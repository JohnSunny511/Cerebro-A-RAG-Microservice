import os
import uuid
import shutil

from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import chromadb

import ollama

from file_loader import load_file
from chunker import chunk_text


app = FastAPI()

# ---------------- DATABASE & OLLAMA ----------------
chroma = chromadb.PersistentClient(path="./db")

# Use 'chroma' here, not 'client'
collection = chroma.get_or_create_collection(
    name="docs", 
    metadata={"hnsw:space": "cosine"}
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_client = ollama.Client(host=OLLAMA_HOST)

MODEL_NAME = os.getenv("LLM_MODEL", "qwen2.5:3b")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------- STARTUP ----------------
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*50)
    print("  CEREBRO RAG SERVER RUNNING")
    print("  Open -> http://localhost:8000")
    print("="*50 + "\n", flush=True)


# ---------------- UI ----------------
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")


# ---------------- QUERY (WITH CONFIDENCE & CITATIONS) ----------------
chat_history = []

@app.post("/query")
def query(q: str):
    global chat_history

    # Retrieve more chunks to give the LLM the full picture
    results = collection.query(query_texts=[q], n_results=8)

    context_items = []
    if results["documents"] and results["documents"][0]:
        for i in range(len(results["documents"][0])):
            doc = results["documents"][0][i]
            meta = (results["metadatas"][0][i] if results["metadatas"] else {}) or {}
            source = meta.get("source", "Manual Entry")
            context_items.append(f"CONTENT: {doc}\nSOURCE: {source}")

    context_str = "\n\n---\n\n".join(context_items)
    
    # Prompting the LLM
    prompt = f"Answer the Question ONLY using the provided Context. Context:\n{context_str}\nQuestion: {q}"
    response = ollama_client.generate(model=MODEL_NAME, prompt=prompt)
    answer = response["response"]

    # --- SMART CONFIDENCE SCALING ---
    # 1. Get the best distance (0.0 to 1.0 in Cosine space)
    best_dist = results["distances"][0][0] if results["distances"] else 1.0
    
    # 2. Count how many unique chunks we found (Evidence Count)
    evidence_weight = len(results["documents"][0]) * 5  # Add 5% for every chunk found
    
    # 3. Calculate Base Score: (Invert distance + add evidence weight + logic boost)
    # We boost by 30 because if we found ANY docs, the LLM is usually capable.
    conf_percent = max(5, min(99, round((1.0 - best_dist) * 100) + evidence_weight + 30))

    # If the LLM says "I don't know", force confidence to 0
    if "don't know" in answer.lower() or "do not know" in answer.lower():
        conf_percent = 0

    status = "HIGH" if conf_percent > 75 else "MEDIUM" if conf_percent > 40 else "LOW"

    chat_history.append({"role": "user", "content": q})
    chat_history.append({"role": "assistant", "content": answer})

    return {"answer": answer, "confidence": conf_percent, "status": status}


# ---------------- ADD TEXT ----------------
@app.post("/add")
def add_knowledge(text: str):
    if not text.strip():
        return {"status": "error", "message": "Empty text"}
        
    doc_id = str(uuid.uuid4())
    
    # Use the first 50 characters of the text as the 'source' 
    # so the Manifest sees them as unique entries
    display_name = text[:50] + "..." if len(text) > 50 else text

    collection.add(
        documents=[text], 
        ids=[doc_id], 
        metadatas=[{"source": display_name}] 
    )
    return {"status": "success", "id": doc_id}


# ---------------- FILE UPLOAD (NEW FEATURE) ----------------
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    print("UPLOADED NAME:", file.filename)
    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)

        # save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # extract text
        text = load_file(file_path)

        if not text.strip():
            return {"status": "error", "message": "File contains no readable text"}

        # split into chunks
        chunks = chunk_text(text)

        added = 0
        for chunk in chunks:
            doc_id = str(uuid.uuid4())
            collection.add(
                documents=[chunk],
                ids=[doc_id],
                metadatas=[{"source": file.filename}]
            )
            added += 1

        return {
            "status": "success",
            "filename": file.filename,
            "chunks_added": added
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------- LIST ----------------
# Replace your current /list endpoint with this:
@app.get("/list")
def list_knowledge():
    data = collection.get(include=["metadatas", "documents"], limit=100)
    
    files = {} # Dictionary to group text by filename/source
    metadatas = data.get("metadatas", [])
    documents = data.get("documents", [])

    if not documents:
        return {"documents": []}

    for i in range(len(documents)):
        meta = metadatas[i] or {}
        content = documents[i]
        display_name = meta.get("source", content[:50] + "...")

        if display_name not in files:
            files[display_name] = {"chunks": [], "count": 0}
        
        files[display_name]["chunks"].append(content)
        files[display_name]["count"] += 1

    result = [
        {"filename": k, "chunks": v["chunks"], "count": v["count"]} 
        for k, v in files.items()
    ]
    return {"documents": result}

# ---------------- DELETE ----------------

@app.delete("/delete/{identifier}")
def delete_knowledge(identifier: str):
    """
    Smart Delete: Checks if identifier is a filename (metadata) 
    or a specific Doc ID.
    """
    # 1. Try to delete by filename (Source Metadata)
    collection.delete(where={"source": identifier})
    
    # 2. Also try to delete as a direct ID (for manual text entries)
    try:
        collection.delete(ids=[identifier])
    except:
        pass 

    return {"status": "success", "message": f"Sector {identifier} purged."}


@app.post("/clear_history")
def clear_history_logic():
    global chat_history
    chat_history = []
    return {"status": "memory_wiped"}

# --- REMOVE the old 'delete_file_from_db' and the duplicate 'clear_history' ---
import os
import uuid
import shutil
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import chromadb
import ollama

from file_loader import load_file
from chunker import chunk_text

# ---------------- API SCHEMAS (Pydantic) ----------------
# These define exactly what the outside world sends and receives.
class QueryResponse(BaseModel):
    answer: str
    confidence: int
    status: str

class KnowledgeItem(BaseModel):
    filename: str
    chunks: List[str]
    count: int

class ListResponse(BaseModel):
    documents: List[KnowledgeItem]

class StatusResponse(BaseModel):
    status: str
    message: Optional[str] = None

# ---------------- APP INITIALIZATION ----------------
app = FastAPI(title="Cerebro RAG Microservice")


# ---------------- STARTUP LOGS ----------------
@app.on_event("startup")
async def startup_event():
    print("\n" + "" + "="*50)
    print("  CEREBRO RAG MICROSERVICE ACTIVE")
    print("  API Documentation: http://localhost:8000/docs")
    print("  Frontend UI:       http://localhost:8000")
    print("="*50 + "\n", flush=True)

# 1. ENABLE CORS: Crucial for microservices
# Allows your frontend (React, Vue, or static HTML) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with your specific domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- DATABASE & OLLAMA ----------------
# If CHROMA_DB_PATH is set (Docker), use it. Otherwise, use local "./db"
DB_PATH = os.getenv("CHROMA_DB_PATH", "./db")
chroma = chromadb.PersistentClient(path=DB_PATH)

collection = chroma.get_or_create_collection(
    name="docs", 
    metadata={"hnsw:space": "cosine"}
)

# If OLLAMA_HOST is set (Docker), use 'ollama-server'. Otherwise, 'localhost'
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_client = ollama.Client(host=OLLAMA_HOST)

# If LLM_MODEL is set (Docker), use it. Otherwise, default to qwen
MODEL_NAME = os.getenv("LLM_MODEL", "qwen2.5:3b")

# Handles uploads directory flexibly
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- UI & STATIC ----------------
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def get_index():
    return FileResponse("static/index.html")

# ---------------- MICROSERVICE ENDPOINTS ----------------

@app.post("/query", response_model=QueryResponse)
def query(q: str):
    """Executes a RAG query against the vector database."""
    results = collection.query(query_texts=[q], n_results=8)

    context_items = []
    if results["documents"] and results["documents"][0]:
        for i in range(len(results["documents"][0])):
            doc = results["documents"][0][i]
            meta = (results["metadatas"][0][i] if results["metadatas"] else {}) or {}
            source = meta.get("source", "Manual Entry")
            context_items.append(f"CONTENT: {doc}\nSOURCE: {source}")

    context_str = "\n\n---\n\n".join(context_items)
    prompt = f"Answer the Question ONLY using the provided Context. Context:\n{context_str}\nQuestion: {q}"
    
    try:
        response = ollama_client.generate(model=MODEL_NAME, prompt=prompt)
        answer = response["response"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama Error: {str(e)}")

    # Confidence Logic
    best_dist = results["distances"][0][0] if results["distances"] else 1.0
    evidence_weight = len(results["documents"][0]) * 5
    conf_percent = max(5, min(99, round((1.0 - best_dist) * 100) + evidence_weight + 30))

    if "don't know" in answer.lower() or "do not know" in answer.lower():
        conf_percent = 0

    status = "HIGH" if conf_percent > 75 else "MEDIUM" if conf_percent > 40 else "LOW"
    return QueryResponse(answer=answer, confidence=conf_percent, status=status)


@app.post("/add", response_model=StatusResponse)
def add_knowledge(text: str):
    """Directly injects text into the knowledge base."""
    if not text.strip():
        return StatusResponse(status="error", message="Empty text")
        
    doc_id = str(uuid.uuid4())
    display_name = text[:50] + "..." if len(text) > 50 else text

    collection.add(
        documents=[text], 
        ids=[doc_id], 
        metadatas=[{"source": display_name}] 
    )
    return StatusResponse(status="success", message=doc_id)


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Uploads and chunks a file for indexing."""
    try:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        text = load_file(file_path)
        if not text.strip():
            return {"status": "error", "message": "File contains no readable text"}

        chunks = chunk_text(text)
        for chunk in chunks:
            collection.add(
                documents=[chunk],
                ids=[str(uuid.uuid4())],
                metadatas=[{"source": file.filename}]
            )

        return {"status": "success", "filename": file.filename, "chunks_added": len(chunks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list", response_model=ListResponse)
def list_knowledge():
    """Lists all files and text chunks stored in the system."""
    data = collection.get(include=["metadatas", "documents"], limit=100)
    files = {}
    metadatas = data.get("metadatas", [])
    documents = data.get("documents", [])

    for i in range(len(documents)):
        meta = metadatas[i] or {}
        content = documents[i]
        display_name = meta.get("source", content[:50] + "...")

        if display_name not in files:
            files[display_name] = {"chunks": [], "count": 0}
        
        files[display_name]["chunks"].append(content)
        files[display_name]["count"] += 1

    result = [KnowledgeItem(filename=k, chunks=v["chunks"], count=v["count"]) for k, v in files.items()]
    return ListResponse(documents=result)


@app.delete("/delete/{identifier}", response_model=StatusResponse)
def delete_knowledge(identifier: str):
    """Removes a file or specific entry from the memory."""
    collection.delete(where={"source": identifier})
    try:
        collection.delete(ids=[identifier])
    except:
        pass 
    return StatusResponse(status="success", message=f"Sector {identifier} purged.")


@app.post("/clear_history")
def clear_history_logic():
    return {"status": "memory_wiped"}
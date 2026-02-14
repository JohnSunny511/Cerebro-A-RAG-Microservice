from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import chromadb
import ollama
import uuid

app = FastAPI()



# Database & Ollama Setup
chroma = chromadb.PersistentClient(path="./db")
collection = chroma.get_or_create_collection("docs")
ollama_client = ollama.Client(host="http://host.docker.internal:11434")


# --- STARTUP MESSAGE ---
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*50)
    print("  RAG OS is running!")
    print("  Click here to open: http://localhost:8000")
    print("="*50 + "\n", flush=True)


# --- SERVING THE UI ---
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def get_index():
    # Return the HTML file when visiting the root URL
    return FileResponse('static/index.html')

# --- API ENDPOINTS ---

@app.post("/query")
def query(q: str):
    results = collection.query(query_texts=[q], n_results=1)
    context = results["documents"][0][0] if results["documents"] and results["documents"][0] else ""
    answer = ollama_client.generate(
        model="tinyllama",
        prompt=f"Answer the Question only based on the provided context. If you cannot answer Question based on the provided Context due to lack of information just say 'I don't know'.Context:{context}\n\n Question:{q}\n"
    )
    return {"answer": answer["response"]}

@app.post("/add")
def add_knowledge(text: str):
    doc_id = str(uuid.uuid4())
    collection.add(documents=[text], ids=[doc_id])
    return {"status": "success", "id": doc_id}

@app.get("/list")
def list_knowledge():
    data = collection.get()
    docs = [{"id": data["ids"][i], "content": data["documents"][i]} 
            for i in range(len(data["documents"] or []))]
    return {"documents": docs}

@app.delete("/delete/{doc_id}")
def delete_knowledge(doc_id: str):
    collection.delete(ids=[doc_id])
    return {"status": "success"}


    
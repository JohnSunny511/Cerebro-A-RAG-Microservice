from fastapi import FastAPI
import chromadb
import ollama

app = FastAPI()
chroma = chromadb.PersistentClient(path="./db")
collection = chroma.get_or_create_collection("docs")

@app.post("/query")
def query(q: str):
    results = collection.query(query_texts=[q], n_results=1)
    context = results["documents"][0][0] if results["documents"] else ""
    print(f"Context being sent to Ollama: {context}")
    answer = ollama.generate(
        model="tinyllama",
        prompt=f"Context:\n{context}\n\nQuestion: {q}\n\nAnswer only based on the provided context. If the answer is not in the context, say \"I don't know\". Answer clearly and concisely:"
    )

    return {"answer": answer["response"]}
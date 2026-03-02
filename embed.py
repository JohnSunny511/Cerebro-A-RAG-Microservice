import chromadb

chroma = chromadb.PersistentClient(path="./db")
collection = chroma.get_or_create_collection("docs")

with open("docs/k8s.txt", "r", encoding="utf-8") as f:
    text = f.read()

chunks = text.split("\n\n")

for i, chunk in enumerate(chunks):
    if chunk.strip():
        collection.add(
            documents=[chunk],
            ids=[f"init-{i}"],
            metadatas=[{"source": "k8s.txt"}]
        )

print("Embedding stored in Chroma")
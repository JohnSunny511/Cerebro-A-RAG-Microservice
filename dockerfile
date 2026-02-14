FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy the requirements-related files and source code
# We specifically add 'static/' here so FastAPI can find your UI
COPY app.py embed.py k8s.txt ./
COPY static/ ./static/

# Install Python dependencies
RUN pip install --no-cache-dir fastapi uvicorn chromadb ollama

# Run your embedding script during build (Note: ensure embed.py doesn't 
# require a running Ollama server if it's strictly local embedding)
RUN python embed.py

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
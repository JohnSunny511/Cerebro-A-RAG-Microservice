FROM python:3.11-slim

WORKDIR /app

# Receive the model name from Docker Compose during build
ARG LLM_MODEL=tinyllama
# Set it as an Environment Variable so Python's os.getenv() can see it
ENV LLM_MODEL=${LLM_MODEL}
ENV OLLAMA_HOST=http://ollama-server:11434

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p static uploads db
COPY *.py ./
COPY static/ ./static/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
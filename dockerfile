FROM python:3.11-slim

WORKDIR /app

# system packages
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# install python deps first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NOW copy the entire project
COPY . .

ENV OLLAMA_HOST=http://ollama-server:11434

RUN python embed.py

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Keep backend/, frontend/, and data/ as siblings, same as the repo layout —
# app/main.py and app/rag/retriever.py both resolve paths relative to that.
COPY backend/ backend/
COPY frontend/ frontend/
COPY data/ data/

WORKDIR /app/backend

# Railway injects $PORT; fall back to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

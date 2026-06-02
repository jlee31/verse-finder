# Quote Finder — a tiny RAG

You type how you're feeling; the app finds the most relevant quotes and has
Claude write a short reflection grounded in them.


### 1. Backend (from scratch)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # if you haven't already
pip install -r requirements.txt

cp .env.example .env          # then paste your Anthropic API key into .env
uvicorn app.main:app --reload --port 8000
```

The first start is slow — it downloads the embedding model. Once running:
- API docs / try it live: http://localhost:8000/docs

### 2. Frontend

It's a single static file. Just open `frontend/index.html` in your browser
(or serve it: `python -m http.server 5173 --directory frontend`).

## Rebuilding the embeddings (only if you change the quotes)

```bash
cd backend/ml
python train.py
```

# to run (refresher)

front end:

```python -m http.server 3000 ```

backend:

```uvicorn app.main:app --reload --port 8000```
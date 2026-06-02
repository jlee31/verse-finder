"""Semantic search over the quote corpus."""
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

BACKEND_DIR = Path(__file__).resolve().parents[2]
ML_DIR = BACKEND_DIR / "ml"
DATA_DIR = BACKEND_DIR.parent / "data"

# Load the model and embeddings once at startup rather than per request.
_model = SentenceTransformer("all-mpnet-base-v2")
_quote_embeddings = np.load(ML_DIR / "quote_embeddings_mpnet.npy")

# quotes_list.json must stay in the same order as the embeddings: row i -> _quotes[i].
with open(ML_DIR / "quotes_list.json") as f:
    _quotes = json.load(f)

# Author lookup keyed by quote text. Optional — fall back to "Unknown" if absent.
_authors = {}
try:
    with open(DATA_DIR / "quotes.json") as f:
        for item in json.load(f):
            _authors[item["text"]] = item.get("author", "Unknown")
except FileNotFoundError:
    pass


def retrieve(query: str, k: int = 3) -> list[dict]:
    """Return the k quotes most similar to the query, best first.

    Each result is {"text", "author", "score"}, where score is cosine
    similarity in [0, 1].
    """
    query_embedding = _model.encode([query])
    scores = cosine_similarity(query_embedding, _quote_embeddings)[0]
    top_idx = np.argsort(scores)[::-1][:k]

    return [
        {
            "text": _quotes[i],
            "author": _authors.get(_quotes[i], "Unknown"),
            "score": float(scores[i]),
        }
        for i in top_idx
    ]

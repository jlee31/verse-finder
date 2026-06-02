# RAG pipeline

Two stages turn a free-text message into a grounded reflection:

1. **Retrieve** (`retriever.py`) — embed the query with `all-mpnet-base-v2`,
   cosine-compare it against the pre-computed quote embeddings, and return the
   top-k quotes. Pure semantic search, no LLM.
2. **Generate** (`generator.py`) — hand those quotes to Claude Haiku with a
   system prompt that forbids inventing material. The model may only speak from
   the retrieved quotes, which is what makes this RAG rather than free
   generation.

`main.py` wires them together: `POST /api/verses/search` runs `retrieve()` then
`generate_reflection()` and returns the reflection plus the source quotes.

```
query ──▶ retrieve(k=3) ──▶ quotes ──▶ generate_reflection() ──▶ reflection
```

## Data files

Both live in `backend/ml/` and must stay row-aligned:

- `quote_embeddings_mpnet.npy` — the embedding matrix.
- `quotes_list.json` — quote text in the same order (row `i` ↔ quote `i`).

Author names come from `data/quotes.json` (optional; missing → "Unknown").

## Notes

- Model and embeddings load once at import, so the first request after startup
  is warm.
- The Anthropic client is created lazily — retrieval and `/docs` work without
  `ANTHROPIC_API_KEY`; only generation needs it.
- Regenerate embeddings whenever the quote corpus changes, or the rows fall out
  of alignment.

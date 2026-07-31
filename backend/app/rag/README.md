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

## Tools (`tools.py`)

`retrieve()` runs exactly once per request, so a message naming two feelings is
averaged into one vector that matches neither. `tools.py` exposes the same
retrieval as a tool the agent can call *repeatedly* — once per emotional facet —
which is what fixes that. It wraps `retriever.py` without touching it.

- `SEARCH_QUOTES_TOOL` — the schema sent in `tools=[...]`. The description says
  *when* to call, not just what it does; that sentence is what drives the
  decomposition behaviour.
- `search_quotes(query, k=3)` — the plain function.
- `dispatch(name, input) -> ToolOutcome` — execution that never raises, because
  an exception inside the agent loop ends the run instead of letting the model
  correct its call. `run_tool()` is the same thing as a `(content, is_error)`
  pair, for callers that only need what goes on the wire.

## The agent (`agent.py`)

`reflect(text)` runs the loop by hand against the raw SDK: send the conversation
with the tool schemas attached, run whatever searches come back, feed the results
in, repeat until the model stops asking. It returns the reflection, the deduped
quotes, and a trace of every search it ran.

```
text ──▶ [ model ] ──tool_use──▶ search_quotes ──tool_result──┐
            ▲                                                 │
            └─────────────────────────────────────────────────┘
                     until end_turn, at most LOOP_BUDGET turns
                                    │
                                    ▼
                       reflection + quotes + trace
```

Three details do the work, and each fails quietly when you get it wrong:

- **All `tool_result` blocks go in one user message.** Split them and the model
  learns that parallel calls don't work, then stops batching them.
- **Assistant turns are appended verbatim**, thinking blocks included — the API
  requires them back unmodified.
- **`LOOP_BUDGET`** is the whole difference between an agent and an infinite
  loop. When it runs out, `_force_finish()` drops the tools *and* explains why;
  measured, each of those alone fails — dropping tools returns empty text, and
  `tool_choice: none` makes the model emit literal `<invoke>` XML as prose.

Nothing in the API calls this yet — that's Stage 4.

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

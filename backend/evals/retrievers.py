"""Retriever adapters the eval can score.

Every retriever returns the same shape, so `run.py` doesn't care whether it's
the one-shot baseline or an agent loop. Stages 2 and 3 add classes here; nothing
else in the eval needs to change.
"""
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Result:
    """What one retriever produced for one query."""

    quotes: list[dict]  # [{"text", "author", "score"}, ...], best first
    trace: list[dict] = field(default_factory=list)  # searches actually run
    api_calls: int = 0  # LLM round trips (0 for the baseline — it's pure vector search)

    @property
    def top_score(self) -> float:
        return self.quotes[0]["score"] if self.quotes else 0.0


class Retriever(Protocol):
    name: str

    def search(self, text: str) -> Result: ...


class BaselineRetriever:
    """The current pipeline: one embedding lookup, top-k by cosine similarity.

    This is what `POST /api/verses/search` does today, and the number every
    later stage is measured against.
    """

    name = "baseline"

    def __init__(self, k: int = 3):
        self.k = k
        self._retrieve = None

    def search(self, text: str) -> Result:
        # Imported lazily: app.rag.retriever loads the mpnet model and the
        # embedding matrix at import time (~20s), and the pure-logic tests
        # must not pay that cost.
        if self._retrieve is None:
            from app.rag.retriever import retrieve

            self._retrieve = retrieve

        quotes = self._retrieve(text, k=self.k)
        return Result(
            quotes=quotes,
            trace=[{"step": 1, "query": text, "returned": len(quotes)}],
            api_calls=0,
        )


REGISTRY: dict[str, type] = {
    "baseline": BaselineRetriever,
}


def build(name: str) -> Retriever:
    if name not in REGISTRY:
        raise SystemExit(
            f"unknown retriever {name!r}; available: {', '.join(sorted(REGISTRY))}"
        )
    return REGISTRY[name]()

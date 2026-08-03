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

    def __init__(self, k: int = 3, name: str = "baseline"):
        self.k = k
        # Carried on the instance, not the class: `name` picks the results
        # filename, and a wide-k variant writing to baseline.json would
        # overwrite the reference numbers.
        self.name = name
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


class AgenticRetriever:
    """An agent loop, scored like any other retriever.

    It decides how many searches to run and with what wording, so there's no `k`
    to set here — the count of quotes is an output, not an input.

    `module` picks the implementation. Both expose the same `reflect()`, which
    is the entire point of building the loop twice.
    """

    def __init__(self, name: str = "agentic", module: str = "app.rag.agent"):
        self.name = name
        self.module = module
        self._reflect = None

    def search(self, text: str) -> Result:
        if self._reflect is None:
            from importlib import import_module

            self._reflect = import_module(self.module).reflect

        result = self._reflect(text)
        return Result(
            quotes=result.quotes,
            trace=result.trace,
            api_calls=result.api_calls,
        )


REGISTRY: dict[str, callable] = {
    "baseline": BaselineRetriever,
    # The volume control. The agent returns roughly this many quotes across all
    # its searches, and more quotes means more chances to cover a facet — so a
    # coverage win over `baseline` alone doesn't prove the decomposition helped.
    # This separates "searched better" from "returned more".
    "baseline-wide": lambda: BaselineRetriever(k=12, name="baseline-wide"),
    # The same agent, twice over. Scoring both head-to-head is what makes the
    # comparison meaningful: a large gap means one has a bug, not that a
    # framework is smarter.
    "agentic": AgenticRetriever,
    "agentic-lc": lambda: AgenticRetriever(name="agentic-lc", module="app.rag.agent_lc"),
}


def build(name: str) -> Retriever:
    if name not in REGISTRY:
        raise SystemExit(
            f"unknown retriever {name!r}; available: {', '.join(sorted(REGISTRY))}"
        )
    return REGISTRY[name]()

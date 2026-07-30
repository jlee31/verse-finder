"""LLM judge: did the retrieved quotes actually speak to each facet?

Cosine similarity can't answer this — a quote can score 0.42 and still be
generic filler. So we ask a model, once per query, with the facets and quotes
together.

Verdicts are cached on disk keyed by the exact inputs, so re-runs cost nothing
and stay deterministic while you iterate on the retrievers.
"""
import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "judge"

MODEL = "claude-opus-5"

# Bump when the rubric below changes — it's part of the cache key, so old
# verdicts are discarded rather than silently reused under new criteria.
PROMPT_VERSION = 1

SYSTEM_PROMPT = (
    "You are grading a quote-retrieval system. Someone described how they feel. "
    "Their message has been broken into distinct emotional facets, and a "
    "retrieval system returned some quotes.\n\n"
    "For each facet, decide whether AT LEAST ONE returned quote genuinely "
    "speaks to it.\n\n"
    "Rules:\n"
    "- Be strict. A quote counts only if someone feeling that specific thing "
    "would find it relevant.\n"
    "- Generic inspirational lines ('life is 10% what happens to you') do NOT "
    "cover a specific facet like grief or anger. Mark those uncovered.\n"
    "- A quote may cover more than one facet.\n"
    "- Judge the quote's meaning, not keyword overlap.\n"
    "- Return every facet you were given, in the order given."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "facets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "facet": {"type": "string"},
                    "covered": {"type": "boolean"},
                    "quote": {
                        "type": "string",
                        "description": "The covering quote, or an empty string if none.",
                    },
                    "reason": {"type": "string", "description": "One short sentence."},
                },
                "required": ["facet", "covered", "quote", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facets"],
    "additionalProperties": False,
}


def _cache_key(text: str, facets: list[str], quotes: list[dict]) -> str:
    payload = json.dumps(
        {
            "v": PROMPT_VERSION,
            "model": MODEL,
            "text": text,
            "facets": facets,
            "quotes": [q["text"] for q in quotes],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def _build_user_message(text: str, facets: list[str], quotes: list[dict]) -> str:
    facet_list = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(facets))
    if quotes:
        quote_list = "\n".join(
            f'{i + 1}. "{q["text"]}" — {q["author"]}' for i, q in enumerate(quotes)
        )
    else:
        quote_list = "(none returned)"
    return (
        f"What they wrote:\n{text}\n\n"
        f"Facets to grade:\n{facet_list}\n\n"
        f"Quotes the system returned:\n{quote_list}"
    )


class Judge:
    """Grades facet coverage, with a disk cache.

    Set `offline=True` to fail loudly instead of calling the API — used by the
    tests, and by `run.py --no-judge` for a retrieval-only smoke run.
    """

    def __init__(self, offline: bool = False, cache_dir: Path | None = None):
        self.offline = offline
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self.hits = 0
        self.misses = 0

    def _client_lazy(self):
        if self._client is None:
            import anthropic

            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set — the judge needs it. "
                    "It lives in backend/.env; run.py loads that automatically."
                )
            self._client = anthropic.Anthropic()
        return self._client

    def judge(self, text: str, facets: list[str], quotes: list[dict]) -> list[dict]:
        """Return one verdict dict per facet, in the order the facets were given."""
        key = _cache_key(text, facets, quotes)
        cached = self.cache_dir / f"{key}.json"

        if cached.exists():
            self.hits += 1
            return json.loads(cached.read_text())["facets"]

        if self.offline:
            raise RuntimeError(
                f"judge is offline and no cached verdict exists for {text!r}"
            )

        self.misses += 1
        response = self._client_lazy().messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            # Grading a handful of quotes is not hard work; low effort keeps the
            # eval cheap enough to re-run freely. Thinking stays on (the default
            # on Opus 5) — disabling it risks stray tags in the output.
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
            },
            messages=[
                {"role": "user", "content": _build_user_message(text, facets, quotes)}
            ],
        )

        raw = next(b.text for b in response.content if b.type == "text")
        verdicts = json.loads(raw)["facets"]
        verdicts = _align(verdicts, facets)

        cached.write_text(json.dumps({"facets": verdicts}, indent=2))
        return verdicts


def _align(verdicts: list[dict], facets: list[str]) -> list[dict]:
    """Guarantee one verdict per requested facet, in the requested order.

    The schema constrains shape but not count, so a model that drops or
    reorders a facet would otherwise corrupt the score silently.
    """
    by_name = {v["facet"]: v for v in verdicts}
    aligned = []
    for f in facets:
        v = by_name.get(f)
        if v is None:
            v = {
                "facet": f,
                "covered": False,
                "quote": "",
                "reason": "judge returned no verdict for this facet",
            }
        aligned.append(v)
    return aligned

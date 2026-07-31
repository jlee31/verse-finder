"""LLM judge: did the retrieved quotes actually speak to each facet?

Cosine similarity can't answer this — a quote can score 0.42 and still be
generic filler. So we ask a model, with the facets and quotes together.

Two things keep the number trustworthy, and both were forced by measurement
rather than chosen up front:

- **The rubric rules on the emotion, not its object.** Stage 3 chased a 0.07
  gap between two implementations of the *same* agent and found the judge
  flipping, not the code. Every disagreement sat on one axis: a quote that
  speaks to anger but not to *family* anger. The rubric never said which way
  that goes, so the judge decided afresh each time. It says now.
- **Every facet is graded `ROUNDS` times and the majority wins.** A rubric can
  narrow the ambiguity but not erase it, so the residual gets averaged out —
  and each verdict records its vote count, which turns the leftover noise into
  something the results file reports rather than something you have to go
  looking for.

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
#   1: original rubric, single round.
#   2: object-vs-emotion rule added; majority vote over ROUNDS.
PROMPT_VERSION = 2

# Odd, so a majority always exists. Three is enough to absorb a facet that
# flips occasionally; it does not save one the judge is genuinely split on,
# and `votes` in the verdict is how you tell those apart.
ROUNDS = 3

SYSTEM_PROMPT = (
    "You are grading a quote-retrieval system. Someone described how they feel. "
    "Their message has been broken into distinct emotional facets, and a "
    "retrieval system returned some quotes.\n\n"
    "For each facet, decide whether AT LEAST ONE returned quote genuinely "
    "speaks to it.\n\n"
    "Rules:\n"
    "- Grade the FEELING, not its object. A facet like 'anger toward family' "
    "names an emotion (anger) and its object (family). A quote that speaks to "
    "the emotion COVERS the facet even if it never mentions the object — "
    "'holding on to anger is like grasping a hot coal' covers 'anger toward "
    "family'. Someone can carry a general truth about anger into their own "
    "situation; a corpus of general quotes is not expected to name their "
    "family, their job, or their father.\n"
    "- Still be strict about the emotion itself. A quote counts only if "
    "someone feeling that specific thing would find it relevant.\n"
    "- Generic inspirational lines ('life is 10% what happens to you') name no "
    "emotion at all and cover nothing. Mark those uncovered. This is the "
    "distinction that matters: general ABOUT THE FEELING counts, vague about "
    "everything does not.\n"
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


def _cache_key(text: str, facets: list[str], quotes: list[dict], round_: int = 0) -> str:
    """Cache identity for one grading round.

    `round_` is in the key so the rounds of a majority vote cache separately.
    Without it the second round would read back the first one's verdict and the
    vote would be unanimous by construction.
    """
    payload = json.dumps(
        {
            "v": PROMPT_VERSION,
            "model": MODEL,
            "round": round_,
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

    def __init__(
        self,
        offline: bool = False,
        cache_dir: Path | None = None,
        rounds: int = ROUNDS,
    ):
        if rounds < 1 or rounds % 2 == 0:
            raise ValueError(f"rounds must be odd and >= 1, got {rounds}")
        self.offline = offline
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rounds = rounds
        self._client = None
        self.hits = 0
        self.misses = 0
        self.split = 0  # facet verdicts the rounds disagreed on

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
        """Return one verdict dict per facet, in the order the facets were given.

        Each facet is graded `self.rounds` times and the majority wins. The
        returned verdict carries `votes` so a 2-1 call is distinguishable from
        a 3-0 one in the results file.
        """
        rounds = [
            self._judge_once(text, facets, quotes, i) for i in range(self.rounds)
        ]
        verdicts = _vote(rounds, facets)
        self.split += sum(1 for v in verdicts if 0 < v["votes"] < self.rounds)
        return verdicts

    def _judge_once(
        self, text: str, facets: list[str], quotes: list[dict], round_: int
    ) -> list[dict]:
        """One independent grading pass, cached on disk."""
        key = _cache_key(text, facets, quotes, round_)
        cached = self.cache_dir / f"{key}.json"

        if cached.exists():
            self.hits += 1
            return _align(json.loads(cached.read_text())["facets"], facets)

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


def _vote(rounds: list[list[dict]], facets: list[str]) -> list[dict]:
    """Collapse independent grading rounds into one verdict per facet.

    The winning side supplies the quote and reason, so the text you read next
    to a verdict is an argument for the verdict that was actually recorded —
    not a dissent from the round that lost.
    """
    if not rounds:
        raise ValueError("no rounds to vote on")

    n = len(rounds)
    out = []
    for i, facet in enumerate(facets):
        votes = [r[i] for r in rounds]
        yes = [v for v in votes if v["covered"]]
        covered = 2 * len(yes) > n
        winner = (yes if covered else [v for v in votes if not v["covered"]])[0]
        out.append({
            "facet": facet,
            "covered": covered,
            "quote": winner["quote"],
            "reason": winner["reason"],
            "votes": len(yes),
            "rounds": n,
        })
    return out


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

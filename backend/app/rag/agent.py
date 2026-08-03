"""The agent loop, written by hand against the raw Anthropic SDK.

Stage 2 of the agent plan. The pipeline in `retriever.py` searches once, so a
message naming two feelings is averaged into one vector matching neither. This
loop lets the model decide to search *again*, differently, based on what came
back — the one thing a fixed pipeline cannot do.

The loop is four lines of idea:

    1. send the conversation with the tool schemas attached
    2. if stop_reason == "tool_use", run every requested call
    3. append ALL the results in ONE user message, and go round again
    4. stop on end_turn, or when the iteration budget runs out

Two details carry most of the weight, and both are easy to get wrong:

- **All `tool_result` blocks go in a single user message.** The model asked for
  two searches in one turn; splitting the answers across two messages teaches it
  that parallel calls don't work, and it stops batching them.
- **A failed tool comes back as `is_error: true`, not as a dropped result.**
  Every `tool_use` block must be answered or the next request is malformed, and
  an error the model can read is one it can recover from.

`LOOP_BUDGET` is the third: it is the entire difference between an agent and an
infinite loop.
"""
from dataclasses import dataclass, field

import anthropic

from app.rag.tools import TOOLS, dispatch

MODEL = "claude-opus-5"
MAX_TOKENS = 4096

# Enough turns to search, notice a gap, and search again — the behaviour this
# exists for — without letting a confused run bill indefinitely.
LOOP_BUDGET = 6

SYSTEM_PROMPT = (
    "You are a thoughtful companion. Someone shares what they are going "
    "through, and you find quotes that speak to it and reflect back.\n\n"
    "How to search:\n"
    "- First, break their message into its distinct emotional facets. People "
    "rarely feel one clean thing: 'grieving my dad and angry at my family' is "
    "grief AND anger, and they need different quotes.\n"
    "- Call search_quotes once per facet. One theme per call — a query naming "
    "two feelings matches neither well.\n"
    "- Read the scores and the quotes that come back. Ask yourself: is each "
    "facet actually answered, or did I get generic filler? A high score on a "
    "vague quote does not mean the facet is covered.\n"
    "- If a facet is uncovered, search again with different words for it. If "
    "the corpus genuinely has nothing, accept that and move on — do not keep "
    "searching for something that isn't there.\n"
    "- Stop searching once every facet is covered or shown to be uncoverable.\n\n"
    "Then write the reflection:\n"
    "- Ground it ONLY in the quotes you retrieved. Never invent a quote or "
    "attribute an idea to an author you were not given.\n"
    "- Speak to every facet you found quotes for, not just the strongest one. "
    "That is the point of searching more than once.\n"
    "- Write 3-5 sentences. Warm and direct, not preachy.\n"
    "- If a facet turned up nothing genuine, say so honestly rather than "
    "stretching an unrelated quote to fit.\n"
    "- Do not narrate your searching. They see the reflection, not the process."
)


@dataclass
class AgentResult:
    """One agent run."""

    reflection: str
    quotes: list[dict] = field(default_factory=list)  # deduped, best score first
    trace: list[dict] = field(default_factory=list)  # every search, in order
    api_calls: int = 0
    stopped_early: bool = False  # hit LOOP_BUDGET without finishing

    @property
    def searches(self) -> int:
        return len(self.trace)


_client = None


def _get_client() -> anthropic.Anthropic:
    """Created lazily so importing this module doesn't require an API key."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _merge(collected: dict[str, dict], quotes: list[dict]) -> None:
    """Accumulate quotes across searches, keeping the best score for each.

    The same quote can surface under two different facets; the person should
    see it once, at the score that actually found it.
    """
    for q in quotes:
        existing = collected.get(q["text"])
        if existing is None or q["score"] > existing["score"]:
            collected[q["text"]] = q


def _final_text(content) -> str:
    """The reflection: the text blocks of the model's last turn.

    Joined rather than taking the first — a turn can be split across blocks, and
    silently dropping the tail would truncate the reflection mid-thought.
    """
    return "\n\n".join(b.text.strip() for b in content if b.type == "text" and b.text.strip())


def reflect(text: str, *, budget: int = LOOP_BUDGET, client=None) -> AgentResult:
    """Search the corpus as many times as it takes, then reflect on what it found.

    `client` is injectable so the loop can be tested without the network.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if budget < 1:
        raise ValueError("budget must be at least 1")

    client = client or _get_client()
    messages = [{"role": "user", "content": text.strip()}]

    collected: dict[str, dict] = {}
    trace: list[dict] = []
    api_calls = 0
    reflection = ""
    stopped_early = True  # cleared the moment the model finishes on its own

    for _ in range(budget):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            # The judging step — "is this facet actually covered?" — is the
            # reasoning this whole design depends on. Leave it on.
            thinking={"type": "adaptive"},
            messages=messages,
        )
        api_calls += 1

        # Appended whole, including thinking blocks: the API requires them back
        # unmodified on the next turn.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            reflection = _final_text(response.content)
            stopped_early = False
            break

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            outcome = dispatch(block.name, block.input)
            _merge(collected, outcome.quotes)

            step = {
                "step": len(trace) + 1,
                "tool": block.name,
                "query": (block.input or {}).get("query") if isinstance(block.input, dict) else None,
                "returned": len(outcome.quotes),
                "top_score": round(outcome.quotes[0]["score"], 3) if outcome.quotes else None,
            }
            if outcome.is_error:
                step["error"] = outcome.content
            trace.append(step)

            result_block = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": outcome.content,
            }
            if outcome.is_error:
                result_block["is_error"] = True
            results.append(result_block)

        if not results:
            # stop_reason said tool_use but no tool_use block arrived. Sending a
            # user message with empty content is a 400, so stop and let the
            # forced finish salvage a reflection.
            break

        # One message, every result. Splitting them teaches the model to stop
        # asking for searches in parallel.
        messages.append({"role": "user", "content": results})

    if stopped_early:
        reflection, extra = _force_finish(client, messages)
        api_calls += extra

    return AgentResult(
        reflection=reflection,
        quotes=sorted(collected.values(), key=lambda q: q["score"], reverse=True),
        trace=trace,
        api_calls=api_calls,
        stopped_early=stopped_early,
    )


OUT_OF_BUDGET = (
    "Your search budget is used up. Write the reflection now, using only the "
    "quotes you have already retrieved. Do not search again."
)


def _force_finish(client, messages) -> tuple[str, int]:
    """Get a reflection out of a run that used up its budget still searching.

    Without this the person gets nothing at all from a run that already paid for
    six turns of retrieval.

    Both halves are load-bearing, and each fails alone — measured, not guessed:
    dropping `tools` on its own returns an empty text block, and keeping them
    with `tool_choice: none` makes the model emit literal `<invoke>` tool-call
    syntax as prose. Removing the option structurally *and* saying why is what
    produces an actual reflection.
    """
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            messages=messages + [{"role": "user", "content": OUT_OF_BUDGET}],
        )
        return _final_text(response.content), 1
    except Exception:
        # Already over budget and now failing — return the quotes, not an
        # exception. The caller can still show what was found.
        return "", 1

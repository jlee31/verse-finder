"""Tests for the hand-rolled agent loop.

The loop is driven by a fake client, so every test here runs offline and in
milliseconds. That matters: the things worth pinning are the message-assembly
rules, and those are exactly what a live test would obscure behind model
variation.

    pytest -q                  # these
    pytest -q -m live          # one real API round trip (costs money)
"""
from dataclasses import dataclass, field

import pytest

from app.rag import agent
from app.rag.agent import AgentResult, _final_text, _merge, reflect
from app.rag.tools import ToolOutcome


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------

@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ThinkingBlock:
    thinking: str = "hmm"
    type: str = "thinking"


@dataclass
class ToolUseBlock:
    id: str
    input: dict
    name: str = "search_quotes"
    type: str = "tool_use"


@dataclass
class Response:
    content: list
    stop_reason: str


@dataclass
class FakeClient:
    """Replays canned responses and records every request it was sent."""

    responses: list
    calls: list = field(default_factory=list)

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        # The loop appends to one `messages` list in place, so recording it by
        # reference would show every call holding the final conversation.
        # Snapshot it to capture what this request actually sent.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self.responses:
            raise AssertionError("the loop made more API calls than expected")
        return self.responses.pop(0)


def _quote(text, score):
    return {"text": text, "author": "A", "score": score}


@pytest.fixture
def fake_dispatch(monkeypatch):
    """Stub tool execution. Returns the log of (name, input) calls."""
    calls = []

    def fake(name, tool_input):
        calls.append((name, tool_input))
        query = (tool_input or {}).get("query", "")
        if query == "boom":
            return ToolOutcome("Invalid arguments: query must be a non-empty string",
                               is_error=True)
        return ToolOutcome(f"results for {query}", quotes=[_quote(f"{query} quote", 0.5)])

    monkeypatch.setattr(agent, "dispatch", fake)
    return calls


def _answer(text="a reflection"):
    return Response([ThinkingBlock(), TextBlock(text)], "end_turn")


def _searches(*queries):
    return Response(
        [ThinkingBlock(), TextBlock("let me look")]
        + [ToolUseBlock(id=f"tu_{i}", input={"query": q}) for i, q in enumerate(queries)],
        "tool_use",
    )


# --------------------------------------------------------------------------
# the simple path
# --------------------------------------------------------------------------

def test_a_run_with_no_tool_calls_returns_the_text(fake_dispatch):
    client = FakeClient([_answer("just this")])
    result = reflect("i feel lonely", client=client)

    assert result.reflection == "just this"
    assert result.api_calls == 1
    assert result.trace == []
    assert result.stopped_early is False
    assert fake_dispatch == []


def test_the_person_message_is_what_gets_sent(fake_dispatch):
    client = FakeClient([_answer()])
    reflect("  i feel lonely  ", client=client)

    assert client.calls[0]["messages"] == [{"role": "user", "content": "i feel lonely"}]


def test_tools_and_thinking_are_attached(fake_dispatch):
    client = FakeClient([_answer()])
    reflect("i feel lonely", client=client)

    names = [t["name"] for t in client.calls[0]["tools"]]
    assert "search_quotes" in names
    assert client.calls[0]["thinking"] == {"type": "adaptive"}


# --------------------------------------------------------------------------
# message assembly — the part that is easy to get wrong
# --------------------------------------------------------------------------

def test_all_tool_results_go_in_one_user_message(fake_dispatch):
    """The lesson of the loop.

    The model asked for two searches in a single turn. Splitting the answers
    across two user messages teaches it that parallel calls don't work, and it
    stops batching them.
    """
    client = FakeClient([_searches("grief", "anger"), _answer()])
    reflect("grieving and angry", client=client)

    sent = client.calls[1]["messages"]
    assert sent[-1]["role"] == "user"
    assert len(sent[-1]["content"]) == 2
    assert all(b["type"] == "tool_result" for b in sent[-1]["content"])


def test_every_tool_use_is_answered_by_its_own_id(fake_dispatch):
    # An unanswered tool_use block makes the next request malformed.
    client = FakeClient([_searches("grief", "anger"), _answer()])
    reflect("grieving and angry", client=client)

    ids = [b["tool_use_id"] for b in client.calls[1]["messages"][-1]["content"]]
    assert ids == ["tu_0", "tu_1"]


def test_assistant_turns_are_appended_verbatim(fake_dispatch):
    """Thinking blocks must go back unmodified or the API rejects the turn."""
    search_turn = _searches("grief")
    client = FakeClient([search_turn, _answer()])
    reflect("grieving", client=client)

    assistant = client.calls[1]["messages"][1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] is search_turn.content
    assert any(b.type == "thinking" for b in assistant["content"])


def test_a_failed_tool_is_flagged_not_dropped(fake_dispatch):
    client = FakeClient([_searches("boom"), _answer()])
    reflect("grieving", client=client)

    block = client.calls[1]["messages"][-1]["content"][0]
    assert block["is_error"] is True
    assert "Invalid arguments" in block["content"]


def test_a_successful_tool_result_carries_no_error_flag(fake_dispatch):
    client = FakeClient([_searches("grief"), _answer()])
    reflect("grieving", client=client)

    assert "is_error" not in client.calls[1]["messages"][-1]["content"][0]


# --------------------------------------------------------------------------
# accumulating results
# --------------------------------------------------------------------------

def test_quotes_accumulate_across_searches(fake_dispatch):
    client = FakeClient([_searches("grief", "anger"), _answer()])
    result = reflect("grieving and angry", client=client)

    assert {q["text"] for q in result.quotes} == {"grief quote", "anger quote"}


def test_merge_keeps_the_best_score_for_a_repeated_quote():
    # The same quote can surface under two facets; show it once, at the score
    # that actually found it.
    collected = {}
    _merge(collected, [_quote("same", 0.4)])
    _merge(collected, [_quote("same", 0.7)])
    _merge(collected, [_quote("same", 0.5)])

    assert len(collected) == 1
    assert collected["same"]["score"] == 0.7


def test_quotes_come_back_best_first(monkeypatch):
    def fake(name, tool_input):
        q = tool_input["query"]
        return ToolOutcome("ok", quotes=[_quote(f"{q}-a", 0.3), _quote(f"{q}-b", 0.9)])

    monkeypatch.setattr(agent, "dispatch", fake)
    client = FakeClient([_searches("x", "y"), _answer()])
    result = reflect("x and y", client=client)

    scores = [q["score"] for q in result.quotes]
    assert scores == sorted(scores, reverse=True)


# --------------------------------------------------------------------------
# the trace
# --------------------------------------------------------------------------

def test_trace_records_each_search_in_order(fake_dispatch):
    client = FakeClient([_searches("grief", "anger"), _answer()])
    result = reflect("grieving and angry", client=client)

    assert [s["step"] for s in result.trace] == [1, 2]
    assert [s["query"] for s in result.trace] == ["grief", "anger"]
    assert result.searches == 2


def test_trace_records_returned_count_and_top_score(fake_dispatch):
    client = FakeClient([_searches("grief"), _answer()])
    result = reflect("grieving", client=client)

    assert result.trace[0]["returned"] == 1
    assert result.trace[0]["top_score"] == 0.5


def test_trace_numbers_keep_climbing_across_turns(fake_dispatch):
    # Steps are the person's view of "how it searched" — they must not reset
    # every time the loop goes round.
    client = FakeClient([_searches("a", "b"), _searches("c"), _answer()])
    result = reflect("x", client=client)

    assert [s["step"] for s in result.trace] == [1, 2, 3]


def test_trace_records_a_failed_search(fake_dispatch):
    client = FakeClient([_searches("boom"), _answer()])
    result = reflect("x", client=client)

    assert "error" in result.trace[0]
    assert result.trace[0]["returned"] == 0
    assert result.trace[0]["top_score"] is None


# --------------------------------------------------------------------------
# the iteration budget — what separates an agent from an infinite loop
# --------------------------------------------------------------------------

def test_a_model_that_never_stops_is_cut_off(fake_dispatch):
    # Five searching turns offered, budget of 3: the loop must stop on its own.
    client = FakeClient([_searches("a") for _ in range(5)] + [_answer("forced")])
    result = reflect("x", client=client, budget=3)

    assert result.stopped_early is True
    assert result.searches == 3


def test_budget_exhaustion_still_produces_a_reflection(fake_dispatch):
    client = FakeClient([_searches("a"), _searches("b"), _answer("forced")])
    result = reflect("x", client=client, budget=2)

    assert result.reflection == "forced"
    # 2 loop turns + the forced finish.
    assert result.api_calls == 3


def test_the_forced_finish_removes_the_tools_and_says_why(fake_dispatch):
    """Measured, not assumed: dropping tools alone returns empty text, and
    tool_choice:none alone makes the model emit <invoke> XML as prose."""
    client = FakeClient([_searches("a"), _answer("forced")])
    reflect("x", client=client, budget=1)

    final = client.calls[-1]
    assert "tools" not in final
    assert final["messages"][-1]["content"] == agent.OUT_OF_BUDGET


def test_a_failing_forced_finish_still_returns_the_quotes(monkeypatch, fake_dispatch):
    class Dies(FakeClient):
        def create(self, **kwargs):
            if "tools" not in kwargs:  # the forced-finish call
                raise RuntimeError("overloaded")
            return super().create(**kwargs)

    client = Dies([_searches("grief")])
    result = reflect("x", client=client, budget=1)

    # A run that already paid for retrieval should surface it, not raise.
    assert result.reflection == ""
    assert [q["text"] for q in result.quotes] == ["grief quote"]
    assert result.stopped_early is True


# --------------------------------------------------------------------------
# odds and ends
# --------------------------------------------------------------------------

def test_a_tool_use_stop_with_no_tool_blocks_does_not_send_empty_content(fake_dispatch):
    # A user message with an empty content list is a 400. Bail out and let the
    # forced finish salvage a reflection instead.
    client = FakeClient([Response([TextBlock("hm")], "tool_use"), _answer("salvaged")])
    result = reflect("x", client=client)

    assert result.reflection == "salvaged"
    assert result.stopped_early is True


@pytest.mark.parametrize("bad", ["", "   ", None, 7])
def test_blank_input_is_rejected(bad):
    with pytest.raises(ValueError, match="non-empty string"):
        reflect(bad, client=FakeClient([]))


def test_a_budget_below_one_is_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        reflect("x", client=FakeClient([]), budget=0)


def test_final_text_joins_split_blocks():
    # A turn can arrive as several text blocks; taking only the first would
    # truncate the reflection mid-thought.
    assert _final_text([TextBlock("one"), TextBlock("two")]) == "one\n\ntwo"


def test_final_text_ignores_thinking_and_empty_blocks():
    assert _final_text([ThinkingBlock(), TextBlock("  "), TextBlock("real")]) == "real"


def test_the_reflection_excludes_narration_from_earlier_turns(fake_dispatch):
    # "let me look" is said on the searching turn; only the last turn is the
    # reflection.
    client = FakeClient([_searches("grief"), _answer("the reflection")])
    result = reflect("x", client=client)

    assert result.reflection == "the reflection"


def test_searches_counts_the_trace():
    assert AgentResult(reflection="x").searches == 0


# --------------------------------------------------------------------------
# one real round trip
# --------------------------------------------------------------------------

@pytest.mark.live
def test_the_agent_finds_anger_on_the_compound_query():
    """Stage 2's accept criterion, against the real API and real corpus.

    The baseline returns zero anger quotes for this message. The agent should
    search more than once and come back with some.
    """
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    result = reflect("i'm grieving my dad and angry at my family")

    assert result.searches >= 2, "the agent didn't decompose the query"
    assert not result.stopped_early
    joined = " ".join(q["text"] for q in result.quotes).lower()
    assert "anger" in joined or "resentment" in joined
    assert result.reflection

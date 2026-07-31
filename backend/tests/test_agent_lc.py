"""Tests for the LangGraph implementation.

Two jobs here that the hand-rolled tests don't have:

1. Prove the two implementations are genuinely the same agent — same model,
   same prompt, same tool description. If those drift, the eval comparison
   stops measuring the machinery and starts measuring the prompt.
2. Pin the graph's shape, since with a framework the control flow is data
   rather than code you can read top to bottom.

    pytest -q                  # these
    pytest -q -m live          # real API round trips
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from app.rag import agent, agent_lc
from app.rag.agent_lc import (
    _Collector,
    _count_api_calls,
    _drop_unanswered_tool_calls,
    _text,
    build_graph,
    reflect,
)
from app.rag.tools import SEARCH_QUOTES_TOOL, ToolOutcome


@pytest.fixture
def dummy_key(monkeypatch):
    """ChatAnthropic reads the key at construction; it makes no network call."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")


def _quote(text, score):
    return {"text": text, "author": "A", "score": score}


# --------------------------------------------------------------------------
# the two implementations must stay the same agent
# --------------------------------------------------------------------------

def test_both_implementations_share_the_prompt_and_model():
    """Imported, not copied.

    A gap in the eval scores should mean one of them has a bug — not that
    someone quietly improved one system prompt and forgot the other.
    """
    assert agent_lc.SYSTEM_PROMPT is agent.SYSTEM_PROMPT
    assert agent_lc.MODEL == agent.MODEL
    assert agent_lc.MAX_TOKENS == agent.MAX_TOKENS
    assert agent_lc.LOOP_BUDGET == agent.LOOP_BUDGET


def test_the_langgraph_tool_carries_the_hand_written_description(dummy_key):
    # The description is what drives decomposition. Letting the docstring win
    # here would make the two agents behave differently for a reason that has
    # nothing to do with LangGraph.
    tool = _only_tool(dummy_key)
    assert tool.description == SEARCH_QUOTES_TOOL["description"]


def test_the_inferred_schema_matches_the_hand_written_one(dummy_key):
    schema = _only_tool(dummy_key).args_schema.model_json_schema()
    hand = SEARCH_QUOTES_TOOL["input_schema"]

    assert set(schema["properties"]) == set(hand["properties"])
    assert schema["required"] == hand["required"]  # k stays optional


def _only_tool(_dummy_key=None):
    """The search tool as the graph binds it."""
    collector = _Collector()
    captured = {}

    real = agent_lc.ToolNode

    def spy(tools):
        captured["tools"] = tools
        return real(tools)

    agent_lc.ToolNode = spy
    try:
        build_graph(collector)
    finally:
        agent_lc.ToolNode = real
    return captured["tools"][0]


# --------------------------------------------------------------------------
# graph shape
# --------------------------------------------------------------------------

def test_the_graph_is_an_agent_tools_cycle(dummy_key):
    """The conditional edge IS the `stop_reason == "tool_use"` branch."""
    drawn = build_graph(_Collector()).get_graph()
    nodes = set(drawn.nodes)
    edges = {(e.source, e.target) for e in drawn.edges}

    assert {"agent", "tools"} <= nodes
    assert ("__start__", "agent") in edges
    assert ("tools", "agent") in edges  # the cycle
    assert ("agent", "tools") in edges
    assert ("agent", "__end__") in edges  # the way out


# --------------------------------------------------------------------------
# the collector — what the framework costs
# --------------------------------------------------------------------------

def test_the_collector_catches_quotes_toolnode_would_discard():
    # ToolNode only passes the rendered string to the model, so without this
    # the structured results are gone by the time the run ends.
    c = _Collector()
    c.record("grief", ToolOutcome("rendered", quotes=[_quote("q", 0.5)]))

    assert c.quotes == [_quote("q", 0.5)]
    assert c.trace[0]["query"] == "grief"
    assert c.trace[0]["returned"] == 1
    assert c.trace[0]["top_score"] == 0.5


def test_the_collector_dedupes_and_sorts_like_the_handrolled_loop():
    c = _Collector()
    c.record("a", ToolOutcome("x", quotes=[_quote("same", 0.4), _quote("low", 0.1)]))
    c.record("b", ToolOutcome("x", quotes=[_quote("same", 0.9)]))

    assert [q["score"] for q in c.quotes] == [0.9, 0.1]


def test_the_collector_numbers_steps_and_flags_errors():
    c = _Collector()
    c.record("a", ToolOutcome("ok", quotes=[_quote("q", 0.5)]))
    c.record("b", ToolOutcome("Invalid arguments: nope", is_error=True))

    assert [s["step"] for s in c.trace] == [1, 2]
    assert "error" in c.trace[1]
    assert c.trace[1]["top_score"] is None


# --------------------------------------------------------------------------
# message helpers
# --------------------------------------------------------------------------

def test_text_reads_a_plain_string_message():
    assert _text(AIMessage("hello")) == "hello"


def test_text_skips_thinking_blocks():
    # With thinking on, content is a list of blocks; the reasoning must not end
    # up in the reflection.
    msg = AIMessage([
        {"type": "thinking", "thinking": "internal"},
        {"type": "text", "text": "the reflection"},
    ])
    assert _text(msg) == "the reflection"


def test_text_joins_split_text_blocks():
    msg = AIMessage([{"type": "text", "text": "one"}, {"type": "text", "text": "two"}])
    assert _text(msg) == "one\n\ntwo"


def test_api_calls_counts_assistant_turns():
    messages = [SystemMessage("s"), HumanMessage("h"), AIMessage("a"),
                ToolMessage("t", tool_call_id="1"), AIMessage("a2")]
    assert _count_api_calls(messages) == 2


def test_dangling_tool_calls_are_trimmed_before_the_salvage_call():
    """A budget overrun can stop between the agent node and the tools node.

    The API rejects an assistant turn whose tool calls were never answered, so
    leaving it in makes the salvage call fail and return an empty reflection —
    which is exactly what happened before this existed.
    """
    asked = AIMessage("", tool_calls=[{"name": "search_quotes", "args": {}, "id": "tc1"}])
    trimmed = _drop_unanswered_tool_calls([HumanMessage("h"), asked])

    assert [type(m) for m in trimmed] == [HumanMessage]


def test_answered_tool_calls_are_kept():
    asked = AIMessage("", tool_calls=[{"name": "search_quotes", "args": {}, "id": "tc1"}])
    answered = ToolMessage("results", tool_call_id="tc1")
    messages = [HumanMessage("h"), asked, answered]

    assert _drop_unanswered_tool_calls(messages) == messages


# --------------------------------------------------------------------------
# the run, against a fake graph
# --------------------------------------------------------------------------

class FakeGraph:
    """Replays states, and raises like LangGraph does when the budget is spent."""

    def __init__(self, collector, states, searches=(), overrun=False):
        self.collector = collector
        self.states = states
        self.searches = searches
        self.overrun = overrun
        self.config = None

    def stream(self, inputs, config=None, stream_mode=None):
        self.config = config
        self.inputs = inputs
        for query, outcome in self.searches:
            self.collector.record(query, outcome)
        for state in self.states:
            yield state
        if self.overrun:
            raise GraphRecursionError("recursion limit reached")


def _builder(**kwargs):
    return lambda collector: FakeGraph(collector, **kwargs)


def test_a_completed_run_returns_the_last_message_as_the_reflection():
    build = _builder(states=[{"messages": [HumanMessage("h"), AIMessage("done")]}])
    result = reflect("i feel lonely", build=build)

    assert result.reflection == "done"
    assert result.stopped_early is False
    assert result.api_calls == 1


def test_the_system_prompt_and_message_are_what_enter_the_graph():
    graphs = []

    def build(collector):
        g = FakeGraph(collector, [{"messages": [AIMessage("done")]}])
        graphs.append(g)
        return g

    reflect("  i feel lonely  ", build=build)
    sent = graphs[0].inputs["messages"]

    assert isinstance(sent[0], SystemMessage)
    assert sent[0].content == agent.SYSTEM_PROMPT
    assert sent[1].content == "i feel lonely"


def test_quotes_and_trace_come_back_from_the_collector():
    build = _builder(
        states=[{"messages": [AIMessage("done")]}],
        searches=[("grief", ToolOutcome("x", quotes=[_quote("g", 0.5)])),
                  ("anger", ToolOutcome("x", quotes=[_quote("a", 0.7)]))],
    )
    result = reflect("grieving and angry", build=build)

    assert [q["score"] for q in result.quotes] == [0.7, 0.5]
    assert result.searches == 2


def test_the_budget_becomes_a_recursion_limit():
    """One agent turn plus its tools turn is two graph steps.

    2N-1 looks right and is not: it cuts the graph off before the last round of
    searches runs, so the salvage call has no quotes to work with.
    """
    graphs = []

    def build(collector):
        g = FakeGraph(collector, [{"messages": [AIMessage("done")]}])
        graphs.append(g)
        return g

    reflect("x", budget=3, build=build)
    assert graphs[0].config["recursion_limit"] == 6


def test_a_budget_overrun_is_salvaged(monkeypatch):
    monkeypatch.setattr(agent_lc, "_force_finish", lambda messages: ("salvaged", 1))
    build = _builder(
        states=[{"messages": [AIMessage("thinking about it")]}],
        searches=[("grief", ToolOutcome("x", quotes=[_quote("g", 0.5)]))],
        overrun=True,
    )
    result = reflect("x", budget=1, build=build)

    assert result.stopped_early is True
    assert result.reflection == "salvaged"
    # The searches already paid for must survive the overrun.
    assert [q["text"] for q in result.quotes] == ["g"]
    assert result.api_calls == 2  # one streamed turn + the salvage


def test_an_empty_final_message_also_triggers_the_salvage(monkeypatch):
    # The graph can finish with nothing but thinking blocks; that is not a
    # reflection, and the person should still get one.
    monkeypatch.setattr(agent_lc, "_force_finish", lambda messages: ("salvaged", 1))
    build = _builder(states=[{"messages": [AIMessage([{"type": "thinking",
                                                       "thinking": "hm"}])]}])
    result = reflect("x", build=build)

    assert result.reflection == "salvaged"
    assert result.stopped_early is True


def test_a_failing_salvage_still_returns_the_quotes(monkeypatch, dummy_key):
    def boom(*a, **k):
        raise RuntimeError("overloaded")

    monkeypatch.setattr(agent_lc, "_model", boom)
    build = _builder(
        states=[{"messages": [AIMessage("")]}],
        searches=[("grief", ToolOutcome("x", quotes=[_quote("g", 0.5)]))],
        overrun=True,
    )
    result = reflect("x", budget=1, build=build)

    assert result.reflection == ""
    assert [q["text"] for q in result.quotes] == ["g"]


@pytest.mark.parametrize("bad", ["", "   ", None, 7])
def test_blank_input_is_rejected(bad):
    with pytest.raises(ValueError, match="non-empty string"):
        reflect(bad, build=_builder(states=[]))


def test_a_budget_below_one_is_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        reflect("x", budget=0, build=_builder(states=[]))


# --------------------------------------------------------------------------
# one real round trip
# --------------------------------------------------------------------------

@pytest.mark.live
def test_the_langgraph_agent_finds_anger_on_the_compound_query():
    """Stage 3's accept criterion — the same one Stage 2 had to pass."""
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    result = reflect("i'm grieving my dad and angry at my family")

    assert result.searches >= 2, "the agent didn't decompose the query"
    assert not result.stopped_early
    joined = " ".join(q["text"] for q in result.quotes).lower()
    assert "anger" in joined or "resentment" in joined
    assert result.reflection
    assert "<invoke" not in result.reflection

"""The same agent, spelled in LangGraph.

Stage 3 of the agent plan. Same model, same tool, same system prompt as
`agent.py` — the constants are imported from it rather than copied, so the only
thing that differs between the two runs is the machinery. A gap in the eval
scores means one of them has a bug, not that a framework is smarter.

What the framework gives you, and what it costs:

| hand-rolled (`agent.py`)              | LangGraph (here)                     |
| ------------------------------------- | ------------------------------------ |
| `while` loop you wrote                | `StateGraph` + edges                 |
| `if stop_reason == "tool_use"`        | `should_continue` conditional edge   |
| build `tool_result` blocks by hand    | `ToolNode`                           |
| append to a `messages` list           | `add_messages` reducer on the state  |
| `for _ in range(LOOP_BUDGET)`         | `recursion_limit` + `GraphRecursionError` |

The graph is written out explicitly rather than with `create_react_agent`, which
would collapse all of it into one call and hide the exact part worth seeing: the
conditional edge below *is* the `stop_reason` branch from `agent.py`.

The one thing the framework genuinely costs is visible in `_Collector`. The
hand-rolled loop had the structured search results in hand; `ToolNode` only
passes the rendered string along to the model, so getting the quotes back out
means threading a recorder through a closure.
"""
from dataclasses import dataclass, field

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.rag.agent import (
    LOOP_BUDGET,
    MAX_TOKENS,
    MODEL,
    OUT_OF_BUDGET,
    SYSTEM_PROMPT,
    AgentResult,
    _merge,
)
from app.rag.tools import DEFAULT_K, SEARCH_QUOTES_TOOL, dispatch


@dataclass
class _Collector:
    """Catches the structured results on their way past `ToolNode`.

    One per run: it holds mutable state for a single `reflect()` call, which is
    why the graph is built per run rather than once at import.
    """

    collected: dict[str, dict] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)

    def record(self, query: str, outcome) -> None:
        _merge(self.collected, outcome.quotes)
        step = {
            "step": len(self.trace) + 1,
            "tool": SEARCH_QUOTES_TOOL["name"],
            "query": query,
            "returned": len(outcome.quotes),
            "top_score": round(outcome.quotes[0]["score"], 3) if outcome.quotes else None,
        }
        if outcome.is_error:
            step["error"] = outcome.content
        self.trace.append(step)

    @property
    def quotes(self) -> list[dict]:
        return sorted(self.collected.values(), key=lambda q: q["score"], reverse=True)


def _model(bind: bool = True, tools=None):
    """The chat model, configured to match `agent.py` exactly."""
    llm = ChatAnthropic(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        # Same reasoning budget as the hand-rolled loop. The judging step —
        # "is this facet actually covered?" — depends on it.
        thinking={"type": "adaptive"},
    )
    return llm.bind_tools(tools) if bind else llm


def build_graph(collector: _Collector):
    """Wire the agent/tools cycle explicitly.

        START ──▶ agent ──should_continue──▶ tools ──┐
                    ▲                                │
                    └────────────────────────────────┘
                    │
                    └─(no tool calls)──▶ END
    """

    @tool(description=SEARCH_QUOTES_TOOL["description"])
    def search_quotes(query: str, k: int = DEFAULT_K) -> str:
        # The decorator infers the schema from this signature: `query` required,
        # `k` optional with a default — the same shape as the hand-written
        # SEARCH_QUOTES_TOOL. The description is imported, not retyped, so the
        # two implementations cannot drift apart.
        outcome = dispatch(SEARCH_QUOTES_TOOL["name"], {"query": query, "k": k})
        collector.record(query, outcome)
        # ToolNode wraps this string in a ToolMessage; the structured quotes
        # only survive because the collector caught them above.
        return outcome.content

    model = _model(tools=[search_quotes])

    def agent_node(state: MessagesState) -> dict:
        # `add_messages` appends this to the state — the framework's version of
        # `messages.append(...)`, including keeping thinking blocks intact.
        return {"messages": [model.invoke(state["messages"])]}

    def should_continue(state: MessagesState) -> str:
        """The `stop_reason == "tool_use"` branch, as a graph edge."""
        return "tools" if state["messages"][-1].tool_calls else END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode([search_quotes]))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def _text(message) -> str:
    """Pull the prose out of a message.

    With thinking on, `content` is a list of blocks rather than a string, and
    the thinking blocks must not end up in the reflection.
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts = [
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def _count_api_calls(messages) -> int:
    return sum(1 for m in messages if m.__class__.__name__ == "AIMessage")


def reflect(text: str, *, budget: int = LOOP_BUDGET, build=build_graph) -> AgentResult:
    """Same signature and same return type as `agent.reflect`.

    `build` is the graph factory, injectable so tests can supply a fake graph
    wired to the same collector the real one would use.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    if budget < 1:
        raise ValueError("budget must be at least 1")

    collector = _Collector()
    graph = build(collector)

    messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(text.strip())]
    seen = list(messages)
    stopped_early = False

    # The framework's spelling of `for _ in range(LOOP_BUDGET)`. One agent turn
    # plus its tools turn is two graph steps, so N model calls with their
    # searches actually executed is 2N steps. Using 2N-1 looks right and is not:
    # it cuts the graph off between the agent node and the tools node, so the
    # last round of searches never runs and the salvage call has no quotes.
    config = {"recursion_limit": 2 * budget}

    try:
        # Streamed rather than invoked so the partial conversation survives a
        # budget overrun — `invoke()` raises and takes the state with it.
        for state in graph.stream({"messages": messages}, config=config, stream_mode="values"):
            seen = state["messages"]
    except GraphRecursionError:
        stopped_early = True

    reflection = ""
    api_calls = _count_api_calls(seen)

    if not stopped_early and seen:
        reflection = _text(seen[-1])

    if stopped_early or not reflection:
        reflection, extra = _force_finish(seen)
        api_calls += extra
        stopped_early = True

    return AgentResult(
        reflection=reflection,
        quotes=collector.quotes,
        trace=collector.trace,
        api_calls=api_calls,
        stopped_early=stopped_early,
    )


def _drop_unanswered_tool_calls(messages) -> list:
    """Trim a trailing assistant turn whose tool calls were never answered.

    A budget overrun can stop the graph between the agent node and the tools
    node, leaving an AIMessage with `tool_calls` and no ToolMessage after it.
    The API rejects that conversation outright, so the salvage call would fail
    and silently return an empty reflection.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    trimmed = list(messages)
    while trimmed:
        calls = getattr(trimmed[-1], "tool_calls", None)
        if calls and any(c["id"] not in answered for c in calls):
            trimmed.pop()
        else:
            break
    return trimmed


def _force_finish(messages) -> tuple[str, int]:
    """Same salvage as `agent._force_finish`, for the same measured reasons.

    An unbound model has no tools to call, and the nudge is what makes it answer
    instead of returning an empty turn.
    """
    try:
        response = _model(bind=False).invoke(
            _drop_unanswered_tool_calls(messages) + [HumanMessage(OUT_OF_BUDGET)]
        )
        return _text(response), 1
    except Exception:
        # Already over budget and now failing — surface the quotes, not an
        # exception.
        return "", 1

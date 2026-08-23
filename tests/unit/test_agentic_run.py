from research_assistant.llm.base import LLMResponse, LLMUsage, ToolCall
from research_assistant.models import SearchResult
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.agentic.run import MAX_ROUNDS, run_research_loop, write_brief


class ScriptedLLMClient:
    """Fake LLMClient that returns a fixed sequence of responses."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools=None, max_tokens=4096):
        self.calls.append(
            {
                "system": system,
                "messages": list(messages),
                "tools": tools,
                "max_tokens": max_tokens,
            }
        )
        return self._responses.pop(0)


class FakeSearchTool:
    name = "web_search"

    def __init__(self, results_by_query: dict[str, list[SearchResult]]) -> None:
        self._results_by_query = results_by_query
        self.last_results: list[SearchResult] = []
        self.queries: list[str] = []

    def run(self, query: str) -> str:
        self.queries.append(query)
        self.last_results = self._results_by_query.get(query, [])
        return f"results for {query}"

    def as_tooldef(self):
        from research_assistant.llm.base import ToolDef

        return ToolDef(name=self.name, description="fake search", input_schema={})


def _usage() -> LLMUsage:
    return LLMUsage(input_tokens=10, output_tokens=5)


def _search_result(url: str, title: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content="content")


def _tool_use_response(call_id: str, query: str) -> LLMResponse:
    return LLMResponse(
        text=None,
        tool_calls=[ToolCall(id=call_id, name="web_search", input={"query": query})],
        stop_reason="tool_use",
        usage=_usage(),
    )


def _end_turn_response(text: str = "done researching") -> LLMResponse:
    return LLMResponse(text=text, tool_calls=[], stop_reason="end_turn", usage=_usage())


def test_run_research_loop_runs_search_then_stops_on_end_turn():
    llm = ScriptedLLMClient([_tool_use_response("call-1", "capital of France"), _end_turn_response()])
    search_tool = FakeSearchTool({"capital of France": [_search_result("https://a.com", "A")]})
    recorder = RunRecorder(variant="agentic", topic="France")

    results = run_research_loop("France", llm, search_tool, recorder)

    assert results == [_search_result("https://a.com", "A")]
    assert search_tool.queries == ["capital of France"]
    assert len(llm.calls) == 2


def test_run_research_loop_accumulates_results_across_multiple_rounds():
    llm = ScriptedLLMClient(
        [
            _tool_use_response("call-1", "query one"),
            _tool_use_response("call-2", "query two"),
            _end_turn_response(),
        ]
    )
    search_tool = FakeSearchTool(
        {
            "query one": [_search_result("https://a.com", "A")],
            "query two": [_search_result("https://b.com", "B")],
        }
    )
    recorder = RunRecorder(variant="agentic", topic="t")

    results = run_research_loop("t", llm, search_tool, recorder)

    assert [r.url for r in results] == ["https://a.com", "https://b.com"]
    assert search_tool.queries == ["query one", "query two"]


def test_run_research_loop_handles_multiple_tool_calls_in_one_round():
    response = LLMResponse(
        text=None,
        tool_calls=[
            ToolCall(id="call-1", name="web_search", input={"query": "q1"}),
            ToolCall(id="call-2", name="web_search", input={"query": "q2"}),
        ],
        stop_reason="tool_use",
        usage=_usage(),
    )
    llm = ScriptedLLMClient([response, _end_turn_response()])
    search_tool = FakeSearchTool(
        {"q1": [_search_result("https://a.com", "A")], "q2": [_search_result("https://b.com", "B")]}
    )
    recorder = RunRecorder(variant="agentic", topic="t")

    results = run_research_loop("t", llm, search_tool, recorder)

    assert [r.url for r in results] == ["https://a.com", "https://b.com"]
    assert search_tool.queries == ["q1", "q2"]


def test_run_research_loop_stops_at_max_rounds_and_still_returns_results():
    responses = [_tool_use_response(f"call-{i}", f"query {i}") for i in range(MAX_ROUNDS)]
    llm = ScriptedLLMClient(responses)
    search_tool = FakeSearchTool(
        {f"query {i}": [_search_result(f"https://{i}.com", str(i))] for i in range(MAX_ROUNDS)}
    )
    recorder = RunRecorder(variant="agentic", topic="t")

    results = run_research_loop("t", llm, search_tool, recorder)

    assert len(results) == MAX_ROUNDS
    assert len(llm.calls) == MAX_ROUNDS


def test_run_research_loop_records_llm_and_tool_calls_on_recorder():
    llm = ScriptedLLMClient([_tool_use_response("call-1", "q"), _end_turn_response()])
    search_tool = FakeSearchTool({"q": [_search_result("https://a.com", "A")]})
    recorder = RunRecorder(variant="agentic", topic="t")

    run_research_loop("t", llm, search_tool, recorder)
    trace = recorder.finalize()

    assert trace.llm_calls == 2
    assert trace.search_calls == 1
    assert trace.input_tokens == 20
    assert trace.output_tokens == 10


def test_write_brief_produces_cited_markdown_with_sources_section():
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                text="Paris is the capital of France [1].",
                tool_calls=[],
                stop_reason="end_turn",
                usage=_usage(),
            )
        ]
    )
    results = [_search_result("https://a.com", "A")]
    recorder = RunRecorder(variant="agentic", topic="t")

    brief = write_brief("France", results, llm, recorder)

    assert "Paris is the capital of France [1]." in brief.markdown
    assert "## Sources" in brief.markdown
    assert "[A](https://a.com)" in brief.markdown
    assert brief.sources[0].url == "https://a.com"
    assert len(llm.calls) == 1
    assert llm.calls[0]["max_tokens"] == 2048


def test_write_brief_records_llm_call_on_recorder():
    llm = ScriptedLLMClient([_end_turn_response("brief text")])
    recorder = RunRecorder(variant="agentic", topic="t")

    write_brief("t", [], llm, recorder)

    assert recorder.finalize().llm_calls == 1

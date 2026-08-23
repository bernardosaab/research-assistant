from research_assistant.llm.base import LLMResponse, LLMUsage
from research_assistant.models import ResearchPlan, SearchResult, SubQuestion, Triple
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.graphrag.run import build_graph


class ScriptedLLMClient:
    """Fake LLMClient that returns a fixed sequence of responses."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools=None, max_tokens=4096):
        self.calls.append(
            {"system": system, "messages": list(messages), "tools": tools, "max_tokens": max_tokens}
        )
        return self._responses.pop(0)


class FakeGraphStore:
    def __init__(self) -> None:
        self.cleared = False
        self.added: list[tuple[str, str, str, str]] = []

    def clear(self) -> None:
        self.cleared = True

    def add_triple(self, subject: str, relation: str, object: str, source_url: str) -> None:
        self.added.append((subject, relation, object, source_url))

    def get_all_facts(self) -> list[Triple]:
        return [
            Triple(subject=s, relation=r, object=o, source_url=u)
            for s, r, o, u in self.added
        ]

    def close(self) -> None:
        pass


def _usage() -> LLMUsage:
    return LLMUsage(input_tokens=10, output_tokens=5)


def _search_result(url: str, title: str, content: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content=content)


def test_build_graph_clears_then_extracts_per_subquestion_and_writes_all_triples():
    sq1 = SubQuestion(id="1", text="q1", search_results=[_search_result("https://a.com", "A", "c")])
    sq2 = SubQuestion(id="2", text="q2", search_results=[_search_result("https://b.com", "B", "c")])
    plan = ResearchPlan(topic="t", sub_questions=[sq1, sq2])

    response1 = LLMResponse(
        text='[{"subject":"X","relation":"r1","object":"Y","source_url":"https://a.com"}]',
        tool_calls=[], stop_reason="end_turn", usage=_usage(),
    )
    response2 = LLMResponse(
        text='[{"subject":"Y","relation":"r2","object":"Z","source_url":"https://b.com"}]',
        tool_calls=[], stop_reason="end_turn", usage=_usage(),
    )
    llm = ScriptedLLMClient([response1, response2])
    graph_store = FakeGraphStore()
    recorder = RunRecorder(variant="graphrag", topic="t")

    facts = build_graph(plan, llm, graph_store, recorder)

    assert graph_store.cleared is True
    assert graph_store.added == [
        ("X", "r1", "Y", "https://a.com"),
        ("Y", "r2", "Z", "https://b.com"),
    ]
    assert len(facts) == 2
    assert recorder.finalize().llm_calls == 2


def test_build_graph_no_sub_questions_still_clears_and_returns_empty():
    plan = ResearchPlan(topic="t", sub_questions=[])
    llm = ScriptedLLMClient([])
    graph_store = FakeGraphStore()
    recorder = RunRecorder(variant="graphrag", topic="t")

    facts = build_graph(plan, llm, graph_store, recorder)

    assert graph_store.cleared is True
    assert facts == []
    assert graph_store.added == []

from research_assistant.llm.base import LLMResponse, LLMUsage
from research_assistant.models import SearchResult, SubQuestion, Triple
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.graphrag.extraction import extract_triples


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


def _usage() -> LLMUsage:
    return LLMUsage(input_tokens=10, output_tokens=5)


def _search_result(url: str, title: str, content: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content=content)


def _sub_question(results: list[SearchResult]) -> SubQuestion:
    return SubQuestion(id="1", text="Where was Napoleon born?", search_results=results)


def test_extract_triples_parses_valid_json_array():
    response_text = (
        '[{"subject": "Napoleon Bonaparte", "relation": "born_in", '
        '"object": "Corsica", "source_url": "https://a.com"}]'
    )
    llm = ScriptedLLMClient(
        [LLMResponse(text=response_text, tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([_search_result("https://a.com", "A", "Napoleon was born in Corsica.")])
    recorder = RunRecorder(variant="graphrag", topic="t")

    triples = extract_triples(sub_question, llm, recorder)

    assert triples == [
        Triple(subject="Napoleon Bonaparte", relation="born_in", object="Corsica", source_url="https://a.com")
    ]
    assert recorder.finalize().llm_calls == 1


def test_extract_triples_drops_entries_missing_required_keys():
    response_text = '[{"subject": "A", "relation": "rel"}]'
    llm = ScriptedLLMClient(
        [LLMResponse(text=response_text, tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([])
    recorder = RunRecorder(variant="graphrag", topic="t")

    assert extract_triples(sub_question, llm, recorder) == []


def test_extract_triples_no_results_still_sends_placeholder_text():
    llm = ScriptedLLMClient(
        [LLMResponse(text="[]", tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([])
    recorder = RunRecorder(variant="graphrag", topic="t")

    triples = extract_triples(sub_question, llm, recorder)

    assert triples == []
    assert "No search results found." in llm.calls[0]["messages"][0].text


def test_extract_triples_empty_array_response():
    llm = ScriptedLLMClient(
        [LLMResponse(text="[]", tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([_search_result("https://a.com", "A", "content")])
    recorder = RunRecorder(variant="graphrag", topic="t")

    assert extract_triples(sub_question, llm, recorder) == []

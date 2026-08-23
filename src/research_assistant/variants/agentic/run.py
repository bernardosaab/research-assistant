from research_assistant.config import get_settings
from research_assistant.llm.anthropic_client import AnthropicLLMClient
from research_assistant.llm.base import LLMClient, LLMMessage, ToolResult
from research_assistant.models import Brief, SearchResult
from research_assistant.tools.search_tool import TavilySearchTool
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.pipeline.run import BRIEF_SYSTEM_PROMPT
from research_assistant.writing.brief import assemble_brief
from research_assistant.writing.citations import build_source_list, format_sources_for_prompt

MAX_ROUNDS = 8

RESEARCH_SYSTEM_PROMPT = (
    "You are a research assistant investigating a topic using web search. "
    "Search as many times as needed to build a well-rounded understanding "
    "— covering the topic from multiple angles — then stop calling tools "
    "once you have enough to write a short brief."
)


def run_research_loop(
    topic: str, llm: LLMClient, search_tool: TavilySearchTool, recorder: RunRecorder
) -> list[SearchResult]:
    history: list[LLMMessage] = [LLMMessage(role="user", text=f"Topic: {topic}")]
    all_results: list[SearchResult] = []

    for _ in range(MAX_ROUNDS):
        response = llm.complete(
            system=RESEARCH_SYSTEM_PROMPT,
            messages=history,
            tools=[search_tool.as_tooldef()],
        )
        recorder.record_llm_call(response.usage)

        if response.stop_reason != "tool_use":
            break

        history.append(
            LLMMessage(role="assistant", text=response.text, tool_calls=response.tool_calls)
        )

        tool_results = []
        for call in response.tool_calls:
            result_text = search_tool.run(call.input["query"])
            recorder.record_tool_call(search_tool.name)
            all_results.extend(search_tool.last_results)
            tool_results.append(ToolResult(tool_call_id=call.id, content=result_text))
        history.append(LLMMessage(role="user", tool_results=tool_results))

    return all_results


def write_brief(
    topic: str, results: list[SearchResult], llm: LLMClient, recorder: RunRecorder
) -> Brief:
    sources = build_source_list(results)
    sources_text = format_sources_for_prompt(sources)
    response = llm.complete(
        system=BRIEF_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", text=f"Topic: {topic}\n\nSources:\n{sources_text}")],
        max_tokens=2048,
    )
    recorder.record_llm_call(response.usage)
    return assemble_brief(topic, response.text or "", sources)


def run(topic: str, recorder: RunRecorder | None = None) -> Brief:
    settings = get_settings()
    llm = AnthropicLLMClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    search_tool = TavilySearchTool(api_key=settings.tavily_api_key)
    recorder = recorder or RunRecorder(variant="agentic", topic=topic)

    results = run_research_loop(topic, llm, search_tool, recorder)
    return write_brief(topic, results, llm, recorder)

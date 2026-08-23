import json
import re
import uuid

from research_assistant.config import get_settings
from research_assistant.llm.anthropic_client import AnthropicLLMClient
from research_assistant.llm.base import LLMClient, LLMMessage
from research_assistant.models import Brief, ResearchPlan, SubQuestion
from research_assistant.tools.search_tool import TavilySearchTool
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.writing.brief import assemble_brief
from research_assistant.writing.citations import (
    build_source_list,
    format_sources_for_prompt,
)

PLAN_SYSTEM_PROMPT = (
    "You are a research planner. Given a topic, break it down into 3 to 5 "
    "focused sub-questions that, together, would let someone write a short, "
    "well-rounded research brief on the topic. Respond with ONLY a JSON "
    "array of strings, no other text."
)

FINDINGS_SYSTEM_PROMPT = (
    "You are a research assistant. Given a sub-question and a list of web "
    "search results, write a concise 2-4 sentence summary of what the "
    "results reveal about the sub-question. Be factual and specific. Do not "
    "include citation markers or URLs in this summary."
)

BRIEF_SYSTEM_PROMPT = (
    "You are a research assistant writing a short brief. You will be given a "
    "topic, a set of sub-questions with their findings, and a numbered list "
    "of sources. Write a well-organized markdown brief (a few short "
    "paragraphs or bullet sections, no more than about one page) that "
    "synthesizes the findings into a coherent answer to the overall topic. "
    "Cite claims using the exact bracketed numbers from the source list, "
    "e.g. [1] or [2][3], placed right after the claim they support. Do not "
    "include a 'Sources' section yourself — it will be appended separately. "
    "Do not invent source numbers beyond what was given."
)


def run(topic: str, recorder: RunRecorder | None = None) -> Brief:
    settings = get_settings()
    llm = AnthropicLLMClient(
        api_key=settings.anthropic_api_key, model=settings.anthropic_model
    )
    search_tool = TavilySearchTool(api_key=settings.tavily_api_key)
    recorder = recorder or RunRecorder(variant="pipeline", topic=topic)

    plan = generate_plan(topic, llm, recorder)
    plan = run_searches(plan, search_tool, recorder)
    plan = extract_findings(plan, llm, recorder)
    return write_brief(plan, llm, recorder)


def generate_plan(topic: str, llm: LLMClient, recorder: RunRecorder) -> ResearchPlan:
    response = llm.complete(
        system=PLAN_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", text=f"Topic: {topic}")],
    )
    recorder.record_llm_call(response.usage)
    questions = _parse_json_list(response.text or "[]")
    sub_questions = [SubQuestion(id=str(uuid.uuid4())[:8], text=q) for q in questions]
    return ResearchPlan(topic=topic, sub_questions=sub_questions)


def run_searches(
    plan: ResearchPlan, search_tool: TavilySearchTool, recorder: RunRecorder
) -> ResearchPlan:
    for sub_question in plan.sub_questions:
        search_tool.run(sub_question.text)
        recorder.record_tool_call(search_tool.name)
        sub_question.search_results = search_tool.last_results
        sub_question.status = "in_progress"
    return plan


def extract_findings(
    plan: ResearchPlan, llm: LLMClient, recorder: RunRecorder
) -> ResearchPlan:
    for sub_question in plan.sub_questions:
        results_text = (
            "\n".join(
                f"- {r.title} ({r.url}): {r.content}"
                for r in sub_question.search_results
            )
            or "No search results found."
        )
        response = llm.complete(
            system=FINDINGS_SYSTEM_PROMPT,
            messages=[
                LLMMessage(
                    role="user",
                    text=(
                        f"Sub-question: {sub_question.text}\n\n"
                        f"Search results:\n{results_text}"
                    ),
                )
            ],
        )
        recorder.record_llm_call(response.usage)
        sub_question.findings = response.text or ""
        sub_question.status = "done"
    return plan


def write_brief(plan: ResearchPlan, llm: LLMClient, recorder: RunRecorder) -> Brief:
    all_results = [r for sq in plan.sub_questions for r in sq.search_results]
    sources = build_source_list(all_results)
    findings_text = "\n\n".join(
        f"Sub-question: {sq.text}\nFindings: {sq.findings}"
        for sq in plan.sub_questions
    )
    sources_text = format_sources_for_prompt(sources)
    response = llm.complete(
        system=BRIEF_SYSTEM_PROMPT,
        messages=[
            LLMMessage(
                role="user",
                text=(
                    f"Topic: {plan.topic}\n\n"
                    f"Findings:\n{findings_text}\n\n"
                    f"Sources:\n{sources_text}"
                ),
            )
        ],
        max_tokens=2048,
    )
    recorder.record_llm_call(response.usage)
    return assemble_brief(plan.topic, response.text or "", sources)


def _parse_json_list(text: str) -> list[str]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data if isinstance(item, str)]

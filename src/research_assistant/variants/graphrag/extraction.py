import json
import re

from pydantic import ValidationError

from research_assistant.llm.base import LLMClient, LLMMessage
from research_assistant.models import SubQuestion, Triple
from research_assistant.tracing.recorder import RunRecorder

EXTRACTION_SYSTEM_PROMPT = (
    "You are extracting a knowledge graph from web search results. Given a "
    "list of search results, each shown as \"- title (url): content\", "
    "identify the key entities and relationships between them. Respond "
    "with ONLY a JSON array of objects, each with exactly these keys: "
    "\"subject\", \"relation\", \"object\", \"source_url\". Use concise "
    "entity names (e.g. \"Napoleon Bonaparte\", not \"the French emperor "
    "who...\"), short relation labels (e.g. \"born_in\", \"defeated_at\"), "
    "and set \"source_url\" to the exact url of the result the fact came "
    "from. Extract only relationships explicitly stated or clearly implied "
    "by the text. If no clear relationships are found, return an empty "
    "array."
)


def extract_triples(
    sub_question: SubQuestion, llm: LLMClient, recorder: RunRecorder
) -> list[Triple]:
    results_text = (
        "\n".join(
            f"- {r.title} ({r.url}): {r.content}" for r in sub_question.search_results
        )
        or "No search results found."
    )
    response = llm.complete(
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", text=f"Search results:\n{results_text}")],
    )
    recorder.record_llm_call(response.usage)
    return _parse_triples(response.text or "[]")


def _parse_triples(text: str) -> list[Triple]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    triples: list[Triple] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            triples.append(Triple(**item))
        except ValidationError:
            continue
    return triples

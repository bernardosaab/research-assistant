from research_assistant.config import get_settings
from research_assistant.llm.anthropic_client import AnthropicLLMClient
from research_assistant.llm.base import LLMClient, LLMMessage
from research_assistant.models import Brief, ResearchPlan, SearchResult, Source, Triple
from research_assistant.tools.search_tool import TavilySearchTool
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.graphrag.extraction import extract_triples
from research_assistant.variants.graphrag.graph_store import Neo4jGraphStore
from research_assistant.variants.pipeline.run import generate_plan, run_searches
from research_assistant.writing.brief import assemble_brief
from research_assistant.writing.citations import (
    build_source_list,
    format_sources_for_prompt,
)


def build_graph(
    plan: ResearchPlan, llm: LLMClient, graph_store: Neo4jGraphStore, recorder: RunRecorder
) -> list[Triple]:
    graph_store.clear()
    for sub_question in plan.sub_questions:
        for triple in extract_triples(sub_question, llm, recorder):
            graph_store.add_triple(triple.subject, triple.relation, triple.object, triple.source_url)
    return graph_store.get_all_facts()


BRIEF_SYSTEM_PROMPT = (
    "You are a research assistant writing a short brief. You will be given "
    "a topic, a set of facts extracted as a knowledge graph (in the form "
    "'Subject -relation-> Object [n]', where [n] is a citation number), and "
    "a numbered list of sources. Write a well-organized markdown brief (a "
    "few short paragraphs or bullet sections, no more than about one page) "
    "that synthesizes these facts into a coherent answer to the topic, "
    "including connections between entities where relevant. Cite claims "
    "using the exact bracketed numbers from the source list, e.g. [1] or "
    "[2][3], placed right after the claim they support. Do not include a "
    "'Sources' section yourself — it will be appended separately. Do not "
    "invent source numbers beyond what was given."
)


def format_facts_for_prompt(facts: list[Triple], sources: list[Source]) -> str:
    if not facts:
        return "No facts extracted."
    url_to_id = {s.url: s.id for s in sources}
    lines = []
    for fact in facts:
        citation_id = url_to_id.get(fact.source_url)
        marker = f" [{citation_id}]" if citation_id is not None else ""
        lines.append(f"{fact.subject} -{fact.relation}-> {fact.object}{marker}")
    return "\n".join(lines)


def write_brief(
    topic: str, facts: list[Triple], results: list[SearchResult], llm: LLMClient, recorder: RunRecorder
) -> Brief:
    sources = build_source_list(results)
    response = llm.complete(
        system=BRIEF_SYSTEM_PROMPT,
        messages=[
            LLMMessage(
                role="user",
                text=(
                    f"Topic: {topic}\n\n"
                    f"Facts:\n{format_facts_for_prompt(facts, sources)}\n\n"
                    f"Sources:\n{format_sources_for_prompt(sources)}"
                ),
            )
        ],
        max_tokens=2048,
    )
    recorder.record_llm_call(response.usage)
    return assemble_brief(topic, response.text or "", sources)


def run(topic: str, recorder: RunRecorder | None = None) -> Brief:
    settings = get_settings()
    if not (settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password):
        raise RuntimeError(
            "GraphRAG variant requires NEO4J_URI, NEO4J_USER, and "
            "NEO4J_PASSWORD in .env. Run `docker compose up -d` to start a "
            "local Neo4j instance, then set these to its connection details."
        )
    llm = AnthropicLLMClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    search_tool = TavilySearchTool(api_key=settings.tavily_api_key)
    recorder = recorder or RunRecorder(variant="graphrag", topic=topic)

    plan = generate_plan(topic, llm, recorder)
    plan = run_searches(plan, search_tool, recorder)

    graph_store = Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    try:
        facts = build_graph(plan, llm, graph_store, recorder)
    finally:
        graph_store.close()

    all_results = [r for sq in plan.sub_questions for r in sq.search_results]
    return write_brief(topic, facts, all_results, llm, recorder)

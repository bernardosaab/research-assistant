from research_assistant.llm.base import LLMClient
from research_assistant.models import ResearchPlan, Triple
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.graphrag.extraction import extract_triples
from research_assistant.variants.graphrag.graph_store import Neo4jGraphStore


def build_graph(
    plan: ResearchPlan, llm: LLMClient, graph_store: Neo4jGraphStore, recorder: RunRecorder
) -> list[Triple]:
    graph_store.clear()
    for sub_question in plan.sub_questions:
        for triple in extract_triples(sub_question, llm, recorder):
            graph_store.add_triple(triple.subject, triple.relation, triple.object, triple.source_url)
    return graph_store.get_all_facts()

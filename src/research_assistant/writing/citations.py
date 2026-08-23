from research_assistant.models import ResearchPlan, Source


def build_source_list(plan: ResearchPlan) -> list[Source]:
    """Dedupe search results by URL across all sub-questions, in order of
    first appearance, assigning each a stable citation number."""
    seen: dict[str, Source] = {}
    for sub_question in plan.sub_questions:
        for result in sub_question.search_results:
            if result.url not in seen:
                seen[result.url] = Source(
                    id=len(seen) + 1, url=result.url, title=result.title
                )
    return list(seen.values())


def format_sources_for_prompt(sources: list[Source]) -> str:
    """Render the numbered source list to hand to the LLM so it cites using
    the exact numbers assigned here, rather than inventing its own."""
    if not sources:
        return "No sources available."
    return "\n".join(f"[{s.id}] {s.title} — {s.url}" for s in sources)


def render_sources_section(sources: list[Source]) -> str:
    if not sources:
        return ""
    lines = ["## Sources"]
    lines.extend(f"{s.id}. [{s.title}]({s.url})" for s in sources)
    return "\n".join(lines)

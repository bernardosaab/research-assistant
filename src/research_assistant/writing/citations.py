from research_assistant.models import SearchResult, Source


def build_source_list(results: list[SearchResult]) -> list[Source]:
    """Dedupe search results by URL, in order of first appearance, assigning
    each a stable citation number."""
    seen: dict[str, Source] = {}
    for result in results:
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

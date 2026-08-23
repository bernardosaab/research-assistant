from research_assistant.models import Brief, Source
from research_assistant.writing.citations import render_sources_section


def assemble_brief(topic: str, body_markdown: str, sources: list[Source]) -> Brief:
    sources_section = render_sources_section(sources)
    full_markdown = body_markdown.strip()
    if sources_section:
        full_markdown = f"{full_markdown}\n\n{sources_section}"
    return Brief(topic=topic, markdown=full_markdown, sources=sources)

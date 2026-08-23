import pytest

from research_assistant.config import get_settings
from research_assistant.variants.graphrag.run import run

pytestmark = pytest.mark.live


def _settings_available() -> bool:
    try:
        settings = get_settings()
    except Exception:  # noqa: BLE001 - any config error means "not configured"
        return False
    return bool(settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password)


@pytest.mark.skipif(
    not _settings_available(),
    reason="ANTHROPIC_API_KEY / TAVILY_API_KEY / NEO4J_* not configured (.env), "
    "or `docker compose up -d` hasn't been run",
)
def test_graphrag_produces_cited_brief_for_simple_topic():
    brief = run("What is the capital of France and why?")

    assert brief.markdown.strip() != ""
    assert "## Sources" in brief.markdown
    assert len(brief.sources) > 0

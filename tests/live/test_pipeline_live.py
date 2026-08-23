import pytest

from research_assistant.config import get_settings
from research_assistant.variants.pipeline.run import run

pytestmark = pytest.mark.live


def _settings_available() -> bool:
    try:
        get_settings()
    except Exception:  # noqa: BLE001 - any config error means "not configured"
        return False
    return True


@pytest.mark.skipif(
    not _settings_available(),
    reason="ANTHROPIC_API_KEY / TAVILY_API_KEY not configured (.env)",
)
def test_pipeline_produces_cited_brief_for_simple_topic():
    brief = run("What is the capital of France and why?")

    assert brief.markdown.strip() != ""
    assert "## Sources" in brief.markdown
    assert "[1]" in brief.markdown
    assert len(brief.sources) > 0

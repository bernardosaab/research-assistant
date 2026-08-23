import pytest
from pydantic import ValidationError

from research_assistant.models import (
    Brief,
    ResearchPlan,
    SearchResult,
    Source,
    SubQuestion,
    Triple,
)


def test_sub_question_defaults():
    sq = SubQuestion(id="1", text="What is X?")
    assert sq.status == "pending"
    assert sq.findings is None
    assert sq.search_results == []


def test_sub_question_rejects_invalid_status():
    with pytest.raises(ValidationError):
        SubQuestion(id="1", text="What is X?", status="not-a-status")


def test_research_plan_holds_sub_questions():
    plan = ResearchPlan(topic="Topic", sub_questions=[SubQuestion(id="1", text="q1")])
    assert plan.topic == "Topic"
    assert len(plan.sub_questions) == 1


def test_search_result_optional_fields_default_none():
    result = SearchResult(query="q", url="https://a.com", title="A", content="c")
    assert result.score is None
    assert result.raw_content is None


def test_brief_requires_markdown_and_sources():
    brief = Brief(
        topic="t",
        markdown="# Brief",
        sources=[Source(id=1, url="https://a.com", title="A")],
    )
    assert brief.markdown == "# Brief"
    assert brief.sources[0].id == 1


def test_brief_missing_field_raises():
    with pytest.raises(ValidationError):
        Brief(topic="t", sources=[])


def test_triple_holds_subject_relation_object_source():
    triple = Triple(subject="Napoleon", relation="born_in", object="Corsica", source_url="https://a.com")
    assert triple.subject == "Napoleon"
    assert triple.relation == "born_in"
    assert triple.object == "Corsica"
    assert triple.source_url == "https://a.com"


def test_triple_missing_field_raises():
    with pytest.raises(ValidationError):
        Triple(subject="Napoleon", relation="born_in", object="Corsica")

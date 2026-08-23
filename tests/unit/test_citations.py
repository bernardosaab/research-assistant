from research_assistant.models import ResearchPlan, SearchResult, SubQuestion
from research_assistant.writing.citations import (
    build_source_list,
    format_sources_for_prompt,
    render_sources_section,
)


def _search_result(url: str, title: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content="some content")


def test_build_source_list_assigns_sequential_ids_in_order_of_appearance():
    plan = ResearchPlan(
        topic="t",
        sub_questions=[
            SubQuestion(
                id="1",
                text="sq1",
                search_results=[
                    _search_result("https://a.com", "A"),
                    _search_result("https://b.com", "B"),
                ],
            ),
        ],
    )
    sources = build_source_list(plan)
    assert [(s.id, s.url) for s in sources] == [
        (1, "https://a.com"),
        (2, "https://b.com"),
    ]


def test_build_source_list_dedupes_repeated_urls_across_subquestions():
    plan = ResearchPlan(
        topic="t",
        sub_questions=[
            SubQuestion(
                id="1", text="sq1", search_results=[_search_result("https://a.com", "A")]
            ),
            SubQuestion(
                id="2",
                text="sq2",
                search_results=[
                    _search_result("https://a.com", "A"),
                    _search_result("https://c.com", "C"),
                ],
            ),
        ],
    )
    sources = build_source_list(plan)
    assert [s.url for s in sources] == ["https://a.com", "https://c.com"]


def test_build_source_list_empty_plan_returns_empty_list():
    plan = ResearchPlan(topic="t", sub_questions=[])
    assert build_source_list(plan) == []


def test_format_sources_for_prompt_no_sources():
    assert format_sources_for_prompt([]) == "No sources available."


def test_format_sources_for_prompt_lists_each_source_with_bracketed_id():
    plan = ResearchPlan(
        topic="t",
        sub_questions=[
            SubQuestion(
                id="1", text="sq1", search_results=[_search_result("https://a.com", "A")]
            ),
        ],
    )
    sources = build_source_list(plan)
    assert format_sources_for_prompt(sources) == "[1] A — https://a.com"


def test_render_sources_section_no_sources_returns_empty_string():
    assert render_sources_section([]) == ""


def test_render_sources_section_renders_markdown_list():
    plan = ResearchPlan(
        topic="t",
        sub_questions=[
            SubQuestion(
                id="1",
                text="sq1",
                search_results=[
                    _search_result("https://a.com", "A"),
                    _search_result("https://b.com", "B"),
                ],
            ),
        ],
    )
    sources = build_source_list(plan)
    rendered = render_sources_section(sources)
    assert rendered == "## Sources\n1. [A](https://a.com)\n2. [B](https://b.com)"

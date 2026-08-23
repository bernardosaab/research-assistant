from unittest.mock import MagicMock

import pytest

from research_assistant.tools.search_tool import TavilySearchTool


@pytest.fixture
def fake_tavily_client(monkeypatch):
    fake_client = MagicMock()
    fake_client.search.return_value = {
        "results": [
            {
                "title": "Result A",
                "url": "https://a.com",
                "content": "Content A",
                "score": 0.9,
            },
            {
                "title": "Result B",
                "url": "https://b.com",
                "content": "Content B",
                "score": 0.8,
                "raw_content": "Full raw content B",
            },
        ]
    }
    monkeypatch.setattr(
        "research_assistant.tools.search_tool.TavilyClient",
        lambda api_key: fake_client,
    )
    return fake_client


def test_run_parses_results_into_search_results(fake_tavily_client):
    tool = TavilySearchTool(api_key="fake-key")
    output = tool.run("some query", max_results=2)

    assert len(tool.last_results) == 2
    first, second = tool.last_results
    assert first.url == "https://a.com"
    assert first.title == "Result A"
    assert first.content == "Content A"
    assert first.score == 0.9
    assert first.raw_content is None
    assert first.query == "some query"
    assert second.raw_content == "Full raw content B"

    assert "Result A" in output
    assert "https://b.com" in output

    fake_tavily_client.search.assert_called_once_with(query="some query", max_results=2)


def test_run_with_no_results_returns_empty_list_and_message(fake_tavily_client):
    fake_tavily_client.search.return_value = {"results": []}
    tool = TavilySearchTool(api_key="fake-key")
    output = tool.run("empty query")
    assert tool.last_results == []
    assert output == "No results found."


def test_as_tooldef_returns_tooldef_with_correct_shape(fake_tavily_client):
    tool = TavilySearchTool(api_key="fake-key")
    tooldef = tool.as_tooldef()
    assert tooldef.name == "web_search"
    assert "query" in tooldef.input_schema["properties"]

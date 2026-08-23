from typing import ClassVar

from tavily import TavilyClient

from research_assistant.llm.base import ToolDef
from research_assistant.models import SearchResult


class TavilySearchTool:
    name = "web_search"
    description = (
        "Search the web for information relevant to a query. Returns a list "
        "of results with titles, URLs, and content snippets."
    )
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
        },
        "required": ["query"],
    }

    def __init__(self, api_key: str) -> None:
        self._client = TavilyClient(api_key=api_key)
        self.last_results: list[SearchResult] = []

    def run(self, query: str, max_results: int = 5) -> str:
        response = self._client.search(query=query, max_results=max_results)
        results = [_to_search_result(query, item) for item in response.get("results", [])]
        self.last_results = results
        return _format_results(results)

    def as_tooldef(self) -> ToolDef:
        return ToolDef(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


def _to_search_result(query: str, item: dict) -> SearchResult:
    return SearchResult(
        query=query,
        url=item["url"],
        title=item["title"],
        content=item["content"],
        score=item.get("score"),
        raw_content=item.get("raw_content"),
    )


def _format_results(results: list[SearchResult]) -> str:
    if not results:
        return "No results found."
    return "\n".join(f"- {r.title} ({r.url})\n  {r.content}" for r in results)

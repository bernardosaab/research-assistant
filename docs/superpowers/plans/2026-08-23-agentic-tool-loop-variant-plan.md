# Agentic Tool-Loop Variant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second research-assistant variant (`Variant.agentic`) where the LLM drives its own `web_search` tool-call loop to research a topic, then a separate write pass produces a cited `Brief` — comparable to the existing `pipeline` variant via `RunRecorder` traces.

**Architecture:** Two-phase per variant module `variants/agentic/run.py`: a research loop (`run_research_loop`) that calls the LLM with the `web_search` tool up to a round cap, collecting `SearchResult`s, followed by a write phase (`write_brief`) that reuses the pipeline's citation contract and `BRIEF_SYSTEM_PROMPT` to turn accumulated sources into markdown. A shared refactor makes `citations.build_source_list` take a flat `list[SearchResult]` instead of a `ResearchPlan`, since the agentic variant has no plan.

**Tech Stack:** Python 3.11+, existing `research_assistant` package (Pydantic models, `anthropic` SDK via `AnthropicLLMClient`, `tavily-python` via `TavilySearchTool`), `pytest`/`pytest-mock`, `uv`.

**Spec:** `docs/superpowers/specs/2026-08-23-agentic-tool-loop-variant-design.md`

## Global Constraints

- Research loop cap: `MAX_ROUNDS = 8`. On hitting the cap, stop feeding tools and proceed to the write phase with whatever was gathered — never raise, never return an empty brief.
- No new tools beyond `web_search` (no read/extract tool, no `submit_brief` tool).
- Output shape must match the pipeline variant exactly: a `Brief` with non-empty `markdown`, a `## Sources` section, and `[n]`-style citations matching `brief.sources`.
- Citation contract for the write-phase LLM call is unchanged from the pipeline: cite using exact bracketed numbers from the given source list; never invent source numbers.
- Follow existing repo conventions: type-hint against concrete classes where the pipeline already does (e.g. `TavilySearchTool`, not the abstract `Tool` protocol) rather than introducing new abstractions; no unit test for the top-level `run()` function itself (the pipeline variant has none either — only a `live` integration test), since it just wires together already-unit-tested pieces plus real config/API clients.
- Every commit uses `uv run python -m pytest tests/unit -q` to verify, not bare `uv run pytest` (PATH picks up a different pytest on this machine).

---

## File Structure

- `src/research_assistant/writing/citations.py` — **modify.** `build_source_list` signature changes from `(plan: ResearchPlan)` to `(results: list[SearchResult])`.
- `src/research_assistant/variants/pipeline/run.py` — **modify.** `write_brief` flattens `plan.sub_questions[].search_results` before calling `build_source_list`.
- `tests/unit/test_citations.py` — **modify.** Fixtures rewritten as flat `list[SearchResult]` instead of `ResearchPlan`/`SubQuestion`.
- `src/research_assistant/variants/agentic/__init__.py` — **create.** Empty package marker.
- `src/research_assistant/variants/agentic/run.py` — **create.** `MAX_ROUNDS`, `RESEARCH_SYSTEM_PROMPT`, `run_research_loop()`, `write_brief()`, `run()`.
- `tests/unit/test_agentic_run.py` — **create.** `ScriptedLLMClient`/`FakeSearchTool` test doubles, tests for `run_research_loop` and `write_brief`.
- `src/research_assistant/variants/__init__.py` — **modify.** Register `Variant.agentic` in `VARIANT_REGISTRY`.
- `tests/unit/test_variant_registry.py` — **create.** Verifies the registration.
- `tests/live/test_agentic_live.py` — **create.** Mirrors `tests/live/test_pipeline_live.py` for the new variant.

---

### Task 1: Refactor `build_source_list` to take a flat result list

**Files:**
- Modify: `src/research_assistant/writing/citations.py`
- Modify: `src/research_assistant/variants/pipeline/run.py:109-115` (the `write_brief` function)
- Test: `tests/unit/test_citations.py`

**Interfaces:**
- Consumes: `SearchResult`, `Source` from `research_assistant.models` (unchanged shapes).
- Produces: `build_source_list(results: list[SearchResult]) -> list[Source]` — used by Task 3's `write_brief` in the agentic variant, and by the pipeline's `write_brief` after this task.

- [ ] **Step 1: Rewrite the test file for the new signature**

Replace the full contents of `tests/unit/test_citations.py`:

```python
from research_assistant.models import SearchResult
from research_assistant.writing.citations import (
    build_source_list,
    format_sources_for_prompt,
    render_sources_section,
)


def _search_result(url: str, title: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content="some content")


def test_build_source_list_assigns_sequential_ids_in_order_of_appearance():
    results = [
        _search_result("https://a.com", "A"),
        _search_result("https://b.com", "B"),
    ]
    sources = build_source_list(results)
    assert [(s.id, s.url) for s in sources] == [
        (1, "https://a.com"),
        (2, "https://b.com"),
    ]


def test_build_source_list_dedupes_repeated_urls():
    results = [
        _search_result("https://a.com", "A"),
        _search_result("https://a.com", "A"),
        _search_result("https://c.com", "C"),
    ]
    sources = build_source_list(results)
    assert [s.url for s in sources] == ["https://a.com", "https://c.com"]


def test_build_source_list_empty_list_returns_empty_list():
    assert build_source_list([]) == []


def test_format_sources_for_prompt_no_sources():
    assert format_sources_for_prompt([]) == "No sources available."


def test_format_sources_for_prompt_lists_each_source_with_bracketed_id():
    sources = build_source_list([_search_result("https://a.com", "A")])
    assert format_sources_for_prompt(sources) == "[1] A — https://a.com"


def test_render_sources_section_no_sources_returns_empty_string():
    assert render_sources_section([]) == ""


def test_render_sources_section_renders_markdown_list():
    sources = build_source_list(
        [_search_result("https://a.com", "A"), _search_result("https://b.com", "B")]
    )
    rendered = render_sources_section(sources)
    assert rendered == "## Sources\n1. [A](https://a.com)\n2. [B](https://b.com)"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_citations.py -v`
Expected: FAIL — `build_source_list` still expects a `ResearchPlan` (calling `.sub_questions` on a `list` raises `AttributeError`, or a `TypeError` from passing a list where a plan was expected).

- [ ] **Step 3: Update `build_source_list`'s implementation**

In `src/research_assistant/writing/citations.py`, replace the import and function:

```python
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
```

(`format_sources_for_prompt` and `render_sources_section` are unchanged — leave them as-is.)

- [ ] **Step 4: Run the citations tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_citations.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Update the pipeline's call site**

In `src/research_assistant/variants/pipeline/run.py`, in `write_brief`, change:

```python
def write_brief(plan: ResearchPlan, llm: LLMClient, recorder: RunRecorder) -> Brief:
    sources = build_source_list(plan)
```

to:

```python
def write_brief(plan: ResearchPlan, llm: LLMClient, recorder: RunRecorder) -> Brief:
    all_results = [r for sq in plan.sub_questions for r in sq.search_results]
    sources = build_source_list(all_results)
```

- [ ] **Step 6: Run the full unit suite to confirm nothing else broke**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (16 tests — same count as before, since this is a signature change with an equivalent-coverage test rewrite, not new coverage)

- [ ] **Step 7: Commit**

```bash
git add src/research_assistant/writing/citations.py src/research_assistant/variants/pipeline/run.py tests/unit/test_citations.py
git commit -m "refactor: build_source_list takes a flat SearchResult list

Decouples citation building from ResearchPlan so the upcoming agentic
variant (which has no plan) can reuse it."
```

---

### Task 2: Research loop (`run_research_loop`)

**Files:**
- Create: `src/research_assistant/variants/agentic/__init__.py`
- Create: `src/research_assistant/variants/agentic/run.py`
- Test: `tests/unit/test_agentic_run.py`

**Interfaces:**
- Consumes: `LLMClient`, `LLMMessage`, `LLMResponse`, `LLMUsage`, `ToolCall`, `ToolResult` from `research_assistant.llm.base`; `SearchResult` from `research_assistant.models`; `RunRecorder` (`.record_llm_call(usage: LLMUsage)`, `.record_tool_call(tool_name: str)`, `.finalize() -> RunTrace`) from `research_assistant.tracing.recorder`; `TavilySearchTool` shape (`.name`, `.run(query: str) -> str`, `.last_results: list[SearchResult]`, `.as_tooldef() -> ToolDef`) from `research_assistant.tools.search_tool`.
- Produces: `MAX_ROUNDS: int = 8`; `RESEARCH_SYSTEM_PROMPT: str`; `run_research_loop(topic: str, llm: LLMClient, search_tool: TavilySearchTool, recorder: RunRecorder) -> list[SearchResult]` — consumed by Task 3's `run()`.

- [ ] **Step 1: Create the package marker**

Create `src/research_assistant/variants/agentic/__init__.py` (empty file).

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_agentic_run.py`:

```python
from research_assistant.llm.base import LLMResponse, LLMUsage, ToolCall
from research_assistant.models import SearchResult
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.agentic.run import MAX_ROUNDS, run_research_loop


class ScriptedLLMClient:
    """Fake LLMClient that returns a fixed sequence of responses."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools=None, max_tokens=4096):
        self.calls.append(
            {
                "system": system,
                "messages": list(messages),
                "tools": tools,
                "max_tokens": max_tokens,
            }
        )
        return self._responses.pop(0)


class FakeSearchTool:
    name = "web_search"

    def __init__(self, results_by_query: dict[str, list[SearchResult]]) -> None:
        self._results_by_query = results_by_query
        self.last_results: list[SearchResult] = []
        self.queries: list[str] = []

    def run(self, query: str) -> str:
        self.queries.append(query)
        self.last_results = self._results_by_query.get(query, [])
        return f"results for {query}"

    def as_tooldef(self):
        from research_assistant.llm.base import ToolDef

        return ToolDef(name=self.name, description="fake search", input_schema={})


def _usage() -> LLMUsage:
    return LLMUsage(input_tokens=10, output_tokens=5)


def _search_result(url: str, title: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content="content")


def _tool_use_response(call_id: str, query: str) -> LLMResponse:
    return LLMResponse(
        text=None,
        tool_calls=[ToolCall(id=call_id, name="web_search", input={"query": query})],
        stop_reason="tool_use",
        usage=_usage(),
    )


def _end_turn_response(text: str = "done researching") -> LLMResponse:
    return LLMResponse(text=text, tool_calls=[], stop_reason="end_turn", usage=_usage())


def test_run_research_loop_runs_search_then_stops_on_end_turn():
    llm = ScriptedLLMClient([_tool_use_response("call-1", "capital of France"), _end_turn_response()])
    search_tool = FakeSearchTool({"capital of France": [_search_result("https://a.com", "A")]})
    recorder = RunRecorder(variant="agentic", topic="France")

    results = run_research_loop("France", llm, search_tool, recorder)

    assert results == [_search_result("https://a.com", "A")]
    assert search_tool.queries == ["capital of France"]
    assert len(llm.calls) == 2


def test_run_research_loop_accumulates_results_across_multiple_rounds():
    llm = ScriptedLLMClient(
        [
            _tool_use_response("call-1", "query one"),
            _tool_use_response("call-2", "query two"),
            _end_turn_response(),
        ]
    )
    search_tool = FakeSearchTool(
        {
            "query one": [_search_result("https://a.com", "A")],
            "query two": [_search_result("https://b.com", "B")],
        }
    )
    recorder = RunRecorder(variant="agentic", topic="t")

    results = run_research_loop("t", llm, search_tool, recorder)

    assert [r.url for r in results] == ["https://a.com", "https://b.com"]
    assert search_tool.queries == ["query one", "query two"]


def test_run_research_loop_handles_multiple_tool_calls_in_one_round():
    response = LLMResponse(
        text=None,
        tool_calls=[
            ToolCall(id="call-1", name="web_search", input={"query": "q1"}),
            ToolCall(id="call-2", name="web_search", input={"query": "q2"}),
        ],
        stop_reason="tool_use",
        usage=_usage(),
    )
    llm = ScriptedLLMClient([response, _end_turn_response()])
    search_tool = FakeSearchTool(
        {"q1": [_search_result("https://a.com", "A")], "q2": [_search_result("https://b.com", "B")]}
    )
    recorder = RunRecorder(variant="agentic", topic="t")

    results = run_research_loop("t", llm, search_tool, recorder)

    assert [r.url for r in results] == ["https://a.com", "https://b.com"]
    assert search_tool.queries == ["q1", "q2"]


def test_run_research_loop_stops_at_max_rounds_and_still_returns_results():
    responses = [_tool_use_response(f"call-{i}", f"query {i}") for i in range(MAX_ROUNDS)]
    llm = ScriptedLLMClient(responses)
    search_tool = FakeSearchTool(
        {f"query {i}": [_search_result(f"https://{i}.com", str(i))] for i in range(MAX_ROUNDS)}
    )
    recorder = RunRecorder(variant="agentic", topic="t")

    results = run_research_loop("t", llm, search_tool, recorder)

    assert len(results) == MAX_ROUNDS
    assert len(llm.calls) == MAX_ROUNDS


def test_run_research_loop_records_llm_and_tool_calls_on_recorder():
    llm = ScriptedLLMClient([_tool_use_response("call-1", "q"), _end_turn_response()])
    search_tool = FakeSearchTool({"q": [_search_result("https://a.com", "A")]})
    recorder = RunRecorder(variant="agentic", topic="t")

    run_research_loop("t", llm, search_tool, recorder)
    trace = recorder.finalize()

    assert trace.llm_calls == 2
    assert trace.search_calls == 1
    assert trace.input_tokens == 20
    assert trace.output_tokens == 10
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_agentic_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research_assistant.variants.agentic.run'`

- [ ] **Step 4: Implement the research loop**

Create `src/research_assistant/variants/agentic/run.py`:

```python
from research_assistant.llm.base import LLMClient, LLMMessage, ToolResult
from research_assistant.models import SearchResult
from research_assistant.tools.search_tool import TavilySearchTool
from research_assistant.tracing.recorder import RunRecorder

MAX_ROUNDS = 8

RESEARCH_SYSTEM_PROMPT = (
    "You are a research assistant investigating a topic using web search. "
    "Search as many times as needed to build a well-rounded understanding "
    "— covering the topic from multiple angles — then stop calling tools "
    "once you have enough to write a short brief."
)


def run_research_loop(
    topic: str, llm: LLMClient, search_tool: TavilySearchTool, recorder: RunRecorder
) -> list[SearchResult]:
    history: list[LLMMessage] = [LLMMessage(role="user", text=f"Topic: {topic}")]
    all_results: list[SearchResult] = []

    for _ in range(MAX_ROUNDS):
        response = llm.complete(
            system=RESEARCH_SYSTEM_PROMPT,
            messages=history,
            tools=[search_tool.as_tooldef()],
        )
        recorder.record_llm_call(response.usage)

        if response.stop_reason != "tool_use":
            break

        history.append(
            LLMMessage(role="assistant", text=response.text, tool_calls=response.tool_calls)
        )

        tool_results = []
        for call in response.tool_calls:
            result_text = search_tool.run(call.input["query"])
            recorder.record_tool_call(search_tool.name)
            all_results.extend(search_tool.last_results)
            tool_results.append(ToolResult(tool_call_id=call.id, content=result_text))
        history.append(LLMMessage(role="user", tool_results=tool_results))

    return all_results
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_agentic_run.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/research_assistant/variants/agentic/__init__.py src/research_assistant/variants/agentic/run.py tests/unit/test_agentic_run.py
git commit -m "feat: add agentic variant research loop

LLM drives its own web_search tool calls (up to MAX_ROUNDS=8) instead of
following a pre-planned sequence of sub-questions, per the approved design
spec (docs/superpowers/specs/2026-08-23-agentic-tool-loop-variant-design.md)."
```

---

### Task 3: Write phase and top-level `run()`

**Files:**
- Modify: `src/research_assistant/variants/agentic/run.py` (append to the file from Task 2)
- Test: `tests/unit/test_agentic_run.py` (append)

**Interfaces:**
- Consumes: `run_research_loop`, `MAX_ROUNDS`, `RESEARCH_SYSTEM_PROMPT` (Task 2, same file); `BRIEF_SYSTEM_PROMPT: str` from `research_assistant.variants.pipeline.run`; `build_source_list(results: list[SearchResult]) -> list[Source]`, `format_sources_for_prompt(sources: list[Source]) -> str` from `research_assistant.writing.citations` (Task 1's new signature); `assemble_brief(topic: str, body_markdown: str, sources: list[Source]) -> Brief` from `research_assistant.writing.brief`; `get_settings()` from `research_assistant.config`; `AnthropicLLMClient` from `research_assistant.llm.anthropic_client`.
- Produces: `write_brief(topic: str, results: list[SearchResult], llm: LLMClient, recorder: RunRecorder) -> Brief`; `run(topic: str, recorder: RunRecorder | None = None) -> Brief` — consumed by Task 4's `VARIANT_REGISTRY`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_agentic_run.py` (add these imports to the top of the file, alongside the existing ones):

```python
from research_assistant.variants.agentic.run import write_brief
```

Add these two test functions at the end of the file:

```python
def test_write_brief_produces_cited_markdown_with_sources_section():
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                text="Paris is the capital of France [1].",
                tool_calls=[],
                stop_reason="end_turn",
                usage=_usage(),
            )
        ]
    )
    results = [_search_result("https://a.com", "A")]
    recorder = RunRecorder(variant="agentic", topic="t")

    brief = write_brief("France", results, llm, recorder)

    assert "Paris is the capital of France [1]." in brief.markdown
    assert "## Sources" in brief.markdown
    assert "[A](https://a.com)" in brief.markdown
    assert brief.sources[0].url == "https://a.com"
    assert len(llm.calls) == 1
    assert llm.calls[0]["max_tokens"] == 2048


def test_write_brief_records_llm_call_on_recorder():
    llm = ScriptedLLMClient([_end_turn_response("brief text")])
    recorder = RunRecorder(variant="agentic", topic="t")

    write_brief("t", [], llm, recorder)

    assert recorder.finalize().llm_calls == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_agentic_run.py -v`
Expected: FAIL with `ImportError: cannot import name 'write_brief'`

- [ ] **Step 3: Implement `write_brief` and `run`**

Append to `src/research_assistant/variants/agentic/run.py` (add these imports at the top, alongside the existing ones):

```python
from research_assistant.config import get_settings
from research_assistant.llm.anthropic_client import AnthropicLLMClient
from research_assistant.models import Brief
from research_assistant.variants.pipeline.run import BRIEF_SYSTEM_PROMPT
from research_assistant.writing.brief import assemble_brief
from research_assistant.writing.citations import build_source_list, format_sources_for_prompt
```

Then append the two functions:

```python
def write_brief(
    topic: str, results: list[SearchResult], llm: LLMClient, recorder: RunRecorder
) -> Brief:
    sources = build_source_list(results)
    sources_text = format_sources_for_prompt(sources)
    response = llm.complete(
        system=BRIEF_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", text=f"Topic: {topic}\n\nSources:\n{sources_text}")],
        max_tokens=2048,
    )
    recorder.record_llm_call(response.usage)
    return assemble_brief(topic, response.text or "", sources)


def run(topic: str, recorder: RunRecorder | None = None) -> Brief:
    settings = get_settings()
    llm = AnthropicLLMClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    search_tool = TavilySearchTool(api_key=settings.tavily_api_key)
    recorder = recorder or RunRecorder(variant="agentic", topic=topic)

    results = run_research_loop(topic, llm, search_tool, recorder)
    return write_brief(topic, results, llm, recorder)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_agentic_run.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/research_assistant/variants/agentic/run.py tests/unit/test_agentic_run.py
git commit -m "feat: add agentic variant write phase and top-level run()

Reuses the pipeline's BRIEF_SYSTEM_PROMPT and citation contract so both
variants produce structurally identical, comparable Briefs."
```

---

### Task 4: Register the variant

**Files:**
- Modify: `src/research_assistant/variants/__init__.py`
- Test: `tests/unit/test_variant_registry.py`

**Interfaces:**
- Consumes: `run` from `research_assistant.variants.agentic.run` (Task 3); existing `Variant` enum and `VARIANT_REGISTRY` in `research_assistant/variants/__init__.py`.
- Produces: `Variant.agentic` enum member; `VARIANT_REGISTRY[Variant.agentic]` — consumed by `cli.py` (no code change needed there — it already looks up `VARIANT_REGISTRY[variant]` generically).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_variant_registry.py`:

```python
from research_assistant.variants import VARIANT_REGISTRY, Variant
from research_assistant.variants.agentic.run import run as run_agentic


def test_agentic_variant_is_registered():
    assert Variant.agentic in VARIANT_REGISTRY
    assert VARIANT_REGISTRY[Variant.agentic] is run_agentic
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_variant_registry.py -v`
Expected: FAIL with `AttributeError: agentic` (no such member on `Variant`)

- [ ] **Step 3: Register the variant**

Replace the contents of `src/research_assistant/variants/__init__.py`:

```python
from collections.abc import Callable
from enum import Enum

from research_assistant.models import Brief
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.agentic.run import run as run_agentic
from research_assistant.variants.pipeline.run import run as run_pipeline


class Variant(str, Enum):
    pipeline = "pipeline"
    agentic = "agentic"


VARIANT_REGISTRY: dict[Variant, Callable[[str, RunRecorder | None], Brief]] = {
    Variant.pipeline: run_pipeline,
    Variant.agentic: run_agentic,
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_variant_registry.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add src/research_assistant/variants/__init__.py tests/unit/test_variant_registry.py
git commit -m "feat: register agentic variant in VARIANT_REGISTRY

research-assistant run <topic> --variant agentic now works via the
existing CLI, no cli.py changes needed."
```

---

### Task 5: Live integration test

**Files:**
- Create: `tests/live/test_agentic_live.py`

**Interfaces:**
- Consumes: `run` from `research_assistant.variants.agentic.run` (Task 3); `get_settings` from `research_assistant.config`.
- Produces: nothing consumed elsewhere — this is a leaf integration test, mirroring `tests/live/test_pipeline_live.py`.

- [ ] **Step 1: Create the live test**

Create `tests/live/test_agentic_live.py`:

```python
import pytest

from research_assistant.config import get_settings
from research_assistant.variants.agentic.run import run

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
def test_agentic_produces_cited_brief_for_simple_topic():
    brief = run("What is the capital of France and why?")

    assert brief.markdown.strip() != ""
    assert "## Sources" in brief.markdown
    assert "[1]" in brief.markdown
    assert len(brief.sources) > 0
```

- [ ] **Step 2: Run it (only if you have `.env` configured with real API keys — this makes real, billed API calls)**

Run: `uv run python -m pytest tests/live/test_agentic_live.py -m live -v`
Expected: PASS if `.env` has real keys, or SKIPPED with reason "ANTHROPIC_API_KEY / TAVILY_API_KEY not configured (.env)" if not. Either outcome is fine to commit on — this test is opt-in by design (same as the pipeline's live test) and isn't part of the default `pytest` run (`addopts = "-m 'not live'"`).

- [ ] **Step 3: Commit**

```bash
git add tests/live/test_agentic_live.py
git commit -m "test: add live integration test for the agentic variant"
```

---

### Task 6: Full regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS, 24 tests (16 original + 5 from Task 2 + 2 from Task 3 + 1 from Task 4)

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check src tests`
Expected: no errors. If ruff reports anything (e.g. import ordering), run `uv run ruff check src tests --fix` and re-check; for anything it can't auto-fix, resolve per its message before proceeding.

- [ ] **Step 3: Commit if ruff's `--fix` changed anything**

```bash
git add -u
git commit -m "style: ruff fixes"
```

(Skip this step entirely if Step 2 reported no errors and nothing changed.)

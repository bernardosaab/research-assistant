# GraphRAG Variant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third research-assistant variant (`Variant.graphrag`) that extracts search results into a Neo4j knowledge graph (entities + relationships), wiped and rebuilt every run, then writes a cited `Brief` from the graph's facts — comparable to `pipeline`/`agentic` via `RunRecorder` traces.

**Architecture:** Reuses the pipeline's `generate_plan`/`run_searches` as-is. New: per-sub-question LLM extraction into `Triple`s (subject/relation/object/source_url), written into Neo4j via a thin `Neo4jGraphStore` wrapper (one generic `RELATION` edge type carrying the relation label as a property, not a dynamic Cypher identifier), then the whole graph is queried back as a flat fact list for the write phase — no traversal/filtering needed since the graph is already topic-scoped.

**Tech Stack:** Python 3.11+, existing `research_assistant` package, `neo4j` Python driver (new), local Neo4j via `docker-compose.yml`, `pytest`/`pytest-mock`, `uv`.

**Spec:** `docs/superpowers/specs/2026-08-23-graphrag-variant-design.md`

## Global Constraints

- No cross-run persistence: `Neo4jGraphStore.clear()` runs before every graph build, every time.
- `Settings` gains `neo4j_uri`, `neo4j_user`, `neo4j_password` as **optional** fields (default `None`) — must not affect `pipeline`/`agentic`, which don't read them.
- Missing Neo4j config → `run()` raises `RuntimeError("GraphRAG variant requires NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD in .env. Run \`docker compose up -d\` to start a local Neo4j instance, then set these to its connection details.")` verbatim — not a raw driver connection error.
- Citation contract unchanged from the other variants: cite the exact bracketed number from the given source list; never invent one. `format_facts_for_prompt` omits the citation marker (not a fabricated one) for a fact whose `source_url` isn't in the deduped source list.
- Relation labels (LLM output, arbitrary text) are stored as a `type` property on one fixed `RELATION` edge type — never as a dynamic Cypher relationship-type identifier.
- Malformed LLM extraction output (missing required keys) is dropped, not raised — external-boundary defensive parsing, matching `_parse_json_list`'s existing behavior for malformed plan output.
- Every commit uses `uv run python -m pytest tests/unit -q` to verify, not bare `uv run pytest` (this machine's PATH resolves the latter to a different pytest off the venv).
- No unit test for the top-level `run()` function itself — matches the existing pipeline/agentic convention (only a `live` integration test covers the fully-wired `run()`).

---

## File Structure

- `src/research_assistant/models.py` — **modify.** Add `Triple` model.
- `src/research_assistant/config.py` — **modify.** Add optional `neo4j_uri`/`neo4j_user`/`neo4j_password` to `Settings`.
- `pyproject.toml` — **modify.** Add `graphrag` extra (`neo4j>=5`).
- `src/research_assistant/variants/graphrag/__init__.py` — **create.** Empty package marker.
- `src/research_assistant/variants/graphrag/graph_store.py` — **create.** `Neo4jGraphStore`.
- `src/research_assistant/variants/graphrag/extraction.py` — **create.** `EXTRACTION_SYSTEM_PROMPT`, `extract_triples()`.
- `src/research_assistant/variants/graphrag/run.py` — **create.** `build_graph()`, `BRIEF_SYSTEM_PROMPT`, `format_facts_for_prompt()`, `write_brief()`, `run()`.
- `src/research_assistant/variants/__init__.py` — **modify.** Register `Variant.graphrag`.
- `docker-compose.yml` — **create.** Local Neo4j.
- `.env.example` — **modify.** Add `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD`.
- `tests/unit/test_models.py` — **modify.** Add `Triple` tests.
- `tests/unit/test_graphrag_extraction.py` — **create.**
- `tests/unit/test_graphrag_graph_store.py` — **create.**
- `tests/unit/test_graphrag_run.py` — **create.**
- `tests/unit/test_variant_registry.py` — **modify.** Add graphrag registration test.
- `tests/live/test_graphrag_live.py` — **create.**

---

### Task 1: `Triple` model

**Files:**
- Modify: `src/research_assistant/models.py`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `Triple(subject: str, relation: str, object: str, source_url: str)` — a Pydantic `BaseModel`, consumed by every later task in this plan.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_models.py` (add `Triple` to the existing import from `research_assistant.models`):

```python
def test_triple_holds_subject_relation_object_source():
    triple = Triple(subject="Napoleon", relation="born_in", object="Corsica", source_url="https://a.com")
    assert triple.subject == "Napoleon"
    assert triple.relation == "born_in"
    assert triple.object == "Corsica"
    assert triple.source_url == "https://a.com"


def test_triple_missing_field_raises():
    with pytest.raises(ValidationError):
        Triple(subject="Napoleon", relation="born_in", object="Corsica")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Triple'`

- [ ] **Step 3: Add the model**

In `src/research_assistant/models.py`, append at the end of the file:

```python
class Triple(BaseModel):
    subject: str
    relation: str
    object: str
    source_url: str
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_models.py -v`
Expected: PASS (9 tests — 7 existing + 2 new)

- [ ] **Step 5: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (26 tests — 24 existing + 2 new)

- [ ] **Step 6: Commit**

```bash
git add src/research_assistant/models.py tests/unit/test_models.py
git commit -m "feat: add Triple model for graphrag variant"
```

---

### Task 2: Entity/relationship extraction

**Files:**
- Create: `src/research_assistant/variants/graphrag/__init__.py`
- Create: `src/research_assistant/variants/graphrag/extraction.py`
- Test: `tests/unit/test_graphrag_extraction.py`

**Interfaces:**
- Consumes: `LLMClient`, `LLMMessage`, `LLMResponse`, `LLMUsage` from `research_assistant.llm.base`; `SubQuestion`, `Triple` from `research_assistant.models`; `RunRecorder` from `research_assistant.tracing.recorder`.
- Produces: `EXTRACTION_SYSTEM_PROMPT: str`; `extract_triples(sub_question: SubQuestion, llm: LLMClient, recorder: RunRecorder) -> list[Triple]` — consumed by Task 4's `build_graph`.

- [ ] **Step 1: Create the package marker**

Create `src/research_assistant/variants/graphrag/__init__.py` (empty file).

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_graphrag_extraction.py`:

```python
from research_assistant.llm.base import LLMResponse, LLMUsage
from research_assistant.models import SearchResult, SubQuestion, Triple
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.graphrag.extraction import extract_triples


class ScriptedLLMClient:
    """Fake LLMClient that returns a fixed sequence of responses."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools=None, max_tokens=4096):
        self.calls.append(
            {"system": system, "messages": list(messages), "tools": tools, "max_tokens": max_tokens}
        )
        return self._responses.pop(0)


def _usage() -> LLMUsage:
    return LLMUsage(input_tokens=10, output_tokens=5)


def _search_result(url: str, title: str, content: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content=content)


def _sub_question(results: list[SearchResult]) -> SubQuestion:
    return SubQuestion(id="1", text="Where was Napoleon born?", search_results=results)


def test_extract_triples_parses_valid_json_array():
    response_text = (
        '[{"subject": "Napoleon Bonaparte", "relation": "born_in", '
        '"object": "Corsica", "source_url": "https://a.com"}]'
    )
    llm = ScriptedLLMClient(
        [LLMResponse(text=response_text, tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([_search_result("https://a.com", "A", "Napoleon was born in Corsica.")])
    recorder = RunRecorder(variant="graphrag", topic="t")

    triples = extract_triples(sub_question, llm, recorder)

    assert triples == [
        Triple(subject="Napoleon Bonaparte", relation="born_in", object="Corsica", source_url="https://a.com")
    ]
    assert recorder.finalize().llm_calls == 1


def test_extract_triples_drops_entries_missing_required_keys():
    response_text = '[{"subject": "A", "relation": "rel"}]'
    llm = ScriptedLLMClient(
        [LLMResponse(text=response_text, tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([])
    recorder = RunRecorder(variant="graphrag", topic="t")

    assert extract_triples(sub_question, llm, recorder) == []


def test_extract_triples_no_results_still_sends_placeholder_text():
    llm = ScriptedLLMClient(
        [LLMResponse(text="[]", tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([])
    recorder = RunRecorder(variant="graphrag", topic="t")

    triples = extract_triples(sub_question, llm, recorder)

    assert triples == []
    assert "No search results found." in llm.calls[0]["messages"][0].text


def test_extract_triples_empty_array_response():
    llm = ScriptedLLMClient(
        [LLMResponse(text="[]", tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    sub_question = _sub_question([_search_result("https://a.com", "A", "content")])
    recorder = RunRecorder(variant="graphrag", topic="t")

    assert extract_triples(sub_question, llm, recorder) == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_graphrag_extraction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research_assistant.variants.graphrag.extraction'`

- [ ] **Step 4: Implement extraction**

Create `src/research_assistant/variants/graphrag/extraction.py`:

```python
import json
import re

from pydantic import ValidationError

from research_assistant.llm.base import LLMClient, LLMMessage
from research_assistant.models import SubQuestion, Triple
from research_assistant.tracing.recorder import RunRecorder

EXTRACTION_SYSTEM_PROMPT = (
    "You are extracting a knowledge graph from web search results. Given a "
    "list of search results, each shown as \"- title (url): content\", "
    "identify the key entities and relationships between them. Respond "
    "with ONLY a JSON array of objects, each with exactly these keys: "
    "\"subject\", \"relation\", \"object\", \"source_url\". Use concise "
    "entity names (e.g. \"Napoleon Bonaparte\", not \"the French emperor "
    "who...\"), short relation labels (e.g. \"born_in\", \"defeated_at\"), "
    "and set \"source_url\" to the exact url of the result the fact came "
    "from. Extract only relationships explicitly stated or clearly implied "
    "by the text. If no clear relationships are found, return an empty "
    "array."
)


def extract_triples(
    sub_question: SubQuestion, llm: LLMClient, recorder: RunRecorder
) -> list[Triple]:
    results_text = (
        "\n".join(
            f"- {r.title} ({r.url}): {r.content}" for r in sub_question.search_results
        )
        or "No search results found."
    )
    response = llm.complete(
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", text=f"Search results:\n{results_text}")],
    )
    recorder.record_llm_call(response.usage)
    return _parse_triples(response.text or "[]")


def _parse_triples(text: str) -> list[Triple]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    triples: list[Triple] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            triples.append(Triple(**item))
        except ValidationError:
            continue
    return triples
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_graphrag_extraction.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (30 tests — 26 existing + 4 new)

- [ ] **Step 7: Commit**

```bash
git add src/research_assistant/variants/graphrag/__init__.py src/research_assistant/variants/graphrag/extraction.py tests/unit/test_graphrag_extraction.py
git commit -m "feat: add graphrag entity/relationship extraction"
```

---

### Task 3: Neo4j graph store

**Files:**
- Create: `src/research_assistant/variants/graphrag/graph_store.py`
- Modify: `pyproject.toml` (add `graphrag` extra)
- Modify: `src/research_assistant/config.py` (add optional Neo4j settings)
- Test: `tests/unit/test_graphrag_graph_store.py`

**Interfaces:**
- Consumes: `Triple` from `research_assistant.models`; the `neo4j` package's `GraphDatabase`.
- Produces: `Neo4jGraphStore(uri: str, user: str, password: str)` with methods `clear() -> None`, `add_triple(subject: str, relation: str, object: str, source_url: str) -> None`, `get_all_facts() -> list[Triple]`, `close() -> None` — consumed by Task 4's `build_graph` and Task 5's `run()`. Also produces `Settings.neo4j_uri`, `Settings.neo4j_user`, `Settings.neo4j_password` (all `str | None`, default `None`) — consumed by Task 5's `run()`.

- [ ] **Step 1: Add the `graphrag` extra and sync it**

In `pyproject.toml`, add a new table after the existing `[project.optional-dependencies]` entries (`dev`, `notebook`):

```toml
graphrag = [
    "neo4j>=5",
]
```

Run: `uv sync --extra graphrag`
Expected: installs the `neo4j` package into the venv.

- [ ] **Step 2: Add optional Neo4j settings**

In `src/research_assistant/config.py`, add three fields to `Settings` (after `anthropic_model`, before `model_config`):

```python
neo4j_uri: str | None = None
neo4j_user: str | None = None
neo4j_password: str | None = None
```

The full class should now read:

```python
class Settings(BaseSettings):
    anthropic_api_key: str
    tavily_api_key: str
    anthropic_model: str = "claude-sonnet-5"
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

- [ ] **Step 3: Write the failing tests**

Create `tests/unit/test_graphrag_graph_store.py`:

```python
from unittest.mock import MagicMock

import pytest

from research_assistant.models import Triple
from research_assistant.variants.graphrag.graph_store import Neo4jGraphStore


@pytest.fixture
def fake_driver(monkeypatch):
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    monkeypatch.setattr(
        "research_assistant.variants.graphrag.graph_store.GraphDatabase.driver",
        lambda uri, auth: driver,
    )
    return driver, session


def test_clear_runs_detach_delete(fake_driver):
    _, session = fake_driver
    store = Neo4jGraphStore("bolt://x", "u", "p")

    store.clear()

    session.run.assert_called_once_with("MATCH (n) DETACH DELETE n")


def test_add_triple_merges_entities_and_relation_with_params(fake_driver):
    _, session = fake_driver
    store = Neo4jGraphStore("bolt://x", "u", "p")

    store.add_triple("Napoleon", "born_in", "Corsica", "https://a.com")

    args, kwargs = session.run.call_args
    assert "MERGE" in args[0]
    assert "RELATION" in args[0]
    assert kwargs == {
        "subject": "Napoleon",
        "object": "Corsica",
        "relation": "born_in",
        "source_url": "https://a.com",
    }


def test_get_all_facts_returns_triples_from_query_results(fake_driver):
    _, session = fake_driver
    record = MagicMock()
    record.data.return_value = {
        "subject": "Napoleon",
        "relation": "born_in",
        "object": "Corsica",
        "source_url": "https://a.com",
    }
    session.run.return_value = [record]
    store = Neo4jGraphStore("bolt://x", "u", "p")

    facts = store.get_all_facts()

    assert facts == [
        Triple(subject="Napoleon", relation="born_in", object="Corsica", source_url="https://a.com")
    ]


def test_get_all_facts_empty_graph_returns_empty_list(fake_driver):
    _, session = fake_driver
    session.run.return_value = []
    store = Neo4jGraphStore("bolt://x", "u", "p")

    assert store.get_all_facts() == []


def test_close_closes_the_driver(fake_driver):
    driver, _ = fake_driver
    store = Neo4jGraphStore("bolt://x", "u", "p")

    store.close()

    driver.close.assert_called_once()
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_graphrag_graph_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research_assistant.variants.graphrag.graph_store'`

- [ ] **Step 5: Implement the graph store**

Create `src/research_assistant/variants/graphrag/graph_store.py`:

```python
from neo4j import GraphDatabase

from research_assistant.models import Triple


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def clear(self) -> None:
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def add_triple(self, subject: str, relation: str, object: str, source_url: str) -> None:
        with self._driver.session() as session:
            session.run(
                "MERGE (a:Entity {name: $subject}) "
                "MERGE (b:Entity {name: $object}) "
                "MERGE (a)-[r:RELATION {type: $relation}]->(b) "
                "SET r.source_url = $source_url",
                subject=subject, object=object, relation=relation, source_url=source_url,
            )

    def get_all_facts(self) -> list[Triple]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (a:Entity)-[r:RELATION]->(b:Entity) "
                "RETURN a.name AS subject, r.type AS relation, "
                "b.name AS object, r.source_url AS source_url"
            )
            return [Triple(**record.data()) for record in result]

    def close(self) -> None:
        self._driver.close()
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_graphrag_graph_store.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (35 tests — 30 existing + 5 new)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/research_assistant/config.py src/research_assistant/variants/graphrag/graph_store.py tests/unit/test_graphrag_graph_store.py
git commit -m "feat: add Neo4jGraphStore and optional Neo4j settings"
```

---

### Task 4: Graph build orchestration

**Files:**
- Create: `src/research_assistant/variants/graphrag/run.py` (partial — this task only)
- Test: `tests/unit/test_graphrag_run.py`

**Interfaces:**
- Consumes: `extract_triples` (Task 2); `Neo4jGraphStore`-shaped object (Task 3's methods — a fake substitutes in tests); `ResearchPlan` from `research_assistant.models`; `LLMClient`, `RunRecorder`.
- Produces: `build_graph(plan: ResearchPlan, llm: LLMClient, graph_store, recorder: RunRecorder) -> list[Triple]` — consumed by Task 5's `run()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_graphrag_run.py`:

```python
from research_assistant.llm.base import LLMResponse, LLMUsage
from research_assistant.models import ResearchPlan, SearchResult, SubQuestion, Triple
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.graphrag.run import build_graph


class ScriptedLLMClient:
    """Fake LLMClient that returns a fixed sequence of responses."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, *, system, messages, tools=None, max_tokens=4096):
        self.calls.append(
            {"system": system, "messages": list(messages), "tools": tools, "max_tokens": max_tokens}
        )
        return self._responses.pop(0)


class FakeGraphStore:
    def __init__(self) -> None:
        self.cleared = False
        self.added: list[tuple[str, str, str, str]] = []

    def clear(self) -> None:
        self.cleared = True

    def add_triple(self, subject: str, relation: str, object: str, source_url: str) -> None:
        self.added.append((subject, relation, object, source_url))

    def get_all_facts(self) -> list[Triple]:
        return [
            Triple(subject=s, relation=r, object=o, source_url=u)
            for s, r, o, u in self.added
        ]

    def close(self) -> None:
        pass


def _usage() -> LLMUsage:
    return LLMUsage(input_tokens=10, output_tokens=5)


def _search_result(url: str, title: str, content: str) -> SearchResult:
    return SearchResult(query="q", url=url, title=title, content=content)


def test_build_graph_clears_then_extracts_per_subquestion_and_writes_all_triples():
    sq1 = SubQuestion(id="1", text="q1", search_results=[_search_result("https://a.com", "A", "c")])
    sq2 = SubQuestion(id="2", text="q2", search_results=[_search_result("https://b.com", "B", "c")])
    plan = ResearchPlan(topic="t", sub_questions=[sq1, sq2])

    response1 = LLMResponse(
        text='[{"subject":"X","relation":"r1","object":"Y","source_url":"https://a.com"}]',
        tool_calls=[], stop_reason="end_turn", usage=_usage(),
    )
    response2 = LLMResponse(
        text='[{"subject":"Y","relation":"r2","object":"Z","source_url":"https://b.com"}]',
        tool_calls=[], stop_reason="end_turn", usage=_usage(),
    )
    llm = ScriptedLLMClient([response1, response2])
    graph_store = FakeGraphStore()
    recorder = RunRecorder(variant="graphrag", topic="t")

    facts = build_graph(plan, llm, graph_store, recorder)

    assert graph_store.cleared is True
    assert graph_store.added == [
        ("X", "r1", "Y", "https://a.com"),
        ("Y", "r2", "Z", "https://b.com"),
    ]
    assert len(facts) == 2
    assert recorder.finalize().llm_calls == 2


def test_build_graph_no_sub_questions_still_clears_and_returns_empty():
    plan = ResearchPlan(topic="t", sub_questions=[])
    llm = ScriptedLLMClient([])
    graph_store = FakeGraphStore()
    recorder = RunRecorder(variant="graphrag", topic="t")

    facts = build_graph(plan, llm, graph_store, recorder)

    assert graph_store.cleared is True
    assert facts == []
    assert graph_store.added == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_graphrag_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research_assistant.variants.graphrag.run'`

- [ ] **Step 3: Implement `build_graph`**

Create `src/research_assistant/variants/graphrag/run.py`:

```python
from research_assistant.llm.base import LLMClient
from research_assistant.models import ResearchPlan, Triple
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.graphrag.extraction import extract_triples
from research_assistant.variants.graphrag.graph_store import Neo4jGraphStore


def build_graph(
    plan: ResearchPlan, llm: LLMClient, graph_store: Neo4jGraphStore, recorder: RunRecorder
) -> list[Triple]:
    graph_store.clear()
    for sub_question in plan.sub_questions:
        for triple in extract_triples(sub_question, llm, recorder):
            graph_store.add_triple(triple.subject, triple.relation, triple.object, triple.source_url)
    return graph_store.get_all_facts()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_graphrag_run.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (37 tests — 35 existing + 2 new)

- [ ] **Step 6: Commit**

```bash
git add src/research_assistant/variants/graphrag/run.py tests/unit/test_graphrag_run.py
git commit -m "feat: add graphrag graph-build orchestration"
```

---

### Task 5: Write phase and top-level `run()`

**Files:**
- Modify: `src/research_assistant/variants/graphrag/run.py` (append to the file from Task 4)
- Test: `tests/unit/test_graphrag_run.py` (append)

**Interfaces:**
- Consumes: `build_graph` (Task 4, same file); `Neo4jGraphStore` (Task 3); `build_source_list`, `format_sources_for_prompt` from `research_assistant.writing.citations`; `assemble_brief` from `research_assistant.writing.brief`; `get_settings` from `research_assistant.config`; `AnthropicLLMClient` from `research_assistant.llm.anthropic_client`; `TavilySearchTool` from `research_assistant.tools.search_tool`; `generate_plan`, `run_searches` from `research_assistant.variants.pipeline.run`.
- Produces: `BRIEF_SYSTEM_PROMPT: str`; `format_facts_for_prompt(facts: list[Triple], sources: list[Source]) -> str`; `write_brief(topic: str, facts: list[Triple], results: list[SearchResult], llm: LLMClient, recorder: RunRecorder) -> Brief`; `run(topic: str, recorder: RunRecorder | None = None) -> Brief` — consumed by Task 6's `VARIANT_REGISTRY`.

- [ ] **Step 1: Write the failing tests**

Add these imports to the top of `tests/unit/test_graphrag_run.py`, alongside the existing ones:

```python
from research_assistant.variants.graphrag.run import format_facts_for_prompt, write_brief
from research_assistant.writing.citations import build_source_list
```

Append these test functions at the end of the file:

```python
def test_format_facts_for_prompt_maps_source_url_to_citation_id():
    sources = build_source_list([_search_result("https://a.com", "A", "c")])
    facts = [Triple(subject="X", relation="r", object="Y", source_url="https://a.com")]

    assert format_facts_for_prompt(facts, sources) == "X -r-> Y [1]"


def test_format_facts_for_prompt_no_facts_returns_placeholder():
    assert format_facts_for_prompt([], []) == "No facts extracted."


def test_format_facts_for_prompt_unknown_source_url_omits_citation_marker():
    facts = [Triple(subject="X", relation="r", object="Y", source_url="https://unknown.com")]

    assert format_facts_for_prompt(facts, []) == "X -r-> Y"


def test_write_brief_produces_cited_markdown_with_sources_section():
    llm = ScriptedLLMClient(
        [LLMResponse(text="Napoleon was born in Corsica [1].", tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    results = [_search_result("https://a.com", "A", "c")]
    facts = [Triple(subject="Napoleon", relation="born_in", object="Corsica", source_url="https://a.com")]
    recorder = RunRecorder(variant="graphrag", topic="t")

    brief = write_brief("Napoleon", facts, results, llm, recorder)

    assert "Napoleon was born in Corsica [1]." in brief.markdown
    assert "## Sources" in brief.markdown
    assert brief.sources[0].url == "https://a.com"
    assert len(llm.calls) == 1
    assert llm.calls[0]["max_tokens"] == 2048


def test_write_brief_no_facts_still_produces_brief():
    llm = ScriptedLLMClient(
        [LLMResponse(text="No clear facts were found.", tool_calls=[], stop_reason="end_turn", usage=_usage())]
    )
    recorder = RunRecorder(variant="graphrag", topic="t")

    brief = write_brief("t", [], [], llm, recorder)

    assert brief.markdown.strip() != ""
    assert recorder.finalize().llm_calls == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_graphrag_run.py -v`
Expected: FAIL with `ImportError: cannot import name 'format_facts_for_prompt'`

- [ ] **Step 3: Implement the write phase and `run()`**

Append to `src/research_assistant/variants/graphrag/run.py` (add these imports at the top, alongside the existing ones):

```python
from research_assistant.config import get_settings
from research_assistant.llm.anthropic_client import AnthropicLLMClient
from research_assistant.llm.base import LLMMessage
from research_assistant.models import Brief, SearchResult, Source
from research_assistant.tools.search_tool import TavilySearchTool
from research_assistant.variants.pipeline.run import generate_plan, run_searches
from research_assistant.writing.brief import assemble_brief
from research_assistant.writing.citations import build_source_list, format_sources_for_prompt
```

Then append:

```python
BRIEF_SYSTEM_PROMPT = (
    "You are a research assistant writing a short brief. You will be given "
    "a topic, a set of facts extracted as a knowledge graph (in the form "
    "'Subject -relation-> Object [n]', where [n] is a citation number), and "
    "a numbered list of sources. Write a well-organized markdown brief (a "
    "few short paragraphs or bullet sections, no more than about one page) "
    "that synthesizes these facts into a coherent answer to the topic, "
    "including connections between entities where relevant. Cite claims "
    "using the exact bracketed numbers from the source list, e.g. [1] or "
    "[2][3], placed right after the claim they support. Do not include a "
    "'Sources' section yourself — it will be appended separately. Do not "
    "invent source numbers beyond what was given."
)


def format_facts_for_prompt(facts: list[Triple], sources: list[Source]) -> str:
    if not facts:
        return "No facts extracted."
    url_to_id = {s.url: s.id for s in sources}
    lines = []
    for fact in facts:
        citation_id = url_to_id.get(fact.source_url)
        marker = f" [{citation_id}]" if citation_id is not None else ""
        lines.append(f"{fact.subject} -{fact.relation}-> {fact.object}{marker}")
    return "\n".join(lines)


def write_brief(
    topic: str, facts: list[Triple], results: list[SearchResult], llm: LLMClient, recorder: RunRecorder
) -> Brief:
    sources = build_source_list(results)
    response = llm.complete(
        system=BRIEF_SYSTEM_PROMPT,
        messages=[
            LLMMessage(
                role="user",
                text=(
                    f"Topic: {topic}\n\n"
                    f"Facts:\n{format_facts_for_prompt(facts, sources)}\n\n"
                    f"Sources:\n{format_sources_for_prompt(sources)}"
                ),
            )
        ],
        max_tokens=2048,
    )
    recorder.record_llm_call(response.usage)
    return assemble_brief(topic, response.text or "", sources)


def run(topic: str, recorder: RunRecorder | None = None) -> Brief:
    settings = get_settings()
    if not (settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password):
        raise RuntimeError(
            "GraphRAG variant requires NEO4J_URI, NEO4J_USER, and "
            "NEO4J_PASSWORD in .env. Run `docker compose up -d` to start a "
            "local Neo4j instance, then set these to its connection details."
        )
    llm = AnthropicLLMClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    search_tool = TavilySearchTool(api_key=settings.tavily_api_key)
    recorder = recorder or RunRecorder(variant="graphrag", topic=topic)

    plan = generate_plan(topic, llm, recorder)
    plan = run_searches(plan, search_tool, recorder)

    graph_store = Neo4jGraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    try:
        facts = build_graph(plan, llm, graph_store, recorder)
    finally:
        graph_store.close()

    all_results = [r for sq in plan.sub_questions for r in sq.search_results]
    return write_brief(topic, facts, all_results, llm, recorder)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_graphrag_run.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (42 tests — 37 existing + 5 new)

- [ ] **Step 6: Commit**

```bash
git add src/research_assistant/variants/graphrag/run.py tests/unit/test_graphrag_run.py
git commit -m "feat: add graphrag write phase and top-level run()"
```

---

### Task 6: Register the variant

**Files:**
- Modify: `src/research_assistant/variants/__init__.py`
- Modify: `tests/unit/test_variant_registry.py`

**Interfaces:**
- Consumes: `run` from `research_assistant.variants.graphrag.run` (Task 5); existing `Variant` enum and `VARIANT_REGISTRY`.
- Produces: `Variant.graphrag` enum member; `VARIANT_REGISTRY[Variant.graphrag]` — consumed by `cli.py` (no code change needed there — it already looks up `VARIANT_REGISTRY[variant]` generically) and by the future web-app spec's `/variants` endpoint.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_variant_registry.py` (add the import alongside the existing one):

```python
from research_assistant.variants.graphrag.run import run as run_graphrag
```

Append:

```python
def test_graphrag_variant_is_registered():
    assert Variant.graphrag in VARIANT_REGISTRY
    assert VARIANT_REGISTRY[Variant.graphrag] is run_graphrag
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/unit/test_variant_registry.py -v`
Expected: FAIL with `AttributeError: graphrag` (no such member on `Variant`)

- [ ] **Step 3: Register the variant**

Replace the contents of `src/research_assistant/variants/__init__.py`:

```python
from collections.abc import Callable
from enum import Enum

from research_assistant.models import Brief
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.agentic.run import run as run_agentic
from research_assistant.variants.graphrag.run import run as run_graphrag
from research_assistant.variants.pipeline.run import run as run_pipeline


class Variant(str, Enum):
    pipeline = "pipeline"
    agentic = "agentic"
    graphrag = "graphrag"


VARIANT_REGISTRY: dict[Variant, Callable[[str, RunRecorder | None], Brief]] = {
    Variant.pipeline: run_pipeline,
    Variant.agentic: run_agentic,
    Variant.graphrag: run_graphrag,
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/unit/test_variant_registry.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (43 tests — 42 existing + 1 new)

- [ ] **Step 6: Commit**

```bash
git add src/research_assistant/variants/__init__.py tests/unit/test_variant_registry.py
git commit -m "feat: register graphrag variant in VARIANT_REGISTRY

research-assistant run <topic> --variant graphrag now works via the
existing CLI, no cli.py changes needed."
```

---

### Task 7: Local Neo4j + live integration test

**Files:**
- Create: `docker-compose.yml`
- Modify: `.env.example`
- Create: `tests/live/test_graphrag_live.py`

**Interfaces:**
- Consumes: `run` from `research_assistant.variants.graphrag.run` (Task 6); `get_settings` from `research_assistant.config`.
- Produces: nothing consumed elsewhere — this is a leaf integration test and local-infra setup, mirroring `tests/live/test_pipeline_live.py`/`tests/live/test_agentic_live.py`.

- [ ] **Step 1: Create the Docker Compose file**

Create `docker-compose.yml` at the repo root:

```yaml
services:
  neo4j:
    image: neo4j:5
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/researchassistant
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

- [ ] **Step 2: Add Neo4j vars to `.env.example`**

Append to `.env.example`:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=researchassistant
```

- [ ] **Step 3: Create the live test**

Create `tests/live/test_graphrag_live.py`:

```python
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
```

Note: `_settings_available()` here extends the pattern used in the other two live tests (`test_pipeline_live.py`, `test_agentic_live.py`) with an extra check for the Neo4j vars specifically, since this variant needs them and the others don't. This is a deliberate, small divergence from those two files' otherwise-identical helper — not a duplication bug, a different variant's live test needs a different check.

- [ ] **Step 4: Run it (only if you have `docker compose up -d` running and `.env` fully configured — this makes real, billed API calls)**

Run: `uv run python -m pytest tests/live/test_graphrag_live.py -m live -v`
Expected: PASS if Neo4j is running and `.env` has real keys, or SKIPPED with the stated reason otherwise. Either outcome is fine to commit on — this test is opt-in by design and isn't part of the default `pytest` run (`addopts = "-m 'not live'"`).

- [ ] **Step 5: Run the full unit suite (sanity check — this task touches no unit-tested code)**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS, 43 tests (unchanged from Task 6)

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml .env.example tests/live/test_graphrag_live.py
git commit -m "feat: add local Neo4j compose file and graphrag live test"
```

---

### Task 8: Full regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS, 43 tests

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check src tests`
Expected: no errors. If ruff reports anything, run `uv run ruff check src tests --fix` and re-check; for anything it can't auto-fix, resolve per its message.

- [ ] **Step 3: Commit if ruff's `--fix` changed anything**

```bash
git add -u
git commit -m "style: ruff fixes"
```

(Skip this step entirely if Step 2 reported no errors and nothing changed.)

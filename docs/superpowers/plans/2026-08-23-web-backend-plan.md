# Web Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastAPI backend (`src/research_assistant/web/`) that wraps `VARIANT_REGISTRY` behind a submit-and-poll HTTP API, plus a `research-assistant serve` CLI command to run it locally — so any variant can be run and its `RunRecorder` trace inspected from outside the CLI.

**Architecture:** A tiny in-memory job store (`runs.py`) tracks each run by id (`running`/`done`/`error`); a background-thread execution function calls the existing synchronous variant `run()` functions without blocking the event loop; three routes (`app.py`) expose create/poll/list. `Variant` and `VARIANT_REGISTRY` are consumed as-is — no changes to any existing variant code.

**Tech Stack:** FastAPI, uvicorn (new `api` extra), httpx (added to the existing `dev` extra, needed by FastAPI's `TestClient`), Python 3.11+, existing `research_assistant` package.

**Spec:** `docs/superpowers/specs/2026-08-23-web-app-design.md` (this plan implements only the backend half — sections describing the React/Vite frontend are out of scope here and get their own follow-up plan once this backend exists to build against)

## Global Constraints

- No new research capability — the web layer only wraps `VARIANT_REGISTRY[variant](topic, recorder)`; it never changes how any variant researches a topic.
- No persistence beyond the running process — runs live in an in-memory `dict`; restarting the server clears them.
- No auth, binds to `127.0.0.1` only (not `0.0.0.0`) — this proxies your Anthropic/Tavily API key usage, no reason to expose it to the local network.
- No live streaming of in-progress steps — submit-and-poll only (`POST /runs` returns a `run_id`, `GET /runs/{run_id}` polls status).
- `GET /variants` derives its list directly from `VARIANT_REGISTRY` — no hardcoded "coming soon" list to keep in sync manually. Adding a variant to the registry makes it appear here automatically.
- CORS allows only `http://localhost:5173` (the Vite dev server's default port) — not a wildcard.
- A variant failure (any exception) is always caught and stored as `status="error"` with the exception's message — a run must never get stuck at `status="running"` forever.
- Every commit uses `uv run python -m pytest tests/unit -q` to verify, not bare `uv run pytest` (this machine's PATH resolves the latter to a different pytest off the venv).

---

## File Structure

- `src/research_assistant/web/__init__.py` — **create.** Empty package marker.
- `src/research_assistant/web/schemas.py` — **create.** `RunRequest`, `RunRecord`.
- `src/research_assistant/web/runs.py` — **create.** In-memory run store: `start_run`, `execute_run`, `get_run`, `list_runs`.
- `src/research_assistant/web/app.py` — **create.** FastAPI app, CORS, 3 routes.
- `src/research_assistant/cli.py` — **modify.** Add a `serve` command.
- `pyproject.toml` — **modify.** New `api` extra (`fastapi`, `uvicorn`); add `httpx` to the existing `dev` extra (needed by FastAPI's `TestClient`).
- `tests/unit/test_web_schemas.py` — **create.**
- `tests/unit/test_web_runs.py` — **create.**
- `tests/unit/test_web_app.py` — **create.**
- `tests/unit/test_cli_serve.py` — **create.**

---

### Task 1: Web-layer schemas

**Files:**
- Create: `src/research_assistant/web/__init__.py`
- Create: `src/research_assistant/web/schemas.py`
- Test: `tests/unit/test_web_schemas.py`

**Interfaces:**
- Consumes: `Brief` from `research_assistant.models`; `RunTrace` from `research_assistant.tracing.recorder`; `Variant` from `research_assistant.variants`.
- Produces: `RunRequest(topic: str, variant: Variant)`; `RunRecord(run_id: str, status: Literal["running", "done", "error"], topic: str, variant: Variant, created_at: datetime, brief: Brief | None = None, trace: RunTrace | None = None, error: str | None = None)` — both consumed by every later task in this plan.

- [ ] **Step 1: Create the package marker**

Create `src/research_assistant/web/__init__.py` (empty file).

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_web_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from research_assistant.variants import Variant
from research_assistant.web.schemas import RunRecord, RunRequest


def test_run_record_optional_fields_default_to_none():
    record = RunRecord(
        run_id="abc123",
        status="running",
        topic="a topic",
        variant=Variant.pipeline,
        created_at="2026-08-23T12:00:00Z",
    )
    assert record.brief is None
    assert record.trace is None
    assert record.error is None


def test_run_request_rejects_unknown_variant():
    with pytest.raises(ValidationError):
        RunRequest(topic="a topic", variant="not-a-real-variant")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_web_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research_assistant.web.schemas'`

- [ ] **Step 4: Implement the schemas**

Create `src/research_assistant/web/schemas.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from research_assistant.models import Brief
from research_assistant.tracing.recorder import RunTrace
from research_assistant.variants import Variant


class RunRequest(BaseModel):
    topic: str
    variant: Variant


class RunRecord(BaseModel):
    run_id: str
    status: Literal["running", "done", "error"]
    topic: str
    variant: Variant
    created_at: datetime
    brief: Brief | None = None
    trace: RunTrace | None = None
    error: str | None = None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_web_schemas.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (45 tests — 43 existing + 2 new)

- [ ] **Step 7: Commit**

```bash
git add src/research_assistant/web/__init__.py src/research_assistant/web/schemas.py tests/unit/test_web_schemas.py
git commit -m "feat: add web-layer request/response schemas"
```

---

### Task 2: In-memory run store

**Files:**
- Create: `src/research_assistant/web/runs.py`
- Test: `tests/unit/test_web_runs.py`

**Interfaces:**
- Consumes: `RunRecord` (Task 1); `RunRecorder` from `research_assistant.tracing.recorder`; `VARIANT_REGISTRY`, `Variant` from `research_assistant.variants`.
- Produces: `start_run(topic: str, variant: Variant) -> str`; `execute_run(run_id: str, topic: str, variant: Variant) -> None`; `get_run(run_id: str) -> RunRecord | None`; `list_runs() -> list[RunRecord]` — all consumed by Task 3's routes.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_web_runs.py`:

```python
import pytest

import research_assistant.web.runs as runs_module
from research_assistant.llm.base import LLMUsage
from research_assistant.models import Brief
from research_assistant.variants import VARIANT_REGISTRY, Variant
from research_assistant.web.runs import execute_run, get_run, list_runs, start_run


@pytest.fixture(autouse=True)
def _clear_runs():
    runs_module._runs.clear()
    yield
    runs_module._runs.clear()


def _fake_run(topic, recorder):
    recorder.record_llm_call(LLMUsage(input_tokens=5, output_tokens=3))
    return Brief(topic=topic, markdown="# Brief", sources=[])


def _failing_run(topic, recorder):
    raise RuntimeError("boom")


def test_start_run_creates_running_record():
    run_id = start_run("a topic", Variant.pipeline)
    record = get_run(run_id)
    assert record.status == "running"
    assert record.topic == "a topic"
    assert record.variant == Variant.pipeline
    assert record.brief is None


def test_start_run_generates_unique_run_ids():
    first = start_run("topic one", Variant.pipeline)
    second = start_run("topic two", Variant.pipeline)
    assert first != second


def test_execute_run_success_updates_to_done_with_brief_and_trace(monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _fake_run)
    run_id = start_run("a topic", Variant.pipeline)

    execute_run(run_id, "a topic", Variant.pipeline)

    record = get_run(run_id)
    assert record.status == "done"
    assert record.brief.markdown == "# Brief"
    assert record.trace.llm_calls == 1
    assert record.error is None


def test_execute_run_failure_updates_to_error_with_message(monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _failing_run)
    run_id = start_run("a topic", Variant.pipeline)

    execute_run(run_id, "a topic", Variant.pipeline)

    record = get_run(run_id)
    assert record.status == "error"
    assert record.error == "boom"
    assert record.brief is None


def test_get_run_unknown_id_returns_none():
    assert get_run("does-not-exist") is None


def test_list_runs_sorted_most_recent_first(monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _fake_run)
    first_id = start_run("first", Variant.pipeline)
    execute_run(first_id, "first", Variant.pipeline)
    second_id = start_run("second", Variant.pipeline)
    execute_run(second_id, "second", Variant.pipeline)

    ids = [r.run_id for r in list_runs()]
    assert ids.index(second_id) < ids.index(first_id)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_web_runs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research_assistant.web.runs'`

- [ ] **Step 3: Implement the run store**

Create `src/research_assistant/web/runs.py`:

```python
import uuid
from datetime import datetime, timezone

from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants import VARIANT_REGISTRY, Variant
from research_assistant.web.schemas import RunRecord

_runs: dict[str, RunRecord] = {}


def start_run(topic: str, variant: Variant) -> str:
    run_id = str(uuid.uuid4())[:8]
    _runs[run_id] = RunRecord(
        run_id=run_id,
        status="running",
        topic=topic,
        variant=variant,
        created_at=datetime.now(timezone.utc),
    )
    return run_id


def execute_run(run_id: str, topic: str, variant: Variant) -> None:
    record = _runs[run_id]
    try:
        recorder = RunRecorder(variant=variant.value, topic=topic)
        run_fn = VARIANT_REGISTRY[variant]
        brief = run_fn(topic, recorder)
        _runs[run_id] = record.model_copy(
            update={"status": "done", "brief": brief, "trace": recorder.finalize()}
        )
    except Exception as exc:  # noqa: BLE001 - any variant failure surfaces to the UI
        _runs[run_id] = record.model_copy(update={"status": "error", "error": str(exc)})


def get_run(run_id: str) -> RunRecord | None:
    return _runs.get(run_id)


def list_runs() -> list[RunRecord]:
    return sorted(_runs.values(), key=lambda r: r.created_at, reverse=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_web_runs.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (51 tests — 45 existing + 6 new)

- [ ] **Step 6: Commit**

```bash
git add src/research_assistant/web/runs.py tests/unit/test_web_runs.py
git commit -m "feat: add in-memory run store for the web backend"
```

---

### Task 3: FastAPI app and routes

**Files:**
- Modify: `pyproject.toml` (add `api` extra; add `httpx` to `dev`)
- Create: `src/research_assistant/web/app.py`
- Test: `tests/unit/test_web_app.py`

**Interfaces:**
- Consumes: `RunRequest`, `RunRecord` (Task 1); `start_run`, `execute_run`, `get_run`, `list_runs` (Task 2); `VARIANT_REGISTRY` from `research_assistant.variants`.
- Produces: `app` (a `FastAPI` instance) at module level in `research_assistant.web.app` — consumed by Task 4's `serve` command (via the string `"research_assistant.web.app:app"` passed to uvicorn).

- [ ] **Step 1: Add the `api` extra and `httpx`, then sync**

In `pyproject.toml`, add `"httpx>=0.27"` to the existing `dev` list:

```toml
dev = [
    "pytest>=8",
    "pytest-mock>=3",
    "ruff>=0.8",
    "httpx>=0.27",
]
```

Add a new table after the existing `graphrag` extra:

```toml
api = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
]
```

Run: `uv sync --extra dev --extra api --extra graphrag`
Expected: installs `fastapi`, `uvicorn`, `httpx` into the venv (keeping `graphrag`'s `neo4j` too, since this repo's full test suite needs all extras synced together — same pattern established for the graphrag variant).

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_web_app.py`:

```python
import pytest
from fastapi.testclient import TestClient

import research_assistant.web.runs as runs_module
from research_assistant.llm.base import LLMUsage
from research_assistant.models import Brief
from research_assistant.variants import VARIANT_REGISTRY, Variant
from research_assistant.web.app import app


@pytest.fixture(autouse=True)
def _clear_runs():
    runs_module._runs.clear()
    yield
    runs_module._runs.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _fake_run(topic, recorder):
    recorder.record_llm_call(LLMUsage(input_tokens=5, output_tokens=3))
    return Brief(topic=topic, markdown="# Brief", sources=[])


def _failing_run(topic, recorder):
    raise RuntimeError("boom")


def test_get_variants_lists_registered_variants(client):
    response = client.get("/variants")
    assert response.status_code == 200
    names = response.json()
    assert "pipeline" in names
    assert "agentic" in names


def test_create_run_then_poll_returns_done_with_brief(client, monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _fake_run)

    create_response = client.post("/runs", json={"topic": "t", "variant": "pipeline"})
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    poll_response = client.get(f"/runs/{run_id}")
    assert poll_response.status_code == 200
    body = poll_response.json()
    assert body["status"] == "done"
    assert body["brief"]["markdown"] == "# Brief"
    assert body["trace"]["llm_calls"] == 1


def test_create_run_that_fails_returns_error_status(client, monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _failing_run)

    create_response = client.post("/runs", json={"topic": "t", "variant": "pipeline"})
    run_id = create_response.json()["run_id"]

    poll_response = client.get(f"/runs/{run_id}")
    body = poll_response.json()
    assert body["status"] == "error"
    assert body["error"] == "boom"


def test_get_unknown_run_returns_404(client):
    response = client.get("/runs/does-not-exist")
    assert response.status_code == 404


def test_create_run_with_invalid_variant_returns_422(client):
    response = client.post("/runs", json={"topic": "t", "variant": "not-a-real-variant"})
    assert response.status_code == 422


def test_list_runs_returns_all_created_runs(client, monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _fake_run)
    create_response = client.post("/runs", json={"topic": "t", "variant": "pipeline"})
    run_id = create_response.json()["run_id"]

    list_response = client.get("/runs")
    assert list_response.status_code == 200
    ids = [r["run_id"] for r in list_response.json()]
    assert run_id in ids
```

Note: `TestClient` runs FastAPI's `BackgroundTasks` synchronously as part of the request/response cycle, so by the time `client.post("/runs", ...)` returns, the background-scheduled `execute_run` has already completed — no polling loop or sleep is needed in these tests, a single immediate `client.get` afterward already sees the final status.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_web_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'research_assistant.web.app'`

- [ ] **Step 4: Implement the app**

Create `src/research_assistant/web/app.py`:

```python
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from research_assistant.variants import VARIANT_REGISTRY
from research_assistant.web.runs import execute_run, get_run, list_runs, start_run
from research_assistant.web.schemas import RunRecord, RunRequest

app = FastAPI(title="research-assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/variants")
def variants() -> list[str]:
    return [v.value for v in VARIANT_REGISTRY]


@app.post("/runs")
def create_run(request: RunRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    run_id = start_run(request.topic, request.variant)
    background_tasks.add_task(execute_run, run_id, request.topic, request.variant)
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def read_run(run_id: str) -> RunRecord:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@app.get("/runs")
def read_runs() -> list[RunRecord]:
    return list_runs()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_web_app.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (57 tests — 51 existing + 6 new)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/research_assistant/web/app.py tests/unit/test_web_app.py
git commit -m "feat: add FastAPI app with variants/runs routes"
```

---

### Task 4: `serve` CLI command

**Files:**
- Modify: `src/research_assistant/cli.py`
- Test: `tests/unit/test_cli_serve.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks in this plan directly — references the app via the string `"research_assistant.web.app:app"` (uvicorn's own import-string convention, not a Python import), so this task has no hard import-time dependency on Task 3's module beyond that string being correct.
- Produces: `serve(port: int = 8000)` — a new Typer command on the existing `research_assistant.cli.app`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_cli_serve.py`:

```python
from typer.testing import CliRunner

from research_assistant.cli import app

runner = CliRunner()


def test_serve_command_calls_uvicorn_run_with_default_port(monkeypatch):
    captured = {}

    def fake_run(app_path, host, port):
        captured["app_path"] = app_path
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0
    assert captured["app_path"] == "research_assistant.web.app:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000


def test_serve_command_respects_custom_port(monkeypatch):
    captured = {}

    def fake_run(app_path, host, port):
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = runner.invoke(app, ["serve", "--port", "9000"])

    assert result.exit_code == 0
    assert captured["port"] == 9000
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/unit/test_cli_serve.py -v`
Expected: FAIL — `AssertionError`/`KeyError` (no `serve` command exists yet, so `result.exit_code` won't be 0 and `captured` stays empty)

- [ ] **Step 3: Add the `serve` command**

In `src/research_assistant/cli.py`, add this command after the existing `run` command (before the `if __name__ == "__main__":` block):

```python
@app.command()
def serve(port: int = 8000) -> None:
    """Run the web backend locally (binds to 127.0.0.1 only)."""
    import uvicorn

    uvicorn.run("research_assistant.web.app:app", host="127.0.0.1", port=port)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/unit/test_cli_serve.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS (59 tests — 57 existing + 2 new)

- [ ] **Step 6: Commit**

```bash
git add src/research_assistant/cli.py tests/unit/test_cli_serve.py
git commit -m "feat: add serve CLI command for the web backend"
```

---

### Task 5: Full regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS, 59 tests

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check src tests`
Expected: no errors. If ruff reports anything, run `uv run ruff check src tests --fix` and re-check; for anything it can't auto-fix, resolve per its message.

- [ ] **Step 3: Commit if ruff's `--fix` changed anything**

```bash
git add -u
git commit -m "style: ruff fixes"
```

(Skip this step entirely if Step 2 reported no errors and nothing changed.)

- [ ] **Step 4: Manual smoke check — start the server and hit it for real**

Run: `uv run research-assistant serve` (leave it running in one terminal)

In another terminal (or via `curl`):
```bash
curl http://127.0.0.1:8000/variants
```
Expected: a JSON array containing `"pipeline"`, `"agentic"`, and (if the graphrag variant is registered) `"graphrag"`.

This isn't an automated test — it's a one-time sanity check that the server actually starts and responds, which none of the unit tests (they only exercise the FastAPI `app` object via `TestClient`, never a real running server) verify. Stop the server (Ctrl+C) once confirmed.

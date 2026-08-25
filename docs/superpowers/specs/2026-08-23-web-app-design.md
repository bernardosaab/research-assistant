# Web backend + frontend — design

## Purpose

`research-assistant` is CLI-only today (`research-assistant run <topic>
--variant <name>`). This spec adds a browser interface: a FastAPI backend
wrapping the existing `VARIANT_REGISTRY`, and a React frontend to submit a
topic, watch a run complete, read the resulting `Brief`, and compare
`RunRecorder` traces across runs — the trace data already exists on every
run today but nothing surfaces it anywhere, CLI included.

## Non-goals

- No new research capability. The web layer is a thin wrapper around
  `VARIANT_REGISTRY[variant](topic, recorder)` — it does not change how any
  variant researches a topic.
- No persistence beyond the running process. Runs live in an in-memory
  store for comparison within a session; restarting the server clears them.
  Consistent with the rest of this project's local-dev-tool scope (e.g. the
  GraphRAG variant's per-run graph rebuild, for the same reason: this isn't
  a hosted service with uptime or durability guarantees).
- No auth, no multi-user concerns. Binds to `127.0.0.1` only.
- No live streaming of in-progress steps (round N of 8, which sub-question
  is searching now). Considered and explicitly rejected: the variant
  `run()` functions emit no intermediate events today, and adding that
  would mean threading an event-hook mechanism through all three variants
  just for the web layer's benefit. Submit-and-poll only.
- Does not require or block on the GraphRAG variant being built. `/variants`
  reflects whatever `VARIANT_REGISTRY` currently contains — see "Variant
  discovery" below.

## Design

### File layout

- `src/research_assistant/web/__init__.py`
- `src/research_assistant/web/app.py` — the FastAPI app, three routes (no
  CORS middleware — see "Frontend↔backend connection" below for why)
- `src/research_assistant/web/runs.py` — in-memory run store + the
  background execution function
- `src/research_assistant/web/schemas.py` — `RunRecord`, `RunRequest`
  (web-layer Pydantic models; the existing domain models — `Brief`,
  `Source`, `RunTrace` — are reused inside them, not duplicated)
- `src/research_assistant/cli.py` — add a `serve` command
- `pyproject.toml` — new `api` extra: `fastapi`, `uvicorn`
- `web/` (repo root, sibling to `src/`) — the React/Vite frontend, its own
  `package.json`:
  - `web/vite.config.ts` — dev-server proxy config (see below)
  - `web/src/App.tsx` — routes the three views
  - `web/src/RunForm.tsx` — topic input + variant picker
  - `web/src/useRunPolling.ts` — polls `GET /api/runs/{id}` until done/error
  - `web/src/BriefView.tsx` — renders the markdown brief + sources
  - `web/src/TraceCompare.tsx` — chart comparing traces across this
    session's completed runs

### Frontend↔backend connection — resolved 2026-08-25

Earlier drafts of this spec were self-contradictory: they mandated CORS
restricted to `http://localhost:5173` *and* described a Vite dev-server
proxy from `/api` to the backend — mutually exclusive (a proxy makes every
request same-origin, making CORS irrelevant; the proxy as described would
also have 404'd, since backend routes are mounted at root, e.g. `/variants`,
not under `/api/variants`).

**Decision: Vite dev-server proxy.** The frontend calls relative paths like
`/api/variants` and `/api/runs`; Vite's dev server rewrites and forwards
`/api/*` to `http://127.0.0.1:8000/*` (stripping the `/api` prefix). The
browser only ever talks to `:5173` — no cross-origin request ever happens.
Consequently, **the backend's `CORSMiddleware` is dead code and gets
removed** from the already-merged `app.py` as part of implementing this
(the backend shipped with it before this decision was made, since at the
time either resolution was still open).

```typescript
// web/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
```

### Variant discovery — no hardcoded "coming soon" list

`GET /variants` returns `list(VARIANT_REGISTRY.keys())` mapped to their
string values — nothing more. Today that's `["pipeline", "agentic"]`.
GraphRAG does not appear as a disabled/greyed option; it simply isn't in
the list until its own implementation plan registers `Variant.graphrag` in
`VARIANT_REGISTRY`, at which point it appears in the picker automatically,
with zero changes to the web layer. (This corrects the "graphrag shows
disabled with a tooltip" framing from the chat design — that would have
meant hand-maintaining a second list of variants of the web layer, which
duplicates `VARIANT_REGISTRY` as a source of truth and goes stale the
moment the roadmap changes. Deriving the list directly from the registry
avoids that entirely.)

### Data flow

**1. Schemas (`web/schemas.py`):**

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

`variant: Variant` on `RunRequest` means FastAPI/Pydantic validates the
variant string automatically — an unknown variant name is a 422 before any
application code runs, no hand-written validation needed.

**2. Run store + execution (`web/runs.py`):**

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
        run_id=run_id, status="running", topic=topic, variant=variant,
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

**Every store update replaces the whole `RunRecord`** (`model_copy`) rather
than mutating fields in place. Combined with CPython's GIL making a single
`dict[key] = value` assignment atomic, this needs no explicit lock even
though `execute_run` runs in a background thread while request handlers
read concurrently — there's no window where a reader sees a half-updated
record.

**Every variant failure is caught and stored as `status="error"`.**
FastAPI's `BackgroundTasks` logs an unhandled exception and moves on — it
does not update anything for you. Without the try/except, a failing run
(e.g. GraphRAG's own `RuntimeError` for missing Neo4j config, or any
Anthropic/Tavily API error) would leave its `RunRecord` stuck at
`status="running"` forever, and the frontend would poll indefinitely with
no way to know something went wrong.

**3. App + routes (`web/app.py`):**

```python
from fastapi import BackgroundTasks, FastAPI, HTTPException

from research_assistant.variants import VARIANT_REGISTRY
from research_assistant.web.runs import execute_run, get_run, list_runs, start_run
from research_assistant.web.schemas import RunRecord, RunRequest

app = FastAPI(title="research-assistant")


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

A sync function passed to `background_tasks.add_task` runs in Starlette's
thread pool, not the event loop — so the blocking, synchronous variant
`run()` calls (real network calls to Anthropic/Tavily) don't block other
requests from being served while a run is in progress.

**4. CLI integration** — `cli.py` gains:

```python
@app.command()
def serve(port: int = 8000) -> None:
    """Run the web backend locally (binds to 127.0.0.1 only)."""
    import uvicorn
    uvicorn.run("research_assistant.web.app:app", host="127.0.0.1", port=port)
```

Binding to `127.0.0.1` rather than `0.0.0.0` is deliberate: this proxies
your Anthropic/Tavily API keys' usage to whatever hits it, and there's no
reason to expose that to the local network for a personal dev tool.

**5. Frontend flow:** `RunForm` submits `POST /api/runs`, gets a `run_id`,
hands it to `useRunPolling` which calls `GET /api/runs/{run_id}` every ~2s
until `status !== "running"`. On `"done"`, `BriefView` renders
`record.brief.markdown` + sources. On `"error"`, the form surfaces
`record.error` directly (it's already a plain string message, not a stack
trace, thanks to the variants' own error handling — e.g. GraphRAG's
`RuntimeError` about missing `.env` config). `TraceCompare` calls
`GET /api/runs` and charts `trace.llm_calls` / `search_calls` / `input_tokens`
+ `output_tokens` / `duration_seconds` across whichever runs in the list
have `status === "done"`, grouped by `variant`. All frontend fetches use
the `/api/...`-prefixed relative path — Vite's proxy (above) handles the
rest; the frontend code never hardcodes `http://127.0.0.1:8000` anywhere.

### Local dev

Two processes, no new Docker orchestration (Compose stays scoped to Neo4j,
per the GraphRAG spec):

```
uv sync --extra dev --extra api
uv run research-assistant serve        # backend on :8000

cd web && npm install && npm run dev   # frontend on :5173, proxies /api -> :8000
```

### Testing

- **Backend:** FastAPI's `TestClient` against the three routes, with
  `VARIANT_REGISTRY` monkeypatched to a fake `run` function — same
  dependency-injection-for-testability pattern already used throughout this
  codebase (the agentic variant's fake `LLMClient`/`TavilySearchTool`).
  Covers: run creation, polling before/after completion, the 404 for an
  unknown `run_id`, and a variant that raises surfacing as `status="error"`
  with the exception message.
- **Frontend:** Vitest + React Testing Library for `RunForm` (submits the
  right payload), `useRunPolling` (stops polling on done/error, doesn't
  poll forever), and `BriefView`/`TraceCompare` rendering against fixture
  `RunRecord` JSON.

## Success criteria

- `research-assistant serve` + `npm run dev` is sufficient to use every
  built variant from a browser — no other local infrastructure beyond what
  each variant itself already needs (e.g. GraphRAG still needs its own
  `docker compose up -d` for Neo4j, unchanged by this spec).
- A failed run surfaces its actual error message in the UI, never leaves
  the frontend polling forever.
- Adding a new variant to `VARIANT_REGISTRY` makes it appear in the web UI
  with zero web-layer code changes.

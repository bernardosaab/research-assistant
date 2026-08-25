# research-assistant

A research assistant that plans, searches, reads, and writes a short brief —
built multiple ways to compare agentic architectures against the same task,
using `RunRecorder` traces (LLM calls, tokens, duration, search calls) to
compare them.

## Setup

```
uv sync --extra dev        # base deps + pytest/pytest-mock/ruff
uv sync --extra notebook   # only needed for tokenizer_analysis.ipynb
uv sync --extra graphrag   # only needed to run `--variant graphrag`
uv sync --extra api        # only needed to run the web backend (`research-assistant serve`)
cp .env.example .env       # fill in ANTHROPIC_API_KEY / TAVILY_API_KEY
```

Run tests with `uv run python -m pytest` (not bare `uv run pytest` — on this
machine that resolves to an Anaconda pytest on PATH instead of the venv's).
Live tests that hit real APIs are marked `live` and excluded by default
(`addopts = "-m 'not live'"` in pyproject.toml).

To run the web app locally (two processes, no Docker beyond what GraphRAG
already needs):

```
uv sync --extra api
uv run research-assistant serve        # backend on :8000

cd web && npm install && npm run dev   # frontend on :5173, proxies /api -> :8000
```

## Architecture

- `models.py` — Pydantic domain models: `SearchResult`, `Source`,
  `SubQuestion`, `ResearchPlan`, `Brief`, `Triple`.
- `llm/base.py` — `LLMClient` Protocol + `LLMMessage`/`ToolDef`/`ToolCall`/
  `ToolResult`/`LLMResponse`. Already supports tool-use, in anticipation of
  an agentic variant.
- `llm/anthropic_client.py` — the only `LLMClient` implementation so far.
- `tools/search_tool.py` — `TavilySearchTool`.
- `tracing/recorder.py` — `RunRecorder`, produces a `RunTrace` (variant,
  topic, duration, llm_calls, search_calls, tokens) per run, for comparing
  variants against each other.
- `writing/` — `assemble_brief` and citation formatting/numbering.
- `variants/` — one module per architecture, each exposing a
  `run(topic, recorder) -> Brief` function, registered in
  `variants/__init__.py`'s `VARIANT_REGISTRY` keyed by the `Variant` enum.
  - `variants/pipeline/run.py` — **implemented.** Fixed 4-step pipeline:
    `generate_plan` → `run_searches` → `extract_findings` → `write_brief`,
    each a separate non-tool-use LLM call.
  - `variants/agentic/run.py` — **implemented.** ReAct-style single-agent
    tool loop (LLM drives its own `web_search` calls up to an 8-round cap,
    then a separate write pass), hand-rolled on the existing
    `LLMClient`/`ToolDef`/`ToolCall` plumbing. Design:
    `docs/superpowers/specs/2026-08-23-agentic-tool-loop-variant-design.md`.
  - **GraphRAG retrieval variant — implemented.** A different axis than
    the others: retrieval *strategy* rather than orchestration
    control-flow. Search results get extracted into a knowledge graph
    (entities + relationships) in a local Neo4j instance (wiped and
    rebuilt every run — no cross-run persistence, so `RunRecorder` traces
    stay comparable to the other variants), queried back as a flat fact
    list for the write phase. Simplified GraphRAG (no community
    detection/summarization — see spec for why). Design:
    `docs/superpowers/specs/2026-08-23-graphrag-variant-design.md`.
  - **plan-execute-reflect variant — not started.** Per the original
    4-variant plan: explicit planner produces a structured plan, an executor
    works through steps, a reflection step checks sufficiency and can loop
    before the final write. Decided 2026-08-23: implement this on
    **Google ADK** (Agent Development Kit) rather than hand-rolled, to
    compare framework-provided vs. hand-rolled orchestration for the same
    control flow. ADK specifics (API shape, current version) need
    verification against its docs when this is picked up.
  - **multi-agent orchestration variant — not started.** Per the original
    4-variant plan: a lead/orchestrator agent delegates sub-questions to
    parallel researcher subagents, then a writer agent synthesizes findings.
    Decided 2026-08-23: also implement on **Google ADK**, same rationale as
    above.
- `cli.py` — Typer CLI: `research-assistant run <topic> --variant <name>
  --output <path>`. Also has a `serve` command now, which runs the FastAPI
  web backend locally (binds to `127.0.0.1` only).
- `web/` — **implemented.** A FastAPI backend (`src/research_assistant/web/`,
  with `schemas.py`, `runs.py`, `app.py`) wrapping `VARIANT_REGISTRY` behind
  a submit-and-poll HTTP API, plus a React/Vite frontend (`web/`, its own
  `package.json`) to submit a topic, watch a run complete, read the
  resulting `Brief`, and compare `RunRecorder` traces across runs from a
  browser — the frontend talks to the backend only through a Vite dev-server
  proxy (`/api/* -> 127.0.0.1:8000`), never cross-origin. In-memory only, no
  persistence beyond the process, binds to `127.0.0.1` only. Design:
  `docs/superpowers/specs/2026-08-23-web-app-design.md`.

## Status

Pipeline, agentic, and graphrag variants are implemented with unit test
coverage and `live` integration tests. The web app — FastAPI backend and
React/Vite frontend — is now implemented and tested end to end.
`tokenizer_analysis.ipynb` is a separate, finished, self-contained notebook
(domain-specific tokenizer fragmentation) unrelated to the CLI app.

Roadmap (in rough order): plan-execute-reflect on Google ADK →
multi-agent orchestration on Google ADK. Each gets its own
brainstorming → spec → plan cycle when picked up; neither is designed yet
beyond this roadmap note.

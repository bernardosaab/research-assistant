# research-assistant

A research assistant that **plans → searches → reads → writes a short brief**
on a topic — implemented three different ways against the same task, so the
underlying agentic architectures can be compared head-to-head rather than
taken on faith. Every run is traced (LLM calls, tokens, search calls,
duration) through a shared `RunRecorder`, and a small web app lets you submit
a topic, watch a run complete, read the resulting brief, and compare traces
across runs and variants — from a browser or the CLI.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the solution design,
the reasoning behind each variant, and the architectural decisions and
trade-offs behind the web layer.

## The three variants

| Variant | Control flow | What it's comparing |
|---|---|---|
| `pipeline` | Fixed 4-step sequence: plan → search → extract findings → write. Each step is one non-tool-use LLM call. | The baseline: an explicit, deterministic orchestration with no agent judgment in the loop. |
| `agentic` | Single ReAct-style agent that drives its own `web_search` tool calls (up to 8 rounds) until it decides it has enough, then a separate write pass. | Hand-rolled tool-use orchestration vs. the fixed pipeline — same task, agent decides *when* and *what* to search. |
| `graphrag` | Same plan/search steps as `pipeline`, but search results are extracted into a knowledge graph (entities + relationships) in Neo4j, wiped and rebuilt per run, then queried back as a flat fact list for the write step. | A different axis: retrieval *strategy* rather than orchestration control-flow. |

All three share one interface — `run(topic, recorder) -> Brief` — registered
in `VARIANT_REGISTRY`, so the CLI, the web API, and any future variant treat
them identically.

## Quick start

```bash
uv sync --extra dev        # base deps + pytest/pytest-mock/ruff
cp .env.example .env       # fill in ANTHROPIC_API_KEY / TAVILY_API_KEY
```

Run a single variant from the CLI:

```bash
uv run research-assistant run "the current state of fusion energy" --variant pipeline
uv run research-assistant run "the current state of fusion energy" --variant agentic
```

Run the tests:

```bash
uv run python -m pytest              # not bare `uv run pytest` — see note below
```

> **Windows note:** always use `uv run python -m pytest`, not bare
> `uv run pytest` — on this machine the bare form can resolve to an Anaconda
> `pytest` on `PATH` instead of the project's own virtualenv.
>
> Tests that hit real Anthropic/Tavily APIs are marked `live` and excluded by
> default (`addopts = "-m 'not live'"`). Run them explicitly with
> `uv run python -m pytest -m live` once your `.env` keys are filled in.

## Running the `graphrag` variant

The `graphrag` variant needs a local Neo4j instance and the `graphrag` extra:

```bash
uv sync --extra graphrag
docker compose up -d       # starts Neo4j (bolt on :7687, browser on :7474)
```

Add the connection details to `.env` (already present in `.env.example`,
matching `docker-compose.yml`'s default credentials):

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=researchassistant
```

The graph is wiped and rebuilt on every run — there is no cross-run
persistence, so `graphrag` traces stay comparable to the other two variants
(see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#graphrag-variant) for why).

```bash
uv run research-assistant run "the current state of fusion energy" --variant graphrag
```

## Running the web app

Two processes, no Docker beyond what `graphrag` already needs:

```bash
uv sync --extra api
uv run research-assistant serve        # backend on :8000 (binds 127.0.0.1 only)
```

```bash
cd web
npm install
npm run dev                            # frontend on :5173
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to the
backend (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#frontendbackend-connection)
for why the frontend never calls the backend cross-origin), so pick a topic
and variant in the form, submit, and the page polls until the run finishes
and shows the brief plus its sources. "Past runs" below it lists every
completed run's trace (LLM calls, search calls, tokens, duration) side by
side for comparison — the whole point of building three variants of the same
task.

Frontend tests:

```bash
cd web && npm test
```

## Project layout

```
src/research_assistant/
  models.py              Pydantic domain models: SearchResult, Source,
                          SubQuestion, ResearchPlan, Brief, Triple
  config.py               Settings, loaded from .env
  llm/
    base.py                LLMClient Protocol + message/tool-call types
    anthropic_client.py     the only LLMClient implementation
  tools/
    search_tool.py          TavilySearchTool
  tracing/
    recorder.py              RunRecorder / RunTrace — the cross-variant
                              comparison mechanism
  writing/
    brief.py, citations.py    assembling and numbering the final Brief
  variants/
    pipeline/run.py           fixed 4-step pipeline
    agentic/run.py            ReAct-style tool-loop agent
    graphrag/                 knowledge-graph retrieval variant (Neo4j)
    __init__.py                VARIANT_REGISTRY — the single source of
                                truth for which variants exist
  web/
    app.py, runs.py, schemas.py   FastAPI backend: submit-and-poll HTTP API
  cli.py                    Typer CLI: `run` and `serve` commands

web/                       React + TypeScript + Vite frontend (separate
                            package.json, its own toolchain)

tests/
  unit/                    fast, mocked — the default test run
  live/                    real API calls — marked `live`, opt-in only

docs/
  ARCHITECTURE.md          solution design, architecture, and the
                            reasoning behind each decision
  superpowers/specs/       detailed per-subsystem design docs (agentic
                            tool loop, GraphRAG, web app)
```

## Architecture & design docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — start here: overall
  architecture, why three variants, the tracing mechanism, the web layer's
  design and trade-offs.
- `docs/superpowers/specs/` — the original detailed design spec for each
  subsystem (agentic tool loop, GraphRAG, web app), written before
  implementation and kept as the record of *why*, not just *what*.
- `CLAUDE.md` — living status/roadmap doc, kept up to date as the project
  evolves.

## Roadmap

Pipeline, agentic, and GraphRAG variants are implemented and tested, as is
the web app (FastAPI backend + React/Vite frontend). Two orchestration
variants remain, both planned on **Google ADK** (Agent Development Kit)
rather than hand-rolled, specifically to compare framework-provided vs.
hand-rolled orchestration for the same control flow:

- **plan-execute-reflect** — explicit planner → executor → a reflection step
  that checks sufficiency and can loop before the final write.
- **multi-agent orchestration** — a lead/orchestrator agent delegates
  sub-questions to parallel researcher subagents, then a writer agent
  synthesizes findings.

Neither is designed yet beyond this roadmap note; each gets its own
brainstorm → spec → plan cycle when picked up.

# research-assistant

A research assistant that plans, searches, reads, and writes a short brief —
built multiple ways to compare agentic architectures (pipeline vs. agentic
tool-loop) against the same task, using `RunRecorder` traces (LLM calls,
tokens, duration, search calls) to compare them.

## Setup

```
uv sync --extra dev        # base deps + pytest/pytest-mock/ruff
uv sync --extra notebook   # only needed for tokenizer_analysis.ipynb
cp .env.example .env       # fill in ANTHROPIC_API_KEY / TAVILY_API_KEY
```

Run tests with `uv run python -m pytest` (not bare `uv run pytest` — on this
machine that resolves to an Anaconda pytest on PATH instead of the venv's).
Live tests that hit real APIs are marked `live` and excluded by default
(`addopts = "-m 'not live'"` in pyproject.toml).

## Architecture

- `models.py` — Pydantic domain models: `SearchResult`, `Source`,
  `SubQuestion`, `ResearchPlan`, `Brief`.
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
  - `variants/agentic/run.py` — **speced, not yet implemented.** ReAct-style
    single-agent tool loop (LLM drives its own `web_search` calls up to an
    8-round cap, then a separate write pass), hand-rolled on the existing
    `LLMClient`/`ToolDef`/`ToolCall` plumbing. Design:
    `docs/superpowers/specs/2026-08-23-agentic-tool-loop-variant-design.md`.
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
  - **GraphRAG retrieval variant — not started, newly added 2026-08-23.**
    Not part of the original 4-variant plan. A variant exploring a different
    *retrieval* strategy rather than orchestration control-flow: build a
    knowledge graph from retrieved documents and retrieve via graph
    traversal/community summaries (the GraphRAG technique) instead of
    Tavily web search per sub-question/tool-call. Orthogonal axis of
    comparison to the other variants (retrieval strategy vs. control flow).
- `cli.py` — Typer CLI: `research-assistant run <topic> --variant <name>
  --output <path>`.

## Status

Working pipeline variant with unit test coverage (citations, models, search
parsing) and a `live` integration test. `tokenizer_analysis.ipynb` is a
separate, finished, self-contained notebook (domain-specific tokenizer
fragmentation) unrelated to the CLI app.

Roadmap (in rough order): implement the agentic tool-loop variant (spec
approved, plan next) → plan-execute-reflect on Google ADK → multi-agent
orchestration on Google ADK → GraphRAG retrieval variant. Each gets its own
brainstorming → spec → plan cycle when picked up; none of the later items
are designed yet beyond this roadmap note.

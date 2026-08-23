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
  - **Agentic tool-loop variant — not yet implemented.** Only
    `Variant.pipeline` exists in the registry today. The plan is a variant
    where the LLM drives its own loop via tool calls (search, maybe
    read/extract) rather than a fixed sequence of prompts, reusing the same
    `LLMClient`/`ToolDef`/`ToolCall` plumbing that already exists for this.
- `cli.py` — Typer CLI: `research-assistant run <topic> --variant <name>
  --output <path>`.

## Status

Working pipeline variant with unit test coverage (citations, models, search
parsing) and a `live` integration test. `tokenizer_analysis.ipynb` is a
separate, finished, self-contained notebook (domain-specific tokenizer
fragmentation) unrelated to the CLI app.

Next planned work: design and implement the agentic tool-loop variant so it
can be compared against the pipeline variant via `RunRecorder` traces.

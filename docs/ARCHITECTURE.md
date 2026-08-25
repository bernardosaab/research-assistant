# Architecture

This document explains what `research-assistant` is for, how it's put
together, and — more importantly — *why* it's put together this way. For the
detailed, point-in-time design spec each subsystem was actually built from,
see `docs/superpowers/specs/`; this document is the durable summary that
stays current as those specs age.

## Purpose

The project exists to answer one question: **for the same research task, how
do different agentic architectures compare?** Not in the abstract — in
concrete, measurable terms, on the same topic, with the same LLM and search
provider, producing a directly comparable trace (LLM calls, tokens spent,
search calls, wall-clock duration).

That framing drives most of the design decisions below: a shared domain
model and a shared tracing mechanism matter more here than in a typical
single-approach tool, because the whole point is to hold everything constant
except the orchestration strategy.

## High-level architecture

```
                        ┌─────────────────────┐
   CLI (cli.py)  ─────▶ │                      │
                        │  VARIANT_REGISTRY    │ ── Variant.pipeline ─▶ variants/pipeline/run.py
   Web API             │  {Variant: run_fn}    │ ── Variant.agentic  ─▶ variants/agentic/run.py
   (web/app.py) ──────▶ │                      │ ── Variant.graphrag ─▶ variants/graphrag/run.py
                        └─────────────────────┘
                                   │
                     each run_fn(topic, recorder) -> Brief
                                   │
                        ┌──────────┴──────────┐
                        │                      │
                 LLMClient (Anthropic)   TavilySearchTool
                        │                      │
                        └──────────┬──────────┘
                                   │
                          RunRecorder.record_*()
                                   │
                             RunTrace (comparable
                             across all variants)
```

Both entry points — the Typer CLI and the FastAPI web backend — call into
the exact same `VARIANT_REGISTRY[variant](topic, recorder)` function. Neither
entry point knows or cares how a variant does its work internally; this is
what makes the comparison fair and the web layer a thin wrapper rather than a
second implementation.

## Shared domain model (`models.py`)

One set of Pydantic models is used by every variant and every entry point —
there is deliberately no per-variant model duplication:

- `SearchResult` — one search hit (query, url, title, content, score).
- `Source` — a de-duplicated, numbered reference (`[1]`, `[2]`, …) built from
  search results, shared by the CLI output, the web API, and the brief's
  rendered "Sources" section.
- `SubQuestion` / `ResearchPlan` — the `pipeline` and `graphrag` variants'
  explicit plan structure (the `agentic` variant has no separate plan step;
  see below).
- `Brief` — the final output: topic, markdown body, sources. What every
  variant converges on, regardless of how it got there.
- `Triple` — a `(subject, relation, object, source_url)` fact, used only by
  `graphrag`.

## The `LLMClient` abstraction (`llm/base.py`)

A `Protocol`, not an ABC, with one method: `complete(system, messages, tools,
max_tokens) -> LLMResponse`. `AnthropicLLMClient` is the only implementation,
but the Protocol already models tool-use (`ToolDef`, `ToolCall`,
`ToolResult`) even though the `pipeline` variant never uses it — this was a
deliberate choice made before the `agentic` variant existed, so that adding
tool-use later required zero changes to the interface, only a new caller.

## Tracing (`tracing/recorder.py`)

`RunRecorder` is the mechanism that makes cross-variant comparison possible
at all. It's intentionally minimal — four counters and a wall-clock timer:

```python
record_llm_call(usage)      # increments llm_calls, accumulates input/output tokens
record_tool_call(tool_name) # increments search_calls if tool_name == "web_search"
finalize() -> RunTrace       # variant, topic, duration_seconds, llm_calls,
                              # search_calls, input_tokens, output_tokens
```

Every variant's `run()` function takes an optional `recorder` parameter and
calls `record_llm_call` after every `llm.complete(...)` and `record_tool_call`
after every search — that's the entire contract. There is no event bus, no
callback registry, no structured logging framework: the trade-off is that
adding a new *kind* of thing to measure means touching every variant's call
sites, but for four counters across three variants that's a smaller cost
than the machinery an event system would add, and it keeps each variant's
`run()` readable as a straight-line function.

## The three variants

All three variants live in `variants/<name>/run.py` and expose one function:
`run(topic: str, recorder: RunRecorder | None = None) -> Brief`. They are
registered in `variants/__init__.py`'s `VARIANT_REGISTRY: dict[Variant,
Callable]` — the single source of truth for which variants exist. Nothing
outside that file hardcodes a variant list (see "No hardcoded variant list"
below).

### `pipeline` — the baseline

Four sequential, non-tool-use LLM calls, each a separate testable function:

```
generate_plan(topic)        one call → 3-5 SubQuestions, parsed from a JSON array
run_searches(plan)          one Tavily search per sub-question (no LLM call)
extract_findings(plan)      one call per sub-question → 2-4 sentence summary
write_brief(plan)           one call → final markdown, cited against sources
```

This is the control group: no agent judgment anywhere in the loop, a fixed
number of LLM calls determined entirely by the number of sub-questions. It
exists to give the other two variants something concrete to be measured
against.

### `agentic` — ReAct-style tool loop

A single agent drives its own `web_search` tool calls in a loop (capped at 8
rounds), deciding for itself when it has searched enough, followed by one
separate write pass:

```
for round in range(MAX_ROUNDS):
    response = llm.complete(..., tools=[web_search])
    if response.stop_reason != "tool_use":
        break                          # the agent chose to stop
    run the tool calls, append results to history, continue
write_brief(topic, all_results)         # separate call, not part of the loop
```

The comparison this enables against `pipeline`: same task, same tools
available, but the *number and content* of searches is now a judgment call
made by the model at run time rather than fixed in advance by an explicit
plan step. The 8-round cap exists purely as a safety bound against a
non-terminating loop, not as an expected operating point.

### `graphrag` — a different axis

`graphrag` reuses `pipeline`'s `generate_plan` and `run_searches` unchanged
— its variable isn't planning strategy, it's what happens to search results
before they reach the write step. Rather than summarizing each
sub-question's results directly, each batch of results is passed through an
LLM extraction step (`extraction.py`) that pulls out `(subject, relation,
object, source_url)` triples, which are written into a small local knowledge
graph (Neo4j), then read back as a flat list of facts for the final write
call.

```
generate_plan → run_searches → for each sub-question:
    extract_triples(sub_question) → graph_store.add_triple(...)
→ graph_store.get_all_facts() → write_brief(facts, ...)
```

This is deliberately **simplified GraphRAG** — no community detection, no
graph summarization pass, no multi-hop query planning. Those are what
distinguish full GraphRAG implementations from a plain vector-retrieval
pipeline, but they add orchestration complexity that isn't the variable
under study here; the point of this variant is retrieval *structure*
(graph vs. flat text), not the most sophisticated possible graph pipeline.

**The graph is wiped and rebuilt on every run** (`graph_store.clear()` before
extraction) — there is deliberately no cross-run persistence. Two reasons:
first, this project isn't a hosted service with durability guarantees for
any variant (the web app's run store is in-memory-only for the same reason);
second and more importantly, persisting facts across runs would let a later
`graphrag` run on the same topic benefit from a previous run's extraction
work, which would silently break comparability against `pipeline` and
`agentic` — those always start from zero background knowledge, and
`graphrag` needs to as well for the trace comparison to mean anything.

`Neo4jGraphStore.__init__` imports `neo4j` **lazily** (inside `__init__`,
not at module level) specifically because `neo4j` is an optional dependency
(the `graphrag` extra). A module-level import would break `uv sync --extra
dev` for anyone not using this variant — this was caught as a real bug in
review (see "Known failure mode" below) and is now the pattern any future
optional-dependency variant should follow.

### No hardcoded variant list

Every consumer of variants — the CLI's `--variant` option, the web API's
`GET /variants`, the frontend's variant picker — derives its list from
`VARIANT_REGISTRY` rather than hardcoding variant names. The frontend's
`variant` field is typed `string`, never a fixed TypeScript union, for the
same reason: adding a fourth variant to the registry should require zero
changes anywhere in the CLI or web layer.

## Web layer

### Why a thin wrapper, not a second implementation

The FastAPI backend (`web/app.py`, `web/runs.py`, `web/schemas.py`) has
exactly three routes and no business logic of its own — it exists purely to
expose `VARIANT_REGISTRY[variant](topic, recorder)` over HTTP with a
submit-and-poll flow, because a browser can't call a blocking Python
function directly.

```
POST /runs           -> starts a run in a background thread, returns {run_id}
GET  /runs/{run_id}  -> current RunRecord (status: running | done | error)
GET  /runs           -> all runs this process has seen, for comparison
```

**No live streaming of in-progress steps** was considered and explicitly
rejected: the variant `run()` functions emit no intermediate events today
(no "round 3 of 8", no "searching sub-question 2"), and adding that would
mean threading an event-hook mechanism through all three variants just for
the web layer's benefit — a cost paid by every variant to serve one
consumer. Submit-and-poll every ~2 seconds from the frontend is a
deliberately simpler trade-off.

**No persistence beyond the running process.** Runs live in an in-memory
`dict[str, RunRecord]`; restarting the backend clears them. Consistent with
the rest of the project's local-dev-tool scope — the same reasoning behind
`graphrag`'s per-run graph wipe above. This is not a hosted service with
uptime or durability guarantees for any variant.

**No auth, binds to `127.0.0.1` only.** `research-assistant serve` runs
`uvicorn.run(..., host="127.0.0.1", ...)` deliberately, not `0.0.0.0` — this
proxies your Anthropic/Tavily API keys' usage to whatever hits it, and
there's no reason to expose that to the local network for a personal dev
tool.

**Concurrency:** `POST /runs` hands the variant call to FastAPI's
`BackgroundTasks`, which runs a *synchronous* function in Starlette's thread
pool rather than blocking the event loop — so a long-running variant call
(real network calls to Anthropic/Tavily) doesn't block other requests from
being served while it's in progress. Every store write replaces the whole
`RunRecord` via `model_copy()` rather than mutating fields in place; combined
with CPython's GIL making a single `dict[key] = value` assignment atomic,
this needs no explicit lock even though the background thread writes while
request handlers read concurrently.

**Every variant failure is caught and stored as `status="error"`.**
`BackgroundTasks` logs an unhandled exception and moves on — it does not
update the run store for you. Without an explicit `try/except` around the
variant call, a failing run (a missing Neo4j config, an API error) would
leave its `RunRecord` stuck at `status="running"` forever, and the frontend
would poll indefinitely with no way to know something went wrong.

### Frontend/backend connection

The frontend (`web/`, a separate React + TypeScript + Vite project) talks to
the backend through a **Vite dev-server proxy**: it calls relative paths
like `/api/runs`, and Vite's dev server rewrites and forwards `/api/*` to
`http://127.0.0.1:8000/*`, stripping the `/api` prefix. The browser only
ever talks to `:5173` — no cross-origin request ever happens, and the
backend's `CORSMiddleware` (present in an earlier draft) is dead code and
was removed.

This decision replaced an earlier, self-contradictory draft of the spec that
called for *both* a restrictive CORS policy *and* a dev-server proxy —
mutually exclusive, since a proxy makes every request same-origin and makes
CORS irrelevant. The proxy approach was chosen because it's simpler for a
local dev tool (no CORS configuration to keep in sync with whatever port the
frontend happens to run on) and because it matches how the app is actually
used: two local processes, one browser tab, no real cross-origin deployment
scenario to design for.

## Testing strategy

- **Unit tests** (`tests/unit/`, the default `pytest` run) mock the LLM
  client and search tool — the same dependency-injection-for-testability
  pattern used throughout (`LLMClient` as a `Protocol` makes this a plain
  fake, no mocking framework required for the interface itself).
- **Live tests** (`tests/live/`) hit real Anthropic/Tavily APIs and are
  marked `live`, excluded by default via `addopts = "-m 'not live'"` in
  `pyproject.toml` — they exist to catch integration drift (API shape
  changes, prompt regressions) without slowing down or adding cost to every
  normal test run.
- **Frontend tests** (`web/src/*.test.{ts,tsx}`) use Vitest + React Testing
  Library, testing components and the polling hook against fixture
  `RunRecord` JSON rather than a real backend.
- A real-server integration test
  (`tests/unit/test_web_app_concurrency.py`) runs an actual `uvicorn.Server`
  in a background thread to prove `POST /runs` returns before the variant
  finishes — the property that matters most about the concurrency design
  above can't be verified through a mocked `TestClient` alone.

## Known failure mode worth remembering

When `graphrag`'s dependency (`neo4j`) was first added, `variants/__init__.py`
unconditionally imported the `graphrag` module (needed to populate
`VARIANT_REGISTRY`), and `graph_store.py` imported `neo4j` at module level —
together, this silently broke `uv sync --extra dev` for anyone not
installing the `graphrag` extra, since importing `research_assistant.cli`
transitively imported `neo4j`, which wasn't installed. The fix was moving
the `neo4j` import inside `Neo4jGraphStore.__init__` (lazy import). Any
future variant that introduces its own optional dependency (as the Google
ADK variants on the roadmap will) needs the same discipline: nothing outside
that dependency's own extra may import the optional package at module level.

## Where the detailed specs live

This document is the durable summary. The original point-in-time design
specs — written and approved before each subsystem was implemented — are
kept in `docs/superpowers/specs/`:

- `2026-08-23-agentic-tool-loop-variant-design.md`
- `2026-08-23-graphrag-variant-design.md`
- `2026-08-23-web-app-design.md`

They carry more granular rationale (e.g. the full non-goals list for each
subsystem) than is repeated here, and are the record of what was
*considered and rejected*, not only what was built.

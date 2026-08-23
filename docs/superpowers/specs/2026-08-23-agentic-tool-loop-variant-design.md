# Agentic tool-loop variant — design

## Purpose

`research-assistant` was built to compare agentic architectures on the same
task (plan → search → extract → write a short cited brief). Today only the
**pipeline** variant exists (`variants/pipeline/run.py`): a fixed sequence of
four non-tool-use LLM calls (`generate_plan` → `run_searches` →
`extract_findings` → `write_brief`).

This spec adds a second variant — **agentic** — where the LLM drives its own
research loop via tool calls (`web_search`) instead of following a
pre-planned sequence of sub-questions, so the two can be compared head-to-head
via `RunRecorder` traces (LLM calls, tokens, duration, search calls) on the
same topics.

## Non-goals

- No new tools beyond `web_search` (no page-read/extract tool, no
  `submit_brief` tool — see "Approach considered and rejected" below).
- No changes to `Variant` selection UX beyond registering the new variant —
  `cli.py` already takes `--variant` generically.
- No change to the `Brief`/`Source` output shape — the agentic variant must
  produce a `Brief` indistinguishable in structure from the pipeline's, so
  comparison is apples-to-apples.

## Approach considered and rejected

A single-phase design was considered where the LLM has both `web_search` and
a `submit_brief(markdown)` tool, ending the loop when it calls
`submit_brief`. Rejected because citation correctness (matching `[n]` to the
right `Source`) would rest entirely on the model tracking numbering itself
across a long, freeform tool-call history, with no separate pass to hand it a
clean, deduped, numbered source list. The two-phase approach below keeps
citation numbering deterministic and code-controlled, matching how the
pipeline variant already does it.

## Design

### File layout

- `src/research_assistant/variants/agentic/__init__.py`
- `src/research_assistant/variants/agentic/run.py` — exposes
  `run(topic: str, recorder: RunRecorder | None = None) -> Brief`, same
  signature as the pipeline variant.
- `variants/__init__.py` — add `agentic = "agentic"` to the `Variant` enum and
  register it in `VARIANT_REGISTRY`.
- `cli.py` — no changes needed; `--variant agentic` works once registered.

### Data flow

**Phase 1 — research loop** (max 8 rounds, see "Loop cap" below):

```
history: list[LLMMessage] = [LLMMessage(role="user", text=f"Topic: {topic}")]
all_results: list[SearchResult] = []

for round in range(MAX_ROUNDS):
    response = llm.complete(
        system=RESEARCH_SYSTEM_PROMPT,
        messages=history,
        tools=[search_tool.as_tooldef()],
    )
    recorder.record_llm_call(response.usage)

    if response.stop_reason != "tool_use":
        break

    history.append(LLMMessage(role="assistant", text=response.text,
                               tool_calls=response.tool_calls))

    tool_results = []
    for call in response.tool_calls:
        result_text = search_tool.run(call.input["query"])  # already formatted
        recorder.record_tool_call(search_tool.name)
        all_results.extend(search_tool.last_results)
        tool_results.append(ToolResult(
            tool_call_id=call.id,
            content=result_text,
        ))
    history.append(LLMMessage(role="user", tool_results=tool_results))
else:
    pass  # cap hit: fall through to write phase with whatever was gathered
```

A single LLM response can contain multiple `tool_use` blocks (parallel tool
calls); the loop handles all of them per round, and captures
`search_tool.last_results` immediately after each individual `run()` call
since it's overwritten on every call.

**Phase 2 — write**: identical in spirit to the pipeline's `write_brief`:

```
sources = build_source_list(all_results)
sources_text = format_sources_for_prompt(sources)
response = llm.complete(
    system=BRIEF_SYSTEM_PROMPT,  # reused as-is from variants/pipeline/run.py
    messages=[LLMMessage(role="user", text=(
        f"Topic: {topic}\n\nSources:\n{sources_text}"
    ))],
    max_tokens=2048,
)
recorder.record_llm_call(response.usage)
return assemble_brief(topic, response.text or "", sources)
```

Unlike the pipeline, there's no separate `findings` text per sub-question to
hand the write phase — the model has to synthesize directly from its own
tool-call history (which isn't passed to this call) plus the source list.
This is intentional: it's the natural shape of a single-agent tool loop
(the model already "knows" what it found from its own transcript) and it
keeps the write-phase prompt small. **Open risk:** without findings text
in-context for this call, brief quality depends on the model reasoning from
just topic + source titles/URLs; if this reads too thin in practice, a
follow-up could pass the full loop transcript into this call instead.

### System prompt (research phase)

```python
RESEARCH_SYSTEM_PROMPT = (
    "You are a research assistant investigating a topic using web search. "
    "Search as many times as needed to build a well-rounded understanding "
    "— covering the topic from multiple angles — then stop calling tools "
    "once you have enough to write a short brief."
)
```

### Loop cap

`MAX_ROUNDS = 8`. If the model still wants to search after 8 rounds, the loop
stops feeding it tools and proceeds straight to the write phase with
whatever `all_results` was accumulated so far — never raises, never returns
an empty brief. This mirrors real usage (a user is never left with nothing)
and keeps `RunRecorder` traces bounded and comparable to the pipeline's fixed
cost.

### Shared refactor: `citations.build_source_list`

Currently: `build_source_list(plan: ResearchPlan) -> list[Source]`, walking
`plan.sub_questions[].search_results`. This assumes the pipeline's
`ResearchPlan` shape, which the agentic variant doesn't have.

Change to: `build_source_list(results: list[SearchResult]) -> list[Source]`,
deduping by URL in order of first appearance (same logic, flattened input).

Pipeline's `write_brief` updates to flatten before calling:

```python
all_results = [r for sq in plan.sub_questions for r in sq.search_results]
sources = build_source_list(all_results)
```

`tests/unit/test_citations.py` updates to build flat `list[SearchResult]`
fixtures instead of `ResearchPlan`/`SubQuestion` objects — a mechanical
change, same assertions.

### Error handling

No new failure modes beyond what the pipeline already leaves unhandled:
LLM/API errors propagate uncaught (consistent with `variants/pipeline/run.py`
today). `web_search`'s single `query: string` field is validated against its
JSON schema by Anthropic before the tool is invoked, so malformed tool input
isn't a case this code needs to guard against.

### Testing

- **New:** `tests/unit/test_agentic_run.py` — a hand-written fake `LLMClient`
  (implementing the `llm.base.LLMClient` protocol; no fake exists yet in the
  codebase, since the pipeline's `run.py` has no unit tests today, only its
  downstream pieces do) that scripts a fixed sequence of `LLMResponse`s to
  verify:
  - a `tool_use` → `tool_use` → `end_turn` sequence runs two search rounds,
    accumulates results, and produces a brief with citations
  - hitting `MAX_ROUNDS` still terminates and produces a brief (cap
    behavior), rather than looping forever or erroring
  - `RunRecorder` is called once per LLM call and once per tool call, so
    trace counts are auditable
- **Updated:** `tests/unit/test_citations.py` — flat-list fixtures instead of
  `ResearchPlan`.
- **New:** `tests/live/test_agentic_live.py` — mirrors
  `test_pipeline_live.py` (marked `live`, skipped without API keys in
  `.env`), asserts a non-empty, cited brief for a simple topic.

## Success criteria

- `research-assistant run "<topic>" --variant agentic` produces a `Brief`
  with the same structural guarantees as the pipeline variant (non-empty
  markdown, a `## Sources` section, `[n]`-style citations matching
  `brief.sources`).
- `RunRecorder` traces for both variants are directly comparable (same
  fields populated: `llm_calls`, `search_calls`, `input_tokens`,
  `output_tokens`, `duration_seconds`).
- All existing pipeline tests still pass after the `citations.py` signature
  change.

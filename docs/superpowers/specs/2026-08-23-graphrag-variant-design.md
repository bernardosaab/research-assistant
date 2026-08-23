# GraphRAG variant — design

## Purpose

`research-assistant` compares agentic architectures on the same task (plan
→ search → extract → write a short cited brief). Two variants exist today:
**pipeline** (fixed sequence of prompts) and **agentic** (LLM-driven tool
loop). Both retrieve information the same way — flat text from Tavily
search results fed straight to an LLM.

This spec adds a third variant, **graphrag**, that changes the *retrieval
strategy* instead of the control flow: search results are turned into a
knowledge graph (entities + relationships) before the write phase, so
multi-hop connections between facts from different searches are visible in
a way flat text summaries lose.

## Non-goals

- No community detection or community summarization (the full Microsoft
  GraphRAG technique) — this is the simplified version: extract → build
  graph → query the whole (already topic-scoped) graph → write.
- No cross-run persistence. The graph is cleared and rebuilt from scratch
  on every `run()` call, same per-query semantics as the other two
  variants, so `RunRecorder` traces stay comparable.
- No new `Variant` selection UX — `cli.py` already takes `--variant`
  generically.
- No change to `Brief`/`Source` output shape — same structural guarantees
  as the other two variants (non-empty markdown, `## Sources` section,
  `[n]`-style citations).

## Approach considered and rejected

**Full GraphRAG** (entity/relationship extraction → graph clustering into
communities via an algorithm like Leiden → LLM-generated summary per
community → "global search" across summaries) was considered and
rejected for this project's scope: it triples the LLM-call surface per run,
adds a graph-clustering dependency, and the value it adds (aggregate
insight across many documents) doesn't show up meaningfully at the scale
of a handful of sub-question searches. The simplified version below keeps
the retrieval-strategy contrast (structured graph vs. flat text) without
the clustering machinery.

## Design

### File layout

- `src/research_assistant/variants/graphrag/__init__.py`
- `src/research_assistant/variants/graphrag/run.py` — `run(topic,
  recorder) -> Brief`, `build_graph(...)`, `write_brief(...)`
- `src/research_assistant/variants/graphrag/graph_store.py` —
  `Neo4jGraphStore`
- `src/research_assistant/variants/graphrag/extraction.py` —
  `EXTRACTION_SYSTEM_PROMPT`, `extract_triples(...)`
- `src/research_assistant/models.py` — add `Triple` (subject, relation,
  object, source_url)
- `variants/__init__.py` — add `graphrag = "graphrag"` to `Variant`,
  register in `VARIANT_REGISTRY`
- `src/research_assistant/config.py` — add optional `neo4j_uri`,
  `neo4j_user`, `neo4j_password` fields to `Settings`
- `docker-compose.yml` (repo root) — local Neo4j for development
- `.env.example` — add `NEO4J_URI`/`NEO4J_USER`/`NEO4J_PASSWORD`
- `pyproject.toml` — new `graphrag` extra: `neo4j>=5`

### Data flow

**1. Plan + search** — reused as-is from the pipeline variant:
`generate_plan(topic, llm, recorder)` then `run_searches(plan, search_tool,
recorder)`, both imported from `variants.pipeline.run`.

**2. Extraction** — one LLM call per sub-question, turning that
sub-question's search results into JSON triples:

```python
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
    results_text = "\n".join(
        f"- {r.title} ({r.url}): {r.content}" for r in sub_question.search_results
    ) or "No search results found."
    response = llm.complete(
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", text=f"Search results:\n{results_text}")],
    )
    recorder.record_llm_call(response.usage)
    return _parse_triples(response.text or "[]")
```

`_parse_triples` mirrors the pipeline's `_parse_json_list` pattern (regex
for a `[...]` block, `json.loads`, skip anything that fails) but validates
each item into a `Triple`, silently dropping entries missing a required
key — LLM output is an external boundary, not internal code, so defensive
parsing here is warranted (unlike the rest of the codebase's
no-unnecessary-error-handling stance).

**3. Graph build** — writes triples into Neo4j via a store abstraction:

```python
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

**Deliberate choice: a single generic `RELATION` relationship type with a
`type` property**, rather than a dynamic Cypher relationship type per
extracted relation name (e.g. `:BORN_IN`). Relation labels come from LLM
output — using them as literal Cypher relationship-type identifiers would
require sanitizing arbitrary text into valid identifier syntax and risks
malformed queries. Storing the relation as a property on a fixed
relationship type sidesteps that entirely.

`build_graph` orchestrates extraction + writing, and is the unit-testable
seam (takes `graph_store` as a parameter, so a fake store substitutes in
tests — same pattern as the agentic variant's `search_tool` parameter):

```python
def build_graph(
    plan: ResearchPlan, llm: LLMClient, graph_store: Neo4jGraphStore, recorder: RunRecorder
) -> list[Triple]:
    graph_store.clear()
    for sub_question in plan.sub_questions:
        for triple in extract_triples(sub_question, llm, recorder):
            graph_store.add_triple(triple.subject, triple.relation, triple.object, triple.source_url)
    return graph_store.get_all_facts()
```

**4. Retrieval** — deliberately simple: `get_all_facts()` returns the
*entire* graph, no traversal/filtering step. Since the graph was built only
from this run's topic-scoped searches (step 1-2), it's already scoped —
multi-hop connections between entities from different sub-questions are
still visible in the full fact list without needing path-finding logic.

**5. Write phase** — a dedicated `BRIEF_SYSTEM_PROMPT` (not reused from the
pipeline, for the same reason the agentic variant's final review flagged:
the prompt must accurately describe what it actually receives):

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
        messages=[LLMMessage(role="user", text=(
            f"Topic: {topic}\n\n"
            f"Facts:\n{format_facts_for_prompt(facts, sources)}\n\n"
            f"Sources:\n{format_sources_for_prompt(sources)}"
        ))],
        max_tokens=2048,
    )
    recorder.record_llm_call(response.usage)
    return assemble_brief(topic, response.text or "", sources)
```

A fact whose `source_url` isn't in the deduped source list (e.g. the model
hallucinated a URL not present in the given results) is still listed, just
without a citation marker — never invents a bracket number, consistent
with the citation contract.

**6. Top-level `run()`:**

```python
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

The `try/finally` ensures the Neo4j driver connection is closed even if
extraction or graph-writing raises.

### Config changes

`Settings` gains three **optional** fields (default `None`) so `pipeline`
and `agentic` aren't affected:

```python
neo4j_uri: str | None = None
neo4j_user: str | None = None
neo4j_password: str | None = None
```

### Local infra

`docker-compose.yml` at the repo root:

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

`.env.example` additions:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=researchassistant
```

### Error handling

- Missing Neo4j config: `run()` raises a clear `RuntimeError` naming the
  missing `.env` vars and the `docker compose up -d` fix, rather than
  letting a driver-level connection error surface first.
- Malformed LLM extraction output: triples missing required keys are
  dropped, not raised (external-boundary defensive parsing, matching how
  `_parse_json_list` already handles malformed plan output).
- No other new failure modes beyond what the other variants already leave
  uncaught (LLM/API errors propagate).

### Testing

- **Unit:** `extract_triples` tested with a scripted `LLMClient` (verifies
  JSON parsing, malformed-entry dropping). `build_graph` tested with a fake
  `GraphStore` test double (`clear`/`add_triple`/`get_all_facts` as plain
  Python, no real Neo4j) — verifies orchestration (one extraction call per
  sub-question, all triples written, facts returned). `format_facts_for_prompt`
  tested directly (pure function: citation-marker mapping, missing-URL
  fallback, empty-facts fallback).
- **Not unit tested:** `Neo4jGraphStore`'s Cypher queries themselves — like
  `AnthropicLLMClient`/`TavilySearchTool`, this is the real-adapter layer,
  exercised by the live test instead. Also no unit test for top-level
  `run()` itself, same convention as the other two variants.
- **Live:** a `live`-marked test (same skip-without-config pattern as the
  other two) that requires both API keys *and* a reachable local Neo4j —
  its `_settings_available()` check extends to verify Neo4j config is
  present, not just Anthropic/Tavily.

## Success criteria

- `research-assistant run "<topic>" --variant graphrag` produces a `Brief`
  with the same structural guarantees as the other two variants.
- `docker compose up -d` + `.env` config is sufficient to run it locally —
  no other local infrastructure needed.
- `RunRecorder` traces are comparable across all three variants (same
  fields populated).
- Existing pipeline/agentic tests and behavior are unaffected — `Settings`
  fields are additive and optional.

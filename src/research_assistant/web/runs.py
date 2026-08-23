import uuid
from datetime import UTC, datetime

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
        created_at=datetime.now(UTC),
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
    # Break ties on created_at (clock resolution can make two calls in quick
    # succession compare equal) using dict insertion order as a secondary key,
    # so the most recently started run always sorts first.
    indexed = list(enumerate(_runs.values()))
    indexed.sort(key=lambda pair: (pair[1].created_at, pair[0]), reverse=True)
    return [record for _, record in indexed]

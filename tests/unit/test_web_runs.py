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

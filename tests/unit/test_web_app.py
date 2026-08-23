import pytest
from fastapi.testclient import TestClient

import research_assistant.web.runs as runs_module
from research_assistant.llm.base import LLMUsage
from research_assistant.models import Brief
from research_assistant.variants import VARIANT_REGISTRY, Variant
from research_assistant.web.app import app


@pytest.fixture(autouse=True)
def _clear_runs():
    runs_module._runs.clear()
    yield
    runs_module._runs.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _fake_run(topic, recorder):
    recorder.record_llm_call(LLMUsage(input_tokens=5, output_tokens=3))
    return Brief(topic=topic, markdown="# Brief", sources=[])


def _failing_run(topic, recorder):
    raise RuntimeError("boom")


def test_get_variants_lists_registered_variants(client):
    response = client.get("/variants")
    assert response.status_code == 200
    names = response.json()
    assert "pipeline" in names
    assert "agentic" in names


def test_create_run_then_poll_returns_done_with_brief(client, monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _fake_run)

    create_response = client.post("/runs", json={"topic": "t", "variant": "pipeline"})
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    poll_response = client.get(f"/runs/{run_id}")
    assert poll_response.status_code == 200
    body = poll_response.json()
    assert body["status"] == "done"
    assert body["brief"]["markdown"] == "# Brief"
    assert body["trace"]["llm_calls"] == 1


def test_create_run_that_fails_returns_error_status(client, monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _failing_run)

    create_response = client.post("/runs", json={"topic": "t", "variant": "pipeline"})
    run_id = create_response.json()["run_id"]

    poll_response = client.get(f"/runs/{run_id}")
    body = poll_response.json()
    assert body["status"] == "error"
    assert body["error"] == "boom"


def test_get_unknown_run_returns_404(client):
    response = client.get("/runs/does-not-exist")
    assert response.status_code == 404


def test_create_run_with_invalid_variant_returns_422(client):
    response = client.post("/runs", json={"topic": "t", "variant": "not-a-real-variant"})
    assert response.status_code == 422


def test_list_runs_returns_all_created_runs(client, monkeypatch):
    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _fake_run)
    create_response = client.post("/runs", json={"topic": "t", "variant": "pipeline"})
    run_id = create_response.json()["run_id"]

    list_response = client.get("/runs")
    assert list_response.status_code == 200
    ids = [r["run_id"] for r in list_response.json()]
    assert run_id in ids

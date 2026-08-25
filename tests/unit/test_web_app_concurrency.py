import threading
import time

import httpx
import uvicorn

import research_assistant.web.runs as runs_module
from research_assistant.llm.base import LLMUsage
from research_assistant.models import Brief
from research_assistant.variants import VARIANT_REGISTRY, Variant
from research_assistant.web.app import app


def test_post_runs_returns_immediately_while_variant_is_still_running(monkeypatch):
    release = threading.Event()
    started = threading.Event()

    def _blocking_run(topic, recorder):
        started.set()
        release.wait(timeout=5)
        recorder.record_llm_call(LLMUsage(input_tokens=1, output_tokens=1))
        return Brief(topic=topic, markdown="# done", sources=[])

    monkeypatch.setitem(VARIANT_REGISTRY, Variant.pipeline, _blocking_run)
    runs_module._runs.clear()

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "server did not start in time"

        port = server.servers[0].sockets[0].getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"

        # Warm up the connection before timing: the first request to a
        # freshly-started server pays a one-time connection-setup cost
        # (TCP handshake, TLS-equivalent socket setup, httpx client init)
        # that has nothing to do with whether POST /runs blocks on the
        # variant. Absorb that cost here, outside the timed section below.
        httpx.get(f"{base_url}/variants")

        start = time.monotonic()
        response = httpx.post(f"{base_url}/runs", json={"topic": "t", "variant": "pipeline"})
        elapsed = time.monotonic() - start
        assert response.status_code == 200
        assert elapsed < 1.0, f"POST /runs took {elapsed:.2f}s — looks like it blocked on the variant"
        run_id = response.json()["run_id"]

        assert started.wait(timeout=5), "variant function was never invoked"
        poll = httpx.get(f"{base_url}/runs/{run_id}")
        assert poll.json()["status"] == "running"

        release.set()

        final_status = None
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            poll = httpx.get(f"{base_url}/runs/{run_id}")
            final_status = poll.json()["status"]
            if final_status == "done":
                break
            time.sleep(0.05)
        assert final_status == "done"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        runs_module._runs.clear()

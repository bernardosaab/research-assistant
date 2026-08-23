from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from research_assistant.variants import VARIANT_REGISTRY
from research_assistant.web.runs import execute_run, get_run, list_runs, start_run
from research_assistant.web.schemas import RunRecord, RunRequest

app = FastAPI(title="research-assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/variants")
def variants() -> list[str]:
    return [v.value for v in VARIANT_REGISTRY]


@app.post("/runs")
def create_run(request: RunRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    run_id = start_run(request.topic, request.variant)
    background_tasks.add_task(execute_run, run_id, request.topic, request.variant)
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def read_run(run_id: str) -> RunRecord:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@app.get("/runs")
def read_runs() -> list[RunRecord]:
    return list_runs()

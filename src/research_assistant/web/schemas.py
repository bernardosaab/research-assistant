from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from research_assistant.models import Brief
from research_assistant.tracing.recorder import RunTrace
from research_assistant.variants import Variant


class RunRequest(BaseModel):
    topic: str
    variant: Variant


class RunRecord(BaseModel):
    run_id: str
    status: Literal["running", "done", "error"]
    topic: str
    variant: Variant
    created_at: datetime
    brief: Brief | None = None
    trace: RunTrace | None = None
    error: str | None = None

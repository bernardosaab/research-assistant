from collections.abc import Callable
from enum import Enum

from research_assistant.models import Brief
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.agentic.run import run as run_agentic
from research_assistant.variants.pipeline.run import run as run_pipeline


class Variant(str, Enum):
    pipeline = "pipeline"
    agentic = "agentic"


VARIANT_REGISTRY: dict[Variant, Callable[[str, RunRecorder | None], Brief]] = {
    Variant.pipeline: run_pipeline,
    Variant.agentic: run_agentic,
}

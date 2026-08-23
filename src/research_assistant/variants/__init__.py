from collections.abc import Callable
from enum import Enum

from research_assistant.models import Brief
from research_assistant.tracing.recorder import RunRecorder
from research_assistant.variants.pipeline.run import run as run_pipeline


class Variant(str, Enum):
    pipeline = "pipeline"


VARIANT_REGISTRY: dict[Variant, Callable[[str, RunRecorder | None], Brief]] = {
    Variant.pipeline: run_pipeline,
}

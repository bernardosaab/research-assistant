import pytest
from pydantic import ValidationError

from research_assistant.variants import Variant
from research_assistant.web.schemas import RunRecord, RunRequest


def test_run_record_optional_fields_default_to_none():
    record = RunRecord(
        run_id="abc123",
        status="running",
        topic="a topic",
        variant=Variant.pipeline,
        created_at="2026-08-23T12:00:00Z",
    )
    assert record.brief is None
    assert record.trace is None
    assert record.error is None


def test_run_request_rejects_unknown_variant():
    with pytest.raises(ValidationError):
        RunRequest(topic="a topic", variant="not-a-real-variant")

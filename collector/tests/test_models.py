from datetime import datetime, timezone
import pytest
from pydantic import ValidationError


def test_brief_rejects_missing_summary():
    from vid2idea.models import Brief
    with pytest.raises(ValidationError):
        Brief(details=[], suggested_steps=[], open_questions=[])


def test_brief_rejects_blank_summary():
    from vid2idea.models import Brief
    with pytest.raises(ValidationError):
        Brief(summary="   ")


def test_capture_keeps_snowflakes_as_strings():
    from vid2idea.models import SourceCapture
    capture = SourceCapture(channel_id="123456789012345678", message_id="987654321098765432",
        original_url="https://example.com/project", canonical_url="https://example.com/project",
        note="Build this", shared_at=datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert capture.model_dump(mode="json")["message_id"] == "987654321098765432"
    assert capture.note == "Build this"


def test_generated_brief_rejects_model_supplied_evidence():
    from vid2idea.models import GeneratedBrief
    with pytest.raises(ValidationError):
        GeneratedBrief(title="Solar tracker", brief={"summary": "A tracker"}, tags=["solar"], evidence_kinds=["video_frames"])

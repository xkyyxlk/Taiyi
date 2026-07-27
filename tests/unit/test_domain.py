from __future__ import annotations

import pytest
from pydantic import ValidationError

from taiyi.domain import IdentitySnapshot, MemoryDraft, MemoryType, utc_now


def test_memory_requires_source_event() -> None:
    with pytest.raises(ValidationError):
        MemoryDraft(
            type=MemoryType.EPISODIC,
            content="unsupported",
            source_event_ids=(),
            confidence=0.5,
            importance=0.5,
        )


def test_snapshot_is_immutable() -> None:
    snapshot = IdentitySnapshot(
        id="snap_1",
        core_id="core_1",
        self_description="Stable",
        created_at=utc_now(),
    )
    with pytest.raises(ValidationError):
        snapshot.self_description = "Changed"  # type: ignore[misc]

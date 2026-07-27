from __future__ import annotations

import pytest

from taiyi.application import IdentityService, WorldlineService
from taiyi.domain import EventType
from taiyi.storage import ConflictError, Repository


def test_forks_are_isolated(repository: Repository) -> None:
    identity = IdentityService(repository)
    _, snapshot = identity.initialize("Taiyi")
    left = identity.fork("left")
    right = identity.fork("right")
    assert left.base_snapshot_id == right.base_snapshot_id == snapshot.id
    assert left.worldline_id != right.worldline_id

    worldlines = WorldlineService(repository)
    event = worldlines.append_for_incarnation("left", EventType.USER_MESSAGE, {"content": "a"})
    assert worldlines.events_for_incarnation("right") == []
    with pytest.raises(ConflictError):
        worldlines.assert_event_access("right", event.id)


def test_event_sequence_is_stable(repository: Repository) -> None:
    identity = IdentityService(repository)
    identity.initialize("Taiyi")
    identity.fork("left")
    worldlines = WorldlineService(repository)
    first = worldlines.append_for_incarnation("left", EventType.USER_MESSAGE, {"content": "1"})
    second = worldlines.append_for_incarnation("left", EventType.MODEL_RESPONSE, {"content": "2"})
    assert [first.sequence_number, second.sequence_number] == [1, 2]
    assert first.payload_hash != second.payload_hash

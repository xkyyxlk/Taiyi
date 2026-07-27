from __future__ import annotations

from taiyi.domain import EventType, IdentitySnapshot, WorldlineEvent, utc_now
from taiyi.providers import MockProvider
from taiyi.storage.sqlite import payload_hash


def _event(content: str) -> WorldlineEvent:
    payload = {"content": content}
    return WorldlineEvent(
        id="evt_1",
        worldline_id="world_1",
        sequence_number=1,
        event_type=EventType.USER_MESSAGE,
        payload=payload,
        payload_hash=payload_hash(payload),
        created_at=utc_now(),
    )


def test_mock_provider_is_deterministic_and_extracts_tag() -> None:
    provider = MockProvider()
    event = _event("remember [policy]: evidence matters")
    snapshot = IdentitySnapshot(
        id="snap_1",
        core_id="core_1",
        self_description="Taiyi",
        created_at=utc_now(),
    )
    assert provider.respond(snapshot, [event], []) == provider.respond(snapshot, [event], [])
    drafts = provider.extract_memories([event])
    assert len(drafts) == 1
    assert drafts[0].content == "evidence matters"
    assert drafts[0].tags == ("policy",)

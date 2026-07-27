from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from taiyi.domain import EventType, IdentitySnapshot, WorldlineEvent, utc_now
from taiyi.providers.openai import OpenAIProvider
from taiyi.storage.sqlite import payload_hash


class FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = iter(outputs)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=next(self.outputs))


def test_openai_adapter_uses_responses_and_validates_memory() -> None:
    event_payload = {"content": "Remember this"}
    event = WorldlineEvent(
        id="evt_1",
        worldline_id="world_1",
        sequence_number=1,
        event_type=EventType.USER_MESSAGE,
        payload=event_payload,
        payload_hash=payload_hash(event_payload),
        created_at=utc_now(),
    )
    snapshot = IdentitySnapshot(
        id="snap_1",
        core_id="core_1",
        self_description="Taiyi",
        created_at=utc_now(),
    )
    extraction = json.dumps(
        [
            {
                "type": "episodic",
                "content": "The user asked to remember this.",
                "source_event_ids": ["evt_1"],
                "confidence": 0.9,
                "importance": 0.7,
                "tags": ["request"],
            }
        ]
    )
    responses = FakeResponses(["Acknowledged.", extraction])
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.model = "test-model"
    provider.client = SimpleNamespace(responses=responses)

    assert provider.respond(snapshot, [event], []) == "Acknowledged."
    drafts = provider.extract_memories([event])
    assert drafts[0].source_event_ids == ("evt_1",)
    assert [call["model"] for call in responses.calls] == ["test-model", "test-model"]

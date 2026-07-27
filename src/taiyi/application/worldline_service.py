from __future__ import annotations

from typing import Any

from taiyi.domain import EventType, WorldlineEvent
from taiyi.storage import ConflictError, Repository


class WorldlineService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def events_for_incarnation(self, incarnation_name: str) -> list[WorldlineEvent]:
        incarnation = self.repository.get_incarnation(incarnation_name)
        return self.repository.list_events(incarnation.worldline_id)

    def append_for_incarnation(
        self, incarnation_name: str, event_type: EventType, payload: dict[str, Any]
    ) -> WorldlineEvent:
        incarnation = self.repository.get_incarnation(incarnation_name)
        return self.repository.append_event(incarnation.worldline_id, event_type, payload)

    def assert_event_access(self, incarnation_name: str, event_id: str) -> WorldlineEvent:
        incarnation = self.repository.get_incarnation(incarnation_name)
        event = self.repository.get_event(event_id)
        if event.worldline_id != incarnation.worldline_id:
            raise ConflictError("cross-worldline event access is not allowed")
        return event

    def redact_event(self, event_id: str) -> int:
        return self.repository.redact_event(event_id)

from __future__ import annotations

from taiyi.application import IdentityService, MemoryService, WorldlineService
from taiyi.domain import EventType, MemoryStatus
from taiyi.providers import MockProvider
from taiyi.storage import Repository


def test_memory_provenance_and_redaction(repository: Repository) -> None:
    identity = IdentityService(repository)
    identity.initialize("Taiyi")
    identity.fork("branch")
    memory_service = MemoryService(repository, MockProvider())
    _, memories = memory_service.chat("branch", "remember [secret]: erase me")
    assert len(memories) == 1
    source = repository.get_event(memories[0].source_event_ids[0])
    assert source.event_type is EventType.USER_MESSAGE
    old_hash = source.payload_hash

    affected = WorldlineService(repository).redact_event(source.id)
    redacted = repository.get_event(source.id)
    deleted_memory = repository.get_memory(memories[0].id)
    assert affected == 1
    assert redacted.payload is None
    assert redacted.payload_hash == old_hash
    assert deleted_memory.status is MemoryStatus.DELETED
    assert memory_service.list_for_incarnation("branch") == []
    remaining_payloads = [
        event.payload
        for event in repository.list_events(source.worldline_id)
        if event.sequence_number > source.sequence_number
    ]
    assert remaining_payloads == [None, None]


def test_keyword_search_stays_within_worldline(repository: Repository) -> None:
    identity = IdentityService(repository)
    identity.initialize("Taiyi")
    identity.fork("left")
    identity.fork("right")
    service = MemoryService(repository, MockProvider())
    service.chat("left", "remember [topic]: lunar archives")
    service.chat("right", "remember [topic]: solar archives")
    results = service.search("left", "archives")
    assert len(results) == 1
    assert results[0].content == "lunar archives"
    assert service.search("left", "solar") == []

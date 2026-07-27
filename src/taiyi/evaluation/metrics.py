from __future__ import annotations

from typing import Any

from taiyi.domain import MemoryStatus
from taiyi.storage import Repository


def evaluate(repository: Repository) -> dict[str, Any]:
    core = repository.get_core()
    memories = repository.list_all_memories(include_deleted=True)
    active = [memory for memory in memories if memory.status is not MemoryStatus.DELETED]
    supported = 0
    for memory in active:
        try:
            events = [repository.get_event(event_id) for event_id in memory.source_event_ids]
        except RuntimeError:
            continue
        if events and all(event.payload is not None for event in events):
            supported += 1
    source_accuracy = supported / len(active) if active else 1.0
    deleted = [memory for memory in memories if memory.status is MemoryStatus.DELETED]
    deletion_complete = all(
        all(repository.get_event(event_id).payload is None for event_id in memory.source_event_ids)
        for memory in deleted
    )
    snapshots = repository.list_snapshots(core.id)
    descriptions = {snapshot.self_description for snapshot in snapshots}
    current = repository.get_snapshot(core.current_snapshot_id)
    accepted = [repository.get_memory(memory_id) for memory_id in current.accepted_memory_ids]
    source_worldlines = {
        memory.worldline_id for memory in active if not memory.worldline_id.startswith("merge:")
    }
    retained_worldlines = {
        memory.worldline_id for memory in accepted if not memory.worldline_id.startswith("merge:")
    }
    branch_fidelity = (
        len(retained_worldlines) / len(source_worldlines) if source_worldlines else 1.0
    )
    accepted_ids = {memory.id for memory in memories if memory.status is MemoryStatus.ACCEPTED}
    snapshotted_ids = {
        memory_id for snapshot in snapshots for memory_id in snapshot.accepted_memory_ids
    }
    pollution_resistance = (
        len(accepted_ids.intersection(snapshotted_ids)) / len(accepted_ids) if accepted_ids else 1.0
    )
    return {
        "source_accuracy": source_accuracy,
        "false_memory_rate": 1.0 - source_accuracy,
        "event_sequence_valid": all(
            [event.sequence_number for event in repository.list_events(inc.worldline_id)]
            == list(range(1, len(repository.list_events(inc.worldline_id)) + 1))
            for inc in repository.list_incarnations(core.id)
        ),
        "identity_stability": 1.0 if len(descriptions) <= 1 else 0.0,
        "branch_fidelity": branch_fidelity,
        "deletion_completeness": 1.0 if deletion_complete else 0.0,
        "pollution_resistance": pollution_resistance,
        "conflict_detection_rate": None,
        "conflict_detection_note": "requires a labeled scenario",
        "snapshot_count": len(snapshots),
        "memory_count": len(active),
    }

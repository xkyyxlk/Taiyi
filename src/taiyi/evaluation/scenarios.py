from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from taiyi.application import IdentityService, MemoryService, MergeService
from taiyi.domain import DifferenceKind, MergeStrategy
from taiyi.evaluation.metrics import evaluate
from taiyi.providers import MockProvider
from taiyi.storage import Database, Repository

SCENARIOS = ("same-origin-fork", "conflict-merge", "memory-rebirth")


def run_scenario(name: str, output_dir: Path) -> dict[str, Any]:
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario: {name}")
    scenario_dir = output_dir / name / f"run-{uuid4().hex[:12]}"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    database = Database(scenario_dir / "scenario.sqlite3")
    database.create_schema()
    repository = Repository(database)
    identity = IdentityService(repository)
    memory = MemoryService(repository, MockProvider())
    merge = MergeService(repository)
    if name == "same-origin-fork":
        result = _same_origin(identity, memory, repository)
    elif name == "conflict-merge":
        result = _conflict(identity, memory, merge)
    else:
        result = _rebirth(identity, memory, merge, repository)
    result["metrics"] = evaluate(repository)
    result["passed"] = all(result["checks"].values())
    result["output_dir"] = str(scenario_dir)
    (scenario_dir / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    database.engine.dispose()
    return result


def _same_origin(
    identity: IdentityService, memory: MemoryService, repository: Repository
) -> dict[str, Any]:
    identity.initialize("Taiyi Experiment")
    philosopher = identity.fork("philosopher")
    scientist = identity.fork("scientist")
    memory.chat("philosopher", "remember [method]: reflection is useful")
    memory.chat("scientist", "remember [method]: experiments are useful")
    philosopher_events = repository.list_events(philosopher.worldline_id)
    scientist_events = repository.list_events(scientist.worldline_id)
    return {
        "name": "same-origin-fork",
        "checks": {
            "different_worldlines": philosopher.worldline_id != scientist.worldline_id,
            "same_base_snapshot": philosopher.base_snapshot_id == scientist.base_snapshot_id,
            "event_isolation": {event.worldline_id for event in philosopher_events}
            == {philosopher.worldline_id}
            and {event.worldline_id for event in scientist_events} == {scientist.worldline_id},
        },
    }


def _conflict(
    identity: IdentityService, memory: MemoryService, merge: MergeService
) -> dict[str, Any]:
    identity.initialize("Taiyi Experiment")
    identity.fork("branch-a")
    identity.fork("branch-b")
    memory.chat("branch-a", "remember [policy]: autonomy should take precedence")
    memory.chat("branch-b", "remember [policy]: safety should take precedence")
    proposal = merge.propose("branch-a", "branch-b")
    conflict_items = [item for item in proposal.items if item.kind is DifferenceKind.CONFLICT]
    reviewed = merge.review(proposal.id, approve=True)
    snapshot = merge.apply(reviewed.id)
    return {
        "name": "conflict-merge",
        "checks": {
            "conflict_detected": len(conflict_items) == 1,
            "human_review_required": reviewed.reviewed_at is not None,
            "conflict_suspended": bool(snapshot.unresolved_conflict_ids),
        },
    }


def _rebirth(
    identity: IdentityService,
    memory: MemoryService,
    merge: MergeService,
    repository: Repository,
) -> dict[str, Any]:
    _, initial = identity.initialize("Taiyi Experiment")
    identity.fork("branch-a")
    identity.fork("branch-b")
    memory.chat("branch-a", "remember [alpha]: learned from branch A")
    memory.chat("branch-b", "remember [beta]: learned from branch B")
    proposal = merge.propose("branch-a", "branch-b")
    resolutions = {item.id: MergeStrategy.COEXIST for item in proposal.items}
    merge.review(proposal.id, approve=True, resolutions=resolutions)
    merged = merge.apply(proposal.id)
    child = identity.rebirth("next-generation")
    base = repository.get_snapshot(child.base_snapshot_id)
    return {
        "name": "memory-rebirth",
        "checks": {
            "new_snapshot": merged.id != initial.id,
            "reborn_from_merged": child.base_snapshot_id == merged.id,
            "inherits_both_memories": len(base.accepted_memory_ids) == 2,
            "provenance_preserved": all(
                repository.get_memory(memory_id).source_event_ids
                for memory_id in base.accepted_memory_ids
            ),
        },
    }

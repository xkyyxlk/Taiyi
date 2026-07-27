from __future__ import annotations

import pytest

from taiyi.application import IdentityService, MemoryService, MergeService
from taiyi.domain import DifferenceKind, MergeStrategy, ProposalStatus
from taiyi.providers import MockProvider
from taiyi.storage import ConflictError, Repository


def _branches(
    repository: Repository, left: str, right: str
) -> tuple[IdentityService, MergeService]:
    identity = IdentityService(repository)
    identity.initialize("Taiyi")
    identity.fork("left")
    identity.fork("right")
    memory = MemoryService(repository, MockProvider())
    memory.chat("left", left)
    memory.chat("right", right)
    return identity, MergeService(repository)


def test_merge_requires_review_and_preserves_snapshot(repository: Repository) -> None:
    _, merge = _branches(
        repository,
        "remember [alpha]: left knowledge",
        "remember [beta]: right knowledge",
    )
    proposal = merge.propose("left", "right")
    base = repository.get_snapshot(proposal.base_snapshot_id)
    with pytest.raises(ConflictError):
        merge.apply(proposal.id)

    reviewed = merge.review(proposal.id, approve=True)
    assert reviewed.status is ProposalStatus.APPROVED
    snapshot = merge.apply(proposal.id)
    assert snapshot.id != base.id
    assert len(snapshot.accepted_memory_ids) == 2
    assert repository.get_snapshot(base.id) == base
    assert repository.get_core().current_snapshot_id == snapshot.id


def test_conflict_is_explicit_and_can_be_synthesized(repository: Repository) -> None:
    _, merge = _branches(
        repository,
        "remember [policy]: autonomy first",
        "remember [policy]: safety first",
    )
    proposal = merge.propose("left", "right")
    conflict = next(item for item in proposal.items if item.kind is DifferenceKind.CONFLICT)
    merge.review(
        proposal.id,
        approve=True,
        resolutions={conflict.id: MergeStrategy.SYNTHESIZE},
        resolution_content={conflict.id: "Balance autonomy with safety."},
    )
    snapshot = merge.apply(proposal.id)
    assert len(snapshot.accepted_memory_ids) == 1
    synthesis = repository.get_memory(snapshot.accepted_memory_ids[0])
    assert synthesis.content == "Balance autonomy with safety."
    assert len(synthesis.source_event_ids) == 2


def test_rollback_repoints_without_deleting_history(repository: Repository) -> None:
    identity, merge = _branches(
        repository,
        "remember [alpha]: left",
        "remember [beta]: right",
    )
    initial = repository.get_core().current_snapshot_id
    proposal = merge.propose("left", "right")
    merge.review(proposal.id, approve=True)
    merged = merge.apply(proposal.id)
    identity.rollback(initial)
    assert repository.get_core().current_snapshot_id == initial
    assert repository.get_snapshot(merged.id).id == merged.id


def test_stale_proposal_cannot_overwrite_new_snapshot(repository: Repository) -> None:
    _, merge = _branches(
        repository,
        "remember [alpha]: left",
        "remember [beta]: right",
    )
    first = merge.propose("left", "right")
    second = merge.propose("left", "right")
    merge.review(first.id, approve=True)
    merge.review(second.id, approve=True)
    merge.apply(first.id)
    with pytest.raises(ConflictError):
        merge.apply(second.id)

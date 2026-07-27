from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping

from taiyi.domain import (
    DifferenceKind,
    DiffItem,
    IdentitySnapshot,
    Memory,
    MemoryDraft,
    MemoryStatus,
    MergeProposal,
    MergeStrategy,
    ProposalStatus,
    new_id,
    utc_now,
)
from taiyi.storage import ConflictError, Repository


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", text.casefold()).strip()


class MergeService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def diff(self, incarnation_a: str, incarnation_b: str) -> list[DiffItem]:
        left = self.repository.get_incarnation(incarnation_a)
        right = self.repository.get_incarnation(incarnation_b)
        if left.id == right.id:
            raise ConflictError("choose two different incarnations")
        if left.core_id != right.core_id:
            raise ConflictError("incarnations belong to different identity cores")
        left_memories = self.repository.list_memories(left.worldline_id)
        right_memories = self.repository.list_memories(right.worldline_id)
        return self._compare(left_memories, right_memories)

    def propose(self, incarnation_a: str, incarnation_b: str) -> MergeProposal:
        left = self.repository.get_incarnation(incarnation_a)
        right = self.repository.get_incarnation(incarnation_b)
        core = self.repository.get_core(left.core_id)
        items = self.diff(incarnation_a, incarnation_b)
        proposal = MergeProposal(
            id=new_id("merge"),
            core_id=core.id,
            base_snapshot_id=core.current_snapshot_id,
            incarnation_ids=(left.id, right.id),
            worldline_ids=(left.worldline_id, right.worldline_id),
            items=tuple(items),
            status=ProposalStatus.PENDING,
            created_at=utc_now(),
        )
        return self.repository.create_proposal(proposal)

    def review(
        self,
        proposal_id: str,
        approve: bool,
        resolutions: Mapping[str, MergeStrategy] | None = None,
        resolution_content: Mapping[str, str] | None = None,
    ) -> MergeProposal:
        proposal = self.repository.get_proposal(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise ConflictError("only a pending proposal can be reviewed")
        if not approve:
            reviewed = proposal.model_copy(
                update={"status": ProposalStatus.REJECTED, "reviewed_at": utc_now()}
            )
        else:
            chosen = {item.id: item.suggested_strategy for item in proposal.items}
            chosen.update(resolutions or {})
            reviewed = proposal.model_copy(
                update={
                    "status": ProposalStatus.APPROVED,
                    "resolutions": chosen,
                    "resolution_content": dict(resolution_content or {}),
                    "reviewed_at": utc_now(),
                }
            )
        self.repository.save_proposal(reviewed)
        return reviewed

    def apply(self, proposal_id: str) -> IdentitySnapshot:
        proposal = self.repository.get_proposal(proposal_id)
        if proposal.status is not ProposalStatus.APPROVED:
            raise ConflictError("proposal must be approved before it can be applied")
        base = self.repository.get_snapshot(proposal.base_snapshot_id)
        accepted = list(base.accepted_memory_ids)
        unresolved = list(base.unresolved_conflict_ids)
        synthesized: list[Memory] = []
        for item in proposal.items:
            strategy = proposal.resolutions[item.id]
            memories = [self.repository.get_memory(memory_id) for memory_id in item.memory_ids]
            if any(memory.status is MemoryStatus.DELETED for memory in memories):
                raise ConflictError("proposal references deleted memory; create a new proposal")
            if strategy is MergeStrategy.COEXIST:
                accepted.extend(memory.id for memory in memories)
            elif strategy is MergeStrategy.SELECT:
                selection = proposal.resolution_content.get(item.id, item.memory_ids[0])
                if selection not in item.memory_ids:
                    raise ConflictError(f"selected memory is not part of item {item.id}")
                accepted.append(selection)
            elif strategy is MergeStrategy.SYNTHESIZE:
                content = proposal.resolution_content.get(item.id)
                if not content:
                    content = " | ".join(memory.content for memory in memories)
                draft = MemoryDraft(
                    type=memories[0].type,
                    content=content,
                    source_event_ids=tuple(
                        dict.fromkeys(
                            event_id for memory in memories for event_id in memory.source_event_ids
                        )
                    ),
                    confidence=min(memory.confidence for memory in memories),
                    importance=max(memory.importance for memory in memories),
                    tags=tuple(dict.fromkeys(tag for memory in memories for tag in memory.tags)),
                )
                synthesis = Memory(
                    id=new_id("mem"),
                    worldline_id=f"merge:{proposal.id}",
                    type=draft.type,
                    content=draft.content,
                    source_event_ids=draft.source_event_ids,
                    extractor="human-reviewed-merge",
                    prompt_version="merge-v1",
                    confidence=draft.confidence,
                    importance=draft.importance,
                    tags=draft.tags,
                    status=MemoryStatus.ACCEPTED,
                    created_at=utc_now(),
                )
                synthesized.append(synthesis)
                accepted.append(synthesis.id)
            elif strategy is MergeStrategy.SUSPEND:
                unresolved.append(item.id)
            elif strategy is MergeStrategy.REJECT:
                continue
        snapshot = IdentitySnapshot(
            id=new_id("snap"),
            core_id=base.core_id,
            parent_snapshot_ids=(base.id,),
            self_description=base.self_description,
            accepted_memory_ids=tuple(dict.fromkeys(accepted)),
            belief_ids=base.belief_ids,
            unresolved_conflict_ids=tuple(dict.fromkeys(unresolved)),
            created_by_merge_id=proposal.id,
            created_at=utc_now(),
        )
        self.repository.apply_merge(
            proposal,
            snapshot,
            snapshot.accepted_memory_ids,
            new_memories=synthesized,
        )
        return snapshot

    @staticmethod
    def _compare(left: list[Memory], right: list[Memory]) -> list[DiffItem]:
        items: list[DiffItem] = []
        used_left: set[str] = set()
        used_right: set[str] = set()
        right_by_content: dict[str, list[Memory]] = defaultdict(list)
        for memory in right:
            right_by_content[_normalize(memory.content)].append(memory)
        for memory in left:
            matches = right_by_content.get(_normalize(memory.content), [])
            match = next(
                (candidate for candidate in matches if candidate.id not in used_right), None
            )
            if match:
                used_left.add(memory.id)
                used_right.add(match.id)
                items.append(
                    DiffItem(
                        id=new_id("diff"),
                        kind=DifferenceKind.DUPLICATE,
                        memory_ids=(memory.id, match.id),
                        reason="normalized contents are equal",
                        suggested_strategy=MergeStrategy.SELECT,
                    )
                )
        for l_memory in left:
            if l_memory.id in used_left:
                continue
            conflict = next(
                (
                    r_memory
                    for r_memory in right
                    if r_memory.id not in used_right
                    and l_memory.type is r_memory.type
                    and set(l_memory.tags).intersection(r_memory.tags)
                    and _normalize(l_memory.content) != _normalize(r_memory.content)
                ),
                None,
            )
            if conflict:
                used_left.add(l_memory.id)
                used_right.add(conflict.id)
                items.append(
                    DiffItem(
                        id=new_id("diff"),
                        kind=DifferenceKind.CONFLICT,
                        memory_ids=(l_memory.id, conflict.id),
                        reason="same typed topic has divergent content",
                        suggested_strategy=MergeStrategy.SUSPEND,
                    )
                )
        for memory in [*left, *right]:
            used = used_left if memory in left else used_right
            if memory.id not in used:
                items.append(
                    DiffItem(
                        id=new_id("diff"),
                        kind=DifferenceKind.SUPPLEMENT,
                        memory_ids=(memory.id,),
                        reason="unique information from one worldline",
                        suggested_strategy=MergeStrategy.COEXIST,
                    )
                )
        return items

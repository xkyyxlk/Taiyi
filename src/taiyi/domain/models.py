from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class IncarnationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class EventType(StrEnum):
    USER_MESSAGE = "user_message"
    MODEL_RESPONSE = "model_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM_OPERATION = "system_operation"
    MEMORY_EXTRACTION = "memory_extraction"
    MERGE = "merge"
    ROLLBACK = "rollback"


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    RELATIONAL = "relational"
    IDENTITY = "identity"
    VALUE = "value"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DELETED = "deleted"


class DifferenceKind(StrEnum):
    DUPLICATE = "duplicate"
    SUPPLEMENT = "supplement"
    CONFLICT = "conflict"


class MergeStrategy(StrEnum):
    COEXIST = "coexist"
    SELECT = "select"
    SYNTHESIZE = "synthesize"
    SUSPEND = "suspend"
    REJECT = "reject"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class IdentityCore(FrozenModel):
    id: str
    name: str
    created_at: datetime
    current_snapshot_id: str


class IdentitySnapshot(FrozenModel):
    id: str
    core_id: str
    parent_snapshot_ids: tuple[str, ...] = ()
    self_description: str
    accepted_memory_ids: tuple[str, ...] = ()
    belief_ids: tuple[str, ...] = ()
    unresolved_conflict_ids: tuple[str, ...] = ()
    created_by_merge_id: str | None = None
    created_at: datetime


class Incarnation(FrozenModel):
    id: str
    name: str
    core_id: str
    base_snapshot_id: str
    worldline_id: str
    status: IncarnationStatus
    created_at: datetime


class WorldlineEvent(FrozenModel):
    id: str
    worldline_id: str
    sequence_number: int = Field(ge=1)
    event_type: EventType
    payload: dict[str, Any] | None
    payload_hash: str
    payload_deleted_at: datetime | None = None
    created_at: datetime


class MemoryDraft(FrozenModel):
    type: MemoryType
    content: str = Field(min_length=1)
    source_event_ids: tuple[str, ...] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    tags: tuple[str, ...] = ()


class Memory(FrozenModel):
    id: str
    worldline_id: str
    type: MemoryType
    content: str
    source_event_ids: tuple[str, ...]
    extractor: str
    prompt_version: str
    confidence: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    tags: tuple[str, ...] = ()
    status: MemoryStatus
    created_at: datetime


class DiffItem(FrozenModel):
    id: str
    kind: DifferenceKind
    memory_ids: tuple[str, ...] = Field(min_length=1)
    reason: str
    suggested_strategy: MergeStrategy


class MergeProposal(FrozenModel):
    id: str
    core_id: str
    base_snapshot_id: str
    incarnation_ids: tuple[str, ...] = Field(min_length=2)
    worldline_ids: tuple[str, ...] = Field(min_length=2)
    items: tuple[DiffItem, ...]
    resolutions: dict[str, MergeStrategy] = Field(default_factory=dict)
    resolution_content: dict[str, str] = Field(default_factory=dict)
    status: ProposalStatus
    reviewed_at: datetime | None = None
    applied_snapshot_id: str | None = None
    created_at: datetime

    @model_validator(mode="after")
    def resolutions_reference_items(self) -> MergeProposal:
        item_ids = {item.id for item in self.items}
        if not set(self.resolutions).issubset(item_ids):
            raise ValueError("resolution references an unknown diff item")
        if not set(self.resolution_content).issubset(item_ids):
            raise ValueError("resolution content references an unknown diff item")
        return self


class AuditEvent(FrozenModel):
    id: str
    core_id: str | None
    operation: str
    payload: dict[str, Any]
    created_at: datetime

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

PROTOCOL_VERSION = "1.0"

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r".*\S.*"),
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
VersionString = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r".*\S.*"),
]


def _require_datetime_string(value: object) -> object:
    if not isinstance(value, str):
        raise ValueError("时间字段必须使用 RFC 3339 字符串")
    return value


Timestamp = Annotated[AwareDatetime, BeforeValidator(_require_datetime_string)]


class ProtocolModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RecordType(StrEnum):
    MANIFEST = "manifest"
    SNAPSHOT = "snapshot"
    EVENT = "event"
    MEMORY = "memory"


class SnapshotRole(StrEnum):
    BEFORE = "before"
    AFTER = "after"


class ScopeKind(StrEnum):
    AGENT = "agent"
    USER = "user"
    TENANT = "tenant"
    SESSION = "session"
    CUSTOM = "custom"


class EventType(StrEnum):
    USER_INPUT = "user_input"
    MODEL_OUTPUT = "model_output"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DOCUMENT_READ = "document_read"
    MEMORY_WRITE = "memory_write"
    SYSTEM = "system"


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"
    RELATIONAL = "relational"
    CUSTOM = "custom"


class Scope(ProtocolModel):
    kind: ScopeKind
    id: Identifier


class Producer(ProtocolModel):
    name: Identifier
    version: VersionString


class BaseRecord(ProtocolModel):
    protocol_version: Literal["1.0"]
    sequence_number: Annotated[int, Field(ge=1, strict=True)]


class ManifestRecord(BaseRecord):
    record_type: Literal[RecordType.MANIFEST]
    project_id: Identifier
    run_id: Identifier
    baseline_run_id: Identifier | None = None
    captured_at: Timestamp
    producer: Producer
    model_version: VersionString
    prompt_version: VersionString
    tool_versions: dict[Identifier, VersionString]
    writer_version: VersionString


class SnapshotRecord(BaseRecord):
    record_type: Literal[RecordType.SNAPSHOT]
    snapshot_id: Identifier
    snapshot_role: SnapshotRole
    captured_at: Timestamp


class EventRecord(BaseRecord):
    record_type: Literal[RecordType.EVENT]
    event_id: Identifier
    event_type: EventType
    scope: Scope
    occurred_at: Timestamp
    content_hash: Sha256Digest
    content: str | None = None
    parent_event_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def content_matches_hash(self) -> EventRecord:
        if (
            self.content is not None
            and sha256(self.content.encode("utf-8")).hexdigest() != self.content_hash
        ):
            raise ValueError("事件正文与 content_hash 不一致")
        return self


class MemoryRecord(BaseRecord):
    record_type: Literal[RecordType.MEMORY]
    snapshot_id: Identifier
    memory_id: Identifier
    scope: Scope
    memory_type: MemoryType
    content_hash: Sha256Digest
    content: str | None = None
    source_event_ids: tuple[Identifier, ...]
    created_at: Timestamp
    updated_at: Timestamp
    writer_version: VersionString
    memory_version: VersionString | None = None

    @model_validator(mode="after")
    def memory_fields_are_consistent(self) -> MemoryRecord:
        if (
            self.content is not None
            and sha256(self.content.encode("utf-8")).hexdigest() != self.content_hash
        ):
            raise ValueError("记忆正文与 content_hash 不一致")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at 不得早于 created_at")
        return self


AnalysisRecord = ManifestRecord | SnapshotRecord | EventRecord | MemoryRecord


def content_digest(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()

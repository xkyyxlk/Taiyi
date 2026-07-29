from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field

from taiyi.analysis.models import Identifier, ProtocolModel, RecordType, Sha256Digest, SnapshotRole

REPORT_VERSION: Literal["1.0"] = "1.0"
POLICY_VERSION: Literal["1.0"] = "1.0"

RULE_MISSING_SOURCE = "TY-PROV-001"
RULE_SCOPE_MISMATCH = "TY-SCOPE-001"
RULE_PARENT_AFTER_CHILD = "TY-AUDIT-001"
RULE_EVENT_CYCLE = "TY-AUDIT-002"

RULE_IDS = frozenset(
    {
        RULE_MISSING_SOURCE,
        RULE_SCOPE_MISMATCH,
        RULE_PARENT_AFTER_CHILD,
        RULE_EVENT_CYCLE,
    }
)


class ResultModel(ProtocolModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)


class MemoryChangeKind(StrEnum):
    ADDED = "added"
    DELETED = "deleted"
    CONTENT_MODIFIED = "content_modified"
    STRUCTURE_CHANGED = "structure_changed"


class FindingLevel(StrEnum):
    IGNORE = "ignore"
    WARNING = "warning"
    ERROR = "error"


class EvidenceReference(ResultModel):
    record_type: Literal[RecordType.EVENT, RecordType.MEMORY]
    record_id: Identifier
    sequence_number: int = Field(ge=1, strict=True)
    snapshot_role: SnapshotRole | None = None


class MemoryChange(ResultModel):
    memory_id: Identifier
    kinds: tuple[MemoryChangeKind, ...] = Field(min_length=1)
    changed_fields: tuple[str, ...] = ()
    before: EvidenceReference | None = None
    after: EvidenceReference | None = None


class Finding(ResultModel):
    rule_id: str
    default_level: FindingLevel
    effective_level: FindingLevel
    message: str
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1)


class Policy(ResultModel):
    version: Literal["1.0"] = POLICY_VERSION
    overrides: dict[str, FindingLevel] = Field(default_factory=dict)


class AnalysisSummary(ResultModel):
    added: int = Field(ge=0)
    deleted: int = Field(ge=0)
    content_modified: int = Field(ge=0)
    structure_changed: int = Field(ge=0)
    ignored_findings: int = Field(ge=0)
    warnings: int = Field(ge=0)
    errors: int = Field(ge=0)


class AnalysisReport(ResultModel):
    report_version: Literal["1.0"] = REPORT_VERSION
    tool_version: str
    protocol_version: Literal["1.0"]
    policy_version: Literal["1.0"]
    input_sha256: Sha256Digest
    project_id: Identifier
    run_id: Identifier
    changes: tuple[MemoryChange, ...]
    findings: tuple[Finding, ...]
    summary: AnalysisSummary
    reproduction_command: tuple[str, ...] = Field(min_length=4)
    exit_code: Literal[0, 2]

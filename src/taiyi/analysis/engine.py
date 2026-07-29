from __future__ import annotations

from hashlib import sha256

from taiyi import __version__
from taiyi.analysis.models import EventRecord, MemoryRecord, RecordType, SnapshotRole
from taiyi.analysis.protocol import AnalysisInput, parse_jsonl
from taiyi.analysis.results import (
    RULE_EVENT_CYCLE,
    RULE_IDS,
    RULE_MISSING_SOURCE,
    RULE_PARENT_AFTER_CHILD,
    RULE_SCOPE_MISMATCH,
    AnalysisReport,
    AnalysisSummary,
    EvidenceReference,
    Finding,
    FindingLevel,
    MemoryChange,
    MemoryChangeKind,
    Policy,
)

_STRUCTURE_FIELDS = (
    "scope",
    "memory_type",
    "source_event_ids",
    "created_at",
    "updated_at",
    "writer_version",
    "memory_version",
)


def analyze_jsonl(
    content: str,
    policy: Policy | None = None,
    reproduction_command: tuple[str, ...] = (
        "taiyi",
        "analyze",
        "check",
        "<input.jsonl>",
    ),
) -> AnalysisReport:
    analysis_input = parse_jsonl(content)
    return analyze_input(
        analysis_input,
        input_sha256=sha256(content.encode("utf-8")).hexdigest(),
        policy=policy,
        reproduction_command=reproduction_command,
    )


def analyze_input(
    analysis_input: AnalysisInput,
    *,
    input_sha256: str,
    policy: Policy | None = None,
    reproduction_command: tuple[str, ...] = (
        "taiyi",
        "analyze",
        "check",
        "<input.jsonl>",
    ),
) -> AnalysisReport:
    effective_policy = policy or Policy()
    unknown_rule_ids = set(effective_policy.overrides) - RULE_IDS
    if unknown_rule_ids:
        raise ValueError(f"策略引用未知规则：{', '.join(sorted(unknown_rule_ids))}")

    changes = _compare_memories(analysis_input)
    findings = _apply_policy(_run_rules(analysis_input), effective_policy)
    summary = _summarize(changes, findings)
    exit_code = 2 if summary.errors else 0

    return AnalysisReport(
        tool_version=__version__,
        protocol_version=analysis_input.manifest.protocol_version,
        policy_version=effective_policy.version,
        input_sha256=input_sha256,
        project_id=analysis_input.manifest.project_id,
        run_id=analysis_input.manifest.run_id,
        changes=changes,
        findings=findings,
        summary=summary,
        reproduction_command=reproduction_command,
        exit_code=exit_code,
    )


def _memory_reference(memory: MemoryRecord, role: SnapshotRole) -> EvidenceReference:
    return EvidenceReference(
        record_type=RecordType.MEMORY,
        record_id=memory.memory_id,
        sequence_number=memory.sequence_number,
        snapshot_role=role,
    )


def _event_reference(event: EventRecord) -> EvidenceReference:
    return EvidenceReference(
        record_type=RecordType.EVENT,
        record_id=event.event_id,
        sequence_number=event.sequence_number,
    )


def _compare_memories(analysis_input: AnalysisInput) -> tuple[MemoryChange, ...]:
    before = {memory.memory_id: memory for memory in analysis_input.before_memories}
    after = {memory.memory_id: memory for memory in analysis_input.after_memories}
    changes: list[MemoryChange] = []

    for memory_id in sorted(before.keys() | after.keys()):
        old = before.get(memory_id)
        new = after.get(memory_id)
        if old is None and new is not None:
            changes.append(
                MemoryChange(
                    memory_id=memory_id,
                    kinds=(MemoryChangeKind.ADDED,),
                    after=_memory_reference(new, SnapshotRole.AFTER),
                )
            )
            continue
        if new is None and old is not None:
            changes.append(
                MemoryChange(
                    memory_id=memory_id,
                    kinds=(MemoryChangeKind.DELETED,),
                    before=_memory_reference(old, SnapshotRole.BEFORE),
                )
            )
            continue
        if old is None or new is None:
            continue

        changed_fields: list[str] = []
        kinds: list[MemoryChangeKind] = []
        if old.content_hash != new.content_hash:
            changed_fields.append("content_hash")
            kinds.append(MemoryChangeKind.CONTENT_MODIFIED)
        for field_name in _STRUCTURE_FIELDS:
            if getattr(old, field_name) != getattr(new, field_name):
                changed_fields.append(field_name)
        if any(field_name != "content_hash" for field_name in changed_fields):
            kinds.append(MemoryChangeKind.STRUCTURE_CHANGED)
        if not kinds:
            continue
        changes.append(
            MemoryChange(
                memory_id=memory_id,
                kinds=tuple(kinds),
                changed_fields=tuple(changed_fields),
                before=_memory_reference(old, SnapshotRole.BEFORE),
                after=_memory_reference(new, SnapshotRole.AFTER),
            )
        )
    return tuple(changes)


def _run_rules(analysis_input: AnalysisInput) -> tuple[Finding, ...]:
    events_by_id = {event.event_id: event for event in analysis_input.events}
    findings: list[Finding] = []

    for role, memories in (
        (SnapshotRole.BEFORE, analysis_input.before_memories),
        (SnapshotRole.AFTER, analysis_input.after_memories),
    ):
        for memory in memories:
            memory_ref = _memory_reference(memory, role)
            if not memory.source_event_ids:
                findings.append(
                    Finding(
                        rule_id=RULE_MISSING_SOURCE,
                        default_level=FindingLevel.ERROR,
                        effective_level=FindingLevel.ERROR,
                        message="记忆缺少显式来源事件",
                        evidence=(memory_ref,),
                    )
                )
            for source_id in memory.source_event_ids:
                source = events_by_id[source_id]
                if source.scope != memory.scope:
                    findings.append(
                        Finding(
                            rule_id=RULE_SCOPE_MISMATCH,
                            default_level=FindingLevel.ERROR,
                            effective_level=FindingLevel.ERROR,
                            message="记忆作用域与来源事件作用域不一致",
                            evidence=(memory_ref, _event_reference(source)),
                        )
                    )

    for event in analysis_input.events:
        for parent_id in event.parent_event_ids:
            parent = events_by_id[parent_id]
            if parent.occurred_at > event.occurred_at:
                findings.append(
                    Finding(
                        rule_id=RULE_PARENT_AFTER_CHILD,
                        default_level=FindingLevel.ERROR,
                        effective_level=FindingLevel.ERROR,
                        message="父事件发生时间晚于子事件",
                        evidence=(_event_reference(parent), _event_reference(event)),
                    )
                )

    for cycle in _event_cycles(analysis_input.events):
        findings.append(
            Finding(
                rule_id=RULE_EVENT_CYCLE,
                default_level=FindingLevel.ERROR,
                effective_level=FindingLevel.ERROR,
                message="事件父子关系形成循环",
                evidence=tuple(_event_reference(events_by_id[event_id]) for event_id in cycle),
            )
        )

    findings.sort(key=_finding_sort_key)
    return tuple(findings)


def _event_cycles(events: tuple[EventRecord, ...]) -> tuple[tuple[str, ...], ...]:
    parents = {event.event_id: event.parent_event_ids for event in events}
    visiting: list[str] = []
    visited: set[str] = set()
    cycles: set[tuple[str, ...]] = set()

    def visit(event_id: str) -> None:
        if event_id in visiting:
            start = visiting.index(event_id)
            cycles.add(tuple(sorted(visiting[start:])))
            return
        if event_id in visited:
            return
        visiting.append(event_id)
        for parent_id in parents[event_id]:
            visit(parent_id)
        visiting.pop()
        visited.add(event_id)

    for event_id in sorted(parents):
        visit(event_id)
    return tuple(sorted(cycles))


def _apply_policy(findings: tuple[Finding, ...], policy: Policy) -> tuple[Finding, ...]:
    return tuple(
        finding.model_copy(
            update={"effective_level": policy.overrides.get(finding.rule_id, finding.default_level)}
        )
        for finding in findings
    )


def _finding_sort_key(finding: Finding) -> tuple[object, ...]:
    return (
        finding.rule_id,
        tuple(
            (
                evidence.snapshot_role.value if evidence.snapshot_role is not None else "",
                evidence.record_type.value,
                evidence.record_id,
                evidence.sequence_number,
            )
            for evidence in finding.evidence
        ),
    )


def _summarize(changes: tuple[MemoryChange, ...], findings: tuple[Finding, ...]) -> AnalysisSummary:
    kind_counts = {
        kind: sum(kind in change.kinds for change in changes) for kind in MemoryChangeKind
    }
    return AnalysisSummary(
        added=kind_counts[MemoryChangeKind.ADDED],
        deleted=kind_counts[MemoryChangeKind.DELETED],
        content_modified=kind_counts[MemoryChangeKind.CONTENT_MODIFIED],
        structure_changed=kind_counts[MemoryChangeKind.STRUCTURE_CHANGED],
        ignored_findings=sum(
            finding.effective_level is FindingLevel.IGNORE for finding in findings
        ),
        warnings=sum(finding.effective_level is FindingLevel.WARNING for finding in findings),
        errors=sum(finding.effective_level is FindingLevel.ERROR for finding in findings),
    )

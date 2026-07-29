from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from itertools import product
from typing import Literal

from pydantic import Field

from taiyi import __version__
from taiyi.analysis.engine import analyze_jsonl
from taiyi.analysis.models import ProtocolModel, content_digest
from taiyi.analysis.results import (
    POLICY_VERSION,
    REPORT_VERSION,
    RULE_MISSING_SOURCE,
    RULE_SCOPE_MISMATCH,
    AnalysisSummary,
)

GENERATOR_VERSION = "1.0"
DEFAULT_SCENARIO_SEED = 20260729
COMMIT_SCENARIO_COUNT = 1000


class MemoryPresence(StrEnum):
    BOTH = "both"
    BEFORE_ONLY = "before_only"
    AFTER_ONLY = "after_only"


class SourceMode(StrEnum):
    COMPLETE = "complete"
    MISSING = "missing"


class ScopeMode(StrEnum):
    SAME = "same"
    MISMATCH = "mismatch"


class ScenarioDimensions(ProtocolModel):
    presence: MemoryPresence
    content_changed: bool
    source_mode: SourceMode
    scope_mode: ScopeMode
    writer_changed: bool


class ExpectedAnalysis(ProtocolModel):
    rule_ids: tuple[str, ...]
    exit_code: Literal[0, 2]
    summary: AnalysisSummary


class GeneratedScenario(ProtocolModel):
    generator_version: Literal["1.0"] = "1.0"
    seed: int
    case_index: int = Field(ge=1)
    case_id: str
    dimensions: ScenarioDimensions
    input_sha256: str
    jsonl: str
    expected: ExpectedAnalysis


class ScenarioMismatch(ProtocolModel):
    case_id: str
    differences: tuple[str, ...] = Field(min_length=1)


class ScenarioRunSummary(ProtocolModel):
    generator_version: Literal["1.0"] = "1.0"
    tool_version: str = __version__
    protocol_version: Literal["1.0"] = "1.0"
    report_version: Literal["1.0"] = REPORT_VERSION
    policy_version: Literal["1.0"] = POLICY_VERSION
    seed: int
    case_count: int = Field(ge=1)
    suite_sha256: str
    mismatches: tuple[ScenarioMismatch, ...]


@dataclass(frozen=True)
class _CaseSpec:
    presence: MemoryPresence
    content_changed: bool = False
    source_mode: SourceMode = SourceMode.COMPLETE
    scope_mode: ScopeMode = ScopeMode.SAME
    writer_changed: bool = False

    @property
    def key(self) -> str:
        return ":".join(
            (
                self.presence.value,
                str(int(self.content_changed)),
                self.source_mode.value,
                self.scope_mode.value,
                str(int(self.writer_changed)),
            )
        )


def _case_specs() -> tuple[_CaseSpec, ...]:
    specs = [
        _CaseSpec(presence=MemoryPresence.BEFORE_ONLY),
        _CaseSpec(presence=MemoryPresence.AFTER_ONLY),
        _CaseSpec(presence=MemoryPresence.AFTER_ONLY, source_mode=SourceMode.MISSING),
        _CaseSpec(presence=MemoryPresence.AFTER_ONLY, scope_mode=ScopeMode.MISMATCH),
    ]
    for content_changed, source_mode, scope_mode, writer_changed in product(
        (False, True),
        tuple(SourceMode),
        tuple(ScopeMode),
        (False, True),
    ):
        specs.append(
            _CaseSpec(
                presence=MemoryPresence.BOTH,
                content_changed=content_changed,
                source_mode=source_mode,
                scope_mode=scope_mode,
                writer_changed=writer_changed,
            )
        )
    return tuple(specs)


def _ordered_specs(seed: int, epoch: int) -> tuple[_CaseSpec, ...]:
    return tuple(
        sorted(
            _case_specs(),
            key=lambda spec: sha256(f"{seed}:{epoch}:{spec.key}".encode()).hexdigest(),
        )
    )


def generate_scenarios(seed: int, case_count: int) -> tuple[GeneratedScenario, ...]:
    if case_count < 1:
        raise ValueError("case_count 必须大于零")
    scenarios: list[GeneratedScenario] = []
    specs_per_epoch = len(_case_specs())
    for offset in range(case_count):
        epoch, position = divmod(offset, specs_per_epoch)
        spec = _ordered_specs(seed, epoch)[position]
        scenarios.append(_build_scenario(seed, offset + 1, spec))
    return tuple(scenarios)


def _build_scenario(seed: int, case_index: int, spec: _CaseSpec) -> GeneratedScenario:
    case_id = f"GEN-{seed}-{case_index:06d}"
    event_id = f"event_{case_index}"
    memory_id = f"memory_{case_index}"
    before_id = f"snapshot_before_{case_index}"
    after_id = f"snapshot_after_{case_index}"
    records: list[dict[str, object]] = [
        {
            "protocol_version": "1.0",
            "record_type": "manifest",
            "sequence_number": 1,
            "project_id": "generated_project",
            "run_id": f"generated_run_{seed}_{case_index}",
            "baseline_run_id": "generated_baseline",
            "captured_at": "2026-07-29T06:00:00Z",
            "producer": {"name": "taiyi-generator", "version": GENERATOR_VERSION},
            "model_version": "model-a",
            "prompt_version": "prompt-v1",
            "tool_versions": {},
            "writer_version": "writer-v1",
        },
        {
            "protocol_version": "1.0",
            "record_type": "snapshot",
            "sequence_number": 2,
            "snapshot_id": before_id,
            "snapshot_role": "before",
            "captured_at": "2026-07-29T06:00:00Z",
        },
    ]
    if spec.presence is not MemoryPresence.AFTER_ONLY:
        records.append(
            _memory_record(
                snapshot_id=before_id,
                memory_id=memory_id,
                content="基线记忆",
                source_event_ids=[event_id],
                scope_id="user_alice",
                writer_version="writer-v1",
                memory_version="1",
                updated_at="2026-07-29T05:00:00Z",
            )
        )
    records.extend(
        [
            {
                "protocol_version": "1.0",
                "record_type": "event",
                "sequence_number": 0,
                "event_id": event_id,
                "event_type": "user_input",
                "scope": {"kind": "user", "id": "user_alice"},
                "occurred_at": "2026-07-29T06:01:00Z",
                "content_hash": content_digest("来源事件"),
                "parent_event_ids": [],
            },
            {
                "protocol_version": "1.0",
                "record_type": "snapshot",
                "sequence_number": 0,
                "snapshot_id": after_id,
                "snapshot_role": "after",
                "captured_at": "2026-07-29T06:02:00Z",
            },
        ]
    )
    if spec.presence is not MemoryPresence.BEFORE_ONLY:
        changed = (
            spec.presence is MemoryPresence.AFTER_ONLY
            or spec.content_changed
            or spec.source_mode is SourceMode.MISSING
            or spec.scope_mode is ScopeMode.MISMATCH
            or spec.writer_changed
        )
        records.append(
            _memory_record(
                snapshot_id=after_id,
                memory_id=memory_id,
                content="变更记忆" if spec.content_changed else "基线记忆",
                source_event_ids=[] if spec.source_mode is SourceMode.MISSING else [event_id],
                scope_id="user_bob" if spec.scope_mode is ScopeMode.MISMATCH else "user_alice",
                writer_version="writer-v2" if spec.writer_changed else "writer-v1",
                memory_version="2" if changed else "1",
                updated_at="2026-07-29T06:02:00Z" if changed else "2026-07-29T05:00:00Z",
            )
        )
    for sequence_number, record in enumerate(records, 1):
        record["sequence_number"] = sequence_number
    jsonl = (
        "\n".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records
        )
        + "\n"
    )
    return GeneratedScenario(
        seed=seed,
        case_index=case_index,
        case_id=case_id,
        dimensions=ScenarioDimensions(
            presence=spec.presence,
            content_changed=spec.content_changed,
            source_mode=spec.source_mode,
            scope_mode=spec.scope_mode,
            writer_changed=spec.writer_changed,
        ),
        input_sha256=sha256(jsonl.encode()).hexdigest(),
        jsonl=jsonl,
        expected=_expected_analysis(spec),
    )


def _memory_record(
    *,
    snapshot_id: str,
    memory_id: str,
    content: str,
    source_event_ids: list[str],
    scope_id: str,
    writer_version: str,
    memory_version: str,
    updated_at: str,
) -> dict[str, object]:
    return {
        "protocol_version": "1.0",
        "record_type": "memory",
        "sequence_number": 0,
        "snapshot_id": snapshot_id,
        "memory_id": memory_id,
        "scope": {"kind": "user", "id": scope_id},
        "memory_type": "semantic",
        "content_hash": content_digest(content),
        "source_event_ids": source_event_ids,
        "created_at": "2026-07-29T05:00:00Z",
        "updated_at": updated_at,
        "writer_version": writer_version,
        "memory_version": memory_version,
    }


def _expected_analysis(spec: _CaseSpec) -> ExpectedAnalysis:
    added = int(spec.presence is MemoryPresence.AFTER_ONLY)
    deleted = int(spec.presence is MemoryPresence.BEFORE_ONLY)
    content_modified = int(spec.presence is MemoryPresence.BOTH and spec.content_changed)
    structure_changed = int(
        spec.presence is MemoryPresence.BOTH
        and (
            spec.content_changed
            or spec.source_mode is SourceMode.MISSING
            or spec.scope_mode is ScopeMode.MISMATCH
            or spec.writer_changed
        )
    )
    rule_ids: list[str] = []
    if spec.presence is not MemoryPresence.BEFORE_ONLY:
        if spec.source_mode is SourceMode.MISSING:
            rule_ids.append(RULE_MISSING_SOURCE)
        elif spec.scope_mode is ScopeMode.MISMATCH:
            rule_ids.append(RULE_SCOPE_MISMATCH)
    errors = len(rule_ids)
    return ExpectedAnalysis(
        rule_ids=tuple(rule_ids),
        exit_code=2 if errors else 0,
        summary=AnalysisSummary(
            added=added,
            deleted=deleted,
            content_modified=content_modified,
            structure_changed=structure_changed,
            ignored_findings=0,
            warnings=0,
            errors=errors,
        ),
    )


def verify_generated_scenarios(
    scenarios: tuple[GeneratedScenario, ...],
) -> ScenarioRunSummary:
    if not scenarios:
        raise ValueError("待验证场景不能为空")
    seed = scenarios[0].seed
    if any(scenario.seed != seed for scenario in scenarios):
        raise ValueError("同一场景套件必须使用相同种子")
    mismatches: list[ScenarioMismatch] = []
    for scenario in scenarios:
        report = analyze_jsonl(scenario.jsonl)
        differences: list[str] = []
        actual_rule_ids = tuple(finding.rule_id for finding in report.findings)
        if actual_rule_ids != scenario.expected.rule_ids:
            differences.append("规则编号不一致")
        if report.exit_code != scenario.expected.exit_code:
            differences.append("退出码不一致")
        if report.summary != scenario.expected.summary:
            differences.append("摘要不一致")
        if differences:
            mismatches.append(
                ScenarioMismatch(case_id=scenario.case_id, differences=tuple(differences))
            )
    suite_hash = sha256("".join(item.input_sha256 for item in scenarios).encode()).hexdigest()
    return ScenarioRunSummary(
        seed=seed,
        case_count=len(scenarios),
        suite_sha256=suite_hash,
        mismatches=tuple(mismatches),
    )


def run_generated_scenarios(seed: int, case_count: int) -> ScenarioRunSummary:
    return verify_generated_scenarios(generate_scenarios(seed, case_count))

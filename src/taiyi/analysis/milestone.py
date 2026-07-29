from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from hashlib import sha256
from itertools import product
from typing import Literal, cast

from pydantic import Field

from taiyi import __version__
from taiyi.analysis.engine import analyze_jsonl
from taiyi.analysis.models import ProtocolModel, ScopeKind, content_digest
from taiyi.analysis.results import (
    POLICY_VERSION,
    REPORT_VERSION,
    RULE_MISSING_SOURCE,
    RULE_SCOPE_MISMATCH,
    AnalysisSummary,
)
from taiyi.analysis.scenarios import ExpectedAnalysis, MemoryPresence

MILESTONE_GENERATOR_VERSION = "1.0"
MILESTONE_SCENARIO_COUNT = 10_000
DEFAULT_MILESTONE_SEED = 20260729


class MilestoneSourceMode(StrEnum):
    COMPLETE = "complete"
    MISSING = "missing"
    MULTIPLE = "multiple"


class MilestoneDimensions(ProtocolModel):
    memory_count: int = Field(ge=1, le=3)
    presence: MemoryPresence
    scope_kind: ScopeKind
    source_mode: MilestoneSourceMode
    source_scope_mismatch: bool
    content_changed: bool
    writer_changed: bool
    include_content: bool
    model_variant: bool
    prompt_variant: bool
    tool_variant: bool


class GeneratedMilestoneScenario(ProtocolModel):
    generator_version: Literal["1.0"] = "1.0"
    seed: int
    case_index: int = Field(ge=1)
    case_id: str
    dimensions: MilestoneDimensions
    input_sha256: str
    jsonl: str
    expected: ExpectedAnalysis


class MilestoneMismatch(ProtocolModel):
    case_id: str
    differences: tuple[str, ...] = Field(min_length=1)


class MilestoneRunSummary(ProtocolModel):
    generator_version: Literal["1.0"] = "1.0"
    tool_version: str = __version__
    protocol_version: Literal["1.0"] = "1.0"
    report_version: Literal["1.0"] = REPORT_VERSION
    policy_version: Literal["1.0"] = POLICY_VERSION
    seed: int
    case_count: int = Field(ge=1)
    distinct_dimension_count: int = Field(ge=1)
    suite_sha256: str
    mismatches: tuple[MilestoneMismatch, ...]


@dataclass(frozen=True)
class _MilestoneSpec:
    memory_count: int
    presence: MemoryPresence
    scope_kind: ScopeKind
    source_mode: MilestoneSourceMode
    source_scope_mismatch: bool
    content_changed: bool
    writer_changed: bool
    include_content: bool
    model_variant: bool
    prompt_variant: bool
    tool_variant: bool

    @property
    def key(self) -> str:
        return ":".join(
            (
                str(self.memory_count),
                self.presence.value,
                self.scope_kind.value,
                self.source_mode.value,
                str(int(self.source_scope_mismatch)),
                str(int(self.content_changed)),
                str(int(self.writer_changed)),
                str(int(self.include_content)),
                str(int(self.model_variant)),
                str(int(self.prompt_variant)),
                str(int(self.tool_variant)),
            )
        )


@lru_cache(maxsize=1)
def _case_specs() -> tuple[_MilestoneSpec, ...]:
    specs: list[_MilestoneSpec] = []
    for values in product(
        (1, 2, 3),
        tuple(MemoryPresence),
        tuple(ScopeKind),
        tuple(MilestoneSourceMode),
        (False, True),
        (False, True),
        (False, True),
        (False, True),
        (False, True),
        (False, True),
        (False, True),
    ):
        typed_values = cast(
            tuple[
                int,
                MemoryPresence,
                ScopeKind,
                MilestoneSourceMode,
                bool,
                bool,
                bool,
                bool,
                bool,
                bool,
                bool,
            ],
            values,
        )
        spec = _MilestoneSpec(*typed_values)
        if spec.source_scope_mismatch and spec.source_mode is not MilestoneSourceMode.MULTIPLE:
            continue
        if spec.presence is MemoryPresence.BEFORE_ONLY and (
            spec.source_mode is not MilestoneSourceMode.COMPLETE
            or spec.source_scope_mismatch
            or spec.content_changed
            or spec.writer_changed
        ):
            continue
        if spec.presence is MemoryPresence.AFTER_ONLY and (
            spec.content_changed or spec.writer_changed
        ):
            continue
        specs.append(spec)
    return tuple(specs)


@lru_cache(maxsize=16)
def _ordered_specs(seed: int, epoch: int) -> tuple[_MilestoneSpec, ...]:
    return tuple(
        sorted(
            _case_specs(),
            key=lambda spec: sha256(f"{seed}:{epoch}:{spec.key}".encode()).hexdigest(),
        )
    )


def generate_milestone_scenarios(
    seed: int, case_count: int
) -> tuple[GeneratedMilestoneScenario, ...]:
    if case_count < 1:
        raise ValueError("case_count 必须大于零")
    specs_per_epoch = len(_case_specs())
    scenarios: list[GeneratedMilestoneScenario] = []
    for offset in range(case_count):
        epoch, position = divmod(offset, specs_per_epoch)
        spec = _ordered_specs(seed, epoch)[position]
        scenarios.append(_build_scenario(seed, offset + 1, spec))
    return tuple(scenarios)


def _build_scenario(seed: int, case_index: int, spec: _MilestoneSpec) -> GeneratedMilestoneScenario:
    before_id = f"snapshot_before_{case_index}"
    after_id = f"snapshot_after_{case_index}"
    scope = {"kind": spec.scope_kind.value, "id": "scope_primary"}
    records: list[dict[str, object]] = [
        {
            "protocol_version": "1.0",
            "record_type": "manifest",
            "sequence_number": 0,
            "project_id": "milestone_project",
            "run_id": f"milestone_run_{seed}_{case_index}",
            "baseline_run_id": "milestone_baseline",
            "captured_at": "2026-07-29T06:00:00Z",
            "producer": {"name": "taiyi-milestone-generator", "version": "1.0"},
            "model_version": "model-b" if spec.model_variant else "model-a",
            "prompt_version": "prompt-v2" if spec.prompt_variant else "prompt-v1",
            "tool_versions": {"search": "2.0" if spec.tool_variant else "1.0"},
            "writer_version": "writer-v1",
        },
        {
            "protocol_version": "1.0",
            "record_type": "snapshot",
            "sequence_number": 0,
            "snapshot_id": before_id,
            "snapshot_role": "before",
            "captured_at": "2026-07-29T06:00:00Z",
        },
    ]
    if spec.presence is not MemoryPresence.AFTER_ONLY:
        records.extend(
            _memory_record(index, before_id, "before", spec, ["event_1"])
            for index in range(1, spec.memory_count + 1)
        )
    records.extend(
        (
            _event_record("event_1", scope),
            _event_record(
                "event_2",
                {"kind": spec.scope_kind.value, "id": "scope_other"}
                if spec.source_scope_mismatch
                else scope,
            ),
            {
                "protocol_version": "1.0",
                "record_type": "snapshot",
                "sequence_number": 0,
                "snapshot_id": after_id,
                "snapshot_role": "after",
                "captured_at": "2026-07-29T06:02:00Z",
            },
        )
    )
    if spec.presence is not MemoryPresence.BEFORE_ONLY:
        source_ids = {
            MilestoneSourceMode.COMPLETE: ["event_1"],
            MilestoneSourceMode.MISSING: [],
            MilestoneSourceMode.MULTIPLE: ["event_1", "event_2"],
        }[spec.source_mode]
        records.extend(
            _memory_record(index, after_id, "after", spec, source_ids)
            for index in range(1, spec.memory_count + 1)
        )
    for sequence_number, record in enumerate(records, 1):
        record["sequence_number"] = sequence_number
    jsonl = (
        "\n".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records
        )
        + "\n"
    )
    return GeneratedMilestoneScenario(
        seed=seed,
        case_index=case_index,
        case_id=f"MIL-{seed}-{case_index:06d}",
        dimensions=MilestoneDimensions(**spec.__dict__),
        input_sha256=sha256(jsonl.encode()).hexdigest(),
        jsonl=jsonl,
        expected=_expected(spec),
    )


def _event_record(event_id: str, scope: dict[str, str]) -> dict[str, object]:
    return {
        "protocol_version": "1.0",
        "record_type": "event",
        "sequence_number": 0,
        "event_id": event_id,
        "event_type": "user_input",
        "scope": scope,
        "occurred_at": "2026-07-29T06:01:00Z",
        "content_hash": content_digest(f"里程碑来源 {event_id}"),
        "parent_event_ids": [],
    }


def _memory_record(
    index: int,
    snapshot_id: str,
    role: str,
    spec: _MilestoneSpec,
    source_event_ids: list[str],
) -> dict[str, object]:
    before_content = f"基线记忆 {index}"
    content = f"变更记忆 {index}" if role == "after" and spec.content_changed else before_content
    record: dict[str, object] = {
        "protocol_version": "1.0",
        "record_type": "memory",
        "sequence_number": 0,
        "snapshot_id": snapshot_id,
        "memory_id": f"memory_{index}",
        "scope": {"kind": spec.scope_kind.value, "id": "scope_primary"},
        "memory_type": "semantic",
        "content_hash": content_digest(content),
        "source_event_ids": source_event_ids,
        "created_at": "2026-07-29T05:00:00Z",
        "updated_at": "2026-07-29T05:00:00Z",
        "writer_version": "writer-v2" if role == "after" and spec.writer_changed else "writer-v1",
        "memory_version": "1",
    }
    if spec.include_content:
        record["content"] = content
    return record


def _expected(spec: _MilestoneSpec) -> ExpectedAnalysis:
    count = spec.memory_count
    added = count if spec.presence is MemoryPresence.AFTER_ONLY else 0
    deleted = count if spec.presence is MemoryPresence.BEFORE_ONLY else 0
    content_modified = count if spec.presence is MemoryPresence.BOTH and spec.content_changed else 0
    structure_changed = (
        count
        if spec.presence is MemoryPresence.BOTH
        and (spec.source_mode is not MilestoneSourceMode.COMPLETE or spec.writer_changed)
        else 0
    )
    rule_id: str | None = None
    if spec.presence is not MemoryPresence.BEFORE_ONLY:
        if spec.source_mode is MilestoneSourceMode.MISSING:
            rule_id = RULE_MISSING_SOURCE
        elif spec.source_scope_mismatch:
            rule_id = RULE_SCOPE_MISMATCH
    rule_ids = (rule_id,) * count if rule_id is not None else ()
    return ExpectedAnalysis(
        rule_ids=rule_ids,
        exit_code=2 if rule_ids else 0,
        summary=AnalysisSummary(
            added=added,
            deleted=deleted,
            content_modified=content_modified,
            structure_changed=structure_changed,
            ignored_findings=0,
            warnings=0,
            errors=len(rule_ids),
        ),
    )


def verify_milestone_scenarios(
    scenarios: tuple[GeneratedMilestoneScenario, ...],
) -> MilestoneRunSummary:
    if not scenarios:
        raise ValueError("待验证里程碑场景不能为空")
    seed = scenarios[0].seed
    if any(scenario.seed != seed for scenario in scenarios):
        raise ValueError("同一里程碑场景套件必须使用相同种子")
    mismatches: list[MilestoneMismatch] = []
    for scenario in scenarios:
        report = analyze_jsonl(scenario.jsonl)
        differences: list[str] = []
        if tuple(finding.rule_id for finding in report.findings) != scenario.expected.rule_ids:
            differences.append("规则编号不一致")
        if report.exit_code != scenario.expected.exit_code:
            differences.append("退出码不一致")
        if report.summary != scenario.expected.summary:
            differences.append("摘要不一致")
        if differences:
            mismatches.append(
                MilestoneMismatch(case_id=scenario.case_id, differences=tuple(differences))
            )
    return MilestoneRunSummary(
        seed=seed,
        case_count=len(scenarios),
        distinct_dimension_count=len({scenario.dimensions for scenario in scenarios}),
        suite_sha256=sha256(
            "".join(scenario.input_sha256 for scenario in scenarios).encode()
        ).hexdigest(),
        mismatches=tuple(mismatches),
    )


def run_milestone_scenarios(seed: int, case_count: int) -> MilestoneRunSummary:
    return verify_milestone_scenarios(generate_milestone_scenarios(seed, case_count))

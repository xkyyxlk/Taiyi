from __future__ import annotations

import json
from collections import Counter
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal

from pydantic import Field

from taiyi import __version__
from taiyi.analysis.models import ProtocolModel, content_digest
from taiyi.analysis.protocol import ProtocolError, parse_jsonl

MALFORMED_GENERATOR_VERSION = "1.0"
DEFAULT_MALFORMED_SEED = 20260729
COMMIT_MALFORMED_COUNT = 1000


class MalformedKind(StrEnum):
    TRUNCATED_JSON = "truncated_json"
    BLANK_LINE = "blank_line"
    DUPLICATE_FIELD = "duplicate_field"
    UNKNOWN_FIELD = "unknown_field"
    RECORD_ORDER = "record_order"
    SEQUENCE_GAP = "sequence_gap"
    DUPLICATE_IDENTIFIER = "duplicate_identifier"
    MISSING_FIELD = "missing_field"
    WRONG_TYPE = "wrong_type"
    INVALID_ENUM = "invalid_enum"
    NAIVE_DATETIME = "naive_datetime"
    INVALID_HASH = "invalid_hash"
    DANGLING_REFERENCE = "dangling_reference"
    UNSUPPORTED_VERSION = "unsupported_version"


class ExpectedProtocolError(ProtocolModel):
    category: MalformedKind
    error_fragment: str


class GeneratedMalformedScenario(ProtocolModel):
    generator_version: Literal["1.0"] = "1.0"
    seed: int
    case_index: int = Field(ge=1)
    case_id: str
    kind: MalformedKind
    input_sha256: str
    jsonl: str
    expected: ExpectedProtocolError


class MalformedScenarioMismatch(ProtocolModel):
    case_id: str
    kind: MalformedKind
    expected_error: str
    actual_error: str | None


class MalformedRunSummary(ProtocolModel):
    generator_version: Literal["1.0"] = "1.0"
    tool_version: str = __version__
    protocol_version: Literal["1.0"] = "1.0"
    seed: int
    case_count: int = Field(ge=1)
    category_counts: dict[str, int]
    suite_sha256: str
    mismatches: tuple[MalformedScenarioMismatch, ...]


_EXPECTED_ERRORS: dict[MalformedKind, str] = {
    MalformedKind.TRUNCATED_JSON: "不是有效 JSON",
    MalformedKind.BLANK_LINE: "JSONL 不允许空行",
    MalformedKind.DUPLICATE_FIELD: "重复字段",
    MalformedKind.UNKNOWN_FIELD: "不符合协议",
    MalformedKind.RECORD_ORDER: "事件记录必须位于",
    MalformedKind.SEQUENCE_GAP: "sequence_number 必须为",
    MalformedKind.DUPLICATE_IDENTIFIER: "event_id 在同一协议文件中必须唯一",
    MalformedKind.MISSING_FIELD: "不符合协议",
    MalformedKind.WRONG_TYPE: "不符合协议",
    MalformedKind.INVALID_ENUM: "不符合协议",
    MalformedKind.NAIVE_DATETIME: "不符合协议",
    MalformedKind.INVALID_HASH: "不符合协议",
    MalformedKind.DANGLING_REFERENCE: "不存在的来源事件",
    MalformedKind.UNSUPPORTED_VERSION: "不符合协议",
}


def _ordered_kinds(seed: int, epoch: int) -> tuple[MalformedKind, ...]:
    return tuple(
        sorted(
            MalformedKind,
            key=lambda kind: sha256(f"{seed}:{epoch}:{kind.value}".encode()).hexdigest(),
        )
    )


def generate_malformed_scenarios(
    seed: int, case_count: int
) -> tuple[GeneratedMalformedScenario, ...]:
    if case_count < 1:
        raise ValueError("case_count 必须大于零")
    scenarios: list[GeneratedMalformedScenario] = []
    kinds_per_epoch = len(MalformedKind)
    for offset in range(case_count):
        epoch, position = divmod(offset, kinds_per_epoch)
        kind = _ordered_kinds(seed, epoch)[position]
        scenarios.append(_build_malformed_scenario(seed, offset + 1, kind))
    return tuple(scenarios)


def _base_records(seed: int, case_index: int) -> list[dict[str, Any]]:
    event_id = f"event_{seed}_{case_index}"
    return [
        {
            "protocol_version": "1.0",
            "record_type": "manifest",
            "sequence_number": 1,
            "project_id": "malformed_project",
            "run_id": f"malformed_run_{seed}_{case_index}",
            "baseline_run_id": "malformed_baseline",
            "captured_at": "2026-07-29T06:00:00Z",
            "producer": {"name": "taiyi-malformed-generator", "version": "1.0"},
            "model_version": "model-a",
            "prompt_version": "prompt-v1",
            "tool_versions": {},
            "writer_version": "writer-v1",
        },
        {
            "protocol_version": "1.0",
            "record_type": "snapshot",
            "sequence_number": 2,
            "snapshot_id": f"snapshot_before_{case_index}",
            "snapshot_role": "before",
            "captured_at": "2026-07-29T06:00:00Z",
        },
        {
            "protocol_version": "1.0",
            "record_type": "event",
            "sequence_number": 3,
            "event_id": event_id,
            "event_type": "user_input",
            "scope": {"kind": "user", "id": "user_alice"},
            "occurred_at": "2026-07-29T06:01:00Z",
            "content_hash": content_digest(f"畸形案例来源事件 {case_index}"),
            "parent_event_ids": [],
        },
        {
            "protocol_version": "1.0",
            "record_type": "snapshot",
            "sequence_number": 4,
            "snapshot_id": f"snapshot_after_{case_index}",
            "snapshot_role": "after",
            "captured_at": "2026-07-29T06:02:00Z",
        },
        {
            "protocol_version": "1.0",
            "record_type": "memory",
            "sequence_number": 5,
            "snapshot_id": f"snapshot_after_{case_index}",
            "memory_id": f"memory_{case_index}",
            "scope": {"kind": "user", "id": "user_alice"},
            "memory_type": "semantic",
            "content_hash": content_digest(f"畸形案例记忆 {case_index}"),
            "source_event_ids": [event_id],
            "created_at": "2026-07-29T05:00:00Z",
            "updated_at": "2026-07-29T06:02:00Z",
            "writer_version": "writer-v1",
            "memory_version": "1",
        },
    ]


def _serialize(records: list[dict[str, Any]]) -> list[str]:
    return [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records]


def _resequence(records: list[dict[str, Any]]) -> None:
    for sequence_number, record in enumerate(records, 1):
        record["sequence_number"] = sequence_number


def _malformed_jsonl(seed: int, case_index: int, kind: MalformedKind) -> str:
    records = _base_records(seed, case_index)
    if kind is MalformedKind.UNKNOWN_FIELD:
        records[0]["unknown_field"] = True
    elif kind is MalformedKind.RECORD_ORDER:
        records[1], records[2] = records[2], records[1]
        _resequence(records)
    elif kind is MalformedKind.SEQUENCE_GAP:
        records[2]["sequence_number"] = 4
    elif kind is MalformedKind.DUPLICATE_IDENTIFIER:
        records.insert(3, dict(records[2]))
        _resequence(records)
    elif kind is MalformedKind.MISSING_FIELD:
        del records[0]["project_id"]
    elif kind is MalformedKind.WRONG_TYPE:
        records[2]["sequence_number"] = "3"
    elif kind is MalformedKind.INVALID_ENUM:
        records[2]["event_type"] = "invalid_event_type"
    elif kind is MalformedKind.NAIVE_DATETIME:
        records[2]["occurred_at"] = "2026-07-29T06:01:00"
    elif kind is MalformedKind.INVALID_HASH:
        records[2]["content_hash"] = "not-a-sha256"
    elif kind is MalformedKind.DANGLING_REFERENCE:
        records[4]["source_event_ids"] = ["event_missing"]
    elif kind is MalformedKind.UNSUPPORTED_VERSION:
        records[0]["protocol_version"] = "2.0"

    lines = _serialize(records)
    if kind is MalformedKind.TRUNCATED_JSON:
        lines[-1] = lines[-1][:-1]
    elif kind is MalformedKind.BLANK_LINE:
        lines.insert(1, "")
    elif kind is MalformedKind.DUPLICATE_FIELD:
        lines[0] = lines[0].replace(
            '"protocol_version":"1.0"',
            '"protocol_version":"1.0","protocol_version":"1.0"',
            1,
        )
    return "\n".join(lines) + "\n"


def _build_malformed_scenario(
    seed: int, case_index: int, kind: MalformedKind
) -> GeneratedMalformedScenario:
    jsonl = _malformed_jsonl(seed, case_index, kind)
    return GeneratedMalformedScenario(
        seed=seed,
        case_index=case_index,
        case_id=f"MAL-{seed}-{case_index:06d}",
        kind=kind,
        input_sha256=sha256(jsonl.encode()).hexdigest(),
        jsonl=jsonl,
        expected=ExpectedProtocolError(
            category=kind,
            error_fragment=_EXPECTED_ERRORS[kind],
        ),
    )


def verify_malformed_scenarios(
    scenarios: tuple[GeneratedMalformedScenario, ...],
) -> MalformedRunSummary:
    if not scenarios:
        raise ValueError("待验证畸形场景不能为空")
    seed = scenarios[0].seed
    if any(scenario.seed != seed for scenario in scenarios):
        raise ValueError("同一畸形场景套件必须使用相同种子")

    mismatches: list[MalformedScenarioMismatch] = []
    for scenario in scenarios:
        actual_error: str | None = None
        try:
            parse_jsonl(scenario.jsonl)
        except ProtocolError as exc:
            actual_error = str(exc)
        if actual_error is None or scenario.expected.error_fragment not in actual_error:
            mismatches.append(
                MalformedScenarioMismatch(
                    case_id=scenario.case_id,
                    kind=scenario.kind,
                    expected_error=scenario.expected.error_fragment,
                    actual_error=actual_error,
                )
            )

    counts = Counter(scenario.kind.value for scenario in scenarios)
    return MalformedRunSummary(
        seed=seed,
        case_count=len(scenarios),
        category_counts={kind.value: counts[kind.value] for kind in MalformedKind},
        suite_sha256=sha256(
            "".join(scenario.input_sha256 for scenario in scenarios).encode()
        ).hexdigest(),
        mismatches=tuple(mismatches),
    )


def run_malformed_scenarios(seed: int, case_count: int) -> MalformedRunSummary:
    return verify_malformed_scenarios(generate_malformed_scenarios(seed, case_count))

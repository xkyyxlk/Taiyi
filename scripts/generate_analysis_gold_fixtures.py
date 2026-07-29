from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
OUTPUT_DIR = ROOT / "tests" / "fixtures" / "analysis" / "v1"
MEMORY_TYPES = ("episodic", "semantic", "procedural", "preference", "relational", "custom")
SCOPE_KINDS = ("agent", "user", "tenant", "session", "custom")
EVENT_TYPES = (
    "user_input",
    "model_output",
    "tool_call",
    "tool_result",
    "document_read",
    "memory_write",
    "system",
)
ZERO_SUMMARY = {
    "added": 0,
    "deleted": 0,
    "content_modified": 0,
    "structure_changed": 0,
    "ignored_findings": 0,
    "warnings": 0,
    "errors": 0,
}


@dataclass(frozen=True)
class GoldCase:
    scenario_id: str
    title: str
    records: list[dict[str, Any]]
    expected_changes: list[dict[str, Any]]
    expected_rule_ids: list[str]
    expected_summary: dict[str, int]
    expected_exit_code: int


def _manifest(scenario_id: str) -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "record_type": "manifest",
        "sequence_number": 0,
        "project_id": "gold_project",
        "run_id": f"gold_run_{scenario_id.lower()}",
        "baseline_run_id": "gold_baseline",
        "captured_at": "2026-07-29T06:00:00Z",
        "producer": {"name": "taiyi-gold-fixture", "version": "1.0"},
        "model_version": "model-a",
        "prompt_version": "prompt-v1",
        "tool_versions": {},
        "writer_version": "writer-v1",
    }


def _snapshot(role: str, captured_at: str = "2026-07-29T06:03:00Z") -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "record_type": "snapshot",
        "sequence_number": 0,
        "snapshot_id": f"snapshot_{role}",
        "snapshot_role": role,
        "captured_at": "2026-07-29T06:00:00Z" if role == "before" else captured_at,
    }


def _event(
    event_id: str = "event_1",
    *,
    event_type: str = "user_input",
    scope_kind: str = "user",
    scope_id: str = "scope_primary",
    occurred_at: str = "2026-07-29T06:01:00Z",
    parents: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "record_type": "event",
        "sequence_number": 0,
        "event_id": event_id,
        "event_type": event_type,
        "scope": {"kind": scope_kind, "id": scope_id},
        "occurred_at": occurred_at,
        "content_hash": (event_id[-1] if event_id[-1].isalnum() else "a") * 64,
        "parent_event_ids": parents or [],
    }


def _memory(
    snapshot_role: str,
    *,
    memory_id: str = "memory_1",
    memory_type: str = "semantic",
    scope_kind: str = "user",
    scope_id: str = "scope_primary",
    content_hash: str = "a" * 64,
    source_event_ids: list[str] | None = None,
    created_at: str = "2026-07-29T05:00:00Z",
    updated_at: str = "2026-07-29T05:00:00Z",
    writer_version: str = "writer-v1",
    memory_version: str = "1",
) -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "record_type": "memory",
        "sequence_number": 0,
        "snapshot_id": f"snapshot_{snapshot_role}",
        "memory_id": memory_id,
        "scope": {"kind": scope_kind, "id": scope_id},
        "memory_type": memory_type,
        "content_hash": content_hash,
        "source_event_ids": ["event_1"] if source_event_ids is None else source_event_ids,
        "created_at": created_at,
        "updated_at": updated_at,
        "writer_version": writer_version,
        "memory_version": memory_version,
    }


def _records(
    scenario_id: str,
    before_memories: list[dict[str, Any]],
    events: list[dict[str, Any]],
    after_memories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = [
        _manifest(scenario_id),
        _snapshot("before"),
        *before_memories,
        *events,
        _snapshot("after"),
        *after_memories,
    ]
    for sequence_number, record in enumerate(records, 1):
        record["sequence_number"] = sequence_number
    return records


def _summary(**overrides: int) -> dict[str, int]:
    return {**ZERO_SUMMARY, **overrides}


def _change(memory_id: str, kind: str, changed_fields: list[str] | None = None) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "kinds": [kind],
        "changed_fields": changed_fields or [],
    }


def _unchanged_case(number: int, memory_type: str, scope_kind: str = "user") -> GoldCase:
    scenario_id = f"SCN-{number:03d}"
    before = _memory("before", memory_type=memory_type, scope_kind=scope_kind)
    after = _memory("after", memory_type=memory_type, scope_kind=scope_kind)
    return GoldCase(
        scenario_id,
        f"{memory_type} 记忆在 {scope_kind} 作用域保持不变",
        _records(scenario_id, [before], [_event(scope_kind=scope_kind)], [after]),
        [],
        [],
        _summary(),
        0,
    )


def _event_type_case(number: int, event_type: str) -> GoldCase:
    scenario_id = f"SCN-{number:03d}"
    return GoldCase(
        scenario_id,
        f"{event_type} 事件作为新增记忆来源",
        _records(
            scenario_id,
            [],
            [_event(event_type=event_type)],
            [_memory("after")],
        ),
        [_change("memory_1", "added")],
        [],
        _summary(added=1),
        0,
    )


def _structure_case(number: int, field_name: str) -> GoldCase:
    scenario_id = f"SCN-{number:03d}"
    before = _memory("before")
    after = _memory("after")
    events = [_event()]
    if field_name == "memory_type":
        after["memory_type"] = "preference"
    elif field_name == "source_event_ids":
        after["source_event_ids"] = ["event_1", "event_2"]
        events.append(_event("event_2"))
    elif field_name == "created_at":
        before["created_at"] = "2026-07-29T04:00:00Z"
        after["created_at"] = "2026-07-29T04:30:00Z"
    elif field_name == "updated_at":
        after["updated_at"] = "2026-07-29T05:30:00Z"
    elif field_name == "writer_version":
        after["writer_version"] = "writer-v2"
    elif field_name == "memory_version":
        after["memory_version"] = "2"
    return GoldCase(
        scenario_id,
        f"记忆仅改变 {field_name}",
        _records(scenario_id, [before], events, [after]),
        [_change("memory_1", "structure_changed", [field_name])],
        [],
        _summary(structure_changed=1),
        0,
    )


def _content_case(number: int, memory_type: str) -> GoldCase:
    scenario_id = f"SCN-{number:03d}"
    return GoldCase(
        scenario_id,
        f"{memory_type} 记忆仅修改内容哈希",
        _records(
            scenario_id,
            [_memory("before", memory_type=memory_type)],
            [_event()],
            [_memory("after", memory_type=memory_type, content_hash="b" * 64)],
        ),
        [_change("memory_1", "content_modified", ["content_hash"])],
        [],
        _summary(content_modified=1),
        0,
    )


def _presence_case(number: int, scope_kind: str, kind: str) -> GoldCase:
    scenario_id = f"SCN-{number:03d}"
    before = [_memory("before", scope_kind=scope_kind)] if kind == "deleted" else []
    after = [_memory("after", scope_kind=scope_kind)] if kind == "added" else []
    return GoldCase(
        scenario_id,
        f"{scope_kind} 作用域记忆{('新增' if kind == 'added' else '删除')}",
        _records(scenario_id, before, [_event(scope_kind=scope_kind)], after),
        [_change("memory_1", kind)],
        [],
        _summary(**{kind: 1}),
        0,
    )


def _special_cases() -> list[GoldCase]:
    cases: list[GoldCase] = []
    scenario_id = "SCN-055"
    cases.append(
        GoldCase(
            scenario_id,
            "新增记忆具有两个同作用域来源",
            _records(
                scenario_id,
                [],
                [_event(), _event("event_2")],
                [_memory("after", source_event_ids=["event_1", "event_2"])],
            ),
            [_change("memory_1", "added")],
            [],
            _summary(added=1),
            0,
        )
    )
    scenario_id = "SCN-056"
    cases.append(
        GoldCase(
            scenario_id,
            "新增记忆的两个来源中一个作用域不一致",
            _records(
                scenario_id,
                [],
                [_event(), _event("event_2", scope_id="scope_other")],
                [_memory("after", source_event_ids=["event_1", "event_2"])],
            ),
            [_change("memory_1", "added")],
            ["TY-SCOPE-001"],
            _summary(added=1, errors=1),
            2,
        )
    )
    scenario_id = "SCN-057"
    cases.append(
        GoldCase(
            scenario_id,
            "两条新增记忆均缺少来源",
            _records(
                scenario_id,
                [],
                [],
                [
                    _memory("after", memory_id="memory_a", source_event_ids=[]),
                    _memory("after", memory_id="memory_b", source_event_ids=[]),
                ],
            ),
            [_change("memory_a", "added"), _change("memory_b", "added")],
            ["TY-PROV-001", "TY-PROV-001"],
            _summary(added=2, errors=2),
            2,
        )
    )
    scenario_id = "SCN-058"
    cases.append(
        GoldCase(
            scenario_id,
            "两条新增记忆按标识稳定排序",
            _records(
                scenario_id,
                [],
                [_event()],
                [
                    _memory("after", memory_id="memory_b"),
                    _memory("after", memory_id="memory_a"),
                ],
            ),
            [_change("memory_a", "added"), _change("memory_b", "added")],
            [],
            _summary(added=2),
            0,
        )
    )
    scenario_id = "SCN-059"
    cases.append(
        GoldCase(
            scenario_id,
            "三事件父子链时间顺序有效",
            _records(
                scenario_id,
                [],
                [
                    _event("event_1", occurred_at="2026-07-29T06:00:00Z"),
                    _event(
                        "event_2",
                        occurred_at="2026-07-29T06:01:00Z",
                        parents=["event_1"],
                    ),
                    _event(
                        "event_3",
                        occurred_at="2026-07-29T06:02:00Z",
                        parents=["event_2"],
                    ),
                ],
                [],
            ),
            [],
            [],
            _summary(),
            0,
        )
    )
    scenario_id = "SCN-060"
    cases.append(
        GoldCase(
            scenario_id,
            "三个事件形成单一规范化循环",
            _records(
                scenario_id,
                [],
                [
                    _event("event_1", parents=["event_3"]),
                    _event("event_2", parents=["event_1"]),
                    _event("event_3", parents=["event_2"]),
                ],
                [],
            ),
            [],
            ["TY-AUDIT-002"],
            _summary(errors=1),
            2,
        )
    )
    return cases


def build_cases() -> list[GoldCase]:
    cases: list[GoldCase] = []
    for number, memory_type in enumerate(MEMORY_TYPES, 15):
        cases.append(_unchanged_case(number, memory_type))
    for number, scope_kind in enumerate(SCOPE_KINDS, 21):
        cases.append(_unchanged_case(number, "semantic", scope_kind))
    for number, event_type in enumerate(EVENT_TYPES, 26):
        cases.append(_event_type_case(number, event_type))
    structure_fields = (
        "memory_type",
        "source_event_ids",
        "created_at",
        "updated_at",
        "writer_version",
        "memory_version",
    )
    for number, field_name in enumerate(structure_fields, 33):
        cases.append(_structure_case(number, field_name))
    for number, memory_type in enumerate(MEMORY_TYPES, 39):
        cases.append(_content_case(number, memory_type))
    for number, scope_kind in enumerate(SCOPE_KINDS, 45):
        cases.append(_presence_case(number, scope_kind, "added"))
    for number, scope_kind in enumerate(SCOPE_KINDS, 50):
        cases.append(_presence_case(number, scope_kind, "deleted"))
    cases.extend(_special_cases())
    return cases


def main() -> None:
    cases = build_cases()
    if len(cases) != 46:
        raise ValueError("扩展金样本必须恰好包含四十六个场景")
    manifest_cases: list[dict[str, Any]] = []
    for case in cases:
        file_name = f"gold-{case.scenario_id.lower()}.jsonl"
        content = (
            "\n".join(
                json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                for record in case.records
            )
            + "\n"
        )
        (OUTPUT_DIR / file_name).write_text(content, encoding="utf-8")
        manifest_cases.append(
            {
                "id": case.scenario_id,
                "title": case.title,
                "input": file_name,
                "protocol_valid": True,
                "expected_changes": case.expected_changes,
                "expected_rule_ids": case.expected_rule_ids,
                "expected_exit_code": case.expected_exit_code,
                "expected_summary": case.expected_summary,
            }
        )
    manifest = {
        "scenario_version": "1.0",
        "protocol_version": "1.0",
        "reviewed_at": "2026-07-29",
        "review_status": "人工复核",
        "scenario_count": len(manifest_cases),
        "scenarios": manifest_cases,
    }
    (OUTPUT_DIR / "golden-v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

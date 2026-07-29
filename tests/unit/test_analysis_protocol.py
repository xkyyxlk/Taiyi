from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from taiyi.analysis import ProtocolError, content_digest, parse_jsonl

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "analysis" / "v1"


def _records() -> list[dict[str, object]]:
    return [
        {
            "protocol_version": "1.0",
            "record_type": "manifest",
            "sequence_number": 1,
            "project_id": "project_demo",
            "run_id": "run_candidate",
            "baseline_run_id": "run_baseline",
            "captured_at": "2026-07-29T06:00:00Z",
            "producer": {"name": "taiyi-fixture", "version": "1.0.0"},
            "model_version": "model-a",
            "prompt_version": "prompt-v2",
            "tool_versions": {"search": "1.2.0"},
            "writer_version": "writer-v3",
        },
        {
            "protocol_version": "1.0",
            "record_type": "snapshot",
            "sequence_number": 2,
            "snapshot_id": "snapshot_before",
            "snapshot_role": "before",
            "captured_at": "2026-07-29T06:00:00Z",
        },
        {
            "protocol_version": "1.0",
            "record_type": "memory",
            "sequence_number": 3,
            "snapshot_id": "snapshot_before",
            "memory_id": "memory_preference",
            "scope": {"kind": "user", "id": "user_alice"},
            "memory_type": "preference",
            "content_hash": content_digest("用户偏好红茶"),
            "content": "用户偏好红茶",
            "source_event_ids": ["event_preference"],
            "created_at": "2026-07-29T05:00:00Z",
            "updated_at": "2026-07-29T05:00:00Z",
            "writer_version": "writer-v2",
            "memory_version": "1",
        },
        {
            "protocol_version": "1.0",
            "record_type": "event",
            "sequence_number": 4,
            "event_id": "event_preference",
            "event_type": "user_input",
            "scope": {"kind": "user", "id": "user_alice"},
            "occurred_at": "2026-07-29T06:01:00Z",
            "content_hash": content_digest("以后请推荐绿茶"),
            "content": "以后请推荐绿茶",
            "parent_event_ids": [],
        },
        {
            "protocol_version": "1.0",
            "record_type": "snapshot",
            "sequence_number": 5,
            "snapshot_id": "snapshot_after",
            "snapshot_role": "after",
            "captured_at": "2026-07-29T06:02:00Z",
        },
        {
            "protocol_version": "1.0",
            "record_type": "memory",
            "sequence_number": 6,
            "snapshot_id": "snapshot_after",
            "memory_id": "memory_preference",
            "scope": {"kind": "user", "id": "user_alice"},
            "memory_type": "preference",
            "content_hash": content_digest("用户偏好绿茶"),
            "content": "用户偏好绿茶",
            "source_event_ids": ["event_preference"],
            "created_at": "2026-07-29T05:00:00Z",
            "updated_at": "2026-07-29T06:02:00Z",
            "writer_version": "writer-v3",
            "memory_version": "2",
        },
    ]


def _jsonl(records: list[dict[str, object]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def test_valid_protocol_input_is_grouped_by_role() -> None:
    parsed = parse_jsonl(_jsonl(_records()))

    assert parsed.manifest.run_id == "run_candidate"
    assert parsed.before_snapshot.snapshot_id == "snapshot_before"
    assert parsed.after_snapshot.snapshot_id == "snapshot_after"
    assert [memory.memory_id for memory in parsed.before_memories] == ["memory_preference"]
    assert [event.event_id for event in parsed.events] == ["event_preference"]


def test_empty_source_list_is_valid_protocol_data() -> None:
    records = _records()
    records[-1]["source_event_ids"] = []

    parsed = parse_jsonl(_jsonl(records))

    assert parsed.after_memories[0].source_event_ids == ()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda records: records[0].update(protocol_version="2.0"), "不符合协议"),
        (lambda records: records[0].update(unknown_field=True), "不符合协议"),
        (lambda records: records[2].update(content_hash="0" * 64), "不符合协议"),
        (lambda records: records[3].update(sequence_number=9), "sequence_number"),
        (lambda records: records[3].update(sequence_number="4"), "不符合协议"),
        (lambda records: records[3].update(occurred_at=1), "RFC 3339"),
        (
            lambda records: records[-1].update(source_event_ids=["event_missing"]),
            "不存在的来源事件",
        ),
    ],
)
def test_invalid_protocol_input_is_rejected(mutate: object, message: str) -> None:
    records = _records()
    assert callable(mutate)
    mutate(records)

    with pytest.raises(ProtocolError, match=message):
        parse_jsonl(_jsonl(records))


def test_duplicate_json_key_is_rejected() -> None:
    lines = _jsonl(_records()).splitlines()
    lines[0] = lines[0].replace(
        '"protocol_version": "1.0"',
        '"protocol_version": "1.0", "protocol_version": "1.0"',
        1,
    )

    with pytest.raises(ProtocolError, match="重复字段"):
        parse_jsonl("\n".join(lines))


def test_blank_line_is_rejected() -> None:
    content = _jsonl(_records()).replace("\n", "\n\n", 1)

    with pytest.raises(ProtocolError, match="不允许空行"):
        parse_jsonl(content)


def test_event_after_after_snapshot_is_rejected() -> None:
    records = _records()
    event = deepcopy(records.pop(3))
    records.append(event)
    for sequence_number, record in enumerate(records, 1):
        record["sequence_number"] = sequence_number

    with pytest.raises(ProtocolError, match="事件记录必须位于"):
        parse_jsonl(_jsonl(records))


def test_duplicate_memory_id_in_snapshot_is_rejected() -> None:
    records = _records()
    duplicate = deepcopy(records[2])
    records.insert(3, duplicate)
    for sequence_number, record in enumerate(records, 1):
        record["sequence_number"] = sequence_number

    with pytest.raises(ProtocolError, match="before 快照中的 memory_id 必须唯一"):
        parse_jsonl(_jsonl(records))


def test_standard_scenario_protocol_expectations() -> None:
    manifest = json.loads((FIXTURE_DIR / "scenarios.json").read_text(encoding="utf-8"))

    assert manifest["scenario_version"] == "1.0"
    assert manifest["protocol_version"] == "1.0"
    assert len(manifest["scenarios"]) == 14
    for scenario in manifest["scenarios"]:
        content = (FIXTURE_DIR / scenario["input"]).read_text(encoding="utf-8")
        if scenario["protocol_valid"]:
            parse_jsonl(content)
            continue
        with pytest.raises(ProtocolError, match=scenario["expected_error"]):
            parse_jsonl(content)

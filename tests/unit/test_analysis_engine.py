from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from taiyi.analysis import (
    RULE_EVENT_CYCLE,
    RULE_MISSING_SOURCE,
    RULE_PARENT_AFTER_CHILD,
    RULE_SCOPE_MISMATCH,
    FindingLevel,
    MemoryChangeKind,
    Policy,
    analyze_jsonl,
)

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "analysis" / "v1"


def _fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _records(name: str = "valid-modification.jsonl") -> list[dict[str, object]]:
    return [json.loads(line) for line in _fixture(name).splitlines()]


def _jsonl(records: list[dict[str, object]]) -> str:
    for sequence_number, record in enumerate(records, 1):
        record["sequence_number"] = sequence_number
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def test_modified_memory_produces_deterministic_report() -> None:
    content = _fixture("valid-modification.jsonl")

    first = analyze_jsonl(content)
    second = analyze_jsonl(content)

    assert first == second
    assert first.exit_code == 0
    assert first.summary.content_modified == 1
    assert first.summary.structure_changed == 1
    assert first.findings == ()
    assert first.changes[0].kinds == (
        MemoryChangeKind.CONTENT_MODIFIED,
        MemoryChangeKind.STRUCTURE_CHANGED,
    )


def test_added_and_deleted_memories_are_distinguished() -> None:
    added_records = _records()
    added_records.pop(2)
    added = analyze_jsonl(_jsonl(added_records))

    deleted_records = _records()
    deleted_records.pop()
    deleted = analyze_jsonl(_jsonl(deleted_records))

    assert added.summary.added == 1
    assert added.changes[0].kinds == (MemoryChangeKind.ADDED,)
    assert deleted.summary.deleted == 1
    assert deleted.changes[0].kinds == (MemoryChangeKind.DELETED,)


def test_missing_source_is_an_error_by_default_and_can_be_downgraded() -> None:
    content = _fixture("missing-source.jsonl")

    default_report = analyze_jsonl(content)
    warning_report = analyze_jsonl(
        content,
        Policy(overrides={RULE_MISSING_SOURCE: FindingLevel.WARNING}),
    )

    assert [finding.rule_id for finding in default_report.findings] == [RULE_MISSING_SOURCE]
    assert default_report.summary.errors == 1
    assert default_report.exit_code == 2
    assert warning_report.summary.warnings == 1
    assert warning_report.summary.errors == 0
    assert warning_report.exit_code == 0


def test_cross_scope_source_produces_scope_finding() -> None:
    report = analyze_jsonl(_fixture("cross-scope.jsonl"))

    assert [finding.rule_id for finding in report.findings] == [RULE_SCOPE_MISMATCH]
    assert report.findings[0].effective_level is FindingLevel.ERROR
    assert report.exit_code == 2


def test_parent_after_child_produces_audit_finding() -> None:
    records = _records()
    child = records[3]
    child["parent_event_ids"] = ["event_parent"]
    parent = deepcopy(child)
    parent.update(
        event_id="event_parent",
        parent_event_ids=[],
        occurred_at="2026-07-29T07:00:00Z",
    )
    records.insert(4, parent)

    report = analyze_jsonl(_jsonl(records))

    assert RULE_PARENT_AFTER_CHILD in {finding.rule_id for finding in report.findings}


def test_event_cycle_produces_one_canonical_finding() -> None:
    records = _records()
    first_event = records[3]
    first_event["parent_event_ids"] = ["event_2"]
    second_event = deepcopy(first_event)
    second_event.update(event_id="event_2", parent_event_ids=["event_1"])
    records.insert(4, second_event)

    report = analyze_jsonl(_jsonl(records))
    cycle_findings = [finding for finding in report.findings if finding.rule_id == RULE_EVENT_CYCLE]

    assert len(cycle_findings) == 1
    assert {evidence.record_id for evidence in cycle_findings[0].evidence} == {
        "event_2",
        "event_1",
    }


def test_policy_rejects_unknown_rule_id() -> None:
    with pytest.raises(ValueError, match="未知规则"):
        analyze_jsonl(
            _fixture("valid-modification.jsonl"),
            Policy(overrides={"TY-UNKNOWN-001": FindingLevel.ERROR}),
        )


def test_standard_scenarios_match_analysis_expectations() -> None:
    manifests = [
        json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        for name in ("scenarios.json", "golden-v1.json")
    ]

    for manifest in manifests:
        for scenario in manifest["scenarios"]:
            if not scenario["protocol_valid"]:
                continue
            report = analyze_jsonl(_fixture(scenario["input"]))
            assert [finding.rule_id for finding in report.findings] == scenario["expected_rule_ids"]
            assert report.exit_code == scenario["expected_exit_code"]
            for field_name, expected in scenario.get("expected_summary", {}).items():
                assert getattr(report.summary, field_name) == expected
            if "expected_changes" in scenario:
                actual_changes = [
                    {
                        "memory_id": change.memory_id,
                        "kinds": [kind.value for kind in change.kinds],
                        "changed_fields": list(change.changed_fields),
                    }
                    for change in report.changes
                ]
                assert actual_changes == scenario["expected_changes"]

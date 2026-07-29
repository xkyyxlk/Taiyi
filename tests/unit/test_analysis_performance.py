from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from taiyi.analysis import (
    PerformanceBudget,
    check_performance_budget,
    generate_scale_jsonl,
    parse_jsonl,
    run_performance_sample,
)

ROOT = Path(__file__).parents[2]


def test_scale_input_is_reproducible_and_has_declared_counts() -> None:
    first, first_metadata = generate_scale_jsonl(20, 5)
    second, second_metadata = generate_scale_jsonl(20, 5)
    parsed = parse_jsonl(first)

    assert first == second
    assert first_metadata == second_metadata
    assert first_metadata.record_count == 33
    assert len(parsed.events) == 20
    assert len(parsed.before_memories) == 5
    assert len(parsed.after_memories) == 5


def test_performance_sample_reports_expected_changes() -> None:
    sample = run_performance_sample(20, 5)

    assert sample.input.event_count == 20
    assert sample.input.memory_change_count == 5
    assert sample.actual_content_modified == 5
    assert sample.actual_change_count == 5
    assert sample.actual_finding_count == 0
    assert sample.exit_code == 0
    assert sample.peak_traced_memory_bytes > 0
    assert sample.report_bytes > 0


def test_performance_budget_reports_pass_and_regression() -> None:
    sample = run_performance_sample(20, 5)
    budget = PerformanceBudget(
        event_count=20,
        memory_change_count=5,
        expected_input_sha256=sample.input.input_sha256,
        reference_python_version=sample.environment.python_version,
        reference_operating_system=sample.environment.operating_system,
        reference_machine=sample.environment.machine,
        reference_processor=sample.environment.processor,
        baseline_total_seconds=100,
        baseline_peak_traced_memory_bytes=100_000_000,
        allowed_regression_percent=20,
        max_total_seconds=120,
        max_peak_traced_memory_bytes=120_000_000,
        max_report_bytes=sample.report_bytes,
        expected_change_count=5,
        max_finding_count=0,
        expected_exit_code=0,
    )

    assert check_performance_budget(sample, budget).passed
    regressed = budget.model_copy(update={"max_report_bytes": sample.report_bytes - 1})
    check = check_performance_budget(sample, regressed)
    assert not check.passed
    assert check.violations == ("报告大小超过预算",)


def test_performance_budget_rejects_ceiling_above_declared_regression() -> None:
    with pytest.raises(ValidationError, match="总耗时上限"):
        PerformanceBudget(
            event_count=1,
            memory_change_count=1,
            expected_input_sha256="a" * 64,
            reference_python_version="3.13.12",
            reference_operating_system="Windows",
            reference_machine="AMD64",
            reference_processor="processor",
            baseline_total_seconds=10,
            baseline_peak_traced_memory_bytes=100,
            allowed_regression_percent=20,
            max_total_seconds=13,
            max_peak_traced_memory_bytes=120,
            max_report_bytes=1,
            expected_change_count=1,
            max_finding_count=0,
            expected_exit_code=0,
        )


def test_versioned_reference_budget_is_valid() -> None:
    budget_path = ROOT / "docs" / "质量" / "Agent记忆分析性能预算_v1.json"
    budget = PerformanceBudget.model_validate_json(budget_path.read_text(encoding="utf-8"))

    assert budget.event_count == 100_000
    assert budget.memory_change_count == 10_000
    assert budget.allowed_regression_percent == 20


@pytest.mark.parametrize(
    ("event_count", "memory_change_count", "message"),
    [
        (0, 1, "event_count"),
        (1, 0, "memory_change_count"),
        (1, 2, "不得大于"),
    ],
)
def test_scale_input_rejects_invalid_counts(
    event_count: int, memory_change_count: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        generate_scale_jsonl(event_count, memory_change_count)

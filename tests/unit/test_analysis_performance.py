from __future__ import annotations

import pytest

from taiyi.analysis import generate_scale_jsonl, parse_jsonl, run_performance_sample


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

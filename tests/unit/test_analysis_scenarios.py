from __future__ import annotations

import pytest

from taiyi import __version__
from taiyi.analysis import (
    COMMIT_MALFORMED_COUNT,
    COMMIT_SCENARIO_COUNT,
    DEFAULT_MALFORMED_SEED,
    DEFAULT_SCENARIO_SEED,
    MalformedKind,
    MemoryPresence,
    ScopeMode,
    SourceMode,
    generate_malformed_scenarios,
    generate_scenarios,
    parse_jsonl,
    run_generated_scenarios,
    run_malformed_scenarios,
)


def test_fixed_seed_generation_is_reproducible() -> None:
    first = generate_scenarios(DEFAULT_SCENARIO_SEED, 40)
    second = generate_scenarios(DEFAULT_SCENARIO_SEED, 40)
    different = generate_scenarios(DEFAULT_SCENARIO_SEED + 1, 40)

    assert first == second
    assert [item.input_sha256 for item in first] != [item.input_sha256 for item in different]
    assert all(parse_jsonl(item.jsonl) for item in first)


def test_generated_suite_covers_declared_dimensions() -> None:
    scenarios = generate_scenarios(DEFAULT_SCENARIO_SEED, 40)

    assert {item.dimensions.presence for item in scenarios} == set(MemoryPresence)
    assert {item.dimensions.source_mode for item in scenarios} == set(SourceMode)
    assert {item.dimensions.scope_mode for item in scenarios} == set(ScopeMode)
    assert {item.dimensions.content_changed for item in scenarios} == {False, True}
    assert {item.dimensions.writer_changed for item in scenarios} == {False, True}


def test_commit_level_thousand_cases_match_independent_expectations() -> None:
    summary = run_generated_scenarios(DEFAULT_SCENARIO_SEED, COMMIT_SCENARIO_COUNT)

    assert summary.case_count == 1000
    assert summary.tool_version == __version__
    assert summary.mismatches == ()
    assert len(summary.suite_sha256) == 64


def test_generator_rejects_empty_suite() -> None:
    with pytest.raises(ValueError, match="大于零"):
        generate_scenarios(DEFAULT_SCENARIO_SEED, 0)


def test_fixed_seed_malformed_generation_is_reproducible() -> None:
    first = generate_malformed_scenarios(DEFAULT_MALFORMED_SEED, 40)
    second = generate_malformed_scenarios(DEFAULT_MALFORMED_SEED, 40)
    different = generate_malformed_scenarios(DEFAULT_MALFORMED_SEED + 1, 40)

    assert first == second
    assert [item.input_sha256 for item in first] != [item.input_sha256 for item in different]
    assert {item.kind for item in first} == set(MalformedKind)


def test_commit_level_thousand_malformed_cases_match_stable_expectations() -> None:
    summary = run_malformed_scenarios(DEFAULT_MALFORMED_SEED, COMMIT_MALFORMED_COUNT)

    assert summary.case_count == 1000
    assert summary.mismatches == ()
    assert set(summary.category_counts) == {kind.value for kind in MalformedKind}
    assert min(summary.category_counts.values()) >= 71
    assert len(summary.suite_sha256) == 64


def test_malformed_generator_rejects_empty_suite() -> None:
    with pytest.raises(ValueError, match="大于零"):
        generate_malformed_scenarios(DEFAULT_MALFORMED_SEED, 0)

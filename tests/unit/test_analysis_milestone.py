from __future__ import annotations

import pytest

from taiyi.analysis import (
    DEFAULT_MILESTONE_SEED,
    MilestoneSourceMode,
    generate_milestone_scenarios,
    run_milestone_scenarios,
)
from taiyi.analysis.models import ScopeKind
from taiyi.analysis.scenarios import MemoryPresence


def test_milestone_generation_is_reproducible_and_covers_dimensions() -> None:
    first = generate_milestone_scenarios(DEFAULT_MILESTONE_SEED, 200)
    second = generate_milestone_scenarios(DEFAULT_MILESTONE_SEED, 200)

    assert first == second
    assert {item.dimensions.memory_count for item in first} == {1, 2, 3}
    assert {item.dimensions.presence for item in first} == set(MemoryPresence)
    assert {item.dimensions.scope_kind for item in first} == set(ScopeKind)
    assert {item.dimensions.source_mode for item in first} == set(MilestoneSourceMode)
    assert {item.dimensions.include_content for item in first} == {False, True}
    assert {item.dimensions.model_variant for item in first} == {False, True}
    assert {item.dimensions.prompt_variant for item in first} == {False, True}
    assert {item.dimensions.tool_variant for item in first} == {False, True}


def test_milestone_cases_match_independent_expectations() -> None:
    summary = run_milestone_scenarios(DEFAULT_MILESTONE_SEED, 200)

    assert summary.case_count == 200
    assert summary.distinct_dimension_count == 200
    assert summary.mismatches == ()
    assert len(summary.suite_sha256) == 64


def test_milestone_generator_rejects_empty_suite() -> None:
    with pytest.raises(ValueError, match="大于零"):
        generate_milestone_scenarios(DEFAULT_MILESTONE_SEED, 0)

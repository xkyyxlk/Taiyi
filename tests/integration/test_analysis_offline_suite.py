from __future__ import annotations

import socket

import pytest

from taiyi.analysis import (
    COMMIT_MALFORMED_COUNT,
    COMMIT_SCENARIO_COUNT,
    DEFAULT_MALFORMED_SEED,
    DEFAULT_MILESTONE_SEED,
    DEFAULT_SCENARIO_SEED,
    MILESTONE_SCENARIO_COUNT,
    run_generated_scenarios,
    run_malformed_scenarios,
    run_milestone_scenarios,
    run_performance_sample,
)


def test_complete_analysis_suites_do_not_open_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("完整分析套件不应打开网络连接")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    commit_summary = run_generated_scenarios(
        DEFAULT_SCENARIO_SEED,
        COMMIT_SCENARIO_COUNT,
    )
    malformed_summary = run_malformed_scenarios(
        DEFAULT_MALFORMED_SEED,
        COMMIT_MALFORMED_COUNT,
    )
    milestone_summary = run_milestone_scenarios(
        DEFAULT_MILESTONE_SEED,
        MILESTONE_SCENARIO_COUNT,
    )
    performance_sample = run_performance_sample(20, 5)

    assert commit_summary.mismatches == ()
    assert malformed_summary.mismatches == ()
    assert milestone_summary.mismatches == ()
    assert performance_sample.actual_change_count == 5

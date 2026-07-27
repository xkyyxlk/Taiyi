from __future__ import annotations

from taiyi.evaluation import SCENARIOS, run_scenario


def test_all_standard_scenarios(tmp_path) -> None:  # type: ignore[no-untyped-def]
    results = [run_scenario(name, tmp_path) for name in SCENARIOS]
    assert all(result["passed"] for result in results)
    assert all((tmp_path / name).exists() for name in SCENARIOS)

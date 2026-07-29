from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from taiyi.cli.app import app

runner = CliRunner()
ANALYSIS_FIXTURES = Path(__file__).parents[1] / "fixtures" / "analysis" / "v1"
ADAPTER_FIXTURES = (
    Path(__file__).parents[1] / "fixtures" / "adapters" / "langgraph-langsmith" / "v1"
)


def test_cli_minimal_workflow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    options = ["--data-dir", str(tmp_path)]
    assert runner.invoke(app, [*options, "--help"]).exit_code == 0
    assert runner.invoke(app, [*options, "prototype", "--help"]).exit_code == 0
    initialized = runner.invoke(app, [*options, "init", "Taiyi"])
    assert initialized.exit_code == 0, initialized.output
    duplicate = runner.invoke(app, [*options, "init", "Another"])
    assert duplicate.exit_code == 1
    assert runner.invoke(app, [*options, "fork", "alpha"]).exit_code == 0
    chat = runner.invoke(app, [*options, "chat", "alpha", "hello"])
    assert chat.exit_code == 0, chat.output
    shown = runner.invoke(app, [*options, "worldline", "show", "alpha"])
    assert shown.exit_code == 0
    assert len(json.loads(shown.output)) == 3


def test_analysis_validate_does_not_initialize_legacy_database(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data_dir = tmp_path / "legacy-data"
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "analyze",
            "validate",
            str(ANALYSIS_FIXTURES / "valid-modification.jsonl"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "valid": True,
        "protocol_version": "1.0",
        "project_id": "project_demo",
        "run_id": "run_candidate",
        "record_count": 6,
    }
    assert not (data_dir / "taiyi.sqlite3").exists()


def test_analysis_check_returns_report_exit_codes() -> None:
    passed = runner.invoke(
        app,
        ["analyze", "check", str(ANALYSIS_FIXTURES / "valid-modification.jsonl")],
    )
    blocked = runner.invoke(
        app,
        ["analyze", "check", str(ANALYSIS_FIXTURES / "missing-source.jsonl")],
    )

    assert passed.exit_code == 0, passed.output
    passed_report = json.loads(passed.output)
    assert passed_report["summary"]["errors"] == 0
    assert passed_report["reproduction_command"][:3] == ["taiyi", "analyze", "check"]
    assert blocked.exit_code == 2, blocked.output
    assert json.loads(blocked.output)["findings"][0]["rule_id"] == "TY-PROV-001"


def test_analysis_protocol_error_uses_exit_code_one() -> None:
    result = runner.invoke(
        app,
        ["analyze", "check", str(ANALYSIS_FIXTURES / "invalid-sequence.jsonl")],
    )

    assert result.exit_code == 1
    assert "sequence_number" in result.output


def test_analysis_policy_file_can_downgrade_rule(tmp_path) -> None:  # type: ignore[no-untyped-def]
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "overrides": {"TY-PROV-001": "warning"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "analyze",
            "check",
            str(ANALYSIS_FIXTURES / "missing-source.jsonl"),
            "--policy",
            str(policy_path),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["summary"]["warnings"] == 1
    assert report["summary"]["errors"] == 0
    assert report["reproduction_command"][-2] == "--policy"


def test_analysis_unknown_policy_rule_uses_exit_code_one(tmp_path) -> None:  # type: ignore[no-untyped-def]
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": "1.0",
                "overrides": {"TY-UNKNOWN-001": "error"},
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "analyze",
            "check",
            str(ANALYSIS_FIXTURES / "valid-modification.jsonl"),
            "--policy",
            str(policy_path),
        ],
    )

    assert result.exit_code == 1
    assert "未知规则" in result.output


def test_analysis_check_outputs_markdown() -> None:
    result = runner.invoke(
        app,
        [
            "analyze",
            "check",
            str(ANALYSIS_FIXTURES / "valid-modification.jsonl"),
            "--format",
            "markdown",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "# 太一 Agent 记忆分析报告" in result.output
    assert "## 记忆变化" in result.output


def test_analysis_check_writes_html_without_legacy_database(tmp_path) -> None:  # type: ignore[no-untyped-def]
    data_dir = tmp_path / "legacy-data"
    output_path = tmp_path / "reports" / "report.html"
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "analyze",
            "check",
            str(ANALYSIS_FIXTURES / "missing-source.jsonl"),
            "--format",
            "html",
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 2, result.output
    assert output_path.is_file()
    assert '<html lang="zh-CN">' in output_path.read_text(encoding="utf-8")
    assert "TY-PROV-001" in output_path.read_text(encoding="utf-8")
    assert not (data_dir / "taiyi.sqlite3").exists()


def test_analysis_simulate_is_reproducible_without_legacy_database(tmp_path: Path) -> None:
    data_dir = tmp_path / "legacy-data"
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    command = [
        "--data-dir",
        str(data_dir),
        "analyze",
        "simulate",
        "--seed",
        "20260729",
        "--count",
        "25",
    ]

    first = runner.invoke(app, [*command, "--output-dir", str(first_output)])
    second = runner.invoke(app, [*command, "--output-dir", str(second_output)])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    first_result = json.loads(first.output)
    second_result = json.loads(second.output)
    assert first_result["case_count"] == 25
    assert first_result["mismatches"] == []
    assert first_result["suite_sha256"] == second_result["suite_sha256"]
    first_manifest = (first_output / "manifest.json").read_text(encoding="utf-8")
    second_manifest = (second_output / "manifest.json").read_text(encoding="utf-8")
    assert first_manifest == second_manifest
    assert len(json.loads(first_manifest)["cases"]) == 25
    assert len(list(first_output.glob("case-*.jsonl"))) == 25
    assert not (data_dir / "taiyi.sqlite3").exists()


def test_analysis_simulate_malformed_is_reproducible_without_legacy_database(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "legacy-data"
    first_output = tmp_path / "first-malformed"
    second_output = tmp_path / "second-malformed"
    command = [
        "--data-dir",
        str(data_dir),
        "analyze",
        "simulate-malformed",
        "--seed",
        "20260729",
        "--count",
        "35",
    ]

    first = runner.invoke(app, [*command, "--output-dir", str(first_output)])
    second = runner.invoke(app, [*command, "--output-dir", str(second_output)])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    first_result = json.loads(first.output)
    second_result = json.loads(second.output)
    assert first_result["case_count"] == 35
    assert first_result["mismatches"] == []
    assert len(first_result["category_counts"]) == 14
    assert first_result["suite_sha256"] == second_result["suite_sha256"]
    first_manifest = (first_output / "manifest.json").read_text(encoding="utf-8")
    second_manifest = (second_output / "manifest.json").read_text(encoding="utf-8")
    assert first_manifest == second_manifest
    assert len(json.loads(first_manifest)["cases"]) == 35
    assert len(list(first_output.glob("case-*.jsonl"))) == 35
    assert not (data_dir / "taiyi.sqlite3").exists()


def test_analysis_adapt_langgraph_uses_offline_fixture(tmp_path: Path) -> None:
    data_dir = tmp_path / "legacy-data"
    output_path = tmp_path / "adapted" / "run.jsonl"

    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "analyze",
            "adapt-langgraph",
            str(ADAPTER_FIXTURES / "run-bundle.json"),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["adapter_version"] == "1.0"
    assert summary["langgraph_version"] == "1.2.10"
    assert summary["langsmith_version"] == "0.10.11"
    assert summary["record_count"] == 9
    assert output_path.read_text(encoding="utf-8") == (
        ADAPTER_FIXTURES / "expected.jsonl"
    ).read_text(encoding="utf-8")
    assert not (data_dir / "taiyi.sqlite3").exists()

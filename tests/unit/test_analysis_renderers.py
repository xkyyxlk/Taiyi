from __future__ import annotations

import json
from pathlib import Path

from taiyi.analysis import (
    ReportFormat,
    analyze_jsonl,
    content_digest,
    render_html,
    render_json,
    render_markdown,
    render_report,
)

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "analysis" / "v1"


def _fixture_records(name: str = "valid-modification.jsonl") -> list[dict[str, object]]:
    content = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in content.splitlines()]


def _jsonl(records: list[dict[str, object]]) -> str:
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def test_all_report_formats_are_deterministic() -> None:
    content = (FIXTURE_DIR / "valid-modification.jsonl").read_text(encoding="utf-8")
    report = analyze_jsonl(content)

    for report_format in ReportFormat:
        assert render_report(report, report_format) == render_report(report, report_format)

    assert json.loads(render_json(report))["run_id"] == "run_candidate"
    assert "# 太一 Agent 记忆分析报告" in render_markdown(report)
    assert '<html lang="zh-CN">' in render_html(report)


def test_human_readable_reports_do_not_copy_raw_content() -> None:
    records = _fixture_records()
    secrets: list[str] = []
    for index, record in enumerate(records):
        if record["record_type"] not in {"event", "memory"}:
            continue
        secret = f"绝密正文-{index}-不得进入报告"
        secrets.append(secret)
        record["content"] = secret
        record["content_hash"] = content_digest(secret)
    report = analyze_jsonl(_jsonl(records))

    markdown = render_markdown(report)
    html = render_html(report)

    assert all(secret not in markdown for secret in secrets)
    assert all(secret not in html for secret in secrets)


def test_html_escapes_dynamic_identifiers() -> None:
    records = _fixture_records()
    records[0]["project_id"] = "<script>alert(1)</script>"
    report = analyze_jsonl(_jsonl(records))

    html = render_html(report)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

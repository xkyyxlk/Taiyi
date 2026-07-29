from __future__ import annotations

import json
from enum import StrEnum
from html import escape

from taiyi.analysis.results import (
    AnalysisReport,
    EvidenceReference,
    FindingLevel,
    MemoryChangeKind,
)


class ReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"


_CHANGE_LABELS = {
    MemoryChangeKind.ADDED: "新增",
    MemoryChangeKind.DELETED: "删除",
    MemoryChangeKind.CONTENT_MODIFIED: "内容修改",
    MemoryChangeKind.STRUCTURE_CHANGED: "结构变化",
}

_LEVEL_LABELS = {
    FindingLevel.IGNORE: "忽略",
    FindingLevel.WARNING: "告警",
    FindingLevel.ERROR: "错误",
}


def render_report(report: AnalysisReport, report_format: ReportFormat) -> str:
    if report_format is ReportFormat.JSON:
        return render_json(report)
    if report_format is ReportFormat.MARKDOWN:
        return render_markdown(report)
    return render_html(report)


def render_json(report: AnalysisReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    )


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _evidence_text(evidence: EvidenceReference) -> str:
    role = f"，快照={evidence.snapshot_role.value}" if evidence.snapshot_role is not None else ""
    return (
        f"{evidence.record_type.value}:{evidence.record_id}"
        f"（序号={evidence.sequence_number}{role}）"
    )


def render_markdown(report: AnalysisReport) -> str:
    lines = [
        "# 太一 Agent 记忆分析报告",
        "",
        f"- 报告版本：`{_markdown_cell(report.report_version)}`",
        f"- 工具版本：`{_markdown_cell(report.tool_version)}`",
        f"- 协议版本：`{_markdown_cell(report.protocol_version)}`",
        f"- 策略版本：`{_markdown_cell(report.policy_version)}`",
        f"- 项目：`{_markdown_cell(report.project_id)}`",
        f"- 运行：`{_markdown_cell(report.run_id)}`",
        f"- 输入 SHA-256：`{report.input_sha256}`",
        f"- 退出码：`{report.exit_code}`",
        "",
        "## 摘要",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| 新增记忆 | {report.summary.added} |",
        f"| 删除记忆 | {report.summary.deleted} |",
        f"| 内容修改 | {report.summary.content_modified} |",
        f"| 结构变化 | {report.summary.structure_changed} |",
        f"| 忽略发现 | {report.summary.ignored_findings} |",
        f"| 告警发现 | {report.summary.warnings} |",
        f"| 错误发现 | {report.summary.errors} |",
        "",
        "## 记忆变化",
        "",
    ]
    if not report.changes:
        lines.append("无记忆变化。")
    for change in report.changes:
        kinds = "、".join(_CHANGE_LABELS[kind] for kind in change.kinds)
        lines.extend(
            [
                f"### `{_markdown_cell(change.memory_id)}`",
                "",
                f"- 变化：{kinds}",
                "- 变化字段："
                + ("、".join(f"`{field}`" for field in change.changed_fields) or "无"),
            ]
        )
        if change.before is not None:
            lines.append(f"- 前置证据：{_evidence_text(change.before)}")
        if change.after is not None:
            lines.append(f"- 后置证据：{_evidence_text(change.after)}")
        lines.append("")

    lines.extend(["## 治理发现", ""])
    if not report.findings:
        lines.append("无治理发现。")
    for finding in report.findings:
        evidence = "；".join(_evidence_text(item) for item in finding.evidence)
        lines.extend(
            [
                f"### `{finding.rule_id}`：{finding.message}",
                "",
                f"- 默认级别：{_LEVEL_LABELS[finding.default_level]}",
                f"- 生效级别：{_LEVEL_LABELS[finding.effective_level]}",
                f"- 最小证据：{evidence}",
                "",
            ]
        )

    lines.extend(
        [
            "## 复现命令",
            "",
            "```json",
            json.dumps(report.reproduction_command, ensure_ascii=False),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _html_evidence(evidence: EvidenceReference) -> str:
    role = (
        f"，快照={escape(evidence.snapshot_role.value)}"
        if evidence.snapshot_role is not None
        else ""
    )
    return (
        f"<code>{escape(evidence.record_type.value)}:{escape(evidence.record_id)}</code>"
        f"（序号={evidence.sequence_number}{role}）"
    )


def render_html(report: AnalysisReport) -> str:
    change_sections: list[str] = []
    for change in report.changes:
        kinds = "、".join(_CHANGE_LABELS[kind] for kind in change.kinds)
        fields = "、".join(f"<code>{escape(field)}</code>" for field in change.changed_fields)
        evidence_items = []
        if change.before is not None:
            evidence_items.append(f"<li>前置证据：{_html_evidence(change.before)}</li>")
        if change.after is not None:
            evidence_items.append(f"<li>后置证据：{_html_evidence(change.after)}</li>")
        change_sections.append(
            f"<section><h3><code>{escape(change.memory_id)}</code></h3>"
            f"<ul><li>变化：{escape(kinds)}</li>"
            f"<li>变化字段：{fields or '无'}</li>{''.join(evidence_items)}</ul></section>"
        )
    if not change_sections:
        change_sections.append("<p>无记忆变化。</p>")

    finding_sections: list[str] = []
    for finding in report.findings:
        evidence = "；".join(_html_evidence(item) for item in finding.evidence)
        finding_sections.append(
            f"<section><h3><code>{escape(finding.rule_id)}</code>："
            f"{escape(finding.message)}</h3><ul>"
            f"<li>默认级别：{escape(_LEVEL_LABELS[finding.default_level])}</li>"
            f"<li>生效级别：{escape(_LEVEL_LABELS[finding.effective_level])}</li>"
            f"<li>最小证据：{evidence}</li></ul></section>"
        )
    if not finding_sections:
        finding_sections.append("<p>无治理发现。</p>")

    reproduction = escape(json.dumps(report.reproduction_command, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>太一 Agent 记忆分析报告</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;
padding:0 1rem;line-height:1.6}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #bbb;padding:.4rem;text-align:left}}
code{{overflow-wrap:anywhere}}section{{margin:1rem 0}}
</style>
</head>
<body>
<h1>太一 Agent 记忆分析报告</h1>
<ul>
<li>报告版本：<code>{escape(report.report_version)}</code></li>
<li>工具版本：<code>{escape(report.tool_version)}</code></li>
<li>协议版本：<code>{escape(report.protocol_version)}</code></li>
<li>策略版本：<code>{escape(report.policy_version)}</code></li>
<li>项目：<code>{escape(report.project_id)}</code></li>
<li>运行：<code>{escape(report.run_id)}</code></li>
<li>输入 SHA-256：<code>{report.input_sha256}</code></li>
<li>退出码：<code>{report.exit_code}</code></li>
</ul>
<h2>摘要</h2>
<table><thead><tr><th>指标</th><th>数量</th></tr></thead><tbody>
<tr><td>新增记忆</td><td>{report.summary.added}</td></tr>
<tr><td>删除记忆</td><td>{report.summary.deleted}</td></tr>
<tr><td>内容修改</td><td>{report.summary.content_modified}</td></tr>
<tr><td>结构变化</td><td>{report.summary.structure_changed}</td></tr>
<tr><td>忽略发现</td><td>{report.summary.ignored_findings}</td></tr>
<tr><td>告警发现</td><td>{report.summary.warnings}</td></tr>
<tr><td>错误发现</td><td>{report.summary.errors}</td></tr>
</tbody></table>
<h2>记忆变化</h2>
{"".join(change_sections)}
<h2>治理发现</h2>
{"".join(finding_sections)}
<h2>复现命令</h2>
<pre><code>{reproduction}</code></pre>
</body>
</html>
"""

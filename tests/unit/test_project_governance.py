from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_iteration_handoff_files_exist() -> None:
    required = (
        ROOT / "AGENTS.md",
        ROOT / "docs" / "项目迭代工作流.md",
        ROOT / "docs" / "迭代状态.md",
        ROOT / "docs" / "会话交接模板.md",
        ROOT / "docs" / "迭代记录" / "记录索引.md",
        ROOT / "docs" / "迭代记录" / "迭代记录模板.md",
    )
    assert all(path.is_file() for path in required)


def test_iteration_status_contains_recovery_fields() -> None:
    status = (ROOT / "docs" / "迭代状态.md").read_text(encoding="utf-8")
    required_sections = (
        "## 当前基线",
        "## 最近完成",
        "## 当前现场",
        "## 下一步操作",
        "## 最近验证",
        "## 阻塞与待决定事项",
    )
    assert all(section in status for section in required_sections)


def test_archived_iteration_records_are_complete_and_indexed() -> None:
    archive_dir = ROOT / "docs" / "迭代记录"
    index = (archive_dir / "记录索引.md").read_text(encoding="utf-8")
    records = sorted(
        path
        for path in archive_dir.glob("*.md")
        if path.name not in {"记录索引.md", "迭代记录模板.md"}
    )
    required_sections = (
        "## 基本信息",
        "## 目标",
        "## 本次完成内容",
        "## 重要决策",
        "## 验证结果",
        "## 相关提交",
        "## 影响范围",
        "## 遗留事项",
    )

    assert records
    for record in records:
        content = record.read_text(encoding="utf-8")
        assert record.name in index
        assert all(section in content for section in required_sections)

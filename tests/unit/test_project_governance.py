from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).parents[2]
LOCAL_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)#]+)")


def test_iteration_handoff_files_exist() -> None:
    required = (
        ROOT / "AGENTS.md",
        ROOT / "docs" / "文档索引.md",
        ROOT / "docs" / "开发" / "项目迭代工作流.md",
        ROOT / "docs" / "开发" / "迭代状态.md",
        ROOT / "docs" / "开发" / "会话交接模板.md",
        ROOT / "docs" / "开发" / "迭代记录" / "记录索引.md",
        ROOT / "docs" / "开发" / "迭代记录" / "迭代记录模板.md",
    )
    assert all(path.is_file() for path in required)


def test_iteration_status_contains_recovery_fields() -> None:
    status = (ROOT / "docs" / "开发" / "迭代状态.md").read_text(encoding="utf-8")
    required_sections = (
        "## 当前基线",
        "## 最近完成",
        "## 当前现场",
        "## 下一步操作",
        "## 最近验证",
        "## 阻塞与待决定事项",
    )
    assert all(section in status for section in required_sections)


def test_document_modules_and_index_are_complete() -> None:
    docs_dir = ROOT / "docs"
    index = (docs_dir / "文档索引.md").read_text(encoding="utf-8")
    modules = ("产品", "架构", "开发", "质量", "发布")

    assert all((docs_dir / module).is_dir() for module in modules)
    assert all(f"{module}/" in index for module in modules)
    assert {path.name for path in docs_dir.glob("*.md")} == {"文档索引.md"}


def test_local_markdown_links_are_valid() -> None:
    markdown_files = [
        *ROOT.glob("*.md"),
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".github").rglob("*.md"),
    ]
    invalid_links: list[str] = []

    for path in markdown_files:
        content = path.read_text(encoding="utf-8")
        for match in LOCAL_MARKDOWN_LINK.finditer(content):
            target = unquote(match.group(1).strip())
            if not (path.parent / target).exists():
                invalid_links.append(f"{path.relative_to(ROOT)} -> {target}")

    assert not invalid_links, "以下 Markdown 本地链接无效：" + ", ".join(invalid_links)


def test_archived_iteration_records_are_complete_and_indexed() -> None:
    archive_dir = ROOT / "docs" / "开发" / "迭代记录"
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

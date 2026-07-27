from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_iteration_handoff_files_exist() -> None:
    required = (
        ROOT / "AGENTS.md",
        ROOT / "docs" / "项目迭代工作流.md",
        ROOT / "docs" / "迭代状态.md",
        ROOT / "docs" / "会话交接模板.md",
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

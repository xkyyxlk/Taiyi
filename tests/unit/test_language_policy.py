from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).parents[2]
HAS_CHINESE = re.compile(r"[\u3400-\u9fff]")
HAS_ENGLISH_WORD = re.compile(r"[A-Za-z]{3,}")
MACHINE_COMMENT = re.compile(r"^#\s*(type:\s*ignore|noqa|pragma:)")


def _markdown_files() -> list[Path]:
    return [
        *ROOT.glob("*.md"),
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".github").rglob("*.md"),
    ]


def test_markdown_prose_uses_chinese() -> None:
    violations: list[str] = []
    for path in _markdown_files():
        in_code_block = False
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or not HAS_ENGLISH_WORD.search(line):
                continue
            if not HAS_CHINESE.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}")
    assert not violations, "以下 Markdown 非代码文本未使用中文：" + ", ".join(violations)


def test_python_comments_and_docstrings_use_chinese() -> None:
    violations: list[str] = []
    for base in (ROOT / "src", ROOT / "tests"):
        for path in base.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type != tokenize.COMMENT or MACHINE_COMMENT.match(token.string):
                    continue
                if HAS_ENGLISH_WORD.search(token.string) and not HAS_CHINESE.search(token.string):
                    violations.append(f"{path.relative_to(ROOT)}:{token.start[0]}")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    continue
                docstring = ast.get_docstring(node, clean=False)
                if (
                    docstring
                    and HAS_ENGLISH_WORD.search(docstring)
                    and not HAS_CHINESE.search(docstring)
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 1)}")
    assert not violations, "以下 Python 注释或文档字符串未使用中文：" + ", ".join(violations)

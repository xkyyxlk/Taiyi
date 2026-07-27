from __future__ import annotations

import json

from taiyi.application import IdentityService, MemoryService
from taiyi.application.export_service import ExportService
from taiyi.providers import MockProvider
from taiyi.storage import Repository


def test_jsonl_and_markdown_export(repository: Repository, tmp_path) -> None:  # type: ignore[no-untyped-def]
    identity = IdentityService(repository)
    identity.initialize("Taiyi")
    identity.fork("branch")
    MemoryService(repository, MockProvider()).chat("branch", "hello")
    paths = ExportService(repository).export(tmp_path / "export")
    assert {path.suffix for path in paths} == {".jsonl", ".md"}
    records = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines()]
    assert {record["kind"] for record in records} >= {
        "core",
        "snapshot",
        "incarnation",
        "event",
        "memory",
        "audit",
    }

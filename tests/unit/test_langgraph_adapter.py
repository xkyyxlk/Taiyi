from __future__ import annotations

import json
import socket
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from taiyi.adapters import (
    SUPPORTED_LANGGRAPH_VERSION,
    SUPPORTED_LANGSMITH_VERSION,
    adapt_langgraph_json,
    canonical_json_digest,
    instrument_memory_write,
    parse_langgraph_bundle,
)
from taiyi.analysis import (
    RULE_MISSING_SOURCE,
    MemoryType,
    Scope,
    ScopeKind,
    analyze_jsonl,
    parse_jsonl,
)

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "adapters" / "langgraph-langsmith" / "v1"


def _fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _raw_bundle() -> dict[str, object]:
    value = json.loads(_fixture("run-bundle.json"))
    assert isinstance(value, dict)
    return value


def test_offline_fixture_matches_golden_protocol() -> None:
    first = adapt_langgraph_json(_fixture("run-bundle.json"))
    second = adapt_langgraph_json(_fixture("run-bundle.json"))

    assert first == second == _fixture("expected.jsonl")
    parsed = parse_jsonl(first)
    report = analyze_jsonl(first)
    assert parsed.manifest.tool_versions["langgraph"] == SUPPORTED_LANGGRAPH_VERSION
    assert parsed.manifest.tool_versions["langsmith"] == SUPPORTED_LANGSMITH_VERSION
    assert report.summary.content_modified == 1
    assert report.summary.structure_changed == 1
    assert report.findings == ()
    assert "red tea" not in first
    assert "green tea" not in first


def test_missing_explicit_sources_are_reported_without_guessing() -> None:
    raw = _raw_bundle()
    writes = raw["writes"]
    assert isinstance(writes, list)
    current_write = writes[1]
    assert isinstance(current_write, dict)
    current_write["source_run_ids"] = []

    report = analyze_jsonl(adapt_langgraph_json(json.dumps(raw)))

    assert [finding.rule_id for finding in report.findings] == [RULE_MISSING_SOURCE]


def test_unsupported_framework_version_is_rejected() -> None:
    raw = _raw_bundle()
    frameworks = raw["frameworks"]
    assert isinstance(frameworks, dict)
    frameworks["langgraph"] = "1.2.9"

    with pytest.raises(ValueError, match="1.2.10"):
        parse_langgraph_bundle(json.dumps(raw))


def test_store_value_must_match_instrumented_write() -> None:
    raw = _raw_bundle()
    after = raw["after"]
    assert isinstance(after, dict)
    items = after["items"]
    assert isinstance(items, list)
    item = items[0]
    assert isinstance(item, dict)
    item["value"] = {"preference": "coffee"}

    with pytest.raises(ValueError, match="内容不一致"):
        parse_langgraph_bundle(json.dumps(raw))


def test_instrumentation_hashes_canonical_json_without_mutation() -> None:
    value = {"b": [2, 1], "a": "值"}
    original = deepcopy(value)

    write = instrument_memory_write(
        write_id="write_1",
        namespace=("user_alice", "memories"),
        key="preference",
        value=value,
        memory_id="memory_1",
        scope=Scope(kind=ScopeKind.USER, id="user_alice"),
        memory_type=MemoryType.PREFERENCE,
        occurred_at=datetime(2026, 7, 29, 6, tzinfo=UTC),
        source_run_ids=("run_1",),
        writer_version="writer-v1",
        memory_version="1",
    )

    assert value == original
    assert write.value_sha256 == canonical_json_digest({"a": "值", "b": [2, 1]})
    assert write.occurred_at.isoformat() == "2026-07-29T06:00:00+00:00"


def test_adapter_path_does_not_open_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("适配器不应打开网络连接")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    adapt_langgraph_json(_fixture("run-bundle.json"))

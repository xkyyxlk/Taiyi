from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from taiyi.analysis.models import (
    AnalysisRecord,
    EventRecord,
    EventType,
    Identifier,
    ManifestRecord,
    MemoryRecord,
    MemoryType,
    Producer,
    ProtocolModel,
    RecordType,
    Scope,
    Sha256Digest,
    SnapshotRecord,
    SnapshotRole,
    Timestamp,
    VersionString,
)
from taiyi.analysis.protocol import parse_jsonl

ADAPTER_VERSION = "1.0"
SUPPORTED_LANGGRAPH_VERSION = "1.2.10"
SUPPORTED_LANGSMITH_VERSION = "0.10.11"
PRODUCER_NAME = "taiyi-langgraph-langsmith"


class FrameworkVersions(ProtocolModel):
    langgraph: Literal["1.2.10"]
    langsmith: Literal["0.10.11"]


class AdapterManifest(ProtocolModel):
    project_id: Identifier
    run_id: Identifier
    baseline_run_id: Identifier | None = None
    captured_at: Timestamp
    model_version: VersionString
    prompt_version: VersionString
    tool_versions: dict[Identifier, VersionString]
    writer_version: VersionString


class LangGraphStoreItem(ProtocolModel):
    namespace: tuple[Identifier, ...] = Field(min_length=1)
    key: Identifier
    value: JsonValue
    created_at: Timestamp
    updated_at: Timestamp
    write_id: Identifier

    @model_validator(mode="after")
    def timestamps_are_ordered(self) -> LangGraphStoreItem:
        if self.updated_at < self.created_at:
            raise ValueError("LangGraph Store 项目的 updated_at 不得早于 created_at")
        canonical_json_digest(self.value)
        return self


class LangGraphSnapshot(ProtocolModel):
    checkpoint_id: Identifier
    captured_at: Timestamp
    items: tuple[LangGraphStoreItem, ...]

    @model_validator(mode="after")
    def item_keys_are_unique(self) -> LangGraphSnapshot:
        keys = [(item.namespace, item.key) for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("同一 LangGraph 快照中的 namespace 与 key 组合必须唯一")
        return self


class LangSmithRun(ProtocolModel):
    run_id: Identifier
    parent_run_id: Identifier | None = None
    run_type: Literal["chain", "llm", "tool", "retriever", "embedding", "prompt", "parser"]
    scope: Scope
    started_at: Timestamp
    inputs: JsonValue
    outputs: JsonValue

    @model_validator(mode="after")
    def payload_is_json(self) -> LangSmithRun:
        canonical_json_digest({"inputs": self.inputs, "outputs": self.outputs})
        return self


class InstrumentedMemoryWrite(ProtocolModel):
    write_id: Identifier
    namespace: tuple[Identifier, ...] = Field(min_length=1)
    key: Identifier
    memory_id: Identifier
    scope: Scope
    memory_type: MemoryType
    occurred_at: Timestamp
    source_run_ids: tuple[Identifier, ...]
    writer_version: VersionString
    memory_version: VersionString | None = None
    value_sha256: Sha256Digest

    @model_validator(mode="after")
    def sources_are_unique(self) -> InstrumentedMemoryWrite:
        if len(self.source_run_ids) != len(set(self.source_run_ids)):
            raise ValueError("显式记忆写入的 source_run_ids 不得重复")
        return self


class LangGraphLangSmithBundle(ProtocolModel):
    format_version: Literal["1.0"]
    frameworks: FrameworkVersions
    manifest: AdapterManifest
    before: LangGraphSnapshot
    runs: tuple[LangSmithRun, ...]
    writes: tuple[InstrumentedMemoryWrite, ...]
    after: LangGraphSnapshot

    @model_validator(mode="after")
    def references_are_consistent(self) -> LangGraphLangSmithBundle:
        if self.before.checkpoint_id == self.after.checkpoint_id:
            raise ValueError("前后 LangGraph 快照必须使用不同 checkpoint_id")

        run_ids = [run.run_id for run in self.runs]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("LangSmith run_id 必须唯一")
        write_ids = [write.write_id for write in self.writes]
        if len(write_ids) != len(set(write_ids)):
            raise ValueError("显式记忆写入的 write_id 必须唯一")
        event_ids = set(run_ids)
        collisions = event_ids & set(write_ids)
        if collisions:
            raise ValueError(f"run_id 与 write_id 不得重复：{', '.join(sorted(collisions))}")

        known_runs = set(run_ids)
        for run in self.runs:
            if run.parent_run_id is not None and run.parent_run_id not in known_runs:
                raise ValueError(f"LangSmith 运行 {run.run_id} 引用了未导出的父运行")
        for write in self.writes:
            missing_sources = set(write.source_run_ids) - known_runs
            if missing_sources:
                raise ValueError(
                    f"显式记忆写入 {write.write_id} 引用了未导出的来源运行："
                    f"{', '.join(sorted(missing_sources))}"
                )

        writes_by_id = {write.write_id: write for write in self.writes}
        referenced_write_ids: set[str] = set()
        for snapshot in (self.before, self.after):
            memory_ids: list[str] = []
            for item in snapshot.items:
                linked_write = writes_by_id.get(item.write_id)
                if linked_write is None:
                    raise ValueError(f"LangGraph 项目 {item.namespace}/{item.key} 缺少显式写入记录")
                if linked_write.namespace != item.namespace or linked_write.key != item.key:
                    raise ValueError(
                        f"显式写入 {linked_write.write_id} 与 LangGraph 项目标识不一致"
                    )
                if linked_write.value_sha256 != canonical_json_digest(item.value):
                    raise ValueError(
                        f"显式写入 {linked_write.write_id} 与 LangGraph 项目内容不一致"
                    )
                memory_ids.append(linked_write.memory_id)
                referenced_write_ids.add(linked_write.write_id)
            if len(memory_ids) != len(set(memory_ids)):
                raise ValueError("同一 LangGraph 快照映射后的 memory_id 必须唯一")
        unused_write_ids = set(writes_by_id) - referenced_write_ids
        if unused_write_ids:
            raise ValueError(
                f"显式记忆写入没有对应前后快照项目：{', '.join(sorted(unused_write_ids))}"
            )

        reserved_versions = {
            "langgraph": self.frameworks.langgraph,
            "langsmith": self.frameworks.langsmith,
        }
        for name, expected in reserved_versions.items():
            actual = self.manifest.tool_versions.get(name)
            if actual is not None and actual != expected:
                raise ValueError(f"tool_versions 中的 {name} 版本与 frameworks 不一致")
        return self


class _DuplicateKeyError(ValueError):
    pass


def _object_without_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"JSON 对象包含重复字段：{key}")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"JSON 不允许非有限数字：{value}")


def canonical_json_digest(value: JsonValue) -> str:
    try:
        content = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("适配器值必须是有限的 JSON 数据") from exc
    return sha256(content.encode("utf-8")).hexdigest()


def instrument_memory_write(
    *,
    write_id: str,
    namespace: tuple[str, ...],
    key: str,
    value: JsonValue,
    memory_id: str,
    scope: Scope,
    memory_type: MemoryType,
    occurred_at: datetime | str,
    source_run_ids: tuple[str, ...],
    writer_version: str,
    memory_version: str | None = None,
) -> InstrumentedMemoryWrite:
    return InstrumentedMemoryWrite(
        write_id=write_id,
        namespace=namespace,
        key=key,
        memory_id=memory_id,
        scope=scope,
        memory_type=memory_type,
        occurred_at=_timestamp(occurred_at) if isinstance(occurred_at, datetime) else occurred_at,
        source_run_ids=source_run_ids,
        writer_version=writer_version,
        memory_version=memory_version,
        value_sha256=canonical_json_digest(value),
    )


def parse_langgraph_bundle(content: str) -> LangGraphLangSmithBundle:
    try:
        raw = json.loads(
            content,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except (json.JSONDecodeError, _DuplicateKeyError, ValueError) as exc:
        raise ValueError(f"LangGraph/LangSmith 适配器输入不是有效 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("LangGraph/LangSmith 适配器输入必须是 JSON 对象")
    try:
        return LangGraphLangSmithBundle.model_validate(raw)
    except ValueError as exc:
        raise ValueError(f"LangGraph/LangSmith 适配器输入不符合 1.0 契约：{exc}") from exc


def _event_type(run_type: str) -> EventType:
    return {
        "llm": EventType.MODEL_OUTPUT,
        "tool": EventType.TOOL_RESULT,
        "retriever": EventType.DOCUMENT_READ,
    }.get(run_type, EventType.SYSTEM)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _run_event(run: LangSmithRun, sequence_number: int) -> EventRecord:
    return EventRecord(
        protocol_version="1.0",
        record_type=RecordType.EVENT,
        sequence_number=sequence_number,
        event_id=run.run_id,
        event_type=_event_type(run.run_type),
        scope=run.scope,
        occurred_at=_timestamp(run.started_at),
        content_hash=canonical_json_digest({"inputs": run.inputs, "outputs": run.outputs}),
        parent_event_ids=() if run.parent_run_id is None else (run.parent_run_id,),
    )


def _write_event(write: InstrumentedMemoryWrite, sequence_number: int) -> EventRecord:
    return EventRecord(
        protocol_version="1.0",
        record_type=RecordType.EVENT,
        sequence_number=sequence_number,
        event_id=write.write_id,
        event_type=EventType.MEMORY_WRITE,
        scope=write.scope,
        occurred_at=_timestamp(write.occurred_at),
        content_hash=write.value_sha256,
        parent_event_ids=write.source_run_ids,
    )


def _memory_record(
    item: LangGraphStoreItem,
    write: InstrumentedMemoryWrite,
    snapshot_id: str,
    sequence_number: int,
) -> MemoryRecord:
    return MemoryRecord(
        protocol_version="1.0",
        record_type=RecordType.MEMORY,
        sequence_number=sequence_number,
        snapshot_id=snapshot_id,
        memory_id=write.memory_id,
        scope=write.scope,
        memory_type=write.memory_type,
        content_hash=write.value_sha256,
        source_event_ids=write.source_run_ids,
        created_at=_timestamp(item.created_at),
        updated_at=_timestamp(item.updated_at),
        writer_version=write.writer_version,
        memory_version=write.memory_version,
    )


def adapt_langgraph_langsmith(bundle: LangGraphLangSmithBundle) -> str:
    framework_versions = {
        "langgraph": bundle.frameworks.langgraph,
        "langsmith": bundle.frameworks.langsmith,
    }
    records: list[AnalysisRecord] = [
        ManifestRecord(
            protocol_version="1.0",
            record_type=RecordType.MANIFEST,
            sequence_number=1,
            project_id=bundle.manifest.project_id,
            run_id=bundle.manifest.run_id,
            baseline_run_id=bundle.manifest.baseline_run_id,
            captured_at=_timestamp(bundle.manifest.captured_at),
            producer=Producer(name=PRODUCER_NAME, version=ADAPTER_VERSION),
            model_version=bundle.manifest.model_version,
            prompt_version=bundle.manifest.prompt_version,
            tool_versions={**bundle.manifest.tool_versions, **framework_versions},
            writer_version=bundle.manifest.writer_version,
        ),
        SnapshotRecord(
            protocol_version="1.0",
            record_type=RecordType.SNAPSHOT,
            sequence_number=2,
            snapshot_id=bundle.before.checkpoint_id,
            snapshot_role=SnapshotRole.BEFORE,
            captured_at=_timestamp(bundle.before.captured_at),
        ),
    ]
    writes_by_id = {write.write_id: write for write in bundle.writes}
    for item in sorted(
        bundle.before.items,
        key=lambda value: writes_by_id[value.write_id].memory_id,
    ):
        records.append(
            _memory_record(
                item,
                writes_by_id[item.write_id],
                bundle.before.checkpoint_id,
                len(records) + 1,
            )
        )

    events: list[tuple[datetime, str, LangSmithRun | InstrumentedMemoryWrite]] = [
        (run.started_at, run.run_id, run) for run in bundle.runs
    ]
    events.extend((write.occurred_at, write.write_id, write) for write in bundle.writes)
    for _, _, event in sorted(events, key=lambda value: (value[0], value[1])):
        sequence_number = len(records) + 1
        if isinstance(event, LangSmithRun):
            records.append(_run_event(event, sequence_number))
        else:
            records.append(_write_event(event, sequence_number))

    records.append(
        SnapshotRecord(
            protocol_version="1.0",
            record_type=RecordType.SNAPSHOT,
            sequence_number=len(records) + 1,
            snapshot_id=bundle.after.checkpoint_id,
            snapshot_role=SnapshotRole.AFTER,
            captured_at=_timestamp(bundle.after.captured_at),
        )
    )
    for item in sorted(
        bundle.after.items,
        key=lambda value: writes_by_id[value.write_id].memory_id,
    ):
        records.append(
            _memory_record(
                item,
                writes_by_id[item.write_id],
                bundle.after.checkpoint_id,
                len(records) + 1,
            )
        )

    output = (
        "\n".join(
            json.dumps(
                record.model_dump(mode="json", exclude_none=True),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for record in records
        )
        + "\n"
    )
    parse_jsonl(output)
    return output


def adapt_langgraph_json(content: str) -> str:
    return adapt_langgraph_langsmith(parse_langgraph_bundle(content))

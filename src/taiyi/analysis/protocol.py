from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, TypeAdapter, ValidationError

from taiyi.analysis.models import (
    AnalysisRecord,
    EventRecord,
    ManifestRecord,
    MemoryRecord,
    RecordType,
    SnapshotRecord,
    SnapshotRole,
)

RecordAdapter: TypeAdapter[AnalysisRecord] = TypeAdapter(
    Annotated[
        ManifestRecord | SnapshotRecord | EventRecord | MemoryRecord,
        Field(discriminator="record_type"),
    ]
)


class ProtocolError(ValueError):
    pass


class _DuplicateKeyError(ValueError):
    pass


@dataclass(frozen=True)
class AnalysisInput:
    manifest: ManifestRecord
    before_snapshot: SnapshotRecord
    after_snapshot: SnapshotRecord
    events: tuple[EventRecord, ...]
    before_memories: tuple[MemoryRecord, ...]
    after_memories: tuple[MemoryRecord, ...]
    records: tuple[AnalysisRecord, ...]


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKeyError(f"JSON 对象包含重复字段：{key}")
        value[key] = item
    return value


def _parse_record(line: str, line_number: int) -> AnalysisRecord:
    try:
        raw = json.loads(line, object_pairs_hook=_object_without_duplicate_keys)
    except (json.JSONDecodeError, _DuplicateKeyError) as exc:
        raise ProtocolError(f"第 {line_number} 行不是有效 JSON：{exc}") from exc
    if not isinstance(raw, dict):
        raise ProtocolError(f"第 {line_number} 行必须是 JSON 对象")
    try:
        return RecordAdapter.validate_python(raw)
    except ValidationError as exc:
        raise ProtocolError(f"第 {line_number} 行不符合协议：{exc}") from exc


def parse_jsonl(content: str) -> AnalysisInput:
    if not content:
        raise ProtocolError("协议输入不能为空")
    lines = content.splitlines()
    if not lines:
        raise ProtocolError("协议输入不能为空")
    if any(not line.strip() for line in lines):
        raise ProtocolError("JSONL 不允许空行")

    records = tuple(_parse_record(line, index) for index, line in enumerate(lines, 1))
    for expected_sequence, record in enumerate(records, 1):
        if record.sequence_number != expected_sequence:
            raise ProtocolError(
                f"第 {expected_sequence} 行的 sequence_number 必须为 {expected_sequence}"
            )

    if not isinstance(records[0], ManifestRecord):
        raise ProtocolError("第一条记录必须是 manifest")
    if any(isinstance(record, ManifestRecord) for record in records[1:]):
        raise ProtocolError("每个协议文件只能包含一条 manifest")

    before_snapshot: SnapshotRecord | None = None
    after_snapshot: SnapshotRecord | None = None
    before_memories: list[MemoryRecord] = []
    after_memories: list[MemoryRecord] = []
    events: list[EventRecord] = []
    phase = "before_snapshot"

    for record in records[1:]:
        if isinstance(record, SnapshotRecord):
            if record.snapshot_role is SnapshotRole.BEFORE and phase == "before_snapshot":
                before_snapshot = record
                phase = "before_memories"
                continue
            if record.snapshot_role is SnapshotRole.AFTER and phase in {
                "before_memories",
                "events",
            }:
                after_snapshot = record
                phase = "after_memories"
                continue
            raise ProtocolError("快照记录顺序必须是 before 后接 after，且每种角色只能出现一次")

        if isinstance(record, MemoryRecord):
            if phase == "before_memories" and before_snapshot is not None:
                if record.snapshot_id != before_snapshot.snapshot_id:
                    raise ProtocolError("before 记忆的 snapshot_id 与快照不一致")
                before_memories.append(record)
                continue
            if phase == "after_memories" and after_snapshot is not None:
                if record.snapshot_id != after_snapshot.snapshot_id:
                    raise ProtocolError("after 记忆的 snapshot_id 与快照不一致")
                after_memories.append(record)
                continue
            raise ProtocolError("记忆记录必须紧随所属快照，并位于允许的协议阶段")

        if isinstance(record, EventRecord):
            if phase not in {"before_memories", "events"}:
                raise ProtocolError("事件记录必须位于 before 与 after 快照之间")
            phase = "events"
            events.append(record)
            continue

        if record.record_type is RecordType.MANIFEST:
            raise ProtocolError("每个协议文件只能包含一条 manifest")

    if before_snapshot is None or after_snapshot is None:
        raise ProtocolError("协议文件必须各包含一条 before 和 after 快照")
    if before_snapshot.snapshot_id == after_snapshot.snapshot_id:
        raise ProtocolError("before 和 after 必须使用不同的 snapshot_id")

    _validate_unique_ids(events, before_memories, after_memories)
    _validate_references(events, before_memories, after_memories)

    return AnalysisInput(
        manifest=records[0],
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        events=tuple(events),
        before_memories=tuple(before_memories),
        after_memories=tuple(after_memories),
        records=records,
    )


def _validate_unique_ids(
    events: list[EventRecord],
    before_memories: list[MemoryRecord],
    after_memories: list[MemoryRecord],
) -> None:
    event_ids = [event.event_id for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ProtocolError("event_id 在同一协议文件中必须唯一")
    for role, memories in (("before", before_memories), ("after", after_memories)):
        memory_ids = [memory.memory_id for memory in memories]
        if len(memory_ids) != len(set(memory_ids)):
            raise ProtocolError(f"{role} 快照中的 memory_id 必须唯一")


def _validate_references(
    events: list[EventRecord],
    before_memories: list[MemoryRecord],
    after_memories: list[MemoryRecord],
) -> None:
    event_ids = {event.event_id for event in events}
    for event in events:
        if event.event_id in event.parent_event_ids:
            raise ProtocolError(f"事件 {event.event_id} 不能引用自身为父事件")
        missing_parents = set(event.parent_event_ids) - event_ids
        if missing_parents:
            raise ProtocolError(
                f"事件 {event.event_id} 引用了不存在的父事件：{', '.join(sorted(missing_parents))}"
            )
    for memory in (*before_memories, *after_memories):
        missing_sources = set(memory.source_event_ids) - event_ids
        if missing_sources:
            raise ProtocolError(
                f"记忆 {memory.memory_id} 引用了不存在的来源事件："
                f"{', '.join(sorted(missing_sources))}"
            )


def read_jsonl(path: Path) -> AnalysisInput:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError("协议文件必须使用 UTF-8 编码") from exc
    return parse_jsonl(content)

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.event import listen
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from taiyi.domain import (
    AuditEvent,
    EventType,
    IdentityCore,
    IdentitySnapshot,
    Incarnation,
    IncarnationStatus,
    Memory,
    MemoryDraft,
    MemoryStatus,
    MemoryType,
    MergeProposal,
    ProposalStatus,
    WorldlineEvent,
    new_id,
    utc_now,
)


class TaiyiError(RuntimeError):
    """Base class for expected user-facing errors."""


class NotFoundError(TaiyiError):
    pass


class ConflictError(TaiyiError):
    pass


class Base(DeclarativeBase):
    pass


class CoreRecord(Base):
    __tablename__ = "identity_cores"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_snapshot_id: Mapped[str] = mapped_column(String)


class SnapshotRecord(Base):
    __tablename__ = "identity_snapshots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    core_id: Mapped[str] = mapped_column(ForeignKey("identity_cores.id"), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IncarnationRecord(Base):
    __tablename__ = "incarnations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    core_id: Mapped[str] = mapped_column(ForeignKey("identity_cores.id"), index=True)
    base_snapshot_id: Mapped[str] = mapped_column(ForeignKey("identity_snapshots.id"))
    worldline_id: Mapped[str] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("core_id", "name", name="uq_incarnation_core_name"),)


class EventRecord(Base):
    __tablename__ = "worldline_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    worldline_id: Mapped[str] = mapped_column(String, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String)
    payload_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("worldline_id", "sequence_number", name="uq_worldline_sequence"),
    )


class EventPayloadRecord(Base):
    __tablename__ = "event_payloads"
    event_id: Mapped[str] = mapped_column(ForeignKey("worldline_events.id"), primary_key=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryRecord(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    worldline_id: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    source_event_ids_json: Mapped[str] = mapped_column(Text)
    extractor: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String)
    confidence: Mapped[str] = mapped_column(String)
    importance: Mapped[str] = mapped_column(String)
    tags_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProposalRecord(Base):
    __tablename__ = "merge_proposals"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    core_id: Mapped[str] = mapped_column(ForeignKey("identity_cores.id"), index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditRecord(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    core_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    operation: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_dump(payload).encode("utf-8")).hexdigest()


def _enable_sqlite(connection: Any, _record: Any) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(f"sqlite:///{path}", future=True)
        listen(self.engine, "connect", _enable_sqlite)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_core(
        self, name: str, self_description: str
    ) -> tuple[IdentityCore, IdentitySnapshot]:
        now = utc_now()
        core_id = new_id("core")
        snapshot = IdentitySnapshot(
            id=new_id("snap"),
            core_id=core_id,
            self_description=self_description,
            created_at=now,
        )
        core = IdentityCore(
            id=core_id,
            name=name,
            created_at=now,
            current_snapshot_id=snapshot.id,
        )
        with self.database.session() as session, session.begin():
            existing = session.query(CoreRecord).first()
            if existing is not None:
                raise ConflictError(
                    f"data directory already contains identity core: {existing.name}"
                )
            session.add(
                CoreRecord(
                    id=core.id,
                    name=core.name,
                    created_at=core.created_at,
                    current_snapshot_id=core.current_snapshot_id,
                )
            )
            session.add(self._snapshot_record(snapshot))
            self._add_audit(session, core.id, "core.created", {"snapshot_id": snapshot.id})
        return core, snapshot

    def get_core(self, core_id: str | None = None) -> IdentityCore:
        with self.database.session() as session:
            query = session.query(CoreRecord)
            record = (
                query.filter_by(id=core_id).first()
                if core_id
                else query.order_by(CoreRecord.created_at).first()
            )
            if record is None:
                raise NotFoundError("no identity core exists; run `taiyi init <name>` first")
            return self._core(record)

    def get_snapshot(self, snapshot_id: str) -> IdentitySnapshot:
        with self.database.session() as session:
            record = session.get(SnapshotRecord, snapshot_id)
            if record is None:
                raise NotFoundError(f"snapshot not found: {snapshot_id}")
            return IdentitySnapshot.model_validate_json(record.payload_json)

    def list_snapshots(self, core_id: str) -> list[IdentitySnapshot]:
        with self.database.session() as session:
            records = (
                session.query(SnapshotRecord)
                .filter_by(core_id=core_id)
                .order_by(SnapshotRecord.created_at)
                .all()
            )
            return [IdentitySnapshot.model_validate_json(record.payload_json) for record in records]

    def create_incarnation(self, core_id: str, snapshot_id: str, name: str) -> Incarnation:
        incarnation = Incarnation(
            id=new_id("inc"),
            name=name,
            core_id=core_id,
            base_snapshot_id=snapshot_id,
            worldline_id=new_id("world"),
            status=IncarnationStatus.ACTIVE,
            created_at=utc_now(),
        )
        with self.database.session() as session, session.begin():
            if session.query(IncarnationRecord).filter_by(core_id=core_id, name=name).first():
                raise ConflictError(f"incarnation already exists: {name}")
            if session.get(SnapshotRecord, snapshot_id) is None:
                raise NotFoundError(f"snapshot not found: {snapshot_id}")
            session.add(
                IncarnationRecord(
                    id=incarnation.id,
                    name=incarnation.name,
                    core_id=incarnation.core_id,
                    base_snapshot_id=incarnation.base_snapshot_id,
                    worldline_id=incarnation.worldline_id,
                    status=incarnation.status.value,
                    created_at=incarnation.created_at,
                )
            )
            self._add_audit(
                session,
                core_id,
                "incarnation.created",
                {"incarnation_id": incarnation.id, "snapshot_id": snapshot_id},
            )
        return incarnation

    def get_incarnation(self, name_or_id: str) -> Incarnation:
        with self.database.session() as session:
            record = session.get(IncarnationRecord, name_or_id)
            if record is None:
                record = session.query(IncarnationRecord).filter_by(name=name_or_id).first()
            if record is None:
                raise NotFoundError(f"incarnation not found: {name_or_id}")
            return self._incarnation(record)

    def list_incarnations(self, core_id: str) -> list[Incarnation]:
        with self.database.session() as session:
            records = (
                session.query(IncarnationRecord)
                .filter_by(core_id=core_id)
                .order_by(IncarnationRecord.created_at)
                .all()
            )
            return [self._incarnation(record) for record in records]

    def append_event(
        self, worldline_id: str, event_type: EventType, payload: dict[str, Any]
    ) -> WorldlineEvent:
        with self.database.session() as session, session.begin():
            if (
                session.query(IncarnationRecord).filter_by(worldline_id=worldline_id).first()
                is None
            ):
                raise NotFoundError(f"worldline not found: {worldline_id}")
            last = (
                session.query(EventRecord)
                .filter_by(worldline_id=worldline_id)
                .order_by(EventRecord.sequence_number.desc())
                .first()
            )
            event = WorldlineEvent(
                id=new_id("evt"),
                worldline_id=worldline_id,
                sequence_number=1 if last is None else last.sequence_number + 1,
                event_type=event_type,
                payload=payload,
                payload_hash=payload_hash(payload),
                created_at=utc_now(),
            )
            event_record = EventRecord(
                id=event.id,
                worldline_id=event.worldline_id,
                sequence_number=event.sequence_number,
                event_type=event.event_type.value,
                payload_hash=event.payload_hash,
                created_at=event.created_at,
            )
            session.add(event_record)
            session.flush()
            session.add(EventPayloadRecord(event_id=event.id, payload_json=_dump(payload)))
            return event

    def list_events(self, worldline_id: str) -> list[WorldlineEvent]:
        with self.database.session() as session:
            rows = (
                session.query(EventRecord, EventPayloadRecord)
                .outerjoin(EventPayloadRecord, EventPayloadRecord.event_id == EventRecord.id)
                .filter(EventRecord.worldline_id == worldline_id)
                .order_by(EventRecord.sequence_number)
                .all()
            )
            return [self._event(event, payload) for event, payload in rows]

    def get_event(self, event_id: str) -> WorldlineEvent:
        with self.database.session() as session:
            event = session.get(EventRecord, event_id)
            if event is None:
                raise NotFoundError(f"event not found: {event_id}")
            body = session.get(EventPayloadRecord, event_id)
            return self._event(event, body)

    def redact_event(self, event_id: str) -> int:
        with self.database.session() as session, session.begin():
            event = session.get(EventRecord, event_id)
            if event is None:
                raise NotFoundError(f"event not found: {event_id}")
            rows = (
                session.query(EventRecord, EventPayloadRecord)
                .join(EventPayloadRecord, EventPayloadRecord.event_id == EventRecord.id)
                .filter(EventRecord.worldline_id == event.worldline_id)
                .all()
            )
            bodies = {
                row.id: json.loads(body.payload_json)
                for row, body in rows
                if body.payload_json is not None
            }
            redacted_ids = {event_id}
            changed = True
            while changed:
                changed = False
                for candidate_id, payload in bodies.items():
                    references = set(payload.get("source_event_ids", []))
                    reply_to = payload.get("in_reply_to_event_id")
                    if reply_to:
                        references.add(reply_to)
                    if candidate_id not in redacted_ids and references.intersection(redacted_ids):
                        redacted_ids.add(candidate_id)
                        changed = True
            deleted_at = utc_now()
            for row, body in rows:
                if row.id in redacted_ids and body.deleted_at is None:
                    body.payload_json = None
                    body.deleted_at = deleted_at
            affected = 0
            for memory in (
                session.query(MemoryRecord).filter_by(worldline_id=event.worldline_id).all()
            ):
                if (
                    set(json.loads(memory.source_event_ids_json)).intersection(redacted_ids)
                    and memory.status != MemoryStatus.DELETED
                ):
                    memory.content = "[deleted]"
                    memory.status = MemoryStatus.DELETED.value
                    affected += 1
            incarnation = (
                session.query(IncarnationRecord).filter_by(worldline_id=event.worldline_id).one()
            )
            self._add_audit(
                session,
                incarnation.core_id,
                "event.redacted",
                {
                    "event_id": event_id,
                    "cascade_event_ids": sorted(redacted_ids),
                    "derived_memories_deleted": affected,
                },
            )
            return affected

    def add_memories(
        self,
        worldline_id: str,
        drafts: Iterable[MemoryDraft],
        extractor: str,
        prompt_version: str,
    ) -> list[Memory]:
        events = {event.id: event for event in self.list_events(worldline_id)}
        memories: list[Memory] = []
        for draft in drafts:
            if any(source_id not in events for source_id in draft.source_event_ids):
                raise ConflictError("memory source must belong to the same worldline")
            memories.append(
                Memory(
                    id=new_id("mem"),
                    worldline_id=worldline_id,
                    type=draft.type,
                    content=draft.content,
                    source_event_ids=draft.source_event_ids,
                    extractor=extractor,
                    prompt_version=prompt_version,
                    confidence=draft.confidence,
                    importance=draft.importance,
                    tags=draft.tags,
                    status=MemoryStatus.CANDIDATE,
                    created_at=utc_now(),
                )
            )
        with self.database.session() as session, session.begin():
            session.add_all([self._memory_record(memory) for memory in memories])
        return memories

    def list_memories(self, worldline_id: str, include_deleted: bool = False) -> list[Memory]:
        with self.database.session() as session:
            query = session.query(MemoryRecord).filter_by(worldline_id=worldline_id)
            if not include_deleted:
                query = query.filter(MemoryRecord.status != MemoryStatus.DELETED.value)
            return [
                self._memory(record) for record in query.order_by(MemoryRecord.created_at).all()
            ]

    def add_merged_memory(
        self,
        proposal_id: str,
        draft: MemoryDraft,
        extractor: str = "human-reviewed-merge",
    ) -> Memory:
        """Create a cross-worldline synthesis while preserving all event provenance."""
        for event_id in draft.source_event_ids:
            self.get_event(event_id)
        memory = Memory(
            id=new_id("mem"),
            worldline_id=f"merge:{proposal_id}",
            type=draft.type,
            content=draft.content,
            source_event_ids=draft.source_event_ids,
            extractor=extractor,
            prompt_version="merge-v1",
            confidence=draft.confidence,
            importance=draft.importance,
            tags=draft.tags,
            status=MemoryStatus.ACCEPTED,
            created_at=utc_now(),
        )
        with self.database.session() as session, session.begin():
            session.add(self._memory_record(memory))
        return memory

    def get_memory(self, memory_id: str) -> Memory:
        with self.database.session() as session:
            record = session.get(MemoryRecord, memory_id)
            if record is None:
                raise NotFoundError(f"memory not found: {memory_id}")
            return self._memory(record)

    def list_all_memories(self, include_deleted: bool = False) -> list[Memory]:
        with self.database.session() as session:
            query = session.query(MemoryRecord)
            if not include_deleted:
                query = query.filter(MemoryRecord.status != MemoryStatus.DELETED.value)
            return [
                self._memory(record) for record in query.order_by(MemoryRecord.created_at).all()
            ]

    def create_proposal(self, proposal: MergeProposal) -> MergeProposal:
        with self.database.session() as session, session.begin():
            session.add(
                ProposalRecord(
                    id=proposal.id,
                    core_id=proposal.core_id,
                    status=proposal.status.value,
                    payload_json=proposal.model_dump_json(),
                    created_at=proposal.created_at,
                )
            )
            self._add_audit(
                session,
                proposal.core_id,
                "merge.proposed",
                {"proposal_id": proposal.id, "worldline_ids": proposal.worldline_ids},
            )
        return proposal

    def get_proposal(self, proposal_id: str) -> MergeProposal:
        with self.database.session() as session:
            record = session.get(ProposalRecord, proposal_id)
            if record is None:
                raise NotFoundError(f"merge proposal not found: {proposal_id}")
            return MergeProposal.model_validate_json(record.payload_json)

    def list_proposals(self, core_id: str) -> list[MergeProposal]:
        with self.database.session() as session:
            records = (
                session.query(ProposalRecord)
                .filter_by(core_id=core_id)
                .order_by(ProposalRecord.created_at)
                .all()
            )
            return [MergeProposal.model_validate_json(record.payload_json) for record in records]

    def save_proposal(self, proposal: MergeProposal) -> None:
        with self.database.session() as session, session.begin():
            record = session.get(ProposalRecord, proposal.id)
            if record is None:
                raise NotFoundError(f"merge proposal not found: {proposal.id}")
            record.status = proposal.status.value
            record.payload_json = proposal.model_dump_json()
            self._add_audit(
                session,
                proposal.core_id,
                f"merge.{proposal.status.value}",
                {"proposal_id": proposal.id},
            )

    def apply_merge(
        self,
        proposal: MergeProposal,
        snapshot: IdentitySnapshot,
        memories_to_accept: Iterable[str],
        new_memories: Iterable[Memory] = (),
    ) -> None:
        with self.database.session() as session, session.begin():
            record = session.get(ProposalRecord, proposal.id)
            core = session.get(CoreRecord, proposal.core_id)
            if record is None or core is None:
                raise NotFoundError("proposal or identity core not found")
            stored = MergeProposal.model_validate_json(record.payload_json)
            if stored.status is not ProposalStatus.APPROVED:
                raise ConflictError("only an approved proposal can be applied")
            if core.current_snapshot_id != proposal.base_snapshot_id:
                raise ConflictError("core advanced since proposal creation; create a new proposal")
            session.add_all(self._memory_record(memory) for memory in new_memories)
            session.add(self._snapshot_record(snapshot))
            core.current_snapshot_id = snapshot.id
            for memory_id in memories_to_accept:
                memory = session.get(MemoryRecord, memory_id)
                if memory is not None and memory.status != MemoryStatus.DELETED.value:
                    memory.status = MemoryStatus.ACCEPTED.value
            applied = proposal.model_copy(
                update={"status": ProposalStatus.APPLIED, "applied_snapshot_id": snapshot.id}
            )
            record.status = ProposalStatus.APPLIED.value
            record.payload_json = applied.model_dump_json()
            self._add_audit(
                session,
                proposal.core_id,
                "merge.applied",
                {"proposal_id": proposal.id, "snapshot_id": snapshot.id},
            )

    def rollback(self, core_id: str, snapshot_id: str) -> None:
        with self.database.session() as session, session.begin():
            core = session.get(CoreRecord, core_id)
            snapshot = session.get(SnapshotRecord, snapshot_id)
            if core is None or snapshot is None or snapshot.core_id != core_id:
                raise NotFoundError(f"snapshot not found for core: {snapshot_id}")
            previous = core.current_snapshot_id
            core.current_snapshot_id = snapshot_id
            self._add_audit(
                session,
                core_id,
                "core.rolled_back",
                {"from_snapshot_id": previous, "to_snapshot_id": snapshot_id},
            )

    def list_audit_events(self, core_id: str | None = None) -> list[AuditEvent]:
        with self.database.session() as session:
            query = session.query(AuditRecord)
            if core_id:
                query = query.filter_by(core_id=core_id)
            return [self._audit(row) for row in query.order_by(AuditRecord.created_at).all()]

    @staticmethod
    def _core(record: CoreRecord) -> IdentityCore:
        return IdentityCore(
            id=record.id,
            name=record.name,
            created_at=record.created_at,
            current_snapshot_id=record.current_snapshot_id,
        )

    @staticmethod
    def _snapshot_record(snapshot: IdentitySnapshot) -> SnapshotRecord:
        return SnapshotRecord(
            id=snapshot.id,
            core_id=snapshot.core_id,
            payload_json=snapshot.model_dump_json(),
            created_at=snapshot.created_at,
        )

    @staticmethod
    def _incarnation(record: IncarnationRecord) -> Incarnation:
        return Incarnation(
            id=record.id,
            name=record.name,
            core_id=record.core_id,
            base_snapshot_id=record.base_snapshot_id,
            worldline_id=record.worldline_id,
            status=IncarnationStatus(record.status),
            created_at=record.created_at,
        )

    @staticmethod
    def _event(event: EventRecord, payload: EventPayloadRecord | None) -> WorldlineEvent:
        body = None
        deleted_at = None
        if payload is not None:
            deleted_at = payload.deleted_at
            if payload.payload_json is not None:
                body = json.loads(payload.payload_json)
        return WorldlineEvent(
            id=event.id,
            worldline_id=event.worldline_id,
            sequence_number=event.sequence_number,
            event_type=EventType(event.event_type),
            payload=body,
            payload_hash=event.payload_hash,
            payload_deleted_at=deleted_at,
            created_at=event.created_at,
        )

    @staticmethod
    def _memory_record(memory: Memory) -> MemoryRecord:
        return MemoryRecord(
            id=memory.id,
            worldline_id=memory.worldline_id,
            type=memory.type.value,
            content=memory.content,
            source_event_ids_json=_dump(memory.source_event_ids),
            extractor=memory.extractor,
            prompt_version=memory.prompt_version,
            confidence=str(memory.confidence),
            importance=str(memory.importance),
            tags_json=_dump(memory.tags),
            status=memory.status.value,
            created_at=memory.created_at,
        )

    @staticmethod
    def _memory(record: MemoryRecord) -> Memory:
        return Memory(
            id=record.id,
            worldline_id=record.worldline_id,
            type=MemoryType(record.type),
            content=record.content,
            source_event_ids=tuple(json.loads(record.source_event_ids_json)),
            extractor=record.extractor,
            prompt_version=record.prompt_version,
            confidence=float(record.confidence),
            importance=float(record.importance),
            tags=tuple(json.loads(record.tags_json)),
            status=MemoryStatus(record.status),
            created_at=record.created_at,
        )

    @staticmethod
    def _add_audit(
        session: Session, core_id: str | None, operation: str, payload: dict[str, Any]
    ) -> None:
        session.add(
            AuditRecord(
                id=new_id("audit"),
                core_id=core_id,
                operation=operation,
                payload_json=_dump(payload),
                created_at=utc_now(),
            )
        )

    @staticmethod
    def _audit(record: AuditRecord) -> AuditEvent:
        return AuditEvent(
            id=record.id,
            core_id=record.core_id,
            operation=record.operation,
            payload=json.loads(record.payload_json),
            created_at=record.created_at,
        )

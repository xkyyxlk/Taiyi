from __future__ import annotations

from taiyi.domain import IdentityCore, IdentitySnapshot, Incarnation
from taiyi.storage import Repository


class IdentityService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def initialize(
        self, name: str, self_description: str | None = None
    ) -> tuple[IdentityCore, IdentitySnapshot]:
        description = self_description or f"I am {name}, a persistent identity managed by Taiyi."
        return self.repository.create_core(name.strip(), description.strip())

    def show(self) -> tuple[IdentityCore, IdentitySnapshot, list[Incarnation]]:
        core = self.repository.get_core()
        return (
            core,
            self.repository.get_snapshot(core.current_snapshot_id),
            self.repository.list_incarnations(core.id),
        )

    def fork(self, name: str, snapshot_id: str | None = None) -> Incarnation:
        core = self.repository.get_core()
        base_id = snapshot_id or core.current_snapshot_id
        snapshot = self.repository.get_snapshot(base_id)
        if snapshot.core_id != core.id:
            raise ValueError("snapshot belongs to another identity core")
        return self.repository.create_incarnation(core.id, base_id, name.strip())

    def rebirth(self, name: str) -> Incarnation:
        return self.fork(name)

    def rollback(self, snapshot_id: str) -> IdentitySnapshot:
        core = self.repository.get_core()
        snapshot = self.repository.get_snapshot(snapshot_id)
        if snapshot.core_id != core.id:
            raise ValueError("snapshot belongs to another identity core")
        self.repository.rollback(core.id, snapshot_id)
        return snapshot

from __future__ import annotations

from typing import Protocol

from taiyi.domain import IdentitySnapshot, Memory, MemoryDraft, WorldlineEvent


class ModelProvider(Protocol):
    name: str
    prompt_version: str

    def respond(
        self,
        snapshot: IdentitySnapshot,
        events: list[WorldlineEvent],
        inherited_memories: list[Memory],
    ) -> str: ...

    def extract_memories(self, events: list[WorldlineEvent]) -> list[MemoryDraft]: ...

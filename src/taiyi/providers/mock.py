from __future__ import annotations

import re

from taiyi.domain import (
    EventType,
    IdentitySnapshot,
    Memory,
    MemoryDraft,
    MemoryType,
    WorldlineEvent,
)


class MockProvider:
    name = "mock"
    prompt_version = "mock-v1"

    def respond(
        self,
        snapshot: IdentitySnapshot,
        events: list[WorldlineEvent],
        inherited_memories: list[Memory],
    ) -> str:
        del snapshot, inherited_memories
        latest = next(
            (
                str(event.payload.get("content", ""))
                for event in reversed(events)
                if event.event_type is EventType.USER_MESSAGE and event.payload
            ),
            "",
        )
        return f"Mock response: {latest}"

    def extract_memories(self, events: list[WorldlineEvent]) -> list[MemoryDraft]:
        drafts: list[MemoryDraft] = []
        for event in events:
            if event.event_type is not EventType.USER_MESSAGE or not event.payload:
                continue
            text = str(event.payload.get("content", "")).strip()
            if not text:
                continue
            match = re.match(r"(?i)^remember\s+\[([^]]+)]\s*:\s*(.+)$", text)
            if match:
                tag, content = match.groups()
                memory_type = MemoryType.SEMANTIC
                tags: tuple[str, ...] = (tag.strip().casefold(),)
            else:
                content = f"User said: {text}"
                memory_type = MemoryType.EPISODIC
                tags = ()
            drafts.append(
                MemoryDraft(
                    type=memory_type,
                    content=content,
                    source_event_ids=(event.id,),
                    confidence=1.0,
                    importance=0.5,
                    tags=tags,
                )
            )
        return drafts

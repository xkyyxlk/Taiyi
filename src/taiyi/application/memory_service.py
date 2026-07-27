from __future__ import annotations

from taiyi.domain import EventType, Memory, WorldlineEvent
from taiyi.providers.base import ModelProvider
from taiyi.storage import Repository


class MemoryService:
    def __init__(self, repository: Repository, provider: ModelProvider) -> None:
        self.repository = repository
        self.provider = provider

    def chat(self, incarnation_name: str, message: str) -> tuple[str, list[Memory]]:
        incarnation = self.repository.get_incarnation(incarnation_name)
        snapshot = self.repository.get_snapshot(incarnation.base_snapshot_id)
        inherited_memories = [
            self.repository.get_memory(memory_id)
            for memory_id in snapshot.accepted_memory_ids
            if self._memory_available(memory_id)
        ]
        user_event = self.repository.append_event(
            incarnation.worldline_id,
            EventType.USER_MESSAGE,
            {"content": message},
        )
        visible_events = self.repository.list_events(incarnation.worldline_id)
        response_text = self.provider.respond(snapshot, visible_events, inherited_memories)
        response_event = self.repository.append_event(
            incarnation.worldline_id,
            EventType.MODEL_RESPONSE,
            {
                "content": response_text,
                "provider": self.provider.name,
                "in_reply_to_event_id": user_event.id,
            },
        )
        extraction_input: list[WorldlineEvent] = [user_event, response_event]
        drafts = self.provider.extract_memories(extraction_input)
        memories = self.repository.add_memories(
            incarnation.worldline_id,
            drafts,
            extractor=self.provider.name,
            prompt_version=self.provider.prompt_version,
        )
        self.repository.append_event(
            incarnation.worldline_id,
            EventType.MEMORY_EXTRACTION,
            {
                "memory_ids": [memory.id for memory in memories],
                "source_event_ids": [user_event.id, response_event.id],
                "extractor": self.provider.name,
                "prompt_version": self.provider.prompt_version,
            },
        )
        return response_text, memories

    def list_for_incarnation(self, incarnation_name: str) -> list[Memory]:
        incarnation = self.repository.get_incarnation(incarnation_name)
        return self.repository.list_memories(incarnation.worldline_id)

    def inspect(self, memory_id: str) -> tuple[Memory, list[WorldlineEvent]]:
        memory = self.repository.get_memory(memory_id)
        return memory, [self.repository.get_event(event_id) for event_id in memory.source_event_ids]

    def search(self, incarnation_name: str, query: str) -> list[Memory]:
        terms = {term.casefold() for term in query.split() if term.strip()}
        if not terms:
            return []
        memories = self.list_for_incarnation(incarnation_name)

        def score(memory: Memory) -> tuple[int, float, float]:
            content = memory.content.casefold()
            matches = sum(term in content or term in memory.tags for term in terms)
            return matches, memory.importance, memory.confidence

        return sorted(
            (memory for memory in memories if score(memory)[0] > 0),
            key=score,
            reverse=True,
        )

    def _memory_available(self, memory_id: str) -> bool:
        try:
            memory = self.repository.get_memory(memory_id)
            return memory.status.value != "deleted"
        except RuntimeError:
            return False

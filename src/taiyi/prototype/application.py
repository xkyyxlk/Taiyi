from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from taiyi.application import IdentityService, MemoryService, MergeService
from taiyi.domain import MergeStrategy, ProposalStatus
from taiyi.providers.base import ModelProvider
from taiyi.storage import NotFoundError, Repository

DEMO_PRESET = {
    "title": "未知任务的两种选择",
    "identity_name": "岔路旅人",
    "description": "我重视在不确定条件下做出可解释的选择。",
    "left_name": "探索者",
    "right_name": "守护者",
    "left_message": "remember [决策原则]: 面对未知时，应优先尝试可逆的探索",
    "right_message": "remember [决策原则]: 面对未知时，应优先避免未经验证的风险",
    "rebirth_name": "协调者",
    "synthesis": "在风险可控且行动可逆时主动探索；否则先验证再行动。",
}


def _required_text(payload: dict[str, Any], field: str, *, maximum: int = 4000) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空文本")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{field} 不能超过 {maximum} 个字符")
    return value


def _optional_text(payload: dict[str, Any], field: str, *, maximum: int = 4000) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是文本")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{field} 不能超过 {maximum} 个字符")
    return value or None


def _string_map(value: Any, field: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field} 必须是对象")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ValueError(f"{field} 的键和值必须是文本")
        result[key] = item
    return result


class PrototypeApplication:
    """把现有应用服务投影为本地产品原型需要的状态与操作。"""

    def __init__(self, repository: Repository, provider: ModelProvider) -> None:
        self.repository = repository
        self.identity = IdentityService(repository)
        self.memory = MemoryService(repository, provider)
        self.merge = MergeService(repository)

    def state(self) -> dict[str, Any]:
        try:
            core, current_snapshot, incarnations = self.identity.show()
        except NotFoundError:
            return {
                "stage": "identity",
                "demo": DEMO_PRESET,
                "core": None,
                "current_snapshot": None,
                "incarnations": [],
                "snapshots": [],
                "proposals": [],
                "audit": [],
            }

        all_memories = self.repository.list_all_memories(include_deleted=True)
        memories_by_id = {memory.id: memory for memory in all_memories}

        def memory_payload(memory_id: str) -> dict[str, Any]:
            memory = memories_by_id[memory_id]
            data = memory.model_dump(mode="json")
            data["source_events"] = [
                self.repository.get_event(event_id).model_dump(mode="json")
                for event_id in memory.source_event_ids
            ]
            return data

        incarnation_payloads: list[dict[str, Any]] = []
        for incarnation in incarnations:
            data = incarnation.model_dump(mode="json")
            data["events"] = [
                event.model_dump(mode="json")
                for event in self.repository.list_events(incarnation.worldline_id)
            ]
            data["memories"] = [
                memory_payload(memory.id)
                for memory in self.repository.list_memories(
                    incarnation.worldline_id, include_deleted=True
                )
            ]
            incarnation_payloads.append(data)

        snapshots = self.repository.list_snapshots(core.id)
        snapshot_payloads: list[dict[str, Any]] = []
        for snapshot in snapshots:
            data = snapshot.model_dump(mode="json")
            data["is_current"] = snapshot.id == core.current_snapshot_id
            data["accepted_memories"] = [
                memory_payload(memory_id)
                for memory_id in snapshot.accepted_memory_ids
                if memory_id in memories_by_id
            ]
            snapshot_payloads.append(data)

        proposals = self.repository.list_proposals(core.id)
        proposal_payloads: list[dict[str, Any]] = []
        for proposal in proposals:
            data = proposal.model_dump(mode="json")
            data["is_stale"] = (
                proposal.status in {ProposalStatus.PENDING, ProposalStatus.APPROVED}
                and proposal.base_snapshot_id != core.current_snapshot_id
            )
            data["items"] = []
            for item in proposal.items:
                item_data = item.model_dump(mode="json")
                item_data["memories"] = [
                    memory_payload(memory_id)
                    for memory_id in item.memory_ids
                    if memory_id in memories_by_id
                ]
                data["items"].append(item_data)
            proposal_payloads.append(data)

        return {
            "stage": self._stage(incarnation_payloads, proposals, current_snapshot.id),
            "demo": DEMO_PRESET,
            "core": core.model_dump(mode="json"),
            "current_snapshot": current_snapshot.model_dump(mode="json"),
            "incarnations": incarnation_payloads,
            "snapshots": snapshot_payloads,
            "proposals": proposal_payloads,
            "audit": [
                event.model_dump(mode="json")
                for event in self.repository.list_audit_events(core.id)
            ],
        }

    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        result: BaseModel
        if action == "identity.create":
            name = _required_text(payload, "name", maximum=80)
            description = _optional_text(payload, "description", maximum=1000)
            result = self.identity.initialize(name, description)[0]
        elif action == "incarnation.create":
            name = _required_text(payload, "name", maximum=80)
            snapshot_id = _optional_text(payload, "snapshot_id", maximum=100)
            result = self.identity.fork(name, snapshot_id)
        elif action == "experience.add":
            name = _required_text(payload, "incarnation_name", maximum=80)
            message = _required_text(payload, "message")
            response, memories = self.memory.chat(name, message)
            return {
                "result": {
                    "response": response,
                    "memories": [memory.model_dump(mode="json") for memory in memories],
                },
                "state": self.state(),
            }
        elif action == "comparison.create":
            left = _required_text(payload, "left", maximum=80)
            right = _required_text(payload, "right", maximum=80)
            result = self.merge.propose(left, right)
        elif action == "proposal.review":
            proposal_id = _required_text(payload, "proposal_id", maximum=100)
            approve = payload.get("approve")
            if not isinstance(approve, bool):
                raise ValueError("approve 必须是布尔值")
            raw_resolutions = _string_map(payload.get("resolutions"), "resolutions")
            resolutions = {
                item_id: MergeStrategy(strategy) for item_id, strategy in raw_resolutions.items()
            }
            result = self.merge.review(
                proposal_id,
                approve=approve,
                resolutions=resolutions,
                resolution_content=_string_map(payload.get("content"), "content"),
            )
        elif action == "proposal.apply":
            proposal_id = _required_text(payload, "proposal_id", maximum=100)
            result = self.merge.apply(proposal_id)
        elif action == "identity.rebirth":
            name = _required_text(payload, "name", maximum=80)
            result = self.identity.rebirth(name)
        elif action == "identity.rollback":
            snapshot_id = _required_text(payload, "snapshot_id", maximum=100)
            result = self.identity.rollback(snapshot_id)
        else:
            raise ValueError(f"未知操作：{action}")
        return {"result": result.model_dump(mode="json"), "state": self.state()}

    @staticmethod
    def _stage(
        incarnations: list[dict[str, Any]], proposals: list[Any], current_snapshot_id: str
    ) -> str:
        if len(incarnations) < 2:
            return "incarnations"
        if any(not incarnation["memories"] for incarnation in incarnations[:2]):
            return "experiences"
        if not proposals:
            return "compare"
        latest = proposals[-1]
        if latest.status is ProposalStatus.REJECTED:
            return "compare"
        if latest.status is ProposalStatus.PENDING:
            return "review"
        if latest.status is ProposalStatus.APPROVED:
            return "apply"
        if latest.status is ProposalStatus.APPLIED:
            reborn_from_current = any(
                incarnation["base_snapshot_id"] == current_snapshot_id
                for incarnation in incarnations
            )
            if not reborn_from_current:
                return "rebirth"
        return "complete"

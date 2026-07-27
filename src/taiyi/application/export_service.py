from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from taiyi.storage import Repository


class ExportService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def export(self, output_path: Path) -> list[Path]:
        if output_path.suffix.lower() == ".jsonl":
            self._write_jsonl(output_path)
            return [output_path]
        if output_path.suffix.lower() in {".md", ".markdown"}:
            self._write_markdown(output_path)
            return [output_path]
        output_path.mkdir(parents=True, exist_ok=True)
        jsonl = output_path / "taiyi-export.jsonl"
        markdown = output_path / "taiyi-export.md"
        self._write_jsonl(jsonl)
        self._write_markdown(markdown)
        return [jsonl, markdown]

    def _records(self) -> list[dict[str, Any]]:
        core = self.repository.get_core()
        incarnations = self.repository.list_incarnations(core.id)
        records: list[dict[str, Any]] = [{"kind": "core", "data": core.model_dump(mode="json")}]
        records.extend(
            {"kind": "snapshot", "data": item.model_dump(mode="json")}
            for item in self.repository.list_snapshots(core.id)
        )
        records.extend(
            {"kind": "incarnation", "data": item.model_dump(mode="json")} for item in incarnations
        )
        for incarnation in incarnations:
            records.extend(
                {"kind": "event", "data": event.model_dump(mode="json")}
                for event in self.repository.list_events(incarnation.worldline_id)
            )
        records.extend(
            {"kind": "memory", "data": memory.model_dump(mode="json")}
            for memory in self.repository.list_all_memories(include_deleted=True)
        )
        records.extend(
            {"kind": "merge_proposal", "data": proposal.model_dump(mode="json")}
            for proposal in self.repository.list_proposals(core.id)
        )
        records.extend(
            {"kind": "audit", "data": audit.model_dump(mode="json")}
            for audit in self.repository.list_audit_events(core.id)
        )
        return records

    def _write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for record in self._records():
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _write_markdown(self, path: Path) -> None:
        core = self.repository.get_core()
        current = self.repository.get_snapshot(core.current_snapshot_id)
        incarnations = self.repository.list_incarnations(core.id)
        lines = [
            f"# Taiyi export: {core.name}",
            "",
            f"- Core ID: `{core.id}`",
            f"- Current snapshot: `{core.current_snapshot_id}`",
            f"- Created: {core.created_at.isoformat()}",
            "",
            "## Current identity",
            "",
            current.self_description,
            "",
            "## Snapshots",
            "",
        ]
        for snapshot in self.repository.list_snapshots(core.id):
            lines.append(
                f"- `{snapshot.id}` parents={list(snapshot.parent_snapshot_ids)} "
                f"memories={len(snapshot.accepted_memory_ids)}"
            )
        lines.extend(["", "## Worldlines", ""])
        for incarnation in incarnations:
            lines.append(f"### {incarnation.name}")
            lines.append("")
            for event in self.repository.list_events(incarnation.worldline_id):
                payload = (
                    "[redacted]"
                    if event.payload is None
                    else json.dumps(event.payload, ensure_ascii=False)
                )
                lines.append(f"- {event.sequence_number}. `{event.event_type.value}` {payload}")
            lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

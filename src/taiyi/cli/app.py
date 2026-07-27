from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from taiyi.application import IdentityService, MemoryService, MergeService, WorldlineService
from taiyi.application.export_service import ExportService
from taiyi.config import Settings
from taiyi.domain import MergeStrategy
from taiyi.evaluation import SCENARIOS, evaluate, run_scenario
from taiyi.providers import MockProvider, create_provider
from taiyi.storage import Database, Repository, TaiyiError

app = typer.Typer(
    name="taiyi",
    help="One Identity, Many Incarnations - AI identity version control.",
    no_args_is_help=True,
)
core_app = typer.Typer(help="Inspect the identity core.")
worldline_app = typer.Typer(help="Inspect isolated worldlines.")
memory_app = typer.Typer(help="Inspect provenance-bound memories.")
merge_app = typer.Typer(help="Compare and manually merge worldlines.")
event_app = typer.Typer(help="Manage event payloads.")
experiment_app = typer.Typer(help="Run reproducible standard experiments.")
app.add_typer(core_app, name="core")
app.add_typer(worldline_app, name="worldline")
app.add_typer(memory_app, name="memory")
app.add_typer(merge_app, name="merge")
app.add_typer(event_app, name="event")
app.add_typer(experiment_app, name="experiment")


@dataclass
class Runtime:
    settings: Settings
    repository: Repository


@app.callback()
def main(
    ctx: typer.Context,
    data_dir: Path | None = typer.Option(
        None,
        "--data-dir",
        envvar="TAIYI_DATA_DIR",
        help="Directory containing the local Taiyi database.",
    ),
) -> None:
    settings = Settings.load(data_dir)
    database = Database(settings.database_path)
    database.create_schema()
    ctx.call_on_close(database.engine.dispose)
    ctx.obj = Runtime(settings=settings, repository=Repository(database))


@contextmanager
def handled() -> Iterator[None]:
    try:
        yield
    except (TaiyiError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _parse_pairs(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, content = value.partition("=")
        if not separator or not key or not content:
            raise ValueError(f"expected ITEM=VALUE, got: {value}")
        result[key] = content
    return result


@app.command("init")
def initialize(
    ctx: typer.Context,
    identity_name: str = typer.Argument(..., help="Name of the persistent identity."),
    description: str | None = typer.Option(None, "--description", "-d"),
) -> None:
    with handled():
        core, snapshot = IdentityService(ctx.obj.repository).initialize(identity_name, description)
        _json({"core": core.model_dump(mode="json"), "snapshot": snapshot.model_dump(mode="json")})


@core_app.command("show")
def core_show(ctx: typer.Context) -> None:
    with handled():
        core, snapshot, incarnations = IdentityService(ctx.obj.repository).show()
        _json(
            {
                "core": core.model_dump(mode="json"),
                "current_snapshot": snapshot.model_dump(mode="json"),
                "incarnations": [item.model_dump(mode="json") for item in incarnations],
            }
        )


@app.command("fork")
def fork(
    ctx: typer.Context,
    incarnation_name: str,
    snapshot_id: str | None = typer.Option(None, "--snapshot"),
) -> None:
    with handled():
        _json(IdentityService(ctx.obj.repository).fork(incarnation_name, snapshot_id))


@app.command("rebirth")
def rebirth(ctx: typer.Context, incarnation_name: str) -> None:
    with handled():
        _json(IdentityService(ctx.obj.repository).rebirth(incarnation_name))


@app.command("chat")
def chat(
    ctx: typer.Context,
    incarnation_name: str,
    message: str | None = typer.Argument(None),
) -> None:
    with handled():
        service = MemoryService(ctx.obj.repository, create_provider(ctx.obj.settings))
        if message is not None:
            response, memories = service.chat(incarnation_name, message)
            typer.echo(response)
            typer.echo(f"Extracted memories: {len(memories)}")
            return
        typer.echo("Interactive chat; enter /exit to stop.")
        while True:
            prompt = typer.prompt("you")
            if prompt.strip().lower() in {"/exit", "/quit"}:
                break
            response, memories = service.chat(incarnation_name, prompt)
            typer.echo(f"taiyi> {response}")
            typer.echo(f"[{len(memories)} memories extracted]")


@worldline_app.command("show")
def worldline_show(ctx: typer.Context, incarnation_name: str) -> None:
    with handled():
        events = WorldlineService(ctx.obj.repository).events_for_incarnation(incarnation_name)
        _json([event.model_dump(mode="json") for event in events])


@memory_app.command("list")
def memory_list(ctx: typer.Context, incarnation_name: str) -> None:
    with handled():
        memories = MemoryService(ctx.obj.repository, MockProvider()).list_for_incarnation(
            incarnation_name
        )
        _json([memory.model_dump(mode="json") for memory in memories])


@memory_app.command("inspect")
def memory_inspect(ctx: typer.Context, memory_id: str) -> None:
    with handled():
        memory, events = MemoryService(ctx.obj.repository, MockProvider()).inspect(memory_id)
        _json(
            {
                "memory": memory.model_dump(mode="json"),
                "source_events": [event.model_dump(mode="json") for event in events],
            }
        )


@memory_app.command("search")
def memory_search(ctx: typer.Context, incarnation_name: str, query: str) -> None:
    with handled():
        memories = MemoryService(ctx.obj.repository, MockProvider()).search(incarnation_name, query)
        _json([memory.model_dump(mode="json") for memory in memories])


@app.command("diff")
def diff(ctx: typer.Context, incarnation_a: str, incarnation_b: str) -> None:
    with handled():
        items = MergeService(ctx.obj.repository).diff(incarnation_a, incarnation_b)
        _json([item.model_dump(mode="json") for item in items])


@merge_app.command("propose")
def merge_propose(ctx: typer.Context, incarnation_a: str, incarnation_b: str) -> None:
    with handled():
        _json(MergeService(ctx.obj.repository).propose(incarnation_a, incarnation_b))


@merge_app.command("review")
def merge_review(
    ctx: typer.Context,
    proposal_id: str,
    approve: bool = typer.Option(False, "--approve", help="Approve after applying overrides."),
    reject: bool = typer.Option(False, "--reject", help="Reject the whole proposal."),
    resolution: list[str] | None = typer.Option(
        None, "--resolution", help="Override as ITEM_ID=STRATEGY; repeatable."
    ),
    content: list[str] | None = typer.Option(
        None, "--content", help="Selection ID or synthesis text as ITEM_ID=VALUE; repeatable."
    ),
) -> None:
    with handled():
        if approve and reject:
            raise ValueError("choose either --approve or --reject")
        if not approve and not reject:
            approve = typer.confirm("Approve this proposal using the suggested strategies?")
            reject = not approve
        raw_resolutions = _parse_pairs(resolution or [])
        resolutions = {key: MergeStrategy(value) for key, value in raw_resolutions.items()}
        reviewed = MergeService(ctx.obj.repository).review(
            proposal_id,
            approve=approve and not reject,
            resolutions=resolutions,
            resolution_content=_parse_pairs(content or []),
        )
        _json(reviewed)


@merge_app.command("apply")
def merge_apply(ctx: typer.Context, proposal_id: str) -> None:
    with handled():
        _json(MergeService(ctx.obj.repository).apply(proposal_id))


@app.command("history")
def history(ctx: typer.Context) -> None:
    with handled():
        repository: Repository = ctx.obj.repository
        core = repository.get_core()
        _json(
            {
                "current_snapshot_id": core.current_snapshot_id,
                "snapshots": [
                    snapshot.model_dump(mode="json")
                    for snapshot in repository.list_snapshots(core.id)
                ],
                "audit": [
                    event.model_dump(mode="json") for event in repository.list_audit_events(core.id)
                ],
            }
        )


@app.command("rollback")
def rollback(ctx: typer.Context, snapshot_id: str) -> None:
    with handled():
        _json(IdentityService(ctx.obj.repository).rollback(snapshot_id))


@event_app.command("redact")
def event_redact(
    ctx: typer.Context,
    event_id: str,
    yes: bool = typer.Option(False, "--yes", help="Skip the destructive-action confirmation."),
) -> None:
    with handled():
        if not yes and not typer.confirm(
            "Permanently erase this event payload and all memories derived from it?"
        ):
            raise typer.Abort()
        affected = WorldlineService(ctx.obj.repository).redact_event(event_id)
        _json({"event_id": event_id, "derived_memories_deleted": affected})


@app.command("export")
def export(ctx: typer.Context, output_path: Path) -> None:
    with handled():
        paths = ExportService(ctx.obj.repository).export(output_path.resolve())
        _json({"files": [str(path) for path in paths]})


@app.command("evaluate")
def evaluate_command(ctx: typer.Context) -> None:
    with handled():
        _json(evaluate(ctx.obj.repository))


@experiment_app.command("run")
def experiment_run(
    name: str = typer.Argument(..., help=f"One of: {', '.join(SCENARIOS)}, all"),
    output_dir: Path = typer.Option(Path("experiments"), "--output-dir"),
) -> None:
    with handled():
        names = SCENARIOS if name == "all" else (name,)
        results = [run_scenario(scenario, output_dir.resolve()) for scenario in names]
        _json(results)


if __name__ == "__main__":
    app()

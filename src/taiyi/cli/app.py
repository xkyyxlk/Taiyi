from __future__ import annotations

import json
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from taiyi.adapters import (
    ADAPTER_VERSION,
    SUPPORTED_LANGGRAPH_VERSION,
    SUPPORTED_LANGSMITH_VERSION,
    adapt_langgraph_json,
)
from taiyi.analysis import (
    BASELINE_EVENT_COUNT,
    BASELINE_MEMORY_CHANGE_COUNT,
    COMMIT_MALFORMED_COUNT,
    COMMIT_SCENARIO_COUNT,
    DEFAULT_MALFORMED_SEED,
    DEFAULT_MILESTONE_SEED,
    DEFAULT_SCENARIO_SEED,
    MILESTONE_SCENARIO_COUNT,
    PerformanceBudget,
    Policy,
    ReportFormat,
    analyze_jsonl,
    check_performance_budget,
    generate_malformed_scenarios,
    generate_milestone_scenarios,
    generate_scenarios,
    parse_jsonl,
    render_report,
    run_performance_sample,
    verify_generated_scenarios,
    verify_malformed_scenarios,
    verify_milestone_scenarios,
)
from taiyi.application import IdentityService, MemoryService, MergeService, WorldlineService
from taiyi.application.export_service import ExportService
from taiyi.config import Settings
from taiyi.domain import MergeStrategy
from taiyi.evaluation import SCENARIOS, evaluate, run_scenario
from taiyi.prototype import create_prototype_server
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
analysis_app = typer.Typer(help="校验并分析 Agent 长期记忆记录。")
app.add_typer(core_app, name="core")
app.add_typer(worldline_app, name="worldline")
app.add_typer(memory_app, name="memory")
app.add_typer(merge_app, name="merge")
app.add_typer(event_app, name="event")
app.add_typer(experiment_app, name="experiment")
app.add_typer(analysis_app, name="analyze")


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
    if ctx.invoked_subcommand == "analyze":
        return
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


def _read_utf8(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"无法读取{label}：{path}") from exc
    except UnicodeError as exc:
        raise ValueError(f"{label}必须使用 UTF-8 编码：{path}") from exc


def _load_policy(path: Path | None) -> Policy:
    if path is None:
        return Policy()
    try:
        return Policy.model_validate_json(_read_utf8(path, "策略文件"))
    except ValidationError as exc:
        raise ValueError(f"策略文件不符合版本化策略协议：{exc}") from exc


def _load_performance_budget(path: Path) -> PerformanceBudget:
    try:
        return PerformanceBudget.model_validate_json(_read_utf8(path, "性能预算文件"))
    except ValidationError as exc:
        raise ValueError(f"性能预算文件不符合版本化预算协议：{exc}") from exc


def _write_utf8(path: Path, content: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"无法写入输出文件：{resolved}") from exc
    return resolved


@analysis_app.command("validate")
def analysis_validate(input_path: Path = typer.Argument(..., help="待校验的 JSONL 文件。")) -> None:
    with handled():
        parsed = parse_jsonl(_read_utf8(input_path, "协议文件"))
        _json(
            {
                "valid": True,
                "protocol_version": parsed.manifest.protocol_version,
                "project_id": parsed.manifest.project_id,
                "run_id": parsed.manifest.run_id,
                "record_count": len(parsed.records),
            }
        )


@analysis_app.command("check")
def analysis_check(
    input_path: Path = typer.Argument(..., help="待分析的 JSONL 文件。"),
    policy_path: Path | None = typer.Option(
        None,
        "--policy",
        help="版本化 JSON 策略文件。",
    ),
    report_format: ReportFormat = typer.Option(
        ReportFormat.JSON,
        "--format",
        help="报告格式：json、markdown 或 html。",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        help="报告输出路径；省略时写入标准输出。",
    ),
) -> None:
    with handled():
        reproduction_command = ["taiyi", "analyze", "check", str(input_path.resolve())]
        if policy_path is not None:
            reproduction_command.extend(("--policy", str(policy_path.resolve())))
        if report_format is not ReportFormat.JSON:
            reproduction_command.extend(("--format", report_format.value))
        if output_path is not None:
            reproduction_command.extend(("--output", str(output_path.resolve())))
        report = analyze_jsonl(
            _read_utf8(input_path, "协议文件"),
            policy=_load_policy(policy_path),
            reproduction_command=tuple(reproduction_command),
        )
        rendered = render_report(report, report_format)
        if output_path is None:
            typer.echo(rendered, nl=False)
        else:
            typer.echo(_write_utf8(output_path, rendered))
        if report.exit_code:
            raise typer.Exit(report.exit_code)


@analysis_app.command("simulate")
def analysis_simulate(
    output_dir: Path = typer.Option(
        Path("analysis-scenarios"),
        "--output-dir",
        help="生成案例和清单的输出目录。",
    ),
    seed: int = typer.Option(
        DEFAULT_SCENARIO_SEED,
        "--seed",
        help="固定种子。",
    ),
    case_count: int = typer.Option(
        COMMIT_SCENARIO_COUNT,
        "--count",
        help="组合案例数量。",
    ),
) -> None:
    with handled():
        scenarios = generate_scenarios(seed, case_count)
        summary = verify_generated_scenarios(scenarios)
        resolved_output = output_dir.resolve()
        cases: list[dict[str, object]] = []
        for scenario in scenarios:
            file_name = f"case-{scenario.case_index:06d}.jsonl"
            _write_utf8(resolved_output / file_name, scenario.jsonl)
            cases.append(
                {
                    "case_id": scenario.case_id,
                    "file": file_name,
                    "input_sha256": scenario.input_sha256,
                    "dimensions": scenario.dimensions.model_dump(mode="json"),
                    "expected": scenario.expected.model_dump(mode="json"),
                }
            )
        manifest = {
            **summary.model_dump(mode="json"),
            "cases": cases,
        }
        manifest_path = _write_utf8(
            resolved_output / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        _json(
            {
                **summary.model_dump(mode="json"),
                "output_dir": str(resolved_output),
                "manifest": str(manifest_path),
            }
        )
        if summary.mismatches:
            raise typer.Exit(1)


@analysis_app.command("simulate-malformed")
def analysis_simulate_malformed(
    output_dir: Path = typer.Option(
        Path("analysis-malformed-scenarios"),
        "--output-dir",
        help="生成畸形案例和稳定标准答案清单的输出目录。",
    ),
    seed: int = typer.Option(
        DEFAULT_MALFORMED_SEED,
        "--seed",
        help="固定种子。",
    ),
    case_count: int = typer.Option(
        COMMIT_MALFORMED_COUNT,
        "--count",
        help="畸形案例数量。",
    ),
) -> None:
    with handled():
        scenarios = generate_malformed_scenarios(seed, case_count)
        summary = verify_malformed_scenarios(scenarios)
        resolved_output = output_dir.resolve()
        cases: list[dict[str, object]] = []
        for scenario in scenarios:
            file_name = f"case-{scenario.case_index:06d}.jsonl"
            _write_utf8(resolved_output / file_name, scenario.jsonl)
            cases.append(
                {
                    "case_id": scenario.case_id,
                    "file": file_name,
                    "kind": scenario.kind.value,
                    "input_sha256": scenario.input_sha256,
                    "expected": scenario.expected.model_dump(mode="json"),
                }
            )
        manifest = {
            **summary.model_dump(mode="json"),
            "cases": cases,
        }
        manifest_path = _write_utf8(
            resolved_output / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        _json(
            {
                **summary.model_dump(mode="json"),
                "output_dir": str(resolved_output),
                "manifest": str(manifest_path),
            }
        )
        if summary.mismatches:
            raise typer.Exit(1)


@analysis_app.command("simulate-milestone")
def analysis_simulate_milestone(
    seed: int = typer.Option(
        DEFAULT_MILESTONE_SEED,
        "--seed",
        help="里程碑固定种子。",
    ),
    case_count: int = typer.Option(
        MILESTONE_SCENARIO_COUNT,
        "--count",
        help="里程碑组合案例数量。",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        help="里程碑验证摘要 JSON 输出路径；省略时写入标准输出。",
    ),
) -> None:
    with handled():
        scenarios = generate_milestone_scenarios(seed, case_count)
        summary = verify_milestone_scenarios(scenarios)
        rendered = json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        if output_path is None:
            typer.echo(rendered, nl=False)
        else:
            resolved_output = _write_utf8(output_path, rendered)
            _json({**summary.model_dump(mode="json"), "output": str(resolved_output)})
        if summary.mismatches:
            raise typer.Exit(1)


@analysis_app.command("adapt-langgraph")
def analysis_adapt_langgraph(
    input_path: Path = typer.Argument(..., help="离线 LangGraph/LangSmith 1.0 契约 JSON。"),
    output_path: Path = typer.Option(
        ...,
        "--output",
        help="中性分析协议 JSONL 输出路径。",
    ),
) -> None:
    with handled():
        output = adapt_langgraph_json(_read_utf8(input_path, "适配器输入"))
        parsed = parse_jsonl(output)
        resolved_output = _write_utf8(output_path, output)
        _json(
            {
                "adapter_version": ADAPTER_VERSION,
                "langgraph_version": SUPPORTED_LANGGRAPH_VERSION,
                "langsmith_version": SUPPORTED_LANGSMITH_VERSION,
                "protocol_version": parsed.manifest.protocol_version,
                "record_count": len(parsed.records),
                "output": str(resolved_output),
            }
        )


@analysis_app.command("benchmark")
def analysis_benchmark(
    event_count: int = typer.Option(
        BASELINE_EVENT_COUNT,
        "--event-count",
        help="规模输入中的事件数量。",
    ),
    memory_change_count: int = typer.Option(
        BASELINE_MEMORY_CHANGE_COUNT,
        "--memory-change-count",
        help="规模输入中的记忆变化数量。",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        help="性能样本 JSON 输出路径；省略时写入标准输出。",
    ),
    budget_path: Path | None = typer.Option(
        None,
        "--budget",
        help="版本化性能预算 JSON；违反预算时返回退出码二。",
    ),
) -> None:
    with handled():
        sample = run_performance_sample(event_count, memory_change_count)
        result = sample.model_dump(mode="json")
        budget_check = None
        if budget_path is not None:
            budget_check = check_performance_budget(
                sample,
                _load_performance_budget(budget_path),
            )
            result["budget_check"] = budget_check.model_dump(mode="json")
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if output_path is None:
            typer.echo(rendered, nl=False)
        else:
            resolved_output = _write_utf8(output_path, rendered)
            _json({**result, "output": str(resolved_output)})
        if budget_check is not None and not budget_check.passed:
            raise typer.Exit(2)


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


@app.command("prototype")
def prototype(
    ctx: typer.Context,
    port: int = typer.Option(8765, "--port", help="本地产品原型监听端口。"),
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help="启动后是否使用默认浏览器打开产品原型。",
    ),
) -> None:
    with handled():
        server = create_prototype_server(
            ctx.obj.repository,
            create_provider(ctx.obj.settings),
            port,
        )
        actual_port = server.server_address[1]
        url = f"http://127.0.0.1:{actual_port}"
        typer.echo(f"太一产品原型已在本地启动：{url}")
        typer.echo("按 Ctrl+C 停止。数据只写入当前 --data-dir。")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            typer.echo("\n产品原型已停止。")
        finally:
            server.server_close()


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

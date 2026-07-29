from __future__ import annotations

import json
import platform
import time
import tracemalloc
from hashlib import sha256
from typing import Literal

from pydantic import Field, model_validator

from taiyi import __version__
from taiyi.analysis.engine import analyze_jsonl
from taiyi.analysis.models import ProtocolModel, Sha256Digest
from taiyi.analysis.renderers import render_json

PERFORMANCE_GENERATOR_VERSION = "1.0"
BASELINE_EVENT_COUNT = 100_000
BASELINE_MEMORY_CHANGE_COUNT = 10_000


class ScaleInputMetadata(ProtocolModel):
    generator_version: Literal["1.0"] = "1.0"
    protocol_version: Literal["1.0"] = "1.0"
    event_count: int = Field(ge=1)
    memory_change_count: int = Field(ge=1)
    record_count: int = Field(ge=1)
    input_bytes: int = Field(ge=1)
    input_sha256: str


class PerformanceEnvironment(ProtocolModel):
    python_version: str
    implementation: str
    operating_system: str
    machine: str
    processor: str


class PerformanceSample(ProtocolModel):
    benchmark_version: Literal["1.0"] = "1.0"
    tool_version: str = __version__
    input: ScaleInputMetadata
    environment: PerformanceEnvironment
    generation_seconds: float = Field(ge=0)
    analysis_seconds: float = Field(ge=0)
    render_seconds: float = Field(ge=0)
    total_seconds: float = Field(ge=0)
    peak_traced_memory_bytes: int = Field(ge=1)
    report_bytes: int = Field(ge=1)
    actual_content_modified: int = Field(ge=0)
    actual_change_count: int = Field(ge=0)
    actual_finding_count: int = Field(ge=0)
    exit_code: Literal[0, 2]


class PerformanceBudget(ProtocolModel):
    version: Literal["1.0"] = "1.0"
    event_count: int = Field(ge=1)
    memory_change_count: int = Field(ge=1)
    expected_input_sha256: Sha256Digest
    reference_python_version: str
    reference_operating_system: str
    reference_machine: str
    reference_processor: str
    baseline_total_seconds: float = Field(gt=0)
    baseline_peak_traced_memory_bytes: int = Field(ge=1)
    allowed_regression_percent: float = Field(ge=0, le=100)
    max_total_seconds: float = Field(gt=0)
    max_peak_traced_memory_bytes: int = Field(ge=1)
    max_report_bytes: int = Field(ge=1)
    expected_change_count: int = Field(ge=0)
    max_finding_count: int = Field(ge=0)
    expected_exit_code: Literal[0, 2]

    @model_validator(mode="after")
    def ceilings_match_declared_regression(self) -> PerformanceBudget:
        factor = 1 + self.allowed_regression_percent / 100
        if self.max_total_seconds > self.baseline_total_seconds * factor + 0.000001:
            raise ValueError("总耗时上限超过声明的回退比例")
        if (
            self.max_peak_traced_memory_bytes
            > int(self.baseline_peak_traced_memory_bytes * factor) + 1
        ):
            raise ValueError("峰值内存上限超过声明的回退比例")
        return self


class PerformanceBudgetCheck(ProtocolModel):
    budget_version: Literal["1.0"] = "1.0"
    passed: bool
    violations: tuple[str, ...]


def _line(record: dict[str, object]) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def generate_scale_jsonl(
    event_count: int, memory_change_count: int
) -> tuple[str, ScaleInputMetadata]:
    if event_count < 1:
        raise ValueError("event_count 必须大于零")
    if memory_change_count < 1:
        raise ValueError("memory_change_count 必须大于零")
    if memory_change_count > event_count:
        raise ValueError("memory_change_count 不得大于 event_count")

    sequence_number = 1
    lines = [
        _line(
            {
                "protocol_version": "1.0",
                "record_type": "manifest",
                "sequence_number": sequence_number,
                "project_id": "performance_project",
                "run_id": f"performance_{event_count}_{memory_change_count}",
                "baseline_run_id": "performance_baseline",
                "captured_at": "2026-07-29T06:00:00Z",
                "producer": {"name": "taiyi-performance-generator", "version": "1.0"},
                "model_version": "model-a",
                "prompt_version": "prompt-v1",
                "tool_versions": {},
                "writer_version": "writer-v1",
            }
        )
    ]
    sequence_number += 1
    lines.append(
        _line(
            {
                "protocol_version": "1.0",
                "record_type": "snapshot",
                "sequence_number": sequence_number,
                "snapshot_id": "snapshot_before",
                "snapshot_role": "before",
                "captured_at": "2026-07-29T06:00:00Z",
            }
        )
    )
    for index in range(1, memory_change_count + 1):
        sequence_number += 1
        lines.append(_line(_scale_memory(index, sequence_number, "before")))
    for index in range(1, event_count + 1):
        sequence_number += 1
        lines.append(_line(_scale_event(index, sequence_number)))
    sequence_number += 1
    lines.append(
        _line(
            {
                "protocol_version": "1.0",
                "record_type": "snapshot",
                "sequence_number": sequence_number,
                "snapshot_id": "snapshot_after",
                "snapshot_role": "after",
                "captured_at": "2026-07-29T06:02:00Z",
            }
        )
    )
    for index in range(1, memory_change_count + 1):
        sequence_number += 1
        lines.append(_line(_scale_memory(index, sequence_number, "after")))

    jsonl = "\n".join(lines) + "\n"
    encoded = jsonl.encode()
    return jsonl, ScaleInputMetadata(
        event_count=event_count,
        memory_change_count=memory_change_count,
        record_count=len(lines),
        input_bytes=len(encoded),
        input_sha256=sha256(encoded).hexdigest(),
    )


def _scale_event(index: int, sequence_number: int) -> dict[str, object]:
    return {
        "protocol_version": "1.0",
        "record_type": "event",
        "sequence_number": sequence_number,
        "event_id": f"event_{index:06d}",
        "event_type": "user_input",
        "scope": {"kind": "user", "id": "user_performance"},
        "occurred_at": "2026-07-29T06:01:00Z",
        "content_hash": sha256(f"event:{index}".encode()).hexdigest(),
        "parent_event_ids": [],
    }


def _scale_memory(index: int, sequence_number: int, role: str) -> dict[str, object]:
    return {
        "protocol_version": "1.0",
        "record_type": "memory",
        "sequence_number": sequence_number,
        "snapshot_id": f"snapshot_{role}",
        "memory_id": f"memory_{index:06d}",
        "scope": {"kind": "user", "id": "user_performance"},
        "memory_type": "semantic",
        "content_hash": sha256(f"{role}:{index}".encode()).hexdigest(),
        "source_event_ids": [f"event_{index:06d}"],
        "created_at": "2026-07-29T05:00:00Z",
        "updated_at": "2026-07-29T05:00:00Z",
        "writer_version": "writer-v1",
        "memory_version": "1",
    }


def performance_environment() -> PerformanceEnvironment:
    return PerformanceEnvironment(
        python_version=platform.python_version(),
        implementation=platform.python_implementation(),
        operating_system=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor(),
    )


def run_performance_sample(event_count: int, memory_change_count: int) -> PerformanceSample:
    tracemalloc.start()
    started = time.perf_counter()
    jsonl, metadata = generate_scale_jsonl(event_count, memory_change_count)
    generated = time.perf_counter()
    report = analyze_jsonl(jsonl)
    analyzed = time.perf_counter()
    rendered = render_json(report)
    finished = time.perf_counter()
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return PerformanceSample(
        input=metadata,
        environment=performance_environment(),
        generation_seconds=round(generated - started, 6),
        analysis_seconds=round(analyzed - generated, 6),
        render_seconds=round(finished - analyzed, 6),
        total_seconds=round(finished - started, 6),
        peak_traced_memory_bytes=peak_memory,
        report_bytes=len(rendered.encode()),
        actual_content_modified=report.summary.content_modified,
        actual_change_count=len(report.changes),
        actual_finding_count=len(report.findings),
        exit_code=report.exit_code,
    )


def check_performance_budget(
    sample: PerformanceSample, budget: PerformanceBudget
) -> PerformanceBudgetCheck:
    violations: list[str] = []
    expected_environment = (
        budget.reference_python_version,
        budget.reference_operating_system,
        budget.reference_machine,
        budget.reference_processor,
    )
    actual_environment = (
        sample.environment.python_version,
        sample.environment.operating_system,
        sample.environment.machine,
        sample.environment.processor,
    )
    if actual_environment != expected_environment:
        violations.append("参考环境不匹配")
    if sample.input.event_count != budget.event_count:
        violations.append("事件数量不匹配")
    if sample.input.memory_change_count != budget.memory_change_count:
        violations.append("记忆变化数量不匹配")
    if sample.input.input_sha256 != budget.expected_input_sha256:
        violations.append("固定输入哈希不匹配")
    if sample.total_seconds > budget.max_total_seconds:
        violations.append("总耗时超过预算")
    if sample.peak_traced_memory_bytes > budget.max_peak_traced_memory_bytes:
        violations.append("峰值追踪内存超过预算")
    if sample.report_bytes > budget.max_report_bytes:
        violations.append("报告大小超过预算")
    if sample.actual_change_count != budget.expected_change_count:
        violations.append("实际变化数量不匹配")
    if sample.actual_finding_count > budget.max_finding_count:
        violations.append("治理发现数量超过预算")
    if sample.exit_code != budget.expected_exit_code:
        violations.append("分析退出码不匹配")
    return PerformanceBudgetCheck(passed=not violations, violations=tuple(violations))

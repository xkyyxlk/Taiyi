# LangGraph 与 LangSmith 参考适配器 v1

- 适配器契约版本：`1.0`
- 太一协议版本：`1.0`
- 对应工作项：`TY-202607281622`
- 更新时间：2026-07-29

## 目标与边界

本适配器把本地导出的 LangGraph Store 前后快照、LangSmith 运行记录和显式记忆写入旁车记录
转换为太一中性 JSONL 协议。它只读取用户指定的 JSON 文件并写入用户指定的 JSONL 文件，
不连接 LangSmith 服务、不导入 LangGraph 或 LangSmith SDK，也不读取或修改外部记忆库。

LangGraph 官方将检查点用于线程内状态，将 Store 用于跨线程长期记忆；Store 项目包含
`namespace`、`key`、`value`、`created_at` 和 `updated_at`。LangSmith 运行记录提供运行 ID、
父运行、类型、开始时间、输入和输出。参考资料见
[LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)和
[LangSmith Run 数据格式](https://docs.langchain.com/langsmith/run-data-format)。

框架原生字段不能可靠证明记忆的稳定业务 ID、作用域、类型和来源，因此这些字段不能由
适配器按文本、时间或命名空间猜测，必须通过显式写入旁车记录提供。

## 固定参考版本

截至 2026-07-29，离线金夹具精确锁定：

| 组件 | 参考版本 | 兼容行为 |
|---|---|---|
| 适配器契约 | `1.0` | 只接受 `format_version: "1.0"` |
| LangGraph | `1.2.10` | 只接受精确版本 |
| LangSmith Python SDK | `0.10.11` | 只接受精确版本 |
| 太一 JSONL | `1.0` | 转换后再次经过协议读取器校验 |

版本依据见 [LangGraph 1.2.10](https://pypi.org/project/langgraph/1.2.10/)和
[LangSmith 0.10.11](https://pypi.org/project/langsmith/0.10.11/)。精确锁定表示“已经用离线夹具
验证”，不表示相邻版本一定不兼容。支持新版本前必须增加对应夹具并更新本表，不能静默接受。

太一运行时依赖不包含这两个软件包。用户可以在自己的 Agent 环境提取数据，再把离线契约
文件交给太一转换。

## 离线输入契约

顶层 JSON 对象包含以下字段：

| 字段 | 含义 |
|---|---|
| `format_version` | 当前固定为 `1.0` |
| `frameworks` | 精确的 `langgraph` 和 `langsmith` 版本 |
| `manifest` | 项目、运行、模型、提示词、工具和默认写入器版本 |
| `before` | 运行前 checkpoint 及 Store 项目 |
| `runs` | 当前文件引用到的 LangSmith 运行记录 |
| `writes` | 显式记忆写入旁车记录 |
| `after` | 运行后 checkpoint 及 Store 项目 |

每个 Store 项目保留框架原生 `namespace`、`key`、`value`、创建时间和更新时间，并增加
`write_id` 以关联旁车记录。相同快照中的 `namespace` 与 `key` 组合必须唯一。

每个规范化 LangSmith 运行包含：

- `run_id` 和可选 `parent_run_id`；
- `run_type`，支持 `chain`、`llm`、`tool`、`retriever`、`embedding`、`prompt` 和 `parser`；
- 显式 `scope`；
- `started_at`、`inputs` 和 `outputs`。

`inputs`、`outputs` 和 Store `value` 必须是有限 JSON 数据。适配器按 UTF-8、键排序和紧凑
分隔符生成规范 JSON 后计算 SHA-256，避免依赖 Python 对象表示。

每条显式写入记录包含：

- 与 Store 项目匹配的 `namespace`、`key` 和 `value_sha256`；
- 唯一 `write_id` 和跨快照稳定的 `memory_id`；
- 显式 `scope`、`memory_type`、`writer_version` 和可选 `memory_version`；
- `occurred_at` 和零个或多个 `source_run_ids`。

所有 Store 项目必须关联写入记录，所有写入记录也必须被至少一个前后快照项目引用。空
`source_run_ids` 不会被猜测补全；转换后的记忆来源数组保持为空，并由 `TY-PROV-001` 报告。

完整离线输入与标准输出见
[参考输入](../../tests/fixtures/adapters/langgraph-langsmith/v1/run-bundle.json)和
[标准 JSONL](../../tests/fixtures/adapters/langgraph-langsmith/v1/expected.jsonl)。

## 映射规则

| 输入 | 太一协议记录 | 规则 |
|---|---|---|
| `manifest` | `manifest` | 生产器固定为适配器 `1.0`，框架版本写入 `tool_versions` |
| 前后 checkpoint | `snapshot` | `checkpoint_id` 作为快照稳定 ID |
| Store 项目 | `memory` | 值只写 SHA-256，不复制原始 JSON |
| `llm` 运行 | `model_output` 事件 | 输入与输出组合只写 SHA-256 |
| `tool` 运行 | `tool_result` 事件 | 输入与输出组合只写 SHA-256 |
| `retriever` 运行 | `document_read` 事件 | 输入与输出组合只写 SHA-256 |
| 其他已支持运行类型 | `system` 事件 | 不猜测更细事件语义 |
| 显式写入 | `memory_write` 事件 | `source_run_ids` 同时作为父事件 |

记忆记录的 `source_event_ids` 直接取显式写入的 `source_run_ids`，不使用 `write_id` 掩盖空
来源。LangSmith `parent_run_id` 映射为事件父 ID。事件按发生时间和 ID 稳定排序；父事件无需在
JSONL 中先出现，最终引用完整性和审计链仍由协议与规则检查。

## 显式写入辅助函数

外围辅助函数只生成旁车记录，不调用 `store.put`，不会获得外部记忆库权限：

```python
from datetime import UTC, datetime

from taiyi.adapters import instrument_memory_write
from taiyi.analysis import MemoryType, Scope, ScopeKind

namespace = ("user_alice", "memories")
key = "tea_preference"
value = {"preference": "green tea"}

write = instrument_memory_write(
    write_id="write_preference_new",
    namespace=namespace,
    key=key,
    value=value,
    memory_id="memory_tea_preference",
    scope=Scope(kind=ScopeKind.USER, id="user_alice"),
    memory_type=MemoryType.PREFERENCE,
    occurred_at=datetime.now(UTC),
    source_run_ids=("langsmith_run_id",),
    writer_version="memory-writer-v2",
    memory_version="2",
)

store.put(namespace, key, value)
writes.append(write.model_dump(mode="json"))
```

调用方负责只在实际写入成功后保存旁车记录，并在构造离线契约时保留前后快照所引用的历史
写入记录。适配器会重新计算 Store 值哈希，拒绝旁车记录与实际快照不一致的输入。

## 命令行

```text
taiyi analyze adapt-langgraph ./run-bundle.json --output ./run.jsonl
taiyi analyze validate ./run.jsonl
taiyi analyze check ./run.jsonl --format markdown --output ./report.md
```

转换命令返回适配器、框架和协议版本、记录数量及解析后的输出路径。输出文件的父目录会按需
创建；命令不会初始化 `v0.1.1` 身份 SQLite。

## 已知限制

- 本契约消费用户在 Agent 环境中整理的离线 Store 与 Run 数据，不直接调用 LangSmith 导出
  API 接口；
- `tool` 运行按完成后的 `tool_result` 表达，单独的工具调用意图需要调用方另建明确事件；
- 任意 Store JSON 值统一作为一项记忆内容计算哈希，不解释其中的业务字段；
- 不复制运行输入、输出或记忆值到中性协议，报告无法显示原文；
- 不支持从 checkpoint 状态推断长期记忆；短期线程状态不属于本适配器首版范围；
- 新框架版本、异步导出器和直接 SDK 提取属于后续兼容检查点。

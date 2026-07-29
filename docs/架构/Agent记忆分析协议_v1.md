# Agent 记忆分析协议 v1

- 协议版本：`1.0`
- 文档状态：首个实现版本
- 对应工作项：`TY-202607281622`
- 外部议题：[GitHub #5](https://github.com/xkyyxlk/Taiyi/issues/5)
- 更新时间：2026-07-29

## 目标

本协议定义 Agent 框架、测试夹具和太一分析核心之间的 JSONL 边界。一个文件描述一次运行
的运行前快照、运行事件和运行后快照，使分析器能够在不访问外部记忆库写接口的情况下校验
输入并比较记忆变化。

协议只表达可观察工程状态，不证明记忆真实、恶意、过期或应当删除。

## 编码与文件规则

- 文件使用 UTF-8 编码；
- 每行必须是一个完整 JSON 对象；
- 允许文件以一个换行符结束，不允许空行；
- 不允许同一 JSON 对象包含重复字段；
- 所有记录都必须包含 `protocol_version`、`record_type` 和 `sequence_number`；
- `sequence_number` 从 `1` 开始逐行连续递增；
- 未声明字段一律拒绝，避免拼写错误被静默忽略；
- 时间使用带时区的 RFC 3339 表示，规范化输出使用 UTC；
- 内容哈希使用小写十六进制 SHA-256；
- 标识符必须是非空、非纯空白字符串，最长二百五十六个字符。

## 文件结构与顺序

一个 `1.0` 文件只能描述一个运行，并使用以下顺序：

```text
manifest
snapshot(before)
memory(before) *
event *
snapshot(after)
memory(after) *
```

- `manifest` 必须是第一条且只能出现一次；
- `before` 和 `after` 快照必须各出现一次，标识不得相同；
- 运行前记忆紧随 `before` 快照；
- 事件位于两个快照之间；
- 运行后记忆紧随 `after` 快照；
- 同一快照内 `memory_id` 唯一，同一记忆可以在前后快照复用相同标识；
- `event_id` 在文件内唯一；
- 记忆和事件引用在完整文件读取后校验，因此可以引用文件中稍后出现的事件。

## 公共字段

| 字段 | 类型 | 规则 |
|---|---|---|
| `protocol_version` | 字符串 | 当前必须精确为 `1.0` |
| `record_type` | 枚举 | `manifest`、`snapshot`、`event` 或 `memory` |
| `sequence_number` | 正整数 | 从一开始按文件行连续递增 |

## `manifest` 记录

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `project_id` | 标识符 | 是 | Agent 项目的稳定标识 |
| `run_id` | 标识符 | 是 | 当前运行的稳定标识 |
| `baseline_run_id` | 标识符或空 | 否 | 当前运行所比较的基线运行 |
| `captured_at` | 带时区时间 | 是 | 文件生成时间 |
| `producer` | 对象 | 是 | 生产器的 `name` 和 `version` |
| `model_version` | 字符串 | 是 | 当前运行使用的模型版本 |
| `prompt_version` | 字符串 | 是 | 当前运行使用的提示词版本 |
| `tool_versions` | 对象 | 是 | 工具名称到版本的映射，可以为空 |
| `writer_version` | 字符串 | 是 | 默认记忆写入器版本 |

版本字段是可追溯标识，不要求符合某一种包版本语法，但不得为空或只包含空白。

## `snapshot` 记录

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `snapshot_id` | 标识符 | 是 | 本次捕获快照的稳定标识 |
| `snapshot_role` | 枚举 | 是 | `before` 或 `after` |
| `captured_at` | 带时区时间 | 是 | 快照捕获时间 |

快照记录只是记忆集合的边界，不表示 `v0.1.1` 身份快照，也不继承旧身份审核语义。

## `event` 记录

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `event_id` | 标识符 | 是 | 来源事件稳定标识 |
| `event_type` | 枚举 | 是 | 事件类别 |
| `scope` | 对象 | 是 | 显式作用域 `kind` 和 `id` |
| `occurred_at` | 带时区时间 | 是 | 事件发生时间 |
| `content_hash` | SHA-256 | 是 | UTF-8 正文的内容哈希 |
| `content` | 字符串或空 | 否 | 可选原始正文 |
| `parent_event_ids` | 标识符数组 | 是 | 显式父事件，可以为空 |

`event_type` 允许以下值：

```text
user_input
model_output
tool_call
tool_result
document_read
memory_write
system
```

如提供 `content`，分析器必须重新计算哈希并与 `content_hash` 比较。父事件不得引用自身，
且所有父事件必须存在于同一文件。

## `memory` 记录

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `snapshot_id` | 标识符 | 是 | 所属 `before` 或 `after` 快照 |
| `memory_id` | 标识符 | 是 | 跨快照稳定的记忆标识 |
| `scope` | 对象 | 是 | 显式作用域 `kind` 和 `id` |
| `memory_type` | 枚举 | 是 | 记忆类别 |
| `content_hash` | SHA-256 | 是 | UTF-8 记忆正文哈希 |
| `content` | 字符串或空 | 否 | 可选记忆正文 |
| `source_event_ids` | 标识符数组 | 是 | 显式来源事件，可以为空 |
| `created_at` | 带时区时间 | 是 | 首次创建时间 |
| `updated_at` | 带时区时间 | 是 | 最近更新时间，不得早于创建时间 |
| `writer_version` | 字符串 | 是 | 产生该记录的写入器版本 |
| `memory_version` | 字符串或空 | 否 | 外部系统提供的记忆版本 |

`memory_type` 允许以下值：

```text
episodic
semantic
procedural
preference
relational
custom
```

`source_event_ids` 字段缺失属于协议错误；字段存在但数组为空属于有效协议数据，由来源完整性
规则产生确定性发现。引用不存在的事件属于引用完整性错误，协议读取失败。

## 作用域

`scope` 必须包含以下字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `kind` | 枚举 | `agent`、`user`、`tenant`、`session` 或 `custom` |
| `id` | 标识符 | 外部系统中的稳定作用域标识 |

协议只校验作用域结构。记忆与来源事件作用域不一致仍是可读取输入，后续作用域规则应生成
发现，而不是把问题隐藏为解析失败。

## 结构错误与治理发现

协议读取器处理结构正确性；分析规则处理有效输入中的治理风险：

| 情况 | 分类 | 行为 |
|---|---|---|
| JSON 无效、重复字段、未知字段 | 协议错误 | 读取失败 |
| 不支持的协议版本 | 协议错误 | 读取失败 |
| 记录乱序、序号不连续 | 协议错误 | 读取失败 |
| 重复事件或同快照重复记忆标识 | 协议错误 | 读取失败 |
| 哈希与所附正文不一致 | 协议错误 | 读取失败 |
| 引用不存在的事件 | 协议错误 | 读取失败 |
| 来源数组为空 | 治理发现 | 输入有效，后续规则报告 |
| 记忆与来源作用域不一致 | 治理发现 | 输入有效，后续规则报告 |
| 前后快照内容或类型变化 | 记忆变化 | 输入有效，差异阶段报告 |

## 版本与兼容策略

当前实现只接受 `1.0`：

- 主版本不为一时拒绝；
- 高于 `1.0` 的次版本在支持规则发布前也拒绝；
- 未知字段拒绝，不进行静默向前兼容；
- `1.0` 字段含义和枚举一经发布不得原地改变；
- 兼容新增必须先定义读取行为、示例和自动测试，再发布新的次版本；
- 删除字段、改变含义或收紧既有合法输入必须提升主版本并提供迁移说明。

严格版本策略会降低早期扩展速度，但能防止持续集成对未知输入产生看似成功的错误报告。

## 最小示例

以下示例省略可选正文，只保留内容哈希。真实文件必须保持每条 JSON 独占一行：

```jsonl
{"protocol_version":"1.0","record_type":"manifest","sequence_number":1,"project_id":"project_demo","run_id":"run_candidate","baseline_run_id":"run_baseline","captured_at":"2026-07-29T06:00:00Z","producer":{"name":"example-adapter","version":"1.0.0"},"model_version":"model-a","prompt_version":"prompt-v2","tool_versions":{},"writer_version":"writer-v3"}
{"protocol_version":"1.0","record_type":"snapshot","sequence_number":2,"snapshot_id":"snapshot_before","snapshot_role":"before","captured_at":"2026-07-29T06:00:00Z"}
{"protocol_version":"1.0","record_type":"memory","sequence_number":3,"snapshot_id":"snapshot_before","memory_id":"memory_1","scope":{"kind":"user","id":"user_alice"},"memory_type":"preference","content_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_event_ids":["event_1"],"created_at":"2026-07-29T05:00:00Z","updated_at":"2026-07-29T05:00:00Z","writer_version":"writer-v2","memory_version":"1"}
{"protocol_version":"1.0","record_type":"event","sequence_number":4,"event_id":"event_1","event_type":"user_input","scope":{"kind":"user","id":"user_alice"},"occurred_at":"2026-07-29T06:01:00Z","content_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","parent_event_ids":[]}
{"protocol_version":"1.0","record_type":"snapshot","sequence_number":5,"snapshot_id":"snapshot_after","snapshot_role":"after","captured_at":"2026-07-29T06:02:00Z"}
{"protocol_version":"1.0","record_type":"memory","sequence_number":6,"snapshot_id":"snapshot_after","memory_id":"memory_1","scope":{"kind":"user","id":"user_alice"},"memory_type":"preference","content_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","source_event_ids":["event_1"],"created_at":"2026-07-29T05:00:00Z","updated_at":"2026-07-29T06:02:00Z","writer_version":"writer-v3","memory_version":"2"}
```

## 实现入口

- 中性协议模型：`src/taiyi/analysis/models.py`；
- JSONL 读取和结构校验：`src/taiyi/analysis/protocol.py`；
- [LangGraph 与 LangSmith 参考适配器 v1](LangGraph与LangSmith参考适配器_v1.md)；
- 初始标准场景：[Agent 记忆分析标准场景](../质量/Agent记忆分析标准场景.md)。

# 太一

> 一体万化，万忆归一。

太一是一个本地优先的 AI 身份实验框架。它通过可追溯事件、隔离世界线、
版本化快照和人工审核归一来实现身份的分叉、演化、合并与回滚。

可以把太一理解为：**AI 身份的版本控制系统**。

太一研究记忆连续性和身份叙事连续性，不声称创造、检测或证明 AI 的主观意识。

## v0.1 能力

- 从身份快照派生相互隔离的同位体；
- 追加式记录用户消息、模型回复和系统操作；
- 提取带来源、可信度、重要性和版本信息的长期记忆；
- 比较世界线中的重复、补充和冲突；
- 以 `coexist`、`select`、`synthesize`、`suspend` 或 `reject` 人工审核归一；
- 生成不可变快照，审计、回滚并从新快照再派生；
- 擦除敏感事件正文并使其派生记忆失效；
- 导出 JSONL/Markdown，并运行三个可复现实验。

## 安装

需要 Python 3.11 或更高版本：

```bash
python -m venv .venv
# Windows：.venv\Scripts\activate
# macOS/Linux：source .venv/bin/activate
python -m pip install -e ".[dev]"
taiyi --help
```

状态默认保存在操作系统的本地应用数据目录。开发和实验时可以明确指定目录：

```bash
taiyi --data-dir .taiyi init "我的太一"
```

## 首次分叉与归一

默认 `MockProvider` 完全离线且输出可重复。它识别
`remember [主题]: 内容` 形式的演示记忆：

```bash
taiyi --data-dir .taiyi init "我的太一"
taiyi --data-dir .taiyi fork 哲学家
taiyi --data-dir .taiyi fork 科学家
taiyi --data-dir .taiyi chat 哲学家 "remember [方法]: 反思很重要"
taiyi --data-dir .taiyi chat 科学家 "remember [方法]: 实验很重要"
taiyi --data-dir .taiyi diff 哲学家 科学家
taiyi --data-dir .taiyi merge propose 哲学家 科学家
```

记下提案编号和差异项编号，再明确审核。冲突默认悬置；也可以覆盖策略：

```bash
taiyi --data-dir .taiyi merge review <提案编号> --approve
taiyi --data-dir .taiyi merge apply <提案编号>
taiyi --data-dir .taiyi history
taiyi --data-dir .taiyi rebirth 下一代
```

`merge review` 还支持重复传入 `--resolution 差异项编号=策略`，以及通过
`--content 差异项编号=内容` 指定被选择的记忆编号或人工综合文本。未经审核的提案不能应用。

## 使用 OpenAI 模型提供器

模型调用只存在于模型提供器边界，领域层不依赖模型软件开发工具包：

```bash
set TAIYI_PROVIDER=openai
set OPENAI_API_KEY=你的密钥
set TAIYI_OPENAI_MODEL=gpt-5.6-terra
```

macOS/Linux 使用 `export` 代替 `set`。模型名可配置；生产使用前请根据账户可用模型和
当前官方文档确认。API 密钥不会写入数据库。

## 审计、删除和实验

```bash
taiyi --data-dir .taiyi memory search 哲学家 反思
taiyi --data-dir .taiyi memory inspect <记忆编号>
taiyi --data-dir .taiyi event redact <事件编号>
taiyi --data-dir .taiyi export ./export
taiyi --data-dir .taiyi evaluate
taiyi --data-dir .taiyi experiment run all --output-dir ./experiments
```

`event redact` 会永久清除事件正文、可追踪的派生事件正文，并将相关派生记忆标记为
已删除；事件 ID、顺序和原正文哈希仍保留用于证明曾发生过一次删除。请先备份需要
保留的数据。

## 开发

```bash
ruff check .
mypy src/taiyi
pytest --cov=taiyi
```

更多信息见 [架构](docs/ARCHITECTURE.md)、[评估](docs/EVALUATION.md)、
[已知限制](docs/LIMITATIONS.md)、[开发计划](docs/DEVELOPMENT_PLAN_V0.1.md) 和
[架构决策记录](docs/adr/)。项目采用 [Apache-2.0](LICENSE) 许可证。

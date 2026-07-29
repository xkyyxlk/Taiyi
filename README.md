# 太一

> 一体万化，万忆归一。

太一目前是一个本地优先、人工治理的 AI 身份演化产品原型。它让用户从同一身份版本
派生多个运行实例，观察不同经历如何形成记忆与冲突，再由用户决定哪些内容进入下一
身份版本。

可以把太一理解为：**AI 身份的版本控制系统**。

这个说法是帮助理解谱系、分叉和审核的工程比喻。太一所称的身份不是模型权重、完整
对话历史或主观意识，而是经过治理、可以被后续运行实例继承的身份状态。经历不等于
记忆，记忆也不自动成为身份；只有经过审核并写入快照的内容才可以继承。

太一研究记忆连续性和身份叙事连续性，不声称创造、检测或证明 AI 的主观意识，也不
保证模型生成的记忆客观真实。完整边界见[产品定义](docs/产品/产品定义.md)。

当前发布版本是已经打通核心闭环的本地产品原型。`v0.1.1` 在没有真实用户验证的情况下
按维护者决定发布，不承诺生产级稳定性、学术研究基准或确定的最终市场方向。

当前开发分支正在建设本地优先、只读旁路的 Agent 长期记忆分析工具。该能力尚未发布，
开发版本可以使用版本化 JSONL 校验和确定性检查：

```bash
taiyi analyze validate ./run.jsonl
taiyi analyze check ./run.jsonl
taiyi analyze check ./run.jsonl --policy ./policy.json
taiyi analyze check ./run.jsonl --format markdown --output ./report.md
taiyi analyze check ./run.jsonl --format html --output ./report.html
taiyi analyze simulate --seed 20260729 --count 1000 --output-dir ./analysis-scenarios
taiyi analyze adapt-langgraph ./run-bundle.json --output ./run.jsonl
```

`simulate` 会生成固定种子的提交级案例、独立标准答案和可复核清单。分析命令不初始化旧身份
SQLite，不调用外部模型，也不写入外部记忆库。协议和报告规范见
[Agent 记忆分析协议 v1](docs/架构/Agent记忆分析协议_v1.md)与
[Agent 记忆分析规则与报告 v1](docs/架构/Agent记忆分析规则与报告_v1.md)。LangGraph 与
LangSmith 的离线输入和显式写入字段见
[参考适配器 v1](docs/架构/LangGraph与LangSmith参考适配器_v1.md)。

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

## 体验本地产品原型

使用一个全新的数据目录启动十至十五分钟核心体验：

```bash
taiyi --data-dir .taiyi-prototype prototype
```

命令默认只监听 `127.0.0.1` 并打开浏览器。页面会预填“未知任务的两种选择”演示，依次
引导创建身份、派生两个同位体、输入经历、查看记忆来源、比较世界线、人工审核归一、
生成新快照以及回滚或重生。默认 `MockProvider` 完全离线，不需要 API 密钥。

完整说明见[产品原型使用指南](docs/产品/产品原型使用指南.md)。

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

完整文档入口见[文档索引](docs/文档索引.md)。常用资料包括
[产品定义](docs/产品/产品定义.md)、[系统架构](docs/架构/系统架构.md)、[评估](docs/质量/评估.md)、
[已知限制](docs/产品/已知限制.md)、[开发计划](docs/产品/开发计划_v0.1.md) 和
[架构决策记录](docs/架构/决策记录/)。项目采用 [Apache-2.0](LICENSE) 许可证。

## 持续迭代与新会话

长期开发以 [项目迭代工作流](docs/开发/项目迭代工作流.md) 为准。当前断点记录在
[迭代状态](docs/开发/迭代状态.md)，切换 Codex 会话时可以直接使用
[会话交接模板](docs/开发/会话交接模板.md)。每次迭代的目标、实际改动、决策、验证和
提交永久保存在[迭代记录索引](docs/开发/迭代记录/记录索引.md)。新会话必须先读取这些
文件并核对 Git 现场，不得只依赖旧会话记录。

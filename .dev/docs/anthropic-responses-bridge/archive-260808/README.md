# Anthropic Responses bridge 本会话终态记录

## 文档性质

本文是 2026-08-08 收尾时的历史终态记录，只回答“本会话完成了什么、当时证据支持到哪里”。它不是当前实施状态、部署 readiness 或下一动作的第二状态源。代码、分支、测试、候选、未闭合项与下一动作等易变事实必须回到 [Implementation](../implementation.md)；替代现服前的实时判断必须回到 [Readiness](../../service-cutover/readiness.md)。

本文及同目录的 [evidence-index.md](evidence-index.md) 不移动、不改写任何原始 `docs/tmp` report。报告均保留其原始 point-in-time 身份、候选 HEAD、内容 hash、范围与 verdict。

## 本会话完成的工作

截至本记录形成时，本会话已把 Anthropic Messages → OpenAI Responses 主路径从 foundations 推进到 current `main@fb4272b5752bd8439c1ee5a098960f31d4ea70f1`：reasoning carrier／cardinality、session liveness、request conversion、non-stream conversion与usage、stream semantic parser、route policy、semantic parity、route happy path、typed block delivery、reasoning capability、History facts、production stream route、stream request facts、headers-before network retry、resident-byte primitive与production wiring，以及 Copilot token／response／item identity兼容修复均已按独立切片进入主线；对应 reviewed source refs已归档。

本会话同时维持了三条不可混淆的边界：Spec继续是唯一行为 oracle；Acceptance继续是验收 oracle而不是产品通过报告；Architecture继续是尚待用户裁决的非规范提案，`D-ARCH`／`D-MIGRATION`没有因代码落地或评审绿灯自动成为 ADR。

上述结论是本会话终态，不承诺未来 `main`、报告集合或未闭合范围不再变化。当前事实只以 [Implementation](../implementation.md) 为准。

## 真实 Copilot canary 结果

独立复跑在 2026-08-08 将验证对象固定为 `main@fb4272b5752bd8439c1ee5a098960f31d4ea70f1`，仅使用隔离的 `127.0.0.1:4142`，没有接管生产 `4141`：

- readiness 为 HTTP 200；`/api/models` 为 HTTP 200，观测到 32 个模型，其中 10 个明确声明 Responses endpoint。
- 选用 `gpt-5.3-codex`；正式 `anthropic.route_override: responses` 下，non-stream 为 HTTP 200并产生 Anthropic `text` content block。
- stream 为 HTTP 200，事件顺序为 `message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop`，判定为合法 Anthropic message sequence。
- token值、生成正文、reasoning内容、tool arguments与response body均未写入报告；Python child经精确进程 handle发送SIGTERM并完成`wait()`／reap，清理后`4142`无listener。
- 成功窗口内旧Bun `4141` incarnation前后一致，canary向旧Bun发送signal数为0；没有执行cutover。

最初的 canary 摘要缺少可访问原始运行输出，独立快速复核因此给出1项major；随后 [最小真实 Copilot canary 独立复跑](evidence/real-copilot-canary.md)重新执行并落下可追溯结果。历史缺口与后续闭合过程分别保留在 [原始摘要](../../../tmp/260807-real-copilot-canary.md)、[证据缺口复核](../reports/260807-review-real-copilot-canary.md)和归档内的[独立复跑](evidence/real-copilot-canary.md)中，不通过改写旧报告抹平。

## 未闭合范围

本会话没有把完整产品升级为 `PASS`。收尾时明确未闭合的范围包括：

- 真实 tool-use、tool arguments roundtrip与完整 reasoning／thinking／carrier live矩阵。
- 完整 request／global quota、backpressure、有限queue、admission及metrics／History映射。
- 真实 loopback sink的kernel-level partial write／RST、accepted／partial／uncertain delivery分类及禁止错误重发。
- 完整 Acceptance required gates，包括未在同一候选上闭合的错误、retry、usage parity、cancel／shutdown、HTTP／WS与fault矩阵。
- 真实 systemd user manager、socket activation、effective cgroup、restart与manager stop；S5保持`BLOCKED`。
- 数据／认证disposition、rollback、observation与生产`4141`接管；部署保持`NO_CUTOVER`。
- Architecture的`D-ARCH`／`D-MIGRATION`仍须按live文档中的裁决边界由用户决定，不能从本历史记录推导为已接受。

这些条目只是本会话收尾快照。增删、优先级与最新证据必须查阅live载体。

## Current live carriers

- [Spec](../spec.md)：唯一行为 oracle；稳定行为合同由此定义。
- [Architecture](../architecture.md)：非规范架构提案及`D-ARCH`／`D-MIGRATION`裁决入口。
- [Acceptance](../acceptance.md)：完整产品验收 oracle；定义required gates与证据等级。
- [Implementation](../implementation.md)：bridge易变实施状态、current `main`、已落地切片、未闭合项与下一动作的真相源。
- [Service cutover Readiness](../../service-cutover/readiness.md)：替代现服前的实时readiness矩阵与`NO_CUTOVER`状态源。
- [Systemd runtime Plan](../../systemd-runtime/plan.md)：S3～S7运行态实施与阻塞状态的live计划。
- [Service cutover Plan](../../service-cutover/plan.md)：生产接管、数据disposition、rollback与观察顺序的live计划。
- [本次关键证据索引](evidence-index.md)：只提供少量point-in-time报告入口，不承担current状态。

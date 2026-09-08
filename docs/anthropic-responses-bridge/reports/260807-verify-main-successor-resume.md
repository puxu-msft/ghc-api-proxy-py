# Current main successor scoped 独立验收

## 判定

**Scoped verdict：PASS。**

验收对象为主仓 `/home/xp/src/ghc-api-proxy-py` 的 current `main@b91e58a29324b11840002efc53ed6f869b800c39`。用户给出的短 SHA `b91e58a` 经 `git rev-parse b91e58a^{commit}` 解析为同一完整 SHA；验收开始与收尾均满足 `HEAD == refs/heads/main == b91e58a29324b11840002efc53ed6f869b800c39`，分支为 `main`，物理根与 Git top-level 均为 `/home/xp/src/ghc-api-proxy-py`。

本 PASS 只覆盖 current Acceptance 中已经进入 main 的三个 scoped 轴：

1. Responses semantic parser 与 non-stream converter 在 reasoning、text、function call 上的语义 parity，包括 authoritative done、empty reasoning、unknown reasoning summary拒绝与 source／completion order facts。
2. 真实 `/v1/messages` ASGI non-stream Responses route 的 happy path、typed rejection、Responses upstream error envelope、response header policy、Anthropic hooks、approval与单一 History context／finalize。
3. Parser→block delivery 骨架的完整 block 才交付、连续完成前缀、首批 `message_start` 与完整首 block 同 batch、terminal skeleton及 single-writer串行化。

**完整产品 verdict：UNVERIFIED。** 本轮明确不覆盖 production Responses stream route、真实 HTTP SSE／socket delivery、partial write／delivery uncertainty、retry／attempt reset／post-commit failure、resident quota／backpressure，也不覆盖 WebSocket、cancel、shutdown、live canary或capture corpus。不得把 scoped PASS 外推为完整 bridge产品 PASS或cutover readiness。

## Oracle 与身份 gate

- Current Acceptance：`docs/agents/anthropic-responses-bridge/acceptance.md`，SHA-256 `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`。
- Current Spec：`docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。
- 两个 hash 分别由 `sha256sum` 与 Python `hashlib.sha256` 交叉复核，结果一致。
- Acceptance 包含 `FINALIZED_ACCEPTANCE_ORACLE` 状态，并逐字绑定上述 current Spec hash。
- 关键运行模块的进程内 `__file__` 均位于主树 `src`：`app.openai.responses_stream_parser`、`app.protocols.responses_anthropic`、`app.delivery.anthropic_sse`、`app.routes.anthropic`；模块加载 gate为 PASS。

## 从 Acceptance 独立推导的 scoped 矩阵

| Scoped 轴 | Acceptance依据 | 独立判据 | 结果 |
|---|---|---|---|
| Semantic parser parity | `NS-01`～`NS-04`、`STR-03`中可由现有semantic facts验证的部分 | 同一静态 Responses reasoning→text→function_call语义序列，non-stream必须得到 `thinking→text→tool_use`；stream parser必须得到对应 `ReasoningBlock→TextBlock→FunctionCallBlock`，opaque payload、call id、name、arguments及顺序不变 | PASS |
| Empty／authoritative reasoning parity | `REQ-05`、`NS-03` | authoritative item done覆盖中间值；absent／empty encrypted content保持一个empty reasoning semantic block，并由non-stream生成项目bare marker；未知summary part两路均拒绝 | PASS |
| Non-stream route happy | `REQ-01`、`REQ-02`、`NS-01`～`NS-04`、`LIFE-01`～`LIFE-03`的已接线non-stream子集 | 从真实FastAPI `/v1/messages`进入；只发生一个Responses attempt；resolved model与PRE_SEND修改进入最终wire；响应为Anthropic message，reasoning／text／tool／usage正确 | PASS |
| Error与header | `NS-05`、Header契约 | Responses 429变为Anthropic error envelope并保留允许的 `retry-after`；内部OpenAI header不下发；happy path允许的request-id／rate-limit header保留，错误content-length重算 | PASS |
| Hooks与History | `LIFE-01`～`LIFE-03`的已接线non-stream子集 | 同一RequestContext只started／finalized一次；happy为 `REQUEST_RECEIVED→RESPONSE→FINALIZE`，typed failure为 `REQUEST_RECEIVED→ERROR→FINALIZE`；approval不产生第二owner | PASS |
| 完整block与连续前缀 | `STR-02`～`STR-03`的骨架子集 | B先完成而A仍open时sink零batch；A闭合后按A、B顺序提交；首batch包含 `message_start→完整block envelope` | PASS |
| Single writer | `STR-02`、single lifecycle owner不变量的骨架子集 | sink拒绝第二writer；并发block／terminal操作由同一session串行，不发生重叠write | PASS |

## 实际执行证据

### Main scoped tests

在同一 shell链中打印并验证物理根、Git top-level与完整HEAD后执行：

`PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -p no:cacheprovider -q tests/unit/test_responses_stream_parser.py tests/smoke/test_anthropic_responses_route.py tests/smoke/test_anthropic_block_delivery.py`

结果：`44 passed in 3.83s`，退出码 `0`。口径为上述三个文件、主树完整提交 `b91e58a29324b11840002efc53ed6f869b800c39`。独立执行同路径 `--collect-only -q` 后按 node ID计数得到 `44`，退出码 `0`，与pytest运行摘要一致。

这三份测试分别提供：semantic parser与non-stream parity；真实ASGI non-stream Responses route的happy／error／header／hooks／History；parser驱动block delivery与single-writer。它们是主树真实测试，不是另一个worktree的结果。

### 独立小探针

探针从 current Acceptance推导静态expected，不调用产品codec生成expected：

- 静态producer vector固定使用项目主v1的 `opaque-😀` expected signature；non-stream实际content类型为 `thinking、text、tool_use`，stream parser实际semantic类型为 `ReasoningBlock、TextBlock、FunctionCallBlock`，字段与顺序逐项相等。
- Parser→delivery输入两个message source；B先完成时断言sink仍为空，A完成后捕获text marker精确为 `A、B`，batch数为2，第二writer被 `SingleWriterViolation`拒绝。

探针结果：`PASS`。结构化输出保存于仓库外 `/tmp/ghc-verify-b91e58a-probes.json`，不属于持久化产品资产；本报告记录可复现输入、判据与结果。

### 目标正控

目标机制：`ContinuousPrefixSequencer`不得让已完成的后序source越过仍open的前序缺口。

正控采用进程内单侧monkeypatch，仅替换 `reconcile_open_identities()`的release策略，不修改producer、parser、renderer、expected或仓库文件。变异让任意closed后序source立即返回；同一独立探针按唯一目标原因变红：`later block leaked before the earlier source closed`。随后恢复原方法并重跑，重新得到B先完成时零写入、最终 `A、B`与single-writer拒绝，结果转绿。

正控结论：判据确实咬住“后序block越过前序缺口”这一目标缺陷，不是fixture解析、模块未加载或旁路断言导致的红。

## 被排除的运行结果

共享terminal surface存在其他并行会话。两类输出被机械排除，不进入本 verdict：

- 一次全仓尝试得到空日志、退出码0且没有JUnit文件。这是不可接受的false-green形态，已作废。
- 另一次输出明确打印物理目录 `/home/xp/src/ghc-api-proxy-py-stream-route`、分支 `feat/anthropic-responses-stream-route`，并运行了本主树不存在于scoped范围的production stream-route测试。它未通过目标树gate，全部结果均不归属于本次main验收。

因此本报告不声称“全仓pytest已通过”。可归属且计入结论的是固定main HEAD上的44项scoped测试、44项collect-only交叉计数、主树模块加载gate、独立小探针及目标正控。该证据足以判定用户指定的已实现scoped轴为PASS，但不能提升完整产品状态。

## 未验证边界

以下项目明确为 `UNVERIFIED`，不是已证实缺陷，也不是本次PASS组成部分：

- Production Anthropic→Responses stream route接线。
- 真实HTTP SSE consumer、loopback socket、chunk／frame边界、RST、half-close与partial write。
- Sink `delivery-uncertain`、post-commit partial failure及禁止full replay的route-level实证。
- Retry owner、attempt reset、retry exhaustion与失败attempt隔离。
- 普通per-request aggregate、global resident quota、有限queue与backpressure。
- Client cancellation、shutdown、WebSocket transport、HTTP／WS parity。
- Live canary、SDK前raw capture provenance、capture corpus与local fault矩阵。

## 结构边界观察

本轮只验收用户可观察行为，不做架构review。与验收范围直接相关的唯一结构边界是：`src/app/delivery/anthropic_sse.py`仍是独立delivery skeleton，尚未构成production stream route／socket sink。处置为保持本轮scope不扩张，并将相应产品轴明确留在 `UNVERIFIED`；这不是本轮缺陷。

## 最终结论

`main@b91e58a29324b11840002efc53ed6f869b800c39` 的 semantic parser parity、真实non-stream Responses route happy／error／header／hooks／History，以及block delivery skeleton／single-writer三个已实现scoped轴：**PASS**。

完整 Anthropic Messages↔OpenAI Responses bridge产品：**UNVERIFIED**。

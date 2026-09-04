# Anthropic Responses bridge research R2 独立复评

## 评审结论

- **评审范围**：`docs/agents/anthropic-responses-bridge/research.md` 当前工作树内容，SHA-256 `04abcaffca8d8754341184ef76e6e5ba1013d606671cf22358592a8d83aead17`；复核首轮唯一 major、抽样 20 个 `file:line` 引用、来源 HEAD／commit-tree provenance、后续用户目标约束，以及目标结论是否误采 upstream 有损 reasoning 聚合。
- **总体 verdict**：**修复 major 后可进入下一阶段。** 首轮 `file:line` major 已关闭，但最新用户重裁没有完整同步到研究文档，当前不能定稿。
- **blocker 数**：0。
- **major 数**：1。

## 双视角覆盖证据

### 机械核对

- 每次有效 shell 取证均在同一调用中 gate `/home/xp/src/ghc-api-proxy-py` 的物理 top-level、分支 `main`、`HEAD == refs/heads/main`；复评绑定 current main `ed77c9d191df81c451c25161420515cca52ce6a4`。出现过共享终端串流污染时，因 nonce／输出标签不匹配已作废并重跑，污染输出未纳入证据。
- 来源代码均从文档声明的固定 commit tree 读取，而非采信来源仓工作树。主 upstream 固定为 `/home/xp/src/copilot-api-js` @ `8d5c861c2e079b92401dd8ccd49695a363d078fe`；抽样还覆盖目标历史快照 `47d9ef101c4b81ac70d805b1da157b34d021d33d`、`caozhiyuan-copilot-api` @ `6b97876927b7209a1e0f498e81927b32cc443e52`、VS Code upstream @ `d62bf252c865fbf41550ce3076e918c52f0bced7`、`CLIProxyAPIPlus` @ `0c48ef58e0d37220367401b8f7cf689e2e50a701` 与 `awsl-maxx` @ `03d018fac3645b14d7b6d51b223b2148227c8992`。
- 逐行抽样 20 个最终引用，且包含首轮四处原错误：`anthropic.py:53-120`、`openai.py:80-112`、`driver.ts:1335-1418`、`responses-stream-translation.ts:88-144`。四个扩展范围现均覆盖被声称的决定性动作：stream passthrough／idle timeout／SSE return、`client.responses(request)`、boundary flush／`committedAny`／ledger record，以及 default／`return []`。
- 其余 16 个样本覆盖目标 buffering primitive，以及 upstream／refs 的 route、request、tool-name、reasoning、commit、delivery、并行 tool 与 stream coverage 结论。各引用范围均包含对应命题的关键动词，未发现同类范围过短问题。
- 将 `research.md:11-18,103-105,123,171-177,187-193,203-208` 与 current `spec.md:3-8,203-229`、`architecture.md:1-9,31-37` 及 `docs/tmp/260806-arbitrate-reasoning-aggregation.md:5-9,29-35` 对账。研究文档已经补入一轮用户目标约束，但没有同步更晚的重裁结果：carrier wire 已冻结，不再是“具体编码后续冻结”；16 MiB 已被明确取消为产品／架构阈值，不应继续作为具名约束来组织合同。

### 第一人称执行模拟

- 以规格作者身份沿 route decision → request bridge → non-stream response → reasoning carrier → stream parser → block accumulator → commit frontier → delivery owner → retry／error 路径执行；文档始终把 protocol parser 的细粒度事件处理与 downstream block-level delivery 分开，没有把 upstream transport streaming 解释成 live downstream flush。
- 以实现者身份走 encrypted-only reasoning 与多个 reasoning items：文档先把 upstream 的“聚合所有 summary、只留最后 ciphertext、summary 为空则不生成 block”标为已确认反例，再要求目标按 reasoning item identity 一对一保存 visible summary、opaque payload 与 provenance；能力矩阵也明确写“采用但重写 reasoning 聚合”。因此文档没有把 upstream 有损 producer 当目标 oracle。
- 继续按“目标项目约束”执行时会遇到相反问题：`research.md:18,105` 告诉实施者 carrier 只需版本化，具体编码、版本识别与兼容／拒绝规则仍待后续规格冻结；但 current Spec 已按最新用户重裁冻结 `copilot-api:synthetic-reasoning:v1:` prefix、UTF-8→unpadded base64url、bare prefix、legacy sentinel、strip 与 malformed 边界。实施者可能据研究重新设计 carrier 或重开已决合同。
- 以容量测试作者身份执行 `research.md:16,123,193` 时，会把“超过 16 MiB”保留成具名边界；current Spec／Architecture 则明确要求 16 MiB 只是普通大小，不得建立专门 gate、fixture、metric threshold 或状态分支，只能使用普通 per-request aggregate＋global reservation／backpressure。两种文字会导出不同验收设计。

## 抽样清单

| # | 固定来源与引用 | 核验命题 | 结果 |
|---|---|---|---|
| 1 | target `47d9ef1`，`src/app/routes/anthropic.py:53-120` | stream passthrough、idle timeout、SSE return | 通过；原错误已关闭 |
| 2 | target `47d9ef1`，`src/app/routes/openai.py:80-112` | `/responses` 调用 `client.responses(request)` | 通过；原错误已关闭 |
| 3 | upstream `8d5c861`，`src/lib/pipeline/driver.ts:1335-1418` | boundary flush、`committedAny`、成功后 ledger record | 通过；原错误已关闭 |
| 4 | caozhiyuan `6b97876`，`responses-stream-translation.ts:88-144` | unknown event 的 default／`return []` | 通过；原错误已关闭 |
| 5 | target `47d9ef1`，`buffered_retry.py:4-18` | 整流 `bytearray`＋cap，无 block grammar／ledger | 通过 |
| 6 | upstream `8d5c861`，`router.ts:201-247` | direct Messages、Responses、CC 与 vendor fallback 决策 | 通过 |
| 7 | upstream `8d5c861`，`anthropic-to-responses-request.ts:113-168` | 从零构造 Responses request 字段 | 通过 |
| 8 | upstream `8d5c861`，同文件 `:214-255` | assistant text／reasoning 聚合后置于 tool calls 前 | 通过 |
| 9 | upstream `8d5c861`，`openai-responses-cell.ts:88-113` | direct converter 接线且 S3 rewrite 为空 | 通过 |
| 10 | upstream `8d5c861`，`tool-name-sanitize.ts:183-224` | definitions、input calls、forced choice 同步能力 | 通过 |
| 11 | upstream `8d5c861`，`responses-to-anthropic.ts:163-173` | summary 全局累加且 ciphertext last-wins | 通过 |
| 12 | upstream `8d5c861`，同文件 `:210-219` | 仅 summary 非空时生成 thinking block | 通过 |
| 13 | upstream `8d5c861`，`synthetic-reasoning.ts:31-46` | v1 prefix、legacy sentinel、base64url payload | 通过 |
| 14 | VS Code upstream `d62bf25`，`responsesApi.ts:631-655` | `rs` id＋encrypted payload 的 domain gate | 通过 |
| 15 | caozhiyuan `6b97876`，`responses-translation.ts:147-253` | tool／reasoning 边界的连续 run flush | 通过 |
| 16 | upstream `8d5c861`，`commit-boundaries.ts:1-24` | content block／error boundary | 通过 |
| 17 | upstream `8d5c861`，`committed-blocks-ledger.ts:1-29` | 只记录完整提交 block | 通过 |
| 18 | upstream `8d5c861`，`delivery/session.ts:354-478` | 唯一 owner 写入与 committed error | 通过 |
| 19 | CLIProxyAPIPlus `0c48ef5`，Responses Go translator `:281-305` | output index＋tool index 复合 key 分桶 | 通过 |
| 20 | awsl-maxx `03d018f`，`claude_to_codex.go:239-278` | 仅 start／text delta／stop 且事件名非标准 | 通过 |

## 首轮 major 处置

首轮唯一 major 为多处引用范围在关键动作前结束。当前文档已扩大四处范围，并声明对全部 76 个唯一引用完成关键动词覆盖复验。本轮独立抽样 20 个引用，包含四处原错误及跨仓、跨机制样本，未复现范围过短或 provenance 错配；该 major **关闭**。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/research.md:16,18,105,123,177,193,208` — “目标项目约束”只同步了较早裁决，没有同步 current Spec 已记录的最新用户重裁，导致研究文档把已冻结合同写成待冻结，并继续把 16 MiB 当作具名边界 — `research.md:18,105` 只要求 carrier 版本化并称具体编码、版本识别与兼容／拒绝规则仍由后续规格冻结；current `spec.md:3-8,203-229` 已明确固定 upstream v1 wire 是最终 oracle，冻结 ASCII prefix、UTF-8→unpadded base64url、bare prefix、legacy sentinel、strip 与 malformed 行为，且禁止另造 schema／HMAC。`research.md:16,123,193` 反复以“超过 16 MiB”陈述资源合同；current `spec.md:6-8` 与 `architecture.md:7-9,37` 明确 16 MiB 不是产品／架构阈值，不建立专门状态、spill、gate 或 threshold，容量只走普通 per-request aggregate＋global reservation／backpressure。失败场景是实施者依研究重新设计 carrier，或测试作者建立 16 MiB 专属 fixture／状态分支，两者都会违反最新已决合同。修复建议：把 carrier 约束改成固定 upstream v1 byte-compatible wire，并明确“兼容 wire 不等于复制有损聚合”；把 16 MiB 条目改成“无专门阈值，普通内存预算／准入／背压，禁止 spill 与 overflow-to-live”，同步能力矩阵、待冻结合同与评审处置表。修订后再做一次目标约束对账；无需重开已通过的 20 个引用样本。

## 主观建议

无。

## 定稿判定

**0 blocker、1 major。** 首轮引用范围缺陷已经关闭，且文档正确拒绝把 upstream 有损 reasoning 聚合当成目标；但最新用户重裁尚未完整同步，因此当前不能宣布研究文档定稿。关闭上述 major 后可快速复评定稿。

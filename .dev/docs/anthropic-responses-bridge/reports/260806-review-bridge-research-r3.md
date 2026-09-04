# Anthropic Responses bridge research R3 最终独立复评

## 评审结论

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/research.md`，SHA-256 `4fc48d4f6d5d62709c6c7a5e2cfd30a216bdd54446b24d4cf54dde6928dc68aa`；消费 R2 报告 `docs/tmp/260806-review-bridge-research-r2.md`，SHA-256 `ca507b7bce1ad070273a025846a515f9595f46b9be938fcf91bc4f2e3148807a`。复评时主树为 `main`，`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`。本轮只复核 carrier wire 冻结、不得复制有损聚合、取消 16 MiB 具名阈值、低概率事件的最小止血，以及来源事实与目标裁决分层；不重做 R2 已通过的引用抽样或全仓调查。
- **总体 verdict**：**可进入下一阶段；当前研究文档可定稿。** R2 唯一 major 在指定五个维度均已关闭，修订没有引入新的 blocker 或 major。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

### 机械核对

- 逐项对账 R2 的事实性发现、修复建议与最新版正文。`research.md:13-18` 已把四项内容明确标成目标项目的一手用户裁决，并冻结 carrier wire、容量边界与最小止血；`research.md:99-105` 分开记录 upstream 有损聚合反例与可移植 carrier wire；`research.md:123,171-177,193,208` 又在改造要求、能力矩阵、后续合同和处置表重复落实同一边界，没有残留“具体编码后续冻结”或允许复制聚合的旧措辞。
- 将最新版与正式 Spec 及 Architecture 对账。Spec 的 upstream-compatible v1 wire、一 item 一 block、encrypted-only no-loss、无单 block 专属容量阈值与最小 admission 止血，和研究文档的结论一致；Architecture 同样把当前聚合实现标为待修事实，而非目标合同。
- 定向扫描 `16 MiB`、`carrier`、`聚合`、`encrypted-only`、`admission`、`来源`、`upstream` 与 `目标项目` 等词族。所有 `16 MiB` 命中都是否定其语义边界的文字，没有专属 gate、fixture、metric threshold、spill、状态分支或 overflow-to-live 建议；所有聚合命中都将有损行为标为反例或待重写项。
- 只采信完成了主树物理 top-level、`main` 与完整 `HEAD == refs/heads/main` 校验的 shell 证据。共享终端出现过与本轮命令无关的串流输出，已明确作废，没有纳入本报告结论。

### 第一人称执行模拟

- **以 carrier 实现者执行**：从 `research.md:18` 与 `:105` 得到的是固定 `copilot-api-js` v1 prefix、UTF-8→unpadded base64url、bare／legacy、strip 与 malformed 行为，不能另创 delimiter、schema 或 HMAC；不会再把 wire 设计当成待决分叉。
- **以 response converter 实现者执行**：先在 `research.md:99` 看到跨 item summary 聚合、last-ciphertext-wins 与 encrypted-only 丢失是已确认反例，再在 `:105,173,177` 得到逐 reasoning item identity 保存 visible／opaque／provenance 的目标；不会因 wire byte-compatible 而复制 upstream 的有损 forward aggregation。
- **以容量测试作者执行**：`research.md:16,123,193` 明确把任何单 block 大小都当普通大小维度，只测试 per-request aggregate、global reservation、准入、backpressure 与取消清理；跨过 16 MiB 不会触发专属 fixture、指标阈值、状态或 fallback。
- **以故障策略实现者执行**：实际全局内存耗尽这一低概率事件只拒绝新的 bridge admission；文档没有授权 victim selection、终止既有请求、落盘或全面资源策略。若运行证据要求扩展，执行者必须先取得用户裁决。
- **以研究消费者执行**：目标用户裁决集中在“目标项目约束”，目标仓历史快照事实集中在“目标仓当前事实与能力缺口”，外部代码集中在“来源仓库与固定快照／主 upstream 机制”；`research.md:193` 还显式说明现有整流 cap 是目标仓快照事实，不是目标裁决，因此不会把来源实现反向升级为产品合同。

## R2 发现处置

| 指定复核项 | 处置 | 关闭依据 |
|---|---|---|
| Carrier wire 冻结 | **关闭** | `research.md:18,105,177,208` 固定 upstream-compatible v1 wire 与禁止另造私有 carrier；不再写成后续待冻结。 |
| 不得复制有损聚合 | **关闭** | `research.md:18,99,105,173,177,208` 将 wire 互操作与 forward cardinality 分开；聚合 summary、last-ciphertext-wins、encrypted-only 丢失均明确为反例。 |
| 取消 16 MiB 具名阈值 | **关闭** | `research.md:16,123,193,208` 只为否定专属边界而提及该数值，并禁止专属 gate、fixture、metric threshold、状态分支、spill 与 overflow-to-live。 |
| 低概率最小止血 | **关闭** | `research.md:16,123,193,208` 一致规定实际全局内存耗尽时只拒绝新 bridge admission；更全面策略必须先询问用户。 |
| 来源／目标分层 | **关闭** | `research.md:13,34-49,51-65,193,208` 区分一手目标裁决、目标仓固定快照事实、外部来源机制与不可照搬项，并明确当前 primitive 不构成目标合同。 |

## 事实性发现

未发现问题。

## 主观建议

无。

## 定稿判定

**0 blocker、0 major。`docs/agents/anthropic-responses-bridge/research.md` 可定稿。** 本结论只覆盖本报告声明的五个最终复核维度，不把研究文档的静态定稿误写成 bridge 实现已经通过验收。

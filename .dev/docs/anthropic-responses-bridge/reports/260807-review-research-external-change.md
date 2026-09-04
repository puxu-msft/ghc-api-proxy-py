# Anthropic Responses bridge Research 外部变化只读复核

## 评审结论

- **评审范围**：current `docs/agents/anthropic-responses-bridge/research.md`，工作树 SHA-256 为 `54cf0cde2bc7122516bec9948f62a65f7900c775d5bd1da6200cb224f184856e`；对照 Research R3 `docs/tmp/260806-review-bridge-research-r3.md` 绑定的 SHA-256 `4fc48d4f6d5d62709c6c7a5e2cfd30a216bdd54446b24d4cf54dde6928dc68aa`、后续 merged-state 报告 `docs/tmp/260806-review-docs-merged.md`，以及文档引用的固定 commit tree。每次有效 shell 取证均在同一次调用内验证物理 top-level、分支 `main` 与 `HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`。
- **总体 verdict**：**可进入下一阶段；current Research 可提交。** 未观察到未授权语义漂移。R3 后的变化严格限于 merged-state 已指出并授权修复的 Anthropic `/v1/messages` bridge route scope；carrier wire、reasoning cardinality、容量政策、来源／目标裁决分层和既有 `file:line` 修复均保持成立。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

### 机械核对

- 用 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉验证 current Research，均得到 `54cf0cde2bc7122516bec9948f62a65f7900c775d5bd1da6200cb224f184856e`。
- 当前文件是 `AM` 状态且不在 `ed77…` 的 `HEAD` tree 中，因此没有错误地把 `HEAD` 当作正文基线。Index blob SHA-256 为 `04abcaffca8d8754341184ef76e6e5ba1013d606671cf22358592a8d83aead17`，与 Research R2 绑定值一致；R3 报告绑定后续正文 SHA-256 `4fc48d…`。
- 从 current 中逆转三处 route scope 文本并删除对应 merged-state 处置行后，重建内容的 SHA-256 精确等于 R3 绑定值 `4fc48d4f6d5d62709c6c7a5e2cfd30a216bdd54446b24d4cf54dde6928dc68aa`。因此 R3→current 恰有四个变化点，没有第五处外部编辑：`research.md:17`、`:171`、`:187` 限定 route scope，`:209` 记录该 major 的关闭。
- 定向扫描并对账 `carrier`、`byte-compatible`、`聚合`、`encrypted-only`、`16 MiB`、`admission`、`Anthropic /v1/messages`、`原生 OpenAI Responses`、来源与目标裁决措辞。`research.md:13-18,99-105,123,171-177,187-193,208-209` 彼此一致，没有恢复 R2 前的旧合同。
- 直接读取文档绑定的固定 commit tree，复核四处已知扩大引用：`anthropic.py:53-120` 覆盖 `client.execute`、stream 分支、idle timeout、`aiter_raw()`、History／usage finalization 与 SSE response；`openai.py:17-39,80-112` 覆盖 raw stream passthrough、approval、History start 与 `client.responses`；`driver.ts:1335-1418` 覆盖 boundary flush、`committedAny` 与 ledger `recordCommitted`；`responses-stream-translation.ts:88-144` 覆盖 `default` 与 `return []`。引用修复未退化。
- 对 `research.md` 执行 `git diff --check`，未发现 whitespace error。结构怪味扫描覆盖重复产品合同的四个落点、来源事实与目标裁决边界、route scope 以及 file:line 动词范围；未发现相互矛盾的重复实现说明、职责错位或抽象泄漏。

### 第一人称执行模拟

- **以 reasoning carrier 实现者执行**：`research.md:18,99-105,177,208` 要求 producer／consumer 与 `copilot-api-js` v1 wire byte-compatible，但明确把跨 item summary 聚合、last-ciphertext-wins 与 encrypted-only 丢失列为上游反例；执行者会保留逐 item identity、visible／opaque／provenance，而不会复制有损聚合。
- **以容量与背压实现者执行**：`research.md:16,123,193,208` 把 16 MiB 明确降为普通大小，不建立专门状态、fixture、metric threshold、spill 或 overflow-to-live；只使用普通 per-request aggregate、global reservation、admission 与 backpressure，真实全局耗尽时只拒绝新 bridge admission，更全面政策须先取得用户裁决。
- **以路由实现者执行**：`research.md:17,171,187,209` 对 Anthropic `/v1/messages` bridge 给出唯一算法：无 override 时双能力选 Messages、Responses-only 选 Responses、Messages-only 选 Messages、unknown fail closed；原生 OpenAI Responses 公共入口仍走 Responses upstream。执行者不会再把 bridge precedence 外推到 native Responses route。
- **以研究消费者执行**：目标裁决集中在“目标项目约束”，目标仓事实集中在“目标仓当前事实与能力缺口”，外部来源机制及反例集中在后续来源章节；`research.md:193` 又明确当前整流 cap 是历史快照事实而非目标合同。来源事实不会被误升格为用户裁决。
- **以引用跟随者执行**：按四处扩大范围打开固定 commit blob，可以在范围内找到正文声称的完整关键动作，而不是只看到函数入口或缺失的尾部行为。

## R3 后精确差异

| 位置 | R3 语义 | Current 语义 | 裁定 |
|---|---|---|---|
| `research.md:17` | “双端点默认 Messages”会把 native Responses 一并改道 | 仅 Anthropic `/v1/messages` bridge 采用能力驱动 precedence；native Responses 保持 Responses upstream | merged-state major 的授权修复 |
| `research.md:171` | 能力矩阵沿用宽泛“双端点默认 Messages” | 明列 bridge 双能力／Responses-only 分支，并排除 native Responses | 同一修复的矩阵同步 |
| `research.md:187` | 路由合同以宽泛“双端点默认 Messages”为基线 | 路由合同限定 bridge scope，并明确 native Responses 不受影响 | 同一修复的合同同步 |
| `research.md:209` | 无该记录 | 新增 merged-state major 的采纳与关闭记录 | 可追溯处置，不改变其它合同 |

## 事实性发现

未发现问题。

## 主观建议

无。

## 提交判定

**0 blocker、0 major。Current `research.md` 保留 carrier wire 兼容但不复制有损聚合、无 16 MiB 专门阈值、Anthropic `/v1/messages` bridge 双能力默认 Messages 而 native Responses 入口仍走 Responses、来源事实／目标裁决分层，以及已修复的 `file:line` 引用。未观察到未授权语义漂移，可提交。** 本结论只评 Research 文档内容，不外推为 bridge 产品实现已通过验收。

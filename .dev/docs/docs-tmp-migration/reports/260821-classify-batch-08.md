# 分类批次 08：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：48（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-verify-main-happy-usage.md` | main happy pure-path 独立验收 | `anthropic-responses-bridge` | high | |
| `260807-verify-main-successor-resume.md` | successor scoped 独立验收 | `anthropic-responses-bridge` | high | |
| `260807-verify-nonstream-response.md` | non-stream response 独立复验 | `anthropic-responses-bridge` | high | |
| `260807-verify-nonstream-usage.md` | non-stream usage 独立复验 | `anthropic-responses-bridge` | high | |
| `260807-verify-resident-byte-budget.md` | resident byte budget 验收 | `anthropic-responses-bridge` | medium | 属 bridge 交付层的资源配额机制，非独立话题 |
| `260807-verify-route-happy-r2.md` | route happy-path 复验 R2 | `anthropic-responses-bridge` | high | |
| `260807-verify-route-happy-r3.md` | route happy-path 验收 R3 | `anthropic-responses-bridge` | high | |
| `260807-verify-route-happy.md` | route happy-path 独立验收 | `anthropic-responses-bridge` | high | |
| `260807-verify-semantic-parity-r2.md` | semantic parity 验收 R2 | `anthropic-responses-bridge` | high | |
| `260807-verify-semantic-parity.md` | semantic parity 独立复验 | `anthropic-responses-bridge` | high | |
| `260807-verify-systemd-code-only.md` | systemd-code-only 验收 | `systemd-runtime` | high | |
| `260807-verify-systemd-next.md` | systemd-next 独立验收 | `systemd-runtime` | high | |
| `260807-verify-systemd-rebuild-resume.md` | systemd rebuild resume 验收 | `systemd-runtime` | high | |
| `260807-verify-token-exchange-identity.md` | Copilot token 交换验收 | `UNCLASSIFIED` | high | 上游认证/token exchange，无匹配话题 |
| `260814-audit-dependency-graph.md` | import 依赖图与循环体检 | `architecture-audit` | high | 七轴线体检之一 |
| `260814-audit-duplication.md` | 重复实现体检 | `architecture-audit` | high | |
| `260814-audit-library-alternatives.md` | 自研 vs 第三方库审计 | `architecture-audit` | high | |
| `260814-audit-lifecycle-ownership.md` | 请求生命周期所有权体检 | `architecture-audit` | high | |
| `260814-audit-module-boundaries.md` | 模块划分职责错位体检 | `architecture-audit` | high | |
| `260814-audit-test-structure.md` | 测试结构独立体检 | `architecture-audit` | high | |
| `260814-audit-typing-leaks.md` | 类型化与抽象泄漏体检 | `architecture-audit` | high | |
| `260814-synthesis-gaps.md` | 七轴线综合：缝与冲突裁决 | `architecture-audit` | high | 综合报告 |
| `260814-synthesis-vs-proposal.md` | 体检对账既有提案 | `architecture-audit` | high | |
| `260816-candidate-docs-review.md` | 候选文档对账评审 | `documentation-restructure` | high | 审计 `.dev/human-controlled-docs-candidates/` 与代码是否一致 |
| `260816-count-tokens-review.md` | count_tokens 接线评审 | `count-tokens` | high | |
| `260816-lifecycle-code-review.md` | ShutdownLadder 生命周期评审 | `lifecycle-reorg` | medium | 内容是服务器进程生命周期（启停信号），非请求生命周期，与话题描述有偏差 |
| `260816-lifecycle-reorg-review.md` | 生命周期模块重组评审 | `lifecycle-reorg` | high | |
| `260817-entry-switch-review.md` | 直接运行入口切换评审 | `lifecycle-reorg` | high | 明确的「入口切换」 |
| `260817-systemd-escalation-research.md` | systemd 三级关闭信号调研 | `systemd-runtime` | high | |
| `260818-cache-control-translation.md` | cache_control→Responses 调查 | `pipeline-rewrite-parity` | high | 新提出 slug，见下 |
| `260818-ops-gap.md` | 运维面接口缺口调查 | `pipeline-rewrite-parity` | high | 新提出 slug |
| `260818-retry-gap.md` | 上游出错恢复能力差距 | `pipeline-rewrite-parity` | high | 新提出 slug |
| `260818-traffic-feature-gap.md` | 真实流量请求特性缺口 | `pipeline-rewrite-parity` | high | 新提出 slug |
| `260818-vcrpy-poc.md` | vcrpy 录制回放 PoC | `test-infrastructure` | high | |
| `260819-copilot-api-js-ir-architecture.md` | copilot-api-js IR 架构调查 | `pipeline-rewrite-parity` | high | 新提出 slug |
| `260820-claude-code-websearch-request-forensics.md` | Claude Code websearch 请求取证 | `hosted-web-search` | high | |
| `260820-client-e2e-group.md` | 客户端 e2e 测试组说明 | `hosted-web-search` | high | 首要发现即 web search 合成块验证 |
| `260820-client-timeout-forensics.md` | 客户端超时取证 256.9s | `delivery-keepalive` | high | 「超时取证」 |
| `260820-closeout-loose-ends.md` | 收尾未完成项独立枚举 | `hosted-web-search` | high | 内容以 hosted-web-search-spec 未闭合项为主 |
| `260820-closeout-verify-commits.md` | request log 提交收尾验收 | `tui` | high | 请求日志行格式（count-tokens 后缀/verdict 着色） |
| `260820-closeout-verify-docs.md` | request log 收尾独立验收 | `tui` | high | 同上 |
| `260820-copilot-api-js-reasoning-identity.md` | copilot-api-js reasoning carrier 调查 | `anthropic-responses-bridge` | high | reasoning carrier 身份/位置事实调查 |
| `260820-copilot-api-js-websearch-audit.md` | copilot-api-js web search 实现调查 | `hosted-web-search` | high | 参考实现处理 |
| `260820-deferred-d3-d5-d6.md` | 上游保活旋钮/deadline 错配调查 | `delivery-keepalive` | high | |
| `260820-downstream-keepalive-defect.md` | 下游保活 ping 节拍缺陷 | `delivery-keepalive` | high | |
| `260820-empty-text-block-copilot-api-js.md` | copilot-api-js 空 text 块处理 | `empty-text-block` | high | |
| `260820-empty-text-block-inbound-trace.md` | 空 text 块入站读写点清查 | `empty-text-block` | high | |
| `260820-empty-text-block-response-side.md` | 空 text 块响应产出侧调查 | `empty-text-block` | high | |

## 新提出的 slug

- `pipeline-rewrite-parity`：覆盖 `260818-cache-control-translation.md`、`260818-ops-gap.md`、`260818-retry-gap.md`、`260818-traffic-feature-gap.md`、`260819-copilot-api-js-ir-architecture.md`（5 个文件）。这五份都是围绕本仓库新出现的「新请求管道」（`Chain`/`DirectDriver`/`pipeline_app`）与 `copilot-api-js` 参考实现之间做特性/可靠性/运维面差距分析与架构调研，日期集中在 2026-08-18～19，且互相引用（`ops-gap`/`retry-gap`/`traffic-feature-gap` 共享同一份「新链」判定口径，`ir-architecture` 是同一系列的参考实现架构调查）。现有候选 slug 均装不下：`count-tokens` 只覆盖该管道的一个端点；`lifecycle-reorg` 只覆盖入口切换；`architecture-audit` 特指 2026-08-14 那一轮七轴线体检；`httpx2-migration`/`test-infrastructure`/`delivery-keepalive` 等语义均不贴合。

## 读不下去的文件

无。48 个文件全部完整读取（部分超长文件读取标题、背景/结论段与关键小节，未逐行通读，但均已判断出可归属的话题或确认无法归类的原因）。

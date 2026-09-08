# 分类批次 10：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：48（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260820-spec-revision-candidate-r3.md` | carrier v2＋等待式准入 spec 修订候选 r3 | `anthropic-responses-bridge` | high | |
| `260820-spec-revision-candidate-r4.md` | 同上，r4 稿 | `anthropic-responses-bridge` | high | |
| `260820-spec-revision-candidate-r5.md` | 同上，r5 稿 | `anthropic-responses-bridge` | high | |
| `260820-spec-revision-candidate.md` | 同上，初稿 | `anthropic-responses-bridge` | high | |
| `260820-system-reminder-wire-shapes.md` | 上行 body 中 `<system-reminder>` 形态普查 | `UNCLASSIFIED` | high（判不进任何现有话题） | 是 system-reminder 剥离功能的调研取证，不属于列出的任何候选话题；未见其余文件与之同题，未提出新 slug |
| `260820-test-hygiene-two-defects.md` | 两个测试卫生缺陷只读诊断（模块边界污染／keep-alive 断言过宽） | `test-infrastructure` | high | |
| `260820-unit-smoke-combined-hang.md` | `tests/unit`+`tests/smoke` 合跑会挂住 | `test-infrastructure` | high | |
| `260820-verify-server-tool-subscriber.md` | 独立验收：内置订阅者能否挡住 web_search 400 | `hosted-web-search` | high | |
| `260820-vscode-ext-websearch-audit.md` | vscode-copilot-chat 对 web search 的处理审计 | `hosted-web-search` | high | |
| `260820-websearch-400-copilot-api-js.md` | copilot-api-js 对 web search 400 的完整处置 | `hosted-web-search` | high | |
| `260820-websearch-400-our-side.md` | 本侧调查：web search 400 的上行来路 | `hosted-web-search` | high | |
| `260820-websearch-400-synthesis.md` | web search 400 根因与修法建议合成 | `hosted-web-search` | high | |
| `260820-websearch-400-vscode-ext.md` | vscode-copilot-chat 如何回避该 400 | `hosted-web-search` | high | |
| `260820-websearch-fix-v2-design.md` | web search 修法 v2：外置改写载体＋能力分流 | `hosted-web-search` | high | |
| `260820-websearch-on-responses-leg.md` | Anthropic 客户端 web search 经 Responses 上游能力合同 | `hosted-web-search` | high | |
| `260820-websearch-responses-leg-400-fix.md` | Responses 腿 web_search 400 止血修复（已取代） | `hosted-web-search` | high | |
| `260820-websearch-responses-leg-mapping.md` | Responses 腿 hosted web search 映射实现 | `hosted-web-search` | high | |
| `260820-websearch-upstream-probe.md` | web search 上游探针实测报告 | `hosted-web-search` | high | |
| `260821-copilot-api-js-websearch-response-side.md` | copilot-api-js web search 响应侧处理调查 | `hosted-web-search` | high | |
| `260821-gone-scenario-persistence.md` | `gone` 场景下落盘缺口取证（history 未接线） | `history` | high | 独立复现 `docs/agents/history-forensics/proposal.md` 的结论 |
| `260821-httpx-usage-inventory.md` | 仓库 httpx 使用面清单（迁移盘点） | `httpx2-migration` | high | |
| `260821-httpx2-api-delta.md` | httpx→httpx2 API/行为差异调研 | `httpx2-migration` | high | |
| `260821-httpx2-ecosystem-compat.md` | httpx2 生态兼容性调研 | `httpx2-migration` | high | |
| `260821-per-dialect-byte-thresholds-review.md` | 按 dialect 分档下行字节阈值独立评审 | `tui` | medium | 评审对象是 `request_log.py` 完成行着色阈值，涉及 footer/TUI 调用面排查，非典型 tui 主题但最贴近 |
| `260821-responses-leg-websearch-capability-reference.md` | Responses 腿 web search 能力处理：参考实现对照 | `hosted-web-search` | high | |
| `260821-responses-websearch-citation-evidence.md` | Copilot Responses web search 引用信息取证 | `hosted-web-search` | high | |
| `260821-review-httpx2-plan-a.md` | httpx2 迁移计划对抗性评审 A | `httpx2-migration` | high | |
| `260821-review-httpx2-plan-b.md` | httpx2 迁移计划覆盖面评审 B | `httpx2-migration` | high | |
| `260821-review-httpx2-plan-r2.md` | httpx2 迁移计划第 2 稿复评 | `httpx2-migration` | high | |
| `docs-migration-plan.md` | 文档渐进式迁移计划（`docs/2604-rewrite` → 新结构） | `documentation-restructure` | high | |
| `live-doc-truth-audit.md` | `docs/2604-rewrite` 活文档真相审计 | `documentation-restructure` | high | |
| `python-bridge-architecture.md` | Anthropic route→Responses upstream 最小架构切缝 | `anthropic-responses-bridge` | high | |
| `refs-go-bridges.md` | Go 协议桥参考调查（CLIProxyAPIPlus／awsl-maxx） | `anthropic-responses-bridge` | high | |
| `refs-python-bridges.md` | Python 近似桥接参考调查（ghc-api-py 等三仓） | `anthropic-responses-bridge` | high | |
| `refs-typescript-bridges.md` | TypeScript 参考实现调查（vscode-copilot-chat 等） | `anthropic-responses-bridge` | high | |
| `review-bridge-acceptance.md` | bridge acceptance.md 独立评审 | `anthropic-responses-bridge` | high | |
| `review-bridge-architecture.md` | bridge architecture.md 独立评审 | `anthropic-responses-bridge` | high | |
| `review-bridge-research.md` | bridge research.md 独立事实评审 | `anthropic-responses-bridge` | high | |
| `review-bridge-spec.md` | bridge spec.md 独立评审 | `anthropic-responses-bridge` | high | |
| `review-code-reasoning.md` | reasoning carrier 代码独立评审 | `anthropic-responses-bridge` | high | |
| `review-doc-migration-plan.md` | 文档重组计划独立评审 | `documentation-restructure` | high | |
| `upstream-bridge-tests.md` | Anthropic→Responses bridge 测试资产与缺口 | `anthropic-responses-bridge` | high | |
| `upstream-recent-changes.md` | copilot-api-js 近期高价值变更调查 | `anthropic-responses-bridge` | high | |
| `upstream-request-conversion.md` | Anthropic→Responses request converter 调查 | `anthropic-responses-bridge` | high | |
| `upstream-response-conversion.md` | Responses→Anthropic 非流 response converter 调查 | `anthropic-responses-bridge` | high | |
| `upstream-route-decision.md` | Anthropic 入站选择 Responses upstream 路由调查 | `anthropic-responses-bridge` | high | |
| `upstream-stream-blocks.md` | Responses stream→Anthropic SSE 调查 | `anthropic-responses-bridge` | high | |
| `verify-liveness.md` | session liveness primitive（keepalive）独立验收 | `delivery-keepalive` | high | |

## 新提出的 slug

无。

## 读不下去的文件

无。全部 48 个文件均可正常读取，无空文件、乱码或超长读不完的情况。

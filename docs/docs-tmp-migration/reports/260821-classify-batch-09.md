# 分类批次 09：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：40（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260820-empty-text-block-synthesis.md` | 空文本块 400 根因与修复综合报告 | `empty-text-block` | high | |
| `260820-external-rewrite-surface.md` | 请求/响应改写外置接入点盘点 | `hooks-subscription-migration` | high | 见「新提出的 slug」 |
| `260820-js-rewriter-architecture.md` | copilot-api-js 改写器架构调查 | `hooks-subscription-migration` | high | 作为外置改写方案的参考实现调查 |
| `260820-live-doc-correction-disposition.md` | 全局内存预算删除后 live 文档修正记录 | `anthropic-responses-bridge` | high | 修正对象是 bridge 的 architecture/research/implementation 等文档 |
| `260820-memory-budget-doc-references.md` | 全局内存预算删除后文档残留审计 | `anthropic-responses-bridge` | high | 同上，审计对象同一批 bridge 文档 |
| `260820-reasoning-item-identity-facts.md` | reasoning item 身份的生产历史事实调查 | `anthropic-responses-bridge` | high | 被后续 reasoning carrier v2 规格评审引用为证据 |
| `260820-research-pipeline-idle-timeout.md` | 新 pipeline 接入上游 idle timeout 现状调查 | `delivery-keepalive` | high | |
| `260820-research-upstream-timeout-wiring.md` | upstream_request_timeouts 接线调查 | `delivery-keepalive` | high | |
| `260820-review-blank-text-subscriber.md` | 评审：空块剥离落点搬到订阅者 | `empty-text-block` | high | synthesis 报告第 6 节引用的第三轮评审 |
| `260820-review-count-tokens-shared-pipeline.md` | 评审：count_tokens 共享请求管道 | `count-tokens` | high | |
| `260820-review-downstream-keepalive-defect.md` | 评审：下游保活缺陷证伪 | `delivery-keepalive` | high | |
| `260820-review-final-and-probe.md` | 评审：空块修复最终提交与探针方法论 | `empty-text-block` | high | synthesis 第五轮评审 |
| `260820-review-history-flattening.md` | 评审：历史 server-tool blocks 摊平 | `hosted-web-search` | high | |
| `260820-review-hosted-web-search-spec.md` | 评审：hosted-web-search-spec 规格文档 | `hosted-web-search` | high | |
| `260820-review-keepalive-doc-fixes.md` | 评审：保活文档修订本身 | `delivery-keepalive` | high | |
| `260820-review-keepalive-rulings.md` | 评审：保活裁决落实与文档一致性 | `delivery-keepalive` | high | |
| `260820-review-pipeline-idle-timeout.md` | 评审：新 pipeline idle timeout 实现核验 | `delivery-keepalive` | high | |
| `260820-review-principle-facts.md` | 事实核查：project-review-principles 某条原则 | `project-review-principles-skill` | high | 见「新提出的 slug」 |
| `260820-review-principle-placement.md` | 评审：复查原则第五条的归属与形态 | `project-review-principles-skill` | high | |
| `260820-review-project-review-principles-skill.md` | 评审：project-review-principles skill 正文 | `project-review-principles-skill` | high | |
| `260820-review-request-id-and-count-prefix.md` | 评审：请求日志 request id 与 count-tokens 前缀显示 | `tui` | high | slug 定义明确覆盖「请求日志行…count-tokens 行」 |
| `260820-review-responses-token-counting.md` | 评审：count_tokens 翻译路径与估算器 | `count-tokens` | high | |
| `260820-review-s1-upstream-ownership.md` | 评审：stream_delivery 上游所有权与关闭语义 | `delivery-keepalive` | high | 与 shield/S1-wiring 同一批改动 |
| `260820-review-s1-wiring.md` | 评审：弃流关闭确定性改动接线影响 | `delivery-keepalive` | high | |
| `260820-review-server-tool-subscriber.md` | 评审：server-tool 剥离订阅者 | `hosted-web-search` | high | |
| `260820-review-session-closeout.md` | 会话收尾产物独立复核 | `UNCLASSIFIED` | high | 会话收尾/交接流程记录，非产品话题 |
| `260820-review-shield-stopasynciteration.md` | 评审：`_events_with_ping` 去掉 shield 修复 | `delivery-keepalive` | high | |
| `260820-review-spec-revision-candidate-r2.md` | 复评：spec/acceptance 修订候选 r2 | `anthropic-responses-bridge` | high | reasoning carrier v2 + 等待式准入规格修订 |
| `260820-review-spec-revision-candidate-r3.md` | 复评：spec/acceptance 修订候选 r3 | `anthropic-responses-bridge` | high | |
| `260820-review-spec-revision-candidate-r4.md` | 复评：spec/acceptance 修订候选 r4 | `anthropic-responses-bridge` | high | |
| `260820-review-spec-revision-candidate-r5.md` | 复评：spec/acceptance 修订候选 r5（pass） | `anthropic-responses-bridge` | high | |
| `260820-review-spec-revision-candidate.md` | 评审：spec/acceptance 修订候选（r1） | `anthropic-responses-bridge` | high | |
| `260820-review-synthetic-start-fix.md` | 评审：deadline 合成物改为只发 message_start | `empty-text-block` | high | synthesis 第二轮评审 |
| `260820-review-unconditional-blank-strip.md` | 评审：无条件剥离空白 text block | `empty-text-block` | high | |
| `260820-review-upstream-timeout-wiring.md` | 独立评审：upstream_request_timeouts 接线修复 | `delivery-keepalive` | high | |
| `260820-review-websearch-fix-second-opinion.md` | 对照评审：Responses 腿 web_search 400 止血修复 | `hosted-web-search` | high | |
| `260820-sanitize-family-migration-status.md` | `anthropic/sanitize/` 家族在新链路去向排查 | `hooks-subscription-migration` | high | |
| `260820-server-timeout-forensics.md` | 服务端取证：客户端 256.9s 超时事故 | `delivery-keepalive` | high | 与 downstream-keepalive-defect 同一事故取证链 |
| `260820-smell-survey-streaming-pull.md` | 代码怪味普查：上游拉取/保活/清理 | `delivery-keepalive` | high | |
| `260820-spec-revision-candidate-r2.md` | 候选 r2 正文：carrier v2 + 等待式准入规格修订 | `anthropic-responses-bridge` | high | |

## 新提出的 slug

- `hooks-subscription-migration` —— 覆盖 `260820-external-rewrite-surface.md`、`260820-js-rewriter-architecture.md`、`260820-sanitize-family-migration-status.md`（3 个文件）。三份文件调查的是同一个架构问题：把请求/响应改写能力（`src/app/hooks/`、`anthropic/sanitize/` 家族）从 legacy 链路吸收进新 pipeline 的订阅机制（`SubscriberRegistry`），包括接入点盘点、参考实现 copilot-api-js 的改写器架构对照、以及 sanitize 家族被排除在新链路之外究竟是有意设计还是迁移残留。这是一个独立于具体 400 修复（`empty-text-block`、`hosted-web-search` 是两次具体生产故障的根因与修复）的架构设计调查线，也不属于 `anthropic-responses-bridge` 主产品链路的规格/实现范畴（它讨论的是横切的扩展机制，不是 Anthropic→Responses 桥接本身）。三份文件互相引用、结论互相印证，覆盖数满足 ≥3 的门槛。

- `project-review-principles-skill` —— 覆盖 `260820-review-principle-facts.md`、`260820-review-principle-placement.md`、`260820-review-project-review-principles-skill.md`（3 个文件）。三份都是对项目自建 skill `.claude/skills/project-review-principles/SKILL.md`（及其中某条原则）的评审/事实核查，评审对象是方法论文档本身而非产品代码或产品文档，与既有候选 slug（均为产品功能或流程话题）都不匹配。三份文件评审的是同一个 skill 文件的相邻版本，互相引用彼此的处置记录，覆盖数满足 ≥3 的门槛。

## 读不下去的文件

无。40 个文件全部可正常打开阅读，无空文件、乱码或因超长而放弃的情况（长文件均通过截取标题、结论段、评审结论/发现小节完成判断）。

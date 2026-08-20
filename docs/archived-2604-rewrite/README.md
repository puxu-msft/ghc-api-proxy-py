# `2604-rewrite`（已归档，仅供参考）

**用户裁定（2026-08-20）：这里整体过期。** 它是早期由 peer 会话编写的 **`copilot-api-js` 学习笔记**——对参考项目的阅读理解与据此设想的重写方案，不是本项目的设计规范，也不是对已实现行为的描述。

原位置 `docs/2604-rewrite/`，42 份文件，逐字节未改地搬到这里。

> **不要把这里的任何一句当作裁决、契约或当前行为。** 它没有权威地位：既不是用户亲笔（那是主仓库 `docs/.human-controlled/`），也不是从代码核对出来的（那是 `docs/agents/<topic>/` 与代码本身）。

## 为什么这条裁决重要，而不只是「换个地方放」

这个目录被当成权威引用过。搬移时清点到**主仓库有 53 个文件、共 280 处引用指向它**，其中若干处不是「链接」而是「引证」，例如：

- `docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md:276` —— 「这与 `docs/2604-rewrite/tool-use.md:23` 的**既有裁决**一致，本规格不重开」
- `docs/agents/anthropic-responses-bridge/architecture.md:492` —— 「不得借新增 journal 隐式重裁 `docs/2604-rewrite/history-system.md` 的轻量终态一次写入设计」
- `docs/agents/history-forensics/proposal.md:253` —— 「`docs/2604-rewrite/history-system.md` 的**设计明写** `busy_timeout = 5000`。实现与设计文档对不上」

按本裁决，这些引证的前提不成立：被引的不是裁决、不是设计规范，是学习笔记。**「实现与设计文档对不上」这类判断需要重新做**——对不上的可能恰恰是笔记。这些文件属于其它话题、且有并行会话在其上工作，本次没有改动它们，只在此记录。

## 谁引用了这里（2026-08-20 清点）

| 层 | 位置 | 处理 |
|---|---|---|
| 仓库门面 | `README.md`、`TODO_CURRENT.md` | **已改**，见下 |
| 其它话题的活文档 | `docs/agents/anthropic-responses-bridge/`（4）、`delivery-keepalive/`（9）、`documentation-restructure/README.md`（2）、`history-forensics/proposal.md`（1）、`systemd-runtime/plan.md`（1） | **未动**：属于其它话题、有并行会话在写；且问题是引证前提而非链接，需各自话题重判 |
| 历史快照 | `docs/tmp/**`（约 40 份 agent 报告）、`docs/agents/documentation-restructure/archive-260808/plan.md`（105 处）、`exp/phase2-acceptance/`（8）、`verification/`（1） | **未动**：写下时是准确的，是当时的记录，断链不改变其历史价值 |

`documentation-restructure` 那份归档计划整份是**关于如何把这个目录重组成活文档**的。本裁决把它的输入判为过期笔记，所以那份计划的前提也随之失效。

## 内容

42 份，含 `plan/` 与 `lib-survey/` 两个子目录。原样保留，未加 banner、未改一字——加注解等于在学习笔记上再叠一层推断。

其中 `lib-survey/HANDOVER.md` 曾作为「库调研交接入口」被项目记忆引用；该记忆已改指向这里的新路径，但它同样落在本裁决的范围内，接手前先判断它还成不成立。

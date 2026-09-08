# 分类简报：`docs/tmp/` → `.dev/docs/`

本文件是派给分类 agent 的共享上下文。**只读**：分类 agent 除了自己那一份报告文件之外，不得修改仓库里的任何东西，不得移动/删除任何文件，不得提交。

## 背景事实（已核实，不必重新调查）

- 仓库根：`/home/xp/src/ghc-api-proxy-py`
- `docs/tmp/` 下有 417 个 `.md`，是 2026-08-06 起累积的 agent 报告、评审、验收、取证、调研原件。其中 61 个被主仓库 git 跟踪，其余未跟踪。
- `.dev/` 是独立仓库，在主仓库 `.gitignore` 里。它存放开发过程状态。布局约定见 `.dev/README.md`。
- CLAUDE.md 已由用户授权：「最新的开发文档位于 `.dev/docs/` 目录下。曾经用户选用过 `docs/agents/`，你可以逐步按主体迁移。」
- 本次任务只做**分类判断**与随后的搬迁，不做知识蒸馏、不重写报告内容。

## `.dev/docs/` 现有话题（真实存在，不要臆造）

```
.dev/docs/archived-2604-rewrite/        早期 copilot-api-js 学习笔记，用户 2026-08-20 裁定整体过期
.dev/docs/cli-commands/debug-models/    debug-models 子命令
.dev/docs/graceful-shutdown/client-side/ 关闭信号 → 进程退出（客户端侧）
.dev/docs/history/                      请求历史落盘/取证（含 archive-260807-legacy-chain/）
.dev/docs/sync-refs/sxwxs-ghc-api/      对照外部参考实现
.dev/docs/tui/                          请求日志与实时 footer（含 5 个 archive-*/）
.dev/docs/upstream/h2-goaway/           上游 HTTP/2 GOAWAY
```

主仓库 `docs/agents/` 下仍有的话题目录（尚未迁入 `.dev`）：
`anthropic-responses-bridge`、`delivery-keepalive`、`deployment-systemd`、`documentation-restructure`、`httpx2-migration`、`service-cutover`、`systemd-rolling`、`systemd-runtime`。

## 候选目标话题（可用，也可提出新的）

分类时优先复用下面这些 slug。**允许提出新 slug**，但必须说明理由，且新 slug 要能覆盖 ≥3 个文件；覆盖不足 3 个的，宁可判 `UNCLASSIFIED`。

| slug | 覆盖什么 |
|---|---|
| `anthropic-responses-bridge` | Anthropic Messages 入站 → OpenAI Responses 上游这条主产品链路的规格/架构/实现/验收/评审。包含 request converter、response converter、stream blocks、reasoning carrier、liveness、happy path、semantic parity 等 |
| `systemd-runtime` | systemd 单元、socket activation、user manager、安装器、滚动重启 |
| `service-cutover` | 从既有 `copilot-api-js`（4141）切换过来的计划、备份端口冒烟、割接清单 |
| `documentation-restructure` | 文档重组/迁移计划、live 文档真相审计、docs/tmp 蒸馏矩阵、文档链接审计 |
| `architecture-audit` | 2026-08-14 那一轮七轴线独立体检（依赖图、重复实现、库替代、生命周期所有权、模块边界、测试结构、类型泄漏）及其综合 |
| `delivery-keepalive` | 下游保活、ping 节拍、deadline 合成物、上游 idle timeout 接线、超时取证 |
| `hosted-web-search` | web search / server tool 的 400、能力合同、映射实现、外置改写载体、各参考实现的处理 |
| `empty-text-block` | `text content blocks must be non-empty` 那条 400 的取证与修复 |
| `httpx2-migration` | httpx → httpx2 的盘点、API 差异、生态兼容、迁移计划评审 |
| `count-tokens` | `/v1/messages/count_tokens` 端点、共享请求管道、token 估算 |
| `lifecycle-reorg` | 请求生命周期模块重组、入口切换 |
| `test-infrastructure` | cassette/vcrpy、测试组划分、测试卫生、unit+smoke 合挂 |
| `tui` | 请求日志行、footer、count-tokens 行（已有 `.dev/docs/tui/`） |
| `history` | 请求历史落盘与取证（已有 `.dev/docs/history/`） |
| `UNCLASSIFIED` | 判不进上面任何一个，或跨太多话题、或是一次性杂务 |

## 判据

1. **按内容判，不按文件名判。** 文件名里的 `review` / `audit` / `verify` 只说明它是什么体裁，不说明它属于哪个话题。必须打开文件读。
2. **一个文件只归一个话题。** 跨话题的，按「它评审/取证的那个被改对象属于谁」定；仍判不了就 `UNCLASSIFIED`，并在备注里写出它横跨了哪几个。
3. **`UNCLASSIFIED` 不是失败。** 用户明确要求「保持未分类移入 `.dev/docs/tmp`」。判不准就判它，比硬塞进一个话题好。
4. **置信度必须给。** `high` = 读完正文能直接说出它属于哪个话题；`medium` = 靠上下文推断；`low` = 猜的（`low` 一律降级为 `UNCLASSIFIED`）。

## 输出格式

写入你被指定的报告文件，正文是一张表，**每个被分配的文件恰好一行，不得遗漏、不得合并**：

```markdown
# 分类批次 NN：`docs/tmp/` → `.dev/docs/`

分类时间：2026-08-21　　批次文件数：N（与下表行数一致）

| 文件 | 这是什么（≤25 字） | 话题 slug | 置信度 | 备注 |
|---|---|---|---|---|
| `260807-xxx.md` | 某某评审 R3 | `anthropic-responses-bridge` | high | |
```

表后加一节 `## 新提出的 slug`（没有就写「无」），逐条写 slug、覆盖哪些文件、为什么现有 slug 装不下。

再加一节 `## 读不下去的文件`（没有就写「无」）：文件为空、乱码、或超长读不完的，逐个列出并说明。

**不要在回复里复述这张表。** 回复只给：报告文件路径、处理了多少文件、各 slug 的计数、以及 `UNCLASSIFIED` 的数量。

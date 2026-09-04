# `completed` 与 client actions 实施计划评审处置

日期：2026-09-04

对象：[`../plan.md`](../plan.md) §10

首轮 reviewer 原报告位于其隔离 worktree 的 `review-completed-client-actions-plan.md`。结论：0 blocker、3 major；全部采纳并已修订。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| F01：计划把未获本轮 Spec 覆盖的 `response.incomplete` 送进新 terminal-status renderer | 采纳 | C | Direct passthrough adapter 只在 `response.completed` 填新 facts；`response.incomplete` 保持 `terminal_status=""`、`client_actions=[]`、completeness false，继续由 shared reader 产出黄色 `max_tokens`。新增 producer scope 与 renderer scope 回归 |
| F02：full regression 排在会修改候选的 implementation review 之前 | 采纳 | C | 顺序改为 targeted candidate → independent review、处置与复评 → 受影响 targeted controls → 共识后的唯一一次 Ruff、Pyright、full regression → source commit。评审修复不会让“最终”证据陈旧，也不会被迫重复 full suite |
| F03：新文件没有显式 `git add`，pathspec commit 无法提交 unknown-to-Git 路径 | 采纳 | C | Source 与 `.dev` 两个提交都先对同一精确 pathspec 执行 `git add --`，再做 scoped cached audit 和 pathspec `git commit -F`；全局 cached audit 只观察并保留同伴 staged entries，不 reset、restore 或裸 commit |

## 第二轮复评

第二轮 reviewer 原报告位于其隔离 worktree 的 `review-completed-client-actions-plan-round2.md`。结论：**pass，可执行；F01～F03 全部 closed，0 blocker、0 major、0 minor**。复评确认 completed-only producer、incomplete legacy renderer、review-before-final-suite 顺序，以及 source 和 `.dev` 两侧 exact-pathspec add/audit/commit 均已闭合；未重开其它计划范围。

未采纳项：无。

复评范围：F01～F03 的原发现、整改后的 Task 10.2、10.4 与 10.6，以及这些改动相邻的 direct-only producer、最终验证顺序和 source/docs 两个新文件提交路径。
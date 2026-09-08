# Direct buffered Chat Completions 实施进度账本

状态：进行中
状态日期：2026-09-06
编排会话：`buffered chat completions`／job `3db40195`
源码基线：`f97d243f9431d836861ce5e9938605df56b37478`
权威计划：[plan.md](plan.md)，当前SHA-256 `b2577401444304f0b0d66c3ad197a486230ee6fd6d552e3c322989339ffae73d`；Task 2 review驱动的Task 2／3接口修订正做定向plan复评
权威行为：[`../direct-passthrough/spec.md`](../direct-passthrough/spec.md) §5.4／§9.3／§10、[`../error-envelope/spec.md`](../error-envelope/spec.md) §5.1／§8／§10.2、[`../tui/spec.md`](../tui/spec.md) Chat provider observation schema
文档分支：`dotdev-direct-buffered-chat-design`，当前提交 `b7ffe3e623750db4532ceb15fbd18bdf221f8fd0`

本项目把`.dev`持久化在独立dotdev lineage，不能与source commit处于同一个Git commit。适配进度协议的方法是：每个source semantic commit完成后立即更新本账本，写入该source commit及剩余项，再以exact paths提交到本任务dotdev分支；两次提交构成同一checkpoint。Source与dotdev都不推送。

## 任务列表

| Task | 状态 | Owner | 依赖 | 交付 |
|---|---|---|---|---|
| 1. Closed Chat capability与typed refusal | done | agent `ad77363b71744709c` | 无 | Main `5995bbe`；archive `3897912`；review clean；147 passed＋Ruff／Pyright通过 |
| 2. Raw SSE frame与Chat facts | done | agents `afc6e2ab44a22bc36`、`a84ab1d288fe4d046` | Task 1完成 | Main `92ac564`；archive `bfd9c2d`；review clean；128 passed＋Ruff／Pyright通过 |
| 3. Single-attempt collector | WIP | 待派implementer | Task 2完成 | Collector、memory account、typed ending／decision |
| 4. DirectDriver pre-success seam | pending | 未分配 | Tasks 1、3 | Response lease/handoff、prepared body retry、event limiter、pending finalizers |
| 5. Provider透明与non-stream adaptation | pending | 未分配 | Tasks 1～4 | Provider migration、ChatSendPlan、adapted JSON与raw/projection handoff |
| 6. Post-header direct streaming runner | pending | 未分配 | Tasks 2～5 | Transaction runner、prepared reopen、keepalive/cap/deadline/candidate selection |
| 7. Chat observation/TUI/schema | pending | 未分配 | Tasks 2、5、6 | Final candidate observation、JSONL/TUI与deferred closure |
| 8. Merged-state验收与收尾 | pending | 未分配 | Tasks 1～7 | Integration controls、full checks、merged review、status/closeout |

## 当前动作

Task 1已集成到main `5995bbe0ac1885482e4976975c3b74d196cb7b11`。Task 2经四轮fix由main `92ac5643985d0b28fb1d94bbce3d5eb24abcfc44`集成，reviewed source存于`archive/260906-direct-chat-facts`；14项finding全部关闭。Task 3从`92ac564`开始，实施single-attempt collector与统一logical memory account。

## 计划与实际差异

当前无。出现偏离时记录被证伪的计划句、证据、实际做法和影响，不改写历史行。

## 未做与不阻塞项

- CodeBuddy真实`stream:false` P6未运行，按用户裁决保留compatibility provenance；不阻塞本次实现。
- Translated Chat→Anthropic multi-choice projection仍在[deferred.md](deferred.md) D-2；不阻塞direct路径。
- 生产`4141` cutover未授权，不在本任务范围。

## Peer attribution

- `.dev/docs/tui/spec.md` 当前combined file同时含本任务的direct buffered Chat observation schema与peer会话 `tui function-call coalescing` 已完成的Responses action display grouping条款。Peer于2026-09-06明确请求本任务dotdev分支原样持久化该combined file；Responses grouping hunk归该peer会话，本任务不改写、不冒领，也不纳入其余grouping design/plan/reports/tracking。

## 每个checkpoint必须记录

1. Source commit SHA与exact paths。
2. 本任务targeted test／Ruff／Pyright结果及其证据上限。
3. 剩余项与第一个未闭合gate。
4. 在途意图和已否决路线；没有也写“无”。
5. 对应dotdev commit SHA。

# Raw capture v23 收尾报告

日期：2026-09-09

## 交付结论

raw-capture 的主体功能和本轮发现的关键缺口已经在当前共享工作树实现：通过 SQLite 持久化规则按 provider、实际发送 model、session 和可选 agent 选择请求；命中请求保存入站、实际 upstream、实际 client body；文件使用 CBOR Sequence 与独立 zstd frame；失败 attempt、proxy timeout、observed-empty、count cleanup、writer/quota/poison 和普通诊断安全边界均已按 ACTIVE v23 收敛。

本结论的范围是当前共享工作树中的 raw-capture 产品面，不等同于全量项目测试、真实 Copilot canary、部署验证或生产切换。最终 review chain 由 durable `.dev/docs/raw-capture/reports/raw-capture-final-rereview-2026-09-09.md`（RC-FINAL-01 至 RC-FINAL-03 的 source/test re-review）和 `.superpowers/sdd/plan-f8086b646635/final-rereview-final.md`（RC-FINAL-04 的 current ledger/package binding）组成；旧的 `.superpowers/sdd/plan-f8086b646635/final-review.md` 和中间 re-review 文件保留为 point-in-time 过程证据，不是当前 verdict。这个 chain 的最终复评均为 pass，但仍不外推为全量系统验收。

## 代码交付面

本轮 raw-capture 相关实现和测试仍位于共享主工作树，尚未提交：`src/app/observability/raw_capture.py`、`src/app/observability/debug_capture.py`、`src/app/pipeline/direct_driver/base.py`、`src/app/pipeline/driver.py`、provider HTTP/SDK client 接缝、`src/app/server/routes/inference.py`、`src/app/server/routes/ops.py`、配置与 Chain 装配，以及对应 unit/component/integration tests。

共享工作树同时包含不属于本轮的 peer WIP，包括 provider、pipeline、protocol、配置示例和容器相关改动；本轮没有使用宽泛 staging、没有 reset、没有提交、没有 push，也没有触碰现有 4141 服务或执行 cutover。

## 规格与文档

- 行为权威：`.dev/docs/raw-capture/spec.md` ACTIVE v23。
- 实施计划：`.dev/docs/raw-capture/plan.md`，已改写为已执行状态，并明确 shared-worktree integration 暂缓。
- Finding 处置账：`.dev/docs/raw-capture/raw-capture-review-disposition.md`，Task 1–4 findings 已关闭。
- Deferred：`.dev/docs/raw-capture/deferred.md`，D-2 仍保留；D-1 已由实际安全 warning 修复接管。
- 收尾证据清单：`.dev/docs/raw-capture/closeout-manifest-20260909.md`。
- 过程报告和复评：`.dev/docs/raw-capture/reports/` 与 `.superpowers/sdd/plan-f8086b646635/` 下的 task reports/reviews；这些 point-in-time 原文未被改写。
- RC-FINAL-01–03 durable source review：`.dev/docs/raw-capture/reports/raw-capture-final-rereview-2026-09-09.md`；它保留 source/test re-review 的 point-in-time scope。
- RC-FINAL-04 current binding：`.superpowers/sdd/plan-f8086b646635/final-rereview-final.md`；它绑定 current progress 与六个 applied source/test/disposition snapshot。旧 `final-rereview.md`、`final-rereview-e8c.md` 和 `final-review.md` 保留为历史过程证据。

本次未使用 Claude Plan Mode，因此没有 `~/.claude/plans/<random>.md` 需要落盘；实施计划的常驻载体是 `.dev/docs/raw-capture/plan.md`。

## 验证证据

以下是本轮新产或按 scoped review 复用的证据，不能外推为全量系统通过：

- Raw capture 和 provider/timeout/count 相关 unit/component 集合：`139 passed`，使用 Task 6 scoped E1 命令；另有 Task 1–4 各自独立 review 的 focused tests。
- Pipeline capture controls：`8 passed`，覆盖规则持久化与选择、retry、cleanup failure、rejection、unmatched、timeout wire body 和安全异常投影。
- 管理 API routes：`45 passed`。
- 最终修复后的 affected controls：raw capture `26 passed`、request completion `54 passed`、ASGI/completion selection `9 passed`、upstream projection selection `2 passed`；这些数字和命令保存在 `.superpowers/sdd/plan-f8086b646635/task-6-fix-report.md`，由当前 final review 绑定，不作为全量数字。
- Ruff：raw-capture scoped target `All checks passed`，命令和完整文件集合见 Task 6 fix report及 final review evidence；本轮未运行 `ruff format`。
- Pyright：最终修复涉及的 production/completion targets `0 errors, 0 warnings, 0 informations`；完整 raw-capture target 仍有既有 test-only `tests/unit/observability/test_raw_capture.py` 对 `store._queue` 的 `reportPrivateUsage`，没有把它写成 production error。
- 全量回归：`uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80` 运行过一次，结果 `3509 passed, 2 skipped, 11 failed, 327 warnings`，coverage `90.17%`，退出 1。失败集合包括 delivery replay/replacement、配置示例与 catalog、SSE warning 旧断言等共享 peer WIP/既有范围；它不是 raw-capture scoped pass，也没有被隐藏。最终 scoped raw-capture controls 仍按上列命令单独通过。

## 收尾范围与临时态

- 冻结范围：仓库主工作树 `/home/xp/src/ghc-api-proxy-py`，当前 HEAD 的日期与主题为 `2026-09-08 fix: accept null Responses reasoning content`；工作树与 index 均有大量 peer WIP。
- linked worktree：冻结时仓库登记了多棵 peer/历史 agent worktree；本轮没有删除、切换或修改它们。它们不属于本 raw-capture change 的交付面。
- 后台 agent：Task 1–5 implementer/reviewer 与 Task 6 final reviewer 均已回执；没有仍在写本主题文件的活跃 child task。
- Job scratch：`/home/xp/.claude/jobs/43cf5eb9/tmp` 的 raw-capture 过滤枚举为空，manifest 中已明确记录。
- Session temp：`/tmp` raw-capture/task/ghc-task2 过滤集合共 2534 个文件和 3 个符号链接；本轮没有执行删除，因为没有独立 manifest deletion review，也没有用户要求破坏性清理。它们保留给 harness/session 生命周期管理；durable conclusions 已在 reports、fix report、final review 和本 manifest 中落盘。
- 非文件候选：旧 JSONL 路线、全局 quota、attempt completeness 混淆、timeout request body 遗失、cleanup boundary、safe ordinary projection、管理 API错误 envelope 和各测试 oracle 缺口均已进入 spec revision、disposition 或 deferred；本轮没有新增 skill/rule/memory资产。

## Git 与下一步

本轮 integration decision 是 **keep shared dirty worktree**：不创建 broad commit，不触碰 peer WIP，不 push，不 merge，不删除 branch/worktree。原因是 raw-capture 改动跨多个与 peer 同时修改的文件，当前 shared index 不能证明只含本轮 hunks；用 pathspec 直接提交会有带入或遗漏风险。后续若要提交，应在 peer WIP 收敛后重新冻结范围，使用 filtered patch 或独立 worktree 构造只含 raw-capture 语义单元的提交，并重新跑 scoped review；这不是本轮已执行的动作。

没有下一条必须立即执行的命令。若下一棒要继续，先读取本报告、`progress.md`、`spec.md` 和 `raw-capture-review-disposition.md`，不要把全量回归失败误读成 raw-capture scoped failure，也不要把本报告的 scoped conclusion 外推为真实 upstream 或部署通过。

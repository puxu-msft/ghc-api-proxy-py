# `completed` 与 client actions 上下文着色 closeout

状态：终态记录
日期：2026-09-04

## 交付

- 主仓 `main` 已提交 2026-09-04 `feat: report contextual Responses completion status`。Responses 流式直连现在从 terminal `response.output` 记录 typed client actions 与 snapshot completeness；`completed` 只有在分类完备且 action-free 时绿色。
- `.dev` 已提交规格、实施计划与实现评审处置；本 closeout 与最后两处机械同步尚待本轮最终 `.dev` 提交。
- 没有推送、发布、切换服务或触碰生产 `4141`。

## 范围与保持不变项

本切片只覆盖原生 Responses streaming direct 的 `response.completed`。`response.incomplete` 继续显示黄色 `max_tokens`；translated Responses 继续使用 legacy stop reason；nonstream `/responses` 仍无 whole-body reply reader。开放项继续由 [`../../tui/deferred.md`](../../tui/deferred.md) 第 0 条和第 1 条持有，没有因本切片结案。

Wire event、framer、continuation 与 terminal delivery 未改写。Done-side `_saw_client_action` 继续只服务 buffering 与下游 stop-reason 合成；action list 与 completed 颜色只读 terminal snapshot。

## 验证

最终稳定候选按顺序运行：

1. `uv run ruff check src tests` → clean。
2. `uv run pyright src tests` → 0 errors、0 warnings、0 informations。
3. `uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80` → 2213 passed、2 skipped、coverage 91.29%。

此前的相关 merged-state suite 在 mutation restore 前后均为 367 passed。9 个单变量 controls 全部按目标变红，覆盖 present-empty item 被跳过、status-only green、all-uncoloured、empty-actions-as-complete、missing-output-as-complete、all-unknown、drop-unknown、reverse-terminal-order、terminal-snapshot-replaced-by-done；恢复后核心 61 passed，4 份 clean candidate snapshots 逐字相等。

这些 mock 与 controls 证明本代理的 collector、trace、record 与 renderer 接线，不冒充真实 Copilot 本轮实况；用户提供的 `completed + function_call/custom_tool_call` 是产品合同来源。

## 评审

- Spec：六轮窄评审收敛到 0 blocker、0 major，可定稿；处置见 [`260903-completed-client-actions-spec-review-disposition.md`](260903-completed-client-actions-spec-review-disposition.md)。
- Plan：两轮评审，首轮 3 major 全部采纳，复评 0 blocker、0 major；处置见 [`260904-completed-client-actions-plan-review-disposition.md`](260904-completed-client-actions-plan-review-disposition.md)。
- Implementation：首轮 1 major，修复 present-empty `{}` 与 absent item object 的状态混淆；复评 0 blocker、0 major、0 minor，可提交。Closeout docs review 为 0 blocker、0 major、1 minor，版本号 v20 → v21 已采纳；处置见 [`260904-completed-client-actions-implementation-review-disposition.md`](260904-completed-client-actions-implementation-review-disposition.md)。
- Final closeout report：0 blocker、0 major、1 minor，终态报告可交付；资产查重措辞已按 finding 收窄为补充候选而非“既有记忆已覆盖”。

未采纳路线及理由均已进入上述 dispositions；当前没有 open 或 disputed finding，也没有本会话自裁驳回而未经第三方查看的 finding。

## 活文档与归档

常驻权威为 [`../spec.md`](../spec.md) §7.1、§10，[`../../tui/spec.md`](../../tui/spec.md)「着色规则」「描述回复的用词跟随上游」「验收」，以及 [`../plan.md`](../plan.md) §10。正控扫描命中 `terminal_status` 与 2026-09-04 source subject；针对 `待本轮实现`、`可观测切片已定稿待实现`、`completed.*待实现` 的 live-doc 扫描无命中。

不归档本轮 Specs 与 plan：Specs 仍定义外部可观察合同，plan 仍承载 direct-passthrough 的其它开放切片。未使用 Claude Plan Mode；计划由项目现有 living plan 承载。

## 临时态

`$CLAUDE_JOB_DIR/tmp` 写 marker 前有 12 项，写后 13 项；`fd --hidden --no-ignore` 与 Python `os.walk` 的普通文件和符号链接集合逐项一致。处置标记位于 `$CLAUDE_JOB_DIR/tmp/CLOSEOUT-DISPOSITION.md`。

本轮未为不可逆删除另派 manifest review，因此执行零删除；4 份 snapshots、4 份 commit-message files、mutation runner、3 份 spec baselines 与 marker 全部就地留给 harness 随 job 过期。没有任何产品结论仅由这些临时文件承载。

## Git 与无关 WIP

冻结-1：主仓 `main`，2026-09-04 `feat: report contextual Responses completion status`；`rev-parse` 回执位于 closeout 阶段 1 的仓库冻结命令。Source 提交后 13 个 source/test 路径干净。

冻结-2：`.dev`，2026-09-04 `docs: record contextual completed status implementation`；`rev-parse` 回执位于同一冻结命令。最后 closeout 文档提交完成后需重新记录 `.dev` 终态。

主仓既有用户控制文档、Docker 文件和 HTTP/2 实验目录保持原样；`.dev` 既有 httpx2 migration、delivery keepalive、graceful shutdown、tmp reports、retry/continuation reports 与 verification WIP 保持原样。共享 index 在冻结时均为空，本轮提交只使用精确 pathspec。

本会话没有创建 feature branch 或自有 worktree；工作直接集成到 `main`，因此没有 merge/keep/discard 分支决策。Reviewer worktrees 属 harness 评审会话，本轮不移除。没有 push。

## 可复用资产

本轮没有新增通用 rule、skill 或 agent soul。`terminal status` 与 `client action` 分槽已由既有“两项同时为真的事实需要两个槽”记忆覆盖；事实三态与 policy bool 分离已由现有 strategy/orchestration 技艺覆盖。`if not value` 把 present-empty 与 absent 合并是既有“缺席不可读”记忆的补充候选，本轮只登记、不安装；本次项目实例与可执行判据已经进入 living Specs、typed records、tests 和 implementation disposition，不会随会话丢失。

## 下一步

当前请求无需用户再执行命令。后续若要让 translated 或 nonstream Responses 同样显示权威 terminal status，应从 TUI deferred 第 0 条或第 1 条另开切片，不能把本轮证据外推过去。

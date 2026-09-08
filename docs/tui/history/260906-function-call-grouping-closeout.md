---
report_id: function-call-grouping-closeout-260906
status: candidate-final
completed_at: 2026-09-06
final_review: reports/260906-function-call-grouping-closeout-review.md
---

# Responses client-action grouping 收尾报告

## 交付

TUI completion line 现在把 visible segment sequence 中连续、同 raw item type、具名且 `REQUIRED` 的 client actions 合并为一个字段，并保留名称顺序与重复。用户报告的 `function_call(TaskCreate) function_call(Bash)` 现在输出为 `function_call(TaskCreate,Bash)`。

Production、unit 与 integration 三文件已由 2026-09-06 的 `fix: coalesce adjacent response actions in logs` 提交承载：

- `src/app/observability/request_log.py`
- `tests/unit/observability/test_request_log.py`
- `tests/int/test_pipeline_app.py`

当前分支为 `main`，相对 `origin/main` ahead 2；本轮只拥有上述提交，前一条 `feat: model Chat response capabilities` 来自并行工作。未 push、未创建 PR、未执行 production cutover。

## 根因与修复

Merge `f97d243` 在整合 observability 两条开发线时保留 reasoning accumulator，却删除 action accumulator，并同步把 tests 的 grouped oracle 改成逐项显示。代码仍可运行、tests 仍绿，因此回归被误写成新合同。

修复没有恢复两套相互 flush 的 pending state。`request_log.py` 现在先把 provider items 投影成 `_NamedAction`、`_Reasoning`、`_UnknownAction` 与 `_AnonymousAction` typed segments，再由 `_coalesce_response_display_segments()` 做 total pairwise reduction，最后由 `_render_response_display_segment()` 编码和渲染。只有 `_NamedAction + same raw_type` 与 `_Reasoning + same kind` 两种组合可合并；其它可见 variant 默认是 barrier。Rich observation 与 legacy fallback 共享 `_action_display_segment()`、reducer 与 renderer，contextual `completed` 仍直接读取完整 output facts。

行为权威已更新到 `.dev/docs/tui/spec.md`，内部机制在 `.dev/docs/tui/design.md`，终态执行记录在 `.dev/docs/tui/function-call-grouping-plan.md`，进度投影在 `.dev/docs/tui/tracking.md`。

## 验证

### 新鲜终态检查

在当前 `main`、2026-09-06 的 `fix: coalesce adjacent response actions in logs` 上执行：

```bash
PYTHONPATH=src uv run python <user-reproduction>
uv run pytest tests/unit/observability/test_request_log.py tests/int/test_pipeline_app.py::test_terminal_output_drives_both_action_list_and_completed_colour
uv run ruff check src tests
uv run pyright src tests
```

结果：direct reproduction 输出 `completed reason(enc:1) function_call(TaskCreate,Bash)`；targeted 为 85 passed；Ruff clean；Pyright 为 0 errors、0 warnings、0 informations。三个提交路径均 clean，当前 HEAD 就是该提交。

### Full regression

Review 修复后，第一次 full run 在 `tests/unit/streaming/test_streaming_resilience.py` 出现一次失败；该测试立即以 `pytest --last-failed --maxfail=1` 重跑通过。随后重新执行完整命令：

```bash
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

结果为 2854 passed、2 skipped、1 warning，coverage 91.77%。该证据支持默认 test collection 在这次 checkout 通过；不证明默认 sweep 明确排除的 `tests/tui/`，也不证明真实 Copilot upstream shape。

### 分辨力

从已提交 candidate 导出 job-private archive，只把 named-action merge arm 变异为不可达，再运行 reducer、用户复现和 production-entry integration 三个 oracle。Pytest 精确报告 `3 failed`、无 setup／collection `ERROR`；共享主树 source hash 前后不变。这证明这三条 oracle 能识别 `f97d243` 的 action-grouping 删除形状。

Code review 另发现 nonempty `NOT_REQUIRED` output 的绿色 `completed` 缺少正样本。新增 `message` 用例后，正确 candidate 的 contextual tests 通过，原收窄谓词 mutant 在新增断言处失败。最终代码评审为 0 blocker、0 major。

## 评审与处置

- 结构评审：`reports/260906-function-call-grouping-structure-review.md`，2 个 major 已实施。
- Design 评审：`reports/260906-function-call-grouping-design-review-2.md`，1 个 major 已关闭，最终 pass。
- Spec 评审：`reports/260906-function-call-grouping-spec-review.md`，1 个 major 已关闭，最终 pass。
- Plan 评审：`reports/260906-function-call-grouping-plan-review.md`，6 个 major 已关闭，最终 pass。
- Code review：`reports/260906-function-call-grouping-code-review.md`，1 个 major 已关闭，最终 pass。
- 完整处置账：`reports/260906-function-call-grouping-structure-review-disposition.md`。Open findings 为 0，disputed findings 为 0；本轮没有 coordinator 自行驳回而未经第三方复核的 finding。

## 冻结范围与分支终态

| 标签 | 日期与提交主题 | `rev-parse` 回执位置 | 用途 |
|---|---|---|---|
| freeze-main-1 | 2026-09-06 `fix: coalesce adjacent response actions in logs` | 收尾阶段“Freeze main repository and worktrees”工具回执 | 最终主树、targeted sanity check 与提交可达性 |
| freeze-dotdev-1 | 2026-09-04 `docs: merge dotdev histories` | 收尾阶段“Freeze dotdev repository state”工具回执 | 判断 `.dev` 文档持久化状态 |

本次主会话没有创建 feature branch 或 worktree，生效位置就是共享主工作树 `main`，因此没有 merge／keep／discard 三选一；本轮派出的 review worktrees 由 harness 创建且未承载源码提交，不由本会话删除。当前有一个并行 `buffered chat completions` 会话仍在工作，`.claude/worktrees/`、`.dockerignore`、`Dockerfile`、`docker-compose.yml` 与 `exp/260820-h2-stream-cap/` 是本轮开始前即存在或由其它工作产生的未跟踪项，本轮未修改、暂存或提交。

## 文档与持久化

跨文档正控在 Spec、design 和 terminal plan 中命中 `function_call(Bash,Bash)`；对 live `spec.md`、`design.md`、`tracking.md` 与 disposition 扫描未命中“production/tests 待同步”、`fix: open`、`fix: disputed` 或 `response_required: true`；当前三个 source/test 路径也未命中同 raw type 相邻调用的旧双字段 oracle。历史 review 原文与终态 plan 中保留的旧输出是显式事故证据，不属于 stale live contract。

`.dev` 当前 checkout 的 dotdev branch不包含项目说明中所称的同步 `README.md`，而 `docs/tui/` 全部显示为 untracked；同一文档树还有并行 Chat 工作。为避免把同伴内容署到本轮或臆造 bulk-copy 流程，本轮没有提交、移动、归档或 push `.dev` 材料。所有 Spec、design、plan、tracking 与报告保留在主根 `.dev` 工作副本；这是明确的持久化限制，不是“已提交”的声称。

## 临时态与清理

`$CLAUDE_JOB_DIR/tmp` 已用 `fd --hidden --no-ignore --type file --type symlink` 与显式包含 directory symlink 的 `os.walk(..., followlinks=False)` 双向比较，集合一致。`closeout-manifest.tsv` 逐项记录当时的 865 个普通文件／符号链接；`CLOSEOUT_DISPOSITION.md` 记录总体与分类。

本轮未取得删除 manifest 的独立许可，因此没有删除任何 job scratch。Commit message、hash manifests、full-test log、baseline copies 与 mutation archive 均就地留给 harness 过期；未知或其它任务的产物保持 untouched。该处置以零删除收口，不声称 manifest 已证明可安全删除。

## 文档生命周期

`spec.md` 与 `design.md` 继续作为 living conclusion documents。`function-call-grouping-plan.md` 已改写为 fully implemented terminal record；`tracking.md` 的 G1～G6 均为 done。评审和 checklist 仍位于 `reports/`，保持 point-in-time 原文。

本次没有移动这些完成材料进入 archive：可观察理由是 `.dev/docs/tui` 正被并行 Chat 工作共用，且 dotdev 持久化边界当前未闭合；移动会同时改变 peer 正在引用的路径。所有材料原地保留并由本报告索引，未执行删除。后续该 topic 的统一归档应在并行工作收束、dotdev 同步机制可确认后一次处理。

本次没有使用 Claude Plan Mode；计划直接写入项目 `.dev/docs/tui/function-call-grouping-plan.md`，不存在 `~/.claude/plans/` 中待迁移的随机计划文件。

## 可复用资产

- 已有 `git commit takes the whole index`、`proving where a command ran`、`mutation restore needs a snapshot` 与 `what a mutation result does and does not prove` 已覆盖本轮共享树、root binding 与 mutation 风险；维持原样，不新增同义 rule／skill。
- 本轮新增的领域机制与 regression oracle 属项目设计和测试，已落在 `design.md`、Spec 与 tests，不提升为通用模型指令。
- 实施账本 memory 已更新为完成态，只提供 `.dev/docs/tui/` 入口，不另复制行为合同。

## 最终边界

本报告不声称真实 Copilot upstream 必然产生测试中的 mock shape，也不声称默认 test sweep 覆盖 `tests/tui/`。本次改动不依赖真实 upstream 语义：它只按已经保留的 `ResponseObservation.output_items` 做 deterministic display projection；production-entry mock 验证 collector 到 completion formatter 的本地接线。

本报告在最终独立评审通过前不发完成信号。最终评审对象为本报告、`spec.md`、`design.md`、terminal plan、tracking、disposition 与提交后的三文件状态。

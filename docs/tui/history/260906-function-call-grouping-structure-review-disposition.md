---
report_id: function-call-grouping-structure-review-disposition-260906
status: closed
source_report: function-call-grouping-structure-review-260906
source_reviewed_at_rev: f97d243f9431d836861ce5e9938605df56b37478
---

# Responses completion action 聚合结构评审处置

## 接收回执

- received_at: 2026-09-06
- counts_declared: findings_total=2, confirmed=2, blocker=0, major=2, minor=0, nit=0
- counts_verified: yes
- delivery_sentinel_verified: yes
- checklist_coverage_verified: yes

## 处置

### function-call-grouping-structure-review-260906-01

- statement_kind: fact
- claim: confirmed
- verification: 已独立对比 `45e7cfb`、`b233751` 与 `f97d243^2..f97d243`；merge 确实删除 action-run accumulator，并同步把 unit oracle 从 grouped 改成 ungrouped。当前 direct reproduction 得到 `function_call(TaskCreate) function_call(Bash)`。
- fix: adopted
- evidence: `abdfd54` 以 typed visible segments → adjacent reduction → rendering 取代双 accumulator；rich 与 legacy formatter 共用 action seam，用户示例现在输出 `function_call(TaskCreate,Bash)`。
- next_actor: none
- response_required: false

### function-call-grouping-structure-review-260906-02

- statement_kind: fact
- claim: confirmed
- verification: 当前 `.dev/docs/tui/spec.md` 明文要求每个相邻 action 独立显示，和用户本轮确认的显示合同冲突。
- fix: adopted
- evidence: `spec.md` 已修订 display grammar、验收第 7 条与修订记录；`abdfd54` 同步 production、unit 与 integration 转录，Spec reviewer 两轮收口至 0 blocker／0 major。
- next_actor: none
- response_required: false

## 设计判断

### 采用候选：typed visible segments → domain-specific adjacent reduction → rendering

- statement_kind: judgment
- judgment_status: concurred
- level: C
- criteria: 它把事实选择、可见 barrier、raw identity、相邻归约与文本渲染拆成可独立测试的责任；新增 segment 默认成为 barrier；删除 action merge arm 会在 reducer 层直接可见。
- decision_origin: agent-decided-within-delegated-scope；用户明确把内部技术裁决委托给 coordinator。
- fix: adopted

### legacy fallback 同批复用 action segment seam

- statement_kind: judgment
- judgment_status: concurred
- level: C
- criteria: `format_terminal_status()` 在 rich observation unavailable 时渲染相同 Responses client-action grammar，且 `ClientAction` 已携带 requirement、raw type、raw name 和顺序。不纳入会让同一显示合同随 observation availability 漂移。纳入只复用 projection／reducer／renderer，不改 producer、优先级或 durable schema。
- decision_origin: agent-decided-within-delegated-scope；用户明确把内部技术裁决委托给 coordinator。
- fix: adopted

### function-call-grouping-design-review-260906-2-01

- statement_kind: fact
- claim: confirmed
- verification: `design.md` 原稿声明 `spec.md` 是唯一行为权威，却没有显式记录现行精确 oracle 与新裁决冲突，也没有规定同一 change 的 Spec-first 同步顺序。
- level: C
- fix: adopted
- evidence: `design.md`“目标与边界”已补明冲突和顺序：先修订行为条款、验收第 7 条及修订记录，再同步修改 production projection 与 unit／integration 转录；同一评审者的限域复评在 `260906-function-call-grouping-design-review-2.md` 第二轮关闭该 major，结论为 pass、0 blocker、0 major。
- next_actor: none
- response_required: false

### function-call-grouping-spec-review-260906-01

- statement_kind: fact
- claim: confirmed
- verification: Grouping 行为正文和验收已经修订，但 `design.md` 仍称 Spec 待修订，`spec.md` 状态段又未标出 production／test 尚未同步，两份 living document 的阶段状态冲突。
- level: C
- fix: adopted
- evidence: `design.md` 已改为“Spec 已修订，production 与 tests 待同步”；`spec.md` 状态段已单列 2026-09-06 Responses grouping 修订的未实现状态，并完整保留 Chat provider observation 的尚未实现状态。同一评审者在 `260906-function-call-grouping-spec-review.md` 第二轮关闭该 major，结论为 pass、0 blocker、0 major。
- next_actor: none
- response_required: false

### function-call-grouping-plan-review-260906-01

- statement_kind: fact
- claim: confirmed
- level: C
- fix: adopted
- evidence: 计划已删除硬编码 job id；所有临时文件在执行时从当前 `$CLAUDE_JOB_DIR/tmp` 推导并校验未逃逸 job root。
- next_actor: none
- response_required: false

### function-call-grouping-plan-review-260906-02

- statement_kind: fact
- claim: confirmed
- level: C
- fix: adopted
- evidence: 计划已要求每个 private seam import 使用项目现有的 `# pyright: ignore[reportPrivateUsage]`，不放宽全局 Pyright 配置，也不把 private symbol 改成 public API。
- next_actor: none
- response_required: false

### function-call-grouping-plan-review-260906-03

- statement_kind: fact
- claim: confirmed
- level: C
- fix: adopted
- evidence: 计划中的每个 tree-dependent shell block 现在都在同一调用内绑定 `/home/xp/src/ghc-api-proxy-py`；Git selector 全部使用 `git -C`，mutation archive 另行核验自己的物理根。
- next_actor: none
- response_required: false

### function-call-grouping-plan-review-260906-04

- statement_kind: fact
- claim: confirmed
- level: C
- fix: adopted
- evidence: 计划在 review 前记录三文件 hash；review 后 bytes 不变才复用旧证据，发生任何 source／test 改动就重跑 targeted、Ruff、Pyright 与 full regression，再允许提交。
- next_actor: none
- response_required: false

### function-call-grouping-plan-review-260906-05

- statement_kind: fact
- claim: confirmed
- level: C
- fix: adopted
- evidence: 计划不再 mutation／restore 共享主树；先提交候选并钉住 commit，再用 `git archive` 导出到当前 job 私有目录，只修改 archive copy并从该副本运行三个缺陷控制，另核对共享 source hash 未变。
- next_actor: none
- response_required: false

### function-call-grouping-plan-review-260906-06

- statement_kind: fact
- claim: confirmed
- level: C
- fix: adopted
- evidence: Ownership inspection 在独立调用中先冻结 approved parent 与三个 worktree blob ids，再从该 parent 生成 baseline、打印实际 diff，并在输出后重核 blobs；下一调用只复用和核验这份 manifest，不得重新定义 approved bytes。Commit 后核 parent、subject、精确 path set 与 candidate blob ids，全部成立后才写 candidate pointer。Archive mutation 使用 Pytest `--quiet`，并要求 exit 1、exact `3 failed`、三个目标 test name 均出现且输出无 `ERROR`，不再把 setup／collection failure 误报为缺陷控制命中。
- next_actor: none
- response_required: false

### function-call-grouping-code-review-260906-01

- statement_kind: fact
- claim: confirmed
- level: C
- fix: adopted
- evidence: 现有 test 只证明 empty output 为绿色；错误收窄成 `items is not None and not items` 时 full suite 仍绿。`test_observed_completed_is_green_only_for_a_known_action_free_output` 已加入 nonempty `message` 正样本，精确断言绿色 `completed` 且无 `client_action?`；production 逻辑无需修改。
- next_actor: none
- response_required: false

## 未采用方案

1. 原样恢复 `b233751` 的双 accumulator——不采用。它恢复行为但保留了依赖每个分支手工 flush 的结构根因。
2. 抽取 callback 驱动的通用 streaming run reducer——不采用。当前只有一个领域调用者，generic interface 会把 skip／barrier／identity／merge 组合重新藏进调用约定。
3. 渲染字符串后再合并——不采用。此时 raw identity 已丢失，且 provider 字符与 renderer delimiter／ANSI 无法可靠区分。
4. 只修改最终字符串 oracle——不采用。它复制了 `f97d243` 的失效形状，不能独立守住归约责任。
5. 重写 `ResponseObservation` schema 或整个 TUI——不采用。现有 rich facts 足够，扩大范围不修复 display reduction 缺层。
6. 排除 legacy fallback——不采用。它会留下数据源可用性相关的显示分叉；本次已经让 legacy fallback 复用相同 action seam。

## 实施与验证回执

- source commit: `abdfd54`，subject `fix: coalesce adjacent response actions in logs`；parent、精确三路径、subject 与三个 committed blob ids 均在写入 candidate pointer 前通过核验。
- targeted verification: `tests/unit/observability/test_request_log.py` 加既有 production-entry integration test，共 85 passed。
- static verification: `uv run ruff check src tests` clean；`uv run pyright src tests` 为 0 errors。
- full regression: 第一次刷新运行在 `tests/unit/streaming/test_streaming_resilience.py` 出现一次失败，该测试立即单独重跑通过；随后完整重跑为 2854 passed、2 skipped、coverage 91.77%。因此最终通过性结论以第二次完整运行和单测复现为依据，不把第一次失败隐去。
- code review: `260906-function-call-grouping-code-review.md` 首轮 1 个 major 已补测；限域复评以正确 candidate 3 passed、收窄谓词 mutant 1 failed／3 passed关闭，最终 0 blocker／0 major。
- negative control: 从 `abdfd54` 导出的 job-private archive 中仅禁用 named-action merge arm；三个 action-grouping oracle 精确报告 `3 failed`、无 setup／collection `ERROR`，共享主树 source hash 前后相同。
- open findings: 0。
- disputed findings: 0。

## 承重关系

前提是用户本轮确认的聚合边界；它支撑 typed segment 的 projection 与 adjacent reduction 规则。若该前提为假，segment barrier、merge identity 和 unit／integration oracle 都要同步改变；历史实现仅是旁证，不能替代用户当前裁决。

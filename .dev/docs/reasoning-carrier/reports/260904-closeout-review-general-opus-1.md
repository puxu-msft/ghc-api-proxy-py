# Reasoning carrier v2 closeout artifact review

## Scope and provenance

- 只读对象为 feature worktree 中的 `tracking.md` 与 `implementation-review-disposition.md`、候选代码与 Git objects、主树 implementation review originals，以及主树 living Spec。
- 冻结候选为 `3466c0af5a6a2d2043956569ff6d1ba97f22f70d`，提交主题为 `test: type the UTF-16 carrier fixture explicitly`。
- 用户指定的 `my-agents:as-reviewer` 不在本会话可用 skill 列表中，无法加载；已记录并继续。评审时加载了 `my-skills:qualifying-a-claim-and-its-coverage`。
- CodeGraph 明确警告其索引来自另一 worktree 且 auto-sync 已停，因此没有把其结果用于承重判断；相关当前源码由目标 worktree 绝对路径直接读取。

## Verdict

**NEEDS-FIX**。0 blocker，1 major。C1、C2、C3、C4、C5、C6、C8 通过；C7 不通过。

## Finding

### MAJOR-1：living Spec 没有收录实施阶段形成的 wire grammar 与 slot-classification 合同，tracking 也没有暴露这项差异（C7）

主树 living Spec §6.2 只把 record `type` 写成“非空 ASCII namespaced string”，没有定义可判定的 lexical grammar；目标实现却在 `src/app/pipeline/translation_driver/reasoning_carrier.py:43-45,237-243` 固定为 `[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+`，并在 `tests/unit/pipeline/translation_driver/test_reasoning_carrier.py:249-256` 把 bare `x` 固化为 malformed。这个 accepted／rejected input boundary 是 observable wire contract，不是单纯内部实现细节。

最终复评又把 Responses slot 中的 project v1 payload／bare 与兼容 v1 payload／bare／legacy 全部归入 `project_v2_direction_mismatch`：实现位于 `src/app/pipeline/translation_driver/reasoning_bridge.py:77-99`，处置文档第 26 行也明确说修复扩到了这些形态；但 Spec §6.4、§8 的 profile／precedence 与分类表没有规定这组 v1→`project_v2_direction_mismatch` 映射。该 refinement 会进入 reader、compat classifier 与 provider last-mile guard 的稳定诊断，因此同样属于 Spec-level behavior。

`tracking.md` 的 P6 和评审段仅概括“全部 findings 已处置”并链接处置文档；它没有指出上述两项仍未进入 authority Spec，反而让读者得到 Spec 与 candidate 已完全闭合的结论。`implementation-review-disposition.md` 记录了实现结果，但按项目的 living-Spec 规则，处置文档不能代替行为权威。合入前应先由 Spec 明确 exact dotted grammar 和 Responses slot 对 legacy v1 forms 的分类／错误代码，在 Spec 自身 revision record 记录实施评审触发的修订，再让 tracking 如实标明该同步已完成；若不准备把当前实现提升为合同，则 tracking 必须明确暴露差异并阻止把它描述成已闭合。

证据强度：源码、测试、处置原件与当前 authority Spec 的直接对账，足以据此阻止 closeout；无需推断运行态。

## C1-C8 verification record

| Criterion | Result | Evidence |
|---|---|---|
| C1 | PASS | 从 base `39274d7bc3601f2236ffdfc52ea6f34f885ba405` 到候选是 9 个单父提交。前 5 个提交主题逐字对应 P1～P5；其后的独立 fixture、两轮 finding closure 与最终 annotation 共同对应 P6 的评审／验证收口。逐提交 name-status／stat 与各语义边界一致。当前 main 的 tracked WIP 是 tool-choice／tool-result 主题，候选相对 base 的完整 diff 对这些具名 marker 为 0 命中，正控在 main WIP 中有大量命中；candidate 没有夹带该 WIP。 |
| C2 | PASS | HEAD、index 与 tracked working files 均锚定最终候选。最终改动文件 mtime 为 07:48:19，Ruff cache 最新条目为 07:49:03，commit 为 07:49:17；`.coverage` 与 pytest nodeids 均更新于 07:51:22，晚于最终 commit，现有 coverage data 只读重算为 91.46%。tracking 记录的最终命令与结果为 Ruff PASS、Pyright 0 errors／0 warnings、pytest 2244 passed／2 skipped。`pyproject.toml` 的 default pytest entry 明确 `--ignore=tests/tui`，candidate 的 27 个变更路径没有 TUI。受“唯一可写报告”约束，本轮没有重跑会更新 cache／coverage 的命令；现有 final-HEAD artifacts、时间顺序与声明无冲突。 |
| C3 | PASS | 两份首轮报告合计的五类独立 finding 均在第一轮处置表有对应项：strict UTF-8／JSON／record grammar、slot-aware classification、redacted data guard、redacted streaming typed IR、buffer accounting。两份第二轮报告共同提出的 Responses-slot bare-v2 finding 在“第二轮处置”单列，并覆盖扩展后的 project／compat v1 matrix。两份第三轮 PASS 与 annotation-only 第四轮 PASS 均在“最终复评”逐份列出；原件没有其他 finding。处置明确声明 0 不采纳、0 暂定、0 deferred、0 待裁决。 |
| C4 | PASS | 注册 worktree 仍为 keep，branch ref 与 worktree HEAD 都指向候选。Target index checksum有效，root cache-tree 与 HEAD commit tree 相同，587 个 index entry 全为 stage 0，587 个 tracked working file 的 blob／mode 全部匹配 index；额外内容只有 `.dev`、`.venv`、coverage／pytest／Ruff 等 ignore 范围，故状态 clean。只有本地 `refs/heads/worktree/reasoning-carrier-v2` 包含候选；main、remote refs 与 tags 均不包含，branch 无 upstream，故在可观察 refs 下为 unmerged／unpushed。当前 4141 listener 的 PID 303153 启动于 04:56:32，早于本 branch 第一提交 06:40:55；本轮只读检查也未对其执行控制操作，与 originals／tracking 的“未操作 4141”一致。 |
| C5 | PASS | `tracking.md` 第 4 行明确其为 feature-worktree 临时投影，第 43 行明确状态与实现处置尚待同步到 local `dotdev`；没有把未完成持久化写成完成。 |
| C6 | PASS | 对两份叙述文档执行 7～40 位 lowercase hexadecimal commit-like token 搜索为 0 命中；候选通过可重定位命令和提交主题描述，没有裸 SHA。 |
| C7 | FAIL | 见 MAJOR-1。 |
| C8 | PASS | 两份文档与全部 implementation review originals 均未声称或执行删除，故不存在需要 deletion manifest 授权的动作。`tracking.md` 明确 branch／worktree keep，临时投影先同步到 local `dotdev`、再处置副本；去留顺序与接收位置均明确。 |

## Review boundary

本轮没有修改源码或被审文档，没有执行 git add／commit／checkout／stash，没有删除、清理、合并、发布或控制 4141。唯一写入产物是本报告。

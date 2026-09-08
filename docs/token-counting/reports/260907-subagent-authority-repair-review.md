# Token-counting authority repair merged-state review

## 评审范围

工作目录固定为 `/home/xp/src/ghc-api-proxy-py`。只读评审对象为当前 `.dev/docs/token-counting/` 下的 `spec.md`、`plan.md`、`status.md`、`HANDOVER.md`，以及用户指定的四份历史报告：`260907-task3b-authority-review-gpt-high.md`、`260907-subagent-t3b-authority-analysis.md`、`260907-subagent-handover-inspection.md`、`260907-subagent-downstream-readiness.md`。

判据来自用户本次评审问题、项目开发工作流、`as-reviewer` 的权威归属与绿灯分辨要求，以及 `as-handoff-inspector` 的真实接手执行要求。未启动 source、测试、Ruff、Pyright、真实 upstream 或 4141；未修改任何既有文件。

## 总体 verdict

**READY**

- blocker：0
- major：0
- minor：1
- confidence：高

T3B-AUTH-01～04 与 Minor05 在当前 Spec／Plan 中已经有唯一且相互一致的 owner／carrier／acceptance 归属。T3B-AUTH-03 的执行入口 writeback 也已实际出现，并由本次 fresh review 重新核对，不再沿用旧报告的“待复核”状态。H2 已经可以执行；H3／H4 仍按 HANDOVER 正确保持 blocked，不能把本次 READY 误读为已经授权启动 Task 3B source。

## 实际执行轨迹

按 HANDOVER 当前动作表，第一条 `ready` 动作为 H2（`HANDOVER.md:29-37`）。我实际执行了：

```text
git status --short --branch
git rev-parse HEAD
sha256sum .dev/docs/token-counting/{spec,plan,status,HANDOVER}.md
git rev-parse --verify main
git rev-parse --verify integration/token-learning-store
git rev-parse --verify archive/260907-token-prediction-persistence
git rev-parse --verify archive/260907-token-learning-store
git rev-parse --verify dotdev-token-counting-learning
git rev-parse --verify origin/main
```

实际结果为：`main` 与 `HEAD` 均为 `42fb23299bc9487d1751749668277ac4304861f8`；`main...origin/main [ahead 3]`；integration 为 `16a0904496f0af0a7832e4dd4bcb18fdc69919f9`；两个 archive 分别为 `c59cdd66a008f8ae8248b781a0c74fc36e129287` 与 `9ff21cef4d0f2377d1e60eba962e3b450584902c`；dotdev 为 `b1dd960d6e5a5781f46610be8ff9ed212eaca5c0`。root 的 untracked 集合与 HANDOVER 记录一致。

当前 authority hash 实测为：

```text
spec.md  5d9477dd260edfdad90b62c031086de29f1a7b9e6852816d41eb3973fc93cc48
plan.md  bea5e7537f79a8242be48609e320481445599a317eb4fab38a29c9f2e450047a
status.md 1f789f01db3b19fc4d392ca5bc9f8527a11d37c2871a521ae388058c5cabcc65
```

`spec.md` 与 `plan.md` 的 hash 与 `status.md:5`、`HANDOVER.md:5` 完全一致。H2 的相对链接解析命令确认 HANDOVER 中的全部 14 个 Markdown 链接均存在。仓库内没有发现项目专用 HANDOVER checker；该机械检查记为不可用，没有把链接解析冒充项目闸门。

随后才完成当前八份对象的通读和逐条比对，并用限定 `rg` 复核 owner、pending carrier、A44／A45、4B-P、revision、refs 与 action-table 锚点。

## 逐项结论

### T3B-AUTH-01：policy／store final observation owner

**结论：已关闭，confirmed，高置信。**

`plan.md:134` 明确 `TokenLearningPolicy` 只返回 logical `LearningUpdate`，不得返回或预填 `TokenLearningObservation`、checkpoint store outcome、post-transition revision、capacity transition 或 durable event。`plan.md:143` 将后台产生的 typed observation 与 RequestLine 分开；Spec §7.3、§8.4（尤其 `spec.md:372`、`spec.md:475-484`）规定 store 在 final state 与 confirmed COMMIT 后唯一构造 durable observation 与 checkpoint outcome。

这不是仅改了一个标题：Plan 的 Task 3B interface（`plan.md:387`）也删除了 policy-owned final observation，改为 logical command、store stamping、persistent evidence 和 store-owned outcome。未发现旧的“policy 返回 final observation”仍出现在当前 Spec／Plan的执行性正文中。历史报告保留旧反例是点时证据，不是当前 owner。

### T3B-AUTH-02：pending checkpoint evidence 与 committed order

**结论：已关闭，confirmed，高置信。**

`spec.md:372` 定义独立的 `PendingPrefixChampionErrorTriple`，明确它只能出现在 policy-return logical command、最多一个、必须是 evidence 唯一 tail，历史 entries 必须已经是 positive order；multiple pending、non-tail、persistent pending 和 early encode 都是 corruption。store 计算 `next_global_revision` 后，才把 pending tail 与当前 sample stamp 为同一 positive `committed_order`，再构造 persistent triple 并 encode。

`plan.md:387` 对同一 carrier、stamp 时点和拒绝条件作了相同转录。`spec.md:265` 继续保持 pending sample 在 policy 边界为 `None`、public／persistent state 不得为 `None`。未发现 policy 猜测 revision、sentinel order 或 persistent DTO 接受 pending order 的授权路径。

### T3B-AUTH-03：4B-P、旧 brief、状态投影和执行入口

**结论：已关闭，confirmed，高置信。**

当前 `plan.md:29` 固定 `3B → deterministic 4A → 4B-P → 4B → 4C`。`status.md` 的任务投影已单列 4B-P，并让 4B 依赖 4B-P；HANDOVER 的 H1／H2／H3／H4 action table（`HANDOVER.md:33-37`）给出了可执行的 review gate 和 blocked downstream actions。HANDOVER 还明确旧 Task 4A brief 只能作为被否路线证据，不得直接派发。

历史 `260907-subagent-downstream-readiness.md` 与 `260907-subagent-handover-inspection.md` 记录的是修复前状态，报告中“未复核”“接不住”仍然存在，但它们是被检历史报告，不是当前状态 authority。当前 HANDOVER 的 main、dotdev、integration 和 archive refs 已与 Git 实测一致；旧报告中的 `18c7c690`／`7119473d` 不再被当前 HANDOVER 当作 current anchor。该差异是历史演进，不是现行授权缺口。

### T3B-AUTH-04：full-baseline 与 current-zero controls

**结论：已关闭，confirmed，高置信。**

`spec.md:656` 的 A45 现在有两组能区分错误实现的输入：一组让 historical known delta 为 0、visual／prior delta 为正并断言完整 baseline 的 residual、ratio、candidate value 和 sample count；另一组让 current baseline 为 0、但提供至少三条 positive historical ratio evidence，并断言 multiplicative candidate 保留且 suffix value 为 0。两组都明确要求把 known-only baseline 或恢复 current-zero gate 的 mutation 判红。

`plan.md:396` 的 Task 3B tests checklist 和 `plan.md:431-436` 的 Task 4B-P checklist同步列出这两个 mutation。Spec §13 transcription map（`spec.md:658` 后的 `test_learning_store.py`／`test_prediction.py` 条目）也把它们归入现行转录要求。因而原反例不能再依靠 visual／prior 为零的 fixture 全绿通过。

### Minor05：same-transaction current-sample prune

**结论：已关闭，confirmed，高置信。**

`spec.md:655` 的 A44 明确要求 current sample 在同一 transaction 成为 sample-cap victim 时，sample row 最终缺席，但 checkpoint replacement／delete、真实 Applied／Deleted outcome 和 post-transition revision 仍保留；“pruned 时跳过 checkpoint”和“改成 NoChange”两种 mutation 必须判红。Plan 的 Task 3B checklist同步要求该 fixture及两种 mutation。

这把“旧 checkpoint source sample 后续被 prune”与“本次刚插入的 sample 同事务被 prune”分开，正好覆盖原 Minor05 的接缝。

## owner、acceptance 与 revision 的一致性

当前 Spec revision record 最后一条 Task 3B 修订记录明确写入 policy／durable observation owner、pending carrier／store stamping、A44 current-sample prune 和 A45 baseline／current-zero discrimination。Plan 的 Task 3B interface、checklist 和 Task 4B-P checklist 与这些条款一致，没有发现把行为事实重新安置到 status、HANDOVER 或历史报告的情况。

`status.md:5` 的 Spec／Plan hash 与实测一致；status 仍明确“尚未通过 fresh scoped review”，这是本次 review 之前的有效门禁快照，不是错误 owner。HANDOVER 的 H2 为 `ready`，H3／H4 为 `blocked`，且 exact base `16a09044...` 与实际 integration ref一致。没有发现 current status、Plan checklist 或 HANDOVER action table把 source 标成可直接启动。

## 真实差异与唯一 minor

### AUTH-REPAIR-REVIEW-MINOR-01：H0 声称记录三个 authority hash，但 HANDOVER 只展示两个

- `severity`：minor。
- `confidence`：高。
- `primary_location`：`HANDOVER.md:5`、`HANDOVER.md:33`。
- `evidence`：H0 的命令包含 `spec`、`plan`、`status` 三个文件，但 HANDOVER 顶部只给出 Spec 与 Plan 的 hash；实测 `status.md` hash 为 `1f789f01db3b19fc4d392ca5bc9f8527a11d37c2871a521ae388058c5cabcc65`。
- `impact`：接手者仍可按 H0 命令重算，且 status 作为 volatile projection 不应成为行为 authority；因此不阻塞 H2，也不形成 source authorization。缺的是 status snapshot 的可复核 artifact anchor，而不是行为 owner。
- `recommended disposition`：下一个 HANDOVER/status 同步时可补上 `status.md` hash 或明确 H0 的“三个 authority hash”仅指可重算命令，不必回滚当前 gate。

## HANDOVER 是否已从“接不住”修到可执行

**已修到可执行，结论为 confirmed。**

我按当前 H2 真实走了一遍：能够从 action table 找到唯一 `ready` 动作，能够解析其依赖与 evidence locator，能够冻结实际 refs／hash，并能确认 H3／H4 仍 blocked。相对链接 14/14 存在；没有 source、测试或 4141 的隐含启动入口。

旧接手性报告的主要问题（无 action table、旧 main／dotdev 锚）在当前 HANDOVER 中已经有可观察修复：H0～H4 action table 已存在，main 为 `42fb232...`，dotdev 为 `b1dd960...`，并显式写出 H2 前没有 source authorization。旧报告本身仍写着“接不住”是历史结论，不能反向覆盖当前 HANDOVER。

负空间也足够明确：HANDOVER 明说 A44／A45 坏样本尚未运行、没有机械 checker、没有运行 source／tests／Ruff／Pyright／真实 upstream／4141，也没有移动或清理 shared main。冻结理由具体指向 4 Major／1 Minor 门禁、旧 brief superseded、main 已移动和未授权 source，而不是空泛的“暂不处理”。

## 未验证边界

本报告没有验证尚未实现的 Task 3B source，也没有执行 A44／A45 mutation；HANDOVER 已正确把这些记为 `unverified`，不能把 acceptance 文本当作测试通过。没有验证真实 upstream token accuracy、SQLite runtime behavior、TaskList 原始 JSON 或 source integration。历史报告中的测试数、coverage 和 action denominator均作为点时证据处理，没有冒充当前 runtime evidence。

## 结论

当前 authority repair merged state 可通过 fresh scoped review：**READY，0 blocker，0 major，1 non-blocking minor**。可继续 H3：生成 Task 3B implementation brief并独立评审；在 H3 通过前仍不得启动 Task 3B source。  

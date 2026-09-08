# Task 3B 独立 source review

## 评审范围

- 被检对象：独立工作树 `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration` 上相对 `16a0904496f0af0a7832e4dd4bcb18fdc69919f9` 的**未提交** source diff。
- HEAD 即 source base：`16a0904496f0af0a7832e4dd4bcb18fdc69919f9`（`feat: preserve token prediction candidates`）。无 source commit。
- 工作树 `git diff --name-status` 仅 6 个路径，与 brief allowed paths 一致；`worker.py` / `test_local_token_worker.py` 未改：
  - `src/app/tokenization/types.py`
  - `src/app/tokenization/features.py`
  - `src/app/tokenization/learning_schema.py`
  - `src/app/tokenization/learning_store.py`
  - `tests/unit/tokenization/test_features.py`
  - `tests/unit/tokenization/test_learning_store.py`
- 判据来源（主工作树，读实现之前取）：`spec.md` §4.1／§6.2／§7.3／§8.1.1／§8.2／§8.4／§8.5／§11／A40～A44；`plan.md` Task 3B；`task-3b-brief.md`。`reports/260907-task3b-implementation-gpt-m-followup.md` 只作未核验 claim，不从中反推合同。
- 明确不在范围：不修改任何文件、不提交、不启动 4141、不碰 shared main；不评 Task 4A predictor、Task 4B 16／8 policy、Task 4B-P formulas。
- 本轮为独立 source review，不是 verifier 验收，也不是对实现者自述的勾选复核。

## 总体 verdict

**NEEDS FIXES。** Spec compliance：**NEEDS FIX。** 未发现 blocker；发现 2 条 major、1 条 minor。按 brief「source review 必须确认 0 Critical／Important」闸门，**阻塞 commit**。

- blocker: 0
- major: 2
- minor: 1
- nit: 0

## 已核对且成立的承重面

下列合同在最终状态与探针中成立，不构成发现：

- `LearningUpdate` 只携带 logical `prefix_checkpoint_command`；`TokenLearningObservation`／checkpoint outcome／post-transition revision 由 store 在 stamp 之后构造。
- `ReplacePrefixCheckpoint` 拒绝 multiple／non-tail pending；`PrefixEligibilityCheckpoint` 拒绝 public pending；`LearningSnapshot` 拒绝 `committed_order is None`。
- `_stamp_update()` 把 current sample 与唯一 pending tail 标成同一 `next_global_revision`，再进入 sample codec／checkpoint upsert。
- Prefix checkpoint 表以 canonical ProfileKey JSON 为 PK，hash 只作 index，FK 指向 `epoch_state` 而非 sample；同事务 current-sample prune 仍保留真实 `Applied` outcome。
- Per-identity rollover 只清当前 identity 的 E checkpoint，current sample 留在 E，active 变为空的 E+1；global 零收益分支 typed `CapacityRejected` 且 sample 仍 commit。
- Drift 强制 `NoPrefixCheckpointChange`，并借 inactive cleanup 清旧 epoch checkpoint。
- Action ledger 测试字面量独立于 production expansion helper，并断言 111 bases／211 IDs。
- Compact codec 拒绝 verbose prefix object、wrong arity、非 4 倍数 framing。
- 独立切片探针中，四种 visual suffix（None→present、0→present、present→present、present→None）按 item slice 的 `known + visual_or_zero + prior` 可算出，whole-visual 差分对 None 前缀不可用。这证明 **producer 的 per-item 数值** 可用，不证明 A40 已绑定 mutation。

---

## Findings

### T3B-SR-01 — 含成功 image 的 mixed media 会丢掉 `MEDIA_REASON`

- **severity:** major
- **confidence:** high
- **阻塞 commit:** 是
- **primary_location:** `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/features.py:365`
- **related_locations:**
  - `src/app/tokenization/features.py:345-366`（`capability_visual_tokens` 在成功路径 `discard(MEDIA_REASON)`）
  - `src/app/tokenization/features.py:392-407`（`finish()` 对每个 item slice 再调用一次）

**判据**

Spec §4.2：公式缺席或所需 metadata 不足时，visual 槽为 `None`，方程贡献 0，并增加具名 low-confidence reason。`zero-prior:media-without-capability-formula` 在 media 存在且公式未覆盖全部适用 media 时必须保留。Task 3B 把 whole 计算改成「先 whole、再 per-item」，不得让 per-item 成功路径改写 whole 仍为 `None` 时的 reason 集。

**场景与错误行为**

payload 含一张可公式化 image（56×84→6）和一项无 image formula 的 PDF。独立探针：

```text
MIXED_VISUAL None
MIXED_ITEM_VISUAL [6, None]
MIXED_HAS_MEDIA_REASON False
MIXED_REASONS ('zero-prior:pdf-without-capability-formula',)
PDF_ONLY_VISUAL None REASON True
```

Whole visual 仍正确为 `None`（all-or-none），per-item 也正确。但 image slice 走完成功路径后执行 `discard(MEDIA_REASON)`，把 PDF item 先前 `record_media()` 写入的 generic media reason 抹掉。3B 之前 whole 函数在遇到非 image 时会在 discard 之前 `return None`，mixed 不会丢这个 reason；这是 per-item 二次调用引入的回归。

**为何现有 tests 未抓到**

`test_item_contributions_exactly_reconstruct_known_and_visual_aggregates` 只用 message+image 的成功 visual；没有 mixed image+PDF／missing-dimension 的 reason 断言。绿灯没有分辨力。

**最小修法（供调用方，本轮不改）**

reason discard 只能在 **whole** media 集全部成功时发生；per-item 计算不得修改共享 `low_confidence_reasons`。

---

### T3B-SR-02 — `failed` observation 接受非法 checkpoint outcome

- **severity:** major
- **confidence:** high
- **阻塞 commit:** 是
- **primary_location:** `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/types.py:1343-1348`
- **related_locations:**
  - `src/app/tokenization/types.py:1235-1355`（`TokenLearningObservation.__post_init__` 矩阵）
  - `src/app/tokenization/learning_store.py` `_decode_prefix_checkpoint_outcome` / `_validate_observation_for_storage`（decode 后只再走同一 DTO）

**判据**

Spec §7.3／A44：duplicate 只接受 `NotAttempted(duplicate-sample)`；rejected 只接受 `NotAttempted(sample-rejected)`；failed 在 policy 前只接受 `NotAttempted(failure-before-policy)`，policy entry 后只接受 `NotCommitted`。DTO、event codec 与 all-epoch graph 必须拒绝 wrong family／unknown variant。

**场景与错误行为**

duplicate／rejected 分支是精确相等检查。failed 分支只要求 `NotCommitted | NotAttempted`，**不限制 NotAttempted 的 reason**。独立探针：

```text
FAILED+NOTATTEMPTED_DUP ACCEPTED
FAILED+NOTATTEMPTED_REJECT ACCEPTED
FAILED+NOTATTEMPTED_BEFORE ACCEPTED
FAILED+NOTCOMMITTED ACCEPTED
DUP+SAMPLE_REJECTED ValueError
COMMITTED+NOTCOMMITTED ValueError
```

因此 `failed + NotAttempted(duplicate-sample)` 与 `failed + NotAttempted(sample-rejected)` 可构造、可 `record_event`、可经 event JSON round-trip，startup graph 不会当 corruption。实现者 follow-up 声称「failed observations enforce the appropriate not-attempted/not-committed families」与此不符。

**为何现有 tests 未抓到**

没有 failed×checkpoint-outcome 负例。`_event()` 对一切 failed 填 `NotCommitted`；另一处 drift fixture 用了正确的 `FAILURE_BEFORE_POLICY`，两套组合 DTO 都接受，形不成单变量判红。

**最小修法**

failed 只允许 `NotCommitted` 或 `NotAttempted(FAILURE_BEFORE_POLICY)`。若要把 reason_code 与 phase 绑死，`ANALYSIS_FAILED`／`STORE_UNAVAILABLE`／`MIGRATION_FAILED` 不得搭配 `NotCommitted`。

---

### T3B-SR-03 — stamp 前 sample codec 不是 typed reject

- **severity:** minor
- **confidence:** high
- **阻塞 commit:** 否（生产路径先 stamp；不满足 brief 的 typed-before-codec 控制）
- **primary_location:** `/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration/src/app/tokenization/learning_store.py:4965`
- **related_locations:**
  - `src/app/tokenization/learning_store.py:4928-4945`（`_stamp_update`）
  - `src/app/tokenization/learning_store.py:5891-5899`（`_validate_sample_for_storage` 才拒绝 pending）
  - `tests/unit/tokenization/test_learning_store.py` `test_malformed_pending_checkpoint_commands_reject_before_codec_or_rows`（monkeypatch `_encode_sample`，不是 codec 自己拒绝）

**判据**

Brief pending 专项：stamp 前 early encode 必须 typed reject，且发生在 persistent codec／row write 之前。实现者 follow-up 自己的 stamp-skip mutation 失败形态是 `sqlite3.IntegrityError: NOT NULL constraint failed: samples.committed_order`，即已经进入 INSERT。

**场景与错误行为**

`committed_order is None` 的 logical sample 调用 `_encode_sample()`：**接受**。`_validate_sample_for_storage()` 会拒绝，但 `_run_and_prepare_transition()` 在 stamp 后直接 `_encode_sample`，不走 storage validator。若 stamp 被拿掉，失败点是 SQL NOT NULL，不是 typed codec error；malformed-pending 测试靠 monkeypatch 才假装「codec 前拒绝」，生产 codec 并无此守卫。

**为何现有 tests 未抓到**

正向 stamp 测试只看到 stamp 后的 positive order。负例在 validation 层用伪造 command 失败，encode 路径根本走不到。

---

## 未采用建议

- 把 `_encode_sample`／checkpoint evidence JSON 做成独立的 stamp-gated codec，pending 或缺 `committed_order` 时 raise 具名 `ValueError`，不要依赖 SQLite NOT NULL。这是 T3B-SR-03 的修复方向，不是另一条合同。
- A40 四种 suffix transition、nested framing／tuple-swap mutation、788-item SQLite round-trip 应写成单变量 control。当前实现的 per-item 数值在探针上可用，但 **不能** 用现有绿灯冒充 A40 已绑定。
- failed 矩阵应覆盖 policy-entry rollback `NotCommitted` 与 post-COMMIT cancellation 携带实际 committed checkpoint result；现有 cancellation suite 不能替代 A44 专用矩阵。

## 未验证边界

未当作「已通过」，也不从实现者 432 passed 折算：

- A40：nested framing 漏算／重复、item token 算入 fixed context、verbose prefix 恢复（codec 探针会拒，但无 mutation 测试）、788-item **SQLite** round-trip、worker 真实 process pickle。本轮未跑 `test_local_token_worker`（worker 未改）。
- A41：same-timestamp 两 sample 的 committed-order availability／single canonical base。3B 只 stamp order；pairing 属后续 predictor。本轮未构造 two-process 同 timestamp fixture。
- A42：eligible16／demoted8 领域 policy（brief non-goal）；CAS mismatch 与 `DeleteRecoveredPrefixCheckpoint` 有实现与 action-trace 触达，无独立 CAS 负例。
- A43：inactive cleanup 的确定性排序；「零收益仍 rollover」的源码 mutation 由作者自述，本轮只复现了正确 reject 路径，未再破坏源码。
- A44：committed 五结果全矩阵、`pruned→skip checkpoint`／`pruned→NoChange` 必须判红的 mutation。current-prune 正向路径已探针：sample 缺席且 event JSON `kind=applied`。
- A45 formula／full-baseline／current-zero multiplicative：按 brief 留给 Task 4B-P，3B 未实现 `prediction.py`，不构成缺陷。
- 完整 `tests/unit/tokenization` 与 Ruff／Pyright：作者 follow-up 声称全绿。本轮只跑了 7 个 focused tests，`7 passed in 2.41s`，且这些测试对 T3B-SR-01／02 **不变红**。未把作者的 432／549 当作本轮证据。

## 搜索面

- 读完：brief、spec 3B 相关节、plan Task 3B、6 文件 diff 与最终状态（types 新 DTO、features `_Analysis` item accumulator、schema `prefix_checkpoints`／compact columns、store stamp／capacity／decode／observation 矩阵、新增 store tests）。
- 命令：`git -C … status/diff --stat/--name-status`；独立 python 探针（mixed media reason、四 suffix、DTO 矩阵、compact codec、pending encode、rollover DB rows）；focused pytest 7 项。
- 未跑：完整 learning-store／tokenization selectors、Ruff、Pyright、4141、作者列出的 stamp-skip／zero-benefit 源码 mutation（评审不得改被检对象）。
- 范围扫描：`TokenLearningObservation(` / `LearningUpdate(` 仅出现在 allowed 的 types／store／两份 tests 中；无 allowed-path 外泄漏。

## Verdict

**NEEDS FIXES。** 0 blocker，2 major（T3B-SR-01、T3B-SR-02）阻塞 commit；T3B-SR-03 不单独阻塞。修复后必须再做独立 source review，不得把本轮 focused 绿灯或作者 follow-up 的 432 passed 当作关闭证据。

# Raw capture v23 final-fix scoped re-review

状态：final
report_id: raw-capture-final-rereview-v23
attempt_id: raw-capture-final-rereview-20260909-aa8d206f22cbb25bd
reviewed_at_rev: shared post-fix snapshot bound by Task 6 fix-report SHA-256 values
spec_rev: ACTIVE v23

## 评审范围

本次只复审上一轮 `/tmp/raw-capture-final-review.md` 的 RC-FINAL-01 至 RC-FINAL-04，以及这些修复 hunk 直接触及的 ordinary diagnostics、structured completion records、exact hashed paths、cross-store CBOR poison controls 和 Task 6 progress/package binding。判据来自 ACTIVE v23 `spec.md` §2–§6、上一轮四条 finding 的具体合同，以及用户本次 scoped re-review 指令。

明确不重开全量 raw-capture review，不评价 final-fix package 中从原始 BASE 带入但不属于 RC-FINAL-01 至 04 的累计 diff，不把 shared tree 的无关 peer WIP、11 个 full-regression failures、真实 Copilot canary、coverage 或部署验证纳入 verdict。

本次读取的七个 shared files 的 SHA-256 全部与 `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-f8086b646635/task-6-fix-report.md:39` 所列 post-fix snapshot 一致：`request_completion.py`、`inference.py`、`test_raw_capture.py`、`test_request_completion.py`、`test_pipeline_app.py`、disposition 和 progress。故该 fix report 的 scoped test text 和 source assertions 可绑定到当前被审字节，而非仅是另一个临时副本。

## 总体 verdict

Ready to merge：With fixes。Critical：0，Important：0，Minor：1。RC-FINAL-01、RC-FINAL-02 与 RC-FINAL-03 的 source implementation 和对应判否 controls 均已闭合。RC-FINAL-04 只消除了旧的 `not started` 矛盾，却仍把已经应用的 shared patch 写成 pending，且没有把新的 `final-fix-review-package.md` 纳入 active recovery map；在用户要求的“single consistent state”下仍未闭合。

## Strengths

- `safe_exception_detail()` 现在对已归一化的 upstream error 保留固定 status projection，对其它异常仅返回 `module.qualname`；不再调用 exception 的 `str()` 或 `repr()`。`safe_exception_notes()` 同样只输出固定 presence／unavailable marker。
- dispatch failure、secondary cleanup、interruption record、emit/freeze warning 与 local stream ending 已接到同一安全投影。现有 client wire error 的 `proxy_error(..., str(error))` 保留在 client-response path，而不进入 ordinary diagnostics。
- 新的 hashed-path controls 精确比较 session／agent 的 SHA-256 前 24 位、missing-agent namespace、suffix 和 raw identity 缺席；它们能区分上一轮指定的 SHA-1、错误截断长度和经 sanitization 的明文路径回归。
- 新的 cross-store control 以 valid zstd 载体分别注入 scalar 和 multi-item CBOR，实际经过 `RawCaptureStore` 的 first-append validation，并同时判定不增长、无 reservation、`path_poisoned` 和 ordinary-log payload 缺席。

## Critical findings

未发现 Critical finding。

## Important findings

未发现 Important finding。

## Minor findings

### RC-FINAL-04 · Minor · progress ledger 仍将已应用的 shared fix 写成 pending，且没有锚到新的 fix package

- primary_location：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-f8086b646635/progress.md:130-143`。
- related_locations：`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-f8086b646635/final-fix-review-package.md:0-12`；`/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-f8086b646635/task-6-fix-report.md:35-39`。
- 逐条完成度：部分关闭。`progress.md:65` 已把 Task 6 收敛为 `in-progress`，不再同时宣称 “not started”，并正确把旧 `final-review-package.md` 标为 pre-fix input。可是 `progress.md:138` 仍称 “shared-worktree application and coordinator re-review remain pending”，`:143` 仍把 “coordinator applies the patch” 列为未完成的前置条件。
- 具体失败场景：新 package 明确写的是 “Current shared worktree after /tmp/raw-capture-final-fix.patch applied”，而当前七个 source/test/document SHA-256 也逐项等于 fix report 的 post-fix values。因此 next actor 同时读 package 与 recovery ledger 时，会得到“patch 已在 shared tree”与“coordinator 尚未应用 patch”两种互斥状态。ledger 还没有指向本次实际被用于 re-review 的 `final-fix-review-package.md`，只能从外部消息猜到正确 package。
- 影响：当前代码行为不受影响，但 final integration 的恢复源仍不具单一、一致且可复现的状态。后续协调者可能重新应用已经在树内的 patch，或把 re-review 的 artifact 与其对应 source snapshot 断开。
- 建议：将 `progress.md` Task 6 段改为明确区分 “shared patch applied and hashes verified” 与 “scoped re-review/integration decision pending”，加入 `final-fix-review-package.md` 的绝对路径和它与 fix-report hash binding 的关系。随后再以这一份 active ledger 作为 integration decision 的状态源。

## Spec coverage

| Previous finding | Contract | 结论 | 复审证据 |
|---|---|---|---|
| RC-FINAL-01 | ACTIVE v23 §4／§6 的 ordinary diagnostics 与 completion record 不复制 unknown exception message、repr、chain text、note 或 local stream text | 已关闭 | `request_completion.py` 的 shared projector、`inference.py` local-stream path、package 中 dispatch／cleanup／interruption／local-stream controls；本轮无写入 in-memory probe 对 dispatch、cleanup/note 和 local stream 均只得到 stable type／marker。 |
| RC-FINAL-02 | ACTIVE v23 §2 的 SHA-256 24-character path、missing namespace、raw identity 不出现在 path | 已关闭 | `test_capture_path_uses_exact_hash_prefixes_without_raw_identity_values` 与 `test_missing_agent_id_has_its_own_exact_hashed_capture_group` 的 exact-path oracle；本轮无写入 probe 以当前 `RawCaptureStore._path_for()` 复算并通过。 |
| RC-FINAL-03 | ACTIVE v23 §3／§5 的 valid-zstd scalar 或 multi-item frame 在 new-store first append 时 poison 而不增长 | 已关闭，限 source/test-control audit | 参数化 control 逐项断言 file bytes、reservation、`path_poisoned` 和 payload-free logging；`iter_raw_capture_records()` 当前仍有 one-item 与 top-level-map guards。 |
| RC-FINAL-04 | 用户要求的 Task 6 ledger/package binding 单一一致状态 | 未关闭 | 旧 `not started` 状态已消除，但 shared application 的当前状态和新 package anchor 仍与 package/source hash 事实不一致。 |

## Evidence limits

- 本轮没有运行真实 Copilot canary、全量 pytest、coverage、部署检查，且没有把它们的缺席转成 finding。
- Task 6 fix report 的 pytest、Ruff 和 Pyright outputs 是 bytes-bound 的 scoped prior evidence，不是本 reviewer 重跑出的全量结果。首次尝试在 shared tree 无写入重跑 pytest 时，`--basetemp` 的父目录未先创建，所有测试在 fixture setup 以 `FileNotFoundError` 结束，零测试 body 执行；这是本次命令构造错误，不是产品失败。随后复杂的临时 cross-store probe 被隔离-worktree guard 拒绝，亦未执行。
- 本 reviewer 实际执行了 two no-write probes：当前 shared source 的 ordinary safe projection，以及 exact path derivation；两者均通过。RC-FINAL-03 的当前行为结论来自 source/control audit 与 bytes-bound fix-report evidence，而非本轮新的 filesystem mutation probe。
- `progress.md` 的事实状态由当前文本、new package header 和七个 matched hashes 共同裁决；本报告不推断是谁尚未更新该 ledger。

## Assessment

Ready to merge：With fixes。不能将这轮 scoped re-review 写成 pass，因为用户指定的 RC-FINAL-04 要求的是 single consistent state，而 current progress 仍宣称 shared application pending。修正这一条活文档状态并加入 new-package anchor 后，RC-FINAL-01 至 04 将无剩余 Critical、Important 或 Minor finding；届时只需复核 progress/package binding，不必臆造真实 Copilot canary 或重开全量 review。

## 我最没把握的三个判断

1. RC-FINAL-04 的严重级别维持上一轮 Minor：它破坏的是 recovery/integration metadata，不改变当前 raw-capture wire behavior；但用户将它显式列为本 re-review 的完成条件，所以它仍使当前 scoped verdict 为 needs-fix。
2. fix report 的 focused test outcomes没有由本 reviewer 完整重跑；七个 SHA-256 精确匹配、current source/control inspection和两个无写入 behavior probes使其足以作为有限复审证据，但不替代一份新的 full regression。
3. `final-fix-review-package.md` 本身未携带 live-document hashes；本报告将其视为可由 `task-6-fix-report.md` 的 post-fix hash table补足，而不是将这个布局选择单独升级为新的 finding。真正的当前缺陷是 ledger 未写 shared application 已完成且未锚到新 package。

## 执行本契约时遇到的摩擦

按照用户的只读范围，本 agent 未修改 shared worktree、Git 或仓库内报告；唯一写入是用户指定的 `/tmp/raw-capture-final-rereview.md`。一次尝试以孤立临时目录运行 pytest 的 `--basetemp` 设置错误，未触及测试 body 或共享源码；一次复杂临时 probe 被 harness guard 在执行前拒绝。二者均如实列入 Evidence limits，未被伪装成产品测试结果。

## 交付声明

delivery_complete: true
completed_at: 2026-09-09
finding_total: 1
critical: 0
important: 0
minor: 1

DELIVERY_COMPLETE: true
FINDING_TOTAL: 1
CRITICAL: 0
IMPORTANT: 0
MINOR: 1

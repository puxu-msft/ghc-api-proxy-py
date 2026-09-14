# Raw capture Review disposition

日期：2026-09-14  
当前 Spec：[`spec.md`](spec.md) ACTIVE v25

报告原件保持 point-in-time，不重写。当前状态由 v25 Spec、`status.md` 和本表共同导航。

| 报告 / finding | 当前处置 | current owner / evidence |
|---|---|---|
| `raw-capture-review-2026-09-09-implementation-audit.md` A1-01 | accepted-deferred | [`deferred.md#D-3`](deferred.md)；失败 attempt 与 request-level diagnosis 仍分开处理 |
| 同报告 A1-02 | accepted-deferred | [`deferred.md#D-3`](deferred.md)；driver timeout sent-body hardening |
| 同报告 A1-03 | accepted-deferred | [`deferred.md#D-3`](deferred.md)；count cleanup response boundary |
| 同报告 A1-04 | accepted-deferred | [`deferred.md#D-4`](deferred.md)；准备阶段 warning projection |
| 同报告 A1-05 | accepted-deferred | [`deferred.md#D-3`](deferred.md)；HTTP CRUD/未装配错误 oracle |
| `raw-capture-review-2026-09-09-adversarial-verifier.md` F-01 | superseded/duplicate of A1-01 | 同一 retry/attempt-level request diagnosis 缺口；current disposition 走 [`deferred.md#D-3`](deferred.md) |
| 同报告 F-02 | accepted-deferred | [`deferred.md#D-4`](deferred.md)；完成诊断 reason/安全 warning 的既有 minor |
| 同报告 F-03 | accepted-deferred | [`deferred.md#D-3`](deferred.md)；未装配 rule store 的 HTTP error envelope |
| 同报告 AC-28 | unverified evidence gap | 非流式 aggregate wire path 尚无独立 product oracle；不作为 pass 证据 |
| 同报告 AC-29 | accepted evidence boundary | ordinary safe projection 有当前实现与 targeted tests；独立验收仍可作为后续 test-strengthening |
| `raw-capture-final-rereview-2026-09-09.md` RC-FINAL-01/02/03 | closed | v25 code/tests；报告保留为 point-in-time evidence |
| 同报告 RC-FINAL-04 | superseded | `.superpowers` progress/package 不属于 current dotdev owner；当前状态由本表和 topic status 统一承载 |
| `260909-merged-state-review.md` M-1 | closed | v25 Spec §6 reason enumeration |
| 同报告 M-2 / S-1 | accepted-deferred | [`deferred.md#D-4`](deferred.md) |
| `raw-capture-review-2026-09-09-adversarial-verifier.md` AC-08/09/27 deviations | accepted-deferred | [`deferred.md#D-3`](deferred.md)；AC-28 remains unverified evidence, not a pass claim |
| `260909-coordinator-audit-checklist.md` | methodology/provenance | checklist only; it is not a finding disposition or current gate |
| full-header / credentials | closed | `050f0e3e` + `1c348dfc` |
| capture reference / History attachment | closed | History slices; owners are `history/spec.md` + `raw-capture/spec.md` |
| per-attempt capability matrix | accepted-deferred | [`deferred.md`](deferred.md) and `../history/deferred.md` |
| user-controlled candidate refresh | pending user-controlled flow | [`../../human-controlled-docs-candidates/260914-observability.md`](../../human-controlled-docs-candidates/260914-observability.md) |

旧报告目录：[`reports/`](reports/)。

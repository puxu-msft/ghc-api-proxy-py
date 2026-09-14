# Raw capture — deferred（未采纳与后续候选）

依据：`.dev/docs/raw-capture/spec.md`（ACTIVE v25）；本文件只记录当前仍未采纳的事项与理由，不承载规格事实。下方条目是 review 后仍接受不做的实现 hardening；v25 的 full-header/capability/replay 合同不在此重复。

## D-2 缩短 path 验证的锁持有时间（来源：合并态评审 S-2）

`_validate_existing_path` 在 accounting lock 内做全量 reader 扫描，数百 MB 既有文件的首次 append 会阻塞并发 append。规格 §5 字面要求验证受该锁串行化，实现合规且保守正确。

未采纳理由：先有规格再有实现——缩短锁域需先修订 §5 的表述（锁外读、锁内状态转换），不属于实现侧可自行做出的变更。仅在真实出现大文件首 append 的阻塞证据后再立项。

## D-3 失败 attempt / cleanup boundary hardening

来源：`reports/raw-capture-review-2026-09-09-implementation-audit.md` 的 `raw-capture-impl-audit-20260909-a1-01` 至 `a1-03`，以及 adversarial verifier 的 AC-08/AC-09/AC-27 偏差。

当前处置：**accepted-deferred**。当前 capture 已保留失败 attempt 的事件和实际可观察 body；但 request-level `upstream_incomplete` 判定、driver timeout 的 sent-body 载体、count cleanup 的 response boundary，以及未装配 rule store 的 HTTP error envelope 仍需独立实现切片。不得在 status/ledger 中把这些条目写成 v25 全部闭合。

Current owner：后续 raw-capture implementation slice；本条不是当前 capture 文件格式或普通日志安全边界的修改授权。

## D-4 诊断 warning 白名单收敛

来源：`reports/260909-merged-state-review.md` 的 M-1/M-2 与主观建议 S-1。

当前处置：**accepted-deferred**。reason 枚举已在 v25 Spec 归档为完整集合；准备阶段 warning 仍可进一步收敛为与 writer warning 相同的逐字段安全投影。当前未观察到 payload 回显，不把它升级为本轮 blocker。

## D-5 非流式 aggregate 与管理 HTTP oracle

来源：adversarial verifier 的 AC-25、AC-28、AC-29。

当前处置：**accepted-deferred**。store-level 与主要 capture path 已有测试；独立 HTTP CRUD、非流式 aggregate 的真实 product oracle、以及 ordinary safe projection 的额外反向控制留给后续 test-strengthening slice，不把“未独立验证”写成“已验证通过”。

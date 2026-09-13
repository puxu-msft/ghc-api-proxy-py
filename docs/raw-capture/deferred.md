# Raw capture — deferred（未采纳与后续候选）

依据：`.dev/docs/raw-capture/spec.md`（ACTIVE v24）；本文件只记录当前仍未采纳的事项与理由，不承载规格事实。下方 D-2 是 v23 writer 实现切片遗留的后续候选；v24 的 full-header/capability/replay 合同不在此重复。

## D-2 缩短 path 验证的锁持有时间（来源：合并态评审 S-2）

`_validate_existing_path` 在 accounting lock 内做全量 reader 扫描，数百 MB 既有文件的首次 append 会阻塞并发 append。规格 §5 字面要求验证受该锁串行化，实现合规且保守正确。

未采纳理由：先有规格再有实现——缩短锁域需先修订 §5 的表述（锁外读、锁内状态转换），不属于实现侧可自行做出的变更。仅在真实出现大文件首 append 的阻塞证据后再立项。

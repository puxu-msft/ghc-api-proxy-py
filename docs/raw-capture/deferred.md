# Raw capture — deferred（未采纳与后续候选）

依据：`.dev/docs/raw-capture/spec.md`（ACTIVE v22）；本文件只记录「评审提出、当前未采纳」的事项与理由，不承载规格事实。

## D-1 append() 两个即时 warning 收紧为逐字段白名单（来源：合并态评审 M-2 / S-1）

`raw_capture.py` 中 `append()` 的两处即时 warning（file quota exceeded 的 `%s` path、capture_error 的 `%s` exception）目前用整对象格式化。评审实证当前消息不含 payload（cbor2 消息只含类型、OSError str 只含 hash 形式 path、zstd 错误无 payload），不违反 §4/§6，非行为缺陷。

未采纳理由：纯防御性收紧，且可能牵连多处断言日志文本的测试；本片任务是移除全局配额，扩大改动面会在同伴在飞批次收敛前引入无谓冲突面。 writer warning（逐字段白名单：request_id/event_type/reason/exception_type/errno）是既定口径，未来任何触碰这两行的改动都应顺手对齐。

## D-2 缩短 path 验证的锁持有时间（来源：合并态评审 S-2）

`_validate_existing_path` 在 accounting lock 内做全量 reader 扫描，数百 MB 既有文件的首次 append 会阻塞并发 append。规格 §5 字面要求验证受该锁串行化，实现合规且保守正确。

未采纳理由：先有规格再有实现——缩短锁域需先修订 §5 的表述（锁外读、锁内状态转换），不属于实现侧可自行做出的变更。仅在真实出现大文件首 append 的阻塞证据后再立项。

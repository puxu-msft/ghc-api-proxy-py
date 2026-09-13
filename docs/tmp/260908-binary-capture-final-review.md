# Binary raw capture 与 response-body observability 最终独立复审

## 评审范围

- 基准：当前 `HEAD` 到 `/home/xp/src/ghc-api-proxy-py` 工作树未提交状态。
- 判据来源：用户本轮明确要求；`.dev/docs/raw-capture/spec.md` ACTIVE v2；上轮报告 `.dev/docs/tmp/260908-binary-capture-review.md`；stream body attempt 的任务合同与接口说明 `.dev/docs/tmp/260908-stream-body-logging-agent-report.md`。
- 重点范围：`src/app/observability/raw_capture.py` 及其配置、composition、request completion、stream body attempt 采集/投影/完成行接口与直接测试。
- 明确不在范围：同一工作树中的 reasoning encrypted include、usage normalization、Docker/实验目录及其他无关未提交改动；本报告不评价这些改动。

## 总体 verdict

**needs-fix**。上轮 `capture-writer-ack` finding 的零字节 writer `OSError` 回滚、per-request attribution、ack 等待和安全完成枚举已闭合；但 partial write 会污染同一 `(session_id, agent_id)` 的共享 append stream，而后续另一个 capture 仍会被确认完整，导致完成诊断与实际可读性相反。

## Blocker 数

**0**

## Findings

### `partial-write-poisons-shared-stream` — major — partial frame 后仍写入其他 capture，并把不可读取的后续 capture 报告为完整

- **primary_location**：`src/app/observability/raw_capture.py:178-214`
- **related_locations**：`src/app/observability/raw_capture.py:216-237`、`src/app/observability/raw_capture.py:280-303`、`src/app/observability/raw_capture.py:392-428`、`src/app/observability/raw_capture.py:431-458`
- **判据**：文件按 `(session_id, agent_id)` 由多个 request capture 共享；每个 zstd frame 必须是完整、可逐条读取的 CBOR item。short write 属于 capture 不完整，后续完成诊断不能把实际无法由生产 reader 访问的 capture 声称为完整。
- **事实与复现**：
  1. worker 发现 short write 后按 `persisted_bytes` 保留已写前缀并仅调用失败项所属 `RawRequestCapture.note_writer_frame_completed(..., stored=False)`。
  2. 后续跳过判断是 `item.capture.has_writer_failure()`，只停止同一个 request capture；共享相同 `item.path` 的其他 capture 不知道该文件尾部已有半个 zstd frame，仍会正常 append、获得成功 ack，并且不发 completion warning。
  3. 独立只读探针让第一个 capture 的首个 frame 确定性短写一半，再让第二个 capture 使用相同 session/agent 正常完成。结果是第二个 request 的 incomplete completion warning 数为 **0**，accounting 与实际磁盘大小相等，但 `iter_raw_capture_records()` 对该共享文件抛出 `ZstdError`；第二个 capture 的完整 frames 位于损坏 frame 之后，生产 reader 无法到达。
  4. 现有并发测试只覆盖“不同 path 的 4 个失败 capture + 4 个成功 capture”；没有覆盖同一共享 path 上 partial write 后的其他 capture，因此绿灯无法区分此错误。
- **影响**：一次合法的 short write 不只丢失当前 request 的 frame，还能使同一 session/agent 文件之后所有 request 的事件不可读取；这些后续 request 却没有 `forensic_replay_complete=false` 或 `writer_error`，造成取证完整性的虚假肯定。影响跨 request 且可持续到进程结束，因此定为 major。
- **建议修复方向**：把“此 path 已存在不完整尾 frame”作为 store/file 级失败状态，而非仅 capture 级状态；partial write 后禁止向该 path 继续 append，或安全切换到不会把损坏 frame 留在后续完整 frame 之前的新文件。所有受影响的后续 capture 必须获得稳定、安全的 incomplete 回执。修复后测试需覆盖同 path 多 capture 的 partial-write 顺序，而不只是不同 path 的 mixed success/failure。

## 上轮 finding 完成度

- `capture-writer-ack`：**partially-closed**。普通 `OSError`/零字节失败现已回滚 reservation、归因到对应 capture、等待 ack 并以安全 `writer_error` 枚举报 completion warning；并发不同 path 的成功成本也保持正确。其“partial write 时计数与不完整标记正确”这一承重要求只在失败 capture 自身成立，未覆盖共享文件上的后续 capture，详见 `partial-write-poisons-shared-stream`。

## 其余承重要求

- **reservation accounting 与归因**：除 finding 中的共享文件 partial-write 语义外，未发现新的 accounting race。`queue.put_nowait`、file/total reservation 和 per-capture pending ack 注册在同一个 store lock 临界区内；worker 即使先取到 item，也必须等该临界区释放后才能完成 accounting，因此不会在 pending 注册前回执。失败/跳过项在相同 accounting lock 中回滚未写部分；正常并发探针让 32 个 capture 共享同一路径并完成 96 个 frame，最终 reservation 精确等于文件 `stat().st_size` 且 reader 得到全部 96 条记录。现有 mixed-path success/failure 并发测试连续 5 次通过。
- **writer 错误归因与完成枚举**：queue item 携带 capture、固定 event type 与 reserved cost。零字节 `OSError` 会归因到对应 request，`finish()` 等该 request pending ack 清零后恰好发一次 completion warning；首因使用固定 `writer_error` 或既有 quota/queue/store/capture 枚举，另以 `writer_error=true` 保留后发 writer failure。即时 warning 不格式化异常 message，只记录 request ID、固定 event type、exception type 与 errno。未发现新增 body、header、token 或原始 session/agent identity 进入普通日志。
- **partial write accounting 本身**：short write 已写前缀继续计入 file/total 实际成本，未写部分会回滚；独立探针确认 accounting 等于实际文件大小。问题不是字节成本虚增，而是该不完整 zstd frame 污染共享流后，其他 capture 仍被虚假确认完整，详见 finding。
- **CBOR Sequence + zstd 合同**：生产路径由 `cbor2.dumps(..., canonical=True)` 直接生成 map，body 保持 CBOR native byte string；每条 item 独立压成完整 zstd frame并 append 到 `.cborseq.zst`。代码搜索未见 JSON/JSONL、Base64 或私有长度前缀编码路径；`.jsonl.zst` 仅作为 legacy 文件后缀参与初始 total quota。独立 generic `zstandard` + `cbor2.CBORDecoder` 探针得到 3 个连续 map，body 类型为 `bytes`。
- **reader**：reader 逐 frame 使用 `decompressobj.eof`/`unused_data`，要求每个 frame 恰有一个顶层 map，并拒绝截断 frame、额外 item 与非 map。finding 展示的是 writer 把 partial frame 从“尾部”变成“中部”后 reader 必然无法越过，并非 reader 把损坏数据误判为完整。
- **stream body attempt 接口**：三个生产 `_counted_upstream` 接线点均传入 status code；每次实际 pull 建立 attempt-local 计数，EOF 标记 `complete`，普通 body exception 标记 `error`，仅持久化字节/chunk 计数、monotonic 相对时间及 exception module/type。`FinalizedRequest` 冻结 tuple，schema v2 投影和最终 completion formatter使用同一 tuple。单次正常成功不扩展完成行；多 attempt 或 error 以一致 `<attempt>:<status>/<bytes>/<outcome>@<elapsed>` 形式报告。三次真实 ASGI replay 的集成测试覆盖 nonzero-byte timeout、zero-byte timeout 与最终成功，且验证 attempt 投影不含正文。

## 执行与搜索面

### 阅读与静态核对

- 先读用户判据、ACTIVE v2 raw-capture spec、上轮独立复审及 body-attempt 任务合同，再读实现。
- 完整阅读 `src/app/observability/raw_capture.py` 和 `tests/unit/observability/test_raw_capture.py`。
- 跟踪 `RequestCompletionCoordinator` 的 capture lifecycle、finalization、structured record 与 completion line；跟踪 `_counted_upstream` 的全部初次/replay/one-shot 接线和 body pull 的 EOF/error/cleanup路径。
- 核对 config/composition/dependency lock；搜索目标实现中全部 logging call、JSON/Base64/length-prefix 痕迹及 formatter/capture 调用点。
- 边界检查当前全部 modified/untracked 文件；未评无关实现，也未读取或输出已有 capture 原文或秘密。

### 实际验证

- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py tests/unit/observability/test_response_observation_projection.py`：**154 passed**。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture or successful_header_attempt'`：**3 passed, 273 deselected**。
- mixed-path 并发 reservation test 连续 5 次：每次 **1 passed**。
- `ruff check`（直接相关 implementation/tests）：**All checks passed**。
- `pyright`（直接相关 implementation 与 raw-capture tests）：**0 errors, 0 warnings, 0 informations**。
- `git diff --check`：通过；`uv lock --check`：通过。
- 独立正常同 path 32-capture 并发探针：**96/96 records 可读，accounting 等于实际磁盘大小**。
- 独立 generic CBOR Sequence decoder 探针：**3 maps，native `bytes` body，`.cborseq.zst` suffix**。
- 独立同 path partial-write 对抗探针：第二个 capture **0 条 incomplete completion warning**，accounting 等于实际磁盘大小，但生产 reader 抛出 **`ZstdError`**；由此闭合本报告唯一 finding。

## 未验证项

- 未在真实磁盘上制造 ENOSPC、权限在途变化或内核级 short write；零字节 writer failure 使用现有确定性 ENOTDIR 测试，partial write 使用返回真实短写计数的受控 unbuffered stream 替身，均穿过生产 worker/accounting/ack/reader 路径。
- 未验证多进程同时向同一 capture path 追加；现有合同和 composition 是单进程 store/worker。
- 未对范围外的未提交改动作质量结论。

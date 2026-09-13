# Binary capture closeout review

## 评审范围

审查当前未提交改动中 `raw capture` 的 CBOR Sequence + independently appendable zstd frames、reader、writer queue/lock/ack/accounting/close 状态机、同路径 partial-write poisoning、普通日志敏感信息边界，以及 `upstream_body_attempts` 的采集、结构化投影、console projection 与直接测试。明确不评审同一工作树里与上述合同无关的 reasoning subscriber、translation codec、Docker/experimental 资产。

## 总体 verdict

**needs-fix**。已确认同一 `RawCaptureStore` 生命周期内的 short write 会阻止同路径已排队和后来提交的 append；但 poisoned 状态只存在内存中，重启后同一路径会继续 append，并把后续请求虚假报告为完整。

## Blocker 数

0

## Findings

### RC-1 — `major` — poisoned path 在 store/process 重建后失忆，后续请求继续 append 且无 incomplete 诊断

- `finding_id`: `RC-1`
- `severity`: `major`
- `primary_location`: `src/app/observability/raw_capture.py:59`
- `related_locations`: `src/app/observability/raw_capture.py:135`, `src/app/observability/raw_capture.py:231`, `tests/unit/observability/test_raw_capture.py:310`
- `status`: `open`
- **判据**：用户合同要求同路径 short write 后不再 append，后续请求必须明确 `path_poisoned`，不得出现虚假完整。
- **证据**：`_poisoned_paths` 在 `RawCaptureStore.__init__` 中总是初始化为空集；启动时只扫描既有文件大小，不验证尾帧，也没有持久化 poison marker。`append()` 因而只会对当前实例内观察到的 poison 返回 `path_poisoned`。现有 direct test 仅在同一个 store 实例内发起第二个请求，未覆盖 store/process 重建。
- **执行复现**：先用 short-writing stream 让首个 `request.start` 只落下半个 zstd frame，完成并关闭首个 store；随后对同一 root、session、agent 新建 store 并完成第二个请求。探针只输出布尔状态，结果为 `grew_after_restart=True`、`second_reported_incomplete=False`、`second_reported_path_poisoned=False`，未读取或输出 capture 内容。
- **影响**：重启后的完整 frames 会被追加到已截断 frame 之后；reader 在损坏处停止，后续 capture 实际不可达，但第二个请求没有任何 incomplete/poison 诊断，形成虚假完整。partial write 常与磁盘或进程异常相邻，因此“写坏后重启”是该故障模式的直接恢复路径，不是独立的假设性场景。
- **修复方向**：在允许 append 前让 poison 能跨实例恢复，例如原子持久化 per-path poison marker，或启动/首次使用路径时验证所有 zstd frames 且把截断/损坏尾部标记为 poisoned；补一个关闭首个 store、重建第二个 store 的 direct test，断言文件尺寸不再增长、后续请求为 `path_poisoned` 且 `forensic_replay_complete=false`。

## 前两轮发现复核

1. **writer `OSError` 回滚与请求归因：`closed`。** Writer completion 在 store lock 下按当前 item 的 `reserved_bytes - persisted_bytes` 回滚，不会重算并覆盖并发 path 的成本；失败诊断携带对应 `request_id`/event type，而不带 body、session/agent identity。现有 concurrent successful-cost direct test、writer-error direct test均通过。
2. **partial write 污染共享 path 后续 capture：`partially-closed`。** 同一 store 内已闭合：short write 先记录实际 partial size 并 poison path；worker 对已经排队的同路径 items 在写前检查 poison，后来提交的 items 在 `append()` reservation 前被拒绝；request-local ack 最终归零，首个失败请求保持 `writer_error`，其他请求明确 `path_poisoned`，文件不再增长。对抗探针让 first write 阻塞、在 poison 落锁前排入第二个请求并并发 `finish()`，之后再发第三个请求，结果两条后续路径均 `path_poisoned`、pending 均为 0、poison 后尺寸不增长。跨 store/process 生命周期仍由 `RC-1` 打开。

## 其余合同核验

- **格式与 reader**：writer 使用 canonical `cbor2.dumps()`，body 保持 CBOR byte string；每个 item 独立压入一个 zstd frame，文件名为 `.cborseq.zst`。reader 逐 frame 解压，要求每 frame 恰好一个 CBOR map，并对截断 frame 报错。新写路径没有 JSONL、base64 body 或 length-prefixed JSON；唯一 `.jsonl.zst` 引用仅用于把既有 legacy 文件计入总 quota。
- **queue/lock/ack/accounting/close**：同一 store 的 enqueue reservation、worker completion release、capture ack 和 path poison 均在明确锁序下完成；对抗排队探针未见死锁、负 pending、poison 后 append 或成本漂移。`close()` 先原子拒绝新 append，再 `queue.join()`，之后放 sentinel 并 join writer；已接受 work 在返回前得到 ack。未发现这一生命周期内的高置信竞态缺陷。
- **普通日志敏感边界**：raw-capture warnings 只携带 request id、event kind、safe reason、exception type/errno、hashed capture path/root 与 completeness flags；direct tests/探针确认 synthetic body/session markers不进入 warnings。Body-attempt console projection只含 attempt、status、byte count、outcome 和 elapsed time；结构化字段只增加 timing/count/outcome/exception class identity，不保存 upstream body 或 exception message。
- **body-attempt 一致性**：每次收到成功 headers 时建立一条 attempt-local record；pull/chunk/EOF/error 更新同一条 immutable replacement，结构化 projection 的 14 个字段与 integration assertion一致。三次 200 body attempts（首个有 bytes 后 timeout、次个零 bytes 后 timeout、第三个完整）得到预期的 `(bytes, chunks, outcome, exception type)`，console `body-attempts=` 与结构化数据一致。

## 搜索面

### 已读

- `src/app/observability/raw_capture.py` 最终状态与完整 change diff。
- `src/app/observability/request_completion.py`、`request_log.py`、`request_trace.py` 中 capture completion、structured projection、console projection 与 attempt-local timing 状态机。
- `src/app/server/routes/inference.py`、`src/app/pipeline/driver.py`、`src/app/pipeline/direct_driver/base.py` 的生产采集、retry/reopen、EOF/error/cleanup 与 attempt 归因调用点。
- `src/app/core/chain.py`、`src/app/server/composition.py`、`src/app/config/schema.py`、`docs/.human-controlled/config.example.yaml` 的构造、shutdown 与用户可见格式合同。
- `tests/unit/observability/test_raw_capture.py`、request completion/projection tests、request-log/stream-delivery tests，以及 `tests/int/test_pipeline_app.py` 中 raw capture 与 body-attempt direct integration cases。

### 已执行

- `uv run pytest -q tests/unit/observability`：231 passed。
- `uv run pytest -q tests/unit/pipeline/delivery/test_stream_delivery.py tests/unit/observability/test_request_log.py`：165 passed。
- raw capture/request completion/projection targeted unit set：135 passed。
- raw capture + body-attempt targeted integration set：3 passed。
- direct capture failure/format subset：6 passed。
- `uv run pytest -q tests/unit/test_module_boundaries.py`：6 passed。
- `uv run ruff check ...`：通过。
- `uv run pyright ...`：0 errors。
- `uv lock --check`、`git diff --check`：通过。
- 两个不落盘、不打印 capture 内容的 synthetic 对抗探针：同-store poison 排队竞态通过；跨-store restart 复现 `RC-1`。

### 未覆盖

- 未运行全仓完整 test suite；本次执行覆盖了改动承重路径及其直接集成测试。
- 未做真实磁盘故障注入或进程 crash；short write 使用与仓内 direct test同形的 stream wrapper，跨实例恢复使用正常 `close()` 后重建 store，已经足以证明 poison 状态未持久化这一确定性状态机缺口。

# Binary raw capture + stream body-attempt observability 独立只读验收

## 评审范围

- 被检对象：`/home/xp/src/ghc-api-proxy-py` 当前工作树中与 raw capture 的 CBOR Sequence + zstd 落盘、writer 失败归因/配额、partial-write poison/restart validation，以及 stream `upstream_body_attempts` 结构化记录和普通 completion line 投影直接相关的未提交改动。
- 主要实现文件：`src/app/observability/raw_capture.py`、`request_completion.py`、`request_log.py`、`request_trace.py`、`src/app/server/routes/inference.py`、`src/app/server/composition.py`、`src/app/core/chain.py`、`src/app/pipeline/driver.py`、`src/app/pipeline/direct_driver/base.py`。
- 主要测试/契约文件：`tests/unit/observability/test_raw_capture.py`、`test_request_completion.py`、`test_response_observation_projection.py`、`tests/unit/pipeline/test_response_observation.py`、`tests/unit/pipeline/delivery/test_stream_delivery.py`、`tests/int/test_pipeline_app.py`、`docs/.human-controlled/config.example.yaml`、`src/app/config/schema.py`、`pyproject.toml`。
- 明确不在范围：同一工作树中 model resolution、reasoning include、translation codec、Docker/experiment/worktree 等不属于本次合同的其他未提交改动；未运行整个 repository test suite，也未接触真实 capture、credential 或上游服务。

## 总体 verdict

**pass**

## Blocker 数

**0**

## Findings

未发现高置信 bug。

## 硬性合同核验

### 1. 新 raw capture 是二进制结构化格式，不是 JSONL 或长度前缀 JSON

- `RawCaptureStore.append()` 以 `cbor2.dumps(..., canonical=True)` 产生一个原生 CBOR map，其中 body 保持 CBOR byte string；随后将每个 item 压成独立 zstd frame，并追加到 `.cborseq.zst`。
- 路径后缀固定为 `.cborseq.zst`；旧 `.jsonl.zst` 只参与历史占用量统计，不会成为新写入目标。
- `iter_raw_capture_records()` 逐个解出 concatenated zstd frame，要求每 frame 恰有一个 CBOR item且为 map；截断 frame、frame 内多 item、非 map 均拒绝。
- 单元测试明确检查解压后的首项为 CBOR map major type、不是 `{` 开头、binary body 原样 round-trip，且没有新 `.jsonl.zst`。

### 2. 普通日志不带 raw body/header/token

- 本轮新增的 body-attempt 普通日志只投影 attempt index、HTTP status、累计 byte count、outcome 与相对结束时间。
- 结构化 `upstream_body_attempts` 只包含 timing、byte/chunk count、outcome、exception module/type；不包含 exception message、body、headers 或 token/credential。
- raw capture 失败日志只使用 hashed path、request id、event type、reason、exception type/errno 和布尔完整性元数据。
- 现有隐私断言使用独特 body/credential marker，覆盖 quota、writer error、same-store partial write、restart poison；body-attempt integration test另断言 SSE payload marker不进入结构化 attempt projection。

## 前轮三个修复逐条完成度

### writer error attribution/accounting — closed

- 每个 queued frame携带原 capture、event type及预留压缩字节数。
- worker 写失败通过 `_complete_write()` 回写到正确的 `RawRequestCapture`，设置首个 drop reason / writer error event，释放未持久化 reservation；`finish()` 等待本 request 的 pending writes归零后再发布安全的不完整诊断。
- 并发成功/失败 session 的测试核对 `_reserved_file_bytes` 与实际成功文件 size逐 path一致，并核对 `_reserved_total_bytes` 为成功文件之和。

### partial write 同 store path poison — closed

- `0 < persisted_bytes < reserved_bytes` 时在 store lock内 poison该 path；后续同 path frame在写前被拒绝并分别回写 `path_poisoned`。
- 已排队的同 request后续 frame因 writer failure被拒绝；其他 request 的同 path frame因 path poison被拒绝。它们均完成 pending accounting，`finish()` 不会先于失败归因返回。
- 测试确认第二个 request 不再增加损坏文件、两个 request分别报告 `writer_error` / `path_poisoned`，并且损坏文件读取失败而不是被误判为完整。

### partial write 重启后 path validation — closed

- 新 store 对目标 `.cborseq.zst` path 的第一次 append在持有 store lock时完整迭代既有 records；截断 zstd tail、非法 CBOR、frame多 item或非 map会 poison path，append不进入 queue。
- 合法既有 concatenated frame文件仍可追加：现有 restart测试覆盖两个 store顺序写同一文件并读取四条 records；额外 synthetic probe覆盖不同 compression level、checksum和无 content-size选项组成的两个合法 concatenated zstd frames。
- 旧 committed 格式使用不同的 `.jsonl.zst` 后缀；代码和额外 probe确认它保持原样、新 CBOR capture写到独立路径。旧文件仍计入 `max_total_bytes`，已有单元测试覆盖。
- 未发现 validation 把本仓可生成的合法 concatenated frames、schema version 1/2 CBOR map或旧 `.jsonl.zst` 误判损坏的路径。

## 当前系统状态复核

### 不可读 capture 是否仍可能被报告 complete

- 正常 writer 路径中，`RawRequestCapture.finish()` 先尝试 queue `request.end`，再等待该 capture 的 `_pending_writes == 0`；worker failure会在递减 pending前设置 drop状态。因此 partial write或任何被 worker观察到的 `OSError` 不能越过等待并静默完成。
- partial write保留实际写入字节作为 quota成本并 poison path；其余未写 reservation被释放。重启后同 path在任何新 frame入队前重新验证。
- queue full、quota、store closed、validation poison、encode/compress/I/O失败均会 disable该 capture并在 request completion输出 `forensic_replay_complete=false`；后续未捕获 event type也被记录，用于安全的 response-body完整性布尔值。
- 未发现由本进程正常 API 路径产生、文件已不可读但 request completion仍不带不完整诊断的高置信路径。

### lock / queue / close

- append在同一 store lock内完成 closed检查、path首次验证、quota检查、queue admission和reservation/pending登记；worker completion也通过同一 lock更新 poison与reservation，避免成功/失败 path之间的 lost update。
- worker可能在 `put_nowait()` 后立即取 item，但 `_complete_write()` 需要同一 lock；因此 pending计数会在 worker归零前完成登记。
- `close()` 先在 lock内阻止新 append，再 `queue.join()` 等完所有已接纳 frame，最后入 sentinel并 join worker；不存在 sentinel越过已接纳 frame的路径。
- 生产所有权为 `Chain.aclose()`，在 request lifecycle结束后同步关闭 raw capture，再关闭 provider clients；未发现生产调用图中并发多 owner close或 lock-order环。

### stream body-attempt observability

- 每个实际开始拉取的 upstream streaming body调用 `begin_upstream_body_timing()` 创建独立 immutable attempt snapshot；replay会新建 entry并重置 latest-attempt timing companions。
- 每次 pull记录开始时间；chunk只累计 byte/chunk安全元数据；EOF记 `complete`，普通读取异常记 `error`及 exception module/type，cancellation/下游提前关闭保持 `open`，不会伪称 upstream body正常结束。
- raw capture attempt start由 driver记录，buffered response在完整 body已取得后结束，streaming response由 `_counted_upstream()` finally按 EOF结果结束；replay使用实际 attempt index。
- integration test覆盖三次 HTTP 200 header attempt：第一条有 bytes后 ReadTimeout、第二条零 bytes ReadTimeout、第三条成功；结构化 record和普通 line均逐 attempt准确投影，且没有 payload内容。

## 执行证据

所有 shell命令均以 `cd /home/xp/src/ghc-api-proxy-py &&` 开头。

- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_response_observation_projection.py tests/unit/pipeline/test_response_observation.py` → **137 passed**。
- `uv run pytest -q tests/int/test_pipeline_app.py::test_each_successful_header_attempt_records_its_body_progress_before_read_timeout` → **1 passed**。
- raw capture integration/config/body-attempt reset四项 targeted tests → **4 passed**。
- synthetic concatenated-zstd validation probe → **pass**；覆盖不同合法 frame选项与 schema 1/2 map。
- synthetic legacy `.jsonl.zst` isolation probe → **pass**。
- `uv run ruff check`（本次主要实现/测试文件）→ **All checks passed**。
- `git diff --check` → exit 0。

## 搜索面与限制

- 审阅了当前最终状态而不只看 diff，并回看 `HEAD` 中旧 raw capture实现以确认旧文件后缀/格式。
- 沿 request body、direct driver attempt、buffered response、stream delivery/replay、ASGI send、completion publish、Chain shutdown调用链核对 capture开始/结束与 ownership。
- 针对 restart validation检查了截断 tail、完整已有 stream、合法 concatenated zstd frames、旧 JSONL隔离与quota；针对并发检查了 reservation、poison、pending write、queue sentinel及close顺序。
- 未做真实磁盘故障注入、跨进程同时写同一 capture root或全仓测试；本项目生产构造与 shutdown调用图未显示多进程共享 writer或并发 close合同，因此这些不构成本次高置信 finding。

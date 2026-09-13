# Binary raw capture 独立只读审查

## 评审范围

- 基准：当前 `HEAD` `e593cf0c` 到工作树未提交状态。
- 判据来源：用户本轮明确要求——SSE raw capture 必须是二进制结构化文件，禁止 JSONL 与“长度前缀 JSON”；候选采用 CBOR Sequence + zstd；append/读取须跨 zstd frame 正确；配额与失败语义不得让诊断静默丢失；普通完成日志不得泄漏正文、headers 或令牌；实现、接口与测试须一致。
- 直接审查文件：`pyproject.toml`、`uv.lock`（依赖一致性核对）、`docs/.human-controlled/config.example.yaml`、`src/app/config/schema.py`、`src/app/observability/raw_capture.py`、`src/app/observability/request_completion.py`、`src/app/observability/request_log.py`、`src/app/observability/request_trace.py`、`src/app/server/composition.py`、`src/app/server/routes/inference.py`，以及对应 unit/integration tests。
- 边界检查但不纳入目标结论：同一工作树中的 reasoning include、usage normalization、Docker/实验目录、历史文档路径调整等无关未提交改动。

## 总体 verdict

**needs-fix**。格式、跨 frame 读取与普通完成日志的敏感数据边界已通过本轮静态检查和独立探针；但异步 writer 的真实落盘失败没有反馈给对应 capture，能把已接受但未写入的事件继续当作完整 capture，并使配额永久计入并不存在的字节。

## Blocker 数

**0**

## Findings

### `capture-writer-ack` — major — 异步写入失败既不回滚配额，也不把 capture 标记为不完整

- **primary_location**：`src/app/observability/raw_capture.py:156-169`
- **related_locations**：`src/app/observability/raw_capture.py:113-143`、`src/app/observability/raw_capture.py:196-207`、`src/app/observability/raw_capture.py:294-318`
- **判据**：capture 的丢失必须能可靠归因到具体请求并在请求完成时报告；配额若宣称按实际压缩写入成本计数，就不能永久保留从未写入的预约字节。
- **事实与复现**：
  1. `append()` 在把 `(path, compressed)` 放入 queue 后立即增加 `_reserved_file_bytes` / `_reserved_total_bytes` 并返回成功。
  2. `_write_loop()` 随后才执行 `mkdir/open/write`；其 `OSError` 分支只写一条不含 `request_id`/event 的普通 warning，没有回滚预约，也没有任何通道把失败通知 `RawRequestCapture`。
  3. 因此 `RawRequestCapture._drop_reason` 仍为 `None`，`finish()` 不发出 `raw request capture incomplete at request completion`。
  4. 独立探针以“capture root 实际为普通文件”稳定触发 writer `ENOTDIR`：`request.start` 与 `request.end` 均被 `append()` 接受、均未落盘，capture 仍保持 `_drop_reason is None`；输出只有两条无法关联具体请求的 writer warning。该探针没有读取或输出任何 capture 正文。
- **影响**：磁盘权限变化、目录异常、磁盘满等真实 writer 故障会让一个或多个请求的取证文件缺事件甚至完全不存在，而这些请求的完成日志仍不声明 capture 不完整；同时未写入字节继续消耗 file/total quota，可能进一步诱发后续 quota drop。对于明确以“不会再次静默丢失诊断”为目标的功能，这是核心可靠性缺口。
- **建议修复方向**：queue item 应携带可回执的 capture/event 身份；writer 成功后再确认实际成本，失败时原子回滚未写入部分并把首个失败传播到对应 `RawRequestCapture`，使请求完成诊断能安全报告 `writer_error`。若选择保留 reservation 语义，也至少必须区分 reserved 与 committed，并证明 partial write 时的计数与不完整标记正确。

## 其余承重要求的结论

- **确为 CBOR Sequence，而非 JSON/JSONL/长度前缀 JSON**：`cbor2.dumps(..., canonical=True)` 直接编码 map；body 是 CBOR native byte string；每个 zstd frame 解压后恰有一个 CBOR item。独立 generic `cbor2.CBORDecoder` 探针读出 3 个连续 map，并确认二进制 body 保持 `bytes`。未发现 JSON 编码或 `.jsonl.zst` 新文件写入路径；legacy suffix 只用于把旧文件的实际大小纳入 total quota。
- **append 与跨 zstd frame 读取**：每个事件先形成完整独立 zstd frame，再以 `ab` 追加；reader 正确使用 `decompressobj.eof` 与 `unused_data` 进入下一 frame，并拒绝截断尾 frame及单 frame 内额外 CBOR item。额外探针使用不可压缩的 150,000-byte body，使文件超过 64 KiB read chunk；generic decoder 与项目 reader 均得到相同 3 条记录。未发现跨 frame 读取错误。
- **成功写入时的配额成本**：append 前按将要追加的 `len(compressed)` 预约，独立探针确认正常写入后 `path.stat().st_size == _reserved_total_bytes`；legacy 与新 suffix 的既有文件均按 `stat().st_size` 纳入初始 total。除 `capture-writer-ack` 所述 writer 失败路径外，未发现 quota 比较使用 uncompressed/JSON 长度的问题。
- **普通日志敏感数据边界**：新 completion line 与 finalized record 只加入 attempt number、status、相对时间、byte/chunk count、outcome、exception module/type；不加入 body、headers、exception message 或 credential。quota completion warning 只含 `request_id`、枚举 reason、event type 与布尔完整性。相关测试使用秘密 marker 验证 warning 不含正文；多次 body-attempt integration test也验证 attempt 结构与普通完成行不含 SSE 内容。未发现本轮新增的正文、headers 或令牌泄漏。
- **接口与测试**：`RawCaptureStore.append()` 的 tuple 返回只由 `RawRequestCapture.append_event()` 消费；server composition/config、capture lifecycle、finalized record、completion formatter和 body-attempt call sites一致。`cbor2` 同时存在于 `pyproject.toml` 与 `uv.lock`，`uv lock --check` 通过。除上述 writer failure 缺口外，未发现直接相关接口/测试不一致。

## 执行与搜索面

### 阅读/静态核对

- 完整阅读 `src/app/observability/raw_capture.py`，并逐段跟踪其 config、composition、request lifecycle、upstream event wiring与 shutdown close。
- 阅读 `request_trace.py` 的 attempt state methods、`request_log.py` 的 completion formatter、`request_completion.py` 的 capture/finalized record投影，以及 `inference.py::_counted_upstream` 的所有开始、chunk、EOF、error与 cleanup路径。
- 阅读直接相关 diff和 tests；对工作树全部 modified/untracked 项先做边界检查，未把无关 reasoning include、usage normalization、Docker/实验内容混入结论。
- 枚举 reviewed modules 的所有新增/相关 logging call 与敏感字段引用；未输出任何 capture 原文或密钥。

### 实际验证

- `uv run pytest -q tests/unit/observability`：**228 passed**。
- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/observability/test_request_completion.py tests/unit/observability/test_request_log.py`：**148 passed**。
- `uv run pytest -q tests/unit/config/test_config_schema.py::test_raw_capture_is_opt_in_and_has_a_bounded_compression_level`：**1 passed**。
- `uv run pytest -q tests/int/test_pipeline_app.py`：**276 passed**。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture or successful_header_attempt'`：**3 passed**。
- `uv run pyright`（直接相关 implementation files）：**0 errors, 0 warnings**。
- `uv run ruff check`（直接相关 implementation/tests）：**All checks passed**。
- `git diff --check`：通过。
- `uv lock --check`：通过。
- 独立 binary format / >64 KiB concatenated-frame / actual-size quota / writer-error probes：前三项通过；writer-error probe稳定复现 `capture-writer-ack`。

### 非目标失败

一次包含整个 `tests/unit/config/test_config_schema.py` 的组合命令得到 **206 passed, 1 failed**；失败是 authoritative example 中现存的 `exposed_models`、`sub2api.token_file/api_base_url`、`reasoning_encrypted_content` 与同一工作树其他未提交 schema 改动不一致，和本次 raw capture / body-attempt 目标无直接关系，故未作为本报告 finding。直接相关 raw capture config test 已单独通过。

## 未验证项

- 未做真实磁盘满/权限在途变化测试；使用确定性的 `ENOTDIR` 触发了同一个 `_write_loop` `OSError` 分支，已足以闭合 finding，但未枚举所有 OS error。
- 未做多进程同时向同一 capture path 追加的验证；当前目标与现有单进程 lifecycle 没有给出跨进程并发契约。
- 未对无关未提交改动作完整质量评审。

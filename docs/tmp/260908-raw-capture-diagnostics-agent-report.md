# Raw capture 二进制格式与配额诊断实施报告

> 本报告前半保留 2026-09-08 第一阶段“配额诊断”调查链；后半记录用户随后作出的二进制格式裁决及完整落实。后半的最终范围与验证结果取代第一阶段的临时范围统计。

## 范围与约束

- 目标：当 raw capture 因单文件或总量配额停止记录时，在请求完成阶段留下不含密钥和原始正文的明确诊断，并说明响应正文取证可能不完整。
- 不修改 stream-body timeout 日志字段。
- 工作树已有多处无关修改；本次仅触碰 raw capture 实现、其聚焦单元测试和本报告。

## 初始审查

`RawCaptureStore.append()` 在配额、队列、关闭或写入准备失败时只返回 `False`。`RawRequestCapture.append_event()` 随即将 `_enabled` 置为 `False`，但不保存失败原因；后续事件（包括 `request.end`）全部静默跳过。现有即时 warning 只说明某路径或根目录配额已满，既没有 request 关联，也没有在请求完成时说明响应正文证据是否缺失。因此，文件中只剩 `request.start` 时，HTTP 200 完成后无法从完成诊断判断 raw capture 已失效及其取证影响。

## 假设

1. 首次 append 失败原因未保存在 per-request capture 中，且 disabled 状态让 `finish()` 无法发出完成诊断，这是主要原因。
2. 请求完成发布顺序可能让 capture 状态来不及进入普通完成记录。
3. 异步 writer 失败可能造成与配额失败相同的表象，但已知案例由同步 reservation 配额检查直接触发，优先级较低。

## 验证计划

新增聚焦单元测试：设置一个只够容纳 `request.start`、不足以容纳后续大正文事件的单文件配额；继续模拟 upstream/client 200 响应并调用 `finish()`；断言完成阶段 warning 包含 request ID、安全的失败原因、首个丢失事件和响应正文取证不完整标记，同时断言日志不含测试正文。

## 红灯复现

运行：

```text
uv run pytest -q tests/unit/observability/test_raw_capture.py::test_quota_drop_is_reported_safely_at_request_completion
```

修复前结果为 `1 failed`。磁盘 capture 只写入 `request.start`，现有日志只有即时的 file quota warning；测试找不到任何请求完成阶段的 incomplete 诊断。这直接复现了目标症状，单次约 0.22 秒，确定且无需外部服务。

## 实施

仅修改 `src/app/observability/raw_capture.py`：

1. `RawCaptureStore.append()` 除成功布尔值外返回稳定、安全的失败原因：`file_quota_exceeded`、`total_quota_exceeded`、`writer_queue_full`、`store_closed` 或 `capture_error`。这些值不包含路径、身份、header 或正文。
2. `RawRequestCapture` 在首次失败时保存失败原因、首个丢失事件类型，并以集合跟踪 disabled 后被跳过的事件类型。集合只保存固定事件名，不保存事件 payload。
3. `finish()` 仍保持幂等；完成时若 capture 已不完整，额外发出一次 warning，字段包括 `request_id`、失败原因、首个丢失事件、`response_body_capture_complete` 和 `forensic_replay_complete=false`。目标案例会明确得到 `reason=file_quota_exceeded`、`first_dropped_event=request.body`、`response_body_capture_complete=false`。
4. warning 不包含 session/agent identity、认证 header、token、raw request/response body 或上游错误正文。既有即时 quota warning 保持不变。

没有修改 `request_log.py`、请求的 stream-body timeout 字段、配置 schema、pipeline 或 server 代码。`RequestAccounting` 现有完成路径已在发布 finalized request 前调用 `raw_capture.finish()`，因此无需扩大改动面。

## 测试覆盖

`tests/unit/observability/test_raw_capture.py` 新增参数化回归测试，分别覆盖：

- 单文件配额耗尽：`reason=file_quota_exceeded`；
- 总量配额耗尽：`reason=total_quota_exceeded`；
- 实际 capture 文件仅保留 `request.start`；
- 完成诊断恰好出现一次；
- HTTP 200 后的 upstream/client response body 均因禁用而缺失时，`response_body_capture_complete=false`；
- 普通日志不包含测试正文。

## 验证结果

- `uv run pytest -q tests/unit/observability/test_raw_capture.py`：`4 passed`。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture'`：`2 passed, 273 deselected`；仅有第三方 Starlette deprecation warning。
- `uv run ruff check src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py`：通过。
- `uv run pyright src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py`：`0 errors, 0 warnings, 0 informations`。
- 聚焦 grep 确认本次两个代码/测试文件没有 stream-body timeout 字段。

## 独立审查结论

本改动在不把 raw 内容复制到普通日志的前提下，把同步可判定的 quota 丢失状态带到 per-request completion。它不尝试把诊断重新写入已经满额的 raw capture 文件，因此不会再次被同一配额吞掉；也不改变 capture 配额计算或轮转策略，避免扩大到数据保留策略。异步 worker 在 reservation 成功后发生的底层写盘错误仍无法反向归因到具体 request，这不是已知的 quota-full 症状，也不在本次最小修复范围内。

## 工作树隔离

开始时工作树已有多处修改与未跟踪文件，其中包括另一代理负责的 observability、pipeline、server 和 stream timeout 相关工作。本次只新增/修改：

- `src/app/observability/raw_capture.py`
- `tests/unit/observability/test_raw_capture.py`
- `.dev/docs/tmp/260908-raw-capture-diagnostics-agent-report.md`

未改动、还原、暂存或清理任何既有脏改动。

---

## 第二阶段：用户二进制格式裁决

### 明确裁决

用户于 2026-09-08 进一步裁决：raw capture 必须使用二进制结构化文件，绝不能继续使用 JSONL，也不能用长度前缀 JSON 冒充二进制格式；要求同步更新权威 Spec、生产实现、配置/路径/测试和直接相关文档，同时保留配额完成诊断且不得把 raw body 或密钥写入普通日志。

### 权威文档定位与修订

审查发现：

- `docs/.human-controlled/README.md` 清单提到 `observability.md`，但主工作树与 `HEAD` 均没有该文件。
- `.dev/human-controlled-docs-candidates/raw-capture.md` 是既有唯一完整格式描述，但它是未追踪的候选材料，不足以承担权威合同；其中明确写的是 Base64-in-JSONL。
- `.dev/docs/direct-passthrough/spec.md` §6.5.6 是“account-switch 两个 attempt 必须采哪些 request/response body”的行为权威，但不适合拥有通用文件编码。

因此建立 `.dev/docs/raw-capture/spec.md` 作为 `observability.raw_capture` 文件格式、路径、配额、reader、安全与失败诊断的 ACTIVE v1 唯一权威规格，并完成以下联动：

- 独立 Spec 逐字记录本次用户裁决和 2026-09-08 v1 修订；
- `.dev/docs/direct-passthrough/spec.md` 升到 v29，保留“采什么”的归属并把“怎么落盘”唯一指向 raw-capture Spec；
- `.dev/human-controlled-docs-candidates/raw-capture.md` 删除旧 Base64-in-JSONL 描述，改为二进制格式并链接权威 Spec；
- `docs/.human-controlled/config.example.yaml` 增加 opt-in 配置、安全提示、`.cborseq.zst` 路径和压缩后字节配额语义。该文件通常由用户控制，但本轮用户明确要求更新权威 Spec 与直接相关配置文档，故按本次逐项授权修改。

### 格式设计

采用 **RFC 8742 CBOR Sequence + concatenated zstd frames**：

- 每条事件是一个完整 CBOR map，不是 JSON；
- body 使用 CBOR native byte string，不再 Base64；
- 每个 CBOR item 单独压成一个完整 zstd frame，再 append 到同一文件；
- 新路径固定为 `session-<hash>/agent-<hash>.cborseq.zst`；
- schema version 从 1 提升到 2；
- 生产 reader 逐个验证 zstd frame，每个 frame 必须恰好包含一个 CBOR item，顶层必须是 map；
- reader 遇到截断尾 frame 明确报错，同时已完整的前序 frame 仍可逐条读出，不把损坏尾部静默当作完整文件。

选择 CBOR Sequence 而不是 MessagePack 私有约定或 length-prefixed JSON 的理由是：CBOR item 原生自定界，RFC 8742 已定义连续 item 流；CBOR 原生 byte string 消除 Base64 膨胀；zstd concatenated frame 原生支持追加和完整前缀恢复。每事件一个 frame 让追加边界与 reader 校验边界一致。

### 生产实现

`src/app/observability/raw_capture.py` 已完成：

1. 删除 `orjson`/Base64 capture 编码，新增 `cbor2` canonical encoding，body 直接存 bytes。
2. 每条 CBOR item 在请求线程先压成独立 zstd frame；有界队列传递已压缩 frame，worker 只 append。
3. 单文件/总配额改按**实际压缩 frame 字节** reservation；包括已落盘与已排队字节。
4. 总配额启动扫描同时计入 `.cborseq.zst` 与遗留 `.jsonl.zst`，防止升级后旧文件不计费而绕过总量上限；新实现绝不创建或追加 JSONL。
5. 新增 `iter_raw_capture_records(path)` 流式逐 frame/逐 item reader，验证不完整 zstd 尾部、单 frame 多 item 和非 map 顶层。
6. 保留第一阶段的 per-request drop reason、首个丢失事件和完成 warning；普通日志只写 request ID、固定原因、固定事件类型与 completeness 布尔值，不写 session/agent identity、header、token 或 body。

项目依赖增加 `cbor2`；本仓 `uv.lock` 不受 Git 跟踪，`uv lock` 已在工作树生成包含 `cbor2 6.1.4` 的本地 lock 数据，生产依赖声明的权威改动是 `pyproject.toml`。

### 红灯与回归覆盖

在生产改动前先把 unit/integration 测试改为要求：

- `iter_raw_capture_records` 存在；
- 路径是 `.cborseq.zst`；
- schema version 为 2；
- body 解码结果是 native bytes；
- 真实二进制流第一个 top-level item 是 CBOR map，不以 JSON `{` 开头；
- 新实现不产生 `.jsonl.zst`。

旧实现第一次运行在 collection 阶段确定失败：`ImportError: cannot import name 'iter_raw_capture_records'`。这条红灯直接证明旧 JSONL 实现不能满足新合同。

后续扩展测试还覆盖：

- 多个独立 zstd frame 真正 append，旧前缀不被重写；
- reader 逐条读完整前缀，并对截断尾 frame 报错；
- 遗留 `.jsonl.zst` 仍计入总配额；
- 单文件和总目录配额都能形成“仅留下 `request.start`”的场景；
- 配额完成 warning 分别报告 `file_quota_exceeded` / `total_quota_exceeded` 和 `response_body_capture_complete=false`；
- 日志断言确认测试正文标记未进入普通 warning；
- 两个 account-switch attempt 的实际 upstream request body 仍可从 CBOR capture 逐条取回。

### 第二阶段验证结果

- `uv run pytest -q tests/unit/observability/test_raw_capture.py`：`7 passed`。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture'`：`2 passed, 274 deselected`；仅有第三方 Starlette deprecation warning。
- 最终合并聚焦命令（raw capture schema unit + 7 个格式/配额 unit + 2 个 integration）：`10 passed, 274 deselected`。
- `uv run ruff check src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py tests/int/test_pipeline_app.py`：通过。
- `uv run pyright src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py`：`0 errors, 0 warnings, 0 informations`。
- `uv lock --check`：通过；解析 81 个包。
- 从权威 config example 只抽取本轮新增的 `observability` 段交给 `ProxyConfig`：通过，默认关闭且 compression level 为 3。
- 聚焦搜索只在“明确禁止/遗留配额兼容”的 Spec、常量与测试中保留 `.jsonl.zst` 字样；生产新路径只使用 `.cborseq.zst`。

尝试运行整个 `test_authoritative_example_config_parses` 时，该测试被本轮范围外的既有不一致阻断：当前 config example 中已有 `model_providers.ghc.exposed_models`、`sub2api.api_base_url` 空值、`sub2api.token_file`、`hook_fix_responses_request.reasoning_encrypted_content` 四项与共享工作树 schema 不匹配。本轮新增 `observability.raw_capture` 段不在四项错误中，且已被上面的抽取验证和现有 raw capture schema unit 单独证明可解析。按“不改无关脏改动”约束没有处理这些字段。

### 最终改动范围

本代理修改/新增：

- `.dev/docs/raw-capture/spec.md`
- `.dev/docs/direct-passthrough/spec.md`（仅 raw capture 格式归属与 v29 修订）
- `.dev/human-controlled-docs-candidates/raw-capture.md`
- `.dev/docs/tmp/260908-raw-capture-diagnostics-agent-report.md`
- `docs/.human-controlled/config.example.yaml`（仅新增 raw capture 配置段）
- `pyproject.toml`（仅新增 `cbor2`）
- `uv.lock`（Git 未跟踪/忽略的本地生成 lock，仅由 `uv lock` 加入 `cbor2` 解析结果）
- `src/app/observability/raw_capture.py`
- `tests/unit/observability/test_raw_capture.py`
- `tests/int/test_pipeline_app.py`（仅 raw capture imports 和两个既有 raw capture 测试）

共享工作树在本轮期间仍有其他代理修改 `request_completion.py`、`request_trace.py`、`request_log.py`、pipeline、server 与相关测试。本代理没有编辑或还原这些文件，也没有触碰另一代理负责的 stream-body timeout 完成行字段。

---

## 第三阶段：`capture-writer-ack` major finding

独立审查 `.dev/docs/tmp/260908-binary-capture-review.md` 指出：当前 queue item 只有 `(path, compressed)`；`append()` 入队后立即增加 reservation 并向 `RawRequestCapture` 返回成功，但 `_write_loop()` 后续 `OSError` 只写匿名 warning，不回滚 reservation，也无法把失败反馈给所属 request。于是磁盘没有事件时 capture 仍被视为完整，`finish()` 不会报告丢失；不存在的字节还会继续消耗配额。

已先把权威 `.dev/docs/raw-capture/spec.md` 修订为 ACTIVE v2，新增以下承重合同：

- queue item 必须关联 capture、event type 与预留 frame 成本；
- reservation 表示实际已落盘字节加 queued pending 字节；成功确认时数值不变，失败时在 accounting 锁内回滚未写部分；
- 短写/close error 保留实际已写成本、回滚未写部分，并将 capture 标记不完整；
- writer 失败后该 capture 尚未落盘的 queued frame 不再继续写；
- `RawRequestCapture.finish()` 必须等本 request 的所有 writer ack 后再发完成诊断；
- writer `OSError` 使用稳定枚举 `writer_error`；即时与完成 warning 都只允许安全元数据，禁止 body、header、token 和原始 session/agent identity。

计划用确定性的 ENOTDIR 场景建立红灯：让 capture root 本身是普通文件，使 worker 在创建 session 目录时稳定得到 `OSError`；请求仍模拟 response body 并完成。测试将要求完成 warning 为 `reason=writer_error`、响应正文 capture 不完整、所有 warning 不含正文/credential marker，并在所有 ack 后验证 file/total reservation 回到实际零成本。

### 第三阶段红灯

运行：

```text
uv run pytest -q tests/unit/observability/test_raw_capture.py::test_writer_error_is_acknowledged_and_releases_reservations
```

修复前稳定得到 `1 failed`：四个 frame 均在 ENOTDIR 路径发出匿名 writer warning，但没有 `raw request capture incomplete at request completion`；这与独立审查探针一致。测试没有读取或输出 capture body/credential。

### 第三阶段实施

`src/app/observability/raw_capture.py` 在不改变 CBOR Sequence + per-item zstd frame 的前提下完成：

1. queue item 改为 `_QueuedCaptureFrame`，携带 `path`、压缩 frame、所属 `RawRequestCapture`、固定 event type 和 `reserved_bytes`。
2. 入队、file/total reservation 增加、per-capture pending ack 增加都在 store accounting lock 的同一个临界区完成；writer 无法在 pending 注册前完成回执。
3. writer 使用 unbuffered append 并记录本次实际 `persisted_bytes`。完整成功时 reservation 数值原样成为实际成本；`mkdir/open/write/close` 的 `OSError` 或短写时，`_complete_write()` 在同一 store lock 内回滚 `reserved_bytes - persisted_bytes`，实际已写部分继续计入磁盘成本。
4. writer 回执在同一临界区之后更新所属 capture 的 pending count；失败将 event 标为 missing、设置稳定 `writer_error` 状态并唤醒等待者。
5. writer 已失败的 capture 后续 queued frame 会被丢弃并完整回滚，不会继续追加在可能损坏的尾部之后。
6. `RawRequestCapture.finish()` 在 enqueue/skip `request.end` 后等待本 request 的 pending ack 归零，再生成一次完成 warning，因此 append 已返回成功但异步 writer 后失败也不会越过完成诊断。
7. 首次 drop reason 仍保留；纯 writer failure 得到 `reason=writer_error`。若先有 quota drop、后有在途 writer failure，则完成 warning 另带 `writer_error=true`，且后续 queued frame 仍停止，避免首因保留掩盖 writer 故障。
8. 即时 writer warning 只含 request ID、固定 event type、`reason=writer_error`、exception type 和 errno；不再格式化可能携带路径或 payload 的 exception message。完成 warning 同样只含安全枚举/布尔元数据。

### 第三阶段测试

新增两个 unit：

- `test_writer_error_is_acknowledged_and_releases_reservations`：capture root 为普通文件，稳定触发 ENOTDIR；验证完成 warning 恰好一次、`reason=writer_error`、`writer_error=true`、response body capture 不完整、file/total reservation 回到零，并验证全部 warning 不含 body marker 或作为 session identity 传入的 credential marker。
- `test_writer_failure_rollback_preserves_concurrent_successful_cost`：同一 store 中 4 个坏 session parent 与 4 个正常 session 通过 8 个线程并发完成；坏 frame 回滚，正常文件完整落盘，最终 per-file reservation 精确等于各文件 `stat().st_size`，total 精确等于这些实际成本之和。

### 第三阶段最终验证

- writer ENOTDIR 红灯修复后：`1 passed`。
- `uv run pytest -q tests/unit/observability/test_raw_capture.py`：`9 passed`。
- 并发 mixed success/failure test 连续运行 5 次：每次 `1 passed`。
- 最终聚焦 unit + integration：`11 passed, 274 deselected`；仅有第三方 Starlette deprecation warning。
- `uv run ruff check src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py tests/int/test_pipeline_app.py`：通过。
- `uv run pyright src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py`：`0 errors, 0 warnings, 0 informations`。
- scoped `git diff --check`：通过。
- 聚焦搜索确认本代理文件没有 stream body-attempt/timeout 字段；未触碰另一代理的 observability 完成行工作。

### 第三阶段结论

独立审查的 major finding `capture-writer-ack` 已闭合：异步 writer 的成功/失败现在有 per-request ack，失败 reservation 按实际落盘成本原子回滚，finish 在完成诊断前等待回执，ENOTDIR 能可靠、安全地报告 `writer_error`。CBOR Sequence + zstd 文件合同和普通日志敏感边界保持不变。

---

## 第四阶段：`partial-write-poisons-shared-stream` major finding

最终复审 `.dev/docs/tmp/260908-binary-capture-final-review.md` 证明第三阶段只停止“发生 short write 的 request capture”，没有停止共享同一 `(session_id, agent_id)` path 的其他 capture。A 留下半个 zstd frame 后，B 仍可把完整 frame 追加在坏 frame 后并获得成功 ack；accounting 虽等于磁盘大小，生产 reader 却无法越过中间坏 frame，因此 B 的“完整”是虚假结论。

已先把权威 `.dev/docs/raw-capture/spec.md` 修订为 ACTIVE v3：

- `0 < persisted_bytes < reserved_bytes` 在 accounting lock 内把 path 登记为 store 级 poisoned；
- poisoned path 在当前 store 生命周期内不自动恢复；
- 指向 poisoned path 的 queued 或新 frame 均不得 append，reservation 完整回滚；
- partial bytes 仍按实际磁盘成本保留；
- 当前 partial-write capture 保持 `writer_error`；同路径后续 capture 使用稳定首因 `path_poisoned`，且 `writer_error=false`，避免把 A 的 writer error冒充成 B 自身错误；
- B 的完成 warning 必须安全关联 B request ID、标记 `forensic_replay_complete=false`，不得包含 body、credential 或原始 session/agent identity。

计划新增确定性同路径顺序测试：受控 unbuffered writer 只对 A 的首个 frame 返回半长 short write；等待 A 完成并确认 path 已有 partial bytes 后，再启动同 session/agent 的 B。测试将要求 B 得到唯一 `path_poisoned` 完成 warning，B 的 frame 不增加文件大小，reader 仍只报告原 partial 尾错误而不存在不可达的 B 记录，最终 reservation 精确等于 partial 文件实际大小，全部普通 warning 不含 A/B body 或 session credential marker。

### 第四阶段红灯

运行：

```text
uv run pytest -q tests/unit/observability/test_raw_capture.py::test_partial_write_poisons_shared_path_for_the_next_request
```

修复前稳定得到 `1 failed`：A 的首 frame short write 后文件为 84 bytes；同路径 B 完成后文件增长到 600 bytes。日志只有 A 的 `writer_error`，B 没有 incomplete completion warning。这直接证明 B 的完整 frames 被追加在不可越过的 partial frame 后。

### 第四阶段实施

`RawCaptureStore` 新增 `_poisoned_paths`，并把检查/登记放在既有 store accounting lock 下：

1. 当前 writer item 满足 `0 < persisted_bytes < reserved_bytes` 时，`_complete_write()` 在回滚未写字节的同一临界区先把 `item.path` 加入 poisoned set，再向 A 回执 `writer_error`。
2. writer 取出任何后续 queued item 时先检查 path poison；命中则不打开文件、不 append，完整回滚该 item reservation，并向所属 capture 回执 `path_poisoned`。
3. 新 `append()` 在 store lock 内先检查 path poison；命中直接返回 `path_poisoned`，不 reservation、不入队。
4. poisoned set 在 store 生命周期内单向增长，不存在并发清除，因此“检查后又恢复”的竞态不存在；同一 worker 串行写文件，而 appender 即使恰好在 partial write 与 poison 登记之间入队，后续 worker-side check 仍会安全丢弃并回滚。
5. A 已写的 partial bytes 保持在 file/total accounting 中；B queued/new frame 的未写成本为零落盘、全额回滚。不同 path 的并发 capture 继续沿原合同独立成功。
6. `RawRequestCapture.note_writer_frame_completed()` 接收具体 drop reason；A 保持 `reason=writer_error` / `writer_error=true`，B 得到 `reason=path_poisoned` / `writer_error=false`。两者完成 warning 都只包含 request ID、固定枚举、固定 event type 和布尔完整性。

CBOR Sequence + zstd 编码、`.cborseq.zst` 路径、reader 与 body capture 内容均未改变；未修改 stream body observability 文件。

### 第四阶段测试与结果

新增 `test_partial_write_poisons_shared_path_for_the_next_request`：

- monkeypatch 只让 A 首个真实 unbuffered append 写入 frame 的一半并返回 short count；
- A `finish()` 等待 ack，确认 `writer_error`；
- 再以相同 session/agent 启动 B，验证唯一完成 warning 为 `path_poisoned`、`writer_error=false`、response body capture 不完整；
- B 完成后共享文件大小保持 A 的 partial size，不存在追加的 B bytes；
- 生产 reader 对原 partial 尾明确报错；
- 最终 per-file/total reservation 精确等于 partial 文件 `stat().st_size`；
- 所有普通 warning 不含 body marker 或作为 session identity 传入的 credential marker。

验证：

- 新红灯修复后：`1 passed`；连续运行 5 次均通过。
- `uv run pytest -q tests/unit/observability/test_raw_capture.py`：`10 passed`。
- 最终聚焦 unit + integration：`12 passed, 274 deselected`；仅有第三方 Starlette deprecation warning。
- `uv run ruff check src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py tests/int/test_pipeline_app.py`：通过。
- `uv run pyright src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py`：`0 errors, 0 warnings, 0 informations`。
- scoped `git diff --check`：通过。
- 聚焦搜索确认本代理文件没有 stream body-attempt/timeout 字段。

### 第四阶段结论

最终复审 major `partial-write-poisons-shared-stream` 已闭合：shared path 一旦留下 partial zstd frame，当前 store 不再向其追加；所有后续 queued/new capture 都获得稳定、安全的 `path_poisoned` incomplete 回执，且其 reservation 全额回滚。文件不再出现“B 成功 ack 但记录位于不可读取坏 frame 后”的虚假完整状态。

---

## 第五阶段：closeout 复审 `RC-1`

closeout 复审 `.dev/docs/tmp/260908-binary-capture-closeout-review.md` 指出：v3 的 `_poisoned_paths` 只属于一个 `RawCaptureStore` 实例。A 留下 partial frame 后即使当前实例不再追加，正常 `close()` 再创建新 store 会把 poisoned set 重置为空；同 session/agent 的 B 随后继续 append 且没有 incomplete warning，重新形成虚假完整。

已先把权威 `.dev/docs/raw-capture/spec.md` 修订为 ACTIVE v4，规定：

- 每个新 store 对某 path 的第一次 append 必须先用生产 `iter_raw_capture_records()` 验证已有 `.cborseq.zst`；
- 验证覆盖所有 zstd frame、每 frame 单一 CBOR item、顶层 map 和完整尾部；
- path 不存在或空文件可以 append；
- 首次验证、“validated”登记、poison 登记与首次 reservation/入队必须由 store accounting lock 串行化，并发 appender 不能绕过；
- 验证失败立即登记 `path_poisoned`，当前和后续 capture 不 append、不 reservation，并在 finish 安全报告；
- 验证成功后同一 store 不重复扫描，后续依赖 writer ack 与内存 poison；
- 验证异常不得把 decoder payload、body、credential 或原始 session/agent identity写入普通日志。

计划新增 close → new store → same session/agent 回归：store A 用受控 short write 留下 partial frame并正常关闭；记录损坏文件 size；新建 store B 后对同 path 发 request/body/finish。旧实现会让文件增长且 B 没有 warning；目标实现必须保持 size、让 B 唯一完成 warning 为 `path_poisoned` / `writer_error=false` / `forensic_replay_complete=false`，accounting 等于原 partial size，并证明全部 warning 不含正文/credential marker。

### 第五阶段红灯

运行：

```text
uv run pytest -q tests/unit/observability/test_raw_capture.py::test_partial_write_poison_is_recovered_by_a_new_store
```

修复前稳定得到 `1 failed`：A store short write 并正常关闭时损坏文件为 84 bytes；B store 重建并完成同路径请求后文件增长到 595 bytes。普通日志只有 A 的 `writer_error`，B 没有 incomplete completion warning。

### 第五阶段实施

`RawCaptureStore` 新增 `_validated_paths`。`append()` 在 store accounting lock 内、检查内存 poison 和任何 quota/reservation/queue 操作之前调用 `_validate_existing_path(path)`：

1. 同一 store 首次看到 path 时先登记 validated，确保并发 appender 只有锁持有者执行一次验证。
2. path 不存在或不是既有普通 capture 文件时不扫描，沿 writer 的正常创建/错误回执路径处理。
3. 既有普通文件由生产 `iter_raw_capture_records()` 从首 frame 读到 EOF；这同时验证 zstd frame 完整性、单 frame 单 CBOR item 和顶层 map。
4. 验证遇到 `OSError`、`ValueError`、`CBORDecodeError` 或 `ZstdError` 时，在首次 append 仍持有 store lock 的情况下把 path 加入 `_poisoned_paths`。
5. 随后的既有 poison check 立即返回 `path_poisoned`；当前 request 的 `request.start` 不 reservation、不入队，后续 body/event 只进入 per-request missing event set，`finish()` 安全发出唯一 incomplete warning。
6. 新 store 初始化时仍按 partial 文件实际 `stat().st_size` 计入 total reservation；拒绝 append 后 file 不增长，per-file pending reservation 保持空，total 保持实际 partial size。
7. 验证过程不记录 decoder exception message、文件内容或 identity；B 完成 warning 只含 request ID、`path_poisoned`、固定 event type 和 completeness 布尔值。

没有引入 JSONL、sidecar JSON 或长度前缀 envelope；CBOR Sequence + independently compressed zstd frames 保持不变。

### 第五阶段测试与结果

新增：

- `test_partial_write_poison_is_recovered_by_a_new_store`：A short write → `close()` → B new store → same session/agent；断言文件不增长，B 唯一 completion 为 `reason=path_poisoned` / `writer_error=false` / response body incomplete，accounting 等于原 partial size，全部 warning 不含 body/credential marker。
- `test_new_store_validates_and_appends_to_a_complete_existing_stream`：正控制；完整既有文件通过验证，新 store 正常追加，reader 按顺序读到两个 request 的四条事件，防止“所有既有文件一律 poison”的伪修复。

验证：

- RC-1 红灯修复后：`1 passed`；连续运行 5 次均通过。
- `uv run pytest -q tests/unit/observability/test_raw_capture.py`：`12 passed`。
- 最终聚焦 unit + integration：`14 passed, 274 deselected`；仅有第三方 Starlette deprecation warning。
- `uv run ruff check src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py tests/int/test_pipeline_app.py`：通过。
- `uv run pyright src/app/observability/raw_capture.py tests/unit/observability/test_raw_capture.py`：`0 errors, 0 warnings, 0 informations`。
- scoped `git diff --check`：通过。
- 聚焦搜索确认本代理文件没有 stream body-attempt/timeout 字段。

### 第五阶段结论

closeout 复审 major `RC-1` 已闭合：poison 不再依赖前一个 store 的内存；新 store 第一次允许同路径 append 前，生产 reader 会可靠恢复既有 partial/corrupt 文件事实。损坏 path 不增长，重建后的请求稳定、安全地报告 `path_poisoned`，完整既有 stream 仍可正常续写。

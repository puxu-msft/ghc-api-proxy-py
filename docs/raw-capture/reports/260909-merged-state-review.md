# 评审报告：raw capture 合并态（动态 capture 主体 + 移除全局配额差量）

日期：2026-09-09
评审者：独立评审代理（as-reviewer；判据独立于实现取得）
规格依据：`.dev/docs/raw-capture/spec.md`（ACTIVE v21）
差量自述：`.dev/docs/raw-capture/reports/260909-drop-global-quota.md`（按未核验 claim 处理，逐项以 diff 与命令输出复核）

## 评审范围

合并态（工作树未提交改动）中的 raw capture 相关文件：

- 批次 1（动态 capture 主体）：`src/app/observability/debug_capture.py`、`src/app/server/routes/ops.py` 的 `/api/debug/capture-rules`、`src/app/observability/raw_capture.py`、`src/app/server/routes/inference.py` 的 `_routed` 及 capture 接线。
- 批次 2（移除全局配额差量）：`src/app/config/schema.py`、`src/app/config/compat.py`、`src/app/server/composition.py`、`src/app/observability/raw_capture.py`、`tests/unit/observability/test_raw_capture.py`、`docs/.human-controlled/config.example.yaml`。

**明确不在范围**：工作树中其他在飞批次（`model_provider/*`、`pipeline/*`、`protocols/*` 删除、`fallback_model_provider` 移除等）——它们与 raw capture 的交集仅作为接缝扫过；已知预存失败（`test_authoritative_example_config_parses` 的 4 个 ValidationError、`test_pipeline_app.py`/`test_sse_assembly.py` 的 9 个失败）只复核基线、不列为发现。

## 总体 verdict

**pass。blocker = 0，major = 0，minor = 2，主观建议 2（不占 severity）。**

差量「移除全局配额」与规格 v21 逐条相符，无残留状态假设；判别性测试经变异探针证实有分辨力；被删断言的覆盖由 per-file 断言等价承接；安全边界未发现违规。

## 发现

### minor

**M-1 完成诊断 reason 的代码全集宽于 §6 固定的枚举，规格侧不完备**（非本次差量引入，非行为缺陷）

§6 只固定枚举了 `file_quota_exceeded` / `writer_error` / `path_poisoned` / `request_incomplete`。代码实际可作为完成 warning `reason=` 出现的固定字符串全集还包括：

- `store_closed`（`raw_capture.py:132`，append 时 store 已关闭）；
- `writer_queue_full`（`raw_capture.py:145`）；
- `capture_error`（`raw_capture.py:182`，CBOR 编码 / zstd 压缩 / stat 失败）；
- `upstream_incomplete`（`raw_capture.py:334` `_note_incomplete`，partial boundary 参与完成诊断，见 `test_partial_response_boundary_is_reported_at_request_completion` 断言 `reason=upstream_incomplete`）。

前三者的**语义**在 §5 有覆盖（「达到配额、队列满、store 已关闭、编码/压缩准备失败或 writer 失败时，停止该 request 后续 capture」），但枚举名未在规格固定；`upstream_incomplete` 是 v17「partial boundary 参与 completion warning」验收链的产物，§5/§6 均未固定其名。

已废止原因 `total_quota_exceeded` 全仓 grep 无残留（唯一 `max_total_bytes` 命中在 `compat.py:87`，是 `_drop_key` 删除废弃键本身所需字符串）✔。

影响：全部为固定字符串、安全元数据，无行为或安全问题；但后续实现者/验收者无法从规格文本推导出完整合法枚举，规格与代码会继续漂移。建议在 §6 补全枚举（或声明 §6 列举非穷尽、以 §5 语义为准）。

**M-2 `append()` 的两个即时 warning 字段口径弱于 writer warning 的白名单写法**

- `raw_capture.py:135`：`logger.warning("raw request capture file quota exceeded: %s", path)`；
- `raw_capture.py:201`：`logger.warning("could not keep raw request capture: %s", error)`——格式化整个 exception。

实证（本评审执行）：cbor2 对不可序列化对象抛 `CBOREncodeError: cannot encode type <class 'X'>`，消息**不含值内容**；`path.stat()` 的 OSError str 只含 hash 形式 path（`session-<sha256-24>/agent-<sha256-24>.cborseq.zst`），§6 明确允许 path 出现、禁的是「path 对应的原始 identity」；zstd 错误无 payload。故**当前不违反 §4/§6**，不构成正确性缺陷。定 minor 的理由是结构性：writer warning（`raw_capture.py:226-236`）采用逐字段白名单（request_id/event_type/reason/exception_type/errno），而这两处用 `%s` 吐整个对象，未来任何异常类型若其消息回显值内容，此处没有防线。与 M-1 同为既有代码，非差量引入。

### 主观建议（不占 severity，取舍交调用方）

**S-1** 同 M-2 的结构性观察：`append()` 两个 warning 建议改为与 writer warning 一致的逐字段白名单写法。当前实证无 payload 回显，属防御性收紧。

**S-2** `_validate_existing_path`（`raw_capture.py:150-164`）在 accounting lock 内做全量 reader 扫描（append 持锁期间调用）。数百 MB 的既有 capture 文件首次 append 时会阻塞所有并发 append 与 writer 记账。规格字面要求「验证与状态转换必须受 store accounting lock 串行化」，实现合规且保守正确；若未来要缩短锁持有时间，需先修订 §5 表述（锁外读、锁内转换）。当前按规格执行是正确取舍。

## 已核验通过面（无发现）

### 规格 §1/§2/§3（文件与分组、二进制流）

- CBOR Sequence（RFC 8742）+ 每事件独立 zstd frame 追加；`schema_version=2`；公共字段齐全（`raw_capture.py:104-112`）。
- 路径命名：session/agent 各 SHA-256 前 24 hex；missing agent 独立命名空间 `missing-<sha256("missing-agent-id")[:24]>`；文件名/目录名无原始 identity（`_path_for`，`raw_capture.py:86-95`；测试 `test_capture_path_does_not_use_raw_identity_values` 用 `../..` 与 slash 注入验证）。
- 新实现不创建/追加 `.jsonl.zst`：`CAPTURE_FILE_SUFFIX` 唯一；`LEGACY_CAPTURE_FILE_SUFFIX` 已随差量删除；`request_log_file.py` 的 `requests-*.jsonl` 是普通请求日志、非 capture 形态。
- reader 合同：逐 frame 解压、每 frame 单一 CBOR item、顶层 map 合同、截断尾 frame 报 ValueError（`iter_raw_capture_records`；测试 `test_capture_appends_complete_frames_and_rejects_a_truncated_tail`）。

### 规格 §2.1（规则匹配时机与补录）

- SQLite 表 + `UNIQUE(provider, model_id, session_id, agent_id)` + 匹配索引，启动时创建（`debug_capture.py:57-70`）；路径独立持久化（`composition.py:696-701`，config `rules_database` 或 `debug_capture_rules_path()`）。
- 精确匹配：`matches` SQL `provider=? AND model_id=? AND session_id=? AND (agent_id='' OR agent_id=?)`（`debug_capture.py:157-170`）；DB sentinel `''` 不可由客户端提交（`_normalize` 拒空串，header 空值在 `agent_id_from_headers` 处即归为缺失）。
- 管理接口：GET 列表 / POST 幂等创建（201/200，`INSERT OR IGNORE` + 回读）/ DELETE 404 或 204（`ops.py:57-90`）；payload `extra="forbid"`，只含四个条件字段，不接受 body；strip+非空校验。
- 匹配时机：`_routed` 由 `shape_request` 在 `decide_route`+`apply_route` 后立即触发（`driver.py:113-116`），早于 translation 与第一次 upstream attempt；count_tokens 路径同挂钩（`driver.py:483-484`）。
- 补录：`raw_body` 来自 `await request.body()`（`inference.py:606`）完整读取后传入；命中即 `store.start` + `capture.request_body(raw_body)` + `request_body_end(complete=True)`（`inference.py:737-746`），complete=True 语义正确（body 已读完，ClientDisconnect 在 dispatch 前即 raise）。
- 未命中零副作用：matches 是纯 DB 查询；`session_id is not None` 守卫；body/provider/model-id 解析失败不进路由、不启动 capture。

### 规格 §5（配额与写入；删除总量配额后的自洽性）

- 仅 `max_file_bytes`（`0` 禁用）；无目录级总量配额；legacy 文件不参与任何配额计算（合并态无任何 rglob/legacy 计数；`test_legacy_jsonl_files_do_not_participate_in_any_quota` 断言 4 GiB legacy 文件不影响 append）。
- reservation 语义（已落盘 + 已排队）：`current_file_bytes = _reserved_file_bytes.get(path, path.stat().st_size if path.is_file() else 0)`，入队即累加，writer committed 数值不变（`_complete_write` 全写成功时 `released_bytes=0`）。
- **差量回归核心**：删除 `_reserved_total_bytes` 后无残留状态假设。`_complete_write` 直接下标 `self._reserved_file_bytes[item.path]`（`raw_capture.py:287`）的 KeyError 风险经锁序论证排除：`append` 在同一 accounting lock 内完成 put_nowait → 记账 → `note_writer_frame_queued`，writer 的 `_complete_write` 必须先取到该锁，故记账必已生效；空 dict 清理由 `del` 键完成（`remaining_file_bytes == 0` 时），后续 append 落回 stat fallback——`test_writer_error_is_acknowledged_and_releases_reservations` 断言 `_reserved_file_bytes == {}` 通过。
- 队列项携带 capture/event_type/reserved_bytes（`_QueuedCaptureFrame`），非匿名 `(path, bytes)`。
- writer OSError：锁外写、同锁回滚未写部分、短写 raise OSError、`0 < persisted < reserved` → poison；已写部分计入实际成本（`_write_loop` 230-273）。
- path poison：锁内与 partial-write 回执同登记、store 生命周期不清除、同路径 queued/new frame 全回滚并报 `path_poisoned`、不同 path 不受影响（`test_partial_write_poisons_shared_path_for_the_next_request` 断言 `_reserved_file_bytes == {capture_path: partial_size}`）。
- 跨 store 恢复：新 store 首次 append 前用生产 reader 全量验证，空/不存在文件视为可 append，验证与状态转换受锁串行化（`_validate_existing_path` 在 append 持锁内）；`test_partial_write_poison_is_recovered_by_a_new_store`、`test_new_store_validates_and_appends_to_a_complete_existing_stream` 覆盖两端。
- ack 合同：`finish()` 写 `request.end` 后 `_wait_for_writes()` 等全部队列项回执再定诊断；配额/队列满/关闭/编码失败/ writer 失败均停 capture 不影响代理请求。
- 并发：`test_writer_failure_rollback_preserves_concurrent_successful_cost`（8 线程混失败/成功）断言 `_reserved_file_bytes == actual_costs`。

### 规格 §6（完成诊断）

- 完成 warning 恰好一次（`if drop_reason is not None`，字段含 request_id/reason/first_dropped_event/writer_error/response_body_capture_complete/`forensic_replay_complete=false`）。
- `writer_error` 首因保留 + `writer_error=true` 标记双轨：`_mark_drop_locked` 独立记 `_writer_error_event`，`_drop_reason` 只认首因（`raw_capture.py:316-326`）；`test_writer_error_is_acknowledged_and_releases_reservations` 断言 `reason=writer_error` 且 `writer_error=true`。
- `path_poisoned` 归属正确：后续 request 的 `writer_error=false`（`test_partial_write_poisons_shared_path_for_the_next_request` 断言）。
- `request_incomplete`：`finish(complete=False)` 固定原因（`test_incomplete_request_is_reported_even_when_writer_succeeds`）。
- 配额耗尽案例：`reason=file_quota_exceeded` + `response_body_capture_complete=false`（`test_quota_drop_is_reported_safely_at_request_completion`，含 4 KB 随机 marker 不入日志断言）。

### 差量回归（compat 作用域）

`_drop_key` 仅对 `migrated["observability"]["raw_capture"]` 子 dict 应用精确键 `max_total_bytes`（`compat.py:83-90`）。全仓唯一同名键即该废弃键；`upstream_request_retry.max_total` 键名不同（`max_total`）且不在该节，不受影响。`migrate_compat` 在加载链真实接线（`loading.py:210`、`loader.py:96`）。`RawCaptureStore` 唯一生产调用点 `composition.py:702` 不再传 `max_total_bytes`；17 个测试调用点均两参内。

### 测试分辨力（变异探针，执行验证）

在隔离副本（`/tmp/probe-mrq`，已清理）把旧实现行为打回：恢复 `__init__` 的 legacy `.jsonl.zst` rglob 计数 + 默认 4 GiB `_max_total_bytes` + `append` 的 `total_quota_exceeded` 分支与 total 累计 + `_complete_write` 的 total 回滚。判别性测试 `test_legacy_jsonl_files_do_not_participate_in_any_quota` **在旧实现下失败**：`total_quota_exceeded` → capture 文件未创建 → `assert len(files) == 1` 得 `0 == 1`（pytest 输出截留于评审记录）。新实现下通过。判别力成立。

被删断言（原 4 处 `_reserved_total_bytes` 检查）的覆盖映射：`{}`（writer_error 清空）、`actual_costs`（并发实际成本）、`{path: partial_size}`（poison 后保留 partial 成本）、`{}`（新 store 验证恢复）——全部由 per-file 断言承接，无净覆盖损失。参数化删除 `max_total_bytes=512` 组后 file 组保留。`partial_size` 在所在测试仍有文件大小断言用途，无死变量。

### 安全边界

- `debug_capture.py`、`ops.py` 路由、`inference.py` `_routed` 补录路径：零日志语句。
- `raw_capture.py` 全部 5 处日志逐条过：writer warning 与完成 warning 均白名单字段（request_id/event_type/reason/exception_type/errno/completeness 布尔）；验证失败（poison 判定）无日志；两处 `%s`（path/exception）实证不含 payload（见 M-2）。
- `config.example.yaml`：`observability.raw_capture` 节与 schema 对齐（无 `max_total_bytes`），注释第 4 条只述单文件配额 + 安全元数据口径；差量声称的「两处最小修改」与实际 diff 一致（该节整体相对 HEAD 为批次 1 新增）。
- 测试防泄漏：marker 断言覆盖 quota/poison/writer 路径。

### 工具与测试执行记录

- `uv run pytest tests/unit/observability tests/unit/config --no-cov -q` → **372 passed, 1 failed**；唯一失败 `test_config_schema.py::test_authoritative_example_config_parses`，ValidationError 全部位于 `model_providers.*` / `hook_fix_responses_request.reasoning_encrypted_content`（4 个错误，另有 `api_base_url` string_too_short），无一条涉及 `observability.raw_capture`——与已知预存基线一致，不列为发现。
- `uv run pytest tests/int/test_pipeline_app.py -k capture --no-cov -q` → **6 passed**（规则 API 持久化、opt-in 双侧 body、失败 attempt 保留、count retry、refusal 不写 legacy capture）。
- `uv run ruff check`（6 个范围文件）→ All checks passed。
- `uv run pyright`（4 个范围文件）→ 0 errors, 0 warnings。
- `tests/unit/observability/test_debug_capture.py` → 3 passed（持久化、幂等、agent 精确匹配、空条件拒绝）。

## 搜索面说明

**读过**：spec.md 全文；差量报告全文；`raw_capture.py`、`debug_capture.py`、`compat.py`、`test_raw_capture.py` 全文；`ops.py`（payload + 三路由段）、`inference.py`（`_routed`、`_dispatch_after_body`、body 读取点、upstream capture 接线三段）、`driver.py`（`shape_request`/`on_routed` 触发点、count capture 段）、`schema.py`（`RawCaptureConfig`）、`composition.py`（store 构造段）、`test_debug_capture.py` 断言概貌、`session_identity.py`、`config.example.yaml` 与 `api.md` 的相关 diff/段落。

**跑过**：上节全部命令 + cbor2/zstd/OSError 异常消息实证脚本 + 变异探针（判别测试红 + 修正后重跑）。

**没看**（明确未覆盖）：批次 1 主体在 v12-v21 验收链中已验收的行为细节（rejection_capture、request_completion 等模块的合并态内部）；e2e 与部署监听面（§2.1 明确交部署层）；`tests/tui`（默认排除）。工作树中其他在飞批次的正确性不属于本次边界，其与 raw capture 的接缝（schema 节、example 节、composition 构造）已扫。

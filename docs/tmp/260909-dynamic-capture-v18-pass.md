# Dynamic capture v18 最终只读复核

## 评审范围

被检对象是 `/home/xp/src/ghc-api-proxy-py` 当前工作树最终状态。判据来源是 `.dev/docs/raw-capture/spec.md` ACTIVE v18、用户给出的条件式 raw capture 合同、`.claude/rules/00-development-workflow.md`，以及 `docs/.human-controlled/api.md`、`docs/.human-controlled/config.example.yaml` 和相关 active module 文档。覆盖 HTTP API + SQLite 精确规则、未命中无正文、CBOR/zstd 真实 wire、provider/status/partial/cleanup/count/retry/CodeBuddy aggregate attempt bytes 与 completeness、pre-first-pull/direct discard、partial completion warning、COUNT buffered attempts、普通 upstream 安全投影、proxy-owned message、ResponseObservation event errors、legacy JSON inactive 和 active docs 同步。未操作现有 4141，未读取、输出或持久化真实 capture 正文、认证信息、token、credential 或秘密。

## 总体 verdict

**needs-fix：发现 5 个高置信度问题，不能报告 pass。**

## Blocker 数

0。

## Findings

### DYN-CAP-22 —— major —— prepared streaming response 被 direct discard 时缺少 response/attempt incomplete boundary

- `finding_id`: `DYN-CAP-22`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:1697-1699`
- `related_locations`: `src/app/server/routes/inference.py:427-443`、`src/app/server/routes/inference.py:1444-1457`、`.dev/docs/raw-capture/spec.md:50、82-86`
- **判据**：命中 capture 的 upstream attempt 必须保留 response completeness；首次 body pull 前 prepared response 因 downstream disconnect 或其他 direct discard 被关闭时，必须写 `upstream.response.end(complete=false)`，随后写 `upstream.attempt.end(complete=false)`。
- **证据强度**：高。`_run_dispatch_while_connected()` 的未交付结果通过 `_discard_prepared_response()` 调用 `_AccountedStreamingResponse.aclose()`；该方法只关闭 content/response，不调用 `note_unstarted_upstream_body_cleanup()`。后者只在 `__call__()` 的 finally 中执行。合成 probe 确认直接调用 prepared response 的 `aclose()` 不会触发未启动边界。
- **影响**：capture 已经有 `upstream.request.body` 与 `upstream.response.start` 时，仍会缺少 `upstream.response.end` 和 `upstream.attempt.end`，无法区分未拉取 body 的 direct discard 与其他 attempt 结束形态。
- **修复方向**：让 prepared-response discard 路径幂等地登记 `response.end(false)` 和 `attempt.end(false)`，并保持 response owner、completion publish 与后续 cleanup 的职责不重复。

### DYN-CAP-23 —— major —— one-shot 路径把 local failure 当作 upstream failure

- `finding_id`: `DYN-CAP-23`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:1947-1957`
- `related_locations`: `src/app/pipeline/delivery/stream.py:75-108`、`src/app/server/routes/inference.py:1419-1425`
- **判据**：one-shot upstream provenance 必须使用 upstream source 的正向身份；proxy-owned bookkeeping、byte counter、delivery 或其他本地异常必须保持 proxy-owned projection，不能冒充 upstream。
- **证据强度**：高。one-shot 只要 `assembler is None` 且 `upstream_body_started`，就对任意异常安装始终返回 `True` 的 provenance，并以 `upstream=True` 记录。此范围包含位于 `UpstreamSource` 之上的 `_counted_upstream` 本地 bookkeeping。合成 probe 将一个 proxy-owned `RuntimeError` 送入该分支，最终 detail 被投影为 upstream stream failure。
- **影响**：普通 completion、failure origin 和安全 detail 会错误归因；后续按 provenance 做的失败消费、重试或诊断也可能把代理自身缺陷归到 provider。
- **修复方向**：one-shot 也传递并校验 `UpstreamSource.tear_is_unmodified` 一类的正向 provenance；没有正向证据时保持 proxy-owned，不要使用“body 已启动”作为 upstream 证明。

### DYN-CAP-24 —— major —— ResponseObservation event error detail 可把异常文本写入普通 structured record

- `finding_id`: `DYN-CAP-24`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/response_observation.py:304-305、586-597`
- `related_locations`: `src/app/observability/request_completion.py:230-255、1080-1085`、`.dev/docs/raw-capture/spec.md:52、82-93`
- **判据**：ResponseObservation event errors 只能保留安全错误 code、field path、exception type 等固定 metadata；普通日志和 request completion record 不得复制 upstream message、raw error object 或异常中可能回显的正文。
- **证据强度**：高。`observe_event()` 将捕获的异常直接传给 `_issue()`，而 `_issue()` 把 `str(error)[:500]` 存入 `ObservationIssue.detail`；`_issue_dict()` 又无条件把 detail 写进 structured observation。合成 event probe 确认异常自带的敏感文本会进入 issue detail。
- **影响**：观察器本应是 side-only、安全投影，却为普通 request record 打开了任意异常文本落盘路径；这与 v18 的 safe ordinary projection 合同直接冲突。
- **修复方向**：对 observer/parser 异常使用固定 issue code、field path、异常类型和 bounded safe category；不要持久化异常 message。provider error 的 presence projection 继续使用现有安全 helper。

### DYN-CAP-25 —— major —— Xingchen status cleanup failure 会覆盖已读 response 的 provider/body evidence

- `finding_id`: `DYN-CAP-25`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/xingchen/client.py:126-139`
- `related_locations`: `src/app/model_provider/upstream_errors.py:190-209`、`src/app/pipeline/direct_driver/base.py:176-195`
- **判据**：任何 provider 的 status-body read、transport 或 cleanup failure 都必须保留 request bytes、status、已观测 response bytes 和 `complete=false` attempt boundary；cleanup error 不得覆盖已经存在的 provider response evidence。
- **证据强度**：高。Xingchen 在 `response.raise_for_status()` 的 `finally` 中直接 `await response.aclose()`；若 close 抛错，它会替换 status exception。外层随后只对该 cleanup exception 调用 `normalize_upstream_error()`，该异常没有 response carrier，因此 status/body/request evidence 丢失，`capture_failed_upstream_attempt()` 也不会得到可 capture 的 upstream error。
- **影响**：Xingchen 的 status cleanup failure 可能只留下一个未归一化的异常和不完整 attempt，违反“所有 provider/status/cleanup”证据合同。
- **修复方向**：沿用 generic cleanup carrier，把原 response、已读 body、status、request bytes 和 `body_complete=false` 绑定到归一化错误；cleanup 只作为 primary 的安全 secondary，不得替换 provider response。

### DYN-CAP-26 —— major —— shared status normalizer 把未观测 body 错报为 observed complete empty body

- `finding_id`: `DYN-CAP-26`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/model_provider/upstream_errors.py:95-117、263-297`
- `related_locations`: `src/app/model_provider/upstream_errors.py:212-229`、`src/app/pipeline/exceptions.py:42-75`、`.dev/docs/raw-capture/spec.md:50、82-93`
- **判据**：status response 的“未观测 body”“观测到空 body”“观测到 partial body”必须保持可区分；没有实际读取 body 时不得生成 `body_observed=true` 或 `body_complete=true`。
- **证据强度**：高。`_response_parts()` 计算了 `body_observed` 却没有把它放入返回值；`normalize_upstream_error()` 的 429、4xx 和其他 status 分支都硬编码 `body_observed=True`。用一个未消费的 streamed 500 response 做 probe，归一化结果为 `body_observed=True`、`body_complete=True`、空 body。
- **影响**：共享 provider error carrier 会把缺失 wire evidence 伪装成完整空 response，导致 raw capture 与 ordinary attempt completeness 给出过强且错误的取证结论。
- **修复方向**：让 `UpstreamResponseParts` 携带 body observation/completeness，并在各 status 分支原样传递；只有 provider 明确完成了 body read 时才标记 complete。

## 上轮 finding 完成度与当前系统状态

- DYN-CAP-18 的已写入 partial boundary warning、DYN-CAP-19 的未观测 response end、DYN-CAP-20 的 COUNT buffered attempt projection 和 DYN-CAP-21 的 active module doc 漂移在当前代码中已有对应修复或同步迹象，相关最小测试通过。
- direct-driver 返回 response 的 discard helper 已经会写入 `response.end(false)`；DYN-CAP-22 是另一个 prepared streaming response 在 ASGI 交付前被 `_discard_prepared_response()` 关闭的边界，不能据此视为已闭合。
- 抛开上轮清单，当前系统仍存在上述五个独立问题；绿色测试没有覆盖这些缺口。

## 最小相关验证

- `uv run pytest -q tests/unit/observability/test_raw_capture.py tests/unit/model_provider/test_provider_error_wire_capture.py tests/unit/pipeline/test_response_observation.py tests/unit/observability/test_response_observation_projection.py tests/component/model_provider/codebuddy_client/test_codebuddy_client.py`：104 passed。
- `uv run pytest -q tests/int/test_pipeline_app.py -k 'raw_capture or count_capture or unmatched_refusal_capture or rejection_capture'`：5 passed，273 deselected。
- `uv run pytest -q tests/component/model_provider/codebuddy_client/test_codebuddy_client.py tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py`：37 passed。
- `uv run pytest -q tests/unit/observability/test_request_completion.py tests/unit/pipeline/test_direct_driver.py tests/unit/pipeline/delivery/test_one_shot_delivery.py tests/int/test_pipeline_app.py -k 'raw_capture or count_capture or rejection_capture or one_shot or response_start_failure'`：18 passed，361 deselected。
- 不落盘合成 probe 另外确认了：未消费 status response 被错误标成 observed/complete；ResponseObservation issue 保留异常文本；prepared response `aclose()` 不登记 unstarted boundary；one-shot local error 被投影为 upstream。

## 搜索面与未覆盖面

已读 ACTIVE v18 raw-capture Spec、项目开发工作流、debug capture SQLite store、ops HTTP routes、raw capture writer/reader、inference lifecycle、direct driver、COUNT driver、request trace/completion/log、Responses observation、GHC/OpenAI-compatible/CodeBuddy/Xingchen provider normalizers、rejection shim、active docs 及相关 unit/component/integration tests。未运行完整 regression、Ruff、Pyright、真实 upstream、真实磁盘故障、多进程 append 压力或部署验收；这些未覆盖面没有被当作已验证，也不改变上述代码级高置信度 findings。未操作现有 4141。

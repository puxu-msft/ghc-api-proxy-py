# 动态调试捕获最终审查报告

## 评审范围

基准是 `/home/xp/src/ghc-api-proxy-py` 当前工作树相对 `HEAD` 的动态捕获相关未提交状态。直接审查了 `src/app/observability/debug_capture.py`、`src/app/observability/raw_capture.py`、其现有调用接线、`src/app/config/paths.py`、`src/app/config/loading.py`、`src/app/config/schema.py`、`src/app/core/chain.py`、`src/app/server/composition.py`、`src/app/server/routes/ops.py`、`src/app/server/routes/inference.py`、`tests/unit/observability/test_debug_capture.py`、`tests/unit/observability/test_raw_capture.py`、`tests/int/test_pipeline_app.py`、`docs/.human-controlled/api.md`、`docs/.human-controlled/config.example.yaml` 与 `.dev/docs/raw-capture/spec.md`。

为验证 `raw_capture` 现有接口的完整接线，额外只跟踪了 `request_completion.py`、`pipeline/direct_driver/base.py`、`pipeline/driver.py` 与 `pipeline/count_tokens.py` 中的相关调用点，没有对这些文件的其他功能做全面审查。没有读取、输出或依赖任何真实 capture 正文、真实请求/响应正文、secret 或真实数据库内容。

## 总体 verdict

**needs-fix**。匹配时机、已解析 provider/model-id、默认关闭与 SQLite 基本持久化路径正确；但 count、非重试上游拒绝和不完整 stream/error 结束路径仍会把不完整证据写成缺失或看似完整，不能接受为动态全量取证的最终状态。

## Blocker 数

0

## Findings

### DC-1 — major — 非重试上游拒绝及部分失败 attempt 没有保存实际 upstream wire evidence

- `finding_id`: `DC-1`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/direct_driver/base.py:175-191`
- `related_locations`: `src/app/pipeline/direct_driver/base.py:421-426`、`src/app/pipeline/direct_driver/base.py:479-488`
- **判据**：`.dev/docs/raw-capture/spec.md` §2.1、§4 要求命中请求继续记录每次实际 upstream request、response、retry 与错误事件；失败 attempt 不能只留下一个边界标记而丢失实际发送/收到的 body。
- **证据**：`_capture_failed_upstream_attempt()` 只有在异常是 `UpstreamError` 时才写入 `sent`、status、`body_bytes` 和 response end。现有异常合同中，非重试的 4xx 会使用不继承 `UpstreamError` 的 `UpstreamRejected`，因此同一请求在 400/403/404/422 等拒绝路径上只会由 `run()` 写入 `upstream_attempt_end(complete=False)`，不会写入实际 request body 或 upstream response body。响应已经取得但在 rate-limit discard、subscriber success hook 或其他 hand-off 前异常退出的 finally 路径也只写 attempt end，不会补写 wire evidence。
- **执行探针**：使用不落盘的 synthetic capture 调用该 helper，带有 request/response bytes 的 `UpstreamRejected` 产生 0 个 body/status 事件，而同条件 `UpstreamError` 产生 request、response start/body/end 事件。探针没有输出 body。
- **影响**：规则命中的请求在最需要取证的确定性上游拒绝路径上无法重放实际发送内容，也无法看到上游原始状态和响应正文；重试或失败诊断因此不完整。该问题跨越所有命中规则的非重试拒绝请求，定为 `major`。
- **修复方向**：把“从异常或已取得 response 提取实际 request/response bytes”的逻辑覆盖 `UpstreamRejected` 及所有 response discard 分支，且仍保持普通日志只记录安全元数据；每个实际发送或已收到的 attempt 都应先补 wire event，再写 `upstream_attempt_end`。

### DC-2 — major — count_tokens 的多次 upstream retry 全部标成同一个 attempt

- `finding_id`: `DC-2`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/driver.py:458-475`
- `related_locations`: `src/app/pipeline/count_tokens.py:70-99`、`src/app/config/schema.py:128`、`docs/.human-controlled/config.example.yaml:65-69`
- **判据**：`.dev/docs/raw-capture/spec.md` §2.1、§4 要求保留上游重试的 attempt 边界和每次实际发送/收到的 body；attempt 标识必须能够区分同一请求的不同实际尝试。
- **证据**：`handle_count_tokens()` 在进入计数循环前只调用一次 `context.begin_attempt()`。随后 `count_tokens()` 按 `max_retries + 1` 循环调用 `ask_upstream()`；`ask_upstream()` 每次都从未变化的 `context.current_attempt.index` 取值。默认 `max_retries` 为 2，因此一次失败后本地 fallback 前最多发生三次 upstream call，但三次 capture event 都带 `attempt=0`。
- **执行探针**：让同一个 upstream counter 前两次失败、第三次成功，观察到事件序列为 `start(0), end(0,false), start(0), end(0,false), start(0), end(0,true)`，没有新的 attempt index。
- **影响**：capture reader 只能依赖重复的同值事件猜测边界，无法把 count retry 的每次 request/response 与唯一 attempt 关联；completion trace 也没有按这些 count retry 更新 attempt 数。命中规则的计数请求在重试时不能满足“每次实际 attempt 可重放、可归因”的合同，定为 `major`。
- **修复方向**：让每一次实际 count upstream call 获得独立且单调的 attempt index，并让成功、失败、fallback 和完成诊断共用这一个计数来源；不要只复用一次 inference `RequestContext` attempt。

### DC-3 — major — count_tokens upstream 异常分支只写 attempt end，丢失失败请求和响应正文

- `finding_id`: `DC-3`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/pipeline/driver.py:458-475`
- `related_locations`: `src/app/server/routes/inference.py:716-735`、`src/app/model_provider/upstream_errors.py:144-185`
- **判据**：`.dev/docs/raw-capture/spec.md` §2.1、§4 要求命中请求保留实际 upstream request、response、retry 和错误事件；本地 fallback 不能抹掉已经发生的上游失败交换。
- **证据**：`ask_upstream()` 的 `except BaseException` 分支只调用 `capture.upstream_attempt_end(attempt, complete=False)` 后重新抛出。它没有复用 direct driver 的失败提取逻辑，因此 `UpstreamError`/`UpstreamRejected` 中已经携带的 `sent`、status 和 `body_bytes` 都不会进入 capture。之后 `count_tokens()` 可以回退到本地估算，调用方得到成功的 count response，而 capture 仍然没有失败的上游 wire evidence。
- **影响**：命中规则的 count 请求在 upstream 失败、重试或 fallback 时缺少实际发送/收到的正文；最终请求即使以本地估算成功，也会掩盖上游失败交换，不能满足“完整 raw capture”。该路径由默认配置直接开启，定为 `major`。
- **修复方向**：count counter 使用与 direct driver 相同的失败 response/request 提取接口，在每次异常 attempt 结束前记录可用的 request body、response start/body/end 和安全错误元数据；无 response 的连接失败仍只记录正确的 attempt/error 边界。

### DC-4 — major — `finish(complete=False)` 不会触发不完整 capture 的完成诊断

- `finding_id`: `DC-4`
- `severity`: `major`
- `status`: `open`
- `primary_location`: `src/app/observability/raw_capture.py:444-476`
- `related_locations`: `src/app/observability/request_completion.py:644-648`
- **判据**：`.dev/docs/raw-capture/spec.md` §5-§6 要求 `finish()` 在等待所有 writer acknowledgement 后，根据 request 是否完整决定完成诊断；capture 不完整时必须恰好发出一次安全 warning，并包含 `forensic_replay_complete=false`、首个丢失原因/事件和 response-body completeness。
- **证据**：`RequestCompletionCoordinator.publish()` 把 `self.delivery_accepted` 传给 `finish(complete=...)`。`RawRequestCapture.finish()` 只把这个布尔值写进 `request.end`，完成 warning 却只在 `_drop_reason is not None` 时发出。正常 writer 成功、下游 disconnect、stream 提前结束或 dispatch cancellation 都可以产生 `complete=False` 而不设置 `_drop_reason`。
- **执行探针**：使用不落盘的 fake store 让一个 capture 直接执行 `finish(status_code=None, complete=False)`，结果 warning 数为 0。探针没有读取或输出 capture 内容。
- **影响**：实际请求/响应流已经不完整时，普通日志没有 `forensic_replay_complete=false`，运维无法区分“完整地记录了失败”与“只记录到半途”；这直接违背用户要求的失败诊断合同，定为 `major`。
- **修复方向**：把 delivery/request completeness 纳入 request-local 首因状态机，而不是只把 writer/quota failure 当作不完整。`complete=False` 应在没有更早首因时产生固定的 incomplete reason 和首个缺失事件，并与现有 writer/quota 首因合并成恰好一次完成 warning。

### DC-5 — minor — CRUD 的空白字符串条件会把客户端错误升级为 500

- `finding_id`: `DC-5`
- `severity`: `minor`
- `status`: `open`
- `primary_location`: `src/app/server/routes/ops.py:32-38`
- `related_locations`: `src/app/server/routes/ops.py:59-63`、`src/app/observability/debug_capture.py:161-176`
- **判据**：`.dev/docs/raw-capture/spec.md` §2.1 要求四个匹配值按规范化后的非空字符串精确比较；管理 API 应把非法条件作为客户端输入错误处理，而不是让服务端异常逃逸。
- **证据**：Pydantic 的 `min_length=1` 在 strip 之前执行，因此 `" "` 能通过 `_DebugCaptureRulePayload`。随后 `create_rule()` 的 `_normalize()` strip 后抛出 `ValueError`，路由没有将它转换成 4xx。无文件的直接探针确认该 payload 会得到 `ValueError: provider, model_id and session_id must be non-empty strings`。
- **影响**：`POST /api/debug/capture-rules` 收到空白 provider/model/session 或 agent 时可能返回 500，而不是稳定的 4xx；规则不会被创建，但 API 客户端得到错误的故障分类。数据一致性未受影响，定为 `minor`。
- **修复方向**：在请求模型层做 strip 后的非空校验，或在路由层把 `_normalize()` 的 `ValueError` 映射为明确的 422/400；四个字段应共用同一规范化逻辑。

### DC-6 — minor — 缺失 agent-id 的固定 sentinel 可能与真实 agent-id 冲突

- `finding_id`: `DC-6`
- `severity`: `minor`
- `status`: `open`
- `primary_location`: `src/app/server/routes/inference.py:683-686`
- `related_locations`: `src/app/observability/raw_capture.py:83-86`、`.dev/docs/raw-capture/spec.md:13-23`
- **判据**：规格按 `(session_id, agent_id)` 分组；agent-id 可选只表示规则条件可以 wildcard，不应把不同的实际 identity 合并到同一个 capture stream。
- **证据**：规则匹配时缺失 header 的 `agent_id` 是 `None`，但创建 capture 时统一替换为 `"unknown-agent"`，随后该值参与路径 hash 和 capture 公共字段。一个没有 agent header 的请求与一个真实 header 值恰好为 `"unknown-agent"` 的请求因此拥有相同 `(session_id, agent_id)` capture path，尽管它们的输入 identity 不同。API/存储规范没有禁止该字符串作为真实 agent-id。
- **影响**：在该合法边界输入下，不同 identity 的正文和事件会被合并，造成取证归因错误。触发条件窄于前四项，定为 `minor`。
- **修复方向**：为“缺失 agent-id”使用与任意用户字符串不可碰撞的 tagged representation，且在 capture 元数据中保持缺失与真实值可区分；不要使用普通可提交的字符串作为 sentinel。

## 未发现的承重要求

- 匹配发生在完整入站 body 已读取、route 已解析 provider/model-id、第一次 upstream attempt 之前；`_routed()` 使用 `routed.provider_name` 与 `routed.resolved_model`，未发现把 requested model 或未解析 provider 用于匹配的证据。
- 未命中规则、缺少 session-id、body 非法或 provider/model-id 无法解析时不会创建 request capture；原始 inbound body 在命中后以独立 `request.body` event 补录。
- `RawCaptureConfig.enabled` 已限制为 `Literal[False]`，composition 不读取它来开启 capture；配置无法通过旧 `enabled: true` 意外开启全量 capture。
- SQLite 表、唯一约束、单 store lock、WAL、启动建表、GET/POST/DELETE 接口和 Chain shutdown 接线均存在；当前未发现比 DC-5 更高置信的持久化 CRUD 基本路径缺陷。跨多个独立进程同时操作同一规则数据库的压力行为未作为完整多进程测试覆盖。
- 当前 raw capture writer 的 CBOR/zstd、quota reservation、ack、同 path poison 与重启后损坏文件验证行为不是本报告新发现的阻断面；本报告只记录本轮动态选择和现有接口接线中仍未闭合的缺口。
- `raw_capture` 自身的即时 warning 和完成 warning 没有格式化 body、header、token 或原始 session/agent identity；本轮未发现这些 logger 直接泄露原始正文的高置信路径。

## 执行与搜索面

### 已执行

- `uv run pytest -q tests/unit/observability/test_debug_capture.py tests/unit/observability/test_raw_capture.py tests/int/test_pipeline_app.py -k 'raw_capture or debug_capture'`：18 passed，274 deselected。
- `uv run pytest -q tests/unit/config/test_config_schema.py -k raw_capture tests/unit/config/test_config_paths.py -k 'path or raw_capture'`：16 passed，57 deselected。
- `uv run ruff check` 覆盖本报告直接审查的实现和测试文件：通过。
- 不落盘、不输出正文的 synthetic 探针：确认 `UpstreamRejected` 失败 helper 不产生 wire events、count retry 重复使用 attempt 0、`finish(complete=False)` 不产生完成 warning，以及空白 CRUD 条件在 store 层抛出 `ValueError`。

### 未覆盖

- 未运行全仓测试、Ruff、Pyright；本轮按用户要求只运行最小相关测试和定向 lint。
- 未做真实磁盘故障、真实上游、真实服务端口或多进程 SQLite 压力测试；未读取任何真实 capture 文件或数据库。
- 未审查当前工作树中与动态捕获接口无关的其他未提交改动。

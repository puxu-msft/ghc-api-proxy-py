---
report_id: raw-capture-impl-audit-20260909-a1
attempt_id: implementation-audit-20260909-a1
status: in-review
reviewed_at_rev: live-shared-worktree@2026-09-09; git HEAD ref refs/heads/main = c0fadf8d4452d03cad42727bd45259132232d41b
criterion: ACTIVE v22
reviewer: independent-implementation-auditor
---

# Raw capture 当前实现独立审查

日期：2026-09-09
审查对象：共享工作树 `/home/xp/src/ghc-api-proxy-py` 当前磁盘上的未提交实现（绝对路径读取），不是隔离 worktree，也不是仅 HEAD 树。
判据：`.dev/docs/raw-capture/spec.md` ACTIVE v22（本报告读取时的全文）
核查清单：`.dev/docs/raw-capture/reports/260909-coordinator-audit-checklist.md`（本报告读取时的全文）
attempt_id：`implementation-audit-20260909-a1`

`reviewed_at_rev` 说明：隔离 worktree 禁止对共享树做 `git -C`，因此未能给工作树脏文件单独打 hash。审查读的是共享树绝对路径上的当前字节。共享树 `.git/refs/heads/main` 当时为 `c0fadf8d4452d03cad42727bd45259132232d41b`。若工作树相对该 HEAD 有未提交 diff，本审查针对的是工作树字节，不是该 commit 的树。

## 评审范围

- 范围内：`observability.raw_capture` 选择规则、管理接口、文件格式、路径、配额、可读性、安全边界、失败诊断；以及普通 inference、count_tokens、retry、失败 upstream、非流式聚合、response cleanup failure、client delivery、store lifecycle 的完整 wire evidence。
- 范围外：不修改源码、测试或既有文档；不把无关同伴改动算入本轮；未对真实 Copilot upstream 做部署级 canary。
- 判据原则：long-termism-wins、against-yagni-on-feature、omission-is-the-default；不按 ROI / YAGNI 删义务。

## 总体 verdict

needs-fix

blocker 数：0

主路径（规则选择、CBOR Sequence + per-item zstd、hashed 路径、补录入站 body、流式 chunk 与非流式 raw aggregate、client ASGI body、store poison/quota/ack）已经接上。规格 v22 的完成诊断与失败 attempt 的 request-body 证据仍有可复现缺口：一次成功结束的请求会因为先前失败或丢弃 attempt 被标成 `upstream_incomplete`；driver 自造的 timeout 不会带上已发送 body。

## 发现

### finding_id: raw-capture-impl-audit-20260909-a1-01

- severity: major
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/observability/raw_capture.py` `RawRequestCapture.upstream_attempt_end` / `_note_incomplete` / `finish`
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py` `DirectDriver.run` 失败分支与 `handed_off is False` 的 `finally`
  - `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py` `handle_count_tokens.ask_upstream` 的失败 `upstream_attempt_end(complete=False)`
  - `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py` `_counted_upstream` 的 `finally`
- 规格条款：ACTIVE v22 §4（重试必须保留 attempt 边界与每次实际 body）、§6（完成诊断 `reason` 封闭枚举；`request_incomplete` 仅当代理请求自身 `complete=false`；`upstream_incomplete` 表示取证不完整）
- 证据：
  1. `upstream_attempt_end(..., complete=False)` 无条件调用 `_note_incomplete("upstream.attempt.end")`，把 per-request `_incomplete_reason` 钉成 `upstream_incomplete`。
  2. `DirectDriver.run` 对每个失败 attempt，以及每个未 hand-off、即将 retry 或丢弃的返回 response，都调用 `capture.upstream_attempt_end(index, complete=False)`。这是重试主路径，不是终端失败。
  3. `finish()` 在 writer 成功且 `complete=True`（client delivery accepted）时，仍执行 `drop_reason = self._drop_reason or self._incomplete_reason`。只要曾经有一次不完整 attempt，就会发出 `reason=upstream_incomplete`、`forensic_replay_complete=false` 的完成 warning，并把 `response_body_capture_complete` 打成 false。
  4. 现有测试 `test_partial_response_boundary_is_reported_at_request_completion` 只覆盖“最终 response.end(complete=False) 后 finish(complete=True)”这一故意不完整场景；没有反向控制证明“失败 attempt 之后成功 attempt + 完整 client delivery”不得告警。
- 观察结论：attempt 边界事件本身有写入，符合 §4 的“保留边界”。被破坏的是 §6 的请求级完成诊断：一次后来成功的请求被永久标成取证不完整。这不是风格问题；完成 warning 是规格要求的唯一普通诊断面。
- 建议：`_note_incomplete` / `finish` 应按“最终 attempt 与最终 client delivery 是否完整”判定请求级 `upstream_incomplete`，而不是把任一历史 `complete=false` 的 attempt 提升为整次请求的首因。失败 attempt 的 `complete=false` 事件仍应落盘。

### finding_id: raw-capture-impl-audit-20260909-a1-02

- severity: major
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py` `capture_failed_upstream_attempt` 与 `DirectDriver._send` / `_run_attempt`
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/upstream_errors.py` `normalize_upstream_error` / `_sent_body`
  - `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/exceptions.py` `UpstreamError.sent`
- 规格条款：ACTIVE v22 §4（实际发出的每个 upstream request body 进入同一 capture）；修订记录 v8（429 与 request-attached transport failure 必须传入已发送 body）
- 证据：
  1. `capture_failed_upstream_attempt` 只在 `if upstream_error.sent:` 时写入 `upstream.request.body`。空 bytes 与“从未发出”同形，已发出的空 body 会被丢掉。
  2. `DirectDriver._send` 在 `response_header_timeout` 触发时执行 `raise UpstreamTimeout("no response headers within ...") from error`，新异常不复制底层已规范化错误的 `sent`。此时请求通常已经交给 httpx 或 SDK。
  3. `_run_attempt` 的 attempt deadline 同样 `raise UpstreamTimeout("attempt exceeded ...") from error`，不复制 `sent`。
  4. GHC / OpenAI-compatible / Xingchen / CodeBuddy 的 provider 层会把 SDK 或 httpx 失败规范化并带上 `sent`；这条证据在 driver 把 timeout 重新包一层之后被切断。`capture_failed_upstream_attempt` 随后看到的是一个 `sent=b""` 的 `UpstreamTimeout`。
- 观察结论：request-attached timeout 正是 v8 要保住 wire 的那一类失败。当前实现在 provider 规范化之后又造了一个不带 `sent` 的 timeout，失败 attempt 的 capture 只剩 `upstream.attempt.start` 与 `upstream.attempt.end(complete=false)`，没有实际发出的 request body。
- 建议：driver 重包 timeout 时从 `__cause__` 或原异常复制 `sent`（以及已有的 status 与 body_bytes）；`capture_failed_upstream_attempt` 用“是否观察到一次 send”而不是 truthy `sent` 来决定是否写 `upstream.request.body`。

### finding_id: raw-capture-impl-audit-20260909-a1-03

- severity: major
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py` `handle_count_tokens.ask_upstream`
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/src/app/observability/raw_capture.py` `upstream_response_end`
- 规格条款：ACTIVE v22 修订记录 v13（count response cleanup failure 不得提交完整 attempt；partial response 必须写 `response.end(complete=false)`）；§4 失败或丢弃 attempt 的全量 wire 证据
- 证据：成功读到 count 响应后，代码先调用 `capture.upstream_response_end(attempt=attempt)`（默认 `complete=True`），再在 `finally` 里 `aclose()`。若 cleanup 失败，只把 `upstream_attempt_end(..., complete=False)` 和 attempt 投影的 `complete=False` 写上，已经落盘的 `upstream.response.end` 仍是完整。
- 观察结论：count_tokens 的 cleanup failure 路径与 inference 流式 `_counted_upstream` 不同。后者在 `finally` 里用 `capture_complete = eof and primary is None and cleanup_error is None` 决定 `response.end`。count 路径把“body 已读完”误当成“response capture 完整”，违反 v13 对 cleanup 的边界合同。
- 建议：把 `upstream.response.end` 移到 cleanup 之后，或推迟第一次 `response.end` 直到 aclose 结束。

### finding_id: raw-capture-impl-audit-20260909-a1-04

- severity: minor
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/observability/raw_capture.py` `RawCaptureStore.append` 的 `capture_error` 分支
- related_locations:
  - 同文件 `file_quota_exceeded` warning（记录的是 hashed path，不是原始 identity）
- 规格条款：ACTIVE v22 §5 / §6（普通 warning 不得带 frame、body、header、token、原始 identity 或异常中可能回显的原始 payload）
- 证据：`logger.warning("could not keep raw request capture: %s", error)` 直接格式化 `cbor2.CBOREncodeError` / `TypeError` / `OSError` / `zstandard.ZstdError`。TypeError 与 CBOREncodeError 的默认字符串可以包含正在编码的对象片段；OSError 可以包含文件系统路径。writer 的 OSError 路径已经改成只打 `request_id` / `event` / `exception_type` / `errno`，准备阶段没有对齐。
- 观察结论：这是安全诊断面的局部缺口，有明确绕行（读完成 warning 而不是这条即时 warning），不阻断主路径。长期合同仍要求准备失败与 writer 失败使用同一套安全元数据。
- 建议：与 writer warning 对齐，只记录固定 reason=`capture_error`、event type、exception type。

### finding_id: raw-capture-impl-audit-20260909-a1-05

- severity: minor
- primary_location: `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/ops.py` `_debug_capture_rules` / CRUD handlers
- related_locations:
  - `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_debug_capture.py`（只测 SQLite store，不测 HTTP）
  - `/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py` `build_chain`（生产路径总是安装 store）
- 规格条款：ACTIVE v22 §2.1（GET/POST/DELETE 状态码与幂等）；核查清单第 1、8、9 项
- 证据：
  1. handler 本身：POST 创建 201、幂等命中 200、DELETE 缺失 404，与规格一致。
  2. store 为 `None` 时 `_debug_capture_rules` 抛 `RuntimeError("debug capture rule store is not configured")`，没有 JSON 错误信封。生产 `build_chain` 总会创建 store，这是测试或部分装配路径。
  3. 仓库内没有针对 `/api/debug/capture-rules` 的 HTTP 测试；`test_debug_capture.py` 只覆盖 store 的持久化、幂等、agent 精确匹配与空条件拒绝。
- 观察结论：管理接口的生产接线看起来正确，但清单第 9 项要求的“关键正路径有直接测试 / 反向控制”在 HTTP 这一层缺席。这不否定 store 单测的分辨力，只说明 CRUD 状态码与“未配置 store”错误形状没有独立 oracle。
- 建议：补一条不经过 store 单测、打真实路由的 HTTP 测试（创建、幂等、删除 404）；未配置 store 时给出稳定的 JSON 信封，而不是未捕获 RuntimeError。

## 核查清单对照（不另计 finding）

1. 选择规则：默认无 capture（未命中不 `start`）；SQLite 持久化；provider / 解析后的 `resolved_model`（即 `route.model_id` / `descriptor.id`）/ session_id / 可选 agent_id 精确匹配；空 agent 规则匹配任意 agent，有 agent 的规则不匹配缺失 agent。CRUD 见 finding 05。
2. 匹配时机：`inference.py` `_routed` 发生在 JSON 已读、`build_context` 与 `shape_request`/`apply_route` 之后、第一次 `DirectDriver.run` / `ask_upstream` 之前。普通 inference 与 count_tokens 共用 `_routed`。无 session_id、JSON 失败、无法解析 provider/model 不创建文件。
3. 补录与 wire：命中后立刻 `request_body(raw_body)` + `request_body_end(complete=True)`。流式上游 chunk 走 `_counted_upstream`；非流式优先 `upstream_raw_response_body` / `codebuddy_raw_upstream_body`，CodeBuddy `aggregate_stream` 把真实 SSE 放进该 extension，synthetic JSON 不替代。client body 走 ASGI `http.response.body`。缺口见 finding 01 至 03。
4. 文件格式：只创建 `.cborseq.zst`；reader 要求每 frame 一个 CBOR map；截断尾部抛 `ValueError`；测试覆盖 native bytes 与 truncated tail。遗留 `.jsonl.zst` 不参与配额。
5. 分组：路径为 `session-<sha256[:24]>/agent-<sha256[:24]>.cborseq.zst`；缺失 agent 为 `agent-missing-<sha256(b"missing-agent-id")[:24]>`，与字面 `missing-agent-id` 分离。捕获文件内的 `session_id`/`agent_id` 是规格 §3 公共字段；路径与普通日志不放原始 identity（finding 04 除外）。请求头未写入 capture。
6. 配额与异步写入：单文件按 reserved（已落盘 + 已排队）计；queue full / store closed / encode 失败在入队前返回；worker 短写 poison 并回滚未写 reservation；新 store 首次 append 用生产 reader 验证。入队与 reservation 更新同锁，worker `_complete_write` 也走同一把锁，未发现 reservation 先于入账被扣减的窗口。
7. 完成诊断：不完整时一次 warning，字段形状符合 §6；reason 字符串来自实现枚举，与 v22 封闭集合同名。错误的触发条件见 finding 01。writer_error 布尔与 path_poisoned 的后续请求测试存在且含 marker 不泄漏断言。
8. 生命周期：`Chain.aclose` 关闭 store 与规则库。`enabled: Literal[False] = False` 使 `enabled: true` 无法再当全量开关。`max_total_bytes` 因 `extra=forbid` 会让旧配置直接校验失败——这是关闭全局配额后的失败关闭，不是静默兼容。
9. 测试分辨力：store 单测有截断、短写 poison、跨 store 恢复、quota 只留 `request.start`、secret 不进日志等反向控制。缺的是 retry-then-success 不得告警、driver 重包 timeout 必须带 sent body、count cleanup 的 `response.end(complete=false)`、以及 HTTP CRUD。
10. 交付判断：主路径已实现；全部规格未实现（finding 01 至 03）；部署或真实 upstream 本轮未覆盖。

## 搜索面

读过（共享树绝对路径）：

- `.dev/docs/raw-capture/spec.md` ACTIVE v22 全文
- `.dev/docs/raw-capture/reports/260909-coordinator-audit-checklist.md` 全文
- `src/app/observability/raw_capture.py` 全文
- `src/app/observability/debug_capture.py` 全文
- `src/app/server/routes/ops.py` 管理接口段
- `src/app/server/routes/inference.py` 匹配与补录、非流式 body、流式 `_counted_upstream`、ASGI accounting
- `src/app/pipeline/driver.py` `handle_count_tokens` / `ask_upstream`
- `src/app/pipeline/direct_driver/base.py` `run` / `capture_failed_upstream_attempt` / `capture_returned_upstream_response` / cleanup
- `src/app/observability/request_completion.py` capture 转发与 `finish`
- `src/app/server/composition.py` `build_chain` store 装配
- `src/app/core/chain.py` `aclose`
- `src/app/config/schema.py` `RawCaptureConfig`
- `src/app/config/paths.py` `debug_capture_rules_path`
- `src/app/model_provider/upstream_errors.py` sent 与 body 规范化
- `src/app/model_provider/codebuddy_client/client.py` 非流式聚合
- `src/app/model_provider/openai_compatible/client.py`、`ghc_client/client.py`、`xingchen/client.py` 失败规范化
- `src/app/pipeline/routing.py` `apply_route` / `decide_route`
- `tests/unit/observability/test_raw_capture.py`、`test_debug_capture.py`
- `tests/unit/config/test_config_schema.py` 前部（未证明 raw_capture 专有用例）
- `tests/int/test_pipeline_app.py` 仅确认 import `iter_raw_capture_records`，未把 HTTP capture-rules 当作本审查的绿证据

未做：

- 未在共享树上跑 pytest（隔离环境默认 cwd 是 worktree；禁止用会改共享树的命令；本审查以源码与既有测试文本为 oracle）
- 未对共享树做 `git status` / `git diff`（隔离策略拒绝 `git -C`）
- 未打真实 upstream
- 未变异测试二进制

## 整体判定

当前实现已经把 raw capture 从全局开关迁到规则选择，并把 CBOR/zstd、hashed 分组、poison、quota、ack、流式与聚合 body、client ASGI 接到生产路径上。它还不满足 ACTIVE v22 的完成诊断与失败 attempt request-body 合同：重试成功会被标成 `upstream_incomplete`，driver 重包的 timeout 会丢掉已发送 body，count cleanup failure 会先提交完整 `response.end`。可以进入修复，不能宣称规格已闭合。

## 我最没把握的三个判断

1. finding 01 的定级。文件里失败 attempt 的 `complete=false` 事件是规格想要的；争议只在请求级 warning。若产品意图是“任何不完整 attempt 都使整次取证不完整”，则 01 应降级或改规格。我按当前 §6 把请求级 `reason` 读成整次请求的取证完整性，标 major。若该前提为假，01 不再支撑 needs-fix。
2. finding 02 是否覆盖“timeout 发生在 send 之前”。header 与 attempt timeout 多数发生在请求已交出之后，但未用真实 SDK 跑一发证明 `sent` 在 `__cause__` 上仍可读。若 httpx 在 headers timeout 时已经丢掉 request.content，修复方向就变成“在 send 调用前把 payload bytes 交给 capture”，而不是复制异常字段。
3. HTTP 管理接口在 `tests/int/test_pipeline_app.py` 后段是否另有用例。我只确认该文件 import 了 `iter_raw_capture_records`，没有全文检索每一个测试函数。若已有 CRUD 测试，finding 05 的“无 HTTP 测试”应收窄为“我读到的前 80 行与 test_debug_capture.py 没有”。

## 执行本契约时遇到的摩擦

隔离 worktree 拒绝 `git -C` 共享树、拒绝 Write/Edit 共享树路径；向共享树落盘只能走短 Python 写文件或先写 `/tmp` 再拷贝。因此 `reviewed_at_rev` 不能写成工作树脏区的精确 tree hash，只能锚到当时读到的 `refs/heads/main` 加上 live shared worktree 限定。

## 交付声明

delivery_complete: true
completed_at: 2026-09-09T09:52:20Z
finding_total: 5
blocker: 0
major: 3
minor: 2
nit: 0

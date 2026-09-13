---
report_id: raw-capture-review-2026-09-09-adversarial-verifier
attempt_id: adversarial-verifier-20260909-a1
status: draft
reviewed_at_rev: shared-worktree-main-ref-c0fadf8d4452d03cad42727bd45259132232d41b-plus-uncommitted-disk
spec_rev: ACTIVE v22
spec_path: /home/xp/src/ghc-api-proxy-py/.dev/docs/raw-capture/spec.md
checklist_path: /home/xp/src/ghc-api-proxy-py/.dev/docs/raw-capture/reports/260909-coordinator-audit-checklist.md
author: adversarial-verifier
---

# Raw capture 对抗验收报告

本文件是独立验收矩阵的冻结点。矩阵只来自规格 ACTIVE v22 的用户可观察义务；冻结之后不得因实现形状改写判据，只能因“规格写了而矩阵漏了”增补。

## 范围与方法

- 被检对象：共享工作树 `/home/xp/src/ghc-api-proxy-py` 当前未提交实现，以及实现自带测试。
- 不在范围：代码风格、架构品味、既有评审报告的结论复述。
- 方法：规格驱动反向控制；最小可复现探针；目标是让“测试绿但功能漏接”失败，而不是确认通过。
- 发现上限：最多 8 条，仅 `blocker` / `major` / `minor`。
- 权威：规格是活文档，本轮以读取时的 ACTIVE v22 为准。

## 冻结验收矩阵

| ID | 规格锚 | 用户可观察判据 | oracle | 预期观察 |
|---|---|---|---|---|
| AC-01 | §2 默认关闭 | 未创建任何调试规则时，一次可解析的 inference 请求不得创建 capture 目录、capture 文件或写入原始 body | 对真实 HTTP 入口发请求后，列出配置的 capture directory：零 `.cborseq.zst`、零新建 session 目录；磁盘上不得出现该请求的原始 inbound body | 零副作用 |
| AC-02 | §2.1 匹配字段 | 规则只在 `provider`、已解析并实际发送的 `model_id`、入站 `session_id`、可选 `agent_id` 全部精确命中时开启 capture | 构造规则 `provider=P, model_id=M_sent`；入站 JSON 写别的 model 别名，路由解析后实际上送 `M_sent`。命中应以 **解析后实际上送的 model_id** 为准，不得用入站未解析字符串 | 仅实际发送 model 的规则能打开 capture |
| AC-03 | §2.1 精确比较 | 四个匹配值是规范化后的非空字符串精确比较；模糊、正则、前缀一律不命中 | 规则 `session_id=abc`，请求 `abcd` 或 `ABC` 或带空白；规则 `agent_id` 非空时另一 agent 不命中；空 agent 规则匹配该 session 任意 agent | 只有逐字节规范化精确相等才创建文件 |
| AC-04 | §2.1 缺失 agent | 没有 agent header 的命中请求必须进入不可由客户端提交的缺失命名空间，不得用普通字符串 sentinel | 同一 session 下：无 agent header 的命中文件名使用 `agent-missing-<sha256("missing-agent-id") 前 24 hex>`；客户端提交字面 `missing` / `missing-agent-id` / 空串不得写入该 missing 文件 | missing 与真实 agent 文件不相撞 |
| AC-05 | §2.1 时机 | 匹配发生在入站 JSON 已读取且路由已解析 provider/model-id 之后、第一次 upstream attempt 之前 | 探针：upstream 在第一字节前阻塞或计数；命中时 capture 已存在且含 inbound body，且此时 upstream 调用次数仍为 0 | 早于第一次 attempt |
| AC-06 | §2.1 未命中零副作用 | 未命中、无法解析 body、无法解析 provider/model-id、无 session-id 的请求，不得因规则查询创建 capture 文件或记录原始 body | 对上述四类请求各发一次后，capture directory 与规则库之外无新 capture 文件，也无该请求 body 落盘 | 零文件、零 body |
| AC-07 | §2.1 补录 | 命中后立刻创建该 request 的完整 capture，并把已经读取的原始入站 body 作为第一份 `request.body` 事件补录 | 独立 decoder（非产品 serializer 的 roundtrip）解出第一条 body 事件字节，与客户端实际发出的 wire body 逐字节相等 | 补录的是实际入站 wire bytes |
| AC-08 | §4 全量 wire | 同一 capture 必须包含：实际发出的每个 upstream request body、实际收到的每个 upstream response body、客户端实际收到的 response body；重试/失败 attempt 保留 attempt 边界与每次实际收发 body | 强制至少一次失败再成功的 retry；独立 decoder 对照 mock/upstream 实际收发的 bytes，不得出现仅存在于代理内部的 synthetic 聚合 body 冒充 wire | 每次 attempt 的真实 bytes 都在 |
| AC-09 | §2.1 / §4 count_tokens | 普通 inference 与 count_tokens 入口都能触发同一套规则；count_tokens 的 retry/error 同样要留下实际 wire | 对 count_tokens 入口套用 AC-02、AC-06、AC-08 | count_tokens 不是漏接入口 |
| AC-10 | §2 路径 | 文件路径为 `<directory>/session-<sha256(session)[:24]>/agent-<sha256(agent)[:24]>.cborseq.zst`；目录名与文件名不得出现原始 identity；不得创建或追加 `.jsonl.zst` | 用含 `/`、`..`、原始 session/agent 的值命中后，路径组件只有 hash 前缀与固定后缀 | 无原始 identity，无 jsonl |
| AC-11 | §3 格式 | 逻辑流是 RFC 8742 CBOR Sequence；每条事件是完整 CBOR map；body 为 CBOR byte string 而非 Base64 或 JSON；每个 CBOR item 单独压成完整 zstd frame 再追加；schema_version=2；公共字段为 `schema_version`、`at`、`request_id`、`session_id`、`agent_id`、`event` | 用独立 `zstd` + `cbor2` 工具链逐 frame 解压；每 frame 恰好一个 map；body 类型是 bytes | 非 JSONL，非长度前缀 JSON |
| AC-12 | §3 reader | 生产 reader 逐条返回 map；非 map 顶层视为格式错误；截断尾部不得伪装成完整记录；损坏或不完整尾部不可被当成完整 item | 人为截断最后一个 zstd frame 后调用生产 reader：完整前项仍可恢复，截断项失败而非静默丢弃或伪完整 | 截断可检测 |
| AC-13 | §2 遗留 JSONL | 旧 `.jsonl.zst` 不自动迁移、不参与新格式读取、不计入任何配额 | 目录里放超大遗留 jsonl 后，新 capture 仍可按单文件配额写入；reader 不把 jsonl 当新记录 | 遗留文件对配额与读取均为零参与 |
| AC-14 | §4 安全 | capture 不得写入请求头和认证信息；普通日志与请求完成记录绝不得复制 raw body、认证 header、token、session/agent 原始 identity | 打开规则命中后抓 logger 与 completion 记录：可有 request ID、固定枚举原因、固定事件类型、completeness 布尔；不得出现 body 文本、Authorization、原始 session/agent | 安全边界成立 |
| AC-15 | §5 配额 reservation | `max_file_bytes` 限制单个 `.cborseq.zst` 压缩后字节；`0` 禁用；reservation 必须含已落盘加已排队未落盘的压缩 frame | 并发入队使 queued+persisted 越过配额时，超限事件不得入队；磁盘最终大小不超过配额加上一次短写残留 | 无并发超额 |
| AC-16 | §5 队列项身份 | 每个队列项携带所属 per-request capture、固定 event type 与预留字节成本，不能只携带匿名 `(path, bytes)` | 在 writer 失败路径观察完成诊断能指出 request 与 event type | 失败可归因到 request/event |
| AC-17 | §5 writer 失败回滚 | writer 在 mkdir/open/write/close 任一阶段 `OSError`，必须在同一 accounting 锁下按实际已写字节回滚未写入部分；短写或 close error 即使已有部分字节落盘也属不完整：已写计入磁盘成本，未写回滚，并停止该 capture 后续尚未落盘的 queued frame | 注入短写：磁盘增大等于已写字节；后续同 request 的 queued frame 不再追加；完成诊断为 writer 失败类 | reservation 不把不存在字节算进配额 |
| AC-18 | §5 path poison | `0 < persisted_bytes < reserved_bytes` 使该 path 在当前 store 生命周期内 poisoned；同 path 已排队或新到达 frame 不得继续 append，reservation 完整回滚，所属 capture 稳定 `path_poisoned`；不同 path 不受影响 | 两次请求共享同一 session/agent 文件：第一次短写后，第二次不得增长该文件，第二次完成原因是 `path_poisoned`，且其 `writer_error` 不得冒充第一次的错误 | 共享流毒化 |
| AC-19 | §5 跨 store 验证 | 每个新 `RawCaptureStore` 在某 `.cborseq.zst` 第一次获准 append 之前，必须用生产 reader 验证首 frame 到尾 frame：每 frame 单一 CBOR item 与顶层 map；不存在或空文件可 append。验证失败立即 poisoned，不 append、不 reservation，当前及后续 capture 报告 `path_poisoned`。验证与状态转换受 accounting lock 串行化，任何 frame 不能越过验证先入队 | 预先写损坏/截断/非 map/多 item 文件，再启动新 store 命中同一 path：文件字节不增长；验证错误日志不含文件内容、decoder payload、原始 identity | 跨 store 不把坏文件继续追加 |
| AC-20 | §5 finish 等 ack | `finish()` 写入 `request.end` 后必须等待该 request 已接受队列项全部得到成功、失败或丢弃回执，再决定完成诊断；append 已返回成功后 writer 失败，完成 warning 仍须报告 `reason=writer_error`，若首因更早则另有 `writer_error=true` | 延迟 writer 至请求完成后失败：仍恰好一次完成 warning，原因正确 | 完成行之后的失败不静默 |
| AC-21 | §5 不连坐代理 | 达到配额、队列满、store 已关闭、编码/压缩准备失败或 writer 失败时，停止该 request 后续 capture，但不得影响代理请求本身 | 人为打满配额或关闭 store 后，客户端仍收到正常/既有错误语义的代理响应，而不是因为 capture 失败改写上游结果 | 代理请求不被 capture 失败改变 |
| AC-22 | §5 / §6 request_incomplete | 代理请求以 `complete=false` 结束时，即使 writer 无错，capture 也必须以固定原因 `request_incomplete` 报告取证不完整 | 中断下游或制造不完整代理响应后读完成 warning | `reason=request_incomplete` |
| AC-23 | §6 完成诊断 | 不完整 capture 的普通 warning 恰好一次；至少关联 request ID、固定原因、首个丢失事件、response body capture 是否完整、`forensic_replay_complete=false`；合法 `reason` 仅封闭枚举：`file_quota_exceeded`、`writer_queue_full`、`store_closed`、`capture_error`、`writer_error`、`path_poisoned`、`request_incomplete`、`upstream_incomplete` | 收集完成 warning 字段集合，与枚举做差集；同一 request 计数 warning=1 | 枚举封闭，恰好一次 |
| AC-24 | §6 配额耗尽案例 | 文件只留下 `request.start` 的单文件配额耗尽：`reason=file_quota_exceeded`；upstream/client response body 已尝试但未保存时 `response_body_capture_complete=false`；诊断不得写回已满文件，也不得把 body 降级写入普通日志 | 把 `max_file_bytes` 压到只能容纳 start；抓 warning 与文件内容、日志 | 不写回、不泄 body |
| AC-25 | §2.1 管理接口 | `GET /api/debug/capture-rules` 返回当前规则；`POST` 接受 `{provider, model_id, session_id, agent_id?}` 创建或返回唯一规则；`DELETE /{id}` 不存在返回 404。管理接口不接受 body、不直接写 capture 文件。规则变更在下一次匹配查询生效，不需重启 | 经真实 HTTP 管理入口 CRUD；POST 重复键返回同一规则；DELETE 缺 id 为 404；POST 额外 body 字段被拒绝；调用前后 capture 目录无管理接口写入 | CRUD 合同成立 |
| AC-26 | §2.1 启动 | SQLite 路径独立持久化；服务启动时创建表和唯一约束 | 空库启动后表存在且 `(provider, model_id, session_id, agent_id)` 唯一；重启后规则仍在 | 持久化 |
| AC-27 | 生命周期 | store 与 rule database 的启动/关闭和异常路径可释放；未配置 store 时管理 API 错误明确；`enabled: true` 不得重新成为全量开关；废弃 `max_total_bytes` 不得恢复目录级配额语义 | 启动带 `enabled: true` 且无规则：仍零 capture；配置 `max_total_bytes` 不得让超大目录阻止单文件写入；关闭后文件句柄/线程可结束 | 启动关闭合同 |
| AC-28 | §4 / 修订 v6–v11 | 非流式聚合、cleanup failure、discard/partial 不得用 synthetic response 替代实际 upstream SSE/wire body | 对聚合型上游返回 SSE 再合成 JSON 的路径，capture 中的 upstream response body 等于 SSE wire 而非合成 JSON | wire ≠ 内部合成物 |

矩阵冻结完毕。以下章节在冻结后填写，不得回改上表判据。

## 矩阵冻结后的实现阅读与探针

### reviewed_at_rev

共享工作树 `/home/xp/src/ghc-api-proxy-py`。`.git/HEAD` 指向 `refs/heads/main`，`refs/heads/main` 为 `c0fadf8d4452d03cad42727bd45259132232d41b`。本轮按磁盘当前字节阅读，不假设与该 commit 的 tree 逐字节相同。关键文件 SHA-256 前 16 hex：`raw_capture.py=6fe77becc52b3a82`，`debug_capture.py=c9f5f2af19ae3f2d`，`inference.py=0ea8ea55177a2b12`，`ops.py=4849975329a9b2c5`，`composition.py=d2a5acc8946c7379`，`schema.py=c5762b01a92b09c3`，`chain.py=93b034abf7c1c4bc`，`driver.py=2aab6919e32a49b4`，`spec.md=a33bbc184d0100d1`。规格 ACTIVE v22。coordinator 清单 `/home/xp/src/ghc-api-proxy-py/.dev/docs/raw-capture/reports/260909-coordinator-audit-checklist.md`（2026-09-09 落盘）。未把 `/home/xp/src/ghc-api-proxy-py/.dev/docs/raw-capture/reports/260909-merged-state-review.md`（针对规格 v21 的 pass 结论）当作本轮证据。

### 冻结后因规格漏读而增补的判据

| ID | 规格锚 | 用户可观察判据 | oracle | 预期观察 |
|---|---|---|---|---|
| AC-29 | 修订 v20 | 普通 usage/completion observation 只保留稳定 code、固定 field path 与 exception type，不得把上游可控字段名或异常文本写入 ordinary record | 命中规则的失败请求后读普通完成记录：无上游 error.message、无 raw error object | 普通记录保持安全投影 |

增补原因：反向再读规格修订记录时，v20 句子没有对应矩阵行。本轮未对该条做独立探针。

### 实现阅读（矩阵冻结之后）

匹配入口在 `src/app/server/routes/inference.py` 的 `_routed`：`chain.debug_capture_rules.matches(provider=routed.provider_name, model_id=routed.resolved_model, session_id=session_id, agent_id=agent_id)`。`resolved_model` 来自 `apply_route` ← `decide_route` 的 `descriptor.id`，即解析后实际上送的 model，不是入站别名。`shape_request` 在第一次 upstream attempt 之前调用 `on_routed`。`handle_count_tokens` 在 `shape_request` 之后、`ask_upstream` 之前调用同一个 `_routed`。未命中时不调用 `store.start`。无 `session_id` 时 `_routed` 不匹配。无法解析 JSON / provider/model 的请求在 `_routed` 之前返回。

`build_chain` 无条件构造 `RawCaptureStore` 与 `DebugCaptureRuleStore`。`RawCaptureConfig.enabled` 的类型是 `Literal[False]`。`max_total_bytes` 只在 compat 里删除。CLI 的 `finally` 调用 `chain.aclose()`，进而 `raw_capture.close()` 与 `debug_capture_rules.close()`。`create_pipeline_app` 的 lifespan 不关闭这两个 store。

失败 attempt 的接线：`direct_driver/base.py` 在 except 路径调用 `capture_failed_upstream_attempt` 后无条件 `upstream_attempt_end(..., complete=False)`。`RawRequestCapture.upstream_attempt_end` 在 `complete=False` 时调用 `_note_incomplete`，把整次 request 的完成原因钉成 `upstream_incomplete`。

### 实际执行的命令

1. `PYTHONPATH=/home/xp/src/ghc-api-proxy-py/src:/home/xp/src/ghc-api-proxy-py/tests/int /home/xp/src/ghc-api-proxy-py/.venv/bin/python .probe_raw_capture_adv.py`（隔离 worktree 内探针，import 共享树 `src/` 与 `tests/int/test_pipeline_app.py` 的 `make_client`）。第一轮 14 行：AC-02/03/04/06/08/09/14/25 的正反向对照通过；AC-27 未配置 store 得到未处理 `RuntimeError`；count_tokens 三次 retry 的 request/response body 与 mock wire 逐字节相等，同时日志出现 `reason=upstream_incomplete`。
2. 同解释器第二轮只跑 inference 500→200 retry：`upstream.request.body` 两份等于 wire，HTTP 200，但完成 warning 仍为 `reason=upstream_incomplete`、`response_body_capture_complete=false`、`forensic_replay_complete=false`。
3. `PYTHONPATH=/home/xp/src/ghc-api-proxy-py/src ... pytest tests/unit/observability/test_raw_capture.py tests/unit/observability/test_debug_capture.py tests/unit/config/test_config_schema.py::test_raw_capture_uses_rule_selection_and_has_a_bounded_compression_level` → `19 passed in 2.32s`。这些测试与实现同源，只证明它们自己的断言为绿，不能单独支撑“规格成立”。

探针脚本路径：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-aadf577fcdc1fa133/.probe_raw_capture_adv.py`。临时目录示例：`/tmp/raw-capture-adv-48gv5_r_`、`/tmp/raw-capture-adv-kxcjy22o`。

### 验收矩阵结论

| ID | 结论 | 证据摘要 |
|---|---|---|
| AC-01 | 通过 | 无规则时 `_routed` 不 `start`；有规则但 session 不匹配的 HTTP 探针零文件 |
| AC-02 | 通过 | 入站 `alias`、实际上送 `claude-model`：规则写 `alias` 零文件，规则写 `claude-model` 恰好一份 capture。既有测试未覆盖映射，但实现未漏接 |
| AC-03 | 通过 | `session_id=abc` 对 `abcd`/`ABC` 不命中，精确值命中且 `request_id` 只有一个 |
| AC-04 | 通过 | HTTP 无 agent 落入 `agent-missing-<sha256(b"missing-agent-id")[:24]>`；字面 `missing-agent-id` 落入另一 `agent-<hash>` 文件 |
| AC-05 | 通过 | 代码：`on_routed` 位于 `shape_request`/`handle_count_tokens` 第一次 `provider.count_tokens`/`send` 之前。未经时钟冻结变异 |
| AC-06 | 通过 | 无 session、非法 JSON 均零 `.cborseq.zst`；既有 `test_an_unmatched_refusal_does_not_write_a_legacy_capture` |
| AC-07 | 通过 | `_routed` 补录 `await request.body()` 的 `raw_body`；既有测试用独立 `orjson.loads` 读 capture |
| AC-08 | 偏差 | retry 的每份 upstream request/response body 都在（inference 与 count_tokens 探针均与 wire 相等）。完成诊断却把这次完整取证标成不完整，见 F-01 |
| AC-09 | 偏差 | count_tokens 能命中规则且三次 retry 的 body 齐全；完成 warning 同样误报 `upstream_incomplete`，见 F-01 |
| AC-10 | 通过 | `_path_for` 只用 hash；既有路径注入测试 |
| AC-11 | 通过 | 既有 `test_capture_is_a_stream_of_native_cbor_maps_not_json`；schema_version=2 |
| AC-12 | 通过 | 既有截断尾 frame 测试 |
| AC-13 | 通过 | 既有 4GiB legacy jsonl 不参与配额测试 |
| AC-14 | 通过 | HTTP 探针：普通日志不含 session/agent 原文、body 标记、`secret-token-marker`；路径无原文。capture 文件内 `session_id`/`agent_id` 是规格 §3 公共字段，不是普通日志 |
| AC-15 | 通过 | 既有并发 rollback 测试本轮复跑为绿 |
| AC-16 | 通过 | `_QueuedCaptureFrame` 携带 capture/event_type/reserved_bytes |
| AC-17 | 通过 | 既有 writer OSError / 短写测试本轮复跑为绿 |
| AC-18 | 通过 | 既有 shared-path poison 测试：第二次 `reason=path_poisoned` 且 `writer_error=false` |
| AC-19 | 通过 | 既有新 store 验证损坏文件、完整文件可追加 |
| AC-20 | 通过 | `finish` 先写 `request.end` 再 `_wait_for_writes`；既有 writer_error ack 测试 |
| AC-21 | 通过 | `max_file_bytes=512` 的 HTTP 探针仍 200；capture 失败不改代理结果 |
| AC-22 | 通过 | 既有 `test_incomplete_request_is_reported_even_when_writer_succeeds` |
| AC-23 | 偏差 | 封闭枚举本身与“恰好一次”在单元测试里成立。成功 retry 与 store_closed 两条完成 warning 的完整性布尔不真，见 F-01、F-02 |
| AC-24 | 通过 | 既有配额耗尽只留 `request.start`、日志无 body 标记 |
| AC-25 | 通过 | HTTP：POST 201/200 幂等、空 session 422、DELETE 缺 id 404、额外 `body` 字段 422、管理调用不写 capture 文件 |
| AC-26 | 通过 | 既有 SQLite 重启后仍在、UNIQUE 幂等 |
| AC-27 | 偏差 | `enabled: true` 被 schema 拒绝；`max_total_bytes` 被 compat 丢弃；CLI 关闭路径调用 `aclose`。将 `debug_capture_rules=None` 后管理 API 抛未处理 `RuntimeError`，见 F-03。`pipeline_app` lifespan 不关 store，本轮未把嵌入式宿主做成独立 finding |
| AC-28 | 未验证 | 代码与单元 helper `capture_returned_upstream_response` 优先 `upstream_raw_response_body`。未走 CodeBuddy 真实 HTTP 聚合入口，不能把 helper 绿写成产品路径成立 |
| AC-29 | 未验证 | 未做 usage observation 字段探针 |

## 发现

### F-01 `raw-capture-review-2026-09-09-adversarial-verifier-01`

- severity: major
- acceptance criterion: AC-08、AC-09、AC-23
- primary_location: `src/app/observability/raw_capture.py` `RawRequestCapture.upstream_attempt_end` / `_note_incomplete`；调用方 `src/app/pipeline/direct_driver/base.py` 失败 attempt 的 `upstream_attempt_end(..., complete=False)`，以及 `src/app/pipeline/driver.py` `ask_upstream` 的同类调用
- related_locations: `tests/int/test_pipeline_app.py` `test_rule_selected_count_capture_keeps_each_upstream_retry`、`test_raw_capture_keeps_both_failed_account_switch_attempts`（绿且不断言完成 warning 缺席）
- oracle: 规格 §4 要求重试保留每次实际收发 body；§6 仅在 capture 不完整时发出完成 warning，并给出 `forensic_replay_complete=false`。v17 把 `upstream_incomplete` 绑在 partial response boundary，不是“某次 attempt 业务失败但 body 已完整入档”
- observed result: 规则命中后，mock 上游第一次 500、第二次 200。客户端 200。capture 中 `upstream.request.body` 份数等于 wire，字节相等。仍然恰好一条完成 warning：`reason=upstream_incomplete first_dropped_event=upstream.attempt.end writer_error=false response_body_capture_complete=false forensic_replay_complete=false`。count_tokens 三次 500/500/200 同样如此。既有 retry 测试全绿，因为它们只数 body、不断言“不得误报不完整”
- 建议: 把“attempt 未成功交付”与“该 attempt 的 wire 未完整入档”拆开。`upstream_attempt_end(complete=False)` 在 request/response body 均已写入时不应调用 `_note_incomplete`。`upstream_incomplete` 留给 response/attempt 边界上真正缺字节或 discard/partial 的情况

### F-02 `raw-capture-review-2026-09-09-adversarial-verifier-02`

- severity: minor
- acceptance criterion: AC-23
- primary_location: `src/app/observability/raw_capture.py` `RawRequestCapture.finish`
- related_locations: 同文件 `_missing_event_types` 只在 drop 之后累加
- oracle: §6 完成 warning 必须报告 response body capture 是否完整。完整意为取证能否得到那些 body，不是“启用状态下有没有试图写过这些事件类型”
- observed result: store 已关闭后 `start`+`finish(complete=True)`，文件零增长，完成 warning 为 `reason=store_closed first_dropped_event=request.start`，同时 `response_body_capture_complete=true`。谓词是 `not ({upstream.response.body, client.response.body} ∩ missing) and not incomplete_reason and complete`。从未尝试的事件不进 missing 集合，于是在什么都没落下时仍可报 true
- 建议: 完整性布尔改为“这些事件是否实际 committed”，或在首事件即 drop 时强制 false

### F-03 `raw-capture-review-2026-09-09-adversarial-verifier-03`

- severity: minor
- acceptance criterion: AC-27
- primary_location: `src/app/server/routes/ops.py` `_debug_capture_rules`
- related_locations: `src/app/server/composition.py` 生产路径总是注入 store
- oracle: coordinator 清单第 8 项与规格“管理接口……错误明确”。未配置时应是稳定、可机读的 HTTP 错误，而不是未处理异常
- observed result: 把 `chain.debug_capture_rules` 置 `None` 后，`GET`/`POST /api/debug/capture-rules` 抛 `RuntimeError: debug capture rule store is not configured`，TestClient 看到的是未处理 500 栈，不是 JSON 错误信封
- 建议: 映射为明确 503/500 JSON（固定 type/message），不要依赖框架默认异常页。生产 `build_chain` 虽总是配置 store，嵌入式 Chain 与测试替身仍会走到这条路径

## 整体判定

needs-fix。主路径（规则选择、解析后的 provider/model、未命中零副作用、CBOR/zstd、补录 inbound wire、retry 的实际 body、配额/poison/跨 store、CLI 关闭）已经接到真实 HTTP 入口。完成诊断把“失败后成功的 retry”和“store 在第一帧就关闭”报告成取证不完整或 response body 完整，这是规格 §6 的关键义务，且被既有绿测试漏掉。

## 我最没把握的三个判断

1. F-01 的产品语义。若有人把规格读成“任何 `complete=false` 的 attempt.end 都使整次 capture 不完整”，则本条应改规格而不是改代码。我按 v17 的 partial-boundary 原话和 §4“保留每次实际 body”判定为实现过宽。若该前提为假，F-01 应从 major 降为规格分叉。
2. F-03 是否算产品缺陷。生产 `build_chain` 不会留下 `None`。清单写了“未配置 store 时错误明确”，所以仍登记为 minor。若只验收 CLI 宿主，可驳回。
3. AC-28。CodeBuddy 聚合的 wire 分离只看到 helper 与 `inference.py` 的 `extensions` 读取，没有独立 HTTP 探针。漏接可能仍在 provider 未写入 `upstream_raw_response_body` 的那一层。未验证，不升为缺陷。

## 执行本契约时遇到的摩擦

隔离 worktree 禁止对共享树 `Write`/`git -C`。报告用 Python 写到指定共享 `.dev` 路径。CodeGraph 多次声称源码“Already sent earlier in this conversation”，本会话并没有那些全文，改为绝对路径 `Read`。既有合并态评审针对规格 v21，本轮不采信其 pass。

## 交付声明

delivery_complete: true
completed_at: 2026-09-09T07:46:10Z
finding_total: 3
blocker: 0
major: 1
minor: 2
nit: 0
verdict: needs-fix

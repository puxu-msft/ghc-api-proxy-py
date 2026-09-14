# Raw capture 产品规格

日期：2026-09-08，2026-09-09，2026-09-13 修订
状态：**ACTIVE v25**
权威范围：`observability.raw_capture` 的选择规则、管理接口、文件格式、路径、配额、可读性、安全边界、capture capability 与失败诊断。其他规格可以要求采集哪些 exchange，但不得另行定义落盘格式或把全量 capture 重新接回全局配置开关。

## 1. 用户裁决

用户于 2026-09-08 明确裁决：**raw capture 必须使用二进制结构化文件，绝不能再使用 JSONL。** “把 JSON 编码后加长度前缀”仍是 JSON，不满足本裁决。此前 `.dev/human-controlled-docs-candidates/raw-capture.md` 描述的 Base64-in-JSONL 形态自本版起废止。

## 2. 文件与分组

功能默认关闭。没有命中调试规则时，不创建任何 request capture。命中规则后，同一 `(session_id, agent_id)` 的连续事件追加到：

```text
<directory>/session-<sha256-prefix>/agent-<sha256-prefix>.cborseq.zst
```

`session` prefix 是原始 session ID 的 SHA-256 前 24 个十六进制字符；真实 `agent_id` 的 prefix 是原始 agent ID 的 SHA-256 前 24 个十六进制字符。缺失 agent-id 使用 `agent-missing-<sha256("missing-agent-id")-prefix>` 的独立命名空间，避免与任何真实 agent-id 文件碰撞；文件名和目录名不得出现原始 identity。新实现不得创建或追加 `.jsonl.zst`。旧 `.jsonl.zst` 只作为升级前遗留文件保留，不自动迁移、不参与新格式读取；不存在目录级总量配额，遗留文件不参与任何配额计算。

## 2.1 调试规则与管理接口

需要完整取证的请求由 SQLite 中的持久化调试规则选择，不由配置项把所有请求切换为 capture。规则表的每一行必须包含 `provider`、已解析并实际发送的 `model_id`、入站请求的 `session_id`，并可以包含 `agent_id`。`agent_id` 为空表示匹配该 session 下的任意 agent；非空时必须精确匹配。四个匹配值都按规范化后的非空字符串做精确比较，不使用模糊匹配、正则或前缀匹配。没有 agent header 的命中请求在 capture 中以独立的缺失值保存和分组，不得用可由真实客户端提交的普通字符串作为 sentinel。

规则由 HTTP 管理接口维护：

- `GET /api/debug/capture-rules` 返回当前规则；
- `POST /api/debug/capture-rules` 接受 `{provider, model_id, session_id, agent_id?}`，创建或返回唯一规则；
- `DELETE /api/debug/capture-rules/{id}` 删除指定规则，规则不存在返回 404。

管理接口只管理条件，不接受 body、不直接写 capture 文件。服务默认监听本机地址，因此该接口的默认暴露范围是本机；若部署改变监听范围，必须由部署层负责访问控制。SQLite 数据库路径是独立持久化路径，服务启动时创建表和唯一约束，规则变更在下一次匹配查询中生效，不需要重启。管理能力未完成装配时，接口必须返回稳定的 JSON 服务错误和明确的不可用状态，不得让未处理异常穿透为框架默认错误页。

规则匹配发生在入站 JSON 已读取、路由已经解析出 provider/model-id 之后，并且必须早于第一次 upstream attempt。命中后，代理立刻创建该 request 的完整 capture，并把已经读取的原始入站 body 作为第一份 `request.body` 事件补录；后续 upstream request、upstream response、client response、retry 和错误事件继续写入同一 capture。未命中请求不得因为规则查询而创建 capture 文件或记录原始 body。无法解析 body 或无法解析 provider/model-id 的请求没有可匹配的完整条件，因此不启动规则 capture。

## 3. 二进制结构化流

逻辑流是 **CBOR Sequence（RFC 8742）**，不是 JSON，也不是私有长度前缀 envelope。每条事件是一个完整 CBOR map；body 使用 CBOR byte string 原样承载，不做 Base64。每个 CBOR item 单独压缩成一个完整 zstd frame，再将 frame 追加到文件。

这组边界同时满足：

- CBOR item 自定界，成熟 decoder 可以逐条 decode，不依赖换行或扫描分隔符；
- zstd 原生支持 concatenated frames，单条事件压成独立 frame 后可以只追加，不必重写旧数据；
- reader 将 concatenated zstd frames 解压为 CBOR Sequence 后，可以在数据持续增长时逐条读取完整 item；
- 尾部写入被截断时，截断前的完整 frame/item 仍可恢复；损坏或不完整尾部不得被伪装成完整记录。

生产代码必须提供逐条 reader，返回 map；遇到非 map 顶层 item 视为格式错误。文件 schema 从 JSONL 时代的 `1` 提升为 `2`。每条 map 的公共字段为 `schema_version`、`at`、`request_id`、`session_id`、`agent_id`、`event`；各事件再带自己的字段。

## 4. 捕获内容与安全边界

命中规则的 capture 保存完整 transport evidence：

- 入站/client request headers 与原始 body；
- 每个 upstream attempt 的 request/response headers、body 和边界；
- client response headers 与原始 body；
- retry、cleanup、错误和 capture completeness 事件；
- credentials、Authorization、Cookie 和其他 transport-sensitive fields。

capture 默认仍是 opt-in；没有命中持久化规则的请求不得创建 capture 或记录正文。规则命中后不再提供 body-only profile：每个 capture 都是 full-header/full-transport capture。capture 文件、History cold transport 和显式 transport export 都属于敏感数据面。

普通日志、metrics、LiveObservation 和 request log 仍必须使用 safe projection，不得复制 raw request/response body、认证 header、token、session/agent 原始 transport identity 或未知异常原文。History 的普通 list/detail projection 可以返回由 History contract 拥有的 normalized session/agent metadata，以及 semantic summary、capability 和 reference；不得把 raw transport headers/credentials 复制到该 projection。完整 transport 必须显式请求 transport/evidence projection，并标记 `contains_credentials=true`。

捕获请求的实际 upstream request body 必须在请求真正交给 upstream transport 的边界保留，即使随后发生代理侧 header/attempt timeout，也不得因为代理重新包装异常而丢失这份证据。Replay 不得自动复用 capture headers/credentials；它使用当前配置重新生成认证。

### 4.1 Capture status 与 capability

每个 request capture 和其 History attachment 都必须能表达：

- `capture_status`: `none | pending | complete | incomplete | corrupt`；
- `client_request_available`；
- 每个 upstream attempt 的 request/response/boundary completeness；
- `client_response_available`；
- `wire_diagnostic_eligible`；
- `semantic_replay_eligible`；
- `live_replay_eligible`。

`capture_status=complete` 是总览而不是 replay gate 的唯一条件。请求 body 完整但 response partial 的 capture 可以支持部分 semantic/live source，却不能被当作完整 wire diagnostic。

## 5. 配额与写入

`max_file_bytes` 限制一个 `.cborseq.zst` 文件的实际压缩后字节数；`0` 表示禁用。不存在目录级总量配额：capture 的总量由规则选择与单文件配额约束，不再提供 `max_total_bytes`。配额 reservation 必须包含已经落盘与已排队但尚未落盘的压缩 frame，防止并发超额。

写入使用有界后台队列。一次事件先完成 CBOR 编码和 zstd frame 压缩，再在锁内检查/预留实际 frame 字节并入队，后台 worker 负责创建目录和 append frame。每个队列项必须携带所属 per-request capture、固定 event type 与预留字节成本，不能只携带匿名 `(path, bytes)`。

reservation 表示“已经落盘 + 已入队待确认”的实际压缩字节。writer 完整写入后只把该项确认为 committed，数值不变；writer 在 `mkdir/open/write/close` 任一阶段得到 `OSError` 时，必须在同一 accounting 锁下按实际已写字节回滚未写入部分，不能让不存在的字节继续占用 file quota。短写或 close error 即使已有部分字节落盘，也属于 capture 不完整：已写部分继续计入实际磁盘成本，未写部分回滚，并停止该 capture 后续尚未落盘的 queued frame。

`0 < persisted_bytes < reserved_bytes` 表示共享 append stream 已留下不完整 zstd frame；这不是单个 request capture 的私有失败，而是该 `path` 的 store 级 poisoned 状态。poison 必须在 accounting lock 内与 partial-write 回执同时登记，并在当前 store 生命周期内不可自动清除。poison 后任何已经排队或新到达、指向同一路径的 frame 都不得继续 append；其 reservation 必须完整回滚，所属 capture 必须收到稳定 `path_poisoned` incomplete 原因。不同 path 不受影响，已落盘的 partial bytes 继续按实际文件大小计入 file quota。

内存 poison 不是跨 store/process 的事实来源。每个新 `RawCaptureStore` 在某个 `.cborseq.zst` path **第一次获准 append 之前**，必须用生产 reader 验证该文件从首 frame 到尾 frame 的完整性、每 frame 单一 CBOR item 与顶层 map 合同；不存在或空文件视为可 append。验证与“该 path 已验证/已 poisoned”的状态转换必须受 store accounting lock 串行化，使并发首个 appender 只有一个验证者，且任何 frame 都不能越过验证先入队。验证成功后，该 store 生命周期内依赖自身 writer ack/poison 状态，不重复扫描；验证发生 `OSError`、zstd/CBOR decode error、截断 frame、额外 item 或非 map 时立即把 path 标为 poisoned，不 append、不 reservation，并让当前及后续 capture 稳定报告 `path_poisoned`。验证错误的普通日志不得格式化文件内容、decoder payload 或原始 identity。

per-request capture 必须跟踪 outstanding writer acknowledgements。`finish()` 写入 `request.end` 后必须等待该 request 已接受的队列项全部得到成功、失败或丢弃回执，再决定完成诊断；否则异步 writer 在完成行之后失败会再次静默。达到配额、队列满、store 已关闭、编码/压缩准备失败或 writer 失败时，停止该 request 后续 capture，但不得影响代理请求本身。失败或被丢弃的 upstream attempt 可以以 `complete=false` 写入 attempt 边界；这只描述该 attempt 没有成功交付，不得单独把整次 request 标成 `upstream_incomplete`，因为失败 attempt 的 request/response wire body 仍可能已经完整保存。只有明确的 partial response/body boundary 或 capture drop 才能设置 request-level 的 `upstream_incomplete`。若代理请求本身以 `complete=false` 结束，即使 writer 没有报错，capture 也必须以固定的 `request_incomplete` 原因报告取证不完整。响应 body 完整性必须依据相关 response-body 事件已经成功 committed 的事实判断；在第一条事件就关闭、配额耗尽或写入失败而没有任何 response-body evidence 时，必须报告 `response_body_capture_complete=false`，不能把“尚未尝试写 response body”当成完整。count_tokens 等 buffered response 只有在 response cleanup 也成功后，才能提交完整的 response boundary。

## 6. 完成诊断

per-request capture 必须保留首次丢失原因、首个丢失事件类型和后续被跳过的固定事件类型。请求完成时若 capture 不完整，普通 warning 必须恰好发出一次，并至少关联 request ID、固定原因、首个丢失事件、response body capture 是否完整，以及 `forensic_replay_complete=false`。

writer `OSError` 的稳定原因枚举是 `writer_error`。worker 的即时 warning 与请求完成 warning 都只能带 request ID、固定 event type、固定 reason、errno/exception type 等安全元数据；不得带 frame、body、header、token、session/agent 原始 identity 或异常中可能回显的原始 payload。即使 writer 在 `append()` 已返回成功后失败，请求完成 warning 也必须报告 `reason=writer_error`；若更早已有 quota 等首因而 `reason` 保留首因，则必须另有稳定 `writer_error=true` 标记，且后续 queued frame 仍按 writer failure 停止。

同一路径在先前 request 的 partial write 后，后续 request 的稳定首因枚举是 `path_poisoned`；其 `writer_error` 布尔值只表示该 request 自己是否收到 writer error，不得把前一个 request 的错误冒充成本 request 的 writer error。完成 warning 必须关联后续 request ID 并给出 `forensic_replay_complete=false`。普通日志仍不得包含 path 对应的原始 session/agent identity 或任何 body/credential。

已知的单文件配额耗尽案例中，如果文件只留下 `request.start`，完成 warning 必须明确给出 `reason=file_quota_exceeded`，且当 upstream/client response body 已尝试但未保存时给出 `response_body_capture_complete=false`。诊断不得尝试写回已满的 capture 文件，也不得把 body 降级写入普通日志。

完成诊断 `reason` 的合法全集是封闭枚举：`file_quota_exceeded`、`writer_queue_full`、`store_closed`、`capture_error`、`writer_error`、`path_poisoned`、`request_incomplete`、`upstream_incomplete`。本段与前文按场景讨论的枚举是同一全集的子集；实现新增任何原因都必须先修订本节。

## 7. 修订记录

| 日期 | 版本 | 变化 | 触发 |
|---|---|---|---|
| 2026-09-14 | v25 | 澄清 History-owned identity metadata 与 raw transport identity 的边界；普通 History projection 可保留 History contract 的 identity 字段，但不得复制 capture headers/credentials | 多轮文档 review 发现 raw-capture 与 History identity wording 可产生两种安全解释 |
| 2026-09-13 | v24 | 明确 full transport capture：命中规则的 capture 保存完整 headers/credentials；普通日志与 History 默认 projection 仍 safe；新增 capture status/capability matrix；History 通过 capture reference 关联 full transport；replay 使用当前认证而不复用 source headers | 可观测性、History、debug、replay 重构 shared understanding |
| 2026-09-09 | v23 | 明确失败 attempt 的业务结果不等于 request-level 取证不完整；response-body completeness 以已 committed evidence 判断；buffered count response 要等 cleanup 成功；管理 API 未装配和未知异常日志都必须使用稳定安全投影；代理侧 timeout 不得丢失已交给 upstream transport 的 request body | 动态 capture 独立验收 F-01 至 F-05 与普通日志回归 |
| 2026-09-09 | v22 | §6 固定完成诊断 `reason` 的封闭枚举（补 `store_closed`/`writer_queue_full`/`capture_error`/`upstream_incomplete`） | 合并态评审 M-1：派生枚举与代码漂移 |
| 2026-09-09 | v21 | 移除全局（目录级）配额 `max_total_bytes`；capture 的总量由规则选择与 per-file 配额约束；遗留 `.jsonl.zst` 不再计入任何配额 | 用户裁决：不再提供全局配额 |
| 2026-09-09 | v20 | usage observation issues 只保留稳定 code、固定 field path 与 exception type，不把上游可控字段名或异常文本写入 ordinary record | 最终验收 DYN-CAP-27 |
| 2026-09-09 | v19 | prepared direct discard 与 partial/zero-body response 都写 incomplete response boundary；one-shot local provenance、ResponseObservation issue 脱敏、Xingchen cleanup carrier、shared unobserved-body status 语义接线 | 最终验收 DYN-CAP-22 至 DYN-CAP-26 |
| 2026-09-09 | v18 | generic cleanup/partial error carriers、one-shot provenance、safe ordinary projection、CodeBuddy raw aggregate separation、COUNT buffered attempts 与 provider-specific response evidence 全部接线并完成回归 | 最终动态 capture 收尾验收 |
| 2026-09-09 | v17 | direct discard 写 `response.end(false)`；partial boundary 参与 completion warning；COUNT 记录 buffered attempt projection；active module doc 删除 retired rejection persistence 事实 | 最终验收 DYN-CAP-17、DYN-CAP-18、DYN-CAP-20、DYN-CAP-21 |
| 2026-09-09 | v16 | one-shot upstream provenance 与 proxy-owned deadline 分离；generic proxy detail 保留自身消息但 upstream 投影使用安全 helper；CodeBuddy cleanup carrier、pre-pull boundary、partial completeness 和最终安全回归同步 | 最终验收 DYN-CAP-15、DYN-CAP-16、DYN-CAP-17、DYN-CAP-18 |
| 2026-09-09 | v15 | generic provider cleanup failure 建立 capture-able upstream error；proxy-owned deadline 与 upstream failure 分开投影；同步 pre-first-pull accounting fixture | 最终验收 DYN-CAP-12、DYN-CAP-13、DYN-CAP-14 |
| 2026-09-09 | v14 | 同步安全投影回归断言；为首次 body pull 前的 response close 增加幂等 `response.end(false)`/`attempt.end(false)` 边界 | 最终验收 DYN-CAP-09、DYN-CAP-10 |
| 2026-09-09 | v13 | 未归一化 upstream exception 的普通投影改为固定类型/状态元数据；count response cleanup failure 不得提交完整 attempt；partial response 必须写 `response.end(complete=false)` | 最终验收 DYN-CAP-03、DYN-CAP-04、DYN-CAP-05 |
| 2026-09-08 | v12 | 普通 detail、FailureSummary、InterruptionObservation 和 hand-over completion 统一使用安全 upstream 状态投影；OpenAI-compatible partial status-body read 保留 status/partial response bytes；CodeBuddy aggregate 的真实 SSE body 与 synthetic response 分离并进入 capture | 最终验收 DYN-CAP-01、DYN-CAP-02、RC-009、RC-010 |
| 2026-09-08 | v11 | CodeBuddy non-stream aggregation 必须保留实际 upstream SSE body；聚合 synthetic response 不得替代 wire capture；aggregate cleanup failure 也必须归一化并保留 request/partial response evidence | 最终验收 RC-009、RC-010 |
| 2026-09-08 | v10 | provider response body `aread()` 与 cleanup 阶段的 timeout/transport error 也必须归一化并保留 request bytes；CodeBuddy 聚合和 OpenAI-compatible 非 200 response 共用该规则 | 最终验收发现 RC-008 扩展路径 |
| 2026-09-08 | v9 | CodeBuddy 非流式聚合 body 阶段的 timeout/transport failure 也必须归一化并保留 request-attached bytes | 最终验收 RC-008 |
| 2026-09-08 | v8 | 429 与 request-attached transport failure 也必须把已发送 upstream request body 传入失败 attempt capture | 最终验收 RC-005 |
| 2026-09-08 | v7 | 未命中规则不再走 legacy JSON rejection capture；timeout 从 request-attached error 传递已发送 body；普通 completion/response observation 只保留安全错误元数据，不复制 upstream error message 或 raw error object | 最终动态捕获验收发现条件选择与普通日志安全边界缺口 |
| 2026-09-08 | v6 | 补充缺失 agent-id 的不可碰撞分组、`request_incomplete` 完成原因，以及失败/丢弃 attempt 和 count_tokens retry 的全量 wire 证据要求 | 动态捕获独立审查发现不完整请求与计数重试证据缺口 |
| 2026-09-08 | v5 | 将全量 capture 的开关从配置项改为 SQLite 持久化调试规则；新增 HTTP CRUD 管理接口、provider/model/session/可选 agent 精确匹配，以及路由后补录已读取入站 body 的命中时机 | 用户要求通过 HTTP API 和 SQLite 按条件开启指定请求的全量记录 |
| 2026-09-08 | v4 | 增加跨 store/process poison 恢复：每个 path 在新 store 第一次 append 前用生产 reader 完整验证；损坏文件不增长，当前与后续 capture 报告 `path_poisoned` | closeout 复审 major `RC-1` 与用户修复要求 |
| 2026-09-08 | v3 | 增加 shared-path poisoning 合同：partial zstd frame 将 path 标为 poisoned；禁止同路径后续 queued/new frame 追加，完整回滚其 reservation，并让受影响 capture 稳定报告 `path_poisoned` | 最终复审 major finding `partial-write-poisons-shared-stream` 与用户闭合要求 |
| 2026-09-08 | v2 | 增加 writer acknowledgement 合同：队列项关联 capture/event，失败在锁内回滚未写 reservation，per-request finish 等待 ack，`OSError` 稳定报告 `writer_error`，普通 warning 继续禁止 raw payload/credential | 独立审查 major finding `capture-writer-ack` 与用户修复要求 |
| 2026-09-08 | v1 | 建立 raw capture 独立权威规格；废止 Base64-in-JSONL，裁定 RFC 8742 CBOR Sequence + per-item zstd frame、`.cborseq.zst` 路径、压缩后字节配额、逐条 reader 与安全完成诊断 | 用户明确产品裁决 |

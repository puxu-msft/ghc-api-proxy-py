# History 行为规格

日期：2026-09-13

状态：**ACTIVE v2**。这是 HistoryEntry、HistoryArchiveStore、查询面、durability、archive、pin 和 retention 的行为权威。当前实现边界见 [`status.md`](status.md)，长期候选见 [`deferred.md`](deferred.md)；`src/.archived/` 下的旧 History 不构成当前实现。

## 1. History 的边界

History 是跨重启可查询的 request projection，不是 raw capture event stream，也不是 request-local journal。

- 一条 client request 对应一条 `HistoryEntry`；
- upstream retry/hedge/hand-over 作为有序 attempt summary 进入同一 entry；
- `RequestJournal` 只作为生成 projection 的 request-local source；
- `CaptureAttachment` 是可选的独立 raw wire evidence，通过 `capture_ref` 关联；
- replay 必须满足 capture eligibility，History semantic payload 不能单独成为 replay source。

History 不是实时请求列表。实时 view 由 [`../observability/spec.md`](../observability/spec.md) 定义，使用独立的 `/api/observability/requests` 查询面。

History-owned session/agent metadata 是 queryable request identity，不是 raw transport header、credential 或 capture body。Raw transport 的敏感边界仍由 [`../raw-capture/spec.md`](../raw-capture/spec.md) 定义；普通 History projection 不复制这些 transport fields。

## 2. HistoryEntry projection

每个 entry 的稳定 projection 至少包含：

| 类别 | 内容 |
|---|---|
| identity/time | `request_id`、History-owned session/agent metadata、started/finished timestamps |
| route | inbound format、requested/resolved model、provider、target policy、client/upstream protocol |
| outcome | `outcome`、`delivery`、HTTP status、terminal facts、failure classification |
| attempts | ordered attempt summary、attempt count、retry count、replaced failures、timing、body byte counts |
| semantic | client request、client-visible response、usage、losses/facts |
| capture | `capture_ref`、`capture_status`、capability flags、capture durability |
| provenance | original request、replay_of、source entry/capture reference |
| durability | `pending`、`durable`、`persistence_failed` |

History 不持久化完整 RequestJournal event stream。若未来需要跨重启事件审计，必须建立独立的 HistoryEventArchive 设计，而不是把 journal 隐式塞进当前 entry schema。

## 3. Full transport coverage

只有命中 capture 规则的 entry 才有 full transport。未命中请求仍可有完整 semantic History，但：

```text
capture_ref = none
capture_status = none
semantic_replay_eligible = false
wire_diagnostic_eligible = false
live_replay_eligible = false
```

Captured entry 的 full transport envelope 可以包含：

- inbound/client request headers 与 body；
- 每个 upstream attempt 的 request/response headers、body 和边界；
- client response headers 与 body；
- credentials、Authorization、Cookie 和其他 transport-sensitive fields；
- capture schema、digest、completeness 与 writer diagnostics。

这使 captured History 和 raw capture 都属于敏感数据面。普通 request log、metrics 和安全 observation 不得复制这些字段。

对 History transport 读取，主程序提供最小的独立管理边界，而不是把 localhost 默认值误作访问控制：operator 必须配置 `server.history_export_token`（至少 16 个字符），调用方必须在 `X-History-Export-Token` header 中提供相同值。token 缺失、错误或服务未配置 token 时，credential-bearing transport/full export 必须在读取或确认 entry 存在之前以稳定的 `403 access_denied` 拒绝，且错误不得回显 token、capture 或 credential。该 token 是 secret；`/api/config` 的配置展示必须保持脱敏。外部监听时，operator 仍负责 TLS、网络隔离和该管理 secret 的轮换；bind host 从来不是这条授权合同的一部分。

## 4. Capture capability

History 保存 capture 总览和能力矩阵：

- `capture_status`: `none | pending | complete | incomplete | corrupt`；
- `client_request_available`；
- `upstream_attempts[]`，每个 attempt 独立记录 `attempt_started`、request/response start、headers/body presence、response/attempt end completeness 与由该 matrix 导出的 `wire_diagnostic_eligible`；
- `client_response_available`；
- `wire_diagnostic_eligible`；
- `semantic_replay_eligible`；
- `live_replay_eligible`。

History handoff 在 RawCapture `finish()` 已等待全部 writer acknowledgements 后直接复制 immutable observation；History async writer 只持久化/读取该 safe matrix。字段缺失的既有 index row 必须投影为 false，且不得从 `UpstreamBodyAttempt`、timing 或 raw response 的存在猜测 true。`capture_status=complete` 不能替代能力矩阵。`none` 与 `corrupt` 是所有 replay mode 的状态否决；`pending`/`incomplete` 不得单独否决 semantic/live，后两种 mode 必须按完整 client request 与各自 capability 判断。请求 body 完整但响应不完整的 capture 可以支持某些 semantic/live source，却不能伪装成完整 wire diagnostic；wire 必须同时命中所选 attempt 的 `wire_diagnostic_eligible`。

Capture writer 的 receipt 与 History writer 的 receipt 独立。History row 可以已经 durable，而 capture 仍为 pending/incomplete；capture complete 也不能反向修改 RequestFacts。

## 5. Storage

### 5.1 Hot index

Hot SQLite 只保存可筛选的 metadata、summary、capability flags、durability、archive state 和 cold reference：

- segment id；
- byte offset/length；
- schema version；
- digest；
- entry/request identity；
- capture/reference state。

大 semantic payload 和 full transport 不作为默认 hot BLOB。

### 5.2 HistoryArchiveStore

`HistoryArchiveStore` 独占 History cold segment 的 writer/index。它不复用 `RawCaptureStore` 的逻辑文件或 schema，但可以共享底层 block compression primitive。

冷存储按 normalized session/agent 分组，使用版本化 History envelope。每个 segment：

- 保存有序 entry payload/object；
- 使用 block-level zstd frames；
- 由 hot index 记录 segment、offset、length、digest；
- 约 1 GiB rollover；
- 尾部 block 损坏不得使此前已校验的 block 伪装成可读；
- semantic payload 对所有 entry 可存在，full transport 仅对 captured entry 存在。

### 5.3 Durability

History projection 的生命周期为：

```text
projection_created
  -> accepted
  -> durable
  -> persistence_failed
```

`accepted` 不等于 `durable`。transient writer failure 可以按 writer policy 重试；最终失败必须发布稳定 failure code，不能静默丢失 projection。

## 6. Query API

主程序第一版提供：

```text
GET  /history/api/entries
GET  /history/api/entries/{id}
POST /history/api/entries/{id}/archive
POST /history/api/entries/{id}/pin
POST /history/api/entries/{id}/unpin
```

查询规则：

- list 默认只返回非 archived entries；
- detail 默认返回 metadata、semantic summary、capture capability 和 references；
- `include=semantic` 才加载 semantic payload；
- `include=transport` 才读取 cold full transport，且必须满足 `server.history_export_token` 与 `X-History-Export-Token` 的独立管理访问合同；
- `export` 必须显式选择 `semantic`、`transport` 或 `full`；
- `export=transport` 与 `export=full` 必须满足同一独立管理访问合同；`export=semantic`、list、detail 和 `include=semantic` 不要求该 header，继续是 credential-free 的普通 History projection；
- transport/full projection 明确标记 `contains_credentials=true`；
- replay result 不自动内嵌 source transport，只返回 provenance/reference；
- captured History 的完整 transport 读取不等于普通 request log 读取。

主程序不提供 replay API。Replay source、缺证据错误和独立 process 由 [`../replay/spec.md`](../replay/spec.md) 定义。

## 7. Archive、pin 与 retention

Archive 是单向 public lifecycle action：

- 只有 archive，没有 restore；
- archive 成功后 entry 从 public list/detail/export/replay source 下线；
- internal cold artifact 与 tombstone 可以保留；
- pinned entry archive 返回 `409 entry_pinned`；
- archive failed entry 仍 public 可见，返回稳定 failure code 并允许重试；
- public API 不提供 physical delete 或 purge；
- retention/运维层可以在受控流程中 purge cold artifact，purge 后只保留不可逆 deletion receipt/tombstone；
- pin 只阻止自动 retention/reaper，不自动 archive。

Archive 使用异步 receipt：

```text
active -> archiving -> archived
                  \-> archive_failed
```

只有 cold copy、digest、reference 和 hot transition 全部确认后才进入 `archived`。客户端不等待大对象 copy 完成。

## 8. Revision record

| 日期 | 版本 | 变化 | 触发 |
|---|---|---|---|
| 2026-09-16 | v4 | 明确 History attachment/index 仅复制 writer-confirmed RawCapture per-attempt matrix；缺失历史字段 fail-closed，禁止 response-timing 推断 | replay review RCR-04 |
| 2026-09-15 | v3 | 为 credential-bearing History transport/full export 新增 fail-closed 的 `server.history_export_token` + `X-History-Export-Token` 管理访问合同，明确 semantic/index projection 不受此 gate 限制，listener locality 不能替代授权 | 发现 host 可配置为外部地址，而 route 未单独保护 raw transport |
| 2026-09-14 | v2 | 明确 History-owned identity metadata 与 raw transport identity/credentials 的边界，并把实现限制与长期 hardening 移到 status/deferred | 多轮文档 review 与当前实现对账 |
| 2026-09-13 | v1 | 建立一 client request 一 entry、semantic projection、captured full transport、HistoryArchiveStore、capture capability、单向 archive、pin/retention 和独立 durability receipt 合同 | 可观测性、History、debug 重构 grill 达成 shared understanding |

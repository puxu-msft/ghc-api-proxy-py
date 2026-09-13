# 可观测性行为规格

日期：2026-09-13

状态：**ACTIVE v1**。这是可观测性事实、实时投影、日志和指标的行为权威；当前生产实现只覆盖其中一部分，未实现部分不得被描述为已接线。

## 1. 范围与术语

本规格定义一次 client request 如何产生 typed facts，以及这些事实如何投影为：

- `LiveObservation`：进程内 active/recent 只读视图；
- request log：面向终端和日志收集器的文本流；
- metrics：固定 cardinality 的进程指标；
- `HistoryEntry`：交给 History consumer 的 durable projection；
- `CaptureAttachment` reference：指向受规则选择的 raw wire evidence。

本规格不定义 History 的 cold storage、archive lifecycle 或 query schema；这些由 [`../history/spec.md`](../history/spec.md) 定义。raw capture 的文件、配额、writer 和 capture completeness 由 [`../raw-capture/spec.md`](../raw-capture/spec.md) 定义。Replay 是独立进程，由 [`../replay/spec.md`](../replay/spec.md) 定义。

## 2. RequestJournal 与 RequestFacts

`RequestJournal` 是一次请求生命周期内按发生顺序追加的 typed facts。它不是第二个 state machine，不允许 observer 回写 request owner 的状态，也不保存 raw wire。

事件类别至少包括：

- `request.received`、`request.approved`、`route.selected`；
- `attempt.started`、`transport.opened`、`conversion.warning`、`attempt.failed`、`attempt.completed`；
- `block.assembled`、`block.commit_started`、`block.committed`；
- `upstream.terminal`、`delivery.partial`、`delivery.uncertain`、`client.aborted`；
- `request.completed`、`request.failed`、`history.projection_accepted`、`history.projection_rejected`、`request.finalized`。

每个 attempt event 必须带 attempt identity。block event 记录 semantic identity 与 commit outcome，不复制正文。`RequestJournal` 在 `request.finalized` 发布后冻结，随后不得再追加 request-local facts。

`RequestFacts` 是冻结后的 typed terminal facts。它至少包含：

- request identity、时间和来源；
- requested/resolved model、provider、route 与 client/upstream wire format；
- attempt summary、retry/replaced failures 和关键 timing；
- terminal facts、delivery verdict 和 failure classification；
- normalized usage、conversion losses/facts；
- client semantic request/response 的 History projection；
- capture reference、capture completeness 与 replay capability。

`RequestFacts` 是 History、日志和 metrics 的事实来源。任何 projection 都不得重新解析 raw Responses events 来猜测 route、usage、commit 或 failure state。

## 3. 终局模型

终局使用两个正交维度：

### 3.1 outcome

封闭集合：

- `completed`：client delivery 满足成功合同；
- `failed`：服务、上游、转换或交付失败；
- `aborted`：客户端或下游主动离开，责任不归因于正常成功；
- `interrupted`：进程生命周期中断后由恢复/运维层归类。

`retry` 不是 outcome；它是发生过 replacement attempt 的展示标签。`gone` 不作为 canonical fact，统一投影为 `aborted`。

### 3.2 delivery

封闭集合：

- `none`：没有可证明的客户端交付；
- `complete`：客户端交付完成；
- `partial`：已经交付部分内容，但终局不完整；
- `uncertain`：发送结果无法证明。

`partial` 和 `uncertain` 不得被投影成成功。`outcome` 与 `delivery` 必须同时保留，避免把客户端断开、上游截断和 sink uncertainty 压成一个布尔值。

## 4. Projection 合同

### 4.1 LiveObservation

实时观察只在进程内存在。它可以展示 active request、最近完成 request、draining、connections、capture pending/failure 和 History persistence failure，但不承诺跨重启。

主程序的实时查询面为：

```text
GET /api/observability/requests
```

它与 History 查询面分离。两者使用同一个 `request_id` 关联，但不在服务端把 ephemeral row 与 durable row 合并成一个 History entry。

### 4.2 Request log

request log 是文本输出流，不是事实源，不是 History store。它可以显示 outcome、delivery、route、model、timing、usage、attempt summary 和安全错误分类，但不得输出 raw body、credentials、headers、原始 session/agent identity 或异常原文。

JSONL 完成记录不再作为第二个 durable truth。迁移期间如果保留兼容 writer，它只能是 History projection 的临时 shadow/export，不得拥有独立语义。

### 4.3 Metrics

第一版只承诺固定 cardinality：

- request total、outcome、delivery；
- upstream attempt、retry；
- duration、time-to-first-byte、stream gap；
- History projection accepted/durable/persistence_failed；
- capture selected/complete/incomplete/drop；
- replay started/succeeded/failed/cancelled/source_unavailable。

label 只可来自固定集合或受配置集合约束的 provider/wire format。不得使用 request_id、session_id、agent_id、prompt、任意客户端 model input 或异常文本作为 label。

### 4.4 History handoff

Driver 在 request-owned buffer cleanup 前生成自包含 immutable History projection，并恰好一次提交给 History consumer。`projection accepted` 不等于 `History durable`；History writer 必须独立发布 durable 或 persistence_failed receipt。

History sink、日志 sink、metrics sink、TUI sink 或 capture sink 失败，都不得改变已经确定的 request action。sink 失败必须通过安全的 observation/metric/receipt 面可见。

## 5. Sink failure 与生命周期

- request owner 只负责事实收集、终局判定和 projection handoff；
- History writer 负责 History durability，不回写已冻结的 RequestFacts；
- capture writer 负责 CaptureAttachment durability，不伪造 History durable；
- observer failure 不替换 primary request failure，也不把 queue accepted 伪装成 durable；
- `request.finalized` 对每个 request 恰好一次，并且是 RequestJournal 的最后一个 request-local fact。

## 6. 当前实现边界

当前实现已有 `RequestTrace`、`FinalizedRequest`、`ActiveRequestRegistry`、request log、metrics 和 rule-selected raw capture，但这些对象仍存在重复投影和部分同步写入。它们不是本规格已经实现的证明；后续实现必须先收敛事实 owner，再逐个接入 projection。

## 7. 修订记录

| 日期 | 版本 | 变化 | 触发 |
|---|---|---|---|
| 2026-09-13 | v1 | 建立 RequestJournal/RequestFacts、LiveObservation、request log、metrics 与 sink isolation 的独立行为权威；明确四类产品面和 outcome/delivery 正交模型 | 可观测性、History、debug 重构 grill 达成 shared understanding |

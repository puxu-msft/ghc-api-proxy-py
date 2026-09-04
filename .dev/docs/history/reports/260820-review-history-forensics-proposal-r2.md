# 《取证记录能力方案（history 增强）》r2 聚焦复评

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/agents/history-forensics/proposal.md` r2。

基线：当前工作树，`HEAD eb932156d30294c9c809a70ea5a4649d85304eae`。本轮只核 r1 原 12 条的处置，以及全文重写新增的事实错误/矛盾；没有重复全量核验。针对并行改动，重新读取了当前 `pipeline_app.py`、`request_log.py`、`assembler.py`、`sse_source.py`，并重测 import closure 与配置消费者。

结论：**needs-fix，r2 目前还不宜交用户裁决。** 原 12 条中 11 条已解决、1 条部分解决；未发现原 blocker 原样残留，但重写新增 5 个 major、3 个 minor。主要问题不是原架构方向退回去了，而是 L2 采集面的现状仍说得过于便宜、local forensic headers 与 export allowlist 自相矛盾、分片顺序会先默认开启无容量上限的持久化、日志 sink 粗估漏掉必要保留策略，以及第六节直接违反项目的 Spec 前置纪律。

证据强度：当前源码与方案文本直接对账，足以据以修订文档。工作量判断只指出方案自身遗漏造成的明显低估，不把任意“片”换算成工时。

## 一、原报告 12 条逐项处置

| 原发现 | 状态 | r2 处置核对 |
|---|---|---|
| B1 旧链路调用者错误全称 | **已解决** | `proposal.md:39-47` 改为“例如”并补出 smoke/unit 调用者；生产入口结论未扩大。 |
| B2 `_log_completion` 非 exactly-once | **已解决** | `proposal.md:69-78` 明确只有两个调用点，区分流式幂等收尾与非流式异常洞；与当前 `src/app/server/pipeline_app.py:157-166,320-338,365-372,386-402` 一致。 |
| B3 全仓唯一解析／`SseEvent` 保 chunk | **已解决** | `proposal.md:91-101` 改记 `_counted_upstream` 的 raw parser-input chunks，并把“唯一解析”限定为生产闭包。 |
| B4 低估 `HistoryEntry` 不匹配 | **已解决** | `proposal.md:80-89` 准确列出字段、monotonic 时间、positional SQL、sync/async 四类不匹配；`3.1` 改为新 DTO、新表。 |
| B5 L2+L3 不足以导出 cassette | **已解决** | `proposal.md:127-135` 列出 method/path、extensions、真实 chunks、attempt 四项；`proposal.md:175-201` 的三层模型补入 attempt 维度、上游 method/path/extensions 与 raw chunks。新增的 headers 矛盾另见 N2。 |
| B6 压缩口径错误 | **已解决** | `proposal.md:116-125` 不再把整请求压缩数字套给逐帧 schema，改为 attempt 级 blob + chunk 长度/offset。 |
| M1 失败何时可知、crash/hang/retry | **部分解决** | `proposal.md:203-215` 已改为 provisional → per-attempt → chunks → terminal 的“先写后分类”，并在 `3.1` 加 attempt；但 exchange 级单 zstd blob（`:188-189`）如何与 crash 前可恢复的“增量追加或 spool”（`:209-215`）闭合没有说明，且“未终结记录说明进程在那一刻死了”是过强因果，详见 R1。 |
| M2 reaper 留孤儿 | **已解决** | `proposal.md:217-221` 明确要求同一 writer transaction 显式删子表，或启用 FK cascade。 |
| M3 内部 events 不能代替完成点 | **已解决** | `proposal.md:195-201` 把 finalizer、attempt events/transport tap、raw chunk tap 分工，不再把 `request.succeeded` 当完成点。 |
| M4 漏 raw-vs-frame、durable-vs-best-effort 两个真分叉 | **已解决** | `proposal.md:253-270` 新增分叉 B、C。 |
| M5 L3 可推出 L4 的理由过强 | **已解决** | `proposal.md:314-318` 已收窄为固定代码/配置下重放预期转换，不冒充实际交付。 |
| m1 可变数据库计数无时间锚 | **已解决** | `proposal.md:49` 同时给 09:00 与 09:13:36 快照，不再写成永久常量。 |

## 二、残留问题

### R1 — major — “先写后分类”尚未闭合持久化形态，且把未终结错误归因为进程死亡

证据：`proposal.md:188-189` 决定一个 attempt 的 chunks 合成单个 zstd blob，chunk 表只留 metadata；`:209-215` 又要求 chunk 到达时增量追加或进有界 spool，以保住 crash/hang 取证。若 spool 只在内存，crash 后 L3 仍全丢；若 spool 落盘，它就是 schema/lifecycle 的一部分，必须说明未封口 spool 如何被查询、恢复、压缩并原子替换。当前文字没有把这两种状态接起来。

`proposal.md:215` 的“未终结记录本身说明进程在那一刻死了”也不成立。它只证明“没有持久化 terminal transition”；仍在运行的挂起请求、被强制取消但 finalizer 未落盘、writer 失败、进程 crash 都能产生同一状态，且记录本身没有“那一刻”的死亡时间。

修订建议：写成“未终结记录是异常中断或仍在运行/挂起的证据，需结合进程 generation/启动时间裁决”；明确选 disk-backed append log/独立 chunk rows，或承认 L3 best-effort 在 crash 时可丢。若最终压成单 blob，定义 provisional spool 的持久化与恢复转换。

## 三、r2 新引入的问题

### N1 — major — 1.3 仍错误声称 L2 每 attempt 所需数据已在现有采集点手里、无需新接缝

证据：`proposal.md:57-67` 把 L2 采集点写成 `_dispatch` 设置 `trace.bytes_in` 处，并称“已持有 `response.request.content`”“三处都不需要新建管线接缝”。当前 `src/app/server/pipeline_app.py:245-256` 只在 driver 返回**最终 response** 后看到该 request；前序 retry、发送即抛错的 attempt、错误 response body 都到不了这里。

现有 attempt 事件也不握完整 wire 事实：`src/app/pipeline/request.py:38-47` 的 `Attempt` 只有 endpoint/payload/status_code/error；`src/app/pipeline/direct_driver/base.py:123-170,191-213` 的 subscribers 收到 `RequestContext`，没有实际 `httpx.Request.method/url/headers/content`、response extensions 或 error body。`proposal.md:200` 自己写“attempt 事件 / transport tap”，其中 transport tap 正是需要新增的采集接缝，和 1.3 的“无需新建”矛盾。

修订建议：把 1.3 收窄为“L1 与最终成功 stream 的 L3 已有自然包裹点；完整 per-attempt L2 需要扩展 driver/transport observation contract”。这也应计入 A1/A2 的粗估。

### N2 — major — 取证库的 headers 被误套 cassette allowlist，与“不在本地脱敏”及取证目标矛盾

证据：`proposal.md:188` 把 `UpstreamExchange.headers` 定为 allowlist；`proposal.md:225-233` 又明确“取证库本身不脱敏，只有 export-cassette 才走响应头 allowlist”。二者不能同时成立。

三项 cassette allowlist 的目的只是在将固件写进版本库时裁剪；本地取证若只存三项，会永久丢掉 upstream request id、rate-limit headers 等本来可用于关联事故的事实。r2 的共享 codec 设计已经允许在 export terminal 再裁剪，没有理由上游采集时先丢。

修订建议：L2 保存完整 upstream response headers；`export-cassette` 才投影到 `KEPT_RESPONSE_HEADERS`。若某些 header 确实不应存，需按用户威胁模型另行裁决，不能借 cassette 合同倒推本地取证合同。

### N3 — major — 分片 2 默认开启持久化，但容量控制被推迟到分片 6

证据：`proposal.md:336-344` 在分片 2 就落 L1，L2/L3 随后继续写，直到分片 6 才交付双维度 reaper、配置与档位；`proposal.md:306-310` 又指出 `history.enabled` 当前默认 true，接上即默认记录。按项目“每个自足补丁立即集成”的流程，分片 2～5 的集成态会形成默认开启且无容量上限的数据库，分片 1 的日志文件同样没有任何 retention 说明。

修订建议：最小容量边界与 `history.enabled` 接线必须和首次持久化同片，或首次落地保持默认不启用，直到分片 6 一起切换；不能靠“后续很快会做”维持自足性。日志 sink 也要同时决定外部 journald/logrotate 承担 retention，还是使用 bounded rotating handler。

### N4 — major — 6.3 对 Spec 的判断与项目硬流程及本节自己的前句冲突

证据：`proposal.md:360-364` 先承认“新增磁盘写入”属于可观察行为，下一句却判定分片 1 日志文件 sink 不需要 Spec。项目规则明确要求 observable behavior 变更在实现前有完整 Spec；把它称为“日志配置”不会改变它新增文件、路径、格式、保留和失败行为的事实。

修订建议：分片 0 的测试隔离修复可不另立行为 Spec；分片 1 至少应在既有 Spec 中冻结文件 sink 的启用默认、路径、格式、retention、写失败行为，再实施。无需建新证明体系，只需满足已有 Spec 前置纪律。

### N5 — major — E1 的 0.5 片粗估没有覆盖一个可长期使用的 file sink 合同

证据：`proposal.md:284-293` 只依据“全项目一个 StreamHandler”把 E1 估为 0.5 片；当前 `src/app/observability/logging.py:116-175` 确实只有一个 console handler，但新增 file handler 仍必须决定路径、父目录创建、text/JSON 格式、与 console 的 color 差异、rotation/retention、写失败是否影响服务，以及 shutdown flush/close。`proposal.md:286` 的“加一个 file handler”没有覆盖这些行为，N3 已展示不做 retention 的具体失效。

粗估复核：A1/A2/A3 与第六节的 L1/L2/L3/config 分片数量大体能对上；D1、F1 没有可由现代码机械推翻的明显数量错误。**唯一明显失真的是 E1**：0.5 片只够接一个无完整运行合同的 handler，不够交付本文声称“立刻可用”的长期 sink。

修订建议：要么把 E1 明确定义成由 systemd/journald 已有 retention 承担的配置切换，并证明仍需要额外文件；要么把 bounded file sink 的必要合同纳入估算。不要先固定 0.5 再把必需行为推给后续。

### N6 — minor — “按钩子语义留位置”把 raw chunk 点误说成 `on_upstream_sse_block_ready`

证据：`proposal.md:320-324` 说取证无论如何会在 `on_upstream_request_ready` 与 `on_upstream_sse_block_ready` 两个语义位置开接缝；但人写配置对后者的说明是“上游 SSE 流式响应的完整块已准备好”，而 r2 的 L3 在 `proposal.md:91-101,195-201` 明确选择解析前 raw chunk。raw parser-input chunk 可能含半帧或多帧，并不是“完整块 ready”。

修订建议：保留 raw chunk recorder seam，同时另把 operator hook 的完整块语义记为后续接缝；不要为了复用位置把二者改成同一事件。

### N7 — minor — 第六节的“每片交付后回答真实问题”有两个表述超出实际

证据：`proposal.md:330-346` 先立“每片”规则，分片 0 的交付栏却明确为“—”；它实际是 prerequisite，不应继续称业务价值分片。分片 1 写能回答“昨天 14:03”的 400，但 file sink 只能回答**部署以后**发生且当前 completion path 覆盖到的请求，不能恢复已经滚掉的昨天日志，也仍漏 B2 所述非流式异常，直到分片 2 才补 exactly-once。

修订建议：把分片 0 标为 prerequisite、不纳入“每片有查询价值”；把分片 1 改成“部署后的、已走到现有 completion sink 的请求”，分片 2 才承诺异常退出也有记录。

### N8 — minor — “pin/unpin 已实现”只对旧 `entries` 成立，新表仍需实现

证据：`proposal.md:187` 给新 `ForensicRequest` 设计了 pinned，`proposal.md:221` 称 pin/unpin 已实现。当前 `src/app/history/store.py:59-64` 与 `src/app/history/sqlite/writer.py:206-216` 只操作旧 `HistoryEntry`/`entries`；r2 又明确不复用该合同（`proposal.md:80-89`）。可复用的是行为与 SQL 模式，不是现成接线。

修订建议：改成“旧 history 已有 pin/unpin 行为可沿用，新 forensic 表仍需对应 writer/query/CLI 接线”，并把它计入 L1/容量分片。

## 四、当前工作树漂移核对

针对并行改动重新核对的承重事实仍成立：

- import closure 仍为 `pipeline_app=111`、`cli=125`、history 6/6/9/34，三类禁区违规均为 0；
- `_Trace.failed`、stream ending 分类虽在并行演进，但 `_log_completion` 仍只有正常非流式与 `_StreamAccounting.finish` 两处；非流式 `BaseException` 洞仍在；
- `_StreamAccounting.finish` 当前仍以 `done` 幂等，generator 与 response 两个收尾者都调用它，r2 的“流式路径 exactly-once”在正常进程存活与 logger 不抛错的边界内可沿用；
- `_counted_upstream` 仍逐个转发 `response.aiter_bytes()` 产出的 parser-input chunks，不改字节；
- `parse_frame` 仍执行 replacement decode、丢 comment/未知字段、规范化 data 行；
- `ProxyConfig.history` 与六个 operator hooks 仍无运行时消费者；`setup_logging` 仍只有一个 `logging.StreamHandler`。

除 N1～N8 外，没有发现由 `request_log.py`、`assembler.py`、`sse_source.py` 的并行改动新增、足以推翻 r2 其他裁决的事实漂移。

## 五、放行判断

**r2 不能按当前文本交用户裁决。** 建议先修 R1、N1～N5；N6～N8 可同轮顺手精确化。修完不需要重跑 r1 全量核验，只需复查：L2 采集合同与 estimate 是否一致、local headers 与 export projection 是否分层、首次持久化是否自带容量边界、file sink 是否有完整但不过度的合同、Spec 顺序是否符合项目规则。

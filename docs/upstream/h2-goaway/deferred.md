# 待裁决与未闭合

本文件只列**需要用户裁决**或**已知未闭合**的项。已经做完的在 `README.md` 与 `findings.md`。

## 需要用户裁决

### 1. 每连接流数上限取什么值

机制已落地（`42738c9`），`upstream_transport.max_streams_per_connection`，**默认 0 = 关闭**。

默认关闭是刻意的：本项目没有任何测量支持某个具体数字，替操作者选一个等于替他做了个他没要求的决定。给选值的人两个事实：

- 上游通告 `MAX_CONCURRENT_STREAMS = 100`，所以只有我方这个 cap 起作用；
- 姊妹项目 `copilot-api-js`（`b5892380f`，2026-07-22）发的是 **1**，并测到成批失败占比从 57.6% 降到 5.9%。**但本项目的规矩是不把它的默认值当作本项目契约。**

代价（PoC 实测）：每条连接边际 ~87 KiB RSS、精确 1 个 fd；TLS 握手 ~155ms 是最大的一项。

### 2. STR-04 的 failed History 一半

SSE 信封那一半已闭合（`16dd68c`）。另一半没有：`context.reply` 仍 gate 在 `terminal.seen`，被截断的回复不进 `reply`。

放宽那道门是 **hooks 与 History 的契约变更**（`reply is not None ⇒ 回复已完成` 是现有契约），`../../anthropic-responses-bridge/implementation.md` 的结构怪味登记明写这一项要与 STR-04 同一切片一并裁决。

## 已知未闭合

### 3. 三条路的裁决还没有调用者 —— 已移交，且 CONTINUE 那一格已作废

`decide_stream_ending()`（`5c1afbe`）是纯函数、已测、已做变异检验，但**生产链路无人调用**。

**这笔欠账 2026-08-21 移交给 `../retry-and-continuation/`**，本主题不再跟踪它。移交时状态有变，两点：

- **REPLAY / ABANDON 仍然要接**，就是人写文档里的「无痕重试」。
- **CONTINUE 那一格已被用户裁决作废**——代理内续写整体放弃，改由客户端经 MCP 工具驱动续写。`continuation_messages()` 与 `RetryReason.CONTINUATION` 因此**不再是待接线的孤儿件，而是待删除的件**。见 `../retry-and-continuation/archive-proxy-side-continuation/README.md`。

### 4. 「上游响应被提前关闭」的频率没有数

这是**目前已知的**、能区分「h2 + cap」与「HTTP/1.1」的量：提前关闭时 HTTP/1.1 作废整条连接并重新握手（实测 ~155ms），h2 只丢那条 stream。（不是唯一的量——连接复用、握手次数、时延、实际重连都可测。）

结构化日志（`10e4811`）使它**可估而非可精确计数**：`status=gone` 的语义是「交付在上游完成前从我方一侧停止」，它**包含客户端取消，也包含服务 shutdown**，而上游抛错或无终止 EOF 记的是 `fail`（见 `pipeline_app.py` 的 `_ending()`）。要评估 HTTP/1.1 因提前关闭而重连的实际代价，得排除 shutdown，并结合 `detail`、连接标识与后续连接／握手记录一起看。

### 5. 本项目自身的中断频率仍无历史基线

取证只覆盖到现网 Bun 服务。本项目当时零生产数据：History 未接活链路（`HistoryConsumer` 只在 legacy 的 `app_factory` 里构造）、日志不落盘、不在 systemd 下所以 journald 也空。

结构化日志补上的是**第二项「日志不落盘」**。**第一项与第三项仍然成立**——服务仍不在 systemd 下，journald 仍无记录；`HistoryConsumer` 没接活链路这一条尤其值得单独确认是否有意为之。

## 明确不做

- ~~向 httpcore／hyper-h2 上报~~ ——用户 2026-08-20 裁决删除。这是诊断作者自己臆想的条目，从未被要求，也没有任何文档完整描述过它是什么；**本项目不修改上游仓库。**

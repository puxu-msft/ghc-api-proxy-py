# auto mode 分类器本地处置 — 未闭合事项

> 只放**未闭合**的条目。查清的移出本文、归进 `spec.md` 或 `status.md` 并带出处。编号是标识不是序列，移走的不补号。
>
> 快照日期：2026-08-23。

## D1 — 合成回复被记账成一次真实上游交换

**状态**：未修，超出本次范围，**是既有缺陷而非本次引入**。

两轮评审各自独立提出（gpt 报告 C-02、claude 报告 minor-4）。

`_answered_auto_mode()` 造一个没有经过网络的 `httpx2.Response`，而下游的完成记账无条件按真实上游响应处理它：把空的 synthetic request 记成发送 `0` 字节，把 `response.http_version`（默认 `HTTP/1.1`）记成上游协议，把本地 body 长度记成上游返回字节。流式分支还会经 `_counted_upstream()` 增加 upstream chunk 数与首字节时间。

于是完成行会声称「代理从一个 HTTP/1.1 上游收到了这份回复」，而实际上没有任何上游参与。这与本项目既有的约定直接冲突：日志与 footer 的这组字段描述的是 proxy↔upstream 那一段交换。

**为什么不在本次修**：`_answered_failed_search()`（hosted web search 的失败合成）走的是**完全相同的形状**，早于本改动存在。只修新路径会让两条同形路径行为不一致，修两条则要动 observability 层对 `synthesized` 的读法（`inference.py` 的三处记账点与 `request_trace.py`），影响面超出「添加一个配置项」。

**修的方向**（供接手者，未验证）：`HandledRequest.synthesized` 已经存在并已被交付层读取（`delivery_policy.py`、`reply.py` 三处 carve-out），记账点缺的是同一个 carve-out——让这些字段在 synthetic 路径上**缺席**或显式标为 local，而不是填一个虚构值。命中专用的那条 INFO 日志（「多少字节未发上游」）是正确的，且不能替代这件事：它修不了另一条完成记录里的假事实。

出处：`reports/260823-review-gpt.md` §C-02、`reports/260823-review-claude.md` §minor-4。

## D2 — 判据在真实流量上从未命中过一次

**状态**：未验证，且当前环境下无法验证。

本特性全部证据来自两处：客户端源码静态阅读（三个版本）与 2026-07/08 的历史流量（2300 条）。**没有一次端到端的真实命中**。

原因是环境的：本机 `~/.claude/settings.json` 当前 `defaultMode: "bypassPermissions"`，该模式下客户端根本不调用分类器；而本项目自 2026-08-20 接管 4141 起不落上行 body，即使有流量也无从取证。

**要闭合它需要**：把 Claude Code 切到 auto mode，打开 `decision: allow`，然后确认日志里出现命中行、且客户端没有因为回复不可解析而重试（重试会表现为同一动作前连续多条命中）。这是一次几分钟的人工确认，不是自动化任务。

在它闭合之前，`spec.md` 里所有关于「客户端会接受这个回复」的陈述都是**从源码推出的**，强度是「足以据以实现」，不是「已观测」。

## D3 — 历史库其实存了入站 body，而代码注释说它没存

**状态**：未修，与本特性相邻但不属于它。

`tests/int/recorded/from_history.py:210` 的注释写着 `# Left empty: history records no request body, so there is nothing to project.`，而本次取证证明历史库完整保存了入站 body——`payload-skeleton` + `payloadSequences` + `v3_sequence_nodes` 三段可以拼回完整请求（重建路径见 `../tmp/260823-auto-mode-traffic-samples.md` §2.2）。

影响的不只是一句注释：如果将来要给**上行方向**建 cassette（比如给分类器请求做夹具），现状的注释会让人以为必须真实调用上游或手写，而实际上可以从历史库导出真实骨架——那正是本项目「Upstream behaviour is recorded, not imagined」想要的东西。

需要主会话或接手者裁决：是否修正注释并扩展 `from_history.py` 支持请求侧投影。

出处：`../tmp/260823-auto-mode-traffic-samples.md` §7.1。

## D4 — 内嵌的网关契约文档值得单独立项

**状态**：未展开。

Claude Code bundle 里内嵌了一份写给**网关/代理实现方**的契约文档（`~/.claude/refs/claude-code-2.1.241/app.pretty.js:648400` 一带），本次只读了与合成回复相关的那几段。它还包含：

- 一张 `error.message` → 错误类别的映射表（`prompt_too_long`、`max_tokens_context_overflow`、`beta_header:<value>`、`thinking_type:<...>`、`effort_unsupported`、`media_budget`、`image_block`、`document_block` 等），并说明表是**有序**的、类别是 append-only contract、分类要保守——「一个错的 token 会触发错误的客户端恢复动作」
- 阻断请求的标准格式：`400` + `x-should-retry: false` + `{"type":"error","request_id":"<id>","error":{"type":"policy_blocked","message":"…"}}`，且 `request_id` 要填成自己审计行的主键
- 端点形状约定：`match on the path, tolerate the query`

这与本项目的错误语义设计直接相关——我们现在如何把上游错误映射成客户端能正确恢复的形状，很可能可以对着这张表校准。**本次不展开**，建议单独立一个 topic。

出处：`../tmp/260823-cc-auto-mode-request-shape.md` §9。

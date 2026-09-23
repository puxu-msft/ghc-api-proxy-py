# 2026-09-23 `/v1/messages` 400 排查：路由、prefill 与跨模型 carrier

**范围与基线：** 主工作树 `main@061aff32` 加未提交 WIP；现场服务原进程 08:09:55 启动，用户于 10:48:52 自行重启。只读检查请求日志、`/api/status`、`/api/config`、本机客户端 transcript 和现行 Spec；未读取或输出消息正文，未向上游发出诊断性推理请求。

## 已确认的三个错误签名

1. 08:11:03 六个 `RoutingError`，attempts=0：四个请求 `grok-4.6`，两个请求 `gpt-5.6-terra`。原进程未加载磁盘上 08:13:39 新增的 `grok-4.6: grok-4.7` 映射；`gpt-5.6-terra` 在运行时和磁盘配置均被显式禁用。重启后 `/api/status` 已把 `grok-4.6` 报为可路由至 `grok-4.7`；前者的配置生效见 `../../service-cutover/reports/260923-4141-config-reload-observation.md`。尚未以真实推理调用证明上游成功。
2. 08:13:16 `req=701b4050-925e-4c18-be87-c2405586e345`，attempts=1，`sonnet` 路由至 `ghc-msft/claude-opus-5.5`，上游返回 400。客户端 transcript `53be5736-1030-48be-b02e-2d432a9bb4b0.jsonl` 对应时刻记有相互匹配的 assistant `tool_use` 与紧随其后的 user `tool_result`，随后客户端记录错误 `This model does not support assistant message prefill. The conversation must end with a user message.` 08:11:42 的同一会话也有一次相同形状和错误。**这不能证明实际 HTTP 请求体以 user 结束**：transcript 不是 request wire capture；该请求的 History `capture_status=none`、`client_request_available=0`，运行时 `observability.raw_capture.enabled=false`。不能据此认定是客户端主动 prefill，亦不能认定是哪一个代理阶段丢掉了 user 轮。
3. 08:13:22 `req=1681dbad-f239-4d2e-ae56-b067ed07e5f4`，attempts=1，客户端错误是 `synthetic reasoning carrier project_v2 reached provider last-mile`。客户端 transcript `d12b0df5-34cc-4fd2-b2fc-539b1fbe87b5.jsonl` 中同一会话先前 `gpt-5.6-terra` 的 thinking 块包含项目 carrier，随后请求被映射到 `claude-opus-5.5` 的 Anthropic Messages upstream。`reasoning-carrier/spec.md` §7.3 规定 carrier 不能原样到达另一协议的 provider、last-mile 必须 fail closed。这里的拒绝保护了不便携的 opaque state；丢掉历史 carrier 再声称成功会改变对话语义，不能作为修法。

## 原因、排除与剩余工作

前两项是两条不同路径：六个本地错误没有任何上游调用；prefill 错误已抵达上游。第三项是跨协议/跨模型历史的既定拒绝，非 prefill 的另一种拼写。现行 `anthropic_trailing_assistant` 仅在原始 Anthropic body **明确以 user 结尾**、且代理的最终 body 以带内容 assistant 结尾时追加 `Please continue.`；客户端自己写的 prefill 不应被伪装为成功。针对这些判据与路由的已有单测本轮运行 25 项通过，但它们不包含失败那次实际 HTTP body，不能冒充生产故障已复现。

**未完成：** 701b/8328 两次 upstream prefill 的最早分叉尚未定位，未修改产品代码，不能称为 `fixed`。下一次复现需要在用户授权的安全窗口获得请求进入代理时与实际发往上游时的末尾角色、块类型及配对关系，优先使用不含文本/签名的结构化诊断；仅当这些元数据不足时，再讨论本地限量原始捕获的隐私与切换代价。不得根据 transcript 猜测出站形状、向客户端自带 prefill 后面静默插入 user turn，或关闭 carrier guard。`gpt-5.6-terra` 禁用状态属于运维选择，本轮不替用户更改。

**重议触发：** 取得同一请求的入站/出站形状并能在隔离环境复现时，按首次偏离修复并补回归；若要改变客户端 prefill 或跨模型 carrier 的既有用户裁决，先在各自的活 Spec 中取得并记录新裁决。

**设计层观察：** request transcript 仅能证明客户端会话的逻辑事件，不是代理的 wire oracle；未启用 capture 时，“客户端自己请求了 prefill”与“某次修复删掉了最后一个 user”在当前记录里不可区分。重启后另有约四分钟的启动就绪窗口，已在 service-cutover 报告中登记。

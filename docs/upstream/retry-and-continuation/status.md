# 实现状态与路线

**日期**：2026-08-21。**权威**：`docs/.human-controlled/upstream-retry-and-continuation.md`（下称「人写文档」）。本文只记实现状态与路线，不复述它的裁决。

## 当前状态：一行代码都还没动

人写文档描述的机制**在代码里一处都不存在**。下面是 live 链路（`create_pipeline_app`，`cli.py:23,151,176`）的实际情况。

> ⚠️ `app/delivery/`、`pipeline/executor.py`、`app/hooks/` 是**未挂载的 legacy 链路**。按它们读会把结论读反——本主题的所有代码事实都取自 live 链路。

| 人写文档要求 | live 链路现状 | 出处 |
|---|---|---|
| 网络中断、5xx 可续 | **只在上游响应头到达之前**重试；network 9 次、serverError 9 次、`max_total` 20；**无退避、无 jitter、无间隔**，连打 | `direct_driver/base.py:126-176`、`:228` |
| 读流中断可续 | **零重试**。5 个 except 分支已逐条核对 | 同上 |
| 已交付过完整块才走合成 | 「已交付」这个判据**读不出来**。`DeliverySession.delivered` 是 `stream.py:215` 的函数内局部变量，无外部读取者，`committed_count` 零调用。出错时能读的是 `assembler.terminal.blocks`——那是**已装配**，`policy: full`／`until-tool-use` 下会高估 | `pipeline/delivery/stream.py` |
| `stop_reason` 原样透出 | 只认 `max_output_tokens` → `max_tokens`，**其余所有 incomplete 一律翻成 `end_turn`**；`incomplete_details.reason` 读到后不写任何地方（`Terminal` 无承载字段） | `pipeline/delivery/assembler.py:330-338` |
| 丢弃 `status:"incomplete"` 的块 | `assembler.py` **完全不读 item 的 `status`**（该文件 `.status`／`"status"` 零命中），`output_item.done` 无条件成块 | `assembler.py:231-232` → `_close`（`:279`） |
| 429 返回真实状态码 | 预算耗尽后被包成 `PipelineAbort`，客户端拿到 **502，`Retry-After` 丢失**；`error_status` 的 429 分支在 driver 路径上不可达。而且已有测试把这个缺陷**固定成断言** | `base.py:214`；`tests/int/test_pipeline_app.py:755` |
| 已交付之后的失败要能进裁决 | 干净 EOF 无终止事件 → 发 SSE `error`；**撕流／idle／deadline／缓冲超限 → 不发任何错误帧**，异常上抛截断连接，只进服务端日志 | `stream.py:279-288`；`pipeline_app.py:590-591` |
| 请求行区分「上游尝试失败」 | `LogStatus` 只有 `ok`／`fail`／`gone` 三值；`[RETRY]` 前缀已存在但**是 7 字符，其余全是 6**，把固定宽度那一列顶歪了 | `request_log.py:65,70`；`logging.py:22,68` |
| 合成工具调用 | 不存在 | — |

**已存在但零生产调用点的件**（`decide_stream_ending()`、`RetryBudget`、`buffered_retry.py`、`delayed_commit.py` 等 6 组，以及 `continuation.*`／`streamReplay`／`max_tokens_as_retryable`／`hedge` 4 个死配置项）见 `deferred.md`。

## 一条决定分类表形状的结构事实

**上游 HTTP 状态码随上游响应头到达，早于任何 body 字节；而块要装配出来至少得有 body。** 加上「已交付」分支不发起任何新的上游 attempt，两头一夹，得到：

| 失败形态 | 只可能在「未交付」 | 只可能在「已交付」 | 两者皆可 |
|---|---|---|---|
| 400 / 401 / 403 / 429 / 5xx（HTTP 状态码类） | ✔ | | |
| `stop_reason` 类（`max_tokens`、`refusal`） | | ✔ | |
| 网络中断 / 撕流 | | | ✔ |
| 请求超时 / deadline | | | ✔ |
| 客户端断开 / 优雅关闭 | | | ✔ |
| 代理保护机制（缓冲超限） | | ✔ | |

**推论**：合成工具调用时传给 MCP 的 `category`，实际只可能取到 `network` 与 `internal` 那一小撮，**取不到 `client`／`auth`／`rate_limit`**。这三格的回复文案配了也不会被用到。

这是推论不是裁决——前提是「已交付分支不发起新 attempt」，前提变了它就不成立。

## 路线：五个阶段

**顺序有依赖，不要合并 D 与 E。** D 改的是交付路径的失败处理，E 在它之上加合成；混在一个分支里出问题时分不清是谁的。

### A. 纯文档与归档

建本主题；把被推翻的代理内续写材料集中归档到 `archive-proxy-side-continuation/`；重指 `h2-goaway` 的活文档；候选材料写进 `.dev/human-controlled-docs-candidates/`。

无行为风险。**先于 B**——否则删完代码没有地方说明为什么删。

### B. 删除代理内续写机制

删 `continuation_messages()`、`RetryReason.CONTINUATION`、`decide_stream_ending()` 的 CONTINUE 分支、`continuation.*` 配置及其测试。

**明确不动**：`decide_stream_ending()` 本身（REPLAY／ABANDON 要接线）、`RetryBudget`、`buffered_retry.py`、`delayed_commit.py`、`streamReplay`、`hedge`、`max_tokens_as_retryable`。用户 2026-08-21 裁决：「现有代理内续写机制从代码中删除，其他未接线的功能不要动」。

### C. 观测面与 `stop_reason` 原样透出

三处彼此独立、各自可单独验证：

1. `[RETRY]` → `[RETY]`。**这是在修一个既有 bug**：实测所有前缀 6 字符宽，只有它 7 字符。
2. `LogStatus` 加第四格 `retry` + `STATUS_COLOURS` 黄色。`request_log.py:70` 的注释自己写明两张颜色表是「restated rather than imported……a change to either belongs in both」，工作项边界由代码自述。
3. 停止把非 `max_output_tokens` 的 incomplete 改写成 `end_turn`；`stop_reason` 原样透出，已知值着色；让 `Terminal` 承载 `incomplete_details.reason`。会动到现有断言。

第 3 项与 G1（分支 `fix/upstream-error-events`）相邻，接线前先与该分支对账。

### D. 无痕重试

- 读流中断纳入重试——**今天零重试，这是最大的新能力**。
- 接 `decide_stream_ending` 的 REPLAY／ABANDON。
- 删 `client_delivery.synthesized_response_headers_after_sec`（`schema.py:264`，默认 240 秒）。
- 429 走反应式限流器；预算耗尽后返回**真实 429 + `Retry-After`**，改掉把 502 固定住的那条断言。
- 本侧结束（客户端断开／优雅关闭／代理保护机制）不进重试。优雅关闭**改走 MCP-driven 续写**，不在关闭中开新的上游请求。
- **无痕重试不设间隔**，反应式限流器给的间隔除外。

**风险最高的一组**，动的是交付路径。要跑完整回归 + 独立评审。

> **一条推论，不是独立规则**：删掉 `synthesized_response_headers_after_sec` 之后，`stream.py:253-262` 那个唯一会单独发 `message_start` 的出口消失，于是 `message_start` 只能与第一个完整块同批发出，**半开状态不再可达**。前提是那个配置项确实被删；它若回来，这条推论随之失效。注意这是**构造性保证**——live 链路一条相关断言都没有（9 条 `DeliveryOrderError` 全在未挂载的 legacy 侧），将来谁再引入单发 `message_start` 的路径，不会有任何东西报错。

### E. MCP-driven 续写

- `status:"incomplete"` 的块丢弃规则：**有任何完整块才丢；只有未完成块则保留**（保留半截内容优于给客户端一个空回答）。reasoning item 无此字段，不处理。
- 合成 `tool_use` 块调用 `turn_interrupted(num_messages, category, message)`；`num_messages` 取**客户端请求**的 `messages` 长度。
- 检查入站 `tools[]` 是否含该工具；没有则**打 warning 但照发**。
- 配置项 `client_delivery.auto_retry_tool_call_full_name` 可覆盖工具全名。
- 仅在 **anthropic-messages 客户端请求**上生效；两条上游腿都适用。
- `max_tokens` 一律走合成，不回落到无痕重试。
- 观测面：**客户端请求算成功，本次上游尝试算失败**，请求行记 `[RETY]` + 黄色。
- `usage` 报失败 attempt 实报值。

**跨仓依赖**：`num_messages` 的判法需与改 MCP 的同伴对齐——建议按「同一数值重复出现」而非「数值有没有增长」，因为并行子智能体与主会话共享同一个 MCP server 进程，调用会交错。两边不一致这个参数就白加。

## 几条不必再写进代码的顾虑

- **`usage` 排除在 token 校准之外**——不需要。校准只学输入侧（`token_calibration.py:53-63`，`input_tokens + cache_read + cache_creation` 配 `estimate_anthropic_input`），截断只影响输出侧；更要紧的是 MCP-driven 下**没有代理自造的续写请求**，估算与实测天然来自同一个实际请求，那正是原条款要求的条件，由构造保证。
- **MCP-driven 续写的次数上限**——不设。用户 2026-08-21 裁决：会触发这条路就说明事情有进展。门本身（已交付过至少一个完整块）保证零进展的一轮到不了这里。
- **被截断 tool call 的 `{"__raw": …}` 参数**——由 E 的丢弃规则顺手解决。另有实测旁证表明 Claude Code 自己有 `safeParseJSON` → `{}` → zod → `is_error` 的原生恢复链，所以它本来也不是必须修的危害。

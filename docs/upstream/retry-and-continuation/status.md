# 实现状态与路线

**日期**：2026-08-21。**权威**：`docs/.human-controlled/upstream-retry-and-continuation.md`（下称「人写文档」）。本文只记实现状态与路线，不复述它的裁决。裁决的时间、场合与理由记在 [`decisions.md`](decisions.md)。

## 当前状态：除 B 阶段外一行代码都还没动

**本节描述的是主仓 `8a36fe3`**（即 B 阶段落地之前）。B 阶段随后删除了代理内续写机制；下表中与它相关的行已就地标注。其余各行仍然成立。

> 可变陈述必须带锚点：主仓正被并行会话推进，一句不带提交号的「现状」在几分钟内就会变成假话。

人写文档描述的机制**在代码里一处都不存在**。下面是 live 链路（`create_pipeline_app`，`cli.py:23,151,176`）的实际情况。

> ⚠️ `app/delivery/`、`pipeline/executor.py`、`app/hooks/` 是**未挂载的 legacy 链路**。按它们读会把结论读反——本主题的所有代码事实都取自 live 链路。

| 人写文档要求 | live 链路现状 | 出处 |
|---|---|---|
| 网络中断、5xx 可续 | **只在上游响应头到达之前**重试（循环在 `base.py:126-176`；`_send` 止于响应头见 `:228`），**无退避、无 jitter、无间隔**，连打。次数 network 9／serverError 9／`max_total` 20／streamReplay 100 来自配置默认值 | `direct_driver/base.py:126-176`、`:228`；`config/schema.py:163-175,184` |
| 读流中断可续 | **零重试**。5 个 except 分支已逐条核对 | 同上 |
| 已交付过完整块才走合成 | 「已交付」这个判据**读不出来**。`session` 是 `stream.py:215` 的函数内局部变量，它的 `delivered`／`committed_count`（`blocks.py:141-142`）因而没有外部读取者。出错时能读的是 `assembler.terminal.blocks`——那是**已装配**，`policy: full`／`until-tool-use` 下会高估 | `pipeline/delivery/stream.py:215`、`pipeline/delivery/blocks.py:141-142` |
| `stop_reason` 原样透出 | 只认 `max_output_tokens` → `max_tokens`，**其余所有 incomplete 一律翻成 `end_turn`**；`incomplete_details.reason` 读到后不写任何地方（`Terminal` 无承载字段） | `pipeline/delivery/assembler.py:330-338` |
| 丢弃 `status:"incomplete"` 的块 | `assembler.py` **完全不读 item 的 `status`**（该文件 `.status`／`"status"` 零命中），`output_item.done` 无条件成块 | `assembler.py:231-232` → `_close`（`:279`） |
| 429 返回真实状态码 | 预算耗尽后被包成 `PipelineAbort`，客户端拿到 **502，`Retry-After` 丢失**；调查未能在 driver 路径上找到通往 `error_status` 429 分支的路径（**是「未找到」，不是已证明不可达**）。而且已有测试把这个缺陷**固定成断言** | `base.py:214`；`tests/int/test_pipeline_app.py:755` |
| 已交付之后的失败要能进裁决 | 干净 EOF 无终止事件 → 发 SSE `error`（`stream.py:279-288`）。撕流／idle／deadline／缓冲超限 → 异常上抛截断连接，**只进服务端日志**（`pipeline_app.py:590-591` 是那条日志判定）。「**不发任何错误帧**」是按 `stream.py` 里全部发帧点枚举得出的否定结论，不由 `:590-591` 支撑 | `stream.py:279-288`；`pipeline_app.py:590-591` |
| 请求行区分「上游尝试失败」 | `LogStatus` 只有 `ok`／`fail`／`gone` 三值；`[RETRY]` 前缀已存在但**是 7 字符，其余全是 6**，把固定宽度那一列顶歪了 | `request_log.py:65,70`；`logging.py:22,69` |
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

**推论**：合成工具调用时传给 MCP 的 `category`，**取不到 `client`／`auth`／`rate_limit`**——那三格全属 HTTP 状态码类，只可能出现在「未交付」位置。这三格的回复文案配了也不会被用到。

剩下能到达的是 `network`（撕流、超时）与 `internal`（本项目自身异常）；`ErrorCategory` 的六格里只有这两格可达。**但可达形态不止这两种**：`max_tokens` 是唯一确定会到达合成点的形态，而它**根本不在 `ErrorCategory` 里**——用户已裁决它要有自己的 category 与回复文案，取什么值尚未定，见 `decisions.md` 第四节。

这是推论不是裁决——前提是「已交付分支不发起新 attempt」，前提变了它就不成立。

## 路线：五个阶段

**顺序有依赖，不要合并 D 与 E。** D 改的是交付路径的失败处理，E 在它之上加合成；混在一个分支里出问题时分不清是谁的。

### A. 纯文档与归档

建本主题；把被推翻的代理内续写材料集中归档到 `archive-proxy-side-continuation/`；重指 `h2-goaway` 的活文档；候选材料写进 `.dev/human-controlled-docs-candidates/`。

无行为风险。**先于 B**——否则删完代码没有地方说明为什么删。

### B. 删除代理内续写机制 —— **已落地**（主仓 `40d9c76`）

删 `continuation_messages()`、`RetryReason.CONTINUATION`、`decide_stream_ending()` 的 CONTINUE 分支、`continuation.*` 配置及其测试。

**明确不动**：`decide_stream_ending()` 本身（REPLAY／ABANDON 要接线）、`RetryBudget`、`buffered_retry.py`、`delayed_commit.py`、`streamReplay`、`hedge`、`max_tokens_as_retryable`。用户 2026-08-21 裁决：「现有代理内续写机制从代码中删除，其他未接线的功能不要动」。

### C. 观测面与 `stop_reason` 原样透出 —— **第 1、3 项已落地**（主仓 `696a786`），第 2 项移入 E

三处彼此独立、各自可单独验证：

1. `[RETRY]` → `[RETY]`。**这是在修一个既有 bug**：实测所有前缀 6 字符宽，只有它 7 字符。
2. `LogStatus` 加第四格 `retry` + `STATUS_COLOURS` 黄色。`request_log.py:70` 的注释自己写明两张颜色表是「restated rather than imported……a change to either belongs in both」，工作项边界由代码自述。
   **→ 已移入 E 组**：请求行的 `retry` 状态**没有生产者**，要到合成落地才有人设它。放在这里就是造一个没人走的分支——本项目已经有六组那样的件。（通用日志器的 `[RETY]` 前缀是活的，`logging.py:42` 给任何带 `status` 的行贴前缀，所以第 1 项独立成立。）
3. 停止把非 `max_output_tokens` 的 incomplete 改写成 `end_turn`，改为原样透出；没给原因的 `response.incomplete` 发 `"incomplete"` 而非落回 `end_turn`。
   **未做 `Terminal` 承载 `incomplete_details.reason`**：`stop_reason` 现在已经原样携带该事实，桥 spec 要求的「保留原因事实」由它满足，再加一个无人读取的字段就是孤儿件。唯一被映射掉的是 `max_output_tokens` → `max_tokens`，而那是 spec 明令的映射、1:1 可还原。

**已与 G1 对账**（分支 `fix/upstream-error-events`，同伴在飞）：它对 `assembler.py` 是**纯新增 65 行**（`UpstreamFailure` / `Terminal.failure` / `_read_failure`），**没有动 `_read_terminal`**——它那份的第 380-382 行与 main 逐字相同。两处改动是同一文件的不同 hunk，不重叠。

**变异检验**：把 `end_turn` 放回去，两条新测试都转红，还原后文件与变异前逐字节相同（sha256 一致）。

### D. 无痕重试

- 读流中断纳入重试——**今天零重试，这是最大的新能力**。
- 接 `decide_stream_ending` 的 REPLAY／ABANDON。
- 删 `client_delivery.synthesized_response_headers_after_sec`（`schema.py:264`，默认 240 秒）。
- 429 走反应式限流器；预算耗尽后返回**真实 429 + `Retry-After`**，改掉把 502 固定住的那条断言。
- 本侧结束（客户端断开／优雅关闭／代理保护机制）不进重试。优雅关闭**改走 MCP-driven 续写**，不在关闭中开新的上游请求。
- **无痕重试不设间隔**，反应式限流器给的间隔除外。

**风险最高的一组**，动的是交付路径。要跑完整回归 + 独立评审。

> **施工约束（从 `h2-goaway/findings.md` 的在建表继承而来，仍然成立）**：要动的 `pipeline_app.py`／`handler.py` 正被并行会话大改（`direct_driver` 重构）。**共用同一棵工作树时同改一文件是互相覆盖，不是合并冲突**——Git 不会报错，后写的直接盖掉先写的。动手前先看 `git status` 与 `git branch -a`（带 `+` 的分支正被别的 worktree 检出），必要时改用隔离工作树。

> **一条推论，不是独立规则**：删掉 `synthesized_response_headers_after_sec` 之后，`stream.py:253-262` 那个唯一会单独发 `message_start` 的出口消失，于是 `message_start` 只能与第一个完整块同批发出，**半开状态不再可达**。前提是那个配置项确实被删；它若回来，这条推论随之失效。注意这是**构造性保证**——live 链路一条相关断言都没有（9 条 `DeliveryOrderError` 全在未挂载的 legacy 侧），将来谁再引入单发 `message_start` 的路径，不会有任何东西报错。

### E. MCP-driven 续写

本节每一条都有出处：写进人写文档的见该文档，只存在于 2026-08-21 讨论中的见 [`decisions.md`](decisions.md) 第二节，属本项目推论而非裁决的见其第三节（「两条上游腿都适用」是推论）。

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

- **`usage` 排除在 token 校准之外**——不需要，而且理由比原先写的更强。live 链路的校准在 `server/handler.py:301-303`（`pipeline_app.py:43` 引入），它**只在 `count_tokens` 端点里学**：拿本地估算配上游 `count_tokens` 的答案，**根本不读消息响应的 `usage`**。读 `usage` 的那个 `TokenCalibrationSuccessObserver`（`app/hooks/builtin/token_calibration.py:53-65`）在未挂载的 legacy 侧，不参与。加之用户已裁决 `count_tokens` 不走续写，应用侧也没被碰到。
- **MCP-driven 续写的次数上限**——不设。用户 2026-08-21 裁决：会触发这条路就说明事情有进展。门本身（已交付过至少一个完整块）保证零进展的一轮到不了这里。
- **被截断 tool call 的 `{"__raw": …}` 参数**——由 E 的丢弃规则顺手解决。另有实测旁证表明 Claude Code 自己有 `safeParseJSON` → `{}` → zod → `is_error` 的原生恢复链，所以它本来也不是必须修的危害。

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

**已存在但零生产调用点的件**（`decide_stream_ending()`、`RetryBudget`、`buffered_retry.py`、`delayed_commit.py` 等 6 组，以及 `continuation.*`／`streamReplay`／`max_tokens_as_retryable`／`hedge` 4 个死配置项）见 `deferred.md`。**前三个已分别按用户裁决删除**（B 组、`9aa31f9`、`fef7d96`）；`hedge` 仍在。

> **2026-08-22 更正**：上面这句把 `decide_stream_ending()` 列为「零生产调用点」，**当天已不成立**——`8f654b4` 接线，`1743a0b` 把「上游是否已完成」前移到异常分类之前，`f0527e5` 补守卫。它现在是活件；不可达的只剩它内部的 `COMPLETE` 那一格（调用者先答完了这一问）。见 `deferred.md` 第 7、11、12 条。

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

> **2026-08-23／24 更正，权威已移交**：上一段说 `internal` 可达，这在 `0ca87b9` 之后不再成立——兜底从 `INTERNAL` 改成 `UPSTREAM`，错误分支的值域收成 `network` / `upstream` / `auth`，`internal` 已经发不出来。**这一格的权威是 [`README.md`](README.md) 的 `category` 行与其后「三条会绊到人的」第二条**，那里记着它当天变了两次的完整经过、以及 `1a34042` 之后本侧 bug 不再冒充上游；本处不复述，保留原句只为说明这张表当初是怎么推出来的。

这是推论不是裁决——前提是「已交付分支不发起新 attempt」，前提变了它就不成立。

## 路线：五个阶段

**顺序有依赖，不要合并 D 与 E。** D 改的是交付路径的失败处理，E 在它之上加合成；混在一个分支里出问题时分不清是谁的。

### A. 纯文档与归档

建本主题；把被推翻的代理内续写材料集中归档到 `archive-proxy-side-continuation/`；重指 `h2-goaway` 的活文档；候选材料写进 `.dev/human-controlled-docs-candidates/`。

无行为风险。**先于 B**——否则删完代码没有地方说明为什么删。

### B. 删除代理内续写机制 —— **已落地**（主仓 `40d9c76`）

删 `continuation_messages()`、`RetryReason.CONTINUATION`、`decide_stream_ending()` 的 CONTINUE 分支、`continuation.*` 配置及其测试。

**当时明确不动**：`decide_stream_ending()` 本身（REPLAY／ABANDON 要接线）、`RetryBudget`、`buffered_retry.py`、`delayed_commit.py`、`streamReplay`、`hedge`、`max_tokens_as_retryable`。用户 2026-08-21 裁决：「现有代理内续写机制从代码中删除，其他未接线的功能不要动」。

**后续两次局部推翻**（均由用户，记在 `decisions.md` 第 15、15之三 条）：`streamReplay` 随「断流走标准上游重试预算」删除（`9aa31f9`），`max_tokens_as_retryable` 随配置迁移删除（`fef7d96`）。其余仍然不动。

### C. 观测面与 `stop_reason` 原样透出 —— **第 1、3 项已落地**（主仓 `696a786`），第 2 项移入 E

三处彼此独立、各自可单独验证：

1. `[RETRY]` → `[RETY]`。**这是在修一个既有 bug**：实测所有前缀 6 字符宽，只有它 7 字符。
2. `LogStatus` 加第四格 `retry` + `STATUS_COLOURS` 黄色。`request_log.py:70` 的注释自己写明两张颜色表是「restated rather than imported……a change to either belongs in both」，工作项边界由代码自述。
   **→ 已移入 E 组**：请求行的 `retry` 状态**没有生产者**，要到合成落地才有人设它。放在这里就是造一个没人走的分支——本项目已经有六组那样的件。（通用日志器的 `[RETY]` 前缀是活的，`logging.py:42` 给任何带 `status` 的行贴前缀，所以第 1 项独立成立。）
3. 停止把非 `max_output_tokens` 的 incomplete 改写成 `end_turn`，改为原样透出；没给原因的 `response.incomplete` 发 `"incomplete"` 而非落回 `end_turn`。
   **未做 `Terminal` 承载 `incomplete_details.reason`**：`stop_reason` 现在已经原样携带该事实，桥 spec 要求的「保留原因事实」由它满足，再加一个无人读取的字段就是孤儿件。唯一被映射掉的是 `max_output_tokens` → `max_tokens`，而那是 spec 明令的映射、1:1 可还原。

**已与 G1 对账**（分支 `fix/upstream-error-events`，同伴在飞）：它对 `assembler.py` 是**纯新增 65 行**（`UpstreamFailure` / `Terminal.failure` / `_read_failure`），**没有动 `_read_terminal`**——它那份的第 380-382 行与 main 逐字相同。两处改动是同一文件的不同 hunk，不重叠。

**变异检验**：把 `end_turn` 放回去，两条新测试都转红，还原后文件与变异前逐字节相同（sha256 一致）。

### D. 无痕重试 —— **已落地**

| 提交 | 内容 |
|---|---|
| `361a7b9` | 预算耗尽保留上游真实状态（429 + `Retry-After`、超时 504）；`PipelineAbort` 带 `cause`，三个 `error_*` 读穿它 |
| `0b57645` | 删 `synthesized_response_headers_after_sec` 与整条合成前导帧管路 |
| `a2c9b77` | 更正：200 早于第一个 chunk 发出（`starlette/responses.py:249` 实证），SSE ping 不再被「有没有交付过块」拦 |
| `96eb2fa` | `ReplaySupport` 接缝：位置判定在交付层，可重试性判定在调用方 |
| `9aa31f9` | 删 `streamReplay`，断流走 `network` 普通预算 |
| `a68672c` | driver 不再吞掉取消（504 而非 502 `CancelledError`） |
| `51196e2` | 客户端时限真正罩住 body，到点发 SSE error 帧 |
| `8f654b4` | 接线，并让一条客户端请求共用一个 `RetryLedger` |
| `1018e3a` | 按独立评审修 1 blocker + 6 major：重开不再二次翻译 payload、客户端时限跟着新迭代器走、error 帧的门改回响应头、attempt 数刷新、两处时限同起点 |

**每一处有测试的新行为都做过变异检验**，且还原后逐字节校验。措辞是评审收窄的：变异检验只能证明「有测试的地方测试是活的」，对**没有测试的地方一言不发**——D 组的 blocker 正是藏在那里。端到端那条（`test_a_torn_stream_the_client_never_saw_is_replayed_end_to_end`）在去掉 `replay=replay` 后转红——它钉的是接线，不是接缝。

原计划条目：

- 读流中断纳入重试——**今天零重试，这是最大的新能力**。
- 接 `decide_stream_ending` 的 REPLAY／ABANDON。
- 删 `client_delivery.synthesized_response_headers_after_sec`（`schema.py:264`，默认 240 秒）。
- 429 走反应式限流器；预算耗尽后返回**真实 429 + `Retry-After`**，改掉把 502 固定住的那条断言。
- 本侧结束（客户端断开／优雅关闭／代理保护机制）不进重试。优雅关闭**改走 MCP-driven 续写**，不在关闭中开新的上游请求。

  **2026-08-22 更正：这一条当时没有落地，而 D 组标着「已落地」。** 直到该日 `active_requests.draining` 在任何决定重试的代码里都**没被读过一次**，而且在 systemd 那条路上**根本没人置它**——`serve_inherited` 起的是裸 `uvicorn.Server`，只有独立模式（自己拥有监听套接字）把 `begin_draining` 传了下去。所以排空期间上游一报错照样开新的上游请求。已由主仓 `db49581` 补上：两道闸（驱动层预算、交付层重开），加 systemd 路径的接线，三处各有变异检验。

  **同时更正这条计划文字本身**：「优雅关闭改走 MCP-driven 续写」读起来像是关机会**触发**续写，实际不是。续写要求客户端手里已有内容，而 `decide_stream_ending` 只在**一个字节都没交付**时才返回 REPLAY——所以被排空拦下的重开，客户端拿到的是截断结局，不是交接；而那些真会以交接收场的失败，本来就因为已交付过块而没有重开资格，与排空无关。准确的说法是**「关机时不再开新的上游请求」**，交接是另一条路径的既有行为。
- **无痕重试不设间隔**，反应式限流器给的间隔除外。

**风险最高的一组**，动的是交付路径。要跑完整回归 + 独立评审。

> **施工约束（从 `h2-goaway/findings.md` 的在建表继承而来，仍然成立）**：要动的 `pipeline_app.py`／`handler.py` 正被并行会话大改（`direct_driver` 重构）。**共用同一棵工作树时同改一文件是互相覆盖，不是合并冲突**——Git 不会报错，后写的直接盖掉先写的。动手前先看 `git status` 与 `git branch -a`（带 `+` 的分支正被别的 worktree 检出），必要时改用隔离工作树。

> **一条推论，不是独立规则**：删掉 `synthesized_response_headers_after_sec` 之后，`stream.py:253-262` 那个唯一会单独发 `message_start` 的出口消失，于是 `message_start` 只能与第一个完整块同批发出，**半开状态不再可达**。前提是那个配置项确实被删；它若回来，这条推论随之失效。注意这是**构造性保证**——live 链路一条相关断言都没有（9 条 `DeliveryOrderError` 全在未挂载的 legacy 侧），将来谁再引入单发 `message_start` 的路径，不会有任何东西报错。

### E. MCP-driven 续写 —— **已落地**

| 提交 | 内容 |
|---|---|
| `66b63c9` | 丢弃上游标为 `status:"incomplete"` 的块——**有完整块在前才丢**，只有它时保留；reasoning 无该字段，不处理 |
| `e81f07f` | 交接：合成 `tool_use` 调用 `turn_interrupted`；`num_messages` 取客户端 `messages` 长度；工具未声明只警告不阻断；仅 anthropic-messages 客户端请求；`max_tokens` 一律交接；请求行 `[RETY]` + 黄色 |
| `bce8b0d` | 按独立评审修 1 blocker + 3 major：**已完成的回合不再被伪造成中断**（COMPLETE 曾被折进 ABANDON）；`max_tokens` 丢空时不再交付零字节；补主路径测试 |
| `fef7d96` | 非流式 `stop_reason` 不再抹平成 `end_turn`（C 组只修了流式那侧，两条路曾对同一事实给出不同答案）；配置项迁移 |
| `af84097` | **非流式续写**：翻译时找被截断 item 的边界 + 缓冲回复末尾追加合成块。推翻了「非流式不可能续写」 |

### F. 交接信息与归因 —— **已落地**

起点是用户 2026-08-24 的一句观察：续写请求触发正常，但 `message` 字段只有一个裸 h2 事件的 `repr`（`<ConnectionTerminated error_code:0, …>`），读不出发生了什么。查下去牵出的是归因与分类，不只是文案。

| 提交 | 内容 |
|---|---|
| `0ebdfd0` | 撤回 h2 映射的理由，并把守卫改名为它真正检查的东西（原名声称的是「h2 异常按构造属上游」，实测 10 个成员可由调用方误用触发，该断言不成立） |
| `0ca87b9` | 裸 `h2.ProtocolError` 归入 `_CONNECTION_ERRORS`（用户 2026-08-23 选定；连带变成可重放）。**同一个 GOAWAY 不再因为内核有没有把帧并进一次 `read()` 而落到两种命运** |
| `1a34042` | 由调用方指名上游侧（`UpstreamSource`），交接信息说出它吞掉了什么。标记下移到 `_counted_upstream` **之下**：本侧字节计数器的 bug 不再冒充上游 |
| `93c4bab` | 关闭链路穿过字节计数器（客户端离开后，标记、两道守卫与上游响应曾一直悬着等回收）；记录每一次重放替换了什么 |
| `0062b67` | 被重放的失败与交接信息用同一个界限截断（`repr` 无上限，完成行只有一行） |
| `da0c4b5` | 关闭失败不再顶掉正在传播的异常；每一次重放都记，而不只是第一次 |
| `0f2e7f1` | cleanup 先做完再上报：委托 `finish_stream_cleanup`（第二次取消不再打断释放；`GeneratorExit` 之下的关闭失败不再被吞）；`raise_with_cleanup_under` 统一三处配对；`replaced_failures` 与 attempt 数同条件写出，不再造幽灵重放 |
| `b5bc8f9` | 上游写完终结事件之后再断连，不再无痕：交付层 `on_tear_after_terminal` 回调 + 完成行一句 note，状态仍为 `ok`（客户端拿到了完整回合）。这是 `deferred.md` §22之七 表里最后一格 |
| `bb17558` | 按第七轮评审修 5 minor + 2 nit + 2 条建议：异常配对的五处拼法统一到一个 helper；`or` 改 `is None`（falsey 异常会翻转退出优先级）；`asyncio.shield` 改 `asyncio.wait`（取消后 cleanup 再失败会多报一条「未消费」）；一条已过期的归因注释 |

**交接信息现在写的是异常链，不是最外层那一个。** 真实的连接重置以 `httpx2.ReadError('')` 抵达，一路到第四环才出现 `OSError: [Errno 104] Connection reset by peer`——只印最外层等于什么都没说。链的走法与 `app.streaming.sse` 一致（`__cause__` 优先，`__context__` 仅在未被抑制时跟进），环数与每环字符数都有上限。

**`internal` 在错误分支上已不可发。** 见本文上一节的更正块与 [`README.md`](README.md)。

**两个入口**：可续失败且已交付过块；以及上游干净收尾但 `stop_reason` 说它没写完（`max_tokens`）。后者不经异常路径，所以单独判。

**category 从 `RetryReason` 映射**而非二次分类——`classify_error` 不认识 pipeline 的异常类型，传输撕裂在它那里是 `internal`，而重放路径看同一个事件叫 `network`。一件事两套分类必然打架。

**三条既有测试原本断言这些结局会抛异常**，它们钉的是被文档改掉的行为；各自保留原主题（守卫有没有按时触发），改断言新的结局。

原计划条目：

本节每一条都有出处：写进人写文档的见该文档，只存在于 2026-08-21 讨论中的见 [`decisions.md`](decisions.md) 第二节，属本项目推论而非裁决的见其第三节（「两条上游腿都适用」是推论）。

- `status:"incomplete"` 的块丢弃规则：**有任何完整块才丢；只有未完成块则保留**（保留半截内容优于给客户端一个空回答）。reasoning item 无此字段，不处理。
- 合成 `tool_use` 块调用 `turn_interrupted(num_messages, category, message)`；`num_messages` 取**客户端请求**的 `messages` 长度。
- 检查入站 `tools[]` 是否含该工具；没有则**打 warning 但照发**。
- 配置项 `upstream_request_retry.auto_retry_tool_call_full_name` 可覆盖工具全名。
- 仅在 **anthropic-messages 客户端请求**上生效；两条上游腿都适用。
- `max_tokens` 一律走合成，不回落到无痕重试。
- 观测面：**客户端请求算成功，本次上游尝试算失败**，请求行记 `[RETY]` + 黄色。
- `usage` 报失败 attempt 实报值。

**跨仓依赖**：`num_messages` 的判法需与改 MCP 的同伴对齐——建议按「同一数值重复出现」而非「数值有没有增长」，因为并行子智能体与主会话共享同一个 MCP server 进程，调用会交错。两边不一致这个参数就白加。

## 几条不必再写进代码的顾虑

- **`usage` 排除在 token 校准之外**——不需要，而且理由比原先写的更强。live 链路的校准在 `server/handler.py:301-303`（`pipeline_app.py:43` 引入），它**只在 `count_tokens` 端点里学**：拿本地估算配上游 `count_tokens` 的答案，**根本不读消息响应的 `usage`**。读 `usage` 的那个 `TokenCalibrationSuccessObserver`（`app/hooks/builtin/token_calibration.py:53-65`）在未挂载的 legacy 侧，不参与。加之用户已裁决 `count_tokens` 不走续写，应用侧也没被碰到。
- **MCP-driven 续写的次数上限**——不设。用户 2026-08-21 裁决：会触发这条路就说明事情有进展。门本身（已交付过至少一个完整块）保证零进展的一轮到不了这里。
- **被截断 tool call 的 `{"__raw": …}` 参数**——由 E 的丢弃规则顺手解决。另有实测旁证表明 Claude Code 自己有 `safeParseJSON` → `{}` → zod → `is_error` 的原生恢复链，所以它本来也不是必须修的危害。

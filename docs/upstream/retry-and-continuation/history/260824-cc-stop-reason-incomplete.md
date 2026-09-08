# Claude Code 收到 `stop_reason: "incomplete"` 时会怎样

> 调查日期：2026-08-24。主仓 HEAD `0f2e7f1`。
> 被测客户端：Claude Code **2.1.241**（`claude --version` 实测，与 `~/.claude/refs/claude-code-2.1.241/` 抽取版本一致，`manifest.json` 记 `extractedAt: 2026-08-23`）。
> 本报告不修改仓库任何文件，唯一产物是本文件。

## 结论摘要

`"incomplete"` **不是** Anthropic Messages API 的合法 `stop_reason` 枚举值（anthropic SDK 1.0.0 一手实测），但 Claude Code 对 `stop_reason` **完全不做枚举校验**——SDK 的 SSE 解码器只做 `JSON.parse` 就把事件原样 yield，CC 自己的所有分支都是 `=== "refusal"` / `=== "max_tokens"` / `=== "tool_use"` 这类正向单值比较，没有 switch、没有穷举、没有会抛错的 default。
**实测把真实 CC 2.1.241 接到本地假上游验证：`"incomplete"` 与 `"end_turn"` 的结局一模一样**——内容完整交付、`is_error: false`、`num_turns: 1`、无重试、退出码 0，而且 `"incomplete"` 被原样写进 CC 自己的结果 JSON。连 `"totally_bogus_value_xyz"` 都照样成功。
唯一可观测的行为差异是一处**良性**的：`stop_reason` 不是 `end_turn`/`stop_sequence` 时，CC 的「回复无正文」补问分支不触发，因而少发一次上游请求。

**因此：默认值 `"incomplete"` 对 Claude Code 是安全的，不需要改。** 这也与 2026-08-22 用户裁决一致（见第 3 节）。

---

## 1. `"incomplete"` 是不是合法的 `stop_reason`

**答：不是。证据强度：实测（一手，读已安装 SDK 的类型定义）。**

```
$ uv run python -c "from anthropic.types import StopReason; print(StopReason)"
anthropic version: 1.0.0
anthropic path: /home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/anthropic/__init__.py
StopReason: typing.Literal['end_turn', 'max_tokens', 'stop_sequence', 'tool_use', 'pause_turn', 'refusal', 'model_context_window_exceeded']
```

合法取值共 7 个：

| 值 | 含义 |
|---|---|
| `end_turn` | 模型自然说完 |
| `max_tokens` | 撞上输出上限 |
| `stop_sequence` | 命中停止序列 |
| `tool_use` | 要调工具 |
| `pause_turn` | 长任务中途暂停（server tool 相关） |
| `refusal` | 安全拒答 |
| `model_context_window_exceeded` | 超上下文窗口 |

`"incomplete"` 不在其中。它是 **OpenAI Responses** 侧 `response.status` 的词（上游 Copilot 自己的词），被本项目当作合成兜底借用过来。

**顺带一条同源实测，关系到「别的客户端」**：Python SDK 的严格校验**会**拒绝它——

```
RawMessageDeltaEvent.model_validate({...'stop_reason':'incomplete'...})
  -> ValidationError: Input should be 'end_turn', 'max_tokens', 'stop_sequence', 'tool_use', 'pause_turn', 'refusal' or 'model_context_window_exceeded'
RawMessageDeltaEvent.construct(...)   -> OK, stop_reason='incomplete'
```

即：**宽容度是客户端特有的，不是协议给的。** Claude Code 不校验，一个用 Python SDK 且走 `model_validate` 路径的客户端会炸。本项目当前唯一在册的客户端是 Claude Code，所以这不构成阻断，但它是这条默认值真正的风险面所在，值得记下。证据强度：**实测**。

---

## 2. Claude Code 拿到枚举外的 `stop_reason` 会怎样

### 2.1 静态证据：全链路没有任何枚举校验

素材：`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js`（660403 行）。下文 `L<数字>` 均指该文件。凡 L58xxxx–L64xxxx 段落均为 bundle 内嵌的 `claude-api` skill 文档字符串，**不是可执行代码**，已在所有统计中排除。

**(a) SDK 的 SSE 解码器不做任何 schema 校验。** `L9326`–`L9358`，`fromSSEResponse` 的核心：

```js
if (a.event === "message_start" || a.event === "message_delta" || ... ) try {
  yield JSON.parse(a.data);
} catch (l) {
  throw o4.error("Could not parse message into JSON:", a.data), ... , l;
}
```

**唯一的失败模式是 JSON 语法错误。** 没有 zod、没有类型守卫、没有 Literal 校验。这条直接回答了任务里点名的那个担心：**CC 不会因为 SDK 层 schema 校验拒收整条 SSE 流**。证据强度：**实测（代码字面）**。

**(b) SDK 的消息累加器只做赋值。** `L13072`（另有 `L12092` 一份同形副本）：

```js
case "message_delta":
  if (r2.stop_reason = t4.delta.stop_reason, r2.stop_sequence = t4.delta.stop_sequence, ...)
```

裸赋值，无校验。证据强度：**实测（代码字面）**。

**(c) CC 自己的流消费者只做 null 检查。** `L429410`：

```js
if (Sr = wi.delta.stop_reason, Sr !== null) Br = true;
```

随后 `L429413` 把它原样传播到每条 assistant 消息上。证据强度：**实测（代码字面）**。

**(d) 全库不存在对 `stop_reason` 的 switch 或穷举。** 穷举 grep（排除文档段）后，代码里对 `stop_reason` 的**全部**比较只有这几种，且都是正向单值匹配：

| 位置 | 比较 | 用途 |
|---|---|---|
| `L10577` | `=== "end_turn"`（`stop_reason?.type`，SDK session 工具，另一条链路） | session idle 判定 |
| `L12279` | `=== "refusal"` | tool runner 中断 |
| `L312021` | `=== "max_tokens"` | thinking 块续写遥测 |
| `L312798` | `=== "tool_use"` | malformed tool use 检测（见 2.2） |
| `L312809` | `=== "end_turn" \|\| === "stop_sequence"` | 「回复无正文」补问门（见 2.2） |
| `L365938` / `L368469` / `L368477` / `L429116` / `L429118` | `=== "refusal"` | 安全拒答 fallback |
| `L408826` | `=== null` | 丢弃未完成的尾部 assistant 消息 |

`switch (…stopReason…)` 全库 **0 处**（`rg 'switch\s*\(\s*[A-Za-z0-9_$.]*[sS]top[Rr]eason'` 无匹配）。
唯一带 default 的分类器是遥测用的 `bam`（`L311580`），它把未知值折成 `"other"`：

```js
function bam(e, t4, r2) {
  if (e > 0) return "succeeded";
  if (t4 === "tool_use" && !r2) return "gave_up";
  if (t4 === "end_turn") return "end_turn";
  return "other";
}
```

`Ryr`（`L415461`，非流式路径的 stop_reason 处理器）第一行就是 `if (e !== "refusal") return;`——非 `refusal` 直接返回 `undefined`，无 default 动作。
遥测清洗函数 `io`（`L103`）是 `e == null ? void 0 : ERt(e)`，只挡 null，不是白名单。

证据强度：**实测（代码字面，穷举 grep）**。

**(e) 主 agent 循环的续跑判据是 `tool_use` 内容块，不是 `stop_reason`。** `L312909` 把 `yt` 作为 `toolUseBlocks` 传下去，`yt` 由内容块收集而来（`L312609` 等）。所以一个非法 `stop_reason` **不会**影响 CC 要不要继续跑工具。证据强度：**实测（代码字面）**。

### 2.2 动态证据：把真 CC 接到假上游实跑

写了一个只有 40 行的本地假 Anthropic 端点（`/tmp/cc-stopreason/fake2.py`，仅监听 `127.0.0.1`，无外网、无凭据），发出一条形状完全合法的流：`message_start` → `content_block_start` → `content_block_delta("HELLO-FROM-FAKE-UPSTREAM")` → `content_block_stop` → `message_delta(stop_reason=<变量>)` → `message_stop`，并在服务端计数收到几次请求。

用 `claude -p "say hi" --settings <临时文件> --output-format json` 驱动真实 CC 2.1.241。

> **一个必须记下的坑**：`ANTHROPIC_BASE_URL` 走 shell 环境变量**不生效**——`~/.claude/settings.json` 的 `env` 块（`ANTHROPIC_BASE_URL: http://127.0.0.1:4141`）会覆盖它。第一次尝试因此把请求打到了既有的 4141 服务上（真实计费，CC 自报 `total_cost_usd: 0.2315`），拿到的是真上游的回答而不是假上游的。必须用 `--settings <文件>` 才能压过去。**未对 4141 服务做任何 signal／停止／重启／接管，仅发出了一次普通查询。** 如实登记这次误打。

结果（`num_turns`／`upstream requests` 是判「有没有重试」的判据）：

| 场景 | `is_error` | `stop_reason`（CC 自报） | `num_turns` | `terminal_reason` | 上游请求数 | 退出码 | `result` |
|---|---|---|---|---|---|---|---|
| `end_turn`（基线） | `False` | `'end_turn'` | 1 | `completed` | 1 | 0 | `HELLO-FROM-FAKE-UPSTREAM` |
| **`incomplete`** | **`False`** | **`'incomplete'`** | **1** | **`completed`** | **1** | **0** | **`HELLO-FROM-FAKE-UPSTREAM`** |
| `totally_bogus_value_xyz` | `False` | `'totally_bogus_value_xyz'` | 1 | `completed` | 1 | 0 | `HELLO-FROM-FAKE-UPSTREAM` |
| `tool_use` 但无 tool_use 块（**控制组**） | `True` | `'stop_sequence'` | 2 | `malformed_tool_use_exhausted` | **2** | 1 | `The model's tool call could not be parsed (retry also failed).` |
| `message_delta` 的 data 非法 JSON（**控制组**） | `True` | `'stop_sequence'` | 1 | `api_error` | 1 | 1 | `API Error: JSON Parse error: Expected '}'` |

**读法**：

- `incomplete` 与 `end_turn` **逐字段相同**：内容完整、无错、无重试、退出 0。
- **`"incomplete"` 被原样透传进 CC 自己的结果 JSON**（`"stop_reason":"incomplete"`）——它既没被拒绝，也没被归一化。
- 连一个纯属捏造的 `totally_bogus_value_xyz` 也照样成功，这是「无枚举校验」最直接的证伪性证据。

**这个绿有分辨力**——两个控制组证明了这套 harness 抓得住失败：

- `tool_use` 无块 → **上游请求数从 1 变成 2**，`is_error=True`，`terminal_reason: malformed_tool_use_exhausted`。这正是 `L312798` 那个分支读出来的行为，代码与实跑互相印证。说明 harness **能观测到重试**。
- 非法 JSON → `is_error=True`，`API Error: JSON Parse error`。说明 harness **能观测到拒收**，也印证了 (a) 里「唯一失败模式是 JSON 语法错误」。

证据强度：**实测（一手，真实 CC 二进制 + 计数式判据 + 正反双向控制）。强到可以据此行动。**

### 2.3 唯一的行为差异：一处良性的少发一次请求

`L312809` 的门：

```js
let Zr = xr?.message.stop_reason ?? mt;
if ((Zr === "end_turn" || Zr === "stop_sequence") && !xr?.isApiErrorMessage && ... && !bt.some((Oo) => Oo.message.content.some((qs) => qs.type === "text" && qs.text.trim().length > 0)) && ...) {
  // 补问一次：塞一条 meta 消息 JAaa 再 continue
}
```

即「回合结束了但一个字正文都没有」时，CC 会补问一次。这道门**只认 `end_turn` 与 `stop_sequence`**，所以 `"incomplete"` 走不进去。

实测验证（正文置空，其余不变）：

| 场景 | `num_turns` | 上游请求数 | `is_error` | `terminal_reason` |
|---|---|---|---|---|
| 空正文 + `end_turn` | 2 | **2**（补问了） | `False` | `completed` |
| 空正文 + `incomplete` | 1 | **1**（没补问） | `False` | `completed` |

**判断：这是差异，不是缺陷。** 两者都以 `is_error: False` / `completed` 收场；`incomplete` 只是少浪费一次上游调用。而且我们这条链路上触发它的前提（干净 EOF、块边界、且交付的块全无正文）本就极罕见。证据强度：**实测**。

### 2.4 与 `usage: {"output_tokens": 0}` 有关的一个副作用

合成帧配的 `usage: {"output_tokens": 0}`（`formats/anthropic_messages.py:243`）会让 CC 把这一回合的输出记成 0 token、成本记成近似 0。实测 `incomplete` 场景 CC 自报 `output_tokens: 0`、`total_cost_usd: 1.5e-05`。**这是客户端侧的计量失真，不是错误**，且该取舍已在 `deferred.md` §5之二 被评审复核并有意保留（协议要求该键必填，零是唯一合法占位）。证据强度：**实测**，处置已裁决，本报告不重开。

---

## 3. 项目内已有的记录与裁定

**有，而且用户已经就这一点下过裁决。这是最高权威，本报告完全支持它，不提议推翻。**

### 3.1 用户裁决（2026-08-22）

`.dev/docs/upstream/retry-and-continuation/deferred.md:47`：

> ~~上游干净 EOF 但无终止事件 → 发 SSE `error`。~~ **裁决：细化。** 判断装配器有没有未完成的草稿——**落在块边界（无草稿）就不报错，正常收尾**；**切穿了某个块才算截断**，保持 error 帧。收尾用的 `stop_reason` 是一次合成，因此**做成了配置项** `client_delivery.unterminated_stream_stop_reason`，默认 `incomplete`（上游自己的词），可填 `end_turn`，**留空则整个细化关掉**、退回原行为。守住的不变量没变：**绝不把上游没说完的回合打扮成它说完了**——`end_turn` 不会被默默用上。

同文件 `:83` 记有出口：「想『不说谎』的操作员已有出口：`unterminated_stream_stop_reason` 留空 → 回到 error 帧，根本不发 `message_delta`。」

**本调查的结果与该裁决不冲突，而且补上了它当时缺的那块证据**：裁决选 `incomplete` 的理由是「上游自己的词」（诚实性），而当时**没有任何证据说明客户端吃不吃得下它**。现在有了：Claude Code 吃得下，且与 `end_turn` 无异。

### 3.2 其他已有记录

| 文件 | 内容 | 与本题的关系 |
|---|---|---|
| `.dev/docs/server-layout/reports/260823-error-surface-inventory.md:39`（E12） | 记录了「上游块边界干净 EOF → `message_delta(stop_reason:"incomplete")` + `message_stop`，**看起来像正常收尾**」，标注为实测 | 观测到了同一现象，但关心的是**可观测性**（失败被伪装成成功），不是客户端解析 |
| `.dev/docs/server-layout/reports/260823-error-surface-inventory.md:195` | 指出代码注释「与撕裂不可区分」已不成立，现在是「与**成功**不可区分」 | 同上，是可观测性问题 |
| `.dev/docs/error-envelope/spec.md:100-102` | 已把上面那条写进 spec：客户端收到「语法上完全正常的收尾」 | 同上 |
| `.dev/docs/error-envelope/reports/260824-claude-code-sse-retry-behavior.md` | 今天新写的 CC 2.1.241 重试行为考古，非常详尽 | **不覆盖本题**。它查的是「流内 `event: error` 帧与连接失败怎么触发重试」，一个字没提枚举外 `stop_reason`。两份互补，不重复 |
| `.dev/docs/upstream/retry-and-continuation/deferred.md:121`（§6） | 裁决不给 `Terminal` 加承载 `incomplete_details.reason` 的字段，因为 `stop_reason` 已原样携带该事实 | 说明 `stop_reason` 携带上游原词是**有意设计**，不是疏漏 |

### 3.3 一个顺带发现的文档缺口（只报告，不动手）

`client_delivery.unterminated_stream_stop_reason` 是一个**面向操作员的配置项**（代码注释原话：「it is an operator's setting」，`stream.py:114`），但它**不在** `docs/.human-controlled/config.example.yaml` 的 `client_delivery` 段里（实测：该文件 `unterminated` 零匹配，`client_delivery` 段列的是 `client_request_deadline` / `buffering_policy` / `buffer_cap_bytes` / `sse_ping_interval` / `hedge`）。

`docs/.human-controlled/` 由用户亲笔，**我不修改**。按项目约定，候选材料应写入 `.dev/human-controlled-docs-candidates/`。**本报告只登记这个缺口，未写候选、未改任何文件**，留给主会话裁量。证据强度：**实测**。

### 3.4 任务描述里两处需要更正的细节

1. **行号已漂移**。任务说 `stream.py:463-475`，实际在 HEAD `0f2e7f1` 上是 **`stream.py:473-481`**。
2. **一处语义遗漏，而且是重要的**。任务说合成值会被写进 `message_delta`，但实际表达式是

   ```python
   replace(terminal, stop_reason=terminal.stop_reason or settings.unterminated_stop_reason)
   ```

   **上游自己给过 `stop_reason` 时，上游的值优先**，配置的合成值只在上游什么都没说时才用。代码注释明确写了理由（Anthropic 腿把结局拆成 `message_delta` + `message_stop` 两半，只丢后一半的流其实已经说了为什么停）。所以 `"incomplete"` 实际落到 wire 上的窗口，比任务描述给人的印象更窄。证据强度：**实测（读码）**。

---

## 4. 排除清单（查了没查到 / 考虑过又否决的）

**查了但没查到的：**

1. **CC 里对 `stop_reason` 的 zod schema / 类型守卫** —— 不存在。SDK 只 `JSON.parse`（`L9344`-`L9348`）。已用「非法 JSON」控制组反证 harness 抓得住这类拒收。
2. **`stop_reason` 值的 Set / 数组常量** —— 全库 0 处。grep `["end_turn"` 与 `"end_turn", "…"` 等形状只命中 `L307431` 一个完全无关的请求字段名列表。
3. **`switch` on stop_reason** —— 0 处。
4. **2.1.226 里有一个 `oZs(g.stop_reason) ? "truncated" : …` 的分类器（`L235217`）** —— 在 **2.1.241 中已消失**（`"truncated"` 在 241 里只剩一处无关 UI 命中，`L542224`）。**因为已确认用户实际运行的就是 2.1.241，本报告不再深挖 226 的那个分支。** 这是一条明确的范围限定：**结论只对 2.1.241 成立**，若将来降级到 2.1.226，这一处需重查。
5. **`docs/.human-controlled/` 里对本问题的裁定** —— 无。`upstream-retry-and-continuation.md` 只谈 `refusal` 与 `max_tokens`，未涉及无终止事件的合成收尾。用户的相关裁决记在 `deferred.md`，不在人写文档里。

**考虑过又否决的路线：**

1. **重跑 `unbun` 抽取 CC 源码** —— 否决。`~/.claude/refs/` 下已有 2.1.241 现成的 `app.pretty.js`，且 `manifest.json` 的版本与 `claude --version` 实测一致，无需重抽。
2. **只靠读码下结论，不实跑** —— 否决。读码能证明「没有校验」，但证明不了「实际结局与 end_turn 无异」（还有 `L312809` 那类间接分支）。实跑成本极低（本地回环、无凭据、单次数百毫秒），且是唯一能产生反证性控制组的办法。
3. **用 `pkill -f` 清理探针进程** —— 否决，**并且是踩了才改的**。`pkill -f 'fake_anthropic.py'` 会匹配到我自己那次 Bash 调用的命令行（heredoc 里含该字符串），**把自己的 shell 杀掉**，导致后续 heredoc 从未执行、文件从未写出，症状要到下一步才显形。改用记录 `$!` 后按 PID kill。收尾已实测确认无残留：`ss -ltnp` 在 8791/8792 上无监听，`pgrep -af cc-stopreason` 为空。
4. **测试 thinking-only 响应下的补问分支** —— 否决（改用等价替代）。thinking 块需要合法 signature，构造成本高且可能被 CC 另行拒绝。改用「空正文 text 块」触发同一道门（`L312809` 的条件是「无非空 text」，thinking-only 只是它的一个特例），已得到干净的双向对照，见 2.3。
5. **顺手把 `unterminated_stream_stop_reason` 补进 `config.example.yaml`** —— 否决。该文件是用户亲笔的最高权威，不得擅改；只登记缺口（§3.3）。
6. **建议把默认值从 `incomplete` 改成 `end_turn`** —— 否决。(a) 用户 2026-08-22 已明确裁定默认 `incomplete`，并写明「`end_turn` 不会被默默用上」是要守的不变量；(b) 实测证明 `incomplete` 对 CC 无害，改动没有收益，只有推翻用户裁决的代价。
7. **测试非流式（`stream: false`）路径** —— 未做，**如实标为未验证**。本项目这条合成路径只在流式交付（`_deliver`）上可达（`stream.py` 的 `stream_delivery`），非流式另有其路，不产出这个帧。故不在本题范围内。

**空清单显式声明：** 除上述之外，无其他被排除的路线。

---

## 5. 一句话建议

**不需要改任何东西。** 默认 `"incomplete"` 对 Claude Code 2.1.241 安全（实测），与用户 2026-08-22 裁决一致，且本报告为该裁决补上了它当时缺的客户端侧证据。

唯一值得主会话裁量的两件小事，都不阻断：

1. `client_delivery.unterminated_stream_stop_reason` 未出现在 `docs/.human-controlled/config.example.yaml`（§3.3）——要不要写一份候选材料给用户。
2. 「非 CC 客户端可能严格校验」这条风险（§1 末，Python SDK `model_validate` 实测会 raise）——目前在册客户端只有 CC，但若将来支持别的客户端，这是第一个会崩的地方。这条事实建议落进 `.dev/docs/upstream/retry-and-continuation/deferred.md` 第 5 条那一段的近旁，因为它是那条裁决的直接限定成分。

## 附：可复现的探针

- 假上游：`/tmp/cc-stopreason/fake2.py`（参数：`<scenario> <port>`；scenario 取 `end_turn` / `incomplete` / 任意字符串 / `tool_use_no_block` / `malformed_json`，加 `emptytext_` 前缀则正文置空）
- 驱动：`claude -p "say hi" --settings <含 env.ANTHROPIC_BASE_URL 的 json> --output-format json --model claude-sonnet-4-5 < /dev/null`
- **必须用 `--settings`**，shell 环境变量会被 `~/.claude/settings.json` 的 `env` 块压掉（§2.2 的坑）。
- 探针在 `/tmp` 下，非仓库内容，未提交。

# 上游实测：tool description 空值与 `system[0]` attribution 行的接受度

- 日期：2026-08-21
- 仓库 HEAD：`b71e83d08d9772896b0c703e4133414f51bd4f6a`
- 上游：`https://api.githubcopilot.com`（individual），凭据取自 `~/.local/share/ghc-api-proxy/github_token`，走 `CopilotTokenManager` 真实换取 Copilot token
- 探针脚本：`/home/xp/.claude/jobs/89874ec2/tmp/probe.py`、`probe2.py`、`probe3.py`、`probe4.py`；原始结果 `results.jsonl` ~ `results4.jsonl`（同目录）
- 全部为真实请求，无 mock、无 cassette、无推理填空。共 54 次上游推理调用（probe1 12 + probe2 14 + probe3 7 + probe4 21），另有 token 交换与一次 `/models` 目录拉取，prompt 一律是 `Reply with exactly one word: PONG`。

---

## 0. 正样本对照（先证明探针真的跑了）

换取 Copilot token 第一次尝试返回 `403 Forbidden`（`https://api.github.com/copilot_internal/v2/token`），原因是没带 identity headers；按 `composition.py:379-383` 补上 `build_identity_headers()` 后成功。这一段本身就是探针可用性的第一道证据：探针能区分「拿不到凭据」和「上游拒绝」。

正样本 `P0-control-normal`，`POST /responses`，模型 `gpt-5.6-terra`：

请求体：

```json
{"model": "gpt-5.6-terra", "input": [{"role": "user", "content": [{"type": "input_text", "text": "Reply with exactly one word: PONG"}]}], "stream": false, "max_output_tokens": 32, "instructions": "You are a terse assistant.", "tools": [{"type": "function", "name": "get_weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": false}, "description": "Do a thing."}]}
```

响应：`HTTP 200`，`output_text = ["PONG"]`，响应体带 `copilot_usage`（input 58 / output 6 token）。

**探针的分辨力另有一处正面证据**：同一批里的 `Q1-6`（`description` 为整数 `123`）拿到了 `HTTP 400` 并带上游原话错误体。也就是说，这套探针在同一条代码路径上既能拿到 200 也能拿到 400，后面所有 200 都不是「探针坏了所以什么都没发生」。

---

## 1. Q1：Responses 上游是否拒绝「存在但为空」的 tool description

`POST /responses`，模型 `gpt-5.6-terra`，其余字段与正样本一致，只改 `tools[0].description`。

| 变体 | `tools[0].description` | 状态码 | 上游响应 |
|---|---|---|---|
| Q1-1 | 键完全不存在 | 200 | `output_text = ["PONG"]` |
| Q1-2 | `""` | 200 | `output_text = ["PONG"]` |
| Q1-3 | `"   "` | 200 | `output_text = ["PONG"]` |
| Q1-4 | `"Do a thing."`（对照） | 200 | `output_text = ["PONG"]` |
| Q1-5 | `null` | 200 | `output_text = ["PONG"]` |
| Q1-6 | `123`（整数） | **400** | `{"error":{"message":"Invalid type for 'tools[0].description': expected a string, but got an integer instead.","code":"invalid_request_body"}}` |

### 跨模型复核（是否模型相关）

同样四种空值形状（omit / `""` / `"   "` / `null`）在其他模型上重跑：

| 模型 | omit | `""` | `"   "` | `null` | 备注 |
|---|---|---|---|---|---|
| `gpt-5.5` | 200 | 200 | 200 | 200 | |
| `gpt-5.6-luna` | 200 | 200 | 200 | 200 | |
| `grok-4.6` | 200 | 200 | 200 | 200 | |
| `gemini-3.6-flash` | 400 | 400 | 400 | 400 | 与 description 无关：`{"error":{"message":"model gemini-3.6-flash does not support Responses API.","code":"unsupported_api_for_model"}}` |
| `gpt-4.1` | 400 | 400 | 400 | 400 | 同上：`{"error":{"message":"model gpt-4.1 is not supported via Responses API.","code":"unsupported_api_for_model"}}` |

两个 400 是**端点级**拒绝（模型根本不支持 Responses API），四种形状返回完全相同的错误体，与 `description` 无关。

### 模型层是否照单全收

`forced-tool-choice-empty-description`：`description: ""` 的工具 + `tool_choice: {"type":"function","name":"get_weather"}`，prompt 改为 `What is the weather in Paris?`。

结果 `HTTP 200`，输出 `function_call: {"name": "get_weather", "arguments": "{\"city\":\"Paris\"}"}`。空 description 的工具能被正确调用、参数正确。

### Anthropic 直连路径对照

`POST /v1/messages`，模型 `claude-sonnet-5`：`M6`（工具无 `description` 键）与 `M7`（`description: ""`）均 `HTTP 200`，`content = ["PONG"]`。

**Q1 结论**：Responses 上游对 `tools[].description` 只做类型校验。缺键、空串、纯空白、`null` 全部接受；只有非字符串且非 `null` 的类型被拒。`null` 与「缺键」等价——它没有触发 `expected a string` 那条错误，说明网关把 `null` 当作未提供。

---

## 2. Q2：`system[0]` / `instructions` 里的 attribution 行

固定文本：

- `ATTRIBUTION` = `x-anthropic-billing-header: cc_version=1.0; cc_entrypoint=cli;`
- `OTHER_HEADER` = `x-some-other-header: foo=bar;`
- `HTTP_LOOKING` = `Content-Type: text/plain`
- `PLAIN_SYSTEM` = `You are a terse assistant.`
- `CC_SYSTEM` = `You are Claude Code, Anthropic's official CLI for Claude.`

### (a) 翻译路径：作为 Responses 的 `instructions`

`POST /responses`，模型 `gpt-5.6-terra`。

| 变体 | `instructions` 内容 | 状态码 | 上游响应 |
|---|---|---|---|
| Q2a-1 | `ATTRIBUTION` + `\n` + `PLAIN_SYSTEM` | 200 | `["PONG"]` |
| Q2a-2 | `OTHER_HEADER` + `\n` + `PLAIN_SYSTEM` | 200 | `["PONG"]` |
| Q2a-3 | `HTTP_LOOKING` + `\n` + `PLAIN_SYSTEM` | 200 | `["PONG"]` |
| Q2a-4 | `PLAIN_SYSTEM`（对照） | 200 | `["PONG"]` |
| Q2a-5 | 只有 `ATTRIBUTION`，没有别的 | 200 | `["PONG"]` |
| C6 | `ATTRIBUTION` + `\n` + `CC_SYSTEM`，`stream: true` | 200 | 正常 SSE，首帧 `event: response.created` |
| C4 | `instructions` 干净，但把 `x-anthropic-billing-header` 作为**真实 HTTP 请求头**发出 | 200 | `["PONG"]` |

### (b) 直连路径：作为 Anthropic `system[0]`

**这条路径当前可达**：`POST https://api.githubcopilot.com/v1/messages`，模型 `claude-sonnet-5`，带 `anthropic-version: 2023-06-01` 与本项目的 identity headers，正样本 `M0` 返回 200。

（附带确认：`claude-sonnet-5` **不支持** Responses API——`R0`~`R5` 六个变体一律返回 `{"error":{"message":"model claude-sonnet-5 does not support Responses API.","code":"unsupported_api_for_model"}}`。所以 Claude 系模型在本机上游只有直连路径可走，这一条与 attribution 无关，但影响「翻译路径能覆盖哪些模型」的判断。）

| 变体 | `system` 形态 | 状态码 | 上游响应 |
|---|---|---|---|
| M0 | `[{"type":"text","text": PLAIN_SYSTEM}]`（对照） | 200 | `["PONG"]` |
| M1 | `[{"type":"text","text": ATTRIBUTION + "\n" + PLAIN_SYSTEM}]` | 200 | `["PONG"]` |
| M2 | 同上但换成 `OTHER_HEADER` | 200 | `["PONG"]` |
| M3 | 同上但换成 `HTTP_LOOKING` | 200 | `["PONG"]` |
| M4 | `[{"type":"text","text": ATTRIBUTION}]`（只有属性行） | 200 | `["PONG"]` |
| M5 | attribution 独立成 `system[0]`，`PLAIN_SYSTEM` 为 `system[1]` | 200 | `["PONG"]` |
| C2 | Claude Code 真实形状：`system[0]` = `ATTRIBUTION\nCC_SYSTEM` + `cache_control: {"type":"ephemeral"}` | 200 | `["PONG"]` |
| C5 | `system` 为**纯字符串** `ATTRIBUTION\nCC_SYSTEM`（非数组） | 200 | `["PONG"]` |
| C3 | `system` 干净，attribution 作为真实 HTTP 头 | 200 | `["PONG"]` |

### (c) `count_tokens` 端点

`POST /v1/messages/count_tokens`，模型 `claude-sonnet-5`：

| 变体 | `system[0]` | 状态码 | 响应体原文 |
|---|---|---|---|
| C0 | `CC_SYSTEM` | 200 | `{"input_tokens":43}` |
| C1 | `ATTRIBUTION\nCC_SYSTEM` | 200 | `{"input_tokens":77}` |

**Q2 结论**：上游在**任何**测过的形态下都没有拒绝 attribution 行——不管属性名是 `x-anthropic-billing-header`、别的名字、还是像 `Content-Type` 这样的真 HTTP 头名；不管它在 `instructions`、`system[0]` 文本块、独立 system 块、纯字符串 system、还是作为真实 HTTP 请求头；不管流式还是非流式；`count_tokens` 也照收。

但它**不是没有代价**：C0 vs C1 显示，同一段 system 加上这一行 attribution，上游自己算出的 `input_tokens` 从 43 涨到 77，多 34 个 token。这是可测量的净损耗，且这行文本会原样进入模型的上下文。

---

## 3. Q3：失败发生在哪一层

本轮实测中唯一与「消毒规则」相关的失败是 `Q1-6`，发生在 **Copilot 网关的请求体校验层**，模型完全没被触及：

```json
{"error":{"message":"Invalid type for 'tools[0].description': expected a string, but got an integer instead.","code":"invalid_request_body"}}
```

`error.code = invalid_request_body`。

另外两类 400 也都在网关层，且与本次两个问题无关，是模型-端点匹配校验：

```json
{"error":{"message":"model claude-sonnet-5 does not support Responses API.","code":"unsupported_api_for_model"}}
{"error":{"message":"model gpt-4.1 is not supported via Responses API.","code":"unsupported_api_for_model"}}
```

`error.code = unsupported_api_for_model`。注意这两条的 `message` 措辞不同（`does not support` vs `is not supported via`），但 `code` 相同——要按 `code` 判别，不要按 `message` 匹配。

「模型照单全收但输出异常」这一支**没有观测到**：所有 200 的用例都返回了预期的 `PONG`，带 attribution 的用例也一样；空 description 的工具被强制调用时参数正确。

---

## 4. 判定

| 命题 | 判定 | 依据 |
|---|---|---|
| Responses 上游拒绝缺失 `description` 键的 tool | **已实测证否** | Q1-1、跨 3 个模型复核，均 200 |
| Responses 上游拒绝 `description: ""` | **已实测证否** | Q1-2、跨 3 个模型复核，均 200；强制 tool_choice 也能正常调用 |
| Responses 上游拒绝 `description: "   "` | **已实测证否** | Q1-3、跨 3 个模型复核，均 200 |
| Responses 上游拒绝 `description: null` | **已实测证否** | Q1-5、跨 3 个模型复核，均 200；`null` 被当作未提供 |
| Responses 上游拒绝非字符串类型的 `description` | **已实测确认** | Q1-6，400 `invalid_request_body`，上游原话见上 |
| 翻译路径上，`instructions` 里的 `x-anthropic-billing-header:` 行会被上游拒绝 | **已实测证否** | Q2a-1、Q2a-5、C6（流式）、C4（HTTP 头形态），均 200 |
| 直连路径上，`system[0]` 里的 attribution 行会被上游拒绝 | **已实测证否** | M1、M4、M5、C2（含 `cache_control`）、C5（字符串 system）、C3（HTTP 头形态），均 200 |
| 上游拒绝的是**任意** `key: value;` 形状的首行 | **已实测证否** | Q2a-2/Q2a-3、M2/M3 均 200 |
| `count_tokens` 端点拒绝带 attribution 的 system | **已实测证否** | C1，200 `{"input_tokens":77}` |
| 失败层级：网关而非模型 | **已实测确认** | 唯一相关失败 Q1-6 带 `code: invalid_request_body`，无响应体输出 |
| attribution 行对**模型输出质量**有影响 | **未能测得** | 见下方局限 |

### 局限（读这份报告时必须一并读）

1. **prompt 是 trivial 的，检测模型行为退化的分辨力极弱。** 所有用例都只要模型回一个词。「200 且返回 PONG」只能支撑「网关不拒、模型没崩」，**不能**支撑「attribution 行对模型行为无害」。真实 Claude Code 的 system prompt 有上万 token，一行噪声在那种规模下的影响本轮没测。
2. **单账号、单时点、individual 账户。** 结论对 `api.githubcopilot.com` 的 individual 端点、2026-08-21、上述模型目录快照成立。企业端点或网关升级后可能不同。
3. **每种变体只发了一次。** 按任务约定控制 token 消耗；这排除不了低概率的间歇性拒绝。
4. **没有测「历史上是否曾经拒绝」。** 本报告只能说现在不拒。人写文档写下那句断言的时点若早于某次网关放宽，两者可以同时为真。

### 一条旁证（弱，仅供参考，不作为判据）

`~/src/copilot-api-js/config.yaml:628-646` 里，`strip_attribution_header` 的注释把这条剥离描述为对客户端行为的处理与 `strip_request_headers` 的互补项，把 HTTP 头形态那一条明确标注为 `DEFENSIVE`，**通篇没有记录任何上游 400**。也就是说，上游项目自己的文档也没有为「GHC API 不认」留下证据。这只是旁证，真正的判据是上面 15 次带 attribution 的 200（Q2a-1/2/3/5、C1、C2、C3、C4、C6、M1~M5）。

---

## 5. 回答人写文档的 TODO

`docs/.human-controlled/message-format-sanitize.md:29`：

> TODO：用户想知道 GHC API 不认 `x-anthropic-billing-header:` 还是 GHC API 不认 `system[0]` 中的任何 attribution？

**实测答案：都不是。GHC API 两个都认。**

- 不是「不认特定名字」：`x-anthropic-billing-header:` 原样发出去，翻译路径（`instructions`）和直连路径（`system[0]`）都返回 200。
- 不是「不认任何 attribution 行」：换成 `x-some-other-header: foo=bar;` 或 `Content-Type: text/plain`，同样 200。
- 也不是「不认 HTTP 头形态」：把 `x-anthropic-billing-header` 作为真实请求头发给 `/responses` 和 `/v1/messages`，都是 200。
- `count_tokens` 也不拒。

所以该文档第 25 行的前提句「GHC API 不认，需要剥离」**与当前实测不符，需要修正**。

但这**不等于该剥离动作应当取消**——剥离仍有两条不依赖「上游拒绝」的理由，请用户裁决保留哪一条作为新的依据：

1. **token 净损耗**：实测 34 token/请求（`count_tokens` 43 → 77）。对每次请求都带它的 Claude Code 而言这是持续成本。
2. **prompt 卫生**：这行文本会原样进入模型上下文，是一行与任务无关的伪 HTTP 头。它对模型行为的实际影响本轮**未能测得**（见局限 1）。

另外本轮实测顺带发现一条与该文档相邻、但它没有记录的事实，建议一并纳入：**`claude-sonnet-5` 不支持 Responses API**（`code: unsupported_api_for_model`）。这意味着「Anthropic Messages → OpenAI Responses」的翻译路径无法承载 Claude 系模型，它们只能走 `/v1/messages` 直连。这条超出本次三个问题的范围，未展开验证其他 Claude 型号，交由主会话判断是否单独立项。

# 重复实现体检：同一语义写了两遍

- 仓库：`/home/xp/src/ghc-api-proxy-py`，分支 `main`，HEAD `44471c6ceedd8a06a7e0cca480314f8fc205e7c0`
- 日期：2026-08-14
- 轴线：只查「同一件事在代码里写了两遍，且其中一遍可能弱一档」。其他轴的发现只记一行标 `out-of-axis`。
- 只读审计：未修改 `src/`、`tests/` 或任何既有文件，未执行任何 git 写操作。本文件是唯一写入路径，探针脚本写在 `/tmp/`。

## 1. 结论摘要

- **找到 3 处已实测发生行为漂移的重复实现**，全部在「Anthropic Messages 入站 ← Responses 上游」这条主路径的 **流式 / 非流式** 之间。同一个上游响应，走 `stream:true` 与 `stream:false` 得到的结果在语义上不同（一个 200 一个 502，且两个用例的偏向方向相反）。这是本轮最高价值的发现，证据是可复现的进程内探针输出，见第 3 节。
- 漂移根因是同一条规则被写了两遍而非被复用：`Responses usage → Anthropic usage` 换算、`stop_reason` 判定、「`incomplete/max_output_tokens` 算不算成功」谓词、「空内容怎么处理」，在 `protocols/responses_anthropic.py`（非流式）与 `delivery/responses_anthropic_stream.py` + `delivery/anthropic_sse.py`（流式）各有一份，两份互不知道对方存在。
- 另有 2 处**结构性缺一半**：tool name 的 `restore()` 只在非流式一侧有接缝，流式一侧连接缝都没有；Gemini 的 `tool_call → functionCall` 转换流式一侧藏在 `routes/` 里、非流式一侧在 `protocols/` 里，且非流式那份对坏 JSON 会抛异常。
- 上游 exchange 层 `CopilotUpstream` / `GenericUpstream` 共 12 个方法覆盖 6 种调用形态，逐一手抄；12 个里只有 2 个（`send_responses_headers`）做了 `APIStatusError` 归一化，其余 10 个在上游非 2xx 时直接抛。已用 `httpx.MockTransport` 实测 openai 与 anthropic 两个 SDK 在 `cast_to=httpx.Response` 下均抛 `APIStatusError`。
- 路由层 `routes/openai.py::_response` 与 `routes/azure.py::_response` **逐字节相同**（31 行，`diff` 无输出）。
- 判为良性、不入表的形似重复也逐条写在 4.3，使「无发现」与「没扫」可区分。

## 2. 重复实现表

严重程度按「下一个复用者还会不会踩」判定，不按修复行数。

| # | 语义 | 实现 A | 实现 B（及 C/D） | 是否有害 | 差异 / 漂移证据 | 建议收敛层 |
|---|---|---|---|---|---|---|
| D1 | Responses `usage` → Anthropic `usage` 换算 | `src/app/protocols/responses_anthropic.py:214` `_convert_usage` | `src/app/delivery/responses_anthropic_stream.py:404` `_terminal_usage` | **有害（已漂移）** | 同一条算式 `input = max(0, total_input - cached - cache_write)` 写两遍。B 弱三档：① `input_tokens_details` 不是对象时 A 报 `invalid_response`，B 静默当空字典（`:425-430`）→ 实测漂移，见 3.3；② A 产出 `usage_inconsistent` 事实（`:244-258`），B 无；③ A 保留 `reasoning_tokens` 与完整 details（`ResponseUsageFacts`），B 的 `TerminalUsage` 只有 4 个字段，reasoning token 直接丢弃 | 抽出单一 `ResponsesUsage.from_wire()` 值对象，A/B 都从它派生；`TerminalUsage` 由该对象投影而非并列定义 |
| D2 | `stop_reason` 判定 | `src/app/protocols/responses_anthropic.py:130`（只有 `tool_use` / `end_turn`） | `src/app/delivery/responses_anthropic_stream.py:276-282`（有 `max_tokens` / `tool_use` / `end_turn`） | **有害（已漂移）** | A 根本没有 `max_tokens` 分支，因为 A 在 `:84-88` 先把 `status != "completed"` 一律判死。实测同一份 `incomplete/max_output_tokens` 响应：非流式 502，流式 200 + `stop_reason:"max_tokens"`。见 3.1 | 把「terminal → (是否成功, stop_reason)」提成一个纯函数放在 `protocols/` 层，两条路径共用 |
| D3 | 「`incomplete` + `max_output_tokens` 算成功终态」谓词 | `src/app/delivery/anthropic_sse.py:756-759` | `src/app/delivery/responses_anthropic_stream.py:267-273` 与 `:276-281`（同一文件内还写了两遍） | **有害（未漂移，但三副本）** | 同一个谓词 3 份字面量。将来若第二种 incomplete reason（如 `max_tool_calls`）也要算成功：改漏 delivery 那份 → `ResponsesDeliveryError`；改漏 stream 那份 → `stop_reason` 错 | 与 D2 合并到同一个 terminal 分类函数 |
| D4 | 空内容响应的处置 | `src/app/protocols/responses_anthropic.py:121-122`（补一个空 text block，返回 200） | `src/app/openai/responses_stream_parser.py:510-517`（转成 `incomplete/empty_response_content`，最终 502） | **有害（已漂移，方向相反）** | 同一份 content 为空的 message 项：非流式 200 + `content:[{"type":"text","text":""}]`；流式 `ApiError: response completed without content`。见 3.2。两条路径对「上游给了空内容」这件事做了独立且相反的产品裁决 | 先由用户 / ADR 裁定哪一侧是正确语义，再收敛到 `protocols/` 层单一判定。本条落在 `check-existing-decisions-before-changing-behavior` 范围，**不应由实现者自行统一** |
| D5 | tool name 还原（wire name → 原始 name） | `src/app/protocols/responses_anthropic.py:202` `mapper.restore(name)` | 流式无对应实现：`src/app/delivery/anthropic_sse.py:525` 与 `src/app/delivery/responses_anthropic_stream.py:147` 都直接用 `content.name` | **有害（潜伏）** | 不是两份实现不同，是**只有一份**。今天两边等价，因为 `anthropic/client.py:250,285` 谁也没把 mapper 传下去，`restore()` 未 bind 时恒等（`protocols/anthropic_responses.py:133-136`）。一旦启用 tool name 映射，非流式会还原、流式返回 wire name。判别句「下一个复用者还会踩吗」：会 | mapper 随请求上下文流到 delivery 层；或把「还原」放进 `CompletedBlock → Anthropic block` 的唯一投影函数里 |
| D6 | `CompletedBlock` → Anthropic content block 投影 | `src/app/delivery/anthropic_sse.py:487` `_block_events`（渲染成 SSE 事件序列） | `src/app/delivery/responses_anthropic_stream.py:141` `_project_block`（渲染成历史 JSON） | **有害（中）** | 同一语义块的三种内容类型各写两遍。差异：thinking 在 A 是 `thinking:""` + delta（`:544-571`），在 B 是直接 `thinking: content.summary`（`:152-156`）；tool_use 的 `input` 在 A 走 `partial_json` 原样字符串（`:530-540`）、在 B 走 `orjson.loads`（`:148`）；A 校验 arguments 解出来是 dict（`:513-514`），B 直接 `cast`。D5 漏还原正是从这条缝里漏的——两份都得改才生效 | 单一 `block_to_anthropic_content(block) -> dict`；SSE 渲染器从这个 dict 派生事件，历史投影直接用它 |
| D7 | 「function-call arguments 必须是合法 JSON 且解出对象」 | `src/app/openai/responses_stream_parser.py:658` `_validate_tool_arguments_object` | `src/app/protocols/responses_anthropic.py:185-198`；`src/app/delivery/anthropic_sse.py:512-514`；`src/app/delivery/responses_anthropic_stream.py:148` | 中等（4 副本，错误类型各异） | parser 抛 `ResponsesStreamProtocolError(invalid_tool_arguments)`；protocols 抛 `ResponseConversionError(invalid_tool_arguments)`；`anthropic_sse` 抛裸 `ValueError` 且**不捕 `JSONDecodeError`**；stream 投影**完全不校验**。流式链路上 parser 已校验过，后两份是冗余防御，但错误类型不一致意味着同一个坏输入在不同入口给出不同 wire code | 一个共享校验 / 解析 helper（返回 typed 结果）；parser 是唯一 gate，渲染与投影信任 typed fact |
| D8 | SSE 帧解析 | `src/app/streaming/openai_sse.py:6` `parse_sse_json` | `src/app/streaming/anthropic_usage.py:13` `AnthropicSSEUsageTap.feed` | **有害（潜伏）** | 两份手写 SSE 帧解析器。B 弱：只认 `data: `（带空格，`:21`），A 认 `data:` 与 `data: `（`:44-48`）；SSE 规范里那个空格是可选的。B 用在 `routes/anthropic.py:49`，对**原生 Anthropic 直通**那条腿吃的是上游字节；上游若发 `data:{...}` → usage tap 静默返回空 usage → 历史与 hooks 拿到 0。B 也不认 `[DONE]` | 收敛到一个 SSE 帧解析器（或换成成熟库 `httpx-sse` / `sse-starlette` 的解析侧），usage tap 建在它之上 |
| D9 | 上游 exchange 形态 | `src/app/upstream/copilot.py:94-176`（6 个方法） | `src/app/upstream/generic.py:25-102`（同样 6 个方法） | **有害** | 12 个方法覆盖 6 种形态，逐一手抄，唯一实质差别是 Copilot 注入 `await self._headers()`。12 个里只有 2 个 `send_responses_headers`（`copilot.py:148` / `generic.py:76`）做了 `APIStatusError → response` 归一化与传输错误分类，其余 10 个非 2xx 直接抛（探针见 4.2） | 一个基类持 6 个方法，子类只覆写「如何生成 options/headers」；错误归一化下沉到基类，所有形态统一 |
| D10 | 协议路由的响应收尾 | `src/app/routes/openai.py:26-56` `_response` | `src/app/routes/azure.py:22-52` `_response` | **有害（低风险高确定性）** | `diff` 逐字节相同（31 行）。Azure 路由本就把请求适配成 OpenAI 形态，没有理由持第二份 | 移到 `src/app/routes/protocol_history.py`（`history_stream` 已在那里）或一个共享 `routes/_protocol_response.py`，两个路由 import |
| D11 | OpenAI `tool_call` → Gemini `functionCall` | `src/app/routes/gemini.py:70-83`（流式，`loads` 失败降级为 `{"raw": ...}`） | `src/app/protocols/gemini.py:126-134` `_tool_call_part`（非流式，`json.loads` 无 try） | **有害** | 同一转换两份，且分层不一致：流式那份写在 `routes/` 里。非流式弱一档：上游返回不合法 arguments JSON 时 A 降级、B 抛 `JSONDecodeError`。另外流式帧从不带 `usageMetadata`，非流式带（`protocols/gemini.py:118-122`）——同一协议的 usage 语义只实现了一半 | 流式那份搬进 `protocols/gemini.py`，两条路径共用一个 `_tool_call_part` 与一个 usage 投影 |
| D12 | Responses 终态事件集合 | `src/app/openai/responses_ws.py:7-14` `TERMINAL_EVENTS` | `src/app/openai/responses_stream_parser.py:215-220` 同一组字面量 | 中等 | 同一组 4 个事件类型写两遍，HTTP 腿与 WS 腿各一份。上游新增终态事件时必然只改一处 | 提成一个模块级常量，parser 与 WS 客户端共用 |
| D13 | Anthropic error 信封 `{"type":"error","error":{...}}` | `src/app/streaming/sse.py:121-129` | `src/app/routes/anthropic.py:131-141`；`src/app/delivery/anthropic_sse.py:460-467`；`src/app/anthropic/client.py:452-459` | 中等（4 副本，字段集不一致） | 前两份带 `request_id`，后两份不带；后两份带 `code`。同一个 `ApiError` 从不同出口出去，客户端看到的字段集不同 | 一个 `anthropic_error_payload(ApiError) -> dict`，4 处共用 |
| D14 | 「Anthropic 总输入 = input + cache_read + cache_creation」 | `src/app/protocols/responses_anthropic.py:240-241` | `src/app/hooks/builtin/token_calibration.py:53-61` | 轻微 | 同一恒等式的正反两向分别手写。目前一致，但它是 usage 语义的核心不变量，散在两处 | 与 D1 的 usage 值对象合并 |

## 3. 已发生漂移的证据（可复现）

探针：`/tmp/probe_drift.py`、`/tmp/probe_case1.py`，用 `.venv/bin/python` 在 HEAD `44471c6` 上执行。两侧分别直接调用 `convert_responses_response_to_anthropic()`（非流式）与 `render_responses_as_anthropic_sse()`（流式），喂**语义等价**的输入：同一 response id / model / 内容 / usage，一个是完整 JSON body，一个是产生该 body 的 SSE 事件序列。

### 3.1 `incomplete` + `max_output_tokens`：一边 502，一边 200

输入：`status:"incomplete"`，`incomplete_details.reason:"max_output_tokens"`，输出一条 `output_text:"hi"`，`usage:{input_tokens:10, output_tokens:5}`。

- 非流式（`protocols/responses_anthropic.py:84-88`）：
  `ResponseConversionError code=unsupported_response_status | unsupported Responses status 'incomplete'`
  → 经 `anthropic/client.py:299-306` 变成 `ApiError(status_code=502, category=UPSTREAM)`。
- 流式（`delivery/responses_anthropic_stream.py:276-282` + `delivery/anthropic_sse.py:756-759`）：正常 200，末帧为
  `data: {"type":"message_delta","delta":{"stop_reason":"max_tokens","stop_sequence":null},"usage":{"input_tokens":10,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}`

**同一个上游状态，客户端加不加 `stream` 决定它拿到的是被截断的正常回答还是一个网关错误。** 这是 D2 + D3 的直接后果。

### 3.2 message 项 content 为空：一边 200 空文本，一边 502

输入：`status:"completed"`，`output:[{"type":"message","id":"msg_2","content":[]}]`。

- 非流式（`protocols/responses_anthropic.py:121-122`）：200，`content:[{"type":"text","text":""}]`，`stop_reason:"end_turn"`。
- 流式（`openai/responses_stream_parser.py:510-517`）：`ApiError: response completed without content`（`empty_response_content` → 502）。

方向与 3.1 **相反**：这次是非流式宽松、流式严格。两条路径对同一产品问题各做了一次独立且相反的裁决。

### 3.3 `usage.input_tokens_details` 不是对象：一边 502，一边静默吞掉

输入：`usage:{input_tokens:10, output_tokens:5, input_tokens_details:"oops"}`。

- 非流式（`protocols/responses_anthropic.py:284-291` → `_mapping`）：`ResponseConversionError code=invalid_response | usage.input_tokens_details must be an object` → 502。
- 流式（`delivery/responses_anthropic_stream.py:425-430`）：`isinstance(..., Mapping)` 为假 → 当作空字典，正常 200，末帧
  `"usage":{"input_tokens":10,"output_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}`
  ——cache 字段被静默清零，且不产生任何 `usage_inconsistent` 事实。

这是 D1 的直接后果，也是「其中一遍弱一档」最典型的形态：**弱的那一遍不报错，所以没人会发现它弱。**

## 4. 扫描范围与判据

### 4.1 判据

判「重复」用两条，任一命中即入表：

1. **同一条可陈述的规则在两个位置各有一份完整实现**（不是调用同一个函数）。规则要能写成一句话，例如「incomplete + max_output_tokens 算成功」。
2. **同一输入类型 → 同一输出类型的转换写了两遍**，即使措辞不同。

判「有害 vs 良性」用判别句：**下一个复用者还会踩吗**。会 → 有害。两份处在不同抽象层且参数化确实困难、或其中一份是另一份的 typed 投影且不含独立规则 → 良性。

判「已漂移」只在**跑出两侧不同输出**时才标，不靠读代码推断。

### 4.2 实际执行的扫描与探针

- **全量结构扫描**：`/tmp/dupscan.py`，用 Python `ast` 归一化（变量名、属性名、常量全部抹平）后对函数体哈希分组。口径：`src/app/**/*.py` 全部文件，HEAD `44471c6`，阈值「归一化后 body dump ≥ 400 字符」以滤掉 trivial。结果：**函数 / 方法定义 915 个**，**结构完全相同的分组 17 组**。17 组逐个人工判读，入表的是 D9（`upstream/copilot.py` 与 `generic.py` 各 2 组）与 D10（两个 `_response`）。其余 15 组判为良性（FastAPI 依赖注入 getter 7 连、`hooks/registry` 的 3 个 register、`routes/history.py` 的 pin/unpin、路由 handler 样板、`quiesce`/`resume` 对称对、两个 `open_writer`、三个 `__init__`）——它们是**样板结构**相同而非**规则**相同，不满足判据 1/2。
- **逐行通读**（任务点名的全部 6 个搜索面）：`openai/responses_conversion.py`、`openai/responses_stream_parser.py`(1043)、`openai/stream_accumulator.py`、`openai/responses_stream_accumulator.py`、`openai/client.py`、`openai/responses_ws.py`、`protocols/anthropic_responses.py`(713)、`protocols/responses_anthropic.py`(345)、`protocols/azure.py`、`protocols/gemini.py`、`transform/translator.py`、`streaming/translator.py`、`streaming/sse.py`、`streaming/openai_sse.py`、`streaming/anthropic_usage.py`、`delivery/anthropic_sse.py`(1047)、`delivery/responses_anthropic_stream.py`(497)、`routes/anthropic.py`、`routes/openai.py`、`routes/azure.py`、`routes/gemini.py`、`routes/responses_ws.py`、`routes/protocol_history.py`、`anthropic/client.py`、`anthropic/thinking/responses_reasoning.py`、`errors.py`、`upstream/base.py`、`upstream/copilot.py`、`upstream/generic.py`、`tokenization/estimators.py`、`hooks/builtin/token_calibration.py`。
- **行为探针**（进程内，只读）：`/tmp/probe_drift.py`（3.1 / 3.2 / 3.3 三个用例，两侧对照）、`/tmp/probe_case1.py`（取 3.1 完整终帧）、`/tmp/probe_sdk.py` 与 `/tmp/probe_anthropic_sdk.py`（用 `httpx.MockTransport` 验证 openai 与 anthropic 两个 SDK 在 `cast_to=httpx.Response` 时对 429 均抛 `APIStatusError`，支撑 D9）。
- **引用点核查**：`rg` 找 `ToolNameMapper` / `tool_name_mapper` / `restore(` 全部源码引用点，确认生产代码无一处传入 mapper（D5 的「今天等价、明天漂移」结论基于此）；`rg -n "is_success" src/app --type py` 得 **10 处、分布 6 个文件**（口径：该命令原样输出行数）。
- **行号复验**：交付前对报告引用的 34 个 `file:line` 逐个 `sed -n "${l}p"` 取当行内容核对，全部命中预期符号。

### 4.3 扫了但**无发现**的地方（与「没扫」区分）

- **`streaming/translator.py` 与 `openai/responses_conversion.py`**：读完，各自只有一份实现，仓库内没有第二份 chat→responses 事件翻译或 call_id 归一化。无发现。
- **`openai/stream_accumulator.py`(ChatStreamAccumulator) 与 `openai/responses_stream_accumulator.py`(ResponsesStreamAccumulator)**：形似（都是 `process`/`snapshot` + `copy.deepcopy(usage)`），但吃的是**两个不同协议**的事件（`choices[0].delta` vs `response.output_text.delta`），没有共享规则可抽。**判为良性**，不入表。
- **`protocols/azure.py`**：19 行，只做 `model → deployment` 改写，仓库内无第二份。无发现。
- **`transform/translator.py`（OpenAI ↔ Anthropic 双向）**：与 `protocols/anthropic_responses.py` / `responses_anthropic.py` 概念上都做「Anthropic ↔ 别的协议」，但目标协议不同（Chat Completions vs Responses），块级规则不重合（前者是 `tool_calls` 数组，后者是独立 `function_call` item）。**判为良性**，不入表。
- **`errors.py`**：`classify_error` / `_category_from_status` 各只有一份，无第二处状态码→类别映射。错误**分类**无重复；错误 **wire 格式化**有重复，已记为 D13。
- **`routes/responses_ws.py` vs `openai/responses_ws.py` vs HTTP 腿**：exchange 形态差异实质（WS 帧 vs SSE 字节），未发现复制粘贴；唯一重复是终态事件集合，已记为 D12。
- **`tokenization/`**：`estimators.py` 的 `estimate_anthropic_input` / `estimate_gemini_input` 是两个协议各一份，共享 `_TOKENIZER_NAME` 与 tiktoken；`calibration.py` / `limits.py` 各持一份状态。未发现第二份 token 算式。唯一相关重复是 D14 那条恒等式。
- **`streaming/keepalive.py` / `idle_timeout.py` / `buffered_retry.py` / `delayed_commit.py`**：仅按行数与 `rg` 符号面扫过，未逐行通读，见第 5 节。

## 5. 未覆盖面

- **未逐行读**：`pipeline/`（`executor.py` 512 行、`manager.py`、`strategies/`）、`rolling_*.py`（约 1360 行）、`history/`、`hooks/executor.py`、`observability/`、`config/`、`auth/`、`server*.py`、`socket_activation.py`、`generation*.py`。这些落在结构扫描（4.2 第一项，覆盖全部 915 个定义）的覆盖内，但**没有过语义判据 1**——结构扫描只能抓「代码长得一样」，抓不到「规则一样但写法不同」，而本报告最有价值的 D1 / D2 / D4 恰恰全是后者。**这些目录里可能还有同类漂移，本轮未证否。**
- **`tests/` 未扫**：测试里可能存在第二份规则实现（fixture 里手写的期望映射），本轮未查。
- **重试 / retry 路径未查**：`streaming/buffered_retry.py`、`hooks/builtin/retry.py`、`pipeline` 的重试语义是否与 delivery frontier 的 uncertain 语义各写了一份，未验证。这条我判断风险不低，建议单独派一轮。
- **`refs/` 与 `~/src/copilot-api-js` 的对照未做**：本轮只看本仓库内部的自我重复，没有查「本项目重新实现了 copilot-api-js 已有的东西」。
- **D4 的正确方向未裁定**：我只证明了两侧行为相反，没有判断哪一侧是产品想要的。这属于用户 / ADR 裁决范围。

## 6. out-of-axis（各记一行，不展开）

- `out-of-axis`（错误处理）：`upstream/{copilot,generic}.py` 的 10 个非 `send_responses_headers` 方法在上游非 2xx 时抛 `APIStatusError`（已实测），而下游 10 处 `is_success` 分支按「会返回 response」写。Anthropic 腿有 `pipeline/executor.py:299` 的 `except Exception` 兜底，但会把上游 429 归一成 `ApiError(NETWORK, 502)`、丢掉真实状态码；`routes/openai.py` / `routes/azure.py` / `routes/gemini.py` 走的是 `OpenAIClient`，**没有任何兜底**，`server.py` 也只注册了 `ApprovalRejectedError` 一个 exception handler。建议单独查证「上游 429 时 `/v1/chat/completions` 实际返回什么」。
- `out-of-axis`（fake 保真度）：若测试里的 upstream fake 在非 2xx 时返回 `httpx.Response` 而非抛 `APIStatusError`，上一条永远不会被测出来。
- `out-of-axis`（分层）：`routes/gemini.py:30-98` `_gemini_stream` 承担了协议转换职责，应属 `protocols/gemini.py`。
- `out-of-axis`（第三方库）：SSE 解析（D8）与 SSE 渲染（`streaming/sse.py:20`）目前手搓，`httpx-sse` / `sse-starlette` 是成熟替代；`DelayedStartStreamingResponse`（`streaming/sse.py:66-203`）重写了 Starlette 的 `stream_response` 并 import 了 `starlette._utils.collapse_excgroups`（私有 API），值得单独评估。
- `out-of-axis`（生命周期所有权）：`DeliverySession` 同时持有 sequencer、renderer、writer、lease account 与 frontier 五种所有权，`_mode` 字段（`anthropic_sse.py:1010-1014`）在运行时区分 manual / typed 两套 API，是两个身份挤在一个对象里的信号。

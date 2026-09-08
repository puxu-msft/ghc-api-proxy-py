# 本侧调查：`The use of the web search tool is not supported` 400 的上行来路

调查对象：`/home/xp/src/ghc-api-proxy-py`，HEAD `b082039`（工作树有未提交改动，与本次结论无关：改动集中在 `observability/` 与 `server/` 的日志字段，不触碰 tools）。
调查日期：2026-08-20。纯只读调查，未修改任何代码。
姊妹报告：`docs/tmp/260820-websearch-400-vscode-ext.md`（上游侧／第一方扩展如何规避同一个错误）。本报告与它互相独立取证，结论一致。

生产日志原文：

```
[FAIL] 21:43:34 400 POST /v1/messages claude-opus-5 98ms: upstream rejected the request: Error code: 400 - {'error': {'message': 'The use of the web search tool is not supported.', 'code': 'unsupported_value'}}
```

---

## 0. 结论先行

**这条 400 不是从 Responses 端点回来的，是从 Copilot 的 Anthropic Messages 端点（`/v1/messages`）回来的。**

`claude-opus-5` 在 Copilot 目录里只广告 `/v1/messages` 与 `/chat/completions`，**不广告 `/responses`**。因此 `/v1/messages` 入站请求命中 `decide_route` 的 `inbound_format_supported` 分支，`translation_required = False`，走 **direct driver 原样透传**。客户端声明的 `web_search_20250305` server tool 连同整个 body 原封不动发给了上游，上游拒绝。

既定合同里那道「本地显式拒绝 `server_tool_not_supported`」的门（`protocols/anthropic_responses.py:409/540`）**根本不在这条路径上**——它属于 `app/anthropic/client.py` 这套 legacy 实现，而生产进程跑的是另一套 pipeline chain，两者没有任何交集。

置信度：**强，可据以动手**。理由见 §5。

---

## 1. 完整链路：从入口到发出上游请求

### 1.1 生产跑的是哪一个 app

项目里同时存在两套 FastAPI 应用，`src/app/server/__init__.py:6-12` 明说不能同时挂载。

- **生产用**：`src/app/cli.py:17` `from app.server.pipeline_app import create_pipeline_app`，在 `cli.py:138`（systemd/socket 激活）与 `cli.py:158`（standalone）两处构造。
- **未用**：`src/app/server/app_factory.py:164` `create_app`，`pipeline_app.py:3` 的模块 docstring 称其为「the existing implementation」。`cli.py` 从不引用它。

**判别证据**：日志行格式。`[FAIL] 21:43:34 400 POST /v1/messages claude-opus-5 98ms: <detail>` 正是 `observability/request_log.py:114` `format_completion_line` 的输出（status → subject → duration → detail，detail 前用冒号分隔，见 `request_log.py:143-144`），而唯一的调用点是 `server/pipeline_app.py:78-101` `_log_completion`。legacy app 没有这套行。

**顺带一条可读的事实**：`_subject`（`request_log.py:89-103`）在 `requested_model != model` 时会渲染成 `asked → answered`。日志里只有一个 `claude-opus-5`，且 `trace.requested_model` 在 `pipeline_app.py:150` 就已经写入（早于任何失败返回），所以**客户端字面请求的就是 `claude-opus-5`**，没有经过 `model_mappings` 改写。

### 1.2 链路

1. `src/app/server/pipeline_app.py:338` `router.add_api_route(path, _serve, methods=["POST"])`，路径来自 `server/inbound.py:34` `InboundRoute("/v1/messages", WireFormat.ANTHROPIC_MESSAGES)`。
2. `pipeline_app.py:104` `_serve` → `pipeline_app.py:122` `_dispatch` → `inbound.py:59` `build_context`（只提取 model / stream / 过滤 headers，**不碰 tools**）。
3. `pipeline_app.py:187` `handle_bounded` → `server/handler.py:56` `handle`。
4. `handler.py:58-64` `decide_route(...)` → `pipeline/routing.py:66` `decide_route`。
5. `handler.py:66-69`：入站是 Anthropic 时调 `fix_anthropic_request`（`pipeline/anthropic_request_hook.py:55`）。
6. `handler.py:71-79`：**仅当 `route.translation_required` 才翻译**。
7. `handler.py:82` `context.payload["model"] = route.model_id`。
8. `handler.py:90-98`：`DRIVERS[route.endpoint]` 构造 driver 并 `driver.run(context)`。
9. `pipeline/direct_driver/base.py` 的共享循环 → `model_provider/github_copilot.py:114` `send` → `:130-135` `send_anthropic_messages`。
10. `ghc_client/client.py:131-145` `send_anthropic_messages` → `:83-97` `_post_anthropic("/v1/messages", ...)`，即 `AsyncAnthropic.post`。

### 1.3 谁构造最终 body

**没有人。** 这条路上没有任何构造器——`context.payload` 就是客户端 JSON body 本身，只经过两处就地修改：

- `anthropic_request_hook.py:63` `normalize_context_management`（`{"edits": null}` → `{"edits": []}`）；
- `anthropic_request_hook.py:82-91` 空 thinking 块清理 + assistant 消息 destack；
- `handler.py:82` 覆写 `model`。

**关键取证**：对新链路的四个文件做 `tools` 全文检索，**零命中**：

```
rg -n "tools" src/app/server/handler.py src/app/server/inbound.py \
              src/app/pipeline/direct_driver/base.py \
              src/app/pipeline/anthropic_request_hook.py
# 无输出
```

另外 `server/composition.py:216` 构造 `Chain` 时 `subscribers=(subscribers or SubscriberRegistry[RequestContext]()).freeze()`——**默认不注册任何 subscriber**，所以 `attempt.prepare` 事件上也没有任何东西改写 payload。

### 1.4 错误文本的来路

`ghc_client/errors.py:99-105`：状态码 400 不在 `RETRYABLE_STATUSES`（`errors.py:40`）内，于是包成 `UpstreamRejected(f"upstream rejected the request: {error}")`。`{error}` 是 SDK 的 `APIStatusError.__str__`，形如 `Error code: 400 - {…}`（Python dict repr）。

`handler.py:221-224` 把 `UpstreamRejected` 映射回它自己的 `status_code`（400），`pipeline_app.py:188-196` 写进 `trace.detail`。

**注意**：`anthropic` SDK 与 `openai` SDK 的 `APIStatusError` 消息格式**完全相同**，所以「Error code: 400 - {...}」这个字符串本身**不能**区分是哪条腿。区分靠的是 §2 的目录事实。

---

## 2. `tools` 数组里会不会出现 hosted builtin——会，而且有两条各自独立的泄漏路径

### 2.1 路径 A（本次实际命中）：Anthropic → Anthropic 直通，完全无门

`pipeline/routing.py:92-95`：

```python
inbound_endpoint = FORMAT_ENDPOINTS[inbound_format]
if descriptor.supports(inbound_endpoint):
    endpoint = inbound_endpoint
    reason = "inbound_format_supported"
```

`routing.py:107` `translation_required=target_format is not inbound_format` → `False`。于是 `handler.py:71` 的翻译分支不进，body 原样出门。

**`claude-opus-5` 支不支持 `/v1/messages`？支持。** 证据是本仓自己的 live 录制目录 `tests/cassettes/anthropic_to_responses_stream.json`（`response.source == "live-recording"`，`GET /models`，该文件提交于 2026-08-19 `e742243`，即事故前一天）。把 chunks 拼回 JSON 后：

```
claude-opus-4.8 ['/v1/messages', '/chat/completions']
claude-opus-5   ['/v1/messages', '/chat/completions']
claude-sonnet-5 ['/v1/messages', '/chat/completions']

广告 /responses 的全部模型：
['gpt-5.3-codex', 'gpt-5.4-mini', 'gpt-5.4', 'gpt-5.5', 'gpt-5.6-luna',
 'gpt-5.6-sol', 'gpt-5.6-terra', 'grok-4.5', 'grok-4.6',
 'mai-code-1.1-flash', 'mai-code-1-flash-picker', 'gpt-5-mini']
```

**没有任何 Claude 模型广告 `/responses`。** 同一份 cassette 里那次 `POST /responses` 用的 model 是 `gpt-5.5`，不是 Claude。`refs/available_models.json`（2026-07-15 的旧快照）对全部 claude-* 也是同样的两项。

因此本次请求 **100% 走 `/v1/messages` 直通腿**，而不是 Responses 腿。

### 2.2 路径 B（本次未命中，但同样敞着）：Anthropic → Responses 翻译，typed tool 原样穿过

`pipeline/translation_driver/openai_responses.py:121-136`：

```python
def _function_tool(tool: dict[str, Any]) -> dict[str, Any]:
    if "input_schema" not in tool:
        return tool          # ← typed/server tool 无 input_schema，原样返回
    converted = {key: value for key, value in tool.items() if key != "input_schema"}
    converted["type"] = tool.get("type", "function")
    converted["parameters"] = tool["input_schema"]
    return converted
```

`openai_responses.py:405-406` `payload["tools"] = [_function_tool(tool) for tool in request.tools]`。`web_search_20250305` 没有 `input_schema`，于是 `{"type": "web_search_20250305", "name": "web_search", ...}` 会原样写进 Responses `tools`。

同理 `translation_driver/anthropic_messages.py:228` `payload["tools"] = request.tools`，逐字透传。

**这条今天没被触发只是因为没有 Claude 模型走 Responses 腿**（§2.1）。它是一个已装填但未击发的同类缺陷，不是安全的。

### 2.3 既定的本地能力门在哪里，为什么没响

门确实存在，位置也对得上任务简报：

- `protocols/anthropic_responses.py:539-540`：`if tool.type is not None: self._fail(path, "server_tool_not_supported", ...)`
- `protocols/anthropic_responses.py:408-409`：`_is_server_block`（`server_tool_use` / `*_tool_result`）也拒
- `protocols/responses_anthropic.py:112-113`：响应侧同样拒

唯一调用者是 `app/anthropic/client.py:250` `convert_messages_request_to_responses(...)`，而 `AnthropicClient` 只由 `server/app_factory.py` 组装——**生产不跑那套**（§1.1）。

同样的孤儿关系还有两处，值得一并记下：

- `anthropic/message_tools.py:6` `preprocess_tools`（会给无 `type` 的工具打 `defer_loading`，并注入 `tool_search_tool_regex_20251119`）只被 `anthropic/request_preparation.py:29` 调用，后者只被 `anthropic/client.py:12` 调用。新链路完全不经过。
- `anthropic/feature_negotiation.py` 的 `FeatureNegotiationStore`：`rg feature_negotiation --type py src/` **零个导入者**，是纯孤儿模块。而且它的 `NEGOTIATION_CATEGORIES`（`:5-15`）与现网 JS 服务相比**少了 `serverTools` 与 `serverToolDowngrade` 两类**，恰恰是处理本问题的那两类。

---

## 3. 候选解释逐条证伪／证实

| # | 候选 | 判定 | 依据 |
|---|---|---|---|
| A | Anthropic `tools` 有 bypass/passthrough 路径绕过能力门 | **证实（根因）** | `routing.py:92-95` + `handler.py:71` + 对四个文件 `rg tools` 零命中；目录证据 §2.1 |
| B | 存在把 client tool 原样透传的 driver | **证实** | `direct_driver/anthropic_messages.py`（整文件 32 行，只绑定 endpoint）+ `direct_driver/base.py` docstring：「The payload goes out as it arrived, apart from what subscribers change」，而默认零 subscriber（`composition.py:216`） |
| C | `tool_choice` / `include` / `store` / `reasoning` 等其它字段触发 `unsupported_value` | **证伪** | 直通腿上 body 就是客户端的 Anthropic body，压根没有 `include` / `store` / `reasoning` 这些 Responses 专有字段（它们只在 `protocols/anthropic_responses.py:181-187` 的 Responses 桥里被构造，而那条路没走）。且错误文本点名 “web search tool”，不是字段名 |
| D | 上游是在对**历史消息里残留的 web_search 相关 item** 报错，而不是对 `tools` 声明 | **证伪** | 现网 JS 服务把这两种拒绝分成了两个**不同 message、不同 negotiation 类别**的策略：<br>• `tools` 声明被拒 → `The use of the web search tool is not supported.` + `unsupported_value` → `serverTools` 类（`~/src/copilot-api-js/src/lib/request/strategies/server-tool-rejection-retry.ts:51-59`、`src/lib/anthropic/feature-negotiation.ts:24-27`）<br>• 历史轮 `server_tool_use{web_search}` 块被拒 → `Tool 'web_search' not found in provided tools` → `serverToolDowngrade` 类（`src/lib/request/strategies/web-search-not-found-retry.ts:1-45`）<br>我们观测到的是前者 |
| E | 我们把 Anthropic 历史消息转成 Responses `input` 时会造出 web search item | **证伪（对本次而言）** | 本次没走翻译（§2.1）。且翻译器 `openai_responses.py:269-297` `_item_from_block` 是白名单式的，只产出 `input_text`/`output_text`/`function_call`/`function_call_output`/`reasoning`，未知 block 走 `conversion.record(BLOCK_NOT_CARRIED)` 并返回 `None`。<br>**但**：`translation_driver/anthropic_messages.py:184-185`，`_block_to_anthropic` 对 UNKNOWN block「returning it is what keeps a same-format crossing exact」，即 Anthropic→Anthropic 时 `server_tool_use` / `web_search_tool_result` 块也是**原样透传**的。这是一条与 D 并列、今天没被触发的同类敞口 |

### 关于 D 的补充说明

D 这条虽被证伪，但它的存在形态在本项目里**比在 JS 服务里更糟**：JS 服务有常驻兜底 `downgradeEmptyEncryptedSearchResults`（`~/src/copilot-api-js/docs/tool-use.md:19`），本项目直通腿上什么都没有。

---

## 4. 本地能否复现／取到真实上行 payload——取不到，而且是能力缺失不是找不到

结论：**取不到。生产进程当前没有记录上行 payload 的能力。**

逐条排查：

1. **`~/.local/share/ghc-api-proxy/history.db`**（2.1 MB，最后写入 2026-08-19 21:57，时间上紧挨事故）——7434 条，但 `GROUP BY endpoint, resolved_model` 的全部结果只有 `gpt-test` / `gemini-test` / `deployment` 三个假模型，**没有一条 `claude-opus-5`，没有一条 `anthropic-messages` endpoint**。这些是测试套件写进真实数据目录的产物。
2. **为什么没有生产记录**：`HistoryConsumer` 只在 `server/app_factory.py:107` 被接线（`runtime.anthropic_client.history = HistoryConsumer(...)`）。`server/composition.py` 的 `Chain` **没有 history 字段**，`server/pipeline_app.py` 全文不引用 history。`cli.py:97/219` 的 `--history` 只写进 config，新链路无人消费。
3. **`data/history.db`**（20 KB，2026-08-12，root 属主）——同一套 legacy schema 的更旧残留。
4. **可观测性侧**：`observability/tracing.py` / `telemetry.py` 对 `payload` 零命中。`pipeline_app.py` 只记 `bytes_in` 长度（`:125`），不记内容。
5. **现网 JS 服务的 history v3 DB**：扫了 2026-08-15 ~ 08-19 的四个库共 32762 个对象（gzip 解压后全文搜 `web_search`），**零命中**。但这条**不构成反证**——那几个库里 `payload` 类对象只有 81 个、合计 14 KB，请求体基本以 `payload-skeleton` 形式存在，本来就不保全文。
6. **现网 JS 服务的 negotiation 缓存** `~/.local/share/copilot-api/negotiation-states.json`：`serverTools` 与 `serverToolDowngrade` 均为 `{}`。说明这套拒绝在现网 4141 上**从未被观测到过**——与「客户端只在特定配置下才声明 web_search，而那个客户端这次指向的是我们的 Python 代理」相容。

---

## 5. 根因与置信度

### 根因

客户端（请求字面 model = `claude-opus-5`，形态与 Claude Code 的 `WebSearch` server tool 一致）在 `/v1/messages` 请求的 `tools` 里声明了 `web_search_20250305` 这类 hosted server tool。由于 `claude-opus-5` 在 Copilot 目录里支持 `/v1/messages`，`decide_route` 判定无需翻译，direct driver 把整个 body 原样 POST 到 Copilot 的 `/v1/messages`；Copilot 后端不支持服务端执行 web search，返回 400 `unsupported_value`。

本项目对 typed/server tool 的既定本地拒绝合同只实现在 Responses 桥（`protocols/anthropic_responses.py`）里，而那套代码属于生产不运行的 legacy app；新 pipeline 链路在 tools 上**没有任何门**。

### 置信度：强，可据以动手

支撑它的是四条**互相独立**的证据：

1. 代码路径静态可达性（§1、§2.1），无分支歧义；
2. 事故前一天的 live 录制目录证明 `claude-opus-5` 不广告 `/responses`（§2.1）——这条同时**推翻了任务简报里「上游 Responses 端点拒绝」的前提**；
3. 现网 JS 服务对**同一个上游、同一句 error message、同一个 error code** 有专门的策略与注释，且把它与「历史块被拒」明确区分成两类（§3 D）；
4. 姊妹报告独立发现第一方 vscode 扩展硬编码剔除 `type.startsWith('web_search')`，并在源码注释里写 `CAPI does not yet support the WebSearch tool`。

**它没有覆盖的**：我们拿不到那次请求的字节级 payload（§4），所以「客户端具体发的是 `web_search_20250305` 还是别的 `web_search_*` dated variant」属于推断而非观测。这不影响根因判断——`SERVER_TOOL_REJECTION_TABLE` 用的就是 `web_search_` 前缀，任何 dated variant 都落进同一条。

### 排序第二的候选（若有人要挑战）

「上游拒绝的不是 `tools` 声明而是别的东西」。我给它的权重是**低**，因为 §3 C/D 已各自被独立证据切掉。

### 最小判别实验

一条实验就能区分全部候选，且**不需要动生产**：

用当前 Copilot 凭据，对 `/v1/messages` 发两次极小请求，model 固定 `claude-opus-5`，messages 固定一句 `hi`，唯一差异是 `tools`：

- **实验组**：`tools: [{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}]`
- **对照组**：`tools` 省略

预期（若根因成立）：实验组 400 `The use of the web search tool is not supported.` / `unsupported_value`；对照组 200。

若两组都 400，则根因不在 `tools`，转查 C。若两组都 200，则说明触发条件还依赖 messages 里的历史块，转查 D／E 的 Anthropic→Anthropic UNKNOWN block 透传（`translation_driver/anthropic_messages.py:184-185`）。

按项目的 cassette 纪律，这次调用应经 `tests/integration/recorded/record_cassette.py` 录制留档，而不是临时脚本。

---

## 6. 顺带发现（本次未处置，仅记录，供裁决）

以下都不属于本次调查的授权范围，**没有做任何修改**，也不建议在没有裁决前动手：

1. **同类敞口尚未击发**：Anthropic→Responses 翻译腿的 `_function_tool`（`openai_responses.py:121-136`）同样会原样透传 typed tool。今天安全只是因为没有 Claude 模型走那条腿——这是个依赖上游目录的偶然，不是设计保证。
2. **历史块方向的敞口**：`anthropic_messages.py:184-185` 让 `server_tool_use` / `web_search_tool_result` 在 Anthropic→Anthropic 时原样透传。对应 JS 服务的 `serverToolDowngrade` 与常驻 `downgradeEmptyEncryptedSearchResults` 兜底，本项目两者皆无。
3. **孤儿模块**：`anthropic/feature_negotiation.py` 零导入者，且缺 `serverTools` / `serverToolDowngrade` 两个类别；`anthropic/message_tools.py` → `request_preparation.py` 链只服务于生产不跑的 legacy app。按记忆里「不得擅自删除已实现的功能」的裁决，这里只做记录，不提删除。
4. **400 不可重试是有意的**：`pipeline/exceptions.py:60-66` 明说 `UpstreamRejected` 故意不继承 `UpstreamError`，`classify` 因此 abort。所以本项目**结构上没有**现网 JS 那种「400 → 学习 → strip → 重试」的反应式自愈；要补的话是新增机制，不是修 bug。

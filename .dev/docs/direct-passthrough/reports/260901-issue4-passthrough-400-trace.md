# issue #4 追踪：`/responses` 直连腿 400 的代码路径与成因

> **落盘位置说明（给主会话）**：本报告本应写入主工作树的 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260901-issue4-passthrough-400-trace.md`（项目规则：隔离 worktree 无 `.dev/` 副本，报告仍写回主树）。但本次会话的 harness 守卫拒绝向 shared checkout 写入，强制要求写在 worktree 内。故落在此处，**内容即最终版，请 `mv` 到主树同名路径**。详见 §8 局限 6。

**日期**：2026-09-01
**调查基线**：主工作树 `/home/xp/src/ghc-api-proxy-py`，HEAD = `1fb37cd`（*fix: carry upstream's own events on every direct leg this proxy can, closing issues #2 and #3*，2026-09-01 16:39:17 +0000）
**性质**：只读调查。未修改任何源码、未跑测试、未向 Copilot 发任何真实推理请求。

---

## 0. 结论先行

**根因已确定，且不是推断——上游用自己的话说出来了。**

同一份 901,008 字节的请求体，在 16:32 和 16:50 两次发出，得到两条**措辞不同、指向同一件事**的 400：

```
16:32  {"error":{"message":"The resource you requested was not found.","code":"invalid_request_body"}}
16:50  {"error":{"message":"The encrypted content for item rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0 could not be verified. Reason: Encrypted content item_id did not match the target item id.","code":"invalid_request_body"}}
```

`rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0` 是本代理 `ResponsesFramer._item_id()` 自己造的 item id（`src/app/pipeline/delivery/formats/openai_responses.py:155-156`），格式为 `rs_<RequestContext.id 的 uuid4>_<output_index>`。同一个 reasoning item 上，`encrypted_content` 却是**上游原样的密文**（同文件 `:341-343`）。

于是：**本代理在响应方向把上游 reasoning item 的 id 改写成了自己的，密文原封不动带走；Codex 把这一对存进会话历史；下一轮回发时 Copilot 解开密文、读出里面绑定的 item_id、与外层 `id` 比对，不一致 → 400。**

请求方向**没有任何问题**：本次请求的出站字节与客户端 body 逐字节等价（§5 有复现证明）。缺陷在**上一轮的响应方向**，本次请求只是它的受害者。

`1fb37cd`（16:39）引入的 native passthrough 正是这个缺陷的修法——它把上游事件原样转发，不再造 id。但它落地在这次失败（16:32）**之后**，且**修不了已经被污染的会话历史**：Codex 线程里那 28 个假 id 会一直回发，直到它们被挤出上下文或线程重开。

---

## 1. 证据来源与权重

| 编号 | 来源 | 权重 | 说明 |
|---|---|---|---|
| E1 | `/home/xp/src/ghc-api-proxy-py/src/**` @ `1fb37cd` | 强（一手，读到的代码） | 本报告所有 `文件:行号` 引用 |
| E2 | issue #4 附件（`gh issue view 4` 取到 URL，下载到 `/tmp/issue4-capture.json`，1,923,506 B） | 强（一手，生产取证） | 16:32 那次 400 的完整 `capture_rejection` 记录 |
| E3 | `~/.local/share/ghc-api-proxy/rejected/2026090*.json` 四份 | 强（一手，生产取证） | **不是我造的**——16:43/16:44 三份是同伴或用户跑的隔离探针，16:50 一份是同一 body 的重放 |
| E4 | `refs/available_models.json`、`exp/260820-websearch-probe/raw/models-live.json` | 强（一手，实测目录快照） | `gpt-5.6-sol` 的 `supported_endpoints` |
| E5 | `.dev/docs/sync-refs/sxwxs-ghc-api/260821-probe-upstream-sanitize-rules.md` | 强（一手实测，本项目自己的） | Copilot 错误码词汇 |
| E6 | `/home/xp/src/refs/hooyao-copilot-bridge/docs/codex-protocol-research.md` | 中（他人实测，2026-06-12，不同账户） | Copilot `/responses` 字段接受矩阵 |

**关于 E2/E3 的取证动作**：本次调查下载了 issue #4 的公开附件到 `/tmp`，并读取了本机 `~/.local/share/ghc-api-proxy/rejected/` 下的错误捕获文件。两者都是只读，且都是本调查的直接证据。E3 中 16:43–16:50 的四份**不是本次调查产生的**——它们的时间戳早于本次调查介入，说明用户或同伴会话已经在做同一件事，本报告与之收敛而非独立发现。

---

## 2. Q1：入口与路由，这条请求怎么走到 `/responses` 的

### 2.1 HTTP 入口

`POST /responses`（或 `/v1/responses`、`/openai/v1/responses`，见 `src/app/server/routes/table.py` 的 `OPENAI_PREFIXES`）由**唯一的分发器** `serve` → `_dispatch` 接住，`src/app/server/routes/inference.py:73` 与 `:135`。

路由表查找在 `inference.py:147-148`：

```python
matched = request.scope.get("route")
route = route_for_path(getattr(matched, "path", None) or request.url.path)
```

命中 `table.py` 的这一行：

```python
InboundRoute("/responses", WireFormat.OPENAI_RESPONSES, openai_prefixed=True),
```

所以 `route.wire_format = OPENAI_RESPONSES`、`streamable=True`、`count_tokens=False`、`implemented=True`。

`inference.py:171` 解析 JSON；`:188` 调 `build_context(route, body, request.headers, request.path_params)`。

`src/app/server/inbound.py:56` 是关键的一行：

```python
working = deepcopy(dict(payload))
```

**没有任何 Pydantic 模型参与**。整条直连路径上 payload 始终是 `dict[str, Any]`，所以「未知字段被 `extra="ignore"` 丢掉」或「被 `extra="forbid"` 拒掉」这两种可能**在这条腿上都不存在**（对比：`handle_count_tokens` 里的 `_countable()` 才会 `MessagesRequest.model_validate`，那是另一条腿）。`stream` 只被读成 `bool`（`inbound.py:51`），不改写。

### 2.2 `route_reason = inbound_format_supported` 是怎么得出的

`inference.py:267` → `handle_bounded` → `handle`（`src/app/pipeline/driver.py:132`）→ `shape_request`（`:82`）→ `decide_route`（`src/app/pipeline/routing.py:290`）。

`decide_route` 的判定在 `routing.py:314-326`：

```python
if explicit_format is not None:
    ...
    reason = "explicit_format"
else:
    inbound_endpoint = FORMAT_ENDPOINTS[inbound_format]
    if descriptor.supports(inbound_endpoint):
        endpoint = inbound_endpoint
        reason = "inbound_format_supported"
    else:
        endpoint = _first_supported(...)
        reason = "translated_to_available_endpoint"
```

模型名里没有 `@format` 后缀，所以走 else 分支；`FORMAT_ENDPOINTS[OPENAI_RESPONSES] = ModelEndpoint.OPENAI_RESPONSES`（即 `"/responses"`），而 `descriptor.supports("/responses")` 为真，于是 `reason = "inbound_format_supported"`。

`translation_required` 在 `routing.py:335`：

```python
translation_required=target_format is not inbound_format,
```

`target_format = ENDPOINT_FORMATS["/responses"] = OPENAI_RESPONSES`，与 `inbound_format` 同一个枚举成员，所以 `False`。捕获文件里 `translation_required = False`、`target_format = "openai-responses"` 与此一致。

### 2.3 交给谁执行

`driver.py:157` 的 `if route.translation_required:` 整块被跳过（不翻译）。然后：

```python
context.payload["model"] = route.model_id          # driver.py:172
driver_type = DRIVERS[route.endpoint]              # driver.py:177  → OpenAIResponsesDriver
outcome = await driver.run(context)                # driver.py:190
```

`OpenAIResponsesDriver`（`src/app/pipeline/direct_driver/openai_responses.py:15`）只是把 `ENDPOINT = ModelEndpoint.OPENAI_RESPONSES` 绑到共享的 `DirectDriver` 上，没有自己的逻辑。

`DirectDriver.run`（`src/app/pipeline/direct_driver/base.py:136`）的一次 attempt：

```python
await self._publish(EVENT_ATTEMPT_PREPARE, context, outcome)   # base.py:145
attempt.payload = dict(context.payload)                        # base.py:148
response = await self._send(context, attempt.payload)          # base.py:151
```

`_send`（`base.py:236`）调 `provider.send(endpoint, payload, model_id=..., stream=..., extra_headers=context.client_headers or None)`。

**链路完整闭合**：`serve` → `_dispatch` → `build_context` → `handle_bounded` → `handle` → `shape_request`/`decide_route` → `DirectDriver.run` → `GithubCopilotProvider.send` → `GhcApiClient.send_responses` → `AsyncOpenAI.post("/responses")`。

---

## 3. Q2：provider `ghc-msft` 是什么，Copilot 到底有没有 `/responses`

### 3.1 有。这一点用不着推断

`gpt-5.6-sol` 在两份**实测目录快照**里都明确写着（E4）：

```json
"id": "gpt-5.6-sol",
"supported_endpoints": ["/responses", "ws:/responses"],
"capabilities": {"type": "chat", "limits": {"max_context_window_tokens": 1050000, "max_prompt_tokens": 922000, ...}}
```

注意它**只有** `/responses`，连 `/chat/completions` 都没有。所以「Copilot 只有 `/chat/completions`」这个猜想是反的。

更强的一层：**代码本身就是守卫**。请求能出网就证明目录里有它且它宣告了 `/responses`——

- `routing.py:308-312`：`descriptor = provider.describe(resolution.resolved)`，`None` 就 `raise UnknownModel`，在任何网络请求之前。
- `github_copilot.py:99-102`：`describe` 只返回 `self._descriptors.get(model_id)`，而 `_descriptors` 只由 `replace_catalog` 从上游 `/models` 的响应填充（`:104-133`）。**没有任何乐观放行**。
- `github_copilot.py:164-167` + `types.py:206-214`：`send` 里再查一道 `require_endpoint`，不支持就 `raise EndpointNotSupported`，同样在网络之前。

捕获文件里 `attempts = 1` 且带着**上游自己的 body**，证明请求真的飞出去过。所以「模型不在目录里」「模型不支持 `/responses`」两条**被代码证据排除**。

补充旁证（E5，本项目 2026-08-21 实测）：Copilot 对「模型不支持 Responses API」有专门的错误码 `unsupported_api_for_model`，措辞是 `model claude-sonnet-5 does not support Responses API.`；对「模型不存在」是 `model_not_supported` / `The requested model is not supported.`。本次拿到的是 `invalid_request_body`，两者都不是。

### 3.2 base URL 与端点拼接

`ghc-msft` 是 `model_providers` 里用户自取的名字，仓库内无任何硬编码（全仓 grep `ghc-msft` 零命中）。它的 base URL 有且只有两条来路，`src/app/server/composition.py:347-408` 的 `resolve_provider_base_urls` 说得很清楚：运维在 `model_providers.<name>.api_base_url` 写全 URL，或探测 `/copilot_internal/user` 由订阅计划推导。

推导规则在 `src/app/model_provider/ghc_client/config.py:46-55`：

```python
override = config.api_base_url_override.rstrip("/")
if override: return override
if config.account_type == "self-hosted":
    raise ValueError("self-hosted accounts require an explicit api_base_url_override")
if config.account_type == "individual": return INDIVIDUAL_BASE_URL   # https://api.githubcopilot.com
return f"https://api.{config.account_type}.githubcopilot.com"        # business / enterprise
```

端点拼接：`composition.py:437-439` 构造 `AsyncOpenAI(base_url=base_url)`，`GhcApiClient.send_responses`（`src/app/model_provider/ghc_client/client.py:154-168`）调 `_post_openai("/responses", ...)`，后者（`:76-82`）是 `self._openai.post("/responses", cast_to=httpx2.Response, body=dict(payload), options={"headers": ...}, stream=stream)`。**最终 URL = `<base_url>/responses`**。

> 参考：本仓 cassette `tests/int/cassettes/anthropic_to_responses_stream.json` 里的 token 交换响应显示 `"endpoints":{"api":"https://api.enterprise.githubcopilot.com"}`，`sku` 为 `copilot_enterprise_seat_multi_quota`。E4 的目录快照也是这个账户拉的。`ghc-msft` 具体指向哪个 host 本次**未核**（配置文件在 `~/.config/ghc-api-proxy/` 或用户指定路径，不在仓库里），但由 §3.1 的代码守卫可知：无论指向哪里，它的 `/models` 里确实有 `gpt-5.6-sol` 且宣告 `/responses`。

### 3.3 请求头

两层：

**本库自有头**（`src/app/model_provider/ghc_client/headers.py:20-59`）——`editor-version`、`editor-plugin-version`、`user-agent: GitHubCopilotChat/<ver>`、`x-vscode-user-agent-library-version`、`Authorization: Bearer <copilot token>`、`content-type: application/json`、`copilot-integration-id: vscode-chat`、`openai-intent: conversation-panel`、`x-github-api-version`、`x-request-id`、`X-Interaction-Id`、`X-Interaction-Type`、`X-Agent-Task-Id`。

**客户端转发头**：`GhcApiClient.request_headers`（`client.py:39-66`）把 `extra_headers` 放在**底下**，并且**大小写不敏感**地让自有头覆盖（`:57` 的 `owned = {name.lower() for name in headers}`）。所以 Codex 的 `user-agent`、`content-type` 都被顶掉。

客户端头能到这里，先要过两道筛：

1. **地板**（`build_context` 里，`src/app/anthropic/header_policy/__init__.py:4-35` 的 `REQUEST_FLOOR`）——凭据、hop-by-hop、forwarded 链、`content-length`、`accept-encoding` 等无条件删。同一函数 `:82` 还有一条容易漏看的：

   ```python
   and not name.lower().startswith(("x-github-", "openai-"))
   ```

   **所以 Codex 的 `OpenAI-Beta: responses=experimental` 被丢掉了**，它不可能是本次 400 的因。

2. **路径策略**（`shape_request` 里，`driver.py:107-109` → `src/app/pipeline/request_headers.py:64-77`）——直连腿用黑名单，而 `DIRECT_PATH_BLACKLIST = ()`（`request_headers.py:45`，空元组）。**即：过了地板的客户端头，直连腿全部转发**（`originator`、`session_id`、`conversation_id`、`accept` 等 Codex 头都会到 Copilot）。

`driver.py:111-129` 的 `anthropic-beta` 剥离整块被 `if context.inbound_format is WireFormat.ANTHROPIC_MESSAGES` 挡住，这条腿不走。

一处**已存在但不影响本次**的间隙：`ModelDescriptor.request_headers`（目录里的 per-model 额外头）被解析并保存（`github_copilot.py:125`），但 `GhcApiClient.request_headers` 从不把它传给 `build_request_headers(model_request_headers=...)`，所以**目录声明的 per-model 请求头一律不发**。`gpt-5.6-sol` 的目录条目没有这个键，本次无影响。

---

## 4. Q3：`gpt-5.6-sol` → `gpt-5.6-sol` 的解析，以及「不在目录里会怎样」

### 4.1 解析两趟

`.dev/docs/multi-provider-routing/spec.md` §2 定义的两趟，实现在 `src/app/pipeline/model_resolution.py`：

- `discover_provider`（`:111-154`）**不查任何目录**，只走 `model_mappings` 的别名链，回答「归谁」。
- `resolve_against_catalog`（`:283-303`）回答「在那边叫什么」。

`decide_route` 里串起来（`routing.py:297-306`）。

### 4.2 关键回答：不在目录里会怎样

**先放行原样退回原名，但随即被拦下报错——最终行为是拦截，不是透传到上游。**两段分开看：

`resolve_against_catalog`（`model_resolution.py:299-303`）：

```python
available_index = {canonical(model): model for model in available}
direct = available_index.get(canonical(target))
if direct is not None:
    return ModelResolution(requested, direct, matched_key, hops=hops)
return ModelResolution(requested, requested.strip(), matched_key, passthrough=True, hops=hops)
```

链末的 target 落不进目录 → `passthrough=True`，`resolved` 退回**客户端原来那个名字**。这一步确实「放行」。

但下一步立刻收网（`routing.py:308-310`）：

```python
descriptor = provider.describe(resolution.resolved)
if descriptor is None:
    raise UnknownModel(provider.name, resolution.resolved, choice.target)
```

而 `describe`（`github_copilot.py:99-102`）只认目录里有的。所以 `passthrough` 的语义是「放弃坏掉的 mapping，退回客户端自己写的名字再查一次目录」，不是「不查目录直接发」。`resolve_against_catalog` 的 docstring 自己也这么解释（`:293-297`）。

本次 `requested_model == resolved_model == "gpt-5.6-sol"`，两种情况都能产生这个等式（直接命中，或 mapping 断链后 passthrough 回原名再命中），**捕获文件里的字段无法区分二者**。但无论哪一种，`describe` 都返回了非 `None` 的 descriptor——见 §3.1。

### 4.3 目录里到底有没有它

有。E4 两份快照都有完整条目（`type: chat`、`reasoning_effort: [none, low, medium, high, xhigh, max]`、`supported_endpoints: ["/responses","ws:/responses"]`）。`tests/int/cassettes/` 里没有 `gpt-5.6-sol` 的 `/responses` 请求 cassette（现有三份 POST cassette 都是 `gpt-5.5`）。

---

## 5. Q4：直通路径对 payload 做了什么 —— 逐字节答案是「什么都没做」

### 5.1 代码上的每一处可能改动

| 位置 | 这条腿上做了什么 |
|---|---|
| `inbound.py:56` | `deepcopy(dict(payload))`。**纯 dict，无 Pydantic，无字段白名单** |
| `inbound.py:57-58` | `route.model_from_path` 为空，不触发 |
| `driver.py:107-109` | 只动 headers，不动 body |
| `driver.py:111-129` | 被 `inbound_format is ANTHROPIC_MESSAGES` 挡住，整块跳过 |
| `driver.py:138-155` | auto-mode 拦截，同样被 `inbound_format` 挡住 |
| `driver.py:157-169` | `route.translation_required` 为 `False`，翻译整块跳过 |
| `driver.py:172` | `context.payload["model"] = route.model_id`——唯一一次赋值，本次前后同值 |
| `base.py:145` | 发布 `attempt.prepare`，六个内建 subscriber 全部跑过 |
| `base.py:148` | `attempt.payload = dict(context.payload)`，浅拷贝 |
| `client.py:79` | `body=cast(OpenAIBody, dict(payload))`，交给 OpenAI SDK 序列化 |

六个 `attempt.prepare` subscriber **在这条腿上全是空转**，每个都有明确的门：

| subscriber | 门 | 行 |
|---|---|---|
| `builtin:server-tool-capability` | `if context.target_format is not WireFormat.ANTHROPIC_MESSAGES: return` | `subscribers/server_tools.py:258` |
| `builtin:hosted-web-search-gate` | `if context.inbound_format is not WireFormat.ANTHROPIC_MESSAGES: return` | `subscribers/hosted_web_search.py:94` |
| `builtin:anthropic-thinking-capability` | `if context.target_format is not WireFormat.ANTHROPIC_MESSAGES: return` | `subscribers/anthropic_thinking.py:90` |
| `builtin:blank-text-blocks` | 同上 | `subscribers/blank_text.py:74` |
| `builtin:anthropic-trailing-assistant` | 同上 | `subscribers/anthropic_trailing_assistant.py:79` |
| `builtin:anthropic-cache-control-vocabulary` | 同上 | `subscribers/anthropic_cache_control.py:188` |

所以：`additional_tools` 这种 input item 类型、`client_metadata` 顶层键、`reasoning.context` 子键、`include` 数组、`prompt_cache_key`、`text.verbosity`、`store`、`parallel_tool_calls`、`tool_choice`——**全部原样透传，没有白名单、没有校验、没有裁剪**。

### 5.2 逐字节复现证明

不止是读代码。捕获文件同时存了 `payload`（发送前的 dict）和 `sent`（httpx 真正写到线上的字节，见 `src/app/observability/rejection_capture.py:72-78`）：

```
payload 的键与 sent 的键完全一致且顺序相同：
  ['model','input','tool_choice','parallel_tool_calls','reasoning','store','stream','include','prompt_cache_key','text','client_metadata']
json.loads(sent) == payload  →  True
```

并且用 httpx 的序列化参数重新序列化 payload：

```python
len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))
# → 901008，与 capture 的 sent_bytes 完全相等
```

**键的顺序、分隔符、非 ASCII 编码都对得上**，说明出站字节就是客户端 body 经 `json.loads` → `json.dumps` 的往返，内容零改动（`model` 值前后相同，所以 `driver.py:172` 那次赋值也不可见）。

### 5.3 捕获到的 payload 长什么样（供后续判据引用）

顶层：

```json
{"model":"gpt-5.6-sol","tool_choice":"auto","parallel_tool_calls":false,
 "reasoning":{"effort":"high","context":"all_turns"},
 "store":false,"stream":true,
 "include":["reasoning.encrypted_content"],
 "prompt_cache_key":"01a05417-6085-7e92-acea-f93bb5079fc5",
 "text":{"verbosity":"low"},
 "client_metadata":{...}}
```

`input` 359 项，类型分布：`function_call` 102、`function_call_output` 102、`reasoning` 66、`message/assistant` 54、`message/user` 16、`message/developer` 8、`custom_tool_call` 5、`custom_tool_call_output` 5、`additional_tools` 1。

- **无顶层 `tools`**。工具全在 `input[0]`：`{"type":"additional_tools","role":"developer","id":"at_3d7b149d-…","tools":[{"type":"namespace","name":"functions","tools":[custom exec, function wait, function request_user_input]}]}`。
- 工具调用配对**完好**：107 个 call、107 个 output，无孤儿、无重复。函数名 `exec_command` 98、`apply_patch` 5、`write_stdin` 3、`wait` 1。
- **无重复 item id，无缺 id**。
- `client_metadata.x-codex-turn-metadata` 里 `"turn_trigger":"edit_user_message"`。

---

## 6. Q5：候选成因，排序与判据

先讲一件对**所有**后续判据都成立的事：**`error.code = invalid_request_body` 在 Copilot `/responses` 腿上没有任何鉴别力。**本仓自己的测试注释就写着（`tests/unit/pipeline/test_error_classify.py:337`、`tests/int/test_error_envelope.py:609`）：上下文溢出、字段类型错、被拒工具、网关不认的 beta 头，四种毫不相干的失败共用这一个 code。**只能看 message。**

而 message 也不稳定：§0 已证明**同一份 901,008 字节在 16:32 和 16:50 得到两条不同措辞**。所以「`The resource you requested was not found.` 这句话很奇怪」这个观察本身是对的，但它不是一条独立线索——它只是同一次拒绝的另一种渲染。

### 6.1 排名第一（已证实）：本代理改写了 reasoning item id，密文却是上游的，回发时校验失败

**证据强度：强到不需要排序——上游直接点名了那个 item。**

三段证据咬合：

**(a) 上游的原话**（E3，16:50 捕获，body 与 issue 附件逐字节相同）：

```
The encrypted content for item rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0 could not be verified.
Reason: Encrypted content item_id did not match the target item id.
```

`rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0` 正是本次请求 `input[230]`，一个带 10,960 字符 `encrypted_content` 的 reasoning item。

**(b) 代码里造 id 的那两行**（E1，`src/app/pipeline/delivery/formats/openai_responses.py`）：

```python
155:    def _item_id(self, prefix: str) -> str:
156:        return f"{prefix}_{self._response_id}_{self._output_index}"
```

`_response_id` 来自 `delivery_policy.py:97` 的 `ResponsesFramer(response_id=message_id, model=model)`，而 `message_id` 是 `inference.py:329` 传的 `context.id`——`RequestContext.id` 的定义是 `src/app/pipeline/request.py:68`：

```python
id: str = field(default_factory=lambda: str(uuid4()))
```

**一个本地 uuid4，与上游说过的任何东西都无关。**

同一个 `_reasoning` 方法里（`:333` 与 `:341-343`）：

```python
item_id = self._item_id("rs")                 # 本地造的
...
carrier = decode_reasoning_carrier(str(block.payload.get("signature", "")))
if carrier.encrypted_content:
    item["encrypted_content"] = carrier.encrypted_content   # 上游原样的密文
```

**id 是我们的，密文是上游的。**这就是 (a) 说的 "did not match"。

**(c) 请求体里两族 id 并存，边界与服务方切换对得上**：

| id 形态 | 数量 | `encrypted_content` | `content` | 归属 |
|---|---|---|---|---|
| `rs_resp_20260831031408…_1` 这类 | 93 | 无 | 1 段明文 | 早期由存量 Bun 服务（copilot-api-js @ :4141）交付的轮次 |
| `rs_<uuid4>_<idx>` / `msg_<uuid4>_<idx>` / `fc_<uuid4>_<idx>` | 28 | 有（5–11 KB） | 空 | **本代理 `ResponsesFramer` 交付的轮次** |
| `fco_01a054…`、`msg_01a057…`（UUIDv7） | 其余 | — | — | Codex 客户端自己生成的 |

按数组顺序（即时间顺序）看，两族交替出现，正是用户在两个服务之间来回切换的痕迹：idx 0–229 全 `resp_`（08-31 03:14–03:34），idx 230–244 突然变 `<uuid4>_<idx>`，idx 249–337 又回 `resp_`（04:11–04:22），idx 341 之后全是 `<uuid4>_<idx>`（09-01）。旁证：`input[338]` 是一条 `<model_switch>` developer 消息，Codex 自己也记录了这次切换。

**注意一个关键的不对称**：`resp_` 那一族全部 `encrypted_content = None`（Bun 侧交付的是解密后的 `content` 明文），所以它们从来没有触发过校验。**只有本代理交付的那一族既带密文又带假 id**，于是只有它们会炸。

**(d) 同伴已经跑过的隔离探针**（E3，16:43–16:44，各 3 个 item、约 11 KB）：拿 idx 230 那一块 10,960 字符的密文，只换外层 `id`，三次都 400：

| 探针 | 试的 id | 结果 |
|---|---|---|
| 16:43:47 | `rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_0`（本代理造的） | 400，同一条 message |
| 16:44:49.009 | `rs_resp_202608310314088f84634097214507_1`（Bun 那一族的） | 400，同一条 message |
| 16:44:49.288 | `rs_deadbeefdeadbeefdeadbeef`（手工编的） | 400，同一条 message |

三条负样本一致 ⇒「id 与密文里绑定的 item_id 不符就拒」这条规则成立。这三次的顶层字段也已经被削到最小（只剩 `model` / `input` / `stream` / `store` / `include` / `reasoning`），所以 `tool_choice`、`client_metadata`、`prompt_cache_key`、`text` 等在这三次里根本不存在，却照样 400——**这同时是对 §6.3 一整排候选的独立排除**。

**这组探针缺一个正对照**：没有一次用「上游真正为这块密文签发的 id」去发。所以**已证明的是「这三个 id 都不行」，尚未证明「正确的 id 就行」**。不过上游 message 已经把机制说出口了（`Encrypted content item_id did not match the target item id`），加上 (c) 的不对称分布，我判定这一条**强到可以据以行动**。

**要彻底闭合它需要的观测**：拿一次真实的 Copilot `/responses` 流式响应，记下上游 `response.output_item.added` 里 reasoning item 的原始 `id` 与 `encrypted_content`，把这一对原样回发。预期 200。这需要凭据，本次调查不做。

### 6.2 排名第二（未排除，但已降权到不足以行动）：请求体大小越过某个阈值

**证据强度：仅剩弱相关。**

重建各轮请求体大小（用 §5.2 那套复现方法逐段截断 `input`）：

| 请求（`input[:n]`） | 字节 | 结果 |
|---|---|---|
| `[:341]` | 852,155 | 200 |
| `[:345]` | 858,312 | 200 |
| `[:351]` | 879,939 | 200 |
| `[:353]` | 887,908 | 200 |
| `[:355]` | 893,594 | 200 |
| `[:359]` | **901,008** | **400** |

（「200」的依据：`input[341]` 之后那些由本代理框出来的 assistant 轮次存在于历史里，就证明产生它们的那次请求拿到了 200。）

阈值若存在，落在 (893,594, 901,008]，900,000 恰在窗口内。**但这条被两件事按下去**：

- 16:43 的探针只有 **11,408 字节**、3 个 item，照样 400，且是同一条 message。大小假说解释不了它。
- Copilot 对超限有专门的话：`Your input exceeds the context window of this model.` 与 code `model_max_prompt_tokens_exceeded`（本仓 `tests/int/test_error_envelope.py:606`、E5）。而 `gpt-5.6-sol` 的 `max_prompt_tokens` 是 922,000 **token**，901 KB 大约 23–26 万 token，远未触及。

保留它只是因为大小确实单调增长到失败点；它更可能是**假的共变**——真正单调增长的是那批坏 item 在上下文里的累积。

### 6.3 已被排除的候选（逐条给排除依据）

这一组的排除依据有两个来源：**(i)** 它们出现在同一线程里被 Copilot 答过 200 的请求上；**(ii)** §6.1(d) 的最小化探针里它们根本不存在，却仍然 400。

| 候选 | 判定 | 依据 |
|---|---|---|
| 模型不在目录 / 不支持 `/responses` | **排除** | §3.1：代码在网络前就会 `UnknownModel`/`EndpointNotSupported`；且 E4 目录快照明确宣告 `/responses`；且 Copilot 对此有专属 code `unsupported_api_for_model` |
| `additional_tools` input item 不被接受 | **排除** | (i) 本线程内多次 200 携带它；(ii) 探针里没有它；另有 E6 独立实测「Copilot 原生接受该 item（200）」 |
| `client_metadata` 顶层键不被接受 | **排除** | (i) Codex 每次都发，本线程内多次 200；(ii) 探针里没有它 |
| `include: ["reasoning.encrypted_content"]` 不被接受 | **排除** | (i) 本线程多次 200；E6 独立实测 200。（探针里**有**它，但正是它触发了校验——这不是它「不被接受」） |
| `prompt_cache_key` 不被接受 | **排除** | (i) 多次 200；(ii) 探针里没有它；E6 实测 200 |
| `text.verbosity` 不被接受 | **排除** | (i) 多次 200；(ii) 探针里没有它 |
| `store` 不被接受 | **排除** | 本次是 `store: false`。E6 实测只有 `store: true` 会 400，且 message 是 `store is not supported`、code 是 `unsupported_value` |
| `reasoning.effort: "high"` 不被接受 | **排除** | E4 目录宣告支持；E6 实测全模型 200 |
| `reasoning.context: "all_turns"` 未知子键 | **排除** | (i) 本线程多次 200 携带它。（这是唯一一个在任何已知实测里都没被单独探过的字段，但线程内正对照足够） |
| 顶层缺 `tools` | **排除** | (i) 多次 200；(ii) 探针同样没有 `tools` 而机制已另有解释 |
| `function_call` 缺 `namespace` | **排除** | 107 个调用全部无 `namespace` 且多次 200；且 namespace 名就是默认的 `functions`。hooyao 记录的 `Missing namespace for function_call` 是另一条 message，只在非默认 namespace 才要求 |
| 工具调用配对错误 / 孤儿 call | **排除** | §5.3 实测配对完好。Copilot 对此有专属措辞 `No tool output found for function call X.`（`exp/260820-tool-pair-probe/raw/G5-…`） |
| `custom_tool_call` id 前缀错 | **排除** | 5 个全是 `ctc_` 前缀，符合 Copilot 已知的前缀校验 |
| 请求头（`OpenAI-Beta`、Codex 自定义头等） | **排除** | §3.3：`openai-*` 与 `x-github-*` 前缀在 `header_policy/__init__.py:82` 被无条件删；其余头在成功轮次与探针里是同一套 |
| `1fb37cd` / `01c33f1` 引入了回归 | **排除** | `git show --stat` 显示两个提交**只动 `src/app/pipeline/delivery/**`**（响应方向）与其测试，请求方向零改动；且 `1fb37cd` 的时间（16:39）晚于失败（16:32） |
| 上游瞬时故障 / 路由抖动 | **排除** | 16:50 用**逐字节相同**的 body 重放，仍然 400。确定性复现 |
| 内容策略拦截 | **排除** | 新增的两条 user 消息是 `<environment_context>` 块与「继续」两个字；且 Copilot 对策略拦截有专属 code `cyber_policy` |

---

## 7. 派生发现（不属于本次五问，但影响处置）

### F-1　`1fb37cd` 的 native passthrough 就是这个缺陷的修法，但修不了存量污染

`delivery_policy.py:57-72` 的 `carries_upstream_natively` 对 `inbound_format is OPENAI_RESPONSES` 且未翻译、未合成的路由返回 `True`，`:96-99` 于是包上 `PassthroughFramer`。passthrough 引擎按 `output_index` 分组上游原始 SSE 事件再原样发出（`formats/openai_responses_passthrough.py` 的模块 docstring 明说「没有 item 类型分类，不认识的 item 也只按 output_index 分组」），**不造 id**。所以 HEAD 之后新产生的轮次是干净的。

但 Codex 线程里已有的 28 个假 id + 密文会一直回发。**在那个线程里，本次 400 会持续复现，直到这些 item 被挤出上下文或用户重开线程。**这是给用户的直接操作建议，且不需要改任何代码。

**给主会话的判断题（我不裁决）**：要不要在请求方向加一道「剥掉本代理自己签发过的 item id 所对应的 `encrypted_content`」的兼容处理，来救活存量线程？这会让老线程立刻可用，但也意味着丢掉那几轮的加密推理上下文，且是一条只为历史污染存在的补丁。属于产品分叉。

### F-2　翻译腿没有同一个缺陷，但机制未验证

Anthropic → Responses 的翻译腿在 `translation_driver/openai_responses.py:732-761` 的 `_reasoning_item` 里发出的是：

```python
{"type": "reasoning", "summary": _summary_parts(block.text), "encrypted_content": state.value}
```

**根本不写 `id`**。没有外层 id，就不会出现 id 与密文不符。这条腿一直在生产跑，反证它可用。但「上游对没有 `id` 的 reasoning item 是跳过校验还是另有规则」本次**未核**，只能说「不受同一缺陷影响」，不能说「已验证安全」。

### F-3　`capture_rejection` 不记请求头，本次证明该决定成立

`src/app/observability/rejection_capture.py:11` 的模块 docstring 明确写着这是**范围决定而非脱敏**。这个理由在本次成立（§6.3 已排除头部因素）。顺带记一笔：上游响应头里的 `x-request-id` 是向 GitHub 报障时唯一能对上号的凭据，目前**任何地方都没留**。是否值得加，属于产品分叉，不在本报告裁定范围。

### F-4　上游同一条拒绝有两种措辞，永远不要按 message 匹配

16:32 与 16:50 逐字节相同的 body 得到 `The resource you requested was not found.` 与具名的 `The encrypted content for item … could not be verified.`。本仓 E5（`260821-probe-upstream-sanitize-rules.md:144`）早就写过同一条教训的另一个实例：`does not support` 与 `is not supported via` 两种措辞共用 `unsupported_api_for_model`。区别在于**那一次 code 有鉴别力，这一次没有**（`invalid_request_body` 是 `/responses` 腿的通用桶）。所以在这条腿上，**message 与 code 都不是可靠判据**，任何按它们分类的重试/改写逻辑都要先考虑这一点。

---

## 8. 局限与未核项

1. **无凭据，未发任何真实上游请求。**「正确的 id 会 200」这个正对照没有做（§6.1 末）。当前结论建立在三条一致的负样本 + 上游自述的机制 + 代码里那两行之上。
2. **`ghc-msft` 的实际配置未读。**配置文件不在仓库里，本次没有去 `~/.config/ghc-api-proxy/` 找。base URL 指向哪个 host 属未核；但 §3.1 的代码守卫使这一点不影响结论。
3. **存量 Bun 服务（copilot-api-js）请求方向是否改写 `input[].id` / `encrypted_content` 未查。**这关系到「idx 249–337 那批经 Bun 发出的请求，body 里已经含有 idx 230–244 这些带假 id 的密文 item，为什么没炸」。可能的解释有两个——Bun 在请求方向剥掉了 `encrypted_content`，或那批请求走了别的路径——**两个都没有证据**。这是本条结论上唯一的松动处，建议后续单独查 `~/src/copilot-api-js/src/routes/responses/` 的请求侧处理。它不动摇根因（§6.1 的探针是独立的直接证据），只影响时间线叙述的完整性。
4. **我读的是主工作树 HEAD (`1fb37cd`) 的代码**，不是 16:32 那一刻运行中的进程代码。两者在请求方向与 `ResponsesFramer._item_id` 上无差异（`git show --stat` 已核，见 §6.3 末），但严格说这是推断而非直接观测。
5. **调查期间的写操作**：向 `/tmp/issue4-capture.json` 下载了 issue 的公开附件（只读取证），以及本报告。仓库内源码一个字未改，未跑测试，未提交。
6. **本次会话的 Bash 工具在 worktree 隔离检查上处于矛盾态**：Bash 守卫声称我隔离在 `.claude/worktrees/260901-issue4-reasoning-id`，而 `EnterWorktree` 声称我的 cwd 是仓库根、不是 worktree 会话，两者互斥，导致调查后期无法再执行任何 Bash（含 `cd <worktree> && …` 这种绑定写法）。所有证据都在此之前取齐。派发时指定的落盘路径是主树 `.dev/docs/tmp/`，被守卫拒绝，故落在 worktree 内同名相对路径，**请主会话 `mv` 回主树**。

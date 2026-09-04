# 本项目当前能力面盘点（ghc-api-proxy-py）

> 盘点对象：`/home/xp/src/ghc-api-proxy-py`，分支 `main`，`HEAD = 172adc2`。
> 用途：供主会话拿去与另一同类项目做逐项对照。
> 方法：从真实入口 `pyproject.toml:51 → src/app/__main__.py → src/app/cli.py` 顺流程读到底，再反向验证每个模块是否真有调用方。**没有从目录名推断存在性。**
> 只读盘点，未修改仓库任何文件（本报告除外）。
>
> **盘点时工作树是脏的**（并行会话正在改 `stream_cap.py` / `hosted_web_search.py` / `composition.py` / keepalive 文档等，`git status` 显示 `MM` 与 `??`）。所有行号取自当前磁盘内容，可能与 `HEAD` 有细微出入；结论层面不受影响。

## 规模与依赖（对照基线）

- Python 3.14+（`pyproject.toml:10`），入口脚本 `ghc-api-proxy = "app.cli:main"`（`pyproject.toml:51`）
- `src/` 229 个 `.py`，27837 行；`tests/` 151 个 `.py`，33920 行
- 运行时依赖（`pyproject.toml:11-34`）：`fastapi` / `uvicorn` / `typer`、`httpx[http2,socks]` + `httpx-ws`、**`anthropic` 与 `openai` 两个官方 SDK**、`pydantic` + `pydantic-settings[yaml]`、`orjson`、`structlog`、`textual`（TUI）、`tiktoken`（本地估算）、`platformdirs`、`cryptography`、四个 `opentelemetry-*`
- 开发依赖：`pytest` / `pytest-asyncio` / `pytest-cov`、`pyright`、`ruff`、`pyte`（仅 `tests/tui/`）、`zstandard`（仅 `tests/int/recorded/from_history.py`）
- **注意**：四个 `opentelemetry-*` 是运行时依赖，但活链路一个都不用（见第 6.5 节）；`httpx-ws` 同理（只服务 legacy 的 `routes/responses_ws.py`）。

---

## 0. 最重要的一条：这个仓库里有两条完整的请求链路，只有一条是活的

这是对照时最容易踩空的地方，先讲。

| | 活链路（live） | 死链路（legacy） |
|---|---|---|
| 应用工厂 | `src/app/server/pipeline_app.py:602` `create_pipeline_app` | `src/app/server/app_factory.py:157` `create_app` |
| 路由定义 | `src/app/server/inbound.py:33`（数据表）+ `pipeline_app.py:586` `build_router()` | `src/app/routes/*.py`（11 个 FastAPI router） |
| 配置对象 | `ProxyConfig`（`src/app/config/schema.py:344`） | `AppSettings`（`src/app/config/settings.py`） |
| 上游驱动 | `src/app/pipeline/direct_driver/base.py` + `src/app/pipeline/translation_driver/` | `src/app/pipeline/executor.py:196` + `src/app/anthropic/client.py` |
| SSE 解析/交付 | `src/app/pipeline/delivery/`（assembler / stream / blocks / anthropic_sse） | `src/app/openai/responses_stream_parser.py` + `src/app/delivery/responses_anthropic_stream.py` |
| 扩展点 | `src/app/pipeline/events.py` + `src/app/pipeline/subscribers/` | `src/app/hooks/`（registry / executor / loader / builtin） |
| 历史 | JSONL：`src/app/observability/request_log_file.py:31` | SQLite：`src/app/history/sqlite/` |

证据：

- CLI 的两条服务路径都只构造活链路 —— `src/app/cli.py:144`（`serve_inherited`，`--fd`）与 `src/app/cli.py:169`（`_serve_pipeline`，普通启动），两处都调 `create_pipeline_app(chain)`。
- `create_app` 全仓仅被 `tests/int/test_*_routes.py` 引用（`tests/int/test_azure_routes.py:7`、`test_gemini_routes.py:9`、`test_health_routes.py:7`、`test_history_routes.py:9`、`test_management_routes.py:8`、`test_responses_ws.py:13`、`test_anthropic_responses_route.py:26`），**没有任何生产入口引用它**。
- `src/app/server/__init__.py:6` 自陈这两者是并列的两条链，`pipeline_app.py:3` 的模块 docstring 直接写「Separate from `app_factory`, which still serves the existing implementation. Mounting both would give one path two owners.」

**权重档：强到可直接采纳。** 顺入口读了完整调用链，并做了反向 grep 验证。

对照时的实际含义：`src/app/routes/` 里的 `/v1/chat/completions`、`/v1/responses`、`/v1/embeddings`、Gemini `/v1beta/models/*`、Azure `/openai/deployments/*`、approval、history、management **全部不在运行中的服务里**。下面第 1 节按活链路给出真实端点表。

另有一处**残骸**：`src/app/lifecycle/rolling/`（含 `generation/`）在磁盘上只剩 `__pycache__`，`git ls-files src/app/lifecycle/` 不含任何 `rolling` 文件 —— rolling generation 机制已被删除，只有编译缓存留着。`contrib/systemd/rolling/` 同样只剩 `__pycache__/rolling-generation-launcher.cpython-314.pyc`。**权重档：强到可直接采纳**（`git ls-files` 与 `fd -e py` 双向确认）。

---

## 1. 协议端点

### 1.1 活链路实际暴露的 HTTP 路由

推理端点（全部 `POST`，由 `src/app/server/inbound.py:33-44` 的 `ROUTES` 表驱动，`pipeline_app.py:590-598` 注册）：

| 路径 | wire format | 流式 | 证据 |
|---|---|---|---|
| `/v1/messages` | `anthropic-messages` | 是 | `src/app/server/inbound.py:34` |
| `/v1/messages/count_tokens` | `anthropic-messages` | 否（`streamable=False`） | `src/app/server/inbound.py:35-40` |
| `/chat/completions`、`/v1/chat/completions`、`/openai/v1/chat/completions` | `openai-chat-completions` | 是 | `inbound.py:41` + `pipeline_app.py:592-593`（三前缀展开） |
| `/responses`、`/v1/responses`、`/openai/v1/responses` | `openai-responses` | 是 | `inbound.py:42` |
| `/embeddings`、`/v1/embeddings`、`/openai/v1/embeddings` | `openai-embeddings` | 否 | `inbound.py:43` |

注意 `/v1/messages` **不**做三前缀展开（`inbound.py:49` 只对非 Anthropic 格式加前缀；`pipeline_app.py:592` 只对 `openai-` 开头的格式加）。

运维端点（`src/app/server/ops_routes.py`，`pipeline_app.py:608` 挂载）：

- `GET /health/liveness` — `ops_routes.py:30`
- `GET /health`、`GET /health/readiness` — `ops_routes.py:36-37`；就绪判据是模型目录非空，空目录返回 503（`ops_routes.py:50-53`）
- `GET /models`、`GET /v1/models`、`GET /openai/v1/models` — `ops_routes.py:57-59`，OpenAI list 形状
- `GET /metrics` — `ops_routes.py:74`，返回 `prometheus_client` 默认 REGISTRY

**没有的**：Gemini、Azure、WebSocket `/responses`、approval API、history API、management API —— 这些只存在于 legacy 的 `src/app/routes/`。`ops_routes.py:8-10` 的 docstring 明说 History 与 management「are absent rather than answered with a plausible stub」。

**权重档：强到可直接采纳。**

### 1.2 端点级路由与降级

`decide_route`（`src/app/pipeline/routing.py`）决定 provider / model / endpoint / 是否翻译。支持：

- `model@format` 后缀显式指定目标格式（`routing.py:47-58`，`FORMAT_SEPARATOR = "@"`，未知格式是错误而非模型名的一部分）
- 入站格式对应的 endpoint 不可用时，按 `_FALLBACK_ORDER`（Anthropic → Responses → ChatCompletions → Embeddings，`routing.py:24-30`）降级
- 能力 fail-closed：目录为空则拒绝一切请求（`ops_routes.py:41-44` 的注释与 `composition.py:417-421` 一致）

---

## 2. 请求转换（Anthropic → OpenAI Responses）

主产品路径。翻译在 `src/app/server/handler.py:116-124` 触发，实现在 `src/app/pipeline/translation_driver/`：读端 `anthropic_messages.py:115` `from_anthropic_messages`，写端 `openai_responses.py:704` `to_openai_responses`，中间表示 `semantic.py:96` `SemanticRequest`。

### 2.1 覆盖情况逐项

| 字段 | 状态 | 实现位置与边界 |
|---|---|---|
| `system` | **有** | `anthropic_messages.py:116` → `semantic.py:131` `system_blocks_from_value`（string 与 block 列表两种拼写都接受）；写出为 `instructions` 单一字符串，块之间空行拼接（`openai_responses.py:110-123`）。**per-block metadata（含 `cache_control`）不随行**，记为 `SYSTEM_METADATA_NOT_CARRIED`（`openai_responses.py:117-122`）。模块 docstring（`openai_responses.py:1-16`）记录了实测依据：上游只接受字符串形式的 `instructions`，且它自己按前缀缓存，所以丢 marker 不丢缓存。 |
| `messages` / text | **有** | `anthropic_messages.py:107-112`（string content 也接受）；写出时按 role 决定 `output_text` / `input_text`（`openai_responses.py:459-463`）。 |
| `tools`（普通函数工具） | **有** | `openai_responses.py:126-141` `_function_tool`：`input_schema` → `parameters`，补 `type`；已是 Responses 形状的工具原样放行。 |
| `tools`（Anthropic server tool = web search） | **部分有** | `openai_responses.py:170-248`：只认 `web_search_<YYYYMMDD>` 一族（`_ANTHROPIC_SERVER_TOOL_FAMILIES = ("web_search_",)`，`openai_responses.py:149`），映射成 `{"type": "web_search"}`。`user_location` 白名单透传（键集 `openai_responses.py:164`），`max_uses` 丢弃并记录，`allowed_domains`/`blocked_domains` 按配置 `web_search_domain_restrictions` 决定 refuse 还是丢弃（默认 `drop_fields`，`schema.py:249`）。**`web_fetch_`、`memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_` 一律不映射**，原样travel（`openai_responses.py:146-148` 明确登记为缺口）。 |
| `tool_choice` | **部分有** | 不是任何 translator 认领的键，落进 `extensions`，跨格式时整体丢弃（见下）。**唯一例外**：`_carry_forced_search`（`openai_responses.py:619-646`）把点名 web search 声明的 `tool_choice` 补成 `{"type":"web_search"}`。docstring 给了实测依据：190 个真实 Claude Code 子请求里 95 个靠这个强制搜索。`_repoint_tool_choice`（:649）与 `_drop_dangling_tool_choice`（:675）只在同格式穿越时可达。 |
| `thinking`（请求参数） | **没有** | 不在 `_PASSTHROUGH_KEYS`（`anthropic_messages.py:31-33`），进 `extensions`；`semantic.py:116-128` `extensions_for` 在 `source_format != wire_format` 时**整体清空**并记 `EXTENSIONS_NOT_CARRIED`。也就是说 `thinking.budget_tokens` 到不了 Responses 腿，且**没有映射到 `reasoning.effort`** —— 全仓 grep `reasoning_effort` 无命中。 |
| assistant 侧 thinking 块 | **有** | `anthropic_messages.py:71-85` 读成 `BlockKind.REASONING`；写出见第 4 节。 |
| `image` | **部分有** | `anthropic_messages.py:102` 识别为 `BlockKind.IMAGE`；写出时 `openai_responses.py:464-465` **原样把 Anthropic 的 image block dict 塞进 Responses items**。Anthropic 的 `{"type":"image","source":{...}}` 与 Responses 的 `input_image` 形状不同，这条路径极可能被上游拒。**未找到任何 image 形状转换代码，已检索 `input_image` / `image_url` / `BlockKind.IMAGE` 全仓。** |
| `document` | **没有** | 无 `document` 分支，落到 `BlockKind.UNKNOWN`（`anthropic_messages.py:104`），写出时 `_item_from_block` 走到最后返回 `None` 并记 `BLOCK_NOT_CARRIED`（`openai_responses.py:492-493`），即**静默丢块**（只进 `Conversion`）。 |
| `cache_control`（消息块级） | **没有** | 文本块写出只保留 `{"type": part_type, "text": ...}`（`openai_responses.py:463`），块上的 `cache_control` 随 `raw` 一起被扔掉，且**不记 loss**（system 块那条会记）。 |
| `tool_result` | **有** | `anthropic_messages.py:94-101` 读；`openai_responses.py:473-478` 写成 `function_call_output`，`_flattened_output`（:532）把 block 列表压成字符串，非文本部分记 `TOOL_RESULT_CONTENT_FLATTENED`。`is_error` 在 Responses 侧无对应，丢弃且不记。 |
| `max_tokens` / `temperature` | **有** | `anthropic_messages.py:134-139` → `openai_responses.py:727-730`（`max_output_tokens`）。 |
| 其余未建模字段（`top_p`、`top_k`、`stop_sequences`、`metadata`、`context_management` 等） | **没有（跨格式时）** | 同 `thinking`，进 `extensions` 后整体丢，记一条 `EXTENSIONS_NOT_CARRIED`。`semantic.py:107-111` 的注释给了理由：把 Anthropic 的 `context_management` 发给 Responses 端点会得到 `failed to parse request`。 |

### 2.2 「未覆盖字段」的清单与告警机制

**有，但只有一半。**

- **有清单**：`LossCode` 枚举（`src/app/pipeline/translation_driver/semantic.py:31-48`）共 10 个码；`Conversion.record()`（:85）逐条累积；`TranslationRefused`（:51）是「宁可拒绝也不静默改变语义」的那一类，带 `code` 与 `field_path`，映射成 400（`handler.py:336-344`、`error_body` 的 `field_path` 输出在 `handler.py:379-383`）。
- **没有告警落点**：`handler.py:124`、`handler.py:207`、`handler.py:412` 把 loss 写进 `context.extras["conversion_losses"]` / `["response_conversion_losses"]`，**全仓没有任何读者** —— grep 这两个键只有这三处写入，`src/` 与 `tests/` 均无读取。也就是说：翻译丢了什么，运行时既不上日志行、也不进 JSONL 记录、也不回给客户端。
- 少数几条走 logger：web search 约束丢弃（`openai_responses.py:231-234`，WARNING）、web search 声明翻译（`openai_responses.py:310-315`，INFO）、tool pair 修复（`anthropic_request_hook.py:165-170`，INFO）。

**权重档：强到可直接采纳**（写入点与消费点都做了全仓 grep）。

### 2.3 翻译之前的请求修复

`shape_request`（`handler.py:107-109`）在**翻译之前**对 Anthropic body 跑 `fix_anthropic_request`（`src/app/pipeline/anthropic_request_hook.py:146`）：

- `context_management: {"edits": null}` → `{"edits": []}`（:39-56，带 2026-08-18 实测依据）
- `repair_tool_pairs`（:82-131）：删掉无人应答的 `tool_use` 与无来源的 `tool_result`，并丢弃被清空的轮次；**故意不去重同 id 的 tool_use**（:93，实测上游接受）
- `sanitize_empty_thinking`（:187）与 `destack_content`（:191），由 `hook_fix_anthropic_request.thinking` 配置驱动

另有三个 `attempt.prepare` 订阅者（`src/app/pipeline/subscribers/__init__.py:47-70`）：`builtin:server-tool-capability`、`builtin:hosted-web-search-gate`、`builtin:blank-text-blocks`。顺序由注册顺序固定，`tests/unit/pipeline/subscribers/test_builtin_subscribers.py` 钉住。

---

## 3. 响应与流式转换（Responses → Anthropic）

### 3.1 活链路的实现位置

- 流式：`src/app/pipeline/delivery/assembler.py:201` `ResponsesAssembler` 组装完整块 → `src/app/pipeline/delivery/blocks.py` 的 `BlockBuffer`/`DeliverySession` 缓冲 → `src/app/pipeline/delivery/stream.py:168` `stream_delivery` 出帧 → `src/app/pipeline/delivery/anthropic_sse.py` 渲染 Anthropic SSE。
- 非流式：`handler.py:392` `response_payload` → `chain.translators.translate_response`。
- **块级交付，不是 token 级**：`stream.py:1-8` 的 docstring 与 `assembler.py:3-4`（"A block is emitted when its closing event arrives, never on a delta"）。

### 3.2 `output_item.added` / `output_item.done` 之间 item id 变化

**已处理，用 `output_index` 而非 `item.id` 做键。**

`assembler.py:238-254` `_item_key`：

```
index = data.get("output_index")
if index is not None:
    return f"index:{index}"
```

docstring 直接写了原因：「Copilot sends a *different* `item.id` on `output_item.added` and `output_item.done` for the same item, so keying on the id meant `_close` never found what `_open` had created and the whole response assembled into nothing.」ids 只作为缺 index 的上游的 fallback。

同一问题在 reasoning signature 上也处理了：`_reasoning_signature`（`assembler.py:343-359`）从**关闭事件**读 `encrypted_content`，draft 只作 fallback。

**对照要点**：legacy 链路的做法完全不同 —— `src/app/openai/responses_stream_parser.py:942/953` 会在 id 变化时抛 `item_id_mismatch`，靠 `src/app/routes/anthropic.py:228` 的 `require_stable_responses_identity = settings.upstream.type != "copilot"` 把 Copilot 特例关掉。活链路没有这个开关，它是结构上不受影响。

**权重档：强到可直接采纳。**

### 3.3 未知 output item 类型怎么处理

**放行，不报错。** `assembler.py:256-267` `_open` 用一张三项映射表（`message`→text、`function_call`→tool_use、`reasoning`→thinking），**未命中时 `kind` 就是上游原始 item type**；`_close`（:279-321）的最后一个 `else` 分支（:317-318）把它渲染成 `{"type": "text", "text": draft.text}`。

两个特例：

- `web_search_call`：`assembler.py:279-294` 允许「没 `added` 只有 `done`」的迟到注册（docstring 说参考项目那边这个 item 直接消失了）；`:310-316` 从 `done` 事件读 `action` 渲染成文本行。
- 完全未知的**事件类型**（不是 item type）：`assembler.py:236` `return ()`，静默忽略。

对比 legacy：`responses_stream_parser.py:275-277` 会把未知 item 标 `unsupported` 并产出 `UnsupportedResponsesEvent`，`:920-923` 对未知 `output_index` 抛 `unknown_output_item`。活链路更宽松。

**权重档：强到可直接采纳。**

### 3.4 流截断的处理

`stream.py:275-294`：

- 见到 terminal（`response.completed` / `response.incomplete`）→ 正常发 `message_delta` + `message_stop`，`stop_reason` 空时兜底 `end_turn`（:289-291，注释说明这是「填空」而非「发明结局」）。
- **没见到 terminal 就 EOF** → 发 Anthropic SSE `error` 帧（`incomplete_responses_stream`），**并且不再发 `message_stop` 冒充成功**（:279-288）。这是 2026-08-20 的 `16dd68c` 补上的回归修复，登记在 `docs/agents/anthropic-responses-bridge/implementation.md:267`。
- 一个块都没提交过（`client_has_bytes` 未置位）→ 直接 return，客户端拿到 200 空 body（:276-278，注释承认这是遗留行为）。

`response.incomplete` + `incomplete_details.reason == "max_output_tokens"` → `stop_reason: max_tokens`（`assembler.py:330-338`）。

usage 转换：`assembler.py:362-372` `_anthropic_usage` 复用 `app/protocols/responses_anthropic.py` 的 `anthropic_usage_from_responses`，转换失败时返回 `{}` 继续交付（docstring 说明这是有意的优先级）。

---

## 4. reasoning / thinking 载体

**有自有版本化载体。**

- 实现：`src/app/pipeline/translation_driver/reasoning_carrier.py`（166 行），`encode_reasoning_carrier` / `decode_reasoning_carrier`。
- 出方向（Responses → Anthropic）：`assembler.py:343-359`（流式）与 `anthropic_messages.py:190-209` `_reasoning_to_anthropic`（非流式/回读）。空 `encrypted_content` 也发裸 marker 而不是空串（`assembler.py:346-348` 说明这条曾经写 `""`，两头都坏）。
- 回方向（Anthropic → Responses）：`anthropic_messages.py:50-64` `_reasoning_from_signature` 按签发者分类，`decoded.classification == "foreign"` → `OpaqueFormat.CLAUDE_SIGNATURE`（**不可跨界**），否则 `OpaqueFormat.PROXY_CARRIER`（可解回 `encrypted_content`）。写出在 `openai_responses.py:562-594` `_reasoning_item`：
  - `RESPONSES_ENCRYPTED` → 直接作 `encrypted_content`
  - `PROXY_CARRIER` 带 payload → 值精确还原；裸 carrier → 只还原 summary（:579-589）
  - 其它（即 Anthropic 自己的 signature）→ **拒绝**，记 `REASONING_STATE_NOT_PORTABLE`（:590-594）。docstring 明确：「writing it into `encrypted_content` would hand upstream something it never issued」。

### 4.1 版本号怎么标

命名空间 + 版本号写在签名字符串的前缀里（`reasoning_carrier.py:10-16`）：

| 常量 | 值 |
|---|---|
| `PROJECT_SYNTHETIC_REASONING_NAMESPACE` | `ghc-api-proxy:synthetic-reasoning:` |
| `PROJECT_SYNTHETIC_REASONING_SIGNATURE` | `ghc-api-proxy:synthetic-reasoning:v1`（裸载体，无 payload） |
| `PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX` | `ghc-api-proxy:synthetic-reasoning:v1:`（后接 payload） |
| `UPSTREAM_SYNTHETIC_REASONING_SIGNATURE` | `copilot-api:synthetic-reasoning:v1` |
| `UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX` | `copilot-api:synthetic-reasoning:v1:` |

自有 v1 的 payload 是 **base64url(JSON)**，JSON 恰好两个键 `{"tag": "openai.responses.reasoning.encrypted_content", "encrypted_content": ...}`（`encode_reasoning_carrier`，:52-66）。解码严格：canonical base64url 往返校验（`_decode_canonical_base64url`，:132-142）、JSON 重复键拒绝（`_unique_object`，:145）、键集必须**恰好相等**而非包含（:111）、`tag` 必须匹配、`encrypted_content` 必须非空字符串（:114-118）。

### 4.2 copilot-api-js v1 兼容路径

`decode_reasoning_carrier`（:77-100）返回九态 `ReasoningCarrierClassification`（:22-32）：

- 自有：`project_bare_v1` / `project_v1` / `project_malformed_v1` / `project_unknown_version`
- 兼容 copilot-api-js：`upstream_bare_v1` / `upstream_v1` / `upstream_malformed_v1` / `upstream_legacy_bare`
- 其它：`foreign`

兼容侧的 payload 是**裸 base64url 文本**（`_decode_upstream_payload`，:122-129 直接 `decoded.decode()`），不是 JSON —— 与自有格式的差异就在这里，符合项目规则里「兼容不要求复刻每个畸形解码边界」。解码顺序是**自有优先**（:79-88 在前）。

`is_direct_messages_synthetic_signature`（:69-74）用于在直连 Messages 腿上移除代理自签的载体。

### 4.3 一处值得注意的分类塌缩（活链路比 legacy 弱）

`decode_reasoning_carrier` 给出九态，但**活链路只用二分**。`anthropic_messages.py:50-64` `_reasoning_from_signature`：

```
if decoded.classification == "foreign":  → CLAUDE_SIGNATURE（不可跨界）
else:                                    → PROXY_CARRIER, encrypted_content=decoded.encrypted_content or ""
```

于是九态里的八态全归为 `PROXY_CARRIER`，后果：

- `project_malformed_v1` / `upstream_malformed_v1`（畸形载体）与 `project_bare_v1`（合法裸载体）**同形**，都变成「carrier 但无 payload」，写回 Responses 时都只还原 summary（`openai_responses.py:579-589`）。畸形载体不产生任何信号。
- `project_unknown_version`（未来的 v2）同样被静默降级成裸 v1，而不是被拒或被记 loss。

**legacy 链路在同一位置做得更细**：`src/app/anthropic/thinking/responses_reasoning.py:101-112` `decode_anthropic_thinking` 显式把 `project_unknown_version` / `project_malformed_v1` / `upstream_malformed_v1` / `foreign` 四态判为不可解码（`item=None`），并把 `malformed_payload` 与 `classification` 带出来。它的调用方是 `src/app/protocols/anthropic_responses.py:10`，属 legacy 请求方向。

`DecodedReasoningCarrier.malformed`（`reasoning_carrier.py:40-45`）因此**只有 legacy 一个消费者**（`responses_reasoning.py:110`），活链路不读。

注意 `src/app/protocols/responses_anthropic.py` 本身**是两条链共享的**（活链路经 `translation_driver/responses.py:28` 与 `delivery/assembler.py:21-24` 用它做响应方向与 usage 转换），所以不要把整个 `protocols/` 当成 legacy。

**权重档：强到可直接采纳**（读了 `reasoning_carrier.py` 全文 167 行，加上两个方向的四个调用点，并做了 `.malformed` 的全仓 grep）。

`redacted_thinking` 有专门处理：读在 `anthropic_messages.py:79-85`，写回在 `:197-198`。

---

## 5. 可靠性

### 5.1 重试

**有，两层，但顶层的「续写/重放」没接线。**

已接线的那层：`src/app/pipeline/direct_driver/base.py` 的驱动循环 + `LedgerBudget`（`base.py:63-71`）+ `RetryLedger`（`src/app/pipeline/retry.py:65`）。构造点在 `handler.py:136`。

重试原因分类 `reason_for`（`retry.py:40-61`）：

| 条件 | reason | 默认预算 |
|---|---|---|
| `PipelineRetry` | `streamReplay` | `schema.py:165-182` 的 `RetryStrategiesConfig` |
| `UpstreamTimeout` | `network` | 同上 |
| `UpstreamRateLimit` | `serverError` | 同上 |
| HTTP 401 | `githubTokenExpired` | 同上 |
| HTTP ≥ 500 | `serverError` | 同上 |
| 无 status（响应前失败） | `network` | 同上 |
| 其它 | `serverError` | — |

共享总预算 `max_total` 默认 20（`schema.py:184`），每个 reason 另有自己的计数器，一个抖动的原因不会吃光全部预算（`retry.py:1-4`）。

**没接线的那层**：`decide_stream_ending`（`retry.py:139`）与 `continuation_messages`（`retry.py:108`）—— 四态 `COMPLETE / REPLAY / CONTINUE / ABANDON`，含「已开流但未提交块不可重放」「已提交块可续写」的完整规则。**全仓生产代码零调用方**，只有 `tests/unit/pipeline/test_stream_ending.py` 与 `test_retry_strategies.py` 引用。`stream_delivery` 的截断分支（`stream.py:279-288`）直接发 error 帧，从不咨询它。配置 `upstream_request_retry.strategies.continuation`（`schema.py:159-163`，默认 `enabled: true`, `max_retries: 10`）因此**是一个不生效的配置面**。

**权重档：强到可直接采纳**（grep `decide_stream_ending|continuation_messages` 在 `src/` 只命中定义处）。

### 5.2 keepalive / ping

**有，且计时读的是自己那一侧。**

- 面向客户端的 SSE ping：`stream.py:29` `PING_FRAME = b": ping\n\n"`，间隔 `client_delivery.sse_ping_interval` 默认 15s（`schema.py:265`）。
- **计时器读客户端侧**：`_LastWrite`（`stream.py:39-47`）记录「最后一个字节交给客户端的时刻」，在 `stream_delivery` 的 `yield` **返回之后**打戳（`stream.py:199-201`，注释解释为什么在 `send` 之后而非之前）。`_keepalive_due`（`stream.py:154-165`）取 `max(ping_deadline, last_write.at + interval)`。
- 模块 docstring（`stream.py:7`）直接写了这条教训：「Keying the cadence on upstream events installed the guard backwards — it fired while upstream was quiet, and stayed silent while upstream was busy」。
- 另有「合成响应头」机制：`synthesized_response_headers_after_sec` 默认 240s（`schema.py:264`），超时且客户端还没拿到任何字节时，先发 `message_start`（`stream.py:253-262`）。注释记录了 2026-08-20 的实测：之前发占位空文本块，导致客户端把 `{"type":"text","text":""}` 存进历史并让下一次请求被上游拒。
- 上游侧 TCP keepalive 是另一套：`upstream_transport.tcp_keepalive_interval` 默认 15（`schema.py:133`），实现为真的 `SO_KEEPALIVE` + `TCP_KEEPIDLE` + `TCP_KEEPINTVL` + 4 次探测（`composition.py:73-102`）。HTTP 代理池要打补丁才生效（`composition.py:160-201`），SOCKS 路径做不到，只发 warning（`composition.py:203-222`）。
- `http2_ping_interval` 配置键存在但**明确不实现**（`composition.py:112` 的注释：httpx 0.28.1 / httpcore 1.0.9 都不暴露周期 PING）。

### 5.3 超时分层

`UpstreamRequestTimeoutsConfig`（`schema.py:146-152`）三项：

| 键 | 默认 | 守卫哪一段 | 执行点 |
|---|---|---|---|
| `response_header` | 0（关） | 响应头等待 | `handler.py:138` → `DirectDriver(response_header_timeout=)` |
| `stream_idle` | 0（关） | 流中上游静默 | `handler.py:510-515` → `pipeline_app.py:426-429` `with_idle_timeout` |
| `upstream_request_deadline` | 1200 | **整次尝试**（含 body 流） | `handler.py:131` → driver 固定 `attempt.deadline_at`；`pipeline_app.py:425-431` `with_deadline_at` 二次执行同一上界 |

外层还有客户端总时限：`client_delivery.client_request_deadline` 默认 3600（`schema.py:261`），在 `handler.py:309-322` `handle_bounded` 用 `asyncio.timeout` 实现，从准入起算、重试不重置。

两个流守卫的嵌套顺序有意为之：deadline 在外、idle 在内（`pipeline_app.py:423-424` 的注释）。`stream_idle` 默认 0 是刻意的（`handler.py:513-514`：「never to false-kill legitimate thinking」）。

`response_header` 默认 0 意味着这道守卫默认不生效 —— `docs/agents/delivery-keepalive/deferred.md` 里把它记作「一道从未实现的守卫」的相邻事项。

### 5.4 上游 token 刷新

**有，但只有惰性刷新，没有后台循环。**

- `CopilotTokenManager`（`src/app/ghc_client/tokens.py:36`）：`get_token()`（:76）检查 `expires_at - validity_margin`，过期则 `refresh()`；`refresh()`（:105）在 `anyio.Lock` 下做 single-flight；`_exchange_with_retry()`（:122）有有限次重试。
- GitHub token 来源链：CLI → Env → File（`composition.py:305-313` 组装，实现在 `src/app/auth/providers.py:38/55/82`）。
- **`run_refresh_loop`（`tokens.py:89`）在活链路没有启动方** —— 唯一 `start_soon` 在 `app_factory.py:105`（legacy）。`pipeline_app.py:630-671` 的 lifespan 只起了 tokenization flush 一个后台任务。
- **模型目录也没有周期刷新**：`refresh_catalogs` 只在 lifespan 启动时调一次（`pipeline_app.py:650`）；配置键 `model_providers.<name>.model_refresh_interval` 默认 3600（`schema.py:94`）**在活链路无消费者**（grep 只命中 `app_factory.py:106` 与 legacy `settings.py:192`）。

**权重档：强到可直接采纳。**

### 5.5 错误映射

`handler.py:325-389` 三个函数：

- `error_status`（:325）：`ProviderError`/`RoutingError`/`TranslatorNotFound`/`CountTokensRequestError`/`TranslationRefused` → 400；`CountTokensUnavailable` → 503；`UpstreamRateLimit` → 429；`UpstreamTimeout` → 504；`UpstreamRejected` → **透传上游自己的 status**；其余 → 502。docstring 记录了这是从「一切都落 502」修回来的。
- `error_headers`（:360）：只回 `Retry-After`，白名单。
- `error_body`（:371）：`{"error": {"type": <类名>, "message": ..., "code"?, "field_path"?, "upstream"?}}`。

**注意**：这**不是 Anthropic 的错误体形状**。Anthropic 规范是 `{"type":"error","error":{"type":"invalid_request_error","message":...}}`；这里外层是 `error`，内层 `type` 放的是 Python 类名（如 `UpstreamRejected`、`TranslationRefused`）。流式路径下的 error 帧走另一套（`stream.py:283-287` → `anthropic_sse.error_frame`，用 `WIRE_TYPES[ErrorCategory.UPSTREAM]`，那个是 Anthropic 词汇）。**两条路的错误词汇不一致**。

**权重档：强到可直接采纳**（两处代码都读了）。

被上游拒绝的请求体会落盘取证：`src/app/observability/rejection_capture.py:31` 起，只对非限流 4xx，保留最新 50 份，写到 `<data>/rejected/`，不写 header（`rejection_capture.py:11`）。

### 5.6 限流

- 主动（并发上限）：`InFlightLimit` 中间件（`src/app/server/admission.py`），`pipeline_app.py:612-615` 挂在最外层，`proactive_rate_limiter.max_inflight` 默认 50（`schema.py:198`）。**超限是排队等待，不拒绝、不断连**（`pipeline_app.py:610-611`）。
- 被动（429 反馈）：`RateLimiter`（`src/app/pipeline/rate_limiting.py`），每 provider 一个（`composition.py:413`），配置 `reactive_rate_limiter`（`schema.py:201-210`）。
- `client_delivery.hedge`（`schema.py:213-215, 266`）**只有配置没有实现** —— 用户已裁决「未来做，目前暂缓」（`docs/agents/delivery-keepalive/deferred.md` 的 D-4）。

---

## 6. 可观测性

### 6.1 SQLite 历史

**活链路没有。**

- `src/app/history/sqlite/schema.py:2` 定义单表 `entries` + 两个索引（`idx_entries_started_at`、`idx_entries_session`），写入在 `src/app/history/sqlite/writer.py`。
- 消费方 `HistoryConsumer` 只被 `app_factory.py:13` 与 `src/app/anthropic/client.py:36` 引用 —— **全是 legacy**。
- 配置 `history.enabled`（`schema.py:269-270`，默认 true）与 CLI `--history/--no-history`（`cli.py:228`）在活链路**无消费者**。

### 6.2 活链路实际的持久化：JSONL

`src/app/observability/request_log_file.py:31` `write_request_record`，由 `pipeline_app.py:241` 每个完成的请求调一次：

- 路径 `<platformdirs user_data>/ghc-api-proxy/requests/requests-YYYYMMDD.jsonl`（:22, :40）
- 每行一个 JSON：`{"at":..., "status":..., **asdict(RequestLine)}`（:41）
- 按文件名保留最近 14 个 UTC 日（`KEEP_DAYS = 14` 在 `:17`，`_prune` 在 `:52`）
- 永不抛异常（:45-48）

`RequestLine` 的字段集在 `src/app/observability/request_log.py`，由 `pipeline_app.py:210-239` 填充，来源是 `_Trace`（`pipeline_app.py:152-203`）：method / path / request_id / message_id / inbound_format / count_tokens / client_protocol / upstream_protocol / requested_model / model / status_code / started_at / duration_s / first_upstream_byte_s / bytes_in / bytes_out / usage / terminal_seen / stop_reason / blocks / tools / thinking / count_provider / count_provider_reason / dialect / attempts / detail / upstream_conn。

其中 `upstream_conn` 是上游 socket 身份快照（`pipeline_app.py:106-137`），**区分「没有」与「读不出来」**（`UNREADABLE` 哨兵，:71-90），docstring 点名读者是 `.dev/docs/upstream/h2-goaway/`。

### 6.3 日志行与 TUI

- 完成行：`pipeline_app.py:205-245` `_log_completion` → `format_completion_line`（`request_log.py`）；到达行默认 DEBUG（`pipeline_app.py:269`）。
- 流式结局三分：`_StreamAccounting._ending()`（`pipeline_app.py:501-514`）区分 `fail`（异常前无 terminal）、`fail`（drained 无 terminal）、`gone`（交付先于上游结束，含客户端离开与本进程关停）。第三档的分辨率不足已登记在 `.dev/docs/tui/deferred.md` 第 3 条。
- TUI footer：`src/app/observability/tui.py:158` 行（含 Textual App 与 rich Live），`footer.py:179` 行是纯函数的宽度算法。启用与否**探测而非配置** —— `footer_tui_or_none(chain.active_requests, chain.capabilities)`（`pipeline_app.py:660`），能力探测在 `src/app/observability/terminal.py:1-9`（拆成 live / color / unicode 三项，不是一个布尔）。
- 在飞请求登记：`ActiveRequestRegistry`（`src/app/observability/active_requests.py`），无论是否渲染都维护（`composition.py:270-271`）。

### 6.4 token 计数来源

**两个来源，显式区分，不混淆。**

`handle_count_tokens`（`handler.py:188-291`）：

- `ghc`：上游 `/v1/messages/count_tokens`（`handler.py:234-250` `ask_upstream`），**只在目标格式是 Anthropic Messages 时可用**（`handler.py:261` `upstream_counts`）。
- `local`：本地估算，`tiktoken` `o200k_base`（`src/app/tokenization/estimators.py:11`），按协议分开（`estimate_anthropic_input` / `estimate_responses_input`），再乘上学到的校准系数（`handler.py:252-254`，`src/app/tokenization/calibration.py`）。
- 上游答出真值时**回灌校准**（`handler.py:288-289` `calibration.learn`）。
- 顺序由 `inbound.anthropic_count_tokens.providers` 决定，默认 `["ghc", "local"]`（`schema.py:75`）。
- 估算结果在响应里标 `{"input_tokens": n, "estimated": true}`（`handler.py:291`）。
- 日志行报 `provider(no-counter,local)` / `provider(ghc-failed,local)` / `provider(local)` 三态（`handler.py:278-285`）。

校准状态跨进程持久化：`TokenizationStateStore(tokenization_state_path())`（`composition.py:275-277`，路径 `<data>/tokenization.json`），lifespan 里 `load()` + 每 5 秒 flush（`pipeline_app.py:63, 656, 662`）。

**流式/非流式响应的 usage 来自上游**：`assembler.py:323-341` `_read_terminal` 读 `response.usage`；本地 tokenizer 只用于 count_tokens 端点。

### 6.5 统计 / 报表

**活链路基本没有。**

- `GET /metrics`（`ops_routes.py:74`）返回 `prometheus_client` 默认 REGISTRY，即只有 Python 进程自带指标。
- `RequestTelemetry`（`src/app/observability/telemetry.py:17`，定义了 `ghc_proxy_requests` / `ghc_proxy_tokens` / `ghc_proxy_duration_ms`）与 `setup_metrics()` **只被 `app_factory.py:21` 引用**，活链路从不调用。
- 也就是说：**`/metrics` 端点在，业务指标一个都没有。**

**权重档：强到可直接采纳**（grep `telemetry` 全仓只两处）。

---

## 7. 认证

### 7.1 入站认证

**没有。已检索**：`src/app/server/` 全目录 grep `x-api-key|authorization|Authorization|api_key|bearer|Bearer` 只命中 `composition.py:332/338` 的 `api_key="proxy-managed"`（那是给 SDK 的占位符，不是入站校验）；`pipeline_app.py` 的 `_serve` / `_dispatch` 没有任何鉴权分支；`build_context`（`inbound.py:59`）只读 body 与 header 白名单。

客户端 header 只有两个会转发上游：`anthropic-beta`、`anthropic-version`（`src/app/pipeline/request_headers.py:17-23`）。白名单而非黑名单，docstring 说明理由是转发 `user-agent` / `x-stainless-*` 会替换掉 Copilot Chat 身份并被上游拒。客户端的凭据**在入口就被过滤掉，下游任何一层都拿不到**（`inbound.py:69-71`）。

默认监听 `127.0.0.1:4142`（`schema.py:69-70`），支持 TLS（`schema.py:59-64`，`src/app/server/tls.py`，可自签生成）。

### 7.2 上游凭据

链：GitHub token → Copilot token 交换。

- GitHub token 三级来源，按序：`CLITokenProvider` → `EnvTokenProvider` → `FileTokenProvider`（`composition.py:305-313`；实现 `src/app/auth/providers.py:38/55/82`）。file 位置由 `model_providers.<name>.github_token_file` 指定，未指定则默认位置（`composition.py:286-293`）。
- Device Flow 登录：`src/app/ghc_client/device_flow.py`，CLI 命令 `auth` / `login`（`cli.py:348-357`），`logout` 清除（`cli.py:360-364`）。
- Copilot token 交换与缓存：`CopilotTokenManager`（第 5.4 节）。
- 上游身份头：`src/app/ghc_client/headers.py` 的 `build_identity_headers` / `build_request_headers`（`composition.py:29-35` 导入）。

---

## 8. 配置

### 8.1 格式与位置

- 格式 YAML，schema 是 Pydantic（`src/app/config/schema.py:344` `ProxyConfig`，`Section` 基类在 :55）。
- 内置默认文件 `src/app/config/bundled-config.yaml`，`--generate-config` 复制它而不是 dump schema 默认值（`cli.py:46-55`，理由写在 docstring 里）。
- 加载 `src/app/config/loading.py:load_proxy_config`（`cli.py:106`）。
- 路径（`src/app/config/paths.py`）：
  - 配置文件 `platformdirs user_config / ghc-api-proxy / config.yaml`（:19-20），另有 spec 指定的 `user_data / config.yaml`（:23-27）
  - pidfile `<data>/standalone.pid`（:31）
  - 校准状态 `<data>/tokenization.json`（:35）
  - TLS 材料 `<data>/tls/`（:48-55）
  - 请求 JSONL `<data>/requests/`、被拒 body `<data>/rejected/`
  - `expand_user_path`（:58）专门处理 spec 里的 `$XDG_DATA_HOME/...` 拼写

### 8.2 CLI 参数

`ghc-api-proxy`（`pyproject.toml:51`），Typer，命令：

| 命令 | 状态 |
|---|---|
| `start` | 实现（`cli.py:212`） |
| `auth` / `login` | 实现（`cli.py:348/354`） |
| `logout` | 实现（`cli.py:360`） |
| `debug models` | 实现（`cli.py:405`，支持 `--provider` `--json`） |
| `setup-claude-code` / `setup-codex` / `list-claude-code` / `debug info` / `debug usage` | **未实现**，打印 "not implemented yet"（`cli.py:42-43`, :367-388, :455-458） |

`start` 的参数：`--port/-p`、`--host/-H`、`--fd`、`--graceful-timeout`、`--verbose/-v`、`--account-type/-a`、`--ghc-api-base-url`、`--rate-limit/--no-rate-limit`、`--history/--no-history`、`--github-token/-g`、`--proxy`、`--config`、`--manual`、`--generate-config`、`--restart`、`--pidfile`（`cli.py:213-238`）。

**其中四个在活链路无处安放，会打 warning 且不生效**：`--manual`、`--rate-limit/--no-rate-limit`、`--github-token`、`--account-type`（`cli.py:66-71` `_NO_HOME_IN_SPEC`，`cli.py:320-323` 输出 warning）。这是 2026-08-17 的用户裁决，名字与理由被显式留在代码里。

### 8.3 模型名映射

**有。** `model_mappings: dict[str, str]`（`schema.py:349`），在 `decide_route(mappings=chain.config.model_mappings)`（`handler.py:100`）消费，解析逻辑 `src/app/pipeline/model_resolution.py`。另有 `model@format` 后缀（第 1.2 节）与 `disabled_models`（`schema.py:95`）。

legacy 侧另有一套 `src/app/transform/model_resolver.py`（别名/标准化/override/family），活链路不用。

---

## 9. 生命周期

`src/app/lifecycle/` 全部 11 个文件都在版本控制内且被活链路用到（`rolling/` 除外，见第 0 节）。

| 能力 | 状态 | 位置 |
|---|---|---|
| 独立启动（自己 bind listener） | 有 | `entry.py:59` `run_standalone` ← `cli.py:168` |
| 继承 fd 启动（systemd socket activation） | 有 | `cli.py:134-152` `serve_inherited`（`--fd N`，uvicorn `fd=`），`cli.py:283-288` 注释说明这条路让 uvicorn 保留 listener |
| systemd `LISTEN_FDS` 协议解析 | **有代码，无生产调用方** | `lifecycle/activation.py:1-157`（`ActivatedSocketSet.from_systemd_environment`）只被 `tests/unit/lifecycle/test_lifecycle_activation.py` 引用。实际走的是 `--fd` 显式传参。 |
| sd_notify | 有 | `lifecycle/systemd/notify.py` |
| systemctl 交互 | 有 | `lifecycle/systemd/systemctl.py` |
| 优雅停机（阶梯式） | 有 | `lifecycle/standalone.py:345` 行，`lifecycle/shutdown.py`；`ShutdownReport` 在 `cli.py:177-209` `report_shutdown` 输出为最后一行日志。计入 `connections_asked_to_close` / `refused_requests` / `severed_connections` / `interrupted_connections` / `cancelled_requests` / `cleanup_timed_out`。docstring（`cli.py:186`）明确「ok 不是证书，是地板值」。 |
| 滚动重启（`--restart` + `SO_REUSEPORT` + SIGUSR2） | 有 | `entry.py:1-9` docstring，`entry.py:59-80`；pidfile 定位前任并拒绝签名不符的进程（`lifecycle/pidfile.py:257` 行） |
| 首字节路由适配 | 有 | `lifecycle/listener.py:349` 行，`FirstByteRoutingAdapter` |
| uvicorn 适配层 | 有 | `lifecycle/adapter.py:488` 行 |
| rolling generation | **已删除** | 见第 0 节 |

systemd 单元模板在 `contrib/systemd/`：`ghc-api-proxy.service`、`.slice`、`.socket`、`install-user.py`。测试在 `tests/systemd/`（3 个文件）。

活链路的 lifespan（`pipeline_app.py:630-671`）做的事：打版本横幅 → `refresh_catalogs`（失败不致命，降级为 not-ready）→ 载入 tokenization 状态 → 打监听地址 → 探测终端起 TUI → 起 tokenization 周期 flush。

**未见**：连接排空时对已 accept 连接的迁移（`.claude/rules` 与项目文档都强调 socket activation 不等于零停机迁移，代码与之一致）。

---

## 10. 测试与验证设施

`tests/` 共 151 个 `.py`，分组：`unit/`、`int/`、`component/`、`e2e/`、`tui/`、`systemd/`。

`pyproject.toml:56`：`addopts = "--strict-markers --strict-config --ignore=tests/tui --ignore=tests/e2e"` —— TUI 与 e2e 不在默认 sweep 里，点名路径才跑。

### 10.1 cassette 录制回放

**有，且是「真实上游录音」而非手写替身。**

- 数据：`tests/int/cassettes/*.json`，当前 5 个 —— `anthropic_to_responses_stream`、`history_anthropic_stream`、`history_responses_stream`、`responses_web_search_nonstream`、`responses_web_search_stream`。
- 回放：`tests/int/recorded/recorded_provider.py` —— 构造**真的** `GithubCopilotProvider` + 真的 openai/anthropic SDK + `ReplayTransport`，只有 transport 是假的（:1-11 的 docstring 把这条设计理由写死了：手写替身正是当年掩盖 item id 缺陷的东西）。
- 录制：`tests/int/recorded/record_cassette.py`，需凭据、手工跑（`PYTHONPATH=src:tests/int uv run python tests/int/recorded/record_cassette.py <scenario>`）。config 是 pin 死的而非 `load_proxy_config()`（:15-18 记录了这条坑）。脱敏在写盘方向而非穿透方向（:12-14）。
- 从既有服务历史库派生：`tests/int/recorded/from_history.py`，不需凭据不需上游。
- 消费：`tests/int/test_recorded_upstream.py`。

### 10.2 mock upstream

有。`tests/int/test_pipeline_app.py`、`tests/int/test_anthropic_block_delivery.py` 等用注入 provider 的方式（`build_chain(providers=...)`，`composition.py:366` 明确「injectable so a test can drive the whole path without reaching the network」）。

### 10.3 TUI 测试

有，独立分组。`tests/tui/`：`test_tui.py`、`test_footer_screen.py`、`_footer_driver.py`、`_naive_footer_driver.py`、`conftest.py`。用 `pyte` 做终端模拟（`pyproject.toml:42-43` 的注释说明为什么不能只断言字节流）。

### 10.4 基准测试

**未找到。已检索**：`fd -e py` 下 `tests/` 无 `bench` 命名文件，`pyproject.toml` 无 `pytest-benchmark` 依赖，无 `[tool.pytest]` benchmark 配置。仓库根有 `exp/` 与 `verification/` 目录（本次未展开）。

### 10.5 结构守卫

`tests/unit/test_module_boundaries.py`、`tests/unit/test_imports.py` —— 存在架构边界测试（与 `src/app/server/__init__.py:6` 的「不要 re-export」纪律呼应）。

---

## 11. hooks

**活链路没有在用 `src/app/hooks/`。**

`src/app/hooks/` 是一套完整的注册表机制：

- `types.py` 定义四类扩展点：`PayloadHook`（`PayloadPhase`：`pre_sanitize` / `post_sanitize` / `pre_send`，`types.py:12-15`）、`RetryStrategyFactory`、`ResponseHook`、`ObserverHook`（`ObserverEvent` 七态：`request_received` / `pre_sanitize` / `post_sanitize` / `pre_send` / `response` / `error` / `finalize`，`types.py:23-30`）。另有 `HookErrorMode`（`fail_request` / `continue`，`types.py:18-20`）。
- `registry.py:26` `HookRegistryBuilder`：名字唯一性、`builtin:` 前缀 + order 0..999 vs 用户 hook order ≥ 1000、`disabled` 列表、按 `(order, name)` 排序后冻结。
- `loader.py:12` `load_user_hook_modules`：按 `settings.hooks.modules` importlib 加载，要求模块导出 `register(builder, settings)`。
- `executor.py:167` 行 `HooksExecutor`：带 `user_timeout_ms`。
- builtin 五个（`builtin/__init__.py:17-41`）：`StripReadToolResultTagsHook`、`ThinkingDestackHook`、`DeduplicateToolCallsHook`（条件注册）、`PoisonedThinkingRetryFactory`、`TokenCalibrationSuccessObserver` + `TokenCalibrationFailureObserver`。

**唯一装配点是 `app_factory.py:111-127`（legacy），且吃的是 `AppSettings` 而非 `ProxyConfig`。** 活链路的 `build_chain`（`composition.py:356`）从不构造 `HookRegistryBuilder`。

配置侧的 `hooks:` 段（`schema.py:273-285`，六个订阅点：`on_client_request_parsed` / `on_upstream_request_ready` / `on_upstream_sse_block_ready` / `on_client_sse_block_ready` / `on_upstream_request_closed` / `on_client_request_closed`）**在活链路无消费者** —— grep `config.hooks` 无命中，且 `subscribers/__init__.py:11` 的 docstring 明说「The operator-facing `hooks:` subscription points in `config.example.yaml` are a different layer with their own undecided question — what a list item names — and this package deliberately does not pre-empt that answer by inventing a key of its own.」

活链路的等价物是 `src/app/pipeline/events.py` 的 `SubscriberRegistry`（`composition.py:395` 构造，`:404` 注册 builtin，`:409` freeze），**目前只有一个事件 `attempt.prepare` 有订阅者**（三个 builtin，见第 2.3 节），且**不可配置**（有意为之，`subscribers/__init__.py:9`）。驱动侧定义了 5 个事件（`direct_driver/base.py:29-40`：`attempt.prepare` / `attempt.succeeded` / `attempt.failed` / `request.succeeded` / `request.failed`），后四个**目前无订阅者**。

**权重档：强到可直接采纳。**

---

## 12. 已知缺口 / 明确 deferred

按文档来源分组。**我没有遍历 `docs/tmp/`（几百份历史评审），只按文件名检索了 deferred / status / decision 类。**

### 12.1 `docs/agents/delivery-keepalive/deferred.md`（工作树中正被修改）

- **D-7 未解决（缺陷，无岔路）**：`proxy` 三个来源（CLI `--proxy` / 环境变量 / 配置文件）在 `load_proxy_config()` 里被压平、不留 provenance，导致人写文档规定的优先级（CLI > 环境 > 配置）**无法实现**；当前实际行为是配置文件非空就完全忽略环境变量，与规定相反。
- **D-4 暂缓（用户已裁决）**：`client_delivery.hedge` 只有配置项没有实现。
- **D-2 待用户裁决**：`synthesized_response_headers_after_sec` 的窗口定义与人写文档冲突 —— 文档说「很久没有响应头」，实现从响应头**到达之后**才起算。
- 交还用户的文档问题两条：`synthesized_response_headers_after_sec` 中英文不一致；`http2_ping_interval` 在人写文档里仍被描述成生效的保活（实际做不到）。
- 已解决的记在同一份里（D-1、D-3a/b/c/d/e/f、D-5、D-6、D-8/9/10），对照时不必当缺口。

### 12.2 `.dev/docs/tui/deferred.md`

- **第 0 条（优先级最高，功能缺失）**：`/responses` 与 `/chat/completions` 入站的**回复汇总为空** —— `handler.reply_summary`（`handler.py:476-477`）对非 Anthropic 入站直接返回 `None`，那些请求的日志行不报告任何回复内容（推理块、工具调用、stop reason、token 用量）。缺一个 Responses 形状的读取器。
- **第 0.5 条**：上游 usage 自相矛盾时（缓存明细之和 > `input_tokens`、`reasoning_tokens > output_tokens`、`total_tokens` 对不上），`anthropic_usage_from_responses()` 只返回 `.wire`，把 `ResponseConversionFact` 与精确 usage 全丢了；管线照常给出「看起来正常」的数字，运行时无任何信号。usage 非法时（`ResponseConversionError`）两处都返回 `{}` 继续交付，「上游没报 usage」与「上游报了坏数据」在日志上同形。
- **第 1 条**：Responses 腿的 `end_turn` / `max_tokens` 仍是合成词（上游只发 `response.completed` / `response.incomplete`），与已按上游用词区分的 `think`/`reason`、`tool_use`/`function_call` 形成半新半旧的词汇。用户未裁决。
- **第 3 条**：`[GONE]` 分不出「客户端走了」与「本进程关停」。分辨率不足，非错误，不建议在无真实困扰前做。
- **第 4 条**：`context.extras["count_tokens_attempts"]`（形如 `ghc:0:APIStatusError`）**至今无消费者**，`ghc-failed` 说不出是超时/429/500 也说不出重试几次。

### 12.3 `.dev/docs/upstream/h2-goaway/deferred.md`

存在但本次未展开（文件名已确认：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/h2-goaway/deferred.md`）。相关结论散见于 `retry.py:148` 的注释（GOAWAY 的发起方不可观测，规则只能写成「本侧收到并交付了什么」）与 `pipeline_app.py:109` 的 `upstream_conn` 读者说明。**权重档：仅存档、不据以决策。**

### 12.4 `docs/agents/anthropic-responses-bridge/implementation.md` 的「结构怪味登记」（:263-293）

其中仍未闭合的两条与本盘点直接相关：

- `:267` —— 流截断的 **SSE 信封一半已闭合**（`16dd68c`），但 **failed History 一半未闭合**：`context.reply` 仍 gate 在 `terminal.seen`，被截断的回复不进 `reply`，需与 STR-04 同一切片裁决。
- `:268` —— `_StreamAccounting.finish()` 里 `trace.absorb` 无条件、`context.reply` 有条件，两套门有意保持不一致并就地注释（`pipeline_app.py:487-491` 的注释与之对应）。今天 `context.reply` **无读者**，所以无可观测影响。

同一份文档的 `:223`、`:261` 把产品整体状态标为 `UNVERIFIED`、部署 `NO_CUTOVER`，未闭合项包括：完整 tool/reasoning 矩阵、kernel partial-write（body 短写 / RST 分类）、真实 manager / cgroup 的 S5 验证。

### 12.5 `TODO_CURRENT.md`

顶部自陈**依据已悬空**：其来源 `docs/2604-rewrite/` 已被用户于 2026-08-20 裁定整体过期（早期 `copilot-api-js` 学习笔记），移入 `.dev/docs/archived-2604-rewrite/`。文件里 Phase 0–3 全打勾，但那些勾**描述的是 legacy 链路**（`routes/anthropic.py`、`anthropic/client.py`、`pipeline/executor.py`、`streaming/translator.py`）。**不要拿这份文件当能力面证据。**

### 12.6 本次盘点自己发现、文档里未见登记的缺口

按发现顺序，都做过反向 grep：

1. **`decide_stream_ending` / `continuation_messages` 无生产调用方**（第 5.1 节）—— 配置 `upstream_request_retry.strategies.continuation` 是空转的。
2. **`model_refresh_interval` 无生产消费者**，活链路模型目录只在启动时刷一次（第 5.4 节）。
3. **`CopilotTokenManager.run_refresh_loop` 无生产启动方**，只有惰性刷新（第 5.4 节）。
4. **`conversion_losses` / `response_conversion_losses` 无读者**，翻译损失记了但没人看（第 2.2 节）。
5. **`/metrics` 无业务指标**，`RequestTelemetry` 只在 legacy 装配（第 6.5 节）。
6. **`config.hooks` 六个订阅点无消费者**（第 11 节）。
7. **`history.enabled` / `--history` 无消费者**，活链路只有 JSONL（第 6.1/6.2 节）。
8. **`lifecycle/activation.py` 的 systemd `LISTEN_FDS` 解析无生产调用方**，实际走 `--fd`（第 9 节）。
9. **image block 跨格式时原样透传**，形状不匹配（第 2.1 节）。
10. **`document` block 静默丢弃**，只进 `Conversion`（第 2.1 节）。
11. **非流式错误体不是 Anthropic 形状**，且与流式 error 帧的词汇不一致（第 5.5 节）。
12. **`src/app/lifecycle/rolling/` 与 `contrib/systemd/rolling/` 只剩 `__pycache__` 残骸**（第 0 节）。

**权重档：1–8、12 强到可直接采纳**（都做了定义点 + 全仓调用点双向 grep）。**9–11 是个倾向、需更多样本** —— 我读了代码路径能确定行为，但没有实测上游对这三种情形的真实反应，也没有找到覆盖它们的测试。

---

## 13. 对照时建议优先看的几处

给主会话的建议，不是结论：

1. **先划清活/死链路**（第 0 节）。对方项目如果只有一条链，那么本项目 `src/app/routes/`、`src/app/hooks/`、`src/app/history/sqlite/`、`src/app/delivery/`、`src/app/openai/responses_stream_parser.py`、`src/app/pipeline/executor.py`、`src/app/anthropic/client.py` 这一大片**不应计入本项目的能力面**，但也不该当成「没做」—— 它们是做过、被新链路取代、按记忆规则「不得擅自删除已实现的功能」而保留的。
2. **item id 不稳定的处理方式**（第 3.2 节）是本项目最硬的一条差异化经验，两条链路给出了两种不同答案，值得单独对照。
3. **翻译损失有清单无读者**（第 2.2 节）与 **`config.hooks` 有面无实现**（第 11 节）是同一类形态：契约面已经铺好、消费侧空着。对照对方项目时值得问同一个问题。
4. **可靠性配置里有三处空转**（continuation、hedge、model_refresh_interval），对照配置表时容易被当成「已具备」。

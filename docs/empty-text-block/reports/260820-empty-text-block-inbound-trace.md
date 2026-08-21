# `/v1/messages` direct passthrough 腿：`messages[*].content` 全量读写点清查

- 日期：2026-08-20
- 仓库 HEAD：`f5c2e9f`
- 目标：定位生产 400 `messages: text content blocks must be non-empty` 的产出点，判定我方是否会造出空 text 块。
- 纪律：纯调查，未修改任何源码。下文每条判断都标注证据强度：**读到的代码**（直接读源码得出）／**实测**（运行了探针，命令与输出附上）／**推断**（由前两者推导，未直接观测）。

## 0. 结论摘要

**这条腿上没有任何一处代码能把一个非空 text 块变成空串或纯空白，也没有任何一处会新造出空 text 块。**（证据强度：读到的代码 + 实测的模块可达性；足以据此行动。）

更强的一条结论：**这条腿上根本没有任何"清空 text 块"的清洗器在跑**。项目里确实有一个专门删空 text 块的 `filter_empty_text_blocks`，但它只挂在 legacy 链路上，生产链路一次都不调用它。所以客户端送来的 `{"type":"text","text":""}` 会**原样**送到上游，被上游 400 拒绝。

因此下一步应查的方向是**客户端送来了什么**，而不是代理改了什么。第 5 节给出唯一可行的落盘/打印手段。

## 1. 实测：生产入口能拉起哪些模块

判据性探针（read-only，不发网络）：

```
cd /home/xp/src/ghc-api-proxy-py
PYTHONPATH=src uv run python -c "
import importlib, sys
importlib.import_module('app.server.pipeline_app')
print(len([n for n in sys.modules if n.startswith('app.')]))
"
```

输出 `98`，即 `app.server.pipeline_app` 的传递闭包只有 98 个 `app.*` 模块（全仓约 175 个可达模块 —— 该数字来自 `tests/unit/test_module_boundaries.py:1-11` 的文档注释，属**引用他人记录**，我未复核）。

各关键模块的可达性（实测，同一次探针）：

| 模块 | 是否被生产入口 import | exit |
|---|---|---|
| `app.server.app_factory` | **否** | — |
| `app.pipeline.executor` | **否** | — |
| `app.routes.*` | **否**（0 个） | — |
| `app.hooks` / `app.hooks.builtin.payload` | **否** | — |
| `app.history` | **否** | — |
| `app.anthropic.client` | **否** | — |
| `app.anthropic.request_preparation` | **否** | — |
| `app.anthropic.message_tools` | **否** | — |
| `app.transform.translator` | **否** | — |
| `app.pipeline.strategies` | **否** | — |
| `app.auto_truncate` | **否**（源文件不存在） | — |
| `app.anthropic.sanitize` / `.text_blocks` / `.tool_blocks` | **是（仅被 import，见 §3.1）** | — |
| `app.anthropic.thinking.destack` / `.protection` / `.strip_all` | 是 | — |

这一事实另有一条守卫测试固化：`tests/unit/test_module_boundaries.py:25-31` 断言 `app.server.app_factory`、`app.pipeline.executor`、`app.routes.*` 均不在新链路的闭包内。

## 2. 逐段链路：入站字节 → 发往上游

### 2.1 `src/app/server/pipeline_app.py`

| 位置 | 做什么 | 能否产出空 text 块 |
|---|---|---|
| `pipeline_app.py:167` | `await request.body()` 把请求体读完 | **不能**。只消费字节，不解析。（读到的代码） |
| `pipeline_app.py:176` | `parsed = await request.json()` | **不能**。`json.loads` 语义保真。（读到的代码） |
| `pipeline_app.py:183` | `body = cast(dict[str, Any], parsed)` | **不能**。纯类型 cast，运行时 no-op。（读到的代码） |
| `pipeline_app.py:186` | `build_context(route, body, request.headers)` | 见 §2.2 |
| `pipeline_app.py:224` | `handle_bounded(chain, context, _routed)` | 见 §2.3 |
| `pipeline_app.py:250` | `trace.bytes_in = len(response.request.content)` | **不能**。只取长度，不改内容。这是**实际发出字节数**的唯一读取点 —— 它证明字节存在过，但只保留了长度，见 §5。（读到的代码） |
| `pipeline_app.py:342-350` `_counted_upstream` | 计上游**响应**字节 | **不能**。响应侧，且 `yield chunk` 原样转发。（读到的代码） |

中间件 `InFlightLimit`（`pipeline_app.py:391-394` → `src/app/server/admission.py`）：`rg -n "body|content|messages|payload" src/app/server/admission.py` → **exit 1**（零命中）。**不能**，它只做并发计数。（实测 grep）

### 2.2 `src/app/server/inbound.py`

| 位置 | 做什么 | 能否产出空 text 块 |
|---|---|---|
| `inbound.py:72-74` | 校验 `model` 是非空字符串 | **不能**。只读 `model`。 |
| `inbound.py:76-78` | 读 `stream`，校验路由可流式 | **不能**。 |
| `inbound.py:80-86` | `RequestContext(payload=dict(payload), ...)` | **不能**。`dict()` 是**浅拷贝**：`messages` 列表对象和其中每个 block dict 与解析结果共享。不复制不等于会改写 —— 它一个字节都没动。（读到的代码） |

`forwarded_client_headers`（`src/app/pipeline/request_headers.py`）只处理 header，`rg -n "body|content|messages"` 的三条命中全在文档注释里。**不能**。（实测 grep）

### 2.3 `src/app/server/handler.py`

| 位置 | 做什么 | 能否产出空 text 块 |
|---|---|---|
| `handler.py:63-68` | `decide_route(...)` | **不能**。见 §2.4，`Route` 是 frozen dataclass，不碰 payload。 |
| `handler.py:74-77` | `if inbound_format is ANTHROPIC_MESSAGES: fix_anthropic_request(context.payload, ...)` | **这是这条腿上唯一改写 body 的地方**。见 §2.5。判定：**不能**产出空 text 块。 |
| `handler.py:79-87` | `if route.translation_required: chain.translators.translate(...)` | **在这条腿上不执行**。`refs/available_models.json` 中 Claude 模型广告 `['/v1/messages','/chat/completions']`，`routing.py:92-95` 命中 `inbound_format_supported`，`translation_required=False`（`routing.py:107`）。此判定的前提"目录里就是这么广告的"来自派发说明与 `docs/tmp/260820-websearch-400-our-side.md`，属**引用他人记录**，我未重新核对 `refs/available_models.json`。代码分支本身是**读到的代码**。 |
| `handler.py:90` | `context.payload["model"] = route.model_id` | **不能**。只写顶层 `model`。 |
| `handler.py:106` | `driver.run(context)` | 见 §2.6 |
| `handler.py:114-171` `handle_count_tokens` | **不在这条腿上**。`/v1/messages` 的 `InboundRoute.count_tokens` 为 `False`（`inbound.py:34`），`pipeline_app.py:201` 的分支不进。 |
| `handler.py:174-186` `_countable` | 同上，只在 count_tokens 分支；且它只 `dict(payload)` 后 `setdefault("max_tokens", 1)`，注释明说"never sent anywhere"。**不能**。 |
| `handler.py:257-273` `response_payload` / `276-289` `blocks_from_anthropic` / `292-309` `deliver_blocks` | 全是**响应**侧。与出站 `messages` 无关。 |

### 2.4 `src/app/pipeline/routing.py`

`decide_route`（`routing.py:66-110`）只读 `requested_model`、`inbound_format`、provider 目录，返回 frozen `Route`。全文无 `payload`/`messages`/`content` 字样。**不能**。（读到的代码）

### 2.5 `src/app/pipeline/anthropic_request_hook.py` —— 唯一的 body 改写点

`fix_anthropic_request`（`anthropic_request_hook.py:55-91`）对每条 message：

1. `normalize_context_management(payload)`（`:36-52`）—— 只在 `payload["context_management"]["edits"] is None` 时改成 `[]`。**不能**，不碰 `messages`。（读到的代码）
2. `sanitize_empty_thinking(content, "all_empty")`（`:85`，条件 `strip_empty`，默认 `True`）—— 实现在 `src/app/anthropic/thinking/protection.py:34-58`。它对 `type` 不在 `THINKING_TYPES` 的块**一律 `output.append(dict(block))` 原样保留**（`:43-45`）；只有 thinking/redacted_thinking 才可能被**删除**，且从不修改任何块的字段。**不能**产出空 text 块。（读到的代码）
3. `destack_content(content, strategy)`（`:89`，仅 `role == "assistant"`）—— 实现在 `src/app/anthropic/thinking/destack.py:22-52`。三条路径：
   - `passthrough`，或 `not _has_adjacent(content)`（没有相邻 thinking 块）→ `[dict(block) for block in content]`，逐块浅拷贝，**一字不改**（`:26-27`）。**这是绝大多数请求走的路径**。
   - `insert_text`（`:28-34`）→ 在相邻 thinking 之间插入 `{"type":"text","text": SYNTHETIC_SEPARATOR}`；`SYNTHETIC_SEPARATOR = "[ghc-api-proxy: thinking separator]"`（`:7`），非空且非空白。其余块 `copy.deepcopy` 原样。**不能**。
   - `move_blocks`（`:35-52`）→ 分离 thinking 与非 thinking；非 thinking 的过滤条件是 `block.get("type") != "text" or str(block.get("text","")).strip()`（`:40`），即**空/纯空白 text 块在此被丢弃**。补位用的也是非空的 `SYNTHETIC_SEPARATOR`（`:49`）。**不能**产出空 text 块 —— 它反而是唯一会删空 text 块的地方。
4. `entry["content"] = content`（`:91`）—— 写回上面三步产出的新列表。**不能**。

**综合判定：`fix_anthropic_request` 不能产出空 text 块，也不能把非空 text 变成空。**（读到的代码；置信足以据此行动。）

⚠️ 一个容易被误读的点：`move_blocks` 删空 text 块这件事**覆盖面极窄**。它同时要求 (a) `role == "assistant"`，(b) 该 message 的 content 里存在两个**相邻**的 thinking 块。user 消息永远不经过它；没有相邻 thinking 的 assistant 消息也不经过它（`destack.py:26` 直接短路 return）。所以它**不构成**对空 text 块的防线，不要把它当成"我们已经清过了"。

### 2.6 `src/app/pipeline/direct_driver/*`

| 位置 | 做什么 | 能否产出空 text 块 |
|---|---|---|
| `direct_driver/anthropic_messages.py:15-32` | 只绑定 `ENDPOINT = ModelEndpoint.ANTHROPIC_MESSAGES`，其余全继承 | **不能**。全文无 payload 逻辑。 |
| `direct_driver/base.py:130` | `await self._publish(EVENT_ATTEMPT_PREPARE, context, outcome)` —— 注释说"Subscribers edit the context payload" | **生产环境下这里没有任何订阅者**。见 §3.2。 |
| `direct_driver/base.py:133` | `attempt.payload = dict(context.payload)` | **不能**。浅拷贝，`messages` 共享。 |
| `direct_driver/base.py:136` → `_send`（`:216-241`） | `self._provider.send(endpoint, payload, ...)` | **不能**。原样转交。 |
| `pipeline/request.py:82-89` `begin_attempt` | `payload=dict(self.payload)` | **不能**。浅拷贝。 |

### 2.7 `src/app/model_provider/github_copilot.py` → `src/app/ghc_client/client.py`

| 位置 | 做什么 | 能否产出空 text 块 |
|---|---|---|
| `github_copilot.py:141-153` | 校验模型/endpoint 后 `self._client.send_anthropic_messages(payload, ...)` | **不能**。payload 原样。 |
| `ghc_client/client.py:131-145` `send_anthropic_messages` | 转 `_post_anthropic("/v1/messages", payload, ...)` | **不能**。 |
| `ghc_client/client.py:83-97` `_post_anthropic` | `self._anthropic.post(path, cast_to=httpx.Response, body=cast(AnthropicBody, dict(payload)), ...)` | **不能**。`dict(payload)` 浅拷贝后交给 Anthropic SDK 的 raw `post`。传的是**裸 dict 而非 typed model**，SDK 不做任何字段级重塑，只 JSON 序列化。（读到的代码 + §5 的实测证实 SDK 看到的 `json_data` 与传入 dict 逐字相同） |

**至此，从入站字节到发出字节，写过 `messages[*].content` 的代码只有 `anthropic_request_hook.py:91` 一处。**（实测：`rg -n "payload\[|\"messages\"\]|\"content\"\]|\.payload =" src/app/pipeline/ src/app/server/ src/app/model_provider/ src/app/ghc_client/ src/app/anthropic/thinking/` 在可达模块中只命中 `anthropic_request_hook.py:91`、`handler.py:85/90/132`、`direct_driver/base.py:133`；其余命中全在 §3 的 off-leg 模块或响应侧。exit=0）

## 3. 重点判定：sanitizer 到底挂在哪

### 3.1 `src/app/anthropic/sanitize/*` —— **被 import，但从不被调用**

`app.anthropic.sanitize` 出现在可达闭包里，容易让人误判"接上了"。真实机制是一条 import 副作用链：

```
anthropic_request_hook.py:14  from app.anthropic.thinking.destack import ...
  → 触发 app/anthropic/__init__.py:1  from app.anthropic.sanitize import sanitize_messages
    → 触发 app/anthropic/sanitize/__init__.py:1-3 拉入 result / text_blocks / tool_blocks
```

**被 import ≠ 被调用。** 判据性 grep（每个函数的**调用点**，`\bNAME\(`）：

| 函数 | 定义 | 生产调用点 | 在生产腿上？ | exit |
|---|---|---|---|---|
| `sanitize_messages` | `sanitize/__init__.py:7` | `anthropic/client.py:157`、`pipeline/executor.py:168` | **否**（两者均 off-leg） | 0 |
| `filter_empty_text_blocks` | `sanitize/text_blocks.py:4` | 仅 `sanitize/__init__.py:15`（即只被 `sanitize_messages` 调） | **否** | 0 |
| `process_tool_blocks` | `sanitize/tool_blocks.py:4` | 仅 `sanitize/__init__.py:11` | **否** | 0 |
| `strip_system_reminders` | `sanitize/system_reminders.py:6` | 仅 `sanitize/read_tool_result_tags.py:12` | **否** | 0 |
| `strip_read_tool_result_tags` | `sanitize/read_tool_result_tags.py:7` | `hooks/builtin/payload.py:37` | **否**（`app.hooks` 不可达） | 0 |
| `deduplicate_tool_calls` | `sanitize/deduplicate_tool_calls.py:7` | **无任何生产调用点**（只有 `tests/unit/test_anthropic_deep_sanitize.py:41`） | **否 —— 全仓死代码** | 0 |

调用者链条完整还原：

- `app/anthropic/client.py` ← `app/deps.py:7`、`app/upstream/bootstrap.py:10`、`app/pipeline/executor.py:9` ← `app/routes/anthropic.py:26` ← `app/server/app_factory.py`。**整条链在 §1 实测中不可达。**
- `app/hooks/builtin/payload.py` ← `app/hooks/builtin/__init__.py:3` ← `app/server/app_factory.py:16`。**同样不可达。**

**这一条对本次 400 至关重要**：`filter_empty_text_blocks`（`text_blocks.py:15`）的判据正是 `block.type == "text" and not (block.text or "").strip()` —— **它就是专门删空/纯空白 text 块的那个清洗器**，而生产链路一次都不调用它。所以客户端送来的空 text 块**没有任何东西拦它**。（实测 grep + 实测可达性；置信足以据此行动。）

顺带记两条各自的产出能力（即便它们 off-leg，避免下次重查）：

- `filter_empty_text_blocks` —— 只**删**块，不改字段。不能产出空 text 块。
- `strip_system_reminders`（正则 `<system-reminder>.*?</system-reminder>` → `""`）—— **理论上能把一个字符串清空**。但它只作用于 `type == "tool_result" and tool_name == "Read"` 且 `content` 是 `str` 的块（`read_tool_result_tags.py:9-12`），**从不碰 `type == "text"` 的块**，而上游报的是 "text content blocks"。即便它在线上也不是本次 400 的成因。
- `process_tool_blocks` / `deduplicate_tool_calls` —— 只做块/消息级的增删与 tool 名修复，不写 `text` 字段。

### 3.2 `src/app/hooks/*` 与订阅者 —— 生产环境为空集

`DirectDriver` 在 `attempt.prepare` 发布事件，订阅者可以改写 payload（`direct_driver/base.py:130-133`）。但生产环境注册了**零个**订阅者：

- `cli.py:139`（`serve_inherited`）与 `cli.py:161`（`_serve_pipeline`）都调用 `build_chain(config, http_client=http_client)`，**不传 `subscribers`**。
- `composition.py:221`：`subscribers=(subscribers or SubscriberRegistry[RequestContext]()).freeze()` → 空注册表。
- 实测 grep：`rg -n "build_chain|SubscriberRegistry"` 显示 `src/` 中除 `composition.py` 与 `cli.py` 外无第三处调用 `build_chain`；带 `subscribers=` 的调用点为**零**。exit=0。

`app.hooks.*` 那一套（`HooksExecutor` / `HookRegistryBuilder` / `register_builtin_hooks`）是**另一套完全不同的机制**，只在 `app/server/app_factory.py:16-19` 装配，与 `FrozenSubscribers` 无关。两者都不在生产腿上。（读到的代码 + 实测）

### 3.3 `src/app/auto_truncate/` —— 已删除的死代码

- `ls -la src/app/auto_truncate/` → 目录下**只有** `__pycache__/`，含 `__init__ / engine / token_limits` 三个 `.pyc`，时间戳 `Jul 17 17:12`。无 `.py` 源文件。
- `rg -n --text "auto_truncate" src/ tests/` → **exit 1**（含二进制搜索，零命中）。
- 唯一提及只在 `docs/` 与 `TODO_CURRENT.md:116`（记为已删除），以及 `docs/2604-rewrite/hooks-tokenization-spec.md:9`（明确裁决：代理不得改写历史）。

**判定：已删除的死代码，`.pyc` 是残留。不参与任何链路。**（实测；置信足以据此行动。）
附带一条已知未决项（**引用他人记录**，`docs/tmp/260814-audit-test-structure.md:59`）：曾有一个"`auto_truncate` 不得复活"的缺席守卫测试从未进入历史，现在无人守。不属本次任务范围，仅备录。

### 3.4 `src/app/anthropic/request_preparation.py`、`message_tools.py`

- `app.anthropic.request_preparation` **不可达**（实测）。唯一生产调用点 `anthropic/client.py:134`，off-leg。
- `prepare_anthropic_request`（`request_preparation.py:17-63`）确实改写 `messages[*].content`（`:40-44` 删合成 thinking 块、`:45-49` 删空 content 的 message、`:50-55` 硬编码 `destack_content(..., "move_blocks")`）。**即便如此它也不能产出空 text 块** —— 三步全是"删块"，无一处写 `text` 字段。
- `preprocess_tools`（`message_tools.py:6-30`）只碰 `tools`，不碰 `messages`。**不能**。

### 3.5 `src/app/transform/*`

- `transform/translator.py`、`transform/system_prompt.py` **不可达**（实测）。
- 可达的只有 `transform/model_resolver.py`（被 `tokenization/*` 与 `anthropic/features.py` 拉入），它做模型名归一化，不碰 body。**不能**。

### 3.6 `src/app/pipeline/translation_driver/*` —— 可达但本腿不执行

模块被 `build_chain` → `default_registry(config.model_translation)`（`composition.py:220`）拉入并构造，但 `handler.py:79` 的 `if route.translation_required:` 在本腿为 `False`，翻译器一次都不跑。`translation_driver/anthropic_messages.py:226-234` 与 `openai_responses.py:378-412` 那些 `payload[...] = ...` 写入因此不发生。**在本腿上不能**。（读到的代码）

### 3.7 `src/app/anthropic/thinking/strip_all.py` —— 可达但无调用者

`strip_all_thinking`（`strip_all.py:9-33`）写 `message["content"]`（`:32`），但它的生产调用点只有 `pipeline/strategies/__init__.py:114` 与 `pipeline/executor.py:263`，两者均 off-leg（`app.pipeline.strategies` 不在 98 模块闭包内）。它被 import 只是因为 `app/anthropic/thinking/__init__.py:1` 的再导出。且它同样只**删**块（thinking 块与恰好等于 `SYNTHETIC_SEPARATOR` 的 text 块），不写 `text` 字段。**不能**。

## 4. 问题一：默认 destack 策略是哪个

**默认是 `move_blocks`。**

映射链：

- `src/app/config/schema.py:244` —— `assistant_message_layout: AssistantMessageLayout = "move_and_synthetic"`（这就是默认值所在的 `file:line`）
- `src/app/config/schema.py:245` —— `strip_both_empty_thinking_blocks: bool = True`
- `src/app/pipeline/anthropic_request_hook.py:19-23` —— `_LAYOUT_STRATEGY = {False: "passthrough", "move_and_synthetic": "move_blocks", "synthetic_only": "insert_text"}`
- 故 `layout_strategy("move_and_synthetic")` → `"move_blocks"`

**实测有效值**（read-only 探针）：

```
PYTHONPATH=src uv run python -c "
from app.config.loading import load_proxy_config
c=load_proxy_config(); t=c.hook_fix_anthropic_request.thinking
print(repr(t.assistant_message_layout), t.strip_both_empty_thinking_blocks)"
→ 'move_and_synthetic' True
```

且 `config_file_path()` = `/home/xp/.config/ghc-api-proxy/config.yaml`，`exists: False` —— **本机没有用户配置文件覆盖它**，所以 schema 默认就是生产实际值。`src/app/config/bundled-config.yaml` 中 `rg -n "assistant_message_layout|hook_fix"` → **exit 1**（未出现，故不覆盖）。

**但这一条不要拿来解释本次 400。** 如 §2.5 的告警所说，`move_blocks` 只在 `role == "assistant"` 且存在**相邻 thinking 块**时才触发；两个条件之一不满足，`destack_content` 在 `destack.py:26` 直接短路成逐块浅拷贝，空 text 块原封不动通过。它不是一道防线。

顺带记一批**配置项已定义但全仓无读取者**（实测 grep，排除 `src/app/config/` 自身）：

| 配置字段 | 读取者 | exit |
|---|---|---|
| `hook_fix_anthropic_request.strip_system_reminder_from_Read` | **零** | 1 |
| `hook_fix_anthropic_request.thinking.strip_all_thinking_blocks_on_reject` | **零** | 1 |
| `hook_fix_anthropic_request.cache_control` | 零（命中的全是同名的 Anthropic wire 字段，非配置读取） | 0 |
| `hook_fix_anthropic_request.context_editing` | 零（命中的是 `anthropic/features.py` 的同名局部参数，且该模块 off-leg 使用） | 0 |
| `hook_fix_anthropic_request.extended_cache_ttl` | 零（同上） | 0 |
| `history.enabled`（实测有效值 `True`） | 零（在生产腿上；只有 `app_factory.py:73` 读，off-leg） | 0 |

这些属于"配置说开着、实际不生效"，对排障是陷阱：不要因为 `config` 里有 `strip_system_reminder_from_Read` 就以为有清洗在跑。（实测；置信足以据此行动。）

## 5. 问题二：能不能把**实际发往上游的 body** 落盘或打日志

### 5.1 项目自身：**没有**

- **history**：`app.history` 在生产入口的 import 闭包里**不存在**（§1 实测）。`ProxyConfig.history`（`schema.py:309`）存在且实测有效值 `enabled=True`，`cli.py --history/--no-history` 也接受该开关（`cli.py:101-102`、`:255-256`），但**这条腿上没有任何代码读它**。唯一读取者是 `app/server/app_factory.py:73-137`（legacy）。所以 `--history` 在生产路径上是**接受即无效**的开关。
- **debug dump**：`src/app/debug/` 只有 `__init__.py` 与 `models.py`，后者服务 `ghc-api-proxy debug models`（模型目录），与请求 body 无关。
- **capture / cassette**：`tests/integration/recorded/record_cassette.py` 能录真实流量，但那是测试工具，需要跑 `record_cassette.py <scenario>` 主动发起请求，不是在生产进程里旁路抓取。
- **请求日志行**：`pipeline_app.py:99-126` 的 `_log_completion` 只记 method/path/model/status/耗时/字节数/usage 等标量。`trace.bytes_in = len(response.request.content)`（`pipeline_app.py:250`）拿到的正是**实际发出的字节**，但只保留了长度，内容当场丢弃。
- 实测：`rg -n "payload\[|\"messages\"\]|\"content\"\]" src/app/observability/` 无与 body 落盘相关的命中。

**判定：项目自身没有任何机制把出站 body 落盘或打印。**（实测 + 读到的代码；置信足以据此行动。）

### 5.2 唯一可行手段：Anthropic SDK 的 DEBUG 日志（**实测可行**）

`ghc_client/client.py:91` 走的是 `AsyncAnthropic.post(...)`，SDK 在 `_build_request` 里会打印完整的 `json_data`：

`/home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/anthropic/_base_client.py:496-504`

```python
if log.isEnabledFor(logging.DEBUG):
    log.debug(
        "Request options: %s",
        model_dump(options, exclude_unset=True, exclude={"content"}),
    )
```

`exclude` 只排掉 `content`（原始字节体），**不排 `json_data`**。实测验证（未发网络，只构造请求）：

```
PYTHONPATH=src uv run python - <<'PY'
import logging
from anthropic import AsyncAnthropic
from anthropic._models import FinalRequestOptions
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
c = AsyncAnthropic(api_key="x", base_url="https://example.invalid")
opts = FinalRequestOptions.construct(method="post", url="/v1/messages",
    json_data={"model":"claude-opus-5","messages":[{"role":"user","content":[{"type":"text","text":""}]}]},
    headers={"authorization":"Bearer SECRET"})
c._build_request(opts)
PY
```

实测输出：

```
anthropic._base_client DEBUG Request options: {'method': 'post', 'url': '/v1/messages', 'headers': {'authorization': 'Bearer SECRET'}, 'json_data': {'model': 'claude-opus-5', 'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': ''}]}]}}
```

即空 text 块会**逐字**出现在日志里。

**两种开启方式**（均**未执行**，仅给出命令）：

1. `ghc-api-proxy start --verbose` —— `cli.py:238` 调 `setup_logging(log_level="DEBUG")`，`observability/logging.py:141` 把 root logger 设为 DEBUG。`setup_logging` 的降噪名单（`logging.py:145`）只有 `uvicorn.error / uvicorn.access / httpx / httpcore`，**不含 `anthropic`**，所以 `anthropic._base_client` 会继承 root 的 DEBUG 并经 root handler 输出。（读到的代码 + 上面的 SDK 实测；此路径本身**未端到端跑过**，属推断，但两段都已分别实测。）
2. 环境变量 `ANTHROPIC_LOG=debug` —— `anthropic/__init__.py:107` 在 import 时调 `_setup_logging()`，`anthropic/_utils/_logs.py:17-21` 读该变量并把 `anthropic` 与 `httpx` logger 直接设为 DEBUG。这条**不需要** `--verbose`，因为它设的是 logger 自身的 level，而 root handler 的 level 是 NOTSET，不会拦。（读到的代码；推断）

两者的缺点相同：`--verbose` 会把整个进程的 DEBUG 全打开（噪音大），`ANTHROPIC_LOG=debug` 会额外把 `httpx` 也拉到 DEBUG。

**一条须知会的事实**（陈述，不作裁决）：上面的日志行同时包含 `options.headers`，而 `ghc_client/client.py:95` 传入的 headers 正是 `request_headers()` 的产物，内含 Copilot 的 `Authorization` bearer。所以开 DEBUG 抓 body 的同时，日志里会有明文上游 token。是否可接受由你判断 —— 按项目既有约定（完整日志/录制中的临时 token 不视为需脱敏项），这里只作为事实告知，不建议加任何脱敏。

### 5.3 更省事的替代（建议，未执行）

若目标只是"看客户端到底送了什么"，比开 DEBUG 更精准的做法是在 `pipeline_app.py:183` 拿到 `body` 之后、`handler.py:77` 的 `fix_anthropic_request` 之前，各落一次 `messages` 的快照 —— 这样能同时区分"客户端就送了空块"与"我们改出来的"。但这是**改代码**，本次任务是纯调查，我没有做。列在这里供你裁决。

## 6. 完整判定表（一览）

| # | `file:line` | 做什么 | 能否产出空 text 块 | 在生产腿上 | 证据 |
|---|---|---|---|---|---|
| 1 | `server/pipeline_app.py:167` | 读完请求体 | 不能 | 是 | 代码 |
| 2 | `server/pipeline_app.py:176` | `request.json()` | 不能 | 是 | 代码 |
| 3 | `server/pipeline_app.py:250` | 取出站字节**长度** | 不能 | 是 | 代码 |
| 4 | `server/admission.py`（全文） | 并发计数 | 不能 | 是 | grep exit 1 |
| 5 | `server/inbound.py:80-86` | `payload=dict(payload)` 浅拷贝 | 不能 | 是 | 代码 |
| 6 | `pipeline/routing.py:66-110` | 决定路由，不碰 body | 不能 | 是 | 代码 |
| 7 | `server/handler.py:77` | 调 `fix_anthropic_request` | 不能（见 8-11） | 是 | 代码 |
| 8 | `pipeline/anthropic_request_hook.py:36-52` | `context_management.edits: null → []` | 不能 | 是 | 代码 |
| 9 | `anthropic/thinking/protection.py:34-58` | 删空 thinking 块；非 thinking 块原样保留 | 不能 | 是 | 代码 |
| 10 | `anthropic/thinking/destack.py:22-52` | destack；`move_blocks` **丢弃**空 text 块，分隔符非空 | 不能 | 是 | 代码 |
| 11 | `pipeline/anthropic_request_hook.py:91` | `entry["content"] = content` 写回 | 不能 | 是 | 代码 |
| 12 | `server/handler.py:85` | 翻译后替换 payload | 本腿不执行 | 否（分支不进） | 代码 |
| 13 | `server/handler.py:90` | 写顶层 `model` | 不能 | 是 | 代码 |
| 14 | `pipeline/request.py:82-89` | `begin_attempt` 浅拷贝 | 不能 | 是 | 代码 |
| 15 | `pipeline/direct_driver/base.py:130` | 发布 `attempt.prepare` | 无订阅者 | 是（但为空） | 代码+实测 |
| 16 | `pipeline/direct_driver/base.py:133` | `attempt.payload = dict(...)` | 不能 | 是 | 代码 |
| 17 | `model_provider/github_copilot.py:148-153` | 转 `send_anthropic_messages` | 不能 | 是 | 代码 |
| 18 | `ghc_client/client.py:83-97` | `_anthropic.post(body=dict(payload))` | 不能 | 是 | 代码+实测 |
| 19 | `anthropic/sanitize/text_blocks.py:4-20` | **删**空/纯空白 text 块 | 不能（只删） | **否** | 实测可达性+grep |
| 20 | `anthropic/sanitize/tool_blocks.py:4` | tool 块配对修复 | 不能 | **否** | 同上 |
| 21 | `anthropic/sanitize/system_reminders.py:6` | 正则清 `<system-reminder>`，**能把字符串清空** | 能（但只作用于 Read tool_result，非 text 块） | **否** | 代码+grep |
| 22 | `anthropic/sanitize/read_tool_result_tags.py:7-13` | 调 21，限 `tool_result`+`tool_name=="Read"` | 不能（不碰 text 块） | **否** | 代码+grep |
| 23 | `anthropic/sanitize/deduplicate_tool_calls.py:7-58` | 去重 tool 对 | 不能 | **否（全仓无调用者）** | grep |
| 24 | `hooks/builtin/payload.py:19-164` | 三个 payload hook | 不能（只删块） | **否** | 实测可达性 |
| 25 | `anthropic/request_preparation.py:17-63` | 删合成 thinking / 空 content message / destack | 不能 | **否** | 实测可达性 |
| 26 | `anthropic/message_tools.py:6-30` | 只改 `tools` | 不能 | **否** | 代码 |
| 27 | `anthropic/thinking/strip_all.py:9-33` | 删 thinking + 合成分隔符 | 不能 | **否（无可达调用者）** | grep |
| 28 | `transform/translator.py` / `system_prompt.py` | 协议翻译 | — | **否** | 实测可达性 |
| 29 | `pipeline/translation_driver/*` | 协议翻译 | 本腿不执行 | 模块可达，代码不跑 | 代码 |
| 30 | `pipeline/executor.py:168/174/263` | legacy sanitize + strip_all | — | **否** | 实测可达性+守卫测试 |
| 31 | `auto_truncate/` | — | — | **否（源文件已删）** | 实测 |

## 7. 给主会话的建议（未执行，供裁决）

1. **调查方向应转向客户端**。代理侧已排除。下一步是拿到那次 400 请求的入站 body。§5.2 的 `ANTHROPIC_LOG=debug` 是零改码手段（代价：token 明文入日志 + httpx 噪音）；§5.3 的入站快照是精准手段（代价：改代码）。二选一需要你裁决。
2. **`filter_empty_text_blocks` 从生产链路上掉队，这本身是个待裁决项**，不是本次 400 的原因但可能是它的解药。legacy 链路会删空 text 块，新链路不会 —— 这是一次**行为回退**，且看不出是有意为之（`anthropic_request_hook.py:8-9` 的模块 docstring 只提到 destack 与 sanitize_empty_thinking "已实现但新链路没人调"，没提 sanitize 那一套）。是补回还是明确记为"由客户端负责"，需要你定。
3. **`hook_fix_anthropic_request` 下有 4 个配置项全仓零读取者**（§4 表格）。配置说开着、实际不生效，是排障陷阱。建议单独立项处理，不要混进本次修复。
4. `deduplicate_tool_calls`（`sanitize/deduplicate_tool_calls.py`）与 `auto_truncate/__pycache__/` 是两处死代码残留，可顺手清理，但按项目"孤儿模块可以留着"的既有裁决，需你确认后再动。

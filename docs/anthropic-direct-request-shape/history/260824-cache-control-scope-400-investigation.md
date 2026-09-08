# `cache_control.ephemeral.scope` 400 调查：配置项实现状况与 direct path 改写链

**角色**：调查取证（investigator），不是评审，不做修复。
**日期**：2026-08-24。
**仓库状态**：`HEAD = 2c4ba59`（`feat: say an upstream context overflow in the words the client acts on`），工作树有未提交改动：`docs/.human-controlled/config.example.yaml` 与 `docs/.human-controlled/message-translation.md` 各有用户新增内容（见 §4.4）。
**证据面**：`src/`（含 `src/.archived/`）、`tests/`（含 `tests/.archived/`）、`docs/.human-controlled/`、`.dev/docs/`、参考项目 `/home/xp/src/copilot-api-js/`。**未看**：`.claude/worktrees/` 下四个同伴工作树（它们各自有 `schema.py` 的同一处定义，但不是主树，见 §7 否决项 R-1）。

**结论摘要**（详见各节）：

| 编号 | 结论 | 分量 |
|---|---|---|
| F-1 | `hook_fix_anthropic_request.cache_control` **完全没有实现**：四种模式在主树里零消费者，实测四种取值走完 `fix_anthropic_request` 后请求体逐字节相同 | 可据以行动 |
| F-2 | `hook_fix_anthropic_request.extended_cache_ttl` **完全没有实现**：三个字段零消费者；它依赖的 `model_capabilities.extended_cache_ttl` 在配置样例里也只存在于注释，从来不是一个真实的键 | 可据以行动 |
| F-3 | direct path 上请求体只经过 6 步改写，其中没有一步读 `cache_control`；`fix_anthropic_request` **确实在新链路上被调用**（不是「守卫留在 legacy 链路」那种形态） | 可据以行动 |
| F-4 | `src/.archived/` 里**没有** cache_control 的旧实现；只有一个发 `extended-cache-ttl-2025-04-11` beta 头的布尔开关，且没有任何调用方传 `True` | 可据以行动 |
| F-5 | 既有裁决与设计文档里，**没有任何一条关于 cache_control 的裁决，也没有任何待办台账登记过「四种模式未实现」** | 可据以行动 |
| F-6 | 测试完全没有覆盖 cache_control 改写；现有 5 处 `cache_control` 测试断言的都是「**别把它弄丢**」，且值一律是 `{"type": "ephemeral"}`，**没有一处带 `scope`** | 可据以行动 |
| F-7 | 前身项目 `copilot-api-js` 在 **`passthrough` 模式下也剥 `scope`**，与用户亲笔配置样例对 `passthrough` 的描述（「原样转发」）不一致 | 可据以行动（事实），但**该差异如何处置是用户的裁决，不是我的** |
| F-8 | direct path 会把客户端的 `anthropic-beta`（含 `prompt-caching-scope-2026-01-05`）原样转发给上游；即上游是在**收到该 beta 的情况下**仍然拒绝 `scope` | 强推断，非直接观测（见 §3.3 限定） |

---

## 1. `cache_control` 配置项到底实现了没有

### 1.1 它在哪被定义

- `src/app/config/schema.py:16`：`type CacheControlMode = Literal["disabled", "passthrough", "sanitize", "proxied"]`
- `src/app/config/schema.py:344`：`cache_control: CacheControlMode = "passthrough"`，是 `FixAnthropicRequestHook`（`:343`）的第一个字段
- `src/app/config/schema.py:417-419`：`ProxyConfig.hook_fix_anthropic_request` 挂载该 section

### 1.2 它在哪被消费——没有

**搜索面（一手命令）**：

```
rg -n --no-ignore --hidden 'cache_control|CacheControlMode|extended_cache_ttl' \
   -g '!.git/**' -g '!.claude/worktrees/**' -g '!.venv/**' -g '!exp/**' -g '!.dev/**' \
   --files-with-matches .
```

主树命中的源码文件只有 8 个，逐个核对后：

| 文件 | `cache_control` 出现的性质 | 是否读配置 |
|---|---|---|
| `src/app/config/schema.py:16,344` | 定义 | — |
| `src/app/models/anthropic.py:24,35,43` | Anthropic **wire 字段**的 pydantic 声明（`cache_control: dict[str, Any] \| None = None`），与配置无关 | 否 |
| `src/app/protocols/anthropic_responses.py:39,41,44-49,370-371,417-418,515-516,547-548` | Anthropic→Responses 翻译时把 wire 字段记为 `cache_control_not_supported` 降级 | 否 |
| `src/app/pipeline/subscribers/server_tools.py:124-129` | 重建 block 时**保留**原块上的 wire 字段 | 否 |
| `src/app/pipeline/translation_driver/openai_responses.py:6-7,109,169` | 注释与 `_WEB_SEARCH_IGNORED` 常量，说明 Responses 腿不带这个字段 | 否 |
| `src/app/pipeline/translation_driver/semantic.py:24` | 注释 | 否 |
| `src/app/pipeline/anthropic_request_hook.py:58` | docstring 里提到实测过带 `cache_control` 的请求，不是代码 | 否 |

**`CacheControlMode` 这个类型名在主树里只有两处**（`schema.py:16` 定义、`schema.py:344` 使用），没有第三处。

### 1.3 实测：四种取值走完 `fix_anthropic_request` 后请求体不变

只靠 grep 会漏掉「通过 `config.model_dump()` 之类间接读」的形态，所以补了一次真实执行。探针脚本 `/tmp/cc_probe.py`（一次性，不入库），命令：

```
PYTHONPATH=src uv run --no-project python /tmp/cc_probe.py
```

输入体带两处 `{"type": "ephemeral", "scope": "conversation"}`（`system[1]` 与 `messages[0].content[0]`），输出：

```
mode=disabled     unchanged=True  system[1].cache_control={"type": "ephemeral", "scope": "conversation"}
mode=passthrough  unchanged=True  system[1].cache_control={"type": "ephemeral", "scope": "conversation"}
mode=sanitize     unchanged=True  system[1].cache_control={"type": "ephemeral", "scope": "conversation"}
mode=proxied      unchanged=True  system[1].cache_control={"type": "ephemeral", "scope": "conversation"}
sanitize+extended_ttl unchanged= True {"type": "ephemeral", "scope": "conversation"}
```

**这个「全 True」有分辨力吗？** 单独看，`unchanged=True` 与「探针根本没跑对」同形。所以跑了一次正控制（`/tmp/cc_probe_control.py`）：同一个函数、同一个 `sanitize` 配置，输入里多一个 `context_management: {"edits": None}`——那是 `fix_anthropic_request` 已知会改写的字段（`anthropic_request_hook.py:117-129,227`）：

```
control unchanged= False context_management -> {"edits": []}
control cache_control -> {"type": "ephemeral", "scope": "conversation"}
```

**同一次调用里，`context_management` 被改了、`cache_control` 没被碰。** 这排除了「探针没跑起来」和「等值比较看不见变化」两族假数字。

**F-1 分量：可据以行动。** `cache_control` 是一个悬空配置项——schema 收得下这四个值，`extra="forbid"`（`schema.py:58`）也不会报错，但没有任何代码读它。**四种模式里包括 `sanitize`，而 `sanitize` 的定义逐字就是「strip non-standard fields like scope」——也就是说，用户亲笔文档承诺的、正好能修掉本次 400 的那个模式，是不存在的。**

---

## 2. `extended_cache_ttl` 实现了没有

### 2.1 定义

- `src/app/config/schema.py:17`：`type CacheTtl = Literal["5m", "1h"]`
- `src/app/config/schema.py:280-283`：`class ExtendedCacheTtlConfig(Section)`，字段 `enabled: bool = False`、`tools_system_ttl: CacheTtl = "1h"`、`messages_ttl: CacheTtl = "5m"`
- `src/app/config/schema.py:345`：`extended_cache_ttl: ExtendedCacheTtlConfig = Field(default_factory=ExtendedCacheTtlConfig)`

### 2.2 消费者——同样没有

`rg -n --no-ignore --hidden 'ExtendedCacheTtlConfig|tools_system_ttl|messages_ttl|CacheTtl\b|extended-cache-ttl'` 在主树（排除 `.venv`、worktrees、`.dev`）的全部命中：

- `docs/.human-controlled/config.example.yaml:485-500`（用户文档）
- `src/app/config/schema.py:17,280,282,283,345`（定义）
- `src/.archived/app/anthropic/features.py:67`（归档代码，见 §4）

**零个活代码消费者。** §1.3 的探针最后一行也覆盖了这一条：`enabled=True, tools_system_ttl="1h"` 与 `sanitize` 同时打开，请求体依然逐字不变。

### 2.3 一个额外发现：它引用的门控本身不存在

`config.example.yaml:488` 与 `:494-495` 写道该特性「还受模型支持（上方 `model_capabilities.extended_cache_ttl`）门控」。

`rg -n 'model_capabilities' docs/.human-controlled/config.example.yaml src/app/config/schema.py` 的**全部**命中就是这两行注释本身。**`model_capabilities` 从来不是这份配置样例里的一个键，schema 里也没有。**

**我的推断（非观测）**：这段注释连同 `cache_control` 那段一起是从 `copilot-api-js` 搬来的，而那边确实有 `modelSupportsExtendedCacheTtl(...)`（`request-preparation.ts:1008`）。搬运时保留了对一个未一并搬来的配置节的交叉引用。**分量：仅为倾向，需更多样本**——我没有去查 `copilot-api-js` 的配置文件里是否真有 `model_capabilities` 这一节。

**F-2 分量：可据以行动**（零消费者这一半）。§2.3 那一半是倾向级。

---

## 3. direct path 上请求体经过哪些改写步骤

**判据**：`POST /v1/messages` → `translation_required == false` → target format `anthropic-messages` → 发往上游 `/v1/messages`。

### 3.1 有序清单（从 HTTP 入口到 `sent`）

| # | 步骤 | 位置 | 动到请求体吗 | 碰 `cache_control` 吗 |
|---|---|---|---|---|
| 0 | 读 body、`json` 解析、要求是 object | `src/app/server/routes/inference.py:170-183` | 否 | 否 |
| 1 | `build_context`：**深拷贝**成工作副本 `payload`，原件存进 `original_payload`；请求头过 `REQUEST_FLOOR`（`forwarded_client_headers`） | `src/app/server/inbound.py:25-68`（深拷贝在 `:56`，注释在 `:63`）；`src/app/pipeline/request_headers.py:28-38`；`src/app/anthropic/header_policy/__init__.py:4-34` | 只拷贝 | 否 |
| 2 | `strip_attribution_lines`：剥 `system[0]` 开头的 attribution 行。**默认关**（`strip_attribution_header: bool = False`，`schema.py:277`） | 调用点 `inference.py:197-203`；实现 `src/app/pipeline/anthropic_request_hook.py:53-98` | 是（若开启） | **有意保留**：`:90` 用 `{**first, "text": stripped}` 重建块，正是为了不丢 `cache_control` |
| 3 | `inbound_payload = deepcopy(context.payload)`：留一份可重放的快照 | `inference.py:261-264` | 否 | 否 |
| 4 | `shape_request`：路由 → `apply_route` → `apply_path_header_policy(translated=False)` → `strip_denied_beta_flags` → **`fix_anthropic_request`** | `src/app/pipeline/driver.py:86-115`；`fix_anthropic_request` 调用在 **`driver.py:114`** | 是 | **否**（§1.3 实测） |
| 5 | auto mode classifier 短路（`decision != passthrough` 时不发上游） | `driver.py:123-140` | 否（走短路则整个不发） | 否 |
| 6 | `route.translation_required` 分支 —— **direct path 上跳过**；随后 `context.payload["model"] = route.model_id` | `driver.py:142-154` | 只改 `model` | 否 |
| 7 | `DirectDriver.run` 发布 `attempt.prepare`，五个 builtin 订阅者按序跑，随后 `attempt.payload = dict(context.payload)` | `src/app/pipeline/direct_driver/base.py:145-151`；注册在 `src/app/pipeline/subscribers/__init__.py:60-97`，由 `src/app/server/composition.py:493-509` 接线 | 是 | **否**（逐个见 §3.2） |
| 8 | `provider.send(ANTHROPIC_MESSAGES, payload, …)` → `send_anthropic_messages` → `_post_anthropic("/v1/messages", …)`：`dict(payload)` 后交给 Anthropic SDK `post` | `base.py:236-253`；`src/app/model_provider/github_copilot.py:141-175`；`src/app/model_provider/ghc_client/client.py:130-144`、`:84-98` | 否（只浅拷贝） | 否 |
| 9 | 请求头合成：`build_request_headers` 的自有头压在客户端头**之上**，客户端头里没被 `owned` 覆盖的原样带走 | `client.py:39-66`；`src/app/model_provider/ghc_client/headers.py:20-59` | — | — |

### 3.2 五个 `attempt.prepare` 订阅者，逐个核对

注册顺序（`subscribers/__init__.py:60-97`）：

1. `builtin:server-tool-capability`（`server_tools.py`）——把 `server_tool_use` / `*_tool_result` 块摊平成文本。**`:124-129` 显式把原块的 `cache_control` 复制到重建块上**，注释写明理由。不改其值。
2. `builtin:hosted-web-search-gate`（`hosted_web_search.py`）——只动 `tools`。
3. `builtin:anthropic-thinking-capability`（`anthropic_thinking.py`）——只动 `thinking` / `output_config`。
4. `builtin:blank-text-blocks`（`blank_text.py:78-89`）——会删掉 `system` 里的**全空白文本块**，也会删 `system` 键本身；对**留下来**的块不做任何字段级修改。
5. `builtin:anthropic-trailing-assistant`（`anthropic_trailing_assistant.py`）——只动 `messages` 末尾。

**没有一个读 `cache_control` 配置，也没有一个改写 `cache_control` 的值。**

### 3.3 「守卫被留在 legacy 链路上」这次不成立

项目记忆里有这条教训，所以我按它的判据正查了一遍：

- `fix_anthropic_request` 的**唯一**生产调用点是 `driver.py:114`，在 `shape_request` 里（`driver.py:75-115`）。
- `shape_request` 有两个调用方，都是活的：`handle`（`driver.py:118`，服务 `/v1/messages`）与 `handle_count_tokens`（`driver.py:244`，服务 `/v1/messages/count_tokens`）。
- `handle_bounded` → `handle` 由 `inference.py:266` 调用，那是 `_dispatch` 的主路径。
- 反面证据：`rg` 对 `fix_anthropic_request` 的全部命中里，除 `driver.py:21,114` 外全是 `tests/` 与 docstring。

**所以 `fix_anthropic_request` 确实在跑。** 它不改 `cache_control` 的原因不是「没接线」，而是**它的函数体里根本没有这段逻辑**（`anthropic_request_hook.py:220-265` 只读 `config.thinking.assistant_message_layout` 与 `config.thinking.strip_both_empty_thinking_blocks`，一次都没有引用 `config.cache_control` 或 `config.extended_cache_ttl`）。这是两种不同的缺陷形态，值得分清。

### 3.4 `anthropic-beta` 在 direct path 上是转发的

- `DIRECT_PATH_BLACKLIST: tuple[str, ...] = ()`（`request_headers.py:22`）——direct path 的黑名单是**空的**；`apply_path_header_policy(translated=False)` 走 `strict=False` 分支（`:41-54` + `header_policy/__init__.py:84-92`）。
- `REQUEST_FLOOR`（`header_policy/__init__.py:4-34`）里**没有** `anthropic-beta`。
- `strip_denied_beta_flags`（`request_headers.py:82-129`）按 `resolved_model` 匹配 `strip_anthropic_beta_flags` 表，逐 flag 剥离。
- `build_request_headers`（`headers.py:36-47`）的自有头里**没有** `anthropic-beta`，所以客户端那个不会被覆盖（`client.py:56-65` 的 `owned` 集合不含它）。

用户亲笔配置里那张表唯一的键是 `claude-sonnet-4.6`（`config.example.yaml:442-449`，**行号取自当前工作树，该处含一行用户未提交的新注释**），而用户本次新加的注释明说「事实上已被上文 `model_mappings` 覆盖，从而导致永远不会出现发往 `claude-sonnet-4.6` 的请求」。

**F-8 的推断链**：客户端（Claude Code）实际发的 `anthropic-beta` 值里含 `prompt-caching-scope-2026-01-05`——这条来自本仓 2026-08-18 的流量普查报告 `.dev/docs/pipeline-rewrite-parity/reports/260818-traffic-feature-gap.md:42-43`（429 个样本，三种取值，两种都含该 flag）。若那台机器的配置没有为 resolved model 配 strip 项，该 flag 就原样到达上游，而上游**仍然**拒绝 `scope`。

**分量：强推断，不是直接观测。** 我没有那台机器的配置文件，也没有那次请求的实际出站头。**要把它变成观测**，最省事的一手证据是 `~/.local/share/ghc-api-proxy/rejected/` 下本次 400 的落盘记录（`observability/rejection_capture.py` 会存出站请求体；`.dev/docs/anthropic-direct-request-shape/spec.md:35` 记录了上一次 400 就是这么取证的）——**建议主会话去读那个文件确认出站头里 `anthropic-beta` 的实际值**。

---

## 4. 既有裁决与设计文档

### 4.1 `docs/.human-controlled/config.example.yaml:467-500`（用户亲笔，最终权威）

**本节所有 yaml 行号取自当前工作树**（含用户未提交的 +12 行）；对应到 `HEAD = 2c4ba59` 的版本，这一段整体上移 1 行。

四种模式的定义逐字如下（`:474-483`）：

- `disabled`：strip all cache_control fields (no caching)
- `passthrough`：forward client cache_control as-is (default) — clients like Claude Code send their own well-tuned conversation breakpoints; the proxy stays out of the way
- `sanitize`：**forward but normalize to `{ type: "ephemeral" }` (strip non-standard fields like scope)**
- `proxied`：proxy controls injection — strip client breakpoints, then re-inject GHC-style …

默认值 `cache_control: passthrough`（`:483`），与 `schema.py:344` 一致。

`extended_cache_ttl`（`:485-500`）：`enabled: false`、`tools_system_ttl: 1h`、`messages_ttl: 5m`，并写明「仅当代理自己写断点时生效——即 `cache_control: proxied`（注入）或 `sanitize`（升级既有客户端断点）；`passthrough` / `disabled` 忽略」。

**这是**关于 cache_control **唯一一份用户亲笔的表态**，而且它是**配置语义的定义**，不是「遇到 `scope` 该怎么办」的行为裁决。

### 4.2 `docs/.human-controlled/message-format-reshape.md`（88 行，全文读过）

**零处提到 `cache_control`、prompt caching 或 `scope`。**

与本次相关的只有 `:37-49`《按需剥离 `anthropic-beta` 请求头的部分 flag》，示例里列出的四个要剥的 flag 中**包含 `prompt-caching-scope-2026-01-05`**（`:47`）——但那是给 `claude-sonnet-4.6` 的，理由写的是 `400 invalid beta flag`，**不是**为了避免 `scope` 字段被拒。这两件事在文档里没有被联系起来。

`:11-21`《剥离请求头》确立了 direct path 黑名单 / 翻译路径白名单的机制，翻译路径白名单「（暂无）」。

### 4.3 `.dev/docs/anthropic-direct-request-shape/`（全部四份文档读过）

- `README.md:3`：topic 范围明确写死为「`thinking` 与 `output_config` 该长什么样」。
- `spec.md:5`：「**范围**：……这几处字段：`thinking`、`output_config`、以及 `messages` 的**末尾角色**。**其余字段不在本文范围内。**」
- `spec.md:288-298` §8 待裁决与延后：A-1 ～ A-7，**没有任何一条与 cache_control 有关**。
- `status.md`：同样零处提及。

**所以：cache_control 不在这个 topic 的范围内，也没有被它登记为延后项。** 它现在**没有 owner**。

顺带记一处不属于本次调查、但读到了的不一致：`status.md:60` 写「见 spec.md **§7** 的 **A-1 ～ A-5**」，而 spec.md 的待办表在 **§8**、编号到 **A-7**。**分量：可据以行动的事实，但优先级低**，交主会话决定要不要顺手修。

### 4.4 工作树里用户刚加的未提交内容

- `config.example.yaml` +12 行：给 `strip_anthropic_beta_flags` 加了一句注释（说那张表被 `model_mappings` 架空），以及新增 `intercept_auto_mode_classifier` 三个键（`decision: allow`）。**与 cache_control 无关。**
- `message-translation.md` +4 行：新增两段总则，其中一句是 direct path 的授权来源 ——「对于直连路径，采用尽可能原样转发的原则。当我们需要理解和处理时，才分析和处理对应部分。」

**这一句很重要**：`anthropic-direct-request-shape/spec.md:166-170` 已经把它当作「主动改写直连请求体」的授权来源引用了。**但它此刻还是未提交状态**——也就是说 spec 引用的那句话，是用户**今天刚写进去还没 commit** 的。**分量：观测事实。** 它不改变授权成立与否，只是提醒引用者：这句话的 provenance 是工作树，不是某个提交。

### 4.5 已有的时点报告早就记过零消费者

两份独立报告在三四天前就查出过同一件事，只是没被提炼进任何活文档：

- `.dev/docs/hooks-subscription-migration/reports/260820-external-rewrite-surface.md:54`：「`FixAnthropicRequestHook` 共 5 个字段，**只有 `thinking` 下的两个被消费**。`cache_control`、`extended_cache_ttl`、`context_editing`、`strip_system_reminder_from_Read` 全部零消费者」；`:235-236` 的表格逐项列出「消费者：**无**」。
- `.dev/docs/empty-text-block/reports/260820-empty-text-block-inbound-trace.md:235,237`：`hook_fix_anthropic_request.cache_control` 与 `.extended_cache_ttl` 的配置读取命中数均为 **0**。

**这正是本项目 CLAUDE.md 警告的「报告成了唯一真相来源」的形态**：事实查清了四天，没有进 spec、没有进 deferred、没有进任何 status，于是今天以一个线上 400 的形式重新出现。

### 4.6 全仓 deferred 台账：零登记

`fd --no-ignore --hidden 'deferred.md' .dev/docs` 得到 8 份台账（`auto-mode-classifier`、`client-leg-formats`、`delivery-keepalive`、`error-envelope`、`server-layout`、`tui`、`upstream/h2-goaway`、`upstream/retry-and-continuation`）。对全部 8 份 `rg -i 'cache'`：**唯一命中是 `tui/deferred.md:19` 的 `cache_read_input_tokens`，与本主题无关。**

**F-5 分量：可据以行动。** 「cache_control 四种模式未实现」这件事**从未被任何台账登记过**。

---

## 5. 测试现状

### 5.1 有没有测 cache_control 改写——没有

主树里 `cache_control` 出现在 5 个测试文件，逐个核对：

| 文件:行 | 断言什么 | 值里带 `scope` 吗 |
|---|---|---|
| `tests/unit/pipeline/test_attribution_stripping.py:29-46` | 剥 attribution 行后 `cache_control` **还在** | 否 |
| `tests/unit/pipeline/subscribers/test_subscribers_server_tools.py:276-283` | 摊平 server tool 块后 `cache_control` **还在** | 否 |
| `tests/unit/pipeline/test_auto_mode_classifier.py:68` | 只是构造一个真实形状的 body，`cache_control` 是背景噪声 | 否 |
| `tests/unit/transform/test_translator.py:92-98` | 翻译时 system block 的 metadata 保留 | 否 |
| `tests/unit/pipeline/translation_driver/test_translation_driver.py:29,34,65,75` | `cache_control` **过不了字符串形态**，必须记成一条 loss | 否 |

**五处的值一律是 `{"type": "ephemeral"}`，没有一处带 `scope` 或 `ttl`。** 没有任何测试用 `CacheControlMode` 的四个取值做参数，也没有任何测试断言过某个模式下的输出形状。

### 5.2 `test_attribution_stripping.py:29-46` 具体断言了什么

```python
def test_block_metadata_survives_the_edit() -> None:
    """`cache_control` is the reason this rebuilds the block instead of replacing it.

    Claude Code marks the first system block as a cache breakpoint. Dropping that while removing a line from the same block would silently move where the prompt cache begins, which costs money on every subsequent request and shows up nowhere.
    """
```

断言三条（`:44-46`）：返回值 `== 1`（剥掉一行）、`payload["system"][0]["cache_control"] == {"type": "ephemeral"}`、`payload["system"][0]["text"] == SYSTEM`。

**它守的是「不要把 `cache_control` 弄丢」，方向与本次需求恰好相反。** 这条测试与「剥掉 `scope`」不冲突（它的值里没有 `scope`），但它固化了一个态度：本项目现有测试对 `cache_control` 的立场统一是**保全**，没有任何一处考虑过**归一化**。

**F-6 分量：可据以行动。**

---

## 6. 前身项目 `copilot-api-js` 怎么做的（供对照，不是判据）

**为什么值得记**：本项目的这四个模式名、默认值、以及配置注释的措辞都来自它，所以它的实际行为是理解这份配置意图的最强旁证。**但它不是权威**——CLAUDE.md 明说「do not copy its defaults or defects as project contracts」。

### 6.1 主动式：`applyCacheControlMode`

`/home/xp/src/copilot-api-js/src/lib/anthropic/request-preparation.ts:1001-1050`，四个 case 齐全。**关键在 `passthrough` 那一支（`:1019-1025`）**：

```ts
case "passthrough": {
  // 只挖已知地雷（GHC 未支持的 cache_control 子字段，如 scope），保留客户端精调断点。
  const blacklist = collectUnsupportedCacheControlSubfields(model, ctx.opts.excludeCacheControlSubfields)
  const stripped = filterCacheControlSubfields(wire, blacklist)
  if (stripped.length > 0) ctx.strippedCacheControlSubfields = stripped
  break
}
```

而黑名单的内置项（`:298-299`）：

```ts
/** GHC 上游不支持的 cache_control 子字段（内置地雷）。scope 由 prompt-caching-scope beta 引入，GHC 未启用。 */
const BUILTIN_UNSUPPORTED_CACHE_CONTROL_SUBFIELDS: ReadonlyArray<string> = ["scope"]
```

`collectUnsupportedCacheControlSubfields`（`:306-315`）把三个来源并起来：内置地雷、配置 `stripCacheControlSubfields`、以及 reactive 腿学到的字段。

**F-7：前身在 `passthrough` 下也剥 `scope`。** 而本项目用户亲笔的 `config.example.yaml:476-477` 把 `passthrough` 定义为「forward client cache_control **as-is**……the proxy stays out of the way」。**这两者不一致，而且不是措辞差异——是行为差异。** 那句注释里对 `scope` 的处置只出现在 `sanitize` 一档。

**这个差异怎么办不是我能决定的**：`config.example.yaml` 是用户亲笔的最终权威文档，改它的语义是用户的裁决。我只把事实摆出来。

### 6.2 反应式：`cache-control-subfield-rejection-retry`

`/home/xp/src/copilot-api-js/src/lib/request/strategies/cache-control-subfield-rejection-retry.ts`：

- `:39` 正则 `/\.cache_control\.\w+\.([a-z_]\w*): Extra inputs are not permitted/gi` ——**逐字匹配本次这条 400 的 message**。
- `canHandle`：`error.type === "bad_request" && status === 400 && !attempted`。
- `handle`：把解析出的字段写进 endpoint-wide 的学习缓存（`markAnthropicUnsupportedCacheControlSubfield`），带 `prepareHints.excludeCacheControlSubfields` 重发一次，**per-instance 一次性**（`let attempted = false`）。

本仓 2026-08-18 的报告 `.dev/docs/pipeline-rewrite-parity/reports/260818-retry-gap.md:22,47` 已经把这条列为「新链缺失的 retry 策略」之一，并写明「搜索 `src/app` 的 `cache_control` 只命中 model／旧模块，不存在错误 matcher、per-endpoint learned strip 或 retry hint」。**结论至今未变。**

### 6.3 与既有裁决的张力（只报告，不裁决）

`anthropic-direct-request-shape/spec.md:158-162` §3.2 为 `thinking` 一族**选择了主动式而非反应式**，理由是 `docs/.human-controlled/upstream-retry-and-continuation.md:9` 把 400 列进「无法继续」。**同样的论证形状可以原样套到 cache_control 上**（主动剥 `scope` 就不会产生这个 400），但那是设计决定，不是调查结论。

---

## 7. 我排除了什么

**硬性要求，逐条写下。**

| 编号 | 考虑过的解释 / 走过的路 | 为什么否决 |
|---|---|---|
| R-1 | **`.claude/worktrees/` 下四个同伴工作树里可能有实现** | 首轮 `rg` 确实在 `upstream-error-events`、`one-ending`、`260822-never-silent-upstream-failure`、`delivery-keepalive` 四棵树里命中了 `CacheControlMode`。逐一核对行号后发现**全部是同一处 schema 定义的副本**（`schema.py:16` + `:288`/`:323`），没有一棵树有消费者。且它们不是主树，不能作为「实现了没有」的答案。**后续搜索一律用 `-g '!.claude/worktrees/**'` 排除。** |
| R-2 | **`src/.archived/` 里有被搁置的旧实现** | 这是任务点名要查的。`fd` 列出 `src/.archived/` 全部 **83** 个文件，`rg -i 'cache\|ephemeral\|ttl\|scope'` 只命中 `app/anthropic/features.py:56,66-67`——一个 `extended_cache_ttl: bool = False` 参数和一句 `betas.append("extended-cache-ttl-2025-04-11")`。**那是 beta 头发射器，不是 body 改写**。`request_preparation.py`（归档链里唯一调用它的地方，`:5,58`）对 cache/ephemeral/ttl/scope 的 grep **exit 1，零命中**。所以：**归档树里没有 cache_control 的旧实现可供复活**，只有 beta 头那一小块，而且没有任何调用方传 `extended_cache_ttl=True`：`rg 'build_anthropic_beta_headers'` 全仓（含 `tests/`）共 **6 行、4 个文件**——`src/.archived/app/anthropic/features.py:50`（定义）、`src/.archived/app/anthropic/request_preparation.py:5,58`（唯一归档调用点，**没传这个参数**）、`tests/.archived/unit/anthropic/test_feature_negotiation.py:6,50`、以及 `src/app/pipeline/request_headers.py:96`（活代码里唯一一处，是 **docstring 里的一句引述**，不是调用）。 |
| R-3 | **`fix_anthropic_request` 存在但 direct path 走不到它**（「守卫留在 legacy 链路」那种形态） | 正查了调用链（§3.3）：唯一生产调用点 `driver.py:114` → `shape_request` → `handle` → `handle_bounded` → `inference.py:266`。链路完整。**否决**。真正的形态是函数体里没有这段逻辑。 |
| R-4 | **配置可能通过 `model_dump()` / `getattr` 之类间接被读到，grep 看不见** | 这是 grep 的已知盲区。用 §1.3 的真实执行探针排除：四种取值 + `extended_ttl` 打开，请求体逐字不变；并用正控制证明探针有分辨力。**否决**。 |
| R-5 | **`sanitize` 可能在 `attempt.prepare` 的某个订阅者里实现了，而不是在 `fix_anthropic_request` 里** | 逐个读完五个订阅者（§3.2）。`server_tools.py:124-129` 是唯一碰 `cache_control` 的，而它做的是**保留**，且不读配置。`blank_text.py:78-89` 会删整块但不改块内字段。**否决**。 |
| R-6 | **可能在 `model_provider` / SDK 层做了字段清洗** | 读了 `github_copilot.py:141-175` → `client.py:130-144` → `_post_anthropic:84-98`：只有 `dict(payload)` 一次浅拷贝，直接交 SDK。没有字段过滤。**否决**。 |
| R-7 | **`src/app/protocols/anthropic_responses.py` 那一大堆 `cache_control_not_supported` 是不是就是实现** | 读了 `:370-371,417-418,515-516,547-548`：那是 **Anthropic→Responses 翻译**时把丢掉的字段记成 `Conversion` 的一条 loss。它只在 `translation_required == true` 时跑，**direct path 根本不经过**（`driver.py:142`）。而且它记的是「丢了」，不是「改了」。**与本次无关，否决**。 |
| R-8 | **`docs/.human-controlled/message-translation.md` 里那两段 `cache_control` JSON 是不是一条裁决** | 读了 `:23,30,49,56`：那是在讲「anthropic-messages 的 system 长什么样、翻成 responses 之后长什么样」的**示例数据**，`cache_control` 只是示例里恰好带的字段。全文没有一句关于该字段处置的规定。**否决**。 |
| R-9 | **`.dev/docs/anthropic-direct-request-shape/` 可能已经登记了这件事** | 全部四份文档读完（README 26 行、spec 312 行、status 62 行、两份 disposition）。范围声明 `spec.md:5` 明确排除其余字段，§8 的 A-1～A-7 无一相关。**否决：这个 topic 没有 owning 它。** |
| R-10 | **8 份 deferred 台账里可能有登记** | 全部 grep 过，唯一 `cache` 命中是 `tui/deferred.md:19` 的 `cache_read_input_tokens`。**否决**。 |
| R-11 | **`exp/` 下可能有相关 PoC** | `exp/phase2-acceptance/ACCEPTANCE_REPORT.json:15` 的命中只是 pydantic 模型 dump 里的字段名。其余无。**未展开细查**，因为它不改变「主树零消费者」这个结论。**记为未穷尽面。** |
| R-12 | **本次 400 是不是因为 `anthropic-beta` 被我们剥掉了，导致上游不认识 `scope`** | 这是一个**合理且与结论方向相反**的解释，认真查了：`DIRECT_PATH_BLACKLIST` 为空（`request_headers.py:22`）、`REQUEST_FLOOR` 不含它、`build_request_headers` 不覆盖它、`strip_denied_beta_flags` 只按配置表剥而表里只有 `claude-sonnet-4.6`。所以 direct path 上它**是转发的**。**降级而非否决**：我没有那台机器的配置与实际出站头，所以 §3.3 记为强推断并给出了取证路径（读 `~/.local/share/ghc-api-proxy/rejected/` 的落盘）。 |
| R-13 | **`copilot-api-js` 的 `passthrough` 行为可否直接当作本项目应有的行为** | 事实照录（§6.1），但**不当判据**：CLAUDE.md 明令不得把它的默认值与缺陷当作本项目契约，且 `config.example.yaml` 是用户亲笔的更高权威。**否决把它当结论**，只作为「用户配置注释与前身行为存在差异」这一事实的证据。 |

**未穷尽的面（诚实记录）**：`exp/` 目录未逐个读；`.dev/docs/archived-2604-rewrite/`（用户 2026-08-20 已裁定整体过期）只按 grep 结果扫了相关行，未通读；`copilot-api-js` 的配置文件是否真有 `model_capabilities` 一节未查（影响 §2.3 的倾向级推断）；本次 400 的落盘出站记录未读（影响 F-8 的档位）。

---

## 8. 交回主会话的问题（不由我决定）

1. **`passthrough` 到底该不该剥 `scope`。** 用户亲笔文档说 `passthrough` = 原样转发、`sanitize` = 剥 `scope`；前身项目在两档下都剥。这是配置语义的裁决，属于用户。
2. **修法选主动式还是反应式。** `anthropic-direct-request-shape/spec.md:158-162` 为 `thinking` 一族确立了「主动式，不做 400 学习重试」的先例并给了理由；同样的论证可以套用，但这是设计决定。前身两条腿都做了。
3. **这件事归哪个 topic。** `anthropic-direct-request-shape` 的范围声明（`spec.md:5`）把它排除在外。要么扩范围，要么新立 topic，要么先进某个 deferred 台账——但**不能再只活在一份报告里**，那正是 §4.5 记录的、已经付过一次代价的形态。
4. **`extended_cache_ttl` 依赖的 `model_capabilities` 节从来不存在**（§2.3）——如果将来要实现 `extended_cache_ttl`，这个门控得先有个着落。
5. **顺手项**：`status.md:60` 的「§7 / A-1～A-5」与 `spec.md` 的「§8 / A-1～A-7」对不上（§4.3 末）。

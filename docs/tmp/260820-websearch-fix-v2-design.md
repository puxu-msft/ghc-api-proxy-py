# web search 修法 v2：外置改写载体 + 按上游能力分流

**日期**：2026-08-20
**取代**：`260820-websearch-400-synthesis.md` 的第 3、5 节（根因部分仍然有效）
**新输入**：用户 2026-08-20 给出两条方向——(1) 请求/响应改写功能应**外置**；(2) **Anthropic 上游不支持 web search，但 GPT 上游支持**。
**证据来源**：`260820-external-rewrite-surface.md`、`260820-js-rewriter-architecture.md`、`260820-websearch-on-responses-leg.md`，以及第一轮的三份。本文档只做合成与裁决建议。

---

## 0. 用户第 2 点触及的冻结裁决

`260806-arbitrate-server-tool-contract.md` 当初把「把 Anthropic server tool 映射为 Responses hosted builtin」列为**必须取得本项目单独用户裁决**的事项，并要求「若未来用户决定引入 Responses hosted web search，应以独立产品规格一次性冻结 declaration、forced choice、response presentation、stream lifecycle、History／continuation、错误与 capability gate，不得从 converter 映射表增量偷渡」。

用户的第 2 点就是那道裁决的开启。本文档据此展开，但**遵守「一次性冻结完整合同」的要求**：下文第 4 节把该合同的七个面逐一列出，并标注哪些已有证据、哪些必须先探针。

---

## 1. 「外置」不是新发明，是已裁决且基础设施已建成的事

### 1.1 用户亲笔（权威最高）

`docs/.human-controlled/MAIN.md`：

> 为了充分可扩展，每个请求都由一个 RequestContext 描述，驱动应该提供事件订阅点，允许功能模块订阅（传入唯一 id 和可选的"插入到谁之前/后"）。订阅者能够修改公共对象，也可以通过抛出不同的异常来触发中止/重试。
>
> 2026-08-16：这里"不同的异常"分两类，已知异常（如 `UpstreamError`、`UpstreamTimeout`、`UpstreamRateLimit`、`PipelineRetry`、`PipelineAbort`）会按内置逻辑处理；未知异常则总是中止。

`docs/.human-controlled/config.example.yaml:436-453` 已定名**六个订阅点**，其中包含出站方向的两个 SSE 块级点。

### 1.2 已裁决方向

`pipeline-subscriptions.md:5`：**「订阅机制吸收 hooks」**，且「要不要吸收」不再重开。同文 `:33` 记：有序插入与异常控制流**都已建成**，缺的是吸收本身。

### 1.3 已建成 vs 缺席（证据权重：强）

| 件 | 位置 | 状态 |
|---|---|---|
| 事件注册表 | `src/app/pipeline/events.py`（116 行：id + before/after 定序 + freeze + 异常转控制流） | **机制齐备，有单测** |
| `attempt.prepare` 事件 | `src/app/pipeline/direct_driver/base.py:29-41,114-133` | 订阅者改 `context.payload`，驱动 `:133` 重读后发出。**在重试循环内** |
| 注入参数 | `src/app/server/composition.py:184,221` | 参数在，但 5 个 `build_chain` 调用点**无一传值**，`src/` 下零 `.subscribe()` |
| 外置 hooks 框架 | `src/app/hooks/`（types/registry/loader/executor/builtin，5 个测试文件） | 4 类 typed 契约、`importlib` 加载用户模块、`builtin:*` 命名空间、超时、记账、deepcopy 隔离——**全部已实现**，但只接在 legacy `app_factory.py:111-127`，新链零引用 |
| 响应侧接入点 | 无 | 新链路上非流式只有翻译，流式链 `stream.py:133/196/205` 全程无订阅点 |

`docs/` 全库**零命中**任何「外置到进程外」的规划。

### 1.4 参考项目的对照（copilot-api-js HEAD `6209cb510`）

它的改写器注册表**不是外置的**，而且是**刻意拒绝运行期注册**（`rewrite-registry.ts:154-166`，理由写在注释里：装配确定性、避免可变全局单例）。它真正外置的是另一套 `src/lib/pipeline/hooks/`（配置 `hooks.upstream_module`、`Bun.Transpiler` 转译后动态 import、`POST /api/hooks/reload` 热重载），但那套**每个挂载点至多一个函数，无链、无 order、无 buffer/flush**——是「外置的观测/单点补丁」，不是「外置的改写器」。

**值得借鉴的四条**（详见 `260820-js-rewriter-architecture.md` §8）：

1. `order` 作为可检查契约，**并把顺序背后的理由写在 order 表旁边**（`rewrite-registry.ts:170-208` 逐条说明「为什么 100 必须早于 300」并指明锁定它的测试）——整套设计里最值钱的部分。
2. 响应侧 `FrameAction` 三态 `emit`/`suppress`/`buffer`，**缓冲由改写器自持状态，driver 不代管**——贴合本项目的块级交付。
3. `preserve`/`fresh` provenance 标记，直接决定溯源图长不长新节点。
4. **`appliesTo` 门控在出线腿（`targetEndpoint`）而非入站格式**——本项目主路径 Anthropic 入、Responses 出，两轴天然不同，这条直接适用，也正是本次修复的判据轴。

**该丢弃的**：开关散落在七种业务配置键里（判断「哪些改写器是活的」要读七处源码）；请求侧观测缺席（`RewriteResult.changed`/`stats` 定义了无人消费）；`apply` 非纯函数。js 的 retry strategy 有统一 `configKey` 配置面而改写器没有——**反向应用到改写器上，正是它没做而本项目该做的**。

### 1.5 结论

「外置」在本项目的落点已经确定：**订阅者注册表 + 具名内置订阅者 + 声明式配置开关**。不需要进程外机制，也没有任何文档规划过它。本次修复应当作为**第一个内置订阅者**落地，而不是再往 `fix_anthropic_request` 里加一个写死的函数调用。

旁证：`hook_strip_anthropic_request_headers` 是同族的「配置已定、实现缺席」缺口（`request_headers.py:17-33` 硬编码、零配置消费者），是天然的第二个订阅者。载体一旦建好，它顺手就能填。

---

## 2. 按上游能力分流：判据与事实

### 2.1 唯一可用的判据是 `supported_endpoints`（证据权重：强）

`refs/available_models.json` 40 个模型的 `capabilities.supports` 键并集里**没有任何 web search 能力位**。目录回答不了「谁支持 web search」。唯一判据是 `supported_endpoints` 是否含 `/responses`：8 个 GPT 模型含，**全部 Claude 模型不含**——这正是本次 400 的根因。

**这是必要非充分条件**：只探针过 gpt-5.5 与 gpt-5.6-sol 两个模型确实执行了搜索。

**陷阱**：`copilot-api-js` 的 `codex-assembly.ts:70` 有 `supportsWebSearch: supports?.web_search === true`，因目录无此键而**恒为 false**，是悬空代码，不能当 oracle。

### 2.2 GPT 腿确实原生执行（证据权重：强，一手、双模型、双日期）

`/responses` + `{type:"web_search"}` 在 gpt-5.5 上 HTTP 200 并原生执行搜索（`copilot-api-js/exp/anthropic-responses-direct/FINDINGS.md:41-47`）。上游 200 响应体回显了补默认后的工具形状：

```
{type:"web_search", return_token_budget:"default", search_content_types:["text"],
 search_context_size:"medium",
 user_location:{type:"approximate", city, country:"US", region, timezone}}
```

### 2.3 参考实现的请求侧映射有两个不该抄的地方

`from-ir/openai-responses/parameters.ts:58-65` 的 `SERVER_TOOL_MAPPING` 只有一行 `web_search_` → `{type:"web_search"}`，**光秃秃的 type、零子字段**。

1. **子字段静默蒸发**：`max_uses` / `allowed_domains` / `blocked_domains` / `user_location` / `cache_control` 无声丢弃（`dropWarn` 只在整工具无映射时才触发，`:97-101`）。**`allowed_domains` 被丢会放宽用户明确要求的限制**——这是行为改变，不是保守降级，不该照抄。`user_location` 的形状与 Anthropic 几乎逐字对应，**极可能 1:1 可写但未探针**；`max_uses` 与域名过滤在上游**无对应物**。
2. **过度剥离**：`isApiDefinedToolType` 认 10 个前缀，除 `web_search_` 外全剥+warn，包括 client-executed 的 `memory_` / `tool_search_` / `text_editor_`——**Claude Code 实际会发这些**，它们本可降级成普通 function tool 透传。

### 2.4 `tool_choice` 与 `include`

- `tool_choice` 映射（`:125-156`）：`auto→auto`、`any→required`（tools 非空才发）、`none→none`、`{tool,name}` → `{type:"web_search"}` 并回检可用性，声明被剥则整条省略。**但 builtin 对象形态的 tool_choice 从未探针**，所有实测都是 `"auto"`。
- **`include` 在参考实现全仓从无写入点** → `web_search_call.action.sources` 从没被请求过，行为完全未知。
- `tool_usage` 不是请求字段，是上游**响应**字段（`web_search.num_requests`），一手双来源存在、双方都没用——白捡的可观测信号。

---

## 3. 响应侧：这是真正的新产品能力，不是本次 400 的一部分

### 3.1 参考实现永远降级，不还原（证据权重：代码强，真实流量零）

`webSearchCallToText`（`from-ir/anthropic/server-tool.ts:24-27`）产出一行文本 `[web_search: "<query>"] (id: <424字符>, status: completed)`。判据是 **item 的来源协议**（`:36`）而非 item 种类：Anthropic 来源的 `server_tool_use` 原生还原，Responses 来源的 `web_search_call` 降级。

理由：Anthropic 的 `web_search_tool_result` 要求非空 `encrypted_content`，而 `web_search_call` **确无该字段**（两次独立一手实测）。合成即撞 400。

**两个判断要点**：

1. 它把 424 字符的不透明 id 塞进面向客户端的正文，**不该抄**。
2. **它的 no-revive 前提是「合成块会回喂 Anthropic 上游」，而本项目下一轮同样发往 Responses，这个约束在本项目不自动成立。** 渲染形态是本项目自己的裁决点。

### 3.2 流式：whole-item，有记录在案的真实回归

上游对 `web_search_call` 只发 `output_item.added` + `output_item.done` 两次完整快照，**中间零 delta**（一手 `stream-id.json`）。

`to-ir/openai-responses/response-wire.ts:447-452` 记录了一个真实回归：早先版本在 `done` 时若该 index 没开过就 return，结果**整个搜索 item 静默消失且无 observation**。**按常规「added 开块 → delta → done 收口」写解码器会重复这个 bug。**

id 在 added/done 之间稳定（`distinctIds:1`）。这与本项目 CLAUDE.md 记录的 function_call id 不稳定**不矛盾**——那条是在 `function_call` 上测的，**不得据此放宽 function_call 侧纪律**。本条也只是两事件、单次、单模型。

### 3.3 历史回放：链路靠降级文本闭合，没有 call id 回到上游

- 方向 (a)（Anthropic 历史 → Responses 请求）：**直接丢弃**，只记 observation（`request-write.ts:250-258`）。链路实际靠「降级文本被客户端当普通文本回传」闭合。
- 方向 (b)（Responses 续接载体）：契约已定义、上游已实测、**代码零生产使用点**。实测五形态：完整 item 200 / `{type,id}` 200 / `item_reference` **404** / id 翻一个字符 **400** / 省略 200。机制是上游**解密该 id**。**必须逐字保留的只有 `id`，没有 encrypted content 要保。**
- **最关键**：A/B/E 三者答案完全相同（都 `NO_CONTEXT`）——**回传 `web_search_call` 并没有把搜索结果带回上下文**，结果一直在 message 文本里。它的续接价值是 provenance 与顺序，不是可恢复数据。且伪造短 id 也 200，「被接受」无判别力。

### 3.4 本项目一份真实样本都没有

cassette 里 `web_search_call` 零次（只有信封里 `num_requests:0`）；生产 history 全扫 **1,694,395 个 gzip 对象、零命中**。唯一真实样本是 `copilot-api-js/exp/` 下那两份 JSON。

**要 cassette 只能自己录**——`from_history.py` 派生这条路在这里是死的。

---

## 4. 若要开启完整能力，冻结裁决要求一次性覆盖的七个面

| 面 | 现有证据 | 缺口 |
|---|---|---|
| declaration 映射 | 强（一手 200） | 子字段可写性未探针（`user_location` 极可能可写，`max_uses`/域名过滤无对应物） |
| forced choice | 仅代码 | builtin 对象形态的 `tool_choice` 从未探针 |
| response presentation | 参考实现永远降级；其前提在本项目不成立 | **本项目的渲染形态未裁决**；零真实样本 |
| stream lifecycle | 强（whole-item，一手） | 解码器必须按 whole-item 写，有记录在案的回归 |
| History / continuation | 强（五形态实测） | 只保 `id`；但回传不恢复上下文，价值仅 provenance |
| 错误处理 | 两条拒绝措辞已知（`unsupported_value` / `invalid_request_body`） | `web_fetch`、`code_execution` 在 `/responses` 腿**均未探针**，参考实现映射表有意留空（注明 "omitted until probed, rather than guessed"） |
| capability gate | 强（`supported_endpoints`） | 必要非充分，只探过 2 个 GPT 模型 |

---

## 5. 建议的实施形态

### 5.1 载体（无分歧，顺已裁决方向）

把改写做成 **`attempt.prepare` 的具名订阅者**：

- `build_chain` 把 `SubscriberRegistry` 传下去（`composition.py:184,221` 参数已在，5 个调用点补传）；
- 注册内置订阅者，命名与寻址沿用 js 的 `${stage}:${name}` 规则；
- 配置面用声明式 id 列表——正好回答 `config-migration-gaps.md:45-49` 悬置的「列表项指什么」；
- `order` 表旁边写清楚顺序理由并指明锁定它的测试（借鉴点 1）。

选 `attempt.prepare` 的理由：它**同时覆盖直通腿与 Responses 腿**，且**在重试循环内**——这是本次问题唯一同时具备两个性质的接入点。

### 5.2 订阅者按出线腿分流（借鉴点 4）

- **Anthropic Messages 腿**：剥掉 server-tool 声明 + 清理悬空 `tool_choice`，剥离在请求日志可见。**不要顺手剥 `memory_`/`tool_search_`/`text_editor_`**——那些是 client-executed，应降级为普通 function tool 透传。
- **Responses 腿**：映射 `web_search_*` → `{type:"web_search"}`，但**不静默丢 `allowed_domains`/`blocked_domains`**。子字段可写性未探针之前，保守做法是：带了域名限制就**不映射、改为剥离并告警**，而不是"部分映射"悄悄放宽用户的限制。

### 5.3 响应侧另起一轮

第 3、4 节的内容是独立产品规格，需要先录 cassette（本项目零样本）、先探针（子字段、forced choice、`include`、`web_fetch`）。**不要塞进本次修复。**

---

## 6. 用户裁决（2026-08-20，已定案）

1. **分流语义**：能力**跟随已路由的模型**。Claude → 剥离；GPT → 映射。
2. **不引入按请求内容路由**。Claude Code 的 WebSearch 是主请求声明还是独立子请求尚不确定，按主请求保守处理；若日后证实是子请求，再考虑把这类子请求路由到 GPT 模型。
3. **切片顺序**：载体与首个订阅者一起做。

## 7. 已落地（本次切片）

| 件 | 位置 |
|---|---|
| 内置订阅者注册表 | `src/app/pipeline/subscribers/__init__.py`（含 order 表与其理由，指明锁定它的测试） |
| 首个订阅者 | `src/app/pipeline/subscribers/server_tools.py`，id `builtin:server-tool-capability`，事件 `attempt.prepare` |
| 接线 | `src/app/server/composition.py` 的 `build_chain`，**零调用点改动** |
| 测试 | `tests/unit/test_subscribers_server_tools.py`（10 条行为）、`tests/unit/test_builtin_subscribers.py`（4 条，含驱动级证明订阅者真在请求路径上跑） |

行为：`target_format` 为 Anthropic Messages 时，剥掉 `tools[]` 中 `type` 以 `web_search_` 或 `web_fetch_` 开头的声明；剥空则删 `tools` 键而非置 `[]`；清理因此悬空的 `tool_choice`；`logger.warning` 记录剥了什么。

### 落地时做的三个判断（与设计稿的偏差）

1. **不新造配置项。** `pipeline-subscriptions.md` 把「`hooks:` 六个点的列表项指什么」列为待裁决第 3 项；协议兼容性修复按 `hooks-tokenization-spec.md` 属于不可禁用的 mandatory sanitizer，与 `normalize_context_management` 一样本就无开关。所以这一片不预支未定的配置语义。**配置面在那道裁决落地后再补。**
2. **只剥两个前缀。** `web_search_`（今天这条 400）与 `web_fetch_`（上游用另一套 body 拒绝：`rejected tool(s): web_fetch` / `invalid_request_body`）。`memory_`、`tool_search_`、`text_editor_`、`bash_`、`computer_` **刻意不剥**——它们由客户端执行，Claude Code 确实会发，没有任何证据表明上游拒绝它们，剥掉是为了防一个没人见过的失败而弄坏正在工作的请求。参考实现把十个前缀全剥，那是错的。
3. **判据读我们发出的声明，不读上游的措辞。** 同一条规则上游有两套 body，按单一错误文本写 matcher 会漏掉另一套。这也是预防式相对反应式的一个附带优势。

### 验证

- 变异验证：把 `_REJECTED_TYPE_PREFIXES` 置空 → 6 条测试变红（含驱动级那条），确认绿灯有分辨力；随后精确还原并复跑 14 条全绿。
- 完整默认回归 `uv run pytest -q`：**1321 passed, 2 skipped**。
- `ruff check` 与 `pyright` 对改动文件均零问题。**未运行 `ruff format`**（项目禁止）。

### 顺带发现的既有问题（未处置）

`uv run pytest tests/unit tests/http` 这种窄化调用会有 2 个 `tests/http/test_pipeline_app.py` 的红（`test_upstream_429_is_seen_by_the_rate_limiter`、`test_upstream_503_does_not_enter_limited_mode`），断言形如 `assert <RateLimitMode.NORMAL> is <RateLimitMode.NORMAL>`——同值不同身份，模块被重新加载。污染源是 `tests/unit/test_module_boundaries.py`。

**归因证据**：把本次改动 stash 掉、把本次新增的两个测试文件也排除掉，仍然复现；两个失败的测试在 HEAD 中原样存在、并行会话也未修改。完整默认扫（`uv run pytest -q`）因为顺序不同**不复现**。所以这是既有的顺序依赖假红，与本次改动无关，也不影响默认扫。

## 8. 评审与验收处置

评审：[`260820-review-server-tool-subscriber.md`](260820-review-server-tool-subscriber.md)（blocker 0、major 2、minor 8）。独立验收：[`260820-verify-server-tool-subscriber.md`](260820-verify-server-tool-subscriber.md)（**PASS**）。

| 发现 | 处置 |
|---|---|
| M1 冻结 spec `hooks-tokenization-spec.md:126` 逐字禁止 server-tool 过滤，本次落地相反却无裁决记录 | **采纳**。已在该 spec 原文后增补 2026-08-20 裁决段，写明只推翻「请求 `tools[]` 声明」这一半，历史 blocks 的 breaking-removal 立场不变 |
| M2 锁定测试只断言 `attempt.prepare` 一个桶，docstring 却声称锁定整个集合——下一个订阅者挂到别的事件上不会触发 | **采纳**。改为按事件全集断言（`frozen_by_event`），并把理由写在期望值旁边 |
| m1 被剥声明缺 `name` 时悬空 `tool_choice` 留存 | **采纳**。`_drop_dangling_choice` 改为**对存活工具**判定而非对被剥的名字判定；补测试 |
| m2 前缀带尾随下划线，漏掉 OpenAI 裸拼法 `{"type":"web_search"}` | **采纳**。前缀改为 `("web_search", "web_fetch")`；补测试。触发路径：`/responses` 入站 + Claude 模型回退到 Anthropic 腿，translator 逐字透传 |
| m3 逐请求 `logger.warning`，与仓内「WARNING 留给非例行」约定冲突 | **采纳但不照搬**。姊妹 sanitizer 用 debug，但那修的是无语义的空文本块；剥离删掉的是客户端要的能力。改为 **info**——例行所以不是 warning，但运维不该非开 debug 才看得见。理由写进代码注释 |
| m4 同一 registry 两次 `build_chain` 会抛 `SubscriptionError` | **不改行为**，补 docstring 说明这是设计意图而非疏漏：registry 属于一条 chain，跨两次 `build_chain` 复用意味着第二条 chain 的订阅者本该是别人的，启动期报错正是要说出这件事 |
| m5 `count_tokens` 腿不经驱动，订阅者不生效（验收实测：出站 `tools` 仍带声明） | **本切片不修**，记为缺口。修它要改 `src/app/server/handler.py`，而该文件正被并行会话编辑（本次调查期间 30 秒内变动过）。影响：`/v1/messages/count_tokens` 带 server tool 时行为未测量；若上游拒绝会退到本地估算，客户端无可见失败但校准停止学习 |
| m6 docstring 把判据说窄了：翻译**进入** Anthropic 的路线上载荷仍是 Anthropic 形状、订阅者应当跑 | **采纳**，改写 docstring 与测试注释 |
| m7 测试名说 order 而断言用 `set` | **采纳**，改名并把断言改为有序 |
| m8 历史残留 `server_tool_use` 的会话修复后从一个 400 变成另一个 400 | **采纳**，本文档 §9 记录，并收窄「立刻恢复可用」的措辞 |
| 验收：docstring 用「`/responses` 原生执行 web search」论证翻译腿安全，但上游只被问过 Responses 拼法，Anthropic 拼法**未测量** | **采纳**。docstring 改为「因为没有测量到拒绝而放过，不是因为已知可用」 |
| 验收：既有假红的机制措辞 | **采纳**。不是 reload，是 `reachable_from` 把 `sys.modules` 中所有 `app*` 条目删除后重新 import；那两个用例的 `RateLimitMode` import 写在函数体内，所以只有它们红。验收用 `git archive HEAD` 导出纯净树独立复现，归因成立 |

**验收的关键限定**（作者认可）：全程假上游，只证明「这条声明不会被发出去」，**不证明上游会 200**；也未验证前缀名单是否完整。

## 9. 待用户裁决（剩余）

1. **响应侧渲染形态**：参考实现的「一行降级文本」前提在本项目不成立（第 3.1 节）。本项目要不要还原成 `server_tool_use` + `web_search_tool_result`？这决定要不要探针 `encrypted_content` 的替代。
2. **历史残留块**：`hooks-tokenization-spec.md` 把「历史里残留的 server-tool 块被上游拒绝」定为**有意的 breaking removal**，本次裁决未改这一半。本次只剥 `tools[]` 声明，所以**已经产生过 server-tool 块的旧会话**修复后撞到的是另一句 `Tool 'X' not found in provided tools`——「立刻恢复可用」只对新会话与从未用过 web search 的会话成立。要不要改这个立场？
3. **`count_tokens` 腿**：要不要让它也过订阅者（须改 `handler.py`，等并行会话的改动落定）。
4. **订阅者的配置面**：等 `pipeline-subscriptions.md` 第 3 项（`hooks:` 列表项语义）落地。
5. **翻译到 `/responses` 的腿**：Anthropic 拼法的 server tool 声明在该端点是否被接受，未测量。要不要探针。


---

## 7. 顺带发现，本次不处理

- `src/app/hooks/` 整套外置框架已实现但只接 legacy app；若采纳订阅者路线，它按 `pipeline-subscriptions.md:5` 应被**吸收**而非并存。
- `hook_strip_anthropic_request_headers`：配置已定、实现缺席，天然的第二个订阅者。
- `feature_negotiation.py` 缺 `serverTools`/`serverToolDowngrade` 是 `hooks-tokenization-spec.md` §8 **刻意删除**，不是遗漏。
- 参考实现 `hooks/loader.ts:38` 的 `HOOK_POINTS` 漏了 `client.inboundComposed`（`types.ts:60` 已声明、`driver.ts:497` 已读取），磁盘加载的 hook 导出该叶子会被静默丢弃——是参考项目的真缺陷，本项目实现同类 loader 时别复制。

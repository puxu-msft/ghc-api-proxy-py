# Anthropic `cache_control` → OpenAI Responses 调查

- 范围：只读解析 `copilot-api-js` 的活跃 history 与 codec 源码；唯一写入本文件。未接触 `127.0.0.1:4141` 或 pid 926144。
- 已知前提：GHC `/responses` 的 `instructions` 仅接受字符串；system blocks 当前以 `\n\n` 拼接，故该路径不保留 block-level `cache_control`。
- 证据状态：已完成 history、当前源码、OpenAI 官方文档与三次直连 GHC 的取证。

## 1．活跃 history：确有 Anthropic 入站 → Responses 出站

- 全程以 `sqlite3.connect('file:...db?immutable=1', uri=True)` 打开；未连接或请求 pid 926144。
- 代表操作 `req_1787075757398_727`：summary 为 `rawPath=/v1/messages`、`requestModel=gpt`、`responseModel=gpt-5.6-terra`、`responseSuccess=true`；命令输出见本调查的 immutable-SQLite 查询。
- `payload:0` 是 Anthropic body（含 `system/messages/tools/context_management`）；其 `system[0]`、`system[1]` 的 history overlays 都是 `{type:"ephemeral"}`。
- `payload:1`、`payload:2` 是同一份 Responses-shaped body：`model=gpt-5.6-terra`、`input`、`instructions`、`max_output_tokens`、`reasoning`、`tools`、`user`、`stream`；无 `cache_control`、`cacheControl`、`prompt_cache_key`、`prompt_cache_breakpoint` 或 cache options。
- 该 body 的 `instructions` 是字符串：两段 source `system[].text` 的精确 `"\n\n"` join（62 + 5602 chars → 5666 chars）；不是 block array，故两个入站 breakpoint 未映射到它。
- `input` 是 Responses item array：Anthropic user/system text 变为 `{type:"message",role,content:[{type:"input_text",text}]}`，并夹有 `reasoning`、`function_call`、`function_call_output`；全体输入 items 也未出现 cache 字段。
- Track 进一步定性：`effective-request#0 → payload:1` 与 `upstream-request#0 → payload:2` 都标为 `format=openai-responses`；后者 query 为 `?beta=true`，上游 SSE 是 `response.created` 等 Responses events。history 不保存原始字节，保存的是语义 payload/frames，故“相同”限于该语义记录。

## 2．当前 `copilot-api-js` 的实现结论

- 它**做** Anthropic→Responses 翻译：`src/lib/codec/openai-responses/openai-responses-cell.ts:12-21,109-124` 对 Anthropic `@responses` 调用 `translateRequestVia(..., ENDPOINT.RESPONSES, ...)`，产物是 Responses-shaped body。
- 该 body 走 direct wire：`openai-responses-cell.ts:70-72,135-151` 与 `openai-responses-leg.ts:109-118` 调 `prepareResponsesRequest`，发送 `ENDPOINT.RESPONSES`；不是 Anthropic native leg。
- Anthropic native leg 才会处理 cache：`src/lib/anthropic/request-preparation.ts:992-1045` 的 mode 可 strip、sanitize 或注入 `cache_control`；`...:1250-1266` 在最后可承载 block 直接写 `{type:"ephemeral"}`。
- Responses leg 的实际 last-mile 仅改 function-call id、`user` 和 headers（`src/lib/openai/request-preparation.ts:105-124`）；在 `src/lib/codec/openai-responses/`、`src/lib/openai/`、`src/types/api/openai-responses.ts` 搜索 `cache_control|cacheControl|prompt_cache_key|promptCacheKey|ephemeral` 未找到 Responses cache 映射。
- 在 `src`、`packages`、`tests` 的 TypeScript 与对应 Git history 搜索 `prompt_cache_key|promptCacheKey|prompt_cache_breakpoint|promptCacheBreakpoint` 均为零命中；当前可执行源码没有填写或传递 `prompt_cache_key` 的实现。

## 3．Responses 的 cache 字段不是 Anthropic breakpoint 的同义物

- 官方 Prompt Caching 指南：`prompt_cache_key` 是顶层 optional routing/affinity hint；复用它的相同 prefix 才更可能落到同一缓存机。GPT-5.6+ 中它也参与更可靠的 exact-prefix 匹配，但不写 cache entry、不规定 block 边界或 TTL。
- 显式 cache 边界是另一机制：content block 上的 `prompt_cache_breakpoint:{mode:"explicit"}`；TTL 由 `prompt_cache_options.ttl`（新模型）或 `prompt_cache_retention`（旧模型）控制。来源：https://developers.openai.com/api/docs/guides/prompt-caching
- 因而单把 Anthropic `{type:"ephemeral",ttl?}` 改成 `prompt_cache_key` 不保真：它丢掉 breakpoint 位置和 TTL，且 key 本身不能令不同 prefix 命中。
- 旧 history `history-v3-260807.db` 的 request-shaped object 确有 top-level `prompt_cache_key`（36-char string，值未披露）；同库的 response-shaped object 有 `prompt_cache_retention`。这证明历史上游支持这些字段，**不**证明当前源码填了它们，也不证明二者来自同一请求。

## 4．直连 GHC：`input` 可走 OpenAI 的显式 breakpoint，不能原样带 Anthropic 字段

- Probe A：`input[0].content[0].cache_control={type:"ephemeral"}`（`input_text`）经 `GhcApiClient.send_responses` 返回 **400**：`Unknown parameter: 'input[0].content[0].cache_control'.`；原字段不能保留。
- Probe B：同一位置改为 `prompt_cache_breakpoint:{mode:"explicit"}` 返回 **200**（`gpt-5.6-terra`、`status=completed`）。
- Probe C：把 marker 放在 `input` 的 `role:"system"` message 的 `input_text` 上，并另附普通 user message，也返回 **200**。三次都直发 `https://api.githubcopilot.com/responses`，未触及 `127.0.0.1:4141`。
- 200 只证明 GHC 接受该 wire shape；未作两次相同前缀的 cache-read/write 对照，故不把它写成“已观察到缓存命中”。

## 5．回答与可行保真策略

- `copilot-api-js` 当前确实把 Anthropic 客户端请求送到 Responses，但历史样本证明它把入站 `cache_control` 丢在翻译边界：`payload:0` 有 breakpoint，最终 `upstream-request#0/payload:2` 无任何缓存字段。
- `instructions` 无法承载 block marker；`input` 中的 system message 可以承载 Responses 的 `prompt_cache_breakpoint`，且该 GHC model 实测接受。因此要保留“此处建立 cache prefix”的语义，系统块应走 `input` block，并将 Anthropic marker**翻译**为 OpenAI marker，而非拼进 `instructions`。
- `prompt_cache_key` 可作为同一稳定 prefix 的顶层 affinity/matching key；它应是额外优化，不是 `cache_control` 的替身。当前 `copilot-api-js` 无生成它的代码，若本项目要填，必须明确选择稳定、可复现的 key 来源。
- 不能声称完全 wire/TTL 保真：Anthropic `ephemeral`（及可选 `ttl:"1h"`）和 Responses 的 marker/retention 是不同契约；需按官方 Responses TTL 语义单独映射或记录降级。`context_management` 也仍是已知 400，不能借它承载缓存。

## 6．结构检查

- 无新增生产实现。本轮结构扫描范围是报告涉及的 Anthropic prep、Responses leg、Responses prep/type 与 history；发现的职责差异是 native Anthropic cache handling 与 Responses translation 分离（`request-preparation.ts:992-1045` 对 `openai/request-preparation.ts:105-124`），本轮仅记录，因为任务授权为调查而非改代码。
- 自我批判：替代方案是只用 `prompt_cache_key`，但官方语义与实测 marker 接受性均表明它不足；判据已覆盖“原字段是否可 parse”和“OpenAI marker 是否可 parse”，尚未覆盖真实 cache hit；成熟第三方方案不适用——这是上游协议映射，不是本地缓存机制。

### 证据命令

- history：`uv run python` 以 `file:...history-v3-20260818-044224.db?immutable=1` 解 zstd manifest/object，并读取 `v3_tracks`；源码：`codegraph explore ...`、`rg -n ...`；官方文档：上列 URL。
- 所有数字均限于各条命令输出或指定的代表 operation；未以计数推断全量行为。

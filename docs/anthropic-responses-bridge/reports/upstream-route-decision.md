# Anthropic Messages 入站选择 OpenAI Responses upstream 调查

## 评审范围与结论

- **评审范围**：只读调查 `/home/xp/src/copilot-api-js` 的 `master@74853175c2c5771e6110bdbdfb97870132788fa1`，限定于 Anthropic Messages 入站如何选择 OpenAI Responses upstream；证据来自该提交的生产路由、模型解析、S2 router、CellAssembly、Anthropic↔Responses 直接桥、物理 transport 与相关测试。调查期间仓库曾被并发会话切换 `HEAD`，最终重新冻结当前 `master`，并确认本报告引用的关键路径相对最终 `HEAD` 无工作树改动。
- **既有裁决边界**：用户已裁决“block-level buffering 是基础能力，下游不提供 live streaming 体验”。本报告不重开、不反驳该裁决；upstream protocol leg 的选择与 downstream buffering／交付粒度是正交问题。
- **总体 verdict**：**修复 major 后可进入下一阶段**。生产代码的 Responses upstream 选择链完整且有矩阵／forward-leg 测试，但 `docs/DESIGN.md` 仍有一句与当前无后缀自动翻译行为相反的活文档陈述。
- **blocker 数**：0。
- **发现计数**：6 条事实性发现，其中 1 条 major、5 条信息性事实；无主观建议。

## 双视角覆盖证据

### 机械核对视角

- 核对路由挂载、Messages handler、模型后缀解析、模型目录能力谓词、S2 单一决策点、CellAssembly、Anthropic→Responses 直接请求桥、Responses wire 准备与物理 transport。
- 对账无后缀矩阵与显式 `@responses` 测试；确认 Google force-fallback、`supported_endpoints` 缺失／index miss 的 legacy-true 语义，以及 `ws:/responses` 只作为 Responses 能力标记。
- 以最终 `HEAD` 重新验证关键路径无工作树差异；所有 `file:line` 均按最终文件复核。

### 第一人称执行视角

- 模拟 `POST /v1/messages` 与 `/anthropic/v1/messages`，分别发送：Anthropic `/v1/messages` 模型、Responses-only 模型、CC+Responses 模型、CC-only 模型、Google Responses 模型、未知／旧模型，以及显式 `@responses`／`@cc`／`@messages` 后缀。
- 沿实际执行顺序走通：route → `handleMessagesV4` → `resolveModelTarget`／`state.modelIndex` → `driver.runRequest` → `decideRoute` → `resolveCellAssembly` → Anthropic→Responses 直接桥 → `prepareResponsesDirectWire` → Anthropic handler 注入的 HTTP transport → Responses→Anthropic 响应翻译。
- 单独模拟“协议 leg 是 `/responses`”与“物理 transport 是否为 upstream WebSocket”，确认二者不能混为同一选择。

## 事实性发现

### 1. [信息] Anthropic Messages 的两个客户端入口汇入同一 v4 handler

- **入口**：`/home/xp/src/copilot-api-js/src/routes/index.ts:55-58` 同时把 `messagesRoutes` 挂到 `/v1/messages` 与 `/anthropic/v1/messages`；`/home/xp/src/copilot-api-js/src/routes/messages/route.ts:8-14` 的 `POST /` 调 `handleMessagesV4`。
- **调用链起点**：`POST /v1/messages` 或 `POST /anthropic/v1/messages` → `messagesRoutes.post("/")` → `handleMessagesV4`。
- **边界**：`/count_tokens` 是独立旁路，不参与本报告的 completion upstream route decision。

### 2. [信息] Responses upstream 的唯一协议路由裁决发生在 driver S2；无后缀 Anthropic 优先级为 `messages > responses > cc`

- **调用点**：`/home/xp/src/copilot-api-js/src/routes/messages/handler-v4.ts:372-420` 解析 payload、用 `resolveModelTarget` 得到规范模型名与可选 route override，并从 `state.modelIndex` 取得模型；`/home/xp/src/copilot-api-js/src/routes/messages/handler-v4.ts:451-490` 构建 codec／transport／driver，并把 `preResolved` 交给 `driver.runRequest`。
- **单一决策点**：`/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts:320-366` 在 S2 调 `decideRoute`，把 `passthrough.endpoint` 或 `translate.to` 写成 `targetEndpoint`，随后按该 endpoint 执行 `translateOut`。
- **默认决策**：`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:67-91` 按 `clientFormat` 分派；`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:201-247` 对无后缀 Anthropic 先试 direct `/v1/messages`，失败后先试 Responses，再试 Chat Completions，最后才 400。
- **结论**：Responses upstream 不是 handler 中的硬编码，也不是 buffering 开关决定；它由规范模型、模型目录能力与可选 route override 在 S2 决定。

### 3. [信息] 选择 `/responses` 的模型／配置条件与例外是明确的

- **direct Messages 条件**：`/home/xp/src/copilot-api-js/src/lib/anthropic/features.ts:29-48` 要求 `state.modelIndex[modelId].vendor === "Anthropic"`，且模型支持 `/v1/messages`；仅在该条件成立时无后缀 Anthropic 请求直连 Messages。
- **Responses 能力条件**：`/home/xp/src/copilot-api-js/src/lib/models/endpoint.ts:45-59` 把 `/responses` 或 `ws:/responses` 任一广告视为 Responses-capable。`supported_endpoints` 缺失或模型 index miss 时，`isEndpointSupported` 返回 true，因此无后缀 Anthropic 会按优先级选择 `/responses`；现有矩阵测试将 legacy／unknown 固定为该行为，见 `/home/xp/src/copilot-api-js/tests/pipeline/route-matrix.it.test.ts:149-188`、`:191-222`。
- **多能力优先级**：同时支持 CC 与 Responses 的非直连模型仍选 Responses，见 `/home/xp/src/copilot-api-js/tests/pipeline/route-matrix.it.test.ts:132-145`。
- **Google 例外**：`/home/xp/src/copilot-api-js/src/routes/responses/fallback.ts:17-27` 只列 `Google` 为 force-CC vendor；`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:237-241` 因而把本来选中的 `/responses` 改成 `/chat/completions`。显式 `@responses` 也不能越过该例外，见 `/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:111-151` 与 `/home/xp/src/copilot-api-js/tests/pipeline/route-explicit-leg.it.test.ts:122-134`。
- **显式后缀**：`/home/xp/src/copilot-api-js/src/lib/models/resolver.ts:185-209` 从客户端模型名或 `model_mappings` target 解析 `@cc`／`@responses`／`@messages`；客户端显式后缀优先于映射 target 后缀。`@responses` 正常要求 Responses-capable，否则 400；`@messages` 仍要求真实 Anthropic vendor gate，不能仅靠 endpoint 列表，见 `/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:153-189`、`/home/xp/src/copilot-api-js/tests/pipeline/route-explicit-leg.it.test.ts:137-177`。

### 4. [信息] 选中 `/responses` 后走 Anthropic↔Responses 直接桥，不经过 Chat Completions 中转

- **CellAssembly**：`/home/xp/src/copilot-api-js/src/lib/pipeline/cell-assembly.ts:187-193` 将 `/responses` 映射到 `responsesLeg`；`/home/xp/src/copilot-api-js/src/lib/pipeline/cell-assembly.ts:218-237` 由 `(clientFormat, targetEndpoint)` 组合出实际 outbound cell。
- **请求转换**：`/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/openai-responses-cell.ts:77-109` 对 `clientFormat === "anthropic"` 调共享 `translateRequestVia(..., ENDPOINT.RESPONSES, ...)`；`/home/xp/src/copilot-api-js/src/lib/pipeline/hub-translate.ts:139-157` 选择独立 `anthropicToResponsesBridge`，`/home/xp/src/copilot-api-js/src/lib/pipeline/hub-translate.ts:178-205` 的穷尽表把 `(anthropic, /responses)` 直接绑定到该桥。
- **wire 形状**：`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:113-164` 把 Anthropic `system/messages/max_tokens/tools/tool_choice` 等转换为 Responses `instructions/input/max_output_tokens/tools/tool_choice`；`/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/openai-responses-cell.ts:111-119` 因 body 已是 Responses-shaped 而调用 `prepareResponsesDirectWire`；`/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/openai-responses-leg.ts:107-120` 最终产出 `url: "/responses"`。
- **实测型测试**：`/home/xp/src/copilot-api-js/tests/anthropic/forward-leg-strategies.it.test.ts:127-136` 断言 `@responses` 的实际 sent wire 是 `/responses`、有 `input[]` 且无 `messages[]`。
- **响应回程**：`/home/xp/src/copilot-api-js/src/lib/codec/anthropic/codec.ts:282-326` 对 Responses upstream 的流式／非流式结果再翻回 Anthropic 客户端格式，并用 Responses accumulator 记录真实上游腿。

### 5. [信息] Anthropic→Responses 选择的是 Responses HTTP API 协议 leg，但不会启用 Responses handler 专用的 upstream WebSocket 二次选择

- **Anthropic handler 注入 transport**：`/home/xp/src/copilot-api-js/src/routes/messages/handler-v4.ts:451-456` 无条件构建 `createUpstreamHttpTransport`。该 transport 在 `/home/xp/src/copilot-api-js/src/lib/transport/http-transport.ts:64-104` 直接按 `wire.url` 调 `sendUpstreamHttp`，所以 Anthropic→Responses 会 HTTP 请求 `/responses`。
- **专用 WS 选择只在 Responses handler transport**：`/home/xp/src/copilot-api-js/src/lib/transport/responses-transport.ts:65-100` 才会在 streaming、未 force HTTP 且 `canUseUpstreamWebSocket` 时尝试 WS；`/home/xp/src/copilot-api-js/src/lib/openai/upstream-ws-attempt.ts:59-64` 还要求 `openai_responses.upstream_ws` 生效、manager 可用、breaker 未禁用、模型明确广告 `ws:/responses`。
- **关键区分**：模型只广告 `ws:/responses` 仍会让 router 把 Anthropic 入站的协议 endpoint 定为 `/responses`，但物理发送仍是 HTTP `/responses`。`openai_responses.upstream_ws` 不参与 Anthropic Messages 入站的 upstream protocol route decision，也不会把该路径升级为 WS。

### 6. [major] 活文档仍称“非 Anthropic vendor 在 S2 拒绝 400”，与当前自动选择 Responses／CC 的生产行为冲突

- **失真位置**：`/home/xp/src/copilot-api-js/docs/DESIGN.md:65` 写“非 Anthropic vendor 模型在 S2 拒绝 400（无降级）”。
- **反证**：`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:201-247` 已明确对非 direct-Anthropic 模型自动选择 `/responses`，其次 `/chat/completions`；`/home/xp/src/copilot-api-js/tests/pipeline/route-matrix.it.test.ts:111-188` 固定了 OpenAI／Google／legacy／unknown 的翻译行为。
- **失败场景**：下游若只读该段活文档，会误判 Claude Code 用 GPT／Responses 模型必定 400，进而绕开已经上线的 direct bridge 或重复实现路由。
- **修复建议**：把该句改为“direct `/v1/messages` 仅限 Anthropic vendor + Messages-capable；否则按 `responses > cc` 自动选择可翻译 leg，Google Responses 强制转 CC，无可达 leg 才 400”，并链接 `pipeline/router.ts` 的决策矩阵。此文档修复不得借机恢复 live downstream streaming 叙述，亦不得推翻既有 block-level buffering 裁决。

## 最近相关提交

以下提交均可由最终 `HEAD` 祖先链到达；日期按提交记录口径：

- `192dce69f1bf482b1c3130d519991594a3fe46ab`（2026-08-06，`fix: summarize cross-model thinking drops`）：补强 Anthropic→Responses 跨模型 thinking 降级汇总，影响 direct bridge 的可观测性。
- `b8372966ad1ca750be9b5c3fa4638e9a5de48360`（2026-08-05，`fix(responses): preserve forced custom tool choices`）与 `c4004e48944886326039b259b527b79dc9c741dc`（2026-08-05，`fix(responses): align tool choice with translated tools`）：修正 Anthropic→Responses 工具选择翻译。
- `69b82024aeb4155d978227d725b3583b299020f4`（2026-07-15，`feat(bridge): direct anthropic→responses request bridge (Phase 3 subtask A)`）：引入前向直接请求桥。
- `9f0203a9d572d263dd6e688dba4952c495ccf3e2`（2026-07-15，`refactor(bridge): route anthropic-direct @responses through the direct wire path, dedupe`）：把 Anthropic `@responses` 接到共享 Responses direct wire core。
- `0fd3fbbf083dffb0387828908c4f383420e0c235`（2026-07-16，`feat(bridge): direct responses→anthropic streaming response bridge (Phase 3 subtask C)`）：补齐 Responses SSE 到 Anthropic SSE 的直接回程。

## 主观建议

无。本报告只陈述最终 `HEAD` 可核验的调用链、条件、传输边界与一处活文档漂移。

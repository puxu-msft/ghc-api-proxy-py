# `The use of the web search tool is not supported.` — 根因与修法建议

**日期**：2026-08-20
**触发**：生产日志 `[FAIL] 21:43:34 400 POST /v1/messages claude-opus-5 98ms: upstream rejected the request: Error code: 400 - {'error': {'message': 'The use of the web search tool is not supported.', 'code': 'unsupported_value'}}`
**证据来源**：三份并行调查 —— [我方链路](260820-websearch-400-our-side.md)、[copilot-api-js](260820-websearch-400-copilot-api-js.md)、[vscode-copilot-chat](260820-websearch-400-vscode-ext.md)。本文档只做合成与裁决建议，细节以那三份为准。

## 1. 根因（证据权重：强，可据以动手）

Claude Code 在启用 WebSearch 时会在 `tools[]` 里发一条 Anthropic 原生 server tool 声明（`{"type": "web_search_20250305", "name": "web_search", ...}`）。这条声明**原样透传**到了 Copilot 的 Anthropic Messages 端点，被上游拒绝。

链路如下：

1. `refs/available_models.json` 中**没有任何 Claude 模型广告 `/responses`**，全部只有 `['/v1/messages', '/chat/completions']`。
2. 因此 `/v1/messages` 入站在 `src/app/pipeline/routing.py:92-95` 命中 `inbound_format_supported` 分支，`translation_required=False`（`:107`）。
3. `src/app/server/handler.py:73` 的翻译整段跳过，direct driver 把客户端 body 逐字发给上游。判据性 grep：`handler.py`、`server/inbound.py`、`pipeline/direct_driver/base.py`、`pipeline/anthropic_request_hook.py` 四个文件中 `\btools\b` 零命中（exit 1 = 真无匹配）。
4. `src/app/ghc_client/errors.py:99-105` 把 SDK 的 `BadRequestError` 包成 `UpstreamRejected`，产出日志里那句话。

**既有的能力门不在这条路上。** `src/app/protocols/anthropic_responses.py:539-540` 的 `server_tool_not_supported` 唯一调用者是 `src/app/anthropic/client.py:250`，属于 legacy app（`server/app_factory.py`）；生产走 `cli.py` → `create_pipeline_app`，两套无交集。

**推论**：本项目冻结的 server-tool no-revive 合同（`docs/tmp/260806-arbitrate-server-tool-contract.md`、`spec.md:136,159,513`）规定 typed/server tool 应**显式拒绝**，而生产在 Anthropic 直通腿上实际是**静默透传**。今天这条 400 同时暴露了一个合同与实现的偏离，不只是一个上游兼容问题。

**未覆盖**：拿不到字节级上行 payload。`HistoryConsumer` 只在 `app_factory.py:107` 接线，pipeline app 完全不引用 history；`~/.local/share/ghc-api-proxy/history.db` 里无任何 `claude-opus-5` 记录。「客户端发的是哪个 dated variant」是推断，不影响根因。

**最小判别实验**（不需动生产）：对 `/v1/messages` 发两次 `claude-opus-5` 极小请求，唯一差异是带不带 `tools: [{"type":"web_search_20250305","name":"web_search"}]`，预期实验组 400、对照组 200。

## 2. 两个参考项目分别怎么做

### vscode-copilot-chat（第一方客户端，HEAD `5863f5a70`）

**出站前硬编码剔除，不做能力协商，不做 400 后降级。**

- `src/extension/externalAgents/node/oaiLanguageModelServer.ts:133-142` —— 给 Codex CLI 当 Responses 代理时，透传前过滤掉 `tool.type.startsWith('web_search')`，日志 `Filtering out unsupported tool type`。引入提交 `52032e48d` 标题即 "Filter out unsupported codex tool type (#1748)"。
- `src/extension/chatSessions/claude/node/claudeCodeAgent.ts:432-434` —— `// TODO: CAPI does not yet support the WebSearch tool` + `disallowedTools: ['WebSearch']`。第一方直白确认后端能力缺失。
- `src/platform/endpoint/node/responsesApi.ts:42-47` —— tools 是**构造性白名单**，无条件写死 `type: 'function'`，结构上产不出 hosted tool。
- `src/platform/endpoint/common/endpointProvider.ts:45-56` —— `/models` 的 `capabilities.supports` 里**没有任何 web search 能力位**。「按 capability 位裁剪」这条假设被直接证伪。
- `src/extension/prompt/node/chatMLFetcher.ts:1470-1530` —— 4xx 分支只特化 `off_topic` 与 `previous_response_not_found`，**没有剥工具重发**。第一方把它当不可恢复错误，只在出站前预防。
- 全仓 `unsupported_value` / `web search tool is not supported` 零命中。

### copilot-api-js（我方参考实现，HEAD `17bed64a1`）

**乐观发出 → 被拒学习 → 此后提前剥。**

- `strategies/server-tool-rejection-retry.ts:44-88` —— matcher 只看 message 文本、不看 `unsupported_value` code；命中后 payload 原样回传，只置 `prepareHints.excludeServerToolTypes: ["web_search_"]`。
- 真正剥离在下一次 prepare 的 `stripServerTools`：**只剥 `tools` 声明、整条丢弃不降级**，剥空返 `undefined`。**不碰 `tool_choice`**（悬空 forced choice 无人清理），**不碰历史**。
- learned state 键 = `<上游 base URL>|anthropic-messages|<归一化 model>`，**不含 account**；落盘 `<APP_DIR>/negotiation-states.json`，默认 TTL 30 天。
- 历史块降级是**另一条腿**：`rewriteServerToolBlocks` 把 `server_tool_use`→plain `tool_use`（id/name/input 逐字保留），`*_tool_result`→字符串化文本的 user 侧 `tool_result`，且**必须劈开消息**（`tool_result` 只能在 user 轮）。触发它的是不同的 400：`Tool 'X' not found in provided tools`。

**关键限制**：这整套自愈挂在 `targetEndpoint === MESSAGES` 门上（`retry-registry.ts:140-143`）。**我们今天出事的正是这条腿**，所以 js 侧确实有现成答案 —— 但它对 Anthropic→Responses 那条腿反而是乐观映射 `web_search_*`→`{type:"web_search"}` 直通、不查账本，那条腿上它同样硬失败。

**证据强度提示**：js 侧**无 fixture/cassette**，测试全是手写 fetch-mock；唯一的真实探针 `reject-probe.ts` 结果从未回填。那句错误措辞的最强证据其实是我们自己今天的生产日志。

### 一手实测数据点（来自 js 仓 `exp/`）

- `/responses` + `{type:"web_search"}` 在 **gpt-5.5 上 HTTP 200 并原生执行搜索**（`exp/anthropic-responses-direct/FINDINGS.md:41-47`）。所以这不是「Copilot 全域不支持 hosted web search」，而是**端点/模型相关**。
- `web_fetch` 的 400 是**另一套 body**：`{"message":"rejected tool(s): web_fetch","code":"invalid_request_body"}`（2026-07-12 实测）。**按单一形状写死 matcher 会漏。**

## 3. 修法选项

### A. 出站前预防式剥离（推荐）

在 `src/app/pipeline/anthropic_request_hook.py` 的 `fix_anthropic_request` 里加一条 fixup：Anthropic 腿出站前，剥掉 `tools[]` 中带 server-tool `type` 的声明，并清理由此产生的悬空 `tool_choice`（named choice 指向已剥工具 → 一并去掉；`tools` 剥空 → 整个字段去掉）。剥离要在请求日志里可见，不做静默。

- **先例**：同一钩子里的 `normalize_context_management`（`:36-53`）形状完全相同 —— Claude Code 发上游拒收的东西，我们出站前改写，注释记录了对真实上游的实测。这不是新产品能力，是同类兼容修复。
- **与第一方一致**：vscode ext 就是这么做的，而且它连 Claude Code 那侧都直接 `disallowedTools: ['WebSearch']`。
- **代价**：web search 能力对客户端消失（模型不再有该工具）。这是可感知的能力删减。
- **作用域**：只在 Anthropic Messages 直通腿上剥。不要推广到 Responses 腿 —— 那里 gpt-5.5 实测 200。

### B. 本地显式拒绝

把既有的 `server_tool_not_supported` 门接到生产 pipeline 上，请求根本不发出去，返回稳定错误码。

- **与冻结合同最一致**（`spec.md:136,159,513`：typed/server tool 显式 REJECT）。
- **代价**：用户必须在 Claude Code 侧关掉 WebSearch，否则每个请求都失败。今天的症状不会消失，只是错误变得清晰且本地化。

### C. 反应式 400 → 剥离 → 重试 + learned state（copilot-api-js 式）

- **代价最大**：本项目 `src/app/pipeline/exceptions.py:60-66` 明示 400 故意不可重试，这是新增机制而非修 bug。`docs/tmp/260818-retry-gap.md` 已经盘点过整条策略链我们都没有。
- **收益**：能自动适配「哪些模型/端点支持」，不必写死判断。但我们已经从模型目录知道**没有 Claude 模型走 `/responses`**，且第一方把同一结论硬编码了，眼下这个自适应能力用不上。

### 我的偏好

**A**，理由是它最小、与第一方一致、有同钩子内的先例，且能立刻让 Claude Code 会话恢复可用。B 在合同上更纯，但把一个能自动修好的问题推回给用户手工配置。C 留到真正需要跨模型协商时再说。

## 4. 需要用户裁决的点

A 与 B 是**可观察的产品行为分歧**，且触及既有冻结合同：

- `docs/2604-rewrite/hooks-tokenization-spec.md:126` 写明 mandatory sanitizer「只处理 client tools；`server_tool_use` 与 `*_tool_result` 不进入配对修复，也不获得任何 server-tool 降级、过滤或重试支持」，并称残留历史被上游拒绝是**有意的 breaking removal**，项目「只提供清晰错误与 release note，不保留隐式 downgrade sanitizer」。该条支持 B、反对 A。
- 反面证据：同一钩子里的 `normalize_context_management` 说明该钩子本就承担「改写上游拒收的请求字段」这一职责，且 `docs/tmp/260806-arbitrate-server-tool-contract.md` 反对的是**把 server tool 映射为 hosted builtin**（revive），剥离不是 revive。

这两条哪个更近，需要用户拍板。

## 5. 若采纳 A，实施切片

1. **切片一（本次 400）**：剥 `tools[]` 中的 server-tool 声明 + 清理悬空 `tool_choice`，请求日志可见。加一个针对该形状的单测。
2. **切片二（下一轮 400）**：历史里残留的 `server_tool_use` / `*_tool_result` 块降级。**只有在会话历史来自真实 Anthropic、或曾在剥离生效前产生过 server-tool 块时才需要**；若从第一个请求就剥，模型永远不会产出这类块。命中时上游报的是**另一句** `Tool 'X' not found in provided tools`。降级时注意 js 侧踩过的坑：`tool_result` 只能在 user 轮，必须劈开消息，否则一个 400 换另一个 400。
3. **不要**按单一错误文本写死判断：`web_fetch` 的拒绝是完全不同的 body 形状。判据应基于**我们自己发出的 tool `type`**（出站前预防），而不是基于上游错误措辞（反应式）—— 这也是 A 相对 C 的一个附带优势。

## 6. 顺带记录的未处置发现

来自 [我方链路报告](260820-websearch-400-our-side.md)，本次不处理：

- `src/app/pipeline/translation_driver/openai_responses.py:121-136` —— 同类敞口，今天没击发：无 `input_schema` 的 typed tool 原样返回。
- `src/app/pipeline/translation_driver/anthropic_messages.py:184-185,228` —— UNKNOWN block 与 tools 逐字透传。
- `feature_negotiation.py` 是缺两个类别的孤儿模块。
- pipeline app 不接 history，导致**无法取到真实上行 payload**。这是排障能力缺口，不是本次 bug。

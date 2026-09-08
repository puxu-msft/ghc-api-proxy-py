# Python／近似桥接参考调查：Anthropic Messages → OpenAI Responses

调查日期：2026-08-06。

调查结论：三个参考仓库都提供了可复用部件，但没有一个可以整体照搬。`caozhiyuan-copilot-api` 提供最直接的 Anthropic Messages→Responses 请求、非流式响应和 SSE 状态机；`hooyoo-copilot-bridge` 提供更强的中间表示、扩展字段保真、错误终止与 fixture round-trip 方法；`ghc-api-py` 的近似桥接实际是 Messages→Chat Completions，价值主要在直接 Anthropic 旁路、有限提交窗口与工具泄漏恢复。所有参考实现的逐 token／event 即时下游写出都服从本项目既有裁决：**block-level buffering 是基础产品合同，下游不承诺 token／event 级 live streaming**。本调查不改变该裁决，也不替它决定尚未裁决的 block 定义、失败重取、内存／磁盘预算、背压、取消和 History 提交时点。

## 来源快照

请求路径 `/home/xp/src/copilot-api-js/refs/ghc-api-py` 物理解析为 Git top-level `/home/xp/src/refs/ghc-api-py`。首次 gate 记录 `9d284c457120e618689ba22ff29a51c6fa03cef5`，随后检测到并发 HEAD 漂移；所有最终代码结论基于重新冻结并在写入前复验的 `8d064a27308ed249da8c9ce7ecc54c89ee68c151`。顶层包括 `ghc_api/`、`tests/`、`scripts/`、`README.md`、`requirements.txt`、`setup.py`。

请求路径 `/home/xp/src/copilot-api-js/refs/caozhiyuan-copilot-api` 物理解析为 Git top-level `/home/xp/src/refs/caozhiyuan-copilot-api`，HEAD `6b97876927b7209a1e0f498e81927b32cc443e52`。顶层包括 `src/`、`tests/`、`copilot-api/`、`pages/`、`README.md`、`package.json`、`bun.lock`。

请求路径与 Git top-level 均为 `/home/xp/src/copilot-api-js/refs/hooyoo-copilot-bridge`，HEAD `2032fdd782aa1166eea0286977c59ab93eb5cab2`。顶层包括 `src/`、`tests/`、`docs/`、`openspec/`、`README.md`、`CopilotBridge.slnx`。

三个仓库均在同一次 shell 调用内打印并校验 `pwd -P`、`git rev-parse --show-toplevel` 与完整 HEAD；均无 `.codegraph/`。本次未运行测试，因为 Bun／.NET／Python 测试可能写缓存、构建输出或临时文件，而用户只授权写本报告。

## 对比与结论

1. **路由与桥接边界。** `ghc-api-py/ghc_api/routes/anthropic.py` 优先把支持 `/v1/messages` 的模型直接送原生 Anthropic upstream，不支持时才转成 `/chat/completions`，所以它是近似参考而非 Responses 参考。`caozhiyuan` 在 `src/routes/messages/handler.ts` 按模型的 `supported_endpoints` 依次选择原生 Messages、Responses、Chat Completions，Responses 路径完整落在 `responses-translation.ts` 与 `responses-stream-translation.ts`。`hooyoo` 以 Anthropic-shaped IR 为 hub：Claude Code inbound 是 identity，路由到 `CopilotResponsesStrategy` 后由 T2 构建 Responses wire、T3 把 Responses SSE 转回 Anthropic IR。可复用方向是“能力驱动路由＋独立 leg”，不能把某模型家族名直接等同于固定 endpoint。

2. **请求消息与顺序。** `caozhiyuan` 将 `system` 合并为 `instructions`，以 `flushPendingContent` 在 `tool_result` 前结束普通 user message，从而把 `function_call_output` 保持为独立 item；assistant text 与 `tool_use` 同样分段。它还固定 `temperature: 1`、`parallel_tool_calls: true`、`store: false`、`reasoning.summary: detailed`、`include: [reasoning.encrypted_content]`，并把 `max_output_tokens` 至少抬到 12800——这些是该项目策略，不应无条件复制。`hooyoo` 的 T1／T2 用 typed IR 保存 message／tool item 顺序，并用 `ProviderExtensions["openai"]` 旁袋保存 IR 无类型槽位的 Responses 字段；这是长期保真的更好基座。`ghc-api-py` 的 Chat fallback 会先发同一 user turn 内全部 tool messages，再发其他 user content，且把 assistant `thinking` 拼入可见文本，语义损失较大。

3. **工具请求与结果。** 三者都保持 `tool_use.id`／`tool_result.tool_use_id` ↔ `function_call.call_id`／`function_call_output.call_id`。`caozhiyuan` 支持 string／text／image／`tool_reference` result，`is_error` 映射为 `status: incomplete`；tool schema 经过 normalize，`any` 映射 `required`。`hooyoo` 更严格：Responses 历史 tool arguments 必须是 JSON object，畸形或 array／scalar 抛 typed 400；Claude 的 result block array 会压成 Responses 可接受的 string；被过滤工具对应的强制 `tool_choice` 会降为 `auto`，避免引用不存在工具导致 upstream 400。建议复用“call_id 不变量＋typed 400＋survivor-aware tool_choice”，但具体 server／IDE tool 过滤仍须按本项目 feature negotiation 决定。

4. **reasoning／thinking 请求回灌。** `caozhiyuan` 把 Anthropic `thinking.signature` 约定为 `encrypted_content@id`，回建 Responses reasoning item；compaction 另用 `cm1#<encrypted>@<id>` carrier。`hooyoo` 用 `RedactedThinkingBlockParam` 保存 encrypted content，并在 part-level provider bag 保存 reasoning id；普通未加密 `ThinkingBlockParam` 因 Responses 不接受而显式丢弃。前者实现简单但自定义字符串 carrier 需要转义／版本化契约，后者的 typed opaque block＋扩展 bag 更可复用。不要把可见 thinking 文本伪装成普通 assistant text；`ghc-api-py` fallback 正有此风险。

5. **非流式响应。** `caozhiyuan` 将 Responses `reasoning`、`function_call`、`message`、`compaction` output items 映射为 Anthropic content blocks，映射 usage 与 `completed`／`incomplete` stop reason；畸形 function arguments 不丢失，而是回退为 `{raw_arguments: ...}`。`hooyoo` 当前存在关键接缝风险：`CopilotResponsesStrategy` 对非 SSE success／error 只缓冲原始 Responses bytes，`ClaudeCodeOutboundAdapter.AdaptBufferedAsync` 又是 identity，因此 `/cc` 路由在 `stream:false` 或 upstream 未返回 SSE 时可能把 Responses JSON 直接交给 Anthropic client。只能复用其流式 T3，不能把当前 buffered 接缝视为完整 Messages→Responses bridge。

6. **流式响应状态机。** `caozhiyuan` 逐事件将 `response.created`、output item、text delta、reasoning summary delta、function arguments delta、terminal 转成 Anthropic grammar；用 `(output_index, content_index)` 分配稳定 block index，并在切换 block 时闭合前一 block。`hooyoo` T3／T4 也维护显式 block 生命周期，且 T4 为 `*.done` 与 terminal 重建完整 item；它用真实 Responses SSE fixture 验证 text／tool delta 拼接与 terminal。`ghc-api-py` 的 Chat stream 状态机较简单，按 tool index 转发 argument fragment，但缺少 Responses 的 item／content 双层索引。建议以 `caozhiyuan` 的 Responses 事件覆盖面结合 `hooyoo` 的双向 grammar／fixture 方法，而不是采用 Chat 状态机。

7. **reasoning／unknown stream event 风险。** `caozhiyuan` 会流式发 `thinking_delta`，在 reasoning item done 时发 `signature_delta`，空 summary 用固定 `Thinking...` 占位。`hooyoo` 的 T3 明确吞掉 `reasoning_*` stream events，并跳过 reasoning output item，因此它适合 Codex→Responses 近透传，却不满足 Claude Code 需要可见 thinking／signature 的完整 Anthropic 响应保真；T4 也只识别 text／tool block。两者 default 分支都会丢未知事件。目标实现应把“已知但无目标形态”“真正未知”“控制事件”分开记账，并给 unknown 事件可观测告警／sidecar；不能静默把未来协议扩展当成功。

8. **buffering 裁决与可借用边界。** `caozhiyuan`、`hooyoo` 的转换器都在收到 delta 后立即产出下游 delta；`hooyoo` 的 `_textBuffer`／`_argsBuffer` 只为生成 done item，不延迟已发 delta。`ghc-api-py` 有两种窄缓冲：`RetryingResponsesResponse` 只缓存 `created／in_progress／queued` 前导，首个实质事件后立刻提交并禁止重试；`LeakedToolCallTransformer` 只 hold back 可能长成 `<invoke>` 的危险后缀。它们可借鉴“明确 commit frontier、提交后禁止重放、缓冲状态与转换状态分离”，但都不是本项目已裁决的 block-level 下游交付实现。复用任何状态机时，必须把“解析出 delta”与“block 达到可提交边界”拆开；不得恢复旧的默认零缓冲产品合同。

9. **错误与终止。** `caozhiyuan` 在 upstream HTTP 非 2xx 时抛 `HTTPError`；流内 `response.failed`／`error` 转 Anthropic error，流无 completion 时补 error；tool argument 连续空白超过阈值也终止为 error，但阈值是该项目经验规则，不能当协议事实。`hooyoo` 用私有 IR `error` stop marker 保证 `response.failed` 仍是 honest failed terminal，空流／截断也合成成对终止并记录 `UpstreamStreamFault`；这是最值得复用的错误状态机。不过它对非空畸形 SSE 只 warning 后跳过，可能把协议破坏降级成看似成功。`ghc-api-py` direct stream 会规范化 SSE error；Chat fallback 的 timeout／connection error主要记日志与 cache，可能在无明确下游 error terminal 的情况下结束，风险最高。

10. **测试证据。** `ghc-api-py` 有 direct handler no-op 隔离、逐字符 tool leak、thinking policy、Responses early-failure retry toggle 等针对性测试，但本次快照未见完整 Anthropic→Chat request／response fixture round-trip。`caozhiyuan` 的 Responses 测试覆盖普通 user text、metadata cache key、tool reference、非流式 reasoning＋tool，以及 function argument delta／done；未覆盖完整 stream 生命周期、交错多 block、unknown event、`response.failed`、截断、reasoning signature round-trip。`hooyoo` 最强：真实 captured SSE fixture、请求 bag canary、tool pairing、usage 子计数、empty／failed／incomplete／malformed／multi-block 顺序均有测试；但仍缺 `/cc stream:false → /responses → Anthropic JSON` 的端到端测试，正好未拦住第 5 条接缝。

11. **优先可复用清单。** 第一优先复用 `caozhiyuan` 的 Anthropic↔Responses 字段映射矩阵与 Responses event coverage；第二优先复用 `hooyoo` 的 provider-extension bag、typed bad request、call-id／block-order 不变量、honest failed terminal、真实 fixture＋合成边界用例；第三优先复用 `ghc-api-py` 的 direct Messages capability bypass、commit frontier 与可开关 recovery 隔离。复用应落在本项目独立的 pure translation／stream parser 层，HTTP transport、retry、History 与 block-level delivery 仍由本项目 pipeline 编排。

12. **实施前风险门。** 必须先冻结双向字段表和两套 oracle：请求侧验证顺序、role、tool pairing、opaque provider fields、reasoning identity；响应侧验证 block grammar、text／args 拼接、usage、stop／error、unknown event 与 cancellation。随后把相同事件流分别喂给“逐事件解析器”和“block-level 下游提交器”，证明转换正确性不依赖 live flush。至少加入一个跨真实 upstream fixture 的单向 oracle，避免只做同源 encode↔decode round-trip；并专门加入非流式 Anthropic client→Responses upstream→Anthropic response 测试，以阻断 `hooyoo` 第 5 条所示的 raw Responses 泄漏。

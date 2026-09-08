# copilot-api-js：inbound → IR → outbound 架构调查

## 口径

- 调查对象是 `/home/xp/src/copilot-api-js`；本报告的相对路径均以该仓库根目录为准，源码行号取自当前工作树。
- 仅执行只读检索和 `git -C` 的只读查询；未连接、信号、停止或重启 `127.0.0.1:4141` 的进程。

## 1．IR 的实际形状

- 它不是单一 DTO：请求走独立的 ordered-turn 模型，响应走事件化 `SemanticLedger`；`core/turn-model.ts:1-10` 明确禁止把请求复用为 response ledger。
- 请求的核心类型是 `TurnToken`：`ordinal`、`messageIndex`、`role: "assistant" | "user" | "system"`、`kind`、原始 `value: unknown`、可选 `correlationId`，见 `src/lib/translation/core/turn-model.ts:32-57`。
- 请求 token 的 `kind` 是 `reasoning | text | image | unknown | tool-use | tool-result | server-tool-use | server-tool-result | system-message`；它保留顺序和消息边界，不将内容块归一为单一字段形状，见 `core/turn-model.ts:37-54`。
- Anthropic request reader 将 `text/image/thinking|redacted_thinking/tool_use/tool_result/server_tool_use/*_tool_result` 映为上述 kind；未知 block 变 `unknown` 而非丢弃，见 `to-ir/anthropic/request-read.ts:23-46,75-89`。
- Responses request reader 将 `message/function_call/function_call_output/reasoning` 映为 `text/tool-use/tool-result/reasoning`；未知 item（含 `item_reference`）也保留为 `unknown`，见 `to-ir/openai-responses/request-read.ts:29-48,67-111`。
- 响应 item 的声明联合是 `ItemKind = reasoning | text | function-call | function-result | server-tool-call | server-tool-result | degraded-text | drop`；`SemanticItem` 给出带终态和 disposition 的 settled view，而 ledger snapshot 实际保存 `PerOutputItemState`，见 `core/types.ts:186-315`、`core/snapshot.ts:29-34`。
- 文本是 `text`／`degraded-text` item 的有序 `PartState`；part 有 `kind: reasoning-summary | reasoning-content | text`、delta、`authoritativeText` 和 terminal，见 `core/types.ts:274-315`。
- 工具调用持 `CallMetadata { callId, name, sourcePayload? }` 与最终 `arguments`；工具结果持 `ResultMetadata { callId, name?, isError, sourcePayload? }` 与最终 `output`，见 `core/types.ts:200-253`。
- 图片只出现在请求 `TurnToken.kind === "image"`：Anthropic writer 将 Responses `input_image` 还原为 Anthropic image block，见 `from-ir/anthropic/request-write.ts:72-78,217-223`；Responses writer 将 Anthropic image 加入 message content parts，见 `from-ir/openai-responses/request-write.ts:182-187`。响应 `ItemKind` 没有 image arm。
- refusal 也没有专属 IR item/block：Responses `response.refusal.delta` 和 final `part.refusal` 均写成 text part，见 `to-ir/openai-responses/response-wire.ts:294-305,421-431`；Anthropic 的结构化 `stop_details` 则保留在 response metadata 的 `terminalDetail: unknown`，见 `core/types.ts:344-365` 与 `to-ir/anthropic/response-wire.ts:145-180`。

## 2．inbound／outbound 如何配对和分发

- 目前没有「格式插件注册表」：request bridge 显式组合 `readAnthropicRequest → writeResponsesRequest` 或 `readResponsesRequest → writeAnthropicRequest`，见两个 bridge 的 `anthropic-to-responses-request-via-ir.ts:69-104`、`responses-to-anthropic-request-via-ir.ts:34-60`。
- 响应则由 `<protocol>/response-wire` decoder 产出 `LedgerUpdate`，`SemanticLedger` 接受 update 后向 non-stream emitter 提供 snapshot、向 stream emitter 提供 transition feed，见 `core/types.ts:371-399`、`core/snapshot.ts:29-54`、`core/ledger.ts:100-117`。
- HTTP 路径的选择仍在 `hub-translate.ts`：请求表 `REQUEST_BRIDGES` 是 `Record<ClientFormat, Record<UpstreamEndpoint, RequestBridge>>`，见 `src/lib/pipeline/hub-translate.ts:120-219`；非流式、正向流式、反向流式分别是三个穷尽表，见 `:244-287,320-380,450-529`。
- 其中两条 request IR bridge 和三条 response／stream IR bridge 被 hub 显式 import，并落在 anthropic↔responses 的对应表项，见 `hub-translate.ts:64-70,156-181,263-279,350-356,480-503`。
- router 的 `IR_CARRIED_PAIRS` 是另一个显式 allowlist，只开 `anthropic → /responses|ws:/responses` 与 `openai-responses → /v1/messages`；其他 translate 决策改为 `400 translation-not-carried-by-ir`，见 `src/lib/pipeline/router.ts:108-136`。
- 因而按当前代码新增一个 IR 协议不是填一处注册：文档规定各加 `to-ir/<协议>/` 和 `from-ir/<协议>/`，再接 bridge、hub 的 request／非流式／两类 stream 表，以及 router allowlist；`BridgeProtocol` 目前还从词汇表只抽取两个协议，见 `docs/format-translation/README.md:29-39`、`core/types.ts:29-43`、`router.ts:119-126`。

## 3．无法表达、未知值与有损转换

- 没有统一的 `Conversion.losses` 信封。请求 writer 返回 `TranslationObservation[]`，其每项含稳定 `reason`、`detail`、可选 `ordinal/blockType/signed`，见 `core/turn-model.ts:68-88`、`from-ir/openai-responses/request-write.ts:69-75`、`from-ir/anthropic/request-write.ts:55-61`。
- 响应 emitter 返回 `EmitObservation[]`；`reason` 来自 `DEGRADATION_REASONS`，而不是从英语描述解析，见 `from-ir/openai-responses/response-body.ts:44-61`、`core/types.ts:67-106`。
- 每个 settled response item 还必须带双平面 `ItemDisposition`：presentation 为 `native/degraded/dropped`，continuation 为 `none/native/carrier/rejected`；二者刻意独立，见 `core/types.ts:131-155`。
- `drop` 是显式 item，ledger 强制其只能 `discarded`；未知 Anthropic output block 被 decoder 变为该 item，见 `core/ledger.ts:305-342`、`to-ir/anthropic/response-wire.ts:340-355`。
- 具体无法表达会形成 observation，例如 function result 没有 Responses output item、独立 server-tool result 没有 Responses item，见 `from-ir/openai-responses/response-body.ts:238-267`；Anthropic `tool_result` 内 image 无 `function_call_output` 槽时被 dropWarn 且输出仅拼文本，见 `from-ir/openai-responses/blocks.ts:35-60`。
- 这不是所有 payload 字段的统一审计：两个 request bridge 都以注释列出无对应物而直接省略的顶层参数，例如 Anthropic `top_k/stop_sequences/context_management` 与 Responses `previous_response_id/store/metadata/truncation`，见两个 request bridge `:83-88`、`:44-45`。

## 4．推理／思考与 opaque state

- 响应的统一载体是 `ReasoningExchangeItem`：`visible` 为 `summary{text}|omitted|redacted`，可选 `opaque` 为版本化 `claude-signature` 或 `responses-encrypted` bytes，并带 source identity、boundary、correlationId，见 `core/types.ts:162-180`。
- Anthropic decoder：`thinking` 建 reasoning-content part，signature 累积为 opaque `claude-signature`；`redacted_thinking.data` 变 `visibleKind: redacted` 和同类 opaque bytes，见 `to-ir/anthropic/response-wire.ts:320-332,382-386,259-266`。
- Responses decoder：summary 与 content 是同一 reasoning item 下各自索引的 `reasoning-summary`／`reasoning-content` parts，`output_item.done.encrypted_content` 变 opaque `responses-encrypted`，见 `to-ir/openai-responses/response-wire.ts:7-20,332-342,408-418`。
- 从 IR 写回 Responses 时，原生 `responses-encrypted` 直接写 `encrypted_content`；跨协议 Claude signature 才编码成 carrier，编码失败会产生 `thinkingSignatureNotPortable` observation，见 `from-ir/openai-responses/response-body.ts:152-203`。
- 从 IR 写回 Anthropic 时，Claude signature 原样作 `thinking.signature`；Responses opaque state 用 proxy synthetic signature 承载，且仅 Responses source 会生成该 carrier，见 `from-ir/anthropic/response-body.ts:123-149`。
- 请求方向只重放本代理可识别的 carrier：Anthropic 真签名／redacted thinking 不能伪造为 Responses reasoning，记录 `thinkingSignatureNotPortable` observation，见 `from-ir/openai-responses/request-write.ts:216-248`；反向方向同样只重建本代理签发的 Claude signature，见 `from-ir/anthropic/request-write.ts:118-136,255-270`。

## 5．完成度、并存路径与演进证据

- 当前状态是「已完成的窄 pair，未完成的全矩阵」：`docs/DESIGN.md:78-80` 标 `[wip]`，只允许 anthropic↔openai-responses 双向四条腿；`openai-cc` 与 `gemini` 在 `BridgeProtocol` 类型上不可表示。
- 实施提交集中于 2026-08-15：`5da7844`（06:31:59，ordered-turn）、`b5924da`（07:17:21，Anthropic→Responses request）、`6b8ce78`（08:58:27，Responses→Messages，称“completing the pair”）；2026-08-15 `22611e0` 将 IR 对旧桥的依赖反转，2026-08-16 `f016950` 仍记录 reasoning encrypted-content 的实测结论。证据命令：`git -C /home/xp/src/copilot-api-js log --date=iso-strict --format='%H %ad %s' -n 1 <上述哈希>`。
- 新旧路径确实并存：`hub-translate.ts:70-86` 同时 import IR bridge 与 `legacy-direct/index`；但针对 anthropic↔responses 的 legacy 模块，目标仓库的 README 声明已无生产调用、只保留作差分 oracle，其他 pair 则留在树上但由 router 拒绝，见 `docs/format-translation/README.md:41-46`。
- 迁移说明存在且明确当前范围：`docs/format-translation/README.md:18-20,23-45` 记录 2026-08-15 两协议对已走 IR、目录迁移和旧桥角色；`docs/format-translation/2026-08-08-anthropic-responses-semantic-bridge.md` 是其引用的 Accepted v2 RFC。
- 同一 README 也写明外置 inbound formats 的 spec 尚未执行，且全局终局架构存在未裁决贯通性缺口，见 `README.md:6-10,64-67`；这与「该 pair 已接入」是并存状态，不是互相否定。

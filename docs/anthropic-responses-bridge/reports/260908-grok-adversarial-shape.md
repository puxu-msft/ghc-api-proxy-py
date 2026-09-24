# Anthropic Messages ↔ OpenAI Responses 翻译路径：反方架构审查

- **评审范围**：`HEAD e593cf0c89107708a60587e5a772a7c62d9f3ce6` 上 Anthropic Messages ↔ OpenAI Responses 翻译路径的长期模块形状。核心被检对象：`translation_driver`、`delivery/formats/openai_responses.py`、`response_observation.py`、`delivery_policy.py`、`reply.py`、`driver.py`。问的是这些模块是否真正满足已接受的方案 B：shared semantic kernel、stream/non-stream parity、single owner、transport/delivery 正交。不是行为验收，不是实现修复。
- **总体 verdict**：**当前模块切缝不是长期形状。** 它既不满足已接受的方案 B（typed semantic kernel＋single driver＋protocol／transport 正交），也不满足人写文档要求的「只经 IR、不直接 wire↔wire」。请求侧有半套 kernel（`SemanticRequest`），响应侧是两套转换器加一套旁路观察器。不能在此切缝上「补全 B」。
- **blocker 数**：2
- **major 数**：3
- **minor 数**：2
- **审查身份**：独立反方；判据不从被检代码反推。本轮只读，不改生产代码，不碰并行会话未提交改动。
- **代码锚点**：物理仓库 `/home/xp/src/ghc-api-proxy-py`，`HEAD e593cf0c89107708a60587e5a772a7c62d9f3ce6`。工作树在审查范围内若干文件有并行未提交改动（含 `driver.py`、`response_observation.py`、`delivery/formats/openai_responses.py`、`translation_driver/responses.py`）。**被检对象是 HEAD tree，不是工作树 diff。** 并行会话 `fd74ca3f` 的用户原话只作意图锚，其尚未提交的实现不进入被检对象。

## 边界

**在范围内**

- 翻译路径的模块接口、owner、依赖方向、语义单源与交付接缝。
- 对照判据：`D-ARCH=B` 五项不可拆分核心；`D-MIGRATION=M1`；Spec 的 reasoning cardinality、tool search、unknown item、terminal/usage、block order、retry/frontier。
- 推荐目标目录／接口，以及能让错误形状变红的反例测试。
- 三分处置：必须现在修的结构错误；可局部保留的迁移形态；暂时不值得动的代码。

**明确不在范围内**

- 不修改任何生产代码、测试、Git index／refs。
- 不把并行会话工作树当 current 形状。
- 不重开 Spec 已决可观察行为；不把 Architecture 可局部调整的命名／文件拆分升格为 blocker。
- 不验收完整产品 `PASS`；不跑会改状态的命令。只读探针若执行，会在搜索面写明。
- 不把 `TODO_CURRENT.md` 当判据：用户已裁定其依据悬空。

## 判据来源（先于被检对象）

按权威递减。冲突时行为回 Spec，架构回用户对 Architecture 的裁决，人写文档覆盖实现细节授权但不覆盖 Spec。

### 一手用户意图

并行重构会话 `fd74ca3f-9d8a-4b0b-b25a-ddf1523d71d4` 的逐字原话（local session store `turns`）：

1. 「重构本项目对 anthropic-messages <-> openai-responses wire format 的翻译路径，可以参考具备类似能力的项目」
2. 「现在的模块间结构是长期最优的形状吗」
3. 「完整做完这套长期形状」

这三句构成**意图**：用户要的是长期形状，不是局部接线修补。它们**不是**对具体目录、类名或迁移节奏的新裁决。长期形状的内容仍以 2026-08-19 已关闭的 `D-ARCH`／`D-MIGRATION` 为准。

### 已接受架构（`architecture.md`，2026-08-19）

- `D-ARCH = B`：typed semantic kernel＋single driver＋protocol／transport legs。
- `D-MIGRATION = M1`：一次建立完整 B 骨架。注意这与文档推荐的 M2 **不同**，以用户裁决为准。因此「长期保留 A 形 adapter」不是已授权迁移形态；A 只在 M2 下作为受约束过渡存在，而 M2 未被接受。
- 选择 B 时不可拆分的五项：
  1. Typed facts 是内部共享真相；Anthropic／Responses wire 只在 adapter／codec 边界存在。
  2. Single driver 是唯一 lifecycle 与 action owner。
  3. Protocol leg 与 transport leg 正交。
  4. Assembler／sequencer／sink／frontier 是一条完整交付链。
  5. History projection ownership 与 request lifecycle 分离。
- Converter 三段式：`AnthropicInboundAdapter` → `ResponsesRequestCodec` → `ResponsesResponseNormalizer`；非流与流式必须调用相同 block constructors。
- 方案 C（route 调现有 Responses pipeline）拒绝。
- Architecture 顶部授权：实现细节可推进 B，发现与用户文档不一致再讨论；**不覆盖 `spec.md`，不覆盖 `docs/.human-controlled/`。** Architecture 自身写明 `delayed response-start` 一族是非规范旧链描述，不得覆盖 Spec 2026-08-22 headers 合同。

### 行为 oracle（`spec.md`）

承重、且迁移时易破坏的合同：

- 单一 Anthropic pipeline owner；Responses 只是 attempt transport＋direct converter＋block buffer。
- Chat Completions 不得作语义中间表示。
- 一 Responses reasoning item → 一 Anthropic thinking block；禁止跨 item 聚合／last-ciphertext-wins；非空 encrypted-only 不得丢。
- 客户端已声明的 tool search 翻译，不再剥离；tool 声明白名单重建；server-tool no-revive。
- 未知 output item／未知 content part／malformed lifecycle → `REJECT`，不得用空 text 或正常 terminal 掩盖。
- stream 与 non-stream 对同一 fixture 归一为相同 ordered blocks、usage、stop reason、explicit losses。
- HTTP SSE 与 upstream WS 共享同一语义核心。
- retry 与 commit 共用 frontier：headers 绑定第一次上游 HTTP 200；`message_start` 与首个完整 block 同 batch；post-commit 禁止透明 full replay。
- 输出顺序由 Responses item／content part 语义顺序决定，不按类型或完成时间重排。

### 人写文档（覆盖实现细节授权）

- `docs/.human-controlled/message-translation.md`：翻译路径必须经内部 IR，不直接建立两种 wire 之间的映射；`translation_driver` 注册 inbound／outbound translators。
- `docs/.human-controlled/request-pipeline.md`：统一 `ClientRequest`／`UpstreamAttempt`；路由判定是否需要格式翻译。
- `docs/.human-controlled/module-org.md`：`app.pipeline` 与 `app.pipeline.delivery` 已追认；`app.anthropic`／`app.openai` 尚未确认。
- `docs/.human-controlled/client-side-block-delivery.md`：完整块才交付；headers 在第一次 HTTP 200 转发。
- `docs/.human-controlled/upstream-retry-and-continuation.md`：无痕重试 vs 合成续写；非流式同样支持。

### 研究与反例（`research.md`，非产品合同）

可移植：能力驱动 leg、单跳 direct bridge、按 item／block identity 分桶、独立 delivery owner、commit frontier 驱动 retry。不可照搬：request block 顺序重排、tool-name sanitizer 未接线、non-stream reasoning 聚合、未知事件静默空数组。

### 明确不是判据

- `implementation.md` 的切片进度与历史 canary。
- `TODO_CURRENT.md`。
- 并行会话尚未提交的设计或代码。
- 参考实现（sub2api、copilot-api-js）的字段取舍。

## 承重问题（本轮必须对过）

1. 是否存在真正的 shared semantic kernel，还是两套 wire 互转外加若干 dict？
2. stream 与 non-stream 是否共享同一 block constructors／field mapping，还是平行实现？
3. 是否只有一个 lifecycle owner，还是 delivery／observation／reply／driver 各自推进 frontier／retry／finalize？
4. transport 与 delivery 是否正交，还是 Responses format 模块同时做解析、翻译、交付政策？
5. 迁移时下列行为会不会被拆模块拆坏：reasoning cardinality、tool search、unknown item、terminal／usage、block order、retry／frontier。

## 判据矛盾（先于发现）

两份用户侧权威对「内部状态该不该有 owner」不一致。本轮**不发明裁决**，只声明后果。

| 来源 | 要求 |
|---|---|
| `architecture.md` `D-ARCH=B`（记录为 2026-08-19 已接受） | Request／route／attempt／conversion／delivery facts 有具名类型与唯一 owner；wire 只在 codec 边界 |
| `docs/.human-controlled/request-pipeline.md` | 统一可变 `ClientRequest`；订阅者可改上下文；用户裁定不适用 ownership／permission |

现行代码跟的是后者：`RequestContext` 自述「Every field is writable by design」。因此即使用户现在要「完整做完长期形状」，**必须先承认**：做成 B 会碰到人写文档的可变上下文；做成「只加深 translation_driver IR」则不会自动得到 B 的 single driver／typed facts。下面发现按 **B + Spec + message-translation.md 的 IR 单源** 对照；与可变上下文冲突的项标为建议，不升格为 blocker。

`architecture.md` 顶部「已获用户接受」是文档自述，本轮未检索到 2026-08-19 用户逐字原话。按 as-reviewer 权威归属：该接受记录继续作为架构判据来源引用，但不把未核验的原话再传播一遍。

## 地图

HEAD 上这条翻译路径实际是四层，不是方案 B 的一层 kernel：

```
inference.py (route: 首 attempt + body replay + 选 assembler/framer)
    ├─ driver.handle / _drive          # 翻译一次，然后 DirectDriver 打到 headers
    ├─ translation_driver.registry     # 请求 IR；非流响应 IR
    ├─ reply.response_payload          # 非流：translate_response
    ├─ delivery_policy.assembler_for   # 流：ResponsesAssembler（第二套转换）
    ├─ delivery.stream_delivery        # commit／replay／hand-over
    └─ response_observation            # 第三套 Responses 解析，只写日志
```

**承重接缝**

1. `TranslatorRegistry.translate`：Anthropic→`SemanticRequest`→Responses，单跳，不经 Chat Completions。请求 IR 成立。
2. `TranslatorRegistry.translate_response`：只服务非流。`reply.response_payload` 是唯一调用方。
3. `ResponsesAssembler`：自己把 SSE item 收成 Anthropic `CompletedBlock.payload` dict，**不**调用 `response_blocks_from_item`。
4. `inference.py` `_reopen`：driver 返回之后再 `replay_prepared`。driver／RequestContext 注释都承认这件事。
5. `context.extras[CLIENT_SEARCH_TOOL|HOSTED_WEB_SEARCH_EXPECTED]`：tool search 的跨半场合同，不是 typed ConversionFacts。
6. `app.protocols.responses_anthropic.convert_responses_response_to_anthropic`：第三套 JSON 转换器；生产路径不用，单测仍当 oracle。

**依赖方向（HEAD，无 import 环）**

```
delivery_policy → driver.HandledRequest
reply → driver + delivery_policy
request → delivery.assembling.Terminal + ResponsesObserver
delivery/formats/openai_responses → translation_driver.responses + reasoning_bridge + protocols.usage
translation_driver 不反向依赖 delivery（除 chat completions 一处）
```

不是环，是**分层倒置**：delivery 选择依赖 lifecycle DTO；通用 `RequestContext` 依赖 Responses 观察器。

**可疑处（深入前）**

- 同一未知 item：流式 `REJECT`，非流 `ITEM_NOT_CARRIED` 后继续。
- 同一 message item 多 content part：流式一个 TEXT draft，非流按 part 拆块。
- 畸形 tool arguments：流式 `{"__raw": ...}`，非流保留原字符串，Spec 要求 conversion error。
- usage：两处 wrapper 吞 `ResponseConversionError` 成 `{}`；观察器另走 `convert_responses_usage`。

## 事实性发现

### F-1 · blocker · 响应转换没有 shared semantic kernel，流／非流是两套规则

- **判据**：`D-ARCH=B` 核心 1 与 Converter 三段式；Spec「text／tool／reasoning 在 non-stream 和 stream 归一化结果中一致」；`message-translation.md`「不直接建立两种 wire 映射，总是经 IR」；Architecture 可证伪判据「语义单源」「multi-part identity」「unknown item」。
- **primary_location**：`src/app/pipeline/delivery/formats/openai_responses.py` `ResponsesAssembler._close`
- **related_locations**：
  - `src/app/pipeline/translation_driver/responses.py` `from_openai_responses_response`
  - `src/app/pipeline/translation_driver/openai_responses.py` `response_blocks_from_item` / `blocks_from_item`
  - `src/app/pipeline/reply.py` `response_payload`
  - `src/app/pipeline/delivery_policy.py` `assembler_for`
- **证据**：
  1. 非流路径：`reply.response_payload` → `translators.translate_response` → `from_openai_responses_response` → `response_blocks_from_item` → `ContentBlock` → `to_anthropic_response`。这是 IR。
  2. 流路径：`assembler_for` 构造 `ResponsesAssembler`。`_close` 按 `draft.kind` 手写 Anthropic dict（`tool_use`／`thinking`／text／hosted pair），产出 `CompletedBlock`。全文件没有调用 `response_blocks_from_item` 或 `SemanticResponse`。
  3. 未知 item：assembler 在 `UNKNOWN` 上设 `StreamFailure`／`unknown_output_item`／`replayable=False`，注释并引用 Spec `REJECT`。非流对 `BlockKind.UNKNOWN` 只 `record(ITEM_NOT_CARRIED)` 然后 `continue`，正常 `stop_reason` 收尾。
  4. 多 content part：`_open` 把整个 `message` item 映成一个 `TEXT` draft，`_accumulate` 把所有 `output_text.delta` 拼进 `draft.text`。非流 `_block_from_content_part` 按 part 产多个 `ContentBlock`。这正是 Architecture 点名的「按 item 单 draft 合并」反例。
  5. tool arguments：流式 `decode_json(partial_json or "{}")`，失败得 `{"__raw": raw}`；非流 `_decoded_arguments` 保留无法解析的字符串。Spec 基础行为是解析失败即 conversion error。
  6. `ResponsesFramer` 与 `ResponsesAssembler` 同文件。模块头说自己是「Rendering completed blocks as OpenAI Responses SSE」——inbound 翻译混在 outbound framing 里。
- **为何是结构错误而不是漏测**：两套规则可以各自补 if，但迁移时「以 assembler 为准」或「以 translate_response 为准」会把另一侧的 reasoning／tool search／unknown／usage 一并带走。这不是文件名问题；Architecture 把「具体函数签名／是否按文件拆分」列为可局部调整，**把「非流与流式必须调用相同 block constructors」列为 B 的不可拆分核心**。
- **迁移时会破坏**：unknown item（一侧变红一侧仍 200）、block order／part cardinality、tool search 回译名字（两边都读 extras，但构造路径不同）、reasoning 只在 item-done 拼 summary 的那条路上。

### F-2 · blocker · 一个请求两个 lifecycle owner：driver 管到 headers，route 管 body replay

- **判据**：`D-ARCH=B` 核心 2「Single driver 是唯一 lifecycle 与 action owner」；Spec「application Anthropic pipeline 是唯一真实 upstream retry owner」；方案 C 因第二套 owner 被拒绝；`D-MIGRATION=M1` 不允许把 A 形双 owner 留作长期形态。
- **primary_location**：`src/app/server/routes/inference.py` `_reopen`（约 L941–L1014）
- **related_locations**：
  - `src/app/pipeline/driver.py` `ledger_for` 注释（约 L87–L93）
  - `src/app/pipeline/request.py` `retry_ledger`／`Attempt.deadline_at` 字段注释
  - `src/app/pipeline/delivery/stream.py` `ReplaySupport` + `stream_delivery`
  - `src/app/pipeline/direct_driver/base.py` `_prepare_and_send`／`_handle_failure`
- **证据**：
  1. `handle`／`_drive` 在 upstream **headers** 到达后返回 `HandledRequest`。其后 `stream_delivery` 在 route 里跑。
  2. body 撕裂时 `_reopen` 调 `replay_prepared`，再 `assembler_for`，再把新 iterator 交给 `stream_delivery`。driver 已不在栈上。
  3. `ledger_for` 原文：「delivery opens further attempts after a torn body, long after the driver that opened the first has returned」。`RequestContext.retry_ledger` 同样写了这句话。这不是推断，是模块自己的 owner 声明。
  4. 共享 `RetryLedger` 只共享预算，不共享编排。attempt 的打开、assembler 替换、rate-limiter `note_failure`、drain 拒绝，都在 `inference.py`。
  5. `EVENT_ATTEMPT_PREPARE` 只在 `prepared_payload is None` 时发。stream replay 带 prepared payload，跳过 prepare。这与 Spec「下一 attempt 重新 PRE_SEND 并重新转换」不是同一条路径——对 **post-header replay** 复用 payload 是对的（前缀不能接另一份对话），但它被实现成「driver 不管这条 attempt 序列」。
- **为何 blocker**：B 的五项核心写明不能拆掉 single driver 还自称 B。当前切缝是 **handler 编排 + driver 只做首跳**，接近被拒绝的方案 C 的弱形式（不是 route 调 Responses pipeline，而是 route 成为第二 driver）。M1 不允许把这当作过渡 adapter 永久留下。
- **迁移时会破坏**：retry／frontier（committed_count 仍在 delivery session，driver 看不见）、post-commit 禁止 full replay、合成续写与无痕重试的分界（`ContinuationSupport` 在 stream.py，不在 driver）。

### F-3 · major · 内部同时有三套（加一套僵尸）响应模型

- **判据**：B 核心 1「wire 只在 adapter／codec 边界」；Architecture「observer 消费事实，不重新解析 raw Responses events」；Spec unknown／empty content／incomplete 合同。
- **primary_location**：`src/app/pipeline/translation_driver/content.py` `ContentBlock` vs `src/app/pipeline/delivery/blocks.py` `CompletedBlock`
- **related_locations**：
  - `src/app/pipeline/response_observation.py` `ResponsesObserver`
  - `src/app/protocols/responses_anthropic.py` `convert_responses_response_to_anthropic`
  - `src/app/pipeline/request.py` `begin_attempt` 构造 `ResponsesObserver`
- **证据**：
  1. **Kernel 块**：`ContentBlock` + `BlockKind` + `ReasoningContent`。请求与非流响应使用。
  2. **Delivery 块**：`CompletedBlock.kind` 是 Anthropic 字符串，`payload` 是 Anthropic wire dict。`blocks.py` 写明「a block *is* an Anthropic content block」。这是方案 A 的 canonical Anthropic，不是协议中立 kernel。
  3. **Observation**：`ResponsesObserver` 再解析同一 SSE（stdlib `json.loads`，不用 assembler）。自述「never allowed to steer delivery」——正交是做到了；「消费 facts」没做到。usage 走 `convert_responses_usage`，与 delivery／reply 的 `anthropic_usage_from_responses` 包装不同。
  4. **僵尸转换器**：`convert_responses_response_to_anthropic` 生产路径零调用（只用其中 usage helper）。它仍：只接受 `status==completed`（`incomplete`／`max_tokens` 直接 fail）；未知 item `_fail`；空 content 塞一个空 text block（与现行 `to_anthropic_response` 的 `content: []` 相反）。`tests/unit/protocols/test_responses_anthropic_nonstream.py` 把它当活 oracle。`responses_reasoning_to_anthropic` 已是 per-item facade，不再聚合；但这个 JSON 转换器仍是第三套字段矩阵。
- **迁移时会破坏**：若「统一」时误把 protocols 转换器当单源，会恢复 empty-text 与拒绝 incomplete；若只搬文件不合并模型，reasoning cardinality 测试会在错误的类型上绿。

### F-4 · major · tool search／hosted search 的跨半场合同是 `context.extras` 旁路，不是 kernel

- **判据**：Spec 2026-08-25 tool search 翻译；Architecture ConversionFacts owner＝converter；未知／识别失败不得静默。
- **primary_location**：`src/app/pipeline/driver.py` `CLIENT_SEARCH_TOOL`／`HOSTED_WEB_SEARCH_EXPECTED` 写入 extras
- **related_locations**：
  - `src/app/pipeline/delivery_policy.py` `assembler_for` 读 extras
  - `src/app/pipeline/reply.py` `response_payload` 读 extras
  - `src/app/pipeline/translation_driver/semantic.py` `SemanticRequest.client_search_tool`
- **证据**：请求 writer 把名字放进 `SemanticRequest`，`handle` 立刻掏进 `context.extras`。响应两侧不能从 Responses item 恢复名字（`tool_search_call` 无名），所以都从 extras 再读一遍。`SemanticResponse` 没有这个字段。replay 若丢 extras 或合成路径没写 extras，流式会把 search 标 `DISCARDED`，非流会走 unknown→loss。合同成立靠约定，不靠类型。
- **迁移时会破坏**：拆 `HandledRequest`、改 extras、或让 assembler 不再经过 `driver.handle` 的写入点时，tool search 回译会静默消失（历史缺陷正是空 text block）。

### F-5 · major · 转换挂在 retry loop 外；attempt 修改的是 Responses wire

- **判据**：Architecture「每 attempt 转换：PRE_SEND 后每次从当前 semantic state 生成 wire；故意把 converter 移到 loop 外应变红」；Spec「retry 修改 payload 后下一 attempt 重新 PRE_SEND 并转换为 Responses wire」。
- **primary_location**：`src/app/pipeline/driver.py` `handle` 在 `_drive` 之前 `_translate_with_facts`
- **related_locations**：`src/app/pipeline/direct_driver/base.py` `_prepare_and_send`、`_handle_failure` 的 `ConnectionBoundInputIdRetry`
- **证据**：翻译一次，之后 `context.payload` 已是 Responses。driver 内重试发 `EVENT_ATTEMPT_PREPARE` 或直接改 Responses payload（connection-bound id 剥离）。没有 `SemanticRequest` 再 encode。stream `replay_prepared` 更是显式复用 prepared_payload——对 **已交付前缀后的 replay** 这是正确不变量，但它和「pre-commit 策略重试必须再走 IR」挤在同一个「不翻译」开关里。
- **不是**：要求 body replay 重跑翻译（那会把前缀接到另一份对话，inference 注释已测过）。缺的是 **两个 seam**：pre-commit 的 semantic re-encode，与 post-header 的 byte-exact replay。现在只有后者。

### F-6 · minor · delivery 选择与 reply 依赖 `driver.HandledRequest`，通用 request 依赖 Responses 观察器

- **判据**：分层／循环依赖风险；B 核心 3 protocol／transport 正交。
- **primary_location**：`src/app/pipeline/delivery_policy.py` import `HandledRequest`
- **related_locations**：`src/app/pipeline/reply.py`；`src/app/pipeline/request.py` import `ResponsesObserver`
- **证据**：HEAD **没有** import 环。`driver.py` 只在注释里提到 reply／delivery_policy。环的材料已经齐了：只要 driver 为了合成回复去 import reply，立刻成环。`RequestContext.begin_attempt` 在 `target_format is OPENAI_RESPONSES` 时 new `ResponsesObserver`——通用请求记录知道一种上游协议。
- **为何不是 major**：当前可运行，伤害是迁移摩擦。Architecture 允许把 DTO 挪出 driver 而不重开 `D-ARCH`。

### F-7 · minor · `delivery_policy`／`reply` 是浅模块，但接缝位置对

- **判据**：codebase-design deletion test；Architecture「assembler 按 upstream、framer 按 client」正交。
- **primary_location**：`src/app/pipeline/delivery_policy.py`
- **related_locations**：`src/app/pipeline/reply.py`
- **证据**：`assembler_for`／`framer_for` 按 dialect／inbound_format 分派，注释明确两条腿正交——**这是对的**。模块本身几乎没有行为，删掉复杂度回到 `inference.py`。`reply.blocks_from_anthropic` 把 Anthropic dict 再包成 `CompletedBlock`，是第三种「读回复」路径，只服务 console `Terminal`。
- **处置**：保留接缝，不要在里面长出第二套转换。

## 主观建议

- 不要把 `D-MIGRATION=M1` 读成「先把现在这些 adapter 再包一层 port」。M1 要的是 B 骨架，不是更多 adapter。
- `ResponsesObserver` 的「不转向 delivery」值得留。长期应改为投影 assembler／kernel 已发布的 facts。在 journal 存在之前，加新解析字段是负功。
- `SemanticRequest.tools: list[dict]` 仍是 content.py 曾经修过的那个洞（消息曾经是 Anthropic dict）。不是本轮 blocker，但是 kernel 未完成的信号。
- `delivery/blocks.py` 模块头仍写「首块前零 success headers」。已被 2026-08-22 用户裁决覆盖。注释错误，不单独开 finding。

## 三分处置

### 必须现在修的结构错误

1. **响应转换单源**（F-1）：`ResponsesAssembler` 在 `output_item.done` 上只做 SSE grammar／draft 生命周期，闭合时调用与非流相同的 `response_blocks_from_item` → `ContentBlock`，再投影为 `CompletedBlock`。未知 item、多 part、tool args、hosted search、reasoning 只许有一份规则。
2. **attempt 序列单 owner**（F-2）：body replay／hand-over 的「要不要再开 attempt」是 driver（或 driver 拥有的 port）的 action。`inference.py` 只绑 ASGI envelope。共享 `RetryLedger` 不够。
3. **退休僵尸 oracle**（F-3 的 protocols 转换器）：`convert_responses_response_to_anthropic` 退出生产语义。usage helper 可留在一处。活测试不得再把它当 Messages↔Responses 的行为源。

### 可局部保留的迁移形态

这些不是 B，但 **暂时**当 adapter 可以，必须有退出条件。注意：用户选的是 M1，所以它们是「搬家时别拆」的形态，不是授权的长期双轨。

| 形态 | 退出条件 |
|---|---|
| `SemanticRequest` 请求 IR＋registry 单跳 Anthropic↔Responses | 已接近目标；补齐 tools 的 typed blocks 后留下 |
| `reasoning_bridge`／`reasoning_carrier` | 已是单源；assembler 改为走它（流式 thinking 已调用 `read_responses_reasoning`）即可 |
| `FINISHED_STOP_REASONS`／`INCOMPLETE_REASONS` 由 responses.py 出口 | 已是正确方向；terminal 映射应跟过来，而不是再抄一份 |
| `delivery_policy` 的 assembler／framer 分派 | 抽出 `HandledRequest` 后保留为无逻辑表 |
| `context.extras` 里的 search 名字 | 直到 `ConversionFacts`／`SemanticResponse` 带上同名字段；退出＝extras 键删除 |
| `ResponsesObserver` 旁路解析 | 直到 Terminal／kernel 能提供 usage／item 摘要；退出＝observer 不再 `loads` SSE |

### 暂时不值得动的代码

- `delivery/blocks.py` 的 `BlockBuffer`／`DeliverySession`／`buffer_cap_bytes`（交付机制，不是转换）
- `delivery/stream.py` 的 ping／idle／commit sequencer 机械部分（把 **谁调用 reopen** 上收即可，不要重写 buffer）
- `openai_responses_passthrough.py` 同协议直通（`carries_upstream_natively`；Spec 允许 direct Messages／direct Responses 不经 IR）
- Chat Completions outbound translator（本 bridge 禁止 CC 作中间表示；它是另一条产品腿，registry 注释已限制 inbound）
- `fix_anthropic_request`／thinking layout hooks（人写 reshape；发生在翻译前是对的）
- `tool_search.py` 识别启发式本身（产品合同；先保证单 owner 再改启发式）
- `direct_driver/openai_responses.py`（薄 endpoint adapter，51 行，deletion test 通过）

## 推荐目标目录／接口

目标仍是 B，但 **seam 放在已有 `translation_driver` 上加深**，不要再引入第四套 `semantic_kernel` 包（deletion test：新包会变成 pass-through）。人写 `message-translation.md` 已经把这个包定为 IR 位置。

```
src/app/pipeline/
  translation_driver/          # 唯一语义 kernel
    semantic.py                # SemanticRequest, SemanticResponse, Conversion, TranslationRefused
    content.py                 # ContentBlock, BlockKind, ReasoningContent
    anthropic_messages.py      # inbound/outbound Anthropic request + block render
    openai_responses.py        # inbound/outbound Responses request + item constructors
    responses.py               # JSON 响应 codec：items → SemanticResponse → Anthropic/Responses body
    reasoning_bridge.py
    reasoning_carrier.py
    tool_search.py / tool_choice.py / reasoning.py
    registry.py
  delivery/
    assembling.py              # BlockAssembler protocol；CompletedBlock 只是 delivery unit
    formats/openai_responses_grammar.py   # SSE event → 打开/关闭哪个 item（无字段映射）
    formats/openai_responses_framer.py    # CompletedBlock → 客户端 Responses SSE（现 ResponsesFramer）
    formats/anthropic_messages.py
    stream.py                  # buffer、sink、frontier；reopen 是注入的 port
    blocks.py                  # 保留
  handled.py                   # HandledRequest；driver/delivery_policy/reply 都依赖它，切断环材
  driver.py                    # 唯一 attempt owner：含 body replay 决策
  delivery_policy.py           # 纯分派
  reply.py                     # 非流：registry.translate_response；Terminal 从 SemanticResponse 投影
  response_observation.py      # 从 SemanticResponse/Terminal 投影；禁止第二份 SSE parser
```

**外部 seam（调用方与测试共用，少量入口）：**

```python
class ResponseConversionContext:
    client_search_tool: str
    hosted_web_search_expected: bool
    hand_over_stop_reasons: frozenset[str]

def read_responses_output(
    items: Sequence[Mapping[str, Any]],
    *,
    ctx: ResponseConversionContext,
) -> SemanticResponse:
    """JSON 与 assembler 在 item-done 时共用。未知 item 在这里 REJECT，不在调用方。"""

class ResponsesGrammar:
    """只懂 event 名与 output_index。item 闭合时交出 raw item dict，不产 Anthropic dict。"""
    def push(self, event: SseEvent) -> tuple[Mapping[str, Any], ...]: ...

class ResponsesAssembler:
    def push(self, event: SseEvent) -> tuple[CompletedBlock, ...]:
        # grammar.push → read_responses_output([item], ctx) → ContentBlock → CompletedBlock
        ...
```

**不该出现的接口：**

- `CompletedBlock.payload` 继续充当「唯一真相」（它只是 Anthropic 下游 unit）
- `context.extras["client_search_tool"]` 作为稳定合同
- `convert_responses_response_to_anthropic` 作为生产或新测试 oracle
- assembler 与 `from_openai_responses_response` 各写一份 hosted-search pair
- `inference.py` 持有 `ReplaySupport.reopen`

依赖类别（Deepening）：转换是 in-process，应合并进 kernel 直接测；transport 才是 remote。不要为 JSON vs SSE 再做 port——那不是两个 adapter，是同一 codec 的两个入口。

## 实施顺序

先做能让错误形状变红的 kernel 测试，再收语义，最后收 owner。不要先搬 retry，也不要先新建第四个包。

0. **门（代码前）**：承认 `D-ARCH=B` 的 typed owners 与人写可变 `ClientRequest` 并存。本顺序按「加深已有 `translation_driver` IR，不重开可变上下文」落地；若要把 RequestFacts 所有权做进 B，那是另一次文档裁决，不插在下面切片里。
1. **先写反例，再改生产**（X-PARITY-UNKNOWN／MULTIPART／TOOLARGS／REASONING-CARD／SEARCH-NAME）。测 `read_responses_output` 这一层，不要测 assembler 私有 draft。没有这组测试，S2 的绿没有分辨力。
2. **S2 响应单源（F-1，必须先做）**：`output_item.done` 只交出 raw item；`from_openai_responses_response` 与 assembler 都走 `read_responses_output` → `ContentBlock` → 下游 unit。未知 item、多 part、tool args、hosted search、reasoning 只留一份。这是唯一能同时关掉 F-1 并降低 F-3／F-4 迁移杀伤的切片。
3. **S3 把 search 合同写进 `SemanticResponse`／`ConversionFacts`（F-4）**：与 S2 同一波或紧随其后。退出条件是删除 `context.extras` 那两个键。不要单独先「整理 extras」。
4. **S4 退休僵尸 oracle（F-3 的 `convert_responses_response_to_anthropic`）**：S2 成为行为源之后立刻做。usage helper 搬到唯一 usage 模块；活测试改挂 kernel。可与 S3 并行。
5. **S5 抽出 `handled.py`（F-6）**：无行为变更。为 S6 切断环材。不要顺便改 dialect 表。
6. **S6 driver 收回 reopen（F-2）**：`inference.py` 只绑 ASGI。`ReplaySupport.reopen` 由 driver 注入。buffer／ping／commit 机械留在 `stream.py`。必须在 S2 之后：两套转换器还在时搬 retry，会把未知 item 分歧复制进第二条 attempt 序列。
7. **S7 拆开两个转换 seam（F-5）**：pre-commit 策略重试走 IR 再 encode；post-header replay 仍 byte-exact `prepared_payload`。两个入口，禁止一个「不翻译」开关伺候两种寿命。
8. **S8 observer 改为投影（F-3 余下）**：不再 `loads` SSE。可晚于 S6。在 journal／Terminal 能提供 item 摘要之前不要加新解析字段。
9. **S9 可选文件拆分（F-7）**：grammar／framer 分文件。Architecture 允许局部调整，不阻断 S2–S7。

**禁止插队：** 重写 `BlockBuffer`、打开 Anthropic 直通、改 tool_search 启发式、为 JSON vs SSE 加 port、新建 `semantic_kernel` 包。

## 反例测试

现有绿不能证明形状。下列注入必须变红；正样本保持绿。接口是 kernel，不是 assembler 私有状态。

| ID | 注入 | 必须红的原因 | 正样本仍绿 |
|---|---|---|---|
| X-PARITY-UNKNOWN | 同一 fixture：JSON body 与 chunked SSE 含 `custom_tool_call` | 非流若只记 loss 仍 200／`end_turn`，流式若 501／无 terminal，形状未统一 | 合法 `function_call` 两边同 blocks |
| X-PARITY-MULTIPART | 一个 `message` item 两个 `output_text` parts | 流式合成一块则红（Architecture multi-part identity） | 单 part 文本 |
| X-PARITY-TOOLARGS | `function_call` arguments 非 JSON | 一侧 `__raw`、一侧 raw string、一侧静默 `{}` 则红；应对齐 Spec conversion error | 合法 JSON arguments |
| X-REASONING-CARD | 两个 reasoning items，各自 summary＋encrypted | 聚合／last-ciphertext-wins 红；item 内多 summary part 拼接仍绿 | 单 item encrypted-only → `thinking=""`＋carrier |
| X-SEARCH-NAME | 请求译出 client search，响应 `tool_search_call` 无名 | extras 丢失或 assembler DISCARD 导致空 text 红 | 无 search 声明时 unknown／discard 显式 |
| X-OWNER-REPLAY | 测替身：policy／assembler／framer 自己调 transport | 架构检查红 | driver 接受 `RetryAttempt` 才 reopen |
| X-CONV-LOOP | 两次 attempt，PRE_SEND 改 thinking；converter 在 loop 外 | 第二次 wire 仍是第一次语义则红 | post-header replay 仍 byte-exact prepared_payload |
| X-ZOMBIE | 新测试 import `convert_responses_response_to_anthropic` 当 oracle | 该入口应不存在或标 deprecated 失败 | usage helper 单测可留在唯一 usage 模块 |
| X-OBSERVER | observer 抛异常 | delivery 仍提交已完成块（现有 no-throw 应保持） | 日志可缺失 |
| X-FRONTIER | assembler complete 但 sink 未 accepted 时标 committed | frontier 提前红 | headers 已在首次 200 提交（2026-08-22），不要用旧 delayed-start 判据 |

**不要写的测试：** 模块是否存在、`ResponsesAssembler` 类名、16 MiB 专属路径、Chat Completions 是否注册 outbound。

## 搜索面

**读过的判据**

- `.dev/docs/anthropic-responses-bridge/{README,spec,architecture,research,implementation}.md`（spec／architecture 承重条款；implementation 不当判据）
- `docs/.human-controlled/{message-translation,request-pipeline,module-org,client-side-block-delivery,upstream-retry-and-continuation,message-format-reshape}.md`
- 并行会话 `fd74ca3f` 用户三句原话（local session store）
- 未把 `TODO_CURRENT.md`、sub2api 分析、并行工作树当判据

**读过的 HEAD 实现**

- `translation_driver/{registry,semantic,content,openai_responses,responses,anthropic_messages}.py`（结构＋响应 codec 全文；openai_responses 的 item 映射）
- `driver.py` handle／translate／replay／ledger
- `reply.py`、`delivery_policy.py` 全文
- `delivery/formats/openai_responses.py` assembler／framer／terminal／usage
- `delivery/{assembling,blocks,stream}.py` 接口与 replay 类型
- `response_observation.py` 公开合同与 observer
- `request.py` Attempt／extras／observer 构造
- `direct_driver/base.py` prepare／retry
- `server/routes/inference.py` stream `_reopen`／`response_payload`
- `protocols/responses_anthropic.py` 僵尸转换器
- `anthropic/thinking/responses_reasoning.py` 确认已是 per-item facade

**命令（只读）**

- `git rev-parse`／`git status`／`git ls-tree HEAD`／`git show HEAD:…`／`git grep HEAD`
- 未跑 pytest／ruff／pyright；未做失效变异。绿测试分辨力 = `unverified`
- 未读工作树脏文件正文；未跟踪的 `translation_driver/usage.py` 不在被检对象

**未覆盖**

- Chat Completions assembler 内部、Gemini、embeddings
- History SQLite schema、hooks 全表
- 真实 Copilot canary
- 并行会话未提交 diff（明确排除）
- `acceptance.md` 逐条 REQ（本轮是形状审查不是验收）

**停止条件**：四条承重问题均已对照：shared kernel（否，仅请求侧）、stream／non-stream parity（结构上否，且未知 item／multi-part 已有源码级分歧）、single owner（否）、transport／delivery 正交（分派正交，assembler 内容不正交）。

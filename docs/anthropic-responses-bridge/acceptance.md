# Anthropic Messages ↔ OpenAI Responses bridge 独立验收规范

> Current authority：本文件当前状态是 `FINALIZED_ACCEPTANCE_ORACLE`，候选产品及完整 bridge 为 `UNVERIFIED`。2026-08-08 最终输入为 Spec `4c9beed133b80e1c03d46db50b25bcbb43df505c29174a68fab566fc671e1f8f` 与 Architecture `746adc7aaa14e3c8775fbabad8d316d5d88cc83ec793956c3e966f42702bd5e2`。Current Architecture 已与 Spec 的“双格式 carrier”方向一致，但仍是非规范提案，不产生 Acceptance expected。下文出现的旧 hash、`upstream-only`、`READY_FOR_FINAL_REVIEW`、“待复评”或 R2～R7 verdict 只属于历史处置记录，均被本段 current 声明覆盖，不是 current gate。

## 状态与判定

- **仓库根目录**：`/home/xp/src/ghc-api-proxy-py`。
- **历史修订锚点**：本轮 oracle 内容对账曾在 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 执行。该 commit 不是 current main 状态；current 实现见 [implementation.md](implementation.md)。
- **行为 oracle**：`spec.md`，本轮在 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 现场以 `sha256sum` 与 Python `hashlib.sha256` 交叉复核的 current SHA-256 均为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。该内容保留 D1～D3、route precedence、strict compatibility、server-tool no-revive、usage、post-commit partial failure与普通 per-request aggregate＋global reservation／backpressure，并以 2026-08-07 用户最新重裁覆盖旧 D4及 2026-08-06 upstream-only／全 malformed byte-exact 范围：本项目主 v1 是默认 producer，consumer 兼容固定 `copilot-api-js` v1 合法主路径，不要求所有 malformed 边界逐字节等同 Node；一 Responses reasoning item 一 Anthropic thinking block、普通模式 encrypted-only no-loss、unknown／foreign／malformed 最小止血保持不变。以下 required gate 只能按该内容版本与本文件 `POLICY-MANIFEST-v1` 给出 expected。Spec 内容 hash 改变后，本规范必须先重做 route／request／response／buffering／retry／lifecycle／limits 七域逐项 policy 对账，不能沿用旧 verdict或只替换 hash。
- **架构参考而非行为 oracle**：`architecture.md`，本轮现场以 `sha256sum` 复核的 current SHA-256 为 `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d`。该文件仍明确标记为“非规范架构提案，尚未获用户接受”：`D-ARCH` 只推荐目标内部架构，`D-MIGRATION` 只推荐迁移节奏，两者均不产生、覆盖或扩张 Acceptance expected。其完整 block、capacity、unknown endpoint、post-commit failure、delivery与History承载仍可帮助定位非 carrier 接缝；但其 `ADR-BRIDGE-06` reasoning carrier 仍记录旧 upstream-only producer 口径，已被 current Spec 的双格式重裁覆盖，不能进入 REQ-05／NS-03 expected，也不能据此判双格式 Acceptance 为不一致。Architecture 的 typed semantic kernel、`PolicyOutcome`、History receipt owner、adapter 退出条件与 route 启用门同样只可帮助定位内部接缝或未来实施门。
- **评审输入**：首轮 `reports/review-bridge-acceptance.md`，读取时 SHA-256 为 `b619e7ce5636ec1bf8010099047fe2559d60efbfe75b31918a4dfb5842a8f32d`；独立复评 R2 `reports/260806-review-bridge-acceptance-r2.md`，读取时 SHA-256 为 `b9c6bee01e7707365fd0e6e2872c15851b4617f5823f2f5a0ab432a03956b18f`；独立复评 R3 `reports/260806-review-bridge-acceptance-r3.md`，读取时 SHA-256 为 `a32ca0fad8af900e977f272819779752add9b322b38d8059a9a548c045799f50`；独立最终复评 R4 `reports/260806-review-bridge-acceptance-r4.md`，读取时 SHA-256 为 `6df6575996e00f669df515959de1061e37bdf5070ccc28f9dd3aca7f23b0aa6e`；独立最终复评 R5 `reports/260806-review-bridge-acceptance-r5.md`，读取时 SHA-256 为 `d66958bb95beba1e1a74d043fc31e14c40ba948a24a8ce06a2eea8967ba59716`；独立最终定向复评 R6 `reports/260806-review-bridge-acceptance-r6.md`，读取时 SHA-256 为 `2e1b11598470fbf3342582e854571901e2b624b112dac6ef5501222c885ce22b`；Architecture 用户裁决矩阵独立终审 `reports/260807-review-architecture-decision-matrix.md`，读取时 SHA-256 为 `6922a93038b9e80677c8d6482c7236ec729facff3d8b3b69d53397f193d17a93`；Acceptance 独立终审 R7 `reports/260807-review-bridge-acceptance-r7.md`，读取时 SHA-256 为 `9ab0fb3c35d1506a31f3a4fb789d6b03e02ebd27a6f2e1f880f2dc7148c988be`，结论为 blocker 0、major 0；正式文档 merged-state 最终评审 R2 `reports/260807-review-docs-merged-r2.md`，读取时 SHA-256 为 `b62711635cdcfd34adcf406073bae9ef2f156e4378b1a999920b7e0e0dc7c2d9`；carrier 双格式定向评审 `reports/260807-review-spec-carrier-dual-format.md`，本轮现场以 `sha256sum` 复核的 SHA-256 为 `1d51e1a8dde27493503adb9701544ef8e35b75404420a4516732d06074addd05`，结论为 blocker 0、major 0、minor 0，并明确只放行 current Spec 的项目主 v1＋upstream v1 compatibility、识别顺序、最小止血与一 item一 block／no-loss合同，不替代实现证据；空 reasoning 语义独立裁决 `reports/260807-arbitrate-empty-reasoning.md`，本轮以 `sha256sum` 与 Python `hashlib.sha256` 交叉复核的 SHA-256 均为 `8f12e0703a925a511fad3188f54a89a7a1d6056096fde05520a1c21cb5e6c568`，唯一裁决为 `summary=[]` 且 `encrypted_content` absent／empty 时仍生成恰好一个 `thinking=""`＋项目 bare marker block，但不得恢复或伪造 `encrypted_content`。R6／R7与双 carrier 定向复评只保留为旧 Acceptance bytes 的历史 verdict；本次 Acceptance bytes 必须经过新的独立定向复评，旧 0／0不得沿用。
- **未决政策处理**：Spec “仍需用户选择的低概率扩展”当前均已有确定基础行为：malformed tool arguments与multimodal tool result固定`REJECT`；foreign／unsigned thinking按固定upstream兼容合同记录`DEGRADE`并从Responses wire丢弃，不恢复opaque signature；公开model suffix不存在。Required gate只验这些最小止血行为，不为扩展形态建立专门能力gate。将来若启用任何扩展而尚无新的 Spec 内容版本，对应扩展项只能记为`UNVERIFIED`，不得由候选实现、自带测试或本规范临时创造expected，也不得据此宣称整体符合扩展合同。
- **本规范状态**：**`FINALIZED_ACCEPTANCE_ORACLE`。** ⚠️ **2026-08-24 起这个字面量只读作「本轮验收对账已完成」，不表示本文封版**——用户当日裁定全面废除 spec 冻结，本文与它所对账的 [spec.md](spec.md) 同为活文档，Spec 条款修订时**本文必须同改**，否则 oracle 会静默落后于它声称在验收的行为。**字面量本身未改名**：`../service-cutover/plan.md` 与 `readiness.md` 按「状态字面量 @ 内容哈希」硬引用了它，改名属机制变更，待用户裁决（那两处的哈希绑定已于 `1197da7` 失配，详见 `../service-cutover/plan.md` 权威边界条下的说明）。 本次仅按 current Spec `5e362822…` 与空 reasoning 独立裁决澄清 NS-03：`summary=[]` 且 `encrypted_content` absent／empty 必须保留一 item一 block cardinality，生成恰好一个 `thinking=""`＋项目 bare marker block；bare marker 不承载可恢复 opaque payload，consumer不得添加或伪造`encrypted_content`；non-empty encrypted-only仍必须通过payload carrier value-exact no-loss。Spec、其他policy域与其他gate expected均未改。空 reasoning 定向独立复评 `reports/260807-review-acceptance-empty-reasoning.md` 绑定修订候选 SHA-256 `a4b9e31fd1d237ca8038573320809305e0ac567eb2d56d5c967716cc8cdbfac8`，报告 SHA-256 `5d9ad16e371f14544dfe2d5b7e84070cf8e851aa73343b6893d344b75cd1f623`，结论为0 blocker／0 major／0 minor，故本规范恢复最终标记。候选产品及完整bridge仍为`UNVERIFIED`；基础integration的`PASS`、Spec carrier评审0／0、Acceptance文档复评0／0或旧Acceptance R6／R7 verdict均不等于产品通过。正确样本失败、缺陷注入未按目标原因变红，或出现已证实的丢失／重复／重排属于`BLOCKED`；必需证据尚未取得、capture corpus过期或政策仍未冻结属于`UNVERIFIED`，不得误报成实现缺陷。只有全部已决required gate通过、每个缺陷注入控制均以预期原因失败、确定性live canary通过、所依赖capture corpus provenance有效且本地fault injection通过，基础合同verdict才能升级为`PASS`。

## 用户可观察合同

本 bridge 的外部合同不是“内部 converter 返回了某个对象”，而是 Anthropic 客户端经 `POST /v1/messages` 或 Anthropic 兼容 transport 发出请求后，无须知道上游实际使用 OpenAI Responses HTTP 或 WebSocket，即可观察到合法且语义等价的 Anthropic Messages 非流响应或 SSE 流。请求生命周期只能有一个 owner；approval、hooks、retry、History 与 tokenization 必须继续表现为同一次 Anthropic 请求，而不是桥接后产生第二个平行请求。

必须保持以下不变量：

- 入站与下游始终是 Anthropic 语义；Responses wire 只存在于 attempt transport 边界。
- 非流与流式路径表达同一组 content blocks、相同顺序、相同 tool/reasoning/signature 语义、相同 stop reason 与归一化 usage。
- 流式下游的最小提交单元是一个完整、可独立解析、已闭合的 Anthropic content block；在该 block 完成前不得泄漏 token、delta 或 event。
- 已提交前缀永不重复、永不丢失、永不重排。透明 retry 只允许发生在首个 block commit 前；commit 后不得从头重放。
- client cancellation、slow consumer、global memory pressure、transport close、clean truncation、upstream error 与 converter error 都必须有确定且可审计的终态，不能假装成功。
- HTTP 与 WebSocket upstream transport 只能改变传输方式，不能改变 Anthropic 请求、响应、History、hooks、approval、retry 或 tokenization 的含义。
- 不支持或无法无损表达的字段必须按已声明策略显式降级或报错；禁止无记录地静默丢弃。

## `POLICY-MANIFEST-v1`：current Spec 逐节对账

本 manifest 与“状态与判定”中的 Spec／Architecture SHA-256 来自本轮 current 输入。本轮先读取 current Spec 的规范章节与双向字段矩阵，再逐域核对全部 required gate 的 expected、错误路径和边界，最后只用 current Architecture 查找承载接缝。七域均已完成内容对账：route、buffering、retry、lifecycle、limits 全域 expected 不变；request、response 仅 carrier producer ownership、合法 compatibility 范围与 malformed expected 改为双格式合同，其他 expected 不变。Architecture `c6088a…` 的 carrier 段落仍是旧 upstream-only口径，该已知陈旧参考被明确排除，不能覆盖 current Spec或生成 expected；它的其他承载内容仍不产生第二套政策。Carrier双格式Spec定向评审为0 blocker／0 major；空 reasoning 定向独立复评 `reports/260807-review-acceptance-empty-reasoning.md` 为0 blocker／0 major／0 minor并覆盖本次NS-03修订bytes，故本规范恢复`FINALIZED_ACCEPTANCE_ORACLE`。任一manifest行所引Spec语义或Spec内容hash改变时，该行及依赖gate立即回到`UNVERIFIED`，必须重做内容对账，不得仅刷新数字。

| Policy 域 | current Spec 规范来源 | 本规范 gate／expected 对账 | 结论 |
|---|---|---|---|
| route | “Route selection 与 model capability 契约”“冻结的 route precedence”“Route 真值表”“Compatibility 契约” | `REQ-01`、`TR-HTTP`、`TR-WS`、`TR-PARITY`固定 resolved-model lookup、显式 override优先且不可用不fall through、双支持默认Messages、Responses-only选Responses、unknown fail closed、protocol leg与physical transport正交；Architecture的ADR-BRIDGE-04与ADR-BRIDGE-06只承载这些Spec已决约束，`D-ARCH`／`D-MIGRATION`不改变route expected | 一致 |
| request | “Request conversion 契约”“双向字段处置矩阵”“Reasoning 与 signature 契约” | `REQ-02`～`REQ-06`逐项冻结system／envelope、原序、tool identity与no-revive、approval后重新prepare及每attempt `PRE_SEND`后转换；REQ-05固定项目主v1为默认producer，consumer按first-match顺序接受项目主v1、项目bare marker、`copilot-api-js` v1合法主路径／bare／legacy，并对project unknown／project malformed／upstream malformed／foreign执行稳定最小止血；不要求全malformed Node byte-exact。Architecture `c6088a…` 的旧upstream-only carrier段落不产生expected | 一致；carrier expected已按current Spec更新，其余request expected不变 |
| response | “Response conversion 契约”“Non-stream contract”“SSE／WS envelope 契约”“Usage 契约”“Error 契约”“Header 契约” | `NS-01`～`NS-05`、`STR-01`、`STR-04`～`STR-05`固定content／reasoning一对一、tool优先stop reason、terminal与error互斥、usage算式、Anthropic error／header envelope及stream／nonstream等价；reasoning响应新增项目主v1 producer exact vector与value-exact echo，仍保持一item一block、普通模式encrypted-only no-loss、显式strip有意去除与authoritative `.done`；Architecture旧carrier文字被排除 | 一致；carrier producer expected已按current Spec更新，其余response expected不变 |
| buffering | “Downstream Anthropic SSE”“Block-level buffering 与 commit 契约”“Ordering、no duplication、no loss 契约” | `STR-02`～`STR-03`、`REL-03B`与`CAL-04`固定完整Anthropic content block为最小提交单元、首个完整block前零headers／`message_start`／body event、首批同batch、连续完成前缀、sink uncertainty及零content完整terminal batch；Architecture的ADR-BRIDGE-02、03、06与delivery chain只提供内部承载和观测点，不把Python yield、TCP packet、durable ack或推荐sink调用粒度变成产品保证 | 一致 |
| retry | “Retry ownership 与 delivery semantics”“唯一 owner”“推荐 retry 边界” | `REL-01`～`REL-04`固定application pipeline唯一retry owner、SDK retry关闭、pre-commit可按预算重试、attempt-local state全量reset、post-commit禁止full replay且默认partial failure、真实exchange数等于attempts；Architecture的ADR-BRIDGE-05只承载该已决frontier，`PolicyOutcome`与未来continuation接缝不产生expected | 一致 |
| lifecycle | “Approval、hooks、History 与 tokenization 契约”“Shutdown、cancel、backpressure 与 limits 契约”中的Shutdown／Client cancel | `LIFE-01`～`LIFE-04`、`REQ-06`、`REL-05`固定single RequestContext／History／approval／finalize、Anthropic hook语义、cancel／shutdown不retry、资源关闭与token calibration；Architecture的ADR-BRIDGE-06、typed journal、History projection与独立durability receipt仅作承载参考，未提升为行为expected | 一致 |
| limits | “Shutdown、cancel、backpressure 与 limits 契约”中的Backpressure／一般memory-only政策／Limits及“非功能要求” | `REL-06`固定普通per-request aggregate＋global resident reservation、有限queue、charge-before-read、两级可观测计账、capacity／deadline／cancel终态与拒绝新admission最小止血；Architecture的ADR-BRIDGE-03与容量章节和Spec一致，但不新增16 MiB专门gate、single-block阈值、spill、live forwarding、victim policy或其他未裁决expected | 一致 |

Manifest 绑定的是上述政策语义与 gate 映射，不是文件名清单或“已阅读”声明。逐项复核结果为：ADR-BRIDGE-02与response／buffering一致，ADR-BRIDGE-03与limits一致，ADR-BRIDGE-04与route一致，ADR-BRIDGE-05与retry一致；ADR-BRIDGE-06的block／route／delivery／History承载仍可作接缝参考，但其旧upstream-only reasoning carrier已被current Spec双格式合同覆盖，不参与expected。Architecture中与Spec一致的delayed start、continuous-prefix、sink outcome只帮助选择`AUTO-HTTP`／`AUTO-SOCKET`观测点；`D-ARCH`、`D-MIGRATION`、推荐方案、内部类型、History持久化时点或未来独立ADR即使变化，也不能自动改写本manifest的expected。

## Gate 执行规则

### 双向控制

每个 gate 都必须在同一测试入口上执行两种控制：

- **正确样本控制**：已知合法输入走真实生产入口，断言完整用户可观察结果为绿。不得只调用测试 helper、私有 converter 或 fake-only shortcut。
- **缺陷注入控制**：只注入该 gate 要捕获的一个目标缺陷，确认同一断言必然变红，并核对失败原因确实来自目标不变量，而不是 fixture 解析失败、未接线或另一条旁路断言。注入必须使用冻结的 exact patch、可替换策略对象或测试专用 fault injector；恢复后复跑正确样本。

缺陷注入控制是 gate 的组成部分，不是可选 mutation campaign。正确样本不绿属于 false-red；注入后仍绿属于 false-green；两者都阻断验收。

### 判据独立性

- wire 层使用完整对象 equality、字段明确缺失断言和 item 顺序断言；不得只检查“包含某字段”。
- 流层除逐 event 断言外，必须由真实 Anthropic Python SDK streaming consumer 或与产品 parser 不同源的严格 consumer 重新消费，并比较最终累积 message。
- stream/nonstream 等价比较先归一化 transport-only 字段，再比较 content blocks、tool input、thinking/signature、stop reason 与 usage；不得由同一个产品 serializer 同时生成 expected 与 actual。
- no-dup/no-loss/order 以输入语义 item 的唯一 marker 与有序序列为 oracle。每个 marker 必须在最终 Anthropic 累积结果中恰好出现一次，且顺序精确相等；只比较拼接字符串长度不够。
- 所有自动化 gate 都要记录候选 commit、测试命令、退出码和失败注入的目标。未执行项标记为 `UNVERIFIED`，不得折算为通过。
- policy-dependent expected 必须在测试 manifest 中记录上述 Spec SHA-256、对应章节／矩阵行和 policy 配置。Manifest 与执行时 Spec hash 不同则该 gate 为 `UNVERIFIED`，不能自动挑选另一 expected 继续跑绿。

### 自动化与证据标记

- `AUTO-UNIT`：纯转换、状态机或 property-based 测试，可在无网络环境自动执行。
- `AUTO-COMPONENT`：真实 pipeline owner、fake upstream、History、hooks、approval、tokenization 的组件测试。
- `AUTO-HTTP`：真实 ASGI HTTP route 与真实字节流消费测试。
- `AUTO-WS`：真实本地 WebSocket client/server、有限 queue 与 close code 测试。
- `AUTO-SOCKET`：通过 loopback socket 注入分帧、RST、half-close、慢读与取消；不能用直接调用 async generator 代替真实 transport flow control。
- `LIVE-CANARY`：每轮可确定调用的真 OpenAI Responses／Copilot upstream 正常请求和上游明确提供的官方触发器；不得要求托管上游在本轮偶发 5xx、truncation、特定 close code 或 queue pressure。
- `CAPTURE-CORPUS`：真实历史事件或上游官方 fixture 经 SDK 前 raw recorder 捕获、脱敏、版本化后的 corpus。它提供不可控异常的协议样本，但不冒充本轮 live 事件。
- `LOCAL-FAULT`：在 loopback HTTP／WS server、TCP proxy 或 sink fault injector 中确定性制造 truncation、RST、partial write、close 和 backpressure，并验证产品错误路径。它证明本地处理机制，不冒充真实 upstream 异常 provenance。

## 请求与路由 gate

### REQ-01 endpoint capability 与单一生命周期

- **正确样本**：按绑定 Spec 的 route 真值表覆盖 Responses-only、Messages-only、双支持无 override、双支持显式 Responses override、能力未知和 transport 不可用。Responses-only 只产生一次 Responses upstream attempt；Messages-only 与双支持无 override 只产生一次 Messages attempt；unknown／unsupported／selected transport unavailable 在网络调用前返回可审计 Anthropic error且不 fall through。每种情况只有一个 request id、一条 in-flight History 和连续 attempt 序列。
- **缺陷注入控制**：让 endpoint selector 按模型名称猜测，或让 Anthropic route 借用原生 OpenAI route pipeline。gate 必须因错误 endpoint、重复 approval／History、两个 request id 或 attempt 与实际调用数不一致而红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`；HTTP／WS capability的真实声明由`LIVE-CANARY`与版本化`CAPTURE-CORPUS`校准。
- **通过判据**：用户看到的 Anthropic 成功／错误合同不依赖选中的 upstream transport，且真实底层请求数严格等于 context attempts。

### REQ-02 envelope、system 与 last-mile wire

- **正确样本**：覆盖 string system、多 system text blocks、空 system、`max_tokens`、显式 `stream` true／false、temperature、top_p、metadata user id、resolved model 与未知顶层字段。断言 Responses wire 使用 `instructions`、`input`、`max_output_tokens`，不出现 Chat `messages`；`cache_control`／非 allowlist metadata 按冻结矩阵 `DEGRADE` 并记录精确路径，`top_k`／`stop_sequences`／`context_management`／未知顶层字段按冻结矩阵 `REJECT`，不得由实现选择 permissive policy。
- **缺陷注入控制**：改成 Chat Completions 形状、漏掉第二个 system block、保留 `top_k`／`stop_sequences`、把原始 model 而非 resolved model 发出，或 serializer 输出 `None` 字段。完整 wire equality 必须变红。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：logical request 与最终 outbound wire 都符合 Responses schema，且 last-mile rewrite 后重新断言实际发送值。

### REQ-03 content blocks、multimodal 与原序

- **正确样本**：使用带唯一 marker 的交错序列，覆盖 user text、base64 image、URL image、assistant text、tool_use、tool_result、error tool_result、empty text、document／audio／video／unknown block。至少包含 `[tool_use, text]`、`[text, tool_result]` 与多次交错，断言转换后的 item 顺序与用户 turn 内原序一致；不可表达 block 按冻结矩阵 `REJECT`，只有矩阵明确列为 `DEGRADE` 的字段才可继续。
- **缺陷注入控制**：把所有 text 聚合到 tools 前、把 tool_result 推到 user message 前、静默丢掉 image／unknown block，或把空 item 伪造成非空内容。序列与 degradation oracle 必须变红。
- **方式**：`AUTO-UNIT`，并用随机合法 block 序列做 property-based permutation 测试。
- **通过判据**：marker 恰好一次且原序不变；映射策略对每种 block 都有可观测结果。

### REQ-04 tool declarations、choice、name 与 call identity

- **正确样本**：覆盖普通 function tool、web search builtin、不支持的 typed tool、`auto`／`any`／`none`／named choice、missing named choice、需 sanitizer 的名称、assistant function call 与 user function output。普通function声明、forced choice、历史call name使用同一映射；`call_id` byte-exact；arguments以JSON字符串发送；禁止伪造Responses item `id`。Web search及其他server／typed tools按server-tool no-revive在upstream调用前`REJECT`，不得由实现自行白名单化。
- **缺陷注入控制**：只 sanitize 声明而不改 choice／历史 call、保留悬空 choice、把 `call_id` 塨进 `id`、改变 call id、或 arguments 双重 JSON 编码。完整 wire 与 roundtrip identity 断言必须变红。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：tool 集合与 choice 共同变换，call identity 可跨请求与响应无歧义往返。

### REQ-05 thinking、reasoning 与 signature 请求往返

- **双格式独立 oracle**：本项目 producer 主格式直接绑定 current Spec“项目主 v1 wire contract”，默认只输出 payload prefix `ghc-api-proxy:synthetic-reasoning:v1:`或 bare marker `ghc-api-proxy:synthetic-reasoning:v1`。项目 payload 是固定 tag＋非空 `encrypted_content` 的最小紧凑 UTF-8 JSON，再经 canonical unpadded base64url；不得编码 item／model／upstream identity，也不得加入 HMAC、JCS、`kid`或新 delimiter。Consumer 在项目格式之后兼容 `/home/xp/src/copilot-api-js` commit `8d5c861c2e079b92401dd8ccd49695a363d078fe` 的 v1 合法 canonical 主路径、bare prefix与legacy bare sentinel；该固定 upstream 只定义 compatibility 输入，不定义本项目 producer bytes或全 malformed Node边界。
- **正确样本**：覆盖enabled／adaptive／disabled thinking、budget到effort、capability gate、summary＋payload、summary-only、encrypted-only、多个reasoning items、strip option、两类bare、upstream legacy、project unknown version、project malformed v1、代表性upstream malformed、foreign／unsigned／redacted thinking。项目producer exact向量固定为`opaque-😀`→`ghc-api-proxy:synthetic-reasoning:v1:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLfCfmIAifQ`；缺失／空payload→项目bare marker。Upstream compatibility向量固定为`ENC==`→`copilot-api:synthetic-reasoning:v1:RU5DPT0`、`opaque-😀`→`copilot-api:synthetic-reasoning:v1:b3BhcXVlLfCfmIA`，并覆盖bare prefix `copilot-api:synthetic-reasoning:v1:`与legacy sentinel `copilot-api:synthetic-reasoning:v1`。再重放stream `.added="MID-STATE-added-blob"`后`.done="AUTHORITATIVE-done-blob"`，断言项目producer只采用authoritative `.done`。项目producer→client echo→Responses consumer必须value-exact恢复非空payload；consumer必须同样value-exact恢复两个upstream合法向量。Direct Messages sanitizer必须剥离整个项目synthetic namespace、upstream prefix form与legacy sentinel。Project unknown、recognized malformed与foreign均按稳定分类记录，整个thinking block从Responses wire丢弃且不恢复visible summary或`encrypted_content`，不抛裸异常、不泄漏完整signature；不要求枚举所有非canonical Node codec边界。
- **缺陷注入控制**：必须分开执行以下两种单侧变异，任一未执行都使REQ-05为`UNVERIFIED`；共享helper同时改变producer与consumer不算有效控制。
	- **producer-only**：消费者完全不参与expected生成；只改变项目namespace／version／tag／最小字段集合、UTF-8紧凑JSON、base64url alphabet／padding、empty handling、strip marker或authoritative `.done`选择之一，直接与项目exact向量、bare marker和block顺序比较，必须变红。让producer输出upstream v1也必须变红。
	- **consumer-only**：生产者完全旁路，直接向真实请求入口分别喂项目exact向量／bare／unknown／malformed、upstream两个合法向量／bare／legacy／代表性malformed以及foreign signature；只改变first-match识别顺序、项目schema gate、upstream合法主路径decode、bare／legacy行为、稳定分类、whole-block drop、direct-leg strip或multi-item association之一，expected保持不动，必须变红。把每个malformed差异都强制等同Node不是合法变异目标。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`、`LIVE-CANARY`。真upstream canary只验证恢复后的Responses `encrypted_content`可被接受；它不充当carrier格式oracle。
- **通过判据**：provenance图必须记录四条链：current Spec内嵌项目exact bytes→Python producer输出观测点；独立静态项目vectors→Python consumer输入观测点；固定upstream bytes→Python consumer输入观测点；固定Responses event corpus→Python semantic normalizer。Expected资产不得调用产品codec生成；产品producer／consumer共享codec不能同时控制expected与actual。最终同时证明项目主producer稳定、两类consumer输入可互操作、一item一block且普通模式encrypted-only no-loss，而不是只证明产品与自己round-trip。

### REQ-06 approval 修改与每 attempt 转换

- **正确样本**：approval 修改 Anthropic tools/messages 后批准；完整 Anthropic prepare 与 hooks 重新运行一次，随后每个 attempt 都在 `PRE_SEND` 后把该 attempt 的最终 Anthropic payload 转成 Responses wire。拒绝时 upstream 调用为零。
- **缺陷注入控制**：在 approval 或 `PRE_SEND` 前只转换一次、让 approval 看 Responses wire、审批修改后不重新 sanitize，或嵌套第二个 approval gate。第二 attempt 的 captured wire、phase trace、pending approval 数与 History 必须暴露错误。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`。
- **通过判据**：一次用户请求最多一个 approval 决策；每次实际发送精确反映该 attempt 的 Anthropic payload。

## 非流响应 gate

### NS-01 text、refusal、unknown item 与 content order

- **正确样本**：Responses output按顺序包含reasoning、message output_text、refusal、future unknown item与普通text。已支持item映射到Anthropic blocks且顺序稳定；refusal形成text block并记录`DEGRADE` fact，future unknown item按冻结矩阵`REJECT`，不能由实现改成degradation或无痕消失。
- **缺陷注入控制**：静默跳过 unknown item、合并后重排 text／refusal、或在空 content 时掩盖本应报错的 unknown item。content 与 degradation/error 断言必须变红。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：最终 `MessagesResponse` 可被 Anthropic SDK schema 消费，且每个输入 marker 都有明确去向。

### NS-02 tool call、arguments 与 stop reason

- **正确样本**：覆盖合法 JSON arguments、任意 malformed JSON、多个 function calls、意外 server-tool item 与 terminal status 冲突。function call 映射为 `tool_use`，call id/name/input 正确；存在 tool call 时 `stop_reason=tool_use` 优先；malformed arguments 按冻结基础政策严格失败，不运行尚未裁决的 repair；server-tool 按 no-revive 拒绝。
- **缺陷注入控制**：把 malformed arguments repair或静默改成 `{}`、丢 call id、恢复错误 tool name、让 completed status 覆盖 `tool_use` stop reason，或将 server-tool伪造成普通 function／Anthropic server block。gate 必须变红。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：基础合同不执行repair；任意malformed arguments走确定错误策略，不得制造看似成功的空工具调用。未来只有新冻结Spec显式启用repair后，该扩展才另行验收。

### NS-03 encrypted-only 与多 reasoning items

- **正确样本**：把 block cardinality、visible summary与opaque payload可恢复性作为三个独立断言。`summary=[]`且`encrypted_content` absent时必须生成恰好一个`{type:"thinking",thinking:"",signature:"ghc-api-proxy:synthetic-reasoning:v1"}` block；`summary=[]`且`encrypted_content=""`时必须生成相同的恰好一个项目bare marker block；两者经client echo后都恢复一个`{type:"reasoning",summary:[]}` item，且不得添加或伪造`encrypted_content`。`summary=[]`且`encrypted_content="opaque-state"`时必须生成恰好一个`thinking=""`且signature为项目主v1 payload carrier的block，经client echo后value-exact恢复`encrypted_content="opaque-state"`。同时覆盖多个各有summary／非空encrypted payload的reasoning items、summary-only item、带visible summary的empty payload与explicit strip mode；默认producer对每个item生成项目主v1 payload或项目bare marker。另以旁路producer的静态输入证明同一consumer对upstream v1合法payload／bare／legacy兼容。多item不得跨item聚合summary、覆盖ciphertext或改变语义顺序。
- **缺陷注入控制**：分别执行单侧变异并核对目标失败原因：只在summary非空时创建thinking block时，absent／empty两个正确样本必须因实际cardinality为0而非1变红；把项目bare marker解释成含可恢复payload时，echo必须因凭空出现`encrypted_content`变红；丢弃non-empty encrypted-only item或把它降为bare marker时，echo必须因`opaque-state`缺失而变红；使用“summary全累加、encrypted后值覆盖”的不对称accumulator时，多item cardinality、association与顺序断言必须变红。不得用同时修改producer与consumer的同源变异制造假绿。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：每个Responses reasoning item恰好对应一个Anthropic thinking block。Absent／empty `encrypted_content`同义，均生成`thinking=""`＋项目bare marker并在echo后恢复`summary=[]`，但恢复结果明确没有`encrypted_content`；non-empty encrypted-only生成payload carrier并value-exact恢复原opaque值。多item cardinality、carrier association与语义顺序保持一对一；默认输出只使用项目主v1，explicit strip保留每item block cardinality并记录有意payload removal。Upstream v1只作为独立consumer compatibility输入，不授权producer改用upstream格式或复制有损聚合。

### NS-04 terminal status 与 usage 算术

- **正确样本**：覆盖 completed、cancelled、incomplete/max_output_tokens、incomplete/content_filter、unknown future reason、无 usage，以及 total input、cache read、cache write、output、reasoning 与 modality details。断言 stop reason、content-filter marker、净 input 算术和保留 details。
- **缺陷注入控制**：不扣 cache write、重复扣 cache、把 reasoning tokens 算入 input、丢 detail、把 unknown reason 当成功 max_tokens，或让 tool call 不再优先。参数化 oracle 必须变红。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：归一化 usage 各分量非负、总量关系符合已冻结口径，stream 与 nonstream 得到相同事实。

### NS-05 HTTP error 与失败响应

- **正确样本**：覆盖 Responses HTTP 400／429／500、failed status 有／无 message、content-type 非 JSON、timeout 与 malformed success body。用户收到合法 Anthropic error envelope、正确 HTTP status 与可审计 message；response 始终关闭；History 失败且只 finalize 一次。
- **缺陷注入控制**：原样透传 Responses error body、把 failed status 返回 200 message、丢 HTTP status、吞 response close，或先运行成功 response hook。route-level gate 必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`LOCAL-FAULT`；真实错误body与status组合由可确定`LIVE-CANARY`触发器或版本化`CAPTURE-CORPUS`校准。
- **通过判据**：错误不泄漏 Responses wire 合同，不产生成功 content 或 completed History。

## 流式转换与 block buffering gate

### STR-01 合法 Anthropic SSE 与独立 consumer

- **正确样本**：Responses stream 依次表达 reasoning、tool_use、text、usage 与 terminal；对每个 event 的字节边界、SSE 行边界和 JSON delta 做随机分片。将输出交给真实 Anthropic Python SDK streaming consumer，断言累积 message、block index、tool input、thinking/signature、stop reason 与 usage。
- **缺陷注入控制**：删除任一 start／delta／stop、在 stop 后向旧 index 发 delta、复用稀疏 upstream index、重复 `message_stop`，或把 JSON event 拆分处理错。独立 strict grammar oracle 必须变红；官方 SDK若宽松接受，不得覆盖 strict失败。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`；官方 SDK 公共 streaming 入口和版本兼容性由独立 SDK compatibility oracle 交叉验证。
- **通过判据**：strict grammar oracle 依据冻结 event state machine判定 Anthropic index连续单调、每个 block恰好一次 start／stop、terminal恰好一次；SDK oracle只证明目标 SDK版本能消费合法 feed并记录其对非法 feed的实际反应。两者结论分别报告，不以“SDK接受”证明 wire合法。

### STR-02 完整 block 才可见

- **正确样本**：分别把 text、thinking 与 function arguments 拆成多个 upstream delta。在对应 `.done`／item completion 前，以并发 reader观察下游必须得到零个该 block字节；该 block完成且它之前的 semantic blocks也都完成时，连续可提交前缀立即进入串行 sink，每个 block batch包含 start、全部 delta、必要 signature与stop，且可独立解析。专门覆盖 `A.start → B.start → B.done` 时零写入，随后 `A.done` 后按 A、B 顺序提交。
- **缺陷注入控制**：切换为逐 delta live write、把 `content_block_start` 提前泄漏、把 signature留到 block commit之后、按完成顺序先提交B，或在连续前缀已就绪且sink可写时仍等完整response。时序probe必须分别抓到过早可见、重排或无故过晚阻塞。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`AUTO-SOCKET`。
- **通过判据**：探测对象是“下游可观察提交边界”，不是内部 list或buffer长度；未完成block完全不可见，只有从最早未提交位置开始的连续已完成前缀立即可见，后完成但序位更晚的block必须等待缺口闭合。

### STR-03 no duplicate、no loss、order

- **正确样本**：生成带唯一 marker 的多 block 序列，覆盖 thinking→tool→text、text→tool→text、多个 tools、空 delta、web search 与稀疏 upstream indices；对 chunking 与 interleaving 做随机化。最终 SDK 累积 block marker 序列必须与语义输入序列精确相等。
- **缺陷注入控制**：重复一个 committed block、漏掉中间 block、交换两个 blocks、将旧 attempt buffer 与新 attempt 拼接，或对 continuation index 错位。序列 equality 必须变红。
- **方式**：`AUTO-UNIT` property-based、`AUTO-COMPONENT`、`AUTO-HTTP`。
- **通过判据**：不能只断言最终文本相同；block 类型、marker、call id、signature、index 与顺序都参加比较。

### STR-04 terminal、clean EOF 与流内 error

- **正确样本**：覆盖 completed、incomplete、response.failed、Responses `error` event、没有 terminal 的 clean EOF、malformed SSE 与 converter exception。成功只在合法 terminal 且全部 block drain 后产生 `message_delta`＋`message_stop`；其他路径产生确定 Anthropic error／连接终止和 failed History。
- **缺陷注入控制**：在 clean EOF 上调用正常 flush、failed 后仍发 `message_stop`、吞 malformed event、重复 terminal，或 error 后继续 content。route-level consumer 必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`AUTO-SOCKET`、`LOCAL-FAULT`；真实upstream terminal／EOF形态由`LIVE-CANARY`正常样本与`CAPTURE-CORPUS`异常样本校准。
- **通过判据**：成功 terminal 与错误 terminal 互斥；任何 failure 后不得出现成功 terminal。

### STR-05 流式 usage 与 nonstream 等价

- **正确样本**：同一语义响应分别走 nonstream 与多种 SSE 分片，包含 cache read/write、reasoning/output token details。归一化后的 Anthropic usage 完全相等，History 与 token observer 只采纳最终成功 attempt。
- **缺陷注入控制**：累加失败 attempt usage、重复消费 terminal usage、只从 delta 猜 usage、或 stream 路径遗漏 cache／reasoning details。等价 oracle 必须变红。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：usage 来源与 attempt provenance 可追踪；失败 attempt 不进入用户账单事实。

## retry、failure frontier、cancel 与 backpressure gate

### REL-01 response headers 前失败与首 block commit 前失败

- **正确样本**：分别在 response headers 前、首 block 未完成时注入 transport reset／clean truncation；预算允许时由唯一 pipeline owner 新建下一 attempt。失败 attempt 的 bytes、usage 与 converter state 全部丢弃，客户端只看到后一 attempt 的一代完整输出。
- **缺陷注入控制**：启用 SDK 自动 retry、让 converter 自行重发、保留旧 attempt buffer，或不增加 context attempt。底层请求数、attempt ledger 与客户端序列必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-SOCKET`。
- **通过判据**：底层请求数严格等于 attempts；只有 application pipeline 消耗 retry budget。

### REL-02 attempt reset 与失败代隔离

- **正确样本**：多个 pre-commit failures 后成功；每个 attempt 使用不同 marker、usage、message id 与稀疏 index。最终只出现成功 attempt 的 marker、usage 和 id，Anthropic indices 从合法起点重新分配。
- **缺陷注入控制**：不 reset parser、accumulator、open block、usage 或 index map 中任一项。no-dup/no-loss/order 与 usage gate 必须变红。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`、`AUTO-SOCKET`。
- **通过判据**：reset 覆盖所有 attempt-local state；不能只清 byte buffer。

### REL-03 commit 后失败

- **正确样本**：首个完整 block 已下游可见后，在下一 block 中途注入 reset、clean EOF 与 converter error。不得从头透明 retry；已提交 block 保持一次且完整，未提交 block 不泄漏；客户端得到明确 partial-degrade／stream error。若未来实现 continuation，必须有独立 resume 去重契约后另行验收。
- **缺陷注入控制**：commit 后重跑整个 request、重复已提交 prefix、补发半个 block，或把 partial 当 completed。客户端 marker 与 History 终态必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`AUTO-SOCKET`。
- **通过判据**：commit frontier 一旦前进不可回退；没有已验收 resume 协议时，任何 post-commit full replay 都是 blocker。

### REL-03B sink partial-write 与 delivery-uncertain

- **正确样本**：完整 block envelope已materialize后，通过真实 loopback socket／ASGI sink分别在 response-start、`message_start`、block batch多个byte offset及terminal batch注入短写、RST、task cancellation和“调用返回前连接状态未知”。记录客户端实际观察bytes、sink outcome与request-level delivery frontier；只有sink明确报告整个操作未开始时才保持`not_started`，任何可能已写出前缀的结果都进入对应`uncertain`状态。
- **缺陷注入控制**：让driver把assembler complete或render complete当作committed、把partial write误归类为零写入并重发同一batch、在`uncertain`后发送success terminal，或把History记为completed。相同fault offset下，wire／frontier／History联合断言必须变红。
- **方式**：`AUTO-HTTP`、`AUTO-SOCKET`、`LOCAL-FAULT`。
- **通过判据**：不得声称socket write原子或客户端durable ack；`delivery-uncertain`后禁止重发同一envelope／batch和透明full retry，禁止成功terminal，资源关闭且History／FINALIZE恰好一次。报告同时保留“客户端实际捕获前缀”和“代理所知状态”，不得用任一方冒充另一方。

### REL-04 retry exhaustion

- **正确样本**：所有 pre-commit attempts 都失败直到预算耗尽。客户端收到单一 Anthropic error，零 success blocks、零 `message_stop`；History attempts 与真实请求相等且终态 failed。
- **缺陷注入控制**：预算 off-by-one、多打一请求、泄漏最后失败 attempt 的 prefix、返回 synthetic success terminal，或 History completed。gate 必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`AUTO-SOCKET`。
- **通过判据**：耗尽只产生一个最终失败事实，不伪装成功、不无限重试。

### REL-05 client cancellation

- **正确样本**：分别在 headers 前、首 block 未完成、首 block commit 后由 HTTP client 断开或取消 task；同时覆盖 WS downstream close。上游 response／socket、producer task 与 buffer 被及时关闭；不 retry；History 标记 aborted/failed 的明确终止原因并只 finalize 一次。
- **缺陷注入控制**：把 cancellation 当 transport retry、后台 producer 继续读取、吞 `CancelledError`、History completed，或泄漏 pending task／connection。资源与 ledger 断言必须变红。
- **方式**：`AUTO-HTTP`、`AUTO-WS`、`AUTO-SOCKET`、`LOCAL-FAULT`；真实upstream是否收到cancel／close只在`LIVE-CANARY`可观察时记录，不要求不可控对端每轮提供确认。
- **通过判据**：取消传播方向清晰且资源归零；不得只断言客户端收不到更多 bytes。

### REL-06 backpressure、有限队列与全局 resident quota

- **正确样本**：使用慢downstream consumer、有限completed-block queue、并发requests和不同普通大小的blocks；生产者必须被背压，所有draft、completed queue、预渲染envelope与carrier bytes同时进入普通per-request aggregate reservation和global reservation／resident计账，charge／release绑定request、attempt与owner且恰好一次。测试配置满足`0 < request_budget < global_budget`，每个输入block都明显小于`request_budget`，但同一已接纳请求跨多个draft、completed block、预渲染envelope及History移交对象的resident bytes可逐步逼近并尝试超过`request_budget`。在下一笔charge仍可容纳时正常继续；该charge会超过request aggregate预算时，必须在charge前暂停上游读取且两个计数均不得超卖。若downstream drain释放该请求的completed对象，则等待者继续组装原block；若当前draft等不可释放对象使请求在既有request deadline或普通capacity policy内不可能取得容量，则产生稳定Anthropic capacity／limit终态、停止继续读取、不提交partial block、释放该请求全部charge，且另一请求在global预算仍有余量时不受影响。全局reservation暂不可得时同样暂停可暂停的upstream读取，容量恢复后继续原block；实际全局内存压力达到已决拒绝条件时只拒绝新的bridge admission，已接纳请求继续服从普通backpressure、cancel和既有request deadline。任何终止都不提交当前partial block，已提交前缀不重复。
- **缺陷注入控制**：分别注入两种相反缺陷且不得合并：一是删除per-request aggregate检查、只保留global reservation，使单请求在global尚有余量时越过其普通request预算；二是把聚合检查替换成单block大小检查或`16 MiB`专属分支，使多个普通block累计不受限或跨某个硬编码size才失败。另覆盖无界queue、各组件分账而无request／global汇总、容量压力后切live token forwarding／spill、拒绝新admission后仍启动transport、丢frame，或consumer停止后producer无限前进。正确实现样本与上述每个单侧变异使用同一组配置化预算和普通大小输入；request/global current bytes、各自high-water mark、quota wait、queue depth、上游读取时序、marker、其他请求进展、cleanup与稳定error reason联合断言必须分别变红。
- **方式**：`AUTO-WS`、`AUTO-SOCKET`、`LOCAL-FAULT`；`LIVE-CANARY`只观察正常flow-control，不要求真upstream每轮制造queue pressure。
- **通过判据**：背压是实际await链与有限容量的可观察效果，不是配置名；per-request current bytes等于该request所有resident owner之和，global current bytes等于所有request及共享bridge resident owner之和，且同一对象不得双重charge或提前release；success／retry reset／conversion failure／capacity failure／cancel／shutdown后两级计账回到实际resident值。**不建立`>16 MiB`专门gate、fixture类别、metric阈值或状态分支**；size只作为普通随机维度，任何单个fixture均无须接近16 MiB，测试不得以跨过16 MiB作为单独断言。未经新用户裁决，不验收victim selection、额外终止政策或全面物理OOM状态机。

## HTTP 与 WebSocket transport gate

### TR-HTTP Responses upstream

- **正确样本**：真实 ASGI `/v1/messages` 经 HTTP Responses upstream fake server 覆盖 nonstream、SSE、429、failed、RST、slow body 与 cancellation。断言 Anthropic media type、headers policy、body/SSE schema、close 与 lifecycle。
- **缺陷注入控制**：绕过 converter 原样 passthrough Responses JSON/SSE、转发不允许的 upstream headers、错误 content type，或 response 未关闭。外部 HTTP oracle 必须变红。
- **方式**：`AUTO-HTTP`、`AUTO-SOCKET`、`LOCAL-FAULT`、`LIVE-CANARY`、`CAPTURE-CORPUS`。
- **通过判据**：客户端 wire 只包含 Anthropic 合同；真实 route 接线而非单独 converter 通过。

### TR-WS Responses upstream

- **正确样本**：Anthropic 请求通过 WS Responses upstream transport 发出 `response.create`，接收 reasoning/tool/text/terminal JSON frames，并向下游提供与 HTTP transport 等价的 Anthropic nonstream 或 SSE 结果。覆盖 upgrade rejection、network close、terminal error、slow consumer 与 cancel。
- **缺陷注入控制**：让 Anthropic route借用原生 `/v1/responses` WS 的独立 approval／History owner、漏强制 stream、错误 terminal 提前停止、WS close 后透明 full replay，或将 Responses JSON frame直接发给 Anthropic client。transport parity 与 lifecycle gate 必须变红。
- **方式**：`AUTO-WS`、`AUTO-COMPONENT`、`LOCAL-FAULT`、`LIVE-CANARY`、`CAPTURE-CORPUS`。
- **通过判据**：WS 只是 attempt transport adapter；不得形成第二条请求 pipeline。

### TR-PARITY HTTP／WS 语义一致性

- **正确样本**：把同一语义 fixture 经 HTTP Responses 与 WS Responses 两种 upstream transport 返回，随机化各自 chunk/frame 边界。比较归一化 Anthropic content、order、tool identity、reasoning/signature、usage、error category、attempts 与 History。
- **缺陷注入控制**：仅在 WS 丢 reasoning `.done`、仅在 HTTP 丢 cache usage、给 WS 单独 retry owner，或不同 transport 使用不同 unknown-item 策略。parity comparison 必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`AUTO-WS`；双方真实协议差异由`LIVE-CANARY`与版本化`CAPTURE-CORPUS`校准。
- **通过判据**：除 transport metadata 外，用户可观察语义完全相同。

## History、hooks、approval 与 tokenization gate

### LIFE-01 History 一致性

- **正确样本**：覆盖 nonstream success、multi-block stream success、pre-commit retry success、post-commit failure、converter failure、client cancel 与 approval rejection。每个请求只有一条 entry；original payload 始终是 Anthropic；attempts 等于真实 upstream 请求；终态、error、session／agent 与 normalized response 正确。
- **缺陷注入控制**：桥接时新建第二条 protocol History、把 Responses wire 覆盖 original payload、流在首 block 后就 completed、重复 finalize，或漏记失败 attempt。store 与 in-flight 快照必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`AUTO-WS`。
- **通过判据**：History 是同一 RequestContext 的投影，不由 transport route另建真相源。

### LIFE-02 hooks 顺序、语义与 exactly-once finalize

- **正确样本**：Messages upstream、HTTP Responses 与 WS Responses 使用同一 hook fixture。比较 `REQUEST_RECEIVED`、`PRE_SANITIZE`、`POST_SANITIZE`、每 attempt `PRE_SEND`、`RESPONSE`／`ERROR`、`FINALIZE` 的顺序、protocol、attempt_number 与 modification records。response hook 只看到转换后的 Anthropic body；流 success／failure 各 finalize 一次。
- **缺陷注入控制**：把 Responses wire 暴露给 Anthropic hook、conversion 前运行 response hook、retry 时跳过 `PRE_SEND`、同时由 route 与 pipeline finalize，或 failure 仍发 completed finalize。phase trace 必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`。
- **通过判据**：hook 合同不随 upstream transport 改变，且 phase trace 与实际 attempts 对齐。

### LIFE-03 approval exactly once

- **正确样本**：approved unchanged、approved modified、rejected、timeout 与 client cancel while pending；覆盖 HTTP／WS Responses transport。pending approval 恰好一份，修改作用于 Anthropic payload，拒绝／timeout 时 upstream 调用为零，History 终态明确。
- **缺陷注入控制**：bridge 进入 OpenAI protocol guard 产生第二 approval、重试再次审批、批准修改未重新 prepare，或拒绝后仍发送。pending list、call count 与 captured wire 必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`、`AUTO-WS`。
- **通过判据**：approval 决策属于用户请求而非 transport attempt；retry 不重复询问。

### LIFE-04 token counting 与 calibration

- **正确样本**：Responses-only model 调用 `/v1/messages/count_tokens` 时不误发 Anthropic count endpoint，返回 Anthropic shape、正整数 input tokens 与 estimate provenance。随后 bridge success 将 normalized input/cache facts写入同一 Anthropic calibration bucket；prompt-limit error 更新 Anthropic limit registry；reasoning tokens 不计入 input。
- **缺陷注入控制**：调用 unsupported Anthropic count endpoint、按 Responses request wire 估算而改变 Anthropic合同、把 reasoning 加入 input、失败 attempt 重复校准，或 HTTP／WS transport 各用不同 bucket。counter、state store 与 observer 断言必须变红。
- **方式**：`AUTO-COMPONENT`、`AUTO-HTTP`；真实Responses usage与prompt-limit error形状由可确定`LIVE-CANARY`触发器或版本化`CAPTURE-CORPUS`校准。
- **通过判据**：count_tokens 的用户合同保持 Anthropic；Responses usage 只是校准事实输入，不取代 Anthropic estimator。

## 真上游、capture corpus 与本地 fault 校准

本地 fake 只有在与真实counterpart对账后才可作为验收依赖。fake不得比真实协议更“友好”，尤其不能自动补terminal、合并chunk、规范化malformed JSON、吞close code、替产品处理backpressure，或把HTTP与WS错误统一成测试期望。校准证据严格分成三层，报告不得混写：

1. `LIVE-CANARY`每轮只执行可确定触发的正常text／tool／reasoning／incomplete及上游公开提供的错误fixture。不可控的5xx、truncation、network close、特定close code或queue pressure本轮没有出现时，记录“未观察”，不判实现失败。
2. `CAPTURE-CORPUS`保存真实历史异常或官方fixture。每条记录必须有producer、SDK前raw观测点、recorder revision、自动retry关闭证明、upstream／model／API revision、raw status／headers／SSE bytes或WS frames／close、脱敏变换和内容hash。过期或缺失只使依赖该形态的验收项为`UNVERIFIED`，不得伪造live capture，也不得把整个实现判成缺陷。
3. `LOCAL-FAULT`在本地raw transport边界确定性重放corpus并注入RST、half-close、partial write、malformed frame、slow read和queue pressure。它每轮必跑，证明产品处理路径，但不得被描述成真实upstream异常。

Raw capture的provenance图固定为：真实upstream是producer→独立raw HTTP／WS recorder在任何产品Responses SDK、自动retry、parser、chunk merger或error normalizer**之前**观测→只做可审计脱敏的fixture generator→immutable corpus。产品SDK解析同一raw corpus是第二条兼容性观察，不是raw fixture的来源；与产品共用transport recorder的capture不能给fake独立性签字。

### CAL-01 HTTP nonstream 校准

- **正确样本**：`LIVE-CANARY`捕获可确定触发的success、tool、reasoning与incomplete；代表性4xx／5xx来自上游公开触发器或`CAPTURE-CORPUS`。SDK前raw recorder保存status、headers、body bytes、usage与close；fake重放必须与raw fixture的可观察字段一致。
- **缺陷注入控制**：在 fake 中改一个 status、移除 error detail、补一个真实响应没有的字段，或不要求 response close。fixture parity gate 必须变红。
- **方式**：`LIVE-CANARY`、`CAPTURE-CORPUS`、`AUTO-COMPONENT`、`LOCAL-FAULT`。
- **通过判据**：fake provenance可追溯到SDK前raw capture；不能以项目converter或产品SDK的输出反向定义fake。不可控5xx本轮未出现不构成false-red。

### CAL-02 SSE framing 与 terminal 校准

- **正确样本**：`LIVE-CANARY`捕获可确定触发的text、tool arguments、reasoning summary／encrypted content、completed、incomplete与正常close；failed、error与可观察truncation来自公开触发器或`CAPTURE-CORPUS`。raw recorder保留原始SSE event名、data bytes、空行、wire chunk boundary、终止顺序与socket close；SDK exception仅作为另列兼容观察。
- **缺陷注入控制**：fake 总把一个 event 放在单一 chunk、自动补 `.done`／terminal、把 failed 变成 exception而丢 frame，或 clean EOF 总被当成功。真实 capture replay gate 必须变红。
- **方式**：`LIVE-CANARY`、`CAPTURE-CORPUS`、`AUTO-SOCKET`、`LOCAL-FAULT`。
- **通过判据**：parser同时通过raw capture replay与随机rechunk；本地fault确定性覆盖clean EOF／truncation。不得要求真upstream每轮自行截断连接。

### CAL-03 WebSocket 校准

- **正确样本**：`LIVE-CANARY`记录upgrade headers、初始`response.create`、frame schema、terminal frame与正常close code／reason；network failure、异常close与queue pressure来自公开触发器或`CAPTURE-CORPUS`，并由`LOCAL-FAULT`每轮确定性注入。raw recorder位于产品WS SDK之前并保存原始frame bytes与close handshake。
- **缺陷注入控制**：fake 忽略 required frame、把 terminal 后的 close 隐藏、永不背压、或使用与真实协议不同的 error frame。parity gate 必须变红。
- **方式**：`LIVE-CANARY`、`CAPTURE-CORPUS`、`AUTO-WS`、`LOCAL-FAULT`。
- **通过判据**：WS fake的producer、SDK前观测点和真实上游provenance明确；真upstream本轮未产生network failure／queue pressure不阻断可达的基础`PASS`，但缺失或过期corpus覆盖项必须显式`UNVERIFIED`。

### CAL-04 Anthropic strict grammar oracle

- **独立来源与版本绑定**：本节内嵌表 `CAL-04-GRAMMAR-v1` 是当前strict producer oracle的规范资产，定位锚点为本文件“CAL-04 Anthropic strict grammar oracle”；协议绑定`anthropic-version: 2023-06-01`，外部来源绑定Anthropic官方《Streaming messages》的“Event types”“Content block delta types”与“Full HTTP stream response”章节（`https://docs.anthropic.com/en/api/messages-streaming`，2026-08-07读取）以及官方《Thinking》的“Streaming thinking”“Thinking encryption”章节（`https://docs.anthropic.com/en/build-with-claude/thinking`，2026-08-07读取）。官方版本策略允许新增event type，因此本表只定义bridge当前承诺生成的最小合法子集；未来event或block type在更新本表版本前不得由测试作者现场判成合法bridge输出。实现fixture后固定路径为`tests/fixtures/anthropic_responses_bridge/anthropic-sse-grammar-v1.json`，但该资产**目前只是规划、尚不存在**；落地前expected直接来自本表，落地后fixture必须逐行等价并在manifest记录fixture SHA-256、本表版本、上述协议版本和来源URL，不能以fixture反向改写本表。

本 grammar 的输入单位是**串行 sink batch**，不是可被旁路 writer 单独发送的 event。表内“batch 内事件”只用于在完整 batch 已 materialize 后校验其内部顺序；batch 校验与 sink 接受前，其中任何 event 都不是下游已观察事实。这样既能校验 Anthropic event grammar，又不会把 `message_start` 与首个完整 block之间的瞬时解析位置误写成允许独立 `ping`／body write的提交边界。

| `CAL-04-GRAMMAR-v1`状态／对象 | 唯一允许的下一 batch／batch 内语义事件 | 必须满足的字段、batch与累积规则 |
|---|---|---|
| stream初始态 | 首个完整content batch、零content terminal batch或`error` batch | 首个content batch必须已完整materialize，并按`message_start → index=0的完整block envelope`组成同一sink batch；零content成功必须按`message_start → message_delta → message_stop`组成同一完整terminal batch。`message_start`恰好一次；SSE `event`名必须等于JSON `type`；`message.content=[]`、`stop_reason=null`。任一首批提交前不得出现HTTP success headers、`ping`或任何body event。若先出现`error`则直接进入error终止态。 |
| `message_started_but_no_completed_block`，仅首个content batch的内部校验瞬态 | 同一batch内index=0的完整block envelope；不得结束batch、不得接受`ping`、`message_delta`、`message_stop`、`error`或旁路body write | 该状态在校验首batch内的`message_start`后进入，在同一batch的首个`content_block_stop`后原子转为`one_or_more_completed_blocks`；它不是合法的batch间停留状态或下游可观察提交点。首个block必须在进入sink前已经完成，`message_start`与完整envelope一起接受或一起失败，禁止`message_start → ping → first content_block_start`及任何先发`message_start`再等待block的实现。 |
| `zero_content_terminal_batch`，仅零content terminal batch的内部校验瞬态 | 同一batch内唯一`message_delta`后立即`message_stop` | `message_start`、`message_delta`与`message_stop`必须在terminal已确定后一起materialize并作为一个sink batch接受；三者之间不得插入`ping`、error或任何其他body event，禁止`message_start → ping → message_delta`。该batch接受后直接进入success终止态。 |
| `one_or_more_completed_blocks`，batch边界且当前无open block | `ping` batch、下一连续index的完整block batch、唯一terminal batch或`error` batch | 第一个block已经随`message_start`同batch提交；后续block index严格为前一个已关闭index加1，每个block以独立完整batch提交。此状态可接受零次或多次`ping` batch；`ping`不分配index、不改变block／message累积。禁止index gap、复用、嵌套start和已关闭index复活。 |
| open `text` block | 零个或多个同index的`content_block_delta{text_delta}`，随后同index的`content_block_stop` | start payload为`{type:"text",text:""}`；只拼接`text`字段；bridge允许空text block，因此可零delta关闭；其他delta type、错index、stop后delta均非法。 |
| open `tool_use` block | 一个或多个同index的`content_block_delta{input_json_delta}`，随后同index的`content_block_stop` | start含非空`id`、非空`name`和`input:{}`；按到达顺序拼接`partial_json`，stop时完整串必须解析为JSON object并成为最终`input`；其他delta type、错index、零delta、malformed／非object终值均非法。 |
| open `thinking` block | 零个或多个同index的`content_block_delta{thinking_delta}`，恰好一个同index的`content_block_delta{signature_delta}`，立即接同index的`content_block_stop` | start payload为`{type:"thinking",thinking:"",signature:""}`；thinking按序拼接。`signature_delta`必须非空、只能出现一次、位于全部thinking delta之后且是stop前最后一个语义事件；display omitted可为零thinking delta，但不能省signature。signature后不得再有任何delta。 |
| 一个或多个blocks关闭后的message尾部 | 一个完整terminal batch，内部为恰好一个`message_delta`后接恰好一个`message_stop` | `message_delta`同时承载冻结的顶层stop／terminal usage事实；不得出现第二个`message_delta`，也不得再start／delta／stop任何content block；usage按既定usage gate累积，`message_stop`不得携带新content。terminal batch接受后不得有任何事件。 |
| 合法`ping` batch | 保持`one_or_more_completed_blocks`状态 | 只允许在首个完整block已随`message_start`成功接受后的batch边界出现，可位于首block或任一后续`content_block_stop`之后、下一block／terminal batch之前；不得位于首批之前、`message_started_but_no_completed_block`、`zero_content_terminal_batch`、任一open block内部、terminal batch内部或`message_stop`／`error`之后。 |
| 任一未成功终止状态的`error` | error终止态 | `error`与`message_stop`互斥；error后不得再有ping、content、message delta或terminal。它不补齐open block，也不得把partial block加入冻结message。 |

> ⚠️ **`ping` 的位置约束已被 2026-08-22 用户裁决推翻，本表与下面的 fixture 集合尚未跟进。** 裁决：HTTP success headers 在第一次上游 200 时就提交，`ping` 因此可以出现在首个完整 block **之前**——那正是该裁决要换取的保活窗口。见 `spec.md`「文档状态」与「Downstream Anthropic SSE」第 1／3 条。
>
> 本表是版本化的冻结语法 `CAL-04-GRAMMAR-v1`，其 `ping` 转移行、下面「不得把`ping`放在首批之前」那句、以及已闭评审行 R3-M1／R4-M1／R5-M1（它们正是历次裁 `ping` 位置的记录，其中 R4-M1 曾采纳过与本次同向的修订、后被 R5 推翻）需要作为**一次独立切片**一起重做并升版，而不是就地改一行。**该语法目前只存在于文档，主仓测试中没有实现**（`rg CAL-04 tests/` 无命中），因此不阻塞运行时行为。

- **完整最小正向fixture集合**：必须至少物化并冻结以下5条batch序列及其最终message：单一零content terminal batch `[message_start → message_delta → message_stop]`；首批 `[message_start → text block的两个text_delta → block stop]`；首批含tool block的两个可拼成object的`input_json_delta`；首批含thinking block的两个`thinking_delta → signature_delta → stop`；首批含omitted thinking的`signature_delta → stop`而无`thinking_delta`。有content的四类都另有“首个完整block batch已接受 → `ping` batch → terminal batch”的必需正样本，并可在后续完整block batches之间插入多个`ping`而最终message不变；零content fixture不得有`ping`变体。不得把`ping`放在首批之前、`message_start`与首个`content_block_stop`之间、任一后续block batch内部或terminal batch内部。所有fixture的index从0连续分配，成功路径恰好一个`message_delta`与一个`message_stop`，event name与JSON type逐项相等。
- **正确样本**：测试侧独立state machine只按`CAL-04-GRAMMAR-v1`和上述最小fixtures判定合法序列，覆盖连续index、start→delta→stop、各block允许的delta、signature位置、零content、ping无状态效果、唯一success terminal与error互斥；合法feed必须累积为各fixture冻结message。产品parser、renderer、官方SDK和候选实现均不得生成expected。
- **缺陷注入控制**：逐项向同一正向fixture只注入一种缺陷：delta-after-stop、missing start、duplicate stop、index gap／复用、block与delta type错配、tool partial JSON终值malformed／非object、signature缺失／重复／后置thinking delta、content-after-message-delta、duplicate `message_delta`、`message_start`前`ping`、open block期间`ping`、success／error双terminal、duplicate terminal、event name与JSON type不一致或post-error事件；同一grammar expected必须逐项变红。首批与零content各拆成两个正交控制轴：目标`ping`负fixture分别是单一首批`[message_start → ping → index=0的完整合法block envelope]`和单一零content terminal batch`[message_start → ping → message_delta → message_stop]`；除目标`ping`转移外，event字段、index、block envelope、terminal唯一性与batch边界必须全部合法。独立的split-batch负fixture不得含`ping`，分别是`[message_start] → [index=0的完整合法block envelope]`和`[message_start] → [message_delta → message_stop]`，只用于证明两个内部瞬态不得跨batch停留。对strict oracle本身逐项实施单侧放宽：放宽`message_started_but_no_completed_block`在同一首批内部接受一个无状态`ping`时，第一条目标`ping`fixture必须转绿；放宽`zero_content_terminal_batch`在同一terminal batch内部接受一个无状态`ping`时，第二条目标`ping`fixture必须转绿；两次均不得放宽batch完整性、block或terminal规则。随后外层mutation gate必须因原本非法的目标fixture被接受而红。对split-batch轴则只放宽对应内部瞬态跨batch停留，原始split fixture必须转绿，外层mutation gate必须因非法拆批被接受而红。任何fixture若先因拆分`message_start` batch、字段／index／envelope错误或另一规则失败，该轮控制无效。
- **方式**：`AUTO-UNIT`、`AUTO-COMPONENT`。
- **通过判据**：manifest精确绑定`CAL-04-GRAMMAR-v1`、batch输入模型及其来源／版本；expected来自本节冻结表而非产品parser、renderer、SDK实际行为或未来fixture作者。正控必须先证明五类最小合法fixture为绿，首个完整block batch已接受后的合法`ping`仍为绿，且两条不含`ping`的未拆批对应样本保持为绿。负控必须证明全部单缺陷样本、两条单batch目标`ping`样本与两条无`ping` split-batch样本分别按唯一目标原因变红；每个单侧oracle放宽必须先让其目标fixture转绿，再让外层mutation gate因非法fixture被接受而红，最后恢复oracle并复跑合法正样本为绿。官方协议新增项在完成来源复核并发布`CAL-04-GRAMMAR-v2`前标记`UNVERIFIED`，不得静默扩展v1。

### CAL-05 Anthropic 官方 SDK 兼容 oracle

- **正确样本**：将CAL-04合法feeds交给固定版本的官方Python SDK公共streaming入口，比较累积message；另把非法feeds交给SDK并只记录其实际接受／拒绝／异常，不把该结果改写成grammar expected。
- **缺陷注入控制**：只破坏合法feed的一个公共字段或event顺序，确认SDK compatibility gate无法再得到冻结合法message；非法feed若被SDK宽松接受，CAL-04仍须保持红。
- **方式**：官方SDK本地PoC，随后`AUTO-UNIT`固化版本化兼容结果。
- **通过判据**：CAL-04回答“wire是否严格合法”，CAL-05回答“目标SDK是否可消费”；二者均不得由产品parser兼任，结论分栏报告且互不覆盖。

所有真实capture都必须脱敏，不保存凭据、用户内容或不可公开的原始标识。上游API、model revision、recorder、SDK version或transport行为变化时，先重跑可确定live canary并评估corpus有效性，再决定fake fixture是否仍有效；未校准的新行为及过期corpus覆盖范围一律标记`UNVERIFIED`，不得误判`BLOCKED`。

## 自动化资产规划

后续实现者可以按项目命名约定调整文件名，但以下职责必须保持分离：

- request/nonstream 纯语义 corpus：`tests/acceptance/test_anthropic_responses_conversion.py`。
- stream assembler、随机 rechunk 与 SDK consumer：`tests/acceptance/test_anthropic_responses_stream.py`。
- block commit、retry frontier、attempt reset、cancel 与 backpressure：`tests/acceptance/test_anthropic_responses_resilience.py`。
- 真实 ASGI HTTP route：`tests/acceptance/test_anthropic_responses_http.py`。
- Responses WS upstream transport 与 HTTP/WS parity：`tests/acceptance/test_anthropic_responses_ws.py`。
- History/hooks/approval/tokenization：`tests/acceptance/test_anthropic_responses_lifecycle.py`。
- 真 upstream 脱敏 captures 与 fake parity：`tests/fixtures/anthropic_responses_bridge/` 和显式 opt-in PoC runner。

这些路径目前只是验收资产规划，不代表文件已经存在或 gate 已执行。

## 当前实现映射与尚未执行项

oracle 写完后仅为判断自动化落点读取了当前实现。以下事实不改变 oracle，也不是产品通过证据：

- `src/app/routes/anthropic.py` 当前将 upstream nonstream body 与 stream raw bytes直接返回，适合作为未来 HTTP route-level gate 的入口，但它本身不能证明 Responses→Anthropic 转换或 block buffering。
- `src/app/pipeline/executor.py` 当前集中持有 Anthropic hooks、approval、retry attempts 与 History，适合作为单一 lifecycle owner 的测试接缝。
- `src/app/streaming/buffered_retry.py` 当前只提供整流 `collect_with_limit()`，其被测对象不是完整 content block；不得用其存在性替代 block-level commit gate。
- `src/app/routes/responses_ws.py` 当前拥有原生 Responses WS route 的独立 approval／History；Anthropic bridge 若使用 WS upstream，验收必须证明它只复用 transport client，而不复用这条 route lifecycle。

本次没有运行候选实现测试、mutation 或真 upstream PoC。原因不是成本或 YAGNI，而是本次唯一授权产物是本规范，且尚未指定已实现的 bridge 候选与可写验证资产位置。上述全部 oracle 均保留为必需项，没有因当前代码尚缺接缝而删除或降级。

## 最终放行清单

放行报告必须逐项列出每个gate的candidate commit、绑定Spec SHA-256／章节、执行层级、正确样本结果、缺陷注入结果、失败原因核对、`LIVE-CANARY`结果、SDK前raw capture provenance、`LOCAL-FAULT`结果，以及未验证项。最终判定规则如下：

- 任一正确样本红：`BLOCKED`。
- 任一缺陷注入后仍绿，或因非目标原因变红：`BLOCKED`。
- 任一 gate 的 policy expected 未绑定当前冻结Spec、或仍未裁决：该项`UNVERIFIED`；不得由实现选择expected，也不得把未决本身写成实现缺陷。
- 任一可确定`LIVE-CANARY`未运行、fake无SDK前raw provenance、依赖的`CAPTURE-CORPUS`缺失／过期，或必需`LOCAL-FAULT`未运行：受影响项及整体基础合同为`UNVERIFIED`，不是`BLOCKED`。不可控真上游异常没有在本轮自然出现不构成缺陷，也不要求每轮重现。
- 任一no-dup/no-loss/order、连续前缀commit、sink delivery-uncertain、error terminal、cancel cleanup、History exactly-once不变量未获得route-level实证：`UNVERIFIED`；若实证显示违反则`BLOCKED`。
- 只有所有已决required项都具有可复现实证时：基础合同`PASS`。未启用且未裁决的低概率扩展保持`UNVERIFIED`，不借机扩张required范围；其已冻结最小止血默认行为必须通过。

**当前验收规范状态：`FINALIZED_ACCEPTANCE_ORACLE`（该字面量的读法见文首「本规范状态」条的 2026-08-24 说明：只表示本轮对账已完成，不表示本文封版）；候选产品及完整 bridge verdict：`UNVERIFIED`。本轮只按 current Spec `5e362822…` 与空 reasoning 独立裁决澄清NS-03的三条正交断言：absent／empty仍为恰好一个bare marker block、bare marker不得伪造`encrypted_content`、non-empty encrypted-only payload必须value-exact no-loss；其他expected不变。`reports/260807-review-acceptance-empty-reasoning.md` 已对本次bytes给出0 blocker／0 major／0 minor，故恢复最终标记；该文档checkpoint不构成产品符合性证据。候选产品尚未经过本规范的完整验收；基础 integration 的 `PASS` 不等于全规格通过。**

## 评审问题处置表

**处置总状态：`FINALIZED_ACCEPTANCE_ORACLE`。** 来源：首轮`reports/review-bridge-acceptance.md`、独立复评 R2 `reports/260806-review-bridge-acceptance-r2.md`、独立复评 R3 `reports/260806-review-bridge-acceptance-r3.md`、独立最终复评 R4 `reports/260806-review-bridge-acceptance-r4.md`、独立最终复评 R5 `reports/260806-review-bridge-acceptance-r5.md`、独立最终定向复评 R6 `reports/260806-review-bridge-acceptance-r6.md`、Acceptance 独立终审 R7 `reports/260807-review-bridge-acceptance-r7.md`、Architecture 用户裁决矩阵独立终审 `reports/260807-review-architecture-decision-matrix.md`、正式文档 merged-state 最终评审 R2 `reports/260807-review-docs-merged-r2.md`、carrier 双格式 Spec 定向评审 `reports/260807-review-spec-carrier-dual-format.md`、空 reasoning 独立裁决 `reports/260807-arbitrate-empty-reasoning.md`，以及空 reasoning 定向独立复评 `reports/260807-review-acceptance-empty-reasoning.md`。最新复评绑定本轮NS-03修订候选bytes并给出0 blocker／0 major／0 minor，故本规范恢复最终标记。以下修订绑定current Spec `5e362822…`与`POLICY-MANIFEST-v1`；没有以Architecture提案、官方consumer宽松行为、基础integration结果或候选实现反向创造产品政策。

| ID | 级别 | 原发现 | 处置 | 修订落点与关闭依据 |
|---|---|---|---|---|
| B1 | blocker | oracle宣称完整，但expected受未裁决政策影响 | **采纳并关闭** | “状态与判定”绑定最新Spec SHA-256；required gate写死route／字段矩阵／strict malformed args／no-revive／post-commit partial failure／普通per-request aggregate＋global reservation与拒绝新admission最小止血；未来未冻结扩展只记`UNVERIFIED` |
| B2 | blocker | 必需真上游异常不可按需制造，`PASS`永久不可达 | **采纳并关闭** | 校准拆为`LIVE-CANARY`、`CAPTURE-CORPUS`、`LOCAL-FAULT`；每轮live只要求确定性触发，不可控异常由版本化corpus＋本地注入覆盖，缺证据为`UNVERIFIED`而非假缺陷 |
| M1 | major | signature producer→consumer可能共享codec而同源全绿 | **采纳并按双格式合同继续关闭** | REQ-05分别固定current Spec项目主v1 exact bytes与`copilot-api-js@8d5c861…`合法compatibility vectors，执行producer-only／consumer-only变异，并要求“项目exact→producer”“静态项目vectors→consumer”“固定upstream bytes→consumer”“Responses corpus→normalizer”四链provenance；共享helper同步变异不算有效控制 |
| M2 | major | “完成即立即可见”与semantic order冲突 | **采纳并关闭** | STR-02把“立即”限定为从最早未提交位置开始的连续已完成前缀；新增A未完成、B先完成时零写入，A完成后按A、B提交的正负控制 |
| M3 | major | 漏掉完整batch sink partial-write／ack不确定 | **采纳并关闭** | 新增REL-03B，在response-start、首batch、block多个byte offset与terminal注入短写／RST；要求`delivery-uncertain`、禁止重发与success terminal并核对客户端bytes和代理认知 |
| M4 | major | raw capture可能位于产品SDK之后而与实现同源 | **采纳并关闭** | 校准总则及CAL-01～03强制SDK／retry／parser之前的独立raw HTTP／WS recorder，记录完整provenance、关闭自动retry并把SDK结果降为第二条兼容观察 |
| M5 | major | 官方SDK兼容性不能独自定义strict grammar | **采纳并关闭** | CAL-04以冻结grammar state machine判严格合法性，CAL-05单独验证官方SDK兼容；SDK宽松接受非法feed不得覆盖strict verdict |
| R2-M1 | major | CAL-04引用的冻结grammar table／fixture不存在且未绑定独立来源 | **采纳并关闭** | CAL-04内嵌`CAL-04-GRAMMAR-v1`完整最小表，绑定`anthropic-version: 2023-06-01`、官方streaming／thinking文档URL与读取日期，冻结5类最小正向fixture及逐项负向变异；未来fixture路径明确标为规划且尚不存在，落地后必须绑定内容hash并与本文表逐行等价 |
| R2-M2 | major | 移除16 MiB专门gate时漏掉普通per-request aggregate buffered-bytes gate | **采纳并关闭** | REL-06新增配置化request/global两级预算、跨多个普通block与resident owner的request聚合charge／wait／release／capacity终态、其他请求隔离和两级可观测计数；分别注入global-only与single-block／16 MiB分支两种相反缺陷，仍禁止任何16 MiB语义边界 |
| R3-M1 | major | CAL-04允许多个`message_delta`及`message_start`前／open block中的`ping`，违反冻结 producer／commit 合同 | **采纳；R4证伪旧关闭后转R4-M1最终关闭** | R3修订已关闭duplicate `message_delta`、pre-start与open-block `ping`，但错误保留了紧随`message_start`的`ping`；R4-M1继续收紧首批与零content batch边界，故不沿用R3的旧关闭声明 |
| R3-m1 | minor | 当前 HEAD 声明陈旧 | **采纳并持续关闭** | “状态与判定”已用本次同一shell的物理root／branch／HEAD gate更新current `main`为`80bc8f252b46c511f428af1d97159a5980ee9dc9`；不再把历史编写基线写成当前状态 |
| R3-m2 | minor | 容量摘要只写global reservation，与REL-06的per-request aggregate gate冲突 | **采纳并关闭** | 行为oracle摘要同步为普通per-request aggregate＋global reservation／backpressure，并继续明确不设16 MiB专门产品／架构阈值 |
| R4-M1 | major | `message_start`后、首个完整block提交前及零content terminal batch内仍允许`ping` | **采纳行为修订；R5证伪旧控制后转R5-M1最终关闭** | CAL-04已改为batch-aware grammar并禁止两个内部瞬态中的`ping`与旁路body write；但R4修订把`[message_start]`单独拆成首批，导致目标`ping`mutation不可达。R5-M1改用完整单batch目标fixture并把split-batch另立控制轴，故不沿用R4的旧控制关闭声明 |
| R4-M2 | major | current Spec／Architecture hash漂移，旧policy对账和`READY_FOR_FINAL_REVIEW`不可沿用 | **采纳policy manifest；R5证伪旧同快照绑定后转R5-M2最终关闭** | R4修订已建立`POLICY-MANIFEST-v1`及七域对账，但Architecture随后修改了ADR-BRIDGE-04分类并改变hash。R5-M2按current Architecture重做参考边界对账与同快照绑定，故不沿用R4的旧hash关闭声明 |
| R5-M1 | major | 两条`ping`负fixture先因拆分`message_start` batch失败，放宽目标`ping`转移也不能转绿 | **采纳并关闭** | CAL-04把首content与零content的`ping`fixture改为各自单一完整batch，除目标`ping`转移外所有字段、envelope、terminal与batch规则合法；split-batch另用两条无`ping`fixture及独立mutation。每个单侧放宽都必须先使目标fixture转绿，再使外层mutation gate因非法fixture被接受而红，并在恢复后复跑合法正样本为绿 |
| R5-M2 | major | Architecture hash再次漂移，route manifest仍把ADR-BRIDGE-04误写为Architecture待确认项 | **采纳并关闭** | 在与current Spec相同的最终输入快照重读Architecture，复核其ADR-BRIDGE-04只承载Spec已决的unknown capability fail-closed，不把typed kernel、History receipt owner或其余待确认ADR提升为expected；Spec hash复核为`a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，Architecture hash更新为`7bd98a384ccb313f2e72a598dc876766a1044a9bfcef4685ba09412895ea7679`，route manifest同步声明Architecture不产生expected |
| R6-FINAL | final review | R6 定向复核 R5 的 2 个 major，并检查 current Spec／Architecture 同快照绑定与非规范参考边界 | **采纳最终 verdict 并定稿** | R6 报告为 0 blocker／0 major，确认 acceptance oracle 可定稿；该结论只定稿验收 oracle，不是候选产品符合性证据。候选产品及完整 bridge 仍为`UNVERIFIED`，基础 integration 的`PASS`不等于全规格通过 |
| ARCH-MATRIX-FINAL | architecture review | Architecture 收敛为仅含 `D-ARCH`／`D-MIGRATION` 两项未接受的用户裁决，并把ADR-BRIDGE-02～06归入已决Spec输入与历史承载记录；需确认current Architecture不会反向改变Acceptance expected | **采纳历史终审输入；current carrier漂移由Spec覆盖** | `reports/260807-review-architecture-decision-matrix.md` 为0 blocker／0 major，其终审快照Architecture hash为`6de919d…`。Current Architecture为`c6088a2d…`且仍非行为oracle；其block／capacity／route／retry／delivery／History接缝可作参考，但ADR-BRIDGE-06旧upstream-only carrier已被current Spec双格式重裁覆盖，明确不得进入REQ-05／NS-03 expected |
| R7-FINAL | final review | R7 复核 Spec／Architecture hash、七域manifest、ADR-BRIDGE-02～06非扩张边界及oracle／产品状态分工 | **采纳终审 verdict；明确绑定历史快照** | `reports/260807-review-bridge-acceptance-r7.md` 为0 blocker／0 major，允许其绑定的current Acceptance提交；其Architecture输入为`6de919…`。该报告仍是最近一次Acceptance独立终审，但不覆盖随后仅涉及Architecture current review provenance／状态与处置表的`c6088a…`变化，也不构成产品符合性证据 |
| MERGED-R2-M1 | merged-state major | Architecture 已记录裁决矩阵终审0／0，Acceptance却仍以旧R6／R7绑定快照作为current状态依据，造成current review provenance矛盾 | **历史修订已关闭；本轮不沿用旧内容结论** | 旧轮曾绑定Spec `a193da…`与Architecture `c6088a…`并确认当时expected不变。本轮Spec已变为`5e362822…`，故重新执行七域内容对账：carrier expected改变，其他expected不变；旧轮“全部不变”与最终状态不得沿用，产品继续`UNVERIFIED` |
| D4-R2-SPEC-REVIEW | targeted spec review | 用户最新双carrier重裁是否充分冻结项目主v1、upstream合法主路径compatibility、识别顺序、最小止血与一item一block／no-loss | **采纳0／0 verdict；只放行Spec输入** | `reports/260807-review-spec-carrier-dual-format.md` SHA-256为`1d51e1a8dde27493503adb9701544ef8e35b75404420a4516732d06074addd05`，blocker 0、major 0、minor 0；该报告允许current Spec恢复`FINALIZED`，但不替代Acceptance新bytes复评或产品实现证据 |
| ACCEPTANCE-DUAL-CARRIER-REREVIEW | targeted acceptance review | 新Acceptance是否忠实把七域manifest、REQ-05、NS-03、状态与provenance改为双格式合同，并保持其他expected不变 | **采纳0／0 verdict并关闭** | 独立复评绑定READY候选SHA-256 `787b5c386dd6c623d66e47e2c26d2b84bb605db66dc0db97a6ee9dc1a2379afb`，核对current Spec／Architecture／carrier评审输入、七域manifest、项目exact vector、upstream合法兼容、最小止血、一item一block／no-loss及旧口径残留，结果blocker 0、major 0；随后只恢复状态与本处置记录，产品保持`UNVERIFIED` |
| EMPTY-REASONING-ARBITRATION | current targeted clarification | NS-03中“empty payload且无summary不凭空制造可恢复block”被误读为零block，与FINALIZED Spec的一item一block、bare marker与non-empty encrypted-only no-loss合同冲突 | **采纳裁决、修订并经0／0定向复评关闭** | `reports/260807-arbitrate-empty-reasoning.md` SHA-256 `8f12e0703a925a511fad3188f54a89a7a1d6056096fde05520a1c21cb5e6c568`冻结唯一解释：absent／empty必须生成恰好一个`thinking=""`＋项目bare marker block，echo恢复`summary=[]`且不添加`encrypted_content`；non-empty encrypted-only必须生成payload carrier并value-exact no-loss。`reports/260807-review-acceptance-empty-reasoning.md` 绑定修订候选 SHA-256 `a4b9e31fd1d237ca8038573320809305e0ac567eb2d56d5c967716cc8cdbfac8`，报告 SHA-256 `5d9ad16e371f14544dfe2d5b7e84070cf8e851aa73343b6893d344b75cd1f623`，结论为0 blocker／0 major／0 minor；Acceptance恢复`FINALIZED_ACCEPTANCE_ORACLE`，产品保持`UNVERIFIED` |

### 用户最新约束的额外落实

- 低概率扩展只验证当前冻结的最小止血默认行为，不为malformed repair、multimodal tool result、foreign thinking forwarding或公开model suffix建立扩展能力gate。
- REL-06不建立`>16 MiB`专门gate、fixture类别、metric阈值或状态分支；容量只验普通per-request aggregate／global reservation、backpressure与拒绝新admission的最小止血。
- REL-06同时验证Spec已冻结的普通per-request aggregate buffered-bytes预算；该预算跨多个resident owner聚合，不以单block大小或16 MiB为语义边界。
- REQ-05以current Spec项目主v1 exact bytes作为默认producer oracle，以`copilot-api-js@8d5c861…`的v1合法canonical主路径／bare／legacy作为consumer compatibility oracle；验证authoritative `.done`、strip、识别顺序、unknown／foreign／代表性malformed最小止血及producer-only／consumer-only变异，不要求全malformed Node byte-exact。
- REQ-05与NS-03共同证明一Responses reasoning item一Anthropic thinking block、普通模式encrypted-only no-loss和多item不聚合／不错配；显式strip保持block cardinality并记录有意payload removal。
- CAL-04服从冻结Spec中比官方consumer合同更严格的producer／commit边界：首个content成功批次必须把`message_start`与首个完整block envelope同batch提交，零content成功必须提交无`ping`的完整terminal batch；只有首个完整block已接受后的batch边界允许`ping`。成功路径恰好一个`message_delta`和一个`message_stop`；官方SDK若接受更宽松feed，不得覆盖strict verdict。
- CAL-04的`ping`转移与batch完整性是两个独立控制轴：目标`ping`fixture始终保持单一完整batch，split-batch fixture始终不含`ping`；任何mutation只有在目标fixture先转绿、外层mutation gate再因非法接受而红、恢复后合法正样本仍绿时才算有效正控。

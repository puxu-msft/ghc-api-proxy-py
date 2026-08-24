# Anthropic Messages ↔ OpenAI Responses bridge 独立验收规范

> Current authority：本文件当前状态是 `LIVING_ACCEPTANCE_ORACLE`——它与所验收的 [spec.md](spec.md) 同为活文档，随 Spec 条款修订同步更新，候选产品及完整 bridge 为 `UNVERIFIED`。**判据以 [spec.md](spec.md) 的当前内容为准**，按 `.dev` 提交锚定（基线 `.dev@66811b1`）；本文此前钉的那两个 2026-08-08 内容哈希已于 `5e94b75` 之后失配，2026-08-24 一并撤下，历史事实见 [reports/260807-acceptance-review-disposition.md](reports/260807-acceptance-review-disposition.md)。Current Architecture 已与 Spec 的“双格式 carrier”方向一致，但仍是非规范提案，不产生 Acceptance expected。下文出现的旧 hash、`upstream-only`、`READY_FOR_FINAL_REVIEW`、“待复评”或 R2～R7 verdict 只属于历史处置记录，均被本段 current 声明覆盖，不是 current gate。

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

## 证据分级：本项目用哪几层

下面每条判据都标了它要求的证据层。**每一层都写明了它不能冒充什么**——这是分级唯一的用途，否则「用 fake 测过了」会被读成「已验证」。

| 标签 | 是什么 | 不能冒充什么 |
|---|---|---|
| `AUTO-UNIT` | 纯转换、状态机或 property-based 测试，无网络可跑 | 不证明接线 |
| `AUTO-COMPONENT` | 真实 pipeline owner + fake upstream + History／hooks／approval／tokenization | 不证明 wire 字节 |
| `AUTO-HTTP` | 真实 ASGI route 与真实字节流消费 | 不证明上游真实行为 |
| `AUTO-WS` | 真实本地 WebSocket client/server、有限 queue 与 close code | 同上 |
| `AUTO-SOCKET` | 经 loopback socket 注入分帧、RST、half-close、慢读与取消 | **不得用直接调用 async generator 代替真实 transport 流控** |
| `LIVE-CANARY` | 每轮可确定调用的真上游正常请求，以及上游官方提供的触发器 | **不得要求托管上游在本轮偶发 5xx／truncation／特定 close code** |
| `CAPTURE-CORPUS` | 真实历史事件或官方 fixture，经 SDK 前 raw recorder 捕获、脱敏、版本化 | **不冒充本轮 live 事件** |
| `LOCAL-FAULT` | 在 loopback server／TCP proxy／sink fault injector 里确定性制造 truncation、RST、partial write、backpressure | **只证明本地处理机制，不冒充真实上游异常的 provenance** |

判据本身怎么写才不会真空通过（双向控制、判据独立性、异源 oracle），见 skill `writing-acceptance-criteria-that-can-fail`。

**三个状态词的判据**（原定义随「状态与判定」删去，此处只留判据）：

- `PASS`——正确样本绿，且该 gate 的缺陷注入确实变红、红的原因出自目标不变量。
- `BLOCKED`——正确样本红，或注入后仍绿，或已证实存在丢失／重排。**这是实现缺陷。**
- `UNVERIFIED`——证据未取得、corpus 过期、或政策未裁决。**不得误报成实现缺陷，也不得折算为通过。** 这两个方向都会错：把没跑过写成有缺陷，和把没跑过写成通过，一样是假信息。

## Spec 章节 → 本文件哪几条 gate

本文的存续条件是「随 Spec 条款修订同步更新」。下表是它的执行入口——Spec 某节改了，回来重做对应的 gate。（原 `POLICY-MANIFEST-v1` 的对账结论与身份门已删，只留这份映射。）

| Policy 域 | Spec 规范来源章节 | 对应 gate |
|---|---|---|
| route | Route selection 与 model capability 契约、route precedence、Route 真值表、Compatibility 契约 | `REQ-01`、`TR-HTTP`、`TR-WS`、`TR-PARITY` |
| request | Request conversion 契约、双向字段处置矩阵、Reasoning 与 signature 契约 | `REQ-02`～`REQ-06` |
| response | Response conversion 契约、Non-stream contract、SSE／WS envelope 契约、Usage 契约、Error 契约、Header 契约 | `NS-01`～`NS-05`、`STR-01`、`STR-04`～`STR-05` |
| buffering | Downstream Anthropic SSE、Block-level buffering 与 commit 契约、Ordering／no duplication／no loss 契约 | `STR-02`～`STR-03`、`REL-03B`、`CAL-04` |
| retry | Retry ownership 与 delivery semantics、唯一 owner、推荐 retry 边界 | `REL-01`～`REL-04` |
| lifecycle | Approval／hooks／History／tokenization 契约、Shutdown／cancel 部分 | `LIFE-01`～`LIFE-04`、`REQ-06`、`REL-05` |
| limits | Backpressure／memory-only 政策／Limits 与非功能要求 | `REL-06` |


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
> 本表是版本化的冻结语法 `CAL-04-GRAMMAR-v1`，其 `ping` 转移行、下面「不得把`ping`放在首批之前」那句、以及已闭评审行 R3-M1／R4-M1／R5-M1（**已于 2026-08-24 移出本文件**，原文见 [reports/260807-acceptance-review-disposition.md](reports/260807-acceptance-review-disposition.md)；那份是点时记录**不得修改**，升版时在本文件另写一条 `CAL-04-GRAMMAR-v2` 的裁决记录）（它们正是历次裁 `ping` 位置的记录，其中 R4-M1 曾采纳过与本次同向的修订、后被 R5 推翻）需要作为**一次独立切片**一起重做并升版，而不是就地改一行。**该语法目前只存在于文档，主仓测试中没有实现**（`rg CAL-04 tests/` 无命中），因此不阻塞运行时行为。

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

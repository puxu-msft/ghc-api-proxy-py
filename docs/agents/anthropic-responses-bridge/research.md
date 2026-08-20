# Anthropic Messages ↔ OpenAI Responses bridge 可追溯研究

## Verdict

**结论：可进入规格与实施计划阶段，但不可把任一参考实现整体照搬。** 已独立核验的最佳方向是：能力驱动的 upstream leg 决策、Anthropic↔Responses 单跳 direct bridge、协议域隔离的 opaque reasoning carrier、按 item／block identity 分桶的流状态机、独立于翻译器的 block-level delivery owner，以及以 commit frontier 驱动的 retry／error 分类。`copilot-api-js` 是机制覆盖最完整的主参考，但它当前仍存在 request block 顺序重排、tool-name sanitization 未接入、non-stream reasoning carrier 丢失／错配等缺陷；参考仓库也各有私有协议、默认值、非流接缝或事件覆盖缺口。

**不得推翻的产品边界：block-level buffering 是基础能力，下游不提供 token／event 级 live streaming 体验。** 这是本次任务的一手用户裁决，不是从临时报告推导出的仓库事实。所有下文提到的 SSE parser、delta translator、keepalive、retry 与 transport streaming 都只描述 upstream 读取和内部状态推进；它们不得被解释为恢复 live downstream flush。upstream protocol leg 与 downstream delivery 粒度必须保持正交。

**范围结论：不因 ROI、成本或 YAGNI 删除任何已接受能力。** direct request／non-stream response／stream response、reasoning、tool use、usage、error、retry、cancellation、HTTP／WS 一致性、History／hooks／approval 接缝和 block-level delivery 都应进入后续规格与验收映射；实施顺序可以分阶段，范围不能静默缩水。

## 目标项目约束

以下四项均是本轮用户对目标项目的直接裁决，不是主 upstream 或 refs 的事实，也不改变本文对固定 commit tree 的核验结论。

1. **Anthropic content block 是 block-level buffering 与 commit 的交付单元。** parser 可以按上游协议维护更细事件状态，但 delivery frontier 以完整 Anthropic content block 为准。
2. **Block buffer 没有 16 MiB 或其他单 block 专属阈值。** buffer 与 carrier 是普通内存对象，服从 per-request `client_delivery.buffer_cap_bytes`、有界队列与背压；不建立按单 block 大小触发的专门状态、fixture、metric threshold、spill 或 overflow-to-live 路径。进程级只有等待式在途请求上限 `proactive_rate_limiter.max_inflight`，超限请求排队等待而不被拒绝；若真实运行证据要求 victim selection、额外终止政策或其他全面资源设计，必须先询问用户并取得裁决。
3. **Anthropic `/v1/messages` bridge 的默认 route。** 仅对该 bridge：无 endpoint override 时，resolved model 同时支持 Messages 与 Responses 则选择 Messages，Responses-only 模型选择 Responses，Messages-only 模型选择 Messages，能力未知则 fail closed。原生 OpenAI Responses 公共入口继续使用其 Responses upstream；不得从该 bridge 的 route precedence 推导其改走 Messages。显式 override、能力例外与 fallback 的优先级仍须在规格中冻结。
4. **Opaque reasoning carrier wire 固定与 `copilot-api-js` v1 byte-compatible。** 目标 producer／consumer 必须兼容固定 upstream 的 ASCII prefix `copilot-api:synthetic-reasoning:v1:`、UTF-8→unpadded base64url payload、bare prefix、legacy sentinel、strip option 与 malformed 边界；不得另造私有 delimiter、schema、HMAC 或其他 carrier。该裁决只冻结 carrier wire 与 echo／strip 互操作，不把 upstream non-stream 的跨 item summary 聚合、last-ciphertext-wins 或 encrypted-only 丢失提升为目标语义。

## 证据口径

### 状态标签

- **已独立核验**：本轮在目标主树 gate 后，直接读取固定 Git commit tree 或已 gate 的参考仓库源码；结论不依赖 agent 的可信度。
- **仅 agent 报告待核验**：只由输入调查报告提出，本轮未完成独立源码／运行时闭环；不作为设计定论，只保留为后续核验项。
- **未运行验证**：本轮没有运行 Bun、Python、Go 或 .NET 测试，也没有对真实 upstream 做 live-wire replay；“存在测试源码”不等于“本轮测试通过”。

### 目标主树 gate

- 目标仓库：`/home/xp/src/ghc-api-proxy-py`。
- 固定 HEAD：`47d9ef101c4b81ac70d805b1da157b34d021d33d`。
- 本轮每次 shell 调用都在同一调用内校验 Git top-level 与该 HEAD。主树原有其他未跟踪文件，本轮唯一写入是本文。

### 来源仓库与固定快照

| 角色 | Repo | 固定 HEAD | 本轮证据状态 |
|---|---|---|---|
| 主 upstream | `/home/xp/src/copilot-api-js` | `8d5c861c2e079b92401dd8ccd49695a363d078fe` | 已独立核验；仓库工作树有其他会话改动，因此只读 commit tree，不采信工作树差异 |
| Python 近似参考 | `/home/xp/src/refs/ghc-api-py` | `8d064a27308ed249da8c9ce7ecc54c89ee68c151` | 已核验 repo gate；仅抽查路由与流处理 |
| TypeScript direct bridge | `/home/xp/src/refs/caozhiyuan-copilot-api` | `6b97876927b7209a1e0f498e81927b32cc443e52` | 已核验 repo gate；仓库有未跟踪目录，结论只引用 tracked source |
| .NET typed-IR bridge | `/home/xp/src/copilot-api-js/refs/hooyoo-copilot-bridge` | `2032fdd782aa1166eea0286977c59ab93eb5cab2` | 已核验 repo gate；部分关键接缝仅报告待核验 |
| VS Code Copilot Chat upstream | `/home/xp/src/copilot-api-js/refs/vscode-copilot-chat-upstream` | `d62bf252c865fbf41550ce3076e918c52f0bced7` | 已独立抽查 Responses adapter 与 stream processor |
| GitHub Copilot Chat 同构参考 | `/home/xp/src/copilot-api-js/refs/github-copilot-chat` | `6ad6a351c60c8dab1b9a1e620ef9156b28005893` | 已核验 repo gate；未逐项复核，作为同构线索 |
| Go Chat→Responses 状态机 | `/home/xp/src/refs/CLIProxyAPIPlus` | `0c48ef58e0d37220367401b8f7cf689e2e50a701` | 已独立抽查状态、terminal 与并行 tool 分桶 |
| Go direct bridge | `/home/xp/src/refs/awsl-maxx` | `03d018fac3645b14d7b6d51b223b2148227c8992` | 已独立抽查双向注册与 stream coverage 缺口 |

### 临时输入的角色

以下七份文件只作为调查线索和来源清单，不是本文结论的长期权威：`/home/xp/src/ghc-api-proxy-py/docs/tmp/upstream-route-decision.md`、`/home/xp/src/ghc-api-proxy-py/docs/tmp/upstream-request-conversion.md`、`/home/xp/src/ghc-api-proxy-py/docs/tmp/upstream-response-conversion.md`、`/home/xp/src/ghc-api-proxy-py/docs/tmp/upstream-recent-changes.md`、`/home/xp/src/ghc-api-proxy-py/docs/tmp/refs-python-bridges.md`、`/home/xp/src/ghc-api-proxy-py/docs/tmp/refs-typescript-bridges.md`、`/home/xp/src/ghc-api-proxy-py/docs/tmp/refs-go-bridges.md`。本文的已采纳结论均在下文给出固定 repo+HEAD 和绝对 source `file:line` 或 commit；临时文件删除后，本文仍可独立阅读。

## 目标仓当前事实与能力缺口

1. **[已独立核验] Anthropic Messages 当前固定走 Anthropic client，没有 upstream leg resolver。** `/home/xp/src/ghc-api-proxy-py/src/app/routes/anthropic.py:53-120` 直接调用 `client.execute`，stream 分支把 `upstream.aiter_raw()` 经 idle timeout、usage tap 和 byte passthrough 交给 SSE response；该路径没有 Anthropic→Responses request converter 或 Responses→Anthropic response converter。证据锚定目标 HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d`。

2. **[已独立核验] OpenAI Responses HTTP 当前也是协议内直通。** `/home/xp/src/ghc-api-proxy-py/src/app/routes/openai.py:17-39` 的共享 `_response` 对成功 stream 直接转发 raw bytes，`/home/xp/src/ghc-api-proxy-py/src/app/routes/openai.py:80-112` 的 `/responses` 只做 approval、History start 和 `client.responses`；没有跨协议 bridge。证据锚定目标 HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d`。

3. **[已独立核验] 现有 buffering primitive 不是 block-level delivery。** `/home/xp/src/ghc-api-proxy-py/src/app/streaming/buffered_retry.py:4-18` 的 `collect_with_limit` 只把整个 byte stream 收进一个 `bytearray` 并执行 cap 检查；它没有 SSE grammar、block boundary、commit ledger、attempt replay suppression 或 downstream owner。证据锚定目标 HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d`。

4. **[已独立核验] 现有 Responses accumulator 不足以支持 terminal completeness 或 block commit。** `/home/xp/src/ghc-api-proxy-py/src/app/openai/responses_stream_accumulator.py:5-24` 只累计 `response.output_text.delta`、最近 `response` 和 `usage`，没有 output item identity、function arguments、reasoning、unknown event、terminal completeness 或 synthetic provenance。证据锚定目标 HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d`。

5. **[已独立核验] retry owner 已在应用层，但当前不理解 delivery commit phase。** `/home/xp/src/ghc-api-proxy-py/src/app/upstream/client.py:54-82` 为 OpenAI／Anthropic SDK 设置 `max_retries=0`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/executor.py:165-190` 建立应用层 `RetryCoordinator`，但 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/executor.py:190-278` 只在收到非成功 HTTP response 后决策，没有 pre-commit／post-commit stream error 合同。证据锚定目标 HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d`。

6. **[已独立核验] server-tool 不能因 bridge 引入而被“顺手恢复”。** `/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/tool-use.md:3-12` 明确当前只支持 client-executed tools，不执行、合成、过滤或降级重试 Anthropic 原生 server tools；`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/request-pipeline.md:24-36` 同样声明 server-tool rejection 没有专用 retry。direct bridge 可以定义“不伪造、显式降级、可观测”的跨协议语义，但若要改变原生 server-tool 产品边界，必须另行取得用户裁决。证据锚定目标 HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d`。

## 主 upstream 机制

### 1. 路由决策与 transport／delivery 解耦

**[已独立核验] 机制。** `copilot-api-js` 把模型名规范化、显式 leg override、模型能力检查与 protocol leg 选择集中在 pipeline S2：`/home/xp/src/copilot-api-js/src/lib/models/resolver.ts:185-209` 解析 `@cc`／`@responses`／`@messages`，`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:67-91` 按 client format 分派，`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:201-247` 对无后缀 Anthropic 依次选择 direct Messages、Responses、Chat Completions，`/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts:320-371` 在单一 S2 点固定 target endpoint 后才调用 outbound translation。证据锚定 upstream HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

**可移植项。** Python 侧应分成 `resolve model target → decide protocol leg → resolve bridge cell → prepare transport wire`，不能在 route handler 里用模型名前缀散落判断。leg decision 只决定 upstream 协议；HTTP／WS transport 与 downstream block delivery 是后续独立维度。

**不可照搬项。** `/home/xp/src/copilot-api-js/src/lib/models/endpoint.ts:45-59` 对 `supported_endpoints` 缺失／index miss 的 legacy-true 语义，以及 `/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:237-241` 的 Google force-CC 规则属于该 upstream 的产品兼容策略，不应未经目标规格确认直接复制。

### 2. 单跳 direct bridge 与按协议对注册

**[已独立核验] 机制。** `/home/xp/src/copilot-api-js/src/lib/pipeline/cell-assembly.ts:187-237` 按 target endpoint 选择 leg，再按 `(clientFormat, targetEndpoint)` 组装 cell；`/home/xp/src/copilot-api-js/src/lib/pipeline/hub-translate.ts:139-205` 把 Anthropic→Responses 绑定到独立 bridge，而不是经 Chat Completions canonical shape；`/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/openai-responses-cell.ts:77-119` 调 direct translator 并进入 Responses wire preparation。证据锚定 upstream HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

**可移植项。** 每个协议对维护独立、纯函数化 request／non-stream response translator，并为 stream 建独立有状态 parser；共享层只提供 routing、context、delivery、retry 与 observability，不把 Chat Completions 当万能中间表示。

**不可照搬项。** 不应复制 TypeScript 的 CellAssembly 类型结构或二维表写法本身；目标是保留“协议对独立、共享编排不吞语义”的职责边界，而不是逐文件翻译语言结构。

### 3. Anthropic→Responses request 白名单映射

**[已独立核验] 机制。** `/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:113-168` 从零构造 `instructions/input/max_output_tokens/tools/tool_choice/reasoning/user/stream` 等 Responses 字段；`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:187-355` 显式转换 string／text／image／tool_use／tool_result／thinking；`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:362-479` 用表驱动处理 server tools、普通 tools 与 tool choice；`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:485-506` 将 thinking 配置映射为 reasoning。证据锚定 upstream HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

**可移植项。** 采用显式字段矩阵而不是 source object spread；保留 `tool_use.id ↔ function_call.call_id`、`tool_result.tool_use_id ↔ function_call_output.call_id`；Responses input 的 `function_call.id` 与 `call_id` 必须分开建模，不能用 `toolu_`／`call_` 伪造 `fc_` item id。该 upstream 对 fabricated item id 的历史修复可追溯到 commit `684761e4005fc380edec8eb7d7a27b768d6f550e` 和 backstop commit `a53ff7407f38275b7102764a45c57edaa75decae`；commit 归因来自 agent 报告，实施前仍应以 `git show` 复核补丁内容。

**已确认反例 A：顺序重排。** `/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:214-255` 会把 assistant text／reasoning 聚合后插到 tool calls 前，`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:278-306` 会把 user text／image 聚合后追加到 tool results 后；这不能作为 shape fidelity 的目标实现。目标 translator 应按连续 run flush，或由冻结规格明确允许的重排规则驱动。

**已确认反例 B：tool-name sanitizer 接缝。** `/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/openai-responses-cell.ts:88-113` 的 Anthropic→Responses S2 调 direct converter，而 S3 rewrite 返回空；`/home/xp/src/copilot-api-js/src/lib/openai/tool-name-sanitize.ts:183-224` 虽能同步 declaration、历史 function call 与 forced choice，却没有在该 cell 接线。目标实现必须让 tool definitions、历史 calls、results、forced `tool_choice` 和 response restore 共享同一 mapper，不能只修一个字段。

### 4. Responses→Anthropic non-stream response

**[已独立核验] 机制。** `/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts:157-236` 遍历 Responses output，把 message／refusal／reasoning／function_call／web_search_call 映射为 Anthropic content，并处理 failed status、content-filter side channel 与空 content；`/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts:242-317` 修复 tool arguments 并选择 stop reason；`/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts:339-352` 映射 usage。证据锚定 upstream HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

**可移植项。** output item 应按原序转换；function arguments 的畸形输入不能静默吞失，至少应形成 typed error 或保留 raw arguments 的可诊断降级；unknown item、content filter、failed terminal 和 usage 缺失都要有显式合同。

**已确认反例：reasoning carrier 聚合不对称。** `/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts:163-173` 累加所有 summary text，却只保留最后一个 `encrypted_content`；`/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts:210-219` 只有 summary 非空才生成 thinking block。因此 encrypted-only carrier 会丢失，多 reasoning items 会形成“聚合 summary + 最后 blob”错配。目标实现必须按 reasoning item identity 一对一保存 visible summary、opaque payload 与 provenance。

### 5. Opaque reasoning／thinking 的协议域隔离

**[已独立核验] 机制。** `/home/xp/src/copilot-api-js/src/lib/anthropic/synthetic-reasoning.ts:31-46` 为代理生成的 carrier 使用可识别版本前缀；`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:127-143` 只恢复本代理产生且可验证的 carrier，并对 foreign／unsigned thinking 记录 degradation 后丢弃。VS Code upstream 采用另一种域 gate：`/home/xp/src/copilot-api-js/refs/vscode-copilot-chat-upstream/extensions/copilot/src/platform/endpoint/node/responsesApi.ts:631-655` 只把 `rs` id 且含 encrypted payload 的 Responses reasoning 放回 Responses request。两个来源分别锚定 HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe` 与 `d62bf252c865fbf41550ce3076e918c52f0bced7`。

**可移植项。** visible thinking text、opaque continuation payload、item id、签发协议／模型域和 degradation reason 必须分字段；opaque payload 只能回送到签发它的协议域。目标 carrier wire 已裁决固定与 `copilot-api-js` v1 byte-compatible：沿用其 prefix、UTF-8→unpadded base64url、bare／legacy、strip 与 malformed 行为，不重开私有 carrier 设计。该 wire 兼容不改变目标按 reasoning item identity 一对一保存 visible summary、opaque payload 与 provenance 的语义要求。跨协议无法保真的内容应显式计数／记录，而不是伪装成普通 assistant text。

**不可照搬项。** `/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-translation.ts:103-145` 和 `/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-translation.ts:352-390` 使用 `encrypted_content@id`／`cm1#...@id` 私有字符串 carrier，并在空 summary 时生成固定 `Thinking...` 占位；这是客户端兼容策略，不是公共协议。其 delimiter、版本、来源域和空 id 语义不能直接成为本项目合同。证据锚定 HEAD `6b97876927b7209a1e0f498e81927b32cc443e52`。

### 6. Responses stream parser 与 block grammar

**[已独立核验] 机制。** `caozhiyuan` 的 `/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-stream-translation.ts:78-128` 保存 message start、block key、open blocks、delta presence 与 `output_index` 对应的 function-call state；`/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-stream-translation.ts:156-346` 处理 item added、reasoning／text delta、function arguments delta／done，并在 done-only 场景补最终参数；`/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-stream-translation.ts:460-490` 在 terminal 前关闭 blocks，再发 Anthropic terminal；`/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-stream-translation.ts:592-705` 用 `(output_index, content_index)` 或 `output_index` 绑定稳定 block。证据锚定 HEAD `6b97876927b7209a1e0f498e81927b32cc443e52`。

**可移植项。** parser 必须维护 `begin → delta* → done` grammar、稳定 block identity、done-only 补偿、terminal 前闭合、failed／EOF 的 honest terminal。解析器输出的是内部 block events；delivery owner 再决定何时向下游提交完整 block。

**不可照搬项。** 该 translator 的 default 分支直接返回空数组，未知事件无可观测性；固定连续空白阈值和 `Thinking...` 占位也属于项目策略。目标实现应区分 control、known-but-lossy 和 truly unknown，并为后两者留下结构化诊断。

### 7. Block-level commit、retry 与 exactly-once 前缀

**[已独立核验] 机制。** `/home/xp/src/copilot-api-js/src/lib/codec/anthropic/commit-boundaries.ts:1-24` 定义 Anthropic block／terminal boundary；`/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts:1335-1418` 在 boundary 上提交完整 block，并把错误终止纳入边界判断；`/home/xp/src/copilot-api-js/src/lib/pipeline/committed-blocks-ledger.ts:1-29` 记录已完整提交的 block；`/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts:1080-1260` 在 generation／flush 路径携带已提交事实和唯一 transform seam。证据锚定 upstream HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

**可移植项。** 将“parser 已识别完整 block”“delivery 已提交 block”“attempt 可否重试”分成三个事实。目标项目已裁决 Anthropic content block 是 block-level buffering 与 commit 的交付单元。pre-commit 失败可以重试未提交区间；post-commit 失败不得重放已提交 block，只能续接、发 canonical error，或按冻结合同终止。ledger 必须绑定 generation／attempt identity，并由唯一 downstream writer 使用。

**必须按用户裁决改造的部分。** upstream 主实现仍包含 live sink／逐帧路径；本项目不能复制“边解析边下游 flush”。目标结构应是 `upstream stream → protocol parser → block accumulator → commit predicate → delivery owner`，其中 commit predicate 只在完整 Anthropic content block 或 terminal/error block 上放行。buffer pressure 不得退回 live 直写，也不得引入磁盘 spill；16 MiB 或其他单 block 大小不是状态、测试或指标边界。buffer 只走 per-request `client_delivery.buffer_cap_bytes`、有界队列与背压；进程级只有等待式在途请求上限 `proactive_rate_limiter.max_inflight`，超限请求排队等待而不被拒绝，任何更全面的资源设计必须先询问用户。

### 8. Buffered merge 与 terminal repair

**[已独立核验] 机制。** `/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts:1218-1245` 在唯一 flush choke point 调 candidate-hosted transform；`/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/buffered-merge-reducer.ts:70-175` 先比较 terminal `response.output` 与已观察 items，只在不完整时 repair，并标记 synthetic provenance。证据锚定 upstream HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

**可移植项。** 完整上游事件必须先进入 history／diagnostics，再做面向客户端的 compaction 或 repair；normal terminal 不应被无条件重写；synthetic terminal 必须可观测。目标仓已有 accumulator 只能作为起点，需扩展为 item-level completeness oracle，不能仅按 text 拼接判断完整性。

### 9. Delivery owner、错误阶段与取消 provenance

**[已独立核验] 机制。** `/home/xp/src/copilot-api-js/src/lib/pipeline/delivery/session.ts:78-87`、`/home/xp/src/copilot-api-js/src/lib/pipeline/delivery/session.ts:354-478` 集中 delivery ownership 与 owner error；`/home/xp/src/copilot-api-js/src/lib/request/strategies/network-retry.ts:1-55` 只把连接错误及空 body upstream 499 归入一次有界 network retry；`/home/xp/src/copilot-api-js/src/lib/openai/upstream-ws-attempt.ts:152-179` 传播并解除外部 abort source，`/home/xp/src/copilot-api-js/src/lib/anthropic/client.ts:77-118` 区分 client abort 与 shutdown abort。证据锚定 upstream HEAD `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

**可移植项。** heartbeat、正常 block、terminal repair 与 error frame 必须共用一个 downstream owner；client disconnect、server shutdown、idle timeout、upstream reset 和 admission cancellation 必须保留 provenance。只有真实 client disconnect 可映射为 499；其它来源进入各自 retry／error／observability 合同。

## 异构参考交叉结论

### 已独立核验的可移植模式

1. **连续 run flush 保序。** `/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-translation.ts:147-253` 在 tool_result、tool_use 或 reasoning 边界前调用 `flushPendingContent`，避免把原本交错的 text／tool blocks 全部聚合到一侧。证据锚定 HEAD `6b97876927b7209a1e0f498e81927b32cc443e52`。

2. **`output_index` 只作流内关联，协议 id 作跨轮关联。** `/home/xp/src/copilot-api-js/refs/vscode-copilot-chat-upstream/extensions/copilot/src/platform/endpoint/node/responsesApi.ts:1196-1245` 用 `output_index` 建 tool state、累加 arguments 并在 item done 发布完成 call；`/home/xp/src/copilot-api-js/refs/vscode-copilot-chat-upstream/extensions/copilot/src/platform/endpoint/node/responsesApi.ts:631-655` 另用真实 reasoning id 控制跨轮回送。证据锚定 HEAD `d62bf252c865fbf41550ce3076e918c52f0bced7`。

3. **并行 tool 状态必须用复合 key 分桶。** `/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response.go:20-55` 为 message、reasoning、function 和 usage 分开建状态；`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response.go:281-305` 以 choice index + tool index 建 key；`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response.go:467-520` 分别累计 arguments 和 output index。证据锚定 HEAD `0c48ef58e0d37220367401b8f7cf689e2e50a701`。

4. **finish 与最终 terminal 分两阶段。** `/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response.go:229-242` 只在 `[DONE]` 且 `CompletionPending` 时发一次 completed，`/home/xp/src/refs/CLIProxyAPIPlus/internal/translator/openai/openai/responses/openai_openai-responses_response.go:520-611` 的 finish reason 先完成 items、置 pending，让晚到 usage 仍可进入 terminal。证据锚定 HEAD `0c48ef58e0d37220367401b8f7cf689e2e50a701`。

### 已独立核验的不可照搬项

1. **参考实现的逐 delta 输出与本项目裁决冲突。** `/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-stream-translation.ts:88-346` 收到 Responses delta 后立即生成 Anthropic delta；其状态机可作为 parser 参考，但输出必须改接 block accumulator，不能直接接 downstream sink。证据锚定 HEAD `6b97876927b7209a1e0f498e81927b32cc443e52`。

2. **Go direct Claude→Responses stream 不完整且事件名非标准。** `/home/xp/src/refs/awsl-maxx/internal/converter/claude_to_codex.go:239-278` 只处理 message start、text delta 和 message stop，并生成 `response.output_item.delta`／`response.done`；缺 reasoning、tool arguments、usage、标准 item added／done／completed。证据锚定 HEAD `03d018fac3645b14d7b6d51b223b2148227c8992`。

3. **Go Responses→Claude 使用单一全局 block index。** `/home/xp/src/refs/awsl-maxx/internal/converter/codex_to_claude.go:20-25` 的状态只有 `HasToolCall/BlockIndex/ShortToOrig`，`/home/xp/src/refs/awsl-maxx/internal/converter/codex_to_claude.go:147-279` 依次推进一个 index；它不能证明交错并行 items 的正确性。证据锚定 HEAD `03d018fac3645b14d7b6d51b223b2148227c8992`。

4. **参考默认值不是协议事实。** `/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-translation.ts:57-92` 固定 `temperature:1`、`parallel_tool_calls:true`、`store:false`、`reasoning.summary:detailed` 并抬高 `max_output_tokens`；`/home/xp/src/refs/awsl-maxx/internal/converter/claude_to_codex.go:150-167` 默认 reasoning effort 为 medium。除非目标规格另行接受，否则均不得复制。证据分别锚定 HEAD `6b97876927b7209a1e0f498e81927b32cc443e52` 与 `03d018fac3645b14d7b6d51b223b2148227c8992`。

### 仅 agent 报告待核验

1. **hooyoo non-stream raw Responses 泄漏风险。** agent 报告声称 `/home/xp/src/copilot-api-js/refs/hooyoo-copilot-bridge/src/CopilotBridge.Cli/Pipeline/Strategies/Codex/CopilotResponsesStrategy.cs:23-190` 对非 SSE success／error 只缓存原始 Responses bytes，而 `/home/xp/src/copilot-api-js/refs/hooyoo-copilot-bridge/src/CopilotBridge.Cli/Pipeline/Adapters/ClaudeCode/ClaudeCodeOutboundAdapter.cs:32-38` 的 `AdaptBufferedAsync` 是 identity，可能让 Anthropic client 收到 raw Responses JSON。本轮只独立确认这些符号和调用点存在，未完整读取两侧实现形成闭环，因此该项不能作为既成事实；后续必须补 `stream:false` 与“upstream 未返回 SSE”的端到端探针。来源 repo HEAD `2032fdd782aa1166eea0286977c59ab93eb5cab2`。

2. **hooyoo typed provider-extension bag 的完整保真范围。** agent 报告指出 `/home/xp/src/copilot-api-js/refs/hooyoo-copilot-bridge/src/CopilotBridge.Cli/Models/Common/ProviderExtensions.cs:47-54`、`/home/xp/src/copilot-api-js/refs/hooyoo-copilot-bridge/src/CopilotBridge.Cli/Pipeline/Adapters/Codex/ResponsesToIrInboundAdapter.cs:120-160` 和 `/home/xp/src/copilot-api-js/refs/hooyoo-copilot-bridge/src/CopilotBridge.Cli/Pipeline/Strategies/Codex/ResponsesRequestBuilder.cs:45-189` 用 provider bag 保存 IR 无类型槽位的字段。本轮确认符号存在，但没有逐字段验证 T1→IR→T2 的 producer／observer／upstream provenance，故只把“typed extension bag”保留为设计候选，不宣称它已完整 round-trip。来源 repo HEAD `2032fdd782aa1166eea0286977c59ab93eb5cab2`。

3. **上游历史提交归因。** agent 报告列出的 direct bridge、block commit、terminal repair、delivery owner、empty-499 retry 和 abort-provenance commit SHA 可用于追踪动机，但本轮共享终端受到其它会话输入干扰，批量 `git show` 祖先／主题校验未完整结束。本文关于当前机制的结论已经由 HEAD commit tree 独立支撑；具体历史归因在同步或实施前仍应逐个 `git show --stat --oneline <sha>` 复核，不能只引用报告标题。

## 可移植能力矩阵

| 能力 | 采用方向 | 主要依据 | 迁移时必须补的约束 |
|---|---|---|---|
| upstream leg resolver | 采用 | `copilot-api-js` S2 single decision | Anthropic `/v1/messages` bridge 无 override 时双能力模型选 Messages、Responses-only 模型选 Responses；原生 OpenAI Responses 公共入口保持 Responses upstream；缺失能力、unknown model、显式 override 与 vendor exception 必须由目标规格冻结 |
| direct request bridge | 采用 | per-protocol direct translator | 保序、tool-name mapper 闭包、field-loss matrix、no fabricated item id |
| non-stream response bridge | 采用但重写 reasoning 聚合 | direct output-item mapping | encrypted-only、多 reasoning、unknown item、failed terminal、raw arguments |
| stream parser | 采用状态机思想 | `output_index`／block key、done compensation | parser 与 delivery 分离；unknown event 可观测；不得 live flush |
| block-level delivery | 采用并作为基础合同 | commit predicate + ledger + owner | cap 不退回 live；pre／post commit error；exactly-once 已提交前缀 |
| terminal repair | 采用 repair-if-incomplete | item history + completeness oracle | synthetic provenance；正常 terminal 不重写；History 先观察原始帧 |
| reasoning round-trip | 采用 upstream-compatible v1 opaque carrier | fixed `copilot-api-js` v1 wire + source-domain gate | carrier byte-compatible，不重开私有设计；wire 兼容不等于复制有损聚合；visible／opaque／id／provenance 分字段 |
| client tools | 采用 call-id invariant | direct bridge + reference states | declaration／choice／history／response restore 共用 mapper |
| server tools | 不恢复产品支持 | 目标现行契约 | 只定义 no-revive、explicit degradation 和 observability；行为变更另行裁决 |
| retry／cancel | 采用应用层 owner | SDK retry=0 + stage/provenance | delivery phase 入合同；client／shutdown／timeout／upstream reset 分离 |
| HTTP／WS | 共享语义层 | upstream cell／transport separation | 同一 parser／delivery／History oracle；transport 只适配 wire |

## 后续规格必须冻结的合同

以下不是删减建议，而是完整范围进入实现前必须明确的合同；不能以暂时用不上为由跳过。

1. **路由合同。** 以 Anthropic `/v1/messages` bridge 的已裁决基线冻结 model mapping、显式 suffix、capability unknown、vendor exception、HTTP／WS leg 和 fallback 的精确优先级：无 override 时双能力模型选 Messages、Responses-only 模型选 Responses；原生 OpenAI Responses 公共入口继续使用 Responses upstream，不受该 bridge precedence 改写。依据：`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts:67-247` @ `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

2. **双向字段损失矩阵。** system／instructions、role、text／image／document、tools／choice、tool result、thinking／reasoning、metadata、usage、stop reason、errors、unknown fields 和 server tools。依据：`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:113-506` 与 `/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts:157-352` @ `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

3. **block 定义与 commit frontier。** 以 Anthropic content block 为已裁决交付单元，冻结 terminal／error 是否独立 block，以及跨 attempt 如何识别已提交 block。依据：`/home/xp/src/copilot-api-js/src/lib/codec/anthropic/commit-boundaries.ts:1-24` 与 `/home/xp/src/copilot-api-js/src/lib/pipeline/committed-blocks-ledger.ts:1-29` @ `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

4. **资源与背压。** 16 MiB 不是产品／架构阈值，不建立专属 gate、fixture、metric threshold、状态分支或 spill 路径；buffer 与 carrier 只服从 per-request `client_delivery.buffer_cap_bytes`、有界队列、backpressure 与取消清理。进程级只有等待式在途请求上限 `proactive_rate_limiter.max_inflight`，超限请求按到达顺序等待而不被拒绝；若运行证据要求 victim selection、额外终止政策或其他全面资源设计，必须先询问用户。当前目标 primitive 只有整流 cap，见 `/home/xp/src/ghc-api-proxy-py/src/app/streaming/buffered_retry.py:4-18` @ `47d9ef101c4b81ac70d805b1da157b34d021d33d`；该现状属于目标仓当前事实，不是目标裁决，更不能把其 cap 提升为目标合同。

5. **History／hooks／approval 时点。** 原始 upstream frame、translated block、committed downstream block、synthetic repair、retry attempt 和 final outcome 分别何时观察、记录和审批；不得让 History 只看到压缩后的客户端视图。当前目标 route 的 History 与 raw stream 紧耦合，见 `/home/xp/src/ghc-api-proxy-py/src/app/routes/openai.py:17-39`、`/home/xp/src/ghc-api-proxy-py/src/app/routes/openai.py:80-112` @ `47d9ef101c4b81ac70d805b1da157b34d021d33d`。

6. **兼容与可观测性。** unknown event、known-but-lossy field、foreign reasoning、filtered tool、terminal repair、post-commit error、cancel provenance 和 fallback reason 都必须有结构化 signal；不能以静默 drop 表示成功。反例见 `/home/xp/src/refs/caozhiyuan-copilot-api/src/routes/messages/responses-stream-translation.ts:88-144` default branch @ `6b97876927b7209a1e0f498e81927b32cc443e52`。

## 本轮评审处置

| 评审／裁决项 | 处置 | 结果 |
|---|---|---|
| major：`anthropic.py:53-100` 未覆盖 stream passthrough、idle timeout 与 SSE return | 采纳 | 扩为 `anthropic.py:53-120`，结论不变 |
| major：`openai.py:80-106` 未覆盖 `client.responses(request)` | 采纳 | 扩为 `openai.py:80-112`，结论不变 |
| major：`driver.ts:1335-1390` 未覆盖 flush、`committedAny` 与 ledger record | 采纳 | 扩为 `driver.ts:1335-1418`，结论不变 |
| major：stream translator `:88-125` 未覆盖 default／`return []` | 采纳 | 扩为 `:88-144`，结论不变 |
| 全文 `file:line` 关键动词覆盖复验 | 采纳并完成 | 逐项以固定 commit tree 复验全部 76 个唯一引用；另扩大 delivery owner error、network retry、Anthropic abort、hooyoo identity adapter、provider bag 与 committed ledger 六处窄范围；未采信脏工作树 |
| R2 唯一 major／最新用户重裁：carrier wire 固定兼容 `copilot-api-js` v1；16 MiB 不是产品／架构阈值 | 采纳并关闭；其中的内存预算部分已于 2026-08-19 被覆盖，见下一行 | 目标约束已改为 byte-compatible wire 且明确不继承 upstream 有损聚合；删除 16 MiB 专属 gate／状态建议，改为普通内存预算／准入／背压、实际全局耗尽时拒绝新 admission 的最小止血，全面资源设计先询问用户；上游事实与目标裁决继续分层 |
| merged-state major：把 Anthropic `/v1/messages` bridge 的默认 route precedence 误扩张到原生 OpenAI Responses 公共入口 | 采纳并关闭 | “目标项目约束”、能力矩阵与后续路由合同均已限定为 Anthropic `/v1/messages` bridge：无 override 时双能力模型选 Messages、Responses-only 模型选 Responses；原生 OpenAI Responses 公共入口保持 Responses upstream，不从 bridge precedence 推导改走 Messages |
| 2026-08-19 用户重裁：删除全局内存预算，改以在途请求数封顶（覆盖上面 R2 行的内存预算部分） | 采纳并关闭 | 字节级内存预算整体删除（`src/app/delivery/reservation.py` 与 `openai_responses.global_resident_bytes`／`request_resident_bytes` 随 `546852a` 移除）；进程级改为等待式在途请求上限 `proactive_rate_limiter.max_inflight`（默认 50，`InFlightLimit`，`f5589ec`），超限请求按到达顺序等待，不拒绝、不返回 429、不断连，`/health`、`/health/liveness`、`/health/readiness`、`/metrics` 豁免（`7e9b62d`）；per-request `client_delivery.buffer_cap_bytes` 保留。“16 MiB 不是阈值”“全面资源设计先询问用户”两条继续有效 |

## 持续同步 upstream 的方法

### 1. 冻结 sync baseline，而不是跟随工作树

每轮同步先在同一 shell 调用中校验目标 repo top-level+HEAD，再对每个来源 repo 记录物理 top-level、完整 HEAD 和 status。主 upstream 若工作树脏，只用 `git show <HEAD>:<path>`、`git diff <OLD>..<NEW>` 与 `git log <OLD>..<NEW>`；不得把未提交文件内容混进结论。本文当前 baseline 是 `/home/xp/src/copilot-api-js` @ `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

### 2. 保存按机制分组的 watch list

后续同步至少观察以下路径组；路径变化时按职责重新定位，不把文件名本身当永久合同。

- 路由：`/home/xp/src/copilot-api-js/src/lib/models/resolver.ts`、`/home/xp/src/copilot-api-js/src/lib/models/endpoint.ts`、`/home/xp/src/copilot-api-js/src/lib/pipeline/router.ts`。
- request bridge：`/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts`、`/home/xp/src/copilot-api-js/src/lib/openai/tool-name-sanitize.ts`、`/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/openai-responses-cell.ts`。
- response bridge：`/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts`、`/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic-stream.ts`、`/home/xp/src/copilot-api-js/src/lib/anthropic/synthetic-reasoning.ts`。
- delivery／retry：`/home/xp/src/copilot-api-js/src/lib/codec/anthropic/commit-boundaries.ts`、`/home/xp/src/copilot-api-js/src/lib/pipeline/committed-blocks-ledger.ts`、`/home/xp/src/copilot-api-js/src/lib/pipeline/driver.ts`、`/home/xp/src/copilot-api-js/src/lib/pipeline/delivery/session.ts`。
- Responses reducer／transport：`/home/xp/src/copilot-api-js/src/lib/codec/openai-responses/buffered-merge-reducer.ts`、`/home/xp/src/copilot-api-js/src/lib/openai/upstream-ws-attempt.ts`、`/home/xp/src/copilot-api-js/src/lib/request/strategies/network-retry.ts`。

### 3. 每个 upstream delta 做四类判定

1. **语义变化**：field mapping、event grammar、stop／usage／error、tool／reasoning provenance 是否变化。
2. **接线变化**：helper 是否真正进入 route→driver→cell→transport→delivery 生产链；helper 存在不等于能力生效。
3. **判据变化**：新增测试是否覆盖真实 producer／consumer seam，还是只直接调用 helper；测试源码存在不等于本轮 green。
4. **产品边界冲突**：任何 live sink、buffer-cap retreat-to-live、server-tool revive 或 SDK retry ownership 变化，都必须先与本项目裁决／契约对账，不能自动同步。

### 4. 用差分 oracle 同步，不做代码拷贝同步

建立目标仓自有 fixtures，将同一 Anthropic request／Responses response／SSE event sequence 喂给固定 upstream translator 快照与目标 translator，比较规范化语义而非逐字节对象。请求 oracle 至少覆盖反向排列和交错排列、forced tool choice、非法 tool name、foreign reasoning、fabricated item id；响应 oracle 至少覆盖 encrypted-only、多 reasoning、unknown item、malformed arguments、failed／incomplete、late usage、transport EOF；delivery oracle 另验证完整 block 才提交、pre-commit 可重试、post-commit 不重复。来源反例分别见 `/home/xp/src/copilot-api-js/src/lib/openai/translate/anthropic-to-responses-request.ts:214-306` 与 `/home/xp/src/copilot-api-js/src/lib/openai/translate/responses-to-anthropic.ts:163-219` @ `8d5c861c2e079b92401dd8ccd49695a363d078fe`。

### 5. 同步记录必须携带 provenance

每轮记录 `old upstream HEAD → new upstream HEAD`、changed paths、采纳／不采纳机制、理由、目标测试／fixture 和尚待 live-wire 核验项。提交 SHA 只说明历史来源，不证明目标项目应采用；源码 line 只说明该固定 HEAD 的实现，不是永恒位置。若 upstream 修复本文列出的缺陷，应先确认生产接线和正反控制，再更新本文状态，不能仅凭 commit title 把“待核验”改成“已解决”。

## 验证边界与下一步

- 本轮已完成静态、固定快照的独立源码核验；未运行任何项目测试，也未做真实 upstream 网络复验。
- 后续进入规格时，应把“可移植能力矩阵”和“必须冻结的合同”逐项映射到 acceptance；不得把参考实现已有测试当成本项目 oracle。
- 后续进入实施计划时，应按 TDD 顺序先写字段／grammar／delivery／retry 的失败测试，再实现 pure translators、state machines 和 shared delivery owner；HTTP／WS routes 最后接线，以防 route 内复制语义。
- 本文是长期研究结论；七份 `docs/tmp` 输入可归档或删除，不影响本文的 source repo+HEAD、机制、可移植项、不可照搬项与同步方法。

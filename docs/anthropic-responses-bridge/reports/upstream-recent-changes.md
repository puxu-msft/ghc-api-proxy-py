# copilot-api-js upstream 近期高价值变更调查

## 调查口径

- 调查日期：2026-08-06。
- upstream：`/home/xp/src/copilot-api-js`。调查开始 HEAD 为 `995c1047244c5e1c6f683336eff615ae651e73c1`；并发会话期间仓库前进，最终对账 HEAD 为 `8d5c861c2e079b92401dd8ccd49695a363d078fe`。从前一对账点 `74853175c2c5771e6110bdbdfb97870132788fa1` 到该 HEAD 仅新增 History worker 规格文档，未触及本报告主题。本文的“当前是否仍有效”均以最终 HEAD 的已提交树为准。
- migration target：`/home/xp/src/ghc-api-proxy-py`，写入前 HEAD 为 `47d9ef101c4b81ac70d805b1da157b34d021d33d`。
- 只读方法：按主题扫描提交历史，逐条用 `git show` 核对 SHA／日期／主题，再用最终 HEAD 的 `git grep`／提交树行号确认实现仍可达。未把 upstream 工作树中的未提交内容计入结论，也未做运行时网络复验；因此“仍有效”表示实现仍存在且接线可达，不等价于真实上游兼容性已重新实测。
- target 当前基线：Anthropic `/v1/messages` 在 `src/app/routes/anthropic.py:53-100` 首响应后直接透传；Responses HTTP 在 `src/app/routes/openai.py:17-39,80-106` 直接透传；`src/app/streaming/buffered_retry.py:4-16` 只有整流限额收集 primitive，尚没有 block-level commit、delayed commit、terminal repair 或 direct semantic bridge 的完整生产接线。

## 高价值变更

### 1. 模型目标后缀与 Anthropic 无后缀自动路由

- Commit：`b2aadcb787e7193e3bd31c4489f8f97d7a8cc44e`，2026-07-12，`feat(models): add resolveModelTarget with @cc/@responses/@messages suffix parsing (T1.1)`；`9def2fc50f4336caffeb71eed861a0b373e6ab0b`，2026-07-13，`feat(router): no-suffix anthropic auto-routes non-Anthropic models (messages > responses > cc)`。
- 改动／当前 `file:line`：`src/lib/models/resolver.ts:199` 解析显式 route override；`src/lib/pipeline/driver.ts:267-273` 在统一 S2 路由点调用 `decideRoute`。
- 当前是否仍有效：是。解析器与 driver 单一读点均仍在最终 HEAD。
- 迁移价值：高。Python 当前 Anthropic 路由固定调用 Anthropic client；若要让 Messages 客户端选择 Responses upstream，建议先迁移“解析目标”和“选择 upstream”两个独立阶段，避免把 `@responses` 之类后缀泄漏到真实 model id。

### 2. Anthropic Messages → Responses upstream 的单跳 direct bridge

- Commit：`69b82024aeb4155d978227d725b3583b299020f4`，2026-07-15，`feat(bridge): direct anthropic→responses request bridge (Phase 3 subtask A)`；`cd1a5be6f654fbc1e4463a6151659a1f2937e009`，2026-07-15，`feat(bridge): direct responses→anthropic non-streaming response bridge (Phase 3 subtask B)`；`0fd3fbbf083dffb0387828908c4f383420e0c235`，2026-07-16，`feat(bridge): direct responses→anthropic streaming response bridge (Phase 3 subtask C)`。
- 改动／当前 `file:line`：`src/lib/openai/translate/anthropic-to-responses-request.ts:113-168` 直接构造 Responses request；`src/lib/pipeline/hub-translate.ts:256-265` 接入 Responses upstream → Anthropic 非流式 bridge；流式实现位于 `src/lib/openai/translate/responses-to-anthropic-stream.ts`。
- 当前是否仍有效：是。request bridge、HTTP response bridge 与 streaming translator 均仍由 hub 使用。
- 迁移价值：最高。Python 已有 Messages 与 Responses 两套 transport，但没有跨协议单跳语义层；可直接借鉴“每个协议对独立 bridge，不经 Chat Completions 中间形态”的边界，减少 tool／reasoning 信息损失。

### 3. Responses client → Anthropic Messages upstream 的反向 direct bridge

- Commit：`9d6fc30efb6225c7f93decdda861342115cd0d9a`，2026-07-16，`feat(bridge): direct responses→anthropic reverse request bridge (Phase 4 subtask D)`；`4888edd4a6a6b9d35e19394c64be18f212fb956d`，2026-07-16，`feat(bridge): direct anthropic→responses reverse non-streaming response bridge (Phase 4 subtask E)`；`2d78a3d850b668e4359c57d123c973da7282820a`，2026-07-16，`feat(bridge): direct anthropic→responses reverse streaming response bridge (Phase 4 subtask F)`。
- 改动／当前 `file:line`：`src/lib/openai/translate/responses-to-anthropic-request.ts:113` 构造 Messages wire；`src/lib/pipeline/hub-translate.ts:166,194` 注册 request bridge；`src/lib/pipeline/hub-translate.ts:467-500` 为 Responses client 建立 reverse stream translator，并强制要求 exchange context。
- 当前是否仍有效：是。双向 hub matrix 仍显式注册该组合。
- 迁移价值：最高。Python 的 Responses HTTP／WS transport 已存在，迁移此能力可让 Claude 模型走原生 `/v1/messages`，但必须同时迁移 exchange context 中的 response id、item id 与 resolved model，不能只做无状态逐帧改名。

### 4. reasoning／thinking 的跨协议往返与签名隔离

- Commit：`3770bc73f8310b34ea0b35eda1e0432542380835`，2026-07-16，`feat(bridge): claude-signature carrier primitive (Phase 5 reverse round-trip)`；`039521b0852df1f9443aecc6b31aa9a32efd7657`，2026-07-16，`feat(bridge): forward reasoning round-trip return leg (Phase 5)`；`6874027d70680d1259a1fd7471eb6d42e8e3c804`，2026-07-16，`feat(bridge): two-scenario reasoning features wiring (strip-thinking-signature) (Phase 5)`。
- 改动／当前 `file:line`：`src/lib/anthropic/synthetic-reasoning.ts:44` 生成可辨识 carrier；`src/lib/openai/translate/anthropic-to-responses-request.ts:203-212` 只恢复本代理产生的 sentinel envelope，并计数丢弃不可移植的 Claude-signed thinking。
- 当前是否仍有效：是。carrier primitive 与 request translator 的重建／隔离逻辑仍存活。
- 迁移价值：高。Python 若实现 direct bridge，应把“真实 Claude signature”和“代理合成的 Responses encrypted_content carrier”分域，禁止把不可移植签名误送到另一模型，同时为有损丢弃留下结构化诊断。

### 5. server tool 的请求侧映射与响应侧 R-NO-REVIVE 降级

- Commit：`26738c710cb5727f55c420a354a625499f5444d7`，2026-07-16，`feat(bridge): server-tool request-side passthrough via mapping table (Phase 6 subtask P)`；`5054e5e2b548a14185449b4f6ce21c9a532eab34`，2026-07-16，`feat(bridge): web_search_call response-side degradation, R-NO-REVIVE (Phase 6 subtask Q)`。
- 改动／当前 `file:line`：请求侧映射仍集中在 `src/lib/anthropic/message-mapping.ts:31` 附近；`src/lib/openai/translate/responses-to-anthropic.ts:189-262` 与 `responses-to-anthropic-stream.ts:280-283` 把原生 `web_search_call` 降级为可读文本，明确不伪造可回放 server-tool block。
- 当前是否仍有效：是。R-NO-REVIVE 分支仍是 non-streaming／streaming 共用语义。
- 迁移价值：条件性高。Python 当前明确不实现 Anthropic 原生 server-tool 执行；不应推翻该裁决，但一旦引入 direct bridge，至少应迁移“未知 server tool 不伪造成 client tool、不可往返时显式降级”的不变量。

### 6. function_call 输入 item id 的 upstream 400 修复

- Commit：`684761e4005fc380edec8eb7d7a27b768d6f550e`，2026-07-21，`fix(responses): omit fabricated function_call item id on request input (upstream 400)`；`a53ff7407f38275b7102764a45c57edaa75decae`，2026-07-21，`fix(responses): unconditional wire backstop stripping non-fc function_call item ids`。
- 改动／当前 `file:line`：`src/lib/openai/translate/anthropic-to-responses-request.ts:339-376` 的回归契约对应当前 translator 的 function-call 构造规则：输入只带 `call_id`，不把 `call_`／`toolu_` id 伪装为必须 `fc_` 前缀的 item `id`；last-mile wire 另有无条件 backstop。
- 当前是否仍有效：是。direct translator 与 wire shaping 仍遵守该规则。
- 迁移价值：最高且低成本。Python direct bridge 必须把 Responses item `id` 与 tool `call_id` 分开建模；建议同时做 translator 层正确构造和出站 wire backstop，避免单一调用点漏网。

### 7. Anthropic Messages 的 block-level commit boundary buffered retry

- Commit：`b1bf467fe3e858136218b5a8869c1be86dfcf4ba`，2026-07-11，`feat(anthropic): content_block_stop commit-boundary predicate`；`756387cf928e95ef5d9f7a90dc42b25e77d02be8`，2026-07-13，`feat(anthropic): wire block-level commitBoundaries into buffered pump (P1 Task 6 wiring)`；`1da8a033950b508f4ebe3c814400f47e04dd5ca8`，2026-07-14，`fix(pipeline): keep buffered anchor open across block-level commits + guard re-injection`。
- 改动／当前 `file:line`：`src/lib/pipeline/driver.ts:1357-1371` 在格式提供的 boundary 上提交完整 block，并把 upstream error 同时视为 boundary 与 terminus；`src/lib/pipeline/committed-blocks-ledger.ts:4-18` 只记录完整提交的 block。
- 当前是否仍有效：是。commit-boundary 分支、跨 attempt ledger 与 anchor 处理仍在统一 driver。
- 迁移价值：最高。Python 的 `collect_with_limit` 只能全量收集，Messages 路由又直接逐 chunk 透传；应升级为“完整 content block 才提交”，让失败 attempt 在未提交区间可重试，同时不重复已发 block。

### 8. Messages pre-commit retry signal 与 post-commit canonical error 分流

- Commit：`2dcebc76afd78edb82e19e05721e9f9f73ceac43`，2026-07-13，`feat(messages): pre-commit error-shaping glue for /v1/messages routes`；`301e63b299fca6c5ad60a9bd181951320f420b68`，2026-07-20，`fix(messages): delayed-commit catch 重排使瞬态 request.failed 快照含 error 帧（Unit 1 缩减版）`。
- 改动／当前 `file:line`：`src/lib/anthropic/error-shaping.ts:59-109` 用 `pre-commit | post-commit` 作为核心事实；可重试错误在 pre-commit 变成 retry signal，post-commit 只能生成协议合法的 canonical error frame。
- 当前是否仍有效：是。错误分类与 commit phase 的组合仍是 Messages handler 的决策输入。
- 迁移价值：最高。Python 目前上游非成功响应直接返还、流中断统一记 499；迁移后应把“是否已向客户端提交协议内容”放进错误合同，避免已发前缀后仍重试造成重复或混流。

### 9. generation coordinator、fast retry eligibility 与有界候选竞争

- Commit：`cd8fa64910b3dcc81c33f87fda16224bc6812ba9`，2026-07-18，`refactor(pipeline): add candidate and dispatch runtime`；`5990bde9ed3ef9541324aa538737ce0e82e1c941`，2026-07-18，`feat(pipeline): define fast-retry eligibility`；`032a48423ddb14f294c32f4e66d2982cd60d5148`，2026-07-18，`feat(pipeline): classify candidate commit boundaries`；`689cf2aeb5e49956f174d706a73948890c0b8914`，2026-07-18，`feat(pipeline): wire live fast-retry candidates`；`8955e0366c1c537cc7731b44fafb04e699ab9d71`，2026-07-18，`feat(pipeline): bound generation competition resources`。
- 改动／当前 `file:line`：`src/lib/pipeline/generation/candidate-response-session.ts:42-155` 承载候选状态与 flush transform；`src/lib/pipeline/generation/dispatch-scheduler.ts:194-219,342-349` 传播 admission／cancel 原因并释放 dispatch；driver 在 `1116-1119` 维护跨 attempt 已提交事实。
- 当前是否仍有效：是，但已被后续 delivery／generation 重构吸收，不能按原提交逐文件照搬。
- 迁移价值：高、实施复杂度高。Python 已明确让 SDK `max_retries=0`，因此 retry owner 应继续留在应用层；建议先迁移单候选 pre-response fast retry，再考虑 hedge，且用容量 gate 限制并发候选，避免连接池与模型配额被放大。

### 10. Responses buffered merge 的 driver flush seam 与 candidate 接线

- Commit：`230984ccfba0b9b1f3ac3e67ea19110f2b86615b`，2026-07-19，`feat(pipeline): add candidate-hosted transformBufferedFlush seam to driver flush choke point`；`45f3799b9baef3308f351faabcff8e380cf679ad`，2026-07-19，`feat(responses): wire the buffered-merge reducer into the candidate response session (spec §4 2026-07-19 重接地)`。
- 改动／当前 `file:line`：`src/lib/pipeline/driver.ts:1218-1245` 在唯一 flush choke point 调用可选 transform；`src/routes/responses/candidate-response-session.ts:115-151` 先 observe 完整 rendered frame，再在 flush 时做 reducer transform。
- 当前是否仍有效：是。HTTP／WS 共用 candidate-hosted reducer，且 observe-before-drop 顺序仍保留。
- 迁移价值：最高。Python Responses HTTP／WS 当前只透传；可迁移一个协议专用 reducer，但应挂在共享 flush seam，而不是分别在两个 route 内复制。完整帧必须先进入 history／diagnostics，再做面向客户端的 delta compaction。

### 11. Responses completed_output 缺陷探测与 terminal snapshot repair

- Commit：`3644c976746784c1a8f82c5a6f93577e2cf6ccb6`，2026-07-19，`feat(responses): add isTerminalSnapshotComplete() defect oracle for the completed_output repair gate`；`7ff8a54a5cd2850000ca4b94a0e84d1af2396393`，2026-07-19，`feat(responses): completed_output repair-if-incomplete rebuilds defective terminal + tags synthetic`。
- 改动／当前 `file:line`：`src/lib/codec/openai-responses/buffered-merge-reducer.ts:70-175` 比较 terminal `response.output` 与已收集 item，只在缺陷模式下重建，并给合成 terminal 标记 synthetic origin。
- 当前是否仍有效：是。`repair-if-incomplete` 与 unconditional `rebuild` 模式均仍在 reducer。
- 迁移价值：高。Python 已有 `ResponsesStreamAccumulator`，可复用其 item 累积状态做独立 completeness oracle；不要无条件改写正常 upstream terminal，合成帧必须可观测，避免 history 把代理修复误认成原始上游事实。

### 12. buffered delivery owner port 跨 leg 复用

- Commit：`3dca351582d42c24918392f349a911fec7e65458`，2026-08-02，`refactor(delivery): reuse buffered owner port across legs`。
- 改动／当前 `file:line`：提交改动集中在 `src/lib/pipeline/driver.ts`；最终 delivery 所有权错误合同位于 `src/lib/pipeline/delivery/session.ts:79-84,354-478`，driver 在 `1188` 统一识别 `DeliveryOwnerError`。
- 当前是否仍有效：是。所有 leg 共用同一 delivery ownership 抽象，而非各自维护近似 owner。
- 迁移价值：中高。Python 新增 block buffering 时应先抽“唯一 downstream writer／owner port”再接 Anthropic 与 Responses，避免 heartbeat、正常帧、错误帧三条路径并发写同一响应流。

### 13. 空 body upstream HTTP 499 纳入一次 network retry

- Commit：`d2607ec9b195bc39a34fc7d8f369f6bca700e9e4`，2026-08-06，`fix: retry empty upstream 499 responses`。
- 改动／当前 `file:line`：`src/lib/request/strategies/network-retry.ts:4-25` 把连接失败与“upstream 499 且 body 为空”归为同一瞬态网络类，短暂退避后用相同 payload 重试一次；非空 499 不被此规则吞掉。
- 当前是否仍有效：是。network strategy 与 retry registry 仍注册该分类。
- 迁移价值：最高且低成本。Python 当前 `UpstreamResponseError` 会原样返还任何 499；应在尚未提交 client response 时，仅对“确认来自 upstream、body 为空”的 499 做一次有界重试，并保留非空 body 的真实语义。

### 14. Responses fallback 跨转换保留 forced tool choice

- Commit：`c4004e48944886326039b259b527b79dc9c741dc`，2026-08-05，`fix(responses): align tool choice with translated tools`；`b8372966ad1ca750be9b5c3fa4638e9a5de48360`，2026-08-05，`fix(responses): preserve forced custom tool choices`；`dc1288ea0415e35adae86ae3a9d3dc5b476d0d2d`，2026-08-05，`fix(responses): preserve tool choices across fallbacks`。
- 改动／当前 `file:line`：最终改动存活在 `src/lib/openai/translate/anthropic-to-cc-request.ts` 与 `src/lib/openai/translate/responses-to-anthropic.ts`；同类命名同步不变量可见 `src/lib/anthropic/sanitize/tool-name-sanitize.ts:79-106`，forced choice 必须与已重命名／过滤后的 tool definition 同步。
- 当前是否仍有效：是。direct 与 fallback translator 都保留 forced custom tool choice，而非退化为 `auto`。
- 迁移价值：最高。Python direct bridge／fallback 若只翻译 `tools` 而遗漏 `tool_choice`，会产生静默行为回归；建议把两者放进同一个 translator 返回值并做“chosen tool 必须存在于 translated tools”的闭包校验。

### 15. WS／legacy 路径保留 abort provenance

- Commit：`0027741bcb998637b01b9b218f0973119065ce49`，2026-07-28，`fix(responses,anthropic): carry abort provenance through the WS and legacy paths`。
- 改动／当前 `file:line`：`src/lib/openai/upstream-ws-attempt.ts:152-179` 显式登记、传播并解除外部 abort source；`src/lib/anthropic/client.ts:80-96` 区分 client abort 与 shutdown abort，后者包装为可重试 529，而不是误报 client cancel。
- 当前是否仍有效：是。WS attempt 和 Anthropic transport 都仍保留取消来源。
- 迁移价值：高。Python 的 stream finalizer 当前把所有未完成流统一记作 499；应携带 client disconnect、server shutdown、idle timeout、upstream reset 等 provenance，只有 client disconnect 映射 499，shutdown／upstream failure 才能进入正确 retry 与观测路径。

## 建议迁移顺序

1. 先做第 13、14、15 条：改动面较窄，能立即修复错误分类、tool intent 丢失和取消误归因。
2. 再建立第 7、8、12 条的 delivery／commit 基座：唯一 writer、commit phase、block ledger 先于协议功能。
3. 在该基座上做第 10、11 条 Responses buffered merge／terminal repair，以及第 9 条单候选 pre-response fast retry；hedge 最后。
4. 最后做第 1～6 条双向 direct bridge。先冻结每个协议对的损失矩阵与 exchange context，再接 streaming；不要先做通用 canonical hub 后补语义漏洞。

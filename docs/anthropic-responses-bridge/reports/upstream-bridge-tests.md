# Anthropic→Responses direct bridge 测试资产与缺口

## 评审摘要

- **评审范围**：`/home/xp/src/copilot-api-js` 最新且冻结的 `HEAD` `8d5c861c2e079b92401dd8ccd49695a363d078fe`。范围包括 Anthropic client→Responses upstream 的请求转换，以及 Responses upstream→Anthropic client 的非流与流式返回，并追踪工具、reasoning、usage/error、重试与 buffering 接缝。
- **总体 verdict**：**修复 major 后可进入 Python 移植**。纯转换层测试资产丰富，流式层还有独立 consumer oracle；但 direct 路由的集成样本主要停留在等价区，跨轮 reasoning、Responses 错误映射和 Responses 路由上的重试/buffering 尚有明显假绿窗口。
- **blocker 数**：0。
- **major 数**：5。
- **调查方式**：只读静态调查；未运行测试。上游工作树有并行改动，因此所有枚举与引用均锚定上述 commit；被引用测试文件另经 `git diff --quiet <HEAD> -- <paths>` 确认与 commit 内容一致。调查期间 HEAD 两次前进，最终一次仅修改 `docs/spec/2026-08-06-history-persistence-worker.md`，未触及本报告范围。

### 双视角覆盖证据

- **机械核对**：核对 production wiring `src/lib/pipeline/hub-translate.ts` 的三个 direct bridge 接点；枚举 `anthropic-to-responses-request`、`responses-to-anthropic`、`responses-to-anthropic-stream` 的 unit/IT/HTTP 资产；对账 `@responses` 路由选择、Responses fixture、独立 SDK/accumulator oracle、retry/buffering 测试实际选择的 upstream endpoint；扫描测试名中的旧“四跳/两跳”措辞。
- **第一人称执行模拟**：模拟 Python 实现者按请求转换→非流返回→流式状态机→工具→reasoning 跨轮→usage/error→RST 重试与 buffer commit 的顺序移植；逐步检查每一阶段是否有独立 oracle 能让错误实现变红，以及 direct bridge 退回旧两跳、路由未接线、失败尝试泄漏、权威 `.done` 数据丢失时现有测试是否仍可能全绿。

## 分类资产、可移植性与缺口

1. **请求转换｜可直接移植｜假绿风险：低**
   - 资产：`/home/xp/src/copilot-api-js/tests/openai/anthropic-to-responses-request.unit.test.ts:472`，测试 `envelope: instructions (system flatten) / max_output_tokens=max_tokens / temperature/top_p/stream / metadata.user_id→user; Anthropic-only top_k/stop_sequences dropped`。
   - Oracle：对完整输出对象做字段存在与明确缺失断言，尤其是 `instructions`、`max_output_tokens`、`user` 和 `top_k`/`stop_sequences` 不泄漏。
   - Python：原样移植为参数化 dict equality/absence tests；不要只断言目标字段存在。

2. **请求转换｜可直接移植｜假绿风险：低**
   - 资产：`/home/xp/src/copilot-api-js/tests/openai/anthropic-to-responses-request.unit.test.ts:339`，测试 `assistant tool_use → a function_call item (call_id=block.id, NO fabricated item id, arguments=JSON.stringify(input)); text+tool_use are SEPARATE items (per-block, no CC-style fold)`；以及 `:366`，测试 `assistant tool_use whose id is a call_-prefixed id ... carries NO item id`。
   - Oracle：同时锁定 item 顺序、`call_id`、JSON arguments，以及非法 `id` 字段必须缺失；这是比“能看到 function_call”更有判别力的 wire oracle。
   - Python：直接移植，并加入完整序列断言，避免 serializer 默认补 `None` 后仍输出 `id: null`。

3. **请求转换／工具｜可直接移植｜假绿风险：低**
   - 资产：`/home/xp/src/copilot-api-js/tests/openai/anthropic-to-responses-request.unit.test.ts:227`，测试 `a forced web_search choice uses the same Responses builtin category as the translated tool`；`:239`，测试 `a forced choice for an unmapped typed tool is dropped with that tool instead of becoming a dangling function choice`；`:273`，测试 `a named choice with no matching declaration is dropped instead of becoming a dangling function choice`。
   - Oracle：工具声明集合与 `tool_choice` 必须共同变换，不能产生悬空强制选择。
   - Python：适合表驱动移植，覆盖 builtin、function、unsupported typed tool 与 missing named choice。

4. **请求转换／生产接线｜可直接移植但需增强｜假绿风险：中**
   - 资产：`/home/xp/src/copilot-api-js/tests/anthropic/anthropic-codec-forward-leg.it.test.ts:118`，测试 `@responses forward leg → prepare-wire yields a Responses-shaped wire at /responses (input[], not messages[]) — W4`；`:140`，测试 `@responses forward leg records one structured degradation for all foreign Claude thinking blocks`。
   - Oracle：真实 codec+driver 的 `/responses` 路由、`input[]` wire shape 和 degradation telemetry，可移植为 Python handler/service integration test。
   - 缺口：集成层没有在同一个用例里断言工具、tool choice、reasoning effort 和 envelope 的具体 wire 值；若 hub 选对 endpoint、但调用了错误 mapper，基础 shape 仍可能通过。

5. **非流响应｜可直接移植｜假绿风险：低**
   - 资产：`/home/xp/src/copilot-api-js/tests/openai/responses-to-anthropic.unit.test.ts:113`，测试 `function_call → tool_use block (call_id passed through verbatim, arguments JSON-parsed)`；`:131`，测试 `tool_calls wins stop_reason regardless of status`。
   - Oracle：完整 Anthropic content block equality，加上 tool turn 对 terminal status 的优先级。
   - Python：直接移植；malformed arguments 的 repair/degrade 用例也应保持同一 expected object，而不是只断言“不抛错”。

6. **非流响应／usage 与状态｜可直接移植｜假绿风险：低**
   - 资产：`/home/xp/src/copilot-api-js/tests/openai/responses-to-anthropic.unit.test.ts:261`，测试 `incomplete + an UNKNOWN/future reason ... → end_turn`；`:268`，测试 `incomplete + content_filter → end_turn ... + contentFiltered flag`；`:317`，测试 `cache_write_tokens ... subtracted too + surfaced as cache_creation_input_tokens`；`:324`，测试 `output_tokens_details.reasoning_tokens is forwarded`。
   - Oracle：显式枚举 status mapping，未知值走保守默认；usage 同时核对净输入算术和保留的明细字段。
   - Python：优先移植为参数化映射表与算术不变量，尤其要防 `input_tokens - cache_read - cache_write` 与 reasoning detail 丢失。

7. **非流响应／生产接缝｜major｜假绿风险：高**
   - 证据：`/home/xp/src/copilot-api-js/tests/anthropic/anthropic-nonstream-roundtrip.it.test.ts:176`，测试名仍为 `Anthropic → CC → Responses wire → mock Responses response → Responses → CC → Anthropic (four hops)`，但最新 production wiring 已是 direct bridge。该用例只断言 text、function_call、stop reason 和基础 usage，这些都属于新旧路径的等价区。
   - 失败场景：direct response bridge 被绕过或退回旧两跳时，该测试仍可能全绿；direct 独有的 reasoning、unknown incomplete reason、content filter marker、cache-write/reasoning usage 均未进入真实 driver roundtrip。
   - 修复建议：Python 不要照搬“四跳 golden”；新增 direct-only 集成样本，把 reasoning item、`incomplete_details` 和 richer usage 从 mock Responses upstream 送过真实 route/driver，再断言 Anthropic response。

8. **流状态机｜可直接移植｜假绿风险：低**
   - 资产：`/home/xp/src/copilot-api-js/tests/openai/responses-to-anthropic-stream.unit.test.ts:269`，测试 `sparse/large native output_index ... still allocates a small monotone Anthropic index`；`:254`，测试 `interleaved ... tool args defensively reopen the target block`；`:588`，测试 `flush is idempotent`。
   - Oracle：输出 block index 必须连续单调且与稀疏 upstream `output_index` 解耦；乱序工具参数不能崩溃；flush 只能终结一次。
   - Python：原样移植状态转移序列和完整 frames，不要只测最终拼接文本。

9. **流状态机／独立 consumer｜可移植其不变量｜假绿风险：低**
   - 资产：`/home/xp/src/copilot-api-js/tests/openai/responses-to-anthropic-stream.unit.test.ts:450`，测试 `SDK ORACLE: a reasoning+tool_use+text stream accumulates a well-formed message via the REAL @anthropic-ai/sdk`。
   - Oracle：把合成 SSE wire 交给真实 Anthropic SDK decoder，再断言 thinking/tool/text 顺序、tool arguments、signature payload 与 stop reason；它能抓住 self-golden 看不到的 event-line 丢帧。
   - Python：不可机械复制 TypeScript helper，但必须保留“独立消费者”原则。优先使用 Anthropic Python SDK 的实际 streaming parser；若无可调用公共入口，使用与产品 parser 不同实现的严格 SSE decoder，并断言完整累积对象。

10. **流状态机／生产接缝｜major｜假绿风险：高**
    - 证据：`/home/xp/src/copilot-api-js/tests/anthropic/anthropic-stream-roundtrip.it.test.ts:175`，测试 `Responses SSE → Anthropic frames survive the real SDK decoder` 确实走真实 codec+driver 和 `@responses`，但 fixture 只有 `response.created`、一个 text delta 和 `response.completed`。
    - 失败场景：production seam 对 function_call、稀疏 index、reasoning `.done`、content filter 或 truncated terminal 的 option/meta threading 接错时，unit tests 与 text-only IT 仍会同时全绿。
    - 修复建议：Python 集成测试至少加入一个混合 reasoning→tool→text stream，并由独立 Anthropic consumer 累积；另加无 terminal 与 `response.failed` 两个 route-level 分支。

11. **reasoning 跨轮｜major｜假绿风险：高**
    - 证据：`/home/xp/src/copilot-api-js/tests/openai/responses-to-anthropic.unit.test.ts:211`，测试 `reasoning encrypted_content is embedded in the signature for cross-turn round-trip`；`/home/xp/src/copilot-api-js/tests/openai/anthropic-to-responses-request.unit.test.ts:44`，测试 `an echoed-back sentinel-signed thinking block reconstructs a reasoning input item carrying the recovered encrypted_content`。两侧分别使用 helper 构造/解析 fixture；冻结测试树中没有测试把前者的实际输出原样喂给后者。
    - 失败场景：生产者和消费者对 sentinel、base64url、空 payload 或 block ordering 的约定发生接缝漂移时，两组 isolated tests 仍可能全绿。
    - 修复建议：Python 必须增加真实 producer→client echo→consumer roundtrip，断言 `encrypted_content` byte-exact；同时保留 foreign signature、bare prefix 与多 reasoning block 的负样本。

12. **usage/error｜major｜假绿风险：高**
    - 资产：`/home/xp/src/copilot-api-js/tests/openai/responses-to-anthropic-stream.unit.test.ts:515`，测试 `plain text completion → end_turn + net usage`；`:531`，测试 `reasoning_tokens is forwarded onto the terminal usage`；`:578`，测试 `response.failed throws`；`:583`，测试 `a terminal error event throws`。
    - 缺口：HTTP/driver error oracle 只见 `/home/xp/src/copilot-api-js/tests/anthropic/anthropic-nonstream-roundtrip.it.test.ts:228` 的 `upstream CC 429 ... mapped to an Anthropic error envelope`，没有等价的 `@responses` 429/failed route test。纯 translator 抛错不能证明 handler 保留 status/type/message，也不能证明失败前未提交 200。
    - 修复建议：Python 复用 Anthropic error envelope oracle，但 upstream 改为 Responses 429 与 stream `response.failed`，同时断言 HTTP status、body type/message、history terminal 和未泄漏成功帧。

13. **重试/buffering｜major｜假绿风险：高**
    - 可移植 oracle：`/home/xp/src/copilot-api-js/tests/anthropic/streaming-l2-buffered.http.test.ts:187`，测试 `2 mid-stream RSTs then complete → client transparently receives ONE complete generation, history completed`；`:266`，测试 `acc reset regression — even 3 leading RSTs commit a single non-summed generation`；`:282`，测试 `retries exhausted ... synthetic error, NO message_stop`；`:393`，测试 `block committed ... THEN RST ... un-retryable partial-degrade`。另有 `/home/xp/src/copilot-api-js/tests/anthropic/commit-window-ingress-deadline.http.test.ts:121` 的 partial-budget oracle，以及 `/home/xp/src/copilot-api-js/tests/anthropic/pre-response-abort.http.test.ts:97` 的 499/aborted oracle。
    - 缺口：这些 suite 均把模型限制在 `/v1/messages` upstream；`/home/xp/src/copilot-api-js/tests/anthropic/reactive-retry-legs-wiring.http.test.ts:96` 等 reactive retries 也只 mock `/v1/messages`。没有 `@responses` translated stream 上的 RST-before-commit、RST-after-commit、buffer reset、retry exhaustion、pre-response abort 或 ingress deadline 组合测试。
    - Python：移植“最终客户端只见一代”“失败尝试 usage 不累加”“commit 后绝不重发”“exhaustion 无成功 terminal”“abort=499 而非 failed”这些行为 oracle，并把 fixture 改为 Responses lifecycle events；仅移植 direct Messages fixture会造成同样的接缝假绿。

## 移植优先级

1. 先移植第 1～6、8～9 条的纯函数与独立 consumer oracle，作为 Python translator 的快速回归层。
2. 在宣布 bridge 可用前，必须补齐第 7、10～13 条的 direct-only 接缝测试；它们是当前主要假绿来源。
3. 保留两类 oracle：精确 wire/object equality 负责字段与顺序，独立 SDK/parser 或真实 driver 负责证明事件真正可消费、路由真正接线。两者不能互相替代。

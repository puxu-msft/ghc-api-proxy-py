# Anthropic Responses bridge happy-path 独立验收

## Verdict

**本阶段 PASS。完整 bridge 仍为 `UNVERIFIED`。**

精确验收对象为 `/home/xp/src/ghc-api-proxy-py-integrate-happy` 的 `integrate/260807-bridge-happy-path@d78b3cdc172ecad42873a70f1df31438ecca1663`，base 为 `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。在 current Spec 指定的本阶段范围内，未发现用户可观察偏差：项目主 carrier、`copilot-api-js` 合法 v1 消费兼容与 direct Messages strip；route policy；Anthropic request → Responses request；Responses non-stream → Anthropic text／tool／reasoning／public identity／基础 usage；stream semantic parser 的 complete-only 与 order facts 均通过独立 probe。

本轮明确不接真实 route，不验证完整 lifecycle、HTTP／SSE sink 或网络 transport。因此，本报告的 PASS 只能作为 happy-path primitives／pure-path checkpoint 的阶段结论，不得解释为完整 Anthropic Responses bridge 已符合 Spec。

## 验证基线与独立性

- **Current Spec**：主树 working-tree `docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，状态为 `FINALIZED`。
- **候选**：`integrate/260807-bridge-happy-path@d78b3cdc172ecad42873a70f1df31438ecca1663`。
- **Base**：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79`，已用 `git merge-base --is-ancestor` 验证为候选祖先。
- **oracle 构造顺序**：先读取 current Spec 并独立抽取本阶段验收矩阵，之后才读取候选实现和候选测试。
- **只读约束**：所有 Python／pytest 运行均设置 `PYTHONDONTWRITEBYTECODE=1`，Python 使用 `-B`，pytest 使用 `-p no:cacheprovider`；候选树在全量测试和 pure-path probe 后的 `git status --short` 均为空。
- **唯一持久化写入**：主树本报告 `docs/tmp/260807-verify-happy-path.md`。未修改候选生产代码、测试、fixture 或配置。
- **独立 probe 形态**：使用 stdin Python 脚本直接调用候选 public primitives，不读取或复用候选测试 fixture／expected；未生成候选树内测试资产，以满足“候选只读、唯一写主树报告”的本轮约束。

## 从 current Spec 抽取的本阶段验收矩阵

| ID | Current Spec 阶段 oracle | 独立输入与判据 | 结果 |
|---|---|---|---|
| HP-1 | 本项目 producer 使用项目主 v1 carrier；consumer 接受 `copilot-api-js` upstream v1 合法主路径、bare prefix 与 legacy sentinel；direct Messages 无条件 strip 项目 synthetic namespace 与 upstream synthetic forms | 断言项目 canonical `opaque-😀` 向量 byte-exact；解码 upstream `ENC==` 与 `opaque-😀` 合法向量；检查 bare／legacy 分类；把项目 v1、upstream payload、upstream legacy、项目 unknown version、native Anthropic signature 和 text 一起送入 direct preparation | **PASS** |
| HP-2 | route policy 使用 resolved model capability；Responses-only 选 Responses；双支持无 override 默认 Messages；unknown capability fail closed | Responses-only model＋仅 Responses HTTP 可用，断言选择 Responses；双支持 model 断言默认 Messages；空 capability 断言 `CAPABILITY_MISSING` | **PASS** |
| HP-3 | route 选定 Responses 后，每个 attempt 从 Anthropic canonical request 转换 Responses wire；system、turn、reasoning、text、tool call／result 与 tool name mapping 保序且语义稳定 | 同一 pure path 中先 route 选 Responses，再转换含项目 carrier thinking、assistant text、tool use、tool result、user text、named choice 的请求；断言 wire 类型顺序为 `reasoning → message → function_call → function_call_output → message`，carrier 恢复 `CONT-OLD`，声明／choice／历史 call 使用同一 wire name | **PASS** |
| HP-4 | complete Responses non-stream body 转为 Anthropic text／tool／reasoning，保持语义顺序；每个 reasoning item 一对一，encrypted-only 不丢失；tool name 恢复；public identity 不泄漏 upstream id；基础 usage 使用 `I=max(0,T-R-W)` | 模拟 body 顺序为 reasoning(summary＋`ENC-1`) → 两个 text part → function call → encrypted-only reasoning(`ENC-ONLY`)；输入 `T=100,R=20,W=10,O=30`；断言 Anthropic block 为 `thinking → text → text → tool_use → thinking`，tool name 恢复，两个 carrier 分别还原 payload，public id 为不含 `resp_` 的稳定 `msg_`，usage 为 `I=70,R=20,W=10,O=30` | **PASS** |
| HP-5 | producer → client echo → consumer 在普通模式下对 non-empty `encrypted_content` value-exact 往返，保持 item cardinality | 把 HP-4 产生的两个 public thinking blocks 原样放入下一轮 assistant message，再走 request converter；断言恢复两个独立 reasoning items，payload 依次为 `ENC-1`、`ENC-ONLY` | **PASS** |
| HP-6 | stream semantic parser 在 authoritative completion 前不产生 `CompletedBlock`；输出 source order 与 completion order 是独立 typed facts，不得把完成先后误当语义顺序 | 先打开 text，后打开 reasoning 与 function call；让 reasoning、tool、text 逆 source order 完成。所有 delta／summary done／arguments done 前均断言零 `CompletedBlock`；最终 source order 为 `TextBlock → ReasoningBlock → FunctionCallBlock`，completion order 为 `ReasoningBlock → FunctionCallBlock → TextBlock`，terminal 为 completed 且无 open block | **PASS** |

## 独立纵向 pure-path probe

纵向 probe 没有调用真实 route handler 或网络 transport，按本轮明确边界直接串联：

1. `decide_protocol_leg()` 选择 Responses。
2. `convert_messages_request_to_responses()` 转换 Anthropic request，并保留 request-scoped `ToolNameMapper`。
3. 构造一个 complete 模拟 Responses JSON body。
4. `convert_responses_response_to_anthropic()` 使用同一 mapper 转换 non-stream response。
5. 把产生的 public thinking blocks 原样 echo 回 `convert_messages_request_to_responses()`，验证 carrier 往返。
6. 单独驱动 `ResponsesStreamParser` 的 interleaved lifecycle events，验证 complete-only 与两类 order facts。

关键实际输出：

- `BASELINE_VERTICAL_PASS {'route': 'responses', 'wire_types': ['reasoning', 'message', 'function_call', 'function_call_output', 'message'], 'content_types': ['thinking', 'text', 'text', 'tool_use', 'thinking'], 'public_id': 'msg_aIewDcmN1Dx7M3aRWFd9Tkrol0uFMeeA'}`。
- `BASELINE_STREAM_PASS {'semantic_source': ['TextBlock', 'ReasoningBlock', 'FunctionCallBlock'], 'completion_sequence': ['ReasoningBlock', 'FunctionCallBlock', 'TextBlock']}`。
- probe 进程退出码为 0。

这条 probe 证明本阶段 primitives 可以在不经过 Chat Completions、也不经过真实 route 的情况下形成 direct semantic pure path；它不证明这些 primitives 已接入唯一 production lifecycle owner。

## 正控变异

为证明 HP-4／HP-5 的 reasoning cardinality 与 encrypted-only no-loss 判据不是 false-green，本轮在同一 Python 进程内临时 monkeypatch `app.protocols.responses_anthropic.responses_reasoning_to_anthropic`：当 reasoning item 的 `summary=[]` 且存在非空 `encrypted_content` 时，故意返回空 block 列表。未修改任何候选文件。

正控结果：

- baseline 真实实现先通过完整纵向 probe。
- 注入“丢弃 encrypted-only reasoning item”缺陷后，同一纵向断言转红。
- 关键输出为 `POSITIVE_CONTROL_RED`，实际 public content 仅剩首个 thinking、两个 text 与 tool_use，缺失末尾 encrypted-only thinking block。
- finally 恢复真实函数后，同一纵向 probe 再次通过，输出 `POST_MUTATION_RESTORE_PASS`。
- 整个正控 harness 退出码为 0；这里的 0 表示 harness 成功观察到预期红灯并完成恢复，不表示变异实现通过。

该正控直接命中目标机制：若实现重新引入 encrypted-only 丢失或 reasoning item cardinality 收缩，本轮纵向 oracle 会失败。

## 现有测试与交叉核对

### 全量现有测试

运行边界：候选 `d78b3cdc172ecad42873a70f1df31438ecca1663` 的完整 `tests/`，解释器为主树 `.venv/bin/python`，import root 显式绑定候选 `src/`。

结果：`418 passed in 8.17s`，退出码 0。

### 测试数量交叉核对

另以不同执行模式运行 pytest collect-only，不执行测试体，只枚举 node ids。

结果：`418 tests collected in 2.84s`，退出码 0。collect-only 的 418 与实际执行通过的 418 一致；该数字口径均为候选 HEAD `d78b3cdc172ecad42873a70f1df31438ecca1663` 的完整 `tests/`。

### 补充 oracle

独立补充 probe 对项目 canonical carrier、两个 upstream 合法向量、upstream bare forms、双支持默认 Messages 与 unknown fail-closed 逐项断言，输出 `SUPPLEMENTAL_ORACLE_PASS project_vector upstream_vectors bare_forms dual_default fail_closed`，退出码 0。

一次补充 probe／collect-only 尝试曾被外部 `SIGINT` 中断并混入另一 worktree 的并发终端输出，退出码为 2；该轮已明确废弃，未作为任何 PASS 或计数证据。随后使用独立进程组重跑，并从隔离 `/tmp` 输出文件取得上述干净证据。

## 明确未验证范围

以下均超出本轮冻结的 happy-path primitive／pure-path 范围，全部保持 **`UNVERIFIED`**，不得从本阶段 PASS 外推：

- 真实 `/v1/messages` route 是否调用本轮 route policy、request converter、Responses transport、non-stream converter 或 stream parser；本轮按要求不接真实 route。
- Anthropic pipeline 是否仍是唯一 lifecycle owner，以及 single `RequestContext`、approval once、attempt sequence、retry owner、History entry、hooks、tokenization observer 与 finalize exactly-once。
- `PRE_SEND` 后每 attempt 重新转换，以及 retry 修改是否进入下一 attempt wire；本轮仅调用一次 pure request converter。
- 真实 Responses HTTP JSON、HTTP SSE 与 upstream WebSocket transport；认证、headers、request close、network error、frame parsing、CRLF／multi-line SSE／fragmentation 与 clean EOF truncation。
- downstream Anthropic HTTP／SSE wire rendering；首完整 block 前零 success headers／`message_start`／body event；完整 block envelope、commit frontier、sink batch、post-commit partial failure 与 no-dup delivery。HP-6 只验证 parser semantic facts，不验证 sink。
- stream 与 non-stream 对同一完整 fixture 的 normalized Anthropic message／usage／stop reason／error 等价；本轮 stream parser 未连接 response renderer。
- refusal、incomplete／`max_tokens`、failed／error mapping、unknown item、server-tool no-revive、malformed tool arguments和 malformed lifecycle 的完整错误矩阵。
- usage 的 `output_tokens_details.reasoning_tokens`、`Q>O` inconsistency、`T<R+W`、usage absent／estimated、非法数值、failed-attempt usage 隔离和 diagnostic fact 持久化；本阶段只验基础 cache usage 向量。
- `stripThinkingSignature` 显式有损 policy 及 conversion fact；本轮只验普通 producer／echo 和 direct Messages 无条件 strip。
- capability 的 streaming、vision、parallel tool、reasoning effort、context／output／image limits 逐字段 gate，以及 override／transport unavailable 的完整用户错误 envelope。
- memory budget、admission、backpressure、queue、cancel、shutdown、deadline、quota charge／release、资源关闭、无 spill 与禁止 live forwarding。
- public `msg_` identity 在真实 HTTP response 中的最终可见性，以及 upstream `resp_`／resolved model 在 History／trace 中的持久化；本轮只验证 converter typed result。

## 最终结论

候选 `d78b3cdc172ecad42873a70f1df31438ecca1663` 在用户指定的本阶段范围内 **PASS**：项目主 carrier 与 upstream v1 compatibility、direct strip、route policy、request conversion、non-stream text／tool／reasoning／public identity／基础 usage，以及 stream parser complete-only／order facts均有实际运行证据。全量现有测试通过，测试数量经 collect-only 交叉核对；独立纵向 oracle 经 encrypted-only 丢失正控证明具有判别力。

**完整 bridge 仍为 `UNVERIFIED`。** 尤其是真实 route wiring、single-owner lifecycle、transport、SSE sink、commit／retry、History／hooks／tokenization、resource limits 与 error matrix 均不在本轮 PASS 内。后续只有在这些范围分别完成独立验收后，才能提升完整 bridge verdict。

> 本报告由 verifier 叶子执行单元生成。按协作规则，报告本身仍需主会话安排独立 review；本轮 verifier 不派生 reviewer，也未修改生产代码。

# sxwxs/ghc-api 对本项目的可借鉴项：对照与裁断

> 日期：2026-08-21。被调研对象：`sxwxs/ghc-api`，HEAD `0cb1087`（2026-08-17），Flask + waitress + requests，107 个 py 文件，244 个提交（2026-02 起）。
> 本项目对照基线：`/home/xp/src/ghc-api-proxy-py`，`main`，HEAD `172adc2`。
> **本文已经过两轮异源核查并据此修订**（核查记录见 §7）。五份精读报告与两份核查报告同目录：
> - `260821-survey-ghc-api-core-translation.md`（转换与 SSE，823 行，含实测探针）
> - `260821-survey-ghc-api-reliability.md`（重试 / 保活 / 超时 / token）
> - `260821-survey-ghc-api-observability.md`（历史 / 统计 / 基准）
> - `260821-survey-ghc-api-periphery.md`（认证 / profile / ACP / 部署）
> - `260821-inventory-our-capabilities.md`（本项目能力面盘点）
> - `260821-verify-our-side-claims.md`（核查我方主张，判定 needs-fix）
> - `260821-verify-ghc-api-claims.md`（核查 ghc-api 转述，49 条中 39 忠实 / 7 过度概括 / 3 失真）

## 0. 这两个项目的关系

同源程度超出预期：都是 GitHub Copilot 代理，主路径都是 **Anthropic Messages 入 → OpenAI Responses 上游**，都用自有版本化 reasoning 载体承载 `thinking.signature`，都独立发现了「Copilot 在同一个 item 的 `output_item.added` 与 `output_item.done` 之间换掉 `item.id`」这个上游缺陷，也都独立选择了用 `output_index` 而不是 id 做跨事件身份键。它的 `benchmarks/e2e/compare_copilot_api_js.py` 甚至就是拿 `copilot-api-js` 做对照基线。

它的价值因此不是「一个可以抄的参考实现」，而是**一个在同一片雷区里独立走过一遍的同行**：它踩到的坑与我方的坑高度重合，所以**它的错误比它的正确更有信息量**。

对照前必须先划清一件事：本项目仓库里有**两条完整链路**，随 CLI 启动的只有 `pipeline_app` 那条。`src/app/server/app_factory.py` 那条（连带 `src/app/routes/`、`src/app/hooks/`、`src/app/history/sqlite/`、`src/app/delivery/`、`src/app/openai/responses_stream_parser.py`、`src/app/pipeline/executor.py`、`src/app/anthropic/client.py`）是一棵**仍然完整、可被显式 import 的 dormant 生产模块图**，不是「只被测试引用的死代码」。下文所有「我方已有 / 没有」一律指**活链路**；凡 legacy 已实现的会单独点出——因为那意味着实现成本大幅低于从零做。

## 1. 对照确认：我方做对了的四处

不需要行动，但值得知道有第二个实现独立到达了同一结论。

| 事项 | 我方 | ghc-api |
|---|---|---|
| item id 不稳 → 用 `output_index` 做键 | `delivery/assembler.py:238-254` `_item_key`，id 只作缺 index 时的 fallback | 同解，且**多一层**：把「id 稳不稳」升格成 `ResponsesWireProfile.stable_ids` 能力位。注意其门控范围有限——只管上游 item id / response id 这一类会被每帧重新加密的标识，`call_id` 与工具名变异**无论方言如何都强校验**（`sse/anthropic_responses.py:296-312`） |
| 保活计时读自己那一侧 | `delivery/stream.py:40-46, 154-202`：`_LastWrite` 记「最后一个字节交给客户端的时刻」，在 `yield` 返回**之后**打戳 | **装反了**：`q.get(timeout=interval)` 被上游每一行重置。它的翻译路径对 tool call / reasoning 整块缓冲，于是上游忙、下游零字节时 ping 永不触发，且无测试覆盖、项目自己未意识到 |
| 自有版本化 reasoning 载体 + 严格解码 | `translation_driver/reasoning_carrier.py:103-151`：canonical base64url 往返校验、拒重复键、键集必须恰好相等 | 同构（`ghc-api:responses-reasoning:v1:`），另有三条策略我方可补，见 §2.6 |
| 上游行为靠录制而非手写替身 | `tests/int/cassettes/` + `recorded_provider.py`：真 provider、真 SDK、真 token manager、真 token exchange；**替身是 `ReplayTransport` 与 `RecordedTokenSource` 两个**（`recorded_provider.py:35-51`） | 同源理由：它的方言能力位注释写着「dump 证明了 `prompt_cache_key` 但没证明 explicit breakpoints，所以后者取保守值」。**但它的 `benchmarks/e2e/fake_backend` 是手写的，只能测性能不能测正确性**，见 §3 |

## 2. 值得采纳的（按 ROI 排序）

### 2.1 fail-open / fail-closed 的判据应该是「可恢复性」，不是「未知性」——但我方不满足它的前提

**判据本身是整份调研里最值得学的一条设计原则。**

ghc-api 的边界表（写在 `docs/decisions/ANTHROPIC_RESPONSES_WEB_SEARCH_COMPATIBILITY_DECISION.md` 结尾，逐行已回代码核实）：

| 漂移形态 | 处理 | 理由 |
|---|---|---|
| 未知 SSE **事件类型** | 告警并跳过 | `response.completed` / `.incomplete` 携带完整 `output` 数组，`_hydrate_terminal` 会把它合并回来——只是延迟到流末而非增量 |
| 未知 **output item 类型** | 拒绝，502 | 它要么作为内容到达客户端、要么根本不到达；**没有任何后续事件会以已知形状重述它** |
| 未知 **content part 类型** | 拒绝，502 | 同上，低一层。**执行者是审计层 `compat_profiles.audit_responses_event`（`fail_always=True`）而不是转换器**——转换器本身对未知 part 是静默放行的（`sse/anthropic_responses.py:894-902`、`anthropic_responses.py:1834-1835`） |
| 未知**非流式 `response.status`** | 拒绝，502 | body 已是终局，status 正是区分完整 / 截断 / 失败的那个字段 |
| 流结束但无终局事件 | 拒绝，502 | 终局对账从未运行，被跳过的事件永远补不回来 |

判据一句话：**这个漂移的形状还有没有第二次被对账的机会**。有就放行，没有就拒绝。

**关键限定（核查证伪了我的初版建议）**：这条判据里「未知事件可以跳过」成立，**完全依赖于终局对账真的会重放完整 `output`**。我方**没有这个机制**——`delivery/assembler.py:323-340` 的 `_read_terminal` 只读 `usage`、`incomplete_details.reason` 并设 `seen` / `stop_reason`，**从不读 `response.output`**；`delivery/stream.py:266-294` 在事件循环结束后只 flush 已交给 `DeliverySession` 的 block，没有第二次 response-body 对账。

所以我方当前的行为是：

- 未知**事件类型** → `assembler.py:218-236` 静默 `return ()`，**内容永久丢失**，无日志、无 loss、无错误。
- 未知 **output item 类型** → 正常 `added → done` 生命周期的被猜成 `{"type":"text","text":draft.text}`（`assembler.py:295-321`）；**只有 `done` 没有 `added` 的直接被丢弃**（`:279-294`，`web_search_call` 除外）。

也就是说我方在**两档上都选择了 fail-open，而且两档的可恢复性前提都不成立**。legacy 链路反而更严（未知事件与未知 item type 都标 `UnsupportedResponsesEvent`，最终抛 `unsupported_responses_event`；`unknown_output_item` 是另一个错误码，指「事件引用了从未打开的 `output_index`」）——这是新链路相对旧链路的一处**未登记的能力退化**。

修正后的建议：**在实现终局 output 对账之前，两档都不能 blanket fail-open**。最小动作是给两档都记 loss 并接出口（见 §2.2）；是否升级为 502 取决于用户对「宁可断也不猜」的取舍。若要保留未知事件跳过，就得先补终局对账——那才是 ghc-api 那一行的前提。

权重：判据 **强到可直接采纳**；「我方前提不成立」**强到可直接采纳**（核查员读完了 `_read_terminal` 与 `stream_delivery` 的全部终局路径）。

### 2.2 翻译损失：有清单、无读者

我方 `LossCode` 十个码、`Conversion.record()` 逐条累积、`TranslationRefused` 带 `field_path` 映射 400——契约面已经铺好。但 `context.extras["conversion_losses"]` 与 `["response_conversion_losses"]` **全仓无读者**（`handler.py:116-125`、`:199-207`、`:406-413` 三个写点；`pipeline_app.py:345-362` 的 `extras` 生产读点只读 count-token 键，也没有遍历或整体序列化 `extras` 的间接出口）。翻译丢了什么，运行时没有任何信号。

ghc-api 的 `X-GHC-Compatibility-Warnings` 三段分工可直接套，且三段可独立采纳：

1. **头只放 code 集合**（排序、逗号连接、截到 1024 字节），代码注释明说「这是诊断线索不是权威报告」；
2. **完整列表进请求记录**（我方对应 `RequestLine` / JSONL）；
3. **日志按五元组 `(code, path, profile, cli_version, fingerprint)` 五分钟去重打印，但计数不去重**（`routes/anthropic.py:148-166`，`counters.incr` 在 `if should_log` 之外）——计数给频率，打印给样本。另有 4096 条上限的老化。

我方 `RequestLine` 已是聚合记录、`request_log_file.py:31-49` 已每请求写一行 JSONL，把 loss code 集合塞进去成本极低。这是**已经付过成本的机制没有出口**，ROI 最高的一条。

一个限定：JSONL 那一行不是绝对保证——写函数捕获所有异常返回 `None`，`pipeline_app.py:271-281` 在 `_dispatch` 抛 `BaseException` 时只摘 active request 后重抛、不写 completion，未注册路径由 FastAPI 直接回答。准确说法是「每个正常完成并到达 completion accounting 的已注册代理请求 best-effort 落一行」。

顺带一条它的教训：**记账必须发生在知道结果之后**。它的 `_map_reasoning_effort` 在确认 `thinking` 是 dict 之后、不管 `thinking.type` 是什么都先 `mark("/thinking/type", SEMANTIC, "/reasoning/effort")`（`anthropic_responses.py:841`），随后三个分支（`disabled` / `adaptive`|`auto` / `enabled`）都不命中就 `return None`（`:866`）。于是这个叶子「已记账」（不进 `unaccounted_paths`）、处置是 `semantic`（不产告警），实际什么也没发生——**审计线索说它被映射了，而它被静默吞掉了**。这正是那套机制存在的理由所要防的失败。（两名独立调研员各自实测复现。）

权重：**强到可直接采纳**。

### 2.3 `thinking` 请求参数在活链路没有落地——但 legacy 已有完整实现

活链路：`thinking` 不在 `_PASSTHROUGH_KEYS`（`anthropic_messages.py:31-33`），进 `extensions`，而 `semantic.py:116-128` 的 `extensions_for` 在跨格式时**整体清空**并记 `EXTENSIONS_NOT_CARRIED`。客户端设的 `thinking.budget_tokens` 到不了上游，推理档位完全不受控。

**但这不是「项目从未实现过」**：能力事实定义在 `src/app/protocols/anthropic_responses.py:60-100`，完整的 `thinking` budget → explicit effort 映射与范围校验在 `:251-351`，legacy 链路已实现并测试。所以这是**新链路没接线**，而不是要从零做——实现成本大幅低于我初版判断。

ghc-api 的对应实现可作参照，但**它的写法只兑现了一半**：优先读 `output_config.effort`；否则从 `thinking` 推断——`disabled` → `none`（不支持则退 `low`）、`adaptive`/`auto` → `high`（不支持则取方言列表最后一项）、`enabled` 按 `budget_tokens` 分档。分档的五档里**只有 `max`（≥30000）和 `xhigh`（≥16000）检查了 `profile.reasoning_efforts`，`high` / `medium` / `low` 三档是硬编码的名字**（`anthropic_responses.py:854-863`）。当前三个方言恰好都含这三个名字，所以漏检不发作；方言表一变就会静默发出上游不认的 effort 名。

准确的可采纳表述：**把 effort 名当成能力位查表而不是硬编码——ghc-api 只在两档做到了，抄的时候要补齐五档**。阈值本身是经验值，我方自己定。

这是本次唯一一条**用户可感知的能力差距**。

权重：机制 **强到可直接采纳**；阈值 **仅存档**。

### 2.4 三条具体的上游兼容性事实（我方三条都没做）

都是 ghc-api 踩坑之后加的，核查已确认我方活链路**均未处理**：

1. **工具 `description`：缺席 ≠ 空**。Copilot 的 `/responses` 拒绝「存在但为空」的 description；缺席是合法的，转换后必须保持缺席。ghc-api 对**空串、纯空白、以及任何非字符串值**替换成确定性替身 `f"Tool: {name}."`，对缺席不动；三个分支都有测试，还断言合法无描述工具**不产生任何告警**（`anthropic_responses.py:1048-1057`）。
   我方：`translation_driver/openai_responses.py:126-141` 只把 `input_schema` 改名为 `parameters`，其余字段原样保留，空串原样进上游。legacy 的另一套 converter 同样只是「非 `None` 就写」。**确认是缺口。**
2. **孤儿 `tool_result` 与孤儿 `tool_use` 处理方向相反**。孤儿 `tool_result`（历史截断 / 压缩 / 客户端编辑造成）会让上游整个调用失败在 `No tool call found for function call output`，所以在转换器本地丢弃；孤儿 `tool_use` **保留不动**，因为合成一个 output 等于编造模型从未产出的工具答案。代码注释逐字给出这两条判据（`anthropic_responses.py:677-694`）。判据是「上游会不会硬失败」与「补偿会不会编造内容」，不是对称性。
   我方 `anthropic_request_hook.py:102-123` 的 `repair_tool_pairs` **两个方向都删**，且落在活链路上（`handler.py:95-110` → `shape_request`）。方向差异需要裁一次：删孤儿 `tool_use` 会丢掉模型确实产出过的调用记录。
3. **剥离客户端注入的合成计费头**。Claude Code 会在 system 里注入 `x-anthropic-billing-header:` 开头的文本，直接发给上游模型是污染。ghc-api 整块丢弃并记 `semantic`（字符串 system 与 block 数组两条路径都有）。
   我方 active pre-translation fixup 只处理 context management、tool pair 与 thinking layout；system blocks 原样读入、原样拼接。注意 `config/settings.py:93-105` 有个同名 blacklist，那是 dormant legacy 的 **HTTP request header** 配置，不是 system 文本过滤，**不要误认成同一机制**。**确认是缺口。**

权重：均 **强到可直接采纳**（ghc-api 侧代码 + 测试双证；我方侧逐条回代码核实）。

### 2.5 严格 JSON 解析用在上游返回的 function call arguments 上

三层严格解析里唯一一条我认为必须采纳的。它的 docstring 把利害写得很清楚：把标量、数组、畸形 JSON 或**含重复键的对象**当作 Anthropic `tool_use.input` 发给客户端，会让 CLI 按一个不同的契约执行调用。测试遍历 `"[]"` / `"1"` / `"null"` / `"not-json"` / `'{"x":1,"x":2}'` 五个样本，断言每个都出 error、都不产生 `content_block_start`。

**我方确认有这个缺口**：流式路径 `assembler.py:296-303` → `:375-380` 用 `orjson.loads`；非流式 `openai_responses.py:331-339` → `:398-409` 用标准库 `json.loads`。两者都不检查结果必须是 object，也不用 duplicate-key hook。核查员的运行探针显示：`{"x":1,"x":2}` 两者都得到 `{"x":2}`；`[]` / `1` / `null` 分别得到 list / int / `None`，这些值随后成为 Anthropic `tool_use.input`。畸形 JSON 的行为也不一致——流式包成 `{"__raw": raw}`，非流式保留原字符串。

另两层（全局嵌套深度守卫、请求体严格解析）：

- **嵌套深度守卫**（84 行、无依赖）防的是真实故障——`request.get_json()` 在足够深的 body 上抛 `RecursionError` 而 `silent=True` 不捕获它；下游 `copy.deepcopy` 约 500 层就崩。它不靠 `RecursionError`（CPython 的 C scanner 到约 10k 层才抛，早就来不及了），改用结构字节线性扫描、限值 100 层，并显式论证了为什么不用正则匹配字符串字面量（每个开启未终止字面量的引号都要付一次全长失败匹配，整体变二次）。我方是 FastAPI + orjson，故障形态未必相同，**需先确认我方有没有这个故障**再决定。
- **请求体拒绝重复键 / NaN / 尾随数据**：收益真实但会拒掉部分合法客户端。建议先在我方 cassette 上统计是否真出现过歧义体。

权重：function arguments 那条 **强到可直接采纳**；另两层 **存疑**。

### 2.6 reasoning 载体的三条策略（与编码格式无关）

我方载体机制完整，但活链路把 `decode_reasoning_carrier` 的**九态分类塌缩成二分**（`anthropic_messages.py:50-64` 只特判 `foreign`，其余八态全归 `PROXY_CARRIER`）。后果：畸形载体（`project_malformed_v1` / `upstream_malformed_v1`）与合法裸载体同形，都只还原 summary，**畸形不产生任何信号**；未来的 v2（`project_unknown_version`）被静默降级成裸 v1 而不是被拒或记 loss。legacy 在同一位置做得更细（`anthropic/thinking/responses_reasoning.py:92-120` 对 unknown version、两种 malformed 与 foreign 都返回无 item，并保留 classification / malformed 标志）——又一处新链路相对旧链路的退化。

ghc-api 的三条策略可直接套到我方自有载体：

1. **解析区分三种结局**：不带前缀 → 返回 `None`（外来签名，不是我们的东西）；带前缀但畸形 → 抛错，让调用方丢掉损坏的不透明状态、**保留可见的 summary**、并报一条兼容告警；合法 → 返回载体。
2. **模型 / 方言不匹配时保 summary 丢密文**，而不是整体失败。它把 `wire_profile` 与 `model` 都写进载体，回程校验不上就降级为 approximation。
3. **跨路径剥离**：请求转去原生 Anthropic 端点之前把自签的 thinking 块摘掉——把伪造的 thinking signature 发给原生 Anthropic 模型会被上游拒。我方有 `is_direct_messages_synthetic_signature`，需确认调用点覆盖了所有出口。

权重：**强到可直接采纳**。

### 2.7 `ResponsesWireProfile`：值得抄的是规则，不是那 13 个字段

它有两个都叫 profile 的东西，职责完全不同——`compat_profiles.py` 里的 `CompatibilityProfile` 是客户端身份 / 漂移审计（name / protocol / cli_version / anthropic_version / betas / fingerprint），真正的能力矩阵是 `anthropic_responses.py:268-285` 的 `ResponsesWireProfile`：**13 个能力位**描述「这个上游方言收不收 `temperature`、tools 放顶层还是塞进 input、它的 id 稳不稳」。三个方言：GPT-5.x 的 `copilot_responses_lite`、Grok 的 `copilot_public_responses`、真 OpenAI 的 `public_responses`。

没有这层抽象，这些差异会以 `if model.startswith("grok-")` 的形式散落在转换器的几十个分支里。

值得抄的三条规则：

1. **能力位由录制证据决定，未被证明的取保守值**，并把证据出处写在字段旁边的注释里；
2. **能力位要能影响流式不变量的强弱**，而不只是请求体字段——`stable_ids` 是最好的例子，它让「校验 id 一致性」从「要么全做要么全不做」变成 per-方言的选择；
3. **方言名要进 reasoning 载体**，这样跨方言的历史重放会被识别并降级，而不是把 A 方言的密文喂给 B 方言（我方载体已有此形）。

一个它自己没理清的地方：`copilot_public_responses` 同时是 `stable_ids=False` 和 `preserves_reasoning_item_ids=True`，而且两个位都真在用——一边宣布「这个 id 每帧重新加密不能用作身份键」，一边又把它塞进 reasoning 载体发回上游。**我方若采纳，应把「能不能拿它做跨事件比较」与「能不能把它发回上游」拆成两个位。**

我方当前只服务一个上游、没有方言选择点，所以这是**中期候选**而非当下动作。但它揭示了一个我方迟早要面对的问题：上游不是一个方言。

权重：三条规则 **强到可直接采纳**；13 个字段值 **仅存档**。

### 2.8 可靠性上的四条小项（核查后两条转为「我方已具备」）

1. **重试时重建 headers 而非复用同一个 dict**。ghc-api 的 docstring 把两个真实故障写出来了：复用会在 token 刷新后重发旧 token（把可恢复重试变成 401），并让多次尝试共用同一个 `X-Request-Id`（破坏上游关联与去重）。它自己在 direct Anthropic 路径上正好违反了这条——headers 在 `for attempt` 循环**之外**只算一次。
   **我方已正确**：`direct_driver/base.py:126-146` 每轮重走 provider send，`ghc_client/client.py:46-98` 每次重取 token 并构造新 dict，`ghc_client/headers.py:35-47` 每次生成新 request id。只复用 `context.client_headers` 这个只读输入映射，合并结果仍是新 dict。**不是缺口。**
2. **早期失败重试的判据是一个布尔闸门，不是字节计数器**：「上游 SSE 里出现了一个不在序幕事件白名单（恰好 `response.created` / `.in_progress` / `.queued` 三个）里的事件类型」即永久关闭重试。取向是 fail-safe 偏向不重试——**畸形 JSON 载荷也算内容因而提交**，注释原文「a malformed data payload is still downstream-visible output and therefore commits the stream」。
3. **绝不读 `stream=True` 响应的 `.text`**（做成 property 并配一条专门的回归测试 `test_construction_does_not_read_the_streaming_body`）——读 `.text` 会走 `Response.content` 把整条流吸干。
   **我方情况需登记但不必恐慌**：成功的流式 body 只由 `pipeline_app.py:401-441` 的 `aiter_bytes()` 消费，没有整体读；但 SDK 对 stream 请求抛 status error 后走 `ghc_client/client.py:100-114` 归一化，而 `ghc_client/errors.py:62-77` 会访问 `response.text`。这条访问是否吸流取决于 SDK 在构造异常前是否已消费 error body（httpx 对未读流的 `.text` 会抛 `ResponseNotRead`），**不能写成「必然吸干成功 SSE」**，但路径本身该登记并用锁定版本测一次。
4. **「不设读超时的长连，必须由并发上限而非超时兜底」**。ghc-api 的 Web IQ MCP GET 故意 `(connect, None)`，配一个 4 路并发上限对 16 线程池，超限**立即 503 + `Retry-After: 1`** 而非排队。这个配对关系与具体协议无关。
   **我方不匹配这个前提**：`InFlightLimit` 超限确实是排队（`server/admission.py:25-49` 的 `asyncio.Semaphore`），但我方**没有无读超时的长连**——固定环境探针显示 OpenAI 与 Anthropic SDK 对共享 httpx client 实际使用 `Timeout(connect=5.0, read=600, write=600, pool=600)`，且默认 attempt 总 deadline 1200 秒同时覆盖响应头与 body。`stream_idle` 默认 0 只是关掉额外的业务 idle guard，不等于没有读超时。**这条对我方不成立**（升级 SDK 后应重测，不能只看 composition 未显式传 `timeout`）。

权重：1–3 **强到可直接采纳**（其中 1、3 是「我方已具备 / 需登记」而非缺口）；4 **对我方不适用**。

### 2.9 pre-header 分流的判据

ghc-api 的 D1：**按「有没有拿到 HTTP 响应」分流，而不是按「快不快」**。早期版本对所有非 2xx 都走流式（提交 200 + 合成 SSE 错误），结果客户端丢掉 429（不再退避，反而重试更凶，放大了这个机制本来要治的循环）、丢掉 401（不再重新鉴权），面板与客户端看到的状态还不一致。`ConnectionError` 意味着「没有响应存在」，所以它归流式路径是自洽的。代码兑现了这条：立即拿到但非 OK 的落回普通路由循环并保留原始 HTTP 状态与 body。

我方形态不同：`handler.py:325-357` 的 `error_status` 透传 `UpstreamRejected.status_code`，非流式没有这个问题；流式路径的 `synthesized_response_headers_after_sec` 默认 240 秒（`config/schema.py:258-266`），比它的 0.5 秒保守得多，被误锁成 200 的窗口小得多。**所以这条对我方不是缺口，是判据本身值得记下。**

另有两条它的配套教训：

- **参数钳制 `min(max(0.0, x), 5.0)` 一行，参数顺序有意义**（`max(0.0, nan)` 是 `0.0`，`max(nan, 0.0)` 是 `nan`）——这一条**在代码注释里逐字写着**。不钳制的后果不是良性的：负数让 `queue.Queue.get(timeout=)` 抛 `ValueError`（每个流式请求变 500），`inf` 抛 `OverflowError`，`nan` **静默**关掉超时退回旧的阻塞行为、任何地方都不报错。决策文档明说这一行取代了原先一整张说明表——「防御性散文应当变成可执行代码」。
- **失效模式的不对称性决定默认值方向**：太小是**静默**失败（保状态码那条路悄悄永不生效），太大是**可见且有界**的失败（客户端超时）。所以默认值往大了偏。（注意「0.5 秒是占位值而非实测值」是决策文档的自述，不是代码事实。）

权重：判据与两条配套教训 **强到可直接采纳**；具体机制对我方 **不适用**。

## 3. 明确不适用

大方判掉，不为凑数硬推荐。

| 事项 | 理由 |
|---|---|
| `compat_profiles.py` 主体（1762 行客户端漂移审计 + 29 个 Claude Code 内置工具契约的 sha256 基线 × 2 个 CLI 版本） | 解决的是运维可观测性而非转换正确性，绝大多数告警 `action == "warn"` 不改变任何行为；`KNOWN_CLAUDE_CLI_VERSIONS` 只认 `2.1.197` / `2.1.207`，客户端每次升级都要人肉重采——一条维护跑步机。按 `build-proof-infrastructure-only-if-requested` 属于额外的证明基础设施。**但其中的 `audit_responses_event` 是 §2.1 那张表第 3 行的实际执行者**，若采纳该判据需要一个等价的（远小得多的）审计层 |
| 全叶子记账 `ConversionReport` 的**完整版** | 两名调研员独立实测：1600 条消息的请求稳定产出约 **594 KiB** 审计报告，**体积只跟叶子数走、与字节数无关**（1349 KiB 与 5099 KiB 两种请求体产出同样的 594 KiB）；而缓存的体积截断名单里**没有** `conversion_report`——超限请求的 body 被换成占位符之后，那份报告仍完整驻留内存。信息量最低的 `exact` 记录正是体积来源。核心收益（未登记叶子自动变成告警）我方已有 `LossCode` 清单可承担，缺的只是出口（§2.2） |
| JSONL sidecar 统计索引（`request_file_stats.py`，50913 字节） | 「增量」只减少 JSON 重解析，**追加时仍要哈希整个旧文件并把旧 sidecar 整份复制**，不是低 I/O 增量；「损坏自动重建」只覆盖 metadata 解析失败 / sidecar 缺失 / 长度不符，等长内容损坏是盲区。我方 SQLite 是更合适的统一事实源 |
| `RequestCache` 的 1000 条 FIFO 原始请求响应缓冲 | 名字误导（不是响应复用缓存，是观测历史）；单一全局锁包住写入 / 聚合 / 全文搜索的 `json.dumps`；对外读取直接返回内部可变对象。与我方「展示层读聚合记录」的边界相反 |
| 缓存里的上游原始事件被脱敏成哈希 | `redact_responses_event_for_cache` 的判据是 `if audit.warnings:`，**不区分 action**，`warn` 级同样触发，整条事件被替换成 `{_redacted, _reason, _size, _sha256}`——**你最需要原始报文的那一刻，正是它被替换成哈希的那一刻**。且代码里那句「raw bytes are still retained by the base cache handler」是错的（子类覆写了 `raw_events_for_cache`）。与我方 `no-imagined-security-theater` / `richest-context-flow` 直接冲突 |
| 可配置上游 profile（`/proxy/<name>/v1/...`）与 affinity routing | 解决多个异构 OpenAI-compatible 上游 + 粘性路由 header 的场景；我方单一上游没有选择点，引入只会把单一路径变成配置矩阵 |
| 用户 token registry（`gha_` 自助注册 + 管理员审批） | 它的威胁模型是「把部署者的 Copilot 额度分给经许可的用户」，并把管理面认证交给反向代理（README 自述属实，代码核上了）。token 明文存 JSON、`dict.get` 非常数时间比较。我方无此角色模型 |
| OneDrive 配置同步、Microsoft Web IQ 透传、ACP 子进程集成、内容过滤（改写 system prompt / 裁 tool result 后缀） | 与我方产品边界无关。内容过滤尤其危险：作用域只按「哪个端点」限定，不按模型 / 用户 / 来源限定，且其运行时配置可由 Flask 层不认证的 dashboard 改变 |
| Waitress `.run()` 运行方式、无在途流排空、无 socket activation | 我方 systemd / socket activation / 优雅停机目标在这份代码里**找不到可借鉴的实现**，需另找样本。它的优雅停机只覆盖 token usage reporter 落盘 |
| 手写 fake backend 作为正确性 oracle | 它的 E2E harness 工程卫生不错（真实 CLI 进程、direct baseline、预热、多并发、多 trial、交替实现顺序、记录对方 commit），但 load generator **只在 HTTP status ≥400 时失败**，不比较内容、事件序列、tool arguments、usage；fake 也不校验代理发上来的 body。转换器漏内容、错拼 tool arguments、错标 usage，bench 照样绿。项目**并未主张**它能证明正确性（README 标题就是 performance benchmark，功能验证归 pytest）——**缺的是一句显式的「本 harness 不校验内容，转换缺陷不会让它变红」**。这条对我方的意义是：性能 harness 与 cassette 行为验证要分工写明，别让读者自己推断 |

## 4. 反面样本：它踩了、我方要防的

1. **保活守卫读上游侧**（§1）。我方已避开。但它的近亲我方**确实有**：ghc-api 的连接重试退避直接 `time.sleep(min(2**n, 8))` 共 10 处，其中一处落在已经 commit 了 SSE 的生成器内部——睡最多 8 秒且不吐 keepalive。
   **我方对应情况**：`DirectDriver` 的 funded retry 本身没有指数退避，但 429/502 会让 `RateLimiter.observe_failure` 设定下次允许时间，下一轮在 `rate_limiting.py:130-138` sleep；token exchange 自身在 `ghc_client/tokens.py:123-158` 也有 1/2 秒退避。这些 sleep 都发生在 response 交给 `pipeline_app` **之前**——此时 client-facing `stream_delivery` 尚未创建，因而不会发 SSE ping。**是一个真实的 pre-response 客户端静默窗口**，与 `synthesized_response_headers_after_sec` 的 240 秒共同决定客户端体验。
2. **新机制只接到了部分入口**。ghc-api 的 `cancel()` 所有权修复落到三条流式路径中的两条，`_stream_pending_direct_anthropic_request` 没有。
   **我方是同一形态、且更严重**：本次盘点自查出**多处「有配置面无生产消费者」**——`hedge`（零读取）、`model_refresh_interval`（只启动时刷一次）、`CopilotTokenManager.run_refresh_loop`（无后台刷新，惰性刷新仍在）、`config.hooks` 六个订阅点（零反射零 loader）、`history.enabled` / `--history`（解析层有、运行行为无）、`/metrics` 业务指标（endpoint 在、`RequestTelemetry` 只在 dormant 侧装配）、`ActivatedSocketSet.from_systemd_environment`（类本身活链路在用，无调用方的是这个 classmethod）。`continuation` 稍有不同——`RetryLedger.limit_for` 确实读配置，但唯一产生 continuation 判决的 `decide_stream_ending` 全 `src/` 无调用方，活流终止直接发 error 帧，所以**配置分支存在但永远不被请求**。
   对照配置表时这些**很容易被当成「已具备」**。
3. **记账早于判断成败**（§2.2 末）。
4. **审计报告的 `target_path` 会失真而它看起来像权威记录**。`_convert_system` 按当时下标记账，随后工具转换 `input_items.insert(0, ...)` 把所有下标顶一位。紧跟其后的注释原文「Existing target paths in records are descriptive only」——但「descriptive only」不是读者能从字段名里读出来的限定。**审计线索失真比没有审计线索更危险。**
5. **决策文档的开放项清单本身会过期，而它看起来像当前状态**。这是本次核查现场抓到的一个样本：ghc-api 的决策文档记着「三条流式路径三种 pre-header 语义，Converge them or document why they differ」，但此后 `f3e8bae`（2026-08-15）已把翻译路径收敛到 grace，HEAD 上只剩两种。文档没跟着更新，于是任何照读文档的人（包括第一轮调研）都会把一个已修一半的问题当成完全未修。与第 4 条同族。
6. **对任意非 2xx 静默重放 4 次**（direct Anthropic 路径：非 OK 分支只有两种情况 `continue`，其余既不 `break` 也不 `return`，直接落到下一轮；且四次共用同一个 headers dict、同一个 `X-Request-Id`、同一个 token 快照）。项目自己记为「一行就能修」，HEAD 上确实仍未修——**这一条代码与文档一致**。
7. **限流槽位在生成器 `finally` 里释放**——`try_acquire` 在**创建生成器之前**执行，若 WSGI 层拿到 `Response` 却从未开始迭代，`generate()` 的函数体从未进入、`finally` 不运行，可用槽位少一个；累积到上限后所有 MCP 请求恒 503。（Python 语义两名核查员各自用探针验证；可达性未证。）若我方用同类模式，acquire 也要放进生成器体内。

## 5. 它的 `docs/decisions/` 写法，独立印证了我方的方法论

两份决策文档（`RESPONSES_PRE_HEADER_KEEPALIVE.md`、`ANTHROPIC_RESPONSES_WEB_SEARCH_COMPATIBILITY_DECISION.md`）的结构：决策 + **明确记录刻意没做什么** + 开放项 + 过程教训。其中三条与我方既有记忆完全同源，属于外部独立到达（原文逐字核对过）：

- 「**当一次测量说『没有差异』时，先验证测量装置能不能观测到那个差异，再相信它。**」——它的所有权泄漏问题第一次被测成「无差异」并据此驳回，原因是 fake 上游在 SSE body 之后仍持有连接、保活间隔留在 30 秒默认值，于是客户端离开期间根本没有写失败发生。对应我方 `prove-the-probe-ran-before-reading-its-number`。
- 「**对每一条新回归测试做变异测试**：把修复撤掉再跑，还能过的测试什么都没守住。」对应我方 `trusting-a-green-result`。
- 「**先测量再建缓解措施**」：并发上限被规格化之后**故意推迟**，代价是四个计数器（约 0.3 微秒/请求），并**预先写死了触发建设的阈值**（峰值 inflight < 16 什么都不做；> 64 或 cancelled > 10/min 才建）。原文「The deferral is only defensible because the observation landed with it」。对应我方「拒绝为任务额外搭建证明基础设施」，且给出了一个更好的执行形态。

另有一条它自己总结的：「**防御性散文应当变成可执行代码**」——评审笔记原本带着一张「`Queue.get(timeout=)` 对 -1 / 0 / nan / inf 分别做什么」的表，最后交付的是一行钳制，比它替换掉的那张表更短。

**但同一批文档也贡献了 §4.5 那条反面教训**：它们的「开放项」小节没有跟着代码更新。可采纳的形态是「记开放项，并在关掉时回来划掉」，而不是只记不销。

## 6. 建议的动作清单

按建议顺序，均需用户裁断是否执行。标注了核查后的成本变化。

| # | 动作 | 依据 | 规模 |
|---|---|---|---|
| 1 | 给翻译损失接一个出口（loss code 集合进 `RequestLine` / JSONL） | §2.2 | 小，机制已存在 |
| 2 | 未知 output item type 与未知**事件**类型都不能继续静默 fail-open——我方没有终局 output 对账，跳过即永久丢失。最小动作是两档都记 loss（配合 #1 才有出口）；是否升级 502 需裁断 | §2.1 | 小；**前提已被核查修正，不能照抄 ghc-api 的「未知事件跳过」** |
| 3 | 工具空 description 替身 + 剥离 `x-anthropic-billing-header:` 注入文本（均已确认我方未做）；孤儿 tool 配对方向需裁一次（我方双向删，ghc-api 只删 `tool_result`） | §2.4 | 小 |
| 4 | 上游 function call arguments 走严格解析（至少拒重复键与非对象），流式与非流式两处对齐 | §2.5 | 小，缺口已用探针确认 |
| 5 | reasoning 载体解码的九态别塌缩成二分：畸形与未知版本要有信号 | §2.6 | 小，且 legacy 已有更细实现可参照 |
| 6 | `thinking` → reasoning effort 接线 | §2.3 | **中降为小**：legacy 已有完整实现与测试，是接线不是从零做 |
| 7 | 登记并测量：stream 错误归一化路径上的 `response.text` 访问在锁定 SDK 版本下会不会吸流；pre-response 退避静默窗口（rate-limit pacing + token exchange）与 240 秒合成响应头的关系 | §2.8.3、§4.1 | 小，以测量为主 |
| 8 | `image` block 形状转换（当前原样透传后成为 top-level item，shape 错位）；`document` 的处置（当前有 `BLOCK_NOT_CARRIED` 记账地丢弃，但记账无出口——与 #1 同一条链） | inventory §2.1 | 中 |
| 9 | 中期：方言能力矩阵抽象（若上游出现第二个方言）。采纳时把「能否跨事件比较」与「能否发回上游」拆成两个位；effort 名查表要补齐全部档位 | §2.7、§2.3 | 大，暂不动 |

**已核查为「不是缺口」、从清单中移除的**：重试复用 headers dict（我方每轮重建）、无读超时长连（SDK read=600 + attempt deadline 1200）。

## 7. 核查修订记录

初版由五份精读报告收敛而成，随后派两名异源核查员分别对着**我方源码**与 **ghc-api 源码**证伪（不允许以那五份报告为权威）。据其结论修订如下。

我方侧（`260821-verify-our-side-claims.md`，判定 needs-fix）：

| 初版说法 | 修正 |
|---|---|
| 未知事件可维持跳过，因为终局会补回 | **推翻**。`_read_terminal` 从不读 `response.output`，`stream_delivery` 没有第二次对账。跳过即永久丢失 |
| 全仓没有 `reasoning_effort` 映射 | **收窄**。活链路没有；legacy `protocols/anthropic_responses.py:60-100, 251-351` 已有完整实现与测试 |
| 需自查重试是否复用 headers | **已确认不是缺口**，我方每轮重建 headers、重取 token、新 request id |
| 需自查是否有「无读超时长连」 | **不成立**。SDK read=600、attempt deadline=1200 |
| 录制 provider「只有 transport 是假的」 | **补充**：还有 `RecordedTokenSource` |
| legacy「只被测试引用」 | **改为** dormant 生产模块图，可被显式 import |
| 空 description / 计费头「需核对」 | **确认我方均未做** |
| function arguments 解析「未知」 | **确认缺口**，探针验证重复键静默取后者 |

ghc-api 侧（`260821-verify-ghc-api-claims.md`，49 条中 39 忠实）：

| 初版说法 | 修正 |
|---|---|
| 分档「每一档都先检查方言是否支持该 effort 名」 | **失真**。五档只有 `max` / `xhigh` 检查，其余三档硬编码。抄的时候要补齐——这条正是被推荐的写法 |
| 「三条流式路径三种 pre-header 语义…未修」 | **失真**。HEAD 上是两种，翻译路径已被 `f3e8bae` 收敛；过期的是决策文档的开放项。此事本身升格为 §4.5 一条独立教训 |
| 「12 个能力位」 | **13 个** |
| `stable_ids` 门控「全部 id 比较」 | **收窄**。`call_id` 与工具名变异始终强校验 |
| 未知 content part → 502 | **补执行者**。是审计层 `fail_always=True` 做的，转换器本身静默放行；照抄判据不建审计层不会自动成立 |
| 594 KiB「约 44%」 | **比例是形状的性质不是机制的性质**。体积与叶子数成正比、与字节数无关 |
| E2E「它自己没划清这条线」 | **改为「没写下」**。项目从未主张能证明正确性，功能验证归 pytest |
| 告警去重键「(code, path, 指纹)」 | 实为五元组 `(code, path, profile, cli_version, fingerprint)` |
| 空 description「对 `""` 替换」 | 空串、纯空白、任何非字符串值都替换 |
| 「无条件先 mark」 | 改为「不管 `thinking.type` 是什么都先 mark」（前面另有两道提前返回的闸） |

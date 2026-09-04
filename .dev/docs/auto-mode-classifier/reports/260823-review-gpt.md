# Auto mode classifier 独立对抗性评审

- 评审日期：2026-08-23
- 评审对象：`/home/xp/src/ghc-api-proxy-py` 当前未提交工作树
- 评审结论：`needs-fix`
- 发现计数：blocker 6，major 2，minor 0，nit 0
- 证据权重：下列 blocker 与 major 均有当前源码控制流、可执行反例或 Claude Code 2.1.241 原始 JS 支撑，强到可以据此阻止合入；其中阈值 `100` 是否已由线上服务端配置下发没有流量证据，但“客户端明确接受该值且会把本地 block 读成 allow”本身已由源码直接成立。

## 结论摘要

当前实现不能合入。最直接的四条产品失败是：severity 的无 `stop_sequences` 请求被误判成 block 协议；合法阈值 `100` 会把配置的 `block` 静默解释成 allow；两个单独成立的 body 谓词会劫持普通 Anthropic 请求；同一分类器还会在合法 OpenAI Chat Completions 请求上触发并返回 Anthropic 响应。另有两条解析可靠性 blocker：测试中的 Python parser 并非 JS parser 的忠实转写；`reason` 的大小写敏感过滤挡不住客户端大小写不敏感的第二个相反决定。短路还跳过了 request-level success subscriber，并把本地生成的回复伪记成一次 HTTP/1.1 上游响应。

`uv run pytest tests/unit/pipeline/test_auto_mode_classifier.py --no-cov -q` 在本工作树上得到 `23 passed in 2.30s`。这个绿灯不反驳下列发现：现有负例没有制造判据碰撞，协议测试没有覆盖 severity 的无 stop-sequence 形状，parser oracle 与 JS 在 Unicode 语义上同源错误，且集成测试只走 Anthropic Messages 入口。

## Blocker

### B-01：severity 的无 `stop_sequences` 请求被确定性误判成 block 协议

- 严重度：blocker
- 置信度：高；当前 Claude Code 2.1.241 控制流与实现可逐行对上，无需推测线上数据。
- 位置：`src/app/pipeline/auto_mode_classifier.py:89-97`、`tests/unit/pipeline/test_auto_mode_classifier.py:187-190`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368332-368336`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368454-368460`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368474`

`_protocol_of()` 只在 `stop_sequences` 含 `</severity>` 时返回 `severity`，其余一律返回 `block`。但真实客户端不是用 `stop_sequences` 唯一标识 severity：`OGw()` 会把 system 的 Output Format 改成 `$Gw` 的 severity 版本；只要变量 `u` 存在，`G` 就固定为 `QRl`，即客户端对回复使用 severity parser。阶段 2 的请求对象 `j` 根本没有 `stop_sequences`，仍把 `G` 传给 `p1m`；`fast` 模式也可形成无 stop-sequence 的请求。实现因此会给这类请求返回 `<block>…</block>`，`QRl → UGw` 找不到 `<severity>`，`p1m` 把它当 `unparseable` 并重试。

测试 `test_stage_two_carries_no_stop_sequences_and_still_uses_block` 只构造了旧流量中观察到的 block 阶段 2，并把“无 stop sequence”错误提升为“必是 block”。规格 `.dev/docs/auto-mode-classifier/spec.md:43` 已写明还要由 system 的 severity Output Format 判别，代码没有实现这一半。至少需要加入由 `OGw/$Gw` 形状导出的 severity 阶段 2 请求，并让协议判别读取该结构；否则两阶段 severity 的阻断路径必然反复解析失败。

### A-02：声称为逐字转写的 Python parser 与 JS parser 有可执行语义分歧

- 严重度：blocker
- 置信度：高；已把同一字符串分别交给 Node.js 中逐字复制的 `oLl/UGw` 与测试文件中的 Python 函数，结果相反。
- 位置：`tests/unit/pipeline/test_auto_mode_classifier.py:98-122`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368404-368427`

两步 thinking 剥离的先后顺序、全局非贪婪闭合块后再剥未闭合尾部、`matchAll` 对应非重叠全局 `finditer`、可选闭合标签，这些部分逐项核对后没有发现分歧。分歧在 regex 字符语义：JavaScript 这里的非 `u` 正则以 ASCII word/digit 规则处理 `\b` 与 `\d`，而 Python `re` 默认使用 Unicode；Python `re.IGNORECASE` 还会把 long s `ſ` 与 ASCII `s` 做额外折叠。实测反例为：`<block>yesé` 在 JS `oLl` 返回 `true`、Python `parses_as_block` 返回 `None`；`<block>yeſ</block>` 在 JS 返回 `null`、Python 返回 `False`；`<severity>١</severity>` 在 JS `UGw` 返回 `null`、Python `parses_as_severity` 返回 `1.0`。`\s` 也不等价：`<severity>` 后放 U+001C 时，JS 返回 `null`，Python 返回 `0.0`。

当前生成器只写 ASCII 数字和 `yes/no`，所以这些反例不表示默认生成文本已失败；它们表示测试宣称的外部 oracle 不存在，测试可接受真实客户端拒绝的回复，也可拒绝真实客户端接受的回复。按本次评审的明确判据，任何不忠实转写都是 blocker。修正时不能简单给 severity 全部加 `re.ASCII`，因为 ECMAScript `\s` 又包含一部分非 ASCII 空白；需要显式复现 ECMAScript 的字符集合，block 路径则需同时收紧 ASCII word boundary 与 case-insensitive 行为。

### A-03：`reason` 的过滤大小写敏感，合法配置可稳定制造不可解析回复

- 严重度：blocker
- 置信度：高；已直接调用当前 `verdict_text()` 复现，并与 `oLl` 的 `/gi` 标志核对。
- 位置：`src/app/pipeline/auto_mode_classifier.py:136-141`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368407-368413`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368542-368566`

代码只用大小写敏感的 `"<block>" not in reason` 决定是否保留理由，客户端却用 `/<block>(yes|no)\b/gi` 扫描所有决定。反例是 `decision: block` 与 `reason: "Proxy overrode <BLOCK>no</BLOCK>."`：当前输出为 `<block>yes</block>\n<reason>Proxy overrode <BLOCK>no</BLOCK>.</reason>`，客户端看到 yes 与 no 两种决定后返回 `null`，`p1m` 随即重试。混合大小写 `<BlOcK>no</bLoCk>` 同样穿过过滤并失败。`reason` 是不受 schema 限制的公开配置字段，因此这不是仅靠恶意内存构造才能到达的状态。过滤规则至少要与客户端的大小写语义一致，或者把理由作为文本转义后再嵌入。

### A-04：severity 的 `100` 不能保证 block；客户端允许阈值恰为 `100`

- 严重度：blocker
- 置信度：高；阈值接受范围与严格大于比较都在当前客户端源码中。线上当前是否下发 `100` 未观测，但它是客户端显式接受的合法配置，不是越界输入。
- 位置：`src/app/pipeline/auto_mode_classifier.py:25-28`、`src/app/pipeline/auto_mode_classifier.py:132-135`、`.dev/docs/auto-mode-classifier/spec.md:87-91`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368350-368376`、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js:368463-368474`

客户端的 `nLl()` 接受 `0 <= threshold <= 100`，随后阶段 1 与阶段 2都用严格比较 `score > threshold`。当服务端下发 `t1 = 100` 或 `t2 = 100` 时，本地 `decision: block` 生成的 `<severity>100</severity>` 得到 `100 > 100 === false`，被客户端静默解释为 allow；阶段 1 还会立即走 allow 返回，不会有第二次机会纠正。规格把 `100` 称作在任何合理阈值下都位于 block 一侧，但客户端自身把 `100` 认作合法阈值，已经给出反例。`UGw` 不校验 `0-100` 范围，因此 `101` 能越过客户端允许的全部阈值；无论采用它还是放弃本地 severity block，都必须先在规格中明确裁决，不能保留当前“保证 block”的错误主张。

### B-05：两个单独成立的弱谓词都能劫持普通 Anthropic Messages 请求

- 严重度：blocker
- 置信度：高；已直接把两份合法普通 body 交给当前 `classify()`，均返回本地 allow verdict。
- 位置：`src/app/pipeline/auto_mode_classifier.py:47-59`、`src/app/pipeline/auto_mode_classifier.py:63-86`、`src/app/pipeline/auto_mode_classifier.py:100-118`、`tests/unit/pipeline/test_auto_mode_classifier.py:78-93`、`tests/unit/pipeline/test_auto_mode_classifier.py:156-158`、`.dev/docs/auto-mode-classifier/spec.md:22-27`

P1 的实现比规格还宽：规格写 `system[0].text`，实现扫描任意 system block。一个普通请求可以把首块设为 `You are a normal assistant.`，第二块设为 `You are a security monitor for autonomous AI coding agents. Explain the quoted role below.`，最后消息只是 `hello`；当前实现命中 `system-prompt`。即使收回到 `system[0]`，任意 Anthropic API 客户端也可以合法使用恰好以该句开头的自定义 system prompt，单一字面量仍不能证明请求来源。

P2 的反例更直接：普通请求的最后一条 user message 合法地由多个 text block 组成，第一个 block 恰为 `<transcript>\n`，后续 block 要求总结所附转录；当前实现命中 `transcript-open`，把真实请求偷换成 `<block>no</block>`。现有负例故意让普通请求在 system、stream、tools、角色历史、首块文本等每一项都不同，只证明一个完全不相似的 body 不命中，没有约束单字段碰撞。

按用户点名的嵌套场景继续核对：只把监控句粘贴进普通 `messages` 文本而不让它成为 system block，不会触发 P1；标准 Anthropic `tool_result` 中嵌套的 `content: [{"type":"text","text":"<transcript>\n"}]` 也不会触发 P2，因为代码不递归且顶层第一块类型是 `tool_result`。这两种精确形状查了，没找到反例。误伤发生在同样合法且更直接的 system 多块与 user 多 text-block 形状。

2300 条正样本与历史库里的零碰撞只支持这些字段对已观察 Claude Code 流量的识别能力，不能支持任一字段单独成为替换响应的充分条件。至少应把 Anthropic endpoint、非流式、无 tools、已知 `max_tokens`、system marker、完整 transcript 包裹及消息角色结构作为联合判别候选，并用规格重新裁定需要满足哪些项；这是收紧误伤面，不是要求穷举状态空间。

### B-06：分类器没有 Anthropic 入口边界，会在合法 OpenAI Chat Completions 请求上返回 Anthropic Message

- 严重度：blocker
- 置信度：高；已通过当前 `handle()`、`build_chain()` 与一个声明 `OPENAI_CHAT_COMPLETIONS` 能力的 provider 直接复现。
- 位置：`src/app/pipeline/driver.py:115-126`、`src/app/pipeline/delivery/formats/anthropic_messages_synthetic_reply.py:166-184`、`src/app/pipeline/reply.py:18-27`、`src/app/server/routes/table.py:27-39`

`handle()` 对所有已实现入口无条件调用 `classify()`，没有检查 `context.inbound_format is WireFormat.ANTHROPIC_MESSAGES`。合法 Chat Completions body 的 user content parts 也可以是 `[{"type":"text","text":"<transcript>\n"}, …]`；直接探针得到 `synthesized=True`、`content-type=application/json`，body 却是 `{"type":"message","role":"assistant","content":[…],"stop_reason":"end_turn",…}`。`response_payload()` 因 `handled.synthesized` 原样返回它，于是 `/chat/completions` 客户端收到错误协议，并且真实请求从未到达上游。即使 B-05 的谓词被收紧，这一入口边界仍必须独立存在；规格定义的目标明确只是非流式 `/v1/messages`。

## Major

### C-01：本地成功请求不发布 `request.succeeded`，破坏 request-level subscriber 语义

- 严重度：major
- 置信度：高；静态控制流明确，且带自定义 success subscriber 的 `handle()` 探针得到空事件列表。
- 位置：`src/app/pipeline/driver.py:115-126`、`src/app/pipeline/direct_driver/base.py:135-192`、`src/app/pipeline/direct_driver/base.py:29-41`、`src/app/server/composition.py:447-507`、`docs/.human-controlled/request-pipeline.md:14-18`

短路在 driver 构造前直接返回，因此五个 driver 事件全部不发布。没有上游 attempt，所以跳过 `attempt.prepare`、`attempt.succeeded` 与对应失败事件是合理的；但客户端请求已成功得到 200，本应属于 `request.succeeded`。当前 `build_chain(..., subscribers=...)` 明确允许调用方注册订阅者，我用该入口注册 `request.succeeded` 后发一条本地命中的请求，回复成功而 subscriber 观察到 `[]`。这会让任何 request-level 记账、审计或后续 History subscriber 漏掉恰恰由代理自行决定的请求。当前生产注册表只含三个 `attempt.prepare` built-in，所以尚未发现现有生产模块丢状态；缺陷是已经暴露的扩展契约在本地成功路径上失真。

### C-02：短路后的通用响应记账把本地字节与默认 HTTP/1.1 伪装成上游交换

- 严重度：major
- 置信度：高；当前代码与 `httpx2.Response` 实例探针一致。
- 位置：`src/app/pipeline/driver.py:196-221`、`src/app/server/routes/inference.py:267-283`、`src/app/server/routes/inference.py:480-511`、`src/app/server/routes/inference.py:608-631`、`src/app/observability/request_trace.py:199-246`

`_answered_auto_mode()` 创建一个没有网络传输的 `httpx2.Response`，但 `_dispatch()` 随后无条件执行真实上游响应的记账：把空 synthetic request 记作发送 `0` 字节，把 `response.http_version` 记作上游协议，把 synthetic body 长度记作上游返回字节。探针显示这种 response 的 `http_version == "HTTP/1.1"`、`extensions == {}`、连接快照为 `no-transport-identity`。因此完成行会表示代理从 HTTP/1.1 上游收到了本地生成的回复；streaming 分支还会经 `_counted_upstream()` 增加 upstream chunks、first-byte 与 received bytes。项目这组字段的既有契约明确描述 proxy↔upstream 交换，不能把客户端收到的 synthetic bytes 填进去。命中专用 INFO 中的“原请求多少字节未发上游”是正确且保留价值的，但不能修正另一条完成记录中的伪造上游事实；synthetic 路径需要让这些字段保持缺席或明确标记为 local。

## C 方向的完整路径盘点

| 阶段 | 是否经过 | 判断 |
|---|---|---|
| ASGI `InFlightLimit` proactive admission | 是；`src/app/server/pipeline_app.py:30-39` 与 `src/app/server/admission.py:40-48` 包在路由外层 | 不存在短路绕过；无需修改。排队时间是否计入 client deadline 是既有全路径问题，不是本特性新引入。 |
| active request 注册、footer 状态、最终 completion log | 是；`src/app/server/routes/inference.py:67-105` | 没有被跳过；但 completion log 的 upstream 字段被 C-02 污染。 |
| body 读取、JSON 解析、入口路由、`build_context`、credential/header floor | 是；`src/app/server/routes/inference.py:129-170` 与 `src/app/server/inbound.py:24-70` | 不存在短路绕过。 |
| client request deadline | 是；deadline instant 在 `src/app/server/routes/inference.py:129-136` 建立，并由 `handle_bounded` 在 `src/app/server/routes/inference.py:245`、`src/app/pipeline/driver.py:341-367` 包住 `handle()` | 不存在短路绕过。 |
| attribution strip、模型 route、`on_routed`、path header policy、denied beta strip 及其 metric、Anthropic request fixup | 是；`src/app/server/routes/inference.py:174-183`、`src/app/pipeline/driver.py:73-113` | 均发生在分类前；没有反例。 |
| 请求翻译与把 payload model 改成 resolved model | 否；`src/app/pipeline/driver.py:128-140` | 本地直接生成 Anthropic 回复时跳过合理；判别依赖原 Anthropic body。前提是先修 B-06 的入口边界。 |
| `context.begin_attempt`、upstream attempt deadline、response-header timeout、RetryLedger、draining retry gate、provider send | 否；`src/app/pipeline/direct_driver/base.py:135-192` 与 `src/app/pipeline/direct_driver/base.py:235-274` | 没有上游 attempt，跳过正确。当前 `attempts=0` 是诚实结果。 |
| reactive rate limiter acquire/observe | 否；`src/app/pipeline/direct_driver/base.py:148-179` | 它只调节和学习上游 429/502，本地回复不应参与，跳过正确。 |
| `attempt.prepare` built-in subscribers | 否；注册表见 `src/app/pipeline/subscribers/__init__.py:33-66` | 当前三个 built-in 只修整将发往上游的 body，本地回复没有该 leg，跳过未找到现实反例。 |
| `request.succeeded` subscribers | 否 | 不应跳过，见 C-01。 |
| History | 当前生产管线中不存在可调用的 History writer/subscriber；全仓 `src/app` 只见 `HistoryConfig` 与说明“pipeline records no history”的 rejection-capture 文档 | 查了，没有一个实际 History 步骤可被本短路额外绕过；不能把尚未实现的配置面算作本特性的回归。若未来用 `request.succeeded` 落 History，C-01 会使其漏记。 |
| metrics | attribution 与 denied-beta counters 在短路前仍会更新；translation-loss counter 没有 translation 可记；项目没有通用 request/upstream-attempt counter | 查了，没有发现现存 counter 被静默跳过。专用命中只有 INFO 日志而非 Prometheus counter，与当前规格“打一条 INFO”一致。 |
| buffered/streaming delivery、response summary、client response、active removal | 是；`src/app/server/routes/inference.py:267-511` | 客户端仍能收到回复，`reply_summary` 也会读取 synthetic Anthropic body；错误仅是 C-02 所述把本地载荷投影成上游事实。 |

## A 方向其余核对结果

除 A-02、A-03、A-04 与 B-01 外，查了，没找到反例。具体范围如下：`dLl` 的两次 replace 在 Python 中按同一顺序执行；闭合 thinking 使用全局非贪婪删除，未闭合 thinking 从标签删到末尾；block parser 在 thinking 剥离前先扫描互相冲突的 yes/no，剥离后再做最终扫描；`matchAll` 与 `finditer` 对这些非空模式都枚举非重叠全局匹配；闭合标签的可选性一致。真实非流式调用链从 `Age()` 的 `client.beta.messages.create` 到 `p1m`、`Wd`、`oLl/QRl`、`iLl` 已顺读：合成 body 提供 SDK 后续直接读取的 `id`、`content`、`usage.input_tokens`、`usage.output_tokens` 与 `stop_reason`；`Wd` 能取到唯一 text block；默认 ASCII `<block>no</block>`、`<block>yes</block>` 与带安全 reason 的 block 回复均可解析；severity 回复使用 `end_turn`，满足 `QRl` 的 `stop_sequence/end_turn` 限制；非空 text 且 stop reason 非 `refusal`，不会被 `iLl` 判成 `policy_refusal`；缺少 `_request_id` 与 cache token 字段的调用点都以 optional/nullish 方式读取。当前 Claude Code 源码中的分类器调用是非流式，未发现真实调用链还要求 synthetic SSE。

## 建议的修复顺序

1. 先修 B-06 的 endpoint guard 与 B-05 的联合判别，因为它们决定普通请求会不会被偷换。
2. 再修 B-01 的 severity 协议识别与 A-04 的 block 分值，因为它们决定被正确识别的请求是否得到正确决定。
3. 把 A-02 的测试 oracle 改成 ECMAScript 语义，并用它覆盖 A-03 的大小写 reason 与 B-01 的无 stop-sequence severity；不要再用当前 Python 默认 Unicode regex 作为客户端等价物。
4. 最后把 request-level success 发布和 synthetic observability 分支补齐。无需让 synthetic 请求经过任何 upstream attempt、reactive rate limiter 或 attempt-level subscriber。

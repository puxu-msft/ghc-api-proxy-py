# 错误信封行为 Spec v2 评审

评审日期：2026-08-23。

评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md`，SHA-256 为 `adfdc2313ba2ef53c500a366aea01719e320cd8dbaeab4c5e7ac1e2894aadfc0`，文件时间为 `2026-08-23 13:33:27 +0000`。评审期间该草稿从 v1 并发改成了 v2；本报告只对这个哈希的 v2 生效，不评价先前字节。

代码基线：主仓库 `HEAD=0ebdfd0749cea16139c0ddd9a9151d4c2a116422` 加当前工作树。用户亲笔的 `message-translation.md` 是当前未提交工作树版本，SHA-256 为 `359e60c5ded0cc31bde61e4936e9b9356442ce952620bcab13cd5d57a09da71c`；本报告按用户给定规则把它当作最高权威，不因尚未提交而降级。

技能说明：用户要求先调用 `my-skills:as-reviewer`，但该名称不在本会话的可用技能清单中；已按指示回退并实际调用 `verifying-authoritative-claims`。任务涉及 Anthropic SDK 合同，因此另调用了 `claude-api:claude-api` 并只读取其错误合同材料。

v1 交接：我在 v2 到盘前已经核过 §1 的四处权威引用、§2 的两轴判据、JSON／SSE 当前形状、SDK 词汇与 one-shot 行为。v2 原样保留的 §1、§2、§6、§7 继续采用这些证据；v1 关于「新建 `SemanticError`」与「现有载体里已有原始响应 bytes」的结论均不沿用。收到协调方更正后，我又读取了 v2 引用的 `.dev/docs/server-layout/reports/260823-error-surface-inventory.md`；该报告锚在 `9c4ba6c`，当前 `HEAD` 是其后代，相关路径此后只有 `errors.py` 与 `stream.py` 的注释变化，且本报告用当前工作树独立重跑了承重 HTTP 场景。

## 结论

**结论：needs-fix，当前不应冻结。共 4 条 blocker、8 条 major、1 条 minor。** 权威引文主体准确，v2 也纠正了 v1 对原始字节、`TranslatorRegistry` 和 one-shot 空 body 的三处错误；但 v2 新增了一处直接违背用户原文的规则，并且把只有枚举的分类表当成了完整错误 IR。更关键的是，「流式与非流式同一个信封」无法套到 OpenAI Responses 的真实 SSE 错误事件上，也无法与明确排除的 Chat Completions one-shot 腿同时成立。

严重度口径：`blocker` 表示同一份 Spec 内存在互斥要求、违背当前用户裁决，或缺少会让实现者只能自行发明公共行为的核心合同；`major` 表示会 materially 改变客户端收到的状态、类别、重试动作或字段，但可在不推翻主方向的前提下补齐；`minor` 表示不改变主决策但会让证据或文字被误读。

## 一、权威引文逐条核对

| Spec 引用 | 权威原文核对 | 判定与证据强度 |
|---|---|---|
| `message-translation.md:9` | 当前工作树第 9 行逐字是「对于翻译路径，采用按需理解和处理的原则，不直接建立两种类型之间的映射，而是总是建立消息格式与内部 IR 的映射关系，按需理解和处理。」Spec 引文逐字准确。 | **已确认；把握高，足以据此行动。** 直接读取用户亲笔工作树文件并用一基行号复核。 |
| 同文件第 3、5 行 | 第 3 行是「采用‘输入格式 <-> 中间表示 <-> 上游模型格式’的方式」；第 5 行指定 `translation_driver`，并说明每种格式注册 `inbound.from-*` / `outbound.to-*` 翻译器、不要求能力等价、无唯一翻译路径时提供配置。Spec v2 只转述了机制名与三段关系，没有把「无唯一翻译路径时提供配置」偷换成已决定的唯一行为。 | **已确认；把握高。** 行号与转述均对得上；没有丢掉会改变 v2 主张真假的限定词。 |
| `message-format-reshape.md:11` | 第 11 行确实说直连请求头按黑名单、翻译请求头按白名单。 | **已确认；把握高。** 但该句只谈请求头，不能单独授权错误体或错误响应头；错误体的授权来自本轮用户原文，不应反向归给第 11 行。 |
| 「客户端返回 Anthropic Messages」一节 | 第 51～63 行确实列出直连响应头黑名单与翻译响应头白名单。 | **已确认；把握高。** 原文没有「只为成功响应」这个限定，见 F-05。 |
| 该节 TODO | 第 63 行原文带三层限定：「根据我的认知」；非 Anthropic 上游可能语义相同、形式不同；「在认清之前翻译路径的处置先不做」。Spec v2 在 §1 保留了当时「先不做」的处置，没有把这个旧 TODO 单独写成已获授权；当前翻译过 IR 的授权来自 2026-08-23 新裁决。 | **已确认；把握高。** §1 的转述没有发生本项目曾出现的「待裁决 → 已授权」错误；真正发生该错误的是 §7 最后一段，见 F-04。 |

## 二、现状事实逐条核对

### 2.1 实际 HTTP 请求探针

探针源与输出分别在 `/home/xp/.claude/jobs/08aff420/tmp/error_envelope_probe.py` 和 `/home/xp/.claude/jobs/08aff420/tmp/error_envelope_probe-v2.out`。它从项目根目录执行，生产入口是 `create_pipeline_app`，上游是 `httpx2.MockTransport`，客户端通过真实 ASGI app 发请求；命令为 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py/src:/home/xp/src/ghc-api-proxy-py/tests/int uv run python /home/xp/.claude/jobs/08aff420/tmp/error_envelope_probe.py`。这类判据换一个上游也成立，因此不需要打真实 Copilot。

| 命题 | 实测结果 | 判定与证据强度 |
|---|---|---|
| 今天直连与翻译走同一条通用 JSON 信封 | 同一个 `/v1/messages`，直连 `claude-model` 与翻译到 Responses 的 `gpt-model` 都让上游返回同一份 400。客户端两次都收到 267 字节、逐字相同的 `{"error":{"type":"UpstreamRejected",...}}`，没有收到上游原生信封。 | **已确认；把握高，足以据此行动。** 同端点、同上游响应，只改变路由是否翻译。 |
| 响应头提交前后的错误形状由时序决定 | `/v1/messages` 在 body 解析期失败时收到 `400 application/json` 与 `{"error":{"message":"body is not valid JSON"}}`；同端点先提交 200、交付一个完整块、再在第二块中断时收到 `200 text/event-stream`，末帧是 `event: error` 与 Anthropic 外形的 `{"type":"error","error":...}`。 | **已确认；把握高，足以据此行动。** 这是用户特别要求的实际请求验证，不是代码推断。 |
| 当前流式错误帧已经是合法 Anthropic 类型 | 上述真实请求末帧的 `error.type` 是 `upstream_error`。安装的 Anthropic SDK 1.0.0 顶层 Literal 不含它。 | **已推翻；把握高。** 只能说「外层信封采用 Anthropic 形状」，不能说类型词汇已经是 Anthropic 方言。Spec v2 已在 §4.2 正确写明这一点。 |
| 上游流内失败事件被吞成正常收尾 | Anthropic 直连流在一个完整块后发送原生 `event: error`，客户端收到 752 字节，结尾却是 `message_delta(stop_reason="incomplete") + message_stop`，原始 `overloaded_error` 与 `ANTHROPIC-FAILURE` 均消失。Responses 直连流发送 `response.failed`，客户端收到 2903 字节并以 `response.incomplete`、`error:null` 结束；翻译到 `/v1/messages` 时收到 749 字节并以 Anthropic 的 `message_stop` 结束。 | **已确认；把握高，足以据此行动。** 两条上游腿与两条客户端腿均经实际请求观测。Spec 的行为判断正确，但「零字节到达客户端」措辞不准确，见 F-12。 |
| 非 UTF-8 上游错误 body 的原始字节已经丢失 | 上游返回 `b"\xffraw-body"`，客户端信封中的 `upstream` 与 `message` 均变成 `�raw-body`。 | **已确认；把握高。** 直接证明 v2 §3.2 的前提，而不只依赖 `_response_parts` 读码。 |

### 2.2 代码与 SDK 静态核对

| 命题 | 核对结果 | 判定与证据强度 |
|---|---|---|
| `UpstreamRejected` / `UpstreamError` 已携带 `status_code`、`headers` 与上游 body | `src/app/pipeline/exceptions.py` 两个构造器都有这三个字段；`normalize_upstream_error()` 的状态异常分支都赋值。body 类型是已解码 `str`，来源是 `response.text`，不是原始响应字节。`UpstreamRejected.sent` 另存的是**请求**原始字节，不是响应。 | **已收窄；把握高。** 「携带 body 字符串」成立，「携带上游原始响应 body 字节」不成立。v2 已准确修正。 |
| `TranslatorRegistry` 今天有四条轴 | `TranslatorRegistry.__init__` 有 `_inbound`、`_outbound`、`_read_response`、`_write_response` 四张表，对应请求 reader/writer 与响应 reader/writer。 | **已确认；把握高。** v1 的「再加错误 reader/writer」提议已从 v2 删除；当前 v2 不再错误依赖这个断言。 |
| `framer is None` 守卫一触发就只能 200 + 空 body | `one_shot_delivery()` 在异常前已积累字节时先交付积累值再重抛；`tests/unit/pipeline/delivery/test_one_shot_delivery.py` 分别钉住「已有字节则交付」与「第一字节前失败才为空」。 | **已推翻；把握高。** v2 §6 已改成「已到达字节会交付，只是没有错误帧」，修正正确。 |
| Anthropic 顶层词汇表有所列 9 个成员 | 安装的 `anthropic==1.0.0` 中 `ErrorObject` 是以 `type` 为 discriminator 的九成员 union，Literal 依次为 `invalid_request_error`、`authentication_error`、`billing_error`、`permission_error`、`not_found_error`、`rate_limit_error`、`timeout_error`、`api_error`、`overloaded_error`。 | **已确认；把握高。** 数量、成员与 Spec 完全一致。 |
| OpenAI `ErrorObject.type` 是裸 `str` | 安装的 `openai==3.3.1` 中 `ErrorObject.__annotations__` 为 `code: str | None`、`message: str`、`param: str | None`、`type: str`。 | **已确认；把握高。** 没有 Literal 或 enum。 |
| 客户端 SDK 按 `error.type` 选择异常类 | OpenAI 与 Anthropic Python SDK 的 `_make_status_error()` 都按 HTTP status 选择 `AuthenticationError`、`PermissionDeniedError`、`NotFoundError`、`RateLimitError` 或 5xx 类；OpenAI 的 `type/code/param` 是错误对象附加字段，Anthropic 暴露 `.type`，但没有一等 `.code`。两者默认都重试 408、409、429 与全部 `>=500`，并识别 `x-should-retry`。 | **已推翻；把握高。** `error.type` 仍可供应用细分，但 SDK 自带异常分类与自动重试首先由 status 和 header 决定。§4.3 不能只定义字符串列。 |

## 三、发现

### F-01　[blocker] [把握：高] §5 要求直连流内失败先映射 `ErrorCategory`，直接违背用户「直连一定用原生，即使未知也能传递」的原文

位置：`spec.md:144`。

§5 写道「上游的失败事件必须映射到 `ErrorCategory`（直连也要）」并以「本代理已经在重新成帧」为理由排除原生透传。这不是当前裁决允许的例外。`event: error`、`response.failed` 与其中的未知字段同样是上游原生 wire 内容；把 `overloaded_error`、供应商新类型或未知附加字段压进本项目闭集，会恰好丢掉「即使我们未知，也能传递」要保住的信息。实现已经重成帧是现状约束，不能反过来改写用户的行为裁决。

实际探针证明这不是抽象争论：原生 Anthropic `overloaded_error` 与消息当前被整段吃掉；修法若改成 `UPSTREAM/api_error`，客户端仍拿不到上游原生类别。直连腿应当携带并按客户端同方言重放上游原生失败事件的完整 payload；若必须重编号或重包 SSE，只允许改变传输包装，不得把 payload 先归入本项目闭集。翻译腿才读入内部 IR。

可执行建议：把 §5 第一条拆成两条判据。直连上游失败事件保存原始 event 名、原始 JSON payload 与未知字段，并在客户端同方言下重放；翻译腿通过方言 reader 读入完整错误 IR，再由客户端 writer 输出。若作者认为块级交付让直连原生事件不可实现，应把这个真实冲突交回用户裁决，不能自行宣布「谈不上原生透传」。

### F-02　[blocker] [把握：高] `ErrorCategory` 只是分类枚举，不是能够完成错误翻译的 IR；source → IR 合同仍整块缺失

位置：`spec.md:68-75`、`spec.md:96-130`。

现有 `ErrorCategory` 只装一个六值分类；它没有 `message`、`status_code`、`headers`、`code`、`param`、上游原始 payload、未知扩展、来源方言或转换损失。§4.4 又要求这些字段参与写出，§7 还要处理读不动的原文。把 enum 称为「IR 已经存在」只证明了一个字段已经存在，不能推翻对错误记录载体的需要。

同时，Spec 只给了 `category → 目标方言字符串`，没有给出任何完整的 source → IR 表。实现者仍需自行决定：`UnknownModel`、`CapabilityMissing`、`RoutingError`、`TranslationRefused`、`CountTokensUnavailable`、`PipelineAbort(cause=...)`、HTTP 401/403/404/408/429/500/503/504、传输 timeout、流内 `response.failed` 各自进哪个 category，status 是否保留，message 从哪里抽，code 默认值是什么，param 如何提取，未知字段放哪里。这里每一项都会改变客户端行为。

可执行建议：保留 `ErrorCategory` 作为 IR 的一个字段，但定义一个完整记录，例如 `ErrorInfo`，至少包含 `category`、`message`、`status_code`、`code`、`param`、`headers`、`source_format`、`source_payload` / `source_bytes` 与转换损失；随后增加一张异常类／上游 status／流内事件到该记录的规范表。不要把载体是否复用现有 enum 与「是否需要完整 IR」混成同一个决定。

### F-03　[blocker] [把握：高] §6 的「同一个信封两种包装」既不符合 OpenAI Responses SSE 合同，也与明确排除的 one-shot 腿自相矛盾

位置：`spec.md:148-152`、`spec.md:124-125`。

OpenAI JSON `ErrorObject` 的确是嵌套 `{"error": {"message", "type", "param", "code"}}`；但 OpenAI Responses 的官方 `ResponseErrorEvent` 是扁平的 `{"type":"error","code", "message", "param", "sequence_number"}`。事件 `type` 固定 Literal `"error"`，没有嵌套 `error`，也没有独立 category 字段。因而「SSE 的 `event: error` 帧与 JSON body 是同一个信封的两种包装」对 OpenAI Responses 不成立。强行同形会产出官方 SDK 不认识的事件；当前 `ResponsesFramer.error()` 正是为此把 category 放进 message，而不是复用 JSON envelope。

同一节下一段又把 Chat Completions 的 `framer is None` 腿排除在外。一个端点若在响应头后守卫触发时根本写不出错误帧，就不满足上一段无条件的「必须一致」。说「与信封选择无关」不能消掉对客户端可见结果的矛盾。

可执行建议：把规范改成「同一语义事实、按各协议各自合法的 error carrier 写出」，并为每个方言分别列 JSON error 与 streaming error 形状。Anthropic 可以复用内层 error object；OpenAI Responses 必须用 flat `ResponseErrorEvent`，category 要通过明确规定的 `code` 或 message 策略承载；Chat Completions 要么进入范围实现错误帧，要么把 §6 限定为「有合法 streaming error carrier 的客户端腿」，并把缺口登记为待裁决而非已满足。

### F-04　[blocker] [把握：高] §7 把明确「待用户裁决」的选项 1 写成了实施指令

位置：`spec.md:154-166`。

章节标题、开篇与三个候选都承认这项尚未裁决，最后却写「在裁决到达之前，实施按第 1 个进行」。这会把未获授权的公共行为先做出去，再用注释声明它不是裁决。项目规则要求 observable behavior 的完整 Spec 先冻结；更重要的是，用户特别要求本次检查「有没有把需要裁决写成已获授权」，这里正是该错误，只是发生在 Spec 自己的实施命令里，而不是发生在权威引文中。

可执行建议：删除临时实施指令。冻结前先取得裁决；若实现工作必须并行，只能先完成不依赖该分支的结构性部分，不能让未知翻译错误通过任一候选行为出现在公共接口。

### F-05　[major] [把握：高] Spec 给用户亲笔响应头黑名单添加了不存在的「只为成功响应」限定，并把错误头合同藏到实施期

位置：`spec.md:47-48`、`spec.md:177-178`。

`message-format-reshape.md` 的「客户端返回 Anthropic Messages」没有成功／错误限定。Spec 自行说「该黑名单是为成功响应写的」，据此把错误响应是否适用留给「实施时核实并登记」，又在不在范围内章节排除黑白名单。这个新增限定没有权威依据，并且会把直接决定客户端重试与诊断的 `retry-after`、rate-limit 与 request-id 头留给实现者临场决定。

可执行建议：如果本轮用户裁决的「原生」意图足以覆盖错误响应，就明确规定错误响应沿用该直连黑名单；如果作者认为成功与错误必须不同，把它升入待用户裁决清单。不要用一个来源里没有的限定把行为推迟到实施阶段。

### F-06　[major] [把握：高] OpenAI 映射列是人为填满的表，不是经实际合同支持的语义映射；`RATE_LIMIT` 尤其把 `rate_limit_exceeded` 放到了错误层级

位置：`spec.md:100-117`。

当前 OpenAI SDK 只保证 `ErrorObject.type: str`，官方当前错误指南没有列出 `invalid_request_error`、`authentication_error`、`permission_error`、`not_found_error`、`rate_limit_exceeded` 或 `server_error` 这些 wire `type` 合同；它只明确展示过 `error.type=insufficient_quota`，并要求按 `error.code` 区分更具体原因。Responses streaming error 更直接：只有 `code/message/param`，没有 category type。

因此 `AUTH`、`PERMISSION`、`NOT_FOUND` 全塌成 `invalid_request_error` 不是「OpenAI 没有对应拼写」的结论，只是 Spec 自选的约定；裸 `str` 反而说明 writer 可以保留不同字符串，而不是必须压平。`rate_limit_exceeded` 在本 Spec 同时最像一个稳定 code，却被放进 `error.type`，而真正的 `code` 列没有定义。

可执行建议：先把 OpenAI 列改名为「本代理约定的 `error.type`」，明确它不模拟 OpenAI 的封闭词汇；随后优先用 status 决定 SDK 异常类，用 `code` 承载机器可读细分。若要声称模拟真实 OpenAI，请先用官方响应或录制固定每个类别的 `type/code` 对，而不是从类名猜。至少不要在没有必要时把 authentication、permission 与 not-found 三个内部概念压成同一字符串。

### F-07　[major] [把握：高] 「客户端能做不同动作」的切分类准没有落实到 status、默认 code 与 retry header，`billing_error` 和 `NOT_IMPLEMENTED` 暴露了反例

位置：`spec.md:96-118`、`spec.md:129-130`。

OpenAI 与 Anthropic Python SDK 都按 HTTP status 选择异常类，并默认重试 408、409、429 与全部 `>=500`；`error.type` 只提供额外细分。Spec 没有 category → status 表，也没有 category → 默认 code 表，更没有 `x-should-retry` / `retry-after` 策略。于是类别虽然在 IR 中分开，客户端动作仍未定义。

两个具体反例足以推翻当前「按动作切」的完整性。第一，Anthropic 的 `billing_error` 与 `permission_error` 都可能落在 403，而 SDK 正是靠 `.type` 让应用区分「去处理账单」与「去申请权限」；Spec 已知道 billing，却把它留给未来未知错误路径，这不是已闭合词汇表。第二，`NOT_IMPLEMENTED` 若保留现有 501，OpenAI 与 Anthropic SDK 都把它当 `>=500` 自动重试；`UPSTREAM` 502 也重试。两者映射为同一 type 且没有 `x-should-retry:false` 时，客户端默认动作完全相同，违背该 category 存在的理由。

可执行建议：补一张完整输出行为表，逐 category 规定 HTTP status、方言 type/status、默认 code、param、可转发 headers 与 retry 指令。把 `BILLING` 纳入当前表，或明确列为冻结 blocker。对 `NOT_IMPLEMENTED` 明确是否要阻止 SDK 自动重试；若要，两个 SDK 都支持的 `x-should-retry:false` 是可验证候选，但是否采用仍应作为行为决定写进 Spec，而不是由实现猜。

### F-08　[major] [把握：高] §2 把「路径未注册」纳入 IR，§8/§9 又把框架 404/405 排除，而且未知路径没有客户端方言可供 writer 选择

位置：`spec.md:35`、`spec.md:172`、`spec.md:180`。

未知路径不会进入 `serve/_dispatch`；FastAPI/Starlette 直接返回 `{"detail":"Not Found"}`。这正是 §8 所说的框架 404。§2 却把「路径未注册」列为本代理产生并按客户端方言写出的错误。两条同时成立不了，且 `/nope` 本身没有 route，无法推导 `inbound_format`，所以「按客户端方言」也没有定义域。

可执行建议：二选一并写明。若框架 404/405不在范围内，从 §2 删除「路径未注册」，并登记未来统一项；若要纳入，定义无 route 时的固定 fallback envelope 与方言判定规则，并接管框架异常。不要让清单声称覆盖、范围章节又取消覆盖。

### F-09　[major] [把握：高] Gemini 501 同时被纳入代理错误 writer，又被「实际 wire 翻译不实现」排除

位置：`spec.md:35`、`spec.md:125`、`spec.md:180-181`。

`端点未实现` 明确属于本代理产生的错误，Gemini 路径今天恰好答 501；§2 的表要求这类错误按客户端 inbound 方言 writer 输出，§4.4 也给了 Gemini envelope。§9 随后说 Gemini 实际 wire 翻译不随本切片实现。对当前唯一 Gemini 行为而言，错误 writer 就是实际 wire 输出，不能同时要求和排除。

可执行建议：明确本切片是否必须让 Gemini 的现有 501 采用 Gemini error envelope。我的倾向是纳入：它不要求实现成功请求翻译，只要求已有端点用自己声明的错误格式；若不纳入，就把 §2 的「所有本代理错误按客户端方言」限定到已实现 writer 的格式，并登记 Gemini 501 为显式缺口。

### F-10　[major] [把握：高] §7 的三个候选还不足以交给用户做一次闭合裁决，选项 1 的「SDK 一定能解析」也没有合同支撑

位置：`spec.md:158-164`。

选项 1 没有给「附加字段」命名、层级、编码或大小规则；选项 3 与选项 1 的核心行为都是按方言渲染 `UPSTREAM`，差别只剩 message 前缀，未说明原文放哪里。Anthropic 官方 ErrorObject 成员只声明 `type/message`，没有 `code/param` 或任意扩展字段；Python SDK 的异常 `body` 会保留原始 dict，但没有一等 `.code`，这不能推出所有目标 SDK 与客户端「一定能解析」任意附加字段。

可执行建议：在请求裁决前把候选改成互斥、字段完整的 wire 示例，并逐个写明信息损失与 SDK 行为。至少明确：未知原文是在 `message`、`code`、命名扩展字段还是只在服务端诊断记录；Anthropic/OpenAI/Gemini 各自是否允许；客户端看见的是 typed 属性、raw body 还是解析失败。然后删除未裁先实施句。

### F-11　[major] [把握：高] Anthropic 侧把分辨率损失寄托在自定义 `code`，但 Spec 没有命名这个扩展合同或证明目标客户端会读

位置：`spec.md:114-116`、`spec.md:129-130`。

Anthropic SDK 1.0.0 的九个 ErrorObject 成员都只有 `message/type`；现有 `error_frame()` 加的 `code` 是本项目扩展。Python SDK 会在 `APIStatusError.body` 中保留 dict，但只把 `.type` 提升为 typed 属性，没有 `.code`。因此 `code` 可以是本项目与已知客户端之间的扩展合同，却不能被描述成方言天然提供的「唯一机器可读通道」。若 Claude Code 或另一已知客户端已经读取它，Spec 应引用那个解析器与失败后果；若没有，客户端仍无法按它区分 `NETWORK`、`INTERNAL` 和 `NOT_IMPLEMENTED`。

可执行建议：把 Anthropic `code` 明确标成版本化的本项目扩展，列出已知消费者与兼容行为；若没有消费者，不要用它证明 §4.3 已满足「客户端不同动作」，而应依靠标准 status/type/header 或另行裁决扩展合同。

### F-12　[major] [把握：高] §4.2 对「官方 SDK 未声明」的独立结论成立，但把它升级成「Anthropic 不认识」超出了证据能力

位置：`spec.md:79-93`。

原清点用正则扫描 `.venv/.../anthropic/types/*.py` 的 `Literal["*_error"]`，再排除 `*_tool_result_error`。这个方法能提供候选清单，但不适合承重全称结论：类型可能经 alias、union 或不同引号／模块声明，扫全目录还会混入内容块类型。我的独立核验没有沿用正则，而是直接展开安装的 `anthropic==1.0.0` 的 `anthropic.types.ErrorObject` discriminated union，并交叉读取 `anthropic.types.shared.error_type.ErrorType`。两处权威 SDK 类型都恰好给出同一组 9 个顶层值；`network_error`、`upstream_error`、`internal_error` 确实不在其中。`*_tool_result_error` 排除也正确，因为它们不属于 `ErrorObject` union，而是内容块／工具结果的错误词汇。

但「不在 SDK 声明的顶层词汇表」不等于「Anthropic 服务或客户端一定不认识／拒绝」。SDK 的 `APIStatusError.__init__` 只是从 raw body 取 `error.type` 后 `cast(ErrorType, ...)`，没有 runtime validation；上游 API 也可能先于 SDK 发布新值。当前实测只证明代理发了非官方声明值，没有证明 Claude Code、Anthropic SDK 或真实 API 会拒绝它。

可执行建议：把 §4.2 的结论收窄成「不属于当前官方 SDK 声明的顶层 error vocabulary，因此不能声称是合同内 Anthropic 类型」。按官方词汇重映射仍然是合理目标，不需要推翻 §4.3；但删除「Anthropic 不认识」这类客户端行为断言，除非再用已知客户端解析器或真实 counterpart 证明其失败后果。静态 guard 也应基于 `ErrorObject` / `ErrorType` 的 union，而不是扫描全目录后按名称排除。

### F-13　[minor] [把握：高] §5 的「零字节到达客户端」把「失败事件未被转发」写成了「整个响应为空」

位置：`spec.md:138`。

实际三次请求分别收到 752、2903、749 字节；消失的是失败事件与其字段，先前完整块和代理合成的正常终结都到达了。下一句又说客户端拿到 `message_delta/message_stop` 或 `response.incomplete`，与「零字节」字面自相矛盾。

可执行建议：改成「失败事件本身零字节到达客户端，先前完整块仍交付，随后代理合成正常终结」。这不改变严重性判断，反而把失败机制说准。

## 四、§4.3 逐行语义与 SDK 动作核对

| `ErrorCategory` | 语义核对 | SDK 实际动作 | 结论 |
|---|---|---|---|
| `CLIENT` | Anthropic `invalid_request_error` 与 Gemini `INVALID_ARGUMENT` 对齐。OpenAI 字符串只能算本项目约定。 | status 400 才让 SDK 产生 BadRequest；type 不负责选类。 | 可保留，但必须补 status 400 与 code 规则。 |
| `AUTH` | Anthropic `authentication_error` 与 Gemini `UNAUTHENTICATED` 对齐。OpenAI 压成 `invalid_request_error` 会丢失 `.type` 信息，但 401 仍可让 SDK 正确分类。 | status 401 → AuthenticationError。 | 不需要为了「OpenAI 没有对应 Literal」而压平；其 type 本来就是任意 `str`。 |
| `RATE_LIMIT` | Anthropic 与 Gemini 对齐。OpenAI 的 `rate_limit_exceeded` 没有当前官方 `error.type` 合同，Responses SSE 只能放 `code`。 | status 429 → RateLimitError 并自动重试。 | 这一格像是为了填表把 code 写进了 type；应拆开。 |
| `NETWORK` | 没有上游响应时只能由代理合成；Anthropic `api_error`、OpenAI `server_error`、Gemini `UNAVAILABLE` 都是近似。 | 取决于代理选的 5xx；两 SDK 对所有 5xx 自动重试。 | 语义近似可接受，但必须明定 status/code，不能只靠 type。 |
| `UPSTREAM` | 三列都表达上游或服务内部失败，粒度粗但方向对。 | 5xx 自动重试。 | 可接受为兜底；直连上游原生类型不得先塌到这里。 |
| `INTERNAL` | 对客户端而言是代理内部失败；映成供应商 `api/server/internal` 是常见近似，但会与上游失败同形。 | 5xx 自动重试。 | 只有在标准字段之外确有可读 code 时才能保留动作差异；当前 Spec 未证明。 |
| `PERMISSION` | Anthropic `permission_error` 与 Gemini `PERMISSION_DENIED` 对齐。OpenAI SDK 依 status 403 正确分类，不依 type。 | status 403 → PermissionDeniedError。 | 应保留内部类别；OpenAI type 是否压平是本项目选择，不是外部限制。 |
| `NOT_FOUND` | Anthropic 与 Gemini 对齐。OpenAI SDK 依 404 正确分类。 | status 404 → NotFoundError。 | 同上，补 status 即可；压平 type 会损失应用级细分。 |
| `OVERLOADED` | Anthropic `overloaded_error` 与 Gemini `UNAVAILABLE` 对齐；OpenAI 没有已证的专属 type。 | Anthropic 标准为 529；OpenAI 常用 5xx，均会重试。 | 可接受，但要固定 status，不能只写 `server_error`。 |
| `TIMEOUT` | Anthropic `timeout_error` 与 Gemini `DEADLINE_EXCEEDED` 对齐；OpenAI `server_error` 是宽化。 | 传输 timeout 没有 HTTP response；代理合成的 504 会作为 5xx 重试。 | 需要区分「上游无响应 timeout」与「上游返回 timeout error」，并定义 status/code。 |
| `NOT_IMPLEMENTED` | Gemini `UNIMPLEMENTED` 精确；Anthropic/OpenAI 都塌成服务错误。 | 若 status 501，两 SDK默认自动重试。 | 当前映射无法兑现「客户端做不同动作」；需 retry 指令或重考 status。 |
| 缺失的 `BILLING` | Anthropic 官方有 `billing_error`，且它与 permission 的客户端动作明显不同。OpenAI 官方当前指南也要求按 billing `error.code` 细分。 | 可能与 permission 共用 403，必须靠 type/code 区分。 | 不是可忽略的未知供应商错误；应现在纳入或作为冻结前待裁项。 |

总体判断：Anthropic 与 Gemini 多数拼写语义相符；真正硬凑的是 OpenAI `error.type` 列，以及用未定义的 `code` 去声称所有分辨率损失已被补回。OpenAI 不是「没有 authentication/permission/not-found 的客户端概念」，而是把 SDK 异常分类放在 HTTP status 上，并把 wire `type` 留成开放字符串。

## 五、结构与范围总表

| 检查项 | 结果 |
|---|---|
| 自相矛盾 | 有。§6 的无条件同形与 one-shot 排除矛盾；§2 的路径未注册与框架 404 排除矛盾；Gemini 本地 501 writer 的要求与 Gemini wire 排除矛盾。 |
| 应定未定却未登记 | 有。错误响应头黑名单是否适用、source → category/status/code、Anthropic 自定义 `code` 消费者、`NOT_IMPLEMENTED` 是否禁止 SDK 重试都没有进入 §7。 |
| 决定藏在叙述而未进判据表 | 有。§5「直连流内事件也过 IR」是重大行为决定，却藏在括号理由中并违背顶层裁决；§7 临时实施选项 1 也是实施决定。 |
| §9 静默缩小范围 | 有。framework 404/405 与 Gemini 501 都在前文覆盖集合里，后文却排除；one-shot 腿使 §6 的不变量变成带例外但正文没改量词。 |
| v2 已正确修掉的 v1 问题 | 原始响应字节已丢失、one-shot 有已到达字节时并非空 body、无需把 `TranslatorRegistry` 当成唯一错误落点。 |

## 六、建议的最小修订顺序

1. 先让用户裁决 F-01 与 F-04：直连流内失败是否仍必须原生，以及翻译 reader 读不动时选哪种闭合 wire 行为。在这两项前不要冻结或实施 observable fallback。
2. 定义完整 `ErrorInfo` 记录与 source → IR 表，保留 `ErrorCategory` 作为其中一个字段；同时补 category → status/type/code/param/headers/retry 表。
3. 把「同形」改成「同语义、各方言合法 carrier」，单列 Anthropic JSON/SSE、OpenAI JSON/Responses SSE、Chat Completions SSE 与 Gemini JSON。
4. 修正覆盖集合：路径未注册、framework 404/405、Gemini 501、one-shot 四项各自明确纳入或登记待裁，不能前文纳入后文排除。
5. 最后再调整 OpenAI 与 Anthropic 映射。先用 status 保住 SDK 动作，再决定开放 `type`、标准 `code` 与本项目扩展字段；补上 billing 和 not-implemented 的重试语义。

## 七、证据边界与本次未采用的路线

- 按协调方更正读取了 `.dev/docs/server-layout/reports/260823-error-surface-inventory.md`，但没有修改它。该报告的 20 出口清单用来补足枚举范围；本报告的 blocker 与 major 仍由权威原文、当前源码、安装 SDK 或独立 HTTP 探针复核，没有把清点报告的自述当成唯一 oracle。
- 没有向真实 Copilot/OpenAI/Anthropic 发请求。当前行为命题换一个上游仍成立，MockTransport 更能隔离代理行为；OpenAI 的外部合同用官方文档与官方 SDK 当前源码核对。因没有真实 OpenAI 错误录制，本报告不声称「OpenAI 永远不会发某个 type」，只声称当前官方合同没有给这些字符串背书，SDK 也不把 type 当异常分派依据。
- 没有修改源文件、测试或 `docs/.human-controlled/`。唯一新增的非报告资产是用户授权目录下的探针与输出。

## 八、外部来源

- [OpenAI API error codes guide](https://developers.openai.com/api/docs/guides/error-codes#api-errors)
- [OpenAI Python `ErrorObject`](https://github.com/openai/openai-python/blob/main/src/openai/types/shared/error_object.py)
- [OpenAI Python `ResponseErrorEvent`](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_error_event.py)
- [OpenAI Python exception classes](https://github.com/openai/openai-python/blob/main/src/openai/_exceptions.py)
- [Anthropic Python `ErrorObject`](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/shared/error_object.py)
- [Anthropic Python `ErrorType`](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/shared/error_type.py)
- [Anthropic Python exception parsing](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_exceptions.py)

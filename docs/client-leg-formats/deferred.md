# 待办与已知缺口

来源：两份评审（`reports/260822-four-rulings-implementation-review.md`、`reports/260822-delivery-restructure-review.md`）逐条处置后的剩余项，加上按 `project-review-principles` 复查跑出来的。

**分类口径**（沿用 `delivery-keepalive/deferred.md`）：「缺陷」= 正确做法唯一，排期做掉即可；「裁决」= 存在真实岔路，不同选择导向不同产品行为或代价，归用户。

---

## 归用户裁决

### U-1 没有带 `function_call` 的 Responses 流式录制

`formats/openai_responses.py` 的 `_function_call` 那组帧、以及 reasoning item 的 `summary_text` 形状，都是**据 openai SDK 3.3.1 的类型与解析器推出来的，不是从录制读的**。仓库五份 cassette 一份都没有 `function_call`。

代码里已如实声明。补录要用凭据、发真实上游请求（`tests/int/recorded/record_cassette.py`），未擅自执行。

**不补的代价**：那组帧的形状只由 SDK 类型担保。SDK 的 `construct_type` 是宽松构造，不校验——所以缺字段在当前 oracle 下不可见。已加一条「逐事件对账 SDK 必填字段」的测试兜住这一层（`test_openai_responses_format.py`），但它管不了「字段齐全而语义错」。

### U-2 `--account-type` 与被删的 `--ghc-api-base-url` 同族，处置不一致

两者都是「在新链路上没有落点」的 CLI 选项。后者已删（它还是个静默空操作），前者保留并打印 `warning: ... has no effect`。

不一致本身是我造成的：我只删了用户点名的那一个。要么一并删，要么给保留写个理由。**归用户**，因为删 CLI 面是对外行为。

### U-3 `stream.py` 的 `framer` 缺省值硬编码为 `AnthropicFramer`

`framer=None` 时构造 Anthropic 成帧器。这是重构前就有的行为（当时直接调 `anthropic_sse` 的函数），命名重排只是原样换了 import 路径。

在「两个格式平等」这条线上，这个调用点不对等。改法是要求调用方总是显式传 framer——代价是 20 多处既有调用点（含同伴正在改的 `test_stream_delivery.py`）都要改。**当时选择不改是为了压缩与同伴的碰撞面**，不是判断它不该改。

### U-4 `synthetic` 一词在仓库里指三件事

`formats/anthropic_messages_synthetic.py`（搜索失败时合成的回复）、`handler.HandledRequest.synthesized`（整条回复由本代理写）、`stream.ContinuationSupport.synthesize`（流中途合成工具调用收尾）。本轮只给第一个加了格式前缀，没碰这层歧义。

---

## 缺陷（正确做法唯一）

### D-1 `_FINISHED` 是反向白名单，未识别的 stop reason 直接透传进 `incomplete_details.reason`

`formats/openai_responses.py`。`incomplete` 这一支已修（映射为 `null`，那是上游自己表示「没给理由」的形态）。但任何未列入 `_FINISHED` 的 stop reason 仍会原样进入 `incomplete_details.reason`，而 Responses 的词汇表里没有 `stop_sequence` / `pause_turn` / `refusal` 这些词。

当前可达性低（需要 `/responses` 入站配 Anthropic 方言装配器，被翻译器注册表挡着），但白名单默认的方向是危险的那一边。

### D-2 `ResponsesFramer.block` 对未知 kind 静默降级为空 text item

`else` 分支落到 `_message`，而未知 kind 的 payload 里没有 `TEXT` 键，于是发一个空文本 item。「没认出来」和「上游确实发了空文本」被抹平成同一个结果。

### D-3 `Terminal.upstream_usage` 只在一种模式下被写

按 `project-review-principles` 的 `one-reply-fact-one-answer-across-both-reply-modes` 复查跑出来的。写入方只有 `ResponsesAssembler._read_terminal`；`terminal_from_anthropic`（whole-body 路径）写 `usage` 但从不写 `upstream_usage`。

**今天无害**——whole-body 的 `/responses` 直接原样返回上游 body，根本不经过成帧器，所以没有另一侧的消费者。字段注释也写明了「空 = 未观测」。

**记在这里的理由**是那条原则的判据：将来给 `Terminal` 加一个键、或让 whole-body 路径也需要报 upstream usage 时，这个出口会不会被漏掉。同一形状在本项目已发作过三次。

### D-4 `refresh_in` 已无人读，却仍是硬性必填

`ghc_client/tokens.py` 解析 copilot token 响应时 `refresh_in=int(raw["refresh_in"])`，缺键就抛 `invalid Copilot token response`。后台刷新循环删掉之后，生产代码里没有任何地方读它。

于是：上游哪天不发这个字段，token 兑换会整个失败，而失败的理由是一个我们已经不用的字段。

### D-5 `one_shot_delivery` 的前提没有断言守着

它的正确性依赖「上游返回的就是客户端要的那种 SSE」——也就是这条路由未经翻译。当前由「没有 chat-completions 翻译器」这个事实构造性保证，但没有任何断言写下这件事。翻译器注册表哪天加了一个，这里会静默把 Responses 的字节原样发给 chat-completions 客户端。

### D-6 一次性交付路径上守卫触发时不发任何东西

客户端 deadline / 上游空闲超时 / attempt 超时触发时，异常穿过 `one_shot_delivery` 抛出，客户端拿到已发出的 200 和空 body，没有错误帧。

这与 U-1／块级边界是同一件未做的工作：**这条腿没有成帧器，就写不出这个协议的错误帧**。代码注释已如实说明。

---

## 小项

- **n-1** `response.id` 是裸 UUID，没有 `resp_` 前缀。上游真实值是 416 字符的 base64 串，我们本来就不模仿它；但 OpenAI 生态里 `resp_` 前缀是惯例。
- **n-2** keep-alive 那条测试的注释声称「它没有消耗序号」，而断言只检查了字节内容。
- **n-3** `test_exhausted_exchange_reports_the_failure_to_the_caller` 用 `pytest.raises(Exception)` 过宽。
- **n-4** `README.md` 痛斥 `model_copy(update=...)` 不校验，而 `resolve_provider_base_urls` 的最后一行自己用它换 `model_providers`（那一处是整个映射替换、不是按名字改字段，风险不同，但读起来刺眼）。
- **n-5** `stream_settings(chain)` 在 `_routed` 里被调用两次。

---

## 已在本轮修掉的（不要重复处理）

- `response.function_call_arguments.done` 缺 SDK 必填的 `name`、两个 `output_text` 事件缺 `logprobs` —— `db6f549`
- `incomplete` 透传进 `incomplete_details.reason` —— `db6f549`
- reasoning docstring 声称「照三份录制抄」而实际 summary 全为空 —— `db6f549`
- 一次性交付路径自称「以同样方式收尾」 —— `db6f549`
- 启动期探测失败一律阻止启动 —— `44fa576`（用户裁决后）
- `openai_responses.py` docstring 里的陈旧模块名、两处 `__init__` 的「一个格式一个模块」 —— `3e70ee8`
- 语料基数写成「三份 cassette」而仓库有五份 —— 本轮

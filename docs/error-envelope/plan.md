# 错误信封：实施计划

**这份是活文档**。规范判据在 [spec.md](spec.md)——**它同样是活文档，不冻结**，随新裁定与新发现当场修订，某条何时因何而变见它的条款修订记录；本文只答「按什么顺序做、每片怎么验」。

**v2**，采纳计划评审 [reports/260823-plan-review.md](reports/260823-plan-review.md) 的 4 条 blocker、10 条 major、1 条 minor，**全部**。处置见 [reports/260823-plan-review-disposition.md](reports/260823-plan-review-disposition.md)。v1 的切片划分（S0～S6）**不再使用**——它的 S1、S2、S6 都不是自洽的语义单位。

## 分层落点

三件事分开：**分类**（source → IR）、**IR**（记录本身）、**渲染**（IR → 方言字节）。

| 职责 | 落点 | 理由 |
|---|---|---|
| `ErrorCategory`、`ErrorInfo`、`category_for_status` | `app/errors.py` | 实测是零 `app.*` import 的叶子（新解释器导入它只加载它自己）。**必须保持**：`ErrorInfo.conversion` 用 `TYPE_CHECKING` 引用 `Conversion` 并设为必传字段，**不得** `default_factory=Conversion`——那会让叶子运行时反向依赖 `translation_driver` |
| pipeline 封闭异常集的分类 | `app/pipeline/error_classify.py`（新） | 它认得 `app.pipeline.exceptions` 与 `app.model_provider.types`，两者都在 pipeline 侧或更内层 |
| server 独有来源的分类 | `app/server/http_errors.py` | `InboundRequestError` 定义在 `app.server.inbound`；让 pipeline 认识它会造出 `pipeline -> server` 反向边。**边缘自己建 `ErrorInfo`**，不把这个来源推给 pipeline |
| 各方言的 error writer | `app/pipeline/delivery/formats/*.py` | wire 形状归 codec 边界；`anthropic_messages.error_frame` 已经在那儿 |
| 统一的 HTTP 响应工厂 | `app/server/http_errors.py` | 见 J 片 |

**实测过的依赖事实**（评审的 AST + 运行时探针）：全 `src/app` 静态图强连通分量为 0（无环）；`app.errors -> ∅`；当前没有任何在用 `app.pipeline.*` 导入 `app.server.*`。`http_errors -> formats.* -> app.errors` 是 server 向内的正常依赖，不成环。

**既有的 `test_module_boundaries.py` 四条断言看不见这些性质**（评审实测：新落点下它们仍全绿）。所以要新增两条：`reachable_from("app.errors") == {"app.errors"}`，以及 AST 断言 `app.pipeline` 不导入 `app.server`。

## 切片

顺序即依赖顺序。每片单独提交，每片自身是自洽的语义单位。

### D　建 deferred 台账（**排在第一个实施提交之前**）—— **已完成**，`.dev` `1dd1d6d`

Spec §10.2 明写「实施时建立」，§11 要求七项逐项登记，而 `deferred.md` 至今不存在。计划的「推迟项」一节不等于台账——计划会关闭，台账只保留未闭合项。

**做**：建 `error-envelope/deferred.md`，收 §10.2 与 §11 的全部条目，各自引 Spec 当前版本为权威。后续闭合的从台账移出并更新对应活文档。

### S0　保住上游的原始字节 —— **已完成**

主仓 `249c894`。`_response_parts` 一并取原始 `bytes` 与 `content-type`，三个分支都带；`body` 保持不变。四条变异全打红。

### I　IR 与分类（一次提交，不留半宽枚举）—— **已完成**，主仓 `3533386`

Spec §4、§5。**评审 F-06 指出 v1 的致命问题**：`ErrorCategory` 从 6 扩到 12 而 `WIRE_TYPES` 只有 6 个键，`ApiError(category=NOT_FOUND).wire_type` 会 `KeyError`——那是可观测回退，不是「暂时的死代码」。

- `app/errors.py`：`ErrorCategory` 扩到 12（现有 6 个拼写不动）；`ErrorInfo` 的 **10 个字段**（`category`、`message`、`status_code`、`code`、`param`、`headers`、`source_format`、`source_bytes`、`source_content_type`、`conversion`——Spec §4.2 的表是 9 行，但 `source_bytes / source_content_type` 那行命名了两个）；`category_for_status`（Spec §5.2）。
- **同一提交内**让每一张以 `ErrorCategory` 为键的表覆盖全部 12 键，或让它退场。`WIRE_TYPES` 在此片就换成按方言分层的表，不留窗口。
- `app/pipeline/error_classify.py`：`describe`，覆盖 pipeline 侧来源与 `ProviderError` 家族五个子类（Spec 2026-08-23 条款修订记录第 1 条）。
- `pipeline/count_tokens.py`：`CountTokensUnavailable` **保留 cause**。今天它只存字符串 attempts，不存任何异常对象，所以「读穿到成因」在它现在的形状下做不到。哪一条失败作为 cause 要写进代码注释。

**落地后新增的一条事实**（由既有测试暴露，已写回 Spec §6.4）：把 Anthropic 那一列改成真实词汇后，`INTERNAL` 与 `UPSTREAM` 都塌成 `api_error`，而 `tests/unit/pipeline/delivery/test_stream_delivery.py` 里两条测试原本正是靠 `internal_error` / `upstream_error` 区分「本代理的 bug」与「上游断了」。**流式帧上 status 早已发出，所以 `code` 是那里唯一的通道**——两条测试已改钉 `code`。

**验**：
- **测试侧手工转录** Spec 当前版本的每一行（**Spec 是活文档：条款修订时必须同改本转录，否则测试会静默落后于 Spec 且仍然全绿**），每 case 一个稳定 id、一个 source constructor、一份完整 expected 投影（`category`/`status`/`code`/`param`/`source_*` 全断，不只断 `category`）。**不得从生产表生成 expected**——评审 F-11 说得对，那是同源恒真：删一行则参数数也少一行，写错值则 expected 同时变错，测试仍绿。
- 另设独立字面量 `EXPECTED_CASE_IDS`，断言 `set(CASES) == EXPECTED_CASE_IDS`；生产侧若用 registry，再断言 registry 的键与这组 id 相等。
- §5.2 另用测试侧字面 status→category cases，**至少含** 403 的 billing 分支、catch-all 的 418 与 599、以及边界值。
- 钉 `ProviderError` 的子类集合：新增一个子类必须被显式分类才能通过。
- 断言 `set(每张方言表) == set(ErrorCategory)`；变异：删一行、改坏一个值，都必须红。
- module-boundary：新解释器导入 `app.errors` 仍只加载它自己。

### J　JSON 出口：统一工厂、直连透传、全部早期出口、Gemini 501 —— **已完成**，主仓 `c4216f7`

Spec §2、§3.1、§3.3、§5.1、§6.1～§6.4、§9、§10.1。**第一个改变可观测行为的切片，也是必须一次做完的那个。**

评审 F-01 指出：`error_status` / `error_body` / `error_headers` 三件套加 `JSONResponse` **表达不了**字节透传——`JSONResponse` 的输入是待序列化对象，且它自己决定 Content-Type。

- `http_errors.py` 收敛为一个工厂：`error_response(source, *, inbound_format, translated) -> Response`，`source` 接受 `BaseException | ErrorInfo`。
  - 直连 + 上游错误 → `Response(content=body_bytes, status_code=..., headers=过滤后的原头)`，Content-Type 由保留下来的原头决定。
  - 其余 → 方言 writer → `JSONResponse`。
- **所有早期出口一并改接**（评审 F-09）：请求体非 JSON、顶层非对象、`route.implemented=False`、`InboundRequestError`。这四处今天绕过 `http_errors` 直接 return 字符串信封；它们没有异常对象的那三处由边缘自建 `ErrorInfo`。
- **Gemini 501 用 Gemini writer**（Spec §9）。错误 writer 就是该端点今天唯一的 wire 输出，只建 writer 不接线等于没做。
- JSON writers（Anthropic / OpenAI 三种 / Gemini）随本片落地——**按首个生产消费者切，不提前建**（评审 F-07：本项目已为「原语留在没人调用的链路上」付过代价）。
- `UnknownModel → 404`、`TranslatorNotFound → 501` 的行为变更在本片发生（评审 F-08：接了 `describe` 就必然发生，不可能推到后面）。
- `x-should-retry: false` 的**唯一生产者**写死：classifier 决定 category/status/default code，HTTP 边缘只在代理自产的 `INTERNAL` / `NOT_IMPLEMENTED` 上合成该头；**直连上游错误不得覆盖上游原头**。

**落地后的三条修正**（都由变异暴露，三条变异原本没打红）：
1. `headers["content-type"] = ...` 是**死代码**——`Response(media_type=...)` 已经在做，那行看起来像机制而不是。已删。
2. `x-should-retry` 条件里的 `not direct` **今天不可达**：没有任何上游状态码映射到 `INTERNAL`／`NOT_IMPLEMENTED`（`category_for_status` 把所有 ≥500 送到 `UPSTREAM`）。保留该项并在注释里写明它是结构性而非可达的，同时把那条假装在检查它的测试改名、改成它真能观察的事。
3. writer 原本可以**无条件**附上 `upstream_error` 而所有断言照样通过——缺一条「能读懂时它不出现」的缺席断言。已补。

**另外补了一个真实遗漏**：`CountTokensRequestError` 没有分类分支，落到 `INTERNAL`／500 而 Spec 说 `CLIENT`／400。它已从 `driver` 搬到 `count_tokens`，这样分类器能指名它而不必把整条请求管线拖进来。

**验**（评审 F-12：现有判据分不出「真透传」与「解析后重新序列化成相同 JSON」）：
- 真实 ASGI 入口 + MockTransport。直连样本用 `b"\xffraw-body"` 或带 BOM 的字节，**普通 JSON 样本不行**——错误实现 parse 再 dump 也能相同。
- 同一响应带上 `content-type: text/html`、`x-request-id`、`anthropic-ratelimit-*`、原写法的 `retry-after`，以及应剔除的 `content-length` / `content-encoding` / `connection`。逐个断言保留与剔除。
- 翻译对照走 `translation_required=True` 的**真实 route**，断言客户端方言信封与默认 code/status/header，不是直接调 writer。
- 变异：把直连分支改成走 writer、或让工厂忽略 `translated` 参数，都必须红。
- Gemini 501 必须有真实 endpoint 测试。
- 未知上游错误在翻译路径上产生 `upstream_error` 结构化扩展（Spec §10.1）。

### F　流式词汇：framer 的 error 契约与三个现有 SSE 出口

Spec §6.1、§6.3、§7。

- `OutboundFramer` 的 error 契约改为收 `ErrorInfo`；各腿的流式 writer 随本片落地。
- `stream.py` 的三处 `framer.error(...)` 改为传 `ErrorInfo`；generic delivery **不直接 import 具体 format**，只经 framer 接口。
- 删掉平表 `WIRE_TYPES`（若 I 片未删完）。

**验**（评审 F-13：只断言「Anthropic 那列的值都在 SDK union 里」是子集检查，缺一行也真空通过；而且不证明生产 SSE 用了新表）：
- 静态：同时断言 `set(anthropic_mapping) == set(ErrorCategory)` 与 `set(values) <= sdk_union`。**union 从 `anthropic.types.shared.error_type.ErrorType` 取，不扫目录做正则**。两种变异——删一行、改坏一个值——都必须红。
- 行为：从真实入口分别触发客户端截止、上游撕裂、本侧 `BufferCapExceeded`，断言实际收到的 Anthropic `error.type` 对应 Spec 的 `TIMEOUT` / `NETWORK` / `INTERNAL`。这同时证明接线与分类，不只证明表的内容。
- module-boundary：断言 generic `stream.py` 不直接 import `formats.*`。
- **信封形状护栏**（2026-08-24 新增，依据 Spec §6.3 的两条硬约束）：断言 anthropic-messages 流式 error 帧的 payload **顶层没有 `message` 键**、且 `error.type` 在嵌套的 `error` 对象里。判据不要写成「等于某个字面串」，而要钉住结构——扁平化是唯一要拦的变异。正样本对照：把 framer 改成扁平输出，该断言必须变红。理由与实测见 [reports/260824-claude-code-sse-retry-behavior.md](reports/260824-claude-code-sse-retry-behavior.md)；形状判定可用同目录探针复现。
  - **不在本片内**：Spec §6.3 第 2 条的「错误帧必须早于第一个非 thinking 内容块」是**交付时机**约束，不是成帧约束，落点在块级交付那一侧而非 framer。本片只固化形状。**时机已于 2026-08-24 移交给 `delivery-keepalive`**——接收端登记在 [`../delivery-keepalive/spec.md`](../delivery-keepalive/spec.md) §3.5（事实）与 [`../delivery-keepalive/deferred.md`](../delivery-keepalive/deferred.md)（未裁决项）。⚠️ 本句原文只写「留待那边排期」而**从未通知过那边**，那边一无所知达数小时——搬走内容不留转发地址不报错，只是此后没人找得到。

### R　流内失败事件：typed seam、直连原样重放、翻译过 IR

Spec §3.4、§3.5、§5.3、§7、§10.1。**清点里唯一「把失败伪装成成功」的出口。**

评审 F-03 指出：今天 `BlockAssembler.push()` 只返回 `tuple[CompletedBlock, ...]`，两个 assembler 遇到失败事件都是记日志返回空；`stream_delivery` 拿不到 `translation_required`；而同一个 `ResponsesAssembler` 同时服务直连与翻译，**从 assembler 或 framer 的类型都推不出该走哪条**。所以数据通道与策略选择点必须先定义。

- 定义 format-neutral 的失败结果：`StreamFailure(source_event, source_data, info)`，由 assembler 通过显式通道返回。
- `inference.py` 依据已知的 `route.translation_required` 把直连／翻译策略传入 delivery；`stream.py` 只消费策略与 typed result，**不 `isinstance` 具体 assembler/framer**。
- 直连策略：只重建 SSE 包装，重放 `source_event` + `source_data`。
- 翻译策略：`info` 交给客户端 framer/writer。
- 两条腿都**必须在合成终结事件之前终止**。
- 修正 `anthropic_messages.py` 与 `openai_responses.py` 那两句已不成立的注释。

**验**（评审 F-14：现有判据可由「认出 Anthropic `event:error` 就原样吐回」这一条特判满足）：四组真实入口断言——
1. Anthropic 直连保留 event 名与我们不认识的字段；
2. Responses 直连分别保留 `response.failed` 与 `response.cancelled`，**不得统一改名成 `error`**；
3. Responses→Anthropic 翻译，已知 code 落到正确的 category/status/code；
4. 未知 code 走 §10.1 的 `UPSTREAM` + 结构化 `upstream_error`。

每组都断言失败之后**没有**正常 terminal。另选一个能在响应头前／后都出现的同义上游失败，比较两侧最终的语义投影——这才是 §7 的判据，只比较 writer 函数不是。

### C　count_tokens 读穿到成因

Spec §5.1（清点 E6）。上游 400 与 500 今天都被压成 503，上游 body 一字节不到。cause 的保留在 I 片已完成，本片只接 wire。

**验**：上游 400 与上游 500 分别到达客户端时状态与信封不同；直连路径上拿到上游原生 body。

### N　上游 200 但 body 不是 JSON

Spec §5.1（清点 E18）。今天异常逃出 `_dispatch`，客户端拿到 `500` + `text/plain` + `Internal Server Error` 五个字。改为显式捕获 → `UPSTREAM` / 502 + 方言信封。

**验**：真实入口，上游答 200 + `<html>`，客户端拿到 502 与方言信封而非 `text/plain`。

## 推迟项

**都进 D 片建的台账**，本节只是索引：

- **Chat Completions 流式腿的 error carrier**（Spec §10.2，用户 2026-08-23 裁决推迟）。它使 Spec §7 的不变量带例外。`inference.py` 里那句说该腿给出空 body 的注释与实测不符（实测给出的是已到达的上游字节），随 J 片或 F 片修正。
- Spec §11 登记的七项。

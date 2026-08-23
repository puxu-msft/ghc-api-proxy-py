# 错误信封实施计划评审

评审日期：2026-08-23。

评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/plan.md` 的工作树版本，SHA-256 为 `59131d094c2b4879cf33234a1176802476b6f45ff5bd681313def4d6121c8fc6`，文件时间为 `2026-08-23 18:18:28 +0000`。规范权威是同目录冻结的 `spec.md`，本次读取版本 SHA-256 为 `89fa75e24b0fb87adc164d6be092c74486f8d43da89fc16a30566f5e9e672934`。主仓库代码锚点为 `HEAD=0ebdfd0749cea16139c0ddd9a9151d4c2a116422` 加当时工作树。

技能说明：用户要求先调用 `my-skills:as-reviewer`，但该名称不在本会话的可用技能清单中；已按指示回退并实际调用 `verifying-authoritative-claims`。任务涉及 Anthropic SDK 错误词汇，又调用了 `claude-api:claude-api`；外部合同结论仍只采用冻结 Spec 与当前锁定 SDK／源码，不让该技能改写 Spec。

并发说明：评审开始时 `src/app/model_provider/ghc_client/errors.py` 与 `src/app/pipeline/exceptions.py` 尚未出现在 `git status --short`，评审期间两者同时变为修改状态，文件时间分别为 `18:24:14` 与 `18:20:06 +0000`。这是主会话正在实施 S0；本报告不评 S0 实现质量，只按读取时的结构判断计划，并没有修改任何源文件。探针只写入 `/home/xp/.claude/jobs/08aff420/tmp/`。

## 结论

**结论：needs-fix。共 4 条 blocker、10 条 major、1 条 minor。** 这一结论的证据强度为“足以据此修改计划”：两个 blocker 是当前函数签名与调用链直接证明无法实现目标，另一个 blocker 是当前流式接口没有承载失败事件的通道，最后一个 blocker 是冻结 Spec 自己漏掉了当前可达错误，实施者无权替用户补语义。分层的大方向可以成立，但当前计划还没有把跨层数据契约与每个出口的接线写闭合；S0 可以继续，S1 之后不宜按现计划切片提交。

严重度口径：`blocker` 表示按当前计划无法满足冻结合同，或必须在计划外临场发明公共行为；`major` 表示会留下未接线实现、假绿验收、不可独立提交的中间态或明确漏项；`minor` 表示不会单独改变行为，但文字歧义会让实现字段漂移。

## 一、依赖方向实测

仓库没有 `.codegraph/`，因此没有自行建索引；我用 AST 导入图与新解释器运行时可达集交叉核对。探针为 `/home/xp/.claude/jobs/08aff420/tmp/error_envelope_import_probe.py`。

当前静态直接边是：`app.errors -> ∅`；`app.pipeline.delivery.stream -> app.errors + delivery generic modules + retry + streaming guards`；`app.pipeline.delivery.formats.anthropic_messages -> app.config.schema + delivery generic modules`；`app.pipeline.delivery.formats.openai_responses -> delivery generic modules + translation reasoning carrier + protocol converter`；`app.server.http_errors -> app.model_provider + pipeline.count_tokens/driver/exceptions/routing/translation_driver`。全 `src/app` 静态图中强连通分量数量为 0，即当前没有模块导入环。

运行时结果进一步确认 `app.errors` 是严格叶子：新解释器导入它只加载 `app.errors` 自己。导入任一现有 format 模块会加载 38 个 `app.*` 模块，因为 Python 先执行 `app.pipeline.delivery.__init__`，而该文件同时再导出 Anthropic 与 Responses 两个 format；导入当前 `app.server.http_errors` 已加载 103 个 `app.*` 模块。后两个数字只说明包初始化的真实成本，不代表成环。

按计划最小实现，`http_errors -> formats.* -> app.errors` 是 server 向 pipeline codec 边界的正常向内依赖；当前没有任何在用 `app.pipeline.*` 模块导入 `app.server.*`，所以这组边本身不会制造反向依赖或成环。真正会反向的是让 `app.pipeline.error_classify` 为了识别当前的 `app.server.inbound.InboundRequestError` 而导入 server，见 F-02。真正会打破叶子声明的是让 `app.errors.ErrorInfo` 在运行时导入 `Conversion`，见 F-05。

`uv --directory /home/xp/src/ghc-api-proxy-py run pytest /home/xp/src/ghc-api-proxy-py/tests/unit/test_module_boundaries.py` 在本次快照上是 `4 passed`。现有四条断言分别约束归档模块不可解析、typed content kernel 不拖入 protocol、pipeline exceptions 不拖入 provider/upstream、h2 静态 import allowlist；它们都不会发现 `app.errors` 失去叶子地位、pipeline 新增 server 反向边，或 generic `stream.py` 直接认识 format。因此，按一个合理实现，既有断言不会被新落点直接打破；但“既有测试仍绿”也不能证明新落点成立。可执行建议是在 S1 增加 `reachable_from("app.errors") == {"app.errors"}`，并用 AST 断言 `app.pipeline` 不导入 `app.server`；S4 再断言 generic stream 只经 `OutboundFramer` 写出，不直接导入 `formats.*`。

## 二、发现

### F-01　[blocker] [把握：高] S3 的“三件套 + JSONResponse”接口无法完成原始字节与 Content-Type 透传

位置：`plan.md:49-58`；当前调用点 `src/app/server/routes/inference.py:207-211`、`:255-259`、`:274-278`。

计划只说改造 `error_status`、`error_body`、`error_headers`，但三个调用点仍把 `error_body(...)` 交给 `JSONResponse`。`JSONResponse` 的输入是待 JSON 序列化对象；直接交 `bytes` 不能产生原始响应体，且它会选择 JSON Content-Type。Spec §3.1 明确要求任意 body 字节、原 status、过滤后的原 headers 与原 Content-Type 一起透传，所以这不是实现细节，而是当前 API 形状表达不了目标。

可执行建议：S3 明确把三件套收敛为一个边缘工厂，例如 `error_response(error, *, inbound_format, translated) -> Response`。直连上游错误分支返回 `Response(content=body_bytes, status_code=status_code, headers=filtered_headers)`，让过滤后仍保留的 `content-type` 原值决定类型；翻译或本代理错误分支才调用方言 writer 并返回 `JSONResponse`。三个调用点同片改接工厂，避免分别调用 `describe` 三次后得到可能不一致的结果。

### F-02　[blocker] [把握：高] `describe(error)` 在 pipeline 层不可能覆盖 Spec §5.1 声称的 14 行

位置：`plan.md:28-35`；Spec §5.1；当前 `inference.py:150-165` 与 `server/inbound.py:18`。

14 行里至少三类没有能传给 `describe` 的异常对象：请求 JSON 非法与顶层非对象是直接返回字符串信封，`route.implemented=False` 也是直接返回；`InboundRequestError` 虽然是异常，却定义在 `app.server.inbound`。若 `app.pipeline.error_classify` 为识别它而导入 `app.server.inbound`，就形成计划试图避免的 `pipeline -> server` 反向依赖；若不导入，计划所谓“实现 14 行表”就不成立。当前函数签名也不能表达“代理已知要发 NOT_IMPLEMENTED，但没有异常实例”的来源。

可执行建议：计划先裁定 source reader 的公共契约，再实施。可选的最小做法是让 HTTP 边缘工厂同时接受 `BaseException | ErrorInfo`，把无异常的三个早期分支在 server 侧显式建成 `ErrorInfo`；同时把 `InboundRequestError` 移到不依赖 server 的叶子模块，或把它也先转成 `ErrorInfo` 后再进 writer。另一条可行路线是为这些来源建立叶子级 typed errors，再统一交给 `describe`。无论选哪条，都要把它写进计划；不能让实现者在 S3 临场决定。

### F-03　[blocker] [把握：高] S5 没有定义失败事件从 assembler 到 delivery 的数据通道，也没有定义直连／翻译选择点

位置：`plan.md:69-78`；当前 `delivery/assembling.py:61-77`、`formats/anthropic_messages.py:269-301`、`formats/openai_responses.py:409-445`、`delivery/stream.py:321-346`。

当前 `BlockAssembler.push()` 只返回 `tuple[CompletedBlock, ...]`，两个 assembler 遇到失败事件都记录日志后返回空 tuple；`stream_delivery` 只拿到 blocks、terminal 与 framer，没有 `Route.translation_required`。同一个 `ResponsesAssembler` 同时服务 Responses 直连和 Responses→Anthropic 翻译，所以不能从 assembler 类型推断该原样重放还是读入 IR；从 framer 类型反推会把 generic delivery 绑到具体格式。计划只写结果，没有写承载原始 event 名、原始 data 与 parsed `ErrorInfo` 的 typed seam，实施者必须在核心架构上自行发明。

可执行建议：S5 先定义一个 format-neutral 的失败结果，例如让 assembler 的返回值能携带 `StreamFailure(source_event, source_data, info)`，或增加等价的显式失败通道；由 `inference.py` 依据已知 `route.translation_required` 把直连／翻译策略传入 delivery。直连策略只重建 SSE 包装并重放 `source_event + source_data`，翻译策略把 `info` 交给 client framer/writer。`stream.py` 只消费这个策略与 typed result，不直接 `isinstance` 具体 assembler/framer。该失败分支必须在 terminal 合成前终止。

### F-04　[blocker，Spec 自身问题，不计作计划偷改] [把握：高] 冻结 Spec §5.1 的“完整清单”漏掉了当前可达的 `EndpointNotSupported`

位置：Spec §5.1；当前 `model_provider/types.py:45-49`、`pipeline/routing.py:97-101`。

这不是旧 Spec 评审已闭合的 13 条之一。一次真实 ASGI + MockTransport 探针通过 `/v1/messages` 请求 `claude-model@openai-responses`，稳定得到 `400` 与 `{"error":{"type":"EndpointNotSupported",...}}`，且上游请求数为 0；探针在 `/home/xp/.claude/jobs/08aff420/tmp/error_envelope_omitted_provider_probe.py`。同一 `ProviderError` 族里还有 `ProviderNotConfigured` 与 `EndpointNotImplemented` 的 raise site，但一个已证可达反例已经足以推翻“完整清单”。计划若只实现 14 行，会漏；若用 `ProviderError -> CLIENT/400` catch-all，又是在冻结 Spec 外发明 type、code 与 retry 行为。

可执行建议：把这条交回 Spec 权威单独补裁，不混入计划措辞。最低限度要为 `EndpointNotSupported` 指定 category/status/default code；若采用 `ProviderError` catch-all，也要由 Spec 明写其边界与更具体子类优先级。计划在该裁定前可以保留结构工作，但不能宣称 source→IR 表已完整实现。

### F-05　[major] [把握：高] `ErrorInfo.conversion` 与“app.errors 零 app import”之间缺少可执行落法

位置：`plan.md:8-13`、`:32`；Spec §4.2；当前 `translation_driver/semantic.py:77-94`。

Spec 要求 `ErrorInfo.conversion` 使用与请求／响应相同的 `Conversion`；该类型今天定义在 `app.pipeline.translation_driver.semantic`。若 `app.errors` 为默认工厂直接 import 它，当前实测的 `app.errors -> ∅` 立刻变为 core leaf 反向依赖 pipeline，计划第 10 行的理由失真。若只写 `Any` 或另造一份 conversion，又没有落实 Spec 的“同样的 Conversion”。

可执行建议：在计划中固定一种不产生运行时反向边的实现。最小方案是在 `TYPE_CHECKING` 下引用 `Conversion`，让 `ErrorInfo` 的 `conversion` 成为必传字段，并由 `error_classify` 创建后传入；不要在 `app.errors` 内做 `default_factory=Conversion`。若必须默认构造，则先把 `LossCode/Loss/Conversion` 抽到比 errors 与 semantic 都低的叶子模块，并把这次搬迁算进 S1。S1 的 module-boundary 验证必须证明新解释器导入 `app.errors` 仍只加载自身。

### F-06　[major] [把握：高] S1 单独落地会扩宽枚举却留下以它为键的旧表不完整，且 CountTokens 行在当时没有 cause 可读

位置：`plan.md:28-35`、`:80-87`；当前 `app/errors.py:3-19`、`pipeline/count_tokens.py:23-28`。

S1 把 `ErrorCategory` 从 6 个扩到 12 个，S4 才删除 `WIRE_TYPES`。两片之间 `WIRE_TYPES` 只有 6 个键；`ApiError(category=ErrorCategory.NOT_FOUND).wire_type` 等合法新值会产生 `KeyError`。这是具体可观测回退，不只是“暂时有死代码”。同时 `CountTokensUnavailable` 当前只保存字符串 attempts，不保存任何 cause；S1 无法按 §5.1 对它“读穿到成因”，而 S6 才打算改行为。S1 所称完整分类在自己的提交态做不到。

可执行建议：不要让枚举扩容早于所有枚举键表。优先把 S1 与每个方言的完整 key set 原语放在同一语义提交，并立即让旧 `WIRE_TYPES` 覆盖全部 12 键或同时退场；测试固定断言 `set(mapping) == set(ErrorCategory)`。`CountTokensUnavailable` 的 cause 保留应前移到 S1，哪一条失败作为 cause 也要写明，再由 S3／专门 count_tokens 切片接 wire。

### F-07　[major] [把握：高] S2 不是“纯新增”，且多数 writer 在 S2 提交态仍是测试专用死代码

位置：`plan.md:37-47`。

S2 明确修改现有 `anthropic_messages.error_frame`，所以不是纯新增；这部分至少进入当前 SSE 路径。相反，OpenAI JSON、Chat Completions JSON、Gemini JSON 与未知上游扩展 writer 在 S2 都没有生产调用方，测试能证明“给定自造 ErrorInfo 会序列化”，不能证明客户端链路使用它。项目已经为“守卫／原语留在没人调用的链路上”付过代价，这一切片复现了同一形态。

同一验收句“每种方言 ×（JSON / 流式）各钉一条”也不可执行：Chat Completions 流式 carrier 被 Spec §10.2 明确推迟，Gemini 流式在 §11 排除，Embeddings 也没有流式腿。实现者只能擅自扩范围或静默跳过矩阵格。

可执行建议：按首个生产消费者切 writer，而不是一次建完。Anthropic／Responses 流式 writer 与 S4 同片，JSON writers 与 S3 同片，Gemini writer 与 Gemini 501 的实际接线同片；若仍保留 S2，则把 S2+S3 作为一个不可拆提交边界。验收矩阵改成 Spec §6.3 明列的合法 carrier 集，并把被推迟／未实现的格显式标为 N/A，不写笛卡尔积。

### F-08　[major] [把握：高] S3 已经必然实施 S6 的两项状态变化，S6 不是独立语义片且完全没有“验”

位置：`plan.md:49-58`、`:80-93`。

S1 的 `describe` 已按 Spec 表产生 `UnknownModel -> 404`、`TranslatorNotFound -> 501`，S3 又把现有 `error_status/error_body` 调用接到 `describe`。因此这两项对外行为在 S3 就发生，不可能等到 S6；若 S3 刻意继续覆写成 400，则 S3 自己违反冻结 Spec。S6 剩下的 `CountTokensUnavailable` 与“200 非 JSON”又是两条不同入口、不同数据机制，不能由“零散项”证明为一个可回退单元。更直接的问题是 S6 没有任何验收段。

可执行建议：把 UnknownModel／TranslatorNotFound 的行为与测试归入 S3；把 count_tokens cause 保存与出口接线做成单独切片；把上游 200 非 JSON 的显式捕获与方言错误响应做成另一切片；两处注释分别随改掉其事实的 S5 与 one-shot 相关片落地。每片都补真实入口正样本与旧行为反样本。

### F-09　[major] [把握：高] 有三组规范要求只有“writer／章节引用”，没有任何生产出口负责接线

位置：`plan.md:37-58`、`:95-99`；Spec §3.3、§6.2、§9、§10.2、§11。

第一，JSON 非法、顶层非对象与 `route.implemented=False` 都绕过 `http_errors`；计划没有一片改这三个 return，所以本代理早期错误不会统一过 IR。第二，S2 只“落地 Gemini writer”，S3 只改 `http_errors`；Gemini 501 的当前 return 仍不调用 writer，Spec §9 实际 wire 没有完成。第三，`x-should-retry:false` 属于 HTTP headers，不可能由只返回 body dict 的方言 writer 单独实现；计划虽给 S2 标了“§6.2”，却没有指定由 classifier 还是 HTTP edge 产生它，也没有验证 INTERNAL／NOT_IMPLEMENTED 两格。

可执行建议：在 S3 明列并改接所有早期 return，让它们传 `ErrorInfo` 给统一 response factory；Gemini 501 必须有实际 endpoint test。把 §6.2 的所有者写死：classifier 决定 category/status/default code，HTTP edge 只在代理自产 INTERNAL／NOT_IMPLEMENTED 上合成 `x-should-retry:false`，直连上游错误不得覆盖上游原头。若选择别的分工也可以，但计划必须能逐字段指出唯一生产者。

### F-10　[major] [把握：高] Spec 要求的 deferred 登记当前不存在，计划也没有任何切片创建它

位置：`plan.md:95-99`；Spec §10.2、§11；当前目录文件清单。

当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/deferred.md` 不存在。计划末尾只说 Chat Completions 流式腿与 §11 七项“推迟／已登记”，没有创建步骤；Spec §10.2 明写“实施时建立”，§11 又要求每条登记，项目规则禁止发现后静默裁掉。把清单写在计划的“推迟项”里不等于完成指定 ledger，因为计划结束后仍会被关闭，而 deferred 应只保留开放项。

可执行建议：增加一个明确文档切片，在第一次实施提交前创建 `error-envelope/deferred.md`，逐项收录 §10.2 与 §11 的七项，并引用冻结 Spec 作为权威；后续关闭项从 ledger 移出并更新相应 living doc。该动作不应藏在 S6 的“零散项”中。

### F-11　[major] [把握：高] S1 所谓“从表结构生成每行断言”若用生产表生成 expected，就是同源恒真 oracle

位置：`plan.md:35`。

冻结 Spec 是 Markdown，主仓库测试又不能依赖独立 `.dev` 仓库；不存在一个可自动读取且独立于实现的规范数据源。若生产代码有 `_TABLE`，测试遍历 `_TABLE` 并拿 `_TABLE` 的值作 expected，则删一行时参数数也少一行、写错值时 expected 同时变错，测试仍绿。这里“不要手抄”不是优势，而是取消了独立 oracle。

可执行做法：在测试侧显式维护一份由冻结 Spec 手工转录的 14 个 case，每个 case 有稳定 id、source constructor 与完整 expected 投影；这是必要的独立重复，不应回避。另设一个独立 literal `EXPECTED_CASE_IDS`，断言 `set(CASES) == EXPECTED_CASE_IDS`，并在 production 若采用 registry 时再断言 registry keys 与这组 id 相等。每个参数断言 `category/status/message/code/param/source_*` 等所有相关字段，不只断言 category。§5.2 另用测试侧字面 status→category cases，至少含 403 billing 分支、catch-all 418/599 与边界值。不能从生产 mapping 生成 expected；若不愿手工转录，唯一替代是先把规范迁成 checked-in machine-readable authority，但这会扩大任务且不值得。

### F-12　[major] [把握：高] S3 验收不足以区分“真实透传”与“恰好重序列化成相同 JSON”，也完全没验 headers／Content-Type

位置：`plan.md:58`。

“直连 400 的 body 与状态相同”若样本是普通 JSON，错误实现可以 parse 后再 dump，甚至继续走通用 JSON writer，而测试仍可能相同；四种 inbound shape 只证明 writer selector 的输出不同，不证明 direct bypass。计划也没有一条检查语义头保留与 framing 头剔除，当前“全部丢头”的行为可以在所有现有验收下继续绿。

可执行建议：S3 用真实 ASGI 入口与 MockTransport，直连样本采用 `b"\xffraw-body"` 或带 BOM／非规范 whitespace 的 bytes，并同时带 `content-type:text/html`、`x-request-id`、`anthropic-ratelimit-*`、原写法的 `retry-after` 与应剔除的 `content-length/content-encoding/connection`。断言 body 字节、status、Content-Type 与每个保留／剔除头。翻译对照必须走 `translation_required=True` 的真实 route，断言客户端方言 envelope 与默认 code/status/header，而不是直接调用 writer。把 direct bypass 改成 writer 或忽略 route 参数的变异都应打红。

### F-13　[major] [把握：高] S4 的 union 守卫既可能漏掉缺行，也不证明 production SSE 使用了新映射

位置：`plan.md:60-67`。

只断言“Anthropic 那一列的所有值都在 SDK union 中”会在 mapping 少一个 category 时真空通过；把某一格改成非法值的变异只证明 subset 检查，不证明完整性。即使守卫完整，`stream.py` 继续走旧 `WIRE_TYPES` 或固定字符串时它也可以全绿，因为验收没有发起任何实际 SSE 请求。

可执行建议：静态部分同时断言 `set(anthropic_mapping) == set(ErrorCategory)` 与 `set(anthropic_mapping.values()) <= sdk_union`，并做两种受控变异：删除一行、改坏一个值，均必须红。行为部分从真实入口分别触发客户端截止、上游 transport tear、本侧 `BufferCapExceeded`，断言实际 Anthropic `error.type` 对应 Spec 中 TIMEOUT／NETWORK／INTERNAL 的映射；这同时证明 stream 接线与 source classification，而不只证明表内容。

### F-14　[major] [把握：高] S5 与 §7 的验收只覆盖一个直连事件，翻译 reader、Responses event 名与“同一事实”仍可完全失效

位置：`plan.md:69-78`；Spec §5.3、§7、§10.1。

现有验收可由“识别 Anthropic `event:error` 后原样吐回”这一条特判满足，即使翻译腿仍吞事件、Responses `response.failed/response.cancelled` 仍变正常终结、未知翻译错误未产生 `upstream_error` 扩展。顶层“stream.py 与 http_errors 共用 writer”只保证 IR→wire 可能共用，不能保证两个入口构造的是同一 `ErrorInfo`；source→IR 错了，共用 writer 仍会一致地写错。

可执行建议：至少增加四组生产入口断言。其一，Anthropic 直连 `event:error` 保留 event 名与未知字段；其二，Responses 直连分别保留 `response.failed` 与 `response.cancelled`，不能统一改名为 `error`；其三，Responses→Anthropic 翻译已知 code 到正确 category/status/code；其四，未知 code 走 §10.1 的 `UPSTREAM` 与结构化 `upstream_error`。每组都断言失败后没有正常 terminal。另选一个能在响应头前／后出现的同义上游失败，比较两边最终的语义投影，才能验证 §7，而不是只比较 writer 函数。

### F-15　[minor] [把握：高] “ErrorInfo（9 个字段）”按字段名实际是 10 个，容易漏掉 `source_content_type`

位置：`plan.md:32`；Spec §4.2。

Spec 表有 9 行，但 `source_bytes / source_content_type` 那一行命名了两个字段；实际字段名是 `category`、`message`、`status_code`、`code`、`param`、`headers`、`source_format`、`source_bytes`、`source_content_type`、`conversion`，共 10 个。计划只写数量不列名字，而 S0 恰好新增了 `content_type`，这种歧义会让后续实现误以为两者择一。

可执行建议：S1 直接列出 10 个字段及类型，不写“9 个字段”这个按表行计数的简称。

## 三、切片独立性逐片结论

| 切片 | 单独落地后的判定 | 证据强度与处置 |
|---|---|---|
| S0 | 可以独立。只扩充异常保真字段，不要求新消费者，现有 `body` 保留。 | **足以行动，把握高。** 并发实现不在本报告评审范围。 |
| S1 | 不可以按现计划独立。枚举扩宽令旧 `WIRE_TYPES` 缺键；14 行中有无异常来源；CountTokens 没有 cause；Conversion leaf 未定。 | **足以行动，把握高。** 先修 F-02、F-05、F-06。 |
| S2 | 技术上能编译的部分不等于完整语义切片。Anthropic refactor 有生产消费者，其余 writer 是死代码；验收矩阵还要求已推迟 carrier。 | **足以行动，把握高。** 按消费者并入 S3／S4，或把 S2+S3 设为不可拆边界。 |
| S3 | 当前 API 不能透传 bytes，且三个早期出口与 Gemini 501 不接线；如果硬接 `describe`，UnknownModel／Translator 行为已经提前发生。 | **足以行动，把握高。** 先引入统一 response factory 并列全调用点。 |
| S4 | 可以成为独立行为片，但当前验收只测孤立表，不测 stream 接线，也没防缺键。 | **足以行动，把握高。** 补完整性与真实 SSE 正样本。 |
| S5 | 核心数据通道与策略选择点未定义，不能直接实施；当前验收只覆盖 Anthropic 直连的一格。 | **足以行动，把握高。** 先补 typed failure seam。 |
| S6 | 不是一个独立语义片，部分行为已由 S3 实现，剩余两项机制不同，并且没有验收判据。 | **足以行动，把握高。** 拆成 count_tokens、200 非 JSON 与随片注释三部分。 |

S0→S2“可以一次提交或分两次”的说法因此不成立。提交边界不是绿灯决定，但仍要是自洽的语义单位；当前 S1 和 S2 单独都没有这个性质。

## 四、Spec 逐条对计划的覆盖

| Spec 条款 | 计划名义落点 | 覆盖判断 |
|---|---|---|
| §2 两轴矩阵 | S3 非流式、S5 流式、S1/S2 代理错误 | **部分。** 直连／翻译主方向有，但早期代理错误与 S5 策略 seam 未闭合。 |
| §3.1 body/status/headers/Content-Type | S0、S3 | **部分。** S0 有原料；S3 现有 API 无法发 bytes，验收漏 headers/Content-Type。 |
| §3.2 原始字节前置 | S0 | **覆盖。** |
| §3.3 直连路径上的代理自产错误过 IR | S1～S4 | **缺实际接线。** 非法 JSON、非对象、Gemini 501 绕过 `http_errors`，见 F-02、F-09。 |
| §3.4 直连流内失败原样重放 | S5 | **名义覆盖但不可实施。** 没有 raw failure carrier 与 direct selector，见 F-03。 |
| §3.5 不得正常终结 | S5 | **名义覆盖。** 需扩成所有 event 类型与两条腿的验收，见 F-14。 |
| §4.1～§4.3 IR 与 category | S1 | **部分。** 基本落点正确；Conversion leaf 与字段数未闭合。 |
| §4.4 code/param | S1、S2 | **名义覆盖。** S1 验收必须断言字段，不可只测 category。 |
| §4.5 自建 message，不用 SDK `__str__` | S1 | **名义覆盖。** `plan.md` 只以“§4”总引，实施时应把 message producer 写入 `describe` case。 |
| §5.1 本代理错误表 | S1、S6 | **部分且 Spec 自身有 blocker。** 无异常来源不可由签名表达，S3/S6边界冲突；`EndpointNotSupported` 漏于冻结表。 |
| §5.2 status→category | S1 | **名义覆盖。** 需独立 expected table、billing 分支与 catch-all 边界。 |
| §5.3 流内事件→category | S5 | **部分。** 计划没有逐项写 Anthropic known/unknown、Responses failed/cancelled 与 transport tear，验收也没覆盖。 |
| §5.4 PipelineAbort 读 cause | S1 | **覆盖。** |
| §6.1 各方言词汇 | S2、S4 | **部分。** writers 有落点；key completeness 与生产 SSE 接线未证。 |
| §6.2 status/default code/retry | S1～S3 | **部分。** status/code 可由 IR 承担；`x-should-retry:false` 没有明确生产者与验收，见 F-09。 |
| §6.3 carrier | S2 | **覆盖方向正确。** 验收矩阵必须去掉 Spec 已排除的流式格。 |
| §6.4 版本化 code 扩展 | S2 | **名义覆盖。** 不应让测试声称存在 typed consumer。 |
| §7 流式／非流式表达同一事实 | 顶层共享 writer、S3～S5 | **不足。** 共用 IR→wire 不证明 source→IR 一致，缺跨时序语义对照，见 F-14。 |
| §8 Chat Completions 注释修正 | S6 | **覆盖。** 更合理的提交位置是改动该事实的切片。 |
| §9 Gemini 501 | S2 | **未覆盖实际行为。** 只有 writer，没有 endpoint 接线，见 F-09。 |
| §10.1 未知翻译错误 | S2、S5 | **部分。** writer 分支有计划，reader 分类与翻译入口验收缺失。 |
| §10.2 推迟与登记 | 推迟项 | **未完成。** 指定的 deferred ledger 不存在，也没有创建步骤，见 F-10。 |
| §11 七项范围外登记 | 推迟项 | **未完成。** 只写“已登记”而没有 ledger／逐项落盘，见 F-10。 |

明确的“Spec 要求但没有任何切片完成”集合是：§3.3 的无异常早期错误实际接线、§9 的 Gemini 501 endpoint 接线、§10.2 的 deferred 文件建立、§11 七项逐项登记；§6.2 的 `x-should-retry:false` 虽被章节引用覆盖，却没有任何字段生产者，因此也应视为未分配工作而非已完成。

## 五、建议的最小重排

1. 保留 S0 独立。
2. 先修 Spec 的 `EndpointNotSupported` 缺口；同时在计划中固定 `ErrorInfo` 10 字段、Conversion 的叶子策略、无异常 source 的进入方式。
3. 建 IR 与 source classification 基础，但同片保证所有 `ErrorCategory` keyed tables 完整，并让 CountTokens 保留 cause；不要留下半宽枚举。
4. 把统一 `error_response`、所有 JSON 出口、各 JSON writer、Gemini 501 与 UnknownModel／Translator 行为组成一个可观察且完整的 JSON 切片；该片必须含 direct bytes/header/content-type e2e。
5. 把 OutboundFramer 的 `error(ErrorInfo)` 契约、各流式 writer、category mapping 与 stream 三个现有错误出口组成一个 SSE 词汇切片；generic stream 不直接选具体 format。
6. 单独定义并实现 stream failure typed seam，再接直连 raw replay 与翻译 reader；把两处“与撕裂不可区分”的注释随这一片修正。
7. CountTokens cause 读穿与上游 200 非 JSON 各自独立，因为入口与失败机制不同；one-shot 注释随前者之外的相应小片修正。
8. 立即创建 deferred ledger，纳入 §10.2 与 §11；这不是行为实现的尾声，而是冻结范围得以不被静默删掉的记录。

## 六、证据与未采用路线

- 使用冻结 Spec v3 作为行为 oracle，旧 `260823-spec-review-gpt.md` 的 13 条已闭合发现均未重提。F-04 是当前源码中另一个已实测可达的错误类型，独立列为 Spec 自身问题。
- 没有向真实 Copilot、Anthropic 或 OpenAI 发请求。依赖方向来自当前源码；客户端出口探针使用真实 ASGI app 与 `httpx2.MockTransport`，待测命题换上游仍成立。
- 没有采用“测试直接遍历生产表并断言生产表自己的值”这条路线，因为它没有独立 oracle；也没有建议把 `.dev` Markdown 解析成 CI 规范源，因为 `.dev` 是独立仓库且这会把普通实现任务扩成新的证明基础设施。
- 没有建议 `http_errors` 继续暴露三件套后由每个调用点自行选择 `Response`／`JSONResponse`；那会复制直连判定与 writer selector，违背计划本来想要的单一边缘所有者。
- 本报告只读源码与运行测试／探针，没有修改任何源文件、测试或用户控制文档。

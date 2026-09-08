---
report_id: context-condition-spec-review
attempt_id: context-condition-spec-review-01
status: in-review
reviewed_at_rev:
  main_head: 436dc46ecf96ac80dfe769d1002dd6cf10a5ca63
  main_target_files_sha256: 54ed50b0138d3dacda7cf99359e7224724ad717f0410ab7c31f3375acf48a193
  dev_head: 7dcadbca89095c1861d087ad094bf00540e1b351
  spec_file_sha256: 8e2c7005b2ea05d434dea105fa784eca8359a26a35eff59f494aba4814b19190
  plan_deferred_files_sha256: fe70b29e81e23f84784f5b0f2cd225add9c8ca6c77078ccaed22671994229b4d
reviewed_on: 2026-08-24
---

# `CONTEXT_WINDOW_EXCEEDED` 设计与规格独立评审

## 评审范围

本次评审对象是上述工作树快照中尚未提交的 `.dev/docs/error-envelope/spec.md` §4.2 新增字段、§5.5～§5.5.4、§6.2 新增说明、条款修订记录，以及它们在 `src/app/errors.py`、`src/app/pipeline/error_classify.py`、`src/app/pipeline/delivery/formats/errors.py` 与对应测试中的 IR 落点。`docs/.human-controlled/config.example.yaml` 与 `docs/.human-controlled/message-translation.md` 的未提交改动属于用户自己的改动，不作为被评对象；后者只作为最高权威判据读取。其余 Docker、HTTP/2 实验和无关 `.dev` 改动不在范围内。

## 总体 verdict

**needs-fix**。主场景「Anthropic Messages 客户端经 OpenAI Responses 上游收到 400 context-window 错误」已经走通，`UpstreamCondition` 作为独立于粗粒度 `ErrorCategory` 的语义维度也是正确方向；但当前 Spec 与实现仍有 4 条 major，其中一条是识别谓词与 Spec 双向不一致，另一条是 IR 在 source reader 阶段提前固化 Anthropic 文案，导致条件语义和方言呈现分裂。修复这些问题前，不应把本切片作为规格与实现已一致的候选提交。

**blocker 数：0。**

## 发现汇总

| severity | 数量 |
|---|---:|
| blocker | 0 |
| major | 4 |
| minor | 3 |
| 合计 | 7 |

## Major findings

### CCSR-01　`condition` 的抽象方向正确，但 `message` 在 source reader 中提前渲染，IR 同时保存语义与一份可矛盾的 Anthropic 文案

- `finding_id`：`context-condition-spec-review-01`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:230-244`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-translation.md:8`；`/home/xp/src/ghc-api-proxy-py/src/app/errors.py:57-81`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/error_classify.py:97-117`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/error_classify.py:120-186`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/errors.py:27-34`
- 原文：Spec 写道，`“message” 是“方言中立”的，即 OpenAI 与 Gemini 信封上也写这句 Anthropic 措辞`，理由是 `把“说什么”搬进只负责“怎么拼”的 writer` 不合适；最高权威则要求翻译路径“总是建立消息格式与内部 IR 的映射关系”。实现中 `_UpstreamRead` 暂存 `counts`，`_condition_message()` 在分类器里立刻生成 `prompt is too long: …`，进入 `ErrorInfo` 后不再保留结构化计数；writer 只按方言替换 `code`，原样采用 `info.message`。
- 证据：只读探针构造了 `condition=CONTEXT_WINDOW_EXCEEDED`、`message="upstream's original wording"` 的 `ErrorInfo`。Anthropic 输出成为 `code="model_max_prompt_tokens_exceeded"` 加原来的无关 message，OpenAI 输出成为 `code="context_length_exceeded"` 加同一无关 message。也就是说，`condition` 与 `message` 的一致性并非 IR 或 renderer 的结构性质，只是当前 `_from_upstream()` 这一处调用约定。反过来，正常分类路径又把面向 Claude Code 的精确兼容短语固化进所谓方言中立 IR，并有意送到 OpenAI、Gemini 客户端。
- 影响：这违反“source format → IR → target format”的分层目标，并把一个机器会解析的客户端兼容 token 伪装成人类中立文案。新增 condition、增加另一种目标方言或从另一个 reader 构造 `ErrorInfo` 时，`message` 与 `code` 可以分别正确而组合错误；当前流内 reader 已经展示了这种旁路，见 CCSR-03。
- 建议：保留 `UpstreamCondition`，不要把它升级成 `ErrorCategory`；同时把上游实测到的 `current` / `limit` 作为 condition 的结构化可选细节留在 IR。由 `app.errors` 这类领域层提供 `(condition, details, target_format) -> rendered message + code` 的单一呈现函数或记录，再让 envelope writer 只负责结构拼装。这样“说什么”没有塞进 structural writer，Anthropic 专用短语也不污染 source reader 或其它方言。
- 结论强度：**强到足以据此修改设计。** 判据来自用户亲笔的 IR 规则，现状来自直接源码，矛盾状态由只读运行探针复现；不依赖测试绿灯。

### CCSR-02　分类器没有实现 Spec §5.5.1 的第三条判据，并额外接受了 Spec 未授权的宽判据

- `finding_id`：`context-condition-spec-review-02`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/src/app/errors.py:221-264`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:218-228`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/test_error_classify.py:329-383`；`/home/xp/src/ghc-api-proxy-py/tests/unit/tokenization/test_tokenization_limits.py:3-18`
- 原文：Spec 第三条要求 `error.message` **匹配** `prompt is too long: N tokens > M maximum` 或 `prompt token count of N exceeds the limit of M`。实现却让 `is_context_window_exceeded()` 只检查 `error.code`，或检查 `_CONTEXT_LIMIT_PHRASES = ("exceeds the context window", "prompt is too long")`；它既没有调用 `_CONTEXT_LIMIT_COUNT_PATTERNS`，又把第二个完整数值模式放宽成任意 `prompt is too long` 子串。
- 证据：只读生产代码探针得到两端反例。`{"error":{"message":"prompt token count of 150000 exceeds the limit of 100000"}}` 按 Spec 第三条应命中，实际 `condition is None`；`{"error":{"message":"prompt is too long"}}` 不满足 Spec 的任一完整模式，实际却被标为 `context_window_exceeded` 并改写。`tests/unit/tokenization/test_tokenization_limits.py:3-18` 只证明共用计数 helper 能解析两个模式，没有证明 classifier 使用了它；`tests/unit/pipeline/test_error_classify.py:353-373` 的 Anthropic 样本同时携带强 `code`、完整数值 message 与宽短语，无法隔离第三条判据。
- 影响：这是双向合同偏差。第一种情况下 Spec 承诺识别却不识别；第二种情况下代理会把未经 Spec 或样本支持的上游错误改写成 context overflow，可能诱导客户端压缩并重发。已知 M2“退化成只看 code”会变红，只证明 Responses 片段分支存在，不能覆盖这里的反向退化。
- 建议：让 condition 判定显式组合三个 Spec 谓词，计数模式应参与判定而不只参与提数；如果确实要把 `prompt is too long` 本身升级成独立充分条件，应先用证据修订 Spec，而不是在代码中暗自放宽。测试为 `code-only`、`exceeds-context-window-only`、两个 `count-pattern-only` 各放一个互不共享信号的正例，并补一个只有裸短语的负例或经裁定后的正例。
- 结论强度：**已确认，强到足以据此修复。** 两个反例直接运行当前生产入口并得到与 Spec 相反的结果。

### CCSR-03　§5.5 没有限定为建流前 HTTP 错误，但流内两个 reader 和 OpenAI Responses framer 都绕过 `condition`

- `finding_id`：`context-condition-spec-review-03`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py:449-469`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py:358-373`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/anthropic_messages.py:318-340`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:208-228`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:354-356`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/deferred.md:71-89`
- 原文：Spec 写道 `condition` 命中时“只改变 `message` 与 `code`”，且 §7 要求流式与非流式表达同一语义事实，没有把 §5.5 限定为建流前的非 2xx HTTP body。实际两个 assembler 遇到 `event: error` / `response.failed` 时直接构造 `ErrorInfo`，只填 `category`、`message`、`code`，不调用 condition reader；`OpenAIResponsesFramer.error()` 又直接写 `"code": info.code or None`，不走本切片新增的 `condition_code()`。
- 证据：客户端一手报告 `/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/reports/260824-claude-code-context-limit-detection.md:120-138` 明确列出 SSE `event: error` 的错误对象路径，并证明 `prompt is too long` 在该路径同样生效；同一报告也把“本项目的上下文超限会在建流前返回 400”标成结构推断、仅倾向、未做运行时验证。现有 48 例都属于建流前 400，足以支持当前主场景，却不足以把流内可能性写成不存在。当前 `deferred.md` 登记了 E-10 与 E-11，但没有登记这条范围差异。
- 影响：Spec 当前表述覆盖所有翻译路径，而实现只覆盖 `_from_upstream()` 的 HTTP 错误。若任何 upstream condition 以流内事件出现，Anthropic→OpenAI 或 Responses→Anthropic 都不会获得相同的 condition 语义；OpenAI 流式 carrier 即使收到一个带 condition 的 `ErrorInfo`，也仍会输出 category/default code。新增闭集成员会扩大这处遗漏。
- 建议：二选一并在 Spec 当场说清。若本切片只承诺 48 例支持的建流前 400，就把 §5.5 的定义域明确限定为 HTTP error body，并把流内 condition 记为带重开条件的未决项；若 §7 的全路径语义保持不变，则让两个 stream reader 复用同一 condition classifier，并让每个 framer 复用同一 condition presentation。
- 结论强度：**实现缺口已确认；真实上游是否会以流内事件报告本 condition 仍未决。** 即使后一事实为假，当前也必须收窄 Spec；若为真，则需补实现。

### CCSR-04　新增按方言 `code` 表没有被手工转录成独立 oracle，测试只验证键集合

- `finding_id`：`context-condition-spec-review-04`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/test_error_classify.py:405-429`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:240-244`；`/home/xp/src/ghc-api-proxy-py/tests/int/test_error_envelope.py:635-650`；`/home/xp/src/ghc-api-proxy-py/src/app/errors.py:182-199`；`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:13`
- 原文：测试名声称 `test_every_dialect_that_has_a_code_spells_every_condition`，实现却只断言 `set(table) == set(UpstreamCondition)`；另一个测试只断言 `CONDITION_CODES_BY_FORMAT` 的 format 键集合。Spec 的实际值 `Anthropic -> model_max_prompt_tokens_exceeded`、`OpenAI -> context_length_exceeded` 没有被这一手工转录件逐值写下。
- 证据：在整个 `/home/xp/src/ghc-api-proxy-py/tests` 搜索字面量 `context_length_exceeded` 返回零命中；集成测试只断言 Anthropic 输出的 `model_max_prompt_tokens_exceeded`。因此把 `OPENAI_CONDITION_CODES` 的值误写为任意非空字符串、或让 OpenAI writer 使用 Anthropic 拼写，现有这些断言仍会通过。项目规则明确要求 Spec 表的手工转录在同一改动同步，且不能以生产表派生期望值。
- 影响：闭集新增成员时的“缺行”护栏存在，但当前行的“错值”与按方言串线没有护栏；这是公共 wire contract 的静默回归面。
- 建议：增加以字面量手工列出的 `(wire_format, condition, expected_code_or_absence)` 用例，实际调用 writer/framer，而不从生产映射取 expected；同时覆盖 Gemini 无字符串 code 的负向行为。CCSR-02 所列三条识别谓词也应各自成为不共享信号的转录用例。
- 结论强度：**强到足以据此补测试。** 这是对测试源文本与全测试树精确字面量搜索的直接结论；已知六个变异全部打红不包含这个 OpenAI 值变异。

## Minor findings

### CCSR-05　§5.5.3 把“Anthropic 信封必须嵌套”误写成 context-limit matcher 的必要条件

- `finding_id`：`context-condition-spec-review-05`
- `severity`：`minor`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:262`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/plan.md:151-155`；`/home/xp/src/ghc-api-proxy-py/tests/int/test_error_envelope.py:635-650`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/reports/260824-cc-context-limit-predicate-probe.mjs:5-12`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/reports/260824-cc-context-limit-predicate-probe.mjs:149-166`
- 原文：Spec 写道“客户端的 `makeMessage` 只有在顶层没有 `message` 字段时才把整串 body 序列化进去匹配，扁平信封会让它只取顶层 `message`，本条随之失效”；集成测试的 docstring 更明确声称“a flattened envelope would carry the right words and still fail to be recognised”。
- 证据：同目录现成探针 case I 正是 `400 + 顶层扁平 message`，输出为 `Eci=true`、`jXr=true`、`YvE="Prompt is too long"`。`makeMessage` 取顶层 message 并不会丢掉其中的 `prompt is too long`；只有像 §6.3 的 overloaded 判断那样，关键字位于被丢弃的其它字段时，嵌套才是客户端匹配的必要条件。
- 影响：当前嵌套输出仍然是合法且正确的 Anthropic 信封，所以没有造成产品行为错误；错误的是 §5.5 的因果解释，以及 M4“信封压扁”被描述成验证 context matcher。它实际只验证协议结构，不能证明此处声称的识别机制。
- 建议：保留 §6.3 的嵌套信封规范与结构测试，但从 §5.5.3、plan 和该测试 docstring 中删除“否则 context matcher 看不到”的理由；把这条测试准确命名为 Anthropic carrier 形状测试。
- 结论强度：**已确认。** 既有逐字探针已运行，case I 直接反证原句。

### CCSR-06　两个活代码／测试注释仍把 Spec 称为 frozen，违反本次评审的项目级权威规则

- `finding_id`：`context-condition-spec-review-06`
- `severity`：`minor`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/tests/int/test_error_envelope.py:1-3`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/src/app/server/http_errors.py:1-3`；`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:8-13`
- 原文：测试模块写道 ``.dev/docs/error-envelope/spec.md` is the frozen form of it.`；HTTP error 模块写道 `rewritten on 2026-08-23, when .dev/docs/error-envelope/spec.md froze.`。项目规则则明确要求 Spec 是活文档、永不冻结，也不得引用“the frozen spec”。
- 影响：这不改变运行行为，但会让维护者把已经新增 §5.5 的同一份 Spec 误读为不可修订的历史快照，正好逆转本轮规则要消除的工作流错误。两个文件都处于当前错误信封路径，其中测试文件还是本切片正在修改的转录件。
- 建议：改成“current normative living Spec”，历史日期若仍有价值则只描述“当时首次成为实施判据”，不要再使用 `froze` / `frozen form`。
- 结论强度：**已确认。** 精确搜索当前 `src`、`tests` 与 `.dev/docs/error-envelope` 后，相关活代码／测试命中就是上述两处；报告原件中的历史措辞不在修改建议内。

### CCSR-07　代码注释把第三方录制也统称为 first-hand，证据层级高估

- `finding_id`：`context-condition-spec-review-07`
- `severity`：`minor`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/src/app/errors.py:221-227`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260821-context-limit-400-examples.md:145-157`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:220-224`
- 原文：注释写道 `Every entry is from a first-hand recording — 48 samples across two upstream legs plus one third-party capture`，但依据报告把 `/chat/completions` 的第三种形态明确标为“旁证，不是本机录制”和“第三方录制的真实响应”。
- 影响：三个模式本身仍有真实捕获来源，采用它们不因此失效；问题只在证据强度被统一抬成 first-hand。以后若用这句注释决定删改判据，会看不出 48 个本机样本与 1 个第三方历史样本的适用面不同。
- 建议：改为“48 first-hand local samples across two active legs, plus one third-party recorded `/chat/completions` sample”。Spec 的条款修订记录对 48 例与客户端报告的引用、触发和方向本身准确，无需因这条注释问题改写。
- 结论强度：**已确认。** 两份文档对同一第三种样本的证据层级有逐字冲突。

## 重点判断的结论

### §10.1 与“读懂后改写、不带原文”

两条规范**自洽**。§10.1 只为无法映射进 IR 的错误保留 `upstream_error`；`CONTEXT_WINDOW_EXCEEDED` 已是已知 IR 概念，因此不应再走该扩展。`ErrorInfo.source_bytes` 仍把原始字节带到 presentation 边界，直连路径仍逐字透传；翻译 writer 在已理解时不输出原文，是 presentation 端的有意裁剪。对当前两个已观测形态，Responses 原句没有额外数值，Anthropic 原句中的两个数又会被保留到新句子里，因此这项客户端可见损失值得接受。规范性效果由 §5.5.2 与 §10.1 合读已经明确；若要提升可读性，可补一句“已识别时 source_bytes 不进入客户端信封”，但我不把它列为独立缺陷。

### `condition` 是否是正确抽象层

是，**但其呈现方式需按 CCSR-01 重构**。新增 `ErrorCategory` 会把一个细粒度语义条件混进负责 status、SDK exception class 与通用 retry 的粗粒度轴，并迫使每张 category 表新增一行；只改 `code` 又无法触发已证实只读 message 的 Claude Code。正确的分层是 `category` 表达通用 HTTP/SDK 处置，`condition` 表达更细的语义与专用恢复动作。当前文档中“category 答客户端该做什么动作”说得过满，因为 §5.5.3 恰好证明 condition 也会改变客户端动作；应收窄成“category 决定通用 status/type/retry 处置”。

### `message` 方言中立

不成立，见 CCSR-01。这里的 `prompt is too long` 不是普通中立英文，而是 Claude Code 的机器判据；把它发给所有方言是 target-specific presentation 泄漏进 IR。更好的做法不是让 structural writer 自己决定语义，而是在 `app.errors` 的领域层集中渲染 condition 的 `{message, code}`，writer 仍只拼信封。

### 禁止合成数字

这条禁令恰当且足够硬。Spec 使用“不得”“禁令，不是暂缓”，实现只接受上游原句中满足 `current > limit > 0` 的两个数，测试同时钉住有数值和无任何数字字符两条路径。模型目录的上限与本地估算的当前值不是同一观测，不能拼成客户端会当作实测的数据。

### 转录件与其它复述

转录件有缺口，见 CCSR-02、CCSR-04；其它活代码注释有 stale freeze 说法，见 CCSR-06；计划和集成测试又复制了错误的“扁平则 matcher 失败”理由，见 CCSR-05。报告原件是点时记录，不要求追改。

### 条款修订记录

新增行对用户触发、48 例上游记录、三版本客户端判据及行为后果的指向准确；`condition` 与按方言 `code` 的概述也吻合当前变更。`“IR 只按状态码分类，做的是转发而不是翻译”` 是修辞性压缩：旧路径已经建立 `ErrorInfo` 并重写信封，只是没有理解 condition、message 仍在转述上游。建议未来改成“IR 只做到 category，未做到 condition-level interpretation”，但不单独升级为 finding。真正的证据层级错误在 CCSR-07。

### 静默削减与 deferred

未发现本切片已经明确发现却完全未登记的同类项。`deferred.md` E-10 正确登记了 `input length and max_tokens exceed context limit` 这一不同条件，并写明需要真实上游样本；E-11 登记了完成日志与客户端 wire 文案分叉。CCSR-03 是本次评审新发现的流内定义域缺口，处置时应直接修 Spec 或登记为真正未决，不能保持当前无声状态。

## 考虑过但否决的路线

1. **把 `CONTEXT_WINDOW_EXCEEDED` 新增为 `ErrorCategory`——否决。** 它不需要新的 status/type/通用 retry 行；这么做会混淆粗分类与语义子条件，并扩大所有 category-keyed 表。保留独立闭集更合适。
2. **只改 `code`——否决。** 三版本 Claude Code 的判据不读取 `error.code`，不能触发反应式压缩。
3. **把方言 message 逻辑直接堆进每个 envelope writer——否决。** 这会复制“说什么”；CCSR-01 建议的是领域层单一 renderer，writer 只消费其结果并拼结构。
4. **所有已识别错误仍附 `upstream_error`——否决。** 这违背 §10.1 已选择的边界，重复两套词汇；保留 IR 内 `source_bytes`、只在读不动时向客户端附原文即可。
5. **从模型目录与本地 estimator 合成数字——否决。** 两个来源不是一次上游测量，客户端会把它们显示成实测值。
6. **把 status 改成 413，或伪造 `capability_rejected: prompt_too_long`——否决。** 前者与 413 的请求字节语义冲突，后者是新版 Claude Code 网关内部协议，且两者都不如三版本共同的 `prompt is too long`。
7. **把“必须嵌套”继续作为 context matcher 的必要条件——否决。** case I 已直接证伪；嵌套仍因 Anthropic carrier 合法性和 overloaded SSE 判据而保留，但不能借用错误因果。

## 搜索面与执行记录

- 判据来源：逐行读取用户亲笔 `docs/.human-controlled/message-translation.md`、`message-format-reshape.md`，项目 `.claude/rules/00-development-workflow.md`，48 例上游报告与三版本 Claude Code 判据报告；没有重新请求真实上游。
- 被检对象：读取当前 Spec 全文、主仓全部目标 diff、`ErrorInfo`／classifier／JSON writers、Anthropic 与 OpenAI Responses stream readers/writers、unit 与 integration 转录件、plan 和 deferred；排除用户自己的两个 human-controlled 文件改动及所有无关工作树改动。
- 横向搜索：对 `UpstreamCondition`、两个 code、两个关键短语、`upstream_error` 与 frozen-Spec 复述做了 `rg`；项目没有 `.codegraph/`，因此按项目规则使用文件读取与 `rg`。
- 执行：`uv run pytest tests/unit/pipeline/test_error_classify.py tests/int/test_error_envelope.py --quiet` 得到 `106 passed in 4.53s`。这只证明当前测试集合在该快照通过，不作为设计正确证据。
- 分辨力：沿用调用方提供的六个已知变异结论，只据此判断这些具体机制已有防线；CCSR-02、CCSR-04 分别指出六个变异没有覆盖的谓词反向偏差和 OpenAI 映射错值。
- 只读探针：运行现成 Claude Code predicate probe，case I 证伪嵌套必要性；另直接调用生产 classifier／writer，复现 CCSR-01 与 CCSR-02。未修改任何被评文件。
- 未覆盖：没有对真实 Copilot 发请求；没有执行全仓 Ruff、Pyright 或全量测试；没有把 OpenAI `context_length_exceeded` 提升为官方合同。当前仓内多个外部实现支持它是生态惯例，但官方 live search 本次不可用；Spec 只称“通行拼写”而非官方值，因此不据此新增 finding。

## 整体判定

`needs-fix`。没有 blocker；4 条 major 需要在进入提交前闭合。主路径行为已经可运行，问题集中在 Spec 与 classifier 谓词不一致、IR/presentation 分层、流式定义域，以及手工转录不完整。

## 我最没把握的三个判断

1. **CCSR-03 的 severity。** 流内漏接线是确定事实，但现有 48 例全是建流前 400；若调用方明确把 §5.5 定义域收窄为这类 HTTP 错误，影响会从 major 降为已登记的未来范围。当前 Spec 没有该限定，所以本报告按 major。
2. **CCSR-01 是否必须立刻引入结构化 condition details。** “Anthropic phrase 泄漏到其它方言”和可构造矛盾 IR 是确定的；具体载体可以是字段、typed payload 或一个独立 rendering record，本报告只裁定不能继续在 source classifier 中丢掉 counts 并固化 target 文案。
3. **CCSR-07 是否值得独立成 minor。** 它不改变模式本身的可信度，但本项目反复依赖证据层级决定可否外推；因此保留为独立精度问题，而不是降成 nit。

## 执行本契约时遇到的摩擦

- 共享工作树在评审期间出现一次目标 diff hash 变化；我重新读取了全部目标源文件与测试，并以文首最终 hash 绑定报告。
- 官方 OpenAI live search 本次不可用；本报告没有把该失败转化成对 `context_length_exceeded` 的否定结论，也没有依赖该外部命题判定 major。

## 交付声明

delivery_complete: true
completed_at: 2026-08-24
finding_total: 7
blocker: 0
major: 4
minor: 3
nit: 0

---
report_id: context-condition-code-review
attempt_id: context-condition-code-review-01
status: in-review
reviewed_at_rev:
  main_head: 436dc46ecf96ac80dfe769d1002dd6cf10a5ca63
  worktree: uncommitted (8 modified files, `git diff` md5 = 1266dbd9b3ceacd9c9e78821cb86e5b9)
reviewed_on: 2026-08-24
---

# `UpstreamCondition` 实现与判据独立评审

## 评审范围

被评对象是 `436dc46` 工作树上**未提交**的实现侧改动：`src/app/errors.py`、`src/app/pipeline/error_classify.py`、`src/app/pipeline/delivery/formats/errors.py`、`src/app/tokenization/limits.py`，以及 `tests/unit/pipeline/test_error_classify.py` 与 `tests/int/test_error_envelope.py` 末尾新增的两批测试。

**判据来源**（在读被检对象之前读完）：`.dev/docs/error-envelope/spec.md` §3、§4.2、§5.5～§5.5.4、§6.1～§6.4、§10.1；48 例一手上游记录 `.dev/docs/upstream/retry-and-continuation/reports/260821-context-limit-400-examples.md`；客户端判据 `.dev/docs/error-envelope/reports/260824-claude-code-context-limit-detection.md`；项目规则 `.claude/rules/00-development-workflow.md`。

**不在范围内**：`docs/.human-controlled/` 的两处改动（用户自己的改动，只作为最高权威判据读）；`.dev/` 里 `spec.md` / `plan.md` / `deferred.md` 的文本本身（只作判据与对账，不作被评对象）；Docker、`exp/260820-h2-stream-cap/`、`.claude/worktrees/` 等无关未跟踪文件。

**与同目录 `260824-context-condition-spec-review.md` 的关系**：我在形成全部发现之后才读它，用于对账。两份在两条发现上独立收敛（下文逐条标注），其余不重合。我没有采信它的任何未复核结论。

## 总体 verdict

**needs-fix**。主场景（anthropic-messages 入、openai-responses 上游、400 上下文超限）确实走通了，且我实测确认了三处最容易踩空的地方都没踩：`text/plain` 装 JSON、body 末尾 `\n`、`error.code` 零区分力。问题集中在**判据本身与 Spec §5.5.1 双向不一致**，以及**这条判据最危险的两处行为零测试覆盖**——我用变异实测证明了后者，且用控制变异证明了这批测试整体确有分辨力。

**blocker 数：0。** major 3，minor 7，nit 2。

## 我实际跑过的验证

| 手段 | 结果 |
|---|---|
| `uv run pytest tests -q` | 1733 passed, 2 skipped（全量基线） |
| `uv run ruff check src tests` / `uv run pyright src tests` | 全通过，0 errors |
| 叶子约束实测：子进程 `import app.errors` 后列 `sys.modules` | `['app.errors']`——**叶子成立** |
| 反向：`import app.tokenization.limits` | 拉起 14 个 `app.*` 模块，含 `app.errors`；`app.errors` 不 import 任何 `app.*`，**无环** |
| AST 扫描 `src` + `tests` 全部 `ErrorInfo(` 调用 | 零处位置参数——新字段插在 `status_code` 与 `code` 之间**不构成回归** |
| `parse_prompt_limit_error` 差分（12 条语料，含反向数字、大小写、非 JSON、`&gt;`） | 与改动前实现**逐条相同**，无差异 |
| 六处变异之外的新变异 5 条 + 控制 1 条 | 见下表 |

变异实测（每条跑 `tests/unit/pipeline/test_error_classify.py` + `tests/int/test_error_envelope.py` + `tests/unit/pipeline/delivery` + `tests/unit/tokenization`，共 302 条；每条跑完从 `/tmp/review-snapshot-260824/` 的快照还原并逐字节比对 `git diff`，全部 `RESTORED-IDENTICAL: True`）：

| 变异 | 内容 | 结果 |
|---|---|---|
| M18（**控制**） | 删掉 `"exceeds the context window"` | **7 红** —— 证明这批测试确有分辨力，下面的绿不是探针没跑起来 |
| M7 | 删掉 `_CONTEXT_LIMIT_PHRASES` 里的裸片段 `"prompt is too long"` | **302 全绿** |
| M8 | 给 condition 加状态码门 `read.condition if status == 400 else None` | **302 全绿** |
| M15 | 把 `OPENAI_CONDITION_CODES` 的值改成 `"wrong_spelling_entirely"` | **302 全绿** |
| M17 | 让 `_read_upstream_error` 完全不读 `error.code`（`code = ""`） | **302 全绿** |
| M9 | 删掉 `_code()` 的 `or info.code` 回落 | **302 全绿** |

## 发现

### F-01（major）识别判据与 Spec §5.5.1 双向不一致：宽了一条、丢了一条

**主位置**：`src/app/errors.py:232-236`（`_CONTEXT_LIMIT_PHRASES`）、`src/app/errors.py:257-265`（`is_context_window_exceeded`）。
**相关位置**：`src/app/errors.py:224-229`（`_CONTEXT_LIMIT_COUNT_PATTERNS`，判定时未被调用）、`src/app/pipeline/error_classify.py:162-166`。

原文：

```python
_CONTEXT_LIMIT_PHRASES = (
    "exceeds the context window",
    "prompt is too long",
)
...
def is_context_window_exceeded(*, message: str, code: str) -> bool:
    if code in _CONTEXT_LIMIT_CODES:
        return True
    lowered = message.lower()
    return any(phrase in lowered for phrase in _CONTEXT_LIMIT_PHRASES)
```

Spec §5.5.1 列的是三条判据：①`error.code == "model_max_prompt_tokens_exceeded"`；②`error.message` 含 `exceeds the context window`；③`error.message` **匹配** `prompt is too long: N tokens > M maximum` 或 `prompt token count of N exceeds the limit of M`，「即 `app/tokenization/limits.py` 已有的两条正则。它们同时给出数字」。

实现对第 ③ 条做了两件 Spec 没有写的事：

**(a) 放宽**：把「`prompt is too long: N tokens > M maximum`」放宽成裸子串 `prompt is too long`，任何数字要求都没有了。
**(b) 丢失**：`prompt token count of N exceeds the limit of M` 这条措辞**完全退出了判定**——`_CONTEXT_LIMIT_COUNT_PATTERNS` 只被 `prompt_limit_counts()` 用来提数，`is_context_window_exceeded()` 一次也没调用它。

实测（只读探针，喂生产函数）：

```
True   None                 responses leg recorded
True   (1051542, 1000000)   anthropic leg recorded
True   (13613, 12288)       chat-completions recorded (vscode)
False  (13613, 12288)       chat-completions wording, code absent      <-- (b)
False  None                 unrelated 400 same leg
True   None                 'messages.0.content.0.text: the value "my prompt is too long, sorry" is not allowed'   <-- (a)
True   None                 'Internal server error while evaluating whether the prompt is too long'                 <-- (a)
```

第 4 行是最干净的一条：**同一个模块里，`prompt_limit_counts` 已经从这句话里读出了 `(13613, 12288)` 这一对合法的超限数字，而 `is_context_window_exceeded` 对同一句话说「不是上下文超限」。** 两个函数隔着 15 行，判据不一致。这不需要任何关于上游的假设就成立。

关于 (a) 的假阳性：上面后两行的 body 是**我构造的**，不是录制的，我不把它们当作「上游确实会这么发」的证据。但机制是实测的，且**上游确实会把请求里的内容回显进 `error.message`** 是一手记录里已有的事实——48 例报告 §3.1／§3.2 的对照组里，`Tool 'search.web' not found in provided tools`（回显工具名）、`Invalid 'input[1].id': 'call_jCWUMZ57P3JSaKR5wZBhrO8Z'`（回显 id）都是回显。所以「上游把请求派生的字符串放进 error.message」是**已观测**的，只有「那串字符恰好含 `prompt is too long`」未观测。命中的代价不是文案问题：客户端会压缩历史并重发（`reactive_compact_retry`），上游真正的错误话被整句替换，用户看到的是「Context limit reached」而不是真实原因。

按项目规则 `.claude/rules/00-development-workflow.md`「Never bypass the Spec」的两半：(a) 是实现先于 Spec 改变了可观察行为，(b) 是 Spec 的一条判据在实现里悄悄消失。**§5.5.1 是我方从实测推导出的判据表，不是用户裁决**，按 Spec 抬头的规则可由评审共识做条款级修订——所以「先修订 Spec 再改代码」这条路是开着的，不需要等用户裁。

**建议**（取舍交调用方）：把判定改成显式三选一 `code 命中 or 片段命中 or prompt_limit_counts(message) is not None`，并同步修订 §5.5.1 说明裸片段是否升格为独立充分判据。若决定保留裸片段，Spec 要写下它的假阳性面。

> 与同目录 `260824-context-condition-spec-review.md` 的 CCSR-02 独立收敛。我的两条补充是：第 4 行那个「同模块自相矛盾」的反例，以及下面 F-02 的变异测量。

### F-02（major）这条判据最危险的两处行为，测试零覆盖

**主位置**：`tests/unit/pipeline/test_error_classify.py:353-374`（parametrize 块 + `test_an_upstream_context_overflow_is_recognised_on_every_leg_that_reports_one`，`def` 在 :361）。
**相关位置**：`tests/int/test_error_envelope.py:615-633`（`def` 在 :618）。

该测试的 docstring 写着「Three wordings, one condition —— and no two of the three share a signal」。**这句话不成立**：三条样本里，Anthropic 腿那条同时带强 `code`、完整数值 message 与裸片段，三个信号叠在一条样本上。实测后果：

- **M17 全绿**——把 `error.code` 的读取整个删掉（`code = ""`），302 条测试没有一条变红。Spec §5.5.1 称之为「强判据」的第 ① 条，**没有任何测试单独钉住它**。
- **M7 全绿**——把裸片段删掉，同样没有一条变红。也就是说 F-01(a) 那条 Spec 未授权的放宽，**是这批测试完全看不见的**。
- 两者互相遮蔽：删掉任一条，另一条替它接住 Anthropic 腿的样本。

第三处：**M8 全绿**——给 condition 加一个 `status == 400` 的门。Spec §5.5.1 末句「判据只读上游 body，**不由状态码限定**」是一条明确的规范条款，而所有样本都是 400，所以这条条款没有任何测试。

控制变异 M18（删掉 `exceeds the context window`）**7 红**，证明这批测试整体是有分辨力的——上面三个绿是覆盖缺口，不是探针失效。

**建议**：每条 Spec 判据各配一条**只带该信号**的正例（`code` only／`exceeds the context window` only／两条计数正则 only），加一条只有裸片段的用例（按 F-01 裁决结果决定它是正例还是负例），再加一条非 400 状态的正例钉住「不受状态码限定」。

### F-03（major）新表没有对 `WireFormat` 求全，而它依赖的那条「已有守卫」并不存在

**主位置**：`tests/unit/pipeline/test_error_classify.py:419-429`（`test_the_dialects_with_a_condition_code_are_exactly_those_with_a_code_field`）。
**相关位置**：`src/app/errors.py:195-200`（`CONDITION_CODES_BY_FORMAT`）、`src/app/pipeline/delivery/formats/errors.py:116` 与 `:121-123`。

新守卫钉的是**字面量集合**：

```python
assert set(CONDITION_CODES_BY_FORMAT) == {
    "anthropic-messages", "openai-chat-completions", "openai-responses", "openai-embeddings",
}
```

而同文件里既有的同类守卫 `test_every_table_keyed_on_the_category_covers_all_of_it`（:290-297）钉的是 `set(table) == set(ErrorCategory)`，它的 docstring 明写理由：「adding a `WireFormat` member left `FORMAT_ENDPOINTS` a member short, and the gap surfaced as a 502」。**新表用的是弱一档的写法**：给 `WireFormat` 加一个成员并给它接上 `_openai` writer，这条断言仍然绿，而那个方言会静默失去条件拼写、回落成类别默认。这正是项目记忆里「枚举加成员会给每张以它为键的表造缺项」的同一形状，第二次发生在同一组表上。

更要命的是它所依赖的前提。`write_error` 的 docstring（`errors.py:116`）写着：

> That fallback is unreachable today: `_WRITERS` covers every `WireFormat` member, **and a test asserts it does**.

`formats_with_writers()` 的 docstring（:122）写着：

> Read by the test that pins this against `WireFormat`.

**这两条都不成立。** `rg -F 'formats_with_writers' src tests` 只有定义处一行，**零调用者**；`rg -F '_WRITERS' src tests` 只在 `errors.py` 内部；全仓没有任何一处把 `_WRITERS` 或 `ERROR_TYPES_BY_FORMAT` 对 `WireFormat` 求全。同一文件另一处同形：`src/app/errors.py:8` 说「Deliberately a leaf: … **and a test asserts it**」，而 `tests/unit/test_module_boundaries.py` 里 `reachable_from` 的三个调用点是 `translation_driver.content` 与 `pipeline.exceptions`，**没有 `app.errors`**。叶子性质我实测成立（见上表），但守卫不存在。

这两条虚假声明本身在 HEAD 里就有（不是本次引入），但本次改动**新增了一张同键的表并把「兜底不可达」当作论证前提**，所以它们从这一刻起是承重的。

**建议**：补一条 `set(CONDITION_CODES_BY_FORMAT) | {"gemini-generate-content"} == set(WireFormat)` 形状的断言（或等价的、以 `WireFormat` 为真源的写法），并把 `_WRITERS` 与 `app.errors` 叶子这两条守卫真的建起来，或把 docstring 里「a test asserts it」改成事实。

### F-04（minor）IR 拿到了结构化数字却没有携带它

`src/app/pipeline/error_classify.py:134`（`_UpstreamRead.counts`）、`:173`、`:177-187`（`_condition_message`）。

数字在 reader 阶段被解析出来，句子在 reader 阶段就被拼死，`ErrorInfo` 上只有 `condition`、没有 counts。于是任何下游（另一种方言的 writer、可观测性面、history）都无法再问「上游说的是多少 token」，只能对一句已经成型的英文做二次正则。`richest-context-flow` 的反面。

Spec §5.5.2 确实明知而为地裁定了「`message` 方言中立、由本代理构造」，所以**「句子是 Anthropic 措辞」这一条我不报为缺陷**；我报的只是更窄的一条：**已经解析出来的结构化数字不该在 IR 边界被丢掉**。加一个 `ErrorInfo.condition_counts: tuple[int, int] | None` 是低成本的。

> 同目录 CCSR-01 提出了更强的一条（message 应当在 writer 侧按方言渲染，理由是用户亲笔的「总是建立消息格式与内部 IR 的映射关系」）。**我既不采纳也不驳回**：Spec §5.5.2 已经把这个取舍连同理由写下来了，而我读用户那句话不足以直接推翻它——那句讲的是消息格式与 IR 的映射关系，我不确定它是否覆盖「错误 message 的措辞选择」。低置信，交调用方裁。

### F-05（minor）`_gemini` 的新参数未使用；`or info.code` 回落今天不可达

`src/app/pipeline/delivery/formats/errors.py:89`（`def _gemini(info: ErrorInfo, wire_format: str)`）、`:28-35`（`_code`）。

`_gemini` 的函数体（:90-99）**从不调用 `_code`**——它的 `code` 是 `info.status_code`。所以派发说明里「Gemini 走 `condition_code(...) or info.code` 这条回落」的前提不成立，实测：

```
gemini-generate-content  {'error': {'code': 400, 'message': "prompt is too long: …", 'status': 'INVALID_ARGUMENT'}}
condition_code gemini -> ''
```

`or info.code` 的唯一可达路径是未知方言经 `write_error` 兜底进 `_anthropic`——而那条路径按 `write_error` 自己的 docstring 是不可达的（该说法的真伪见 F-03）。M9 实测：删掉 `or info.code`，302 全绿，**今天是死分支**。

**回答 Q3**：回落写法本身没有错（对没有 `code` 通道的方言返回空、由调用方兜回默认，比编一个拼写更对）；但既然它今天不可达，`_gemini` 的 `wire_format` 参数就是纯噪声。两个候选：让 `_gemini` 也走 `_code`（Gemini 信封里没有放它的字段，等于什么都不做，不推荐），或者把三个 writer 的签名统一成 `(info, *, wire_format)` 并接受 `_gemini` 忽略它、在 docstring 里写明为什么忽略。我倾向后者，理由是签名统一是 `_WRITERS` 这张表的前提。

### F-06（minor）未知方言兜底：形状回落了，词汇没有

`src/app/pipeline/delivery/formats/errors.py:118`：`return _WRITERS.get(wire_format, _anthropic)(info, wire_format)`。

实测：

```
some-future-dialect  {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': "prompt is too long: …", 'code': 'invalid_request'}}
```

也就是说：`type` 用的是 Anthropic 的表（`_anthropic` 内部硬接 `ANTHROPIC_ERROR_TYPES`），`code` 却拿未知方言自己的名字去查条件表、查不到、回落成类别默认。**一个自称「回落到 Anthropic 形状」的信封，恰好缺了让 Anthropic 客户端起作用的那个拼写。**

**回答 Q4**：不是想要的行为。更清楚的写法是先解析 writer、再传它真正在写的方言名，例如

```python
writer = _WRITERS.get(wire_format)
if writer is None:
    return _anthropic(info, ANTHROPIC_MESSAGES)
return writer(info, wire_format)
```

这样「形状与词汇同源」这条性质就写在代码里，而不是靠读者自己对上。今天不可达，所以是 minor。

### F-07（minor）`§5.5.2` 表的 OpenAI 一列，值零断言

`tests/unit/pipeline/test_error_classify.py:406-417`（`def` 在 :410）只断言 `set(table) == set(UpstreamCondition)`（键集合）；int 测试只跑 anthropic-messages 入站，钉住了 `model_max_prompt_tokens_exceeded`（`tests/int/test_error_envelope.py:650`）。M15 实测：把 OpenAI 的值改成 `"wrong_spelling_entirely"`，302 全绿。

Spec §5.5.2 那张表有两列，只有一列被钉住。补一条对 `write_error(info, wire_format="openai-responses")["error"]["code"]` 的断言即可。

### F-08（minor）`app/errors.py` 的模块 docstring 与它现在装的东西不符

`src/app/errors.py:3`：「Two things live here and nothing else:」，随后列 `ErrorCategory`（本次补进了 `UpstreamCondition`）与 `ErrorInfo` + 方言表。但本次还搬进了上游措辞正则（:224-239）与 `prompt_limit_counts()`（:242-255）——后者是一个 token 计数抽取器，服务的是 `app/tokenization` 的 `PromptLimitRegistry`，不是错误词汇表。docstring 只补了半句。

**回答 Q2 的层次部分**：把**识别用的措辞**放进 `app/errors.py` 我认为是对的——它与「按方言拼写」是同一份词汇的两面，分开放才是真的会漂。叶子约束实测仍然成立（`import app.errors` 只加载 `app.errors`），`app.tokenization.limits → app.errors` 不成环、也不构成不该有的边（`app.models.common` 早已依赖 `app.errors`）。真正别扭的只有 `prompt_limit_counts` 这个**函数**的归属：它的名字与返回值是 tokenization 的语义。可接受的做法是把它留在这里但在 docstring 里说清「为什么一个计数抽取器住在错误模块里」，或只把 patterns 放这里、让 `limits.py` 自己循环。两者都比现在的沉默好。

### F-09（minor）「frozen spec」措辞残留在本次改过的文件里

`tests/int/test_error_envelope.py:3`：「`.dev/docs/error-envelope/spec.md` is **the frozen form of it**.」
同类另一处（本次未改动）：`src/app/server/http_errors.py:3`：「rewritten on 2026-08-23, when `.dev/docs/error-envelope/spec.md` **froze**」。

2026-08-24 用户裁定废除「spec 冻结」，`.claude/rules/00-development-workflow.md` 明写「Never describe a Spec as frozen, and never cite one as 'the frozen spec'」。第一处在本次被修改的文件里，属于本轮该顺手带走的。

### F-10（minor）条件跨状态码生效，会产出自相矛盾的信封

`src/app/pipeline/error_classify.py:100` + `:103-109`。`describe` 对 `UpstreamRateLimit`（429）与 `UpstreamError`（5xx）走的是同一个 `_from_upstream`，所以只要 body 里有那几个字，条件就命中。实测（构造 body，标注为构造）：

```
429 -> rate_limit 429 context_window_exceeded
    {'type': 'error', 'error': {'type': 'rate_limit_error', 'message': "prompt is too long: …", 'code': 'model_max_prompt_tokens_exceeded'}}
502 -> upstream 502 context_window_exceeded
    {'type': 'error', 'error': {'type': 'api_error', 'message': "prompt is too long: …", 'code': 'model_max_prompt_tokens_exceeded'}}
```

客户端侧的后果是实测过的：`260824-claude-code-context-limit-detection.md` §1.2／§3.1 证明 `jXr` **没有状态码门**，所以一个 429 会让 Claude Code 立刻压缩并重发——对限流来说这是最糟的动作。

**这条不是实现违反 Spec**：§5.5.1 明确要求「不由状态码限定」，实现照做了。所以这是一条 **Spec 级的影响面缺口**：Spec 只写了「判据不受状态码限定」，没有写「于是 429/5xx 上命中会产生什么信封、客户端会做什么」。触发它需要一个非 400 且含该措辞的上游 body，目前**零一手样本**，所以定 minor。与 F-01(a) 叠加：裸片段把触发面明显放宽了。

**建议**：在 §5.5 补一段影响面（或补一条「命中但状态码不是 4xx 时如何处置」的条款），并把 M8 那条变异变成一条测试——不管最终裁决是「保持不限定」还是「限定到 4xx」，都需要一条测试说明这是选出来的而不是默认掉的。

### F-11（nit）识别用的裸片段没有复用刚定义的常量

`src/app/errors.py:205` 定义 `PROMPT_TOO_LONG_PHRASE = "prompt is too long"`，注释说「Kept as a constant so the guard test and the two message forms below cannot drift apart from one another」；而 `:235` 又硬写了一遍同一个字面量。识别（上游说什么）与拼写（我们说什么）确实是两件事、不该强行绑定，但两处字面量相同、注释又正好在讲防漂移，读者会以为已经绑上了。加半句注释说明「这里故意不复用那个常量」就够。

### F-12（nit）流式腿产不出条件，Spec 也没说它该不该产

`src/app/pipeline/delivery/stream.py:267-280`（`_stream_error`）构造 `ErrorInfo` 时不带 `condition`，`_report_failure` 也不经过 `_read_upstream_error`。所以一个以 `response.failed` 形态到达的上下文超限不会被改写。今天影响很小（超限在建流前就是 400），且 Spec §5.5 没有对流式腿提要求——**登记而非缺陷**，交调用方决定要不要写进 §5.5 的适用范围。

## 我核过、确认没有问题的面（登记，免得下次重查）

- **三个已知陷阱全部没踩**：`_response_parts`（`src/app/model_provider/ghc_client/errors.py:104-110`）取 `response.text` 与 `response.content`，与 `content-type` 无关；`_read_upstream_error` 用 `json.loads`，容忍末尾 `\n`；负控测试 `test_an_unrelated_400_on_the_same_leg_is_not_dressed_as_an_overflow` 直接钉住了 `invalid_request_body` 的零区分力。int 测试用真实入口 + `text/plain` header 跑通了这条腿，不是纸面推断。
- **`_overflow_rejection` 没有遮蔽 `_rejected`**：两者分别在 `tests/unit/pipeline/test_error_classify.py:52` 与 `:339`，名字不同、无覆盖关系。
- **夹具逐字忠实**：`RESPONSES_LEG_OVERFLOW` 与 48 例报告 §1.2 的 Python 字面量逐字节一致（含末尾 `\n`）；`ANTHROPIC_LEG_OVERFLOW` 与 §1.1 实例 B 一致。我另外核了报告全文 `&gt;` 零命中，所以夹具里用字面 `>` 是对的。
- **`ErrorInfo` 新字段无回归**：AST 扫描全仓零处位置参数构造。
- **`parse_prompt_limit_error` 逐字等价**：12 条差分语料零差异。
- **上游原文没有真的丢**：条件命中时 `upstream_error` 扩展不出现（`_upstream_remains` 只在 `UPSTREAM_ERROR_NOT_INTERPRETED` 时给），信封里确实看不到上游原句；但 `src/app/observability/rejection_capture.py:62` 对 4xx 非限流全量落盘 `error.body`，措辞漂移的事后取证面仍在。**不构成发现。**
- **恒真断言**：`assert "message" not in body`（`tests/int/test_error_envelope.py:647`）不是恒真——`_anthropic` 若被压扁就会失败；`assert not any(character.isdigit() ...)` 是有效的「合成数字」控制。这两条我认为写得好。

## 考虑过但否决 / 降级的路线

1. **把「message 应当在 writer 侧按方言渲染」升为我方 major** —— 降级为 F-04 的窄版。理由：Spec §5.5.2 已明知而为地裁了这个取舍并写下了理由，我读用户亲笔那句不足以直接推翻它，低置信的分歧应交调用方而不是我自己拍板。
2. **把「上游原句从信封里消失」报为信息丢失** —— 否决。查了取证面，`rejection_capture` 全量落盘，见上节。
3. **把「正则搬进 `app/errors.py` 造成层次问题」报为 major** —— 降级为 F-08。理由：叶子性质与无环都是我实测过的，剩下的只是 docstring 不同步与一个函数的命名归属。
4. **把「`_read_upstream_error` 不看 `content-type`」报为缺陷** —— 否决。那正是对的做法，且 int 测试真的用 `text/plain` 跑通了。
5. **把「夹具用字面 `>` 而录制可能是 `&gt;`」报为夹具失真** —— 否决。报告原文 `&gt;` 零命中，且 48 例报告 §4 有把真实 body 喂进 `parse_prompt_limit_error` 拿到数字对的实测。
6. **重跑派发说明里那六条已知变异** —— 否决。调用方已给出结果，重跑是重复已有证据；我改为找它们没覆盖的，并用 M18 做控制证明这批测试整体有分辨力（这一步不能省，否则我那几个「全绿」读起来和探针没跑起来一样）。
7. **对 `is_context_window_exceeded` 提议加状态码门** —— 不作为建议提出。Spec §5.5.1 明确要求不限定，改它是 Spec 层的事；我只在 F-10 把影响面交回去。
8. **建议引入一套判据回归的证明设施（判据矩阵 / 覆盖门）** —— 否决。项目规则明禁把普通实现升级成证明设施；F-02 的建议停在「补几条只带单一信号的用例」这一档。

## 搜索面

**读过**：`spec.md` 全文；48 例上游报告全文；Claude Code 判据报告全文；`src/app/errors.py`、`src/app/pipeline/error_classify.py`、`src/app/pipeline/delivery/formats/errors.py`、`src/app/tokenization/limits.py`、`src/app/server/http_errors.py` 全文；`src/app/pipeline/delivery/stream.py` 的 `_stream_error` / `_report_failure` 段；`src/app/observability/rejection_capture.py` 前 80 行；`src/app/model_provider/ghc_client/errors.py` 的 `_response_parts`；两个测试文件的新增段与既有夹具；`tests/unit/test_module_boundaries.py` 全部断言；`tests/unit/test_imports.py`；`.dev` 侧 `plan.md` K 片与 `deferred.md` E-10／E-11 的 diff；同目录 spec 评审报告（对账用，最后读）。

**跑过**：全量 pytest、ruff、pyright；叶子与依赖图的两个子进程探针；`ErrorInfo` 位置参数 AST 扫描；`parse_prompt_limit_error` 12 条差分；`write_error` 四方言探针；429／502 跨状态码探针；六条变异（含一条控制）。

**没看的面**：`hand_over.py` 与 MCP 侧对 `ErrorCategory` 的既有消费（`condition` 是新字段、默认 `None`，我判断不受影响，但没有读那两处代码核实）；`tests/tui/`（默认扫描外，与本切片无关）；真实上游（全程未发任何上游请求）；`docs/.human-controlled/` 两处改动的实现影响（明确排除在范围外）。

**仓库状态**：评审全程只写本报告一个文件。六次变异各自从 `/tmp/review-snapshot-260824/` 快照还原，最终 `git diff` 与开始前逐字节一致（md5 `1266dbd9b3ceacd9c9e78821cb86e5b9`），`git status --porcelain` 与开始前相同。

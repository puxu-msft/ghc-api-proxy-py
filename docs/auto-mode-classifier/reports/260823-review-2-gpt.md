# Auto mode classifier 三次未评审改动的异源独立评审

- 评审日期：2026-08-23
- 评审基线：`2b28d071354531f3308cce406c13488d4275390f..4087a86f27d09f46f751e15ead7c359c079e0d3b`
- 代码范围：`src/app/config/schema.py`、`src/app/pipeline/auto_mode_classifier.py`、`src/app/pipeline/driver.py`、`tests/unit/pipeline/test_auto_mode_classifier.py`
- 排除项：未审 `f5b5e3a`，它不在上述四个文件的净 diff 中，也与本特性无关。
- 用户权威输入：读取的是当前工作树里未提交的 `docs/.human-controlled/config.example.yaml`；`git status --short` 为 ` M`，当前文件 hash 为 `cf13e90387c2a70748afce19eb7cbcb663d8acac`，而 HEAD blob 为 `ecbd760d9df128f2ef52c6cdd28ca0798e9a5b72`。
- 结论：`needs-fix`。
- 发现计数：blocker 0，major 2，minor 3。
- 证据权重：两条 major 均有当前字节、运行时值或受控变异支撑，强到可以据此要求修复；三条 minor 均有精确反例，但不表示当前核心短路行为已经出错。

## 总结

A 的七项修复全部仍在，逐项运行没有找到回归反例。当前产品代码还能正确识别 severity 阶段 2、输出 `101`、过滤大小写变体、限定 Anthropic Messages 入口、先过结构门槛、发布 `request.succeeded`，测试里的 parser 转写也仍与实跑的 ECMAScript 反例一致。

需要修的是配置契约与测试分辨力。schema 的 `block_reason_str` 默认值没有逐字服从用户当前亲笔配置；更严重的测试问题是，`test_the_reason_reaches_the_reply` 没有走配置到 `handle()` 的接线，我把生产接线改成硬编码错误字符串后，整个 scoped 测试文件仍是 `42 passed`。另有一个过宽的 `pytest.raises(ValidationError)`、一个对过滤机制恒绿的参数实例，以及 living status 中两个 `false` 时代残留。

## Findings

### Major-1：schema 的 `block_reason_str` 默认值与用户权威文件不一致

- 严重度：major
- 置信度：高。
- 位置：`src/app/config/schema.py:303-331`，具体默认值在 `src/app/config/schema.py:324`；用户权威值在 `docs/.human-controlled/config.example.yaml:567`；相同权威复述在 `.dev/docs/auto-mode-classifier/spec.md:107-123` 与 `.dev/docs/auto-mode-classifier/status.md:17-30`。
- 证据：当前用户文件写的是 `Blocked by proxy, without a model review.`，schema 默认值却是 `Blocked by proxy configuration, without a model review.`。运行 `InterceptAutoModeClassifierConfig().model_dump()` 得到后者；解析当前用户文件则得到前者。
- 影响：显式复制当前 example 的部署行为正确，但只配置 `decision: block`、省略 `block_reason_str` 的部署会得到另一句用户未裁定的默认理由。`src/app/config/schema.py:1` 自称匹配用户权威配置，且本次任务明确要求默认值逐字对账，因此不能把语义近似当成一致。
- 修复判据：`InterceptAutoModeClassifierConfig().block_reason_str` 必须逐字等于当前用户权威文件的值，并由读取该权威值或直接断言该默认值的测试守住。

### Major-2：`test_the_reason_reaches_the_reply` 不验证配置接线；把生产接线改坏后 42 条测试仍全绿

- 严重度：major
- 置信度：高；有运行时注入证明、全文件变异结果与字节级还原。
- 位置：测试在 `tests/unit/pipeline/test_auto_mode_classifier.py:234-239`；真正读取配置并送入回复的接线在 `src/app/pipeline/driver.py:210-235`，具体读取点是 `src/app/pipeline/driver.py:219`。
- 问题：测试直接调用 `verdict_text(verdict, "refused: this proxy is configured to block")`，再检查同一句 literal 出现在结果中。它只证明 helper 会保留参数，不经过 `ProxyConfig`、`handle()` 或 `_answered_auto_mode()`，因此没有证明名为 `block_reason_str` 的配置会到达回复。
- 变异验证：在独立 clone `/tmp/ghc-api-proxy-review-260823-gpt-YxRpRt` 中，把 `driver.py:219` 改成 `text = verdict_text(verdict, "BROKEN hard-coded reason")`；用 `inspect.getsource()` 确认测试进程加载的是该 clone 且变异已生效；随后运行整个 `tests/unit/pipeline/test_auto_mode_classifier.py`，结果仍为 `42 passed in 2.08s`。
- 还原证明：`driver.py` 变异前后 SHA-256 都是 `62383e06dc3f47cc38533c85219f88230cc2efb29ab593500f0a6ab1f9b72aec`，且还原后 `git diff --exit-code -- src/app/pipeline/driver.py` 通过。
- 影响：本次三轮改动恰好重命名并搬迁了这个键；当前代码接线是对的，但测试不能阻止同类改名遗漏或硬编码回归，且测试名会让读者误以为这条接线已经受保护。
- 修复判据：用一个唯一的自定义 `block_reason_str` 经 `ProxyConfig → build_chain → handle()` 驱动命中请求，再从合成 body 断言该唯一字符串；把 `driver.py:219` 改成任何硬编码值时，这条测试必须变红。

### Minor-1：`test_the_transcript_wrapper_is_not_a_setting` 接受任意 `ValidationError`，没有钉住未知键这一失败原因

- 严重度：minor
- 置信度：高。
- 位置：`tests/unit/pipeline/test_auto_mode_classifier.py:226-232`。
- 当前事实：我实际构造 `InterceptAutoModeClassifierConfig(match_transcript_open="<conversation>\n")`，当前唯一错误是 `type == "extra_forbidden"` 且 `loc == ("match_transcript_open",)`，所以这一次绿灯确实来自预期原因。
- 分辨力缺口：测试只写 `pytest.raises(ValidationError)`；若未来同一构造因另一个字段默认值失效、model validator 或其他 schema 错误抛出 `ValidationError`，它仍会通过，却没有证明 `match_transcript_open` 不存在。
- 修复判据：捕获异常并断言错误集合至少精确包含 `("extra_forbidden", ("match_transcript_open",))`，且不存在其他错误。

### Minor-2：大小写 reason 参数组里的 `< block >` 实例对被测过滤机制恒绿

- 严重度：minor
- 置信度：高；已把过滤与保留两种输出都送入测试自己的客户端 parser。
- 位置：参数在 `tests/unit/pipeline/test_auto_mode_classifier.py:301-307`，断言在 `tests/unit/pipeline/test_auto_mode_classifier.py:309-316`；客户端等价 scan 在 `tests/unit/pipeline/test_auto_mode_classifier.py:107-108`。
- 反例：对 reason `Proxy overrode < block >no.`，当前过滤输出 `<block>yes</block>`，`parses_as_block()` 为 `True`；手工保留 reason 后的输出 `<block>yes</block>\n<reason>Proxy overrode < block >no.</reason>`，`parses_as_block()` 仍为 `True`。原因是客户端正则只识别精确的 `<block>`，不识别带空格的 `< block >`。
- 判断：没有找到整条测试方法无条件恒真；但这个参数实例对它声称验证的 reason 过滤机制恒绿。前两个大小写参数有分辨力，这一个没有，而且它不是“大小写不敏感”的样本。
- 修复判据：若契约只跟随客户端 parser，就移除该参数；若另有独立契约要求连 `< block >` 都丢弃，则直接断言 `<reason>` 不存在，不得再拿客户端 parser 的可解析性充当 oracle。

### Minor-3：living status 仍残留标量 `false` 时代的当前状态声明

- 严重度：minor
- 置信度：高。
- 位置：`.dev/docs/auto-mode-classifier/status.md:9` 与 `.dev/docs/auto-mode-classifier/status.md:54-58`；同一文档较后的正确陈述在 `.dev/docs/auto-mode-classifier/status.md:38-42`。
- 残留一：`status.md:9` 仍写“默认 `false`”，但当前 schema、spec 与用户权威契约都是默认 `passthrough`。
- 残留二：`status.md:58` 把“拆掉 `decision is False` 短路后两条测试变红”写成当前七项变异证据；当前代码已没有这条分支，当前测试也不能再复现那次标量阶段的变异。该句现在是历史记录，却放在 living status 的当前验证栏并被读成当前分辨力。
- 代码侧核对：当前四个 scoped 文件里没有 `decision is False`、`decision == False` 或 `false | allow | block` 残留；运行时 `False`、`True` 与字符串 `"false"` 都被 `AutoModeDecision` 拒绝，`passthrough`、`allow`、`block` 三值被接受。
- 修复判据：当前状态只写 `passthrough`；标量阶段的变异结果若保留，必须明确标成历史且不得支撑当前测试分辨力。

## A：七项回归逐条结论

| 项 | 结论 | 文件与行号 | 实际运行验证 |
|---|---|---|---|
| A1 severity 同时读 `stop_sequences` 与 system `<severity>` | **仍修着，没找到回归反例。** | `src/app/pipeline/auto_mode_classifier.py:140-158`，其中 stop signal 在 `:149-151`，system signal 在 `:152-157`。 | 全文件测试实际覆盖 `stop_sequences=["</severity>"]`；另构造无 `stop_sequences`、system Output Format 含 `<severity>` 的阶段 2 请求，`classify()` 返回 `protocol="severity"`，不是 block。 |
| A2 severity block 分值 > 100 | **仍修着，没找到回归反例。** | 常量在 `src/app/pipeline/auto_mode_classifier.py:34-41`，使用点在 `:202-204`；回归断言在 `tests/unit/pipeline/test_auto_mode_classifier.py:421-432` 与 `:549-570`。 | 对上述阶段 2 请求配置 `block`，实际文本为 `<severity>101</severity>`，parser 得 `101.0`，满足 `> 100`。 |
| A3 `<block>` reason 过滤大小写不敏感 | **仍修着，没找到大小写回归反例。** | `src/app/pipeline/auto_mode_classifier.py:43-44` 与 `:206-210`。 | reason `Proxy overrode <BlOcK>no</bLoCk>.` 实际被整段丢弃，输出只剩 `<block>yes</block>`，客户端等价 parser 得 `True`。`< block >` 的额外宽匹配另见 Minor-2，不是否定大小写修复。 |
| A4 短路以前置 `inbound_format is ANTHROPIC_MESSAGES` 门控 | **仍修着，没找到入口回归反例。** | `src/app/pipeline/driver.py:117-140`，门在 `:123`。 | 同一 marker body 从 `ANTHROPIC_MESSAGES` 进入时 `synthesized=True`；从 `OPENAI_CHAT_COMPLETIONS` 进入时 `synthesized=False`，并到达会故意抛 `AssertionError` 的 upstream probe。 |
| A5 两个 marker 都必须先过结构门槛 | **仍修着，没找到绕过反例。** | 结构门槛在 `src/app/pipeline/auto_mode_classifier.py:114-137`，且在 marker 判别前于 `:174-182` 执行。 | 分别构造只保留 system marker 与只保留 transcript marker 的请求，再逐一加入 `tools`、`stream=True`、assistant 轮，共六个输入，六个 `classify()` 都返回 `None`。 |
| A6 测试 parser 保持 ECMAScript 语义 | **仍修着，没找到转写回归反例。** | 显式 `\s` 集合在 `tests/unit/pipeline/test_auto_mode_classifier.py:103-104`，`re.ASCII` 在 `:106-108`，`[0-9]` 在 `:109-110`。 | Python 与实际 Node.js 分别运行五个区分输入，结果逐项一致：`<block>yesé` → `True`、long-s 变体 → `None`、Arabic-Indic digit → `None`、U+001C 空白 → `None`、NBSP → `0`。 |
| A7 短路路径发布 `request.succeeded` | **仍修着，没找到事件回归反例。** | `src/app/pipeline/driver.py:127-140`，append 与 publish 在 `:132-134`。 | 注册真实 `EVENT_REQUEST_SUCCEEDED` subscriber 后运行 `handle()`，结果 `outcome.events == ["request.succeeded"]`，subscriber 恰调用一次并收到同一个 `RequestContext`。第一次 probe 的 subscriber 自己误读不存在的 `request_id` 属性而在已被调用后抛错；修正为记录 context identity 后重新运行得到上述结果，没有把 probe 自身错误算成产品失败。 |

## B：配置契约逐项结论

1. **读取的是当前未提交用户文件。** 证据是工作树状态、当前 hash 与 HEAD blob 三者均已记录在报告开头；当前 section 是用户正在编辑的三键版本。
2. **键集合没有多键或少键。** `InterceptAutoModeClassifierConfig.model_fields` 恰为 `decision`、`match_system_prompt_prefix`、`block_reason_str`；当前用户文件整份经 `ProxyConfig.model_validate()` 解析成功，section 的 `model_dump()` 与 YAML 中三个显式值相等。
3. **`decision` 枚举与默认正确。** 类型是 `Literal["passthrough", "allow", "block"]`，schema 默认 `passthrough`，符合 spec 的“不写即关闭”；example 中显式 `allow` 是作者调优值，不是 schema 默认声明。旧的 bool `False`、bool `True` 与字符串 `false` 均被运行时拒绝。
4. **`match_system_prompt_prefix` 默认逐字一致。** schema 与用户文件都是 `You are a security monitor for autonomous AI coding agents.`。
5. **`block_reason_str` 默认不一致。** 这是 Major-1。
6. **生产代码没有 `False` 分支或死分支残留。** 当前 residual search 与运行时三值验证均未发现反例；living status 有两处文字残留，见 Minor-3。

## C：测试分辨力逐项结论

### `test_the_prompt_marker_is_configurable`

**能失败。** 在独立 clone 中把 `classify()` 对该字段的读取改成硬编码旧英文前缀，先用运行时 `inspect.getsource()` 证明变异模块路径为 `/tmp/ghc-api-proxy-review-260823-gpt-YxRpRt/src/app/pipeline/auto_mode_classifier.py` 且变异行已加载；目标测试随后在 `tests/unit/pipeline/test_auto_mode_classifier.py:224` 按预期失败，因为 repaired config 仍得到 `None`。还原后同一测试 `1 passed`。

变异文件还原前后的 SHA-256 都是 `6814b353c714348e07940dd2734d4d1a24bea47824bb032a4a7c025be47f7e79`，还原后的 scoped `git diff --exit-code` 通过。这个绿灯有分辨力，强到可以据此信任该字段在 `classify()` 内确实被读取。

### `test_the_transcript_wrapper_is_not_a_setting`

**当前是因正确原因通过，但断言方式不可靠。** 当前错误精确为 `extra_forbidden @ match_transcript_open`；测试却接受任意 `ValidationError`。结论与修复判据见 Minor-1。

### 恒真或假绿检查

没有找到整条测试方法无条件恒真。找到两处更具体、且已运行证实的分辨力缺口：一是 `< block >` 参数实例对 reason 是否过滤恒绿，见 Minor-2；二是测试名声称配置 reason 到达回复，但把真正的 driver 接线硬编码改坏后全文件仍 `42 passed`，见 Major-2。除这两处外，我按 `rg` 列出的全部 assertion 与 `pytest.raises` 逐条核对，没有再找到由同一个被测值计算 expected、字面量自等或不经过所声称生产路径的反例。

## 运行记录摘要

- `uv run pytest tests/unit/pipeline/test_auto_mode_classifier.py --no-cov --quiet`：`42 passed in 4.15s`。
- `uv run ruff check` 限定四个 reviewed 文件：通过。
- `uv run pyright` 限定四个 reviewed 文件：`0 errors, 0 warnings, 0 informations`。
- 自定义输入 probe：A1、A2、A3、A4、A5、A6、A7 均得到上述逐项结果。
- Node.js ECMAScript parser probe 与 Python transliteration 对五个区分输入逐项一致。
- prompt 配置读取的正向变异：目标测试红，字节还原，恢复后绿。
- reason 配置接线的反向变异：整个 scoped 文件仍 42 绿，字节还原；这正是 Major-2 的分辨力证据。
- 主工作树在 probe 前后保持同一状态；没有修改四个 reviewed 文件，也没有触碰用户未提交的 `docs/.human-controlled/config.example.yaml`。

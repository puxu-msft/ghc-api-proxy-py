# G1 候选 `4ffa95f` 评审

## 总评

**结论：needs-fix。** 候选的总体形态符合冻结 spec：`failure` 与成功语义的 `seen` 分开，客户端在已提交后收到 Anthropic SSE `error` 且不再收到 `message_stop`，两种方言的正常错误事件都能进入聚合记录，Anthropic 腿的静默截断文案也不再错称 `Responses`。但是 `_StreamAccounting.finish()` 仍有一条可达分支会把已记录的上游明确失败写成 `[ OK ]`，直接破坏本补丁要建立的日志／客户端一致性；此外，Responses 合法的 nullable `code` 会被伪造成字符串 `"None"`。前一项是 major，足以阻止当前候选合入。

评审对象固定为隔离工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/upstream-error-events` 的完整 HEAD `4ffa95f4c642a892406385229aac22e61e7f7007`。证据权重：下列行为结论均由候选源码、冻结 spec、实际运行探针或目标测试直接支持，强到足以行动；关于上游是否现实中发出某个合法事件排列，不作频率推断。

## 发现

### major：已有 `stop_reason` 的失败流绕过 `_ending()`，日志和 JSONL 被标成成功

位置：`src/app/server/pipeline_app.py:540-543`，相关生产者在 `src/app/pipeline/delivery/assembler.py:155-162`，客户端分支在 `src/app/pipeline/delivery/stream.py:291-303`。

`finish()` 目前只在 `not (delivered_whole and terminal.stop_reason)` 时调用 `_ending(terminal)`。这个门没有把 `terminal.failure` 纳入条件。Anthropic 流先收到合法的 `message_delta`，从中记下 `stop_reason="end_turn"`，随后以 terminal `error` 结束时，最终状态是 `drained=True`、`failure is None`、`terminal.stop_reason="end_turn"`、`terminal.failure is not None`、`terminal.seen=False`。`stream.py` 因失败分支排在成功分支之前，会正确向客户端发送 `error` 且不发送 `message_stop`；但 `finish()` 把 `delivered_whole and terminal.stop_reason` 判真，完全跳过 `_ending()`，于是 `status_override=None`、`detail=""`，HTTP 200 经 `status_for` 落成 `ok`。JSONL 同时出现 `status:"ok"`、`terminal_seen:false` 和非空 `upstream_error`，控制台则出现 `[ OK ] ... end_turn`，与客户端明确失败互相矛盾。

我用真实 `AnthropicAssembler.push()` 依次送入 `message_delta {stop_reason:"end_turn"}` 与 `error {type:"overloaded_error",message:"Overloaded"}`，再以 `drained=True` 调用真实 `_StreamAccounting.finish()`。探针从候选工作树加载 `pipeline_app.py`，结果为：`seen=False`、`stop_reason='end_turn'`、`failure=UpstreamFailure(...)`，但最终 `status_override=None`、`detail=''`；另行核对 `status_for(200, override=None)` 得到 `ok`。这不是把 `seen` 设真的伪装成功，而是失败状态被外层旧成功门挡在 `_ending()` 之外。

现有 int fixture `sse_upstream_ending_in_an_error()` 在首个 `message_delta` 之前截断正常流，再拼接 `error`，所以它构造出的 `terminal.stop_reason` 必为空，无法覆盖这个门。修复后应增加一个保留 `message_delta`、以 `error` 替换 `message_stop` 的用例，至少同时断言客户端无成功 terminal、日志状态为 `fail` 且 `detail` 为上游错误，而不是 `ok/end_turn`。

### minor：Responses 的合法 `code:null` 被伪造成客户端和 JSONL 中的字符串 `"None"`

位置：`src/app/pipeline/delivery/assembler.py:387-397`，尤其是 `code=str(error.get("code", ""))`。

当前安装的 OpenAI SDK 对 `ResponseErrorEvent.code` 的类型定义是 `str | None`，因此顶层 `error` 事件带 `"code":null` 是合法形状。候选用 `str()` 归一化后得到 `failure.code == "None"`；`stream.py` 认为它非空，进而向客户端发送 `"code":"None"`，结构化 `upstream_error` 也永久记录同一个伪造值。实际探针输入 `{"type":"error","code":null,"message":"Overloaded","param":null,"sequence_number":7}`，输出帧确实包含 `{"type":"upstream_error","message":"Overloaded","code":"None"}`。

这也说明实现并未完全沿用 legacy 的取词语义：`responses_stream_parser.py:496-500` 使用 `_optional_string`，`null` 不会变成文本。正常位置选择是对的——官方 `error` 从顶层取，`response.failed` 从 `response.error` 取；legacy 另外还提供了两处之间的 fallback，但冻结合同不要求接纳 nested-only 的非官方 `error`，因此我不把缺少该 fallback 单独列为缺陷。需修的是 nullable 合法值不得通过 `str(None)` 变成上游从未给出的 code。三个字段均缺席或为空串时，当前 `_failure_message` 的通用客户端文案与 `_failure_detail` 的 `upstream gave no reason` 都不误导；问题仅在 `null` 被错误地解释成文字。

### minor：新增落盘契约没有正向测试，清空结构化字段仍全绿

位置：`tests/unit/observability/test_request_log_file.py:116-155` 与 `tests/int/test_pipeline_app.py:1698-1731`。

`upstream_error` 是新的 JSONL 落盘字段，但单测只断言成功请求写出空字典；int 测试只检查客户端 body 和控制台 `detail`，没有读取或断言错误请求落盘后的非空结构。测试中的注释还引用了不存在的 `test_an_upstream_error_event_reaches_the_record_and_the_line`。我用 pytest plugin 在运行时把 `_failure_fields` 精确变异为恒返 `{}`，并确认变异已生效；新增 int 用例和 request-log 单测仍然 `2 passed`。因此现有测试钉住了错误帧与日志散文的接缝，却没有钉住本补丁新声明的持久化契约。建议新增一条错误事件记录断言，精确核对 `{"type":"overloaded_error","code":"","message":"Overloaded"}`；无需扩展成完整状态空间。

## 按重点问题逐项判断

1. **Spec 合规与伪装成功**：`failure` 独立于 `seen`、失败帧先于截断／成功分支的基本形态正确；不会通过 `terminal_frames` 发送 `message_stop`。但上述 major 证明 `finish()` 的旧门仍可在日志与 JSONL 一侧伪装成功，当前候选尚未完全合规。
2. **两条交付路径一致性**：fixture 覆盖的“块后直接 error”输入下二者一致；“`message_delta(stop_reason)` 后 error”是明确反例，客户端失败而日志为 `ok`。另一个值得说明但不单列的问题是，若记录 error 后又发生 transport exception，`_ending()` 当前优先报告已知上游错误而不是后续 transport exception；这会丢失后者，但不改变请求失败判定，也不构成本切片已冻结合同的直接反例。
3. **取词与回退链**：客户端只把 prose 放进 `message`，日志把 label 与 prose 合并，这个刻意不对称合理。字段均为空时两侧都明确表达“上游失败但没给理由”，没有虚构具体原因。合法 `null` 经 `str()` 变成 `"None"` 是实际误导，已列 minor。
4. **Responses `error` 的取词位置**：官方主形状和 candidate 一致，顶层 `code/message`；`response.failed` 的官方主形状位于 `response.error`。Legacy 对所有 terminal 类型统一执行“顶层优先、`response.error` fallback”，所以“完全一致”这个说法过强，但 candidate 覆盖了两个官方主形状。真正的行为缺陷是 legacy 会保留 `null` 的缺席语义，而 candidate 不会。
5. **新增测试分辨力**：用户给出的 `seen=True` 变异使 assembler 单测变红而 int 测试不红是合理结果，不表示 int 测试无用。int 测试本来钉住的是 assembler failure 进入客户端帧和 `_ending()` 日志的交付形状；失败分支刻意排在 `seen` 之前，所以交付对该变异具有构造性免疫。更合适的正控是删除／绕过 `stream.py` 的 failure 分支或 `_ending()` 的 failure 分支，它们分别会使 body 或日志断言变红。现有 int 测试真正缺的是 major 所示的旧 `stop_reason` 门，以及 minor 所示的 JSONL 正向断言。
6. **`upstream_error` JSONL 字段**：命名与既有错误术语一致，三字段对象保留两种方言的不同 taxonomy，`{}` 表示未观察到上游 terminal error，而全空三字段对象仍可表示“观察到事件但它没给词”，这个形状合理。`detail` 是供人读的当前散文，`upstream_error` 是稳定分组字段，二者并存合理。需要补的是 nullable 值的正确归一化与正向落盘测试，不建议仅因本次评审改名或删掉任一载体。

## 验证与归因

- 候选工作树中，目标测试 `tests/unit/pipeline/delivery/test_sse_assembly.py`、`tests/unit/observability/test_request_log_file.py`、`tests/int/test_pipeline_app.py` 共 `113 passed`。
- 独立重跑 `uv run pyright src tests` 得到 `21 errors, 0 warnings, 0 informations`，全部只位于 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`。`git diff 4ffa95f^ 4ffa95f --` 对这两个文件为空，确认候选提交未修改它们；单独检查候选改动的四个生产文件得到 `0 errors, 0 warnings, 0 informations`。用户给出的 Pyright 归因成立。
- 未重复全量 pytest、Ruff 或用户已经完成的 `seen=True` 变异；前者已有明确候选 HEAD 下的证据，后两者对本次新发现没有额外判别力。
- 评审期间未修改候选代码、索引或 HEAD；结束前 `git status --short`、`git diff --exit-code`、`git diff --cached --exit-code` 均为空／成功。

## 增补复核：`eb6cdd6`

**结论：pass，无新增 blocker／major／minor。** 本轮只复核 `4ffa95f..eb6cdd652a2580c3a99da765f10d5a5b3a59b6a3`，没有重跑上一轮的全量、Ruff 或 Pyright 归因。三个新增回归测试定向运行得到 `3 passed`。

### 原三条发现的处置

1. **major 已关闭。** `delivered_whole` 现在同时要求 `terminal.failure is None`，因此已有 `stop_reason` 不能再越过明确失败。新增 fixture 保留 `message_delta` 并只用 `error` 替换 `message_stop`，准确构造了上一轮反例；int 测试同时检查客户端没有成功 close、日志 status 为 `fail`、detail 使用上游原话。协调方给出的旧门正控与上一轮独立探针同向，且目标机制与断言对齐，证据足够，无需重复变异。
2. **nullable `code` minor 已关闭。** `_text()` 只接受真实字符串，`None`、缺席及其他非字符串值归为空串，两个 assembler 的 failure 取词都统一经过该边界；新单测覆盖 Responses 合法的 `code:null`。这恢复了 legacy `_optional_string` 在缺席语义上的关键性质，同时没有把 nested-only 非官方形状扩大成合同。
3. **JSONL 正向测试 minor 已关闭。** 新测试从 `Terminal.failure` 经 `_Trace.absorb()`、`_log_completion()` 到真实 JSONL 写入，精确断言非空三字段对象、`status == "fail"` 与 `terminal_seen is False`；悬空测试名也已改为实际存在的名字。它直接打在上一轮恒返 `{}` 变异留下的盲区上。

### 双重失败时保留哪个 detail

当前取舍可以保留，本候选不要求改。上游 terminal error 已经决定 turn 的语义结果，后续 transport exception 不会把它改成另一种 turn outcome；让 `_ending()` 以上游原话作为主要 detail，比用后续 transport 症状覆盖它更有诊断价值。协调方理由中“后续 exception 是它的后果”这层因果说得略强：两者也可能只是先后发生或共享一个根因，现有代码没有证明因果。不过这不影响当前优先级裁决，也不构成冻结合同反例。若未来真实观测到双重失败并确认 durable request record 需要同时回答“turn 为什么失败”与“为何 error envelope 没送达”，届时应保留上游错误为主事实并追加 transport detail，而不是反转优先级；在没有该实例前不为它扩展本切片。

### History 扫描在 fixture docstring 中的措辞

措辞强度合适。它把否定结论严格限定在“既有 capture”“33.8M frame objects”“2026-07-17..08-15”的覆盖面内，并明确说这不是我方录制；随后仍把“上游是否恰好发送这种形状”留作 fixture 无法回答的问题，没有从零命中外推成“上游从不发”。这与探测报告的权重一致：覆盖时间窗内零 root error／`response.failed` 是强到可陈述的事实，2026-08-15 后没有 frame 覆盖则没有被暗中写成否定结论。

一个不影响 verdict 的文字精度提示：`assembler.py` 新 `_text()` docstring 中“Both legs declare these fields nullable”比现有类型证据宽；已确认 nullable 的是 Responses `error.code`，而 Anthropic `error.type/message` 与 Responses message 均声明为字符串。实现把不可信 JSON 边界的所有非字符串归零仍然正确；若以后触碰这段注释，宜收窄为“some fields may be absent or nullable”，但无需因此重开候选或复评。

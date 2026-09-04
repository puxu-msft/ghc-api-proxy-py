# 无条件剥离空白 text block 独立评审

## 结论

**判定：needs-fix。blocker 0，​​应改 2，建议 0，不同意但可接受 0。**

评审快照为 `/home/xp/src/ghc-api-proxy-py` 的 `main@5e98a9e` 加指定四个文件的未提交 diff。未修改源码或测试。用户给出的既有验证结果沿用；现场另做了静态调用链核对、最终 Responses wire 小探针和目标 diff 的 `git diff --check`，后者无输出、退出 0。结论强度足以要求修正下列两处，但不支持把现有全套测试结果外推为 Responses 最终 wire 已覆盖。

反转的生产接线本身正确：`src/app/pipeline/anthropic_request_hook.py:93` 已删除 `upstream_is_anthropic`；仓库内四个调用点均为两参数形式；`src/app/server/handler.py:76-87` 对所有 Anthropic Messages 入站请求先执行 fixup，再按 route 决定是否翻译，没有残余 leg 门控或死参数。

## 发现

### 应改 1：名为 Responses leg 的新增测试没有进入 Responses leg，也没有约束本次真正改变的最终 wire

- **位置：** `tests/unit/test_blank_text_blocks.py:171-194`，关联生产路径 `src/app/server/handler.py:76-87`、`src/app/pipeline/translation_driver/openai_responses.py:105-118,231-253,269-278,394-404`。
- **判定：应改。**
- **问题：** `test_the_responses_leg_is_held_to_the_same_rule` 只调用无 route 参数的 `_fix()`，随后仍断言 Anthropic-shaped `system` 和 `messages[].content`。它没有调用 handler、registry 或 `to_openai_responses`，因此即使 hook 与 Responses translation 的顺序断开、translation 重新生成空 text part，或最终 `instructions`／`input` 分段错误，该测试仍可通过。它不是恒真断言——把过滤变成空操作会使它变红——但它证明的是通用 helper 过滤，不是测试名和说明所声称的 Responses leg。
- **实际可观察差异：** 混合 system blocks 从 `"first\n\n\n\nthird"` 变为 `"first\n\nthird"`；首尾空白 block 会去掉前置／尾随的 `\n\n`。消息里的空白 text part 会从 Responses `message.content` 消失；若它原先独占 tool call 前后的一个 message item，则整个空 message item 消失，而不只是“一个空 text part”消失。现场按当前代码探得该新增样本最终为 `instructions: "be brief"`，且 `input` 只剩 `function_call`，没有空 `message` item。
- **修正建议：** 把该测试至少推进到 `default_registry().translate(... ANTHROPIC_MESSAGES -> OPENAI_RESPONSES)` 后断言最终 `instructions` 和完整 `input`；更贴近接线的做法是扩展 `tests/http/test_pipeline_app.py:143-163` 的现有 translated-route 测试，直接断言 fake provider 收到的 JSON。全空 system 的新增测试也应在同一最终 wire 样本中断言 `instructions` 缺失。无需新增验收框架。

### 应改 2：全空消息路径的日志自相矛盾，若干注释仍把只在 Anthropic leg 已知的拒绝写成所有 upstream 的事实

- **位置：** `src/app/pipeline/anthropic_request_hook.py:59-64,77-90,135-146`；对应测试说明 `tests/unit/test_blank_text_blocks.py:66-71,171-175,197-200`。
- **判定：应改。**
- **问题一：** `drop_blank_text()` 在 `:89` 对全空消息先记录“dropped N”，调用方在 `:140-146` 却不采用空结果并记录“sent unchanged”。两条日志同时为真不了；实际发送的是保留空白块的 `content`。简化后的 helper 若只负责返回过滤结果，最简单的是不在 helper 里声称改写已经落地，而由两个调用点在采用结果后记录。
- **问题二：** `:60` 仍把 predicate 写成“upstream would reject”；`:80` 写“Keeping it costs the whole request: upstream rejects”；`:143-146` 及测试 `:69` 写成所有路径都会发送原 body 并由 upstream 拒绝。这个全称不符合已核实边界：Responses leg 只知道 wire 会改变，旧门控理由正是没有测得 Responses upstream 拒绝；而全空消息经过翻译后不是“原样”发送，它成为一个空 `input_text` part。`content: []` 在 Responses writer 也不会原样发出，而会让该 message 没有任何 item（`openai_responses.py:231-253`）。
- **修正建议：** predicate 和通用 docstring 只陈述新裁决的语义判据；全空 warning 只陈述“保留该 turn，避免删除／改空后破坏历史结构”，不要无条件预言 upstream 拒绝。若要保留拒绝事实，明确限定为 direct Anthropic leg，但 helper 当前不再知道 route，因而更适合删掉该 route-specific 断言。

## 逐项核对

### 1. 反转是否完整

**通过，除上述陈述残留外没有代码条件化残留。** `src/app/pipeline/anthropic_request_hook.py:93-111,135-146` 对 system 和 message 都不再读取 route；`src/app/server/handler.py:76-80` 恢复两参数调用。仓库搜索只找到定义、handler 和两个测试 helper 共四个 `fix_anthropic_request(`，均无旧参数；`upstream_is_anthropic` 无命中。

### 2. Responses leg 与空 text fallback

**当前主样本不会因为剥离而触发 `responses.py:71-90`。** 请求链是 `handler.py:76-87` 先过滤，再经 `anthropic_messages.py:115-146` 读入 semantic request，最后由 `openai_responses.py:394-404` 写 Responses request。`responses.py:71-90` 是反方向的 response writer，只在 upstream response 已经读成零个可渲染 block 时运行；请求 `input` 为空不会在本进程内直接调用它。

具体结果如下：

- 混合 system：空白 block 不再参与 `openai_responses.py:105-118` 的 `"\n\n".join`，所以减少对应的空行 padding；有效文本顺序不变。
- 全空 system：`anthropic_request_hook.py:103-111` 删除键；`anthropic_messages.py:115-121` 将缺失值读成空 system；`openai_responses.py:403-404` 因 `request.system` 为空而不生成 `instructions`。
- 空白 text 加 tool block：空白 part 被删，tool block 仍由 `openai_responses.py:281-287` 生成 `function_call`，最终 `input` 非空。
- 全空 message：`anthropic_request_hook.py:140-146` 保留原 block，翻译后是含 `text: ""` 的 `input_text`／`output_text`，并非空 `input`。

存在一个更窄但真实的边界：若删掉空白 text 后只剩 writer 无法携带的 block，例如 foreign Claude reasoning state，`openai_responses.py:294-297,231-253` 可把该 message 渲染为零个 item，甚至让整个 `input` 为空。这不会直接触发 response fallback；是否随后得到零 output 取决于 upstream。该 translator 本来就会对不可携带 block 记录 conversion loss，单独只有这种 block 时也已能产生空 input，所以这不是本次反转新造的确定性回路。

`src/app/pipeline/translation_driver/responses.py:71-81` 确实仍会在 Responses upstream 合法成功但没有可渲染 output 时生成 `{"type":"text","text":""}`。客户端若回传一个只含该 block 的 assistant turn，当前 `anthropic_request_hook.py:140-146` 会落入全空例外并保留它；direct Anthropic leg 仍可能拒绝。这是现有 Spec 明许的 response fallback 与本次明确裁决的“全空 turn 不删除／不造 filler”共同留下的残余，不是请求过滤绕代码直接触发的回路，也没有忠实且更简单的本地改写，所以本评审不把它列为 blocker 或要求推翻例外。

### 3. 删除 system 键

**安全。** direct Anthropic leg 没有后续代码按 `payload["system"]` 取值，payload 缺键直接发送；按任务给出的实测，缺键被接受而 `system: []` 被拒绝。Responses leg 的 reader 使用 `payload.get("system")`（`anthropic_messages.py:115-121`），缺失值稳定映射为空列表；writer 只在列表非空时生成 `instructions`（`openai_responses.py:403-404`）。空列表输入也被当前 hook 删除，因此两条腿都不会把 `system: []` 送到 upstream。新增 `tests/unit/test_blank_text_blocks.py:197-210` 的断言有分辨力，不是恒真。

### 4. message 全空时不动

**取舍成立。** 例外保护的是 turn 的结构身份，不是给空白 block 宣称语义。删 message 会改变历史位置和 tool call/result 关联；写成 `content: []` 在 direct Anthropic leg 仍非法，在 Responses writer 则会使该 message 完全没有输出 item；写 filler 又会伪造内容。保留输入并把失败交给能准确命名它的一方，是现有选项中信息损失最小的。需要修的是 route-neutral 说明和日志，而不是把旧门控加回来。

### 5. 测试判定

- `tests/unit/test_blank_text_blocks.py:171-194`：断言本身有分辨力，但测试名／说明越出了实际 oracle；缺最终 Responses wire 覆盖，见应改 1。
- `tests/unit/test_blank_text_blocks.py:197-210`：不是恒真；能区分删键与保留 `[]`，并同时证明正常 message 未受影响。建议把缺 `instructions` 的最终 Responses wire 断言放进应改 1 的同一测试，而不是另建大矩阵。
- 用户给出的 no-op 变异使 13 条中 8 条转红，足以证明过滤 helper 的现有测试不是整体假绿；它不能补足 handler→translator→wire 的缺口。

### 6. 更简单或更正确的做法

生产结构总体已经是较简单的正确分层：纯 predicate／filter 给出 survivors，system 与 message 的 all-empty policy 留在各自调用点。唯一可再简化的是让 `drop_blank_text()` 真正只返回过滤结果，不在结果尚未被调用方采用时记录“dropped”；日志放到确认采用的分支。除此之外不建议恢复 route 参数、引入配置，或把两种 all-empty policy重新塞回 helper。

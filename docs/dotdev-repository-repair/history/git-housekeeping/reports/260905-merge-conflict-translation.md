# 翻译驱动 merge 冲突只读调查

## 1. 调查边界与结论

本报告只读调查 merge-base `e1b2baa99637349d2f552343c57769a311bfb179`、ours `605d42bd85d6d25bc5e4b73dada727a893742527`、theirs `8ac6522896cdd3a43d796c33999595c25b8f798b` 在以下四个文件上的 base／ours／theirs 对象与相关提交历史：

- `src/app/pipeline/translation_driver/anthropic_messages.py`
- `src/app/pipeline/translation_driver/openai_responses.py`
- `src/app/pipeline/translation_driver/semantic.py`
- `tests/unit/pipeline/translation_driver/test_translation_driver.py`

未修改源代码、Git 索引或提交。调查在隔离 worktree 中按对象 SHA 使用只读 Git 命令进行；为展开 diff3 冲突而写入的临时 blob 副本位于 `/tmp/translation-merge-investigation-abaf2125/`，不属于仓库工作树。

结论强度：**足以直接指导冲突解决。** 四个文件共有 8 个文本冲突 hunk，正确方向都不是整块选择 ours 或 theirs，而是组合三条彼此正交的演进：

1. ours 的 `ThinkingEffortIntent`、`output_config.effort`、per-message effort、`ThinkingTargetProfile` 与 capability alignment 负责“下一次模型调用采用什么 thinking／effort”。
2. theirs 的 `ReasoningContent`／`reasoning_bridge` 负责“历史或响应中的 reasoning 内容、summary 结构与 opaque continuation state 如何跨协议保存”。
3. theirs 的 `ToolChoiceIntent`、server-tool blocks、hosted-search response bridge 与 request-scoped `hosted_web_search_expected` 负责工具选择和响应解释。

request-level reasoning policy 只能保留 ours 的 `SemanticRequest.thinking_effort`。content-level reasoning 继续保留 `ContentBlock.reasoning: ReasoningContent | None`。两者名称相近但层次不同，不应恢复 base／theirs 的 `SemanticRequest.reasoning: ReasoningIntent | None`。

另有一个**不在四个冲突文件内、但按本方案合并后确定会失效的随动点**：`src/app/pipeline/translation_driver/openai_chat_completions.py` 与其单元测试仍引用 ours 已删除的 `request.reasoning`，必须迁移到 `request.thinking_effort`。这不是推测；对 theirs tip 的全树符号搜索与 blame 均定位到 `fcb6982cc4c9dcfa26eb4c82b3ecc764dc1a784d`。

## 2. 对象身份

| 角色 | Commit |
|---|---|
| merge-base | `e1b2baa99637349d2f552343c57769a311bfb179` |
| ours | `605d42bd85d6d25bc5e4b73dada727a893742527` |
| theirs | `8ac6522896cdd3a43d796c33999595c25b8f798b` |

| 文件 | base blob | ours blob | theirs blob |
|---|---|---|---|
| `src/app/pipeline/translation_driver/anthropic_messages.py` | `a0a2f2770bf04538bcd9b459b583257620bc3e21` | `e8ba54c07f3ffd701bb3c08f4010300341f58140` | `946594fe85986b3942864ffe12ff32c67c2e48cf` |
| `src/app/pipeline/translation_driver/openai_responses.py` | `edcb45f6ca9af84e3882094c9d314a3585e4529f` | `666888538930593e1dc3726ddf6cb9b42094d29f` | `7f393326651ce60685759feea608a851de763779` |
| `src/app/pipeline/translation_driver/semantic.py` | `4ffcc4153e61124453c4b4ea9135f169e4caffd6` | `9ef4ab8bb1e6616feb1c25803f71ad62656d69fd` | `be9d5aed6a96c8eb07d2aad7ff8edb014f9074fb` |
| `tests/unit/pipeline/translation_driver/test_translation_driver.py` | `5427a758cf7a6a91edecdb2d8bbba3a4181020e7` | `23b08c25b79f1c9428ec7f4ac8804a7a2fc7d693` | `f92b5b2188066a6d34bab161c44f456aa6036d4f` |

对上述 12 个 blob 的 `ls-tree` 身份已逐项核对。

## 3. 查过的相关提交

| Commit | 调查中确认的作用 |
|---|---|
| `e1b2baa99637349d2f552343c57769a311bfb179` | merge-base；仍使用旧 `ReasoningIntent`，并提供 merge 前 client-action delivery policy 的对照。 |
| `605d42bd85d6d25bc5e4b73dada727a893742527` | ours tip；其父提交为 local contextual completion，tip 本身更新配置与 message translation 文档。 |
| `8ac6522896cdd3a43d796c33999595c25b8f798b` | theirs tip；用于读取最终 remote reasoning bridge、tool semantics、response observation 与相关测试。 |
| `4b7d74f56b8b0264b481a2fefe275a233979fbb2` | ours：以 `ThinkingEffortIntent` 重写 Messages／Responses effort translation，增加 top-level／per-message effort、profile 与 model-capability alignment。 |
| `bb5783f17f8f21017010a14d00b762b49ee6cc13` | ours：在本地 delivery terminal 上增加 contextual Responses completion 和 client-action 显示。 |
| `6200600d756803ac15a7bdd0f90db303ca605188` | theirs：建立 `ResponseObservation`、`response_action.py` 与统一 request-completion projection。 |
| `b9b0a9bf501f1ce58bb19967dd8cc5670ec0505c` | theirs：建立结构化 `ReasoningContent`／`reasoning_bridge`，保留 summary parts、extensions 与 opaque continuation state。 |
| `18347af55137b87d5d7e8680c818a3c4bb3cc3af` | theirs：把预期 hosted web search 响应恢复成 Anthropic native unavailable pair。 |
| `4aa1e39eaee313dcfaada3e2843fe3bbdfb0c983` | theirs：补齐 hosted-search loss accounting 与 request-scoped response context。 |
| `3ec2ed85e147f107098a502e8ee90032795b39e0` | theirs：引入 `ToolChoiceIntent`，在实际发出的 tool declarations 上解析、改写或拒绝 `tool_choice`。 |
| `fcb6982cc4c9dcfa26eb4c82b3ecc764dc1a784d` | theirs：引入 Chat Completions writer；其 `request.reasoning` 引用构成合并后的隐藏随动点。 |

另对 `e1b2baa..605d42b` 与 `e1b2baa..8ac6522` 的完整 commit 序列做了范围扫描，并用四个冲突路径的 path-filtered log 确认直接改动来源。四个冲突路径在 ours 一侧只由 `4b7d74f5` 改动；theirs 一侧直接相关的是 `b9b0a9bf`、`18347af5`、`4aa1e39e` 与 `3ec2ed85`。

## 4. 演进还原

base 把两件不同的事压在一个 `ReasoningIntent` 上：Anthropic `thinking` mode／budget 被转换成 Responses effort，同时 reasoning content 只携带扁平 text 和单个 opaque state。ours 纠正了第一件事：thinking enablement、effort 与 provenance 被放入 `ThinkingEffortIntent`，并明确规定 budget 不选择 effort。theirs 纠正了第二件事：reasoning history 被提升为 `ReasoningContent`，summary boundaries、extensions、redacted state 与 provider-native continuation state 经 `reasoning_bridge` 保存。

因此，合并后应形成以下分工：

- `SemanticRequest.thinking_effort` 是 request-level producer policy。
- `ContentBlock.reasoning` 是 message／response content 与 continuation state。
- `SemanticRequest.tool_choice` 是跨 writer 共用的 tool-selection intent。
- `SemanticRequest.hosted_web_search_expected` 是请求侧 provenance，供 response translator 区分 expected 与 unsolicited `web_search_call`。
- `ResponseObservation` 是 side-only 的实际响应观测，不参与 request payload translation。

保留 `SemanticRequest.reasoning: ReasoningIntent` 不只是冗余：merged `reasoning.py` 来自 ours，已经不再定义 `ReasoningIntent`、`intent_from_thinking`、`unused_thinking_fields` 或 `resolve`，因此保留 theirs 的旧 import 会直接造成 import failure。

## 5. 逐 hunk 合并建议

### 5.1 `anthropic_messages.py` hunk 1：`_PASSTHROUGH_KEYS`

采用两边并集，精确结果应为：

```python
_PASSTHROUGH_KEYS = frozenset(
    {
        "model",
        "system",
        "messages",
        "tools",
        "stream",
        "max_tokens",
        "temperature",
        "thinking",
        "output_config",
        "tool_choice",
    }
)
```

`output_config` 已由 effort reader 拆成 modelled `effort` 与 `nested_extensions`；`tool_choice` 已由 `intent_from_anthropic_tool_choice` 读取，无法识别的 shape 会被显式放回 `extensions`。任一键缺失都会同时造成重复携带或错误 loss accounting。

必须保留的断言：

- `test_anthropic_same_format_nested_extensions_are_rebuilt`
- `test_anthropic_same_format_rebuild_uses_intent_and_nested_residuals`
- `test_an_unclaimed_choice_replays_on_the_same_format`
- `test_anthropic_tool_choice_round_trips_through_the_same_format`

### 5.2 `anthropic_messages.py` hunk 2：`to_anthropic_messages` 尾部调用顺序

保留两边调用，顺序应为：

```python
payload.update(request.nested_extensions_for(WIRE_FORMAT))
_restore_thinking(payload, request)
_apply_responses_thinking(payload, request, target)
_restore_tool_choice(payload, request)
payload.update(request.extensions_for(WIRE_FORMAT))
return payload
```

顺序是承重的：

- nested residual 必须先合入，再由 modelled effort／thinking 覆盖陈旧值。
- `_restore_thinking` 只处理 Anthropic-origin same-format rebuild。
- `_apply_responses_thinking` 只处理 Responses-origin crossing，并使用 resolved target profile。
- `_restore_tool_choice` 必须在 `extensions_for` 前运行，才能在 foreign opaque choice 被跨格式丢弃前拒绝它。
- 最后的 `extensions_for` 负责 same-format unclaimed choice 精确重放。

必须保留的断言：

- `test_minimal_maps_to_low_and_records_approximation`
- `test_responses_to_anthropic_reasoning_effort_uses_exact_downward_and_floor_alignment`
- `test_responses_reasoning_none_and_unspecified_effort_do_not_invent_output_config`
- `test_responses_tool_choice_is_restored_as_anthropic_spelling`
- `test_responses_parallel_false_becomes_disable_parallel_true`
- `test_a_crossing_without_tools_does_not_invent_a_choice`

### 5.3 `anthropic_messages.py` hunk 3：`_restore_thinking` 尾部与 `_restore_tool_choice`

不要二选一。保留 ours 的完整 `_restore_thinking` body，包括：

- 从 `nested_extensions["thinking"]` 恢复 future siblings 与 budget。
- 依据 `enabled`／budget 重建 `thinking.type`。
- 仅当 `effort_source is EffortSource.ANTHROPIC_TOP_LEVEL` 时恢复 top-level `output_config.effort`。

紧接着完整保留 theirs 的 `_restore_tool_choice`。两者是独立字段的 writer，没有替代关系。

必须保留的断言：

- budget 与 future siblings 原样保留。
- per-message effort provenance 不被错误恢复成 top-level effort。
- forced choice 没有 declarations 时拒绝。
- named choice 必须命中实际发送的工具。
- `disable_parallel_tool_use=False` 也必须在 same-format round trip 中保留。

### 5.4 `openai_responses.py` hunk 1：imports

采用现代 API 的并集，并删除已被合并态实现淘汰的 imports。精确结果应为：

```python
from app.pipeline import anthropic_server_tools
from app.pipeline.server_tool_text import render_server_tool_block, web_search_call_text
from app.pipeline.translation_driver.content import BlockKind, ContentBlock, SemanticMessage
from app.pipeline.translation_driver.reasoning import (
    RESPONSES_EFFORTS,
    EffortSource,
    ReasoningResolution,
    ThinkingEffortIntent,
    align_effort,
)
from app.pipeline.translation_driver.reasoning_bridge import (
    ReasoningBridgeError,
    ReasoningNotPortable,
    read_responses_reasoning,
    reasoning_to_responses,
)
```

不得保留：

- `call_text`：theirs 已用共享 `render_server_tool_block` 取代本地 renderer。
- `OpaqueFormat`、`ReasoningState`：theirs 的 `ReasoningContent`／bridge 已取代直接操作旧 opaque state。
- `resolve`：ours 的 merged `reasoning.py` 已删除该函数；merged `_apply_reasoning` 使用 `align_effort`。
- `ReasoningIntent`：同理已不存在。

这里必须保留的行为断言包括 reasoning summary／carrier round trip、server-tool text fallback、tool-result error marker 与 hosted-search native response pair。

### 5.5 `openai_responses.py` hunk 2：`_PASSTHROUGH_KEYS`

采用：

```python
_PASSTHROUGH_KEYS = frozenset(
    {
        "model",
        "instructions",
        "input",
        "tools",
        "stream",
        "max_output_tokens",
        "temperature",
        "reasoning",
        "tool_choice",
    }
)
```

不要把 `parallel_tool_calls` 无条件加入该集合。当前逻辑有意在 tool choice 成功建模且值为 `False` 时从 extensions 中移除；没有 modelled choice 或值为 `True` 时，它仍作为 same-format extension 存活。

必须保留的断言：

- `reasoning.summary` 等 residual 在 same-format 先恢复，再由 owned effort 覆盖。
- unclaimed／`allowed_tools` choice same-format 精确重放。
- `parallel_tool_calls=False` 与 modelled choice 结合；孤立 flag 不被误吞。
- crossing 时无法表示的 opaque choice 必须拒绝而不是静默丢失。

### 5.6 `semantic.py` hunk 1：imports

保留 ours 的 effort types，加上 theirs 的 tool-choice type：

```python
from app.pipeline.translation_driver.reasoning import ThinkingEffortIntent, ThinkingTargetProfile
from app.pipeline.translation_driver.tool_choice import ToolChoiceIntent
```

不得保留 `ReasoningIntent` import；merged `reasoning.py` 没有该符号。

### 5.7 `semantic.py` hunk 2：`SemanticRequest` fields

采用单一 request-level reasoning policy，加上 tool choice：

```python
thinking_effort: ThinkingEffortIntent | None = None
# None means absent or unclaimed; an unclaimed choice remains in extensions for exact replay.
tool_choice: ToolChoiceIntent | None = None
```

不要同时保留：

```python
reasoning: ReasoningIntent | None = None
```

必须继续保留 auto-merged 的以下字段与类型：

- `client_search_tool`
- `hosted_web_search_expected`
- `nested_extensions`
- `conversion`
- `TranslationTarget.thinking_profile` 与 `thinking_profile_pattern`
- `ConversionFactCode.THINKING_PROFILE_SELECTED`／`THINKING_PROFILE_REJECTED`
- server-tool 与 reasoning-intent loss codes

`hosted_web_search_expected` 不是通用 `ResponseObservation` 的重复字段。它表达“请求侧是否映射了 hosted search declaration”，用于把响应中的 `web_search_call` 区分成预期调用或 unsolicited 调用；响应本身无法还原这个事实。

### 5.8 `test_translation_driver.py` hunk 1：imports

合并成：

```python
from app.pipeline.translation_driver.anthropic_messages import (
    from_anthropic_messages,
    render_anthropic_thinking,
    to_anthropic_messages,
)
from app.pipeline.translation_driver.openai_responses import (
    from_openai_responses,
    to_openai_responses,
)
from app.pipeline.translation_driver.reasoning import (
    EffortSource,
    ThinkingEffortIntent,
    ThinkingTargetProfile,
)
from app.pipeline.translation_driver.reasoning_carrier import (
    RESPONSES_ENCRYPTED_CONTENT,
    decode_reasoning_carrier,
)
```

`RESPONSES_ENCRYPTED_CONTENT` 不能省略：theirs 已把 decoder 从单一 `encrypted_content` 字段升级为 typed carrier records，`test_a_responses_reasoning_item_reaches_anthropic_with_its_state_intact` 通过该常量读取 record。

测试文件除这个 import hunk 外应保留自动合并得到的两边全部测试，不应删除一侧测试来消除未使用 import。

## 6. 自动合并区域中必须保留的契约

### 6.1 Effort translation

以下断言共同定义新 request-level contract，不能退回 base／theirs 的 budget-derived `ReasoningIntent`：

- `ThinkingEffortIntent` 同时携带 `enabled`、`effort`、`effort_source`。
- Anthropic omitted thinking／effort 在 translated path 上是 enabled + high default。
- `thinking.budget_tokens` 只保留 wire residual，不选择 effort。
- top-level explicit effort 优先；per-message control 在下一个 user turn 生效，并要求 beta header。
- malformed thinking、effort 与 control message 在精确 field path 上拒绝。
- Responses `none|minimal|low|medium|high|xhigh|max` 域完整读取。
- target profile 决定 Anthropic `adaptive`／manual budget／disabled 是否可渲染。
- capability alignment 的 exact、downward、floor、not-carried 与 loss 顺序全部保留。
- nested residual 不可伪装成 lost effort。

对应的核心测试包括：

- `test_explicit_effort_wins_and_budget_never_selects_the_level`
- `test_anthropic_thinking_compatibility_has_static_wire_and_loss_expectations`
- `test_responses_reasoning_effort_reader_maps_the_complete_domain`
- `test_nested_extension_reasoning_fields_are_not_counted_as_lost_effort`
- `test_anthropic_reader_defaults_omitted_thinking_and_effort_to_enabled_high`
- `test_equal_per_message_effort_still_records_per_message_provenance`
- `test_invalid_per_message_effort_control_is_refused_before_message_parsing`

### 6.2 Reasoning bridge

必须保留 theirs 的以下断言：

- native Anthropic signature 不能伪造成 Responses `encrypted_content`。
- proxy-issued carrier 可以恢复原 upstream encrypted payload。
- Responses summary part boundaries、空 part、Unicode 与 extensions 完整 round trip。
- native Anthropic signature 经 Responses response carrier 后恢复。
- response reasoning carrier 使用 `RESPONSES_ENCRYPTED_CONTENT` typed record。
- request writer 使用 `bridge_for_client=False`，response writer 使用 `bridge_for_client=True`；这一区别不能因“统一 helper”而消失。

对应的核心测试包括：

- `test_a_real_anthropic_signature_is_refused_rather_than_forged`
- `test_a_carrier_this_proxy_issued_does_cross`
- `test_a_responses_reasoning_item_reaches_anthropic_with_its_state_intact`
- `test_a_response_round_trip_keeps_the_reasoning_payload`
- `test_response_round_trip_preserves_summary_part_boundaries_and_extensions`
- `test_native_anthropic_signature_round_trips_through_responses_response`

### 6.3 Tool semantics 与 hosted search

必须保留：

- errored `tool_result` 在 Responses 中写 `[tool_error] ` 并记录 loss；literal prefix 不被反向解释成 error。
- `auto`／`any`／`none`／named tool choice 映射。
- forced choice 无 declarations、名称未声明、名称歧义或目标 declaration 被改写成不可强制的 `tool_search` 时拒绝。
- explicit parallel restriction 与 tool choice 一起跨格式。
- same-format opaque／future choice 原样保留。
- mapped web-search choice 跟随 declaration 变成 `{"type": "web_search"}`。
- expected search 响应生成 `server_tool_use` + unavailable `web_search_tool_result`，且位于 answer 前。
- incomplete expected search 不被 hand-over filtering 丢掉。
- unsolicited search 保留 D3 text fallback。
- server-tool call id 不可携带与 partial representation 分别记账。
- generic server-tool family 仍走共享 text fallback。
- `hosted_web_search_expected` 在每次 `to_openai_responses` 开始时重置，并只由实际 emitted mapped declarations 设置。

对应的核心测试包括：

- `test_an_errored_tool_result_is_marked_in_text`
- `test_a_literal_tool_error_prefix_is_not_reinterpreted`
- `test_tool_choice_modes_convert_across_the_boundary`
- `test_a_named_function_tool_choice_passes_through`
- `test_a_forced_choice_of_a_replaced_search_tool_is_refused`
- `test_a_forced_choice_is_refused_when_the_name_is_ambiguous`
- `test_an_expected_search_becomes_a_native_unavailable_pair_before_the_answer`
- `test_an_expected_incomplete_search_is_not_dropped_by_hand_over_rules`
- `test_an_unsolicited_search_keeps_the_d3_text_fallback`
- `test_another_server_tool_family_keeps_the_existing_generic_text_fallback`

## 7. Local contextual completion 与 remote response observation 的组合

remote `response_action.py`／`ResponseObservation` 应成为唯一事实与分类来源；local `openai_responses_actions.py` 和 `assembling.ClientAction*` 不应与其并存为第二套 authority。

理由是二者并非完全等价：

- base 对缺失／未知 `tool_search_call.execution` 的 delivery policy 是 `False`，即继续等待 terminal。
- local classifier 把它标为 observational `UNKNOWN`，随后用 `requirement is not NOT_REQUIRED` 投影成 `True`，意外改变为提前释放。
- remote classifier 显式分开 `requirement=UNKNOWN` 与 `delivery_required=False`，保持 base delivery 行为，同时允许日志诚实显示“不知道”。
- remote 还保存 `basis`，并区分 malformed／local／container shell execution；这些事实由 delivery 与 observation 共用。

推荐组合方式：

1. 以 `ResponseObservation.output_items` 和每项的 `ClientActionObservation` 作为 contextual completion 的输入。
2. 将 local `client_action_classification_complete` 映射为 `observation.output_items is not None`；`None` 与空 tuple 必须继续区分。
3. 保留 local 的用户可见目标：completed 要带 action context；unknown action 要显示 `?`，但不能声称 client 确实欠一次动作；无法分类 terminal output 时保留“unclassified”语义。
4. delivery 只读取 `delivery_required`，console／JSONL 读取 `requirement`、`basis` 与 item fields。
5. 不让 observation 反向驱动 payload translation；它是 side-only view。
6. 不用 `ResponseObservation` 取代 `SemanticRequest.hosted_web_search_expected`，两者分别描述实际响应和请求侧 provenance。

这部分是**强建议，但位于四个文本冲突 hunk 之外**。单一 classifier 与保持 base delivery policy 的结论足以执行；最终 console 的精确拼写仍应以 local contextual completion tests 与 remote `format_response_observation` tests 的合并态为准。

## 8. 四个冲突文件之外的确定随动点

theirs 的 `fcb6982cc4c9dcfa26eb4c82b3ecc764dc1a784d` 新增了以下旧 API 引用，而 ours 的 `reasoning.py` 已删除旧 API：

- `src/app/pipeline/translation_driver/openai_chat_completions.py`：`if request.reasoning is not None:`
- `tests/unit/pipeline/translation_driver/test_openai_chat_completions.py`：`assert request.reasoning is not None`

两处应迁移为 `request.thinking_effort`。不要为兼容这两行而在 `SemanticRequest` 中恢复 `reasoning: ReasoningIntent`。Chat writer 仍应记录 `REASONING_INTENT_NOT_CARRIED`，因为该 wire 没有已测量的 request reasoning spelling。

对 theirs tip 的全树符号搜索显示，除两个冲突 translator 自身外，生产代码中剩余的 request-level `request.reasoning` 只有上述 Chat writer 一处；旧 `test_reasoning.py` 由 ours 的新版 reasoning tests 取代，因为 theirs 的 `reasoning.py`／`test_reasoning.py` blobs 与 merge-base 相同。

## 9. 被否决方案

1. **整块选择 ours。** 否决原因：会丢失结构化 reasoning bridge、typed carrier records、server-tool response blocks、tool-result error semantics、tool choice 与 hosted-search response provenance。
2. **整块选择 theirs。** 否决原因：会恢复 budget-derived `ReasoningIntent`，丢失独立 effort、per-message control、target thinking profile、nested effort residual 与 profile observations。
3. **同时保留 `SemanticRequest.reasoning` 和 `thinking_effort`。** 否决原因：同一请求会有两个可分叉的 reasoning policy authority；merged `reasoning.py` 也不再提供旧类型与 `resolve`。
4. **同时保留 local 与 remote 两套 client-action classifier。** 否决原因：缺失 `tool_search_call.execution` 时两者给出相反 delivery policy，且 terminal facts 会出现两份可漂移来源。
5. **把 `output_config`、`reasoning` 或 `tool_choice` 留给普通 extensions。** 否决原因：跨格式时会静默丢掉已可建模的语义；same-format 时也会让 stale residual 覆盖 modelled value。
6. **随意调整 nested extensions、modelled writers 与 top-level extensions 的调用顺序。** 否决原因：nested residual 必须先合并、owned field 后覆盖；tool-choice renderer 又必须看见 extensions 中的 opaque same-format value，并在 foreign crossing 时主动拒绝。
7. **由响应体自行推断 hosted search 是否 expected。** 否决原因：同一个 `web_search_call` 可以来自请求映射或上游 unsolicited 行为，response body 没有请求 provenance。
8. **为修复 Chat writer 而恢复旧 `ReasoningIntent`。** 否决原因：这是用过时消费者反向决定新公共模型；正确做法是迁移唯一消费者，避免重新引入 budget→effort 推导。

## 10. 合并后建议验证

首先做旧 request-level API 残留检查：

```bash
rg --line-number '\bReasoningIntent\b|request\.reasoning\b|from app\.pipeline\.translation_driver\.reasoning import resolve' src tests
```

然后至少运行直接涉及本次接缝的测试：

```bash
uv run pytest \
  tests/unit/pipeline/translation_driver/test_translation_driver.py \
  tests/unit/pipeline/translation_driver/test_reasoning.py \
  tests/unit/pipeline/translation_driver/test_reasoning_bridge.py \
  tests/unit/pipeline/translation_driver/test_tool_choice.py \
  tests/unit/pipeline/translation_driver/test_openai_chat_completions.py \
  tests/unit/pipeline/test_response_observation.py \
  tests/unit/pipeline/delivery/test_responses_passthrough.py \
  tests/unit/observability/test_request_log.py
```

随后按项目规定运行：

```bash
uv run ruff check src tests
uv run pyright src tests
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

上述命令是合并后的建议验证，**本次只读调查没有运行它们，也不把它们冒充现有证据**。

## 11. 调查状态

- 源代码改动：无。
- Git index 改动：无。
- Commit：无。
- 测试执行：无；没有形成实际 merge candidate。
- 隔离 worktree 最终 `git status --short --branch` 仅输出分支标题，未出现工作树或 index 变更。
- 被否决方案：8 项，均已在第 9 节列明原因。
- 需要 merge 执行者额外处理的非 hunk 随动点：2 处旧 `request.reasoning` 引用，以及 contextual completion／response observation 的单一 classifier 收敛。

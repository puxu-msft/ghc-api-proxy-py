# Pipeline core 与 Responses passthrough merge 冲突调查

日期：2026-09-05

状态：只读调查完成，未实施 merge resolution

## 1．结论

当前 merge 不能按 ours 或 theirs 整体选边。应按三个相互独立的语义轴组合：

1. **Responses completion/status**：保留 ours `bb5783f` 的用户可见合同。`completed` 只有在 terminal `response.output` 分类完备且无 `required`／`unknown` client action 时才可显示为绿色；terminal snapshot 缺失、未知 action、`function_call` 或 `custom_tool_call` 都不能被“空 action”或普通绿色 `completed` 掩盖。
2. **Response observation/action**：保留 theirs `6200600d` 的 `ResponsesObserver`、`ResponseObservation`、`ClientActionObservation`、`basis` 和 per-attempt 原始上游观测链。它覆盖 streaming、buffered、failure、replacement attempt，明显比 ours 只挂在 `Terminal` 上的直连 streaming 记录更宽。
3. **Routing 与 translation target**：保留 theirs 的“路由选中的精确 `ModelDescriptor` snapshot”，再叠加 ours 的 `ThinkingTargetProfile`。不能回退到通过 `provider.describe(model_id)` 二次查询 descriptor。
4. **Request translation/tool semantics**：保留 ours 的 `source_headers`、thinking profile、conversion facts；同时保留 theirs 的 `tool_choice`、`HOSTED_WEB_SEARCH_EXPECTED`、`RESPONSE_CONVERSION_LOSSES`、prepared replay、prompt admission 和多 provider descriptor 传递。

这意味着当前四个文件之外还有必须同步的语义接缝。尤其不能把 `app.pipeline.delivery.assembling.ClientActionRequirement` 与 `app.pipeline.response_action.ClientActionRequirement` 两套同名 enum 原样并存并交叉使用。二者即使 `.value` 相同，`is` 比较也永远不相等，可能把所有 `NOT_REQUIRED` 都当成 client action。

结论权重：**足以据此实施 merge resolution**。依据是三方 blob、相关提交历史、当前 `origin/dotdev` living Spec 和实际调用链。尚未运行测试，因此不构成“merge 后已通过验证”的结论。

## 2．对象与证据边界

### 2.1 Merge 身份

- Base：`e1b2baa99637349d2f552343c57769a311bfb179`，`feat: notice a doubly-closed output item, and offer to settle upstream's drifting ids`
- Ours／`ORIG_HEAD`：`605d42bd85d6d25bc5e4b73dada727a893742527`
- Theirs／`MERGE_HEAD`：`8ac6522896cdd3a43d796c33999595c25b8f798b`
- Merge message：`Merge branch 'main' of gh_puxu-msft:puxu-msft/ghc-api-proxy-py`

### 2.2 Stage blobs

| 文件 | base `:1` | ours `:2` | theirs `:3` |
|---|---|---|---|
| `src/app/pipeline/delivery/formats/openai_responses_passthrough.py` | `06e0c6b143f8d1c94fa5fae8fd78388dc7b1d4e4` | `e9679b6bec6c71f52127137b73a9374628d93ecb` | `0c59df4fbadcc4e0b1a4c306fdfb2fb7bf154f35` |
| `src/app/pipeline/driver.py` | `0badbe7abaeaa46bb0926f623e719740e33f7812` | `57ab044454fa8a59a7d21a16ce3e3916400b0807` | `dbf4f0b74c253de7afb2f5e754d454f266d123cc` |
| `src/app/pipeline/routing.py` | `c10b93c7418bd041062098989d0be5e499606ad7` | `74bf9bae63a9f99bcccbdb72b39fb299099e7c2b` | `f02e885b76344aeee9272483d39e1895362844fa` |
| `tests/unit/pipeline/delivery/test_responses_passthrough.py` | `d46bddb183fd93773691fa4f5811e93ef823a39c` | `e21d2fe20007b611ee6c0a40a2ffbd4d7704982a` | `6823127985dbe267506cd72f6c2eb5f034b1f90c` |

### 2.3 调查方法与限制

受 harness 隔离限制，直接执行 `git -C /home/xp/src/ghc-api-proxy-py ...` 被拒绝。上述 stage SHA 由协调会话从主 checkout 提供；我在同一 repository object store 中逐一读取并比较了这些对象。主 checkout 的 `MERGE_HEAD`、`ORIG_HEAD`、`MERGE_MSG` 和冲突工作树文本则以绝对路径直接读取。

未修改任何源文件、Git 索引或工作树；调查用隔离 worktree 最终 `git status --short` 为空。未运行 Ruff、Pyright 或 pytest，因为主工作树仍处于未解决 merge，且本任务是只读调查。

## 3．权威合同与两边实现的关系

当前 `origin/dotdev` 为 `862b13748cefe3e27f8a95c7885cb3a4405345bc`。其中 `.dev/docs/direct-passthrough/spec.md` §7.1、§10 和 `.dev/docs/tui/spec.md` 明确规定：

- `client_action_requirement` 是 `required`／`not_required`／`unknown` 三态。
- buffering bool 是该三态的投影：只有 `not_required` 为 `false`，`required` 与 `unknown` 都为 `true`。
- 缺失或不可识别 discriminator 的 `tool_search_call`、`shell_call` 属于 `unknown`，因此 delivery 应释放。
- 最终 client-action 摘要的 authority 是 terminal `response.output`，不是 `output_item.done` 顺序或 done-side buffering bool。
- `client_action_classification_complete` 必须独立表达 terminal snapshot 是否完整。
- 用户于 2026-09-03 明确裁定 `completed + function_call/custom_tool_call` 不得显示为绿色。

因此 theirs `response_action.py` 当前两处行为已经落后于 living Spec：

- `tool_search_call` 缺失／未知 `execution` 返回 `UNKNOWN`，但 `delivery_required=False`。按当前 Spec 应为 `True`。
- `shell_call` 缺失／不可识别 `environment` 被判为 `REQUIRED`。按当前 Spec 应保留为 `UNKNOWN`，其 delivery projection 仍为 `True`。

另一方面，theirs 的 observation 架构比 ours 更完整：

- `RequestContext.begin_attempt()` 为每次 Responses attempt 建立独立 `ResponsesObserver`。
- streaming 在生产 assembler 前观察原始 `SseEvent`；buffered 和 HTTP error 观察原始 body bytes。
- replacement attempt 会清除前一次 response projection。
- `ResponseObservation` 保留 status、terminal event、usage、output items、reasoning、client-action basis、provider/tool usage 和 observation issues。
- 观测异常被包含，明确不参与 framing、retry 或 delivery control。

因此应保留 remote observer 作为 provider-side rich observation；但不能直接用它当前的 renderer 替换 local completion contract。当前 `format_response_observation()` 对任意 `completed` 先染绿，而且 `ResponseObservation.output_items` 会把 done-side draft 与 terminal body 合并，也没有 terminal snapshot completeness 字段。这不足以满足 local Spec 的 terminal-authority 与绿色判据。

安全的本轮组合是：

- 保留 ours 的 direct-stream `Terminal.terminal_status`、`Terminal.client_actions`、`client_action_classification_complete` 和其完成行优先级，确保已裁定行为不回归。
- 保留 theirs 的 `ResponseObservation` 作为更丰富、更宽范围的旁路记录。
- 两条记录共享一个 classifier authority，不能各维护一套 item taxonomy。
- 后续若要消除双 collector，应先给 `ResponseObservation` 增加“terminal output snapshot”及 completeness 的独立槽，再把完成行切过去；不能仅凭现有 `output_items` 替代。

## 4．逐 hunk 建议

当前四个目标文件共有 8 个标记冲突 hunk。

### 4.1 `openai_responses_passthrough.py` hunk 1：base taxonomy 的双边删除

位置：当前冲突文本约 58～87 行。

建议：删除 base `_ALWAYS_CLIENT_ACTION`／`_NEVER_CLIENT_ACTION`，不要在本文件恢复任何 taxonomy。保留：

- ours 的 `client_action_requirement` 与 `read_responses_client_actions` collector import；
- theirs 的 `classify_responses_client_action` import。

但 `openai_responses_actions.py` 不应继续持有自己的分类表。应改成薄 adapter／terminal snapshot collector，由 `app.pipeline.response_action.classify_responses_client_action()` 提供唯一分类答案。

同时应把 `ClientActionRequirement` 的唯一 enum 定义放在 dependency-leaf `response_action.py`，让 `assembling.py` 导入或 re-export。不要保留两个同名 enum。

### 4.2 `openai_responses_passthrough.py` hunk 2：`requires_client_action`

位置：当前冲突文本约 90～119 行。

建议采用 theirs 的 richer classifier 入口，但先把其 policy 修正为当前 Spec：

```python
def requires_client_action(item: dict[str, Any]) -> bool:
    return classify_responses_client_action(item).delivery_required
```

`response_action.py` 必须同步满足：

- unknown future item → `UNKNOWN`，`delivery_required=True`
- missing／unknown `tool_search_call.execution` → `UNKNOWN`，`delivery_required=True`
- missing／unknown `shell_call.environment` → `UNKNOWN`，`delivery_required=True`
- explicit client/local → `REQUIRED`，`True`
- explicit server/container → `NOT_REQUIRED`，`False`

`RESPONSES_DIALECT` 应保留 ours 已经被 generic engine 使用的三态入口：

```python
client_action_requirement=client_action_requirement
```

不能直接拿 theirs 的：

```python
requires_client_action=requires_client_action
```

因为当前 auto-merged `delivery/passthrough.py` 已把 `Dialect` 合同改成 `client_action_requirement`，并在按 `output_index` 合并 opening／closing item facts后才分类。这项 merge-before-classify 修复必须保留，否则 opening 缺 `execution` 会在 closing 明确 `server` 前先触发错误的 conservative release。

### 4.3 `openai_responses_passthrough.py` 无冲突标记但必须人工裁决的 `_read_terminal`

当前 Git 自动保留了 ours `_read_terminal` 的 terminal snapshot collector。建议本轮保留：

- `response.completed` 的 native status；
- terminal `response.output` 的 ordered typed actions；
- `client_action_classification_complete`；
- 其它 terminal 仍只走 legacy `read_responses_terminal()`。

理由：这是当前 living Spec 和用户裁定的直接实现，而 remote `ResponseObservation` 尚不能表达“terminal output snapshot 完备”与“done-side aggregate”之间的区别。直接删掉会让 direct Responses completion 再次出现“有 action 仍绿”或“缺 terminal output 被视作空集合”的回归。

同时保留 remote observer，但明确其当前作用是 rich provider observation，不替代这份 direct-stream display projection。

### 4.4 `driver.py` hunk 1：imports

位置：当前冲突文本约 9～15 行。

不能选单边。应合并为：

```python
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
```

并保留：

```python
from app.model_provider import ModelDescriptor, ModelProvider
```

理由：

- `Sequence`、`ConversionFact`、`SemanticRequest`、`TranslationRefused` 服务 ours 的 effort conversion facts。
- `deepcopy`、`ModelDescriptor` 服务 theirs 的 exact prepared replay、prompt admission 与 descriptor snapshot。
- `ModelProvider` 仍由 `_drive()` 和 routing 返回值使用。

### 4.5 `driver.py` hunk 2：`handle()` 的 request translation

位置：当前冲突文本约 205～224 行。

保留 ours `_translate_with_facts()`，但把 helper 参数从 `provider` 改为 `descriptor`：

```python
def _translate_with_facts(
    chain: Chain,
    context: RequestContext,
    route: Route,
    descriptor: ModelDescriptor,
    source_headers: Mapping[str, str],
) -> tuple[dict[str, Any], SemanticRequest]:
    target = translation_target(descriptor, chain.thinking_profiles)
    ...
```

调用应为：

```python
translated, semantic = _translate_with_facts(
    chain,
    context,
    route,
    descriptor,
    source_headers,
)
```

周边必须同时保留：

- 在 `shape_request()` 前读取 `source_headers = context.source_headers_for_translation()`；
- theirs 的 `descriptor = route.descriptor` 与 `None` guard；
- `CLIENT_SEARCH_TOOL`；
- `HOSTED_WEB_SEARCH_EXPECTED`；
- request-side conversion losses；
- 最后进入 theirs `_drive()`，从而保留 prompt admission、prepared replay 和 exact descriptor。

这不是任选其一。直接选 ours 会丢 prompt admission、replay 和 hosted web search；直接选 theirs 会丢 source headers、thinking profile 与拒绝路径上的 conversion facts。

### 4.6 `driver.py` hunk 3：`handle_count_tokens()` 入口

位置：当前冲突文本约 392～396 行。

建议顺序：

```python
_check_count_deadline(deadline_at)
source_headers = context.source_headers_for_translation()
provider, route = shape_request(chain, context)
```

之后保留 theirs 的 descriptor guard 与 `on_routed`。

先检查 deadline 是 theirs 的既有生命周期约束；随后在 `shape_request()` 过滤 client headers 前采样 source headers，是 ours 的 effort translation 约束。两者不冲突。

### 4.7 `driver.py` hunk 4：count translation

位置：当前冲突文本约 408～427 行。

同样调用统一 helper，并传 exact descriptor：

```python
translated, semantic = _translate_with_facts(
    chain,
    context,
    route,
    descriptor,
    source_headers,
)
```

随后保留 theirs 的 async local token worker、deadline checks、descriptor-based provider count、multiplier 和 response byte observation。

Count 路径不能保留 theirs 的裸 `chain.translators.translate(...)`，否则 normal request 与 count request 对同一 body 的 effort/source-header 语义会再次分叉。

### 4.8 `routing.py` hunk：`translation_target`

位置：当前冲突文本约 376～438 行。

保留 ours 的 `compile_thinking_profiles()` 和 `select_thinking_profile()`，但函数输入采用 theirs 已由 routing 选定的 descriptor：

```python
def translation_target(
    descriptor: ModelDescriptor,
    thinking_profiles: CompiledThinkingProfiles,
) -> TranslationTarget:
    selected = select_thinking_profile(thinking_profiles, descriptor.id)
    pattern, profile = selected if selected is not None else ("", None)
    return TranslationTarget(
        model_id=descriptor.id,
        reasoning_efforts=descriptor.reasoning_efforts,
        thinking_profile=profile,
        thinking_profile_pattern=pattern,
    )
```

imports 应保留 `re`、`ThinkingTargetProfileConfig`、`CompiledThinkingProfiles`、`ThinkingTargetProfile`、`ModelDescriptor`，并删除仅为旧签名存在的 `ModelProvider`。

原因：

- `descriptor.reasoning_efforts` 必须来自 `decide_route()` 当时实际选中的 provider/catalog snapshot。
- `thinking_profile` 仍按 resolved `descriptor.id` 选择最后一个 regex fullmatch。
- 二次 `provider.describe(model_id)` 会在 dynamic catalog refresh 后得到另一个答案，使 routing、translation 与 prompt admission 使用不同 snapshot。
- 多 provider 下，同一 model id 不保证具有相同能力；route 已经确定 provider 与 descriptor，translation 不应重新回答一次。

`.dev/docs/anthropic-responses-bridge/plan-effort-translation.md` 当前仍写旧签名 `translation_target(provider, model_id, thinking_profiles)`，实施此组合时必须同步修订 living plan；不能让已知过时的签名继续作为权威文本。

### 4.9 `test_responses_passthrough.py` hunk：imports

位置：当前冲突文本约 10～18 行。

应取并集：

```python
from app.pipeline.delivery.assembling import ClientAction, ClientActionRequirement, Terminal
from app.pipeline.delivery.blocks import BlockBuffer, BufferCapExceeded, DeliverySession
```

并保留 `client_action_requirement` import，前提是它已改为共享 classifier 的 adapter。

测试内容建议：

- 保留 ours 的三态 classifier、unknown projection、merge-before-classify、present-empty item、terminal output authority、classification completeness 和 contextual status tests。
- 保留 theirs 的 `DeliverySession` atomic `until-tool-use` test 和 generic close-batch integration test。
- 更新 remote `tests/unit/pipeline/test_response_observation.py` 中两组过时预期：missing `tool_search_call.execution` 的 `delivery_required` 应为 `True`；missing／未知 shell discriminator 的 requirement 应为 `UNKNOWN`。
- `test_a_batch_merges_an_items_facts_before_projecting_the_policy()` 的三个结果应继续是 client=`True`、server=`False`、missing=`True`。这三个控制共同证明既执行了 merge，又没有把结果写成常量。
- 不要仅保留 remote 的旧 adapter table。其 missing `tool_search_call` 预期 `False` 与 current Spec §7.1 正面冲突。

## 5．必须同步检查的非目标文件

虽然用户点名四个文件，以下文件已经被 Git 自动合并或另有冲突，若不联动处理，四个 hunk 即使去掉 marker 也不会形成一致系统：

1. `src/app/pipeline/response_action.py`
   - 作为唯一 Responses action classifier。
   - 修正 unknown projection 和 shell discriminator 语义。
   - 保留 `basis`，不要把 unknown policy fallback伪装成已确认 client action。

2. `src/app/pipeline/delivery/assembling.py`
   - 保留 ours `ClientAction`、Terminal contextual fields，直至 observer 拥有独立 terminal snapshot。
   - `ClientActionRequirement` 应从 `response_action.py` 导入／re-export，不能定义第二个 enum。
   - 保留 theirs `REDACTED_THINKING` 与 `CHAT_COMPLETIONS`。

3. `src/app/pipeline/delivery/formats/openai_responses_actions.py`
   - 保留 terminal snapshot collector。
   - 删除本地 taxonomy，委托 `response_action.classify_responses_client_action()`。

4. `src/app/pipeline/delivery/passthrough.py`
   - 保留 ours 的按 item index 合并 facts 后分类、present-empty 与 absent 分离。
   - 保留三态 `Dialect.client_action_requirement`，并确保 enum 与 central classifier 是同一类型。

5. `src/app/observability/request_log.py`
   - 完成行顺序应为：count provider → direct-stream `terminal_status` contextual renderer → generic `response_ending` → legacy stop reason。
   - 不能直接采用 remote 的 `response_ending` 优先级，因为它当前会把所有 `completed` 先染绿。
   - 保留 remote rich response observation 输出，并保留 ours conversion facts。

6. `src/app/observability/request_trace.py`
   - 保留 local terminal status/actions/completeness 与 conversion facts。
   - 保留 remote `response_observation`、token admissions、timing 和 `absorb_response()`。
   - `absorb_response()` 不应清除 direct terminal snapshot slots；它们回答 terminal-authoritative display，remote fields回答 provider-wide observation。

7. `src/app/pipeline/translation_driver/semantic.py`、`anthropic_messages.py`、`openai_responses.py`
   - local `ThinkingEffortIntent`／profiles／nested extensions／conversion facts 与 remote `ToolChoiceIntent`／reasoning bridge／hosted search 都要并存。
   - `TranslationRefused.facts` 应保留默认空 tuple，使 remote 新增的 tool-choice refusal 无需逐处改构造函数，同时 local `_translate_with_facts()` 能记录拒绝前 facts。
   - `SemanticRequest` 同时保留 `thinking_effort` 与 `tool_choice`；不能二选一。

## 6．提交历史

### 6.1 Ours

- `4b7d74f56b8b0264b481a2fefe275a233979fbb2` — `feat: translate effort between Messages and Responses`
  - 修改 `driver.py`、`routing.py`。
  - 引入 thinking profiles、source-header snapshot、conversion facts，并让 send/count 共用 translation helper。
- `bb5783f17f8f21017010a14d00b762b49ee6cc13` — `feat: report contextual Responses completion status`
  - 修改 passthrough source/test、Terminal、trace、request log。
  - 实现 terminal `response.output` authority、三态 action、classification completeness 和 contextual coloring。
- `605d42bd85d6d25bc5e4b73dada727a893742527` — ours head；该顶端提交本身只更新文档，不是这些代码冲突的来源。

### 6.2 Theirs

- `6200600d756803ac15a7bdd0f90db303ca605188` — `feat: preserve Responses facts through observability`
  - 引入 `response_action.py`、`response_observation.py`、`request_completion.py` 和原始 provider-side observation 链。
- `c27da611e9439f38e8df427bb4182909244b0203` — `merge: reconcile Responses delivery changes`
  - parents 为 `d9535032c8b35554b90a1f268d8d659bb62f3873` 与 base `e1b2baa99637349d2f552343c57769a311bfb179`；说明 theirs 已先把 response observation 与 base 的 direct delivery 做过一次整合。
- `1389108e614b797da067213cc67062d4d444c143` — `feat: add atomic delivery batches`
  - 增加 `DeliverySession` test。
- `c5f8a669e5bc519795a481d84d0b93e87b8f8dc4` — `fix: stabilize response stream ids by default`
  - passthrough doc/default 更新，应保留 theirs 的“default on”表述。
- `18347af55137b87d5d7e8680c818a3c4bb3cc3af` — `feat: restore hosted web search response blocks`
  - 增加 `HOSTED_WEB_SEARCH_EXPECTED` request→response context。
- `831885c98d480b03d05929f2e6ff9080492482c7` — `feat: reject oversized responses prompts before send`
  - `translation_target(descriptor)`、descriptor-based admission。
- `8d957389eb738cd9b0e9d4cf542b4707bb2c5cab` — `fix: stabilize prompt admission boundaries`
  - 增加 prepared replay 和 `_drive()` 共用路径。
- `998d0f717adf3493958035b2eda94bdc5ec14bbe` — `feat: configure count-only local estimate multiplier`
- `9a1ffc3c5f2a6e27ba5c97ab1589019bba9eca88` — `perf: offload count token estimation without blocking dispatch`
- `3ec2ed85e147f107098a502e8ee90032795b39e0` — `fix: preserve tool semantics across translation writers`
  - 虽未直接修改四个目标文件，却决定 `SemanticRequest.tool_choice`、writer 行为和 driver helper 必须怎样组合。
- `11bc4224c57df2b6460275c61b2282ea366b1341` — `feat: bind model descriptors to providers`
  - 是 exact descriptor／多 provider 语义的相关基础。
- `8ac6522896cdd3a43d796c33999595c25b8f798b` — theirs head。

## 7．被否决方案及原因

1. **否决：四个文件全部选 ours。**
   - 会丢掉 `ResponsesObserver` 接线、prepared replay、prompt admission、hosted web search response context、async count estimator 与 exact descriptor snapshot。
   - 多 provider／dynamic catalog 下 translation 可能重新查询到与 routing 不同的能力答案。

2. **否决：四个文件全部选 theirs。**
   - 会丢掉 source headers、thinking profiles、conversion facts 和当前用户已裁定的 contextual `completed` 行为。
   - theirs 当前把 missing `tool_search_call.execution` 的 delivery 判为 false，并把所有 `completed` 先染绿，违反 current direct-passthrough／TUI Specs。

3. **否决：保留两套 `ClientActionRequirement` enum，再让模块间直接传值。**
   - 两个 `StrEnum` 类的同值成员不是同一对象；现有代码大量使用 `is`／`is not`。最坏结果是 `NOT_REQUIRED` 被判作 action，`until-tool-use` 在首个普通 item 即释放。

4. **否决：只把 remote `.requirement` 桥接给 local generic engine，不同步 `.delivery_required` 语义。**
   - 当前 remote 特意让两种 `UNKNOWN` 产生相反 delivery 结果，而 current Spec 已裁定所有 unknown 都投影为 true。保留这种分叉会让 observer、public adapter 与 buffer 给出不同答案。

5. **否决：丢掉 ours 的 merge-before-classify，恢复逐事件 `any()`。**
   - opening `tool_search_call` 可能缺 `execution`，closing 才给出 `server`；逐事件分类会让 opening 的 unknown 抢先触发 release，无法被 closing 的 server fact纠正。

6. **否决：保留 `translation_target(provider, model_id, profiles)`。**
   - 它二次读取 live catalog；route、translation、admission 不再共享同一 descriptor snapshot。该问题在 catalog refresh 与多 provider 下具有真实可观察后果。

7. **否决：只保留 remote `format_response_observation()` 并删除 local terminal snapshot。**
   - remote observation 当前没有 terminal snapshot completeness，且 merged `output_items` 会继承 done-side fields；无法满足 terminal `response.output` authority、missing-output unknown 与 action-aware completed color。

8. **否决：把 local completion facts 反向用于 retry、framing、continuation 或 response conversion。**
   - local Spec 明确这些是 observability/display facts；delivery 的 `_saw_client_action` 与 terminal snapshot action list回答不同问题，不能相互替代。

未采纳路线均已列明，无遗漏的纯推理否决项。

## 8．验证与交接

本次只读调查未运行 Ruff、Pyright 或 pytest，因为主工作树处于未解决 merge，且任务明确禁止修改索引／工作树。建议完成 resolution 后至少运行：

- `uv run ruff check src tests`
- `uv run pyright src tests`
- 针对 passthrough、response observation、request log、routing、translation driver、pipeline integration 的相关测试
- 最终完整 `uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80`

尤其要保留以下可判别控制：

- terminal `output=[]` 才能确认无 action；
- terminal output 缺失／错误类型不得绿；
- unknown item 不得伪装 absent；
- done-side 与 terminal snapshot 故意矛盾时，display 必须采用 terminal snapshot；
- opening 缺 execution、closing 为 server/client/missing 的三联 batch；
- 同 model id、不同 provider descriptor；
- catalog snapshot 在 routing 后变化，translation 仍使用 route descriptor；
- thinking profile 与 tool choice／hosted search 同时存在的请求。

收口判断：本轮只写了这份用户要求的调查报告；无源代码、Git 索引或工作树状态变更，无清理／提交事项。该报告属于非平凡 merge 建议，协调会话应在实际改动后安排独立 review。

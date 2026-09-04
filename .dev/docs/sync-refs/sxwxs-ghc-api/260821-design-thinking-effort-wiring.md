# Anthropic `thinking` 到 OpenAI Responses `reasoning.effort` 的活链路接线方案

## 摘要

推荐采用“显式、协议中立的 `ReasoningIntent` + 从 legacy 提升出的共享纯策略 + resolved model 的能力事实”这一组合，而不是把 Anthropic 原始字典藏进 `extensions`，也不应让活链路直接 import `app.protocols.anthropic_responses`。这个组合改动面比“加一个 key”大，因为当前活链路的 `ModelDescriptor` 丢掉了模型目录中的 reasoning 能力，`TranslatorRegistry.translate` 也没有传入 resolved target capabilities 的接口；但这些改动把能力来源、语义意图和 wire rendering 分开，能确保五个目标档位每次都经过目标模型的 `supported_efforts` 查表，并能让 `count_tokens` 与真实发送走同一决策。判断权重：**强到可直接采纳**。依据是 `GithubCopilotProvider.replace_catalog`、`ModelDescriptor`、`TranslatorRegistry.translate`、`SemanticRequest`、`from_anthropic_messages` 与 `to_openai_responses` 的当前依赖和数据流。

当前录制证据能证明两件事：真实 Copilot `/models` 目录为 Responses 模型发布了逐模型的 `reasoning_effort` 枚举；真实 `/responses` 成功响应会回显规范化后的顶层 `reasoning` 对象。它不能证明 `{"reasoning":{"effort":X,"summary":"auto"}}` 的每个 `X` 都已由本仓 cassette 的请求侧逐值实测，因为 cassette 有意只保存 request digest、model 与 stream，不保存 request body。事实权重：**强到可直接采纳**。证据是 `RecordingTransport` / `Cassette`（`tests/int/recorded/cassettes.py`）、`SCENARIOS`（`tests/int/recorded/record_cassette.py`）、`messages_body`（`tests/int/test_recorded_upstream.py`）及 `request.shape` / `response.chunks`（`tests/int/cassettes/anthropic_to_responses_stream.json`）。

阈值、`disabled` 的降级、能力缺席时 drop 还是 reject、`adaptive` 的固定档位、`summary` 是否发送以及是否暴露配置项都不是现有证据能替用户决定的产品合同。本文把它们列为未决项，不把第三方项目或 legacy 测试 fixture 的数值冒充本项目裁决。

## 1. 调研范围与证据分级

本报告基于 2026-08-21 当前工作树的 `main` 分支，只读源码、测试、cassette 与 `.dev/docs/`，没有发真实请求，也没有修改源文件。工作树有并行会话的既有改动；本文只引用本任务相关文件的当前磁盘内容。事实权重：**强到可直接采纳**。证据是本次 `git status --short --branch` 的输出及本文实际操作范围。

证据按下列层次使用：

1. **录制证据**：`tests/int/cassettes/*.json` 中 `source: live-recording` 的真实 Copilot 响应、录制脚本固定的输入场景，以及由历史库提取的真实终局帧。这一层可以证明“该次真实交换实际出现了什么”，但 request body 没有落盘时不能反推它精确发送了什么。
2. **代码合同**：生产源码与测试说明“项目打算发送、接受或拒绝什么”。它能证明本地行为，不能单独证明 Copilot 接受该 wire shape。
3. **既有结论**：`.dev/docs/` 的报告可提供已经核对过的上下文；凡影响本方案的结论都回到对应源码或 cassette 交叉核对。

上述分级判断权重：**强到可直接采纳**。依据是 `request_shape` 的实现与注释（`tests/int/recorded/cassettes.py`）、`test_the_cassette_carries_nothing_that_identifies_the_account` 和 `test_a_request_for_something_else_is_not_served_this_recording`（`tests/int/test_recorded_upstream.py`），以及《PoC：续写请求能否原样回传加密 reasoning》的“现有 cassettes 无法提供 body 证据”结论（`.dev/docs/tmp/260821-poc-continuation-reasoning-echo.md`）。

## 2. 当前活链路、legacy 归属与 import 方向

### 2.1 活链路上的缺口

| 事实 | 证据 | 权重 |
|---|---|---|
| `from_anthropic_messages` 没有认领顶层 `thinking`，它进入 `SemanticRequest.extensions`。 | `_PASSTHROUGH_KEYS` 与 `from_anthropic_messages`，`src/app/pipeline/translation_driver/anthropic_messages.py`。 | **强到可直接采纳** |
| 跨 `anthropic-messages` → `openai-responses` 时，`SemanticRequest.extensions_for` 整体丢弃 source-format extensions，并记录 `EXTENSIONS_NOT_CARRIED`。 | `SemanticRequest.extensions_for`，`src/app/pipeline/translation_driver/semantic.py`。 | **强到可直接采纳** |
| `to_openai_responses` 当前没有生成顶层 `reasoning`，只写 model、input、instructions、tools、stream、max_output_tokens、temperature 与允许回放的 extensions。 | `to_openai_responses`，`src/app/pipeline/translation_driver/openai_responses.py`。 | **强到可直接采纳** |
| `handle` 在完成 translation 后才把 payload 的 model 改成 resolved model；translator 本身既拿不到 resolved `ModelDescriptor`，也拿不到目标模型的 reasoning 能力。 | `shape_request` 与 `handle`，`src/app/server/handler.py`；`TranslatorRegistry.translate`，`src/app/pipeline/translation_driver/registry.py`。 | **强到可直接采纳** |
| `GithubCopilotProvider` 保存完整 `raw_catalog`，但 `replace_catalog` 投影出的 `ModelDescriptor` 只有 endpoint、unknown endpoint 与 request headers，reasoning capability 在活链路的路由对象中消失。 | `GithubCopilotProvider.raw_catalog` / `GithubCopilotProvider.replace_catalog`，`src/app/model_provider/github_copilot.py`；`ModelDescriptor`，`src/app/model_provider/types.py`。 | **强到可直接采纳** |

判断：因此这不是只改两个 translator 的小补丁。若 effort 必须按 resolved model 的能力位查表，至少还要补一条“目录能力 → `ModelDescriptor` → translation invocation → Responses writer”的数据通道。判断权重：**强到可直接采纳**。依据是上表四个数据断点。

### 2.2 `responses_anthropic.py` 与 `anthropic_responses.py` 的真实归属

`src/app/protocols/anthropic_responses.py` 是 legacy 请求方向的 Anthropic Messages → Responses converter。其生产调用方是 `AnthropicClient._send_responses`，位于 `src/app/anthropic/client.py`；`AnthropicClient.execute` 再导入 legacy `app.pipeline.executor`。能力事实 `ReasoningCapabilityFacts` / `ReasoningEffortBand`、`_RequestConverter._convert_reasoning` 和 `convert_messages_request_to_responses` 都在这棵请求方向模块里。事实权重：**强到可直接采纳**。证据是这些符号的定义与调用关系。

`src/app/protocols/responses_anthropic.py` 是 Responses → Anthropic 的完整响应与 usage converter，确实被两条链共享：活链路的 `from_openai_responses_response` / `_anthropic_usage`（`src/app/pipeline/translation_driver/responses.py`）和 `ResponsesAssembler._anthropic_usage`（`src/app/pipeline/delivery/assembler.py`）都直接 import 它。事实权重：**强到可直接采纳**。证据是上述 import 与调用符号。

但当前共享响应模块又从 legacy 请求模块 import `ToolNameMapper`。 fresh interpreter import `app.server.pipeline_app` 的本次探针同时加载了 `app.protocols.responses_anthropic` 和 `app.protocols.anthropic_responses`，而没有加载 `app.anthropic.client`、`app.pipeline.executor`、`app.server.app_factory` 或 `app.routes.*`。事实权重：**强到可直接采纳**。证据是 `ToolNameMapper` import（`src/app/protocols/responses_anthropic.py`）与本次 `uv run python` fresh-import 探针。

判断：活链路**目前已经间接拖入** `app.protocols.anthropic_responses`，但这不是继续让 active request writer 直接依赖 legacy converter 的理由；相反，它暴露了 `ToolNameMapper` 也应在后续独立清理时移到共享 leaf 的既有耦合。直接复用 `_RequestConverter._convert_reasoning` 会把 Anthropic Pydantic request、orjson、legacy conversion facts 与工具映射一起留在 active import closure，且要求把 active `SemanticRequest` 再倒回 legacy `MessagesRequest`，依赖方向错误。判断权重：**强到可直接采纳**。依据是 `app.protocols.anthropic_responses` 的模块级 imports、`_RequestConverter` 构造参数和 `SemanticRequest` 的中心层职责。

架构守卫的当前结果为 22 passed。`test_the_new_chain_does_not_drag_in_the_existing_one` 禁止 active app import `app.server.app_factory`、`app.pipeline.executor` 和 `app.routes.*`；`test_the_typed_kernel_is_a_leaf` 禁止 typed content kernel 反向 import `app.anthropic`、`app.openai`、`app.upstream` 或 `app.routes`。事实权重：**强到可直接采纳**。证据是 `tests/unit/test_module_boundaries.py`、`tests/unit/test_imports.py` 与本次 `uv run pytest tests/unit/test_module_boundaries.py tests/unit/test_imports.py --quiet`。本文所有推荐都保持这些断言，不建议放宽。

## 3. 上游到底接受什么

### 3.1 有录制证据的能力枚举

`anthropic_to_responses_stream.json` 中 `/models` interaction 标为 `source: live-recording`，由 41 个保留原始 chunk boundary 的 chunk 拼出真实模型目录。下面只列目录中广告 `/responses` 的模型；相同枚举合并展示。

| 真实目录中的 Responses 模型 | `capabilities.supports.reasoning_effort` | 与 budget 相关的目录字段 | 证据权重 |
|---|---|---|---|
| `gpt-5.3-codex` | `low, medium, high, xhigh` | `min_thinking_budget` / `max_thinking_budget` 均缺席 | **强到可直接采纳** |
| `gpt-5.4-mini`、`gpt-5.4`、`gpt-5.5` | `none, low, medium, high, xhigh` | 两个 budget limit 均缺席 | **强到可直接采纳** |
| `gpt-5.6-luna`、`gpt-5.6-sol`、`gpt-5.6-terra` | `none, low, medium, high, xhigh, max` | 两个 budget limit 均缺席 | **强到可直接采纳** |
| `grok-4.5`、`mai-code-1.1-flash`、`mai-code-1-flash-picker`、`gpt-5-mini` | `low, medium, high` | 两个 budget limit 均缺席 | **强到可直接采纳** |
| `grok-4.6` | `low, medium, high, xhigh` | 两个 budget limit 均缺席 | **强到可直接采纳** |

证据：`response.chunks` 中真实 `/models` body（`tests/int/cassettes/anthropic_to_responses_stream.json`），由 `GithubCopilotProvider.replace_catalog` 当前解析 endpoint；本次只读脚本对 chunks 顺序拼接后用 JSON parser 提取，未对内容做猜测。

判断：模型目录中的 effort list 足以作为“这个 resolved model 允许 writer 选择哪些名称”的能力位，并且明确否定了“所有 Responses 模型都有 low/medium/high/xhigh/max”的假设。判断权重：**强到可直接采纳**。依据是上表的逐模型差异。

判断：目录**不能**决定 `budget_tokens` 的五档阈值，也不能提供 Responses 模型的合法 budget range，因为这些模型没有发布 `min_thinking_budget` / `max_thinking_budget`。Claude `/v1/messages` 模型在同一目录发布了 1024/32000，但把另一 endpoint、另一模型族的限制借给 Responses target 没有依据。判断权重：**强到可直接采纳**。依据是同一份真实目录中两类模型字段的对照。

### 3.2 有录制证据的 `reasoning` 响应形状

固定场景 `SCENARIOS["anthropic_to_responses_stream"]` 发送 `gpt-5.5`、`max_tokens: 64`、`stream: true` 和一句 PONG prompt，没有顶层 `thinking`。对应真实 `/responses` 成功流的 `response.created` / `response.in_progress` 回显：

```json
{"reasoning":{"context":"current_turn","effort":"medium","mode":"standard","summary":null}}
```

事实权重：**强到可直接采纳**。证据是 `SCENARIOS`（`tests/int/recorded/record_cassette.py`）、`messages_body`（`tests/int/test_recorded_upstream.py`）以及 `/responses` 的 `response.chunks`（`tests/int/cassettes/anthropic_to_responses_stream.json`）。这证明“省略 request reasoning 时该次 gpt-5.5 请求被接受，并被上游规范化为 medium”，不证明 request 曾发送 medium。

`responses_web_search_stream.json` 的真实 gpt-5.5 成功流也回显同一 `current_turn / medium / standard / null` 形状。`history_responses_stream.json` 的历史派生流回显 `effort: high`，但 request shape 为空，无法证明当时 request body 的精确 spelling。事实权重：前者 **强到可直接采纳**；后者 **是个倾向、需更多样本**。证据是各 cassette 的 `request.shape` 与 `response.chunks`。

现有历史终局帧还记录了 `{"reasoning":{"context":"all_turns","effort":"high","mode":"standard","summary":"detailed"}}`，并有多个 `type: reasoning` output item，每项可含 summary 与 `encrypted_content`。事实权重：**强到可直接采纳**，但只对该真实历史响应形状负责。证据是《真实历史帧与错误体探针》中的完整终局快照（`.dev/docs/tmp/260821-probe-history-error-frames.md`）。

### 3.3 只有代码合同、尚非本仓录制请求证据的部分

| 本地合同 | 代码证据 | 能支持的结论 | 权重 |
|---|---|---|---|
| legacy writer 对 enabled/adaptive 生成 `{"reasoning":{"effort":...,"summary":"auto"}}`。 | `_RequestConverter._convert_reasoning`，`src/app/protocols/anthropic_responses.py`。 | 项目已有这一 request shape 与验证逻辑。不能单凭代码宣称 Copilot 已逐值接受 `summary: auto`。 | **强到可直接采纳**（仅对本地行为） |
| legacy unit tests 使用 `low / medium / high` 和 fixture 阈值 4096/16384。 | `REASONING_CAPABILITIES` 与 reasoning tests，`tests/unit/anthropic/test_anthropic_responses_request.py`。 | 算法边界有测试；fixture 不是上游合同，也不是本项目已裁定阈值。 | **强到可直接采纳**（算法），阈值 **仅存档、不据以决策** |
| legacy route tests 断言 `summary: auto` 与 effort。 | reasoning route tests，`tests/int/test_anthropic_responses_route.py`。 | legacy app 的集成接线被测试；测试 target 是 harness，不是 live Copilot。 | **强到可直接采纳**（本地接线），上游接受性 **仅存档、不据以决策** |
| `ModelSupports` 能解析 `adaptive_thinking`、budget limits 和 `reasoning_effort`。 | `ModelSupports`，`src/app/models/capabilities.py`。 | legacy typed catalog 有字段容器；它不自动让 active provider 暴露这些字段。 | **强到可直接采纳** |
| legacy production capability extraction 对多 effort 模型不建立 bands；只有恰好一个 effort 时建立 open-ended band，并只在目录显式声明 adaptive 时把该唯一 effort 作为 adaptive effort。 | `AnthropicClient._reasoning_capabilities`，`src/app/anthropic/client.py`。 | legacy converter 算法完整且有测试，但生产 capability assembly 不能直接为当前多档 Responses 模型给出 budget→effort mapping。 | **强到可直接采纳** |

关键判断：可以复用 legacy 的“严格验证、能力交集、范围检查、band selector”思想和测试结构，但不能把 legacy 当前 production `ReasoningCapabilityFacts` 原样接进活链路后声称完成；对真实 Responses 目录，它会因 budget limits 未知、bands 为空、adaptive effort 为空而拒绝 enabled/adaptive。判断权重：**强到可直接采纳**。依据是 `AnthropicClient._reasoning_capabilities` 与真实目录表的组合。

关键判断：`disabled` 不能沿用 legacy 的“返回 `None` 即不写 reasoning”作为无损映射。真实 gpt-5.5 cassette 已证明省略 reasoning 会得到 medium 默认值，所以“disabled → omit”至少对该模型不是 disabled。判断权重：**强到可直接采纳**。这是第三方方案 `disabled → none` 值得保留的语义动机，但 `none` 缺席时如何处理仍需用户裁决。

## 4. 设计共同约束

无论选哪个候选，以下约束都应成立：

1. writer 最终返回的每一个 effort 字符串都必须来自 resolved model 的 `supported_efforts`；`low`、`medium`、`high`、`xhigh`、`max` 五个 enabled 档位以及 `disabled` 的 `none` 都不能绕过查表。判断权重：**强到可直接采纳**。依据是真实目录中 effort 集合按模型变化，以及第三方实现遗漏三档检查的已知反例。
2. 不以模型名 prefix 猜 effort 能力。能力必须来自 provider 的该次目录快照；缺席与空列表不能扩张为“随便试”。判断权重：**强到可直接采纳**。依据是 `ModelDescriptor` / `resolve_endpoints` 已采用的 fail-closed 设计，以及真实目录差异。
3. 选择逻辑不能使用 `supported_efforts[-1]` 表示“最高档”，除非项目另行把目录顺序写成合同。更稳妥的做法是用本项目明确裁定的 canonical lattice 与 capability set 求交。判断权重：**强到可直接采纳**。依据是列表当前看似升序，但 `ModelSupports` 和 provider 均未声明顺序语义。
4. invalid `thinking` 是 client error，应用 `TranslationRefused` 携带 `code` 与 `field_path`，不应伪装成 loss 后继续。无法精确映射但获准降级的合法 intent 才进入 `LossCode`。判断权重：**强到可直接采纳**。依据是 `TranslationRefused` 与 `Conversion` 在 `src/app/pipeline/translation_driver/semantic.py` 中的既有职责区分。
5. `reasoning.effort` 是 request generation policy；assistant 历史中的 `thinking` / Responses `reasoning` item 是 continuation state。两者应分字段、分类型，不能把 request intent 塞进 `ContentBlock.reasoning`。判断权重：**强到可直接采纳**。依据是 `ContentBlock` / `ReasoningState`（`src/app/pipeline/translation_driver/content.py`）、`SemanticRequest` 与 `_reasoning_item` 当前职责。

## 5. 候选方案

### 候选 A：在 `SemanticRequest` 上增加 Anthropic-shaped 原始 `thinking` 字段

**形态**：把 `thinking` 加入 `_PASSTHROUGH_KEYS`，由 `from_anthropic_messages` 显式读到 `SemanticRequest.thinking: Mapping[str, Any] | None`；`to_openai_responses` 再解析 type/budget 并输出 `reasoning`。这里“passthrough”只表示 reader 已认领，不表示原字典直接发给 Responses。

**改动文件**：

- `src/app/pipeline/translation_driver/anthropic_messages.py`：认领与复制 `thinking`。
- `src/app/pipeline/translation_driver/semantic.py`：增加 raw field；必要时增加 reasoning loss code。
- `src/app/pipeline/translation_driver/openai_responses.py`：wire validation 与 mapping。
- `src/app/model_provider/types.py`、`src/app/model_provider/github_copilot.py`：把 resolved model effort list 带出目录。
- `src/app/pipeline/translation_driver/registry.py`、`src/app/server/handler.py`：把 target capability 交给 writer。
- `tests/unit/pipeline/translation_driver/test_translation_driver.py`、`tests/unit/model_provider/test_github_copilot_provider.py` 或现有等价 provider test：档位、非法值与能力查表。
- `tests/int/test_pipeline_app.py`：断言 mock upstream 实际收到 reasoning；同时覆盖 `count_tokens`。

**跨格式行为**：Anthropic → Responses 映射；Anthropic → Anthropic 可重建原字典。Responses → Anthropic 没有对称语义，除非再加一个 OpenAI-shaped raw field，因此中间表示开始知道 Anthropic wire shape。

**与 `LossCode` 的关系**：精确的 `disabled → none` 可不记 loss；budget 离散化、adaptive 固定档及 capability fallback 应至少记录 `REASONING_INTENT_APPROXIMATED`；获准 drop 时记录 `REASONING_INTENT_NOT_CARRIED`；非法结构直接 `TranslationRefused`。

**对 `count_tokens` 的影响**：仍必须拿到 target capability 才能复用真实发送的转换；`estimate_responses_input` 不读取顶层 `reasoning`，数值应不变。若 send policy 是 reject，count 应作同样 reject，否则它回答的是一个不可发送 request 的大小。

**优点判断**：比 extensions 特判清楚，改动相对小。权重：**强到可直接采纳**。

**缺点判断**：`SemanticRequest.thinking` 以 source protocol 命名，违背 intermediate protocol-neutral 的长期方向；OpenAI input 的 explicit effort 无法对称表达。权重：**强到可直接采纳**。

**总评**：可作为快速 slice，但不是最佳终态。权重：**是个倾向、需更多样本**；是否接受源协议字段取决于本轮对架构债的容忍度。

### 候选 B：在 `SemanticRequest` 上增加协议中立的 `ReasoningIntent`

**形态**：新增 leaf 类型，例如：

```python
@dataclass(frozen=True, slots=True)
class ReasoningIntent:
    mode: Literal["disabled", "adaptive", "budget", "effort"]
    budget_tokens: int | None = None
    effort: str | None = None
```

`from_anthropic_messages` 把 `{type: disabled}`、`{type: adaptive}`、`{type: enabled, budget_tokens: N}` 解析成 intent；未来 `from_openai_responses` 可把 `reasoning.effort` 解析成 `mode="effort"`。writer 按目标协议渲染，而不是跨层保存 wire dict。

**改动文件**：候选 A 的全部文件；此外建议把 `ReasoningIntent` 与其结构不变量放在 `src/app/pipeline/translation_driver/semantic.py`，或单独放在不 import codec 的 `src/app/pipeline/translation_driver/reasoning.py`。`from_openai_responses` 是否在本 slice 认领顶层 `reasoning` 可分成后续小 patch，但 field 本身应能表达 explicit effort，避免一开始就锁成 Anthropic-only。

**跨格式行为**：

- Anthropic → Responses：budget/adaptive/disabled 经 target capability resolver 变成 effort。
- Anthropic → Anthropic：按 intent 无损重建已知合法三态；未知 extras 仍依既有 extensions 机制。
- Responses → Responses：explicit effort 可无损保留。
- Responses → Anthropic：explicit effort 没有精确 budget 反解；应拒绝、按用户裁决降级为 adaptive，或记录 approximation，不能编造一个精确 budget。

**与 `LossCode` 的关系**：intent 解析成功本身不是 loss；离散化或 fallback 是 approximation；完全不能承载才是 not-carried；malformed/unknown mode 是 refusal。建议 resolver 返回带 disposition 的结果，而不是 writer 先记账再发现没有输出，以避开第三方项目“mark 了但没映射”的反面样本。

**对 `count_tokens` 的影响**：与真实 send 共用同一个 intent 和 resolver。顶层 reasoning policy 不计入 input estimator；历史 `input` 中的 reasoning item 仍由 `_responses_item_text` 的 JSON fallback 计入，二者不会混淆。

**优点判断**：边界最清楚，后续能支持 Responses inbound，request intent 与 response carrier 不混淆。权重：**强到可直接采纳**。

**代价判断**：需要改变 translator invocation，使 writer 看到 resolved target capability；改动不再是单文件补丁。权重：**强到可直接采纳**。

**总评**：最佳语义模型，但应与候选 C 的 shared policy 一起采用。权重：**强到可直接采纳**。

### 候选 C：把 legacy reasoning mapping 提升为共享 leaf，再由两条链调用

**形态**：将 `ReasoningEffortBand`、capability facts 的不变量、canonical effort selection 和 mapping result 从 `src/app/protocols/anthropic_responses.py` 提升到不依赖 protocol/pipeline 的共享模块，例如 `src/app/models/reasoning.py`。legacy `_RequestConverter` 与 active `to_openai_responses` 都 import 这个 leaf；wire shape parsing、`RequestConversionError` / `TranslationRefused`、conversion fact / loss 仍留在各自边界。

**改动文件**：

- 新增 `src/app/models/reasoning.py`，或项目选定的同级 leaf。
- `src/app/protocols/anthropic_responses.py`：改为 import shared policy，保留 legacy adapter。
- `src/app/anthropic/client.py`：继续组 capability facts，但不能把当前 multi-effort 空 bands 当 active 默认。
- 候选 B 的 active semantic、reader、writer、provider、registry、handler 文件。
- `tests/unit/anthropic/test_anthropic_responses_request.py`：保留 legacy 行为回归。
- 新增 shared resolver unit tests，覆盖每个 desired tier 都在 capability set 内、缺档 fallback/reject、非法 capability facts。
- active translator 与 integration tests 同候选 B。

**跨格式行为**：由 `ReasoningIntent` adapter 决定；shared 模块只做 protocol-free intent + capabilities → resolution，不产生 wire dict。

**与 `LossCode` 的关系**：shared resolver 返回类似 `ReasoningResolution(effort, disposition, reason)`；legacy adapter 转成 `ConversionFact` / `RequestConversionError`，active adapter 转成 `LossCode` / `TranslationRefused`。这避免 shared leaf import 任一链的 error 类型。

**对 `count_tokens` 的影响**：active count 与 send 共用 resolver；legacy 不受 active count 影响。

**import 边界**：`app.models.reasoning` 不 import `app.protocols`、`app.pipeline`、`app.anthropic` 或 `app.server`；两条链依赖向内。`test_the_typed_kernel_is_a_leaf` 无需放宽。可另加一条针对 shared reasoning leaf 的同类 import 断言，但不需要新建证明框架。

**优点判断**：真正复用了已经验证的算法和不变量，不复制两份五档 selector，也不让 active 依赖 legacy wire converter。权重：**强到可直接采纳**。

**代价判断**：这是一次有意义的 extraction；同时碰 legacy 文件，必须跑 legacy 与 active 两组 targeted tests。权重：**强到可直接采纳**。

**总评**：与候选 B 组合后是推荐方案；单独采用、仍让 active 保存 raw thinking，只解决复用，不解决 semantic shape。权重：**强到可直接采纳**。

### 候选 D：保留 `thinking` 在 `extensions`，由 Responses writer 白名单消费

**形态**：不把 `thinking` 加进 `_PASSTHROUGH_KEYS`，继续保存在 `SemanticRequest.extensions`；`to_openai_responses` 在调用 `extensions_for` 前专门读取并消费 `extensions["thinking"]`，把它映射为 reasoning，同时确保 generic extension drop 不再把已消费 key 报成 `EXTENSIONS_NOT_CARRIED`。可实现为 `consume_extension` 或 `extensions_for(..., consumed={"thinking"})`，绝不能白名单后把 Anthropic thinking 字典原样 replay 到 Responses。

**改动文件**：`src/app/pipeline/translation_driver/semantic.py`、`src/app/pipeline/translation_driver/openai_responses.py`，以及与候选 A 相同的 provider/registry/handler capability plumbing 和测试。`anthropic_messages.py` 可不改，或只加注释说明该 key 被 target writer 特判。

**跨格式行为**：Anthropic → Responses 特判；same-format round trip 仍由 generic extensions 回放；其他 target 对这个 key 不知情。

**与 `LossCode` 的关系**：必须区分“已被语义消费”与“被丢弃”，否则同一 key 既映射又产生 `EXTENSIONS_NOT_CARRIED` 的假报告。fallback/drop/refusal 规则同候选 A/B。

**对 `count_tokens` 的影响**：同样需要 capability plumbing；没有因为使用 extensions 而减少这一部分工作。

**优点判断**：最少改 semantic schema，能快速接通。权重：**强到可直接采纳**。

**缺点判断**：一个已经理解其语义、会改变上游生成行为的字段仍伪装成“无 translator 认领的扩展”；每增加一个 target-specific semantic mapping 都会继续给 `extensions_for` 增加例外，且类型校验发生得过晚。权重：**强到可直接采纳**。

**总评**：不推荐。权重：**强到可直接采纳**。它节省的只有一个 dataclass field，却没有省掉能力通道、mapping policy、count path 与测试。

## 6. 推荐方案与实施边界

### 6.1 推荐

采用候选 B + C：

1. 用 protocol-neutral `ReasoningIntent` 在 `SemanticRequest` 表达 disabled/adaptive/budget/explicit-effort。
2. 从 legacy 提升纯 capability/mapping policy 到共享 leaf；不要从 active codec import `app.protocols.anthropic_responses`。
3. 在 `ModelDescriptor` 增加 typed reasoning capabilities，由 `GithubCopilotProvider.replace_catalog` 从 raw catalog 解析，保留“字段缺席”和“字段为空”的区别。
4. 给 `TranslatorRegistry.translate` 增加一个轻量的 target context，例如 `TranslationTarget(model_id, reasoning_capabilities)`；`handle` 与 `handle_count_tokens` 都在 `shape_request` 之后传入同一 resolved descriptor。writer 看 target context，reader 不需要知道 route。
5. `to_openai_responses` 调 shared resolver，并在得到 resolution 后才写 `payload["reasoning"]` 与 conversion loss。

推荐权重：**强到可直接采纳**。理由是它同时满足全档 capability lookup、协议边界、两链复用、count/send 一致性和现有 import guard；其他候选至少牺牲其中一项，却没有实质减少 capability plumbing。

建议的 shared policy 输入输出如下，名称可调整：

```python
@dataclass(frozen=True, slots=True)
class ReasoningCapabilities:
    supported_efforts: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ReasoningResolution:
    effort: str | None
    approximated: bool
    reason: str = ""
```

resolver 的硬不变量应是：`resolution.effort is None or resolution.effort in capabilities.supported_efforts`。判断权重：**强到可直接采纳**。这个不变量直接封死第三方实现三档绕过 capability list 的缺陷。

### 6.2 不推荐的“直接复用”方式

不要让 `src/app/pipeline/translation_driver/openai_responses.py` import `_RequestConverter`、`ReasoningCapabilityFacts` 或私有 `_convert_reasoning` from `src/app/protocols/anthropic_responses.py`。即使当前 fresh import 已因 `ToolNameMapper` 间接加载这个模块，直接依赖仍会把 legacy wire model 与 active semantic model绑在一起，并使将来移走 `ToolNameMapper` 时 active closure 无法真正变轻。判断权重：**强到可直接采纳**。

不要把完整 `ModelCapabilities` Pydantic object直接塞进 `SemanticRequest`。它是 target/provider 的事实，不是 client semantic request；把它作为 writer 的 translation context 更符合职责。判断权重：**强到可直接采纳**。

### 6.3 推荐的测试位置

| 测试目标 | 位置 | 必须有的鉴别样本 | 权重 |
|---|---|---|---|
| shared resolver | 新的 `tests/unit/models/test_reasoning.py` 或项目选定的 shared-policy unit test | capability 分别只有 `{low,medium,high}`、含 xhigh、含 max、含/不含 none；五个 desired enabled tier 逐一断言结果属于 set；未知 effort 名不可能被返回。 | **强到可直接采纳** |
| Anthropic reader | `tests/unit/pipeline/translation_driver/test_translation_driver.py` | disabled/adaptive/enabled、缺 budget、bool budget、零/负数、unknown type、extra key。 | **强到可直接采纳** |
| Responses writer | 同上 | 真实目录中至少四种 capability shape；`disabled` 不得因 omit 变成默认 medium；loss/refusal 精确断言。 | **强到可直接采纳** |
| provider catalog projection | 现有 model provider tests，若无合适文件则新增窄测试 | 从 raw entry 保留 effort tuple；区分 absent、null、empty、malformed、duplicate。 | **强到可直接采纳** |
| 活链路 wire | `tests/int/test_pipeline_app.py` | Anthropic body 经 `create_pipeline_app` 到 mock provider，断言 provider 收到 resolved model 对应的 `reasoning`；另测 capability 不支持时的用户裁定行为。 | **强到可直接采纳** |
| count path | `tests/int/test_pipeline_app.py` 的 count_tokens 组 | 同一 body 的 send 与 count 走同一 resolution；估算值不因顶层 reasoning policy 被误加成 prompt token；malformed thinking 行为一致。 | **强到可直接采纳** |
| 录制回放 | `tests/int/recorded/` | 只有在另一路真实实测给出可重录 fixture 后再新增；本任务禁止发真实请求，不手写 cassette。 | **强到可直接采纳** |
| 架构边界 | `tests/unit/test_module_boundaries.py` 与 `tests/unit/test_imports.py` | 保持现有断言；shared leaf 不反向 import protocol/pipeline。 | **强到可直接采纳** |

测试数量不应扩成穷举矩阵；resolver 的 capability intersection、活 wire 一条 happy path、一个 unsupported path、count 一条一致性路径足以覆盖本 slice 的真实失败面。判断权重：**强到可直接采纳**。依据是项目测试规则要求覆盖 critical path、happy path 与本 slice 实际改变的 failure mechanism。

### 6.4 推荐的代价

- 必须修改 provider descriptor 与 translator invocation，不是“只改 translator”规模。事实权重：**强到可直接采纳**。
- shared extraction 会同时触及 legacy tests；这是语义复用的成本，不是让 legacy 重新成为活入口。判断权重：**强到可直接采纳**。
- `ReasoningIntent` 若本 slice 同时支持 Responses inbound，会扩大范围；可以先定义 `effort` variant但暂不认领 `from_openai_responses` 的顶层 reasoning，后续独立补对称 round-trip。判断权重：**是个倾向、需更多样本**。若用户要求本次完全对称，则不应切掉。
- `LossCode` 当前缺运行时读者，新增 approximation loss 仍只进入 `context.extras`；这不应阻塞正确接线，但不能把“已记录”描述成“用户可见”。事实权重：**强到可直接采纳**。证据是 `handle` / `handle_count_tokens` 写入 conversion losses，以及《本项目当前能力面盘点》的“翻译损失有清单、无读者”结论（`.dev/docs/sync-refs/sxwxs-ghc-api/260821-inventory-our-capabilities.md`）。

## 7. 与 `LossCode` 和错误语义的建议关系

建议最多新增两个宽而明确的 code，而不是为每一档建一个 code：

- `REASONING_INTENT_APPROXIMATED`：合法 intent 被量化或 fallback，例如 budget→离散 tier、adaptive→固定 tier、desired xhigh→supported high、disabled→low（若用户允许）。detail 写 source intent、desired effort、selected effort 与 model。
- `REASONING_INTENT_NOT_CARRIED`：用户裁决允许继续，但 target 完全不支持或 policy 决定 omit。detail 写明原因。

unknown type、缺失/非法 budget、非法 extra key、capability facts malformed，以及用户裁决为 strict 的不支持情况应抛 `TranslationRefused`，使用稳定 code 和精确 field path，例如 `thinking.type`、`thinking.budget_tokens`、`thinking`。判断权重：**强到可直接采纳**。这沿用现有“损失是可继续的降级，refusal 是继续会改变含义”的定义。

是否对**每一次** budget→tier 都记 approximation 需要用户裁决。倾向：记，因为连续 budget 变离散 effort 必然丢信息；若最终产品 spec 明确宣布这些阈值就是其语义编码，则可以只在 desired tier 不受支持、发生二次 fallback 时记 loss。判断权重：**是个倾向、需更多样本**。依据是 `Conversion.losses` 的当前语义与未来可观测性成本尚未裁定。

## 8. `count_tokens` 路径影响

`handle_count_tokens` 当前与真实发送一样先 `shape_request`、再 translation、再把 model 改成 resolved model，并对 Responses target 调 `estimate_responses_input`；Responses family 没有 upstream count endpoint。事实权重：**强到可直接采纳**。证据是 `handle_count_tokens`（`src/app/server/handler.py`）。

`estimate_responses_input` 只计 `instructions`、`tools` 和 `input` items，不计顶层 `reasoning`。这符合该 endpoint 返回“input token estimate”的职责：effort 控制未来输出，不是 prompt 内容。历史 continuation 中真正位于 `input` 的 `type: reasoning` item则由 `_responses_item_text` fallback 序列化并计入，现有行为不应改变。事实权重：**强到可直接采纳**。证据是 `estimate_responses_input` 与 `_responses_item_text`（`src/app/tokenization/estimators.py`）。

推荐 count 与 send 使用同一 resolved capability 和 resolver，不增加 `count_tokens` 专用阈值或专用配置。若用户裁决“模型不支持显式 reasoning 时发送应拒绝”，count 也应拒绝 malformed/unsupported semantic request；若用户裁决 drop/approximate，count 应执行同样转换后估算。判断权重：**强到可直接采纳**。这样避免 count 回答一个与真实发送不同的 body。

数值层面不需要因为顶层 `reasoning.effort` 新增 token 项，也不需要改变 Anthropic estimator 跳过 assistant historical thinking 的既有规则。判断权重：**强到可直接采纳**。这里回答的是 input size，不是高 effort 可能消耗的 future reasoning/output budget。

信心限制：没有 Copilot Responses count endpoint可测“顶层 reasoning object 是否有极小的内部计费 overhead”；当前 estimator 本来就是 payload input 的保守本地估算，不是 billing oracle。这个不确定性不足以支持把 generation policy JSON 字节算进 prompt。判断权重：**是个倾向、需更多样本**。

## 9. 未决问题清单

| 未决项 | 可选裁决 | 我的倾向 | 倾向权重与依据 |
|---|---|---|---|
| enabled budget 的五档阈值 | 采用第三方 3000/8000/16000/30000；采用 legacy fixture 4096/16384 再扩两档；另定。 | 若必须立即给默认，倾向第三方的五档阈值作为起点，但明确标为本项目产品 policy，而非上游事实。 | **是个倾向、需更多样本**。它有同类项目经验但无本仓 live evidence；legacy fixture 只有三档且只是测试数据。 |
| 边界是 `>=` 还是 `<= band.max` | 两种写法需统一成同一组半开区间。 | 倾向按 desired tier 的 lower bound 表达，即 `>=30000→max` 等，便于读懂五档。 | **是个倾向、需更多样本**。纯可读性偏好。 |
| `thinking: disabled`，target 支持 `none` | 发 `effort: none`；omit。 | 发 `none`。 | **强到可直接采纳**。真实 gpt-5.5 cassette 证明 omit 会默认 medium。 |
| `thinking: disabled`，target 不支持 `none` | reject；降到最低 supported effort并记 loss；omit。 | 倾向 reject；若产品优先保持可用，再选最低 supported effort并明确 loss，绝不静默 omit。 | **是个倾向、需用户裁决**。disabled 是明确反向指令，low 仍不是 disabled。 |
| `thinking: adaptive` | 固定 high；最高 supported；最高不超过 high；交给 omit/default。 | 倾向 desired=high，再按 canonical lattice 向下选 supported，不升级到 xhigh/max；并记 approximation。 | **是个倾向、需更多样本**。第三方选择 high，但本仓无 adaptive→Responses 实测。 |
| enabled desired tier 不受支持 | floor 到较低 supported；nearest；reject。 | 倾向 floor，不上调成本，并记录 desired/selected；若连 low 都没有则 reject。 | **是个倾向、需用户裁决**。这是成本方向的产品选择。 |
| 模型无 `reasoning_effort` 字段、字段为 null/empty、或 malformed | drop；reject；按模型名猜。 | reject显式 enabled/adaptive；disabled 对真正不推理的模型可视为已满足，但“字段缺席”不等于已证明不推理，所以仍倾向 reject。 | **强到可直接采纳**的是“不猜模型名”；具体 reject/drop **需用户裁决**。 |
| budget 合法范围 | 只验证正整数；沿用 Anthropic 1024 minimum；要求不超过 max_tokens；借用 32000 maximum。 | 倾向至少拒绝 bool/非整数/非正数；其他限制等当前 Anthropic contract或实测员结论，不借用 Claude `/v1/messages` 模型的 32000 给 Responses target。 | **强到可直接采纳**的是“不借错 endpoint 的 limits”；具体范围 **需用户裁决**。 |
| `summary` request 字段 | 发 `summary: auto`；omit；发 detailed/concise。 | 暂倾向沿用 legacy 的 `auto`，但在实测员结果回来前不要把它写成已录制事实。 | **是个倾向、需更多样本**。只有代码与 mock test，cassette request body未保存。 |
| mapping 是否记 `LossCode` | 所有 budget quantization 都记；只在 capability fallback 时记；不记。 | 倾向所有连续→离散都记 approximation；若 spec 将阈值定义成正式语义，再收窄到只记 fallback。 | **是个倾向、需用户裁决**。 |
| 不支持 reasoning 时 drop 还是 reject | drop + loss；reject。 | 倾向 reject显式 enabled/adaptive，防止请求看似成功却完全未生效。 | **是个倾向、需用户裁决**。符合现有 `TranslationRefused` 定义。 |
| 是否增加配置项 | 阈值/fallback 可配置；先固定产品 policy。 | 不增加配置；先由 spec 固定一套规则，能力列表继续动态来自目录。 | **强到可直接采纳**。当前只有一个上游选择面，配置会把一个合同扩大成组合矩阵；以后出现真实不同部署需求再加。 |
| `count_tokens` 遇到 unsupported reasoning | 照 send reject；忽略 generation policy后仍给 input estimate。 | 倾向与 send 同裁决，保持“测的是会发送的 body”。 | **是个倾向、需用户裁决**。现有 count path 强调 shape/translate 一致，但也明确排除纯执行约束；需用户决定 reasoning support 属哪类。 |
| Responses inbound explicit effort 是否本 slice 对称支持 | 同时实现；只预留 intent variant。 | 倾向预留 `mode="effort"`，本 slice 先完成主产品方向；若 complete behavioral Spec 要求 round-trip，则同批实现。 | **是个倾向、需用户裁决**。这是范围而不是技术可行性问题。 |

## 10. 反向检查：响应方向与 carrier 是否会出现新不一致

### 10.1 已有响应链能承载什么

流式 `ResponsesAssembler` 对每个 `type: reasoning` output item分别开 draft，在 `response.reasoning_summary_text.delta` 累积可见 summary，在 `response.output_item.done` 从 closing item优先读取 `encrypted_content`，最后生成一个 Anthropic `thinking` block与项目 carrier。事实权重：**强到可直接采纳**。证据是 `ResponsesAssembler._open`、`ResponsesAssembler._accumulate`、`ResponsesAssembler._close` 和 `_reasoning_signature`（`src/app/pipeline/delivery/assembler.py`）。

非流式路径的 `blocks_from_item` 把每个 Responses reasoning item变成 `ContentBlock(BlockKind.REASONING)`，`_reasoning_to_anthropic` 再把 opaque payload编码进 carrier。反向历史 replay由 `_reasoning_item` 精确恢复 `encrypted_content`；foreign Claude signature不伪装成 Responses payload。事实权重：**强到可直接采纳**。证据是 `blocks_from_item` / `_reasoning_item`（`src/app/pipeline/translation_driver/openai_responses.py`）与 `_reasoning_to_anthropic`（`src/app/pipeline/translation_driver/anthropic_messages.py`）。

当前 carrier producer/consumer不依赖 request effort，故增加顶层 `reasoning.effort` 不要求改变 carrier版本或 wire format。判断权重：**强到可直接采纳**。effort改变“模型投入多少推理”，不改变 output reasoning item中 summary/encrypted_content 的既有承载职责。

### 10.2 需要新增的反向验证

高 effort 可能增加 reasoning tokens、summary长度、reasoning item数量或 block resident bytes，但本仓没有“同 prompt 不同 effort”的录制对照，因此不能宣称 response shape完全不变。判断权重：**是个倾向、需更多样本**。现有真实证据只覆盖默认 medium和历史 high，不是控制变量实验。

建议至少增加一个纯本地 active response regression：mock upstream返回两个 reasoning items，其中一个有 summary + encrypted_content，另一个 summary为空但 encrypted_content非空，确认流式和非流式都得到两个独立 thinking blocks且 carrier可回放。判断权重：**是个倾向、需更多样本**。当前代码按 item独立处理，但本次检索到的 active tests主要是单 reasoning item；多 item是新 feature更常触发时最值得锁住的形状。

block-level buffering是产品既定要求，高 effort产生更大 reasoning block时会增加直到 `output_item.done` 前的驻留字节，但不应改成 token/event级下游交付。判断权重：**强到可直接采纳**。证据是 `ResponsesAssembler` 的 block close语义与项目开发规则。

usage方向已经读取 `output_tokens_details.reasoning_tokens` 到 `ResponseUsageFacts.reasoning_tokens`，Anthropic下游 usage仍只暴露其协议字段；高 effort无需修改 usage转换，但可观测到的 reasoning token总量可能上升。事实权重：**强到可直接采纳**。证据是 `_convert_usage`（`src/app/protocols/responses_anthropic.py`）。

### 10.3 `count_tokens` 与 output budget

`count_tokens` 是 input estimate，不估算 future reasoning/output tokens；因此 effort接线后无需把 budget或effort折算进 input token返回值。判断权重：**强到可直接采纳**。

另一个独立问题是 `max_tokens` → `max_output_tokens` 与 Anthropic `thinking.budget_tokens` 的关系。当前 active reader只验证 `max_tokens` 是 int后写入 semantic，尚未验证 enabled budget与max output的组合；legacy converter也主要依据 model capability limits。是否要求 budget小于、等于或独立于max output必须由当前 Anthropic/Copilot合同或实测结果决定，不能从effort映射自行推出。事实与判断权重：现状 **强到可直接采纳**；应否新增关系校验 **是个倾向、需更多样本**。

## 11. 信心边界

以下结论信心足够直接进入实现 Spec：active缺口的数据流；Responses模型 effort枚举必须逐模型查表；omit不等于disabled；active provider当前丢弃 reasoning capability；不能直接把legacy converter当shared leaf；推荐的dependency方向；count estimator不应把顶层generation policy当prompt token。权重：**强到可直接采纳**。

以下结论仍缺证据：每个 effort值在当前Copilot `/responses` 上是否逐值接受；`summary: auto` 是否是当前Copilot方言的最佳 spelling；五档阈值；adaptive映射；高 effort是否改变事件形状；budget与max output的合法关系。权重：**是个倾向、需更多样本**。等待另一名实测员的结果能缩小前两项，但阈值和降级仍是产品裁决，不会被“端点接受”自动决定。

第三方 sxwxs/ghc-api 的阈值与 fallback只作为独立实现样本，不作为本项目上游事实；其五档中三档绕过 capability list的写法明确不采纳。权重：阈值 **仅存档、不据以决策**；“所有输出 effort均需 capability membership” **强到可直接采纳**。证据是《sxwxs/ghc-api 对本项目的可借鉴项：对照与裁断》与核查报告（`.dev/docs/sync-refs/sxwxs-ghc-api/260821-ghc-api-lessons-for-us.md`、`.dev/docs/sync-refs/sxwxs-ghc-api/260821-verify-ghc-api-claims.md`）。

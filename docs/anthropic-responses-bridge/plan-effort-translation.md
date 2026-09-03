# Effort Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This project implements production behavior before adding the directly related tests; do not invert the steps into TDD.

**Goal:** 完整实现 Anthropic Messages `thinking／output_config.effort` 与 OpenAI Responses `reasoning.effort` 的双向翻译，同时保持 direct leg 原样转发、send／count 同形、精确 conversion facts 和 target thinking capability fail-closed。

**Architecture:** 两侧 reader 先把 request-level 状态归一为 `ThinkingEffortIntent`，writer 再结合 resolved target 的 effort catalog 与配置选中的 `ThinkingTargetProfile` 生成目标 wire。Thinking 只决定 enabled／disabled，effort 只取 effort 字段；deprecated manual budget只用于识别 source compatibility 或构造 extended-only target 的合法 wire，不参与 effort 档位选择。Nested residual 与 capability observations 单独保留，不能借 generic extensions 丢掉或重复记录已转换字段。

**Tech Stack:** Python 3.14、Pydantic v2、FastAPI、OpenAI SDK 3.3.1、Anthropic SDK、pytest、Ruff `check`、Pyright、YAML bundled config。

**Spec:** `.dev/docs/anthropic-responses-bridge/spec.md` 的「Request-level ThinkingEffortIntent」与双向字段矩阵；验收转录为 `.dev/docs/anthropic-responses-bridge/acceptance.md` 的 REQ-05A。实现状态由 `.dev/docs/anthropic-responses-bridge/implementation.md` 维护。

## 执行状态（2026-09-03）

- **状态**：Tasks 1～5全部实施、whole-branch final review与唯一fix wave收口、full Ruff／Pyright／pytest通过，净语义已进入main；current事实与证据见[Implementation](implementation.md)和[代码评审处置](review-disposition-effort-translation-code.md)。下文checkbox保留为本次执行配方与可追溯计划，不再表示open待办。
- **装位**：reviewed source由`archive/260903-effort-translation@ed6addd`保留，squash结果为`main@4b7d74f`；完整tree一致。
- **实际偏离**：Task 1 Files遗漏了最终profile接线所需的`src/app/pipeline/driver.py`，执行时只补send／count两处参数；Task 5为取得真实explicit-high cassette，增加multi-provider后失效的recorder统一transport与零interaction保护；final review另发现transparent replay丢source beta header及Spec同pattern override文字漂移，分别以request-lifetime snapshot和living Spec／Acceptance纠正收口。三项均记录在[代码评审处置](review-disposition-effort-translation-code.md)，没有删除或缩减原计划功能。
- **边界**：真实cassette只校准PONG＋gpt-5.5＋explicit high，不外推其它model／effort；没有push、deployment或`4141`cutover。

## Global Constraints

- 不修改 `docs/.human-controlled/`；配置样例建议写入 `.dev/human-controlled-docs-candidates/`，由用户自行摘取。
- 不改或复活 legacy `src/app/protocols/anthropic_responses.py` request converter；生产路径继续只走 `pipeline/translation_driver`。
- 不运行 `ruff format`；只运行 `uv run ruff check src tests`或本计划列出的精确子路径。
- Direct Anthropic→Anthropic 与 Responses→Responses 不调用本轮 translation policy，wire保持原样。
- Anthropic source effort合法值为`low／medium／high／xhigh／max`，省略为`high`；Responses source effort为nullable `none／minimal／low／medium／high／xhigh／max`。
- Literal `ultracode`不是wire值并稳定拒绝；Claude Code实际发送的`xhigh`按普通档位翻译，代理不模拟Workflow。
- Forward enabled effort候选排除`none`；disabled target不明确发布`none`时拒绝。
- Reverse thinking shape只取`model_translation.to_anthropic_messages.thinking_profiles`最后一个resolved-model regex fullmatch；默认配置转录Spec官方表，用户配置可覆盖。
- Extended-only target没有显式manual budget、manual budget与当前`max_tokens`不相容、always-on target收到disabled或profile未命中时零upstream拒绝。
- 每次提交只含本轮精确路径，commit message使用`-F <file>`，不使用`-m`，不推送。

---

### Task 1: 配置并编译 target Anthropic thinking profiles

**Files:**
- Modify: `src/app/config/schema.py:203-234`
- Modify: `src/app/config/bundled-config.yaml`
- Modify: `src/app/core/chain.py:29-53`
- Modify: `src/app/pipeline/routing.py:371-379`
- Modify: `src/app/server/composition.py:526-575`
- Modify: `src/app/pipeline/driver.py:157-163,274-280`
- Modify: `src/app/pipeline/translation_driver/reasoning.py`
- Modify: `src/app/pipeline/translation_driver/semantic.py:104-117`
- Test: `tests/unit/config/test_config_schema.py`
- Test: `tests/unit/config/test_config_loading.py`
- Test: `tests/unit/pipeline/translation_driver/test_reasoning.py`
- Test: `tests/int/test_pipeline_app.py`

**Interfaces:**
- Produces: `ThinkingTargetProfileConfig`、`ThinkingTargetProfile`、`CompiledThinkingProfiles`、`compile_thinking_profiles()`、`select_thinking_profile()`。
- Produces: `TranslationTarget.thinking_profile` 与 `TranslationTarget.thinking_profile_pattern`，供 Task 4 的 Anthropic writer 使用。
- Consumes: `ProxyConfig.model_translation.to_anthropic_messages.thinking_profiles`。

- [ ] **Step 1: 在 config schema 中增加 profile 类型与 translation section**

实现以下类型；`manual_budget_tokens`必须以 strict integer拒绝bool，profile modes不能为空且不重复：

```python
type AnthropicEffort = Literal["low", "medium", "high", "xhigh", "max"]
type AnthropicThinkingMode = Literal["adaptive", "enabled"]

class ThinkingTargetProfileConfig(Section):
    modes: tuple[AnthropicThinkingMode, ...]
    can_disable: bool = Field(strict=True)
    disabled_max_effort: AnthropicEffort | None = None
    manual_budget_tokens: int | None = Field(default=None, strict=True, ge=1024)

    @model_validator(mode="after")
    def _modes_are_nonempty_and_unique(self) -> ThinkingTargetProfileConfig:
        if not self.modes:
            raise ValueError("thinking profile modes may not be empty")
        if len(set(self.modes)) != len(self.modes):
            raise ValueError("thinking profile modes may not contain duplicates")
        return self

class ToAnthropicMessagesConfig(Section):
    thinking_profiles: dict[str, ThinkingTargetProfileConfig] = Field(
        default_factory=lambda: dict[str, ThinkingTargetProfileConfig]()
    )

class ModelTranslationConfig(Section):
    to_openai_responses: ToOpenAiResponsesConfig = Field(default_factory=ToOpenAiResponsesConfig)
    to_anthropic_messages: ToAnthropicMessagesConfig = Field(default_factory=ToAnthropicMessagesConfig)
```

- [ ] **Step 2: 在 bundled config 写入Spec六条默认regex profile**

```yaml
model_translation:
  to_anthropic_messages:
    thinking_profiles:
      'claude-(?:fable|mythos)-5(?:[.-]1)?(?:-[0-9]{8})?':
        modes: [adaptive]
        can_disable: false
      'claude-mythos-preview(?:-[0-9]{8})?':
        modes: [adaptive, enabled]
        can_disable: false
      'claude-opus-5(?:-[0-9]{8})?':
        modes: [adaptive]
        can_disable: true
        disabled_max_effort: high
      'claude-(?:opus-4[.-](?:7|8)|sonnet-5)(?:-[0-9]{8})?':
        modes: [adaptive]
        can_disable: true
      'claude-(?:opus|sonnet)-4[.-]6(?:-[0-9]{8})?':
        modes: [adaptive, enabled]
        can_disable: true
      'claude-(?:(?:opus|sonnet|haiku)-4[.-]5|opus-4[.-]1|opus-4|sonnet-4)(?:-[0-9]{8})?':
        modes: [enabled]
        can_disable: true
```

- [ ] **Step 3: 增加runtime profile、编译与最后命中选择**

在`reasoning.py`定义纯runtime数据；在`routing.py`编译配置并实现最后fullmatch胜出：

```python
@dataclass(frozen=True, slots=True)
class ThinkingTargetProfile:
    modes: tuple[str, ...]
    can_disable: bool
    disabled_max_effort: str | None = None
    manual_budget_tokens: int | None = None

CompiledThinkingProfiles = tuple[tuple[re.Pattern[str], ThinkingTargetProfile], ...]

def compile_thinking_profiles(
    configured: Mapping[str, ThinkingTargetProfileConfig],
) -> CompiledThinkingProfiles:
    return tuple(
        (
            re.compile(pattern),
            ThinkingTargetProfile(
                modes=profile.modes,
                can_disable=profile.can_disable,
                disabled_max_effort=profile.disabled_max_effort,
                manual_budget_tokens=profile.manual_budget_tokens,
            ),
        )
        for pattern, profile in configured.items()
    )

def select_thinking_profile(
    profiles: CompiledThinkingProfiles, model_id: str,
) -> tuple[str, ThinkingTargetProfile] | None:
    selected: tuple[str, ThinkingTargetProfile] | None = None
    for pattern, profile in profiles:
        if pattern.fullmatch(model_id):
            selected = (pattern.pattern, profile)
    return selected
```

`TranslationTarget`新增：

```python
thinking_profile: ThinkingTargetProfile | None = None
thinking_profile_pattern: str = ""
```

- [ ] **Step 4: 在composition只编译一次并沿routing传入target**

`Chain`新增`thinking_profiles: CompiledThinkingProfiles = ()`；`build_chain()`调用`compile_thinking_profiles(config.model_translation.to_anthropic_messages.thinking_profiles)`；`translation_target(provider, model_id, thinking_profiles)`选择最后命中profile并保留pattern。`handle()`与`handle_count_tokens()`都传同一`chain.thinking_profiles`。

**执行时Ruling（2026-09-03）**：原Files／Step 8 pathspec漏列`src/app/pipeline/driver.py`，却在本Step明确要求修改它。该文件归入Task 1，范围只限上述两处profile参数接线；Task 2的source-header逻辑仍由Task 2实现。

- [ ] **Step 5: 运行直接配置探针**

Run:

```bash
uv run python - <<'PY'
from app.config.loading import bundled_config_values
from app.config.schema import ProxyConfig
from app.pipeline.routing import compile_thinking_profiles, select_thinking_profile
config = ProxyConfig.model_validate(bundled_config_values())
profiles = compile_thinking_profiles(config.model_translation.to_anthropic_messages.thinking_profiles)
for model in ("claude-opus-5", "claude-opus-4.8", "claude-haiku-4.5"):
    print(model, select_thinking_profile(profiles, model))
for model in ("claude-sonnet-4-1", "claude-haiku-4-1", "claude-haiku-4"):
    assert select_thinking_profile(profiles, model) is None
PY
```

Expected: 三个官方model各命中唯一profile；三个邻近负样本均为`None`。

- [ ] **Step 6: 补配置与选择测试**

测试覆盖：六条regex的官方正样本与三个负样本；非法regex启动失败；空／重复modes；`can_disable`的字符串`"false"`与整数0／1拒绝、YAML原生true／false接受；manual budget的bool／小于1024值失败；用户新增重叠regex作为最后match覆盖bundled profile；同pattern部分override保留未覆盖字段。

代表性测试：

```python
def test_thinking_profile_last_matching_user_pattern_overrides_bundled_default(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "model_translation:\n"
        "  to_anthropic_messages:\n"
        "    thinking_profiles:\n"
        "      'claude-opus-.*':\n"
        "        modes: [enabled, adaptive]\n"
        "        can_disable: true\n"
        "        manual_budget_tokens: 2048\n",
        encoding="utf-8",
    )
    config = load_proxy_config(config_path=config_path, environ={})
    profiles = compile_thinking_profiles(config.model_translation.to_anthropic_messages.thinking_profiles)
    pattern, profile = select_thinking_profile(profiles, "claude-opus-5") or ("", None)
    assert pattern == "claude-opus-.*"
    assert profile is not None and profile.modes == ("enabled", "adaptive")
```

- [ ] **Step 7: 运行本切片测试**

Run:

```bash
uv run pytest --collect-only -q tests/unit/config/test_config_loading.py::test_thinking_profile_last_matching_user_pattern_overrides_bundled_default
uv run pytest tests/unit/config/test_config_schema.py tests/unit/config/test_config_loading.py tests/unit/pipeline/translation_driver/test_reasoning.py tests/int/test_pipeline_app.py -k 'thinking_profile or bundled_profile or model_translation'
uv run ruff check src/app/config src/app/core/chain.py src/app/pipeline/routing.py src/app/server/composition.py tests/unit/config tests/unit/pipeline/translation_driver/test_reasoning.py
uv run pyright src/app/config src/app/core/chain.py src/app/pipeline/routing.py src/app/server/composition.py tests/unit/config tests/unit/pipeline/translation_driver/test_reasoning.py
```

Expected: targeted tests、Ruff、Pyright全部通过；这只证明profile配置／选择，不证明request translation。

- [ ] **Step 8: 提交配置语义切片**

只暂存本Task路径。先用Write创建`$CLAUDE_JOB_DIR/tmp/commit-effort-profile.txt`，内容为`feat: configure Anthropic thinking profiles`，再执行：

```bash
git add -- src/app/config/schema.py src/app/config/bundled-config.yaml src/app/core/chain.py src/app/pipeline/routing.py src/app/server/composition.py src/app/pipeline/driver.py src/app/pipeline/translation_driver/reasoning.py src/app/pipeline/translation_driver/semantic.py tests/unit/config/test_config_schema.py tests/unit/config/test_config_loading.py tests/unit/pipeline/translation_driver/test_reasoning.py tests/int/test_pipeline_app.py
git commit -F "$CLAUDE_JOB_DIR/tmp/commit-effort-profile.txt" -- src/app/config/schema.py src/app/config/bundled-config.yaml src/app/core/chain.py src/app/pipeline/routing.py src/app/server/composition.py src/app/pipeline/driver.py src/app/pipeline/translation_driver/reasoning.py src/app/pipeline/translation_driver/semantic.py tests/unit/config/test_config_schema.py tests/unit/config/test_config_loading.py tests/unit/pipeline/translation_driver/test_reasoning.py tests/int/test_pipeline_app.py
```

### Task 2: 建立`ThinkingEffortIntent`、source context与nested residual

**Files:**
- Modify: `src/app/pipeline/translation_driver/reasoning.py`
- Modify: `src/app/pipeline/translation_driver/semantic.py`
- Modify: `src/app/pipeline/translation_driver/registry.py`
- Modify: `src/app/pipeline/translation_driver/anthropic_messages.py`
- Modify: `src/app/pipeline/translation_driver/openai_responses.py`
- Modify: `src/app/pipeline/driver.py:132-169,263-283`
- Test: `tests/unit/pipeline/translation_driver/test_translation_driver.py`
- Test: `tests/int/test_pipeline_app.py`

**Interfaces:**
- Produces: `ThinkingEffortIntent(enabled, effort, effort_source)`与`EffortSource`。
- Produces: request reader协议`reader(payload, *, source_headers, translated)`。
- Produces: `SemanticRequest.nested_extensions`和`nested_extensions_for()`，供两向writer重建或记录精确loss。
- Consumes: Task 1的`TranslationTarget`。

- [ ] **Step 1: 增加统一IR但保留旧消费者的可运行过渡**

在`reasoning.py`增加并导出：

```python
class EffortSource(StrEnum):
    ANTHROPIC_DEFAULT = "anthropic-default"
    ANTHROPIC_TOP_LEVEL = "anthropic-top-level"
    ANTHROPIC_PER_MESSAGE = "anthropic-per-message"
    RESPONSES = "responses"

@dataclass(frozen=True, slots=True)
class ThinkingEffortIntent:
    enabled: bool
    effort: str | None
    effort_source: EffortSource
```

Task 2只新增field，不删除旧field；旧`from_anthropic_messages()`与两侧writer继续读写`reasoning`，因此该Task结束时现有production行为可运行：

```python
# Transitional through Task 2 only; Task 3 removes this after every consumer switches.
reasoning: ReasoningIntent | None = None
thinking_effort: ThinkingEffortIntent | None = None
nested_extensions: dict[str, dict[str, Any]] = field(default_factory=lambda: dict[str, dict[str, Any]]())
```

Task 2测试必须断言现有Anthropic→Responses budget行为仍可走通；不得先改reader写`thinking_effort`而让旧writer继续读空`reasoning`。

- [ ] **Step 2: 增加nested residual的同格式重建／跨格式loss**

```python
def nested_extensions_for(self, wire_format: str) -> dict[str, dict[str, Any]]:
    if not self.nested_extensions:
        return {}
    if self.source_format == wire_format:
        return {name: dict(fields) for name, fields in self.nested_extensions.items()}
    for name, fields in self.nested_extensions.items():
        for key in sorted(fields):
            self.conversion.record(
                LossCode.EXTENSIONS_NOT_CARRIED,
                f"from {self.source_format} into {wire_format}: {name}.{key}",
            )
    return {}
```

两侧writer必须先合并同格式nested residual，再覆盖自己拥有的`effort`，避免residual反向覆盖规范字段。

- [ ] **Step 3: 扩展request reader协议并传source headers**

把`InboundTranslator`改为Protocol：

```python
class RequestReader(Protocol):
    def __call__(
        self,
        payload: Mapping[str, Any],
        *,
        source_headers: Mapping[str, str] | None = None,
        translated: bool = False,
    ) -> SemanticRequest: ...
```

`TranslatorRegistry.translate()`新增`source_headers`，并以`translated=source is not target`调用reader。两侧reader先接受这些keyword并保持当前行为。

- [ ] **Step 4: 在path policy清空前捕获source headers，send与count共用**

在`handle()`与`handle_count_tokens()`调用`shape_request()`前执行：

```python
source_headers = dict(context.client_headers)
```

随后send与count两处现有`chain.translators.translate`调用都传`source_headers=source_headers`。不得把该快照重新写回`context.client_headers`；translation path仍按现有空whitelist向upstream转发零客户端header。

- [ ] **Step 5: 运行source-header与residual直接探针**

用自建`TranslatorRegistry`验证reader收到已归一的`anthropic-beta`与`translated=True`；直接构造SemanticRequest验证同格式nested residual重建及跨格式精确loss：

```bash
PYTHONPATH=src uv run python - <<'PY'
from app.pipeline.request import WireFormat
from app.pipeline.translation_driver.registry import TranslatorRegistry
from app.pipeline.translation_driver.semantic import SemanticRequest, TranslationTarget

captured = {}
def reader(payload, *, source_headers=None, translated=False):
    captured.update(headers=dict(source_headers or {}), translated=translated)
    return SemanticRequest(model="m", source_format="anthropic-messages")

registry = TranslatorRegistry()
registry.register_inbound(WireFormat.ANTHROPIC_MESSAGES, reader)
registry.register_outbound(WireFormat.OPENAI_RESPONSES, lambda request, target: {})
registry.translate(
    {"model": "m"},
    source=WireFormat.ANTHROPIC_MESSAGES,
    target=WireFormat.OPENAI_RESPONSES,
    target_model=TranslationTarget(),
    source_headers={"anthropic-beta": "mid-conversation-output-config-2026-07-01"},
)
assert captured == {"headers": {"anthropic-beta": "mid-conversation-output-config-2026-07-01"}, "translated": True}
request = SemanticRequest(
    model="m",
    source_format="openai-responses",
    nested_extensions={"reasoning": {"summary": "auto"}},
)
assert request.nested_extensions_for("openai-responses") == {"reasoning": {"summary": "auto"}}
assert request.nested_extensions_for("anthropic-messages") == {}
assert request.conversion.losses[-1].detail.endswith("reasoning.summary")
PY
```

- [ ] **Step 6: 补IR、reader协议、header与nested residual测试**

代表性测试：

```python
def test_nested_extensions_for_preserves_same_format_and_records_cross_format_fields() -> None:
    request = SemanticRequest(
        model="m",
        source_format="openai-responses",
        nested_extensions={"reasoning": {"summary": "auto"}},
    )
    assert request.nested_extensions_for("openai-responses") == {
        "reasoning": {"summary": "auto"}
    }
    assert request.nested_extensions_for("anthropic-messages") == {}
    assert [loss.detail for loss in request.conversion.losses] == [
        "from openai-responses into anthropic-messages: reasoning.summary"
    ]
```

Task 4在Responses reader真正认领effort后再新增`test_nested_extension_reasoning_fields_are_not_counted_as_lost_effort`，验证effort不被重复计loss；Task 2不得提前消费该语义。

Task 2只用spy／monkeypatch reader验证`handle()`与`handle_count_tokens()`都传入path policy之前的source header，并断言upstream request headers仍不含`anthropic-beta`；不得用真实per-message输入作本Task证据，因为真实reader到Task 3才认领该header。真实per-message HTTP测试只属于Task 3。

- [ ] **Step 7: 运行本切片测试并提交**

Run:

```bash
uv run pytest --collect-only -q tests/unit/pipeline/translation_driver/test_translation_driver.py::test_nested_extensions_for_preserves_same_format_and_records_cross_format_fields
uv run pytest tests/unit/pipeline/translation_driver/test_translation_driver.py tests/int/test_pipeline_app.py::test_a_thinking_budget_reaches_upstream_as_an_effort_the_model_offers tests/int/test_pipeline_app.py -k 'source_header or nested_extension or same_format or thinking_budget'
uv run ruff check src/app/pipeline/translation_driver src/app/pipeline/driver.py tests/unit/pipeline/translation_driver tests/int/test_pipeline_app.py
uv run pyright src/app/pipeline/translation_driver src/app/pipeline/driver.py tests/unit/pipeline/translation_driver tests/int/test_pipeline_app.py
```

提交信息文件内容：`refactor: model thinking and effort as one intent`。只提交本Task列出的路径。

### Task 3: 实现Anthropic→Responses effort翻译

**Files:**
- Modify: `src/app/pipeline/translation_driver/reasoning.py`
- Modify: `src/app/pipeline/translation_driver/anthropic_messages.py`
- Modify: `src/app/pipeline/translation_driver/openai_responses.py:87-111,865-975`
- Modify: `src/app/pipeline/translation_driver/semantic.py`
- Test: `tests/unit/pipeline/translation_driver/test_reasoning.py`
- Test: `tests/unit/pipeline/translation_driver/test_translation_driver.py`
- Test: `tests/int/test_pipeline_app.py:3513-3615`

**Interfaces:**
- Consumes: Task 2的`ThinkingEffortIntent`、source headers与nested residual。
- Produces: `read_anthropic_thinking_effort()`、`_align_enabled_responses_effort()`和新的`_apply_reasoning()`。
- Removes in Step 6 only after production与test consumers全部切换: 活路径`BUDGET_LADDER`、`BUDGET_FLOOR`、`ADAPTIVE_EFFORT`、`ReasoningIntent`、`SemanticRequest.reasoning`、`resolve()`及budget→档位测试。

- [ ] **Step 1: 实现Anthropic顶层thinking／effort解析**

合法Anthropic effort常量：

```python
ANTHROPIC_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
RESPONSES_EFFORTS = frozenset({"none", "minimal", *ANTHROPIC_EFFORTS})
```

Reader规则：`thinking`缺席／adaptive为enabled，disabled为false；translated path兼容auto、缺budget enabled、正整数低budget和超官方max关系budget并记录compatibility；非对象、未知type、bool／非int／非正budget拒绝。所有budget记录未携带但不决定effort。`output_config.effort`显式值优先，缺席为high；`output_config`非对象、effort非字符串或不在五档时以精确field path拒绝；其余output_config字段放入nested residual。

- [ ] **Step 2: 实现逐消息effort candidate、校验与折叠**

Candidate判据是“message mapping含`output_config`键”，不能先要求role／content合法，否则错误role会漏成普通消息。Header token按逗号切分并trim；控制message只允许`role／content／output_config`，其中role必须system，content只接受`""`或空list，output_config必须是只含effort的mapping，effort必须是Anthropic五档。错误使用稳定code和下列field path：message sibling→`messages[i].<key>`；role／content→对应字段；output config sibling／effort→`messages[i].output_config.<key>`；缺beta→effort字段。

```python
EFFORT_BETA = "mid-conversation-output-config-2026-07-01"
_CONTROL_MESSAGE_KEYS = frozenset({"role", "content", "output_config"})
_CONTROL_OUTPUT_KEYS = frozenset({"effort"})


def _is_effort_control_candidate(raw: object) -> bool:
    return isinstance(raw, Mapping) and "output_config" in raw


def _anthropic_beta_tokens(headers: Mapping[str, str]) -> frozenset[str]:
    return frozenset(
        token.strip()
        for token in headers.get("anthropic-beta", "").split(",")
        if token.strip()
    )


def _parse_effort_control(
    raw: Mapping[str, Any],
    *,
    index: int,
    source_headers: Mapping[str, str],
) -> str:
    field = f"messages[{index}]"
    extra = raw.keys() - _CONTROL_MESSAGE_KEYS
    if extra:
        key = sorted(extra)[0]
        raise TranslationRefused(f"unsupported effort control field {key!r}", code="effort-control-invalid", field_path=f"{field}.{key}")
    if raw.get("role") != "system":
        raise TranslationRefused("effort control role must be system", code="effort-control-invalid", field_path=f"{field}.role")
    content = raw.get("content")
    if content != "" and content != []:
        raise TranslationRefused("effort control content must be empty", code="effort-control-invalid", field_path=f"{field}.content")
    output = raw.get("output_config")
    if not isinstance(output, Mapping):
        raise TranslationRefused("effort control output_config must be an object", code="effort-control-invalid", field_path=f"{field}.output_config")
    output_extra = output.keys() - _CONTROL_OUTPUT_KEYS
    if output_extra:
        key = sorted(output_extra)[0]
        raise TranslationRefused(f"unsupported effort control output field {key!r}", code="effort-control-invalid", field_path=f"{field}.output_config.{key}")
    effort = output.get("effort")
    if not isinstance(effort, str) or effort not in ANTHROPIC_EFFORTS:
        raise TranslationRefused("invalid per-message effort", code="effort-invalid", field_path=f"{field}.output_config.effort")
    if EFFORT_BETA not in _anthropic_beta_tokens(source_headers):
        raise TranslationRefused("per-message effort requires its beta header", code="beta-required", field_path=f"{field}.output_config.effort")
    return effort


def _effective_per_message_effort(
    messages: list[object],
    *,
    source_headers: Mapping[str, str],
    baseline: str,
    baseline_source: EffortSource,
) -> tuple[str, list[object], EffortSource]:
    active = baseline
    source = baseline_source
    pending: str | None = None
    filtered: list[object] = []
    for index, raw in enumerate(messages):
        if _is_effort_control_candidate(raw):
            pending = _parse_effort_control(
                cast(Mapping[str, Any], raw),
                index=index,
                source_headers=source_headers,
            )
            continue
        filtered.append(raw)
        if isinstance(raw, Mapping) and raw.get("role") == "user" and pending is not None:
            active = pending
            source = EffortSource.ANTHROPIC_PER_MESSAGE
            pending = None
    return active, filtered, source
```

来源由控制是否实际作用于user turn决定，不能以“值是否改变”判断：top-level与逐消息都为high时，逐消息仍是实际来源。Future-only尾部control从target input移除但不改变本次active／source；original payload不改。该过滤必须在`_message_from_anthropic()`列表推导之前运行，普通message parser永远看不到已认领control；错误role／shape也不会先被普通parser吞掉。

- [ ] **Step 3: 用effort字段替代budget resolver**

Forward enabled只从target capabilities排除none后的集合对齐；known-only-none拒绝，capability None／empty／unrankable按Spec记录not-carried。Disabled必须明确支持none，否则拒绝。删除budget ladder及其调用，保留`align_effort()`供direct Anthropic subscriber和两向档位对齐。

在`openai_responses.py`的wire边界实现：

```python
def _align_enabled_responses_effort(
    desired: str,
    capabilities: tuple[str, ...] | None,
) -> ReasoningResolution:
    if capabilities is not None and capabilities and set(capabilities) <= {"none"}:
        raise TranslationRefused(
            "target model offers only disabled reasoning",
            code="reasoning-enable-not-supported",
            field_path="output_config.effort",
        )
    filtered = None if capabilities is None else tuple(value for value in capabilities if value != "none")
    return align_effort(desired, filtered)
```

- [ ] **Step 4: 一次切换全部production旧consumer，暂不删除定义**

重写Responses writer `_apply_reasoning()`：disabled写`reasoning.effort=none`；enabled用intent effort；intent不存在才省略reasoning。同步重写Anthropic writer `_restore_thinking()`，让`source_format=="anthropic-messages"`的同格式重建从`thinking_effort`和`nested_extensions["thinking"]`恢复，而不是继续读旧`reasoning`；Responses source的profile渲染明确留给Task 4，此时不得无profile猜target shape。确认`from_anthropic_messages()`、`to_openai_responses()`、`to_anthropic_messages()`都不再访问旧field，但保留`SemanticRequest.reasoning`、`ReasoningIntent`、budget ladder和`resolve()`定义直到Step 6迁移完test consumers。合并同格式`reasoning` residual时，writer拥有的effort最后覆盖。Literal ultracode在reader返回`TranslationRefused(code="effort-invalid", field_path="output_config.effort")`。

- [ ] **Step 5: 运行生产入口直接探针**

在`PYTHONPATH=src:tests/int uv run python`脚本中直接调用`test_pipeline_app.make_client()`验证：省略thinking／effort发high；adaptive+xhigh按catalog对齐；相同effort配两个不同budget得到相同wire；disabled target有none发none、无none返回400且upstream调用0；per-message xhigh覆盖top-level medium；future-only控制不生效；count产生相同loss且不上游。至少先运行这个正向探针：

```bash
PYTHONPATH=src:tests/int uv run python - <<'PY'
from typing import Any, cast
import httpx2
import orjson
from test_pipeline_app import make_client

client, seen = make_client(lambda _: httpx2.Response(200, json={"id": "resp_1"}))
for budget in (1024, 64000):
    response = client.post(
        "/v1/messages",
        json={
            "model": "reasoning-model",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 64,
            "thinking": {"type": "enabled", "budget_tokens": budget},
            "output_config": {"effort": "xhigh"},
        },
    )
    assert response.status_code == 200
wires = [cast(dict[str, Any], orjson.loads(request.read())) for request in seen[-2:]]
assert [wire["reasoning"] for wire in wires] == [{"effort": "high"}, {"effort": "high"}]
PY
```

- [ ] **Step 6: 更新单元与HTTP测试**

按以下顺序迁移并删除，不能重排：

1. 删除钉住1k／8k／16k／24k／32k budget阶梯的旧测试，换成静态effort expected。`tests/unit/pipeline/translation_driver/test_reasoning.py`逐项移除`ReasoningIntent／ReasoningIntentInvalid／intent_from_thinking／resolve／unused_thinking_fields` imports与全部consumer：budget／adaptive／disabled resolver测试删除或改写为writer完整wire测试；thinking shape／invalid budget／unused sibling测试迁到`test_translation_driver.py`并经真实Anthropic reader；`align_effort`及profile纯函数测试保留。
2. Production旧definitions仍存在时，运行`uv run pytest --collect-only -q tests/unit/pipeline/translation_driver/test_reasoning.py tests/unit/pipeline/translation_driver/test_translation_driver.py`；必须无collection import error。
3. 在下列七个确切文件上运行同一legacy-symbol scan；不得扩大到全仓通用`resolve()`：

```bash
rg -n \
  -e '\bReasoningIntent\b' \
  -e '\bReasoningIntentInvalid\b' \
  -e '\bintent_from_thinking\b' \
  -e '\bunused_thinking_fields\b' \
  -e '\bBUDGET_LADDER\b' \
  -e '\bBUDGET_FLOOR\b' \
  -e '\bADAPTIVE_EFFORT\b' \
  -e '^def _desired\(' \
  -e '^def _resolve\(' \
  -e '^def resolve\(' \
  -e '^[[:space:]]+resolve,$' \
  -e 'import .*\bresolve\b' \
  -e '[^.]\bresolve\(' \
  -- \
  src/app/pipeline/translation_driver/reasoning.py \
  src/app/pipeline/translation_driver/semantic.py \
  src/app/pipeline/translation_driver/anthropic_messages.py \
  src/app/pipeline/translation_driver/openai_responses.py \
  tests/unit/pipeline/translation_driver/test_reasoning.py \
  tests/unit/pipeline/translation_driver/test_translation_driver.py \
  tests/int/test_pipeline_app.py
```

只允许`reasoning.py`／`semantic.py`中下一步要删除的definitions；任何consumer命中都先修复。
4. 删除`SemanticRequest.reasoning`、`ReasoningIntent`、`ReasoningIntentInvalid`、`intent_from_thinking`、`unused_thinking_fields`、`BUDGET_LADDER／BUDGET_FLOOR／ADAPTIVE_EFFORT`、`_desired()`、`_resolve()`与`resolve()`。
5. 逐字重跑第3步同一命令，要求零命中；再运行同一`pytest --collect-only -q`，确认最终状态仍可collection。

随后覆盖Spec REQ-05A正向控制族；每个测试断言完整`reasoning`对象、精确loss code／field path和upstream调用数。固定创建供Step 7使用的node：`test_omitted_anthropic_effort_sends_high`、`test_enabled_intent_rejects_a_none_only_target`、`test_per_message_effort_overrides_top_level_and_is_not_prompt_content`、`test_future_only_effort_control_does_not_apply`、`test_direct_anthropic_leg_bypasses_effort_translation`。

代表性测试：

```python
def test_explicit_effort_wins_and_budget_never_selects_the_level() -> None:
    registry = default_registry()

    def translate(budget: int) -> tuple[dict[str, Any], SemanticRequest]:
        return registry.translate(
            {
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "thinking": {"type": "enabled", "budget_tokens": budget},
                "output_config": {"effort": "xhigh"},
            },
            source=WireFormat.ANTHROPIC_MESSAGES,
            target=WireFormat.OPENAI_RESPONSES,
            target_model=TranslationTarget(
                model_id="m",
                reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
            ),
        )

    first_wire, first_semantic = translate(1024)
    second_wire, second_semantic = translate(64000)
    assert first_wire["reasoning"] == {"effort": "xhigh"}
    assert second_wire["reasoning"] == first_wire["reasoning"]
    for semantic in (first_semantic, second_semantic):
        assert any("thinking.budget_tokens" in loss.detail for loss in semantic.conversion.losses)
```

- [ ] **Step 7: 执行REQ-05A正向有限单侧控制并安全恢复**

先建立当前WIP快照与binary diff；每轮只用Edit改变一个分支，绝不使用`git checkout／restore`：

```bash
cp src/app/pipeline/translation_driver/anthropic_messages.py "$CLAUDE_JOB_DIR/tmp/task3-anthropic_messages.py.good"
cp src/app/pipeline/translation_driver/openai_responses.py "$CLAUDE_JOB_DIR/tmp/task3-openai_responses.py.good"
cp src/app/pipeline/driver.py "$CLAUDE_JOB_DIR/tmp/task3-driver.py.good"
git diff --binary -- src/app/pipeline/translation_driver/anthropic_messages.py src/app/pipeline/translation_driver/openai_responses.py src/app/pipeline/driver.py > "$CLAUDE_JOB_DIR/tmp/task3-before.patch"
```

逐轮执行并核对失败来自指定完整wire／loss／调用次数断言：①忽略`output_config.effort`，`test_explicit_effort_wins_and_budget_never_selects_the_level`红；②用budget重新选档，同一测试红；③省略Anthropic默认high，`test_omitted_anthropic_effort_sends_high`红；④enabled候选保留none，`test_enabled_intent_rejects_a_none_only_target`红；⑤跳过beta校验或不移除控制message，`test_per_message_effort_overrides_top_level_and_is_not_prompt_content`红；⑥让future-only control提前生效，`test_future_only_effort_control_does_not_apply`红；⑦让direct Anthropic leg调用translator，`test_direct_anthropic_leg_bypasses_effort_translation`红。

每轮测试后立即从对应`.good`恢复；最后执行：

```bash
cp "$CLAUDE_JOB_DIR/tmp/task3-anthropic_messages.py.good" src/app/pipeline/translation_driver/anthropic_messages.py
cp "$CLAUDE_JOB_DIR/tmp/task3-openai_responses.py.good" src/app/pipeline/translation_driver/openai_responses.py
cp "$CLAUDE_JOB_DIR/tmp/task3-driver.py.good" src/app/pipeline/driver.py
git diff --binary -- src/app/pipeline/translation_driver/anthropic_messages.py src/app/pipeline/translation_driver/openai_responses.py src/app/pipeline/driver.py > "$CLAUDE_JOB_DIR/tmp/task3-after.patch"
cmp "$CLAUDE_JOB_DIR/tmp/task3-before.patch" "$CLAUDE_JOB_DIR/tmp/task3-after.patch"
uv run pytest tests/unit/pipeline/translation_driver/test_translation_driver.py tests/int/test_pipeline_app.py -k 'explicit_effort or omitted_anthropic_effort or none_only_target or per_message_effort or future_only_effort or direct_anthropic_leg'
```

Expected: 每个mutation的目标测试非零且失败原因命中目标断言；恢复后`cmp`与pytest退出0。

- [ ] **Step 8: 运行本切片验证并提交**

Run:

```bash
uv run pytest tests/unit/pipeline/translation_driver/test_reasoning.py tests/unit/pipeline/translation_driver/test_translation_driver.py tests/int/test_pipeline_app.py -k 'effort or thinking or count'
uv run ruff check src/app/pipeline/translation_driver src/app/pipeline/driver.py tests/unit/pipeline/translation_driver tests/int/test_pipeline_app.py
uv run pyright src/app/pipeline/translation_driver src/app/pipeline/driver.py tests/unit/pipeline/translation_driver tests/int/test_pipeline_app.py
```

提交信息文件内容：`feat: translate Anthropic effort to Responses`。只提交本Task路径。

### Task 4: 实现Responses→Anthropic effort与thinking profile翻译

**Files:**
- Modify: `src/app/pipeline/translation_driver/openai_responses.py:87-111`
- Modify: `src/app/pipeline/translation_driver/anthropic_messages.py:229-281`
- Modify: `src/app/pipeline/translation_driver/reasoning.py`
- Modify: `src/app/pipeline/translation_driver/semantic.py`
- Test: `tests/unit/pipeline/translation_driver/test_reasoning.py`
- Test: `tests/unit/pipeline/translation_driver/test_translation_driver.py`
- Test: `tests/int/test_pipeline_app.py:2934-2965`

**Interfaces:**
- Consumes: Task 1的`TranslationTarget.thinking_profile`／pattern与Task 2的统一IR。
- Produces: `read_responses_thinking_effort()`、`render_anthropic_thinking()`。

- [ ] **Step 1: 解析Responses reasoning对象**

Absent reasoning→intent None；non-object拒绝；effort absent／null→enabled且effort None；none→disabled；minimal／五档→enabled；unknown／literal ultracode拒绝。`summary／context／mode`等兄弟字段进入nested residual。

- [ ] **Step 2: 按profile渲染target thinking shape**

```python
def render_anthropic_thinking(
    intent: ThinkingEffortIntent,
    target: TranslationTarget,
    *,
    max_tokens: int | None,
) -> dict[str, Any]:
    profile = target.thinking_profile
    if profile is None:
        raise TranslationRefused("no thinking profile matches the resolved model", code="thinking-profile-missing", field_path="reasoning")
    if not intent.enabled:
        if not profile.can_disable:
            raise TranslationRefused("target model cannot disable thinking", code="thinking-disable-not-supported", field_path="reasoning.effort")
        if profile.disabled_max_effort is not None and EFFORT_LADDER.index("high") > EFFORT_LADDER.index(profile.disabled_max_effort):
            raise TranslationRefused("target model cannot disable thinking at its effective effort", code="thinking-disable-effort-not-supported", field_path="reasoning.effort")
        return {"type": "disabled"}
    for mode in profile.modes:
        if mode == "adaptive":
            return {"type": "adaptive"}
        budget = profile.manual_budget_tokens
        if mode == "enabled" and budget is not None and max_tokens is not None and budget < max_tokens:
            return {"type": "enabled", "budget_tokens": budget}
    raise TranslationRefused("target thinking profile has no renderable mode", code="thinking-mode-not-renderable", field_path="reasoning")
```

实现时在disabled分支把缺失`disabled_max_effort`读作无额外上限；存在上限时以Anthropic省略effort的有效high检查。Profile source pattern在成功与拒绝路径都必须可观察。

- [ ] **Step 3: 对齐Anthropic output_config.effort**

Minimal先转desired low并固定记录approximation；五档同名。目标effort候选为catalog发布集合与五档交集；exact／downward／floor调用`align_effort()`，missing／empty／unrankable省略output_config并记not-carried，但不撤销已渲染thinking。Reasoning effort none不附output_config。

- [ ] **Step 4: 合并Anthropic residual并保持direct leg不变**

`to_anthropic_messages()`只在translated writer调用profile；同格式residual先重建`output_config`，再由writer覆盖effort。Direct `/v1/messages`不经过该函数，现有`anthropic_thinking` subscriber行为不改。

- [ ] **Step 5: 运行反向生产入口探针**

用公开`POST /responses`路由分别指向：adaptive profile、always-on profile、extended-only无budget、用户override `[enabled,adaptive]` 有／无可用budget、profile missing。断言完整upstream Anthropic body、HTTP 400、精确param和upstream调用数。验证`none`在always-on拒绝，minimal在adaptive target发`thinking.adaptive＋output_config.low`，extended-only override发manual shape。先把`tests/int/test_pipeline_app.py`的`claude-model`catalog fixture补上`reasoning_effort=[low,medium,high,xhigh,max]`，再运行：

```bash
PYTHONPATH=src:tests/int uv run python - <<'PY'
from typing import Any, cast
import httpx2
import orjson
from test_pipeline_app import make_client

body = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "content": [],
    "model": "claude-model",
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 1, "output_tokens": 1},
}
overrides = {
    "model_translation": {
        "to_anthropic_messages": {
            "thinking_profiles": {
                "claude-model": {"modes": ["adaptive"], "can_disable": True}
            }
        }
    }
}
client, seen = make_client(lambda _: httpx2.Response(200, json=body), overrides=overrides)
response = client.post(
    "/responses",
    json={"model": "claude-model", "input": [], "reasoning": {"effort": "minimal"}},
)
assert response.status_code == 200
wire = cast(dict[str, Any], orjson.loads(seen[-1].read()))
assert wire["thinking"] == {"type": "adaptive"}
assert wire["output_config"] == {"effort": "low"}
PY
```

- [ ] **Step 6: 补反向单元与HTTP测试**

覆盖六条bundled profile正域和三个负域、最后fullmatch、modes逐项fallback、config-time与request-time budget边界、effort exact／downward／floor／not-carried、null／absent、nested reasoning residual、literal ultracode。固定创建：`test_profile_modes_fall_through_to_adaptive`、`test_always_on_profile_rejects_none`、`test_extended_only_profile_never_invents_budget`、`test_missing_profile_rejects`、`test_minimal_maps_to_low_and_records_approximation`、`test_nested_extension_reasoning_fields_are_not_counted_as_lost_effort`、`test_direct_responses_leg_bypasses_effort_translation`。

- [ ] **Step 7: 执行REQ-05A反向有限单侧控制并安全恢复**

快照本方向会改的production文件与当前diff：

```bash
cp src/app/pipeline/translation_driver/anthropic_messages.py "$CLAUDE_JOB_DIR/tmp/task4-anthropic_messages.py.good"
cp src/app/pipeline/translation_driver/openai_responses.py "$CLAUDE_JOB_DIR/tmp/task4-openai_responses.py.good"
cp src/app/pipeline/routing.py "$CLAUDE_JOB_DIR/tmp/task4-routing.py.good"
cp src/app/config/bundled-config.yaml "$CLAUDE_JOB_DIR/tmp/task4-bundled-config.yaml.good"
git diff --binary -- src/app/pipeline/translation_driver/anthropic_messages.py src/app/pipeline/translation_driver/openai_responses.py src/app/pipeline/routing.py src/app/config/bundled-config.yaml > "$CLAUDE_JOB_DIR/tmp/task4-before.patch"
```

逐轮只做一项：①selector遇首个match立即返回，last-match override测试红；②恢复第六条过宽regex，三个负域测试红；③第一个enabled mode不可渲染时立即拒绝，fallback测试红；④允许always-on disabled，零upstream测试红；⑤extended-only缺budget时合成budget，对应拒绝测试红；⑥profile missing时省略thinking，missing-profile测试红；⑦minimal不记approximation，loss测试红；⑧删除reasoning sibling merge，同格式完整对象／跨格式精确loss测试红；⑨让direct Responses leg进入translator，byte-equivalent bypass测试红。

逐轮恢复对应snapshot；最后执行：

```bash
cp "$CLAUDE_JOB_DIR/tmp/task4-anthropic_messages.py.good" src/app/pipeline/translation_driver/anthropic_messages.py
cp "$CLAUDE_JOB_DIR/tmp/task4-openai_responses.py.good" src/app/pipeline/translation_driver/openai_responses.py
cp "$CLAUDE_JOB_DIR/tmp/task4-routing.py.good" src/app/pipeline/routing.py
cp "$CLAUDE_JOB_DIR/tmp/task4-bundled-config.yaml.good" src/app/config/bundled-config.yaml
git diff --binary -- src/app/pipeline/translation_driver/anthropic_messages.py src/app/pipeline/translation_driver/openai_responses.py src/app/pipeline/routing.py src/app/config/bundled-config.yaml > "$CLAUDE_JOB_DIR/tmp/task4-after.patch"
cmp "$CLAUDE_JOB_DIR/tmp/task4-before.patch" "$CLAUDE_JOB_DIR/tmp/task4-after.patch"
uv run pytest tests/unit/config/test_config_loading.py tests/unit/pipeline/translation_driver/test_translation_driver.py tests/int/test_pipeline_app.py -k 'thinking_profile or always_on or extended_only or missing_profile or minimal_maps or nested_extension or direct_responses_leg'
```

Expected: 每个mutation因目标断言非零；恢复后binary diff相等且目标组通过。

- [ ] **Step 8: 运行本切片验证并提交**

Run:

```bash
uv run pytest tests/unit/pipeline/translation_driver/test_reasoning.py tests/unit/pipeline/translation_driver/test_translation_driver.py tests/int/test_pipeline_app.py -k 'responses_to_anthropic or thinking_profile or reasoning_effort'
uv run ruff check src/app/pipeline/translation_driver tests/unit/pipeline/translation_driver tests/int/test_pipeline_app.py
uv run pyright src/app/pipeline/translation_driver tests/unit/pipeline/translation_driver tests/int/test_pipeline_app.py
```

提交信息文件内容：`feat: translate Responses effort to Anthropic`。只提交本Task路径。

### Task 5: 持久化profile facts、执行完整接线验收并收口

**Files:**
- Modify: `src/app/pipeline/translation_driver/semantic.py`
- Modify: `src/app/pipeline/translation_driver/anthropic_messages.py`
- Modify: `src/app/pipeline/driver.py`
- Modify: `src/app/observability/request_trace.py:112-132,135-203,211-250`
- Modify: `src/app/observability/request_log.py:103-157`
- Modify: `src/app/server/routes/inference.py:226-287,572`
- Test: `tests/unit/observability/test_request_log.py`
- Test: `tests/unit/observability/test_request_log_file.py`
- Test: `tests/int/test_pipeline_app.py`
- Create: `.dev/human-controlled-docs-candidates/effort-thinking-profiles-config-example.md`
- Modify: `.dev/docs/anthropic-responses-bridge/implementation.md`

**Interfaces:**
- Produces: `ConversionFact(code, detail)`与`Conversion.facts`，以及RequestLine的durable `facts`字段。
- Consumes: Task 1 profile pattern与Task 3／4 mapping结果。

- [ ] **Step 1: 增加非loss conversion facts**

```python
class ConversionFactCode(StrEnum):
    THINKING_PROFILE_SELECTED = "thinking-profile-selected"
    THINKING_PROFILE_REJECTED = "thinking-profile-rejected"

@dataclass(frozen=True, slots=True)
class ConversionFact:
    code: ConversionFactCode
    detail: str = ""

@dataclass(slots=True)
class Conversion:
    losses: list[Loss] = field(default_factory=list)
    facts: list[ConversionFact] = field(default_factory=list)

    def observe(self, code: ConversionFactCode, detail: str = "") -> None:
        self.facts.append(ConversionFact(code, detail))

class TranslationRefused(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        field_path: str,
        facts: tuple[ConversionFact, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field_path = field_path
        self.facts = facts
```

`lossless`只看losses，不因观察事实变false。Profile writer在选择pattern后先observe selected；拒绝前observe rejected，并把`tuple(request.conversion.facts)`放入`TranslationRefused.facts`，使异常路径也能持久化来源与原因。

- [ ] **Step 2: 从translation到RequestContext传递facts**

Send与count共用一个复制helper，并在成功与`TranslationRefused`两条出口都调用：

```python
def _keep_conversion_facts(context: RequestContext, facts: Sequence[ConversionFact]) -> None:
    if facts:
        context.extras["conversion_facts"] = list(facts)


def _translate_with_facts(
    chain: Chain,
    context: RequestContext,
    route: Route,
    provider: ModelProvider,
    source_headers: Mapping[str, str],
) -> tuple[dict[str, Any], SemanticRequest]:
    target = translation_target(provider, route.model_id, chain.thinking_profiles)
    try:
        translated, semantic = chain.translators.translate(
            context.payload,
            source=route.inbound_format,
            target=route.target_format,
            target_model=target,
            source_headers=source_headers,
        )
    except TranslationRefused as refusal:
        _keep_conversion_facts(context, refusal.facts)
        raise
    _keep_conversion_facts(context, semantic.conversion.facts)
    return translated, semantic
```

两处真实调用不能复制这段`try／except`后各自漂移：抽成共享helper或共享translate wrapper。Profile成功选择时记录resolved model与匹配pattern；profile missing／not renderable记录model、候选pattern与稳定原因。不得把pattern写成loss。

- [ ] **Step 3: 把facts写入durable request record**

`RequestTrace`和`RequestLine`新增`facts: tuple[dict[str, str], ...]`；`_translation_facts()`只接收`ConversionFact`并输出code/detail；把`absorb_losses()`重命名为`absorb_conversion()`，同时重算losses与facts，并更新`server/routes/inference.py`的五个调用点。`write_request_record()`继续通过`asdict()`自动持久化。Console line不新增字段。

- [ ] **Step 4: 补facts持久化与失败路径测试**

断言profile exact success、user override success、always-on reject、profile missing和count path都在durable JSONL record的`facts`数组保留exact code／detail；error message只能作附加断言，不能替代该槽。一个无profile需求的direct request保持`facts=[]`。`anthropic_messages.py`的profile writer必须在成功时observe selected，在always-on／missing／unrenderable拒绝前observe rejected并把当前facts附进`TranslationRefused`；该producer文件属于本Task提交。

增加`tests/int/test_pipeline_app.py::test_rejected_thinking_profile_facts_reach_jsonl`并执行一次安全单侧控制。先快照当前WIP：

```bash
cp src/app/pipeline/driver.py "$CLAUDE_JOB_DIR/tmp/task5-driver.py.good"
git diff --binary -- src/app/pipeline/driver.py > "$CLAUDE_JOB_DIR/tmp/task5-driver-before.patch"
```

只用Edit切断`except TranslationRefused`分支的`_keep_conversion_facts(context, refusal.facts)`，保留success copy、writer facts和error message；随后无论测试结果如何都恢复：

```bash
set +e
uv run pytest tests/int/test_pipeline_app.py::test_rejected_thinking_profile_facts_reach_jsonl
mutation_rc=$?
set -e
cp "$CLAUDE_JOB_DIR/tmp/task5-driver.py.good" src/app/pipeline/driver.py
git diff --binary -- src/app/pipeline/driver.py > "$CLAUDE_JOB_DIR/tmp/task5-driver-after.patch"
cmp "$CLAUDE_JOB_DIR/tmp/task5-driver-before.patch" "$CLAUDE_JOB_DIR/tmp/task5-driver-after.patch"
if [[ $mutation_rc -eq 0 ]]; then
  printf 'exception-copy mutation did not make the JSONL facts assertion fail\n'
  exit 1
fi
uv run pytest tests/int/test_pipeline_app.py::test_rejected_thinking_profile_facts_reach_jsonl
```

Expected: mutation轮因JSONL`facts`为空而非error message变化失败；binary diff恢复相等；最终正样本通过。不得只测`Conversion.observe()`。

- [ ] **Step 5: 创建人控配置样例候选并同步Implementation**

在`.dev/human-controlled-docs-candidates/effort-thinking-profiles-config-example.md`写出六条bundled defaults、用户last-fullmatch override示例、manual budget约束和“不修改direct leg”说明；明确它是候选，不修改`docs/.human-controlled/config.example.yaml`。Implementation记录实际代码提交、测试命令与尚未运行的LIVE-CANARY边界，不复制可变测试数量。

- [ ] **Step 6: 运行REQ-05A关键路径与全量验证**

先用公开HTTP入口运行关键组：

```bash
uv run pytest tests/unit/config/test_config_schema.py tests/unit/config/test_config_loading.py tests/unit/pipeline/translation_driver/test_reasoning.py tests/unit/pipeline/translation_driver/test_translation_driver.py tests/unit/observability/test_request_log.py tests/unit/observability/test_request_log_file.py tests/int/test_pipeline_app.py -k 'effort or thinking_profile or per_message or source_header or conversion_fact'
```

再运行项目规定全量验证：

```bash
uv run ruff check src tests
uv run pyright src tests
uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

Expected: 三条命令退出0。若全量存在与本轮无关的共享基线失败，保留完整输出并证明本轮targeted组仍通过；不得把targeted green外推为全量通过。

- [ ] **Step 7: 独立代码评审并处置**

使用`my-skills:let-agent-review`派一个未参与实现的reviewer，报告落`.dev/docs/anthropic-responses-bridge/reports/`；核查Spec C1～C12、REQ-05A、真实route接线、profile正负域、send／count、direct bypass、facts持久化。收到报告后使用`my-skills:checking-review-report`逐条处置，复评到0 blocker／0 major；只剩minor可合，但不得把文档R4替代代码review。

- [ ] **Step 8: 提交代码与文档收口**

代码提交信息文件内容：`feat: complete effort translation`；只提交Task 5代码／测试路径。`.dev`在其独立仓库另作`docs: record effort translation implementation`提交，只含candidate、Implementation与本轮代码review／disposition文件。不得推送。

- [ ] **Step 9: 最终边界判断**

加载`my-skills:closing-out-work-at-a-boundary`，核对：代码worktree clean；每个评审finding终态；临时`.venv`只在保留的实现worktree中作为ignored dependency环境，不当作需提交产物；主仓未触碰他人WIP；`.dev`无本轮未提交文件；LIVE-CANARY未运行时明确写未运行。只有这些事实成立才报告implementation complete。

`.dev`只存在于主工作树。执行Task 5的candidate、Implementation与review文档步骤前，先保留并退出code worktree、回到主仓更新独立`.dev`仓库；不得在code worktree创建`.dev`副本。需要继续改code时再进入原worktree路径。

## Plan Self-review

| Spec义务 | 实施Task | 可判别证据 |
|---|---|---|
| `ThinkingEffortIntent`分开enabled与effort，budget不定档 | Task 2、3 | 统一IR类型；同effort不同budget产生相同wire |
| Anthropic缺省high、显式五档、disabled优先、enabled排除none | Task 3 | 公开`/v1/messages`完整upstream body与零调用400 |
| 逐消息effort、beta、future-only、send／count同形 | Task 2、3 | source header在path policy前捕获；HTTP与count parity测试 |
| Responses七值、none／minimal与五档反向映射 | Task 4 | 公开`/responses`完整Anthropic body与loss |
| 配置profile唯一来源、bundled官方正则表、用户最后match覆盖 | Task 1、4 | 六条正域／三条负域、override与profile source facts |
| adaptive／extended-only／always-on／disabled／manual budget全域 | Task 1、4 | `[enabled,adaptive]`fallback、only-enabled reject、always-on reject、budget两阶段测试 |
| nested sibling同格式重建、跨格式精确loss | Task 2、3、4 | 静态完整对象与显式缺席断言 |
| ultracode只按xhigh，literal拒绝 | Task 3、4 | xhigh正样本与literal零upstream负样本 |
| direct legs原样 | Task 2、3、4 | byte-equivalent direct bypass测试 |
| profile来源／拒绝原因进入durable record | Task 5 | RequestLine／JSONL facts与失败路径integration |
| 不复活legacy converter、不建证明控制面 | 全局、Task 5 | import／调用检索；复用现有pytest、request record与review流程 |

Self-review结论：Spec的request-level effort义务均有owner和可判别入口；没有TBD／TODO／“类似Task”占位符。`ThinkingTargetProfile`、`ThinkingEffortIntent`、`source_headers`、`nested_extensions_for`和`ConversionFact`的定义先于所有消费者；后续Task引用的名称与产生Task一致。

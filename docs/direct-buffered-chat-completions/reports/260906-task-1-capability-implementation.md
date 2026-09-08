# Task 1 capability implementation report

STATUS: DONE

## 基线与提交

- Base：`f97d243f9431d836861ce5e9938605df56b37478`
- Head：`38979123336a622a02424645ffbcad3822136c2f`
- Branch：`worktree-agent-ad77363b71744709c`
- Worktree：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-ad77363b71744709c`
- Commits：`ee07f4322e2dee35816a107c8965f8db34582099`（`feat: model Chat response capabilities`）；`38979123336a622a02424645ffbcad3822136c2f`（`test: complete Chat capability fixtures`）

## Exact files

- `src/app/model_provider/types.py`
- `src/app/model_provider/__init__.py`
- `src/app/model_provider/github_copilot.py`
- `src/app/model_provider/codebuddy.py`
- `src/app/model_provider/xingchen/provider.py`
- `src/app/pipeline/error_classify.py`
- `tests/unit/model_provider/test_model_provider.py`
- `tests/unit/model_provider/test_codebuddy.py`
- `tests/unit/model_provider/xingchen/test_provider.py`
- `tests/unit/pipeline/test_error_classify.py`

`.dev`进度与本报告未进入source commit。

## 实现行为

- 新增closed `ChatResponseMode`，成员为`streaming`与`non_streaming`。
- 新增frozen、slotted `ChatEndpointCapabilities`，要求`response_modes`与`provenance`非空，并携带两个streaming request default与provenance。
- `ModelDescriptor`新增`chat_endpoint_capabilities` snapshot，并在构造时双向校验：声明Chat endpoint必须携带capability；未声明Chat endpoint不得携带capability。
- GitHub Copilot Chat descriptor声明两种response modes，两个defaults均为`None`，provenance为`GitHub Copilot provider catalog`。
- CodeBuddy Chat descriptor只声明streaming，include-usage default为`True`、tool default为`None`，provenance逐字为`reference compatibility assumption; P6 not run`。
- Xingchen Chat descriptor声明两种response modes，两个defaults均为`True`，provenance为`2026-09-04 protocol measurement`。
- 新增`ResponseModeNotSupported(provider, model_id, requested_mode, available_modes)`，保留四项typed facts并稳定排序available modes。
- Error classifier在generic `ProviderError`分支前将该拒绝映射为`ErrorCategory.CLIENT`、HTTP 400与`unsupported_response_mode`；未扩大`CapabilityMissing`。
- Public model-provider exports与`ProviderError` subclass exhaustiveness oracle均已更新。
- 没有新增按provider name分支；provider/catalog负责声明snapshot，pipeline后续消费者可直接解释descriptor。

## 测试与检查

### Production-first既有测试

命令：`uv run pytest tests/unit/model_provider/test_model_provider.py tests/unit/model_provider/test_codebuddy.py tests/unit/model_provider/xingchen/test_provider.py tests/unit/pipeline/test_error_classify.py -q`

结果：exit 1，`136 passed, 1 failed in 4.93s`。唯一失败是`test_the_provider_error_subclasses_are_all_classified`发现新增`ResponseModeNotSupported`尚未进入test oracle；没有descriptor constructor失败。随后按brief Step 2／5更新exhaustiveness与targeted tests，未用neutral default掩盖失败。

### 最终targeted pytest

命令：`uv run pytest tests/unit/model_provider/test_model_provider.py tests/unit/model_provider/test_codebuddy.py tests/unit/model_provider/xingchen/test_provider.py tests/unit/pipeline/test_error_classify.py -q`

结果：exit 0，`146 passed in 2.23s`。

### Ruff

命令：`uv run ruff check src/app/model_provider/types.py src/app/model_provider/__init__.py src/app/model_provider/github_copilot.py src/app/model_provider/codebuddy.py src/app/model_provider/xingchen/provider.py src/app/pipeline/error_classify.py tests/unit/model_provider tests/unit/pipeline/test_error_classify.py`

结果：exit 0，`All checks passed!`。

### Pyright

命令：`uv run pyright src/app/model_provider/types.py src/app/model_provider/__init__.py src/app/model_provider/github_copilot.py src/app/model_provider/codebuddy.py src/app/model_provider/xingchen/provider.py src/app/pipeline/error_classify.py tests/unit/model_provider tests/unit/pipeline/test_error_classify.py`

结果：exit 0，`0 errors, 0 warnings, 0 informations`。

## Targeted test coverage

- Empty response modes拒绝。
- Empty provenance拒绝。
- Chat endpoint无capability拒绝。
- Non-Chat endpoint携带capability拒绝。
- GitHub Copilot、CodeBuddy、Xingchen三份profile逐字段断言。
- Capability snapshot的frozen dataclass与`frozenset`性质。
- `ResponseModeNotSupported`的category、status、exact message与exact OpenAI body code。
- `CapabilityMissing`负控能完成fixture construction，但得到`invalid_request`而非`unsupported_response_mode`，因此替换typed refusal会在code assertion处失败。
- `ProviderError.__subclasses__()`闭集已显式包含新类型。

## Self-review

- Scope：commit仅含brief列出的10个source／test paths；worktree中的untracked `.dev` symlink未暂存。
- Diff hygiene：whitespace检查通过；最终stat为248 insertions、2 deletions。
- 核心问题一：新Chat descriptor不能省略capability，构造时立即`ValueError`；非Chat descriptor也不能错误携带Chat capability。
- 核心问题二：unsupported response mode不会伪装成空endpoint集合；独立异常保留requested／available modes，classifier生成专用code。
- Provider declaration：三个provider只按resolved endpoint附加snapshot，不在请求期读取provider name决定行为。
- API compatibility：新descriptor字段追加在现有default字段之后，避免改变已有第三个及后续positional arguments的含义。

## Concerns

- 无阻断性concern。
- CodeBuddy profile按Spec明确仍是`P6 not run`的reference compatibility assumption；本任务遵守“不调用真实provider”，没有把它表述成上游实测。
- 验证范围严格采用brief列出的targeted pytest／Ruff／Pyright，没有声称完成全仓回归。

## 未采用路线

- Provider-wide bool：无法表达同一provider内按model／account变化的能力。
- Neutral default capability：会把“未声明”与“明确支持两种mode”混为同一状态，因此descriptor缺失直接失败。
- 复用`CapabilityMissing`：会错误声称endpoint集合为空，也无法携带requested／available modes。
- 对CodeBuddy每个parsed descriptor无条件附加Chat capability：会让非Chat或malformed injected catalog entry违反成对不变量；最终只在resolved endpoints含Chat时附加。
- Runtime按provider name选择defaults：违反descriptor snapshot合同，未采用。

## Fix round 1/5（review F-1／F-2）

### 处置

- F-1 major已修复：`tests/unit/pipeline/test_auto_mode_classifier.py`定义frozen neutral Chat capability；`RecordingProvider.describe()`只在dynamic endpoint为`OPENAI_CHAT_COMPLETIONS`时附加该snapshot，非Chat endpoint仍显式为`None`。原endpoint-boundary断言现可抵达，不再提前触发descriptor invariant。
- F-2 minor已修复：`test_response_mode_refusal_has_its_own_openai_400_body`现在分别断言`provider`、`model_id`、`requested_mode`与完整`available_modes`；enum使用identity，modes使用完整`frozenset` equality。
- Exact fix files：`tests/unit/pipeline/test_auto_mode_classifier.py`、`tests/unit/pipeline/test_error_classify.py`。
- 新commit：`38979123336a622a02424645ffbcad3822136c2f`（`test: complete Chat capability fixtures`）。

### Fix verification

- F-1最小node命令：`uv run pytest tests/unit/pipeline/test_auto_mode_classifier.py::TestTheShortCircuitIsWiredIn::test_a_chat_completions_request_is_never_answered_as_anthropic -q`。
- F-1最小node结果：exit 0，`1 passed in 2.65s`。
- 最终pytest命令：`uv run pytest tests/unit/model_provider/test_model_provider.py tests/unit/model_provider/test_codebuddy.py tests/unit/model_provider/xingchen/test_provider.py tests/unit/pipeline/test_error_classify.py tests/unit/pipeline/test_auto_mode_classifier.py::TestTheShortCircuitIsWiredIn::test_a_chat_completions_request_is_never_answered_as_anthropic -q`。
- 最终pytest结果：exit 0，`147 passed in 2.31s`。
- 最终Ruff命令：`uv run ruff check src/app/model_provider/types.py src/app/model_provider/__init__.py src/app/model_provider/github_copilot.py src/app/model_provider/codebuddy.py src/app/model_provider/xingchen/provider.py src/app/pipeline/error_classify.py tests/unit/model_provider tests/unit/pipeline/test_error_classify.py tests/unit/pipeline/test_auto_mode_classifier.py`。
- 最终Ruff结果：exit 0，`All checks passed!`。
- 最终Pyright命令：`uv run pyright src/app/model_provider/types.py src/app/model_provider/__init__.py src/app/model_provider/github_copilot.py src/app/model_provider/codebuddy.py src/app/model_provider/xingchen/provider.py src/app/pipeline/error_classify.py tests/unit/model_provider tests/unit/pipeline/test_error_classify.py tests/unit/pipeline/test_auto_mode_classifier.py`。
- 最终Pyright结果：exit 0，`0 errors, 0 warnings, 0 informations`。

### Fix self-review与concerns

- `diff --check`通过；fix commit只含两条review finding要求的两个test paths。
- Neutral snapshot只服务于dynamic test fixture，没有向production新增fallback或provider-name branch。
- 新增typed facts断言与既有exact message／wire body断言分开，能够分别判否consumer contract与wire contract。
- 无新增未采用路线；无阻断性concern。等待协调方复评，不把本轮自审冒充独立review verdict。


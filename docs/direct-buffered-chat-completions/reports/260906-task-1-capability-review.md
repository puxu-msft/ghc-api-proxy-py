# Task 1 capability review

## 评审范围

本轮评审以 `/home/xp/src/ghc-api-proxy-py/.superpowers/sdd/plan-68285e45598b/task-1-brief.md` 与调用方列出的 binding constraints 为判据，评审提交范围 `f97d243f9431d836861ce5e9938605df56b37478..ee07f4322e2dee35816a107c8965f8db34582099`。被检对象是完整 review package 中列出的 10 个 source／test 文件及提交态的相关 `ModelDescriptor` 构造点、`ProviderError` 分类闭集和已有测试接缝。Task 4／Task 5 的 plan／driver 实现不在本轮范围；本轮只检查 Task 1 是否提前迁移 payload／stream 处理。

## 总体 verdict

- SPEC COMPLIANCE：❌
- TASK QUALITY：Not approved
- Blocker 数：0
- Finding 计数：major=1，minor=1，nit=0，total=2

## Findings

### F-1 — major — 既有 Chat 测试 descriptor 未迁移，测试在到达原断言前失败

- Primary location：`tests/unit/pipeline/test_auto_mode_classifier.py:507`
- Related locations：`tests/unit/pipeline/test_auto_mode_classifier.py:630`、`tests/unit/pipeline/test_auto_mode_classifier.py:644`、`src/app/model_provider/types.py:203`
- 违反判据：Task 1 明确要求更新每一个 production／test Chat descriptor constructor；Chat endpoint 存在时 capability 必须显式非空。
- 具体 failure scenario：`test_a_chat_completions_request_is_never_answered_as_anthropic` 在第 644 行以 `ModelEndpoint.OPENAI_CHAT_COMPLETIONS` 构造 `RecordingProvider` 链。其 `describe()` 在第 507～511 行创建 Chat `ModelDescriptor`，却没有传 `chat_endpoint_capabilities`。新 `ModelDescriptor.__post_init__` 因而抛出 `ValueError("Chat endpoint requires non-null capabilities")`，测试无法进入原本要验证的 endpoint-boundary 行为。一个以 candidate source 为 `PYTHONPATH`、复现相同 constructor 的独立 probe 已得到该异常；这不是对实现者 targeted suite 的重复运行。
- 影响：已有测试套件存在确定性回归，而且实现报告第 83 行“新 Chat descriptor 不能省略 capability”的自查只验证了拒绝机制，没有完成同一句约束要求的全库 test-constructor 迁移。当前 targeted pytest 的绿色结果不能支撑“每一个 test Chat descriptor 已显式更新”。
- 修法：在该 fake provider 的 `describe()` 中按 `self._endpoint` 是否为 `OPENAI_CHAT_COMPLETIONS` 显式附加一个 frozen `ChatEndpointCapabilities`；非 Chat endpoint 继续传 `None`。随后只运行此前未被实现者运行的 `test_a_chat_completions_request_is_never_answered_as_anthropic`，再由协调方决定是否需要扩大回归范围。

### F-2 — minor — refusal测试没有锁定四项 typed facts

- Primary location：`tests/unit/pipeline/test_error_classify.py:240`
- Related location：`src/app/model_provider/types.py:94`
- 违反判据：`ResponseModeNotSupported` 的公开合同不仅是错误字符串和 wire code，还必须保留 `provider`、`model_id`、`requested_mode`、`available_modes` 四项 typed facts，供 Task 4／Task 5 消费。
- 具体 failure scenario：当前测试只通过 exact message 间接使用构造参数，并未读取异常对象的四个属性。若后续重构仍用构造参数生成同一字符串，却漏设或错设其中任一属性，现有测试仍会通过；Task 4／Task 5 一旦读取这些字段就会得到 `AttributeError` 或错误路由事实。当前 production implementation 的第 94～97 行确实正确赋值，因此这是 acceptance coverage 缺口，而不是现行 runtime failure，定级为 minor。
- 修法：在 `test_response_mode_refusal_has_its_own_openai_400_body` 中增加四项 identity／equality 断言，尤其断言 enum identity 与完整 `frozenset`，使 wire contract 与 typed consumer contract 分别可判否。

## 已核验且未发现问题的承重面

- `ChatResponseMode` 只有 `streaming`／`non_streaming` 两个成员；未发现以该 enum 为键但漏成员的 production table。三个 provider profile 的 mode/default/provenance 与 brief 逐项一致，CodeBuddy provenance 逐字包含 `P6 not run`。
- `ChatEndpointCapabilities` 与 `ModelDescriptor` 均为 frozen、slotted dataclass；`response_modes` 使用 `frozenset`。provider catalog attachment 均按 descriptor 是否实际含 Chat endpoint 决定，非 Chat GitHub descriptor 的测试也明确断言为 `None`。
- `ResponseModeNotSupported` 是独立 `ProviderError` 子类，没有复用或扩大 `CapabilityMissing`；四项 facts 在当前实现中均被保存，available mode 的 message 使用按 value 排序，输出确定；classifier 分支位于 generic `ProviderError` 之前并输出 CLIENT／400／`unsupported_response_mode`。
- `ProviderError.__subclasses__()` oracle 已更新为集合全等断言；新增 `ChatResponseMode` 未进入任何需同步的 production mapping table。
- `ModelDescriptor.chat_endpoint_capabilities` 追加在原有 default fields 之后，未改变既有 positional argument 含义；提交态扫描未发现 positional `ModelDescriptor` 调用。
- diff 中没有新增 runtime provider-name 分支，也没有迁移 payload／stream 处理；变更只落在 brief 的 10 个文件。diff whitespace check 通过。

## 对实现者验证证据的核验

- Production-first 与 final pytest 使用的命令均逐字覆盖 brief Step 4／6 指定的四个 test 文件；报告中的 `136 passed, 1 failed` 后转为 `146 passed`，增量与本 patch 新增的 parametrized／standalone cases 数量相符。首次唯一失败指向新增 exception 未进入既有 subclass oracle，也与提交态改动一致。该证据足以支撑“指定 targeted suite 最终通过”，但 package 未附原始命令 transcript，因此时间顺序只能按实现报告认定。
- Ruff 与 Pyright 命令逐字覆盖 brief 指定 paths，结果声称分别为 clean 与 0 errors；它们足以支撑 listed paths 的静态检查结论，但无法执行动态 fake descriptor constructor，不能弥补 F-1。
- 本 reviewer 遵照要求没有重跑实现者已跑的四文件 pytest。另行用 candidate source 做了最小 constructor probe，确认 F-1 的构造形态确定抛出预期 `ValueError`；未调用真实 provider。
- 因 F-1 位于 targeted pytest 之外，实现者的命令／结果不足以支撑“所有 production／test Chat constructors 已迁移”这一 Task-level claim。故两项 verdict 不能通过。

## 审查搜索面

- 已依次读取 requirements brief、implementer report、完整 review package。
- 已检查 exact diff scope／whitespace、全部提交态 `ModelDescriptor(` 调用位置、全部 `ChatResponseMode`／`ResponseModeNotSupported`／`chat_endpoint_capabilities` 引用、动态 endpoint descriptor helpers、exception exhaustiveness oracle、provider conditional attachment、positional constructor 面和 Task 5 越界面。
- 未运行全仓回归，也未重跑实现者的 targeted pytest／Ruff／Pyright；未审查 Task 4／Task 5 尚未交付的实现。

## 审查后否决的建议

- 否决“为 `Literal[True] | None` 与 `frozenset[ChatResponseMode]` 再增加 runtime type checker”：brief 给出的闭合类型由 typed internal constructors 产生，当前没有 concrete invalid-input boundary；把通用 runtime schema validation 加进本 slice 没有被现有 failure scenario 支撑。
- 否决“在 Task 1 顺手消费 capability 并迁移 payload／stream handling”：该行为明确属于 Task 5，本提交保持声明层与错误分类层边界是正确的。
- 否决“按 provider name 在 runtime 选择 defaults”：这会破坏 per-model descriptor snapshot 合同，当前实现没有采用。


---

## Scoped re-review：ee07f43..3897912

### 范围与最新 verdict

本轮只复核原 F-1、F-2 及 fix diff `ee07f4322e2dee35816a107c8965f8db34582099..38979123336a622a02424645ffbcad3822136c2f`，不扩展到未改代码。以下状态与 verdict 是对原报告结论的最新补充。

- F-1：ADDRESSED
- F-2：ADDRESSED
- 新 Critical breakage：0
- 新 Important breakage：0
- SPEC COMPLIANCE：✅
- TASK QUALITY：Approved

### F-1 disposition：ADDRESSED

Fix 在 `tests/unit/pipeline/test_auto_mode_classifier.py` 定义 frozen `_NEUTRAL_CHAT_CAPABILITY`，并在 `RecordingProvider.describe()` 中仅当 dynamic endpoint 为 `ModelEndpoint.OPENAI_CHAT_COMPLETIONS` 时附加该 snapshot，否则显式附加 `None`。这与原 finding 要求逐项相符：Chat constructor 不再违反 descriptor invariant，非 Chat 构造仍保持 null，而且分支依据 endpoint 而非 provider name。实现报告给出的最小 node 结果为 `1 passed`，随后包含原 targeted suite 与该 node 的组合结果为 `147 passed`；本 reviewer 按要求未重复执行。

### F-2 disposition：ADDRESSED

Fix 在 `tests/unit/pipeline/test_error_classify.py` 对 `error.provider`、`error.model_id`、`error.requested_mode`、`error.available_modes` 分别增加断言；enum 使用 identity，available modes 使用完整 `frozenset` equality。四项 typed consumer facts 与既有 exact message／wire body checks 现在能够分别判否，完整关闭原 acceptance coverage 缺口。

### Fix diff 新 breakage 检查

Fix 只改动上述两个 test 文件。新增 snapshot 是 immutable test fixture，没有 production fallback、provider-name branch 或 Task 5 payload／stream 行为；conditional attachment 保持 Chat／non-Chat 双向 invariant。新增 typed facts assertions 只观察现有异常合同，不改变 fixture setup 或 error classification。未发现 Critical／Important 新 breakage。

### 验证证据适足性

更新后的 implementation report 给出的 pytest、Ruff、Pyright commands 均纳入两处 fix path；pytest 还单独执行并通过 F-1 原失败 node。对本轮 scoped re-review，这些结果足以支撑两项修复；本 reviewer 没有重跑已执行测试，也没有把结论扩展为未执行的全仓回归。

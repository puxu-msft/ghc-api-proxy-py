# Task 1 独立代码评审

## Verdict

- **Spec compliance：PASS。** 在评审包 `b67634d929b22f3cdcc83cf5607cd37c4eb35c2c..a2bd918` 所限定的改动中，源码实现符合 Task 1 brief、task-specific binding constraints 与 `spec.md` 的 Target Anthropic thinking profile 小节。
- **Code quality：CHANGES_REQUESTED。** 实现本身未发现功能偏差，但最终接线缺少具有分辨力的回归测试；这与 implementer report 所称“`handle／count`接线测试：2 passed”不相符。
- **证据边界：** 按要求只读 requirements brief、implementer report、完整 review package、authority 小节及为核查 merge／ordering、imports 与调用链所需的相关源码；未重跑 implementer 已报告的测试。报告中的测试通过数字因此只作为 implementer 的既有回执采用，不升级为本 reviewer 的独立运行证据。

## Compliance trace

- 配置能力的唯一来源是 `ProxyConfig.model_translation.to_anthropic_messages.thinking_profiles`；runtime profile 没有另设 model-family fallback。
- `src/app/config/bundled-config.yaml:58-79` 逐项转录 authority 的六条 regex profile，pattern、`modes` 顺序、`can_disable`、`disabled_max_effort` 与空 manual budget 均一致。
- `src/app/config/loading.py:36-52,190-212` 先载入 bundled mapping，再深合并用户层；新 pattern 保持追加次序，同 pattern 逐字段深合并。`src/app/pipeline/routing.py:376-400` 按 mapping 次序编译，以 `fullmatch` 扫描并让最后命中项生效。
- `src/app/config/schema.py:231-258` 限制 modes 为 `adaptive／enabled`、拒绝空值与重复项，`can_disable` 使用 strict bool，manual budget 使用 strict int 且下限为 1024。
- `src/app/server/composition.py:535-537,563-565` 在 `build_chain()` 中编译一次并写入 `Chain.thinking_profiles`；非法 regex 在 chain 构建期间抛出。
- `src/app/pipeline/routing.py:403-420` 将选中的 runtime profile 与原始 pattern 写入 `TranslationTarget`；`src/app/pipeline/driver.py:157-163,274-280` 的真实发送与 count 两条翻译路径都传入同一个 `chain.thinking_profiles`。
- imports 形成单向依赖：schema → reasoning runtime types → semantic target → routing／chain／composition；未发现 import cycle。
- review package 只包含 brief 列出的 Task 1 文件以及 Ledger Ruling 明确授权的 `src/app/pipeline/driver.py` 两处参数接线；未修改 `docs/.human-controlled/`、legacy converter 或 Task 2 source-header 逻辑，也没有 `ruff format` 产生的改写。

## Critical

none。

## Important

### I1．最终 profile 接线没有可判否的测试

- **位置：** `tests/int/test_pipeline_app.py:174-200`，`tests/unit/pipeline/translation_driver/test_reasoning.py:183-217`，`src/app/server/composition.py:535-537,563-565`，`src/app/pipeline/routing.py:403-420`，`src/app/pipeline/driver.py:157-163,274-280`。
- **场景：** 新增的 integration test 只证明非法 regex 会在 `build_chain()` 中编译失败；selection tests 则直接调用 `compile_thinking_profiles()`／`select_thinking_profile()`。没有测试观察 `build_chain()` 是否把编译结果保存在 `Chain`，没有测试观察 `translation_target()` 是否把 profile 与 pattern 放进 `TranslationTarget`，也没有测试分别经过 `handle()` 与 `handle_count_tokens()` 确认二者读取同一个 compiled profiles。把 `Chain(..., thinking_profiles=thinking_profiles)` 改成 `thinking_profiles=()`、把任一 driver 调用的第三个参数改成 `()`，或让 `translation_target()` 丢弃 `profile／pattern`，本 Task 新增测试仍会全部通过。Task 4 writer 接入后，这会表现为真实发送或 count 其中一条路径把已配置模型当成 profile unknown，或者两条路径产生不同 translated body；当前测试绿无法区分这种失败。完整 review package 中也没有 implementer report 所称的两条 `handle／count` profile 接线测试。
- **修法：** 增加两条经过真实 driver 入口的分辨性测试，一条调用 `handle()`，一条调用 `handle_count_tokens()`。用包含自定义重叠 pattern 的 config 经 `build_chain()` 构造 chain，并以记录型 translator 捕获实际收到的 `TranslationTarget`；分别断言其 `thinking_profile` 的全部字段及 `thinking_profile_pattern`，并断言两条路径得到相同值。测试必须经过 `build_chain()`，否则仍无法覆盖 startup compile → `Chain` → driver → `translation_target()` 的整条接线。

## Minor

none。

## Closeout note

本报告是 Task 1 的中间独立评审交付物，后续 finding disposition、复评、整合与 worktree 生命周期由上级 coordinator 管理。本 reviewer 未修改源码、未创建测试资产、未执行清理／归档／提交／合并／发布，也未派生 subagent；除用户指定的本报告外没有新增产物。

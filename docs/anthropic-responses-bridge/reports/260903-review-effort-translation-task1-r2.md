# Task 1 scoped re-review R2

## Scope and evidence

本轮只复核原评审 I1 及 fix diff `a2bd918..69b6ac6` 新增内容，不重开原先已经 PASS 的生产 diff。依次读取了原 review、更新后的 implementer report、Task 1 brief 与完整 fix package，并读取 fix 所在测试文件的局部上下文以确认 helper、catalog、imports 与执行入口。按要求未重跑 implementer 已报告的测试；“两个 exact node 2 passed、Ruff 通过、Pyright 0 errors”只作为 implementer report 的既有回执采用。

## I1 disposition

**I1：ADDRESSED。**

- `tests/int/test_pipeline_app.py:220-280` 从带两个重叠 profile pattern 的 `ProxyConfig` 调用真实 `build_chain()`，随后只把 `chain.translators` 换成记录型 registry；`Chain.thinking_profiles` 仍是 `build_chain()` 在 startup 编译并保存的对象，没有由测试手工注入 profile 或绕过该接缝。
- `tests/int/test_pipeline_app.py:283-297` 调用真实 `driver.handle()`；`tests/int/test_pipeline_app.py:300-314` 独立调用真实 `driver.handle_count_tokens()`。两条路径都发生 Responses→Anthropic translation，均由记录型 outbound writer 捕获生产 `translation_target()` 生成的 `TranslationTarget`。
- 两条断言都与 `tests/int/test_pipeline_app.py:206-216` 的完整期望对象做 dataclass equality，观察了 `model_id`、`reasoning_efforts`、`thinking_profile.modes`、`can_disable`、`disabled_max_effort`、`manual_budget_tokens` 与 `thinking_profile_pattern`；精确 pattern 位于宽 pattern 之后，期望对象同时证明最后命中项及其原始 pattern 被带到 writer。
- 分辨力满足原 finding：若 `build_chain()` 不把编译结果存入 `Chain`，两条测试都会得到空 profile；若只删除或改空 `handle()` 接线，第一条失败；若只删除或改空 `handle_count_tokens()` 接线，第二条失败；若 `translation_target()` 丢弃 profile 或 pattern，两条都会因完整对象不等而失败。每条测试各建一条 fresh chain 不削弱该判据，因为两者分别验证的是各自入口从 startup compilation 到 captured target 的完整因果链，而不是对象 identity。

## Fix-diff breakage check

**NEW_BREAKAGE：none。** Fix 只改 `tests/int/test_pipeline_app.py`；新增 imports 均被 helper／assertions 使用，记录型 translator 注册 source reader 与 target writer 后才替换 chain registry，两个测试都在 `finally` 关闭共享的 async HTTP client。未发现绕过 production wiring、自洽 oracle 掩盖 profile／pattern 丢失、错误 route direction、资源泄漏或 Task 1 范围外行为改动。

## Verdict

**PASS。** I1 已由能对相邻断线状态判红的两条 chain-level tests 关闭，fix diff 未引入新 finding。

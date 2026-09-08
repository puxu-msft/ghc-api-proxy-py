# Anthropic Responses happy-path 定向代码复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-happy` 分支 `integrate/260807-bridge-happy-path`，固定 `HEAD=7e4b642be8bd526d8f20f3f8d7e2d7848278a443`、base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。本轮只复核 `docs/tmp/260807-review-code-happy-path.md` 的唯一 major，以及上一轮 reviewed HEAD `d78b3cdc172ecad42873a70f1df31438ecca1663` amend 到 current HEAD 所引入的新问题；不重新展开四个 feature commits 的全量代码评审。
- **总体 verdict**：**可进入下一阶段。** 上一轮同源 carrier expected 的唯一 major 已关闭，amend 未发现新 blocker、major 或 minor。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：每项 load-bearing shell 证据均在同一调用内打印并校验目标 physical root、branch、精确 HEAD 与 clean status；逐行读取最终 happy-path smoke、项目 carrier codec、公开 reverse consumer 及 current Spec canonical vector。`d78b3cdc…→7e4b642…` 的 name-status 只列出 `tests/smoke/test_anthropic_responses_happy_path.py`；零上下文 diff 显示 amend 删除产品 encoder／decoder／prefix 生成 expected 的旧写法，改为静态完整 signature。该常量与 `docs/agents/anthropic-responses-bridge/spec.md:219` 的 `opaque-😀` canonical vector 逐字相等；`tests/smoke/test_anthropic_responses_happy_path.py:79-98` 先从公开 nonstream converter 取得 Anthropic block、断言完整 signature，再调用公开 `anthropic_thinking_to_responses()` 做 value-exact echo。进程内只把实际 producer prefix 改为错误 `v9` 后，目标 smoke 以 `AssertionError` 准确变红，目标树保持 clean；恢复后的独立 happy-path smoke 在目标 import path 下为 `8 passed in 1.02s`，包含两份 smoke 与 carrier／reverse／nonstream／stream parser／preparation targeted unit 的集合为 `66 passed in 1.04s`。两个测试数字分别绑定上述明确 selector 与 current HEAD；它们是同一路径的 isolated／superset 运行，不冒充两种独立原理的交叉验证，两个通过数均标记为未交叉验证。
- **双视角覆盖证据——第一人称执行**：模拟 `opaque-😀` Responses reasoning item 经公开 nonstream converter 形成公开 Anthropic thinking block，先对 Spec 固定完整 wire 做字节级比较，再把同一个公开 block 交给公开 reverse consumer，恢复的 visible summary 与 `encrypted_content` 均 value-exact；随后把 producer version 改错为 `v9`，确认测试在 reverse 之前即由 wire 断言拦截，不再允许 producer／consumer 同漂移。另按 amend 删除路径追踪旧 multiple reasoning／encrypted-only 组合覆盖，确认 `tests/unit/test_responses_reasoning.py:25-44,91-170` 与 `tests/unit/test_responses_anthropic_nonstream.py:90-122` 仍守住 encrypted-only、source order、多 item 独立 blocks 与逐 block reverse，且这些文件已包含在本轮 targeted green 中。

## 事实性发现

未发现问题。

## 主观建议

无。

## 上一轮 major 处置

- **关闭**：上一版 smoke 的 expected 同时由产品 version 常量、encoder 与 decoder控制，错误 producer／consumer 可共同漂移仍保持绿色。current amend 已把 expected 绑定 current Spec 的完整静态 signature，并从产品公开 nonstream 输出观察实际 wire；公开 reverse 只验证该已通过独立 wire 断言的 block。`v9` producer 变异准确红，证明上一轮复现的 false-green 不再存在。
- **amend 回归核对**：amend 为建立独立 wire oracle，把原 smoke 中 multiple reasoning／encrypted-only 断言收敛为一个 canonical vector。该行为覆盖未被静默删除，而是继续由 targeted unit 明确承担；未发现覆盖断层。

## 结构怪味扫描

- `tests/smoke/test_anthropic_responses_happy_path.py:31-35,79-98`——**oracle 同源风险**——本轮已修；静态 Spec vector 与公开产品输出比较，expected 不再调用产品 codec。
- `tests/smoke/test_anthropic_responses_happy_path.py:79-98` 对照 `tests/unit/test_responses_reasoning.py:91-170`、`tests/unit/test_responses_anthropic_nonstream.py:90-122`——**组合测试收窄可能造成重复职责或覆盖缺口**——本轮核对后不另修；smoke 负责跨模块 canonical wire＋public reverse，unit 负责 cardinality／order／encrypted-only，职责分层清晰且 targeted green。
- 扫描范围还包括 amend 全量 diff、carrier producer／consumer 接缝与四提交 parent 链；未发现新的重复实现、职责错位或抽象泄漏。

## 四 commits 回放结论

四个 reviewed commits 构成从 frozen base 开始的线性无 merge 链：

1. `1ed13ad7e19385b9f86a1cd292547438f6137179`——`feat: add versioned reasoning carrier codec`
2. `80b3cfade000cd9e1626074d14b1f9c9d5294891`——`feat: convert Responses JSON to Anthropic messages`
3. `c950912ad739f85c39397ab0f2c4d25b82dddcb7`——`feat: assemble Responses stream events`
4. `7e4b642be8bd526d8f20f3f8d7e2d7848278a443`——`feat: add typed protocol route policy`

**明确结论：在先把 frozen base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 落到 main 的既定集成顺序下，上述四 commits 可按列出顺序逐个回放 main。** Current `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1` 与 base 的共同祖先是 `ed77c9d191df81c451c25161420515cca52ce6a4`，目前尚非 base 的后代；因此本结论不授权跳过 base 直接 cherry-pick 四 commits。共同祖先到 current main 只改 bridge 文档，和共同祖先到 base 的前置代码／测试路径不相交；四 commits 又精确线性建立在 base 上，故先 base、后四 commits 的逐个回放顺序没有已知路径冲突。本轮按只读约束未执行实际 cherry-pick dry-run。

本 verdict 只放行 happy-path checkpoint 的四提交集成，不表示完整 Anthropic Responses bridge 产品 PASS；未在本轮复评范围内的后续 usage、stream grammar／framing／sequencer、route handler／transport 接线与全量验收状态保持原裁决。

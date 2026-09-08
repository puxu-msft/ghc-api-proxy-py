# Non-stream converter PASS 与独立验收 FAIL 范围冲突裁决

- **评审范围**：只读裁决 `/home/xp/src/ghc-api-proxy-py-response` 的 `feat/responses-anthropic-nonstream@7ddf17364d97349638d44352bbd9a9b025723ccc`、其 base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`、`/home/xp/src/ghc-api-proxy-py-carrier-v2` 的 `feat/reasoning-carrier-v2@8301ee938601ad86c7f72d313abc6c976a74b2a9`，以及 current Spec `docs/agents/anthropic-responses-bridge/spec.md` SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。裁决对象是 `docs/tmp/260807-review-code-nonstream-response-r2.md` 的 checkpoint PASS／可 squash 与 `docs/tmp/260807-verify-nonstream-response.md` 的 full-Spec FAIL 是否冲突；不重新评审两条分支的全部代码，也不修改代码。
- **总体 verdict**：**可进入下一阶段；允许 nonstream 分支作为已声明范围的 checkpoint squash。** 两份报告测量范围不同，并非同一命题一真一假。Carrier F-1 裁定为**集成排序依赖**，不是 nonstream converter major；Usage F-2 是 current Spec 下真实的 nonstream 后续实现缺口，但 R2 明示排除 usage，故不追溯推翻本 checkpoint 的 0 blocker／0 major。独立验收的 expected 没有错误，但其 full-Spec `FAIL` 不得外推为“本 checkpoint 不可 squash”或“carrier codec 应复制进 converter”。
- **blocker 数**：0。
- **本 checkpoint major 数**：0。
- **完整产品状态**：仍为 **`UNVERIFIED`**。本裁决不把局部 squash、组合 smoke 或 carrier v1 gate 改写成完整 bridge `PASS`。
- **双视角覆盖证据——机械核对**：每次 shell 分别 gate nonstream root／branch／精确 HEAD／base ancestry、carrier-v2 root／branch／精确 HEAD，以及 current Spec 内容 SHA-256。逐行对账 nonstream converter 的 import、reasoning 调用点与 `_convert_usage()`，carrier-v2 的 `encode_reasoning_carrier()`／`responses_reasoning_to_anthropic()`，两份冲突报告、current Spec 的项目主 v1 与 Usage 合同、current Acceptance 的 `NS-03`／`NS-04`，以及 Implementation 对 checkpoint 与完整产品验收的分层规则。两个候选相对同一 base 的改动路径无交集，三方 merge-tree 未报告文本冲突。
- **双视角覆盖证据——第一人称执行**：先以 `7ddf173` 单树执行 verifier 路径，观察到 converter 通过共享 helper 产出旧 upstream carrier；再在 `/tmp` 构造 `6a00f6f → 8301ee9 carrier-v2 → 7ddf173 nonstream` 组合快照，复跑同一独立矩阵。项目主 v1 carrier 项由 FAIL 变为 PASS，而 usage reasoning detail 仍 FAIL；这把共享 producer 依赖与 converter 自有 usage 缺口机械分开。组合相关单测与 Ruff 通过；临时仓外快照上的 Pyright 因路径产生 `reportMissingTypeStubs`，不计为产品失败或绿色证据。测试 runner 输出的具体用例数未以第二种原理交叉验证，因此本文不把数量作为验收断言。

## 裁决

| 议题 | 裁定 | 证据与边界 |
|---|---|---|
| Carrier F-1 是否是 nonstream 实现 major | **否；是集成排序依赖。** | `src/app/protocols/responses_anthropic.py:9,64` 只调用共享 `responses_reasoning_to_anthropic([item])`，没有也不应复制 carrier 编码。`7ddf173` 的 base 尚无 carrier-v2，故单树解析到旧 `copilot-api:synthetic-reasoning:v1:` producer；组合 `8301ee9` 后，同一 converter 与同一 verifier 输入产出项目主 v1并通过该项。根因位于依赖版本，不在 converter 的消费方式。 |
| Usage F-2 是否是 oracle 错误 | **否；是完整 Spec 下真实但已后置的 nonstream 功能缺口。** | `src/app/protocols/responses_anthropic.py:171-198` 的 `_convert_usage()` 只读取 input details；`src/app/models/anthropic.py:64-68` 的 `AnthropicUsage` 也没有显式 `output_tokens_details` 字段。Current Spec 与 Acceptance `NS-04` 要求保留 `Q=output_tokens_details.reasoning_tokens`。Carrier-v2 组合不会关闭该项。 |
| Usage F-2 是否追溯成为本 checkpoint major | **否。** | R2 的评审范围明确“不重新评审 usage”；Implementation 又冻结“happy path／smoke checkpoint 先 squash，后续继续补齐边界，完整产品保持 `UNVERIFIED`”的开发节奏。因此 F-2 必须保留为后续 required gap，但不能跨范围推翻已经通过的 identity 定向复评。 |
| 独立验收 oracle 是否错误 | **Expected 正确，适用范围被误用于 squash 决策。** | 对“`7ddf173` 单树是否独立满足 current Spec”提问，overall FAIL 正确；对“该声明范围 checkpoint 是否可 squash”提问，overall FAIL 不是适用 verdict。其 carrier 修复路由也不得被解释成要求 converter 内复制 codec。 |
| Nonstream 是否允许 squash | **允许。** | 允许的是 `7ddf173` 的 checkpoint 语义与归档，不是完整 nonstream／bridge 产品 PASS。Squash 说明必须显式保留 carrier-v2 组合依赖与 usage required gap，禁止只写“nonstream complete”。 |
| 是否需要声明依赖 | **需要，且是 squash／组合 gate 的硬前提。** | 声明：nonstream reasoning wire correctness 依赖共享 `responses_reasoning_to_anthropic()` 的项目主 v1 producer；项目主 v1验收必须在含 `8301ee9` 或其经身份核对的等价 squash 语义的组合态执行。 |

## 唯一最小动作

1. **现在允许 squash `7ddf173`，不改 converter 来复制 carrier codec。** Squash／归档说明必须同时写明两点：项目主 v1 carrier 是 `8301ee9` 的共享依赖；reasoning usage detail 仍是后续 required gap，产品保持 `UNVERIFIED`。
2. **固定 main 组合顺序为 `6a00f6f foundations → 8301ee9 carrier-v2 等价 squash → 7ddf173 nonstream 等价 squash`。** 两片源码路径虽无交集、理论应用顺序可交换，但本轮只保留这一条确定顺序，使 producer 先到位，再验证 consumer-facing nonstream wire，避免在旧 helper 上重跑项目主 v1 gate得到已知假失败。每片仍保留自己的 reviewed pre-squash HEAD；若回放改变语义或发生冲突，旧 verdict 不继承。
3. **只在上述组合态验证项目主 v1。** 最小组合 gate 必须旁路候选 expected，独立断言：每个 reasoning item 一对一且顺序不变；非空与 encrypted-only payload 均输出 current Spec 项目主 v1 exact bytes；client echo 后 consumer value-exact 恢复每个 payload；producer 不得输出 upstream v1；direct Messages strip 与真实 Anthropic signature 保留继续通过。Gate 同时运行 nonstream 与 carrier-v2各自定向测试，以及跨片 producer→nonstream→echo→consumer 接缝测试。
4. **不得把当前 full-Spec verifier 整体要求为绿色后才 squash。** 该矩阵在组合 carrier-v2 后仍会因 Usage F-2失败；这项应由后续 nonstream usage切片修复并按 Acceptance `NS-04`／`STR-05`复验。项目主 v1组合 gate通过只关闭 carrier dependency，不关闭 usage、stream、route或完整生命周期验收。

## 事实性发现

[major] `docs/tmp/260807-verify-nonstream-response.md:5-12,31-32,107` 的 verdict 使用边界 —— 报告把“单树不满足完整 current Spec”正确判为 FAIL，但若将其作为 `7ddf173` checkpoint 的 squash veto，就越过了 `docs/tmp/260807-review-code-nonstream-response-r2.md:3-4,26` 明示范围与 `docs/agents/anthropic-responses-bridge/implementation.md:65,179-184` 的 checkpoint 分层 —— 临时组合实证证明 carrier失败由缺少 `8301ee9` 决定，而非 converter 复制编码不足；同一实证也证明 usage缺口独立存在 —— 按上面的唯一最小动作执行：允许 checkpoint squash，声明依赖，只在固定组合态执行项目主 v1 gate，并把 usage留在后续 required gate。

## 主观建议

无。本裁决给出单一路由，不新增替代方案。

## 结论

**最终分类不是三选一中的单一标签，而是按失败项拆分：Carrier F-1＝集成排序依赖；Usage F-2＝完整 Spec 下真实的后续 nonstream 实现缺口；验收 expected＝正确，但 full-Spec verdict 不适用于 checkpoint squash。** 因此 `7ddf173` 可作为 checkpoint squash；必须声明对 `8301ee9` 项目主 v1 producer 的组合依赖，并在 `foundations → carrier-v2 → nonstream` 的组合态执行项目主 v1 gate。不得复制 carrier 编码到 converter，也不得把该组合 gate 的通过外推为完整产品 PASS。

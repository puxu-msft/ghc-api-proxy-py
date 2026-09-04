# 空 reasoning 语义冲突独立裁决

- **评审范围**：current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 的 FINALIZED `docs/agents/anthropic-responses-bridge/spec.md`、`docs/agents/anthropic-responses-bridge/acceptance.md`、living `docs/agents/anthropic-responses-bridge/implementation.md`，semantic candidate `fix/responses-semantic-parity@1cde3d58338eeefb3cf8040f970c3612d451668b` 的 committed code／tests，以及 `docs/tmp/260807-review-code-semantic-parity.md` 与 `docs/tmp/260807-verify-semantic-parity.md`。只裁决 `summary=[]` 且 `encrypted_content` absent／empty 的 block cardinality，并核对 non-empty encrypted-only no-loss；不重审 candidate 的 unknown summary part major、其他 semantic-parity 行为或完整 bridge。
- **总体 verdict**：**唯一裁决为一个 `thinking=""` bare carrier block，不是零 block。** Candidate 在本裁决轴上的 non-stream／stream parity 方向正确；`verify-semantic-parity.md` 的零-block expected、living `implementation.md` 的零-block实施门，以及 Acceptance `NS-03` 被读成零-block规则的解释错误。Acceptance 本身存在会诱发该误读的歧义措辞，必须澄清，但不得扩张或覆盖 Spec。该定向裁决可进入最小文档／验收修复；不表示 semantic candidate 整体可 squash，因为独立 code review 另有不在本裁决范围内的 major。
- **blocker 数**：0。
- **major 数**：2，均为 oracle／living 文档错误；本裁决轴上的 candidate 实现错误数为 0。
- **证据身份**：本轮采纳为证据的每次 shell 均在同一次调用内 gate 主树物理 root、`main` 分支与完整 HEAD `80bc8f252b46c511f428af1d97159a5980ee9dc9`；candidate 固定为 clean `1cde3d58338eeefb3cf8040f970c3612d451668b`。本轮以 Python `hashlib.sha256` 与 `sha256sum` 交叉核对四个输入：Spec `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`、Acceptance `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`、code review `e69adaaf9eb2a1dee91facf020b62ea5e3f963b57b7d325bf016053afffdbed7`、verify report `2b871ec71f449c618d589bc145e946eb23a8e92684ec72034c52623162f11b54`。
- **双视角覆盖证据——机械核对**：确认 Spec `:5` 的 `FINALIZED` 与“行为 oracle”身份；逐句对账 Spec `:182`、`:207`、`:221`、`:325`、`:525`，Acceptance `:137-142`，living implementation `:32`，code review `:13`，verify report `:5-7,13-14,28-33,58`；读取 candidate committed non-stream producer `responses_reasoning.py:43-80` 与 stream completion `responses_stream_parser.py:493-511`；搜索 current docs 中所有“零 block／不凭空制造可恢复 block”复述，确认错误 expected 已进入 living implementation 与 verify report。
- **双视角覆盖证据——第一人称执行**：分别以 `summary=[]`＋absent、`summary=[]`＋`encrypted_content=""`、`summary=[]`＋`encrypted_content="opaque-state"` 走 candidate 真实 producer／consumer。前两者均生成一个 `thinking=""`＋`ghc-api-proxy:synthetic-reasoning:v1` block，echo 后恢复 `{type:"reasoning", summary:[]}` 且不产生 `encrypted_content`；第三者生成一个带项目 v1 payload carrier 的 `thinking=""` block，echo 后 value-exact 恢复 `encrypted_content="opaque-state"`。隔离进程输出 `RUNTIME_ORACLE=PASS`，候选前后 clean。

## 唯一裁决

### `summary=[]` 且 `encrypted_content` absent／empty

目标 Anthropic **必须生成恰好一个** thinking block：

- `type="thinking"`；
- `thinking=""`；
- `signature="ghc-api-proxy:synthetic-reasoning:v1"`，即项目 bare marker；
- absent 与空字符串同义；
- echo consumer 恢复一个 summary-only Responses reasoning item `{type:"reasoning", summary:[]}`，但**不得添加或伪造 `encrypted_content`**。

这不是“可恢复密文 carrier”。Bare marker只保留 item cardinality与空 visible summary，不承载 opaque payload。因而 Acceptance 的“不凭空制造可恢复 block”只能约束“不得伪造可恢复的 `encrypted_content`”，不能扩张成“不得生成 block”。

### non-empty encrypted-only

当 `summary=[]` 且 `encrypted_content` 为非空字符串时，目标 Anthropic 同样必须生成恰好一个 `thinking=""` block，但 signature 必须是带 payload 的项目主 v1 carrier。客户端原样 echo 后，consumer 必须 value-exact 恢复同一非空 `encrypted_content`。任何零-block、只在 summary 非空时建 block、聚合多个 items 或 last-ciphertext-wins 行为都违反 no-loss 与一 item一 block。

## 权威推导

1. Spec `docs/agents/anthropic-responses-bridge/spec.md:5` 明确自身是 FINALIZED 行为 oracle；Acceptance 只能执行该行为，不能创造例外。
2. Spec `:182` 冻结每个 reasoning item 一对一形成 thinking block；`:221` 进一步规定每个 Responses reasoning item 独立构造一个 block，缺失或空 `encrypted_content` 产生 bare marker，consumer恢复 summary-only item；这里没有“空 summary 时例外”。
3. Spec `:325` 再次把“一个 Responses reasoning item映射为一个 Anthropic thinking block”列为 semantic block 完成规则，并规定空 `encrypted_content` 与 absent 相同。Spec `:207` 及 `:525` 单独强化 non-empty encrypted-only no-loss 与每-item cardinality。
4. Acceptance `docs/agents/anthropic-responses-bridge/acceptance.md:139` 同一句先要求“默认 producer 对每个 item 生成项目主 v1 payload 或项目 bare marker”，后写“empty payload 且无 summary 不凭空制造可恢复 block”；`:140` 的缺陷注入还明确要求“仅在 summary 非空时创建 thinking block”必须变红，`:142` 要求 empty payload 保留项目 bare marker且“不伪造可恢复性”。三处合读只能得到“一 block＋bare marker＋无可恢复密文”，不能得到零 block。
5. 因此 verify report `docs/tmp/260807-verify-semantic-parity.md:7,13-14,28-33,58` 把 Acceptance 中的“不可恢复”提升为“不可存在”，反向覆盖 Spec，并错误判 candidate FAIL。Code review `docs/tmp/260807-review-code-semantic-parity.md:13` 在本裁决轴上的解释正确。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/acceptance.md:139-142` — `NS-03` 同时写“每 item 生成 payload／bare marker”和“empty payload且无summary不凭空制造可恢复block”，后一句缺少“不可恢复的是 encrypted payload，而非 block cardinality”的明确限定 — 实际 verify 已据此推导出零 block，证明歧义具有现实执行影响；但 `:140` 的 mutation expected 与 FINALIZED Spec 都排除零 block — 最小修复为把后一句明确改成：empty payload且无summary仍生成一个 `thinking=""`＋项目 bare marker block；consumer只恢复`summary=[]`，不得恢复或伪造`encrypted_content`。同步保持`:140`“仅在summary非空时建block必须变红”。

[major] `docs/agents/anthropic-responses-bridge/implementation.md:32`、`docs/tmp/260807-verify-semantic-parity.md:5-7,13-14,28-33,58` — living implementation与verify report把歧义固化为零-block expected，并据此要求修改正确 candidate — 该 expected 直接冲突 Spec `:182,221,325`，也与 Acceptance 自身 `:139-142` 的 per-item bare marker／mutation条款冲突 — 最小修复为撤销零-block门：living implementation改为“一 empty item一 bare block parity”；verify 的 SP-01／SP-02 expected改为“一 block且无`encrypted_content`可恢复”，F1及定向 FAIL随之撤销。历史报告可保留原文但必须由本裁决标记为 superseded；不得按其建议删除 candidate 的空 `ReasoningBlock`。

## 实现归属与最小代码处置

- `src/app/anthropic/thinking/responses_reasoning.py:43-80` 对每个合法 reasoning item生成一个 thinking block，并让 absent／empty走bare marker，**本裁决轴正确，无需修改**。
- `src/app/openai/responses_stream_parser.py:493-511` 在 authoritative item done后生成 `ReasoningBlock("", None)`，与non-stream语义一致，**本裁决轴正确，无需修改**。
- `tests/unit/test_responses_stream_parser.py:269-293` 的 one-block parity expected方向正确，应保留。最小回归应同时断言：absent／empty恰好一个block、bare signature、不恢复`encrypted_content`；non-empty encrypted-only恰好一个block且value-exact恢复payload。
- 不要为本冲突引入新的 shared “block eligibility”过滤器；它会把正确的一 item一 block合同改成零 block。若未来为减少stream／non-stream重复而提取共享normalizer，必须保持上述三向量，不得顺带改变cardinality。
- Candidate整体仍受 `docs/tmp/260807-review-code-semantic-parity.md:19` 的unknown reasoning summary part major约束；本裁决不关闭、不降级该独立问题。

## 主观建议

[建议] `docs/agents/anthropic-responses-bridge/acceptance.md:139-142` — 将“block存在性”“visible summary”“opaque payload可恢复性”拆成三个独立断言 — 预期影响是避免再次把“无可恢复密文”误读为“无block” — 推荐用三行正向 expected，并为 absent、empty、non-empty encrypted-only 各给一个明确向量，不再用“可恢复block”这一复合短语。

## 结论

本冲突的唯一合法行为是：**empty reasoning item → 一个 `thinking=""` bare carrier block；non-empty encrypted-only → 一个 `thinking=""` payload carrier block并保证 value-exact no-loss。** 错误位于 Acceptance 的歧义表达及其下游 verify／living implementation 的零-block扩张，不位于 candidate 当前 empty-reasoning实现。最小修复只改 oracle措辞、living门与验收expected，不改该轴生产代码。

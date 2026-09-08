# Anthropic Responses bridge 规格独立复评 R2

## 评审结论

- **评审范围**：主树 `HEAD=ed77c9d191df81c451c25161420515cca52ce6a4` 下的 `docs/agents/anthropic-responses-bridge/spec.md`。按派活约束，仅定向复核上一轮 `docs/tmp/review-bridge-spec.md` 的 6 条 major、2026-08-06 reasoning carrier 重裁，以及 route precedence、首 block 前零外露、字段矩阵、server-tool no-revive、usage 算式、carrier 兼容与低概率不过度设计；未重做全仓调查。
- **总体 verdict**：**修复 1 条 major 后可定稿**。
- **计数**：blocker 0，major 1。
- **上一轮处置**：M1～M5 已由唯一、可验收的行为合同关闭；M6 的旧 HMAC／schema 修法已按用户重裁撤销，固定 upstream-compatible prefix／base64url／legacy／strip 合同足以关闭原发现。本轮 major 不重开 M6 的产品裁决，而是当前状态与实现证据失真。

## 双视角覆盖证据

- **机械核对**：每次 shell 均校验主树完整 HEAD；逐项对账 route precedence 与真值表、首 block／HTTP success headers／`message_start` commit 边界、双向 `PRESERVE`／`TRANSFORM`／`REJECT`／`DEGRADE` 矩阵、request／response／block 三处 server-tool no-revive、usage 公式与四组数值向量、低概率扩展的冻结基础行为，以及 `>16 MiB`／专用大对象阈值残留。另在 `copilot-api-js@8d5c861c2e079b92401dd8ccd49695a363d078fe` 逐行核实 carrier prefix、Node `base64url` producer／consumer、legacy bare sentinel、`stripThinkingSignature` 与 direct Messages unconditional strip，并用 Node 实跑两个固定正向向量。
- **第一人称执行**：模拟了显式 override 不可用、双 endpoint 无 override、unknown capability、首 block 前 upstream 失败、unknown request／response 字段、Anthropic server tool 输入、未请求的 Responses server-tool item、cache＋reasoning usage、encrypted-only reasoning、多个 reasoning item 交错，以及全局内存压力下单个普通大 block。除下述当前实现证据陷阱外，规格都给出唯一动作，且未用专用大小假设或泛化安全系统扩大基础范围。

## 定向复核结果

- **Route precedence**：关闭。显式 override、双支持默认 Messages、单 endpoint、unknown fail closed、vendor 不形成隐藏 precedence、protocol leg 与 physical transport 正交，均有唯一结果。
- **首 block 前零外露**：关闭。HTTP success headers、`message_start` 与 body event 均绑定首个完整 block 的串行 sink batch；pre-commit retry 不会泄漏失败 attempt。
- **字段矩阵**：关闭。双向矩阵定义四种处置状态、unknown strict 默认及明确的低概率扩展基线，没有把 reject／degrade 留给实现者任选。
- **Server-tool no-revive**：关闭。请求 gate、响应转换、semantic block 完成条件及扩展裁决边界一致，未暗中恢复 Anthropic 原生 server-tool 编排。
- **Usage 算式**：关闭。`I=max(0,T-R-W)`、`Q⊆O`、total=`I+R+W+O` 与 inconsistent／absent 行为形成唯一 oracle，reasoning 不二次相加。
- **Carrier 兼容重裁**：行为合同关闭。固定 prefix、Node-compatible base64url、bare／legacy、foreign、strip 与固定向量均和指定 upstream commit 一致；没有重新引入 HMAC、`kid`、JCS、domain binding 或私有 schema。
- **低概率不过度设计**：关闭。`>16 MiB` 假设已删除；carrier 与 block 作为普通内存对象服从统一 resident budget、queue、deadline、cancel 与 shutdown，规格明确禁止专用大对象阈值、spill 和 live forwarding。四项低概率扩展均有冻结基础行为，不阻断基础实现。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/spec.md:6,227` — “仓库基线／待回并实现证据”与当前主树相反，并会把一个已知不符合规格的 carrier 实现误呈现为可依赖的完成证据 — 当前主树已是 `ed77c9d191df81c451c25161420515cca52ce6a4`，不是规格所写的 `47d9ef101c4b81ac70d805b1da157b34d021d33d`；`b040eb3ce44a6e18a41cd89228fba4173c1c05d1` 也不是仍待回并的当前实现。当前 `src/app/anthropic/thinking/responses_reasoning.py:55-95` 明确把所有 reasoning items 聚合成至多一个 thinking block、只保留最后一个非空 ciphertext，并在 summary 为空时返回 `None`；`tests/unit/test_responses_reasoning.py:25-30,64-93` 又主动断言 encrypted-only 被丢弃且多个 items 被聚合。定向测试 `uv run pytest -q tests/unit/test_responses_reasoning.py` 在该 HEAD 得到 `8 passed`，说明绿灯固化的正是与规格 `spec.md:203,206-209` 相反的行为。第一人称按规格进入实施计划时，执行者可能把 line 227 当成 carrier 已完成证据，遗漏 encrypted-only、multiple-item 一对一及顺序修复，最终无法满足规格自身验收。**修复建议**：把仓库基线更新到当前 HEAD；删除“待回并且已固化 encrypted-only／multiple-item 合同行为”的失真陈述，改为明确记录“wire codec 已落地，但当前 producer 聚合 items 并丢 encrypted-only，尚不符合本规格”，并把这三项列为实施与验收必修项；或者将易变实现状态移到 tracking／implementation 文档，只在正式规格保留固定 upstream oracle。不得为迁就当前测试而放宽一对一、encrypted-only no-loss 或语义顺序合同。

## 主观建议

未列。除上述 major 外，未发现 blocker 或其他 major；修复后可定稿并进入实施计划。

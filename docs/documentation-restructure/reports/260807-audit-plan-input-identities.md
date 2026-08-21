# Current Plan 规范输入 identity 审计

## 范围与结论

- **评审范围**：只读核对 current `docs/agents/documentation-restructure/plan.md` 及其规范输入 `docs/agents/anthropic-responses-bridge/spec.md`、`docs/agents/anthropic-responses-bridge/acceptance.md`。除本报告外未修改任何文档。
- **仓库门**：每次 shell 调用均在同一调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。
- **总体 verdict**：Plan 的 Spec identity 仍一致；Acceptance 当前实体已经是 `19635e04886052fa2c2c98e42aab1c87c23c1fb9c8935753201928eaa8463498`，而 Plan 的 current 绑定仍写死旧值 `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091`。因此 Plan 在 planner 同步并完成定向复评前不得执行阶段 0B 或阶段 1 bridge gate。
- **blocker 数**：0。
- **major 数**：1。
- **双视角覆盖证据**：机械核对逐项比较 Plan 写死 hash 与实体 SHA-256，并扫描 Plan 内全部 `a193da…`、`31673…`、`19635…` 命中；第一人称执行模拟阶段 0B 与阶段 1 kick-off 的 identity gate，确认当前 Plan 会在 Acceptance hash 检查处 fail closed，而历史 R4 处置记录不参与 current manifest 绑定。

## Identity 快照

以下 SHA-256 均在上述 `main@ed77…` 门内分别用 `sha256sum` 与 Python `hashlib.sha256` 交叉复核，两种方法结果一致：

| 对象 | Current 实体 SHA-256 | Plan 当前写死值 | 一致性 |
|---|---|---|---|
| Plan `docs/agents/documentation-restructure/plan.md` | `eba0666f1cd25b36edb2371c12b1eee35f21cd06a67405a1dd126a549b2bfeca` | 不适用 | 本报告的读取快照 |
| Spec `docs/agents/anthropic-responses-bridge/spec.md` | `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694` | 第 64、665 行均为 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694` | **一致** |
| Acceptance `docs/agents/anthropic-responses-bridge/acceptance.md` | `19635e04886052fa2c2c98e42aab1c87c23c1fb9c8935753201928eaa8463498` | 第 65、665 行均为 `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091` | **不一致** |

Acceptance 为上述 `19635…` bytes 的条件成立。Current Acceptance 仍明确标记 `FINALIZED_ACCEPTANCE_ORACLE`，第 7 行继续绑定同一 Spec `a193da…`，并在 `POLICY-MANIFEST-v1` 中记录 route／request／response／buffering／retry／lifecycle／limits 七域已重新对账；本审计只证明这些声明存在且 identity 发生变化，不替 planner 或后续独立复评重新裁定其规范充分性。

## Planner 精确同步点

1. **`docs/agents/documentation-restructure/plan.md:65`**：这是第 2.3 节 current 规范输入表中的 Acceptance 绑定。将完整旧值 `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091` 同步为完整 current 值 `19635e04886052fa2c2c98e42aab1c87c23c1fb9c8935753201928eaa8463498`。
2. **`docs/agents/documentation-restructure/plan.md:665`**：这是实施 kick-off 的 current bridge 规范输入绑定。将完整旧值 `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091` 同步为完整 current 值 `19635e04886052fa2c2c98e42aab1c87c23c1fb9c8935753201928eaa8463498`。
3. **`docs/agents/documentation-restructure/plan.md:67`**：该行没有单独写出 Acceptance hash，但声称“上述两项 current SHA-256”已在 `main@ed77…` 下双方法交叉复核。更新第 65 行后，这一声明只有在 planner 保留本轮同样的 `sha256sum`＋`hashlib.sha256` 实测证据时才继续成立；本审计已取得该证据。无需仅为 identity 数字机械改写该行。
4. Spec 的第 64、665 行保持 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，不应改动。

## 不应手改的历史 hash

- **`docs/agents/documentation-restructure/plan.md:683`** 的 `Acceptance FINALIZED_ACCEPTANCE_ORACLE@31673…` 位于“R4：bridge `normative_inputs` 只绑定路径”历史 major 处置行，描述的是 R4 当时现场复核并据以关闭该轮缺陷的历史快照，不是 current manifest 或 kick-off 的绑定字段。
- 不要把第 683 行的 `31673…` 手改成 `19635…`。这样会把新 bytes 倒灌进旧评审事实，伪造 R4 当时审阅的输入 identity。若 planner 需要记录本次漂移，应新增本轮处置／复评记录，或在 current 合同位置同步，不得重写旧轮次证据。
- 同理，Acceptance 自身评审处置表内绑定旧 Architecture／Acceptance 快照的历史 hash 也不是本次 Plan identity 同步对象。

## 对后续复评的最小交接

Planner 同步第 65、665 行后，应把修订后的 Plan 作为新 bytes 重新计算 identity，并让定向复评至少核对：current Spec／Acceptance 完整 hash、两者状态、Acceptance → Spec `a193da…` 绑定、七域 `POLICY-MANIFEST-v1` 对账身份、第 67 行双方法证据，以及第 683 行历史 `31673…` 未被篡改。只有新复评达到 0 blocker／0 major，Plan 自身写明的执行门才闭合。

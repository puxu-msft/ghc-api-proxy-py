# Anthropic Responses route policy 独立代码评审

- **评审范围**：只读评审 `/home/xp/src/ghc-api-proxy-py-route-policy` 分支 `feat/anthropic-responses-route-policy`、HEAD `84a22c07db3923768db44a1314e5ae6d5aed2e98` 相对 base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 的最终代码。改动范围为 `src/app/pipeline/route_policy.py` 与 `tests/smoke/test_route_policy.py`。本轮是 happy-path 骨架切片评审，仅报告阻止 squash 的 major；不要求 fallback 或真实 network 接线。
- **总体 verdict**：**可进入下一阶段；未发现阻止 squash 的 major，明确可 squash。**
- **blocker 数**：0。
- **major 数**：0。
- **双视角覆盖证据——机械核对**：逐行对账实现与 smoke，并对照 current `docs/agents/anthropic-responses-bridge/spec.md`、`acceptance.md` 与 `architecture.md` 的 route precedence；检查了 override capability gate、双支持默认 Messages、Messages-only／Responses-only、unknown／missing／conflict fail closed、`/responses`／`ws:/responses` capability、protocol leg 与 transport 正交、Chat 非候选，以及 typed reason／source／error code。定向 smoke、Ruff、Pyright 均通过；全量 pytest、Ruff 与重跑后的全量 Pyright 均通过，目标 worktree 最终保持 clean。
- **双视角覆盖证据——第一人称执行**：分别模拟无 override 的双支持、Messages-only、Responses-only、Chat-only、unknown-only，显式 Responses override 成功与不支持 override，catalog miss／缺失／冲突，选中 leg 的 transport 不可用，以及 `/responses` capability 配 WS transport、`ws:/responses` capability 配 HTTP transport；确认失败均在调用 transport 前终止且不改走另一 protocol leg。
- **smoke 判别力**：临时源码副本中的有效变异对照覆盖 override capability gate、双支持默认 leg、Responses-only、conflict fail closed、`ws:/responses` capability、transport 正交、Chat 排除和 typed override reason；各变异均由对应 smoke 断言以目标测试失败捕获。首次不完整临时包造成的 collection 假红已明确作废，未计入证据；第二轮受外部中断后也只采用中断前已打印具体失败测试名的结果。

## 事实性发现

未发现问题。指定 happy-path 骨架范围内没有 blocker 或 major。

## 主观建议

无。本轮按要求不把非阻断扩展项升级为 squash 门。

## 验证结果

- 定向：`tests/smoke/test_route_policy.py` 全部通过；目标文件 Ruff 与 Pyright 通过。
- 全量：`tests` 全部通过；`src`＋`tests` Ruff 通过；`src`＋`tests` Pyright 为 0 errors、0 warnings、0 informations。
- 独立组合探针确认 Chat／unknown endpoint 不成为候选，`/responses` 与 `ws:/responses` 均证明 Responses protocol capability，physical transport availability 不反向改写 protocol leg。
- 评审后目标 worktree 为 clean；未修改目标分支。

**最终结论：0 major，明确可 squash。**

# Reservation wiring WIP 只读预审

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的精确 `main@29c0ce3230181a113363eb398dfa24d8e41a9012`，以及 `/home/xp/src/ghc-api-proxy-py-reservation-wiring` 的 `feat/resident-budget-wiring@29c0ce3230181a113363eb398dfa24d8e41a9012` 未提交 WIP。最终评审快照的 `git diff --binary` SHA-256 为 `82580fb9c2de082a08d915e1e41d3d3596106b347304736a59d318ba399a4b68`，包含 5 个生产文件与 1 个 smoke test 文件。只检查默认禁用、配置合法性、process 共享 budget、per-request account 仅用于 Responses stream、`finally` release、cancel 不泄漏、non-stream／Messages 不变；不扩展到完整 quota、admission、queue、metrics、History quota facts 或真实 socket partial-write。
- **总体 verdict**：**可进入下一阶段**。在上述最小边界内未发现 blocker 或 major。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

- **机械核对**：每次 shell 取证均在同一调用内校验物理 cwd、Git top-level、branch 与完整 HEAD，并在最终检查前后比对 candidate diff／status 哈希。逐项对账 `src/app/config/settings.py` 的 `0／0` 默认禁用、成对启用、非负和 request 不超过 global 的配置约束；`src/app/server.py` 与 `src/app/runtime.py` 的 lifespan 单例 `ResidentByteBudget`；`src/app/routes/anthropic.py` 仅在 `request.stream` 且 selected leg 为 Responses 时创建 `RequestResidentAccount`；`src/app/delivery/responses_anthropic_stream.py` 把 account 注入 `DeliverySession`，并在 renderer 外层 `finally` 冻结 History 投影后调用 `aclose()`。改动范围 Ruff 通过，全项目 Pyright 为 0 errors／0 warnings；candidate 全量测试在精确快照上为 613 passed。配置正反探针验证默认、合法组合与四类非法组合；聚焦 8 项回归覆盖成功释放、等待 reservation 时取消、既有 prefetch disconnect／二次取消 cleanup、Responses non-stream 与 dual-capability Messages 路径。
- **第一人称执行模拟**：以单一 app process 启动，默认 `0／0` 时 runtime 不构造 budget；启用后 lifespan 只建立一个共享 budget，各 Responses stream 请求从该对象创建独立 account。沿成功 terminal 走到 renderer `finally`，观察 high-water 大于零且 current bytes 归零；沿真实 ASGI 首个 block 已 charge 后客户端 disconnect，观察 upstream 关闭且 process budget 归零。再分别执行 Responses non-stream 与 dual-capability 默认 Messages 请求，确认它们不创建 account，既有 upstream 选择与响应行为保持不变。

## 事实性发现

未发现 blocker 或 major。

## 主观建议

无。本 verdict 仅覆盖上述最小 reservation wiring，不外推为完整 quota 或完整 `REL-06` 通过。

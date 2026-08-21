# Current Implementation 与 Readiness resident wiring 联合定向复评
- **评审范围**：仅复评 current `main@941299fe5a5275c4a5fc327d172a1deeccfb3085`、`docs/agents/anthropic-responses-bridge/implementation.md` SHA-256 `f5f7627296d0f7da37b1e0667557bb27adb23deb822a8d7407ab7a916517487b` 与 `docs/agents/service-cutover/readiness.md` SHA-256 `2879e773ca0dfa000018a3e253f21b7baa3cf024ba89c1702d6c631a14e7d2da`。唯一写入为本报告；未修改两份 living 文档、代码、Git refs、服务或运行态。
- **内容身份稳定性**：连续两次现场取样及最终复验均确认物理 repo root、branch `main`、`HEAD == refs/heads/main`、完整 SHA 与两份文档 hash 不变。
- **总体 verdict**：**可进入 checkpoint。** Resident primitive、production wiring、archive 与限定测试事实可采信；保持 `LIVING／UNVERIFIED／NO_CUTOVER`。发现 1 项不阻断 checkpoint 的 next-action 表述偏差。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。

## 双视角覆盖证据

- **机械核对**：对象级确认 `29c0ce3…` resident primitive 与 `941299f…` production wiring 已线性进入 main，archive refs 精确指向 `8fb6a97e97fe7db9034b1b68636bc40beaf7cec6` 与 `aa5f1d3ef793c8d9b4098df0883d20468a48dc57`，且 wiring archive 的六个结果文件与 current main 相同。对账 settings、lifespan runtime、Responses stream route、delivery cleanup、ASGI uncertainty callbacks、History projection与两份 living 文档；AWK 与独立 Python 解析均得到 Readiness `P0 10＋P1 8＋P2 11＋P3 12＋cc-daemon 2＝43`。
- **第一人称执行模拟**：按默认配置启动时不创建 process budget，Responses non-stream 与 Messages 路径不建立 account；显式同时配置正值时由 lifespan 创建共享 budget，每个 Responses stream 使用 request account，并在 renderer `finally` 冻结投影后清理 leases。再沿 start send 失败、body send 失败、History finalize、真实 kernel partial-write、4142 canary、manager／cgroup及 cutover 分支执行，确认已有 ASGI uncertainty 接缝不会授权重发或 success terminal，但未验证项仍阻止产品与部署升级。

## 事实性发现

[minor] `docs/agents/anthropic-responses-bridge/implementation.md:267`、`docs/agents/service-cutover/readiness.md:150,159,180`——下一动作仍写成“实现真实sink partial-write／delivery-uncertain最小切片”，会让执行者重复开发 current main 已存在的 ASGI `send` uncertainty 状态接缝——`src/app/streaming/sse.py:131-186` 已在 response start／body `send()` 异常时调用 uncertainty hooks，`src/app/routes/anthropic.py:255-273` 已接到同一 stream state，`src/app/delivery/responses_anthropic_stream.py:76-89,350-359` 与既有回归已把 pending batch 标为 uncertain并投影为失败 History；真正未验证的是 kernel／socket 层 partial bytes 可见性，而不是是否有 uncertainty 状态机——把 next 改为 current main 的隔离 `4142` 真上游 canary，或先以真实 kernel probe 找出可复现缺口；只有探针暴露实现缺陷时再建立代码切片，不再造一套 partial-write 框架。

## 已确认事实

1. Resident-byte primitive 已作为 `29c0ce3230181a113363eb398dfa24d8e41a9012` 进入 main，production Responses stream wiring 已作为 current `941299fe5a5275c4a5fc327d172a1deeccfb3085` 进入 main；两份 reviewed source archive 精确且 wiring 六路径结果与 main 等价。
2. `global_resident_bytes=0` 与 `request_resident_bytes=0` 是默认禁用；配置要求两项成对启用、非负且 request 不超过 global。只有两项同时显式为正值时，Responses stream 进入有界 reservation 模式。
3. 完整 quota 仍未完成：其他 resident owner、parser charge-before-read drafts、有限 queue、admission、metrics／History quota facts与全局压力策略继续由各自 owner 承担，不能从 wiring 绿灯外推。
4. 真实 kernel／socket partial-write、真实 manager／effective cgroup与真实 upstream 均未验证；祖先 `d903d72…` 的 Backup smoke R3 也不能外推到 current `941299f…`。
5. ASGI `send` 调用级 uncertainty 接缝已经存在：start／body 异常进入同一 frontier，body pending batch转为 uncertain，History 记录 `delivery_uncertain`，且不得发送成功 terminal；这不是完整 kernel partial-write 证明。
6. 合理 next 是在隔离 `4142` 对 current main 执行低副作用真上游 canary，或针对真实可复现缺口做窄 probe；不得把“尚无 kernel 实证”误写成“尚无 ASGI uncertainty 实现”。

## 数字与运行证据

- Current main 全仓复跑最终为 **613 passed**，Ruff 全通过，Pyright 为 0 errors／0 warnings；`pytest --collect-only` 摘要与独立 node-id 行数均为 613，口径均绑定 `941299fe…`。
- 首次全仓复跑曾有 liveness 心跳计时断言 1 项失败、其余 612 项通过；该目标测试随后连续 20 次通过，同一锚点全仓再跑 613 项全通过，故记录为调度敏感的偶发假红，不把它隐藏或升级为本次 resident wiring major。
- 三条既有 ASGI uncertainty 定向回归独立复跑为 3 passed，覆盖 response-start send failure、first-body send failure与失败 History projection；这只证明 ASGI 调用级接缝，不冒充 kernel partial bytes oracle。
- Readiness required 行由 AWK 状态机与独立 Python section parser 交叉核对，均为 `10＋8＋11＋12＋2＝43`；43 行口径保持。

## 状态边界

- `LIVING`：Implementation 与 Readiness 继续随后继实证更新，本次 0 major 只允许 checkpoint，不表示文档或实现收口。
- `UNVERIFIED`：完整 quota、kernel partial-write、真实 upstream、完整 Acceptance、真实 manager／cgroup、credential与数据 disposition仍未闭合。
- `NO_CUTOVER`：不得据本报告安装或启动生产 unit、触碰 `4141` owner、操作 `cc-daemon`、迁移数据或执行切换。

## 主观建议

未提出超出上述事实修正的额外建议；优先用真实 counterpart／kernel probe取得下一条证据，避免为已有状态接缝重复造轮子。
**最终结论：`0 blocker／0 major／1 minor`，可 checkpoint；保持 `LIVING／UNVERIFIED／NO_CUTOVER`，next 转向 `4142` 真上游 canary或真实缺口，不再开发重复的 partial-write 框架。**

# Anthropic Responses bridge foundations 独立验收报告

## 判定

- **候选**：`/home/xp/src/ghc-api-proxy-py-integrate-bridge`，分支 `integrate/260806-bridge-foundations`，HEAD `614cacde72568d53170be714ea5c9a9b4d889a05`。
- **base**：`ed77c9d191df81c451c25161420515cca52ce6a4`；每次有效 shell 调用均在同一调用内确认物理根目录、分支、完整 HEAD，并以 `git merge-base --is-ancestor` 确认 base 是候选祖先。
- **总体 verdict**：**PASS**，但只针对本报告列出的纯基础 oracle。未发现违反冻结 Spec 的基础行为偏差。
- **明确不覆盖**：route selection、ASGI／HTTP／WebSocket transport、完整 response assembler、block buffering／commit frontier、block sink、retry／History／approval／hooks 的 route-level 接线。它们不是本轮 PASS 的组成部分，状态仍为**未验证**，不得从本报告推导完整 bridge 已通过。
- **写入纪律**：候选 integration worktree 全程严格只读；禁用 Python bytecode 与 pytest cache，所有有效执行前后 `git status --porcelain` 均为空。唯一写入是主树本报告。

## 冻结 oracle 与验收矩阵

本轮先读取 current Spec／Acceptance 并独立推导判据，之后才读取候选实现与现有测试。Oracle 内容哈希由 `sha256sum` 与 Python `hashlib.sha256` 两种不同实现交叉验证，结果一致：

| Oracle | SHA-256 | 本阶段采用的冻结行为 |
|---|---|---|
| `docs/agents/anthropic-responses-bridge/spec.md` | `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694` | reasoning carrier、reasoning item cardinality／no-loss、request 字段处置矩阵、server-tool no-revive、tool identity、thinking capability facts、session liveness 的基础约束 |
| `docs/agents/anthropic-responses-bridge/acceptance.md` | `3acc1273625d13bfb265606cb88ea72ac666193f2ba208d8131fc2b34e03d357` | `REQ-02`～`REQ-05` 中可由纯 converter 验证的部分，以及 liveness primitive 的单 pull、heartbeat、idle timeout、cleanup 行为；不采用 route／transport／sink gate 作为本阶段 expected |

从上述 oracle 得到的本阶段矩阵如下：

| ID | 验收项 | 独立 expected | 结果 |
|---|---|---|---|
| FND-01 | reasoning carrier | 固定 prefix `copilot-api:synthetic-reasoning:v1:`；UTF-8 后使用无 padding 的 base64url；legacy bare sentinel 只恢复 summary；foreign signature 不恢复 | PASS |
| FND-02 | reasoning cardinality／no-loss | 每个 Responses reasoning item 对应一个 thinking block；源顺序不变；非空 encrypted-only item 不丢失；跨轮恢复 byte-exact | PASS |
| FND-03 | request envelope 与字段矩阵 | resolved model、`instructions`、`input`、`max_output_tokens`、sampling／stream 字段按冻结映射；system 空 segment 保留；`cache_control` 与非 allowlist metadata 记录 `DEGRADE`；`top_k`、`stop_sequences`、`context_management` 与未知字段 `REJECT` | PASS |
| FND-04 | server-tool no-revive | typed／server tool declaration、`server_tool_use` 与 server-tool result 在纯转换入口显式拒绝，不转换为普通 function tool | PASS |
| FND-05 | tool mapper 与 identity | 同一 request-scoped 双射原子作用于声明、named choice 与历史 call；`call_id` byte-exact 且不得伪造 Responses item `id`；响应名可由同一 mapper 恢复 | PASS |
| FND-06 | thinking facts | `enabled`／`adaptive` 只依据显式 capability facts 生成 Responses reasoning；预算边界和 effort band 确定映射；缺 capability 或越界时显式拒绝 | PASS |
| FND-07 | session liveness primitive | 一个 upstream `anext` 在 heartbeat 期间保持单一 in-flight；数据顺序不变；idle deadline 触发归类异常；正常结束、超时与取消路径关闭 upstream iterator | PASS |

## 候选实现观测点

这些位置只用于说明实际执行入口，不是代码 review：

- `src/app/anthropic/thinking/responses_reasoning.py:67`：逐 reasoning item 的 Responses→Anthropic 转换入口。
- `src/app/anthropic/thinking/responses_reasoning.py:118`：carrier／legacy／foreign 解码入口。
- `src/app/protocols/anthropic_responses.py:67`：显式 reasoning capability facts。
- `src/app/protocols/anthropic_responses.py:109`：request-scoped `ToolNameMapper`。
- `src/app/protocols/anthropic_responses.py:663`：Anthropic Messages→Responses request 纯转换入口。
- `src/app/streaming/keepalive.py:8`：session liveness primitive。

同一 Python 进程打印并验证了三个被测模块的 `__file__`：

- `/home/xp/src/ghc-api-proxy-py-integrate-bridge/src/app/anthropic/thinking/responses_reasoning.py`
- `/home/xp/src/ghc-api-proxy-py-integrate-bridge/src/app/protocols/anthropic_responses.py`
- `/home/xp/src/ghc-api-proxy-py-integrate-bridge/src/app/streaming/keepalive.py`

三者经 `Path.resolve()` 后均位于 integration worktree 根目录下，因此本轮没有误加载主树或共享安装中的同名模块。

## 实际执行证据

### 现有测试

在候选 worktree 中使用主树虚拟环境的 Python，设置 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-integrate-bridge/src`、`PYTHONDONTWRITEBYTECODE=1`，并通过 pytest `-p no:cacheprovider` 禁止 cache 写入：

| 执行范围 | 实际结果 | 独立收集交叉核对 |
|---|---:|---:|
| `tests/unit/test_responses_reasoning.py`、`tests/unit/test_anthropic_responses_request.py`、`tests/unit/test_streaming_resilience.py` | `82 passed in 1.01s`，退出码 `0` | `82 tests collected in 0.71s` |
| 整个 `tests/` | `362 passed in 7.90s`，退出码 `0` | `362 tests collected in 2.55s` |

首次全量尝试受到共享终端的外部 `Ctrl-C` 与另一会话命令干扰，在收集阶段以退出码 `2` 中断，未把该次运行计为通过或失败。随后使用独立 process group 重跑，得到上表的完整 `362 passed`；重跑前后候选 worktree 均为空状态。

### 独立表驱动／差分 probe

独立 probe 未复用候选测试中的 expected helper，直接从冻结 Spec 构造 expected，并在单次只读 Python 进程内覆盖八组断言：

1. `reasoning-cardinality-order-encrypted-only-no-loss`：包含 summary＋payload、非 reasoning 间隔项、encrypted-only 与 summary-only，断言一对一、顺序与 byte-exact 恢复。
2. `carrier-node-differential-legacy-foreign`：使用 Node `Buffer.from(payload, "base64url").toString("utf8")` 作为独立 counterpart，对 `RU5DPT0`、`b3BhcXVlLfCfmIA` 及 malformed vectors 做差分；同时验证 legacy 与 foreign 分类。
3. `positive-control-restored-baseline`：完成下述 producer-only 正控后恢复原函数，再次通过固定 exact bytes oracle。
4. `request-envelope-transform-reject-degrade-matrix`：完整对象 equality 验证 envelope、system 空 segment、sampling／stream、metadata allowlist、degradation facts 与 strict reject。
5. `server-tool-no-revive-reject`：分别覆盖 typed declaration、`server_tool_use` 和 server-tool result。
6. `tool-mapper-atomicity-call-identity-response-restore`：声明、choice、历史 call 共用映射，`call_id` 保持，未出现伪造 `id`，同一 mapper 可恢复原名。
7. `thinking-explicit-capability-facts-boundaries`：独立预算表覆盖 `100`、`500`、`501`、`1000` 四个合法边界／分段，以及 `99`、`1001` 和 capability 缺失错误路径。
8. `session-liveness-single-pull-order-heartbeat-idle-cleanup`：验证 heartbeat 期间只有一次 upstream pull、数据顺序、正常结束 cleanup，以及 idle timeout cleanup。

实际汇总为：`INDEPENDENT_PROBE_SUMMARY pass=8 fail=0 positive_control=red`，进程退出码 `0`。

### 正控变异

正控采用**内存中的 producer-only 变异**，没有改动任何磁盘文件：临时把 carrier producer 的 prefix 输出改为 `mutated-prefix:`，consumer 完全不参与 expected 生成，仍以 Spec 固定 carrier bytes 比较。结果为：

`POSITIVE_CONTROL_RED producer-only-prefix-mutation target=exact-carrier-bytes`

失败来自目标机制——prefix／exact carrier bytes 不相等，而非 fixture 解析、导入失败或旁路断言。随后恢复原 producer，同一基线 oracle 重新通过。这证明 FND-01 的 probe 能区分目标正确与错误实现，不是同源 round-trip 假绿。

## 未验证边界

以下项目按用户明确要求排除，不能被本报告的 PASS 覆盖：

- Anthropic route 是否选择 Responses leg，以及 capability／override precedence。
- HTTP SSE 与 upstream WebSocket transport、真实 ASGI route、wire header／error envelope。
- Responses response assembler、stream／non-stream parity 与 terminal lifecycle。
- 完整 Anthropic content block buffering、连续 commit frontier、sink batch 与 delivery uncertainty。
- route-level retry、approval、hooks、History、tokenization、cancel、shutdown、backpressure 与 resident quota。

这些项目本轮均标记为**未验证**，而不是缺陷。只有后续按 Acceptance 的对应 route／transport／buffering／lifecycle gate 取得实证后，才能对完整 bridge 给出总体产品符合性判定。

## 最终结论

候选 HEAD `614cacde72568d53170be714ea5c9a9b4d889a05` 相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的本阶段纯基础能力通过独立验收：reasoning carrier 与一对一 no-loss、request conversion 冻结字段矩阵、server-tool reject、tool mapper／identity、thinking capability facts，以及 session liveness primitive 均有实际绿样本、错误路径与独立 probe 证据；producer-only 正控按目标原因变红并在恢复后重新变绿。

**范围内 verdict：PASS。完整 bridge verdict：本报告不作判定。**

> 评审状态：本文件是包含当前状态与验收结论的非平凡交付物。当前执行角色为 leaf verifier，按编排边界不得派生 reviewer；因此主会话在将其作为最终放行依据前仍需安排独立文档复核。
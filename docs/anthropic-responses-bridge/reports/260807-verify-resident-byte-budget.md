# Resident byte budget 独立验收

## Verdict

**PASS**。

验收对象为工作树 `/home/xp/src/ghc-api-proxy-py-reservation` 的精确提交 `63db675b59a659d8c1f06ee9bc0c7bf945bac161`。本结论仅覆盖本轮明确要求的 happy path、backpressure／cancel 机制、payload／rendered lease 生命周期，以及既有 delivery 主路径回归；不扩张为完整 bridge quota、production 配置接线或 `REL-06` 验收。

## 验收依据与矩阵

冻结行为依据为 `docs/agents/anthropic-responses-bridge/spec.md:8,454,463,498,500`，并以主树切片说明 `docs/tmp/260807-next-reservation-slice.md` 限定本轮范围。

| 验收项 | 独立判据 | 结果 | 证据 |
|---|---|---|---|
| 并发 weighted acquire 不超 capacity | 多个 waiter 必须原子取得各自完整 weight；任何可观察时刻 global current 不得超过 capacity；释放 holder 后正确 waiter 必须继续，最终归零 | PASS | stdin 异步 probe 在 capacity `10 bytes` 下先持有 `7 bytes`，并发等待 `6 bytes` 与 `4 bytes`；观测序列为 `7→6→10→10 bytes`，high-water 为 `10 bytes`，最终为 `0 bytes`，退出码为 `0` |
| cancel 不 charge | 尚在 global capacity wait 的 task 被取消时必须原样传播 `CancelledError`；waiter request current 保持零，global current 只包含既有 holder | PASS | stdin 异步 probe 在 holder 占用 `8 bytes` 时取消 `3 bytes` waiter；waiter current 为 `0 bytes`，取消时 global current 仍为 `8 bytes`，holder release 后为 `0 bytes`，退出码为 `0`；候选现有回归测试位于 `tests/smoke/test_anthropic_block_delivery.py:780` |
| payload／rendered leases 正确释放 | semantic payload 在 History／frontier payload 生命周期结束前不得提前释放；rendered lease 在 accepted／uncertain 后释放，writer error 后释放，pending close 时由幂等 `aclose()` 清理；所有路径最终归零 | PASS | stdin 异步 probe 分别执行 accepted、uncertain、writer error、pending close。accepted 与 uncertain 在 ACK 后只保留 semantic charge，writer error 后只保留 semantic charge，`aclose()` 后 request／global current 均为零；候选现有 happy 测试位于 `tests/smoke/test_anthropic_block_delivery.py:739`，pending／uncertain 行为测试位于 `tests/smoke/test_anthropic_block_delivery.py:564,588` |
| 现有 delivery 主路径不回归 | 不传 `resident_account` 时，既有 block ordering、terminal、single writer、pending／uncertain ACK 与真实 Responses→Anthropic stream adapter 行为保持通过 | PASS | `tests/smoke/test_anthropic_block_delivery.py` 全文件通过；`tests/smoke/test_anthropic_responses_stream_route.py` 全文件通过。两次运行前均断言实际加载模块位于候选工作树 |

## 实际运行

### DeliverySession 与 reservation smoke

运行环境绑定到候选工作树并校验：`PWD`、Git top-level 均为 `/home/xp/src/ghc-api-proxy-py-reservation`，HEAD 为 `63db675b59a659d8c1f06ee9bc0c7bf945bac161`；`app.delivery.anthropic_sse` 与 `app.delivery.reservation` 均从该工作树的 `src/` 加载。

使用主树已有虚拟环境解释器，并显式设置候选 `PYTHONPATH` 后运行 `tests/smoke/test_anthropic_block_delivery.py`：`21 passed in 0.36s`，退出码为 `0`。测试数量另由 `pytest --collect-only` 交叉核对为 `21 tests collected`。

### Responses→Anthropic stream adapter smoke

同样绑定候选工作树、精确 HEAD 与候选源码加载路径后运行 `tests/smoke/test_anthropic_responses_stream_route.py`：`15 passed in 2.47s`，退出码为 `0`。测试数量另由 `pytest --collect-only` 交叉核对为 `15 tests collected`。

### 独立最小 probe

probe 通过 stdin 执行，不写入候选树或主树测试文件。它直接从候选工作树加载 `app.delivery.reservation` 与 `app.delivery.anthropic_sse`，覆盖以下状态转移：

- shared weighted budget：holder release 后两个 waiter 可共同达到但不超过 capacity，随后全部 release；
- waiting reservation cancel：`CancelledError` 传播且 waiter 不 charge；
- pending→accepted：rendered lease 在 accepted ACK 后释放，semantic lease保留到 close；
- pending→uncertain：rendered lease 在 uncertain ACK 后释放，semantic lease保留到 close；
- writer error：异常传播，rendered lease释放，semantic lease保留到 close；
- pending session close：semantic 与 rendered leases 一并释放，重复 `aclose()` 不重复扣减。

probe 总退出码为 `0`。

为确认并发 capacity 判据具备判别力，另在独立进程内将 `ResidentByteBudget.can_reserve()` 临时 monkeypatch 为恒真，不编辑任何文件。相同的 `current <= capacity` 断言按预期捕获 `17 bytes > 10 bytes`，输出 `POSITIVE_CONTROL_RED`；这证明绿色 probe 确实会对目标超卖机制变红。新进程退出后原始实现不受影响，候选工作树仍为干净状态。

### 无效的环境尝试

候选 worktree 没有自己的 `.venv`，首次尝试调用候选 `.venv/bin/python` 在进入测试前以退出码 `127` 失败。该结果只说明解释器路径不存在，不属于实现 FAIL。随后改用主树现有虚拟环境，并用候选绝对 `PYTHONPATH` 与模块物理路径断言排除了加载错树风险。

另一次 stream-route 执行被共享终端中的其他并行命令替换，输出 marker 与提交的命令不匹配，因此整次结果作废且未用于 verdict；之后使用唯一 marker、完整 HEAD 与候选模块路径重新执行并取得上述有效结果。

## 范围边界

本轮没有验证，也不据此宣称以下能力已完成：production request／global capacity 配置与依赖注入、parser draft 的 charge-before-append／charge-before-read、route admission、全部 resident owner、queue item cap、deadline／shutdown 产品映射、metrics／History quota facts，以及完整 `REL-06`。这些均不在用户指定的本轮 happy 与 backpressure／cancel 机制范围内。

## 工作树完整性

验收结束前复核候选工作树 `git status --short` 为空。验收过程未修改候选生产代码或测试；主树唯一新增文件为本报告 `docs/tmp/260807-verify-resident-byte-budget.md`，主树其余既有未提交改动保持在验收写前基线中。

# Resident byte budget 定向独立评审

## 评审范围与 verdict

- **候选**：`/home/xp/src/ghc-api-proxy-py-reservation`，branch `feat/resident-byte-budget`，HEAD `63db675b59a659d8c1f06ee9bc0c7bf945bac161`。
- **基线**：`080105b54614e1320a5c193d7206dcaa584c9b41`。
- **限定范围**：weighted `asyncio.Condition` 原子 reservation、request account、lease exactly-once／cancel、`DeliverySession` opt-in 与 rendered lease cleanup、ACK bytes retention 删除、两个新增测试的判别力。不扩展到完整 quota、route 配置、parser draft charge-before-read、admission、metrics 或完整 `REL-06`。
- **总体 verdict**：**修复 major 后可进入下一阶段；当前不可 squash。**
- **Blocker**：0。
- **Major**：4。

## 双视角覆盖证据

### 机械核对

- 每次 shell 调用均在同一调用内验证物理路径、Git top-level 与精确 HEAD；候选相对 base 只有 1 个提交与 4 条改动路径，评审前后候选工作树状态哈希均保持空树哈希 `e3b0c442…`。
- 对 `reservation.py`、`anthropic_sse.py`、`responses_anthropic_stream.py` 与完整 `test_anthropic_block_delivery.py` 做最终文件阅读及 base 差分对账；用源码搜索确认生产 `ResponsesAnthropicStreamState.batches` 累计已删除，剩余 `.batches` 命中均为测试 sink／writer 观测。
- 显式把 `PYTHONPATH` 绑定到候选 `src`，并验证 import origin 为候选 worktree；两个新增测试执行为 2 passed，修改后的测试文件执行为 21 passed，且 `--collect-only` 分别交叉确认收集 2 项与 21 项。Ruff 通过；Pyright 为 0 errors、0 warnings、0 informations。
- 对两个新增测试分别做内存 monkeypatch 正控：禁用 ACK 后 rendered lease 释放时 happy 测试按预期变红；绕过 reservation wait 时 cancel 测试按预期变红。两项测试确实咬住了各自当前主路径。
- 反向控制显示：删除 request aggregate gate后两个新增测试仍为 2 passed；把 `reserve_many()` 改成逐项 reserve、并实测失败后留下 6 bytes partial charge时，两个新增测试仍为 2 passed。

### 第一人称执行模拟

- 模拟同一 request 已持有 6 bytes、再申请 5 bytes、request capacity 为 10 bytes：实现立即产生 `ResidentCapacityError(scope="request", amount=11, capacity=10)`，request／global current 都保持 6，未把不可能由其他 request 释放的 request overage 错当 global wait。
- 模拟另一个 request 占住 shared budget，目标 session 先取得 4 bytes semantic lease、再在 rendered reservation 等待时被取消：取消后目标 request 仍持有 4 bytes semantic lease，随后 `aclose()` 正确释放到 0，说明“取得 lease 后取消由 session cleanup 接管”的实现路径成立。
- 模拟 pending sink 的正常主路径：semantic＋rendered 在 write pending 期间同时收费；ACK accepted 后 rendered 释放而 semantic 保留；`aclose()` 两次后两级余额归零。
- 模拟调用者取得公开 `ResidentLease` 后修改字段及提前调用状态方法，证实可破坏余额与 release exactly-once 不变量。
- 模拟 `DeliverySession.aclose()` 后再次调用 `render_error()`：accepted sink 仍发生一次写入；pending sink 则产生 97 bytes reservation，第二次 `aclose()` 仍保持 97 bytes，证实 close 后可重新产生永久 lease 泄漏。
- 用可控暂停点让 pending ACK 与 `aclose()` 同时进入同一 rendered lease 的 release：一个操作成功，另一个抛 `RuntimeError`，余额虽归零但首次 close 中断，`_closed` 仍为 `False`。

## 事实性发现

### [major] `src/app/delivery/anthropic_sse.py:813-835,889-910` — `aclose()` 后 `render_error()` 仍可重新写 sink，并可产生不可再次清理的 rendered lease

**问题**：`deliver()`／`consume()`／`finish()` 通过 `_raise_if_stopped()` 拒绝 closed session，但 `render_error()` 只检查 `_terminal_scheduled`，没有检查 `_closed`。`aclose()` 首次完成后把 `_closed` 置为 `True`；随后 `render_error()` 仍可取得新 lease、写 sink并把 pending batch加入 `_pending`。第二次 `aclose()` 在 892-893 行直接返回，不会收集这批 close 后新建的 lease。

**证据或失败场景**：独立 pending-sink 探针按 `aclose() → render_error() → aclose()` 执行后，request 与 global current 均为 97 bytes；第二次 close 后仍为 97。accepted-sink 探针也观察到 close 后 `write_count == 1`。这同时破坏“closed session 不再产生输出”、rendered lease cleanup 与计账归零。

**修复建议**：在 `render_error()` 进入 operation lock 后首先执行与其他写入口一致的 closed／stopped 检查；最好把所有可写入口收敛到同一 shared guard，避免下一入口再次漏检。增加回归测试覆盖 accepted 与 pending 两个 outcome：close 后调用必须在 reserve／writer 之前失败，sink 写入为 0，两级余额保持 0，重复 close 仍幂等。

### [major] `src/app/delivery/anthropic_sse.py:837-910` — pending ACK 与 `aclose()` 未串行化，可竞争释放同一 rendered lease并使 cleanup 失败

**问题**：`aclose()` 持有 `_operation_lock`，但公开的 `acknowledge()`／`acknowledge_data()` 不持该锁。对 pending batch 而言，ACK 从 `_pending` 取出 lease并开始 `_release_rendered()` 的同时，`aclose()` 可从 `_rendered_leases` 把同一 lease加入 `_cleanup_leases`，随后两条路径各自执行 `lease.release()`。`ResidentLease.release()` 的 released 检查发生在进入 account condition 之前，不能把这两个并发调用合并为一个成功操作。

**证据或失败场景**：可控 account 在 `release_lease()` 入口暂停两条任务，确认 ACK 与 close 都已到达同一 lease 后同时放行；结果为 ACK 成功、close 抛 `RuntimeError`，request／global balance 虽归零，但 `_closed` 仍为 `False`，首次 cleanup 未完成。这是正常 pending sink 在 client cancel／shutdown cleanup 与迟到 ACK 相交时可达的 exactly-once 竞争。

**修复建议**：让 pending ACK 的队列移除、frontier 处理、rendered lease 释放与 `aclose()` 对同一 session 状态遵守同一串行化合同；不要靠吞掉 double-release error掩盖竞争。增加确定性测试，把 ACK 卡在 release 中点再启动 close，并覆盖相反调度顺序；两种顺序都必须无异常、lease只释放一次、余额归零、首次 close 完成且 session closed。

### [major] `src/app/delivery/reservation.py:169-202` — 公开且可变的 `ResidentLease` 允许调用者伪造 release 状态或篡改 amount，破坏 request／global 计账

**问题**：`ResidentLease` 是公开 mutable dataclass，`account`、`owner`、`amount` 与 `_released` 均可赋值，`mark_released()` 也是公开方法。`RequestResidentAccount.release_lease()` 又直接信任调用时的 `lease.owner` 与 `lease.amount`。因此“唯一释放权”并未由类型封装保证。

**证据或失败场景**：申请 5 bytes 后把 `lease.amount` 改为 1，再 `release()`，request 与 global current 都残留 4 bytes，而 lease 已显示 released；申请 5 bytes 后直接调用 `mark_released()`，后续 `release()` 抛“already released”，两级 current 都永久保留 5 bytes。修改 `owner` 或 `account` 也会让真实 account registry 无法正常释放。

**修复建议**：让 lease 的 account／owner／amount 成为只读属性，实际字段私有且不能由调用者赋值；把 released 状态转换限制为 account 内部能力，不暴露可由普通调用者调用的 `mark_released()`。保留公开 `release()` 作为唯一状态转换入口，并增加 amount、owner、account、released-state 不可伪造及并发 double release 不重复减账的测试。

### [major] `tests/smoke/test_anthropic_block_delivery.py:738-827` — 两个新增测试未守住本切片明确要求的 request aggregate、`reserve_many()` 全有或全无及“容量恢复后继续”合同

**问题**：happy 测试使用 request capacity 等于 global capacity，且只有一个 block；cancel 测试也让 request capacity 等于 global capacity，并只调用单 block `deliver()`，取消后直接结束 session。两者都没有让 request aggregate gate成为决定性条件，没有走多 owner `reserve_many()`，也没有验证 holder release 后 waiter 恢复并完成。

**证据或失败场景**：把 request gate临时退化成 global-only 后，这两个测试仍为 2 passed。把 `reserve_many()` 临时退化成逐项 reserve，独立反例在 `(6, 5)`／capacity 10 的批量失败后留下 6 bytes partial charge，但这两个测试仍为 2 passed。因此当前绿色不能防止本切片核心原子性与 request-local gate 回归。现有 cancel 测试只证明“尚未 charge 的单 owner global wait 被取消”，没有证明多 block charge全有或全无，也没有覆盖“semantic 已 charge、rendered wait 被取消后由 close 清理”。

**修复建议**：按本切片既定测试设计补足或重塑这两项测试：第一项使用普通不同 request／global capacity，先证明第二 delivery 确实被 global contention 阻塞，释放 holder 后必须继续完成并归零；第二项用一个 `consume()` 携带两个 completed blocks，固定 `reserve_many()` 等待／取消时零 partial charge与零 sequencer mutation。邻近子例还应固定 request aggregate立即 typed fail、批量失败无 partial charge、semantic 已 charge 后 rendered wait取消再由幂等 `aclose()` 归零。对 request-gate-disabled 与 sequential-reserve 两种变异至少各有一个永久测试会因目标机制变红。

## 未发现问题的限定结论

- 未发现 weighted global reservation 在正常 API 路径中超卖：request 与 global counter 的成功更新位于同一 `Condition` 临界区，二者之间无 await；release 也在同一临界区减账并 `notify_all()`。
- 未发现 request aggregate 超限被错误等待：当前实现会立即返回 typed request-scope capacity error。
- 未发现正常 pending／accepted／uncertain ACK 路径提前释放 semantic lease；rendered lease 在 ACK 或 writer exception 后释放，semantic lease留到 session cleanup。
- 未发现 opt-in 语义回归：未传 `resident_account` 的既有 19 个测试与新增 2 个测试共同组成的该文件 21 项均通过；生产 stream adapter本切片仍未创建 account，符合“不扩完整 quota／route 配置”的范围边界。
- 未发现 ACK bytes retention 删除遗漏的生产消费者；删除的是无消费者的 `ResponsesAnthropicStreamState.batches` 累计，测试专用 sink 的观测缓存仍保留。

## 主观建议

未提出超出本切片的主观扩展建议。完整 route quota、parser charge-before-read、queue depth、admission、metrics／History 与完整 `REL-06` 继续留在后继切片，不作为本轮 major。

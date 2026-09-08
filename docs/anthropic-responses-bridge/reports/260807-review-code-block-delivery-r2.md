# Anthropic block delivery 骨架定向代码复评 R2

- **评审范围**：只读复评 `/home/xp/src/ghc-api-proxy-py-block-delivery` 的 `feat/anthropic-block-delivery@e506bf87318424e4075b6422772ee0c7e9b8694a`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮逐条复核上一轮 `2 major + 1 minor`：item-level order 不支持多 parts、terminal 越过 open／incomplete source、并发写未串行；同时覆盖 parser→delivery smoke、合法零 block source、较晚 item、typed terminal errors 与并发正控。唯一写入为本报告；未修改候选树。
- **总体 verdict**：**可进入下一阶段；block delivery 骨架可以 squash。** 上一轮两项 major 与一项 minor 均已关闭，未发现新的 blocker 或 major。该结论只覆盖本骨架 checkpoint，不表示真实 ASGI／socket、网络 partial write／delivery uncertainty、retry／post-commit replay、resident quota／backpressure 或完整 bridge 产品已经 `PASS`。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对视角

- 固定并复验目标物理根、branch、完整 HEAD、base 与 clean worktree；相对 base 共两提交，最终改动路径仅为 `src/app/delivery/__init__.py`、`src/app/delivery/anthropic_sse.py`、`tests/smoke/test_anthropic_block_delivery.py`。完整读取最终 delivery 实现、parser 实现与 smoke，而非只看修复 diff。
- 对账顺序模型：`BlockOrderKey` 由 item-level `source_order`、part-level `content_index` 与 semantic kind 构成；`ContinuousPrefixSequencer` 按 `SourceOpened` 建 source state，source 关闭后一次性按 key 排出其全部 blocks，并允许零 block source 推进连续 source 前缀。实现位置为 `src/app/delivery/anthropic_sse.py:92-115,183-256`。
- 对账 lifecycle 与 terminal：typed `DeliverySession.consume()` 穷尽消费 `SourceOpened`、`CompletedBlock`、`UnsupportedResponsesEvent` 与 `ResponsesTerminal`，将 terminal 的 `open_blocks` 与 parser 当前快照对账；非 completed、仍有 open source、缺 usage 或未提交 source prefix 均抛 `ResponsesDeliveryError`，失败后会话保持 poisoned，不会旁路成功 `finish()`。实现位置为 `src/app/delivery/anthropic_sse.py:499-669`。
- 对账并发：同一 `asyncio.Lock` 包住 `deliver()`、typed `consume()` 与 `finish()` 的 sequencer→render→writer await→frontier 全状态转移；不是只限制 writer 对象领取次数。实现位置为 `src/app/delivery/anthropic_sse.py:499-506,518-555,612-624`。
- 定向 smoke 在目标 import path 下通过，覆盖多 parts、较晚 item、零 block source、typed/manual 隔离、incomplete／failed／error terminal，以及 consume／consume 与 deliver／finish 并发。全仓 pytest、Ruff、Pyright 也在固定候选 HEAD 和目标 import path 下通过；候选树门前门后均 clean。

### 第一人称执行视角

- 以真实 `ResponsesStreamParser` 驱动同一 message item：`content_index=1` 先完成、`content_index=0` 后完成时，item 未关闭前不写；`output_item.done` 后按 part order 写出 `A,B`，不再发生同一 item source order 冲突。
- 以独立事件矩阵复核非测试 helper 样例：同一 item 的 sparse parts `9` 先完成、`2` 后完成，最终按 `2,9` 排序；首 source 是空 reasoning 且合法产生零 block 时，后续 source 的 `content_index=4` 仍成为首个已提交 block，不留下 source-order 洞。
- 先打开 source 0 与 source 1，再让 source 1 完成：sink 保持空；source 0 关闭后一次写出 `A,B`。这证明较晚 item 不能越过更早 open source，而不是只证明完成顺序恰好正确。
- `response.completed` 带 open item 会被 parser 降为 typed incomplete，`response.incomplete`、`response.failed` 与 `error` 均抛 `ResponsesDeliveryError`；这些路径不写成功 terminal，后续 manual `finish()` 重新抛同一 stopped error。typed session 即使已提交 block，也不能在 parser terminal 前切换到 manual `finish()`。
- 并发正控先以真实 lock 得到单 active write，terminal task 在 block write 释放前保持等待；随后仅在验证进程内把 `_operation_lock` 替换为空 context manager，同一 oracle 立即观察到两个 active writes 并按目标原因转红。候选文件未被变异，正控后候选树仍 clean。

## 上一轮发现关闭复核

### item-level order 不支持多 parts — 已关闭

`BlockOrderKey` 不再把一个 item-level source order 当成唯一 block key。一个 source 可持有多个按 `content_index` 排序的 completed blocks，source close 后整体释放；source 本身可零 block。`tests/smoke/test_anthropic_block_delivery.py:228-393` 走真实 parser，分别固定多 parts、较晚 item先完成与零 block source；独立事件矩阵另用 sparse part index 复核，避免只复述候选 fixture。

### terminal 越过 open／incomplete source — 已关闭

Parser facts 必须经 typed `consume()` 进入 session；typed 与 manual API 不能混用。Terminal snapshot mismatch、非 completed terminal、open identity、缺 usage、uncommitted source prefix 均为 typed refusal，且错误会 poisoned session。`tests/smoke/test_anthropic_block_delivery.py:395-548` 覆盖 parser terminal 前 manual finish、open-source completed、incomplete／failed／error 与重复 finish；实际 sink 均未出现伪成功 terminal。

### 并发写未串行 — 已关闭

`asyncio.Lock` 覆盖每个 public async 操作的完整状态转移与 sink write。`tests/smoke/test_anthropic_block_delivery.py:553-630` 使用可控暂停 writer，证明 block／terminal 不重叠且 wire 顺序为完整 block 后 terminal；进程内移除 lock 的正控观测到 `maximum_active_writes=2`，确认测试确实咬住目标机制，而非同步 memory writer 假绿。

## 事实性发现

未发现问题。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/delivery/anthropic_sse.py:518-533,612-624` | `deliver()`／`finish()` manual compatibility API 与 typed `consume()` 并存，存在未来调用者误选入口的边界风险 | **本轮不改，不阻塞 squash**：docstring 明确 parser-driven caller 必须使用 `consume()`，mode 机械禁止混用，当前生产代码尚无调用者；接 driver 时应只暴露 typed path |
| `src/app/delivery/anthropic_sse.py:543-608` | session 同时承担 adapter、sequencing、render 与 write orchestration，后续加入 retry／uncertain outcome 时可能职责膨胀 | **登记后续组合 gate**：本 checkpoint 的原子状态边界清晰；待引入 retry frontier 时再分离 driver／mailbox，不在当前骨架提前手搓框架 |
| `tests/smoke/test_anthropic_block_delivery.py:228-630` | 多个组件行为集中于单一 smoke 文件 | **本轮保留**：当前规模可读，且独立 oracle与正控弥补同源风险；接真实 ASGI sink后按 parser／delivery／transport 层拆分 |

## 主观建议

未提出阻止 squash 的主观建议。当前内部方案中，`asyncio.Lock` 比提前引入 mailbox task 更直接地冻结 public API 的串行合同；判据已同时覆盖正常绿、lock 移除后目标红，以及真实 parser 接缝。Python 标准库已提供成熟锁与队列原语，SSE framing 也复用项目既有实现；没有引入第三方流处理框架的必要。

## 保留的后续门

- 真实 ASGI delayed-start 与 socket sink。
- 网络 partial write／delivery uncertainty，以及失败后 frontier／retry／post-commit replay。
- resident quota、backpressure 与取消传播。
- 与 route、semantic parity、usage、header、service runtime 的完整 bridge 合并态验收。

这些项目未被本轮静默删除，也不改变当前骨架的 `0 blocker／0 major` squash 结论；它们继续由后续组合阶段验收。

## 结论

`e506bf87318424e4075b6422772ee0c7e9b8694a` 已关闭上一轮 `2 major + 1 minor`，并通过真实 parser→delivery smoke、独立多 parts／零 block／较晚 item／terminal 事件矩阵、并发正控及全仓静态与测试门。**当前为 0 blocker／0 major／0 minor，Anthropic block delivery 骨架可以 squash。** 本 verdict 不外推为 transport、retry、quota 或完整 bridge 产品 `PASS`。

# Current main resident byte budget 定向独立复核

## 评审范围与 verdict

- **评审范围**：current 主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@29c0ce3230181a113363eb398dfa24d8e41a9012`。范围严格限定为 resident primitive 合并态、首轮 4 项 major 修复——close 后禁写、pending ACK／close 串行、lease 不可重入篡改、request aggregate／`reserve_many()`／capacity waiter——以及既有 delivery 主路径不回退。未扩展 production quota、route 配置与注入、parser draft charge-before-read、admission、metrics、History quota facts或完整 `REL-06`。
- **总体 verdict**：**可进入下一阶段。Current main resident slice 为 0 blocker／0 major；按用户门槛，0 major 可继续。**
- **Blocker 数**：0。
- **Major 数**：0。
- **合并态身份**：目标短 SHA `29c0ce3` 现场解析为完整 SHA `29c0ce3230181a113363eb398dfa24d8e41a9012`；`HEAD == refs/heads/main`，唯一 parent 为 `6dd9411b7950abd9137455383693cc86d3f3ce9b`。该提交只改动 `src/app/delivery/anthropic_sse.py`、`src/app/delivery/reservation.py`、`src/app/delivery/responses_anthropic_stream.py` 与 `tests/smoke/test_anthropic_block_delivery.py`。

## 双视角覆盖证据

### 机械核对视角

- 现场断言物理 cwd、Git top-level、branch、`HEAD` 与 `refs/heads/main`；对提交 pathset、parent 与 subject做对象级核对。主线四个结果 blob逐项等于最终 reviewed source `8fb6a97e97fe7db9034b1b68636bc40beaf7cec6` 的对应 blob，未发现 squash 后内容漂移。
- 完整读取 `src/app/delivery/reservation.py`，并定向读取 `DeliverySession`、stream ACK接线、全部 resident新增测试；逐项对账首轮报告 `docs/tmp/260807-review-resident-byte-budget.md`、R2与R3复评的原失败场景和关闭条件。
- `RequestResidentAccount.reserve_many()` 在 `src/app/delivery/reservation.py:113-163` 先规范化完整 charge集合，拒绝重复 owner与非正整数，分别执行单次申请上限、request aggregate及global capacity检查；进入共享 `Condition` 后在任何 charge前等待，成功时才同时更新 request／global计数与全部 leases。`release()` 在 `src/app/delivery/reservation.py:165-176` 的同一 condition临界区验证 active lease、删除 registry、扣减两级计数、标记 released并 `notify_all()`。
- `ResidentLease` 在 `src/app/delivery/reservation.py:179-208` 以 `__slots__`和拒绝赋值的 `__setattr__()`封闭普通篡改入口；one-shot `__init__()` guard位于任何字段写入之前，重复初始化不会改变 owner、amount或released状态。
- `DeliverySession` 的公开 `acknowledge()`、`acknowledge_data()`、`acknowledge_data_if_pending()` 与 `aclose()` 在 `src/app/delivery/anthropic_sse.py:838-945` 共用 `_operation_lock`。首次 close在锁内置 `_closed`、清空 payload-bearing引用并冻结 cleanup lease集合，然后创建唯一 `_cleanup_task`；所有 close waiter以 `asyncio.shield()`等待该任务，单个 waiter取消不会取消实际 cleanup。
- 所有写入口最终在 reserve／sink前检查 closed：`deliver()`、`consume()`与`finish()`通过 `_raise_if_stopped()`，`render_error()`直接调用 `_raise_if_closed()`；`tests/smoke/test_anthropic_block_delivery.py:963-1040`同时覆盖 accepted四入口与 pending error入口。
- Production stream ACK仍只对 `_BufferedSink`中尚未解决的 batch做 accepted／uncertain确认，见 `src/app/delivery/responses_anthropic_stream.py:330-341`；state不再额外累计已ACK bytes。未传 `resident_account` 时原 delivery路径继续使用相同 renderer、sequencer、writer与frontier合同。
- 在显式设置 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py/src` 后，先断言三个 delivery模块均从 current main物理路径加载，再运行 `tests/smoke/test_anthropic_block_delivery.py` 与 `tests/smoke/test_anthropic_responses_stream_route.py`：**45 passed**。测试数以 pytest `--collect-only`摘要与独立 node-id行数两种口径交叉核对，均为 **45**。运行前后工作区 porcelain指纹一致。
- 首次测试尝试虽显示 45 passed，但 import-origin探针发现 editable install将三个模块解析到 `/home/xp/src/ghc-api-proxy-py-reservation/src/`；该次结果明确作废，未用于 verdict。随后才取得上述绑定 current main的有效结果。

### 第一人称执行视角

- **close 后禁写**：模拟已完成 `aclose()` 的 session依次调用 `deliver()`、`consume()`、`finish()`与`render_error()`。四条路径均在 reservation与sink write之前拒绝；pending error也不能形成新 rendered lease，重复 close复用既有 cleanup结果。
- **ACK／close串行**：分别模拟 ACK先进入 rendered release中点与 close先进入该中点。因为队列移除、frontier处理、lease release、close快照及closed发布都受同一 operation lock保护，两种调度都只释放一次 rendered lease；迟到 ACK在close已先完成时无操作返回，不会 double release。
- **close waiter取消**：模拟首个 close waiter在 cleanup暂停期间被取消，第二个 waiter继续等待同一 `_cleanup_task`。实际 cleanup不被传播取消，semantic与rendered leases最终均释放，重复 close不再扣账。
- **lease不可重入篡改**：申请 owner=`payload`、amount=`5` 后，普通公开／私有字段赋值均被拒绝；再次调用 `lease.__init__("payload", 1)`在字段写入前抛 `RuntimeError`，lease事实和两级余额保持 `5`，随后由所属 account正常 release到零。
- **request aggregate／`reserve_many()`／waiter**：同一 request已持有 `6`、再申请 `5`且request capacity为`10`时立即得到 request-scope typed failure，余额保持`6`；批量`(6, 5)`在同一 capacity下整批失败且无`6`字节 partial charge；shared holder释放后，等待中的`4`字节reservation由`notify_all()`唤醒并完成，最终两级余额归零。
- **既有 delivery主路径**：以不传 `resident_account` 的 block ordering、terminal、single-writer、pending／uncertain ACK及真实 Responses→Anthropic stream adapter测试作为正确样本；与 resident opt-in测试同轮执行全部通过，未发现把正确的非quota路径误拒绝或改变 wire输出的回退。

## 首轮 4 项 major 处置

| 首轮 major | Current main结论 | 最终代码与测试证据 |
|---|---|---|
| `aclose()` 后仍可写并新建永久 rendered lease | **关闭，未回退** | `src/app/delivery/anthropic_sse.py:635-675,736-835,915-945,1000-1008`；`tests/smoke/test_anthropic_block_delivery.py:963-1040` |
| pending ACK与close竞争释放同一 lease | **关闭，未回退** | `src/app/delivery/anthropic_sse.py:838-945`；`tests/smoke/test_anthropic_block_delivery.py:1042-1153` |
| `ResidentLease`可由普通赋值或`__init__()`重入篡改 | **关闭，未回退** | `src/app/delivery/reservation.py:165-208`；`tests/smoke/test_anthropic_block_delivery.py:913-950` |
| request aggregate、`reserve_many()`全有或全无及容量恢复 waiter缺少判别性测试 | **关闭，未回退** | `src/app/delivery/reservation.py:113-176`；`tests/smoke/test_anthropic_block_delivery.py:835-910` |

## 事实性发现

未发现问题。定向检查未发现 blocker、major、minor或等价入口绕过；4 项首轮 major均在 current main的最终代码与永久回归中关闭，最小现有 delivery／stream smoke未发现主路径回退。

## 主观建议

无。本轮不应借 resident primitive合并态复核扩展完整 quota；production配置／注入、parser draft、全部 resident owners、admission、metrics／History及完整`REL-06`继续保留为后继范围，不影响本次“0 major可继续”的限定结论。

## 结构怪味扫描

- `src/app/delivery/reservation.py:113-176`——**计账真相源分叉**——request与global charge／release仍集中在account和同一condition临界区；处置：本轮无需修改。
- `src/app/delivery/reservation.py:179-208`——**只读外观但存在等价写入口**——普通赋值与重复初始化均由共同构造边界拒绝；处置：本轮无需修改。
- `src/app/delivery/anthropic_sse.py:838-984`——**ACK／close cleanup双 owner**——operation lock、唯一cleanup task与account active-lease校验共同约束生命周期；处置：本轮无需修改。
- `src/app/delivery/responses_anthropic_stream.py:64-87,330-341`——**ACK bytes重复保留**——production state未重复累计已解决bytes，`_BufferedSink._pending`只保留待ACK批次；处置：本轮无需修改。

## 最终结论

**`main@29c0ce3230181a113363eb398dfa24d8e41a9012` 的 resident primitive合并态为 `0 blocker／0 major`，本轮 4 项 major均已关闭，既有 delivery主路径未回退；按用户门槛，0 major可继续。** 该结论仅覆盖本文限定切片，不表示完整 quota、完整`REL-06`、完整 bridge、部署或cutover已经通过。

## 报告评审状态

本会话是叶子 reviewer，不能派生另一名 reviewer。本文已完成事实证伪、双视角执行模拟、current-main模块来源校验与最小现有测试；按 wrap-up产物规则，主会话在采用本文前仍须独立复核 current-state断言、测试口径与引用行号。该义务不改变本轮 `0 blocker／0 major` 的定向结论。

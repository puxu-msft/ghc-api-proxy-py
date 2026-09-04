# Copilot item identity WIP 只读预审

- 评审范围：`/home/xp/src/ghc-api-proxy-py-item-identity`，分支 `fix/copilot-item-identity`。
- 总体 verdict：`PENDING`。候选在预审期间持续变化，不能把旧快照结论冒充当前结论。
- blocker 数：0。
- major 数：1，绑定最后一个完整检查且测试前后稳定的快照，不自动外推到当前移动 WIP。
- 最后完整检查快照：`HEAD 0e66cab5ffd636e40a0f378d6017326603a3196a`，diff SHA-256 `5e0368b440475711c1266b890d377b63dd6eef89365781667ec6f58ce74fe7ec`。
- 报告写入时观测：`HEAD 0e66cab5ffd636e40a0f378d6017326603a3196a`，diff SHA-256 `c42a9d1e5077e1526f70b7ce7cead209a64052ec51b598543efc9cf957cdd2cf`。若与上一行不同，必须按当前 bytes 重审。

## 双视角覆盖证据

### 机械核对

- 最后完整检查快照中，parser 与 renderer 的 item identity 参数默认均为 strict；route 仅对显式 Copilot 同时放宽 response ID 与 item ID；generic 仍 strict。
- present ID 仍要求非空；`output_index` 仍经既有 item 表关联；文本块仍以 `(output_index, content_index)` 建键；item done 仍核对最终 content indexes。
- item type、function `call_id` 与 `name` 的比较不受 relaxed 开关影响。
- 使用候选绝对 `PYTHONPATH` 运行 identity 定向集，最后稳定快照结果为 `21 passed, 51 deselected in 2.14s`；运行前后 diff hash 相同，导入路径指向候选 worktree。该数字仅对应单次 pytest 命令，未用不同原理交叉验证。

### 第一人称执行模拟

- 默认调用方：response ID 与 item ID 保持 strict。
- Copilot route：response／item ID 可漂移，present ID 仍非空，坐标继续关联同一语义 item／content。
- generic route：同类 item ID 漂移失败为 `item_id_mismatch`。
- relaxed parser 未落盘负向探针：未知 `output_index` 为 `unknown_output_item`，item type 漂移为 `item_type_mismatch`，`call_id`／`name` 漂移为 `function_call_identity_mismatch`，content 坐标不一致为 `message_content_mismatch`。

## 事实性发现

[major] `tests/unit/test_responses_stream_parser.py:82-171`，绑定 diff `5e0368b440475711c1266b890d377b63dd6eef89365781667ec6f58ce74fe7ec` — relaxed 模式的仓库最小回归门没有直接钉住关联坐标、item type、`call_id` 与 `name` 仍严格 — 当时新增测试覆盖 ID 漂移／缺失／空值，但若未来误将关联、类型或 function identity 检查置于 `require_stable_item_id` 条件下，这组测试仍可能全绿；运行探针证明当时实现行为正确，因此问题是测试判别力缺口 — 在稳定 WIP 上补最小参数化负例并重跑；若当前移动 WIP 已补齐，则本条在下一轮按当前 file:line 与测试结果关闭。

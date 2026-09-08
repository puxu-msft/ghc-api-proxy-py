---
report_id: merge-resolution-review-runtime-260905
status: settled
reviewed_main_tree: 96fb3be3d2a0cf7f683c18dc947884cc33e87508
reviewed_at: 2026-09-05
transcription: 主会话从隔离 reviewer 的 SendMessage 原样转录；reviewer 无法写入主工作树。
---

# Merge resolution runtime review

- Parents：ours `605d42bd85d6d25bc5e4b73dada727a893742527`，theirs `8ac6522896cdd3a43d796c33999595c25b8f798b`，base `e1b2baa99637349d2f552343c57769a311bfb179`。
- Verdict：**NEEDS-FIX**。
- Counts：blocker 0，major 1。

## Major

### M1：terminal `response.output` 不是不可逆的最终快照，后续 item event 可重新写入或补出项目

位置：`src/app/pipeline/response_observation.py:264-289`、`src/app/pipeline/response_observation.py:459-506`。

失败场景：observer 先收到 `response.output_item.done`，再收到 `response.completed` 且 `response.output=[]`。终态处理会正确清空 draft；但若终态后再出现一个不同 `output_index` 的迟到或异常 item event，item mutator 仍会在空字典中新增该项目。最终 `snapshot().output_items` 不再是终态声明的空数组，TUI 会把本应为绿色的 action-free `completed` 显示成带 client action 的未完成工作。现有 late-partial 测试只覆盖“终态中已有同一 index”这一种情形，逐 index source 比较无法保护终态的完整集合边界。

同根场景：终态事件的 `response` 本身不是 object 时，代码只记录 issue，没有丢弃此前 draft，导致不可分类的终态继续冒充为此前已知项目集合。

建议修法：给 observer 增加终态快照已封口的全局状态；任何 `complete_body=True` 的终态都先封口，合法数组替换全集，缺失或 malformed output 保持 `None`；终态 `response` 非 object 时也清空为不可分类状态。封口后忽略所有 `_ITEM_EVENTS`，而不是只在相同 index 已有 `COMPLETE_RESPONSE` 时拒绝降级。补测试覆盖 terminal empty／missing／malformed 后出现新 index、terminal `response` 非 object 前已有 draft，以及合法 terminal item 后迟到新 index。

## 其余核验

派发清单 C1～C8 除上述 M1 外未发现 blocker／major。reviewer 未执行测试；该报告只审固定 tree，不把 mock 测试冒充真实 upstream 实况。`my-agents:as-reviewer` 在 reviewer 环境不可用。

## 复评结果

固定 main tree `c0e5d2b6cad5662173aa3c6cb8ec990efbac22ef`：**PASS，0 blocker，0 major**。`complete_body=True` 会封口 item 集合；终局后的同 index／新 index item event 都不能改写；empty 保持 `()`，missing／null／malformed／non-object terminal response 保持 `None`，non-object output element 保留为对应位置的 UNKNOWN item。新增与既有测试覆盖上述场景，未发现相邻 major。复评没有重跑测试，采用协调会话提供的 Ruff、Pyright 与定向测试结果。

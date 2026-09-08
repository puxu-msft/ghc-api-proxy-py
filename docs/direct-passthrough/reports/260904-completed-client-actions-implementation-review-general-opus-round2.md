---
report_id: completed-client-actions-implementation-review-round2
attempt_id: completed-client-actions-implementation-review-round2-260904-opus-01
status: in-review
reviewed_at_rev: "uncommitted candidate bound by SHA-256 manifest below"
reviewed_at: 2026-09-04T02:01:54+00:00
---

# Completed client actions implementation review，round 2

## 评审范围

只续评首轮 `completed-client-actions-implementation-review-01`，并只读取 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py`、`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py` 与 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260904-completed-client-actions-implementation-review-disposition.md` 的当前内容。判定轴限于 C1、C2、C8、C9；按调用方指令不重开首轮已通过且本修复未触及的 C3～C7。

## 总体 verdict

`pass`。首轮唯一 major 已关闭；本轮未发现 blocker／major，当前候选可提交。

## Blocker 数

0。

## Candidate 版本绑定

源码阅读前后两次 SHA-256 一致，本报告只约束下列确切内容。

```text
6571b11fbb40341fd6f89b6f92c971c78f3d57675f2ba04f44b6b046881a90ae  src/app/pipeline/delivery/passthrough.py
61babb0274b0530d0cc214199cdd78235415a8f130ebba8ca97d0ef7af2bbc3c  tests/unit/pipeline/delivery/test_responses_passthrough.py
09514fe4569c167688ce82af4b720c7a427f3f07d82da8385b8d171ee7aac2b2  .dev/docs/direct-passthrough/reports/260904-completed-client-actions-implementation-review-disposition.md
```

## 首轮 finding 处置

| Finding | 状态 | 证据 |
|---|---|---|
| `completed-client-actions-implementation-review-01` | closed | `_item_object()` 现在以 `None` 唯一表示 object 缺席，并原样保留 present-empty `{}`；batch 只跳过 `None`，因此空 item 会进入 indexed merge 并由 classifier 投影为 true。见 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:109-139`。 |

focused probe 在当前 candidate 上得到 `classifier=unknown`、`empty_batch_projection=True released=1 held=0`，与首轮反例 `batch_projection=False released=0 held=1` 相反。done-side 缺 object 时第 198～200 行显式用 `{}` 分类，保留原有 conservative stop-reason 语义；batch 对真正不存在的 object 仍跳过，focused control 得到 `absent_batch_projection=False`、`absent_done_stop_reason=tool_use`。

新增测试 `/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:402-409` 同时断言 classifier 的 `{}` 为 `UNKNOWN` 与 batch projection 为 true。处置报告 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260904-completed-client-actions-implementation-review-disposition.md:8-16` 对改动、65-test／Ruff／Pyright 证据、第 9 个 mutation control 与复评边界的记载均与本轮读取到的代码和测试一致。

## C1／C2／C8／C9 复评

| Criterion | 结论 | file:line 证据 |
|---|---|---|
| C1 | 通过。present-empty `{}` 不再被 truthiness 丢弃，三态 classifier 的 `unknown` 现在按唯一合法 bool projection 变为 true；新增 regression 正面锁住该边界。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:109-123,133-139`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:402-409`。 |
| C2 | 通过。indexed opening／closing merge 仍先聚合、后分类；`None` 与 `{}` 的区分没有改变 server `tool_search_call` 被 closing discriminator 覆盖为 false 的路径，新测试补上 missing-type 空 item 的 true 路径。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:103-123`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:375-409`。 |
| C8 | 通过。修复只改变分类输入是否存在，`RawEventBatch.encode()` 仍逐事件调用 `encode_frame`，没有改写 event、framer、continuation 或 wire bytes；新增回归只观察 bool projection。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:109-130,198-202`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:402-409`。 |
| C9 | 通过。本轮修复闭合 present-empty／absent 的状态边界，两个 `_item_object()` consumer 均已适配 `dict | None`；未发现新的 blocker／major correctness、state-consistency、serialization 或 efficiency 缺陷。 | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:109-139,183-202`。 |

## Findings

未发现 blocker／major；也未发现需要阻止提交的 minor。可提交候选。

## 已运行证据的资格

- 调用方提供的 65 tests、Ruff clean、Pyright 0、第 9 个 mutation 目标判红与恢复后 61 tests 证据按 trust-first 使用，没有冒充本 reviewer 重跑。
- 本 reviewer 只重跑了首轮最小反例及 absent control，并以 `PYTHONDONTWRITEBYTECODE=1` 从主树绝对 `PYTHONPATH` 导入当前 candidate；该 probe 证明 finding 的失败机制已反转，但不冒充完整测试套件。
- 若上述三个文件任一 SHA-256 改变，本轮 verdict 不自动延伸到新 bytes。

## 未采纳／排除路线

- 未重开 C3～C7，因为调用方明确限定复评范围，且本轮三个 hash 所对应的修复只触及 item-object 分类边界与其测试／处置记录。
- 未把 absent item object 在 batch 与 done-side 的不同处置报为缺陷；前者没有 item facts 可合并而保留 skip，后者必须为旧 stop-reason consumer 作 conservative classification，这正是处置记录明示并由 focused control 确认的两种定义域。
- 未重复受影响 65-test suite、Ruff、Pyright 与 mutation runner；没有源码矛盾要求推翻调用方给出的 freshness evidence。

## 整体判定

首轮 finding 01 已闭合，C1、C2、C8、C9 均通过。在本 hash manifest 上，候选可提交。

## 我最没把握的三个判断

1. absent item object 的 batch-skip 与 done-side conservative classification 是否应长期保持是定义域判断；本轮证据足以确认它不是首轮 finding 的未修残留，但若 Spec 将来把“event 表示 item”本身定义为可分类事实，应另开规格修订而非重开本 finding。
2. mutation runner 的失败位置来自调用方与处置报告，没有由本 reviewer读取原始 runner output；按 trust-first 足以支持本轮 verdict，但不能冒充独立重跑。
3. 没有第三个真实的不确定判断；C1、C2 与 C8 的 source path 均为直接数据流，证据强到足以据此行动。

## 执行本契约时遇到的摩擦

none

## 交付声明
delivery_complete: true
completed_at: 2026-09-04T02:01:54+00:00
finding_total: 0
blocker_count: 0
major_count: 0
minor_count: 0
nit_count: 0

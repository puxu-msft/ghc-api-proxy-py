# `completed` 与 client actions 实现评审处置

日期：2026-09-04

对象：主工作树相对 baseline `4b7d74f56b8b0264b481a2fefe275a233979fbb2` 的 completed/client-actions source 与 tests 候选。

首轮 reviewer 原报告位于其隔离 worktree 的 `review-completed-client-actions-implementation.md`。结论：0 blocker、1 major。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| completed-client-actions-implementation-review-01：RawEventBatch 在分类前跳过 `{}`，把 missing-type unknown 错投影为 false | 采纳 | C | `_item_object()` 改为 `dict | None`，用 `None` 唯一表示没有 item object，保留存在但为空的 `{}`；batch 只跳过 `None`，done-side 没有 object 时显式以 `{}` 分类，继续得到 unknown→true。新增 empty-item batch 回归，同时保留“没有 item object”的跳过语义 |

修复后证据：`uv run pytest tests/unit/pipeline/delivery/test_responses_passthrough.py tests/unit/pipeline/delivery/test_anthropic_passthrough.py -q` → 65 passed；targeted Ruff clean；targeted Pyright 0 errors。Mutation 把 `if item is None` 改回 `if not item` 时 `test_an_explicit_empty_item_projects_unknown_for_buffering` 目标变红；恢复后包含全部 9 个 controls 的 runner 报 `ALL CONTROLS RED; CLEAN CANDIDATE GREEN`，核心 61 passed，4 个 snapshot files 逐字恢复。

## 第二轮复评

Reviewer 原报告位于其隔离 worktree 的 `review-completed-client-actions-implementation-round2.md`。结论：**pass；首轮 finding closed，C1、C2、C8、C9 通过，0 blocker、0 major、0 minor，当前候选可提交**。复评最小探针得到 `classifier=unknown`、`empty_batch_projection=True released=1 held=0`，并另证 absent item object 仍保持 batch skip、done-side conservative stop-reason classification。

## 最终候选证据

评审共识后对稳定候选只运行一次全量验证：`uv run ruff check src tests` clean；`uv run pyright src tests` 0 errors；`uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80` 得到 2213 passed、2 skipped、coverage 91.29%。随后以精确 pathspec 提交为 `bb5783f17f8f21017010a14d00b762b49ee6cc13`，提交后 13 个 source/test 路径均干净；没有推送。

## Closeout 文档评审

Reviewer 原报告位于其隔离 worktree 的 `review-completed-client-actions-closeout-docs.md`。结论：pass，0 blocker、0 major、1 minor，docs 可提交。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| completed-client-actions-closeout-docs-review-01：Direct Spec revision 已到 v21，顶部仍写 v20 | 采纳 | C | 机械同步为 `DRAFT v21 — 待复评`；“待复评”继续保留，因为整份 direct-passthrough Spec 还有本切片外的开放面 |

未采纳项：无。

复评范围：原 finding、修复 diff，以及受影响的 C1、C2、C8、C9；首轮已通过且未受改动的 C3～C7 不重开。
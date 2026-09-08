# Task 3B source review follow-up

## 评审范围

- 被检对象：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3-integration` 相对 `16a0904496f0af0a7832e4dd4bcb18fdc69919f9` 的**未提交** diff。HEAD 仍是该 base，无 source commit。
- 工作树 `git diff --name-status` 仍只含 brief 允许的 6 个路径；`worker.py` 未改。相对上一轮 source review，source 增量很小：`features.py` 把 `MEDIA_REASON` discard 限制在 whole 路径；`types.py` 收紧 failed checkpoint 矩阵；`learning_store.py` 的 `_encode_sample` 拒绝 pending `committed_order`；对应 tests 增补负例。
- 判据仍是主工作树 `spec.md`／`plan.md`／`task-3b-brief.md`，以及上一轮 `260907-task3b-source-review-grok-xhigh.md` 的 T3B-SR-01～03。实现者 `260907-task3b-implementation-gpt-m-fix2.md` 只作未核验 claim。
- 只读：不修改、不提交、不启动 4141、不碰 shared main。
- 复核两问分开答：上轮条目完成度 ≠ 当前系统状态。

## 总体 verdict

**APPROVED。** blocker=0，本轮新发现 major=0／minor=0。上轮 3 条均 `closed`。按 brief 的 0 Critical／Important 闸门，**不再因 T3B-SR-01～03 阻塞 commit**；commit 前仍须跑文末机械检查。

## 上轮条目完成度

| ID | 状态 | 证据 |
|---|---|---|
| T3B-SR-01 | **closed** | `capability_visual_tokens(..., media_items=None)` 才 `discard(MEDIA_REASON)`；per-item slice 不再改共享 reason 集。独立探针：image+PDF 与 PDF-then-image 均 `MEDIA_REASON=True` 且 whole visual `None`；image-only 仍 discard。`test_mixed_image_and_pdf_preserves_generic_media_reason_after_item_visual_success` 覆盖正向 mixed。 |
| T3B-SR-02 | **closed** | `TokenLearningObservation` failed 只接受 `NotCommitted` 或 `NotAttempted(FAILURE_BEFORE_POLICY)`。探针：`duplicate-sample`／`sample-rejected`／`NoChange` 均 ValueError；合法两组合 ACCEPTED。raw event JSON 改成 `not-attempted/duplicate-sample` 或 `sample-rejected` 后 startup=`INVALID_STATE` 且 bytes 不变；合法 `failure-before-policy` 可重启。 |
| T3B-SR-03 | **closed** | `_encode_sample` 在组 JSON 前拒绝 `committed_order is None`（`sample codec requires a positive committed_order`）。pending `_sample(0)` 探针 typed reject；stamp 后 encode 成功。stamp 测试现直接调用 codec 负例，不再只靠 monkeypatch。 |

## 当前系统状态（抛开上轮清单）

未发现本轮修复引入的新正确性／合同缺陷。抽查上一轮已成立的承重面，行为未回退：

- image-only 仍丢掉 `MEDIA_REASON`（公式成功）；PDF-only 与「成功 image + 缺 dimension image」保留该 reason。
- duplicate／committed observation 矩阵仍拒绝错 family。
- rollover：outcome `CapacityRolledOver`，public snapshot epoch=1 且 samples/checkpoints 空，DB 两行 sample 仍在 epoch 0（`committed_order` 1 与 2）。
- current-sample prune：reason `pruned`，checkpoint outcome `PrefixCheckpointApplied`，retained sample 仍在 snapshot。
- allowed paths 无扩大。

残余（不升格为本轮 finding）：failed 仍允许 `ANALYSIS_FAILED`+`NotCommitted`（DTO 无 phase 字段；上轮已把 reason 级收紧列为可选，不把已关闭的 SR-02 重开）。A40 单变量 mutation／788 SQLite／worker process pickle／A44 全矩阵 mutation 仍如初轮未验证边界，不是本轮回归。

## Findings

未发现新问题。

## 未验证边界

与初轮相同、本 follow-up **没有**新证据关闭的：

- A40 nested framing 漏算／重复、item 算入 fixed context、verbose prefix mutation、788-item **SQLite** round-trip、worker 真实 process pickle。
- A41 same-timestamp pairing／single canonical base（属后续 predictor）。
- A42 16／8 领域 policy（brief non-goal）；CAS mismatch 无独立负例。
- A44 committed 五结果全矩阵、`pruned→skip`／`pruned→NoChange` 源码 mutation。
- A45 formula 仍属 Task 4B-P。
- 完整 `tests/unit/tokenization`、Ruff、Pyright：本轮未跑。只跑了 10 个 focused tests（`10 passed in 2.40s`）加独立 python 探针。不得用实现者自述的全量绿灯替代。

## 搜索面

- 读最终状态：`features.py:345-366`、`types.py:1235-1355`、`learning_store.py:4928-4975`／`5898-5902`；新测试 `test_features.py:1278-1296`、`test_learning_store.py:3253-3254`／`3505-3558`。
- 命令：`git diff --name-status/--stat`；独立探针（mixed／order-swap media reason、failed DTO 五组合、pending encode、startup 两例 corruption + 一例合法 failed、rollover DB rows、prune Applied、stamped encode）；focused pytest 10 项。
- 未跑：完整 tokenization／learning-store selectors、Ruff、Pyright、源码破坏 mutation、4141。

## Commit 前必须做的机械检查

实现者在独立 worktree 上、**不接管 shared main、不启动 4141**，至少：

1. `uv run pytest -q tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py`
2. `uv run pytest -q tests/unit/tokenization`
3. `uv run ruff check src/app/tokenization/features.py src/app/tokenization/types.py src/app/tokenization/learning_schema.py src/app/tokenization/learning_store.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py`
4. `uv run pyright` 对上述六路径
5. `git diff --name-only` 仍仅这六路径；`git diff --check`

本 follow-up 不把上述 1–4 标为已执行。source commit 仍须在本报告之后、restack 到 current main 之前另做 path-overlap 检查（brief 原要求，非本轮回归）。

## Verdict

**APPROVED。**

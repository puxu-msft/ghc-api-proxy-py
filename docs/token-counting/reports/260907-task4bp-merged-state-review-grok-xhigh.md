# Task 4B-P merged-state review（squash onto current main）

## 评审范围

- 被检对象：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task4bp-main-integration` 相对 current main `3badac7f6b020764cf8e30b2528ff51055dad0c2` 的 **`git merge --squash` source `d10121c902daef7da090c4d6702d4b3eb6d28c80`** 暂存 candidate，尚未提交。
- 无 `MERGE_HEAD`、无 unmerged；工作树＝index。
- merge-base(`3badac7f`, `d10121c`) = `3badac7f`（source 直接长在 current main）。
- 判据：修订 Spec A45／brief C04、Plan Task 4B-P、source review `260907-task4bp-source-review-grok-xhigh.md`（APPROVED）。
- 只读：未改、未提交、未操作 4141／shared main。未跑完整 gate。

## 总体 verdict

**APPROVED。** blocker=0，major=0，minor=0。暂存恰两 allowed paths，与 `d10121c` **byte-identical**；无冲突／泄漏；4A cold 与 3B seam 仍可 import；C04／current-zero／newest31／all-variants 探针与 source review 一致。

## Staged 边界

| status | path |
|---|---|
| M | `src/app/tokenization/prediction.py` |
| M | `tests/unit/tokenization/test_prediction.py` |

`git diff --cached --stat`：889 insertions, 13 deletions，与 `d10121c` vs `3badac7f` 相同。未暂存 types／store／scaling／pipeline／`.dev`／human-controlled。冲突标记无。工作树对 `d10121c` 全量 diff 为空。

## Seam／non-goals

- `CountTokensRequestError`、`LocalTokenWorker`、`scale_local_estimate(0,1.5)=1` 仍可用。
- `prediction.py` 无 `learning_store`／`ReplacePrefixCheckpoint`。
- 探针：C04 110／110／110 count=3；C06 multiplicative 100 count=3、additive count=4；C09 selected deterministic；C07 five variants、selected exact；无 prefix 时 4A cold-start。

## Findings

未发现问题。

## 未验证边界

- 未在本 merged 树跑 pytest／Ruff／Pyright（source isolation 曾 36 passed，不折算）。
- 未跑 C01–C12 源码 mutation、int tests、4141。
- Task 5 index cache、4B 16／8、4C 不在范围。

## Commit 前必须检查

本 isolation 树、不接管 shared main、不启 4141：

1. `uv run pytest -q tests/unit/tokenization/test_prediction.py`
2. `uv run pytest -q tests/unit/tokenization`
3. `uv run ruff check` 与 `uv run pyright` 对上述两路径（brief 另要求 `pyright src tests`）
4. `git diff --cached --name-only` 仍恰这 2 个文件；`git diff --cached --check`
5. subject 与 source 一致：`feat: learn token prefix residuals`

本 review 不把 1–3 标为已执行。

## Verdict

**APPROVED。**

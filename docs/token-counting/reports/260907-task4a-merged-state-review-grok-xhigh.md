# Task 4A merged-state review（squash onto current main）

## 评审范围

- 被检对象：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task4a-main-integration` 上相对 current main `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5` 的 **`git merge --squash integration/task4a-prediction`（`7d7e43b32c1d90e1723e6ad469262c5617e670a5`）暂存 candidate**，尚未提交。
- 无 `MERGE_HEAD`、无 unmerged index；工作树与 index 一致。
- merge-base(`6044919a`, `7d7e43b3`) = `6044919a`（source 直接长在 current main 上）。
- 判据：Task 4A brief（READY follow-up）、Spec／Plan 的 4A 边界、source review `260907-task4a-source-review-grok-xhigh.md`（APPROVED）。
- 只读：未改、未提交、未操作 4141／shared main。未跑完整 tokenization gate。

## 总体 verdict

**APPROVED。** blocker=0，major=0，minor=0。暂存恰为四个 allowed paths，且与 `7d7e43b3` **byte-identical**；无冲突残留、无 path leakage；Task 3B carriers／`6044919a` seam 仍可 import；pure suffix／finalization 探针与 source review 一致。

## Staged 边界

相对 `6044919a` 暂存恰好：

| status | path |
|---|---|
| A | `src/app/tokenization/prediction.py` |
| M | `src/app/tokenization/scaling.py` |
| M | `tests/unit/tokenization/test_local_estimate_scaling.py` |
| A | `tests/unit/tokenization/test_prediction.py` |

`git diff --cached --stat`：679 insertions, 7 deletions，与 `7d7e43b3` 对 `6044919a` 的 `--stat` 相同。未暂存 `types.py`／store／pipeline／`.dev`／`docs/.human-controlled/`。`git ls-files -u` 空；冲突标记扫描无命中。工作树对 `7d7e43b3` 的全量 `git diff` 为空。

## 与 source／main 的关系

- 四文件 `git diff --quiet 7d7e43b3 -- <path>` 全部 IDENTICAL。
- main 在这四条路径上自 merge-base 以来无独立改动（base 即 HEAD）。
- 因此不存在 3B overlap 重写：`prediction.py` 为新建；`scaling.py` 仅把 wrapper 接到 `finalize_local_prediction`。

## Seam／non-goals

- `LocalTokenWorker.estimate`／`CountTokensRequestError` 仍可从 merged tree import。
- `prediction.py` 不含 `learning_store` 文本。
- 探针：`finalize(100.5,1.1)=111`、`scale_local_estimate(0,1.5)=1`、bool value 拒绝、C07 形 suffix `215`、record keys prefix+cold。无 4B-P／16／8／drift／Task 5 路径进入 staged tree。

## Findings

未发现问题。

## 未验证边界

- 未在本 merged worktree 跑 pytest／Ruff／Pyright（source review 曾在 isolation 树跑 focused 38 passed，不折算为本树证据）。
- 未跑 `tests/int` 或 4141。
- 未重放 C01–C14 源码 mutation。
- `scale_local_estimate` 对 `driver.py` 现网 0／shortcut 的 ASGI 差未测。

## Commit 前必须检查

在 **本 isolation worktree**、不接管 shared main、不启 4141：

1. `uv run pytest -q tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py`
2. `uv run pytest -q tests/unit/tokenization`
3. `uv run ruff check` 与 `uv run pyright` 针对上述四路径（brief 另要求 `pyright src tests`）
4. `git diff --cached --name-only` 仍恰这 4 个文件；`git diff --cached --check`
5. subject 与 source 一致：`feat: predict tokens from exact history`

本 review 不把 1–3 标为已执行。

## Verdict

**APPROVED。**

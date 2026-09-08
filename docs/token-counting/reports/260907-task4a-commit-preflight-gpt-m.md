# Task 4A source commit preflight

## Scope and source commit

在隔离 worktree `/home/xp/.claude/jobs/4f9bdf9a/tmp/task4a-prediction`、branch `integration/task4a-prediction` 完成。提交前 base 是 `6044919a4b9a9fd2ea06f60fe5331536fd64b0f5`，提交是 `7d7e43b32c1d90e1723e6ad469262c5617e670a5`，parent 精确为该 base，subject 是 `feat: predict tokens from exact history`。`git merge-base --is-ancestor 6044919a... HEAD` 成功。

用户已提供独立 source review verdict：`APPROVED`，0 blocker/major/minor。此执行没有自行重做 source review，也没有 push、squash、merge shared main 或操作 4141。

提交范围由 `git diff-tree --no-commit-id --name-status -r HEAD` 和 `git diff --name-status 6044919a..HEAD` 双重确认，均严格为：

```text
A	src/app/tokenization/prediction.py
M	src/app/tokenization/scaling.py
M	tests/unit/tokenization/test_local_estimate_scaling.py
A	tests/unit/tokenization/test_prediction.py
```

提交后 `git status --short` 为空；working/cached `git diff --check` 均为 exit 0。提交前检查也确认四条 source paths 以外无 tracked 或 untracked 改动，且这四条路径没有 `<<<<<<<`、`=======`、`>>>>>>>` conflict marker。

## Commit-before gate

所有命令在上述 worktree、Python `3.14.2` 下重新执行：

| Command | Result |
|---|---|
| `uv run pytest tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py` | `38 passed in 0.63s` |
| `uv run pytest tests/unit/tokenization/` | `574 passed in 146.58s (0:02:26)` |
| `uv run ruff check src/app/tokenization/prediction.py src/app/tokenization/scaling.py tests/unit/tokenization/test_prediction.py tests/unit/tokenization/test_local_estimate_scaling.py` | `All checks passed!` |
| `uv run pyright src tests` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | exit `0` |
| conflict-marker scan over all four paths | `none` |

## Mutation evidence disposition

已重新读取并复核 implementation report [260907-task4a-implementation-gpt-m.md](260907-task4a-implementation-gpt-m.md)：C01–C14 均有直接单变量 mutation、target node raw red output 和 exit status `1`；恢复后用所有相同 selector nodes 的 `22 passed` 运行确认 green。该 evidence 已完整且其 source bytes 在本次 preflight 前未变化，因此没有无理由重复全套破坏性 mutation。

本提交不会把后续 slice 冒充为完成：Task 4B-P learned prefix pairs/full-baseline/current-zero/newest31、Task 4B profile/16/8 policy、Task 4C drift，以及 Task 5/pipeline/store persistence 仍未实现且未由本 gate 验证。

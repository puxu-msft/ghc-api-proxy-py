DONE

Commit：`c59cdd66a008f8ae8248b781a0c74fc36e129287`

Tests：direct regressions 2 passed；action-ID／diagnostic-absence selectors 2 passed；`test_learning_store.py` 369 passed；完整 tokenization 535 passed；Ruff passed；Pyright 0 errors。

## Source fix report

Base：`56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8`

Final：`c59cdd66a008f8ae8248b781a0c74fc36e129287`

Physical worktree：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd`

Branch：`worktree-agent-a2cd3b8776da8ebfd`

Exact changed paths：

```text
src/app/tokenization/types.py
tests/unit/tokenization/test_features.py
tests/unit/tokenization/test_learning_store.py
```

### T3A-SR-01

在 `LearningSnapshot.__post_init__()` 中建立所有 prediction records实际表达的：

```python
(record.sample_key, candidate.candidate_key)
```

集合，并要求 persisted snapshot evaluation keys为该集合的子集。

实现刻意使用 subset，而不是 equality，因此：

- 拒绝同 sample但 record中不存在的 candidate evaluation。
- 不要求每个 record candidate都有 persisted evaluation row。
- Older diagnostic evaluation absence继续合法。

新增直接 DTO regression：构造 cold-only `PredictionRecord`，再加入同 sample的 extra `history-exact/median` evaluation；`LearningSnapshot` constructor必须以“evaluation未引用 prediction record candidate”拒绝。

### T3A-SR-02

在 `TokenLearningObservation.__post_init__()` 集中验证 observation evaluations的 candidate keys唯一。既有 sample-key alignment先确保所有 evaluation属于 observation sample，随后 duplicate candidate key被直接拒绝。

新增 independent raw-row regression：

1. 创建并关闭合法 store。
2. 复制数据库。
3. 读取合法 `learning_events.evaluations_json`。
4. 复制其中一个完整 evaluation entry并追加回 JSON。
5. 重启 store必须返回 `LearningStoreStartupReason.INVALID_STATE`。
6. Startup前后 database bytes完全相等。

该负例经过 event decoder进入 `TokenLearningObservation`，证明 duplicate candidate evaluations不会再被 `_validate_derived_graph` 后续 set comparison静默折叠。

### 验证命令与结果

Direct DTO／raw corruption selectors：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_features.py::test_learning_snapshot_rejects_evaluation_without_record_candidate 'tests/unit/tokenization/test_learning_store.py::test_candidate_key_graph_rejects_independent_raw_corruption[event-evaluation-duplicate]'
```

结果：`2 passed in 1.72s`。

完整 store：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py
```

结果：`369 passed in 87.06s`。

完整 tokenization：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/
```

结果：`535 passed in 149.23s`。

Diagnostic absence与action-ID专项核验：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python -m pytest tests/unit/tokenization/test_learning_store.py::test_confirmed_action_ledger_matches_independent_fixed_contract_literal tests/unit/tokenization/test_learning_store.py::test_newest_128_diagnostics_and_160_record_reconstruction_are_independent
```

结果：`2 passed in 1.79s`。

这证明：

- 108 semantic bases／204 expanded action IDs未改变。
- Newest-128 mandatory diagnostics与older evaluation absence合同仍成立。
- 160-record reconstruction仍不要求 persisted evaluation全集。

Ruff：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/ruff check src/app/tokenization/types.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py
```

结果：`All checks passed!`

Pyright：

```bash
pwd -P
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 56ec5e7e0cf0740a9d7fcd92cac7cb875ef212c8 HEAD
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a2cd3b8776da8ebfd/src /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/pyright src tests --pythonpath /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a90712cc2b7ab2a9c/.venv/bin/python
```

结果：`0 errors, 0 warnings, 0 informations`。

### Commit

Commit message通过 `/tmp/task3a-source-fix-1-commit-message.txt` 传给 `git commit --file`，内容：

```text
fix: validate token prediction evaluation keys
```

使用 exact pathspec提交，没有 amend：

```bash
git commit --file /tmp/task3a-source-fix-1-commit-message.txt -- src/app/tokenization/types.py tests/unit/tokenization/test_features.py tests/unit/tokenization/test_learning_store.py
```

结果：

```text
[worktree-agent-a2cd3b8776da8ebfd c59cdd6] fix: validate token prediction evaluation keys
 3 files changed, 53 insertions(+), 1 deletion(-)
```

Final parent逐字等于 candidate base。Tracked working tree与index干净；仅保留未触碰、未提交的 managed-worktree `.dev` symlink。

Concerns：指定 `.dev` report未写，因为当前 leaf harness明确禁止写 report `.md`；以上为完整 inline fix report。Independent re-review仍由 controller安排。没有修改 authority、brief、shared main、action registry、schema、pipeline或其它 source paths。
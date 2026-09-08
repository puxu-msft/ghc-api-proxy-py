# Task 3B merged-state review（squash onto current main）

## 评审范围

- 被检对象：`/home/xp/.claude/jobs/4f9bdf9a/tmp/task3b-main-integration` 上相对 current main `42fb23299bc9487d1751749668277ac4304861f8` 的 **`git merge --squash integration/token-learning-store` 暂存 candidate**，尚未提交。无 `MERGE_HEAD`，无 unmerged index，工作树与 index 一致。
- `integration/token-learning-store` tip = source-reviewed `e2461a6e`（`feat: persist prefix learning prerequisites`）。旧 base 上的 source review follow-up 已 APPROVED；本轮不重做 3B 完整 gate，只评 squash 后的 **main overlap / 最终 staged 树**。
- merge-base(`42fb232`, `e2461a6e`) = `e4edc6ebebb91427654c8ce86f88b6c9b57bbd08`。
- 判据：`task-3b-brief.md`（allowed/non-goals、不得改 `docs/.human-controlled/`、source review 后须查 current main path overlap）；`spec.md`／`plan.md` 的 3/3A/3B 合同；上一轮 T3B-SR-01～03 的关闭证据。
- 只读：不修改、不提交、不操作 4141／shared main。未跑完整 tokenization gate。

## 总体 verdict

**APPROVED。** blocker=0，major=0，minor=0。自动 squash 无冲突残留；3B 六文件与 `e2461a6e` **byte-identical**；T3B-SR-01～03 在 merged tree 上复现成立；与 main 的真实 overlap 只有 `pyproject.toml`，合并结果保留 main 的 `zstandard` 主依赖并追加 `aiosqlite>=0.22.1`；42fb232 的 routed-upstream count seam **未被 squash 改写**。

## Staged 边界

相对 `42fb232` 暂存 12 路径（整条 Task 3＋3A＋3B 栈，不是 3B-only slice，这是 restack 的正确形状）：

| status | path |
|---|---|
| M | `pyproject.toml` |
| M | `src/app/config/paths.py` |
| M | `src/app/tokenization/estimators.py` |
| M | `src/app/tokenization/features.py` |
| A | `src/app/tokenization/learning_schema.py` |
| A | `src/app/tokenization/learning_store.py` |
| M | `src/app/tokenization/types.py` |
| M | `src/app/tokenization/worker.py` |
| M | `tests/unit/tokenization/test_features.py` |
| A | `tests/unit/tokenization/test_learning_store.py` |
| M | `tests/unit/tokenization/test_local_token_worker.py` |
| M | `tests/unit/tokenization/test_responses_estimator.py` |

- `git ls-files -u` 空；对暂存文件扫描 `<<<<<<<`／`=======`／`>>>>>>>` 无命中。
- **未**暂存 `docs/.human-controlled/`、`count_tokens.py`、`pipeline/driver.py`、config schema、4141 相关文件。

## Path overlap 与 seam

main 自 merge-base 以来，在上述 tokenization／paths 路径上的 **净 diff 只有** `pyproject.toml`（`18c7c690` 把 `zstandard` 挪到主依赖）。`42fb232`（routed upstream count）改的是 `count_tokens.py`／`driver.py`／provider／schema，不在 squash 路径里。

`pyproject.toml` staged vs main：仅在主依赖末尾增加 `"aiosqlite>=0.22.1"`，main 的 `zstandard` 位置保留。相对 `e2461a6e` 的唯一 pyproject 差异也是这处 main-side 安置，不是丢 3B 依赖。

`paths.py` 只追加 `tokenization_learning_path()` → `tokenization-learning.sqlite3`，加法、无改名。

worker／estimators 对 `LocalTokenWorker.estimate(protocol, payload)` 与 `estimate_responses_input(payload)` 保持可调用；`capabilities` 为可选。main `driver.py` 仍是 `chain.local_token_worker.estimate(protocol, context.payload)`。worker 继续从 `app.pipeline.count_tokens` import `CountTokensRequestError`（该类在 42fb232 的 `count_tokens.py` 仍存在）。独立 import smoke：`IMPORT_OK`。

3B 核心六文件及 `estimators.py`／`worker.py`／`paths.py`／worker tests 对 `e2461a6e` 均为 **IDENTICAL**。Task 3／3A 持久化合同随 `e2461a6e` 原样进入 staged tree，没有被 main 侧内容覆盖。

## T3B-SR-01～03 在 merged tree 上的复现

用本树 `src` + 既有 3B worktree 的 interpreter（本树无 `.venv`）探针：

```text
MIXED None [6, None] True True
IMAGE_ONLY_MEDIA False 6
FAILED+DUP ValueError:failed observations require NotCommitted or failure-before-policy
FAILED+BEFORE ACCEPTED
FAILED+NOTCOMMITTED ACCEPTED
ENCODE_PENDING ValueError sample codec requires a positive committed_order
ESTIMATE_INT 6
```

源码锚点仍在：`features.py` `if media_items is None:` 才 discard `MEDIA_REASON`；`types.py` failed 只接受 `NotCommitted`／`FAILURE_BEFORE_POLICY`；`learning_store.py` `_encode_sample` 拒绝 pending order。

## Findings

未发现问题。

## 未验证边界

- 未在本 merged worktree 跑 pytest／Ruff／Pyright（无本地 `.venv`；不把旧 isolation 树的 10 passed 折算过来）。
- 未跑 `tests/int/test_pipeline_app.py` 对 42fb232 routed count 的回归。
- 未启动 4141，未做 live canary。
- Task 3／3A 的 cancellation／schema oracle 全矩阵未在 squash 树上重跑；依据是与 `e2461a6e` 文件恒等，不是新的执行证据。
- `uv.lock` 被 gitignore，本候选不包含 lock；安装是否解析到 `aiosqlite>=0.22.1` 留给 commit 前 `uv sync`。

## Commit 前必须检查

在 **本 isolation worktree** 上、不接管 shared main、不启 4141：

1. `uv sync`（写入 `aiosqlite`）后 `uv run pytest -q tests/unit/tokenization`
2. `uv run ruff check` 与 `uv run pyright` 针对上述 12 个暂存路径
3. `git diff --cached --name-only` 仍恰为这 12 个路径；`git diff --cached --check`
4. 确认 index 无 conflict marker、无 `docs/.human-controlled/`
5. 提交信息按 stacked integration 语义（3＋3A＋3B），不要写成「只含 3B」

本 review 不把 1–2 标为已执行。

## Verdict

**APPROVED。**

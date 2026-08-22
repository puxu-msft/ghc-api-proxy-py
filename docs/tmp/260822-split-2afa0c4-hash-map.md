# 主仓 `2afa0c4` 拆分：新旧哈希对照

**日期**：2026-08-22。**动作**：把 `2afa0c4`「refactor: make the delivery loop ask which client it is answering」拆成两条提交——它把 `docs/.human-controlled/` 那 14 个文件和 CLAUDE.md 的指向改动一起卷了进去，而提交信息只讲了 delivery 那件事。

拆分后 `main` 上这段历史的哈希全部变了。内容一字未动：改写后的 tree 与改写前的 `30f251c^{tree}` 精确相等（`a37a14f6`），`git diff` 旧新两端为空。

旧历史保留在分支 `a/2026-08-22-split-2afa0c4`（指向旧的 `30f251c`），不要删除——评审报告与过程记录里的旧哈希只有它还能解析。

## 对照表

| 旧 | 新 | 提交 |
|---|---|---|
| —— | `bbf5f50` | docs: put the user-controlled requirement documents in the repository（**新增的那一半**） |
| `2afa0c4` | `36e303d` | refactor: make the delivery loop ask which client it is answering（原信息不变，只剩代码那一半） |
| `8ce22b9` | `13bc1c3` | test: make the keep-alive test check the thing its comment claimed |
| `027698f` | `2e17663` | fix: say which clock a finished turn loses to, and pin it |
| `25432d4` | `bfdc6aa` | docs: point the deadline comment at a branch that exists |
| `30f251c` | `53dd99c` | refactor: say synthetic what, and stop naming the module after its only occupant |

后四条是原样重放：tree、提交信息、author 与 committer 六个字段逐对相同，只有父提交变了，`git range-diff` 全部标 `=`。

## 引用处置

- **活文档已重指**：`docs/client-leg-formats/deferred.md`（U-3、U-4、D-5、D-6、n-2、n-5 六处）、`docs/upstream/retry-and-continuation/deferred.md`（第 132 行）。
- **过程记录有意不回填**：`docs/tmp/260822-review-session-closeout.md`、`docs/upstream/retry-and-continuation/reports/260822-review-mcp-contract-and-deadline-order.md`、`.../260822-review-mcp-contract-disposition.md`。它们记的是写作当时看到的仓库状态，回填会把「当时看到的」改写成「现在看到的」，那份验收记录就不再能当证据用。要解析里面的旧哈希，走上面的对照表或那条保留分支。

## 波及面

改写时 `main` 上的两个活跃 worktree 分支（`proxy-priority-on-httpx2`、`fix/upstream-error-events`）都**不**包含 `2afa0c4`，没有分支被这次改写孤立。`origin/main` 停在 `44fa576`，这段历史从未发布。

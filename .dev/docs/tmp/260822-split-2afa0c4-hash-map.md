# 主仓 `2afa0c4` 拆分：新旧哈希对照

**日期**：2026-08-22。**动作**：把 `2afa0c4`「refactor: make the delivery loop ask which client it is answering」拆成两条提交——它把 `docs/.human-controlled/` 那 14 个文件和 CLAUDE.md 的指向改动一起卷了进去，而提交信息只讲了 delivery 那件事。

拆分后 `main` 上这段历史的哈希全部变了。内容一字未动：改写后的 tree 与改写前的 `30f251c^{tree}` 精确相等（`a37a14f6`），`git diff` 旧新两端为空。**拆分点本身也核过**：`tree(800eb5b) == tree(2afa0c4) == 10b57f25`——这比只比 tip 强，它排除了「两半各自漏一点、在后续提交里互相补回来」这种 tip 比对看不出来的失手。

旧历史保留在分支 `a/2026-08-22-split-2afa0c4`（指向旧的 `30f251c`），不要删除——评审报告与过程记录里的旧哈希只有它还能解析。

## 对照表

| 旧 | 新 | 提交 |
|---|---|---|
| —— | `fa0b281` | docs: put the user-controlled requirement documents in the repository（**新增的那一半**） |
| `2afa0c4` | `800eb5b` | refactor: make the delivery loop ask which client it is answering（原信息一字未动，只剩代码那一半） |
| `8ce22b9` | `57d5b0e` | test: make the keep-alive test check the thing its comment claimed |
| `027698f` | `08f3c29` | fix: say which clock a finished turn loses to, and pin it |
| `25432d4` | `7904a2a` | docs: point the deadline comment at a branch that exists |
| `30f251c` | `1c91870` | refactor: say synthetic what, and stop naming the module after its only occupant |

后四条是原样重放：tree、提交信息、author 与 committer 六个字段逐对相同，只有父提交变了，`git range-diff` 全部标 `=`。

⚠️ **本仓（`.dev`）的提交 `fea4e4a` 里写的是一组中间哈希**（`bbf5f50` / `36e303d` / `13bc1c3` / `2e17663` / `bfdc6aa` / `53dd99c`），那一轮因独立评审指出 docs 提交信息里一处时序断言不成立而被重做，已被上表取代。中间那组哈希只存在于 reflog，不要用。

## 引用处置

- **活文档已重指**：`docs/client-leg-formats/deferred.md`（U-3、U-4、D-5、D-6、n-2、n-5 六处）、`docs/upstream/retry-and-continuation/deferred.md`（第 132 行）。
- **过程记录有意不回填**：`docs/tmp/260822-review-session-closeout.md`、`docs/upstream/retry-and-continuation/reports/260822-review-mcp-contract-and-deadline-order.md`、`.../260822-review-mcp-contract-disposition.md`。它们里的旧哈希**全部是「某时刻的主仓 HEAD」**这一种用法，回填会断言一件物理上不可能的事——`08f3c29` 在那些记录写下的时刻根本不存在。所以这里不回填不只是「过程记录一般不动」的惯例，而是唯一为真的选择。要解析里面的旧哈希，走上面的对照表或那条保留分支。

## 波及面

改写时 `main` 上的两个活跃 worktree **分支**（`proxy-priority-on-httpx2`、`fix/upstream-error-events`）都不包含 `2afa0c4`，没有分支被这次改写孤立。另有第三个 worktree `/home/xp/.claude/jobs/826d4cda/tmp/review` 是 detached HEAD（`7839b02`，2026-08-18），停在改写点之下，同样不受影响。`origin/main` 停在 `44fa576`，这段历史从未发布。

⚠️ **`docs/.human-controlled/` 自 `fa0b281` 起才受版本控制，这给旧分支的整合加了一层新后果**：`fix/upstream-error-events`（`fd6b591`）的树是迁移前的旧 `docs/`（106 个文件，`docs/agents/` + `docs/tmp/`，没有 `.human-controlled/`）。按「squash 取它的树」整合它，除了 `.claude/rules/00-development-workflow.md:39` 已经警告过的「静默带回 `docs/tmp/` 与 `docs/agents/`」，现在还会**同时删掉这 14 份用户亲笔文档**，无冲突、无报错。那条规则既有的收尾检查（「整合后确认 `docs/` 只剩 `.human-controlled/`」）恰好也能击发这一种，**不需要加新机制**。

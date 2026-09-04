# `integration/dotdev-remote-260904` peer-report merge candidate 评审

日期：2026-09-04。

评审对象：merge commit `f491f52c24b51003926abd2ef7e8c5aedcf46536`、frozen remote first parent `c3601f62836c411bc9f4d9e375f4697e07b8753f` 与 peer exact-path second parent `0e642400d6629fd4a83831eea683de8b949cfc60`。范围严格限于 `/home/xp/src/ghc-api-proxy-py/.dev/.git` objects／refs／index；全程只读，没有写文件、暂存、提交、fetch 或 push。

方法：直接解析 loose／packed commit、tree、blob objects 与 refs；对三个 commit 做全树 path／mode／OID 比较，并遍历 ancestry。没有用工作树文件替代提交态事实。

## Verdict

**pass。** 0 blocker、0 major。C1～C6 全部通过；未发现整改引入的其它 blocker／major。

## C1～C6 逐项核验

### C1　PASS

`f491f52c…` 的 commit object 有且仅有两个 parent，顺序精确为：第一父 `c3601f62836c411bc9f4d9e375f4697e07b8753f`，第二父 `0e642400d6629fd4a83831eea683de8b949cfc60`。完整 ancestor traversal 对两者均返回 true；两者同时也是直接父，不只是间接可达。

当前 refs 与被评身份一致：`refs/remotes/origin/dotdev = c3601f62836c411bc9f4d9e375f4697e07b8753f`，`refs/heads/dotdev = 0e642400d6629fd4a83831eea683de8b949cfc60`，`refs/heads/integration/dotdev-remote-260904 = f491f52c24b51003926abd2ef7e8c5aedcf46536`。

### C2　PASS

Merge root tree OID 为 `c2473424f1e87f048591d7d99684ef9ff311404d`。根 entries 恰好一项：mode `40000`、name `.dev`、subtree `b7d391acaa685ddb244f64470bc6dbbecaf07648`。没有根 `docs`、没有第二个 root。

### C3　PASS

Second parent `0e642400…` 的 root tree OID 精确为 `b7d391acaa685ddb244f64470bc6dbbecaf07648`，与 merge commit 的 `:.dev` subtree OID 完全相等。因此 merge 内 `.dev/` 是 second parent 整树的结构性复用，不是逐文件近似复制。

相对 first parent 的完整 tree delta 恰为 12 个 `A`，全部位于 `.dev/docs/direct-passthrough/reports/`。每一项去掉 `.dev/` 前缀后，与 second parent 对应路径的 mode／blob OID 完全一致，`delta_vs_second_bad=0`。Second parent 相对自己的父 `ab621846…` 也恰为同 12 个 `A`，两组 normalized delta 逐项相等。

Merge tree 共 1181 个文件；`merge_has_dev_dev=false`、`merge_root_docs=false`。没有 `.dev/.dev`，没有遗留根 `docs`。

### C4　PASS

First-parent→merge 的 12 条 delta 是下列报告原件，除此之外没有任何 local delta：

- `260903-completed-client-actions-spec-review-gpt-opus-round2.md`～`round6.md`，5 份；
- `260904-completed-client-actions-plan-review-gpt-opus.md` 与 `round2.md`，2 份；
- `260904-completed-client-actions-implementation-review-general-opus.md` 与 `round2.md`，2 份；
- `260904-completed-client-actions-closeout-docs-review-general-opus.md`，1 份；
- `260904-completed-client-actions-final-closeout-review-general-opus.md` 与 `round2.md`，2 份。

全 12 份 mode 均为 `100644`，blob OID 与 second parent exact。Delta 中 living-doc path 数为 0；没有 Spec、plan、deferred、README、status、source、tests、human-controlled 或其它 local/main WIP。

### C5　PASS

当前 remote ref 仍为 frozen first parent `c3601f62836c411bc9f4d9e375f4697e07b8753f`，而它是 candidate 的直接第一父。因此 `f491f52c…` 是当前 remote tip 的 fast-forward descendant，普通非强制 push 足够。若 push 前 remote ref 移动，本结论随条件失效，必须重新比较并构造新 descendant；不得 force push。

### C6　PASS

十二个新增 path 全部在项目定义的 `reports/` 原件目录，文件名逐份标识 reviewer、round 或 closeout review；first-parent tree 的所有 living docs 保持同一 mode／blob。故本提交只归档 peer 报告原件，不修改任何 living authority，也不把报告 verdict 投影成 current status。

## 主动检查

- Parent order、root set、subtree identity、delta 路径、mode／blob 与 ancestry 均来自 commit objects直接核验。
- Remote first-parent history和peer second-parent history都由merge commit直接可达，没有squash或丢弃任一侧历史。
- Merge全树对`.dev/src/`、`.dev/tests/`、`.dev/docs/.human-controlled/`的命中为0；本次12项delta也全部是reports。
- Commit message：second parent为`docs: archive contextual status review reports`，内容正是12份报告；merge为`docs: merge dotdev histories`，对象确是双父history merge。未发现message/content不符。

## 未采纳建议

无。候选已满足exact-path、history、tree与fast-forward边界；不需要改写commit、移动报告、触碰living docs、force push或增加额外proof framework。

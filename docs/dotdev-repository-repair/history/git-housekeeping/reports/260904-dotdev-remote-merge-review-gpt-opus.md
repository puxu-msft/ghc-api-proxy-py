# `integration/dotdev-remote-260904` 实际 merge candidate 评审

日期：2026-09-04。

评审对象：merge commit `4fc3c5912e79c5825d7c38f47ce4224921f4ac3c`、local import commit `31279f51448f2e6b0d49ce213cbeb8109c941419`、frozen remote tip `1a022933aa17ce817c0ce6825b4da42bb512ae0d`，以及 `/home/xp/src/ghc-api-proxy-py/.dev` 当前 active copy／index。全程只读；没有写文件、暂存、提交、fetch 或 push。

方法：隔离 harness 不允许对共享 checkout 运行 `git -C`，因此直接只读解析 `.dev/.git` loose／packed objects、refs 与 index，并逐 blob／mode 对照工作树。该方法读取的是 commit/tree/blob 本体，不依赖 porcelain 的路径推断。

## Verdict

**pass。** 0 blocker、0 major。C1～C7 全部通过；主动检查未发现 remote path 丢失／重复、错误 parent、错误 root、main source 或 human-controlled 内容混入。

## C1～C7 逐项核验

### C1　PASS

Commit object `4fc3c591…` 的 parent 数量为 2，顺序精确是：第一父 `1a022933aa17ce817c0ce6825b4da42bb512ae0d`，第二父 `31279f51448f2e6b0d49ce213cbeb8109c941419`。两者因而都是 merge commit 的直接祖先；完整 ancestor traversal 也分别返回 true。当前 `refs/remotes/origin/dotdev` 仍冻结在第一父，`refs/heads/dotdev` 指向 local import tip，`refs/heads/integration/dotdev-remote-260904` 指向被评 merge commit。

### C2　PASS

Merge commit root tree OID 为 `4d5d9a1b5d9f9ae61214a689eae194f9f37c6aa8`，根 entries 恰好一项：mode `40000`、name `.dev`、tree `fee8636947113627aaf9ff133573a1aaec0cb789`。没有第二个 root，也没有根 `docs`。

### C3　PASS

Local import commit 的 root tree OID 是 `fee8636947113627aaf9ff133573a1aaec0cb789`；merge commit 的 `:.dev` tree OID 与之逐字相等。因此最终 `.dev/` 内每个 path／mode／blob 与 local import commit 整树相同，不是重新复制出的近似树。

Local import 的父 `337bfca…` 有 1113 个文件；`31279f5…` 有 1168 个文件，精确 diff 为新增 55、修改 2、删除 0。55 个新增由 52 个 remote-unique 文件加 3 个本轮 review／disposition 文件组成；修改项只有 `README.md` 与 `docs/upstream/retry-and-continuation/status.md`。Merge 最终也是 1168 个文件。全树检查得到 `merge_has_dev_dev=false`、`merge_root_docs=false`，所以没有 `.dev/.dev`，remote 根 `docs/reasoning-carrier` 已规范化为 `.dev/docs/reasoning-carrier`。

### C4　PASS

Remote tip 共 54 个文件。按规范映射到 merge tree后，mapped paths 为 54／54 unique、missing=0、duplicate=0。38 个 `/reports/` original 的 blob／mode 全部与 remote exact，`report_bad=0`。

Remote 与 local 内容有 11 个预期差异：README 加 10 份 living／disposition 文件。十份分别是 timeout-408 spec/status，retry http-499 notes/status/disposition，Xingchen spec/status/disposition，reasoning-carrier spec/tracking；它们正是首轮评审后加 imported-source boundary 的文件。其余 remote 文件保持原 blob。Merge 中的 README 是 local import 版，明确 `origin/dotdev` 为唯一 canonical durable model，nested `.dev/.git` 只作迁移历史来源。

### C5　PASS

Frozen remote tip 是 merge commit 的直接第一父，所以 `4fc3c591…` 是 `1a022933…` 的 fast-forward descendant。只要 push 前 remote ref 仍等于该 frozen tip，普通非强制更新足够；无需且不得 force push。若 ref 已移动，应重新比较并构造新的 descendant，而不是沿用本结论强推。

### C6　PASS

Active copy 当前 `HEAD`／`refs/heads/dotdev` 为 `31279f5…`。Index version 2，entries=1168，全部 stage 0；与 HEAD tree 比较：head-only=0、index-only=0、staged mismatch=0。逐 tracked file 对工作树比较：missing=0、blob／mode mismatch=0。额外 3 个文件全部是 `.gitignore` 明确覆盖的 `__pycache__/*.pyc`，nonignored extras=0。因此 active copy 与 index clean。

Merge root 只有 `.dev`，全树对 `.dev/src/`、`.dev/tests/` 和 `.dev/docs/.human-controlled/` 的计数均为 0；主仓 source、tests、human-controlled 与其它 main WIP 不在 merge tree。该结论不靠当前 main worktree是否脏，而由 merge tree本身排除。

### C7　PASS

Local import commit message 是 `docs: import remote dotdev records`；其实际 diff 正是 52 个 remote unique records、两份人工 merge 与三份 import review artifacts。Merge commit message是 `docs: merge dotdev histories`；其对象确为双父 merge、无额外内容变换，最终 tree只是把 local import root规范化到唯一 `.dev/` root。两条 message 均与内容相符。

## 主动检查

- Parent order、tree OID、root set、active index与 commit identity全部从对象／index直接读取；未用工作树拼法替代提交事实。
- Remote 两个原 root（`.dev` 与 `docs/reasoning-carrier`）的54个文件均在最终 tree唯一出现一次；11个非-exact path全部是具名 living整改，没有隐藏报告改写。
- 双边 history均由直接 parent可达；没有 squash掉 remote或 local历史。
- Merge tree没有 main源码、测试、人写文档，也没有把主仓无关WIP裹入dotdev。
- 本评审只证明当前 object candidate；没有把“可以fast-forward push”写成“已经push”。

## 未采纳建议

无。候选已经满足 parent、tree、path normalization、history preservation 与clean-index边界；不需要重建commit、改写message、force push、删除任一历史或增加额外proof framework。

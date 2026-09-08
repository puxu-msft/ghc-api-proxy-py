# `origin/dotdev` 内容导入候选评审

日期：2026-09-04。

评审对象：`/home/xp/src/ghc-api-proxy-py/.dev` 当前导入候选、远端 tip `refs/remotes/origin/dotdev = 1a022933aa17ce817c0ce6825b4da42bb512ae0d`，以及当前主仓行为／人写 authority。全程只读；没有写文件、暂存、提交、fetch 或 push。

方法边界：隔离 harness 不允许对共享 checkout 运行 `git -C`，因此用只读 Git object/index 解析直接读取 remote/local commit、tree、blob 与 mode；当前主仓状态以 `/home/xp/src/ghc-api-proxy-py/.git/refs/heads/main`、工作树源码及 `docs/.human-controlled/` 为准。结论绑定本次观测时点；共享 ref 后续若移动，应重核受影响状态。

## Verdict

**needs-fix。** 发现 3 条：blocker 1、major 2。C1、C2、C4、C6、C7 通过；C3、C5 不通过。

## Blocker／Major findings

### F-01　[blocker] HTTP 499 living 状态与当前最高 authority、实现同时冲突
- `.dev/docs/upstream/retry-and-continuation/status.md:4-8`、`http-499-retry.md:2-5,18-30` 与 `review-disposition.md:291-299` 把 499 requirement、实现和用户审核写成 current／complete。
- 当前人写 authority `docs/.human-controlled/upstream-retry-and-continuation.md:13-18` 的可继续列表没有 499；当前实现 `src/app/model_provider/ghc_client/errors.py:31-35` 的 `RETRYABLE_STATUSES` 也不含 499。
- 复核时主仓 `main` 为 `bb5783f17f8f21017010a14d00b762b49ee6cc13`；远端文档所称 requirement／source commit 没随本次 dotdev 导入进入该主仓。因此 C3 所要求的三方一致不存在。
- 合入会让 living status 反向覆盖人写 authority并宣称尚不存在的行为。须先由用户／主会话恢复准确的人写提交并集成对应 source history，或把这些文件明确降格为另一 clone 的点时快照而非本仓 current 状态；本评审不授权修改 human-controlled 文档。

### F-02　[major] timeout-408 与 Xingchen 的 living status 把另一份 main 的 PASS 冒充当前 main
- `docs/timeout-408/status.md:2,18-38` 声称 disconnect fix 已进 main；但当前 `src/app/server/routes/inference.py:96-99,135-145` 仍在读完 body 后直接 await `_dispatch`，全 `src/`／`tests/` 对 `finish_async_cleanup` 与该 disconnect listener 无命中。
- `docs/xingchen/status.md:8-23,38-46` 与 `review-disposition.md:38-44` 声称 `main=0cd1641…`、archive `2ed92c5…` 已装位；当前 `src/`／`tests/` 对 Xingchen／TeleAgent／gateway fields 为 0 命中，两个引用 commit 在当前主仓 object store 也不存在。
- 报告 originals 的 PASS 可以保留，但这两份根目录 status 是 current carrier。须在导入前标明它们属于外部 clone／尚待 source-history 导入，或先让对应 reviewed source 与 archive 在当前主仓可达；否则 C5 不成立。

### F-03　[major] reasoning-carrier 的 living tracking 指向不可达的唯一实现位置
- `docs/reasoning-carrier/tracking.md:2-7,38-44` 声称候选保存在 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2` 与 `worktree/reasoning-carrier-v2`，并要求在该处用 `git rev-parse HEAD` 重定位；本次检查该 worktree 与 branch ref 均不存在。
- 原 closeout 报告 `reports/260904-closeout-review-general-opus-1.md:30-35` 明确当时只有该本地 branch 含候选，并刻意没有在 living docs 留 commit token；dotdev 远端只带文档，不能据此恢复 source candidate。
- 路径归入 `docs/reasoning-carrier/` 本身合理，但当前 tracking 作为 living 状态已失去可执行定位。须导入／归档对应 source ref，或把 tracking 改成带 exact commit 与真实可达位置的跨 clone handoff；不能用评审 PASS 代替候选可达性。

## C1～C7 逐项核验

### C1　PASS

只读解析 remote tip 得到 54 个文件，根为 `.dev/` 与 `docs/reasoning-carrier/`。按候选映射规则去掉 `.dev/` 前缀、保留 remote 根 reasoning-carrier 的 topic 路径后，与 local tip `337bfca78d12777ffa97436536f1db867323e7a0` 比较：共同路径恰为 `README.md` 与 `docs/upstream/retry-and-continuation/status.md` 两个；其余 52 个路径均不在 local commit tree。当前 active copy 对这 52 个文件 `missing=0`、blob mismatch=0、mode mismatch=0；映射后无路径碰撞。两共同文件是具名人工 merge，而非静默覆盖。

这支持“52 份 remote unique 文件全部可达、未覆写 local tracked file”。对导入前未被 Git 记录的瞬时 untracked 字节，本次事后树比较不能单独重建，但协调者提供的导入时 no-conflict 检查与当前 52/52 exact blob 对账一致，没有出现反证。

### C2　PASS

当前 `.dev/README.md:6-10` 忠实记录 2026-09-04 用户选择 dedicated orphan `origin/dotdev`，明确它取代 nested repo 的最终存储模型，并把现存 `.dev/.git` 限定为迁移前历史来源；`:18-20` 规定 exact-path sync、先判 active side、不得 bulk-copy／覆盖 peer WIP、无当前明确授权不 push 且禁止 force push；`:22-26` 规定专用 worktree 恢复，不切共享 main、不整树覆盖。`:28-81` 保留原布局、规则和主题入口。文本只有一个 canonical remote model，没有把迁移来源称为第二个 current authority。

### C3　FAIL

Current `status.md` 确实以 `:10-297` 保留 local broad route／history，并在 `:4-8` 接入 remote HTTP 499 完成摘要；remote `http-499-retry.md` 与 `review-disposition.md` 彼此一致。但 F-01 证明这些 current assertions 与本次 checkout 的人写 requirement 和实现均冲突，故三方一致性断言失败。

### C4　PASS（路径层）

Remote 根 `docs/reasoning-carrier/**` 被归入 active `docs/reasoning-carrier/**`，其余 timeout-408／xingchen 文件按原 `.dev/docs/<topic>/` 去前缀，两个候选进入 `human-controlled-docs-candidates/`。根 README `:69-73` 具名索引 reasoning-carrier、timeout-408、xingchen；候选文档各自在标题和开头明确“候选、非 human authority”。入口与归属合理。F-02／F-03 指向的是 living 状态真实性／可达 source，不否定目录归属本身。

### C5　FAIL

Remote tree 没有导入或修改 `docs/.human-controlled/**`，候选也明确不授权 agent 修改它；这一半通过。但 F-01、F-02、F-03 说明多份 root status／tracking 把另一 clone 的 requirement、main commit、worktree／branch 状态写成当前事实。报告 originals 可以保留 PASS，living carrier 不能据此宣告本 checkout 已实现或可恢复，故整体不通过。

### C6　PASS

对以下 11 个新增入口／living docs 做相对链接存在性检查：根 README；timeout-408 spec/status；retry `http-499-retry.md`/status；xingchen spec/status；reasoning-carrier spec/tracking；两份 human-controlled candidate。结果为 `docs=11 links=12 missing=0`。该证据只支持这 11 个入口的相对链接可达；没有外推为 archived/report originals 全部链接仍指向 current paths。

### C7　PASS（计划层）

现有两历史无共同祖先时，以 remote tip 为第一父、local tip 为第二父并显式构造最终 tree，是保留双方 commit DAG 的正确形态；remote 第一父使最终提交成为 `origin/dotdev` 的 fast-forward descendant，无需 force push。把 local root 映射到 `.dev/`，并将 remote 根 `docs/reasoning-carrier/` 收进最终 `.dev/docs/reasoning-carrier/`，可使最终 tree 只含 `.dev/`，与 README `:8-10` 的 canonical layout 一致。该判断只验计划形态；实际提交后仍须核 parents、最终 root、54 个 imported paths 与 push ref，不能把计划冒充已执行。

## 主动检查结论

- Remote tip 自身有 `.dev/` 与根 `docs/` 两个 root，而其 README 说 canonical tree 只含 `.dev/`；候选没有隐瞒该事实，C7 的 normalization 正是在修这一过渡态。
- README 的 storage authority、同步、恢复与不强推边界没有互相冲突；本地 nested history 被写成 migration source，不是新的 canonical store。
- 主要 authority 冲突与 stale mutable status 已由 F-01～F-03 覆盖；未发现第四条独立 blocker／major。

## 未采纳建议

- 未采纳“因为 remote 报告已 PASS 就直接把全部 living status 当 current”：报告只证明其原候选／原 clone，不能替当前 main 与 human authority。
- 未采纳“为让导入通过而直接编辑 `docs/.human-controlled/`”：该目录由用户控制；应恢复用户亲自作出的确切提交或请用户裁决。
- 未采纳 force-push、以 local tree 覆盖 remote、删除任一侧历史或改写报告 originals；这些都不需要，也违反既定存储／历史边界。

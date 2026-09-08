# `coordinating-a-shared-git-worktree` carrier trade-off 独立评审

日期：2026-08-22

待审文件：`/home/xp/.claude/my/skills/skills/coordinating-a-shared-git-worktree/SKILL.md`

评审范围：新增的第 117–153 行、它们与既有正文和 `reference.md` 的对账、实际加载面、命名与交叉引用，以及一次性 Git fixture 中的可执行验证。`evolving-skills` 已加载；运行时没有 `my-skills:as-reviewer`，故按请求跳过。

## 结论

**Verdict：needs-fix。** 概念归属正确，实测也支持 CAS、hooks 与“工作树缺少已提交 hunk 时会被下一次同路径 pathspec commit 静默回退”这三个核心命题；但当前文件根本没有进入运行时召回面，新增 worktree 配方还遗漏了共享 index realign，并把可能失败的 cleanup 放在 CAS 之后直接传播失败。两项都会让这份文本无法按现状成为可用的 user-level skill。

证据权重：下述 blocker 与三个 major 均由当前运行时清单、精确配置、原始 transcript 命令或一次性 Git fixture 直接支持，强到足以据此修改；minor 是从同一会话三个样本推出跨场景措辞的范围判断，足以要求收窄措辞，但不能支持“冲突通常都在几分钟内消失”这一更强结论。

## 分级发现

### BLOCKER — 文件不在任何当前生效的 skill 加载面，反向召回必然失败

处在“我要提交，文件混着同伴改动”这一时刻的读者，会按 description 检索共享 worktree、同文件混合改动或只提交自己的内容；从问题域看，他应当召回 `coordinating-a-shared-git-worktree`，因此**概念归属正确**，不应搬去只管“开工前隔离”的 `isolating-from-a-shared-git-worktree`。

但当前物理归属无效。目标目录不在 `/home/xp/.claude/skills/` 的直接扫描根下；`/home/xp/.claude/my/skills/.claude-plugin/plugin.json` 声明插件名为 `my-skills`，本地 marketplace 也注册为 `my-skills`，而 `/home/xp/.claude/settings.json` 启用的是不存在的 `skills@my-marketplace`。`installed_plugins.json` 没有 `my-skills@my-marketplace`，只有已失去 install path 的旧 `git-preference@my-marketplace` 记录；本轮运行时给出的 available-skills 清单也没有该 skill。故这不是“可能没加载”，而是本轮已观察到没有加载。

影响：新增内容等于不存在；`my-skills:coordinating-a-shared-git-worktree`、`git-preference:coordinating-a-shared-git-worktree` 与无 namespace 三种活引用同时存在，至少前两种不可能都由当前状态解析。

要求：先由用户裁定一个 canonical 发布面，再修复注册与所有活引用。我的偏好是沿当前源目录和 user rule 已使用的命名，真正注册并启用 `my-skills@my-marketplace`，然后把活的 `git-preference:`／无 namespace 引用统一到 `my-skills:`；若用户决定恢复 `git-preference` 插件，也可反向迁移，但不能继续让源目录、settings、installed registry 与引用各说一种名字。按 `evolving-skills`，这是归属层级／发布面变更，评审者不自行移动。

### MAJOR — worktree carrier 在 CAS 后没有 realign 共享 index，因此并未“做同样的工作”

新增配方在 detached worktree 中正常提交并用 CAS 移动共享 branch ref，这一核心成立；但 ref 移动不会更新原共享 worktree 的 index。一次性 fixture `/tmp/skill-carrier-review.Uq21SD/worktree-carrier` 中，CAS 后主树的 index blob 仍是 `$OLD`，`HEAD` 已是 `$NEW`，`git status --short -- shared.txt` 为 `M  shared.txt`，也就是 index 正携带一份已提交 hunk 的 staged inverse。按第 145 行只把同样编辑写回主树后，状态变成 `MM shared.txt`，`git diff -- shared.txt` 仍显示作者自己的 `+mine`，不可能满足“只显示 peer hunks”的检查。

这与既有 private-index 配方第 95–102 行的 conditional index realign 不是小差异。新增第 147 行声称“一层 realign index，一层 realign worktree”，但新 worktree carrier 自己根本没有执行前一层。后续 bare commit 可以把 stale index 中的 inverse 提交出去；即使所有人严格走 pathspec，状态和 cached-set 判定也会被这个 phantom staged diff 污染。

要求：worktree carrier 也必须在 CAS 后按 changed path 逐项、且仅在共享 index entry 仍等于 `$OLD` baseline 时 realign 到 `$NEW`；若要支持实测段落所说的七个文件，就不能照搬只处理一个 `$P` 的代码而假装完成。失败发生在 CAS 之后，必须报告“commit 已落地、仅 realign 失败”，不得让调用者重建。完成这层之前，不应把它称为 private-index carrier 的等价替代。

### MAJOR — CAS 已成功后让 `git worktree remove` 的失败原样退出，会把“已提交”伪装成“未提交”

新增代码的最后一条命令是 `GIT_DISCIPLINE_OK=1 git worktree remove --force "$W"`。它位于 CAS 之后，却没有像既有第 111 行要求的那样把 post-CAS housekeeping failure 与 CAS refusal 区分开。

一次性 fixture `/tmp/skill-worktree-cleanup-review.CekhQ3` 先锁住 throwaway worktree，再照配方执行：CAS 成功，branch 已等于 `$NEW`；随后单 `--force` 的 remove 返回 128，报“cannot remove a locked working tree”，worktree 仍注册。整个块因此以非零结束，但 commit 已经落地。按前文对 CAS refusal 的指导重建，会重复提交。

要求：把 cleanup 明确写成 best-effort post-land housekeeping，失败时输出 `$NEW` 已落地以及遗留 `$W` 的精确路径，并返回成功或使用不会与 CAS refusal 混淆的显式状态。不能仅改成双 `--force`，因为锁只是证明该 failure shape 可达的一个正样本，不是唯一可能失败的原因。

### MAJOR — “从未落盘／Rung 2 和 3 都缺工作树内容”是错误的全称，并与既有正文和 reference 矛盾

第 119 行称 private-index blob“assembled in memory”且“never existed on disk anywhere”，但既有配方第 70–80 行明确把完整内容写入磁盘文件 `$D/mine`，再由 `git hash-object -w` 写入 object store。已验证为真的命题是：`commit-tree` 不会自动让 hooks 或 tests 针对一个 checked-out tree 运行；不是“字节从未在磁盘出现”。

第 143 行又称 filtered-patch 与 private index 都不把作者改动放到工作树，并把“共享工作树缺作者 hunk”写成 Rung 2／3 的普遍终态。它只在作者从 baseline 另行构造 patch／blob、而没有先在共享工作树编辑同一 hunk时成立。既有 `reference.md` 第 208 行已经把 Rung 2 写成这个条件式；第 293 行则明确描述 private-index 的常见终态是工作树本来就含作者与 peer 两边的 hunk，提交后只比 `HEAD` 多 peer hunk。新增文本与后者直接矛盾。

一次性 fixture 确认了**条件式命题**：`/tmp/skill-carrier-review.Uq21SD/rung2-revert` 与 `rung3-revert` 都先让 commit 拥有 `mine`、让共享工作树只拥有 peer edit，再用同一路径的 rung-1 pathspec commit；两者最终均为 `rung*_mine_survives=no`，无冲突、无错误。它没有、也不能证明“每次 Rung 2／3 都会留下这种终态”。

要求：改成显式条件句，例如“如果你的 hunk 只存在于 cached patch／private content tree，而共享 worktree 从未含它”；检查也应先判定 shared worktree 是否真的缺该 hunk。把“下一次 pathspec commit”收窄为“下一次包含该路径的 pathspec commit”。Rung 2 的主正文可保留这一高价值判据，但应链接 `reference.md` 已有的完整条件和 `git apply <patch>` 修法，而不是另写一条更强、与 reference 冲突的规则。

### MINOR — “peer 的 uncommitted state has a short half-life”把一次会话的三个样本写成了普遍属性

第 151 行的三个碰撞、两次提前搭好 Rung 3、一整次 worktree／gate／CAS 白做，确实直接支持一个低成本做法：动手前重读一次当前 diff。它不是流水账，也不含项目专有信息。

但三个样本全在同一会话，不能支持加粗前句把 peer state 的“short half-life”写成跨项目属性。保留日期与样本作为“凭什么”的一句实证，同时把判据写成条件式即可，例如“peer state may disappear quickly enough that a cheap re-read pays for itself”。

## 对 `evolving-skills` 各项问题的裁定

### 1. 归属与反向召回

语义 home 正确：这是“已在共享树发生 mixed-file collision 后，怎样只提交自己的 change”这一问题，触发时刻属于 §1 commit ladder；§2 是“开工前怎样让整个 session 隔离”，触发时刻不同。新增 throwaway worktree 是一次提交的 carrier，不是长期 session isolation，所以不是重复 §2。建议在新节首句加一个到 §2 的边界句，但不应搬家。

物理 home 当前错误：死文件不能算 home。修复 blocker 后，才能说“内容写在这里”成立。

### 2. `rewriting-drops-coverage-silently` 双向对账

“本轮只是新增、未改既有段落”按实际编辑动作属实。主会话 transcript 的原始 Bash tool input 显示，第一次写入把唯一 anchor `⚠️ **No rung covers ...**` 精确替换为 `addition + anchor`；随后两次替换只把刚新增的 `Rung 3b` 标题改名，并把新增段里的 `Prefer 3b` 改成 `Prefer the worktree`。没有既有段落被这三次操作改写。

但目标文件确实受 Git 跟踪，repo root 是 `/home/xp/.claude`；当前相对 `HEAD` 的总 diff 是 218 insertions／27 deletions，不是纯新增。这些更早已存在的未提交变化不能归因给本次三节插入，transcript 给出了区分两者的 pre-edit boundary。因而“这次编辑纯新增”为真，“git diff 看不到”为假。

旧覆盖没有因本次插入被删除；新增覆盖却与旧 `reference.md` 产生了上面 major 所列的矛盾。Rung 2 的 loaded-worktree trap 已在 `reference.md` 第 208 行存在，新正文是在主路径提升一个关键判据，属于有价值的正文重述，而不是无意义重复；前提是保持条件一致并引用 authority。

### 3. `the-body-holds-criteria-not-chronicle`

116 秒内三个 commit 前进，以及同一会话三次 collision 自行消失，都是紧接判据的一句实证：前者解释为什么长 gate 会使 CAS refusal 变得现实，后者解释为什么开工前 re-read 有回报。两段都让读者据此决定“CAS 拒绝后重建”和“先重读”，不是按时间展开的返工史，因此不构成 chronicle。唯一问题是第二段把样本外推得太强，已列 minor。

### 4. `four-ways-a-skill-goes-wrong`

新增文本没有服务名、内部路径、项目专有文件或只能在一个项目成立的命令。Git worktree、CAS、hook、pathspec 与 index/worktree 分层均跨 Git 项目复用；日期、116 秒、三次 commit、七个文件是具日期的证据，不是适用前提。没有“只对当时项目成立”的段落。

### 5. 技术验证结果

| 命题 | 一次性 fixture 结果 | 裁定 |
|---|---|---|
| `worktree add --detach "$W" "$OLD"` 后做一次普通 commit | `$NEW^ == $OLD` | 成立，但“恰好一次普通 commit、期间未移动 detached HEAD”是前提 |
| `rev-parse HEAD^` 断言 | 零 commit 与两 commit 均被拒绝；单 commit 通过 | 必要的 procedure guard，不是多余；它把散文里的“commit once”变成可执行断言。它只检查 first parent，若要排除 merge commit 还需另验 parent count |
| 正常 worktree commit 触发 hooks | `pre-commit|commit-msg:<COMMIT_EDITMSG>|` | 成立 |
| `git commit-tree` 触发 `pre-commit`／`commit-msg` | marker bytes 为 0 | 不触发，原主张成立 |
| CAS success | branch 从 `$OLD` 移到 `$NEW` | 成立 |
| peer 先移动 ref 时 CAS refusal | exit 128，peer tip 保持 | 成立 |
| Rung 2／3 内容缺 shared worktree 后，下一次同路径 pathspec commit | 两个 fixture 都静默删除 `mine` | 条件式成立 |
| worktree carrier CAS 后的 shared index | index 仍指向 `$OLD` blob，status 为 `M `；仅同步 worktree 后为 `MM` | 新配方不完整 |
| CAS 后 cleanup failure | remove exit 128，而 branch 已是 `$NEW` | 新配方错误传播 post-land failure |

主要证据目录：`/tmp/skill-carrier-review.Uq21SD`、`/tmp/skill-hook-review.CnWZBI`、`/tmp/skill-worktree-cleanup-review.CekhQ3`。

验证过程说明：首轮 hook probe 曾错误地把 `git -C ... rev-parse --git-path hooks` 的相对输出按 harness cwd 解析，因而在主仓 `.git/hooks/` 新建了两个 probe hook。birth time 证明两文件均为本轮新建、未覆盖旧文件；我已将它们备份到 `/tmp/skill-carrier-review.Uq21SD/accidental-hooks-backup/` 后精确删除，并用绝对 git dir 在 `/tmp/skill-hook-review.CnWZBI` 重跑。主仓没有残留这两个 hook。

### 6. 命名与交叉引用

目标文件内没有 `Rung 3b`、`rung 3b` 或 `Prefer 3b` 残留。第 38、115、191、270、271 行的 `§3b`／`3b. HEAD-moving` 都明确指向既有 §3b，不与新标题冲突。新三节之间的指代可解码。

断链不在旧标题，而在 skill namespace：live corpus 同时出现 `my-skills:coordinating-a-shared-git-worktree`、`git-preference:coordinating-a-shared-git-worktree` 与无 namespace 名称，当前运行时一个也没有可加载的目标。此项归 blocker 一并处置。

## 建议修改顺序

1. 先裁定并恢复 canonical skill 发布面，否则其余文字修改不会被召回。
2. 给 worktree carrier 补完整的多路径 conditional index realign，并明确 CAS 后所有 failure 的“commit 已落地”语义。
3. 把“从未落盘”和“Rung 2／3 必然缺 working-tree hunk”改成准确的 checked-out-tree／条件式命题，与 `reference.md` 第 208、293 行对齐。
4. 收窄“short half-life”的外推；保留两个实证段落作为判据依据。

## 复审：原发现修补（2026-08-22）

复审范围只含第一轮五项发现及其修补 diff，即当前 `SKILL.md` 第 117–173 行与它直接引用的既有 rung 1／2／3、`reference.md` 第 208、293 行；按请求没有重跑第一轮 fixture。本轮对 shell 配方做静态控制流与 Git entry-format 对账。

### 复审结论与计数

**Verdict：needs-fix。开放计数为 blocker=1、major=3、minor=0、nit=0。** 若只统计“实现者当前有权自行处理”的 blocker，可以记 `local-fixable blocker=0`；但从 skill 是否可交付、可召回的 readiness 口径看，加载面仍未恢复，所以原 blocker 只能记为 `pending-user`，不能记为已关闭。

本轮没有新增超出原发现域的问题。第一轮 minor 已关闭；worktree cleanup 命令本身的失败传播已关闭；但 index realign 只修了普通“路径在新旧 tree 都存在、mode 未被 peer 改过”的一格，post-CAS failure envelope 仍有未守住的命令，working-tree gap 也仍被写成了 Rung 3 的全称。

### BLOCKER 复审 — 处置正确，但 finding 仍开放并等待用户裁决

实现者没有把内容复制进已加载邻居，这个处置正确。向已加载邻居加一句指向当前 dead skill 的路标也不是补救：目标仍不可加载，读者只会得到一个更显眼的断链；若路标改成“直接读磁盘文件”，则是在用户裁决 canonical 发布面之前私建第二套加载机制，仍然绕过 B 级变更。当前最小正确动作就是保留 `pending-user` finding，不复制内容、不再增加死链接，等待用户裁定 namespace／安装面后一次性修活引用。

因此：实现者责任范围内没有遗漏动作，但 artifact 的开放 blocker 仍是 1，而不是 0。

### MAJOR 复审 1 — per-path realign 的字段位置基本正确，但 guard 和终态覆盖不完整

第 138 行对 `git ls-files --stage` 取 `$2` 得到 oid，正确；第 139、143 行对 `git ls-tree` 取 `$3` 得到 oid，正确；第 143 行取 `$1` 得到 mode，也正确。对旧、新 tree 都有普通 stage-0 entry 的 content modification，这组字段能生成合法的 `--cacheinfo <mode>,<oid>,<path>`。

但原 major 要求的是“当前 index **entry**仍等于 `$OLD` baseline entry”，修补只比较 blob。`ls-files --stage` 的完整关键部分是 `<mode> <oid> <stage>`；peer 若只暂存了 `100644 → 100755` 的 mode change，blob 与 `$OLD` 相等，当前 guard 会通过并用 `$NEW` mode 覆盖 peer snapshot。冲突 stage 也应明确要求 stage 0，而不是靠多行输出碰巧不等。guard 必须至少比较 old tree 的 `mode+oid` 与 index 的 `mode+oid+stage=0`；两边都无 entry 才表示 baseline 本来不存在。

删除路径也没有处理。`git ls-tree "$NEW" -- "$P"` 对 deletion 返回空，当前代码拼出 `,,<path>`，`update-index --cacheinfo` 失败后被吞掉，旧 index entry 继续作为 `$NEW` HEAD 上的 staged inverse；rename 的旧路径同样中招。删除分支需要在 baseline guard 通过后用 index-only remove 语义 realign，同时保留 shared working-tree 文件。新增路径这一格则可工作：old tree 与 baseline index 都空、new entry 非空。

`for P in <the paths you committed>` 还把真实 changed-path set 交给人工枚举；漏掉 hook 自动纳入的路径、rename 的旧侧，或错误 shell-split 含空白的路径，都会留下 phantom inverse。更可靠的 producer 是从 `$OLD..$NEW` 派生 NUL-delimited changed paths，再逐项处理 add／modify／delete；若正文坚持 placeholder，也必须明确它包含 commit 实际改变的两侧路径并保留 path 原子性。

所以第一轮“补完整的多路径 conditional index realign”尚未关闭。此项仍是 major。

### MAJOR 复审 2 — cleanup 已 best-effort，但“CAS 后不得报告失败”尚未由控制流完全保证

第 147–148 行的 `git worktree remove ... || echo ...` 正确关闭了第一轮具名 cleanup failure；普通 remove 失败不会再把已落地 commit 报成 CAS refusal。

然而第 138、139、141 行三个 command-substitution assignment 都没有放进 `if`／`||` 的 best-effort 分支。调用者若启用了 `set -e -o pipefail`，任一 `git ls-files`／`git ls-tree` 读取失败都会在 CAS 已落地后直接退出；未启用 `pipefail` 时，前置 Git 命令的失败又可能被末端 `awk` 的 0 吃掉，门转而 fail-open。第 135 行的全称“Everything below ... must not report failure”因而仍只是注释，没有被 shell 控制流机械落实。

每个 post-CAS read／parse 都应显式写成“失败则打印 `$NEW` 已落地并 `continue`”，且不能让 pipeline 的最后一个过滤器替 Git 命令提供退出码。`update-index` 与 worktree cleanup 现有的 `|| echo` 形状可以保留。此项仍是 major。

### MAJOR 复审 3 — Rung 2 的错误全称已撤掉，但 Rung 3／worktree gap 仍是错误全称

把 Rung 2 从标题与主张中移出，并把一次会话三个样本明确降为非测量，两个方向都对；第一轮 minor 因此关闭。`$D/mine` 改成“temp directory”也修正了“从未落盘”的字面错误。

但第 119、161–167 行仍断言 private-index／worktree carrier 发布的作者 hunk必然不在 shared working tree。既有 `reference.md` 第 293 行明确给出正常形态：作者与 peer 的 hunk 原本都在 shared worktree，private index 只是从中分离作者 hunk去提交；CAS 后 shared copy 仍同时含两边，因而相对 HEAD 只多 peer hunk。worktree carrier 也常从这份 mixed shared copy 重建 `$W`，不会自动删除 shared copy 里作者原有的 hunk。另一个合法 Rung 3 入口是“同路径完全归我、但 shared index 里有 peer 的其它 staged file”，此时 `$D/mine` 甚至可以与 shared working-tree file 字节相同。

真实判据仍然必须是条件式：“如果 `$NEW` 中某个作者 hunk不在 shared working-tree copy，就同步它；若 shared copy 已含作者 hunk，只检查它没有作为 inverse 出现在 diff。”标题宜改成 `When rung 3 leaves the shared working tree behind`。第 119 行的 carrier 比较也应写成“private-index recipe 不保证 exact `$NEW` tree 曾被 checkout 并运行 gate”，而不是“它从未是这个仓库 working tree 的内容”。

Rung 2 的正常 recipe 确实从 working tree 切 patch，但 `reference.md` 第 208 行还保留了从 HEAD／index context 构造 patch 的异常分支；正文若要说“本节不讲正常 Rung 2”没有问题，最好不要把“Rung 2 永远不可能有此 gap”写成全称。此项仍是 major。

### 三节之间及与既有 ladder 的对账

除上述条件域问题外，三节的顺序和职责现在可以解码：carrier 选择 → index／worktree 两层 realign → 开工前廉价重读；与 §2 的长期 session isolation 仍是不同触发时刻，没有新增重复。Rung 1“pathspec 从 working tree 取该路径”、Rung 2“正常流程 patch 来源于 shared working tree”、Rung 3“CAS 后 post-land housekeeping 不得诱发 rebuild”三条既有合同都保留。

尚未闭合的矛盾只有两族：realign loop 没覆盖完整 Git entry／path state space，以及 working-tree absence 被写成 Rung 3 的必然结果。修完这两族并把所有 post-CAS reads 包进 best-effort 控制流后，三个第一轮 major 才能归零。

## 第三轮复审：三条 major 的第二次修补（2026-08-22）

复审范围限定为上一节的三个 major 与当前 `SKILL.md` 第 119–188 行修补 diff。没有重跑第一轮 fixture；另做了一次只针对本轮“rename 两侧是否都在 `--name-only -z` 输出中”的一次性探针，位于 `/tmp/skill-realign-rename-review.ppYqYt`。

### 第三轮结论与计数

**Verdict：needs-fix。开放计数为 blocker=1、major=2、minor=1、nit=0；其中 blocker 仍是 `pending-user`，实现者本地可修 blocker 为 0。** 上轮 major-3 已关闭；major-1 与 major-2 仍各有可导致错误终态／错误退出的缺口，不能归零。

### MAJOR-1 复审 — entry guard 与 add／modify／delete 已修，但 rename、路径原子性与 check→reset 竞态尚未闭合

这轮修补确实关闭了上轮点名的三个静态缺陷：`IDXKEY` 现在读取 `ls-files --stage` 的 mode=`$1`、oid=`$2`、stage=`$3`，`BASEKEY` 读取 `ls-tree` 的 mode=`$1`、oid=`$3`；多行或非 stage 0 会拒绝；add／modify／delete 统一交给 index-only `git reset -- <paths>`，不再从空 `NEWENTRY` 拼 `,,<path>`。把 NUL 流写入临时文件再由 `read -d ''` 消费也是正确修法，避免了 command substitution 丢 NUL。

但第 171 行“`--name-only -z` gives both sides of every change”不成立。针对纯 rename 的一次性探针得到 `git diff --name-status` 为 `R100 old name.txt new name.txt`，而 `git diff --name-only -z "$OLD" "$NEW"` 的 token 只有 `new name.txt`；旧路径不会进入 guard／reset，仍以 staged inverse 留在 index。这里应显式加 `--no-renames`，让 rename 按 delete+add 产出两侧，或解析 `--name-status -z` 的可变字段；前者更简单，也正符合 realign 的目标。

第 151、159 行的空格拼接仍破坏路径原子性。`SAFE="$SAFE $P"` 加无引号 `$SAFE` 会按 IFS 拆开含空格／换行的路径，并再次做 glob expansion。因为代码块明确是 Bash，最小修法是 `SAFE=()`、循环内 `SAFE+=("$P")`、循环后 `if ((${#SAFE[@]})); then git --literal-pathspecs reset --quiet -- "${SAFE[@]}" || ...; fi`。路径数量可能逼近 `ARG_MAX` 时，可另写 NUL-delimited `SAFELIST` 并使用 `--pathspec-from-file`／`--pathspec-file-nul`；当前规模下 Bash array 更直接。

还有一个 fixture 没覆盖的并发接缝：guard 读取 entry 后，代码先收集全部 `$SAFE`，最后才启动一次 `git reset`。peer 若在其间暂存同一路径，reset 会无条件覆盖那份刚出现的 snapshot；“fixture 中 peer 在 guard 之前暂存会被保住”证明不了这一窗口。要让“只在 entry 仍等于 baseline 时 realign”在动作时仍成立，需要在短暂的 guard+reset 区间持有本 skill §5／isolation ladder 所说的 L2 `git` resource lock；拿不到 lock 就跳过 realign并警告。仅在 reset 前再读一次仍留有同样的 check→write 缝，不能算关闭。

因此 major-1 仍开放。

### MAJOR-2 复审 — 两个空测试本身不触发 `errexit`，但 cleanup 与 parse 仍有 post-CAS 硬失败路径

用户点名的两个形状要分开裁定。在 Bash `set -e` 下，`[ -n "$PATHLIST" ] && ...` 与 `[ -n "$SAFE" ] && ...` 的左侧测试属于 AND-list 的非末命令；空值令测试返回 1 时不会触发 `errexit`。第二条在非空时执行的 group 又把 `git reset` 放在 `|| echo` 中，所以单就这两个“空值”分支，不是新的硬失败路径。

但第 156 行在 `$PATHLIST` 非空时，`rm -f "$PATHLIST"` 是 AND-list 的末命令；它若失败，继承了 `set -e` 的调用者会在 CAS 已落地后立即退出。应改成显式 `if`，并把删除失败也吞成具名 warning：`if [ -n "$PATHLIST" ]; then rm -f -- "$PATHLIST" || echo "commit $NEW landed; path list $PATHLIST remains" >&2; fi`。

第 148–149 行的 `IDXKEY=$(printf ... | awk ...)` 与 `BASEKEY=...` 同样没有 `if`／`||`。它们不再让 `awk` 代替 Git 命令判成败，这是进步；但 `awk` 自身缺失或解析失败时，assignment 仍可在 `set -e -o pipefail` 下直接退出，末尾的 `:` 来不及执行。把两个 parse assignment 也放进 `if ! ...; then warn; continue; fi`，才能兑现第 174 行“every read is inside an if or carries ||”这一全称。

末尾 `:` 只稳定正常走到块尾时的最终状态，救不了 `errexit` 提前退出。major-2 因此仍开放。

### MAJOR-3 复审 — 条件域已经修正，major 关闭

标题已改为 `When rung 3 leaves the shared working tree behind`；第 182 行先声明 ordinary shape 通常没有 gap，并与 `reference.md:293` 对齐；第 186 行把动作绑定到可观察判据“diff 是否把作者改动显示成 removal”。这已消除“Rung 3 必然缺 shared-working-tree hunk”的错误全称，也恢复了 filtered-patch 异常分支到 `reference.md:208` 的路由。该 major 关闭。

保留一个 minor 措辞问题：第 184 行列出三种**可能**从 shared copy 之外构造内容的入口后，仍写成“In all three the shared copy never received your change”。从 `$OLD` 独立重建不排除同一 hunk 本来已在 shared copy；正确说法是“each can leave a gap when the shared copy did not independently receive the same change”。因为第 186 行的终端检查会阻止误操作，这一残余不再是 major。

### BLOCKER 状态

加载面 blocker 没有变化，仍为 artifact readiness 的 1 个 `pending-user` blocker、本地可修计数 0。仍不建议向已加载邻居添加一个指向 dead skill 的路标；它既不恢复内容可达性，也会扩散断链。

### 归零条件

1. 路径 producer 显式覆盖 rename 两侧，safe paths 保持原子，guard+reset 在 L2 `git` resource lock 下执行。
2. `PATHLIST` cleanup 与两个 key parse 都进入显式 best-effort 控制流，保证 `set -e -o pipefail` 下也走到末尾 `:`。
3. 第 184 行把三种入口从必然 gap 收窄为可能 gap。

满足前两项后，major 可归零；第三项关闭当前唯一 minor。

## 第四轮复审：缩回单路径配方与 L2 取舍（2026-08-22）

复审范围限定为第三轮的 major-1、major-2、minor 及本轮“脚本缩回判据”的方向调整，没有重跑 fixture。

### 第四轮结论与计数

**Verdict：needs-fix。开放计数为 blocker=1、major=1、minor=1、nit=0；其中 blocker 仍是 `pending-user`，实现者本地可修 blocker 为 0。** rename、路径原子性、add／modify／delete、post-CAS `errexit` 与 gap 条件域的具名缺陷都已修；剩余 major 是 L2 限制仍排在危险动作之后、且未成为执行该动作的前置条件。

### 对方向性取舍的明确裁定

**认可“不在代码块里实现 L2 锁协议”，也认可逐路径 check→reset 取代批量收集；不认可当前把无锁 reset 作为默认执行路径、做完后才说明窗口。** 正确落点不是“必须内联一套锁实现”和“完全不许给命令”二选一，而是把 L2 写成代码块的外部前置条件：在进入 CAS／realign 的短区间前取得 §5 的 `git` resource lock并持有到 realign 结束；拿不到就不执行 unlocked realign，明确报告 shared index 仍携带 inverse。

`default-to-prose-not-script` 并不禁止这里所有 shell：entry 是否等于 baseline、changed-path set、reset 是否成功都有外部 Git oracle，逐路径命令是允许的原子动作；项目的 proof-infrastructure 禁令也不适用，因为这里没有新增 CI／gate。不能脚本自证的是“check 后、reset 前绝无 peer writer”这一并发命题，它依赖外部协调，所以应由正文判据拥有，而不是把锁协议塞进 shell。

我的偏好是：正文保留四个承重不变量——changed paths 从 `$OLD..$NEW` 派生、entry 比较 mode+oid+stage、路径逐项 literal reset、post-CAS 只 warn——并在代码块**之前**写“仅在持有 L2 时执行；否则跳过并声明 stale index”；当前短块可以保留。若以后继续增长，再把完整命令移入 `reference.md`，正文留下带触发时机的 REQUIRED 指针；没有必要现在把所有命令删成纯散文。

### MAJOR-1 复审 — 路径与终态覆盖已修，L2 仍须从事后限制提升为前置条件

`--no-renames --name-only -z` 会把 rename 按 delete+add 暴露两侧；逐路径、带引号的 `git --literal-pathspecs reset -- "$P"` 同时解决了空白／换行／pathspec magic、`ARG_MAX` 与旧侧遗漏。mode+oid+stage guard、NUL 临时文件和 add／modify／delete reset 也与本轮 fixture 结果一致。这些子项关闭。

但第 177 行对 race 的说明位于第 145–158 行循环**之后**，而循环默认已经执行 unlocked reset。它诚实承认“不 airtight”是进步，却没有改变动作：任一 live peer 都可能在 `IDXKEY` 读取后、该路径 reset 前暂存，reset 随即覆盖 guard 从未见过的 snapshot。“tree busy enough”没有可观测阈值，读者无法在动作前判断何时该升级；缩短窗口降低概率，不改变错误终态。

因此，L2 无需由这个代码块实现，但必须成为动作前的白名单式前提，而不是事后披露：**持有 L2 才运行 realign；未持有就跳过 reset并发出 stale-index warning。** 最好在 worktree gate 完成后、CAS 前取得短时 L2 并持有到 realign 结束；CAS 仍负责拒绝锁取得前已经发生的 ref movement。当前形态未满足这一点，所以 major-1 尚未关闭。

### MAJOR-2 复审 — post-CAS 控制流已闭合，major 关闭

`IDX`／`BASE` reads 都带 `||`；两个 `awk` assignment 都处在 `||` 左侧，因而在 `set -e -o pipefail` 下不会提前退出；`rm` 已放入 `if` 且失败由 `|| echo` 吞成 warning；per-path reset、worktree cleanup 也都显式降级，块末 `:` 稳定最终退出码。第三轮点名的 post-CAS hard-failure shape 已关闭。

### MINOR 复审 — gap 措辞已修；`IDXKEY=?` 仍混合 parse failure 与 guard-negative

第 189 行已把三个入口改成 `can leave a gap` 并承认同一 hunk 可能独立存在于 shared copy，第三轮 minor 关闭。

`IDXKEY=$(...) || IDXKEY=?` 在控制流上安全，且 `?` 不可能与正常的 `<mode> <oid>` key 相等，所以它不会误放行；但它把“awk 无法执行／parse 失败”和“entry 合法解析后为 conflicted／非 stage 0”压进同一个 sentinel，随后第 153 行统一归因为“someone staged there”。这会吞掉真正的 parser failure，并使后来者误以为 `?` 只是可随手优化掉的值。

建议把机制失败与领域判否分开：`if ! IDXKEY=$(...); then echo "$P: cannot parse index entry; not realigning"; continue; fi`；awk 内部若仍需用 `?` 表示“成功解析出的非基线形态”，保留它并在 guard 中判断。`BASEKEY` 同理。此项是可维护性与错误归因 minor，不影响 fail-closed 行为。

### BLOCKER 状态

加载面仍是 artifact readiness 的 1 个 `pending-user` blocker、本地可修计数 0；本轮方向调整不改变该状态。

### 本轮归零条件

1. 把 L2 从循环后的 known limitation 移成循环前的执行前提，禁止默认运行 unlocked reset；无需在本代码块实现锁协议。
2. 将 parser failure 与 parsed guard-negative 分开报告，关闭唯一 minor。

第一项完成后 major 可归零。

## 第五轮复审：L2 fail-closed 分支与 parser 分型（2026-08-22）

复审范围限定为第四轮开放的 major-1 与 minor，没有重跑 fixture。

### 第五轮结论与计数

**Verdict：needs-fix。开放计数仍为 blocker=1、major=1、minor=1、nit=0；其中 blocker 是 `pending-user`，实现者本地可修 blocker 为 0。** L2 已从事后说明移动到 reset 之前，parser failure 也已从 guard-negative 分出；但 L2 分支本身仍有两个 fail-open 表达，解释段还残留上一版 `?` sentinel 的陈述。

### MAJOR-1 复审 — 方向已经改对，但 L2 白名单与 warning 仍各留一个绕回 unlocked reset 的入口

把 realign 整体放进 L2 条件分支、未持锁时完全跳过 reset，是正确修法；无需也不应在这个代码块内实现锁协议。`HAVE_GIT_LOCK` 作为“读者已按 §5 取得外部锁”的显式 attestation 可以接受，skill 文本不必机械验证锁所有权。

第 142 行当前用“是否非空”判定锁：`[ -z "${HAVE_GIT_LOCK:-}" ]`。这不是白名单；`HAVE_GIT_LOCK=0`、`false`、旧 shell 遗留的任意非空值都会进入 destructive reset 分支。既然正文只定义值 `1`，门也必须只放行精确的 `1`：`if [ "${HAVE_GIT_LOCK:-}" != 1 ]; then warn-and-skip; else ... fi`。这不要求新增锁实现，只是让 attestation 的合同 fail-closed。

更直接的绕回在未持锁 warning：第 143 行写“realign under the §5 git lock, **or clear those paths by hand**”。手工 clear 仍是同一个 index write，仍有同一 check→act race；把它列成不持锁的替代路线，会把刚刚关上的危险分支重新打开。warning 应只给一条安全路：“obtain the §5 git lock, then rerun／clear those paths; until then do not make a bare commit”。任何 index realign，无论脚本还是手工，都受同一 L2 前提约束。

这两处都能让读者在没有锁的状态下执行 reset，属于会毁同伴 snapshot 的原 failure shape，所以 major-1 尚未归零。修正后，L2 major 可以关闭。

### MINOR 复审 — parser 控制流已拆开，但解释正文仍描述旧 sentinel

第 157–160 行已经把“awk 执行失败”分别路由到 `cannot parse ...; continue`，而 `multi`／`conflicted` 是成功解析出的 guard-negative；代码层的概念分离正确，`IDXKEY=?` 耦合已消失。

但第 190 行仍写“两条 awk pipeline fall back to `?` rather than exiting if awk is absent”，这与当前代码不符。应改成“each parse has an explicit failure branch that warns and continues”。这是陈述漂移，不会令 guard fail-open，故维持 minor；修正文案后归零。

### 必须改与可 deferred

**必须改：**

1. L2 gate 只接受精确值 `1`，其它所有值都走 skip。
2. 删除“不持锁也可手工 clear”的替代路线；手工 realign 同样必须在 L2 下。
3. 更新第 190 行残留的 `?` sentinel 说明，使其与实际 parser branch 一致。

**可 deferred：**

1. 在代码块内实现或机械验证 L2 lock ownership；当前文本 attestation 足够，真正锁协议继续归 §5／isolation skill。
2. 把完整 realign 命令搬进 `reference.md`、正文只留不变量和 REQUIRED 指针；当前体量尚可读，是否搬迁是后续组织优化，不影响本轮正确性。
3. 为这两处纯控制流／陈述修订再造 fixture；已有 fixture 足以覆盖主要 Git 终态，本轮剩余项静态可判。

### BLOCKER 状态

加载面仍是 artifact readiness 的 1 个 `pending-user` blocker、本地可修计数 0，本轮不变。

## 第六轮复审：L2 拒绝面与 parser 说明收口（2026-08-22）

复审范围限定为第五轮的 major-1 与 minor，没有重跑 fixture。

### 第六轮结论与计数

**Verdict：needs-fix only because of the pending-user loading blocker。当前开放计数为 blocker=1、major=0、minor=0、nit=0；实现者本地可修 blocker 为 0。** 本次待审三节及其 carrier 配方的所有 review finding 已归零。

### MAJOR-1 复审 — 关闭

第 144 行现在只对白名单值 `HAVE_GIT_LOCK=1` 开放 reset；`0`、`false`、未设及其它任何值都走 warning-and-skip。第 145 行只给出“取得 §5 lock 后再 realign”这一条安全路线，并明确要求在任何 bare commit 之前处理，不再把 unlocked hand-clear 作为捷径。第 190 行正文同步解释了精确值门和 fail-closed 方向。

这满足上一轮裁定：锁协议继续由 §5／isolation skill 拥有，本代码块只消费一个显式 attestation；未持锁时不写 shared index。major-1 关闭。

### MINOR 复审 — 关闭

第 159–162 行把 parser execution failure 分别送到具名 warning+continue；成功解析出的 `multi`／`conflicted` 只承担 guard-negative。第 192 行也已改写为相同语义，不再声称 fallback 到 `?`。代码与解释重新一致，minor 关闭。

### 必须改与 deferred

**必须改：无。** 当前实现者范围内没有 blocker／major／minor／nit。

**Deferred：**是否把完整可运行配方移到 `reference.md` 不影响本轮正确性，可以后续单独做。若移动，正文必须保留 carrier 取舍、L2 白名单前提、mode+oid+stage guard、`--no-renames`／NUL 路径原子性、post-CAS 只 warn 这些承重判据，并留下带触发时机的 REQUIRED 指针；迁移本身要再做一次双向覆盖对账，不能仅以篇幅为理由。

### BLOCKER 状态

唯一开放项仍是加载面：artifact readiness 有 1 个 `pending-user` blocker，本地可修计数 0。它不影响本轮三节内容的评审归零，但在用户裁定并恢复 canonical 发布面之前，整份 skill 仍不可宣称可召回／已部署。

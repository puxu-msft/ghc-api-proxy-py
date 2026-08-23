# 会话 `be410f2e` 临时状态处置清单

**根**：`/home/xp/.claude/jobs/be410f2e/tmp`（`CLAUDE_JOB_DIR=/home/xp/.claude/jobs/be410f2e`，已确认变量已设置、目录存在）。

**枚举**（2026-08-23 07:0x **关闭前重列**，两法一致）：

| 方法 | 结果 |
|---|---|
| `find "$R" \( -type f -o -type l \)` | **71** |
| `fd -H -I --type f --type l . "$R"` | **71** |
| `fd -H --type f --type l . "$R"`（对照，不加 `-I`） | 68 |

那 3 个差额是 `dist/` 下被 `.gitignore` 覆盖的项——**本次实测复现了「`fd` 不加 `-I` 会少报，且少报的正是没人评审过的那几行」这条已知陷阱**。清单由 `find` 产出（下表所有 71 个路径逐一出现，计数可机械核对）。

**首次枚举时是 66**，关闭前重列得 71；**5 个新增全部回到分类**（组 6，均为本次收尾新写的提交信息文件），没有一个被扫进计数了事。

**一次中途暴增，记下来以免下一个人困惑**：为复现搬迁前的模块计数，我在此目录下建过两棵临时 git worktree（`pre-step0` @ `8fb267b`、`at-archive` @ `2248a69`），期间 `find` 数到 **1129**，其中 1058 个属于那两棵树。两棵都是 detached、`git status --porcelain` 为空、HEAD 在 `main` 上可达，已用 `GIT_DISCIPLINE_OK=1 git worktree remove` 移除，计数回到 71。`.claude/worktrees/` 下同伴那四棵**一棵都没碰**。

**处置动作只有五种**：逐字持久化 ／ 蒸馏进结论载体 ／ 暂留并说明理由 ／ 验证后删除 ／ **原地弃置**（结论已有载体、结果记在本清单、文件留给 harness 过期）。

**本次的总处置是「原地弃置为主，5 个探针逐字持久化」——不执行任何删除。** 因此本清单不主张「差集已证明为空」，只主张：下表每一行都被分类过，每一条仍有指导价值的结论都有一个可定位的持久载体。

**评审状态**：✅ **已过一轮独立评审并按其结论修订**（报告：[260823-review-temp-manifest.md](260823-review-temp-manifest.md)，判定 needs-fix，0 blocker / 6 major / 7 minor / 2 nit）。六条 major 全部采纳并落地，其中一条改变了处置（`delete-manifest.json` 由弃置升为逐字持久化），一条改变了判据（计数门由「总数相等」改为「未分类差集为空」）。

评审明确**不建议把任何一行升级为真删除**，理由不是「删了可惜」，而是**本次审计自身的错误率**：一份主张「差集已证明为空」的清单，其差集运算刚被查出 6 处 major 缺陷。**零删除是这份清单当前唯一守得住的档位**——这个理由比我原先写的更硬，采纳。

---

## 组 1：`split/` —— 拆分 `2afa0c4` 与文档引用重指的中间态（33 个）

`docs-msg.txt`、`docs-msg2.txt`、`docs-paths.txt`、`docstree.txt`、`idx`、`idx2`、`oldtip.txt`、`newtip.txt`、`newtip2.txt`、`curtip.txt`、`target-tree.txt`、`c1-paths.txt`、`c2-paths.txt`、`p0.txt`、`p1.txt`、`p2.txt`、`pu.txt`、`paths.txt`、`pairs.txt`、`pairs2.txt`、`m.txt`、`rd.txt`、`status-before.txt`、`status-after.txt`、`sa2.txt`、`sb2.txt`、`refactor-msg.txt`、`refs-msg.txt`、`refs-msg2.txt`、`followup-msg.txt`、`my-files.txt`、`mine.txt`、`pyright-files.txt`

**长期价值：无。** 全部是 plumbing 操作的输入与中间态：私有索引二进制（`idx`/`idx2`，共 116K）、进哪个提交的路径清单、`commit-tree` 的父子对、前后 `git status` 快照、`git range-diff` 输出（`rd.txt`）、以及各步的 tree/tip SHA。

**替代证据（逐一命名到文件级）**：

- 提交信息文件 → 对应提交**已存在且带着那条信息**：`fa0b281`（`docs-msg2.txt`）、`800eb5b`（`refactor-msg.txt`）、`598b778`（`refs-msg.txt`）、`1f29d0a`（`followup-msg.txt`）。
- **`refs-msg2.txt` 是个例外，我原先声称「已核对内容一致」是假的**（评审查出）：它不对应任何提交。它是 `598b778` 的加长改写稿，`15:37` 写好、`15:39` 因同伴提交而**永远没能 amend 上去**。它相对 `1f29d0a` 差 84 行。**它仍然可以弃置，但换一条理由**：评审核实了 `1f29d0a` 的信息第 32–36 行已完整承载它的两处实质更正（「eleven modules」→「thirteen citations across twelve modules」、「six spec.md/deferred.md」→「five of each，那个六来自一次截断的列举且混进了 worktree 副本」），**独有内容为零**。
- **`docs-msg.txt` 对应的 `bbf5f50` 不被任何 ref 包含**（评审 HANDOFF 第 3 条）——那是拆分过程中被后续改写取代的中间提交。其最终形态是 `fa0b281`，由 `docs-msg2.txt` 对应。不为它建 ref：中间态没有独立价值，而留存分支 `a/2026-08-22-split-2afa0c4` 已承载改写前的原尖端。
- 路径清单与私有索引 → 那两个提交各自的 `git show --stat`。
- tip／tree SHA → **留存分支 `a/2026-08-22-split-2afa0c4` 在 `30f251c`** 承载了改写前的原始尖端，比一个 41 字节的 SHA 文本文件更耐用（它是 ref，不会被当成垃圾清掉）。
- `status-before/after.txt`、`sa2/sb2.txt`（「我没动同伴的东西」的自检对照）→ 结论已成立且提交已落；这类快照的价值在操作当时，事后不可再用（同伴此后已多次提交）。
- **`rd.txt`（`range-diff` 输出，40K）→ 替代成立，但我初版写的理由是错的。** 我写「结果已在两个提交里」，而 range-diff 记的是**改写前后的对应关系**，不是结果。**真正承重的是两端都还可达**：改写前的原尖端由留存分支 `a/2026-08-22-split-2afa0c4` @ `30f251c` 承载，改写后在 `main` 上。评审当场重跑了 `git range-diff e7cf57a..a/2026-08-22-split-2afa0c4 e7cf57a..1c91870`，配对干净，**且比 `rd.txt` 更准**——`rd.txt` 对的是一条后来被弃的中间链。

**动作：原地弃置。清理前置条件：无（不执行删除）。**

## 组 2：复现探针与删除授权书 —— **已逐字持久化**（6 个）

`reach.py`、`count.py`、`sets.py`、`importable.py`、`drop_emptied_dirs.py`、`delete-manifest.json`

**长期价值：有，且是唯一的。** status.md 写着 106 → 83、247 → 169、77 + 48，但只写了「实测」；这 5 个脚本（合计 2.3KB）是那些数字的唯一复现手段。**这正是技能列的第一条判断错误的形状——把派生数据和产生它的脚本一起扔掉。**

**接收者**：`.dev/docs/server-layout/probes/`，随 `.dev` 提交 **`44d9859`** 落地，逐字复制未作修改。同目录 `README.md` 记录了每个探针的当前复现值、正样本对照、以及各自不能证明什么。

**持久化后已验证**：在主仓 `7525f76` 上重跑，`reach.py`+`count.py` 复现 83／25，正样本对照 `import app.server` 得 1；`importable.py` 得「169 个模块，0 失败」。`sets.py` 报 `ModuleNotFoundError: app.server.app_factory`——**它已随第 6 步自我失效，探针的失效即归档的证明**，README 给了回到 `2248a69^` 复现的方法。

**`delete-manifest.json` 是评审建议加进来的，理由成立**：它**不是任何脚本的输出**，是手写的删除授权书——喂给删除护栏的那一份，内含六个被删目录的字面路径、两条 `preserved` 声明（「46 个 `.py` 已由 `git mv` 迁至 `src/.archived/app/`」「六个目录此刻只含 `__pycache__`，脚本每次 rmtree 前断言无真实文件」），以及一段 `note` 说明为什么设了 `allow_unenumerated_targets`。**它与 `drop_emptied_dirs.py` 是一对：脚本是执行者，清单是授权书**，分开留任何一个都读不出当时到底删了什么、凭什么删。已随本轮落进 `probes/`。

**顺带更正我写进项目记忆的一句话**：我曾写「有意不用 `allow_unenumerated_targets` 旁路，改为把路径写成字面量」——**错了，那个开关实际是打开的**，因为护栏读不出被调用的 Python 脚本内容，它是唯一的出路。字面路径是**额外**的自律，不是替代。记忆 `bash-guards-block-the-whole-call-not-the-command` 已更正为「开关关掉的是护栏的检查，不是你自己的」。

**动作：逐字持久化（已完成）+ 副本原地弃置。**

## 组 3：一次性探测脚本与派生数据（10 个）

`probe_chain.py`、`A.json`、`B.json`、`sets.json`、`handler_imports.txt`、`legacy_files.txt`、`legacy_tests.txt`、`tests_only_legacy.txt`、`tests_archive.txt`、`move.txt`

（`delete-manifest.json` 原本列在这里，**评审指出它不是任何脚本的输出**，已移入组 2 逐字持久化。）

**长期价值：无。**

- `probe_chain.py` —— `core/chain.py` 落地前的前瞻试算。结论已经**变成** `chain.py` 本身及其 docstring，探针没有二次价值（README 已记录未保留它的理由）。
- 其余 9 个是组 2 那些脚本的输出。归档划分的最终形态已经是 `2248a69` 里 125 条 100% 相似度的 rename 记录，比任何一份中间清单都权威。

**「脚本在，数据可再生」这句我原先写得太顺，评审指出它与组 2 自陈的事实直接矛盾**：其中八份（`A.json`、`B.json`、`sets.json`、`legacy_files.txt`、`legacy_tests.txt`、`tests_only_legacy.txt`、`tests_archive.txt`、`move.txt`）全是 `sets.py` 那条差集流水线的产物，而 `sets.py` **在当前树上一行都跑不出来**——它 import 的 `app.server.app_factory` 正是被归档的入口。准确的说法是：**脚本在，且 `probes/README.md` 的 `sets.py` 一节给了回到 `2248a69^` 复现的方法（`2248a69` 在 `main` 上可达，这条路今天仍然走得通）；但在当前树上这八份数据不可再生。** 只读这份清单的人会以为跑一遍脚本就行，跑完拿到 `ModuleNotFoundError` 然后不知道下一步——这正是两段隔十行互相拆台的代价。

**动作：原地弃置。**

## 组 4：worktree 误改还原的逐行核对证据（6 个）

`cli.base`、`cli.mine`、`cli.peer-worktree.bak`、`only-mine.patch`、`tsd.base`、`tsd.mine`

**长期价值：无，且继续留着有轻微坏处**——其中 `cli.peer-worktree.bak`（23K）是**同伴工作树中文件的副本**，还原已完成，一份滞留的旧副本只会在将来被误读为当前状态。

**替代证据**：教训已进项目记忆 `repo-wide-rewrites-walk-into-peer-worktrees`，含「不要整树 checkout、逐文件核对 `non-mine-lines=0` 再单独还原」的完整做法与实测结果。三棵树的最终状态已在会话中验证（两棵回到干净，一棵只剩同伴自己的 6 个文件）。

**动作：原地弃置。**

## 组 5：`handler.py` 溶解的切块工具与产物（3 个）

`block.py`（14K）、`handler_blocks.py`（36K）、`handover_src.txt`（6.2K）

**长期价值：无。** `handler.py` 已被删除，其内容分入 4 个模块，落在提交 `1b34815`。`handler_blocks.py` 是切块中间产物，`handover_src.txt` 是搬迁时抄写的源码片段——**这些代码现在都在 `src/` 里的正式位置**，副本只会成为第二份会漂移的真相。

**动作：原地弃置。**

## 组 6：提交信息文件（10 个）

`msg3.txt`、`msg4.txt`、`msg5a.txt`、`msg5b.txt`、`msg6.txt`、`dotdev-msg1.txt`、`dotdev-msg2.txt`、`dotdev-msg3.txt`、`dotdev-msg4.txt`、`main-msg1.txt`

**长期价值：无，解除条件已满足。** 技能规定提交信息文件在「命名的提交存在且带着那条信息」之前不自动可弃。

**映射（经独立评审逐条跑回 git 核对，初版第一条是错的）**：`msg3.txt` → **`1b34815`**（不是我原先写的 `28c1a7a`）、`msg4.txt` → `b973ed0`、`msg5a.txt` → `c01191f`、`msg5b.txt` → `ef4defb`、`msg6.txt` → `2248a69`、`dotdev-msg1`～`5` → `.dev` 的 `44d9859`／`a9e10a4`／`0cb3759`／`11a1b6a`／`0fec088`、`main-msg1.txt` → 主仓 `af40e9b`。全部解除条件满足。

**文件名按步号编，不按提交顺序**（`msg3` = 第 3 步），所以「哪一步用了 `-m` 内联」正好表现为**那一步没有对应文件**——第 2 步就是唯一没有的那一步。

**我原先在这里写的「一个例外」不存在，评审查出来了，更正如下。** 我曾写「`msg3.txt` 里是完整的而 git 里是残缺的」，据此把它列为本清单唯一一处「替代证据与原件不等价」。**真实情况更简单**：`msg3.txt` 是 `1b34815` 的信息，与 `28c1a7a` 毫不相干（diff 56 行）；**`28c1a7a` 的完整信息在本目录里根本不存在**，因为它正是那条用 `git commit -m` 内联传的——从来没有落过盘。

**但这条更正带出了一个实际的修复。** 原文并非不可恢复：**命令替换发生在 shell 里，而 transcript 记的是 shell 收到之前的那份 argv**。完整信息（含全部 8 个符号名）已提取并存进 [`.dev/docs/server-layout/reports/260822-28c1a7a-intended-message.md`](../server-layout/reports/260822-28c1a7a-intended-message.md)，附与 git 版本的逐行 diff（5 行受影响）。`status.md` 的那条债与记忆 `never-pass-a-commit-message-inline-to-bash` 都已指向它。

**所以本清单现在没有「替代证据与原件不等价」的行**：`msg3.txt` 由 `1b34815` 承载，`28c1a7a` 的原文由那份报告承载，两者都不依赖本目录存活。

**动作：原地弃置。**

## 组 7：构建实测产物（2 个）

`dist/.gitignore`（1 B）、`dist/app-0.1.0-py3-none-any.whl`（**399K，占本目录体积的 46.3%**——我初版写 39%，评审实测 399209／861995）

**长期价值：无。** 结论（wheel 174 个条目、不含 `.archived`、正样本对照确认 `app/cli.py` 在内）已写进 `.dev/docs/server-layout/status.md`，`uv build` 一条命令即可重建。

**动作：原地弃置。**

## 组 8：提交回执（1 个）

`receipts.txt`

**长期价值：无，且已经是错的。** 它是会话中途从 transcript 收割的 17 条提交回执，**其中三条已失效**（我初版只点名了两条，第三条是评审查出的）：

| 回执 | 状态 | 失效原因 |
|---|---|---|
| `main 56da22a` | 无任何 ref 包含 | 改写事故，内容以 `2248a69` 存在 |
| `main 002d0db` | 无任何 ref 包含 | 只带了 14 个文件里 3 个的破损提交，后被 amend |
| **`main 4d6a28a`** | **无任何 ref 包含** | **amend**——它是第 5 步 `ef4defb` 的前身 |

其余 14 条（`.dev` 六条 + `main` 八条）经评审逐条核对，全部仍然可达。

**第三条最刺眼**：它的失效原因是 amend，而「**被 amend 掉的旧 SHA 仍留在转录里**」正是我自己在收割回执时点名过的两个抽取盲区之一。**盲区被点名了，审计这份回执时却没有被应用。** 这一节原本的收尾句写着「陈旧回执比没有回执更危险，因为它的形状读起来完全像是可信的」——**那句话对我自己的这份分析同样成立：一份漏了三分之一的陈旧清单，读起来和一份完整的一样。**

**`56da22a` 消失的原因不是 rebase**（本文一度这样写，与 `status.md` 当时的说法同源，都是错的）。真相是另一个会话的一次改写事故：它的脚本用 `git rev-parse HEAD` 指认「我刚才那个提交」，而在两条命令之间 `56da22a` 落了地，于是它改写的是别人的提交——CAS 顺利通过，因为传进去的 `<old>` 正是那个刚落地的提交。归档内容没丢（`git diff 56da22a 2248a69 -- src/.archived tests/.archived` 为空）。

**替代证据**：`.dev/docs/server-layout/status.md` 的六步表格与「已知的债」一节，SHA 是重新核对过的当前值，并完整记录了这次事故与那个留下来的空提交 `f7121ca`。

**这一行本身就是「陈旧回执比没有回执更危险」的实例**，因为它的形状（一列整齐的 `分支 SHA`）读起来完全像是可信的。**而我为它写的第一版解释同样整齐、同样可信、同样是错的**——这是同一天里第二次把「提交换了身份」默认归因给 rebase。

**动作：原地弃置。**

## 组 9：恢复 `28c1a7a` 原文时的中间产物（2 个）

`28c1a7a-intended.txt`（从 transcript argv 提取的原文）、`28c1a7a-actual.txt`（`git log -1 --format=%B 28c1a7a`）

**长期价值：无。** 两份的内容与它们的逐行 diff 都已逐字进入 [`.dev/docs/server-layout/reports/260822-28c1a7a-intended-message.md`](../server-layout/reports/260822-28c1a7a-intended-message.md)，`actual` 那份随时可由 git 重出，`intended` 那份的提取方法写在该报告开头。

**这一组是差集判据自己抓出来的**：它们创建于关闭前重列之后，总数判据只会说「72 变 74」，差集判据直接指出是**哪两行没人分类过**。

**动作：原地弃置。**

---

## 计数校验

**判据不是「总数相等」，是「未分类路径的差集为空」。** 这是评审改的，理由过硬：收尾过程本身还在往这个目录里写文件（每提交一次就多一个提交信息文件），用总数当门，**每落一个新文件就作废一次评审**，而作废之后最省事的修法恰好是「把 71 改成 72」——那 1 行于是没人分类、也没人评审。

判据（可机械重跑）：把 `find` 出的相对路径与八组的成员集合作差，两个方向都要为空。

**当前**：74 个文件，组 1–9 合计 74，**未分类差集为空、分类中不存在的也为空**。

**分类规则**（让新文件自动落位，不必逐个列举）：`split/` 下的一律归组 1；`dist/` 下的归组 7；文件名匹配 `msg<数字>[ab]?.txt`、`dotdev-msg<数字>.txt`、`main-msg<数字>.txt` 的归组 6（本次收尾产生的提交信息文件）；其余按上表逐个具名。

**这条判据在本次就抓到了东西**：首次枚举 66 → 关闭前重列 71 → 现在 74。中间新增的 5 个提交信息文件按规则落进组 6；最后 2 个（`28c1a7a-*.txt`）**是差集抓出来的**，另立组 9。若用总数判据，这 2 行会被一次「改数字」抹平。

## 评审结果与我的自评差在哪

初版三处自评弱点，评审的独立判断是：**两处我判错了方向，一处结论对而理由错。**

| 我的自评 | 评审的独立判断 |
|---|---|
| 组 6 那个「例外」是唯一一处替代证据与原件不等价 | **那个例外根本不存在。** `msg3.txt` 是 `1b34815` 的信息，`28c1a7a` 的完整信息从未落过盘。**而这条更正反过来带出了一个实际修复**——原文可从 transcript 的 argv 恢复，现已存档 |
| `rd.txt` 的替代请核对 | **结论成立、理由写错。** 承重的是「两端都还可达」而非「结果已在两个提交里」。评审当场重跑 `range-diff` 得到比 `rd.txt` **更准**的输出（后者对的是一条被弃的中间链） |
| 请抽查组 1 与组 3 的替代证据 | **组 1 逐项属实**（路径清单 15+8=23 与 `--stat` 精确相等）；**组 3 不成立**——「数据可再生」与组 2 自陈的「`sets.py` 已自我失效」隔十行互相拆台 |

评审另外查出三处我完全没看到的：`refs-msg2.txt` 对应一个从未存在的提交而我声称核对过、`receipts.txt` 陈旧的是**三条**（漏的那条失效原因正是我自己点名过的 amend 盲区）、`delete-manifest.json` 被误归为派生数据。

**这一节留着不删，因为它记录的是一个可复用的比率**：作者能指出自己「哪里可能有问题」（三处全部指对了位置），但**判断方向的准确率是 1/3**。自评的用处是**给评审指路**，不是替代评审。
3. 本清单**不执行删除**，所以按技能的分级标准，停止判据是「每条已发现的候选都有可定位的持久载体」，而不是「差集已证明为空」。若评审认为某一行应改为真删除，那一行的门槛就要提高到后者。

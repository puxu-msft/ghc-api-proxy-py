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

**评审状态**：⏳ 待独立评审。清单任何一行的处置发生增删改，都作废先前的评审结论，必须重过。

---

## 组 1：`split/` —— 拆分 `2afa0c4` 与文档引用重指的中间态（33 个）

`docs-msg.txt`、`docs-msg2.txt`、`docs-paths.txt`、`docstree.txt`、`idx`、`idx2`、`oldtip.txt`、`newtip.txt`、`newtip2.txt`、`curtip.txt`、`target-tree.txt`、`c1-paths.txt`、`c2-paths.txt`、`p0.txt`、`p1.txt`、`p2.txt`、`pu.txt`、`paths.txt`、`pairs.txt`、`pairs2.txt`、`m.txt`、`rd.txt`、`status-before.txt`、`status-after.txt`、`sa2.txt`、`sb2.txt`、`refactor-msg.txt`、`refs-msg.txt`、`refs-msg2.txt`、`followup-msg.txt`、`my-files.txt`、`mine.txt`、`pyright-files.txt`

**长期价值：无。** 全部是 plumbing 操作的输入与中间态：私有索引二进制（`idx`/`idx2`，共 116K）、进哪个提交的路径清单、`commit-tree` 的父子对、前后 `git status` 快照、`git range-diff` 输出（`rd.txt`）、以及各步的 tree/tip SHA。

**替代证据（逐一命名到文件级）**：

- 提交信息文件 → 对应提交**已存在且带着那条信息**，这是技能要求的解除条件：`fa0b281`（`docs-msg2.txt`）、`800eb5b`（`refactor-msg.txt`）、`598b778`（`refs-msg.txt`）、`1f29d0a`（`refs-msg2.txt`／`followup-msg.txt`）。已用 `git log -1 --format=%B` 核对过内容一致。
- 路径清单与私有索引 → 那两个提交各自的 `git show --stat`。
- tip／tree SHA → **留存分支 `a/2026-08-22-split-2afa0c4` 在 `30f251c`** 承载了改写前的原始尖端，比一个 41 字节的 SHA 文本文件更耐用（它是 ref，不会被当成垃圾清掉）。
- `status-before/after.txt`、`sa2/sb2.txt`（「我没动同伴的东西」的自检对照）→ 结论已成立且提交已落；这类快照的价值在操作当时，事后不可再用（同伴此后已多次提交）。

**动作：原地弃置。清理前置条件：无（不执行删除）。**

## 组 2：复现探针 —— **已逐字持久化**（5 个）

`reach.py`、`count.py`、`sets.py`、`importable.py`、`drop_emptied_dirs.py`

**长期价值：有，且是唯一的。** status.md 写着 106 → 83、247 → 169、77 + 48，但只写了「实测」；这 5 个脚本（合计 2.3KB）是那些数字的唯一复现手段。**这正是技能列的第一条判断错误的形状——把派生数据和产生它的脚本一起扔掉。**

**接收者**：`.dev/docs/server-layout/probes/`，随 `.dev` 提交 **`44d9859`** 落地，逐字复制未作修改。同目录 `README.md` 记录了每个探针的当前复现值、正样本对照、以及各自不能证明什么。

**持久化后已验证**：在主仓 `7525f76` 上重跑，`reach.py`+`count.py` 复现 83／25，正样本对照 `import app.server` 得 1；`importable.py` 得「169 个模块，0 失败」。`sets.py` 报 `ModuleNotFoundError: app.server.app_factory`——**它已随第 6 步自我失效，探针的失效即归档的证明**，README 给了回到 `2248a69^` 复现的方法。

**动作：逐字持久化（已完成）+ 副本原地弃置。**

## 组 3：一次性探测脚本与派生数据（11 个）

`probe_chain.py`、`A.json`、`B.json`、`sets.json`、`handler_imports.txt`、`legacy_files.txt`、`legacy_tests.txt`、`tests_only_legacy.txt`、`tests_archive.txt`、`move.txt`、`delete-manifest.json`

**长期价值：无。**

- `probe_chain.py` —— `core/chain.py` 落地前的前瞻试算。结论已经**变成** `chain.py` 本身及其 docstring，探针没有二次价值（README 已记录未保留它的理由）。
- 其余 10 个是组 2 那些脚本的输出。**脚本在，数据可再生**；而归档划分的最终形态已经是 `2248a69` 里 125 条 100% 相似度的 rename 记录，比一份中间清单更权威。

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

**长期价值：无，解除条件已满足。** 技能规定提交信息文件在「命名的提交存在且带着那条信息」之前不自动可弃。逐一对应并已核对：`28c1a7a`（`msg3.txt`）、`b973ed0`（`msg4.txt`）、`c01191f`（`msg5a.txt`）、`ef4defb`（`msg5b.txt`）、`2248a69`（`msg6.txt`）、`.dev` 的 `44d9859`／`a9e10a4`／`0cb3759`／`11a1b6a`（`dotdev-msg1`～`4`）、主仓 `af40e9b`（`main-msg1.txt`）。

**一个例外要写明**：`28c1a7a` 的提交信息**在 git 里是残缺的**（8 处反引号包裹的符号名被 shell 当命令替换吃空），而 `msg3.txt` 里是完整的。所以这一个文件的内容**并不完全等于**它对应的提交对象。已在 `.dev/docs/server-layout/status.md` §已知的债 里记录该残缺与不修的理由，教训进了记忆 `never-pass-a-commit-message-inline-to-bash`。**判断：仍然弃置**——损失的是 8 个符号名的措辞，提交内容与验证均无误，而为一条信息改写同伴正在推进的分支不成比例。

**动作：原地弃置。**

## 组 7：构建实测产物（2 个）

`dist/.gitignore`（1 B）、`dist/app-0.1.0-py3-none-any.whl`（**399K，占本目录体积的 39%**）

**长期价值：无。** 结论（wheel 174 个条目、不含 `.archived`、正样本对照确认 `app/cli.py` 在内）已写进 `.dev/docs/server-layout/status.md`，`uv build` 一条命令即可重建。

**动作：原地弃置。**

## 组 8：提交回执（1 个）

`receipts.txt`

**长期价值：无，且已经是错的。** 它是会话中途从 transcript 收割的 17 条提交回执，但其中 **`main 56da22a` 已不在任何分支上**（内容以 `2248a69` 存在），**`main 002d0db` 是那个只带了 14 个文件里 3 个、后被 amend 掉的破损提交**。

**`56da22a` 消失的原因不是 rebase**（本文一度这样写，与 `status.md` 当时的说法同源，都是错的）。真相是另一个会话的一次改写事故：它的脚本用 `git rev-parse HEAD` 指认「我刚才那个提交」，而在两条命令之间 `56da22a` 落了地，于是它改写的是别人的提交——CAS 顺利通过，因为传进去的 `<old>` 正是那个刚落地的提交。归档内容没丢（`git diff 56da22a 2248a69 -- src/.archived tests/.archived` 为空）。

**替代证据**：`.dev/docs/server-layout/status.md` 的六步表格与「已知的债」一节，SHA 是重新核对过的当前值，并完整记录了这次事故与那个留下来的空提交 `f7121ca`。

**这一行本身就是「陈旧回执比没有回执更危险」的实例**，因为它的形状（一列整齐的 `分支 SHA`）读起来完全像是可信的。**而我为它写的第一版解释同样整齐、同样可信、同样是错的**——这是同一天里第二次把「提交换了身份」默认归因给 rebase。

**动作：原地弃置。**

---

## 计数校验

33 + 5 + 11 + 6 + 3 + 10 + 2 + 1 = **71**，与关闭前重列的 `find` 结果相等。

首次枚举时是 66；那之后新写了 4 个 `.dev` 提交信息文件与 1 个主仓提交信息文件，**5 个全部回到组 6 分类**。这正是技能要求「关闭处置前立刻重列根目录，任何新路径回到分类而不是被扫进计数」的用处——**如果只是把总数从 66 改成 71，那 5 行就是没人分类过、也没人评审过的行**。

## 我自己看到的弱点

1. **组 6 那个例外（`msg3.txt` ≠ `28c1a7a` 的实际信息）是本清单里唯一一处「替代证据与原件不等价」**，我判为可弃，但这是作者自评，请评审独立判断。
2. `rd.txt`（`git range-diff` 输出，40K）我归为无长期价值，理由是拆分结果已在两个提交里。但 range-diff 记录的是**改写前后的对应关系**，而改写前的原件由留存分支承载——请核对这条替代是否真的成立。
3. 本清单**不执行删除**，所以按技能的分级标准，停止判据是「每条已发现的候选都有可定位的持久载体」，而不是「差集已证明为空」。若评审认为某一行应改为真删除，那一行的门槛就要提高到后者。

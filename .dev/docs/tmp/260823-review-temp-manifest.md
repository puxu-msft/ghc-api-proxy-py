# 评审：会话 `be410f2e` 临时状态处置清单

**评审对象**：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260823-session-closeout-temp-manifest.md`
**评审根**：`/home/xp/.claude/jobs/be410f2e/tmp`
**评审时间**：2026-08-23（`main` = `8de0d3c`，`.dev` HEAD = `0fec088`）
**VERDICT**：needs-fix

---

## 0. 三句话结论

1. **清单的分类框架、组划分与处置方向我全部认可，问题集中在「命名到文件级的替代证据」这一层。** 我把每一条替代证据都跑回了 git，**发现 6 处 major**：组 6 的第一条映射整个错位（`msg3.txt` 是 `1b34815` 的信息，而 `28c1a7a` 在 tmp 里根本没有文件）、组 1 的 `refs-msg2.txt` 对应一个从未存在的提交、`receipts.txt` 陈旧的是**三条**不是两条、组 3 的「脚本在，数据可再生」与组 2 自陈的「`sets.py` 已自我失效」直接互相矛盾、`delete-manifest.json` 被误归为可再生的派生数据、以及计数门已经失效（现在是 **72** 个文件）。
2. **对你点名的三个弱点，我的独立判断是**：组 6 那个「例外」**不存在**——真实情况比你写的更糟也更简单（`28c1a7a` 的完整信息从未落过盘，因为它正是那条内联 `-m`），但处置结论（弃置）仍然成立；`rd.txt` 的替代**成立，但理由写错了**，我实测重跑 `range-diff` 得到了比 `rd.txt` 更好的输出；组 1 的路径清单与 tip 替代**逐项属实**（15 + 8 = 23，与 `fa0b281`/`800eb5b` 的 `--stat` 精确相等），组 3 则如上不成立。
3. **我不建议把任何一行改成真删除**，理由不是「删了可惜」，而是**本次审计自身的错误率**：一份主张「差集已证明为空」的清单，其差集运算刚被我查出 6 处 major 缺陷。零删除是当前这份清单唯一能守得住的档位。**但我建议把 `delete-manifest.json` 从「弃置」升为「逐字持久化」**——理由见 §4。

**证据强度**：本报告的每一条结论都由当场执行的 git 命令支撑，**强到可据此行动**；`rd.txt` 那条我重跑了替代命令并给出了输出，属同档。唯一到不了这一档的是 §5 关于「是否该升级为删除」的建议——那是判断而非观测，我标为「倾向性，需你或第三方复核」。

---

## 1. 计数与枚举

| 项 | 清单声称 | 我实测 |
|---|---|---|
| `find "$R" \( -type f -o -type l \)` | 71 | **72** |
| 两棵临时 worktree（`pre-step0`、`at-archive`） | 已移除 | ✅ `git worktree list` 里没有，只剩主树 + 同伴四棵 + 另一会话一棵 |
| 同伴的 `.claude/worktrees/` 四棵 | 一棵都没碰 | ✅ 四棵全在（`260822-never-silent-upstream-failure`、`delivery-keepalive`、`one-ending`、`upstream-error-events`） |
| wheel 占本目录体积 | 39% | **46.3%**（399209 / 861995） |

**新增的第 72 个文件是 `dotdev-msg5.txt`**（2022 B），对应 `.dev` 提交 `0fec088`「docs: main was never rebased, and one commit changing identity is not what a rebase looks like」——即你为修正 rebase 归因而写的那条。我已验证 `dotdev-msg5.txt` 与 `0fec088` 的信息逐字相等（差异只有末尾空行）。

---

## 2. 六处 major

### M1 组 6 的第一条映射错位，而「一个例外」整段建立在这个错配上 —— **major**

清单写：「`28c1a7a`（`msg3.txt`）」，并据此写出「一个例外」：`msg3.txt` 里是完整的、git 里是残缺的。

**实测**：

```
$ diff <(git log -1 --format=%B 1b34815) msg3.txt
36d35
<                       # 只差一个末尾空行
```

`msg3.txt` 是 **`1b34815`**（第 3 步，`handler.py` 溶解）的提交信息，首行是 `refactor: dissolve the request handler into the four things it was`。而 `28c1a7a` 的真实首行是 `refactor: move what a request accumulates out of the module that routes it`。**两者毫不相干**，diff 有 56 行。

更要紧的是：

```
$ grep -rl 'move what a request accumulates' /home/xp/.claude/jobs/be410f2e/tmp
（无）
```

**`28c1a7a` 的完整信息在 tmp 里根本不存在**——这正是那次事故的定义：它是用 `git commit -m` **内联**传的，从来没有落过盘。`msg3.txt` 之所以叫 `msg3`，是因为文件名按**步号**而不是按提交顺序编的（`msg4`→第 4 步 `b973ed0`、`msg5a/5b`→第 5 步、`msg6`→第 6 步，全部核实无误），而第 2 步恰好是唯一没有文件的那一步。

**后果有两层**：

1. 清单声称「逐一对应并已核对」的十条里，第一条是错的，而**这一条正是你自评为唯一弱点、要我独立判断的那一条**。
2. `1b34815`（第 3 步，130 行提交信息的那条）**完全不在组 6 的映射表里**，于是它的解除条件从没被检查过。我替它检查了：`1b34815` 在 `main` 上可达且信息完整，解除条件满足。

**对处置的影响**：`msg3.txt` **仍然可以弃置**——`1b34815` 带着它。但「例外」那一段要整段重写，改成：**tmp 里没有任何文件承载 `28c1a7a` 的完整信息；那 8 个被吃空的符号名此刻只存在于主 transcript 里那条 `git commit -m` 的 argv 中，弃置本目录不会让它更糟，因为它从来就不在这里。** 这个说法比原文准，也更有用——它告诉后继者去哪里找，而原文告诉他去一个不存在的地方找。

### M2 `split/refs-msg2.txt` 对应一个从未存在的提交，而清单声称核对过 —— **major**

清单写：「`1f29d0a`（`refs-msg2.txt`／`followup-msg.txt`）。已用 `git log -1 --format=%B` 核对过内容一致。」

**实测**：`followup-msg.txt` 与 `1f29d0a` 相等 ✅；`refs-msg2.txt` 与 `1f29d0a` 差 **84 行**，它的首行是 `docs: point the code's citations at the documents that now hold them`——那是 **`598b778`** 的标题。但它也不等于 `598b778`（`refs-msg.txt` 才是），它是 **`598b778` 的加长改写稿**：把「eleven modules」改成「thirteen citations across twelve modules」、把「six `spec.md` and six `deferred.md`」改成「five of each」、把「31 lines」改成「26 files, 44 lines added and 43 removed」。

这就是 `15:37` 准备好、`15:39` 因同伴提交 `ea7a665` 而**永远没能 amend 上去**的那一版。**没有任何提交带着这条信息**，技能要求的解除条件（「命名的提交存在且带着那条信息」）对它不成立。

**对处置的影响**：**仍然可以弃置，但要换一条替代证据**。我核实了 `1f29d0a` 的信息第 32–36 行完整承载了那两处更正（「It says "eleven modules"; the citations were thirteen across twelve. It says `.dev/docs/` holds six … it holds five of each. The six came from a truncated listing that also counted worktree copies.」）。所以 `refs-msg2.txt` 的**独有内容为零**——但那是我查出来的，不是清单说的那条理由查出来的。清单说的理由（「已核对内容一致」）是假的。

### M3 `receipts.txt` 陈旧的是三条，不是两条 —— **major**

清单点名了 `56da22a` 与 `002d0db`。我逐条跑了可达性：

| | |
|---|---|
| `dotdev` 六条（`1197da7` `26ed922` `58663b5` `740a8b5` `bae93f8` `fea4e4a`） | 全在 `.dev` HEAD 上 ✅ |
| `main` 八条（`1b34815` `1f29d0a` `28c1a7a` `598b778` `928b355` `b973ed0` `c01191f` `c170f0f`） | 全在 `main` 上 ✅ |
| `main 002d0db` | ⚠ 无任何 ref 包含（清单已点名） |
| `main 56da22a` | ⚠ 无任何 ref 包含（清单已点名） |
| **`main 4d6a28a`** | **⚠ 无任何 ref 包含（清单未点名）** |

`4d6a28a` 是 `refactor: give the endpoints the package name the spec ratified for them`（14 文件、741+/44-），即**第 5 步 `ef4defb` 的 amend 前身**。

**为什么这条比另外两条更刺眼**：`002d0db` 与 `56da22a` 的失效原因在会话里都被显式讨论过；`4d6a28a` 的失效原因是 **amend**——而「被 amend 掉的旧 SHA 仍留在转录里」正是你在 `06:22:36` 自己点名的两个抽取盲区之一。**盲区被点名了，但审计 `receipts.txt` 时没有被应用。** 清单这一节的收尾句写着「这一行本身就是『陈旧回执比没有回执更危险』的实例，因为它的形状读起来完全像是可信的」——它对自己的分析同样成立：**一份漏了三分之一的陈旧清单，读起来和一份完整的一样。**

**对处置的影响**：不变（弃置），但那一节要补上第三条，且要点明它属于「amend 盲区」这一类。

### M4 组 3 的「脚本在，数据可再生」与组 2 的「`sets.py` 已自我失效」直接矛盾 —— **major**

组 3 写：「其余 10 个是组 2 那些脚本的输出。**脚本在，数据可再生**」。
组 2 写：「`sets.py` 报 `ModuleNotFoundError: app.server.app_factory`——**它已随第 6 步自我失效**」。

两段隔 10 行，互相拆台。我读了 `sets.py` 的源码确认：它 import `app.cli` 与 `app.server.app_factory` 两个入口取差集，而后者已被归档，所以**在当前树上它一行都跑不出来**。

受影响的是组 3 十一个里的**八个**：`A.json`、`B.json`、`sets.json`、`legacy_files.txt`、`legacy_tests.txt`、`tests_only_legacy.txt`、`tests_archive.txt`、`move.txt`——它们全部是那条差集流水线的产物。

**这不是致命的**：`probes/README.md` 已经给了正确的复现路径（`git worktree add --detach /tmp/pre-archive 2248a69^`），而我核实了 `2248a69` 在 `main` 上可达，所以那条路径今天仍然走得通。**问题在于清单没有引它**：一个只读这份清单的人会以为跑一遍脚本就行，跑完拿到一个 `ModuleNotFoundError`，然后不知道下一步。

**修法**：把组 3 那句改成「**脚本在，且 `probes/README.md` §`sets.py` 给了回到 `2248a69^` 复现的方法；在当前树上这八份数据不可再生**」。

### M5 `delete-manifest.json` 被误归为可再生的派生数据 —— **major**

组 3 把它和另外十个并列，用同一句「组 2 那些脚本的输出，脚本在，数据可再生」打发。**它不是任何脚本的输出**。我读了它的全文：它是手写的保全清单，是喂给删除护栏的那份，内容包括六个被删目录的字面路径、两条 `preserved` 声明（「46 个 .py 源文件已由 git mv 迁至 `src/.archived/app/`」「被删除的六个目录此刻只含 `__pycache__`；脚本在每次 rmtree 前断言该目录下无任何真实文件」），以及一段 `note` 说明为什么设了 `allow_unenumerated_targets`。

**三条理由让它区别于组 3 的其余十个**：

1. **无法再生。** 没有脚本产出它；重建要靠人重新回忆当时删了哪六个目录、保住了什么。
2. **它是本会话唯一一次不可逆操作的授权与保全记录。** 六个目录被 `rmtree` 掉了，这份文件是「删之前证明过什么」的全部凭据。组 2 的 `drop_emptied_dirs.py` 被逐字持久化了（它是**执行者**），而**授权书**被判弃置——这个组合很别扭。
3. **它的 `note` 承载了一条不在别处的裁决。** 而且这条裁决被记错过：会话叙事说「与其打开『允许不可枚举』的旁路开关，不如把路径写成字面量」，`delete-manifest.json` 里却明明白白写着 `"allow_unenumerated_targets": true`——**旁路是被用了的，只是同时把 targets 也逐条列了出来**。（这一条也是我上一轮报告 B25 的错误来源，我在 §6 自我更正。）

**建议改为**：逐字持久化到 `.dev/docs/server-layout/probes/`，与 `drop_emptied_dirs.py` 放在一起，`probes/README.md` 补一句说明它们是执行者与授权书的两半。**这是本报告唯一一条主张改变处置的建议。**

### M6 计数门已经失效，而它是清单唯一的机械闸门 —— **major**

清单的「计数校验」节把 `33+5+11+6+3+10+2+1 = 71` 与关闭前重列的 `find` 结果相等当作闸门，并特意写了一段说明「如果只是把总数从 66 改成 71，那 5 行就是没人分类过、也没人评审过的行」。

**实测现在是 72。** 新增 `dotdev-msg5.txt`（对应你 07:05 的 `.dev` 提交 `0fec088`）。

这不是你写清单时的疏忽——它是**在清单写完之后、评审开始之前**产生的。但正因为如此，它证明了一件对这份清单的判据更要紧的事：**「关闭前重列」这个动作的保质期短于一次评审往返。** 你自己在上一轮已经承认过同族的问题（记忆 `a-blocking-observation-has-a-shelf-life`），这里是它在**收尾清单**上的形态。

**修法建议**（我倾向前者）：

- **（a）把闸门从「总数相等」改成「不存在未分类路径」**，判据写成一条可重跑的命令——从清单里抽出全部已分类文件名，与 `find` 的输出做差集，差集为空则通过。这样新增一个文件只会让差集非空、点名它，而不会让整个闸门失效。
- （b）保留计数闸门，但把「重列」明确移到**评审回执落地之后、宣布关闭之前**，并接受它会作废前一次评审。清单第 23 行的「任何一行的处置发生增删改，都作废先前的评审结论」已经写了这个意思，只是没覆盖「行数变了」这种情况。

---

## 3. 你点名的三个弱点：我的独立判断

### 弱点 1：组 6 的例外（`msg3.txt` ≠ `28c1a7a`）

**你的判断（仍然弃置）我同意，但你给的事实是错的。** 见 M1。真实情况是：`msg3.txt` 属于 `1b34815`；`28c1a7a` 的完整信息**从未落过盘**。

所以这里根本没有「替代证据与原件不等价」这回事——**tmp 里没有那个原件**。那 8 个符号名的唯一残存载体是主 transcript 里 `git commit -m` 那条命令的 argv（我核实过：`28c1a7a` 在 git 里的信息第 11、12、14、15、18 行处能看到被吃空后留下的空位，`for ,  and`、`are ,  and ,`、`four  comments` 这样的形状）。

**证据强度：强到可据此行动**（两条 `diff` 与一次 `grep -rl` 的输出直接对上）。

### 弱点 2：`rd.txt` 的替代是否成立

**结论成立，理由要改写。** 我把它拆成两问：

**（i）`rd.txt` 记的是哪一次改写？** 它记的是**第一次**改写（`2afa0c4…30f251c` → `bbf5f50/36e303d…53dd99c`），而那条链后来又被第二次改写取代（修 F2 时序错误，得到 `fa0b281/800eb5b…1c91870`）。所以 `rd.txt` 描述的中间链**不在任何 ref 上**。

**（ii）真正该保住的对应关系还能不能拿到？** 能，而且更好。我当场重跑了：

```
$ git range-diff e7cf57a..a/2026-08-22-split-2afa0c4 e7cf57a..1c91870
1:  2afa0c4 ! 1:  fa0b281   refactor: make the delivery loop ask which client it is answering
-:  ------- > 2:  800eb5b   refactor: make the delivery loop ask which client it is answering
2:  8ce22b9 = 3:  57d5b0e   test: make the keep-alive test check the thing its comment claimed
3:  027698f = 4:  08f3c29   fix: say which clock a finished turn loses to, and pin it
4:  25432d4 = 5:  7904a2a   docs: point the deadline comment at a branch that exists
5:  30f251c = 6:  1c91870   refactor: say synthetic what, and stop naming the module after its only occupant
```

**这比 `rd.txt` 强**：`rd.txt` 把原链对到了被弃的中间链，重跑得到的是原链对**最终链**——后者才是任何人真正会问的那个对应关系。

**但清单写的理由不对。** 它写「替代是拆分结果已在两个提交里 + 留存分支承载改写前的原尖端」。**让这条成立的是后半句，不是前半句**：range-diff 需要**两端**，「结果在两个提交里」提供的是新的那一端，旧的那一端完全由留存分支 `a/2026-08-22-split-2afa0c4` @ `30f251c` 提供。**如果哪天有人清掉那个留存分支，前半句依然为真而结论立刻为假**——这正是一条替代证据最不该有的性质。

**修法**：把理由改成「**两端都仍可达（旧端 = 留存分支 @ `30f251c`，新端 = `main` 上的 `fa0b281..1c91870`），所以 `git range-diff` 随时可重跑，且重跑的结果比 `rd.txt` 更准；`rd.txt` 唯一独有的是被弃中间链的对应关系，而那条链的唯一特征（F2 的时序错句）已由 `260822-review-split-2afa0c4.md` 与处置表承载**」。同时把「留存分支不得删除」这条前置条件写进去——组 1 已经有「它是 ref，不会被当成垃圾清掉」这半句，只是没和 `rd.txt` 这行连起来。

**证据强度：强到可据此行动**（重跑输出如上）。

### 弱点 3：替代证据抽查（组 1 全判无价值、组 3 十一个派生数据）

**组 1：逐项属实，是本清单质量最高的一组。**

| 替代证据 | 我的核对 |
|---|---|
| `docs-msg2.txt` → `fa0b281` | ✅ 相等（差末尾空行） |
| `refactor-msg.txt` → `800eb5b` | ✅ 相等 |
| `refs-msg.txt` → `598b778` | ✅ 相等 |
| `followup-msg.txt` → `1f29d0a` | ✅ 相等 |
| `refs-msg2.txt` → `1f29d0a` | ❌ 见 M2 |
| 路径清单 → 两个提交的 `--stat` | ✅ **精确相等**：`docs-paths.txt` 15 行 / `c1-paths.txt` 15 行 ↔ `fa0b281` 15 files；`c2-paths.txt` 8 行 ↔ `800eb5b` 8 files；15 + 8 = 23 |
| tip／tree SHA → 留存分支 @ `30f251c` | ✅ `git rev-parse` 得 `30f251ce…`，且 `e7cf57a..留存分支` 正好是原始五条 |
| `status-before/after`、`sa2/sb2` → 「价值在操作当时，事后不可再用」 | ✅ 判断成立 |

**一处未被覆盖（minor，见 m1）**：`split/docs-msg.txt` 不在替代映射里。它对应第一次改写的中间提交 `bbf5f50`，而 `git for-each-ref --contains bbf5f50` 输出为空——**该对象不被任何 ref 包含，随时可能被 gc 掉**。内容是带 F2 错句的那一版，弃置本身无妨，但清单那句「提交信息文件 → 对应提交已存在且带着那条信息」对它**不成立**，不该被这句话覆盖过去。

**组 3：见 M4 与 M5。** 十一个里，八个的再生路径被写错（需要 `2248a69^` worktree），一个（`delete-manifest.json`）根本不是派生数据，一个（`handler_imports.txt`）也不是（它是 `handler.py` 的 import 块，替代应写成 `git show 1b34815^:src/app/server/handler.py`，我核实该路径存在）。只有 `probe_chain.py` 的理由完全站得住——我读了它，它 import 的正是 `chain.py` 今天字段类型依赖的那十个模块，「结论变成了 `chain.py` 本身」属实。

**组 2、4、5、7、8 抽查**（你没点名，我一并跑了）：

- **组 2**：`.dev/docs/server-layout/probes/` 下五个脚本全部存在且与 tmp 副本同名同职。`importable.py` 里我确认了两处质量细节——它显式 `continue` 跳过 `app.__main__` 并带注释「入口自身，import 会执行它」，而 `probes/README.md` 也写明了 `git ls-files` 看不见未跟踪文件这个盲区。**这一组的持久化做得扎实。**
- **组 4**：教训确在记忆 `repo-wide-rewrites-walk-into-peer-worktrees` 里（第 15、17、19 行），含「不要整树 checkout、逐文件核对 `non-mine-lines=0`」。三棵同伴 worktree 现状：`git worktree list` 显示四棵全在。✅
- **组 5**：`block.py` 的三个符号（`UNREADABLE`、`_extra_info`、`_readable`）**全部在 `src/app/observability/request_trace.py` 里**（去空行后 32 行差异，来自私有名转正与 import 调整，符合预期）；`handover_src.txt` 的 `_client_message_count` 对应 `hand_over.py` 的 `client_message_count`。✅ 替代成立。
- **组 7**：结论确在 `status.md:30`。✅（占比数字见 §1）
- **组 8**：见 M3。

---

## 4. 是否该把某一行改为真删除

**总体：不建议。理由不是保守，是本次审计自身的错误率。**

技能的分级是对的：零删除的停止判据是「每条候选都有可定位的持久载体」，真删除的判据是「差集已证明为空」。而我刚刚在这份清单的差集运算里查出 6 处 major——**其中三处（M1、M2、M3）恰恰是「某个东西的载体不是清单说的那个」**。一份差集运算刚被证明有 6 处缺陷的清单，没有资格支撑「差集为空」这个更强的结论。这不是循环论证：修完这 6 条之后，如果你想升级某一行，那时再重新评估是合理的。

另有一条独立理由：`$CLAUDE_JOB_DIR/tmp` 按约定就是 harness 会过期的临时区，「原地弃置」本身已经是一个终结动作。为一个会自己消失的目录承担一次不可逆操作的风险，收益是 862 KB 的磁盘——**不成比例**。

**唯一反向的一条（我主张升级，但方向是持久化不是删除）：`delete-manifest.json`，见 M5。**

**顺带一条要说清楚的**：组 4 的 `cli.peer-worktree.bak`（23536 B）是同伴工作树里文件的副本，清单说「继续留着有轻微坏处……会在将来被误读为当前状态」。这个判断我同意，但注意 `cli.base`（22248 B）与 `cli.mine`（22251 B）同样是 `cli.py` 的两份快照，**清单只点名了 `.bak` 一个**。要么三个一起说，要么都不说；单点名一个会让读者以为另外两个性质不同。（这是 minor，见 m6。）

---

## 5. 完整发现表

| # | 级别 | 发现 |
|---|---|---|
| M1 | **major** | 组 6：`msg3.txt` 是 `1b34815` 的信息不是 `28c1a7a` 的；`28c1a7a` 在 tmp 里无对应文件；`1b34815` 未进映射表。「一个例外」整段需重写 |
| M2 | **major** | 组 1：`refs-msg2.txt` 是 `598b778` 的未落地 amend 稿，无任何提交带它；清单声称「已核对内容一致」为假 |
| M3 | **major** | 组 8：陈旧回执是三条不是两条，漏了 `4d6a28a`（`ef4defb` 的 amend 前身），而 amend 盲区是作者自己点名过的 |
| M4 | **major** | 组 3 的「脚本在，数据可再生」对其中八份不成立（`sets.py` 已自我失效），与组 2 自陈直接矛盾；需引 `probes/README.md` 的 `2248a69^` 复现路径 |
| M5 | **major** | `delete-manifest.json` 不是派生数据、不可再生，且是本会话唯一一次不可逆操作的授权与保全记录；建议改为逐字持久化 |
| M6 | **major** | 计数门失效：现为 72 个文件（新增 `dotdev-msg5.txt` → `0fec088`）。建议把闸门从「总数相等」改成「未分类路径差集为空」 |
| m1 | minor | `split/docs-msg.txt` 未被替代映射覆盖；其对应的 `bbf5f50` 不被任何 ref 包含，随时可被 gc |
| m2 | minor | `handler_imports.txt` 不是组 2 脚本的输出；替代应写 `git show 1b34815^:src/app/server/handler.py`（已核实可取） |
| m3 | minor | `rd.txt` 的替代结论成立但理由写错：承重的是「两端都可达 ⇒ 可重跑」，不是「结果已在两个提交里」；且需写明「留存分支不得删除」这个前置 |
| m4 | minor | 组 5 把 `block.py` 称作「切块工具」，它实际是被搬走的源码副本；处置对，措辞不对 |
| m5 | minor | `probe_chain.py` 被弃置，但它是唯一能复现 104/81 那一组数的脚本，而 A3 的「两组数差 2」结论建立在这组数上；与组 2「脚本是那些数字的唯一复现手段」的理由不一致 |
| m6 | minor | 组 4 只点名 `cli.peer-worktree.bak` 有坏处，而 `cli.base`／`cli.mine` 同样是 `cli.py` 快照 |
| m7 | minor | wheel 占比实测 46.3%（399209 / 861995），清单写 39% |
| n1 | nit | 组 6 现在是 11 个文件不是 10 个 |
| n2 | nit | 我上一轮的 B25 是错的，见 §6 |

**合计**：blocker 0、major 6、minor 7、nit 2。

---

## 6. 我上一轮报告的一处自我更正

上一轮（`260823-nonfile-candidates-review-B.md`）我把「**有意不使用护栏的 `allow_unenumerated_targets` 旁路**」列为 B25，依据是会话叙事 `19:01:29`：「与其打开『允许不可枚举』的旁路开关，不如把路径写成字面量——那本来就是它要的东西。」

**这条不成立。** 本次我读了 `delete-manifest.json` 的实际内容：

```json
"allow_unenumerated_targets": true,
"note": "targets 在本清单里已逐条列明；allow_unenumerated_targets 仅因为护栏无法静态读取被调用的 Python 脚本内容。"
```

**旁路被用了**，只是同时把六个目标写成了字面路径。所以真实的做法是「**开旁路 + 仍然逐条列明目标**」，而不是「不开旁路」。这个做法本身是合理的（护栏读不进 Python 脚本，这是它的能力边界，不是使用者的取巧），但**它不是我写下的那句话**。

我要精确地更正**哪一条**：错的是「有意不使用旁路」这个事实断言。**没有错的是**：这件事值得作为第 6 类留档（护栏的能力边界 + 使用者的应对方式），也没有错的是我上一轮 B8 里对护栏行为边界的其余观测。这一条恰好也强化了 M5——`delete-manifest.json` 的 `note` 是这条知识**唯一的**准确载体，而会话叙事里的版本是错的、我的报告里的版本也是错的。**留着它，或把它的 `note` 蒸馏进 `probes/README.md`。**

---

## 7. 建议的处置顺序

1. **先修 M1**（组 6 的映射与「例外」段）——它是你自评的唯一弱点，而实情与自评不同，改完这段的信息量会明显上升。
2. **M3 补第三条陈旧回执**，并点明它属于「amend 盲区」这一类，与你在非文件候选清单里点名的盲区连起来。
3. **M4 + M5 重写组 3**：把八份数据的复现路径指向 `probes/README.md` 的 `2248a69^` 方法，把 `delete-manifest.json` 与 `handler_imports.txt` 移出「派生数据」，前者升为持久化。
4. **M2 换 `refs-msg2.txt` 的替代证据**（指向 `1f29d0a` 信息里承载那两处更正的第 32–36 行）。
5. **M6 改闸门形态**，我倾向「未分类路径差集为空」那条，因为它对新增文件是自愈的。
6. **m3 重写 `rd.txt` 的理由**，把「留存分支不得删除」写进前置条件。
7. m1、m2、m4、m5、m6、m7 各改一句。
8. 按清单第 23 行的自订规则，以上任何一条落地后本评审结论作废，需重过——**但我建议重过时只核被改的那几行加计数闸门**，其余部分我这次是逐条跑回 git 的，没有必要重烧一遍。

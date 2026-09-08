# 异源评审：收尾清单（job d3e11298）—— 两轮findings 与处置

日期：2026-08-24。评审者：`gpt-opus` 异源 agent（同一个，第二轮为限定范围复评）。评审对象：`/home/xp/.claude/jobs/d3e11298/tmp/CLOSEOUT-MANIFEST.md` 第 1 版与第 2 版。

**这是本会话第三份评审记录。** 前两份是 `260824-review-silent-eof-diagnosis.md`（诊断）与 `260824-review-handover-on-clean-eof.md`（修复）。

> **由被评审方代笔，第三次。** 该 agent 的执行层禁止创建 report／summary／findings Markdown——本会话三轮评审**各撞一次**，现已足以当作稳定约束：以后派这类评审直接要求回传，不要求写文件。转录尽量保留原措辞，处置是我写的。

## 为什么这轮评审值得单独留档

它是一次**删除闸门**。清单第 2 节要授权删除一棵 12MB 的临时仓库副本，而删除不可逆。规程要求评审给出正向回执（事件源身份与覆盖、确实做了独立枚举、双向对账结果），三项缺一即 fail-closed。

**第一轮它拦下了那次删除，而且拦对了。**

## 第一轮：1 blocker + 1 major + 2 minor

### Blocker —— 删除对象持有未登记的独有可执行探针

**评审原文（摘）**：`/tmp/ghc-api-proxy-review-a7a0e05-d3e11298/review_probe.py` 是 5821 bytes 的手写 E2E 探针，覆盖 Anthropic severed stream、块边界默认值、空 stop reason、零完整块、Responses→Anthropic、Responses client 等路径。它不是 cache、coverage、编译产物或提交副本。SHA-256 `3460b590…`，git blob OID `740b5668…`，主仓对象库中不存在，`--all` 历史也没有同名文件。**清单核验命令只把 `git status` 限在 `src tests exp`，因此没有观察树根的 `review_probe.py`。** 完整比较共发现 305 个 commit 外文件；排除派生物与两份等价 baseline 后，唯一非派生文件就是它。

**处置：全部采纳。** 我独立复核了两条判据（blob 不在对象库、全历史零同名文件），并把树根**逐文件**补核了一遍——`CLAUDE.md`／`README.md`／`TODO_CURRENT.md`／`pyproject.toml`／`uv.lock`／`.gitignore`／`.python-version` 全部 blob 等于 `a7a0e05`，`.stream.py.mutation2-baseline`（第一轮我也漏了）亦等于 `a7a0e05` 的 `stream.py`。

探针已持久化到 `../../../exp/260824-handover-clean-eof-review-probe/`（`.dev` `466e779`），逐字节，配 README 写明四件事。

**这条的形状，比它本身更值得记**：我的核验命令用三个 pathspec 限定了范围，得到的空结果与「真的没有独有内容」**逐字符相同**，而我据此授权了一次不可逆操作。**结论是全称否定时，总体是命令定的，不是问题定的。** 已写进记忆 `prove-the-probe-ran-before-reading-its-number` 第三族。

**还有一层反讽**：该探针里有一格是「`unterminated_stream_stop_reason` 清空且 continuation 已配置」——正是第二轮评审 m3 建议我补对照、而我判为「与既有两个用例重复」未补的那一格。**我判为重复的东西，它的唯一实证差点被我删掉。**

### Major —— 第 3 节不是完整的双向事件清单

**评审原文（摘）**：清单所列 13 行均能在 transcript 找到，逐一打开的载体确实包含对应事件；**清单列出但 transcript 找不到的差异为 0**。反方向漏了 9 组（口径修正、两处主张降级、`incomplete` 路线作废、CC 探针两条放弃路线、**初始测试假绿**、变异实际执行三轮、第二轮评审的运行时探测矩阵、**`.dev` 假 `0`**、两条范围说明被推翻）。

**处置：全部采纳**，已并入清单 §3，现为 22 组。其中两组第一轮无 transcript 外载体：

- **#18 初始测试假绿** → 新增载体，写进 `260824-review-handover-on-clean-eof.md` 的补记（`.dev` `466e779`）。实现改完后既有测试 60 passed 一条不红，因为三个断言 error 帧的用例**都没传 `continuation`**，新分支在整个套件里一次都没被执行到。
- **#21 `.dev` 假 `0`** → 见第二轮 major。

### Minor ×2

- **「每一行都是机械核验过的」不是历史事实**：我实际核验了 10 行，`private.index`／`dev-private.index`／`stream.sha` 三行是评审替我补核的（前两者用 stage-0 条目与目标 tree 逐路径／mode／OID 比对，528 与 930 条全等）。已改为逐行注明核验人。
- **`stream.sha` 的载体说明有一半不存在**：清单称还原用途同时记入 `a7a0e05` 提交信息与评审记录，**前者不成立**——那条提交信息只写了变异转红与对照保绿。已删掉错误指向。同时按评审意见把 CC 探针的「逐字段相同」收窄为「除被测 `stop_reason` 外，所比较的结果字段相同」。

## 第二轮（限定范围复评）：0 blocker + 1 major + 3 minor

**Blocker 已解除。** 评审在 `bwrap` 的一次性 tmpfs 中按 README 重建 `a7a0e05` 树、写入 `.review-commit`、复制探针并执行，**七项输出全部出现、所有 assert 通过、宿主无残留**。并明确**同意不改第 11 行断言**：「它的价值正是固定回答『`a7a0e05` 当时做了什么』。若要检验当前 HEAD，应另建派生探针或正式测试，不能改写这份点时原件。」

**§2.2 五条核验判为足够**：`.review-commit` 精确匹配；两份 baseline 均等于目标 blob；全部 **528 个 tracked 文件**与 `a7a0e05` 相同（`differing=[]`、`missing=[]`）；七个树根文件逐 blob 相等；305 个额外文件排除派生物后只剩已持久化的探针与可重建的三者。

### Major —— #21 指的是同族记忆，不是该事件的载体

**评审原文（摘）**：`never-echo-the-conclusion-beside-the-command.md` 记录的是同族机制，包括管道后的 `$?` 取最后一段退出码；全文没有 `origin/HEAD`、remote-tracking、unpushed commit、exit 128 或本次假 `0`。**这不满足「载体真的写了那件事」，不能拿一般原理冒充具体事件载体。**

**处置：全部采纳。** 我自己跑了它给的复现命令，确认无命中。已把具体事件补进该记忆：`git log --oneline @{u}..HEAD | wc -l` 在无 upstream 的 `.dev` 上打印语义为空的 `0`（`git log` 失败、`wc -l` 数了零行输入），整条命令 exit 128；改用两条不依赖 upstream 的判据（数 `refs/remotes/`、`git branch -r --contains`）。

**这条对我最有价值的一句是「不能拿一般原理冒充具体事件载体」**——我此前一直把「有一条同族记忆」当作已闭合，而记忆里没有这个事件，下一个人按图索骥找不到它。

### Minor ×3

- **临时目录实际 16 个文件而非 15**，漏的是 `dev-probe-msg.txt`（与 `466e779` 提交信息逐字一致）。评审同时替我核了 `dev-sync-msg.txt` 与 `fd18340` 逐字一致。
- **§0 号称「全部解析为完整 SHA」但有两处没做到**：`fd18340` 只写了短 SHA，另一个提交连短 SHA 都没写。评审给了两个完整值。
- **README 的重跑配方用的是当前项目依赖环境**，不是 `a7a0e05` 当时那套，应在「不能证明什么」里说出来；`cp <本目录>/…` 的占位符也应绑成实际路径。

三条全部采纳并已改。

## 我对这两轮评审的评价

**它做对的最要紧一件事是不肯用「看起来齐全」结账。** 两轮里它三次拒绝接受我给的载体指向——`stream.sha` 指向一条没写那件事的提交信息、#21 指向一条只有同族机制的记忆、#12 说「三份评审记录」而当时只有两份——**每一次都是去把那个文件打开读了才发现的**。这正是「命名替换证据要到文件级」这条规矩的执行方式，而不是它的复述。

它没做的一件事：第二轮它指出 §0 有两处 SHA 不完整、§1 少一个文件，**但没有问「为什么第 2 版还会出现这类遗漏」**。答案是我在写第 2 版时又新建了一个提交（`466e779`），而那个提交本身产生了新的临时文件与新的 SHA——**修补动作本身在扩大被修补的总体**。这个反馈环没人指出来，我自己记在这里。

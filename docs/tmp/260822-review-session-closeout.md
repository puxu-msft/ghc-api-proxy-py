# 收尾产物独立评审：证伪本会话的事实性声明

**评审人**：独立子智能体（异源）
**日期**：2026-08-22
**评审基线（全部经 `git rev-parse` 固化）**：

| ref | SHA（完整） |
|---|---|
| 主仓 `main` HEAD（评审开始时） | `8b71266cbd62ed523d0d889c20866f174cd18036` |
| 主仓 `main` HEAD（评审中途，同伴推进） | `75273e1`（13:35:16）——**HEAD 在评审期间移动过，下文凡涉及 HEAD 的判据均标注取值时刻** |
| 本会话主仓提交 | `f0527e5dfcd3ccaecc8fc8b7e971caade0ba1eb3` |
| `archive/260822-complete-not-abandon` | `1479025b019211d84ac699db8a77659988cb9690` |
| `archive/260822-finished-turn-unnamed-failure` | `223085236c6b56f585ca021e60d3ba5d176c1413` |
| `archive/260822-finished-turn-guard` | `22c7e8d3ce80f7b0eed480de9137cb743b7dbb1a` |
| `.dev` HEAD（评审开始时） | `64aeb59afea657aad7c59a7d4da1ca51e5c59f3a` |
| `.dev` 本会话 6 个提交 | `11c7df3fa4aa02cc4498ea5569cabca061d13756`、`0f7bd11e50a87c78a531faa1add8e1b91b98cfb0`、`f760078e4a66ee4a3fce40c9f9be13dd1a040fdf`、`69c12f54ea05cbf5928a197c697988887530dc7f`、`b1a883d79303f47655d941681aeedd52347583e9`、`64aeb59afea657aad7c59a7d4da1ca51e5c59f3a` |

（本文件按证据到手的顺序追加写入，节序不代表严重度排序；末尾有汇总表。）

---

## 一、逐条终态声明的复核

### 1.1 「本会话在主仓只有 `f0527e5` 一个提交，恰含 2 个文件」——**部分成立，措辞需要限定词**

`git show --stat f0527e5` 输出：

```
f0527e5dfcd3ccaecc8fc8b7e971caade0ba1eb3
Pu Xu
Sat Aug 22 13:13:34 2026 +0000
test: make the finished-turn guard prove its premise, and cover what full loses

 src/app/pipeline/retry.py                          |  1 +
 .../unit/pipeline/delivery/test_stream_delivery.py | 61 ++++++++++++++++------
 2 files changed, 47 insertions(+), 15 deletions(-)
```

**恰好 2 个文件，成立。** 但「在主仓只有一个提交」这句在字面上不成立：本会话在**同一个主仓仓库**（同一个 `.git`，同一个对象库）里至少还创建了 4 个提交，全部在 `worktree-260822-complete-not-abandon` 分支上，且全部仍然可达：

`git reflog show worktree-260822-complete-not-abandon --date=iso` 全量输出：

```
22c7e8d @{2026-08-22 13:13:19}: commit: test: make the finished-turn guard prove its premise, and cover what full loses
1743a0b @{2026-08-22 13:08:34}: reset: moving to 1743a0b
2230852 @{2026-08-22 13:07:04}: commit: fix: ask whether upstream finished before asking what the failure was
f191e4d @{2026-08-22 12:59:01}: reset: moving to f191e4d
1479025 @{2026-08-22 12:02:42}: commit: docs: say only what the terminal short-circuit proves, and where COMPLETE went
c86712d @{2026-08-22 11:47:52}: commit: fix: a reply upstream had already finished is not thrown away by the socket
4c7129a @{2026-08-22 10:48:28}: reset: moving to 4c7129a
fa628e1 @{2026-08-22 10:47:41}: branch: Created from origin/main
```

即 `c86712d`、`1479025`、`2230852`、`22c7e8d` 四个提交（作者时间 11:47～13:13，落在会话窗口 09:30:50Z 之后）。准确说法是「**本会话只有 `f0527e5` 一个提交进入 `main`**」。

**权重：够据此行动**（修正措辞）。**严重度：minor**——`.dev` 交接件 §9 的归档表其实已经把这 4 个提交都列出来了，所以是本次终态自述的措辞松，不是文档漏记。

### 1.2 「`f0527e5` 提交时索引里有同伴暂存的 15 个文件，未被卷入」——**「未被卷入」成立，「15」不可事后独立复核**

- **未被卷入**：可证。`f0527e5` 的 diff 恰好只有那 2 个文件（上引 `--stat`），而其父提交 `64bff1e` 与它之间没有第三个文件。这一点是提交对象自身的性质，与当时索引里有什么无关。
- **「15 个」**：Git 不保留历史索引快照，`.git/index` 只有当前态；`reflog` 不记录暂存。**该数字在事后无任何 ground truth 可对**。它只能由当时的命令输出支撑，而那条输出没有落进任何持久文档（`.dev` 里 grep 不到 `15 个文件` 之外的原始命令输出）。

**权重：「未被卷入」够据此行动；「15」仅存档，不可复核。** **严重度：minor**——建议在 §9 那句里把 15 标注为「当时 `git diff --cached --name-only | wc -l` 的读数，事后不可复核」，或者干脆只说「同伴暂存的文件全程未被卷入」。这一条正落在项目记忆《`git commit` 会提交整个索引》的关切上，值得写准。

### 1.3 「`22c7e8d` 的两个文件与主仓 HEAD 逐字节相同」——**成立**

blob 哈希三处一致（取值时刻：主仓 HEAD = `8b71266`）：

```
--- 22c7e8d ---
100644 blob 33b85bfea4bc733f36e46d1d805cbcd8c58ff7ce	src/app/pipeline/retry.py
100644 blob 99db3e887b8ce071e3c3fb7ff0ef59c03f68f799	tests/unit/pipeline/delivery/test_stream_delivery.py
--- HEAD (8b71266) ---
100644 blob 33b85bfea4bc733f36e46d1d805cbcd8c58ff7ce	src/app/pipeline/retry.py
100644 blob 99db3e887b8ce071e3c3fb7ff0ef59c03f68f799	tests/unit/pipeline/delivery/test_stream_delivery.py
--- f0527e5 ---
（同上两行，逐字节相同）
```

**权重：够据此行动。** 需要注意的**保质期**：评审期间 `main` 已前进到 `75273e1`（13:35:16，`fix: stop the Responses framer answering with words the protocol does not have`），该提交是否触碰这两个文件本评审未再复核——「与当前 HEAD 相同」这句话本身随同伴提交而过期，交接件若要留这句，应当锚到 `f0527e5` 而不是「当前 HEAD」。

### 1.4 `c86712d` 可达性：**本会话的更正是对的，原始断言为假**——但更正本身少了一句更强的话

逐 ref 复核（73 个 ref 全扫），带正样本对照：

```
=== c86712d exists? ===  commit
=== which refs contain c86712d ===
REACHABLE_FROM: refs/heads/archive/260822-complete-not-abandon
=== positive control ===  CTRL_OK(f0527e5 in main)
=== ref 总数 ===  73
```

`c86712d` 可达，且**恰好只从这一个 ref 可达**。所以 `deferred.md` 第 12 条的更正（「该断言不成立」）**是对的**，被更正的原话（「不被任何 ref 引用的对象」）**是假的**。

**这条断言是谁写的、什么时候写的——我第一版查错了，改正在此。** 我起初按 `.dev` 提交 `f760078`（12:01:15，本会话）落笔，认定是本会话自己写的。逐提交 diff 后不成立：

- `f760078`（**本会话**，12:01:15）写的是干净的「由 `c86712d` 引入的 `if assembler.terminal.seen: break` 带出」，**没有那句假话**。
- `2aa0cad`（**同伴**，13:03:58，提交信息 `docs: register the three minors that are not worth fixing yet, and correct one attribution`）才把它插进去，第 11、12 两条各一份：

```diff
-来源：……。由 `c86712d` 引入的 `if assembler.terminal.seen: break` 带出。
+来源：……。由 `bce8b0d` 引入（原始来源 `c86712d` 是一个不被任何 ref 引用的对象，`main` 上承载同一语义的是前者）的 `if assembler.terminal.seen: break` 带出。
```

所以**本会话在第 12 条里把它记成「同伴插的」是对的**（会话记录第 1891 条 13:30:18 原话：「同伴在第 12 条标题里插了一句错的」）。我上一版把它归给本会话，是我自己犯了《归因写下前先核 `--stat`》那条——**这条更正本身就是那条记忆的第 5 个样本，而且是我作为独立评审者犯的**。

完整时间线（`git reflog` + 逐提交 diff，全部一手）：

| 时刻 | 事件 | 谁 |
|---|---|---|
| 10:47:41 | 分支 `worktree-260822-complete-not-abandon` 由 `origin/main` 创建 | 本会话 |
| 11:47:52 | `c86712d` 提交在该分支上（该分支当时的 tip 就是它） | 本会话 |
| 12:01:15 | `f760078` 登记第 11、12 条，写「由 `c86712d` 引入」 | 本会话 |
| 12:58:55 | `archive/260822-complete-not-abandon` 由 `1479025` 创建，`c86712d` 成为其祖先 | 本会话 |
| 12:59:01 | 分支 reset 到 `f191e4d`，`c86712d` 离开活分支——但归档已经接住 | 本会话 |
| **13:03:58** | `2aa0cad` 插入「`c86712d` 是一个不被任何 ref 引用的对象」 | **同伴** |
| 13:31:26 | `64aeb59` 更正第 12 条 | 本会话 |

**关键点：13:03:58 写下时 `c86712d` 已经被 `archive/260822-complete-not-abandon` 接住了（12:58:55 建的）**，所以那句断言在写下的那一刻就是假的，不是后来才变假的。同伴那句话的源头是其报告 `docs/upstream/retry-and-continuation/reports/260822-review-unreviewed-span.md:212`，判据写的是「`git log --oneline --all` 无命中」——而 `--all` 本就覆盖 `refs/heads/archive/*`，所以那次检查要么跑在别的树上，要么命中判据（对缩写哈希做文本匹配）失效了。**这一点我只能指出判据可疑，无法复现当时的执行环境，权重：倾向，不足以据此改写那份报告**（何况报告原件按规矩不改）。

**对第 12 条的具体建议**：把「2026-08-22 收尾时逐 ref 复核」改成「该断言由 `2aa0cad`（同伴，13:03:58）写入，而 `archive/260822-complete-not-abandon` 早在 12:58:55 就已建立，故写下时即为假」。现在的措辞没说是谁写的、也没说它从一开始就假，读者会以为是「归档改变了事实」。**严重度：minor（措辞）。权重：够据此行动。**

### 1.5 工作树已移除、分支保留——**成立**

```
=== .claude/worktrees 目录 ===
delivery-keepalive
upstream-error-events
=== 目标路径 ===  ABSENT
=== 正样本对照 ===  CTRL_EXISTS(delivery-keepalive)
=== .git/worktrees 管理目录 ===  delivery-keepalive  review  upstream-error-events
=== git branch --merged main --list 'worktree-260822*' ===  （空）
=== 分支 tip ===  22c7e8d3ce80f7b0eed480de9137cb743b7dbb1a
```

工作树目录与 `.git/worktrees/` 下的管理目录都已清除（即 `prune` 也做了），正样本对照证明 `test -e` 判据有效。分支 `worktree-260822-complete-not-abandon` 仍在，tip = `22c7e8d`，与 `archive/260822-finished-turn-guard` 同点。

`git branch -d` 拒绝的机理也复核过：该分支**不在** `git branch --merged main` 里（`22c7e8d` 不是 `main` 的祖先——它的内容经 `f0527e5` **重新提交**进 main，`-d` 判的是可达性不是内容），所以 `-d` 必然拒绝，未用 `-D` 是正确处置。

**权重：够据此行动。**

### 1.6 `$CLAUDE_JOB_DIR/tmp` 为空——~~成立~~ **这一节的结论是错的，见 1.6bis**

```
--- ls -la .../e5003c51/tmp/ ---
total 8
drwxr-xr-x 2 xp xp 4096 Aug 22 09:30 .
drwxr-xr-x 3 xp xp 4096 Aug 22 13:35 ..
--- fd --hidden --no-ignore（含隐藏与被忽略项）---  0
--- 正样本对照：同一条 fd 命令跑在 /home/xp/.claude/jobs ---  547235
```

0 个文件，且正样本对照证明该 `fd` 调用确实在数东西（同参数在父目录得到 547235 条）。

> **⚠️ 上面这段读数是错的，我留着它是为了让错法可见。** 它跑在 2026-08-22 13:35 前后，而本会话在 **13:37:36** 才写入 `DISPOSITION.md`。重跑见下一节。

### 1.6bis 【major】`$CLAUDE_JOB_DIR/tmp` **不为空**，终态是 1 个文件

```
now=2026-08-22T13:41:48Z
total 12
drwxr-xr-x 2 xp xp 4096 2026-08-22 13:37:36.840949881 +0000 .
drwxr-xr-x 3 xp xp 4096 2026-08-22 13:37:48.503358028 +0000 ..
-rw-r--r-- 1 xp xp 2226 2026-08-22 13:37:36.835983327 +0000 DISPOSITION.md
--- fd --hidden --no-ignore | wc -l ---   1
--- find ( -type f -o -type l ) | wc -l ---   1
```

会话记录第 2123 条（`2026-08-22T13:37:36.715Z`，工具 `Write`）就是这次写入，工具返回 `File created successfully at: /home/xp/.claude/jobs/e5003c51/tmp/DISPOSITION.md`。

**所以终态声明「为空，0 个文件」为假。** 而且这不是一个纯粹的口误——那份 `DISPOSITION.md` 的正文写着：

> **population = 0。本会话从未在此目录创建过任何文件。**

这句话在被写下的那一瞬间自我证伪：写它这个动作本身就是「本会话在此目录创建文件」。文中随后那句「这份标记存在，是为了让『空目录』与『没人清点过的目录』可区分」说明作者知道自己在放一个文件进去，但正文的绝对句式没有跟着改。**修法极小**：把 `population = 0` 改成「除本标记外 population = 0（本标记写于 13:37:36）」，并把交接侧的终态声明改成「1 个文件，即处置标记本身」。

**我自己也在这里翻了一次同样的车，一并记下来**：我第一次的 `ls` + `fd` 都跑对了、正样本对照也过了，数字仍然是错的——因为**被观测的对象在观测之后才改变**。项目记忆《先证明探针真的跑了，再读它的数字》记的是四种「探针没真跑」的形态，这是第五种：**探针真跑了、数也真，但快照时刻早于终态**。对一个仍在推进的会话做终态盘点时，时刻戳必须和被盘点的动作对齐。**权重：够据此行动（两处文字都要改）。**

---

### 1.7 「本会话引用的 7 份文档全部已进入 `.dev` 历史」——**成立**

会话第 1863 条自查的就是这 7 份。我在 `.dev` HEAD = `460998b69cbe5a4d406047f63550d46c0eb9ff03`（评审后期取值，HEAD 又前进了）上独立复跑：

```
IN_HISTORY  docs/tmp/260822-h2-streamreset-cancel-diagnosis.md
IN_HISTORY  docs/tmp/260822-review-streamreset-diagnosis-gpt.md
IN_HISTORY  docs/tmp/260822-review-streamreset-diagnosis-opus.md
IN_HISTORY  docs/tmp/260822-review-complete-fix-gpt.md
IN_HISTORY  docs/tmp/260822-review-complete-fix-opus.md
IN_HISTORY  docs/tmp/260822-p2-complete-fix-handover.md
IN_HISTORY  docs/upstream/retry-and-continuation/deferred.md
--- 负样本对照（不存在的路径）---        CTRL_OK(not found)
--- 正样本对照（未跟踪的本报告文件）--- CTRL_OK(untracked file correctly absent from HEAD)
```

两个对照都到位：`git cat-file -e` 确实会对不在 HEAD 的路径报失败（用一个真实但未跟踪的文件验证），所以 7 个 `IN_HISTORY` 是真读数而非恒真。**权重：够据此行动。**

**一处要提醒**：`deferred.md` 虽在历史里，但工作树版本与 HEAD 版本**不同**（见 §2.1 的时效说明）。「在历史里」与「历史里的那一版就是你说的那一版」是两个命题，交接件只证了前者。

---

## 二、`deferred.md` 第 11／12／19 条

### 2.1 【major】第 11 条仍然携带被第 12 条判为假的那句话

`.dev` HEAD（`64aeb59`，及其后的 `1fb2341`，后者未动此文件）：

```
HEAD:docs/upstream/retry-and-continuation/deferred.md:107:
来源：`../../tmp/260822-review-complete-fix-opus.md` 问题 2（异源评审，8 个受控变异）。由 `bce8b0d` 引入（原始来源 `c86712d` 是一个不被任何 ref 引用的对象，`main` 上承载同一语义的是前者）的 `if assembler.terminal.seen: break` 带出。

HEAD:docs/upstream/retry-and-continuation/deferred.md:119:
……标题一度写着「原始来源 `c86712d` 是一个不被任何 ref 引用的对象」。**该断言不成立**……
```

**同一份文件里，第 119 行宣布某句话为假，第 107 行原封不动地留着那句话。** 这是本次评审最实的一处缺陷：更正只做在被点名的那一条上，没有在文件里搜一遍同一句话的其他落点。命令代价是一次 `git grep '不被任何 ref'`——本评审就是这么找到的。

同一次 grep 还命中 `docs/upstream/retry-and-continuation/reports/260822-review-unreviewed-span.md:212`，那里同样写着这句话。**那一处不该改**：报告原件是点时记录，项目规矩明写「留档报告不要动」。所以正确的处置面恰好是一处——`deferred.md:107`。

**证据等级：确凿（逐字引自 HEAD 的 blob）。权重：够据此行动。**

**一条时效说明，必须一并读**：主工作树 `.dev` 里此刻有**未提交**的 `deferred.md` 改写（同伴或本会话在评审开始后所为），它把第 11 条整条重写为「已裁决」，并且**顺带删掉了那句假话**（新文字：「由 `bce8b0d` 引入的 `if assembler.terminal.seen: break` 带出」）。所以：**提交态有缺陷，工作树态已修但未提交。** 按项目记忆《查残留要 grep 提交态，不是工作树》，这正是「工作树能凭空洗白」的形态，我按提交态判 major，并提请注意这条修正尚未落进历史。

### 2.2 【成立】第 12 条的更正方向正确

见 §1.4。补一句本条自身的文字问题：更正段说「2026-08-22 收尾时逐 ref 复核……该断言不成立」，读起来像是「归档使它变得可达」。实际是**写下的那一刻就已经可达**（当时它就是活分支的 tip）。建议把这半句改成「该断言在写下时即为假：`c86712d` 当时正是分支 `worktree-260822-complete-not-abandon` 的 tip」，因为这才是可复用的教训。**严重度：minor（措辞），权重：够据此行动。**

### 2.3 第 19 条：三个数字**都对**，但两处推理有问题

先给数（全部自数，含 `-uuu` 穷尽扫描 + 正样本对照，`__pycache__` 已识别并排除）：

| 声明 | 实测 | 判定 |
|---|---|---|
| `code="incomplete_responses_stream"` 被 **2 处测试断言** | `tests/unit/pipeline/delivery/test_openai_responses_format.py:310` → `assert payload["code"] == "incomplete_responses_stream"`；`tests/unit/pipeline/delivery/test_stream_delivery.py:310` → `assert "incomplete_responses_stream" in body`。同文件 `:304` 的同名字面是**构造入参**不是断言，正确地没被计入 | **成立，恰好 2** |
| 被 `../../delivery-keepalive/spec.md` **逐字复述** | `.dev/docs/delivery-keepalive/spec.md:50` 命中该字面（相对路径从 `docs/upstream/retry-and-continuation/` 解析正确）。另有 `delivery-keepalive/status.md:69`、`anthropic-responses-bridge/implementation.md:267` 等多处复述，本条只点名 spec，不构成错 | **成立** |
| `message` 字面 **零断言** | 全仓 `-uuu` 扫描，测试里唯一一处是 `test_openai_responses_format.py:303` 的**构造入参**；该测试断言的是 `payload["message"].startswith("api_error: ")`，不含该字面。改 `stream.py` 的 message 不会打红任何测试 | **成立** |

**【major】但「零消费，可以改」把代价算低了。** 同一句字面在生产代码里有**第二个产出点**：

```
src/app/delivery/responses_anthropic_stream.py:349:            "Responses stream ended before a successful terminal event",
```

而第 19 条所指的那处，紧挨着的注释（`src/app/pipeline/delivery/stream.py:392`）把这件事写成了**有意为之的契约**：

> Ported from the legacy chain rather than redesigned, as `implementation.md` directs: `app/delivery/responses_anthropic_stream.py`, on `not frontier.terminal_accepted`, raises `incomplete_responses_stream` and renders an SSE error. **Same code, same wire shape, same message**, same gate on the message having started — a client that already learned to read one of these does not have to learn a second.

legacy 链路**仍然接线**（`src/app/routes/anthropic.py:12` import 它，`tests/int/test_anthropic_responses_stream_route.py:17` 也在测它）。所以真实代价不是零，而是「要么两处一起改，要么同时修订这条注释并说明为什么两条链路从此说不同的话」。第 19 条的读者是将来做这次裁决的人，把代价写成零会让他少做一步。**证据等级：代码事实，确凿。权重：够据此行动（改文档，不改码）。**

**【major】「两条腿共用」的**理由**用错了轴。** 第 19 条写的是：

> 而 `_deliver` 是**两条腿共用**的——`framing` 由调用方给，`AnthropicFramer` 与 Responses 侧走同一段代码。

但本仓的两条选择轴是分开的，而且代码里专门写了注释防止把它们搞混：

- `framer_for`（`src/app/server/handler.py:571-598`）选的是**客户端腿**：注释原文「Selected on `route.inbound_format` — the protocol the client asked in — and **deliberately not** on `dialect_for`, which answers which upstream replied」。
- `assembler_for`（`handler.py:609-616`）选的是**上游腿**，经由 `dialect_for`。
- `src/app/pipeline/delivery/framing.py:5` 更是直说「Getting that backwards is **the specific mistake this type exists to make hard**」。

而第 19 条的结论说的是「一次走 Anthropic **上游**腿的截断」。用 framer（客户端轴）去论证上游轴的共用，是不成立的推理——**结论恰好为真**（两个 assembler 确实汇入同一个 `_deliver`，`_deliver` 签名 `stream.py:249-259` 收 `assembler: BlockAssembler` 与 `framer: OutboundFramer`，那条 error 帧不看 assembler 是哪个），但理由为假。

更值得注意的是这是一次**退步**：同一事实在 `.dev/docs/tmp/260821-plan-g1-upstream-error-events.md:215` 与 `.dev/docs/tmp/260821-truncated-anthropic-stream-diagnosis.md:63` 里的论证都是**对的**——「assembler 按 dialect 分流，随后共用同一个 `stream_delivery`」。第 19 条把一个正确的理由替换成了代码专门警示的那个错误方向。建议照抄旧论证。**证据等级：代码事实 + 代码注释，确凿。权重：够据此行动。**

（第 19 条引的 `../../tmp/260822-h2-streamreset-cancel-diagnosis.md` §1.2 存在且内容对得上：该文 44-47 行以 `REASONING_WORD` + `dialect_for` + `assembler_for` 三处论证「这次走的是 Anthropic 上游腿」。这一处引用**成立**。）

---

## 三、交接件 `docs/tmp/260822-p2-complete-fix-handover.md` §9「集成结局」

先说成立的部分，逐条都跑过命令：

| §9 的声明 | 复核 | 判定 |
|---|---|---|
| `1743a0b` 提交信息原文「A peer's review of the previous fix found it one door short」 | `git log -1 --format=%B 1743a0b` 首段第一句逐字相同 | **成立** |
| 落盘前两文件「在 `1743a0b..64bff1e` 之间无变化」 | `git diff --stat 1743a0b..64bff1e -- <2 files>` → 空；**正样本对照**：同区间全量 `--stat` 为 14 files changed，证明该 diff 命令确实在比 | **成立** |
| 归档 `1479025`「第一版，基线 `4c7129a`」 | `1479025^ = c86712d`，`c86712d^ = 4c7129a` | **成立** |
| 归档 `2230852`「第二版，基线 `f191e4d`」 | `2230852^ = f191e4d` | **成立** |
| 归档 `22c7e8d`「第三版，即 `f0527e5` 的已评审源」 | `22c7e8d^ = 1743a0b`；blob 与 `f0527e5` 逐字节相同（§1.3） | **成立** |
| 「语义早已在 main（经同伴之手）」 | 主仓当前 `stream.py:318` 有 `if assembler.terminal.seen:`，且 `:311` 的注释记着 2026-08-22 的次序裁决 | **成立** |
| 门禁数字 468 / 115 | 已锚在「`f0527e5` 之后，主树」，属点时读数。当前工作树 `--collect-only` 为 485 / 126（主树此后有 `a2169de`、`8b71266`、`75273e1` 及同伴未提交改动），**差异由树前进解释，不构成证伪**，也无法再复现 | **不可复核，但写法正确**（数字带了锚点） |

### 3.1 【major】§9 自称「本文最终状态」，却写着一句已经不成立的话

第 144 行：

```
工作树 `.claude/worktrees/260822-complete-not-abandon` 保留。
```

实测该工作树**已移除**（§1.5：目录 ABSENT，正样本对照通过；`.git/worktrees/` 下的管理目录也已清掉）。同一份文件的抬头第 5 行还写着「**（保留，未删）**」。

§9 的开头自我声明「本节是本文最终状态」——一个自称终态的小节记着与终态相反的事实，是这份交接件最容易误导后来者的一处：读者据此会去找一棵不存在的树。

**同时缺一句**：分支 `worktree-260822-complete-not-abandon` 实际被**保留**了（`git branch -d` 拒绝，未用 `-D`），§9 的「归档」小节只列了三个 `archive/*` ref，完全没提这个分支还在。于是终态里有一个活分支没有任何文档承认它存在，而它恰好与 `archive/260822-finished-turn-guard` 同点（`22c7e8d`），将来清理的人会不知道它是残留还是有意保留。

**修法**（两句话）：把第 144 行改成「工作树已移除（`git worktree remove` + prune）；分支 `worktree-260822-complete-not-abandon` 保留在 `22c7e8d`，因 `git branch -d` 判其未合入 `main` 而拒绝，未用 `-D` 强删——其内容已由 `f0527e5` 重新提交进 `main`，也已由 `archive/260822-finished-turn-guard` 承接，可安全删除。」并把抬头第 5 行的「保留，未删」改掉。**证据等级：实测，确凿。权重：够据此行动。**

### 3.2 【minor】「同伴暂存的 15 个文件」这个数字事后不可复核

见 §1.2。§9 第 148 行把它写成了与「未被卷入（提交后复核为恰好 2 个文件）」并列的事实，但两者的可复核性完全不同：后者是提交对象自身的性质，永久可查；前者是当时 `.git/index` 的一个瞬时读数，Git 不留快照、reflog 也不记暂存。建议给它加一句来源（当时跑的是哪条命令），否则后来者若去复核会一无所获，而文档没告诉他这是正常的。

### 3.3 §9 未记的一件事：`2230852` 是被 `git reset` 丢弃的，不是被合并的

reflog（§1.1）显示 13:07:04 提交 `2230852` 后，13:08:34 分支直接 `reset` 到同伴的 `1743a0b`。§9 的表格把 `2230852` 记成「第二版，未合并，语义已由 `bce8b0d`+`1743a0b` 覆盖」——**结论对**，但没说这个版本是**在发现同伴已经落地同一语义之后被主动放弃**的。归档 ref 保住了它，所以不是数据风险；但「为什么第二版存在又不用」是这段历史里最容易被后来者误读的一步（会以为是被 rebase 掉的意外）。**严重度：minor，权重：倾向（可加一句，不加也不致误）。**

---

## 四、本会话可能遗漏的东西（先自行枚举，再与已落盘载体对账）

方法：读完主会话记录 2129 条（124 个 assistant 文本块全量扫过）与 4 个子智能体记录的元信息，先列出「值得留存的结论」候选，再逐条去 `.dev/docs/` 与项目记忆里找载体。**每一次「没找到」都先跑正样本对照**（同一条 `rg` 用一个确定存在的串在同一批路径上跑，确认命令在工作）。

### 4.1 我找到、而本会话没有落进任何持久载体的

#### O1【major】「续写没接手时的 ending」这个改名，以及**被更正过的三格清单**

会话记录第 844 条（11:22:33）里有一段结论，是回答用户「续写会不会失败」时得出的：

> **合成本身不会失败。** 它是纯本地构造：读客户端请求 `messages` 的长度、拼一个 `tool_use` 块、走已有的 `block_frames` + `terminal_frames`，**不发任何上游请求**。……
> **所以我的结论是：不淘汰，但触发条件要改写——它不是「续写失败的兜底」，而是「续写没接手时的 ending」。这个区别不是措辞：写成「续写失败」会让人去实现一个永远不触发的分支。**

对账结果（正样本对照：`rg -c -F '合成' docs/tmp/260822-h2-streamreset-cancel-diagnosis.md` → 6，命令有效）：

```
rg -n -F -e '续写没接手' -e '续写失败的兜底' -e '不适用是常态' -- docs/    exit=1（零命中）
rg -n -F -e '合成本身不会失败' -e '纯本地构造' -e '不发任何上游请求' -- docs/    exit=1（零命中）
rg -n -F -e '一个完整块都没交付' -- docs/    exit=1（零命中）
```

**而文档里留着的是被这段结论取代的旧版本。** `docs/tmp/260822-h2-streamreset-cancel-diagnosis.md:150` 写的三格是：

> 适用于 MCP 机制覆盖不到的位置（非 anthropic-messages 客户端请求、不可继续的失败类别、以及**合成本身失败时**）。

与会话后来的三格逐格比对：

| 旧（在文档里） | 新（只在会话记录里） | 差异 |
|---|---|---|
| 非 anthropic-messages 客户端请求 | 同 | 一致 |
| 不可继续的失败类别 | 同 | 一致 |
| **合成本身失败时** | —— | **被证否后删除**：合成是纯本地构造，且用户已把「客户端请求里没有该工具定义」那格裁成「仍照样返回」 |
| —— | **一个完整块都没交付过 + 重放预算耗尽（`max_total=20`）或 `reopen()` 自己失败** | **新增，文档里完全没有** |

**为什么这条要紧**：留在文档里的那一格会让实现者去写一个基本不触发的分支（「合成失败兜底」），同时漏掉一个真会发生的位置（零块交付 + 重试耗尽）。这不是补充，是**更正**——而更正只活在会话记录里。

**建议载体**：`deferred.md` 第 5 条（「已交付之后的两条失败路径行为不一致」，正是这一片）或 `h2-streamreset-cancel-diagnosis.md` §3.1 就地更正并注明「原三格已被 2026-08-22 的分析更正」。**证据等级：会话记录原文 + 零命中（带正样本对照）。权重：够据此行动。**

#### O2【major】交接件 §7 给同伴的**硬要求**从未被复核闭环

§7 第 91 行写着：

> **唯一的硬要求是：这一支必须在 `_hand_over` 之前。**

§9 自称「本文最终状态」，却没有一句话说这条硬要求在合入后到底满足没有。我替它测了——**满足**：

- `src/app/pipeline/delivery/stream.py:318` → `if assembler.terminal.seen: break`
- 同函数 `:352` 一带 → `handed_over = _hand_over(continuation, session, assembler, framer, error=torn)`

`break` 在前，`_hand_over` 在后，且 `:341` 的 `if verdict.ending is StreamEnding.COMPLETE: break` 也在 `_hand_over` 之前，注释原文「a branch that silently fell through to the hand-over is what turned a finished turn into a synthesised interruption in the first place」——正是 §7 警告的那个形态，同伴显然读到了。

**一份交接件对下一棒提出硬要求，却不在终态里说它兑现没有，等于把验证成本推给了下一个读者**，而这次验证只花两条 `rg`。**证据等级：代码事实，确凿。权重：够据此行动（在 §9 补一行即可）。**

#### O3【minor】`deferred.md` 的编号在 12 之后直接跳到 15

```
### 11 …  ### 12 …  ### 15 …  ### 16 …  ### 17 …  ### 18 …  ### 19 …
```

13、14 是空号（同伴的 `2aa0cad` 一次插了重复的 `### 12/13/14`，`985f1d9` 重编号后留下的缺口）。会话记录第 1915 条（13:30:44）明确说「我不动它，避免和正在编辑的人撞车，**只在报告里提一句**」——但检索三份本会话报告，没有任何一处提到它。**空号会被读成「这两条被删了」**，而实际上从来没有过。成本是一行注脚。**权重：够据此行动。**

#### O4【minor】`git stash` 的条目是**仓库级共享**的（跨 worktree）

会话记录第 759 条（10:51:53）：在隔离工作树里做变异检验时用了 `git stash`，`stash pop` 被拒，随后意识到「`git stash` 的条目是仓库级共享的，同伴在主树也能看到」，于是先确认内容是自己的那 7 行再丢弃。

项目记忆 `git-commit-takes-the-whole-index.md` 现有的一句只写了「绝不做……**无 pathspec 的 `git stash`**」，说的是「别把别人的东西 stash 走」；**没有写「stash 条目本身跨 worktree 共享、隔离工作树并不隔离它」**。后者才是这次踩到的机制，而且它直接推翻「我在隔离树里，怎么折腾都不外溢」这个很自然的假设。

`.dev/docs/` 里也没有（正样本对照有效）：`rg -n -F -e 'refs/stash' -- docs/` 只命中三份历史报告的「没做过 `git stash`」自述，无一条描述这个机制。**权重：倾向（补进那条既有记忆的一句话，不必新建）。**

#### O5【minor】`my-skills:coordinating-a-shared-git-worktree` 在这台机器上没有安装

会话记录第 558 条（10:46:55）：「协作技能在这台机器上没安装」，于是改走隔离工作树。

这条是环境事实，而项目里**至少两份文档把这个技能当成现成载体在引用**：

```
docs/tmp/260821-shared-index-left-reverting-head.md:71: 同类纪律的完整版在 skill `git-preference:coordinating-a-shared-git-worktree`……
docs/tui/archive-count-tokens-line/reports/260820-closeout-count-tokens-log-line.md:131: ……共享树提交纪律已有 `git-preference:coordinating-a-shared-git-worktree`……再造一个只会是同义词。
```

（注意两处引的是 `git-preference:` 前缀，会话记录里说的是 `my-skills:`——**前缀不同，可能根本是两个东西**，我无法在此判定，这正是它值得报给用户的原因。）

后来者按这些文档去取那个技能会取不到，而「已有覆盖，不必新建」这条结论正建立在它可用之上。**这是用户的环境，处置权不在我，也不在本会话**——建议只是把这条事实报给用户。**权重：倾向（报告即可，不要自行安装或自行改文档结论）。**

#### O6【minor】同伴关于 G1 的分层拆解主张，只经本会话转述过一次

会话记录第 665 条（10:49:24）转述了同伴的意见：G1 按层拆——`assembler.py` 那 65 行纯新增零冲突（`_read_terminal` 逐字未动），保留并优先合入；`stream.py` / `pipeline_app.py` 的交付侧改动**作废重写**；`request_log.py` 的 `upstream_error` 字段保留。

检索（正样本对照有效）：`rg -n -F -e '按层拆' -e '交付侧作废重写' -- docs/` → `exit=1`，零命中。

这是关于活分支 `fix/upstream-error-events` 的处置意见。它是同伴自己的知识，**我无法证明他没有另外记下来**，所以这条的权重只到「提醒」：本会话是我能看到的唯一转述点，若同伴那边也没记，它就没了。**权重：仅存档 / 提醒，不足以据此要求本会话补写。**

#### O7【minor】第二版 `2230852` 为什么被放弃

见 §3.3。

#### O8【倾向】「天然变异」这个观察

会话记录第 1494 条（13:02:20）：「**变异检验是天然的**——我先在未改动的 main 上跑出了红，这比人造变异更强。」

这确实比人造变异强一个档：人造变异证明的是「测试能咬住我构造的这个坏法」，而在**缺陷仍然存在的真实基线**上跑出红，证明的是「测试能咬住真实存在过的那个缺陷」，中间不经过任何构造假设。项目记忆 `what-a-mutation-result-does-and-does-not-prove.md` 今天未被改动，讲的是变异结果的边界，没有这一面。

**但这条只有一个样本，而且它成立有前提**（要求缺陷基线仍可获得且可运行——本次是因为同伴的 `1743a0b` 尚未合入时 main 上洞还在）。**权重：倾向，值得记一条但不急；不构成本会话的失职。**

### 4.2 本会话记了、我逐条去找依据的结果

`DISPOSITION.md`（那份处置标记）列了一张「持久载体」表，我逐行核：

| 它的声明 | 我的核对 | 判定 |
|---|---|---|
| 生产代码与测试 → 主仓 `f0527e5`（2 文件） | `git show --stat` 恰好 2 文件 | ✓ |
| 诊断与评审报告（5 份）→ `.dev` `11c7df3`/`0f7bd11`/`f760078` | 5 份 `docs/tmp/260822-*.md` 全部 `git cat-file -e HEAD:` 通过（§1.7） | ✓ |
| 结论与待裁项 → `deferred.md` 第 7、11、12、19 条 | 四条都在 HEAD 里；但第 11 条带着一句已被判假的话（§2.1），第 19 条两处推理有问题（§2.3） | ✓ 存在，**内容有缺陷** |
| 交接记录 → `260822-p2-complete-fix-handover.md` | 在历史里；§9 有一句与终态相反（§3.1） | ✓ 存在，**内容有缺陷** |
| 活文档更正 → `.dev` `1fb2341` | `1fb2341 docs: 更正两处活文档里「decide_stream_ending 无人调用」的过期说法`，改 `h2-goaway/deferred.md` + `retry-and-continuation/status.md` 共 4 行 | ✓ |
| 三个 `archive/*` ref | 三个都在，SHA 与声称一致，父提交关系全部核过（§三 表） | ✓ |
| 可复用教训 → 记忆 `locating-a-version-by-line-numbers.md`、`a-fixture-helper-can-encode-the-bug.md`，以及对 `never-echo-the-conclusion-beside-the-command.md` 的补写 | 前两份 front-matter 的 `originSessionId` 都是 `e5003c51-…`（本会话）；第三份尾部确有 2026-08-22 新增小节，内容正是 `/proc/*/cwd` 那次假阳性 | ✓ |
| 「本会话从未在 `$CLAUDE_JOB_DIR/tmp` 创建过任何文件 / population = 0」 | **假**，见 §1.6bis | ✗ |

**一个值得表扬的准确处**：今天该记忆目录里还有另外两份被改动过的文件——`git-log-is-blind-to-a-never-committed-file.md`（13:24:56）与 `a-blocking-observation-has-a-shelf-life.md`（09:41:43），时间戳都落在本会话窗口内。它们的 `originSessionId` 分别是 `a444a483-…` 与 `156d9daf-…`，**都不是本会话**。`DISPOSITION.md` 没有把它们算成自己的产出，这个边界划对了——按时间戳去认领会认错两份。

**另一处准确**：第 11 条的归属（「同伴在第 12 条标题里插了一句错的」）经我逐提交 diff 复核**成立**，是 `2aa0cad`（同伴，13:03:58）插的，不是本会话的 `f760078`（12:01:15）。我自己第一版把它归给了本会话，已在 §1.4 更正。

---

## 五、汇总

**Verdict：needs-fix。** 没有 blocker——没有任何一条缺陷会造成代码错误、数据丢失或不可逆后果；全部是**文档与终态自述与事实不符**，以及**两条有价值的结论没有落盘**。

| # | 严重度 | 位置 | 一句话 |
|---|---|---|---|
| 1 | **major** | `deferred.md:107`（第 11 条） | 同一份文件第 119 行判为假的那句话，第 107 行原样留着 |
| 2 | **major** | `deferred.md` 第 19 条 | 「message 零消费可以改」漏了第二个产出点 `responses_anthropic_stream.py:349`，以及 `stream.py:392` 把「same message」写成有意契约 |
| 3 | **major** | `deferred.md` 第 19 条 | 「两条腿共用」的理由用了 framer（客户端轴），而结论说的是上游轴；旧文档里本来是对的论证被换成了代码专门警示的错误方向 |
| 4 | **major** | 终态声明 + `DISPOSITION.md` | `$CLAUDE_JOB_DIR/tmp` **不为空**，有 1 个文件（就是那份标记本身，13:37:36 写入） |
| 5 | **major** | 交接件 §9:144 + 抬头 :5 | 自称「最终状态」，却写着「工作树保留」——实测已移除；且完全没提被保留下来的分支 |
| 6 | **major** | 遗漏 O1 | 「续写没接手时的 ending」这个更正只在会话记录里，文档留着被它取代的旧三格 |
| 7 | **major** | 遗漏 O2 | §7 对下一棒提的硬要求，终态没说兑现没有（我测了：已兑现） |
| 8 | minor | 终态声明 | 「主仓只有一个提交」需加「进入 `main`」；分支上另有 4 个 |
| 9 | minor | 交接件 §9:148 / 终态 | 「15 个暂存文件」事后不可复核，应注明来源 |
| 10 | minor | `deferred.md` 第 12 条 | 更正措辞读起来像「事实后来变了」，实际是写下时即为假；也没说是谁写的 |
| 11 | minor | 交接件 §9 | 没说 `2230852` 是被主动 reset 放弃的 |
| 12 | minor | 遗漏 O3 | `deferred.md` 编号 12→15 有空号，会话说要提一句但没提 |
| 13 | minor | 遗漏 O4 | `git stash` 跨 worktree 共享这条机制没进记忆 |
| 14 | minor | 遗漏 O5 | 共享树协作技能未安装（环境事实，且已有文档在引用它） |
| 15 | minor | 遗漏 O6 | 同伴的 G1 分层拆解主张只经本会话转述过一次 |
| 16 | 倾向 | 遗漏 O8 | 「天然变异比人造变异强一档」这个观察 |

**核实为成立、无需动作的**（列出来是为了让「没提到」不等于「没查」）：`f0527e5` 恰好 2 文件；两文件未卷入同伴暂存；`22c7e8d` 与 `f0527e5`/HEAD blob 逐字节相同；`c86712d` 可达且本会话的更正方向正确；工作树已移除且已 prune、分支因 `-d` 拒绝而保留（判据机理也核过）；7 份文档全部在 `.dev` 历史里（两个对照都到位）；第 19 条的三个数字（2 处断言、spec 逐字复述、message 零断言）逐条自数**全部正确**；§9 的 `1743a0b` 引文、`1743a0b..64bff1e` 无变化、三个归档 ref 的父提交关系、以及「语义已在 main」全部核过成立。

**本项目禁止的东西我一条都没建议**：没有覆盖率目标，没有门禁/投票/验证状态机，没有安全加固建议，没有跑 `ruff format`。上面每一条 major 的修法都是改一到两句话，或补一行。

**我自己在本次评审中犯的两个错，都留在正文里没有抹掉**：① §1.6 那次探针跑对了、对照也过了，数字仍然错，因为快照早于被观测的动作（§1.6bis）；② §1.4 的归因第一版写反了，是逐提交 diff 才纠正的。两条都指向同一件事——**正样本对照能证明命令有效，不能证明观测时刻正确，也不能替代逐提交核对**。

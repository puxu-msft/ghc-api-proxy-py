# 独立评审：主仓 `2afa0c4` 拆分

**评审人**：独立子智能体（异源，只读）
**日期**：2026-08-22
**评审对象**：主仓 `main` 上把 `2afa0c4` 拆成 `bbf5f50`（docs）+ `36e303d`（refactor）的这次历史改写，以及 `.dev` 的 `fea4e4a`（引用重指）。

**评审基线（`git rev-parse` 固化）**

| ref | SHA |
|---|---|
| 主仓 `main` HEAD | `53dd99c` |
| 拆分基点 | `e7cf57a` |
| 保留的旧历史 | `a/2026-08-22-split-2afa0c4` → `30f251c` |
| `.dev` HEAD | `fea4e4a` |
| `origin/main` | `44fa576`（不含 `2afa0c4`） |

**总判定**：**pass**。无 blocker，无 major。这次拆分在机械层面是我见过的最严的一种做法——它证到了拆分点本身而不只是 tip（见「做对了的地方」第 4 条）。下面 8 条全是 minor 与 nit，其中只有第 1 条落在提交信息本身。

---

## 一、`bbf5f50` 提交信息的逐句核对

信息全文（`git show bbf5f50`）：

> `docs/` has been empty since 0b01cdc moved the agent working documents into .dev, while CLAUDE.md went on pointing at `docs/.human-controlled/` for the requirements the user writes and ratifies. These fourteen files are that directory: the constraints and the reading of the system the user has settled on, plus a README saying an agent may propose a change to them and may never make one.
>
> CLAUDE.md links to that README under the name the documents give themselves, instead of naming the path in passing.

### F1 「`docs/` has been empty since 0b01cdc」——**成立**

```
$ git ls-tree -r 0b01cdc -- docs/ | wc -l
0
$ git ls-tree -r 0b01cdc^ -- docs/ | wc -l
106
$ git log --oneline 0b01cdc..e7cf57a -- docs/
(空)
$ git ls-tree -r e7cf57a -- docs/ | wc -l
0
```

`0b01cdc` 之前 106 个文件，之后 0 个，且从 `0b01cdc` 到拆分基点 `e7cf57a` 之间**没有任何提交碰过 `docs/`**。「moved ... into .dev」这半句也与 `0b01cdc` 自己的信息一致（「They now live in .dev/docs/, one directory per topic」）。

### F2 「while CLAUDE.md went on pointing at `docs/.human-controlled/`」——**不成立（minor）**

`0b01cdc` 时 `CLAUDE.md` **根本不存在**：

```
$ git show 0b01cdc:CLAUDE.md
fatal: path 'CLAUDE.md' exists on disk, but not in '0b01cdc'
$ git log --diff-filter=A --format='%h %ad %s' --date=short --all -- CLAUDE.md
1b0cdd2 2026-08-21 feat: add project development instructions and update README for clarity
$ git merge-base --is-ancestor 0b01cdc 1b0cdd2 && echo "0b01cdc 在前"
0b01cdc 在前
$ git log -1 --format='%h %ad' --date=iso 0b01cdc   # 2026-08-21 18:21:33
$ git log -1 --format='%h %ad' --date=iso 1b0cdd2   # 2026-08-21 23:05:32
```

`CLAUDE.md` 是 `0b01cdc` 之后约 4 小时 44 分才由 `1b0cdd2` 建的。「went on pointing」（持续指着）在字面上要求它在 `0b01cdc` 时已经指着，读者会据此推断 `CLAUDE.md` 早于 `0b01cdc`——那是假的。

**严重度 minor**：错的只是那段空窗的**时长归属**，不是这次改动的实质（「`docs/` 是空的，而 `CLAUDE.md` 指着一个背后什么都没有的路径」整体为真，只是这个矛盾从 `1b0cdd2` 起才存在，19 小时的窗口里占了 14 小时）。

**修法只需一个动词**：把 `went on pointing at` 改成 `points at`（现在时，不承诺持续性），或写成 `while CLAUDE.md has pointed at ... since 1b0cdd2`。我倾向前者——本仓提交信息本来就少写时长，`bfdc6aa` 那种「comment 指向不存在的分支」的修法也是直接改成事实态。

顺带：本仓有一条更强也更准的候补事实，如果想留一句「谁在指着空目录」——`.claude/rules/00-development-workflow.md:38` 一直写着「The main repository's `docs/` now holds only `docs/.human-controlled/`, which the user writes」，而在 `bbf5f50` 之前那句是**字面为假**的（`docs/` 什么都不 hold）。这条是否值得写进信息由你判断，我不认为缺它算缺陷。

### F3 「These fourteen files」——**成立**

`git show bbf5f50 --stat` 列 15 条路径，其中 `CLAUDE.md` 是第 15 条，`docs/.human-controlled/` 下恰好 14 个：

```
$ git ls-tree main -- docs/.human-controlled/ | wc -l
14
$ fd --hidden --no-ignore . docs/ --type f | wc -l
14
```

工作树与提交一致，目录里没有被 `.gitignore` 挡在外面的第 15 个文件（`git status --porcelain --ignored docs/` 只报两个 `M`，无 `!!`）。

句法上「These fourteen files are that directory: ... plus a README」也自洽——14 = 13 份约束文档 + README，读法无歧义。

### F4 「a README saying an agent may propose a change to them and may never make one」——**成立**

`git show bbf5f50:docs/.human-controlled/README.md` 第 5 行：

> 你可以建议修改或补充本系列文档，但需要用户裁决。你不能亲自动手修改本系列文档，但可以提供文档或片段，写入 `.dev/human-controlled-docs-candidates/` 目录，供用户参考。

「may propose / may never make」是对这句的准确英译，连「候选材料写哪」这个次要条款省略掉也是对的（提交信息是摘要与索引）。

### F5 第二段「CLAUDE.md links to that README under the name the documents give themselves」——**成立**

README 的 H1 是 `# 用户控制的需求约束与认知文档`；`bbf5f50` 里 `CLAUDE.md` 的新文本是 `[用户控制的需求约束与认知文档](docs/.human-controlled/README.md)`——逐字取自 README 自己的标题。旧文本是 `“用户控制的文档”（位于 `docs/.human-controlled/`）`，确实是「naming the path in passing」。两半都对。

### F6 「the constraints and the reading of the system the user has settled on」略有夸张——**nit**

`docs/.human-controlled/cli.md` 是 **0 字节**（`git cat-file -s $(git rev-parse main:docs/.human-controlled/cli.md)` → `0`；`--stat` 里它那行也是 `| 0`）。13 份里有 1 份是空占位，说它承载「用户已经定下的约束」略微超出事实。

**我不建议改**。提交信息是摘要，一个空占位文件不值得一句话；而且这是用户自己目录的现状，不是这次改动引入的。列在这里只是为了让「没提到」不等于「没查」。

### F7 风格与 Conventional Commits——**合格**

- `docs:` 类型选得对（新增的是文档，且 `CLAUDE.md` 的改动是文档指向）。主题行 68 字符，全小写祈使，与 `git log` 里 `docs: point the deadline comment at a branch that exists`、`docs: move the agent working documents out of the main repository` 同形。
- 正文两段散文，先讲问题状态再讲改动，无 bullet 清单、无 `Co-authored-by`、无任何模型足迹——与相邻的 `53dd99c`/`2e17663`/`13bc1c3` 完全同调。
- 正文引用了 `0b01cdc` 这个哈希。**这是安全的**：`0b01cdc` 在拆分基点 `e7cf57a` 之下，本次改写没碰它，将来重写这段历史也不会波及。（提交信息里写哈希本身有保质期风险，这次这个恰好没有。）

---

## 二、拆分边界

### F8 `CLAUDE.md` 归入 docs 半边——**正确，而且是唯一正确的归法**

`CLAUDE.md` 的那一个 hunk 做的事是：把一句「位于 `docs/.human-controlled/`」改写成一个**指向 `docs/.human-controlled/README.md` 的 Markdown 链接**。如果它被放进 `36e303d`，那条链接会在 `bbf5f50` 不存在的世界里悬空；更要命的是拆分后的 `36e303d`（refactor 那一半）会带着一个和 delivery 毫无关系、且指向本提交没有创建的文件的改动，那正是这次拆分要消灭的毛病。

这一条我特别点出来，因为**通行做法会做错**：`CLAUDE.md` 在仓库根、不在 `docs/` 下，按「路径前缀分半」的机械拆法会被留在另一边或干脆留在 refactor 半边。按语义归属而不是按路径前缀归属，是对的。

### F9 其余路径归属——**无一归错**，且分割是精确划分

```
$ diff <(git show --name-only --format='' 2afa0c4 | sort) \
       <(cat <(git show --name-only --format='' bbf5f50) \
             <(git show --name-only --format='' 36e303d) | sort)
PATH SETS IDENTICAL
```

两半路径集**不相交且并集等于原提交**（15 + 8 = 23）。`36e303d` 的 8 条全在 `src/app/pipeline/delivery/`、`src/app/server/`、`tests/` 下，逐 hunk 读过（`git show 36e303d -- src/app/server/pipeline_app.py src/app/server/handler.py`），没有任何一处是文档内容——`handler.py` 里新增的两段注释讲的是 one-shot 前提与 `signature_compat` 的归属，都是 delivery 语义。

更强的证据：

```
$ git rev-parse 36e303d^{tree} 2afa0c4^{tree}
10b57f2514a2a89a17eb23d7fe436a427dc8cacf
10b57f2514a2a89a17eb23d7fe436a427dc8cacf
```

**拆分点的树与原提交的树逐字节相等**。这比 tip 相等强：它排除了「两半各自漏了一点、在后续提交里互相补回来」这种 tip 比对看不出来的失手。

---

## 三、`36e303d` 保留的原信息是否仍然成立

### F10 **仍然成立，且拆分后比拆分前更准**

我把它的每一句断言对回了 8 条路径的 diff：

| 断言 | 落点 | 判定 |
|---|---|---|
| framer 改为必填，`message_id`/`model`/setting 三个参数随默认值一起消失 | `pipeline_app.py:748` 起（`message_id=`、`model=` 从 `stream_delivery` 调用里删掉）+ `stream.py` | 成立 |
| `signature_compat` 移出 `StreamSettings`，`framer_for` 改从 chain 读 | `handler.py:framer_for` 新增 `chain` 形参、读 `chain.config.hook_fix_anthropic_sse...`；`stream_settings()` 只剩 `sse_ping_interval` | 成立 |
| 「StreamSettings is down to the ping interval」 | 同上，返回值确实只剩一个字段 | 成立 |
| one-shot 的前提改为断言（`translation_required` 就 raise） | `handler.py` 新增 `raise ValueError(...)` | 成立 |
| 守卫触发时交出已缓冲字节 | `stream.py`（66 行改动） | 成立 |
| 「It had no test at all before; it has five now」 | `test_one_shot_delivery.py` 在 `2afa0c4^` 不存在；新文件里 `def test_` 计数 = **5** | 成立，逐条数过 |
| `stream_settings` 每请求只读一次 | `pipeline_app.py` 提出 `settings = stream_settings(chain)`，下游改用 `settings=settings` | 成立 |

**没有任何一句在讲文档**。整段信息里出现的名词全是 `stream_delivery`、`signature_compat`、`StreamSettings`、`framer_for`、`WireFormat`、`data: [DONE]`。

值得说清楚的是这次拆分修好了什么：拆分前 `2afa0c4` 的信息不是「有一句假话」，而是**对自己 diff 的 65%（23 条路径里的 15 条、1281 行里的 1120 行）只字未提**。拆分把「信息与 diff 不匹配」这个缺陷消掉了，而不是把一条真句子挪了个地方。

### F11 身份字段与后四条重放——**逐对相同**

```
$ git range-diff 2afa0c4..30f251c 36e303d..53dd99c
1:  8ce22b9 = 1:  13bc1c3 test: make the keep-alive test check the thing its comment claimed
2:  027698f = 2:  2e17663 fix: say which clock a finished turn loses to, and pin it
3:  25432d4 = 3:  bfdc6aa docs: point the deadline comment at a branch that exists
4:  30f251c = 4:  53dd99c refactor: say synthetic what, and stop naming the module after its only occupant
```

四条全 `=`。三个提交的六个身份字段：

```
2afa0c4 => AD=2026-08-22 13:36:08 +0000 AN=Pu Xu AE=puxu@microsoft.com CD=2026-08-22 13:36:40 +0000 CN=Pu Xu CE=puxu@microsoft.com
bbf5f50 => (逐字相同)
36e303d => (逐字相同)
```

**committer date 也保住了**，不只是 author date。这是超出常规的一步（大多数改写会让 committer date 变成改写时刻），我把它列进「做对了的地方」。

父链与 tip：`bbf5f50^ = e7cf57a`，其后逐级 `36e303d → 13bc1c3 → 2e17663 → bfdc6aa → 53dd99c`；`tree(53dd99c) == tree(30f251c) == a37a14f6`；`git diff 30f251c 53dd99c --stat` 为空。

---

## 四、引用处置

### F12 `.dev` 里已无断链的活文档旧哈希——**成立**

穷举检索（`-uuu`，含未追踪、含隐藏、绕过所有 ignore）：

```
$ rg -uuu -n -e '2afa0c4' -e '8ce22b9' -e '027698f' -e '25432d4' -e '30f251c' \
     .dev/ --glob '!.dev/.git/**' -l
.dev/docs/tmp/260822-review-session-closeout.md
.dev/docs/tmp/260822-split-2afa0c4-hash-map.md
.dev/docs/upstream/retry-and-continuation/reports/260822-review-mcp-contract-and-deadline-order.md
.dev/docs/upstream/retry-and-continuation/reports/260822-review-mcp-contract-disposition.md
```

四份，无一是活文档：一份是对照表本身（旧哈希是它的内容），三份是过程记录。两份 `deferred.md` 已经零残留。

`fea4e4a` 的重指本身也核过：`client-leg-formats/deferred.md` 六处（U-3、U-4、D-5、D-6、n-2、n-5）与 `upstream/retry-and-continuation/deferred.md` 一处，每一处的新哈希都与「那件事落在哪一半」对得上——U-3/D-5/D-6/n-5 是代码，指 `36e303d`；n-2 指 `13bc1c3`；U-4 指 `53dd99c`；deadline 那条指 `2e17663`。**没有一处该指 `bbf5f50` 而漏指**（docs 那一半不对应任何 deferred 条目，它是被裹进来的，不是谁的待办）。

### F13 `260822-review-session-closeout.md` 属于过程记录——**你划对了，而且是唯一划法**

我打开读过。它的开篇是：

> **评审基线（全部经 `git rev-parse` 固化）**：| 主仓 `main` HEAD（评审开始时） | `8b71266...` | 主仓 `main` HEAD（评审中途，同伴推进） | `75273e1`（13:35:16）……

文件里 `027698f` 出现 4 次（469、500、511、547 行），**四次全部是「某时刻的主仓 HEAD」这一种用法**：

- 469 行：「主仓 HEAD = `027698f1adac...`，主仓无新提交」——第二轮复核的基线快照。
- 500 行：「主仓 HEAD `027698f`，`sed -n '378,392p' ...`」——自数复核的取值时刻。
- 511 行：「这两个数字今天（HEAD `027698f`）逐行对」+「建议在行号旁标一句『行号锚在 `027698f`』」——显式的时效锚点。
- 547 行：「控制流（主仓 HEAD `027698f`，`src/app/pipeline/delivery/stream.py`）」——引文的取样点。

**没有一处是「这件事落在哪个提交」式的指路**。把它们改成 `2e17663` 会断言「`2e17663` 在 13:54:49 是 HEAD」——那个提交当时**根本不存在**，是把一份验收记录改成伪造的。所以这不是「过程记录一般不回填」的惯例问题，而是这四处**只有不回填才是真的**。项目规则「A report original is a point-in-time record ... rewriting them ... falsifies the record」在这里咬得很紧。

另两份 `reports/` 下的文件同理（`260822-review-mcp-contract-and-deadline-order.md` 开头就写「**仓库状态**：`HEAD = 027698f`」）。

### F14 对照表放在 `docs/tmp/`——**nit**

`260822-split-2afa0c4-hash-map.md` 不是报告，是一份**长期有效的解码器**：只要那三份过程记录还在，旧哈希就还需要它。而 `docs/tmp/` 按项目规则是「topic 未定的报告暂存处」，将来清扫或归档时它会跟着走。

风险其实很低，因为对照关系是**可重建的**：保留分支还在，`git range-diff 2afa0c4..30f251c 36e303d..53dd99c` 一条命令就能重算出后四条的配对，文件自己也写了这一点（「要解析里面的旧哈希，走上面的对照表或那条保留分支」）。所以我评 nit 而不是 minor。

若要处理，我倾向把这份连同 `260822-review-session-closeout.md` 一起归到某个 topic 的 `history/` 或 `archive-*/reports/` 下——它们是同一件事的两面，分开走反而更容易失联。这是建议，不是要求。

### F15 `a/` 前缀这个保留分支约定没有写在任何规则里——**nit**

仓库里已有三条同形分支（`a/2026-08-20-rehome-peer-hunks`、`a/2026-08-20-split-53fec22`、`a/2026-08-22-split-2afa0c4`），用法一致：**改写前历史的保留点**，与 `.claude/rules/00-development-workflow.md` 里写明的 `archive/YYMMDD-<topic>`（squash 之前那份被评审过的源提交）是两类东西。

**用 `a/` 而不是 `archive/` 是对的**——这一段历史不是「被 squash 的评审源」，混进 `archive/` 会让那条规则的语义糊掉。但这个约定目前只活在三条分支名和一份 `docs/tmp/` 文档的「不要删除」一句里。`.claude/rules/` 里没有它。

我不建议为此加门或加检查。要么在规则里补一句「`a/YYYY-MM-DD-<topic>` 是历史改写前的保留点，不删」，要么就承认它是口头约定——**这是给用户的一个选项，不是缺陷**。

---

## 五、其它波及面

### F16 主仓、其它 worktree、`~/.claude`：无残留

```
$ rg -uuu -n -e '2afa0c4' -e '8ce22b9' -e '027698f' -e '25432d4' -e '30f251c' \
     . --glob '!.dev/**' --glob '!.git/**'
(无输出，exit 1)

$ rg -uuu -n <同样五个> /home/xp/.claude/rules /home/xp/.claude/skills \
     /home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/memory /home/xp/.claude/CLAUDE.md
(无输出，exit 1)

$ rg -uuu -n <同样五个> /home/xp/src/copilot-api-js /home/xp/.claude/skills-pending
(无输出)
```

主仓工作树（含 `src/`、`tests/`、`.claude/`、三个 worktree 的检出）零命中；用户级规则、技能、本项目记忆、`skills-pending`、`copilot-api-js` 全部零命中。

ref 层面穷举：

```
$ git for-each-ref --contains 2afa0c4 --format='%(refname)'
refs/heads/a/2026-08-22-split-2afa0c4
```

**只有保留分支**。没有第二条分支被这次改写孤立，旧 tip `30f251c` 仍可达。

### F17 Claude transcript 里有旧哈希——**不应处理，列出以示查过**

```
/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/be410f2e-....jsonl
/home/xp/.claude/projects/.../subagents/agent-a530b3933ba544121.jsonl
```

会话转录是**发生过什么**的记录，不是指向仓库的引用，性质与 F13 的过程记录相同，只是更彻底（它连「可以改」这个选项都不该有）。列在这里只为闭合检索。

### F18 `260822-split-2afa0c4-hash-map.md` 的「波及面」一节漏了第三个 worktree——**nit，无害**

文档写「`main` 上的两个活跃 worktree 分支（`proxy-priority-on-httpx2`、`fix/upstream-error-events`）」。实际有第三个：

```
$ git worktree list
/home/xp/src/ghc-api-proxy-py                                          53dd99c [main]
/home/xp/.claude/jobs/826d4cda/tmp/review                              7839b02 (detached HEAD)
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive     8703cad [proxy-priority-on-httpx2]
/home/xp/src/ghc-api-proxy-py/.claude/worktrees/upstream-error-events  fd6b591 [fix/upstream-error-events]
```

第三个是 detached HEAD，不是分支，所以「两个 worktree **分支**」字面上不假。而且它无害：

```
$ git log -1 --format='%h %ad' --date=iso 7839b02   # 2026-08-18 13:27:35
$ git merge-base 7839b02 main                        # == 7839b02，它是 main 的祖先
$ git merge-base --is-ancestor 2afa0c4 7839b02 && echo YES || echo NO
NO
```

它停在改写点**之下**（2026-08-18），完全不受影响。列出来只是让「两个」这个数字有确切的限定条件。

### F19 `fix/upstream-error-events` 的 squash 现在会**删掉**这 14 份用户文档——**minor，已被既有检查覆盖**

这是 `bbf5f50` 引入的一个新后果，值得写下来。`fd6b591` 的树是迁移前的旧 `docs/`：

```
$ git ls-tree -d fix/upstream-error-events -- docs/
040000 tree 2781c9e...  docs/agents
040000 tree 205cd88...  docs/tmp
$ git ls-tree -r fix/upstream-error-events -- docs/ | wc -l
106
$ git cat-file -e fix/upstream-error-events:docs/.human-controlled/README.md && echo YES || echo NO
NO
```

`.claude/rules/00-development-workflow.md:39` 已经警告过这条分支会「silently 带回 `docs/tmp/` 与 `docs/agents/`」。`bbf5f50` 之后多了一层：按「a squash takes its tree」的做法整合它，还会**同时删掉 `docs/.human-controlled/` 的 14 个文件**——那是用户亲笔、且现在才刚进版本控制的东西，无冲突、无报错。

好消息是**既有那句检查恰好挡得住**：「After integrating such a branch, check that `docs/` holds only `.human-controlled/`」——`.human-controlled/` 被删时这句同样不成立，检查会击发。所以我不提议加任何新机制。

我建议的唯一动作是**一句话**：在 `260822-split-2afa0c4-hash-map.md` 的「波及面」里，或在整合那条分支的当下，记一句「`docs/.human-controlled/` 自 `bbf5f50` 起受版本控制，旧分支的 squash 会删掉它」。要不要写、写在哪，由你定。

（另一条 worktree 分支 `proxy-priority-on-httpx2` 的 `docs/` 是空的，无此问题。）

### F20 三个源文件引用一份不存在的 human-controlled 文档——**minor，先于本次改动存在**

`bbf5f50` 之后这一点第一次变得**可在仓内验证**：

```
$ git grep -n 'message-format-sanitize' main -- src/
src/app/pipeline/anthropic_request_hook.py:28
src/app/pipeline/anthropic_request_hook.py:59
src/app/server/pipeline_app.py:422
$ git ls-tree main -- docs/.human-controlled/ | grep sanitize
(无)
```

三处代码注释把 `docs/.human-controlled/message-format-sanitize.md` 当作裁决依据引用（「rules that this should be resident rather than configured, so the switch is deliberately not read here — see that document for the standing decision」），而该文件不在目录里。目录里有的是 `message-format-reshape.md`。

同样地，README 自己的文档清单列了 `observability.md`（目录里没有），而目录里的 `release-and-deployment.md` **没有**出现在清单里：

```
$ git show main:docs/.human-controlled/README.md | grep -c '^- \['   # 13 条
$ git ls-tree main -- docs/.human-controlled/ | wc -l                # 14 个文件
```

**这些都不是这次拆分的缺陷**，也不是 `bbf5f50` 的信息该承担的内容——`README.md` 与整个目录是用户亲笔，我不提议修改其中任何一个字节。列出来是因为：把这个目录纳入版本控制的直接后果之一，就是这些悬空引用从此对所有人可见、可检索，而**知道它们存在的最好时机是现在**。是否需要向用户提出（走 `.dev/human-controlled-docs-candidates/`）由你判断。

### F21 新纳入版本控制的两个文件在工作树里已有未提交的用户改动——**信息项**

```
$ git diff --stat -- docs/.human-controlled/
 docs/.human-controlled/config.example.yaml | 14 +++++++-------
 docs/.human-controlled/module-org.md       |  3 ++-
$ ls -l --time-style=+%F' '%T docs/.human-controlled/config.example.yaml
-rw-r--r-- 1 xp xp 28548 2026-08-22 14:48:33 config.example.yaml
```

`config.example.yaml` 的 mtime 是 **14:48:33**，晚于你那次 `.dev` 提交（14:47:00）。用户此刻正在编辑这两个文件（`module-org.md` 的改动是给 `pipeline` 加注释、新增 `delivery` 一行）。

两点后果：

1. **这反过来证明「不动工作树、用 `commit-tree` + `update-ref` CAS」这个做法是必需的，不是讲究**。工作树里当时有 10 个 `M` 文件（含这两个用户亲笔文档），任何 `reset --hard` 形态的移 ref 都会把它们抹掉。见「做对了的地方」第 6 条。
2. 从现在起，「仓库里的 `docs/.human-controlled/` == 用户已定的约束」这句话带保质期。**不要代替用户提交这两个文件**——它们是用户亲笔，提交时机归他。

---

## 六、我认为你做对、而通行做法会做错的地方

按「值得被复述」的程度排序：

1. **证到了拆分点，不只是 tip。** `tree(36e303d) == tree(2afa0c4) == 10b57f25`。绝大多数拆分只比 tip 的 tree，而 tip 相等**证明不了两半各自正确**——两边互相欠一点、在后续提交里互相还上，tip 照样相等。加上路径集精确划分（不相交、并集相等），这次的两半各自都被钉死了。

2. **`CLAUDE.md` 按语义而非路径前缀归半。** 它在仓库根、不在 `docs/` 下，而它的改动是一个指向本次新增文件的链接。机械按路径分半会把它留在 refactor 那一半，重新造出这次拆分要消灭的那个毛病。

3. **过程记录不回填的界线划在了正确的位置，理由也比「惯例」更硬。** `260822-review-session-closeout.md` 里的四处 `027698f` **全部是「某时刻的 HEAD」**。回填它们不只是「改写历史记录」这种风格问题，而是会写下一句物理上不可能的话——`2e17663` 在 13:54:49 尚未存在。这一条我特意逐处读过才敢说，见 F13。

4. **committer date 也一并保住。** 六个身份字段逐对相同，不只是 author 三件套。用 `commit-tree` 重放时 committer date 默认取当下，保住它需要显式设 `GIT_COMMITTER_DATE`——这一步经常被跳过，跳过之后 `range-diff` 仍然全 `=`（它不比 committer date），所以是个**不会被自己的验证发现**的漏项。

5. **保留分支用 `a/` 而不是 `archive/`。** 项目规则给 `archive/YYMMDD-<topic>` 的定义是「被 squash 的那份经过评审的源提交」，与「改写前的历史保留点」不是一回事。塞进 `archive/` 会污染那条规则的语义。这里跟了已有的三条 `a/` 先例，判别是对的（虽然这个约定本身还没写进规则，见 F15）。

6. **用 `update-ref <new> <old>` 的 CAS 移 ref、全程不碰工作树。** F21 显示工作树里当时有 10 个 `M` 文件，其中两个是用户亲笔的 human-controlled 文档、一个在改写后一分钟还被再次写入。这个环境里 `reset --hard` 会造成不可恢复的用户数据丢失。CAS 这一步同时还挡住了「同伴在你算 tree 与移 ref 之间又提交了一条」的竞态——这在本仓是**发生过**的（`260822-review-session-closeout.md` 自己就记着「HEAD 在评审期间移动过」）。

7. **`36e303d` 的信息一个字没改。** 有一种很自然的冲动是趁机「顺手润色一下」。没改是对的：它原本就只描述 delivery，改它会让 `range-diff` 和逐字比对失去参照，也会把「拆分」悄悄变成「拆分 + 重写」。

---

## 七、我没有核查的部分（能力边界）

明确列出，以免「没提到」被读成「没问题」：

- **没有跑任何测试、Ruff 或 Pyright。** 判断依据是 `tree(53dd99c) == tree(30f251c)` 与 `tree(36e303d) == tree(2afa0c4)`：改写前后每一个检出点的文件内容逐字节相同，任何构建或测试结果按构造不可能改变。**但这只覆盖 `main` 上的检出点**——它不说明 `main` 本身当前是否绿（`.dev/docs/tmp/ab1f84b` 那条「flag 21 pyright errors on main」的记录暗示可能不绿，我未核实，也不在本次评审范围）。
- **没有逐字审读那 14 份文档的内容。** 它们是用户亲笔，我只核了文件数、`cli.md` 的字节数、README 的清单条目数与那句「agent 不得动手」的原文。文档内容的对错不归我判，也不该由 agent 提改。
- **没有检索 `/home/xp/src/refs/` 下的外部参考项目**。它们是只读参考物，不可能按哈希引用本仓这段历史；我判断 ROI 为负而跳过。已检索的范围：主仓工作树全部（含三个 worktree 检出）、`.dev` 全部（含未追踪与隐藏）、`~/.claude/{rules,skills,skills-pending,CLAUDE.md}`、本项目记忆目录、`~/src/copilot-api-js`。
- **没有核 `.dev` 仓库 `fea4e4a` 之前的历史是否还有别的活文档需要重指**——我核的是 `.dev` **当前工作树**的全量内容（`-uuu`，含未追踪），这覆盖了「现在还有没有断链」这个问题；`.dev` 历史提交里的旧哈希与主仓过程记录同性质，本就不该动。
- **没有验证 `git reflog` 之外是否存在其它指向旧链的机制**（如 `ORIG_HEAD`、stash、其它 clone）。ref 层面用 `for-each-ref --contains` 穷举过，reflog 显示 `main@{1} = 30f251c` 仍在，30 天内可回滚。
- **未执行任何写操作**，除本报告外未创建、修改或删除任何文件，未运行任何改变仓库状态的命令（全部为 `git log/show/ls-tree/rev-parse/range-diff/for-each-ref/merge-base/diff/grep`、`rg`、`fd`、`ls`、`head`、`sed -n`）。

---

## 八、发现汇总

| # | 严重度 | 一句话 | 建议动作 |
|---|---|---|---|
| F2 | **minor** | 「CLAUDE.md went on pointing」暗示 CLAUDE.md 早于 `0b01cdc`，实际它晚 4h44m 才由 `1b0cdd2` 建立 | 改一个动词：`went on pointing at` → `points at` |
| F19 | **minor** | 旧分支 `fix/upstream-error-events` 的 squash 现在会连带删掉 14 份用户文档 | 记一句话即可；既有的 `docs/` 检查已能击发，**不要加新机制** |
| F20 | **minor** | 三处源码注释引用不存在的 `message-format-sanitize.md`；README 清单列了不存在的 `observability.md`、漏了存在的 `release-and-deployment.md` | 先于本次改动存在。是否走 `.dev/human-controlled-docs-candidates/` 提给用户，由你定。**不得直接改那些文件** |
| F6 | nit | `cli.md` 是 0 字节，与「the constraints ... the user has settled on」略有出入 | 不建议改 |
| F14 | nit | 对照表放在 `docs/tmp/`，而它是长期解码器不是报告 | 可选：与那份 closeout 一起归到某 topic 下 |
| F15 | nit | `a/` 保留分支约定有三条先例但未写进 `.claude/rules/` | 可选：补一句定义 |
| F18 | nit | 「波及面」写「两个 worktree 分支」，实际还有第三个 detached worktree | 无害（它是改写点的祖先）；补一句限定即可 |
| F21 | 信息 | 新纳入版本控制的两个文档在工作树里已有用户未提交的改动，其一写于改写后一分钟 | 不要代替用户提交 |

**计数**：blocker 0，major 0，minor 3，nit 4，信息 1。成立且无需动作的核对点 11 条（F1、F3、F4、F5、F7、F8、F9、F10、F11、F12、F13、F16、F17）。

**总判定：pass。** 唯一落在提交信息本身的是 F2，一个动词的事。拆分边界、原信息保留、引用处置三项我逐条核过，**没有找到需要返工的地方**。

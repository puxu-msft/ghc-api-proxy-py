# 第三轮独立评审 C：只查 8 份 subagent 日志正文

**日期**：2026-08-23。**评审人**：第三轮独立评审员（异源）。
**补的盲区**：前两轮（A、B）从主 transcript 各自枚举了非文件知识候选，但都只读了 subagent 回到主线程的摘要，没读日志正文。本轮**只查日志正文**，不重做主 transcript 的枚举。

---

## 〇、覆盖面声明（先说我读了什么、没读什么）

**事件源**：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/be410f2e-42dd-4a60-9b83-26953bd51893/subagents/` 下共 **11** 份 `.jsonl`。其中：

| 排除的 3 份 | 理由 |
|---|---|
| `agent-aabc966cc3b7aafdf`（`Independent nonfile candidate enumeration A`） | 就是评审 A 本人 |
| `agent-a44721aff0b27b7f9`（`Independent nonfile candidate enumeration B`） | 就是评审 B 本人 |
| `agent-a627846c623763c59`（`Enumerate subagent transcripts`，4 行 / 45 KB） | 就是本轮（我）自己的日志 |

剩下 **8 份**即任务指定的目标，全部读完，无跳读：

| agent id | 描述（`meta.json`） | 类型 | 行数 / 字节 | 时段（UTC） |
|---|---|---|---|---|
| `a530b3933ba544121` | Independently review the commit split | gpt-opus | 102 / 408 K | 14:47–14:57 |
| `a168f027ef359bb43` | Audit coverage and over-reach | general-opus | 103 / 575 K | 15:19–15:29 |
| `af922706230f4e0d3` | Verify each repointed citation | gpt-opus | 116 / 607 K | 15:18–15:29 |
| `a739e8c5451e7767e` | Map live vs legacy chains | gpt-opus | 125 / 445 K | 15:49–15:58 |
| `acb051ab661906d39` | Extract prior module-boundary rulings | general-opus | 174 / 793 K | 15:49–16:00 |
| `a11c4f0c4041ac789` | Fact-check the layout proposal | gpt-opus | 128 / 554 K | 16:05–16:20 |
| `a656a8f7275990be2` | Challenge the target design | general-opus | 94 / 650 K | 16:06–16:20 |
| `ab3a3e221638717c2` | Read the unread architecture constraints | gpt-opus | 68 / 773 K | 16:21–16:30 |

**抽取方式**：用一个 Python 脚本把每份 JSONL 展开成「任务提示词 → assistant 文本 → 工具调用（含完整命令行）→ 工具结果」的配对流水账，**每条工具结果截断到 1800 字符**，然后把 8 份（共约 10 250 行）逐页读完。

**因此我的盲区，逐条列出**：

1. **每条工具结果超出 1800 字符的部分我没读。** 被截断最多的是几次 `git show <大提交>`、几次整份文档 `Read`、以及 `.dev/docs` 的全量文件清单。这些都是**被读取的既有内容**（提交、文档、代码），不是本会话新产生的事实，所以截断对「非文件知识候选」这个目标的损失有限——但**它确实可能漏掉某个 agent 在长输出末尾才注意到的东西**。
2. **`thinking` 块的内容在这 8 份日志里全部为空。** 说清楚形态：块本身**存在**（逐份数：24/24/28/33/50/36/26/17 个），但每一个 `.thinking` 字符串的长度都是 **0**。所以不是「模型没思考」，是**内容没有落盘**。后果是「agent 当时怎么想的」不可得，我只能从**命令序列的形状**反推它试过哪些路、在哪里改了口径。这意味着：一次「试了 A 没用、改用 B」如果 A 和 B 长得像，我可能读成一次普通的迭代；而**纯在脑子里否决、没留下任何命令痕迹的路线，我一条也捞不到**。这是本轮方法的硬上限，见第 11.5 节。
3. **8 个 agent 各自写下的报告文件我基本没读**（只在对账阶段定向查了三处）。那些是**文件知识**，本轮按定义不收；但这也意味着我判断「这条只在日志里、没进报告」时，用的是「摘要里没有 + 定向 grep 没命中」，不是「逐字比对过报告全文」。凡受此影响的条目我在下面单独标了。
4. **主 transcript 我一行没读**，按任务要求。所以「这条是不是主线程已经讲过了」我判断不了，只能靠第五节与 A、B 两份材料对账。

**证据强度分档**在每条上标注，三档：**强到可据此行动** / **只是倾向，需更多样本** / **仅存档，不用于任何决策**。

---

## 一、本轮最重的一条：subagent 的 Bash 初始 cwd 在本会话里落在四个不同目录，其中五次落在 `.dev`

**分级：major。证据强度：强到可据此行动。**

每份 subagent transcript 的记录里有一个 `cwd` 字段。8 份的取值：

| agent | 描述 | `cwd` |
|---|---|---|
| `a530b39` | 复核提交拆分 | `/home/xp/src/ghc-api-proxy-py/.dev` |
| `a168f02` | 覆盖面与过度改动 | `/home/xp/src/ghc-api-proxy-py` |
| `af92270` | 逐条核对改指 | `/home/xp/src/ghc-api-proxy-py` |
| `a739e8c` | 链路可达性 | `/home/xp/src/ghc-api-proxy-py/.dev/docs` |
| `acb051a` | 既有裁决考古 | `/home/xp/src/ghc-api-proxy-py/.dev/docs` |
| `a11c4f0` | 提案事实核查 | `/home/xp/src/ghc-api-proxy-py/.dev` |
| `a656a8f` | 提案设计评审 | `/home/xp/src/ghc-api-proxy-py/.dev` |
| `ab3a3e2` | 补读架构约束 | `/home/xp/src/ghc-api-proxy-py/.dev/docs/server-layout/reports` |

主 transcript 自己的 `cwd` 字段在整场会话里反复摆动（按出现顺序的游程计数节选）：`主仓×130 → .dev×73 → 主仓×61 → .dev×46 → 主仓×75 → docs/.human-controlled×8 → … → .dev/docs×19 → … → .dev/docs/anthropic-responses-bridge×84 → .dev/docs/server-layout/reports×12 → …`。

**这不是理论推演，本会话真的击发过一次。** `a530b39`（cwd = `.dev`）：

- 它写了一条**不带 `cd`** 的命令 `echo "=== .dev HEAD ===" && git log --oneline -5`（RESULT #14），得到的是 `.dev` 仓的提交列表（`fea4e4a`、`818d089`…）。输出形状完全正常、没有任何报错——**如果它当时想问的是主仓，这就是一个静默的错答案**，因为 `.dev` 是嵌在主工作树里的独立 git 仓库。
- 紧接着它写了 `cd /home/xp/src/ghc-api-proxy-py && git show fea4e4a`（RESULT #21），拿到 `fatal: ambiguous argument 'fea4e4a'`；改成 `git -C .../.dev show fea4e4a`（RESULT #22）才成功。
- 它还写过不带 `cd` 的 `head -40 docs/tmp/260822-review-session-closeout.md`（RESULT #23），解析到的是 `.dev/docs/tmp/…`。

`acb051a`（cwd = `.dev/docs`）同样写过不带 `cd` 的 `for d in pipeline-rewrite-parity …; do find "$d" …` 与 `rg -l … --glob '!archived-2604-rewrite/**'`（RESULT #9、#10、#25、#48），全部相对 `.dev/docs` 解析并**正常返回**。

**这条为什么重要**：`root-each-bash-call` 这条规则在本仓有一个特有的加剧因素——**主会话最常 `cd` 进去的那个目录（`.dev`）本身是一个嵌套的独立 git 仓库**。于是「忘了绑目录」的后果不是报错，而是 `git log` / `git status` / `git show` 从另一个仓库给出一个形状完全正确的答案。8 次派发里有 6 次的 cwd 不是主仓根、5 次在 `.dev` 内，这不是低概率事件。

**救了这一场的是派发提示词**：这 8 份提示词**每一份**都以「`Agent` 不继承 cwd，每条 Bash 命令自带 `cd /home/xp/src/ghc-api-proxy-py &&` 或 `git -C …`」开头。这个纪律是有效的，唯一滑出去的那次也被下一条命令的 `fatal` 兜住了。

**落点建议**：写进项目记忆（新建一条，或并入 `dev-state-lives-in-dot-dev.md`）。内容应该是两句：（一）本仓 subagent 的初始 cwd 由派发时刻主会话 Bash 的 cwd 决定，实测取到过四个不同值，多数不是仓库根；（二）因为 `.dev` 是嵌套独立仓，漏掉 `-C` 的 git 命令会从错误的仓库给出形状正常的答案，不会报错。派发提示词里那句开场白应当保留为固定模板。

---

## 二、静态 import 图缺「祖先包 init 边」时，会对同一批候选给出与事实相反的「无环」结论

**分级：major。证据强度：强到可据此行动（两次运行、同一探针家族、结论相反，命令与输出都在日志里）。**

`a656a8f`（设计评审）为了判断「新建 `pipeline/delivery/selection.py`、`observability/wire_accounting.py` 会不会造成 import 环」，写了一个 AST import 图并做**假想模块注入**。它跑了两次：

**第一次**（RESULT #20），图里只有显式 `import` 边：

```
app.pipeline.delivery.selection            composition -> ...? no
app.observability.wire_accounting          composition -> ...? no
app.observability.request_trace            composition -> ...? no
（五个候选全部 no）
```

**第二次**（RESULT #22、#23），补上一条边——「import `a.b.c` 会先初始化它的每一级祖先包」——并加上「该模块是否被父包 `__init__` 再导出」这个开关：

```
app.pipeline.delivery.selection   reexported=True  -> CYCLE: app.composition -> app.pipeline.translation_driver.registry
                                                     -> app.pipeline.request -> app.pipeline.delivery.assembling
                                                     -> app.pipeline.delivery.sse_source -> app.pipeline.delivery
                                                     -> app.pipeline.delivery.selection
app.pipeline.delivery.selection   reexported=False -> no cycle
app.observability.wire_accounting reexported=True  -> CYCLE: app.composition -> app.observability.terminal
                                                     -> app.observability -> app.observability.wire_accounting
app.observability.wire_accounting reexported=False -> no cycle
```

第一次的输出**命令正常、退出码 0、格式正确**，结论是「五个落点全都安全」。第二次证明其中三个在被父包再导出时是硬 ImportError。这条发现最后成了该评审两个 blocker 之一（F1）。

**可复用的判据**：判断「新增模块会不会造成环」时，只连显式 import 边的图**系统性地漏报**。必须补两类边——祖先包初始化边，以及「父包 `__init__` 是否再导出该子模块」这个开关（后者把同一个落点从「无环」翻成「有环」）。

**它不能证明什么**（该 agent 自己写明了，值得一并带走）：这是**静态推导**，不是一手证据；要变成一手证据须在树里真写一个 `selection.py` 并改 `delivery/__init__.py`，它按只读约束没做，并把这一步作为需要授权的事项交回。

**落点建议**：`.dev/docs/server-layout/probes/README.md` 的「这套可达性判据被击穿过四次」一节，**加为第五类盲区**。理由：现有四条讲的都是「运行时可达性判据」的盲区，这一条讲的是**静态图本身**的盲区，同一个话题、同一个读者，但机制不同。附带把那两次运行的完整输出抄过去——它是这条盲区唯一的正/负样本对照。

---

## 三、`rg` 无匹配时退出 1，会把 `&&` 串起来的后续搜索段整段静默吃掉

**分级：major。证据强度：强到可据此行动。**

`acb051a` RESULT #35，命令是三段搜索用 `&&` 串起来的：

```bash
cd … && echo "=== lifecycle.systemd refs ===" \
     && rg -n 'lifecycle\.systemd|from \.systemd|from \.\.systemd' src/ \
     && echo && echo "=== app.core refs in src ===" \
     && rg -n 'app\.core|from \.core|from \.\.core' src/ \
     && echo && echo "=== snapshot_store refs ===" && rg -n 'snapshot_store' src/
```

实际输出（全部，30 字节）：

```
=== lifecycle.systemd refs ===
```

第一条 `rg` 在 `src/` 里零匹配 → 退出 1 → `&&` 链断在那里，**后两段搜索连同它们的标题一起没有执行**。

紧接着 RESULT #36 把分隔符换成 `;` 并给每段补了退出码：

```
=== app.core refs ===
src/app/lifecycle/systemd/systemctl.py:6:from app.core.generation_identity import parse_generation_id
src/app/tokenization/snapshot_store.py:12:from app.core.generation_identity import …
src/app/tokenization/snapshot_store.py:13:from app.core.release_identity import …
---exit=0
```

也就是说，被 `&&` 吃掉的那一段**本来有三条命中**。

**这一条属于「命令跑了、输出真实、结论仍错」那一类**：如果读者按标题数把「只印了一个标题」读成「三项都没有」，得到的结论恰好与事实相反。这次是 agent 自己发现了（因为标题缺了两个，形状可疑），但一个只印一次标题的版本就不会露馅。

**落点建议**：`~/.claude/rules/00-user/20-tool-use-preference.md` 的 rg usage notes。那里已经写了三个退出码的语义，也写了 `|| true` 会吞掉退出码 2，但**没有写「`&&` 链会把 exit 1 当失败、静默截断后续段」**——而多段搜索拼一条命令正是 `prefer-multiline-scripts` 鼓励的写法，两条规则在这里会互相坑。建议补一句：多段搜索之间一律用 `;` 或换行，不要用 `&&`。

---

## 四、「命令旁边别硬写结论」这条记忆的失效条件写窄了：本会话四次击发全是命令正常、有输出、结论句仍照印

**分级：major（对既有记忆的条件修正）。证据强度：强到可据此行动，四个独立样本、跨三个 agent。**

项目记忆 `never-echo-the-conclusion-beside-the-command` 现在的措辞是「`echo "(空=无残留)"` 在**命令坏掉时**照印」。本会话这 8 份日志里我数到四次击发，**没有一次是命令坏掉**：

| # | agent / 位置 | 命令与结论句 | 实际发生了什么 |
|---|---|---|---|
| 1 | `af92270` RESULT #18 | 循环里 `git grep -n '\.dev/docs' 598b778 -- "$f"` 之后无条件 `echo "   (none above means no .dev/docs path in that file)"` | 第一个文件**有一条命中**，那句「(none above…)」照样紧跟在命中行下面印出来，与紧邻的输出直接矛盾 |
| 2 | `af92270` RESULT #29 | `rg -n -e '\bClientRequest\b' -e '\bUpstreamAttempt\b' src tests \| head -10 ; echo "(empty above = neither name exists)"` | `rg` **命中了一行**（`src/app/pipeline/request.py:7`），结论句仍印「neither name exists」 |
| 3 | `a739e8c` RESULT #41 | `git status --short src tests docs pyproject.toml && echo "(src/tests/docs 无我造成的改动，上面若只有 docs/.human-controlled 的用户改动即为预期)"` | 输出里有 **5 个 `src/`、`tests/` 文件是 `M`**（同伴在调研期间改的），结论句的前置条件不成立却照印 |
| 4 | `a530b39` RESULT #17 | `rg … 2>&1 \| head -30 ; echo "--- exit=$? (1 = no match) ---"` | `$?` 取的是管道最后一段（`head`）的退出码，不是 `rg` 的；这句结论从一开始就不测量它声称测量的东西 |

第 1、2 两条尤其值得记：**结论句与推翻它的输出出现在同一屏、相隔一到两行，而它们照样被写了下来。** 这说明这个坑不是「命令失败时露不出来」，而是**`echo` 无条件执行**这个更朴素的机制——只要结论不是由命令自己的输出承担，它在任何情况下都会印。

**落点建议**：修订项目记忆 `never-echo-the-conclusion-beside-the-command` 的条件描述。把「命令坏掉时照印」改成「`echo` 是无条件的，所以它在命令成功、有输出、且输出直接推翻该结论时同样照印」，并把第 4 条（`$?` 在管道后取的是最后一段）单列——那是同一句话里的第二个缺陷，与结论句是否为真无关。

---

## 五、用 AST 证明一个「只改注释」的提交确实没改代码

**分级：minor（手法），但可复用性高。证据强度：强到可据此行动。**

`af92270` 要核对提交 `598b778` 的自陈「31 lines changed, none of them code」。它没有靠读 diff，而是（RESULT #24）：

```python
files = git show --name-only --format= 598b778
for f in files:
    old = git show 598b778^:f ; new = git show 598b778:f
    # 把每个 Module/FunctionDef/AsyncFunctionDef/ClassDef 的首个 docstring 常量置空
    if ast.dump(norm(old)) != ast.dump(norm(new)): bad.append(f)
```

输出：`files in commit: 20` / `files whose code (AST minus docstrings) differs: NONE`。

**它证明了什么**：这 20 个文件在「清空 docstring 之后」的抽象语法树逐字节相同——比逐行读 diff 强，因为它对空白、换行、引号风格免疫，也不会被一个夹在代码中间的注释块骗过。

**它不能证明什么**（我补的，日志里没写）：`#` 行注释本来就不进 AST，所以「AST 全等」并不等价于「只动了注释」——它等价于「没动语义」。另外脚本对提交里的每个文件都 `ast.parse`，一旦提交里混进非 `.py` 文件就会抛异常而不是漏过，这次没混进（20 个全是 `.py`）。

**落点建议**：值得单独留，但**不必进记忆**——它是一个成品配方而不是一条纪律。建议抄进 `.dev/docs/server-layout/probes/`（那里已经是本项目探针脚本的落脚点，且该目录的 README 已经在讲「探针能证明什么、不能证明什么」），或者放进 `project-review-principles` 作为「核对一个自称 docs-only 的提交」的手法。

---

## 六、`fd` 的默认过滤让 `docs/` 返回空，而这个空恰好与一句为真的叙述同形

**分级：minor。证据强度：强到可据此行动（这是一个具体样本，机制本身在 user rules 里已有）。**

`a168f02` RESULT #4：`fd . docs --type f | sort` 输出**空**。RESULT #5 换成 `fd . docs --type f --hidden --no-ignore` 后列出 14 个文件——`docs/` 下唯一的内容是 `.human-controlled/`，一个点开头的目录，被 `fd` 默认跳过了。该 agent 当场看出来了（「`fd` skipped hidden dirs」）。

**这个样本的价值不在机制**（`fd` 默认跳隐藏文件已经写在 user rules 的 fd usage notes 里），**而在于假答案与真叙述同形**：同一天的提交信息 `bbf5f50` / `fa0b281` 里明写着「`docs/` has been empty since 0b01cdc」，而这句话是**真的**（在那个时点、对被追踪内容而言）。于是「`fd` 说 docs/ 是空的」与一句已知为真的叙述完全吻合，一个不做第二次搜索的人没有任何理由起疑。

**落点建议**：不值得单独立一条记忆——`fd` 的默认过滤已有条目，再加一条会稀释。建议**作为例子并入**现有的 fd usage notes，或者更省事：不留。理由是这条的教益（「空输出与一句为真的叙述吻合时最危险」）已经被第三节和 `probes/README.md` 那句「部分正确的假结果比全错的更难识破」覆盖，形态更一般。

---

## 七、`git update-ref` 移动分支不带 `-m`，reflog 里留下的是一条空消息条目

**分级：minor。证据强度：强到可据此行动（单条输出，但事实无歧义）。**

`a530b39` RESULT #20，`git reflog show main | head -8`：

```
53dd99c main@{0}:
30f251c main@{1}: commit: refactor: say synthetic what, and stop naming the module after its only occupant
25432d4 main@{2}: commit: docs: point the deadline comment at a branch that exists
…
2afa0c4 main@{5}: commit (amend): refactor: make the delivery loop ask which client it is answering
1e544a7 main@{6}: commit: refactor: make the delivery loop ask which client it is answering
```

`main@{0}` 冒号后面**什么都没有**。那一步正是本次拆分用 CAS `git update-ref refs/heads/main <new> <old>` 移 ref 的动作——`update-ref` 不带 `-m` 就不写 reflog 消息。

**后果**：整段历史改写在 reflog 里是唯一一条**没有任何自述**的条目，而它上下每一条都写着 `commit: <标题>`。事后要从 reflog 复盘「main 是什么时候、被什么动作移到这里的」，这一条什么也不说。

**顺带一条同源观察**：`main@{5}` 是 `commit (amend)`，`main@{6}` 是同标题的原始 `commit`——所以 `2afa0c4` 本身是一次 amend 的产物。这解释了为什么拆分方要同时保住 committer date（`range-diff` 不查这一项）。

**落点建议**：写进 `consolidating-commits-in-a-shared-history` 或 `rewriting-history-while-a-peer-commits` 技能——这两份都把 CAS `update-ref` 当作推荐做法，应当在同一处补一句「一律带 `-m '<为什么移>'`，否则 reflog 里这一步是哑的」。这是低成本、纯增益的补充。

---

## 八、三个 agent 独立测出的同一组可达性数字差 1，口径是「是否把裸 `app` 计入」

**分级：minor（已被文件覆盖，但活文档里的残留不一致仍在）。证据强度：强到可据此行动。**

三次独立测量：

| 来源 | `app.cli` | `pipeline_app` | `app_factory` | 探针谓词 |
|---|---|---|---|---|
| `a739e8c`（RESULT #9、#26、#42） | 140 | 127 | 141 | `m == 'app' or m.startswith('app.')` |
| `acb051a`（RESULT #32） | 139 | 126 | 140 | `n.startswith('app.')` |
| `a11c4f0`（RESULT #18，在 `1f29d0a` 的 `git archive` 副本树与工作树上各跑一遍，两边全等） | 140 | 127 | 141 | `m == 'app' or m.startswith('app.')` |

差值恒为 1，就是裸 `app` 包根。

**这条已经进了文件**：`.dev/docs/server-layout/reports/260822-review-layout-proposal-facts.md` 的 B1 把差值、原因、以及「README 与自己指名的支撑报告在同一张表上给出不同的数」都写清楚了。**所以它不是新的非文件知识。**

**但残留的不一致还在**：`.dev/docs/server-layout/README.md:76` 起的 §3.3 表格今天仍写 `139 / 126 / 140`，且**没有口径注**；而它同一节引用的 `reports/260822-server-layout-chain-map.md` 写的是 140/141。B1 的处置似乎没落到 README 上。

**落点建议**：这不是「非文件知识候选」，是一条**给主会话的活文档修订项**——在 §3.3 表头加一句口径（「不含包根 `app` 自身」或改成含），或按 B1 的建议直接对齐。列在这里是因为我是在读日志时撞上的，且三份材料的数字分歧会让后来人以为有人算错。

---

## 九、`rg -g '!.git/**'` 搜索子目录时不生效，`.dev/.git/` 的内容混进了结果

**分级：minor。证据强度：强到可据此行动。**

`a530b39` 在核对「`.dev` 里还有哪些文件带着旧哈希」时先跑（RESULT #15）：

```bash
rg --hidden --no-ignore-vcs -n -e '2afa0c4' … .dev/ --glob '!.git/**'
```

结果里出现了：

```
.dev/.git/COMMIT_EDITMSG:3:Splitting the main repository's 2afa0c4 changed every hash from there to the
.dev/.git/COMMIT_EDITMSG:6:with, and tmp/260822-split-2afa0c4-hash-map.md is what decodes them.
```

后来它改成 `--glob '!.dev/.git/**'`（RESULT #29），结果干净了（4 个文件）。

**机制**：rg 的 glob 里含 `/` 就锚在**搜索起点**（这里是仓库根，因为命令前面有 `cd 仓库根`），`!.git/**` 只能排除 `./.git/…`；被搜索的实际路径是 `.dev/.git/…`，锚不上。

**为什么归入「命令跑了、输出真实、结论仍错」**：这次的污染项恰好是 `COMMIT_EDITMSG`——它含有刚写完的那条提交信息，所以**内容看起来完全像一份正当的残留**。如果不去看路径的前两段，会把「`.dev` 里还有 2 处旧哈希未处理」记进结论。

**落点建议**：并入 user rules 的 rg usage notes（与第三节那条一起补，同一小节）。措辞要点：glob 锚在搜索起点而不是被搜索的路径参数，所以给 `rg PATTERN sub/dir/` 加排除时，glob 必须写成从起点算起的完整相对路径。

---

## 十、余下的观察（分级较低，逐条给落点）

### 10.1 共享树上量测的收尾纪律：发现被测文件被同伴改过就重跑全量探针

**minor。强到可据此行动。** `a739e8c` 写完报告后跑 `git status --short src tests docs pyproject.toml`（RESULT #41），发现 `cli.py`、`server/handler.py`、`server/pipeline_app.py`、`pipeline/direct_driver/base.py`、`tests/unit/pipeline/test_client_request_headers.py` 五个文件在它调研期间被同伴改过——**与它开工时（RESULT #1）的 `git status` 不是同一组文件**。它随即重跑了全量探针（RESULT #42），确认 `modules 235 / cli 140 / factory 141 / shared 73 / new-only 67 / old-only 68 / dead 27` 与 `app_factory production importers: []` 逐项不变，并把时效声明写进了报告。

这是记忆 `a-blocking-observation-has-a-shelf-life` 的**正向样本**（那条记忆记的是反面）。**落点**：不必单独立条目；建议作为一句例证并入该记忆，或写进 `.dev/docs/server-layout/probes/README.md` 的跑法一节（「在共享树上量测：收工前 `git status` 对一遍被测文件，动过就重跑」）。

### 10.2 用提交频次量化共享树搬迁的碰撞风险

**minor。强到可据此行动。** `a656a8f` RESULT #28，`git log --since=2026-08-20 --oneline -- <file> | wc -l`：

| 文件 | 提交数（8-20 起） |
|---|---|
| `src/app/server/pipeline_app.py` | 31 |
| `src/app/server/handler.py` | 20 |
| `src/app/server/composition.py` | 17 |
| `src/app/cli.py` | 14 |
| `src/app/server/inbound.py` | 1 |
| `src/app/server/tls.py` | 0 |
| `src/app/server/ops_routes.py` | 0 |

它据此判定第 8 节的步骤顺序有实质缺陷（最贵、最容易撞车的那步被排在唯一一道裁决之后）。**落点**：这些数应该在 `.dev/docs/server-layout/` 的 design 评审报告里（我未逐字核）。方法本身（churn 当碰撞代理，配日期基线）值得在 status/plan 里留一句，因为它会被下一次搬迁重用。

### 10.3 主仓 `git worktree list` 里挂着一个 `~/.claude/jobs/` 下的 detached worktree

**minor。强到可据此行动（我另在 2026-08-23 现场复核过，仍然存在）。** `a530b39` RESULT #18：

```
/home/xp/.claude/jobs/826d4cda/tmp/review    7839b02 (detached HEAD)
```

`7839b02` 是 2026-08-18 的 `docs: point at where the harness actually lives`，不含 `2afa0c4`、不含 `e7cf57a`。它不是本项目的 worktree 约定（`.claude/worktrees/` 或 `a/…` 分支），是某个 job 留下的。**2026-08-23 复核**：`git worktree list` 里它仍在，目录 `/home/xp/.claude/jobs/826d4cda/tmp/review` 仍存在；同时主仓的 `.claude/worktrees/` 已从 2 棵长到 4 棵（新增 `260822-never-silent-upstream-failure`、`one-ending`）。**落点**：`.dev/docs/git-housekeeping/` 的待办，或收尾清单的一行。**不要**直接删——按 `no-accidental-data-loss`，先确认那个 job 已结束。

### 10.4 主仓 git 无法为 `docs/.human-controlled/` 里的任何一句断代

**minor。强到可据此行动。** `ab3a3e2` RESULT #21：

```
$ git log --format='%h %ad %s' -- docs/.human-controlled/client-side-block-delivery.md
fa0b281 2026-08-22 docs: put the user-controlled requirement documents in the repository
$ git log -S'只在第一次 HTTP 200 尝试时转发响应头' -- docs/.human-controlled/client-side-block-delivery.md
fa0b281 2026-08-22 docs: put the user-controlled requirement documents in the repository
```

整个目录是一次进仓的，所以「这句话是用户什么时候写的」在主仓 git 里只有一个答案——进仓那一刻。这直接限制了同一天两条判断的可靠性：`ab3a3e2` 报的那条**最重要的意外发现**（`spec.md:285/348` 与 `architecture.md:397/442` 冻结的「首块前不得暴露 HTTP success headers」，与用户亲笔的 `client-side-block-delivery.md`「只在第一次 HTTP 200 尝试时转发响应头」正面相反），它的断代只能靠 mtime；`acb051a` 判断「用户 12:48 编辑 `module-org.md` 时是否已知情」时，用的也是 mtime（12:48）而不是 git。

**这是既有记忆 `git-log-is-blind-to-a-never-committed-file` 与 `locating-a-version-by-line-numbers` 的一个新形态**：文件被追踪、`git log` 也有输出，但**只有一条**，于是「什么时候写的」这个问题的分辨率是整份文档。**落点**：值得在 `.dev/docs/server-layout/decisions.md`（或承载那条 spec-vs-用户文档冲突的地方）留一句 provenance 说明——凡涉及「用户是不是知情地写下这句」的判断，主仓 git 给不出答案，只有 mtime 与主 transcript。

### 10.5 探针「先证明自己跑在哪棵树」的成品配方（含取历史提交的变体）

**minor。强到可据此行动，但**大部分已被 `probes/README.md` 覆盖**。** `a11c4f0` 的做法（RESULT #16、#17、#18）三件套：

1. **正样本对照**：直接 `import app.routes` / `app.core` / `app.config`，确认探针在它们真被导入时看得见（9 个 `app.routes.*`、1 个 `app.core`）；此后所有的 0 才是有分辨力的 0。
2. **取历史提交到独立目录**：`git archive 1f29d0a src | tar -x -C /tmp/rev1f29d0a`，再 `PYTHONPATH=/tmp/rev1f29d0a/src uv run --no-project python …`。
3. **探针自报 `app.__file__`**，每一行输出都带上它，证明测的是哪棵树；并在 pinned 树与工作树上各跑一遍，两边 140/127/141 全等。

`.dev/docs/server-layout/probes/README.md` 已经覆盖了 `--no-project` 的由来（第 2 条假数字机制：`uv run --project <主仓>` 在临时 worktree 里跑会把主仓的 `src` 放进路径）和 `app.__file__` 正样本。**没覆盖的是第 2 步**——用 `git archive … | tar -x` 而不是 worktree 取历史树，从根上避开「临时 worktree 缺 `pyproject.toml`/依赖漂移」那一整类问题。**落点**：给 `probes/README.md` 的跑法一节补一个「要量某个历史提交时」的三行变体。ROI 高、改动面一行。

### 10.6 `_dispatch` 的行数在同一天内从 418 变成 428

**nit。仅存档。** `a11c4f0` 在 `1f29d0a` 上量到 418（RESULT #15），`a656a8f` 一小时后在工作树上量到 428（RESULT #11）。两份报告各写一个数，都对。README §3.2 写的是 418 并标了基线。**落点**：不值得单独留；仅作为「报告里的行数是快照」这条既有纪律的又一个例子。

### 10.7 harness 的大输出落盘产物

**nit。仅存档，不用于任何决策。** 两次 `git show 598b778`（30.3 KB / 30.7 KB）被 harness 转存成 `…/be410f2e-…/tool-results/bzj71phho.txt` 与 `b5ch5p042.txt`，agent 再用 `Read` 读回。这些文件仍在会话目录里。**落点**：不留。它们是 transcript 的附属物，会随会话归档一并处理。

---

## 十一、与已有三份材料的对账

（本节在完成上面全部枚举之后才动笔，顺序未倒。读的是作者处置记录 `260823-session-closeout-nonfile-candidates.md`、评审 A `260823-nonfile-candidates-review-A.md`、评审 B `260823-nonfile-candidates-review-B.md` 三份全文。）

### 11.1 先说两位评审的自陈盲区，边界比他们写的更细

- **评审 B** 写得最准：「8 份 subagent 日志的正文我没有逐份读……我只读了它们经 `task-notification` 回到主线程的摘要」，并明确「**建议第三轮专门补这一面**」。
- **评审 A** 的自陈有一处需要修正：它在文首「事件源」里写「+ 同目录 `subagents/` 下 9 份 agent 日志（含我自己那份）」，读起来像是读了；但正文末尾的能力边界写的是「**8 份 subagent 日志我只读了 4 份的最终文本**，其余靠主转录里的 task-notification 摘要」。后者才是它实际做的。**这两句在同一份报告里对不上**，一个只读文首的人会以为 A 已经覆盖了这一面。

**因此本轮的定位是**：A 与 B 手上有的，最多是这 8 个 agent**回到主线程的摘要**（外加 A 读过其中 4 份的最终文本）。下面凡我标「新」的，都要再分一层：是**只在日志正文里可见**，还是**摘要里有过、但 A 与 B 都没收**。这两者的处置轻重不同。

### 11.2 逐条对账表

| 本文 | 一句话 | 在作者清单 | 在评审 A | 在评审 B | 判定 |
|---|---|---|---|---|---|
| §1 subagent cwd 落在四个目录、五次在 `.dev` | | 无 | 无 | 无 | **新（只在日志正文可见）** |
| §2 静态图缺祖先包边 → 五个候选全报「无环」 | | 无 | A7/E7/m16 记的是**结论**与「读 `request.py:17` 一行即可定案」 | 类 1 记「分层倒置，重合 1.2」；末行「做变异实验证 F1 的 import 环｜未列（价值中等）」 | **新（第一次运行的反向结论只在正文；再导出条件在摘要里有过，两人都没收）** |
| §3 `rg` 退出 1 把 `&&` 后续段静默吃掉 | | 无 | 无 | 无 | **新（只在正文）** |
| §4 「命令旁边硬写结论」的失效条件写窄了 | | 有（记忆已存在） | C19，**但条件写的是「命令坏掉时照印」**，且计「至少两次」 | 未单列 | **既有条目的实质修正 + 四个实例（正文）** |
| §5 用 AST 证明「只改注释」的提交没改代码 | | 无 | 无（D16 只记审计规模） | 无（A2 只讨论 20/12 的文件数） | **新（摘要里有过一句，两人都没收）** |
| §6 `fd` 默认跳隐藏目录让 `docs/` 返回空 | | 3.5（`fd` 不加 `-I` 少报 3 个） | C18 同上，是 `-I` 那个实例 | 类 3「`fd` 少报」重合 3.5 | **同族的另一个实例，机制已有载体。建议不单独留** |
| §7 `git update-ref` 不带 `-m`，reflog 条目为空 | | 无 | 无 | B8 记了护栏要 `GIT_DISCIPLINE_OK=1` 才放行 `update-ref`，未涉及 `-m` | **新（只在正文）** |
| §8 139/126/140 vs 140/127/141 的口径差 | 无 | **D5 写 139、F10 写 140，同一份报告里并存未察** | **B21 写 139/126/140、类 6 写 140，同一份报告里并存未察** | **见 11.3，判定升级** |
| §9 `rg -g '!.git/**'` 搜子目录时锚不上 | | 无 | 无（C5 是 Python `rglob` 走进 worktree，另一回事） | 无 | **新（只在正文）** |
| §10.1 发现被测文件被同伴改过就重跑全量探针 | | 无 | B1–B4 记的是**误归因**那一面 | 无 | **新（正方向的纪律，只在正文）** |
| §10.2 用提交频次量化搬迁碰撞风险 | | 无 | D14 有「`handler.py`/`pipeline_app.py` 两天内 31 次提交」 | 无 | **部分已有（缺完整七行表与方法）** |
| §10.3 `~/.claude/jobs/826d4cda/tmp/review` 挂在主仓 worktree 列表里 | | 无 | 无 | 无 | **新（只在正文）** |
| §10.4 主仓 git 无法为人写文档里的任何一句断代 | | 无 | G1 记的是那条冲突本身 | B17 记的是「文档错、代码对」 | **新（只在正文）** |
| §10.5 `git archive` 取历史树 + 探针自报 `app.__file__` | | 无 | C14 记 `uv run --project` 那次失效 | B11 记 `18:40:46` 在临时 worktree 里先打印 `app.__file__` | **部分已有（`git archive` 变体是新的）** |
| §10.6 `_dispatch` 418 → 428 的当日漂移 | | 无 | 无 | B21 记 418 → 416 → 369 | **nit，不值得单留** |

### 11.3 §8 需要升级：不是「已被覆盖」，而是「覆盖在一份没人往下读的点时刻报告里，分歧此后又扩散了三份」

我在第八节原本判它「已被文件覆盖，只剩活文档残留」。读完 A 与 B 之后要改判，理由是三条新事实：

1. **评审 A 在自己一份报告里同时写下 139 与 140 而没有察觉**：D5「`app.cli` 加载 139 个模块」，F10「与真解释器 `sys.modules` 做逐个全等对照（**140** 个模块）」。
2. **评审 B 同样**：B21「`app.cli` 加载 **139** 个模块……`app.server.app_factory` **140**」，类 6「真解释器 `sys.modules` 与静态 import 图 **140** 个模块逐个全等」。
3. **`.dev/docs/server-layout/README.md:76` 起的 §3.3 至今仍是 139/126/140 且无口径注**，而同一节点名引用的支撑报告写的是 140/141。

所以现状是：**唯一说清楚这件事的地方是 `260822-review-layout-proposal-facts.md` 的 B1（一份按规矩不回填的点时刻报告），而它下游的四份文档——README、评审 A、评审 B、以及 `src/.archived/README.md`（评审 A 的 m5 已经独立发现那里还有第三个数 151）——没有一份带着口径。**

这条与评审 A 的 M4（`chain.py` 的 104/81 vs `status.md` 的 106/83）**是同一族、不同实例**：同一个测量在两处以差一个常数的两个值存在，差值来自「数不数包根/数不数被 import 的模块自身」，而两处都标「measured 2026-08-22」。A 已经为 104/81 那一对开了条目并给了处置（补 provenance）；**139/140 这一对没有人开条目**，而它牵着的是归档判据的原始标定，比 104/81 更承重。

**分级：major。落点建议**：在 `probes/README.md` 的跑法一节写死一句口径（「本目录所有模块数**不含**包根 `app` 自身」或相反），然后把 README §3.3、`src/.archived/README.md` 按同一口径对齐并各带一个测量锚点。**不要去改评审 A、B 与 `260822-…-facts.md`**——那三份是点时刻记录。

### 11.4 我能从日志正文替作者/评审**佐证**的两条

这不是新发现，是给已有判断补一个他们手上没有的证据源。

1. **评审 A 的 B5「驳回事实核查员关于 `copilot-api-js` 仍在服务的主张，理由是他从 JS 仓库源码推断、没查实际在跑什么」——日志正文完全支持这个驳回。** 那位事实核查员（`a11c4f0`）的最后一条实质命令是 RESULT #42：

   ```bash
   cd /home/xp/src/copilot-api-js && rg -ln 'v1beta/models|/openai/deployments|api/status' src
   ```

   输出是十个 `.ts` 文件名。**它从头到尾没有对任何运行中的进程做过观测**——没有 `ss`、没有 `/proc`、没有一次 HTTP 请求。作者驳回它是对的，而且驳回的理由在日志里可以逐字坐实。

2. **评审 B 的 B27「`lifecycle/rolling/` 不止剩 `__pycache__`，还有一个 `generation/` 子目录」——正确。** 两个 subagent 的原始输出都印着它：`acb051a` RESULT #20 的 `ls -R` 与 `a11c4f0` RESULT #9 的 `find`，都显示 `rolling/generation/__pycache__/` 下另有五个 `.pyc`。两位 subagent 报告里「无 `.py`、无 git 追踪文件」这句是准的，松掉的是「只剩 `__pycache__`」这个措辞。B 的 nit 成立。

### 11.5 我**没有**在日志正文里找到的东西（阴性结论，同样是结论）

按任务要求，六类里有几类我在这 8 份日志里**几乎一无所获**，如实记下，因为「没有」也是覆盖面信息：

- **第 4 类（本会话产生或修订的标定值）**：这 8 个 agent 产出的标定值几乎全部进了它们的报告文件与回主线程的摘要，评审 A 的 D 组与评审 B 的 B21 已经收得相当全。**我从正文里没有捞到任何一条有承重、而两位评审都没有的标定值**——唯一的例外是 §8 那个口径分歧，而那是关于已有标定值的元信息，不是新标定值。
- **第 5 类（实际执行过的变异）**：**零**。这 8 个 agent 全部被约束为只读，没有一个做过变异实验。`a656a8f` 明确写下「要变成一手证据须在主树写一个临时 `selection.py`，我按只读约束没有做——若要我做，请明确授权」，这已被评审 A 收作 m16。**「一批只读 agent 结构性地做不了变异」本身是一条关于方法的事实**，但它不构成候选条目。
- **第 6 类（运行时/外部能力探测）**：正文里的探测全部集中在 import 可达性这一件事上（§2、§10.5、§8），且它们的**结论**都进了报告。评审 B 的 B8/B9（护栏行为边界）是主线程自己撞出来的，不在这 8 份日志里——**这 8 个 agent 一次都没有撞到护栏**。这条是穷举得出的：8 份日志里 `is_error==true` 的工具结果共 **13** 段，逐段读过，全部是命令自身的退出码：

  | 退出码 | 段数 | 是什么 |
  |---|---|---|
  | 141 | 3 | `… \| head -N` 造成的 SIGPIPE |
  | 128 | 2 | git fatal：一次是 `CLAUDE.md` 在该提交里不存在，一次是跨仓 `git show fea4e4a`（见 §1） |
  | 2 | 4 | 路径不存在：`rg … scripts`（该目录不存在）两次、`ls <报告文件>` 预检两次 |
  | 1 | 4 | `rg` 无匹配两次、Python `KeyError` 一次（见 §2 的第一次崩溃）、`diff` 有差异一次 |

  **没有一段是护栏拒绝。** 这也解释了为什么护栏知识这一大块（评审 B 的 B8、B9、B25、B26）完全不在本轮的收成里。

**所以：本轮的收成集中在第 1、2、3 类，第 4、5、6 类基本为空。** 这与派发时的预期（「调查/评审类 agent 的路线否决密度高」）方向一致，但幅度小于预期——**主要原因是这 8 份日志的 `thinking` 内容全部未落盘**（见第〇节盲区 2）。本会话这 8 个 agent 横跨 gpt-opus 与 general-opus 两种类型，**两种类型、8/8 全部如此**，所以这不是个别现象；于是「试了三条路才选中一条」这件事只有在**每条路各留下一条命令**时才可见，纯在脑子里否决的路线一条也捞不到。这是本轮方法的硬上限，也是评审 A 在它自己的能力边界里预判到的那一点（「gpt-opus 类 agent 的 thinking 不落盘，所以它们内部的放弃路线与探针失败我看不到」）——**A 的预判是对的，而且这个上限对读正文的我同样成立；只是它还漏了一半，general-opus 也一样不落盘**。

---

## 十二、结论与处置建议

**VERDICT: needs-fix**（针对作者的处置记录，不针对两位评审的报告——那两份是点时刻记录）。

**8 份日志正文里确实有前两轮未覆盖的东西，但没有前两轮那种量级的遗漏。** 具体：**9 条新条目（另 1 条新实例我建议不留）+ 1 条既有条目的实质条件修正 + 1 条判定升级 + 2 条对已有条目的补充**，其中 major 5 条（§1、§2、§3、§4、§8）。这与评审 A 的 21 组、评审 B 的 27 条不在一个量级，**原因不是我查得浅，是这批 agent 的 thinking 内容全部未落盘**（见 11.5）。

另外本轮还产出两条**佐证**（11.4）：从日志正文坐实了作者驳回「`copilot-api-js` 仍在服务」的理由，以及评审 B 的 B27 成立。这两条不新增条目，但它们给已有判断补了一个 A 与 B 手上没有的证据源。

按我的优先级排序，不代替作者裁决：

| 序 | 条目 | 分级 | 落点建议 |
|---|---|---|---|
| 1 | §1 subagent cwd 落在四个目录、五次在嵌套独立仓 `.dev` 内 | major | 新记忆，或并入 `dev-state-lives-in-dot-dev.md`；派发提示词那句开场白定为模板 |
| 2 | §8 判定升级：139/140 的口径差已扩散进四份文档 | major | `probes/README.md` 写死口径；README §3.3 与 `src/.archived/README.md` 对齐并各带锚点。**与评审 A 的 M4 是同族，建议一次处理** |
| 3 | §2 静态图缺祖先包边给出反向结论 | major | `probes/README.md`「被击穿过四次」一节加为**第五类盲区**，附两次运行的原始输出 |
| 4 | §3 `rg` 退出 1 把 `&&` 后续段吃掉 | major | `~/.claude/rules/00-user/20-tool-use-preference.md` 的 rg usage notes，与 §9 合并成一小节 |
| 5 | §4 「命令旁边硬写结论」的失效条件修正 | major | 修订记忆 `never-echo-the-conclusion-beside-the-command`：`echo` 无条件执行，命令成功且输出直接推翻结论时同样照印；`$?` 在管道后取的是最后一段 |
| 6 | §9 `rg -g` 的 glob 锚在搜索起点 | minor | 同第 4 项，合并 |
| 7 | §5 AST 证明「只改注释」的提交 | minor | 抄进 `.dev/docs/server-layout/probes/`，或 `project-review-principles` 的手法一节 |
| 8 | §7 `git update-ref` 一律带 `-m` | minor | `consolidating-commits-in-a-shared-history` 与 `rewriting-history-while-a-peer-commits` 两份技能里都推荐 CAS `update-ref`，在同一处补一句 |
| 9 | §10.4 人写文档在主仓 git 里不可断代 | minor | `.dev/docs/server-layout/decisions.md`（承载那条 spec-vs-用户文档冲突的地方）补一句 provenance |
| 10 | §10.3 `~/.claude/jobs/` 下的游离 worktree | minor | `.dev/docs/git-housekeeping/` 待办。**先确认那个 job 已结束再动** |
| 11 | §10.1、§10.2、§10.5 | minor | 各补一句：§10.1 并入记忆 `a-blocking-observation-has-a-shelf-life` 作正向例；§10.2 的七行表进 server-layout 的 status/plan；§10.5 给 `probes/README.md` 跑法一节补 `git archive` 变体 |

**我明确不建议做的：**

- **不要**为 §6（`fd` 跳隐藏目录）单开条目。机制已有载体，再加一条只会稀释既有的 fd 条目。
- **不要**去改评审 A、评审 B、`260822-review-layout-proposal-facts.md` 这三份点时刻报告里的任何数字。§8 的分歧要在活文档一侧收口。
- **不要**因为本轮只找出 9 条就认为「subagent 日志这条路不值得走」。真正的限制是 thinking 不落盘（11.5），**换一个会落盘 thinking 的模型跑同类 agent，这条路的产出会完全不同**——这一点值得作者知道，因为它影响的是**下一次派发时选哪种 agent**，而不是这一次的收尾。
- **不要**在收尾流程上加门。作者这次做对的顺序（先落清单、再派独立评审、评审共同点名盲区、再派第三轮专攻）本身就是有效的，它靠的是判断而不是阻断。

**作者第四节「未闭合」第 1 项（8 份日志正文从未被枚举）可以关闭**，代价是接受 11.5 那条硬上限：**这 8 份日志里「纯在脑子里否决、没留下命令痕迹」的路线，任何人都取不回来了。**


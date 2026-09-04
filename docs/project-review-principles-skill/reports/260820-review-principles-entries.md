# 评审：`project-review-principles` 新增的两个条目

评审对象：`.claude/skills/project-review-principles/SKILL.md` 未提交改动中的

- `## declined-and-adopted-findings-can-share-one-blind-spot`（下称**条目 3**）
- `## a-broken-test-needs-its-scenario-and-expectation-rechecked`（下称**条目 4**）
- 同一改动里 `### 当前状态` 的更新与新增的 `### 数量与快照`

不在范围：前两条既有条目（`one-reply-fact-...`、`assertions-about-copilot-wire-...`），仅作体例参照；但 `### 数量与快照` 对它们作出了合规声称，那部分声称在范围内。

判据：文件自己的「进来的门槛」三条 + 「退出的判据」。

环境：仓库 `/home/xp/src/ghc-api-proxy-py`，`HEAD=b02db7b`（工作树对该 SKILL.md 有未提交改动），ripgrep 15.2.0，2026-08-20T18:52+00:00。只读评审，未修改仓库任何文件，实验全部为读命令。

结论摘要：**needs-fix**。3 blocker = 0，major = 3，minor = 6，nit = 2。三条 major 都不是「判据错了」，而是「命令与它自称的判据对不上」——两条命令在当前仓库结构下都够不着自己的立条实证，另有一句权重论证被自身实证证伪。判据本身我认为都成立，实证核对逐项属实、没有张冠李戴。

---

## 一、逐条实测记录（命令原样复制执行）

### 1.1 条目 3 命令 A

```bash
rg -n --glob '!**/archived-*/**' --glob '!**/reports/**' --glob '!**/archive-*/**' \
   -e '记录但不改' -e '不采纳' -e '仅备案' -e '记录即可' -e '不补的理由' .dev/docs
```

输出（exit 0），**恰好 1 行**：

```
.dev/docs/graceful-shutdown/client-side/README.md:78:- **给另外三处关连接的地方也加探测**（…）**不补的理由**：这个数字结构上不可能完备，…
```

### 1.2 条目 3 命令 B

```bash
rg -n --glob '!**/archived-*/**' --glob '!**/reports/**' --glob '!**/archive-*/**' \
   -e '进 incidents' -e '是下界' -e '新增.*计数' -e '这个数就是' .dev/docs
```

输出（exit 0），**3 行**，均在同一文件：

```
.dev/docs/graceful-shutdown/client-side/README.md:61:### `severed_connections` 是下界，不是总数
.dev/docs/graceful-shutdown/client-side/README.md:78:- **给另外三处关连接的地方也加探测**…
.dev/docs/graceful-shutdown/client-side/README.md:85:- **我三次把一个数字的含义说大了**…「这个数就是那个数」→ 证伪；…
```

两条都可跑、都给出候选。文中「A 打出 `README.md:78`，B 打出同文件 `:61`」与实测一致（B 另有 `:78`、`:85` 两行文中未提，属子集陈述，不算错）。

### 1.3 条目 4 命令

原样执行（`git log -25` 窗口），exit 0，打出 9 个提交：

```
  b02db7b feat: answer an unrunnable search as a failed tool rathe
      -def test_a_model_not_listed_as_searching_refuses_rather_than_answering_anyway() -> None:
      -    assert response.status_code == 400
      -    assert orjson.loads(response.content)["error"]["code"] == "server_tool_capability_unavailable"
  8a36fe3 chore: move the GOAWAY investigation out of the branch i
  b97930b fix: let the line's verdict decide how the whole line re
      -    assert "↓" not in format_completion_line(base)
      …
  ea0417c feat: say on the line which endpoint a count came from
  40681ce refactor: call the count line's ending what the config c
  783f023 fix: make each of the three upstream timeouts guard the
  9e3d374 fix: say why a token count is an estimate, not just that
  d3335b6 feat: say which counter answered a token count
  064ba63 fix: refuse a search this endpoint cannot run, instead o
  16e87a5 fix: stop the domain-restriction default from disabling
```

可跑、有用。`d3335b6` 与 `8a36fe3` 只出提交头、无 `-assert` 行——正是条目自己点名要优先看的「夹具动了而断言没动」那一形态。噪音率：`-25` 窗口 9/25 命中，`-70` 窗口 33/70，与「打出来的多数是正当的」相符，作为候选生成器合格。

### 1.4 rg 隐藏目录与 glob 锚定的两个警告

**警告一（`--glob '.dev/docs/**'` 配 `.` 搜索根命中零行，rg 不报错）——属实。** 实测：

| 命令 | 结果 |
|---|---|
| `rg -n --glob '.dev/docs/**' -e '不补的理由' .` | 0 行，**exit 1**（no match，非 error 的 2），无任何 stderr |
| 加 `--hidden` 单独 | 仍 0 行，exit 1 |
| 加 `--no-ignore` 单独 | 仍 0 行，exit 1 |
| 加 `-uu` | 2 行，exit 0 |
| 显式路径参数 `.dev/docs`（文中写法） | 2 行，exit 0 |

两个成因文中都点到了且都成立：`.dev` 以点开头（隐藏过滤），且 `.gitignore:26:.dev/` 命中（`git check-ignore -v .dev` 证实）。单开任一开关都不够，必须两个都掀（`-uu`），这一点比文中说得还严一格，文中「写成显式路径参数正是为此」的处方正确。

**警告二（`!archived-*/**` 必须写成 `!**/archived-*/**`）——处方属实，解释反了。** 实测对照（搜 `incidents`，根 `.dev/docs`）：

| 写法 | 命中文件数 |
|---|---|
| `!**/archived-*/**` `!**/reports/**` `!**/archive-*/**` | 1（只剩 README.md） |
| `!archived-*/**` `!reports/**` `!archive-*/**` | 7（6 个 `reports/` 下的文件全部漏排） |

即：非锚定写法确实排不掉嵌套目录，处方对。但原因见发现 F5。

---

## 二、发现

### F1【major】条目 3 的命令排除了 `reports/`，因而结构性地看不到本仓的处置表——包括它自己的立条实证

**依据。** 条目 3 说「这里只管本仓的复查问题：`.dev/docs/<topic>/` 的活文档里，判「不修」的行与…新增量，有没有配成这样一对」，并把 `reports/` 与 `archive-*/` 一并排除，理由写作「归档与逐字原件不是当前处置」。

但在本仓，**完整的逐条处置表就在 `reports/` 里，而且不是归档**。`.dev/docs/graceful-shutdown/client-side/README.md:135` 自己写明：

> `reports/260820-graceful-shutdown-admission-deadlock.md` | 我的工作记录原件：完整根因、四轮评审的**逐条处置表**、被证伪的断言

实测扫过整个 `.dev/docs`，含处置表的文件只有四个，全部落在 `reports/` 或 `archive-*/` 下（另加 README 的「被否定的方案」蒸馏段）：

```
.dev/docs/archived-2604-rewrite/lib-survey/HANDOVER.md
.dev/docs/graceful-shutdown/client-side/README.md
.dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-review-round2.md
.dev/docs/upstream/h2-goaway/archive-260820/260820-h2-goaway-review.md
```

后果是可实测的：**去掉 `--glob '!**/reports/**'` 之后，命令 A 立刻命中条目 3 自己的立条实证。**

```
260820-graceful-shutdown-admission-deadlock.md:158:## 记录但不采纳      ← 4.4（RST 不修）就在这一节，第 160 行
260820-graceful-shutdown-admission-deadlock.md:190:## 记录但不改
260820-graceful-shutdown-admission-deadlock.md:209:评审同时指出一个**处置组合的漏缝**…
260820-graceful-shutdown-admission-deadlock.md:225:## 记录但不改（评审本人亦不建议现在动）
260820-graceful-shutdown-admission-deadlock.md:313:## 记录但不改
260820-graceful-shutdown-admission-deadlock.md:315:- **S-4（minor）**…
```

而按现在写法，A 只剩 README:78 一行；4.4 那条处置（`admission-deadlock.md:160`，措辞是「按评审本人的倾向**记录不改**」）在任何写法下都够不着。

**噪音不构成排除它的理由。** 去掉 `reports/` 排除后，A 全仓一共 14 行、7 个文件（`README:1, closeout:1, admission-deadlock:6, severed-probe:1, delta-review:4, fix-review-gpt:1, test-rebase:1`）。这是一屏之内、人工可配对的量，与文件自己的「命令给候选，不给结论」相容。

**为什么判 major 而不是 minor。** 文件的进入门槛第 3 条要求「能用可跑的检索命令表达判据，且命令要实测过」。命令能跑、也确实实测过（`:78`/`:61` 那一对是真的），但它够不着本仓存放处置表的那一层，于是这条判据在真实复查里只能靠「作者事先把结论蒸馏进 README」这一前置动作才可用——而那正是复查要检查的东西。

**建议**（择一）：

1. 把排除收窄成 `--glob '!**/archive*/**'`，即只排归档树，保留活跃话题下的 `reports/`；或
2. 保留排除，但在「怎么查」里明说：命令只看活文档里的**蒸馏**结论，完整处置表在 `<topic>/reports/` 下需另跑一遍/另读一遍——并给出那条命令。

顺带：A 的模式串缺 `记录不改`（只有 `记录但不改`），而本仓两种写法都在用，建议补上。

### F2【major】条目 3 的权重论证「多派几个评审不解决它」被它自己的实证证伪

**依据。** 条目 3 的权重段写：

> 依据不是发作频次，而是这个缺口的**类型**：它落在所有单条评审的范围之外，所以「多派几个评审」不解决它。

同段又写明：这个缺口「是第三轮评审在审「回应评审后又改的那批」时才指出来的」。核对原件属实——`reports/260820-shutdown-delta-review.md:193`：

> 另外要指出一个**处置组合的漏缝**：修复文档把旧评审 4.4（RST）记为「不采纳」…同时把 5.5 记为「已采纳」（加计数）。…这不是任何一份评审自己的问题，是两次处置之间的缝。

也就是说：**解决它的恰恰是多派了一轮评审**——一轮以「处置之后的状态」为对象的增量评审。原评审自己说的是「不是任何一份评审自己的问题」，条目把它拔高成了「多派几个评审不解决它」，这一步拔高没有依据，且方向有害：它会劝阻读者去做那个唯一被证明有效的动作。

**建议。** 把那半句收窄成实际成立的表述，例如：「对**同一批原始发现**再多派几个评审不解决它；把评审对象换成**处置之后的状态**才解决——本例正是这样被抓到的。」这样既保住「缺口落在单条发现范围之外」这个成立的部分，又把有效动作留在纸面上。

另：同段「前两轮逐条把关都没有、**也不可能**发现」——第一轮成立（`refused_requests` 是第一轮之后才加的，见 `admission-deadlock.md:205`）；第二轮（`260820-shutdown-mutation-audit.md`，职责是复算变异声称）是**范围外**而非逻辑上不可能。措辞可降为「范围之外」。

### F3【major】条目 4 的 `git log -25` 窗口小于本仓一天的推进量，今天就已经够不着它自己的立条实证

**依据。** 立条实证的那次改动在 `9b8114a`（`fix: let a graceful shutdown finish when a pooled client keeps sending`，2026-08-20 14:43:58 +0000）。实测它在 `HEAD` 历史中的位置是**第 60 位**：

```
  1  b02db7b 2026-08-20 18:44:12  feat: answer an unrunnable search as a failed tool …
 29  693dd0d 2026-08-20  fix: call the severed count a floor, …
 42  89002eb 2026-08-20  feat: count the connections the drain actually cut off
 46  a279de3 2026-08-20  fix: stop calling a 503 the failure and an RST the success
 50  8d8026b 2026-08-20  test: make the idle-connection guard witness the rung it names
 60  9b8114a 2026-08-20 14:43:58  fix: let a graceful shutdown finish when a pooled client keeps sending
```

**四小时 = 59 个提交。** 写下这条的当天，`-25` 已经只覆盖约一到两小时的历史。而条目的定位是「**定期**复查」，不是每小时跑一次。

把窗口放宽到 `-70` 重跑同一段脚本，`9b8114a`、`a279de3`、`89002eb` 全部出现，且形态正是条目自己点名的那种：

```
  9b8114a fix: let a graceful shutdown finish when a pooled client
  （无任何 -assert / -def test_ 行）
```

核实原因：`9b8114a` 对 `test_standalone_process.py` 的删除侧只有夹具行，没有断言行——

```
-        from fastapi import FastAPI
-    child = start_child(port, pidfile)
-                b"POST /health/liveness HTTP/1.1\r\nHost: localhost\r\n"
```

这印证了条目那句「对「夹具变了但断言没变」只能交出提交、交不出位置」是**诚实且准确**的；问题纯粹出在窗口大小上。

**连带影响：退役判据变得不可靠。** 条目 4 的退役条件是「本仓不再有随产品改动而改写既有测试的做法时」，唯一的测量手段就是这条命令。窗口只覆盖一两小时时，「命令输出为空」几乎必然是采样太窄，而不是做法消失——恰好落进文件自己警告的「连续两次没查出违背只是弱信号」那个坑。

**建议。** 改成时间窗而非计数窗，并在旁边说明理由，例如 `git log --since='30 days ago' --format=%h`；或至少把 `-25` 提到 `-200` 量级并注明「本仓 2026-08-20 实测 4 小时 59 个提交，计数窗必须按仓库节奏调」。附带把命令自己的**取数时间**写上，这正是新增 `数量与快照` 一节要求的。

### F4【minor】条目 3 权重段的「唯一一例」不是立条那一例，文中没有点破

**依据。** 权重段写「它们只在写这条时对**唯一一例**验证过配对能力（A 打出 `graceful-shutdown/client-side/README.md:78`，B 打出同文件 `:61`）」。

实测那一对确实成立，但它是 **S-4（另三处不加探测，判不补）× `severed_connections` 是下界**，与「凭什么在这里」讲的 **4.4（RST 不修）× 5.5（新增 `refused_requests`）** 不是同一对（后者见 F1，命令够不着）。读者会自然把「唯一一例」读成「立条那一例」，从而高估命令已被验证的程度。

顺带一个对本条**有利**的观察（nit N2）：A:78 × B:61 本身就是同一事故内**同形的第二次**发生——被放弃的三处探测，正是那个计数看不见的东西。若把它明写出来，条目 3 就不止「单次实证」，进入门槛第 1 条会站得更稳。

**建议。** 一句话点破两对不同，并顺手把第二例收编为实证。

### F5【minor】`!archived-*/**` 的问题不是「不锚定」，恰恰是「被锚定」

**依据。** 文中写「同理 `--glob '!archived-*/**'` 不锚定，必须写 `'!**/archived-*/**'`」。rg 的 glob 沿用 gitignore 语义：**模式中间含 `/` 的，被锚定到搜索根**。`archived-*/**` 中间有 `/`，因此它被锚定，只能排掉搜索根**正下方**那一层；嵌套的 `tui/archive-footer/` 之类排不掉。实测（见 1.4 表）证实排不掉，即处方对，但给出的原因是反的。

这不是纯措辞：一个照着「不锚定」这个理由去推理下一个 glob 的人，会得出错的结论。

**建议。** 改成：「`!archived-*/**` 因模式中含 `/` 而被**锚定到搜索根**，只排得掉顶层那一级；要排任意深度必须写 `'!**/archived-*/**'`。」

### F6【minor】条目 4 是四条里唯一不给上游 skill 指路的，而它的第二层正在 `trusting-a-green-result` 的地盘上

**依据。** 文件 frontmatter 明说「绿灯有没有分辨力（→ `trusting-a-green-result`）」不归本文件管；条目 1 在需要时显式写「⚠️ **此时加载 `trusting-a-green-result`**」，条目 2 显式写「一般方法在 `verifying-authoritative-claims`，本条不重写它」，条目 3 显式写「一般的评审处置方法学在 `adopting-agent-findings`」。条目 4 一个都没写。

而条目 4 的第二层（「变异实测：改写后的版本对该缺陷完全不敏感」）与修法方向（「改完问一句：这一层还剩几条守着？只剩零条就是把守卫搬走了」）正是变异/分辨力那套动作。核对 `trusting-a-green-result` 的目录（`The procedure`、`the mutation does NOT bite`、`you just loosened the criterion`、`Restoring the mutation…`），条目 4 **没有复制**其中任何一段方法（不讲怎么变异、怎么还原），所以不构成门槛第 2 条的违反；但缺一个指路，读者在需要做变异那一步时不知道该去哪儿。

**建议。** 在「修法方向」末尾加一句指路，与条目 1 同体例：「判断改写后的那条还有没有分辨力，是 `trusting-a-green-result` 的地盘，本条只负责指出「场景可能从来没成立过」这个方向。」

### F7【minor】条目 4「什么算违背」第 1 条按字面涵盖一切改名与措辞改动，与「怎么查」自相矛盾

**依据。** 「什么算违背」第 1 条：「一条既有测试被改了，而没有任何地方记下**它此前的绿来自什么**。」按字面，改个测试名、改句 docstring，只要没写下「它此前的绿来自什么」，都算违背。而「怎么查」下面紧接着说「打出来的多数是正当的（改名、措辞、契约本身变了）」。两处对同一批候选给出相反判定。

对照条目 1、2 的「什么算违背」（「某字段只在一种模式下被写」「一个声称外部 wire 的期望值只由手写 fixture 支撑」），那两条都是自带排除条件的，条目 4 这条不是。

**建议。** 收窄成带前提的形式，例如：「一条既有测试**的场景（路由、请求体、时序）被改了**，而没有任何地方记下它此前的绿来自什么。」——纯断言侧的措辞/改名改动不触发。

### F8【minor】`数量与快照` 的合规声称只覆盖「实证段落」，而文件里已经腐坏的行号正好在那之外

**依据。** 新增一节说「**本文写下的任何计数、行号、文件路径**都是当时的快照」，然后声称「上面各条的实证段落按此办：具名到文件与行的地方都带日期」。范围前后不一致：规范面向「本文」，合规只声称「实证段落」。

而实测显示，落在实证段落之外、且**当天就已经腐坏**的引用确实存在（既有条目，仅作为对这节合规声称的检验，不建议在本次改动里去改它们）：

| 位置 | 文中写法 | 今天（`b02db7b`）实际 |
|---|---|---|
| 条目 1 范围段 | `pipeline_app.py:313` 先 `response_payload()`；`:316` 再 `reply_summary()` | `response_payload(` 在 **`:417`**，`reply_summary(` 在 **`:420`**；`:313` 现在是 `count_tokens_reason` 那一行 |
| 「这是什么」 | `translation_driver/responses.py:65-67` 有一处 usage 原样拷贝 | 仍成立（`:65-67` 即 `usage = payload.get("usage")` 三行） |
| 条目 1 修法方向 | 「被两个 assembler 与 whole-body 构造**共三处**调用」 | 一个不带时点的「有多少处」计数，正是这节说「一律不给数」的那种 |

也就是说，这节要防的事（下一个人拿一个没有时点的数字去对账，得出错误结论）在本文件里已经发生了一次，而它的合规声称把那一处划在了覆盖面之外。

**建议。** 二选一：把规范与合规声称的范围对齐（「本文所有 `文件:行` 与计数一律带取数日期」，并顺手给条目 1 那三处补上 `（2026-08-20）`），或明说例外（「实证段落之外的行号是导航用途，不作对账依据」）。**不必**在本次改动里去修条目 1 的内容本身——那超出本次范围。

### F9【minor】条目 3 的第一条退役条件只能由「连续观测不到」支撑，与文件的退出判据相冲

**依据。** 文件「退出的判据」写明只由**可证伪的结构事实**触发，并明确「复查历史本身**不是**退出条件」「连续两次没查出违背只能作为发起退役复核的弱信号」。

条目 3 的退役条件第一条是「评审处置不再产生「判不修」与「新增观测量」两类并存的结果时」。这是关于**将来实践**的陈述，可观测的形态只有「连续几次跑 A 或 B 得到空」——正是被明令排除的那种依据。第二条（「本仓不再用 `.dev/docs/<topic>/` 承载处置表」）是干净的结构事实，可用。

对照：条目 1 两条都是结构事实（模式合并、字段不再进入对外契约）；条目 4 那条虽然也是「不再有某种做法」，但它由 git 历史形态直接测量，且条目自己显式挡掉了弱信号误读（「「最近几次改测试都很正当」不是退役条件」）——条目 3 缺这一句。

**建议。** 要么把第一条降级为「发起退役复核的弱信号」并标明，要么改写成结构事实（例如「评审处置表不再进入本仓、或不再采用「采纳/不采纳」这种逐条形式时」）。

### N1【nit】条目 4 脚本的两处 shell 细节

- `git show --format='' -U0 "$c" -- $changed`：`$changed` 是多行且未加引号，靠词分割生效。路径含空格会碎。本仓路径无空格，今天无害。
- `git show --format='' --name-status "$c"` 对 **merge commit** 默认不输出 diff，于是 merge 会被静默跳过。本项目规矩是 squash-only 集成，今天无害；若哪天引入 merge，会是一处静默漏检，值得在命令旁留一行注释。

### N2【nit】条目 3 可能低估了自己的实证强度

见 F4 末段：A:78 × B:61 是同一事故内同形的第二次。

---

## 三、判定为「没问题」的项（逐项给证据）

### OK-1 两节的命令都真的可跑，且给出有用候选

见 §1.1–1.3 的实测输出。三条命令 exit 0，无 stderr，输出量都在人工可读范围（1 行 / 3 行 / 9 个提交）。**门槛第 3 条「命令要实测过」在「能跑」这个层面成立**；它在「够得着立条实证」这个层面不成立，那是 F1 与 F3。

### OK-2 rg 隐藏目录那条警告属实

见 §1.4 表。零命中、exit 1（no match，不是 error 的 2）、无 stderr 输出——「而 rg 不报错」这个说法准确。成因两条（隐藏目录 + gitignore）都验证：`--hidden` 与 `--no-ignore` **单独**都不够，必须两个都掀。`git check-ignore -v .dev` → `.gitignore:26:.dev/`。

### OK-3 条目 3 没有把 `adopting-agent-findings` 复制一份

通读 `~/.claude/skills/adopting-agent-findings/SKILL.md`（169 行）。最接近的一节是「一个反复出现的模式：每一轮的新问题，往往长在上一轮的修复上…我这次的修复本身，有没有引入同类问题？」（:127）——那讲的是**一次修复引入同类新问题**，与条目 3 的**两条处置组合起来留下的盲区**是不同形态；该 skill 中没有任何一处讲组合盲区。其余章节（派活四前置、接收侧四种故障、A/B/C/D 分级表、驳回理由分类、多轮收口）条目 3 一律未涉及。

条目 3 保留的部分确实偏向本仓结构：「怎么查」全部绑在 `.dev/docs/<topic>/` 上。「什么算违背」与「修法方向」偏一般性（「把量的边界写在它旁边」是通用可观测性原则），但该原则目前在 user 级 skill 里**没有家**，所以这不构成门槛第 2 条说的「同一件事有两个家」。**判定：不越界**；但若这条形态将来复发到别的项目，它应当上迁到 `adopting-agent-findings`，届时本条要改成引用——建议在条目里留一句这个意思。

### OK-4 条目 3 的实证与原件逐项吻合，且没有把评审的结论安成自己的

| 文中断言 | 原件 | 判定 |
|---|---|---|
| 评审 4.4 = 「关空闲 keep-alive 连接会让在途字节变成 RST」 | `260820-shutdown-fix-review-gpt.md:236` 标题：「4.4 关闭空闲 keep-alive 连接会让在途字节变成 RST 而非干净 EOF」 | 吻合 |
| 判**不修**，理由「固有代价、ROI 不明」 | `admission-deadlock.md:160`：「这是关闭任何 keep-alive 连接的固有代价…在有实际投诉之前 ROI 不明确，按评审本人的倾向记录不改」 | 吻合 |
| 同一轮 5.5 =「被拒绝的请求不留痕迹」，判**采纳**，新增 `refused_requests` | `fix-review-gpt.md:299` 标题：「5.5 被拒绝的请求没有留下任何可读的痕迹」；`admission-deadlock.md:149` 处置栏：「新增 `refused_requests` 计数，进 `ShutdownReport`，且**进 incidents**」 | 吻合，且 4.4/5.5 确在**同一份**第一轮报告里，「同一轮」成立 |
| 「RST 掉的请求从不经过闸，因此从不计数，而收尾行读作 `[ OK ]`」 | `delta-review.md:191`：「运维读到 `[ OK ] stopped — 1 connections asked to close`，而实际发生的是一个池化客户端的 `POST /v1/messages` 被 RST 掉了」 | 吻合 |
| 「是第三轮评审…才指出来的」 | `delta-review.md:193` 原文；README:142 表格确认 delta-review 是第三轮 | 吻合，**归属正确，未据为己有** |
| 引用的 `README.md:78` / `:61` | 实测今天仍准确（§1.1、§1.2） | 吻合 |

唯一的拔高在权重那句话，已列为 F2；事实层面**没有夸大、没有张冠李戴**。

### OK-5 条目 4 的实证与原件逐项吻合，两层的功劳归属都写对了

| 文中断言 | 核对 | 判定 |
|---|---|---|
| 该测试在优雅关闭修复后变红 | README:83「修复后变红」 | 吻合 |
| 「它断言「进程 3 秒后还活着」」 | `git show 9b8114a^:tests/integration/test_standalone_process.py` 第 234–235 行：`time.sleep(3.0)` + `assert child.poll() is None` | **逐字吻合** |
| 「而那正是死锁的症状」 | `test-rebase-review.md:12`：「老测试断言的「进程还活着」不可能来自「在途请求把排空拖住了」」 | 吻合 |
| 405 机制：`POST /health/liveness` 打在只注册 GET 的裸 FastAPI，Starlette 只看 headers 就回 405、不读 body | 老测试第 226 行确为 `b"POST /health/liveness HTTP/1.1..."`；`test-rebase-review.md:51` 独立探针实测「2 秒内收到 405、`allow: GET`、31 字节，body 从未被读」 | 吻合 |
| 「第二层由**独立评审**补上」 | `test-rebase-review.md:112`：「**但有一处保护力被移走了，而且报告没有明说**：老测试…是**唯一一条**在真实进程 + 真实信号下会因死锁复发而变红的测试。M1 变异证明，重写之后这条 process 测试对死锁复发完全不敏感」 | 吻合。且同报告 `:106` 说第一层「你报告里的这条判断成立，且我是独立复现的，不是照抄」——即第一层确是作者先发现、评审复现。**两层归属都写对了** |
| 「最终处置是保留原场景、换上正确期望，另立一条」 | 当前 `tests/integration/test_standalone_process.py`：原名测试仍在 `:240`（夹具换成 `POST /swallow` + `wait_for_arrivals`），新测试 `test_a_pooled_client_that_races_the_signal_is_answered_rather_than_wedging_the_process` 在 `:283`；`:245` docstring 明写「…keeps that scenario, with the expectation it should have had」 | 吻合 |

### OK-6 条目 4 的退役判据可证伪

「本仓不再有随产品改动而改写既有测试的做法时（例如全面转向只增不改）」是 git 历史形态这一结构事实，由条目自带的命令直接测量。并且它显式挡掉了弱信号误读：「**「最近几次改测试都很正当」不是退役条件**——这条抓的正是看起来正当的那些」，与文件「退出的判据」一致。唯一的削弱来自窗口太小（F3），那是命令的问题不是判据的问题。

条目 3 的退役第二条（「本仓不再用 `.dev/docs/<topic>/` 承载处置表」）同样是干净的结构事实；第一条见 F9。

两条的「**不是**退役条件」反例都写了（评审轮数变多不是；最近几次很正当不是），体例与既有两条一致。

### OK-7 两条与既有两条不重叠、不冲突

- 条目 3 vs 条目 1（跨两种回复模式的事实唯一性）、条目 2（外部 wire 断言要有录制）：对象、判据、命令三者都不相交。
- 条目 4 vs 条目 1：条目 1 管的是「同一事实两处判定」，条目 4 管的是「一条测试的场景是否成立过」，无重叠。
- 条目 4 vs frontmatter 划出去的 `trusting-a-green-result`：无实质复制（证据见 F6），仅缺指路。**边界判定：不越界。**
- 条目 3 与条目 4 之间：一个查文档处置、一个查 git 历史，无重叠。

### OK-8 `### 当前状态` 的更新准确

「四条都立于 2026-08-20」——文件现有条目正好四条，四条的「凭什么在这里」全部标 2026-08-20（`:74`、`:129`「同一场」、`:179`、`:224`）。「都还没被真实复查检验过」与四条各自的权重段（都写了「不足以支撑…有召回力」「从未在一次真实复查里被检验」）一致。

后两条自称「单次实证、靠「一次但代价足以让人记住」那一支进来」——核对属实（条目 3、4 各只引一次事故），且随后立刻用文件自己的退出判据把「找不到第二例」限定成弱信号，前后自洽。这一段是本次改动里写得最扎实的部分。

### OK-9 `### 数量与快照` 的规范本身成立

规范内容（要么标取数时间、要么在数字无判据作用时不写）与文件既有的「命令给候选，不给结论」「别凭上次记忆」一脉相承，且条目 3、4 自身遵守了它：条目 3 的 `README.md:78`/`:61` 落在带 2026-08-20 的实证段内、且今天核对仍准；条目 4 用的是**测试全名**而非行号，天然抗腐坏。问题只在它的覆盖面声称，见 F8。

---

## 四、汇总

| 编号 | 严重度 | 一句话 |
|---|---|---|
| F1 | major | 条目 3 命令排除 `reports/`，够不着本仓处置表与自身立条实证；去掉排除即命中，噪音仅 14 行 |
| F2 | major | 「多派几个评审不解决它」被自身实证证伪——解决它的正是第三轮增量评审 |
| F3 | major | 条目 4 的 `-25` 窗口小于本仓四小时的推进量（59 个提交），今天就够不着 `9b8114a`；连带使退役判据不可靠 |
| F4 | minor | 权重段的「唯一一例」是 S-4×下界 那一对，不是 4.4×5.5，未点破 |
| F5 | minor | `!archived-*/**` 的原因是「被锚定」不是「不锚定」，处方对、解释反 |
| F6 | minor | 条目 4 是四条里唯一不给上游 skill 指路的，第二层落在 `trusting-a-green-result` 地盘 |
| F7 | minor | 条目 4「什么算违背」第 1 条字面涵盖改名/措辞，与「怎么查」互相拆台 |
| F8 | minor | `数量与快照` 的规范面向「本文」而合规只声称「实证段落」，已腐坏的 `pipeline_app.py:313/:316` 恰在覆盖之外 |
| F9 | minor | 条目 3 第一条退役条件只能由「连续观测不到」支撑，与文件退出判据相冲 |
| N1 | nit | 条目 4 脚本：`$changed` 未加引号；merge commit 静默跳过 |
| N2 | nit | 条目 3 可把 A:78×B:61 收编为第二例，实证强度被低估 |

**总体判定：needs-fix。** 两条条目的**判据**我认为都过得了文件自己的三条门槛：形态具名、代价具体、依附本仓结构（`.dev/docs/<topic>/` 布局、git 历史形态）、实证核对逐项属实。要修的是**命令与判据之间的落差**——F1 与 F3 各自使一条命令在真实复查里够不着它要抓的东西，F2 是一句会误导下一个人的权重论证。这三条按文件自己的话就是「命令不好用就改命令，**不要改判据去迁就命令**」，改法都在上面写明且都是局部的。

对权重的自评：F1、F3 由可复跑的命令输出直接支撑（本报告内附了对照数据），**强到可以直接照着改**；F2 由两份原件的原文对照支撑，同样强。F5、F7、F8、F9 是文本一致性问题，依据充分但是否值得现在改属取舍。F4、F6、N1、N2 为建议性质。

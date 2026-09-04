# 收尾归档评审：优雅关闭客户端侧（2026-08-20）

评审对象：本会话收尾产出的归档文档——一个未来接手的人会**代替对话记录**去读的东西。

| # | 对象 | 位置 |
|---|---|---|
| 1 | 话题入口 | `.dev/docs/graceful-shutdown/README.md` |
| 2 | 重写的知识文档（重点） | `.dev/docs/graceful-shutdown/client-side/README.md` |
| 3 | 探针目录说明 | `.dev/exp/graceful-shutdown-client-side/README.md` |
| 4 | 索引更新 | `.dev` 提交 `544987d` 对 `README.md` 的两行新增 |
| 5 | 临时证据处置记录 | `/home/xp/.claude/jobs/f5d7e766/tmp/DISPOSITION.md` |
| 6 | 取消跟踪 7 份文档 | 主仓库提交 `612f115` |

核对基准：`.dev/docs/graceful-shutdown/client-side/reports/` 下 7 份逐字原件、`.dev/README.md` 的写作约定、主仓库 Git 历史、`/home/xp/.claude/jobs/f5d7e766/tmp/` 下 24 份实际文件、以及主仓库当前源码。

评审性质：**只读**。除本报告外没有创建、修改或删除任何文件；未运行任何需要凭据或会触碰 4141 服务的脚本。唯一一次执行是在 `/tmp` 下用一个假变量名复现路径回退行为（见 M-3），它没有创建任何文件。

## 判定

**blocker 0，major 4，minor 7，nit 7。**

这套归档的**取证层是扎实的**：7 份原件逐字节未改，8 个探针脚本逐字节持久化，历史注记（修订后的版本）经得起独立复算，文档引用的路径与哈希无一断链，三行收尾原文与真实日志逐条对得上。四条 major 全部落在**重写层**：一处张冠李戴、一处把双向误差写成单侧保证、一处照着跑不起来、一处开放项清单不全。没有一条构成不可逆风险，全部是文字层面可改的。

严重度口径：`major` = 一个接手的人照着它做会得出错误结论或浪费一轮排查；`minor` = 会造成误解或返工，但读者有别的线索纠正；`nit` = 措辞与体例。

---

## 一、明确判定没问题的项（附据以判断的证据）

这些是我实际去核过、结论是「成立」的，列出来是为了让下一个人知道**哪些不必再查**。

### N-1 七份原件逐字保留 —— 成立

对 `612f115^` 的 blob 与 `.dev` 下的当前文件逐一取 hash：

```
IDENTICAL  260820-graceful-shutdown-admission-deadlock
IDENTICAL  260820-severed-measurement-audit
IDENTICAL  260820-severed-probe-review
IDENTICAL  260820-shutdown-delta-review
IDENTICAL  260820-shutdown-fix-review-gpt
IDENTICAL  260820-shutdown-mutation-audit
IDENTICAL  260820-shutdown-test-rebase-review
```

7/7 同 blob。`.dev/README.md`「保留原件在 `reports/`」这条约定被严格执行了。

### N-2 八个探针脚本逐字持久化 —— 成立

`cmp` 逐个比对 job tmp 与 `.dev/exp/graceful-shutdown-client-side/`：8/8 逐字节相同（`e2e_real_cli.sh`、`e2e_severed.sh`、`e2e_severed_burst.sh`、`e2e_severed_hammer.sh`、`probe_half_sent.py`、`probe_router_resume.py`、`repro_hang.py`、`repro_hang2.py`）。DISPOSITION 里「逐字持久化」这个措辞名副其实。

### N-3 「没有删除任何文件」—— 成立

`find /home/xp/.claude/jobs/f5d7e766/tmp \( -type f -o -type l \)` 现得 **24** 项，等于 DISPOSITION 清点的 23 项加上 DISPOSITION.md 自身。逐项对照它的四行分类表，23 项无一缺席、无一多余。`e2e-57737.pid` 里的 pid `917789` 经 `kill -0` 确认不在运行，「子进程早已 kill -KILL」属实。

### N-4 历史注记（修订后的版本）—— 成立，而且比它自己说的更强

工作树里 `client-side/README.md` 已被改写为「`1a7353e` → `f37068c` → `9b8114a`，重写过两次，判据是 blob 同一性」。我独立复算：

- 三个提交对象都还在，subject 相同；`1a7353e` 与 `f37068c` **不被任何 ref 包含**（`git for-each-ref --contains` 空），`9b8114a` 是 `main` 的祖先——「前两个哈希如今都不可达」属实；
- 8 个 `src/`、`tests/` 路径在 `1a7353e` 与 `9b8114a` 下**同 blob**，与文档所述一致；
- 比文档更强的一条：`git diff 1a7353e 9b8114a -- src tests` 与 `git diff f37068c 9b8114a -- src tests` **整树为空**，不止那 8 个路径；
- 「重写过两次」有旁证：三者的父提交分别是 `423adc6` / `1475ec7` / `dd9cfa6`，subject 同为 `fix: give a reply with nothing to say…`，即上游那一段被重写了同样的次数。

文档强调「判据是 blob 同一性而非补丁文本」这一句是对的，且是接手者容易踩的坑，值得保留。

### N-5 断链 —— 未发现任何一处

- 全仓库检索（排除 `.git`、`.dev`、`docs/tmp` 自身）**没有任何文件**引用那 7 个报告名；`docs/tmp` 幸存的 424 份文档里也没有。搬动没有留下悬空引用。
- 五个提交的 `Docs:` 尾注仍写 `docs/tmp/260820-*.md`，但这些路径在**各自的提交里依然取得到**（`git show 9b8114a:docs/tmp/260820-graceful-shutdown-admission-deadlock.md` 有内容），所以尾注不是死链，只是指向历史快照。`612f115` 的提交说明明确说了「mapping 放在新 README 里而不是重写历史」，这个决定与 `.dev/README.md`「搬动文档时检查引用」不冲突。
- 文档里点名的其余路径逐一存在：`docs/.human-controlled/lifecycle.md`、`docs/2604-rewrite/shutdown.md`、`docs/.human-controlled/config.example.yaml`、`docs/agents/deployment-systemd`、`docs/agents/systemd-rolling`、`docs/agents/systemd-runtime`。

### N-6 `docs/2604-rewrite/shutdown.md` 那条遗留张力 —— 逐字核对成立

该文件第 17 行原文确为「停止监听新连接（已建立的连接保留，不受影响）」。三个符号 `app.state.draining`、`drain_queue`、`ws_manager` 在 `src/` 下**均无匹配**（`rg -F`）。所以「那份文档描述的是计划中的 4 阶段设计、不是已发布的阶梯」这个判断我复核成立，`.dev/README.md`「写下被否定的方案」之外，这一条属于把「文档不是活载体」这个易错点提前写死，是这份归档里质量最高的段落之一。

### N-7 三行收尾原文 —— 数字与顺序逐条对得上

`client-side/README.md`「测量口径」引的三行 vs 三份 ham 日志：

| README | 日志 |
|---|---|
| `[ OK ] … 11 requests refused` | `ham-38569.log` 16:11:53 ✅ |
| `[FAIL] … 8 requests refused, 8 connections severed…` | `ham-47913.log` 16:11:58 ✅ |
| `[FAIL] … 9 requests refused, 10 connections severed…` | `ham-44767.log` 16:12:01 ✅ |

三行按时间序排列，数字一字不差（时间戳被去掉，见 T-1）。

### N-8 探针结论表 —— 与保留下来的日志一致

- 「`e2e_severed.sh` 四次全部落空」：9 份 `sev*.log` **无一出现 severed**，收尾行一律 `stopped — 2 connections asked to close`。
- 「`e2e_severed_burst.sh` 不能命中」：`burst.log` 收尾 `stopped — 20 connections asked to close`，`grep -c severed` 为 0。
- 「`e2e_severed_hammer.sh` 3 次命中 2 次」：三份 ham 日志两份带 severed。
- 「`probe_half_sent.py`：405、`allow: GET`、31 字节」：与 `260820-shutdown-test-rebase-review.md` 的一手实测逐项相符。
- 「`e2e_real_cli.sh` 变异版 15 秒不退、修复版 1.8 秒退出、在途请求拿到真实上游 200」：与 `260820-graceful-shutdown-admission-deadlock.md`「验证」一节相符，且 `e2e.log` 里就有那一行 `H1/H2 200 anthropic-messages/gpt-5.5 → gpt-5.6-terra`。

### N-9 重写文档的主干事实 —— 逐条有支撑

根因四步、`stop_admitting()` 的两半及其分量差、「第一档不截断在途工作（含 chunked 终止块）」、`open_admission()`/`pause_admission()` 的收拢、三个计数的分级与「代价轻重」的分级依据、RST 前提、「踩过的坑」五条中的四条（钉 bug 的测试、探针零分辨力、三次说大、全量数依赖未跟踪文件），在 `reports/` 里都能逐条落到具体段落，没有发现夸大或张冠李戴。`severed_connections` 是**下界**这一条尤其重要，重写把它提成独立小节是对的。

（第五条「`git commit` 提交整个索引」在 `reports/` 里没有对应段落——它是会话自身的教训而非评审结论。归档文档承载会话经验是正当的，只是读者无法回溯取证；不计为发现。）

### N-10 提交清单与 `612f115` —— 核对无误

五个哈希都存在、subject 与表格描述相符、都在 `main` 上、`main` 相对 `origin/main` **ahead 73**（「未推送」属实）。`612f115` 恰好只取消跟踪那 7 份，磁盘上 `docs/tmp/` 里它们已不在（内容在 `.dev`），`docs/tmp` 其余 56 份仍被跟踪、374 份未跟踪——这是搬动前就有的状态，不是本次造成的。

---

## 二、major

### M-1【major，失真：张冠李戴】把 `connections_asked_to_close` 的被否定方案安到了 `severed_connections` 头上

**位置**：`client-side/README.md`「被否定的方案，及否定的理由」第 2 条。

原文：

> **`severed_connections` 只统计真正当场关掉的连接**（而不是「被通知的」）。要读 uvicorn 的 `cycle.response_complete` 内部状态，会随上游重构**静默**给出错误数字。选了改名让措辞与它算的东西一致。

**这条整段搬错了对象。** 原件 `260820-graceful-shutdown-admission-deadlock.md`「记录但不采纳」：

> **gpt 6.1 的首选改法**（只统计真正当场关掉的连接）：需要读 uvicorn 的 `cycle.response_complete` 内部状态，会随上游重构**静默**给出错误数字。改名后这个数说的就是它算的东西，选了后者。

gpt 6.1 说的是 `released_connections` **名不副实**（实测 1 空闲 + 1 在跑 → 报 2），处置是**改名**为 `connections_asked_to_close`。整件事与 `severed_connections` 无关——那个计数根本没有被改过名，它也从来不是「被通知的连接数」。

后果有三重，都会误导：

1. 读者会以为 `severed_connections` 曾经被质疑过口径、并且「选了改名」，而它没有；真正被改名的 `connections_asked_to_close` 那条被否定方案则从档案里消失了。
2. 说反了实现：`_closing_would_sever` 恰恰**就是**用 `cycle is None or response_complete` 早返回的（见 `693dd0d:src/app/lifecycle/adapter.py:435-438`），也就是说「只统计真正当场关掉的连接」在 severed 上**是已经做到的事**，不是被否定的方案。
3. 它把评审的一条真实顾虑（依赖 uvicorn 内部状态会随上游重构静默出错）挂到了一个已经在依赖该状态的计数上，逻辑自相矛盾。

**改法**：把主语换回 `connections_asked_to_close`，并说清被否定的是「只统计真正当场关掉的连接」这个口径、采纳的是改名。

### M-2【major，失真：把双向误差写成单侧保证】「非零 ⇒ 确实有人没被服务」丢掉了同一批改动明写的多报

**位置**：`client-side/README.md`「`severed_connections` 是下界，不是总数」小节结尾。

原文：

> 所以：**非零 ⇒ 确实有人没被服务；零 ⇏ 没人。** 收尾行的 `ok` 是「没抓到」，不是证书。

后半句无可挑剔。前半句是本次归档里**唯一一处把「部分成立」写成「成立」**的地方，而且它正是这条线上被纠正过三次的那类错误的第四种形态。

证据链：

- `260820-severed-probe-review.md` **S-3（minor）** 的标题就是「『两条限制方向都是少报』这句话不成立」，并列出四种**多报**形状，第一种已实测：TLS 下内核缓冲里躺的可能是 close_notify / 重协商 / session ticket 而非请求（`probe_tls3.py` 实测返回 True）；另外还有「客户端发完请求就走人」「RFC 9112 允许的请求行前空行 / 杂散 CRLF」。
- 这条**已被采纳并落进代码**。`693dd0d:src/app/lifecycle/adapter.py:429-433` 的 `_closing_would_sever` docstring 现在写着「Three limits, and they do not all point the same way」，第一条就是 **over-counts under TLS**；`severed_connections()` 的 docstring 末行也留了一句「Not exact in the other direction either: see `_closing_would_sever` for the case that over-counts」。
- 归档文档只抄了 shipped docstring 的粗体那半句（「Non-zero means somebody certainly went without」），把紧随其后的限定整段丢了。
- 更要命的是，**同一个提交 `544987d` 里的另一份文档说了相反的话**：`exp/graceful-shutdown-client-side/README.md`「它们不能证明什么」写「TLS 恰恰是切断探测已知会**多报**（等待的字节可能是重协商）和**少报**（字节已被吸进 SSL 对象）的地方」。两份归档文档互相矛盾。

**为什么判 major 而不是 minor**：这是整个话题的收口结论，也是唯一一句运维会拿去做判断的话——`[FAIL]` 意味着什么。在 `tls_mode` 涉及 TLS 的部署上，一次纯粹的 close_notify 就能把一次干净的关停印成 `[FAIL]`，而文档告诉读者这时「确实有人没被服务」。它同时让这份归档比它所归档的代码**更不准确**，而归档的目的正是替代读代码。

**改法**：一句话——「非零 ⇒ 极可能有人没被服务（明文 HTTP/1.1 下可视为确定；TLS 下等待的字节可能是重协商或告警，见 `_closing_would_sever` 的三条限制）；零 ⇏ 没人。」

### M-3【major，可复现性】`exp/README.md` 的「怎么跑」照着做跑不起来，而且它对回退行为的说明是错的

**位置**：`exp/graceful-shutdown-client-side/README.md` 第 43 行与「怎么跑」代码块。

原文：

> `$CLAUDE_JOB_DIR` 已不存在，脚本里引用它的地方会退回 `/tmp`。

两句话都不成立：

1. **`$CLAUDE_JOB_DIR` 现在仍然存在**。本次评审的 shell 里 `CLAUDE_JOB_DIR=/home/xp/.claude/jobs/f5d7e766`，而且那个目录连同 24 份证据都还在。它是 harness 注入的环境变量，会随会话变化——不是「已不存在」，而是「值会变」。
2. **回退的不是 `/tmp`，是 `/tmp/tmp`**。四个 `.sh` 里都写的是 `TMP="${CLAUDE_JOB_DIR:-/tmp}/tmp"`，末尾那个 `/tmp` 是拼接上去的子目录。`/tmp/tmp` 在本机不存在。

后果是四个 `.sh` 在变量未设置时**全部第一步就失败**。实测（用假变量名在 `/tmp` 下复现，未创建任何文件）：

```
resolved TMP=/tmp/tmp
bash: line 1: /tmp/tmp/probe-readonly-check.log: No such file or directory
exit=1
```

脚本都是 `set -u` 而没有 `set -e`，于是失败会以最难读的形态展开：`uv run ghc-api-proxy start … >"$TMP/e2e.log" 2>&1 &` 的重定向失败，后台子 shell 立刻退出，`CHILD=$!` 拿到一个已死的 pid，接着 readiness 循环空转 `200 × 0.2s = 40 秒`，然后探针对着一个没起来的端口做实验并给出一个看似「测出来」的结论。**这正是最坏的失败形态：不是报错，是慢、静、且给出可信的假结果。**

而如果变量**设置了**（新会话的默认情况），脚本会把日志和 pidfile 写进那个新 job 目录的 `tmp/` 子目录——同样需要它先存在。

**改法**（任选其一，都在 README 里改得掉）：把「怎么跑」的第一行改成 `export CLAUDE_JOB_DIR=$(mktemp -d)` 并 `mkdir -p "$CLAUDE_JOB_DIR/tmp"`；或者直接说明「脚本把日志写到 `${CLAUDE_JOB_DIR:-/tmp}/tmp`，跑之前先 `mkdir -p` 它」。注意这是 README 的问题，不必改脚本——`.dev/README.md` 说 `exp/` 是「保留可跑」的取证手段，而不是保证脚本被维护。

### M-4【major，遗漏】「遗留张力」读起来像开放项全集，但至少漏了三条评审留下的开放项

**位置**：`client-side/README.md`「遗留张力，交给用户裁决」。

该节列了三条（`docs/2604-rewrite/shutdown.md` 的冲突、另外三处不做切断探测、503 信封与 ws 1012）。一个接手的人有充分理由把它当成开放项清单——章节名就叫「交给用户裁决」，而正文其余部分全是已定之事。但 `reports/` 里至少还有三条同级或更高级的开放项没有出现在任何一层归档文档里：

1. **O-1：`both` 模式每次关停都会打一条 `accepted connection routing crashed` 的 ERROR**（`260820-shutdown-delta-review.md`「范围之外的观察」）。既有缺陷，评审与父提交逐行比对确认本次未引入也未加重，根因清楚（`_peek_first_byte` 的 `finally` 撞上 `fileno() == -1` 抛 `ValueError`，两个 except 都接不住），**最小改法只有一行**，评审明确建议「单开一条小改动处理」。它与本话题同处一条路径、同一时刻，会让 `[ OK ] stopped` 旁边紧挨一条 ERROR——正是本次要解决的「让收尾说实话」的反面。这条被整个丢掉了，而它是全部开放项里最该被下一个人捡起来的一条。
2. **F-3：`pause_admission()` 清拒绝态，使「已唤醒但未恢复」的等待者从被 503 变成被正常服务**（同上，minor，潜伏）。当前不可达，但不可达性依赖两个**没有任何东西在守**的实现细节（`asyncio.Lock` 无竞争不让出、第二次 `stop_accepting` 时 `routing_tasks` 恰好为空）。评审原话：一旦有人在 `stop_admitting` 与 `_finalize` 之间加进任何挂起点，症状是「关停期间偶尔还会正常服务一个请求」，**比 503 难查得多**。这是典型的「归档不写就再也没人知道」的知识。
3. **S-5：让 fd 借用安全的两条性质没有守卫**（`260820-severed-probe-review.md`，minor）。改用 `dup()` 之后最阴险的一条已消失，但「peek 不消费」这条仍无守卫，且评审判定**结构上无法守**（被探测的连接下一句就被关，观察不到「字节仍被交付」）。谁将来动 `_closing_would_sever`，都需要先知道这里没有网。

顺带两条量级更小、同样只存在于原件里的：**发现 D**（真正承重的那一半在全量里只有一条确定性守卫）与**审计的建池陷阱**（uvicorn 5 秒 keep-alive 会在慢建池时悄悄缩小连接池，审计自己第一版探针因此量到 `asked=24` 而非 40，且「计数本身看不出异常」）。后者被审计列为必须写进文档的三条之一，理由是「任何人要重跑，这一格必须先对上」。

**这不是要求归档复述全部 1877 行原件。** 判据是：该节自称是交给用户裁决的清单，那它就得是清单；一条评审明确建议「单开一条小改动」的既有缺陷（O-1）不在里面，等于本次收尾把它悄悄吃掉了。

**改法**：在「遗留张力」下补 O-1（连同它的一行改法）与 F-3、S-5 各一句，并注明取证位置在哪份 report 的哪一节。

---

## 三、minor

### m-1【minor，失真】凭据与配额的判定与实测相反

**位置**：`exp/README.md`「它们不能证明什么」：

> **`e2e_real_cli.sh` 与 `e2e_severed_hammer.sh` 会发起真实上游请求**（`POST /v1/messages`），需要凭据，且会计入配额。

对 `e2e_real_cli.sh` 成立：它发的是完整合法的 `{"model": "gpt-5.5", "max_tokens": 16, "messages": […]}`，`e2e.log` 里确有 `H1/H2 200 anthropic-messages/gpt-5.5 → gpt-5.6-terra 3.6s`。

对 `e2e_severed_hammer.sh` **不成立**。它发的是 `POST /v1/messages HTTP/1.1 … Content-Length: 2\r\n\r\n{}`（第 34 行）。`MessagesRequest` 的 `model` / `messages` / `max_tokens` 都是必填（`src/app/models/anthropic.py:47-50`），于是本地就被打回。本会话自己留下的日志是决定性证据：

```
[FAIL] 16:11:07 H1 400 POST /v1/messages 0ms: request body must carry a non-empty string model
```

`0ms`、400、从未出网。`e2e_severed.sh` 与 `e2e_severed_burst.sh` 用的是同一个字节串，同样如此。

反过来，**真正需要凭据的地方文档没说**：`uv run ghc-api-proxy start` 启动时会去拉模型列表（`sev-41683.log`：`42 models available from ghc`），四个 `.sh` 全都要起这个进程。所以正确的表述是「四个 `.sh` 都要求一个能启动的代理进程（启动会拉模型列表）；只有 `e2e_real_cli.sh` 的请求真的走到上游、计入配额」。

**为什么值得改**：这条判定决定读者跑哪几个。按现在的写法，想在不烧配额的前提下复算切断窗口的人会**跳过 hammer**——而 hammer 是唯一证明那个窗口存在的脚本；同时他会以为 `e2e_severed.sh` / `e2e_severed_burst.sh` 无需凭据即可跑。两个方向都错。

### m-2【minor，处置记录诚实性】三份 ham 日志被整体称作「命中切断窗口的三次运行」，实际是三次尝试里命中两次

**位置**：`DISPOSITION.md` 逐类去向第 2 行：「命中切断窗口的三次真实进程运行日志（`ham-38569.log`、`ham-44767.log`、`ham-47913.log`）」。

`ham-38569.log` 的收尾行是 `[ OK ] … 11 requests refused`，**severed 为 0，未命中**。这三份是 hammer 一次运行的三个 attempt，命中的是 2 个——这恰好是文档在别处反复强调的「3 次命中 2 次」。分类标题把 3 说成了命中数。

同一份记录在别处对数字非常克制，这一处却复制了本话题最典型的错误形状（把一个下界/部分说成全体），所以值得单列。**改法**：「hammer 一次运行的三个 attempt 日志（其中 2 次命中）」。

### m-3【minor，处置记录诚实性】`e2e.log` 被归错类，其载体说明也对不上

**位置**：`DISPOSITION.md` 第 3 行把 `e2e.log` 与 8 份 `sev-*.log`、`sev.log`、`burst.log` 一起归入「未命中的扫描运行日志」，去向写「『四次全部落空』『20 条连接一起写也不能命中』的结论写在 `exp/README.md` 的『它们不能证明什么』一节」。

`e2e.log` 不是扫描日志，也谈不上「未命中」——它是 `e2e_real_cli.sh` 那次**成功**运行的服务端输出，内容是 SIGTERM 后在途请求拿到上游 200、随后干净收尾。它承载的是「第一档没有截断在途工作」这条正面结论，而那条结论写在 `exp/README.md` 的**结论表**里（`e2e_real_cli.sh` 那一行）与 `reports/` 的「验证」一节，不在被点名的「它们不能证明什么」一节。

内容没有丢失（结论确有载体），但归类和指向都不对。清点表的价值恰恰在于「一个被清空的目录与一个没人看过的目录长得一模一样」——那就要求每一格的指向经得起核对。

### m-4【minor，与 `.dev/README.md` 约定不符】归档形态没有 `archive-` 前缀，且待裁决项没有落在话题根目录

`.dev/README.md` 的布局块写的是：

```
docs/<topic>/
  ├── README.md
  ├── spec.md
  ├── deferred.md          未决项：想到了但没做的事，及不做的理由
  └── archive-<subtopic>/  历史：已完成工作的知识沉淀
        ├── README.md      重写过的知识文档
        └── reports/       当时的 agent 报告原件，逐字保留
```

并且明确「一份文档搬进 `archive-` 就等于宣布它不再是当前状态」；未决项之所以放话题根目录，「因为它们描述的契约与待办**仍然生效**」。同一仓库里 `docs/tui/` 就是照这个形状建的（`archive-footer/`、`archive-request-log/`、`archive-token-accounting/`、`archive-truncated-stream/`）。

本次建的是 `docs/graceful-shutdown/client-side/`——**归档的内容形态（重写 README + `reports/` 原件），却没有归档的命名**，同时话题根目录没有 `deferred.md` 或 `decision-pending.md`，三条「交给用户裁决」的活项被放在子话题 README 的倒数第二节。`544987d` 也没有更新 `.dev/README.md` 的布局块来容纳这个新形状。

后果有两个，都是可预见的：

- 照 `.dev/README.md` 找归档的人会去找 `archive-*`，找不到；
- **三条待用户裁决的活项在话题入口一层完全不可见**——`docs/graceful-shutdown/README.md` 只有一张表，`client-side/` 的状态栏写「已落地进 main」。一个只读话题入口的人会认为这件事已经关掉了。

这一条我不建议评审单方面裁定改法（是给 `client-side/` 加 `archive-` 前缀、还是承认它是「已落地但仍有未决项」的混合体并更新 `.dev/README.md` 的布局约定，属于目录约定的取舍），**建议交主会话或用户裁决**。但「话题入口没有任何地方提示存在待裁决项」这半条无论怎么裁都该补。

### m-5【minor，遗漏】五个提交在 `main` 上不连续，而文档的呈现方式暗示它们是一段

「提交」一节说「主仓库 `main`，未推送。按时间顺序：」后接五行表格。实际这五个提交之间夹着 **约 25 个并行会话的提交**：`9b8114a` 与 `693dd0d` 之间有 30 个提交，其中只有 4 个属于本话题（`git log 9b8114a~1..693dd0d` 实测）。

这不是措辞问题，它会让两件具体的事落空：

- 想把这条线当一个单元来读的人写 `git log 9b8114a..693dd0d` 或 `git diff`，拿到的是一大堆别的东西；
- 「测量口径」里那个 **1463 / 3** 锚在 `89002eb` 上。`693dd0d` 本身没动任何测试文件（只改 `cli.py`、`adapter.py` 与文档），但两者之间夹了 `10e4811`、`f0124f7`、`5d67eb9` 等别的会话的功能提交，所以**在这条线的最后一个提交上重数不会得到 1463**。文档已经说了「路径与行号是快照」，但没说这个数字的可比性只在 `89002eb` 那一个点上成立。

**改法**：一句话——「这五个提交在 `main` 上不连续，中间夹着并行会话的提交；`1463 / 3` 只在 `89002eb` 的干净 checkout 上可复现。」

### m-6【minor，失真】`repro_hang.py` 的结论在原件里没有直接证据，且与脚本自身的 docstring 相反

`exp/README.md` 的表里给 `repro_hang.py` 的结论是「**不会**（挂）。这一版没有分辨力」，「它们不能证明什么」进一步写「修复版与变异版都会『正常退出』」。

但原件里那条「零分辨力」的教训针对的是**第一版真实 CLI e2e**，不是这个进程内脚本：

> **一条关于探针本身的教训**：第一版 e2e 只开一条空闲 pooled 连接、不制造在途请求，结果修复版与变异版**都在 1 秒内正常退出**……（`260820-graceful-shutdown-admission-deadlock.md`）

而原件提到的进程内复现脚本是**会挂**的那一个（「复现脚本：修复前挂起并打出与生产同形的 traceback」，对应 `repro_hang2.py`）。

结构上这个推断是站得住的——`repro_hang.py` 确实没有在途请求（第一个请求读完即结束，随后 `receive_signal` + `sleep(0.2)` 才发第二个），所以关停会在毫秒级走完、第二个请求落不进窗口。但它是**推断，被写成了实测结论**，而且脚本第 1 行的 docstring 恰好说反：

```python
"""Repro: graceful shutdown never returns when a pooled client sends a request after stop_accepting."""
```

一个打开脚本的人会看到文件自称能复现挂起、README 说它的绿什么都不证明，两者对不上又没有任何一处解释。**改法**：README 里注明这条是从「没有在途请求 ⇒ 窗口不存在」推出的、或补一次实测；顺带在脚本头上加一行「这一版没有分辨力，见 exp/README.md」。（脚本是逐字保留的原件，加注前需要确认是否愿意破坏逐字性——也可以只改 README。）

### m-7【minor，可复现性/遗漏】命中率复算所需的参数与建池陷阱没有进文档

`260820-severed-measurement-audit.md` 把三件事列为「需要原文修订」，其中两件与复算直接相关：

> **这一条的真正缺陷不是夸大，是不可复算**：写入节奏没写进文档，任何人照原文重跑都会落在某个我上表里的失效区，然后得出「命中率远低于 2/3」的错误结论。
>
> 顺带记一句 uvicorn 5 秒 keep-alive 会在慢建池时悄悄缩小连接池。

归档文档写了命中率（3/3 中 2 次、审计 90%–100%），但**没写写入节奏**，也没写建池陷阱。

缓解程度比审计当时高：`e2e_severed_hammer.sh` 被逐字保留了，参数就在里面（每条连接间隔 `time.sleep(0.0002)`、信号在爆发开始后 `time.sleep(0.002)`，即审计表里 `stagger=0.0002 / pre=0.002` 这一格，实测 6/6 命中），而且它的 `pooled()` 按 `Content-Length` 精确读完再返回，天然避开了建池陷阱。所以判 minor 而非 major。

仍然值得补一句的理由：文档没有告诉读者「参数在脚本里」，也没有告诉他「自己改节奏会掉进失效区」——审计实测的两端失效区是完全不错峰（0/3）与错峰 5 ms（0/3），中间才是 90%–100%。这正是审计说的「照原文重跑会得出错误结论」。

---

## 四、nit

### T-1 「三行收尾原文逐字抄进」实际去掉了时间戳

`DISPOSITION.md` 说三行「逐字抄进」。数字、措辞、顺序全对（见 N-7），但日志里是 `[ OK ] 16:11:53 stopped — …`，文档里是 `[ OK ] stopped — …`。去掉时间戳是合理的规范化，只是「逐字」这个词此处名不副实。

### T-2 `probe_half_sent.py` 的运行前置写反了

`exp/README.md`：`uv run python <这个目录>/probe_half_sent.py     # 需要 tests/integration 在 sys.path 上`。

脚本第 17 行自己就做了 `sys.path.insert(0, str(Path("tests/integration").resolve()))`，读者不需要安排 sys.path。真正的前置是**当前工作目录必须是仓库根**（`Path("tests/integration")` 与 `Path("src")` 都是相对 cwd 解析的）。代码块开头的 `cd /home/xp/src/ghc-api-proxy-py` 事实上满足了它，但注释把读者的注意力引到了错误的地方——一旦有人从别处调用，失败信息会是 `ModuleNotFoundError: test_standalone_process`，而他会去查 sys.path 而不是 cwd。

顺带一条正面确认：`app` 在 `.venv` 里有 editable 安装（`_editable_impl_app.pth`），所以这一行不加 `PYTHONPATH=src` 是对的，与上面两行的写法差异不是笔误。

### T-3 两个脚本有结论但没有运行命令

`e2e_severed.sh` 与 `e2e_severed_burst.sh` 出现在结论表和「它们不能证明什么」里，却没有出现在「怎么跑」。`repro_hang.py` 的缺席是有意的（反面教材），这两个的缺席看不出理由。

### T-4 「没有一个走 TLS 路径」有一处例外

`probe_router_resume.py` 第 42-44 行 `generate_self_signed(...)` + `build_server_ssl_context(...)` 构造了 `both` 模式路由器。它没有发起任何 TLS 客户端连接，所以「切断探测未在 TLS 下取证」这个实质结论成立；但字面上的「全部脚本只覆盖明文 HTTP/1.1 + h11。没有一个走 TLS 路径」不严谨。

### T-5 两条提交说明对「几份 agent 报告」说法不一

`612f115` 说「Seven files: the working record and the six agent reports」；`.dev` 的 `544987d` 说「The seven agent reports it was distilled from」。后者把实现者自己的工作记录 `260820-graceful-shutdown-admission-deadlock.md` 也算成了 agent 报告。`client-side/README.md`「本目录」表的写法是对的（第一份标为「我的工作记录原件」）。

### T-6 `DISPOSITION.md` 的 23 项是写它之前的快照

照它给的命令现在重数得 **24**（多的正是 DISPOSITION.md 自身）。记录里没有一句「不含本文件」，而它整节的目的就是让下一个人能重数对上。

### T-7 两份文档对「监听器那一半在哪」指向不同

`docs/graceful-shutdown/README.md` 说那一半「还散在主仓库 `docs/agents/systemd-*`、`deployment-systemd` 下」；`client-side/README.md` 第 5 行说「不在这里，见主仓库 `docs/.human-controlled/lifecycle.md`」。两者都不假（一个指开发记录，一个指权威规范），但一个想找「另一半的开发记录」的人被子文档打发去了规范文件。

### T-8 关于本报告落盘位置

`.dev/README.md` 约定 `reports/` 存「当时的 agent 报告原件，逐字保留」。本报告按任务指定落在这里，于是这个目录从「被蒸馏的原件」变成了「原件 + 一份事后评审」。不构成问题（它确实是一份 agent 报告原件），但如果日后有人按目录语义假设「`reports/` 里每一份都已被 README 蒸馏过」，这份不是。建议在 `client-side/README.md`「本目录」表里补一行指向它。

---

## 五、自相矛盾一览（跨文档）

按被审对象两两对照，实际发现三处，都已在上文展开，此处只做索引：

| 冲突 | 一方 | 另一方 | 见 |
|---|---|---|---|
| severed 是否只会少报 | `client-side/README.md`「非零 ⇒ 确实有人没被服务」 | `exp/README.md`「TLS 已知会**多报**」＋ shipped docstring「over-counts under TLS」 | M-2 |
| `repro_hang.py` 会不会挂 | `exp/README.md`「不会，零分辨力」 | 脚本 docstring「never returns when a pooled client sends a request」 | m-6 |
| 那 7 份是不是都是 agent 报告 | `544987d`「seven agent reports」 | `612f115`「the working record and the six agent reports」 | T-5 |

与 `.dev/README.md` 约定之间的冲突只有一处（m-4 的目录形态与未决项归属）。其余四条约定——归档要重写、保留原件、写下被否定的方案、路径行号是快照——**都被遵守了**，其中「写下被否定的方案」写得相当好（五条，每条都带否定理由），「路径行号是快照」在两份 README 里各声明了一次。

---

## 六、一个接手的人读完这套文档，还缺什么

按任务点名的三种误解逐一回答，再补两条我自己发现的。

1. **「误以为某个数字是总数」——基本防住了，有一处漏网。** `severed_connections` 是下界这件事被提到了独立小节，措辞、机制、两组实测数字齐全，这是整份归档最好的一段。漏网的是 M-2 那半句（下界的另一端其实也不精确）与 m-2（DISPOSITION 把 3 说成命中数）。

2. **「误以为某个探针的绿有分辨力」——防住了，而且防了两层**：`exp/README.md` 有专门的「它们不能证明什么」，`client-side/README.md`「踩过的坑」也把这条写成通则。唯一的瑕疵是 m-6（那条结论安错了脚本）。

3. **「误以为 `docs/2604-rewrite/shutdown.md` 描述的是已实现行为」——防住了，且经我复核成立**（N-6）。这条写得比多数项目文档都清楚：它同时给了「不是活载体」的判据（三个符号不存在）、核对日期，以及「将来照它实现时会冲突」的提醒。

4. **还缺：这套机制在生产部署形态上根本不生效这件事，说了一半。** 「影响面只限自持监听器的直接运行路径……`--fd` 继承监听器的 systemd 路径从不安装这道闸」写在「根因」一节里，作为**缺陷影响面**出现。但同一句话反过来也成立：本次全部修复与三个新计数，在 `--fd`/socket activation 的 systemd 路径上**一样都不生效**——而项目既定的部署目标正是 systemd。一个运维读到「收尾行会报 severed」，去线上 systemd 服务上找，会找不到。原件里这一点是被穷尽枚举验证过的（`_install_admission_barrier()` 的唯一调用点在 `UvicornListenerAdapter.startup_lifespan()`），限定条件也写清了（静态可达性分析，未在运行时拉起 `--fd` 验证）。**建议在「关停收尾行报什么」那一节补一句适用范围**，而不是只在根因里说。

5. **还缺：一句「这条线现在的守卫长什么样」。** 承重的那一半（拒绝准入）在全量里只有一条确定性守卫（发现 D），真实进程那条是 2/10–4/10 的概率性守卫（发现 C），`peek 不消费` 无守卫且结构上无法守（S-5）。这三条合起来是下一个动这块代码的人最该先知道的事，现在要读三份不同的 report 才能拼出来。一张三行的小表就够。

---

## 七、方法、范围与本报告的效力

- **取证方式**：全部结论来自一手核对——`git cat-file` / `git rev-parse` / `git diff` 比对 blob 与树、`git hash-object` 比对原件、`cmp` 比对脚本、`rg` 全仓库检索引用与符号、`find` 清点 job 目录、直接读 job 目录里保留的 24 份日志与 pidfile、读 `693dd0d` 与当前 `main` 的源码 docstring。
- **未做的事**：没有运行任何 `.sh`（需要起真实代理进程，其中一个会计入配额，且本会话被禁止触碰 4141 服务）；没有跑测试套件，因此「1463 / 3」这个数字我**未独立复算**，只核对了它在原件里的出处与归因（`260820-severed-measurement-audit.md` 附一）；没有验证 `--fd` 路径在运行时的行为（原件亦未验证，见第六节第 4 点）。
- **效力分级**：M-1、M-3、m-1、m-2、m-3、m-5、T-1～T-6 与第一节全部 N-* 是**实测或逐字比对得出的，强到可以直接据此行动**；M-2 与 m-6 是**文本比对 + 源码阅读**，同样强；M-4 与 m-4 含**判断成分**（「该节是否自称清单」「归档形态该不该带前缀」），我给的是理由和建议，其中 m-4 的改法明确建议交由用户或主会话裁决。
- **没有做的一件事**：我没有修改任何被审文件，也没有替它们起草补丁。以上「改法」都是建议。

---

*评审者：closeout-review agent。日期 2026-08-20。基准：`.dev` 提交 `544987d` + 工作树中对 `client-side/README.md` 的历史注记修订；主仓库 `main` @ `5c1afbe`。*

---

# 附：复核处置（`.dev` 提交 `b5add6c`，2026-08-20）

只针对上文自己的发现核对是否关闭，不重做全面评审。核对基准：`git -C .dev show b5add6c` 的完整 diff、`DISPOSITION.md` 当前内容（它不在 `.dev` 仓库里，单独读的）、以及处置动作在磁盘上留下的产物。

## 逐条判定

| 发现 | 判定 | 一句话依据 |
|---|---|---|
| M-1 张冠李戴 | **已关闭** | 主语改回 `connections_asked_to_close`，补了原名与实测失真，并显式排除 `severed_connections` |
| M-2 单侧保证 | **已关闭** | 新增一段写明反方向也不是保证，结论改为「非零是『很可能』，涉及 TLS 会被误触」 |
| M-3 跑不起来 | **已关闭，且有独立产物佐证** | 四个 `.sh` 改用会自行创建的目录；`/tmp/ghc-shutdown-probes/tmp/` 下有 3 份 17:34 的新日志 |
| M-4 开放项不全 | **已关闭** | O-1、F-3、S-5 三条进了「遗留张力」，表述与原件相符 |
| m-1 凭据与配额 | **已关闭** | 新增「凭据与配额」一节，四个 `.sh` 与配额的关系按实测重写 |
| m-2 三份 ham 日志 | **已关闭** | 改为「一次运行的三个 attempt，其中 2 次命中、1 次未命中」 |
| m-3 `e2e.log` 归类 | **已关闭** | 单列一行，载体指向 `exp/README.md`「凭据与配额」，该节确有那行 200 日志 |
| T-8 补一行指向本报告 | **顺带关闭** | 「本目录」表新增 `260820-closeout-review.md` 一行 |
| m-4 目录形态 | **未动，按建议留给用户** | 与我的建议一致，不视为未关闭 |
| m-5 / m-6 / m-7、T-1～T-7 | **仍开放** | 本轮未声称处理，见下方清单 |

## 逐条依据

**M-1。** 新文本：「**`connections_asked_to_close` 只统计真正当场关掉的连接**……评审量到过 1 空闲 + 1 在跑 → 报 2 的失真……选了改名（原叫 `released_connections`）……**这条讲的是 `connections_asked_to_close`，与 `severed_connections` 无关**——后者是另一次改动，用 `MSG_PEEK` 新增的。」逐项对得上原件：`1 空闲 + 1 在跑 → 报 2` 出自 `260820-graceful-shutdown-admission-deadlock.md` 的 gpt 6.1 行与 `260820-shutdown-test-rebase-review.md` 附带发现 2（`probe4` 实测）；改名前叫 `released_connections` 属实；severed 由 `89002eb` 引入属实。多加的那句显式排除，正好挡住了我踩到的那个误读路径。

**M-2。** 新文本保留了下界方向，并补「反方向也不是保证……TLS 下等待的字节可能是重协商记录、session ticket 或 close_notify，探针分辨不了，那是**多报**」，收在「非零是『很可能有人没被服务』，在涉及 TLS 的部署上会被误触；零不代表没人。两侧都不是硬保证——这个数字用来引起注意，不用来结案」。与 shipped docstring（`693dd0d:src/app/lifecycle/adapter.py:429-433` 的「Three limits, and they do not all point the same way」）一致，与 `exp/README.md` 的多报表述也不再打架——M-2 同时记的那处跨文档矛盾一并消除。

*一处残留，不构成未关闭*：`260820-severed-probe-review.md` 的 S-3 列的多报形状不止 TLS，还有「客户端发完请求就走人」与「RFC 9112 允许的请求行前空行／杂散 CRLF 也会被读成 a request already sent」（S-8 同指）。新文本写「明文 h11 下非零基本可信」，用「基本」和「两侧都不是硬保证」兜住了，读者不会被误导到硬结论上；shipped docstring 也只把多报归给 TLS。记录，不要求再改。

**M-3。** 四个脚本一致改成 `TMP="${CLAUDE_JOB_DIR:-/tmp/ghc-shutdown-probes}/tmp"` + `mkdir -p "$TMP"`，四处 `mkdir` 都排在第一次使用 `$TMP` 之前（`e2e_real_cli.sh` 在 `PIDFILE=` 与重定向之前，另外三个在 `for` 循环／`start` 之前），`$TMP` 是绝对路径，不受随后 `cd "$ROOT"` 影响。README 那段错误说明被整段重写，并把失败形态（静默夭折 + 40 秒空转 + 可信的假结论）写进了正文与脚本注释。

独立佐证：`/tmp/ghc-shutdown-probes/tmp/` 里有 17:34 的三份新日志——目录确实是被脚本自己创建的，而不是人手 `mkdir` 出来的：

```
ham-33993.log  [FAIL] 17:34:44 stopped — 40 connections asked to close, 14 requests refused, 9 connections severed…
ham-33845.log  [FAIL] 17:34:47 stopped — 40 connections asked to close, 14 requests refused, 9 connections severed…
ham-53563.log  [FAIL] 17:34:50 stopped — 40 connections asked to close, 2 requests refused, 19 connections severed…
```

3/3 命中，与协调者的口头结果一致。**这轮实跑顺带给了一条与本次修复无关但有价值的旁证**：命中率 3/3、severed 9/9/19，落在独立审计量到的 90%–100% 区间里，进一步支持文档里「我报的 3 次命中 2 次是保守说法」那句。

**M-4。** 三条新增项与原件核对：O-1 的「既有缺陷、与父提交逐行比对确认未引入也未加重」出自 `260820-shutdown-delta-review.md` O-1；F-3 的两条不可达性依赖（`asyncio.Lock` 无竞争不让出、第二次 `stop_accepting` 时 `routing_tasks` 恰好为空）逐字对得上 F-3；S-5 的「去掉 `MSG_PEEK` 测试全绿」「`dup()` 之后最阴险的一条已不复存在」「不消费这条结构上无法守」对得上 S-5。*一处从简*：O-1 的一行改法（`finally` 里判 `fileno() != -1`，或把 `except OSError` 放宽到 `ValueError`）没有抄进来，但条目点名了「第三轮评审 O-1」，取证一跳可达，可接受。

**m-1。** 新「凭据与配额」一节的三段分别对应我核到的三件事：启动会拉模型列表（我复查了 job 目录里 10 份服务端日志，**10/10 都有** `42 models available from ghc`，加上新跑的 3 份共 13/13）；只有 `e2e_real_cli.sh` 的请求走到上游（`e2e.log` 的 `H1/H2 200`）；另外三个发 `{}` 在本地被 400 打回（`H1 400 … 0ms`）。末句「想在不烧配额的前提下复算切断窗口，跑 `e2e_severed_hammer.sh`」正好堵住我担心的那个误跳过。

**m-2 / m-3。** `DISPOSITION.md` 第 19 行改成「hammer **一次运行的三个 attempt** 日志……**其中 2 次命中切断窗口、1 次未命中**」，并补了「三行都在，含未命中那行」；`e2e.log` 从第 20 行的「未命中的扫描」里摘出来单列为第 21 行，载体指向 `exp/README.md`「凭据与配额」——我核过该节确实写着那行 200 日志。分类计数同步改成 8 + 3 + 10 + 1 + 1 = 23，算式自洽。新增的「修订」一节交代了改动来源，符合归档留痕的做法。

## 改动本身引入的新问题（3 条，都很小）

**新-1【minor】`DISPOSITION.md` 里「8 个脚本逐字持久化」这句现在过时了。** b5add6c 改了 4 个 `.sh`，于是 job 目录原件与 `.dev/exp` 副本不再逐字节相同：

```
DIFFERS   e2e_real_cli.sh / e2e_severed.sh / e2e_severed_burst.sh / e2e_severed_hammer.sh
IDENTICAL probe_half_sent.py / probe_router_resume.py / repro_hang.py / repro_hang2.py
```

这不是错误处置——`.dev/README.md` 只要求 `reports/` 逐字保留，`exp/` 是「保留可跑」，为了可跑而改脚本正是它的用途，而且 4/8 仍逐字。但 `DISPOSITION.md` 那一格的措辞是「逐字持久化」，且它正是本轮被修订过的文件，读者会以为它已经与当下对齐。**改法**：那一格改成「持久化（四个 `.sh` 随后在 `b5add6c` 修了临时目录回退，见该提交；四个 `.py` 仍逐字）」。

**新-2【nit】`DISPOSITION.md` 新增的「本清单已经过独立评审……它对本文件报了 2 条 minor，均已改正」不全。** 本报告对该文件实际提了 **4** 条：m-2、m-3（minor，已改）与 T-1（「三行逐字抄进」实际去掉了时间戳）、T-6（23 项是写它之前的快照，照它给的命令现在数出 24）——后两条仍在原样。现在的写法容易读成「评审对本文件提的都已闭合」。**改法**：写成「2 条 minor 已改，另有 2 条 nit 未改（见报告 T-1、T-6）」。

**新-3【nit】两处措辞比证据略强，方向都安全。** 其一，`mkdir -p "$TMP"` 没有检查失败（脚本仍是 `set -u` 无 `set -e`），万一目标不可写，回到的还是「静默继续」那一类失败——概率极低（`/tmp` 与 job 目录都可写），提一句是为了不让下一个人以为这条路已经彻底封死。其二，「启动时会去拉模型列表……**这一步就要凭据**」：我实测到的是 13/13 都发生了这次拉取，**没有**实测「无凭据则启动失败」。这是推断，但方向安全（宁可多提示要凭据），不必改，只是别把它当成实测结论再往下传。

## 仍然开放的发现（本轮未声称处理，列出以免丢失）

- **m-4** 目录形态与未决项归属 —— 按我的建议留给用户裁决。其中「话题入口 `docs/graceful-shutdown/README.md` 没有任何地方提示存在待裁决项」这半条，无论怎么裁都该补（现在「遗留张力」已有 6 条，入口一层仍只写「已落地进 main」）。
- **m-5** 五个提交在 `main` 上不连续；`1463 / 3` 只在 `89002eb` 上可复现。
- **m-6** `repro_hang.py` 的结论在原件里无直接证据，且与脚本自身 docstring 相反。
- **m-7** 命中率复算所需的写入节奏与建池陷阱没进文档（参数在 hammer 脚本里，但文档没说）。
- **T-1**～**T-7**（T-8 已顺带关闭）。其中 T-4「没有一个走 TLS 路径」本轮改了同一行的括号内容却未触及该措辞，`probe_router_resume.py` 仍构造着 TLS context。
- 第六节的两条缺口（适用范围只说了缺陷侧、没有一张「现在的守卫长什么样」的小表）也未处理。

## 复核结论

**四条 major 与三条被声称处理的 minor 全部真实关闭**，其中 M-3 有独立可核的磁盘产物、M-1/M-2/M-4 与原件逐条对得上，没有一条是「改了文字但没改到点上」。改动引入的三个新问题都在文字层，没有一个触及取证层：7 份原件仍逐字、清点数仍自洽、无新断链。

**复核判定：pass（就本轮声称处理的 7 条而言）**；整份归档的总判定仍是 needs-fix，因为 m-4 待用户裁决、m-5～m-7 与七条 nit 尚未处理。以上均不阻塞归档可用。

*复核者：同一 closeout-review agent。基准：`.dev` @ `b5add6c`；`DISPOSITION.md` 为 2026-08-20 17:35 后的当前内容。只读复核，未修改任何被审文件（本报告除外）。*

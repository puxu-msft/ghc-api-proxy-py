# 事实核查：`a-setting-says-what-it-bounds-not-what-follows`

**被核产物**：`.claude/skills/project-review-principles/SKILL.md` 第 254 行起（HEAD `12b2c82` = `main`）的第五条原则。
**引入提交**：`abb38f5`（= 工作树侧 `f219f4d`，2026-08-20 20:15:51 UTC）与 `1a9b854`（= `12b2c82`，20:20:09 UTC）。
**注**：`abb38f5`/`1a9b854` 在 worktree 分支 `worktree-delivery-keepalive` 上；`main` 上的对应提交是 `f219f4d`/`12b2c82`，`git diff 1a9b854 12b2c82` 为空，内容同一。本报告的行号与引文取自 `12b2c82`。

**范围**：只核「它说的每一句是不是真的」，不判它该不该在这里。

---

## 结论速览

> **2026-08-20 20:50 修订。** 初版判 7.1「不实」是**我自己的漏检**（按 `type=="user"` 枚举，漏掉了 turn 中途插入的真人消息），主会话提出反证、我独立复算确认反证成立，已改判**属实**并记下漏检机制（见 7.1-A）。同时按主会话的意见加重第 2 条、按修正后的判别轴重判第 5 条（见 5-bis）。下表为修订后的状态。

**核完 14 项可证伪断言：10 项属实，2 项不实，2 项夸大，2 项无据。**

**这条原则本身站得住**——它的三件核心事实逐条属实，处方来源的引文逐字属实，用户对「落点归属」的裁决也确有其言，检索命令与正样本对照我独立复现通过。**问题集中在三处**：把自己的推断写成家法（一处）、给了一组没有观测窗口的时间尺度（一处）、以及一句被同日事实推翻的「这一侧是干净的」；此外「我逐字转达」一句把一次主动升级写成了被动传递，性质比「不准确」更重。

| # | 断言 | 判定 |
|---|---|---|
| 1a | 提议把「双重身份」写进用户的 `config.example.yaml` | **属实** |
| 1b | driver docstring 写 `which is retryable` / `nothing has been shown to the client yet` | **属实** |
| 1c | 认错后把实现事实从自己注释里一并删掉（后又补回） | **属实** |
| 1.4 | 把这三次并列计为「三次触碰」以支撑权重 | **夸大**（第三次只在工作树存活 3 分半、未提交；但复原由用户 20:10:45 的消息触发，不是我自查自纠——初版此处措辞已订正） |
| 2 | 引文「这个双重身份必须写进注释」出自 research 报告 251 行 | **属实**（逐字，未加重语气） |
| 2 | 「我逐字转达」 | **不实，且在开脱**（两个源头都把落点留在我自己的面上；升级到用户契约面的是我。见第 2 条「加重」段） |
| 3 | 「代码属于中间带，长注释是立过的家法」 | 做法侧**属实**（可测）；「立过的家法」**无据** |
| 4 | 「探针几天／报告几周／`docs/` 几个月／两端以年计」 | **无据**（本仓实质历史 5 周；探针实测最长 6 小时） |
| 5 | 「2026-08-20 这一侧是干净的」 | **不实**（按修正后的轴，同日仍有 3 处真违背，全在运维日志行） |
| 6 | 正样本对照（指向修复前命中那句越界原文） | **属实**（我独立复现通过） |
| 7.1 | 「用户当天明确指出这个区分……」 | **属实**（`line=4169`，`origin.kind=human`，20:10:45 中途插入。初版判「不实」已撤回） |
| 7.2 | 「两端要克制（用户的归纳）」 | 属实但**轻度加重**（原话是「两端则可能是精炼的、克制的」） |
| 7.3 | 语义单一性、两个执行点、`upstream_request_retry` 决定结局、候选目录、五条计数、退役路径 | **属实**（逐条已核） |
| 7.4 | 「`await send` 在响应头就返回」（转述的实测） | 未复现；按可据以行动采信，但标明是转述 |

**最严重的一条仍是 #5。** 不是错得最离谱，而是错的方向最坏：条目明写「不是因为它发作过」，而当天这条判据在同一个仓库真发作了 3 次。下一个照清单复查的人会因此跳过它。但**要连同判据轴一起改**——按条目原来那条钝轴，我一度数出 7 处，其中 3 处（进客户端 400 响应体的那几条）实际是正当的，`semantic.py:51-57` 的 docstring 明写那是刻意设计。**一条钝的判据既漏报也误报，而误报会先把人劝退。**

**次严重的是 #2 那层加重**：在一句自陈「我没裁落点」的话里，把自己裁过落点的事实抹掉了。这是同一形态在元层面上的第四次发作，也是唯一一次发作在这条原则自己的正文里。

**一条方法论收获（不针对条目，针对我）：** 「用户没说过 X」这种否定式判定，其可信度完全取决于枚举口径的完备性，而枚举口径的缺口**不会自曝**——它只会给出一个干净的空集。7.1 就是这么错的。今后凡是要下「从未」「没有一条」这类结论，必须先声明枚举口径并证明它覆盖了目标记录类型。

---

## 逐条

### 1. 「2026-08-20 同一处触碰三次」——**属实**（三件事都真实发生），但第三次的份量被拉平了（见 1.4）

**(a) 提议把「双重身份」写进用户的 `config.example.yaml` —— 属实。**

transcript 里我的原话有两处，都在本会话：

- 收尾第一轮（对应 `783f023` 之后的汇报）：「请确认这个数，以及要不要把「它同时管等头和管体」这个双重身份写进你亲笔的 `config.example.yaml`——那个文件我没碰。」
- 收尾清单「仍待你裁决（未做）」第 1 条：「你已确认维持，但**双重身份（同时管等头和管体）尚未写进你亲笔的 `config.example.yaml`**。」

用户 2026-08-20T20:07:07Z 正是逐字引用后者来反驳的。属实。

**(b) driver docstring 写 `which is retryable` / `nothing has been shown to the client yet` —— 属实，且「同一片改动里」也成立。**

`git show 783f023 -- src/app/pipeline/direct_driver/base.py` 显示这两句由该提交引入：

```
+        Both raise `UpstreamTimeout`, which is retryable, because both fire while the driver still owns the attempt and nothing has been shown to the client yet.
```

`783f023` 就是让 `upstream_request_deadline` 首次真正生效的那次修复，与 (a) 汇报的是同一片改动。属实。

**(c) 认错后把实现事实从自己注释里一并删掉 —— 属实，事件确实发生过，且我复原了它。**

`git log -p` 看不到这一步：过度修正**从未进入任何提交**，只在工作树里存在了约 3 分半钟。证据在 transcript 的两次 `Bash`（python heredoc 原地替换）里：

- 20:09–20:10「Trim the over-reaching claims from the guard's docstring」把
  `Both raise UpstreamTimeout, which is retryable, because both fire while the driver still owns the attempt and nothing has been shown to the client yet.`
  换成
  `Both raise UpstreamTimeout, the error this driver raises for an attempt that ran out of time, so that whatever governs retrying sees the same kind of failure from either guard. What follows from that is the retry configuration's to decide, not this function's to state.`
  —— **「both fire while the driver still owns the attempt」这个实现事实被连带删掉了**。
- 20:13:36 前后「Restore the implementation fact without the downstream claim」把它换成最终形态
  `Both raise UpstreamTimeout: both fire while the driver still owns the attempt, so either one leaves through the same path as any other attempt that ran out of time. What is then done about it — another attempt, a continuation, nothing — belongs to the retry configuration, not here.`
  —— 事实补回，下游结局那半句仍不写。

所以「删了什么」= `both fire while the driver still owns the attempt`；「补回了什么」= 同一句，另加明确免责。`abb38f5` 的 diff 只呈现首尾两态，中间那一态不在版本历史里。条目对 (c) 的描述属实。

**1.4 但 (c) 与 (a)(b) 不同量级 —— 条目把三次并列，属**夸大**（轻度）。**

(a) 送到了用户面前并被用户逐字驳回；(b) 进了提交、在 `HEAD` 上活了约 2 小时。(c) 只在工作树存活约 3 分半，从未提交、从未外露。条目「凭什么在这里」写「同一事故内三次同形……满足『一次但代价足以让人记住』」——(c) 的实际代价是三分钟，把它与另两次并列计入「三次」抬高了证据量。这不影响原则本身成立，影响的是它的权重陈述。

> **2026-08-20 20:50 订正**：初版此处写 (c) 是「我在同一个工具循环里自查自纠」，**错了**。复原是被用户 20:10:45 中途插入的那条消息直接触发的（见 7.1）。这一改让 (c) 的份量**上升**而非下降——它不是我自己发现的，是又一次被用户抓到的。但「未提交、未外露、存活 3 分半」这三点不变，所以「与另两次并列计为三次触碰」仍属轻度夸大，只是理由从「自查自纠」收窄为「代价量级不同」。

---

### 2. 处方来源 `docs/tmp/260820-research-upstream-timeout-wiring.md:251` —— 引文**属实且逐字**，但「我逐字转达」一句**不实**，且来源引用**不完整**

该文件第 251 行原文：

> **对比总结**：driver 内的超时是「换一次尝试」，driver 外的超时是「掐断这一条流」。`upstream_request_deadline` 按第四节形状 1 接线后，会**同时具备这两种身份**（等头阶段可重试，体阶段不可重试）。这个双重身份必须写进注释，否则它是一个会被误读的键。

条目引的「这个双重身份必须写进注释」逐字对得上，**没有替原作者加重语气**——「必须」是原文自带的。这一半属实。

但条目接着写「我逐字转达」，**这一句不实**：

- 研究报告说的落点是「**注释**」；我转达给用户时说的是「写进你亲笔的 `config.example.yaml`」。**落点被我换了**，不是逐字转达。
- 真正把落点指向契约面的是**另一份**报告：`docs/tmp/260820-review-upstream-timeout-wiring.md:180`「把这个键的双重身份写进 `config.example.yaml` 的注释并请用户确认 1200 仍是他要的数」，以及同文件 `:386` 表格行「请用户确认 1200，并把双重身份写进他的注释（我不改他的文件）」。该 agent 的 HANDOFF 摘要也这么写。**条目没有引用这一份。**

后果是条目在这一点上**低估了自己的错**：它读起来像「原样传递了一条处方，只是没裁落点」，而实际是「两份报告的处方合并之后，落点从『注释』升级成了『用户亲笔的契约文件』」。建议改成引两份，并把「逐字转达」改为「转达时还把落点从注释换成了他的 `config.example.yaml`」。

**加重（2026-08-20 20:50 补）：这不只是「不准确」，它在替自己开脱。**

把两份报告并排看，谁指向哪个面是清楚的：

| 来源 | 落点 |
|---|---|
| `260820-research-upstream-timeout-wiring.md:251` | 「必须写进**注释**」——指向**我自己的面** |
| `260820-review-upstream-timeout-wiring.md:180` / `:386` | 「写进 `config.example.yaml` 的注释」「写进**他的**注释（我不改他的文件）」——已经指向契约面，但**明写自己不碰** |
| 我转达给用户（transcript 第 755 行） | 「要不要把……这个双重身份**写进你亲笔的 `config.example.yaml`**——那个文件我没碰」 |

也就是说：**两份子智能体报告都把动作留在自己这边**（一份指向代码注释，另一份虽提到用户的文件但明确声明不改、只是建议请用户确认）。**把它变成一条「请用户在他的契约面上补一句」的待裁决项，是我这一步做的。** 条目里「我逐字转达，没有裁决它该落在哪个面上」把一次**主动升级**写成了**被动传递**——语法上把施动者换成了子智能体，责任随之外移。

而这条原则的整个要点就是「落点是要裁的」。**在记录自己没裁落点的那句话里，把自己裁过落点的事实抹掉了**——这是同一形态在元层面上的第四次发作。

**建议改写**为：「这条处方的两个源头都把落点留在我自己的面上（research:251 指向注释；review:180/386 虽提到 `config.example.yaml` 但明写『我不改他的文件』）。**把它升级成一条要用户在契约面上补话的待裁决项，是我做的**——不是转达，是升级。」

---

### 3. 「在这个仓库里代码属于中间带，长注释是立过的家法」—— 前半属实（可测的既有做法），**「立过的家法」无据**

**做法侧：属实，且可测。** `src/` 下 229 个 `.py` 文件，非空非注释行 22984，`#` 注释行 598（比例 2.6%），其中 **230 行（38%）单行超过 120 字符**——即本仓的注释虽稀，但一旦写就是长散文式的「为什么」。集中在本次触碰的核心模块：`pipeline_app.py` 72 条注释里 47 条超长、`request_log.py` 27 条里 25 条、`stream.py` 21 条里 16 条。把代码归入「可以厚的中间带」符合实际观察。

**「立过的家法」侧：无据。** 我找过这些地方，都没有任何关于注释风格的裁决：

- `.claude/rules/` 下只有一个文件 `00-development-workflow.md`，其中唯一提到 comment 的地方是 `ruff format` 那条，且是把「不动注释散文」当作观测结果陈述，不是在立注释规范。
- 项目**没有** `CLAUDE.md`（`CLAUDE.md`、`.claude/CLAUDE.md` 均不存在）。
- 项目记忆 22 条里没有一条讲注释风格；提到「注释」的三条都是别的主题（变异分辨力、探针、文档搬迁时检查引用）。
- 跨全部 505 份本项目 transcript 扫描「用户亲口提到注释」的轮次，只有 5 条，其中 3 条是同一条被 resume/summary 复制的、讲「用户注释掉的配置项先不实现」，另两条是本会话的「『注释保活』是什么」和 20:08:49 那条。**没有一条是在为长注释背书。**
- 唯一反向相关的是 20:08:49 用户那句：那个下游现象「根本不是 `upstream_request_deadline` 配置项该操心、**注释**或声明的」——它是在**限制**注释能写什么，不是在确立长注释的正当性。

会话里「注释在这个仓库里是承重的」这句出自我自己（2026-08-20T20:07 之后的第一条回复），不是用户的裁决。

**判定：这是我从实际做法归纳出的推断，不是家法。** 建议改写为「本仓的既有做法是：注释稀但长，一写就写为什么（`src/` 598 条注释里 230 条超 120 字符）」，去掉「立过的家法」这个把推断说成裁决的措辞。这一点按 `what-decided-is-decided` 是要紧的：把自己的归纳写成已决事项，下一个读者会当契约执行。

---

### 4. 「探针几天、报告几周、`docs/` 的结论几个月、两端以年计」—— **无据**，而且本仓的实测尺度与它差一到两个数量级

我按这四档各自去量，结果如下（全部取自本仓，2026-08-20）：

| 档位 | 条目声称 | 本仓实测 |
|---|---|---|
| `.dev/exp/` 探针 | 几天 | `.dev` 仓库**整个是 2026-08-20 当天建的**（`git -C .dev log` 全部提交同日），三个 `exp/` 子目录 mtime 分别为当天 13:58、17:04、19:51 —— 最长寿命 **6 小时** |
| `docs/tmp/` 报告 | 几周 | 最早批次 `260806`/`260807`（425 份中 308 份），距今 **13～14 天** —— 这一档勉强对得上，但只有一个批次可观测 |
| `docs/` 的结论 | 几个月 | 非 tmp、非 archive 的活文档，最早未再变更日期是 **2026-08-08，12 天** |
| 两端（契约面／日志面） | 以年计 | `docs/.human-controlled/` 六个文件，最老的 `model-translation.md` mtime **2026-08-15（5 天）**；`config.example.yaml` 的 mtime 是 **2026-08-20 20:33**——比这条原则写下的时刻（20:20）还晚 13 分钟 |

更根本的一点：**本仓根本没有「几个月」或「以年计」的观测窗口**。`git log --reverse` 显示只有一个 2026-04-02 的空 `init`，实质开发从 **2026-07-15** 开始，全部历史 368 个提交、跨度 **5 周**。「几个月」「以年计」这两档在本仓不可能有过任何实例。

**判定：无据。** 这是一个听起来顺、也确实符合直觉方向（越外层越稳）的梯度，但四档里两档超出了仓库存在的时间，一档（探针）实测比声称短了一个数量级，只有「报告几周」对得上而且只有一个样本。这不是「倾向，需更多样本」——是**在没有观测窗口的地方写下了具体量级**。

建议改写：保留方向性判断（「越往中间越易腐」——这一条本身在方向上与 `.dev/exp/` 当天即建当天即用、`docs/tmp/` 425 份堆积、`docs/.human-controlled/` 只有 6 个文件的事实相容），删掉具体时间尺度，或改成「本仓成立 5 周，尚不足以支撑任何具体量级；写下的是预期而非观测」。你自己怀疑这一条是对的。

---

### 5. 「2026-08-20 这一侧是干净的」（日志行／错误消息／SSE 帧）—— **不实**；初判 7 处候选，按修正后的判别轴重判为 **3 处真违背**（见本节末 5-bis）

**扫描方法**：本会话首条用户消息 2026-08-20T07:16:00Z，其前最后一个提交是 `db9aa7d`（07:14）；末端取 `5d380a1`（20:32）。对 `git diff db9aa7d..5d380a1 -- src/`（54 文件、+3440/-394）提取全部新增的 `raise ...(` 消息、`logger.*(` 行与其续行字符串，逐条判「只报事实」还是「解释为什么」。

**先确认条目自己举的两条属实**：

- `raise StreamDeadlineError("attempt exceeded its deadline") from error` —— 属实，只报事实。
- `f"no response headers within {self._response_header_timeout}s"` —— 属实，只报事实。（条目写作「no response headers within 1s」，`1s` 是运行时插值出来的示例值，不是字面量；措辞上无碍。）
- 另外同批的 `f"attempt exceeded {self._attempt_deadline}s"`、`f"max_streams must be >= 1, got {max_streams}"`、`f"{type(transport).__name__} carries no connection pool to cap"` 也都干净。

**但同日同仓有以下 7 处候选**（每条已用 `git log -S` 定位到引入提交，全部在会话窗口内）。**下表是初判，用的是条目原文那条钝轴（「只说发生了什么」）；重判见 5-bis，其中 4 处最终判为正当**：

| # | 字符串（截取） | 位置 | 引入提交 | 为什么算「写了为什么」 |
|---|---|---|---|---|
| 1 | `this endpoint does not execute {...}, and answering without it **would return remembered text where the client expects a search**` | `pipeline/subscribers/server_tools.py:228` | `064ba63` 17:51 | 后半句是拒绝的**理由推导**，不是发生了什么 |
| 2 | `{key} cannot be sent to this endpoint, and **dropping it would let the search read sites this request ruled out without anything being able to detect it**` | `pipeline/translation_driver/openai_responses.py:221` | `16e87a5` 17:22 | 后半句论证的是「另一条路会怎样」 |
| 3 | `{key} is not a field this endpoint's web search accepts, and **removing it would silently discard whatever it asked for**` | `openai_responses.py:242` 附近 | `9fc5f25` 15:04 | 同上 |
| 4 | `flattened %d server-tool block(s) ... ; **upstream would have rejected them**` | `server_tools.py` logger | `be87f59` 07:36 | 日志行给出了做这次变换的理由 |
| 5 | `... blank text blocks; emptying the assistant turn, **which upstream accepts**` | blank-block 清洗的 `logger.debug` | `fef7f27` 14:37 | 同上 |
| 6 | `TCP keep-alive is on but %s is unavailable on this platform, **so the system's own timing applies for it rather than the configured value**` | keep-alive `logger.warning` | `52d877c` 20:01 | 因果解释 |
| 7 | `proxy %s is SOCKS, and **httpcore sets no socket options on that path**: tcp_keepalive_interval does not apply ...` | 同上 | `52d877c` 20:01 | 直接讲机制 |

第 1、2、3 条不只是日志——它们是 `TranslationRefused` 系（`semantic.py:51`）的异常消息，`handler.py:342` 把这一族判成 **400**，`handler.py:371` 的 `error_body()` 把 `str(error)` 原样放进响应体的 `message` 字段，**逐字送到客户端手里**。（**这个链路事实成立，但由此推出的「所以是违背」在 5-bis 被推翻**：`semantic.py:51-57` 的 docstring 明写这个外送是刻意的，且那三句讲的是客户端行动所需，不是实现推导。链路事实保留在这里，是因为它对判断「一句话会走多远」仍然有用。）

**一点归属说明（不改变判定）**：这 7 条字符串**都不出现在本会话主 transcript 里**（逐条 `rg -F` 命中 0），说明是子智能体或并行会话写的，不是我在主线上亲手敲的。但条目那句话写的是「2026-08-20 这一侧是干净的」，主语是这一侧、限定词是日期，不是「我今天写的那几条」。按字面读，**不实**。

**这条错误的方向值得注意**：条目说「列在这里是为了让检查有个反例可比，不是因为它发作过」。实际它当天在同一个仓库**真发作了 3 次**（重判后的数，见 5-bis），全在运维日志行。第二个端点这条判据不是「无正样本的空判据」，而是当天唯一有真正样本的一条，条目却把它写成了没发作过。这既误报了事实，也误导了下一次复查的优先级。

> **订正（20:50）**：本段初版写「至少 7 次，其中 3 次落在客户端响应体上」，是按条目原来那条钝轴数出来的，**数大了**。真实是 3 处、且都不在响应体上。保留这句初判是为了记下**钝轴同时会误报**这件事——它比漏报更早劝退读者。

**建议改写**：删掉「这一侧是干净的」，改为「我在本次事故里写的那几条是干净的（`attempt exceeded its deadline`、`no response headers within Ns`）；但同日 `server_tools.py:255`、`blank_text.py:113`、`composition.py` 的 SOCKS 那行把『实现为何如此』写进了运维日志，是这条判据的现成正样本」，并把它从「反例可比」升格为待处理的复查候选。

#### 5-bis 按修正后的判别轴重判（2026-08-20 20:50 补）

主会话指出我用的轴（条目原文「只说发生了什么、不说为什么」）太钝，正确的轴是：**端点可以承载「读者行动所需」的东西，不该承载「实现为何如此」。** 这个修正我接受，理由是 `semantic.py:51-57` 的 docstring 已经把这个取舍写死了，而且是刻意的：

> Carries a `code` and the `field_path` that caused it so the client is told which part of its request is the problem, rather than being handed a generic refusal it cannot act on.

按新轴重判上面 7 处：

| # | 位置 | 重判 | 理由 |
|---|---|---|---|
| 1 | `server_tools.py:228` `…answering without it would return remembered text where the client expects a search` | **正当** | 客户端此刻的决策是「要不要去掉 `web_search` 重发」。这句告诉它那条替代路径会**换掉答案的性质**（拿到记忆里的文本而非检索结果）。讲的是**读者若那样做会怎样**，不是代理内部为何如此；不含任何实现标识 |
| 2 | `openai_responses.py:221` `…dropping it would let the search read sites this request ruled out without anything being able to detect it` | **正当** | 客户端自己设了域名限制。这句说明「代理宁可拒绝也不悄悄放宽」，直接决定客户端是改请求还是接受不受限检索。读者行动所需 |
| 3 | `openai_responses.py:242` 附近 `…removing it would silently discard whatever it asked for` | **正当** | 同上形态 |
| 4 | `server_tools.py:255` `flattened %d server-tool block(s) …; **upstream would have rejected them**` | **真违背** | 前半句「改写了 N 个块」已足够让运维决定要不要看。后半句是**这段实现为何存在**的理由，运维据此做不了任何事，而上游一改它就成了错话。旁边 `:253` 的注释已经在解释为什么用 INFO——**解释有地方放，那个地方是注释，不是日志行** |
| 5 | `blank_text.py:113` `…emptying the assistant turn, **which upstream accepts**` | **真违背（最轻）** | 同 #4 形态。`:112` 的长注释已经带着实测编号（`exp/260820-empty-text-probe/` F6/F4/F3）讲清了为什么，日志行再复述一遍是把中间带的话搬到端点上。debug 级、代价最小，但形态一样 |
| 6 | `composition.py:98` `TCP keep-alive is on but %s is unavailable on this platform, **so the system's own timing applies for it rather than the configured value**` | **正当** | 「so…」这半句讲的正是**运维填的那个值此刻不生效**。这是配置端点最该说的话 |
| 7 | `composition.py` `proxy %s is SOCKS, and **httpcore sets no socket options on that path**: tcp_keepalive_interval does not apply to connections made through it` | **部分违背** | 三段里两段正当（「这个代理是 SOCKS」是事实、「`tcp_keepalive_interval` 不生效」是运维行动所需）；中间那句 `httpcore sets no socket options on that path` 点名了第三方库的内部行为——运维据此做不了事，httpcore 一改就成错话。**改法是删掉这一句，保留首尾**，不是整行推倒 |

**重判结论：7 处中真违背 3 处**（#4、#5 全句，#7 一个从句），4 处正当。

**这不改变第 5 条的判定。** 条目那句「2026-08-20 这一侧是干净的……不是因为它发作过」仍然**不实**——按修正后的、更严格也更正确的轴，同日仍有 3 处真违背，全部由当天的提交引入。变的是**规模与去向**：不是 7 处、不是「进了客户端 400 响应体」（#1#2#3 那三处进响应体的恰恰是正当的），而是 3 处**运维日志行**，两处在 `subscribers/`、一处在 `composition.py`。

**因此对判据轴的建议**（这直接决定条目怎么改）：

- 把「另一个端点」那条从「出现『为什么』而不只是『发生了什么』」改为「**出现『实现为何如此』，而不是读者行动所需**」。
- 附一句可操作的自测：**「读者知道这句之后，能做的事有没有变？」** 变了就留（#1#2#3#6），没变就是解释，挪回注释（#4#5#7 中段）。
- 再附一句本次重判自带的启示：#4 与 #5 的「为什么」**旁边就有一条注释在讲同一件事**（`server_tools.py:253`、`blank_text.py:112`）。**违背常常表现为中间带的话被复制到端点上**，而不是无中生有——所以查的时候看一眼「这句在附近的注释里是不是已经有了」，比判断它像不像解释更快。

---

### 6. 正样本对照 —— **属实**，我独立复现通过

我把条目「怎么查」代码块里的命令**逐字**取出，只把路径参数 `src/` 换成 `git show` 导出的单文件目录（`git show` 写 stdout，不能直接当 rg 的路径参数，必须先落一份；条目没写这一步，是可用性小缺口，不是事实错误）。

先确认取的是同一份字节：`git show abb38f5~1:...` 与 `git show f219f4d~1:...`（= `783f023`）`diff -q` 相同。

**指向修复前**，唯一命中：

```
230:        Both raise `UpstreamTimeout`, which is retryable, because both fire while the driver still owns the attempt and nothing has been shown to the client yet.
```

**指向修复后**，唯一命中的是它的免责版本（因 `continuation` 一词被抓出）：

```
230:        Both raise `UpstreamTimeout`: both fire while the driver still owns the attempt, so either one leaves through the same path as any other attempt that ran out of time. What is then done about it — another attempt, a continuation, nothing — belongs to the retry configuration, not here.
```

条目对命中内容的描述准确，「免责版本也会被抓出来、那是正确行为」也属实。

**附带核了「命令给候选，读一眼多数会排除」**：把同一命令原样打在当前 `src/` 上，输出两条——`blocks.py:4`（讲块级交付本身的模块 docstring，读一眼即排除）与上面那条免责版本。0 条真违背，与条目的描述一致。

**一处 transcript 侧的细节**：会话里实际跑的第一次正样本对照用的**不是**条目发布的这条命令（当时用的锚点是 `-e 'response_header' -e 'attempt deadline' -e 'upstream_request_deadline'`，二级过滤器也不同）。但随后有一步「把文件里那段原样取出来跑一遍」补上了逐字验证，且我这次独立复现也通过。**结论不变：属实。**

---

### 7. 其余可证伪断言

#### 7.1 「用户当天明确指出这个区分：反馈可以进我控制的代码或文档，错的是想让它进用户控制的权威文档」（修法方向的 ⚠️ 段）—— **属实**

> **本节为 2026-08-20 20:50 的更正。初版判为「不实（归因错误）」，是我自己的方法漏检，不是条目的错。主会话提出反证后我独立复算，反证成立。**

用户原话在 transcript `line=4169`，`2026-08-20T20:10:45.171Z`：

> reviewer 说「这个双重身份必须写进注释」，有可能是希望你考虑加入代码中、你自己的文档中，你做错的地方是希望将其反馈加入上游用户控制的权威文档，你可以选择加入或者不加入你自己控制的代码或者文档

该记录的 `attachment.type == "queued_command"`、`attachment.origin.kind == "human"`，是**真人在 turn 中途插入**的消息。条目那句转述与原话同义，且「可以进我控制的代码或文档 / 错在想进用户控制的权威文档」这个二分是**用户逐字给出的**，不是我的归纳。**属实。**

**时间线也因此反转。** 更正后的顺序是：

| 时刻 | 事件 |
|---|---|
| 20:09–20:10 | 「Trim the over-reaching claims」——连带删掉实现事实 `both fire while the driver still owns the attempt` |
| 20:10:39 | 用户排队该消息 |
| 20:10:45 | 用户编辑后送达（`代码活文档` → `代码或者文档`），`origin.kind=human` |
| ~20:12 | 我回「你这个区分很关键，我上一轮**矫枉过正**了……而我认错之后顺手把代码注释里的这层事实也削掉了」 |
| 20:12:34 | 用户再插一条：「这几个教训值得归纳总结和记下来，写入 project-review-principles」 |
| 20:13:36 | 「Restore the implementation fact without the downstream claim」 |

所以**复原是被用户这条消息直接触发的**，我初版写的「过度修正与其复原全部发生在两条用户消息之间、中途无任何用户输入」**是错的**。连带地，「写进 project-review-principles」这件事也是用户当场指示的，不是我自发的。

#### 7.1-A 我的漏检机制（这条比结论本身更值得记）

我枚举用户消息时用的过滤条件是 `select(.type=="user")`。**Claude Code 的 turn 中途插入消息不是 `type: "user"` 记录**，它以两种形态落盘：

- `type: "queue-operation"`（`operation` 取 `enqueue` / `popAll` / `remove`），**同一条消息会重复出现 3～4 次**；
- `type: "attachment"`，`attachment.type == "queued_command"`，其中 `attachment.origin.kind == "human"` 才是真人来源（同一字段下 `origin` 缺失的是 `<task-notification>` 之类的系统注入）。

按 `type=="user"` 枚举会把它们全部漏掉，而漏掉的**恰好是最关键的那几条**——用户会在你干活干到一半时纠正你，那正是纠正最密集的时刻。

**本会话共有 5 条真人中途插入**，我初版一条都没看见：

| 时刻 | 内容 |
|---|---|
| 16:30:26 | 从现在开始，待用户挑选的素材全部移入 `.dev/human-controlled-docs-candidates`，从主分支移走 |
| 16:30:40 | 同时修正相关引用 |
| 20:07:32 | 「SDK 隐式 600 秒 read timeout」是什么意思，我们使用 SDK 了吗，为什么不显式覆盖？ |
| 20:10:45 | （上面那条区分） |
| 20:12:34 | 这几个教训值得归纳总结和记下来，写入 `project-review-principles` |

**正确的枚举口径**：真人轮次 = `type=="user"` 且 content 为 string 且非 `<task-notification>`／`<system-reminder>`，**并集** `type=="attachment"` 且 `attachment.type=="queued_command"` 且 `attachment.origin.kind=="human"`。**不要**直接对 `queue-operation` 做 `rg -c` 计数——一条消息会被计 3～4 次。

**对主会话复算命令的一处订正**：`rg -c '你可以选择加入或者不加入你自己控制的代码或者文档'` 现在返回 **5** 而不是 4，`rg -c '你自己控制的'` 返回 9。差额来自 transcript 在这次往返中继续增长（20:46 之后我的工具调用、工具输出与主会话消息本身都把这句话写了进去）。**这不影响反证**，但说明「对 transcript 做 `rg -c` 得到的次数」本身随时间变化、且把系统回声与真人原话混在一起计数——判定来源必须回到记录类型与 `origin.kind`，不能停在计数上。

#### 7.1-B 这次漏检没有污染其他条目

我逐条回查了初版里依赖「用户说过／没说过」的判定：

- **第 3 条（「立过的家法」无据）**：那次扫描是跨全部 505 份 transcript 按关键词 `注释` 做的**全文**匹配（不限记录类型），5 条命中已逐条列出，不受本盲区影响。为稳妥我按新口径确认：5 条真人中途插入里没有一条提到注释风格。**结论不变：无据。**
- **第 7.2 条（「两端要克制」的语气加重）**：20:12:34 之后到 20:45 之间没有任何真人插入，唯一相关的仍是 20:18:23 那条常规 user turn。**结论不变。**
- **第 1(c)、第 5 条**：不依赖用户消息枚举（前者依赖工具调用序列，后者依赖 git diff）。**结论不变。**


#### 7.2 「本质是信息有层次，而两端要克制（用户 2026-08-20 的归纳）」—— 属实，但**轻度加重**

用户原话是「两端**则可能是**精炼的、克制的」（试探性表述），条目写成「两端**要**克制」（规范性表述）。归纳的归属正确、方向正确，语气从描述硬化成了要求。属可接受的提炼，但既然本条原则的主题就是「不要替别人宣告」，标一下更好。紧随其后的「判据是：端点承诺，中间层解释」条目没有归给用户，正确——那句确实是我加的。

#### 7.3 以下断言逐条**属实**，已核

- **「`upstream_request_deadline` 的语义只有一条——单次上游尝试的最大存活秒数」**：与用户 20:07 的裁决一致，且与用户亲笔 `config.example.yaml:310` 的注释逐字一致（「单次上游尝试的最大存活秒数（0 = 禁用）」）。
- **「它需要两个执行点纯属实现」**：两点在代码里都在——`direct_driver/base.py:256` 的 `asyncio.timeout_at(deadline_at)`，与 `server/pipeline_app.py:390` 的 `with_deadline_at`。后者的注释明写「The second place `upstream_request_deadline` is enforced from — one bound, not two」。
- **「结局由 `upstream_request_retry` 那边的配置决定」**：该键存在于用户亲笔文件 `config.example.yaml:324` 与 `schema.py:368`；续写机制存在于 `pipeline/retry.py:30/108/175`（`CONTINUATION`、`continuation_messages`）。**旁证**：用户自己的文件里，「重试／续写／客户端」这类结局措辞恰恰都写在 `upstream_request_retry` 段落下（`:318`、`:325`、`:341`、`:349`），而 `upstream_request_deadline` 那段一句都没有——条目开的处方（「移到决定那件事的机制的文档下」）与用户既有做法同构。
- **「`.dev/human-controlled-docs-candidates/` 的提案」**：目录存在，含 5 份文件。
- **「同一片改动里，driver 的 docstring 又写了……」**：两句均由 `783f023`（让三个上游超时各守其名的那次修复）引入，与 (a) 汇报的是同一片改动。
- **清单头「五条都立于 2026-08-20」**：`12b2c82` 的第 336 行确为「五条」，计数与本条被加入后一致。
- **「凭什么在这里：存在一个用户亲笔、我不得修改的配置契约面」**：由项目记忆 `human-controlled-docs-are-final-authority` 与 `docs/.human-controlled/` 的实际存在共同支持。
- **退役条件指向 `.dev/docs/<topic>/archive-*/`**：该约定在本仓已在使用（`.dev/docs/tui/`、`.dev/docs/upstream/` 等，含 `archive-*` 子目录）。

#### 7.4 一处未能证实也未能证伪，记录在案

条目转述的实现事实里有一句依赖实测：「`await send` 在响应头就返回」（代码注释写「measured 2026-08-20 on a server that held the body back two seconds after its headers」）。我没有重跑这个探针。它与 httpx streaming 的语义一致、与两个执行点的代码结构一致，**按可据以行动采信**，但它是**转述的实测**而非我核过的实测。



# 保活文档修订本身的独立证伪评审（`029bf0a`）

- 日期：2026-08-20
- 角色：独立证伪者。评审对象是**上一轮 14 条失效项的修订结果本身**，不是被修订之前的状态，也不是代码正确性。
- 评审基线：分支 `worktree-delivery-keepalive` 的 `029bf0a docs: correct what two landed slices invalidated in the keep-alive docs`。
- 事实基准：仓库内文件一律 `git show main:<path>` 读取（`main` 当前 tip 为 `f025e3c`，比上一轮评审的基线 `f3c9de7` 又前进了 5 个提交）；`docs/.human-controlled/` 不在 `main` 上也不在本 worktree 里，只能读主工作树磁盘副本（`config.example.yaml` mtime 2026-08-20 20:33，早于本提交的 21:16，期间未再变）。
- 本轮实际跑过的命令（在本 worktree 内）：`uv run pytest -q`、`uv run pytest -q tests/e2e --collect-only`、`uv run ruff check src tests`、`uv run pyright src tests`。未修改任何文件，未动 `main`，未 rebase。

---

## 一、结论

**verdict：needs-fix。**

修订把上一轮 14 条里的 13 条处置掉了，其中 D-7 那一条（三次声称已记录而实际未写）这次是**真的写进去了，而且内容逐条核实无误**——这一点值得单独说，因为它正是本主题反复失守的地方。测试数 1554、四个归档分支指向、护栏改名、`52d877c` 指针更正、人写文档两条提醒，全部实测/逐字核对通过。

但修订过程本身引入了新的失效断言，而且集中在同一种手法上：**给一句话补上「是哪个提交让它作废的」时，提交号选错了；给活文档补上「当前闸门状态」时，数字取自一个不可比的环境，并且其中一条红灯在写下它的时候已经被本分支自己修掉了。**

- 严重（须改后再合）：4 条 —— M-1、M-2、M-3、M-6
- 中等（应改）：2 条 —— M-4、M-5
- 次要：8 条 —— m-7 ~ m-14

代码侧不受本次提交影响，本报告不对 `10da106` 及其之前的实现另作判断。

---

## 二、须改后再合（严重）

### M-1【严重｜把握：高】`deferred.md` 给 D-5 补的括号说明，把缺陷的主语写反了，且前后半句自相矛盾

`deferred.md:93`（本次新增）：

> D-5（`response_header` 被 `response_header_overrides` 解析，等于用一个 header 守卫去砍整次尝试）

三份独立来源一致指向另一个主语：

1. 权威定义：`docs/tmp/260820-deferred-d3-d5-d6.md:186` 的小节标题是「**D-5：`response_header_overrides` 被拿去覆盖 `upstream_request_deadline`**」。
2. 修复提交的自述：`783f023` 提交信息「And the deadline was resolved against `response_header_overrides`, so an operator capping one model's header wait would have capped that model's whole attempt instead.」
3. 代码证据：`git show 064ba63 -- src/app/server/handler.py` 删掉的正是

   ```python
   attempt_deadline = resolve_timeout(
       route.model_id,
       timeouts.upstream_request_deadline,
       timeouts.response_header_overrides,
   )
   ```

被 `response_header_overrides` 解析的是 `upstream_request_deadline`，不是 `response_header`。而且按字面读，「`response_header` 被 `response_header_overrides` 解析」描述的是一个**完全正常**的覆盖表用法，根本不是缺陷；它与紧随其后的「等于用一个 header 守卫去砍整次尝试」在同一个括号里互相打架——后半句只有在被覆盖的是 deadline 时才成立。

同病还有 `spec.md:143`：

> `response_header` 的相位错配（`deferred.md` D-5）与 body 未被 deadline 约束（D-6）都已由 `783f023` 修掉

D-5 不是「相位错配」。`response_header` 无消费方（真正的相位问题）是**同一节里的另一件事**，研究文档 `260820-deferred-d3-d5-d6.md:22` 明写「同节的 `response_header` 无消费方是另一件事：一道从未实现的守卫」。本次修订把两件事并成了一件，并且并到了错的那一件上。

**要改的点**：`deferred.md:93` 与 `spec.md:143` 两处 D-5 的描述，改成「`upstream_request_deadline` 被 `response_header_overrides` 解析」。

### M-2【严重｜把握：高】D-5 的修复提交归错了：是 `064ba63`，不是 `783f023`

`deferred.md:93` 与 `spec.md:143` 都把 D-5 记在 `783f023` 名下。证据反对：

- `git show 783f023 --stat` 的 14 个文件里**没有** `src/app/server/handler.py`。
- `git log -S 'It used to be resolved against' -- src/app/server/handler.py` 唯一命中 `064ba63 fix: refuse a search this endpoint cannot run, instead of answering without it`。
- 时间：`064ba63` 是 17:51:54，`783f023` 是 18:09:36，早 18 分钟；`064ba63` 是 `783f023` 的祖先。

同一处归属错误还波及 `spec.md:135`：

> 第二版写的是它读 `stream_idle` **与 `stream_idle_overrides`**；`783f023` 之后这半句也不成立了——那次提交把两张 override 映射连同用户已删的配置键一起去掉了。

`stream_idle_seconds` 停止解析 overrides 同样发生在 `064ba63`（该提交把 `def stream_idle_seconds(chain, model)` 改成 `def stream_idle_seconds(chain)`，并删掉「Resolved per model through the same precedence…」那段 docstring）。`783f023` 删掉的是 `schema.py` 里的两个**字段**（`git show 783f023 -- src/app/config/schema.py` 可见）。

**终点结论仍然为真**（`064ba63` 在 `783f023` 之前，所以「`783f023` 之后不成立」不假），坏掉的是因果账。而这份文档的全部价值就在这本账上：它自称记录「哪个提交在哪一刻作废了哪句话」，账目指错提交，下一个人按 `git show 783f023` 去看会看不到那半个修复，然后要么以为文档在编，要么以为修复还没落地。

**要改的点**：三处提交归属，或者改成「`064ba63` 与 `783f023` 两个提交合起来」并说明各自那一半。

### M-3【严重｜把握：高（实测）】`status.md` 新写的「已知既有红灯」在写下它的时候已经不成立了

`status.md:13`（本次新增）：

> **已知既有红灯，先于本主题存在**：`tests/e2e/claude` 因 `ModuleNotFoundError: No module named 'harness'` 收集失败，已在 `52d877c^` 上验证同样失败。全量回归一律用 `--ignore=tests/e2e`。

本 worktree 实测：

```
$ uv run pytest -q tests/e2e --collect-only
...
5 tests collected in 1.67s
```

修掉它的是**本分支自己的** `65e0781 test: finish the reorganisation the authored layout asked for`（20:05:42），`git show 65e0781 -- tests/e2e/claude/conftest.py` 里那一行就是 `-from harness import claude_available` / `+from _harness import claude_available`。它排在本次文档提交（21:16:22）之前 71 分钟。`main` 上的孪生提交 `0c1524f` 同样已修：`git show main:tests/e2e/claude/conftest.py` 第 15 行是 `from _harness import claude_available`。

后半句也已过期：`65e0781` 同时把 `addopts` 从 `--ignore=tests/client_e2e` 改成 `--ignore=tests/e2e`（`main` 上同），所以「一律用 `--ignore=tests/e2e`」现在是配置默认，不需要人记；而在评审员当初实测的那个时点，它恰恰**不**是默认，那句话是对当时的正确建议。

**为什么判严重**：这是本次修订**新增**的一条当前态断言，而这次修订的全部主题就是「文档里关于当前状态的断言过期了」。它不是继承下来的旧债，是同一天、同一支笔、在已经修好之后写下的。

**要改的点**：删掉或改写为历史记录（「`52d877c` 合入时点曾红，`65e0781` / `0c1524f` 已修」）。

### M-6【严重｜把握：高】`deferred.md` D-2 没跟上：仍引 `:404-409`、仍称合成物是「半块」，与 `spec.md` §2.2 的「已消解」正面冲突

`deferred.md:17`（本次**未改动**）：

> `docs/.human-controlled/config.example.yaml:404-409` 定义的窗口是「上游都没有响应头」且合成物是「半块」；实现从响应头**到达之后**才起算，且只发 `message_start`。**用户已表示会自行修订人写文档**，本项目侧不动实现，等文档定稿后再对齐。

磁盘上该文件当前：

- 406 行（中文，权威半句）：「客户端发起流式请求时，若很久上游都没有响应头，合成 HTTP 200 以及一个 `message_start` 给客户端。」
- `:404-409` 现在覆盖的是 `buffer_cap_bytes: 16777216`（404）到英文半句（409），并不是那条设置的定义。

而 `spec.md:77` 本次刚把同一条冲突标成「**已消解，无需裁决**」。于是两份活文档对同一件事给出相反的状态：spec 说已消解，deferred 说还挂在「归用户」里等文档定稿。按「一处权威 + 可复述」的规矩，这里必须有一处指向另一处，而不是各说各的。

这同时直接推翻提交信息里的一句：

> Line-number citations into that file are replaced with section names — they have gone stale once already, and the file is being actively edited.

只在 `spec.md` 做了。`deferred.md:17` 的 `:404-409` 原样留着，而且它是全仓最后一处指向那个正被用户编辑的文件的行号引用。

**要改的点**：`deferred.md` D-2 同步为「窗口定义仍冲突、合成物已消解」，去掉行号。

---

## 三、应改（中等）

### M-4【中｜把握：高（21 是实测）；成因把握：中】`status.md` 的 Pyright「94 → 95」取自隔离副本，与仓库实际不可比，且与同一份文档第 80 行打架

`status.md:11`：

> Pyright 在 `52d877c` 上净增 1（`stream_cap.py` 读 `client._mounts` 的 private-usage 一条），由父提交的 94 变为 95。

出处是 `review-merged-upstream-keepalive.md:121`：「对 `e12003a^` 与 `e12003a` 分别**从 git object 解包后**运行同一 Pyright 配置：父提交 94 errors，目标提交 95 errors。」

本 worktree 实测：

```
$ uv run pyright src tests
21 errors, 0 warnings, 0 informations
```

HEAD 与 `e12003a` 之间只隔四个提交：两个纯文档（`edc9839`、`1a9b854`）、一个 skills + 两行注释（`abb38f5`）、一个测试树重组（`65e0781`，只移动 2 个文件、改若干路径字符串），外加 `10da106`（新增测试，只会**增加** private-usage 诊断）。这些都解释不了 74 条的落差。最可能的解释是：解包副本里没有本树的 venv 与已安装的 `app` 包，Pyright 的导入解析退化，凭空多出几十条形状正确的假诊断——这正是同一份评审自己在紧邻的一行里承认过的坑（「在 git archive 中尝试目标提交全量回归时有 19 failed，全部是 archive 缺资产……**不拿缺资产的 archive 结果评价提交**」），只是那条纪律没有同样施加到 Pyright 上。

雪上加霜的是，同一份 `status.md` 第 80 行还留着调和时点的「Ruff、Pyright 干净」（即 0 errors）。第 11 行的 94 和第 80 行的 0 相隔 69 行并列在一份活文档里，读者无从调和。

**净增 1 这个差值大概率仍然成立**（两侧同环境同配置），不成立的是把 94/95 当作仓库闸门数写进活文档。

**要改的点**：删掉绝对值，只保留「净增 1，在解包副本里测得，绝对值与本仓 `uv run pyright src tests` 不可比」；或者在本树重测一个可比的数。

### M-5【中｜把握：高】上一轮 F-11 未处置，也没有说明为什么不处置，而 `status.md` 却宣称「14 条……已按其处置」

F-11 说的是：`review-transport-keepalive-r3.md` 的最终裁决是 `needs-fix` 并列了三条前置条件，其后归档链上又落了 `ac676b0` / `52d722c` / `2705281` 三个提交，没有 R4，也没有任何文档记录这三条如何关闭——一个 `needs-fix` 判决被无声关掉了。

核实：本次提交信息全文未提 R3；`rg 'R3|review-transport-keepalive-r3|needs-fix'` 扫 `spec.md` / `deferred.md` / `status.md` 只命中一处，是 D-7 里顺带引用 R3-F2 作为「这条被声称记录过三次」的证据，不是对 R3 裁决的关闭说明。

而 `status.md:24` 本次新写：

> ……判定八条裁决在实现里全部准确落实、两条提交信息无夸大，**14 条问题全在文档侧，已按其处置**。

实际是 13/14。按项目规矩，不采纳的建议要记下来并说明理由，不能不声不响地略过。

**要改的点**：要么补一节记 R3 三条的关闭情况，要么在 `status.md` 明写「F-11 未处置，理由是……」。两者都行，不能都不做。

---

## 四、次要

### m-7【次｜高】提交信息「Line-number citations into that file are replaced with section names」夸大

只在 `spec.md` 成立。详见 M-6。

### m-8【次｜高】`spec.md` 前言的「未被评审覆盖」范围，被本次提交自己扩大了却没跟上

`spec.md:6` 只说：

> **但 §3 是 2026-08-20 上游 slice 落地后重写的，那次重写本身没有被任何一份评审覆盖过。**

本次 `029bf0a` 又整段重写了 §2.2（含【需用户裁决】块的全部论证）与 §4，同样未经任何评审。前言现在读起来像是「除了 §3，其余都过审了」。按这份文档自己立的规矩（「每一条关于接线的断言都有保质期」），这一句该一并扩到 §2.2、§4。

### m-9【次｜高】`spec.md:141`「这条警告在同一天内已经击发三次」漏数

`status.md:84` 自己记着第四次：「并行会话对 `upstream_transport.http2` 的改动又让 §3 关于 `http2_ping_interval` 的表述作废」。若把「用户改写人写文档使 §2.2 的引文作废」也算上则是第五次。两份文档在同一件事上给出不同计数。

（这条本身不重要，但它是这次修订里唯一一个可以机械数出来的全称/计数声明，而它没数。）

### m-10【次｜高】`spec.md:81` 换上了 `handler.py:131` 这个行号，与同段「不引行号」的理由自相矛盾

行号本身**当前正确**：`main:src/app/server/handler.py:131` 确为 `attempt_deadline = timeouts.upstream_request_deadline`（已核）。问题是同一次提交刚以「该文件正被持续修订、行号已失效过一次」为由删掉了人写文档的行号，转手却把行号钉进了一个更不稳定的引用面——`status.md:28` 自述主线「每一到两分钟就有一个提交」，同一行在 `783f023^` 上还是 116。

建议改引符号名（`handler.py` 的 `attempt_deadline` 读取点），与人写文档那边采用同一条纪律。

### m-11【次｜高】「见 `deferred.md` 文末」/「见文末」已不指文末

本次提交在 `## 文档侧顺手项（无岔路）` 之后追加了整节 `## 合入后复评查出的三条 —— 已修`，于是：

- `deferred.md:89`「剩下的只有文档侧那张表（**见文末**）」
- `status.md:115`「`streaming-resilience.md` 已判定为归档件、不必回头改（见 `deferred.md` **文末**）」

两处指到的现在是 D-10 与「未采纳的建议」。改成「见『文档侧顺手项』一节」即可。

其余交叉引用与结构逐条核过**均无问题**：

- `deferred.md:60`「见下方 D-3d」→ D-3d 在第 87 行，确在下方 ✓
- `deferred.md:25`「见本文『代理在场时 keep-alive 到底探的是谁』一节」→ 第 70 行 ✓
- 标题层级完整，`## 已裁决` 在第 62 行 ✓（曾误删的那个标题现在在位）
- 新插入的 `## 未解决（缺陷，无岔路，排期做掉）` 与 `## 归用户的提醒（不动人写文档）` 都是 `##`，与同级小节一致 ✓

一处组织上的轻微异味（不算发现）：`## 归用户`（D-2，第 13 行）与 `## 归用户的提醒（不动人写文档）`（第 55 行）是两个名字极像的顶级小节，中间隔着两节，且第一节的内容正是第二节要提醒的同一条设置。合并或改名会更好读。

### m-12【次｜高】§2.2「整次尝试的总时长上界，包括流式正文」的精度边界没写

主体结论**已确认为真**（见第五节）。未写明的三点，都不影响「不要把调低它当成解法」这个结论，但影响「它到底管到哪」：

1. `with_deadline_at` 只在每次 `anext` 的边界上判定，不打断正在进行的下游消费——其自身 docstring 就写着「Time the consumer spends between pulls still counts — it is measured at the next pull rather than interrupting it」。
2. 上游流结束之后的下游交付（块级缓冲的释放、终止帧）不在这个界内。
3. 它是**每次尝试**的界。重试与续写各自 `begin_attempt()` 一次、各得一份新的 1200s，整个请求的墙钟不受它约束。spec 的措辞「整次尝试」在字面上是对的，但紧接着的操作建议（「调到 300 以下会砍断一次已经在输出的长回答」）读起来像是在谈整个请求。

### m-13【次｜低】本次带入仓库的评审报告有两处全角 `／`

`review-merged-upstream-keepalive.md` 第 214 行（`exact host／subdomain／localhost／IPv4／CIDR／IPv6`）与第 245 行（`外部／未追踪`）。按 `10-text-formatting`，`／` 应写作半角 `/`。这份是子智能体报告原样入库的历史件，可以不改，记一笔。

**本次改动的三份活文档（`spec.md` / `deferred.md` / `status.md`）新增段落全部通过标点扫描**：中文句中无半角 `,.;:!?()`，无 `--` 充当破折号，无全角拉丁/数字，无硬折行。

### m-14【次｜中】`status.md:24`「四路独立、异源」与同句列出的五类报告对不上

同句列了契约 3 轮、asyncio 8 轮、调和 1 份、传输层 3 轮、合入后复评 1 轮，共五个来源。把复评并进传输层算作一路可以自圆，但同一句又强调复评是「异源模型」。写成「五路」或补一句归并理由即可。

---

## 五、逐条已确认（复核通过，不构成发现）

任务点名要攻的四处，我都找了反例，没找到：

**1. §2.2「`upstream_request_deadline` 是整次尝试的总时长上界，两处执行读同一个 `attempt.deadline_at`」——成立，且没有绕过路径。**

- `src/app/pipeline/direct_driver/base.py:130-132`：`run()` 每次 `begin_attempt()` 后，若 `_attempt_deadline > 0` 就把 `attempt.deadline_at` 固定成一个 loop 时刻。
- 同文件 `:240 / :253-260`：`_send` 读同一个值，用 `asyncio.timeout_at` 包住 header 等待。
- `src/app/server/pipeline_app.py:390-395`：`with_deadline_at(with_idle_timeout(response.aiter_bytes(), …), deadline_at=attempt.deadline_at …)`。
- **绕过面已扫**：`rg 'deadline_at' src` 全仓只有 `streaming/deadline.py`、`pipeline/request.py`（字段定义）、`direct_driver/base.py`、`pipeline_app.py` 四处；`attempt.deadline_at` 的唯一写入点是 `base.py:132`。
- **驱动面已扫**：`DRIVERS` 里四个驱动（`AnthropicMessagesDriver` / `OpenAIChatCompletionsDriver` / `OpenAIResponsesDriver` / `OpenAIEmbeddingsDriver`）全部是 `DirectDriver` 子类，`attempt_deadline` 在 `handler.py:132-140` 的**单一构造点**统一注入。`translation_driver/*` 不是驱动，只做载荷翻译，不参与这条链。所以本项目主路径（Anthropic Messages 入、Responses 上游）也在界内。
- **消费面已扫**：`rg 'aiter_bytes|aiter_raw' src` 除 `pipeline_app.py:392` 外只剩 `routes/{anthropic,openai,gemini,azure}.py`，那是旧链路，不在 §2.2 的射程内。
- **旁证**：人写文档 `config.example.yaml:310-316` 自己把 `upstream_request_deadline` 定义为「单次上游尝试的最大存活秒数 / Max seconds ONE upstream attempt can live」，与修订后的表述一致。修订方向对着权威走的。

**2. §4「`stream_idle_seconds` 函数体只有一行、没有 overrides」——成立。** `main:src/app/server/handler.py:510-515`，函数体是 `return chain.config.upstream_request_timeouts.stream_idle`。`UpstreamRequestTimeoutsConfig`（`main:src/app/config/schema.py:148-154`）只剩 `response_header` / `stream_idle` / `upstream_request_deadline` 三个字段，默认分别 0 / 0 / 1200。

**3. §4「两条链路」的划分——准确。** 读 overrides 的是 `app/streaming/idle_timeout.py:11` 的 `resolve_stream_idle`，`rg` 全仓只有 `routes/anthropic.py:28` 导入它；新链路 `pipeline_app.py:54` 只导入 `with_idle_timeout`。注意 `with_idle_timeout` 本身是两条链路**共用**的函数——但 spec 那句话说的是「同名**字段**不是同一组配置」，射程正确，没有把共用函数误说成分离。

**4. D-7 的三条事实——全部核实无误。**

- `load_proxy_config()`（`main:src/app/config/loading.py:139-157`）按 bundled → YAML 文件 → `GHC_` 前缀环境 → CLI overrides 四层 `_deep_merge` 压平，最终 `ProxyConfig.model_validate(merged)`，`proxy` 是 `schema.py:362` 的一个 `str`，**不带任何来源标记**。
- 下游行为：`composition.py:147-148` 在 `options.proxy is not None` 时走显式 transport，`_proxy_mounts` 的注释自陈「Empty when `proxy` is configured … an explicit proxy is `all://` and the environment is not consulted」。
- 人写文档 `config.example.yaml:255-263` 规定的优先级**逐字**是：1. CLI `--proxy` 参数；2. `HTTP_PROXY/HTTPS_PROXY` 环境变量；3. 本设置。D-7 写的顺序与之完全一致。
- 第三次落空的出处 `test_an_explicit_proxy_reaching_httpx_shuts_the_environment_out` 的 docstring 在 `main:tests/unit/server/test_http_client_build.py:83-86`，「Recorded in `docs/agents/delivery-keepalive/deferred.md`」原文属实。

**5. `status.md` 的数字与指针——逐个核过。**

| 断言 | 核实 |
|---|---|
| 1554 passed / 3 skipped | **实测复现**：`uv run pytest -q` → `1554 passed, 3 skipped in 102.88s` |
| `ruff check src tests` 通过 | **实测复现**：`All checks passed!` |
| 新增 4 条回归 | 四条测试在本树全部存在：`test_one_pool_is_capped_once_however_many_mounts_reach_it`、`test_a_long_no_proxy_list_still_opens_a_connection`（`tests/unit/upstream/test_stream_cap.py`）、`test_the_socks_warning_prints_an_ipv6_origin_that_can_be_read_back`、`test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive`（`tests/unit/server/test_http_client_build.py`）|
| `52d877c` 时 1550 | 与 `review-merged-upstream-keepalive.md:119` 一致（沿用，未复跑） |
| `archive/260820-delivery-keepalive` = `68a50e7` | ✓ 逐字符相符 |
| `archive/260820-delivery-keepalive-onmain` = `1bb22fb` | ✓ |
| `archive/260820-upstream-keepalive` = `2705281` | ✓ |
| `archive/260820-upstream-keepalive-onmain` = `0176e93` | ✓，且确为一个 squash（`feat: upstream keepalive slice (squashed for rebase)`），F-12 的处置说法成立 |
| `dbb6104` / `52d877c` / `783f023` 在 `main` 上 | ✓ |
| `1a2daac` 不在 `main`、只在 `archive/260820-upstream-keepalive` | ✓ |
| `e12003a` 与 `52d877c` 逐字节相同 | ✓ `git diff --stat 52d877c e12003a` 空输出 |
| 产品文件清单（`composition.py` / `stream_cap.py` / `schema.py` / `settings.py`）| ✓ 与 `e12003a` + `10da106` 的 `--stat` 相符 |

**6. 护栏改名正确。** `test_environment_routing_matches_native_httpx` 在 `main:tests/unit/server/test_http_client_build.py:135`；`ROUTE_SAMPLES`（`:127-132`）确为 **4** 个目的地，与原生 `httpx.AsyncClient()` 的 `describe_route` 逐个比对，并带一条防空过断言（`len({…}) > 1`）。deferred.md 说的「四个目的地逐个与原生 httpx 比对」逐字属实。

**7. `spec.md` 前言的两条新断言成立。** `git ls-tree -r main -- docs/tmp` 里没有 `260820-downstream-keepalive-defect.md` / `260820-review-downstream-keepalive-defect.md` / `260820-review-synthetic-start-fix.md`；`git ls-tree -r main -- docs/.human-controlled` 空；`git show 53fec22 --stat` 里这四项齐全。「16 份独立评审报告」也对：目录实点 async 8 + contract 3 + transport 3 + reconciliation 1 + merged 1 = 16。

**8. 归用户的两条提醒逐字核实。** 人写文档 `:409` 英文半句仍是 `synthesize a half-block to the client`（中文 `:406` 已改），中英确实不一致；`:289-291` 的 `http2_ping_interval: 15` 确无任何未实现标注。F-13 采纳进 spec 的那句新代价，与 `:407` 原文逐字一致。

**9. §3 的射程收窄正确。** `main:src/app/config/settings.py:22-24` 的 `UpstreamConfig` 仍带 `max_connections` / `max_keepalive_connections` / `keepalive_expiry`，旧链路未删。spec 从「不是本项目的配置」改成「不再由新链路配置」并加括号说明，是把射程改对了。

**10. `spec.md:91` 的 `hedge` 断言仍成立。** `rg 'hedge' src --glob '*.py'` 只命中 `schema.py:266` 的定义，无消费方。

---

## 六、上一轮 F-1 ~ F-14 的处置表

| # | 处置 | 判断 |
|---|---|---|
| F-1 §2.2 deadline 射程 | 已改写 | 方向对，但引入 M-1 / M-2 的归属错误 |
| F-2 人写文档引文与行号 | **部分** | `spec.md` 已改 ✓；`deferred.md` D-2 未改 → **M-6** |
| F-3 护栏测试名 | 已改 | ✓ 核实无误 |
| F-4 D-7 落盘 | 已写 | ✓ **内容三条全部核实无误**，这次是真写了 |
| F-5 `status.md` 全面滞后 | 已重写 | 六个子项都覆盖了，但新写的两句有问题 → **M-3 / M-4** |
| F-6 §4 overrides 与行号 | 已改 | 事实对，归属错 → M-2 |
| F-7 `1a2daac` 指针 | 已改 | ✓ 且加了「不要去看它」的反向提示，好 |
| F-8 实测依据不在 `main` | 已加说明 | ✓ 核实无误 |
| F-9 评审沿革 | 已改 | ✓ 16 份点数正确 |
| F-10 全称句射程 | 已收窄 | ✓ |
| F-11 R3 `needs-fix` 无声关闭 | **未处置、未说明** | → **M-5** |
| F-12 `-onmain` 指向 squash | 已记 | ✓ |
| F-13 人写文档新增的合成代价 | 已记入 §2.2 | ✓ 逐字一致 |
| F-14 `http2_ping_interval` 交还用户 | 已记 | ✓ |

**13/14 处置，1 条漏。**

---

## 七、提交信息逐句核查

| 提交信息原句 | 核实 |
|---|---|
| 「all eight are carried out, none widened or narrowed, and neither squash commit message overstates」 | ✓ 与被引评审的结论一致，未加码 |
| 「Everything it found was in the documents」 | ✓ |
| 「`783f023` … bound the streamed body to the same `attempt.deadline_at` the header wait uses」 | ✓ 代码核实 |
| 「which is exactly the defect `deferred.md` had filed as D-6」 | ✓ D-6 = body 不在 deadline 内 |
| 「1200s now bounds the whole streaming answer」 | ✓（精度边界见 m-12） |
| 「The same commit removed the two override maps, which the spec's §4 named as still wired」 | ⚠️ 半真：`783f023` 删的是 schema 字段；§4 说的「消费方读 overrides」是 `064ba63` 改的 → M-2 |
| 「the synthesised object is now written there as "HTTP 200 plus a `message_start`"」 | ✓ 磁盘 `:406` 逐字 |
| 「It is marked resolved rather than left standing」 | ⚠️ 只在 `spec.md`；`deferred.md` D-2 仍 standing → M-6 |
| 「Line-number citations into that file are replaced with section names」 | ❌ 只在 `spec.md` → M-6 / m-7 |
| 「it now points at `52d877c`」 | ✓ |
| 「the guard is `test_environment_routing_matches_native_httpx`」 | ✓ |
| 「a gap … is now D-7」 | ✓ **真的写进去了**，且缺口描述三条全对 |
| 「`load_proxy_config()` flattens CLI, `GHC_PROXY` and YAML into one field with no provenance」 | ✓ 代码核实 |
| 「so the priority order `config.example.yaml` specifies cannot be implemented downstream」 | ✓ 人写文档 `:255-263` 逐字核实 |
| 「`status.md` was still listing six scheduled fixes that are all finished, and a test count from two slices ago」 | ✓ 1504 确是 `dbb6104` 那一轮的数 |
| 「Two things are recorded for the user rather than acted on」 | ✓ 两条都逐字核实 |

未夸大处占多数；三处偏差全部指向 M-6 / M-2 这两条。

---

## 八、能不能集成进 `main`

**建议：先改 M-1、M-2、M-3、M-6 四条，再合。** 这四条都是**当前态假断言**，而不是风格问题——它们与本次提交的主题（清理过期断言）撞在同一处，直接留进 `main` 会让下一个读者按错的提交号去查、按错的主语理解 D-5、以为 e2e 是红的、并在两份活文档之间读到互相矛盾的合成物状态。四条改动都在文档里，量很小。

M-4、M-5 应一并改，但不阻断：M-4 只要把绝对值降级为「不可比」即可；M-5 补一行「F-11 未处置，理由是……」即可。

m-7 ~ m-14 可以在下一次顺手带。

代码侧（`10da106` 及之前）本轮未评，`uv run pytest -q` / `ruff check` 在本树全绿，`pyright src tests` 21 errors（未与 `main` 对照，不作判断）。

---

## 九、本报告的自我限定

- 我核的是「文档写的与代码/文件当前是否一致」以及「上一轮 14 条是否被正确处置」。**我没有重新评审实现的正确性**，也没有独立验证七条保活性质。
- 跑过的四条命令都在**本 worktree**（`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`）里执行，对应的是本分支 HEAD `029bf0a`，不是 `main`。`main` 与本树在 `src`/`tests` 上有 10 个文件的差异（本树少了 `main` 最新的 7 个提交，多了 `10da106`），所以 1554 / 21 这两个数只代表本树 HEAD。
- 「94 → 95 是解包副本的假数字」这一条：**21 是实测的硬事实，把握高**；「成因是缺 venv 导致导入解析退化」是我的最可能解释，**把握中**，未实际复现解包环境去证。无论成因如何，94 与 21 不可比这一点已经足以要求改写。
- `docs/.human-controlled/` 只在主工作树磁盘上存在，我以只读方式读取，未做任何修改。

---

## 十、定向复核（`bf1e3c1`）

- 对象：`bf1e3c1 docs: fix what the last correction got wrong, and close the review it left open`，外加代码侧 `b472a03 fix: print a proxy origin's port even when it is zero, and state the set hazard exactly`。
- 范围：**只做定向复核**——第八节的 M-1 ~ M-6 是否改对、m-8 ~ m-14 的顺带修订有没有改出新问题、以及「这次是不是又引入了新的假断言」。未重跑第五节那批已确认项。
- 本轮实际跑过的命令（本 worktree，HEAD = `bf1e3c1`）：`uv run pytest -q`、`uv run pytest -q tests/e2e --collect-only`、`uv run ruff check src tests`、`uv run pyright src tests`、一条查 httpx 端口解析的 `uv run python -c`。未修改仓库任何文件。

### 10.1 结论

**四条严重项全部改对，M-4、M-5 也处置得当；F-11 的关闭理由站得住。** 逐条独立复核（含两次实测复现）都对得上，这次**没有再出现「当前态假断言」**——上一轮抓到的四条全是「文档说的与代码/环境当前不符」，这一轮一条都没有。

新问题 3 条，形态与上一轮不同：**一条断链、一条计数、一条归因**。都不误导读者对代码现状的判断，但 N-2 会被下一个读者当成又一处失效计数。

- 建议改后再合：N-1、N-2（各一两处字面改动）
- 建议一并改：N-3
- 可不改：N-4

### 10.2 新问题

#### N-1【中｜把握：高】同一个提交改掉了小节名，却没改指向它的两处引用

`bf1e3c1` 把 `deferred.md` 的 `## 归用户的提醒（不动人写文档）` 改名为 `## 交还用户的文档问题（我方不改人写文档）`（现 `deferred.md:58`）。两处引用仍写旧名：

- `deferred.md:20`（本次新写的 D-2 第二条）：「（英文半句仍写 `half-block`，见下方**「归用户的提醒」**。）」
- `status.md:125`：「……见 `deferred.md`**「归用户的提醒」**一节——我方不改那份文件。」

`rg '归用户的提醒'` 在三份活文档里只剩这两处，都指不到东西。

这是上一轮 m-11 的同型复发，而且**发生在同一个提交内**：一边把两处「见文末」修好，一边因为改标题造出两条新断链。改法就是把两处旧名换成新名。

#### N-2【中｜把握：高】`spec.md` 前言的「18 份」与它自己列的项目对不上，也与 `status.md` 直接打架

`spec.md:6`：

> 本文所在主题共 **18 份**独立评审报告：asyncio 正确性 8 轮、契约 3 轮、传输层 3 轮、调和 1 份、合入后传输层复评 1 份、合入后 cap 去重复评 1 份，以及裁决落实与文档一致性核对 **1 份**（`docs/tmp/260820-review-keepalive-rulings.md`、`docs/tmp/260820-review-keepalive-doc-fixes.md`）。

数一遍：8 + 3 + 3 + 1 + 1 + 1 = **17**，与 `ls docs/agents/delivery-keepalive/ | rg '^review'` 的实点 17 个文件完全吻合。最后一项写「**1 份**」却在括号里列了**两个**文件名。总数应当是 **19**。

同时 `status.md:26` 写的是「文档与裁决核对 **2 轮**」。两份活文档对同一件事给出 1 与 2。

这是上一轮 m-9 的同型：**可以机械数出来的计数没有数。** 说「18 份」之前把括号里的文件名数一遍就会发现。

#### N-3【低-中｜把握：高】把调和时点的「Pyright 干净」也归给解包副本的读数陷阱，归因错了

`status.md:13` 末句（本次新写）：

> 本文档第二节末尾那句调和时点的「Pyright 干净」**同理**，是当时那个环境的读数。

`review-reconciliation.md:161-163` 的原文是在**真实 worktree** 里跑的：

```text
$ uv run pyright src tests
0 errors, 0 warnings, 0 informations
```

同一份报告紧接着自述「独立探针均从已确认的 worktree 模块导入生产代码，文件放在 `/tmp`，未修改仓库」——它不是 git 解包副本，没有那个环境陷阱。那个 0 是那棵树在那一刻的真读数。

真正的解释是**主线漂移**，而且有中间证据：`review-transport-keepalive.md:133` 记录中途是 7 errors（`handler.py` 5、`pipeline_app.py` 2），今天本树是 21。所以序列是 0 → 7 → 21，全部由并行会话的提交累积而来，与本主题无关。

用「同理」把它并进解包副本那一类，等于**用一个错误的理由抹掉一条真实且有用的信息**。建议改成：「彼时那棵树上确实是 0（`review-reconciliation.md` 在真实 worktree 里测的）；此后主线累积到 7、再到 21，与本主题无关。」

#### N-4【极低｜把握：高】前言那句「§2.2 与 §4 …由文档一致性核对的第二轮覆盖」在 `bf1e3c1` 之后又欠一次

`bf1e3c1` 第三次重写了 §2.2、§4 与前言本身；覆盖这一次的是本节（定向复核），不是「第二轮」。这句话按轮次写，每改一次就要动一次。建议改成不带轮次的表述（例如「§2.2 与 §4 经文档一致性核对逐轮跟进，最近一次见 `260820-review-keepalive-doc-fixes.md` 第十节」），否则它自己就是下一个会过期的断言。

### 10.3 六条的逐条复核结论

**M-1 —— 已改对 ✓（把握：高）**

- `deferred.md:60` 的 D-5 条目主语已是「`upstream_request_deadline` **被 `response_header_overrides` 解析**」，并给出原式 `resolve_timeout(route.model_id, timeouts.upstream_request_deadline, timeouts.response_header_overrides)`，与 `git show 064ba63 -- src/app/server/handler.py` 的删除行逐字相符。
- `spec.md:143` 同样改对：「`upstream_request_deadline` **被 `response_header_overrides` 解析**（`deferred.md` D-5）由 `064ba63` 修掉」。
- 「`response_header` 无消费方是另一件事」**两处都说清了**：`deferred.md:64`「**`response_header` 无消费方是同一节里的另一件事**（一道从未实现的守卫），不要与 D-5 并成一条」；`spec.md:143`「**注意 D-5 的主语是 deadline 不是 `response_header`**；`response_header` 无消费方是另一件事，一道从未实现的守卫」。与权威定义 `docs/tmp/260820-deferred-d3-d5-d6.md:22`（「同节的 `response_header` 无消费方是另一件事：一道从未实现的守卫」）一致。
- 额外加的那段「初版这里写反了主语……权威定义见 `260820-deferred-d3-d5-d6.md` §2 的标题」是对的，且指得到（该文件 `:186` 的小节标题）。

**M-2 —— 三处全部拆对 ✓（把握：高）**

| 位置 | 现文 | 复核 |
|---|---|---|
| `deferred.md:57-61` | D-5 → `064ba63`（17:51）+ 同一提交去掉 `stream_idle_seconds` 的 overrides 解析；D-6 → `783f023`（18:09）+ 同一提交删 `schema.py` 两字段 | ✓ 与 `git log -1 --format=%ci` 的 17:51:54 / 18:09:36 相符；`git show 783f023 --stat` 确无 `handler.py` |
| `spec.md:135` | 「`064ba63` 之后这半句也不成立了——那次提交把 `stream_idle_seconds` 的 overrides 解析删掉，随后 `783f023` 又删掉了 `schema.py` 里对应的两个字段」 | ✓ 与 `git show 064ba63` 里 `def stream_idle_seconds(chain, model)` → `def stream_idle_seconds(chain)` 相符 |
| `spec.md:143` | D-5 → `064ba63`，D-6 → `783f023` | ✓ |
| `status.md:121` | 「D-5 由并行会话的 `064ba63` 修掉、D-6 由 `783f023` 修掉」 | ✓ |

**M-3 —— 已改对 ✓ 并实测复现（把握：高）**

`status.md:15` 现在写「**已经修好了**，别再按红灯处理」，指名 `65e0781`（主线孪生 `0c1524f`）、`from harness` → `from _harness`、`addopts` 已含 `--ignore=tests/e2e`。

本轮实测：`uv run pytest -q tests/e2e --collect-only` → `5 tests collected`。与文中说法一致。

括号里那句「`52d877c` 合入时点它确实是红的，那时的判断没错」也成立：两个修复提交都晚于 `52d877c`。这个「当时对、此后被修掉」的写法比单纯删掉更好——它保住了上一轮评审员当时判断的正确性。

**M-4 —— 已改对 ✓ 并实测复现（把握：高；残留见 N-3）**

`status.md:11` 现在写「Pyright **净增 0**（本树基线与当前均为 21 errors，`uv run pyright src tests`）」；`:13` 把 94/95 降级为「在 git 解包副本里测的……不可比，不要当闸门数引用」，并保留了「净增 1 那个差值可信」这个正确的区分。

本轮实测当前 HEAD `uv run pyright src tests` = **21 errors**，与我上一轮在 `029bf0a` 上测得的 21 一致，**净增 0 成立**。

**M-5 —— 理由站得住 ✓（把握：高）**

`status.md:30` 给的三条归宿，逐条查证：

- ① SOCKS 只告警由用户 S2 裁决消解 —— `deferred.md` D-3f 有据 ✓。
- ② 兼容范围与迁移规则随 `pool_idle_expiry` 整个撤销而消失 —— `deferred.md` D-3a 自陈「不新增任何配置键，也没有兼容范围要谈」✓；剩下的 proxy 优先级缺口已落成 D-7 ✓（其三条事实我上一轮已逐条核实）。
- ③ 提交内 fd 回归 —— `test_the_keepalive_is_on_the_socket_of_a_connect_tunnel` 在 `main:tests/unit/server/test_http_client_build.py:409` ✓；**「已由合入后复评独立复验」也确有其事**：`review-merged-upstream-keepalive.md:5` 与 `:86` 用真实响应的 `network_stream` socket 读回直连 / HTTP forward proxy / **HTTPS CONNECT tunnel** 三条路径的 `{SO_KEEPALIVE: 1, TCP_KEEPIDLE: 7, TCP_KEEPINTVL: 7, TCP_KEEPCNT: 4}`，并有 `tcp_keepalive_interval: 0` 的反向对照（三者均 `SO_KEEPALIVE: 0`）。

「该补的是这段关闭说明本身，不是再跑一轮 R4」——**这个判断成立**。理由是三条前置条件各自都有可查证的归宿，而 R4 的作用只能是重新确认它们；重跑一轮不会产生新信息。

补一条这段说明**没写、但让理由更强**的事实（可补可不补）：R3 之后那三个提交并非全然无人审。`review-merged-upstream-keepalive.md` 评的正是它们压成的 `e12003a` / `52d877c`；虽然射程限定在代理修复机制被替换的那一部分，但它对 forward / tunnel 两条路径做了逐参数比对，并实测了三条路径的 fd。写上这一句，「不需要 R4」就从「三条各有归宿」升级为「后续状态实际已被独立评审覆盖过」。

**M-6 —— 已改对 ✓，且全仓复查通过（把握：高）**

- `deferred.md:17-20` 的 D-2 已改成索引条目：「权威表述在 `spec.md` §2.2 的【需用户裁决】块，本条只作索引」，两条状态与 `spec.md` §2.2 完全一致（窗口定义仍冲突待裁、合成物已消解），行号已去掉，并写明「不引行号」的理由。两份活文档不再打架。
- **全仓复查**（`rg 'human-controlled/[a-zA-Z._-]*:[0-9]' docs/ .claude/`）：剩余命中全部落在历史件——`review-contract.md`（4 处）、`review-contract-r2.md`、`review-transport-keepalive.md`（2 处）、以及 `docs/tmp/` 的若干报告（含本报告第八节引用旧文的那一处）。按项目约定，历史报告记的是写作当时为真的事，不必回改。
- **三份活文档（`spec.md` / `deferred.md` / `status.md`）已无任何指向 `docs/.human-controlled/` 的行号引用。**

### 10.4 m-8 ~ m-14 的顺带修订

| 项 | 处置 | 复核 |
|---|---|---|
| m-8 前言未评审范围 | 已扩到 §2.2 与 §4 | ✓（残留 N-4） |
| m-9 击发次数 | 已改成五次并逐条列出 | ✓ 五项与我上一轮点的五项一一对应：本节两次、§2.2 一次、§3 `http2_ping_interval` 一次、用户改写人写文档一次 |
| m-10 `handler.py:131` | 已改成「`src/app/server/handler.py` 的 `attempt_deadline` 读出」 | ✓ 符号名不随主线行号漂移 |
| m-11 两处「见文末」 | 已改成「文档侧顺手项」一节（`deferred.md:92`、`status.md:121`） | ✓ 该小节在 `deferred.md:122`，指得到；**但造出 N-1** |
| m-12 §2.2 精度边界 | 已补三点 | ✓ 与 `src/app/streaming/deadline.py` 的 docstring 逐条对得上（拉取边界判定、不打断消费、每次尝试各一份），且「砍断一次已经在输出的长回答」后面补了「准确地说，是砍断当前这次尝试；重试会另起一份新的界」 |
| m-13 评审件里的全角 `／` | 未改 | 属历史件，同意不改 |
| m-14 四路 → 五路 | 已改 | ✓ 但与 N-2 的「18 份」互相矛盾 |

`spec.md:139` 的旧链路括号也顺手补强了，且补得准确：「读它们的是旧链路的 `app/streaming/idle_timeout.py` 的 `resolve_stream_idle`，只有 `routes/anthropic.py` 导入。……注意 `with_idle_timeout` 本身是两条链路共用的函数——**分离的是字段，不是那个函数**。」这正是我上一轮在第五节第 3 条里点出的那个精度，已经写进去了。

### 10.5 顺带核实的 `b472a03` 与「未采纳的建议」重写

不在本次复核范围内，但因为 `deferred.md` 记了它，顺手核了三条，**均无误**：

1. `src/app/server/composition.py:233` 现为 `... if parsed.port is not None else ...`，docstring 写明「httpx parses an explicit `:0` as the integer 0」。实测 `httpx.URL('socks5://h:0').port` → `0`，`httpx.URL('socks5://h').port` → `None`，与文字逐字相符。
2. 回归 `test_the_socks_warning_keeps_an_explicit_port_zero` 在 `tests/unit/server/test_http_client_build.py:223` ✓。
3. 「未采纳的建议」从「两个判据等价」改写成「范围与 ROI 取舍」，是把射程改对了。其中「当前显式 proxy 下 `_mounts == {}`，所以今天不存在这个缺口」成立（`_proxy_mounts` 在配置了 proxy 时返回空 dict）；被援引为覆盖核心调度机制的 `test_the_real_pool_opens_another_connection_once_one_is_full` 确实存在且参数化（`tests/unit/upstream/test_stream_cap.py:294`），并且是 `main` 上**已有**的测试（`main:tests/unit/upstream/test_stream_cap.py:234`），没有被误算进「新增 5 条回归」。

### 10.6 闸门实测复现

| 项 | `status.md` 声称 | 本轮实测 |
|---|---|---|
| 全量 | 1555 passed / 3 skipped | **1555 passed, 3 skipped in 102.16s** ✓ |
| Ruff | 通过 | `All checks passed!` ✓ |
| Pyright | 21 errors，净增 0 | **21 errors, 0 warnings, 0 informations** ✓ |
| 新增回归 5 条 | 1550 + 5 = 1555 | ✓ 算术自洽；第 5 条是 `b472a03` 的 `test_the_socks_warning_keeps_an_explicit_port_zero` |
| `tests/e2e` | 已修，收集出 5 个 | `5 tests collected` ✓ |

### 10.7 标点

`bf1e3c1` 三份活文档的新增段落全部通过扫描：中文句中无半角 `,.;:!?()`，无 `--` 充当破折号，无全角拉丁/数字，无硬折行。

### 10.8 「是不是又引入了新的假断言」

**没有引入「当前态假断言」。** 上一轮抓到的四条（M-1 主语反、M-2 提交归错、M-3 红灯早已修好、M-6 两份文档打架）都属于「文档说的与代码/环境当前不符」，这一类这次一条都没有——我逐条独立核了改动涉及的每一句关于代码现状的陈述，包括两次实测复现。

新出的三条形态不同，也都不误导读者判断代码现状：

- **N-1 是断链**：读者点不到那一节，但不会因此相信一件假事。
- **N-2 是计数**：「18」与它自己列的 19、与 `status.md` 的 2 打架。不影响任何技术判断，但它恰好是这份文档反复强调「可机械核对的东西要数一遍」的那一类，留着会削弱文档自己的可信度。
- **N-3 是归因**：把一个真实读数说成环境артefact。它不会让人对当前 21 errors 判断错，但会让人对「0 → 7 → 21 是主线漂移」这条有用的事实失去线索。

一个观察，作为**倾向性判断（依据是连续两轮的样本，不足以当规律）**：两轮引入的错误都集中在「给一句话补元信息」的动作上——第一轮补的是提交号，第二轮补的是小节名与份数。正文事实（代码怎么接线、哪个字段在不在）两轮都没错过。如果要立一条自检，机械化程度最高的是：**改标题之后 `rg` 一遍旧标题名；写下带数字的份数之前，把被数的东西列出来数一遍。**

### 10.9 本次复核的自我限定

- 定向复核，**未重跑第五节那批已确认项**（归档分支指向、D-7 三条事实、人写文档引文、护栏测试等）。它们在 `bf1e3c1` 中未被改动，`git show bf1e3c1 --stat` 的三份活文档 diff 我逐行看过，没有触及那些段落。
- 四条实测命令都在**本 worktree**（HEAD = `bf1e3c1`）执行，不代表 `main`。
- N-3 里「0 → 7 → 21 是主线漂移」这条：0 与 7 我采信两份评审报告的自述（**沿用**，未复跑历史提交），21 是本轮实测。这一条不承担承重结论，只用于说明「同理」二字归因错了——而那一点只需要 `review-reconciliation.md` 自陈在真实 worktree 里跑，就已经成立。
- 代码侧 `b472a03` 我只核了 `deferred.md` 记的那三条与其对应实现，**没有对该提交做完整代码评审**。

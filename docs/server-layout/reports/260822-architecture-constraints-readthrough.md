# 通读补口：`architecture.md` 428–679 与 `spec.md` 对 `app/server` 布局提案的约束

**日期**：2026-08-22。**被查对象**：`.dev/docs/server-layout/README.md`（布局提案）及其两份评审报告。
**立场**：只读调研。除本报告外未写任何文件，未执行任何搬迁、未提交、未推送、未触碰 `docs/.human-controlled/`。
**任务来源**：两位评审各自声明未读 `architecture.md` 后半与 `spec.md`，而 F2（blocker）悬在这两处未读区上。

**一句话结论**：**F2 成立，但它引的两句只有一句真的咬得住；真正咬住它的三条在 `spec.md` 里，而 `spec.md` 恰好是 2026-08-19 授权明文不覆盖的那份。** 与此同时，第 8 节六步里有四步明确触碰 `spec.md` 的可观察行为合同（第 3、4、5、6 步），第 2 步触碰一个承载点。另外发现一处**跨文档直接冲突**：`spec.md`／`architecture.md` 冻结的「首个完整 block 前不得暴露 HTTP success headers」与用户 2026-08-22 亲笔的 `docs/.human-controlled/client-side-block-delivery.md`「只在第一次 HTTP 200 尝试时转发响应头」正面相反，而当前新链实现的是用户那一侧。这条决定了 S4 与 F15 该怎么表述。

**计数**：本报告给出 5 条对提案的实质修正（其中 1 条推翻评审的一半论据、1 条给 S4 补上它缺的正面依据），外加 1 条跨文档冲突登记。

---

## 0. 我读了什么、没读什么

**逐字读了**：

- `.dev/docs/anthropic-responses-bridge/architecture.md` 第 428–679 行（Failure matrix、Post-commit continuation、History 与 observer、真值时点、History 投影、非流式路径、可证伪的架构判据、结构怪味与目标处置、已决 Spec 输入与 ADR 承载记录、唯一用户裁决矩阵、D-ARCH／D-MIGRATION 全部、route 前置门、评审问题处置表、容量政策、最终推荐）。
- `.dev/docs/anthropic-responses-bridge/spec.md` 全文 588 行。
- 为核验评审引文而定点读了 `architecture.md` 的第 11、38、278–299、340、390–419 行（这些在 428 之前，属于「已有人读过」的区段，我只取证不复述）。

**另外读了（超出任务清单，但直接命中提问）**：

- `.dev/docs/anthropic-responses-bridge/implementation.md` 第 258–293 行，那里有一份**活的**结构怪味登记，比 `architecture.md` 那张表更贴近本提案。
- `docs/.human-controlled/client-side-block-delivery.md` 全文（只读）。
- 代码取证：`src/app/server/pipeline_app.py` 第 176–311、715–760、815–960 行；`src/app/server/handler.py` 第 377–430 行的定位行；`src/app/server/composition.py:460,466`。

**没读**：`architecture.md` 第 1–10、12–37、39–277、300–339、341–389、420–427 行（除上述定点取证外）；`docs/.human-controlled/` 除 `client-side-block-delivery.md` 外的其余文件（`lifecycle.md`、`module-org.md`、`request-pipeline.md`、`api.md`、`test-org.md`、`upstream-retry-and-continuation.md`、`message-*.md`、`cli.md`、`ghc-api.md`、`release-and-deployment.md`、`config.example.yaml`）；`implementation.md` 第 1–257 行；`.dev/docs/server-layout/reports/` 里的链路图与既有结论两份；任何测试文件。**特别提示**：F2 的落点之争若还牵涉 `docs/.human-controlled/lifecycle.md`，我没读那份，答不出。

---

## 1. F2 的 blocker 是否成立

### 1.1 评审引的两句：一句咬住，一句咬不住

评审 F2 引了两句 `architecture.md` 原文。我逐字核对，**引文本身准确**，但适用性一句成立一句不成立。

**第一句（成立，且比评审说的更强）**——`architecture.md:340`：

> 每个 exchange 有唯一 close owner。Driver 在 success、retry、parse error、buffer failure、client cancel 与 shutdown 路径都退出 async context；converter 和 observer 不关闭 transport。即使已经观察到 protocol terminal，仍必须完成 context exit，因为 terminal event 不等于物理连接已释放。

评审把这一句放在次位，主论据压在第二句上。实际上**这一句才是正击**，因为被搬的代码关闭的**不只是下游 body**，它透传到上游连接。证据在代码自陈：

`src/app/server/pipeline_app.py:897`（`_AccountedStreamingResponse.__call__` 的 `finally` 内注释）：

> Closing the body is this response's job and nobody else's: the framework iterates the generator but never closes it, so a client that stops reading leaves the whole delivery chain suspended for the collector to find. **Every layer below already knows how to release the upstream when it is closed — until this line, nothing asked them to.**

`src/app/server/pipeline_app.py:943-945`（`_tracked_delivery` docstring）：

> `aclosing` for the same reason `stream_delivery` wraps its own inner generator: a bare `async for` closes nothing, so a client that goes away throws GeneratorExit at the `yield` below and unwinds straight past the loop, **leaving the delivery chain — and the upstream response under it — suspended** until the collector happens to reach it. …… It also **puts the upstream's release ahead of `finish()`**.

即：`_AccountedStreamingResponse.aclose()` → `_tracked_delivery` 的 `aclosing` → 下面每一层 → **上游 response 释放**。这正是 340 说的 close owner 链。把它整体搬进 `app/observability/`，就是让 observer 包持有 transport 的关闭责任，340 明文禁止。

**第二句（咬不住，建议从 F2 里删掉）**——`architecture.md:398`：

> **Downstream sink** 是唯一 body writer，串行接收完整 bytes batch。Heartbeat、error、normal block 与 terminal 不得从旁路并发写响应。

`_AccountedStreamingResponse` **不写 body**。它继承 `StreamingResponse`，`__call__` 里 `await super().__call__(...)` 由框架完成 ASGI send，它自己只在外层加了一圈 `finally`。它是「唯一 body writer 的宿主」，不是第二个 writer。398 禁止的是「旁路并发写」，这里没有旁路，也没有并发。评审那句「这直接撞上第二句的后半」不成立。

**这不影响 F2 的结论，但影响它的可信度**：一条 blocker 由两条依据支撑，其中一条经不起核对，会让接手者对另一条也打折。建议把 F2 的依据换成下面 1.2 的三条。

### 1.2 真正咬住 F2 的三条，全在 `spec.md`

这三条比 `architecture.md` 那两句更硬，因为 2026-08-19 的授权说明明写它**不覆盖 `spec.md` 的可观察行为合同**（`architecture.md:5`）。

**（1）关闭恰好一次**——`spec.md:389`：

> 每个 upstream response／stream／WS connection 在成功、失败、retry、cancel 与 shutdown 路径上都必须关闭一次。

**（2）finalize 恰好一次，且由单一 owner 解决竞态**——`spec.md:424`：

> finalize恰好一次；成功只在 terminal合法且所有 committed blocks drain后成立。

`spec.md:448`：

> cancel、upstream terminal与shutdown竞态必须通过单一 finalize owner解决，保证**资源关闭和finalize均恰好一次**。

`_StreamAccounting.finish()` 的幂等（`pipeline_app.py:838-841` 的 `if self.done: return`）加上 `_tracked_delivery`／`_AccountedStreamingResponse` 两个入口，就是这条合同在流式路径上的**唯一承载机制**——代码自己也这么写（`pipeline_app.py:822`：「Shared by the delivery generator and the response that carries it, because either one may be the last to run. `finish` is idempotent so whichever gets there first records, and the other is a no-op.」）。把这台机器搬进 `app/observability/`，等于把「finalize 恰好一次」的实现放进 observer 包。

**（3）observer 不得回写 driver state**——`architecture.md:467`（在我的区段内）：

> Journal 不是另一个 state machine；它记录 owner 已发布的事实与 effect，**不允许 observer 回写 driver state**，也不等于默认 SQLite schema。

配合所有权表 `architecture.md:290`：

> | `TerminalFacts` | parser/normalizer 提议，**driver finalize** | request-scoped | 各字段 single-assignment，final error 最终冻结 | …… |

`_StreamAccounting.finish()` 里的 `self.context.reply = terminal`（`pipeline_app.py:850`）就是这条禁令下的写入。评审这一点抓对了。

**追加一条评审和提案都没看到的事实**：这处写入**已经被登记**，并且**已有裁决**，登记在 `implementation.md:268`：

> | `_StreamAccounting.finish()` 中 `trace.absorb` 与 `context.reply` 的两套门 | …… 今天 `context.reply` 无读者所以无可观测影响 | 有意保持不一致并就地注释。…… 真正的理由是保守：`reply is not None ⇒ 回复已完成` 是 hooks 与 History 现有契约，放宽它是契约变更；而 STR-04 已点名需要 failed History，第一个读者不是假想的。**故与 STR-04 同一切片一并裁决** |

也就是说，把 `_StreamAccounting` 搬进 `app/observability/` 不只是「observer 写领域状态」，而是**把一处已登记、已明确推迟到 STR-04 一并裁决的领域状态写入，先行搬进一个按定义不能持有它的包**——搬迁本身会替 STR-04 预先作答。这是 F2 该有而没有的那条加重情节。

### 1.3 一条对 F2 的反向限缩：搬迁本身不被禁止，被禁止的是终点

`architecture.md:611`（在我的区段内，属「选择 B 后可局部调整的边界」）：

> - Cancellation-resilient cleanup 的具体 task／scope 封装和 typed outcome 命名；**唯一 close owner、资源终态和 primary／secondary failure 保真不变**。

所以「把 cleanup 换个封装／换个文件」是明文允许的局部调整，**不需要重开 `D-ARCH`**。F2 若被读成「这块代码不能动」，就读过头了。禁止的是**终点是 `app/observability/`**（因为 340 点名 observer 不关闭 transport），不是**移动**本身。

同一处还给出了这块代码不可改变的三项：唯一 close owner、资源终态、primary／secondary failure 保真。后者正是 `_AccountedStreamingResponse` 第 900–907 行做的事（`raise primary from close_error`），而 `architecture.md:519`（我的区段内）把它写成了**可证伪判据**：

> - **exchange cleanup：** HTTP／WS success、fallback、parse failure、capacity failure、client abort 与 shutdown 都退出 async context，资源计数归零；cleanup 中点连续投递第二次及更多 cancellation 时，同一 shielded cleanup task 仍执行到 terminal 且底层 close 至多一次。`cancel + close error` 与 `parser error + close error` 最终保留 primary 并以 close error 为 `__cause__`；`normal exit + close error` 最终传播 close error；所有分支都观察 secondary failure 且无 orphan task。

一句话：**这四个成员里有三个是 exchange cleanup 判据的被测对象，不是观测者。**

### 1.4 正确的落点

先把四个成员分开——它们不是一类东西：

| 成员 | 它拥有什么 | 文档判据 |
|---|---|---|
| `_counted_upstream` | 什么都不拥有：`AsyncIterator[bytes]` 透传计数，只写 `_Trace` 与 `chain.active_requests` | 无禁令。`architecture.md:610` 明确把「metrics／trace 投影字段和诊断采样方式」列为可局部调整 |
| `_Trace`／`_log_completion`／`_translation_losses` | 同上，纯读事实 + 发射 | 同上，见第 2 节 |
| `_tracked_delivery` | `aclosing` 关闭交付链（透传到上游释放）、判定三种结束形态、调 `finish()` | `architecture.md:340`、`519`；`spec.md:389` |
| `_AccountedStreamingResponse` | body close owner、primary／secondary 排序、保证 `finish()` 必跑 | 同上 + `architecture.md:611` 的三项不变量 |
| `_StreamAccounting` | 流式路径的 finalize-once、写 `context.reply` | `spec.md:424`、`448`；`architecture.md:290`、`467`；`implementation.md:268` |

**`app/observability/` 只能接收前两行。** 评审这一半判断正确。

**后三行的落点，评审给的 `app/server/accounting.py` 与文档指向的不是同一处。** 评审的理由是「它们拥有的是 response body 的关闭顺序与 finish 的幂等，**属于表面的交付所有权**」。而 `architecture.md:528`（结构怪味登记，在我的区段内）对同一形态给的目标处置正相反：

> | `src/app/routes/anthropic.py:99-120` | Route 持有 raw stream delivery 与 History finalization 接缝 | **Route 只绑定 HTTP envelope**；delayed response-start owner 与 **driver／delivery session** 拥有 headers、drain、commit 与 finalize |

以及 `architecture.md:442`（我的区段内）：

> 流式 route 必须使用 delayed-start ASGI response **或等价 owner**。

按这两条，drain 与 finalize 归 **driver／delivery session**，不归表面。因此文档指向的落点是 `pipeline/delivery/`（`DeliverySession` 与 `stream_delivery` 所在处），而不是 `server/accounting.py`。

**旁证**：`_AccountedStreamingResponse` 第 900 行注释自己说「`finish_stream_cleanup` orders the same pair the same way」，而 `finish_stream_cleanup` 在 `src/app/streaming/keepalive.py:69`，被 `src/app/pipeline/delivery/stream.py`、`src/app/streaming/sse.py` 与 `pipeline_app.py` 共同使用；`implementation.md:269` 还为该文件的 cleanup 路径保留了「cancellation-storm、cause chain、资源归零与无 orphan task」的组合回归 gate。也就是说这套语义**已经有一个归属地**，而它不在 `server/`。

**我的判断（权重：可据以行动，依据是三处原文而非口味）**：

- **排除** `app/observability/`：`architecture.md:340` + `spec.md:389/424/448` 各自独立成立。
- **文档指向** `pipeline/delivery/`：`architecture.md:528` + `442` + 现有 `finish_stream_cleanup` 的归属。
- **`server/accounting.py` 是可接受的中途停靠**，但它的**理由**要改写——不是「属于表面的交付所有权」（那与 528 矛盾），而是「本轮不动所有权，只把这三个从 `pipeline_app.py` 里摘出来，所有权的搬迁与 S4 的 driver 归位同批做」。
- **最省事且不失分的一步**：本轮第 3 步只搬 `_Trace`／`_log_completion`／`_translation_losses`／连接快照五件套／`_counted_upstream`，后三行**原地不动**，等第 4 步与 driver 归位一起处理。这与评审 Q3 里「第 3 步与第 6 步应该合并」的直觉方向一致，但依据不同。

**一处次要提醒**：`_counted_upstream` 虽可搬，但它在 `pipeline_app.py:741-757` 的**位置**是承重的——它被夹在 `with_client_deadline_at` 与 `with_deadline_at` 之间，第 744–745 行的注释解释了这个顺序为什么不能换（「the order decides which one gets to speak」）。搬函数不搬装配点，装配点仍留在表面；这没问题，但接手者不要顺手把装配也挪进 observability。

---

## 2. `_Trace`／`_log_completion`／`_translation_losses` 搬进 `app/observability/` 是否也有约束

**结论：没有禁令，且有一条正面授权；但有两条内容性约束随代码一起走，其中一条落在 `spec.md` 上。**

### 2.1 正面授权

`architecture.md:610`（我的区段内，「选择 B 后可局部调整的边界」）：

> - Request-local journal 的内部存储结构、**metrics／trace 投影字段和诊断采样方式**；默认 History 精简政策与 receipt owner 不变。

这三块正是「trace 投影」。移动它们不需要重开 `D-ARCH`。

### 2.2 「History 与 observer」「真值时点」「History 投影」三节对 observer 的四条限制，逐条对照

- `architecture.md:467`：「**不允许 observer 回写 driver state**」。→ 三块**全部合规**：`_translation_losses` 只读 `context.extras`（`pipeline_app.py:186-195`）；`_Trace.absorb`／`absorb_losses` 只写 `_Trace` 自身；`_log_completion` 只构造 `RequestLine`、`inc()` 指标、`write_request_record`、`logger.info`（`pipeline_app.py:268-310`）。**无一处写 `context` 或 driver 状态。**
- `architecture.md:477`：「普通 observer 也不得伪装成 receipt owner」。→ 不适用：这三块不碰 History durability。
- `architecture.md:483`：「`RESPONSE` observer 的成功语义是规范化 Anthropic response 已完成并满足 delivery contract。流式请求应在所有 blocks 与 terminal batch committed 后触发一次；**失败流不得发送成功 `RESPONSE`**」。→ 这条约束的是 hook 观察者，不是请求日志行；但它的**同形要求**在日志行上已经由 `_StreamAccounting._ending()` 与 `trace.status_override` 实现（`pipeline_app.py:856-877`）。**注意**：实现这条的是 `_StreamAccounting`，不是被搬的三块。所以如果第 3 步把三块搬走而把 `_StreamAccounting` 留下，「谁判定这条流是不是成功」与「谁写那一行」就跨了包——这不违反任何条款，但它是接口收敛时要处理的真实接缝，提案第 8 步第 3 条「纯搬迁 + 接口收敛」低估了这一点。
- `architecture.md:486`：「**Observer failure 可继续隔离，不得改变 request action**；但失败记录必须进入 hook records/metrics」。→ **今天不满足，而搬迁会让这件事更显眼**：`_log_completion` 从 `_StreamAccounting.finish()` 里被调用（`pipeline_app.py:859`），而 `finish()` 又在 `_tracked_delivery` 的 `finally`（`:959`）和 `_AccountedStreamingResponse` 的 `finally`（`:909`）里跑；日志发射抛异常会顺着这两个 `finally` 改变请求的出口异常。搬进 `app/observability/` 后，「observer 抛异常不得改变 request action」这条会从「同文件内的隐性事实」变成「跨包契约」。**我不提修法**（任务是只答文档怎么说）；登记为第 3 步应当带着一起看的一项。

### 2.3 一条真的落在 `spec.md` 上的内容约束

`spec.md:142`（双向字段处置矩阵的状态定义）：

> `DEGRADE` 表示请求可继续，但损失必须作为结构化 `ConversionFact` **进入 History、metrics 与 trace**，且不得伪装成已保真。

`_translation_losses` + `TRANSLATION_LOSSES.labels(...).inc()`（`pipeline_app.py:304-305`）+ `RequestLine.losses` 就是这条合同里「metrics 与 trace」两路的承载。**搬迁必须把指标接线一起带走**，否则一条冻结的可观察行为会在纯搬迁中静默丢失。这也是我把第 3 步判为「触碰 `spec.md`」的原因（见第 3 节）。

另有 `spec.md:504`（Observability 非功能要求）：

> 至少可观测：original／resolved model、selected endpoint、route override／fallback source、transport、capability source、attempt、retry owner、time-to-first-complete-block、block count／size、request resident bytes、global resident bytes、quota wait／capacity failure、commit frontier、backpressure time、conversion degradation、usage、error category、cancel／shutdown原因与finalize结果。**日志不得输出secret header、完整signature payload或未经裁剪的敏感content。**

这是一张清单加一条脱敏禁令，两者都随代码走，都不约束模块位置。（顺带：`request resident bytes`／`global resident bytes` 这两项已被 2026-08-19 用户重裁删除，见第 6 节的文档冲突登记。）

---

## 3. 第 8 节六步各自是否触碰 `spec.md` 的可观察行为合同

判定口径：**「触碰」= 这一步搬动的代码是某条 `spec.md` 冻结行为的承载点**，因此纯搬迁必须逐字保住它，而设计上的任何顺手改动都落在 2026-08-19 授权的**豁免区外**。不是说这一步一定会改坏行为。

| 步骤 | 触碰？ | `spec.md` 落点（行号为原文行） |
|---|---|---|
| ① `tls.py` → `lifecycle/` | **否** | 通读全文未见任何关于下游 TLS／监听器的冻结行为。`spec.md:391-399` 的 Header 契约讲的是 upstream／downstream HTTP header 语义，与 TLS 材料无关。**唯一未排除的风险在我没读的 `docs/.human-controlled/lifecycle.md`。** |
| ② `composition.py` 拆分上移 | **是（一个承载点）** | `spec.md:337`「application Anthropic pipeline 是唯一真实 upstream retry owner；**SDK `max_retries` 保持关闭**」；`:339`「每个真实 upstream exchange 必须对应一个可见 `Attempt`」；`:529`「真实upstream exchange数与`RequestContext.attempts`一致」。这三条的实现点就是 `src/app/server/composition.py:460,466` 的 `max_retries=0`（我实测确认）。另 `:486`「认证、base URL与request headers差异停留在transport adapter」约束 HTTP client 工厂的职责边界。**纯搬迁可保，但这一步不在授权豁免区内。** |
| ③ 抽出可观测性三块 | **是** | 对 `_Trace` 一路：`spec.md:142`（`DEGRADE` 损失必须进入 History／metrics／trace）、`:504`（可观测清单与脱敏禁令）。对 `_StreamAccounting`／`_AccountedStreamingResponse`／`_tracked_delivery` 一路：`spec.md:389`（关闭一次）、`:424`（finalize 恰好一次）、`:448`（单一 finalize owner，资源关闭与 finalize 均恰好一次）。**这一步是六步里 `spec.md` 密度最高的之一。** |
| ④ `handler.py` 按三条缝拆开 | **是，最重** | 交付选型一路：`spec.md:308-331`（block-level buffering 与 commit 契约、semantic block 完成条件）；驱动一路：`:333-348`（retry ownership，`handle`／`handle_bounded` 是 retry owner；`:348`「response header commit 与首 block commit固定绑定」）；`errors.py` 一路：`:381-389`（Error 契约，含 commit 前后错误形态不同）、`:391-399`（Header 契约，`:399`「response header commit policy必须与 retry 边界一致」）；deadline 一路：`:467`（limits 必须存在并可观测，含 `request deadline`）、`:469-475`（limit violation 的五项固定后果）。**外加一条用户 2026-08-22 裁决**：504 而非 408（`src/app/server/handler.py:389,426` 自陈「ruled 2026-08-22 and written into `client-side-block-delivery.md`」）。 |
| ⑤ 建立 `server/routes/` | **是（作为「怎么做」的约束）** | `spec.md:74`「Protocol leg 必须只在一个 route-policy 接缝按以下顺序决定；后续 transport、converter、retry strategy 与 **route handler 不得再次推导或静默改写**」；`:509`「request converter、response assembler、block buffer、route policy与orchestrator职责分离，但共享typed facts；**不得复制业务规则到route handlers**」。提案把 `apply_route`／`translation_target` 并入 `pipeline/routing.py`、把「瘦得多的派发」放进 `routes/inference.py`，方向与这两条一致；但「瘦身」之后 routes 里剩什么，正好是这两条要审的东西。 |
| ⑥ 旧链收尾 | **是** | `spec.md:30`「本规格不把 `/v1/messages/count_tokens` 改成 Responses wire API……**已有 OpenAI／Responses routes 继续拥有自己的公共入口**，但不得成为该 bridge 的 lifecycle owner」；`:428-431`（Tokenization 契约）；`:480`「`/v1/messages`的公共request／response schema、approval语义、hooks语义、History identity与count_tokens shape保持」。注意 `spec.md` 只保护 `/v1/messages`、count_tokens 与 OpenAI／Responses 入口，**Azure／Gemini／history／management 不在 `spec.md` 里**，它们的依据只有 `api.md`——提案第 6 节的判断在这一点上没有被 `spec.md` 推翻，也没有被它加强。 |

**汇总**：③④⑤⑥ 明确触碰；② 触碰一个承载点；① 就 `spec.md` 而言不触碰。

这直接坐实了事实核查报告 A1 的担忧并把它具体化：README 第 41 行「已获授权、可直接做」的范围，实际只有第 1 步是干净的。

---

## 4. `architecture.md` 的「结构怪味登记」与本提案的重叠／冲突

`architecture.md:522-532` 那张表共 7 行。逐行对照：

| 登记行（行号） | 与本提案的关系 |
|---|---|
| `src/app/routes/anthropic.py:99-120`（`:528`）「Route 持有 raw stream delivery 与 History finalization 接缝」→「Route 只绑定 HTTP envelope；delayed response-start owner 与 driver／delivery session 拥有 headers、drain、commit 与 finalize」 | **重复发现，且这是 S4 缺的那条正面依据。** 提案的 S4 说的是同一形态在新链 `_dispatch` 上的重演。**这条比 S4 现在引的「边界 2」有力得多**：边界 2（`:596`）点名禁止的是 policy／converter／transport／observer／History writer，不含入站表面（事实核查 A2 在这点上是对的）；而 `:528` 直接把「route 持有 delivery 与 finalize 接缝」登记为怪味并给出目标处置。**建议 S4 换用这一条，指控从「违反边界 2」降为「与已登记怪味的目标处置不一致」——级别下降，依据变硬。** |
| `src/app/anthropic/client.py:148-184`（`:529`）「流式 observer/finalize 与 executor 的非流式路径分裂」→「统一由 fact journal 的 request terminal 时点驱动」 | **重复发现。** 新链上同一形态是：流式经 `_StreamAccounting.finish()` 收口、非流式经 `_serve`／`_dispatch` 的 `_log_completion` 直接收口（`pipeline_app.py:341-351` 的注释明说这两条是「alternatives」）。提案第 3.2 节把它们并列成「可观测性」一类，没有识别出这是已登记的分裂。 |
| `src/app/pipeline/executor.py:190-267`（`:527`）「Driver 同时内联 hook、wire 构造、send、response observer 与 finalize」→「保留唯一 owner，但通过 protocol leg、transport、delivery ports 拆出执行部件」 | **支持第 4 步的方向**（`handler.py` → `pipeline/driver.py`），但提醒：目标处置是「拆出执行部件」，不是「把 HTTP 表面的活整块搬进 driver」。 |
| `src/app/pipeline/strategies/__init__.py:11-60`、`src/app/openai/client.py` 与 `responses_ws.py`、`src/app/streaming/buffered_retry.py:8-18`、`src/app/history/consumer.py:20-33`（`:526,530,531,532`） | 与本提案无直接重叠。 |

**一处结构性张力，值得报给主会话**：这 7 行里有 5 行的坐标（`routes/anthropic.py`、`anthropic/client.py`、`openai/client.py`、`openai/responses_ws.py`、`streaming/buffered_retry.py`）落在提案第 3.3 节判定为**生产不可达**的模块上。`architecture.md` 的怪味登记是以旧链为坐标系写的；提案第 6 步一旦执行，这张表会有一半指向不存在的文件。**这不是提案的缺陷，是两份文档之间必须对账的一件事**，且按项目规矩「报告原件是时点记录，不回填」，要动的是 `architecture.md` 这份活文档而不是报告。

### 4.1 提案与两位评审都漏掉的那份登记

`implementation.md:263-292` 有一份**活的**结构怪味登记，13 行以上，比 `architecture.md` 那张更贴近当前代码。其中三行直接命中本提案：

- **`:268`** —— `_StreamAccounting.finish()` 的 `trace.absorb` 与 `context.reply` 两套门，**已登记、已裁决「有意保持不一致并就地注释」、明确「与 STR-04 同一切片一并裁决」**。见第 1.2 节。这是对 F2 最有力的补强，也是对提案第 3 步「纯搬迁」定性的直接反驳。
- **`:274`** —— 「Route-happy与block-delivery的共享生命周期接缝……**若后继边界修复让route、delivery与ASGI各自finalize，仍可能重新形成第二sink或第二lifecycle owner**」，处置是「Main stream只建立一个 `DeliverySession` 和一个 ASGI writer，并让同一 `RequestContext` 贯穿 route→parser→delivery→History／hooks」。**这一行几乎是为第 3、4、5 步写的风险登记**：它说的正是「把生命周期从表面拆开」这个动作的已知失败形态。
- **`:280`** —— `src/app/pipeline/executor.py` 的 pre-attempt failure 路径，「后继retry／delivery边界修复容易分叉出另一套success／failure终结路径……**stream attempt、parser／delivery错误与ASGI完成都必须在同一 `RequestContext` 上 exactly-once finalize**」。

另 `:269` 登记 `src/app/streaming/keepalive.py` 的 cleanup 路径已修（`f27a8c0`，R3 0／0），并保留「cancellation-storm、cause chain、资源归零与无 orphan task」为组合回归 gate——即 `_AccountedStreamingResponse` 复刻的那套 primary／secondary 语义**在别处已有 owner 与既有 gate**。

**建议**：提案第 10 节「顺带发现」与第 8 节的风险段应当引用 `implementation.md` 的这份登记，而不是只引 `architecture.md`。

---

## 5. 「把生命周期从 HTTP 表面交回 driver」会不会改变已冻结的可观察行为

**方向本身安全**：`architecture.md:528`（route 只绑定 HTTP envelope）、`:596`（single driver 是唯一 lifecycle owner）、`docs/.human-controlled/request-pipeline.md`（`app.pipeline` 驱动模型请求的处理）三处同向。没有任何冻结条款要求生命周期留在 HTTP 表面。

**但接缝上坐着三条已冻结／已裁决的可观察行为，机械地搬会改到它们**：

### 5.1 客户端超时的两种可观察形态（用户 2026-08-22 亲笔）

`docs/.human-controlled/client-side-block-delivery.md`：

> 当客户端请求超时，如果已发 HTTP 200 响应头，则放弃当前缓冲块，发 SSE error 再收尾；如果还没发 HTTP 200 响应头，则直接返回 HTTP 504 Gateway Timeout。

这条的实现今天**跨着接缝**：时限起点在表面（`pipeline_app.py:392` 读 `client_delivery.client_request_deadline`，`:741` 用 `with_client_deadline_at` 包住流），而 504 的映射在 `handler.py:426`（第 389 行注释：「504 rather than 408, ruled 2026-08-22」），`handle_bounded` 自己还有一条回退时钟（`handler.py:377`）。第 4 步把 `error_status` 搬进 `server/errors.py`、把 `handle`／`handle_bounded` 搬进 `pipeline/driver.py`，正好把这条规则的两半分到两个包。**「已发 200 → SSE error；未发 → 504」是一条用户亲笔的可观察行为，是本次搬迁最容易被静默改掉的一条。**

### 5.2 finalize 与关闭各恰好一次（`spec.md:389/424/448`）

见第 1.2 节。`implementation.md:274` 已把「route、delivery 与 ASGI 各自 finalize」登记为已知失败形态。可观察后果是重复或缺失的完成记录，以及未释放的上游连接。

### 5.3 响应头提交时点 —— **这里有一处跨文档正面冲突，必须报给用户**

`spec.md:285`（冻结）：

> 首个 Anthropic content block 完整组装并通过 response hooks／limits 前，**下游不得看到 HTTP success headers**、`message_start` 或任何 body event。

`spec.md:348`（冻结）：

> response header commit 与首 block commit固定绑定：首个完整block及其`message_start`进入同一sink batch前不得提交HTTP success headers。

`architecture.md:397`：

> **Delayed response-start owner** 是 route 与 sink 之间唯一有权发送 ASGI `http.response.start` 的组件。流式 success headers 在首个完整 block 已 materialize、或无 block 的 terminal／pre-body error 已确定前保持未提交。

`architecture.md:442`（我的区段内）：

> 流式 route 必须使用 delayed-start ASGI response 或等价 owner。

**而用户亲笔的 `docs/.human-controlled/client-side-block-delivery.md`（该段由 `fa0b281`，2026-08-22 引入，晚于 Spec 的 2026-08-07 冻结）说的正相反：**

> ## 客户端响应头
>
> **不等到出现完整块才转发上游响应头给客户端**，但也不可能每次上游尝试都能提交响应头给客户端，而是**只在第一次 HTTP 200 尝试时转发响应头给客户端**。后续重试若 HTTP 报错只能转化为 SSE error。例如，后续上游尝试发送 HTTP 429，但我们找不到合适的载体转发 `Retry-After`。接受这个限制，只用 SSE error 告知出现限流。

**当前代码实现的是用户那一侧**：新链走 `_AccountedStreamingResponse`（普通 `StreamingResponse`，头随第一次上游 200 出去），`DelayedStartStreamingResponse` 只存在于 `src/app/streaming/sse.py:95`，即旧链。`implementation.md:267` 还记了一条相应裁决：「用户裁决**不再合成 HTTP 响应头**、因而也不再合成 `message_start`」（`0b57645`，2026-08-22）。

**这条冲突的影响面**：

1. 评审的 **F15**（「Delayed response-start owner 未安置」）**可能整条不成立**——因为按用户最新文档，新链本就不该有 delayed-start owner。请在处置 F15 前先解决这条冲突。
2. 提案第 5 节「与 `D-ARCH = B` 五项核心的对应」表里边界 4 那行的分歧（评审 F13 说不成立）也和这条相关：交付链的头部环节在两份文档里定义不同。
3. **`spec.md` 自称「唯一行为 oracle」（`spec.md:5`、`architecture.md:11`），而这一条已被用户后来的亲笔文档覆盖，`spec.md` 未同步。** 按项目记忆「人写文档是最终权威」，用户那侧胜；但 `spec.md` 仍标 `FINALIZED`，任何按 `spec.md` 做验收的人会得到相反答案。

**我的判断（权重：可据以行动，依据是两处文本正面相反且日期可查）**：这不是布局问题，也不该由布局提案裁决；它是一条**需要用户裁决的文档冲突**，应当与 9.1／9.2 并列为第三个分叉，或单独提出。

### 5.4 顺带登记的第二处同类冲突（不影响本提案，但同一形态）

`spec.md` 多处仍以「全局内存预算／global resident bytes」为冻结前提（`:23`、`:314`、`:454`、`:457-463`、`:499`、`:504`、`:530`、`:537`），而这一整套已被 2026-08-19 用户重裁删除，代之以等待式在途请求上限——`architecture.md:550` 与 `:664` 都记了这次覆盖（「全局内存预算整体删除——`src/app/delivery/reservation.py` 及 `openai_responses.global_resident_bytes`／`request_resident_bytes` 随 `546852a` 移除」）。**`spec.md` 同样未同步。** 与 5.3 是同一形态：`spec.md` 作为 oracle 已有两处过期条款。

---

## 6. 给主会话的处置建议（不改提案，只列）

1. **F2 保留 blocker，但换依据**：删掉「Downstream sink 是唯一 body writer」那条腿（1.1），补上 `spec.md:389/424/448` 与 `implementation.md:268`（1.2）。
2. **F2 的替代落点要改理由**：`server/accounting.py` 与 `architecture.md:528` 的目标处置矛盾；文档指向 `pipeline/delivery/`。最省事的做法是本轮第 3 步只搬纯发射的那几块，所有权三件套原地不动（1.4）。
3. **S4 换引证**：从「违反边界 2」改为「与 `architecture.md:528` 已登记怪味的目标处置不一致」。级别下降，依据变硬，同时回应事实核查 A2（4）。
4. **第 2 节的行动分界线要按第 3 节重画**：六步里只有第 1 步就 `spec.md` 而言是干净的（3）。
5. **新增第三个用户分叉：响应头提交时点**。`spec.md:285/348` 与 `docs/.human-controlled/client-side-block-delivery.md` 正面冲突，`spec.md` 未同步 2026-08-22 的用户裁决；F15 的成立与否取决于它（5.3）。
6. **登记（不在本次做）**：`spec.md` 至少有两处过期条款（响应头时点、全局内存预算），`architecture.md` 的怪味登记有 5/7 行钉在提案判定不可达的模块上。

**我不提议加任何门、CI 检查或校验框架**，本报告不含此类建议。

---

## 7. 能力边界与方法学声明

- **全程只读**。未修改任何仓库文件，未 stage、未 commit、未 push，未触碰 `docs/.human-controlled/`。唯一写入是本报告。
- **未跑任何测试、未跑 ruff／pyright、未试搬任何文件**。本报告不提供「搬完还能编译」的任何证据。
- **行号口径**：`architecture.md`、`spec.md`、`implementation.md` 的行号取自当前工作树（`.dev` 仓）；代码行号取自当前主树工作树，**不是提案基线 `1f29d0a`**。主树有同伴并行改动，`pipeline_app.py` 的行号可能与事实核查报告的 `1f29d0a` 快照相差若干行；我引用的每一处都同时给了函数名或原文片段，可据以重新定位。
- **本报告只回答「这些文档怎么说」**，未重新设计布局，未评估提案第 5 节目标树的设计优劣。
- **第 5.3 节的冲突判定**依据是两段文本正面相反加 `git log` 可查的日期（`fa0b281`，2026-08-22，晚于 `spec.md` 2026-08-07 冻结），**不依赖**任何运行时观察；我未探测任何端口、未启动任何服务。
- **未核查两位评审报告的其余发现**（F1、F3–F15 除 F2 外的部分），只在它们与我的读程直接相撞时提及（F13、F15）。

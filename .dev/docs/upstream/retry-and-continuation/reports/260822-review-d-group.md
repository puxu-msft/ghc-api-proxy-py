# D 组独立评审（`361a7b9` … `8f654b4`）

**日期**：2026-08-22。**评审对象**：主仓八条提交 `361a7b9`、`0b57645`、`a2c9b77`、`96eb2fa`、`9aa31f9`、`a68672c`、`51196e2`、`8f654b4`（区间内的 web-search 与 docs 提交不在范围内）。**评审基准**：`docs/.human-controlled/upstream-retry-and-continuation.md`、`docs/.human-controlled/client-side-block-delivery.md`、`.dev/docs/upstream/retry-and-continuation/decisions.md`。

**结论：needs-fix。** 1 blocker、7 major、7 minor。blocker 落在主产品路径（Anthropic Messages 入、Responses 上游）上，且**当前测试集结构性看不见它**——唯一的端到端重放测试走的是不需要翻译的那条腿。

**判据说明**：本文所有「实测」都由一次性探针取得，探针源码存在 `260822-review-d-group-probes/`（一次性资产，非仓库测试）。运行方式：`cd /home/xp/src/ghc-api-proxy-py && uv run pytest .dev/docs/upstream/retry-and-continuation/reports/260822-review-d-group-probes/<file> -c pyproject.toml -p no:cacheprovider -q -s`。评审期间对生产代码只做过四次受控变异，全部按 sha256 逐字节还原并用 `git status`/`git diff` 复核（见第四节）。

---

## 一、Blocker

### B1 主产品路径上，重放把整段对话丢了

**位置**：`src/app/server/pipeline_app.py:533`（`again = await handle(chain, context, _routed)`），与 `src/app/server/handler.py:108`（`apply_route`，在 `shape_request` 内）、`handler.py:150`（`context.payload = translated`）联合致错。

**为什么错**：`handle()` 对同一个 `RequestContext` **不是幂等的**。第一次调用会把 `context.payload` 就地换成翻译后的 Responses body（`handler.py:150`），并再写 `context.payload["model"]`。`_reopen` 拿同一个 `context` 第二次进 `handle`，`decide_route` 依旧算出 `translation_required=True`（`routing.py:107`，`inbound_format` 取自 context，从未变过），于是 `chain.translators.translate(context.payload, source=anthropic-messages, …)` **对一个已经是 Responses 形状、根本没有 `messages` 的 body 再翻译一次**。

**实测**（`test_replay_translated.py`，模型 `gpt-model`，第一次上游 200 后 body 撕裂）：

| | 发往上游的 body |
|---|---|
| 第 1 次 | `{"model":"gpt-model","input":[{"type":"message","role":"user","content":[{"type":"input_text","text":"hi"}]}],"stream":true}` |
| 第 2 次 | `{"model":"gpt-model","input":[],"stream":true}` |

客户端拿到的是 **HTTP 200 + 一条格式完全正确的回答**，而那条回答是模型对**空 prompt** 生成的。8f654b4 的设计目标「the client cannot tell there were two」在这里正好是危害的放大器：没有任何一侧会报错。

**为什么全绿**：唯一的接线测试 `tests/int/test_pipeline_app.py:2604` 用 `claude-model`，而 fixture catalog（`tests/int/test_pipeline_app.py:55`）把它登记在 `/v1/messages` 上，`translation_required=False`，第二次翻译根本不会跑。**测试选的那条腿恰好绕开了本项目声明的主产品路径。**

**建议怎么改**：让每次 attempt 从未翻译的起点出发。两条可选路线——
1. 在 `build_context` 时把入站 payload 快照存在 `RequestContext` 上，`_reopen` 进 `handle` 前恢复它；
2. 把 `handle` 拆成「shape + translate 一次」与「send（可重复）」两半，`_reopen` 只调后半。

无论走哪条，**必须补一条 `gpt-model` 的端到端重放测试**，并断言两次上游 body 逐字节相同——这正是 `test_replay_translated.py` 的断言。

---

## 二、Major

### M1 重放之后 `client_request_deadline` 不再罩住 body

**位置**：`src/app/server/pipeline_app.py:571`（`with_client_deadline_at` 只包住第一次的 `response.aiter_bytes()`）vs `src/app/pipeline/delivery/stream.py:297`（`chunks, assembler, buffer = replacement`）vs `pipeline_app.py:525-559`（`_reopen` 只用 `with_idle_timeout` + `with_deadline_at` + `_counted_upstream`）。

**为什么错**：`_deliver` 重放时把 `chunks` 整个换掉，外层那个客户端时限守卫随第一条迭代器一起被丢弃。这与三处自述直接相违背：`deadline.py:73`「Bound the whole client request, **across every attempt it takes**」、`deadline.py:5`「bounds *this client request*, across however many attempts it takes」、`pipeline_app.py:571` 的注释「Outermost of the guards, because it is the longest-lived」。

**实测**（`test_deadline_after_replay.py`）：`client_request_deadline=2`，第一次撕裂触发重放，第二条 body 跑满 **6.1 秒**才完整交付。**正样本对照**（`test_control_and_frame_gate.py::test_control_the_client_deadline_does_bound_a_first_attempt`）：同一条慢 body、不撕裂、只有一次 attempt 时，在 **2.01 秒**被切断并发出 `client_deadline_exceeded` 帧。所以这不是探针失灵，是守卫真的没了。

**建议怎么改**：把 `client_deadline_at` 交给 `ReplaySupport`（或直接闭包捕获），让 `_reopen` 在自己那条链的最外层重新套一次 `with_client_deadline_at`。更彻底的做法是把它移进 `_deliver`，每轮 attempt 各套一次——它本来就该是 per-request 而非 per-iterator 的属性。

### M2 「delivery 先答，所以 eligible 看不到客户端时限」是有条件的，写成了无条件

**位置**：`src/app/server/pipeline_app.py:518`（`_replay_reason` docstring：「The client deadline is deliberately absent: delivery answers that one before it ever asks」）vs `src/app/pipeline/delivery/stream.py:269`（`if isinstance(torn, ClientDeadlineError) and client_has_bytes.is_set():`）。

**为什么错**：那个分支带 `and client_has_bytes.is_set()`。而 `client_has_bytes` 为假的窗口恰恰是**重放合法的那个窗口**——`policy: full` / `until-tool-use` 下是整整一轮，`policy: block` 下是第一个完整块之前。此时 `ClientDeadlineError` 会一路落到 `replay.eligible(torn)`。

今天没出事，靠的是 `normalize_upstream_error`（`ghc_client/errors.py:99-135`）对一个它不认识的类型返回 `None`——**这是巧合，不是设计**。`ClientDeadlineError` 与 `StreamDeadlineError`、`StreamIdleTimeoutError` 是同一个 `TimeoutError` 家族的兄弟，而后两者就写在 `_replay_reason` 第一行的 `isinstance` 元组里；谁哪天顺手把它加进去，或者换一个 `eligible` 实现，一个已经超时的请求就会被重开。

**建议怎么改**：把保证做成结构性的，二选一——把 `ClientDeadlineError` 检查提到 `client_has_bytes` 判断之上（与 M3 的修法合流），或在 `_replay_reason` 里显式 `if isinstance(error, ClientDeadlineError): return None` 并写明理由。同时把 docstring 改成有条件的表述。

### M3 第一个块之前的客户端时限，一个字节都不发——与人写文档相违背

**位置**：`src/app/pipeline/delivery/stream.py:269` 的门 `client_has_bytes.is_set()`。

**权威文档怎么说**：`client-side-block-delivery.md:19`——「当客户端请求超时，**如果已发 HTTP 200 响应头**，则放弃当前缓冲块，发 SSE error 再收尾；如果还没发 HTTP 200 响应头，则直接返回 HTTP 408。」判据是**响应头**，不是「交付过块」。

而 a2c9b77 自己确立（我另行复核过，见第三节第 8 条）：200 响应头在 delivery 拉第一个 chunk 之前就已经在线上了。所以只要这个分支能被执行到，文档的条件就**永远**已经满足。实现却用 `client_has_bytes` 又收窄了一次。

**实测**（`test_control_and_frame_gate.py::test_probe3_full_policy_client_deadline_gets_no_frame`）：`policy="full"`，时限中途触发 → 交付 **0 字节**，`ClientDeadlineError` 上抛截断连接。客户端拿到 200 + 空 body，与「上游什么都没产出」逐字节同形——正是 `deferred.md` 8d 登记的那类不可分辨。对照组（`policy="block"`、已交付一块）则正常发出 `client_deadline_exceeded` 帧。

**建议怎么改**：去掉 `and client_has_bytes.is_set()`。单发一个 `error` 事件不需要先有 `message_start`，SSE 上完全合法，也不会被误读成 turn 的一部分。若确实要保留这个收窄（例如为了与 `stream.py:310-312` 那条既有约定一致），那是**一次新的产品裁决**，应交用户裁定并记进 `decisions.md`，不能由实现自己收窄。

### M4 客户端时限在响应头之前触发时返回 504，文档写的是 408

**位置**：`src/app/server/handler.py:351`（`raise UpstreamTimeout(f"client request exceeded {deadline}s")`）→ `handler.py:386-387`（`error_status` 里 `UpstreamTimeout` → 504）。

**权威文档怎么说**：`client-side-block-delivery.md:19` 后半句——「如果还没发 HTTP 200 响应头，则直接返回 **HTTP 408**」。

a68672c 正是把这条路径从 502 修到 504 的提交，它的提交信息也明确写「told 502 … rather than 504」。也就是说 504 是**这次有意选定的值**，而文档要求 408。二者只能有一个成立。

**建议怎么改**：不要直接改代码。这是产品语义分歧（408 = 客户端太慢，504 = 网关上游超时），应把两种取值的含义摆给用户裁决，裁完记进 `decisions.md`。在此之前不要把 504 当成已裁决状态写进 `status.md`。

### M5 重放之后请求行少报 attempt 数，唯一能暴露静默重放的观测面失效

**位置**：`src/app/server/pipeline_app.py:474`（`trace.attempts = context.attempt_count`，在流式分支之前一次性设定）、`pipeline_app.py:471`（`active.set_attempts`）；`_StreamAccounting.finish()`（`pipeline_app.py:635` 起）持有 `self.context` 却从不刷新它；`src/app/observability/request_log.py:380-382` 仅在 `attempts > 1` 时打印 `retries=`。

**实测**：B1 探针那次请求上游被问了两次，完成行是 `H1/H1 200 anthropic-messages/gpt-model 7ms ↑124B ↓690B ↑1 ↓1 end_turn`——**没有 `retries=`**。

**为什么要紧**：`decisions.md` 第二节第 7 条把「本次上游尝试算失败要在请求行看得出来」定为裁决内容；D 组新造的这条静默重放路径恰好绕过了它。客户端看不出来是设计，运维也看不出来就是缺陷。

顺带同样没刷新的还有 `trace.absorb_losses(context)`（第二次翻译的 losses 不进记录）。

**建议怎么改**：在 `_reopen` 成功返回前刷新 `trace.attempts` 与 `active.set_attempts`，或在 `_StreamAccounting.finish()` 里从 `self.context.attempt_count` 重读。

### M6 51196e2 只修好了两段生命周期中的一段，`handle_bounded` 的 docstring 现在是假话

**位置**：`src/app/server/pipeline_app.py:362-364` 计算的 `client_deadline_at`，**全仓只有一处引用**（`pipeline_app.py:587`），而它在 `if context.stream:` 分支内部。

**推论**：
- 流式请求的**响应头之前那一段**，仍然只被 `handle_bounded` 的 `asyncio.timeout(deadline)`（`handler.py:344-348`）约束，而那个时钟在 routing 交接时才起跑；
- **非流式请求完全没被这次改动碰到**——body 读取、JSON 解析、准入排队照旧在唯一那个时钟之外，也就是 `deferred.md` 8b 点名要修的那三样。

`handler.py:341` 至今写着「Measured from admission and never reset by a retry」，而 `pipeline_app.py:359` 两个文件之外明确写着这句不成立（「`handle_bounded` starts its own clock later, when routing hands it the request, so the two do not agree on when the request began」）。同一仓库里两处自述互相打脸。

净效果是一条请求现在有**两个各自完整时长、起点不同的客户端时钟**，最坏情形约为「准入耗时 + deadline」。

51196e2 的提交信息把这写成了完成态（「It is fixed at the top of dispatch now」），`status.md:88` 的行文「客户端时限真正罩住 body」倒是准确的——**提交信息比活文档更宽**。

**建议怎么改**：把 `client_deadline_at` 也传给 `handle_bounded`（改用 `asyncio.timeout_at`），一个瞬时点罩住全程；若暂不做，至少改掉 `handler.py:341` 的 docstring，并在 `status.md` / `deferred.md` 8b 里写清「只闭合了 body 段」。

### M7 新行为的测试覆盖有系统性缺口

以下每一条都是本次新增、**没有任何测试**的行为：

| 未覆盖的新行为 | 后果 |
|---|---|
| 翻译腿上的重放 | **B1 因此没被发现** |
| `_replay_reason` 的 `StreamIdleTimeoutError \| StreamDeadlineError` 分支 | 全部三条 delivery 单测与那条端到端测试都只用 `ConnectionError`；这条分支从未被执行过（我用 `test_release_before_reopen.py` 补了第一次，行为正确） |
| 重放之后客户端时限是否还在 | **M1 因此没被发现** |
| `full` / `until-tool-use` 下的客户端时限 | **M3 因此没被发现** |
| 重放之后请求行的 attempt 数 | **M5 因此没被发现** |
| `_reopen` 返回 `None` 的两条分支 | 无 |
| `_replay_reason` / `_reopen` 本身 | `rg '_replay_reason\|_reopen' tests/` 零命中 |

**这不是「覆盖率不够」的问题**，是四个 major 与一个 blocker 全部落在同一片盲区里：接线层（`pipeline_app.py` 里那两个闭包）只有一条端到端测试，而那条测试选的参数恰好让翻译、客户端时限、非 `ConnectionError` 的触发源三样同时失效。

**建议怎么改**：优先补三条——`gpt-model` 的端到端重放（钉两次 body 相同）、重放后客户端时限仍生效、`policy: full` 下时限触发有 error 帧。其余按修复顺手补。**不要建新的验证框架**，这几条都是既有 `make_client` fixture 一把就能写的。

---

## 三、Minor

- **m1 `_reopen` 把第二次失败整个吞掉**（`pipeline_app.py:532-537`）：`except Exception: return None`，无日志、不写 `trace.detail`、不调 `capture_rejection`。`handle` 正常返回但 `outcome.response is None`（driver abort）的那条路同样静默。运维问「重放为什么没成」时手上什么都没有。建议至少补一条 `logger.debug`，把 error 的 `repr` 记下来。
- **m2 `_reopen` 可能丢弃一个已建立的响应而不关闭它**（`pipeline_app.py:538-539`）：`if reopened is None or not again.context.stream: return None`。第二个析取项今天不可达（`context` 是同一个对象，`stream` 不会变），但一旦触发就是泄漏，形态与 `deferred.md` 8g 登记的那条完全一样。建议要么在该分支 `await reopened.aclose()`，要么删掉这个不可达条件并写明为什么它不可达。
- **m3 a68672c 新增了一处「丢弃活响应而不 `aclose`」**（`base.py:173-176`：`outcome.response = None; raise`）。不是回归（原来的 `except BaseException` 也这么做），但它是 `deferred.md` 8g 那条潜伏泄漏的新实例，应计入该条目而不是无声增加。
- **m4 `_ledger_for` 跨模块私有导入**（`pipeline_app.py:47`，从 `handler.py:130` 导入，带 `# pyright: ignore[reportPrivateUsage]`）。前导下划线现在表达的意思与事实相反。建议改名为 `ledger_for` 正式导出。
- **m5 9aa31f9 的提交信息说 `decide_stream_ending` 那条保留分支「now says why it is unreachable」，但代码里没说。** 解释落在了测试 docstring（`tests/unit/pipeline/test_stream_ending.py:60-64`，那段写得很好，条件也标得准确），`src/app/pipeline/retry.py:144-149` 的注释只说了两条 ABANDON 为什么要分开，没说这条到不了。只读代码的人找不到那句话。建议把那句话复述进代码注释。
- **m6 `.dev` 里的残留自相矛盾**（三处，都由这次改动造成）：
  - `decisions.md:69`（第四节「尚待裁决」第 2 条）仍在问 `streamReplay` 要不要独立预算，而同一份文件 `decisions.md:56`（第 15 条）已记下 2026-08-22 的裁决是删除。同一文件两个答案。
  - `deferred.md` 第 7 条仍写「`streamReplay.max_retries`（默认 100）在 D 组接线后会生效」——9aa31f9 已把它删了。
  - `status.md:27` 仍把 `streamReplay` 列在死配置项里。
- **m7 `tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses` 当前是红的，两个错误归属不同**：
  - `upstream_request_retry.strategies.streamReplay` 是 D 组的（9aa31f9 的提交信息已认领）；
  - `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags` **不是**——它随同伴那份**已暂存但未提交**的 `docs/.human-controlled/config.example.yaml` 一起进来。
  
  另需更正 9aa31f9 提交信息的一个细节：该文件在 HEAD 里根本不存在（`git cat-file -e HEAD:docs/.human-controlled/config.example.yaml` 失败），所以在**提交态**下这条测试是 `skip` 而不是「stays red」。只有在同伴那份暂存生效的当前工作树里才是红的。两条都要用户改自己的文件，但第二条不该记在 D 组账上。

---

## 四、变异抽查（4 处，全部转红，全部逐字节还原）

主会话声称「每一处新行为都做过变异检验，且还原后逐字节校验」（`status.md:91`）。抽查四处，**该项自述属实**：

| # | 变异 | 位置 | 结果 |
|---|---|---|---|
| M1 | `if verdict.ending is not StreamEnding.REPLAY:` → `if False:`（无视位置判据） | `stream.py:291` | `test_a_stream_the_client_already_saw_is_not_replaced` 红（DID NOT RAISE），其余 39 绿 |
| M2 | 整段删除 `ClientDeadlineError` 分支（1339 字符） | `stream.py:269-280` | `test_the_client_deadline_is_the_one_ending_that_says_so` 红，其余 39 绿 |
| M3 | 删除两个 `except asyncio.CancelledError: raise` 守卫 | `base.py:142-144,173-176` | `test_a_cancellation_passes_through_rather_than_being_answered` 红（DID NOT RAISE TimeoutError），其余 21 绿 |
| M4 | 删除 `replay=replay,` 一行 | `pipeline_app.py:594` | `test_a_torn_stream_the_client_never_saw_is_replayed_end_to_end` 红（`RemoteProtocolError` 逃逸），其余 93 deselected |

**还原核对**（`sha256sum` 逐字节 + `git status --porcelain src tests` + `git diff --stat src tests` 双重确认）：

```
441fa0a0d38467e3d12aaaf59cfb60824a82598fe803dbe900d9c2eb348ea0ec  src/app/pipeline/delivery/stream.py
7cad0ed331e3d808330e0b1cff81af48e2c03b15b5c8d6c68a435f2231f56c22  src/app/pipeline/direct_driver/base.py
839a3fda42df283510e339713c6dad315195d9773396934a1e9bcdc2942dfea8  src/app/server/pipeline_app.py
```

三者与变异前一致，`git status` / `git diff` 对 `src`、`tests` 均为空。变异期间 `src`、`tests` 相对 HEAD 是干净的（无同伴未提交改动），所以变异结果的归属没有歧义。

**但要说清变异检验证明了什么、没证明什么**：四次变异各自证明了「这条测试确实钉住了它声称钉住的那一处实现」。它**不能**证明测试集覆盖了新增的行为面——M7 那七条恰恰是「没有测试可以被打红」的位置。主会话那句自述的范围应当收窄为「每一处**有测试的**新行为都做过变异检验」。

---

## 五、查过且没问题的方面（判据一并列出）

**空清单免检是本项目明令禁止的，所以这一节写明查了什么、用什么判据查的。**

1. **重放的状态重置是彻底的。** `stream.py:297-298` 同时替换 `chunks` / `assembler` / `buffer`，并新建 `DeliverySession`。`client_has_bytes` 有意**不**重置，这是对的——它为假才是重放合法的前提，重置它反而会掩盖状态。判据：逐个追 `_deliver` 局部变量的写入点。
2. **`decide_stream_ending` 的位置判据在 `full` 与 `until-tool-use` 下仍然成立。** `DeliverySession.committed_count` 数的是**已释放**的块（`blocks.py:140-142` 与 `_commit` 的 `self.delivered.extend(blocks)`，`blocks.py:151-156`），而 `BlockBuffer.add` 在 `full` 下恒返回 `()`、在 `until-tool-use` 下直到出现 tool 块才返回（`blocks.py:98-108`）。所以那两种策略下整轮 `committed_count == 0`、`downstream_opened == False`，判据读到的是「没交付过」而不是「没装配过」——`status.md:19` 警告的高估已经消失。探针 `test_probe3_*` 的 0 字节输出是正样本旁证。唯一可能偏差的方向是**保守方向**：`session.offer` 在帧真正 `yield` 之前就记账，中途中断会多算，结果是拒绝重放而非误放。
3. **重放后 `_StreamAccounting` 读到的 terminal 是当前那个。** `accounting.assembler = fresh_assembler`（`pipeline_app.py:543`）只在成功返回替换件的路径上赋值，且在 `return` 之前；`_deliver` 在 `replacement is not None` 时无条件采用它。两者之间没有不一致的窗口。
4. **预算不会重复扣也不会漏扣。** 一条客户端请求一个 `RetryLedger`（`request.py:85`、`handler.py:130-136`），driver 的 `LedgerBudget` 与 delivery 的 `decide_stream_ending` 共用同一个对象；`retry.py:139` 的 `ledger.take` 是唯一扣费点，每次授予重放恰好扣一次，且发生在 `reopen()` 之前。`reopen()` 返回 `None` 时那一次扣费被浪费——保守方向，且仍受 `max_total` 总闸约束。
5. **`except Exception`（而非 `BaseException`）确实把本侧结束排除干净了。** `stream.py:264`：`CancelledError` 与 `GeneratorExit` 在本 Python 上都直接继承 `BaseException`，所以「客户端已断开」与「优雅关闭」都到不了重放判定——正是人写文档第 7 行与第 25 行要求的。同时核对了另外两类：`BufferCapExceeded` 是 `DeliveryError(RuntimeError)`（`blocks.py:19-23`），`normalize_upstream_error` 对它返回 `None`，所以「代理保护机制触发」不会被重放；`UpstreamRejected` 被有意排除在 `_RETRYABLE` 之外（`exceptions.py:60-64`、`exceptions.py:110`），所以 400 类拒绝也不会被重放。
6. **重放时旧的上游响应确实先被释放了。** `async with aclosing(_events_with_ping(...))` 位于 `try` 内部（`stream.py:234-240`），异常先过 `__aexit__` 再到 `except`。**实测**（`test_release_before_reopen.py`，用 idle 超时而非撕裂，这样第一条上游是健康的、才有得泄漏）：第二个上游请求到达时，第一个 `httpx2.Response.is_closed` 已经是 `True`。关闭链本身也核对过：`httpx2.Response.aiter_raw` 的 `finally` 里既 `await stream.aclose()` 又 `await self.aclose()`，`read_events`（`sse_source.py:73` 取 `aclose`、`:85-87` 的 `finally` 调用它）显式关闭它的源。
7. **两个 deadline 嵌套后内层不会被外层改名。** `_bounded` 只在 `bound.expired()` 为真时替换异常，否则原样 `raise`（`deadline.py:50-54`）。正样本对照里外层（客户端 2 秒）先到期、内层（attempt 60 秒）没到期，出来的帧是 `client_deadline_exceeded`，名字正确。
8. **a2c9b77 的 starlette 论断成立，而且我比该提交多验了一层。** `starlette 1.6.0` 的 `StreamingResponse.stream_response` 在 `async for` 之前就 `await send({"type": "http.response.start", ...})`；再往下 `uvicorn 0.52.4` 的 h11 `RequestResponseCycle.send` 在收到该消息时立即 `self.transport.write(output)` 把状态行与响应头写上传输层（本环境未安装 `httptools`，所以 h11 就是实际路径）。因此「客户端在 delivery 跑起来时已经握有 200」是真的，无条件发 keep-alive 注释是安全的，0b57645 里那段被推翻的推理也确实被 a2c9b77 正确撤回——**这是本区间里做得最好的一处：错误结论被后一条提交点名更正，而不是悄悄改掉。**
9. **361a7b9 与人写文档第 27 行一致。** `PipelineAbort.cause`（`exceptions.py:98-107`）让 `error_status` / `error_headers` / `error_body`（`handler.py:354`、`:395`、`:411` 三处开头的读穿分支）读穿预算耗尽，429 与 `Retry-After`、504 都能到达客户端。
10. **`max_tokens` 的处置正确（结构性而非靠分支）。** 它以终止事件形式到达，`terminal_seen` 为真时 `decide_stream_ending` 直接 COMPLETE（`retry.py:134-135`），根本进不了重放。人写文档第 23 行「`max_tokens` 不应无痕重试」由结构保证。E 组的合成尚未落地，符合路线。
11. **孤儿与残留已清干净，也没造出新的孤儿。** 全仓 `rg 'streamReplay|stream_replay'` 与 `rg 'synthesized_response_headers'` **零命中**（`config.example.yaml` 那两行是用户自己的文件，见 m7）。`continuation` 的剩余命中全部是关于**已放弃设计**的散文，加上 reasoning carrier 里同名不同义的词汇。新增件 `ReplaySupport`、`_replay_reason`、`_reopen`、`with_client_deadline_at`、`ClientDeadlineError`、`RequestContext.retry_ledger` 各有且仅有一个生产调用点，8f654b4 全部接线。
12. **门与工具链。** `uv run ruff check src tests` 全绿。`uv run pytest tests/unit tests/int` → **1568 passed, 1 failed**，唯一那条就是 m7。`uv run pyright src tests` → 21 errors，**全部**落在 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`，由 `2b20be7` / `2924a8c`（httpx2 迁移）引入，不在本评审区间内——按 `git log --oneline 361a7b9^..8f654b4 -- <那两个文件>` 为空确认。

**明确没查的**：反应式限流器在 429 上是否真的先等待而非立即重试（D 组未触碰该逻辑，人写文档第 27 行前半句的实现属既有面）；`tests/systemd` 与 `tests/e2e`（前者的超时失败已由主会话用 stash 对照证明与本次无关，后者被 `addopts` 排除）。

---

## 六、给主会话的建议顺序

1. **先修 B1**，并补 `gpt-model` 端到端重放测试——在它修好之前，重放接线不应留在 main 上生效；这是唯一一条会给客户端**错误答案**的缺陷。
2. M1 与 M2 一起修（同一处接缝，改法互相咬合）。
3. M3 与 M4 一起交用户裁决（都是与 `client-side-block-delivery.md:19` 的分歧，且是同一句话的两半）。
4. M5、M6、m1～m5 属实现与自述修正，可并入一次提交。
5. m6、m7 是文档与用户文件，按项目惯例处理。

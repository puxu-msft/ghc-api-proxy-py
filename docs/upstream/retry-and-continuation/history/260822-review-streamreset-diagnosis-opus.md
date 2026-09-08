# 对《上游流级 RST_STREAM(CANCEL) 打掉在飞请求》诊断的独立证伪评审

**日期**：2026-08-22
**评审对象**：`.dev/docs/tmp/260822-h2-streamreset-cancel-diagnosis.md`
**评审者本机状态**：`HEAD = 8f654b4`。**评审开始时 `git status --porcelain -- src` 为空；评审进行中一个并行会话改脏了 `src/`**（详见 §0.1）。本报告内所有行号一律锚定 `git show HEAD:<path>`，不是工作树。
**方法**：不接受被评审报告的任何实测转述，逐条重跑；对 §2.2 §2.3 §2.4 三条用**端到端执行整条交付生成器**替代该报告的孤立函数调用；对版本判定用**在 `9aa31f9` 源码树上真跑一遍并读 traceback**替代行号算术。
**探针位置**：`/tmp/rev/`（`probe_e2e.py`、`probe_9aa.py`、`probe_mut.py`、`probe_mut2.py`、`probe_acct.py`、`probe_eof.py`），源码副本 `/tmp/rev/src9`（`git archive 9aa31f9`）、`/tmp/rev/srcH_brk`、`/tmp/rev/srcH_ret`（`git archive HEAD` 后各改一行）。**仓库工作树与索引全程未被本次评审改动**。

**技能偏差声明**：任务要求先调用 `my-skills:as-reviewer`，该技能在本机技能目录中不存在（`ls /home/xp/.claude/skills/` 无此项，`Skill` 调用返回 `Unknown skill`）。改用最贴近的 `verifying-authoritative-claims`，并按其「先把声称写成有条件命题 → 选与命题对齐的 ground truth」的协议执行。

---

## 0. 结论速览

| # | 被评审报告的论断 | 我的裁定 | 档位 |
|---|---|---|---|
| 1 | 部署的是 `9aa31f9`，依据是行号 | **证实但需收窄**：三个行号我全部复现（含 `keepalive.py:126`），但只能定位到**一个跨 5 个提交的区间**，且第三个行号鉴别力为零 | 足以据此行动 |
| 2 | `9aa31f9` 上 replay 完全未接线 | **证实，且我把它加固到整个区间** | 足以据此行动 |
| 3 | HEAD 上该异常被判为可重放的 `NETWORK` | **证实，但报告漏写了一个承重步骤** | 足以据此行动 |
| 4 | HEAD 上这次仍会 abandon | **结论证实（我端到端跑出来了），证据链证伪**：报告漏掉的前提不是它标注的那一个 | 结论足以据此行动；证据链需重写 |
| 5 | 撕断路径拿不到带内 error 帧 | **证实**，并补上了正样本对照 | 足以据此行动 |
| 6 | 吞掉异常会造成回归 | **证伪**。论证与结论都不成立，且它排除掉的是错的候选 | 足以据此行动 |
| 7 | —— | 报告漏了一条会改变优先级定性的事实（见 F2），另有一条它自己的日志证据被读反（见 F1） | 见各条 |

**Major 4 条**（F1 F2 F3 F4），**Minor 5 条**（f1–f5），**另有 6 条我查证后判定「报告没提但确实没问题」的项**，列在 §8 以免下一位评审重跑。

一句话：**这份诊断的三个行动建议（P0 升级、P1 补帧、P2 消 traceback）方向都对，但 P1/P2 的定性、优先级与代价估计都错了**——它把一个「实现偏离冻结 spec」的缺口写成了「需要用户裁决的对外行为变更」，又用一个不成立的回归论证把两步锁成了顺序依赖，而实际上一个关键字就同时做完两件事。

---

## 0.1 并行会话在本次评审进行中改脏了 `src/`（必读）

评审开始时 `git status --porcelain -- src` 为空。评审结束时：

```
 M src/app/pipeline/delivery/stream.py      (mtime 10:16:30)
 M src/app/server/handler.py
 M src/app/server/pipeline_app.py           (mtime 10:25:16)
 M tests/int/test_pipeline_app.py
 M tests/unit/pipeline/delivery/test_stream_delivery.py
```

**这不是我改的**——我的全部变异都在 `/tmp/rev/` 的 `git archive` 副本上（§11 有自证）。三点必须记下：

**(a) 我一度读到了脏工作树，已修正。** 我用 `sed -n` 读 `handler.py` 时拿到的是同伴改后的版本，行号整体偏移 +19（`dialect_for` 工作树 517 / HEAD 498）。**本报告发布前已把所有引用逐条对 `git show HEAD:` 重核并改正**，唯一例外是 §6.3 里那条运行时 traceback 报出的 `pipeline_app.py:301`——那是探针实际执行的工作树版本的行号，保留原样（改写它会伪造记录）。

**(b) 我的实测读数不受影响。** 同伴对 `stream.py` 的改动只有 4 行，全部落在 `ClientDeadlineError` 分支（269 行的判据从 `isinstance(torn, ClientDeadlineError) and client_has_bytes.is_set()` 改成 `isinstance(torn, ClientDeadlineError)`）。我引用的 241、283/292/295、300、313、320 **行号与内容都没变**，而我的 fixture 抛的是 `RemoteProtocolError`，从不进那条分支。

**(c) 同伴的这处改动独立佐证了我在 §5 末尾单列的那条发现。** 他们的新注释写的是：

> Gating on a delivered block instead meant `full` and `until-tool-use` — which deliver nothing until the stream ends — timed out having sent the client zero bytes and no frame at all.

即「非 `block` 策略下客户端拿到零字节」这个形态已被另一条线独立观察到并在修。**这提高了我那条发现的权重**（从我一次探针的单侧观察，变成两条独立路径的一致观察），也说明本诊断报告 P1 的邻域正在被并行推进——见 §7.2。

---

## 1. 论断 1：部署版本判定 —— **证实，但收窄**

### 1.1 我跑的

行号对照（不是引用报告的命令，是我自己跑的）：

```
$ git -C /home/xp/src/ghc-api-proxy-py show 9aa31f9:src/app/pipeline/delivery/stream.py | rg -n 'async for pull in events|^ *raise torn$'
240:                async for pull in events:
270:            raise torn
279:            raise torn
282:            raise torn

$ git show HEAD:src/app/pipeline/delivery/stream.py | rg -n 'async for pull in events|^ *raise torn$'
241:                async for pull in events:
283:            raise torn
292:            raise torn
295:            raise torn
```

`keepalive.py:126`（用户特别点名的那一条）：

```
$ for c in 9aa31f9 8f654b4; do git show $c:src/app/streaming/keepalive.py | rg -n 'await pending|_cancel_and_observe'; done
# 9aa31f9:  80: pending_error = await _cancel_and_observe(pending)
#          118: async def _cancel_and_observe[T](...)
#          126:         await pending
# 8f654b4:  完全相同，逐行一致
```

**用户预设的证伪条件没有触发**：`keepalive.py:126` 在 `9aa31f9` 上**吻合**，版本判定不因此崩塌。

### 1.2 我做的更强的一步：在 `9aa31f9` 源码树上真跑出这条 traceback

行号算术只能证明「文件里那一行长这样」，证明不了「那条 traceback 会经过这些帧、以这个顺序」。所以我把 `9aa31f9` 的 `src/` 解到 `/tmp/rev/src9`，构造一条「先完成一个加密 reasoning 块、再抛 `httpx2.RemoteProtocolError(<StreamReset stream_id:3, error_code:8, remote_reset:True>)`」的上游流，跑完整条 `stream_delivery`：

```
$ PYTHONPATH=/tmp/rev/src9 uv run --no-sync python /tmp/rev/probe_9aa.py
app package resolved to: /tmp/rev/src9/app/__init__.py      # 证明探针读的是 9aa31f9 的码，不是本机 src/
terminal: blocks=1 thinking=['enc'] seen=False
downstream chunks: 5
raised: httpx2.RemoteProtocolError
  tb: File "/tmp/rev/probe_9aa.py", line 27, in main
  tb: File "<9aa31f9>/app/pipeline/delivery/stream.py", line 206, in stream_delivery
  tb: File "<9aa31f9>/app/pipeline/delivery/stream.py", line 270, in _deliver
  tb: File "<9aa31f9>/app/pipeline/delivery/stream.py", line 240, in _deliver
  tb: File "<9aa31f9>/app/streaming/keepalive.py", line 126, in _cancel_and_observe
```

HEAD 上同一探针（`/tmp/rev/probe_e2e.py`，`replay_wired=False` 那一档）给出 `207 / 283 / 241 / keepalive.py:126`。

**三个被引用的行号全部复现，且顺序、帧集合都对得上。这比报告自己的证据强一档。**

### 1.3 【Major F4】但「部署的是 `9aa31f9`」这句话超出了证据

报告写的是「判据是 traceback 里的三个行号逐一吻合，**不是推测**」。这句「不是推测」不成立，有三处：

**(a) 行号定位到的是内容区间，不是提交。** 我枚举了所有触碰 `stream.py` 的提交：

```
51196e2  events=241  firstTorn=283
9aa31f9  events=240  firstTorn=270   <-- 唯一命中
96eb2fa  events=240  firstTorn=269
a2c9b77  events=215  firstTorn=none
（更早的都没有 raise torn）
```

`(240, 270)` 在**触碰过 stream.py 的提交里**确实唯一。但 `9aa31f9` 之后到 `51196e2` 之前有四个提交（`767d0f2`、`fa628e1`、`b64003e`、`a68672c`）**根本没碰 `stream.py` 也没碰 `keepalive.py`**，于是它们的 `stream.py` 内容与 `9aa31f9` 逐字节相同。traceback 无法区分这五者。正确的写法是「部署的是 `9aa31f9..a68672c` 这五个提交之一」。

**(b) 「三个行号」这个计数是虚的。** 报告的对照表只有两行；第三个行号 `keepalive.py:126` 在 `9aa31f9` 与 HEAD 上**完全相同**（见 §1.1），鉴别力为零。它证实了「这条 traceback 与我方代码自洽」，但对「是哪个版本」一个 bit 都没提供。把它计入「逐一吻合的三个判据」是把证据数量算多了。

**(c) 还有一个免费的第四判据被漏掉了**：`stream_delivery` 那一帧，`9aa31f9` 是 **206**，HEAD 是 **207**（见 §1.2 两次探针输出）。这一条是真有鉴别力的，报告没用。

**为什么这仍然只降级不推翻**：承重的下游结论是「那台机器上 replay 未接线」，我在整个五提交区间上逐一验过（§2），全部成立。所以 **P0 建议不变**。但报告用「不是推测」为一句实际是区间估计的话背书，这是 `verifying-authoritative-claims` 里典型的「结论强于 oracle」。

**档位：足以据此行动**（升级建议照做；「部署的是 9aa31f9」这句话在写进任何活文档前必须改成区间）。

**另有一条报告与我都无法排除的可能**（记录，不作为行动依据）：那台机器可能跑的根本不是本仓库历史上的任何提交（本地改动、旧安装）。行号只证明「那两个文件的那一段内容与该区间一致」。这条属于**仅存档**档位，不足以推翻任何东西。

---

## 2. 论断 2：`9aa31f9` 上 replay 未接线 —— **证实，且加固**

报告只验了 `9aa31f9` 一个点。我按 §1.3(a) 的区间把它验满：

```
$ for c in 9aa31f9 767d0f2 fa628e1 b64003e a68672c 51196e2 8f654b4; do
    n=$(git show $c:src/app/server/pipeline_app.py | rg -c 'replay' || true); printf "%-9s replay-hits=%s\n" "$c" "${n:-0}"; done
9aa31f9   replay-hits=0
767d0f2   replay-hits=0
fa628e1   replay-hits=0
b64003e   replay-hits=0
a68672c   replay-hits=0
51196e2   replay-hits=0
8f654b4   replay-hits=5
```

注意我用的是 `rg -c 'replay'`（整个词，任意上下文）而不是报告的 `rg 'replay='`——后者只查关键字实参形式，一个 `**kwargs` 或换行传参就能骗过它。用更宽的模式仍然是 0，所以报告的结论比它自己的命令能支持的更稳。

并且我在 §1.2 的探针里直接观察到了行为后果：`9aa31f9` 树上 `stream_delivery` 的签名根本没有 `replay` 形参可传，撕断直接从 line 270 抛出，`reopen` 从未被咨询。

**证实。档位：足以据此行动。**

---

## 3. 论断 3：HEAD 上该异常被判为 `RetryReason.NETWORK` —— **证实，但报告漏写了一个承重步骤**

我自己跑的（注意：本项目用的是 `httpx2` / `httpcore2` 这两个 fork，不是 `httpx` / `httpcore`）：

```
$ PYTHONPATH=src uv run python /tmp/rev/probe_claim34.py
=== raw: httpx2.RemoteProtocolError | <StreamReset stream_id:3, error_code:8, remote_reset:True>
  normalized: UpstreamError | upstream connection failed: <StreamReset ...>
  reason_for(raw): None
  reason_for(normalized): network
=== raw: httpcore2.RemoteProtocolError | <StreamReset stream_id:3, error_code:8, remote_reset:True>
  normalized: NoneType | None
  reason_for(raw): None
  reason_for(normalized): N/A
```

**报告的结论复现了。但注意第二组输出**：`normalize_upstream_error(httpcore2.RemoteProtocolError(...))` 返回 **`None`**，因为 `errors.py:44` 的 `_CONNECTION_ERRORS` 只收 `httpx2.TransportError`，不收 `httpcore2` 的任何类型。

### 【Minor f5】报告 §1.1 引的是 `httpcore2.RemoteProtocolError`，§5 测的是 `httpx2.RemoteProtocolError`，中间的映射步骤没写

这一步是承重的：换成 `httpcore2` 那一侧，结论从「NETWORK，可重放」翻成「不是已知上游失败，`raise torn`」——正好相反。

我补上了这一步的证据。`httpx2/_transports/default.py`：

```python
class AsyncResponseStream(AsyncByteStream):
    async def __aiter__(self):
        with map_httpcore_exceptions():          # HTTPCORE_EXC_MAP: httpcore2.RemoteProtocolError -> httpx2.RemoteProtocolError
            async for part in self._httpcore_stream:
                yield part
```

而生产链路上 `chunks` 的源头是 `response.aiter_bytes()`，`response` 的声明类型是 `httpx2.Response`（`src/app/pipeline/executor.py:42`）。所以读体时抛出的 `httpcore2.RemoteProtocolError` 在离开 transport 层时就被 `raise mapped_exc(message) from exc` 换成了 `httpx2.RemoteProtocolError`，`httpcore2` 的那一条只作为 `__cause__` 留在链式 traceback 的最上方——**这正是报告只看到那一行的原因**，也解释了为什么它测 `httpx2` 是对的。

**证实。档位：足以据此行动。** 但报告把一个能翻转结论的步骤留成了默会知识，在活文档里必须补上。

---

## 4. 论断 4：HEAD 上仍会 abandon —— **结论证实，证据链证伪**

### 4.1 我不用它的方法，我端到端跑

报告的做法是孤立调用 `decide_stream_ending(downstream_opened=True, committed_blocks=1, ...)`，然后用一段文字论证「这次属于第二行」。这段文字正是要被攻击的地方，所以我不复用它——我把整条 `stream_delivery` 跑起来，让代码自己回答 `downstream_opened` 和 `committed_blocks` 是多少（`/tmp/rev/probe_e2e.py`）：

```
ClientDeliveryConfig defaults: {'client_request_deadline': 3600, 'buffering_policy': 'block',
                                'buffer_cap_bytes': 16777216, 'sse_ping_interval': 15, ...}

--- policy=block  replay_wired=True ---
  assembler terminal: blocks=1 thinking=['enc'] seen=False
  downstream chunks: 5   (message_start, content_block_start, 2x delta, content_block_stop)
  reopen called: 0
  raised: httpx2.RemoteProtocolError
     tb: stream.py:207 in stream_delivery
     tb: stream.py:292 in _deliver          <-- `if verdict.ending is not StreamEnding.REPLAY: raise torn`
     tb: stream.py:241 in _deliver
     tb: keepalive.py:126 in _cancel_and_observe

--- policy=full  replay_wired=True ---
  assembler terminal: blocks=1 thinking=['enc'] seen=False
  downstream chunks: 0
  reopen called: 1                          <-- 真的去重开了
  raised: httpx2.RemoteProtocolError
     tb: stream.py:295 in _deliver          <-- `if replacement is None: raise torn`
```

**HEAD 上在 `block` 策略下击中的是 292 行（abandon 分支），`reopen` 一次都没被叫；在 `full` 策略下击中的是 295 行（replay 分支走到了 reopen）。报告的结论和它标注的那个前提，两者都被端到端执行证实了。**

我另外验了 `until-tool-use`（未接线档），与 `full` 同形：0 chunk。

### 4.2 「`think(enc:1)` 到底证明了什么」

**它来自 assembler，不来自交付记录。** 我核了 provenance 全链：

- `Terminal.record(block)` 在 `assembler.py:187`（`AnthropicAssembler`）与 `assembler.py:320`（`ResponsesAssembler`）被调用，都在块**闭合时**、在块被交给 buffer **之前**；
- `_Trace.absorb(reply: Terminal)`（`pipeline_app.py:227-238`）把 `reply.thinking` 整个拷到日志行；
- `format_thinking` 只读这个 tuple。

`session.delivered` / `committed_count`（真正的交付侧事实）**在日志行上没有任何字段**。所以：

> `think(enc:1)` 支持的窄结论是「assembler 完成了 1 个加密 reasoning 块」。它**不支持**「客户端收到了这个块」。桥接这两者的是且只是 buffering policy。

报告的桥接是对的，它也标注了这个前提，并给了正确的判断方法（看那台机器的配置）。**这一点我确认它做对了**，不算缺陷。

### 4.3 我逐一排查了「块闭合但没交付」的其它可能，结论是没有

用户点名要问的「有没有可能块闭合了但没交付」，我查了三条：

- **buffer cap**：`BlockBuffer._enforce_cap` 在 `add` 追加之前检查（`blocks.py:120-126`），超限抛 `BufferCapExceeded`。**但这条能被观测到的异常本身排除掉**：若 cap 击发，被引用的异常就会是 `BufferCapExceeded` 而不是 `RemoteProtocolError`（它同样落进 `except Exception as error: torn = error`，且会先于撕断发生）。默认 cap 是 16 MiB，本次上游只收到 13.1 KB，也够不着。**排除**。
- **`block` 策略下还有别的扣留条件吗**：没有。`BlockBuffer.add` 在 `policy == "block"` 时无条件 `return self._drain()`（`blocks.py:100-101`），`DeliverySession._commit` 随即 `self.delivered.extend(blocks)`。**排除**。
- **`_commit` 返回空导致 `client_has_bytes` 不置位**：只在 `session.offer(block)` 返回空时发生，即 buffer 扣留时。已被上一条覆盖。**排除**。

所以在 `block` 策略下，「块闭合 ⇒ 已交付」是构造性的，报告的推理正确。

### 4.4 【Major F1】但报告漏掉了一个前提，而且它自己的证据把这个前提读反了

**`think(enc:1)` 里的 `think` 这个词，唯一地说明这次请求没有走 Responses 上游。**

链条（三处，全是当前源码，行号锚定 `git show HEAD:`）：

```python
# request_log.py:33
REASONING_WORD = {ReplyDialect.ANTHROPIC: "think", ReplyDialect.RESPONSES: "reason"}

# handler.py:498-510  dialect_for
if handled.route.target_format is WireFormat.OPENAI_RESPONSES:   # :508
    return ReplyDialect.RESPONSES                                 # :509
return ReplyDialect.ANTHROPIC                                     # :510

# handler.py:527-534  assembler_for
if dialect_for(handled) is ReplyDialect.RESPONSES:
    return ResponsesAssembler()                                   # :533
return AnthropicAssembler()                                       # :534
```

`Terminal.dialect` 只在 `ResponsesAssembler.__init__`（`assembler.py:211`）被设成 `RESPONSES`，其余处处默认 `ANTHROPIC`；`_Trace.absorb` 第 238 行原样拷贝。`handled.synthesized` 也返回 ANTHROPIC（`handler.py:505-507`），但一个被撕断的上游流不可能是合成回复。

于是：**`think` ⟺ `target_format is not OPENAI_RESPONSES` ⟺ 用的是 `AnthropicAssembler`。这次事故发生在 Anthropic 腿上，不在项目 CLAUDE.md 所说的「主产品路径」（Anthropic Messages 入 / OpenAI Responses 上游）上。**

报告在 §1.2 引的却是「`assembler.py:320` 的 `self._terminal.record(block)`」——那是 `ResponsesAssembler._close`（该类从 201 行开始）。Anthropic 侧的对应行是 **187**。报告拿着一条写着「不是 Responses」的日志字段，去引 Responses assembler 的行号当证据。

**这条为什么是 Major**：结论层面它不改任何东西（`stream.py` 两条腿共用，交付语义、abandon 判定、error 帧全都一样，我在 §4.1 用 `ResponsesAssembler` 跑出的结果对 `AnthropicAssembler` 同样成立）。但它**改变了「哪份 spec 管这件事」**，而报告的 P1 定性恰恰建立在这个问题上（见 F2）。一份诊断把事故发生在哪条腿都读反了，后面所有「按项目规矩要先有 Spec」的推论都站在流沙上。

**档位：足以据此行动**（证据链必须重写；`assembler.py:320` 必须改成 187，并显式写出这是 Anthropic 腿）。

---

## 5. 论断 5：撕断路径拿不到带内 error 帧 —— **证实**

控制流我读过了：`raise torn` 在 283 / 292 / 295 三处，都在 `while True` 之内；`session.finish()`（300）、`if not terminal.seen: yield error_frame(...)`（313-321）全在循环之后。抛出即跳过。

但「读代码得出的否定结论」需要正样本对照，否则我无法排除是我的探针根本没跑到那一段。所以我加了一组**干净 EOF 无 terminal event** 的对照（`/tmp/rev/probe_eof.py`）：

```
clean-EOF policy=block: [message_start, content_block_start, delta, delta, content_block_stop, event: error]
clean-EOF policy=full : [message_start, content_block_start, delta, delta, content_block_stop, event: error]
```

对照撕断档（`/tmp/rev/probe_mut2.py`，HEAD 原码）：

```
policy=block  raised=RemoteProtocolError  chunks=5  [... content_block_stop]      # 无 error 帧
policy=full   raised=RemoteProtocolError  chunks=0  []                            # 一个字节都没有
```

**报告描述的那道分界确实存在，而且我的探针有分辨力（同一段代码在干净 EOF 下发得出 error 帧）。**

我另外查了「有没有别的层在撕断时补发了什么」，答案是没有：

- `_tracked_delivery`（`pipeline_app.py:731-757`）：`except Exception as error: accounting.failure = error; raise`（:746）——只记账，原样重抛，不产字节。
- `_AccountedStreamingResponse.__call__`（`pipeline_app.py:686-702`）：`finally` 里只做 `self._content.aclose()` 与 `accounting.finish()`（:702），并明确保留原异常（`raise primary from close_error`）。不产字节。
- starlette `StreamingResponse.stream_response`（`responses.py:248-255`）：`await send({..., "body": b"", "more_body": False})` **只在 `async for` 正常跑完之后**。异常穿过时这一句不执行，响应体在传输层非正常终止。

**证实。档位：足以据此行动。**

**【报告未覆盖的行为，值得单列】** 在 `full` / `until-tool-use` 策略下撕断，客户端拿到的是 **HTTP 200 + 零字节 + 撕断的连接**。部署版本（replay 未接线）上这是这两种策略的 100% 形态。报告只在 abandon 判定的语境里提了策略前提，没提这个明显更糟的可观察后果。**档位：足以据此行动**（若那台机器真用了非 `block` 策略，P0 的紧迫性还要再高一档）。

---

## 6. 论断 6：「吞掉异常会造成回归」—— **证伪**

报告 §2.4 原文：

> **单纯吞掉异常会造成回归**：撕断目前是客户端**唯一**能察觉截断的信号。改成 `return` 会给客户端一个干净的流结束，截断就与成功在线上**完全同形**了——这正是 STR-04 当初要消灭的那个形状（「不得再发 `message_stop` 冒充成功」）。

这段话有三处错，其中第二、第三处直接推翻了它导出的顺序结论（「先补 2.3 才谈得上 2.4，顺序反过来就是回归」）。

### 6.1 「与成功完全同形」不成立

我在 `/tmp/rev/srcH_ret`（HEAD 副本，只把 283 行 `raise torn` 改成 `return`）上跑：

```
policy=block  raised=None  chunks=5  [message_start, content_block_start, delta, delta, content_block_stop]
policy=full   raised=None  chunks=0  []
```

成功的流以 `terminal_frames` 结尾，即 `message_delta`（带 `stop_reason`）+ `message_stop`（`stream.py:324-328`）。`return` 档**一个都不发**。所以两者在 SSE 层面不同形——差的正好是那两个帧。

更要紧的是：报告援引 STR-04 的「不得再发 `message_stop` 冒充成功」来支持自己，**方向是反的**。那条冻结条款禁止的是**发出** `message_stop`；`return` 路径恰恰一个 `message_stop` 都不发。这条先例支持不了它想支持的结论。

### 6.2 【Major F3】它排除的是错的候选：正确的改法是 `break`，不是 `return`

`raise torn` 改成 `break`，控制流会落到 300 行往下，那里已经有现成的处理：`session.finish()` 释放扣留的块 → 若 `client_has_bytes` 被置位 → `if not terminal.seen: yield error_frame(..., code="incomplete_responses_stream")`。

我在 `/tmp/rev/srcH_brk`（HEAD 副本，283 行 `raise torn` → `break`）上实测：

```
policy=block  raised=None  chunks=6  [message_start, content_block_start, delta, delta, content_block_stop, event: error]
policy=full   raised=None  chunks=6  [message_start, content_block_start, delta, delta, content_block_stop, event: error]
```

帧内容：

```
event: error
data: {"type":"error","error":{"type":"upstream_error","message":"Responses stream ended before a successful terminal event","code":"incomplete_responses_stream"...
```

**一个关键字，撕断路径就拿到了带内 error 帧，用的是已闭合那一半的现成线上形状，没有新帧类型、没有新 wire shape。而且 `full` 策略下顺带把扣留的块也交付了（6 chunk vs 现状的 0 chunk）。**

这直接推翻报告的 P1/P2 顺序论证：它认为 2.3（补帧）与 2.4（消 traceback）是两件事、必须先做前者，理由是单做后者会回归。实际上 `break` **同时完成两件事**，而它论证回归时假设的 `return` 是一个没人会提议的改法。

### 6.3 但代价是真实的，而报告和 6.2 都没算：运维侧会丢失异常原文

这是我认为必须交回用户裁决的**真实**取舍（不是报告说的那个）。我跑了 `_tracked_delivery` + `_StreamAccounting`（`/tmp/rev/probe_acct.py`）：

```
HEAD (raise):   acct.drained=False  acct.failure=RemoteProtocolError('<StreamReset ...>')
                _ending() -> ('fail', 'stream failed before a terminal event: <StreamReset stream_id:3, error_code:8, remote_reset:True>')
break 档:       acct.drained=True   acct.failure=None
                _ending() -> ('fail', 'upstream stream ended without a terminal event')
return 档:      同 break 档
```

（探针末尾会抛 `AttributeError: 'FakeChain' object has no attribute 'capabilities'`，来自 `_log_completion` 里 `format_completion_line(...)` 的渲染——traceback 报的行号 `pipeline_app.py:301` 是**探针实际执行的工作树版本**的行号，不是 HEAD 的，此处按记录原样保留。抛点发生在上述三个字段计算完之后；我打印了完整 traceback 确认过，不影响读数。）

两个后果：

1. **报告「改成 `return` 截断就与成功同形」在运维侧也不成立**——`[FAIL]` 照旧出。三档全是 `fail`。
2. **真正的损失是 detail 从异常原文退化成泛化文案**。这正好撞上报告 §2.1 引的那句 docstring：「It is the only account of what went wrong that exists anywhere」。所以 `break` 这个改法需要配一个「把 tear 的原文另行送进 accounting」的小改动，否则是拿运维可观测性换客户端可观测性。

**证伪。档位：足以据此行动。** 建议把 §2.4 整节重写为：候选是 `break` 而非 `return`；带内帧不需要新设计；真实代价是 `accounting.failure` 丢失，需要一并处理。

---

## 7. 【Major F2】报告漏掉的最重要一条：P1 的定性反了

报告 P1：

> 但这是**冻结 Spec 的对外行为变更**，按项目规矩要先有 Spec 再动实现——**需要你裁决**。

我去查了冻结 spec 本身（不是任何报告的转述）。`.dev/docs/anthropic-responses-bridge/spec.md`，文档状态 **`FINALIZED`**，自述「本文件是实现与验收的**行为 oracle**」「实现进度不得反向改写本规格」。它的「Error 契约」一节：

```
- Responses HTTP status、error body、terminal failure、WS upgrade／network error、parse error、conversion error、
  limit error 与 cancellation 先归一为 `ApiError`，再映射为 Anthropic error envelope。
- commit 后发生错误时，HTTP status 已不可更改；发送一个 Anthropic SSE error terminal，关闭 stream，
  History 标记 failed／aborted，且不发送成功 terminal。                       (spec.md:385)
```

以及「SSE／WS envelope 契约」第 5 条（`spec.md:289`）：「terminal error 在尚未提交 HTTP success 时使用 Anthropic HTTP error；**已提交后使用 Anthropic SSE error event**，且不得再发 `message_stop` 冒充成功。」

**「网络错误」+「已 commit（首块已交付）」正是本次事故的形态，而 spec 对这个形态的裁决已经写死了：发一个 Anthropic SSE error terminal。**

所以现状不是「一个待裁决的对外行为变更」，而是**实现偏离了已冻结的行为 oracle**。这把 P1 从「需用户裁决的功能扩面」降级成「按已有裁决修实现」，优先级和所需流程都不一样——而且结合 F3，它连实现代价都只有一个关键字（加上 §6.3 的记账补丁）。

**两点必须写清楚的限定，否则我这条也会犯它那种错**：

1. **适用范围有争议，而争议来自 F1。** 这份 spec 管的是 Messages → Responses 桥；本次事故按 F1 发生在 Anthropic 腿上。严格说，该 spec 的 Error 契约是否约束 Anthropic 腿，需要用户裁一次。**但**：`stream.py:316` 的注释自己就在这段**两腿共用**的代码里援引该条款（「The frozen Spec rules these two mutually exclusive: 不得再发 `message_stop` 冒充成功」），说明实现方已按「该 spec 条款管这段共用代码」在办事。据此我倾向认为它同样约束撕断路径，但这一步是我的判断而非 spec 原文。
2. **`stream.py:274` 那条注释与 spec 相抵。** 报告引它（「Deliberately only this one … a separate question with its own answer to find」）作为「刻意推迟」的依据。代码注释推翻不了 `FINALIZED` 的行为 oracle——按 spec 自己的话，「实现进度不得反向改写本规格」。这条注释本身就该被复查。

**档位：足以据此行动**（但适用范围那一问必须交用户裁）。

### 7.1 附带发现：报告说「已登记」，其实没登记进任何活文档

报告称这是「**已登记的**刻意推迟」，引 `.dev/docs/delivery-keepalive/reports/260820-review-pipeline-idle-timeout.md:292`。我读了原文，那份报告在同一段里说的恰恰是反面：

> 这与 `stream.py:173-177` 登记的 STR-04 缺口是同一件事的两半。研究报告 §6 第 3 条已把它列为待裁决，**本次实现既没有解决，也没有在任何文档里新增登记**。**建议在合入前把这条写进 `.dev/docs/<topic>/decision-pending.md` 之类的待裁决台账**，不要让它只活在一份 `docs/tmp/` 报告里。

我按建议去查了活文档，确认那条建议**没有被执行**：

```
$ rg -n '撕断|RemoteProtocolError|客户端.*读不出|带内' .dev/docs/delivery-keepalive/deferred.md .dev/docs/upstream/h2-goaway/deferred.md .dev/docs/upstream/retry-and-continuation/deferred.md
（exit 1，无命中）
```

它目前只活在 `reports/` 与 `tmp/` 里。按项目规矩（「不要让一份报告成为唯一真相来源」），**「已登记」这个措辞不成立**，而这个措辞正是被用来给 P1 降紧迫度的。这条我列为 **Minor f4**，因为它不改变技术事实，只改变紧迫度叙述。

### 7.2 另一条：已有一份在办的计划文档，报告没提

`.dev/docs/tmp/260821-plan-g1-upstream-error-events.md` 是 2026-08-21 的「G1 方案：让活跃 pipeline 链路认出上游发来的错误事件」，性质自述「单一缺口的边界与设计裁决，**供直接执行**」，并已经把上面那几条 spec 原文摘出来了。本诊断的 P1 与它高度重叠却完全没有引用它。**交回主会话：请确认 P1 是不是 G1 的一部分，避免开两条并行的线。** 档位：倾向如此，需主会话核。

---

## 8. 报告没提、我查过、判定「没问题」的项（列出以免下一位评审重跑）

用户第 7 条点名的几项，我逐一查了，结论都是**否定**——即不是缺陷。这些是正面发现，不计入 Major/Minor：

1. **上游响应未释放？没有。** `httpx2/_models.py:1031-1059` 的 `aiter_raw` 带 `finally: await self.aclose()`，撕断路径必经。生产链的源头 `response.aiter_bytes()` 走的正是它，且 `response` 的声明类型是 `httpx2.Response`（`executor.py:42`）。另外 `_events_with_ping` 的 `finally` → `finish_stream_cleanup` → `_close_iterator(stream)`（`keepalive.py:84`）是第二道关闭。冻结 spec 的「每个 upstream response 在成功、失败、retry、cancel 与 shutdown 路径上都必须关闭一次」在这条路径上成立。

2. **重试预算被错误消耗？没有。** `decide_stream_ending`（`retry.py:114-155`）只在 `not downstream_opened` 分支里调 `ledger.take(reason)`（`retry.py:137-139`）。本次走的是 `committed_blocks > 0` 的 abandon 分支（`retry.py:151-155`），一次 `return` 到底，不碰账本。我在 §4.1 的探针里也观察到 `block` 档 `reopen called: 0`。

3. **`_cancel_and_observe` 出现在栈上暗示清理路径有问题？不暗示，是正常产物。** 我在 HEAD 与 `9aa31f9` 的**每一条**撕断路径上都观察到了这一帧（§1.2、§4.1，共 7 次运行），无一例外。机制是：pull task 已带异常完成 → `_events_with_ping` 的 `finally` 用 `task`（未置 None）调 `finish_stream_cleanup` → `_cancel_and_observe` 的 `await pending`（`keepalive.py:126`）**重新抛出同一个异常对象**，Python 往它的 `__traceback__` 上追加这一帧 → 立刻被 `except Exception as error: return error`（`keepalive.py:134-135`）接住 → `keepalive.py:81-82` 的 `if pending_error is primary: pending_error = None` 明确认出它就是主异常并丢弃。**异常不是从 cleanup 里冒出来的**，它只是路过时留了个帧。

4. **清理路径会不会用第二个异常盖掉主异常？不会。** `finish_stream_cleanup`（`keepalive.py:69-115`）返回 `(cleanup_error, cleanup_cancellation)`，`_events_with_ping` 的 `finally`（`stream.py:151-157`）先判 `if primary is not None: ... raise primary from cleanup_error`。主异常始终赢，清理失败挂在 `__cause__` 上。这是正确的。

5. **`accounting` 会不会记两遍？不会。** `_StreamAccounting.finish()` 首行 `if self.done: return`；`_tracked_delivery` 的 `finally`（`pipeline_app.py:756-757`）与 `_AccountedStreamingResponse.__call__` 的 `finally`（`pipeline_app.py:701-702`）都会调，后者的注释明确说明了这是有意的双保险。

6. **HEAD 新增的 `ClientDeadlineError` 分支会不会把这次请求改判？不会。** `ClientDeliveryConfig.client_request_deadline` 默认 3600 s（`schema.py:268`），本次 48 s，够不着。（这条也顺带说明 HEAD 与部署版之间还有一处行为差异，报告没提，但对本次无影响。**另注**：这条分支正是 §0.1 里同伴此刻在改的那一处。）

---

## 9. 缺陷清单

### Major

| # | 位置 | 问题 | 建议动作 |
|---|---|---|---|
| **F1** | §1.2、§4 全节 | `think(enc:1)` 的 `think` 唯一说明这次走的**不是** Responses 上游（`REASONING_WORD` + `dialect_for` + `assembler_for`），报告却引 `assembler.py:320`（`ResponsesAssembler._close`）当证据；Anthropic 侧应为 187。结论不变，但事故发生在哪条腿被读反，而 F2 的定性依赖这一点 | 改行号；显式写出这是 Anthropic 腿；重估 spec 适用性 |
| **F2** | §2.3、P1 | 把「实现偏离 `FINALIZED` 行为 oracle」写成了「需用户裁决的对外行为变更」。`spec.md:385` 与 `:289` 对「commit 后 network error」已裁决为「发一个 Anthropic SSE error terminal」 | P1 重新定性为 spec 一致性缺陷；仅「该 spec 是否约束 Anthropic 腿」需用户裁 |
| **F3** | §2.4、P2 | 「吞掉异常会造成回归」不成立：候选是 `break` 而非 `return`；`break` 实测直接产出现成的 `incomplete_responses_stream` 帧（block 与 full 两档皆是），P1 与 P2 不存在顺序依赖。且 `return` 也不与成功同形，援引的 STR-04 条款方向相反 | 整节重写；真实代价改为「`accounting.failure` 丢失，`[FAIL]` detail 退化」 |
| **F4** | §1.3 | 「部署的是 `9aa31f9`……不是推测」超出证据：行号只定位到跨 5 个提交的内容区间；「三个行号」里有一个（`keepalive.py:126`）鉴别力为零 | 改写成区间；承重结论（replay 未接线）我已在 5 个提交上验满，P0 不变 |

### Minor

| # | 位置 | 问题 |
|---|---|---|
| f1 | §1.3 表格 | 正文说「三个行号」，表格只有两行 |
| f2 | §1.3 | 漏掉一个有鉴别力的免费判据：`stream_delivery` 帧，`9aa31f9`=206 / HEAD=207 |
| f3 | §2.2 | `network.max_retries` 的实际路径是 `strategies.network.max_retries`（`schema.py:163-165`）；值 9 正确，`max_total=20`（`schema.py:172`）正确 |
| f4 | §2.3 | 「已登记的刻意推迟」措辞过宽：它只活在 `reports/` 与 `tmp/`，被引的那份报告自己说的是「没有在任何文档里新增登记，建议登记」，而该建议未被执行（活文档 grep 无命中） |
| f5 | §1.1 vs §5 | §1.1 引 `httpcore2.RemoteProtocolError`，§5 测 `httpx2.RemoteProtocolError`，中间的 `map_httpcore_exceptions` 映射步骤未写出。这一步承重：换成 `httpcore2` 类，`normalize_upstream_error` 返回 `None`，结论翻转 |

### 报告结论中我确认无误的部分

- §2.1 `[FAIL]` 行符合 `.dev/docs/tui/spec.md:74`（我核对了原文，逐字相符），detail 文案我在 `probe_acct.py` 里实测为 `stream failed before a terminal event: <StreamReset ...>`，与 spec 一致。
- §2.4 引 `lifecycle/adapter.py:403` 作为「答复而非抛」的同型先例，行号与原文正确，且「这里做不到」的理由（响应头已发、200 已定死）成立——starlette 源码与 `_AccountedStreamingResponse` 未覆盖 `stream_response` 都印证了。
- §4 的自我限定（单样本、只够作提示）写得对，且**遵守了用户 2026-08-20 关于「上游为何发 CANCEL 不可判定」的裁决**。我也不去碰这条。
- P0（升级那台机器）方向正确，且我把它的依据加固了。

---

## 10. 我的建议顺序（与报告不同）

1. **P0 不变**：升级那台机器。零代码改动，纯收益。我把「replay 未接线」验满了整个候选区间，这条最稳。
2. **原 P1 + P2 合并为一条 P1**：`raise torn` → `break`，同时把 tear 的异常原文另行送进 `_StreamAccounting.failure`（否则运维侧丢原文，见 §6.3）。定性是**修复对冻结 spec 的偏离**，不是功能扩面。**唯一需要用户裁的是**：`anthropic-responses-bridge/spec.md` 的 Error 契约是否约束 Anthropic 腿（F1 + F2 的交点）。
3. **交回主会话核对**：`.dev/docs/tmp/260821-plan-g1-upstream-error-events.md` 已是「供直接执行」的方案且引了同一批 spec 条文。请确认本条 P1 是否就是 G1 的一部分，避免开两条并行的线。
4. **不做**：追查上游为何发 CANCEL（用户已裁）。

---

## 11. 探针有效性自证

按项目记忆「先证明探针真的跑了，再读它的数字」：

- `probe_9aa.py` 首行打印 `app package resolved to: /tmp/rev/src9/app/__init__.py`，证明它读的是 `9aa31f9` 的码而不是本机 `src/`（venv 里还装着一个 `app` 分发，PYTHONPATH 优先级压过它——这一点是被打印出来的，不是被假设的）。
- `probe_mut.py` / `probe_mut2.py` 的两棵变异树在写入前用 `assert lines[282].strip() == "raise torn"` 断言了改的是哪一行，并回显改后内容。
- §5 的否定结论（撕断无 error 帧）配了正样本对照（`probe_eof.py` 的干净 EOF 能发出 error 帧），证明探针对这个帧有分辨力，不是「哪儿都发不出来」。
- §6 的三档（`raise` / `break` / `return`）跑的是同一个探针脚本、同一份 fixture，只有 PYTHONPATH 不同，唯一变量是那一行。
- `probe_acct.py` 末尾的 `AttributeError` 来自我的 `FakeChain` 缺 `capabilities`，抛点在 `pipeline_app.py:301` 的 `_log_completion` 渲染里，发生在 `drained` / `failure` / `_ending()` 三个读数计算完之后；我打印了完整 traceback 确认过抛点。
- **仓库未被我改动**：所有变异都在 `/tmp/rev/` 的 `git archive` 副本上；本次评审对仓库的唯一写入是本文件。评审结束时 `src/` 与 `tests/` 处于脏状态，那是一个并行会话的改动，不是我的——见 §0.1，那里给了它的内容、mtime 与对本报告读数的影响分析。

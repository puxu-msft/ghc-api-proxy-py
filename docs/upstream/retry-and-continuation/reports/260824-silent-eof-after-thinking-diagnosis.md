# 一条 `[FAIL] … upstream stream ended without a terminal event` 的诊断（req=75ccdf6f）

日期：2026-08-24。代码基线：主仓 `0f2e7f1`；异源评审后按 `b5bc8f9` 复核，本文行号一律标注取自哪个提交（诊断期间同伴推了 `04361a5`、`b5bc8f9`，`stream.py` 相关段落整体后移 9 行）。

**修订记录**：v2（2026-08-24），采纳异源评审 3 major + 2 minor，逐条处置见 `260824-review-silent-eof-diagnosis.md`。v1 有两处错误已改正——时间线重建的间隔位置搞错了，以及**声称客户端结局无法判定，实际可从客户端 transcript 取证且结论与 v1 的推断相反**。

**v3（2026-08-24，同日）：§8 第 2 项已落地，主仓 `a7a0e05`。** 并且**第 8 节的框架本身是错的，如实记在这里**：v1／v2 把「干净 EOF 要不要咨询 `_hand_over`」与「要不要重定 `stream_idle`」两项都写成「需用户裁决」，用户当场指出看不出有什么分叉——查证属实，两项都不是分叉。前者由用户亲笔的 `docs/.human-controlled/upstream-retry-and-continuation.md` 第 30 行**早已裁定**（见 §6 的补充），实现违反它，是 bug 不是待裁事项；后者根本不是修法。**这正是 CLAUDE.md 写死的那个失效形态：授权就在被绕开的那份文档里。** 下文第 8 节保留原措辞作为点时记录，读时请连同本条一起读。

## 0. 结论摘要

上游（GHC 的 **Anthropic 腿**）在 13 秒内交付了一个完整的加密 thinking 块，随后**在本侧两次拉取之间空出 168.63 秒**，最后**切穿在另一个块的中间**并干净地关闭了 h2 流，`message_delta` / `message_stop` 一个都没发。客户端收到的是 SSE error 帧。这是上游的故障，本侧三道守卫都按既定配置正确地没有介入。

线索之上有两件本侧的事值得裁定：

1. **`stream_idle: 0` 的依据「活连接上的静默没有可证明安全的 wall-clock 上界」，现在有了可量化的经验分布**：8424 条同腿其他流的同指标上界是 31.98 秒，无一超过 33 秒，而这次是 168.63 秒。这**不构成对该命题的证伪**（有限样本做不到），但它把任一候选阈值的误杀风险在观测窗口内量化了。
2. **干净 EOF 这条结局从不咨询 `_hand_over`，而撕裂那条会**。两条路把客户端留在同一个位置（`retry.py:126` 明文如此），出口却不同。本次 `committed_count == 1`，**一旦被咨询，交接本来会成功**。该条经异源评审逐环撞击未被推翻。

## 1. 原始日志行

```
[FAIL] 09:01:16 H1/H2 200 POST /v1/messages claude-opus-5 182.0s ↑396.9KB ↓4.7KB think(enc:1): upstream stream ended without a terminal event req=75ccdf6f-2db8-4785-968c-682a5d8c018b
```

## 2. 一手证据与时间线

### 2.1 代理侧落盘

取自 `~/.local/share/ghc-api-proxy/requests/requests-20260824.jsonl`（**实测**，完整记录）：

| 字段 | 值 | 读法 |
|---|---|---|
| `started_at` / `duration_s` | 08:58:14.445Z / 181.99 | 全程 182 秒 |
| `first_upstream_byte_s` | 2.07 | 上游 2 秒开始回话，不是排队或握手问题 |
| `upstream_chunks` | 10 | 整轮只有 10 次到达 |
| `upstream_max_gap_s` | **168.63** | **两次拉取之间**的最长间隔，见 §2.3 的语义限定 |
| `bytes_in` / `bytes_out` | 406 427 / 4 797 | 上行 397KB，上游只回了 4.7KB |
| `blocks` / `thinking` | 1 / `["enc"]` | 一个完整块，加密 thinking |
| `terminal_seen` / `stop_reason` | `false` / `""` | 终结事件、停止原因都没等到 |
| `dialect` | `anthropic` | Anthropic 上游腿，不是 Responses |
| `attempts` | 1 | 未发生任何重试 |
| `upstream_conn` | `140.82.112.22:443`, alpn `h2`, stream_id 1 | 该连接上的第一条流 |
| `losses` | `[]` | 翻译层未丢弃任何东西 |

History 库对本次请求**没有**记录：`~/.local/share/ghc-api-proxy/history.db` 最后写入是 2026-08-20，且 `inference.py`（`0f2e7f1`:584）只在 `terminal.seen` 为真时才写 `context.reply`。出站帧的原始字节因此无处留痕——但见 §2.2，客户端那一侧留了。

### 2.2 客户端侧落盘（决定性，v1 遗漏）

`~/.claude/projects/-home-xp-src-ghc-api-proxy-py/06dcd6c1-36d4-4204-a630-80c4df8a47a7.jsonl`（**实测**，`json.loads` 逐行解析）：

- **line 4900**，`2026-08-24T08:58:27.792Z`，`message.id = 635ad11c-bc28-4730-a314-f7f929d21692`——与代理落盘的 `message_id` 逐字相同——`content` 只有 `['thinking']`，`stop_reason = None`。
- **line 4901**，`2026-08-24T09:01:16.504Z`，**另一个** message id，`stop_reason = stop_sequence`，`text = 'API Error: upstream stream ended before a terminal event'`。这是 CC 自己把 API 错误渲染成的一轮助手消息，不是代理发的帧。

那句 message 逐字对应 `stream.py` error 帧的常量（`0f2e7f1`:483 / `b5bc8f9`:492）。**故客户端走的是 SSE error 分支，`assembler.cut_mid_block` 为真。**

### 2.3 时间线重建

**证据强度：骨架为实测（两侧时间戳互相印证），中间一步为推断。**

```
08:58:14.445  受理，开始
08:58:16.51   上游首字节（+2.07s）
~08:58:27.79  加密 thinking 块合拢并交付客户端 —— 客户端时间戳实测
              （此前累计约 9 次到达）
              ↓ 168.63 秒，本侧两次拉取之间无任何到达
~09:01:16.4   最后一次到达；它开了一个新块而未合拢
09:01:16.43   上游干净 EOF；代理写完成行
09:01:16.504  客户端收到 error 帧 —— 客户端时间戳实测
```

两侧独立测得的间隔吻合：代理侧 168.63 秒，客户端侧 `09:01:16.504 − 08:58:27.792 = 168.71` 秒。

「最后一次到达开了一个新块」是**推断**，依据是 `cut_mid_block` 为真（§2.2 实测）要求装配器留有未合拢的草稿，而 thinking 块在 08:58:27.79 之前已合拢。

> **v1 的错误在此**：v1 写成「收完 10 个 chunk → 静默 → EOF」。`upstream_max_gap_s` 是**两次到达之间**的最大值，且循环结束后不再计算末段，所以那 168.63 秒必然落在 10 次到达**之中**，不在最后一次到达与 EOF 之间。

## 3. 同指标的经验分布（本文最有分辨力的一段）

口径：`~/.local/share/ghc-api-proxy/requests/requests-2026082*.jsonl`，剔除测试模型（`claude-model` / `cc-model` / `gpt-model` / 空 / `nope`；该过滤口径经评审复核，无漏项、无误剔真实模型），只取带 `upstream_max_gap_s` 字段的记录。**两条腿取同一截止时刻 2026-08-24T10:58:53Z**（v1 此处混用了两个快照，已改正）。

**Anthropic 腿**，剔除本故障后 n = 8424（其中 `ok` 8405、`gone` 9、`retry` 10）：

- 最大 **31.98 秒**；第二 30.81；第三 30.51
- 超过 31 秒：**1 条**；超过 33 秒：**0 条**
- 收紧到 `status == ok` **且** `terminal_seen` 的严格队列（n = 8405）：最大仍是 **31.98 秒**——队列纯度不影响这个上界
- 模型构成：`claude-opus-5` 8361、`claude-sonnet-5` 63。**这个上界实质上是 claude-opus-5 的性质**

**Responses 腿**，同窗口 n = 1472：最大 **17.09 秒**，超过 33 秒 0 条，全部 `gpt-5.6-sol`。

两条腿各自压在一个整数附近（≈30 / ≈10）且长回合不抬高上界，形状指向**上游各自的固定保活计时器**。

### 3.1 这个指标能说什么、不能说什么

**必须连同限定一起使用，否则会被读过头。**

- **「本次是同指标上的 5.3 倍离群点」——强到可以据此行动。** 8424 个样本，双向分离干净，唯一越界样本就是这条死掉的流。这个**比较性**结论不受下面的层歧义影响，因为所有流用的是同一把尺。
- **「那 168.63 秒是上游在网线上的静默」——未证实，存在层歧义。** `inference.py`（`b5bc8f9`:679-692）的 `now = time.monotonic()` 取在 `async for chunk in chunks:` 的循环体内，即 chunk **被拉取到本层**的时刻；拉取节奏由下游消费者决定，故本侧调度与 backpressure 会折进这个数。评审的队列探针实测：本侧暂停 0.204 秒 → gap 记为 0.204。**仅凭该字段不能排除本侧调度、backpressure 或 transport。**
  - 但对本请求，层归属已被 §2.2 大幅收窄：客户端独立测得同样的 168.71 秒，所以这不是记账假象。**未排除**的替代解释是「上游在缓慢吐一个永不合拢的块」，不过全程只有 10 次到达，使它很难成立。
- **「那 ~30 秒是上游的应用层 ping」——只是倾向，未证实。** `tests/int/cassettes/` 里没有任何 ping 帧（**实测**，grep 无命中），`upstream_chunks` 只计到达次数不计内容。坐实需要一次带内容的录制。
- **窗口约 2 天。** `upstream_max_gap_s` 是 2026-08-20 那次事故之后才加的字段（`inference.py` 该函数 docstring 写明缘由），8-22 之前记录该字段为 `null`，更早的三条同类故障无法参与统计。该字段还漏掉首段（那是 `first_upstream_byte_s`）、末段，以及少于两次拉取的流。

## 4. 本侧三道守卫为什么都没动

| 守卫 | 配置 | 本次表现 | 判断 |
|---|---|---|---|
| `upstream_request_timeouts.stream_idle` | 0（禁用，bundled default） | 168.63 秒间隔未被掐断 | **按配置正确**。`delivery_policy.py:106-111` 与 `docs/.human-controlled/config.example.yaml:293-299` 写明这是用户冻结的不变量：绝不误杀合法长思考 |
| `upstream_request_timeouts.upstream_request_deadline` | 1200 秒 | 182 秒远未触及 | 正确，此守卫不为这种情形设计 |
| `client_delivery.sse_ping_interval` | 15 秒 | 客户端全程未断开 | **配置为事实；每个 ping 实际送达未实测**。客户端在线由 §2.2 独立证实（它在 09:01:16.504 确实收到了错误帧）。注意 `fail` 而非 `gone` 只证明 delivery 生成器自然耗尽，**不单独证明** TCP 对端一直在 |

即：本侧没有任何东西坏掉。182 秒里有 168.6 秒是在**按用户的明确裁定**等一个再也不会来的字节。

## 5. 客户端最终收到了什么（已由 §2.2 判定）

代码路径 `stream.py`（`0f2e7f1`:463-486 / `b5bc8f9`:472-495）。`terminal.seen` 为假时按 `assembler.cut_mid_block` 二分：

- **落在块边界**（`_drafts` 空）且 `unterminated_stop_reason` 非空 → 合成终结帧。注意表达式是 `terminal.stop_reason or settings.unterminated_stop_reason`——**上游给过停止原因时上游优先**，合成值只在上游什么都没说时才用上。
- **切穿了某个块** → SSE `error` 帧，`code="incomplete_responses_stream"`，且**不**补 `message_stop`。

**本次走的是第二条**（§2.2 实测）。因此整条 `stop_reason: "incomplete"` 的追查**与本次事故无关**——那条分支没走到。

> 该合成值本身的一般性调查另有一份：`.dev/docs/tmp/260824-cc-stop-reason-incomplete.md`。要点：`incomplete` 不在 Anthropic `StopReason` 的 7 个合法值内，但 **CC 实测完全不校验**（真实 CC 2.1.241 接本地假上游，`incomplete` 与 `end_turn` 逐字段相同，带两个控制组）；**而 Python 官方 SDK 的严格 `model_validate` 会 raise**，故非 CC 客户端是风险面。另：`client_delivery.unterminated_stream_stop_reason` **不在** `docs/.human-controlled/config.example.yaml` 里（实测）。

**仍然成立的可观测性缺口**：完成行对上述两种结局给出**逐字相同**的 `upstream stream ended without a terminal event`（`inference.py` `0f2e7f1`:616）。本次之所以能判定，靠的是客户端 transcript，不是代理自己的记录。`cut_mid_block` 没进日志行。

## 6. 干净 EOF 从不咨询 `_hand_over`（本文最强主张，经评审未被推翻）

`_hand_over` 在 `stream.py` 只有两个调用点（**实测**，`git grep -n "_hand_over(" HEAD -- src/`）：

- `0f2e7f1`:412 / `b5bc8f9`:417——**撕裂**路径。`if not ours:` 无条件咨询，连分类器叫不出名字的异常也咨询。
- `0f2e7f1`:453——`terminal.seen` **为真**且 `stop_reason` 落在 `continuation.stop_reasons`（默认 `{"max_tokens"}`）时。

**干净 EOF 且 `terminal.seen` 为假这一格两个都覆盖不到**：`async for` 正常跑完，不进 except；落到 447 行之后，`terminal.seen` 那道门直接挡掉。

为什么认为这是缺口而非设计：

1. **本仓自己写下了相反的原则。** `src/app/pipeline/retry.py:126`：「A clean EOF with no terminal event and a torn connection leave the client in the same place, and it is that place — not the manner of arrival — that decides what may legally happen next.」（引文与上下文经评审复核，未断章取义。）
2. **这次够得着。** `committed_count == 1`，`_hand_over` 的 `committed_count == 0` 那道门不成立，**一旦被咨询就会产出一次交接**，客户端会拿到可续写的 `tool_use`，而不是一句 `API Error`。
3. **不对称是同一个提交造出来的。** `78be0d4`（2026-08-22，*close a clean EOF at a block boundary instead of calling it truncated*，**实测** `git log -S "if not ours:"`，归因经评审复核）同时装上了撕裂路径的无条件咨询、并新建了干净 EOF 收尾路径，而没有给后者装。

反方向论据（如实记下）：台账 `deferred.md`:47 的裁定把块边界上的干净 EOF 称为「正常收尾」。但那条针对的是**不要谎报截断**，没有说这一轮完整；且**本次根本不是块边界那一格**。两者不冲突。

**v3 补充（2026-08-24，推翻本节原结论的最后一句）**：v1／v2 在这里写的是「要不要为这一格开口是产品裁决，本文不动手」。**这句话是错的。** 用户亲笔的 `docs/.human-controlled/upstream-retry-and-continuation.md` 第 30 行已经裁定：「如果已经交付过至少一个完整块，则将报错合成为自制的 `tool_use` / `function_call` 块……返回给客户端」。该文第 5–11 行的「无法继续」清单未列入「上游流无终止事件」，最接近的第 15 行「网络中断」属「一般可以继续」。本次交付过 1 个完整块、并且确实报了错（客户端收到的 `API Error` 就是那个 error 帧），**条件成立、处方未被执行**——这是实现违反用户文档，不是待裁事项。已修，主仓 `a7a0e05`，`spec.md` 第 7 条同步修订。

一条佐证这是 bug 而非设计的实测事实：`StreamIdleTimeoutError` 不是 `DeliveryError`，会被记进 `upstream.tear`，走 `not ours` 分支从而**触发接管**。也就是说在修复之前，**被本侧 idle 守卫掐死的客户端结局，反而优于上游干净关闭**。

## 7. 台账需要对账的一处

`deferred.md` 第 20 条引用的代码片段：

```python
reason = replay.eligible(torn) if replay is not None else None
if replay is None or reason is None:
    raise torn          # ← 裸抛。既不发 error 帧，也不咨询 _hand_over
```

**在 HEAD 上已不成立**（**实测**，按 `b5bc8f9` 复核）。`stream.py`:417 现在是 `if not ours: handed_over = _hand_over(...)`，注释明确讨论并否决了旧行为。引入者 `78be0d4`。该条处置栏仍写「登记，不动手」，与代码脱节。其另一半——「分类器叫不出名字时默认可继续还是不可继续」这个产品裁决——已被 `78be0d4` 以「默认可继续」实现并在注释里给了理由。

## 8. 建议（均需用户裁决，本文不实施）

按我的主观优先级：

1. **把 §3 的分布提给用户，重新裁定 `stream_idle`。** 冻结的不变量的**理由**现在有了可量化的对照：在 Anthropic 腿本窗口内，同指标上界 31.98 秒。**这不是「上界被证明存在」，是「误杀风险可被估计」**——一个 90～120 秒的阈值在**已观测的 8424 条**里不会误杀任何一条，窗口外无保证。不变量是用户的裁定、写在人写文档里，**我不改也不建议绕过，只交证据**。三条必须一并交上去的限制：窗口仅约 2 天、样本 99% 是 `claude-opus-5`、阈值需**分腿**（Responses 腿上界只有 17 秒）。
2. **裁定干净 EOF 要不要咨询 `_hand_over`**（§6）。这是本次唯一「本可以做得更好」的地方。
3. **让完成行区分两种终结形态**（§5）。把 `cut_mid_block` 记进请求记录，成本极低，可独立落地。本次靠客户端 transcript 才判定得出，代理自己说不出来。
4. **对账 `deferred.md` 第 20 条**（§7）。
5. **敞着的问题：那 168.63 秒的层归属。** §3.1 指出该指标折进了本侧 backpressure，评审证伪了「等于网线静默」这个读法却未给替代解释。要分辨需要在该字段旁边再记一个**不受下游拉取节奏影响**的量（例如在 `with_idle_timeout` 那一层计时）。

## 9. 我排除掉的路线

- **本侧 h2 / 传输层 bug**：排除。`upstream_conn` 显示 stream_id 1，`losses` 为空，`attempts` 为 1，无 GOAWAY / StreamReset 记录（那些走 `stream failed before a terminal event: …`，同窗口有 13 条，形态完全不同）。
- **客户端提前离开**：排除，双重证据。日志判 `fail` 而非 `gone`（`inference.py`:617），且客户端 transcript 显示它在 09:01:16.504 收到了错误帧（§2.2）。
- **合成 `incomplete` 终结帧导致客户端异常**：排除。本次根本没走那条分支（§2.2、§5）。
- **`ContinuationSupport` 配置缺失导致没交接**：排除。不是配置问题，是代码路径根本不咨询（§6）。
- **请求过大触发上游截断**：**未排除，但不支持**。上行 397KB 偏大，但同窗口大量更大的请求正常完成；三条历史同类故障上行分别为 974KB / 343KB / 270KB，跨度太大不构成解释。要坐实需按 `bytes_in` 分桶统计故障率，本次未做。
- **上游 ping 帧内容核实**：**未做**。cassettes 无 ping 样本，需一次新录制。不影响 §3 的统计结论，只影响对它的因果解释。
- **168.63 秒的层归属**：**未解决**，见 §8 第 5 条。

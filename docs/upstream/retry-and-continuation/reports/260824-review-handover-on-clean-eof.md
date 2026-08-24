# 异源评审：干净 EOF 也走接管（主仓 `a7a0e05`）—— 发现与处置

日期：2026-08-24。评审者：`gpt-opus` 异源 agent。评审基线：主仓 `a7a0e05`（父 `bb17558`），`.dev` `f7c5401`（父 `ef182c9`）。评审在固定提交快照 `/tmp/ghc-api-proxy-review-a7a0e05-d3e11298` 上执行与变异，未改共享工作树。

结论：`needs-fix`，**blocker 0，major 2，minor 3**。**实现本身被确认成立**，两条 major 与两条 minor 都是「写在它周围的话比它描述的东西宽」。

> **本文为什么由被评审方代笔**：该 agent 的执行层禁止创建报告／summary／findings Markdown，要求直接回传。原始 findings 只存在于任务通知里，不落盘就会丢。**转录尽量保留原措辞；处置是我写的。** 这是同一个 agent 类型第二次撞上这个限制（前一次见 `260824-review-silent-eof-diagnosis.md`），已足以当作稳定约束对待：以后派这类评审，直接要求回传，不要求写文件。

## 评审确认成立的部分（先说这个，因为它是主结论）

- **依据链成立，无断章取义。** 人写文档全文把网络中断列为一般可继续；clean EOF 缺失合法 terminal 是上游请求失败，**不是**「代理保护机制触发」。评审逐条查了「无法继续」清单，未发现覆盖本格的条目。
- **块边界那一格未变**：`cut_mid_block=False` 且 `unterminated_stop_reason="incomplete"` 时不咨询接管，仍发合成 stop reason。
- **`committed_count == 0` 未受影响**：仍是空 body、无接管、无 SSE error。
- **非流式路径未受影响**；**Responses 腿正确**（Responses 上游 → Anthropic 客户端会接管并保留完整 item；Responses 客户端因 wire format 被拒，仍得 Responses error）。
- **异常分类主张成立**：`UpstreamStreamUnterminated` 不是 `DeliveryError`，`normalize_upstream_error` 与 `replay_reason` 均返回 `None`，生产 E2E 实测 `hand_back_block` 输出 category=`upstream`。只构造不抛出，未进入本侧／上游 tear 判定。
- **修法取舍成立**：评审**不建议**把两处接管机械合并到 `terminal.seen` 分叉之前——`max_tokens` 路径携带 `error=None + stop_reason`，clean EOF 路径携带合成异常，且块边界正常收尾必须先排除；合并只是重编码同一组条件并扩大改动面。
- **测试有分辨力，无假绿**。评审自跑两轮变异：① 把新增 `_hand_over` 调用置空 → 正例转红、两个对照仍绿；② **把 `error=` 改成 `error=None`**（我没做的那个）→ 正例在异常类型断言处转红、对照仍绿。每轮均先证明运行时加载的是快照里那份文件，并在退出 trap 下还原，还原后 SHA-256 回到 `e8d7641a…`。
- **`78be0d4` 归因成立**，但范围需收窄（见 M2）。
- 门禁：Ruff 通过、Pyright `0 errors`、`1652 passed, 2 skipped`、coverage `90.19%`。

## Major

### M1 —— Spec 第 7 条把义务写宽到了「无法继续」的保护性错误

**评审原文（摘）**：Spec 第 7 条写成「发出该 SSE error event 之前必须先咨询合成续写」，列出的唯一例外只是客户端／配置／重复接管条件。这比实现和最高权威都更宽。代理保护机制属于人写文档明确列出的「无法继续」，实现也正确地让 `DeliveryError` 跳过 `_hand_over`。固定提交中共有 3 个 `yield framer.error(...)`（`stream.py:380`、`:444`、`:516`），并非每个出口都先咨询接管。**独立构造**「已提交一个完整块，第二块触发 `BufferCapExceeded`」的路径，观察到 `proxy_delivery_aborted`，continuation callback 调用次数为 0——符合人写文档第 7 行，违反当前 Spec 字面。

**处置：全部采纳。** 这是本次最有价值的一条，因为它攻击的正是我修订的那句话本身。Spec 是规范性 oracle，照我写的字面去修实现，会把明确不可继续的保护性错误也合成为续写。已改写第 7 条：把义务限定为「失败属于人写文档第 3–18 行的**业务可继续**类，且已交付过至少一个完整 block」，并显式排除该文第 5–11 行各格与本侧 bug，点明实现上对应 `DeliveryError` 与 `ours` 两道判别、三个 error 出口只有上游截断那个受约束。修订记录条目同步收窄，并写明初稿宽在哪、是谁判的。

**这条的一般形状值得记住**：我在收窄实现范围时是谨慎的（代码里明确只碰报错那两格），但把它写进 Spec 时用了一句更顺口、更概括的话。**实现的范围与描述实现的那句话的范围，是两次独立的收窄，第二次我没做。**

### M2 —— 台账 §20 在仍有未决重放问题时被整体闭合

**评审原文（摘）**：§20 被整体标成已闭合，并声称 `78be0d4` 已把「默认方向」落为默认可继续；但该提交只让**已有内容后的 handover** 不再受异常 taxonomy 阻挡，并没有让 taxonomy 无法识别的错误可重放。该提交新增的注释明确说 unnamed failure 仍不 replay，相关产品问题继续留在 §20；同一份 `deferred.md:49` 与 `:299` 也仍写着该问题未解决。运行 `httpx2.DecodingError` 探针：`normalize_upstream_error(...) is None` 且 `replay_reason(...) is None`。

**处置：全部采纳。** 我独立复核了 `stream.py:431` 与 `deferred.md` 的 `:49`、`:115`、`:299`，四处都把 §20 当**未决**问题引用。已把 §20 拆成两半：交接那一半闭合（分撕裂侧 `78be0d4` 与干净 EOF 侧 `a7a0e05` 两次），重放那一半保持开着并写明证据与四处引用。评审的建议「不要撤销正确的归因，应拆分结论」被逐字采纳。

**与我同日另一处错互为镜像**：诊断报告里我把**已裁定**的事报成待裁，这里我把**未裁定**的事报成已决。两者的共同形状是：**没有把一个条目里的多个独立问题分开，就整体给了一个状态。**

## Minor

### m3 —— `unterminated_stream_stop_reason=""` 的注释与旧测试仍承诺 SSE error

**评审原文（摘）**：该注释与旧测试仍承诺操作员会得到 loud SSE truncation；在生产形态的 Anthropic continuation 可用时，新代码会先 handover，因此不会发出该 error。独立 E2E 探针观察到块边界 EOF ＋空 stop reason 产生 `turn_interrupted`、category 为 `upstream`、没有 `incomplete_responses_stream`。现有测试没有配置 continuation，因此仍绿但只证明 fallback。

**处置：注释部分采纳并已改（主仓 `e9b98c2`）**，写明该设置现在仍然 loud、但不再是同一个帧，并点出「这条注释此前承诺的是帧」。**「增加 continuation 已配置的对照」这半未做**：我新加的三个用例里已经有一个块边界 + continuation 的对照（`test_an_eof_at_a_block_boundary_is_still_closed_rather_than_handed_back`），它钉住的正是这条路径不接管；评审说的那个是 `unterminated_stop_reason=""` 且 continuation 已配置的组合，与它不同。**登记为未做，理由是它验证的行为已由 M1 收窄后的 Spec 与既有两个用例共同覆盖，再加一个是同一判据的第三次表述。** 若后续有人认为该组合值得单独钉住，这里是它的出处。

### m4 —— `stream.py` 新注释声称 `committed_count == 0` 会落到 error frame

**评审原文（摘）**：实际控制流在 `client_has_bytes` 为假时已于 `:479-481` 返回，根本到不了该调用和 error frame。独立构造「第一块尚未闭合即 clean EOF」，下游 body 为零字节，continuation 未咨询，也没有 SSE error；该行为是既有行为，没有被本提交改变。

**处置：采纳，已改（主仓 `e9b98c2`）。** 新注释写明这道门从此处不可达、为什么不可达（到达该行意味着 `client_has_bytes` 已置位，而置位它的只有块出站），以及那个零字节结局是既有行为、本次未触碰。

### m5 —— `status.md` 该行第一列用了日期而非提交哈希

**处置：采纳，已改（`.dev` `488215b`）**，第一列改为 `a7a0e05`。

## 评审排除掉的攻击路线（原文转录）

- 「人写文档没有覆盖 clean EOF」：排除。
- 「把 clean EOF 异常真正抛出更统一」：放弃——会把正常迭代结束改造成 tear，进入 replay、归因和异常传播路径，扩大行为面。
- 「传 `error=None` 足够」：排除——会把不存在的 stop reason 当作上游给出的事实，且变异已被测试抓住。
- 「把所有 terminal-less EOF 都 handover」：排除——会破坏块边界＋非空合成 stop reason 的既有裁决。
- 「把两处 handover 调用合成一个前置条件」：放弃。
- 「`UpstreamStreamUnterminated` 会被当作本侧错误」：排除。
- **未核**：req=`75ccdf6f` 的生产取证按任务说明视为已核实，未重新推导；未做新的真实上游网络调用。

## 我对本次评审的评价

**它做到了我请它做的那件最难的事：攻击我自己刚写下的那句 Spec。** M1 不是从代码里找出来的，是从「实现的范围」与「描述实现的那句话的范围」之间的缝隙里找出来的——而那正是我最容易自我确认的地方。它还自己发明了第二个变异（`error=None`），补上了我变异集的一个真实缺口。

它没做的一件事：M1 指出 Spec 写宽之后，没有回头问「那么实现里 `stream.py:380` 那个 error 出口是否也该咨询接管」。评审的立场是实现正确、Spec 错，我复核后同意（`:380` 在 `not ours` 判别之后，`DeliveryError` 与本侧 bug 都从那里出，按人写文档就不该接管）。**记在这里是因为「Spec 与实现不一致时改哪一边」这个判断本身值得留痕**，而不是因为我怀疑结论。

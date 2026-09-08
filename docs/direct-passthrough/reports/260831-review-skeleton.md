# 直连 Responses 透传骨架：独立评审

日期：2026-08-31
被评对象：worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260831-passthrough-skeleton`，分支 `worktree-260831-passthrough-skeleton`，HEAD `64ed5a4`
判据来源：[`spec.md`](../spec.md)（DRAFT v6）、[`plan.md`](../plan.md)（v5）、`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md`、`openai==3.3.1` 的 `ResponseStreamEvent` union、`tests/int/cassettes/` 三份 Responses 流

> **落盘位置说明**：本文原定写入 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/260831-review-skeleton.md`，被 harness 的后台会话隔离守卫拦下（`.dev` 虽是独立仓库，但路径位于主 checkout 内）。评审者无权解除该守卫，故先落到 `/tmp`，由主会话搬运至上述路径。内容以搬运后的位置为准，相对链接按目标位置书写。

## 评审范围

**在范围内**：本轮新增的两个文件的最终状态——`src/app/pipeline/delivery/formats/openai_responses_passthrough.py`（153 行）与 `tests/unit/pipeline/delivery/test_responses_passthrough.py`（196 行）；它们与 Spec §3／§4／§5／§8 的对应关系；测试的鉴别力（变异验证）；docstring 里全部外部引用的真实性。

**明确不在范围内**：`delivery_policy` 的接线（本刀故意未做，`git show --stat HEAD` 确认只有两个新文件，全仓 `rg` 确认无第三处引用这两个新符号）；`ResponsesAssembler` 翻译腿；`ca777df` 的撤销；Spec 自身的产品裁决（只在实现与 Spec 冲突时指出）；`sse_source.py` 的既有实现（仅在 §3 承诺的边界上核对了一次，见 finding 10）。

**verdict：needs-fix。blocker 0，major 4，minor 6，nit 1。**

方向是对的，且对得很实：分组只读 `output_index`、不建类型表、不重排、`unfinished` 暴露而不丢弃——这四条我逐条核过，都成立，`unfinished` 的「不提前丢」也确认了（全模块只有 `_take_safe_prefix` 的 `del self._queue[:cut]` 一处删队列，且删的只是已释放前缀）。`ruff check`、`pyright`、`tests/unit/pipeline/delivery`（184 passed）全绿。四条 major 里没有一条是「方向错了」，全部是承重判据在某个交错顺序或某种事件形态上没兜住，以及一处把项目自己的未闭合问题写成了已核实事实。

---

## major

### `direct-responses-passthrough-skeleton-review-01` — 安全前缀允许一个已完成的 item group 跨越释放边界，提前提交 attempt 并关掉 §5 的 replay 窗口

- **位置**：`src/app/pipeline/delivery/formats/openai_responses_passthrough.py:100-114`（`_take_safe_prefix`）
- **判据**：Spec §5 的提交时点表——「第一批 item 事件 | **是**（提交本次 attempt）」，以及「首个原生事件提交后：**禁止**整次 attempt replay」；Spec §7.2 收口第 2 步「按原序提交 control 与所有**已完成的安全 group**」；§3 脚注引用的用户亲笔块级合同「`_start` 到 `_end` 之间的全部内容」为交付单位。
- **证据**（实跑，非推断）。序列 `created → added(0) → added(1) → delta(1) → done(0)`，最后一步的输出：

  ```
  push response.output_item.done   oi=0 -> released ['response.output_item.added']
  queued after: [('response.output_item.added', 1), ('response.output_text.delta', 1), ('response.output_item.done', 0)]
  ```

  item 0 的 `added` **脱离它自己的 `done` 单独交付**，`done(0)` 被留在队列里等 item 1 关闭。现有两条交错测试都只覆盖了反向顺序（后开的 item 先关：`test_a_finished_item_waits_behind_an_unfinished_earlier_one` 是 `added(0) → added(1) → done(1) → done(0)`），所以这条路径一次都没被跑到。

- **影响**。两层，第二层更贵：

  1. 交付出去的前缀里装着一个 group 的**半截**。这与 §7.2 的「已完成的 group」和用户亲笔的块级交付单位不一致——客户端拿到一个 `output_item.added` 却拿不到配对的 `done`，中间隔着另一个 item 的全部事件。
  2. **它提交了本次 attempt，而提交的那一个字节没有任何内容价值。** 按 §5，第一批 item 事件一旦发出就禁止整次 attempt replay。于是：item 1 若随后以可重试的 `server_error` 失败，本可透明重放的整轮，现在只能把失败露给客户端，而客户端手里只有一个空的 `added(0)`。Spec §5.2 的 v5 修订恰好点过这件事的价值（「损失最大的恰恰是 `full`」），这里连 `block` 都提前把窗口关掉了。

- **判据本身有歧义，这是要连带处理的一半。** §4 的原句是「只有从 frontier 到某位置之间、所有已打开的 item 都已 `done` 时，才释放这段连续前缀」。按字面，前缀 `[created, added(0)]` 里被打开的 item 只有 0，而 0 此刻**确实**已经 `done` 了——所以实现与 §4 的字面**不冲突**，冲突的是 §7.2 与块级合同。§4 没有说清「已 `done`」指的是 item 的状态，还是「它的 `done` 事件也必须落在这段前缀里」，而实现取了代价更大的那一读。
- **建议**：先在 Spec §4 补一句定案（推荐取「一个 item 的事件不得跨越释放边界」——它同时满足 §7.2、块级合同与 §5 的窗口保全，代价只是多一点 head-of-line blocking，而 §4 本来就已经接受了 head-of-line blocking），再让代码跟上。可用的判据：设 `B` 为第一个属于未闭合 item 的事件位置；若存在任何 item 在位置 `≥ B` 处仍有事件，则把 cut 回退到该 item 最早的那个事件位置，反复直到稳定。上例中 cut 会回退到 `created` 之后，即只释放 `created`。同时补一条钉这个顺序的测试。
- **证据强度**：强（实跑复现 + Spec 逐字引用）。歧义那一半是我的判读，需 Spec 侧确认。

### `direct-responses-passthrough-skeleton-review-02` — 「无法归属」与「envelope」共用一个槽位，与 §4 的保守持有规则相反

- **位置**：`openai_responses_passthrough.py:130-139`（`_item_of`）；**related**：`:60-68`（`_Pending.item` 的类型与 docstring）、`:121-127`（`unfinished`）
- **判据**：Spec §4 逐字——「**无法判定某事件属于哪个 item 时，保守持有到 terminal。**」以及 §3「未闭合 item 的尾巴在每一种 ending 都要丢弃」。
- **证据**。`_item_of` 只有两个返回态：`int`（属于该 item）与 `None`。`None` 同时表示「这是 envelope 事件」和「我判不出它属于谁」，而这两件事在 §4 下的处置**相反**：前者可随前缀释放，后者必须持有到 terminal。三类今天就能触发的输入：

  1. **SDK 3.3.1 里真实存在、且不带 `output_index` 的非 envelope 事件**。我枚举了 `ResponseStreamEvent` union 全部 58 个成员，不带 `output_index` 的共 11 个，其中 7 个是 envelope（`response.created`／`in_progress`／`completed`／`incomplete`／`failed`／`queued`、`error`），**另外 4 个不是**：`response.audio.delta`、`response.audio.done`、`response.audio.transcript.delta`、`response.audio.transcript.done`——它们承载模型输出，却既无 `output_index` 也无 `item_id`。
  2. **payload 不是 JSON object 或解不开**。`SseEvent.json()` 吞掉 `JSONDecodeError` 返回 `{}`，于是 `_item_of` 返回 `None`。§3 自己写明 `errors='replace'` 会把非法 UTF-8 换成 `�`，那之后 payload 就解不开了；finding 10 给出另一条更容易触发的截断路径。
  3. 任何将来新增的、属于某个 item 却不带 `output_index` 的事件。

- **两个泄漏点，实跑各复现一次**：

  - **ending 处**（更隐蔽）。序列 `added(0) → 截断的 delta(0) → delta(0)`：

    ```
    queue:       [('response.output_item.added', 0), ('response.output_text.delta', None), ('response.output_text.delta', 0)]
    unfinished:  ['response.output_item.added', 'response.output_text.delta']
    ```

    那条被误判的 delta **不在 `unfinished` 里**。调用方照 §7.2 收口（丢未闭合 suffix → 按原序提交已完成 group）会把它当 control 事件提交出去，而它属于一个永远没闭合的 item——正是 §3 要求丢弃的那条尾巴。

  - **释放处**。同一个事件若在任何 item 打开之前到达，立刻被释放：`released immediately: ['response.output_text.delta']`。

- **影响**：客户端收到一个未闭合 item 的碎片。这与测试文件 `test_an_unknown_event_is_grouped_with_its_item_not_treated_as_envelope` 的 docstring 里亲自写下的危害是同一个——那条测试守住了「未知**事件名**」这一面，没守住「**不带 `output_index`**」这一面。
- **建议**：给「无法归属」第三个槽位（`_item_of` 返回三态，或让 `_Pending.item` 用一个哨兵）；`CONTROL_EVENTS` 命中才判 envelope，其余不带 `output_index` 的一律按 §4 持有到 terminal，并进 `unfinished`。**这不是在加类型表**——名单只区分「信封 vs 其他」，一个从没听说过的 item 事件仍然无须被认识，它落进「其他」就自动得到保守处置，天花板没有被重建。同时更新 `_Pending` 第 64 行「`item` is `None` for control events」这句——它现在是错的。
- **证据强度**：强（SDK 枚举 + 两处实跑复现 + Spec 逐字）。

### `direct-responses-passthrough-skeleton-review-03` — 实例跨 attempt 复用时块级交付静默消失，且没有任何 reset 通路

- **位置**：`openai_responses_passthrough.py:71-83`（类 docstring 第 74 行「One per request.」与 `__init__` 的三个状态）；**related**：`:91-96`（`_closed` 的更新）
- **判据**：Spec §5——replay 时「旧 attempt 的 control events、item 队列、terminal、ids、usage 与内存计量**全部丢弃**」。
- **证据**（实跑）。同一个实例先喂 attempt 1（`created → added(0) → done(0)`），再喂 attempt 2 的同一批事件：

  ```
  attempt 2:
      response.created           -> ['response.created']
      response.output_item.added -> ['response.output_item.added']
      response.output_text.delta -> ['response.output_text.delta']
      response.output_item.done  -> ['response.output_item.done']
  ```

  attempt 2 的每一个事件**逐个立刻释放**，item 0 一次都没被判为 open——因为 `push` 的 `elif index not in self._closed` 在 `_closed` 里查到了 attempt 1 留下的 `0`。块级交付就此消失，没有报错、没有 warning、没有任何可观测事实。旧 attempt 的队列也没有任何 API 可以丢弃。

- **影响**。两条路都通向问题，且必有一条成立：

  - 若调用方照 docstring 的「One per request」复用实例 → 上面这个静默降级；
  - 若调用方每个 attempt 新建实例 → 行为正确，但 docstring 第 74 行是错的，且模块里没有任何地方说过这件事，下一个人照着 docstring 写就会踩进第一条。

- **建议**：把 docstring 改成「one per **attempt**」并说明理由，或加一个 `reset_attempt()` 明确清空三个状态；两者取其一即可，但要在本刀定下来——replay 是后续刀，可 `_closed` 的永久性是**这一刀**决定的。
- **证据强度**：强（实跑复现）。

### `direct-responses-passthrough-skeleton-review-04` — 把项目自己标为未闭合问题的形态，写成了「上游有案可查」的已核实事实

- **位置**：`openai_responses_passthrough.py:81`（`_closed` 的注释：「a `done` may arrive for an item whose `added` was never seen — **a shape this upstream is on record for**」）；**related**：`tests/unit/pipeline/delivery/test_responses_passthrough.py:149`（「**Upstream is on record for sending a `done` whose `added` never arrived.**」）
- **判据**：`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md` 是这条形态的现有权威，它逐字写着：

  - 第 279 行：「**这是设计裁决，本项目两次实测都带 `added`**（§12 P7）」
  - 第 500 行（未闭合项表）：「P7 | 是否真的存在「`done` 无 `added`」形态 | §6.3 的**防御性分支** | 可后补」

- **证据**。除上述两条外，我把仓里三份 Responses 流 cassette 全解了一遍，`added` 与 `done` 的 `output_index` 列表逐一配对，无一例外：

  | cassette | events | oi-runs | added | done |
  |---|---|---|---|---|
  | `anthropic_to_responses_stream.json` | 12 | `[0, 1]` | `[0, 1]` | `[0, 1]` |
  | `history_responses_stream.json` | 125 | `[0, 1]` | `[0, 1]` | `[0, 1]` |
  | `responses_web_search_stream.json` | 16 | `[0, 1]` | `[0, 1]` | `[0, 1]` |

  真正「on record」的是另一件事：`openai_responses.py:570` 的注释说「The same regression is on record in the **reference project**, where the item vanished with no observation of any kind」——那是 `copilot-api-js` 自己的实现丢了 item，不是本上游发过 `done` 而无 `added`。

- **影响**：**代码行为本身是对的**（把孤立的 `done` 判为已关闭，避免队列被一个永不关闭的 item 永久卡死，这是正确的防御），错的只是它给出的理由。而这类错误比代码错更难发现——P7 是一个明确挂着的未闭合问题，一旦被这两处 docstring 洗成「已有记录的上游行为」，后来人就会引用它，P7 也就被一个从未发生过的观测悄悄关闭了。
- **建议**：改成它真实的强度——「防御性：孤立的 `done` 会让队列永久卡死，容忍成本为零；该形态是否真实存在是 `hosted-web-search-spec.md` §12 P7 的未闭合项，本项目两次实测都带 `added`」。测试 docstring 的第一句同样改（测试名本身没问题）。
- **证据强度**：强（权威文档逐字 + 三份 cassette 全量核对）。

---

## minor

### `direct-responses-passthrough-skeleton-review-05` — `CONTROL_EVENTS` 在当前协议上不决定任何一次分类，而名单本身与 SDK 3.3.1 对不齐

- **位置**：`openai_responses_passthrough.py:17-28`（常量与它上面那行注释）、`:135-136`（短路分支）
- **判据**：一个分支只有在能改变结果时才承担它 docstring 声称的职责。
- **证据**。两条独立证据指向同一结论：

  1. **变异 M1**（删掉 `if event.event in CONTROL_EVENTS: return None` 整个分支）→ 9 条测试**全绿**。
  2. **探针**：SDK 3.3.1 的 58 个流事件中，7 个 envelope 事件**没有一个带 `output_index`**（见 finding 02 的枚举），所以走不走这个短路，`_item_of` 都返回 `None`。我另构造了一个带 `output_index` 的合成 `response.created`，此时短路才第一次改变结果——而这个形态上游不产生。

  所以 M1 打不红是**构造性冗余**，不是测试不足：没有任何测试能在不伪造协议的前提下区分两者，要求补测试是错的。

- **名单本身的两处偏差**（事实陈述，不外推）：`response.queued` 在 SDK 3.3.1 的 union 里真实存在，**不在**名单里；`response.cancelled` 在名单里（且 Spec §6.3／§5.2 也列了它），但**不在** SDK 3.3.1 的 union 里——后者只说明 SDK 没有这个类型，不足以断言 Copilot 不发它，故不作为缺陷记。
- **影响**：今天为零。但**采纳 finding 02 之后这份名单就会变成判别式**，届时漏掉 `response.queued` 会让它被判为「无法归属」而持有到 terminal，从它之后的整条流被卡住。所以两条要一起改。
- **建议**：随 finding 02 一并处理时补上 `response.queued`；在此之前，把常量上方那行注释的措辞从「Events that belong to no output item」调整为说明它当前不参与判定、将在 §5 的提交时点与 finding 02 的三态判别里承重。
- **证据强度**：强（变异 + SDK 枚举）。

### `direct-responses-passthrough-skeleton-review-06` — `_closed` 的注释说反了它存在的理由

- **位置**：`openai_responses_passthrough.py:81`
- **判据**：注释写「Kept because a `done` may arrive for an item whose `added` was never seen ... and such an item is closed, not open.」
- **证据**（变异）。孤立 `done` 的场景**根本不经过 `_closed`**：它命中 `push` 的第一分支（`event.event == _ITEM_DONE` → `discard` + `add`），与 `_closed` 里有没有它无关。

  - **M4a**（把 `elif index not in self._closed:` 改成 `else:`，即拿掉 `_closed` 的读）→ 9 条**全绿**，含 `test_a_done_for_an_item_that_never_opened_still_closes_it`。
  - **M4d**（同上，并额外在 else 分支里 `self._closed.discard(index)`，让 `_closed` 彻底失效）→ 9 条**全绿**。

  `_closed` 唯一真正的作用是「一个 `output_index=k` 的事件在 `done(k)` **之后**到达时不要重新打开 k」，这在单次 attempt 的协议里不发生（`output_index` 是 output 数组的位置，`output_item.done` 是该 item 的最后一个事件），在跨 attempt 复用实例时才发生——而那正是 finding 03 里的静默降级。
- **影响**：注释把一个防御分支的理由安在了另一个分支上。读者据此以为「不要动 `_closed`，它守着 done-无-added」，而真正被它守住的是别的东西，且那个东西恰好是 finding 03 的成因。
- **建议**：改成它真实的作用；连带说明它在跨 attempt 复用下会变成缺陷（指向 finding 03 的处置）。
- **证据强度**：强（两个变异实跑）。

### `direct-responses-passthrough-skeleton-review-07` — Framer 的 docstring 说「Holds no state」，而它持有一个计数器

- **位置**：`openai_responses_passthrough.py:142-153`，docstring 第 144 行与字段第 149 行、第 152 行
- **判据**：docstring 逐字「Writes batches out. **Holds no state**, because there is nothing to renumber.」；`written: int = field(default=0)` 且 `self.written += len(batch.events)`。
- **影响**：这句话的**意图**（不持有任何用于重编号的状态）是对的，但它写成的**断言**是假的，而 `dataclass(slots=True)` 加一个可变字段恰恰使这个类不是无状态的。`written` 同时还是一个没有消费者、没有测试、也没有在 Spec §10 的可观测合同里声明过的字段——§10 要求可观测事实是旁路的 typed facts，一个裸计数器算不算它的一部分，本刀没有说。
- **建议**：把断言改成「holds no **renumbering** state」，并给 `written` 一句它服务于谁的说明；若它现在还没有消费者，考虑随 §10 的可观测迁移一起引入而不是先放在这里。
- **证据强度**：强（代码逐字）。

### `direct-responses-passthrough-skeleton-review-08` — 同一条计量规则写了两遍，其中一份没有调用者

- **位置**：`openai_responses_passthrough.py:44-50`（`RawEventBatch.size_bytes`）与 `:116-119`（`ResponsesPassthroughAssembler.held_bytes`）
- **判据**：两处逐字相同的求和式（`len(...event.encode()) + len(...data.encode())`），互不派生。`rg` 确认 `size_bytes` 在 `src` 与 `tests` 里都没有调用者。
- **实测口径差**（用 `history_responses_stream.json` 的 125 个真实事件）：公式给出 51710；实际成帧后上线 53710（**1.04x**）；两个 `str` 对象的 Python 占用 61960（**1.20x**）。**我原本预估的差距要大得多，实测证伪了——在真实 payload 尺寸下这个近似是站得住的**，§8 的「本代理当前持有的字节」不因此不成立。
- **影响**：不是数值问题，是「同一事实两处各写一遍」——§8 的口径将来若调整（例如改为按成帧后计），一处改了另一处不会红。
- **建议**：让 `held_bytes` 由 `RawEventBatch` 的同一实现派生，或在 cap 那一刀落地时删掉没有消费者的那一份。
- **证据强度**：强（代码 + 实测）。

### `direct-responses-passthrough-skeleton-review-09` — `push` 对每个事件解析两次 JSON

- **位置**：`openai_responses_passthrough.py:89-90`

  ```python
  self._queue.append(_Pending(event=event, item=_item_of(event)))
  index = _item_of(event)
  ```

- **判据**：`_item_of` 内部调用 `event.json()`，即对**整个** payload 做一次 `orjson.loads`。两次调用等于每个事件解析两遍，`output_item.done` 携带完整 item 快照时 payload 可以很大。
- **影响**：纯开销，无正确性问题；125 事件的 cassette 上是 250 次解析而非 125 次。
- **建议**：`index = self._queue[-1].item`，或先算一次存进局部变量。
- **证据强度**：强（代码逐字）。

### `direct-responses-passthrough-skeleton-review-10` — §3 的「明确不承诺」清单漏了一类会**截断** data 的行拆分

- **位置**（既有共用代码，**不在本刀 diff 内**）：`src/app/pipeline/delivery/sse_source.py:45`（`parse_frame` 用 `raw.decode(...).splitlines()`）；受影响的承诺在 Spec §3
- **判据**：§3 承诺重放「经 SSE field parsing 得到的 logical `data` 字符串」逐字，并列出了四项明确不承诺；SSE 只把 CR、LF、CRLF 当行结束符。
- **证据**（实跑）。`str.splitlines()` 的断行集是 SSE 的超集。对 `data: {"delta":"a<CH>b"}` 一帧：

  | 字符 | data 是否保真 | 解析结果 |
  |---|---|---|
  | U+2028 LINE SEPARATOR | 否 | `{"delta":"a` |
  | U+2029 PARAGRAPH SEPARATOR | 否 | `{"delta":"a` |
  | U+0085 NEL | 否 | `{"delta":"a` |
  | U+000B VT、U+000C FF | 否 | `{"delta":"a` |

  注意它**不是**「把分隔符换成 `\n`」，而是**整段截断**：后半行没有冒号，`parse_frame` 的 `if not separator: continue` 直接跳过它。截断后的 payload 也不再是合法 JSON，于是又会撞上 finding 02 的误判路径。

- **触发面的诚实界定**：U+000B 与 U+000C 在合法 JSON 里必须转义，**不可能**以裸字节出现；真正有活性的是 U+2028、U+2029、U+0085——这三个在 JSON 字符串里裸出现是合法的，是否真的从 Copilot 出来取决于上游的 JSON 编码器。**机制已实跑证实，触发未证实。** 这个权重足以支撑「修 §3 的不承诺清单」，不足以支撑「生产上正在丢数据」。
- **建议**：二选一——(a) 在 §3 的「明确不承诺」里补这一条（最小动作，且它是 Spec 该记的事实）；(b) 把 `parse_frame` 的行拆分换成只认 CR／LF／CRLF 的正则（`_FRAME_SEPARATOR` 旁边已有现成写法），这是一处正确性改进且成本很低。两者不互斥，我倾向都做。
- **证据强度**：机制强，触发弱（已分别标注）。

---

## nit

### `direct-responses-passthrough-skeleton-review-11` — 「The three cassettes in this repository」的计数不精确

- **位置**：`tests/unit/pipeline/delivery/test_responses_passthrough.py:95`
- **事实**：`tests/int/cassettes/` 下有 **5** 个 cassette 文件，其中带 Responses 事件流的是 3 个（另两个是 Anthropic 下游流与一个非流式）。Spec §4 用的也是「三份」，而 §5.2 用的是「五份」——两处指的不是同一个集合。
- **建议**：写成「the three Responses-stream cassettes」。实质结论（三份都不交错、`output_index` run 均为 `[0, 1]`）我已独立复核为真，见 finding 04 的表。

---

## 主观建议（不占 severity 档位）

- **`_take_safe_prefix` 目前是每次从队列头重扫，复杂度 O(n²)。** 在 `block` 下 n 是未释放长度、通常个位数；在将来的 `full` 下 n 是整个响应。125 事件的 cassette 上完全无感，长响应上也只是微秒量级。**预期影响：可忽略。** 记在这里只是为了让 `full` 那一刀落地时不必重新发现它。
- **`unfinished` 每次调用都重算并新建 tuple。** 它在收口路径上只会被调用一次，无需改。同上，只是备案。

---

## 变异验证结果

纪律：变异前把源文件 `cp` 到 worktree 之外的 `/tmp/passthrough-review-snapshot/`（sha256 已比对一致），每次变异**在同一次 Bash 调用内**完成「改 → 跑 → 用快照还原 → 数脏文件」，不放后台。全部 12 次变异后 `git status --short` 均为空。

| # | 变异 | 打红？ | 归因 |
|---|---|---|---|
| M1 | `_item_of` 删掉整个 `CONTROL_EVENTS` 短路分支 | **否**（9 passed） | **构造性冗余**。SDK 3.3.1 的 7 个 envelope 事件无一携带 `output_index`，走不走短路结果都是 `None`。要打红只能伪造一个带 `output_index` 的 `response.created`，那不是协议里的形态。**不是测试不足，补测试是错的。** 见 finding 05 |
| M2 | `_item_of` 只认三个已知事件名（复现历史上那次全绿变异） | **是**（`test_an_unknown_event_is_grouped_with_its_item_not_treated_as_envelope` 红） | 新补的那条测试确实修复了鉴别力；提交信息里「八条全绿」的自述与我的复现一致 |
| M3 | `_take_safe_prefix` 的 `break` 改 `continue` | **是**（4 红） | 保序判据有覆盖 |
| M4a | 拿掉 `_closed` 的读（`elif ... not in self._closed` → `else`） | **否**（9 passed） | **测试不足与构造性保证各占一半**：单次 attempt 内「`done(k)` 之后还有 `output_index=k` 的事件」不发生（构造性），但**跨 attempt 复用实例时发生**，且后果是 finding 03 的静默降级。所以缺的不是这条变异的测试，而是 finding 03 的处置——定下 per-attempt 生命周期之后，这条变异就应当保持不红 |
| M4b | 把 `_open.discard` 与 `_closed.add` 两行对调 | **否**（9 passed） | **构造性保证**。两个不同的 `set`，无别名关系，顺序对调是纯 no-op。任何测试都不可能、也不应该抓它 |
| M4c | 把分支重排成「done 也会先打开 item」 | **是**（7 红） | 分支顺序的语义有覆盖 |
| M4d | 让 `_closed` 彻底失效（else 分支里再 `discard`） | **否**（9 passed） | 同 M4a。这一对变异是 finding 06 的直接证据：`_closed` 守的不是它注释里说的那件事 |
| M5 | `encode` 改成每个事件只写一条 `data:` 行 | **是**（`test_the_framer_writes_the_payload_it_was_given` 红） | 多行 payload 的保真有覆盖，与 `7e96adc` 的修复对得上 |
| M6 | `encode` 丢掉 event 名 | **是**（同上一条测试红） | event 名的保真有覆盖 |
| M7 | `unfinished` 返回整个队列 | **是**（`test_control_events_keep_their_place_in_the_queue` 红） | 未闭合尾巴的判据有覆盖 |
| M8 | `held_bytes` 去掉 event 名那一项 | **否**（9 passed） | **测试有意不钉数值，且不钉是对的**。该测试钉的是「入队则计、释放则归零」这个形态，数值组成不是本刀的失败面（cap 是后续刀）。按项目规则不追覆盖率，此处**不作为测试缺口**；口径本身的问题另记为 finding 08 |
| M9 | 空前缀返回空 batch 而非 `None` | **是**（3 红） | 「无可交付时不产出批次」有覆盖 |

**控制变异**：本轮有 7 次打红、5 次不红，红与不红出自同一条命令、同一个 pytest 入口，所以「不红」不可能是「测试根本没跑起来」——这一族假绿已被排除。

**结论**：5 次不红中，**3 次是构造性保证**（M1、M4b，以及 M4d 与 M4a 在单 attempt 内的那一半），**1 次是有意不钉的数值**（M8），**1 次指向的是设计缺陷而非测试缺陷**（M4a／M4d 的跨 attempt 那一半 → finding 03）。**没有一条应当靠补测试来关闭。** 本刀测试的鉴别力，就它声称覆盖的那几件事而言，是够的；漏掉的是 finding 01 与 02 那两类**从未被构造过的输入形态**（较早 item 先关闭的交错顺序、不带 `output_index` 的 item 事件），那是判据没想到，不是变异没打到。

---

## 考虑过但否决的候选发现

逐条写下，因为纯推理排除掉的路线事后捞不回来。

1. **「给 `_item_of` 加一张 item 类型表来处理未知事件」** —— 否决，且是本主题的禁令。天花板正是这样重建的。finding 02 的建议特意绕开了它：只区分「已知信封 vs 其他」，未知 item 事件仍然无须被认识。
2. **「`output_index` 在同一响应内被复用」** —— 否决为独立发现。协议里 `output_index` 是 output 数组的位置，单次响应内不复用；真正会复用的是跨 attempt，已并入 finding 03。
3. **「`encode_frame` 对含 `\r` 的 data 会丢内容」** —— 在本腿**不可达**。data 来自 `parse_frame`，`splitlines()` 已经把 CR 消掉了，逻辑 data 里不可能有裸 `\r`。（`encode_frame` 的其他调用方是否会传含 `\r` 的 data，属于 `_report_failure` 那条路，不在本次范围。）
4. **「空 event 名不写 `event:` 行是保真缺陷」** —— 否决。实跑核过往返：`encode_frame("", d)` 产出 `data: d\n\n`，重解析 event 名为 `""`；上游写 `event: `（空值）重解析同样是 `""`。两者语义等价（SSE 里都退化为默认类型），§3 已明确不承诺 byte-level，故不成立。
5. **「CRLF 没被保留」** —— 否决。§3 的「明确不承诺」逐字列了行尾规范化。
6. **「`held_bytes` 的具体数值没有测试钉住」** —— 否决为发现。项目规则明确不追覆盖率、不预建状态空间，cap 是后续刀；见 M8 的归因。
7. **「`RawEventBatch` 应该复用 `SseFrame`」** —— 反向否决。§3 要求 payload 按原文回去，`SseFrame` 走 `orjson.dumps` 会保住字段而保不住字节，模块的 docstring 对这一点的说明是对的。
8. **「骨架未实现 replay／headers／policy／cap 是缺陷」** —— 否决。plan.md §8 的步骤划分明确把它们放在后续刀，模块 docstring 也逐条声明了。我只检查了它有没有**偷偷替后续刀做决定**：final ending 没做（`unfinished` 暴露而不丢，全模块只有一处删队列且删的是已释放前缀）、headers 没碰、replay 没碰、policy 只实现了 §7 定为默认的 `block` 且已声明。**唯一越界的是 `_closed` 的永久性替 §5 的 attempt 重置做了决定**，已单列为 finding 03。
9. **「`_take_safe_prefix` 的 O(n²) 重扫」** —— 降级为主观建议，不作为发现：实测量级可忽略，且没有 Spec 条款被违反。
10. **「`error` 事件在 §8 下的处置没实现」** —— 否决，后续刀（§8 的 proxy error 属于 ending 决定）。
11. **「应该加一道 gate／覆盖率门／验收状态机来守住这些判据」** —— 否决。项目明确禁止为证明而搭证明设施；本报告只给判据与测试建议，不建议任何阻断装置。
12. **「`ResponsesPassthroughFramer` 是不是根本不需要存在（`batch.encode()` 已经够了）」** —— 考虑过，否决为发现。plan.md §3 明确要一个透传 framer 作为与 `ResponsesFramer` 并列的位置，且它是 `written` 这类可观测事实将来的挂载点。它现在薄，但薄不等于错；`written` 本身的问题已记为 finding 07。

---

## 搜索面

**读过**：`spec.md`（全文 318 行）、`plan.md`（全文）、被评的两个新文件（全文）、`src/app/pipeline/delivery/sse_source.py`（全文）、`src/app/pipeline/delivery/blocks.py` 的 `CompletedBlock`／`BlockBuffer` 计量部分、`src/app/pipeline/delivery/formats/openai_responses.py` 的 `_item_key`／`_open`／`_close`、`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md` 的 §6.3 与 §12 未闭合项表、若干相关评审报告。

**跑过**：`uv run pytest tests/unit/pipeline/delivery/test_responses_passthrough.py`（基线 9 passed）、`uv run pytest tests/unit/pipeline/delivery`（184 passed）、`uv run ruff check src tests`（clean）、`uv run pyright src tests`（0 errors）、12 次变异（见上表）、6 个行为探针（交错顺序、跨 attempt 复用、无法归属事件的两个泄漏点、`CONTROL_EVENTS` 的判别条件、`parse_frame`／`encode_frame` 往返）、`ResponseStreamEvent` union 的 58 成员枚举、三份 Responses cassette 的全量事件解析。

**没看的面**（据此不作任何断言）：`delivery_policy` 与 `stream.py` 的 ending 分支（本刀未接线，接线那一刀需要单独评审，尤其是 finding 01／02 落地后的收口顺序）；非流式路径；headers；`tests/int/` 的集成层；`ResponsesAssembler` 翻译腿的正确性；Spec 自身除本报告点名的两处歧义（§4 的释放判据、§3 的不承诺清单）之外的产品裁决。

**没做变异验证的面**：`RawEventBatch.size_bytes`（无调用者）、`ResponsesPassthroughFramer.written`（无消费者）——两者都没有可失败的下游，变异无意义，已在 finding 07／08 里点名。

# 直连路径原生透传产品规格独立复评（round 9）

> **落盘位置说明（非正文）**：调用方指定路径是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260831-review-spec-round9.md`，`Write` 被 harness 的 bg-isolation 守卫拒绝（原文见「限制」一节）。按调用方预案落 `/tmp`，请搬运：
>
> `cp /tmp/ghc-review-r9/260831-review-spec-round9.md /home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/`

- report_id：`direct-passthrough-spec-review-round9`
- attempt_id：`260831-review-spec-9`
- reviewed_at：2026-08-31
- 被评对象：`.dev/docs/direct-passthrough/spec.md`（文首自称 DRAFT v10，调用方称 v12 —— 这个不一致本身是本轮发现之一）、同目录 `plan.md`（v10）与 `deferred.md`（D-1～D-5）
- 被评快照：`.dev` HEAD `68a95b3`、主仓 HEAD `01c33f1`、实现分支 `worktree-260831-passthrough-wiring` HEAD `b9195f4`。三者本轮用 `git log --oneline`／`git show --stat`／`git show <sha> -- <path>` 独立核过，与调用方给出的一致
- 评审性质：只读。未修改 `src/`、`tests/`、`spec.md`、`plan.md`、`deferred.md`；未 `git commit`／`push`；未调用真实上游；未触碰 4141 服务；未派 agent；未 `EnterWorktree`

## 评审范围

按 `as-reviewer` 的两问分开走。第一问核 round8 十三条的逐条完成度；第二问**抛开那份清单**重新判当前状态，重点按调用方指令压在 v10／v11／v12 三次修订动过的那一层——定义域。

**在范围内**：`spec.md` 全文 495 行、`plan.md` 全文 133 行、`deferred.md` 全文 87 行；判据来源为 `docs/.human-controlled/message-format-reshape.md`／`config.example.yaml`／`upstream-retry-and-continuation.md`／`client-side-block-delivery.md`（引文所在段逐字回核）、`.dev/docs/error-envelope/spec.md` §3.1、`.dev/docs/sync-refs/sxwxs-ghc-api/260822-round2-disposition.md`；代码面逐行读了实现分支的 `pipeline/delivery/passthrough.py` 全文（314 行）、`formats/openai_responses_passthrough.py` 全文、`formats/anthropic_messages_passthrough.py` 全文、`pipeline/delivery_policy.py` 全文、`pipeline/delivery/blocks.py:40-150`、`pipeline/delivery/stream.py:275-330`／`:380-420`／`:450-620`、`pipeline/hand_over.py:222-260`、`pipeline/routing.py` 的 `supports` 面、`server/routes/table.py` 的 embeddings 行；以及实现分支的 `tests/int/test_error_envelope.py:470-525` 与 `tests/unit/pipeline/delivery/test_responses_passthrough.py` 的 failure 用例。

**明确不在范围内**：`anthropic-responses-bridge/spec.md` 与 `error-envelope/spec.md` 本体（只按引用核一致性）；翻译腿 `ResponsesAssembler`／`AnthropicAssembler` 的正确性；实现分支 `b9195f4` 的整体代码质量（本轮只在它与 Spec／Plan 的断言冲突处触碰，且这类发现会显式标注「实现侧」）；真实上游行为的发生率；前八轮报告的内文（按调用方说明，其中旧绝对路径是时点记录，本轮不核不改）。

## 总体 verdict

**needs-fix。blocker 1、major 5、minor 6、nit 4（finding_total 16）。**

**round8 十三条：closed 13、partially-closed 0、not-closed 0。** 逐条判据见第一节，我逐条回到 v12 原文核过，不采信自述。

**第二问的答案与前几轮同形，而且这次更重：新问题几乎全部由 v10～v12 这三次修订自己带进来。** 调用方点名要审的三处里，两处的推理站得住而措辞或引用不准（§2.6、§2.8），一处的核心断言可以被逐字证伪（§2.5 的「六行词汇」与「句子里没有一个 Responses 专有的事实」）。**最高优先级那一问的答案是「不穷尽」，而且不是理论上的不穷尽——实现自己已经有第七、第八项词汇，Spec 的表里没有。**

**另外两件事必须先说，因为它们改变读者要不要停下来的判断：**

1. **§2.5 的 Anthropic control 事件集漏了 `message_stop`。** 照那张表实施，每一条 Anthropic 直连响应都会永久挂住不结束（round9-01）。实现已经偏离该表把它加了回去，所以今天 Spec 与代码在这一格上不一致，而不一致的那一侧是 Spec。
2. **`spec.md` 没有 v11／v12 的修订记录，文首状态行仍写「DRAFT v10」。** 项目硬规则要求每次修订记入规格自己的修订记录，`spec.md` 第 9 行也是这么自我要求的。两次改动了产品裁决面的修订（§2.7 的整形通则、§2.8 的暂不接线）目前在 §12 里查不到（round9-03）。

---

## 一 · round8 十三条逐条完成度

| finding_id | round8 级别 | 状态 | 判据（对 v12 原文核过） |
|---|---:|---|---|
| `round8-01` | blocker | **closed** | §7.2 收口第 3 步（`spec.md:359`）已换成单一谓词「收口时刻没有任何已打开而未闭合的 item」；`:362-378` 六段说明重写，其中 `:364` 逐字点破 v8 论据句「不再有 X 之外的解释」说反了，`:368` 写出根因（§4 把两类事件并进同一个桶），`:376` 把四层触发面按权重分开并明说支撑本裁定的是 (d) 不是 (a)。§11 `:473` 已改为「v8 关闭过一项又在 v9 重裁」。**未采纳的那半条（代理侧 ending 一律丢弃）在 `:372` 写明了不采纳的理由**，符合 `record-what-not-adopted`。骨架侧那份代码转抄也已拆掉：`passthrough.py:272` 现在写「this property deliberately does not say what that answer is」并解释了为什么不转抄 |
| `round8-02` | major | **closed** | §6.2 `:279` 已改为事实陈述并逐字引用用户 `config.example.yaml` 里的 `@ai-sdk/openai`；`:283` 新增「回归是具体的」整段；`:285` 写明「在本腿不是纯粹的将来事项」；产品分叉登记进 `deferred.md` D-3。`:287` 保留了「未核」限定（`@ai-sdk/openai` 的具体版本与校验方式） |
| `round8-03` | major | **closed** | `plan.md:54` 已改为纯引用：「照 Spec §7.2 的四步执行，本文件不复制」，并解释了「漏写不构成冲突」为什么救不了转抄 |
| `round8-04` | major | **closed** | `plan.md:122` 的 v7 判据已收窄为「断言它被**持有**而不是随 envelope 释放，且它与未闭合尾巴**分列两个集合**——ending 处的去向不归这条判据，见下面 v9 那条」，与 `:128` 的 v9 判据不再冲突 |
| `round8-05` | minor | **closed** | §9.1 `:432-437` 已按两侧重写，明确「名单没点名而本规格要剥的」那一侧确实偏离且数不完，并标注该侧理由属本规格推导；§11 O-1（`:471`）同步为两侧 |
| `round8-06` | minor | **closed** | §8 `:397` 已如实陈述用户注释是双语的、两半读法不同，并写明「本规格取当前持有这一读」属 §2.3 推导，附「若用户裁定取累计读法，本节与 §7.2 的 `full` 行为都要重估」 |
| `round8-07` | minor | **closed** | §3 `:130` 已按新基准逐条重述五项身份（第 1 项声明、第 2 项真实取舍、第 3／4 项与规范一致、第 5 项是基准算法自身），`:132` 另起一段警告不要把「与规范一致」那两项当成待补欠缺 |
| `round8-08` | minor | **closed** | `:136` 与 `:138` 的步号都已是「第 3 步」；§3 承诺面 `:138` 补上「同时覆盖按 §7.2 收口第 3 步被提交的无法归属事件」 |
| `round8-09` | minor | **closed** | `plan.md:126` 已补条件性：「**这半条的方向取决于 Spec §11 O-1，用户裁「名单不覆盖本腿」时须整条反转**；weak `ETag`／`Last-Modified` 在输出里，这半条与裁决无关」 |
| `round8-10` | nit | **closed** | P3 已合入 `main`（`109dc44`），§3.1 第三条 `:166` 现为「**已实现（`109dc44`）。**」，与文首、`plan.md:17` 同口径 |
| `round8-11` | nit | **closed** | `:144` 已改为「三份 **Responses 流** cassette」，与 `:193` 同措辞 |
| `round8-12` | nit | **closed** | `:428` 已从「完全相同」改为「超集」；`:426` 已点破 `Hop-By-Hop` 是类别标记不是头名。**但这条修复在 v10 放宽定义域之后本身变成了假命题，见 round9-04** |
| `round8-13` | nit | **closed** | 「不含冒号的 `data` 行」已进 §3「明确不承诺」（`:158`），并写明「这是相对新基准的一处真实偏差」「机制确定、触发未测」「权重只够登记」 |

状态计数：`closed=13`、`partially_closed=0`、`not_closed=0`。

**一句提醒**：`round8-12` 记为 `closed` 而不是 `not-closed`——v9 采纳的文字在 v9 那个定义域下是对的。它在 v10 变假，属于**新缺陷**而不是旧缺陷未闭合，所以计在 round9-04 而不是回退这一格。这个区分不是修辞：把它记成 `not-closed` 会让读者以为上一轮的处置有问题，而实际问题是**放宽定义域时没有回头扫一遍所有以旧定义域为前提的句子**。

---

## 二 · 语义槽扫描（在 round8 那张表之上，补 v10～v12 新增的事实）

判定列只答「这个事实是不是只剩一处当前指令」。

| 事实 | 权威处 | 复述处 | 判定 |
|---|---|---|---|
| **本规格的定义域** | `spec.md:5`（任何 `translation_required is False` 的路由） | §9.1 `:428`（**仍写「本规格还要求两端同为 `openai-responses`」**）、§11 O-1 `:471`（**只问 Responses 客户端的直连腿**）、`plan.md:27`（**仍以「两端同为 `openai-responses`」定义分流点**）、`plan.md` 与 `deferred.md` 的文档标题 | **有问题**：三处窄读的旧句 ＋ 两处窄标题（round9-04、round9-11、round9-13） |
| **方言专有的词汇有哪几项** | §2.5 的表（六行） | 实现 `passthrough.py:34-55` 的 `Dialect`（**八个字段**）及其 docstring（**自称 six facts**） | **有问题**：`read_failure`、`name` 两项不在表里，代码 docstring 已落后于自己的字段（round9-02） |
| **Anthropic 的 control 事件集** | §2.5 表第一行 | 实现 `anthropic_messages_passthrough.py` 的 `CONTROL_EVENTS`（**多一个 `message_stop`**） | **有问题**：Spec 缺项且按 Spec 实施会挂死（round9-01） |
| **native failure 如何进 retry taxonomy** | §5.1 第一行 ＋ §5.2 的表 | `plan.md:60`（只引不抄，正确）、`plan.md:86`（**声称已完成**） | **有问题**：权威处整段是 Responses 专有词汇且无 Anthropic 对应（round9-02）；实现根本没有这条通路而 plan 记为已完成（round9-05） |
| **重开 attempt 的三类结果** | §5.2 的表（`OpenedAttempt`／`AttemptFailed`／`ReopenRefused`） | `plan.md:60`、`plan.md:86` | **有问题**：实现的 `ReplaySupport.reopen` 是 `Attempt | None` 两值（round9-05） |
| **接线覆盖哪几条腿** | §2.6 ＋ §2.8 | `plan.md:89`（第 8 步，Anthropic 未接线）、`plan.md:95`（**「接线覆盖所有直连腿，不只 Responses」，并复述 v11 已替换掉的 §2.6 论据**） | **有问题**：同一文件两处相反（round9-10） |
| **Responses 腿今天接没接线** | `plan.md:4`（已接线，在分支 `b9195f4`） | `spec.md:4`（**「主体（接线）未开始」**）、§2.6 Responses 行 `:90`（**「引擎已建，未接线」**） | **有问题**：v12 更新了 §2.6 的 Anthropic 行却漏了同表的 Responses 行（round9-11） |
| **hand-over 的门在哪** | 实现 `hand_over.py:238`（`wire_format is not ANTHROPIC_MESSAGES`） | §8 `:395`（**写对了，`hand_back_block()`**）、§2.8 `:99`／`:107` 与 `deferred.md:72`／`:84`（**写成 `hand_over_supported`，该符号不存在**） | **有问题**：同一机制两个名字，其一虚构（round9-08） |
| **「§5 第四行」指哪一行** | §5 提交表（第四行是「第一批 item 事件」） | §2.5 表第二行、§2.8 `:101`、`passthrough.py:44`、`openai_responses_passthrough.py:34` | **有问题**：指向的应是第五行（terminal 行），且已转抄进两个源文件（round9-09） |
| **接线不得改变已生效的整形默认值** | §2.7 `:122` | `deferred.md` D-4 `:59`、`anthropic_messages_passthrough.py` 模块 docstring | 一致 |
| **Anthropic 直连腿为什么暂不接线** | §2.8 | `deferred.md` D-5、`plan.md:4`／`:89`、`delivery_policy.py:62` | 一致（**论证本身有两处不准，见 round9-07**） |
| **Chat Completions 直连腿的状态** | §2.6 第三行 | `delivery_policy.py:47`／`:64`、`stream.py:246` 的 `one_shot_delivery` docstring | **有问题**：§2.6 只回答了 §2.1，没说 §5／§8／§9.1／§10 在那条腿上今天全部不成立（round9-12） |
| 「无法归属」事件的处置 | §7.2 收口第 3 步 | §3:136／:138、§4:189、§11:473、`plan.md:128`、`passthrough.py:269-276` | 一致（round8-01 的修复已完整传播，含代码侧的去转抄） |
| 响应头取交集 | §9.1 | §11 O-1、`plan.md:66`、`plan.md:126` | 一致（**但共同的定义域前提已过期，见 round9-04**） |

---

## 三 · 本轮发现

### blocker

#### `direct-passthrough-spec-review-round9-01`

- finding_id：`direct-passthrough-spec-review-round9-01`
- severity：`blocker`
- primary_location：`spec.md:77`（§2.5 表第一行，`anthropic-messages` 列）
- related_locations：`spec.md:78`（同表第二行，terminal 事件集）、`spec.md:189`（§4「无法归属」的处置）、`spec.md:359`（§7.2 收口第 3 步）；实现 `src/app/pipeline/delivery/formats/anthropic_messages_passthrough.py` 的 `CONTROL_EVENTS`、`src/app/pipeline/delivery/passthrough.py:199-203`（`_item_of`）、`:205-212`（`_is_barrier`）
- 标题：§2.5 的 Anthropic control 事件集漏了 `message_stop`，而同表下一行又说 terminal 是 control 的子集；照这张表实施，每一条 Anthropic 直连响应都会因为终局事件被判为「无法归属」而永久挂住

**Spec 逐字。** `spec.md:77`（control 事件集，`anthropic-messages` 列）：

> `message_start`、`message_delta`、`ping`、`error`

`spec.md:78`（terminal 事件集，同一列），以及该行「它回答什么」列的措辞：

> 哪些 **control 事件**结束响应（§5 第四行据此解除持有） | …… | `message_stop`、`error`

**表在自己的术语上就不自洽。** 第二行明说 terminal 是 control 事件的子集，而它列出的 `message_stop` 不在第一行的 control 集合里。

**后果不是措辞问题，是挂死。** 引擎按 `_item_of` 归属一个事件（`passthrough.py:199-203`）：

```python
if event.event in self._dialect.control_events:
    return Attribution.ENVELOPE
payload: dict[str, Any] = event.json()
index = payload.get(self._dialect.item_index_field)
return index if isinstance(index, int) else Attribution.UNATTRIBUTED
```

Anthropic 的 `message_stop` 的 payload 是 `{"type":"message_stop"}`，**不带 `index`**。所以按 Spec 的表实施时它落进 `UNATTRIBUTED`；而 `_is_barrier`（`:205-212`）对 `UNATTRIBUTED` 一律返回 `True`，即它是一道屏障，前缀在它之前截断、它自己永不释放。于是：

- 该响应的终局事件永远不会交付给客户端；
- §7.2 的收口要靠「最终 ending 到达」触发，而这条腿上唯一的正常 ending 就是它；
- 客户端拿到一个开着的 SSE 流，直到 idle guard 或 deadline 把它砍掉。

**实现已经偏离 Spec 绕开了它。** `anthropic_messages_passthrough.py` 的 `CONTROL_EVENTS` 是 `{message_start, message_delta, message_stop, ping, error}`——**五个，比 Spec 多一个 `message_stop`**。所以今天代码是对的、Spec 是错的，两者在这一格上不一致。这正是项目规则里点名的那一类：**Spec 是本规格自己推导的映射表，实现与它不符时要判是谁错了**；这里错的是表，按评审共识改即可，不必升级给用户（§2 的 provenance 划分把「方言词汇」归在 §2.3 的推导层）。

**为什么是 blocker 而不是 major。** 三条理由叠加：(a) 它是一条会产生错误用户可观察行为的规范条款，不是描述精度问题；(b) 它落在 §2.5——v10 放宽定义域之后**唯一**规定方言专有事实的那张表，也是下一个实现者写第三份词汇时唯一会读的东西；(c) 它今天已经造成 Spec 与代码不一致，而不一致的方向是「代码悄悄修了 Spec」，这种偏离不修就会在下一轮被当成实现缺陷反向「修」回去。

**建议。** §2.5 表第一行 `anthropic-messages` 列补上 `message_stop`，并在表下加一句显式规则：**terminal 事件集必须是 control 事件集的子集**——这条约束今天只活在第二行的「哪些 control 事件」这个措辞里，而两列分开填时没有任何东西会拦住漏填。Responses 那一列已经满足（`completed`／`incomplete`／`failed`／`cancelled`、`error` 都在第一行里），所以补这一句不改 Responses 的任何内容。

**证据强度：强到可以据此行动。** Spec 两行逐字对读，冲突可数；实现三处（`CONTROL_EVENTS`、`_item_of`、`_is_barrier`）逐行读过；「`message_stop` 不带 `index`」来自 Anthropic Messages SSE 的事件形状，且实现自己的注释（`anthropic_messages_passthrough.py` 的 `TERMINAL_EVENTS` 上方）逐字写着这条腿「splits its ending across two events」。**未实跑**——按调用方边界我不在实现 worktree 跑 pytest；但这条不需要实跑，因为它是「Spec 与代码逐字不同」，两侧文本都在上面。

---

### major

#### `direct-passthrough-spec-review-round9-02`

- finding_id：`direct-passthrough-spec-review-round9-02`
- severity：`major`
- primary_location：`spec.md:71`（§2.5「句子里没有一个 Responses 专有的事实」）
- related_locations：`spec.md:73-83`（六行词汇表）、`spec.md:223`（§5.1 第一行）、`spec.md:234-239`（§5.2 归一化表）、`spec.md:349-353`（§7.2 final source 表）、`spec.md:393`（§8 第一条）、`spec.md:394`（§8「写 Responses `event: error`」）、`spec.md:395`（§8「`status: "incomplete"` 的 item」）、`spec.md:405`（§9「合法 Responses JSON object」）、`spec.md:461`（§10「原生 output item 计数」）；实现 `src/app/pipeline/delivery/passthrough.py:34-55`（`Dialect` 的八个字段与自称 six facts 的 docstring）
- 标题：**这是调用方最高优先级那一问的答案：六行词汇不穷尽。** 实现自己已经需要第七项（`read_failure`）与第八项（`name`），而 §2.5 声明为方言无关的 §5／§7.2／§8／§9／§10 里，至少有六处逐字的 Responses 专有事实

**§2.5 的断言逐字。** `spec.md:71`：

> §3 的保真层级、§4 的交付单位与全局顺序、**§5 的 commit frontier 与 replay**、**§7 的三种 policy 与收口顺序**、**§8 的失败与容量**、**§9／§9.1 的非流式与响应头**、**§10 的可观测合同**——它们描述的是「一条不翻译的腿如何交付」，**句子里没有一个 Responses 专有的事实**。

**反例一（最重的一处）：§5.2 整节。** `spec.md:234-239` 的归一化表四个输入分别是 `response.cancelled`、`code == "server_error"`、`code == "rate_limit_exceeded"`、`code == "vector_store_timeout"`，并在 `:241` 逐字说明依据是「`openai==3.3.1` 的 `ResponseError.code` 是一个 20 成员的 `Literal`」。**Anthropic 的错误事件根本没有 `code` 这个字段**——它的形状是 `{"type":"error","error":{"type","message"}}`，`type` 取 `overloaded_error`／`rate_limit_error`／`api_error` 这一族。所以 §5.2 的表对 Anthropic 直连腿**一行都不适用，也没有任何对应表**，而 §5.1 第一行（`:223`）又把可 replay 的判定完全押在这张表上。这不是措辞问题：**它是 §2.5 号称通用的那部分里唯一一处规定了「怎么算」的地方，而那个算法只对一种方言存在。**

**实现已经证明了这一点，而且证明得比我更早。** `passthrough.py` 的 `Dialect` 有**八个字段**：

```
name, control_events, terminal_events, item_done_event,
item_index_field, requires_client_action, read_terminal, read_failure
```

其中 `read_failure`（注释：「Upstream's own failure event, as a failure record, or `None` when this event is not one.」）在 §2.5 的表里**没有对应行**，两份方言各给了自己的实现（`responses_failure_from` 与 `anthropic_failure_from`）。`name`（注释：「What the completion line and the observability record call this leg.」）同样不在表里，它服务的是 §10。**所以「方言专有的只有一份词汇」这句话是对的，「那份词汇是六行」这句话是错的，今天至少是八行。**

**同一份代码的 docstring 已经落后于它自己的字段**：`passthrough.py:35` 逐字写着「The six facts about one wire format that the engine cannot derive.」并以 §2.5 为权威。这是 Spec 转抄进代码之后没有跟上的标准形状——加字段时没有人回头数那句话。

**反例二：§7.2 的 final source 表**（`:349-353`）。五行里四行以 `response.completed`／`response.incomplete`／`response.cancelled`／`failed`／`error` 为键。Anthropic 侧没有 `incomplete` 与 `cancelled` 这两个终局——它把「因为没地方了而停」放在 `message_delta` 的 `delta.stop_reason` 里（§2.5 表最后一行自己就是这么写的）。所以这张表在 Anthropic 腿上要么合并成两行，要么要读一个完全不同的位置。

**反例三～六（较轻，但同属一族）**：§8 `:393` 的失败事件枚举、`:394` 的「写 Responses `event: error`」、`:395` 的「`status: "incomplete"` 的 item」（Anthropic 的 content block 没有 `status` 字段）、§9 `:405` 的「合法 **Responses** JSON object」、§10 `:461` 的「原生 **output item** 计数」（Anthropic 叫 content block）。这几处单看都可以说是「举例用了 Responses 的名字」，但 §2.5 的断言是全称否定（「一个都没有」），全称否定被单个反例证伪，何况这里有六个。

**影响。** 三层，第二层最贵：

1. **文本权威**。一句被证伪的全称断言，会让下一个读者相信「§5～§10 直接照抄就能服务第三种方言」，而事实是 §5.2 那张表得整个重写一份。
2. **待办面**。§2.5 是 v10 放宽定义域时**唯一**用来说服读者「放宽的代价可控」的论据。论据不成立，代价就没有被算过——具体地说，**没有任何文档登记「Anthropic 直连腿需要一份自己的 failure→RetryReason 映射」这件事**，`deferred.md` 五条里也没有。按 `no-silently-cut-but-defer`，这是一个中途发现的、与当前任务直接相关的缺口，不应该只活在这份报告里。
3. **实现**。`Dialect` 的 docstring 与 §2.5 现在互相引用且两边都说「六」，改一边就必须同刀改另一边。

**建议。** 三件事，都不需要用户点头（§2.5／§5／§7.2 全部落在 §2.3 的「本规格推导」层）：

1. §2.5 的表补两行：**upstream failure 事件的读法**（Responses：`response.failed`／`cancelled`／`error` ＋ `ResponseError.code`；Anthropic：`event: error` ＋ `error.type`）与**这条腿在完成行／可观测记录里的名字**。同刀改 `passthrough.py:35` 的「six facts」。
2. `spec.md:71` 那句改为可兑现的说法，例如「§3、§4、§7 的交付机制与方言无关；§5.1／§5.2、§7.2 的 final source 表、§8 与 §9 的部分条款目前只写了 Responses 一种方言的取值，第二种方言落地前须各补一份，见 §2.5 的表」。
3. **登记一条待办**：Anthropic 直连腿的 failure→`RetryReason` 映射表尚不存在。它不是产品分叉（不需要用户裁），所以归 `deferred.md` 而不是 §11。

**证据强度：强到可以据此行动。** §2.5 的断言与六处反例全部逐字对读；`Dialect` 的八个字段与两份方言的 `read_failure` 实参逐行读过；「Anthropic 错误事件没有 `code`」来自实现自己的 `anthropic_failure_from`（`formats/anthropic_messages.py:373-398`，读的是 `data["error"]["type"]`），不是我的记忆。**未核的一项**：Anthropic 的 `error.type` 取值全集我没有去 Anthropic 官方文档逐条核，上面举的三个来自本仓已有代码与注释；这不影响「两份方言需要两张表」这个结论，只影响将来那张表怎么填。

---

#### `direct-passthrough-spec-review-round9-03`

- finding_id：`direct-passthrough-spec-review-round9-03`
- severity：`major`
- primary_location：`spec.md:481-495`（§12 修订记录，最新一行是 v10）
- related_locations：`spec.md:4`（文首「**DRAFT v10 — 待复评**」）、`spec.md:9`（「新裁决、实测或发现与本文冲突时当场修订，**每次修订记入 §12**」）、`spec.md:97`（§2.8 排在 §2.7 之前）、`.dev` 提交 `1cfa309`（新增 §2.7）与 `68a95b3`（新增 §2.8）
- 标题：v11 与 v12 两次修订都没有进 §12，文首状态行仍写 v10；而这两次修订恰恰是三次里唯二改动了**产品裁决面**的（§2.7 的「接线不得改变已生效的整形默认值」、§2.8 的「Anthropic 腿暂不接线」）

**事实可数。** `rg -n 'v11|v12' spec.md plan.md deferred.md` 返回空集。§12 最新一行是 v10，文首第 4 行是「**DRAFT v10 — 待复评**」。而 `git show 1cfa309 -- docs/direct-passthrough/spec.md` 与 `git show 68a95b3 -- docs/direct-passthrough/spec.md` 显示这两次提交各新增了一整节正文（§2.7 十九行、§2.8 十二行），两节都以「**本规格裁定**」「**因此……不进行**」的语气写下了新的规范性要求。

**为什么这是 major 而不是 nit。** 项目 `CLAUDE.md` 的规则原文：

> Every amendment is logged in the Spec's own revision record — what changed, why, and what triggered it — and **that record is what makes a living Spec auditable; it replaces freezing as the way to answer "what did we commit to when this code was written"**。

这条规则的整个价值在于「活文档可审计」这一条件，而条件的兑现方式就是修订记录。两次未登记的修订让「这段代码写的时候我们承诺了什么」在 v10 与 v12 之间无法回答——而这两次修订正好夹着实现分支 `b9195f4` 的全部工作。`spec.md:9` 自己也逐字写着「每次修订记入 §12」，所以这不是外部规则强加，是本文档对自己立的规矩没有执行。

**顺带一处结构缺陷，同一次编辑造成。** §2.8 在文档里排在 §2.7 **之前**（`:97` 对 `:109`）。这是因为 v12 把新节插在 §2.6 之后、而没有排到 §2.7 后面。后果不止是好看不好看：一个按目录顺序读的人先读到「Anthropic 腿暂不接线，因为它挡在 §2.7 的规则上」，而 §2.7 还在下面——`:103` 那句「挡住它的是 §2.7 自己那条规则」在阅读顺序上是一次前向引用。

**建议。** 补两行 §12（各写清「变化」与「触发」两列，v11 的触发是「放宽定义域后发现的一般事实」，v12 的触发是「§8 的限定被发现窄于成立范围」，两者都不是用户裁决而是本规格推导 ＋ 已有用户裁决的重新定位，写进「触发」列时要区分开）；文首状态行改为 v12 并同步实施状态（那一半见 round9-11）；把 §2.8 移到 §2.7 之后，或把两节对调编号——**两条路都可以，但不要只改编号不改位置**，那会让引用旧编号的 `deferred.md` D-5（`:86` 写「出处：spec.md §2.8」）与 `delivery_policy.py:62` 的注释一起指错。

**证据强度：强**（`rg` 空集可复现；两次提交的 diff 逐行读过；两条规则原文逐字引用）。**影响**：文档可审计性与后续每一轮评审的基线判定；无当前用户可观察行为后果。

---

#### `direct-passthrough-spec-review-round9-04`

- finding_id：`direct-passthrough-spec-review-round9-04`
- severity：`major`
- primary_location：`spec.md:428`（§9.1「它是本规格定义域的**超集**（本规格还要求两端同为 `openai-responses`）」）
- related_locations：`spec.md:5`（v10 的新定义域）、`spec.md:471`（§11 O-1 的问题措辞「是否覆盖 **Responses 客户端的**直连腿」）、`spec.md:430`（「裁决到达之前一律取交集」）、`docs/.human-controlled/message-format-reshape.md`「客户端返回 Anthropic Messages」一节、`.dev/docs/error-envelope/spec.md` §3.1
- 标题：§9.1 与 §11 O-1 都还站在 v9 的窄定义域上——放宽之后 error-envelope 的直连定义域与本规格**相同**而不是超集，而且 O-1 这个待用户裁项在四条腿里有一条（Anthropic 直连）**根本不存在定义域疑问**，用户拿到的分叉面因此是错的

**逐字对读。** `spec.md:5`（v10 改写）：

> 定义域：**任何 `route.translation_required is False` 的路由**，不限方言。

`spec.md:428`（§9.1，v9 写下、v10～v12 未动）：

> ……它的路径判据键在 `Route.translation_required is False`——**它是本规格定义域的超集（本规格还要求两端同为 `openai-responses`）**，因此本腿被它完整覆盖。

括号里那句话是 v9 的定义域，v10 已经把它删掉了。**放宽之后两者的键完全一致，是相等而不是超集。** 这一格是 round8-12 的修复产物：v9 把「完全相同」改成「超集」，那在 v9 是对的；v10 改了定义域却没有回头扫这句话。

**第二处更要紧，因为它是要送到用户面前的那份问题。** §11 O-1 的问题句（`:471`）是：

> `message-format-reshape.md`「客户端返回 Anthropic Messages」一节的**直连响应头黑名单**是否覆盖 **Responses 客户端的**直连腿

而 §9.1 `:428` 给出的理由是「该节标题是「客户端返回 Anthropic Messages」，而**本腿的客户端收到的是 Responses**」。**放宽定义域之后，四条直连腿里有一条的客户端收到的就是 Anthropic Messages**——`anthropic-messages` ↔ `anthropic-messages` 那条。在那条腿上，用户名单的节标题**逐字命中**，没有任何定义域疑问，黑名单直接适用。

于是 O-1 当前的形态有两个缺陷：

1. **问题问窄了**。它问的是「是否覆盖 Responses 客户端的直连腿」，而 Spec 的定义域现在是四条腿；用户答「不覆盖」时，Chat Completions 与 Embeddings 两条腿的响应头怎么办没有答案。
2. **它没有告诉用户「有一条腿不用问」**。这恰恰是一条能帮用户下判断的事实：如果黑名单在 Anthropic 直连腿上无争议地生效，那么「同一份名单在另一条直连腿上失效」这个读法就要额外解释为什么同一份「直连路径的黑名单」会因客户端方言而不同。这一点对两个方向的裁决都有用，本规格不必主张任何一读，但**必须把它摆上桌**——`as-pending-decisions-checker` 关心的正是「上桌的问题有没有把真实分叉面描述完整」，而 round8-05 已经因为同一类问题（差异只算了一侧）扣过一次。

**这一条不主张改行为。** §9.1 的「取交集」在剥离方向仍然安全，语义判据我也认为是对的。要改的是**定义域陈述**与**上交给用户的那份分叉面**。

**建议。**

1. `:428` 把括号那半句删掉，「超集」改为「**相同**」——error-envelope §3.1 的键与本规格定义域现在逐字一致，结论（本腿被它覆盖）不受影响且更强。
2. §11 O-1 的问题句改为按腿分述：Anthropic 直连腿上名单无争议适用；待裁的是它是否延伸到 Responses、Chat Completions、Embeddings 三条腿的客户端。现状列同步。
3. 顺带把「本腿」这个单数指代在 §9.1 全节检查一遍——`:428`、`:430`、`:451` 都写「本腿」，而定义域现在有四条腿。

**证据强度：强**（`spec.md:5` 与 `:428` 逐字对读，矛盾可数；error-envelope §3.1 的键在 round8 已逐字核过、本轮未重取；四条腿的客户端方言由 §2.6 自己列出）。**影响**：一条待用户裁决项的质量——这是本规格当前唯一需要用户裁的事项，错的分叉面会换来一个不适用的裁决。

---

#### `direct-passthrough-spec-review-round9-05`

- finding_id：`direct-passthrough-spec-review-round9-05`
- severity：`major`
- primary_location：`plan.md:86`（顺序表第 5 步「~~replay 合同~~ **已完成**（`d76ac1c`）」）
- related_locations：`plan.md:4`（状态行「待评审与合并」）、`plan.md:60`（plan §5 自己列出的两件必做事项）、`spec.md:223`（§5.1 第一行）、`spec.md:229-259`（§5.2 全节）；实现 `src/app/pipeline/delivery/stream.py:396-403`（failure 分支）、`:81-92`（`ReplaySupport`）、`:466-473`（`reopen` 的两值调用点）
- 标题：第 5 步被记为已完成，但 plan §5 自己点名要做的两件事——§5.2 的 `StreamFailure` → `RetryReason` adapter、三类重开结果——在实现里都不存在；原生 failure 在交付循环里直接写给客户端然后 `return`，从不进 taxonomy

**plan 自己的要求逐字。** `plan.md:60`：

> **还要实现 Spec §5.2 的 adapter**：把 `StreamFailure` 归一化成既有 `RetryReason | None` 再交给现有 taxonomy，**不新增枚举值**。…… 重开 attempt 的结果按 Spec §5.2 分成 `OpenedAttempt`／`AttemptFailed`／`ReopenRefused` 三类。

**实现里的实际路径。** `stream.py:396-403`：

```python
failure = assembler.failure
if failure is not None:
    yield _report_failure(failure, framer=framer, passthrough=passthrough)
    return
```

`assembler.failure` 是一个 `StreamFailure`。它被直接写给客户端然后 `return`，**没有任何一处把它交给 `replay.eligible`／`replay_reason`／`reason_for`**。replay 机制的入口在 `:456`，谓词是 `reason = None if ours else (replay.eligible(torn) ...)`，其中 `torn` 是一个 `Exception`（由 `:411-413` 的 `except Exception` 捕获）。**原生 failure 事件永远走不到那里**，因为它在上面就 `return` 了。

所以 §5.1 第一行规定的「上游原生 failure 事件在首个原生事件提交前到达 → 是否可 replay 完全复用既有 retry taxonomy」在实现里**一次也不会发生**：一个可重试的 `response.failed`（`code == "server_error"`）今天会被逐字写给客户端并结束，而 Spec 要求先尝试透明 replay。

**三类重开结果同样不存在。** `ReplaySupport.reopen` 的类型是 `Callable[[Exception], Awaitable[Attempt | None]]`（`stream.py:92`），调用点（`:468-472`）只分 `replacement is not None` 两支。§5.2 花了整整一节论证 `AttemptFailed` 与 `ReopenRefused` 的 origin 不同、压成一个会把上游归因套到代理拒绝上——那个区分今天在代码里不存在。

**plan 的完成说明为什么读起来像成立。** `plan.md:86` 逐字：

> `terminal`／`failure`／`cut_mid_block` 由与翻译型 assembler **共用**的读取函数填充，交付循环的 replay 机制原样适用。

前半句是真的（`read_terminal`／`read_failure` 确实共用）。**后半句才是那个跳步**：「交付循环的 replay 机制原样适用」只对 transport tear 成立，而 §5.1／§5.2 要的恰恰是**让原生 failure 也能进那台机器**——那正是 §5.2 存在的全部理由，它开篇就写着「「复用既有 taxonomy」**不能代替一个可执行的输入**，而 v3 就停在了那里」。第 5 步的完成说明现在停在同一个地方，只是换了一个措辞。

**影响。**

1. **门禁**。`plan.md:4` 说这个分支「待评审与合并」，而 Spec 的两条规范性要求没有实现且被记为已完成。合并之后没有任何东西会提醒下一个人回来做。
2. **验收**。`plan.md:118`（v5 组）的验收清单里有「**已知 native failure code** 的归一化（`server_error` 与 `rate_limit_exceeded` 分别走哪条路）」与「**`ReopenRefused` 不进上游 taxonomy**」两条，它们对应的实现不存在，所以这两条判据今天必然写不出来或者会写成空跑。
3. **可观测**。一个本可透明重放的 `response.failed` 现在直接成为客户端可见的失败，而完成行会把它记成一次上游失败而非一次未尝试的 replay。

**建议。** 两条路选一条，**不要两条都不选**：

- 把第 5 步的状态从「已完成」改回未完成，并在顺序表里明确它剩下的是「§5.2 的 adapter ＋ 三类重开结果」；或者
- 若判断这一部分应当推迟（例如「原生 failure 的 replay 不是本刀的射程」），那要**显式写下来**并说明 §5.1 第一行在实现落地前不成立——按 `no-silently-cut-but-defer`，不能靠一个 `~~删除线~~` 把它抹掉。

我的倾向是前者：§5.1／§5.2 是四轮评审产出的东西，且 §5.2 的 `full` 窗口论证（`:243`）说明损失最大的正是这条路径。

**证据强度：强到可以据此行动。** 四处实现逐行读过（failure 分支、`ReplaySupport` 定义、`reopen` 调用点、`except Exception` 的捕获面），`rg` 确认 `assembler.failure` 在 `stream.py` 里只有 `:396` 一个读取点；plan 的两句逐字对读。**未实跑**（边界不允许在实现 worktree 跑 pytest），但这一条是「某条通路在代码里不存在」，读代码就是它的判据。

---

#### `direct-passthrough-spec-review-round9-06`

- finding_id：`direct-passthrough-spec-review-round9-06`
- severity：`major`
- primary_location：实现 `src/app/pipeline/delivery/stream.py:385-403`（`_deliver` 的提交 ＋ failure 分支）
- related_locations：实现 `src/app/pipeline/delivery/passthrough.py:243-251`（`_take_safe_prefix` 的终局放行）、`formats/openai_responses_passthrough.py` 的 `CONTROL_EVENTS` 与 `TERMINAL_EVENTS`、`blocks.py:117-135`（`BlockBuffer.add`）、`stream.py:284-292`（`_report_failure`）；`tests/int/test_error_envelope.py:479-500`（覆盖到这条路径却查不出来的那个断言）；`spec.md:355-360`（§7.2 收口四步）、`spec.md:128`（§3 的逐字重放承诺）、`plan.md:4`
- 标题：**实现侧，超出被评对象但直接推翻 plan v10 的就绪陈述。** 候选分支上，直连 Responses 腿收到上游终局失败事件时，`block` 下会把该事件**发两遍**，`full`／`until-tool-use` 下会把**全部已完成 group 丢掉**；覆盖这条路径的集成测试用的是成员断言，两种后果都查不出来

**链条五环，每一环都在代码里。**

1. `response.failed` 同时属于 `CONTROL_EVENTS` 与 `TERMINAL_EVENTS`（`openai_responses_passthrough.py`，两个 frozenset 都含它）。
2. `PassthroughAssembler.push` 把它记进队列、调 `read_failure` 填 `self._failure`，然后调 `_take_safe_prefix`。
3. `_take_safe_prefix`（`passthrough.py:246-249`）的放行条件是「head 里有 int item **或** 有 terminal 事件」：

   ```python
   if not any(isinstance(p.item, int) for p in head) and not any(
       p.event.event in self._dialect.terminal_events for p in head
   ):
       return None
   ```

   `response.failed` 命中第二个 `any`，**所以含它的前缀被释放**，作为一个 `RawEventBatch` 返回给调用者。
4. `_deliver`（`stream.py:385-395`）先把返回的 batch 交给 `_commit` → `session.offer` → `BlockBuffer.add`。`block` policy 下 `add` 直接 `_drain()` 返回该 batch（`blocks.py:128-129`），于是 `PassthroughFramer.block` 把它 `encode()` 出去——**客户端此时已经收到 `event: response.failed`**。
5. 紧接着 `:396-401` 读 `assembler.failure`（非 `None`），调 `_report_failure`；`passthrough=True` 且 `origin is UPSTREAM_EVENT` 时它返回 `encode_frame(failure.event, failure.raw_data)`——**同一个事件名、同一份 payload，第二遍**。

**`full` 与 `until-tool-use` 下是另一种后果，方向相反。** `BlockBuffer.add` 在 `full` 下返回 `()`（`blocks.py:127-128`），所以第 4 步什么都不发；第 5 步发出 failure 帧后立即 `return`，**`stream.py:506` 的 `session.finish()` 再也到不了**。于是缓冲里全部已完成的 group 被静默丢弃，客户端只收到一条 failure 帧。这与 §7.2 收口第 2 步（「按**原序**提交 control 与所有已完成的安全 group」）直接相反，而 §7.2 `:387` 还专门论证过为什么取「先提交已完成内容再写 error」而不是「全丢」。

**为什么 1993 passed 没有拦住它。** `tests/int/test_error_envelope.py:482-500` 就是覆盖这条路径的测试（直连 Responses 腿 ＋ `response.failed`），它的断言是：

```python
assert event in _events(delivered), f"upstream's own event name was lost: {_events(delivered)}"
```

**`in` 是成员判定，不是计数**，所以「发一遍」与「发两遍」在它眼里完全同形。它检查的命题（「上游自己的事件名有没有被丢掉」）是对的且仍然成立；它只是对本条查不出的那件事没有分辨力。这是本仓记过的形状：**断言钉结构别钉名字**，这里是钉了名字的存在性。

**根因是一处继承来的注释没有随新腿重估。** `stream.py:400` 逐字：

> Blocks completed by this same event go out first, above: they arrived, and dropping them would make what a client received depend on when the failure landed.

这句话写给翻译腿是对的——那条腿上 failure 事件**自己不是**一个块，所以「先发块、再发 failure」不会重复。透传腿上 failure 事件**就在**被释放的那个 batch 里，前提变了而结论被原样搬了过来。

**影响。** `block` 是默认 policy，所以重复那一支是默认路径上的坏帧：一个按 `ResponseFailedEvent` 建模的客户端会看到同一个 response 失败两次，SDK 侧的 accumulator 行为未测。`full`／`until-tool-use` 那一支更重——丢内容而不是多内容。两者都在 `plan.md:4` 声称「待评审与合并」的那个 HEAD 上。

**建议（交实现侧，不由本报告决定形态）。** 两个方向：让 `_report_failure` 在 passthrough 且该事件已随 batch 出门时不再重发；或者让 `_take_safe_prefix` 不把 failure 事件放进 batch、由收口统一发。**第二个方向顺带解决 `full` 那一支**，因为收口路径会先走 §7.2 的四步。无论选哪个，那条集成测试的断言应从 `in` 改成计数或序列比对——**这一处改动本身就是本条的最小回归防线**。

**证据强度：机制强到可以据此行动，但未实跑。** 五处实现逐行读过并逐句引用在上面；两个 frozenset 的成员关系可数；`BlockBuffer.add` 的两个分支逐字；那条集成测试的断言逐字。**按调用方边界我没有在实现 worktree 跑 pytest**，所以这是一次逐环闭合的机械推断而不是一次观测。settle 它的最小命令是在实现 worktree 跑：`uv run pytest tests/int/test_error_envelope.py::test_a_direct_responses_leg_keeps_upstreams_own_event_name -q`，并把断言临时换成 `_events(delivered).count(event) == 1`——这属于「受控变异」，需要在隔离树里做，本轮未做。

---

### minor

#### `direct-passthrough-spec-review-round9-07`

- finding_id：`direct-passthrough-spec-review-round9-07`
- severity：`minor`
- primary_location：`spec.md:101`（§2.8「在 `block` 下它早已出门」）
- related_locations：`spec.md:105`（§2.8 的三个候选）、`deferred.md:74`／`:78-82`（D-5 的冲突陈述与三个候选）；实现 `stream.py:506-527`（`session.finish()` 与 `_hand_over` 的先后）、`stream.py:611-614`（`_hand_over` 里的 `framer.block(handed)` 与 `framer.terminal(...)`）、`passthrough.py:303-307`（`PassthroughFramer.block`／`terminal`）、`blocks.py:68-82`（`CompletedBlock` 无 `encode`）
- 标题：§2.8 的结论（Anthropic 腿暂不接线）成立，但它给的理由有两处不准——顺序问题**不限于 `block`**，而且真正更硬的阻断不是顺序而是类型：`_hand_over` 会把一个 `CompletedBlock` 交给只认 `RawEventBatch` 的 `PassthroughFramer.block`

**先回答调用方点名要核的那一问：§2.8 的前提对吗？对。** 我按调用方要求读了 §5 的提交表与 §7.2 的收口顺序，再对着实现核了终局的释放时点：

- `PassthroughFramer.terminal()` 返回 `()`（`passthrough.py:306-307`），所以 `stream.py:576` 的 `framer.terminal(terminal)` 在这条腿上什么都不发；上游自己的终局事件是**作为一个普通事件混在 batch 里**由 `framer.block()` 发出去的。
- `_hand_over` 的调用点在 `stream.py:521`，而 `session.finish()` ＋ 冲刷 remaining 在 `:506-514`。**所以无论哪种 policy，缓冲里的一切（含承载终局事件的那个 batch）都在 hand-over 判定之前已经写给客户端了。**

**第一处不准：范围被写窄了。** `spec.md:101` 说「在 `block` 下它早已出门」。这个限定会让读者以为 `full` 或 `until-tool-use` 能躲过——躲不过，`:506-514` 的冲刷对三种 policy 一视同仁。**把范围写窄比写宽更危险**：它给了一个不存在的规避路径，而 D-5 的候选 1（「在 hand-over 可能发生时推迟终局的释放」）如果被理解成「只在 `block` 下需要」，做出来就是半个修复。

**第二处不准，也是更硬的那一半：这不只是顺序问题。** `_hand_over`（`stream.py:611-614`）逐字：

```python
handed = CompletedBlock(index=session.committed_count, kind=TOOL_USE, payload=payload)
chunks.extend(framer.block(handed))
chunks.extend(framer.terminal(replace(assembler.terminal, stop_reason=TOOL_USE)))
```

而 `PassthroughFramer.block`（`passthrough.py:303-304`）是：

```python
def block(self, block: RawEventBatch) -> tuple[bytes, ...]:
    return (block.encode(),)
```

`CompletedBlock`（`blocks.py:68-82`）只有 `index`／`kind`／`payload` 三个字段与两个属性，**没有 `encode`**。所以在 Anthropic 直连腿上真的接线之后，一次 `max_tokens` hand-over 不会「插错位置」，而是**在 `framer.block(handed)` 上抛 `AttributeError`**；紧随其后的 `framer.terminal(...)` 又返回 `()`，所以即使前一行不炸，合成块之后也不会有 `message_stop` 收尾。

**这对 D-5 的候选评估有直接后果。** `deferred.md:80-82` 的三个候选里：

- 候选 1（推迟终局释放）**只解决顺序那一半**——推迟之后 `framer.block(CompletedBlock)` 照样抛；
- 候选 2（合成块以该方言的原生事件表达）**同时解决两半**，因为它一开始就不再往 passthrough framer 里塞 `CompletedBlock`；
- 候选 3 与 §2.7 冲突，需用户裁，不变。

D-5 现在写着「**我倾向第二个**」，倾向是对的，但给的理由是「机制现成、与既有委托模式一致、代价最小」——**没有提到候选 1 单独不成立**。一个采纳候选 1 的人不会从这份台账里读到他会撞上什么。

**建议。** 三处小改，都属本规格／台账自己的记录，评审共识即可：

1. `spec.md:101` 去掉「在 `block` 下」这个限定，改为「三种 policy 都如此——`session.finish()` 的冲刷在 hand-over 判定之前」。
2. §2.8 与 D-5 各补一句：除顺序之外还有一处类型不兼容（`_hand_over` 构造 `CompletedBlock`，而 passthrough framer 的 `block()` 只接受 `RawEventBatch`），因此**候选 1 单独不足以解决问题**。
3. D-5 的候选 1 描述里加上这一限定，免得倾向改变时理由跟着失真。

**证据强度：强**（五处实现逐行读过并引用；`CompletedBlock` 无 `encode` 由其类定义全文确认；三种 policy 的冲刷时点由 `stream.py:506-527` 的行序确定）。**影响**：不改变「暂不接线」这个正确结论，改变的是它的理由准确性与 D-5 候选评估的完整性——而 D-5 是要交用户裁形态的。

---

#### `direct-passthrough-spec-review-round9-08`

- finding_id：`direct-passthrough-spec-review-round9-08`
- severity：`minor`
- primary_location：`spec.md:99`（§2.8「`hand_over_supported` 按 inbound 格式门控」）
- related_locations：`spec.md:107`、`deferred.md:72`、`deferred.md:84`；`spec.md:395`（§8，**同一机制写对了**）；实现 `src/app/pipeline/hand_over.py:238`
- 标题：`hand_over_supported` 这个符号在 `src/` 与 `tests/` 里不存在；真正的门是 `hand_back_block()` 开头的 `wire_format is not WireFormat.ANTHROPIC_MESSAGES`，而 §8 自己已经这么写了

**可数事实。** `rg -n 'hand_over_supported' src tests .dev docs` 只在四处命中，**全部在本主题的 `.dev` 文档里**（`spec.md:99`、`:107`，`deferred.md:72`、`:84`），`src/` 与 `tests/` 零命中。

**真正的门。** `hand_over.py:238`：

```python
if wire_format is not WireFormat.ANTHROPIC_MESSAGES:
    return None
```

它在 `hand_back_block` 的开头，经 `ContinuationSupport.synthesize` 暴露给交付循环。**§8 `:395` 已经写对了**：「`hand_back_block()` 对非 Anthropic inbound 返回 `None`」。所以同一份 Spec 用两个名字描述同一个门，其中一个不存在。

**为什么值得写下来而不是放过。** 一个照 §2.8 去代码里找 `hand_over_supported` 的人会找不到，而最省事的下一步是**认为这个门不存在**——而 §2.8 的整个论证（Anthropic 腿今天就放行 hand-over、Responses 腿不放行）都压在这个门上。这属于「一个正确的结论配一个不可核验的理由」。

**建议。** 四处改成 `hand_back_block()` 的门（或直接引 §8 已有的那句话），与 §8 用同一个名字。

**证据强度：强**（`rg` 的空集与四处命中可复现；`hand_over.py:238` 逐行读过；§8 的正确写法逐字对读）。

---

#### `direct-passthrough-spec-review-round9-09`

- finding_id：`direct-passthrough-spec-review-round9-09`
- severity：`minor`
- primary_location：`spec.md:78`（§2.5 表第二行「§5 第四行据此解除持有」）
- related_locations：`spec.md:101`（§2.8「§5 第四行」）、`spec.md:199-205`（§5 的提交表）；实现 `passthrough.py:44`（「§5's fourth row lets one of these release a prefix」）、`openai_responses_passthrough.py:34`（「`spec.md` §5's fourth row gives them their own row」）
- 标题：「§5 第四行」指错行——第四行是「第一批 item 事件」，而被引用的规则（终局解除 control-only 前缀的持有）在第五行；这处错位已经逐字转抄进两个源文件的注释

**数一遍。** §5 提交表（`spec.md:199-205`）的内容行依次是：(1) HTTP 200 headers、(2) SSE comment keepalive、(3) `response.created` / `response.in_progress`、(4) 第一批 item 事件、(5) 无 item 的 terminal／failure。被三处引用的那条规则——「一个终局可以让只含 control 事件的前缀出门」——是第 (5) 行。把表头算作一行也不能救：那样第四行是 `response.created` / `in_progress`。

**它已经扩散了。** `passthrough.py:44` 与 `openai_responses_passthrough.py:34` 两处注释都逐字写着「§5's fourth row」。这是 Spec 转抄进代码之后**连错误一起转抄**的实例，符合项目规则里「每一处转抄都是一个会悄悄落后的地方」那条——只不过这次它一出生就是错的。

**建议。** 三处文档 ＋ 两处代码注释统一改为「§5 提交表的最后一行」或「§5 提交表「无 item 的 terminal／failure」那一行」。**用内容指代而不是序号**，因为这张表还会增行。

**证据强度：强**（表可数；三处文档与两处代码注释逐字对读）。**影响**：可读性与交叉引用的可核验性，无行为后果。

---

#### `direct-passthrough-spec-review-round9-10`

- finding_id：`direct-passthrough-spec-review-round9-10`
- severity：`minor`
- primary_location：`plan.md:95`（「**接线覆盖所有直连腿，不只 Responses。**」整段）
- related_locations：`plan.md:89`（顺序表第 8 步，「**Anthropic 腿未接线**」）、`plan.md:76`（§7 的「顺序表里这一步现在是第 7 位」）、`plan.md:4`、`spec.md:91`（§2.6 的 Anthropic 行，v11 已换掉论据）
- 标题：plan 同一文件里两处相反——第 8 步说 Anthropic 未接线，它下面的说明段仍说「接线覆盖所有直连腿」，且该段复述的是 §2.6 在 v11 已经换掉的旧论据；另有一处步号指错

**其一，两处相反。** `plan.md:89`（v10 改写）：

> 8. **接线**：Responses 直连腿**已完成**（`b9195f4`），issue #2／#3 关闭。**Anthropic 腿未接线**，见 §2.8

`plan.md:95`（v9 写下，v10 未动）：

> **接线覆盖所有直连腿，不只 Responses。** Spec §2.6 逐条核过四条直连对：Responses 是主体工作；**Anthropic 直连是同形缺陷且今天可达**——`descriptor.supports(inbound_endpoint)` 为真时 target 即等于 inbound，而集成测试里已经有 `anthropic-messages` 上游；……

后一段既与前一句相反，又复述了一份**已经被替换的**论据：`spec.md:91` 在 v11 把「今天可达」的依据从「`descriptor.supports` ＋ 集成测试里有 Anthropic 上游」换成了「`claude-sonnet-5` 不支持 Responses API，Claude 系模型只能走直连」——后者严重得多，也是 §2.7／§2.8 全部论证的支点。plan 里留着的是前者。

（顺带核过：`descriptor.supports` 确实存在，`routing.py:316`／`:321` 与 `model_provider/types.py:91`；`unsupported_api_for_model` 那条实测也确实逐字在 `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md:62`。所以两份论据都不假，问题是 plan 留的是被升级掉的那一份。）

**其二，步号指错。** `plan.md:76`（plan §7「撤销 `ca777df` 在直连腿的那一半」的开头）：

> 顺序表里这一步现在是第 7 位，与本节编号无关；见 §8 的两条说明。

顺序表第 7 步是「抽方言词汇 ＋ `anthropic-messages` 一份」；撤销 `ca777df` 那件事在第 8 步（v9 的第 8 步逐字写着「分流点接线 ＋ 撤销 `ca777df` 的直连腿一半 ＋ 更新下述测试的断言，同一刀」）。这一句从 v9 插入词汇步的那一刻起就错了。**而且 v10 把第 8 步改写成「接线：Responses 直连腿已完成」之后，「撤销 `ca777df`」这几个字从顺序表里消失了**——所以现在既没有一个步骤显式承载它，plan §7 又指向了错的步骤。

**建议。**

1. `plan.md:95` 整段重写：说清「接线的目标是覆盖所有直连腿，当前只落了 Responses 一条，Anthropic 挡在 §2.8／D-5，Chat Completions 与 Embeddings 见 §2.6」，并把论据换成 §2.6 现在那一份（或改成纯引用，与同文件对 §7.2、§5.2、header 名单已经采纳的「不复制」纪律一致）。
2. `plan.md:76` 改为「第 8 位」，并在第 8 步的文字里把「撤销 `ca777df` 的直连腿一半」显式记为已完成或未完成——**它现在是不可见的**，而 plan §7 与 Spec §2.4 都还把它当作必须发生的一件事。

**证据强度：强**（plan 三处逐字对读；`spec.md:91` 的 v11 前后文本由 `git show 1cfa309` 逐行核过；`descriptor.supports` 与 `unsupported_api_for_model` 两条引用本轮实取）。

---

#### `direct-passthrough-spec-review-round9-11`

- finding_id：`direct-passthrough-spec-review-round9-11`
- severity：`minor`
- primary_location：`spec.md:4`（文首状态行「主体（接线）未开始」）
- related_locations：`spec.md:90`（§2.6 Responses 行的「依据」列：「引擎已建（`01c33f1`），未接线」）、`plan.md:4`（权威处：已接线，在 `b9195f4`）、`spec.md:477`（§11「实施状态不属于本节，见 `plan.md`」）、`plan.md:27`（分流点仍以旧定义域描述）
- 标题：实施状态的权威是 `plan.md`，而 `spec.md` 有两处复述停在 v10——v12 更新了 §2.6 的 Anthropic 行却漏了同一张表的 Responses 行；另有 plan §1 仍以放宽前的定义域定义分流点

**三处逐字。** `plan.md:4`（权威）：「**Responses 直连腿已接线，issue #2／#3 已修**，在分支 `worktree-260831-passthrough-wiring`（`b9195f4`……），**待评审与合并**」。`spec.md:4`：「Responses 方言的透传骨架亦已合入（`01c33f1`，未接线）。**主体（接线）未开始。**」`spec.md:90`：「引擎已建（`01c33f1`），未接线」。

**对 `main` 而言「未接线」为真**（`main` HEAD 是 `01c33f1`），但两处都没有限定语，而 `plan.md:4` 说的是分支状态。项目规则对这种可变复述的要求很具体：**要么带 provenance 与快照，要么随同一次语义变更一起更新**。§12 缺失（round9-03）让读者连「这句话是哪一版写的」都查不到，两处叠加之后「主体（接线）未开始」就成了一句无法定位的断言。

**v12 只改了半张表。** `git show 68a95b3 -- docs/direct-passthrough/spec.md` 显示这次提交把 §2.6 的 **Anthropic 行**改成「词汇已实现并单测……接线待 §2.8」，**同一张表的 Responses 行一个字没动**。这是 round8-10／round8-11 那一类的第三次复发：同一次修复只走到点名的那几处。

**顺带一处同族的窄读**（与 round9-04 同源，单列在这里因为它在 plan）：`plan.md:27` 的分流点仍写「`DIRECT_RESPONSES_PASSTHROUGH` —— `translation_required is False` 且**两端同为 `openai-responses`**」。实现里没有这个常量，判据是 `delivery_policy.carries_upstream_natively`；而那个函数今天**确实**只对 `OPENAI_RESPONSES` inbound 返回真——所以行为对得上，对不上的是「这是暂时的收窄（因为 §2.8）」这个事实，plan §1 把它写成了设计。

**建议。** `spec.md:4` 与 `:90` 各加限定并指向 plan（例如「`main` 上未接线；分支状态见 `plan.md`」），或者干脆按 §11 `:477` 已经立下的规矩把实施状态从 Spec 里删干净——**后者更彻底，也与 §11 自己那句「实施状态不属于本节」一致**。`plan.md:27` 补一句「当前实现按 §2.8 只覆盖 Responses inbound，判据是 `carries_upstream_natively`」。

**证据强度：强**（三处逐字对读；`git show 68a95b3` 的 diff 逐行核过；`carries_upstream_natively` 全文读过）。

---

#### `direct-passthrough-spec-review-round9-12`

- finding_id：`direct-passthrough-spec-review-round9-12`
- severity：`minor`
- primary_location：`spec.md:92`（§2.6 Chat Completions 行的「状态」与「依据」两列）
- related_locations：`spec.md:5`（定义域）、`spec.md:93`（Embeddings 行）、`spec.md:195-217`（§5 replay）、`spec.md:391-397`（§8）、`spec.md:409-455`（§9.1）、`spec.md:457-463`（§10）；实现 `stream.py:246-266`（`one_shot_delivery` 全文）、`delivery_policy.py:42-55`（`delivers_blocks`）、`server/routes/table.py:39`（embeddings `streamable=False`）
- 标题：§2.6 对 Chat Completions 只回答了 §2.1，而定义域放宽之后 §5／§8／§9.1／§10 也都声称覆盖那条腿——实际上 `one_shot_delivery` 明确没有 replay、没有 keepalive、失败时不写任何 error frame，这几条今天在那条腿上全部不成立且无处登记

**先确认调用方要我自己核的两条事实——两条都成立。**

- **「Chat Completions 的天花板不存在，但那是偶然」：成立。** `delivery_policy.delivers_blocks`（`:53-55`）对 `inbound_format is OPENAI_CHAT_COMPLETIONS` 返回 `False`；`framer_for`（`:88-95`）据此返回 `None`；调用方改走 `one_shot_delivery`，它把上游字节整体缓冲后原样一次写出（`stream.py:257-266`，`body = bytearray()` ＋ `yield bytes(body)`）。中间没有任何 assembler 或类型表。「偶然」这个判断也对——`one_shot_delivery` 的 docstring 逐字说它存在的原因是「Chat Completions 的块边界在 `choices[].delta` 里、本项目不读」，即天花板不存在是因为**整条能力都不存在**，不是因为有人为直连做了保真设计。
- **「Embeddings 非流式」：成立。** `server/routes/table.py:39` 逐字 `streamable=False`。

**但 §2.6 的这一行止于「现状即满足 §2.1」，而定义域已经不止 §2.1 了。** `spec.md:5` 说本规格覆盖任何 `translation_required is False` 的路由。于是 §5、§8、§9.1、§10 的规范性条款**按字面全部落在 Chat Completions 直连腿上**，而 `one_shot_delivery` 的 docstring 逐字否掉其中三条：

> **No replay and no keep-alive.** Both are answers to questions block delivery raises …… and neither has a meaning for a delivery that is a single write.
>
> What the client does *not* get is a frame naming the failure: writing one would mean inventing an error shape for a dialect nothing here can frame ……

也就是说：§5 的整套 replay 合同、§8 的「代理侧错误写 `event: error`」、以及 §10 想要的那些旁路事实，今天在那条腿上都不成立。§9.1 的响应头合同同理——`plan.md:90` 的第 9 步只写「Headers（§9.1）」，没有说它的射程是几条腿。

**这不是要求把那条腿补齐。** 块级交付是 2026-08-22 已裁决的推迟项，§2.6 引用得对。要求的是**把「哪些条款在那条腿上今天不成立」写下来**——按 `no-silently-cut-but-defer`，一个中途发现的、与当前任务相关的缺口不该只以「不因本规格重开」一句带过，因为那句话回答的是「要不要现在做」，不回答「Spec 现在是不是在对一条腿做它兑现不了的承诺」。

**Embeddings 那一行有同样的形状但轻得多**：它写「非流式，按 §9 处置」，而 §9／§9.1 确实是它需要的两节，缺的只是没说 §3～§8 与它无关（这一点从「非流式」三个字可以推出来，所以我不单列）。

**建议。** §2.6 的 Chat Completions 行「依据」列补一句：这条腿今天走 `one_shot_delivery`，**§5 的 replay、§8 的 error frame、§10 的旁路事实在它上面均不成立**，块级交付落地前这几条对它不适用；并在 `plan.md` 第 9 步注明 headers 的射程。若判断这需要更正式的处置，可在 `deferred.md` 立一条指针（**不必上交用户**，这是本规格自己的定义域记录）。

**证据强度：强**（`one_shot_delivery` 全文与 `delivers_blocks`／`framer_for` 逐行读过并逐句引用；`streamable=False` 逐字；§2.6 那一行逐字）。**影响**：Spec 对一条腿的承诺面与实际能力不符；无当前坏行为（那条腿今天的行为是 2026-08-22 裁决的结果，没有变）。

---

### nit

#### `direct-passthrough-spec-review-round9-13`

- finding_id：`direct-passthrough-spec-review-round9-13`
- severity：`nit`
- primary_location：`plan.md:1`（「# 直连 Responses 透传：实施计划」）
- related_locations：`deferred.md:1`（「# 直连 Responses 原生透传：延后项台账」）、`spec.md:1`（已改为「直连路径：原生透传产品规格」）、`spec.md:7`（目录改名那段的理由）
- 标题：Spec 自己用「一个窄于内容的名字本身就是缺陷」这条理由给目录改了名，同一条理由适用于 plan 与 deferred 的标题，而它们仍写「直连 Responses」

`spec.md:7` 逐字：

> **目录名是活的，一个窄于内容的名字本身就是缺陷。**

Spec 的标题已经跟着改成「直连路径：原生透传产品规格」，目录也从 `direct-responses-passthrough` 改成 `direct-passthrough`。`plan.md` 与 `deferred.md` 两份活文档的一级标题没改。

**这一条是 nit 而不是 minor**，因为标题不承载任何指令，读者读第 4 行的状态行就知道射程。写下来只因为它是同一条已被本规格明确采纳的规则的第三个实例，而漏掉的两处恰好是同一次改名当刀里的另外两份文件。

**建议。** 两份标题改为「直连路径：……」。**报告目录下的 12 份历史报告标题不动**——它们是时点记录，与目录改名那段的裁定一致。

**证据强度：强**（三处标题逐字；改名理由逐字引用）。

---

#### `direct-passthrough-spec-review-round9-14`

- finding_id：`direct-passthrough-spec-review-round9-14`
- severity：`nit`
- primary_location：`spec.md:394`（§8「按 `error-envelope/spec.md` 写 Responses `event: error`」）
- related_locations：`spec.md:405`（§9「合法 Responses JSON object」）、`spec.md:461`（§10「原生 output item 计数」）、`spec.md:395`（§8「`status: "incomplete"` 的 item」）
- 标题：四处在自称方言无关的节里用 Responses 的名词；实现已经用委托的方式回答了其中一处，Spec 还没有

这四处是 round9-02 那条全称断言的较轻反例，单列出来是因为**它们的修法与 round9-02 不同**：round9-02 要补词汇行，这四处只要把名词换成方言中立的说法即可。

- `:394` 的「写 Responses `event: error`」——实现已经给出正确形状：`PassthroughFramer.error` **委托给该腿自己的 framer**（`passthrough.py:309-310`），docstring 逐字说明理由是「each dialect already spells them」。所以 Spec 这里应写「按客户端方言写 error 帧，形状见 `error-envelope/spec.md` §6.3」。
- `:405` 的「合法 Responses JSON object」→「合法的 JSON object」。
- `:461` 的「原生 output item 计数」→「原生 item／content block 计数」，或按方言词汇表指代。
- `:395` 的「`status: "incomplete"` 的 item」是 Responses 专有形态（Anthropic 的 content block 没有 `status`）；该条的意图（不得套用翻译腿的 `cut_short`／hand-over 政策）与方言无关，可以把条件写成方言中立的「上游标记为未完成的 item」并注明 Responses 的具体拼法。

**证据强度：强**（四处逐字；`PassthroughFramer.error` 的委托逐行读过）。**影响**：仅可读性与写第三份词汇时的误导面。

---

#### `direct-passthrough-spec-review-round9-15`

- finding_id：`direct-passthrough-spec-review-round9-15`
- severity：`nit`
- primary_location：`plan.md:89`（第 8 步末尾「**Anthropic 腿未接线**，见 §2.8」）
- related_locations：`plan.md:5`（权威声明）、`spec.md:97`
- 标题：`plan.md` 自己有 §1～§9，没有 §2.8；这个交叉引用没说是哪份文档的 §2.8

同一份文件里其他交叉引用都带文档名（`plan.md:54` 写「Spec §7.2」、`:60` 写「Spec §5.2」、`:66` 写「Spec §9.1」）。只有 `:89` 写成裸的「§2.8」。**建议**改为「见 [`spec.md`](spec.md) §2.8」，与同文件既有写法一致。

**证据强度：强**（可数；同文件对照写法逐字）。

---

#### `direct-passthrough-spec-review-round9-16`

- finding_id：`direct-passthrough-spec-review-round9-16`
- severity：`nit`
- primary_location：`deferred.md:66-67`（D-4 与 D-5 之间有两个空行）
- related_locations：`deferred.md:3`（台账自己的编号纪律）
- 标题：D-4 与 D-5 之间多一个空行，与其余条目之间的单空行不一致

纯排版。写下来只因为 `deferred.md` 是要长期增删条目的活文档，条目之间的分隔不一致会在下一次插入时被复制。**建议**去掉多余的那个空行。

**证据强度：强**（可数）。

---

## 四 · 门禁：plan §8 顺序表逐步 yes/no

复核并更新 round8 那份。**第 1～7 步已完成或已合入，本表只对它们记「事后核验结论」；yes/no 只对未完成的步骤有意义。**

| 步 | 内容 | 门禁 | 条件与本轮判据 |
|---|---|---|---|
| 1 | P1／P2 | 已完成 | `7e96adc` 在 `main`。本轮未重跑，沿用 round8 的核验 |
| 2 | 透传骨架 | 已完成 | `01c33f1` 在 `main`。round8 点名必改的那处 docstring 转抄**已改掉**（`passthrough.py:272` 现在明说不转抄裁定），本轮逐行确认 |
| 3 | `parse_frame` 只认 CR／LF／CRLF | 已完成 | `109dc44` 在 `main`；`spec.md:166` 与 `plan.md:17`、文首同口径 |
| 4 | 提交语义接线 | 已完成（`092bd43`） | control-only 前缀的持有与终局解除在 `passthrough.py:243-249` 实现，与 §5 提交表一致。**但那处「§5 第四行」的错位引用随之进了代码注释**（round9-09） |
| 5 | replay 合同 | **完成陈述不成立** | **round9-05**：§5.2 的 adapter 与三类重开结果都不存在，原生 failure 从不进 taxonomy。这一步应改回未完成，或显式记为推迟并同步 §5.1 的可兑现性 |
| 6 | `requires_client_action` 与三种 policy | 已完成 | 判据读 item 自身（`openai_responses_passthrough.py:73-93`），`BlockBuffer` 已泛型化并由 `DeliveryUnit` 提供两个谓词。§7.1 与实现一致，本轮逐行核过 |
| 7 | 抽方言词汇 ＋ Anthropic 一份 | 已完成，**但 Spec 侧未同步** | 词汇已抽出并有第二份实现；**Spec 的词汇表少两行、Anthropic control 集缺 `message_stop`**（round9-01、round9-02）。这一步的产物是对的，落后的是它的权威文档 |
| 8 | 接线（Responses 已完成，Anthropic 未接线） | **Responses 那一半：conditional no（不建议就此合并）** | 三个条件：(a) **round9-06 必须先判**——候选 HEAD 上默认 policy 会重复发送上游终局失败事件、`full`／`until-tool-use` 会丢已完成 group，且覆盖它的集成测试用成员断言查不出来；(b) round9-05 的第 5 步状态要改对，否则合并即锁死一条「已完成」的假记录；(c) round9-11 的 Spec 侧状态要同步。**注意 (a) 与 (b) 都不否定 issue #2／#3 已修**——那两个 issue 的根因（`ResponsesAssembler` 的 `UNKNOWN → REJECT`）确实已经不在这条腿的路径上（`assembler_for` 直接返回透传 assembler），本条只说这一刀还带进了一处新的坏帧 |
| 8' | **Anthropic 腿接线** | **no** | 见下面的专门回答 |
| 9 | Headers（§9.1） | **conditional yes** | round8 判的三个条件里两个已完成（round8-05／round8-09 都 closed）。**新增两个条件**：(a) round9-04——§9.1 与 §11 O-1 的定义域陈述已经过期，且 O-1 的问题面窄于实际，动手前先改；(b) round9-12——这一步的射程是几条腿要写明（Chat Completions 直连腿今天连 error frame 都没有）。**O-1 本身仍不阻塞实施**：取交集在剥离方向保守这一点没变 |
| 10 | 可观测迁移（§10） | **yes**，排在 9 之后不变 | `plan.md:91` 点名的 `tests/int/test_pipeline_app.py:2788` 沿用 round8 的核验，本轮未重取。**一处顺带**：§10 的「原生 output item 计数」在两种方言下是两个名字（round9-14），实现已经用 `Dialect.name` 承载了这条腿的名字而 §2.5 没有登记它（round9-02） |

### 单独回答：Anthropic 腿的接线在 D-5 闭合前是否真的不该做

**不该做，结论成立，而且比 §2.8 给的理由更硬。**

三条独立的依据，任何一条单独都足够：

1. **§2.7 的规则直接适用，而它不是我推的**。`hook_fix_anthropic_sse.thinking.content_block_start_compat` 默认值是 `"signature_delta"`，`framer_for`（`delivery_policy.py:105`）今天就把它交给 `AnthropicFramer`；透传 framer 按构造不做整形。§2.7 裁定「接线不得改变任何一条腿今天已生效的整形默认值」，接线就会改。而用户在亲笔文档里对这一项的倾向是**常驻**，方向与「拿掉」相反（D-4 逐字引了原句）。
2. **hand-over 会直接抛异常，不只是「插错位置」**。`_hand_over` 把 `CompletedBlock` 交给 `PassthroughFramer.block()`，后者调 `block.encode()`，而 `CompletedBlock` 没有这个方法（round9-07）。这条腿是 `claude-sonnet-5` 唯一的路，`max_tokens` 续写是 2026-08-21 的用户裁决，所以这不是边角。
3. **§5.2 对这条方言没有答案**（round9-02）。即使前两条都解决了，`response.failed` 那张归一化表在 Anthropic 侧一行都不适用，接线后这条腿的 native failure 处置是未定义的——虽然今天 replay 通路本来就没接（round9-05），所以这一条的紧迫性低于前两条。

**但有一处要纠正 §2.8 的措辞**：它说「这不是缩减用户 2026-08-31 裁决的范围：词汇已实现并单测，缺的只是打开开关」。前半句对，后半句**不准确**——缺的不只是开关。按上面第 2 条，即使打开开关，一次 `max_tokens` hand-over 会抛 `AttributeError`；这需要一处真实改动，不是配置。把它写成「缺的只是打开开关」会让下一个读者低估 D-5 的工作量，而 D-5 的三个候选里恰好有一个（候选 1）单独做完之后仍然会撞上它。

**另外：D-5 是需要用户裁的，这一点我同意，不重开。** 它裁的是形态（三个候选里选哪个），其中候选 3 明确是一次行为回归、与 §2.7 冲突。候选 1 与候选 2 之间**其实不需要用户裁**——两者都保住行为，选哪个是实现取舍，属评审共识范围。所以严格说 D-5 上交用户的应该是**收窄后的那一问**：「是否接受候选 3（native 腿不提供续写）」；如果答案是否，候选 1／2 之间由实现侧定，而按 round9-07 的证据，候选 2 是唯一一个自足的。**这一点值得在 D-5 里写清楚**——`as-pending-decisions-checker` 的判据是「这一条是不是真的需要用户裁」，而现在 D-5 把三个候选并列上交，其中两个不需要。

---

## 五 · 考虑过但否决的候选发现

**按调用方要求列出，含否决理由。**

1. **「§2.5 缺一行「item 开启事件」」——否决。** 我先按 §3／§7.2 反复用到的「已打开而未闭合的 item」这个概念找它的方言答案，猜 Responses 是 `response.output_item.added`、Anthropic 是 `content_block_start`，于是怀疑表里少一行。**读实现之后否掉**：`PassthroughAssembler.push`（`passthrough.py:158-169`）把「携带归属键且不是闭合事件」的任何事件都算作打开该 item（`self._open.add(item)`），根本不需要知道哪个事件是开启事件。这是一处**真正的方言无关推导**，加一行反而会重新引入不必要的类型学。记下来是因为它是本条最容易误报的邻居。
2. **「§2.6 漏了 `gemini-generate-content` 这条直连腿」——否决。** §2.6 的脚注（`spec.md:95`）已经写明它在路由表里登记但没有 translator 应答、`InboundRoute.implemented` 挡住请求，所以今天不存在该格式的直连腿。措辞准确，不构成缺口。
3. **「§7.1 的 Anthropic 判据 `type == "tool_use"` 漏了 `server_tool_use`／`mcp_tool_use`」——否决为发现，降为观察。** 我怀疑 Anthropic 的 `server_tool_use` 会被误判，但实现的 `requires_client_action`（`anthropic_messages_passthrough.py`）用的是精确相等 `== "tool_use"`，`server_tool_use` 不等于它，答 `False`——而 server 端执行的工具本来就不需要客户端行动，答案正确。该函数的 docstring 还专门论证了「未知 block 类型答 `False` 不是把 Responses 规则反过来」。**没有证据说它错，所以不列为发现。**
4. **「`until-tool-use` 在 Anthropic 腿上会因为 `content_block_stop` 不带 type 而永不触发」——否决，已被修掉。** 这正是 `plan.md:88` 记的第 7 步产物之一：`RawEventBatch.requires_client_action` 扫的是整个 batch 里**携带 item 对象的那个事件**（`_item_object` 找 `item` 或 `content_block` 两个键），不是只读闭合事件。实现已经解决，plan 也记了，不构成发现。
5. **「§3 的 SSE 保真承诺对非流式的 Embeddings 腿是空转」——否决为 nit 都不够。** 「非流式」三个字已经把 §3 排除在外，读者不会误读。
6. **「`_report_failure` 的 `passthrough` 参数在 Anthropic 直连腿接线后会不会传错」——未列，因为不可判定。** 那条腿今天不接线，`carries_upstream_natively` 对它返回 `False`，所以传的是 `False`；接线之后是否会一并改对属未来代码，我不对不存在的代码提发现。
7. **「§9.1 的语义判据应该改成名单」——否决，方向相反。** §9.1 `:444` 自己已经论证过名单必漏（round4 漏了 `Content-MD5`），我同意判据优于名单，不重开。
8. **「plan 第 9 步与第 10 步的顺序应该对调」——否决，无依据。** 我一度觉得可观测迁移应先于 headers，但 plan `:91` 给的理由（第 10 步会改一条 `test_pipeline_app.py` 的断言，那条断言的注释明说要让改动成为一次有意的动作）成立，headers 与它无耦合。**没有理由就不提建议。**

---

## 六 · 搜索面、执行证据与限制

### 判据来源（独立于被检对象）

按 `as-reviewer` 步骤 2 的要求，判据先于被检对象取：

- `docs/.human-controlled/message-format-reshape.md` 的响应头黑名单与「黑名单机制」定义（本轮回核引文所在段，未通读全文——round8 通读过 14 份，本轮不重复）
- `docs/.human-controlled/config.example.yaml` 的 `hook_fix_responses_sse` 段与 `buffer_cap_bytes` 段（回核 round8／round9 引用面）
- `docs/.human-controlled/upstream-retry-and-continuation.md` 的 draining 段与 hand-over 段（回核）
- `.dev/docs/error-envelope/spec.md` §3.1 的直连定义域键（**本轮未重取原文**，沿用 round8 的逐字核验；round9-04 的结论只依赖本规格自己定义域的变化，不依赖那一侧）
- `.dev/docs/sync-refs/sxwxs-ghc-api/260822-round2-disposition.md:62`（`claude-sonnet-5` 的 `unsupported_api_for_model` 实测，本轮实取逐字）
- 项目 `CLAUDE.md` 的 Spec 纪律（活文档、修订记录、转抄同步三条）

### 本轮的执行证据

- `git log --oneline`（`.dev` 与主仓）、`git show --stat`、`git show 1cfa309 -- <spec>`、`git show 68a95b3 -- <spec> <plan>`——三个快照与两次未登记修订的内容逐行确认
- `rg -n 'v11|v12' spec.md plan.md deferred.md` → **空集**（round9-03 的判据）
- `rg -n 'hand_over_supported' src tests .dev docs` → 四处命中，**全在 `.dev` 文档**（round9-08 的判据）
- `rg -n 'def supports|\.supports\(' src/` → `model_provider/types.py:91`、`routing.py:316`／`:321`（核 plan `:95` 的引用真实性）
- `rg -n 'EMBEDDINGS|embeddings' src/app/pipeline/routing.py src/app/pipeline/request.py src/app/server/routes/*.py` → `table.py:39` 的 `streamable=False`
- `rg -n 'assembler.failure|\.failure\b' src/app/pipeline/delivery/stream.py` → 读取点只有 `:396`（round9-05 的判据）
- `rg -ln 'passthrough=True|passthrough_assembler' tests/` → 只有两个单测文件；`rg -n 'response\.failed' tests/` → 定位到 `test_error_envelope.py:479-500` 那条成员断言（round9-06 的判据）
- 全文阅读：`passthrough.py`、`openai_responses_passthrough.py`、`anthropic_messages_passthrough.py`、`delivery_policy.py`

### 限制

**必须如实写明的三条：**

1. **`Write` 被拒。** 报告落在 `/tmp/ghc-review-r9/`，原文见文首。守卫消息逐字：「This subagent's parent bg session hasn't isolated yet, so writes to the shared checkout are blocked.」与 round8 同因。
2. **未在实现 worktree 跑任何测试或探针。** 调用方边界只允许在**主工作树**跑现有测试，而本轮涉及的实现全部在 `260831-passthrough-wiring` 分支上。因此 **round9-01、round9-05、round9-06 三条都是逐环闭合的机械推断，不是观测**。三条的性质不同：round9-01 与 round9-05 是「两份文本逐字不同」「某条通路在代码里不存在」，读代码就是它们的判据，实跑不会增加什么；**round9-06 不是**——它是一条关于运行时输出的预测，我给出了每一环的代码引文，但没有看到那两个字节序列。它是本报告里唯一一条**实跑会改变其证据强度**的发现，我在条目里写了 settle 它的最小命令。
3. **未重取的引用两处**：`error-envelope/spec.md` §3.1 原文、`tests/int/test_pipeline_app.py:2788` 的函数名，都沿用 round8 的逐字核验。两处都不承载本轮任何发现的成立性。

**另外声明一处我没能力核的**：`@ai-sdk/openai` 如何校验 ID 连续性（D-3 的「未核」项）在本轮仍未核，本项目没有它的源码。这一条已经在 Spec 与 deferred 里各自标注，我不重复登记。

---

## 七 · 严重度汇总

| severity | count | finding_id |
|---|---:|---|
| blocker | 1 | round9-01 |
| major | 5 | round9-02、round9-03、round9-04、round9-05、round9-06 |
| minor | 6 | round9-07、round9-08、round9-09、round9-10、round9-11、round9-12 |
| nit | 4 | round9-13、round9-14、round9-15、round9-16 |
| **合计** | **16** | |

**round8 状态**：closed 13、partially-closed 0、not-closed 0。

## 八 · 交接事项

1. **round9-01 与 round9-02 应当同刀改**：两条都改 §2.5 的表（补 `message_stop`、补两行词汇、补「terminal ⊆ control」的约束），且都要同刀改 `passthrough.py:35` 的「six facts」。
2. **round9-06 请优先判**，它是唯一一条会影响「这个分支能不能合」的发现，且我没有实跑证据。若判为真，那条集成测试的断言从 `in` 改成计数是本条最小的回归防线。
3. **round9-04 的 §11 O-1 改写应先于把它送到用户面前**，理由在条目里。
4. **D-5 上交用户的问题面建议收窄**（见第四节末），三个候选里只有一个真的需要用户裁。
5. **本报告未提出任何 gate、覆盖率门、验收状态机或 proof 控制平面**，也未建议 `ruff format`。第四节的 yes/no 是对调用方那一问的回答，不是我建议安装的装置。

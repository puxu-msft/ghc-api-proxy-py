# 评审处置：`cache_control` 子字段与网关 beta 词汇表

对象：[reports/260824-cache-control-and-beta-implementation-review.md](reports/260824-cache-control-and-beta-implementation-review.md)，异源模型（GPT）独立评审，**1 blocker / 2 major / 4 minor**。

处置日期：2026-08-24。**6 条采纳并已落地，1 条（blocker）不由本方处置、交回用户裁决。**

| 编号 | 严重度 | 处置 | 落点 |
|---|---|---|---|
| CCBIR-01 | blocker | **交回用户裁决**，不自行处置 | spec §9 A-8；已向用户提出 |
| CCBIR-02 | major | 采纳，位置集合按官方 schema 补全 | spec §7.1 表；`anthropic_cache_control.py` 的 `_NESTED_CONTENT_BLOCKS` 与顶层 `TOP_LEVEL` |
| CCBIR-03 | major | 采纳，补正文条款并写明适用范围与过期行为 | spec §7.6～§7.8；A-10 迁出待裁决表 |
| CCBIR-04 | minor | 采纳，改为逐处记 loss 并带路径 | `anthropic_cache_control.py` 尾部；spec §7.1 末段 |
| CCBIR-05 | minor | 采纳，四组判别用例全部补齐 | 见下 |
| CCBIR-06 | minor | 采纳，同步活文档引用 | status.md、证据报告 |
| CCBIR-07 | minor | 采纳，三个探针各留两轮逐格输出 | `exp/260824-beta-and-cache-control-probe/raw/` |

## CCBIR-01：`passthrough` 被无条件改写——**我接受这条批评，且不自行处置**

评审的话是：「不要用当前 Spec 自己提出的解释代替裁决」。**这一条说中了。**

我写 §7.3 时引用了两条依据：用户亲笔 `message-translation.md:7`「当我们需要理解和处理时，才分析和处理对应部分」这句授权，以及同族先例——用户亲笔把空 thinking 块的剥离从「可配置」升级为「常驻」。**这两条都成立，但都不足以覆盖本格**，理由是一个我当时没有给足权重的区别：

空 thinking 块的剥离**没有任何用户定义的配置档**。而 `cache_control` **有**，用户亲笔为它写了四档，并且明确把「strip non-standard fields like scope」放进 `sanitize` 那一档、把 `passthrough` 写成 `as-is`。当一个字段已经有了用户写下的语义分档，「需要处理时才处理」这句通用授权就不再是空白处的授权，而是要去覆盖一处已经有人做过的划分。我把前者当成了后者。

我仍然认为「四档管断点、词汇表管键」这个区分本身是有意义的（评审也没有否认这个区分，它否认的是**由我单方面据此改默认行为**）。但那正是需要用户点头的事情，不是我可以用自己写的 Spec 条款去支撑的事情。

**已交回用户**，两个方向都会带上代价：重定义 `passthrough` 允许词汇消毒（要改用户亲笔文档一句话），或 `passthrough` 严格字面（则默认档面对这条 400 的产品行为要另外裁定，因为默认就是 `passthrough`，开箱即 400）。

## CCBIR-02：位置集合只有三处

采纳，且这是本轮最有价值的一条。我原来的三处是**从线上那条 400 的路径反推的**——上游只报了 `system.1`，我据此写了「三处各自独立的 schema」，读起来像是穷举，实际是样本。

按官方请求 schema 补全为七处：顶层、`system[]`、`messages[].content[]`、`tool_result.content[]`、`search_result.content[]`、`document.source.content[]`、`tools[]`。其中**顶层最容易漏**，因为它没有 block 承载，任何按 block 遍历的写法都碰不到它。

采纳评审的两条限制：
- **不做盲递归**，按 block type 分派。盲递归会走进 `tool_use.input`、工具的 JSON Schema 和普通工具输出，那里一个恰好叫 `cache_control` 的键是客户端的数据。
- **`thinking` / `redacted_thinking` 不是遗漏的一处**，官方 schema 不允许它们直接带 marker。评审专门核实了这一点，避免了一次多余的覆盖。

另外独立核实了评审引用的 SDK 事实：`CacheControlEphemeralParam` 逐字就是 `{type, ttl}`，与我从上游 400 实测推出的白名单一致，**两条独立来源同一答案**，已写进 §7.1。

## CCBIR-03：beta 剥离没有规范条款

采纳。这一条命中的是本项目自己的纪律——「Spec 级事实不得只落在 report、status 或代码注释」。我把机制写进了代码注释和 status，却只在待裁决表里留了个 A-10，而 A-10 的措辞（「机制上还没分开」）与同一工作树里已经落地的实现**相反**。

新增 §7.6～§7.8：两层的对照表、内置清单及其精确匹配要求、「加 flag 前必须先测 body 仍合法」的义务、以及适用范围与过期行为。A-10 改写为已闭合并回链正文。

**其中一条我采纳了但没有按建议改实现**：评审指出实现对所有 host 无条件生效而实测只在 enterprise host。我把它写成了 §7.8 的**明知限定**而不是收窄实现，理由是代价不对称——按 §7.7 剥掉后 body 仍合法，所以在一个其实接受该 flag 的 host 上多剥一个，损失是一次没人在用的协商；少剥一个，损失是那个客户端的每个请求。同时写明了「若发现某个 host 因被剥而变差，收窄方式是把清单挂到 provider 上」。这是把未决点变成有名字的限定，不是消除它。

评审对「两个清单是不是话术」的独立判断是「**不是话术**」，并接受并列机制的方向。这一条我原本请它严格审，结论记在这里。

## CCBIR-04：loss 聚成一条

采纳。原实现把 N 处删除聚成一条「3 marker(s)」，而 Spec 自己写的是「每一处删除记一条」。评审给的判据很准：读者要判断的是**哪几个断点被动过**，一条写着数量的记录回答不了。改为逐处记录并带路径；测试同步断言路径集合而不只是「有 loss」。

评审那句「不要让测试把当前实现反向写成规范」也一并采纳——是测试跟着 Spec 改，不是反过来。

## CCBIR-05：四组会静默退化的绿

全部采纳，各补一个最小判别输入，不扩成矩阵：

| 场景 | 补的用例 |
|---|---|
| 白名单退化成「只删 `scope`」 | 未知键用 `invented_2027`，与 `scope` 无关 |
| 从内置 beta 清单删一个成员 | 遍历 `GATEWAY_UNSUPPORTED_BETAS` 逐项断言，新增成员自动被覆盖 |
| guard 从 target format 误改成 inbound | 一个 Responses 入站、Anthropic 出站的正向用例（既有那条只覆盖负向半边） |
| sanitizer 增加 `COUNTING_ONLY` 早退 | 走真实 `handle_count_tokens` 且 body 带 marker |

第四条有先例：同一 topic 的 thinking 订阅者正是被这个变异抓到过假绿（status.md 变异表第 3 行），所以这不是假想的失效形状。

## CCBIR-06：引用不同步

采纳。status 指向 A-10 的那条改指 §7.6～§7.8 正文；status 里「三层」改为七处并注明首版只做了三处；A-10 自身改写为已闭合。**历史报告原件不动**——评审也明确写了不要改归档报告，这与项目规则一致。

## CCBIR-07：第二轮结果没落盘

采纳。`probe_tool_reference.py` 原来只有脚本没有输出，而它承载的恰恰是「剥 beta 后第二轮仍安全」这个最关键、也最容易被漏测的判据。三个探针各跑两轮并落盘（`run-main.txt`、`run-controls*.txt`、`run-responses-tools*.txt`、`run-tool-reference*.txt`），两轮逐格 `diff` 一致；证据报告补 R 系列表。

## 没有采纳的建议

**无。** 七条发现全部采纳，其中 CCBIR-01 的「采纳」形式是交回用户而不是自行实现某一侧——这是评审自己给的处置建议（「在合入前由用户明确裁定二选一」），不是我方对它的削减。

CCBIR-03 有一处采纳方式与建议不同（把 host 范围写成限定而不是收窄实现），理由已在上面写明，并保留了收窄的触发条件。

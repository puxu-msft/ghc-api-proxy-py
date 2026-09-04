# `spec.md`／`acceptance.md` 修订候选 r2 复评

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-spec-revision-candidate-r2.md`。既有规范事实继续以当前 frozen `spec.md`／`acceptance.md` 与空 reasoning 独立裁决为权威；代码只用于核对当前 streaming surface 是否能承载提案。结论强度：下列处置由逐项文本对账支持；两个新 blocker 分别由 recorded upstream event order 与既有 frozen empty-reasoning ruling 直接裁决，足以阻止当前文本交给用户作整体采用。

## r1 八条发现处置复核

| r1 发现 | 复评 | 依据 |
|---|---|---|
| B1 v2 缺 `acceptance.md` 替换文本 | **未生效，仍是 blocker** | r2 `:124-131` 只有改写提纲，没有可直接采用的 replacement；`:127` 还把 exact bytes 留到实现后由产品 producer 生成，违反当前 `acceptance.md:114`「expected 不得调用产品 codec 生成」的独立性要求。候选阶段就必须给出完整 bytes：编码与字段顺序已经冻结，可由独立计算直接得出，不能让被测 producer 定义 oracle。 |
| B2 `i` 与 `spec.md:204` 冲突 | **采纳生效** | r2 `:116-120` 明确要求修订 `:204`，并把 `i`／`n` carve-out 与仍禁止的 upstream item `id` 分开，不再靠缩窄 `item identity` 词义维持旧句。 |
| B3 同时删除又保留「不得无限等待」 | **采纳生效** | r2 `:40-60` 保留「等待必须有上界」，准确标出当前 gate 在 deadline 外，并把甲的定稿显式阻塞在选项 1／2 的用户裁决上；不再同时声称已经删除和暂不改动。 |
| M1 `i` 检不出尾部丢失／合并 | **改法有新问题** | `n` 在一个完整组已知时确能使 `[0,1]→[0]` 变红，assistant turn 分组也消除了跨轮重置歧义；但 streaming producer 在首个 reasoning block 可提交时不知道 response 最终 reasoning 总数，见新 B1。 |
| M2 忽略未知成员会静默吞拼写错误 | **改法有新问题** | r2 `:91-100` 的两个严格 key 集合修掉了原问题；必需 `i`／`n` 在抽象 wire 形态上仍能表达 v1 的 non-empty、summary-only 与 strip 三类合法语义，但 summary-only 改成无 payload carrier 正面覆盖既有 bare-marker 裁决，见新 B2。 |
| M3 producer 切换不可安全回退 | **改法有新问题** | r2 `:135-145` 已承认滚动并存与旧 build 丢 v2 的事实，但「回退须连同 consumer 一起」恰好会让历史 v2 失效；安全的 producer rollback 应保留 v2 consumer，见新 M1。 |
| M4 残留计数错误且漏 `spec.md:530` | **采纳生效，仅余 minor** | r2 `:27-29` 已列出 14 处并补 `:530`，`:23` 也纳入等待上界裁决；`:24` 仍误写「13 处残留」，只是同页计数笔误，不升为 major。 |
| M5 把推论写成实测 | **采纳生效** | r2 `:68-79` 把结论限定到指定样本，明确多个 reasoning 只有范围而无频率，并列 `.added`／`.done` 不同与 final id 10／10 回送成功，不再推出「id 从来不能用」或以日总量代替并发峰值。 |

附带核对：r1 C5 的引用错误也已生效修正，r2 `:26` 使用 `spec.md:469-475`，不再漏掉稳定 Anthropic error 所在的 `:474`。

## 新引入的 blocker 与 major

### B1 — response 总数 `n` 在块级交付时尚不可知

- r2 `:106-108` 要求每个 carrier 写入整个 Responses response 的 reasoning 总数；但 recorded cassette 的顺序是 `reasoning added → reasoning done → message added／done → response.completed`，且前两类 response envelope 的 `output=[]`，只有 terminal 带完整 `output`。
- 当前 parser 在 `responses_stream_parser.py:309-328` 收到 reasoning `output_item.done` 就生成 `CompletedBlock`；frozen spec `:320` 明定 semantic block 不是完整 response，`:514` 以首个完整 block 为可见输出目标，`:546` 禁止 whole-response buffering 取代块级能力。
- 因此首块 producer 无法填写真实 `n`；等 terminal 才写则会让以 reasoning 开头的 stream 全部退化为 whole-response buffering。`n` 方案必须改成可在块提交时确定的合同，不能只补 decoder／acceptance。

### B2 — summary-only 无 payload carrier 覆盖了独立冻结的 bare-marker 裁决

- r2 `:102` 把 absent／empty `encrypted_content` 从 bare marker 改为 `{tag,i,n}` carrier；这与 `spec.md:221,325`、`acceptance.md:141-144` 以及独立裁决 `260807-arbitrate-empty-reasoning.md:14-22,30-33,56` 的唯一合法结果逐字冲突。
- 一 item 一 block与「不伪造 encrypted_content」仍能保持，但 wire 形态已从 bare marker 变成 payload form；「引入 v2」本身没有自动裁决这个额外变化。
- 若该变化确为 `i`／`n` 设计所需，候选必须把覆盖空 reasoning 独立裁决列成明确用户裁决项，并给出对应 spec／acceptance replacement；当前「必须写清」不足以覆盖 frozen ruling。

### M1 — rollback 顺序写反

- r2 `:145` 要求 producer 切换后「连同 consumer 一起回退」，却又承认这样会让已经发给客户端的 v2 signature 失效；这不是回退保护，而是已知兼容性破坏。
- producer 出问题时，安全顺序是 producer 回到 v1、v2 consumer 继续保留，从而同时读取历史 v2 与新 v1；一旦生产过 v2，consumer compatibility 就不能随 producer 一起撤掉。
- 若整 build 回退无法保留新 consumer，应明确写成不支持无损整 build rollback 的部署限制，而不是把破坏性顺序写成「必须」。

### M2 — 检出 `(i,n)` 不一致后的 wire 行为仍未冻结

- r2 `:112` 只说记录 conversion fact、不要「静默」产出错位 input，`:130` 的 acceptance 提纲也只断言产生 fact；两处都没说对应 reasoning group 是继续原序发送、整组丢弃，还是请求失败。
- 各 item 的 `n` 不一致、同一 `i` 携带不同 `n`、缺项／重复等情况因而没有唯一用户可观察结果，也没有矩阵中的 `DEGRADE`／`REJECT` 归属。
- 在 spec 中冻结精确处置并让 acceptance 断言最终 Responses wire／error；conversion fact 不能替代主行为合同。

## Verdict

**needs-fix。** r1 八条中 5 条采纳生效，1 条未生效，2 条改法引入新问题；另有新 blocker 2、新 major 2。尤其 `n` 与块级交付不相容，不能靠补 canonical bytes 或测试消解。当前版本尚不能交给用户整体采用。

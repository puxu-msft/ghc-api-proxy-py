# 候选：`spec.md` / `acceptance.md` 修订（carrier v2 ＋ 等待式准入）

**状态：候选，未落笔。** `spec.md` 与 `acceptance.md` 是 `FINALIZED` 冻结合同，本文不修改它们，只把两处需要改的内容写成可直接采用的替换文本，等用户裁决。

两件事合并在一份里，因为它们改的是同一个冻结文件，一次裁决即可：

- **甲**：准入语义已与实现相反（`spec.md` 要求拒绝，实现按裁决改为等待）。
- **乙**：`引入 v2` 裁决要求新增 carrier 版本，`spec.md:8` 现固定 producer 为 v1。

---

## 甲、等待式准入

### 需要改的规范性条款

| line | 现文要点 | 与实现的关系 |
|---|---|---|
| `spec.md:460` | 「达到全局压力线后，普通 admission control 与有界队列**必须停止新准入**」 | 相反。实现是等待 |
| `spec.md:462` | 「**不得**通过超卖全局预算、**无限等待**、磁盘 spill 或 live forwarding 绕过压力」 | 直接字面冲突。实现正是无超时等待 |
| `spec.md:467` ＋ `:468-473` | 「并发 bridge 数」列入必须可观测的 limit 类别，而所有 limit violation「**在可能时于 upstream 调用前拒绝**」并「产生稳定的 Anthropic error」 | 相反。按此 spec，超并发应当报错 |
| `spec.md:461` | 容量压力产生 `capacity` 终态 | 不再有 capacity 终态 |
| `acceptance.md:41`、`:243` | 验收 oracle 要求「拒绝新 admission 最小止血」并产生 capacity／limit 终态 | **照字面，正确实现会被判红** |

其余 12 处（`spec.md:8/23/249/453/454/463/496/499/504/516/537/548/567`）是全局内存预算的残留描述，机制已随 `reservation.py` 删除，逐行替换文本见 `docs/tmp/260820-memory-budget-doc-references.md` 的 A、C 两节，此处不重复。

### 建议替换文本

`spec.md:460-463` 四条整体替换为：

> - 进程级并发由 `proactive_rate_limiter.max_inflight` 约束。超过上限的请求在 ASGI 层信号量上**按到达顺序等待**，不被拒绝、不返回 429、连接不关闭。该上限计的是**请求**而非连接：keep-alive 下一个连接承载多个请求，成本在请求侧。`0` 表示关闭该门，不表示拒绝一切准入。
> - supervisor 探针（`/health`、`/health/liveness`、`/health/readiness`、`/metrics`）不占用名额。饱和恰是 supervisor 最需要应答的时刻，排队的应答超时后会被读成「已死」。
> - 单请求累计缓冲字节由 `client_delivery.buffer_cap_bytes` 约束，在 block 进入 buffer **之前**校验，因此任何时刻都不会超出。
> - 不得通过磁盘 spill 或 live forwarding 绕过压力。**等待本身即为设计**，不是绕过。queue depth 与 upstream frame limit 各自仍有 hard limit。
> - 若 deadline、cancel 或 shutdown 使请求无法继续，产生对应的 timeout／abort 终态。当前不完整 block 不得提交，已提交前缀不得重复。

`spec.md:467` 的 limit 清单：删去 `global buffered bytes`，并把 `并发bridge数` **移出该清单**——它现在不是 limit violation，而是等待，留在清单里会让 `:468-473` 要求实现返回错误。保留 `per-request buffered bytes`。

`acceptance.md:41`、`:241`、`:243`、`:246`、`:438`：REL-06 整体重写。`request_budget` / `global_budget` 两个配置键已不存在，`0 < request_budget < global_budget` 这个前置条件在当前代码里**不可满足**，该验收样本现在不可执行。可保留的部分只有：慢 downstream ＋ 有界 queue 导致生产者被背压、不提交 partial block、已提交前缀不重复。

### 一个尚未裁决的点

`spec.md:462` 禁止「无限等待」这一条，**在机制改变之后仍然指着一个真实的东西**，不该当作单纯的过时文字删掉。

实测：`client_request_deadline`（默认 3600 秒）在 `handle_bounded` 内起算，而限流门在它外面，所以**排队时间不计入任何 deadline**——按真实层级搭的探针里，排队请求在 0.30 秒 deadline 下总耗时 0.35 秒却没有超时。

50 并发对一天 429 个请求基本够不着，但队列一旦形成就没有上界。三条路写在 `docs/.human-controlled-candidates/proactive-rate-limiter.md`，模型倾向「把排队时间纳入 `client_request_deadline`」——仍是等待，超时按 504 收尾而非按准入拒绝收尾。**未裁决前不动代码，也不动这一条 spec。**

---

## 乙、carrier v2

### 为什么需要新版本，而不是扩展 v1

`spec.md:220` 自己写了出口：「新增字段或语义**必须发布新 version**，不能在 v1 payload 中静默扩展。」

代码侧对应的硬约束在 `src/app/pipeline/translation_driver/reasoning_carrier.py:111`：

```python
if not isinstance(document, dict) or document.keys() != _PROJECT_V1_FIELDS:
    return None
```

**精确 key 集合比对**——v1 payload 多一个字段就被判 `project_malformed_v1`。这是 v1 无法扩展的机制原因，不是疏漏。

### 事实基线

以下全部来自本轮实测，非推断，报告见 `docs/tmp/260820-reasoning-item-identity-facts.md` 与 `docs/tmp/260820-copilot-api-js-reasoning-identity.md`：

| 事实 | 证据规模 |
|---|---|
| 上游**每个** reasoning item 都带 `id`，但**不是** `rs_…`，而是 420–436 字符的 base64 不透明块 | 894/894（08-18 库）＋ 3110（08-11 库），`rs_` 前缀 0 个 |
| 同一 item 在 `.added` 与 `.done` 上的 `id` **完全不同** | 446/446 对全部不同，无一相同；`encrypted_content` 哈希交集为 0 |
| 请求侧回送的 `encrypted_content` 逐字节等于 `.done` 那一份 | 313/313 |
| 本产品路径回送时**从不带 `id`**，上游全部正常接受 | 6 个库、174,597 次出现、反例 0 |
| 一个请求里出现多个 reasoning item 是**常态** | 每数组 1–135 个；全库无字节相同的重复项 |
| reasoning 的后继 100% 是 `function_call` / 另一个 `reasoning` / `message:assistant` | 7271 次统计 |
| **数组下标是唯一表达归属关系的载体**——item 内部无任何指向兄弟项的字段 | 键集恒为 `{encrypted_content, summary, type}` |
| copilot-api-js 曾因在 request input item 上**伪造 `id`** 被上游 400 | commit `684761e40`，错误原文 `400 Invalid 'input[1].id'` |

### 提案：v2 wire contract

**Version 与 marker**：payload prefix 固定 `ghc-api-proxy:synthetic-reasoning:v2:`，bare marker 固定 `ghc-api-proxy:synthetic-reasoning:v2`。新 producer 只输出 v2 两态。

**Consumer 识别顺序**：项目 v2 → 项目 v1 → upstream v1。v1 **永久保留可读**——客户端手里存着历史会话，那些 signature 是 v1 的，停止解码等于让旧会话的 reasoning 全部失效。

**Payload 编码**：与 v1 同构——紧凑 UTF-8 JSON、无 padding base64url。

**字段**：

| 字段 | 必需 | 内容 |
|---|---|---|
| `tag` | 是 | 常量 `openai.responses.reasoning.encrypted_content` |
| `encrypted_content` | 否 | 非空字符串，value-exact 保存 Responses 原值。缺失即 summary-only |
| `i` | 否 | **位置**：该 reasoning item 在本次响应全部 reasoning item 中的 0 基序号 |

**与 v1 的关键差异——decoder 容忍未知成员。** v2 decoder 按类型校验必需成员，**忽略**不认识的成员，不做 key 集合比对。这样 v3 新增字段时 v2 消费者不会把它判成 malformed。这正是 v1 做不到的事。

**明确不采用 copilot-api-js v2 的「重编码逐字节相等」backstop。** 他们那道检查是该解码路径上唯一有判别力的检查（其自身变异测试显示：改坏前两道检查全绿，只有改坏 backstop 才变红），代价是扩展字段能否通过取决于 key 的字典序——同一个字段有时通过有时被拒。这是**不可复制的缺陷**，不是可借鉴的设计。

### `i` 用来做什么——以及不做什么

**做**：检测。回送时按 Anthropic thinking block 顺序重建，若恢复出的 `i` 序列不是从 0 起的连续升序，说明客户端丢弃、重排或合并了 thinking block。此时记录 conversion fact，而不是静默产出一个位置错乱的 `input` 数组。

这是「利用 reasoning 作为载体透传翻译中位置信息」的可落地形态：位置被透传过去，反向翻译**能够校验**它。

**不做**：不用 `i` 去重排。上游按源序接受 reasoning、text、function_call，Anthropic 自身的布局规则又要求 thinking block 领起 assistant 回合，所以保持源序**已经**产出 Responses 期望的形状；拿 `i` 去主动重排等于替客户端决定它的意图。

**不含 item `id`**，四条理由都有实测支撑：

1. 它**不稳定**——同一 item 在 `.added` 与 `.done` 上是两个不同的值，446/446 全变。拿它当身份从一开始就是错的。
2. 它**很大**——420–436 字符；一轮最多观测到 135 个 reasoning item，全部编码进 signature 约 76 KB 纯开销，且对每一轮对话重复承担。
3. 它**不必要**——174,597 次不带 `id` 的回送，上游全部正常接受，反例 0。
4. `spec.md:220` 已明文禁止 carrier 编码 item id。**本轮证据支持这条禁令是对的，建议原样保留。**

数据同时显示带 `id` 回送也能被上游接受（`openai-responses` 透传路径 10/10 成功），所以理由是「无用且昂贵且不稳定」，**不是**「会被上游拒绝」。这个区别要写清楚，否则将来有人看到透传路径成功就以为禁令是误解。

### 需要一并修订的既有条款

- `spec.md:8`「reasoning signature 的 producer 固定使用本项目主 v1」→ 改为 v2；该句位于「**已裁决且不可重开**」段落，改动它需要用户明示这一条被本次裁决覆盖。
- `spec.md:204` 「item identity……不得塞进 carrier」→ **保持不变**。位置不是身份，`i` 不违反它。
- `spec.md:182`、`:325` 一 item 一 block、不得跨 item 聚合 → **保持不变**，v2 不改变基数合同。

### 未决、需要用户点头的两点

1. **是否消费 `copilot-api-js` v2**。他们的 v2 信封已存在且读取端在用，但**没有生产写入端**（唯一调用点在当前类型联合下不可达，其代码注释自陈是有意为之）。现在就实现兼容是为一个尚未出现的格式写代码。倾向：**暂不实现，记录在案**，等他们真正开始输出再做。此处按 `no-silently-cut-but-defer` 留痕，不是静默砍掉。
2. **切换 producer 会改变客户端可见字符串**。所有新 thinking block 的 `signature` 前缀从 `…:v1:` 变成 `…:v2:`。消费侧我们自己两代全收，但若有第三方按前缀匹配，会受影响。

---

## 落地顺序（若两项都获准）

1. 修订 `spec.md` 与 `acceptance.md`（甲＋乙），独立评审。
2. 实现 v2 编解码 ＋ 容忍未知成员的 decoder，producer 仍留在 v1。
3. 接上 `i` 的产出与回送校验，补对应测试。
4. 最后一步才切换 producer 到 v2——它是唯一改变客户端可见字符串的动作，单独成片以便回退。

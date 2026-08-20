# 候选 r2：`spec.md` / `acceptance.md` 修订（carrier v2 ＋ 等待式准入）

**状态：候选，未落笔。** 取代 `docs/tmp/260820-spec-revision-candidate.md`（r1）。r1 的评审见 `docs/tmp/260820-review-spec-revision-candidate.md`，verdict 为 needs-fix，blocker 3、major 5。

## r1 处置表

| 发现 | 处置 | 级别 | 说明 |
|---|---|---|---|
| C3／B2 `i` 就是 item identity | **采纳** | A | 评审对。`:204` 用宽词 `item identity`，`:220` 另用窄词 `item id`，两句并存说明前者不是后者的同义反复；而 `i` 的用途正是在一个 response 内指认某个 item。r1 说「位置不是身份、`:204` 不受影响」是**为保留旧句而缩窄词义**。本稿改为**显式修订 `:204`** |
| B1 v2 缺 acceptance 替换文本 | **采纳** | A | 已核：`acceptance.md:108-111` 明文「默认只输出 payload prefix `ghc-api-proxy:synthetic-reasoning:v1:`」是硬 oracle，正确的 v2 producer 会被判红。本稿补齐 |
| B3 同时删除又保留「不得无限等待」 | **采纳** | A | r1 自相矛盾。本稿**不删该禁令**，改为待裁决的条件文本 |
| M1 ordinal 检测不到尾部丢失与合并 | **采纳** | C | 评审的反例成立：`[0,1]` 丢末项后是 `[0]`，仍满足「从 0 起连续」。本稿加 `n`（总数）并定义分组范围 |
| M2 「忽略未知成员」会静默吞掉拼写错误 | **采纳** | C | 评审第二点更关键：**版本在 prefix 里**，真正的 v3 有自己的 prefix，v2 decoder 不需要靠吞未知成员去读它。r1 的容忍前提本身站不住。本稿改回**严格 key 集合** |
| M3 切 producer 是最不可回退的一步 | **采纳** | C | 已核 `spec.md:246`：旧 build 遇 `project_unknown_version` 会丢掉整个 thinking block。本稿重写迁移段 |
| M4 计数错误且漏 `spec.md:530` | **采纳** | D | 已核 `:530` 确有全局 budget 条款，`:23` 确要求「并发、时间均有边界」 |
| M5 把推论写成实测 | **采纳** | C | 尤其中间一条：另一份报告记录 final id 被 10/10 原样回送且成功，所以「拿它当身份从一开始就是错」是错的措辞 |
| C5 引用范围 `:468-473` 漏引 `:474` | **采纳** | D | 已改为 `:469-475` |

**无不采纳项。**

---

## 甲、等待式准入

### 需要改的条款（13 处残留 ＋ 5 处语义冲突）

语义冲突（与实现相反，必须改）：`spec.md:460`、`:461`、`:462`、`:467` ＋ `:469-475`、`acceptance.md:41`／`:243`。
全局内存预算残留（机制已删）：`spec.md:8`、`:23`、`:249`、`:453`、`:454`、`:463`、`:496`、`:499`、`:504`、`:516`、`:530`、`:537`、`:548`、`:567`——**14 处**（r1 写「12 处」是错的，且漏了 `:530`）。逐行替换文本见 `docs/tmp/260820-memory-budget-doc-references.md` A、C 两节，本稿只补该报告没有覆盖的 `:530`：

> `:530` 现文「global budget／queue 压力只产生普通 admission control、backpressure 或明确 capacity／timeout 终态」→ 「queue 压力只产生 backpressure 或明确 timeout 终态；不再有 global budget，也不再有 capacity 终态。」

### 替换文本

`spec.md:460-461` 替换为：

> - 进程级并发由 `proactive_rate_limiter.max_inflight` 约束。超过上限的请求在 ASGI 层信号量上**按到达顺序等待**，不被拒绝、不返回 429、连接不关闭。该上限计的是**请求**而非连接。`0` 表示关闭该门，不表示拒绝一切准入。
> - supervisor 探针（`/health`、`/health/liveness`、`/health/readiness`、`/metrics`）不占用名额。饱和恰是 supervisor 最需要应答的时刻，排队的应答超时后会被读成「已死」。
> - 单请求累计缓冲字节由 `client_delivery.buffer_cap_bytes` 约束，在 block 进入 buffer **之前**校验，因此任何时刻都不会超出。
> - 若 deadline、cancel 或 shutdown 使请求无法继续，产生对应的 timeout／abort 终态。当前不完整 block 不得提交，已提交前缀不得重复。

`spec.md:462` ——**保留「不得无限等待」，只删掉已不存在的机制**：

> 不得通过磁盘 spill 或 live forwarding 绕过压力。**准入等待必须有上界**，且必须响应 client cancel 与 shutdown。queue depth 与 upstream frame limit 各自仍有 hard limit。

`spec.md:467`：删去 `global buffered bytes`；**`并发bridge数` 移出 limit 清单**——它现在是等待而非 violation，留在清单里会让 `:469-475` 要求实现返回错误。保留 `per-request buffered bytes`。

### 这一条必须先裁决，否则甲无法定稿

上面把「准入等待必须有上界」保留了下来，**而当前实现没有上界**——这不是文字问题，是实现与规范的实质缺口：

`client_request_deadline`（默认 3600 秒）在 `handle_bounded` 内起算，限流门在它外面，所以排队时间不计入任何 deadline。结构依据：`pipeline_app.py:391-394` 挂载 middleware，`admission.py:47-48` 先取名额再调用内层 app，`pipeline_app.py:224` 进入路由后才调 `handle_bounded`，`handler.py:190-195` 在其内部才进入 `asyncio.timeout`。**（该结构结论已由评审独立复核确认。另有一次探针测量得到 0.30 秒 deadline 下排队请求总耗时 0.35 秒未超时，属旁证，命令输出未随文归档。）**

`spec.md:23` 另外要求「并发、时间均有边界」，无上界等待同样与它冲突。

三条路（详见 `docs/.human-controlled-candidates/proactive-rate-limiter.md`）：

1. 保持无上界——最贴合裁决原话，但需同时删掉 `:462` 的「不得无限等待」与 `:23` 的「时间有边界」，**扩大了裁决范围**。
2. **把排队时间纳入 `client_request_deadline`**——仍是等待，超时按 504 收尾而非按准入拒绝收尾。上面的替换文本按这条写。
3. 给排队单独一个配置键——多一个键，收益存疑。

模型倾向 2。**未裁决前不动代码，甲也不能定稿**——因为选 1 与选 2 的 spec 文本不同。

---

## 乙、carrier v2

### 事实基线

以下均为**指定样本内的实测**，非全称断言。证据：`docs/tmp/260820-reasoning-item-identity-facts.md`、`docs/tmp/260820-copilot-api-js-reasoning-identity.md`。

| 事实 | 样本 | 强度 |
|---|---|---|
| 上游 reasoning item 带 `id`，形态为 420–436 字符 base64 块，非 `rs_…` | 894（08-18 库）＋ 3110（08-11 库），`rs_` 前缀 0 | 样本内确定；**不构成对未来上游的承诺** |
| 同一 item 在 `.added` 与 `.done` 上的 `id` 不同 | 446/446 对全不同 | 样本内确定。**结论限定为：`.added` 的 id 无法与 `.done` 关联，因此不能作流内稳定标识**——不等于 final id 不可用 |
| final id 原样回送可被上游接受 | `openai-responses` 透传路径 10/10 成功 | 存在性证据。**这条与上一条并列写出，因为它证伪了「id 从来不能用」这种说法** |
| 本产品路径回送**从不**带 `id`，上游全部接受 | 6 个库、174,597 次出现、反例 0 | 样本内确定，跨 2026-08-06 至 08-20 |
| 请求侧回送的 `encrypted_content` 逐字节等于 `.done` | 313/313 | 样本内确定 |
| 一个 `input` 数组里出现多个 reasoning | 每数组 1–135 | **只给出观测范围，未给出大于 1 的频率分布**；因此只说「多 reasoning 确有发生且规模可观」，不说「是常态」 |
| reasoning 的后继恒为 `function_call`／另一 `reasoning`／`message:assistant` | 7271 次 | 样本内确定 |
| 数组下标是唯一表达归属的载体 | 键集恒为 `{encrypted_content, summary, type}` | 样本内确定 |

### 为什么必须发新版本

`spec.md:220` 自己写了出口：「新增字段或语义必须发布新 version」。代码侧的硬约束在 `reasoning_carrier.py:111`——`document.keys() != _PROJECT_V1_FIELDS` 是**精确 key 集合比对**，多一个字段即判 malformed。

### v2 wire contract

**Version 与 marker**：payload prefix `ghc-api-proxy:synthetic-reasoning:v2:`，bare marker `ghc-api-proxy:synthetic-reasoning:v2`。

**Consumer 识别顺序**：项目 v2 → 项目 v1 → upstream v1。**v1 永久保留可读**——客户端手里存着历史会话，停止解码等于让旧会话的 reasoning 全部失效。

**编码**：紧凑 UTF-8 JSON、无 padding base64url，与 v1 同构；producer 字段顺序固定为 `tag`、`encrypted_content`、`i`、`n`（缺省项跳过）；duplicate key 判 malformed；decode 后再 encode 必须等于原 payload（沿用 `:246` 的 canonical gate）。

**字段与严格 key 集合**——**不采用「忽略未知成员」**。版本在 prefix 里，真正的 v3 会有自己的 prefix，v2 decoder 无须靠吞未知成员去读它；而容忍未知成员会把 `encrypted_contnet` 这类拼写错误静默降级成 summary-only 而不是判 malformed。合法 key 集合恰好两个：

| 形态 | key 集合 | 何时使用 |
|---|---|---|
| 有 payload | `{tag, encrypted_content, i, n}` | `encrypted_content` 非空 |
| 无 payload | `{tag, i, n}` | summary-only（`encrypted_content` 缺失或为空） |

`tag` 仍为常量 `openai.responses.reasoning.encrypted_content`。`i`、`n` 为非负整数，`0 <= i < n`。

**与 v1 的行为差异（必须写清）**：v1 对 summary-only 发 **bare marker**；v2 改为发**无 payload 形态的 carrier**，因为 summary-only item 同样占据一个位置，用 bare marker 会丢掉它的 `i`／`n`。v2 bare marker 只保留给 `stripThinkingSignature` 这一条显式有损路径。

### `i` 与 `n`：能检测什么，不能检测什么

**分组范围**：`n` 是**同一个 Responses response 内 reasoning item 的总数**，`i` 是该 item 在其中的 0 基序号。跨轮历史里会有多组 `(i, n)`，按 assistant turn 分组校验；不得跨轮拼接。

**能检测**：前缀丢失、乱序、空缺、重复，以及——因为有 `n`——**尾部丢失与合并**（恢复出的 item 数小于 `n`）。这正是 r1 只有 `i` 时检测不到的那一类，评审的反例 `[0,1] → [0]` 在有 `n` 后可检出。

**不能检测**：`stripThinkingSignature` 路径下的 bare marker 无 payload，因而无 `(i, n)` 可校验；同一轮内全部 thinking block 被整体丢弃时无残留可比对。这两类**明确排除在承诺之外**。

**检测到之后做什么**：记录 conversion fact，不静默产出位置错乱的 `input`。**不用 `i` 主动重排**——上游按源序接受，Anthropic 自身规则又要求 thinking 领起回合，保持源序已经是对的形状。

### 必须一并修订的既有条款

- **`spec.md:204`** 现文：「item identity、resolved model 与 upstream identity 只能作为内部 typed facts 保存，不得塞进 carrier。」→ **必须显式修订**，否则 v2 同时要求并禁止 `i`。建议改为：

  > resolved model 与 upstream identity 只能作为内部 typed facts 保存，不得塞进 carrier。carrier 可以承载 **response 内的位置事实**（`i`／`n`），用于回送时校验 item 是否被丢弃、移位或合并；除此之外不得承载任何 item 标识，尤其不得承载上游 item `id`。

- **`spec.md:220`** 「carrier 不编码 item id……」→ **保留 `item id` 禁令**，理由改为可核验的三条：不稳定（`.added`／`.done` 不同）、昂贵（420–436 字符 × 每轮多项）、不必要（174,597 次不带 id 被接受）。**同时写明它不是因为会被上游拒绝**——数据显示带 final id 回送 10/10 成功。不写清这一点，将来有人看到透传路径成功就会以为禁令是误解。
- **`spec.md:8`** 「producer 固定使用本项目主 v1」位于「已裁决且不可重开」段 → 改为 v2，需用户明示该条被本次裁决覆盖。
- **`spec.md:182`、`:325`** 一 item 一 block、不得跨 item 聚合 → **不变**，v2 不改基数合同。

### `acceptance.md` 替换文本（r1 缺失，B1）

- **`:108-111`「双格式独立 oracle」**：现文把「默认只输出 payload prefix `ghc-api-proxy:synthetic-reasoning:v1:` 或 bare marker」冻结为硬 oracle。→ 改为默认只输出 v2 两态；v1 与 upstream v1 降为**consumer-only** oracle。
- **新增 v2 producer canonical vectors**：至少四条——有 payload、summary-only、`i=0,n=1`、`i>0,n>1`；每条给出完整 signature 字符串。（具体 bytes 待实现后由 producer 生成并回填，本稿不臆造。）
- **新增识别顺序 oracle**：同一 consumer 依次喂 v2／v1／upstream v1／foreign 四类输入，前三类恢复、第四类不恢复。
- **新增 mixed-history oracle**：同一 conversation 内混有历史 v1 与新 v2 signature，逐 block 各按自身版本恢复，不得因存在 v1 而整轮降级。
- **新增 `i`／`n` 判据**：完整序列通过；缺项、乱序、重复、以及 item 数小于 `n` 各产生一条 conversion fact 而非静默通过。
- **`:36-37`、`:141-144`、`:439`** 中以 v1 为 producer 预期的行描述同步改为 v2。

### 迁移与回退（M3）

**切 producer 是本次唯一改变客户端可见字符串的动作，也是最不可回退的一步**——r1 说它「单独成片以便回退」是错的：

- 旧 build 遇到 v2 signature 会分类为 `project_unknown_version`，按 `spec.md:246` **丢掉整个 thinking block**。所以 producer 一旦切换，回退到旧 build 会让已发出的 v2 signature 在下一轮全部失效。
- 滚动部署期间新旧实例并存，命中旧实例同样如此。

因此顺序必须是：

1. 修订 `spec.md` 与 `acceptance.md`（甲＋乙），独立评审。
2. 实现 v2 编解码与严格校验，**consumer 先行**，producer 仍留 v1。
3. **等 consumer 侧完全铺开**（所有实例都能读 v2）之后，才切 producer。
4. 切换后若需回退，必须**连同 consumer 一起**回退，且接受期间已发出的 v2 signature 失效；这一点要在切换前写进部署记录，不能当作普通可逆片。

### 未决、需要用户点头的两点

1. **是否消费 `copilot-api-js` v2**。他们的 v2 信封已存在且读取端在用，但**没有生产写入端**（唯一调用点在当前类型联合下不可达，其代码注释自陈有意为之）。倾向**暂不实现、记录在案**，等他们真正输出再做。按 `no-silently-cut-but-defer` 留痕，不是静默砍掉。
2. **`spec.md:8` 属「已裁决且不可重开」**，改它需要用户明示覆盖。

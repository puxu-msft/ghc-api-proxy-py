# 候选 r3：`spec.md` / `acceptance.md` 修订（carrier v2 ＋ 等待式准入）

**状态：候选，未落笔。** 取代 r3（`260820-spec-revision-candidate-r3.md`）。r3 复评见 `260820-review-spec-revision-candidate-r3.md`：blocker 0、major 2，四条 canonical vector 已由独立重算逐字节确认。本稿修掉那两条 major，其中 M2 使能力边界**变好**了——详见下方能力表的更正。

## r3 复评处置表

| 发现 | 处置 | 级别 | 说明 |
|---|---|---|---|
| M1 `DEGRADE` 未落进冻结的字段处置矩阵 | **采纳** | C | 补矩阵行。另核：`spec.md:142` 定义 `DEGRADE` 为「请求可继续，但损失必须作为结构化 `ConversionFact` 进入 History、metrics 与 trace」，`:179` 的 refusal 行已有 `TRANSFORM`＋`DEGRADE` 组合标签先例，与本例语义一致 |
| M2 bare marker 是否占 `i` 序位未定义 | **采纳，并更正能力表** | C | 评审对，而且这一条**推翻了我自己写的一句悲观结论**：冻结校验算法后，中途 bare marker 被丢**是可检出的**，只有**尾部**丢失不可检 |

**无不采纳项。**


| 发现 | 处置 | 级别 | 说明 |
|---|---|---|---|
| 新 B1 `n` 在块提交时不可知 | **采纳，删除 `n`** | A | 评审对，且这条推翻了 r2 的核心设计。已核：parser 在 reasoning `output_item.done` 即生成 `CompletedBlock`，而总数只在 `response.completed` 才存在；写 `n` 等于把以 reasoning 开头的 stream 全部退化成 whole-response buffering，`spec.md:546` 明禁 |
| 新 B2 summary-only 新形态覆盖冻结裁决 | **采纳，恢复 bare marker** | A | 评审对。`260807-arbitrate-empty-reasoning.md` 是独立裁决，「引入 v2」没有自动覆盖它 |
| 新 M1 rollback 顺序写反 | **采纳** | C | 评审对，我写反了。一旦发出过 v2，consumer 必须**保留**；回退的是 producer |
| 新 M2 `i` 不一致后的 wire 行为未冻结 | **采纳** | C | 补 `DEGRADE` 归属与可观察结果 |
| r1-B1 acceptance vectors 仍未生效 | **采纳，本稿给出 bytes** | A | 评审对：`acceptance.md:114` 要求 expected 不得由产品 codec 生成，所以「实现后回填」不成立。本稿的 vectors 由**独立脚本**按规范文字直接计算，未 import 任何 `app.*` |
| r1-M4 残余 minor（`:24` 写「13 处」） | **采纳** | D | 本稿统一为 14 处 |

**无不采纳项。**

---

## 头号问题：你的两条指示在此处互相拉扯

这一点必须先说，因为它不是我的设计缺陷，而是两条既有裁决的交汇处，只有你能定。

- 你要求**块级交付**：一个完整 Anthropic content block 就是最小可观察提交单元，不得退化为整响应缓冲。
- 你要求**用 reasoning 作载体透传翻译中的位置信息**。

块级交付意味着：第一个 thinking block 在它自己的 `output_item.done` 到达时就必须发出去，而**那一刻本轮总共会有几个 reasoning item 是不存在的信息**——它只在 `response.completed` 才出现。

因此 carrier 里能放的只有「我是第几个」（`i`），放不了「一共几个」（`n`）。

**校验算法（本稿冻结的那一个）**：`i` 是该 item 在**同一 assistant turn 全部 reasoning item**（含 summary-only）中的 0 基序号。回送时，把该 turn 恢复出的 reasoning block 按源序编号 0、1、2……，然后要求**每个带 payload 的 carrier 的 `i` 等于它自己的序号**。bare marker 不带 `i`，只占序号、不参与比对。

这直接决定了能验出什么：

| 客户端做了什么 | 能否发现 | 为什么 |
|---|---|---|
| 打乱顺序 | **能** | `[p1, p0]` → 位置 0 上的 `i` 是 1，不等 |
| 重复某块 | **能** | `[p0, p0]` → 位置 1 上的 `i` 是 0，不等 |
| 丢掉开头若干块 | **能** | `[p1, p2]` → 位置 0 上的 `i` 是 1，不等 |
| 丢掉中间的 payload 块 | **能** | `[p0, p2]` → 位置 1 上的 `i` 是 2，不等 |
| **丢掉中间的 summary-only 块** | **能** | `[p0, bare, p2]` 丢中间 → `[p0, p2]`，位置 1 上的 `i` 是 2，不等。**这一条是 r3 写错的**——r3 说不能，实际上只要 bare 占序号就能 |
| 合法的 bare 夹在中间 | **不误报** | `[p0, bare, p2]` 原样 → 位置 0 的 `i` 是 0 ✓、位置 2 的 `i` 是 2 ✓ |
| **丢掉末尾若干块** | **不能** | `[p0, p1, p2]` 丢末两块后是 `[p0]`，位置 0 的 `i` 是 0 ✓，与本来只有一块无法区分 |
| **把末尾若干块合并成一块** | **不能** | 同上 |
| **丢掉末尾的 bare marker** | **不能** | 它不带 `i`，尾部又无后继可比 |

**所以边界恰好是「尾部」**：任何**尾部**丢失或合并都检不出，其余（乱序、重复、前缀丢失、中途空洞，无论丢的是 payload 还是 bare）都能检出。这比 r3 声称的要好。

**这仍然是尽力而为、不是完备的。** 尾部这个洞是块级交付的直接代价，补不上——要补就得知道总数，要知道总数就得等整个响应，那正是你否掉的做法。

**需要你裁决**：在这个能力边界下，是否仍然值得把 producer 切到 v2（那会改变客户端可见的 `signature` 字符串，且如下文所述是本次唯一不可逆的动作）。三个选择：

1. **照此实现 v2**——接受尽力而为的校验，拿到乱序／重复／前缀丢失／中间空洞的检出能力。
2. **先只做 v2 信封、不放 `i`**——把可扩展的版本化载体先立起来（v1 因精确 key 集合比对无法扩展），位置留到有具体生产场景再说。
3. **暂不动 v2**——保持 v1，位置能力搁置。

模型倾向 **1**：位置检出虽不完备，但乱序与重复是真实会发生且当前**完全静默**的失真；而 v2 信封无论如何都要立（`:220` 已规定新增字段必须发新版本）。

---

## 甲、等待式准入

### 需要改的条款

语义冲突（与实现相反）：`spec.md:460`、`:461`、`:462`、`:467` ＋ `:469-475`；`acceptance.md:41`、`:243`。
全局内存预算残留：`spec.md:8`、`:23`、`:249`、`:453`、`:454`、`:463`、`:496`、`:499`、`:504`、`:516`、`:530`、`:537`、`:548`、`:567` ——**14 处**。逐行文本见 `260820-memory-budget-doc-references.md` A、C 两节；该报告未覆盖的 `:530` 补充如下：

> `:530` → 「queue 压力只产生 backpressure 或明确 timeout 终态；不再有 global budget，也不再有 capacity 终态。」

`spec.md:460-461` 替换为：

> - 进程级并发由 `proactive_rate_limiter.max_inflight` 约束。超过上限的请求在 ASGI 层信号量上**按到达顺序等待**，不被拒绝、不返回 429、连接不关闭。该上限计的是**请求**而非连接。`0` 表示关闭该门。
> - supervisor 探针（`/health`、`/health/liveness`、`/health/readiness`、`/metrics`）不占用名额。
> - 单请求累计缓冲字节由 `client_delivery.buffer_cap_bytes` 约束，在 block 进入 buffer **之前**校验。
> - 若 deadline、cancel 或 shutdown 使请求无法继续，产生对应的 timeout／abort 终态。当前不完整 block 不得提交，已提交前缀不得重复。

`spec.md:462` ——**保留「不得无限等待」的意图**：

> 不得通过磁盘 spill 或 live forwarding 绕过压力。**准入等待必须有上界**，且必须响应 client cancel 与 shutdown。queue depth 与 upstream frame limit 各自仍有 hard limit。

`spec.md:467`：删 `global buffered bytes`；**`并发bridge数` 移出 limit 清单**，否则 `:469-475` 会要求实现返回错误。

### 甲的定稿卡在这里

上面保留了「准入等待必须有上界」，**而当前实现没有上界**。结构依据（评审已独立复核）：`pipeline_app.py:391-394` 挂 middleware → `admission.py:47-48` 先取名额 → `pipeline_app.py:224` 才进 `handle_bounded` → `handler.py:190-195` 才进 `asyncio.timeout`。`spec.md:23` 亦要求「时间有边界」。

三条路（详见 `docs/.human-controlled-candidates/proactive-rate-limiter.md`）：**保持无上界**（需同时删掉 `:462`／`:23` 的相关要求，扩大裁决范围）／**纳入 `client_request_deadline`**（上面按这条写）／**单独配置键**。模型倾向第二条。

---

## 乙、carrier v2

### wire contract

**Marker**：payload prefix `ghc-api-proxy:synthetic-reasoning:v2:`，bare marker `ghc-api-proxy:synthetic-reasoning:v2`。
**识别顺序**：项目 v2 → 项目 v1 → upstream v1。**v1 永久保留可读**，否则客户端手里的历史会话全部失效。
**编码**：紧凑 UTF-8 JSON、无 `=` padding 的 base64url；producer 字段顺序固定 `tag`、`encrypted_content`、`i`；duplicate key 判 malformed；沿用 `:246` 的 canonical base64url gate（decode 再 encode 必须等于原 payload）。

**严格 key 集合，恰好一个**（不采用「忽略未知成员」——版本在 prefix 里，v3 有自己的 prefix，v2 解码器无须吞未知成员去读它；容忍反而会把 `encrypted_contnet` 这类拼写错误静默降级）：

| 形态 | key 集合 | 何时使用 |
|---|---|---|
| payload carrier | `{tag, encrypted_content, i}` | `encrypted_content` 非空 |
| bare marker | 无 payload | `encrypted_content` 缺失或为空；以及 `stripThinkingSignature` |

`tag` 恒为 `openai.responses.reasoning.encrypted_content`；`i` 为非负整数，语义与校验算法见上文头号问题一节（该 item 在同一 assistant turn 全部 reasoning item 中的 0 基序号，bare marker 占序号但不带 `i`）。

**bare marker 保持 v1 语义不变**——`spec.md:221`、`:325`、`acceptance.md:141-144` 与独立裁决 `260807-arbitrate-empty-reasoning.md` 冻结了「absent／empty `encrypted_content` 恰好产生一个 bare marker block、consumer 不得伪造 `encrypted_content`」。v2 不改这一条。

### 检出后的 wire 行为

位置校验不通过时（某个 payload carrier 的 `i` 不等于它的源序序号），归入 **`TRANSFORM`＋`DEGRADE`**：

> 按客户端给出的 block 源序原样重建 reasoning item（不依 `i` 重排、不丢弃、不使请求失败），并记录一条结构化 `ConversionFact`，载明观察到的序列、期望序号与异常类型。客户端可观察结果与正常路径一致，差别只在该 fact。

**标签选择的依据**：`spec.md:142` 定义 `DEGRADE` 为「请求可继续，但损失必须作为结构化 `ConversionFact` 进入 History、metrics 与 trace，且不得伪装成已保真」——正是此处语义。内容本身仍按确定映射转成 reasoning item，所以同时是 `TRANSFORM`；组合标签在 `:179` 的 refusal 行已有先例。**注意不要与 `:164`／`:165` 那种「整个 block 不进入 wire」的用法混淆**——那是那两行各自的处置内容，不是 `DEGRADE` 的定义。

理由：`i` 的检出能力本就不完备（尾部检不出），据一个不完备的信号丢弃内容或拒绝请求，风险高于它能挡住的问题。**不用 `i` 主动重排**——上游按源序接受，Anthropic 自身规则又要求 thinking 领起回合，保持源序已经是对的形状。

### 字段处置矩阵需要新增的行（r3 复评 M1）

`spec.md:141-142` 规定只有矩阵明确写为 `DEGRADE` 的项目才允许 permissive 处理，unknown 不自动继承。因此上述行为必须在矩阵里有落点，否则正文允许继续、矩阵却禁止：

**request 矩阵（`:161-165` 之间）新增两行：**

| 项目 | 处置 | 内容 |
|---|---|---|
| 本项目主 v2 reasoning carrier | `TRANSFORM` | 在 v1 之前识别；按 v2 namespace、version、tag 与唯一 key 集合恢复 visible summary、`encrypted_content` 与位置序号 `i` |
| 本项目 v2 carrier 位置校验失败 | `TRANSFORM`＋`DEGRADE` | 按源序原样重建 reasoning item，不重排、不丢弃、不失败；记录载明观察序列与异常类型的 `ConversionFact` |

**request 矩阵既有行调整**：`:163` 的「本项目 bare marker」一行扩为同时覆盖 v2 bare marker，处置与内容不变。

**response 矩阵 `:182` 调整**：「每个 reasoning item 一对一形成 thinking block 和本项目主 **v1** carrier」→ 改为 **v2** carrier，并补一句「payload carrier 携带该 item 在本 turn 内的 0 基序号 `i`；`encrypted_content` 缺失或为空时发 v2 bare marker，不携带 `i`」。一 item 一 block、不得跨 item 聚合／错配不变。



### canonical vectors（独立计算，非产品 codec 生成）

由独立脚本按上文规范文字直接实现并计算，**未 import 任何 `app.*`**，满足 `acceptance.md:114` 的 oracle 独立性；脚本已自检四条 vector 均可往返且为 canonical base64url。

| 输入 | 紧凑 JSON | signature |
|---|---|---|
| `encrypted_content="opaque-😀"`, `i=0` | `{"tag":"openai.responses.reasoning.encrypted_content","encrypted_content":"opaque-😀","i":0}` | `ghc-api-proxy:synthetic-reasoning:v2:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLfCfmIAiLCJpIjowfQ` |
| `encrypted_content="ENC=="`, `i=0` | `{"tag":"openai.responses.reasoning.encrypted_content","encrypted_content":"ENC==","i":0}` | `ghc-api-proxy:synthetic-reasoning:v2:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50IjoiRU5DPT0iLCJpIjowfQ` |
| `encrypted_content="opaque-😀"`, `i=2` | `{"tag":"openai.responses.reasoning.encrypted_content","encrypted_content":"opaque-😀","i":2}` | `ghc-api-proxy:synthetic-reasoning:v2:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLfCfmIAiLCJpIjoyfQ` |
| `encrypted_content="a"`, `i=41` | `{"tag":"openai.responses.reasoning.encrypted_content","encrypted_content":"a","i":41}` | `ghc-api-proxy:synthetic-reasoning:v2:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50IjoiYSIsImkiOjQxfQ` |
| summary-only / strip | 无 payload | `ghc-api-proxy:synthetic-reasoning:v2` |

### 必须一并修订的既有条款

- **`spec.md:204`** → 「resolved model 与 upstream identity 只能作为内部 typed facts 保存，不得塞进 carrier。carrier 可以承载 **assistant turn 内的位置序号**（`i`），用于回送时尽力校验 item 是否被移位、重复或丢失；该校验对**尾部**丢失与合并无效，这是块级交付的固有边界，不得据此认为实现有缺陷。除位置序号外不得承载任何 item 标识，尤其不得承载上游 item `id`。」
- **`spec.md:220`** → 保留 `item id` 禁令，理由改为可核验三条：不稳定（`.added`／`.done` 的 id 在 446/446 对中全不同）、昂贵（420–436 字符，一轮最多观测到 135 个 item）、不必要（174,597 次不带 id 回送被接受）。**并写明它不是因为会被上游拒绝**——带 final id 回送在透传路径 10/10 成功。
- **`spec.md:8`** producer 固定 v1 → 改为 v2；该句位于「已裁决且不可重开」段，需你明示覆盖。
- **`spec.md:182`、`:325`、`:221`** 一 item 一 block、bare marker 语义 → **不变**。

### `acceptance.md` 替换要点

- **`:108-111`**：默认输出改为 v2 两态；v1 与 upstream v1 降为 **consumer-only** oracle。
- **新增 v2 producer vectors**：上表五条，直接采用。
- **新增识别顺序 oracle**：依次喂 v2／v1／upstream v1／foreign，前三恢复、第四不恢复。
- **新增 mixed-history oracle**：同一 conversation 混有历史 v1 与新 v2，逐 block 各按自身版本恢复，不因存在 v1 而整轮降级。
- **新增 `i` 判据**，每条都要有正反样本，且**必须含 bare marker 参与序号的样本**（这是 r3 复评 M2 指出会误报的地方）：
  - 通过：`[p(i=0), p(i=1)]`；`[p(i=0), bare, p(i=2)]`（**合法的中间 bare 不得误报**）；`[bare, p(i=1)]`。
  - 产生 `ConversionFact` 且 wire 输出保持源序：`[p(i=1), p(i=0)]` 乱序、`[p(i=0), p(i=0)]` 重复、`[p(i=1), p(i=2)]` 前缀丢失、`[p(i=0), p(i=2)]` 中途丢 payload、`[p(i=0), p(i=2)]` 由 `[p(i=0), bare, p(i=2)]` 丢掉中间 bare 而来（**这一条证明中途丢 bare 可检出**）。
  - **显式断言不产生 fact**（把能力边界钉进 oracle，避免后人当缺陷去修）：`[p(i=0)]` 由 `[p(i=0), p(i=1), p(i=2)]` 丢掉尾部两块而来；`[p(i=0)]` 由 `[p(i=0), bare]` 丢掉尾部 bare 而来。
- **`:36-37`、`:141-144`、`:439`** 中以 v1 为 producer 预期处同步改为 v2；`:141-144` 的 bare-marker 语义本身不变。

### 迁移与回退（更正 r2 的错误顺序）

1. 修订 `spec.md` 与 `acceptance.md`，独立评审。
2. 实现 v2 编解码与严格校验，**consumer 先行**，producer 仍留 v1。
3. 等所有实例都能读 v2 之后，才切 producer。
4. **若切换后出问题，回退的是 producer（回到发 v1），v2 consumer 必须保留。** r2 写的「连同 consumer 一起回退」是错的——那会让已发给客户端的 v2 signature 在下一轮被判 `project_unknown_version`，按 `spec.md:246` 丢掉整个 thinking block。一旦生产过 v2，consumer 兼容性就不能再撤。
5. 若某次部署确实无法保留 v2 consumer（例如整 build 回滚到 v2 之前的版本），那是**不支持无损回滚的已知部署限制**，须在切换前写进部署记录，不能描述成普通可逆操作。

### 未决

1. **是否消费 `copilot-api-js` v2**：他们的 v2 信封已存在且读取端在用，但没有生产写入端（唯一调用点在当前类型联合下不可达，其注释自陈有意为之）。倾向暂不实现、记录在案。
2. **`spec.md:8` 属「已裁决且不可重开」**，改它需你明示覆盖。

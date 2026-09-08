# `upstream/retry-and-continuation/deferred.md` 全条目清点

**日期**：2026-08-22。**性质**：只读清点，未改动任何被清点的文件。
**对象**：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/deferred.md`，条目 1–20（13、14 空号，实有 18 条）+「明确不做」4 条 +「方法学警告」1 条。
**裁决背景**：用户裁定该文件结构无纪律——已查清的内容应移出、归入常规文档的适当位置。该文件抬头自述「只列**需要用户裁决**或**已知未闭合**的项。已经定下来的在 `status.md`」，本次清点即针对它违反自身宪章的部分。

> ⚠️ **本报告未能写入指定路径，原因见文末「交付阻塞」一节。** 指定路径为 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-deferred-md-inventory.md`。

---

## 〇、观测锚点与可信度边界（先读这节，它约束下面每一条）

| 项 | 值 |
|---|---|
| 主仓 HEAD | `c01191f refactor: give the chain's address one owner instead of two` |
| 主仓工作树 | **脏**：29 个已追踪文件 modified，含 `src/app/pipeline/delivery/stream.py`、`src/app/server/pipeline_app.py`、`tests/int/test_pipeline_app.py`、`docs/.human-controlled/` 下 5 份人写文档 |
| `src/app/server/routes/inference.py` | **未追踪（`??`）**，从未进入任何提交。同伴正在把 `pipeline_app.py` 拆进 `server/routes/` |
| `src/app/pipeline/hand_over.py` | 新模块，自述「Split out of `app.server.pipeline_app` on 2026-08-22」 |
| `.dev` 侧 | `deferred.md` 有未提交改动；`evidence/clean-eof-no-terminal/` 未追踪 |

**这不是免责声明，是载重条件。** 本次清点的代码事实分两类，必须分开读：

1. **在提交态成立的**（`git show HEAD:` 或 `git log` 核过）——可据此行动。
2. **只在工作树成立的**——同伴一次 `git checkout` 即失效。按项目记忆「查残留要 grep 提交态，不是工作树」，工作树是叠加态，既能凭空洗白也能凭空造假。凡此类下文标注 **[工作树]**，且判定一律降一档：不写「已闭合」，只写「部分闭合」。

**一处必须点名的能力损失**：清点进行到约三分之二时，harness 对本会话启用了工作树隔离守卫，此后**所有 `Bash` 调用被拒**（守卫按 shell 持久 cwd 判定，且忽略命令内的 `cd`，连 `cd /tmp && pwd` 也被拒）。因此：

- §19 的提交态我**核过**（`git show HEAD:` 证明 HEAD 仍是旧措辞），结论可靠。
- §20、§5、§17、§9 的结构性事实我只能用 `Read` 读**工作树**，**其提交态未核**。下文逐条标注。
- 这不影响「哪个条目属哪一层」「该归哪个载体」「有没有断链风险」这三项主判定——那三项依据的是文档与引用关系，不依赖提交态。

**权重档位约定**（每条判定末尾给出）：

- **够据此行动** —— 由条目自述的用户裁决支撑，或由我实跑命令的一手结果支撑，且不依赖未提交状态。
- **倾向** —— 判据成立但依赖工作树、或依赖同伴在飞的切片，随时可能翻转。
- **仅存档** —— 我未独立核实，只转述条目自述或他人报告。

---

## 一、该主题目录实际有哪些文件（机械枚举）

命令：`git -C /home/xp/src/ghc-api-proxy-py/.dev ls-files docs/upstream/retry-and-continuation/`（实跑，输出 60 余行）。

**根目录只有 4 个活文档**，各自的角色引自它们自己的抬头：

| 文件 | 自述角色 |
|---|---|
| `README.md` | 入口；「这个主题回答什么」；**「支撑本主题的实测证据」表**（带证据等级与样本边界列）；**「本仓实际发出的 MCP 工具调用」**一手契约；相邻主题 |
| `status.md` | 「本文只记实现状态与路线，**不复述它的裁决**」——当前状态表、一条决定分类表形状的结构事实、A–E 五阶段路线（每阶段列提交号）、「几条不必再写进代码的顾虑」 |
| `decisions.md` | 「把裁决发生的**时间、场合与理由**记下来」——〇权威有两份／一已写进人写文档（索引，引句不引行号）／二只存在于讨论中／三**本项目推论，不是裁决**／四**尚待裁决** |
| `deferred.md` | 「只列需要用户裁决或已知未闭合的项」（清点对象） |

其余目录：`archive-proxy-side-continuation/`（归档方案 + 其自有 `reports/`）、`reports/`（15 份报告原件 + `260822-review-d-group-probes/` 探针目录）、`evidence/`（4 组探针脚本与输出）。

### 载体角色盘点：哪些角色有、哪些缺

| 层 | 现成载体 | 够不够 |
|---|---|---|
| **需求层**（必须为真、对外承诺） | 权威在主仓 `docs/.human-controlled/upstream-retry-and-continuation.md`；本主题侧由 `decisions.md` §一（已写进人写文档的索引）、§二／§二之二（只在讨论中的裁决）承载 | **够**。且 §四「尚待裁决」正是「待用户裁决」项的现成归宿 |
| **中间层**（规格、理解、测量、被否方案、理由） | `README.md`「支撑本主题的实测证据」表；`decisions.md` §三「本项目推论，**不是裁决**」；`status.md`「几条不必再写进代码的顾虑」 | **基本够**，缺口见下 |
| **产物层**（当下实际如何、现状、数字） | `status.md` 当前状态表 + A–E 阶段表 | **够** |

**缺的那个角色：一份「已查清、修法唯一、只是没排期」的缺陷登记。**

现有四份都装不下它：它不是裁决（`decisions.md` 拒收），不是实现状态（`status.md` 记「已落地什么」而非「还差什么」），不是支撑性实测证据（`README.md` 那张表收的是支撑事实，不是缺陷），而 `deferred.md` 按宪章只收「需裁决」与「未闭合」。本次清点中 §16、§17、§18、§9 全属此类——它们既非待裁，也非未查清，只是没人排期。

**建议（倾向，非结论）**：**不新建文件**，把 `deferred.md` 的宪章从两栏扩成三栏——「需用户裁决」／「已知未闭合」／「已查清未修（无岔路）」，第三栏每条必须写明「为什么没做」。理由有二：

1. 项目自己的 `.claude/skills/project-review-principles/SKILL.md:22` 已经把 `deferred.md` 当成「违背了但不值得现在修，记入 `deferred.md` 并说明不做的理由」的落点——那个既有用法与第三栏正好对上。另建新文件会让这个既有引用指向错的地方。
2. §二将证明，编号是被生产代码按号引用的公共接口。留在原文件、只加栏目，比拆成两个文件的断链面小一个量级。

---

## 二、全局搬移风险：生产代码按编号引用本文件

**这是本次清点最重要的一条，它约束几乎所有条目的搬法。**

命令（主仓）：`rg -n 'deferred\.md' src tests`。**正样本对照**：同一路径集下 `rg -n --count-matches 'retry-and-continuation' src tests docs` 命中 9 个文件（`inference.py`、`test_pipeline_app.py`、`retry.py`、`hand_over.py`、`responses.py`、`stream.py`、`base.py`、`anthropic_messages_synthetic_reply.py`、`openai_responses.py`），证明模式与路径集有效，上面的命中不是空搜。

| 引用点 | 引的编号 | 形态 | 备注 |
|---|---|---|---|
| `src/app/pipeline/delivery/formats/openai_responses.py:448` | **§2** | 全路径 + 章节号 | |
| `src/app/pipeline/translation_driver/responses.py:160` | **§2** | 全路径 + 章节号 | |
| `src/app/server/routes/inference.py:358` | **§5** | 短名 + 章节号 | **该文件未追踪** |
| `tests/int/test_pipeline_app.py:3116` | **§5** | 短名 + 章节号 | |
| `tests/int/test_pipeline_app.py:3118` | **§5** | 短名 + 章节号 | |
| `src/app/pipeline/direct_driver/base.py:153` | **8a** | 全路径 + 子条号 | |
| `src/app/pipeline/delivery/stream.py:366` | **8d** | 短名 + 子条号 | [工作树] |
| `src/app/pipeline/delivery/stream.py:368` | **§12** | 短名 + 章节号 | [工作树] |
| `src/app/pipeline/delivery/stream.py:360` | **§20** | 短名 + 章节号 | [工作树] |
| `src/app/pipeline/delivery/stream.py:429` | **§19** | 短名 + 章节号 | [工作树] |

`.dev` 侧另有三处**活文档**按编号引用（报告原件不计，那是时点记录，按项目规矩不改）：

- `docs/upstream/h2-goaway/deferred.md:30` —— 「现状与待裁项一律以 `../retry-and-continuation/deferred.md` **第 7、11、12 条**为准，本主题仍不跟踪」
- `docs/upstream/retry-and-continuation/status.md:29` —— 「见 `deferred.md` **第 7、11、12 条**」
- `docs/upstream/retry-and-continuation/decisions.md:64` —— 「回应 `deferred.md` **第 11 条**」

另有一条**反向**引用值得注意：`src/app/pipeline/hand_over.py:84` 引的是 `decisions.md` 的 **`4.1`**（`.dev/docs/upstream/retry-and-continuation/decisions.md` 第四节第 1 条）。这说明**从代码引 `decisions.md` 的小节号已是本项目既有做法**，把「待裁决」条目搬进 `decisions.md §四` 与现状一致，不是我发明的新惯例。

**推论（够据此行动）**：编号是跨仓的公共接口，被 **6 个生产源文件 + 1 个集成测试文件 + 3 处活文档**按号引用。**任何搬移都不得重新编号剩余条目**——否则 `stream.py` 里的「§12」会指到别人身上，而且**不会有任何东西报错**，正是项目记忆「重指路径会改写引文」的同一形状。

**建议的安全搬法（倾向）**：条目搬走后原位留一行墓碑——「§N 已移入 `<文件>` 的 `<小节>`，2026-08-22」——编号**永不回收**。代价是文件仍会长，但长的是索引而非内容。

**一处附带风险**：§5 的三个引用点里有两个（`inference.py:358` 与两条测试 docstring）不只引编号，还**复述了 §5 的实质结论**（「whether a drain should be a case that gate lets through is an open product question」）。§5 若被裁决关闭，这三处注释同时变成陈述过时事实的活文本，必须一并改。这一条在 §5 的行里再记一次。

---

## 三、逐条清点

**列含义**：「判定依据」严格区分 **(自述)** = 条目自己写了裁决／已落地／不再是待办；**(核实)** = 我跑了命令或读了代码。两者都有时都写。

### 条目 1 — 上下文超限的 400：两条腿的分类判据不同（原标题「主路径抽不出数字」已撤销）

- **判定**：**已闭合（含一条明确的低优先残留）**
- **判定依据**：**(自述)** 条目自己写「**这条留作已查清的事实，不再是待办。**」，且原落点已被用户质疑并由本项目撤回。残留部分自述为「仍未查清（低优先，**无消费端**）：账户类型维度；`/chat/completions` 腿只有第三方录制」，并说明「本项目自己不落盘上游 body，`~/.local/share/ghc-api-proxy/rejected/` 不存在，所以这两项只能等新的录制」——即**无行动可做**，不是待办。
- **闭合部分属哪一层**：**中间层**（测量与规格理解：两条腿 400 的结构差异、`error.code` 有无鉴别力、建议匹配 `exceeds the context window`）。另含**中间层的被否记录**两条：撤销的原落点、以及被证伪的旧结论（「没有任何一条当前两条正则漏掉的真实 token-limit body」，因语料全早于 2026-07-18 而不成立）。
- **建议接收者**：**`README.md`「支撑本主题的实测证据」表**。该表已有一行浓缩版（「上下文超限走 HTTP 400，**两条腿形态不同**……48 例一手」），把 §1 的六行对照表并入即可，**不必再抄一份**（见 §四重复项 D-1）。撤销记录与「这次错在哪」的方法学教训（*继承一个缺口的描述时，先找它的消费端*）另有去处：**`decisions.md` §三「本项目推论，不是裁决」**——那正是「前提变了即失效」的推论的家。
- **搬移风险**：**低**。全仓无按「第 1 条」引用它的地方（`rg` 结果中 §1 未出现在任何代码或活文档引用里）。唯一提及在报告原件 `reports/260822-review-mcp-contract-and-deadline-order.md:324`「顺带核验：`deferred.md` 第 1 条的撤销依据」——报告是时点记录，不改。
- **权重**：够据此行动。

### 条目 2 — reasoning item 被截断时没有任何信号

- **判定**：**已闭合**
- **判定依据**：**(自述)**「**用户 2026-08-21 裁决：历史里没有信号就保持悬念，暂不特殊处理。**」**(核实)** 两处生产代码把这条当已决事实引用并说明「Left open deliberately」：`openai_responses.py:448`、`responses.py:160`。
- **闭合部分属哪一层**：**需求层**（用户裁决：不特殊处理，半截 thinking 块照常交付）**+ 中间层**（测量：正常收尾与被截断的 reasoning item 键集逐字相同，`summary: []` 两侧都出现，已做正样本对照；以及被否方案：延迟提交会往交付路径塞状态）。
- **建议接收者**：裁决 → **`decisions.md` §二第 3 条**（**已在那里**，逐字对应：「**reasoning item 无 `status` 信号时不特殊处理**」）。测量 → **`README.md` 证据表第 3 行**（**已在那里**）。**所以本条不需要新载体，只需删除并留墓碑**。
- **搬移风险**：**高——本条是全部条目里断链风险最大的一条。** 两处生产代码按 **§2** 引用（`openai_responses.py:448`、`responses.py:160`），且都写的是「`deferred.md` §2」。编号绝不可回收；墓碑必须写明新落点，否则下一个人顺着代码注释找过来会扑空。
- **权重**：够据此行动。

### 条目 3 — `model_context_window_exceeded` 在 Anthropic 腿仍是可能的

- **判定**：**已闭合**
- **判定依据**：**(自述)** 条目本身就是一条结论（两条腿权重不同，给出「所以分类表里不要把它写成已排除」的行动指引），没有任何待办或待裁语句。
- **闭合部分属哪一层**：**中间层**（测量的**权重定级**：Responses 腿结构性不存在=权重强可据此行动；Anthropic 腿枚举里有值但 13 万次零观测=「未观测」不是「不可能」）。这条正是项目 `state-decisiveness` 要求的写法范本——`reports/260821-review-a-group-docs.md:229` 专门表扬过它「这正是本项目要求的写法」。
- **建议接收者**：**`README.md`「支撑本主题的实测证据」表**。该表已有一行（「Anthropic 腿实测到的 `stop_reason`：`tool_use`(124927)、`end_turn`(8290)、`max_tokens`(24)、`refusal`(1)。`model_context_window_exceeded` **零观测**」），**但缺了 §3 的核心——那句「所以分类表里不要把它写成已排除」的行动指引**。搬移时必须把这句带过去，只留数字会丢掉整条的用处。
- **搬移风险**：**低**。无按编号引用。
- **权重**：够据此行动。

### 条目 4 — 上游 SSE 中途的 `error` 帧：零观测

- **判定**：**部分闭合**
- **判定依据**：**(自述)** 观测面已闭合（134336 个 operation、约 3000 万根帧，`response.failed`／`response.cancelled`／上游 `error` 帧各 0 次）。但处置未闭合，条目自述「现状的处置是坏的：这些帧被 `push` 静默丢弃……**G1（分支 `fix/upstream-error-events`）正是在补这个**」。**(核实)** `git branch -a --list '*upstream-error-events*'` 输出 `+ fix/upstream-error-events`（`+` 表示**正被另一棵 worktree 检出**，即仍在飞）；`rg 'response\.failed|response\.cancelled|UpstreamFailure|_read_failure' src/app/pipeline/` 在活链路**只命中 1 处且是一句注释**（`openai_responses.py:317`，讲的是本侧发 `error` 而非 `response.failed`），**没有任何读取上游 `error` 帧的生产代码**。故 G1 尚未并入。
- **闭合部分属哪一层**：**中间层**（测量：零观测 + 样本量 + 「参考实现枚举过的完整词表只有旁证」这一权重限定）。未闭合部分属**产物层**（现状处置坏，等 G1）。
- **建议接收者**：观测面 → **`README.md` 证据表**（**已有一行**：「Responses 腿的终止只有 `response.completed`(64351) 与 `response.incomplete`(20)；`response.failed`／`cancelled`／上游 `error` 帧**各 0 次**」，见 §四 D-3）。未闭合的处置 → **留在 `deferred.md`**，但应把「G1 正在补」改写成带锚点的现状（G1 分支名 + 「截至 `c01191f` 未并入」+ `README.md:87` 已把它列为本主题依赖）。
- **搬移风险**：**低**。无按编号引用。但注意 `README.md:87` 已有一条 G1 依赖说明，两处讲同一件事，搬移时应合并而非并存。
- **权重**：够据此行动（零观测与 G1 未并入均一手核实）。

### 条目 5 — 已交付之后的两条失败路径行为不一致

**这是全文最长、最混杂的一条，必须拆开判。**

- **判定**：**部分闭合**（五个成分里三个已闭合、两个仍未闭合）
- **判定依据**（逐成分）：

| 成分 | 判定 | 依据 |
|---|---|---|
| (a) 两条失败路径不一致（干净 EOF 发 SSE `error`；撕流/idle/deadline/缓冲超限裸抛不发帧） | **已闭合** | **(核实)** [工作树] `stream.py:366-386`：「Every remaining ending gets a frame *and* still reaches the caller. **Until 2026-08-22 it was a bare `raise`**」——不一致已消除，现在两条都发帧且都上抛 |
| (b) 「commit 后发生错误 → 发 Anthropic SSE error terminal」被误解为「合成续写**失败**时的兜底」这一更正 | **已闭合** | **(自述)** 条目自称「**此前只活在会话里，是本条唯一的持久载体**」，并给出正确提法「续写没接手时的 ending」及其论证（合成是纯本地构造、不发上游请求、人写文档已把最像失败的那一格堵死） |
| (c) 四格触发条件的枚举（非 anthropic-messages 客户端／一个完整块都没交付／有意裁决不可继续／分类器叫不出名字） | **已闭合** | **(自述)** 条目自评「**证据等级：够据此写实现范围**（依据是人写文档原文与 `_hand_over`／`_replay_reason` 的现有分支）」 |
| (d) 「交接需要已交付的内容，所以这一格结构上不可能交接」这句机制陈述是假的 | **已闭合** | **(自述)** 异源评审实测证伪（`reports/260822-review-drain-suppression.md` major-2），且条目写明「已改正代码注释与 `status.md`」。**(核实)** [工作树] `inference.py:356` 逐字承接这次更正：「An earlier version of this comment said a hand-over "needs delivered content to hand over"; **that is false**, and the false reason is what made this look settled」 |
| (e) **真问题：排空这一格要不要为交接开口？** | **仍未闭合，且是需用户裁决** | **(自述)**「**开不开口是产品裁决，需用户定**」。**(核实)** [工作树] `stream.py:456` 的 `if session.committed_count == 0 and stop_reason not in continuation.stop_reasons: return None` 仍在，闸未开；`inference.py:358`「whether a drain should be a case that gate lets through is **an open product question, not an answered one**」 |
| (f) 不开口的代价（`full`／`until-tool-use` 下整轮完整块被整批丢弃，且是本项目 `db49581` 引入的回归） | **已闭合（事实）**，处置随 (e) | **(自述)** 条目自评「**机制与代价均为确凿（一手实测 + 代码事实）**」。**(核实)** [工作树] `inference.py:358` 复述了同一代价 |

- **闭合部分属哪一层**：(a) **产物层**（现状已改）；(b)(c) **中间层**（对人写文档的规格理解，以及一条被否的错误提法——「按它去写会实现一个几乎永不触发的分支」）；(d) **中间层**（被证伪的机制陈述，属「记下不采纳的理由」）；(f) **中间层**（代价量化）。
- **建议接收者**：
  - (a) → **`status.md`**（当前状态表里「已交付之后的失败要能进裁决」那一行，**现在写的仍是旧现状**「撕流／idle／deadline／缓冲超限 → 异常上抛截断连接，**只进服务端日志**」，与工作树已不符，搬移时同步更正）。
  - (b)(c) → **`decisions.md` §三「本项目推论，不是裁决」**。理由：正确提法「续写没接手时的 ending」及其四格枚举，是由人写文档原文推出的，条目自己也说「依据是人写文档原文与现有分支」，正是 §三 的定义（「前提变了即失效」）。
  - (d) → **`decisions.md` §三**，作为被证伪的推论留档（`record-what-not-adopted`）。
  - (e) → **`decisions.md` §四「尚待裁决」**。这是 §四 的标准形态：有真实岔路、不同选择导向不同产品行为。搬移时必须带上 (f) 的代价量化，否则用户无从裁。
  - **不需要新载体。**
- **搬移风险**：**最高。三个引用点不只引编号，还复述了 §5 的实质结论。**
  - `inference.py:358`「Registered in `deferred.md` §5; do not read the current behaviour here as a decision.」
  - `test_pipeline_app.py:3116`「Whether it should is open; see `deferred.md` §5.」
  - `test_pipeline_app.py:3118`「That ending is a bare re-raise rather than an error frame, which is the shape `deferred.md` §5 already records as inconsistent.」
  - **第三处已经与工作树的代码事实矛盾**：按 (a)，`stream.py` 现在**发帧**了，不再是 bare re-raise。这条测试 docstring 在描述一个已被改掉的形态。**这是本次清点顺带查出的一处独立缺陷，不属搬移风险，应单独修**（但注意：该测试文件本身也在工作树未提交改动列表里，可能同伴已在改）。
  - 搬移时：(e) 移入 `decisions.md §四` 后，这三处注释必须改指新位置；`deferred.md §5` 留墓碑。
- **权重**：(a)(d)(f) 倾向（依赖工作树）；(b)(c)(e) 够据此行动（依据是条目自述 + 人写文档，不依赖提交态）。

### 条目 6 — 流式与非流式对同一事实给出不同答案

- **判定**：**已闭合，但条目未销账**
- **判定依据**：**(核实)** `src/app/pipeline/translation_driver/responses.py:113-131` 现在两条路径给同一答案，注释逐字承认这次修复：「Upstream's own word, unmapped, **exactly as the streaming path does it**……everything else **used to** become `end_turn`, which reported a turn upstream had cut short as one it finished. **The two paths described the same fact differently until this line**, which is worse than either answer on its own.」同处并写明「**No longer recorded as a conversion loss: nothing is lost now that the reason reaches the client.**」**(核实)** `rg 'losses' src/app/pipeline/translation_driver/responses.py src/app/pipeline/delivery/formats/openai_responses.py` **零命中**（正样本对照：同一模式在 `src/` 全域命中 7 个文件，证明模式有效），即条目描述的 `conversion.losses` 机制在这两处已不存在。**(旁证)** 异源评审 `reports/260822-review-unreviewed-span.md:168` 早已指出：「`deferred.md` §6『流式与非流式对同一事实给出不同答案』描述的正是 `fef7d96` 修掉的那件事，**条目未销账**」。
- **闭合部分属哪一层**：**产物层**（现状：两条路径已一致）。条目里那句「流式那条还违反 `../../anthropic-responses-bridge/spec.md:264-265`」属**中间层**（对外部 spec 的合规判定），但既已修复，也随之失效。
- **建议接收者**：**`status.md` E 阶段表**——该表**已有一行**：「`fef7d96` | 非流式 `stop_reason` 不再抹平成 `end_turn`（C 组只修了流式那侧，**两条路曾对同一事实给出不同答案**）」，逐字覆盖了 §6 的内容。**所以本条应直接删除并留墓碑，不需要搬任何字。**
- **搬移风险**：**低**。无代码或活文档按编号引用 §6（仅报告原件 `260822-review-unreviewed-span.md:168` 提及，属时点记录）。
- **权重**：够据此行动。

### 条目 7 — 孤儿件与死配置项的处置

- **判定**：**部分闭合**，且**含一处已过期的陈述**
- **判定依据**：
  - **(自述)** 裁决部分已闭合：「**用户 2026-08-21 裁决：只删代理内续写机制，其他未接线的功能不要动。**」
  - **(自述)** 待裁部分未闭合：「待裁的是形状：要么让这个纯函数只裁『未完成流』（去掉 `terminal_seen` 参数与 `COMPLETE`），要么重塑参数使调用者能在异常分类之前问出完整 verdict。**不要**改成在 verdict switch 里处理 `COMPLETE`」。**(核实)** [工作树] `stream.py:347-349` 的 `COMPLETE` 分支仍在，注释写「Unreachable from here now that the same question is answered above」——形状未定，条目仍成立。
  - **(核实) 一处已过期**：条目写「`streamReplay.max_retries`（默认 100）在 D 组接线后会生效」——**假**。逐项 `rg`：`streamReplay` 与 `max_tokens_as_retryable` 在 `src/` **零命中**；`hedge` 只剩 `schema.py:240`；`RetryBudget` 已在 `direct_driver/base.py:46` 定义并被 `__init__.py` 导出（即已非孤儿）；`buffered_retry.py`／`delayed_commit.py` 文件仍在 `src/app/streaming/`。异源评审 `reports/260822-review-d-group.md:139` 早已指出这句过期。
- **闭合部分属哪一层**：**需求层**（用户裁决：不删其他未接线功能）。
- **建议接收者**：
  - 裁决 → **`decisions.md` §二第 12 条**（**已在那里**，且已记录两次局部推翻）。
  - 孤儿件清单的现状 → **`status.md`**（**已有一行**，`status.md:27`，且已带 2026-08-22 更正）。
  - 「`decide_stream_ending()` 的形状待裁」→ **`decisions.md` §四「尚待裁决」**。这是标准的待裁项：两个候选形状 + 一条明确的禁止选项。
  - **不需要新载体。**
- **搬移风险**：**中**。两处活文档按编号引用：`h2-goaway/deferred.md:30` 与 `status.md:29`，都写「**第 7、11、12 条**」。§7 若拆散，这两处必须同步改（它们引的是三条的集合，只改一条会留下半截指向）。
- **权重**：够据此行动（三项 `rg` 均一手核实；`COMPLETE` 分支状态为倾向，依赖工作树）。

### 条目 8 — 生命周期所有权：一处缺口与三条未接线的通道

**七个子条（8a–8g），必须逐子条判。** 条目整体已给出裁断「**不需要全面重写**」——那部分属**需求层／中间层的被否方案**，已闭合。

| 子条 | 判定 | 依据 | 层 | 建议接收者 |
|---|---|---|---|---|
| **8a** 客户端时限触发时返 502 `CancelledError` 而非 504，`raise UpstreamTimeout` 是死代码 | **已闭合** | **(核实)** `git log --oneline -1 a68672c` → `fix: stop the driver answering a cancellation as though it were a failure`；`status.md` D 阶段表已列该提交「driver 不再吞掉取消（504 而非 502 `CancelledError`）」。`base.py:153` 现存注释用**过去时**复述该缺陷并指回 `deferred.md 8a` | **产物层**（已修） | **`status.md` D 阶段表**（**已在那里**）。8a 本身删除留墓碑 |
| **8b** 该时限只覆盖「进入 `handle_bounded` → 上游响应头」，流式 body 完全在外；也不是「从受理开始计」 | **部分闭合** | **(核实)** `status.md` D 阶段列 `51196e2`「客户端时限真正罩住 body」，即 body 段已闭合；但条目点名的**另外三样**（body 读取、JSON 解析、准入排队仍在时钟外）未闭合——`reports/260822-review-d-group.md:100` 明说「非流式请求完全没被这次改动碰到……也就是 `deferred.md` 8b 点名要修的那三样」 | 已闭合部分**产物层**；未闭合部分**已知未闭合** | 已闭合部分 → `status.md`；**残留必须留在 `deferred.md`**，并把范围收窄成「只闭合了 body 段」 |
| **8c** 流式 body 兜底只有 `upstream_request_deadline`(1200) 是真的；另有没人选过、没文档的 httpx `read=600` | **仍未闭合** | **(自述)** 处置写的就是「**登记**。那个 600 秒是隐式契约，值得写进配置文档」——一条从未执行的动作 | **中间层**（隐式契约的发现） | **无现成载体**。它要去的是「配置文档」，而本主题四份活文档没有一份是配置文档；真正的去处是主仓 `docs/.human-controlled/config.example.yaml`（**用户的文件，我方不改**）。**缺的角色是「给用户的候选材料」**——项目已有 `.dev/human-controlled-docs-candidates/` 目录承担这个角色，应写一段候选进去，`deferred.md` 留待裁记录 |
| **8d** 上游撕裂／idle 触发／deadline 触发三者对客户端逐字节相同；另一对 EOF 空 200 与成功零内容也同形 | **已闭合** | **(自述)**「用户 2026-08-22 已裁决：客户端时限在 body 阶段触发时发 SSE error 帧」。**(核实)** [工作树] `stream.py:366` 实现并引用 8d：「Until 2026-08-22 it was a bare `raise`……(`deferred.md` 8d)」。裁决另已记入 `decisions.md` §二之二第 16 条 | **需求层**（用户裁决）**+ 产物层**（已实现） | 裁决 → **`decisions.md` §二之二第 16 条**（**已在那里**）；实现 → **`status.md` D 阶段表**（**已有** `51196e2`）。8d 删除留墓碑。**但 `stream.py:366` 按 `8d` 引用，编号不可回收** |
| **8e** 关机有两条路径；独立路径的 drain **无上限**，其注释前提只在 `upstream_request_deadline > 0` 时成立 | **仍未闭合** | **(自述)** 处置「**登记**，归 `deployment-systemd` / `graceful-shutdown` 主题」——即本主题不做，但也没证据显示已移交 | **中间层**（机制理解） | **无现成载体（在本主题内）**。它自述归属别的主题。应移入 `.dev/docs/` 下 `deployment-systemd` 或 `graceful-shutdown` 主题的 `deferred.md`，本主题留一行「已移交至 X」。**我未核实那两个主题目录是否存在**（Bash 被封禁），交回主会话确认 |
| **8f** `schema.py:250` 称 `client_request_deadline` 是 systemd 停机超时的基准，实为 300+30，全仓无此推导 | **仍未闭合** | **(自述)** 处置「注释失实，**顺手改**」——一条从未执行的动作。**(未核实)** Bash 被封禁，未能确认 `schema.py:250` 现值（该文件在工作树 modified 列表中） | **产物层**（注释失实） | **这是「已查清、修法唯一、只是没排期」的典型**——即 §一 指出的缺角色。按建议应进 `deferred.md` 新设的第三栏。**不必搬，改栏目即可** |
| **8g** 两处潜伏泄漏（`http.response.start` 抛异常时生成器从未迭代；`base.py:150-175` 丢弃已拿到的响应从不 `aclose`） | **仍未闭合，且已明确不做** | **(自述)**「登记，**不改**——两条今天都不可达，改动面大于收益」。**(旁证)** `reports/260822-review-d-group.md:133-134` 记录该条目**又新增了两个实例**（`_reopen` 的 m2、`a68672c` 的 m3），要求「应计入该条目而不是无声增加」 | **中间层**（潜伏缺陷 + 不做的理由） | **`deferred.md`「明确不做」一节**——那一节现存 4 条，8g 的形态与它们一致（已裁决不做 + 理由）。但注意 8g 是「不做**且会继续长**」，评审已往里加了两个实例，搬去「明确不做」时要保留它的可追加性 |

- **另有一条整体判定**：条目开头「**明确不做全面重写**，理由见报告第 6 题」——**已闭合**，属**中间层的被否方案**，应进 **`decisions.md` §三**（本项目推论）。
- **还有一句必须一起搬的元教训**：「**这几条登记在这里，而不是留在报告里，是有代价换来的**：其中两条（O5、流式作用域）2026-08-20 的评审报告就已写清，grep 确认**从未进入任何活文档**，因此两天后仍未被修。**报告不能是唯一的真相来源。**」这是**方法学**，与 §一 指出的「缺一个已查清未修的登记栏」是同一个问题的两面。建议随新设的第三栏一起，写进 `deferred.md` 的抬头说明。
- **搬移风险**：**中高**。`base.py:153` 按 **8a** 引用、`stream.py:366` 按 **8d** 引用。8a 与 8d 都已闭合、都该删——**但它们的编号被代码钉住**，必须留墓碑。这是「已闭合的条目反而不能干净删掉」的典型。
- **权重**：8a 够据此行动；8d 倾向（实现依赖工作树，裁决够据此行动）；8b／8c／8e／8g 够据此行动（自述 + 评审旁证）；8f 仅存档（未核实现值）。

### 条目 9 — 一次性交付路径的结局判定不接线（同伴切片）

- **判定**：**仍未闭合**
- **判定依据**：**(核实)** [工作树] `src/app/server/routes/inference.py:298-306`：`one_shot_accounting = _StreamAccounting(chain=..., request_id=..., trace=..., status_code=..., context=...)` —— **仍不带 `assembler`**；而同文件 `:336-343` 的块级路径构造时**带** `assembler=assembler`。条目描述的形态原样存在。**(自述)** 处置为「**归同伴的切片**（`2769a64`），且他们仍在改该文件（`630f7f3`），故本主题登记不动手」。
- **闭合部分属哪一层**：无闭合部分。
- **建议接收者**：**留在 `deferred.md`**，但**必须更新锚点**：条目写的是「`one_shot_accounting`（`pipeline_app.py:541`）」，而该逻辑已随同伴的重构搬到 `src/app/server/routes/inference.py:298`（**未追踪文件**）。旧行号已失效，且失效方式是静默的。
- **搬移风险**：**低**（无按编号引用），但**有一个更严重的问题**：本条依赖的是一个**从未提交的文件**。按项目记忆「`git log` 看不见从未提交的文件」，`inference.py` 的历史不可达，任何针对它的 grep 结论都随同伴的下一次编辑失效。
- **权重**：倾向（工作树事实，且目标文件未追踪）。

### 条目 10 — 缺一个 schema → example 的反向检查

- **判定**：**仍未闭合，且是需用户裁决**
- **判定依据**：**(核实)** `rg 'def test_' tests/unit/config/test_config_schema.py` 列出 12 个测试，全部是正向（`test_authoritative_example_config_parses`、`test_unknown_key_is_rejected`、`test_unknown_key_inside_a_section_is_rejected`、`test_snapshot_is_frozen` …），**没有任何一个做 schema→example 的反向检查**。条目描述成立。**(自述)**「补不补由用户裁决：它是一道守卫，而本项目对『把守卫接成阻断』有明确态度。」
- **闭合部分属哪一层**：无闭合部分。
- **建议接收者**：**`decisions.md` §四「尚待裁决」**。这是标准待裁项：有真实岔路（补 vs 不补），且岔路的两端由项目价值观（禁止把结果检查升级成阻断装置）决定，只能用户裁。
- **搬移风险**：**低**。无按编号引用。
- **附带观察（不是本条的一部分）**：条目的措辞把「加一条测试」与「把守卫接成阻断」当成同一件事。按项目规矩（`.claude/rules/00-development-workflow.md`：「A gate takes the judgement out of your hands……**the script behind it is not one**」），**一条断言反向一致性的普通单测不是门禁**，成为门禁的是把它接进 pre-commit 或 CI 阻断。这两半应分开裁。**这是我的判断，权重：倾向**，交用户裁。
- **权重**：够据此行动（反向检查确实不存在，一手核实）。

### 条目 11 — 客户端时限与「上游已完成」谁先答

- **判定**：**已闭合**
- **判定依据**：**(自述)** 标题已带删除线并标「已裁决（2026-08-22），当前次序正确」，且条目末尾自述「**2026-08-22 已完成，见主仓 `08f3c29`**」，三件事逐条列出。**(核实)** `git merge-base --is-ancestor 08f3c29 HEAD` → **`08f3c29` 是 HEAD 的祖先**（提交题名 `fix: say which clock a finished turn loses to, and pin it`）。三条测试全部存在于 `tests/unit/pipeline/delivery/test_stream_delivery.py`：`test_the_client_deadline_is_the_one_ending_that_says_so`(:1110)、**`test_the_client_deadline_outranks_an_upstream_that_just_finished`(:1134，新增的那条)**、`test_a_held_back_policy_still_hears_the_client_deadline`(:1177)。
- **闭合部分属哪一层**：**需求层**（用户裁决：`client_request_deadline` 保护「这一轮总耗时」，故客户端时限先答）**+ 中间层**（那段保留的原始分析记录「这个次序**是载重的**，不是风格选择」，以及夹具鉴别力的得失分析）**+ 产物层**（`08f3c29` 已落地）。
- **建议接收者**：
  - 裁决 → **`decisions.md` §二之二第 18 条**（**已在那里**，且写得比 §11 更完整——它还补了「上游时限的次序相反且必须相反」这一对照）。
  - 「次序是载重的」这条理由 + 变异检验结果 → **`decisions.md` §二之二第 18 条**已含要点；更细的鉴别力分析属报告层，`reports/260822-review-mcp-contract-and-deadline-order.md` F12/F13 已逐字保留。
  - 落地 → **`status.md`**（**注意：`status.md` 的 E 阶段表里没有 `08f3c29` 这一行**，D、E 两表都未收录。这是一处真实的同步缺口，搬移时应补）。
  - **不需要新载体。**
- **搬移风险**：**中**。三处活文档按编号引用第 11 条：`h2-goaway/deferred.md:30`、`status.md:29`（均为「第 7、11、12 条」）、`decisions.md:64`（「回应 `deferred.md` 第 11 条」）。**`decisions.md:64` 尤其要注意**——它是用裁决回指提问，若 §11 被删而不留墓碑，那句话会指向空处，读者无法还原「用户在回应什么」。
- **权重**：够据此行动（提交可达性一手核实）。

### 条目 12 — 上游在终结事件之后 reset：完成行不再留痕

- **判定**：**部分闭合**
- **判定依据**：
  - **归因更正部分已闭合**：**(自述)**「这条的归属被改错过一次，改正记在这里而不是抹掉」——原写「`c86712d` 是一个不被任何 ref 引用的对象」，经逐 ref 复核（`git for-each-ref` + `git merge-base --is-ancestor`）证伪，正确时间线为 `bce8b0d` → `1743a0b` → `f0527e5` 三步共同引入。
  - **缺口本身未闭合**：**(自述)** 处置「**归交付侧重写切片（同伴），本主题登记不动手**」，并列了三个候选做法。**(核实)** [工作树] `stream.py:368` 现存注释把这个缺陷描述为**被有意制造**的：「a stream that framed and returned cleanly logged `ok` and left no record of the failure anywhere. That is **`deferred.md` §12's defect manufactured on purpose**.」——即缺口不但未闭合，还被当作设计取舍复用了一次。
- **闭合部分属哪一层**：归因更正属**中间层**（对自己一次误判的更正记录，`record-what-not-adopted` 的同族）。未闭合部分属**已知未闭合**（观测面缺角）。
- **建议接收者**：
  - 归因更正 → **`decisions.md` §三**或就地留档。**我倾向就地留在 §12**：它是这条缺口的来历说明，剥离出去会让缺口失去上下文（`one-authority-allows-contextual-restatement` 允许上下文复述）。
  - 缺口 + 三个候选做法 → **留在 `deferred.md`**。它自述「候选做法（评审倾向第一个，本会话同意）」但**没有用户裁决**，且第三个候选是「明确裁决这个事实不需要留痕」——有真实岔路，形态上更接近 `decisions.md §四`。**但因为处置是「归同伴切片」，在同伴的重写落地前它还不是可裁的形态**，故建议暂留 `deferred.md`。
  - 那句「**不要**为此加门禁或指标体系」应原样保留——它是对未来读者的约束。
- **搬移风险**：**中高**。`stream.py:368` 按 **§12** 引用，且**引用的是它的实质内容**（「§12's defect manufactured on purpose」）——若 §12 被裁决关闭或搬走，这句注释会失去指涉。两处活文档也按「第 7、11、12 条」引用。另有 `.dev/docs/tmp/260822-p2-complete-fix-handover.md:102` 引「第 12 条」（tmp 件，非活文档）。
- **权重**：倾向（`stream.py` 事实依赖工作树；归因更正为自述，仅存档）。

### 条目 15 — `hand_over_stop_reasons` 在非流式的丢弃上不生效

- **判定**：**仍未闭合**（且条目已自带「明确不做（暂时）」的裁断）
- **判定依据**：**(核实)** `src/app/pipeline/translation_driver/responses.py:213-216` 显示 `from_openai_responses_response(payload, *, hand_over_stop_reasons: frozenset[str] = frozenset({"max_tokens"}))` —— **参数存在但有默认值**；而 `registry.py:126` 仍是 `semantic = reader(payload)`（**不传该参数**），`registry.py:150-152` 的 `register_response_reader(WireFormat.OPENAI_RESPONSES, from_openai_responses_response)` 也**未用 `partial` 绑定**。故配置值确实到不了非流式的丢弃逻辑，条目描述精确成立。**(自述)** 处置「两条都比现在这个不一致贵，**等它真的碍事再做**」。
- **闭合部分属哪一层**：条目里「**危害有界**」的论证已闭合，属**中间层**——它给出了一条不变量（「**不交接就不丢**这条在任何配置下都成立」）及其反向的非不变量（「交接就一定丢」不是不变量，本项目不需要它）。这段论证是这条条目最有价值的部分，且**它不依赖缺陷是否被修**。
- **建议接收者**：
  - 「危害有界」的不变量论证 → **`decisions.md` §三「本项目推论，不是裁决」**。它正是「前提变了即失效」的推论（前提是两边默认值一致）。
  - 缺陷本身 + 两条补法 + 「等它真的碍事再做」→ **`deferred.md` 新设的第三栏「已查清未修」**。它不是待裁（本项目已自行判定成本大于收益），也不是未查清。
- **搬移风险**：**低**。无按编号引用。
- **权重**：够据此行动（`registry.py` 与 `responses.py` 签名均一手核实；两处均在提交态还是工作树态未分辨——`responses.py` 不在工作树 modified 列表中，`registry.py` 亦不在，故**这两处是提交态事实**）。

### 条目 16 — 反方向（`/responses` 客户端 + Anthropic 上游）仍在抹平

- **判定**：**仍未闭合**
- **判定依据**：**(核实)** `src/app/pipeline/translation_driver/responses.py:184-205` 的 `to_openai_responses_response` 现值：
  - `"status": "incomplete" if response.stop_reason == MAX_TOKENS else "completed"` —— `refusal`／`stop_sequence` 仍落 `completed`，条目描述的两条实测结论成立；
  - 返回字典里**根本没有 `incomplete_details` 键** —— 「`incomplete_details` 从不生成，客户端读不到原因」成立。
  - **一处必须防混淆的对照**：`src/app/pipeline/delivery/formats/openai_responses.py:107` **确实生成** `"incomplete_details"`——但那是 **Responses 客户端腿的流式成帧器**（`client-leg-formats` 主题的新件），**不是** §16 点名的非流式翻译器。**若只 grep `incomplete_details` 会得到「已修」的假结论**，这正是「模式不等于判据」的形状。
  - `responses.py` 不在工作树 modified 列表 → **提交态事实**。
- **闭合部分属哪一层**：无闭合部分。
- **建议接收者**：**`deferred.md` 新设的第三栏「已查清未修」**。理由：修法唯一（补 `incomplete_details` + 扩 status 映射），无岔路，条目自己也说「**该路由是 served 的**，只是不在主产品路径上」——即已判定优先级低。它既不是待裁，也不是未查清，现有两栏都装不下。
- **搬移风险**：**低**。无按编号引用。
- **权重**：够据此行动（提交态代码事实，且已排除同名干扰项）。

### 条目 17 — 重开不重建 framer

- **判定**：**仍未闭合**（潜伏，今日不可达）
- **判定依据**：**(核实)** [工作树] `inference.py:345-397` 的 `_reopen` 返回 `tuple[AsyncIterator[bytes], BlockAssembler, BlockBuffer]`——只重建 chunks／assembler／buffer；`stream.py:350-356` 收到 `replacement` 后 `chunks, assembler, buffer = replacement`，**`framer` 不在其中**，仍是循环外那一个。条目描述精确成立。**(自述)**「今天路由对同一请求是确定的，所以不可达。**登记以免将来加入模型回退时无声出错。**」
- **闭合部分属哪一层**：无闭合部分。
- **建议接收者**：**`deferred.md` 新设的第三栏**，或——**更好的去处是代码注释**。理由：这是一条「今天不可达、将来加 X 就会无声出错」的潜伏约束，它的读者是**将来动模型回退的那个人**，而那个人会读 `_reopen`，不一定会读 `deferred.md`。项目已有这种做法的先例（`stream.py:348` 对 `COMPLETE` 分支、`inference.py:354` 对 drain 作用域，都是把约束写在代码旁）。**但我只读，不改代码**——这是给主会话的建议。
- **搬移风险**：**低**。无按编号引用。
- **权重**：倾向（依赖工作树，且 `inference.py` 未追踪）。

### 条目 18 — 一条提交信息缺字

- **判定**：**已闭合（明确不做）**
- **判定依据**：**(自述)**「历史已发布，**不重写**；`fef7d96` 的同一句是完整的，可作对照。登记以免后来者读到一句没有主语的话。」已给出终局处置，无任何待办。**(未核实)** 我未复核 `696a786` 的正文（Bash 被封禁），但条目自述已做过 `cat -A` 确认「非渲染问题」。
- **闭合部分属哪一层**：**产物层**（一条历史事实的现状记录）。
- **建议接收者**：**`deferred.md`「明确不做」一节**。它形态上就是「明确不做 + 理由 + 对照物」，与那一节现存 4 条完全同族。**这是本次清点里最该直接换节、且换节成本最低的一条。**
- **搬移风险**：**极低**。无任何引用。
- **权重**：仅存档（未独立核实缺字本身；「不重写」的裁断够据此行动）。

### 条目 19 — 截断 error 帧的 message 在 Anthropic 上游腿上字面是错的

- **判定**：**部分闭合（活链路已改但未提交；legacy 链路未动；一条跨链路契约已发散）**
- **判定依据**：
  - **(核实) 工作树已改**：`stream.py:427-431` 现为 `message="upstream stream ended before a terminal event"`，并带注释「Names no upstream dialect……`deferred.md` §19」——即 §19 描述的缺陷已修。
  - **(核实) 但提交态未改**：`git show HEAD:src/app/pipeline/delivery/stream.py | rg -B1 'incomplete_responses_stream'` → HEAD 版本 `:388` 仍是 **`message="Responses stream ended before a successful terminal event"`**。
  - **(核实) 该措辞从未进入任何提交**：`git log --oneline --all -S'upstream stream ended before a terminal event'` → **空**。**正样本对照**：同一命令搜 `incomplete_responses_stream` 于同一文件 → 命中 `16dd68c`、`a9c75d4` 两个提交，证明命令与路径有效，空结果是真空而非命令失效。
  - **(核实) legacy 链路未动**：`src/app/delivery/responses_anthropic_stream.py:349` 仍是旧措辞 `"Responses stream ended before a successful terminal event"`。
  - **(核实) 跨链路契约已发散且注释已同步**：HEAD 版 `stream.py:384` 注释写「Same code, same wire shape, **same message**, same gate」；工作树版 `:425` 已删去 `same message` 三字。即同伴选择了 §19 给的第二个选项——「明确裁决让两条链路发散」——并改了注释。**但这次发散没有在任何活文档里留下裁决记录。**
- **闭合部分属哪一层**：**产物层**（活链路措辞已改）。未闭合的是**需求层／中间层**：「让两条链路的 message 发散」是一次**契约变更**，条目原文说得很清楚——「改 message 要么两处一起改、要么**明确裁决让两条链路发散**，不是顺手改一个字符串」，而 `stream.py:382` 的原注释「把这件事写成**有意契约**」。契约变更只有代码注释承载，没有进 `decisions.md`。
- **建议接收者**：
  - 措辞已改的现状 → **`status.md`**（等提交后）。
  - **发散这个决定 → `decisions.md`**。属哪一节取决于它是谁做的：若是同伴自行判断，进 **§三「本项目推论，不是裁决」**；若经用户裁决，进 §二之二。**我无法分辨，这是一个交回主会话的问题**（见文末 HANDOFF）。
  - 条目里那段「**本条初稿的论证是错的，记在这里而不是抹掉**」（用错了轴：framer 是客户端轴，`dialect_for` 才是上游轴）→ **中间层**，价值高，应随条目留档，因为它是对 `framing.py` docstring 那条警告的一次实战验证。
- **搬移风险**：**中**。`stream.py:429` 按 §19 引用（工作树）。**更大的风险不是断链而是时序**：若现在按「已闭合」把 §19 删掉，而同伴的工作树改动被丢弃或回滚，缺陷回来了而登记没了。**建议：在该改动进入提交之前，不要动 §19。**
- **权重**：**够据此行动（针对「未提交」这一判定本身）** —— 提交态由 `git show` + `git log -S` 双向核实并配正样本对照。针对「缺陷已修」则只是**倾向**。

### 条目 20 — `_hand_over` 仍排在异常分类之后

- **判定**：**部分闭合（结构性半边已改但未提交；产品裁决未闭合）**
- **判定依据**：
  - **(核实) [工作树] 结构性缺口已补**：`stream.py:357-361` 现为 `if not ours:` → 注释「Asked whether or not the failure could be *named*, **which is the half that used to be missing**: `reason is None` sent the stream straight out of this function on a bare `raise`, so a failure the caller's taxonomy has no word for — a naked `h2.ProtocolError` is the one on record — **skipped the hand-over entirely**」→ 随后**无条件**调用 `_hand_over(continuation, session, assembler, framer, error=torn)`。即条目描述的「裸抛，既不发 error 帧，也不咨询 `_hand_over`」已不成立。
  - **(核实) [工作树] 但产品裁决仍开着**：同处 `:360`「An unnamed failure is still not replayed……**Whether unnamed should also mean retryable is a product question, and it stays in `deferred.md` §20** rather than being answered by this edit.」
  - **(核实) 判据函数已搬家**：条目引的 `_replay_reason` 现为 `src/app/pipeline/hand_over.py:37` 的 `replay_reason`（新模块，自述 2026-08-22 从 `pipeline_app` 拆出）。条目里的旧符号名与代码块已不匹配。
  - **(未核实)** 提交态。Bash 被封禁，无法确认 `:357-361` 是否已在 HEAD 中。**鉴于 §19 的同文件改动确证未提交，本条的提交态存疑，倾向也未提交。**
- **闭合部分属哪一层**：**产物层**（结构性接线已补）。未闭合部分属**需求层**（「分类器叫不出名字时默认可继续还是默认不可继续」是产品裁决）。
- **建议接收者**：
  - 结构性修复 → **`status.md`**（等提交后）。
  - **产品裁决 → `decisions.md` §四「尚待裁决」**。条目自评「**默认方向需用户裁决**」，且已备齐裁决所需材料（形态、代码落点、证伪前提「裸 `h2.ProtocolError` 会从 httpcore 守卫缝隙抛出」及其端到端实测出处）。
  - 「与第 5 条的关系……**两条一并裁决**」这句必须随之搬走并保持成立——即 §5(e) 与 §20 应放进 `decisions.md §四` 的**同一条**或相邻两条，否则「一并裁决」的要求会在搬移中丢失。
- **搬移风险**：**中**。`stream.py:360` 按 §20 引用，且引用的是**它仍然开着这一事实**（「it stays in `deferred.md` §20」）——若 §20 移入 `decisions.md §四`，这句注释必须改指，否则读者会在 `deferred.md` 找不到它。
- **权重**：倾向（结构性事实依赖工作树；「产品裁决未闭合」够据此行动，由条目自述 + 代码注释双重支撑）。

### 「明确不做」4 条

| 条 | 判定 | 依据 | 层 | 建议接收者 |
|---|---|---|---|---|
| 发真实请求向上游补证 | **已闭合** | **(自述)** 用户 2026-08-21 明确禁止 | **需求层** | **`decisions.md` §二第 13 条**（**已在那里**：「**不向上游发真实请求补证**：只查历史，历史没有就保持悬念」）。删除留墓碑 |
| 代理内续写 | **已闭合** | **(自述)** 已裁决放弃 | **需求层** | **`decisions.md` §一**（已写进人写文档：「## 代理内续写（已放弃）」一节）+ `archive-proxy-side-continuation/`。删除留墓碑 |
| MCP-driven 续写的次数上限 | **已闭合** | **(自述)** 已裁决不设 | **需求层** | **`decisions.md` §一**（**已在那里**）+ **`status.md`「几条不必再写进代码的顾虑」**（**也已在那里**，带完整理由）。**这是一处三重复述**，见 §四 D-6 |
| 为非 anthropic-messages 客户端合成工具调用 | **已闭合** | **(自述)**「这是范围边界，不是遗漏」 | **需求层** | **`decisions.md` §一**（**已在那里**：「仅 anthropic-messages 客户端请求适用」）。删除留墓碑 |

**整节判定**：这 4 条**全部已闭合、全部已在 `decisions.md` 或 `status.md` 有对应载体**。按 `deferred.md` 的宪章（只列需裁决或未闭合），**整节都不该在这个文件里**。但注意：把它们删干净会让 `deferred.md` 失去「明确不做」这个栏目，而 8g 与 §18 正需要它。**建议保留栏目，清空内容，改收 8g 与 §18。**

### 「方法学警告（给后来查 history 的人）」

- **判定**：**已闭合**
- **判定依据**：**(自述)** 一条完整的、给未来读者的限制说明：`from_history.py` 的「只取变换图的根」判据在 2026-07-17 19:41 之前的 366 个 operation 上**恒真失效**。**(旁证)** `reports/260821-review-a-group-docs.md:231` 核过它与 `reports/260821-upstream-termination-reasons.md:75-80` 逐字对得上。
- **属哪一层**：**中间层**（测量方法的适用边界）。
- **建议接收者**：**无现成载体，且这是本次清点里最该被搬出本主题的一条。** 它的读者不是本主题的读者，而是**任何将来用 `from_history.py` 的人**。项目 `.claude/rules/00-development-workflow.md` 已把 `from_history.py` 的两个陷阱写进项目规则；这条是**第三个陷阱**，形态完全一致（「Two traps, both already hit」那段）。
  - **首选**：随 `tests/int/recorded/from_history.py` 的模块 docstring（**改代码，非我职权**）。
  - **次选**：`.dev/docs/test-infrastructure/`（该主题在项目规则里被引用过：`.dev/docs/test-infrastructure/reports/260818-vcrpy-poc.md`，**目录应存在但我未核实**）。
  - **留在这里是错的**——它与「上游重试与续写」无关，只是碰巧在这个主题里被发现。
- **搬移风险**：**低**（无引用），但**有丢失风险**：搬出本主题若没有明确落点，这条会消失。建议在 `deferred.md` 留墓碑指向新位置。
- **权重**：够据此行动（该条与本主题无关，判定不依赖任何未核实事实）。

---

## 四、重复项：同一事实已在别处存在（搬移时该合并，不是再抄一份）

这是任务明确要求的第二件事。逐条给出两侧的确切位置。

| # | 事实 | `deferred.md` 侧 | 已存在的另一侧 | 处置 |
|---|---|---|---|---|
| **D-1** | 上下文超限 400 两条腿形态不同，48 例一手 | §1 六行对照表 | `README.md` 证据表第 7 行（浓缩版，带出处 `reports/260821-context-limit-400-examples.md`） | **合并进 README 表**。README 版更简，缺 `Content-Type`／`request_id`／「建议匹配 `exceeds the context window`」三项，应补 |
| **D-2** | reasoning item 无 `status`，键集逐字相同，已做正样本对照 | §2 首段 | ① `README.md` 证据表第 3 行（含「已做正样本对照」与探针出处）② `decisions.md` §二第 3 条（裁决侧） | **三重复述**。README 记测量、decisions 记裁决，分工正确；§2 删除即可 |
| **D-3** | 上游 `error` 帧／`response.failed`／`cancelled` 各 0 次 | §4 首段 | `README.md` 证据表第 4 行（含 `response.completed`(64351)、`response.incomplete`(20) 的对照数字） | **README 版更完整**（有正面数字作分母）。§4 的观测段删除，只留未闭合的处置 |
| **D-4** | Anthropic 腿 `model_context_window_exceeded` 零观测 | §1 末、§3 | `README.md` 证据表第 6 行 | **合并**，但**必须把 §3 的行动指引「所以分类表里不要把它写成已排除」带进 README**，否则丢掉整条的用处 |
| **D-5** | 「只删代理内续写机制，其他未接线的功能不要动」 | §7 | ① `decisions.md` §二第 12 条（含两次局部推翻的记录）② `status.md` B 阶段（含「当时明确不动」清单） | **三重复述且 decisions 版最全**。§7 的裁决段删除 |
| **D-6** | MCP-driven 续写不设次数上限 | 「明确不做」第 3 条 | ① `decisions.md` §一（已写进人写文档）② `status.md`「几条不必再写进代码的顾虑」（含完整理由「门本身保证零进展的一轮到不了这里」） | **三重复述**。`deferred.md` 版最简，删除 |
| **D-7** | 客户端时限先答、`terminal.seen` 后答 | §11 裁决段 | `decisions.md` §二之二第 18 条（**更完整**，多一条「上游时限次序相反且必须相反」的对照） | **decisions 版是权威**。§11 裁决段删除，保留其下的原始分析（那部分 decisions 没有） |
| **D-8** | 排空拒绝重开后客户端拿到截断而非交接，且「交接需要已交付内容」是假理由 | §5 第 2 格 | ① `inference.py:356-358`（代码注释，**逐字复述**）② `test_pipeline_app.py:3116`（测试 docstring） | **这不是文档间重复，是文档—代码重复**。按 `one-authority-allows-contextual-restatement`，代码注释是合法的上下文复述，但**它必须指回权威**——现在它指的是 `deferred.md §5`，所以 §5 一旦搬走，三处复述同时失去权威 |

### 一处**冲突**（不是重复，比重复严重）

`src/app/pipeline/hand_over.py:84` 的注释写：

> **The value is provisional**: the user ruled that this case gets a category of its own but **has not named it**, and the server that reads it is being changed in another repository. See `.dev/docs/upstream/retry-and-continuation/decisions.md` 4.1.

而它指向的 `decisions.md` §四第 1 条写的正好相反：

> ~~**`max_tokens` 触发合成时 `category` 传什么值**~~ —— **这不是待裁决项，是待对齐项**，2026-08-22 更正。**没有分歧**：`"max_tokens"` 是上游自己的词，也是唯一候选，实现里用的就是它。……把协调写成裁决是**升级过头**。

**代码注释停在了被更正之前的版本，并且它引用的正是那条更正本身。** 读者顺着注释找过去会读到与注释相反的话。

- **权重：够据此行动**（两侧原文均一手读取，`hand_over.py` 不在工作树 modified 列表，为提交态）。
- **这不在本次清点范围内**（它是 `decisions.md` 与代码的问题，不是 `deferred.md` 的），但它与本次搬移直接相关：**若把 `deferred.md` 的待裁项并入 `decisions.md §四`，§四的编号会变，`hand_over.py:84` 的「4.1」会指到别处。** 一并报给主会话。

---

## 五、点时观测：哪些句子搬家时必须保留 provenance

技能规定：观测搬家时必须保留「在什么条件、什么时点观测到」，不能只留结论。下面逐条列出 `deferred.md` 里**带日期、提交号或样本量**的句子，以及**丢掉 provenance 会变成什么**。

| 位置 | 点时观测原句（节选） | 必须一起搬的限定条件 | 丢掉后会变成 |
|---|---|---|---|
| §1 | 「**48 例一手录制**」「Anthropic 腿（27 例，**2026-07-18～08-08**）／Responses 腿（21 例，**2026-08-06～08-08**）」 | 两个时间窗 + 逐腿样本量 | 「两条腿形态不同」变成全称断言。**§1 自己就记录了这个教训**：旧结论「没有任何一条漏掉的 body」不成立，正因为「那份的语料**全部早于 2026-07-18**，而当时没有把这个时间窗写下来」 |
| §1 | 「`>` 在线上是 `&gt;`」 | 这是 message 文本的**线上实际转义形态** | 丢掉会让匹配实现按未转义写，静默不命中 |
| §2 | 「20 例样本里有 6 例（只有 reasoning 中途撞顶）」 | 样本量 20 + 子集 6 + 触发条件 | 「半截 thinking 块会照常交付」变成无条件断言 |
| §3 | 「**13 万次请求零观测**」 | 样本量 + 「Anthropic 枚举里**有**这个值」 | 「零观测」被读成「不可能」——**§3 存在的全部理由就是防止这次误读** |
| §4 | 「**134336 个 operation、约 3000 万根帧**」 | 样本规模 | 同上 |
| §5 | 「**2026-08-22** 补第三个触发条件……（主仓 **`db49581`**）」 | 日期 + 提交号 | 「排空主动拒绝重开」失去来历，无法判断它是否仍成立 |
| §5 | 「`db49581` **之前**这一格会重放并大概率成功」 | **提交号 + 「之前」这个时态** | 这是一句**关于两个版本之差**的话。丢掉提交号后它变成对当前行为的描述，且方向恰好相反 |
| §7 | 「`decide_stream_ending()` 本身已接线（**`8f654b4`**），但 **`c86712d`** 之后它的 `COMPLETE` 那一格……不可达」 | 两个提交号 + 先后关系 | 「`COMPLETE` 不可达」失去时间坐标，无法判断某个分支上是否成立 |
| §7 | 「异源评审实测：把该分支改坏，unit+int **1589 条**里只有它自己的单测变红」 | 变异检验 + 测试总数 + 变红范围 | 「有测试覆盖」变成无鉴别力的断言。**1589 这个数字本身随时间失效**，必须带日期或提交号 |
| §8 | 「来源：`reports/260822-lifecycle-ownership-audit.md`（异源审计，**11 条发现，10 个实测探针**）」 | 报告出处 + 发现数 + 探针数 | 整张表失去证据链 |
| §8b | 「实测（**1 秒时限下 3 秒 body 完整交付**）」 | 具体参数与结果 | 「body 完全在外」失去可复现的判据 |
| §8c | 「实测（**`read=600` 随每个请求到达 transport**）」 | 观测点（transport 层） | 无法判断这个 600 是否仍在 |
| §8d | 「**用户 2026-08-22 已裁决**」 | 日期 + 裁决者 | 变成本项目自己的决定 |
| §11 | 「**实测（评审）**：把该支合并进 `if torn is None:` 那一支……三条 client-deadline 测试全部转红」 | 变异内容 + 结果 | 「次序是载重的」失去支撑 |
| §11 | 「**2026-08-22 已完成，见主仓 `08f3c29`**（上面那段是完成前的原始分析，**保留原样**）」 | **「上面那段是完成前的原始分析」这句元说明本身** | 上面那段会被读成当前状态。**这条是本文件里 provenance 做得最好的一条，应作为搬移的范本** |
| §11 | 「次序变异之下，**全套件里只有它转红**」 | 变异 + 范围 | 新测试的鉴别力主张失去证据 |
| §12 | 「**2026-08-22 收尾时逐 ref 复核**，`c86712d` 可达自 `archive/260822-complete-not-abandon`（命令：对 `git for-each-ref` 的每个 ref 跑 `git merge-base --is-ancestor c86712d <ref>`）」 | **日期 + 归档 ref 名 + 复核用的确切命令** | 「可达」这个断言无法被重新验证；且 ref 可能被删，届时结论沉默失效 |
| §12 | 「`bce8b0d` → `1743a0b` → `f0527e5`……由这三步共同引入，**不归任何单一提交**」 | 三个提交号 + 「不归单一提交」这个判断 | 归因会被简化回错误的单一提交——**§12 自述这个归因已经错过一次** |
| §16 | 三行 `anthropic stop_reason=... -> responses status=...` 实测输出 | 「**实测 `to_openai_responses_response`**」这个函数名 | 换成 grep `incomplete_details` 就会得到相反结论（见 §16 行的对照说明） |
| §19 | 「**2026-08-22 那次生产事故**正是 Anthropic **上游**腿（判据：日志行上是 `think` 而非 `reason`，`REASONING_WORD` + `dialect_for` + `assembler_for` 三处共同决定）」 | **判据本身**，不只是结论 | 「事故在 Anthropic 上游腿」变成不可核的断言。判据三处共同决定，缺一不可 |
| §20 | 「`tests/unit/.../test_a_finished_turn_survives_a_failure_nothing_recognises` 里那句 `assert eligible(torn) is None`……评审**实跑 2 passed 并配了负样本对照**」 | 测试名 + 断言原文 + **「配了负样本对照」** | 「这个异常不是假想的」失去支撑；负样本对照是这条证据有效性的前提 |
| 方法学警告 | 「在 **2026-07-17 19:41 之前的 366 个 operation** 上**恒真失效**」 | 精确时刻 + 样本数 | 变成对 `from_history.py` 的全称否定，或反过来被当成已修 |

**一条横跨全表的判断（权重：够据此行动）**：这个文件的 provenance 质量**整体是高的**——绝大多数观测都带了样本量、时间窗或提交号，§11 与 §12 甚至记录了「原始分析保留原样」和「复核用的确切命令」。**它的问题不是 provenance 缺失，而是分类混乱**：已闭合的事实与未闭合的待办混在同一份文件里，读者无法只读待办。这印证了用户的裁决方向，也意味着**搬移的主要风险不是丢失 provenance，而是丢失编号与断链**（见 §二）。

**唯一一处 provenance 不足**：§8f「`schema.py:250` 称……实为 300+30，**全仓无此推导**」——「全仓无此推导」是一个**否定命题**，条目没有给出它是怎么搜出来的（搜的什么模式、什么路径集）。按项目规矩，否定结论需要枚举范围。搬移时应补，或降级措辞。**权重：倾向**（我未能复核，Bash 被封禁）。

---

## 六、汇总

### 判定分布（18 条编号条目 + 「明确不做」4 条 + 方法学警告 1 条 = 23 项）

| 判定 | 数 | 条目 |
|---|---|---|
| **已闭合** | **10** | §1、§2、§3、§6、§11、§18、方法学警告，+「明确不做」4 条中的全部 4 条 → 实为 7 + 4 = **11**（§1 含低优先残留但无行动可做，计入已闭合） |
| **部分闭合** | **5** | §4、§5、§7、§12、§19、§20 → **6** |
| **仍未闭合** | **5** | §9、§10、§15、§16、§17 |
| **明确不做** | **1** | §8g（在 §8 内） |

（§8 因七个子条判定不一，未计入上表整条；其内部分布为：已闭合 8a／8d + 「不需要全面重写」的裁断；部分闭合 8b；仍未闭合 8c／8e／8f；明确不做 8g。）

**结论（权重：够据此行动）**：**23 项里有 11 项已完全闭合、6 项部分闭合**——即**超过七成的内容不属于这个文件自称收纳的范围**。用户的裁决成立，且低估了程度。

### 缺哪些载体

| 缺的角色 | 影响哪些条目 | 建议 |
|---|---|---|
| **「已查清、修法唯一、只是没排期」的登记栏** | §16、§17、§9、8f、§15 的缺陷半边 | **不新建文件**，给 `deferred.md` 加第三栏。理由：项目 `project-review-principles` 技能已把 `deferred.md` 当作这类内容的落点 |
| **配置的隐式契约说明** | 8c（httpx `read=600`） | 真正的去处是用户的 `config.example.yaml`，我方不改；应写候选进 `.dev/human-controlled-docs-candidates/`（**该目录由项目 `CLAUDE.md` 确立，存在性我未核实**） |
| **别的主题的 deferred** | 8e（归 `deployment-systemd` / `graceful-shutdown`） | 移交。**那两个主题目录是否存在，我未核实** |
| **测试基础设施的陷阱清单** | 方法学警告 | 首选随 `from_history.py` 的 docstring；次选 `.dev/docs/test-infrastructure/`。**存在性未核实** |

**三处「存在性未核实」全部因 Bash 被封禁**，交回主会话（见 HANDOFF）。

### 不建议做的事（按项目价值观）

- **不建议**为搬移加任何校验脚本或门禁（项目明确禁止把结果检查升级成阻断装置）。§二 的断链风险应靠**墓碑 + 编号不回收**这一约定处理，不靠自动检查。
- **不建议**新建文件。本次清点找到的 23 项里，**19 项能落进已有的 4 份活文档**，真正缺载体的只有「已查清未修」这一栏，加栏比加文件便宜。
- **不建议**在同伴的工作树改动进入提交之前动 §19、§20、§5(a)、§12——这四条的「已闭合」判定全部依赖未提交状态。

---

## 七、交付阻塞（HANDOFF）

**本报告未能写入任务指定的 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-deferred-md-inventory.md`。**

原因：本会话被 harness 隔离在工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260822-never-silent-upstream-failure`。

1. `Write` 到共享 checkout 被拒：「Edit the worktree copy of this file instead of the shared-checkout path」。
2. 该隔离工作树**没有 `.dev/`**（`Read` 其 `.dev/README.md` → File does not exist；同路径下 `CLAUDE.md` 可读，证明工作树本身存在）。这与项目规则一致：「`.dev/` … exists **only at the main worktree root** — an isolated worktree has no copy」。
3. 因此在工作树内创建 `.dev/docs/tmp/` 会**违反项目规则**，并且该报告会随工作树清理而丢失。我判断不应这么做，故写入 `/tmp`（会话的额外可写目录）。
4. 清点进行到约三分之二时，`Bash` 被同一守卫**完全封禁**（守卫按 shell 持久 cwd 判定并忽略命令内的 `cd`，`cd /tmp && pwd` 亦被拒）。此后所有核实改用 `Read`。

**需要主会话处理**：

1. **把本文件移到指定路径**：`/tmp/260822-deferred-md-inventory.md` → `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260822-deferred-md-inventory.md`。
2. **三处存在性待核**（我因 Bash 封禁无法确认）：`.dev/human-controlled-docs-candidates/`、`.dev/docs/test-infrastructure/`、以及 `deployment-systemd` / `graceful-shutdown` 两个主题目录。8c、8e 与方法学警告的搬移去向取决于它们。
3. **一个我无法分辨的问题**：§19 的「让两条链路 message 发散」是同伴自行判断还是经用户裁决？这决定它进 `decisions.md` §三还是 §二之二。
4. **一条范围外但相关的冲突**（§四末）：`src/app/pipeline/hand_over.py:84` 的注释与它引用的 `decisions.md` §四第 1 条相互矛盾，且若把待裁项并入 §四会改动编号，使该引用失效。
5. **一处顺带查出的独立缺陷**（§5 行）：`tests/int/test_pipeline_app.py:3118` 的 docstring 称该结局是 bare re-raise，而工作树 `stream.py:366-386` 已改为发帧 + 上抛，描述已过时。该测试文件本身也在未提交改动列表中，可能同伴已在处理。

# K 片两份评审的处置

被处置的两份报告：

- [260824-context-condition-spec-review.md](260824-context-condition-spec-review.md)（设计与 Spec，异源模型）—— 0 blocker / 4 major / 3 minor
- [260824-context-condition-code-review.md](260824-context-condition-code-review.md)（实现与判据）—— 0 blocker / 3 major / 7 minor / 2 nit

两份独立收敛到同一条主要发现（判据与 Spec §5.5.1 双向不一致），这是本轮最强的信号：两个不同模型、不同判据来源、不同取证手段，各自从零走到同一处。

**采纳 11 条，部分采纳 1 条，驳回 1 条，登记 1 条。** 逐条如下。

## 采纳

### CCSR-02 / F-01（major，两份收敛）判据与 Spec 双向不一致

**属实，且是本轮唯一的真缺陷。** 实现比 Spec 宽了一条（裸片段 `prompt is too long` 升格为独立判据）、又丢了一条（`prompt token count of N exceeds the limit of M` 完全退出判定）。代码评审给出的反例最干净：`prompt_limit_counts()` 从 `prompt token count of 13613 exceeds the limit of 12288` 读出 `(13613, 12288)`，而隔着十五行的 `is_context_window_exceeded()` 对同一句说「不是超限」。

**处置**：

- 丢的那条补回来，且**由取数函数本身回答**（`return prompt_limit_counts(message) is not None`），而不是另立一份模式清单——两个函数不可能再对同一句话各说各话。
- 宽的那条**收回去**：裸片段从 `_CONTEXT_LIMIT_PHRASES` 删除。已记录的每一条含该短语的样本都同时带着 `code` 或数字，所以排除它不损失任何已观测形态；而上游回显请求派生字符串进 `error.message` 是**已观测**事实（回显工具名、回显 id 各一例）。
- Spec §5.5.1 改写成「**恰好三条**」，并把排除裸片段写成裁决与理由。

**写这条负控测试时发现了一件两份评审都没说的事**，已一并写进 Spec §5.5.1：排除裸片段**并不能**阻止误触发。条件未命中时本代理仍把上游原句逐字引用进 `message`，于是一条恰好含该短语的无关错误，其字节照样到达客户端并被它的子串判据命中。判据管的只是**本代理是否主张这是一次超限**——不改写、不贴 `model_max_prompt_tokens_exceeded`、保留上游原话。不为此裁剪上游原文：那会让代理编辑它唯一被要求原样带过的东西。

### F-02（major）三处零覆盖，评审用变异实测

评审跑了六条变异，其中三条**全绿**：删掉裸片段、完全不读 `error.code`、给 condition 加 `status == 400` 门。并用控制变异（删掉 `exceeds the context window`，7 红）证明这批测试整体有分辨力，所以那三个绿是覆盖缺口而不是探针失效。**这一步不能省，我自己那轮六条变异没做这个控制。**

它同时指出我的 docstring 说谎了：「三条样本无共享信号」不成立——Anthropic 腿那条同时带 `code`、数字与短语，把另两条判据互相遮蔽。

**处置**：新增四条**单信号**用例（只有 `code` / 只有片段 / 两条计数措辞各一），一条裸片段负控，以及一组状态码用例；docstring 改成实话。

### F-10（minor，升格处理）条件跨状态码生效会产出自相矛盾的信封

评审实测：`429 -> rate_limit_error + prompt is too long + model_max_prompt_tokens_exceeded`。它按 Spec 归为「Spec 层影响面缺口」而非实现违规——**这个定性是对的**，Spec §5.5.1 当时确实写着「不由状态码限定」。

**但后果比 minor 重**：客户端对该短语没有自己的状态码门，所以一个被改写成超限的 429 会让它立刻压缩并重发，这是被限流时最糟的动作。**按后果处置，不按报告的定级处置。**

**处置**：条件只在 `category is CLIENT` 时成立（覆盖 400/413/422 与其余 4xx，不含 `AUTH`/`RATE_LIMIT`/`PERMISSION`）。Spec §5.5.1 同步改写，并补一组测试钉住 400/413/422 为正、429/401/403/500 为负——不管结论是「限定」还是「不限定」，都需要一条测试说明这是选出来的而不是默认掉的。

### CCSR-04 / F-07（major / minor）按方言 `code` 只钉了键集合，没钉值

评审实测：把 `OPENAI_CONDITION_CODES` 的值改成 `wrong_spelling_entirely`，302 条全绿。全仓搜 `context_length_exceeded` 零命中。

**处置**：新增手工转录的 `CONDITION_CODE_CASES`，逐条写字面值并**实际调用 writer**，含 Gemini 的「无字符串 code」负向期望；另加一条断言它覆盖 `WireFormat` 全集。

### F-03（major）新表没对 `WireFormat` 求全，且它依赖的两条守卫根本不存在

**我核实了，属实。** `formats_with_writers()` 零调用者；`test_module_boundaries.py` 里 `reachable_from` 的调用点没有 `app.errors`。而 `write_error` 的 docstring 写着「and a test asserts it does」，`app/errors.py` 的模块 docstring 写着「and a test asserts it」——**两条都是对不存在的测试的承诺**。

更难看的是：`plan.md` 第 21 行早在 I 片就写明要加 `reachable_from("app.errors") == {"app.errors"}`，**计划写了，没落地**，而 docstring 已经按落地了写。叶子性质本身从未被破坏——是守卫不存在。

**处置**：建 `test_the_error_vocabulary_is_a_leaf` 与 `test_every_wire_format_can_be_spelled`；条件表的求全断言改成以 `WireFormat` 为真源、把 Gemini 写成具名排除。plan.md 第 21 行改成事实，并注明第二条（`app.pipeline` 不导入 `app.server`）**至今仍未落地**。

### CCSR-05（minor）我把「必须嵌套」写成了 context matcher 的必要条件——被探针证伪

**这条最该记住。** 我在 Spec §5.5.3、plan.md 与集成测试 docstring 三处都写了「扁平信封会让客户端只取顶层 `message`，本条随之失效」。评审跑了同目录现成探针的 case I：`400 + 顶层扁平 message` → `Eci=true`、`jXr=true`，**照样识别**。`makeMessage` 取顶层 `message` 并不会丢掉其中的短语。

嵌套仍然保留，但理由是 §6.3 自己的两条（Anthropic carrier 的合法形状、`overloaded_error` 判据要求关键词落在会被丢弃的字段里），**不是这一条**。借一条被证伪的因果去支撑一条正确的规范，是让 Spec 在没人重读的地方开始变错的方式。

**处置**：三处全改；那条测试改名为 `test_the_overflow_envelope_keeps_anthropics_own_shape`，docstring 写明它验的是协议结构而非识别机制，并写下这次是怎么错的。

### F-05 / F-06（minor）writer 派发：形状回落了，词汇没有

评审实测未知方言的输出：`type` 用 Anthropic 的表，`code` 却拿未知方言的名字去查条件表、查不到、回落成类别默认——**一个自称回落到 Anthropic 形状的信封，恰好缺了让 Anthropic 客户端起作用的那个拼写**。

**处置**：按它的建议改成先解析 writer、再把它真正在写的方言名传下去。`_gemini` 保留 `wire_format` 参数并在 docstring 写明为什么忽略它（签名统一是 `_WRITERS` 这张表的前提）。

### CCSR-03 / F-12（major / nit）流内腿不产生条件

两份评审对同一事实定级相差三档，分歧点是「Spec 该不该主张全路径覆盖」。事实一致：两个流内 reader 与 `OpenAIResponsesFramer.error()` 都绕过条件。

**处置**：**收窄 Spec**，新增 §5.5.4 把定义域明确限定为建流前的 HTTP 错误 body，并登记 [deferred.md](../deferred.md) E-12。收窄使两份评审的定级归一。

**为什么收窄而不是补实现**：48 例全部是建流前 400，**没有任何一例以流内事件到达**。客户端那侧倒是够得着（它的判据没有状态码门，流内帧上同样生效），但「客户端认得」不等于「上游会这么发」，据后者建映射就是替上游发明错误——与 E-10 拒绝为 `max_tokens` 溢出建映射是同一条理由。

### CCSR-06 / F-09（minor）`frozen spec` 措辞残留

`tests/int/test_error_envelope.py:3` 与 `src/app/server/http_errors.py:3`。2026-08-24 用户已废除冻结规则。**处置**：两处都改，后者改成描述「当时首次成为实施判据」，并指向 Spec 的条款修订记录。

### CCSR-07 / F-08（minor）证据层级高估与模块 docstring 不同步

我把 48 例本机录制与 1 例第三方录制统称为 first-hand。**处置**：注释改成分列两档；`app/errors.py` 的模块 docstring 补上第三类内容，并写明 `prompt_limit_counts` 这个计数抽取器为什么住在错误词汇模块里。

### F-11（nit）裸片段没复用常量

**随 CCSR-02 消失**：裸片段已从判据中删除，重复的字面量不再存在。

## 部分采纳

### CCSR-01（major）／ F-04（minor）IR 提前固化文案、丢掉结构化数字

两份对同一处给出强弱两版。设计评审要求把渲染整个移到领域层并**按方言**产出 `{message, code}`；代码评审只取窄的一半（结构化数字不该在 IR 边界丢），并明确把强的那半交回我裁。

**采纳的一半**：渲染函数 `condition_message(condition, counts)` 移进 `app/errors.py`，与词汇表放在一起。理由正是设计评审的：让每一处构造 `ErrorInfo` 的地方用同一种措辞，而不是各渲染各的——那正是「记录带着一个条件和一句与之矛盾的话」的成因，而类型不会说出来。

**驳回的一半：`message` 不按方言渲染。** 理由：

1. 按方言渲染意味着渲染发生在 writer 里，于是 `ErrorInfo.message` 会与客户端真正收到的话**不同**。这个分叉本项目已经付过代价并当场登记为缺陷（E-6、E-11），不该为了分层再造一个。
2. 今天没有任何方言想说不同的话。`prompt is too long` 在 OpenAI 与 Gemini 信封上也是可读的英文。
3. 机器可读的那一半**已经**按方言分了（`code`），这正是分层要保住的东西。

Spec §5.5.2 已经把这个取舍连同理由写下来，代码评审也据此明确不报它为缺陷。**若将来某个方言确实需要不同措辞，重开条件是那个方言出现，不是分层美观。**

**驳回 `ErrorInfo.condition_counts`**：今天**零消费者**。本项目对「原语留在没人调用的链路上」有过明确教训，plan.md J 片的「按首个生产消费者切，不提前建」就是那次的产物。数字已经进了 `message`（上游给了就在那儿），要它结构化的那个消费者出现时再加。

## 未采纳且不登记

无。

## 采纳后的复验

- 全量 1753 passed / 2 skipped，ruff 与 pyright 全通过，覆盖率 90%。
- 变异复跑，含评审实测为**全绿**的那五条（M17 不读 `error.code`、M8 状态码门、M15 OpenAI 拼写、M9 死回落、M7 裸片段），加本轮新机制四条。结果见提交信息与 [plan.md](../plan.md) K 片。

## 一条流程教训

我那轮六条变异**没有做控制变异**。六条全红读起来像「判据可靠」，实际只证明了「这六条被覆盖」——而评审用一条控制变异（删掉 `exceeds the context window` → 7 红）证明测试整体有分辨力之后，才敢把另外五条的全绿读成覆盖缺口而不是探针失效。**没有控制的变异结果，正面反面都读不出来。**

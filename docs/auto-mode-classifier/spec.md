# auto mode 分类器请求的本地处置 — Spec

> 状态：草案，随实现同步更新。证据基础是两份取证报告，见本文末「证据出处」。

## 1. 这解决什么

Claude Code 的 auto mode 在每次需要授权的动作前，会向 `/v1/messages` 发一次**独立的、非流式的**判定请求，让模型回答「这个动作该不该放行」。这个请求经反代到达本项目，并被当作普通对话请求转发给 Copilot 上游。

代价是实测的：一条真实样本（`history-v3.db`，`req_1786636259217_269`，2026-08-13）**上行 710179 字节**——其中分类器 system prompt 110851 字符、用户 CLAUDE.md 129683 字符、会话转录 272750 字符。每一次工具调用都要付一遍。two-stage 模式下阶段 2 还会再付一遍。

本特性让代理**识别出这类请求并就地作答**，不转发上游。

## 2. 边界：这不是什么

- **只在 Anthropic Messages 入站上生效。** 短路以 `context.inbound_format is WireFormat.ANTHROPIC_MESSAGES` 为前置。标记描述的是一个 body，不是一个端点；没有这道边界时，一个合法的 Chat Completions 请求只要 content 部分碰上标记，就会在 `/chat/completions` 上收到一个 Anthropic Message——调用方没有理由读得懂的协议——而它的真实请求永不到达上游。请求从哪个端点进来是路由已经知道的事，由路由来判。
- **不改写任何请求或响应体。** Claude Code bundle 内嵌的网关契约文档明确禁止改写（`app.pretty.js:648400` 一带）：`Never rewrite a request or response body instead — blocking substitutes the whole response; modification poisons prompt caching and diverges the client's view of the conversation.` 本特性替换的是**整个响应**，落在契约允许的一侧。
- **不处置其他权限相关请求。** `permission_explainer`、`auto_mode_critique`、`auto_mode_setup_propose`、`agent_classifier` 走同一端点、同一批请求头，但各有独有特征，一律透传。
- **不做判定。** 代理不理解被审查的动作，也不试图理解。它按配置给出一个**固定**答复。这是本特性的核心诚实性约束：它不是一个更便宜的分类器，它是一个开关。
- **客户端不知道是代理答的，而且会把它显示成一次模型判定。** `zGw` 在放行时返回 `reason: "Allowed by fast classifier"`（`368464`）并打成功遥测（含 `classifierType` / `classifierModel`）。也就是说 Claude Code 的界面与统计里，这次放行与一次真实的模型审查**同形**。当操作者与使用者不是同一个人时（本项目的 subagent 场景正是），使用者没有任何本地信号能分辨。这是打开开关的人需要知道的后果。

## 3. 判别

传输层完全不可区分：`user-agent`、`anthropic-beta`、`x-stainless-*`、`metadata.user_id` 与主对话逐字相同。`x-app: cli-bg` 判别力接近零（同期 6084 条里 5274 条是 `cli-bg`）。`anthropic-beta: auto-mode-classifier-2026-07-16` **在反代下永远收不到**——`Fm()` 要求 base URL host 为 `api.anthropic.com`（`app.pretty.js:64597-64606`）。

**只能靠 body 判别。** 命中需要**两个条件同时成立**：请求整体像一次分类器调用（结构门槛），且带有两个标记之一。

**结构门槛（S）**，三项全须满足，均读自真实样本、并与普通流量逐项相反（流量报告 §6.5）：无 `tools`、非流式、`messages` 里没有任何 `role == "assistant"` 的条目。

**标记（任一即可）**：

- **M1** `system` 为数组且**任一** system 块的 `text` 以 `You are a security monitor for autonomous AI coding agents.` 开头。
- **M2** 最后一条消息 `role == "user"`，其 `content[0]` 恰为 `{"type":"text","text":"<transcript>\n"}`，**且同一条消息后续块中存在闭合块** `</transcript>\n`。

### 为什么 M1 读任一块而不是 `system[0]`

客户端分类器请求设 `forceAttributionHeader: true`（`app.pretty.js:368459`），而 `Age()` 组装 system 时把计费归因文本块放在 index 0（`429857`）——所以「归因在 `system[0]`、监控 prompt 在 `system[1]`」是客户端的正常形态之一。本代理自己的归因剥离作用域是 `system[0]` 的起始若干行，剥完仍在 index 0 留一个块。锚定 index 0 会漏判。

放宽不损失精度：流量报告 §3.1 的排他性扫描本来就是在对象字节里找「这句话出现在任何位置」，145781 条 operation 里只出现在分类器请求中。

### 为什么标记不能单独成立

评审构造了两个**合法的普通请求**，各自触发一个裸标记：一个把第二个 system 块设成引用监控 prompt（「解释下面这段角色设定」），一个的最后一条 user 消息首块恰为 `<transcript>\n`（「总结下面的转录」）。两者在加门槛前都会被答以一句伪造的决定、且真实请求永不发出——**用户看不到发生了什么**。这是本特性最坏的失败模式，不是「错误的决定」，而是「真实请求被静默替换」。

一份评审判此条不成立，理由是这些形状需要刻意构造、而项目规则反对为想象的攻击者加防护。此处**不采纳**，理由是它衡量的对象不对：这里防的不是攻击者，是误伤——「用户发了一个首块恰为 `<transcript>\n` 的请求」是正常使用。更关键的是，该评审论证 M2 的精度依赖「M2 ⊆ M1 ⊆ 分类器」的传递，而那条链只在 **Claude Code 发出的流量**语料里成立；本代理服务任何 Anthropic 客户端，语料的排他性不能外推到语料之外。门槛的代价接近零：真实分类器请求 100% 满足三项。

`max_tokens` 被提议作为第四项门槛，**不采纳**：客户端的服务端可下发 `tengu_auto_mode_config` 同时改模型与 token 预算（`368661`），钉死它会加入一个比它要保护的标记衰减得更快的条件，且衰减方向与标记相同（漏判），因此不增加任何保护。

### 证据的推理链（避免循环论证）

M2「2300 条全中」**不能**单独作为召回率的独立测量：那 2300 条正是用 `previewText LIKE '<transcript>%'` 选出来的，用选择判据证明自己的召回率是恒真的。

非循环的论证是：**M1 匹配了这 2300 条全部，而 M1 在 145781 条里排他**，于是 M2 ⊆ M1 ⊆ 分类器，M2 在该语料上零误报。召回侧由结构保证——`zGw` 的转录块（`368454`）恒以 `<transcript>\n` 起头，且恒是最后一条消息的 `content[0]`。

### 失效方向

**识别的衰减是安全的**：标记认不出 → 返回 `None` → 请求照常转发，即启用本特性之前的行为。代价是省不下那 710 KB，不是答错。M1 是配置项，衰减了改一行配置即可；M2 是常量，衰减了要改代码——两者的易变性判断见 §5。

**这条只覆盖识别。** 一旦请求被识别，本特性仍可能答错，评审各自独立找到两条路径：把 severity 运行读成 block 协议，以及给出一个被客户端阈值比较判到反面的分值。两条都已修（见 §4.1），但被它们证伪的那句一般性承诺不再写——早期版本在四处写过「衰减只会漏判、绝不答错」，那句话对标记成立、对被标记门控的代码不成立。

衰减还有一条与客户端升级无关的通道：客户端的服务端可下发配置改变分类器的模式与模型，**客户端一个字节都不用变**。版本号是可观测的，这个不是。

用户自定义 auto mode 规则只替换 prompt 中部的占位槽（`app.pretty.js:150468`），severity 模式只重写 `## Output Format` 段（`368332`），**都不动首行**，故 P1 不受影响。

## 4. 处置：答复什么

命中后合成一个非流式 Anthropic Messages 响应，不打上游。

### 4.1 输出格式由请求决定

分类器有两种输出协议，解析器分别是 `oLl`（`app.pretty.js:368407`）与 `UGw`（`368422`）：

| 协议 | 解析正则 | 判别方式 |
|---|---|---|
| block | `/<block>(yes\|no)\b(<\/block>)?/gi` | 默认 |
| severity | `/<severity>\s*(\d+(?:\.\d+)?)\s*(<\/severity>)?/g` | 请求 `stop_sequences == ["</severity>"]`，**或**任一 system 块文本含 `<severity>` |

**两个信号都必须读，因为阶段 2 不带 `stop_sequences`。** 只读 `stop_sequences` 会把每一次 severity 阶段 2 判成 block——客户端此时握着 severity 解析器（`QRl`），拿到 `<block>no</block>` 会判不可解析并重试，而重试是又一个 710 KB。severity 模式下 `OGw()` 把 prompt 的 `## Output Format` 段改写成 severity 措辞（`368332`），这是 `<severity>` 出现在**请求**里的地方；分类器 prompt 的其余部分不提这个标签。

三条硬约束，违反任一条都会让客户端**重试**（`p1m` 的 `while (count <= maxRetries && !parseable && iLl(u) === "unparseable")`，`368542`），而每次重试又是一次 700 KB 上行：

1. **闭合标签可选，但决定词必须只出现一次。** `oLl` 先做一次全局扫描，若文本里同时出现 `<block>yes` 与 `<block>no` 直接返回 `null`。所以 `<reason>` 正文里**不得**出现另一个 `<block>…` 串。该扫描是 `/gi`，**大小写不敏感**，因此代理侧的过滤也必须如此——早期版本用大小写敏感的子串检查，`<BLOCK>no</BLOCK>` 与 `<BlOcK>no</bLoCk>` 都能穿过它并制造出一个带两个相反决定的回复。
   `block_reason_str` 是普通配置字段，无 schema 约束，所以这不需要恶意输入就能到达——写一句引用了 `<BLOCK>no</BLOCK>` 的说明就够了。
2. **severity 路径要求 `stop_reason ∈ {stop_sequence, end_turn}`**（`QRl`，`368418`）。block 路径不看 `stop_reason`。统一用 `end_turn` 同时满足两者。
3. **`content` 文本不得为空**，否则 `iLl` 判为 `policy_refusal`，走的是另一条失败路径。

### 4.2 合成的响应体

```jsonc
{
  "id": "msg_<24 hex>",
  "type": "message",
  "role": "assistant",
  "model": "<resolved model>",
  "content": [{"type": "text", "text": "<block>no</block>\n<reason>…</reason>"}],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {"input_tokens": 0, "output_tokens": 0}
}
```

`usage` 归零是诚实的：没有 token 被消耗。客户端把它累加进 auto mode 的开销统计，读到 0 正是事实。

放行时不带 `<category>`——分类器 system prompt 自己的要求是 `Do NOT include a <category> or <reason> tag when the action is allowed`，但 `<reason>` 对阻断有用，故仅阻断时写。

## 5. 配置

形状与键名由用户在 `docs/.human-controlled/config.example.yaml` 亲笔定下（2026-08-23），本节复述那份权威：

```yaml
hook_fix_anthropic_request:
  # 拦截并直接响应 auto mode 分类器的请求。
  intercept_auto_mode_classifier:
    #   passthrough: 透传
    #   allow: 直接允许
    #   block: 直接拒绝
    decision: allow

    match_system_prompt_prefix: "You are a security monitor for autonomous AI coding agents."

    block_reason_str: "Blocked by proxy, without a model review."
```

三个键，schema 默认 `decision: passthrough`——不写这一节就完全不生效。

### 匹配逻辑：哪里是「且」，哪里是「或」

```
decision != passthrough
  AND  结构门槛（无 tools、非流式、无 assistant 轮）
  AND  ( M1  OR  M2 )
```

两条标记之间是**或**，任一命中即可；它们与结构门槛之间是**且**。单靠一条标记命中不了——理由见 §3「为什么标记不能单独成立」。

### 各键的作用

**`decision`** —— 答什么。`passthrough`（默认）透传上游；`allow` / `block` 就地作答一个固定决定。

禁用态拼作 `passthrough` 而非 `false`。本项目另有 `assistant_message_layout`、`context_editing.enabled` 用布尔表示禁用，那是为了绕开 YAML 1.1 把裸 `off` 读成布尔的坑；`passthrough` 不是会踩那个坑的词，所以可以直说。

**`block_reason_str`** —— **不参与识别，是输出**。`block` 时写进合成回复的 `<reason>` 块，Claude Code 把它显示给使用者作为「为什么被拦」，这是本特性唯一被使用者看见的部分。`allow` 时不写（分类器 prompt 自己要求放行时不带 reason）。名字里的 `block_` 前缀说的就是这件事。

约束一条，不显然：文本里**不得出现任何大小写形式的 `<block>` 标签**。客户端先用 `/<block>(yes|no)\b/gi` 扫全文，一旦看到两个相反决定就判整个回复不可解析并**重试**——每次重试又是一次 710 KB。实现检测到就整段丢弃它：宁可拦得没有解释，也不能让回复坏掉。

**`match_system_prompt_prefix`** —— 识别标记 M1，分类器 system prompt 的首行，逐字抄来；**任一** system 块以它开头即算命中（不锚 `system[0]`，理由见 §3）。

### M2 是常量，不是配置项

M2 是客户端套在渲染后转录外面的开标签 `<transcript>\n`（命中要求最后一条 user 消息的 `content[0]` 整块恰等于它，且同一条消息后面存在对应闭合块；闭合标签由开标签推导）。它写死在 `app/pipeline/auto_mode_classifier.py`，**用户 2026-08-23 裁定**。

两条标记都是别人程序里的字面量，但**易变性不对等**，这是分开处理的理由：

- M1 是一句英文散文，会被润色改写 → 给旋钮。
- M2 是结构标签 → 钉死。

还有一条更硬的理由：M2 的值必须精确到尾部那个 `\n`，写成 `"<transcript>"` 就永远匹配不上，而且**失效是无声的**——只表现为命中数为零。一个几乎不需要改、又容易配错的键，留在配置面上只有负收益。

钉死不削弱它的兜底作用，反而更纯粹：M1 易变所以可配，M2 稳定所以钉死，M1 失效时正好由钉死的那条接住。反过来若 M2 真的变了，就是漏判 → 透传（方向安全），届时改代码。

### 为什么挂在 `hook_fix_anthropic_request` 下

这一族就是 `on_client_request_parsed` 那一刻，作用域限定在 Anthropic Messages 那条腿——正是本拦截的作用域：标记读 `system` 与 `messages`，答复是一个 Anthropic Message，短路点在 `fix_anthropic_request()` 返回之后、翻译之前。归属本身就表达了 §2 的入口边界。

与同族其余项的差别：别的项都在**修整一个将要发出的 body**，这一项是**不发了，就地作答**。所以 `fix_anthropic_request()` 不读它，读它的是 `handle()`。section 表达的是「何时、对什么生效」，不是「由哪个函数实现」。

### 5.1 severity 的分值：为什么是 101 而不是 100

severity 协议里，客户端拿分值与**服务端下发的阈值**做**严格大于**比较（`re > u.t1` / `re > u.t2`，`368463`、`368474`），阈值不在请求体里，代理看不到。

而 `nLl()` 接受 `0 <= 阈值 <= 100`。所以阈值恰为 `100` 的部署会把我们的 `100` 读成 `100 > 100 === false`——**一次放行**，给一个配置成 block 的请求。静默地把 block 变成 allow 是本特性最不能有的失败，所以 block 侧取 `101`。

`UGw` 不做范围校验，`101` 会被读成它本身的数值，越过客户端接受的每一个阈值。代价是它确实落在 prompt 自述的 `0-100` 量程之外：若将来客户端开始校验范围，这会变成不可解析并被重试，而重试耗尽后客户端得到自己的 `null`——一次「无法判定」，退回去问操作者。**静默放行比多问一次差。**

allow 侧没有这个问题：`0 > 阈值` 对范围内的每个阈值都为假，正是放行的答案。

早期版本取 `100` 并写下「端点值在任何合理阈值下都落在正确一侧」，两份评审各自独立证伪了它。原措辞的错误在于把「prompt 自述的量程」当成了「客户端接受的阈值范围」。

## 6. 可观测性

命中时打一条 INFO，含：命中的判据（P1 还是 P2）、协议（block / severity）、给出的决定、请求体字节数。字节数是本特性的价值度量——它就是这次省下的上行量。

判据失效是静默的（漏判 → 透传），所以**命中计数本身是那条判据还有效的唯一信号**。

## 7. 不做

- 不缓存、不按动作类型分流、不接入任何外部策略引擎。任何「更聪明的判定」都会把这个开关变成一个没人审过的安全组件。
- 不处置 §2 列出的其余四类请求。
- 不落盘被审查的动作。转录正文里有用户完整 CLAUDE.md 与会话历史，日志只记字节数与判据，不记内容。

## 8. 证据出处

- 代码侧（Claude Code 2.1.241 / 226 / 207 静态提取）：`.dev/docs/tmp/260823-cc-auto-mode-request-shape.md`
- 流量侧（2300 条真实上行 body，2026-07-25 ～ 08-13）：`.dev/docs/tmp/260823-auto-mode-traffic-samples.md`
- 本文引用的 `app.pretty.js` 行号均指 `~/.claude/refs/claude-code-2.1.241/app.pretty.js`。行号是该版本的快照，版本一换即失效。

## 9. 已知的适用性限制

本机 `~/.claude/settings.json` 当前是 `defaultMode: "bypassPermissions"`，该模式下分类器**根本不会被调用**。所以在当前配置下本特性无流量可处置，属于「为切换到 auto mode 准备的能力」，不是当下生效的优化。这一点必须让使用者知道，否则打开 `decision` 后看不到任何命中会被误读为实现有问题。

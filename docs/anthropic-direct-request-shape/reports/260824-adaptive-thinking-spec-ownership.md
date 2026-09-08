# adaptive thinking / `output_config.effort`：这条行为归哪份 Spec 管

**日期**：2026-08-24
**性质**：纯文档侧调查。**未修改任何代码或文档**，只读。
**触发**：线上 400 —— 客户端发 `claude-sonnet-4-5`，经 `model_mappings` 映射为 `claude-sonnet-5`，走 Anthropic → Anthropic **直连路径**（`route.translation_required == False`，endpoint `/v1/messages`），上游拒绝 `"thinking.type.enabled" is not supported for this model. Use "thinking.type.adaptive" and "output_config.effort" to control thinking behavior.`

---

## 0. 结论摘要

1. **没有任何一份现有 Spec 拥有这条行为。** 它落在一个真实的空格里：用户亲笔文档里有**恰好合适的落点**（`message-format-reshape.md` 的「向上游输出 Anthropic Messages」一节），但那一节今天只写了两条 thinking **块布局**的整形，一个字都没写 `thinking.type` / `output_config` / `reasoning_effort` / adaptive。
2. **直连路径上按目标模型能力改写请求体，是被现有 Spec 明确允许的**，且已有两个先例在跑（`strip_anthropic_beta_flags` 的按模型剥离、`strip_both_empty_thinking_blocks` 的常驻整形）。允许它的原话是 `message-translation.md:7`。
3. **与用户亲笔文档的冲突点只有一个，而且只在"反应式"设计上出现**：`upstream-retry-and-continuation.md:9` 把 400 列为「无法继续」。**主动式（发送前按能力改写）完全不触碰这条**。
4. **落笔位置在用户亲笔文档里，我不能自己改。** 需要向 `.dev/human-controlled-docs-candidates/` 提交候选片段并请用户追认。
5. **`.dev/docs/` 下没有任何 topic 拥有「Anthropic 直连路径的请求体构造」**。事实证据已经齐了（在 `sync-refs/sxwxs-ghc-api/` 的一份报告里，逐字包含任务背景引用的那几处 `messagesApi.ts` 行号），但它是**时点报告**，自述范围是翻译腿的 `reasoning.py`，不是直连腿。需要新建一个 topic。

---

## 1. 归属判定：这条行为该写在哪

### 1.1 唯一合适的落点 —— `docs/.human-controlled/message-format-reshape.md` 第 65 行起

该文件第 65 行是一级小节：

```
/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-format-reshape.md:65
## 向上游输出 Anthropic Messages
```

它下辖两小节，**都是 thinking 相关，都是请求体整形，都在直连腿上**：

- `:67` `### assistant 消息的 thinking / redacted_thinking 块不允许相邻（400 "thinking blocks cannot be modified"）`
- `:76` `### 剥离 signature text 都为空的 thinking/redacted_thinking 块`

判定：**这一节就是「发往 Anthropic 上游的请求体要做哪些整形」的权威所在**，`thinking.type` 的能力改写与它同族、同腿、同方向，理应作为该节的第三个 `###`。文件名本身（「模型请求与响应的消息格式的**整形**」）与文件开头第 3 行的立意也直接对上：

```
message-format-reshape.md:3
GHC API 虽然声称支持 anthropic `/messages` `/messages/count_tokens` 和 openai `/responses` 等，但有其怪癖，我们需要按需消毒。
```

—— 我们这次撞上的正是一个「怪癖」：GHC API 对 `claude-sonnet-5` 不接受 `thinking.type: enabled`。

### 1.2 `.dev/docs/` 侧：没有归属 topic，需新建

清点了 `.dev/docs/` 下全部 33 个 topic 目录的 `README.md` / `spec.md` / `status.md` / `deferred.md`。**没有一个 topic 管「Anthropic 直连腿的请求体构造」。**

现存最接近的三处，都不是归属地（否决理由见 §4）：

| 目录 | 内容 | 为什么不是归属地 |
|---|---|---|
| `.dev/docs/sync-refs/sxwxs-ghc-api/` | 有一份 38KB 的 `messagesApi.ts` 逐行考据，**逐字包含任务背景引用的 `:144-177`、`:233-234`、`spec.md:809-826`** | 是 evidence 目录，无活文档；报告第 4 行自述「校正我方 `translation_driver/reasoning.py`」，**射程是翻译腿** |
| `.dev/docs/anthropic-responses-bridge/` | `spec.md:205` 确实规定了 thinking 的 capability gate | `spec.md:30` 的范围边界写死「Anthropic Messages 入站**选择 Responses upstream 后**的完整请求生命周期」——我们这条 `translation_required == False`，不在范围内 |
| `.dev/docs/hooks-subscription-migration/reports/` | 存着 `strip_anthropic_beta_flags` 的落地报告（同族先例） | reports-only 的迁移 topic，无活文档，不是行为 owner |

**建议**：新建 `.dev/docs/anthropic-direct-request-shape/`（名字待定），放 `spec.md` + `reports/`。这与 `sync-refs/sxwxs-ghc-api/260822-round2-disposition.md:62` 已经写下的建议吻合——那一行说 Claude 系模型「只能走直连。超出本轮范围，**建议单独立项**」。

---

## 2. 现有 Spec 已经说了什么（逐条引用）

### 2.1 直连路径上改写请求体：**明确允许**，不是禁止，也不是没提

```
/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-translation.md:7
对于直连路径，采用尽可能原样转发的原则。当我们需要理解和处理时，才分析和处理对应部分。
```

这句话的两半都要读全：默认原样转发，**但"当我们需要理解和处理时"是写在同一句里的授权**，不是例外说明。

同一原则在请求头一侧被写成黑名单机制（`message-format-reshape.md:11`：「一般地，**直连路径上**，客户端请求头值得原样转发给上游，仅部分请求头是需要剥离的，即采用黑名单机制」），而 `error-envelope/spec.md:47` 引用这一条时也确认了它的射程：

```
/home/xp/src/ghc-api-proxy-py/.dev/docs/error-envelope/spec.md:47
**第 1 条与既有条款同形。** `message-format-reshape.md:11` 对请求头写明：直连走黑名单、翻译走白名单。
```

注意 `error-envelope/spec.md` 的「直连透传」是**响应/错误方向**的（文件标题第 1 行：「错误信封：直连透传 / 翻译过 IR」），它不管请求体构造，不构成对本行为的禁止。

### 2.2 已有两个同族先例在跑：按模型能力改写直连请求

**先例 A —— `strip_anthropic_beta_flags`（请求头，按模型）**

```
/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/message-format-reshape.md:37-49
### 按需剥离 `anthropic-beta` 请求头的部分 flag

`anthropic-beta` 请求头表示希望访问的功能特性，是与模型能力相关的，不满足则报错 `400 invalid beta flag`。
```

配套配置（`config.example.yaml:439-448`）：

```yaml
hook_strip_anthropic_request_headers:
  # 特定能力请求头只针对特定模型有效，按需剥离。
  strip_anthropic_beta_flags:
    claude-sonnet-4.6:
      - interleaved-thinking-2025-05-14
      ...
```

**这条先例的形状与本次几乎一模一样**：一个模型能力位决定要不要改写出站请求，不改写就吃 400。它已于 2026-08-22 落地并通过独立评审（`.dev/docs/tmp/260822-review-beta-flag-strip.md`）。

⚠️ **并且它踩过一个坑，本次很可能重演**——同一份评审的第 6 行：

> 剥离表按 `resolved_model` 匹配，而用户亲笔 `config.example.yaml` 里那唯一一张表的键 `claude-sonnet-4.6` 在同一份文件里恰好是 `model_mappings` 的**键**（映射到 `claude-sonnet-5`）；两段配置同时生效时整张表空转。

本次的请求形状正是这个：客户端说 `claude-sonnet-4-5` → `model_mappings` 映到 `claude-sonnet-5`（`config.example.yaml:145`）→ 能力要按 `claude-sonnet-5` 查。**如果新行为是"读目录能力"而不是"查一张手写的按模型表"，这个坑天然不存在。**

**先例 B —— 常驻的 thinking 块整形**

```
message-format-reshape.md:76-78
### 剥离 signature text 都为空的 thinking/redacted_thinking 块
曾经用 `hook_fix_anthropic_request.thinking.strip_both_empty_thinking_blocks` 配置控制生效，现在我认为这是应该常驻的。
```

用户亲笔地把一条直连请求体改写从「可配置」升级为「常驻」。这说明**用户对直连腿上主动改写请求体本身没有意见**。

### 2.3 `thinking` 字段：现有 Spec 只说了**块布局**，没说 `type`

`docs/.human-controlled/` 下 `thinking` 的全部命中（14 处）分两类，无一涉及 `type` 的取值：

| 位置 | 讲的是什么 |
|---|---|
| `message-format-reshape.md:67-74`、`config.example.yaml:537-544` | `assistant_message_layout`：assistant 消息里 thinking 块不许相邻 |
| `message-format-reshape.md:76-78` | 剥离 signature/text 皆空的 thinking 块 |
| `message-format-reshape.md:82-86`、`config.example.yaml:571-576` | `hook_fix_anthropic_sse.thinking.content_block_start_compat`：**响应**方向的 signature 整形 |
| `config.example.yaml:505-518` | `context_editing` 的 `clear-thinking`：修剪旧 thinking 块 |
| `config.example.yaml:546-557` | `strip_all_thinking_blocks_on_reject`：400 "thinking … cannot be modified" 的兜底 |
| `config.example.yaml:298`、`:444` | keepalive 措辞、beta flag 列表 |

**`thinking.type` 的取值（`enabled` / `adaptive` / `disabled`）在用户亲笔文档里零命中。**

### 2.4 `output_config`：用户亲笔文档里**零命中**

`rg -i 'output_config' docs/.human-controlled/` → 无结果。这个键在整个 `docs/` 下不存在。

### 2.5 `reasoning_effort` / adaptive thinking：只在翻译腿被规定过

用户亲笔文档：`reasoning_effort`、`adaptive` 均零命中（`config.example.yaml:298` 的 `adaptive` 属于误配，那是 keepalive 措辞里的英文词）。

`.dev/docs/` 侧唯一的规范性条款：

```
/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/spec.md:205
- Anthropic `thinking.enabled`／`adaptive` 映射为 Responses `reasoning` 配置时，必须受模型 `reasoning_effort` 能力与 budget limits 约束。不能把 budget heuristic 当作模型明确支持。
```

**射程仅限翻译腿**（Anthropic → Responses）。同 spec 的范围边界：

```
anthropic-responses-bridge/spec.md:30
本规格覆盖 Anthropic Messages 入站选择 Responses upstream 后的完整请求生命周期，包括 route selection、capability gate、双向转换、非流与流式输出、retry、operational lifecycle 和兼容性。
```

### 2.6 已有的事实证据（不是 Spec，但直接可用）

`.dev/docs/sync-refs/sxwxs-ghc-api/260822-vscode-copilot-chat-reasoning-values.md` **已经逐字记录了任务背景里引用的那份契约**，且已标好证据权重：

- `:173-211` 逐字引用 `messagesApi.ts:144-177`（`supportsAdaptiveThinking && !thinkingExplicitlyDisabled` → `{type:'adaptive'}`；否则走 min/max budget 分支）
- `:212-217` 逐字引用 `messagesApi.ts:233-234`（`thinking` 与 `output_config: {effort}` **并列发出、互不相干**）
- `:221-235` 引用单测 `messagesApi.spec.ts:809-826`
- `:446-457` 「Anthropic 侧：有，且是官方的首选」——「只要模型支持 adaptive，官方就用 adaptive，用户配的 budget 直接被忽略（除非配成 0）。今天目录里所有 Claude 模型 `adaptive_thinking: true`，所以官方对 Claude 实际上从不发 `budget_tokens`」
- `:456-467` 配套的 beta header 切换（`chatEndpoint.ts:193-197`：不支持 adaptive 才加 `interleaved-thinking-2025-05-14`）——**这一条与我们已落地的 `strip_anthropic_beta_flags` 直接相关，可能是同一个决策的两半**
- `:126-129` 一张目录能力表，含 `claude-sonnet-5` = `low, medium, high, xhigh, max` + `adaptive_thinking: true`

⚠️ 该报告第 26 行有一条自带的时效限定必须一并带走：**vscode-copilot-chat 仓库已归档，代码停在 2026-04/05，而模型目录是活的**。报告第 419-424 行据此判定 `messagesApi.ts:172-176` 那个硬编码 `low|medium|high` 三项比较**在今天是一个静默降级的 bug**（目录已给 `claude-sonnet-5` 发 `xhigh`/`max`，官方会把它们吞成"不发 `output_config`"）。**照抄官方这一段会把这个缺陷一起抄进来。** 报告 §8 的建议是「保持我方的向下取 + 上浮标记，不要学官方的不发字段」。

### 2.7 代码侧的现状（一句话，用于判断这是不是 Spec-implementation 漂移）

不是漂移，是**双向的空白**：

- `rg 'adaptive|output_config' src/app/` 的命中**全部**在 `src/app/protocols/anthropic_responses.py`（legacy 翻译链）与 `src/app/pipeline/translation_driver/`（活翻译链）。直连腿零命中。
- `adaptive_thinking` 在 `src/app/` 只有一处：`src/app/models/capabilities.py:15`，属于 **legacy** 的 `ModelSupports`。活链路的 `ModelDescriptor`（`src/app/model_provider/types.py:70-77`）只带 `reasoning_efforts`，**没有 `adaptive_thinking`**，`github_copilot.py:114` 也只 parse 了前者。

即：要落这条行为，先得把 `adaptive_thinking` 从目录带进活链路的 `ModelDescriptor`。这与 `260821-design-thinking-effort-wiring.md:33` 记下的那个数据断点是同一个（「`replace_catalog` 投影出的 `ModelDescriptor` 只有 endpoint、unknown endpoint 与 request headers，reasoning capability 在活链路的路由对象中消失」）。

---

## 3. 与用户亲笔文档的冲突点

`docs/.human-controlled/` 是用户亲笔、权威最高、**我不得擅自修改**（`docs/.human-controlled/README.md:5`：「你不能亲自动手修改本系列文档，但可以提供文档或片段，写入 `.dev/human-controlled-docs-candidates/` 目录」）。

### 冲突 1（只对"反应式"设计成立）：400 被列为「无法继续」

```
/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md:5-9
这些情况下无法继续：
- 客户端已断开，取消上游请求
- 代理的保护机制触发（如块的内存缓存超限）
- 400，包括请求非法和输入超长
```

若设计成「收到这个 400 → 改写 `thinking` → 重试」（即 `copilot-api-js` 的 `legacy-thinking-retry.ts` 那种反应式策略），**字面上撞这一条**。

**但这条已经被用户自己的其他亲笔内容限定过，不是铁板一块**——三处证据：

```
config.example.yaml:315
# 包括网络抖动、上游 5xx、部分 400 协商重试等所有「再发一次上游请求」的原因。
config.example.yaml:318
# For all reasons that cause "send another request to GHC": network blip, upstream 5xx, some 400-class negotiation retries, etc.
```

```
config.example.yaml:546-557
# 兜底处理 400 "thinking ... cannot be modified"，去除所有 thinking/redacted_thinking 块并重试一次。
strip_all_thinking_blocks_on_reject:
  enabled: true
```

```
config.example.yaml:520-535（整段注释掉，是用户写下的模板形状）
# # 有的模型会拒绝 messages 中包含 role: "system" 的消息，实测 GHC API claude-sonnet-4.6 / claude-haiku-4.5 报 `Unexpected role "system"` 400 …
# message_role_system:
#   # 是否主动改写
#   proactive: false
#   # 是否反应式学习？当 HTTP 400 是因为该原因，标记该模型、改写、重试
#   reactive: as_role_assistant
```

最后这段**是用户亲手写下的、与本次问题同形的处置模板**：一个按模型的 400，两个开关——`proactive`（发送前主动改写）与 `reactive`（400 触发学习 + 改写 + 重试）。它今天是注释态，说明形状已经想清楚但尚未启用。

**判定**：`upstream-retry-and-continuation.md:9` 与 `config.example.yaml:315/546/535` 之间**已经存在一处需要用户澄清的张力**，这不是本次引入的。但本次只要选**主动式**（发送前按目标模型能力构造 `thinking`），就**根本不产生上游 400，也就完全不碰这条**。这是回避冲突的干净路径，也是官方第一方客户端的做法。

### 冲突 2（必然）：落笔位置在用户亲笔文档里

新行为的规范文本要进 `message-format-reshape.md` 第 65 节；若引入配置开关，还要进 `config.example.yaml`。两者我都不能动。
→ **必须走 `.dev/human-controlled-docs-candidates/` + 用户追认。**

### 冲突 3（需用户裁决）：能力缺席时的默认行为

用户亲笔文档在两处表达过 fail-closed 倾向（`model_mappings` 前言 `config.example.yaml:100-102`：「仍不可用则放弃映射、直接透传（**上游随后拒绝它**）」），但没有对 thinking 能力表态。目录里查不到 `adaptive_thinking` 时该原样透传、还是按 budget 走 enabled、还是拒绝——**这是一个用户从未决策过的开口**，按 `no-silently-cut-but-defer` 应交回裁决，不由我定。

### 非冲突（澄清）

- **主动改写请求体本身不冲突**：`message-translation.md:7` 授权，`message-format-reshape.md:37-49/76-78` 有两个已生效的先例。
- **`output_config` 是新增字段而非改写**：用户亲笔文档对它零表态，属于「没提」而非「禁止」。
- **与 `strip_anthropic_beta_flags` 不冲突，但可能重叠**：官方在 `chatEndpoint.ts:193-197` 把「支持 adaptive」与「不发 `interleaved-thinking-2025-05-14`」绑成同一个判据。用户亲笔的 `config.example.yaml:443-444` 恰好也在给 `claude-sonnet-4.6` 剥这个 flag。**这两件事可能是同一个能力位的两个后果**，值得在候选片段里一并指出，但不要自作主张把两者合并——那张表是用户手写的。

---

## 4. 已有登记情况：查过了，**没有**已登记条目

在 `.dev/docs/*/deferred.md`、`*/status.md`、`*/spec.md`、`*/plan.md`、`*/README.md`、`*/decisions.md`（全部活文档）里搜 `adaptive` / `effort` / `output_config` / `thinking` / `sonnet-5`：

**结论：没有任何活文档登记过「Anthropic 直连腿的 adaptive thinking」或这次的 400。** 逐条排查如下。

| 命中 | 内容 | 是不是本条 |
|---|---|---|
| `anthropic-responses-bridge/spec.md:205` | thinking→Responses reasoning 的 capability gate | **否**，翻译腿 |
| `auto-mode-classifier/deferred.md:67` (D4) | Claude Code 内嵌网关契约里有 `error.message` → 类别映射表，含 `thinking_type:<...>`、`effort_unsupported` | **否，但相邻且有用**。它管的是「我方错误怎么让客户端正确恢复」，不管请求构造。D4 状态「未展开」，并建议「单独立一个 topic」 |
| `upstream/retry-and-continuation/deferred.md` | 全文无 thinking-type 相关条目 | 否 |
| `error-envelope/deferred.md`、`plan.md` | 只有直连**错误**透传 | 否 |
| `delivery-keepalive/*`、`client-leg-formats/deferred.md`、`server-layout/deferred.md`、`history/*`、`tui/deferred.md` | 无关 | 否 |

**最接近一条登记的东西在报告里，不在活文档里**：

```
.dev/docs/sync-refs/sxwxs-ghc-api/260822-round2-disposition.md:62
- **`claude-sonnet-5` 不支持 Responses API**（实测 `unsupported_api_for_model`）。这意味着翻译路径承载不了 Claude 系模型，它们只能走直连。超出本轮范围，建议单独立项。
```

这行写于 2026-08-22，**正确预告了本次故障的成因**（Claude 系只能走直连 → 直连腿的 thinking 构造没人管过），并已建议立项。**它至今没有被提炼进任何活文档**——这本身就是一处「报告成了唯一真相来源」的违规，值得在新建 topic 时一并清掉。

其余两处需要一并带走、但不属于本条的相邻缺口（`260822-round2-disposition.md:52-56, 63`）：`reasoning.summary` 发不发（待裁决），`include: ['reasoning.encrypted_content']`（已核对，非缺口）。

---

## 5. 我否决/排除掉的候选

| 一度以为归它管 | 排除理由 |
|---|---|
| `.dev/docs/anthropic-responses-bridge/spec.md` | 它是**唯一行为 oracle**（`README.md` 权威边界表）且 `:205` 恰好规定了 thinking 的 capability gate，看着最像。排除依据是它自己的范围边界 `spec.md:30`：只覆盖「入站**选择 Responses upstream 后**」的生命周期。本次 `translation_required == False`，端点是 `/v1/messages`，不在范围内。**把它当归属地会把一条直连行为写进翻译腿的 oracle，是实打实的越界。** |
| `.dev/docs/error-envelope/spec.md` | 因为触发物是一个 400，第一反应查了它。排除：它管的是**错误信封的渲染与透传**（标题第 1 行「错误信封：直连透传 / 翻译过 IR」），§5.2/§5.3 是「上游状态码 → category」。全文没有一条讲「改写请求以避免错误」。它是这条 400 **到达客户端后**怎么长的 owner，不是**为什么会发生**的 owner。 |
| `docs/.human-controlled/upstream-retry-and-continuation.md` | 若走反应式设计，它确实要改。排除为**归属地**：它管的是「失败之后怎么办」，不管「发出去的请求长什么样」。主动式设计下它一个字都不用动。它在本报告里的角色是 §3 的冲突源，不是 owner。 |
| `docs/.human-controlled/message-translation.md` | 名字最像，且第 7 行正是那条授权。排除：文件第 3 行自述「采用『输入格式 <-> 中间表示 <-> 上游模型格式』的方式」，第 11 行起全是 `anthropic-messages <-> openai-responses` 的字段对照。它管**翻译腿的映射规则**；直连腿在它这里只有第 7 行那一句原则，具体整形条目一律在 `message-format-reshape.md`。 |
| `docs/.human-controlled/request-pipeline.md` | 管路由判定与扩展点形态（`ClientRequest` / `UpstreamAttempt` / 事件订阅），不含任何字段级行为。排除。 |
| `docs/.human-controlled/api.md` / `ghc-api.md` | 前者是端点清单，后者是 provider/base URL/驱动模块对照表。都不含请求体语义。排除。 |
| `.dev/docs/client-leg-formats/` | 名字里有 formats，查了。排除：`README.md:3` 自述管「客户端用哪种协议问，回复就用哪种协议答」——**响应腿的 framer/assembler 选择**。 |
| `.dev/docs/pipeline-rewrite-parity/` | `reports/260818-traffic-feature-gap.md:55` 恰好记着「新链没有把 Anthropic adaptive thinking／effort 映射为 Responses 的 reasoning」。排除两条：(a) 那说的是**翻译腿**；(b) 该 topic 只有 `reports/`，无任何活文档，是时点差距分析，不是行为 owner。 |
| `.dev/docs/sync-refs/sxwxs-ghc-api/` | 证据最全，一度想直接在这里立 spec。排除：整个目录只有报告没有活文档，且报告第 4 行把自己的射程写死在 `translation_driver/reasoning.py`。**报告是证据，不是权威**——按项目规则「不要让报告成为唯一真相来源」。它应当被新 topic **引用**。 |
| `.dev/docs/hooks-subscription-migration/` | 存着最像的先例（`260822-beta-flag-strip-implementation.md`）。排除：reports-only 的迁移 topic，迁移早已完成，不是任何运行时行为的 owner。 |
| `.dev/docs/empty-text-block/` | 名字是一条具体的请求整形，形状同族。排除：同样 reports-only，且它是**一条已闭合的具体缺陷**的记录，不是一个行为面。 |
| `.dev/docs/auto-mode-classifier/deferred.md` D4 | 里面确实有 `thinking_type:` 与 `effort_unsupported` 这两个字符串。排除为归属地：那是 Claude Code **网关契约**的错误分类表，管出站错误的客户端恢复语义。**但它与本条相邻，D4 自己也说"建议单独立一个 topic"**，新 topic 建立时值得交叉引用。 |
| 新建 `.dev/docs/thinking-and-effort/` 这类跨腿 topic | 想过把两条腿的 thinking 策略收在一起。倾向否决：翻译腿的 `reasoning.py` 已有成型实现与 `anthropic-responses-bridge/spec.md:205` 的管辖，合并会造成两个 owner 争同一段文字。建议新 topic 按**腿**切（直连腿的请求体构造），在文中引用翻译腿的既有条款。**这一条是我的倾向，不是判定，可由主会话推翻。** |

---

## 6. 给主会话的落笔建议（不是裁决）

按「绝不绕开 Spec」，动手前的顺序：

1. **新建 `.dev/docs/<新 topic>/spec.md`**，把直连腿的 `thinking` / `output_config` 构造规则写完整（含能力缺席时的行为、effort 的来源、与 `strip_anthropic_beta_flags` 的关系），并引用 `sync-refs/sxwxs-ghc-api/260822-vscode-copilot-chat-reasoning-values.md` 作为证据来源。**注意带上该报告 §0 的归档时效限定与 §8 的「不要学官方的不发字段」。**
2. **同步向 `.dev/human-controlled-docs-candidates/` 提交一份 `message-format-reshape.md` 第 65 节的候选新增小节**，请用户追认。用户追认前，`.dev` 侧的 spec 是我方的推导，不是用户裁决。
3. **交回用户裁决的开口**（§3 冲突 1、冲突 3，以及 §4 末尾遗留的 `reasoning.summary`）。
4. 顺手把 `260822-round2-disposition.md:62` 那条预告提炼进新 topic 的活文档。

---

## 附：本次检索范围（用于判断"未找到"的可信度）

全部只读，在 `/home/xp/src/ghc-api-proxy-py` 下执行：

- `docs/.human-controlled/` 15 个文件全部列出；`thinking|output_config|reasoning_effort|adaptive` 全文搜索，14 处命中逐条读；`message-format-reshape.md`、`message-translation.md`、`request-pipeline.md`、`api.md`、`ghc-api.md`、`README.md`、`upstream-retry-and-continuation.md` 全文读；`config.example.yaml` 读 100-150、318-350、439-470、496-600 段并做顶层键清单。
- `.dev/docs/` 33 个 topic 目录逐个列出、有 `README.md` 的读头部；`*/deferred.md */status.md */spec.md */plan.md */README.md */decisions.md` 全体搜 `thinking|adaptive|effort|output_config|直连|passthrough|直通`。
- `.dev/docs/sync-refs/sxwxs-ghc-api/260822-vscode-copilot-chat-reasoning-values.md` 读 §0、§2、§6、§7、§8 与标题结构；`260822-round2-disposition.md` 全文读；`260821-design-thinking-effort-wiring.md` 读 §1-§5 头部。
- `.dev/docs/anthropic-responses-bridge/spec.md` 读 1-60 行 + `adaptive|thinking.*capab|budget_tokens` 全文搜；`error-envelope/spec.md` 搜 400/重试/§6；`client-leg-formats/README.md` 全文读；`.dev/docs/tmp/260822-review-beta-flag-strip.md` 读 1-60 行。
- 代码侧仅两条只读 `rg`（`adaptive|output_config`、`reasoning_effort|adaptive_thinking`，范围 `src/app/`），用于判断是否存在 Spec-implementation 漂移。

**`docs/.human-controlled/README.md` 的清单里列了 `observability.md`，但该文件在磁盘上不存在。** 与本任务无关，顺手记下。

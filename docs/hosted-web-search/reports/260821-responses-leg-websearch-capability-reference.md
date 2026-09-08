# Responses 腿的 web search 能力处理：参考实现在哪、我们错在哪

日期：2026-08-21
性质：对照调查结论 + 我方缺陷定性
触发：用户三次指出「responses leg 没有使用最正确的处理方法」，第三次明确「用户说的是 responses leg 具有 web search 能力」

## 0. 结论先行

参考项目在 Responses 腿上的 web search 能力处理，**核心不在响应侧渲染，而在请求侧的「反应式协商」**：不预判哪个模型支持搜索，而是照发，被上游拒绝后从错误消息里学到「这个模型不支持」，写进按 (endpoint, model) 键控的协商缓存，并在**本次**重试里确定性地剥离。

我实现的是它的反面：一张手写的模型清单 `models_support_web_search`，清单外一律合成失败。**这正是参考项目 2026-07-13 明确移除掉的那套东西。**

## 1. 三个参考实现在 Responses 腿上各做了什么

| 项目 | 请求侧声明 | 能力判定 | 响应侧呈现 |
|---|---|---|---|
| `copilot-api-js` | `web_search_*` 前缀 → 裸 `{type:"web_search"}` | **无清单，反应式学习** | 一行文本（含上游 416 字符 id） |
| `hooyao-copilot-bridge` | Codex 客户端自带 | 不适用 | Claude 边一行文本（marker 被擦除） |
| VS Code 扩展 | **过滤掉** | 不适用 | 无消费者 |

### 1.1 VS Code 扩展在 Responses 腿上不支持，已穷尽核对

`oaiLanguageModelServer.ts:136` 过滤 `tool.type.startsWith('web_search')`，新旧两份副本都在。全仓 `rg 'web_search_call'` **零命中**，而 `image_generation_call` 在 `responsesApi.ts:1456`／`:1539` 有两处——它是**选择性地只接了一个 hosted item**，不是不知道。

扩展里完整的原生 web search 支持在 `byok/vscode-node/anthropicProvider.ts`，那是 **Anthropic 直连（BYOK）腿**。用户 2026-08-21 裁决：**不采用该做法，Anthropic 腿仍然不支持。**

### 1.2 `copilot-api-js` 的反应式协商（这是要抄的东西）

三个文件构成一套完整机制：

**`src/lib/request/strategies/reactive-rejection.ts`** —— 原语。负责 parse／mark／canHandle／一次性（one-shot）。

**`src/lib/request/strategies/server-tool-rejection-retry.ts`** —— 「模型不支持执行该服务端工具」臂。

```ts
export const SERVER_TOOL_REJECTION_TABLE: ReadonlyArray<{ pattern: RegExp; typePrefix: string }> = [
  { pattern: /the use of the web search tool is not supported/i, typePrefix: "web_search_" },
]
```

其文档原文（关键的两句）：

> server-tool stripping is now purely **reactive-learned** (the global `anthropic.server_tool_strip` config opt-in was **removed** with the web_search retirement 2026-07-13).

> on the first 400 we fixate the offending server tool type prefix in the negotiation cache (so future same-(endpoint, model) requests pre-emptively strip it on first prep) AND carry an authoritative `PrepareHints.excludeServerToolTypes` so THIS attempt's retry strips it deterministically — independent of the cache read.

设计上刻意**表驱动**：新观测到一种拒绝就加一行数据，不加分支。且**不写投机行**——没有实测拒绝消息的工具不进表，未建模的拒绝走 `canHandle=false` 落空，而不是静默剥离一个未知工具。

**`src/lib/request/strategies/web-search-not-found-retry.ts`** —— 「历史里有 `server_tool_use{web_search}` 但模型未配备该工具」臂，匹配 `Tool '[^']+' not found in provided tools`，学进 `serverToolDowngrade` 集合，然后在 **pre-sanitize 基线** 上重跑清洗链（喂 `currentPayload` 会双重应用整条重写链，这被标为 correctness 硬约束）。

**`src/lib/anthropic/feature-negotiation.ts:303`** —— 缓存本体，`markAnthropicServerToolUnsupported(modelId, toolType)` / `getUnsupportedServerToolTypes(modelId)`，按模型键控、带活跃期、异步持久化。

## 2. 我方缺陷定性

### 2.1 预判式能力门是反应式协商的劣化版

`src/app/pipeline/subscribers/hosted_web_search.py` 读 `models_support_web_search`，默认值是**我挑的七个模型**。判据来自「目录里 vendor 为 OpenAI 且广告 `/responses`」——而该模块自己的 docstring 就写着目录**回答不了**这个问题（无任何模型广告 web-search 能力位，两个已知可用的模型在每个已广告字段上与其余模型无法区分）。

于是这张清单是一个猜测，而清单外的模型会被**合成一个失败结果**。

**方向要害**：合成失败这套机制存在的理由，是防止「模型凭记忆作答被贴上搜索结果标签」这种伪造。但清单猜错时，它伪造的是另一个方向的东西——**一次本来会成功的搜索，被报告成失败**。同一套机制，两个方向，我只防了一头。

反应式协商没有这个问题：它只在上游**真的**拒绝之后才降级，之前一律照发。猜测被删除了，不是被改良了。

### 2.2 `annotations` 与 `num_requests` 零消费（两个项目都是）

我们 `src/` 里 `url_citation` / `annotations` 无任何消费者，`tool_usage.web_search.num_requests` 只出现在三处注释。`copilot-api-js` 同样：`annotations` 在 Responses→Anthropic 方向零处读取，`num_requests` 零命中；其仓库里四处 `url_citation` 全是手写 fixture，非 GHC 录制。

**这一条对两边都成立，所以它不是「我们落后」，是「这块没有任何人做过」。** 我们自己两份 cassette 的 `annotations` 都是 `[]`，但查询是「现在几点」——不足以下结论，仍需探针。

## 3. D6（原生块对）与参考实现的关系

**参考实现全都不产原生块对，三个都是文本。** 但它们的理由对我们不直接成立：

`copilot-api-js` 的 RFC 红线 R-NO-REVIVE 写明，不合成 `web_search_tool_result` 是因为该块缺 `encrypted_content` 时会被 **Anthropic 端点**拒（`exp/encrypted-content-400` 四种伪造形态全被拒 400）。

**那堵墙在 GHC 的 `/v1/messages` 上。** 按用户 2026-08-21 裁决 #1，我们的 Anthropic 腿不支持 web search，合成块永不回喂那条腿——这与规格 §5.2 已有的论证一致（「本规格的合成块不会被回喂给 Anthropic 上游」）。

所以：**D6 仍然成立且无参考可抄，它是本项目自己的裁决。** 参考项目在这一点上没有比我们更进一步，我上一轮说的「D6 未落地」仍然是欠账，但它与本文的缺陷是两件独立的事。

## 4. 两件事的关系

| | 欠账 | 性质 |
|---|---|---|
| A | 能力门是预判式清单，应改反应式协商 | **本文新发现**；参考实现有成熟方案可抄；会伪造「失败」 |
| B | D6 原生块对未实现，当前一行文本 | 已裁决未落地；无参考可抄；不伪造，只是信息贫乏 |

A 比 B 更急：A 会让一次本可成功的搜索变成假失败，B 只是把成功的搜索说得简陋。

## 5. 证据强度

- 「参考项目用反应式协商且移除了配置开关」——**足以据此实现**。三个文件互相印证，docstring 明写移除日期与原因，表驱动结构完整。
- 「VS Code 扩展 Responses 腿不支持」——**足以据此实现**。三份副本全搜，`web_search_call` 零命中，对照组 `image_generation_call` 有命中。
- 「上游对不支持搜索的模型在 Responses 腿返回什么错误消息」——**未知，无样本**。`copilot-api-js` 表里那条 `the use of the web search tool is not supported` 是 **Anthropic Messages 端点**的措辞；我们映射成 `{type:"web_search"}` 之后 Responses 端点说什么，没有任何观测。**这是实现反应式协商前必须先取得的一件事实**，否则表里没有可匹配的行。

---

## 6. 用户裁决与落地（2026-08-21）

### 6.1 裁决

> 「能力门采用版本清单，清单接受正则表达式」

**反应式协商未被采纳。** §1.2 与 §2.1 的分析仍然成立且保留，但它们不是本项目的选择。记录不采纳的理由：

1. **反应式协商需要一条可匹配的上游拒绝消息，而我们没有。** `copilot-api-js` 表里唯一那行 `the use of the web search tool is not supported` 是 **Anthropic Messages 端点**的措辞。我们映射成 builtin 之后 Responses 端点说什么，零观测（§5 已标注）。表里没有行的反应式机制什么也做不了。
2. **供应链的分野在名字里看不出来。** `gpt-5-mini` 的 vendor 是 Azure OpenAI，与 `gpt-5.N` 那条线不同源。`gpt` 主版本 ≥ 5 这种纯名字判据宽到会把它扫进来，而它从未被送上过上游。
3. **运维知道得比默认值多时必须说得出口。** 编进二进制的判据无法被告知；清单可以。

正则化把「清单」原有的**可运维**与「判据」的**自动覆盖新版本**两个优点合到一处，这是裁决选中的点。

### 6.2 已落地

- `5b8c56a` —— `models_support_web_search` 条目改为正则，`fullmatch` 匹配上游 `model.id`。默认值从七个精确 id 变为一条 `gpt-[5-9]\.\d+.*`，覆盖同样那七个并自动纳入后继版本。模式在启动时编译；不合法的模式带着**条目原文与键名**重新抛出，因为 `re` 只给字符偏移，跨多条目时说不清是哪一条。
- `2a95811` —— 上一轮那条回归测试的类型标注修复（Pyright）。
- 变异验证：`fullmatch` 改成 `search` 后，锚定那条测试以 `DID NOT RAISE WebSearchNotExecutable` 变红——正是缺陷的形状。恢复后全绿。
- 门禁：1560 passed / 2 skipped，Ruff 全过，Pyright 在我改动的文件上零错误（余下 29 个全在同伴未提交的 `stream_cap` 与 `sse.py` 中）。

### 6.3 未动，需要决定

- **`web_search` → `web_search_preview` 未改。** cassette 的 digest 覆盖整个请求体（`tests/int/recorded/cassettes.py:228`），改类型会让两份 web-search cassette 失配，必须用 `record_cassette.py` 重录，而重录需要凭据并发出真实上游调用。**重录本身就是那次探针**：接受则同时拿到新证据，400 则当场知道。等用户授权。
- **`docs/.human-controlled/config.example.yaml` 仍列四个精确 id。** 该文件由用户亲笔，未改动。四条在 `fullmatch` 下各自只匹配自己，行为不变；是否改写成家族模式由用户决定。

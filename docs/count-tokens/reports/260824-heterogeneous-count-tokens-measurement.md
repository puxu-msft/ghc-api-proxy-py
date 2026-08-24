# 异构模型的 count_tokens：链路是通的，数字是错的

日期：2026-08-24
作者：主会话（Claude Opus 5）
仓库 HEAD：`3533386`
对象：`POST /v1/messages/count_tokens` 上，路由目标为 OpenAI Responses 的模型（gpt / gemini / grok 等，下称「异构模型」）。
性质：定量测量报告。所有数字均为实测，脚本与原始输出见文末「复现」。

## 结论摘要

分两层回答「异构模型是否能正确处理 count_tokens 请求」：

- **机制层：能，且是按设计走的。** 请求不被拒绝、不 502。`handle_count_tokens` 在判定 `route.target_format` 不是 Anthropic Messages 后主动撤走上游计数器（`driver.py:311`），链路退到本地估算，响应为 `{"input_tokens": N, "estimated": true}`，日志写 `provider(no-counter,local)`。路由、翻译、能力门、错误分类都与真实请求走同一条 `shape_request`，端到端实测 200。**判断权重：足以据以行动**（端到端实跑，见下）。
- **数值层：不能。系统性高估，中位 1.76 倍，p95 2.87 倍，最大 3.16 倍。** 单一原因：翻译产物里的 `reasoning` item 带 `encrypted_content`，估算器把整段密文按 tiktoken 计入，而上游实际上几乎不为它计费。把密文那部分从估算里扣掉，估算/真实 = **0.993（中位）**，p05–p95 落在 0.939–1.011。**判断权重：足以据以行动**（314 个真实操作，含 7 个零 reasoning 的对照组）。

**这不是「估算天然不准」，而是一处可定位、可修的偏差。** 估算器的其余部分实测精度在 1% 以内。

## 一、机制层：端到端实跑

用 `tests/int/test_pipeline_app.py` 的 `make_client` 起真实应用，发四个请求（模型 × 是否带 reasoning carrier）：

| model | 带 carrier | 状态码 | 响应体 | 日志 |
|---|---|---|---|---|
| `gpt-model` | 是 | 200 | `{"input_tokens": 4992, "estimated": true}` | `provider(no-counter,local)` |
| `gpt-model` | 否 | 200 | `{"input_tokens": 32, "estimated": true}` | `provider(no-counter,local)` |
| `claude-model` | 是 | 200 | `{"input_tokens": 99}` | `provider(ghc)` |
| `claude-model` | 否 | 200 | `{"input_tokens": 99}` | `provider(ghc)` |

同一段对话，只因为多了一个 reasoning carrier，异构模型报出的数字从 32 变成 4992（**156 倍**）。同构模型问上游，不受影响。

carrier 用 `encode_reasoning_carrier` 构造，`encrypted_content` 取 7164 字符的真实形态 base64（长度取自历史库实测中位数，见下）。翻译产物中该 item 的整段 JSON 为 7285 字符 / 4965 tokens，estimator 全额计入。

## 二、数值层：与上游自己的计数比对

### 地面真值从哪来

既有服务 `copilot-api-js` 的历史库 `~/.local/share/copilot-api/history-v3-20260818-044224.db` 同时存着两样东西：

- `wire-request` 阶段的 payload，即它**实际发往 `/responses` 的那个 body**（manifest 的 `record.arena.payloads` 里 `origin.stage == "wire-request"`，正文经 `payloadSequences` + `v3_sequence_nodes` 重组）；
- 该次操作的 `summary_json.usage`，即**上游为这同一个 body 报回的 token 数**。

真实输入 token 取 `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`。这个求和方式不是我选的：Claude Code 自己的 count_tokens 兜底路径就是这么加的（`~/.claude/refs/claude-code-2.1.241/app.pretty.js:366958`，`return h + g + y`）。

**这条路径此前被认为不存在。** `tests/int/recorded/from_history.py:212` 写着「history records no request body」——那句话对帧成立，对 payload 不成立；请求体是以骨架 + 序列节点的形式存着的，可以重组。重组后的 body 键为 `input / instructions / max_output_tokens / model / reasoning / stream / tools / user`，`input` 长度与 manifest 声明的 `length` 一致，无空洞。

### 结果（314 个操作，全部解码成功，0 个静默跳过）

| 指标 | 中位 | p05 | p95 | max |
|---|---|---|---|---|
| `估算 / 真实` | **1.760** | 1.155 | 2.872 | 3.157 |
| `(估算 − 密文 tokens) / 真实` | **0.993** | 0.939 | 1.011 | — |

- 绝对高估量：中位 **96,038 tokens**，最大 **360,206 tokens**。
- 对照组：7 个不含任何 reasoning item 的操作，`估算/真实` 中位 **1.011**。
- reasoning item ≥ 20 个的 160 个操作，`估算/真实` 中位 **2.154**。

抽样自最近 60 个操作的逐条明细显示比值随 reasoning item 数量单调上升（0 个 → 1.01，1 个 → 1.11，22 个 → 1.59，46 个 → 2.40），且密文占估算总量的 0%–60%。

### 这说明什么

上游 **不按密文的 tiktoken 数计费**。扣掉密文后误差落到 1% 以内，且零 reasoning 的对照组本来就准，两者互为佐证。机制上说得通：`encrypted_content` 是上游自己签发的服务端状态载体，它认得，不需要按字面重新分词。

`estimators.py:72-77` 的 docstring 说「上游数的是到达的东西」「零是可测量地错的」。前半句作为一般原则没问题，但**用在 `encrypted_content` 上是错的**——现在测出来了：对这一项，零比全额近得多。同一段 docstring 承认当时无从测量，这份报告补上了那次测量。

### 校准补不回来

`.dev/docs/count-tokens/reports/260820-review-responses-token-counting.md` 的 MAJOR-1 建议把差额交给 calibration 学回来。**实测表明标量校准原理上补不了这个偏差**：`calibrate` 是对估算值乘一个 per-(protocol, model) 的标量，而这里的比值在**同一个模型、同一个会话内**就从 1.16 走到 2.87——误差正比于 reasoning item 的条数，不正比于估算值。任何标量都会同时把两端修坏。

反过来，密文扣除之后的比值 0.939–1.011 是标量能处理的范围（因子约 1.0）。

顺带确认该报告指出的另一条仍然成立：`responses` 协议的校准**至今学不到任何东西**。`calibration.learn` 全仓只有两个调用点（`driver.py:339` 与 `tokenization/service.py:54,74`），前者在 `result.provider == "ghc"` 分支内，而异构路由永远拿不到 `ghc`。真实请求完成后 usage 里的 `input_tokens` 是现成的地面真值，没有被喂给校准。

## 三、影响面：客户端拿这个数干什么

查 Claude Code 2.1.241 抽出的源码，`/v1/messages/count_tokens` 的调用链是 `upr`（`app.pretty.js:366938`）→ `Urn`（`:366310`，countTokensWithFallback），消费者有四类：

- `KGt`（`:366326`）系统提示词与工具、`:366357` memory 文件、`Zzw`（`:366421`）自定义 agent 描述——这些 body **不含 assistant 消息**，因而不含 reasoning carrier，**不受影响**。
- `r4w`（`:366460`）**整段对话**的 `totalTokens`，喂给 `/context` 的显示。assistant 消息的 content 原样传入，thinking 块在内，**受影响**。

**自动压缩不走这条路。** 压缩阈值读的是 `eP`（`:367083`）：最后一条 assistant 消息 `usage` 里的真实用量，加上其后消息的本地估算。所以本条偏差**不会**触发提前压缩——我原本以为会，查了才发现不是。

结论：影响落在 `/context` 显示的对话总量上，异构模型下会虚报到近两倍。这仍然是用户据以判断「要不要 /compact」的数字，但它不改变客户端的自动行为。**判断权重：足以据以行动**（读的是抽出的源码，调用链逐跳核过）。

## 三点五、第二处差异：异构路由不校验 Messages body（复核自异源评审）

`gpt-opus` 的独立评审报了这一条（`.dev/docs/tmp/260824-count-tokens-heterogeneous-review-gpt.md` 第 2.2 节）。我用同一个 `make_client` 独立复现，并扩到六种畸形形态：

| 畸形 body | `claude-model`（同构） | `gpt-model`（异构） |
|---|---|---|
| `messages[0]` 缺 `content` | 400 `CountTokensRequestError` | 200 `{"input_tokens":1,"estimated":true}` |
| `messages` 是字符串 | 400 | 200 `input_tokens=1` |
| 无 `messages` 键 | 400 | 200 `input_tokens=1` |
| `content` 类型错误（数字） | 400 | 200 `input_tokens=1` |
| `role` 非法（`"wizard"`） | 200（上游 99） | 200（7） |
| 未知 content block 类型 | 200（上游 99） | 200 `input_tokens=1` |

原因清楚：`_countable` 只在 Anthropic 分支被调用（`driver.py:274`），异构分支直接交给宽松的 Anthropic reader，它把非 list 的 `messages` 读成空列表、丢掉读不懂的条目（`anthropic_messages.py:121-133`），翻译出空 `input`，`estimate_responses_input` 的 `max(total, 1)` 把「零」渲染成 `1`。

**但要收窄它的含义。** 我另发了一组同样畸形的 body 到真实的 `/v1/messages`（异构模型、mock 上游）：三种都是 **200**，且实际发往上游的 body 是 `input: []`。所以计数端点没有说谎——它如实报告了这条链路真的会发出去的那个空请求，这正是「量真正会发出去的 body」这条设计原则的结果。

因此这不是计数端点的缺陷，而是**翻译发送链路的缺陷穿透到了计数端点**：异构路由上，一个畸形的 Messages body 会被静默折成空对话发给上游，客户端收到一个 200 和一段无来由的回复。`input_tokens: 1` 只是这件事在计数端点上的投影。同构侧之所以 400，是 `_countable` 为了估算而顺带做的校验，并非有意的协议门——它对非法 `role` 与未知 block 类型同样放行。

修的方向应当在发送链路（异构路由是否也该按 `MessagesRequest` 校验入站 body），而不是给计数端点单独打补丁。**判断权重：足以据以行动**（六种形态实跑，两条路径对照）。

## 四、建议（不构成门禁，供裁决）

1. **`_responses_item_text` 对 `reasoning` item 排除 `encrypted_content` 字段，其余照计。** 这是本报告唯一直接支持的改动，预期把中位误差从 +76% 降到 −0.7%。改完应当有一条测试把带密文 reasoning item 的期望值钉住——现状是这个函数的七个分支里只有 `message` 被走到过（该结论出自 260820 报告的变异实验，未复核）。
2. **给 responses 协议接上校准的学习来源**：真实请求完成后用 usage 的 `input_tokens + cache_*` 调 `learn(protocol, model, estimate, real)`。这条独立于建议 1，且**只有在建议 1 之后才有意义**——在此之前它要学的是一个标量学不动的东西。
3. `driver.py:339` 的 `learn` 第一个参数是 `protocol` 变量（已按 260820 的 MINOR-1 修好），无须再动。
4. 建议 2 的地面真值**已经在记录了**，不需要新采集：异源评审查明 buffered 与 streaming 两条回复路径都解析并保留了上游 `usage`（`protocols/responses_anthropic.py:225-291`、`delivery/formats/openai_responses.py:535-543,588-598`），并经 trace 落进每日 JSONL（`observability/request_log_file.py:31-49`）。缺的只是从那里到 `learn()` 的一根接线。
5. 异构路由是否也该按 `MessagesRequest` 校验入站 body（见第三点五节）——这是发送链路的裁决，不是计数端点的。

## 同伴报告的处置

本报告合并了两份并行 agent 的产出，处置如下：

- `.dev/docs/tmp/260824-count-tokens-heterogeneous-review-gpt.md`（异源评审，gpt-opus）
  - **采纳并独立复核**：Major「异构路由绕过 Messages body 校验」——我扩到六种形态复现，并补了 `/v1/messages` 的对照，**收窄了它的归属**（见第三点五节：缺陷在发送链路，不在计数端点）。
  - **采纳**：`estimated: true` 不会破坏 Claude Code 2.1.241（它只读取并类型检查 `input_tokens`）；默认三个 `attempt.prepare` 订阅者在计数路径上无副作用、不占配额；翻译确实先于估算；真实 usage 已被记录但未喂给校准。
  - **采纳但改写结论**：它把「Responses 校准学不到」列为 Moderate 并建议接上学习来源。接线该补，但**标量校准补不了本报告测出的偏差**（比值在同一会话内 1.16→2.87），所以顺序必须是先修估算器、再接校准。
- `.dev/docs/tmp/260824-count-tokens-prior-art-survey.md`（既有裁决与测试梳理）
  - **采纳**：人控文档对异构 count_tokens 无任何规定，现行行为是代理会话自裁、用户未追认；`.dev/docs/count-tokens/` 只有报告、无活文档；异构路径的唯一成文规格落在被整体判过期的 `archived-2604-rewrite/tokenization.md`；`AnthropicTokenCountingService` 是孤儿模块而 `test_token_counting.py` 保护的正是这条不在服役的路径。
  - **不采纳其结论的一处**：它判断「真正的定量比对只有一条诚实路子——在 `handle()` 里就地采样」。这个判断对 cassette 成立，但不成立于整体：既有服务的历史库同时存着 `wire-request` body 与该次的 `usage`，本报告的 314 个样本就是这么来的。它的排除是在 cassette 范围内做的，被我扩大到了历史库之外。

## 五、限制与未证之处

- **314 个样本来自单一客户端会话、单一模型（gpt-5.6-terra）、单一天。** 其他模型与时段的历史库把 manifest 外置到 `content/chains/` 与 `content/cas/`，本次未解那层格式，因此**跨模型的推广是推断而非测量**。支撑推广的是机制（偏差正比于密文体量）与零 reasoning 对照组，不是更多样本。
- 样本记录的是**既有服务**的翻译产物，不是本项目翻译器的输出。两者的 reasoning item 都携带完整 `encrypted_content`（本项目的形态已由第一节的端到端探针确认），但其余字段可能有细微差别。
- 「上游不为 `encrypted_content` 计费」是从总量差反推的，**没有**直接的上游文档或逐项计费凭证。若上游改变这一策略，本结论随之失效。
- 未测：gemini / grok 等其他异构模型是否也产出 reasoning item；非 Claude Code 客户端如何使用 count_tokens。

## 复现

脚本在 `$CLAUDE_JOB_DIR/tmp/`（会话级，不持久）：`hist_bodies.py`（历史库只读重组 wire-request）、`measure3.py`（全量比对）、`e2e_probe.py`（端到端）、`probe_estimator.py`（单 carrier 量级）。历史库一律以 `file:...?mode=ro` 打开，未复制、未写入。

```
PYTHONPATH=src uv run python measure3.py
PYTHONPATH=src:tests/int uv run python e2e_probe.py
```

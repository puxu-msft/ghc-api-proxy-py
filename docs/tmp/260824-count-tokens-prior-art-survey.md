# count_tokens × 异构模型：既有裁决、规格、报告与测试的清点

- 调查日期：2026-08-24
- 调查者：leaf executor，只读调查（除本报告外未改动仓库任何文件；未运行 `ruff format`）
- 基线：主仓库 HEAD `3533386`（2026-08-23 19:06:05 +0000），`.dev` HEAD `b7dfc45`
- 工作树脏文件：`docs/.human-controlled/config.example.yaml`、`docs/.human-controlled/message-translation.md` 各有一段未提交新增（分别是 `intercept_auto_mode_classifier` 与「直连/翻译路径的处理原则」两段）。**两处均不触及 count_tokens**，本报告引用的 `config.example.yaml:66-72` 位于第 555 行之前，行号未受影响。
- 术语约定（下文一律按此）：
  - **同构路径**：入站 anthropic-messages → 目标格式仍是 `ANTHROPIC_MESSAGES`，上游 `POST /v1/messages/count_tokens` 可用。
  - **异构路径**：入站 anthropic-messages → 目标格式 `OPENAI_RESPONSES`，需翻译，上游计数器被**主动撤走**（不是调用失败）。
  - **不可达路径**：目标格式没有 outbound translator（`/embeddings`、`/chat/completions`），请求根本发不出去。

---

## 0. 一句话结论

异构路径的行为在 2026-08-20 被**完整裁决并实现**了：量翻译后的 Responses body、用 `estimate_responses_input`、calibration 键跟随目标协议、日志行用 `provider(no-counter,local)` 与失败区分开。**唯一公开挂账的缺口是「OpenAI 家族的 calibration 没有学习来源」**——`learn("openai-responses", ...)` 全仓零调用点，`calibrate` 在该协议上恒为恒等函数。这一点被文档、代码 docstring、评审报告三处一致记录为「尚未做」，不是遗漏而是已知待办。

---

## 1. `docs/.human-controlled/`（用户亲笔，最高权威）

### 1.1 直接规定 count_tokens 的原文

| 位置 | 原文 | 读法 |
|---|---|---|
| `docs/.human-controlled/api.md:5` | `- Anthropic：POST /v1/messages、POST /v1/messages/count_tokens` | 端点存在，是 Anthropic 协议族的端点 |
| `docs/.human-controlled/api.md:10` | `- Gemini：POST /v1beta/models/{model}:{generateContent\|streamGenerateContent\|countTokens}` | Gemini 侧也有计数端点（当前代码 `implemented=False`，见 §4.5） |
| `docs/.human-controlled/api.md:21` | `- ~~Tokenization：/api/tokenization/calibration、/api/tokenization/limits~~ 暂不支持` | **管理端点被用户划掉**。代码已一致：`rg 'api/tokenization' src/ tests/` 零命中 |
| `docs/.human-controlled/ghc-api.md:25` | `\| POST /v1/messages POST /v1/messages/count_tokens \| direct_driver.anthropic_messages \| Anthropic 模型都具备该端点 \|` | **这是异构问题的根**：用户明写该端点属于「Anthropic 模型」这一栏。非 Anthropic 模型不在此表内即没有上游计数器 |
| `docs/.human-controlled/message-format-reshape.md:3` | `GHC API 虽然声称支持 anthropic /messages /messages/count_tokens 和 openai /responses 等，但有其怪癖，我们需要按需消毒。` | 消毒同时覆盖两个端点 |
| `docs/.human-controlled/message-format-reshape.md:7` | `这部分仅在 /messages 或 /messages/count_tokens 端点入口生效。` | **整形与 count 路径共享**是用户明写的要求，不是实现者的发挥 |
| `docs/.human-controlled/config.example.yaml:66-72` | 见下方代码块 | 配置契约：provider 顺序 + 重试次数 |

```yaml
inbound:
  # GHC API 提供分词计数器 `POST /v1/messages/count_tokens`，这里控制是否使用它。
  # The GHC API provides a token counter `POST /v1/messages/count_tokens`, this controls whether to use it.
  anthropic_count_tokens:
    # local = 本地 calibrated tiktoken 估算。
    # local = local calibrated tiktoken estimate.
    providers: [ghc, local]
    max_retries: 2
```

代码一致：`src/app/config/schema.py:74-80`，`CountTokensConfig.providers` 默认 `["ghc","local"]`，`max_retries` 默认 2、`ge=0`。

### 1.2 与异构路由相关（未直接点名 count_tokens，但决定它的前提）

- `docs/.human-controlled/request-pipeline.md:11` —— 用户给出的异构路由范例原文：

  > 比如，从 `POST /v1/messages` 输入的 anthropic-messages 格式的模型请求。如果要求访问 `gpt-5.6-terra` 模型，且无模型映射配置，根据上游提供方的信息，该走 `gpt-5.6-terra@openai-responses`；如果要求访问 `claude-sonnet-5` 但显式配置了模型映射关系 `claude-sonnet-5 -> gpt-5.6-terra@openai-responses`。那么需要在 anthropic-messages 格式与 openai-responses 格式间做翻译——发给上游的是 openai-responses 格式，做一次翻译；返回给客户端的是 anthropic-messages 格式，再做一次翻译。

  这条是「异构模型是一等公民、请求确实发得出去」的权威依据，也是 2026-08-20 推翻旧 400 行为时引的那条理由的上游出处。

- `docs/.human-controlled/message-format-reshape.md:11` —— `一般地，**直连路径上**，客户端请求头值得原样转发给上游……翻译路径不遵循这一点，翻译路径采用白名单机制。`（异构路径与直连路径分别定纪律的先例）
- `docs/.human-controlled/message-translation.md:5,9` —— 翻译器注册与「总是建立消息格式与内部 IR 的映射关系」的原则。

### 1.3 检索为空的项（显式记「无」）

- **`docs/.human-controlled/` 中没有任何一句直接规定「异构模型上 count_tokens 该返回什么」**。既没有说「该 400」，也没有说「该本地估算」。整份人控文档里 `count_tokens` 共 6 处命中，全部列于 §1.1。
- **没有任何一句规定 token 估算的精度、误差上限或校准目标。**
- **没有任何一句提到 `estimate_responses_input`、`openai-responses` 这个 calibration 协议键，或异构路径的校准。**
- `docs/.human-controlled/` 中 `tokeniz` / `calibrat` / `估算` 的全部命中只有 `lifecycle.md:3`（说 generation id 解析被 `tokenization` 快照模块共用，宜置于 `core/`），与本主题无关。

**结论（权重：足以据以行动）**：异构 count_tokens 的行为是**由代理会话裁决的**，用户未亲笔追认。若主会话要改动这条行为，不存在需要绕开的人控文档条款；反过来，也不存在人控文档为现行行为背书。

---

## 2. `.dev/docs/` 下的相关文档

`.dev` 是独立仓库、只在主工作树根存在，已确认（`.dev/.git` 存在）。

### 2.1 专题目录 `.dev/docs/count-tokens/`

该目录**只有 `reports/`，没有 `README.md` / `spec.md` / `status.md` / `deferred.md`** —— 即这个专题从未沉淀出活文档。三份报告：

#### (a) `.dev/docs/count-tokens/reports/260816-count-tokens-review.md`（2026-08-16）

评审对象：提交 `17b84ee` 的 provider-chain 接线。**同构路径为主**，异构只作为一条 major 出现。

- 首轮 verdict：blocker=1（新链路无生产调用者，CLI 仍走旧 `routes/anthropic.py`）；复评（HEAD `59c9e45`）verdict：0 blocker，可定稿。
- 与异构直接相关的一条（**已被 2026-08-20 裁决整体作废**）：报告 `:17-21` 的 major 主张「`gpt-model` 只宣称 `/responses`，`provider.count_tokens()` 抛 `EndpointNotSupported`，走到 `local` 是错的，应当 400」。复评 `:64` 记录该修复已落地（`ProviderError` 在通用捕获前重抛）。
- **作废说明**：这条「异构该 400」的裁决在 2026-08-20 被用户明确推翻两次（见 (c) 与 §2.2）。报告本身作为时点记录仍准确，但其结论**不得再引用为当前契约**。
- 仍然成立的部分：C3 学习回灌只在 `result.provider == "ghc"` 时调用；C4 `providers: [ghc]` + `max_retries=2` 连续失败 = 三次请求后 503；C5 `max_tokens` 补默认值不得泄漏到上游 payload。这三条今天的代码与测试仍然照此实现。

#### (b) `.dev/docs/count-tokens/reports/260820-review-count-tokens-shared-pipeline.md`（2026-08-20）

评审对象：`shape_request` 抽取 + `upstream_counts` 判据。VERDICT: needs-fix，blocker=0 / major=2 / minor=4。**这是「三分法」的来源报告**。

- **M1（`:40-57`）判据过宽**：`upstream_counts = route.target_format is WireFormat.ANTHROPIC_MESSAGES` 把「上游没有计数器」和「这个请求根本发不出去」合并了。实测 `embed-model`：`/v1/messages` 返回 `400 TranslatorNotFound`，而 `/v1/messages/count_tokens` 返回 `200 {"input_tokens":6,"estimated":true}`。建议拆成两问。
  **处置状态：已采纳并落地。** 今天 `handle_count_tokens` 在选计数器**之前**先做 `translate()`（`src/app/pipeline/driver.py:251-258`），不可达路径在那里就抛 `TranslatorNotFound`；测试 `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:301` 钉住了它。
- **M2（`:59-76`）** `providers: ["ghc"]` 下 400 变 503 且错误串诬告配置；`count_tokens_upstream_skipped` 写了没人读。
  **处置状态：部分采纳。** `upstream_absent_reason` 机制已落地（`src/app/pipeline/count_tokens.py:52,56`、`driver.py:316`），字面串从 `ghc:unconfigured` 改为 `ghc:no-counter-for-openai-responses`；`count_tokens_reason` 也已有读者（`src/app/server/routes/inference.py:223`）。但 `count_tokens_attempts` 的细节（超时/429/500、重试次数）**至今仍无消费者**，见 §2.3 的 `tui/deferred.md:74`。
- 已核实为正确、不必再查的部分（`:16-34`）：`shape_request` 对 `handle()` 严格等价；count 路径上 `payload["model"]` 赋值顺序无影响；`mute-model` 仍由 `decide_route` 400；`ProviderError` 在此调用点整体不可达；两条变异均有分辨力。
- `:115` 一条仍然有效的提醒：计数 body 现在会经过 `destack_content` 的 `assistant_message_layout` 变形，**若之后 calibration 出现系统性偏移，这里是第一个该查的地方**。

#### (c) `.dev/docs/count-tokens/reports/260820-review-responses-token-counting.md`（2026-08-20）

评审对象：`estimate_responses_input` 与翻译路径计数。blocker=0 / major=2 / minor=7。**这是主会话最该完整读的一份**，因为它是唯一一份对异构估算器做过定量测量的报告。

- **MAJOR-1（`:29-69`）reasoning item 静默计 0，而为它开脱的补偿机制不存在。** 实测数据（来自 `~/.local/share/copilot-api/history-v3-20260815-183721.db`，244 条 `sequence-item`，157 个 `encrypted_content` 值）：

  | 指标 | min | median | max |
  |---|---|---|---|
  | 字符数 | 5020 | 7164 | 11664 |
  | o200k token 数（密文本身） | 3454 | 4901 | 7967 |

  实跑翻译器的分项：7.6 KB 的 body 报 30 tokens（`[1] type=reasoning wire_json_chars=7286 counted_chars=0`）。
  **处置状态：已采纳并修复。** 今天 `_responses_item_text` 的规矩是「每个 item 都计入，没有例外」（`src/app/tokenization/estimators.py:69-77,110`），`reasoning` 落到整段 JSON 兜底。
- **MAJOR-2（`:71-88`）估算器零测试钉住**，用被测函数自己当 oracle；三种独立变异全绿。
  **处置状态：已采纳。** `tests/unit/tokenization/test_responses_estimator.py` 就是为此而写，8 条增量断言测试。
- **仍然成立、且是当前唯一挂账缺口的部分（`:56,68,160`）**：全仓 `learn(` 调用点里没有任何一个传 `"openai-responses"`；`calibration.py` 的 `_models.get(("openai-responses", model))` 恒为 `None`，`factor_at` 恒返回 `1.0`，`calibrate` 恒为恒等函数。建议 1 原文：

  > 在 `handle()` 发出请求前算一次 `estimate_responses_input(context.payload)`，用 Responses 回复的 `usage.input_tokens`（含 cached）调 `learn("openai-responses", route.model_id, estimate, real)`。

  **我于 2026-08-24 独立复核：该事实今天仍然成立。** `rg '\.learn\(' src/` 只有三个调用点：`tokenization/service.py:54,74`（两处硬编码 `"anthropic"`，且该服务已成孤儿，见 §4.4）与 `pipeline/driver.py:339`（`calibration.learn(protocol, ...)`，但只在 `result.provider == "ghc"` 分支内，而 `ghc` 只在同构路径可达）。
- **MINOR-1（`:94-98`）** `learn` 的协议键写死 `"anthropic"` —— **已采纳**，今天是 `calibration.learn(protocol, ...)`（`driver.py:339`）。
- **MINOR-2（`:100-108`）** else 分支覆盖所有非 Anthropic 目标而估算器只认 Responses —— **已采纳**，今天显式 `raise CountTokensRequestError`（`driver.py:277-281`）。
- **MINOR-3（`:110-112`）** web search 的 INFO 日志在启用 web search 的客户端上翻倍（count 路径现在也翻译）。**未见处置记录，仍可能成立。**
- **MINOR-4（`:114-118`）** count 端点新增一类 400（带 `allowed_domains`/`blocked_domains` 的 web search 声明在 counting 时抛 `TranslationRefused`），文档与测试都没提。**未见处置记录。**
- **MINOR-5（`:120-125`）** `function_call` / `function_call_output` 不计 `call_id`；`message` 的 `content` 为字符串时不拼 `role`。**前者已修**（`estimators.py:100,106` 现在都算 `call_id`）；**后者未修**（`estimators.py:85-86` 仍在 `parts.append(role)` 之后，实际上已是对的——`role` 在 `:83-84` 先入 parts，两分支现已一致，此条已被后续改写自然消解）。
- **MINOR-6（`:127-134`）** calibration 键兼容性：`snapshot()` 用 `f"{protocol}:{model}"`，`from_snapshot()` 读条目内字段而非 key，**不污染既有 `anthropic:*` 数据**。已核对无问题，记录以免重查。
- **Q1（`:150-151`）** 穷举了 Anthropic→Responses 出口的全部 item 形态：`message`、`function_call`、`function_call_output`、`reasoning`，外加 **image 是顶层 item**（`_item_from_block` 对 IMAGE 返回原始 Anthropic 块，不在 `{"input_text","output_text","input_image"}` 白名单里，于是独立成项，被整段 JSON 兜底接住，方向偏大，与 Anthropic 侧等价）。`server_tool_use` / `web_search_tool_result` 到不了出口。这份枚举今天仍可复用。

### 2.2 `.dev/docs/archived-2604-rewrite/tokenization.md` —— **注意，这是一个陷阱**

**这份文件同时是「异构 count_tokens 的唯一成文规格」和「用户裁定整体过期的目录里的一份文件」。**

- 路径：`.dev/docs/archived-2604-rewrite/tokenization.md`，`:13-44` 是「与请求管道共享的部分（2026-08-20）」一节。
- 事实链（我用 git 核过，不是推断）：
  - 主仓库历史里 `docs/2604-rewrite/tokenization.md` 由实现提交 `a334fab`「fix: count what would be sent, and by an instrument that exists」与 `c2eae5f`「feat: count the body the translated route would actually send」写入这一节；
  - 随后 `d88c07a`「docs: retire 2604-rewrite from the repository」把整个目录移出主仓库；
  - `.dev` 侧 `3d666ac`「docs: take in 2604-rewrite as archived reference」逐字节收下，**该节在收下时就已存在**（我 `git show 3d666ac:...` 验证过），此后未再修改。
- `.dev/docs/archived-2604-rewrite/README.md` 的裁决原文：

  > **用户裁定（2026-08-20）：这里整体过期。** 它是早期由 peer 会话编写的 **`copilot-api-js` 学习笔记**……**不要把这里的任何一句当作裁决、契约或当前行为。**

- **我的判断（权重：足以据以行动，但需主会话确认）**：这条裁决的**理由**（「早期 peer 写的 copilot-api-js 学习笔记」）对 `:13-44` 这一节**不成立**——它是本项目自己的实现同步文档，写于裁决当天、由实现提交带入。裁决的**字面**却覆盖了它。代码自己已经踩到这个矛盾并给出了处理方式，`src/app/pipeline/driver.py:270` 的注释原文：

  > The idea came from `.dev/docs/archived-2604-rewrite/tokenization.md`, which the user ruled obsolete on 2026-08-20 — it is kept on the reasoning, not on that document's authority.

  即：**代码明确声明不靠这份文档的权威性，只靠它的论证。** 主会话若要引用 `:13-44`，建议同样以「论证」而非「裁决」的身份引用，或将该节内容提取到 `.dev/docs/count-tokens/` 下建立真正的活文档。

- 该节的**规格要点**（原文摘要，`:22-44`）：

  | 目标格式 | 计数器 | calibration 协议键 |
  |---|---|---|
  | Anthropic Messages | 上游 `POST /v1/messages/count_tokens` 优先，失败退本地 `estimate_anthropic_input` | `anthropic` |
  | OpenAI Responses | 本地 `estimate_responses_input`（上游无预检端点） | `openai-responses` |

  - `:29` **上游有没有计数器由 route 判定，不靠调用去发现**；跳过原因写作 `ghc:no-counter-for-openai-responses`，**不写成 `ghc:unconfigured`**。
  - `:30` **calibration 键跟随目标协议**，两族因子混训会让彼此用对方的误差校正自己。
  - `:31` **发不出去的请求仍然 400**。原文点名今天落在这一类的模型：只广告 `/embeddings` 的，以及只广告 `/chat/completions` 的三个（`gemini-3.1-pro-preview`、`gemini-3.5-flash`、`trajectory-compaction`）。
  - `:32` 没有估算器的目标格式**显式报错**，而不是拿 Responses 估算器读一个没有 `input` 的 body 返回 1。
  - `:34` **两次推翻的记录**（关键裁决原文）：

    > 此前翻译路径上 count endpoint 返回 **400 `EndpointNotSupported`**……**该前提不成立**——同一个模型、同一个入站协议下 `POST /v1/messages` 会经翻译成功返回 200……模型是够得着的，够不着的是计数器。随后的第一版改法**只**退回到 Anthropic body 的本地估算，用户 2026-08-20 判定**不够**：翻译路径要**正确支持**，即量翻译后的 body。现行行为即此。

  - `:36` **`estimate_responses_input` 的规矩只有一条：每个 item 都计入，没有例外。**
  - `:44` **尚未做**：

    > OpenAI 家族的 calibration 没有学习来源——上游只在响应完成时报 usage，而 count 发生在之前。把 Responses 响应的 usage 回喂给 `learn("openai-responses", ...)` 是自然的下一步，本次未做。

  - `:58-83` 同构侧的 size-aware calibration 规格（bucket 划分、factor clamp `[0.5,3.0]`、log-linear 插值、权重上限 2000）与学习来源清单。这部分**代码仍在服役**（`src/app/tokenization/calibration.py`），但学习来源清单里的四项**只有一项还接着线**（count endpoint 精确响应，经 `driver.py:339`）——其余三项（非流式 usage、流式 `message_start/message_delta` usage、prompt-limit 400）今天只存在于孤儿 `tokenization/service.py` 里，见 §4.4。**这是一个我在检索中发现、但未见任何文档记录的落差，主会话应单独裁决。**

### 2.3 其它 `.dev` 文档中相关且仍然有效的条目

| 路径 | 日期 | 要点 |
|---|---|---|
| `.dev/docs/tui/spec.md`「一次计数请求怎么读」 | 2026-08-20 | 计数行的**当前权威规格**（`archive-count-tokens-line/README.md:9` 明写「当前行为以 `../spec.md` 为准」） |
| `.dev/docs/tui/archive-count-tokens-line/README.md` | 2026-08-20 | 为什么这样定 + 路上踩了什么。核心可复用判据（`:20`）：**给一个「读不出来」的问题补上字段之后，立刻再问一遍这个新字段本身——它的每个取值是否只对应一种结局？** 第二节给出五种 `provider(...)` 取值的完整语义表；第四节记「不着色」是用户 2026-08-20 的明确裁决，理由是「一条翻译路由天天答 `provider(no-counter,local)` 是正常配置而非事故」；第五节记录了三条**被否决**的方案及理由 |
| `.dev/docs/tui/deferred.md:72-76` | — | 三分法「已解决的那半」与「仍然没有读者的那半」。**开放项**：`ghc-failed` 说不出是超时、429 还是 500，也说不出重试了几次；这些躺在 `context.extras["count_tokens_attempts"]`（形如 `ghc:0:APIStatusError`）里**至今没有任何消费者**。建议做法：带进 `_Trace` → `RequestLine` → JSONL，**不上控制台行** |
| `.dev/docs/server-layout/deferred.md:19-22` | 2026-08-23 | `estimate_gemini_input` 与两个私有辅助函数已从 `src/app/tokenization/estimators.py` 切出归档到 `src/.archived/`；`tokenization/__init__.py` 不再导出它。**Anthropic 与 Responses 估算器还在活树** |
| `.dev/docs/server-layout/deferred.md:30` | 2026-08-23 | **开放项**：`countTokens` 旧链走本地估算（`estimate_gemini_input`，不打上游），与新链 `/v1/messages/count_tokens` 的 `provider(local)` 那一档是同一类事。当前 501 是对的，但「它该走本地估算而不是上游」这条知识**只存在于归档代码里** |
| `.dev/docs/anthropic-responses-bridge/spec.md`、`acceptance.md`、`hosted-web-search-spec.md` | 2026-08-06~08 | 命中 `count_tokens` 但均为端点列举或旁证，**未对异构计数做任何裁决**。`hosted-web-search-spec.md` §3.4 是 MINOR-4 里 `TranslationRefused` 的出处 |
| `.dev/docs/archived-2604-rewrite/hooks-tokenization-spec.md`、`plan/HOOKS_TOKENIZATION_*.md` | 2026-04 | 早期 copilot-api-js 学习笔记，**在用户 2026-08-20 的整体过期裁决内、且理由确实成立**（写于实现之前，非本项目设计规范）。不建议引用 |
| `.dev/docs/tmp/260822-ghc-api-conformance-*.md` | 2026-08-22 | 命中 `count_tokens` 但属 GHC API 一致性巡检，未涉异构计数裁决 |

### 2.4 检索为空的项（显式记「无」）

- **`.dev/docs/count-tokens/` 下没有 `spec.md`、`status.md`、`decision.md`、`deferred.md`、`README.md`** —— 该专题只有三份报告，**从未沉淀活文档**。
- **`.dev/docs/` 全域没有任何一份文档做过「估算器输出 vs 上游真实 `usage.input_tokens`」的定量误差比对。** 唯一的定量测量是 §2.1(c) MAJOR-1 里对 `encrypted_content` 字符数与 o200k token 数的统计，那是**输入侧的量级**，不是误差。
- **没有任何 ADR。** `.dev/docs/` 下无 `adr/` 目录。

---

## 3. `TODO_CURRENT.md` 与 `README.md`

### `TODO_CURRENT.md`

三处命中，且**全文件已被标注为依据悬空**：

- `TODO_CURRENT.md:3`（文件头警示，逐字引用）：

  > **依据**：原本是 `docs/2604-rewrite/` 的 DESIGN／ROADMAP／BACKLOG。**用户于 2026-08-20 裁定该目录整体过期**……**本文件的依据因此悬空**，其阶段划分与状态标注在被重新对照代码核实之前不应据以决策。

- `TODO_CURRENT.md:59` —— `- [x] anthropic/token_counting.py —— count_tokens（上游转发 / 本地估算），支撑本阶段的 count_tokens 路由`。**这条已过时**：`src/app/anthropic/token_counting.py` 在当前树中不存在（`rg -l count_tokens src/` 无此文件），对应能力已迁到 `src/app/pipeline/count_tokens.py` + `src/app/tokenization/`。
- `TODO_CURRENT.md:61` —— `- [x] routes/anthropic.py —— /v1/messages、/v1/messages/count_tokens`。**已过时**：路由表现在是 `src/app/server/routes/table.py`，`src/app/server/routes/inference.py` 是处理入口。
- `TODO_CURRENT.md:117` —— `- [x] tokenization/ —— Anthropic/Gemini estimator、size-aware calibration、prompt-limit observation、原子持久化`。**部分过时**：Gemini estimator 已归档到 `src/.archived/`（§2.3）；prompt-limit observation 的写入点只在孤儿 `tokenization/service.py`（§4.4）。
- `TODO_CURRENT.md:120` —— `- [x] 管理 API 暴露 calibration 与 advertised/observed prompt limits`。**已过时且与人控文档冲突**：`api.md:21` 已划掉这两个端点，代码中零命中。

### `README.md`

两处命中，均与 `api.md` 一致，无额外规定：

- `README.md:9` —— `- Anthropic：POST /v1/messages、POST /v1/messages/count_tokens`
- `README.md:25` —— `- ~~Tokenization：/api/tokenization/calibration、/api/tokenization/limits~~ 暂不支持`

---

## 4. 测试覆盖：逐文件、按同构 / 异构 / 不可达分类

`rg -l 'count_tokens|countTokens|estimate_responses_input|estimate_anthropic_input' tests/` 共 15 个文件。分为「真正测计数行为」（7 个）与「只是替身实现了协议方法」（8 个）。

### 4.1 真正测计数行为的文件

#### `tests/unit/pipeline/subscribers/test_builtin_subscribers.py` —— **异构路径的主战场**

| 行 | 测试 | 路径类别 | 断言了什么 |
|---|---|---|---|
| `:219` | `test_a_translated_route_is_counted_from_the_body_it_would_actually_send` | **异构** | 四条断言，缺一不可：① `estimate_responses_input(translated) != as_anthropic`——先证两个估算器在这个输入上不相等，**这是让后一条具备分辨力的前提**；② `answer["input_tokens"] == estimate_responses_input(translated)`；③ `answer["estimated"] is True`；④ `provider.counted == []`（**根本没调用上游计数器，不是调用后被拒**）；⑤ `context.extras["count_tokens_attempts"] == ["ghc:no-counter-for-openai-responses"]`（字面串精确钉死）|
| `:269` | `test_the_counted_body_is_the_repaired_one` | **同构** | 用 `context_management: {"edits": None}` 作判别输入（**不用空文本块**，因为 `builtin:blank-text-blocks` 也会删空块、断言分不清是哪个跑了），断言上游收到的是 `{"edits": []}`——即 `fix_anthropic_request` 确实跑在 count 路径上 |
| `:301` | `test_a_request_no_route_can_carry_is_refused_rather_than_estimated` | **不可达** | `OPENAI_EMBEDDINGS` 目标 → `pytest.raises(TranslatorNotFound)` + `provider.counted == []`。docstring 明写这是「旧 refusal 判对的那一类，继续拒」 |

> 注意 ②：断言等号右边是被测函数自己，**这条测试证明的是「哪个估算器跑了」，不是「它算得对不对」**。算什么由 `test_responses_estimator.py` 单独钉。这个分工是 §2.1(c) MAJOR-2 的直接产物，报告里写明了原因。

#### `tests/int/test_pipeline_app.py` —— 端到端，同构为主

| 行 | 测试 | 路径类别 | 断言了什么 |
|---|---|---|---|
| `:1197` | `test_count_tokens_asks_upstream_and_returns_its_number` | **同构** | `{"input_tokens": 4242}` 原样返回、**无** `estimated` 键；URL 是 `{BASE_URL}/v1/messages/count_tokens` |
| `:1210` | `test_count_tokens_falls_back_to_the_local_estimate` | **同构，上游 500** | `estimated is True`、`input_tokens > 0` |
| `:1227` | `test_count_tokens_asks_about_the_mapped_model` | **同构** | 上游收到的 body `["model"] == "claude-model"`（`alias` 已解析）|
| `:1242` | `test_count_tokens_accepts_a_body_without_max_tokens` | **同构** | `"max_tokens" not in` 上游 body——补入的默认值**不得越过 wire**（§2.1(a) 的 C5/M3）|
| `:1258` | `test_count_tokens_estimates_locally_for_a_model_with_no_upstream_counter` | **异构** | `gpt-model` → 200、`estimated is True`、`input_tokens > 0`、**`seen == []`**。docstring 是「两次推翻」裁决在测试里的完整复述 |
| `:1279` | `test_count_tokens_rejects_a_body_that_is_not_countable` | 前置 | 400 + `seen == []` |
| `:1290` | `test_count_tokens_refuses_a_model_without_the_messages_capability` | 前置 | `mute-model` → 400 + `seen == []`。docstring 明说这条**由 `decide_route` 拒**，删掉 provider 的 gate 它仍绿——provider gate 另有测试 |
| `:1306` | `test_what_the_calibrator_learns_survives_a_restart` | **同构** | 三个 app 共享一个 state 文件：未教过 → 教 → 后继。断言 `after["input_tokens"] != before` 且 `seen` 非空（**「这测试只在上游真被试过且失败时才有意义」**）。**注意：这条只覆盖 `anthropic` 协议键；`openai-responses` 键的持久化没有任何测试，因为今天没有东西往里写** |
| `:1786` | `test_a_token_count_says_it_was_one_and_which_counter_answered` | **同构** | 日志行 `H1/H1 200 anthropic-messages-count-tokens/claude-model …` 且 `endswith("provider(ghc)")`，两个方向的字节腿都在 |
| `:1809` | `test_a_count_upstream_could_not_answer_is_reported_as_an_estimate` | **同构，上游 500** | `endswith("provider(ghc-failed,local)")`，**单腿** |
| `:1834` | `test_a_count_with_no_upstream_counter_says_that_rather_than_a_failure` | **异构** | `gpt-model` → `endswith("provider(no-counter,local)")`、`seen == []`。docstring：「它与上游被问了却坏掉共享 `provider(local)`，reason 是唯一区分二者的东西」 |
| `:1856` | `test_a_count_upstream_answered_uselessly_keeps_the_leg_it_flew` | **同构，200 但 `input_tokens: 0`** | 双腿 + `provider(ghc-failed,local)`——「腿在」说的是上游**响应了**，不是**答出了** |
| `:2855` | `test_the_attribution_line_is_not_counted_as_prompt` | **同构** | attribution 行被剥离，`"Be brief."` 保留。docstring 给了实测数字：**同一 prompt 上游不带该行数 43 tokens、带则 77** |
| `:2953` | `test_a_count_resolves_reasoning_the_same_way_the_send_does` | **异构** | `reasoning-model` + `thinking.budget_tokens: 32000` → 200 / `estimated`。**不能从请求上读结论（异构路径什么都不发）**，改为从 `losses` 里读 `reasoning-intent-approximated` 恰好 1 条且 detail 含 `max` 与 `high`。docstring 明说第一版只断言「count 回来了且没发东西」，**把 capability channel 整个删掉仍然绿** |

#### `tests/unit/tokenization/test_responses_estimator.py` —— **异构估算器的唯一行为钉**

文件 docstring（`:1-6`）说明了写法纪律：**用增量而非绝对值断言**，因为绝对值要复述公式、而复述公式的测试对该公式的每个版本都通过。8 条测试各对应一种能击穿估算器的变异：

- `:30` `test_a_reasoning_item_is_not_free` —— 追加 4000 字符 `encrypted_content` 的 reasoning item，断言 `grew_by >= tokens(carrier)`。**这就是 §2.1(c) MAJOR-1 的回归**
- `:44` function_call 的 `arguments` 被计入
- `:56` function_call_output 的 `output` 被计入
- `:66` `instructions` 被计入
- `:75` `tools` 声明被计入
- `:86` 未知种类的 item 不免费
- `:96` message 的文本被计入
- `:108` 空 body 仍然计 ≥1

#### `tests/unit/server/test_tls_and_count_tokens.py` —— **协议无关**

`:118-213` 六条测试全部直接调用 `app.pipeline.count_tokens.count_tokens()`，上下游都是抽象 callable（`async def upstream(_) -> int` / `lambda _: 7`）。**既不是同构也不是异构**——它只测 provider chain 的编排：首个成功者胜出、失败交棒、重试花在同一个 provider 内（`max_retries=2` → 3 次调用）、顺序取自配置、`upstream=None` 被跳过而不崩、全部失败抛 `CountTokensUnavailable` 且 attempts 里同时含 `ghc` 与 `local`。

> 命名提示：这个文件前半部分（`:27-108`）是 TLS 材料解析，与 token 无关。**文件名把两个不相干的组捆在一起**，主会话若要找计数测试注意别被前半误导。

#### `tests/unit/tokenization/test_token_counting.py` —— **同构，且测的是孤儿代码**

5 条测试全部针对 `AnthropicTokenCountingService`（`:10` import）：本地估算为正、优先上游并 learn、上游出错回退、回退消费 calibration、记录 limit error 而不改写。

**关键提醒：`AnthropicTokenCountingService` 在生产中已无调用者。** `rg 'AnthropicTokenCountingService' src/ tests/` 只命中 `src/app/tokenization/service.py:21`（定义）、`src/app/tokenization/__init__.py:7,11`（导出）、以及本测试文件。生产计数路径是 `src/app/pipeline/driver.py:handle_count_tokens`。**这 5 条测试今天保护的是一条不在服役的代码路径**，其中包含 §2.2 提到的三条已断线的 calibration 学习来源（非流式 usage、流式 usage、prompt-limit 400）。按项目「不得擅自删除已实现的功能」的既有裁决，代码留着是对的；但主会话应知道**这里的绿灯对生产没有分辨力**。

#### `tests/unit/model_provider/test_model_provider.py:228`

`test_count_tokens_is_gated_on_the_messages_capability` —— provider 层的 gate：`gpt-model`、`mute-model`、`no-such` 三种输入调 `provider.count_tokens()` 都抛。**这是 `test_pipeline_app.py:1290` docstring 里点名的那条「provider gate 自己的测试」。** 今天它守的是一条在 `handle_count_tokens` 调用点上**已整体不可达**的规则（§2.1(b) 已核实 4、§2.2 `:42`），但对其他调用者仍有意义。

#### `tests/unit/server/test_server_inbound.py:66`

`test_count_tokens_route_is_marked_and_not_streamable` —— 路由表事实：`route.count_tokens is True`、不可流式、`context.extras["count_tokens"] is True`。协议无关。

### 4.2 只是替身实现了协议方法（不测计数行为）

以下文件命中 `count_tokens` 仅因为它们的 fake provider 要满足 Protocol：

- `tests/unit/pipeline/test_direct_driver.py:84-86` —— **主会话点名的文件，但它不测 count_tokens**。原文：

  ```python
  async def count_tokens(self, payload: Any, *, model_id: str) -> httpx2.Response:
      # Present so the fake really satisfies the protocol. Nothing here counts tokens, and a silent stub would let a test think it had.
      raise NotImplementedError("this fake does not count tokens")
  ```

  这是刻意的「响亮的空实现」，§2.1(a) 的 C6 核查过它。**该文件对本主题零覆盖。**
- `tests/unit/pipeline/test_timeout_enforcement.py:52`、`tests/unit/pipeline/test_auto_mode_classifier.py:497`、`tests/int/test_pipeline_ops_routes.py:41` —— 同上，替身方法。
- `tests/component/model_provider/ghc_client/test_client.py:74` —— 参数化表里的一行 `("send_anthropic_count_tokens", "/v1/messages/count_tokens")`，测的是**客户端方法到 URL 路径的映射**，与计数语义无关。
- `tests/unit/observability/test_request_log.py:138,140,156,168,170` —— 计数行的**渲染**测试（`count_tokens=True` 字段 → `anthropic-messages-count-tokens/` 前缀）。纯展示层，协议无关。
- `tests/unit/observability/test_request_log_file.py:98,134` —— JSONL 记录的字段清单里含 `count_tokens`，默认 `False`。
- `tests/unit/pipeline/test_error_classify.py:32` —— 只 import `CountTokensUnavailable` 用于错误分类。

### 4.3 覆盖缺口（我的判断，权重：足以据以行动）

1. **异构路径的 calibration 全无覆盖**——因为今天没有任何东西往 `openai-responses` 键写入。若主会话要落地 §2.1(c) 的建议 1，这里是全新的测试面。
2. **`estimate_responses_input` 的绝对精度无覆盖**，且**按设计如此**（增量断言的纪律）。任何「误差有多大」的问题，测试套件回答不了。
3. **`providers: ["ghc"]` + 异构路径**这条组合（§2.1(b) M2 指出的 400→503）**至今没有测试**。今天的 `absent_reason` 让错误串不再诬告配置，但状态码仍是 503。
4. **`count_tokens_attempts` 的细节无消费者也无测试**（§2.3 `tui/deferred.md:74`）。

### 4.4 我在检索中发现、但未见任何文档记录的落差

`.dev/docs/archived-2604-rewrite/tokenization.md:70-83` 列的四条 calibration 学习来源里，**只有第一条还接着线**：

| 学习来源（文档 `:72-75`） | 今天的写入点 | 状态 |
|---|---|---|
| Anthropic count endpoint 精确响应 | `src/app/pipeline/driver.py:339` | **在线** |
| Anthropic 非流式 response usage | `src/app/tokenization/service.py:54` | **孤儿**，生产不经过 |
| Anthropic 流式 `message_start/message_delta` usage | 同上 | **孤儿** |
| Prompt-limit 400 报告的真实 current input tokens | `src/app/tokenization/service.py:74` | **孤儿** |

即：**同构路径的 calibration 今天也只剩一个学习来源**，比文档描述的窄。这一点**未在任何报告或 deferred 台账中出现**，我认为主会话应当单独裁决（是接线回来、还是把文档改成实话）。这与「异构侧零学习来源」是同一类问题的两个程度。

### 4.5 Gemini `countTokens`

`src/app/server/routes/table.py:73-79` 已注册 `/v1beta/models/{model}:countTokens`，`count_tokens=True`、`model_from_path="model"`、但 `implemented=False`。`:60` 的注释原文：「`model_from_path` 和 `count_tokens` 都是对的、是实现时会用的，但 `implemented` 为 false 时没有任何东西读它们」。当前对该路径答 501。相关待办见 §2.3 的 `server-layout/deferred.md:30`。

---

## 5. 第 5 项直接答复：cassette 里有没有可用于定量比对的 Responses 请求体 + `usage.input_tokens`

### 结论：**有 `usage.input_tokens`（4 处，真实上游），但没有请求体。因此现有 cassette 无法直接支撑估算器误差的定量比对。**

`tests/int/cassettes/` 共 5 份。逐份实测（我用 Python 解析了每份 JSON，不是靠 grep 推断）：

| cassette | 交互 | `request` 内容 | 响应中的 `usage` |
|---|---|---|---|
| `tests/int/cassettes/anthropic_to_responses_stream.json` | `[2] POST /responses` | `shape = {"model":"gpt-5.5","stream":true,"digest":"76423e65…"}` | `"usage":{"input_tokens":12,"input_tokens_details":{"cache_write_tokens":0,"cached_tokens":0}}` |
| `tests/int/cassettes/responses_web_search_nonstream.json` | `[1] POST /responses` | `shape = {"model":"gpt-5.5","stream":false,"digest":"44816fc0…"}` | `"usage":{"input_tokens":4693,"input_tokens_details":{"cache_write_tokens":0,"cached_tokens":3712}}` |
| `tests/int/cassettes/responses_web_search_stream.json` | `[1] POST /responses` | `shape = {"model":"gpt-5.5","stream":true,"digest":"4506eeb2…"}` | `"usage":{"input_tokens":4693,"input_tokens_details":{"cache_write_tokens":0,"cached_tokens":3712}}` |
| `tests/int/cassettes/history_responses_stream.json` | `[0] POST /responses` | `shape = {}` | `"usage":{"input_tokens":56919,"input_tokens_details":{"cached_tokens":55680}}` |
| `tests/int/cassettes/history_anthropic_stream.json` | `[0] POST /v1/messages` | `shape = {}` | `"usage":{"cache_creation_input_tokens":1366,"cache_read_input_tokens":621048,"input_tokens":94,…}`（Anthropic 腿，非 Responses）|

`usage` 字段的位置：**在 `interactions[i].response.chunks` 的 SSE / JSON 正文里**，不是独立字段。流式的在 `response.completed` 事件的 `response.usage`；非流式的在唯一那个 chunk 的顶层 `response.usage`。

### 为什么请求体不在

`tests/int/recorded/record_cassette.py:182-197` 的 `_request_shape()` 只存 `{model, stream, digest}`，其中 digest 是**整个 body 排序后 JSON 的 sha256**。原文注释（`:185`）说明了为什么是摘要而不是原文：

> A digest of the whole body rather than a chosen few fields. Naming fields meant the ones left unnamed went unchecked: emptying `input` entirely — losing every message — still matched a recording that agreed on `model` and `stream`.

即：**摘要是为了当守卫用的，不是为了保存内容。** 从 sha256 反推不出 body。

`from_history.py:212-213` 则说明了 history 派生 cassette 为什么连 shape 都空：

> Left empty: history records no request body, so there is nothing to project. A replay of this cassette checks order and path, not shape.

### 一条可行的替代路径（主会话可直接用，我未执行）

`anthropic_to_responses_stream` 这一份的**输入是可复现的**：它的 Anthropic 入站 body 就写在 `tests/int/recorded/record_cassette.py:37-42`：

```python
"anthropic_to_responses_stream": {
    "model": "gpt-5.5",
    "max_tokens": 64,
    "stream": True,
    "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
},
```

而 `record_cassette.py:185` 明写「The outbound body was measured to be identical across runs」——即翻译输出是确定性的。所以可以：本地跑一次 `default_registry(None).translate(那个 body, ANTHROPIC_MESSAGES → OPENAI_RESPONSES)`，对结果算 `estimate_responses_input()`，与 cassette 里的 `input_tokens: 12` 比对；顺便可用 digest 校验翻译输出是否与录制时逐字节一致（若 digest 对得上，这个比对就是**有据可查的一对一**，而不是近似复现）。

**但这个样本的价值有限**：prompt 是刻意琐碎的（`"Reply with exactly: PONG"`），`input_tokens` 只有 12，既没有 reasoning item、没有工具、也没有长上下文——**恰恰避开了估算器误差最大的全部形态**。它能证明「估算器没有系统性偏移一个数量级」，证明不了任何关于 agent 会话真实量级的结论。

另外两份 web search cassette 的 `input_tokens=4693` 量级更有意义，但**它们不在 `SCENARIOS` 里**（`record_cassette.py:36-43` 只有一个条目），入站 body 在仓库中不可复现；`responses_web_search_nonstream.json` 在 `tests/` 与 `src/` 中**没有任何消费者**（`rg 'responses_web_search' tests/ src/` 只命中 `_stream` 那一份，用于 `tests/int/test_pipeline_app.py:431,437`，以及 `src/app/pipeline/delivery/formats/openai_responses.py:10` 的一句计数说明）。

`history_responses_stream.json` 的 `input_tokens=56919` 量级最贴近真实 agent 会话，但除了没有请求体之外，`from_history.py:34` 还说明它的**所有自由文本字段都被同形占位符替换过**（allowlist 机制），所以连响应侧的文本也不是原文。

### 若要真正做定量比对，唯一诚实的路子

按 §2.1(c) 的建议 1 落地——在 `handle()` 发出 Responses 请求前算一次 `estimate_responses_input(context.payload)`，与回复的 `usage.input_tokens`（含 `cached_tokens`）配对。**这既是误差测量的手段，也正好是「补上 OpenAI 家族 calibration 学习来源」这件已挂账待办本身。** 两件事是同一件。

---

## 6. 给主会话的三个待裁决点

1. **`archived-2604-rewrite/tokenization.md:13-44` 的身份**（§2.2）。它是异构 count_tokens 唯一的成文规格，却躺在用户裁定整体过期的目录里，而那条裁决的理由对这一节不成立。建议：提取到 `.dev/docs/count-tokens/spec.md`，在那里重建活文档（该专题目前只有 reports、没有活文档）。
2. **同构 calibration 的三条学习来源已断线**（§4.4），文档仍写着四条。这是我在检索中新发现、无人记录的落差。
3. **`openai-responses` calibration 零学习来源**（§2.1(c)、§2.2 `:44`）——这是唯一被三处一致挂账的已知缺口，且它与「想做估算器误差定量比对」是同一件事（§5 末）。

---

## 附：引用纪律说明

- 标「文档声称」的，一律给了 `文件:行号` 与原文摘录。
- 标「代码实际做的」的，均由我在 HEAD `3533386` 上直接读取源码或实测得出，未转引报告结论。凡我复核过报告里某条事实今天是否仍成立的，都在正文写明了「我于 2026-08-24 独立复核」。
- 报告原件里的路径与行号是其写作时点的快照（例如 `tests/http/test_pipeline_app.py`、`tests/unit/test_builtin_subscribers.py`、`docs/2604-rewrite/tokenization.md` 均已迁移）。**我没有改写报告原件**，正文中凡引用其行号处，同时给出了今天的对应路径。

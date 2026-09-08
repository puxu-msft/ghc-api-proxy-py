---
report_id: buffered-chat-local-tokenizer-analysis
status: settled
analyzed_at: 2026-09-06
trigger:
  source: current user request on 2026-09-06
  quoted_text: 分析会话“buffered chat completions”这证明我们的 local tokenizer 有巨大问题
  strength: technical diagnosis to verify, not a product-contract ruling
sources:
  - .dev/docs/tmp/260906-buffered-chat-completions-transcript-evidence.md
  - .dev/docs/tmp/260906-buffered-chat-completions-transcript-evidence-erratum.md
  - .dev/docs/tmp/260906-local-tokenizer-code-audit.md
---

# “buffered chat completions”会话对 local tokenizer 的证明力

## 结论

**本次请求提出的技术判断——“这证明我们的 local tokenizer 有巨大问题”——成立，而且问题不是普通 tokenizer 误差，而是结构语义建模错误。** 这里确认的是待证技术诊断，不把它升级成用户对修复方案或产品合同的裁决。对会话 `3db40195-b60b-4cdb-ab8d-1116cf721d4b` 最后一笔成功请求的高置信度重建体，事故时 production `estimate_responses_input()` 返回 4,539,201；同一 `message_id` 的 upstream raw usage 返回 921,248 input tokens。本地值是 upstream 值的 4.927230 倍，绝对高估 3,617,953，相对高估 392.723%。这个误差已经大到不能继续把 Responses local count 当作“经过校准、可用于容量判断的近似值”。

**不过，这次会话终止不是 local tokenizer 直接造成的。** 事故窗口没有 `/v1/messages/count_tokens` 调用，inference admission 全部为 `admitted_fast` 且 `field_token_count=null`，所以 whole-request estimator 没进入实际失败链。会话终止的直接链条是：最后成功请求已用到 921,248／922,000 prompt tokens，仅余 752；下一轮正常增量越界；Claude Code 随后发出四个仍超限的摘要请求；第五个摘要请求在 920,760 input tokens 时成功，但 808 个 output tokens 全是 reasoning、没有可读摘要，并以 `max_tokens` 结束；客户端因此报告 `automatic compaction failed: summarization produced empty response`。

这两个命题必须同时保留：**该会话证明 local estimator 有 major 级数量失真；该失真不是这次 overflow 的已证根因。**

## 证据链

### 1．目标会话和 upstream ground truth

目标 session 由结构化 `ai-title` 与 `agent-name` 事件唯一定位为 `3db40195-b60b-4cdb-ab8d-1116cf721d4b`。原 transcript 快照为 5,899 个 JSONL records、17,131,822 bytes，SHA-256 `f8f48799a8e7125fef087d680d60835035b25f694c0c95bd44a903dc3fac0657`。

Transcript 最后一笔正常 response 的 `message.id` 为 `edb7df67-af83-471f-b32f-5a6925f9f9e6`，client-visible usage 为 `672 + 920576 = 921248` input tokens。Proxy request log 以同一 `message_id` 记录 raw upstream usage：`input_tokens=921248`、`cached_tokens=920576`、`output_tokens=63`、`inconsistent=false`。因此 921,248 是这笔 Copilot／OpenAI Responses 请求的 upstream-reported input count，不是 Anthropic count，也不是本地估算。

### 2．同请求重建及本地复算

首个超限请求的 rejected capture 保存了实际 translated Responses payload。删除尾部三个由 transcript 明确新增的 item——上一轮 `reasoning`、上一轮 assistant `message` 和新的 task notification user `message`——得到 3,054 个 input items。Production serializer 对候选体输出 8,662,058 bytes，与上一笔成功请求日志保存的 outbound byte count精确相等；候选 SHA-256 为 `724decad3e5b3cac64b8439c9aeec2621dc1b0e579fbf0c123494fe5881ed910`。

我使用 `/home/xp/src/ghc-api-proxy-py/src/app/tokenization/estimators.py` 的当前 production 实现独立复算，并断言实际 import 路径指向该文件。复算结果完整重复了报告：候选 bytes 8,662,058、候选 SHA-256 相同、本地 estimate 4,539,201、相对 upstream 比值 4.927230。

这里仍保留一个限定：上一笔成功请求没有保存完整 body 或 body hash，所以候选体与原请求的逐字相同属于**强烈推断、足以工程处置**，不是 cryptographic identity。若未来找到原 body hash且不等于候选 SHA，精确 4.927230 倍必须撤回并按原 body重算。请求边界语义与 exact byte-length equality仍使“存在数量级高估”的结论具有很高置信度。

### 3．误差主要来自 reasoning ciphertext

候选体含 788 个 `reasoning` items。当前 `_responses_item_text()` 只特判 `message`、`function_call` 与 `function_call_output`，其它 item全部执行 `dumps(item)` 并交给 `o200k_base`。因此 provider-issued `reasoning.encrypted_content` 被当作普通 prompt文本逐字编码。

| 组成 | Item 数 | 当前 estimator contribution |
|---|---:|---:|
| `reasoning` 完整 items | 788 | 3,729,865 |
| `function_call_output` | 709 | 402,856 |
| `function_call` | 709 | 217,727 |
| `message` | 848 | 170,368 |
| 33 个 tool declarations | 33 | 16,321 |
| `instructions` | 1 | 2,064 |
| 合计 | 3,054 input items | 4,539,201 |

完整 reasoning items 占 local estimate 的 82.170%。单变量控制进一步区分了 ciphertext 与 item framing：保留 788 个 reasoning items、id和其它字段，只把每个 `encrypted_content` 设为 `""`，local estimate 降至 823,520，减少 3,715,681，占原 estimate 的 81.857600%；余下 14,184 是 reasoning item结构与每 item固定 `+4`。删除全部 reasoning items 时才会降至 809,336、减少 3,729,865。原取证报告把这两个 mutation oracle混在了一起，勘误文件已纠正，主结论不变。

这说明问题不是“`o200k_base` 选错了，所以有一点 tokenizer 漂移”。事故 catalog 对 `gpt-5.6-sol` 本来就声明 `o200k_base`；主导误差来自把**不具 ordinary-text 计费语义的 opaque state**送入 ordinary text tokenizer。

### 4．为什么 calibration 没有救回来

Active config 是 `providers: [ghc, local]`，`opus` 映射到 `gpt-5.6-sol`，未设置额外 multiplier。Responses target没有 count endpoint，因此 public `/v1/messages/count_tokens` 会落到 local estimator。Runtime `tokenization.json` 没有 `openai-responses:gpt-5.6-sol` calibration key；源码也只在 direct Anthropic count success 后调用 `calibration.learn()`，正常 Responses inference 的 upstream usage不参与学习。缺项 factor为 1.0，所以同一 translated payload通过 public count path时不会从 4,539,201 修正到 921,248 附近。

即使补一条单一标量 calibration，也不能从根本上修复当前结构错误。Images／PDF base64、Anthropic thinking漏计和Responses reasoning ciphertext分别具有不同方向、不同数量级和不同触发比例；按 `(protocol, model, size bucket)` 聚合一个倍率会把异质输入混进同一桶。Calibration可以修正同分布的系统偏差，不能把“错误地把 opaque/media bytes当文本”变成正确模型。

## 本次 overflow 的独立因果链

事故时 catalog 给出 `max_context_window_tokens=1,050,000`、`max_output_tokens=128,000`、`max_prompt_tokens=922,000`，且 `1,050,000 - 128,000 = 922,000`。最后成功请求 input为 921,248，只余 752。下一轮新增 task notification正文为 1,535 Unicode characters／1,757 bytes；仅它的离线 `o200k_base` estimate已是542，另有上一轮63 output tokens、role／item framing、system reminder和其它结构增量。因而正常增长越过922k硬边界，不需要假设一次异常大消息。

首个正常请求和随后四个逐步缩短的summary requests均收到相同 context-window 400；第五个更短的summary request在 920,760 input tokens时得到200。第五次输出有808个reasoning tokens、没有message item或可读summary，并以`max_tokens`停止；25 ms后客户端记录“summarization produced empty response”。这些观测直接证明客户端尝试了compaction，但没有得到可使用的摘要。

因此本次事故的直接待修方向是 client prompt-cap／compaction行为，不是 local count endpoint。Local tokenizer 的缺陷由同一会话暴露并可用同一请求衡量，但不能因为它们同时出现就把它写进事故根因链。

## Code audit 发现处置

以下处置针对 `.dev/docs/tmp/260906-local-tokenizer-code-audit.md` 的12项发现。它记录本轮分析判断，不授权修改用户控制文档，也不替代后续 living Spec。

| ID | 处置 | 级别 | 理由与边界 |
|---|---|---|---|
| LT-01 | 采纳 | C | `handle_count_tokens()` 在 provider chain前无条件调用 local worker；local encoding／worker failure可阻断本应优先的upstream counter。属于调用顺序 correctness defect。 |
| LT-02 | 采纳 direct Anthropic 部分；收窄 Responses 倍率 | C | Image／PDF `source` 被当JSON文本，官方同一图片样本为1,028而本地为21,158，20.58倍高估；calibration clamp后仍约10.29倍。Responses image同样走JSON fallback，但精确倍率须由对应Responses usage裁决。 |
| LT-03 | 采纳 | C | Assistant thinking被无条件跳过且model不参与策略；对keep-all模型和current turn可形成任意大的向下误差。修法必须model-aware，不能反向改成“全部计入”。 |
| LT-04 | 采纳并提升证据强度 | C | 代码机制已确认；本会话补上provider-issued reasoning-heavy长请求与upstream usage对照。数量级高估足以行动；精确4.927230倍仍受“重建体无原body hash”限定。 |
| LT-05 | 采纳，独立于本会话 | C | Local不执行context edits，production upstream path又把完整count response压成int并丢失`context_management.original_input_tokens`。这不是4.927倍的原因，但属于公开端点合同缺陷。 |
| LT-06 | 采纳，产品合同按现有人控配置解释 | A／C | 人控配置把非`local`项写成provider key；当前实现却让所有非local名称调用同一个routed provider并可能错标来源。遵从现有人控合同无需重问；若要把名称降成纯标签，才需要用户改裁。 |
| LT-07 | 采纳 | C | Responses没有production learning source，whole-request estimator固定`o200k_base`且忽略provider／model generation；“calibrated”对Responses不成立。 |
| LT-08 | 采纳 | C | Public token counting缺少living Spec，关键合同散落在配置、注释、测试和过期引用中。任何observable behavior修改前必须先建立或补齐Spec，不能从当前buggy implementation反推合同。 |
| LT-09 | 采纳机制，影响未决 | C | Tool history漏掉name／id／tool_use_id等结构字段的机制成立；真实平均误差未测，不把它升级为普遍数量级问题。 |
| LT-10 | 采纳 | C | Python中`bool`是`int`子类，当前校验会接受`input_tokens: true`并将其作为1写入calibration。 |
| LT-11 | 采纳 | C | Unit tests覆盖了production不可达的alternate service，并固定了与真实driver相反的完整字段保留行为；这些绿灯不能证明production入口。 |
| LT-12 | 采纳机制；公开合同待用户裁定 | A | `local_estimate_multiplier` 默认1.0，本次事故未触发；显式配置可无上限放大且未进入人控样例。是否把它作为公开稳定配置及是否设上限，不由本轮调查代裁。 |

本轮没有驳回任何发现；两项被收窄而非驳回：LT-02 不把Claude image公式外推为Responses image倍率，LT-09 不把结构字段漏计外推为常见数量级误差。LT-12 的行为存在性已确认，产品地位等待用户裁定。

## 根因归纳

根因不是一个需要微调的常量，而是 local estimator 把“可序列化字节”误当成“上游按ordinary text tokenizer计费的语义内容”。该假设至少在三类输入上同时破裂：Responses opaque reasoning被严重高估，Anthropic image／PDF base64被严重高估，Anthropic retained thinking被计为0而严重低估。固定 tokenizer、固定 framing常量和单一calibration factor只是放大或掩盖这些结构错误，不能修复它们。

Responses链还有第二个根因：系统已经在每次成功 inference response上获得 authoritative upstream usage，却没有让 local estimator学习；同时 carrier保留了巨大的opaque state，却没有保留可直接用于输入计数的语义依据。一次探索性对照显示，截至目标请求的成功Responses输出累计报告135,479个`reasoning_tokens`；若把完整reasoning item contribution从local estimate中拿掉再加这项累计量，得到944,815，与实际921,248相差23,567。这个结果仅是**可用于设计下一轮实验的趋势**，不是可直接采用的公式：output reasoning tokens未被协议承诺等于以后作为input重放时的token贡献，且累计response数与candidate reasoning item数存在边界差异。

## 建议的修复顺序

1. **先补living token-counting Spec。** 定义每个target protocol可用的counter、`estimated`与`local-unavailable`语义、provider顺序、结构类别覆盖、model／provider identity、context editing响应、calibration provenance和允许的误差表达。用户控制文档继续是需求层权威，不能由实现反推或擅改。
2. **把 local estimator从 provider chain前移除。** 只有实际选择local腿或明确需要学习时才计算；local failure不能阻断优先upstream counter。
3. **禁止把opaque/media载体送进ordinary text tokenizer。** 至少显式识别Responses reasoning、Anthropic image／PDF、redacted state和未知block；在缺少可靠模型语义时返回`local-unavailable`并继续其它counter，而不是返回看似精确的错误整数。
4. **为Responses建立真实usage学习路径，但不要只加一个全局倍率。** 采样必须绑定实际provider、model、tokenizer、estimator版本和输入结构特征；应从实际sent request及其final upstream usage建立样本，避免把retry或另一个attempt的usage配错。
5. **单独研究reasoning replay语义。** 可验证的候选包括：保留每轮upstream `reasoning_tokens`作为carrier metadata；比较output reasoning count与下一轮input delta；按prefix exact usage加append delta。必须用真实记录／cassette和holdout判定，不能把本次23,567差额当成协议规律。
6. **同步修复测试层级。** 回归应落在真实ASGI count入口和真实production driver；Responses reasoning测试必须以独立recorded usage为oracle，不再断言ciphertext的`tiktoken`长度；alternate dead service测试不能充当production字段保留证明。

## 当前证据能与不能支持什么

**足以支持：** local Responses estimator在reasoning-heavy长会话上有major级数量失真；当前public local count路径会暴露未经校准的错误值；主导机制是opaque reasoning被ordinary-text tokenization；同一设计还存在image／PDF高估和Anthropic thinking漏计等异向错误；需要结构化重做而不是调倍率。本次overflow的正向因果链也已成立：正常会话增长跨越922,000 prompt cap，随后compaction虽执行却只得到encrypted reasoning而无可读摘要。LT-01、LT-05、LT-06、LT-08、LT-10、LT-11及LT-12的机制按处置表所列强度分别成立；LT-09 的tool-history identity／control-field漏计机制成立，但实际影响仍未测。这些独立发现不是本次4.927倍误差或overflow事故的共同原因。

**不能支持：** local tokenizer导致了本次会话overflow；失败请求的精确upstream token count；候选体与上一笔成功request具有cryptographic identity；Anthropic server对该请求会报多少；所有Responses请求都高估4.927倍；output `reasoning_tokens`可直接等同于未来input贡献；单一calibration multiplier足以修复。

## 来源与复核入口

- 目标会话原始取证：`.dev/docs/tmp/260906-buffered-chat-completions-transcript-evidence.md`。
- Mutation oracle勘误：`.dev/docs/tmp/260906-buffered-chat-completions-transcript-evidence-erratum.md`。
- Local tokenizer代码审计：`.dev/docs/tmp/260906-local-tokenizer-code-audit.md`。
- Anthropic官方 token counting：<https://platform.claude.com/docs/en/build-with-claude/token-counting>。它支持完整结构化system、tools、images、PDF和thinking输入，并明确count只是可能与实际usage有“小量”差异；这不能解释本次4.927倍误差。
- 独立离线复算没有调用真实upstream，实际 import路径、candidate bytes／hash、本地estimate、ciphertext-only mutation和upstream raw usage均已重新核对。

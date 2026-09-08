---
report_id: buffered-chat-completions-transcript-evidence
attempt_id: 260906-buffered-chat-completions-transcript-evidence-a3d7663d2dccd8052
status: in-review
reviewed_at: 2026-09-06
reviewed_at_rev: transcript sha256 f8f48799a8e7125fef087d680d60835035b25f694c0c95bd44a903dc3fac0657，5899 JSONL records，17131822 bytes；request-log prefix through line 4620 sha256 c26ed87eec94bfc47018ffaf5c95deaa92a88d1527e272877592de5ffadd0ce4
---

# “buffered chat completions”会话与 local tokenizer 取证报告

## 结论先行

**结论必须拆成两个命题。**

1. **该 transcript 单独不能证明 local tokenizer 导致了会话终止。** 它直接证明的是：最后一个正常请求已经携带 921248 个 upstream-reported input tokens；随后一个很小的后台任务通知触发了 `model_max_prompt_tokens_exceeded`；Claude Code 识别错误并尝试 automatic compaction，但最终报告 `summarization produced empty response`。Transcript 没有记录同一时刻 `/v1/messages/count_tokens` 的请求或 local estimate，因此不能从“发生 context overflow”直接跳到“local tokenizer 低估并导致 overflow”。
2. **把 transcript 与同一进程在同一时间留下的 proxy request log／rejected payload，以及当时实际加载的 estimator 做关联后，已经有强到足以行动的证据表明 Responses local estimator 存在重大准确性问题，但方向是严重高估，而不是导致本次延迟压缩的低估。** 对上一笔成功请求的高置信度重建体，deployed `estimate_responses_input()` 给出 4539201；同一 `message_id` 的 upstream raw usage 给出 921248 input tokens。比值为 4.927230，绝对高估 3617953，即高出 392.723%。Estimator 的 3729865 tokens，也就是 82.170%，来自把 788 个 `reasoning.encrypted_content` item 当普通 JSON 文本编码。
3. **这次终止更直接的解释是 prompt-cap／client window 不对齐，加上独立的 compaction-output failure。** 事故时 catalog 明示 `max_context_window_tokens=1050000`、`max_output_tokens=128000`、`max_prompt_tokens=922000`，且 `1050000 - 128000 = 922000`。最后成功请求的 upstream input 是 921248，只剩 752 tokens；下一轮正文和结构开销足以跨线。随后四个压缩摘要请求仍收到 400；第五个摘要请求以 920760 input tokens 获得 200，却把 808 个 output tokens 全花在 reasoning、没有任何 readable summary，并以 `max_tokens` 结束，正好解释 transcript 的“summarization produced empty response”。
4. **因此可以定级为 major 的是 local count endpoint 的数量级失真；不能把它写成这次 context-window 事故的已证根因。** 在 17:35～17:56 的完整 proxy request log 中，`count_tokens=true` 的请求数为 0；事故链上的 inference admission 全部是 `admitted_fast`，`field_token_count=null`，说明 whole-request local estimator 根本没有在这条 inference 路径上运行。

## 调查范围与证据层级

本报告只读 `/home/xp/.claude/projects/`、目标项目源码、运行时持久化 request log／rejected capture、活动配置和 tokenization state；唯一写入是本报告。没有修改源码、transcript、配置或 Git 状态，没有调用任何真实 GHC／Copilot／Anthropic／OpenAI upstream。

证据按以下层级使用：

- **直接事实**：JSONL 原始字段、同一 `message_id` 的 transcript↔proxy-log join、proxy capture 中保存的实际 outbound payload、proxy 保存的 upstream raw usage／raw error、对这些固定字节运行当时已加载代码所得的确定性结果。
- **强烈推断，足以行动**：由首个 rejected payload 删除 transcript 明确新增的最后三个 input item，所得序列化长度与上一笔成功请求的日志字节数精确相等，因而把它视为上一笔成功请求体；没有原请求 body hash，所以不把“逐字相同”冒充直接事实。
- **尚未证明**：失败请求的精确 upstream token count、这次终止的唯一根因、五个 400 是否计费、2.1.263 内部 auto-compaction 阈值的确切公式、以及 reasoning ciphertext 在 upstream tokenizer 中逐 item 的计数规则。

## 1．唯一目标 session 的定位

### 定位结果

- Session ID：`3db40195-b60b-4cdb-ab8d-1116cf721d4b`。
- Transcript：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/3db40195-b60b-4cdb-ab8d-1116cf721d4b.jsonl`。
- Snapshot：5899 行，17131822 bytes，SHA-256 `f8f48799a8e7125fef087d680d60835035b25f694c0c95bd44a903dc3fac0657`。
- 标题依据：JSONL line 97 是 `{"type":"ai-title","aiTitle":"buffered chat completions",...}`；line 98 是 `{"type":"agent-name","agentName":"buffered chat completions",...}`。两种记录各重复 326 次，首见分别为 97／98，末见分别为 5888／5889；全 `/home/xp/.claude/projects` 对这两个 exact event 的固定字符串检索均只返回这一份 root transcript。
- 身份一致性：该文件所有非空 `sessionId`／`session_id` 的唯一值均为 `3db40195-b60b-4cdb-ab8d-1116cf721d4b`。
- 任务语义交叉验证：line 11 的首条人类输入是 `direct buffered /chat/completions`，line 18 是 `分析并实现 direct buffered /chat/completions`，line 23 是认证恢复后的 `retry`。每条记录的 `cwd` 均指向 `/home/xp/src/ghc-api-proxy-py`。
- 客户端版本：开头记录为 Claude Code `2.1.261`；line 2084 恢复后为 `2.1.263`，最终 line 5897 也为 `2.1.263`。

### 为什么其它命中不是目标 session

初次对所有 transcript 做普通短语检索得到大量文件，因为目标会话名后来出现在 `ListAgents` 输出、跨会话消息、项目文档以及本次调查提示中。它们只是引用。最终定位使用结构化 exact event `type=ai-title` 与 `type=agent-name`，并以 `sessionId` 和首条人类输入交叉确认，而不是把任意文本命中当标题。

## 2．完整相关上下文审阅

我对 5899 个 record 做了结构化枚举，而不只读取关键词命中行：共 1711 个 assistant records、827 个 user records、755 个 attachment records、110 个 system records。Assistant streaming／多 block 会把同一 API response 写成多行，因此后续统计先按 `message.id` 去重。

- 去重后有 675 个成功的真实 model responses，全部 `message.model=gpt-5.6-sol`。跨 2026-09-05／06 两份 proxy request log 用 `message_id` join 后 675／675 全部命中，且全部是 `requested_model=opus`、`resolved_model=gpt-5.6-sol`、HTTP 200。
- 去重后的 stop reason 为 624 个 `tool_use`、51 个 `end_turn`；root transcript 中没有一个正常 response 以 `max_tokens` 结束。另有 3 个 `<synthetic>` API error：line 15、20 是登录失败，line 5897 是本次 context-window 终态。
- Transcript 中没有 `isCompactSummary=true`、非空 `compactMetadata` 或 compaction boundary。唯一大于 10000 tokens 的相邻 prompt-count 下降发生在 line 2069→2097，由 480768 降为 374181；其间 line 2084 是用户在 CLI 2.1.263 下恢复会话并输入“继续”，同时重新注入 agent／MCP／skill 列表。没有 compaction record，故本报告只称它为“resume 后 request reconstruction 缩小”，不冒称成功压缩。
- 第二阶段从 line 2097 的 374181 单调增长到 line 5884 的 921248；没有任何一次相邻成功 response 的 prompt total 下降。
- 全文语义命中复核：`count_tokens` 只出现在 lines 144、347、363、393、446、710、713、714、879、1302、1460、2406、4813，均为 Read／search 的源码或文档输出，不是本会话的 count endpoint response；`context window` 的运行时命中只有 line 5897，line 4161 是 skill 文本；`compaction` 的运行时命中只有 line 5897，其余 lines 466、670、2087、2445、3844 是源码／文档／skill 内容；`prompt is too long` 相关的 lines 143、660、670、938、958、1760 也是既有测试或文档，只有 line 5897 是当前事故。
- Line 670 所读项目 Spec 解释了 Claude Code 依赖 `prompt is too long` 文案识别 context overflow；line 5897 证明这次 proxy 已输出该文案并触发 automatic compaction，所以旧的“错误未被客户端识别”解释不适用于本次。
- Line 713 所读 TUI Spec 明确把 `provider(local)` 定义为 proxy estimate；line 714 所读状态文档明确说 Responses inference `usage` 不参与 local calibration。两者是会话中读取的项目文字，不是当轮 runtime observation；本报告没有把它们单独当作故障证明。

## 3．Transcript 内的时间线与直接量

`prompt_total` 的算法是每个去重 response 的 `usage.input_tokens + usage.cache_read_input_tokens + usage.cache_creation_input_tokens`。这是 Anthropic-shaped response 中 input 的三个互斥分区；对该 proxy 的 Responses 翻译路径，`src/app/protocols/responses_anthropic.py:233-260,280-299` 把 upstream Responses `usage.input_tokens` 分拆后再输出，故三项之和可与同 `message_id` 的 proxy raw usage 交叉核对。它是 **Copilot／OpenAI Responses upstream-reported count**，不是 Anthropic server count，也不是 local tokenizer estimate。

| UTC 时间 | JSONL 位置 | 事件 | 直接量与解释 |
|---|---:|---|---|
| 2026-09-05 22:42:08 | line 26 | 登录恢复后的首个成功 model response | `34628 + 3584 + 0 = 38212` prompt tokens，output 195。 |
| 2026-09-06 09:43:59 | line 2069 | 第一阶段末成功 response | `512 + 480256 = 480768` prompt tokens，output 544。 |
| 2026-09-06 11:17:13～11:17:23 | lines 2084、2097 | 用户“继续”并恢复到 2.1.263 | 首个成功 request 为 374181，较 line 2069 低 106587；无 compact marker，不能断言是 compaction。 |
| 2026-09-06 17:20:39 | line 5583 | 首次超过 900k | `4801 + 896000 = 900801`。 |
| 2026-09-06 17:34:11 | line 5855 | 首次超过 920k | `6504 + 913920 = 920424`。 |
| 2026-09-06 17:35:35 | lines 5883～5884 | 最后一笔正常 response | `672 + 920576 = 921248` input，output 63；`message.id=edb7df67-af83-471f-b32f-5a6925f9f9e6`。 |
| 2026-09-06 17:52:49 | line 5896 | 下一轮唯一新增可见输入 | 后台 implementer 完成通知；1535 Unicode characters、1757 UTF-8 bytes。用部署同版 `tiktoken==0.14.0`／`o200k_base.encode_ordinary()` 离线计为 542；该 542 只是 local estimate，绝不是 server count。 |
| 2026-09-06 17:55:14 | line 5897 | 终态 | Client-visible `400 invalid_request_error`，code `model_max_prompt_tokens_exceeded`；显示 `Prompt is too long · automatic compaction failed: summarization produced empty response`。 |

### 接近上限的算术

事故时 proxy log 为同一 resolved model 记录 `max_prompt_tokens=922000`。最后成功 input 为 921248，即使用了 99.918438%，只余 752。Claude Code 下一次构造 prompt 时还要纳入上一笔 63 output tokens 和 line 5896 的新消息；仅用 local `o200k_base` 对通知正文算出的 542 相加，得到 `921248 + 63 + 542 = 921853`，距 922000 只剩 147，尚未计 role／item framing、自动 system reminder 和可能变化的 instructions／tools。这个算式只证明“正常增量足以逼近并跨越已知 prompt cap”，不把 542 当 upstream count，也不声称精确还原失败请求 token 数。

### Transcript 直接可累计的吞吐量

按 675 个唯一 `message.id` 去重后求和：uncached input 6835476、cache-read input 386817024、cache-creation input 0、output 367994；累计 prompt-token throughput 为 393652500，累计 prompt+output throughput 为 394020494。它们是 675 次请求的重复处理总量，不是某一轮 context size，也不是账单金额。

Line 2081 的 `cost-state` 是恢复前快照：`totalCostUSD=132.81029975`，两个 model bucket 合计 input 9797835、cache-read 137741312、cache-create 405771、output 496576，并带 `hasUnknownModelCost=true`。它同时包含本 session 派出的 subagents；主 transcript 的 675 个 `message_id` 在 proxy log 中全部是 `opus→gpt-5.6-sol`，而该 snapshot 同时列出 `opus[1m]` 与 `sonnet[1m]`，所以不能把 132.81 美元归因给 root session、更不能归因给 tokenizer。

628 个 `<total_tokens>… tokens left</total_tokens>` attachment 从 15000000 递减，line 2068 到 14519283，resume 后 line 2088 又重置为 15000000，line 5881 为 14560126。它显然是 harness 的会话预算提示，不是 1M model context count；本报告不拿它证明 prompt 大小。

## 4．同一事故的 proxy 侧时间线

以下是辅助证据，不属于 transcript 本体。请求日志为 `/home/xp/.local/share/ghc-api-proxy/requests/requests-20260906.jsonl`；本报告冻结其前 4620 行 SHA-256 为 `c26ed87eec94bfc47018ffaf5c95deaa92a88d1527e272877592de5ffadd0ce4`。Line 4468 的 `message_id` 与 transcript line 5884 精确相同，因此其 raw usage 与请求字节可以可靠归到目标 session。

1. Request-log line 4468：最后正常 request 从 17:35:13.110 到 17:35:35.869，HTTP 200；outbound body 8662058 bytes；raw upstream usage 为 input 921248、output 63、total 921311，其中 cached input 920576；observation 标记 `inconsistent=false`。
2. 同一行的 catalog snapshot：`gpt-5.6-sol`、tokenizer `o200k_base`、`max_prompt_tokens=922000`、`max_context_window_tokens=1050000`；inference admission 为 `admitted_fast`，只记录最大单字段 82384 UTF-8 bytes，`field_token_count=null`。
3. Transcript line 5896 后 319 ms，request-log line 4614 的正常 main request 开始。它在 18.478 s 后返回 400。首个 rejected capture 是 `/home/xp/.local/share/ghc-api-proxy/rejected/20260906T175307.992-400-48461c44-4c41-411d-95ce-bf2d21dfd717.json`，真实 outbound payload 有 3057 input items、8669914 bytes、`max_output_tokens=128000`，且没有 `truncation` 或 `context_management`。Raw upstream body只有 `invalid_request_body` 和 `Your input exceeds the context window of this model...`，没有 token 数；client-visible `model_max_prompt_tokens_exceeded` 是 proxy 的 Anthropic-shaped映射，不能冒充 upstream 原码。
4. Request-log lines 4615～4618 是四个连续的 compaction summarization request，均 HTTP 400、`attempts=1`；对应 captured body依次为 8668613／8662335／8655727／8649042 bytes，input items 为 3055／3050／3047／3045。后四份 payload 的尾部含 `CRITICAL: Respond with TEXT ONLY...` summary instruction，证明这是 client orchestration 逐步缩短摘要输入，不是 proxy 对同一 request 的网络重试。
5. Request-log line 4619 是第五个 summary request：HTTP 200，upstream input 920760、output 808、total 921568；两个 output item 都是 encrypted reasoning，`reasoning_tokens=808`，没有 message item或 readable summary，并以 `stop_reason=max_tokens` 结束。25 ms 后 transcript line 5897 写出 `summarization produced empty response`。这条链直接解释 compaction failure。
6. 五个 400 的服务耗时合计 100.076 s；从 transcript line 5896 到 line 5897 共 145.639 s，余下约 45.563 s 与 line 4619 的 44.523 s 成功但无可读摘要请求及请求间隙吻合。
7. 17:35～17:56 的完整 request log 中 `count_tokens=true` 为 0。事故链各 request 的 token admission 都是 `admitted_fast`，说明 public local count endpoint 与 whole-request estimator不在本次失败路径上。

五份 rejected capture 的 SHA-256 依时间顺序为：

- `52cfad90a68d7788115d0719e9e445bc3927780708ca61bff7e2cd0cac3d2dfd`
- `e4a9d3e574b522b999f56cabd4b5a173a8772502239384b9c27a90fbc2c755cb`
- `9d0c40c27d8639df00d77cf630e94fab7ba6ae91fa0b4ba4141958b3c188a2f7`
- `a09b7cce22748b2afca990023c141e2590c7f3eebb105e67fd2d051f74552520`
- `dc3ce80a0c4503d79e1a6f70c221a815f606d94f87c57f891cdbb48dce64f65a`

## 5．Local estimator 的同请求重建

### 算法与输入来源

输入一是首个 rejected capture 的实际 translated Responses payload；输入二是 transcript lines 5881、5883～5884、5896；输入三是 request-log line 4468 的上一笔成功 request byte count和 raw usage。

重建步骤如下：

1. 首个 failed payload 的最后三个 input item依次是 `reasoning`、`message(role=assistant)`、`message(role=user)`。
2. 前两个逐项对应 transcript lines 5883～5884 的最后正常 response；第三个对应 line 5896 的 task notification。删除这三个 item后，payload最后一项是 `message(role=system)`，正文精确为 transcript line 5881 的 `<total_tokens>14560126 tokens left</total_tokens>`，与上一笔请求的时间边界一致。
3. 用事故进程实际加载的 `app.wire_json.dumps()` 序列化候选体，得到 8662058 bytes，**与 request-log line 4468 保存的上一笔成功 outbound body bytes 精确相等**。候选 SHA-256 为 `724decad3e5b3cac64b8439c9aeec2621dc1b0e579fbf0c123494fe5881ed910`。
4. 用事故进程实际加载的 `src/app/tokenization/estimators.py` 调 `estimate_responses_input(candidate)`，得到 4539201。Estimator 文件 SHA-256 为 `94a75775770f951e75fc4785b2dd2a465fe82a55d5da4c977d362e327f462a48`，mtime 为 2026-09-05 18:56:45 UTC；service process 于 2026-09-06 15:38:49 启动，import解析到该文件，故不是事后换版代码。
5. 同 `message_id` 的 upstream raw usage 是 921248 input tokens。计算为 `4539201 / 921248 = 4.927230`，绝对差 3617953，相对高估 392.723%。

第 3 步的 exact byte-length equality加上 append-only tail对应关系使 reconstruction 足以支撑工程处置，但因为上一笔成功 request没有保存 body hash，本报告仍把“候选逐字等于实际 request”列为强烈推断，而非直接事实。若后来找到上一笔 body或hash且不等于候选 SHA，4.927230× 的 same-request表述必须撤回并重新计算。

### 估算组成

| 部分 | items | estimator tokens |
|---|---:|---:|
| `reasoning` | 788 | 3729865 |
| `function_call_output` | 709 | 402856 |
| `function_call` | 709 | 217727 |
| `message` | 848 | 170368 |
| `tools` | 33 declarations | 16321 |
| `instructions` | 9296 bytes | 2064 |
| 合计 | 3054 input items + top-level fields | 4539201 |

`reasoning` 占 local estimate 的 82.170%。候选中 reasoning text material为 5485996 bytes；当前 `_responses_item_text()` 只特判 `message`／`function_call`／`function_call_output`，所以 `reasoning` 走 fallback `dumps(item)`，把 opaque `encrypted_content` 当 ordinary text计数。把 reasoning contribution从算术中拿掉后只剩 809336，但这不是一个可替代 estimate，更不是 server 对 reasoning 的真实计数；它只用于定位当前 4.54M 数字的主导来源。

首个到第五个 rejected payload 的 raw local estimate依次为 4543418、4540493、4536589、4532730、4528826。即使 client逐轮删掉消息，opaque reasoning历史仍令 local estimate稳定在 4.5M 以上。这个观察与 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260906-local-tokenizer-code-audit.md:115-133` 的 LT-04 机制判断一致，并为其补上长会话、真实 provider-issued reasoning replay 的量级证据。

### 为什么 public local count 会暴露这个数字

事故时 active config `/home/xp/.local/share/ghc-api-proxy/config.yaml:4-7,12-20` 配置 `providers: [ghc, local]`，并把 `opus` 映射到 `gpt-5.6-sol`；未设置 `local_estimate_multiplier`，schema 默认是 1.0。`driver.py:381-413,438-487` 对 count request先翻译成最终 Responses body再估算；Responses target没有 upstream count endpoint，因此转入 `local`。`tokenization.json` 在进程启动前的 snapshot中没有任何 `openai-responses:gpt-5.6-sol` calibration key，`CalibrationEngine` 对缺项返回 factor 1.0。因此，对同一 translated payload，public local count path不会把 4539201 校正回 921248 附近。

这证明的是 local count contract 的重大失真，不是 inference path 的 local rejection。`PromptTokenAdmission` 是另一机制：`admission.py:435-492` 只在某个**单独字段的 UTF-8 bytes**大于 `max_context_window_tokens` 后才 tokenizer-count该字段，不累加全 payload，也不以 `max_prompt_tokens` 为阈值。事故日志里的 `admitted_fast` 与 `field_token_count=null` 正好符合这个窄合同；不能把它说成“local tokenizer算了 4.5M 后仍放行”。

## 6．主张分级

### 直接事实

1. 唯一目标 session及其标题、路径、版本和任务内容已由结构化 event确认。
2. 最后正常 response 的 client-visible usage分区和 proxy raw upstream usage均给出 921248 input tokens；它来自 Copilot/OpenAI Responses，不是 Anthropic server count。
3. 当时 catalog snapshot 的 max prompt为 922000；最后成功 request距上限 752。
4. 下一条 task notification只有 1535 characters／1757 bytes；local `o200k_base` count为542，但该数只是离线估算。
5. 下一轮出现 raw upstream context-window 400；proxy把它映射成client可识别的Anthropic-shaped错误；Claude Code随后尝试compaction。
6. 一个正常 request加四个 summary requests收到400；再一个 summary request得到200但只有808 reasoning tokens、没有 readable summary，随后client报“summarization produced empty response”。
7. 关键时间窗内没有 count endpoint call；所有 inference admission均未运行whole-prompt tokenizer。
8. 当时部署的 estimator对保存的 rejected payload输出约4.53M～4.54M，且82.170%来自reasoning item文本化。

### 强烈推断，足以行动

1. 删除首个 failed payload最后三个、由 transcript 明确新增的item后得到上一笔成功request的逐字payload。支撑：边界item语义完全对应且序列化byte count与日志精确相等；缺口：没有原body hash。
2. 在上述重建成立时，Responses local estimator对同一prompt高估4.927×，属于public `/v1/messages/count_tokens`的major correctness defect；长reasoning-heavy agent session是具体触发条件。
3. 初始400的主要近因是922000 prompt cap被正常会话增长跨越，而不是local estimator低估。支撑：上一笔已到921248、下一轮body增加7856 bytes、local endpoint未调用、local误差方向反而向上。

### 尚未证明

1. 失败request的精确upstream input token数。400 body没有给数字，不能把922000、4539201或UI数字冒充实际count。
2. 上一笔成功payload与重建候选的cryptographic identity。只有结构边界和exact byte-length equality，没有原body hash。
3. Claude Code 2.1.263为何没有在922000前主动换入precomputed summary。相邻2.1.241 source能解释nominal 1M window下较晚阈值，但不是事故版本，故只可作候选解释。
4. 第五个summary request为何只生成808 output tokens便`max_tokens`。日志没有保存该成功request的完整payload，不能确定它请求的output cap，也不能排除upstream动态裁剪。
5. 五个400是否产生费用。没有usage／billing记录，不作推断。
6. 任何Anthropic server token count。本事故没有访问Anthropic模型；所有成功ground truth均是GitHub Copilot承载的OpenAI Responses `gpt-5.6-sol` usage。

## 7．主要替代解释及检查结果

| 替代解释 | 检查 | 判定 |
|---|---|---|
| Local tokenizer低估导致client太晚压缩 | 关键窗口没有count call；重建prompt的estimator误差是约4.93×高估 | **对本次因果已反驳**。不能解释observed late overflow。 |
| Proxy没有把upstream context错误翻成Claude Code认得的形态 | Raw upstream是`invalid_request_body`＋`exceeds the context window`；transcript line 5897已收到`prompt is too long`＋`model_max_prompt_tokens_exceeded`，并明确进入automatic compaction | **反驳**。错误识别与映射生效。 |
| Client根本没有尝试compaction | 四个summary payload 400，随后一个summary payload 200但无文本；总历时与line 5897吻合 | **反驳**。它尝试了，但没取得可用摘要。 |
| 一条异常巨大的task notification突然增加数万tokens | 原文仅1757 bytes，local o200k为542；outbound body只比上一笔多7856 bytes | **不是巨大跳变**。但只剩752-token余量，所以小增量仍足以越线。 |
| Upstream随机抖动／错误误报 | 连续五个逐步缩短的payload都在922k边缘返回同一400，第六个更短请求返回200并报告920760 input | **强烈反驳随机性**，支持硬边界。 |
| Prompt被proxy自动截断或context editing改变 | 五份failed payload均无`truncation`／`context_management`；input item数量按client summary重试逐步下降 | **反驳proxy自动截断**；发生的是client侧逐步缩短summary输入。 |
| `total_tokens` UI说明还有1456万context，故server错误异常 | 该attachment从1500万递减并在resume重置，远大于model window | **反驳**。这是harness预算，不是prompt count。 |
| Line 2081的132.81美元证明tokenizer造成成本异常 | 快照包含subagents、两种model bucket、`hasUnknownModelCost=true`，而且只到resume前 | **未证明**。只能证明已有该本地accounting snapshot。 |
| Inference admission已经运行whole-request tokenizer但算错 | 日志明确`admitted_fast`、`field_token_count=null`；源码合同只审单字段 | **反驳**。该gate没有执行whole-request count。 |
| Local estimator的4.93×只是“tiktoken与Anthropic tokenizer不同” | Ground truth来自`gpt-5.6-sol` Responses usage，不是Anthropic；estimator也用catalog指定的`o200k_base`，误差主要由opaque reasoning被当普通文本 | **反驳该表述**。问题是结构语义，不是拿OpenAI tokenizer去近似Claude tokenizer。 |

## 8．否决过的调查路线

1. **否决用普通全文短语命中定位session。** “buffered chat completions”出现在其他会话的消息、文档和本次调查提示中，第一次检索产生5.5MB噪声；改用exact `ai-title`／`agent-name` event并全局判唯一。
2. **否决把每个assistant JSONL行当一次API call。** Streaming block会共享同一`message.id`和整份usage；统计全部按`message.id`去重，否则会把usage重复两到数次。
3. **否决把`<total_tokens>…tokens left`当context count。** 其1500万量级和resume重置与1.05M model window不相容。
4. **否决把`cost-state`当root-session账单或终态账单。** 它包含subagents、带unknown-cost标志，且快照止于line 2081。
5. **否决把transcript line 5897的code当raw upstream code。** Rejected capture证明raw code是`invalid_request_body`；`model_max_prompt_tokens_exceeded`是proxy的Anthropic-facing映射。
6. **否决只凭context 400宣称local tokenizer有错。** Transcript没有记录当轮local count；必须另找same-prompt estimate与upstream usage。
7. **否决把reconstruction的exact byte-length match升级成cryptographic identity。** 没有原成功body hash；结论保留强烈推断标签和明确falsifier。
8. **否决把prompt admission未累加全体直接定性为tokenizer bug。** 这是当前被测试固定的standalone-field guard；是否应扩为aggregate gate属于另一个产品合同问题。
9. **否决用Claude Code 2.1.241的可读源码替代事故版本2.1.263。** 2.1.241只用于理解候选机制，不进入直接事实链。
10. **否决为补足exact server count重放真实upstream。** 用户明确禁止；本轮只对已保存payload做offline计算。

## 9．最小、可证伪、零真实上游的下一步实验

建立一个单文件test-only fixture／probe即可，不需要接入任何gate：

1. 固定首个rejected capture SHA-256 `52cfad90a68d7788115d0719e9e445bc3927780708ca61bff7e2cd0cac3d2dfd`、transcript snapshot SHA-256和request-log prefix SHA-256；从capture payload删除最后三个input item，要求边界item仍是line 5881的total-token reminder。
2. 用production serializer计算候选体，断言bytes恰为8662058、SHA-256恰为`724decad3e5b3cac64b8439c9aeec2621dc1b0e579fbf0c123494fe5881ed910`；从frozen request-log fixture独立读取同`message_id`的raw upstream `input_tokens=921248`，不要把expected写成estimator自身的输出。
3. 用production `estimate_responses_input()`计算候选体。当前可证伪预测是4539201；若不是，说明代码／依赖或重建前提已改变，停止沿用本报告倍率。
4. 做一个唯一变量控制：把788个reasoning item的`encrypted_content`替换为空串但保留item、id及其它结构。当前预测local estimate减少3729865；若没有，说明本报告定位的主导机制错误。
5. 该offline fixture可以证明estimator mechanics与记录值冲突，但不能新增provider ground truth。若要把“same request”从强烈推断升级为直接事实，唯一缺件是上一笔成功outbound body或其hash；找到后若不等于候选SHA，立即撤回4.927230×并按实际body重算。不要为补这个缺件发真实upstream请求。

实验判否标准很简单：候选hash／bytes任一不符、local estimate不为4539201、reasoning mutation不减少3729865、或后来找到的原成功body hash不同，均使当前倍率结论失败；不允许通过放宽容差保住结论。

## 10．对现有 code audit 的交接

`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260906-local-tokenizer-code-audit.md:115-133` 的 LT-04 当前为 `likely`，理由是没有真实 Responses replay。主会话可以把本报告作为补充证据：将“Responses reasoning全文按ordinary JSON计数会产生数量级高估”提升为**强烈支持、足以修复**；但在没有原成功body hash前，不宜把精确4.927230×写成无条件confirmed。与此同时，必须保留因果分离：这次会话终止不是该高估直接造成的，实际失败链是922k prompt cap触发＋summary response无可读文本。

## 我最没把握的三个判断

1. **重建候选是否逐字等于上一笔成功request。** 语义边界与字节数同时精确吻合，置信度高且足以行动；缺少原body hash，所以不是数学证明。
2. **Client 2.1.263主动压缩阈值与2.1.241是否一致。** 本报告没有把邻近版本反编译结果当事故版本事实；只从实际事件认定client在400后做了reactive compaction。
3. **第五个summary request为何只生成808 output tokens便`max_tokens`。** 输出形态和停止原因是直接事实，具体成因仍未决；它可能涉及动态output cap、provider行为或client recovery参数。

## 执行本契约时遇到的摩擦

- CodeGraph确认目标项目没有可用index，后续按规则改用绝对路径Read／rg。
- `procs`未安装，读取process start time时使用只读`ps` fallback。
- Target transcript在调查中mtime变化但size、line count与SHA-256连续两次一致；报告按最终hash和line 5899截止，不把mtime变化解释成内容变化。
- 本人是leaf executor，未派生reviewer；主会话应独立复核重建步骤后再把精确倍率升级为confirmed。

## 交付声明

delivery_complete: true
completed_at: 2026-09-06
finding_total: 1
blocker: 0
major: 1
minor: 0
nit: 0

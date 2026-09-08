# 评审：count_tokens 翻译路径与 `estimate_responses_input`

日期：2026-08-20
评审对象：工作树未提交改动，限于 `src/app/tokenization/estimators.py`、`src/app/server/handler.py`、`src/app/pipeline/translation_driver/registry.py`、`tests/unit/test_builtin_subscribers.py`、`docs/2604-rewrite/tokenization.md`。
评审者：leaf executor，只读；未修改仓库任何文件（本报告除外）。

## 评审基线与证据可复现性

评审期间仓库 HEAD 被并行会话推进（`3c5a337` → `002c248`，同伴的 `translation_driver/{openai_responses,semantic}.py` 已提交）。**被评审的四个文件在整个评审过程中字节未变**，已用 md5 核对：`estimators.py` = `7016e1725544bd44bfb0e9a10589d279`，`handler.py` = `72bf1116dd96476615c3abedfbdcf2d0`。下述所有变异实验都跑在这两个字节完全一致的副本上。

变异实验在隔离副本 `/tmp/revcopy`（`tar` 排除 `.git/.venv/refs/exp` 后复制）里进行，未触碰共享工作树。副本里有一条固定失败 `tests/unit/test_debug_models.py::test_the_recorded_catalog_capture_reads_end_to_end`（我排除了 `refs/`），是复制产物、非缺陷，下文所有计数都以它为基线。

基线：`1444 passed, 1 failed(复制产物), 2 skipped`。

`ruff check` 与 `pyright` 对三个源文件均干净（`All checks passed` / `0 errors`）。

## 结论

- blocker：0
- major：2
- minor：7

功能方向我认同：量翻译后的 body 是对的，`attempt.prepare` 挪到翻译之后是对的，删 `can_translate()` 是安全的。两条 major 都不是「这次改坏了」，而是「这次声明的东西没有兑现」——一条是文档与 docstring 声称的补偿机制不存在，一条是新估算器完全没有测试钉住。

---

## Major

### MAJOR-1 `reasoning` item 静默计 0，而为它开脱的那条补偿机制不存在

**位置**：`src/app/tokenization/estimators.py:122-123`（`if kind == "reasoning": return ""`）、同文件 `:117` 的 docstring、`docs/2604-rewrite/tokenization.md` 「`estimate_responses_input` 的两处限定」一段。

**具体失败输入 → 具体错误结果**（实测，非推理）：

主产品路径上，Claude Code 把本项目自己的 reasoning carrier 签名回传，`anthropic_messages.py:50-64` 把它判为 `PROXY_CARRIER`，`openai_responses.py:526-536` 于是产出带 `encrypted_content` 的 reasoning item。用 `encode_reasoning_carrier` 造一个 7169 字符的 payload（即实测中位数量级），跑 `default_registry(None).translate(...)`：

```
[0] type=message   wire_json_chars=96    counted_chars=17
[1] type=reasoning wire_json_chars=7286  counted_chars=0
[2] type=message   wire_json_chars=100   counted_chars=20
[3] type=message   wire_json_chars=96    counted_chars=17
estimate_responses_input: 30
```

7.6 KB 的 body 报 30 tokens。

**这个量级是实测的，不是我编的。** 从 `~/.local/share/copilot-api/history-v3-20260815-183721.db`（复制到 `/tmp/histprobe` 后只读打开，未动原库）取 244 条含 `encrypted_content` 的 `sequence-item`，抽出 157 个 `encrypted_content` 值：

| 指标 | min | median | max |
|---|---|---|---|
| 字符数 | 5020 | 7164 | 11664 |
| o200k token 数（密文本身） | 3454 | 4901 | 7967 |

一轮 agent 会话里这样的 item 有几十个。**上游 tokenizer 数的是到达的东西**——这正是这次改动自己写在 `handler.py:145` 的理由——而到达的东西里这几十 KB 被算成了 0。

**「镜像 Anthropic 侧不计 `thinking`」这个类比站不住，缺的是第二半。** Anthropic 侧同样跳过 `thinking`（`estimators.py:27-28`），但那一侧的系统误差**被学回来了**：`calibration.learn("anthropic", ...)` 在 `handler.py:211`、`hooks/builtin/token_calibration.py:65,99`、`tokenization/service.py:54,74` 共四处以真实上游计数为 ground truth 训练因子。Responses 侧一处都没有——全仓 `learn(` 的调用点里没有任何一个传 `"openai-responses"`。于是 `calibration.py:79-81` 的 `_models.get(("openai-responses", model))` 恒为 `None`，`factor_at` 恒返回 `1.0`，`calibrate` 恒为恒等函数。

所以：

- `estimators.py:117` 的 “calibration absorbs the difference rather than a guess being written in”——**当前为假**；
- `tokenization.md` 的 “差额交给 calibration 吸收”——**当前为假**，而且同一节往下三行自己写了「尚未做：OpenAI 家族的 calibration 没有学习来源」。**一节之内自相矛盾。**

**方向就是被警告的那个方向**。`_responses_item_text` 的 docstring 自己说 “a count that is wrong in the direction of ‘smaller’ is the direction that gets a request refused after it was said to fit”。reasoning 的跳过恰恰是这个方向，而且是这条路径上最大的一项。Claude Code 拿这个数决定何时压缩，低报 → 不压缩 → 真请求撞上下文上限被 400。

**判断权重：足以据以行动。** 量级来自 157 个真实样本，路径来自实跑翻译器，补偿机制的缺失来自穷举 `learn(` 全部调用点。我不知道的只有一件：上游对 `encrypted_content` 究竟按多少 token 计费（密文的 tiktoken 数必然远大于其代表的真实 reasoning token 数，所以「按整段 JSON 计入」也是错的，只是错在另一个方向）。这一点确实无从测量，作者的说法成立——但「无从测量」的结论应当是「所以要靠 calibration 学」，而 calibration 现在学不到。

**建议**（择一，不构成门禁）：
1. 优先做文档里已记为「尚未做」的那件事：在 `handle()` 发出请求前算一次 `estimate_responses_input(context.payload)`，用 Responses 回复的 `usage.input_tokens`（含 cached）调 `learn("openai-responses", route.model_id, estimate, real)`。这一步做完，MAIN-1 里「calibration 吸收」才从声称变成事实，并且会把 reasoning 的系统性缺口自动学回来。这比继续打磨估算器本身 ROI 高得多。
2. 在 1 落地之前，把 `estimators.py:117` 与 `tokenization.md` 里「交给 calibration 吸收」改成如实陈述：**当前无补偿，这是一个已知的单向低估**。

### MAJOR-2 `estimate_responses_input` 的行为没有任何测试钉住

**位置**：`tests/unit/test_builtin_subscribers.py:266`。

`assert answer["input_tokens"] == estimate_responses_input(translated)` 用**被测函数自己**当 oracle。它能证明「handler 调用了这个估算器、且喂的是翻译后的 body」，证明不了这个估算器算什么。

**变异验证**（全量 `pytest tests`，隔离副本，字节一致）：

| 变异 | 结果 |
|---|---|
| `_responses_item_text` 对 `reasoning` 改为返回整段 JSON | `1444 passed`，**全绿** |
| `_responses_item_text` 对 `function_call` 改为返回 `""` | `1444 passed`，**全绿** |
| `estimate_responses_input` 不再计 `instructions` | `1444 passed`，**全绿** |
| （作者的变异）count 路径跳过翻译 | `3 failed`（含 1 条基线产物）→ **实测 2 条变红，作者的说法成立** |

`_responses_item_text` 的分支覆盖情况：测试 body 只有 `instructions` + `tools` + 一条 user message，所以只走到 `message` 分支。`reasoning`、`function_call`、`function_call_output`、未知种类的整段 JSON 兜底、非 dict item、`content` 为字符串、无 `role`——**七个分支一个没走到**。

我不提覆盖率建议。这里的具体失败面是明确的：MAJOR-1 里那条「reasoning 计 0」的裁决，是这次改动里唯一一条会显著改变数值、且**方向已知有害**的判断，而它现在可以被任何人在任何时候反向改掉且无人察觉。一条把上面那个 7286 字符 reasoning body 的期望值写成常数的测试就够了（顺带把 `function_call` / `function_call_output` 各带一条），不需要新框架。

---

## Minor

### MINOR-1 `learn` 的协议键仍写死 `"anthropic"`

`src/app/server/handler.py:211`：`calibration.learn("anthropic", route.model_id, estimate, result.tokens)`，而 `:185` 的读侧已经改成 `calibration.calibrate(protocol, ...)`。

当前等价——该分支只在 `result.provider == "ghc"` 时到达，而那要求 `upstream_counts`，即 `target_format is ANTHROPIC_MESSAGES`，此时 `protocol == "anthropic"`。但读写两侧不再由同一个表达式导出，MAJOR-1 建议 1 落地时这就是会写错的那一行。改成 `protocol` 是零成本的。

### MINOR-2 else 分支覆盖了「所有非 Anthropic 目标」，但估算器只认 Responses

`src/app/server/handler.py:167-168`。

今天不可达：`OPENAI_CHAT_COMPLETIONS` / `OPENAI_EMBEDDINGS` 都没有 outbound translator（`registry.py:136-153` 只注册了 Anthropic 与 Responses 两对），`translate()` 会先在 `registry.py:86` 抛 `TranslatorNotFound`。我用 `model@openai-chat-completions` / `model@openai-embeddings` 两条显式路由核对过 `decide_route` → `translate` 的路径，确实都在估算器之前就 400 了。

但一旦有人注册 chat-completions 的 outbound translator：chat-completions body 没有 `input`、没有 `instructions`，`estimate_responses_input` 会返回 `max(tools_only, 1)`——很可能就是 **1**。这正是同一个文件 docstring 里说不许发生的「静默计零」，而且没有任何东西会响。

建议显式判 `route.target_format is WireFormat.OPENAI_RESPONSES`，其余 raise，而不是用 else 兜住整个 `WireFormat` 空间。

### MINOR-3 web search 的 INFO 日志在启用 web search 的客户端上翻倍

`src/app/pipeline/translation_driver/openai_responses.py:297` 每次翻译带 Anthropic server-tool 声明的请求都打一条 INFO。count 路径现在也翻译，所以 Claude Code 每回合会打两条而不是一条。该日志的注释明确论证过「它是 setting 不是 warning，所以用 INFO」，这个论证在频率翻倍后仍成立，但作者应知道这是本次改动的副作用。

### MINOR-4 count 端点新增了一类 400，文档与测试都没提

带 `allowed_domains` / `blocked_domains` 的 web search 声明，现在在 **counting** 时就会从 `openai_responses.py:217` 抛 `TranslationRefused`。`handler.py:258-265` 把它映射到 400，与 `/v1/messages` 一致——**我认为这是对的、也是这次「量真正会发出去的那个 body」的必然结果**。但它是 count 端点的一个全新失败模式，`tokenization.md` 没写，也没有测试。

另附一条协作提示：`handler.py:44` 现在 `from app.pipeline.translation_driver.semantic import TranslationRefused`，这是同伴会话正在实现的 `hosted-web-search-spec.md` §3.4 的产物。改 `error_status` 是必要的（否则 `/v1/messages` 上这条也会掉进 502），但它跨到了同伴的特性边界上，值得知会一声。

### MINOR-5 `_responses_item_text` 的两处小遗漏

- `function_call` / `function_call_output` 都不计 `call_id`（`estimators.py:140-146`）。每个 item 少几到十几个 token，几十次工具调用的会话累计几百 token，方向是「小」。`+4` 的常数项部分吸收了它。
- `message` 的 `content` 为字符串时提前 return（`:126-127`），**不拼 `role`**，与 list 分支（`:136-138` 会 `parts.insert(0, role)`）不一致。

第二条从 `handle_count_tokens` 不可达：count_tokens 只挂在 `ANTHROPIC_MESSAGES` inbound 上（`inbound.py:36-40`），所以 `translation_required` 恒为真，body 恒由 `_message_item`（`openai_responses.py:428-429`）产出、`content` 恒为 list。属防御性代码，不必改；提出来只是因为两分支不一致本身会误导下一个读者。

### MINOR-6 calibration 键兼容性——已核对，无问题（记录以免下一轮重查）

- `snapshot()` 用 `f"{protocol}:{model}"`（`calibration.py:111`），新条目形如 `openai-responses:<normalized-model>`，与 `anthropic:*` 不冲突（`:` 分隔，protocol 里的 `-` 无歧义）。
- `from_snapshot()` 读的是条目内的 `protocol` / `model` 字段而非 key（`calibration.py:131-132`），所以既有存量文件原样加载，不受影响。
- `GET /api/tokenization/calibration` 按 `value["protocol"] == protocol.lower()` 过滤（`management.py:73`），`?protocol=openai-responses` 可用。
- 本路径不会向 `anthropic:*` 写入任何东西，**不污染既有数据**。

一个副记录：变异「把 `protocol` 强行写回 `"anthropic"`」全量测试仍全绿，即这个裁决没有测试钉住。但它今天也不可观测（理由见 MAJOR-1：两个键都没有样本，且 gpt 模型不可能走 Anthropic 腿拿到因子），所以我**不要求**为它加测试。

### MINOR-7 文档：同一句里既立规矩又破规矩

`docs/2604-rewrite/tokenization.md`：

> `estimate_responses_input` 的两处限定……**reasoning item 不计入**……；**未列出的 item 种类按整段 JSON 计入，不静默计零**——数小了的方向正是「说了装得下、发出去被拒」。

reasoning 的跳过**就是**一次静默计零，**就在**「数小了」的方向上，而且是这条路径上金额最大的一次。原文把两条并列写成「两处限定」，读者会以为它们互不冲突。应当写成：默认不静默计零，reasoning 是唯一的、有意的例外，代价是 X，补偿手段是 Y（而 Y 目前不存在，见 MAJOR-1）。

**其余文档核对结果：准确。** 逐条走过——共用塑形路径与翻译顺序（对，与 `handle()` 一致）；计数器按目标协议选的表（对）；`TranslatorNotFound` 仍给 400（对，见下）；`count_tokens.py` 的 `ProviderError` 规则「在这个调用点上现已整体不可达」（对，`upstream=ask_upstream if upstream_counts else None` 只在 ANTHROPIC 目标下传入，而那时 `require_endpoint` 必过）；「两次推翻的记录」（如实）；「尚未做」那一节（如实，且正是 MAJOR-1 该走的路）。**没有把未做的说成做了——唯一的例外就是 MAJOR-1 那句「交给 calibration 吸收」。**

---

## 逐条回答提问

**Q1 `estimate_responses_input` 的正确性 / 有没有真实形状被静默计 0。**
有，一种：`reasoning`（MAJOR-1）。其余覆盖是完整的。我实跑翻译器枚举了 Anthropic→Responses 出口的全部 item 形态：`message`、`function_call`、`function_call_output`、`reasoning`，外加一个容易被忽略的——**image 是顶层 item**，因为 `_item_from_block` 对 IMAGE 返回原始 Anthropic 块 `{"type":"image","source":{...}}`，而 `_input_from_messages:416` 的 `{"input_text","output_text","input_image"}` 白名单不含 `"image"`，于是它没有被塞进 message 的 `content` 而是独立成项。估算器的整段 JSON 兜底恰好接住了它（把 base64 全量计入，方向偏大）——Anthropic 侧 `estimators.py:41-42` 对 image 也是 `dumps(block.source)`，两边等价，**不是回归**。`server_tool_use` / `web_search_tool_result` 根本到不了出口（`BlockKind.UNKNOWN` → `_item_from_block` 返回 `None` 并记 `BLOCK_NOT_CARRIED`），不是估算器的问题。`instructions` 与 `tools` 都算了，`tools` 算的是翻译后带 `parameters` 的形状（对）。顶层未计的只有 `model` / `max_output_tokens` / `temperature` / `tool_choice`，量级可忽略。

**Q2 reasoning 不计入的类比。** 见 MAJOR-1：建模的类比成立，**补偿机制的类比不成立**，而低估量级实测为每个 item 5–12 KB 密文、一次会话几十个。

**Q3 `attempt.prepare` 挪到翻译之后。** 对的，两个订阅者在翻译腿上本来就该 no-op，且确实 no-op：`server_tools.py:271` 与 `blank_text.py:74` 都在函数体第一句 `if context.target_format is not WireFormat.ANTHROPIC_MESSAGES: return`，而 `target_format` 由 `apply_route` 在 `shape_request` 里就设好了，挪动位置不改变它。Anthropic 腿上的语句顺序与改动前逐字相同（`payload["model"]=` → `begin_attempt()` → 订阅者）。`begin_attempt()` 会 `dict(self.payload)` 快照，所以 attempt 记录现在存的是 Responses 形态——这与驱动的行为一致，是正确的。`EXPECTED_ON_ATTEMPT_PREPARE` 那条锁集合的测试仍绿，没有第三个订阅者。**没有订阅者因此改变行为。**
附带说明：变异「把发布点挪回翻译之前」全量测试全绿。这符合预期（今天没有可观测差异），我不要求为它加测试。

**Q4 calibration 键。** 兼容，不污染。详见 MINOR-6。

**Q5 `estimated: true` 的语义。** 作为契约够用——它诚实地说了「这不是测量」。但结合 MAJOR-1，这个数今天是「可见文本的裸 tiktoken 和」，因子恒为 1.0 且缺 reasoning。更该做的就是文档里已记为「尚未做」的那一件：从 Responses 回复的 usage 回喂 `learn("openai-responses", ...)`。我把它排在任何进一步打磨估算器之前。

**Q6 删除 `can_translate()`。** 安全。全仓（含 docs、tests、隐藏文件）`rg can_translate` **零命中**，无其他调用者。`embed-model` 那条 400 行为等价：异常类型同为 `TranslatorNotFound`（`registry.py:86` 抛出）、HTTP 状态同为 400（`handler.py:258-265` 早已包含该类型）、`provider.counted == []` 仍成立（新代码抛得更早，upstream counter 更不可能被调用）。`translate()` 在 `registry.py:101-102` 先解析 inbound 与 outbound 两半再执行任何一半，所以不存在「半程转换后才失败」。测试 `test_a_request_no_route_can_carry_is_refused_rather_than_estimated` 通过。唯一差异是异常文案，无人断言。

**Q7 测试分辨力。** 作者的变异结论**复核成立**（实测 2 条变红）。但见 MAJOR-2：新估算器本身零钉死，三种独立变异全绿。

**Q8 文档。** 见 MINOR-7 与上面的逐条核对。只有一处把未做的说成了做了。

---

## 「已知无关失败」的独立归因复核

**结论：该失败当前不复现，归因已过期。**

`tests/unit/test_translation_driver.py::test_a_domain_restriction_cannot_be_sent_and_is_recorded_rather_than_dropped_quietly` 在我复制的工作树上**通过**（`2 passed`，含同名 parametrize 的两条）。全量 `pytest tests` 也只有我自己排除 `refs/` 造成的那一条失败。

原因是并行会话在评审期间把那部分工作提交了（HEAD `3c5a337` → `002c248`，`translation_driver/{openai_responses,semantic}.py` 已不在未提交列表中）。作者当时的归因（同伴在途、`TranslationRefused` 从 `openai_responses.py:217` 抛出、实现 §3.4）与我读到的代码一致，**归因方式正确，只是被时间追上了**。不需要再当作已知失败携带。

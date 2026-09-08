---
report_id: local-tokenizer-code-audit
attempt_id: 260906-local-tokenizer-code-audit-a1d5011150f83176a
status: in-review
reviewed_at_rev: main ref 92ac5643985d0b28fb1d94bbce3d5eb24abcfc44；源码按下列工作树文件 SHA-256 快照审计
reviewed_at: 2026-09-06
---

# Local tokenizer 只读代码审计

## 评审范围

本次评审覆盖 `/home/xp/src/ghc-api-proxy-py` 当前主工作树中 local tokenizer 的实现、依赖、模型选择、校准与 fallback；`POST /v1/messages/count_tokens` 的完整生产入口；Anthropic Messages 直连与 Anthropic Messages→OpenAI Responses 翻译后的计数输入；OpenAI Responses prompt admission；direct buffered Chat Completions 当前实现及其 usage 路径；system、messages、tools、images、thinking、tool use/result、cache control、context editing 等结构在计数前后的变化；项目规则、living Spec 与 `docs/.human-controlled/` 对 token 数的合同。

明确不在范围内：不修改源码、测试、规格、Git 状态或既有文档；不调用真实 GHC／Copilot／Anthropic 凭据；不评审生成内容质量；不把未接线的未来 direct buffered Chat Task 3～8 当作当前实现；不把 OpenAI Responses 的本地单字段 prompt admission误称为完整 prompt token counter。

版本锚：主工作树 `.git/HEAD` 指向 `refs/heads/main`，其 ref 为 `92ac5643985d0b28fb1d94bbce3d5eb24abcfc44`。因隔离 worktree harness 拒绝对共享主工作树执行 `git -C /home/xp/src/ghc-api-proxy-py ...`，未取得可信的主工作树 dirty-state 清单；为避免把 commit 状态与工作树状态混写，关键源码另以 SHA-256 锚定：`estimators.py=94a75775770f951e75fc4785b2dd2a465fe82a55d5da4c977d362e327f462a48`、`worker.py=ea9fd9be7d5687cd02b150a1d922151cd927398637bf20a6b417ad6acc4ebb6d`、`calibration.py=6ee146a9cce47e0e8db6b435d4bfa8df5a3a07cd84712ccd426ba0630df207ec`、`admission.py=d50c5a051bc62b64f0b783c8236e24413fb0ceed3a231ddb460036d302f33283`、`count_tokens.py=8e7de51ddd15fea5413c7f914a2bad13779fa93fa63e87179cd25e3a3ee29d63`、`driver.py=0c50f5d71dfed57d4898663841630dcd2137033e70ccc1e3bc2ba850c772ea00`、`schema.py=f1b2e6eae490ad5bf6b60310a6b95449a83ba15db3479a563e83c2c377237690`、`chat_completions/state.py=815907ec12318371d169d2f03b84afa764c79a7abe4e29d4483316b841aa03dd`。

## 总体 verdict

**needs-fix。** 未发现 blocker；发现 8 个 major、4 个 minor。当前 happy path 与已有 98 个 tokenization unit tests 全部通过，但这些绿灯不覆盖模型级真实计数语义，且其中一项测试明确把会让 production count endpoint返回500的 `tiktoken` special-token行为固定为预期。

## 判据来源与权威顺序

1. `docs/.human-controlled/README.md` 规定人控文档是最终权威，既有内容若冲突须由用户重裁。
2. `docs/.human-controlled/api.md:5-10` 把 `POST /v1/messages/count_tokens` 列为受支持 Anthropic 端点；`:21` 只把运维 Tokenization 端点列为暂不支持，并未取消计数端点。
3. `docs/.human-controlled/config.example.yaml:65-72` 定义 `inbound.anthropic_count_tokens.providers`、`max_retries`，并把 `local` 明确定义为“本地 calibrated tiktoken 估算”。
4. `docs/.human-controlled/ghc-api.md:21-29` 把 Anthropic count endpoint放在 `direct_driver.anthropic_messages` 能力面；`message-translation.md:3-9` 要求翻译路径经过 IR、直连尽可能原样；`message-format-reshape.md:5-7` 明确请求整形同时适用于 `/messages` 与 `/messages/count_tokens`。
5. `.dev/docs/tui/spec.md:83-114` 定义计数请求的可观测合同：计数端点身份、最终 provider 与按发生顺序的尝试轨迹必须可读，`provider(ghc-failed,local)`、`provider(no-counter,local)` 与 `provider(local)` 语义不同。
6. `.dev/docs/error-envelope/spec.md:238-264` 禁止在上游 context-window error中把本地估算伪装成实测数字。
7. 项目 workflow要求 public behavior先有 living Spec。检索当前 `.dev/docs/` 未找到 token counting 的独立 living Spec；源码只引用一个当前不存在、且即使存在也已被用户判为过期的 `.dev/docs/archived-2604-rewrite/tokenization.md`。
8. 外部协议的独立 oracle使用 Anthropic官方《Token counting》《Thinking》《Vision》当前页面。官方 count endpoint按传入 model计数，支持 system、tools、images、PDF与thinking；Claude 4.7+使用新 tokenizer；context editing的 count返回 edit后 `input_tokens` 与 edit前 `context_management.original_input_tokens`。

## 当前实现地图

### 生产数据流

`server/routes/inference.py::_dispatch_after_body()` 解析入站 Anthropic JSON，可选剥 attribution，再调用 `pipeline/driver.py::handle_count_tokens()`。后者执行 routing、请求修复、必要的 Anthropic→Responses 翻译、resolved model替换、`attempt.prepare` subscribers，然后在选择任何 counter之前无条件调用 `LocalTokenWorker.estimate()`。Worker通过 `anyio.to_process.run_sync()` 在单容量 worker pool中调用 `estimate_anthropic_input()` 或 `estimate_responses_input()`。得到 raw estimate后，`pipeline/count_tokens.py::count_tokens()` 才按配置列表循环；任何非 `local` 名称都调用同一个闭包 `ask_upstream()`，`local` 则读取预先算好的 estimate，经 `(protocol, model)` calibration与 `local_estimate_multiplier` 后返回。

直连 Anthropic target的 upstream success会用 upstream `input_tokens` 教 calibration；OpenAI Responses target没有 count endpoint，所以永远只走本地 estimate。正常 inference response的 `usage` 不进入 calibration。

### 两个本地计数器不是同一机制

公共 count endpoint使用 `estimators.py` 的 whole-request estimate。OpenAI Responses inference的 `PromptTokenAdmission` 则只枚举已知 text-bearing fields，用 catalog指定 tokenizer的 `encode_ordinary()` 检查**单个字段**是否超过 `max_context_window_tokens`。它不累加字段、不执行 whole-prompt count、不使用 `max_prompt_tokens` 作阈值；遇到 image、encrypted reasoning、reduction control、未知 shape或未知 tokenizer时有意 fail-open。`tests/unit/tokenization/test_prompt_token_admission.py:78-99` 明确固定“fields are never added together”，所以本报告把它记录为窄 guard，而不是把它误判成实现错误。

### Direct buffered Chat Completions 与 usage

审计快照中不存在 `src/app/pipeline/delivery/buffered_transaction.py`；`.dev/docs/direct-buffered-chat-completions/status.md` 也声明 Task 1、2已集成、Task 3尚未开始。因此当前 direct `stream:true /chat/completions` 仍走 `one_shot_delivery()`，没有 local tokenizer调用。`chat_completions/state.py` 已能从 upstream Chat `usage.prompt_tokens`、`prompt_tokens_details.cached_tokens`、`completion_tokens` 与 `completion_tokens_details.reasoning_tokens` 形成 raw／exact／normalized usage，其中 normalized fresh input为 `prompt_tokens - cached_tokens`；这条 usage是 upstream事实，不是 local estimate。当前尚未接入的 Task 3～7不能被当作现有 buffered Chat usage delivery。

### 依赖与模型选择

`pyproject.toml:11-38` 只声明无版本下界／上界的 `tiktoken`；`uv.lock:1265-1273` 与当前环境均为 `tiktoken==0.14.0`。whole-request estimator把 tokenizer固定为 `o200k_base`，不读取 model id、provider catalog的 `capabilities.tokenizer` 或 model generation。Prompt admission另行读取 catalog tokenizer，但只接受 `o200k_base`，其它 tokenizer均 fail-open。`anthropic==1.4.0` 与 `openai==3.8.0` 也在 lock中，但 count production path通过 SDK raw `post()` 调 GHC，而不是使用 Anthropic SDK的 typed `messages.count_tokens()`。

## 发现

### LT-01：本地 estimator在 provider chain之前强制成功，能阻断本应优先的 upstream counter

- `finding_id`：`local-tokenizer-code-audit-01`
- `severity`：major
- `conclusion_strength`：confirmed，源码与 production-entry probe均已复现
- `primary_location`：`src/app/pipeline/driver.py:403-464`
- `related_locations`：`src/app/tokenization/worker.py:36-63`；`src/app/tokenization/estimators.py:77-104,151-181`；`src/app/pipeline/count_tokens.py:52-94`；`tests/unit/tokenization/test_local_token_worker.py:60-71`

**对不上之处。** `providers` 合同表示按配置顺序选择 counter，默认先 upstream再 local；实现却在进入 `count_tokens()` 之前无条件完成本地 estimate。即使配置只有 upstream、即使 upstream可以成功，本地 lookup／encode／worker failure都会提前结束请求。

**已观测反例。** 用 production test app配置默认 `ghc,local`，mock upstream固定返回 `{"input_tokens":42}`，请求正文只把用户文本设为 `<|endoftext|>`。当前 `encoding.encode()` 把它识别成禁止的 special token并抛 `ValueError`；HTTP结果为500 `proxy_internal_error`，`upstream_calls=0`。这不是“fallback失败”，而是优先腿从未获得执行机会。已有 unit test反而明确断言该 encode failure必须传播。

**误差／失效方向与触发条件。** 不是数值偏差，而是由可计数文本、encoding lookup failure、worker process failure或低 deadline触发的完全不可用；远端正确答案被本地辅助计算阻断。首次 worker／encoding冷启动也被强制置于 upstream前面。

**可证伪预测。** 把配置设为 `providers: [ghc]`，让 `local_token_worker.estimate()` 抛任意异常，同时让 provider返回42；如果实现正确，响应仍应为42。当前会在 provider call前失败。

**最小独立 oracle。** 用真实 HTTP handler＋两个独立 spies，一个计本地 worker，一个计 provider；断言 provider优先配置时 local failure不阻断 provider success，且 provider call count为1。不要让 expected由 `count_tokens()` 自己生成。

**建议。** Counter selection应先执行；只有选到 local时才要求 local estimate成功。若 upstream success后希望学习 calibration，本地 estimate失败应只跳过 learning，不得撤销 upstream answer。所有用户文本应使用 ordinary-text encoding语义，不能把 tokenizer的 reserved spelling当作非法请求。

### LT-02：image／PDF 的 base64 wire bytes被当作普通文本，官方样本已出现20.58倍高估，calibration clamp仍留下10.29倍

- `finding_id`：`local-tokenizer-code-audit-02`
- `severity`：major
- `conclusion_strength`：confirmed，公式、官方同一素材示例与本地复算形成异源对照
- `primary_location`：`src/app/tokenization/estimators.py:49-74`
- `related_locations`：`src/app/tokenization/estimators.py:107-149`；`src/app/tokenization/calibration.py:23-29,106-107`；`src/app/models/anthropic.py:12-24`；Anthropic官方《Vision》《Token counting》

**对不上之处。** Anthropic image token按解码后的图像 patch／尺寸计，不按 base64文本长度计；官方 count endpoint也明确支持 image与PDF。当前 Anthropic estimator对任何带 `source` 的 block执行 `dumps(block.source)` 后 `o200k_base.encode()`，因此把压缩文件字节的 base64表现当作 prompt文本。Responses estimator对未知 `type`，包括当前翻译产生的 top-level `image`，也 fallback到整个 JSON文本。

**实测。** 官方 token-counting文档的同一 `vision-example.jpg` 请求返回1028 tokens。读取同一张24,688-byte图片并按当前函数公式计算，local estimate为21,158，比例20.58倍。若这个 upstream样本进入 calibration，真实／估算比约0.0486，但 `FACTOR_CLAMP_MIN=0.5`，下一次 fallback仍为10,579，约10.29倍。高熵PNG、PDF或tool_result内嵌image会随压缩字节数线性放大，而真实visual tokens受像素尺寸与模型上限约束。

**误差方向与触发条件。** base64 image／PDF通常严重高估；压缩率越差、文件字节越多而尺寸不变，倍数越大。URL／file_id只按短字符串计，反而没有图像尺寸信息，方向不可确定。tool_result中的image同样进入list JSON序列化，触发同类问题。Translated Responses腿也会把image item整段JSON当文本，但该腿的精确比例必须用对应Responses模型usage裁决，不能借Claude视觉公式代替。

**可证伪预测。** 两张像素尺寸相同、视觉内容相同而编码压缩率相差很大的图像，官方Claude count应接近或相同；local estimate将近似随base64长度变化。对官方样本，任何修复后local estimate若仍在10k以上，仍未建模visual token语义。

**最小独立 oracle。** 对同一model向真实／录制的 `/v1/messages/count_tokens` 发送官方image样本，再与local estimator比较；Responses腿则以同model完成响应的upstream `usage.input_tokens` 作oracle，并用无图baseline做差。不能用tiktoken或本项目自己的serializer生成expected。

**建议。** Multimodal block不能进入文本tokenizer。若本地无法解码／取回图像或PDF并实现对应模型规则，应把该request标为local-unavailable并继续其它counter，而不是给出数量级错误的正整数。

### LT-03：Anthropic assistant thinking被无条件计为0，违反当前模型按model保留／计费的规则

- `finding_id`：`local-tokenizer-code-audit-03`
- `severity`：major
- `conclusion_strength`：confirmed，源码与官方model-specific规则直接冲突
- `primary_location`：`src/app/tokenization/estimators.py:49-60`
- `related_locations`：`src/app/models/anthropic.py:12-24`；`docs/.human-controlled/config.example.yaml:112-124`；Anthropic官方《Thinking》《Token counting》

**对不上之处。** `_anthropic_content_text()` 在 `assistant=True` 时跳过所有 `thinking` 与 `redacted_thinking`，不看model、不看它是不是当前tool-use turn、不看context editing。官方规则是：当前assistant turn thinking计入input；Opus 4.5及后续Opus、Sonnet 4.6及后续Sonnet等keep-all模型还把所有保留的prior-turn thinking当普通历史计入；较旧／Haiku模型才自动剥旧块。项目默认映射正把Opus／Sonnet aliases指向keep-all模型。

**实测。** 对同一请求加入600,000 characters的assistant thinking，当前 `estimate_anthropic_input()` 从19仍返回19，增量精确为0。只要thinking占输入主体，低估可以超过一个数量级；calibration factor上限3.0无法修复10×、100×的组成差异，而且同一model不同会话的thinking占比不同。

**误差方向与触发条件。** Direct Anthropic本地fallback在当前tool-use turn以及keep-all模型历史上向下偏；长agentic会话最严重。对last-turn-only模型的旧thinking，跳过可能正确，因此不能用统一“全算”替换统一“全不算”。`redacted_thinking`也必须遵守同一model／turn保留规则，而不是因为不可读就当不存在。

**可证伪预测。** 使用同一合法、未修改的真实thinking block与后续tool_result，对 `claude-opus-5` count前后差应显著大于0；当前local差恒为0。换到last-turn-only模型并把该块放到旧turn，官方差应消失或缩小，而当前结果不随model变化。

**最小独立 oracle。** 保存真实模型生成的合法thinking／signature块，分别对keep-all与last-turn-only模型调用官方count endpoint；比较同一请求移除该块前后的 `input_tokens`。这同时控制block合法性与model差异。

**建议。** 将保留策略作为model capability进入estimator；至少区分current tool-use turn、keep-all与last-turn-only。无法判定时应标local-unavailable或保守附带明确误差状态，不能返回无条件0增量。

### LT-04：Responses reasoning ciphertext与所有未知item按普通JSON文本计数，且该协议没有任何calibration来源

- `finding_id`：`local-tokenizer-code-audit-04`
- `severity`：major
- `conclusion_strength`：likely，代码机制已确认；数量级由源码自带的一次测量支持，但本审计没有重跑真实Responses replay
- `primary_location`：`src/app/tokenization/estimators.py:107-160`
- `related_locations`：`src/app/tokenization/estimators.py:151-181`；`src/app/tokenization/calibration.py:78-107`；`tests/unit/tokenization/test_responses_estimator.py:30-42`；`src/app/pipeline/translation_driver/reasoning_bridge.py:207-251,287-323`

**对不上之处。** `_responses_item_text()`只特判message、function_call与function_call_output；reasoning及所有未来item走 `dumps(item)`，把 `encrypted_content` 当普通文本。源码自己的测量写明，一个包含7,286-character encrypted content的7.6KB body由upstream报告为30 tokens；当前测试却只要求estimator增长至少为ciphertext的tiktoken数，把“非零”升级成“逐字计费”。本地探针对7,288-character高熵base64载体计算出4,964-token增量。

**误差方向与触发条件。** 带长 `encrypted_content` 的Responses历史、opaque carrier或含大opaque blob的未来item向上偏，现有点样本提示可能超过100×。普通未知可见文本被整段计数是保守方向，但把所有未知对象视为同一种ordinary text语义没有协议依据。

**为何不会被校准修复。** Responses route在 `handle_count_tokens()` 明确禁用upstream counter；全仓只有direct Anthropic count success与死代码service会调用 `calibration.learn()`。正常Responses inference usage不参与learning。因此 `(openai-responses, model)` factor永久停在1.0，除非外部state文件被非当前production路径写入。

**可证伪预测。** 用真实upstream生成的reasoning item作下一轮input；local estimate将随encrypted string长度近似线性增长，而upstream `usage.input_tokens` 的增量不会按该字符串的 `o200k_base` token数增长。若真实usage确实等于逐字token数，本finding的数量级判断应撤销，但“无calibration来源”仍成立。

**最小独立 oracle。** 对同一Responses model做两轮真实／cassette-backed请求：保留真实provider-issued reasoning item，再对下一轮记录actual request与最终 `usage.input_tokens`；用不含reasoning item的等价baseline做差。现有response cassette只证明output shape，不能冒充下一轮input计费。

**建议。** 为Responses estimator建立item-kind语义表，opaque state须由真实usage标定；在有可靠final usage时按target protocol／provider／model采样，或明确把local Responses count降级为不可用。不要用“未知一律JSON文本”替代协议事实。

### LT-05：context editing的count语义未闭合，local不执行edits，upstream正确返回的原始计数也被丢弃

- `finding_id`：`local-tokenizer-code-audit-05`
- `severity`：major
- `conclusion_strength`：confirmed，源码、官方合同与mock production probe一致
- `primary_location`：`src/app/pipeline/driver.py:417-487`
- `related_locations`：`src/app/tokenization/estimators.py:77-181`；`src/app/config/schema.py:412-417,484`；`docs/.human-controlled/config.example.yaml:500-517`；`src/app/pipeline/anthropic_request_hook.py:98-110`

**对不上之处。** 官方count endpoint在context editing启用时返回edit后的 `input_tokens`，并在 `context_management.original_input_tokens` 给出edit前值。Local estimator既不执行 `clear_tool_uses`／`clear_thinking`，也不返回双计数；production upstream path又把response body压成一个int，随后重建 `{"input_tokens":...}`，丢掉upstream的 `context_management`。另外，用户控制配置声明的 `context_editing.enabled/trigger/keep_tools/keep_thinking` 在production源码中没有任何consumer，只有schema定义。

**已观测反例。** Mock upstream返回 `{"input_tokens":25000,"context_management":{"original_input_tokens":70000}}`；production endpoint回答200但body只有 `{"input_tokens":25000}`。这不是展示裁剪，而是公开协议字段丢失。Local fallback在清理会移除大量tool result或thinking历史时会报告清理前近似值，方向向上且可超过一个数量级；若只启用未触发的edit，则应与原值相同。

**可证伪预测。** 配置 `hook_fix_anthropic_request.context_editing.enabled: clear-tooluse` 不会改变任何发往upstream的body；客户端自己带合法edit时，upstream额外返回的 `context_management` 也不会到达客户端。若这两项任一在当前production入口可观察到，本finding需相应收窄。

**最小独立 oracle。** 第一部分用captured outbound request对比开启／关闭配置；第二部分用strict mock返回完整count response并对client body做完整对象相等；第三部分用官方count endpoint对同一长tool history分别启用／禁用edit，比较post-edit与original counts。

**建议。** 先在living Spec明确proxy-owned edit配置和client-supplied edits各自责任，再让count与send共享同一实际request transform；upstream count response应按公开协议完整保留。Local若不能执行相同edits，应声明不可用并转下一腿。

### LT-06：`providers` 中的provider名称不选择provider，所有非local腿都重复调用routed provider并可能错标来源

- `finding_id`：`local-tokenizer-code-audit-06`
- `severity`：major
- `conclusion_strength`：confirmed，调用闭包与配置类型构成静态反例
- `primary_location`：`src/app/pipeline/driver.py:374-419,451-464`
- `related_locations`：`src/app/pipeline/count_tokens.py:52-94`；`src/app/config/schema.py:95-106,588-610`；`tests/unit/config/test_config_schema.py:204-215`

**对不上之处。** Schema与docstring明确每个非local条目是已配置 `model_providers` key，测试还固定部署可写 `providers: [B,local]`。实际 `handle_count_tokens()` 只从route取得一个 `provider`，再把唯一闭包 `ask_upstream()` 传给chain函数。`count_tokens()` 遍历A、B时调用的都是同一个闭包，却把成功结果标成当前字符串。

**误差／失效方向与触发条件。** 多provider配置下，指定B仍可能请求A；若A成功，日志／结果provider标为B；若A失败，A会按B的名义再被重复调用，B从未调用。模型、账号、catalog与tokenizer可能不同，数值方向不确定；尝试次数与延迟向上偏。

**可证伪预测。** 配置route provider A，count providers `[B,local]`，令A返回111、B返回222；当前响应为111且trace称provider B，B call count为0。

**最小独立 oracle。** 两个独立provider spies、不同固定响应、真实 `handle_count_tokens()` 入口；同时断言请求目标、调用次数、返回数字、`count_tokens_provider` 与attempt trail，不能只断言最终数字非零。

**建议。** Counter leg应携带实际provider object与其自有descriptor／route contract；如果产品意图其实是“任意非local字符串都表示routed provider”，应收窄schema与人控文档为枚举，而不是继续接受会说谎的名称。

### LT-07：Responses local count从未“calibrated”，且whole-request estimator忽略catalog tokenizer与模型代际

- `finding_id`：`local-tokenizer-code-audit-07`
- `severity`：major
- `conclusion_strength`：confirmed，learning调用面穷举＋官方model-specific规则
- `primary_location`：`src/app/tokenization/estimators.py:14,77-83,151-164`
- `related_locations`：`src/app/pipeline/driver.py:403-416,451-486`；`src/app/tokenization/calibration.py:41-107`；`src/app/model_provider/types.py:135-173`；`docs/.human-controlled/config.example.yaml:65-72`

**对不上之处。** 人控配置把 `local` 定义为calibrated tiktoken estimate。Direct Anthropic upstream success可以教 `(anthropic,model)` factor；Responses没有count endpoint，production又不从完成响应usage学习，因此 `(openai-responses,model)` 没有production learning source。与此同时whole-request estimator无条件用 `o200k_base`，虽然route descriptor已经携带catalog tokenizer，且官方Claude 4.7+也明确使用较旧模型不同的新tokenizer。同一个输入在新版Claude约多30%，说明model id不是可忽略参数。

**误差方向与触发条件。** Responses target始终是未经校准的 `o200k_base` 启发式；方向取决于模型与内容。Direct Anthropic在没有历史样本时也是raw heuristic，但成功remote counts能逐步校正。Calibration key没有provider、catalog generation、estimator版本或结构类别，升级 `tiktoken`／公式或同名model跨provider后仍复用旧factor；方向不定，clamp限制为0.5～3.0但不能使错误变正确。

**可证伪预测。** 清空state后连续完成任意数量Responses inference，再请求同model local count；calibration snapshot仍没有该protocol/model样本，数字不随actual usage改善。Catalog把tokenizer改成另一个合法名称时，whole-request local count仍逐字不变。

**最小独立 oracle。** 用固定请求集按model分别收集真实count endpoint或final upstream usage，冻结训练／验证样本，确认calibration样本真的由production链写入后再比较holdout误差。一个model的factor不得充当另一个model／provider／estimator版本的oracle。

**建议。** 先修合同措辞或补真正的Responses learning seam；whole-request estimator接受resolved descriptor中的tokenizer与版本化estimator identity，state key至少绑定实际provider/model/tokenizer/formula generation。

### LT-08：公开token-counting行为没有living Spec，关键合同沉在代码注释、测试与不存在的过期路径

- `finding_id`：`local-tokenizer-code-audit-08`
- `severity`：major
- `conclusion_strength`：confirmed，文档全集按相关关键词枚举
- `primary_location`：`docs/.human-controlled/config.example.yaml:65-72`
- `related_locations`：`docs/.human-controlled/api.md:3-10`；`.dev/docs/tui/spec.md:83-114`；`src/app/pipeline/driver.py:403`；`.claude/rules/00-development-workflow.md` 的Spec-first规则

**对不上之处。** 当前权威只规定端点存在、counter顺序、`local` 是calibrated estimate与日志呈现；没有living Spec定义local response shape、模型选择、结构覆盖、context editing、误差界限、calibration provenance、fallback failure、provider name语义或local estimate能否阻断upstream。实现注释引用 `.dev/docs/archived-2604-rewrite/tokenization.md`，该路径当前不存在，且项目memory已记录整个archived-2604-rewrite资料被用户判为过期。

**影响。** 上述行为差异无法由权威判断“该修代码还是改合同”，并已出现production与dead service不一致、配置接受多provider而执行不选择、官方response字段被裁掉等漂移。项目规则明确公共可观察行为必须先落living Spec；这是已发生的Spec bypass，不是文档美观问题。

**可证伪预测。** 若存在当前有效、被README或topic index指向的token counting living Spec，且逐项定义上述合同，本finding应撤销。当前对 `.dev/docs` 与人控文档的关键词枚举只找到散落条款，没有该authority。

**最小独立 oracle。** 从 `docs/.human-controlled/README.md` 与 `.dev/docs` topic入口出发，要求一名未读源码的实现者回答“image怎么数、thinking按哪个model规则、provider B如何选择、local failure能否阻断A、context editing返回什么”；若不能从一个命名authority得到唯一答案，则缺口成立。

**建议。** 新建living token-counting Spec前先让用户裁定真实产品分叉；不要从当前实现反推。把所有已确认事实、外部协议引用、fallback顺序、estimated标记、误差／unavailable语义与transcription tests归到该authority，并在revision record注明来源。

### LT-09：Anthropic tool history只计payload，忽略call identity与部分控制字段

- `finding_id`：`local-tokenizer-code-audit-09`
- `severity`：minor
- `conclusion_strength`：confirmed mechanism；真实平均误差未测
- `primary_location`：`src/app/tokenization/estimators.py:49-74`
- `related_locations`：`src/app/models/anthropic.py:12-24`；Anthropic官方count endpoint结构合同

`tool_use` block只序列化 `input`，不计 `id`、`name`；`tool_result` 只计 `content`，不计 `tool_use_id`、`is_error`；recognized-field均缺席的未来block可贡献0。真实常规ID／name较短，所以不能仅凭结构缺失宣称普遍数量级错误；但大量tool history或长合法identifiers会稳定向下偏，且calibration无法区分“长自然语言”与“高比例结构元数据”。

**可证伪预测。** 在其它字段固定时，只增长tool name／id／tool_use_id，local count不变；官方count若增长则缺口成立。若官方明确这些字段不进prompt，finding应撤销对应字段。

**最小独立 oracle。** 对真实model的count endpoint提交两组合法配对tool history，仅改变一个identifier长度，每次保留合法对应关系；比较delta。不要用我方serializer或estimator作expected。

**建议。** 建立按block type的显式计数字段表；未知类型应返回local-unavailable，而不是安静贡献0或任取第一个optional字段。

### LT-10：upstream `input_tokens: true` 被当成1并污染结果／calibration

- `finding_id`：`local-tokenizer-code-audit-10`
- `severity`：minor
- `conclusion_strength`：confirmed，Python类型规则直接决定
- `primary_location`：`src/app/pipeline/driver.py:428-436`
- `related_locations`：`src/app/tokenization/service.py:48-60`；`src/app/pipeline/chat_completions/state.py:2330-2343`

`isinstance(True, int)` 为真，且 `True > 0`，所以malformed upstream JSON会作为一枚token返回，并以 `real=1` 进入calibration。项目自己的Chat usage parser已正确使用 `isinstance(value,int) and not isinstance(value,bool)`，count path没有复用同一边界。

**可证伪预测。** Mock upstream返回 `{"input_tokens":true}`；当前client body会含boolean而不是fallback estimate，calibration revision增加。

**最小独立 oracle。** Strict JSON-schema／typed SDK response parser，加正控 `1` 与负控 `true`；两者必须分流。

**建议。** 使用 `type(counted) is int and counted > 0`，并把malformed response记录为该provider失败后按配置继续。

### LT-11：测试覆盖了一个production不可达的alternate service，并固定了与生产相反的字段保留行为

- `finding_id`：`local-tokenizer-code-audit-11`
- `severity`：minor
- `conclusion_strength`：confirmed，全仓引用枚举
- `primary_location`：`src/app/tokenization/service.py:21-88`
- `related_locations`：`tests/unit/tokenization/test_token_counting.py:44-137`；`src/app/tokenization/__init__.py:1-18`；`src/app/pipeline/driver.py:358-487`

`AnthropicTokenCountingService` 只被package export与unit tests引用，production `Chain` 不构造它。它会把upstream完整JSON原样返回，测试还用 `future: true` 断言字段保留；production path则只提取int并重建body，正是LT-05抓到的相反行为。`TokenizationSnapshotStore` 与 `preload_tokenizer()` 同样没有production consumer，但本finding的实际危害是dead service测试可绿而真实入口仍丢字段。

**可证伪预测。** 删除／破坏service的 `return data` 不会使任何production-entry test失败；修改production driver丢字段也不会使该future-field unit test失败。

**最小独立 oracle。** 从ASGI `POST /v1/messages/count_tokens` 走mock upstream future-field响应，断言完整client body；这条测试必须不导入 `AnthropicTokenCountingService`。

**建议。** 删除或明确归档alternate service，或让production统一使用一个owner；测试必须落在真实入口，尤其是response完整对象、provider chain与fallback。

### LT-12：`local_estimate_multiplier` 是未进入人控配置合同、且无上限的单向放大器

- `finding_id`：`local-tokenizer-code-audit-12`
- `severity`：minor
- `conclusion_strength`：confirmed
- `primary_location`：`src/app/config/schema.py:95-113`
- `related_locations`：`src/app/tokenization/scaling.py:1-9`；`src/app/pipeline/driver.py:438-444`；`docs/.human-controlled/config.example.yaml:65-72`；`src/app/config/bundled-config.yaml:1-7`

Schema接受任意有限 `>=1.0` multiplier并在calibration后向上取整；人控“完整配置样例”没有该键。它只影响local count response，不影响upstream count、learning或Responses prompt admission。默认1.0无问题；显式设置可以按任意数量级向上放大，属于operator-chosen方向，但当前没有权威文档说明该行为、作用域或上限。

**可证伪预测。** 通过环境变量设置 `...LOCAL_ESTIMATE_MULTIPLIER=1000000`，local响应精确放大约一百万倍，而inference admission不变；配置样例读者无法从人控文档发现这一旋钮。

**最小独立 oracle。** 配置加载＋真实count endpoint的完整响应，正控multiplier=1、反控multiplier=N，并确认upstream success不缩放、local fallback只缩放一次。已有测试覆盖数值行为，但不能替代用户对公开配置的授权。

**建议。** 先由用户决定是否把该键纳入人控合同及是否允许无上限；在裁定前不要把它当已批准的稳定接口。

## 结构建模矩阵

| 输入面 | 计数前实际变化 | Anthropic local estimate | Responses local estimate | 判断 |
|---|---|---|---|---|
| model | routing／mapping后替换为resolved model | model不参与tokenizer选择，只作calibration key | 同左 | 路由对象正确，tokenizer选择不随model |
| system | attribution可选剥离；direct保留blocks；translation合成 `instructions` string | text＋每block固定4；metadata忽略 | 最终instructions文本＋4 | translated腿测的是实际wire；direct cache metadata不影响缓存外总count，但模型系统开销只能靠校准 |
| messages/text | tool-pair repair、blank block、trailing assistant等subscriber先运行 | role＋拼接文本＋每message固定4 | message role／text＋每item固定4 | 主要文本存在，schema framing启发式且非model-specific |
| tools declaration | direct按subscriber清理；translation改成Responses tool shape | 整个tools JSON＋4 | 整个最终tools JSON＋4 | 覆盖较完整，但不是provider tokenizer的structured prompt算法 |
| tool_use/result history | repair pair后进入计数 | input／content被计，id/name/tool_use_id等漏掉 | call_id/name/arguments/output计入 | direct向下偏；translated覆盖更多 |
| images/PDF | direct保留；translation把image作为item | source JSON含base64被当文本 | image/unknown item整段JSON被当文本 | base64通常数量级高估；URL/file无尺寸语义 |
| thinking/redacted_thinking | 可能被sanitizer、carrier、model capability改写 | 所有assistant块无条件0 | reasoning item整段JSON，含opaque ciphertext | 两腿方向相反且都不按model规则 |
| cache_control | direct按mode保留／清理；translation system metadata与部分tool字段丢弃 | system/message marker基本不计，tools marker进入JSON | 只计实际留在final wire中的部分 | 官方count本来不执行缓存；marker忽略本身不是主要误差，cache usage不能从estimate推出 |
| context_management | `edits:null` 变 `[]`；实际edits保留 | edits不执行，仍数原历史 | crossing时作为extension丢弃并记录loss | direct local与官方post-edit语义不一致；proxy-owned配置未接线 |
| tool_choice／thinking config／output_config | subscriber与translation可改写 | 基本不计 | reasoning effort等top-level控制不计 | 通常小量，但不构成完整structured count |
| unknown block/item | Pydantic extra允许／translation可能保留或丢弃 | 只看text/content/input/source，否则0 | 整个JSON文本 | Anthropic倾向漏计，Responses倾向高估opaque数据 |

## 调用入口与输出用途清单

1. **Public count endpoint。** `/v1/messages/count_tokens` 唯一使用whole-request local estimate；remote success返回upstream数，fallback返回 `input_tokens`＋`estimated:true`。数字进入HTTP body与request trace的 `usage.input_tokens`，TUI用count provider标签区分来源。
2. **Calibration。** 只有Anthropic target的upstream count success会学习；prompt-limit error学习只存在于production不可达 `AnthropicTokenCountingService`。正常Messages／Responses／Chat completion `usage` 不学习。
3. **OpenAI Responses admission。** 每个正式attempt在final mutable preparation后执行独立 `PromptTokenAdmission`。它只阻断一个已知文本字段自身超过context window的情形；其它输入与aggregate budget交给upstream。Replay复用原admission observation。
4. **Anthropic Messages→OpenAI Responses count。** 先完整翻译与subscriber reshape，再用Responses estimator；不会调用upstream Anthropic count，因为目标协议没有counter。这个顺序本身正确，问题在estimator语义与无calibration。
5. **Direct buffered Chat Completions。** 当前没有local estimator调用。Chat state读upstream usage；未来buffered collector／observation仍应保持这个边界，不得拿local count填补absent usage。
6. **Budget／truncation。** Local whole-request count不驱动任何自动截断、context editing或输出预算。Prompt admission不做aggregate预算。客户端可能依据count response自行压缩／截断，因此错误数字仍有产品影响，但该动作发生在客户端，不在本代理。
7. **Persistence。** `(protocol, normalized model)` calibration与prompt-limit observations写入 `tokenization.json`，启动load、5秒周期flush、shutdown flush。SnapshotStore是另一套未接线设施。

## 数量级误差汇总

| 机制 | 方向 | 触发条件 | 已有证据权重 |
|---|---|---|---|
| base64 image／PDF按文本tokenize | 向上 | direct Anthropic image／document、tool_result image；translated Responses image item | 已确认，官方同样本20.58×；clamp后仍10.29× |
| Anthropic thinking全部跳过 | 向下 | current tool-use turn；Opus 4.5+／Sonnet 4.6+等keep-all历史 | 已确认机制与官方规则；长thinking可任意放大比例 |
| Responses encrypted reasoning整段JSON | 向上 | replay含长 `encrypted_content` 的reasoning item | likely；本地增量4,964，源码点样本报告全body 30，需真实replay复核 |
| context editing不执行 | 向上 | edit实际清除大量tool/thinking历史且local回答 | 已确认机制；精确倍率依真实edit结果 |
| unknown Anthropic block贡献0 | 向下 | 新合法block把大内容放在未识别字段 | 机制确认、现实shape未枚举，不足以声称当前常见 |
| explicit multiplier | 向上 | operator设置 `>1` | 已确认且无上限；属于显式配置，不是默认误差 |
| calibration跨shape／provider／版本复用 | 两向 | 同bucket混入结构误差样本、同名model跨provider、升级estimator | 已确认设计，实际幅度依样本；clamp为0.5～3.0 |

## 测试与证据

执行 `PYTHONDONTWRITEBYTECODE=1 .../.venv/bin/pytest --rootdir=/home/xp/src/ghc-api-proxy-py -p no:cacheprovider /home/xp/src/ghc-api-proxy-py/tests/unit/tokenization --quiet`，结果为98 passed in 47.52s。它证明当前unit suite与实现一致，不证明计数准确；image与thinking的whole-request estimator没有独立upstream oracle，Responses reasoning测试反而把逐字计ciphertext固定为期望。

执行production-entry special-token probe：mock upstream返回42，实际结果500且upstream call数0。执行production-entry context-management response probe：mock upstream返回post-edit 25000与original 70000，client只收到25000。执行官方image样本本地复算：21,158对官方1,028。执行600,000-character thinking增量probe：local 19→19。所有probe均只读源码／网络输入，没有修改仓库文件。

## 否决路线与理由

1. **否决“只因tiktoken看起来粗糙就判错”。** 人控合同明确允许calibrated tiktoken estimate；本报告只对可复现的结构语义、调用顺序、协议字段与model规则下结论。
2. **否决“用当前unit green证明准确”。** Expected多数来自同一estimator，或只检查正数／delta；dead service测试还与production字段行为相反。绿灯只作为回归现状证据。
3. **否决“用Responses output cassette证明reasoning input计费”。** 现有cassette记录output item与该轮usage，不是下一轮把该item作为input的计费；LT-04明确保留live replay oracle。
4. **否决“把Chat usage改成本地估算”。** 当前Chat usage来自upstream，local tokenizer没有资格填absent字段；二者用途与provenance不同。
5. **否决“把prompt admission没累加字段直接定为bug”。** 源码错误文案与测试明确把它限定为standalone-field context guard，而当前没有living Spec授权把它升级成total-prompt gate；本报告只记录边界，不替用户扩产品范围。
6. **否决“为完成审计调用真实有凭据的GHC”。** Image与thinking有官方独立合同，special-token与response裁剪可由production-entry mock证伪；只有Responses reasoning的真实计费仍需live／recorded replay，因此把该处降为likely而不冒充确认。
7. **否决“把 `usage` 当calibration输入”。** 当前production代码没有这条调用边；基于理想设计推断它会学习会把不存在的机制写成事实。
8. **否决“把 `.dev/docs/archived-2604-rewrite/tokenization.md` 当权威”。** 路径当前不存在，且项目memory明确该档案主题已被用户判过期。

## 搜索面与未覆盖面

源码完整读取／定位了 `app/tokenization/{estimators,worker,calibration,scaling,limits,state_store,snapshot_store,service,__init__}.py`、`pipeline/{count_tokens,driver}.py`、`server/routes/inference.py`、`config/{schema,provider}.py`、provider count实现、Anthropic／Responses translators与request subscribers、Chat usage state、相关模型类型和usage projection。测试覆盖了全部 `tests/unit/tokenization/`、count endpoint integration片段、translation／subscriber相关计数测试。依赖读取了 `pyproject.toml` 与 `uv.lock`。

规范读取了全部相关人控文档、direct buffered Chat topic的README／decisions／design／plan／status、direct passthrough与error envelope／TUI相关条款，并查阅当前官方Anthropic token counting、thinking、vision、context editing文档。

未执行真实GHC／Copilot／Anthropic请求；未跑全仓测试；未验证OpenAI／GHC对opaque Responses reasoning replay的当前计费；未审计archived source行为。上述缺口不阻塞其余结论，LT-04数量级判断保持likely。

CodeGraph MCP与CLI均在首次源码定位前尝试，`projectPath=/home/xp/src/ghc-api-proxy-py`；二者都报告“无index”。目录本身存在，但只含 `.codegraph/.gitignore`，故后续按工具回执改用绝对路径Read／rg，没有自行建索引。

## 我最没把握的三个判断

1. **LT-04的真实倍率。** 代码逐字计ciphertext与“Responses无learning源”是确认事实；upstream对真实replay carrier计多少仅有源码作者留下的点样本，本审计没有独立live replay，因此定为likely而非confirmed。
2. **LT-06的产品意图。** Schema、validator与docstring都把非local值定义为真实provider key，足以判当前执行不符合书面合同；若用户本意只是给routed provider起可观察标签，则应改合同而不是按本报告建议实现跨provider counting。
3. **aggregate prompt admission。** 当前行为显式只审单字段并由测试固定，缺少living Spec说明这是否就是全部目标；因此没有把“未使用 `max_prompt_tokens`／不累加”列为severity finding。

## 执行本契约时遇到的摩擦

- 首条shell调用已按要求输出 `pwd -P`。当前agent处于隔离worktree，harness拒绝对共享主工作树运行 `git -C /home/xp/src/ghc-api-proxy-py`，因此版本锚改用只读 `.git/HEAD`／ref与文件SHA-256，没有绕过限制。
- `/home/xp/src/ghc-api-proxy-py/.codegraph/` 目录存在但没有可用index；MCP与CLI都明确回执不可用。未运行 `codegraph init`。
- Web search服务不可用；官方资料改由WebFetch直读Anthropic当前文档。未把缓存skill文字本身当协议oracle。

## 来源

- [Anthropic Token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)
- [Anthropic Thinking](https://platform.claude.com/docs/en/build-with-claude/thinking)
- [Anthropic Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Anthropic Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)

## 交付声明

delivery_complete: true
completed_at: 2026-09-06
finding_total: 12
blocker: 0
major: 8
minor: 4
nit: 0

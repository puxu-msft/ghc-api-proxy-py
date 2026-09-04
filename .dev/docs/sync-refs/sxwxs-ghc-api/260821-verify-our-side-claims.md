# 对照报告中“我方已有／缺失”主张的源码核查

## 核查口径与总判定

核查基线固定为 `main` 的 `172adc26f129b6f96317ed94178c602f93777cb6`，源码从该 Git object 解出到只读临时快照后核对，未把当前工作树中的并行改动混入结论。入口 ground truth 是 `pyproject.toml:50-51` 的唯一 console script、`src/app/cli.py:22-23` 的 composition 与 app import，以及 `src/app/cli.py:134-169` 两种启动方式共同调用 `create_pipeline_app`。证据权重：强到可直接据此修订被核查报告；它证明的是该提交随项目入口启动的链路，不声称外部代码不能自行 import 仓库里的其他 app factory。

活链路前提 → **部分成立**。随项目 CLI 启动的确只有 `pipeline_app`；但“列出的 legacy 模块全都只被测试引用”不成立。`src/app/server/app_factory.py:13-38` 是一棵仍存在的生产模块图，直接引用 history、hooks、routes、runtime 与 upstream bootstrap，routes 又引用 legacy delivery／executor。正确说法是：“这些模块不在 `ghc-api-proxy` 的当前 CLI 启动图上；它们仍组成可被显式 import 的 dormant legacy app，并非文本意义上的‘仅测试引用’。”这一限定不改变下文只按活链路裁能力的口径。

优先结论：被核查报告最关键的错误是，活链路的 `response.completed`／`response.incomplete` **完全不读取 `response.output`，不能补回任何此前被跳过的事件或 item**。因此“未知事件继续跳过，因为终局会补回”的建议前提不成立。另有三处绝对表述错误：全仓并非没有 reasoning effort 映射；录制 provider 并非只有 transport 是替身；RequestLine／JSONL 不是对任意到达的 HTTP 请求都保证一行。

## 不成立与部分成立

### 2.1 未知事件、未知 output item 与终局补回

主张 → 活链路未知 output item type 一律放行并渲染成 text。判定 → **部分成立**。`src/app/pipeline/delivery/assembler.py:256-267` 在 `response.output_item.added` 为未知 type 建 draft，正常随后收到 `response.output_item.done` 时，`src/app/pipeline/delivery/assembler.py:295-321` 的最后分支确实产出 `{"type":"text","text":draft.text}`。但若未知 item 只在 `done` 出现而没有已开的 draft，`src/app/pipeline/delivery/assembler.py:279-294` 除 `web_search_call` 外直接返回空，连 text 都不会产出。正确说法是：“正常 `added → done` 生命周期中的未知 item 被猜成 text；缺少 `added` 的未知 item 被丢弃。”证据权重：强到可行动，分支是穷尽的。

主张 → 活链路未知事件类型静默忽略。判定 → **成立**。`src/app/pipeline/delivery/assembler.py:218-236` 枚举已知 Responses 事件后以 `return ()` 收尾，没有日志、loss 或错误。证据权重：强到可行动。

主张 → legacy 链路更严，并以 `unknown_output_item` 抛错。判定 → **部分成立**。更严这一层成立：未知事件或未知 item type 被 `src/app/openai/responses_stream_parser.py:173-223`、`src/app/openai/responses_stream_parser.py:225-280` 标为 `UnsupportedResponsesEvent`，随后 `src/app/delivery/anthropic_sse.py:650-658` 抛 `unsupported_responses_event`。但报告点名的 `unknown_output_item` 不是这个错误；它只用于某事件引用一个从未打开的 `output_index`，见 `src/app/openai/responses_stream_parser.py:915-924`。正确说法是：“legacy 对未知事件／item type fail-closed，但错误码是 `unsupported_responses_event`；`unknown_output_item` 是生命周期关联错误。”证据权重：强到可行动。

主张 → 活链路终局合并会从 `response.completed`／`response.incomplete` 的完整 `output` 补回流中未见 item。判定 → **不成立**。`src/app/pipeline/delivery/assembler.py:323-340` 的 `_read_terminal` 只读 `usage`、`incomplete_details.reason` 并设置 `seen`／`stop_reason`；它从未读取 `response.output`，也不创建、关闭或交付任何 draft。`src/app/pipeline/delivery/stream.py:266-294` 在事件循环结束后只 flush 已经交给 `DeliverySession` 的 block，再发送 terminal frames，没有第二次 response-body 对账。正确说法是：“终局只补 terminal metadata，不补 content；被未知事件跳过的内容不会回来。”因此 §2.1 与 §6 动作 2 中“未知事件维持跳过”的理由错误；在实现真正的终局 output reconciliation 前，不能以可恢复性为由 blanket fail-open。证据权重：强到应立即修订建议，调用路径完整且无其他终局 reader。

### 1.4 录制 provider 是否只有 transport 是假的

主张 → `recorded_provider.py` 中只有 transport 是假的。判定 → **部分成立**。`tests/int/recorded/recorded_provider.py:49-51` 的确只用 `ReplayTransport` 替换网络，`tests/int/recorded/recorded_provider.py:61-79` 也确实构造真实 `GhcApiClient`、OpenAI／Anthropic SDK、`CopilotTokenManager` 与 `GithubCopilotProvider`。但 `tests/int/recorded/recorded_provider.py:35-42` 还定义了明确“stands in for”的 `RecordedTokenSource`，返回固定 GitHub token 且 refresh 恒为 `None`；`interaction_id` 和 SDK API key 也使用测试常量。正确说法是：“provider、SDK、token manager 与 cassette 中的 token exchange 都是真实代码；网络 transport 与 GitHub token source 是测试替身。”证据权重：强到可直接修正文案。

### 2.2 翻译损失与每请求 JSONL

主张 → `context.extras["conversion_losses"]` 与 `context.extras["response_conversion_losses"]` 全仓没有读者。判定 → **成立**。固定 HEAD 的全仓 Python identifier 搜索只得到 `src/app/server/handler.py:116-125`、`src/app/server/handler.py:199-207` 与 `src/app/server/handler.py:406-413` 三个写点；`context.extras` 的生产读点只读取 count-token keys，见 `src/app/server/pipeline_app.py:345-362`，也不存在遍历或整体序列化 `extras` 的间接出口。证据权重：强到可行动，搜索覆盖 `src/` 全部 Python 文件并额外排除了 generic iteration／reflection surface。

主张 → `RequestLine` 已经每请求写一行 JSONL。判定 → **部分成立**。每个到达 `_log_completion` 的请求都会在 `src/app/server/pipeline_app.py:205-244` 构造一个 `RequestLine` 并调用 `write_request_record`；`src/app/observability/request_log_file.py:31-49` 正常时向当日 JSONL append 一个对象。但这不是不可失败保证：写函数明确捕获所有异常并返回 `None`，且 `src/app/server/pipeline_app.py:271-281` 在 `_dispatch` 抛出 `BaseException` 时只移除 active request 后重抛，不写 completion；未注册路径也按 `src/app/server/pipeline_app.py:289-292` 的边界由 FastAPI 自己回答而不进入该记录路径。正确说法是：“每个正常完成并到达 completion accounting 的已注册代理请求 best-effort append 一行；写盘失败、dispatch 异常和路由外请求没有这项保证。”证据权重：强到可直接修正文案。

### 2.3 thinking 与 reasoning effort

主张 → 活链路的 `thinking` 进入 `extensions`，跨格式时被整体清空。判定 → **成立**。Anthropic reader 的 `_PASSTHROUGH_KEYS` 不含 `thinking`，见 `src/app/pipeline/translation_driver/anthropic_messages.py:31-33`、`src/app/pipeline/translation_driver/anthropic_messages.py:141-145`；跨到 Responses 时 `src/app/pipeline/translation_driver/semantic.py:116-128` 记录 `EXTENSIONS_NOT_CARRIED` 并返回空 dict，`src/app/pipeline/translation_driver/openai_responses.py:704-738` 没有另行提取 `thinking`。证据权重：强到可行动。

主张 → 全仓没有 `reasoning_effort` 相关映射。判定 → **不成立**。全仓在 `src/app/models/capabilities.py:18`、`src/app/anthropic/client.py:320` 有 `reasoning_effort`，而 legacy converter 已有完整 `thinking` budget → explicit effort 映射：能力事实定义在 `src/app/protocols/anthropic_responses.py:60-100`，转换与范围校验在 `src/app/protocols/anthropic_responses.py:251-351`。正确说法是：“活链路 translation driver 没有 reasoning effort 映射；legacy 链路已经实现并测试了这项能力。”所以“当前活路径完全没落地”成立，“全仓 grep 无命中”和把它描述为项目从未实现过则不成立。证据权重：强到可直接修正文案。

### 2.4 工具 description 与注入计费文本

主张 → 我方是否已经处理工具 `description == ""`。判定 → **不成立**，即活链路尚未处理。`src/app/pipeline/translation_driver/openai_responses.py:126-141` 只把 `input_schema` 政名为 `parameters`，其余字段原样保留；因此空 `description` 原样进入 Responses tool。仓库里能找到的另一套 converter 也只是“非 `None` 就写”，见 `src/app/protocols/anthropic_responses.py:534-555`，同样不把空串改成替身或省略。正确说法是：“缺席会保持缺席，空串也保持空串；没有针对 Copilot 拒空 description 的 active repair。”证据权重：强到可行动。

主张 → 我方是否已经剥离 system 中以 `x-anthropic-billing-header:` 开头的客户端注入文本。判定 → **不成立**，即活链路尚未处理。`src/app/pipeline/anthropic_request_hook.py:146-193` 的 active pre-translation fixup 只处理 context management、tool pair 与 thinking layout；system blocks 在 `src/app/pipeline/translation_driver/anthropic_messages.py:115-145` 原样读入，并由 `src/app/pipeline/translation_driver/openai_responses.py:110-123` 原样拼接。`src/app/config/settings.py:93-105` 的同名 blacklist 是 dormant legacy 的 **HTTP request header** 配置，不是 system 文本过滤，也不在当前 CLI 配置模型上。正确说法是：“active path 没有该 system-text stripping；不要把 legacy HTTP header blacklist 误认成同一机制。”证据权重：强到可行动。

### 2.5 上游 function call arguments 的 JSON 解析

主张 → 活链路会不会静默接受重复键或非对象 function arguments。判定 → **成立（缺口存在）**。流式路径在 `src/app/pipeline/delivery/assembler.py:296-303` 调 `_decode_json`，后者于 `src/app/pipeline/delivery/assembler.py:375-380` 使用 `orjson.loads`；非流式 response translation 在 `src/app/pipeline/translation_driver/openai_responses.py:331-339` 调 `_decoded_arguments`，后者于 `src/app/pipeline/translation_driver/openai_responses.py:398-409` 使用标准库 `json.loads`。两者都不检查结果必须是 object，也不使用 duplicate-key hook。对固定依赖环境的直接探针显示，两者对 `{"x":1,"x":2}` 都得到 `{"x":2}`，对 `[]`、`1`、`null` 分别得到 list、int、`None`；这些值随后成为 Anthropic `tool_use.input`。畸形 JSON 的行为也不严格：streaming 包成 `{"__raw": raw}`，buffered 保留原字符串。证据权重：强到可直接采纳严格解析修复；源码与运行探针一致。

### 2.8 重试 headers、流式 Response 读取与退避静默

主张 → 活链路重试复用同一个 headers dict。判定 → **不成立**。`src/app/pipeline/direct_driver/base.py:126-146` 每轮都重新走 provider send；`src/app/ghc_client/client.py:46-66` 每次 send 都重新取当前 token 并构造新 dict，`src/app/ghc_client/client.py:68-98` 每次 post 都重新 await `request_headers`；`src/app/ghc_client/headers.py:35-47` 每次生成新的 request id。正确说法是：“active model-request retry 会重建 headers、重读 token，并生成新的 `x-request-id`；只复用 `context.client_headers` 这个只读输入映射，合并结果仍是新 dict。”证据权重：强到可排除报告暗示的缺口。

主张 → active httpx 流式响应不存在 `.text`／`.read()` 读取路径。判定 → **不成立**。成功的 streaming body 确实只由 `src/app/server/pipeline_app.py:401-441` 的 `response.aiter_bytes()` 消费，没有 whole-body read；但 SDK 对 stream request 抛 status error 后会走 `src/app/ghc_client/client.py:100-114` 的 normalization，而 `src/app/ghc_client/errors.py:62-77` 对 error response 访问 `response.text`。正确说法是：“成功流没有 `.read()`／`.aread()`；stream=True 的 HTTP error response 存在 `.text` 属性读取路径。”这条访问是否吸流取决于 SDK 在构造 status exception 前是否已消费 error body；httpx 自身对未读流的 `.text` 会抛 `ResponseNotRead`，所以不能把它直接写成‘必然吸干成功 SSE’，但路径本身必须登记。证据权重：静态路径存在这一结论强到可行动；具体 SDK error-body 状态是版本相关事实，需用所锁版本单独测量后才能判断故障后果。

主张 → 重试退避期间是否静默。判定 → **部分成立，且确有客户端静默窗口**。`DirectDriver` 的 funded retry 本身在 `src/app/pipeline/direct_driver/base.py:197-219` 立即返回下一轮，没有指数 backoff；但 429／502 会让 `RateLimiter.observe_failure` 设置下一次允许时间，见 `src/app/pipeline/rate_limiting.py:157-175`，下一轮在 `src/app/pipeline/rate_limiting.py:130-138` sleep。这个等待发生在 `src/app/pipeline/direct_driver/base.py:135-141`、成功 response 尚未交给 `pipeline_app` 之前，client-facing `stream_delivery` 还没创建，因而不会发 SSE ping。token exchange 自身也在 `src/app/ghc_client/tokens.py:123-158` 做 1／2 秒退避，同样位于 response 前。正确说法是：“普通 network／5xx replay 没有 driver-level backoff；rate-limit pacing 与 token exchange retry 有 sleep，期间活链路不向客户端保活。”证据权重：强到可行动。

### 2.8.4 与 3：InFlightLimit 和无读超时长连

主张 → `InFlightLimit` 超限排队而非拒绝。判定 → **成立**。`src/app/server/admission.py:25-49` 用 `asyncio.Semaphore` 包住 app 调用，注释与实现都明确 wait；`src/app/server/pipeline_app.py:602-615` 把它装在活 app 上。证据权重：强到可行动。

主张 → 活链路存在“不设读超时的长连”路径。判定 → **不成立**，至少在固定提交与锁定依赖的默认构造下没有。项目自己的 `stream_idle` 默认 0，见 `src/app/config/schema.py:146-152`，但这只关闭额外的业务 idle guard，不等于 httpx 没有 read timeout；provider SDK 由 `src/app/server/composition.py:316-346` 构造，固定环境探针显示 OpenAI 与 Anthropic SDK 对共享 httpx client 实际使用 `Timeout(connect=5.0, read=600, write=600, pool=600)`。此外默认 attempt 总 deadline 是 1200 秒，见 `src/app/config/schema.py:146-152`，并由 `src/app/pipeline/direct_driver/base.py:126-132` 与 `src/app/server/pipeline_app.py:409-431` 覆盖 response headers 与 streaming body。正确说法是：“额外 stream-idle guard 默认关闭，但 SDK read timeout 为 600 秒，且默认 whole-attempt deadline 为 1200 秒；这不是无读超时长连。”若 operator 显式把 attempt deadline 设为 0，read timeout 仍存在，只是不再限制持续有数据的总时长。证据权重：对当前锁定 SDK 版本强到可排除该类比；升级 SDK 后应重测 runtime timeout，而不能只看 composition 未显式传 `timeout`。

### 4.2 “有配置面无消费者”抽查

主张 → 至少五处配置／机制表面没有活链路生产行为消费者。判定 → **成立，但 continuation 的“零读者”措辞需要收窄**。本次抽查了八类，并同时搜索了固定字段、调用符号、generic `getattr`／`model_dump`、注册表与 Python entry point；当前项目没有按这些配置字段名做字符串反射或 entry-point 注册。证据权重：以下每项都强到可作为当前提交的 wiring 事实，不支持据此直接删定义。

1. continuation → **有效行为无消费者，但不是字面零读取**。`RetryLedger.limit_for` 在 `src/app/pipeline/retry.py:74-86` 确实读取 continuation 配置；然而唯一会产生 continuation verdict 的 `decide_stream_ending` 位于 `src/app/pipeline/retry.py:139-178`，全 `src/` 无调用方，`continuation_messages` 于 `src/app/pipeline/retry.py:108-120` 也无调用方，活流终止直接在 `src/app/pipeline/delivery/stream.py:275-288` 发 error。正确说法是：“配置分支存在并可被单测调用，但 active stream-ending path 永远不请求 `RetryReason.CONTINUATION`，所以配置不影响生产行为。”
2. hedge → **成立**。`threshold_sec`／`max_secondary_candidates` 只在 `src/app/config/schema.py:213-216` 定义；全 `src/` 无读取，driver 只构造单个 provider send。
3. `model_refresh_interval` → **成立**。字段在 `src/app/config/schema.py:83-95`；活链路只在 startup 从 `src/app/server/pipeline_app.py:649-655` 调一次 `refresh_catalogs`。同名周期读取只存在 dormant `src/app/server/app_factory.py:105-109` 的旧 settings 链。
4. `CopilotTokenManager.run_refresh_loop` → **成立**。循环定义在 `src/app/ghc_client/tokens.py:89-103`；活 lifespan `src/app/server/pipeline_app.py:656-671` 只启动 tokenization flush，唯一 production `start_soon(run_refresh_loop)` 位于 dormant `app_factory`。活链仍有 `get_token()` 的同步惰性刷新，所以正确缺口是“无后台刷新”，不是“token 不刷新”。
5. `config.hooks` 六点 → **成立**。六字段只在 `src/app/config/schema.py:273-285` 出现；活 composition 于 `src/app/server/composition.py:394-410` 只注册硬编码 builtin subscribers，没有字段名反射、hook loader 或 entry point。代码注释把某些硬编码位置称作同名 spec moment，不等于消费 operator 的 `config.hooks` 列表。
6. `history.enabled`／`--history` → **成立，按 runtime effect 口径**。字段在 `src/app/config/schema.py:269-270`、`src/app/config/schema.py:379-380`，CLI option 在 `src/app/cli.py:212-239` 并进入 config loading，但 `create_pipeline_app` 的 runtime 没有读取 `chain.config.history`；`src/app/server/ops_routes.py:1-10` 还明确 active chain 不拥有 History。它不是“解析层零消费者”，而是“生产行为零消费者”。
7. `/metrics` 业务指标 → **成立但须保留限定**。active route `src/app/server/ops_routes.py:74-76` 会导出全局 Prometheus registry，所以 endpoint 不是空、默认 process／Python collectors 仍可能出现；但 active composition 没有建立 `RequestTelemetry`，该类只在 `src/app/observability/telemetry.py:18` 定义并由 dormant app factory 的 setup 路径使用。正确说法是：“有 registry endpoint，无 active proxy-request business instrumentation。”
8. systemd `LISTEN_FDS` parser → **成立，限定到 classmethod**。`ActivatedSocketSet` 类型本身被 active listener code 使用，见 `src/app/lifecycle/listener.py:22-105`；无生产调用方的是 `ActivatedSocketSet.from_systemd_environment`，定义在 `src/app/lifecycle/activation.py:63-103`。当前 systemd 入口通过 CLI `--fd` 走 `src/app/cli.py:134-152`，不是环境协议解析。不要把整个 activation module 都说成没用。

### 6 动作 8：image 与 document

主张 → image block 原样透传、形状不匹配；document 静默丢弃。判定 → **部分成立**。Anthropic reader 在 `src/app/pipeline/translation_driver/anthropic_messages.py:102-104` 将 image 标为 `BlockKind.IMAGE`、其他类型包括 document 标为 `UNKNOWN`。Responses writer 对 image 在 `src/app/pipeline/translation_driver/openai_responses.py:454-466` 返回原始 dict，随后 `src/app/pipeline/translation_driver/openai_responses.py:416-438` 只把 `input_image` 等已知 type 放进 message content；原始 Anthropic `type: image` 因而成为 top-level item，确实是原样但 shape 错位。document 走 unknown 分支，在 `src/app/pipeline/translation_driver/openai_responses.py:481-493` 记录 `BLOCK_NOT_CARRIED` 后返回 `None`。所以“丢弃”成立，“静默”只在运行观测层成立：转换层明确记了 loss，但该 loss 又因 §2.2 的无读者而没有日志／JSONL／响应出口。正确说法是：“image 原样错误透传；document 被有记账地丢弃，但记账对运行时消费者不可见。”证据权重：强到可行动。

## 成立项

### 1.1 output_index 键

主张 → `_item_key` 优先使用 `output_index`。判定 → **成立**。`src/app/pipeline/delivery/assembler.py:238-254` 先检查 `output_index`，只有缺失时才 fallback 到 `item.id`／`item_id`。证据权重：强到可沿用。

### 1.2 client-facing LastWrite

主张 → `_LastWrite` 读客户端侧，且在 `yield` 返回后打戳。判定 → **成立**。`src/app/pipeline/delivery/stream.py:40-46` 定义共享的 client last-write 时间；`src/app/pipeline/delivery/stream.py:154-165` 只从它计算 keepalive deadline；唯一交付出口在 `src/app/pipeline/delivery/stream.py:168-202`，先 `yield chunk`，生成器恢复后才更新 `last_write.at`。证据权重：强到可沿用。

### 1.3 reasoning carrier 严格解码

主张 → canonical base64url 往返校验、拒重复键、键集恰好相等。判定 → **成立**。canonical alphabet、strict decode 与 re-encode equality 在 `src/app/pipeline/translation_driver/reasoning_carrier.py:132-142`；duplicate-key hook 在 `src/app/pipeline/translation_driver/reasoning_carrier.py:145-151`；project payload 用 hook 解析并检查 exact field set 在 `src/app/pipeline/translation_driver/reasoning_carrier.py:103-119`。证据权重：强到可沿用。

### 2.4 tool pair 双向删除

主张 → `repair_tool_pairs` 同时删除无人应答的 `tool_use` 与无来源的 `tool_result`。判定 → **成立**，且落在活链路上。两向删除分别在 `src/app/pipeline/anthropic_request_hook.py:102-123`；`src/app/pipeline/anthropic_request_hook.py:156-169` 每次 fix 都调用它；`src/app/server/handler.py:95-110` 在 Anthropic body 翻译前从 active `shape_request` 调 `fix_anthropic_request`。证据权重：强到可沿用。

### 2.6 reasoning 九态与活／legacy 差异

主张 → `decode_reasoning_carrier` 返回九态。判定 → **成立**。九个 `Literal` 分类在 `src/app/pipeline/translation_driver/reasoning_carrier.py:22-32`，`src/app/pipeline/translation_driver/reasoning_carrier.py:77-100` 覆盖并返回每一态。证据权重：强到可沿用。

主张 → 活链路 `_reasoning_from_signature` 把九态塌缩为 foreign／其余二分。判定 → **成立**。`src/app/pipeline/translation_driver/anthropic_messages.py:50-64` 只特判 `foreign`，其余八态都成为 `PROXY_CARRIER`，畸形和 unknown version 没有 loss。证据权重：强到可行动。

主张 → legacy 在同一位置分得更细。判定 → **成立**。`src/app/anthropic/thinking/responses_reasoning.py:92-120` 对 unknown version、两种 malformed 与 foreign 返回无 item，并保留 classification／malformed flag；合法载体才重建 reasoning item。证据权重：强到可行动。

### 2.9 错误 status 与 synthesized headers 默认值

主张 → `error_status` 透传 `UpstreamRejected.status_code`。判定 → **成立**。`src/app/server/handler.py:325-357` 明确返回 `error.status_code`；异常类型在 `src/app/pipeline/exceptions.py:60-83` 保存该值。证据权重：强到可沿用。

主张 → `synthesized_response_headers_after_sec` 默认 240。判定 → **成立**。默认值在 `src/app/config/schema.py:258-266`，active adapter 在 `src/app/server/handler.py:491-499` 读入 `StreamSettings`。证据权重：强到可沿用。

## 最终裁断

被核查报告关于我方的基础盘点多数方向正确，但至少五处会改变动作优先级或建议内容：终局不能补回未知事件；active stream error 确有 `.text` 路径；retry pacing 会制造 pre-response 静默；全仓已有一套 dormant reasoning effort 映射；image／document 的实际状态分别是“错误 shape 透传”与“有 loss 记账但无出口”。这些结论证据强到应在采用动作清单前先修订原报告，尤其不能按现有 §2.1 直接保留未知事件 fail-open。

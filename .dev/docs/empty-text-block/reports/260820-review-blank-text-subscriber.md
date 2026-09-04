# `4f2d786` 独立代码评审

## 结论

判定：**0 个 blocker，1 项应改，1 项建议，1 项不同意但可接受。** 实现落点、Anthropic leg 门控、thinking 分隔符算法、旧落点清理和关键测试均成立。唯一应改项是订阅者顺序的书面理由与实际代码不符；它不影响当前行为，但不应作为冻结顺序的依据。

证据强度：**足以据此处理。** 我以提交 `4f2d786` 的 Git object 为被评审源码，沿 CLI 生产入口、路由、翻译、subscriber dispatch 和 provider send 调用链静态核对；当前 `HEAD be87f59` 中同伴后来加入的 `_flatten_history` 只用于核验用户指定的顺序理由，不把该提交或工作树增量的问题归到 `4f2d786`。用户已提供并完成的测试、Ruff、Pyright 和 mutation 结果按原范围沿用，没有重复运行。

## 发现

### 应改：冻结顺序的理由是错误事实

- 位置：`src/app/pipeline/subscribers/__init__.py:14`。
- 判定：该行称 `builtin:server-tool-capability` “can produce” 空或纯空白 text，因此 blank-text subscriber 必须在它之后。这个理由不成立。
- 依据：在被评审提交 `4f2d786` 中，`src/app/pipeline/subscribers/server_tools.py` 尚无 `_flatten_history`，subscriber 只编辑 `tools` 和 `tool_choice`，根本不生成 text block。当前 `HEAD be87f59` 后加的 `_flatten_history` 也不会生成空白 text：`src/app/pipeline/subscribers/server_tools.py:129-143` 对结果为空使用非空的 `[{family} results omitted]`，`src/app/pipeline/subscribers/server_tools.py:146-160` 即使 query/URL 为空也只返回空后缀，`src/app/pipeline/subscribers/server_tools.py:175-204` 始终在该后缀前放入非空的 `[{family}]`，或使用前述非空结果文本。
- 影响：当前注册顺序本身无行为缺陷；错误在于用不存在的 failure mode 冻结并解释顺序。后续维护者可能把这条虚构依赖当成不可更改的不变量。
- 建议处理：保留现有先后顺序可以，但把理由改成事实，例如“producer/normalizer 先于最终 sanitizer，便于以后新增 text 生成逻辑时仍由最后一道 sanitizer 收口”；不要继续声称当前 flatten 会产生空文本。若不想确立这种面向未来的约定，则如实写成当前两者无数据依赖、注册顺序仅用于确定性。

### 建议：补住 lookahead 算法真正承载的边界

- 位置：`src/app/pipeline/subscribers/blank_text.py:47-66`；现有测试仅覆盖 `tests/unit/test_blank_text_blocks.py:93-117` 的单个夹心 blank。
- 判定：实现目前正确，但测试没有锁住用户重点询问的多 blank 与边界形态。
- 依据：对 `[thinking, blank, blank, thinking]`，第一个 blank 在 `:61-65` 插入一次 separator，第二个 blank 因 `kept[-1]` 已是 separator 而不再插入；`[blank, thinking]` 因 `kept` 为空只删除 blank；`[thinking, blank]` 因 `following is None` 只删除 blank。因此每一段夹在两个 thinking survivor 之间的连续 blank 最多产生一个 separator，首尾 blank 不产生 separator。
- 建议处理：为这三种形态加一个小型参数化测试。它直接保护非平凡 lookahead 与“只插一次”性质，不是追求覆盖率。若以后确有长 content list，再把 `content[index + 1:]` 的反复切片改成按 blank run 单遍处理；当前规模下没有性能性应改项。

### 不同意但可接受：全空 message 的理由说得过强

- 位置：`src/app/pipeline/subscribers/blank_text.py:109-112`；对应测试 `tests/unit/test_blank_text_blocks.py:81-90`。
- 判定：保留全空 message、让 upstream 报原始错误，是可以接受的保守产品选择；但“删除会破坏按位置配对，tool_result 又引用前一轮 tool_use”并没有证明删除这个全空 turn 必然破坏历史。
- 依据：该 message 既然只有 blank text，本身不含 `tool_use` 或 `tool_result`；tool 关联还具有显式 ID，不是单靠列表下标。删除 turn 的确可能改变相邻 role 边界，且只有一个 message 时会留下可能无效的 `messages: []`，所以不能无条件删除，但现有注释给出的必然性因果过强。
- 建议处理：无需因此改行为。把理由收窄为“没有经过实测、对所有历史形态都语义等价且有效的替代；删除 turn 可能改变 role 边界，清空 content 又必然无效，因此保留原输入并暴露原错误”。这会准确表达保守边界。该例外也意味着模块开头 `src/app/pipeline/subscribers/blank_text.py:1-5` 的“removed/catches such a block whoever produced it”不是无条件全称，最好同时注明 all-blank message 例外。

## 逐项核对

### 1. 落点与路径完整性：通过

- `src/app/server/handler.py:65-113` 在 inbound hook 后完成 route 和必要翻译，再构造 endpoint-bound driver；因此 `context.target_format` 与 `context.payload` 已是实际出站格式。
- `src/app/pipeline/direct_driver/base.py:130-136` 先发布 `attempt.prepare`，随后重新从 `context.payload` 取快照，再进入 rate limiter 和 `_send`；`src/app/pipeline/direct_driver/base.py:226-233` 的 provider send 之间没有其他 payload rewrite hook。故它是普通请求发往 upstream 前最后一个可扩展改写点。
- `src/app/server/composition.py:218-226` 把 built-ins 注册进生产 chain 并冻结；`src/app/cli.py:130-165` 的两条服务启动路径都创建 `create_pipeline_app(chain)`。生产 CLI 不使用保留的 legacy `app.server.app_factory.create_app`。
- 当前同伴提交后的 count-tokens 路径也不绕过：`src/app/server/handler.py:141-151` 在 `provider.count_tokens` 前逐个执行同一 `EVENT_ATTEMPT_PREPARE` subscriber。这个变化不属于 `4f2d786`，这里只用于确认当前合并态路径完整。
- 仓库还保留 legacy app factory、route 和 upstream client，但 CLI 生产入口没有引用它；该旧链本身另有 `app.anthropic.sanitize.filter_empty_text_blocks`。模型目录刷新、鉴权等网络调用不发送 Anthropic message body。
- 判定：在生产 pipeline 的普通请求和当前 count-tokens 请求中，没有发现绕过该 subscriber 发送 Anthropic body 的路径。

### 2. 顺序决策：行为可接受，理由应改

- 注册顺序由 `src/app/pipeline/subscribers/__init__.py:35-44` 与 `tests/unit/test_builtin_subscribers.py:25-27` 固定为 server-tool 后、blank-text 前述最后执行。
- `_flatten_history` 不会产生空/纯空白 text。详见“应改”发现。
- 判定：不要求换序；要求撤回错误理由。

### 3. thinking 分隔符：通过

- `src/app/pipeline/subscribers/blank_text.py:61-65` 查找当前 blank 后的下一个非 blank survivor，并只在已经保留的前项和该后项都是 thinking 时插入 `SYNTHETIC_SEPARATOR`。
- 连续 blank 只插一个，首尾 blank 不插；普通非 blank 会阻断两端 thinking 的关系。`thinking` 和 `redacted_thinking` 都由 `THINKING_TYPES` 识别。
- 这与 `src/app/anthropic/thinking/destack.py:15-33` 的“不允许相邻 thinking，必要时插 separator”不变量一致。
- `src/app/pipeline/subscribers/blank_text.py:52` 把该分支标成“基于 shape 的推理，尚非生产测量”是恰当的证据限定：它说明设计依据和未观测范围，没有把推理冒充实测。

### 4. 全空处置：可接受，理由应收窄

- `system` 是可选顶层字段；`src/app/pipeline/subscribers/blank_text.py:78-89` 仅在它是 list 且过滤后无 survivor 时删键。该操作发生在 route/translation 完成后，现有 built-in 顺序里也没有后续消费者依赖 `system`；driver 随后从已修改的 context 重取快照。未发现 `del payload["system"]` 会删掉其他路径所需状态。
- message 则保留原样并明确 warning。行为是保守且可接受的，但注释因果需要按前述“不同意但可接受”收窄。

### 5. 旧落点清理：通过

- `src/app/pipeline/anthropic_request_hook.py:1-91` 无 blank-text import、logger、helper、调用、参数或悬空注释。
- Git object 逐字比较显示，`4f2d786:src/app/pipeline/anthropic_request_hook.py` 与规则首次引入前的 `d732275:src/app/pipeline/anthropic_request_hook.py` SHA-256 同为 `428b6f33b149f2ffac47504d617953292bfeb9d99ddf387b3ce8d76621c4778c`。
- 判定：旧落点清理干净。

### 6. 测试分辨力：通过，边界测试有一项建议

- `tests/unit/test_blank_text_blocks.py:38-78` 直接区分 empty 和 whitespace 过滤；`:81-90` 固定 all-blank message 例外；`:120-148` 区分 system 部分过滤与删键；`:166-200` 固定 Responses target 完全不改；`:203-225` 的 malformed predicate 断言取决于 survivor 内容，不是恒真断言。
- `tests/unit/test_builtin_subscribers.py:129-171` 经真实 `AnthropicMessagesDriver.run` 检查 provider 最终收到的 body，能发现 subscriber 只注册未 dispatch、dispatch 后未重取 payload、或过滤成为空操作。
- `tests/http/test_pipeline_app.py:166-201` 不是恒真“不变”断言。它从 Anthropic inbound 走 route、pre-translation hook、translator、Responses driver 到记录的 wire body，并精确要求 whitespace system 与 empty `input_text` 都保留。若过滤误挂回翻译前，`:197` 会从带空白的 instructions 变成 `be brief`，`:198-201` 会缺少 empty input part，因此会转红。若 Responses leg subscriber 根本不运行，它通过是正确结果；Anthropic leg 是否真实运行由前述 driver 测试独立约束。
- 建议仅是补住连续 blank 与首尾 blank 的 separator 边界，详见上文。

### 7. 更简单或更正确的做法

- 落点与 target-format gate 已是最直接的正确做法，不应搬回翻译前，也不需要配置开关。
- 现有算法保留 object identity、all-blank 字段策略和 thinking adjacency 三项语义；把它替换为单个 list comprehension 会丢掉后两项，不是更正确。
- 可做的简化只有两项：修正顺序说明，不再维护虚构依赖；若未来 content list 规模使 O(n²) lookahead 成为实测问题，再按连续 blank run 单遍处理。当前没有据此重写生产代码的必要。

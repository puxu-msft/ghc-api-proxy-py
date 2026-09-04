# `messages: text content blocks must be non-empty` —— 根因与修复

**日期**：2026-08-20
**状态**：根因闭合（一手证据）。两片修复已落地；落点经用户两次裁决与一次上游实测后定稿于 `4f2d786`。

**触发**：生产日志

```
[FAIL] 06:00:21 400 POST /v1/messages claude-opus-5 466ms: upstream rejected the request: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'messages: text content blocks must be non-empty'}, 'request_id': 'req_011CeDVPWKgMHEfdnkD6vLhu'}
[FAIL] 06:00:22 400 POST /v1/messages claude-opus-5 461ms: ...（同上，request_id req_011CeDVPXoEWqSKKB9Hds8mP）
```

**证据来源**：三份并行调查 —— [我方入站链路](260820-empty-text-block-inbound-trace.md)、[我方响应产出侧](260820-empty-text-block-response-side.md)、[copilot-api-js 参考实现](260820-empty-text-block-copilot-api-js.md)。决定性的一手证据来自客户端 transcript，记录在第 1 节。老服务 history 库的取证在根因闭合后中止，无报告。评审记录见第 6 节与 [260820-review-synthetic-start-fix.md](260820-review-synthetic-start-fix.md)。

## 1. 根因 —— 是我们自己下的毒

**[强，一手证据，因果链完整]**

失败的客户端不是主会话，而是 peer 会话 `792a44f0` 的一个子智能体。它的 transcript 记录了完整因果链：

`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/792a44f0-0de2-4bdb-a1f9-418a394922fd/subagents/agent-abbb204c8997953ff.jsonl`

| 行 | 时间 | 内容 |
|---|---|---|
| 86 | `05:56:07.315Z` | user / `tool_result` —— 这一轮的请求由此发出 |
| 87 | `06:00:09.364Z` | assistant / `[{"type":"text","text":""}]`，`msg.id = fd698f7b…` |
| 88 | `06:00:21.147Z` | assistant / `[tool_use(Write)]`，**同一个 `msg.id`**，`stop_reason: tool_use` |
| 89 | `06:00:21.492Z` | user / `tool_result` |
| 90 | `06:00:22.519Z` | 合成记录：`API Error: 400 … text content blocks must be non-empty` |

Claude Code 把一轮 assistant 按内容块拆成多条 transcript 记录（第 84/85 行的 `thinking` + `tool_use` 同样共享一个 `msg.id`，可作对照）。所以第 87、88 行是**同一轮**，其实际内容是 `[text(""), tool_use]`。

**关键数字**：`05:56:07.315` → `06:00:09.364` = **242.0 秒**。`synthesized_response_headers_after_sec` 的默认值是 **240** 秒（`src/app/config/schema.py:193`），部署配置 `~/.local/share/ghc-api-proxy/config.yaml` 没有覆盖它。

因果链：

1. 上游对这一轮持续 240 秒没有产出任何可解析的 SSE event。
2. `src/app/pipeline/delivery/stream.py` 的 deadline 触发，主动向客户端交付 `synthesized_headers_block()` —— 一个 `text=""` 的**完整内容块**（`content_block_start` ＋ 空 `text_delta` ＋ `content_block_stop`）。
3. 12 秒后上游真正的 `tool_use` 才到，作为块 index 1 交付。
4. 客户端把这一轮存成 `[text(""), tool_use]`。
5. 下一轮请求原样回传这段历史，上游拒绝整个 body。两次连续 400 就是这一轮和它的重试。

**这不是客户端的锅，也不是上游的锅。空块是我方交付层自己造的。**

### 第二个缺陷：拦住它的守卫本项目有，但没接线

**[强，三份独立调查交叉确认]**

即使空块来自别处，也本该被拦下：

- `/v1/messages` ＋ Claude 系模型走 direct passthrough（`translation_required=False`），body 逐字转发。这条腿上唯一改写 `messages[*].content` 的是 `src/app/pipeline/anthropic_request_hook.py` 的 `fix_anthropic_request`（`src/app/server/handler.py:77` 调用）。
- 专做这件事的 `filter_empty_text_blocks`（`src/app/anthropic/sanitize/text_blocks.py:4`，判据 `not (block.text or "").strip()`）只有两个调用者，`src/app/anthropic/client.py:157` 与 `src/app/pipeline/executor.py:168`，**两者都在 legacy 链路上**。`tests/unit/test_module_boundaries.py:30` 把「新链路不引入 `app.pipeline.executor`」写成了断言 —— 守卫是在架构切换时被留在旧链路上的。

**这是上一次 websearch 400 的同一形态**：能力门写好了却没接在生产链路上（那次是 `server_tool_not_supported`）。同一类缺陷第二次击发。

### 上游的判据是「空串**或**纯空白」

**[强，一手]** Claude Code 自身的错误分类器（其可执行文件内，同一段代码把两条错误归为同一个 tag `empty_text_block`）：

```js
e2.message.includes("text content blocks must be non-empty") || e2.message.includes("text content blocks must contain non-whitespace text")
```

所以只判 `== ""` 会漏掉一半。参考实现与本项目既有的 `filter_empty_text_blocks` 都用 `trim()`/`.strip()`，是对的。

### 不是重写引入的

**[强，一手]** 2026-07-15 与 07-16 走老服务 copilot-api-js 时，本机 transcript 里也记录了同一条 `API Error: 400 messages: text content blocks must be non-empty`。这条腿一直有这个敞口。

## 2. 修复第一片 —— 直接防护：剥离空块

**落点由实测决定，不是由推断决定。** 见第 2.1 节：GHC 的 Responses API 接受空 text content part，Anthropic Messages API 不接受。所以剥离**只在出站上游是 Anthropic Messages 时发生，且发生在发出的那一刻**。

实现是 `src/app/pipeline/subscribers/blank_text.py`，一个挂在 `attempt.prepare` 上的订阅者，判据 `context.target_format is WireFormat.ANTHROPIC_MESSAGES` —— 与同伴的 `builtin:server-tool-capability` 同一条轴、同一个判据。注册在 `src/app/pipeline/subscribers/__init__.py`，**排在 server-tool 之后**。但要说清楚：今天两者并无依赖——`adapt_server_tools` 改的是 `tools`、`tool_choice` 与 server-tool 历史块，而它产出的每个文本块都带 `[family]` 前缀，不可能为空（`_render_results` 的每条分支都返回非空串）。排在后面是约定而非必需：这一趟只做删除，放在所有改写之后看到的才是真正会发出的形态，将来若有别的 pass 产出空块也自动被覆盖。

> **更正**：本文档与提交 `4f2d786` 的说明最初写的是「那一趟会把 server-tool 轮次压平成文本，因而可能产出空块」。读了 `server_tools.py` 的 `_flatten_history_block` 与 `_render_results` 之后确认该理由不成立，是我编的。提交信息已在历史里，不改写；此处为准。

**判据**：block 是 dict、`type == "text"`、且 `text` 缺失、为 `None`、或 `strip()` 后为空。`text` 是**非字符串**的畸形块不删——本模块删的是不携带信息的块；静默删除畸形块会把客户端的 bug 藏在一次改写后面，不如让上游指名。

**全空时的处置按字段分开，因为答案本来就不同**：

- `system` 全是空白块 → **删掉整个 `system` 键**。没有 system 提示词与一个只含空白的 system 提示词语义相同，而「没有 `system`」是上游天天见的形态；`system: []` 是第三种、谁也没问过它，所以不发那一种。
- message 的 `content` 全是空白块 → **原样发出并打 WARNING**。没有一种对轮次的改写被测得既合法又等义：`content: []` 会被拒是参考实现两处注释的说法（**二手，本项目未自测，探针也没问过**）；删掉整条轮次会移动其后每一轮的位置、并可能让两个同角色轮次相邻，这两点**同样没对本上游实测过**。既然没有实测过的替代，就原样发出。

> 参考实现 copilot-api-js 正好在这里有洞 —— `content-blocks.ts` 过滤后不检查是否清空，会发出 `content: []`。调查 agent 用它自己的函数实跑复现过。**不要照抄**。

**夹在两个 thinking 块之间的空块被替换而不是删除**：换成 `destack_content` 会用的那个分隔符。直接删会让两个 thinking 块相邻，而那正是 layout pass 存在的理由——layout 跑在翻译之前，远早于这一趟，无法替它善后。这一条是**推理而非测量**：生产中没有观察到该形态，但它只花一次比较，而代价是用一个拒绝换另一个拒绝。

**不加配置开关**：协议修复是强制清洗，不是偏好。

### 2.1 上游实测：只有 Anthropic 腿会拒

`exp/260820-empty-text-probe/`，2026-08-20：

| 探针 | 形态 | HTTP |
|---|---|---|
| E1 | 基线：正常 `input_text` | 200 |
| E2 | `input_text: ""` 与一个真实的并列 | 200 |
| E3 | 纯空白 `input_text: "   \n"` | 200 |
| E4 | assistant 轮 `output_text: ""` | 200 |
| E5 | **阳性对照**：Anthropic 腿的空 text 块 | **400** `messages: text content blocks must be non-empty`（`req_011CeDbPwSjTZEc1W2JASgju`） |

阳性对照是这四个 200 能被解读的前提：同一次运行、同一套凭据、同一个上游主机，E5 拿到 400 且措辞与生产日志逐字一致，所以 200 是「上游看过并接受了」，不是「请求没到达会判断 body 的那一层」。

由此可以把话说准：空块在 Responses 腿上此前是**噪声而非故障**。这解释了为什么这个缺陷只在 Anthropic 直通腿上现形，尽管产生空块的合成占位块对两条腿一视同仁。

边界：只测了非流式 `/responses` 与 `gpt-5.5`，未测流式与其它模型。「content 全是空 part」这个退化形态**assistant 轮已测**（E4 发的就是它，200）；未测的是 user 轮的同一形态与 `content: []` 空数组。结论外推到 Responses 腿上的其它模型时应降为「合理外推」——E5 本身就证明了同一主机上不同端点的判据可以不同。详见 `exp/260820-empty-text-probe/FINDINGS.md`。

### 2.2 落点走过两次弯路，都记在这里

1. **第一版放在 `fix_anthropic_request`（翻译之前），并按出站目标门控。** 首轮评审指出该钩子对两条腿都跑，门控是必要的。
2. **第二版按用户裁决取消门控**——「不需要任何配置，因为该情形不含任何有效语义」——于是两条腿都剥。
3. **第三版按用户裁决搬到出站点**——实测证明只有 Anthropic 腿会拒之后，「只需要对发往 anthropic messages api 上游做剥离，而不是在任何更早的时候」。

第二版的错误值得单独记下：它把「块不含语义」当成了唯一判据，从而认为没有可条件化的东西。实测表明**还有一个判据是可测量的**——谁会读它、会不会拒——而格式处理的落点应当由后者决定。翻译之前的钩子看不到这个判据，所以它本来就不是这条规则该待的地方。


## 3. 修复第二片 —— 不再制造空块（根因）

`src/app/pipeline/delivery/stream.py`：240 秒 deadline 触发时，从「`message_start` ＋ 一个空 text 内容块」改为**只发 `message_start`**。

该机制 docstring 写明的目的是「把字节推到客户端面前，否则它会超时」。`message_start` 达成同一目的，且不向这一轮承诺任何内容。规格与文档中没有任何地方要求它必须是内容块（已 grep 确认）。

随之删除的：`synthetic_block_sent` 标志与它带来的块 index 偏移（真实块现在自然从 index 0 开始）、私有辅助 `_frame_now`、模块级 `synthesized_headers_block`。删除后者是刻意的：把制造这个缺陷的现成工具留在原地，等于邀请它被重新接回去；历史在 Git 里。

**这是一处产品可见的行为变更，且它覆盖了一条曾被测试显式钉住的行为**（原测试名即 `test_synthesizes_one_empty_block_when_first_real_block_is_late`）。

**用户已裁决（2026-08-20）**：在三个候选形态中选定「只发 `message_start`，不发内容块」。另两个候选是「开一个 `content_block_start` 不关闭」（字面意义的「半块」，但本次事故里真正内容是 `tool_use`，那个已开的 text 块只能被关掉、又变回空块）与「维持旧行为，只靠第一片在出站时剥掉」。

**遗留**：`docs/.human-controlled/config.example.yaml` 对该项的说明写的是「合成一个半块给客户端 / synthesize a half-block to the client」。这句话与改动**前**的实现（一个完整的空内容块）本来就对不上，与改动后的实现（不发内容块）也对不上。该文件是用户亲笔，**未修改**，措辞更新需由用户自己来。

### 退化场景的差异

deadline 触发后上游始终没有产出任何块时：

- 改前：客户端得到 `message_start` ＋ 一个空内容块 ＋ 终止帧。
- 改后：客户端得到 `message_start` ＋ 终止帧，即一条 `content: []` 的消息。

判据：deadline 关闭时，零块流本来就一个字节都不发（`stream.py` 末尾的 `if started:` 守卫），所以「零内容块」并不是本次引入的新形态。这条由第二轮评审独立核验。

## 4. 验证

- `tests/unit/test_blank_text_blocks.py`（13 例，含 5 例参数化的 predicate 边界、一例「Responses 腿不被改写」、一例 thinking 分隔符替换）。
- `tests/unit/test_builtin_subscribers.py` 增一例端到端：空块从 driver 实际发出的 body 里消失。该文件工作树里还有同伴的 WIP，提交时只把本次的内容写进索引，未卷入。
- `tests/http/test_pipeline_app.py`：`test_the_responses_leg_keeps_the_blank_blocks_it_was_given`。这是防止落点重新前移的守卫——把剥离搬回翻译前的实现能通过订阅者的全部单测，只在这里失败。
- 改写 `tests/unit/test_stream_delivery.py` 中两条钉住旧占位块行为的测试，并补一条退化线（deadline 触发后上游始终无产出）。
- **变异验证**：把订阅者的过滤变异成空操作后，19 条中 8 条转红（含端到端 driver 那条）。文件逐字还原（`restored: True`）。
- `tests/unit` 1000 全绿（两轮），`tests/http` 87 全绿。
- `ruff check src tests exp/260820-empty-text-probe` 全过；改动文件 pyright 0 错误。
- **已知无关的间歇性失败**：`tests/unit/test_stream_delivery.py::test_a_keep_alive_wait_leaves_no_asyncio_noise`（同伴未提交的测试）装的是**全局** loop 异常处理器，任何先跑的测试留下的未取出异常在 GC 时都会落进它。固定顺序 3/3 通过、随机顺序单文件 8/8 通过、完整 `tests/unit` 两轮通过；1000 条全跑时曾出现一次。属同伴在飞的工作，未处置。

## 5. 与参考实现的差异

| | copilot-api-js | 本项目 |
|---|---|---|
| 判据 | `block.text.trim() !== ""` | `text` 缺失/`None`/`strip()` 为空 |
| 空块处置 | 删块，不占位 | 同 |
| 过滤后清空 | **未处理，发出 `content: []`** | `system` 删键、message 原样发出并告警 |
| 作用范围 | `messages` 全角色 + `system` | 同 |
| 挂载轴 | 出站目标是 Anthropic Messages | 同 —— 但这里是**实测**出来的，不是照抄（见 §2.1） |
| 形态 | 纯预防式，零反应式重试 | 同 |
| 自己是否产出空块 | **是**（`cc-to-anthropic.ts:149`、`responses-to-anthropic.ts:222` 在无内容时故意 push） | 改前是，现已不产出 |

## 6. 评审处置

### 第一轮（第一片，异源模型）：0 blocker，2 应改 1 建议，**全部采纳**

该报告因 agent 运行环境限制未能落盘，结论记录于此。

1. **应改：过滤挂错作用轴。** `fix_anthropic_request` 对所有 Anthropic 入站请求执行，因此过滤也作用于 Anthropic→Responses 翻译腿；而 `translation_driver/openai_responses.py:104-117` 会把 system 的空白文本并入 `instructions`，`:231-252`、`:269-278` 会把空白 message block 渲染成 text part。删掉它们会改变主产品路径的字节，而这次缺陷从未要求这样做，且「上游都会拒绝」在 Responses 腿上未经测量。**一度采纳，随后被用户裁决推翻** —— 判据是块本身不含语义而非某上游会拒，门控已删除。详见第 2 节。
2. **应改：测试没锁住 predicate 自己声明的边界**（`text` 缺失、`None`、非字符串）。**已采纳** —— 补参数化用例。
3. **建议：全空 warning 文案写「in a message」，但 `system` 也用它。** **已采纳** —— `drop_blank_text` 增加 `field` 参数。
4. 其余各项（判据、顺序、全空不动、in-place 别名、测试无恒真断言、不复用 legacy helper）评审判定为通过，无改动。

### 第二轮（第二片，同源模型）：0 blocker，2 应改 3 建议，verdict pass

见 [260820-review-synthetic-start-fix.md](260820-review-synthetic-start-fix.md)。

1. **应改：派单前提有误。** 我在派单里写「规格与文档没要求它必须是内容块」，评审查出 `docs/.human-controlled/config.example.yaml:404-408`（**用户亲笔**）写的是「合成一个半块」，该前提不成立。**已采纳** —— 停下来交由用户裁决，结果见第 3 节。
2. **应改：退化线形无任何测试。** **已采纳** —— 新增 `test_a_synthesized_start_that_never_gets_a_block_still_ends_the_message`，同时在同一条测试里对照「deadline 关闭时零块流一个字节都不发」，把「零内容块不是本次引入的新形态」这个判据固定下来。
3. 评审独立核验通过的项：deadline 分支处 `started` 必然为 False（顺控制流证实，不会重发 `message_start`）；提前 `message_start`、零内容块、ping 任意穿插都在 Anthropic 流式规范形态内；退化线实测为 `message_start → message_delta → message_stop`；564 份 transcript 的 15795 条 assistant 记录中 `content: []` 出现 0 次，回传风险低；`_frame_now` 与 `synthesized_headers_block` 删除后无残留引用，index 偏移无遗留假设。
4. 两条 deferred 建议（`full` 策略下计时解除条件、退化路径的 `end_turn` 语义）未处置，记录在此。

### 第三轮（落点搬迁，异源模型）：0 blocker，1 应改 1 建议 1「不同意但可接受」，**全部采纳**

见 [260820-review-blank-text-subscriber.md](260820-review-blank-text-subscriber.md)。

1. **应改：冻结顺序的理由是错误事实。** 评审读 `server_tools.py` 的 `_flatten_history_block` 与 `_render_results`，确认它不可能产出空文本块。**已采纳** —— 顺序保留，理由改成如实陈述（今天无数据依赖；最后一道只做删除的 sanitizer 放在所有改写之后是约定，便于将来）。我在评审回来前自查也得到同一结论，两条独立路径一致。
2. **建议：补住 lookahead 真正承载的边界。** **已采纳** —— 新增参数化测试覆盖连续两个空块、首部空块、尾部空块、以及三者混合。变异验证：去掉 `_is_thinking(following)` 这个前瞻后，正是「trailing」与「leading-middle-trailing」两例转红，其余全绿。
3. **不同意但可接受：全空 message 的理由说得过强。** 原注释把「删掉轮次会破坏配对」当成既定事实断言。**已采纳收窄** —— 改为：清空 `content` 确定会被拒；删掉轮次会移动其后每一轮的位置、并可能让两个同角色轮次相邻，这两点**都没有对本上游实测过**；既然没有实测过的等价替代，就原样发出，让客户端拿到自己的错误而不是本链路发明的错误。模块开头也补注了这条例外，不再是无条件全称。

修正提交：`3193880`。

### 第五轮（最终候选 `3193880` ＋ 探针方法论，general-opus）：两部分均 0 blocker，5 应改 7 建议，**全部采纳**

见 [260820-review-final-and-probe.md](260820-review-final-and-probe.md)。这一轮补的是前四轮没覆盖到的两块：采纳提交本身，以及决定落点的那个探针。

**第一部分（`3193880`）**：采纳忠实、无过度采纳；新写的顺序理由经评审自读 `server_tools.py` 核实**属实**；「去掉 lookahead 只红新用例」经受控变异实测为真（1335 条中仅 2 红，且在隔离副本 `/tmp/rev3193880` 里做、已还原比对）。三条应改：

1. 被撤回的旧理由还活在 `tests/unit/test_blank_text_blocks.py` 的文档字符串里 —— 同一事实两处强弱不一，且**强的那个留在了测试里**。已改。
2. 同一句还活在 **live 文档** `docs/2604-rewrite/hooks-system.md` 的顺序表里，而那份文档自己声明以 `__init__.py` 为权威源。这是最要紧的一条：只读中文文档的维护者会得到与代码相反的结论。已改。
3. `content: []` 「certainly refused」是二手（来自参考实现的两处注释），本项目未自测，探针也没问过。已降级为带出处的写法。

另外三条建议也已采纳：新写的「Neither reads what the other writes」字面为假（它确实读了对方改写过的 content，真正成立的是「对方写出的东西触发不了这条规则」）；顺序表的 before/after 列声称了一个代码里没有的机器约束（`subscribe` 支持 `before=`/`after=` 但两者都没传），改成「registered last, by convention」；参数化测试里的 `expected is None` 分支改成字面量。

**第二部分（探针）**：E5 经核实是**真对照**（同一次 token 交换、同一 base URL、同一套 header 构造）；四个 200 的响应体都带 usage 与真实输出，不只是「接受了 body」；**探针发的形态经评审顺翻译链核实与生产翻译产物逐字一致**，不是我手写的近似。两条应改：

4. `FINDINGS.md` 的「这对本项目意味着什么」写于 07:19，比 `4f2d786`（07:29）早十分钟，描述的是被随后推翻的「无条件剥离」，与现行门控相反。已加日期标注并划掉过时条目，保留原文以记录当时推理。
5. 「没有测 content 全是空 part」与 E4 自相矛盾 —— E4 发的正是这个形态且拿到 200。已改为准确版本（assistant 轮已测、user 轮与 `content: []` 未测）。

四条建议同样采纳：结论句补上 `gpt-5.5`／非流式限定并说明外推强度；说清 E5 同时变了两个量（端点与协议拼写），严格结论是那一对事实而非把拒绝归因给「API 本身」；把「E4 后跟 user message 而非 function_call」「五个探针都不带 tools」写进边界。

修正提交：`ab3bee7`。

## 7. 提交

| 提交 | 内容 |
|---|---|
| `b2576eb` | 第一片初版：把守卫接回生产链路（放在翻译前的钩子里，按出站目标门控） |
| `e82e9a5` | 第二片：合成响应改为只发 `message_start`，不再制造空块（根因） |
| `db9aa7d` | 第一片二版：按裁决取消门控，两条腿无条件剥离 |
| `4f2d786` | 第一片三版：按裁决与上游实测搬到 `attempt.prepare` 订阅者，只在 Anthropic 腿生效；旧落点逐字还原 |

每次提交都只点名本任务自己的文件。同伴在 `src/app/observability/`、`src/app/server/handler.py`、`src/app/pipeline/subscribers/server_tools.py`、`tests/unit/test_builtin_subscribers.py`、`tests/unit/test_stream_delivery.py` 等处有活跃 WIP，未被卷入 —— 其中 `test_builtin_subscribers.py` 是与同伴改动混在同一文件里的，用「只把自己的内容写进索引、工作树不动」的方式提交。

**注意**：`4f2d786` 的提交信息里对订阅者顺序给了一个理由（「flattening a server-tool turn into text is one of the ways a blank block gets made」），事后核实**不成立**，见第 2 节的更正。历史不改写。

## 8. 仍待你裁决

### 8.1 `config.example.yaml` 的措辞

见第 3 节「遗留」。该文件是你亲笔，我没有改。

### 8.2 拿不到实际发出的 body —— 同一缺口第二次挡路

pipeline app 不接 history（`~/.local/share/ghc-api-proxy/history.db` 里只有 legacy 测试流量，无任何 `claude-opus-5`），400 时也不落盘。上一次 websearch 400 的报告已把这条记为排障能力缺口。这次能闭合根因，靠的是**客户端**的 transcript 恰好留了痕，而不是我们自己的可观测性。

当前唯一可行的替代是 `ANTHROPIC_LOG=debug` 或 `--verbose`，SDK 会打印完整 `json_data`（已实测），代价是日志里带明文上游 token。

**我的偏好**：加一条窄的「400 时把出站 body 落盘」的能力，只在 `UpstreamRejected` 时触发，不常开。请裁决是否要做。

### 8.3 ~~其余 fixup 是否也该按出站目标门控~~（已由裁决解决）

原问题是：`drop_blank_text` 加了门控，而同钩子里既有的 `sanitize_empty_thinking` 与 `destack_content` 无条件作用于两条腿，形成不一致。用户裁决取消了门控，三者现在一致无条件，该不一致不复存在。

## 9. 顺带发现，本次未处置

- **默认测试扫描是红的，与本改动无关。** `tests/unit tests/http` 合跑时 `tests/http/test_pipeline_app.py::test_upstream_429_is_seen_by_the_rate_limiter` 与 `::test_upstream_503_does_not_enter_limited_mode` 失败，形态是 `assert <RateLimitMode.NORMAL> is <RateLimitMode.NORMAL>` —— 同名不同类对象。成因是 `tests/unit/test_module_boundaries.py` 的 `reachable_from()` 会把 `app.*` 从 `sys.modules` 里全部删除再重新导入，之后跑的测试拿到的是第二份 enum 类。判别实验：`tests/http` 单独跑全绿；`test_module_boundaries.py` 与那条限流测试按序同跑即红。该文件 docstring 称其为 2026-08-19 新增，所以这是一条新鲜回归。**未修**，因为在本任务范围外且同伴可能正在该文件上工作。
- `src/app/pipeline/translation_driver/responses.py:71-90` 在翻译后 content 为空时主动补 `[{"type":"text","text":""}]`；`src/app/protocols/responses_anthropic.py:121-133`（legacy）同形。与第二片是同一族问题，但走的是非 SSE 翻译路径，本次未碰。
- `src/app/auto_truncate/` 只剩 `__pycache__`，源文件已删，确认是死代码。
- `src/app/anthropic/feature_negotiation.py` 是孤儿模块（上次调查已记录）。

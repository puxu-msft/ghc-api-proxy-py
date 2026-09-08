# Spec：TUI 请求日志与实时 footer

状态：主体已实现并与代码对账（分支 `worktree-tui-request-log-footer`）。2026-09-08 新增的 retry 请求双段耗时显示已同步到完成日志、请求 trace、durable request record 与真实 replay integration test。2026-09-03 新增的 Responses terminal status 与 client action 组合展示和着色合同已由 `bb5783f` 的流式直连接线及 `6200600` 的统一 provider observer 覆盖到 Responses upstream 的 streaming／non-streaming、direct／translated 路径；2026-09-06 修订的相邻同类型 action display grouping 已由 `abdfd54` 同步到 production projection 与 unit／integration 转录。2026-09-06 增补 direct buffered Chat provider observation合同，尚未实现；其权威字段、展示与验收见本规格，架构见 [`../direct-buffered-chat-completions/design.md`](../direct-buffered-chat-completions/design.md)。Panel/detail 交互不在其中，见文末「明确不做」。验收逐条对应的测试见「验收」一节。

## 目标

环境支持时，终端呈现两样东西：**请求日志按原生终端滚动**（保留 scrollback，可以往回翻），**其下方一行实时 footer** 显示当前在飞请求。环境不支持时，输出与今天完全一致。

这是 P1 只读面：TUI 只读取请求生命周期并展示，不提供从 TUI 反向控制请求的交互。该边界沿用 [`2604-rewrite/telemetry-observability.md`](history/2604-rewrite/telemetry-observability.md) 的既有裁决；该文档属于历史设计，不是 current authority，不在本次重议。

## 为什么不是一个 textual App

[`2604-rewrite/lib-survey/SELECTIONS.md`](history/2604-rewrite/lib-survey/SELECTIONS.md) 记录的历史选型是 `textual`；该文档属于历史选择/实验，非 current authority。它产生不出上面这个形态——textual 的 App 要么接管备用屏（日志不再进原生 scrollback），要么以 inline 模式渲染固定块。本次改用 `rich.Live`，依据是 `.dev/docs/tui/archive-footer/` 的实测：在稀疏日志 + 高频重绘、超宽折行、窄终端四类压力下均干净，且探针已用已知坏实现证明具备鉴别力。

`rich` 是 `textual` 自己的渲染内核，所以这是在同一套已选栈内挑层级，不是引入新技术栈；被放弃的只是「跑全屏 App」这一形态。**这仍然是对已记录选型的偏离，需要用户知悉。**

## 可观察行为

### 由环境探测决定，不由配置决定

裁决于 2026-08-19：**是否呈现 TUI 由环境探测决定，没有配置开关。** 理由是一个开关无从知道进程是被 systemd 拉起、被重定向进文件、还是跑在设了 `TERM=dumb` 的 CI 里，而这三种情形的正确答案各不相同；直接问环境在三种情形下都对，且不需要任何人去维护一个设置。

探测出三项彼此独立的能力，而不是一个布尔：

| 能力 | 判据 | 决定什么 |
|---|---|---|
| `live` | stderr 是 TTY，且 `TERM` 既非空也非 `dumb`，且未设 `CI` | 是否呈现实时 footer |
| `color` | `live` 成立且未设 `NO_COLOR` | 是否输出颜色与 `dim` 等 ANSI 属性 |
| `unicode` | 目标流的编码能承载该字形 | `↓` 还是降级为 `<` |

三者分开是有意的。`TERM=dumb` 的终端仍然是终端，只是只收纯文本行；管到 `tee` 的管道能好好承载 UTF-8，却绝不能收到移动光标的转义。合并成一个布尔会把「字节数字形用哪个」绑到「能不能开实时区域」上，而这是两个无关的问题。

**环境不支持时**：不呈现 footer，不输出任何终端控制序列，不输出颜色，不输出非 ASCII 图标。也不为此记一条日志——管道与 CI 是常态而非降级，不值得在所有人的日志里占一行。

`unicode` 刻意不依赖 `live`：文件与管道都能正确渲染 UTF-8，没有理由因为 footer 跑不起来就连带降级字节数的字形。

### footer 形态

一行，形如：

```
[<-->] gpt-5[high] x2 1.20s ↓4.1KiB 0.35s | claude-sonnet-4[none] 8.90s ↓12KiB | +2 more
```

- **按已解析模型和思考强度分组**，组内与组间都按请求开始时间升序（最老的在前）。思考强度紧跟模型名，以 `model[effort]` 显示；合法显示值包括 `none`、`low`、`medium`、`high`、`xhigh`、`max`，以及 provider catalog 已选出的其它合法 effort 名称。没有 provider-bound named effort 时显示 `none`。最该关注的是跑得久的那个，宽度不够时应该被裁掉的是最新的。
- 分组键是原始的已解析模型名，**空字符串（尚未解析）也是一个合法的键**，渲染为 `(resolving)`。一个真名叫 `(resolving)` 的模型不得与「尚未解析」的请求合并。
- `xN` 报告该模型**实际拥有**的请求数，而不是当前显示的条数。宽度受限时两者不同，而这个计数正是「这行藏了东西」的唯一提示。用 ASCII `x` 而非上游的 `×`：后者会被 linter 判为易混淆字符，且部分终端按双宽渲染。
- 每个在飞请求保留**自己的**耗时与自己的下行字节数，不跨请求合并——这两个字段正是同一模型的两次调用之间的差别，也是看这行的理由。
- 发生 retry 的在飞请求把耗时从单个 `<total>` 展开为 `<last>/<total> (<n>)`：`<last>` 是当前（最后一次）attempt 从打开到此刻的墙钟耗时，`<total>` 是整个请求从开始到此刻的墙钟耗时，`(<n>)` 中的 `n` 是此前实际打开的 replacement attempt 数（`attempts - 1`）。与完成日志的 `retries=N` 措辞不同，footer 是活的、计数还在变，用括号计数贴在双段耗时后；两段时间都用既有的 duration 格式，未 retry 的请求保持原有单值文本。
- `↓<bytes>` 只在该请求已上报过流式进度时出现。**它的缺席意味着「还没有任何字节流回」，与 `↓0` 是不同的事实。**
- 无在飞请求时 footer 为空串（不是一行空白）。

### footer 的宽度纪律

**硬不变量：footer 永远不超过一物理行。** 实现上是单一出口：剥除全部 C0 控制字符（任何一个都会强制第二物理行），再截断到 `columns - 1` 显示列（-1 用于避开某些终端的末列自动换行）。

这不是优化项。实测未截断时在 40 列下每次都失败：footer 折成第二行，其中一种机制的溢出行还会跑到保留区之外污染屏幕（`.dev/docs/tui/archive-footer/`）。

显示预算的分配分两轮：先决定**哪些模型出现**，每个按最小形态（名字 + 它最久的那个请求）度量，装不下的收进 ` | +K more` 尾巴；再把剩余列**轮转**发给已显示的模型，一次加一个请求，使一个繁忙模型无法饿死其它模型。宽终端显示全部在飞请求，窄终端退化为每模型最慢的几个，而不是整组消失。

### 日志行

沿用现有 structlog 的定宽前缀格式（`[ OK ]` / `[FAIL]` / `[GONE]` / `[<-->]` / `[....]` / `[RETRY]`）。footer 存在时它们**必须经由 footer 所属的 console 打印**，而不是另一个独立 handler——两个写者各自持有光标假设，输出必然互相踩踏。

完成日志的模型名后同样显示 provider-bound reasoning effort，格式为 `model[effort]`；没有 named effort 时显示 `model[none]`。失败和取消日志也保留该模型后缀，避免同一次请求在不同终局下丢失思考强度。请求侧 `provider/model` 限定只选择 provider，不是模型映射；当其去掉限定后的模型名等于已解析模型时，成功日志只显示 `model[effort]`，不得伪报为 `provider/model → model[effort]`。真实模型映射保留箭头，并把已解析目标显示为 `provider/model[effort]`，例如 `fast → ttthree/glm-5.3-flash[high]`，使同名模型由哪个 provider 回答不含糊。

完成日志的耗时字段在没有 retry 时保持 `<total>`；发生 retry 后显示为 `<last>/<total> retries=N`。`<last>` 是最终 attempt 自身从打开到完成的墙钟耗时，`<total>` 是整个客户端请求从开始到完成的墙钟耗时，`N` 是最终 attempt 之前实际打开的 replacement attempt 数。两段时间都使用现有 duration 格式，普通请求的单值文本与颜色保持不变。

`[GONE]` 于 2026-08-20 由用户裁决加入，用于**没有人收到答案、而这既不是本代理也不是上游的过错**的请求：客户端按 Esc 走了，或连接断了。它不与 `[ OK ]` 合并（那样一次被取消的轮次与一次答完的轮次无从区分），也不与 `[FAIL]` 合并（本代理服务的是交互式客户端，取消是日常动作，同色会把真正的故障淹掉）。

### 一次流式请求怎么结束，由行来说

流式请求的 HTTP 状态码在上游响应头到达时就定死，此后无论流怎么结束都是 200。所以**状态码不是结局**，结局由 `status_override` 与行尾原因共同表达：

| 结局 | 前缀 | 行尾原因 |
|---|---|---|
| 上游发出了合法终止事件，交付完整跑完 | 由状态码决定 | 无 |
| 上游流自己跑完但没发终止事件 | `[FAIL]` | `upstream stream ended without a terminal event` |
| 上游撕断（reset、读错误、转换异常） | `[FAIL]` | `stream failed before a terminal event: <异常原文>` |
| 交付被这一侧中止（客户端走人；也包括关停取消自己的在途流） | `[GONE]` | `delivery stopped before upstream finished` |

判据是「交付是否完整跑完」**且**「上游是否给出了结束原因」，两者缺一即报。只看结束原因不够：收尾帧写在交付循环之后，撕断与断开都会跳过它，于是上游虽已说过 `end_turn`，客户端却一帧未得。

最后一档分不出「客户端走了」与「关停取消了我们自己的在途流」——两种情形下措辞都成立（没人收到答案、交付先于上游结束），这一行不假装分得出。

无论哪种结局，**已经观测到的事实照常上行**：已关闭的工具块与推理块与终止事件无关，不随结局一起丢弃。上游从未说过的东西则整个缺席，而不是退回某个默认值——`Terminal.stop_reason` 因此默认空串而非 `end_turn`。

### 一次计数请求怎么读

裁决于 2026-08-20，起因是一条读不出来的实际日志：`[ OK ] 17:08:01 H1 200 anthropic-messages/claude-opus-5 1.2s ↑19.7k`。

`/v1/messages/count_tokens` 是**唯一一种没有回复的 200**：没有块、没有结束原因、没有下行词元。而成功行会把 `METHOD /path` 折叠成 `<inbound-format>/<model>`，计数与真实对话又共用 `anthropic-messages` 这个 inbound format，于是行上没有任何东西说明「这是一次计数」。这些缺席逐个都诚实，问题在于**缺席读不出来**：一次计数，与一次交付成功但回复字段全丢的轮次，读者无从分辨。

两处各答一半：

| 事实 | 行上怎么说 |
|---|---|
| 这是一次计数请求 | 格式前缀加后缀，`anthropic-messages-count-tokens/<model>`。它是**端点**，比计数器早一步知道，所以一次连计数器都没跑到的计数仍然说得出自己是计数 |
| 数字是谁给的、之前试过谁 | 行尾 `provider(...)`，占据结束原因的槽位（计数没有结束原因，两者不可能同时出现）。括号里是**按发生顺序的轨迹**：试过而没答上的在前，真正应答的在后 |

**为什么必须说是谁计的**：这一行上实测与估算是同一个裸数字。响应体用 `estimated` 区分了两者，行不能比响应体说得更少——读者据它判断的是「这个数能不能当账单看」。`ghc` / `local` 直接取自 `CountTokensProvider` 这个封闭集合，与配置文件用词一致。

**估算还要说明为什么**。裁决于 2026-08-20：`provider(local)` 原本是三种结局共用一个词，其中两种是事故——「这条路由本来就没有上游计数器」是正常配置、天天发生，「上游被问了却答不出」是要看一眼的事，而它们逐字相同。这与本节开头那个毛病是同一个，只是高了一层：失败并没有从行上缺席，它是**穿着正常情形的衣服**。用户选择把原因写进括号，而不是 `ghc→local` 那种箭头写法；2026-08-20 稍后又把字段名从 `count` 改为 `provider`——格式前缀既然已经带上了 count-tokens 端点，这个槽位再说一遍「这是计数」就是重复，它该说的是谁应答的，也就是 `providers` 配置里的那个词。

| 行 | 含义 |
|---|---|
| `H1/H1 … ↑<字节> ↓<字节> ↑<词元> provider(ghc)` | 问了上游，上游答了，数字是它给的 |
| `H1/H1 … ↑<字节> ↓<字节> ↑<词元> provider(ghc-failed,local)` | 问了上游，上游**给了响应但答案不可用**（200 却没有可用的 `input_tokens`、或 body 不是合法 JSON），降级到估算 |
| `H1 … ↑<词元> provider(ghc-failed,local)` | 问了上游，上游**连响应都没给**（错误状态被抬成 pipeline 错误、传输失败） |
| `H1 … ↑<词元> provider(no-counter,local)` | 这条路由本来就没有上游计数器（翻译到 `/responses` 的模型），从没问过上游 |
| `H1 … ↑<词元> provider(local)` | 运维把 `providers` 配成只估算，或把 `local` 排在 `ghc` 前面。没问过上游，也没有什么出了错 |

所以**上游那一腿在不在**是第三个可读的事实，含义比「上游答出了这个数」更窄：它说的是上游**给过响应**。

原因由 `handle_count_tokens` 判定，不在展示层解析字符串：判据是它自己传给 `count_tokens()` 的 `upstream_absent_reason`，以及尝试轨迹里有没有 `ghc:` 开头的条目。不能只看「这条路由有没有上游计数器」——运维还能通过 `providers` 的取舍与排序让上游根本没被问，那既不是缺计数器也不是失败。

更细的原因（是超时还是 500）仍然只在 `count_tokens_attempts` 里，**目前没有任何读者**；要不要把轨迹带进结构化记录，见 `deferred`。

真正的 *refusal*（`ProviderError`：未知模型、能力缺失）不走这里：它一路冒到 400，既不是 200 也不带 `provider(...)`。

### 着色规则

裁决于 2026-08-20。颜色**承载含义，不做装饰**：一行上被染色的东西，都是不看数字也该注意到的东西。

| 字段 | 规则 |
|---|---|
| 定宽前缀 | `[ OK ]` 绿、`[FAIL]` 红、`[GONE]` 黄、`[RETRY]` 与 `[DRIN]` 黄、`[<-->]` 青、`[....]` 灰。**表以外的 status 会静默回落成 `[....]`**，所以新增档位必须同时进 `STATUS_PREFIXES` 与 `PREFIX_COLOURS`，且测试要断言渲染出来的前缀而不是喂进去的那个键 |
| 状态码 | 成功绿，失败红 |
| 模型名 | 品红；被映射时「原名」灰、「实际应答的」品红 |
| 耗时 | ≤20s 白、≤60s 黄、≤180s 红、更久加粗红（这里保留显式白） |
| **下行字节** | <10KB 灰、<100KB **不着色**、≥100KB 黄（临界点为 `10 * 1024` 与 `100 * 1024`） |
| **下行词元** | <1k 灰、<10k **不着色**、≥10k 黄（临界点为 1000 与 10000） |
| 上行字节 | 恒灰。它的大小由客户端发来的请求决定，与回复如何无关 |
| 上行词元 | 本身不着色；其缓存分段为「读」灰、「写」青 |
| 缓存命中率 | 反向：≥80% 灰，越低越红 |
| **结束原因与终局状态** | `end_turn` / `stop_sequence` 绿；Chat native `stop` 绿；Responses 的 `completed` 仅在 `client_action_classification_complete` 为 true 且 `client_actions` 为空时绿，存在 required、unknown 或集合分类不完备时不着色；`max_tokens` 与 Chat native `length` 黄；`refusal` 与 Chat native `content_filter` 红；`tool_use` / `function_call` / `custom_tool_call` / Chat native `tool_calls` 不着色；**表以外的原因或状态一律不着色** |
| **计数提供方** | `provider` 与括号不着色，括号内的 `[<试过的>,]<应答的>` 灰 |
| **工具名列表** | 灰；其中 `AskUserQuestion` 青 |
| 推理块 | 灰 |
| 失败原因 | 红 |
| 失败行的 `METHOD /path` | 不着色 |

以下几处需要说明理由：

- **只有回来的那半升级**。上行字节大是长上下文的常态，把它染色等于每一行都在喊，反而不再传递信息。
- **「普通」那一档不着色，而不是显式白**。裁决于 2026-08-20：`\x1b[37m` 把前景设成调色板的白，多数深色主题里它比终端**自己的默认前景更亮**，于是最普通的那一档反而比根本没被碰过的字段还响，读起来像强调；它还隐含假设深色背景，浅色终端上接近不可见。量级与失败行的 `METHOD /path` 因此改为不发转义。**耗时保留显式白**，用户明确要求。
- **结束原因是一条阶梯，不是一个标志位**。这几个都终结了这一轮，所以单一颜色只能表达「它停了」——而这件事有这个字段本身就已说明。读者想知道的是**这个结束有多成问题**：干净收尾没什么可看；在词元上限处被截断，是那一行上唯一值得看的事；而拒绝连内容都没交付、也无法直接续跑，所以它与失败状态码同级（红），而不是低一级。裁决于 2026-08-20，由用户指定 `max_tokens` 黄、`refusal` 红。`tool_use` / `function_call` 不进任何一档——它确实结束了模型这一次回复，但它是唯一表示**工作尚未结束**的原因：调用方要去跑工具再回来，给它一个结束色等于在最常见的中间点上画句号。

  这张表是**封闭白名单**，不是规则。表以外的结束原因一律不着色：光看名字无从判断它是好消息还是坏消息，随便给个颜色就是在断言这段代码并不知道的事。
- **Chat显示原生finish reason，不先翻成Anthropic词汇。** `stop`／`length`／`content_filter`分别落入既有clean／token-limit／refusal颜色档，`tool_calls`仍表示工作尚未结束而不着色；这是对同一语义档位的方言投影，不新增第四套严重度判断。Unknown native值保留原文且不着色。
- **Responses 的 `completed` 不能脱离完整 terminal output 集合判读。** `completed` 说明这一份 Responses response 已经收口，不说明模型与客户端之间的工作已经结束；同一份 response 完全可以同时含 `function_call` 或 `custom_tool_call`，等待客户端执行后续动作。权威 terminal status、typed client-action facts 与集合级 `client_action_classification_complete` 因此分槽并同时进入判读。只有 terminal `output` 明确是数组、其中每一项都已得到三态分类，且 action 列表为空时，`completed` 才能使用代表「没什么要看」的绿色；确认需要行动、分类为 unknown，或 terminal snapshot 本身不完备时都不绿。stream item 生命周期是否完整由请求 verdict 与 detail 表达，不由这个颜色字段重复判定。判据不从工具名称、空列表或 buffering policy 的布尔投影反推。用户于 2026-09-03 明确指定 `completed + function_call/custom_tool_call` 不绿，并选择 terminal status 与 client-action facts 分槽；集合完备标志、terminal `output` authority、unknown、无名调用与顺序的处置是本规格推导。
- **临界点取整数，不迁就四舍五入带**。裁决于 2026-08-20：`format_bytes` 只印一位小数，因此 10239 与 10240 字节都显示 `10.0KB`，却分处「灰」与「不着色」两侧。这是已知且接受的表现——阈值是 `10 * 1024` 这个整数，不是「打印出 `10.0KB` 的那一点」。
- **`AskUserQuestion` 从灰色列表里挑出来**。这个工具的用途本身就是向人提问，所以工作此刻卡在「有没有人看到」上。对列表里其它名字**不作任何断言**——工具名是任意字符串，别的工具同样可能在等审批或等外部事件；只是这一个把「要等人」写在了名字上，颜色也只建立在这一点上。
- **计数提供方不进结束原因那条阶梯**。裁决于 2026-08-20，用户明确选了不着色。`ghc` 与 `local` 都不是「有多成问题」的档位：一条翻译路由本来就没有上游计数器，天天答 `provider(no-counter,local)` 是正常配置而不是事故，给它一个警示色等于每天喊一次狼来了。降级那一档（`provider(ghc-failed,local)`）改由**词**承担，而不是颜色——这样它在落盘日志里同样读得出来，颜色在那里是丢失的。计数器名与其原因和工具名列表同理，是括号里的细节，灰。

### 描述回复的用词跟随上游

裁决于 2026-08-20。日志行描述的是 proxy 与 upstream 之间那一段，所以**描述回复内容的字段用上游自己的词**，而不是统一翻译成下游契约的词：

| 事实 | Anthropic 上游 | OpenAI Responses 上游 | OpenAI Chat Completions 上游 |
|---|---|---|---|
| 推理块 | `think(enc:1,txt:2)` | `reason(enc:1,txt:2)` | `reason(enc:1,txt:2)` |
| 以工具调用收尾 | `tool_use(Bash,Read)` | `function_call(Bash,Read)` | `tool_calls(Bash,Read)` |
| 调用了工具但没人说这一轮结束了 | `called(Bash,Read)` | `called(Bash,Read)` | `called(Bash,Read)` |

Responses upstream 路径还持有一个客户端协议投影不能替代的独立事实：上游 response 自己的权威 terminal status。该事实由统一 provider observer 在 streaming event 与 non-streaming whole body 上观察，direct 与 translated 路径都读取同一份 observation；direct streaming 的 legacy terminal projection 只在 observation 不可用时回退。Terminal status 不取代 output item；两者按「status 在前、可见 output segment 按 terminal `response.output` 数组位置在后」同时显示，例如 `completed function_call(Bash)`、`completed custom_tool_call(run_shell)`。该数组位置就是 Responses 的 output position，权威不是 `done` 事件到达顺序；durable observation 逐项保留每个 item 的位置、原始 type、名称、重复与顺序，console projection 才归约相邻 segment。连续、原始 type 相同、名称非空且确认需要客户端行动的 items 合并为一个字段，名称按原顺序用逗号连接且不去重，例如 `function_call(TaskCreate,Bash)`；不同原始 type、可见 reasoning、unknown action 与无名 action 均断开两侧。可见 reasoning 内部，连续 reasoning items 无论 `txt`／`enc` 都归约成单个字段并按 kind 累加计数，一段交叉 `txt`／`enc` 的 run 呈现为一个 `reason(enc:N,txt:M)`（enc 在前），不再展开成一行重复的 `reason(txt:N) reason(enc:N)...`。没有可见内容且不需要客户端行动的 item 不进入 display segment 序列，因此不制造伪边界。无名 required item 只显示原生 type；分类无法确定但 policy 为避免扣押而保守释放的 item 显示为 `client_action?(<原生 type>)`，type 也缺席时显示 `client_action?(unknown)`。terminal `output` 缺席或类型错误时，列表空也不代表没有 action，行上追加 `client_action?(unclassified)`。Rich observation 不可用时，legacy terminal projection 对 client actions 使用同一相邻归约规则；它不合成 legacy carrier 没有的 reasoning facts。这里的 `completed` 按「着色规则」直接读取完整 required 与 unknown facts 以及集合完备标志，不从归约后的 display segments 反推。上述 authority、集合完备、顺序、durable 重复、display 归约、无名和 unknown 呈现中，display 归约边界由用户于 2026-09-06 确认，其余为本规格为兑现可观测合同作出的推导。

Chat upstream 路径的provider observation同样独立于客户端投影，而且只能由最终attempt提供。它保存全部choices并按native `choice.index`排序；每个choice分槽保存native `finish_reason`、reasoning facts与按tool index排序的tool calls，保留重复、无名调用和unknown raw fields。Console只展开最小choice index；多choice时追加 `choices=<n>`，使presentation trim可读而不伪装成只有一个choice。Native finish reason先显示，再显示该choice的reasoning与tool calls；没有finish reason但已经观测到调用时用 `called(...)`，不自行声称这一轮以tool calls结束。SSE的 `[DONE]` 与finish reason分槽：前者决定buffered transaction完整性，后者描述模型为何停止；二者不得相互覆盖。

#### Chat provider observation schema

`ResponseObservation`增加可空的 `chat` 槽，不把Chat choice伪装成Responses `OutputItemSummary`，也不把finish reason塞进Responses `status`。`source_protocol == "openai-chat-completions"` 时 `chat` 按下表写出；其它协议时为null／省略，现有Responses字段语义不变。

| 层级 | 字段 | 精确语义 |
|---|---|---|
| `chat` | `done_seen` | Streaming observation为是否见到首个合法 `[DONE]`；native non-stream JSON为null，表示不适用而不是false |
| `chat` | `tail_ending`／`tail_detail` | 第一个 `[DONE]` 后tail collection被 `transport_tear`、`idle_timeout`、`attempt_deadline`、`client_deadline`、`buffer_cap` 或 `local_failure`终止时记录稳定枚举与有界detail；clean EOF及native non-stream为null。该字段不反转成功verdict |
| `chat` | `choices` | Observation可用时总是数组，显式零choice为 `[]`；unavailable时为null。只收入合法非负整数index的choice并按index升序；非法index不伪造choice，写issue |
| `chat` | `stream_error` | `JsonObservation`，保存最终candidate在semantic freeze前看到的完整error JSON值；未见为absent，显式null与unreadable分开。`[DONE]`后的error只在raw tail，不进入此槽 |
| `chat` | `top_level_unknown` | `FrozenJsonObject`，保存规范聚合表允许保留的unknown top-level字段；无字段时为空object，不用null冒充unavailable |
| `chat` | `unattributed` | 无法归入合法choice／tool index的完整可读facts数组；每项保存frame ordinal、half-open raw offset、field path与原始`JsonObservation`。空数组表示确实没有，null表示observation unavailable |
| choice | `choice_index` | 原生index，非数组位置；重复index跨event是同一choice，同一event重复index按出现顺序累计并记issue |
| choice | `finish_reason` | `JsonObservation`，区分absent、explicit null、合法string与unreadable；冲突值以第一个合法值为投影并记issue，mode adaptation本身按direct-passthrough §9.3失败 |
| choice | `reasoning_content` | `JsonObservation`；所有合法 `reasoning_content` string delta按event顺序连接，只有null且无片段为explicit null，完全没出现为absent，错误类型为unreadable |
| choice | `tool_calls` | 按合法tool index升序的数组；跨event同index为同一call，同一event重复index按出现顺序累计并记issue。数组中的重复名称不去重 |
| choice | `choice_unknown`／`message_unknown` | choice层与delta→message层分别保存`FrozenJsonObject`；同名字段不得互相覆盖。冲突值对应issue，不把后值静默覆盖前值 |
| tool call | `tool_index` | 原生index；非法index不伪造call，其完整raw object进入`chat.unattributed`并写issue |
| tool call | `id`／`type`／`name`／`arguments` | 各为 `JsonObservation`；id／type／name保留首个非空字符串并记录冲突，arguments按event顺序连接；无名调用的name为absent，不用空字符串冒充已观察 |
| tool call | `tool_unknown`／`function_unknown` | Tool层与function层unknown字段分别保存为`FrozenJsonObject`，同名不得互相覆盖 |
| observation | `usage`／`provider_usage`／`tool_usage`／`issues` | 沿用 `ResponseObservation` 现有槽；Chat usage absent时raw为ABSENT，显式null时raw为EXPLICIT_NULL，empty object、合法zero、wrong type与inconsistent各自可区分。最后一个显式object是projection authority，后续null不清空它；wrong-type标准字段写stable conversion issue并保留raw。Provider/tool usage未观察时为absent；issue至少带stable code、field path与event ordinal |

Raw payload可能含一个event无法归入合法choice／tool index。Direct streaming仍原样交付该event；durable observation通过issue与相应raw unknown槽保留可读事实。Mode-adapted non-stream若该event会让标准JSON丢失已知内容，则按direct-passthrough §9.3的 `unassemblable` 失败，不能靠observation容错把交付变成成功。

Console精确拼法如下：最小choice的finish reason先输出；该choice有nonempty reasoning时追加 `reason(txt:1)`，当前Chat carrier没有加密reasoning则不写 `enc`；有tool calls且finish reason为 `tool_calls` 时输出 `tool_calls(Bash,?,Bash)`，其中 `?`逐项表示无名调用并保留重复；有调用但finish reason缺席时输出 `called(Bash,?,Bash)`；无调用而finish reason为 `tool_calls` 时输出裸 `tool_calls`。多于一个合法choice时最后追加 `choices=<n>`。Unknown finish reason原文经 `inert_token`输出且不着色。`tail_ending`非null时再追加黄色 `tail(<code>)`；detail只进durable record与既有request detail，不把任意upstream文本塞进固定宽度字段。

`ResponseObservation` 还把归一化 usage、上游原始 usage、exact cache／reasoning／total 事实与 conversion issues 分槽保存到 schema v2；console token 列只读取归一化投影，不把 `usage_inconsistent` 或 malformed detail 扩成常驻字段。于是「上游未报 usage」「显式 null」「合法零值」「上游报了 malformed／自相矛盾的 usage」在 durable record 中可区分，而不会为了可观测性改变响应交付。Chat使用同一三槽，不另写一套token formatter。

第三行是**两个上游共用一个词**的唯一一处，而且刻意不是任何一方的词。`tool_use` 与 `function_call` 都断言回复**以工具调用收尾**；在一条没有结束原因的行上，没有人说过回复结束了，借用任一方都是在给被截断的一轮画上句号。真实的只有「这些块关闭了、这些工具被点了名」，而这值得读——一轮已经点了三个工具才被截断，与一轮什么都没产出，是不同的事故。

不用 `tools(...)`：那也是请求侧**工具声明**的名字，读日志的人无从分辨「这次请求声明了 Bash 和 Read」与「这一轮调用了它们」，而那是交换的两端。

理由：两者足够像，会被混淆；而「这一轮到底走了哪个上游」正是有人翻日志要查的东西。Responses 本身没有 stop reason，`tool_use` 是 assembler 为满足下游契约**合成**出来的——它对响应体是对的，对这一行是错的，因为 Responses 的追踪里根本不存在名为 `tool_use` 的东西可供检索。

判定依据是**路由**（`handler.dialect_for`），不是回复体：缓冲回复是在翻译成客户端形状之后才被读回的，那时体内已不再有任何东西说明是谁应答的。流式路径由 assembler 自身携带（一个 assembler 只可能描述一种上游）。两者共用同一个分支——`assembler_for` 基于 `dialect_for` 的结果分派——以免两条路径对「谁应答的」得出不同答案。

Responses upstream 的权威 terminal status 现由 provider-side observation 在 direct／translated 与 streaming／non-streaming 路径统一保留；面向客户端的 `end_turn`／`max_tokens` 仍只属于响应协议投影，不反向覆盖这份 observation。`enc`／`txt` 两个计数标签仍是合成词（真实的是 `encrypted_content` 与 reasoning summary），其开放范围及数据丢失点见 [`deferred.md`](deferred.md)。

## 数据来源

在飞请求登记在 `_serve`（`src/app/server/pipeline_app.py`）这一层，它是覆盖整个请求生命期的唯一 ASGI 接缝。

流式请求在 `_serve` 返回时**并未结束**——响应体在其后才被消费。因此注销与字节计数必须包住那个生成器，而不是写在 `_serve` 的出口。这是本设计里最容易写错的一处：把注销放在 `_serve` 末尾，会让每个流式请求在开始吐字节的那一刻就从 footer 上消失，而那恰恰是它最该出现在 footer 上的时候。

登记项字段：请求 id、已解析模型（可为空，渲染为 `(resolving)`）、开始时间、已下行字节数（未上报过则为 `None`）。

## 验收

1. 非交互环境（管道、文件、`TERM=dumb`、`CI`）下输出与今天逐字节一致，无终端控制序列、无颜色、无非 ASCII 图标。
2. `NO_COLOR` 只关颜色，不关 footer；编码承载不了 `↓` 时只降级该字形，不关 footer。
3. pty + pyte 抓屏：日志行不被吞、不被 footer 残骸污染，footer 在所有日志行之下且屏上只有一份，scrollback 中没有 footer 副本。判据须先由一个已知坏实现判红，再谈绿色是否可信——`tests/tui/test_footer_screen.py` 里的 `test_the_scoring_catches_a_footer_that_scrolled_out_of_place` 就是这道正样本对照。
4. 40 列与 80 列下 footer 均不折行。
5. 流式请求在其字节仍在下行期间持续出现在 footer 上，字节数随之增长。
6. footer 构建是纯函数：给定在飞集合、当前时刻与列宽，输出确定，无 I/O、无墙钟读取。
7. Responses 终局状态的判读必须覆盖 status、逐项分类与 terminal snapshot 完备三层，display projection 还必须独立覆盖可见性、barrier、raw-type identity、相邻归约与渲染。格式化单元在开颜色时，对 `client_action_classification_complete=true` 且 actions 为空的状态精确产出 `\x1b[32mcompleted\x1b[0m`；对两个相邻同 raw type 的具名调用与后继不同 type 的调用精确产出 `completed function_call(\x1b[2mBash,Bash\x1b[0m) custom_tool_call(\x1b[2mrun_shell\x1b[0m)`——action type 与 `completed` 本身不着色，名称逐项 inert 后才由 renderer 添加逗号与工具名颜色；legacy fallback 对同一 action sequence 必须产出同形字段。对 snapshot 分类不完备且 actions 为空精确产出 `completed client_action?(unclassified)`，不含绿色转义。Atomic projection 与 reducer 单元分别断言：相邻同 raw type 的具名 required actions 合并且保留重复；不同 raw type、可见 reasoning、unknown 与无名 action 是 barrier；一段内部交叉 `txt`／`enc` 的连续 reasoning run 归约成单个 `_Reasoning` 并按 kind 累加，冗长交替 run 的纯文本尾段精确产出 `reason(enc:N,txt:M)` 而不是若干 `reason(enc:1) reason(txt:1)...`，且 durable `output_items` 仍逐项保留；没有可见内容且 `NOT_REQUIRED` 的 item 不进入 segment sequence；两个不同 raw type 即使经 bounded encoding 得到同一 display label 也不合并。真实 streaming `/responses` 内部路由用 mock upstream 跑五组对照：(a) terminal 显式 `output=[]`，stream 另含一个 unattributed event，摘要仍为 complete、actions 为空，纯文本尾段为 `completed`；(b) terminal `output` 只有完整 `message`，同样得到 clean `completed`，用于判红“所有 item 都是 unknown”；(c) terminal `output` 缺席与类型错误参数化为两例，两者都得到 `completed client_action?(unclassified)` 且不绿；(d) terminal `output` 含一个未知原生 type，得到 `completed client_action?(future_tool_call)` 且不绿；(e) terminal `output` 依次含 `function_call(Bash)`、重复的 `function_call(Bash)` 与无名 `custom_tool_call`；stream 中三个 `done` snapshot 全部故意改成 `tool_search_call(execution=server)` 并使用不同名称，所以 done 侧的 `any(required)` 为 false，而 terminal 三项全部是 `required`；三个 `done` 再以 2、1、0 的反序到达。最终尾段仍须为 `completed function_call(Bash,Bash) custom_tool_call`，两个名称恰好各出现一次且 `completed` 不绿。最后一例是 source-of-truth 控制，不冒充真实上游合法分歧；全部 mock 只证明本代理的 collector、`RequestTrace → RequestLine` 接线、terminal authority、分类完备、排序、相邻归约与展示，不冒充真实上游本轮实况。把 `output=[]` 当缺席、把缺席或错误类型当 complete、让任何 unattributed event 阻止 complete、把所有 item 分类为 unknown、丢弃 unknown、从 `done` snapshot 收集最终 name 或 requirement、按 `done` 到达顺序输出、取消 named-action 相邻归约、用 encoded label 代替 raw type 作 identity、让 visible barrier 被跳过、action 列读 terminal 但 completed 颜色偷读 done-side bool、只按 terminal status 着色或把所有 completed 一律取消着色，必须分别被上述对应层断言判红，且失败原因落在目标 segment、字段或尾段，不得由 fixture 解析错误代打。

8. Responses provider observation 必须从真实 production 入口覆盖四种组合，而不是只直接调用 formatter：streaming direct 的五组对照继续由第 7 条承担；`tests/int/test_pipeline_app.py::test_a_direct_buffered_responses_reply_is_observed_before_translation` 以完整 `output` 的 reasoning＋function call 作为 non-stream direct 正样本；`test_a_responses_upstream_is_logged_in_its_own_words` 与 `test_a_streamed_responses_reply_is_logged_in_its_own_words` 分别钉住 translated non-stream／stream。缺陷控制是把 whole-body observer 移到 response translation 之后或跳过它：前两条 buffered 断言必须因原生 status／item vocabulary 丢失而失败；把 translated path 退回只读下游 `Terminal.stop_reason` 时，后两条必须因出现 `end_turn`／`tool_use` 或缺少 `completed`／`reason`／`function_call` 而失败。mock upstream 只证明本代理的接线与投影，不证明真实 upstream 本轮会产出这些 shape；真实 shape 仍由 cassette 测试承担。

9. Direct buffered Chat provider observation必须从production入口验证而非只调reader：一条direct `stream:true /chat/completions`在首轮无 `[DONE]`、次轮完整后，只记录次轮的finish reason／reasoning／ordered tool calls／usage；一条native non-stream JSON读取同一字段；一条endpoint capability要求streaming→buffered JSON的non-stream路径从最终SSE attempt读取同一字段。至少一例含choice 0与1、choice 0内tool index 0／1／2依次命名 `Bash`／缺席／`Bash`，durable schema按choice／tool index精确保留两个choices与三个calls，console纯文本尾段精确含 `tool_calls(Bash,?,Bash) choices=2`；另一例无finish reason但有同组三个calls，精确含 `called(Bash,?,Bash) choices=2`。Post-`[DONE]` client deadline用例精确追加 `tail(client_deadline)`而保持成功前缀；clean EOF不出现tail字段。还要覆盖explicit null reasoning、unknown finish reason、invalid choice／tool index各自进入具名issue而不伪造record。缺陷控制分别让discarded attempt泄漏、fallback candidate被current attempt覆盖、从synthetic body重推provider facts、把finish reason当 `[DONE]`、把Chat事实塞进Responses status/output_items、按tool到达顺序而非index排序；对应断言必须在目标字段变红。Mock只证明本代理接线与投影，不冒充真实provider shape；CodeBuddy `stream:false` capability仍以P6未实测标注。

## 明确不做

- **panel / detail 交互**（展开列表、详情页、滚动、按键解码）。现有 reducer 的 `panel_list` / `detail` 两态保留，本次不接线。**注意**：`rich.Live` 的 footer 跟着内容浮动而非钉物理底行，多行面板要钉底时这个模型可能不够用，届时需重新评估是否退回 DECSTBM，不得假设本次结论已经覆盖那个场景。
- **从 TUI 中止请求**。P1 只读边界，中止归审批系统。
- 分层遥测、请求历史面板等，均已有各自归属文档。

## 修订记录

| 日期 | 条款 | 变化 | 触发 |
|---|---|---|---|
| 2026-09-08 | 描述回复的用词、验收 | 可见 reasoning 相邻归约不再要求 kind 相同：一段内部交叉 `txt`／`enc` 的连续 reasoning run 归约成单个字段并按 kind 累加，纯文本呈现为固定 `reason(enc:N,txt:M)`（enc 在前），取代原来一行重复的 `reason(txt:N) reason(enc:N)...`；对不同 action 仍是 barrier，durable observation 继续逐项保留 | 用户要求聚合 TUI log 中 `reason(txt:1) reason(enc:1) reason(txt:1) reason(enc:1) reason(txt:1) reason(enc:1)` 这类连续交错的 reason 段 |
| 2026-09-08 | footer 形态、验收 | 发生 retry 的在飞请求把 footer 耗时从单个 `<total>` 展开为 `<last>/<total> (<n>)`，`<last>` 取当前（最后一次）attempt 自打开的墙钟耗时、`<total>` 保持整个请求墙钟耗时、`(<n>)` 的 `n` 为已打开的 replacement attempt 数；未 retry 的请求保持单值耗时。footer 在 retry 打开时更新最后一次 attempt 的 monotonic 起点，渲染继续是纯函数 | 用户要求在 retry 请求的 footer 上同样显示 `<last>/<total> (<n>)` |
| 2026-09-08 | 日志行 | 真实模型映射的已解析目标增加 provider 前缀，采用 `provider/model[effort]`；仅请求侧 provider 限定且模型未映射时保持裸 `model[effort]` | 用户要求模型映射显示 provider，避免同名模型的来源歧义 |
| 2026-09-08 | 日志行 | 明确请求侧 `provider/model` 限定仅选择 provider，不构成模型切换；去掉限定后与已解析模型相同的成功行只显示已解析模型及 reasoning effort，不显示 `→` | 用户报告 `openai-responses/ttthree/glm-5.3-flash → glm-5.3-flash[high]` 把 provider 限定误报为模型切换 |
| 2026-09-08 | 日志行、验收 | retry 过的完成日志把耗时从单一 `<total>` 展开为 `<last>/<total>`，并继续单独显示 `retries=N`；`<last>` 取最终 attempt 的耗时，`<total>` 保持整个请求墙钟耗时。请求 trace 在每个 attempt 建立时记录 monotonic 起点，完成日志与 durable request record 读取同一投影；无 retry 的请求保持原有文本与颜色 | 用户要求修复 TUI log 中 retry 请求仅显示总耗时的问题；`tests/int/test_pipeline_app.py` 的真实 replay 链路补充双段耗时断言 |
| 2026-09-08 | footer 形态、验收 | 活动请求在模型名后显示 provider-bound reasoning effort，使用 `model[effort]` 形式；按模型与 effort 分组，未选择 named effort 的请求显示 `none`，支持 `none`、`low`、`medium`、`high`、`xhigh`、`max` 及 catalog 已选出的其它合法名称 | 用户要求 TUI log 在模型后显示思考强度 |
| 2026-09-06 | 描述回复的用词、验收 | 更正 Responses client-action display projection：durable observation 继续逐项保留位置、raw facts、重复与顺序；console 把相邻同 raw type 的具名 required actions 归约成一个字段，不去重，visible reasoning／不同 type／unknown／无名 action 断开，不可见 `NOT_REQUIRED` item 不制造边界；legacy fallback 复用同一 action grammar。验收 oracle 同步改为 `function_call(Bash,Bash)`，并分层钉住 atomic projection、相邻归约、raw identity、encoding 与 production 接线 | 用户以实际日志指出相邻 `function_call` 未合并并确认行为边界，随后把内部结构裁决委托给 coordinator；三方历史确认 `f97d243` merge resolution 删除了 `45e7cfb`／`b233751` 的 action grouping 并反转测试 oracle；[`design.md`](design.md) 与两轮独立设计评审 |
| 2026-09-06 | 状态、着色规则、描述回复的用词、Chat provider observation schema、验收 | 增加direct buffered Chat provider observation：最终candidate的全部choices、native finish reason、reasoning、ordered tool calls、`[DONE]`、流内error与usage进入独立Chat typed record；逐层定义absent／null／unreadable、unknown raw字段、invalid index issue与无名调用 `?` 呈现。Console只展开最小choice并显式标出多choice，durable schema保留全集；discarded／replacement-failed attempt不得覆盖实际交付candidate。实现完成后关闭deferred第0条 | 用户明确选择把TUI一并接通、标准multi-choice聚合及post-`[DONE]`语义；[`../direct-buffered-chat-completions/decisions.md`](../direct-buffered-chat-completions/decisions.md) D-5／D-9～D-11；两份独立设计评审 |
| 2026-09-05 | 状态、描述回复的用词、数据来源、验收 | 纠正 Responses observation 的当前覆盖面：统一 provider observer 已覆盖 direct／translated 与 streaming／non-streaming；客户端协议投影不再覆盖 provider-native terminal facts，direct streaming 的 legacy terminal projection 仅作 observation 不可用时的兼容回退。补齐四种 production 入口的正样本与接线缺陷控制；显示合同仍严格保留逐项 action、重复、terminal output authority、unknown／unclassified 与 contextual green。Durable schema v2 现分槽保存 normalized／raw／exact usage 及 observation issues；原 deferred 第 0 条的 Responses 半边、第 0.5 与第 1 条已由本规格与 direct-passthrough §10 接管并从台账移除，尚未实现的 direct buffered Chat Completions 半边收窄后仍作为 deferred 第 0 条保留 | 远端 `6200600` 的实现与集成测试；本次 merge 三方历史调查及规范对账 |
| 2026-09-04 | 着色规则、描述回复的用词、验收 | `bb5783f` 实现 Responses 流式直连终局展示：`completed` 与 terminal output 的 required 与 unknown actions 同时显示，只有 snapshot 分类完备且 action-free 时绿色；unclassified 显式可读。JSONL 持久化 status、typed actions 与 completeness；incomplete、translated、nonstream 保持既有路径。实现评审终评 0 blocker、0 major，9 个单变量 controls 全部目标变红；最终 Ruff clean、Pyright 0、full regression 2213 passed、2 skipped、coverage 91.29% | `bb5783f`；[`../direct-passthrough/reports/260904-completed-client-actions-implementation-review-disposition.md`](../direct-passthrough/reports/260904-completed-client-actions-implementation-review-disposition.md) |
| 2026-09-03 | 着色规则、描述回复的用词、验收 | Responses 流式直连的 `completed` 改为与 typed client-action facts 组合判读：仅在已确认无客户端行动时绿；存在 `required`、`unknown` 或集合分类不完备时不着色，并同时显示权威 status、每项行动或 `unclassified` 标记。新增颜色双向控制、explicit-empty、complete not-required、complete unknown 与 missing/malformed-unclassified 三组集合控制、反序 `done` 的排序控制，以及重复与无名 action 的端到端 oracle | 用户主动指出 `completed + function_call/custom_tool_call` 不代表工作结束，并选择 terminal status 与 client-action facts 分槽；三态、terminal `output` authority、集合完备、排序、重复、无名与 unknown 呈现为本规格推导，来源是 direct-passthrough §4、§7.1 与 §10 及 2026-09-03 独立评审 |

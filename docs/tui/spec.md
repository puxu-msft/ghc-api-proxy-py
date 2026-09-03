# Spec：TUI 请求日志与实时 footer

状态：主体已实现并与代码对账（分支 `worktree-tui-request-log-footer`）。2026-09-03 新增的 Responses 流式直连 terminal status 与 client action 组合展示和着色合同待本轮实现；panel/detail 交互不在其中，见文末「明确不做」。验收逐条对应的测试见「验收」一节。

## 目标

环境支持时，终端呈现两样东西：**请求日志按原生终端滚动**（保留 scrollback，可以往回翻），**其下方一行实时 footer** 显示当前在飞请求。环境不支持时，输出与今天完全一致。

这是 P1 只读面：TUI 只读取请求生命周期并展示，不提供从 TUI 反向控制请求的交互。该边界沿用 `docs/2604-rewrite/telemetry-observability.md` 的既有裁决，不在本次重议。

## 为什么不是一个 textual App

`docs/2604-rewrite/lib-survey/SELECTIONS.md` 记录的选型是 `textual`。它产生不出上面这个形态——textual 的 App 要么接管备用屏（日志不再进原生 scrollback），要么以 inline 模式渲染固定块。本次改用 `rich.Live`，依据是 `.dev/docs/tui/archive-footer/` 的实测：在稀疏日志 + 高频重绘、超宽折行、窄终端四类压力下均干净，且探针已用已知坏实现证明具备鉴别力。

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
[<-->] gpt-5 x2 1.20s ↓4.1KB 0.35s | claude-sonnet-4 8.90s ↓12KB | +2 more
```

- **按已解析模型分组**，组内与组间都按请求开始时间升序（最老的在前）。最该关注的是跑得久的那个，宽度不够时应该被裁掉的是最新的。
- 分组键是原始的已解析模型名，**空字符串（尚未解析）也是一个合法的键**，渲染为 `(resolving)`。一个真名叫 `(resolving)` 的模型不得与「尚未解析」的请求合并。
- `xN` 报告该模型**实际拥有**的请求数，而不是当前显示的条数。宽度受限时两者不同，而这个计数正是「这行藏了东西」的唯一提示。用 ASCII `x` 而非上游的 `×`：后者会被 linter 判为易混淆字符，且部分终端按双宽渲染。
- 每个在飞请求保留**自己的**耗时与自己的下行字节数，不跨请求合并——这两个字段正是同一模型的两次调用之间的差别，也是看这行的理由。
- `↓<bytes>` 只在该请求已上报过流式进度时出现。**它的缺席意味着「还没有任何字节流回」，与 `↓0` 是不同的事实。**
- 无在飞请求时 footer 为空串（不是一行空白）。

### footer 的宽度纪律

**硬不变量：footer 永远不超过一物理行。** 实现上是单一出口：剥除全部 C0 控制字符（任何一个都会强制第二物理行），再截断到 `columns - 1` 显示列（-1 用于避开某些终端的末列自动换行）。

这不是优化项。实测未截断时在 40 列下每次都失败：footer 折成第二行，其中一种机制的溢出行还会跑到保留区之外污染屏幕（`.dev/docs/tui/archive-footer/`）。

显示预算的分配分两轮：先决定**哪些模型出现**，每个按最小形态（名字 + 它最久的那个请求）度量，装不下的收进 ` | +K more` 尾巴；再把剩余列**轮转**发给已显示的模型，一次加一个请求，使一个繁忙模型无法饿死其它模型。宽终端显示全部在飞请求，窄终端退化为每模型最慢的几个，而不是整组消失。

### 日志行

沿用现有 structlog 的定宽前缀格式（`[ OK ]` / `[FAIL]` / `[GONE]` / `[<-->]` / `[....]` / `[RETRY]`）。footer 存在时它们**必须经由 footer 所属的 console 打印**，而不是另一个独立 handler——两个写者各自持有光标假设，输出必然互相踩踏。

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
| **结束原因与终局状态** | `end_turn` / `stop_sequence` 绿；Responses 的 `completed` 仅在 `client_action_classification_complete` 为 true 且 `client_actions` 为空时绿，存在 required、unknown 或集合分类不完备时不着色；`max_tokens` 黄；`refusal` 红；`tool_use` / `function_call` / `custom_tool_call` 不着色；**表以外的原因或状态一律不着色** |
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
- **Responses 的 `completed` 不能脱离完整 terminal output 集合判读。** `completed` 说明这一份 Responses response 已经收口，不说明模型与客户端之间的工作已经结束；同一份 response 完全可以同时含 `function_call` 或 `custom_tool_call`，等待客户端执行后续动作。权威 terminal status、typed client-action facts 与集合级 `client_action_classification_complete` 因此分槽并同时进入判读。只有 terminal `output` 明确是数组、其中每一项都已得到三态分类，且 action 列表为空时，`completed` 才能使用代表「没什么要看」的绿色；确认需要行动、分类为 unknown，或 terminal snapshot 本身不完备时都不绿。stream item 生命周期是否完整由请求 verdict 与 detail 表达，不由这个颜色字段重复判定。判据不从工具名称、空列表或 buffering policy 的布尔投影反推。用户于 2026-09-03 明确指定 `completed + function_call/custom_tool_call` 不绿，并选择 terminal status 与 client-action facts 分槽；集合完备标志、terminal `output` authority、unknown、无名调用与顺序的处置是本规格推导。
- **临界点取整数，不迁就四舍五入带**。裁决于 2026-08-20：`format_bytes` 只印一位小数，因此 10239 与 10240 字节都显示 `10.0KB`，却分处「灰」与「不着色」两侧。这是已知且接受的表现——阈值是 `10 * 1024` 这个整数，不是「打印出 `10.0KB` 的那一点」。
- **`AskUserQuestion` 从灰色列表里挑出来**。这个工具的用途本身就是向人提问，所以工作此刻卡在「有没有人看到」上。对列表里其它名字**不作任何断言**——工具名是任意字符串，别的工具同样可能在等审批或等外部事件；只是这一个把「要等人」写在了名字上，颜色也只建立在这一点上。
- **计数提供方不进结束原因那条阶梯**。裁决于 2026-08-20，用户明确选了不着色。`ghc` 与 `local` 都不是「有多成问题」的档位：一条翻译路由本来就没有上游计数器，天天答 `provider(no-counter,local)` 是正常配置而不是事故，给它一个警示色等于每天喊一次狼来了。降级那一档（`provider(ghc-failed,local)`）改由**词**承担，而不是颜色——这样它在落盘日志里同样读得出来，颜色在那里是丢失的。计数器名与其原因和工具名列表同理，是括号里的细节，灰。

### 描述回复的用词跟随上游

裁决于 2026-08-20。日志行描述的是 proxy 与 upstream 之间那一段，所以**描述回复内容的字段用上游自己的词**，而不是统一翻译成下游契约的词：

| 事实 | Anthropic 上游 | OpenAI Responses 上游 |
|---|---|---|
| 推理块 | `think(enc:1,txt:2)` | `reason(enc:1,txt:2)` |
| 以工具调用收尾 | `tool_use(Bash,Read)` | `function_call(Bash,Read)` |
| 调用了工具但没人说这一轮结束了 | `called(Bash,Read)` | `called(Bash,Read)` |

原生 Responses 流式直连路径还持有一个翻译路径没有的独立事实：上游 response 自己的权威 terminal status。它不取代 output item；两者按「status 在前、client action 按 terminal `response.output` 数组位置在后」同时显示，例如 `completed function_call(Bash)`、`completed custom_tool_call(run_shell)`。该数组位置就是 Responses 的 output position，权威不是 `done` 事件到达顺序；同一类型的每个调用保留重复。确认需要客户端行动的 item 按原生 type 显示，名称为空时只显示 type；分类无法确定但 policy 为避免扣押而保守释放的 item 显示为 `client_action?(<原生 type>)`，type 也缺席时显示 `client_action?(unknown)`。terminal `output` 缺席或类型错误时，列表空也不代表没有 action，行上追加 `client_action?(unclassified)`。这里的 `completed` 按「着色规则」同时读 required 与 unknown facts 以及集合完备标志。上述 authority、集合完备、顺序、重复、无名和 unknown 呈现是本规格为兑现可观测合同作出的推导，不是用户原话。

第三行是**两个上游共用一个词**的唯一一处，而且刻意不是任何一方的词。`tool_use` 与 `function_call` 都断言回复**以工具调用收尾**；在一条没有结束原因的行上，没有人说过回复结束了，借用任一方都是在给被截断的一轮画上句号。真实的只有「这些块关闭了、这些工具被点了名」，而这值得读——一轮已经点了三个工具才被截断，与一轮什么都没产出，是不同的事故。

不用 `tools(...)`：那也是请求侧**工具声明**的名字，读日志的人无从分辨「这次请求声明了 Bash 和 Read」与「这一轮调用了它们」，而那是交换的两端。

理由：两者足够像，会被混淆；而「这一轮到底走了哪个上游」正是有人翻日志要查的东西。Responses 本身没有 stop reason，`tool_use` 是 assembler 为满足下游契约**合成**出来的——它对响应体是对的，对这一行是错的，因为 Responses 的追踪里根本不存在名为 `tool_use` 的东西可供检索。

判定依据是**路由**（`handler.dialect_for`），不是回复体：缓冲回复是在翻译成客户端形状之后才被读回的，那时体内已不再有任何东西说明是谁应答的。流式路径由 assembler 自身携带（一个 assembler 只可能描述一种上游）。两者共用同一个分支——`assembler_for` 基于 `dialect_for` 的结果分派——以免两条路径对「谁应答的」得出不同答案。

**仍未改、留待裁决**：本轮只让原生 Responses 流式直连路径记录并展示权威 terminal status；翻译型 Responses 路径仍把 `response.completed` / `response.incomplete` 映成面向 Anthropic 下游的 `end_turn` / `max_tokens` 后再汇总，是否也保存原生 status 是另一项可观察改动。`enc` / `txt` 两个计数标签同样仍是合成词（真实的是 `encrypted_content` 与 reasoning summary）。两项开放范围及数据丢失点见 [`deferred.md`](deferred.md)。

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
7. Responses 终局状态的判读必须覆盖 status、逐项分类与 terminal snapshot 完备三层。格式化单元在开颜色时，对 `client_action_classification_complete=true` 且 actions 为空的状态精确产出 `\x1b[32mcompleted\x1b[0m`；对两项有序行动精确产出 `completed function_call(\x1b[2mBash\x1b[0m) custom_tool_call(\x1b[2mrun_shell\x1b[0m)`——action type 与 `completed` 本身不着色，普通名称仍遵守工具名列表的灰色合同；对 snapshot 分类不完备且 actions 为空精确产出 `completed client_action?(unclassified)`，不含绿色转义。真实 streaming `/responses` 内部路由用 mock upstream 跑五组对照：(a) terminal 显式 `output=[]`，stream 另含一个 unattributed event，摘要仍为 complete、actions 为空，纯文本尾段为 `completed`；(b) terminal `output` 只有完整 `message`，同样得到 clean `completed`，用于判红“所有 item 都是 unknown”；(c) terminal `output` 缺席与类型错误参数化为两例，两者都得到 `completed client_action?(unclassified)` 且不绿；(d) terminal `output` 含一个未知原生 type，得到 `completed client_action?(future_tool_call)` 且不绿；(e) terminal `output` 依次含 `function_call(Bash)`、重复的 `function_call(Bash)` 与无名 `custom_tool_call`；stream 中三个 `done` snapshot 全部故意改成 `tool_search_call(execution=server)` 并使用不同名称，所以 done 侧的 `any(required)` 为 false，而 terminal 三项全部是 `required`；三个 `done` 再以 2、1、0 的反序到达。最终尾段仍须为 `completed function_call(Bash) function_call(Bash) custom_tool_call`，三项恰好一次且 `completed` 不绿。最后一例是 source-of-truth 控制，不冒充真实上游合法分歧；全部 mock 只证明本代理的 collector、`RequestTrace → RequestLine` 接线、terminal authority、分类完备、排序与展示，不冒充真实上游本轮实况。把 `output=[]` 当缺席、把缺席或错误类型当 complete、让任何 unattributed event 阻止 complete、把所有 item 分类为 unknown、丢弃 unknown、从 `done` snapshot 收集最终 name 或 requirement、按 `done` 到达顺序输出、action 列读 terminal 但 completed 颜色偷读 done-side bool、只按 terminal status 着色或把所有 completed 一律取消着色，必须分别被上述同一组断言判红，且失败原因落在目标字段或尾段，不得由 fixture 解析错误代打。

## 明确不做

- **panel / detail 交互**（展开列表、详情页、滚动、按键解码）。现有 reducer 的 `panel_list` / `detail` 两态保留，本次不接线。**注意**：`rich.Live` 的 footer 跟着内容浮动而非钉物理底行，多行面板要钉底时这个模型可能不够用，届时需重新评估是否退回 DECSTBM，不得假设本次结论已经覆盖那个场景。
- **从 TUI 中止请求**。P1 只读边界，中止归审批系统。
- 分层遥测、请求历史面板等，均已有各自归属文档。

## 修订记录

| 日期 | 条款 | 变化 | 触发 |
|---|---|---|---|
| 2026-09-03 | 着色规则、描述回复的用词、验收 | Responses 流式直连的 `completed` 改为与 typed client-action facts 组合判读：仅在已确认无客户端行动时绿；存在 `required`、`unknown` 或集合分类不完备时不着色，并同时显示权威 status、每项行动或 `unclassified` 标记。新增颜色双向控制、explicit-empty、complete not-required、complete unknown 与 missing/malformed-unclassified 三组集合控制、反序 `done` 的排序控制，以及重复与无名 action 的端到端 oracle | 用户主动指出 `completed + function_call/custom_tool_call` 不代表工作结束，并选择 terminal status 与 client-action facts 分槽；三态、terminal `output` authority、集合完备、排序、重复、无名与 unknown 呈现为本规格推导，来源是 direct-passthrough §4、§7.1 与 §10 及 2026-09-03 独立评审 |

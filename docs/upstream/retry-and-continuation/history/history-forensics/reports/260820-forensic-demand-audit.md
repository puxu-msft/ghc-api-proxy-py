# 取证需求盘点：2026-08-20 这批线上排障到底靠什么拿到事实

调查日期：2026-08-20。纯只读盘点，未改动任何代码，只统计已发生的取证动作，不发明需求。

## 0. 覆盖范围与方法

通读的一手排障文档（按事件分组）：

- 256.9s 客户端超时：`docs/tmp/260820-server-timeout-forensics.md`、`docs/tmp/260820-client-timeout-forensics.md`、`docs/tmp/260820-downstream-keepalive-defect.md`、`docs/tmp/260820-smell-survey-streaming-pull.md`
- 空 text block 400：`docs/tmp/260820-empty-text-block-inbound-trace.md`、`docs/tmp/260820-empty-text-block-response-side.md`、`docs/tmp/260820-empty-text-block-synthesis.md`
- websearch 400（Anthropic 直通腿）：`docs/tmp/260820-websearch-400-synthesis.md`、`docs/tmp/260820-websearch-400-our-side.md`
- websearch 能力调研（非事故复盘，是上游能力探针，一并盘点因为它示范了「手动 curl 探针」这条取证手段）：`docs/tmp/260820-websearch-upstream-probe.md`、`docs/tmp/260820-websearch-on-responses-leg.md`

`ls -t docs/tmp | head -60` 扫过一遍，挑出这四组之外还有排障性质的候选（`websearch-400-copilot-api-js.md`、`websearch-400-vscode-ext.md`、`empty-text-block-copilot-api-js.md`、`review-downstream-keepalive-defect.md`、`review-shield-stopasynciteration.md`），但它们是「读参考实现源码」或「评审复核」性质，不产生新的取证手段，本文只在表格里引用其结论，不单独立项。其余 2608xx 文档（spec 评审、debug-models、websearch-fix-v2-design 等）与「取证」无关，不纳入。

证据强度分级沿用原文档的约定：**可据以行动**（原文档标"强"且给出可复核证据）／**仅是倾向**（原文档标"中"、"未坐实"或明确说"相容但未证实"）／**仅存档**（单点观察，未交叉验证）。本文自己的结论也按此分级标注。

---

## 1. 需求清单：每次排障要判定什么、需要什么事实、事实从哪来

### 1.1 事件 A——256.9s 客户端超时（07:45:09 ~ 07:49:26）

| 要判定的问题 | 需要的事实 | 实际来源 |
|---|---|---|
| 这次超时具体是哪一次请求、多长时间、什么模型 | 请求发起/结束时间戳、`model`、`session_id`/`agent_id` | **客户端 transcript**（`~/.claude/projects/.../subagents/agent-a4710f6edaa96e0bb.jsonl:77-82`）——唯一来源。`260820-client-timeout-forensics.md:12` 明说 "256.9s 这个数字在 transcript 里并不存在"，是靠相邻记录的时间戳推算（256.974s）核对上的 |
| 走的是哪个代理进程、哪份配置 | pid/cmdline/cwd/启动时间、`GHC_*` 环境变量、`load_proxy_config()` 实际解析结果 | **本项目日志层无记录**；靠 `/proc/<pid>/{environ,cmdline}`、`ps -o lstart` 等系统级取证，加上**手动运行同一份 loader 代码复算**（`server-timeout-forensics.md:56-58` 的实测命令） |
| 各超时/保活配置项的生效值，及是否真的被消费 | `sse_ping_interval`、`synthesized_response_headers_after_sec`、`stream_idle` 等的值 + 消费点是否在生产链路闭包内 | **实测探针**：`importlib` 拉一次生产入口算可达闭包（`server-timeout-forensics.md:1.5`），再用 `rg` 找每个配置字段的调用点，两条独立证据交叉 |
| 服务端对这次请求留没留记录（model/耗时/状态/协议/字节数） | history.db 记录、日志文件 | **一律没有**：`history.db` 里无 `anthropic-*` 记录（三条独立证据：组装根无 `HistoryStore`、进程 fd 无数据库文件、`history.db` 内容本身查无此请求）；服务端唯一的完成日志只写 stdout，终端已滚动，不可恢复 |
| 该次超时是不是由某个客户端侧显式配置的超时值触发 | `~/.claude/settings.json` 的 `env` 段、运行中 Claude Code 进程的 `/proc/<pid>/environ` | **客户端配置文件 + 运行进程环境实测**：三个超时开关都是 1 200 000ms，远大于 256.9s，可排除（`client-timeout-forensics.md` §6） |
| 这个失效点是否稳定复现在某个数值附近 | 历史上所有同类错误记录的时间间隔 | **对 `~/.claude/projects` 下全部 3855 份 transcript 做统计**（`client-timeout-forensics.md` §5.2），得出 243～324s 的聚集带，但明确声明"不能推出精确阈值" |
| 客户端所用运行时（Bun）本身的空闲超时天花板 | 一个受控的最小复现环境 | **手写探针**：`260820-downstream-keepalive-defect.md` §4，起本地假服务器，用 Bun 1.3.14 直接测三种服务端行为形态（A/B/C），实测出 300s 空闲杀手，且 SSE 注释帧能续命 |

### 1.2 附属机制排查——下游保活缺陷（从事件 A 牵出）

| 要判定的问题 | 需要的事实 | 实际来源 |
|---|---|---|
| ping 的调度是否真的挂在上游事件而非下游字节上 | 一段可控的 `stream_delivery` 调用，交替喂"上游 chatty"和"上游沉默"两种输入 | **读代码 + 亲手写探针**复现（`downstream-keepalive-defect.md` §1），正样本对照（沉默组 2 个 ping vs chatty 组 0 个）证明探针有分辨力 |
| 这个缺陷是否就是当次事故的根因 | 事故期间"上游是否持续发 delta"这一时序事实 | **拿不到**。transcript 只在完整 block 落盘时记录，看不见块内 delta；服务端无记录可复核。结论只能停在"相容"，标注为"仅是倾向"|

### 1.3 事件 C——空 text block 400（06:00:21/22 生产日志）

| 要判定的问题 | 需要的事实 | 实际来源 |
|---|---|---|
| 我方入站/交付代码会不会造出或清空一个 text 块 | 生产入口的 import 可达闭包、每个改写点的代码语义 | **读代码 + 实测可达性探针**（`importlib` + `rg` 调用点排查），逐一排除 31 个候选写入点（`empty-text-block-inbound-trace.md` 第 6 节判定表） |
| 交付层是否存在会主动产出空块的机制 | `stream.py` 的合成占位逻辑、`assembler.py` 的累积逻辑 | **读代码**，辅以既有单测名称（`test_synthesizes_one_empty_block_when_first_real_block_is_late`）作为"这条行为已被固化"的旁证 |
| 这次 400 的完整因果链（是谁、在哪一轮、造出的哪个空块） | 精确到毫秒的请求时间线、每个 assistant 块的内容与 `msg.id` | **客户端 transcript**（`792a44f0-.../subagents/agent-abbb204c8997953ff.jsonl:86-90`）——唯一给出这条因果链的地方，`260820-empty-text-block-synthesis.md` §1 逐行摘出 |
| 上游对"空/纯空白"的判定标准是什么 | 上游错误分类逻辑 | **反编译 Claude Code 自身可执行文件**，摘出它内部的错误匹配正则（`empty-text-block-synthesis.md` §1"上游的判据"一节）——一手但来源特殊 |
| 空块在 Responses 腿是否也会被拒 | 对真实上游发五组探针（含阳性对照） | **手动 curl 式探针**：`exp/260820-empty-text-probe/`，E1-E5 五组，E5 是阳性对照（用同一账号同一时刻复现生产 400），证明前四组的 200 是"上游看过并接受"而非"没测到" |
| 修复是否生效、有没有引入回归 | 单测、变异测试、cassette 回放 | **本项目自身测试基础设施**：13 个单测 + 变异验证（19 条中 8 条随过滤器变异转红）+ 既有 cassette |

### 1.4 事件 D——websearch 400（21:43:34 生产日志）

| 要判定的问题 | 需要的事实 | 实际来源 |
|---|---|---|
| 这条 400 走的是哪条链路（直通还是翻译） | 模型目录里 `claude-opus-5` 支持哪些端点 | **事故前一天的 live 录制 cassette**（`tests/cassettes/anthropic_to_responses_stream.json`，提交于 `e742243`）——碰巧留存的一手记录，不是为此次事故特意录的 |
| 客户端具体在 `tools` 里发了什么 | 字节级上行 payload | **拿不到**。`history.db` 无记录，代理不落盘 payload；只能靠"我们知道 `SERVER_TOOL_REJECTION_TABLE` 按 `web_search_` 前缀匹配"这一代码事实来说"dated variant 是哪个不影响根因判断"——本条明确标注为推断 |
| 既有的本地能力门为什么没接住这次请求 | 门的调用者链条、生产入口的 import 闭包 | **读代码 + `rg` 排查**，判定门只接在 legacy `app_factory` 上，新链路完全绕过 |
| 上游对各种 `web_search` 变体、子字段、`tool_choice`、`include` 的真实反应 | 对上游发一整批探针（A/B/C 三组，19 次真实推理请求） | **手动对真实 GitHub Copilot 上游发探针**，`exp/260820-websearch-probe/`，含 count_tokens 腿、`/responses` 请求侧接受度、真实响应样本三组，逐条记证据权重 |
| 参考实现怎么处理同一问题 | copilot-api-js、vscode-copilot-chat 的源码与提交历史 | **读参考仓库源码**（`~/src/copilot-api-js`、`refs/vscode-copilot-chat`），非本项目一手证据，但用于对照裁决 |

---

## 2. 缺口清单：当时拿不到、只能退而求其次的事实（按被提及次数排序）

| 排名 | 缺口 | 出现次数 | 每次导致的退路 |
|---|---|---|---|
| 1 | **实际发往上游的字节级请求 body** | 至少 4 次：`server-timeout-forensics.md` §3（只留字节数长度）、`empty-text-block-inbound-trace.md` 第 5 节（整节讨论"能不能落盘"）、`empty-text-block-synthesis.md` §8.2（"同一缺口第二次挡路"）、`websearch-400-our-side.md` 第 4 节（"取不到，而且是能力缺失不是找不到"） | 退到"用代码可达性证明我方不可能造出这个字节"这种间接论证；或建议临时开 `ANTHROPIC_LOG=debug`（未执行，见下） |
| 2 | **该次请求的服务端历史记录/完成日志（model、耗时、状态、上游协议、收发字节）** | 至少 3 次：`server-timeout-forensics.md` 第 3、4 节、`websearch-400-our-side.md` 第 4 节、`empty-text-block-synthesis.md` §8.2 | 每次都退到**客户端 transcript**；三份文档都明确写"这是唯一还存在的一手记录，不是我们自己的可观测性" |
| 3 | **上游 SSE 帧的字节级时序（delta 到达时刻、静默窗口内是否真的在发）** | `downstream-keepalive-defect.md` §3、§5（"未坐实"的核心原因） | 退到"机制上相容"这一弱结论，明确拒绝把它升级为根因 |
| 4 | **客户端 transcript 自身的分辨率上限**（只在完整 block 落盘时记一行，看不见块内 delta、看不见字节级时序、不记录重试次数） | `client-timeout-forensics.md` 第 2 节反复声明、`downstream-keepalive-defect.md` §3 | 退到"这是静默时长的上界，不是精确值"这类带保留的表述 |
| 5 | **400/异常发生时上游返回的错误响应体逐字内容与我们发出的 body 逐字内容的对照** | `websearch-400-our-side.md` 全篇；只靠生产日志里那一行摘要文本 | 退到对参考实现和真实上游做独立探针，反推可能的请求形状 |
| 6 | **pts/tmux 终端的历史回滚缓冲** | `server-timeout-forensics.md` §4 | 明确声明"不可取证"，未做任何替代 |
| 7 | **调试级日志（`ANTHROPIC_LOG=debug` / `--verbose`）** | `empty-text-block-inbound-trace.md` §5.2 | 只做了可行性实测（SDK 会把空 body 打进日志），**未实际开启**，因为需要重启且会让上游 token 明文入日志，留作用户裁决项 |

---

## 3. 哪些缺口是"一条结构化记录就能补上"的

以下逐项列出：如果代理在**请求终结时**（含正常完成、400、超时、连接中断）落一行结构化记录，需要哪些字段，能免掉哪次翻 transcript。

| 需要记录的字段 | 对应的缺口排名 | 免掉的取证动作 |
|---|---|---|
| **实际发往上游的完整 body**（至少在 400/异常路径上；正常路径可只记 messages 的结构指纹，如 block 数、每块 type、text 长度） | #1、#5 | 免掉"读代码逐点证明我方不可能造出空块/透传 server tool"这类间接论证；`websearch-400-our-side.md` 里那道"最小判别实验"也不必再手动跑一遍 |
| **上游原始 SSE 帧序列**，或至少每个 `content_block_start/delta/stop` 与 `output_item.added/done` 的到达时间戳 | #1、#3 | 直接把 `downstream-keepalive-defect.md` 里"未坐实"的那句话变成可核实——不需要再靠客户端 transcript 反推静默窗口的上界 |
| **上游响应头**（状态码、`http_version`、`request_id`） | 部分 #2 | 减少"这次请求走的是哪条链路"这类需要翻 cassette 碰运气才留存的判断 |
| **各阶段时间戳**：请求受理、路由决策完成、上游连接建立、上游首字节、每次下游写出、请求完成/失败 | #2、#3 | 直接替代整个"该次请求的服务端历史记录"缺口——不再需要退到客户端 transcript 才能知道耗时和状态 |
| **重试 attempt 记录**（仅限我方到上游的重试，次数、每次状态码/耗时） | 部分 #2 | 能回答"这次 400 之前我们自己有没有重试过"，但**不能**回答客户端到我们这一侧的重试（见第 4 节反向核对） |
| **错误响应体原文**（400 时上游返回的 body 逐字） | #5 | 直接替代 `websearch-400-our-side.md` 花大篇幅去参考实现和真实上游反推错误形状的过程 |
| **收发字节数** | 已有雏形（`trace.bytes_in`/`received` 已实现但只落 stdout） | 只需要把已经在算的这些字段真正落盘，而不是发明新字段 |

**这条落地需要的前提，本次盘点里已有的判断**：`server-timeout-forensics.md` 第 3 节明确指出 `pipeline_app.py` 的 `_Trace`/`RequestLine`/`_log_completion` **已经收集了上面几乎全部字段**，缺的只是"只写成一行日志，这行日志只去了 stdout"——即落地成本主要是**加一个文件/数据库 sink**，而不是重新设计采集点。

---

## 4. 反向核对：哪些事实即使记了也没用

以下几类即便代理自己落盘再详细，也**替代不了**当前的取证手段，不要因为本次盘点而误以为"补一条记录就能覆盖所有缺口"：

1. **客户端到我方的重试次数与时序**（`CLAUDE_CODE_MAX_RETRIES=30`）。这是 Claude Code 客户端内部状态，重试对我们表现为"新的一次独立连接/请求"，我们无法在服务端记录里把它们标记为"同一逻辑请求的第 N 次尝试"——除非额外做跨请求聚类（按来源 IP + 短时间窗口），而那是推断不是记录。`client-timeout-forensics.md` 第 2 节把这一点列为"本次调查确定的一个未知项"，即使加了完成日志，这一项依然是未知项。
2. **客户端运行时（Bun）自身的空闲超时具体数值与触发机制**。`downstream-keepalive-defect.md` §4 是靠**独立起一个假服务器、直接用 Bun 二进制测**才拿到 300s 这个数字的——这是对客户端实现的黑盒测试，不是我们服务端能记录的东西，我们记多细都测不出客户端的超时阈值。
3. **pts/tmux 的终端回滚缓冲**。这是操作环境的偶然产物（有没有 tmux、终端有没有被清屏），不是我们服务的可观测性所能覆盖的层面，也不该被当作排障能力来设计——它本来就是"日志只写 stdout 不落盘"这个已知问题的症状之一，正确的修法是加文件 sink，不是指望终端缓冲。
4. **上游内部为什么接受或拒绝某个字段**（例如 `include` 参数为什么被吃掉但不生效、`allowed_domains` 为什么导致 400）。这些是上游的内部实现细节，只能通过对上游发真实探针获得（`websearch-upstream-probe.md`、`websearch-on-responses-leg.md` 做的正是这件事），我们自己记录任何请求/响应字段都无法"提前知道"上游还没发生过的行为。
5. **Claude Code 可执行文件内部的错误分类正则/first-party 判断逻辑**。`empty-text-block-synthesis.md` 与 `downstream-keepalive-defect.md` 都靠**反编译/读客户端二进制**才拿到这些事实，这类信息只存在于客户端产物里，我们服务端的任何记录都不会包含它。

**这条核对的意义**：第 3 节列出的"一条记录能补上"的缺口，全部集中在**我方服务端与上游之间**这一段的可观测性；而第 4 节这五类分别落在**客户端内部行为**、**客户端运行时黑盒特性**、**操作环境偶然性**、**上游内部实现**、**客户端二进制内部逻辑**这五个我方记录天然够不着的地方。补记录能让"服务端←→上游"这一段的排障不再依赖客户端 transcript 侥幸留存，但不能让"客户端←→服务端"和"服务端←→上游内部决策"这两段的黑盒探测手段（transcript 翻查、真实探针、反编译）退场。

---

## 5. 简要结论（可据以行动）

1. 这批排障里**唯一反复被验证有效的一手事实来源分层清楚**：服务端行为用"读代码 + 实测可达性/探针"，上游行为用"对真实上游发探针"，客户端行为用"翻 transcript 或黑盒测客户端二进制/运行时"。三层没有相互替代关系。
2. 本项目当前的可观测性缺口**高度集中且已被自己的代码结构证实**：`_Trace`/`RequestLine` 已经采集了绝大多数排障需要的字段，只是没有 sink（只写 stdout，不落文件不落 history）。这是本次盘点里权重最高、最值得直接行动的一条。
3. 400/超时时的**上行 body 快照**和**上游 SSE 帧时序**是当前缺口里唯一还没有任何雏形的两项，补上它们的收益最大——它们分别是 websearch 400、空 text block 400、下游保活缺陷三次调查里都被点名"要坐实还差这个"的项。
4. 不要把"完成时落一行记录"这件事扩大成覆盖客户端重试、客户端运行时超时、上游内部决策逻辑——这三类无论记录做得多细都够不着，本批文档里对应的证据全部来自专门的黑盒探针或反编译，不是我方请求生命周期内的字段。

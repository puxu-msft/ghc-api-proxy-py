# `anthropic/sanitize/` 家族在新链路上的去向 —— 是有意设计，还是迁移残留？

**日期**：2026-08-20
**性质**：纯只读代码考古。未修改任何源码或既有文档。
**基线**：HEAD `0871581`。工作树有同伴大量未提交改动（`src/app/server/handler.py`、`src/app/pipeline/subscribers/server_tools.py`、`src/app/pipeline/delivery/*` 等）。**本文行号取自本次阅读时刻的工作树**，引用时以符号名为准、行号为辅。
**问题**：`sanitize` 家族不在新链路上，是否为了给面向用户的 hook system 让路？

---

## 0. 判定（先行）

**(c) 无人决定的意外后果。证据强度：强，可据以动手。**

更精确地说，要把两件事拆开：

| 事实 | 判定 | 证据 |
|---|---|---|
| 新链路不引入 `app.pipeline.executor` / `app.server.app_factory` | **(a) 有意的架构决定** | 提交 `aba73fb`「refactor: make the dependency graph tell the truth before moving anything」，理由是 `D-ARCH = B` 要求 wire shape 只在 codec 边界；`tests/unit/test_module_boundaries.py:25-31` 把它固化成断言 |
| `sanitize` 家族的清洗行为在新链路上不再执行 | **(c) 无人决定的意外后果** | 见下 |
| 这个排除是为了给 hook system 让路 | **不成立，且有反向证据** | 见 §1.3 |

**(c) 的直接证据**：

- `docs/tmp/260820-empty-text-block-synthesis.md:52` —— 「守卫是在架构切换时被留在旧链路上的」。
- 提交 `b2576eb`（2026-08-20，`fix: stop relaying a text block upstream refuses to read`）的提交信息原文：

  > The rule was already written down. `filter_empty_text_blocks` has applied it since the existing chain, with the predicate the reference implementation uses — but its only callers are on that chain, and `test_module_boundaries` pins that the new one cannot reach them. **This is the same shape as the server-tool gate that was left behind in the same move: a guard that exists and is never called.**

- 项目记忆 `guards-stranded-on-the-legacy-chain.md` 记录该形态在 2026-08-20 一天内**连续击发三次**：`web search tool is not supported` 400、`text content blocks must be non-empty` 400、以及上游流无终止事件时伪造 `end_turn` 的**静默假成功**。一件被决定过的事不会以三次生产故障的形式被发现。

**注意一处需要修正的前提**：任务简报说 sanitize 家族「**不在** `app.server.pipeline_app` 的 import 闭包里」。这一句在字面上不成立，实测（read-only 探针，`PYTHONPATH=src uv run python`，导入 `app.server.pipeline_app` 后读 `sys.modules`）：

| 模块 | 在闭包内 |
|---|---|
| `app.anthropic.sanitize` | **是** |
| `app.anthropic.sanitize.result` / `.text_blocks` / `.tool_blocks` | **是** |
| `app.anthropic.sanitize.deduplicate_tool_calls` / `.read_tool_result_tags` / `.system_reminders` | 否 |
| `app.pipeline.executor` / `app.pipeline.context` / `app.hooks` / `app.server.app_factory` | 否 |

闭包共 112 个 `app.*` 模块。`sanitize` 进来是一条 import 副作用链：`pipeline/anthropic_request_hook.py:14` 导入 `app.anthropic.thinking.destack` → 触发 `src/app/anthropic/__init__.py:1` 的 `from app.anthropic.sanitize import sanitize_messages` → 拉入 `result` / `text_blocks` / `tool_blocks`。（同一机制早已由 `docs/tmp/260820-empty-text-block-inbound-trace.md:132-141` 记录。）

**成立的是更弱也更要紧的那句：被 import ≠ 被调用。** `sanitize_messages` 的两个调用点 `src/app/anthropic/client.py:157` 与 `src/app/pipeline/executor.py:168` 都在 legacy 链路上，新链路一次都不调用它。

这个区别有操作后果：`test_module_boundaries.py` 断言的是「不引入 `app.pipeline.executor`」，**没有任何断言禁止新链路引入 `app.anthropic.sanitize`** —— 后者本来就已经在闭包里了。所以那道守卫**不构成把 sanitize 能力搬回新链路的障碍**，说「守卫把 sanitize 排除在外」会高估它的约束力。

---

## 1. 书面依据盘查

### 1.1 用户亲笔（`docs/.human-controlled/`，权重最高）

- `docs/.human-controlled/MAIN.md` —— **全文零次提及**「清洗」「sanitize」「配对」「tool_result」（`rg -n -i '清洗|sanitiz|tool_result|配对'` exit 1）。用户的权威文档从未描述过消息清洗，因此**不存在一条用户亲笔的裁决把 sanitize 排除在新链路之外**。
- `docs/.human-controlled/config.example.yaml:436-453` —— `hooks:` 一节，六个面向运维的订阅点，全为空列表（详见 §3）。
- `docs/.human-controlled/config.example.yaml:608` —— `strip_system_reminder_from_Read: false`。**这是 sanitize 家族唯一在用户亲笔配置里出现的成员**，而且它被放在 `hook_fix_anthropic_request:` 节下（第 512 行起），**不在 `hooks:` 节下**。也就是说，用户亲笔把这项清洗定位成「anthropic 请求处理」的一个配置开关，而不是一个 hook 订阅项。
- 家族其余成员（tool pair/orphan repair、空 text 块、空消息删除、内容去重）在用户亲笔配置里**完全不出现**——与「mandatory sanitizer 无配置面」是一致的。

### 1.2 冻结 Spec（`docs/2604-rewrite/hooks-tokenization-spec.md`，状态「已实施并通过测试」，2026-07-17）

§7 末尾的不可 hook 化清单（约 `:206-213`）：

> 以下不可 hook 化或不可禁用：
> - tool pair/orphan repair、空 block/message legality 等协议 sanitizer。
> - 模型解析、认证、header security floor、审批、限流、请求状态机。
> - history lifecycle 与 transport/streaming 正确性。

`docs/2604-rewrite/sanitize-pipeline.md:5` 同向：

> 协议必需的消息合法性修复由 `anthropic/sanitize/` 承担，**不能被用户 hook 禁用**。可选改写位于 mandatory sanitizer 前后的 payload hooks。

`docs/2604-rewrite/hooks-system.md:62` 第三次重述同一条。

### 1.3 因此：「为 hook system 让路」这个假说被书面依据**证否**，不只是「无依据」

三份文档一致把 tool pair repair 与空块合法性归为 **mandatory sanitizer，明写不可 hook 化、不可禁用**。把它们改造成 hook／订阅项以便用户禁用，等于推翻一条冻结条款。

代码里还有一条独立的同向陈述，`src/app/pipeline/subscribers/__init__.py:7`：

> **Not configurable, on purpose.** Protocol repair is a mandatory sanitizer: a request that upstream rejects whole is not a preference. The operator-facing `hooks:` subscription points in `config.example.yaml` are a different layer with their own undecided question — what a list item names — and this package deliberately does not pre-empt that answer by inventing a key of its own.

**证据强度：强。** 四处独立文本（两份 2604-rewrite 文档、一份冻结 spec、一处模块 docstring）方向一致，无一处相反。

### 1.4 已裁决的方向与「让路」正好相反

`.dev/human-controlled-docs-candidates/pipeline-subscriptions.md:5`：

> 方向已由用户裁决：**订阅机制吸收 hooks**。本文只处理「怎么吸收」，不重开「要不要吸收」。

`.dev/human-controlled-docs-candidates/uncovered-modules.md:18` 复述同一裁决。`docs/2604-rewrite/hooks-system.md:82` 第三次复述。

也就是说：**`src/app/hooks/` 那套是被裁决要退役的一方，不是新增能力应当等待的一方。**「等 hook system 落地」在方向上是等一个已判定要被吸收的机制。

`hooks-system.md:108` 记录吸收进度：

> **吸收本身**。`src/app/hooks/` 的四类 typed 契约、loader、executor 仍只接在 legacy app 上，没有一个内置 hook 迁过来。

### 1.5 `test_module_boundaries.py` 的引入动机（pickaxe 结果）

`git log --oneline -- tests/unit/test_module_boundaries.py` 只有一条：`aba73fb`（2026-08-19）。提交信息全文的动机是**测量两条链的模块划分**，为「按角色重组」做准备：

> Measured before this commit: all 175 reachable modules were reachable from *both* entry points, so by that evidence the two chains were one. … With the re-export gone the same measurement says 86 modules belong only to the existing chain, 39 only to the new one, and 50 are genuinely shared.
> … `D-ARCH = B` puts wire shapes at the codec boundary and nowhere inside; that is only checkable if importing the kernel does not also import everything predating it.

**全文没有一个字提到 sanitize、清洗、hook 或订阅。** 这道守卫的目的是防止 re-export 再次把两条链合并，不是宣告某个功能族被弃用。

`git log -S'sanitize_messages' --oneline` 共 5 条，全部是 2026-07 的 Phase 2/3/4 建设期提交与文档提交，**没有任何一条记录「把 sanitize 从新链路上摘掉」的决定**——因为新链路从来没接过它，不存在「摘掉」这个动作。

---

## 2. 逐函数对照清单

先澄清一处术语：用户提到的「`fix_anthropic_request` 里的 destack 与 empty-thinking」**不属于 sanitize 家族**——`destack_content` 与 `sanitize_empty_thinking` 定义在 `src/app/anthropic/thinking/`（`destack.py` / `protection.py`），由 `src/app/pipeline/anthropic_request_hook.py:85,89` 调用。它们是 thinking 管道的成员，接线时间是 2026-08-17（`e7c1484`）。所以它们不进本表，但它们证明了一件事：**新链路补回 legacy 能力的既有做法，是直接复用 `app.anthropic.*` 下的现成实现，而不是等任何机制落地。**

sanitize 家族本身逐项：

| # | 能力 | 定义 `file:line` | legacy 调用点 | 新链路状态 | 依据 |
|---|---|---|---|---|---|
| 1 | tool pair/orphan repair ＋ 工具名大小写修正 | `src/app/anthropic/sanitize/tool_blocks.py:4` `process_tool_blocks` | 仅 `sanitize/__init__.py:11`（即只被 `sanitize_messages` 调） | **未补回，零实现** | `rg -n -i 'orphan\|tool_use_id\|pair' src/app/pipeline/ src/app/server/` 在请求方向零命中相关逻辑（命中项全是 TLS 证书对、translator pair、reasoning carrier 的 `object_pairs_hook`）。冻结 spec §7 明写它「不可 hook 化或不可禁用」，却在新链路上根本不跑 |
| 2 | 空／纯空白 text 块删除 | `src/app/anthropic/sanitize/text_blocks.py:4` `filter_empty_text_blocks` | 同上（`__init__.py:15`） | **已补回，但不是移植，能力有增有减** | `src/app/pipeline/subscribers/blank_text.py:69` `drop_blank_text_blocks`，事件 `attempt.prepare`。差异见 §2.1 |
| 3 | 清洗后 content 为空的消息整条删除 | `src/app/anthropic/sanitize/__init__.py:16-20`（内联）；另见 `tool_blocks.py:101-105` | 同上 | **未补回，且已就地作出相反裁决** | `blank_text.py:109-112` 明写：一条只剩空白块的消息**原样发出**并打 warning，理由是「没有任何已测过的改写既合法又保义」。这是新链路上一次显式的、写明理由的判断，不是遗漏 |
| 4 | Read 工具结果里的 `<system-reminder>` 剥离 | `src/app/anthropic/sanitize/read_tool_result_tags.py:7` `strip_read_tool_result_tags`；委托 `system_reminders.py:6` `strip_system_reminders` | `src/app/hooks/builtin/payload.py:37`（legacy `app_factory` 装配） | **未补回。配置键存在但零消费者** | `docs/.human-controlled/config.example.yaml:608` 与 `src/app/config/schema.py:256` 都有 `strip_system_reminder_from_Read`，`rg` 在 `src/` 下**零读取者**（`docs/tmp/260820-external-rewrite-surface.md:241` 与 `260820-empty-text-block-inbound-trace.md:233` 两份独立盘点一致）。默认 `false`，所以当前行为上看不出来；**把它设成 `true` 是静默无效** |
| 5 | 按内容签名去重工具轮次 | `src/app/anthropic/sanitize/deduplicate_tool_calls.py:7` `deduplicate_tool_calls` | **全仓无生产调用点**，只有 `tests/unit/test_anthropic_deep_sanitize.py:41` | **未补回；可判为「默认不需要」，但配置面缺席** | `docs/2604-rewrite/sanitize-pipeline.md:50`：它与 ID 配对修复正交，ID 不同而内容相同的完整工具轮次「在协议上合法，不应默认删除」，默认关闭。legacy 侧的开关 `AppSettings.hooks.deduplicate_tool_calls`（`src/app/config/settings.py:148`）在新 schema `ProxyConfig` 里**不存在**。`.dev/human-controlled-docs-candidates/uncovered-modules.md:42` 已把该文件列入「已实现但当前无生产消费者」 |
| 6 | 编排入口 | `src/app/anthropic/sanitize/__init__.py:7` `sanitize_messages` | `anthropic/client.py:157`、`pipeline/executor.py:168` | **未补回**。它只是 1+2+3 的组合，新链路把 2 换成了别的实现，1 与 3 缺席 | — |

### 2.1 第 2 项「已补回」的具体差异（不要当成等价移植）

| 维度 | legacy `filter_empty_text_blocks` | 新链路 `drop_blank_text_blocks` |
|---|---|---|
| 判据 | `block.type == "text" and not (block.text or "").strip()` | 同判据，另加：`text` 为 `None` 算空；`text` 非字符串**不算**空（`blank_text.py:30`，理由写在 docstring） |
| 落点 | 翻译之前，每请求一次 | `attempt.prepare`，**翻译之后、在重试循环内**，每 attempt 一次 |
| 门控 | 无条件 | **仅当 `context.target_format is WireFormat.ANTHROPIC_MESSAGES`**（`blank_text.py:74`），依据是 `exp/260820-empty-text-probe/` 对上游的实测：`/responses` 对空 `input_text` 答 200，`/v1/messages` 同批次同凭据答 400 |
| 覆盖字段 | 仅 `messages[*].content` | `messages[*].content` **＋ `system` 数组**（`blank_text.py:78-89`，`system` 全空时删掉整个 key） |
| 相邻 thinking 保护 | 无 | 有：删掉夹在两个 thinking 块之间的空块时补 `SYNTHETIC_SEPARATOR`（`blank_text.py:64-65`） |
| 整条消息变空 | **删掉该消息**（`__init__.py:16-20`） | **原样发出并 warning**（`blank_text.py:109-112`） |
| 数据层 | typed `AnthropicMessage` | raw `dict` payload |

**结论：这不是把旧函数搬过来，而是就同一条规则重新做了一次判断，且更强。** 说明补回工作是按生产故障逐条驱动的，不是按一份清单执行的。

### 2.2 有没有书面的迁移清单？

**没有。** 判据性检索：`docs/` 下（排除 archive）不存在任何列举「sanitize 家族哪些能力还欠着」的文档。最接近的是两份 2026-08-20 的临时审计表，它们是排障副产品而非迁移台账：

- `docs/tmp/260820-empty-text-block-inbound-trace.md:144-151` —— 六个函数逐个标注「生产调用点 / 在生产腿上？」，结论全是「否」。
- `docs/tmp/260820-external-rewrite-surface.md:231-246` —— 各 `hook_*` 配置节的接线状态表，`strip_system_reminder_from_Read` 一栏写「**无**」。

`docs/agents/service-cutover/readiness.md` 是切换就绪度台账，但它只在 tooling 一行提到 sanitized-name restore，**没有 sanitize 家族的条目**。

所以：**这不是一件「有清单、正在执行」的迁移（(b)），而是一件「没人建过清单」的事（(c)）。** 本表是我所知的第一份逐函数对照，权重：由静态可达性与 `rg` 零命中/唯一命中判定，**强**。

---

## 3. hook system 的现状

### 3.1 `config.example.yaml` 的 `hooks:` 一节定义了什么

`docs/.human-controlled/config.example.yaml:436-453`，节标题「模块化与钩子 / Modularization & Hooks」，六个键，全部默认空列表：

| 键 | 用户亲笔的说明 |
|---|---|
| `on_client_request_parsed` | 当客户端请求被解析、已知路由模型后触发 |
| `on_upstream_request_ready` | 当发往上游的请求已准备好（但还没发）时触发 |
| `on_upstream_sse_block_ready` | 当上游 SSE 流式响应的完整块已准备好时触发 |
| `on_client_sse_block_ready` | 当发往客户端的 SSE 流式响应的完整块已准备好（但还没发）时触发 |
| `on_upstream_request_closed` | 当上游请求结束时触发 |
| `on_client_request_closed` | 当客户端请求结束时触发 |

schema 侧 `src/app/config/schema.py` 的 `HooksConfig` 把六项建模成 `list[str]`，**零消费者**——`rg` 的全部命中只有 schema 定义本身、两处注释引用（`src/app/server/handler.py` 与 `src/app/pipeline/anthropic_request_hook.py:6`，都写「这是 spec 的 `on_client_request_parsed` 时刻」）、以及一条断言默认为空的单测。

### 3.2 与 `attempt.prepare` 的关系：**两层，不是同一套**

`src/app/pipeline/subscribers/__init__.py:7` 与 `docs/2604-rewrite/hooks-system.md:106` 都明写这是「不同的层」。具体对应关系（`docs/tmp/260820-external-rewrite-surface.md:220-227` 的映射表，我复核后同意）：

| 运维订阅点（配置面，用户亲笔） | 新链路上的真实接缝（驱动内部） | 现状 |
|---|---|---|
| `on_client_request_parsed` | `server/handler.py` 调用 `fix_anthropic_request` 处，**翻译之前** | 已有硬编码函数，无注册表、无名字、不可禁用、不可排序 |
| `on_upstream_request_ready` | `pipeline/direct_driver/base.py` 的 `attempt.prepare` | **机制齐备**，现有两个内置订阅者 |
| `on_upstream_sse_block_ready` | `pipeline/delivery/stream.py` 的 `assembler.push(event)` 之后 | 无接缝 |
| `on_client_sse_block_ready` | `pipeline/delivery/stream.py` 的 `for ready in released:` | 无接缝 |
| `on_upstream_request_closed` | `base.py` 的 `request.succeeded` / `request.failed` | 事件已发布，零订阅者 |
| `on_client_request_closed` | `pipeline_app.py` 的 `_tracked_delivery` `finally` | 无接缝 |

**关键差别**：`attempt.prepare` 是**驱动拥有**的事件（事件名由发布它的驱动拥有，`hooks-system.md:89`），发布在**重试循环内**、**翻译之后**；`hooks:` 六点是**运维声明的**、按请求生命周期命名的、跨越请求与响应两个方向的配置面。前者是后者的一个候选实现基座，不是同一个东西。

### 3.3 那道未决裁决具体是什么

`.dev/human-controlled-docs-candidates/config-migration-gaps.md`「hook 列表项的语义与单 hook 超时」一节原文：

> **新**：`hooks` 一节已有六个订阅点，但**列表项指什么没有说明**（模块路径？已注册订阅者的 id？），实现暂按 `list[str]` 建模、无消费者。**单 hook 超时**也没有承载。

`pipeline-subscriptions.md:71-75` 把它列为待用户决定的三点之一（第 3 点），另两点是：

1. 「修改公共对象」的写入规则取哪一种（唯一写者 / 后写覆盖 / 其它）；
2. 现有 `HookErrorMode` 的语义是保留还是并入异常体系。

**这道裁决的分叉后果很实在**：列表项若是**模块路径** → 第三方 Python 模块插件形态，要给新 `ProxyConfig` 加 `hooks.modules` / `hooks.disabled` 字段（目前只有 legacy `AppSettings` 有）；若是**订阅者 id** → 声明式启用/停用/排序，运维不引入外部代码执行，但需要一张内置订阅者表与「配置里写了不存在的 id」的启动期报错。

**内置订阅者的配置面为什么现在缺席，已经有答案且不依赖这道裁决**：`subscribers/__init__.py:7` ——协议兼容性修复是 mandatory sanitizer，「upstream 整条拒收的请求不是一种偏好」。所以它压根不该有开关，不是在等裁决。等这道裁决的是**运维订阅点**那一层。

### 3.4 一处文档与代码的不一致（应更正）

`docs/tmp/260820-empty-text-block-inbound-trace.md:168-172` 断言「生产环境注册了**零个**订阅者」「带 `subscribers=` 的调用点为零」。

**该结论已在同日被推翻。** 现状：`src/app/server/composition.py:41` 导入 `register_builtin_subscribers`，`:219-220` **无条件**对 registry 调用它，`:226` freeze 后装进 `Chain`。所以生产链路上 `attempt.prepare` 现在有两个订阅者（`builtin:server-tool-capability`、`builtin:blank-text-blocks`）。

该临时文档写于订阅者接线落地之前，属于时点差而非错误，但它是排障时会被再读到的文件，**建议在 §3.2 补一行时间戳更正**。（我未修改任何文件。）

---

## 4. 我的判断：新增清洗该加在哪

**结论：继续加在 `src/app/pipeline/subscribers/`（或 `fix_anthropic_request`，判据见下），不要等 hook system。证据强度：强，可据以动手。**

四条理由，每条都落在书面依据上：

1. **等不到。** 用户已裁决的方向是「**订阅机制吸收 hooks**」（`pipeline-subscriptions.md:5`），`src/app/hooks/` 是被吸收的一方。等它落地 = 等一个已判定要退役的机制。而吸收本身「没有一个内置 hook 迁过来」（`hooks-system.md:108`），进度为零。
2. **搬过去会推翻冻结条款。** tool pair repair 与空 block/message legality 在 `hooks-tokenization-spec.md` §7 被明列为**不可 hook 化、不可禁用**；`sanitize-pipeline.md:5` 与 `hooks-system.md:62` 各复述一次。把 mandatory sanitizer 变成 hook 项等于开一道它按合同不该有的开关。
3. **两层本来就不冲突，不存在「统一搬过去」这个终点。** `subscribers/__init__.py:7` 已经把边界说清：内置订阅者是 mandatory 层、无配置面；`hooks:` 六点是运维层、语义未决。订阅者不会因为 hook system 落地而需要搬家——反过来，hook system 落地时最可能的形态就是**在同一个 `SubscriberRegistry` 上再开放一层配置化注册**，届时既有订阅者原地不动即可被 `hooks:` 的 id 列表引用。
4. **既有做法已经这么走了，且被评审确认过。** 2026-08-20 一天内两条修复（`builtin:server-tool-capability`、`builtin:blank-text-blocks`）都落在 subscribers，评审记录在 `docs/tmp/260820-review-server-tool-subscriber.md`、`260820-review-blank-text-subscriber.md`，并被回写进 `hooks-system.md:98-102` 与 `pipeline-subscriptions.md:35-41`。

### 4.1 但真正的分叉不是「subscribers vs hook system」

**是「翻译前的 `fix_anthropic_request` vs 翻译后的 `attempt.prepare` 订阅者」。** 判据只有一条：**这条规则属于哪个 endpoint。**

- 规则的成因是**上游端点拒收某个形状** → 放 `attempt.prepare` 订阅者。此时 payload 已是目标 wire 格式，读 `context.target_format` 能知道「谁将要读这个 body」，且天然在重试循环内。`blank_text.py:9` 的 docstring 把这条判据写成了一句可引用的话：**「Format repair belongs where the format is going, not where it happened to arrive.」**
- 规则属于**Anthropic 协议本身的合法性**、必须在两条腿上都成立 → 放 `fix_anthropic_request`。因为 `attempt.prepare` 发布在翻译之后，Responses 腿上的 payload 已经没有 `messages` 了（`anthropic_request_hook.py:1-6` 明写这是选址理由，且对应 spec 的 `on_client_request_parsed` 时刻）。

**这条判据对本表第 1 项有直接后果**：tool pair/orphan repair 是 Anthropic 协议合法性修复，两条腿都要，所以它**不能**放 `attempt.prepare` 订阅者——那会只覆盖 Anthropic 直通腿。它的落点是 `fix_anthropic_request`，或者需要在翻译前新开一个订阅点。这一点值得在动手前先向用户点明。

### 4.2 需要用户裁决的点

1. **tool pair/orphan repair 要不要补回新链路？** 冻结 spec §7 说它「不可禁用」，而它现在**根本不执行**。这是文档与代码之间一处实打实的不一致，而且和其余两次击发不同——它至今**没有已知的生产击发记录**（我没有找到对应的 400），所以它是一个未触发的敞口而不是一次故障。补它要新写代码（不是移植：legacy 实现吃 typed `AnthropicMessage`，新链路是 raw dict），成本不小。**证据强度：不一致本身是强证据；「值不值得现在补」是待裁决，不是我能定的。**
2. **翻译前是否需要一个具名订阅点？** 目前翻译前只有 `fix_anthropic_request` 这个「写死在 handler 里、无名字、不可排序、不可追加」的函数（`external-rewrite-surface.md:56`）。若第 1 项要补、且将来还有同类，值得把它升格成 `on_client_request_parsed` 事件；但这会新增一个事件名，属于机制扩张，应由用户点头。
3. **`strip_system_reminder_from_Read` 与 `deduplicate_tool_calls` 这两项「可选清洗」的归宿。** 它们和前面四项不同——它们**本来就带用户配置开关**，是 hook/配置面的正当候选。但承载它们也不必等 hook system：`fix_anthropic_request` 已经在读 `hook_fix_anthropic_request.thinking.*` 的键了，`strip_system_reminder_from_Read` 就在同一节里（`config.example.yaml:608`），接线路径是现成的。**当前状态是「用户亲笔写了这个键、schema 里有、代码里没人读」**，属于同族的「配置已定、行为缺席」缺口。

---

## 5. 附：本文动用的判据性检索与探针

全部只读，未产生任何持久副作用。

```
git -C <repo> log -S'sanitize_messages' --oneline                # 5 条，全为 2026-07 建设期
git -C <repo> log --oneline -- tests/unit/test_module_boundaries.py   # 唯一提交 aba73fb
PYTHONPATH=src uv run python -c "import importlib,sys; importlib.import_module('app.server.pipeline_app'); ..."
rg -n 'anthropic\.sanitize|sanitize_messages|process_tool_blocks|filter_empty_text_blocks' src/ tests/
rg -n -i 'orphan|tool_use_id|pair' src/app/pipeline/ src/app/server/
rg -n -i '清洗|sanitiz|tool_result|配对' docs/.human-controlled/MAIN.md   # exit 1
```

---

## 6. 相关文档

- `docs/tmp/260820-external-rewrite-surface.md` —— 改写接入点全集盘点（本文大量复用，未重复其结论）
- `docs/tmp/260820-empty-text-block-inbound-trace.md` —— 入站链路逐点排查（§3.2 已过时，见本文 §3.4）
- `docs/tmp/260820-empty-text-block-synthesis.md` —— 空 text 块 400 的根因与两片修复
- `.dev/human-controlled-docs-candidates/pipeline-subscriptions.md` —— 订阅机制吸收 hooks 的候选路径与三个未决点
- `.dev/human-controlled-docs-candidates/config-migration-gaps.md` —— hook 列表项语义未决点原文
- `docs/2604-rewrite/hooks-tokenization-spec.md` —— 冻结 spec，§7 不可 hook 化清单
- 项目记忆 `guards-stranded-on-the-legacy-chain.md` —— 同一形态的三次击发

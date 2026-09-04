# 评审：server-tool 剥离订阅者与内置订阅者载体

**日期**：2026-08-20
**评审对象**（工作树未提交状态，其余未提交改动属并行会话，未纳入）：

- `src/app/pipeline/subscribers/__init__.py`（新增）
- `src/app/pipeline/subscribers/server_tools.py`（新增）
- `src/app/server/composition.py`（`build_chain` 两处）
- `tests/unit/test_subscribers_server_tools.py`、`tests/unit/test_builtin_subscribers.py`（新增）

**结论**：`needs-fix`。**blocker 0，major 2，minor 8**。核心剥离逻辑正确，判据轴选对了，剥离清单的取舍在证据上站得住；问题集中在三处漏网路径（都已用探针复现）、一条声称覆盖面大于实际覆盖面的守卫，以及与冻结 spec 的文本冲突未记录。

**本次执行的验证**（只读 + `/tmp` 下的一次性探针，未修改仓库任何文件）：

| 项 | 命令 | 结果 |
|---|---|---|
| 新增测试 | `uv run pytest tests/unit/test_subscribers_server_tools.py tests/unit/test_builtin_subscribers.py -q` | 14 passed |
| 受影响的 http 测试 | `uv run pytest tests/http/test_pipeline_app.py -q` | 48 passed（`build_chain` 现在无条件注册内置，未影响这些用例） |
| Lint | `uv run ruff check <四个文件>` | All checks passed（未运行 `ruff format`） |
| 类型 | `uv run pyright <四个文件>` | 0 errors |
| 分辨力复核 | `/tmp/probe_mutation.py`，把 `_REJECTED_TYPE_PREFIXES` 置空后调用 `adapt_server_tools` | 声明原样留下 → 绿灯确实由该常量支撑，设计稿的变异结论独立复现 |

---

## Major

### M1. 冻结 spec `hooks-tokenization-spec.md:126` 的文本与本次行为冲突，且没有任何文档记录这条裁决改了它

`docs/2604-rewrite/hooks-tokenization-spec.md:126`（§5.2 内）写着：

> 协议修复是不可禁用的 mandatory sanitizer……只处理 client tools；`server_tool_use` 与 `*_tool_result` 不进入配对修复，**也不获得任何 server-tool 降级、过滤或重试支持**……项目**只提供清晰错误**与 release note，不保留隐式 downgrade sanitizer，否则实质上仍在维护 server-tool support。

本次落地的正是「server-tool 过滤」，且是隐式的（客户端看不到自己的工具被拿掉，只有一条服务端日志）。同一句话还把「只提供清晰错误」写成项目立场——那是 `260820-websearch-400-synthesis.md` 的选项 B，而用户 2026-08-20 裁决选了 A。

**边界本身判对了**：那句话的上下文是 §5.2 的 tool pair/orphan 修复算法，主语是历史里的 `server_tool_use` / `*_tool_result` 块；本次只动 `tools[]` 声明，不碰历史，这是两个不同的面，划分正确（这一条回答提问 7 的前半）。**问题是没人去改那句话。** 它现在可以被逐字读成「禁止本次落地的东西」，而 spec 按项目工作流「在其外部合同存续期间保持规范性」。

**具体失败场景**：下一个读 spec 的实现者（或下一轮的评审 agent）按 `:126` 判定 `builtin:server-tool-capability` 违反冻结合同，把它删掉或改成显式 400——用户已经裁决过的方向被第二手文档翻回去。这正是 `what-decided-is-decided` 想防的那种事。

**建议**：在 `hooks-tokenization-spec.md:126` 之后补一句修订，注明 2026-08-20 用户裁决把「Anthropic 腿的 `tools[]` server-tool 声明」从该条排除，并指向 `260820-websearch-fix-v2-design.md` §6；同时说清「历史块」仍按原文的 breaking removal 处置。属文档改动，不涉代码。

### M2. `tests/unit/test_builtin_subscribers.py` 只锁住了 `attempt.prepare` 一个桶，而 `subscribers/__init__.py:17` 声称它锁住了「注册的集合」

`src/app/pipeline/subscribers/__init__.py:17`：

> `tests/unit/test_builtin_subscribers.py` locks the registered set and the frozen order, so a subscriber added without a decision about where it goes fails there rather than in production.

实际断言（`tests/unit/test_builtin_subscribers.py:29,56`）都是 `registry.freeze().ids(EVENT_ATTEMPT_PREPARE) == EXPECTED_ON_ATTEMPT_PREPARE`，只读 `attempt.prepare` 这一个事件。

**具体失败场景**：下一个内置订阅者挂在别的事件上（`attempt.failed` / `request.succeeded` 都在 `direct_driver/base.py:30-33` 现成可用，且 §7 已经点名 `hook_strip_anthropic_request_headers` 是天然的第二个订阅者，它未必落在 `attempt.prepare`）——`register_builtin_subscribers` 多一次 `subscribe`，两条断言全绿，order 表也不必更新，docstring 承诺的「没有定位决策就失败」不成立。这条守卫在它自称覆盖的一半上不击发。

**建议**：断言换成整张表，例如 `{event: frozen.ids(event) for event in frozen.events}` 与一个显式字典比较（`FrozenSubscribers.events` 已存在，`events.py:108-110`）。这样新增任何事件上的内置都会红。

---

## Minor

### m1. 被剥声明缺 `name` 时，悬空的 `tool_choice` 留在原地——正是模块自称要防的「一个 400 换另一个 400」

`src/app/pipeline/subscribers/server_tools.py:87-90,62`：`dropped_names` 只收集 `isinstance(name, str)` 的名字；`_drop_dangling_choice` 用 `entry.get("name") in dropped_names` 判定。

**探针复现**（`/tmp/probe_mutation.py`，实测输出）：

- 输入 `{"tools":[{"name":"calc","input_schema":{}},{"type":"web_search_20250305"}],"tool_choice":{"type":"tool","name":"web_search"}}`
- 输出 `{"tools":[{"name":"calc",...}],"tool_choice":{"type":"tool","name":"web_search"}}`
- 上游结果：`Tool 'web_search' not found in provided tools`，即 `server_tools.py:48` 与测试文件 `:43` 明写要避免的那个替换。

要求 Anthropic 的 server tool 必带 `name`，所以这需要一个已经畸形的客户端声明，因此判 minor 而非 major。但修法比现状更简单也更强：判据换成「choice 指的名字是否还在 `kept` 里」，而不是「是否在被删的名字里」——那样对缺 `name`、`name` 非字符串、以及未来任何新的删除原因都天然成立。

### m2. 走翻译进入 Anthropic 腿的 OpenAI 形状 hosted tool（`{"type":"web_search"}`，无下划线）不被剥

`_REJECTED_TYPE_PREFIXES = ("web_search_", "web_fetch_")` 要求尾随下划线（Anthropic 的 dated 拼写）。

**路径**：`/responses` 或 `/chat/completions` 入站、`model` 指向 Claude 模型 → `routing.py:96-98` 走 `_FALLBACK_ORDER` 落到 `ANTHROPIC_MESSAGES`，`translation_required=True` → `translation_driver/anthropic_messages.py:228` 把 `request.tools` **逐字**写进 Anthropic 载荷 → 订阅者看到 `target_format is ANTHROPIC_MESSAGES`（门开），但 `"web_search".startswith("web_search_")` 为假 → 声明原样发出 → 同一条 400。

**探针复现**：`inbound=OPENAI_RESPONSES, target=ANTHROPIC_MESSAGES, payload={"tools":[{"type":"web_search"}]}` → 输出与输入逐字相同。

这同时是提问 2 的答案：门控轴（读已路由的出线腿）**选对了**，翻译**进入** Anthropic 的路线上载荷确实是 Anthropic 形状、确实该剥、确实剥了（这一点比模块 docstring 说的更好，见 m6）；漏的不是轴，是清单在另一个协议命名空间下的拼写。

判 minor 的依据：本项目没有 `/responses` 入站 + Claude 模型的实测流量样本，且 `synthesis.md:103-104` 已把这条翻译腿的 typed tool 透传单独记为未处置敞口。若要处理，最小改法是在同一份清单里加一条不带下划线的精确匹配，并在注释里写明它属于 OpenAI 命名空间（不要放宽成 `startswith("web_search")`，那会顺手吃掉未来的 `web_search_preview` 之类未测形状，与本模块「只剥实测拒绝的」纪律相反）。

### m3. `logger.warning` 逐请求触发，且不带任何请求身份

`server_tools.py:103-108`。两个可观测性问题：

1. **频率**：一个开着 WebSearch 的 Claude Code 会话，**每个请求**一条 warning。同仓的姊妹 sanitizer 给出了相反的先例——`anthropic_request_hook.py:95` 对例行修复用 `logger.debug`，`:90` 只把**无法修复**的那一种留给 `warning`；`observability/logging.py:145` 的注释也把 WARNING 定义为「不是例行的时候才放行」。按这套已有判据，「客户端一直开着 WebSearch」是稳定状态而非异常事件，逐请求 warning 与之不一致。
2. **归属**：`observability/logging.py:113` 装了 `merge_contextvars`，但全仓无 `bind_contextvars`（grep 零命中），这条线里也没带 `context.id` / `resolved_model`。并发两个会话时，运维看到一串 `dropped 1 server-tool declaration(s)...`，无法判断是哪个请求、哪个模型丢了工具。

**建议**（二选一即可，不必都做）：降级为 `debug` 并在消息里带上 `context.id` 与 `context.resolved_model`；或保留 warning 但只在**每个请求的首次**之外静默。不建议为此新造去重状态。

顺带：`", ".join(sorted(dropped_names)) if dropped_names else "them"` 在缺 `name` 时输出「the model will not be offered them」（探针实测），读起来是断句失败；这条与 m1 是同一处根因。

### m4. `build_chain` 改写调用方传进来的 registry，重复调用会抛 `SubscriptionError`，且没有不要内置的出口

`composition.py:218-220`。`SubscriberRegistry.subscribe` 对重复 id 抛 `SubscriptionError`（`events.py:47-50`）。

**具体失败场景**：`reg = SubscriberRegistry(); build_chain(cfg, http_client=c, subscribers=reg); build_chain(cfg2, http_client=c, subscribers=reg)` → 第二次 `SubscriptionError: duplicate subscriber id 'builtin:server-tool-capability' on event 'attempt.prepare'`。

**现状无实活触发**：全仓 6 个 `build_chain` 调用点（`cli.py:139,161`、`debug/models.py:156`、`tests/http/test_pipeline_app.py:122,390,418`、`tests/integration/recorded/*`、`tests/unit/test_config_paths.py:112`、`tests/unit/test_builtin_subscribers.py:54`）**无一传 `subscribers=`**，`cli.py` 的两处也各自新建；`tests/http` 与 `tests/unit` 实跑全绿（见上表）。所以这是潜伏项而非现症，判 minor。

两点建议：`build_chain` 的 docstring 现在只说 `providers` 可注入，应补一句「传进来的 registry 会被就地追加内置订阅者」——这是对调用方对象的副作用，不写出来读不到；以及考虑把这层放进一个「组装 registry」的小函数，让「要不要内置」成为可表达的选择（当前无出口，对未来一个只想测自己订阅者的调用点是硬约束）。

### m5. `count_tokens` 腿完全不经过驱动，因而不经过任何订阅者

`handler.py:144-154` 的 `ask_upstream` 直接 `provider.count_tokens(payload, ...)`，`handle_count_tokens` 全程不构造 driver，`attempt.prepare` 不发布。

**后果**：同一个开着 WebSearch 的会话，`/v1/messages` 已被修好，`/v1/messages/count_tokens` 仍把 `web_search_20250305` 原样送上去。默认 `CountTokensConfig.providers = ["ghc","local"]`（`config/schema.py:68`），所以上游一旦拒收会退到本地估算，**客户端无可见失败**；代价是这类请求永远拿不到上游真值，`calibration.learn`（`handler.py:176`）对它们停止学习。

未实测上游 count_tokens 是否真的拒收该声明，所以这条是**范围提示**而非缺陷断言。若要覆盖，注意它不在驱动上，不能靠同一个订阅点解决。

### m6. 模块与测试对「翻译腿」的措辞把判据说窄了

`server_tools.py:69`：

> The payload is Anthropic-shaped here only because the route targets the Anthropic endpoint — on a translated route it has already become something else by the time this runs.

后半句只对「从 Anthropic 翻**出去**」成立。翻译**进来**（m2 那条路径）时 `translation_required=True` 而载荷恰恰是 Anthropic 形状，订阅者照跑且应当跑。测试名 `test_a_translated_route_is_not_touched`（`:94`）承的是同一个过宽的说法，它实际验证的是 `target_format is OPENAI_RESPONSES`。

**读者会被误导成**：以为凡 `translation_required` 的路线都被这段代码排除，于是把 m2 那条路径当成「设计上不该到这里」而不去查。建议改成「读的是出线腿：目标不是 Anthropic Messages 时这里的 `tools` 属于别的协议」，测试名相应改为按目标格式表述。

### m7. `test_a_caller_s_own_subscribers_share_one_frozen_order_with_the_built_ins` 名字承诺顺序，断言只查成员

`tests/unit/test_builtin_subscribers.py:32-46` 用 `set(...) == {...}`。它证明的是「两者进了同一个 frozen 结果」，这确实是该用例的真实价值（内置与调用方订阅者之间今天没有既定顺序，不该硬编码一个）。只是名字与 docstring 说的是 order。改名（如 `..._end_up_in_one_frozen_registry`）即可，不必加断言。

### m8. 历史残留块：边界划对了，但「会话立刻恢复可用」这句话要限定

提问 7 的后半。本次只剥 `tools[]` 是对的：本代理从未让带 web search 的请求成功过，模型因此从未产出 `server_tool_use`，历史自然干净。**唯一会撞上 `Tool 'X' not found in provided tools` 的是**：会话历史来自真 Anthropic API、或来自别的曾产出过 server-tool 块的代理。那类会话在本次修复后从「400 web search」变成「400 Tool not found」——仍然不可用，只是换了句话。

这不是本次引入的回归（修复前同样 400），也不该塞进本切片（`260820-websearch-fix-v2-design.md` §5.3、§8.2 已把它挂在待裁决上，做法正确）。要动的是措辞：设计稿 §7 与 synthesis §3 的「能立刻让 Claude Code 会话恢复可用」应加上「历史中无 server-tool 块的会话」这个限定。**独立处理，不是本次缺口。**

---

## 判对了的部分（附判据）

按提问逐条给证据，避免只说「看着没问题」。

**剥离逻辑本身（提问 1）**。逐条验过：`kept`/`dropped` 分离不改动原 tool 对象；`payload["tools"] = kept` 换的是新 list，不就地改客户端那条数组；剥空走 `del payload["tools"]` 而非 `[]`（`:99`），理由写在注释里且与仓内既有做法一致；`if not dropped: return`（`:92`）保证无命中时载荷逐字不动——`test_a_request_with_nothing_to_drop_is_left_exactly_as_it_was` 用整体 `==` 而非逐字段断言，这是有分辨力的写法。`_rejected_type` 对 `type` 缺失 / null / 非字符串 / `custom` 全部返回 `None`（`:35-42`），四种都落在「不是我们实测拒绝的那两族」这一条统一规则下，没有为 `custom` 单开分支——这是对的，因为分支多一条就多一处要跟着 Anthropic 演进。`str.startswith` 接元组是标准行为，不是笔误。

**重试循环内的幂等（提问 1）**。`attempt.prepare` 在 `direct_driver/base.py:130` 的 `while True` 内，每次重试都会再发一次；第二次 `tools` 已经不在，`_rejected_type` 无命中 → `if not dropped: return`，既不重复删也不重复打日志。`base.py:133` 在 publish 之后才 `attempt.payload = dict(context.payload)`，所以订阅者改的确实是会发出去的那份——driver 级测试 `assert provider.sent == [{"model": ..., "messages": []}]` 正是钉这一点。

**剥离清单的取舍（提问 3）**。`web_search_` 有今天的生产日志，`web_fetch_` 有 2026-07-12 的一手实测（两套不同 body），两条都记在 `:21-26` 的注释里并说明了「判据读我们发出的声明、不读上游措辞」的理由——这个理由本身是对的，按单一错误文本写 matcher 确实会漏掉 `invalid_request_body` 那套。刻意不剥 `memory_`/`tool_search_`/`text_editor_`/`bash_`/`computer_` 站得住：它们由客户端执行，Claude Code 确实在发，且没有任何一条被实测拒绝过——剥掉是为防一个没人见过的失败而弄坏正在工作的请求。参考实现剥十个前缀，`260820-websearch-fix-v2-design.md` §2.3 已论证那是错的。**我没有找到已知会被上游拒绝而漏掉的类型**：`code_execution` 在 Anthropic 腿未探针（设计稿 §4 明记 `/responses` 腿留空「omitted until probed, rather than guessed」），保持不剥与本模块纪律一致。

**门控轴（提问 2）**。`target_format` 由 `apply_route`（`handler.py:58`）从 `Route` 无条件写入，`Route.target_format` 非可选（`routing.py:42,100`），生产两条入口 `handle` 与 `handle_count_tokens` 都先路由后干活，所以「target 为 None 而漏剥」在生产路径上不存在（只可能出现在不经路由的单测里）。翻译腿不发布 `attempt.prepare`（grep 确认 `translation_driver/` 下零 publish），GPT 腿因此根本不到这里——与「映射推迟到下一轮」的裁决一致。

**测试分辨力（提问 6）**。未见恒真断言。driver 级那条（`:96-119`）确实证明订阅者跑在请求路径上：它跑的是真 `AnthropicMessagesDriver.run`，`RecordingProvider.send` 记的是驱动实际交出去的 payload，断言是整体 `==`。我独立复现了变异结论：把 `_REJECTED_TYPE_PREFIXES` 置空后 `adapt_server_tools` 让声明原样留下，说明绿灯由该常量支撑而非被别处顺手满足。`test_the_chain_the_server_runs_on_actually_carries_them` 补的是另一条腿（`build_chain` 真的注册了），两条合起来覆盖「注册」与「被读」。

**文风（提问 8）**。四个文件均无句中折行；注释解释「为什么」（`:98` 为何不用 `[]`、`:24` 为何判据读发出的声明、`:26` 为何不剥另外五族）而非复述代码。`ruff check` 全绿且 `E501` 在本仓被 ignore（`pyproject.toml:67`，注明正是为了不与 no-hard-wrap 打架），未运行 `ruff format`。order 表（`__init__.py:13-15`）把「为什么在这个位置」写在表旁并指明锁定它的测试，是设计稿借鉴点 1 的正确落地——除了那句测试覆盖面的夸大（M2）。

---

## 附：本次未纳入评审的相邻观察

- `260820-websearch-fix-v2-design.md` 有两个都叫「7」的章节（`:181` 与 `:219`）。文档不在本次评审范围，仅记。
- 设计稿 §7 记录的 `tests/unit` + `tests/http` 窄化调用假红，本次未复现验证（我分别单跑两个目录相关文件，均全绿），其归因结论按原报告采信。

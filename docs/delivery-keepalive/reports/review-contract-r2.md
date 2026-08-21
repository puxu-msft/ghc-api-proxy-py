# 复评（r2）：`docs/agents/delivery-keepalive/spec.md` 能否固定为规范

- 评审对象：`3160285`（`fix: let one gate decide whether the client has bytes`）与 `97d805e`（`fix: time the keep-alive from when a chunk left, not from when it was made`），基线 `a374f39`
- 上一轮报告：`review-contract.md`（F1–F11，needs-fix），本轮逐条核对其落实情况
- 工作树：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`，评审全程只读；探针在 `/tmp/probe_keepalive/`，前一轮的 `probe_full_policy.py` 原样复用
- 角色仍是证伪者。每条给可复核命令或 `文件:行`

严重度：**重要**（会让读者做错事或与既有裁决冲突）/ **次要**（引用、措辞、完备性）/ **观察**（记录，不要求改）
把握程度：**高**（本次亲手复现或全量 grep）/ **中**（读码推断）

**结论：F1 的修复经独立验证成立；spec 正文可以固定，但 §2 的判据在 `3160285` 上还有一个未兑现条件（在途改动正在修），且 §2.2 有一句话必须先改。** 详见末节。

---

## 1. F1 的修复是否修对了

### 1.1 语义等价性：`client_has_bytes.is_set()` 与旧 `started` 严格等价

逐条比对 `git show 3160285 -- src/app/pipeline/delivery/stream.py`：

| 旧代码 | 新代码 | 判定 |
|---|---|---|
| `started = False`（局部 bool） | `client_has_bytes = asyncio.Event()` | 载体变了，语义未变 |
| 合成分支 `response_started.set(); started = True` | 只 `client_has_bytes.set()` | 旧代码这里两个都置位，合并后无信息丢失 |
| `_commit(..., started, ...)` | `_commit(..., client_has_bytes.is_set(), ...)` | 都在调用时求值，等价 |
| `if not started: started = True`（yield 循环内） | `client_has_bytes.set()`（同位置） | 等价 |
| `remaining and not started` → yield → `started = True` | `remaining and not client_has_bytes.is_set()` → yield → `.set()` | 等价，连「置位在 yield 之后」都保留了 |
| `if started:` 决定终止帧 | `if client_has_bytes.is_set():` | 等价 |
| `if blocks: response_started.set()`（assembler 组装即置位） | **已删除** | 这就是修复本身 |

关键点：旧代码里 `response_started` 从来不喂 `started`，`started` 的置位点在新代码里一一对应保留，**没有新增也没有删除任何置位点**。因此 `client_has_bytes` ≡ 旧 `started`，严格等价。唯一的语义变更是「合成计时该问哪道门」——从 `response_started`（组装）改成 `client_has_bytes`（写出），正是 F1 要的。

**推论：`block` 策略下行为完全不变。** 该策略 `add()` 立即 `_drain()`，组装与释放同时发生，两道门本就不分叉。实测印证（下表第一行三次运行数字一致）。

### 1.2 `remaining and not client_has_bytes.is_set()` 路径与终止帧条件

这条路径是本次改动的主要新风险面：合成现在可能在块被扣住期间先行触发，之后末尾 drain 分支还有一个 `message_start`，两者可能各发一次。

实测（`/tmp/probe_keepalive/probe_preamble_once.py`、`/tmp/probe_keepalive/probe_synth_then_blocks.py`，共 12 个配置）：

| 场景 | `message_start` | `message_stop` | 事件序列合法 |
|---|---|---|---|
| `block` / `until-tool-use` / `full`，synth=1s 先触发再来块 | 各 1 | 各 1 | 是 |
| `until-tool-use` / `full`，synth 关闭，块全部走末尾 drain | 各 1 | 各 1 | 是 |
| `block` / `full`，synth 触发后上游**再无任何内容** | 各 1 | 各 1 | 是（`message_start`→`message_delta`→`message_stop`） |
| 空上游、无 synth | 0 | 0 | 是（零字节） |

**没有重复 preamble，没有缺失终止帧，没有在零字节响应上凭空发终止帧。** 复现：

```bash
PYTHONPATH=src uv run python /tmp/probe_keepalive/probe_preamble_once.py
PYTHONPATH=src uv run python /tmp/probe_keepalive/probe_synth_then_blocks.py
```

`_commit(started=True)` 这条路径（合成先发、随后块被释放）在第 1、2、3 行被覆盖，`_commit` 正确跳过了第二个 `message_start`。

### 1.3 三种 policy 对照重跑（上一轮同一个探针，未改动）

```bash
PYTHONPATH=src uv run python /tmp/probe_keepalive/probe_full_policy.py
```

| policy | 上一轮（`a374f39`） | 本轮（`3160285`） |
|---|---|---|
| `block` | 3 pings，首字节 0.20s，最大间隔 1.00s | **3 pings，首字节 0.20s，最大间隔 1.00s** |
| `until-tool-use` | **0 pings，首字节 3.22s**（= 流结束） | **1 ping，首字节 2.00s**（= `synthesized_...=2`），最大间隔 1.00s |
| `full` | **0 pings，首字节 3.22s**（= 流结束） | **1 ping，首字节 2.00s**，最大间隔 1.00s |

首字节精确落在合成上界上，其后间隔精确等于 `sse_ping_interval`。**§2.2「该上界对三种 `buffering_policy` 一致成立」这句话，实测支持。**

### 1.4 回归测试的分辨力：独立验证，不是采信

未改动工作树，用 `git archive '3160285^' src` 把修复前的源码抽到 `/tmp/probe_keepalive/old/`，再用 `PYTHONPATH` 覆盖加载（已打印 `__file__` 与 `'client_has_bytes' in source == False` 确认加载的确实是旧模块）：

```bash
PYTHONPATH=/tmp/probe_keepalive/old/src uv run pytest tests/unit/test_stream_delivery.py -k held_back -q
```

→ `2 failed`，`full` 与 `until-tool-use` 两个参数**都红**。协调方的分辨力声称成立。

**但要点明它是怎么红的**：两次都断在 `assert PING_FRAME in chunks`（`tests/unit/test_stream_delivery.py:311`），而它前面那条 `assert events_of(chunks)[0] == "message_start"` 在旧代码上**是通过的**——旧代码末尾 drain 分支照样把 `message_start` 排在第一个，只是迟到 1.5 秒。所以这条测试的分辨力**全部来自 ping 断言**。

这不是缺陷：ping 只有在 `client_has_bytes` 打开之后才发得出来，而合成在 t=1s、流末在 t=2.5s，因此「存在 ping」本身就蕴含「门在流末之前就开了」——时序确实被钉住了。记录下来是因为将来有人想删掉那条 ping 断言时，需要知道第一条断言接不住。

### 1.5 回归与静态检查

评审期间工作树出现了针对 `_events_with_ping` 的未提交改动（见 §5 R2-0），因此上述全部结论都在**隔离的已提交 HEAD** 上复跑过一遍：`git archive HEAD src tests pyproject.toml` 抽到 `/tmp/probe_keepalive/head/`，用 `PYTHONPATH` 覆盖加载并打印 `__file__` 与 `'_keepalive_due' in source == False` 确认加载的确实是 `3160285` 的代码。两次输出逐字一致。

- `PYTHONPATH=/tmp/probe_keepalive/head/src pytest tests/unit tests/component -q`（在隔离树内运行）→ **1036 passed, 1 skipped**
- `uv run ruff check src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py` → All checks passed
- `uv run pyright src/app/pipeline/delivery/stream.py tests/unit/test_stream_delivery.py` → 0 errors
- `git diff a374f39..HEAD --stat -- src/` → **只有 `stream.py` 一个文件**，未外溢

**1.x 小结：F1 修对了，没有引入新分叉，没有回归。**（但 `3160285` 上还有一个我没找到的独立窗口，见 §5 R2-0 与 §5.0 的自我披露。）

---

## 2. F2–F11 逐条核对

| 编号 | 要求 | 落实 | 依据 |
|---|---|---|---|
| **F1** | §2.2 补第 3 个未覆盖窗口，修正「上界 240s」 | **已落实（改为修掉而非记录）** | 洞已修，§2.1 完整叙述成因＋实测数字；§2.2 改写为「该上界现在对三种 policy 一致成立」 |
| **F2** | 删「也没有上限」，改为 `upstream_request_deadline` 有界但无意义 | **已落实** | spec.md:56，含 `handler.py:99-104` → `base.py:233-241` 链路；`deferred.md:24` 另记一笔「初版写错的事实」 |
| **F3** | 「既有裁决」降级；改定性为与人写文档冲突 | **已落实，且做得比要求更彻底** | spec.md:43 明写「不是用户裁决……原文是『我的偏好』」；新增 §2.2 下的【需用户裁决】小节，引用原文并列出两处对不上；`deferred.md` D-2 同步 |
| **F4** | `hedge` 从 §4 挪进 §2.x | **已落实** | 新 §2.3「本节治下但尚未实现的缓解手段」，spec.md:60-62，明写「因此它属于本节，不是相邻问题」 |
| **F5** | `stream_idle` 改指 `settings.py`，说明 schema 侧无消费方、旧链路未被服务 | **已落实**（行号有误，见 R2-4） | spec.md:83-84 |
| **F6** | 补 `settings.py` 死旋钮、回链设计文档、指出命名不一致、改「改名/撤掉」措辞 | **部分落实** | 回链已加（spec.md:75）、命名不一致已提、httpcore 无 PING 接口已补、措辞已改为「本规范不作提议性裁决，只记录事实并交回」；**但 `settings.py:73-74` 那两个死旋钮仍无人记录**，见 R2-2 |
| **F7** | 定义「交付已经开始」 | **已落实** | 新增 §2.1 专节，spec.md:33-37，直接锚到 `client_has_bytes` |
| **F8** | 补 `sse_ping_interval = 0` 的退化说明 | **已落实** | spec.md:21 「`sse_ping_interval = 0` 关闭该判据——此时本节不作任何承诺，下游静默无上界」 |
| **F9** | 把「唯一出口」结构不变量写进 §2 | **已落实** | spec.md:29，含「不会有任何测试变红」的警告；spec.md:31 另补打戳时机的理由 |
| **F10** | §2.2 点明与 §2.1 是方向相反的两个取舍 | **未落实** | 见 R2-10（次要） |
| **F11** | 文档位置与状态标签 | **已处理** | 状态行改为「规范。适用范围是 `src/app/pipeline/delivery/stream.py` 的下游交付，随该外部契约有效而有效」——用适用范围替代目录之争，是合理处置 |

另：上一轮末节点名的三条「建议单独立案」的观察，`deferred.md` 收了两条（D-5 `response_header_overrides`、D-6 `base.py` docstring），第三条（上游 4 个旋钮全死）只收了其中 2 个，即 R2-2。

---

## 3. 新引入的陈述是否属实

逐条独立复核（不采信协调方自述）：

| spec 位置 | 陈述 | 复核 | 判定 |
|---|---|---|---|
| :21 | `sse_ping_interval = 0` 关闭判据 | `stream.py:58` `ping_deadline = ... if interval > 0 else None` | **属实** |
| :35 | `client_has_bytes` 是三个决策共用的门 | `stream.py:162,170,179,186,194` | **属实** |
| :37 | 实测数字 `block` 3 ping/0.20s；`full`、`until-tool-use` 0 ping/3.22s | 与我上一轮探针输出逐字一致 | **属实** |
| :41 | 240s 上界对三种 policy 一致成立 | 本轮探针，首字节均落在合成上界 | **属实** |
| :47 | `config.example.yaml:404-409` | 该区间正是「合成一个半块」注释块 + `synthesized_response_headers_after_sec: 240` | **属实** |
| :53 | `_deliver` 函数体要等首次拉取才执行 | 异步生成器语义；`stream_delivery` 与 `_deliver` 的 body 都在首个 `__anext__` 时才跑 | **属实** |
| :56 | `upstream_request_deadline` 默认 **1200** | `src/app/config/schema.py:104` | **属实** |
| :56 | `handler.py:99-104` → `base.py:233-241` 的 `asyncio.timeout`，恰好且仅仅覆盖 pre-header 段 | 两处源码复核，`asyncio.timeout` 只包 `await send` | **属实** |
| :62 | `hedge` 无消费方，阈值默认 300s | `rg 'hedge' src/ tests/ --type py` 只命中 `schema.py:165,195` | **属实** |
| :70 | `upstream_transport` **只有两个**配置项 | `schema.py:91-93` `UpstreamTransportConfig` 恰好两个字段 | **属实** |
| :72 | 全仓无 `SO_KEEPALIVE` | `rg -n "SO_KEEPALIVE" src/` 零命中；仅 `docs/2604-rewrite/streaming-resilience.md:250` 的设计示例代码里有，而该文档已在 :75 回链 | **属实** |
| :73 | httpcore 也没有发送 PING 的接口 | `httpcore/_async/http2.py` 全文无 ping 发送逻辑（`h2 4.3.0` 已装，`http2=True` 本身生效） | **属实**，且是比「接线遗漏」更强的事实 |
| :75 | `composition.py:60-81` | `transport_options` 60-72、`build_http_client` 75-81 | **属实** |
| :83 | `settings.py` `TimeoutConfig.stream_idle` 默认 **300**，消费方 `routes/anthropic.py:217` | `settings.py:69`、`routes/anthropic.py:217` → `idle_timeout.py:12-16` | **属实** |
| :83 | 生产服务的是 `create_pipeline_app`，旧链路未被服务 | `cli.py` 只构造 `create_pipeline_app`；`app_factory` 经 `rg` 只被 `tests/` 引用 | **陈述属实，行号错**，见 R2-4 |
| :84 | schema 侧 `stream_idle` 默认 **0**、无消费方 | `schema.py:102`；`rg "upstream_request_timeouts" src/` 仅 `schema.py:295` 与 `handler.py:99` | **陈述属实，措辞偏窄**，见 R2-7 |
| :86 | `response_header` 无消费方；`response_header_overrides` 被拿去覆盖 `upstream_request_deadline` | `handler.py:100-104` | **属实** |

**没有发现新的不实陈述。** 下面列的都是措辞、引用与完备性问题，不是事实错误——除了 R2-1，那是一条会误导决策的建议。

---

## 4. §2 的结构不变量在当前代码上是否仍成立

**仍成立。** 机械复核：

- `_deliver` 产出下游字节的全部位置：`stream.py:169`（合成 `message_start`）、`:171`（`PING_FRAME`）、`:183`（`_commit` 的 chunk）、`:188`（drain 前的 `message_start`）、`:192`（drain 的 block frames）、`:200`（terminal frames）。六处，全部经 `stream_delivery` 的 `async for chunk in inner: yield chunk`（`:125-127`）离开。
- `_events_with_ping` 的 `:84` 与 `:88` 两个 yield 产出的是 `SseEvent | None`，不是字节。
- 外层链路未被这两个提交触碰（`git diff a374f39..HEAD --stat -- src/` 只有 `stream.py`）。`pipeline_app.py:347-355` 的 `_counted_upstream` 与 `:358-367` 的 `_tracked_delivery` 都是纯转发，`_AccountedStreamingResponse.__call__`（`:340-344`）只加 `finally`，`:160-161` 的 `isinstance(response, StreamingResponse)` 分支只做计数登记不产字节。

打戳位置从 `yield` 之前挪到之后（`97d805e`）不影响这条不变量：出口仍是同一个 `yield`。挪动本身是对的——`StreamingResponse` 先取 chunk 再 `await send`，生成器恢复点确实晚于交付；且期间内层生成器全程挂起，无并发读者，`last_write` 不会被别人看到中间态。

spec.md:29 把这条不变量连同「不会有任何测试变红」的后果一起写出来了，这正是 F9 要的。

---

## 5. 本轮新发现

### 5.0 先自我披露：我两轮探针都够不着的一个窗口

评审收尾时工作树出现未提交改动，其中带来一条新测试 `test_an_always_ready_upstream_does_not_starve_the_keep_alive`。我把它拿到隔离的已提交 HEAD 上跑：

```bash
PYTHONPATH=/tmp/probe_keepalive/head/src uv run pytest tests/unit/test_stream_delivery.py -q
# → 1 failed（该条）, 38 passed
```

**它在 `3160285` 上是红的。也就是说 HEAD 上还有第三个下游静默窗口，我前后两轮都没找到。**

机制：`_events_with_ping` 只在 `asyncio.wait` **超时**之后才走到 `yield None`。若上游的下一个事件已经就绪（`read_events` 的 `for frame in iter_frames(buffer)` 会把一个 chunk 里的多个完整帧**连续吐出、中间不 await**，见 `src/app/pipeline/delivery/sse_source.py:71-76`），那么每一次拉取都在同一个调度轮次内 `task.done()`，`break` 回外层重新拉，**下方那个「deadline 过期了」的分支一次也到不了**。块始终不闭合，于是这些事件一个字节也不写往下游，客户端被饿着。改动方的注释记的是十秒内 173125 次过期而被跳过的机会。

**为什么我的探针够不着它**：我两轮所有探针的上游生成器在事件之间都写了 `await asyncio.sleep(gap)`，那一句强制交出一个调度轮次，于是 `asyncio.wait` 必然超时、`yield None` 必然可达。**这是我的方法论盲区，不是运气问题**——「让上游快过 interval」我做到了，「让上游快到根本不交出控制权」我没想到要做。上一轮 F1 是「守卫被一个不成立的前提挡住」，这一条是同一形态的另一个实例，我却只覆盖了其中一个。

**这个窗口在生产上有多真？**（读码判断，中等把握，未做端到端实测）单次 httpx chunk 能解出的帧数有限，一批耗尽后下一次 `anext` 就得真等网络，此时 ping 会补发——所以「一个 burst」造成的静默是微秒级，不构成风险。真正的风险形态是**上游持续快到让 socket 缓冲区始终非空**，此时每次拉取都不需要真等，静默可以一直延续。这正是长 thinking 块高速吐 delta 的形状，与 F1 针对的场景重合。所以我判定它是**真实但比合成测试所暗示的窄**的窗口。

**对结论的影响**：F1 的修复本身不受影响（那是另一道门）。但 **spec §2 的判据「不得让客户端连续 `sse_ping_interval` 秒收不到任何字节」在 `3160285` 上尚未完全成立**——还存在一个使它不成立的条件。改动方的在途修法（把 deadline 结算提到每次拉取之前）方向是对的：它把「ping 能不能发」从「某次拉取是否真的等过」这个偶然条件上摘了下来。**我没有评审那份在途改动**，它需要它自己的一轮。

### R2-0【重要 / 高】评审期间 `_events_with_ping` 有未提交改动，且它改变的正是 §2 描述的机制

`git diff src/app/pipeline/delivery/stream.py` 显示新增 `_keepalive_due()` 辅助函数，并在外层 `while True` 顶部、每次拉取之前先结算一次 deadline。三点交回：

1. **本报告的评审对象是 `3160285`，不含这份改动。** 全部数字已在隔离的已提交 HEAD 上复跑确认（§1.5）。
2. **它落地后，spec §2 的判据才真正成立**（见 §5.0）。§2.1 目前把「两道门合一」讲成了保活缺陷的完整故事，但那只是两个成因中的一个；建议 §2.1 或 §2 补一句「保活的可达性还取决于拉取是否真的等待过」，或者等这份改动落地后统一改写。
3. **顺带**：改动里 `_keepalive_due` 与 `stream_delivery` 之间留了三个空行（`stream.py` 中 `+` 段末尾），提交前值得跑一次 `ruff check`。

### R2-1【重要 / 高】§2.2 建议「把 `upstream_request_deadline` 降到 300 以下」，与用户冻结的不变量冲突，也与本 spec 自己 §4 的分类冲突

原文（spec.md:56 末句）：

> 1200s 远高于背景文档 §4 实测的客户端 300s 天花板，**所以这个上限对客户端毫无意义**——但它存在，现成的调整手段是把它降到 300 以下，而不是新造一个机制。

三处问题，逐条：

1. **它是终止器，不是保活。** 本 spec 的 §4 开宗明义：「上游空闲检测……是终止条件，不是保活：一个是让连接活着，一个是决定放弃它。」把 `upstream_request_deadline` 降到 300 以下并不会让客户端多收到一个字节——它只是让代理在客户端超时之前先行放弃并返回错误。用「现成的调整手段」这个说法把它摆在保活缺口的答案位置上，正是 §4 禁止的那种混淆。（是否「代理主动返回错误」优于「客户端 fetch 超时」是个真问题，但那是另一件事，需要单独说。）

2. **它覆盖的是用户冻结的不变量，而 spec 没有披露这一点。** `docs/.human-controlled/config.example.yaml:282-283`（用户亲笔）：

   > 用户冻结的不变量是绝不误杀合法长思考：活连接上的静默没有可证明安全的 wall-clock 上界，因此 bundled defaults 全部禁用此类终止器。
   > 运维可显式配置非零值以选择有界等待，**但那是对该不变量的主动覆盖**。

   同一节的 `response_header: 0`、`stream_idle: 0` 就是这条不变量的体现。把一个终止器压到 300s 以下，恰恰是「用 wall-clock 上界误杀长思考」——建议本身可以提，但必须标明它是对用户冻结不变量的主动覆盖，而不是「现成的手段」。

3. **一旦 D-6 被修，这条建议的杀伤面会扩大一个数量级。** `deferred.md` D-6 已记录：`upstream_request_deadline` 目前对流式请求只包住 `await send`，所以现在它「恰好且仅仅覆盖」pre-header 段。人写文档 `config.example.yaml:308-312` 说的却是「单次上游尝试的**最大存活秒数**……两者都拦不住『一直滴水但永不结束』的尝试」。也就是说 D-6 修好之后，这个 deadline 会覆盖**整次流式尝试**——此时「降到 300 以下」意味着任何超过 300 秒的流式回答都被砍断。spec 把这条建议写在一个即将改变语义的旋钮上，却没提这层耦合。

**建议改法**：把末句改写为——「它存在，但降低它属于终止器调整而非保活：客户端仍然拿不到字节，只是改由代理先行放弃；且这是对 `config.example.yaml:282-283` 所述冻结不变量的主动覆盖，并会在 D-6 修复后扩大到整次流式尝试。是否采用由用户裁决。」

这是本轮唯一一条会让读者做错事的发现，也是唯一一条我认为必须在固定之前改掉的。

### R2-2【重要 / 高】F6 只落实了一半：`settings.py` 的两个上游死旋钮仍无人记录

```bash
rg -n "upstream_keepalive|upstream_h2_ping" src/ tests/ docs/agents/delivery-keepalive/
```

→ 源码侧只有定义 `src/app/config/settings.py:73-74`（`upstream_keepalive: int = 15`、`upstream_h2_ping: int = 15`），**零消费方**；文档侧只有我上一轮报告命中，`spec.md` 与 `deferred.md` 都没有。

`spec.md:70` 的措辞是「`upstream_transport` **只有两个**配置项」，字面无误（`UpstreamTransportConfig` 确实两个字段），但读者拿到的印象是「上游保活一共两个旋钮，都是死的」。实际是**四个，全是死的**，另两个还用着 `docs/2604-rewrite/streaming-resilience.md` 配置表里的名字——这正是 :75 所说「命名与本节不一致」的具体内容。

**建议改法**：在 `deferred.md` 的 D-3 里加一句，或在 spec.md:75 那句后面补「另有 `src/app/config/settings.py:73-74` 的 `upstream_keepalive` / `upstream_h2_ping` 沿用设计文档的命名且同样无消费方」。

### R2-3【次要 / 高】`deferred.md` D-4 的交叉引用已失效

`deferred.md:44`「见 `spec.md` §4。」但 F4 的落实恰恰是把 `hedge` 从 §4 挪到了 §2.3。现在 §4 的标题是「相邻但不属于本规范的」，把 `hedge` 指到那里，正好复述了被推翻的那个定性。改成「见 `spec.md` §2.3」。

### R2-4【次要 / 高】`spec.md:83` 的 `cli.py` 行号错

spec 写 `src/app/cli.py:142,167`；实际 `create_pipeline_app` 在 **140** 与 **165**（`rg -n "create_pipeline_app" src/app/cli.py`）。142 是 `log_config=None`，167 是一条注释。差 2 行。

### R2-5【次要 / 高】`deferred.md:18` 用了全角 `／`

> ……生产路径上客户端断开时，Starlette**／**uvicorn 到底有没有关闭 `stream_delivery` 这个生成器。

按标点约定，`/` 应用半角。`spec.md` 本身无此问题——两份文档我都做了剥离行内代码后的全量扫描，`spec.md` 9 处命中全是标题编号、`---` 与量值小数点（`0.2s`、`3.22s`、`§2.2`），无真实违例；两份都无硬折行。

### R2-6【次要 / 中】§2.1「这是代码里唯一的那道门」严格说不成立

`src/app/pipeline/delivery/blocks.py:137,154,164` 还有一个 `DeliverySession.started`（「有没有块被释放过」），由 `_commit` 内部置位。它不参与 `_deliver` 的任何判断（唯一读它的 `start_response()` 无条件抛异常），也有测试覆盖（`tests/unit/test_block_delivery.py:93,103,120`），所以不构成第二个答案。

但 §2.1 那句话是全称的，而句子后半段「`_commit` 是否发过 `message_start`、保活是否可发、合成计时是否解除，三者共用它」才是它真正成立的范围。建议把前半句收窄为「这是这三个决策共用的唯一那道门」，避免下一个读者 grep 到 `DeliverySession.started` 时以为 spec 说错了。

### R2-7【次要 / 中】§4 说 schema 侧 `stream_idle`「在新链路上没有任何消费方」——实际是任何链路都没有

`spec.md:84` 的措辞暗示它在旧链路上可能有消费方。实际 `rg -n "upstream_request_timeouts" src/ --type py` 只有 `schema.py:295`（定义）与 `handler.py:99`（只取 `upstream_request_deadline` 和 `response_header_overrides`）——**新旧两条链路都没有**。删掉「在新链路上」五个字即可。

同族的 `stream_idle_overrides` 也一样：`schema.py:103` 无消费方，`idle_timeout.py:13` 读的是 `settings.py:68` 那个。§4 已经点了 `stream_idle`、`response_header`、`response_header_overrides`，顺手补上它更完整。

### R2-8【次要 / 中】F10 未落实

上一轮建议：§2.2 首句点一句「这与 §2.1 是方向相反的两个取舍」——§2.1 论证「发注释帧而不发 `ping` 事件」（嫌事件承诺多），§2.2 论证「合成时发 `message_start` 而不是注释帧」（嫌注释帧承诺少）。现在 §2.1 被改成了「交付已经开始的定义」，原来那节「为什么是注释帧而不是 `ping` 事件」**整节被删掉了**——所以矛盾感没了，但 §2.1 里那段论证也一并没了。

这是个取舍不是错误：spec 里现在只在 §2 的要点里留了一句「保活帧是 SSE 注释（`: ping\n\n`）……已实测：客户端的空闲计时器接受注释帧作为活动信号」，没有说为什么不发 Anthropic 官方那种带类型的 `ping` 事件。**若删除是有意的，记一笔即可**；若是重写时漏掉的，建议把「为什么不发 `ping` 事件、以及若将来有客户端只认事件就要重新裁决」这一条恢复进 §2 的要点列表。这条我拿不准是有意还是遗漏，交回裁决。

### R2-9【观察 / 高】新回归测试的第一条断言在旧代码上是绿的

见 §1.4。`assert events_of(chunks)[0] == "message_start"` 对本缺陷无分辨力，全部分辨力来自 `assert PING_FRAME in chunks`。不要求改（ping 断言已经蕴含了时序），记录以防将来有人以为两条断言各守一半。

### R2-10【观察 / 低】`deferred.md` 编号乱序

当前顺序是 D-1、D-2、D-5、D-6、D-3、D-4。新增的 D-5 与 D-6 插在了中间。纯阅读体验问题。

---

## 6. 这份 spec 现在能否固定为规范

**规范正文（§1、§2 的契约表述、§2.1 的定义、§2.3、§3、§4）可以固定；但 §2 的判据要等在途那份 `_events_with_ping` 改动落地才真正被实现兑现，且 §2.2 里有一句话必须先改。**

已经站得住的部分：

- **F1 的修复经独立验证是对的**：语义严格等价（§1.1 逐条比对）、无重复 preamble 与终止帧回归（12 个配置实测）、三种 policy 对照复现符合 spec 声称、回归测试在 `3160285^` 上两个参数都红（用 `git archive` 抽旧源码独立复现，非采信）、隔离 HEAD 上 1036 条测试全绿、Ruff 与 Pyright 干净、改动未外溢出 `stream.py`。
- **F1–F11 中 10 条已落实**，F6 落实一半（R2-2），F10 因 §2.1 改写而失去载体（R2-8，需裁决是不是有意）。
- **§2 的结构不变量在当前代码上仍成立**，且已被写进 spec 正文连同「破坏它不会有测试变红」的警告。
- **没有发现新的不实陈述**：19 条新增的代码位置、默认值与链路声称逐条复核，只有 `cli.py` 行号差 2 行（R2-4）与两处措辞偏窄（R2-6、R2-7）。

固定之前必须处理的两件事：

1. **R2-1（一句话）** — §2.2 把「把 `upstream_request_deadline` 降到 300 以下」说成「现成的调整手段」，既与本 spec 自己 §4 的终止器与保活的分类冲突，又未披露它是对 `config.example.yaml:282-283` 冻结不变量的主动覆盖，也未提 D-6 修复后杀伤面会扩大到整次流式尝试。它躺在一个供用户裁决的段落里，不改会让用户在信息不全的情况下作决定。
2. **R2-0 / §5.0** — `3160285` 上仍有一个使 §2 判据不成立的窗口（上游从不交出控制权时保活完全不发），在途改动正在修。**建议 spec §2 固定的时点跟这份改动对齐**，或者在 §2 判据下先加一句「当前实现的已知未兑现条件」并指向 deferred。这条我没有评审在途改动本身，它需要独立一轮。

建议同批一起改掉的低成本项：R2-2（补两个死旋钮）、R2-3（D-4 改指 §2.3）、R2-4（行号 140/165）、R2-5（全角斜杠）、R2-6 与 R2-7（两处收窄措辞）。这些都不影响规范的正确性，只影响读者能不能照着走。

需要裁决的：R2-8（§2.1 原本那节「为什么是注释帧而不是 `ping` 事件」是有意删除还是重写时漏掉）。R2-9、R2-10 只是记录。

最后一句留给我自己：**上一轮我把 F1 定为「阻断」，理由是「一份自称完整的枚举漏了一项」；这一轮 §5.0 说明我自己的枚举也漏了一项，成因还是同一形态（守卫被一个不成立的前提挡住）。** 因此对「§2.2 的窗口清单现在完整了吗」这个问题，我的答复是「已知的都在里面」，不是「没有别的了」——这两句话不能互相替代。

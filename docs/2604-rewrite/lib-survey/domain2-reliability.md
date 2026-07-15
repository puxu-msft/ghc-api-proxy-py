# 域2：可靠性 / 控制流机制

> 已按 [_briefing.md](_briefing.md) 的调研纪律执行：不臆断版本/能力，逐库通过 PyPI/官方文档核实。相关设计意图读自 [request-pipeline.md](../request-pipeline.md)、[feature-negotiation.md](../feature-negotiation.md)、[thinking-pipeline.md](../thinking-pipeline.md)、[shutdown.md](../shutdown.md)、[project-structure.md](../project-structure.md)。

## 概览结论表

| 自研点(模块/文件) | 候选库 | 匹配度 | 威胁硬约束? | 推荐 | 理由 |
|---|---|---|---|---|---|
| 重试策略框架（`pipeline/strategies/*` + `executor.py` 的 for 循环） | `tenacity` / `stamina` / `backoff` | 低（语义不匹配） | 否（若强套用会牺牲清晰度，非直接违反 P1/P6） | **保留自研**；可选借用 `wait_exponential`/`stop_after_attempt` 等**纯函数原语** | 这些库的核心抽象是「同一次调用，参数不变，重试直到成功/超限」；本项目要的是「读上一次错误 body → 改写 payload/headers/messages → 换个不同的调用再试」，且要与 `RetryStrategy` 的 `can_handle`/多策略优先级匹配、`max_reactive_retries` 跨策略共享预算、`on_resolved` 学习回调等自定义状态机耦合。tenacity 唯一支持这种改写语义的方式是手动 `for attempt in Retrying(...)` 循环，而这本质上就是本项目已有的 for 循环，借库不省代码反而多一层不必要的抽象/依赖 |
| 自适应限流器（`pipeline/rate_limiter.py`） | `aiolimiter` / `limits` / `pyrate-limiter` | 低（能力错配） | 否 | **保留自研** | 三个库都面向**客户端主动、预先声明速率**的限流（漏桶/令牌桶/滑动窗口），不具备"依据上游 429/503 响应反馈切换 Normal/Rate-Limited/Recovering 三态、动态调整退避时长"的状态机语义；本项目要的不是「限制我方发送速率」而是「感知上游限流反馈并自适应退避+恢复」，属于两类不同问题 |
| TTL 学习缓存（`feature_negotiation.py` 多类别缓存、`auto_truncate/token_limits.py`、`thinking/quarantine.py`） | `cachetools`(TTLCache) / `cacheout` / `aiocache` | 中（可部分借用） | 需逐条核对 | **部分替换**：`thinking/quarantine.py`（单一滑动 TTL、无持久化需求）可考虑用 `cachetools.TTLCache` 替代手写 dict；`feature_negotiation.py`（11 类别、per-entry 元数据 `LearnedEntryMeta`、pin/manually_expired/迁移语义、原子落盘）**保留自研** | 细节见下文逐项 |
| 断路器 / deadline（`pipeline/manager.py` stale reaper + request deadline） | `anyio` 超时原语 / `circuitbreaker` | 低-中 | 否 | **保留自研**（deadline/reaper 用 asyncio 原语已足够简洁）；`circuitbreaker` **不采用** | 详见下文 |

## 逐项详述

### 重试策略框架

**现状**：`pipeline/executor.py::execute_pipeline()` 在 `for attempt_num in range(max_retries + 1)` 循环里，收到错误后遍历 `retry_strategies: list[RetryStrategy]`，逐个调用 `strategy.can_handle(error)` 匹配，命中后 `strategy.handle(error, payload, ctx)` 返回 `RetryAction(should_retry, modified_payload, modifications)`——即**每次重试都可能是对 payload 的结构性改写**（剥离 thinking、截断消息、清理孤儿 tool 块、刷新 token 后改写 headers、降级 server tool 语义）。见 [request-pipeline.md](../request-pipeline.md) L134-232。此外还有：
- 策略优先级（`for...else` 顺序匹配，命中即 break，全不命中则失败）；
- 跨策略共享的 `max_reactive_retries` 预算（[request-pipeline.md](../request-pipeline.md) L241-254）；
- 部分策略成功后触发**跨请求学习**回调（`on_resolved()` 写入 L3 隔离表/feature negotiation 缓存，见 [thinking-pipeline.md](../thinking-pipeline.md) L339-347）；
- per-attempt 记录 `attempt.strategy_applied`/`attempt.payload_modifications` 供可观测性/历史记录消费。

**候选库核对**：

| 库 | 最新版本/日期 | 维护 | async | 类型 | 许可证 | 核心能力 |
|---|---|---|---|---|---|---|
| `tenacity` | 9.1.4（2026-02-07） | 活跃 | 是（`AsyncRetrying`，支持 trio/curio） | 有 stub | Apache-2.0 | 声明式 `retry`/`wait`/`stop`/`before`/`after`/`before_sleep`/`retry_error_callback`，作用对象是**同一个函数调用**，重试间**不提供修改下次调用参数的一等公民 API**——官方文档明确給出的「改写参数」方案是弃用装饰器、改用 `for attempt in Retrying(...)` 手写循环 + 循环体内自行改写变量，这与本项目现状（`for` 循环 + 策略对象）在结构上几乎同构，套用只是换了个「重试预算/等待策略」外壳 |
| `stamina` | 26.1.0（2026-04-13） | 活跃 | 是（对 tenacity 的封装 + Prometheus/structlog 插桩） | 有 | MIT | 同样是「无改判断地重试同一调用」模型，比 tenacity 更简化但改写语义支持面更窄，不解决核心诉求 |
| `backoff` | 2.2.1（2022-10，近三年无更新） | 一般（长期无发布，但社区仍在用） | 部分（装饰器可包 async 函数，无独立异步等待策略集） | 无官方 stub | MIT | 装饰器模型同 tenacity，功能更薄 |

**是否威胁 P1/P6/保真度**：不直接违反。风险在于「借用」的诱惑——若强行把 `RetryStrategy.handle()` 塞进 tenacity 的 `retry_error_callback` 或用其状态在策略间传递 `modified_payload`，会导致：
1. 优先级匹配（`can_handle` 链式尝试第一个命中的策略）与 tenacity 的单一 `retry` 谓词模型不匹配，需要额外包装层；
2. `max_reactive_retries` 是**跨策略共享**的预算而非某个策略的私有重试次数，tenacity 的 `stop_after_attempt` 是绑定单个 `Retrying` 实例的，若要共享预算需要在多个策略间传递同一个 stop 计数器，等价于自己再实现一遍预算跟踪；
3. `on_resolved()` 学习回调需要感知「这次重试是策略 A 成功还是策略 B 成功」，tenacity 的 `after`/`retry_error_callback` 拿到的是最终结果，不天然携带「哪个策略生效」的语义，需要额外埋点。

**推荐：保留自研**。可选借用点（不改变控制流，只借类型/纯函数）：
- `tenacity.wait_exponential` / `tenacity.wait_random_exponential` 的抖动退避算法思路可以借鉴到 `AdaptiveRateLimiter` 的指数退避实现（不引入依赖，照抄公式即可，公式本身无版权价值）；
- `NetworkRetryStrategy`（延迟 1 秒重试一次，无 payload 改写）这类**不改写 payload 的纯粹重试**，理论上可以用 tenacity 的 `@retry(wait=wait_fixed(1), stop=stop_after_attempt(1))` 包装成独立小函数，但考虑到它仍需融入统一的 `RetryStrategy` 协议（`can_handle`/`handle`/`name` 接口一致性），引入 tenacity 只覆盖 6 个策略中最简单的 1 个，边际收益低于多引入一个依赖的认知成本，**不建议单独为它引入外部库**。

### 自适应限流器（`AdaptiveRateLimiter`）

**现状**：[request-pipeline.md](../request-pipeline.md) L256-323 描述的是一个 3 态状态机（Normal / Rate-Limited / Recovering），核心行为：
- `acquire()`：Normal 直接放行；Rate-Limited 通过 `asyncio.Event` 阻塞直至恢复；
- `report_success()` / `report_rate_limit(retry_after)`：**由上游响应反馈驱动**状态迁移——收到 429/503（[request-pipeline.md](../request-pipeline.md) L110-113, L229）触发 `report_rate_limit`，之后连续 N 次成功（`consecutive_successes`，默认 5）才从 Recovering 回到 Normal；
- 退避时长 = `retry_after`（来自 body/header）或指数退避（`current_backoff * 2` 封顶 `max`）；
- 超时兜底：长时间 Rate-Limited 无成功请求自动尝试恢复（`recovery_interval`，默认 600 秒）。

**候选库核对**：

| 库 | 最新版本/日期 | 维护 | async | 许可证 | 核心能力 | 是否支持反馈自适应 |
|---|---|---|---|---|---|---|
| `aiolimiter` | 1.2.1（2024-12-08） | 活跃 | 原生 asyncio | MIT | 漏桶算法，构造时固定 `(max_rate, time_period)` | 不支持——纯粹「限制我方发起速率」，无状态机、无 429 反馈钩子 |
| `limits` | 5.8.0（2026-02-05） | 活跃 | 部分（`aioredis`/`motor` 等 async 存储后端，核心算法本身同步计算） | MIT | 固定窗口/移动窗口/滑动窗口计数器三种**静态速率策略**，多种存储后端（内存/Redis/Memcached/MongoDB） | 不支持——库本身定位是"提前声明速率、按策略计数"，不消费上游响应反馈 |
| `pyrate-limiter` | 4.4.0 | 活跃 | 部分 | MIT/Apache（需查具体，通常 Apache-2.0，PyPI 页注明 License Expression） | 令牌桶变体，支持多规则组合限流 | 不支持——同上，静态规则限流器 |

**是否威胁 P1/P6**：不直接违反（这些库都是纯内存态、非阻塞 I/O 意义上的操作），但**能力不匹配是根本性的**——三个候选库解决的是"客户端要不要发这么快"，本项目要解决的是"上游告诉我它现在限流了/恢复了，我要不要暂停发送以及暂停多久"，这是两个不同问题域（client-side throttling vs. reactive backpressure state machine）。用这些库需要在其外面再包一层状态机来消费 429/503 反馈——那层状态机就是本项目已有的 `AdaptiveRateLimiter` 核心逻辑，引入库对减少代码量没有实质帮助。

**推荐：保留自研**。`AdaptiveRateLimiter` 本身状态机简单（3 态 + 一个 `asyncio.Event` + 一个 backoff 计时任务），代码量小、逻辑清晰，重写成本远低于适配一个语义不匹配的库并维护额外的胶水层。

### TTL 缓存

需要拆开评估三个具体自研点，它们的"TTL 缓存"表象相似但语义差异很大：

#### 3a. `anthropic/thinking/quarantine.py`（L3 会话隔离）

**现状**：[thinking-pipeline.md](../thinking-pipeline.md) L385-451，`ThinkingQuarantineStore` 是一个 `dict[(session_id, agent_id), float]`（键→最后命中时间），**滑动 TTL**（每次命中刷新过期时间，非固定过期）、惰性过期（仅在 `record()` 时机顺带清理，不设独立后台定时器）、有界（`max_entries` 淘汰最旧）、单一 TTL 来源（`ttl_hours_getter` 热重载读取配置）。

**候选库核对**：`cachetools.TTLCache` 的语义是**固定过期**（`ttl` 参数是常量，`__setitem__` 时基于 `timer()` 计算过期时间戳，之后不会因为再次 `get`/命中而"续期"）——这与本项目"每次命中都要刷新 TTL（滑动窗口）"的需求**不一致**。`cachetools` 官方文档未提供"touch 续期"这一功能（其设计哲学更接近 `functools.lru_cache` 的加强版，是访问顺序驱动淘汰而非固定 TTL 刷新）。若要用 `TTLCache` 模拟滑动 TTL，需要每次命中时 `del` 旧 entry 再重新 `__setitem__`，这本身就是重新实现 `touch()` 语义，价值有限。

`cacheout` 支持 TTL，但最新版本 0.16.0 发布于 2023-12-22，此后约两年无发布，维护活跃度存疑（见调研数据）；且是否支持滑动续期同样未在文档明确验证，不建议为一个已停滞维护的库承担依赖风险。

`aiocache` 面向"外部缓存后端"（Redis/Memcached）抽象，其内存后端 `SimpleMemoryCache` 支持 TTL，但定位是跨进程/分布式缓存客户端，对单进程内存字典场景是重量级抽象，且异步接口对一个纯 CPU 内存操作（应为 O(1) 同步操作）套用 `async def get/set` 没有实际价值，反而引入不必要的协程调度开销（这里的 O(1) 读**不应该是 async 的**，参见硬约束"热路径操作应 O(1)、纯内存优先"）。

**推荐：保留自研**。当前实现（`dict` + 惰性 `_prune_locked`）已经是这个具体场景下最直接的实现，滑动 TTL + touch 语义是候选库未原生覆盖的能力，引入库反而需要额外包装层来补齐这个语义缺口。

#### 3b. `anthropic/feature_negotiation.py`（11 类别学习缓存）

**现状**：[feature-negotiation.md](../feature-negotiation.md) 描述的不是一个简单 TTL 缓存，而是一套完整的**学习知识库**：
- 每条 entry 携带 `LearnedEntryMeta`（`first_learned_at`/`last_confirmed_at`/`pinned`/`manually_expired`/`migrated`）而非仅一个过期时间戳；
- 裁决逻辑是自定义纯函数 `is_entry_active(meta, category, now)`（pin 优先于 TTL、manually_expired 优先于 TTL、按 category 查表得 TTL 而非全局统一 TTL）；
- 键结构因类别而异（`(base_url, endpoint, model)` 三元组 / `(base_url, endpoint)` 二元组 / 仅 `model`），且部分类别值本身是集合（`betas` 是 beta token 集合）、部分是有序列表（`efforts`）、部分是布尔成员（`effortUnsupported`）；
- 需要与 config 静态孪生键做**运行时并集**（`config ∪ 学习缓存.active_keys()`）；
- 需要管理 API（GET 快照/`renew`/`expire`/`pin`/`delete`/`export`）操作单条 entry 的元数据；
- 持久化是 v1→v2 版本化 JSON 格式 + 防抖 + 原子 rename，而非缓存库常见的"整体序列化/反序列化"模型。

**候选库核对**：`cachetools`/`cacheout`/`aiocache` 都是"键 → 值 + 单一固定 TTL"的通用缓存抽象，完全不覆盖：per-entry 多字段元数据裁决、pin/manually_expired 语义、按类别差异化键结构、版本化持久化格式迁移、管理 API 对单条 entry 的细粒度操作。这不是"TTL 缓存能力不够强"的问题，而是**这里的"缓存"本质上是一个领域特定的知识库/状态存储**，TTL 只是其中一个维度（还有 pin、手动失效、迁移标记、类别 TTL 覆盖）。

**是否威胁 P1/P6**：不适用（这不是库选型能不能用的问题，是需求形态完全超出通用缓存库覆盖范围）。

**推荐：保留自研**，且这个结论非常明确——套用任何通用缓存库都需要在其外面重新实现全部上述定制语义，库本身贡献的价值（键淘汰/内存管理）在这里占比很小，反而增加一层"库的缓存语义"与"自己的裁决语义"对不齐的认知负担。

#### 3c. `auto_truncate/token_limits.py`（动态 token 限制学习）

**现状**：从错误响应中提取模型实际 token 限制（如 `"token limit: 200000"`），缓存供后续请求主动截断预判（[request-pipeline.md](../request-pipeline.md) L192-195，[project-structure.md](../project-structure.md) L582）。文档对这一模块着墨不多，未明确是否需要 TTL（模型的 token 限制一般不会频繁变化，甚至可能是**永久性**学习，不同于 feature negotiation 需要重新试探"上游是否已修复"）。

**推荐**：若确认不需要 TTL（大概率），这就是一个普通 `dict[model, int]`，不需要任何缓存库。若确认需要 TTL（例如上游可能扩容模型限制），语义与 3a 类似（简单场景），届时可复用与 3a 相同的判断——**保留自研**或直接量身定制，不必引入库。**遗留疑问**：本文档对 token_limits.py 是否需要 TTL 未给出权威定义，需向用户/主会话确认（见下方遗留疑问）。

### 断路器 / deadline（`pipeline/manager.py`）

**现状**：[shutdown.md](../shutdown.md) L224-356 描述两套互补机制：
1. **Stale reaper**：`RequestContextManager` 后台 `asyncio.Task` 每 60 秒扫描一次 `_active` dict，超过 `stale_max_age`（默认 600 秒）的请求强制 `fail()`——纯粹的**周期性清理**，非断路器（不做"连续失败次数触发跳闸"的决策，只按超时清理单个请求）。
2. **Request deadline**：`register()` 时若 `request_deadline > 0`，`ctx.arm_deadline(request_deadline, on_expire=...)`——单请求硬性总时长 SLA，语义等价于一个每请求独立的定时器（`asyncio.get_event_loop().call_later` 或等价物），到期强制失败。

这两者都**不是断路器模式**（circuit breaker 是"连续失败达到阈值后，暂停向某下游发起新请求一段时间，避免雪崩"），而是**单请求级别的存活时长约束**——本质更接近 `asyncio.wait_for`/超时原语的组合应用（一个是周期扫描型超时，一个是逐请求定时器型超时）。

**候选库核对**：
- `anyio`：项目已依赖 FastAPI/httpx/uvicorn 生态，`anyio.move_on_after()` / `anyio.fail_after()` 提供结构化并发超时原语，语义上可以替代"`ctx.arm_deadline` + `on_expire` 回调"这种手写定时器模式——用一个包裹请求执行协程的 `async with anyio.move_on_after(deadline):` 块 + `cancelled_caught` 检测，比手写 `call_later` + 回调更符合结构化并发范式、更不容易泄漏定时器。**但**：项目当前用的是 `asyncio.Lock`/`asyncio.Event`/`asyncio.Task` 原生 API（未见直接依赖 anyio 作为并发原语层，仅 httpx/fastapi 传递依赖），全面切换到 anyio 超时原语意味着要评估是否连带切换其他并发原语以保持一致性风格，这是**架构层面的决策**（是否让 anyio 成为项目的并发抽象层），不是"引入一个小工具库"量级的决定；
- `circuitbreaker`（2.1.3，2025-03-31，BSD，原生 async 支持）：这是真正的断路器库（连续失败触发跳闸），但本项目**当前文档描述的机制根本不是断路器语义**（没有"连续失败阈值→暂停发起新请求"的需求描述，`stale_max_age`/`request_deadline` 都是超时类型而非跳闸类型）。是否需要引入真正的断路器模式是一个**需求缺口**而非"库选型"问题——若未来发现"上游连续报错 N 次应暂停发送新请求"这类需求（不同于`AdaptiveRateLimiter`已覆盖的 429/503 反馈），才值得评估 `circuitbreaker` 或 `aiobreaker`；当前文档没有这个诉求，不构成本次调研的替换对象。

**是否威胁 P1/P6**：不适用。

**推荐**：
- Stale reaper + request deadline：**保留自研**，可选用 `anyio.move_on_after` 替代 `arm_deadline`/`call_later` 手写定时器实现（借用**超时原语**，不改变整体控制流架构）——这是一个值得在实现阶段做的小型工程改进，但不是"用库替代自研机制"意义上的架构级替换，且需要先决定项目并发原语是否统一迁移到 anyio（见遗留疑问）。
- 断路器：**不采用** `circuitbreaker` 类库——当前无对应需求，属于超出当前范围的能力，不应为"可能用到"而预先引入依赖。

## 遗留疑问 / 需主会话或用户裁决的点

1. **并发原语统一层**：项目当前直接使用 `asyncio.Lock`/`Event`/`Task`/`create_task`（见 `manager.py`、`rate_limiter.py` 代码片段），`anyio` 目前只是 FastAPI/httpx 的传递依赖。是否要把 `anyio` 提升为项目显式的并发抽象层（借其结构化超时/取消原语替代手写 `call_later`），是一个跨域的架构决策，建议由主会话统一评估（可能同时影响域1/域3/域4 涉及的其他 `asyncio.Task` 用法），而非本域单独决定。
2. **`auto_truncate/token_limits.py` 是否需要 TTL**：现有文档（request-pipeline.md L192-195、project-structure.md L582）只说"缓存"未明确过期策略。若模型的实际 token 限制被认为是稳定不变的（不同于 feature negotiation 需要"重新试探上游是否已修复"），则不需要 TTL，是最简单的持久 dict；若认为上游可能调整限制、需要定期重新试探，则需要与 feature negotiation 同款 TTL 裁决语义。这个决定影响是否需要额外设计，建议请用户/`architect-advisor` 明确该模块的过期语义后再定案（当前调研结论不受此影响：无论哪种，都不建议引入通用缓存库，因为不涉及本文档 3a/3b 未覆盖的新能力）。
3. **是否存在真正的"断路器"需求**：当前文档只描述了 `AdaptiveRateLimiter`（响应 429/503 反馈）和 stale reaper/deadline（超时清理），没有"连续 N 次非限流类错误（如 5xx）后暂停向上游发送新请求"的断路器语义。若未来有此类需求（例如上游服务大面积故障时，避免用光 `max_reactive_retries` 预算和历史/遥测记录被大量失败请求淹没），届时可重新评估 `circuitbreaker`/`aiobreaker`；当前不构成本次域2 调研范围内的推荐项，特此记录以免被"静默砍掉"（呼应 `no-silently-cut-but-defer`）。

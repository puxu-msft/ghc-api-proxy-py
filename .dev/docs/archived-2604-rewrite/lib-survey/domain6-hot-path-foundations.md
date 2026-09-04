# 域6：热路径基础能力与遗漏模块

> 本报告补齐 [HANDOVER](HANDOVER.md) 第 5 节列出的覆盖缺口。事实核验日期为 2026-07-15；版本号来自 PyPI JSON API，行为结论来自项目固定版本源码、候选库源码或隔离探针。版本号只用于证明当前兼容性，实施时仍应重新解析最新稳定版并锁定。
>
> **后续裁决（2026-07-17）**：代理侧历史截断已删除。下文对应调研仅作历史记录；保留的是 `tiktoken`、协议计数、校准与 prompt-limit observation。

## 结论总表

| 自研点 | 候选 | 推荐 | 核心理由 |
|---|---|---|---|
| JSON 热路径编解码 | `orjson` / `msgspec` | **采用 `orjson` 作为 wire JSON codec；保留 Pydantic 作为模型与校验层** | 当前数据流以宽松 `dict`、Pydantic 和原始协议字段为主，不准备迁移到 `msgspec.Struct`；`orjson` 对现有对象形态改动最小，真实仓库样本中编解码明显快于标准库和 `msgspec`，并直接返回 `bytes`，适合 SSE 帧与 HTTP body |
| 低频配置、错误快照、人工可读 JSON | 标准库 `json` | **保留标准库** | 这些路径不在请求热路径，且需要 `indent`、稳定可读输出；统一强换 `orjson` 没有收益 |
| 精确 Anthropic token count | Anthropic/Copilot `/v1/messages/count_tokens` | **默认走上游端点** | 与真实上游准备流水线同源，最接近实际计费口径；这是远端 API，不应与本地 tokenizer 混为一谈 |
| 本地 token 估算与离线回退 | `tiktoken` / `tokenizers` | **采用 `tiktoken` 的 `o200k_base`，不采用 `tokenizers`** | 设计明确需要 OpenAI `o200k_base`；`tiktoken` 原生提供该编码，`tokenizers` 只是通用 tokenizer 引擎，不附带等价的 OpenAI encoding 定义 |
| transport 级网络重试 | HTTPX 内建 retries / `httpx-retries` | **不采用自动 transport 重试；显式禁用 OpenAI/Anthropic SDK 内建重试** | 隐式重试绕过 `RequestContext.attempts`、共享预算、限流反馈和学习回调，并可能与代理重试相乘；流开始后的读取失败也无法由 transport 自动安全重放 |
| KMP 流式重复检测 | `regex` / `pyahocorasick` 等 | **保留自研、固定有界窗口** | 需求是发现未知周期，不是搜索已知模式；Aho-Corasick 解决多固定模式，正则回溯方案不适合逐 delta 有界延迟，KMP 前缀函数是更小且确定性的算法核心 |
| 本地 token 估算与校准 | LangChain/LlamaIndex 消息裁剪工具 | **不采用裁剪器；保留 `tiktoken` + 自研 size-aware calibration** | 计数与校准不改写请求前缀；消息裁剪破坏 KV/prompt cache 与语义 |
| sanitize 管道 | Pydantic / `jsonschema` | **保留领域清洗；边界结构校验继续用 Pydantic** | sanitize 是有序、可审计、可重复执行的协议修复状态机，不是 JSON Schema validation；未出现“执行任意用户 schema 验证实例”的需求，不应为此引入 `jsonschema` |
| 四阶段优雅关闭 | Uvicorn lifespan / AnyIO | **保留协调器；借 lifespan 和结构化取消原语** | Uvicorn 只能提供服务器生命周期钩子，不能表达本项目的阶段升级、共享 abort、历史库延迟关闭和资源顺序；第三方库只能提供原语，不能替代编排 |

## 1. JSON：采用 `orjson`，但限定在 wire 热路径

### 官方元数据与兼容性

| 库 | 核验版本 | Python 要求 | Python 3.14 构建 | 许可证 |
|---|---:|---|---|---|
| `orjson` | 3.11.9 | `>=3.10` | 有 Linux/macOS/Windows `cp314` wheels | MPL-2.0 AND Apache-2.0/MIT |
| `msgspec` | 0.21.1 | `>=3.10` | 有 Linux/macOS/Windows `cp314` wheels | BSD-3-Clause |

两者都满足 Python 3.14，性能和维护状态都不是淘汰项。真正的选择依据是数据模型边界：本项目已决定以 Pydantic 做入站校验，以宽松 `dict` 保留未知 wire 字段，并且 SDK 底层 `post(body=...)` 也接收普通 mapping。`msgspec` 的最大额外价值来自把模型迁移到 `msgspec.Struct` 后获得一体化 schema decode；若只调用 `msgspec.json.encode/decode`，它对本项目不会减少模型层代码，反而形成 Pydantic + msgspec 两套类型系统。

### 仓库样本探针

隔离探针使用 [available_models.json](../../../refs/available_models.json) 与 [compacted_user_msg_sample.json](../../../refs/compacted_user_msg_sample.json)，每组 300 次、7 轮取中位数，并先用标准库 round-trip 校验语义等价。执行环境为 CPython 3.14.2、JIT 可用但关闭、Linux x86_64、AMD EPYC 7763 虚拟机配额 16 vCPU；未单独固定 CPU 频率，结果只说明本项目现有样本上的方向，不当作跨机器绝对 benchmark：

| 样本 | 标准库 encode | `orjson` encode | `msgspec` encode | 标准库 decode | `orjson` decode | `msgspec` decode |
|---|---:|---:|---:|---:|---:|---:|
| models，42,863 bytes | 85.77 ms | 9.13 ms | 14.07 ms | 66.50 ms | 30.87 ms | 35.66 ms |
| compacted message，3,258 bytes | 8.07 ms | 0.50 ms | 0.79 ms | 6.68 ms | 1.34 ms | 1.49 ms |

### 采用边界

- 新增一个很薄的内部 JSON codec 边界，例如 `wire_json.dumps(obj) -> bytes` 与 `wire_json.loads(data)`，内部委托 `orjson`。业务模块不要散落直接 import，以便集中记录兼容选项并可做 differential tests。
- 跨协议 SSE 只序列化当前事件，不聚合完整响应；`orjson` 不改变 P6 的逐事件语义。
- Pydantic 对象先显式 `model_dump(mode="json")`，不要依赖隐式序列化魔法。未知字段是否保留由 Pydantic model 的 `extra` 策略和 translator 决定，不由 codec 猜测。
- 低频持久化继续用标准库 `json`，尤其是格式化配置、错误快照、迁移文件和人工可读导出。
- 实施测试必须覆盖非 ASCII、空块、超大整数策略、非有限浮点、datetime、未知嵌套字段和逐帧 byte-for-byte 期望。`orjson` 与标准库对 NaN/Infinity 等边界值的默认行为不同，不能只跑性能测试。

## 2. Token counting：远端精确、本地估算，两层并存

### 远端精确路径

Anthropic 官方 API 提供 `POST /v1/messages/count_tokens`，项目设计则通过 Copilot 同名上游端点和现有认证调用。默认路径应继续按 [anthropic-compat](../anthropic-compat.md) 的设计，复用真实 request preparation，并在端点不支持或远端失败时降级。远端 count 是网络调用，不能被描述成“使用 Anthropic tokenizer 库”。

### 本地估算路径

`tiktoken` 0.13.0 要求 Python `>=3.9`，有 `cp314` wheel；`tokenizers` 0.23.1 要求 Python `>=3.10`，其 wheel 使用稳定 ABI/平台标签而不是文件名中的 `cp314`。后者兼容性不是淘汰原因，能力形状才是：设计指定 `o200k_base`，`tiktoken` 直接提供，`tokenizers` 不提供可无歧义替代的 OpenAI encoding bundle。

源码核验发现 `tiktoken` 的 `o200k_base()` 首次构造会调用 `load_tiktoken_bpe()` 读取 OpenAI 公共 blob URL。一次干净缓存探针的首次 `get_encoding("o200k_base")` 用时约 1.22 秒；这意味着“首次请求里懒加载 encoding”会同步执行网络/磁盘工作，违反热路径纪律。必须：

1. 在应用 startup/lifespan 阶段预加载 encoding，并把失败显式记录为“本地估算不可用”；不能在首个请求中下载。
2. 生产构建若要求离线可启动，应在部署镜像中预热并固定 `TIKTOKEN_CACHE_DIR`，同时验证 hash；不能假设运行环境可访问公共 blob。
3. tokenization 是 CPU 工作。长上下文计数应通过有界 `asyncio.to_thread()`/专用 executor offload，或至少以基准确定一个直接执行阈值，避免大请求阻塞事件循环。
4. `o200k_base` 对 Anthropic 只提供估算，必须保留校准因子和“不精确”语义，不能用本地值冒充服务端精确结果。

## 3. 网络重试：只保留一个显式、可观测的重试所有者

HTTPX 内建 `HTTPTransport(retries=N)` 只重试 `ConnectError` 与 `ConnectTimeout`。`httpx-retries` 0.6.0 是真实且活跃的项目，支持同步/异步 `RetryTransport`、状态码与退避策略；此前“项目已删除”的线索来自错误的 GitHub URL，已纠正。它的官方文档也明确说明：transport 已经返回 response 后，消费流式 body 时发生的 `ReadTimeout` 不会被 transport 自动重试。

项目固定的 OpenAI 2.21.0 与 Anthropic 0.79.0 SDK 都默认 `DEFAULT_MAX_RETRIES = 2`，并自动重试 408、409、429、5xx 以及部分连接异常。如果外层 `NetworkRetryStrategy` 再允许 5 次尝试，默认 SDK 重试可能把一次逻辑请求放大成最多 18 次实际调用，而且中间 attempt 不会进入本项目的历史、共享预算和限流状态机。

因此推荐：

- 构造两个 SDK client 时显式设置 `max_retries=0`。
- 不在底层 `AsyncHTTPTransport` 外包 `RetryTransport`，也不设置 HTTPX transport retries。
- 所有可重放的 pre-header 连接错误、408/409/429/5xx 都回到项目 `RetryStrategy` 调度器，由一个共享预算和 attempt 记录统一裁决；429/503 同时反馈给 `AdaptiveRateLimiter`。
- 流一旦向客户端提交，普通 transport retry 禁止自动重放。只有显式 opt-in 的 `buffered_retry` 能在“尚未向客户端暴露任何真实数据、缓冲未超 cap、请求可重放”时重试。
- 对 token exchange、模型目录刷新等后台调用，也应有各自显式且有界的上层策略；不能因为它们不走主请求 pipeline 就开启不可观测的无限 transport retry。

这不是否定 `httpx-retries` 的质量，而是拒绝让 transport 层成为第二个重试所有者。若未来出现完全独立、幂等、无需纳入统一 attempt 审计的 HTTP client，它仍可作为候选重新评估。

## 4. 其余遗漏模块

### KMP 重复检测

检测目标是滑动窗口末尾是否形成未知周期，并非在文本中搜索预先给定的 pattern。`pyahocorasick`、Hyperscan 类库针对“许多已知 pattern”；正则 backreference/回溯方案既不提供可靠的流式增量状态，也更难给出最坏情况时延上界。保留小型 KMP 前缀函数实现更符合需求。

实现时应补上两项约束：窗口必须严格有界；不要在每个极小 delta 上无条件重算整个 10,000 字符窗口，可按最小累计增量或事件节流触发检测，并用 property-based tests 与朴素 oracle 对拍。

### Auto-truncate

LangChain 的 message trimming 和 LlamaIndex 的 token splitters 可以处理一般 token budget，但不知道本项目的 thinking signature 保真、tool 配对、消息索引映射、system 保护和响应式错误学习。采用它们会把真正困难的协议不变量留在外层 glue 中，并引入完整框架依赖。引擎保留自研，token primitive 使用 `tiktoken`，截断后的 Phase 2 sanitize 必须重跑。

### Sanitize 与 JSON Schema

Pydantic 继续负责固定入站结构的 validation；sanitize 负责顺序敏感的领域修复和记录 `SanitizationResult`。`jsonschema` 适合“给定任意 schema，验证任意 instance”，当前设计没有要求代理执行客户端 tool schema 或 tool arguments 的完整 Draft validation。仅转发/保留 tool schema 时引入它会制造错误拒绝和额外 CPU 成本。未来若明确新增“本地执行 JSON Schema validation”的产品能力，应优先采用 `jsonschema` + `referencing`，而不是手写 Draft 实现。

### 优雅关闭

FastAPI lifespan/Uvicorn shutdown 事件适合作为协调器入口；AnyIO/asyncio 适合提供 task group、event、cancel scope 和 timeout 原语，但没有库能替代 Setup → Graceful Wait → Abort → Force Close 的领域顺序。协调器必须保留，并保证重复信号升级、History DB 延迟关闭、上下游连接关闭顺序和遥测 flush cap 都有集成测试。

### 事件循环实现

独立核验补充了 `uvloop`：0.22.1 要求 Python `>=3.8.1`，提供 Linux/macOS 的 CPython 3.14 与 free-threaded wheels；在项目 Python 3.14.2 环境的 `uvloop.run()` 最小探针通过。它是 Uvicorn 原生支持的成熟 asyncio event loop 候选，但不能只凭通用“更快”结论直接设为默认：本项目更看重 SSE/WS 公平性、取消、信号和 shutdown 正确性。建议作为 Linux/macOS deployment extra，先用真实代理负载与 asyncio 3.14 对照；Windows 无 uvloop wheel，保持标准 asyncio。未找到把 `uvloopx` 视作正式后继的权威依据，不纳入候选。

## 5. 与硬约束的最终对齐

- P1：`tiktoken` encoding 在 startup 预载；大文本 tokenization offload；低频持久化仍 off-loop。
- P6：`orjson` 只编码单帧；所有底层自动重试关闭；流后错误不隐式重放。
- 保真度：codec 不负责删字段；Pydantic/translator 明确保留 unknown；同协议仍走原始 bytes 直通。
- 可观测性：每次真正上游调用由唯一 retry owner 建立 attempt；不允许 SDK/transport 在下面产生不可见重试。

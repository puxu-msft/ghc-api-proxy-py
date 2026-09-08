# `docs/2604-rewrite` 活文档真相审计

## 评审范围与结论

- **评审范围**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/*.md` 拟提升为活文档的顶层主题文档；以 `/home/xp/src/ghc-api-proxy-py/src/app/**` 的生产接线为实现真相源，并以用户已裁决的“block-level buffering 是基础能力，下游不提供 live streaming 体验”为决策真相源。
- **基线**：仓库根目录 `/home/xp/src/ghc-api-proxy-py`；审计提交 `47d9ef101c4b81ac70d805b1da157b34d021d33d`；审计开始时除 `verification/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md`、`verification/PHASE3_ACCEPTANCE_REPORT.md`、`verification/phase3_acceptance.py` 三个既有未跟踪文件外，工作树无其他改动。
- **总体 verdict**：**存在 blocker**。当前 `docs/2604-rewrite` 不能原样重组为 `docs/` 活文档；必须先修复下列 blocker，并将目标设计、实施计划和历史论证从运行态真相中分层。
- **发现计数**：2 条 blocker，9 条 major，共 11 条；口径仅含本报告列出的 blocker/major，不含 minor/nit。

## 双视角覆盖证据

### 机械核对视角

- 扫描了 26 份顶层候选 Markdown 文档，共 6778 行，并单独识别出 `plan/`、`lib-survey/`、评审记录和 handover 等开发期材料，避免把过程文档误升为活文档。
- 对账了 buffering、keepalive、delayed commit、translator、hot reload、zstd、server-tool、History、SSE、WebSocket 等关键词的全部顶层文档命中，并逐项追到生产路由、settings、lifespan、存储 schema/writer 与协议适配器。
- 对 helper 做了仓库级调用点扫描：`keepalive_stream`、`delayed_first_item`、`collect_with_limit`、`translate_chat_event_to_responses`、`openai_to_anthropic`、`anthropic_to_openai` 和 `RepetitionDetector` 在生产树中只有定义或测试使用，没有生产路由调用点。
- 核对了路由注册表：Anthropic router 只以原始 `/v1/messages*` 注册；OpenAI/Responses router 才有三重前缀；管理配置只有 `GET /api/config`，没有 YAML 写入或 reload 路由。

### 第一人称执行视角

- 模拟“按活文档启用块级 buffering”：文档会引导执行者保持默认零缓冲并把块级方案继续延后，直接违背已裁决目标，且 settings 中没有可启用块级能力的配置。
- 模拟“按文档启用 keepalive/delayed commit”：配置值虽可解析，但 Anthropic handler 不读取它们，实际请求仍只经过 idle timeout 与 raw-byte passthrough。
- 模拟“编辑 YAML 后热重载”：运行中的 `RuntimeState.settings` 不会替换，hooks/history/upstream 也不会重建；文档承诺的 PUT 路由不存在。
- 模拟 OpenAI、Azure、Gemini、Anthropic 四条流式路径：只有 Anthropic 接入 idle timeout；Gemini做专用逐帧转换；其余所谓通用 translator、repetition detector 与 resilience helper 均未进入请求链。
- 模拟 History 写盘失败和大响应导出：Anthropic 路径会等待 `queue.join()`；worker 只增加计数并吞掉异常；其他协议在确认写成功前移除 in-flight；export 在内存中整体 `json.dumps`，都与文档执行语义不同。

## 事实性发现

### 1. [blocker] 已裁决的块级 buffering 被文档写成“默认零缓冲、块级延后”

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:38`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:45`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming.md:5`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming-resilience.md:7`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming-resilience.md:224`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming-resilience.md:225`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/ROADMAP.md:51`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/ROADMAP.md:58`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/ROADMAP.md:59`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/multi-protocol.md:204`。
- **问题**：这些位置共同把“零缓冲直通”写成默认不变量，把整响应缓冲写成 opt-in，把块级 buffering 写成观望项；这与用户已明确裁决“block-level buffering 是基础能力，下游不提供 live streaming 体验”正面冲突。此处不是实现取舍未定，而是活文档准备推翻既有决定。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/routes/anthropic.py:106-120`、`/home/xp/src/ghc-api-proxy-py/src/app/routes/openai.py:33-43`、`/home/xp/src/ghc-api-proxy-py/src/app/routes/azure.py:31-41` 当前都把上游 chunk 直接交给 `StreamingResponse`；`/home/xp/src/ghc-api-proxy-py/src/app/config/settings.py:75-113` 没有块级 buffering 配置；`/home/xp/src/ghc-api-proxy-py/src/app/streaming/buffered_retry.py:8-18` 只有“收集完整字节流直到 cap”的未接线 helper，不是块级策略。
- **失败场景**：重组者按这些文档写新的 `docs/` 后，后续实现者会继续优化 live passthrough，甚至将块级 buffering 维持在 backlog，导致产品契约与用户裁决持续分叉。
- **应迁移层**：把“已裁决的下游交付契约”写入 `docs/` 活架构/流式契约文档；把当前实现缺口、迁移阶段、测试 oracle 写入 `docs/agents/buffering/`；把默认零缓冲、整响应 opt-in、块级延后的旧方案整体放入对应 `archive-2026-08-06/`，保留为被取代方案及理由记录。
- **应如何改写**：活文档应明确“上游读取可流式，但代理以 block 为提交单元；块完成前不向下游暴露，失败块可重取或失败；下游不承诺 token/event 级 live streaming”；同时明确当前 HEAD 尚未完成该接线，不能把现状描述成目标契约。

### 2. [blocker] 流式韧性文档把未接线且语义不匹配的 helper 宣称为已采纳能力

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:82`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:103`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming-resilience.md:9-13`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming-resilience.md:26-82`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming-resilience.md:84-140`。
- **问题**：文档用 `[采纳]` 和现在时描述 delayed commit、block-aware `empty_text` keepalive、合成 anchor/index remap 以及观测双轨，读者会理解为生产能力；实际 Anthropic handler 根本没有调用这些 helper。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/routes/anthropic.py:106-120` 的流式链只有 `with_idle_timeout`、`_history_stream`、`passthrough_bytes`；`/home/xp/src/ghc-api-proxy-py/src/app/streaming/keepalive.py:6-32` 只会定时发固定 `heartbeat: bytes`，不解析 block、无 anchor、无 index remap；`/home/xp/src/ghc-api-proxy-py/src/app/streaming/delayed_commit.py:6-13` 只用 `fail_after` 等待首 item，超时直接抛错，不实现文档所述“先 commit 200 再桥接 pending upstream”；仓库级生产调用扫描未找到二者调用点。
- **失败场景**：运维设置 `anthropic.stream_keepalive_ping_sec` 或 `stream_commit_after_sec` 后不会改变响应行为；长静默仍由 idle timeout 或外层连接处理，无法获得文档承诺的客户端 watchdog 保护与真实状态码窗口。
- **应迁移层**：当前已接线行为进入 `docs/`；完整 delayed-commit/keepalive 设计与接线计划进入 `docs/agents/streaming-resilience/`；未经实现的旧伪代码快照进入该主题的 `archive-2026-08-06/`。
- **应如何改写**：活文档只陈述“当前 Anthropic SSE 为 raw-byte passthrough + idle timeout；settings 中存在尚未消费的 resilience 字段”；开发文档再说明它们如何与已裁决的 block-level buffering 协同，不能继续按 live streaming anchor 作为产品体验前提。

### 3. [major] TCP keepalive 与 HTTP/2 PING 配置是无效旋钮

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming-resilience.md:232-287`。
- **问题**：文档声称配置 socket keepalive 和周期性 H2 PING，并把 `timeouts.upstream_keepalive`、`timeouts.upstream_h2_ping` 列为有效配置；生产 transport 没有消费这两个字段。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/config/settings.py:69-70` 定义了字段；`/home/xp/src/ghc-api-proxy-py/src/app/upstream/client.py:17-38` 创建 `httpx.AsyncClient` 时只配置 HTTP/2 开关、proxy、连接池、`keepalive_expiry` 与 timeout，没有 `socket_options` 或 H2 ping loop；仓库级调用扫描只找到字段定义。
- **失败场景**：用户把两个 interval 调小后以为会发 TCP probe/H2 PING，实际网络行为不变，长静默连接仍可能被中间层回收。
- **应迁移层**：`docs/` 配置参考中标记为“保留但当前未接线”或在实现前移除公开项；实现设计、平台兼容与真实网络探针放入 `docs/agents/upstream-keepalive/`；现有伪实现归档。
- **应如何改写**：明确区分连接池 `keepalive_expiry` 与 TCP/H2 主动保活；只有真实 transport 接线并以网络层探针验证后，后两者才能进入活文档的“支持”清单。

### 4. [major] 配置热重载与配置写 API 不存在，却被跨文档当作运行态能力

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:275`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:297`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:333`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/ROADMAP.md:22`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming.md:260`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/authentication.md:509`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/thinking-pipeline.md:450`。
- **问题**：文档宣称 `GET/PUT /api/config/yaml`、热重载产生新 settings 实例、每请求读取新值以及专门的热重载中间件；当前进程只在启动时加载并固定 settings。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/config/loader.py:48-80` 只提供一次性 `load_settings()`；`/home/xp/src/ghc-api-proxy-py/src/app/server.py:156-166` 在 `create_app()` 时把单个 `RuntimeState(settings=resolved_settings)` 固定到 app；`/home/xp/src/ghc-api-proxy-py/src/app/routes/management.py:17-24` 只有 `GET /api/config`；`/home/xp/src/ghc-api-proxy-py/src/app/server.py:110-137` 的 hooks/reaper 等按启动快照构造，没有 watcher 或替换路径。
- **失败场景**：执行者 PUT 配置会得到 405/404；直接改 YAML 后运行中的 token、hook、history、timeout 与 quarantine 配置均不会改变。
- **应迁移层**：启动期配置契约进入 `docs/CONFIG.md` 等活文档；热重载架构、字段生效分类、原子替换和重建边界进入 `docs/agents/config-hot-reload/`；旧的“已支持”表述进入归档。
- **应如何改写**：活文档必须写“配置在进程启动时冻结，修改后需重启”；只有未来实现明确的 settings publication、各消费者读取策略和集成测试后，才能逐字段标注热生效。

### 5. [major] 通用跨协议 translator 与“薄适配层复用全部核心 pipeline”的叙述失真

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming.md:309-319`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/multi-protocol.md:7-27`。
- **问题**：文档声称 Anthropic↔OpenAI↔Responses 的通用实时事件翻译，并称 Azure/Gemini 复用 sanitize、限流、重试、feature negotiation、thinking 等完整核心 pipeline。实际生产只为 Gemini 做 OpenAI→Gemini 专用转换；Azure 是 OpenAI wire 适配；两个通用 translator 模块未接线。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/streaming/translator.py:5-21` 只实现 Chat event→Responses 的局部函数；`/home/xp/src/ghc-api-proxy-py/src/app/transform/translator.py:6-98` 有 payload 转换函数但生产调用扫描无调用点；`/home/xp/src/ghc-api-proxy-py/src/app/routes/gemini.py:30-92` 是独立 OpenAI SSE→Gemini 转换；`/home/xp/src/ghc-api-proxy-py/src/app/routes/azure.py:66-141` 和 `/home/xp/src/ghc-api-proxy-py/src/app/routes/gemini.py:123-220` 只复用 approval、OpenAI client 与基础 history，不进入 Anthropic feature/thinking pipeline。
- **失败场景**：实现者会错误地在所谓共享 translator 或 pipeline 上修 bug，但真实 Gemini/Azure 路径继续绕过该修复；反向协议转换也根本不会发生。
- **应迁移层**：真实协议路由/转换矩阵进入 `docs/` 活架构；统一 translator 的目标设计放入 `docs/agents/cross-protocol-translation/`；未接线通用 translator 方案归档或明确标成实验代码。
- **应如何改写**：按“入站协议、实际 upstream API、请求转换、响应转换、共享设施”逐端点列矩阵，不再用一个统一流水线图掩盖不同路径。

### 6. [major] “idle timeout 适用于所有流式路径”和 Anthropic 重复检测接线均不真实

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming.md:235-260`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming.md:264-302`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/multi-protocol.md:219`。
- **问题**：文档说 idle timeout 适用于 Anthropic、Chat Completions、Responses 和 Gemini，并说 `RepetitionDetector` 已集成 Anthropic `text_delta`；实际只有 Anthropic route 包装了 idle timeout，重复检测器没有生产调用点。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/routes/anthropic.py:106-116` 是唯一调用 `with_idle_timeout` 的生产路由；`/home/xp/src/ghc-api-proxy-py/src/app/routes/openai.py:33-43`、`/home/xp/src/ghc-api-proxy-py/src/app/routes/azure.py:31-41`、`/home/xp/src/ghc-api-proxy-py/src/app/routes/gemini.py:151-181` 均没有 idle wrapper；`/home/xp/src/ghc-api-proxy-py/src/app/repetition_detector.py:10-34` 只有实现，仓库级生产调用扫描无消费者。
- **失败场景**：OpenAI/Azure/Gemini 上游永久静默时不会按 `timeouts.stream_idle` 终止；Anthropic 重复输出也不会产生日志告警。
- **应迁移层**：当前逐协议覆盖矩阵进入 `docs/`；统一 timeout/detector 接线计划进入 `docs/agents/stream-consumers/`；旧“全覆盖”叙述归档。
- **应如何改写**：用端点矩阵写出每条路径实际 wrapper 顺序；未接线项标为开发缺口，不能从 helper 存在推导为支持。

### 7. [major] History 的 zstd、fire-and-forget、错误韧性与 in-flight 保证均与代码相反

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/history-system.md:20-35`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/history-system.md:68-105`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/history-system.md:320-365`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/history-system.md:453-490`。
- **问题**：文档声称 payload/response 用 zstd level 3 压缩、请求路径非阻塞、写错分类重试并可观测、仅确认写成功后移除 in-flight。生产代码使用原始 JSON bytes；Anthropic finalize 明确等待队列清空；worker 对所有异常只递增计数；其他协议提交后立即移除 in-flight，未等待写成功。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/history/sqlite/writer.py:75-89` 直接 `dumps()` 入 BLOB，无 zstd；`/home/xp/src/ghc-api-proxy-py/src/app/history/consumer.py:26-31` 先 `finalize()` 再 `flush()`，请求终态等待 `queue.join()`；`/home/xp/src/ghc-api-proxy-py/src/app/history/sqlite/writer.py:56-73` 捕获所有异常后只 `error_count += 1`；`/home/xp/src/ghc-api-proxy-py/src/app/routes/protocol_history.py:42-47` 提交后立即删除 in-flight 并广播完成。
- **失败场景**：慢盘会延长 Anthropic 请求完成路径；永久写错不会重试或记录错误详情；OpenAI/Azure/Gemini 写失败时条目同时从内存消失，文档承诺的最后防线不存在。
- **应迁移层**：当前存储与失败语义进入 `docs/` 活 History 文档；可靠投递、压缩与观测改造进入 `docs/agents/history-durability/`；旧设计伪代码进入归档。
- **应如何改写**：分别记录 Anthropic consumer 与 protocol-history 两条 finalize 路径，不得笼统声称同一保证；对“accepted into queue”“SQLite committed”“in-flight removed”三个时点给出真实顺序。

### 8. [major] History 的“完整响应、完整数据模型与 REST/WS 契约”大面积超前于实现

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/streaming.md:55-75`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/history-system.md:112-170`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/history-system.md:378-401`。
- **问题**：文档声称三类 accumulator 生成完整 response，HistoryEntry 包含 duration/bytes/transport/pid/attempt 摘要，列表有分页与多过滤，export 流式，WS 推送完整 EntrySummary 事件集。生产 schema/model 和路由只实现较小子集。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/history/sqlite/schema.py:2-19` 只有 14 列且无 duration/bytes/transport/pid/preview；`/home/xp/src/ghc-api-proxy-py/src/app/history/types.py:10-24` 同样没有这些字段；`/home/xp/src/ghc-api-proxy-py/src/app/routes/history.py:10-30` 是内存后过滤，无 offset/cursor/search/since/until；`/home/xp/src/ghc-api-proxy-py/src/app/routes/history.py:34-39` 把完整对象一次性 `json.dumps`，不是流式导出；`/home/xp/src/ghc-api-proxy-py/src/app/streaming/anthropic_usage.py:10-29` 只旁路解析 usage，不累计完整响应；OpenAI/Azure 的 `/home/xp/src/ghc-api-proxy-py/src/app/routes/protocol_history.py:51-67` 也只记录终态，不累计 response。
- **失败场景**：调用方依文档查询 search/offset 或期待完整响应会拿不到契约；大记录 export 仍整体占内存；WebSocket 消费者会等待从未广播的 `stats_updated` 等事件。
- **应迁移层**：已实现的 schema、路由参数、WS event 清单进入 `docs/`；完整审计模型与 API 扩展进入 `docs/agents/history-api/`；旧 EntrySummary/accumulator 设计归档。
- **应如何改写**：从真实 Pydantic/dataclass/schema 和 FastAPI route 签名生成当前契约表；每个未实现字段或事件放入开发规格，不在活文档中使用现在时。

### 9. [major] Anthropic 文档仍宣称完整 server-tool 支持，与已删除边界和代码冲突

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/anthropic-compat.md:18`；冲突文档为 `/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/tool-use.md:12`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/feature-negotiation.md:19`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/ROADMAP.md:63`。
- **问题**：支持矩阵写“Server-side Tools 完整支持、所有类型、可按配置剥离”，而同目录其他候选活文档明确说已拒绝/删除该能力。两者不能同时成为活文档真相。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/config/settings.py:75-113` 无 server-tool filter/降级配置；`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/request_preparation.py:25-31` 只对普通 `tools` 调用 `preprocess_tools`；`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/feature_negotiation.py:5-15` 的类别中没有 server-tool 类别。
- **失败场景**：客户端按矩阵发送 web search/code execution 并期待代理执行、过滤或降级，实际只可能透传未知字段并由上游决定，拒绝后没有代理补救路径。
- **应迁移层**：不支持边界进入 `docs/` 活协议兼容矩阵；旧完整支持方案进入 `archive-2026-08-06/`；如未来重新引入，只能作为 `docs/agents/server-tools/` 的新规格并重新裁决。
- **应如何改写**：区分“wire 模型允许未知字段透传”与“代理提供 server-tool 能力”；明确不执行、不合成结果、不过滤 blocks、不做拒绝后降级。

### 10. [major] Anthropic Context Management 与 Cache Control 四模式被写成完整支持，但 settings 和准备链均无实现

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:72-76`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/anthropic-compat.md:15`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/anthropic-compat.md:19`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/anthropic-compat.md:144-225`、`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/ROADMAP.md:28-29`。
- **问题**：文档描述 cache_control 四模式、extended TTL、context editing 自动注入和 negotiation 自愈为已支持能力；当前 settings 没有对应键，prepare 链也不执行这些步骤。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/config/settings.py:75-113` 的 `AnthropicConfig` 没有 `cache_control`、`extended_cache_ttl`、`context_editing` 或其阈值/keep 配置；`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/request_preparation.py:23-46` 只移除 `inference_geo`、预处理 tools、destack thinking、构建基础 beta headers；`/home/xp/src/ghc-api-proxy-py/src/app/anthropic/features.py:47-67` 虽可按显式布尔参数构建 beta，但生产 prepare 只传 `tool_search`。
- **失败场景**：用户配置文档中的键会因 `extra="forbid"` 启动失败；不配置时也不会自动注入 context management 或执行 cache mode。
- **应迁移层**：当前支持矩阵与有效键进入 `docs/`；完整功能设计进入 `docs/agents/anthropic-cache-context/`；旧的“完整支持”版本归档。
- **应如何改写**：活文档应标明“当前保留客户端 payload 中模型允许的字段与否取决于 wire model，但代理没有四模式处理和自动 context editing”；实现后再按配置字段与生产调用点逐项提升。

### 11. [major] Anthropic 路由表包含未注册前缀与模型端点

- **文档位置**：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/DESIGN.md:251-255`。
- **问题**：路由表宣称 `/anthropic/v1/messages`、`/anthropic/v1/messages/count_tokens` 和 `/anthropic/v1/models`；生产只注册 `/v1/messages` 与 `/v1/messages/count_tokens`，没有 Anthropic models handler。
- **代码证据**：`/home/xp/src/ghc-api-proxy-py/src/app/routes/anthropic.py:65` 与 `/home/xp/src/ghc-api-proxy-py/src/app/routes/anthropic.py:135` 是仅有两个 Anthropic route decorator；`/home/xp/src/ghc-api-proxy-py/src/app/server.py:167-176` 对 anthropic router 只调用一次无 prefix 的 `include_router`，三重前缀循环仅用于 OpenAI 与 Responses WebSocket。
- **失败场景**：按文档把 Anthropic SDK base URL 指向 `/anthropic` 会得到 404；`client.models.list()` 也没有对应服务端路由。
- **应迁移层**：真实 route table 进入 `docs/API.md` 等活文档；别名前缀与 Anthropic models 的需求/实现计划进入 `docs/agents/anthropic-routing/`；旧路由表归档。
- **应如何改写**：从 `app.routes` 或 OpenAPI 生成当前端点表，并把“计划支持的兼容别名”与“已注册端点”分列，禁止混用现在时。

## 主观建议

无。本报告只列可由当前 HEAD、生产调用链和用户既有裁决独立核验的事实性 blocker/major。

## 迁移总则

1. `docs/` 只保留当前运行态契约与已裁决、必须长期成立的目标不变量；两者必须显式区分“当前实现”与“已决目标”。
2. `docs/agents/<topic>/` 承载实现缺口、PoC、计划、验收 oracle 与尚未接线的设计，不用 `[采纳]` 代替实现状态。
3. `archive-2026-08-06/` 保存被用户裁决取代的零缓冲/整响应方案、旧伪代码和历史评审，不让它们继续充当活文档入口。
4. 重组完成后的活文档应以生产 route/settings/schema 的自动化清单作为机械基线，再由人工补充语义和已裁决目标；helper 文件存在不能作为“已支持”的证据。

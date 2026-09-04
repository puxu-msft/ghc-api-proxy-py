# 文档渐进式迁移计划

> 状态：待主会话接受后执行
> 规划基线：`47d9ef101c4b81ac70d805b1da157b34d021d33d`
> 日期：2026-08-06
> 输入审计：`docs/tmp/live-doc-truth-audit.md`，仅作为本地迁移证据，不提交
> 本计划：`docs/tmp/docs-migration-plan.md`，仅作为本地迁移报告，不提交

## 1. 目标、边界与不可变约束

本计划只规划文档迁移，不包含产品代码实现。迁移采用“先建立一个可独立验证的真相切片，再提交该切片”的方式，不能把 `docs/2604-rewrite/` 一次性搬家后再集中修错。

用户已经裁决文档结构：

- `docs/`：活文档，承载当前运行态真相、已裁决且长期成立的产品合同，以及清晰标注的当前实现缺口。
- `docs/agents/<topic>/{spec,plan,etc.}`：开发文档，承载目标规格、实施计划、PoC、验收 oracle、评审与进行中状态。
- `docs/agents/<topic>/archive-<date>/`：归档文档，承载已被取代的方案、完成后的过程文档、历史评审和 handover。

产品优先级固定为：

1. Anthropic Messages。
2. OpenAI Responses upstream，包括 HTTP 与 WebSocket 上游接线的真实边界。
3. 两条主线共享的 pipeline、配置、History、可观测性和运维基础。
4. Chat Completions、Azure、Gemini 等次级协议与增强能力。

流式产品合同固定为：

- block-level buffering 是基础能力，不是 opt-in backlog。
- 上游可以流式读取，但代理以完整 block 为下游提交单元。
- block 完成前不向下游暴露其局部内容。
- 下游不承诺 token/event 级 live streaming 体验。
- 当前基线代码仍以 raw-byte/chunk passthrough 为主，活文档必须把“已裁决目标合同”和“当前实现状态”分栏书写，不能把目标伪装成已实现，也不能用当前实现反向否定目标。

不得因成本、ROI、YAGNI 或旧文档中的“默认关闭／缓存／延后”标签删除、降级或无限期推迟已记录功能。未进入当前产品主线的能力迁入相应 `docs/agents/<topic>/spec.md` 或 `docs/ROADMAP.md`，保留需求、前置条件和验收意图；若要改变范围，必须单独取得用户裁决。

## 2. 当前基线与事实分层

### 2.1 规划时已核实的基线

- 仓库根目录：`/home/xp/src/ghc-api-proxy-py`。
- HEAD：`47d9ef101c4b81ac70d805b1da157b34d021d33d`。
- 候选源集合：`docs/2604-rewrite/**/*.md`。在该 HEAD 上由 `fd` 文件清单与 Python `Path.rglob()` 两种方法交叉得到 42 份 Markdown；该数字只描述此规划基线。
- `docs/.gitignore` 当前包含 `/tmp`，因此 `docs/tmp/live-doc-truth-audit.md` 与本计划均应保持未跟踪、不得进入任何迁移提交。
- 规划开始时可见的既有未跟踪项为 `docs/.gitignore` 与 `verification/` 下三项；它们不属于本计划，不得被迁移提交带入。

### 2.2 活文档中的两类真相

每份活文档必须使用以下明确标签，不能继续使用含混的 `[采纳]` 表示实现状态：

- **当前实现**：由基线或该切片提交后的生产路由、settings、schema、lifespan、真实调用点和可执行探针证明。
- **已决目标**：由用户裁决或有效 ADR／冻结规格证明，但尚未实现时必须紧邻标注“当前未接线”，并链接到对应 `docs/agents/<topic>/spec.md` 或 `plan.md`。

开发文档可以描述未来实现，但必须写明状态，例如“拟议”“已接受待实现”“实施中”“已完成待归档”。归档文档顶部必须写明取代原因、取代日期和现行入口，不能让搜索命中者把历史方案误认为当前合同。

### 2.3 当前已确认的关键差异

迁移时至少要保持以下差异可见：

- Anthropic Messages 当前只注册 `/v1/messages` 与 `/v1/messages/count_tokens`，流式链路为 idle timeout、History usage tap 与 raw-byte passthrough；block-level buffering、delayed commit、keepalive 没有进入该生产路由。
- OpenAI Responses HTTP 当前位于 `routes/openai.py`，WebSocket 位于 `routes/responses_ws.py`；二者都不能被旧文档写成“复用 Anthropic 完整 pipeline”。
- OpenAI／Responses router 有三重前缀，Anthropic router 没有 `/anthropic` 前缀，也没有 Anthropic models route。
- 配置在 `create_app()` 与 lifespan 启动时固定；当前没有 YAML PUT 或运行时 settings 原子替换路径。
- helper、配置字段或类的存在不等于生产支持。活文档中的“支持”必须有生产调用点或真实端到端探针。

## 3. 主题模型与目标文档

迁移后的主题不是对旧文件名做机械平移，而是按读者任务与产品主线组织。

| 主题 | 活文档 | 开发文档主题 | 内容边界 |
|---|---|---|---|
| 文档入口与架构 | `docs/README.md`、`docs/ARCH.md` | `docs/agents/architecture/` | 当前组件、装配、真实数据流、文档状态约定 |
| API 与协议矩阵 | `docs/API.md` | `docs/agents/anthropic-routing/`、`docs/agents/multi-protocol/` | 实际注册端点、入站协议、真实 upstream、转换与 wrapper 矩阵 |
| 产品路线图 | `docs/ROADMAP.md` | `docs/agents/product-roadmap/` | 已决优先级、完整待实现能力、依赖与状态；不以 ROI 删除能力 |
| Anthropic Messages | `docs/ANTHROPIC_MESSAGES.md` | `docs/agents/anthropic-messages/`、`anthropic-cache-context/`、`anthropic-feature-negotiation/`、`anthropic-sanitize/`、`anthropic-tool-use/` | 当前请求准备、兼容边界、headers、thinking、tools、已决目标与缺口 |
| OpenAI Responses upstream | `docs/OPENAI_RESPONSES.md` | `docs/agents/openai-responses/` | HTTP／WS 当前 upstream、pipeline 差异、历史与 buffering 接入顺序 |
| Buffering 与流消费 | `docs/STREAMING.md` | `docs/agents/buffering/`、`streaming-resilience/`、`stream-consumers/`、`upstream-keepalive/` | 已决 block-level 下游合同、当前逐协议实现矩阵、待实现语义与探针 |
| 配置 | `docs/CONFIG.md` | `docs/agents/configuration/`、`config-hot-reload/` | 真实 settings schema、默认值、生效时点、保留但未消费字段 |
| 认证与模型 | `docs/AUTHENTICATION.md`、`docs/MODEL_RESOLUTION.md` | `docs/agents/authentication/`、`model-resolution/` | 当前 token/provider 与模型解析契约 |
| 请求处理 | `docs/REQUEST_PIPELINE.md`、`docs/SANITIZE_PIPELINE.md` | `docs/agents/request-pipeline/`、`anthropic-sanitize/` | 当前 Anthropic pipeline、重试所有权、mandatory sanitizer |
| Hooks 与 Tokenization | `docs/HOOKS.md`、`docs/TOKENIZATION.md` | `docs/agents/hooks-tokenization/` | 当前运行态摘要与已实施规格／计划历史 |
| History | `docs/HISTORY.md` | `docs/agents/history-durability/`、`history-api/` | 当前 schema、写入时序、REST／WS；可靠性与 API 扩展分开规划 |
| 运行与可观测性 | `docs/OPERATIONS.md`、`docs/OBSERVABILITY.md`、`docs/APPROVAL.md` | `docs/agents/operations/`、`observability/`、`approval/` | 当前关闭、deadline、metrics、tracing、TUI、审批接线 |
| 依赖选型 | 无直接活文档；必要结论链接到 `ARCH.md` | `docs/agents/dependency-selection/` | 调研、选择、证据日期与版本复核 |
| 旧整体实施 | 无 | `docs/agents/2604-rewrite/archive-2026-08-06/` | 已完成总计划、kick-off、handover 与评审历史 |

主题目录只在对应切片开始时创建，不预先建立一整棵空目录。每个新主题至少有一个有内容的 `spec.md`、`plan.md`、`research.md` 或归档文件；Git 不跟踪空目录。

## 4. 逐文件 old → new 映射

映射中的“拆分”表示先从旧文件提炼经过验证的活文档内容与仍有效的开发需求，再把原文件完整移入指定 archive；不复制一份未经标注的旧正文到活文档。“直接迁移”也必须在同一提交内更新标题、状态、链接和事实错误。

### 4.1 顶层设计与主题文档

| 旧文件 | 迁移方式 | 新位置／产物 | 提升前条件 |
|---|---|---|---|
| `docs/2604-rewrite/260403-docs-review-01-claude.md` | 归档 | `docs/agents/architecture/archive-2026-08-06/260403-docs-review-01-claude.md` | 加归档头，链接本审计结论的正式落点，而不是链接 `docs/tmp` |
| `docs/2604-rewrite/BACKLOG.md` | 拆分 | 经重新判定的能力进入 `docs/ROADMAP.md` 与各 topic `spec.md`；原文移至 `docs/agents/product-roadmap/archive-2026-08-06/BACKLOG.md` | 移除以成本／ROI／YAGNI 作为砍功能依据；block buffering 改为基础能力；其余能力全部保留去向 |
| `docs/2604-rewrite/DESIGN.md` | 拆分 | 当前架构进入 `docs/ARCH.md`；实际路由进入 `docs/API.md`；已决产品合同进入对应活文档；未来设计进入各 topic spec；原文移至 `docs/agents/architecture/archive-2026-08-06/DESIGN.md` | 必须修复 buffering、路由、热重载、History、兼容矩阵等审计发现后才能提升 |
| `docs/2604-rewrite/ROADMAP.md` | 重写后迁移 | `docs/ROADMAP.md`；原文移至 `docs/agents/product-roadmap/archive-2026-08-06/ROADMAP.md` | 优先级改为 Anthropic Messages → OpenAI Responses upstream；block buffering 不得留在 M4／延后；所有旧能力有明确新状态与 topic |
| `docs/2604-rewrite/anthropic-compat.md` | 拆分 | 当前支持矩阵进入 `docs/ANTHROPIC_MESSAGES.md`；未接线 cache／context 能力进入 `docs/agents/anthropic-cache-context/spec.md`；原文移至 `docs/agents/anthropic-messages/archive-2026-08-06/anthropic-compat.md` | 修复 server-tool、cache control、context management、路由与“wire 透传 ≠ 代理支持”表述 |
| `docs/2604-rewrite/approval-system.md` | 核实后迁移 | `docs/APPROVAL.md`；超出现状的设计进入 `docs/agents/approval/spec.md`；旧超前内容归档到 `docs/agents/approval/archive-2026-08-06/approval-system.md` | 从 route、gate、WS manager 与测试生成当前 REST／WS／超时矩阵 |
| `docs/2604-rewrite/authentication.md` | 修真后迁移 | `docs/AUTHENTICATION.md`；未实现或待改能力进入 `docs/agents/authentication/spec.md`；原超前版本归档 | 删除热重载现在时，核对 provider 顺序、token refresh、CLI 与脱敏行为 |
| `docs/2604-rewrite/config-system.md` | 重写后迁移 | `docs/CONFIG.md`；热重载目标进入 `docs/agents/config-hot-reload/spec.md`；原文移至 `docs/agents/configuration/archive-2026-08-06/config-system.md` | 配置表从当前 Pydantic schema 生成；逐项标记启动时冻结、运行时消费或“保留未接线” |
| `docs/2604-rewrite/data-models.md` | 拆分 | 对外 wire 契约进入 `docs/API.md`；当前内部模型边界进入 `docs/ARCH.md`；未来模型设计进入 `docs/agents/data-models/spec.md`；原文归档 | 对照 Pydantic/dataclass/schema，删除不存在的 client/upstream 重对象图与 History 字段 |
| `docs/2604-rewrite/feature-negotiation.md` | 核实后拆分 | 当前生产支持摘要进入 `docs/ANTHROPIC_MESSAGES.md`；完整内部合同进入 `docs/agents/anthropic-feature-negotiation/spec.md`；旧版本归档 | 从类别 enum、生产构造、管理 API 和测试同时核对，server-tool 类别不得回流 |
| `docs/2604-rewrite/header-forwarding.md` | 核实后拆分 | 当前用户合同进入 `docs/ANTHROPIC_MESSAGES.md`；详细设计进入 `docs/agents/header-forwarding/spec.md`；原文按需归档 | 对照 request preparation 与 Anthropic route 的实际 request／response header 链 |
| `docs/2604-rewrite/history-system.md` | 拆分 | 当前事实进入 `docs/HISTORY.md`；持久性目标进入 `docs/agents/history-durability/spec.md`；API 扩展进入 `docs/agents/history-api/spec.md`；原文移至 `docs/agents/history-durability/archive-2026-08-06/history-system.md` | 修复 zstd、fire-and-forget、异常、in-flight、schema、分页、export 和 WS 事件等所有超前陈述 |
| `docs/2604-rewrite/hooks-system.md` | 核实后迁移 | `docs/HOOKS.md`；内部完整合同由 `docs/agents/hooks-tokenization/spec.md` 承载 | 对照 registry build、loader、executor、built-ins 与 lifespan；不得宣称热替换 |
| `docs/2604-rewrite/hooks-tokenization-spec.md` | 直接迁移并校正引用 | `docs/agents/hooks-tokenization/spec.md` | 保留“已实施”状态，但逐条复验验收标准与当前代码；活文档引用新路径 |
| `docs/2604-rewrite/model-resolution.md` | 核实后迁移 | `docs/MODEL_RESOLUTION.md`；未来解析能力进入 `docs/agents/model-resolution/spec.md` | 用 resolver 单测与当前 catalog 路径复验优先级、规范化和 override |
| `docs/2604-rewrite/multi-protocol.md` | 拆分 | 实际协议矩阵进入 `docs/API.md` 与 `docs/ARCH.md`；未统一的 translator 目标进入 `docs/agents/cross-protocol-translation/spec.md`；次级协议缺口进入 `docs/agents/multi-protocol/spec.md`；原文归档 | 修复“共享全部核心 pipeline”、通用 translator、idle timeout 全覆盖与 buffering 延后表述 |
| `docs/2604-rewrite/project-structure.md` | 核实后合并 | 当前模块与生命周期并入 `docs/ARCH.md`；详细开发约束进入 `docs/agents/architecture/spec.md`；旧文件归档或在链接清零后删除 | 用真实目录与 server lifespan 复验，不能复制 DESIGN 的目标模块树 |
| `docs/2604-rewrite/request-pipeline.md` | 核实后迁移 | `docs/REQUEST_PIPELINE.md`；未来 strategy／transport 接线进入 `docs/agents/request-pipeline/spec.md` | 明确本文主要描述 Anthropic；OpenAI Responses 的不同路径单独记录，不得宣称统一 pipeline |
| `docs/2604-rewrite/sanitize-pipeline.md` | 核实后迁移 | `docs/SANITIZE_PIPELINE.md`；复杂未来需求进入 `docs/agents/anthropic-sanitize/spec.md` | 对照 mandatory sanitizer 的生产顺序、幂等测试与 hook 边界 |
| `docs/2604-rewrite/shutdown.md` | 拆分 | 已接线运行合同进入 `docs/OPERATIONS.md`；未接线阶段、reaper、deadline 或错误持久化进入 `docs/agents/operations/spec.md`；原文归档 | 不能因 helper／类存在就称为 server 生命周期能力；必须有 lifespan／signal 接线和执行探针 |
| `docs/2604-rewrite/streaming-resilience.md` | 拆分并归档 | 已决 buffering 合同进入 `docs/STREAMING.md`；实现规格进入 `docs/agents/buffering/spec.md`；keepalive／delayed commit 进入 `docs/agents/streaming-resilience/spec.md`；TCP／H2 保活进入 `docs/agents/upstream-keepalive/spec.md`；原文归档 | 原文的 live streaming anchor、delayed commit、keepalive、整响应 opt-in 与 transport 保活均不得直接提升 |
| `docs/2604-rewrite/streaming.md` | 重写后迁移 | `docs/STREAMING.md`；逐协议未接线项进入 `docs/agents/stream-consumers/spec.md`；原文移至 `docs/agents/buffering/archive-2026-08-06/streaming.md` | 以 block-level 下游合同取代零缓冲不变量；修复 accumulator、WS 文件名／复用关系、idle timeout、detector 和 translator 陈述 |
| `docs/2604-rewrite/telemetry-observability.md` | 核实后迁移 | `docs/OBSERVABILITY.md`；未接线或可选设计进入 `docs/agents/observability/spec.md`；原超前版本归档 | 从 setup、route、exporter、配置和真实指标探针生成支持矩阵，不以模块存在判支持 |
| `docs/2604-rewrite/thinking-pipeline.md` | 拆分 | 当前用户可见边界进入 `docs/ANTHROPIC_MESSAGES.md`；内部合同进入 `docs/agents/thinking/spec.md`；原文归档 | 删除热重载现在时，核实 protection／destack／quarantine 的真实生产调用和持久化边界 |
| `docs/2604-rewrite/tokenization.md` | 核实后迁移 | `docs/TOKENIZATION.md`；完整开发规格留在 `docs/agents/hooks-tokenization/spec.md` | 对照 Anthropic／Gemini route、state store、management API 与 calibration 消费者 |
| `docs/2604-rewrite/tool-use.md` | 核实后迁移 | `docs/TOOL_USE.md`；未来改动进入 `docs/agents/anthropic-tool-use/spec.md` | 明确 client tools、tool search 与 server tools 三者边界；server-tool 旧支持不得进入活文档 |

### 4.2 成熟库调研文档

这些文件全部属于开发证据，不直接提升为活文档。选型结论只有在对照当前 lockfile／依赖元数据、生产 import 和维护状态后，才能由 `docs/ARCH.md` 引用；调研中的版本与外部事实必须保留“核验日期”。

| 旧文件 | 新位置 |
|---|---|
| `docs/2604-rewrite/lib-survey/260715-selections-review-01-claude.md` | `docs/agents/dependency-selection/archive-2026-08-06/260715-selections-review-01-claude.md` |
| `docs/2604-rewrite/lib-survey/HANDOVER.md` | `docs/agents/dependency-selection/archive-2026-08-06/HANDOVER.md` |
| `docs/2604-rewrite/lib-survey/SELECTIONS.md` | `docs/agents/dependency-selection/research.md`，核实后保留当前选择；旧快照同时通过 Git 历史可追溯，不复制第二份无标注正文 |
| `docs/2604-rewrite/lib-survey/_briefing.md` | `docs/agents/dependency-selection/archive-2026-08-06/_briefing.md` |
| `docs/2604-rewrite/lib-survey/domain1-llm-sdk.md` | `docs/agents/dependency-selection/research/domain1-llm-sdk.md` |
| `docs/2604-rewrite/lib-survey/domain2-reliability.md` | `docs/agents/dependency-selection/research/domain2-reliability.md` |
| `docs/2604-rewrite/lib-survey/domain3-streaming-sse-ws.md` | `docs/agents/dependency-selection/research/domain3-streaming-sse-ws.md` |
| `docs/2604-rewrite/lib-survey/domain4-storage-config.md` | `docs/agents/dependency-selection/research/domain4-storage-config.md` |
| `docs/2604-rewrite/lib-survey/domain5-observability.md` | `docs/agents/dependency-selection/research/domain5-observability.md` |
| `docs/2604-rewrite/lib-survey/domain6-hot-path-foundations.md` | `docs/agents/dependency-selection/research/domain6-hot-path-foundations.md` |

### 4.3 旧实施计划、kick-off、handover 与评审

| 旧文件 | 新位置 | 说明 |
|---|---|---|
| `docs/2604-rewrite/plan/260715-implementation-plan-review-01-claude.md` | `docs/agents/2604-rewrite/archive-2026-08-06/260715-implementation-plan-review-01-claude.md` | 完成态整体计划评审 |
| `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md` | `docs/agents/hooks-tokenization/archive-2026-08-06/implementation-plan.md` | 已实施计划，不再作为当前待办 |
| `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_KICKOFF.md` | `docs/agents/hooks-tokenization/archive-2026-08-06/kickoff.md` | 已消费 kick-off |
| `docs/2604-rewrite/plan/IMPLEMENTATION_HANDOVER.md` | `docs/agents/2604-rewrite/archive-2026-08-06/IMPLEMENTATION_HANDOVER.md` | 已明确为历史，顶部链接现行 docs index |
| `docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md` | `docs/agents/2604-rewrite/archive-2026-08-06/IMPLEMENTATION_PLAN.md` | 完成态大计划；不得继续作为当前状态真相源 |
| `docs/2604-rewrite/plan/PHASE_0_KICKOFF.md` | `docs/agents/2604-rewrite/archive-2026-08-06/PHASE_0_KICKOFF.md` | 已消费 kick-off |

## 5. 必须先修真相再提升的文件

以下源文件存在审计已指出的当前态／目标态冲突，禁止先 `git mv` 到 `docs/` 再把修真留给后续：

1. `DESIGN.md`、`ROADMAP.md`、`BACKLOG.md`：先纠正 buffering 基线、产品优先级、路由、热重载和以成本缩减功能的旧取舍。
2. `streaming.md`、`streaming-resilience.md`：先以 block-level buffering 和“下游无 live streaming 承诺”重写合同，再分离当前 passthrough 缺口。
3. `anthropic-compat.md`：先纠正 server-tool、cache control、context editing 与路由支持矩阵。
4. `config-system.md`、`authentication.md`、`thinking-pipeline.md`：先删除运行时热重载的虚假承诺并标出生效时点。
5. `multi-protocol.md`：先按真实 route／client／translator 路径重建矩阵。
6. `history-system.md`：先按真实 schema、writer、consumer、in-flight、REST／WS 重建时序与契约。
7. `data-models.md`：先从当前类型和 schema 生成字段表，不把目标模型当现有模型。

以下文件可走“快速真相复验后迁移”，但不能仅因审计未列为 blocker／major 就直接认定正确：`project-structure.md`、`request-pipeline.md`、`sanitize-pipeline.md`、`hooks-system.md`、`hooks-tokenization-spec.md`、`model-resolution.md`、`feature-negotiation.md`、`header-forwarding.md`、`tokenization.md`、`tool-use.md`。

以下文件需要专项运行态复验后决定活文档与开发文档的分界：`approval-system.md`、`shutdown.md`、`telemetry-observability.md`。它们涉及“类已经存在但 server 是否真正装配”的高风险误判。

所有 `lib-survey/`、`plan/`、review 与 handover 文件不需要“提升”为活文档，只需核实归档头、现行入口和链接。

## 6. 渐进式迁移阶段

### 阶段 0：冻结清单与验证方法

**目标**：在不移动源文件的前提下建立可重复的迁移 gate，防止漏文件、混入 `docs/tmp` 或把错误查询当证据。

**前置**：实施开始时记录实际 HEAD；确认规划基线是其祖先。实施后的 HEAD 会随切片提交推进，不应继续要求等于规划基线。

**动作**：

- 记录 `docs/2604-rewrite/**/*.md` 冻结集合与每个文件的目标去向。
- 记录迁移前 `git status --short`，保护既有未跟踪／未提交项。
- 定义 Markdown 本地链接检查、活文档禁用状态词检查、route/settings/schema 生成探针。
- 自定义检查器必须在临时目录做双向控制：正确 fixture 为绿，故意断链或故意加入 `docs/tmp` 链接的 fixture 为红，并确认红灯来自目标检查。
- 不创建仓库内临时报告；所有临时输出放系统临时目录或仅打印 stdout。

**验收**：冻结集合与第 4 节逐项一一对应；`docs/tmp` 不在 Git pathspec；没有产品文件改动。

**提交**：无提交。该阶段只建立执行证据；本计划和审计继续保持未跟踪。

**风险与回滚**：无仓库写入，无需回滚。

### 阶段 1：Anthropic Messages 与 buffering 合同

**目标**：先建立产品最高优先级的最小可信文档面，并把 blocker 从活文档入口中消除。

**产物**：

- `docs/README.md`：只链接已经在本阶段验证的新活文档；明确旧 `docs/2604-rewrite/` 是迁移源而非真相源。
- `docs/ANTHROPIC_MESSAGES.md`：当前 routes、请求准备、header、thinking、tools、token count、当前 stream chain 与未实现项。
- `docs/STREAMING.md`：已决 block-level 合同、当前 passthrough 差异、逐协议状态表的 Anthropic 行。
- `docs/agents/buffering/spec.md`：只细化已经裁决的合同；未裁决的 block 边界、失败重取、内存／磁盘预算、背压、顺序、取消与 History 时点列为门控问题，不自行决定。
- `docs/agents/anthropic-messages/spec.md`：把 Anthropic 当前缺口按主线排序。
- 按第 4 节建立 `anthropic-cache-context`、`anthropic-feature-negotiation`、`header-forwarding`、`thinking`、`anthropic-tool-use` 的最小开发文档；若本切片尚未复验某主题，只建有明确状态的 spec，不提升支持结论。

**TDD／验证替代**：这是纯文档迁移，无法用先写产品红灯测试证明；改用“先固定错误 oracle → 写文档 → 复跑 oracle”。至少验证：

- 从 FastAPI route table 生成 Anthropic 端点，文档集合精确相等。
- 从 `routes/anthropic.py` 的实际调用链确认 idle timeout、History tap、passthrough 与 cleanup 顺序。
- 用 AST／调用图确认 keepalive、delayed commit、buffered retry 没有 Anthropic 生产消费者；不得只用文本零命中。
- 活文档中不再出现“默认零缓冲”“块级延后”“下游逐 token／event live”作为产品合同。
- 已决目标每处都紧邻“当前未接线”与开发 spec 链接。
- 本地链接全绿，且无链接指向 `docs/tmp`。

**独立提交**：`docs: establish Anthropic Messages buffering truth`

**提交范围**：只含本阶段新文档与本阶段明确迁移的相关源文档；提交前用精确 pathspec 审核，显式排除 `docs/tmp/**` 与既有 `verification/` 项。

**风险与回滚**：最大风险是把 block-level 合同写成未裁决的具体协议。通过把具体 block 定义保留为门控问题规避。该阶段以新增为主，可整体 revert 单提交，不影响旧源树。

### 阶段 2：OpenAI Responses upstream

**目标**：在 Anthropic 合同稳定后建立第二产品主线，不用“统一 pipeline”叙述掩盖 HTTP、SSE 与 WebSocket 的真实差异。

**产物**：

- `docs/OPENAI_RESPONSES.md`：入站前缀、HTTP route、WS route、实际 client／upstream、approval、History、stream cleanup、当前 buffering 缺口。
- `docs/agents/openai-responses/spec.md`：把 Responses upstream 的目标能力、block-level buffering 接入、HTTP／WS 一致性和验收 oracle 分开列出。
- 更新 `docs/STREAMING.md` 的 Responses HTTP／WS 行。
- 更新 `docs/README.md`，仅在本阶段验证完成后添加入口。

**验证**：

- 从 route table 生成 `/responses` 的三个 HTTP 与 WS 前缀组合，并分别核对方法／upgrade 语义。
- 对照 `routes/openai.py`、`routes/responses_ws.py` 与实际 client，绘制两条调用链；不能引用不存在的 `routes/responses.py`。
- 核对 Responses HTTP 与 WS 是否共享模型验证、approval、History、重试、idle timeout、buffering；每项按实际写“共享／不同／未接线”。
- 对一个已存在的 route 测试或 OpenAPI probe 做正样本；在临时期望集合中故意加入不存在别名，确保集合检查变红。
- 本地链接全绿，无 `docs/tmp` 引用。

**独立提交**：`docs: document OpenAI Responses upstream truth`

**风险与回滚**：不得顺便承诺 Anthropic↔Responses 通用 translator。未接线统一转换进入 `cross-protocol-translation` 开发主题，不阻塞本阶段当前真相文档。

### 阶段 3：API、架构与配置骨架

**目标**：把两条产品主线需要的公共查阅入口建立起来，但不提前整理所有次级协议。

**产物**：`docs/API.md`、`docs/ARCH.md`、`docs/CONFIG.md`；更新 `docs/README.md`。

**验证**：

- API 表从 FastAPI route table／OpenAPI 生成，当前阶段至少完整覆盖 Anthropic、Responses、management、health 与 History；次级协议可以列真实现状，但不能先写目标别名。
- 架构图从 `server.py` lifespan、`RuntimeState`、deps 与真实 clients 反推，不复制旧 DESIGN 的目标目录树。
- 配置键、类型、默认值从 Pydantic schema 生成；再由生产调用点补充“消费位置／生效时点／未消费”。字段存在与被消费是两个独立列。
- 特别验证 `stream_keepalive_*`、`stream_commit_after_sec`、`upstream_keepalive`、`upstream_h2_ping` 为保留但当前未接线；配置修改当前需要重启。
- 每个 route／配置数字若写入文档，必须标明该切片 commit 和生成口径，并用第二种原理交叉检查。

**独立提交**：`docs: add current API architecture and config references`

**风险与回滚**：自动生成表可能遗漏动态注册，必须用 OpenAPI 与 `app.routes` 两种方法交叉；结果不一致时先解释差异，不能任选一个。

### 阶段 4：主线共享 pipeline、sanitize、hooks 与 tokenization

**目标**：迁移已经实施且直接服务 Anthropic 主线的共享能力，不把其契约泛化到尚未接线的协议。

**产物**：

- `docs/REQUEST_PIPELINE.md`、`docs/SANITIZE_PIPELINE.md`、`docs/HOOKS.md`、`docs/TOKENIZATION.md`、`docs/TOOL_USE.md`。
- `docs/agents/hooks-tokenization/spec.md`。
- 已完成 hooks／tokenization 计划与 kick-off 移入该主题的 `archive-2026-08-06/`。

**验证**：

- 逐文档从生产入口追到实现，不以孤立单测或 helper 定义证明接线。
- Hooks 验证 registry 的启动期冻结、module failure、observer isolation 与当前 built-ins。
- Tokenization 分别验证 Anthropic 上游优先／fallback 与 Gemini 本地估算，不能写成统一协议服务。
- Tool Use 明确 client tool、tool search、server tool 三条边界，并验证生产准备链。
- 运行相关 targeted tests；文档迁移不修改产品代码时，全量 pytest 不是每个小提交的硬门，但最终阶段必须运行项目现有完整质量门。

**独立提交**：`docs: migrate Anthropic pipeline hooks and tokenization docs`

**风险与回滚**：最大的假绿风险是“规格已实施”只由规格自述证明。验收必须从代码和测试独立重建，不从旧 spec 复制结论。

### 阶段 5：认证、模型解析与剩余 Anthropic 内部合同

**目标**：补齐 Anthropic 主线的可操作文档，同时保持活文档简洁、内部设计进入 agent topic。

**产物**：`docs/AUTHENTICATION.md`、`docs/MODEL_RESOLUTION.md`；完善 `docs/ANTHROPIC_MESSAGES.md`；迁移 feature negotiation、header forwarding、thinking 的详细规格到相应 topic。

**验证**：

- Token provider 顺序、account type、refresh、CLI 与脱敏从生产实现和测试复验。
- 模型解析用表驱动样本验证 alias、normalize、override、disabled model 与 catalog 交互。
- Feature negotiation、thinking quarantine、header policy 分别从生产调用链证明接线范围。
- 所有“修改配置后”的描述写明重启要求。

**独立提交**：`docs: migrate authentication and model contracts`

**风险与回滚**：避免把内部算法细节全部堆入用户入口；活文档保留用户可观察合同，详细内部机制链接 agent spec。

### 阶段 6：History 真相与后续能力分离

**目标**：修复审计中 History 的时序、持久性、schema 与 API 超前陈述，为主产品两条路径提供可信记录语义。

**产物**：`docs/HISTORY.md`、`docs/agents/history-durability/spec.md`、`docs/agents/history-api/spec.md`。

**验证**：

- 从 schema 和 types 两种来源生成字段交集／差异，逐字段解释。
- 分别画出 Anthropic consumer 与 OpenAI／Azure／Gemini protocol-history 的 `in-flight → queue accepted → SQLite commit/failure → removal/broadcast` 时序。
- 以真实 route signature 验证 REST 参数，以 WS broadcaster 验证事件集合，以 export 实现验证内存行为。
- 写盘失败行为必须由故障注入测试或现有失败测试证明；若当前没有足够 oracle，活文档明确“未验证”，开发 spec 添加补测要求。
- 不把未来 zstd、重试、流式 export、分页／搜索字段写成当前能力。

**独立提交**：`docs: reconcile History storage and API truth`

**风险与回滚**：History 有两条 finalize 路径，禁止用一条路径的保证覆盖另一条。若时序无法由现有测试证明，文档降为保守的代码可见事实，不自行发明保证。

### 阶段 7：运维、可观测性与审批

**目标**：迁移不改变产品主线但影响操作正确性的活文档，区分已装配服务与未接线 helper。

**产物**：`docs/OPERATIONS.md`、`docs/OBSERVABILITY.md`、`docs/APPROVAL.md` 及对应 agent specs。

**验证**：

- 关闭、deadline、stale reaper、error persistence 均要求 server／lifespan／signal 的真实接线证据。
- Metrics route 实际抓取并核对 content type 与关键指标；tracing／TUI 按配置和启动路径验证。
- Approval REST／WS／timeout／shutdown rejection 用现有集成测试或可复现 probe 核对。
- 配置字段存在但未消费时，移入开发缺口而非当前支持表。

**独立提交**：`docs: reconcile operations observability and approval docs`

**风险与回滚**：运行态能力容易出现静态存在假绿；每个支持结论至少有一次真实 app probe 或集成测试。

### 阶段 8：次级协议与跨协议设计

**目标**：在两条产品主线和共享基础文档稳定后，再整理 Chat Completions、Azure、Gemini，不让次级协议抢占主线迁移节奏。

**产物**：完善 `docs/API.md`、`docs/ARCH.md`、`docs/STREAMING.md`；建立 `docs/agents/multi-protocol/spec.md` 与 `docs/agents/cross-protocol-translation/spec.md`。

**验证**：

- 对每个端点列“入站协议／实际 upstream API／请求转换／响应转换／共享设施／idle timeout／buffering／History”，从 route 到 client 逐条取证。
- 通用 translator 只有生产消费者后才能进入活文档支持矩阵；Gemini 专用转换与 Azure OpenAI wire 适配必须单列。
- 次级协议的未实现能力仍保留在 specs／ROADMAP，不以低优先级删除。

**独立提交**：`docs: reconcile secondary protocol routing and translation`

**风险与回滚**：避免为了统一表格强造统一架构；矩阵允许不同协议不同路径。

### 阶段 9：路线图与完整需求归位

**目标**：在当前真相稳定后，把旧 BACKLOG／ROADMAP 中所有仍有效的能力逐项归位，形成不会以成本理由静默砍功能的活路线图。

**产物**：最终版 `docs/ROADMAP.md` 与必要 topic specs。

**动作与验证**：

- 对旧 BACKLOG／ROADMAP 每一项建立 disposition：已实现、已决待实现、需用户重裁、被明确取代。不得出现“无去向”。
- Anthropic Messages 与 block-level buffering 排在首位；OpenAI Responses upstream 排第二。
- 热重载、History durability／API、upstream keepalive、stream consumers、cross-protocol translation、observability、冷归档、搜索、详细审计等能力保留明确 topic 与依赖。
- 只有既有明确用户裁决才能把能力标为拒绝；旧文档作者基于性能／复杂度的判断不能替代用户裁决。
- 逐项从旧源表与新路线图反向核对，保证双向集合相等。

**独立提交**：`docs: reconcile product roadmap without scope loss`

**风险与回滚**：本阶段不得顺手做产品范围裁决。遇到“旧文档写拒绝但找不到用户裁决”的项，标为“待重裁”，给选项与影响，交主会话处理。

### 阶段 10：开发资料归档与旧入口切换

**目标**：在新活文档全部可用后，最后迁移调研、完成态计划和旧源快照，移除 `docs/2604-rewrite/` 作为入口。

**动作**：

- 按第 4.2 节迁移 dependency-selection 调研；先复核当前依赖和日期，再更新 `research.md`。
- 按第 4.3 节归档旧实施计划、kick-off、handover 与评审。
- 将各超前旧主题文档移入对应 `archive-2026-08-06/`，补统一归档头：历史状态、为何取代、现行入口、基线 commit。
- 更新所有仓库内 Markdown 链接，不保留指向 `docs/2604-rewrite/` 或 `docs/tmp/` 的活链接。
- 删除已空的 `docs/2604-rewrite/` 目录；不删除任何尚未映射的源文件。
- `docs/tmp/live-doc-truth-audit.md` 与 `docs/tmp/docs-migration-plan.md` 继续留在本地且不提交。它们不是最终文档树的一部分，也不应被移动进 archive。

**验证**：

- 迁移前冻结集合与新位置／archive 的 disposition 一一对应。
- 仓库级 Markdown 链接检查全绿。
- 活文档不存在 `docs/2604-rewrite`、`docs/tmp`、旧 `[采纳]` 现在时或“默认零缓冲／块级延后”合同残留。
- archive 文件均有取代标记，README／ARCH／ROADMAP 不把 archive 当当前真相源。
- `git diff --name-only` 中不含 `docs/tmp/**`、`verification/**` 或其他基线前既有未跟踪内容。

**独立提交**：`docs: archive 2604 rewrite development artifacts`

**风险与回滚**：这是首次大规模移动，但发生在内容逐切片稳定之后，风险只剩链接与历史入口。使用 Git move 保留旧文件历史；若 final link gate 失败，不提交。提交后问题可整体 revert，不需要手工恢复文件。

### 阶段 11：合并态验证与文档定稿

**目标**：验证逐切片全绿没有掩盖文档之间的接缝错误。

**验证清单**：

1. 从空上下文沿 `docs/README.md` 依次完成三个任务：找到 Anthropic Messages 当前端点与缺口、找到 OpenAI Responses HTTP／WS upstream 路径、找到 buffering 已决合同与当前未接线状态。
2. 生成 route、settings、History schema、WS event 与生产调用矩阵，与活文档逐项对账。
3. 对活文档的每个“支持”“所有”“始终”“热生效”“异步不阻塞”等全称断言寻找反例路径。
4. 检查当前实现与已决目标是否在每篇文档中明确分栏，不依赖读者自行猜测时态。
5. 运行项目既有 Markdown／lint gate；若项目没有 Markdown gate，运行经过双向控制的临时 link checker。
6. 运行 Ruff、Pyright strict 与全量 pytest，目的不是证明 Markdown 正确，而是证明迁移没有误改产品文件、配置或测试；测试数只记录本次命令、commit 与路径口径，不复制旧 handover 数字。
7. 复核 `git status --short`、HEAD、分支、工作树与 `docs/ROADMAP.md`；逐条核验 pending／当前状态／下一步。
8. 独立评审需要同时查 false-green 和 false-red：错误状态能否混入活文档，以及正确的当前状态会不会被过严规则误判。评审发现逐条 disposition，修改后复评。

**独立提交**：若只修链接／措辞，用 `docs: finalize migrated documentation index`；若发现事实错误，回到拥有该主题的阶段做语义提交，不把多主题事实修复塞进一个“finalize”提交。

**回滚**：每个阶段均为独立 Conventional Commit。回滚按主题 revert，不使用整树 restore 覆盖共享工作树；若有并行工作，先保存 baseline diff 并只逆转本阶段精确 hunk。

## 7. 每个切片的统一执行 gate

每次 shell 调用都在同一调用内完成目录绑定与 HEAD 记录，不能依赖上一调用遗留 cwd。实施者应采用等价 gate：

1. `cd` 到绝对仓库根并验证 `pwd -P` 精确相等。
2. 打印 `git rev-parse HEAD`。首次实施确认规划基线是祖先；后续记录切片开始 HEAD，而不是错误地要求仍等于规划基线。
3. 打印 `git status --short`，确认既有脏项与本切片改动可区分。
4. 动作前执行该切片事实探针；动作后复跑同一探针和链接检查。
5. 提交前单独审核 `git diff --check`、`git diff --name-only` 与精确 pathspec；检查失败不得与 commit 放在无短路的同一批处理中。
6. 只提交本切片文件。`docs/tmp/**` 明确排除，且不得用 `git add docs` 这类宽 pathspec。
7. 提交后再次打印 HEAD 与 status，记录提交对应的验证命令和结果。

固定规划 HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d` 是迁移事实的起点，不是阻止后续语义提交推进 HEAD 的恒等 gate。

## 8. 门控问题与最小假设

### 8.1 不阻塞文档迁移、但阻塞 buffering 实现规格定稿的问题

用户已经决定 block-level buffering 与下游无 live streaming，但以下语义尚未由现有输入定稿：

- “block”的协议定义：Anthropic content block、Responses output item／content part、tool-call 参数块或统一内部块。
- block 内上游失败时是整块重取、整请求重试还是失败终止，以及如何证明不重复、不丢失、顺序不变。
- 已提交 block 与 History／usage／observer 的一致性时点。
- 单 block 大小上限、总内存预算、磁盘 spill、背压与并发配额。
- SSE／WS 取消、client disconnect、upstream reconnect 与 cleanup 的所有权。
- 下游虽无 live streaming 承诺，是否仍用 SSE／WS 作为分块传输 envelope，以及兼容客户端对事件序列的最低要求。

文档迁移的最小假设仅是记录已决高层合同与上述未决项，不选择具体答案。`docs/agents/buffering/spec.md` 未经架构裁决和验收 oracle 评审前，不得进入实现计划。

### 8.2 需要主会话重裁、不能由迁移者自行处理的问题

- 旧 BACKLOG／ROADMAP 中标为 `[拒绝]`、`[简化]` 或 `[缓存/延后]` 的能力，若找不到直接用户裁决，只能标记“待重裁”，不能据旧作者的成本判断继续拒绝。
- server-tool 当前有明确删除／不支持边界；若要重新引入，必须作为新规格重新裁决，不能借文档迁移恢复。
- 配置热重载、TCP keepalive、H2 PING、History durability／API 扩展和统一 translator 的具体架构，均不能由文档迁移计划替代产品／架构决策。

## 9. 未采纳路径

### 一次性 `git mv docs/2604-rewrite/* docs/`

未采纳。它会把审计已证伪的目标设计、当前实现和历史过程材料同时提升为活文档，并在一个提交中制造大量断链和事实冲突。

### 先全部归档，再从零写活文档

未采纳。它会在迁移窗口内失去可查的设计上下文，也容易漏掉旧 BACKLOG 中不能因 ROI／YAGNI 删除的能力。正确顺序是先建立可验证新入口，最后归档旧源。

### 按旧文件一对一改名

未采纳。旧 `DESIGN.md`、`streaming.md`、`history-system.md` 等同时包含当前事实、目标设计和历史取舍，一对一改名无法恢复真相层次。必须按主题拆分。

### 只修审计列出的句子，其余原样提升

未采纳。审计列出的是已发现的 blocker／major，不是完整正确性证明。每个候选活文档仍需从生产入口重建事实并做反例检查。

### 把所有未来能力留在一个 BACKLOG

未采纳。单一 backlog 会再次把优先级、架构问题、实现计划和被取代方案混为一体。未来能力应进入稳定 `docs/ROADMAP.md` 与具体 `docs/agents/<topic>/spec.md`，并保留依赖与验收意图。

## 10. 完成定义

迁移只有同时满足以下条件才算完成：

- `docs/README.md` 是唯一活文档入口，能清楚引导 Anthropic Messages、OpenAI Responses upstream、buffering 合同、API、配置与路线图。
- `docs/` 中所有支持结论可追到当前生产调用链或可执行探针；所有尚未实现的已决目标都明确标注并链接开发主题。
- block-level buffering 被写成基础产品合同，下游不承诺 live streaming；旧零缓冲／整响应 opt-in／块级延后方案只存在于带取代标记的 archive。
- Anthropic Messages 与 OpenAI Responses upstream 的优先级在 `docs/ROADMAP.md` 和开发主题中一致。
- 第 4 节列出的 42 份基线候选均有唯一 disposition，无遗失、无未标注重复、无活文档继续依赖旧目录。
- 所有已记录功能都有活路线图或 topic spec 去向，没有因成本、ROI 或 YAGNI 被静默砍掉。
- `docs/tmp/live-doc-truth-audit.md` 与 `docs/tmp/docs-migration-plan.md` 没有进入任何 Git 提交。
- 合并态链接、route、settings、schema、调用点、质量门和独立评审均通过；数字均带 commit／路径／命令口径并经不同原理交叉验证。

## 11. 实施 kick-off

请在 `/home/xp/src/ghc-api-proxy-py` 执行本计划，但先只实施“阶段 0：冻结清单与验证方法”和“阶段 1：Anthropic Messages 与 buffering 合同”，验证并形成独立提交后再继续下一阶段。每次 shell 调用必须在同一调用内绑定仓库绝对路径、验证 `pwd -P`、打印 HEAD 与 `git status --short`；规划基线为 `47d9ef101c4b81ac70d805b1da157b34d021d33d`，后续以每个切片开始 HEAD 记录推进。严格遵守文档结构：`docs/` 活文档、`docs/agents/<topic>/` 开发文档、`archive-2026-08-06/` 历史文档。先从生产 route／settings／schema／lifespan／调用点建立 oracle，再写文档并复跑同一 oracle；不得从 helper 存在推导生产支持。产品优先级固定为 Anthropic Messages → OpenAI Responses upstream；block-level buffering 是基础合同，下游不承诺 token／event 级 live streaming，但当前未接线必须明确标注。不得因成本、ROI 或 YAGNI 删除旧需求。每个切片只提交自身精确 pathspec，绝不提交 `docs/tmp/live-doc-truth-audit.md`、`docs/tmp/docs-migration-plan.md` 或既有 `verification/` 未跟踪项。遇到 buffering block 定义、重试／去重语义、预算与 envelope 等未裁决架构问题，只记录到 `docs/agents/buffering/spec.md` 的门控清单并交回主会话，不自行决定。

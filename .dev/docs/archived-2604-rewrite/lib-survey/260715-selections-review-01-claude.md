# 成熟库选型合并态评审 01

> 日期：2026-07-15
> 评审对象：[SELECTIONS](SELECTIONS.md)、[domain1](domain1-llm-sdk.md)～[domain6](domain6-hot-path-foundations.md)、[HANDOVER](HANDOVER.md) 及关联设计文档。

## Verdict

首轮结论为“无 blocker，修复 major 后可进入用户拍板与 planning”。共报告 3 个 major、8 个 minor、2 个建议。主会话没有直接采信评审结论，而是独立复核了 PyPI 元数据、项目模型目录和 feature-negotiation 键控原则后逐项处理。

## 已采纳

1. 修正 HANDOVER 中“litellm 新版已支持 Python 3.14”的错误陈述。当前 1.92.0 仍要求 `<3.14`；即使未来解除版本限制，调用框架与本项目 pipeline 架构不匹配仍是独立淘汰理由。
2. 将 `sse-starlette` 从“直接采用”移到“条件采用”，保真 PoC 是前置门禁。
3. 将 D5 明确标记为从域2未决分叉产生的“新设计提案”，不伪装成既有调研定论。
4. 同步域5“手写 metrics dict 已删除”的现状，避免报告继续把已采纳建议写成活跃问题。
5. 补充 tracing 关闭时日志 processor 省略 trace/span 字段的降级行为。
6. 将 Anthropic SDK 注入 `x-stainless-timeout` 的事实传递到总选型表。
7. 修正 HANDOVER “五域/六域”标题和历史说明。
8. 补充 AnyIO cancel scope 内不得遗失 `asyncio.create_task()` 子任务的约束和集成门禁。
9. 补充 JSON 微基准环境：CPython 3.14.2、JIT 关闭、Linux x86_64、AMD EPYC 7763、16 vCPU 配额。
10. 独立核验并补充 `uvloop`：0.22.1 有 CPython 3.14 wheels，最小运行通过；只作为 Linux/macOS 条件候选，必须以本项目 SSE/WS/cancel/shutdown 负载对 asyncio 3.14 做对照。
11. 精简 `aiofiles` 行，移除与 JSON codec 混杂的说明。

## 未原样采纳

1. **未把 token-limit key 直接改成仅 `model`。** 评审以 reasoning effort 的“模型固有属性”作类比，但 [feature-negotiation](../feature-negotiation.md) 同时明确指出 `base_url` 用于隔离个人/企业/Vertex 等不同账户路由，同名模型可能有不同支持边界；模型目录本身也是账户返回的数据。当前没有 ground truth 能证明 token limit 跨路由、跨 endpoint 恒定，因此保留 `(base_url, endpoint, model)` 为推荐提案，并把“仅 model”列作用户可选分叉。
2. **未拍定任意 tokenization offload 阈值。** 评审建议先给 10,000 tokens，但该数值没有项目 benchmark 支撑。继续要求实施阶段以目标硬件、并发度和事件循环延迟预算测定阈值，避免把猜测固化成规范。
3. **未将 `uvloopx` 纳入候选。** 未找到其为 uvloop 正式后继的权威依据；只核验并记录成熟的 `uvloop`。

## 追加发现

- `uvloop` 是原六域遗漏的成熟事件循环候选，已补入域6和总选型表。
- 模型目录已有 `max_prompt_tokens`，但错误驱动学习仍可能捕获比目录更具体的实际边界；D5 需要用户同时决定 TTL 和键作用域。

## 第二轮复审

修订后复审 verdict：**可进入用户拍板，无 blocker，无 major**。复审只发现 HANDOVER 与 SELECTIONS 的 5 项同步偏差，已全部处理：扩大 `httpx_ws` black-box PoC 范围并记录 `websockets` 退路；HANDOVER 补入 `orjson`/`tiktoken`；移除已收敛的 Typer 排期伪决策；待决策清单改为引用 SELECTIONS D1～D6；关键约束补入单一 retry owner。

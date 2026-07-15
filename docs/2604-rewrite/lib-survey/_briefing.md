# 库调研共享 Briefing（lib-survey）

> 本文件是所有 `domainN-*.md` 调研任务的共享背景。每个域 agent 先读本文件，全部照办，再做自己那一域。

## 任务缘起

用户诉求：**各个模块不要全部自研，系统性寻找成熟、活跃的现成库/工具替代手写实现**（`battle-tested-over-hand-rolled`）。本项目此前的设计文档倾向大量自研（累积器、限流器、TTL 缓存、SSE 构建、SQLite writer 等），需要逐模块审视「哪些能用现成库、哪些确实该保留自研」。

## 项目背景

`ghc-api-proxy-py`：Python 反向代理，对外暴露 OpenAI（Chat Completions / Responses / Embeddings）、Anthropic（Messages / Count Tokens）、Azure OpenAI、Google Gemini 兼容端点；默认上游 GitHub Copilot（GHC），也支持任意兼容服务。

- **技术栈**：Python **3.14**，FastAPI 0.129、uvicorn 0.40、httpx 0.28；已依赖 `openai==2.21.0`、`anthropic==0.79.0`、`opentelemetry-api==1.39.1`。用 `uv` 管理。
- **上游端点分流由数据驱动**：`refs/available_models.json` 每个模型带 `supported_endpoints`（如 Claude=`/v1/messages,/chat/completions`，gpt-5.5=`/responses,ws:/responses`，gemini=`/chat/completions`）。代理据此选上游端点。**这是已证实的事实，不要再质疑或 PoC。**
- **模块地图**：见 `docs/2604-rewrite/project-structure.md`（完整目录树 + 每模块职责）。**先读你那一域涉及的模块文档，理解设计意图再评估。**

## 硬约束（违反即淘汰候选库）

源自 `DESIGN.md` 性能设计原则，**优先于「功能对齐」和「省代码」**：

- **P1 — off-event-loop I/O**：历史/遥测/隔离等所有 SQLite/磁盘 I/O 一律不落在请求热路径（writer 任务 + `asyncio.Queue` 或线程池）。引入同步阻塞 I/O 到请求协程的库不可接受。
- **P6 — 流式零缓冲直通**：SSE 逐事件转发，默认不缓冲完整响应。任何**强制整体缓冲**上游流的库/用法不可接受。
- **保真度**：跨协议翻译（如 anthropic→responses）逐事件进行；同协议链路尽量原始字节直通。SSE 未知字段/未知块不能被库擅自吞掉或重编码破坏（尤其 thinking signature、server_tool 块）。
- 热路径操作应 O(1)、纯内存优先；重 CPU（压缩/哈希/全文索引）不进热路径。

## 调研纪律

- **不臆断**：不要凭记忆猜库的能力或版本号。查官方文档 / PyPI / 源码确认。可用 `uv pip index versions <pkg>` 或 WebFetch 查最新稳定版与维护状态。
- **成熟度信号**：每个候选库注明最新稳定版本、最近发布时间、维护活跃度、大致采用度（星标/下载量量级）、是否有 type hints、是否 async 原生、许可证。
- **别为省事牺牲功能/保真/性能**：不采用 YAGNI/ROI 口径砍需求。若某自研点确实无合适库、或现成库会违反硬约束，明确写「保留自研」并给理由——这本身是有价值的结论。
- **区分「替换传输/机制」与「借用类型/工具函数」**：有的库只值得借它的类型或某个纯函数，不值得让它接管控制流。分开评估。
- **Python 3.14 兼容性**：留意候选库是否已支持 3.14（有的 C 扩展可能滞后）。不确定就标注为待验证。

## 产出格式

写到 `docs/2604-rewrite/lib-survey/domainN-<slug>.md`，结构：

```
# 域N：<领域名>

## 概览结论表
| 自研点(模块/文件) | 候选库 | 匹配度 | 威胁硬约束? | 推荐 | 理由 |

## 逐项详述
### <自研点>
- 现状（读文档后的意图概括 + 引用 project-structure/相关 doc 行）
- 候选库：版本/维护/async/类型/许可 + 能力核对
- 是否威胁 P1/P6/保真度
- 推荐：替换 / 部分替换（借类型或子功能）/ 保留自研 + 理由

## 遗留疑问 / 需主会话或用户裁决的点
```

结论要可被主会话直接汇总进选型表，并交给 reviewer 对抗评审。

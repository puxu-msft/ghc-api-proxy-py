# 候选：`MAIN.md` 未描述的其余模块

> 本文是候选素材，无效力。每项一行，供用户决定是否需要在自己的文档里给它一个位置。
>
> 列出**不等于**建议改动。它们都是已实现且在生产路径上（除标注外）。

## 请求处理路径上的包

| 包 | 现状职责 | `MAIN.md` 中的位置 |
|----|---------|-------------------|
| `anthropic/` | Anthropic 深度兼容：两阶段 sanitize、thinking 全套（块级保护 / destack / L2 剥离 / L3 内存隔离 / signature 兼容 / reasoning carrier）、特性协商与缓存、client tool 预处理、请求响应头策略、warmup、请求准备编排 | 未提；`app.pipeline` 的「转变」应涵盖 |
| `openai/` | OpenAI 侧客户端、Responses 转换、流式解析器与累积器、sanitize | 未提；同上 |
| `protocols/` | 协议对之间的转换：`anthropic_responses`、`responses_anthropic`、`azure`、`gemini` | 未提；对应 `translation_driver` 的翻译器 |
| `transform/` | 模型名解析（别名 / 标准化 / override / family）、系统提示词定制、跨协议非流式翻译 | 模型映射在 `MAIN.md` 路由一节被举例提到，模块归属未写 |
| `delivery/` | 块级交付：Anthropic SSE 渲染、单一 sink、交付前沿、常驻字节预留 | 未提；承载「块级缓冲」裁决 |
| `streaming/` | SSE 编解码、keepalive、空闲超时、延迟首帧、有界缓冲重试、usage 提取 | 未提 |
| `context/` | 请求生命周期事件总线、off-loop 原子错误持久化 | 未提；与 `MAIN.md` 的事件订阅**高度相关** |
| `hooks/` | 四类 typed 扩展契约、启动期不可变 registry、可信 loader、三个内置实现 | 用户已裁决由事件订阅吸收，见 `pipeline-subscriptions.md` |
| `models/` | 四协议的 wire 模型与能力元数据 | 未提 |
| `upstream/` | 上游抽象（`UpstreamTarget`）、SDK 客户端构造、模型目录、generic 上游、Copilot 适配 | 部分被 `app.ghc_client` 覆盖；抽象层与 generic 路径未提 |

## 支撑设施

| 包 / 模块 | 现状职责 | `MAIN.md` 中的位置 |
|----------|---------|-------------------|
| `config/` | 四层配置合并（defaults < YAML < env < CLI）、跨平台路径、兼容映射 | 未提 |
| `auth/` | GitHub token 来源链（CLI / 环境变量 / 文件）与 device 认证服务 | device flow 已按 `MAIN.md` 移入 `ghc_client`；来源链留在此处 |
| `history/` | 单 writer off-loop SQLite、会话、在途请求、WebSocket 推送 | 端点在运维一节列了，模块归属未写 |
| `tokenization/` | 估算器、按规模学习的校准、prompt limit 观测、不可变快照与状态持久化 | 端点在运维一节列了，模块归属未写 |
| `observability/` | 结构化日志、OTel tracing 与 metrics、Prometheus reader、Textual TUI | `/metrics` 在运维一节列了，模块归属未写 |
| `errors.py` | 错误分类、wire format 检测、错误响应格式化 | 未提 |
| `wire_json.py` | 集中式 orjson wire codec | 未提 |
| `repetition_detector.py` | KMP 重复片段检测 | 未提 |
| `cli.py` / `deps.py` / `runtime.py` | Typer 入口、FastAPI 依赖提供者、每应用运行时状态 | 未提 |

## 已实现但当前无生产消费者

以下模块在 `src/` 中没有任何生产代码 import（可用 `rg -l 'app\.<模块名>' src` 逐个复算），仅被各自的测试引用。

**列出不构成删除建议**——它们可能是待接线、已被取代、或有意保留。用户已明确：允许存在无生产消费者的模块。

`shutdown.py`、`pipeline/manager.py`、`context/error_persistence.py`、`repetition_detector.py`、`streaming/delayed_commit.py`、`streaming/buffered_retry.py`、`streaming/translator.py`、`transform/translator.py`、`transform/system_prompt.py`、`anthropic/feature_negotiation.py`、`anthropic/sanitize/deduplicate_tool_calls.py`、`anthropic/thinking/signature_compat.py`、`openai/stream_accumulator.py`、`openai/responses_stream_accumulator.py`、`observability/tui.py`、`history/sessions.py`

其中三项与 `MAIN.md` 的设计直接相关，值得优先给出归属：

- `transform/translator.py` 与 `streaming/translator.py` —— 现有的跨协议翻译实现，与 `MAIN.md` 的 `translation_driver` 是同一件事的两代形态。
- `context/error_persistence.py` —— 与 `MAIN.md` 的事件订阅同属请求生命周期设施。

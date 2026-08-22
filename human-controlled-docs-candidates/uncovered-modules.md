# 候选：用户文档未描述的其余模块

> 本文是候选素材，无效力。每项一行，供用户决定是否需要在自己的文档里给它一个位置。
>
> 列出**不等于**建议改动。它们都是已实现的（生产路径上与否见各表标注）。

**2026-08-22 重写。** 原文通篇以 `docs/.human-controlled/MAIN.md` 为对照列，而该文件已在提交 `2afa0c4` 里被拆成 `module-org.md` / `api.md` / `request-pipeline.md` / `message-translation.md` 等多份，`MAIN.md` 本身不复存在。本次把对照基准换成拆分后的这几份，并按用户 2026-08-22 的追认结果重算了每一行。对账依据：`.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md`。

**本文的对照基准**：`docs/.human-controlled/module-org.md`（模块层次的唯一权威清单）；端点归属另见 `api.md`；管线与事件订阅另见 `request-pipeline.md`；翻译器另见 `message-translation.md`；GHC 客户端与其 `auth` 子模块另见 `ghc-api.md`。

## 已被采纳的部分（2026-08-22）

用户在 `module-org.md` 的「得到用户追认的模块」清单里给了以下几项位置，本文相应的行**已撤下**：

| 原候选行 | 落点 |
|---|---|
| `config/` | `module-org.md:10` |
| `history/` | `module-org.md:12` |
| `observability/` | `module-org.md:17` |
| `cli.py` | `module-org.md:7-9`（并细分了 `debug` / `start` 两个子命令） |
| 块级交付 | `module-org.md:18-19` 的 `pipeline.delivery`。**注意所指与本文原来那一行不是同一个包**，见下方「`delivery/`：被追认的不是这一个」 |

## 请求处理路径上的包

| 包 | 现状职责 | 用户文档中的位置 |
|----|---------|-----------------|
| `anthropic/` | Anthropic 深度兼容：两阶段 sanitize、thinking 全套（块级保护 / destack / L2 剥离 / L3 内存隔离 / signature 兼容 / reasoning carrier）、特性协商与缓存、client tool 预处理、请求响应头策略、warmup、请求准备编排 | **已列入 `module-org.md:24-31` 的「尚未确认、有疑虑」栏**，等用户处置 |
| `openai/` | OpenAI 侧客户端、Responses 转换、流式解析器与累积器、sanitize | 同上 |
| `context/` | 请求生命周期事件总线、off-loop 原子错误持久化 | 同上；与 `request-pipeline.md:17` 的事件订阅**高度相关** |
| `protocols/` | 协议对之间的转换：`anthropic_responses`、`responses_anthropic`、`azure`、`gemini` | 未提；与 `message-translation.md:5` 的 `translation_driver` 翻译器是同一件事的两代形态 |
| `transform/` | 模型名解析（别名 / 标准化 / override / family）、系统提示词定制、跨协议非流式翻译 | 模型映射在 `request-pipeline.md:7-11` 的路由判定里被举例说明，模块归属未写 |
| `delivery/`（顶层 legacy） | 块级交付的**上一代**实现：Anthropic SSE 渲染、单一 sink | 未提。见下节 |
| `streaming/` | SSE 编解码、keepalive、空闲超时、延迟首帧、有界缓冲重试、usage 提取 | 未提 |
| `hooks/` | 四类 typed 扩展契约、启动期不可变 registry、可信 loader、三个内置实现 | 用户已裁决由事件订阅吸收，见 [pipeline-subscriptions.md](pipeline-subscriptions.md) |
| `models/` | 四协议的 wire 模型与能力元数据 | 未提 |
| `upstream/` | 上游抽象（`UpstreamTarget`）、SDK 客户端构造、模型目录、generic 上游、Copilot 适配 | 部分被 `module-org.md:15-16` 的 `app.model_provider` 覆盖；抽象层与 generic 路径未提 |

### `delivery/`：被追认的不是这一个

`module-org.md:18-19` 追认的是 `app.pipeline.delivery`——即 `src/app/pipeline/delivery/`（新链，`assembling.py`、`blocks.py`、`framing.py`、`sse_frame.py`、`sse_source.py`、`stream.py` 加 `formats/`）。

同时仍存在顶层的 `src/app/delivery/`（`anthropic_sse.py`、`responses_anthropic_stream.py`），它只被 `src/app/routes/anthropic.py` 引用，而 `routes/` 属于旧链 `create_app`——旧链已无生产入口（见 [rolling-removal.md](rolling-removal.md) 第六节）。

复算：`rg -n 'app\.delivery' src --glob '*.py'` 命中三处，两处是该包内部自引，第三处是 `src/app/routes/anthropic.py:12`。

所以「块级交付在模块图里有位置了」这件事已经完成，**顶层 legacy `delivery/` 仍无位置**——它与 `transform/translator.py`、`streaming/translator.py` 属于同一类：同一件事的上一代形态，随旧链一并退役才是自然的归宿。是否需要在文档里为它单列一行，取决于用户是否希望文档记录「有一份尚未退役的旧实现」。

### 关于三个「有疑虑」的包，本文不再给归属建议

原文对 `anthropic/`、`openai/`、`context/` 建议「归入 `app.pipeline` 的『转变』一节」。用户 2026-08-22 的处置是把这三个包放进 `module-org.md:24-31` 的**待处置队列**，而不是并进 `pipeline`。继续建议「应由 `app.pipeline` 涵盖」等于替用户把一个他已经挂起的问题答掉，因此该建议已撤下，本文只保留职责陈述。

## 支撑设施

| 包 / 模块 | 现状职责 | 用户文档中的位置 |
|----------|---------|-----------------|
| `auth/`（顶层残留部分） | GitHub token 的**来源链**（CLI / 环境变量 / 文件） | device flow 与 github_token → copilot_token 交换已按 `module-org.md:35` 移入 `app.model_provider.ghc_client.auth`，并写进 `ghc-api.md:5-8`；**来源链那一半仍无位置**。它与 [config-migration-gaps.md](config-migration-gaps.md) 第二节「token 来源」是同一件事的两面（一面是模块归属，一面是配置承载），宜一并裁决 |
| `tokenization/` | 估算器、按规模学习的校准、prompt limit 观测、不可变快照与状态持久化 | 端点已在 `api.md:21` 标注「暂不支持」，模块归属未写 |
| `errors.py` | 错误分类、wire format 检测、错误响应格式化 | 未提 |
| `wire_json.py` | 集中式 orjson wire codec | 未提 |
| `repetition_detector.py` | KMP 重复片段检测 | 未提 |
| `deps.py` / `runtime.py` | FastAPI 依赖提供者、每应用运行时状态 | 未提 |
| `graceful_timeout.py` | 三个写死的退出时限常量；公式已被 `lifecycle.md:57-59` 推翻 | 未提，见 [existing-rulings.md](existing-rulings.md) C-1 |
| `core/` | generation id 与 release id 的解析 | `module-org.md:11` 已追认 `core`；`lifecycle.md:3` 说明了它为什么跨域 |

## 已实现但当前无生产消费者

**2026-08-22 重算。** 判据：该模块的 dotted 路径或相对 import 在 `src/` 中除自身外无命中。复算方式（对某一项 `<pkg>/<mod>`）：

```bash
cd /home/xp/src/ghc-api-proxy-py
rg -l -e 'app\.<pkg>\.<mod>' -e 'from \.<mod> import' -e 'from \.\.<mod> import' src --glob '*.py'
```

注意只按名字做子串匹配会大量误报（`translator`、`manager`、`shutdown`、`sessions` 都是常用词，各自能在十来个无关文件里命中），本次复算已排除这类噪声。

**列出不构成删除建议**——它们可能是待接线、已被取代、或有意保留。用户已明确：允许存在无生产消费者的模块。

`shutdown.py`、`pipeline/manager.py`、`context/error_persistence.py`、`repetition_detector.py`、`streaming/delayed_commit.py`、`streaming/buffered_retry.py`、`streaming/translator.py`、`transform/translator.py`、`transform/system_prompt.py`、`anthropic/feature_negotiation.py`、`anthropic/sanitize/deduplicate_tool_calls.py`、`anthropic/thinking/signature_compat.py`、`openai/stream_accumulator.py`、`openai/responses_stream_accumulator.py`、`history/sessions.py`

本次重算相对上一版的差异：

- **`observability/tui.py` 已移出该清单**——它现在有生产消费者：`src/app/server/pipeline_app.py:38` 导入 `footer_tui_or_none`，`:1026` 调用它。
- `graceful_timeout.py` 一度被考虑补入，复算后**不成立**：`src/app/config/settings.py:8` 导入了它的 `DEFAULT_GRACEFUL_TIMEOUT_SECONDS`。它是「有消费者但公式已被推翻」，不是「无消费者」，见上表。
- 其余 15 项复算后仍成立。

**这份清单的范围要说清楚**：本次做的是**对上一版那 16 项逐个复算**（其中 1 项移出、15 项留下），不是对 `src/app/**` 的全量重扫。所以它保证「列出的都确实没有生产消费者」，**不保证「没列出的都有」**。已知至少还有两个同样无生产消费者的模块没进这张表——`lifecycle/systemd/notify.py` 与 `lifecycle/systemd/systemctl.py`，它们是 rolling 删除后留下的（见 [deployment.md](deployment.md)）。要一份完整清单需要另做一次全量扫描，本次未做。

其中三项与用户文档的设计直接相关，值得优先给出归属：

- `transform/translator.py` 与 `streaming/translator.py` —— 现有的跨协议翻译实现，与 `message-translation.md:5` 的 `translation_driver` 是同一件事的两代形态。
- `context/error_persistence.py` —— 与 `request-pipeline.md:17` 的事件订阅同属请求生命周期设施。

# 候选：请求上下文的事件订阅如何吸收现有 hooks

> 本文是候选素材，无效力。**现状**标注的是代码中已成立的事实；**提案**是模型建议，可整段丢弃。
>
> 方向已由用户裁决：**订阅机制吸收 hooks**。本文只处理「怎么吸收」，不重开「要不要吸收」。
>
> **2026-08-22 重指**：原文以 `MAIN.md` 为出处，该文件已拆分，对应内容现在 `docs/.human-controlled/request-pipeline.md:15-19`。原标题写的 `RequestContext` 也换成中性说法，原因见下方「一处命名不一致」。

## 用户文档已写下的要求（原文，`request-pipeline.md:16-17`）

> 1. 提供统一的上下文对象模型，而不是在各个管道间做数据模型转换。每个客户端请求都由一个 ClientRequest 描述，每次上游尝试都由一个 UpstreamAttempt 描述。
> 2. 可扩展点以事件订阅的形式提供，允许功能模块订阅（传入唯一 id 和可选的“插入到谁之前/后”）。订阅者能够修改上下文对象，也可以通过抛出不同的异常来触发中止/重试。

### 一处命名不一致（2026-08-22 新发现，值得单独提给用户）

用户文档 `request-pipeline.md:16` 现在把两个上下文对象命名为 **`ClientRequest`** 与 **`UpstreamAttempt`**；代码里对应的类是 `src/app/pipeline/context.py:70` 的 `RequestContext` 与 `:37` 的 `Attempt`。

这不是冲突——文档写的是概念，代码写的是类名——但两处名字不同，后续讨论容易各说各话。两条出路，交用户决定：**（甲）** 认定文档名即目标名，代码按它改名；**（乙）** 认定这只是概念称呼，代码名不动，但在文档或代码注释里点明对应关系。本文其余部分沿用代码里的名字，以免与可复算的位置对不上。

## 现有 hooks 的形态（现状）

`src/app/hooks/` 提供四类 typed 契约，启动期构建不可变 registry，模块由可信 loader 加载：

| 契约 | 作用 | 现有阶段 |
|------|------|----------|
| `PayloadHook` | 修改出站请求体 | `POST_SANITIZE`、`PRE_SEND` |
| `ResponseHook` | 处理入站响应 | 响应到达后 |
| `RetryStrategyFactory` | 产出重试决策 | 失败后 |
| `ObserverHook` | 只读观察，不改状态 | `POST_SANITIZE`、`PRE_SEND` 等 |

配套：`HookErrorMode`（单个 hook 失败时是中止还是跳过）、三个内置实现（`payload`、`retry`、`token_calibration`）。调用点在 `src/app/pipeline/executor.py`。

## 两者的差距（现状对比）

| 维度 | 现有 hooks | 用户文档的订阅（`request-pipeline.md:17`） |
|------|-----------|-----------------|
| 定位方式 | 按固定阶段枚举分类 | 按事件订阅，带唯一 id |
| 顺序 | 注册顺序，调用方不可控 | **可指定「插入到谁之前/后」** |
| 中止与重试 | `RetryStrategyFactory` 返回决策对象；`HookErrorMode` 决定失败处置 | **订阅者抛不同异常来触发** |
| 可改范围 | 按契约限定（payload hook 只改 payload） | 「能够修改上下文对象」 |

差距原本集中在两点：**有序插入**与**以异常表达控制流**。**两者现在都已建成**，见下节；尚未发生的是**吸收**——旧 `src/app/hooks/` 仍与新机制并存，没有一个内置 hook 迁过去。

> **2026-08-22 更新（现状，非提案）：订阅者已增至三个。** `src/app/pipeline/subscribers/` 现有 `server_tools.py`（`builtin:server-tool-capability`）、`hosted_web_search.py`（`builtin:hosted-web-search-gate`）、`blank_text.py`（`builtin:blank-text-blocks`），另有一个 `counting.py`——它不是订阅者，是三者共读的 `extras` 载体。三个都挂在 `attempt.prepare` 上，注册顺序与各自的理由写在 `src/app/pipeline/subscribers/__init__.py:13-15` 的表里，由 `src/app/server/composition.py:530` 的 `register_builtin_subscribers()` 在 `build_chain` 内注册，所有调用点无一改动。
>
> 需要说清楚的是：**这三个都是新增能力，不是从 `src/app/hooks/` 迁过来的 hook**，所以本文所说的「吸收尚未发生」仍然成立——三个内置 hook（`payload`、`retry`、`token_calibration`，都在 `src/app/hooks/builtin/`）一个都还没动。
>
> 它顺带回答了本文第 3 个待决点的一半：内置订阅者**目前没有配置面**，因为协议兼容性修复属于不可禁用的 mandatory sanitizer。`hooks:` 六个运维订阅点的列表项语义仍未定义，配置面等那道裁决。
>
> 相关：[hooks-system.md § 事件订阅](../docs/archived-2604-rewrite/hooks-system.md)、[tool-use.md](../docs/archived-2604-rewrite/tool-use.md)、开发文档 `.dev/docs/hosted-web-search/reports/260820-websearch-fix-v2-design.md`。（三条路径均于 2026-08-22 重指：前两条随 `2604-rewrite/` 迁入 `.dev/docs/archived-2604-rewrite/`，第三条随 `docs/tmp/` 迁入 `.dev/docs/`。**注意前两条所在目录已被用户于 2026-08-20 整体判为过期的 `copilot-api-js` 学习笔记**，引用前先判断其结论还成不成立。）

## 已建成的部分（现状）

| 能力 | 实现 | 说明 |
|------|------|------|
| 唯一 id ＋ before/after 拓扑排序 | `src/app/pipeline/events.py` 的 `SubscriberRegistry.freeze()` | 顺序在 freeze 时解析一次并固化；重复 id、引用不存在的 id、成环都在 freeze 时失败。同序并列时按注册顺序决定，结果是确定的而不只是合法的 |
| 以异常表达控制流，且异常是闭集 | `src/app/pipeline/exceptions.py` | 闭集为 `UpstreamError`、`UpstreamTimeout`、`UpstreamRateLimit`、`PipelineRetry`、`PipelineAbort`；`classify()` 对闭集外的一切返回 ABORT |
| 按固化顺序投递 | `src/app/pipeline/direct_driver/base.py` 的 `_publish` | 事件名由发布它的驱动拥有：`attempt.*` 与 `request.*` |

注意：`config.example.yaml:420-437` 的 `hooks` 一节另给了六个**面向运维**的订阅点（`on_client_request_parsed` 等），与上面驱动内部的 `attempt.*` / `request.*` 不是同一层。列表项的语义规格未定义，见 [config-migration-gaps.md](config-migration-gaps.md) 第二节。

## 提案：尚未落地的吸收路径

> 以下是模型建议。

### 1. 事件点取自现有阶段，不新造词汇

现有的 `POST_SANITIZE` / `PRE_SEND` 已经是被 hook 消费的真实接缝，直接升格为订阅事件点，另补响应侧与终态侧。四类契约不再是并列的分类，而都成为**订阅者**，靠订阅的事件点区分。

### 2. 「修改上下文对象」需要一条写入规则

`request-pipeline.md:17` 允许订阅者修改上下文对象。建议补一条：**同一字段的写入者唯一**，或明确「后写覆盖先写」。

理由：现状里 `RequestContext` 已经是 21 字段的可变 dataclass（`src/app/pipeline/context.py:70`，2026-08-22 复算；原文写 20，当时如此），多方写入且无所有权声明；开放订阅会放大这一点。这条规则不改变用户文档的意图，只是把「谁能改什么」写明。

**一个佐证已经出现**：新加的 `counting.py` 之所以把共用事实放进 `extras` 而不是加进 `RequestContext`，其模块 docstring 给的理由正是所有权——「它不属于其中任何一个订阅者，从同伴那里 import 会让那个同伴看起来像它的所有者」。所有权问题在实践中已经被绕着走了一次，写明规则不是空谈。

### 3. 现有三个内置 hook 的归宿

`payload`、`retry`、`token_calibration`（`src/app/hooks/builtin/`）改造成订阅者后行为不变，可作为吸收路径的**首批验证样本**——它们分别覆盖改请求体、产出重试决策、只读观察三类形态。

## 需要用户决定的剩余点

> 2026-08-22 复核：以下三条全部仍然打开，用户文档未就任一条表态。

1. 「修改上下文对象」的写入规则取哪一种（唯一写者 / 后写覆盖 / 其它）。`request-pipeline.md:17` 至今只写「订阅者能够修改上下文对象」。
2. 现有 `HookErrorMode`（`src/app/hooks/types.py:18`）的语义是保留还是并入异常体系——具体问法是：它与 `request-pipeline.md:19` 的「未知异常总是中止」是否重复？若重复，`HookErrorMode` 可退役。
3. `config.example.yaml:420-437` 的 `hooks` 六个订阅点，列表项指什么（模块路径？订阅者 id？），以及是否需要单 hook 超时。
4. **（2026-08-22 新增）** `ClientRequest` / `UpstreamAttempt` 这两个文档里的名字与代码里的 `RequestContext` / `Attempt` 不一致，是否要求代码改名。见本文开头「一处命名不一致」。

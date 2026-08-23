# 实施计划评审：处置

**这份是处置记录**。评审原件不改：[260823-plan-review.md](260823-plan-review.md)。计划已改写到 v2，Spec 有一处冻结后修订。

**一句话**：4 条 blocker、10 条 major、1 条 minor，**15 条全部采纳**，无驳回。v1 的切片划分（S0～S6）整体作废——它的 S1、S2、S6 都不是自洽的语义单位。

## 四条 blocker

### F-01　三件套 + `JSONResponse` 表达不了字节透传

`error_status` / `error_body` / `error_headers` 的调用点都把结果交给 `JSONResponse`，而它的输入是待序列化对象、且自己决定 Content-Type。Spec §3.1 要的是任意 body 字节 + 原 status + 过滤后的原头 + 原 Content-Type。**这不是实现细节，是当前 API 形状表达不了目标。**

处置：收敛为一个工厂 `error_response(source, *, inbound_format, translated) -> Response`，三个调用点同片改接。直连分支返回 `Response(content=body_bytes, ...)`，其余分支才 `JSONResponse`。

### F-02　`describe(error)` 在 pipeline 层覆盖不了 Spec §5.1

三类来源没有异常对象可传（请求体非 JSON、顶层非对象、`route.implemented=False`），而 `InboundRequestError` 定义在 `app.server.inbound`——pipeline 侧的 classifier 为认识它而 import server，就造出了计划本想避免的反向边。

处置：**分成两个 classifier，各自放在它的输入所在的那一侧**。pipeline 侧认 `app.pipeline.exceptions` 与 `app.model_provider.types`；server 独有的来源由边缘自建 `ErrorInfo`。工厂接受 `BaseException | ErrorInfo`。不搬 `InboundRequestError`。

### F-03　R 片（原 S5）没有失败事件的数据通道，也没有直连／翻译的选择点

`BlockAssembler.push()` 只返回 `tuple[CompletedBlock, ...]`；两个 assembler 遇到失败事件都是记日志返回空；`stream_delivery` 拿不到 `translation_required`。而**同一个 `ResponsesAssembler` 同时服务 Responses 直连与 Responses→Anthropic 翻译**，所以从 assembler 类型推不出该走哪条；从 framer 类型反推又会把 generic delivery 绑到具体格式。

处置：先定义 format-neutral 的 `StreamFailure(source_event, source_data, info)` 与显式失败通道；策略由 `inference.py` 依据已知的 `route.translation_required` 传入；`stream.py` 只消费策略与 typed result，不 `isinstance` 具体 assembler/framer。

### F-04　冻结的 Spec 自己漏了一格

`EndpointNotSupported` 已被实测证明可达（`POST /v1/messages` 请求 `claude-model@openai-responses` → 400，上游请求数 0），而 §5.1 的「完整清单」没有它。我方独立复现，并进一步发现 `ProviderError` 是**五个子类的家族**，Spec 只列了两个。

处置：按评审共识修订冻结 Spec（记在 Spec 头部的「冻结后的修订」表）。五个子类各有一行：`UnknownModel → NOT_FOUND/404`、`CapabilityMissing → CLIENT/400`、`EndpointNotSupported → CLIENT/400`、`EndpointNotImplemented → NOT_IMPLEMENTED/501`（它的 docstring 明写「本代理没有驱动它」）、`ProviderNotConfigured → INTERNAL/500`。基类与未列出的子类**保持今天的 400**，不猜——为一个尚不存在的失败改变客户端动作比留着现状更糟；另要求一条测试钉住子类集合，新增子类必须显式分类。

**为什么这不需要用户再裁一次**：改的是我推导出的映射表，不是用户裁定的那两条原则。

## 十条 major 与一条 minor

| 编号 | 内容 | 处置 |
|---|---|---|
| F-05 | `ErrorInfo.conversion` 若在 `app.errors` 里 `default_factory=Conversion`，叶子立刻反向依赖 `translation_driver` | 采纳。`TYPE_CHECKING` 引用 + 必传字段，由 classifier 创建后传入。I 片的 module-boundary 断言要证明新解释器导入 `app.errors` 仍只加载它自己 |
| F-06 | 枚举扩容早于以它为键的表，会开出 `KeyError` 窗口（`ApiError(category=NOT_FOUND).wire_type`）——**可观测回退，不是死代码** | 采纳。I 片一次做完：扩枚举与换表同提交，测试断言 `set(每张表) == set(ErrorCategory)` |
| F-07 | S2「纯新增」不成立（要改 `error_frame`），且多数 writer 在该提交态是测试专用死代码；验收矩阵还要求已推迟的 carrier | 采纳。**按首个生产消费者切 writer**：JSON writers 随 J 片、流式 writers 随 F 片、Gemini writer 随 Gemini 501 接线。验收矩阵改成 Spec §6.3 明列的合法 carrier 集，推迟／未实现的格显式标 N/A |
| F-08 | S3 必然实施 S6 的两项状态变更（接了 `describe` 就发生），S6 不是独立单元且**完全没有验收段** | 采纳。`UnknownModel`／`TranslatorNotFound` 归 J 片；count_tokens 与「200 非 JSON」各自独立成片（C、N），都补验收 |
| F-09 | 三组规范只有 writer／章节引用，没有生产接线：早期 return 绕过 `http_errors`、Gemini 501 不调 writer、`x-should-retry` 没有所有者 | 采纳。J 片列全并改接所有早期 return；Gemini 501 必须有真实 endpoint 测试；`x-should-retry` 的唯一生产者写死为 HTTP 边缘，且**直连上游错误不得覆盖上游原头** |
| F-10 | Spec §10.2 指定的 deferred 台账不存在，计划也没有创建步骤 | 采纳。新增 **D 片，排在第一个实施提交之前**；台账已建，收 §10.2 与 §11 全部条目 |
| F-11 | 「从表结构生成每行断言」若用生产表生成 expected，就是同源恒真 oracle | 采纳。**这是我写的一句错话**：我以为它避免了手抄漏项，实际是取消了独立 oracle——删一行则参数数也少一行，写错值则 expected 同时变错。改为测试侧手工转录 + 独立字面量 `EXPECTED_CASE_IDS` |
| F-12 | J 片验收分不出「真透传」与「解析后重新序列化成相同 JSON」，且完全没验 headers 与 Content-Type | 采纳。直连样本改用 `b"\xffraw-body"` 或带 BOM 的字节（普通 JSON 样本不行）；同一响应带上应保留与应剔除的头各若干，逐个断言；变异「改走 writer」「忽略 `translated` 参数」都必须红 |
| F-13 | union 守卫是子集检查，缺一行真空通过；且不证明生产 SSE 用了新表 | 采纳。同时断言 `set(mapping) == set(ErrorCategory)` 与 `set(values) <= sdk_union`；union 从 `anthropic.types.shared.error_type.ErrorType` 取而**不扫目录做正则**；行为部分从真实入口触发三种失败 |
| F-14 | R 片验收可由「认出 Anthropic `event:error` 就原样吐回」一条特判满足 | 采纳。四组真实入口断言（直连 Anthropic 保留未知字段、Responses 两种 event 名不得统一改名、翻译已知 code、翻译未知 code 走 `upstream_error`），每组都断言之后没有正常 terminal；另比较同一失败在响应头前／后的语义投影 |
| F-15 [minor] | 「`ErrorInfo`（9 个字段）」按字段名实际是 10 个 | 采纳。计划直接列出 10 个字段名 |

## 评审确认、我保留的判断

- **分层大方向成立**。评审用 AST + 运行时探针实测：`app/errors.py` 确实是零 `app.*` import 的叶子；全 `src/app` 静态图强连通分量为 0；当前没有任何在用 `app.pipeline.*` 导入 `app.server.*`。`http_errors -> formats.* -> app.errors` 是 server 向内的正常依赖。
- **但「既有测试仍绿」不能证明新落点成立**——评审实测 `test_module_boundaries.py` 的四条断言看不见「`app.errors` 失去叶子地位」「pipeline 新增 server 反向边」「generic stream 直接认识 format」这三件事。所以要新增断言，不是靠现有的绿。
- **S0 可以独立**，评审判定无需重做。

## 一条方法上的记录

评审在报告开头写明：评审开始时那两个文件还没出现在 `git status`，评审期间变为修改状态——那是我在并发实施 S0。它据此声明「不评 S0 实现质量，只按读取时的结构判断计划」。这个处理是对的，也是共享主树上评审必须做的声明。

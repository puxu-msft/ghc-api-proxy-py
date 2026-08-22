# `app.server` 模块布局：现状分析与目标设计（第二版）

**日期**：2026-08-22。**基线**：主仓 `main` = `1f29d0a`（数字快照时点），`.dev` = `58663b5` 之后。
**第二版**：初版经两轮独立评审（事实核查 0 blocker／3 major，设计评审 2 blocker／6 major）后重写。逐条处置见 [处置表](reports/260822-layout-proposal-disposition.md)。**初版第 5 节六个落点里两个是错的**，本版已改。
**性质**：分析与提案，不是裁决。第 9 节列出**三个**必须由用户裁决的分叉。

**支撑报告**（原始记录，不回填）：[链路可达性](reports/260822-server-layout-chain-map.md)、[既有结论与权威分级](reports/260822-server-layout-prior-art.md)、[事实核查](reports/260822-review-layout-proposal-facts.md)、[设计评审](reports/260822-review-layout-proposal-design.md)、[架构约束补读](reports/260822-architecture-constraints-readthrough.md)

---

## 1. 结论摘要

`app/server/` 八个模块里只有三个真属于它自称的「入站 HTTP 表面」。另外四个的错位都有不依赖口味的判据：`tls.py` 包内零消费者、`composition.py` 被包外的 `cli`／`debug` 消费、`handler.py` 干的是用户追认文档指派给 `app.pipeline` 的活、`app_factory.py` 生产零导入者。第九处在 `pipeline_app.py` 内部：1037 行里约 330 行是可观测性代码，`_dispatch` 单个函数 418 行。

**根因三条，全在 `app/server` 外面**：组装根放在 HTTP 包里、追认的 `server/routes` 从未存在而名字被未追认的顶层 `app/routes/` 占着、旧链整体不可达却持有若干已追认端点的唯一实现。

**初版最大的错误**：它在搬文件，却没有动函数签名。`Chain` 照样穿过每一条新划的包边界，于是每次搬迁都把组装根拖进一个叶子——两个 blocker 都由此而来。本版的第一步因此改成**先收窄依赖，再搬文件**。

---

## 2. 权威边界：谁能裁决什么

**先读这一节再读方案。** 初版这一节漏了一道门，已补。

| 来源 | 地位 | 对本主题的约束 |
|---|---|---|
| `docs/.human-controlled/module-org.md` | **用户亲笔，最高权威** | `server` 只有一个追认子模块：`routes` |
| `docs/.human-controlled/request-pipeline.md` | 同上 | 请求从 `app.server.routes` 进入 → `app.pipeline` **驱动** → `app.model_provider` |
| `docs/.human-controlled/api.md` | 同上 | 端点清单，含 Azure 与 Gemini |
| `docs/.human-controlled/client-side-block-delivery.md` | 同上 | 响应头转发时机（**与 `spec.md` 冲突，见 9.3**） |
| `.dev/docs/anthropic-responses-bridge/spec.md` | **唯一行为 oracle** | 可观察行为合同 |
| `.dev/docs/anthropic-responses-bridge/architecture.md` | **已获用户接受（2026-08-19）** | `D-ARCH = B`、`D-MIGRATION = M1`；五项边界共同定义 B |
| 裁决附带的授权说明（`architecture.md:5`） | 同上 | 「实现方可全面推进 B，若将来发现与用户文档不一致，再讨论与修复，而不是停下来等裁决」——**该授权覆盖实现细节，不覆盖 `spec.md` 的可观察行为合同，也不覆盖 `docs/.human-controlled/`**（两个豁免项，初版只引了后一个） |
| `architecture.md:603` 「可局部调整的边界」 | 同上 | 「组件是否按文件或 package 合并／拆分」不需要重开 `D-ARCH`——但该节开宗明义的前置是「**只要不破坏上述五项核心与 Spec 行为**」（初版丢了这个前置） |
| 2026-08-14 架构审计 | **agent 提案，从未被裁决** | 抽验 8 条，**3 条已作废，且全是布局相关的**。其 `deployment/`／`web/` 三层方案不要重做 |
| `.dev/docs/archived-2604-rewrite/` | **用户 2026-08-20 裁定整体过期** | 不得引为依据 |

**修正后的行动分界线**（比初版严）：

- **已获授权**：`app/` 内部的模块合并、拆分、搬迁——**前提是行为不变**，且不得借搬迁之机改变任何 `spec.md` 管辖的可观察行为。
- **必须问用户**：触及 `docs/.human-controlled/` 所述事实的事；以及 `spec.md` 与用户亲笔文档冲突时该听谁的。

⚠️ **时序事实，防止误读为知情裁决**：`module-org.md` 工作树版本比 HEAD 多出 `pipeline/delivery` 两行（未提交，mtime 12:48），说明用户当天编辑过并保留了 `server/routes`——但那是在代码侧发现这处不一致**之前约三小时**。

---

## 3. 现状证据

### 3.1 `app/server/` 八个模块的实际归属

| 模块 | 行数 | 实际是什么 | 判据 |
|---|---|---|---|
| `inbound.py` | 89 | ✅ 入站编解码 | 与「基础输入格式解析」一致 |
| `ops_routes.py` | 76 | ✅ 运维端点 | 只被 `pipeline_app` 用 |
| `admission.py` | 57 | ✅ 在途并发闸门 | 位置正确 |
| `pipeline_app.py` | 1037 | ⚠️ 四合一 | 见 3.2 |
| `tls.py` | 136 | ❌ 监听器 TLS 材料 | **包内零消费者**；三个调用方全在 `lifecycle`／`cli` |
| `composition.py` | 576 | ❌ 组装根 + 上游传输构造 | 被包外的 `cli.py`、`debug/models.py` 消费 |
| `handler.py` | 645 | ❌ 管线驱动器（**25 个顶层符号**） | `request-pipeline.md` 把驱动指派给 `app.pipeline` |
| `app_factory.py` | 177 | ❌ 旧链 app 工厂 | `src/` 内**零生产导入者** |

### 3.2 `pipeline_app.py` 按职责的量化

| 职责 | 行数 | 成员 |
|---|---|---|
| 可观测性——连接快照 | 68 | `_extra_info` `_readable` `_socket_address` `_alpn` `_snapshot_upstream_connection` |
| 可观测性——trace 与完成行 | 127 | `_translation_losses` `_Trace` `_log_completion` |
| **流字节记账（受 `spec.md` 管辖，见 5.2）** | 135 | `_StreamAccounting` `_AccountedStreamingResponse` `_counted_upstream` `_tracked_delivery` |
| 派发 | 479 | `_serve` `_aborted` `_client_message_count` `_dispatch`（**418 行**） |
| 装配与 lifespan | 79 | `build_router` `create_pipeline_app` `_version` `_lifespan` |

### 3.3 可达性实测（探针已做正样本对照）

| 入口 | `app.*` 模块数 | `app.routes` | `app.core` |
|---|---|---|---|
| `app.cli`（**唯一真实生产入口**） | 139 | 0 | 不可达 |
| `app.server.pipeline_app` | 126 | 0 | 不可达 |
| `app.server.app_factory` | 140 | **12** | 不可达 |

`cli.py` 无任何函数内延迟导入（AST 核实），四条部署路径全部收敛到 `app.cli`。**旧链整体不在生产路径上**，唯一入口是 `app_factory` 这一条边。

另一组实测，是本版第一步的依据：`app.server.composition` 传递拉进 **104** 个 `app.*` 模块，其中 **37** 个 `app.pipeline.*`（含 9 个 `delivery`）并触达 `app.observability`。**任何 pipeline 层的模块要拿 `Chain` 类型，都得反向 import 这一整坨。**

### 3.4 追认清单与代码的差距，以及其中的一条模式

- 10 个顶层**包**从未出现在追认清单：`debug delivery hooks models protocols routes streaming tokenization transform upstream`。
- 7 个顶层**模块**同样从未出现：`deps errors graceful_timeout repetition_detector runtime shutdown wire_json`。
- 3 个列为「尚未确认、有疑虑」仍在：`anthropic context openai`。
- 追认了但生产不加载：`core`（其两个导入者自身也不可达）。

**其中一条值得单独命名的模式——「追认的子模块名，在代码里以顶层兄弟的形式存在」，三例：**

| 追认的名字 | 代码里的顶层兄弟 | 哪个是活的 |
|---|---|---|
| `server/routes` | `app/routes/`（12 模块，旧链） | 都不活——旧链不可达 |
| `cli/debug` | `app/debug/` | 顶层兄弟活（`cli.py` 在 import） |
| `lifecycle/shutdown` | `app/shutdown.py` | **追认的那个活**（`standalone.py` 在用）；顶层兄弟生产零导入者，只有两个测试 |

三例里两例的顶层兄弟是残骸。这比单看 `server/routes` 更能说明问题的性质：**不是文档写错了名字，是代码在追认的位置之外长出了同名兄弟。**

其它重复：新链 `ops_routes.py` 的 health／metrics 与旧链 `routes/health.py`＋`routes/metrics.py` 各写一遍；`app/delivery/` 与 `app/pipeline/delivery/` 各导出一个**不同的** `DeliverySession`；`src/app/lifecycle/rolling/` 只剩 `__pycache__`。

---

## 4. 怪味与各自违反的原则

### S1 包名与内容不符
`__init__.py` 自称「Inbound HTTP surface」，实际装四类东西。**原则**：包以它拥有的职责命名。判据是 3.1 那一列，不是口味。

### S2 依赖方向反了
`lifecycle/entry.py`、`lifecycle/listener.py` 为拿 TLS 材料 import `app.server.tls`。**原则**：边缘依赖核心。TLS 是 physical transport，按 `D-ARCH=B` 边界 3 不属于 protocol 表面。

### S3 组装根放在叶子里——这才是空 `__init__.py` 的真正原因
`composition.py` 造 `Chain`，而 `cli`、`debug` 都要它，于是拿对象图必须 import HTTP 包。3.3 的第二组数字给出了代价：37 个 pipeline 模块被反向拖进来。**即使旧链明天删干净，这条依然成立。**

### S4 一个函数 418 行——**这一条已按评审降级并换了依据**
初版说它「违反 `D-ARCH=B` 边界 2」。**证据不足**：边界 2 的禁止项不含入站表面，且 `pipeline_app.py:391` 有 2026-08-22 的设计说明明确主张「以时刻而非时长下传，正是因为时长在下游重启会产生第二个生命周期」，`:691` 补充「同一个时刻，所以仍是一个 clock」。**时限那一条我不反驳。**

换成正面依据：`architecture.md:528` 直接指出了这一处（补读报告给出原文与行号）。留下的论证是**内聚性**——`_dispatch` 至少有六个变化理由（客户端时限、读 body、路由、错误映射、交付编排、流式响应构造），其中交付编排与字节记账不属于入站表面。这是一条比「边界违反」弱、但仍然成立的论证。

### S5 命名互相打架
`app_factory.py`／`create_pipeline_app`／`composition.py` 三个「装配」；`ops_routes.py` 自称 routes 而真正的路由表在 `inbound.py`；两个 `DeliverySession`；`server/errors.py` 若新建还会与已存在的 `app/errors.py` 撞名。

---

## 5. 目标布局

### 5.1 第零步先做的事：收窄依赖，不搬文件

**这是本版相对初版最重要的改动。** 先把 `Chain` 这个**记录**与 `build_chain` 这个**建造者**分开，其余搬迁才不会互相绊住：

```
app/
  chain.py                    ← 自 composition.py：Chain 记录本身（纯类型，不 import pipeline 建造侧）
  composition/                ← 建造者，只有组装侧 import 它
      __init__.py             ← build_chain、refresh_catalogs
      http_client.py          ← TransportOptions、build_http_client、keepalive、代理与 SOCKS
      providers.py            ← resolve_provider_base_urls、build_copilot_provider
      tokens.py               ← github_token_path、build_github_token_source
```

做完这一步，`app.chain` 是薄记录模块，任何层 import 它都不再拖进 37 个 pipeline 模块——后面四步就互相解耦了。

⚠️ `app/chain.py` 与 `app/composition/` 都是**新增顶层落点，不在追认清单里**。初版把「顶层包不在追认清单」当缺陷数，自己却又新增一个，属双标。本版把这个落点一并交给 9.1 裁决，不自行决定。

### 5.2 其余落点

```
app/
  lifecycle/tls.py            ← 自 server/tls.py（三个消费者本来就在这一层）
  observability/
      request_trace.py        ← 自 pipeline_app.py：_Trace、_log_completion、_translation_losses、连接快照
                                 （补读确认无禁令且有正面授权；**须带走 metrics 接线**，`spec.md:142` 要求损失必须进 metrics 与 trace）
  pipeline/
      driver.py               ← handle、handle_bounded、handle_count_tokens、shape_request、_ledger_for→ledger_for、
                                 _answered_failed_search、_countable、HandledRequest、CountTokensRequestError
      routing.py              ← 并入 apply_route、translation_target
      reply.py                ← response_payload、blocks_from_anthropic、reply_summary、dialect_for
      delivery_policy.py      ← framer_for、assembler_for、stream_settings、delivery_buffer、stream_idle_seconds、delivers_blocks
                                 （**在 delivery 之上，不在 delivery 里面**——见下）
      delivery/               ← 字节记账的落点（补读指向 `architecture.md:528`＋`:442`）；**受 5.3 门控**
  server/
      __init__.py             ← 可以重新有内容
      app.py                  ← create_app + lifespan
      admission.py            ← 不动
      inbound.py              ← 只剩 body → RequestContext
      http_errors.py          ← error_status／error_headers／error_body（避开已存在的 app/errors.py）
      routes/                 ← **追认的那个名字**
          __init__.py         ← build_router()、InboundRoute、ROUTES、route_for_path
          inference.py        ← _serve + 瘦身后的派发
          ops.py              ← 自 ops_routes.py
```

**为什么选帧不能放进 `delivery/`**（初版在此犯了 blocker 级错误）：`src/app/pipeline/request.py:17` 写着 `from app.pipeline.delivery.assembling import Terminal`——`delivery` 在图上位于 `RequestContext`／`Route` **之下**，是叶子包，且 `delivery/` 下今天没有任何东西 import `RequestContext`／`Route`。把「需要 `Route` 才能选帧」的代码放进去就是把分层倒过来。故落在 `delivery_policy.py`，与 `routing.py` 平级。

`deliver_blocks` 不在上表——它是**死代码**（全仓只有自己的定义），登记为待删而非搬迁。

### 5.3 一个被门控住的落点：流字节记账

`_AccountedStreamingResponse` 是 response body 的 **close owner**，关闭 body 会透传释放上游连接。补读结论：

- **`architecture.md:340`「converter 和 observer 不关闭 transport」咬得住** → 搬进 `app/observability/` 被禁。
- 评审引的另一条腿「Downstream sink 是唯一 body writer」**不成立**——它不写 body，只是宿主。
- 真正压住它的三条在 **`spec.md`**（`:389` 关闭一次、`:424` finalize 恰好一次、`:448` 单一 finalize owner），而 `spec.md` 正是 2026-08-19 授权**明文不覆盖**的那份。
- `implementation.md:268` 已把相关的 `context.reply` 写入登记为「有意保持不一致、与 STR-04 同切片裁决」——现在搬它等于替一个已推迟的裁决先行作答。
- `architecture.md:611` 允许重新封装 cleanup，所以**被禁的是终点而非移动本身**；文档指向的落点是 `pipeline/delivery/`。

**结论**：这一块不进 `observability/`，落点是 `pipeline/delivery/`，且**排在 STR-04 切片之后**，不在本次做。

---

## 6. 超出布局、但决定收尾的产品事实

`api.md` 追认的以下端点，**线上此刻没有任何进程在服务**：

| 端点 | 追认状态 | 新链 | 旧链 |
|---|---|---|---|
| Azure `POST /openai/deployments/…` | 已追认 | ✗ | `routes/azure.py` |
| Gemini `POST /v1beta/models/…` | 已追认 | ✗ | `routes/gemini.py` |
| 历史 `/history/api/*`、`/history/ws` | 已追认 | ✗ | `routes/history.py`、`protocol_history.py` |
| 状态与配置 `/api/status`、`/api/config` | 已追认 | ✗ | `routes/management.py` |
| 审批、Responses WS、Tokenization | **已裁决暂不支持** | ✗（正确） | 仍在旧链 |

**「线上」是实测而非推断**：`127.0.0.1:4141` 的监听者是 `/home/xp/src/ghc-api-proxy-py/.venv/bin/ghc-api-proxy start --port 4141 --restart`（pid 2254087，cwd 为本仓库，2026-08-22 11:45:40 启动），全机无第二个 4141 监听者、无 Bun 服务在听。未触碰该进程。**能力边界**：`ss` 只看得见本用户可见的监听者。

（事实核查评审曾据 JS 仓库源码判定「现役服务仍在服务这些端点」，与进程表不符，已驳回并记入处置表。）

⚠️ `/api/status`、`/api/config`（已追认）与两个 tokenization 端点（**已裁决暂不支持**）**同在 `src/app/routes/management.py`**——第 6 步不能整体搬或整体删该文件。

---

## 7. 方案对比

| | 方案 1：按职责归位（**推荐**） | 方案 2：只搬走非 server 的模块 | 方案 3：只改文档与命名 |
|---|---|---|---|
| `app.server` 单一职责 | 是 | 部分 | 否 |
| 解掉空 `__init__.py` | 是 | 是 | 否 |
| 修复 S4 | 是 | 否 | 否 |
| `server/routes` 成真 | 是 | 否 | 否（改文档去掉它） |
| 改动面 | 大 | 中 | 极小 |

**取舍（权重：可据以行动）**：推荐方案 1，**分步，且第零步先做**。

对方案 3 的反对，初版理由是「记录下来的现状没人回头看」——**这条被本文档自己的触发来源证伪**：我正是读 `server/__init__.py` 的 docstring 才发现整件事的，评审这一击打得准。改后的理由弱得多但仍成立：方案 3 把一处真实的内聚性缺陷（S4）固化为现状，而 S4 降级之后，这个反对本就该更弱。**方案 3 是可接受的下限，不是错误选项。**

---

## 8. 分步路径

| 步 | 内容 | 前置 | `spec.md` 关系 |
|---|---|---|---|
| 0 | `Chain` 记录与建造者分离（`app/chain.py` + `app/composition/`） | 9.1 裁决（新增顶层落点） | 触碰；须行为不变 |
| 1 | `tls.py` → `lifecycle/` | 无 | **唯一干净的一步** |
| 2 | `_Trace`／完成行／连接快照 → `observability/`（带走 metrics 接线） | 第 0 步 | 触碰；须行为不变 |
| 3 | `handler.py` 按四条缝拆开 | 第 0 步 | 触碰，**最重** |
| 4 | `_dispatch` 拆薄（**不依赖任何命名裁决**） | 第 3 步 | 触碰 |
| 5 | 建立 `server/routes/` | 9.1 裁决 | 触碰 |
| 6 | 旧链收尾 | 9.2 裁决 | 触碰 |

补读结论：**六步里只有第 1 步就 `spec.md` 而言是干净的**，其余全部触碰其管辖的代码。这不等于禁止——授权的豁免意思是「不得借搬迁改变可观察行为」，而不是「不得搬」。因此每一步的验收就是既有测试全绿，且**不得顺手改行为**。

顺序相对初版的两处修正（采纳设计评审 F7）：`_dispatch` 拆薄从第 5 步之后提到第 4 步，不再挂在唯一一道命名裁决后面；且它只被改写一次，而不是被三步各改一遍——该文件两天内被同伴提交过 31 次，是撞车最重的一处。

**不做的事**：不新增任何门、CI 检查或校验框架。既有 `tests/unit/test_module_boundaries.py` 已钉住「新链不得拖进旧链」；是否收紧是用户的决定。

---

## 9. 三个分叉——**用户已于 2026-08-22 全部裁决**

权威记录在 [decisions.md](decisions.md)，本节保留提问时的分析作为背景，**结论以 decisions.md 为准**：

- **9.3 → D-1**：以用户亲笔文档为准，headers 在第一次上游 200 时转发，换取更长的 SSE ping 保活窗口。`spec.md` 已改；`acceptance.md` 的冻结语法与 `architecture.md` 的 delayed-start owner 留作独立切片。**代码无需改动——本次是文档错、代码对。**
- **9.1 → D-2**：使用 `app.server.routes`。新增顶层落点的问题已被更好的解法消除：`Chain` 记录进追认的 `app/core/`，建造者进入口层。
- **9.2 → D-3**：先接新链，值得迁移的主动迁移；判断权在实施方。

以下为提问时的原文分析。

### 9.1 `app.server.routes` 这个名字，以及新增顶层落点

事实：`module-org.md` 追认了它；它从未存在过（`app/routes/` 与当时的单文件 `app/server.py` 是 2026-07-15 同一提交的兄弟，`server` 要到 2026-08-16 `b4ae8b0` 才成为包）；3.4 显示这是**三例同形模式之一**，另两例中追认的名字有一例是活的。

选项：**(a)** 改代码去对齐文档；**(b)** 改文档去对齐代码；**(c)** 维持现状并记录差异（`1f29d0a` 已做到）。

**我的倾向：(a)。** 理由不是「文档说了算」，而是这个名字独立地也对，且 3.4 的模式显示顶层兄弟多为残骸。**同一裁决请一并覆盖**：第 0 步要新增的 `app/chain.py` 与 `app/composition/` 也是不在追认清单里的顶层落点。

### 9.2 旧链去留

事实见第 6 节。选项：**(a)** 接进新链后删；**(b)** 先删、这些端点转「暂不支持」（**需你改 `api.md`**）；**(c)** 都不动，方案止步第 5 步。

**我的倾向：(a)，但不在本次做**——那是功能补全，不是布局重构。第 6 步在它发生前不启动。

### 9.3 【新增，且优先级高于前两条】响应头转发时机：两份权威文档正面冲突

- **你亲笔的** `docs/.human-controlled/client-side-block-delivery.md:9`（工作树中，mtime 今天 15:06:48）：「**不等到出现完整块才转发上游响应头给客户端**……只在第一次 HTTP 200 尝试时转发响应头」
- **冻结的** `spec.md:285`：「首个 content block 完整组装并通过 hooks／limits 前，**下游不得看到 HTTP success headers**」；`:348` 把 header commit 与首块 commit **固定绑定**

两者方向相反，**当前新链实现的是你那一侧**。按「人写文档是最终权威」，你的文档赢；但 `spec.md` 是被其它工作依赖的冻结行为合同，`architecture.md:397/442` 也建在它上面。**这不是布局问题，是行为合同问题**，且它比本文其余部分都更该先解决——第 5.3 节那个被门控的落点、以及 STR-04 切片都压在它上面。

我不替你选。需要的是：以哪一份为准，另一份怎么改。

---

## 10. 顺带发现（登记，不并入本次）

- `app/core/`（已追认）生产进程完全不加载，两个导入者自身也不可达。
- `app/lifecycle/systemd/` 整包只有一个测试在 import，而部署目标是 systemd 托管服务。
- `src/app/lifecycle/rolling/` 只剩 `__pycache__`，无源码、无 git 追踪。
- `cli` 是 416 行模块而非追认的包；`app/debug/` 应为 `cli/debug/`；`app/shutdown.py` 是 `lifecycle/shutdown.py` 的死兄弟。
- `deliver_blocks` 死代码待删；`pipeline_app.py:54` 对 `_ledger_for` 的 `pyright: ignore[reportPrivateUsage]` 可在第 3 步顺手消掉。
- `architecture.md` 的「结构怪味登记」7 行里有 5 行钉在本文判定不可达的旧链模块上——那份登记需要按本文的可达性结论复核一遍。
- `pipeline_app.py:3` 仍写着「Separate from `app_factory`, which still serves the existing implementation」，而 `app_factory` 已无生产调用者，该句已过期。

## 11. 能力边界

- **未执行任何搬迁**，全文为静态分析与设计。
- 可达性结论基于静态 import 闭包，**看不见**动态 import（全仓唯一一处在 `hooks/loader.py`，只挂旧链）、字符串反射、第三方插件入口。所有可达性探针均先做过正样本对照。
- 行数与职责划分来自 AST 与人工阅读，未做调用图或覆盖率验证。
- `architecture.md` 679 行、`spec.md` 全文由补读者分段读完，我本人只读了裁决相关区段；5.3 与 9.3 的结论**依赖补读报告**，其原文与行号见该报告。
- 主树在分析期间被同伴多次改动；数字是 `1f29d0a` 时点快照。
- 9.3 的「当前实现走用户那一侧」来自补读者的判断与我对 `handler.py:389`（「504 rather than 408, ruled 2026-08-22 and written into `client-side-block-delivery.md`」）的旁证，**未逐路径验证**。

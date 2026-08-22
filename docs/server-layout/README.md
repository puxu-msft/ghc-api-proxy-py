# `app.server` 模块布局：现状分析与目标设计

**日期**：2026-08-22。**基线**：主仓 `main` = `1f29d0a`（分析开始时），`.dev` = `bae93f8`。
**触发**：修复代码文档引用时发现 `src/app/server/__init__.py` 引用了用户追认的 `app.server.routes`，而该模块不存在。
**性质**：本文是**分析与提案**，不是裁决。第 9 节列出两个必须由用户裁决的分叉。

**支撑报告**（原始记录，不回填）：

- [链路可达性实测](reports/260822-server-layout-chain-map.md) —— 真实入口、两条链的成员、235 个模块的划分
- [既有结论与权威分级](reports/260822-server-layout-prior-art.md) —— 此前哪些是用户裁决、哪些只是 agent 提案、哪些已作废

---

## 1. 结论摘要

`app/server/` 的八个模块里，只有三个真的属于它自称的「入站 HTTP 表面」。另外四个各自跑错了地方，而且**每一个都有独立于口味的判据**：`tls.py` 在包内零消费者、`composition.py` 被包外的 `cli` 与 `debug` 消费、`handler.py` 干的是用户追认文档指派给 `app.pipeline` 的活、`app_factory.py` 生产零调用。第九个问题在 `pipeline_app.py` 内部：1037 行里约三分之一是可观测性代码，而单个 `_dispatch` 函数就有 418 行。

但**根因有三条，全在 `app/server` 外面**：组装根放在了 HTTP 包里（这才是 `__init__.py` 必须空着的真正原因）、用户追认的 `server/routes` 从未存在而这个名字被未经追认的顶层 `app/routes/` 占着、旧链整体不可达却仍持有若干**已追认但当前无人服务**的端点。**只在 `app/server` 内部挪文件解决不了任何一条。**

推荐做法：把 `app.server` 收缩成单一职责——**物理传输、协议腿选择、编解码边界**——其余四类各归其位；同时把 `server/routes/` 建成用户追认的那个名字。其中大部分搬迁**已在 2026-08-19 的授权范围内**（见第 2 节），无需重开裁决；只有两件必须问用户。

---

## 2. 权威边界：谁能裁决什么

这一节决定了本文哪些部分可以直接做、哪些不行。**先读它再读方案。**

| 来源 | 地位 | 对本主题的约束 |
|---|---|---|
| `docs/.human-controlled/module-org.md` | **用户亲笔，最高权威** | 追认的模块层次里 `server` 只有一个子模块：`routes` |
| `docs/.human-controlled/request-pipeline.md` | 同上 | 请求从 `app.server.routes` 进入 → `app.pipeline` **驱动**处理 → `app.model_provider` |
| `docs/.human-controlled/api.md` | 同上 | 端点清单，含 Azure 与 Gemini（**当前无人服务**，见第 6 节） |
| `.dev/docs/anthropic-responses-bridge/architecture.md` | **已获用户接受（2026-08-19）** | `D-ARCH = B`、`D-MIGRATION = M1`；五项边界共同定义 B，拆掉任一项就不能再叫 B |
| 同上，裁决附带的授权说明 | **已获用户接受** | 「实现方可全面推进 B，若将来发现与用户文档不一致，**再讨论与修复，而不是停下来等裁决**」——但**该授权不覆盖 `docs/.human-controlled/`** |
| 同上，「可局部调整的边界」一节 | 同上 | 「Record、class、**module** 与 `PolicyOutcome` variant 的具体名称、字段分组」以及「组件是否按文件或 package **合并／拆分**」**不需要重新发起 `D-ARCH`** |
| `.dev/docs/architecture-audit/reports/*`（2026-08-14） | **agent 提案，从未被裁决** | 抽验 8 条断言，**3 条已作废，且作废的三条恰好全是布局相关的**。它提的 `deployment/`／`web/` 三层方案不要重做——实际落地成了 `lifecycle`／`server`／`core`，且用户已追认落地形状 |
| `.dev/docs/archived-2604-rewrite/` | **用户 2026-08-20 裁定整体过期** | 其中任何目录结构方案都不得引用为依据 |

**由此得到本文的行动分界线：**

- **已获授权、可直接做**：`app/` 内部的模块合并与拆分、文件搬迁、职责归位。这正是 architecture.md 白纸黑字列为「可局部调整」的那一类。
- **必须问用户**：任何触及 `docs/.human-controlled/` 所述事实的事——`server/routes` 这个名字，以及 `api.md` 里已追认端点的去留。

⚠️ **一条时序事实，防止误读为知情裁决**：`module-org.md` 的工作树版本比 HEAD 多出 `pipeline/delivery` 两行（未提交，mtime 12:48），说明用户当天确实编辑过这份文件、并保留了 `server/routes`。但那是在代码侧发现这处不一致**之前约三小时**，不能当作用户已知情并坚持该名字。

---

## 3. 现状证据

### 3.1 `app/server/` 八个模块的实际归属

| 模块 | 行数 | 它实际是什么 | 判据（不依赖口味） |
|---|---|---|---|
| `inbound.py` | 89 | ✅ 入站编解码：路由表 + body → `RequestContext` | 与 `request-pipeline.md` 的「基础输入格式解析」一致 |
| `ops_routes.py` | 76 | ✅ 运维端点 | 只被 `pipeline_app` 使用 |
| `admission.py` | 57 | ✅ 在途并发闸门（ASGI 中间件） | 边界层限流，位置正确 |
| `pipeline_app.py` | 1037 | ⚠️ 表面 + 可观测性 + 派发 + 装配，四合一 | 见 3.2 |
| `tls.py` | 136 | ❌ 监听器的 TLS 材料与同端口分流 | **包内零消费者**；三个调用方全在外：`lifecycle/entry.py`、`lifecycle/listener.py`、`cli.py` |
| `composition.py` | 576 | ❌ 全应用组装根 + 上游 HTTP 客户端/代理/keepalive | 被包外的 `cli.py`、`debug/models.py` 消费 |
| `handler.py` | 645 | ❌ 管线驱动器 | `request-pipeline.md` 把「驱动模型请求的处理」指派给 `app.pipeline` |
| `app_factory.py` | 177 | ❌ 旧链 app 工厂 | `src/` 内**零生产导入者**；只有 12–14 个测试文件引用 |

### 3.2 `pipeline_app.py` 1037 行按职责的量化拆分

| 职责 | 大致行数 | 成员 |
|---|---|---|
| 可观测性——连接快照 | 68 | `_extra_info` `_readable` `_socket_address` `_alpn` `_snapshot_upstream_connection` |
| 可观测性——trace 与完成行 | 127 | `_translation_losses` `_Trace` `_log_completion` |
| 可观测性——流字节记账 | 135 | `_StreamAccounting` `_AccountedStreamingResponse` `_counted_upstream` `_tracked_delivery` |
| 派发 | 479 | `_serve` `_aborted` `_client_message_count` `_dispatch`（**单个函数 418 行**） |
| 装配与 lifespan | 79 | `build_router` `create_pipeline_app` `_version` `_lifespan` |

**约三分之一是可观测性代码，而 `app/observability/` 就在旁边。**

### 3.3 可达性实测（探针已做正样本对照）

用一次性解释器 `import <模块>` 后读 `sys.modules`，并先验证探针能看见已知必然加载的模块：

| 入口 | 加载的 `app.*` 模块数 | `app.routes` | `app.core` |
|---|---|---|---|
| `app.cli`（**唯一真实生产入口**） | 139 | 0 | 不可达 |
| `app.server.pipeline_app` | 126 | 0 | 不可达 |
| `app.server.app_factory` | 140 | **12** | 不可达 |

`cli.py` **没有任何函数内延迟导入**（AST 核实），所以这个闭包就是生产闭包。四条部署路径（console script、`python -m app`、Dockerfile `CMD`、systemd `ExecStart`）全部收敛到 `app.cli`。

**推论**：旧链（`app_factory.py` + 顶层 `app/routes/` 12 个模块）**整体不在生产路径上**，唯一入口是 `app_factory` 这一条边。

### 3.4 顶层包与追认清单的差距

追认的 9 个顶层模块都在，但：

- **追认了却不存在**：`server/routes`、`cli/start`；`cli/debug` 以顶层 `app/debug/` 的形式存在，而 `cli` 本身是一个 416 行的**模块**而非包。
- **存在却从未在追认清单里出现**：`debug delivery hooks models protocols routes streaming tokenization transform upstream`（10 个）。
- **列为「尚未确认、有疑虑」且仍在**：`anthropic context openai`。
- **追认了、但生产进程根本不加载**：`core`（3 个模块）。它的两个导入者 `lifecycle/systemd/systemctl.py` 与 `tokenization/snapshot_store.py` 自身也不可达，且全仓无延迟导入 `systemctl` 的写法。
- 重复实现：新链 `ops_routes.py` 的 health/metrics 与旧链 `routes/health.py`+`routes/metrics.py` 各写一遍；`app/delivery/` 与 `app/pipeline/delivery/` 各导出一个**不同的** `DeliverySession` 类。
- `src/app/lifecycle/rolling/` 只剩 `__pycache__`，无 `.py`、无 git 追踪文件。

---

## 4. 五处怪味，以及各自违反的原则

### S1 包名与内容不符：`app.server` 是个杂物袋

`__init__.py` 自称「Inbound HTTP surface」，实际装了四类东西。**原则**：一个包以它拥有的职责命名，包里每样东西都为该职责服务。判据不是「看起来相关」，而是 3.1 那一列——`tls.py` 包内零消费者这种事，靠讨论口味是讨论不出来的。

### S2 依赖方向反了：运行时依赖 HTTP 包

`lifecycle/entry.py` 与 `lifecycle/listener.py` 为拿 TLS 材料而 import `app.server.tls`。**原则**：边缘依赖核心，不能反过来。TLS 是**物理传输**关切，归拥有 socket 的那一层——按追认的树就是 `lifecycle`。这同时也是 `D-ARCH=B` 边界 3「protocol leg 与 transport leg 正交」的直接推论：TLS 是 physical transport，不属于 protocol 表面。

### S3 组装根放在叶子里——这才是空 `__init__.py` 的真正原因

`composition.py` 造出 `Chain`（HTTP 客户端、token 源、provider、目录），而 `cli.py` 与 `debug/models.py` 都要它。于是**任何想拿对象图的代码都得 import HTTP 包**。`server/__init__.py` 之所以必须一个 import 都不能有（并被 `tests/unit/test_module_boundaries.py` 用子进程钉死），通常被叙述为「两条链的隔离」——但那只是症状之一。**组装根错位是更根本的那条**：即使旧链明天删干净，`cli` 依然要为一个 `Chain` 去 import `app.server`。

**原则**：组装根（composition root）属于应用顶层，不属于任何一个叶子层。

### S4 一个函数 418 行，且它在错误的一层拥有生命周期

`_dispatch` 至少有六个变化理由：客户端时限、读 body、路由、错误映射、交付编排、流式响应构造。**这不只是长度问题**：`D-ARCH=B` 边界 2 写明「Single driver 是唯一 lifecycle 与 action owner……policy、converter、transport、observer 和 History writer 不建立第二套请求生命周期」。今天时限与交付编排由 HTTP 表面持有，**这是对一条已获用户接受的架构边界的违反**，不是风格问题。

### S5 命名互相打架

`app_factory.py`（旧链装配）、`create_pipeline_app`（新链装配）、`composition.py`（对象图装配）三个「装配」并存；`ops_routes.py` 自称 routes，而真正的入站路由表在 `inbound.py`、装配在 `pipeline_app.build_router`；两个不同的 `DeliverySession`。**原则**：同一个词在一个代码库里只能指一件事。

---

## 5. 目标布局

按职责推导，不按现状将就。`app.server` 收缩为单一职责：**接受连接、选出协议腿、把 wire 解成 typed 请求、把结果渲染回 wire**——生命周期与领域决策一概不在这里。

```
app/
  composition.py                  ← 自 server/composition.py：对象图（Chain、providers、token 源）
  cli/                            ← 追认形状：包，而非 416 行模块
      start.py
      debug/                      ← 自顶层 app/debug/
  lifecycle/
      tls.py                      ← 自 server/tls.py（三个消费者本来就都在这一层）
  model_provider/
      transport.py                ← 自 composition.py：HTTP 客户端、代理、SOCKS、keepalive
  observability/
      request_trace.py            ← 自 pipeline_app.py：_Trace、_log_completion、_translation_losses
      wire_accounting.py          ← 自 pipeline_app.py：_StreamAccounting、_AccountedStreamingResponse、_counted_upstream、_tracked_delivery
      upstream_connection.py      ← 自 pipeline_app.py：连接快照那 68 行
  pipeline/
      driver.py                   ← 自 server/handler.py：handle、handle_bounded、handle_count_tokens、shape_request
      routing.py                  ← 并入 apply_route、translation_target
      delivery/selection.py       ← 自 server/handler.py：framer_for、assembler_for、stream_settings、delivery_buffer、stream_idle_seconds、dialect_for、delivers_blocks、deliver_blocks
  server/
      __init__.py                 ← 可以重新有内容了
      app.py                      ← create_app + lifespan（今 create_pipeline_app + _lifespan）
      admission.py                ← 不动
      inbound.py                  ← 只剩 body → RequestContext 的入站编解码
      errors.py                   ← 自 server/handler.py：error_status / error_headers / error_body（领域错误 → HTTP）
      routes/                     ← **用户追认的那个名字，终于是真的**
          __init__.py             ← build_router()
          table.py                ← InboundRoute、ROUTES、route_for_path
          inference.py            ← _serve + 一个瘦得多的派发
          ops.py                  ← 自 ops_routes.py
```

`handler.py` 按三条缝拆开，而不是整体搬走——它本来就装着三样东西：驱动（→ pipeline）、交付选型（→ pipeline/delivery）、HTTP 渲染（→ server/errors.py）。`response_payload`（把上游 body 变回客户端要的格式）是翻译，归 pipeline，不归 `errors.py`。

### 与 `D-ARCH = B` 五项核心的对应

| B 的核心边界 | 本方案如何承载 |
|---|---|
| 1 typed facts 是内部共享真相，wire 只在 adapter／codec 边界 | `server/inbound.py` 与 `server/errors.py` 就是那两处边界，且只剩这两处 |
| 2 single driver 是唯一 lifecycle owner | 生命周期从 `_dispatch` 交回 `pipeline/driver.py`；表面只负责收发与渲染 |
| 3 protocol leg ⊥ transport leg | `server/routes/` 管协议腿；TLS 这类物理传输迁往 `lifecycle` |
| 4 assembler／sequencer／sink／frontier 是一条完整交付链 | 交付选型迁入 `pipeline/delivery/`，表面不再持有成帧决定 |
| 5 History projection ownership 与 request lifecycle 分离 | 本次不触及；可观测性抽出后，投影时点更容易独立验证 |

**没有一条需要重开 `D-ARCH`**——architecture.md 明写「组件是否按文件或 package 合并／拆分」属可局部调整。

---

## 6. 一个超出布局、但会决定收尾的产品事实

`api.md` 追认的端点里，以下**当前没有任何进程在服务**：

| 端点 | 追认状态 | 新链 | 旧链 |
|---|---|---|---|
| Azure `POST /openai/deployments/{deployment}/…` | 已追认 | ✗ | `routes/azure.py` |
| Gemini `POST /v1beta/models/{model}:…` | 已追认 | ✗ | `routes/gemini.py` |
| 历史 `/history/api/*`、`/history/ws` | 已追认 | ✗ | `routes/history.py`、`protocol_history.py` |
| 状态与配置 `/api/status`、`/api/config` | 已追认 | ✗ | `routes/management.py` |
| 审批、Responses WebSocket、Tokenization | **已裁决暂不支持** | ✗（正确） | 仍在旧链 |

所以 `app_factory.py` 与 `app/routes/` **不是可以直接删的死代码**，而是若干已追认端点的**唯一实现，只是没接到 CLI 上**。按项目记忆「『暂不支持』是对外行为裁决，不是删代码授权」，反向同样成立：**已追认为支持的端点，不能因为当前不可达就顺手清掉**。

这条不由布局设计者裁决。它决定的是第 8 节第 5、6 步能不能做。

---

## 7. 方案对比

| | 方案 1：按职责归位（**推荐**） | 方案 2：只搬走非 server 的四个模块 | 方案 3：不动结构，只改文档与命名 |
|---|---|---|---|
| `app.server` 是否单一职责 | 是 | 部分——`pipeline_app.py` 仍是四合一 | 否 |
| 是否解掉空 `__init__.py` | 是（组装根上移后就不需要了） | 是 | 否 |
| 是否修复 S4（生命周期在错误的层） | 是 | 否 | 否 |
| `server/routes` 是否成真 | 是 | 否 | 否（改文档去掉它） |
| 改动面 | 大：约 20 个文件搬迁 + 一次 `_dispatch` 拆解 | 中 | 极小 |
| 与 `D-ARCH=B` 的关系 | 对齐边界 2、3 | 不触及 | 边界 2 的违反被固化 |
| 风险 | 与同伴并行改动冲突；一次动太多不好定位回归 | 低 | 无 |

**取舍与理由（判断权重：可据以行动）**：推荐方案 1，但**分步**，且顺序按「与旧链去留无关」优先。方案 3 我明确反对——它把「生命周期由 HTTP 表面拥有」这条对已接受架构边界的违反，从「待修的债」改写成「记录在案的现状」，而记录下来的现状是不会有人再回头看的。方案 2 是可接受的中途停靠点，但它留下 `pipeline_app.py` 这个四合一模块，而那正是本次最贵的一处。

---

## 8. 分步路径

前四步**与旧链去留无关**，不依赖任何用户裁决，且各自独立可回退：

1. **`tls.py` → `lifecycle/`**。零包内消费者，三个调用方本来就在 `lifecycle`／`cli`。最小、最干净的一步，也用来验证搬迁流程。
2. **`composition.py` 拆分并上移**：对象图 → `app/composition.py`；HTTP 客户端／代理／keepalive → `model_provider/transport.py`。完成后 `server/__init__.py` 不再需要为了隔离而空着。
3. **从 `pipeline_app.py` 抽出可观测性三块** → `app/observability/`。约 330 行，纯搬迁 + 接口收敛。
4. **`handler.py` 按三条缝拆开** → `pipeline/driver.py`、`pipeline/delivery/selection.py`、`server/errors.py`。
5. **建立 `server/routes/`**，把 `inbound.py` 的路由表、`ops_routes.py`、以及瘦身后的派发迁入。**前置：第 9.1 条裁决。**
6. **旧链收尾**：把仍被追认的端点接进新链，然后删 `app_factory.py` 与 `app/routes/`。**前置：第 9.2 条裁决。**

每一步单独提交、单独跑 `ruff` + `pyright` + 相关测试。第 4 步之后建议做一次合并态评审，而不是每步都评审。

**不做的事**：不新增任何门、CI 检查或校验框架。`tests/unit/test_module_boundaries.py` 已经存在并且钉住了「新链不得拖进旧链」；每步之后它是否还该收紧，是用户的决定，不是本方案的一部分。

---

## 9. 必须由用户裁决的两个分叉

这两条都落在 `docs/.human-controlled/` 上，**不在 2026-08-19 那条授权的覆盖范围内**。

### 9.1 `app.server.routes` 这个名字

事实：`module-org.md` 追认了它；它从未存在过；这个名字被未经追认的顶层 `app/routes/` 占着；`app/routes/` 与当时的单文件 `app/server.py` 是 2026-07-15 同一个提交里的兄弟，`server` 变成包要到 2026-08-16（`b4ae8b0`，把 `server.py` rename 成 `server/app_factory.py`），那时 `routes` 已独立服务旧链一个月。

三个选项：

- **(a) 改代码去对齐文档**（本文方案 1 采取的路线）：建立 `server/routes/`，旧的顶层 `app/routes/` 随第 6 步消失。
- **(b) 改文档去对齐代码**：从 `module-org.md` 去掉 `server/routes`，承认表面就是 `server` 下的平铺模块。
- **(c) 维持现状并记录差异**：已由 `1f29d0a` 做到（`server/__init__.py` 现在写明「文档这么拼、代码不是这样」）。

**我的倾向：(a)。** 理由不是「文档说了算」，而是这个名字**独立地也是对的**——把表面（路由表 + 端点处理器）与编解码、装配、闸门分开，本来就该有一个自己的包；而且它同时给第 6 步一个明确的落点。

### 9.2 旧链（`app_factory.py` + `app/routes/`）的去留

事实见第 6 节：它整体不可达，却持有 Azure、Gemini、`/history/*`、`/api/status`、`/api/config` 这些**已追认端点的唯一实现**。

选项：**(a)** 把这些端点接进新链后删除旧链；**(b)** 先删旧链、这些端点转为「暂不支持」（**需要你改 `api.md`**）；**(c)** 暂时都不动，本方案止步于第 5 步。

**我的倾向：(a)，但不在本次做。** 那是一次功能补全，不是布局重构，应当各走各的。在它发生之前，第 6 步不启动。

---

## 10. 顺带发现（不在本方案范围，仅登记）

- `app/core/`（用户已追认）生产进程完全不加载，两个导入者自身也不可达。
- `app/lifecycle/systemd/` 整包只有一个测试在 import，而项目部署目标是 systemd 托管服务——两者需要对账。
- `src/app/lifecycle/rolling/` 只剩 `__pycache__`，无源码、无 git 追踪。
- `cli` 是 416 行模块而非追认的包；`app/debug/` 应为 `cli/debug/`。
- 十个顶层包从未出现在追认清单里，三个被列为「有疑虑」仍在。

这些和 `app.server` 是同一种形态（追认的树与代码分叉），但各自是独立的工作项，**不应该并进本次**。

---

## 11. 能力边界

- **未执行任何搬迁**，本文全部是静态分析与设计。
- 可达性结论基于静态 import 闭包：**看不见**动态 import（全仓唯一一处在 `hooks/loader.py`，只挂旧链）、字符串反射、已安装环境的第三方插件入口。
- 未跑全量测试套件；第 3 节的行数与职责划分来自 AST 与人工阅读，未做覆盖率或调用图验证。
- 未逐字通读 `architecture.md` 679 行全文，只读了裁决矩阵、五项核心边界、driver 职责、隔离规则与 protocol/transport 分层。**若其中另有对内部分层的细约束与本文冲突，以该文为准。**
- 主树在分析期间被同伴改动过（`cli.py`、`server/handler.py`、`server/pipeline_app.py` 等）；行数与结构结论在改动落地后复核过一次，但**本文的数字是 `1f29d0a` 时点的快照**。

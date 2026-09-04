# `src/app/server/` 布局重设计的前置调研：既有结论、权威分级与失效面

**日期**：2026-08-22
**性质**：只读代码考古 + 文档权威分级。未修改任何源码、测试或 `docs/.human-controlled/`。唯一写入是本文件。
**代码基线**：`git -C /home/xp/src/ghc-api-proxy-py rev-parse HEAD` = `959e8d1`（2026-08-22 15:xx）。**主树是共享的，同伴在并行提交**——本文引用的行号取自本次阅读时刻，引用时以符号名为准、行号为辅。
**目的**：为「按最佳实践重新设计 `src/app/server/` 模块布局」提供输入，区分**哪些已被用户裁决**、**哪些只是 agent 提案**、**哪些已被后来的代码作废**。

---

## 0. 先行结论（可据以动手的四条）

1. **`src/app/server/` 现在同时装着两条互不相通的请求链**。生产（`app.cli`）只服务新链 `create_pipeline_app`；旧链 `create_app`（`app_factory.py` + 顶层 `app/routes/`）**不被任何生产入口导入**。这不是推断，是实测（§4.1）。任何「重新设计 server 布局」的方案，第一个要回答的问题是旧链去留，而这件事**用户从未裁决过**。
2. **用户亲笔的 `module-org.md` 里的 `server/routes` 在代码里不存在**，而顶层有一个 `app/routes/`。历史上是先有 `app/routes/`（2026-07-15），后有 `app/server/` 包（2026-08-16），二者从未合并。代码今天（2026-08-22 15:39，`1f29d0a`）刚刚被改成**记录这条差异而不替文档断言**。这是一个**活着的、待用户裁决的分叉**（§5）。
3. **2026-08-14 那批架构审计（9 份）在模块布局这一维度上已大面积失效**。基线 `44471c6` 到 HEAD 之间有 **317 个提交、226 个 `src/` 文件被改动**。抽样核验 8 条具体断言：**5 条仍成立、3 条已被作废**（§3）。**不要把它当现行结论用，但它的两类发现仍然活着**：零消费者模块、`protocols/` 方向边界不闭合——而且仍成立的 5 条几乎全是「没人动过的旧链叶子」，这本身就说明力气都花在建新链上了。
4. **「零消费者模块」这条 8 天前的发现不但没闭合，反而放大了**：现在 `src/app/` 的 234 个模块里，**95 个从生产入口 `app.cli` 不可达**（§4.2）。这是本次调研发现的最大的一块未闭合面，而它正好是 server 布局重设计要处理的对象。

---

## 1. 权威分级：谁说了算

| 层 | 位置 | 权威 | 说明 |
|---|---|---|---|
| L0 用户亲笔 | `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/` | **最高**。`README.md:3` 明写「已经存在的内容，如果与本系列文档相违背，都需要用户再次裁决」 | `module-org.md`、`request-pipeline.md`、`api.md`、`test-org.md`、`lifecycle.md` 与本任务直接相关 |
| L1 用户在 agent 文档上的裁决 | `.dev/docs/anthropic-responses-bridge/architecture.md:3` | **是裁决**（有明确日期与内容） | 「状态：**已获用户接受（2026-08-19）。** `D-ARCH = B`…`D-MIGRATION = M1`」 |
| L2 agent 代行裁决（有用户授权） | `.dev/docs/history/decisions.md` | **可推翻的默认** | 文件自述「用户 2026-08-21 授权：『用户没有主动裁决过，可能是同意了你的提案，你可以灵活修改』」 |
| L3 agent 分析报告 | `.dev/docs/*/reports/**` | **不是裁决** | 包括全部 9 份 architecture-audit |
| L4 已被裁定整体过期 | `.dev/docs/archived-2604-rewrite/` | **无权威地位** | 该目录 `README.md:3`：「**用户裁定（2026-08-20）：这里整体过期。**」 |

### 1.1 L0 中与 server 布局直接相关的原文

`docs/.human-controlled/module-org.md`（**工作树版本，未提交**，见 §5.3）：

```
app
    cli                 # 命令行入口
        debug               # debug
        start               # start
    config
    core
    history
    lifecycle
        shutdown
    model_provider      # 上游模型提供方…
        ghc_client
    observability
    pipeline            # 模型请求的处理管线
        delivery            # 客户端侧的块级交付机制
    server
        routes
```

尚未确认、有疑虑的：`app.anthropic`、`app.context`、`app.openai`。

`docs/.human-controlled/request-pipeline.md:3`：

> 主线：请求从 `app.server.routes` 进入，经过 `app.pipeline` 处理后，交给 `app.model_provider` 上游模型提供方。

**读法提示**：`module-org.md` 标题是「得到用户追认的模块」，正文注明「不代表子模块也被追认」。它是**追认**（对既成事实的确认）与**要求**（历史操作那两条是「要求把 X 移入 Y」）的混合体，不能一律当成设计指令。`server/routes` 属于哪一类，无法从文本判定——这正是 §5 的分叉。

---

## 2. 既有结论清单：出处、当时判据、现在是否仍成立

### 2.1 用户裁决（L0/L1）

| # | 结论 | 出处 | 当时判据 | 现在是否仍成立（本次核验） |
|---|---|---|---|---|
| U1 | 追认模块层次含 `app.server`，其下有 `routes` | `docs/.human-controlled/module-org.md:20-21` | 用户亲笔 | **文档成立，代码不成立**。`ls src/app/server/` 无 `routes`；见 §5 |
| U2 | 请求从 `app.server.routes` 进入 → `app.pipeline` → `app.model_provider` | `docs/.human-controlled/request-pipeline.md:3` | 用户亲笔 | **语义成立、拼写不成立**。新链确实是 `pipeline_app` → `app.pipeline` → `app.model_provider`；路由表在 `src/app/server/inbound.py` 的 `ROUTES` |
| U3 | `app.auth` 移入 `app.model_provider.ghc_client.auth` | `module-org.md:35-36`（「历史操作」） | 用户要求 | **已落地**。`src/app/model_provider/ghc_client/auth/{__init__,providers,service}.py` 存在，顶层无 `app/auth/` |
| U4 | `app.pipeline.delivery` 是客户端侧块级交付机制 | `module-org.md`（工作树版，未提交） | 用户亲笔，2026-08-22 12:48 写入 | **成立**。`src/app/pipeline/delivery/` 存在，11 个模块 |
| U5 | `D-ARCH = B`（typed semantic kernel + single driver + protocol/transport legs）、`D-MIGRATION = M1`（一次建立完整 B 骨架） | `.dev/docs/anthropic-responses-bridge/architecture.md:3` | 用户 2026-08-19 接受 | **成立，且是新链存在的理由**。`tests/unit/test_module_boundaries.py:8-10` 明写「`D-ARCH = B` puts the wire shapes at the codec boundary and nowhere inside; that is only checkable if importing the kernel does not also import everything that predates it」 |
| U6 | Responses WebSocket「暂不支持」：现有代码、测试均保留，**不最终接线** | `docs/.human-controlled/api.md:8,12` | 用户亲笔 2026-08-16 | **成立**。`src/app/routes/responses_ws.py` 存在但只挂在旧链 `app_factory.py:175` |
| U7 | 审批 `/api/approval/*`、Tokenization 端点「暂不支持」 | `docs/.human-controlled/api.md:20-21` | 用户亲笔 | **成立**（同上，仅在旧链） |
| U8 | 生成/发布 id 解析被多域共用，宜置于跨域 `core/` | `docs/.human-controlled/lifecycle.md:3` | 用户亲笔 | **文档成立、前提已变**。`src/app/core/{generation_identity,release_identity}.py` 存在，但其两个消费者（`lifecycle/systemd/systemctl.py`、`tokenization/snapshot_store.py`）**都已不在生产路径上**（§4.2）。该句给的复算命令 `rg -l 'generation_identity\|release_identity' src` 今天只命中这两处 |

**U8 的成因**：rolling 子系统于 `e4a0627`（2026-08-19，`refactor: remove rolling replacement, keeping graceful exit and seamless restart`）被整体移除。`lifecycle.md` mtime 是 2026-08-16，早于该移除。这是一处**用户文档与代码的已知偏差**，但因为它是 L0，我不动它，只记录（§6-O5）。

### 2.2 Agent 提案（L3）——2026-08-14 架构审计的模块边界结论

审计基线 `44471c6`（2026-08-10）。**全部 9 份都是提案，无一被用户裁决过。**

| # | 提案 | 出处 | 当时判据 | 现在是否仍成立 |
|---|---|---|---|---|
| A1 | 新建 `protocols/messages_responses/`（`request.py`/`response.py`/`tool_names.py`），因为 `responses_anthropic.py` 反向 import `anthropic_responses.ToolNameMapper`，方向边界不闭合 | `architecture-audit/reports/260814-audit-module-boundaries.md:17` | 双向 bridge 共享状态放在单向模块 | **事实仍成立，处置已被架空**。`src/app/protocols/responses_anthropic.py:14` 今天仍是 `from app.protocols.anthropic_responses import ToolNameMapper`（行号未漂）。但这两个模块现在归**新链**（在 `pipeline_app` 闭包内），而提案设想的重构目标 `delivery/` 已归旧链。**照它做会把新旧两侧拌在一起** |
| A2 | 把 `delivery/responses_anthropic_stream.py` 移为 `protocols/messages_responses/stream.py` | 同上 `:18` | 协议桥接错放在 delivery 层 | **已被作废**。该文件仍在，但**从生产入口不可达**；新链的块级交付在 `app/pipeline/delivery/`（用户已在 U4 追认）。这是两个不同的 delivery |
| A3 | `delivery/anthropic_sse.py` 拆成 contracts/frontier/renderer/session 四块 | 同上 `:19,83,117` | 四个独立状态域共置 | **已被作废**（同 A2，整个 `app/delivery/` 已下线） |
| A4 | `streaming/translator.py`、`transform/translator.py` 层名歧义，应按「协议对 + 数据粒度」改名 | 同上 `:20-21` | 两者当前消费者均为测试 | **零消费者这一点仍成立**（§3-S5），改名建议无人执行 |
| A5 | 建 `deployment/{rolling,generation,systemd}/` 三层，收拢根包的 rolling/generation/systemd 文件 | 同上 `:54-56,64,67` | 一个 deployment 子系统被切成根包平级文件 | **已作废，且落地形态不同**。实际做成了 `app.lifecycle.*` + `app.core`（`c5a540a`、`40965d8`，2026-08-16），随后 rolling 被整体移除（`e4a0627`）。用户在 `module-org.md` 追认的是 `lifecycle`，不是 `deployment` |
| A6 | 建 `web/`（`app_factory.py`/`runtime.py`/`dependencies.py`）收拢 FastAPI composition root | 同上 `:57,66` | server/runtime/deps 散在根包 | **已作废，且方向相反**。`src/app/server.py` 于 `b4ae8b0`（2026-08-16）变成包 `src/app/server/`，旧文件 rename 为 `server/app_factory.py`。用户追认的是 `server`，不是 `web`。`runtime.py`、`deps.py` 仍在根包，但已随旧链下线 |
| A7 | 建 `core/`（`errors.py`、`wire_json.py`、`identifiers.py`） | 同上 `:58,65` | 跨域叶子依赖 | **半成立**。`app/core/` 已建，但只装了两个 identity 模块；`errors.py`、`wire_json.py` **仍在根包**，且**仍是新链的活跃依赖**（实测两者都在 `pipeline_app` 闭包内） |
| A8 | `pipeline/executor.py` 提取 preparation / nonstream_response / finalization，保留 executor 为唯一 retry owner | 同上 `:103,120` | 编排器混入多职责 | **已被作废**。`pipeline/executor.py` 仍在，但不在生产路径上；新链的执行编排在 `app/server/handler.py` + `app/pipeline/translation_driver/` |
| A9 | `openai/responses_stream_parser.py` **不应**拆分（长但内聚的单状态机），只抽不可变 contract | 同上 `:90-92,118` | 所有 handler 共享同一 draft 集合 | **判断本身仍成立，对象已下线**。该文件今天只被旧链的 `delivery/responses_anthropic_stream.py:20` 导入 |
| A10 | 唯一运行时循环 `app.anthropic.client ↔ app.pipeline.executor` | `260814-audit-dependency-graph.md:17,22` | AST 图 + Tarjan/Kosaraju 双算法 | **仍成立、且行号未漂**（§3-S1），但两端都在旧链上。新链侧有一条**同形态但已被修好**的记录：`tests/unit/test_module_boundaries.py:62-70`（`app.pipeline.exceptions` 不得拉入 `app.upstream`／`app.model_provider.ghc_client`，注释说「the cycle it closed was a real outage」） |
| A11 | 运行时分层 L5=`app.routes`、L6=`app.server`、L7=`app.cli`，102 条跨 SCC 边**无违规** | `260814-audit-dependency-graph.md:33-34` | 层级 = 到叶子最长路径 | **已作废**。今天 `app.cli` 的闭包里**根本没有 `app.routes`**（实测），这条分层描述的是一条已经不服务生产的链 |
| A12 | R9「physical architecture：core、web、deployment 与 explicit ports」 | `260814-synthesis-gaps.md:107-111` | 归并 M4-M8 与依赖图 SCC | **已作废**（是 A5+A6+A7 的归并版本，同样以 `web`/`deployment` 命名） |
| A13 | R13「未接线生产 API 的产品归属裁决，不以孤岛删除代替设计……**没有一手 spec／用户裁决前，此组不能自行实施**」 | `260814-synthesis-gaps.md:134-139` | 是否存在产品 contract 不是 import graph 能决定的 | **完全成立，且规模扩大**（§4.2）。这条与项目记忆「不得擅自删除已实现的功能」同向 |
| A14 | 16 个零消费者模块，提案侧 15/16 未提；`TODO_CURRENT.md` 把它们全标 `[x]` 已交付 | `260814-synthesis-vs-proposal.md:70-76` | 依赖图入度为 0 | **仍成立且更严重**：现在是 95 个模块从 `app.cli` 不可达 |

### 2.3 Agent 代行裁决（L2）

| # | 结论 | 出处 | 权威说明 |
|---|---|---|---|
| P1 | 旧链路 history **本次完全不动**——「`protocol_history.py` 的重复实现在一条不服务生产的链路上，重构 ROI 低；判定它无用并移除触及『不得擅自删除已实现的功能』」 | `.dev/docs/history/decisions.md:13`（条目 9.3） | agent 在用户 2026-08-21 概括授权下拍板，文件自述「每一条都是可推翻的」，代价栏写「无。不动就是零成本」 |

### 2.4 已在代码里固化的结论（既非用户裁决、也非纯提案）

| # | 结论 | 出处 | 说明 |
|---|---|---|---|
| C1 | `app/server/__init__.py` **故意不做任何 import**。曾经 re-export `create_app`，导致「导入 `app.server` 下任何东西都会连带拉进整条旧链」，实测**175 个可达模块从两个入口都可达**，依赖图因此说不出两条链的区别 | `src/app/server/__init__.py:5-12`；提交 `aba73fb`（2026-08-19，`refactor: make the dependency graph tell the truth before moving anything`） | **这是 server 布局重设计必须保留的既有教训**：包 `__init__` 的便利 re-export 会把架构断言变成不可测 |
| C2 | 三条结构断言被固化成测试：①新链不得拉入 `app.server.app_factory`／`app.pipeline.executor`／任何 `app.routes.*`；②typed kernel `app.pipeline.translation_driver.content` 必须是叶子（不得 import 任何 protocol）；③`app.pipeline.exceptions` 必须能脱离 pipeline 被导入 | `tests/unit/test_module_boundaries.py:38-70` | 测量方式是**子进程新解释器**，不是进程内 unload——文件 docstring `:12` 记录了 unload 方案曾把两个 rate-limiter 测试搞挂 |
| C3 | 新链的非推理面**另写**而不是复用 `app.routes`：「Those routers resolve their state through `app.deps`, which reaches the existing chain's settings and runtime, so mounting them here would have pulled that chain back in and undone the separation」 | `src/app/server/ops_routes.py:1-11`（提交 `fac3103`，2026-08-19） | 同一文件还写明：history 与 management API 需要新链尚未拥有的状态，**故意缺席而不是用 stub 假答** |
| C4 | `pipeline_app` 与 `app_factory` 不得同时挂载：「Mounting both would give one path two owners」 | `src/app/server/pipeline_app.py:1-5` | |
| C5 | 入站格式是**路由的属性**，不从 body 嗅探；`ROUTES` 表是路由真值源 | `src/app/server/inbound.py:1-8,31+` | 引用 `docs/.human-controlled/api.md` 为依据 |
| C6 | `composition.py` 是新链的 composition root：「Builds the chain a request travels: config -> provider -> pipeline -> driver. Everything is constructed once at startup and handed down, so nothing reaches for a global」 | `src/app/server/composition.py:1-5` | |

---

## 3. 抽样验证：2026-08-14 审计的 8 条具体断言在 HEAD 上的真伪

漂移量：`git rev-list --count 44471c6..HEAD` = **317**；`git diff --stat 44471c6..HEAD -- src` = **226 files changed, 15652 insertions(+), 3497 deletions(-)**。

| # | 审计原文断言 | 出处 | HEAD 实况 | 判定 |
|---|---|---|---|---|
| S1 | `app.anthropic.client:357`（函数内）↔ `app.pipeline.executor:9`（顶层）构成唯一运行时环 | `260814-audit-dependency-graph.md:17,22` | `src/app/anthropic/client.py:357` = `from app.pipeline.executor import execute_anthropic_pipeline`；`src/app/pipeline/executor.py:9` = `from app.anthropic.client import (` | **仍成立，行号一字未漂** |
| S2 | `protocols/responses_anthropic.py:14` 通过 `ToolNameMapper` 反向依赖 `anthropic_responses.py` | `260814-audit-module-boundaries.md:17` | `src/app/protocols/responses_anthropic.py:14` = `from app.protocols.anthropic_responses import ToolNameMapper` | **仍成立，行号未漂** |
| S3 | 顶层散落 `rolling_controller.py`、`rolling_runtime.py`、`generation.py`、`socket_activation.py`、`server_adapter.py`、`systemd_notify.py`、`systemctl_adapter.py`、`generation_identity.py`、`release_identity.py` | `260814-audit-module-boundaries.md:54-56,64-67` | 逐个 `test -e`：**九个全部 GONE**。去向：`c5a540a`/`40965d8` 迁入 `app.lifecycle.*` 与 `app.core`；rolling 部分随后被 `e4a0627` 整体删除 | **已作废** |
| S4 | `src/app/server.py:53-163` 是 FastAPI composition root，应收拢进 `web/` | `260814-audit-module-boundaries.md:57,66` | `src/app/server.py` GONE。`b4ae8b0` 把它 rename 成 `src/app/server/app_factory.py`（相似度 100%，`git show --stat b4ae8b0` 显示 `src/app/{server.py => server/app_factory.py} \| 0`）。且它今天**不在生产路径上** | **已作废**（结构预感对了一半——确实成了包；但名字是 `server` 不是 `web`，且方向是「拆成包」而不是「搬去 web」） |
| S5 | `streaming/translator.py`、`transform/translator.py`「当前消费者均为测试，生产路由未导入」 | `260814-audit-module-boundaries.md:20-21` | `rg -n 'streaming\.translator' src tests` → 唯一命中 `tests/unit/openai/test_openai_sanitize_accumulators.py:4`；`transform.translator` → 唯一命中 `tests/unit/transform/test_translator.py:2` | **仍成立，8 天零变化** |
| S6 | `shutdown.py`、`repetition_detector.py` 顶层生产模块没有生产消费者，「先由用户裁决」 | `260814-audit-module-boundaries.md:69` | `rg -n 'app\.shutdown\|repetition_detector' src tests` → 仅 3 个测试文件命中，`src/` 内零非自身消费者 | **仍成立，仍未裁决** |
| S7 | `graceful_timeout.py:1-5` 的默认值被 `config/settings.py:8` 导入，建议拆成 `config/shutdown.py` + `deployment/systemd/timeouts.py` | `260814-audit-module-boundaries.md:68` | `src/app/config/settings.py:8` = `from app.graceful_timeout import DEFAULT_GRACEFUL_TIMEOUT_SECONDS`，`src/app/graceful_timeout.py` 三个常量原样 | **仍成立**（`deployment/` 那半个处置目标已不存在） |
| S8 | 运行时分层 L5 `app.routes` → L6 `app.server` → L7 `app.cli`，无违规边 | `260814-audit-dependency-graph.md:33-34` | 实测 `app.cli` 的 import 闭包 139 个模块中**没有任何 `app.routes.*`**，也没有 `app.server.app_factory` | **已作废**：这条描述的层次今天不在生产链上 |

**统计**：8 条中 **5 条仍成立**（S1、S2、S5、S6、S7）、**3 条已作废**（S3、S4、S8）。仍成立的那 5 条有个共同特征——**它们描述的都是旧链内部或跨链共用的叶子**，恰恰是**没有人动过**的部分。这本身就是一条信息：过去 8 天的力气全花在建新链上，旧链原地不动。

---

## 4. 当前实测：两条链的边界

### 4.1 生产入口只走新链

方法：与 `tests/unit/test_module_boundaries.py` 相同的**子进程新解释器**探针（`importlib.import_module(m)` 后读 `sys.modules`），只读，无副作用。

```
new chain  (app.server.pipeline_app): 126 个 app.* 模块
old chain  (app.server.app_factory) : 140 个
production (app.cli)                : 139 个

只在旧链、不在新链的顶层包：delivery, deps, history, hooks, openai, routes, runtime
只在新链、不在旧链的顶层包：（无）

app.routes 在新链闭包内？        False
app.routes 在 app.cli 闭包内？   False
app.server.app_factory 在 app.cli 闭包内？ False
```

`src/app/cli.py:23` = `from app.server.pipeline_app import create_pipeline_app`；`:129`、`:155` 是它仅有的两个调用点。`create_app` 在 `src/` 内**零调用者**（`rg -n 'create_app' src` 只命中定义处与 `server/__init__.py` 的注释），在 `tests/` 内有 14 个文件调用。

**注意反向事实**：新链**没有**摆脱旧世界的几个共用叶子——`app.errors`、`app.wire_json`、`app.config.settings`（legacy `AppSettings`）、`app.anthropic.sanitize.*`、`app.protocols.*`、`app.streaming.*`、`app.transform.model_resolver`、`app.upstream.*` 全都在新链闭包内。也就是说：

- `app.config` 下**并存两套配置模型**：legacy `config/settings.py::AppSettings`（14 个 `src/` 消费者）与新的 `config/schema.py::ProxyConfig`（18+ 个消费者），**新链两套都会加载**。
- 顶层 `app/delivery/`（旧）与 `app/pipeline/delivery/`（新，用户已追认）是**两个同名不同物的交付层**。

**方向是单向的**：旧链依赖新链的叶子（`src/app/delivery/responses_anthropic_stream.py:28` = `from app.pipeline.translation_driver.reasoning_carrier import encode_reasoning_carrier`），反过来没有。**所以旧链的存在不构成新链的技术负担，只构成认知负担与「守卫留在旧链上」那类风险（O8）。**

### 4.2 生产入口不可达的模块：95 / 234

方法同上，`app.cli` 闭包 vs `src/app/**/*.py` 全量枚举。

- 总模块数 **234**，`app.cli` 可达 **139**，不可达 **95**。
- **口径警告**：探针只测 import-time 可达性。函数内延迟 import、`importlib` 动态加载、以及包 `__init__` 的隐式加载都不计。因此「不可达」**不等于**「死代码」——`app.lifecycle.systemd.*` 就是可疑项（`--systemd` 路径可能延迟导入），我未逐一排查（§7）。**这个清单是候选，不是判决。**

按包归组的不可达面：

| 包 | 不可达模块 | 备注 |
|---|---|---|
| `app.routes.*` | 全部 12 个 | 旧链路由 |
| `app.hooks.*` | 全部 10 个 | 已被 `app.pipeline.subscribers.*` 取代（见 `.dev/docs/hooks-subscription-migration/`） |
| `app.history.*` | 全部 10 个 | **`history` 是用户在 `module-org.md` 里追认的模块**，却整个不在生产链上 |
| `app.openai.*` | 全部 8 个 | 含 `responses_stream_parser.py`（审计 A9 的对象） |
| `app.delivery.*` | 全部 3 个 | 旧交付层 |
| `app.pipeline.*` | 7 个：`approval`、`context`、`executor`、`manager`、`protocol_guard`、`rate_limiter`、`route_policy`、`strategies` | 旧链管线 |
| `app.anthropic.*` | 11 个（含 `client`、`request_preparation`、`response_validation`、三个 sanitize 成员） | **`sanitize` 家族的部分成员被 import 但从不被调用**，详见 `.dev/docs/hooks-subscription-migration/reports/260820-sanitize-family-migration-status.md` |
| `app.core.*` | 全部 3 个 | **`core` 也是用户追认的模块**；两个消费者本身也不可达 |
| 顶层散件 | `app.deps`、`app.runtime`、`app.shutdown`、`app.repetition_detector`、`app.context.*` | 审计 A6/S6 的对象 |
| 其它 | `app.streaming.{anthropic_usage,buffered_retry,delayed_commit,openai_sse,translator}`、`app.transform.{system_prompt,translator}`、`app.upstream.{base,bootstrap,generic,models_api}`、`app.protocols.azure`、`app.models.openai`、`app.observability.{telemetry,tracing}`、`app.config.provider`、`app.tokenization.snapshot_store`、`app.server.app_factory` | |

**这 95 个里有一个必须单独指出**：`app.protocols.azure` 不可达，而 `docs/.human-controlled/api.md:9` 把 Azure 端点列为**支持的 API**。同理 `app.history.*` 不可达，而 `api.md:17` 把 `/history/api/*`、`/history/ws` 列为支持的运维端点。**这是「用户亲笔声明支持的能力，当前生产链不提供」的一类缺口**，与 §6-O2 同源。

---

## 5. `app.server.routes` 这个名字：历史上发生了什么

### 5.1 时间线（全部来自 `git log --all --diff-filter=ADR --name-status`）

| 日期 | 提交 | 事件 |
|---|---|---|
| 2026-07-15 | `128e486` `feat(server): add structured lifespan and health routes` | **同时**创建 `src/app/server.py`（单文件）与 `src/app/routes/{__init__,health}.py` |
| 2026-07-15～07-16 | `413a4bf`、`a89463f`、`d483f4a`、`618b324`、`d9804e6`、`99a17e7`、`0b8ba87`、`e3cae01` | 陆续加入 `routes/{anthropic,openai,responses_ws,management,history,metrics,approval,azure,gemini,protocol_history}.py` |
| 2026-08-15 | `110e0f8` → `5322758` | `routes/responses_ws.py` 被删又被 revert 回来（对应 `api.md:12` 的「保留但不最终接线」） |
| 2026-08-16 | `b4ae8b0` `feat: make app.server a package with inbound format parsing` | `src/app/server.py` → **rename** 为 `src/app/server/app_factory.py`（相似度 100%），新增 `server/__init__.py`、`server/inbound.py` |
| 2026-08-16 | `6f7455c` `feat: wire the new chain into a servable ASGI app` | 新增 `server/{composition,handler,pipeline_app}.py` ——**新链诞生** |
| 2026-08-16 | `9518dbf` | 新增 `server/tls.py` |
| 2026-08-19 | `aba73fb` `refactor: make the dependency graph tell the truth before moving anything` | 清空 `server/__init__.py` 的 re-export；建立 `tests/unit/test_module_boundaries.py` |
| 2026-08-19 | `fac3103` `feat: give the new chain the ops surface a supervisor needs` | 新增 `server/ops_routes.py`——新链**另写**运维面，不复用 `app.routes` |
| 2026-08-20 | `ff0c0c7` | 新增 `server/admission.py` |
| 2026-08-22 15:39 | `1f29d0a` | `server/__init__.py` docstring 改为**记录**「文档叫它 `app.server.routes`，这里没有这个模块」 |

**结论：`src/app/server/routes` 从未存在过。** `app.routes` 是 2026-07-15 与当时的单文件 `app/server.py` 一起诞生的**兄弟包**，从来不是 `server` 的子包。`server` 变成包是 2026-08-16 的事，而那时 `routes` 已经服务旧链一个月了，两者没有合并。

### 5.2 这个名字今天的处置状态

它在 2026-08-22 当天被评审抓到并处置过一轮，证据链完整：

- `.dev/docs/tmp/260822-review-doc-citations-coverage.md:21` 报 **major**：「本次提交引入了不存在的模块名 `app.server.routes`，与同一 docstring 第三段自相矛盾」；
- `.dev/docs/tmp/260822-doc-citations-review-disposition.md:13` 采纳并独立复核（`ls src/app/server/` 无 `routes`）；
- 提交 `1f29d0a` 的 message：「That name comes from the spec, there is no such module... Both record what the spec spells differently instead of speaking for it.」
- 落地文本 `src/app/server/__init__.py:3`：

  > `docs/.human-controlled/request-pipeline.md` has requests enter this package and be handed to `app.pipeline`. It calls the entry `app.server.routes`; no such module exists here — the real list is below — so that spelling is the document's, not this package's.

**注意处置的性质**：它把分叉**记录**下来了，**没有解决**。`.dev/docs/tmp/260822-review-doc-citations-coverage.md:131` 的原话是「Whether to follow the document's name is its author's call」——即**明确交回用户**。

### 5.3 一条要提醒主会话的时序事实

`docs/.human-controlled/module-org.md` 的**工作树版本与 HEAD 版本不同**（未提交）：

```
$ git diff HEAD -- docs/.human-controlled/module-org.md
-    pipeline
+    pipeline            # 模型请求的处理管线
+        delivery            # 客户端侧的块级交付机制
```

文件 mtime = `2026-08-22 12:48:17`；提交 `fa0b281`（把这批文档放进仓库）时间 = `2026-08-22 13:36:08`，但该提交里的内容是**旧的**（无 `delivery`）——说明暂存发生在 12:48 之前，提交带走的是暂存态。

**推断（中等置信，可据以提问但不可据以行动）**：用户在 2026-08-22 12:48 编辑过这份文件，加入了 `pipeline/delivery`，**同时保留了 `server/routes` 未动**。若成立，则 `server/routes` 不是一句从没被复看过的旧话。**但这不等于用户在知情下重新裁决了它**——`1f29d0a` 那次代码侧的发现是 15:39，晚于 12:48 三小时，用户编辑时未必知道代码里没有这个模块。**这个分叉必须由用户裁决，不能由布局设计者代选。**

### 5.4 分叉的三个候选终点（供用户裁决，我不代裁）

| 候选 | 含义 | 代价 | 与既有裁决的关系 |
|---|---|---|---|
| a) 代码改名就文档 | 把新链的路由入口收成 `src/app/server/routes/`（今天分散在 `inbound.py::ROUTES` + `pipeline_app.py::build_router` + `ops_routes.py`） | 中。要同时处理顶层 `app/routes/` 的重名——两个 `routes` 不能共存而不混淆 | 与 U1/U2 一致 |
| b) 文档改名就代码 | 请用户把 `module-org.md`/`request-pipeline.md` 的 `server/routes` 改成实际模块名 | 小，但只有用户能做（L0 不可由 agent 修改） | 承认 U1 的 `routes` 是**追认失准**而非要求 |
| c) 维持现状 + 记录差异 | 就是 `1f29d0a` 现在的做法 | 零。但差异会在下一次有人读文档时再被发现一次 | 已是事实默认 |

**我的主观倾向（弱，仅供参考）**：a 与 b 的选择取决于一件用户才知道的事——`module-org.md` 里的 `server > routes` 到底是「我要求你们这么组织」还是「我以为你们已经这么组织了」。这两种读法导出相反的动作，**文本本身分辨不出来**，所以这是必须问的问题，不是可以推断的问题。

---

## 6. 未闭合项：此前指出过、从未落地

| # | 未闭合项 | 首次指出 | 当前状态 | 谁能闭合 |
|---|---|---|---|---|
| O1 | **旧链去留**——`app/routes/`、`app/delivery/`、`app/hooks/`、`app/openai/`、`app/deps.py`、`app/runtime.py`、`app/server/app_factory.py` 及旧 `pipeline` 七件套，共 95 个不可达模块中的绝大部分 | 隐含于 `D-ARCH = B` 裁决（2026-08-19），从未被单列裁决 | **完全未闭合**。`history/decisions.md:13` 只对 history 一支拍了「本次不动」 | **只有用户**。项目记忆明写「『暂不支持』是对外行为裁决，不是删代码授权」 |
| O2 | 用户亲笔声明支持的端点，生产链不提供：**Azure**（`api.md:9`）、**Gemini**（`:10`）、`/history/api/*` `/history/ws`（`:17`）、`/api/status` `/api/config`（`:19`） | `.dev/docs/pipeline-rewrite-parity/reports/260818-ops-gap.md` 全表 | **部分闭合**：`fac3103` 后新链有了 `/health/liveness` `/health` `/health/readiness`、`/metrics`、`/models`（`ops_routes.py:30-74`）。**推理面仍只有 5 条**（`inbound.py::ROUTES` = messages、count_tokens、chat/completions、responses、embeddings），Azure 的 `/openai/deployments/{...}` 与 Gemini 的 `/v1beta/models/{...}` 都不在表内——注意 `protocols/gemini.py` 在新链闭包内，但没有路由通向它 | 需要用户确认优先级；`ops_routes.py:7-10` 已声明 history/management 缺席的理由（「absent rather than answered with a plausible stub」） |
| O3 | **零消费者模块逐个裁决**：接线 / 降级为测试支持 / 删除 | `260814-audit-module-boundaries.md:69`；`260814-synthesis-gaps.md:134-139`（R13）；`260814-synthesis-vs-proposal.md:70-76` | **未闭合，规模从 16 扩到 95**。`streaming/translator.py`、`transform/translator.py`、`shutdown.py`、`repetition_detector.py` 8 天零变化 | R13 原文已写「没有一手 spec／用户裁决前，此组不能自行实施」 |
| O4 | `protocols/` 的方向边界不闭合（`responses_anthropic.py:14` 反向 import `ToolNameMapper`） | `260814-audit-module-boundaries.md:17` | **未闭合，且现在归新链**——是少数**仍活着且在生产路径上**的审计发现 | 可由布局设计直接处理（但注意：处置目标不能是审计提的 `protocols/messages_responses/`，那个方案假设 `delivery/` 也一起搬） |
| O5 | `docs/.human-controlled/lifecycle.md:3` 关于 `core/` 共用性的前提，被 `e4a0627`（rolling 移除）作废；`app.core` 现在无生产消费者 | 本次调研发现 | **未闭合** | 只有用户能改 L0 文档 |
| O6 | 两套配置模型（`config/settings.py::AppSettings` 与 `config/schema.py::ProxyConfig`）并存，且新链把两套都加载 | 本次调研发现（`260814` 审计未覆盖 `config/`） | **未闭合** | 属旧链去留（O1）的子项 |
| O7 | 两个 `delivery`：顶层 `app/delivery/`（旧）与 `app/pipeline/delivery/`（新，用户已追认 U4） | 本次调研发现 | **未闭合** | 同 O1 |
| O8 | 「守卫被留在旧链上」这一形态：`filter_empty_text_blocks`、server-tool gate、伪造 `end_turn`——2026-08-20 一天内连续三次生产故障 | `.dev/docs/hooks-subscription-migration/reports/260820-sanitize-family-migration-status.md:0-30`；项目记忆 `guards-stranded-on-the-legacy-chain.md` | **机制未闭合**：该报告判定为「(c) 无人决定的意外后果」，并指出 `test_module_boundaries` **没有任何断言禁止**新链引入 sanitize，所以那道守卫不构成搬回的障碍 | 布局重设计应把「旧链上还有哪些未搬的行为」当成必答项，而不是等下一次故障发现 |

---

## 7. 我没查的（能力与范围边界）

1. **`app.lifecycle.systemd.*` 与其它疑似延迟导入的模块，我未逐一排查函数内 import。** §4.2 的 95 个「不可达」是 **import-time** 口径。`app.lifecycle.systemd.notify` 大概率在 `--systemd` 路径上被延迟导入，我没有走读 `lifecycle/entry.py` 的全部分支去确认。**把 95 当成候选清单，不要当成删除清单。**
2. **`.dev/docs/architecture-audit/reports/` 的另外 5 份我只做了标题级扫读**（`260814-audit-duplication.md`、`-library-alternatives.md`、`-lifecycle-ownership.md`、`-test-structure.md`、`-typing-leaks.md`）。任务点名的 4 份我通读了。这 5 份里可能还有模块边界相关的具体断言我没抽样。
3. **`documentation-restructure/` 的 34 份报告我未通读**，只做了关键词命中检查。从文件名与命中位置判断，它们讲的是**文档目录**重组（`docs/` → `.dev/docs/`），不是代码模块布局。若这个判断错了，那里可能还有我漏掉的结论。
4. **`anthropic-responses-bridge/architecture.md`（`D-ARCH` 提案正文）我只读了状态行与被引用的片段**，没有通读。方案 B 对「typed semantic kernel + single driver + legs」的**内部分层**可能对 server 布局有更细的约束，我没有提取。**这是我认为主会话最可能需要补读的一份。**
5. **测试目录布局与 `docs/.human-controlled/test-org.md` 的一致性我没核**。`test-org.md` 规定 `tests/{unit,component,int,e2e/claude}/`，而我看到 `tests/int/`、`tests/unit/` 存在，`tests/integration/test_server_startup.py` 曾在 `b4ae8b0` 出现——是否还有 `tests/integration/` 与 `tests/int/` 并存，我没查。
6. **我没有运行任何测试、Ruff 或 Pyright。** 本次全部结论来自只读探针、`git log`、`rg` 与源码阅读。主树有同伴并行改动，跑全量回归的结果无法归因。
7. **`module-org.md` 未提交编辑的时序推断（§5.3）是推断，不是观测。** 我没有 shell 历史或编辑器记录来证明是用户在 12:48 手动写的；也可能是某个进程 touch 的。用它提问可以，用它当裁决依据不行。

---

## 8. 给布局重设计的输入摘要（不是方案，是约束清单）

**必须遵守（用户裁决）**：`module-org.md` 的层次；`api.md` 的端点清单与「暂不支持」标注；`request-pipeline.md` 的主线方向；`D-ARCH = B` 的 codec-boundary 约束。

**必须先问用户（活分叉）**：`server/routes` 这个名字（§5.4）；旧链去留（O1）。

**必须保留的既有教训（代码里已固化）**：`server/__init__.py` 不 re-export（C1）；三条 import 结构断言（C2）；新链不复用旧链 routers 的理由（C3）；一条路径不得两个 owner（C4）。

**仍然活着的审计发现（可直接处理）**：`protocols/` 方向边界（O4）；`graceful_timeout.py` 的归属（S7）。

**不要重做的工作**：2026-08-14 审计对 `deployment/`、`web/`、`core/` 的三层提案（A5/A6/A7/A12）——`lifecycle`/`server`/`core` 已经落地成不同的形状，且用户已追认落地形状。

**不得援引的材料**：`.dev/docs/archived-2604-rewrite/` 全部，含 `project-structure.md`（那份描述的正是今天的**旧链**布局，且已被用户 2026-08-20 裁定整体过期）。

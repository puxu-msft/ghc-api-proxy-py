# `app.server` 布局：用户裁决记录

**裁决日期**：2026-08-22。**裁决人**：用户。**提问处**：[README.md](README.md) 第 9 节（当时是三个待裁分叉）。

本文是这三条的权威记录。README 的方案与步骤按它们改写；后续任何一步与本文冲突，以本文为准。

---

## D-1（原 9.3）响应头转发时机：以用户亲笔文档为准

**裁决原文**：「按『不等到出现完整块才转发上游响应头，只在第一次 HTTP 200 尝试时转发』，这支持我们在更长范围内维护客户端 SSE ping」。

**含义**：`docs/.human-controlled/client-side-block-delivery.md`「客户端响应头」一节胜出，`spec.md` 原「首个完整 block 前下游不得看到 HTTP success headers」被覆盖。用户同时给出了理由，而这个理由本身是一条设计约束：**换取的是保活窗口**——headers 提交之后 `client_delivery.sse_ping_interval` 才能开始发 ping，若等到首块，等待首块的那段长静默里客户端看不到任何东西。

**被覆盖的只有 headers 那一半。** `message_start` 与首个完整 block 进入同一 sink batch 的绑定不变，body event 在首块前仍不可见。这条区分是本次最容易做错的地方：原条款把 headers、`message_start`、body events 绑成一句话，只有第一样变了。

**已落实**：

- `spec.md`「文档状态」新增日期化的重裁条目
- `spec.md`「Downstream Anthropic SSE」重写为 7 条，headers（第 1 条）、`message_start`／body events（第 2 条）、`ping`（第 3 条）分开表述
- `spec.md` retry 边界一节：`response header commit` 改为绑定「第一次上游 200」，并写明由此得到的 retry 边界（提交前可透明重试并返回真实 upstream HTTP error，提交后一律 SSE error event）
- `spec.md` 不变量一节：把 HTTP success headers 从「首块前零可见」清单中移出
- `acceptance.md`：在 `CAL-04-GRAMMAR-v1` 的 `ping` 转移行后标注该约束已被推翻，并写明需要独立切片重做什么

**代码无需改动**：当前新链实现的就是这个行为——`handle_bounded` 的 docstring 明写它「跑到上游响应头到达为止」，随后 `pipeline_app` 返回 `StreamingResponse`，Starlette 在生成器产出任何字节前就发出 `http.response.start`；`_events_with_ping` 包在上游 chunk 流外层，与首块是否完成无关。所以这次是**文档错、代码对**。

**尚未跟进（独立切片，已在 `spec.md` 与 `acceptance.md` 就地登记）**：

1. `acceptance.md` 的 `CAL-04-GRAMMAR-v1` 需升版：`ping` 转移行、固定 fixture 集合里「不得把 `ping` 放在首批之前」那句，以及三条已闭评审行 R3-M1／R4-M1／R5-M1（R4-M1 曾采纳过与本次同向的修订、后被 R5 推翻，重做时要把这段历史读完）。该语法**目前只存在于文档，主仓测试没有实现**，不阻塞运行时。
2. `architecture.md` 的 delayed response-start owner 一族（`:289` frontier `headers_state`、`:397`、`:440`、`:442`、`:453` failure matrix、`:510`、`:513`、`:540`、`:541`、`:569`、`:639`）。实测该机制及其测试**只存在于已不可达的旧链**（`app/streaming/`、`create_app`），新链没有它——所以这不是「改设计」，多半是「把只描述旧链的一段标注清楚」。
3. `spec.md:579` 那条 M1 评审记录是点时记录，**有意不回填**；本裁决覆盖它，覆盖关系记在这里。

---

## D-2（原 9.1）`app.server.routes`：改代码去对齐追认文档

**裁决原文**：「使用 `app.server.routes` 这个路径」。

**含义**：README 9.1 的选项 (a)。建立 `src/app/server/routes/`，入站路由表、推理端点派发与运维端点迁入；顶层 `app/routes/` 随旧链收尾消失。

**连带解决的一处**：README 初版把「新增顶层落点」也捆在这条里问，而用户只答了 routes。**这个分叉现在不需要用户回答了**，因为有更好的解法，且不新增任何顶层名字：

- `Chain` **记录** → `app/core/chain.py`。`core` 是追认过的名字，而它的 `__init__.py` 自己就写着用途：「Facts shared across domains, owned by none of them……一个被多个领域依赖的模块，不能住在其中任何一个里面，否则会让那一个成为其它领域的依赖」。这正是把 `Chain` 搬出 `app.server` 的论证。顺带给这个「已追认但生产不加载」的包一个真实用途。
- **建造者**（`build_chain`、HTTP 客户端、providers、tokens）→ 入口层。组装根本来就该贴着应用入口（Composition Root 的标准做法），而它的两个消费者 `cli` 与 `debug` 按追认树都在 `cli` 之下。

⚠️ 代价要说清楚：把建造者放进 `cli` 之下，意味着要按追认树把 416 行的 `cli.py` 变成 `cli/` 包（含 `start`、`debug`）。这是在实施另一条**已经追认**的树形，与 D-2 同源，但它是一块独立的活。**若用户不想让这块跟着一起做，请叫停**——替代做法是新增顶层 `app/composition/`，那需要用户为新增顶层名字单独裁决一次。

---

## D-3（原 9.2）旧链：先接新链，值得迁移的主动迁移

**裁决原文**：「先接新链，如果有值得迁移的功能，主动迁移」。

**含义**：README 9.2 的选项 (a)，且「值得迁移」的判断权在实施方。顺序是先把功能接进新链，再删旧链——不是先删后补。

**待判断的迁移清单**（`api.md` 已追认、当前线上无人服务）：

| 端点 | 旧链位置 | 初步判断（待逐个核实后定） |
|---|---|---|
| Azure `POST /openai/deployments/…` | `routes/azure.py` | **2026-08-23 已迁移**，见 [status.md](status.md) 与 [deferred.md](deferred.md) |
| Gemini `POST /v1beta/models/…` | `routes/gemini.py` | **2026-08-23 路由入口已迁移**，wire 翻译按用户裁决「留空」，三条路径答 501；未闭合项在 [deferred.md](deferred.md) §D-A、§D-B |
| 历史 `/history/api/*`、`/history/ws` | `routes/history.py`、`protocol_history.py` | 已追认，倾向迁移；`app.history` 整包目前生产不可达，需一并判断 |
| 状态与配置 `/api/status`、`/api/config` | `routes/management.py` | **2026-08-23 已由同伴 `7525f76` 迁移** |
| 审批、Responses WS、Tokenization | 各处 | **已裁决暂不支持**，不迁移；但按项目记忆「暂不支持不是删代码授权」，删旧链时要单独确认这几处的处置 |

⚠️ **`/api/status`、`/api/config`（已追认）与两个 tokenization 端点（已裁决暂不支持）同在 `src/app/routes/management.py`**——这个文件不能整体搬也不能整体删。

**线上现状（实测，非推断）**：`127.0.0.1:4141` 的监听者是本项目（`ghc-api-proxy start --port 4141 --restart`，pid 2254087，2026-08-22 11:45:40 起），全机无 Bun 服务在听。所以上表这些端点是**此刻真的无人服务**。未触碰该进程。

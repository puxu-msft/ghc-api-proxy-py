# `app.server` 布局提案的评审处置

**处置日期**：2026-08-22。**被处置的提案**：[README.md](../README.md) 初版（`.dev` 提交 `58663b5`）。
**两份评审**：[事实核查](260822-review-layout-proposal-facts.md)（异源，0 blocker／3 major／4 minor／6 nit）、[设计评审](260822-review-layout-proposal-design.md)（2 blocker／6 major／8 minor／2 nit）。
**结论**：方向保留，**内容大改**。初版第 5 节六个落点里两个是错的、三个切得过细、一个漏了 8 个符号；第 2 节引文漏了一道门；第 4 节 S4 的指控过强。

---

## 一、采纳（并已复核）

| 编号 | 发现 | 我的复核 | 处置 |
|---|---|---|---|
| 事实-M1 | 第 2 节引 2026-08-19 授权说明时**只保留了两个豁免项中的一个**，漏掉「不覆盖 `spec.md` 的可观察行为合同」；推导行动分界线时又丢掉 `architecture.md`「只要不破坏五项核心与 **Spec 行为**」这个前置条件 | 读原文属实（`architecture.md:5`、`:603-605`） | **采纳**。这等于我把一道门删掉了——与我几小时前刚在别处栽过的是同一形态。第 2 节补齐两个豁免项与前置条件，行动分界线相应加上 Spec 门 |
| 事实-M2 | 第 4 节 S4「HTTP 表面持有生命周期，违反已接受边界 2」证据不足：边界 2 的禁止项不含入站表面，且代码里有 2026-08-22 的设计说明主张 deadline **以时刻下传正是为了不产生第二个生命周期**，提案未引用也未反驳 | 复核属实：`pipeline_app.py:391`「An instant rather than a duration…a duration restarted downstream would grant a second lifetime」、`:691`「同一个时刻，所以仍是一个 clock」 | **采纳并降级**。S4 改写为内聚性论证（`_dispatch` 有六个变化理由），明确写出时限那一条已有设计说明主张它是对的、我不反驳；仍主张交付编排与记账应移出，但那是内聚性，不是边界违反 |
| 设计-F1 (blocker) | `pipeline/delivery/selection.py` 会把已存在且承重的分层倒过来 | **复核成立，且不需要变异实验**：`src/app/pipeline/request.py:17` 就写着 `from app.pipeline.delivery.assembling import Terminal`，而 `delivery/` 下今天没有任何东西 import `RequestContext`／`Route` | **采纳**。删掉该落点；选帧／选装配器属于 `Route` 之上，落在 driver 一侧 |
| 设计-F5 | `composition.py` 的正确切法是「记录 vs 建造者」，不是「对象图 vs 传输」 | 复核成立且比我的切法好。评审说该模块「import 了 24 个 pipeline 模块」——**我实测是 7 条直接 import、传递可达 37 个 `app.pipeline.*`（共 104 个 `app.*`）**，数字更正但论证更强（探针已做正样本对照：`app.config.schema` 触达 0 个） | **采纳**，用 `app/chain.py`（薄记录）+ `app/composition/`（建造者包）替换初版两行 |
| 设计-F6 | `handler.py` 的缝应该是四条，初版漏了 8 个符号约 110 行 | 复核：handler.py 实际 **25** 个顶层符号（评审说 26，更正）；`response_payload`「归 pipeline」在初版里没有对应文件名，属实 | **采纳**。加第四条缝 `pipeline/reply.py`；25 个符号逐个落位；`_ledger_for` 顺手改公开并删掉 `pipeline_app.py:54` 那条 `pyright: ignore[reportPrivateUsage]` |
| 设计-F7 | 第 8 节顺序有实质缺陷：最贵、也是唯一兑现架构意图的那件事被挂在唯一一道命名裁决后面，且 `_dispatch` 会被三步各改写一遍，而该文件两天内被同伴提交 31 次 | 复核成立 | **采纳**，重排步骤：`_dispatch` 的拆解不再依赖命名裁决，且只改写一次 |
| 设计-F8 | 我对方案 3 的反对「记录下来的现状没人回头看」，**被本文档自己的触发来源证伪**——我正是读 `server/__init__.py` 的 docstring 才发现这件事的 | 复核成立，这条打得准 | **采纳**。删掉该理由；结论改为「方案 3 是可接受的下限，但它固化一处真实的内聚性缺陷」，并说明 S4 降级后这个反对本就该更弱 |
| 设计-F10 | `server/errors.py` 与已存在的 `app/errors.py` 撞名 | 复核：`src/app/errors.py` 确实存在 | **采纳**，改名 |
| 设计-F11 | `observability/upstream_connection.py` 单开一个模块收益撑不起 | 认可 | **采纳**，并入一个模块 |
| 设计-F12 | 初版新增顶层 `app/composition.py`，而第 3.4 节正把「顶层包不在追认清单里」当缺陷数——自相矛盾 | 复核成立，这是我自己的双标 | **采纳**。修订版明确写出：新增顶层落点同属 `docs/.human-controlled/` 范畴，一并交由 9.1 裁决，不自行决定 |
| 设计-F16 | 第 3.4 节只数了顶层「包」，漏了顶层「模块」 | 复核并**扩展**：另有 7 个顶层模块从未进过追认清单（`deps errors graceful_timeout repetition_detector runtime shutdown wire_json`）；其中 `app/shutdown.py` 与追认的 `lifecycle/shutdown` 同名，且**生产零导入者**（只有两个测试），而 `lifecycle/shutdown.py` 被 `standalone.py` 真在用 | **采纳并升级为一条模式**：「追认的子模块名在代码里以顶层兄弟的形式存在」已有三例（`server/routes` vs `app/routes/`、`cli/debug` vs `app/debug/`、`lifecycle/shutdown` vs `app/shutdown.py`），其中两例的顶层兄弟是残骸。这比单看 `server/routes` 有力得多 |
| 设计-F17 | `deliver_blocks` 是死代码，提案却给它安排了新家 | 复核：全仓只有它自己的定义 | **采纳**，从落点表移除，登记为待删 |
| 事实-minor | `/api/status`、`/api/config`（已追认）与两个 tokenization 端点（已裁决暂不支持）同在 `src/app/routes/management.py` | 认可 | **采纳**，写入第 6 节：第 6 步不能整体搬或整体删该文件 |

设计评审的 F3、F9、F13、F15、F18 一并采纳，属措辞与落点微调，不单列。

## 二、不采纳，附理由

| 编号 | 发现 | 为什么不采纳 |
|---|---|---|
| **事实-M3** | 「第 6 节『当前没有任何进程在服务』不成立——现役的 `copilot-api-js` 服务着 Azure／Gemini／status，这会让用户对 9.2(b) 的代价判断反向」 | **驳回，有一手证据。** 评审是从 JS 仓库的**源码**推断的，没有查**实际在跑的是什么**。实测：`127.0.0.1:4141` 上的监听者是 `/home/xp/src/ghc-api-proxy-py/.venv/bin/ghc-api-proxy start --port 4141 --restart`（pid 2254087，cwd 为本项目，2026-08-22 11:45:40 启动），全机没有第二个 4141 监听者、也没有 Bun 服务在听。所以初版那句是对的，而且**比我写时更重**：这不是待办，是线上正在发生的能力缺失。我未触碰该进程（项目规则禁止），观察仅来自 `/proc` 与 `ss`。**能力边界**：`ss` 只能看到本用户可见的监听者；若该服务被以别的方式代理或在别的命名空间中运行，我看不见 |

## 三、补读之后定案的一条（原「待补读」）

**设计-F2（blocker）：成立，但两条腿只有一条咬得住，而且正确落点不是评审说的那个。**

[架构约束补读](260822-architecture-constraints-readthrough.md)的结论：

- ✅ `architecture.md:340`「converter 和 observer 不关闭 transport」**咬得住**——`_AccountedStreamingResponse` 是 response body 的 close owner，关闭 body 会透传释放上游连接。**搬进 `app/observability/` 被禁。**
- ❌ 评审引的另一条腿「Downstream sink 是唯一 body writer」**不成立**——它不写 body，只是宿主。
- 真正压住它的三条在 **`spec.md`**（`:389` 关闭一次、`:424` finalize 恰好一次、`:448` 单一 finalize owner），而 `spec.md` 恰是 2026-08-19 授权**明文不覆盖**的那份文档。
- `implementation.md:268` 已把相关的 `context.reply` 写入登记为「有意保持不一致、与 STR-04 同切片裁决」——现在搬它等于**替一个已推迟的裁决先行作答**。
- `architecture.md:611` 允许重新封装 cleanup，所以**被禁的是终点而非移动本身**；文档指向的落点是 `pipeline/delivery/`（`:528`＋`:442`），不是评审提议的 `server/accounting.py`。

**处置**：采纳 blocker，但按补读改落点——不进 `observability/`，落 `pipeline/delivery/`，且**排在 STR-04 切片之后，不在本次做**。

补读同时给了两条本表其它行的依据：

- `architecture.md:528` 是 **S4 缺的正面依据**，比初版援引的「边界 2」硬，同时回应事实核查那条 major。修订版 S4 已改用它。
- `_Trace`／`_log_completion`／`_translation_losses` 三块**无禁令且有 `:610` 正面授权**，唯一随身约束是 `spec.md:142` 要求损失必须进 metrics 与 trace——**搬迁须带走指标接线**。
- 六步里**只有第 1 步就 `spec.md` 而言是干净的**，其余全部触碰其管辖的代码；第 3 步最重。这不等于禁止（豁免的意思是「不得借搬迁改变可观察行为」），但每一步的验收就是既有测试全绿且不得顺手改行为。

## 四、补读带出的、比本主题更重要的一条

**`spec.md` 与用户亲笔文档正面冲突**（已复核原文）：

- `docs/.human-controlled/client-side-block-delivery.md:9`（工作树中，mtime 2026-08-22 15:06:48）：「不等到出现完整块才转发上游响应头给客户端……只在第一次 HTTP 200 尝试时转发响应头」
- `spec.md:285`：「首个 content block 完整组装并通过 hooks／limits 前，下游不得看到 HTTP success headers」；`:348` 把 header commit 与首块 commit 固定绑定

方向相反，当前新链实现的是用户那一侧。已作为**第三个用户分叉**写入 README 第 9.3 节，并标注其优先级高于两个布局分叉——5.3 的门控落点与 STR-04 切片都压在它上面。

补读者据此判断设计评审的 F15 可能整条不成立；本表不替其定性，留给该分叉裁决后回头处理。


## 四、这次评审教给我的

- **引文漏掉一个豁免项，等于删掉一道门。**（事实-M1）与我当天早些时候在别处栽的是同一形态：判据写下来了，但少了一个条件，于是它挡不住该挡的东西。
- **「记录下来就有人看」不能当论据，但也不能当反论据。**（设计-F8）我用「记录没人看」去否定方案 3，而我自己正是靠读那条记录才发现问题的。
- **搬文件不等于分层。**（设计-F5／F1）初版的根本毛病是只动目录不动签名——`Chain` 照样穿过每一条新划的边界，于是每次搬迁都把组装根拖进一个叶子。
- **评审的一手性也要查。**（事实-M3）一条来自源码推断的断言，被进程表推翻了。

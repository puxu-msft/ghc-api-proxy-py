# 实施状态

本主题共三个 slice，前两个已合入 `main`，第三个是合入后复评查出的修复。

| slice | `main` 上的提交 | 内容 |
|---|---|---|
| 下游保活 | `dbb6104 fix: keep the client alive on our own writes, not on upstream's pace` | 面向客户端的保活，判据不再取自替身量（七副面孔，见下） |
| 上游保活 | `52d877c feat: give the upstream connection the keep-alive its setting promised` | `tcp_keepalive_interval` 实现成真的 `SO_KEEPALIVE`；环境变量代理重建挂载；SOCKS 告警；删两个 legacy 键 |
| 合入后复评修复 | `306bdb7 fix: cap each connection pool once, and get the keep-alive docs' provenance right` | `NO_PROXY` 重复包装导致的 `RecursionError`、两个补丁的顺序回归、SOCKS IPv6 origin 与端口 0，以及两轮文档核对查出的全部失效断言。见 `deferred.md` D-8 / D-9 / D-10 |

闸门（各自合入时点实测，不是同一个数）：`dbb6104` 时 1504 passed / 3 skipped；`52d877c` 时 1550 passed / 3 skipped；`306bdb7` **合入后在 `main` 上实测 1557 passed / 3 skipped**（`uv run pytest -q`，本 slice 新增 5 条回归；比隔离树里的 1555 多 2 条，那 2 条来自同伴同期的提交）。`ruff check src tests` 通过。Pyright **净增 0**：集成前的 `f025e3c` 与集成后的 `306bdb7` 都是 22 errors。

关于 Pyright 的一个读数陷阱：合入后复评报告里那个「父提交 94 → 目标 95」是**在 git 解包副本里测的**，那份副本没有本树的 venv 与已安装的 `app` 包，导入解析退化会凭空多出几十条形状正确的假诊断。**净增 1 那个差值可信（同环境同配置两侧对比），94 / 95 这两个绝对值与本仓的 `uv run pyright src tests` 不可比，不要当闸门数引用。**

本文档第二节末尾那句调和时点的「Pyright 干净」**不是同一回事**，那是在真实工作树里测出的 0 errors。它与今天的 22 的差距来自另一个原因：主线自身的基线在这段时间里漂移过。当前这 22 条里，21 条落在 `stream_cap` 这一对文件上——`src/app/upstream/stream_cap.py` 3 条、`tests/unit/upstream/test_stream_cap.py` 18 条，全是伸进 httpx/httpcore 私有属性产生的 private-usage 与 unknown-type 诊断，是该模块刻意采取的做法（模块 docstring 写明了为什么读这些私有名）；剩下 1 条在 `tests/unit/pipeline/translation_driver/test_translation_driver.py`，与本主题无关。**读任何 Pyright 数字之前先问它是在哪棵树、哪个基线上测的**——本文出现过的这几个数（0、94/95、21、22）分别属于不同的测量条件，横向比较没有意义。

**`tests/e2e` 的 `ModuleNotFoundError: No module named 'harness'` 已经修好了**，别再按红灯处理：`65e0781`（主线孪生 `0c1524f`）把 `from harness import` 改成 `from _harness import`，实测 `tests/e2e --collect-only` 现在收集出 5 个测试。同一个提交也把 `addopts` 改成含 `--ignore=tests/e2e`，所以全量回归不必再手动加这个参数。（`52d877c` 合入时点它确实是红的，那时的判断没错，只是此后被修掉了。）

归档分支（**两个 slice 的 `-onmain` 后缀含义不同，不要按同一个规则读**）：

| 分支 | 指向 | 是什么 |
|---|---|---|
| `archive/260820-delivery-keepalive` | `68a50e7` | 已评审的原始 12 个提交，基于 `5e2f1d5`，含七副面孔的逐条提交信息 |
| `archive/260820-delivery-keepalive-onmain` | `1bb22fb` | 调和后的 4 个提交 |
| `archive/260820-upstream-keepalive` | `2705281` | 已评审的源提交链，7 个 |
| `archive/260820-upstream-keepalive-onmain` | `0176e93` | **一个 rebase 中转的 squash**，不是多提交源。项目规则「归档不得指向 squash 提交」针对的是集成 squash（这里是 `52d877c`），本分支是中间态；记在这里是因为同后缀在两个 slice 里不同义 |
| `archive/260820-keepalive-followup` | `5116606` | 合入后复评修复的已评审源，5 个提交（`10da106` / `029bf0a` / `b472a03` / `bf1e3c1` / `5116606`）。集成 squash 是 `306bdb7`，按规则本分支不指向它 |

评审：五路独立、异源。契约 3 轮判定 spec 可固定为规范；asyncio 正确性 8 轮判定可以合入；调和评审确认主线的清理语义、STR-04 与本分支七条保活性质全部保持，无忙等、无第八种替身量；传输层 3 轮加合入后复评 2 轮（`review-merged-upstream-keepalive.md`、`review-followup-cap-dedup.md`）；文档与裁决核对 2 轮（`docs/tmp/260820-review-keepalive-rulings.md`、`docs/tmp/260820-review-keepalive-doc-fixes.md`）。

第一轮文档核对判定八条裁决在实现里全部准确落实、两条提交信息无夸大，14 条问题全在文档侧；第二轮核对这次修订本身，判定 13/14 已处置，并查出修订过程**新引入**的 4 条假断言（D-5 主语写反、修复提交归错、e2e 红灯早已修好、`deferred.md` D-2 未跟上），均已改。

**唯一未处置的是第一轮的 F-11，理由记在这里而不是略过**：F-11 指出 `review-transport-keepalive-r3.md` 的 `needs-fix` 裁决被无声关掉了——其后又落了三个提交却没有 R4。不补 R4 的理由是那三条前置条件已各自有归宿：① SOCKS 只告警由用户 S2 裁决消解；② 兼容范围与迁移规则随 `pool_idle_expiry` 整个撤销而自然消失，剩下的 proxy 优先级缺口已落成 D-7；③ HTTPS tunnel 的提交内 fd 回归由 `test_the_keepalive_is_on_the_socket_of_a_connect_tunnel` 补上，且已由合入后复评独立复验。**该补的是这段关闭说明本身，不是再跑一轮 R4**，现已补上。

## 合入是怎么完成的（这一段是给下一个撞上同样情况的人）

主线在这段时间里每一到两分钟就有一个提交，`rebase → 跑闸门 → 合入`的周期追不上它，`git merge --squash` 连续两次被同伴的未提交改动挡下，其中一次还往共享索引里留下了不属于我的暂存内容（已用 `git reset` 复原，同伴的改动无损）。

最终走的是不碰共享工作树的路径：`git merge-tree --write-tree` 算出合并树、`commit-tree` 造出 squash 提交、`update-ref` 带期望旧值做 CAS。整个周期是毫秒级，因此追得上主线；CAS 失败过一次（同伴恰好在那几秒提交），失败是安全的——什么都没动，重试即可。

**代价是必须自己把工作树补上**：`update-ref` 不更新任何工作树，所以合入后同伴的 checkout 里我的文件仍是旧内容、会显示成「我的改动被回退」。我用 `git checkout HEAD -- <我的路径>` 逐一同步；其中 `tests/unit/test_stream_delivery.py` 同伴正好有未提交的新工作（`with_deadline_at` 相关），不能直接覆盖，改用 `git merge-file` 三方合并（base 取合入前的 main），冲突只有「双方都在文件末尾追加」一处，两段都保留。合并后两边内容都在，且同伴那份仍是未暂存状态、归他们提交。

## 落地了什么

规范见 `spec.md`，未决事项见 `deferred.md`。下游保活的改动集中在 `src/app/pipeline/delivery/stream.py` 一个文件；上游保活与其后的复评修复动的是 `src/app/server/composition.py`、`src/app/upstream/stream_cap.py`、`src/app/config/schema.py`、`src/app/config/settings.py`。

一句话：**面向客户端的保活，其判据不再取自任何替身量。**

## 这个缺陷的七副面孔

七次都是同一个结构性错误——**守卫的触发条件读的是一个只能替代真实事实的量**。列在这里是因为它比任何单个修复都更值得记住；七次里有六次是评审找出来的，不是我。

| # | 替身 | 真实事实 | 后果 | 提交 |
|---|---|---|---|---|
| 1 | 上游事件的节奏 | 我们向下游写出字节 | 上游持续发 delta 时下游零字节零 ping，静默无上界 | `a374f39` |
| 2 | 产出字节的时刻 | 字节交给服务器的时刻 | 慢下游提前收到 ping | `97d805e` |
| 3 | 块被组装出来 | 字节被交付 | `full` / `until-tool-use` 下两道守卫同时熄灭 | `3160285` |
| 4 | 「发生过一次等待」 | 「时间到了」 | 上游持续就绪时到期机会被 `task.done()` 全部吃掉 | `6a55adf` |
| 5 | 保活的 deadline | 所有 deadline | `ping=0` 且合成开启时首字节被推到流末 | `b1eb2ee` |
| 6 | 拉取正常 | 交付正常 | 畸形事件前先发了 `message_start` | `c897aec` |
| 7 | 采样得到的布尔值 | 此刻的时钟 | 装配期间到期时保活推迟一整个装配 | `0115c58` |

第 7 次同时推翻了第 6 次提交里「已拆掉最后一个替身」这句话。

## 明示接受的取舍

到期的提示仍会发出，即使下一次拉取会立刻结束或失败——不拉是不可能知道下一次拉取返回什么的。按 `spec.md` §2 裁定：**漏掉一次该发的保活是违约，多发一次不是。**

代价的完整形态写在 `spec.md` §2，不是「一枚注释」那么简单：客户端尚无字节时多发的是 `message_start`，它把原本零字节的请求变成一次**客户端可见的截断报错**——`message_start` → `error`（`incomplete_responses_stream`），按已冻结的 Spec 不得再补 `message_stop`。回归 `test_a_due_preamble_goes_out_even_though_the_stream_is_already_over` 钉住了这个线形。

**这一处我连着写错两次**：先把代价说成「一枚注释」（被契约评审判 major），改对之后又写成「已正常封口的空 message」——那是主线落地 STR-04 截断语义之前的形态，被调和评审再判 major。同一个位置、同一种错误：把代价往轻里说。

## 每条修复都有能红的回归

新增 7 条测试，全部验证过在对应修复之前失败。中途有两条被丢弃或重写，理由一并记下，因为它们是这次唯一两处「绿灯没有分辨力」：

- 一条公共路径的 M-1 测试在未修复代码上是绿的——`stream_delivery` 在 `yield` 恢复后打戳，消费者空转期间生成器挂起、下次拉取先刷新了 `last_write`，那枚提示本来就不会发。改为直接驱动 `_events_with_ping` 才有分辨力。
- 一条断言「调度层产出的每个回合都带事件」的测试碰巧为真——调度层在「拉取仍在进行、deadline 到期」这条分支上确实会产出无事件的回合，只是那个构造走不到。已重命名为它实际钉住的窄性质。


## 与 `main` 的分叉：已调和

初版基于 `5e2f1d5`。此后 `main` 前进了 48+ 个提交，其中三个重写了同样这两个函数：

- `926cabf` 给 `_events_with_ping` 加了「有拉取在飞」的 `task` 语义、外层 `try/finally` + `finish_stream_cleanup`，给 `stream_delivery` 加了 `aclosing`——即本文档初版记的 D-1，**由并行会话修掉了**。
- `a9c75d4` / `16dd68c` 给 `stream_delivery` 尾部加了截断语义（STR-04）。
- `a7ca9ea` 把上游空闲检测接到了新链路。

**已调和**：已评审的 12 个提交存进不可变归档 `archive/260820-delivery-keepalive`，然后压成一个提交 rebase 到 `main`，把本分支的保活调度**手工重新施加**在主线那版之上。结果：`tests/unit/test_stream_delivery.py` 37 passed（主线 30 + 本分支 7），全量 1488 passed / 3 skipped，Ruff、Pyright 干净。**调和后已另派独立评审**——合并两份对同一异步循环的重写，是新缺陷最容易出现的地方，不靠「测试全绿」放行。

（本节与上一节记的是当时发生的事，路径照当时写。那个文件此后被并行会话的测试树重组移到了 **`tests/unit/pipeline/delivery/test_stream_delivery.py`**；要跑它请用新路径。）

跟进主线还暴露了一件比那次更正本身更重要的事：`spec.md` 里每一条关于「某处有没有接线」的断言都有保质期。`a7ca9ea` 一落地，§4 关于 `stream_idle` 的整段就作废了；并行会话对 `upstream_transport.http2` 的改动又让 §3 关于 `http2_ping_interval` 的表述作废。两处都已更正，并在 §4 写明了这条使用限制。

## 用户已裁决

| 项 | 裁决 |
|---|---|
| 两侧保活的关系 | **「要清晰区分 client ↔ proxy ↔ upstream 这两侧的保活，它们是不同的，不可混为一谈。」** 本主题的全部结构由这条决定 |
| 主线跟进与合入 | 持续跟进新版，合适时机 `ExitWorktree` 合入 |
| D-2 合成窗口与人写文档冲突 | **用户自行修订人写文档**，本项目侧不动实现 |
| D-3a `tcp_keepalive_interval` | **A1：实现成真的 `SO_KEEPALIVE`** |
| D-3e 两个 legacy 键 | **被取代就删**；没取代的要说清为什么没实现 |
| D-3f SOCKS 路径 | **S2：接受限制并告警** |
| 连接池保留时长 | **从来没有被裁决过**，不得为保住那 15 秒新造配置键 |
| D-4 `hedge` 未实现 | **未来做，目前暂缓** |

**一条不属于本表的**：用户指出 D-5 / D-6 是缺陷不是裁决点——「如果是修复问题，有什么可裁决的？」把它登记进「已裁决」表本身就是同一个错误的复发，故移出表外记在这里。分类已更正：正确做法唯一，排期修，不需要任何输入；现已由并行会话的 `783f023` 完成。

## 待裁决：已裁完

**用户已裁决 A1——实现成真的 `SO_KEEPALIVE`。** 我原本倾向 A2（只改名，活性靠已排期的 D-6 修复恢复），理由是自建 transport 会让 httpx 关掉 `HTTP_PROXY`/`HTTPS_PROXY` 支持、必须自己补回，而那正是人写文档明确规定了优先级的东西。裁决已下，按 A1 做，那个代理回归是这个 slice 必须证明没有发生的头一件事。

原文（保留备查）：

### 原待裁项

`deferred.md` D-3a：`upstream_transport.tcp_keepalive_interval` 的名字承诺「TCP 保活」，实际是连接池空闲过期时长，从不往 socket 写字节、请求在飞期间根本不生效。三选一：**A1 实现成真的 `SO_KEEPALIVE`**（代价是自建 transport 会关掉环境变量代理支持，须自己补回，且要新增一个配置键）、**A2 只改名**（改的是人写文档，只能由用户做）、**A3 保留现状加注释**。调查方偏好 A1，理由是上游腿三道守卫当前全部失效，它是唯一默认开启的活性探测；判 A3 不可接受。

其余原 D-3 内容已重新分类为**无岔路的缺陷**，见 `deferred.md`：`0 = 禁用` 语义反转、出站连接数无上限、HTTP/2 PING 在 httpcore 上不可实现（应固化为结论）、`settings.py` 两个死键。

## 排期修：本主题内已全部做完

本节此前列着「D-3b、D-3c、D-3d、D-3e、D-5、D-6，以及 `streaming-resilience.md` 配置表的顺手更正」。**这六条现在一条不剩全都完成了**——D-3b/c 随错映射的删除一并消失，D-3d 由并行会话加上 NOT IMPLEMENTED 标注，D-3e 两个 legacy 键已删（`52d877c`），D-5 由并行会话的 `064ba63` 修掉、D-6 由 `783f023` 修掉。`streaming-resilience.md` 已判定为归档件、不必回头改（见 `deferred.md`「文档侧顺手项」一节）。照旧清单接手会去重做六件已完成的事，故改写为现状。

**当前真正未完成的只有一条**：`deferred.md` D-7，proxy 优先级三来源被压平、无 provenance，因而无法实现人写文档规定的优先级。缺陷，无岔路，排期做掉。

另有交还用户的两条文档问题（人写文档中英不一致、`http2_ping_interval` 仍被描述成生效的保活），见 `deferred.md`「交还用户的文档问题」一节——我方不改那份文件。

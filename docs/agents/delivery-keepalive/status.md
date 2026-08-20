# 实施状态

- 分支：`worktree-delivery-keepalive`（工作树 `.claude/worktrees/delivery-keepalive`），**已调和到 `main` 的 `4511aa3` 之上**
- 已评审的原始历史（12 个提交，基于 `5e2f1d5`）封存在不可变归档分支 `archive/260820-delivery-keepalive`
- 闸门（调和后）：全量 `pytest` **1488 passed、3 skipped**；`tests/unit/test_stream_delivery.py` 37 passed；`ruff check src tests` 通过；`pyright src tests` 0 errors
- 评审：三路独立、异源。契约评审三轮判定 spec 可固定为规范；asyncio 正确性评审八轮判定可以合入；**调和评审确认主线的清理语义、STR-04 与本分支七条保活性质全部保持，无忙等、无第八种替身量**
- **尚未合入 `main`**：主线仍在快速前进，合入前需再次 rebase 到当时的 tip 并重跑闸门

## 落地了什么

规范见 `spec.md`，未决事项见 `deferred.md`。代码改动集中在 `src/app/pipeline/delivery/stream.py` 一个文件。

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

跟进主线还暴露了一件比那次更正本身更重要的事：`spec.md` 里每一条关于「某处有没有接线」的断言都有保质期。`a7ca9ea` 一落地，§4 关于 `stream_idle` 的整段就作废了；并行会话对 `upstream_transport.http2` 的改动又让 §3 关于 `http2_ping_interval` 的表述作废。两处都已更正，并在 §4 写明了这条使用限制。

## 用户已裁决

| 项 | 裁决 |
|---|---|
| 主线跟进与合入 | 持续跟进新版，合适时机 `ExitWorktree` 合入 |
| D-2 合成窗口与人写文档冲突 | **用户自行修订人写文档**，本项目侧不动实现 |
| D-4 `hedge` 未实现 | **未来做，目前暂缓** |
| D-5 / D-6 | 用户指出这两条是缺陷不是裁决点。**已更正分类**：正确做法唯一，排期修，不需要任何输入 |

## 待裁决：已裁完

**用户已裁决 A1——实现成真的 `SO_KEEPALIVE`。** 我原本倾向 A2（只改名，活性靠已排期的 D-6 修复恢复），理由是自建 transport 会让 httpx 关掉 `HTTP_PROXY`/`HTTPS_PROXY` 支持、必须自己补回，而那正是人写文档明确规定了优先级的东西。裁决已下，按 A1 做，那个代理回归是这个 slice 必须证明没有发生的头一件事。

原文（保留备查）：

### 原待裁项

`deferred.md` D-3a：`upstream_transport.tcp_keepalive_interval` 的名字承诺「TCP 保活」，实际是连接池空闲过期时长，从不往 socket 写字节、请求在飞期间根本不生效。三选一：**A1 实现成真的 `SO_KEEPALIVE`**（代价是自建 transport 会关掉环境变量代理支持，须自己补回，且要新增一个配置键）、**A2 只改名**（改的是人写文档，只能由用户做）、**A3 保留现状加注释**。调查方偏好 A1，理由是上游腿三道守卫当前全部失效，它是唯一默认开启的活性探测；判 A3 不可接受。

其余原 D-3 内容已重新分类为**无岔路的缺陷**，见 `deferred.md`：`0 = 禁用` 语义反转、出站连接数无上限、HTTP/2 PING 在 httpcore 上不可实现（应固化为结论）、`settings.py` 两个死键。

## 排期修（不需要输入）

按 `deferred.md`：D-3b、D-3c、D-3d、D-3e、D-5、D-6，以及 `streaming-resilience.md` 配置表的顺手更正。D-6 与 `handle_bounded` 是同一个病，合成一个 slice。

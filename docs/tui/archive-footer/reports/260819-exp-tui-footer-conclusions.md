# PoC：live footer 的渲染机制选型

**结论：采用 `rich.Live`。** 它在每一项 DECSTBM 对照组能过的压力下同样干净，且已在依赖树内（`rich` 是 `textual` 的依赖），无需新增依赖，也不必自研终端原语。

复现命令（三个 driver 共用一个探针，`--repeat` 连跑）：

```
uv run --with pyte python exp/tui-footer/pty_probe.py exp/tui-footer/driver_rich_live.py --lines 40 --repeat 8 --hold
TICKS_PER_LOG=25 uv run --with pyte python exp/tui-footer/pty_probe.py exp/tui-footer/driver_rich_live.py --lines 12 --delay 0.004 --repeat 8 --hold
LONG_LINES=1 uv run --with pyte python exp/tui-footer/pty_probe.py exp/tui-footer/driver_rich_live.py --lines 30 --repeat 8 --hold
uv run --with pyte python exp/tui-footer/pty_probe.py exp/tui-footer/driver_rich_live.py --lines 20 --cols 40 --repeat 8 --hold
```

把 `driver_rich_live.py` 换成 `driver_decstbm.py` 得到对照组，换成 `driver_naive.py` 得到已知坏实现。

## 为什么需要这个 PoC

`docs/2604-rewrite/lib-survey/SELECTIONS.md` 记录的选型是「TUI → `textual`，接管终端渲染、布局和按键」。但本次要的形态是「请求日志走终端原生滚动、footer 钉在其下方一行」，而 `textual` 的 App 要么接管备用屏、要么以 inline 模式渲染固定块，两者都不产生这个形态。所以选型必须重新落一次，而落法不能靠读文档——`rich.Live` 内部走相对光标，正是 copilot-api-js 在 `src/lib/tui/render/region.ts` 注释里写明「一旦底部写入触发全屏滚动就会错锚」而放弃的那条路。它是否真的错锚，只有实测能回答。

## 测法

`pty_probe.py` 用标准库 `pty` 起 driver 并绑定固定窗口大小，把输出喂给 `pyte.HistoryScreen`，然后按「屏幕网格 + scrollback」评分，而不是断言字节流里出现了某个转义序列。三个 driver 载荷完全相同（零填充编号 `LOG-0001`，防子串误配），差别只在渲染机制。

压力矩阵四项：基线（密集日志）、稀疏日志 + 每条 25 次 footer 重绘（生产形态：日志少、耗时字段每 ~100ms 跳一次）、超宽日志行折成多物理行、窄终端。

## 判据是怎么立起来的——两次假绿假红

**第一版判据没有鉴别力。** `driver_naive.py`（不设滚动区、直接往物理底行画 footer）在它下面报 PASS。抓屏才看到真实损坏：日志行变成 `LOG-0024 POST /v1/messagesnet-4 11.50s`——footer 被屏幕滚动带上去，日志只覆盖了它前半段，尾巴留在原地。漏检有两个原因：`LOG-` 序号仍完好，所以缺号检查看不见；残骸的 `[<-->]` 前缀已被覆盖，所以标记搜索也看不见。

**第二版判据（整行与预期文本逐字比对）假红。** 它把 `rich.Live` 判成 30 条损坏，但样本是 `LOG-0001 POST`——rich 按词边界折行，raw write 按列折行，没有任何一条重组规则同时适配两者，版式差异被读成了损坏。

**第三版判据针对失效机制本身**：footer 是唯一会打印耗时字段的东西，所以 `\d+\.\d\ds` 出现在 footer 自己那行以外的任何位置就是错锚残骸。它与渲染器无关，且对已知坏实现在两种模式下都判红。

这三版的教训是同一条：先抓屏看，再写断言；正样本对照不通过之前，绿色结果不作数。

## 结果

| 压力 | `rich.Live` | DECSTBM 对照 | naive（已知坏） |
|---|---|---|---|
| 基线 | 干净 | 干净 | **判红**，报出残骸样本 |
| 稀疏日志 + 高频重绘 | 干净 | 干净 | — |
| 超宽行折多物理行 | 干净 | 干净 | **判红** |
| 窄终端（未截断） | **判红** | **判红** | — |
| 窄终端（截断后） | 干净 | — | — |

`rich.Live` 没有出现 copilot-api-js 记录的那个错锚。推测原因是它自己记账 live 区域占用的行数、并在每次 print 前把区域擦掉再重画，而不是依赖「光标还停在我上次留下的地方」这个会被滚动打破的假设。

## 两个必须带进实现的发现

**一、footer 必须截断到 `columns - 1`，这是硬要求不是优化。** 未截断时两种机制在 40 列都判红：footer 折成第二行。DECSTBM 那边更糟——溢出行落到保留区之外去污染屏幕。这与 copilot-api-js `finalizeFooter` 做的事一致（剥控制字符 + 截断到 `columns - 1`，-1 是为了避开某些终端的末列自动换行）。加上截断后 40 列与 80 列都干净。

**二、`rich.Live` 的 footer 跟着内容浮动，不钉物理底行。** 只有 12 条日志时它在第 12 行，DECSTBM 恒在第 23 行。对「日志下方一行 footer」这个形态没有影响，屏幕没满时反而不留空档。但**这条差异对后续的 panel/detail 切片有影响**：多行面板要钉底、要与原生滚动共存时，`rich.Live` 的浮动模型可能不够用，届时需要重新评估是否退回 DECSTBM。这一点不在本次切片范围内，记在此处以免后人以为已经论证过。

## 与已记录选型的关系

本次选型**偏离** `SELECTIONS.md` 的字面记录（`textual`），需要主会话向用户点明而非默默改掉。偏离幅度有限：`rich` 是 `textual` 自己的渲染内核，采用它属于在同一套已选栈内挑层级，而非引入新技术栈；被放弃的只是「跑一个全屏 `textual` App」这个形态，理由是它产生不出本次要的形态。`SELECTIONS.md` 里「保留纯 reducer 与业务 state」的部分不受影响，继续成立。

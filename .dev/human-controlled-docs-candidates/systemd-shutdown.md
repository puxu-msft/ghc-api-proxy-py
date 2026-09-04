# 候选：systemd 侧关闭流程的重组方案

> **⚠️ 本文的提案已被用户否决（2026-08-17）——仅作调研留档，不要照它实施。**
>
> 用户裁决：**systemd 侧只做两级**。理由是本文第一节自己给出的事实——systemd 无法原生驱动三级。
> 因此第二节的「提议的重组」、第三节的时限预算、第四节的三种缓解**均不再适用**；`docs/.human-controlled/lifecycle.md:52-55` 现有的两级流程即为定案。
>
> **仍然有效的部分**：第一节的 systemd 行为事实（可作日后参考）、以及第五节列出的、仍需用户修正的文档不一致。
>
> 本文原为回答 `lifecycle.md:52` 的 `（TODO systemd 是否支持三级处理？）`——该问题现已回答：**不支持，故不做**。
>
> 事实依据：`.dev/docs/systemd-runtime/reports/260817-systemd-escalation-research.md`（原路径 `docs/tmp/260817-systemd-escalation-research.md`，2026-08-21 随 `docs/tmp/` 整体迁入 `.dev/docs/`），本机 systemd 255 实测（一次性 transient user unit，已清理；未触碰任何既有 unit）。
>
> **2026-08-22 核对**：第五节四条不一致**全部仍然打开**，行号已按当前文件重新核准（多处与旧版不同）；第二、四、六节里依赖 `lifecycle/rolling/runtime.py` 的顺带收益已随 rolling 删除而失效，就地标注。

## 一、结论先行

**支持，但不是白拿——需要两个驱动源，而不是一个。**

| 问题 | 答案 |
|------|------|
| `systemctl stop` 会自动发第二、三次可处理信号吗？ | **不会。** 只发一次 `KillSignal`（默认 SIGTERM），等满 `TimeoutStopSec` 后发**不可捕获**的 `SIGKILL` |
| 操作者能手工补发吗？ | **能。** unit 进入 `deactivating` 后，`systemctl kill --signal=SIGTERM --kill-whom=main` 仍能送达（`--kill-whom` 默认是 `all`，须显式写 `main`）。**实测限于本机 systemd 255 的 user manager**；推广到 system manager 是我的推断（同一份 manager 代码路径），未实测 |
| `EXTEND_TIMEOUT_USEC=` 能顶用吗？ | 不能**产生级别**。它只延长 `Type=notify`／`notify-reload` 的 deadline——但这个能力在**第四节**的代价缓解里另有用处 |
| `TimeoutStopFailureMode=abort` 呢？ | 只能在一级预算耗尽**之后**多给一个可处理信号，且最终信号仍是终局动作。**不满足「第三级执行持久化与清理后退出」** |

所以：**三级阶梯本身完全可以照搬**（信号语义与直接运行侧一致），但必须再加一个**时间驱动**，否则单纯一条 `systemctl stop` 只会停在第 1 级，直到被 SIGKILL 打断——清理永远不会发生。

## 二、提议的重组

**一句话：systemd 侧复用直接运行侧的同一个 `ShutdownLadder`，只是多一个「没有新信号就按时限自己推进」的驱动。**

| | 直接运行（现状，已实现） | systemd（2026-08-17 时的现状） | systemd（提议） |
|---|---|---|---|
| 第 1 级触发 | SIGINT/SIGTERM/SIGUSR2 | SIGTERM | 同左 |
| 第 2 级触发 | 再一次 SIGINT/SIGTERM | 再一次信号 → **`os._exit`** | 再一次信号 **或** 第 1 级预算到期 |
| 第 3 级触发 | 再一次 SIGINT/SIGTERM | 无 | 再一次信号 **或** 第 2 级预算到期 |
| 退出方式 | 正常返回、不 `sys.exit` | `os._exit(128+sig)` | 正常返回、不 `sys.exit` |

> **2026-08-22 注**：中间那一列描述的是 `lifecycle/rolling/runtime.py`，它已随 rolling 于 2026-08-19 删除。`--fd` 路径现在没有自己的信号阶梯，走的是 uvicorn 的 handler（`src/app/cli.py` 的 `_DrainAnnouncingServer`），因此表中的 `os._exit` 一格已不再描述任何现存代码。

三个后果：

1. **`systemctl stop` 单独一条命令就能走完三级**——在预算成立且 event loop 未被阻塞的前提下，于 `TimeoutStopSec` 到期前完成持久化与资源清理。**这不是无条件保证**：内部计时器跑在 event loop 上，阻塞、死锁或进程停顿会让第 2、3 级根本来不及执行，最终仍只剩 systemd 的强制终止。
2. **操作者仍可加速**——补发一次信号即跳一级，语义与直接运行侧完全相同，不需要另学一套。
3. **`os._exit` 消失**。`lifecycle.md:26` 的「无论如何，不直接 `sys.exit` 等无防护强制退出」写在 standalone 小节内，字面作用域可争；但它读起来像全局约束，而当时的 systemd 路径是唯一违反它的地方。**这一条已自行解决**：违反它的那段代码随 rolling 一起删掉了。

顺带：两条路径合用同一个阶梯，`rolling/runtime.py` 里那套独立的两级逻辑可以退役，关闭语义只剩一处定义。（**2026-08-22 注**：该收益已不存在——`rolling/` 于 2026-08-19 整体删除，那套两级逻辑随之消失。`--fd` 路径现在的关闭由 `src/app/cli.py` 的 `_DrainAnnouncingServer` 加 uvicorn 自己的 graceful 收尾承担。）

## 三、时限预算

时间驱动成立的**必要条件**（研究报告第 8 问）：

```
E + D + I + F + δ < T_stop
```

- `E` = `ExecStop=` 消耗的时间（当前 unit 没有 `ExecStop=`，为 0）
- `D` = 第 1 级 drain 的最大时长
- `I` = 第 2 级「中断后仍等待清空」的最大时长
- `F` = 第 3 级持久化与清理的最大时长
- `δ` = 调度抖动、信号投递、**lifespan cleanup** 与进程退出的保守余量。注意 lifespan cleanup 不是抖动而是有实体耗时的工作项，`lifecycle.md:59` 还点名要求它——别把 δ 当成一个小数字
- `T_stop` = `TimeoutStopSec`

### 我先前以为这里与 C-1 冲突，复核后**不成立**

我原先把 C-1 写成等式 `T_stop = D + F` 并令 `F = 收尾时限`，代入得 `I + δ < 0`，据此认为第 2 级没有位置。**这个冲突是我自设的等式造出来的**，权威文档并不这么说：

- `config.example.yaml:238`（中）／`:241`（英）：「systemd TimeoutStopSec … **必须大于**它和 `client_request_timeout` 之和」——是**下界**，不是等式。
- `config.example.yaml:237`：`graceful_cleanup_timeout` 是「**在请求排空阶段后**，等待的秒数」。第 2、3 级**都在排空之后**，所以 `I` 与 `F` 天然共用这一个预算。

于是有：

```
T_stop = D + graceful_cleanup_timeout + δ
       = 1200 + 60 + δ
```

drain 拿满 `upstream_request_deadline`，`I + F ≤ graceful_cleanup_timeout`，δ 加在外面。**对外公式一字不改、不新增可调量、drain 不缩水。**

先前那两个备选（缩 drain、给公式加项）在**这三条轴上**被本方案压过，所以不在本节并列。但请注意：**一旦把第四节的 reboot 代价计入，「缩 drain」重新成为候选**——它就是第四节的缓解丙。本节只在「不考虑关闭时长对 reboot 的影响」这个前提下成立。

## 四、这次裁决的真实代价：`TimeoutStopSec` 会涨到约 21 分钟

这一节是我上一版漏掉、而评审撞出来的，**也是本次最实际的代价**。

| | 值 | 来源 |
|---|---|---|
| 本机 systemd 默认 | 90s | `/etc/systemd/system.conf:49`（`#DefaultTimeoutStopSec=90s`） |
| 当前 unit | 330s | `contrib/systemd/ghc-api-proxy.service:28` |
| 按 C-1 新公式 | **≈ 1230–1260s（约 21 分钟）** | 1200 + 收尾时限（30 或 60，见第五节第 1 条）+ δ |

**后果**：任何 reboot／shutdown 事务，以及 `Restart=on-failure` 的每个重启周期，都可能在这个 unit 上**静默挂起最长 21 分钟**——只要 drain 期间恰好有长请求在跑，就必然发生。

**这个代价的绝大部分来自 C-1 的公式裁决（基数从 300 变成 1200），而不是来自三级。** 分解给你自己看比例：

| | `T_stop` | 三级比两级多出的部分 |
|---|---|---|
| 两级（现规格），基数 1200 | ≈ 1200 + ε | — |
| 三级（本提案），基数 1200 | ≈ 1200 + 收尾时限 + δ | 约「收尾时限 + δ」；按 60 计约占总量 5%，按 30 计约 2.5% |

换言之：即便维持两级，reboot 也要等约 20 分钟；三级再加的就是收尾时限那一段（30 或 60 秒）。**这个比例摆在这里，要不要三级仍由你权衡**——我不替你把它从反对理由里划掉。

三种缓解，请你选（或告诉我都不要）：

| | 做法 | 代价 |
|---|---|---|
| **甲（推荐）** | `Type=notify` ＋ `EXTEND_TIMEOUT_USEC=`：unit 里的 `TimeoutStopSec` 保持较短（如 120s），服务**只在真的还有在途请求时**才续期 | **它改写第三节的公式**：`T_stop` 不再等于 1200＋收尾，不等式右侧换成「服务每次续期后的**有效 deadline**」，且服务必须自持一个总上限（续期本身不给 `D`／`I`／`F` 任何上界）。其余代价：上界不再由 manager 固定提供、改由服务承诺，服务卡死时反而失去保护；还要把入口改成 `Type=notify`，此后 unit 启动会等 `READY=1`（`lifecycle/systemd/notify.py` 已有 `notify_ready`），漏发则卡到 `TimeoutStartSec` |
| **乙** | 直接写死 `TimeoutStopSec`＝1230 或 1260s（取决于第五节第 1 条） | 最简单、上界仍由 manager 保证；代价就是上面那 21 分钟 |
| **丙** | systemd 路径单独用一个更短的内部 drain 上限（不复用 `upstream_request_deadline`） | reboot 快；代价是 systemd 路径与直接运行路径对「一个请求能活多久」给出不同答案，规格里要多一条例外 |

## 五、需要你确认的几处文档

> **2026-08-22 复核：以下四条全部仍然打开，行号已重新核准。** 原文写的 `config.example.yaml:235`／`:238`／`:240` 与 `existing-rulings.md:92` 都取自更早的快照，现已不指向对应内容。

1. ~~收尾时限到底是 30 还是 60？~~ **已裁决：60s**（2026-08-17）。`config.example.yaml:243` 的 `graceful_cleanup_timeout: 60` 无需改动；**`docs/.human-controlled/lifecycle.md:59` 正文的「（30s）」与之矛盾，需要你改成 60s**。该行至今未改。

2. **公式的基数在三处文档里写的都是 `client_request_timeout`，而该键已不存在**：`docs/.human-controlled/lifecycle.md:59`、`docs/.human-controlled/config.example.yaml:238`、同文件 `:241`。**三处都要改**，只改前一处仍会留下矛盾。（现行键名是 `client_delivery.client_request_deadline`，见 `config.example.yaml:377`。）

3. **基数究竟是哪一个？两份会话记录互相矛盾，我不敢替你选**：

   | 记录 | 内容 |
   |---|---|
   | [existing-rulings.md](existing-rulings.md) 第三节「`client_request_timeout` 的定名」一行（2026-08-16） | 「定为 `client_delivery.client_request_deadline`，默认 **3600**」 |
   | 你 2026-08-17 的口述 | C-1 的基数是「单次上游上限（默认 **1200**）」＝ `upstream_request_deadline` |

   两条都只有「会话」来源、仓库内无一手出处。可能它们并不冲突——08-16 那条是给**配置键改名**，08-17 这条是定**停止公式的基数**，两件事。但也可能是同一件事被我记岔了。**在你确认之前，本文一律按 1200 计算，并在此标明该前提未经一手核实。**

   （改用行名而非行号引用 `existing-rulings.md`：那份文档 2026-08-22 重排过，行号已变，而行名不变。）

4. **`lifecycle.md:52-55` 的两级流程**：`:52` 的「（TODO systemd 是否支持三级处理？）」至今仍在。既然裁决是只做两级，那句 TODO 可以删掉、或改写成「已裁决只做两级」。该文件受你控制，我不擅改。

## 六、落地顺序（若采纳）

> **本节整体不适用**——提案已被否决。保留仅为记录当时设想的顺序。**2026-08-22 注**：第 4 步的对象（`rolling/runtime.py`）已随 rolling 删除而不存在。

1. 建 `start --systemd` 入口（`lifecycle.md:42` 已定此写法），走 socket activation ＋ `sd_notify`，服务于新处理链。
2. 让该入口使用同一个 `ShutdownLadder`，加时间驱动。
3. 重写 `graceful_timeout.py`：不再是三个写死的常量，而是从 `ProxyConfig` 推出 `TimeoutStopSec`，unit 模板与测试随之对齐（测试现在在 `tests/systemd/`，原文写的 `tests/smoke/` 已不存在）。
4. ~~`rolling/runtime.py` 的两级强杀与 `os._exit` 退役，改用同一阶梯。~~ 对象已删除。

第 1 步本身与本文的提案无关，**它仍然是一件待做的事**——`lifecycle.md:42` 要求 `start --systemd`，而 `src/app/cli.py` 至今只有 `--fd`，见 [existing-rulings.md](existing-rulings.md) 第二节。

# 候选：部署子系统的模块级补充材料

> 本文是候选素材，无效力。
>
> **本文主体已被 `docs/.human-controlled/lifecycle.md` 取代。** 那份文档已确立 `app.lifecycle` 的划分、部署方式、信号语义、相位定义与退出时限口径，均以它为准。
>
> 本文只保留 `lifecycle.md` 未涵盖、而实施时需要的模块级事实与当前状态。**已被推翻的旧内容（原退出时限公式 300+30）已删除**，其冲突登记在 [existing-rulings.md](existing-rulings.md) 的 C-1。
>
> **2026-08-22 更新**：rolling 已于 2026-08-19 整体删除，本文原有的 `app.lifecycle.rolling` 与 `.generation` 两张模块表、以及「当前未闭合项」一节随之全部失效，已撤下并各留一段记录。依据 `.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md`。

## 模块与职责对照（现状）

**搬迁已完成。** `lifecycle.md` 要求的 `app.lifecycle` 划分，以及 id 解析归跨域 `core/` 这一条（`lifecycle.md:3`），都已落地；下表是搬迁后的现状，不再是待办清单。

复算方式：`ls src/app/*.py` 现在只剩真正跨域的模块，`fd -e py . src/app/lifecycle` 给出本子系统的全貌（2026-08-22 为 11 个文件，含 `systemd/` 两个）。

### `app.lifecycle`（direct-run 一侧）

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `lifecycle/shutdown.py` | 信号到相位的阶梯本身：SIGINT/SIGTERM 各降一级，SIGUSR2 只开启下降 | `ShutdownStage`（`:32`）、`ShutdownLadder`（`:41`） |
| `lifecycle/listener.py` | 按 `SO_REUSEPORT` 自行绑定；`adopt_listener()`（`:54`）已实现但**暂无生产调用者** | `bind_listener`（`:79`）、`adopt_listener`、`FirstByteRoutingAdapter`（`:113`） |
| `lifecycle/standalone.py` | 驱动一个 listener 走完 serve 与三级关闭；启动失败时统一拆除 | `StandaloneServer`（`:107`）、`ShutdownReport`（`:92`） |
| `lifecycle/pidfile.py` | 供 `--restart` 找到前任；PID ＋ 启动时刻双重身份，经 `/proc/<pid>` 目录 fd 钉住后再校验、再发信 | `live_predecessor`（`:159`）、`signal_restart`（`:172`）、`write_entry`（`:100`）、`write_pidfile`（`:94`） |
| `lifecycle/entry.py` | direct-run 入口：绑定 → 服务 → 交接 | `StandaloneOptions`（`:42`）、`run_standalone`（`:70`） |

`cli.py` 的 `start` 走 `run_standalone`（`src/app/cli.py:184`），**但 `--fd` 例外**——它走 `serve_inherited`（`cli.py:136`），把 fd 交给 uvicorn 自己的 `Server.serve()`（经 `_DrainAnnouncingServer`，`cli.py:153-165`），因为 `run_standalone` 要拥有 listener 才能交接，而这条路径上 listener 归 systemd。

**注意与旧版本的差别**：本文早先写「`--fd` 仍走 `uvicorn.run`、服务旧链」。两点都已不对——它现在构造的是 `create_pipeline_app(chain)`（`cli.py:155`），即新处理链；用的也不是 `uvicorn.run` 而是 `uvicorn.Server.serve()` 的子类。三级阶梯是否适用于 systemd 路径已由 2026-08-17 裁决为**只做两级**，见 [existing-rulings.md](existing-rulings.md) 第三节 C-2 行，不再是待裁决项。

### 监听与进程接管（两种部署方式共用）

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `lifecycle/activation.py` | 解析 `LISTEN_PID` / `LISTEN_FDS` / `LISTEN_FDNAMES`，校验 fd 与期望监听地址族一致 | `ActivatedSocketSet`（`:32`）、`ExpectedListener`（`:16`）、`ListenerIdentity`（`:24`） |
| `lifecycle/adapter.py` | 拥有 Uvicorn 生命周期：以 `start_serving=False` 注册多 socket 后统一 arm；可停止 accept 而不关闭 master fd，并从同一 fd 恢复 | `UvicornListenerAdapter`（`:58`）、`ListenerState`（`:33`） |

它没有放进 `lifecycle/systemd/`：standalone 自行绑定 listener、用的是同一个类型，放进去会让 direct-run 反过来 import 一个与它无关的包。

### `app.lifecycle.systemd`

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `lifecycle/systemd/notify.py` | `sd_notify` 协议，支持 filesystem 与 abstract socket 两种路径 | `notify`（`:12`）、`notify_ready`（`:41`）、`notify_stopping`（`:45`） |
| `lifecycle/systemd/systemctl.py` | 收窄的 `systemctl` 调用面，按 generation id 推导 unit 名 | `SystemctlAdapter`（`:28`）、`UnitStatus`（`:14`）、`generation_unit()`（`:23`） |

`systemctl.py` 与 `notify.py` 都是 rolling 删除后**留下来的**：前者仍按 generation id 推导 unit 名（`generation_unit()`），而多代际编排本身已经没有了。2026-08-22 复算，两者都**无生产消费者**（`rg -ln 'systemd\.systemctl|SystemctlAdapter|generation_unit' src` 与 `rg -ln 'systemd\.notify|notify_ready|notify_stopping' src` 各只命中它们自己）。`notify.py` 是待接线而非待废弃——`lifecycle.md:42` 要求的 `start --systemd` 入口一旦建起来就需要它；`systemctl.py` 的去留可与 `shutdown.py` 一并考虑。

### `app.core`（跨域，按 `lifecycle.md:3` 不随 rolling 移动）

| 模块 | 职责 | 为什么留在 core |
|------|------|----------------|
| `core/generation_identity.py`、`core/release_identity.py` | id 解析与校验 | `src/app/tokenization/snapshot_store.py` 仍在解析 generation id；rolling 删除后，`rg -ln 'generation_identity\|release_identity' src` 只剩它与 `lifecycle/systemd/systemctl.py` 两个消费者。放在 rolling 下会让 tokenization 为读自己的快照名而依赖一个已经不存在的子系统 |

### 其余

| 现模块 | 说明 |
|--------|------|
| `graceful_timeout.py` | 仍在 `src/app/` 顶层；当前只有三个常量（`DEFAULT_GRACEFUL_TIMEOUT_SECONDS = 300` 等），其公式已被 `lifecycle.md:57-59` 推翻，见 C-1，未裁决前不动。它并非无消费者：`src/app/config/settings.py:8` 仍在导入 |
| `shutdown.py` | 仍在 `src/app/` 顶层；见下 |

## ~~当前未闭合项~~（2026-08-22 撤下）

原表列的四项——`apply` 闸默认关闭、真实 systemd manager 验证未完成、`feat/systemd-rolling-apply` 未并入 `main`、生产切换未执行——**前三项的对象已不存在**：rolling 于 2026-08-19 整体删除，`git ls-files src/app/lifecycle/rolling contrib/systemd/rolling` 输出为空，`RollingState`、`apply_blockers` 等符号一并消失。这三项不是「还没做完」，是「不做了」。

**第四项仍然成立**，但它不属于本文：生产切换（接管现有 `4141` 服务）需要用户单独的显式指令，当前状态记在 [pidfile-port-scoping.md](pidfile-port-scoping.md) 的「切换到新版本时的一次性影响」一节。

同时撤下的还有 `app.lifecycle.rolling` 与 `app.lifecycle.rolling.generation` 两张模块表（controller / state / frontier / runtime / phases / admission / control / control_client 共 8 个模块）。删除前的完整源码保存在归档分支 `archive/260819-rolling`，随时可取回；删除的经过与复活条件见 [rolling-removal.md](rolling-removal.md)。

## `shutdown.py` 的状态（现状）

`shutdown.py` 提供 `ShutdownPhase` 与四阶段的 `ShutdownManager`，**没有任何生产代码 import 它**（2026-08-22 复算：`rg -l 'app\.shutdown' src` 无命中），只有测试引用。关闭编排实际由两处承担：direct-run 一侧是 `lifecycle/standalone.py`，`--fd` 一侧是 `cli.py` 的 `_DrainAnnouncingServer` 加 uvicorn 自己的 graceful 收尾，其余走 lifespan。（原文这里写的第三处是 `lifecycle/rolling/runtime.py` 的 `shutdown()`，已随 rolling 删除。）

本文此前提出「它可能正是三级关闭的落点」，**实施时已核实为不成立**：`ShutdownManager.run()` 无条件顺序跑完全部四个阶段，没有信号输入、没有升级判断。而规格的三级阶梯里，第 2、3 级**只在操作者再次发信号时才发生**——一次正常关闭必须停在第 1 级、绝不中断请求。用它会让每次关闭都强行走到 ABORT 与 FORCE_CLOSE。

因此 `app.lifecycle.standalone` 另建了阶梯，未复用它。`shutdown.py` 仍未接线，**是否退役交用户判断**（依据既有裁决，不擅自删除已实现的功能）。这一条 2026-08-22 复核后仍然打开。

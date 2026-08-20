# 候选：部署子系统的模块级补充材料

> 本文是候选素材，无效力。
>
> **本文主体已被 `docs/.human-controlled/lifecycle.md` 取代。** 那份文档已确立 `app.lifecycle` 的划分、部署方式、信号语义、相位定义与退出时限口径，均以它为准。
>
> 本文只保留 `lifecycle.md` 未涵盖、而实施时需要的模块级事实与当前状态。**已被推翻的旧内容（原退出时限公式 300+30）已删除**，其冲突登记在 [existing-rulings.md](existing-rulings.md) 的 C-1。

## 模块与职责对照（现状）

**搬迁已完成。** `lifecycle.md` 要求的 `app.lifecycle.rolling`、`app.lifecycle.rolling.generation` 划分，以及 id 解析归跨域 `core/` 这一条，都已落地；下表是搬迁后的现状，不再是待办清单。

复算方式：`ls src/app/*.py` 现在只剩真正跨域的模块，`fd -e py . src/app/lifecycle` 给出本子系统的全貌。

### `app.lifecycle`（direct-run 一侧）

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `lifecycle/shutdown.py` | 信号到相位的阶梯本身：SIGINT/SIGTERM 各降一级，SIGUSR2 只开启下降 | `ShutdownStage`、`ShutdownLadder` |
| `lifecycle/listener.py` | 按 `SO_REUSEPORT` 自行绑定；`adopt_listener()` 已实现但**暂无生产调用者** | `bind_listener`、`adopt_listener` |
| `lifecycle/standalone.py` | 驱动一个 listener 走完 serve 与三级关闭；启动失败时统一拆除 | `StandaloneServer`、`ShutdownReport` |
| `lifecycle/pidfile.py` | 供 `--restart` 找到前任；PID ＋ 启动时刻双重身份，经 `/proc/<pid>` 目录 fd 钉住后再校验、再发信 | `live_predecessor`、`signal_restart`、`write_entry` |
| `lifecycle/entry.py` | direct-run 入口：绑定 → 服务 → 交接 | `StandaloneOptions`、`run_standalone` |

`cli.py` 的 `start` 走 `run_standalone`，**但 `--fd` 例外**——它仍走 `uvicorn.run`，因为三级阶梯是否适用于 systemd 路径是 [existing-rulings.md](existing-rulings.md) C-2 的待裁决项。

### 监听与进程接管（两种部署方式共用）

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `lifecycle/activation.py` | 解析 `LISTEN_PID` / `LISTEN_FDS` / `LISTEN_FDNAMES`，校验 fd 与期望监听地址族一致 | `ActivatedSocketSet`、`ExpectedListener`、`ListenerIdentity` |
| `lifecycle/adapter.py` | 拥有 Uvicorn 生命周期：以 `start_serving=False` 注册多 socket 后统一 arm；可停止 accept 而不关闭 master fd，并从同一 fd 恢复 | `UvicornListenerAdapter`、`ListenerState` |

它没有放进 `lifecycle/systemd/`：standalone 自行绑定 listener、用的是同一个类型，放进去会让 direct-run 反过来 import 一个与它无关的包。

### `app.lifecycle.systemd`

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `lifecycle/systemd/notify.py` | `sd_notify` 协议，支持 filesystem 与 abstract socket 两种路径 | `notify`、`notify_ready`、`notify_stopping` |
| `lifecycle/systemd/systemctl.py` | 收窄的 `systemctl` 调用面，按 generation id 推导 unit 名 | `SystemctlAdapter`、`UnitStatus`、`generation_unit()` |

### `app.lifecycle.rolling.generation`

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `.../generation/phases.py` | 相位迁移的唯一 owner、health gating、观察者协议 | `GenerationPhase`、`GenerationLifecycle`、`GenerationSnapshot` |
| `.../generation/admission.py` | 准入闸：拒绝时回 503／WS 1012，health 探针始终放行 | `GenerationAdmissionMiddleware` |
| `.../generation/control.py` | generation 本地的 UDS 控制面服务端 | `GenerationControlServer` |
| `.../generation/control_client.py` | 控制面客户端，含严格 framing/schema 与全链路 deadline | `GenerationControlClient`、`GenerationStatus`、`TokenizationFlushReceipt` |

准入从原 `generation.py` 拆出，因为规格把「相位生命周期」与「准入」列为两件事，且两者问的问题不同：前者决定这一代愿意做什么，后者决定答案为否时对来访请求说什么。

### `app.lifecycle.rolling`

| 模块 | 职责 | 关键符号 |
|------|------|----------|
| `lifecycle/rolling/controller.py` | 编排替换：分配 id、渲染并启动 unit、推进或回退 | `RollingController`、`DryRunPlan`、`plan_to_json()` |
| `lifecycle/rolling/state.py` | 控制器侧持久状态：单调 revision、committed generation/release、各代记录 | `RollingStateStore`、`RollingState`、`GenerationRecord` |
| `lifecycle/rolling/frontier.py` | 单调 id 前沿，保证 generation id 不重复分配 | `RollingFrontierStore` |
| `lifecycle/rolling/runtime.py` | generation 进程侧入口与编排 | `RollingRuntime`、`run_systemd_generation()` |

### `app.core`（跨域，按 `lifecycle.md:3` 不随 rolling 移动）

| 模块 | 职责 | 为什么不在 rolling 下 |
|------|------|---------------------|
| `core/generation_identity.py`、`core/release_identity.py` | id 解析与校验 | `tokenization/snapshot_store.py` 也解析 generation id；放在 rolling 下会让 tokenization 为读自己的快照名而依赖滚动更新子系统 |

### 其余

| 现模块 | 说明 |
|--------|------|
| `graceful_timeout.py` | 仍在 `src/app/` 顶层；当前只有三个常量，其公式已被 `lifecycle.md` 推翻，见 C-1，未裁决前不动 |
| `shutdown.py` | 仍在 `src/app/` 顶层；见下 |

## 当前未闭合项（现状）

| 项 | 状态 | 复算方式 |
|----|------|---------|
| `apply` 闸 | **默认关闭** | `RollingState.apply_enabled = False`；`apply_blockers` 列四项：缺私有 canary 命令、缺快照隔离契约、缺 promote/demote 命令、闸门本身未开放 |
| 真实 systemd manager 验证 | **未完成** | 需具备独立 user manager 与 delegated cgroup v2 的可销毁环境 |
| 完整 replace apply | **未并入 `main`** | `git rev-list --count main..feat/systemd-rolling-apply` = 14 |
| 生产切换 | **未执行** | 现有 `4141` 服务未被接管 |

## `shutdown.py` 的状态（现状）

`shutdown.py` 提供 `ShutdownPhase` 与四阶段的 `ShutdownManager`，**没有任何生产代码 import 它**（`rg -l 'app\.shutdown' src` 无命中），只有两个测试引用。关闭编排实际由三处承担：direct-run 一侧是 `lifecycle/standalone.py`，systemd 一侧是 `lifecycle/rolling/runtime.py` 的 `shutdown()`，其余走 `server.py` 的 lifespan。

本文此前提出「它可能正是三级关闭的落点」，**实施时已核实为不成立**：`ShutdownManager.run()` 无条件顺序跑完全部四个阶段，没有信号输入、没有升级判断。而规格的三级阶梯里，第 2、3 级**只在操作者再次发信号时才发生**——一次正常关闭必须停在第 1 级、绝不中断请求。用它会让每次关闭都强行走到 ABORT 与 FORCE_CLOSE。

因此 `app.lifecycle.standalone` 另建了阶梯，未复用它。`shutdown.py` 仍未接线，是否退役交用户判断（依据既有裁决，不擅自删除已实现的功能）。

# 候选：`lifecycle.md` 的「代（generation）生命周期」一节需要修订

> 本文是候选素材，无效力。用户已于 2026-08-19 裁决删除该功能并表示「当你纠正代码后，用户会重新『追认』删除」，本文即供那次追认使用。
>
> 权威文档 `docs/.human-controlled/lifecycle.md` 由用户亲笔，本文不修改它。

## 一、发生了什么

用户裁决：**保留优雅退出与无缝重启，不再提供回退机制。** 代码已按此删除。

删除的判断依据是：`lifecycle.md` 定义的相位机里，`DRAINED_STANDBY` 加上 `RESUME`（从同一 fd 恢复）**就是**回退——留一个已停止 accept 但保住 listener 的旧代际待命，新代际不行就恢复它。去掉这一能力后，相位塌缩为 `STARTING → READY_ACCEPTING → QUIESCING → STOPPING`，而这正是 `app.lifecycle.standalone` 的 `run_standalone` 已经实现的东西，于是整套多代际编排失去存在理由。

## 二、已删除的内容

| 路径 | 行数 |
|---|---:|
| `src/app/lifecycle/rolling/`（controller / runtime / state / frontier / generation×4） | 2133 |
| `contrib/systemd/rolling/`（v4/v6 socket、generation@、controller、slice、target、launcher） | 7 个文件 |
| CLI 命令 `start-rolling`、`rolling-controller` | — |
| 相关测试（10 个文件整删 ＋ 3 处局部） | 约 3600 |

连带清理的接线：`RuntimeState.generation_lifecycle`、`HistoryStore(generation_lifecycle=...)`、`create_app(generation_lifecycle=...)`、`/health/readiness` 的 `generation` 字段。

**归档分支 `archive/260819-rolling`**（指向 `a8a7f87`）保存了删除前的完整源码，可随时取回。

## 三、保留的内容（用户要的两件事）

- **优雅退出**：`app.lifecycle.standalone` 的分级关闭。systemd 路径按 2026-08-18 裁决为两级。
- **无缝重启**：`app.lifecycle.pidfile` 的 pidfd 钉进程 ＋ `app.lifecycle.listener` 的 SO_REUSEPORT 接管，共 893 行，`start` 正在使用。
- **socket 激活**：`contrib/systemd/ghc-api-proxy.socket` ＋ `--fd`，保住 listener 与已排队未 accept 的连接。

## 四、建议对 `lifecycle.md` 的修订

「### 代（generation）生命周期」整节（含相位图、`QUIESCE`/`RESUME`/`TERMINATE` 语义、`DRAINED_STANDBY` 的 durability barrier、模块划分建议）已无对应实现，建议删除或改写为历史记录。

若改写为历史记录，建议保留该节 2026-08-16 的那句原话——它解释了这套东西为何存在过：

> 整个「代生命周期」与「滚动更新」的概念是对已经实现的功能的「追认」，该模块并非由用户设计，是 agent 拓展的功能。

并补一句 2026-08-19 的处置：功能已删除，归档分支为 `archive/260819-rolling`。

## 五、复活条件（若将来需要）

删除的是「多代际并存 ＋ 回退」，不是「无缝重启」。以下情形才需要重新考虑它：

1. 要做到**迁移已被旧进程接受的连接**——这需要 fd 传递，是比原实现更大的工程，而 `MAIN.md` 现记「must not be described as full zero-downtime migration」。
2. 多机部署，需要跨实例编排。
3. 新版本启动期（实测约 14 秒拉取模型目录）的排队变得不可接受。当前形态下 socket 激活会把连接排住而非拒绝，单用户量级下这是可接受的。

## 六、连带效应：旧链已无生产入口

`start-rolling` 是 `cli.py` 里最后一个 `create_app` 的调用者。删除后：

- `start`（直接运行）→ `create_pipeline_app`
- `--fd`（systemd）→ `create_pipeline_app`
- **旧链 `create_app` 已无任何生产入口**，仅被测试引用。

这解开了此前一直阻塞的事项：可以按角色重排目录，且旧链具备退役条件。退役本身是另一次裁决，本文不代为决定。

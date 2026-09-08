# systemd cgroup runtime 独立定向终审 R4

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-systemd` 分支 `feat/systemd-cgroup-runtime`、最终 HEAD `49fb1988621bba4356e7a5039a6994c2e6d19604` 相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的最终合并态。精确线性范围为 `66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`、`1a220e04a99c6ce07b4bdd6bb0876b4180d4c489`、`49fb1988621bba4356e7a5039a6994c2e6d19604` 三提交。定向终审权限修复、`StateDirectory`、`Type=exec`／`KillMode=control-group`、fd 下界、真实 inherited fd／readiness／tokenization／EnvironmentFile 等价覆盖／History／SIGTERM smoke；未安装、启用、启动、停止、restart 或 reload 任何 system unit，未操作生产 `4141` listener，也不把真实 manager／cgroup 生效或 rolling 纳入本轮回并门。
- **总体 verdict**：**可进入下一阶段**。最终 HEAD 未发现 blocker 或 major；R2 权限 major 已关闭，R3 的运行态覆盖结论在最终 bytes 上成立。精确三提交范围 **`66551e45… → 1a220e04… → 49fb198…` 可 squash 回并**。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **双视角覆盖证据——机械核对**：固定并重复验证目标物理 root、branch、最终 HEAD、base、线性三提交数与 clean worktree；完整读取最终 CLI、CLI 单测、service／socket／slice、systemd smoke、部署 README；对账 R3 的每项事实而不沿用其 verdict；用 systemd 255 的 `systemd-analyze verify` 解析三个原始 unit，唯一诊断是模板约定但本机未安装的 `/opt/ghc-api-proxy/.venv/bin/python`，无 unit 语法或字段诊断；定向 CLI＋systemd suite 中前 16 项完成后最后一项受共享终端外部 `Ctrl-C` 中断，该最后一项随后在正确 import oracle 下独立完整通过，因此定向 17 项均有完成证据；全仓 Ruff 为 `All checks passed!`，全仓 Pyright 为 `0 errors, 0 warnings, 0 informations`，聚合 diff 与最终提交 diff 均通过 `git diff --check`，验证后目标树保持 clean。
- **双视角覆盖证据——第一人称执行**：模拟管理员从旧宽权限模板升级、使用默认状态路径、用 EnvironmentFile 同名变量覆盖默认路径、无可写 HOME、在应用启动前向 listener 建立 backlog 连接、经 fd 3 启动真实 CLI／Uvicorn、等待 generic upstream 模型刷新后读取 readiness 200、发送真实 `/v1/messages` 请求、观察 History 与 tokenization 文件写入覆盖目录，再向进程发送 SIGTERM 并确认 FastAPI lifespan shutdown 日志。另按日常仅 restart service 与误停 socket 两条路径检查文档边界，确认其没有把 backlog 保护写成 rolling 或已 accept 长连接迁移。

## 事实性发现

[minor] `docs/agents/deployment-systemd/README.md:46` — 文档把机密 token 经 `EnvironmentFile=` 提供描述为可用方案，但 systemd 255 `systemd.exec(5)` 明确说明环境变量不适合传递 secrets，并推荐 `LoadCredential=`／`LoadCredentialEncrypted=` — 文件权限限制不能消除 unit 环境经 D-Bus 或进程树暴露的边界；该问题不影响本轮 socket activation、状态权限、readiness、History／tokenization 落盘、SIGTERM 或 cgroup 声明，因此不阻断 squash — 后续把该句改为“兼容但不推荐”，优先让已有 `auth.token_file` 消费 systemd credential 路径并给出 `LoadCredential=` 示例。

未发现阻断性问题；未发现 major。候选明确可 squash 回并。

## 目标合同确认

- **权限修复与 StateDirectory**：`contrib/systemd/ghc-api-proxy.service:13-17` 使用 `StateDirectory=ghc-api-proxy`、`StateDirectoryMode=0700`、`UMask=0077`，并先给出两条默认状态路径、后加载可选 EnvironmentFile。`tests/smoke/test_systemd_units.py:142-208` 以 unit 声明值作用于真实 `HistoryWriter` 与 `TokenizationStateStore`，断言目录 `0700`，SQLite DB／WAL／SHM、tokenization 临时文件与最终文件均为 `0600`。部署 README 已说明 umask 不会递归收紧既有文件，升级和覆盖目录仍须由管理员核对。
- **Type、control group 与关闭合同**：`contrib/systemd/ghc-api-proxy.service:9,21-24` 固定 `Type=exec`、`KillSignal=SIGTERM`、`KillMode=control-group`、`TimeoutStopSec=330s` 和专属 slice。仓库 smoke 证明应用侧 SIGTERM 清理，不外推为真实 manager 对 main＋child cgroup 的广播或超时 SIGKILL 已验证。
- **fd 下界与接线**：`src/app/cli.py:53,79,114` 将 `--fd` 下界固定为 1，拒绝 fd 与 host／port 混用，并把 fd 传给 Uvicorn；`tests/unit/test_cli.py:105-142` 覆盖 fd 3、fd 0 拒绝和 bind 参数冲突。service 的 `ExecStart` 在 `contrib/systemd/ghc-api-proxy.service:18` 使用 `--fd 3`。
- **真实 fd 与 backlog**：`tests/smoke/test_systemd_units.py:227-338` 由父进程建立真实 TCP listener，在应用启动前建立 backlog 连接，再把 listener 复制为 fd 3 并启动真实 CLI／Uvicorn；预连接随后从 `/health/liveness` 得到 200。这证明应用侧 inherited fd 与预连接 backlog 接缝，不证明真实 systemd fd metadata 或跨 restart listener identity。
- **readiness 与真实上游路径**：同一 smoke 连接受控 generic upstream，先完成 `/v1/models` 刷新，再从继承 listener 的 `/health/readiness` 得到 200，并经生产 `/v1/messages` 路径让 upstream 收到真实请求且返回 `msg_smoke`。
- **EnvironmentFile 等价覆盖**：smoke 先注入 unit 默认路径，再用同名环境变量覆盖到独立目录；`src/app/config/loader.py:65-83` 的应用配置优先级为 defaults < YAML < environment < CLI。最终 History 与 tokenization 文件只出现在覆盖目录，默认目录未被误写。systemd 255 手册确认 unit 中后出现的 `EnvironmentFile=` 同名值覆盖 `Environment=`；真实 manager 解析仍留给安装态 gate。
- **History、tokenization 与 SIGTERM**：`tests/smoke/test_systemd_units.py:302-328` 断言 readiness、真实消息响应、SIGTERM、`Application shutdown complete.`、History 文件、tokenization 文件和默认目录未写。`src/app/server.py:132-151` 的 lifespan cleanup 刷新 tokenization、关闭 History 和 upstream。测试当前只把文件存在性作为落盘断言；生产调用链检查确认真实 Anthropic response usage 会标脏 calibration，但本轮受共享终端干扰的额外“解码产物内容”探针未完成，因此不把具体 SQLite 行与 calibration payload 内容外推为新增已验证合同。
- **unit 解析**：本机 systemd 255 对最终三个原始模板执行 `systemd-analyze verify`，退出码 1 且恰有一条诊断：`/opt/ghc-api-proxy/.venv/bin/python` 不存在。该路径属于模板安装前提；没有 unit 语法、依赖、`StateDirectoryMode=`、`UMask=`、`Type=`、`KillMode=` 或 slice 字段诊断，目标机安装后仍须重跑。

## 测试证据边界

- 定向 `tests/unit/test_cli.py tests/smoke/test_systemd_units.py` 的一次运行完成前 16 项，最后的真实进程 smoke 被共享终端外部 `Ctrl-C` 中断；该最后一项随后独立运行并以 `1 passed`、退出码 0 完成，import oracle 为 `/home/xp/src/ghc-api-proxy-py-systemd/src/app/__init__.py`，所以目标清单对应的定向测试均有完成证据。
- 全仓 Ruff 与 Pyright 在最终 HEAD 上完整以 0 退出；目标树验证后保持 clean。
- 全仓 pytest 在本轮多次被同一共享终端的其他任务注入 `Ctrl-C`，均未完成，因此本报告**不声称本轮全仓 pytest 通过**。一次尝试误用了不带 `--wait` 的 `setsid`，父 shell 在 pytest 尚未完成时提前返回 0；该假绿已明确废弃，不作为证据。R3 曾报告全仓 pytest 通过，但本轮只把它当上轮声称，不冒充独立复验结果。
- 本轮按用户要求保持目标树只读，没有做源码变异 positive control；因此不声称现有测试对每一种目标缺陷都具备已实证的变异判别力。真实 listener／CLI／Uvicorn／upstream／state writer／SIGTERM 路径、官方 systemd 语义和代码调用链共同提供交叉证据。

## 结构怪味扫描与处置

- `contrib/systemd/ghc-api-proxy.service:13-17` — **状态目录名与两条绝对状态路径重复表达** — 本轮不改，已有静态配置测试、环境消费测试与覆盖路径 smoke 守护；后续可评估 systemd 的 `$STATE_DIRECTORY`，但须先验证 unit 环境展开和最低 systemd 版本。
- `tests/smoke/test_systemd_units.py:227-338` — **EnvironmentFile 行为以等价环境合并模拟，未经过真实 manager** — 本轮用 systemd 255 手册顺序作为独立 oracle，并把真实 manager 解析留在安装态 gate；不把模拟测试写成安装态证据。
- `tests/smoke/test_systemd_units.py:142-208` — **权限测试在进程内施加 unit 声明的 umask，未经过真实 manager** — 被测边界明确为“声明值作用于真实 writers 后的 mode”；manager 是否施加仍在后续部署验收，不阻断仓库骨架回并。
- `contrib/systemd/ghc-api-proxy.service:18` — **裸 fd 3 与单一 activation socket 顺序耦合** — 当前仅一个 socket，CLI 与真实 fd smoke 已闭合；若未来增加第二 listener，必须引入 `LISTEN_PID`／`LISTEN_FDS`／`LISTEN_FDNAMES` 数量与名称校验，本轮不提前扩大实现。

## 主观建议

[建议] `docs/agents/deployment-systemd/README.md:46` — 将 secret 传递从普通 EnvironmentFile 逐步迁移到 systemd credentials — 预期减少 token 经 unit 环境、D-Bus 或进程树暴露的风险 — 复用已有 `auth.token_file`，提供 `LoadCredential=`／`LoadCredentialEncrypted=` 示例，并将 EnvironmentFile 保留为明确标风险的兼容路径。

[建议] 后续隔离 systemd 环境 — 增加真实 manager 的 fd metadata、service restart listener identity、main＋child control-group 信号与资源限制测试 — 预期把当前“unit 语义＋应用侧真实进程 smoke”提升为安装态证据 — 使用备用 loopback 端口与临时 unit，不操作生产 `4141`；rolling 继续作为独立切片，不反向扩大本轮 squash 门。

## 结论

`feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 在相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的定向范围内为 **`0 blocker／0 major`**。权限 fix、`StateDirectory`、`Type=exec`／`KillMode=control-group`、fd >= 1、真实 fd／backlog、readiness 200、EnvironmentFile 等价覆盖、History／tokenization 文件落盘和 SIGTERM 应用侧清理均已确认。credentials 文档问题保留为 1 项非阻断 minor。精确三提交范围 **`66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`＋`1a220e04a99c6ce07b4bdd6bb0876b4180d4c489`＋`49fb1988621bba4356e7a5039a6994c2e6d19604` 明确可 squash 回并**；该 verdict 不授权安装 unit、改变 manager 状态或切换生产 `4141`。

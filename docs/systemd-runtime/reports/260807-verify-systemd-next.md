# systemd-next 独立验收

- **总体判定**：**PASS**。
- **验收对象**：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-next` 的 `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b`，精确 base 为 `80bc8f252b46c511f428af1d97159a5980ee9dc9`。目标是线性两提交：`91f95f7d30c0b399eef98d997c0f88f57c2d0284 feat: configure graceful shutdown timeout` 与 `0a93e7f18f197bf8a2395eaaf20afda446f92d6b feat: add rootless systemd user installer`。
- **Oracle**：本次用户指定范围，以及 `docs/agents/systemd-runtime/plan.md` 的 S3 graceful timeout 与 S4 rootless installer 合同。先据此形成验收矩阵，再读取实现与已有测试。
- **只读边界**：未修改 target worktree，验证前后 target 均为 clean；未安装 unit，未连接或改变真实 user／system manager，未调用 `systemctl`，未占用或修改生产 `4141`，未触碰 `cc-daemon`。所有 installer apply、unit 文件和 systemd verify 输入均位于自动回收的临时目录。主树唯一写入为本报告。
- **结论边界**：本 PASS 只覆盖用户本次点名的 CLI／config graceful timeout 到 Uvicorn 接线、system／user unit 严格 timeout 余量、短 timeout SIGTERM cleanup、installer dry-run／apply／幂等／零 `systemctl` 和 `systemd-analyze`。它不表示真实 user manager activation、effective cgroup、双 fd／双栈、unit 安装、部署、`localhost:4141` cutover、rolling 或完整产品 P1 已通过。

## 验收矩阵与结果

| ID | 从 Oracle 独立推导的用户可观察判据 | 实际结果 |
|---|---|---|
| SYS-NEXT-01 | YAML、环境变量与 CLI 按正常优先级解析 graceful timeout；最终值必须进入 Uvicorn 的 `timeout_graceful_shutdown`，host／port 与 inherited-fd 两条启动分支均不能丢失该值 | **PASS**。独立 probe 使用 YAML `11`、环境变量 `12`、CLI `13`，观察到 settings 与 Uvicorn 实收均为 `13`。既有 CLI／config 定向 suite 同时通过。 |
| SYS-NEXT-02 | system unit 与 installer 渲染的 user unit 都必须满足 `TimeoutStopSec > --graceful-timeout`，并保持明确的 manager 余量；相等必须失败 | **PASS**。独立解析 system 与 user service 均得到 application `300s`、manager `330s`、余量 `30s`。正控把 system unit 临时变异为 `300s／300s` 后，验收器以 `manager deadline must strictly exceed app timeout` 的目标原因变红。 |
| SYS-NEXT-03 | 低 timeout 的真实 CLI／Uvicorn 进程收到 SIGTERM 后，阻塞中的真实请求进入 Uvicorn timeout 分支，随后仍执行 FastAPI lifespan cleanup，并在有界时间内退出 | **PASS**。隔离执行 `tests/smoke/test_systemd_units.py::test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan`，pytest 返回 `PASSED`、退出码为零；该测试用真实 listener、受控 upstream 和真实子进程验证日志同时出现 `timeout graceful shutdown exceeded`、`Application shutdown complete.` 与 `Finished server process`，并要求从 SIGTERM 到退出小于 `8s`。 |
| SYS-NEXT-04 | installer 默认 dry-run／`--check` 不得创建 XDG config／state 持久目录或 unit 文件，不得调用 `systemctl` | **PASS**。独立黑盒 probe 在全新临时 HOME／XDG 根运行真实 helper；完成真实 `systemd-analyze --user verify` 后，config／state 根仍不存在，捕获的 `systemctl` 调用数为零。 |
| SYS-NEXT-05 | 显式 `--apply` 只写 `.service`、`.socket`、`.slice` 三份 user unit；重复 apply 相同 bytes 必须幂等，不重写 mtime；所有路径仍不得调用 `systemctl` | **PASS**。独立 probe 观察到精确三份 `0644` 文件；重复 apply 报告三次 `UNCHANGED`，bytes 与 `st_mtime_ns` 均不变，`systemctl` 调用数保持零。 |
| SYS-NEXT-06 | system unit 与渲染 user unit 均须通过 `systemd-analyze`；system 模板允许仅为安装前绝对路径制作受控副本，不得屏蔽其他诊断 | **PASS**。user unit 由 helper 直接执行真实 `systemd-analyze --user verify` 通过；system unit 临时副本只把未安装的账户／工作目录／`ExecStart` 前置替换为本机存在值，其余 socket／service／slice 内容保持候选语义，真实 `systemd-analyze verify` 退出码为零。 |

## 实际执行证据

### 定向 suite

- 执行入口：目标树 import oracle 固定为 `/home/xp/src/ghc-api-proxy-py-integrate-systemd-next/src/app/__init__.py`。
- 范围：`tests/unit/test_cli.py`、`tests/unit/test_config_loader.py`、`tests/smoke/test_systemd_units.py`、`tests/smoke/test_systemd_user_install.py`。
- 结果：pytest 退出码为零，日志摘要为 `33 passed in 15.25s`。
- 日志：`/tmp/verify-systemd-next-targeted-0a93e7f.log`，SHA-256 `8f3178602ba981aefd84d5bee920e091f6d87aa0c63e003a68eb93849280c867`。
- 说明：更早一次共享终端执行被外部并发输出与 `Ctrl-C` 污染，已明确丢弃，未作为验收证据；上述专属日志来自后续隔离重跑。

### 独立黑盒 probe 与正控

- 验收脚本：`/tmp/verify_systemd_next_0a93e7f.py`，SHA-256 `0d2cc5252ff288c66a8d8ef390dae3e9b4479956a3f7abc47eadc3fcc5b18f8a`。
- 结果日志：`/tmp/verify-systemd-next-independent-0a93e7f-v2.log`，SHA-256 `58a550fe5cb93082d42aef6513647aa2522ae1ec44911ae51dd964064f67bf2b`。
- 关键输出：`PASS CLI_CONFIG_UVICORN yaml=11 env=12 cli=13 uvicorn=13`；`PASS SYSTEM_TIMEOUT app=300 manager=330 margin=30`；`PASS POSITIVE_CONTROL timeout_drift_rejected`；`PASS INSTALLER_DRY_RUN persistent_writes=0 systemctl_calls=0 systemd_analyze=user-pass`；`PASS USER_TIMEOUT app=300 manager=330 margin=30`；`PASS INSTALLER_APPLY files=3 modes=0644 repeat_mtime_unchanged=yes systemctl_calls=0`；`PASS SYSTEMD_ANALYZE system=pass user=pass`；最终 `VERDICT PASS`。
- 执行后 target 仍为精确 HEAD 且 clean。

### 短 timeout SIGTERM 单项复验

- 命令范围：`tests/smoke/test_systemd_units.py::test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan`。
- 结果：pytest 收集并执行该单项，退出码为零，输出 `PASSED`。
- 日志：`/tmp/verify-systemd-next-short-timeout-0a93e7f.log`，SHA-256 `f0a293758fca106e92ce82d2cc06a0d99b219604a032073e7a6e7ac0a508b81b`。

## 缺陷与未验证项

- 本次指定验收范围内未发现偏差，因此没有需要交回 debugger 或 implementer 的失败复现。
- **未验证**：真实 user manager activation、manager 实际发送 SIGTERM／SIGKILL 的完整生命周期、effective cgroup limits、双具名 fd／IPv4＋IPv6、生产 unit 安装和 `4141` cutover。这些不属于本次点名范围，不能由本报告的 PASS 外推。

## 最终判定

`systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b` 相对 `base@80bc8f252b46c511f428af1d97159a5980ee9dc9` 在本次指定范围内 **PASS**。timeout drift 正控按目标机制变红，恢复到候选 bytes 后独立验收全绿；target worktree 验证前后保持 clean。

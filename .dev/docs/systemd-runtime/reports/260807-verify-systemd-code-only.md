# systemd-code-only 独立验收

- **候选**：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-code`，`integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316`。
- **base**：`80bc8f252b46c511f428af1d97159a5980ee9dc9`；候选是 base 后的两提交线性栈。
- **行为 oracle**：`docs/agents/anthropic-responses-bridge/spec.md` SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，其中 Shutdown 条款要求 grace window 内 drain，超过 deadline 后取消 upstream、关闭资源、清理未提交状态并以 aborted／failed finalize。
- **范围**：只验收 graceful CLI／config precedence、system／user unit 的 `300s／330s` deadline、短 deadline 下 SIGTERM cleanup、rootless installer 的 dry-run／apply／幂等／零 `systemctl`、systemd unit 静态 verify、Plan bytes 不变与 deadline drift 正控。不验收真实 systemd manager activation、安装态、cgroup effective limits、生产端口或 cutover。
- **总体判定**：**PASS**。本轮范围内所有正确样本均通过，四个 deadline drift 单侧缺陷均按目标原因被判据捕获，恢复后重新为绿；未发现违反本轮冻结合同的用户可观察缺陷。

## 验收矩阵

| 验收项 | 独立判据与实际结果 | 判定 |
|---|---|---|
| graceful CLI／config precedence | 通过真实 Typer `start` 入口并在 Uvicorn 调用边界观测，依次得到 default `300`、YAML `11`、environment `12`、CLI `13`；顺序固定为 default < YAML < environment < CLI，最终分别传入 `timeout_graceful_shutdown=300／11／12／13`。既有回归接缝见 `tests/unit/test_cli.py:88-137` 与 `tests/unit/test_config_loader.py:92-109`。 | PASS |
| system unit `300／330` | 独立解析仓库 system service，得到 `ExecStart ... --graceful-timeout 300`、`TimeoutStopSec=330s`，并断言 manager deadline 严格大于 app deadline且余量恰为 `30s`。使用临时副本只替换未安装环境中的 `/opt` 路径和 system account 为当前可解析值后，真实 `systemd-analyze verify` 返回 0；原模板 bytes 未被修改。既有回归接缝见 `tests/smoke/test_systemd_units.py:246-267`。 | PASS |
| user unit `300／330` | 通过真实 installer 渲染 user service，独立解析得到 app `300s`、manager `330s`、余量 `30s`，且不含 `User=`／`Group=`；真实 `systemd-analyze --user verify` 返回 0。 | PASS |
| short SIGTERM cleanup | 真实 CLI→Uvicorn→ASGI lifespan 路径以 inherited listener 启动隔离 local process，以 `--graceful-timeout 1` 阻塞真实在途请求后发送 SIGTERM。定向测试 `tests/smoke/test_systemd_units.py::test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan` 为 `1 passed in 4.14s`；断言进程在 `8s` 内退出，并观察到 `timeout graceful shutdown exceeded`、`Application shutdown complete.` 与 `Finished server process`。fake upstream 随后写已取消连接得到 `BrokenPipeError`，与应用已关闭上游连接的预期一致。精确断言见 `tests/smoke/test_systemd_units.py:387-481`。 | PASS |
| installer dry-run | 在自动清理的临时 HOME／XDG 根运行 `--check`，输出 `DRY-RUN`，未创建 user unit 目录或 state 根，未调用 `systemctl`；真实 `systemd-analyze --user verify` 通过。 | PASS |
| installer apply／幂等 | `--apply --check` 只在临时 `$XDG_CONFIG_HOME/systemd/user/` 写入精确三个 unit；第二次 `--apply` 三项均报告 `UNCHANGED`，bytes 与 `mtime_ns` 均未变化；两次均零 `systemctl` 调用。既有回归接缝见 `tests/smoke/test_systemd_user_install.py:81-151`。 | PASS |
| systemd analyze | 环境为 `systemd 255 (255.4-1ubuntu8.16)`；system 临时可解析副本执行 `systemd-analyze verify` 返回 0，installer 真实渲染结果执行 `systemd-analyze --user verify` 返回 0。该证据只证明 unit 语法与静态引用可验证，不冒充 manager activation 或安装态。 | PASS |
| Plan bytes 未改变 | `docs/agents/systemd-runtime/plan.md` 在 base、candidate HEAD 与 candidate worktree 的 Git blob 均为 `ae73fdf88e104ff1f256e47fb8a51a02713a9834`；`git diff --exit-code base HEAD -- <Plan>` 返回 0。Plan SHA-256 为 `6646cb727e1bc92ce02ec2bd76f825bb8c9b7d190dbd907ed9f9a6e776f156e6`，由 `sha256sum` 与 Python `hashlib` 两种实现交叉复核。 | PASS |
| deadline drift 正控 | 在内存中的 system／user service 副本分别单侧注入四个缺陷：app `300→301`、manager `330→329`。同一独立判据分别捕获 `system-app-301`、`system-stop-329`、`user-app-301`、`user-stop-329`；没有依赖产品测试 helper 生成 expected。恢复原始文本后 system／user 两个正确样本重新为绿。 | PASS |

## 实际执行与证据

### 独立 harness

- **入口**：`/tmp/verify_systemd_code_only_260807.py`，只读候选；installer apply 仅写自动清理的临时目录。
- **日志**：`/tmp/verify-systemd-code-only-final-0d7a.log`，SHA-256 `55d8ec75bf6a7b90d1bb3c4b30f0f514b9a795c9f744f1ada5880c29d54e2276`。
- **身份门**：日志绑定物理 root `/home/xp/src/ghc-api-proxy-py-integrate-systemd-code`、branch `integrate/260807-systemd-code-only`、HEAD `2ec0cb81832691685bfe8d98ad03071d2d5e5316`、base `80bc8f252b46c511f428af1d97159a5980ee9dc9`、clean worktree，并证明运行时加载 `.../ghc-api-proxy-py-integrate-systemd-code/src/app/__init__.py`。
- **结果**：`HARNESS_RC_SYSTEMD_CODE_ONLY_FINAL_PROBES_260807_0D7A=0`；日志逐项记录 `PLAN_UNCHANGED_PASS`、`PRECEDENCE_PASS`、`SYSTEM_UNIT_PASS`、`INSTALLER_PASS`、`USER_UNIT_PASS`、`DEADLINE_DRIFT_POSITIVE_CONTROL_PASS` 与 `OVERALL_PROBE_PASS`。

### short SIGTERM

- **入口**：固定候选下运行单一测试 `tests/smoke/test_systemd_units.py::test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan`，使用 candidate `src` 的绝对 `PYTHONPATH` 与固定解释器 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python`。
- **结果**：`1 passed in 4.14s`，`SIGTERM_RC_SYSTEMD_CODE_ONLY_FINAL_PROBES_260807_0D7A=0`；候选 HEAD 前后不变且 worktree 干净。

### 补充回归证据

- 同一候选的四个相关测试文件曾在独立输出日志 `/tmp/systemd-code-only-targeted-2ec0cb8.log` 中得到 `33 passed in 9.46s`。
- 同一候选的全仓旁证日志为 `/tmp/systemd-code-only-full-2ec0cb8.log`，结果 `440 passed in 14.09s`；collect-only 日志独立列出 `440 tests collected`，Ruff 为 `All checks passed!`，Pyright 为 `0 errors, 0 warnings, 0 informations`。这些结果用于回归旁证，不替代上面的独立行为 harness 与 drift 正控。

## 副作用与未验证边界

- 未复制 unit 到真实 `~/.config/systemd/user` 或 `/etc/systemd/system`，未执行 `daemon-reload`、enable、start、restart、stop，未连接或修改 system／user manager 状态，未占用生产 `4141`，未触碰现有服务或 `cc-daemon`。
- 为满足 short SIGTERM 验收，测试仅直接启动了一个隔离 local application process 和临时 fake upstream，并在测试结束时关闭；这不是 systemd unit 启动或安装。
- installer 的显式 apply 仅发生在 `TemporaryDirectory` 下的隔离 `$XDG_CONFIG_HOME`，临时目录退出时自动清理。
- 真实 systemd manager fd activation、service cgroup、effective limits 与生产部署不在本轮授权及 PASS 范围内，保持未验证，不影响本次 systemd-code-only 范围判定。

## 缺陷

无。本轮没有可复现的 Spec 偏差，因此没有需要交回 debugger／implementer 的生产缺陷。

## 最终结论

`integrate/260807-systemd-code-only@2ec0cb81832691685bfe8d98ad03071d2d5e5316` 相对 base `80bc8f252b46c511f428af1d97159a5980ee9dc9` 在用户指定的 systemd-code-only 验收范围内为 **PASS**。Plan bytes 未改变；system／user deadlines、配置 precedence、短 SIGTERM cleanup、rootless installer 惰性与幂等性、零 `systemctl`、真实静态 verify 和 deadline drift 判据均取得可复现实证。该 PASS 不表示已安装、已启动 systemd unit、已验证真实 manager／cgroup或已获部署／cutover授权。

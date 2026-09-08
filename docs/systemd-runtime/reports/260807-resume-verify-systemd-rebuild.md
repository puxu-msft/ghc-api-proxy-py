# Systemd S3＋S4 new-main rebuild 独立验收

## 判定

**PASS。** 验收对象为只读 worktree `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume` 的 `integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54`，冻结 base 为 `b91e58a29324b11840002efc53ed6f869b800c39`。提交链为 `b91e58a… → 8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`。本轮没有安装 system／user unit，没有调用 `systemctl`，没有执行 `daemon-reload`、enable、start、restart、stop，也没有连接或改变 system／user manager 状态。

唯一仓库写入为主树本报告 `docs/tmp/260807-resume-verify-systemd-rebuild.md`。目标 worktree 在验收前后均只有既存的未跟踪 `docs/tmp/`，状态摘要 SHA-256 均为 `cdc6963f46fc4237e0842a7859b3681ba60b2a065f1f477750812ddb07718f11`；目标 commit、tracked files、index、branch 与 refs 未修改。

## 从冻结合同独立推导的验收矩阵

| 验收项 | 独立 oracle | 实际结果 |
|---|---|---|
| 配置优先级 | 分别只启用 default、YAML、environment、CLI 层，要求 `defaults < YAML < environment < CLI`，并验证 direct bind 与 inherited fd 两条 Uvicorn 路径都消费最终值 | **PASS**：`300 → 311 → 312 → 313`；direct 与 inherited fd 均把 `313` 传给 `timeout_graceful_shutdown` |
| system unit deadline | 从真实 system unit 的 `ExecStart` 与 `TimeoutStopSec` 反解值，要求 app `300s`、manager `330s`、margin `30s` 且严格大于 | **PASS**：`300／330`，严格 margin `30s` |
| user unit deadline | 运行真实 installer render/apply 到隔离临时 XDG 根，再从生成 service 反解相同关系 | **PASS**：`300／330`，严格 margin `30s` |
| 真实 parser | 对临时副本运行真实 `/usr/bin/systemd-analyze verify` 与 installer 的真实 `systemd-analyze --user verify`；system 模板只在临时副本替换未安装的 `/opt` interpreter、账户与 working directory | **PASS**：system 与 user verify 均退出 0；这只证明 parser／引用合同，不证明 unit 已安装或 manager 已加载 |
| 短 SIGTERM cleanup | 真实 CLI／Uvicorn、真实 inherited listener、受控阻塞 upstream、`--graceful-timeout 1`，发送 SIGTERM 后要求 timeout 分支、lifespan cleanup 与有界退出 | **PASS**：隔离 session 复跑 `1 passed in 4.07s` |
| installer 默认零写 | 临时 HOME／XDG 根执行默认 dry-run＋`--check`，要求 unit dir、state dir 均不存在 | **PASS**：`dry_run_writes=0` |
| installer apply 幂等 | 显式 `--apply` 只写临时 XDG unit dir，记录三文件 bytes＋mtime 后重跑 | **PASS**：精确 3 文件；重跑均为 `UNCHANGED`，bytes＋mtime 不变 |
| installer 零 manager 操作 | 临时 PATH 放置退出 97 并记录调用的 fake `systemctl`，覆盖 dry-run、check、apply 与重复 apply | **PASS**：`systemctl_calls=0` |
| Plan bytes 相对 base 不变 | 比较 Git commit object 中 `b91e58a:docs/agents/systemd-runtime/plan.md` 与 `d3fabfa:docs/agents/systemd-runtime/plan.md` blob OID | **PASS**：两者均为 `a390efd0d2cd5393fa6d935f5c8c078a2d245253` |
| deadline drift 正控 | 只在内存／临时文本分别注入 system app `301`、system manager `329`、user app `301`、user manager `329`，要求 oracle 因对应字段漂移而转红，再验证原文本恢复为绿 | **PASS**：4／4 正控均按目标原因被拒绝；原 system／user 文本恢复为绿 |
| full pytest | 固定目标 root、完整 HEAD 与目标 `src/app` 导入路径，禁用 pytest cache 与 Python bytecode；完整执行 `tests` | **PASS**：`474 passed in 16.43s`，退出 0；另一完整隔离运行为 `474 passed in 15.73s`，退出 0 |
| pytest 规模交叉核对 | 对同一 HEAD、同一 `tests` selector 执行 collect-only，按 node ID 独立计数 | **PASS**：`collect_rc=0`，474 node IDs；与 full execution 数量一致 |
| Ruff | `.venv/bin/ruff check src tests` | **PASS**：`All checks passed!`，退出 0 |
| Pyright | `.venv/bin/pyright --pythonpath <target>/.venv/bin/python src tests` | **PASS**：`0 errors, 0 warnings, 0 informations`，退出 0 |

## 实际运行证据

所有 load-bearing shell 都在同一调用先打印并校验物理 cwd、Git top-level 与完整 HEAD；目标 Python 运行还打印并校验 `app.__file__=/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume/src/app/__init__.py`。关键完整运行如下。

1. 独立 code-only oracle，nonce `VFY-D3F-ORACLE-05`：退出 0；输出 `PRECEDENCE_AND_UVICORN_PASS`、4 条 `POSITIVE_CONTROL_REJECTED`、`INSTALLER_AND_UNITS_PASS system=300/330 user=300/330 dry_run_writes=0 apply_files=3 idempotent=yes systemctl_calls=0 system_verify=pass user_verify=pass drift_controls=4` 与 `OVERALL_INDEPENDENT_PROBE_PASS`。
2. 短 SIGTERM 隔离复跑，nonce `VFY-D3F-SIGTERM-04`：`1 passed in 4.07s`，退出 0。
3. 全仓 pytest，nonce `VFY-D3F-PYTEST-07`：`474 passed in 16.43s`，退出 0。另一目标身份固定、前后 status SHA 相等的完整运行得到 `474 passed in 15.73s`，退出 0。
4. Ruff：目标身份固定的组合 gate 输出 `RUFF_RC=0` 与 `All checks passed!`。
5. Pyright，nonce `VFY-D3F-PYRIGHT-11`：`0 errors, 0 warnings, 0 informations`，退出 0。
6. Plan object gate：base 与 candidate 的 Plan blob OID 均为 `a390efd0d2cd5393fa6d935f5c8c078a2d245253`。
7. Collect-only：目标身份固定运行得到 `collect_rc=0` 与 474 node IDs，交叉核对 full pytest 的 474 项执行口径。

共享 VS Code terminal 同时有多个会话排队写入，数次运行被外部 Ctrl-C 或无关命令串入。凡缺少本轮起止 nonce、退出 130、或没有完整摘要的运行均作废，不作为 PASS／FAIL 证据。其中一次定向矩阵得到短 SIGTERM 测试缺少 `Application shutdown complete.` 的 `1 failed, 7 passed`，但同一输出明确夹有外部 Ctrl-C；在忽略共享终端信号的隔离 session 中复跑该 exact test 为 `1 passed in 4.07s`，随后两次完整 pytest 又均为 474 passed，因此该首轮红灯判定为 harness／终端污染，而非可复现产品偏差。

## 正控判别力

正控的被测边界是“system 与 user service 各自声明的 application deadline、manager deadline 与冻结 margin 是否保持 `300／330／30`”。四个变异均只改变一侧的一个字段，并由同一个独立 parser 重新读取：

- system `--graceful-timeout 300 → 301`：因 `application timeout drifted: 301` 转红。
- system `TimeoutStopSec=330s → 329s`：因 `manager timeout drifted: 329` 转红。
- user `--graceful-timeout 300 → 301`：因 `application timeout drifted: 301` 转红。
- user `TimeoutStopSec=330s → 329s`：因 `manager timeout drifted: 329` 转红。

变异仅存在于内存字符串／临时生成文件，没有编辑目标树生产代码，也不需要恢复目标文件。随后原始 system 与 user 文本均重新通过相同 oracle，避免只证明“会红”而没有正确样本。

## 边界与未外推事项

- 本轮只验收 S3 graceful timeout 与 S4 rootless installer code-only rebuild，不验收 S5 真实 user-manager／cgroup smoke，也不验收 S7 rolling。
- `systemd-analyze` 通过不表示 manager 已加载 unit，不表示 fd 已由真实 manager 传递，也不表示 cgroup limits 已由内核施加。
- 临时 XDG 根中的显式 `--apply` 是 installer 行为测试，不是安装到真实 `$XDG_CONFIG_HOME/systemd/user/`。
- 短 SIGTERM smoke 证明 Uvicorn timeout 分支、FastAPI lifespan cleanup 与有界退出，不证明 crash／OOM、重复信号升级、accepted connection migration 或 rolling zero-downtime。
- 本轮没有操作 `localhost:4141` 的常驻服务，没有替换 `copilot-api-js`，没有部署或 cutover。

## 结构观察

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/graceful_timeout.py:1-5` 与 `contrib/systemd/install-user.py:20-21` | deadline facts 在生产模块与独立 installer 中重复定义；当前行为由跨模块 oracle 与 drift 正控保护，但 renderer 本身不是运行时同源 import | **本轮不改。** 这是已冻结 code-only bytes 的维护性观察，不影响当前用户可观察行为 PASS；后续可让 installer 从共享、可安全加载的 facts source 生成，或增加生成时显式一致性检查，仍保留 system／user 双向 drift 正控 |
| `tests/smoke/test_systemd_units.py:394-500` | 短 SIGTERM smoke 对共享 terminal SIGINT 敏感，外部 Ctrl-C 可制造缺 cleanup marker 的假红 | **验收侧已处置。** 用固定身份、独立 session、目标 import oracle 与 exact-test 隔离复跑；后续测试 harness 可把子进程放入独立 process group并显式区分外部 SIGINT 与目标 SIGTERM |

## 结论

`d3fabfadfba57af6c2d63e543e3198444777df54` 相对 `b91e58a29324b11840002efc53ed6f869b800c39` 满足本次冻结验收范围：配置／CLI graceful timeout 优先级正确，system／user unit 保持 `300／330` 且真实 `systemd-analyze` 通过，短 SIGTERM cleanup 可复现通过，installer 默认 dry-run 零写、显式 apply 幂等且零 `systemctl`，Plan commit bytes 不变，4 个 deadline drift 正控有判别力，全仓 pytest、Ruff 与 Pyright 均通过。总体 verdict：**PASS**。

# systemd rebuild resume 独立验收

## 结论

- **候选**：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`，`integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54`。
- **基线**：`b91e58a29324b11840002efc53ed6f869b800c39`。
- **提交链**：`b91e58a29324b11840002efc53ed6f869b800c39 → 8cae6c260c8bc2930be96eaecc7d6d24d470e00a feat: configure graceful shutdown timeout → d3fabfadfba57af6c2d63e543e3198444777df54 feat: add rootless systemd user installer`。
- **验收 verdict**：**PASS，0 blocker／0 major／3 non-blocking minor**。本轮从冻结规格、旧 Acceptance 验收矩阵和提交对象独立重建 oracle；没有直接沿用历史 verdict。配置来源、两条 Uvicorn 启动路径、system／user deadline、真实静态 parser、短 deadline SIGTERM cleanup、installer 默认零写／临时 apply／幂等／零 manager 调用、四个单侧 deadline drift 正控、定向与全仓回归均通过。
- **只读边界**：未修改目标 worktree、未安装 unit、未连接或改变真实 system／user manager、未调用 `systemctl`、未执行 `daemon-reload`／enable／start／restart／stop、未占用或修改生产端口、未触碰 `cc-daemon`、未执行 Git commit／ref／index 操作。Installer 的显式 apply 只写自动回收的临时 `$XDG_CONFIG_HOME`。主树唯一写入为本报告。
- **报告自身评审状态**：当前运行时没有可调度的独立 reviewer／subagent 工具；按 wrap-up artifact 规则，本报告仍需主会话安排独立复核。该待复核状态不改变下列候选执行证据，但不能冒充报告文本自身已经取得二次评审。

## 验收范围与不可外推边界

本 PASS 覆盖：

1. `shutdown.graceful_timeout` 的 default → YAML → environment → CLI 优先级。
2. 直接 host／port 与 inherited fd 两条启动路径均把 effective timeout 传给 Uvicorn `timeout_graceful_shutdown`。
3. System service 与 installer 渲染的 user service 均满足 application timeout `300s`、manager deadline `330s`、严格正余量 `30s`。
4. 短 deadline 下真实 CLI → Uvicorn → ASGI lifespan 路径会取消阻塞中的在途请求、完成 shutdown lifecycle并有界退出。
5. Rootless installer 默认 dry-run／`--check` 零持久写；只有显式 `--apply` 写临时 user unit目录；重复 apply bytes与 `mtime_ns` 不变；所有路径零 `systemctl`。
6. System／user unit 均通过真实 `systemd-analyze` 静态 verify。
7. 候选相对新基线的两片拓扑、pathset、Plan 排除与旧 reviewed code-only 语义等价。

本 PASS **不覆盖**真实 user manager activation、真实 fd 传递、service cgroup归属、effective cgroup limits、双 fd／双栈、accepted connection drain、unit安装、部署、生产 `localhost:4141`、cutover、rolling、installer三文件 all-or-nothing、crash durability、symlink hardening、backup／uninstall。上述事项保持未验证或既有后补状态。

## 独立 oracle 与执行结果

### Git 对象与载荷

冻结 gate 每次打印并验证物理 root、Git top-level、branch与 exact HEAD。提交对象核对结果：

- `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` 的 parent 精确为 `b91e58a29324b11840002efc53ed6f869b800c39`，只包含 graceful timeout 的 9 个非 Plan路径。
- `d3fabfadfba57af6c2d63e543e3198444777df54` 的 parent 精确为 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`，只包含 installer／deployment README／installer smoke 3 个路径。
- 两片 stable patch-id 分别为 `26dcc6fbfffe0db7d3358728ff244fec36078be1` 与 `412e73c47064720386c1075bfac0d3d8d08c6d26`，分别与旧 code-only `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc`、`2ec0cb81832691685bfe8d98ad03071d2d5e5316` 相同。
- `docs/agents/systemd-runtime/plan.md` 在 base、第一片和 tip 的 Git blob均为 `a390efd0d2cd5393fa6d935f5c8c078a2d245253`；候选没有携带 living Plan bytes。

### 配置与 Uvicorn 接线

独立 `/tmp/verify_systemd_rebuild_resume_260807.py` 不调用产品测试 helper 来生成 expected。它以四个互异值逐层读取真实 loader：default `300`、YAML `311`、environment `312`、CLI `313`，并分别从直接 port启动与 inherited fd启动捕获真实 `uvicorn.run()` kwargs。两条路径均得到 `timeout_graceful_shutdown=313`；fd路径同时保持 `fd=3` 且不携带 host／port。

结果：**PASS**。

### System／user deadline 与四个 drift 正控

同一独立 verifier分别解析仓库 system service和真实 installer渲染的 user service，得到：

| 对象 | Application timeout | Manager deadline | Margin | 正确样本 |
|---|---:|---:|---:|---|
| System service | `300s` | `330s` | `30s` | PASS |
| User service | `300s` | `330s` | `30s` | PASS |

随后只在内存文本副本中分别注入四个单侧缺陷，不修改候选：

- System application `300 → 301`：按“application timeout drifted”目标原因转红。
- System manager `330 → 329`：按“manager timeout drifted”目标原因转红。
- User application `300 → 301`：按“application timeout drifted”目标原因转红。
- User manager `330 → 329`：按“manager timeout drifted”目标原因转红。

恢复原始文本后 system／user正确样本重新通过。独立 verifier最终输出 `OVERALL_INDEPENDENT_PROBE_PASS`；日志 `/tmp/verify-systemd-rebuild-resume-independent-260807.log` 只包含本次 verifier输出。

结果：**PASS，四个正控全部有效**。

### Installer 黑盒副作用

独立 verifier在全新临时 HOME／XDG／PATH 中执行真实 helper：

- `--check` 输出 `DRY-RUN`，真实 `systemd-analyze --user verify` 通过，临时 config root与state root均未创建。
- Fake `systemctl` trap从未被调用。
- 显式 `--apply --check` 只在临时 `$XDG_CONFIG_HOME/systemd/user/` 写精确三份 unit，mode均为 `0644`。
- 第二次 `--apply` 三项均报告 `UNCHANGED`，bytes与 `mtime_ns` 均保持不变。
- Sentinel environment secret未出现在 stdout／stderr。
- System模板在临时副本中只替换未安装的 `/opt`解释器／工作目录与测试账户后，由真实 `/usr/bin/systemd-analyze verify` 返回 0；原模板未修改。

结果：**PASS**。

### Short deadline 与信号污染裁决

一次共享终端运行出现外部 `^C`／退出 130；其间 pytest曾报告 short-deadline用例缺少 `Application shutdown complete.` 日志。该运行的进程组已受到非候选 SIGINT污染，且整条命令退出 130，因此按证据规则整体作废，既不计绿也不计产品红。

随后 `/tmp/run_systemd_rebuild_acceptance_260807.py` 忽略 supervisor继承的 SIGINT，并为每个 pytest子进程建立独立 session。相同 short-deadline用例连续 **5／5** 返回 0；之后定向 suite和全仓 suite中又各通过一次。通过时 pytest捕获了子进程输出，因此 supervisor日志中不重复出现 timeout／cleanup marker；marker本身由该测试内部断言验证，不能把外层日志中的 `False`误读成未执行。

结果：**PASS；作废运行已如实保留，隔离后共 7 次通过且未复现**。

### 测试、静态检查与数量交叉验证

以下结果全部绑定 `integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54`，执行时设置 `PYTHONDONTWRITEBYTECODE=1`、禁用 pytest cacheprovider，并由 Python supervisor为每个命令建立独立 session：

| Gate | 选择器／口径 | 结果 | 日志 |
|---|---|---|---|
| Short deadline稳定性 | 单一真实 SIGTERM smoke，连续 5 次 | `5／5 passed` | `/tmp/verify-systemd-rebuild-resume-short-timeout-{1..5}.log` |
| 定向 pytest | `test_config_loader.py`、`test_cli.py`、`test_systemd_units.py`、`test_systemd_user_install.py` | `33 passed in 9.61s` | `/tmp/verify-systemd-rebuild-resume-targeted.log` |
| 全仓 pytest | `tests` | `474 passed in 15.43s` | `/tmp/verify-systemd-rebuild-resume-full-pytest.log` |
| Collect-only | `tests`，按含 `::` 的 node ID独立计数 | `474 node IDs`，pytest自报 `474 tests collected in 3.34s` | `/tmp/verify-systemd-rebuild-resume-collect-only.log` |
| Ruff | `src tests contrib/systemd/install-user.py`，`--no-cache` | `All checks passed!` | `/tmp/verify-systemd-rebuild-resume-ruff.log` |
| Pyright | `src tests contrib/systemd/install-user.py`，显式绑定目标 `.venv/bin/python` | `0 errors, 0 warnings, 0 informations` | `/tmp/verify-systemd-rebuild-resume-pyright.log` |

全仓执行摘要与 collect-only node ID是两种不同原理的同范围计数，均为 474。该数字只绑定本次 exact HEAD与 `tests`选择器，不是永久阈值。

编辑器诊断另对本切片涉及的 CLI、settings、loader、timeout constants、installer和两份 systemd smoke文件报告零问题；它只作静态旁证，不替代上述实际 Ruff／Pyright。

## 最终状态与只读证明

综合 supervisor记录的目标状态 SHA-256 在全部 short-timeout、定向、全仓、Ruff与Pyright前后均为 `cdc6963f46fc4237e0842a7859b3681ba60b2a065f1f477750812ddb07718f11`。最终 collect-only再次固定：

- Root：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`
- Branch：`integrate/260807-systemd-rebuild-resume`
- HEAD：`d3fabfadfba57af6c2d63e543e3198444777df54`
- Status：`?? docs/tmp/`

该未跟踪 `docs/tmp/` 在验收前已存在，最初 status即如此；本轮没有在目标树内创建、修改或删除其内容。由于目标 commit tree、import oracle、测试选择器均显式绑定冻结 worktree，该既有未跟踪目录未参与产品载荷或测试发现。

## Non-blocking minor 与结构怪味

| 位置 | 怪味／minor | 影响与处置 |
|---|---|---|
| `src/app/graceful_timeout.py:1-5` 与 `contrib/systemd/install-user.py:20-21` | Application／manager timeout数字在应用模块与独立 installer中各表达一遍，形成两个文本 owner | 当前 system／user独立 parity gate及四个单侧 drift正控会阻止静默漂移，故不是当前 correctness major。后续可抽取无应用依赖的轻量 shared facts，或继续把 parity gate保留为发布门。 |
| `tests/unit/test_config_loader.py:92-109` | 仓库永久测试只断言 YAML `11`＋env `12`＋CLI `13` 的最终 CLI结果，单独删除 YAML或env层仍可能保持绿色 | 本轮独立 verifier分别观察 `300／311／312／313` 四层，已补足本次 acceptance判别力；永久回归仍建议拆成逐层断言或参数化测试。 |
| `docs/agents/deployment-systemd/README.md` 的 helper apply说明与 `contrib/systemd/install-user.py:_apply()` | “三份文件原子写入”容易被读成整组 all-or-nothing，而实现只保证每个文件各自原子替换 | 既有裁决已把它定为后补 minor。本 PASS只声称逐文件原子／幂等，不声称三文件事务；后续统一文档措辞，并增加第二／第三个 replace失败后的显式失败、无临时残留和重跑收敛回归。 |

## 三向反思

1. **更好的内部替代方案**：当前 Uvicorn拥有 graceful cap，FastAPI lifespan拥有 cleanup；继续沿用这两个真实 owner优于接入未被生产 server消费的历史 `ShutdownManager`并制造第二套 deadline。Installer保持独立脚本也避免为渲染 unit启动整个应用依赖图；timeout facts的重复可在后续以轻量模块收敛。
2. **判据判别力**：配置逐层观察避免“只看最终 CLI值”的假绿；system／user各两种单侧 drift避免两份模板同错时自洽；真实 short-deadline probe覆盖 CLI→Uvicorn→lifespan，而静态 parser只负责 unit语法。外部 SIGINT运行明确作废，隔离 5 连跑与两次 suite回归共同避免把终端噪声误判成产品失败。
3. **成熟方案**：Unit语法继续交给官方 `systemd-analyze`；graceful行为交给 Uvicorn既有 `timeout_graceful_shutdown`；文件原子替换使用 Python／POSIX primitives。当前没有事实支持引入第三方 installer framework或自制 lifecycle owner。

## 最终判定

`integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54` 相对 `base@b91e58a29324b11840002efc53ed6f869b800c39` 在本报告声明的 systemd rebuild resume范围内为 **PASS**。两提交拓扑与载荷正确，Plan bytes未进入候选；配置与两条 Uvicorn路径、system／user deadlines、短 SIGTERM cleanup、rootless installer惰性／临时 apply／幂等／零 manager调用、真实静态 verify和四个 drift正控均取得独立实证。该 PASS不表示 unit已安装、真实 manager／cgroup已验证、服务已部署或 cutover／rolling已获授权。

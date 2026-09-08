# S4 rootless installer 重建恢复报告

## 结论

本报告以 `refs/heads/main@b91e58a29324b11840002efc53ed6f869b800c39` 为新基线，分析 S4 reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd` 与旧 code-only 第二片 `2ec0cb81832691685bfe8d98ad03071d2d5e5316` 的非 Plan 语义。目标独立 worktree 为 `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume`，分支为 `integrate/260807-systemd-rebuild-resume`，起始 HEAD 同为 `b91e58a29324b11840002efc53ed6f869b800c39`。该树现已形成严格线性的 S3 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` → S4 `d3fabfadfba57af6c2d63e543e3198444777df54`；主树 HEAD 与 `refs/heads/main` 仍为 `b91e58a…`，未被本任务修改。

**独立复评状态：review required。** 当前运行时没有可用的本地 subagent／独立 reviewer 调度能力；本报告已完成证伪式自审、源码逐项反查与最终状态复核，但这些不能替代独立文档评审。新 S4 的 patch-id与 3 个 result blobs均等于旧 reviewed code-only S4，且本轮 gate全绿；后续 reviewer仍应独立核对本报告的 current-state claims与 new-main S3＋S4 merged state，不能把历史 review自动外推为本报告已获 0 blocker／0 major。

**本轮已安全生成 S4 commit。** 初次分析时独立 worktree 只有一份尚未提交的 S3 index，故当时明确停止、没有猜测 SHA。随后并行 S3 工作形成实际提交 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`；重新取证确认其 parent 精确为 `b91e58a…`，9 个路径的 stable patch-id 为 `26dcc6fbfffe0db7d3358728ff244fec36078be1`，与旧 code-only S3 `862f4cfa…` 相同，且 tracked／index clean。S4 才在这个实际 parent 上生成，最终 commit 为 `d3fabfadfba57af6c2d63e543e3198444777df54`。

禁止把 `e16c2a7…` 或 `2ec0cb8…` 作为旧提交直接 replay 到新 main；本轮后续使用 `git cherry-pick --no-commit 2ec0cb8…` 只提取 patch到实际 S3 parent，并在创建新 commit前重新验证 parent、pathset、patch-id与 result blobs，不属于保留旧 commit identity 的 direct replay：

- `e16c2a7…` 的 parent 是旧基线 `80bc8f252b46c511f428af1d97159a5980ee9dc9`，其提交还携带 living Plan patch；非 Plan helper 使用固定 `TimeoutStopSec=330s`，但 `ExecStart` 尚无 `--graceful-timeout`，不满足 S3 后的 timeout parity。
- `2ec0cb8…` 的 parent 是旧 S3 code-only commit `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc`。它已完成 S3 parent adaptation，且自身只有 3 个非 Plan paths，但其 parent identity 不是 new-main 实际 S3 `8cae6c2…`。
- 两个旧 commit 均不是 `b91e58a…` 的祖先；它们与新 main 的 merge base 都是 `80bc8f2…`。应重建语义，不应重放旧对象或采用旧 Plan postimage。

## 权威输入与精确范围

| 对象 | Parent | 本报告使用方式 |
|---|---|---|
| 新基线 | `b91e58a29324b11840002efc53ed6f869b800c39` | 本轮 S3／S4 重建基座 |
| S4 reviewed source | `e16c2a700f23f66535e7347ab7357518eb8e56bd` | rootless helper 原始行为与 source provenance |
| 旧 S4 code-only 第二片 | `2ec0cb81832691685bfe8d98ad03071d2d5e5316` | S3 后 timeout adaptation 的参考实现 |
| 旧 S3 code-only 第一片 | `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` | 仅用于解释 `2ec0cb8…` 的 parent；不可作为新重建依赖 |
| 新 S3 实际 commit | `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` | 新 S4 的直接 parent；9-path patch-id 与旧 `862f4cf…` 相同 |
| 新 S4 commit | `d3fabfadfba57af6c2d63e543e3198444777df54` | 本轮在独立 worktree 生成的 3-path、non-Plan 结果 |

排除 `docs/agents/systemd-runtime/plan.md` 后，`e16c2a7…` 与 `2ec0cb8…` 的 S4 pathset 完全相同，精确为：

1. `contrib/systemd/install-user.py`
2. `docs/agents/deployment-systemd/README.md`
3. `tests/smoke/test_systemd_user_install.py`

S4 重建必须只包含这 3 个路径。实际 `d3fabfa…` 的 commit pathset与该集合精确相等，没有带入 S3 的 9 个路径或 living Plan。提交前后均以完整 `S3_ACTUAL=8cae6c260c8bc2930be96eaecc7d6d24d470e00a` 绑定 parent，没有从短 SHA 猜测身份。

## 应保留的精确产品语义

### 默认 dry-run 与无 manager 副作用

`contrib/systemd/install-user.py` 是独立 rootless user-unit renderer／installer helper，不机械复制 system-level 模板。

- 默认动作必须是 write-free dry-run：渲染并向 stdout 输出精确三份 user units，不创建 `$XDG_CONFIG_HOME/systemd/user`，不创建状态目录，不写 unit。
- `--check` 先执行内置文本合同检查；若 `PATH` 中存在 `systemd-analyze`，在临时目录写入渲染结果并执行 `systemd-analyze --user verify <service> <socket> <slice>`。verify 非零时保留 stdout／stderr 并以错误退出。
- `systemd-analyze` 不可用时，明确输出“文本检查通过，但 systemd-analyze unavailable”，返回成功但不得伪称 systemd verify 通过。
- dry-run、`--check` 与 `--apply` 都不得调用 `systemctl`，不得执行 `daemon-reload`、enable、start、restart、stop，也不得连接或改变 user manager 状态。
- helper 不创建、不读取 EnvironmentFile 内容，不采集、复制或打印其中的 token／secret；它只把路径写入 unit。

### 显式 apply、幂等与原子性边界

只有显式 `--apply` 才写目标目录。默认目标为：

- 设置 `XDG_CONFIG_HOME` 时：`$XDG_CONFIG_HOME/systemd/user/`。
- 未设置时：`~/.config/systemd/user/`。
- `--apply` 计算真实 unit 目录时要求 `XDG_CONFIG_HOME` 为绝对路径；相对值以错误退出。纯 dry-run／check 不调用 `_unit_dir()`，因此当前实现不会仅因相对 `XDG_CONFIG_HOME` 拒绝渲染。

apply 固定按 `ghc-api-proxy.service`、`ghc-api-proxy.socket`、`ghc-api-proxy.slice` 的顺序处理。每个文件分别采用同目录临时文件、完整写入、flush、`fsync`、`chmod 0644`、`Path.replace()` 的原子替换；finally 清理临时文件。相同 bytes 报告 `UNCHANGED`，不重写文件且保持 mtime；变化时报 `APPLIED`。

**原子性只到单文件。** 当前语义不保证三份 unit all-or-nothing：第二或第三个文件失败时，前面的文件可能已经替换。报告、README 和测试不得把“逐文件原子替换”写成“三文件事务”。`path.exists() and not path.is_file()` 的目标会被拒绝并显式失败；现有实现的 `Path.is_file()` 会跟随 symlink，因此这不是 symlink 安全合同。冲突备份、uninstall manifest、恶意 symlink、权限错误后的整组恢复仍是后续 helper hardening，不属于本次 S4 重建的既有验收合同。

### 参数、路径与 systemd escaping

保留以下 CLI：

- `--apply`
- `--check`
- `--project-dir ABSOLUTE_PATH`
- `--python ABSOLUTE_PATH`
- `--environment-file ABSOLUTE_PATH`

默认 `--project-dir` 为 helper 文件向上两级解析出的仓库根，默认 `--python` 为当前 `sys.executable` 的 resolved path，默认 EnvironmentFile 为 `$XDG_CONFIG_HOME/ghc-api-proxy/ghc-api-proxy.env`，未设置 XDG 时回退到 `~/.config/ghc-api-proxy/ghc-api-proxy.env`。项目路径必须存在且为目录；Python 路径必须是可执行普通文件。helper 只渲染 EnvironmentFile 路径，不检查该文件存在性，也不读取内容。

路径必须绝对化并由 helper 的内置 renderer 按 systemd unit 语法转义。旧 S4 不调用 `systemd-escape`：`WorkingDirectory=` 与 `EnvironmentFile=` 的路径 renderer 保留安全 ASCII 字符，把 `%` 写成 `%%`，并把空格、非 ASCII bytes 等转为 `\xNN`；解释器由独立 quote renderer 包在双引号内，并转义 `%`、反斜线与双引号。现有 smoke 保留含空格的 EnvironmentFile 路径，并用进程环境中的 sentinel 证明不会把任意环境 secret 打印到输出；“不读取 EnvironmentFile 内容”目前由代码路径审计保证，尚无创建真实 secret 文件后以读取 trap 证明的正控。

### 三份 user units

service 必须保持：

- `Type=exec`，`Requires=ghc-api-proxy.socket`，并在 `network-online.target` 与 socket 后启动。
- 不含 system service 的 `User=`、`Group=`，不使用 `/opt`、`/etc` 或 `/var/lib`。
- `WorkingDirectory=` 指向 escaped project path；`ExecStart=` 使用 escaped Python，运行 `-m app start --fd 3`，并按本报告 timeout parity 小节绑定实际 S3 `8cae6c2…` 的 graceful timeout。
- `StateDirectory=ghc-api-proxy`、`StateDirectoryMode=0700`、`UMask=0077`。
- `GHC_HISTORY__DB_PATH=%S/ghc-api-proxy/history.db` 与 `GHC_TOKENIZATION__STATE_PATH=%S/ghc-api-proxy/tokenization.json`；状态目录由 user manager 启动 service 时创建，helper 本身不创建。
- `EnvironmentFile=-<escaped path>`，缺失允许启动。
- `Restart=on-failure`、`RestartSec=2s`、`KillSignal=SIGTERM`、`KillMode=control-group`、`Slice=ghc-api-proxy.slice`。
- service 故意没有 `[Install]`，避免“复制 unit”等同于“启用 service”。

socket 必须保持 `ListenStream=127.0.0.1:4141`、`Accept=no`、`Backlog=1024`、`NoDelay=true`、`FileDescriptorName=http`、`Service=ghc-api-proxy.service`，且 `[Install]` 只含 `WantedBy=sockets.target`。

slice 必须保持 `MemoryHigh=1G`、`MemoryMax=2G`、`CPUQuota=200%`、`TasksMax=256`。静态渲染或 verify 只证明声明存在，不证明 user manager／kernel 已实际施加 cgroup 限制。

## Timeout parity 与 S3 parent adaptation

`e16c2a7…` 是 S3 前 source：helper 的 `ExecStart` 只有 `--fd 3`，同时硬编码 `TimeoutStopSec=330s`。这些原始 timeout 行**不能直接保留**到新 S3 parent。

`2ec0cb8…` 展示了正确的 S3 后 adaptation：

- 从 S3 模块导入 `DEFAULT_GRACEFUL_TIMEOUT_SECONDS` 与 `SYSTEMD_STOP_TIMEOUT_SECONDS`。
- user service 的 `ExecStart` 增加 `--graceful-timeout {DEFAULT_GRACEFUL_TIMEOUT_SECONDS}`。
- `TimeoutStopSec` 改为 `{SYSTEMD_STOP_TIMEOUT_SECONDS}s`。
- 内置文本检查同时要求 ` --graceful-timeout <default>` 与 `TimeoutStopSec=<computed>s`。
- installer smoke 从同一 S3 模块导入常量，断言渲染出的 `ExecStart` 与 `TimeoutStopSec`，不得在测试中复制第二套数字。

旧 S3 冻结的语义是 application graceful timeout `300s`，正的 manager margin `30s`，systemd stop deadline `330s`，并要求 `TimeoutStopSec > --graceful-timeout`。新 S4 必须保留这个**关系和同源性**，且适配点必须以新 S3 实际 commit 的公开符号、文件位置和值为准：

1. S3 实际 commit 若仍提供 `app.graceful_timeout.DEFAULT_GRACEFUL_TIMEOUT_SECONDS` 与 `SYSTEMD_STOP_TIMEOUT_SECONDS`，可直接采用 `2ec0cb8…` 的 import、render、text-validation 与测试断言。
2. S3 若重命名或移动公开常量，只改 S4 的 import／引用，不复制数字，不自造第二个 timeout owner。
3. S3 若改变默认值或 margin，S4 自动消费 S3 的值；不要为了匹配旧 `300／330` 而反向硬编码旧数。任何语义变化应先由 S3 自己冻结并测试。
4. S3 若没有公开 computed systemd deadline，则 S4 应要求 S3 补出同源公共事实，或在共同基础模块中提供；不要让 installer 自行再算一套未受 S3 测试约束的 deadline。
5. S4 测试应继续验证 rendered user unit 与 S3 常量一致。system template 的严格不等式与真实短-timeout lifecycle probe仍由 S3 测试负责，S4 不复制那套运行态测试。

实际 S3 `8cae6c2…` 与旧 `862f4cf…` 非 Plan patch-id相同，继续提供上述常量与 CLI 接线，因此本次采用上面第 1 种 adaptation：新 S4 的 imports、render、text validation 与测试断言均直接消费 `app.graceful_timeout` 的同源常量。`d3fabfa…` 的三个最终 blobs与旧 timeout-adapted `2ec0cb8…` 对应 blobs逐一相同。

## 可直接应用与必须 parent adaptation 的部分

### 可直接按语义重建

以下部分可从 `e16c2a7…` 原样重建，必要时按新 parent 上的格式上下文落位：

- helper 的 argparse 入口、绝对路径校验、默认 project／Python／EnvironmentFile／unit directory 解析。
- systemd path escaping 与 fallback。
- 三份 user unit 的 rootless 差异、socket activation、状态路径和 slice 资源声明。
- 默认 dry-run、可选 text／`systemd-analyze --user verify`、工具缺失时诚实降级。
- 显式 apply、逐文件原子替换、同内容 `UNCHANGED`、普通文件／非文件冲突处理、零 `systemctl`。
- installer smoke 的临时 HOME／XDG／PATH 隔离、fake `systemctl` trap、fake／real `systemd-analyze`、环境 sentinel 不泄露、dry-run 零写、apply 精确三文件、mtime 幂等、mode `0644`、含空格路径。
- README 的 rootless helper 使用方式、无 manager 副作用、user StateDirectory 语义、service 无 `[Install]`、socket `WantedBy=sockets.target`、effective cgroup 不可声称边界。

“直接应用”指行为与测试意图可复用，不代表旧 commit 获得 direct replay 许可。本次是在实际 S3 parent `8cae6c2…` 上生成新的最小 3-path commit `d3fabfa…`；最终 stable patch-id 与 3 个 result blobs同时证明结果等价于旧 reviewed code-only S4。

### 必须基于 parent 适配

- helper 顶部的 timeout imports、service `ExecStart`、`TimeoutStopSec` 和 `_validate_text()` 的 timeout tripwires：本次以实际 S3 `8cae6c2…` 的公开 API 为准，采用 `2ec0cb8…` 的 adaptation，没有采用 `e16c2a7…` 的旧硬编码形态。
- installer smoke 的 timeout imports 与两条 rendered service assertions：绑定同一 S3 API，不复制数字。
- `docs/agents/deployment-systemd/README.md` 同时被 S3 与 S4 修改。本次以 `8cae6c2…` 的 README 为 parent，在其 timeout／shutdown 说明上增补 rootless helper，没有采用 `e16c2a7…` 的 README postimage覆盖 S3。
- 文档中“与 system template 相同的 timeout”已对照 `8cae6c2…` 的 system unit 与公共常量后保留。
- 测试定位应沿用当前项目实际路径 `tests/smoke/test_systemd_user_install.py`；不要改造成新的 CLI package 或引入不存在的 `src/app/cli/systemd.py`。helper 继续位于 `contrib/systemd/install-user.py`。

## 实际重建与提交门

1. 起始分析发现 S3 仅存在于 index，故停止在计划态，没有生成 S4 或猜测 SHA。
2. worktree HEAD 随后前进；旧 exact-HEAD gate正确转红并阻止后续探针。重新取证得到 actual S3 `8cae6c2…`，确认其 parent 为 `b91e58a…`、9-path patch-id为 `26dcc6fb…`、tracked／index clean。
3. 在 `8cae6c2…` 上以 `git cherry-pick --no-commit 2ec0cb8…` 只准备代码载荷；该动作无冲突，staged pathset精确为本报告的 3 个非 Plan 路径。提交前 stable patch-id为 `412e73c47064720386c1075bfac0d3d8d08c6d26`，与旧 `2ec0cb8…` 相同。
4. 定向 pytest 口径为 `tests/smoke/test_systemd_user_install.py`、`tests/smoke/test_systemd_units.py`、`tests/unit/test_cli.py`、`tests/unit/test_config_loader.py`，结果为 `33 passed in 18.49s`。定向／全仓 Ruff均通过。
5. 裸定向 Pyright 因没有绑定项目 interpreter而只报告 `pytest` missing-import，未计为产品失败或绿色证据；项目级 `uv run pyright src tests` 又被共享终端外部 `SIGINT` 中断，退出 130，同样作废。最终使用 `.venv/bin/pyright --pythonpath <target>/.venv/bin/python src tests` 完整运行，结果为 `0 errors, 0 warnings, 0 informations`。
6. 全仓 pytest 在 `d3fabfa…` 的提交前候选 bytes上执行 `tests`，结果为 `474 passed in 29.03s`；独立 `--collect-only -q tests` 按 node ID计数为 `474 tests collected in 6.18s`。执行摘要与 collect-only 两种方法、同一选择器、同一 S3 parent加 staged S4 bytes一致。
7. 全仓 Ruff 为 `All checks passed!`，`git diff --cached --check` 通过；最终 pathset与 stable patch-id gate通过后创建本地 commit `d3fabfadfba57af6c2d63e543e3198444777df54`，subject 为 `feat: add rootless systemd user installer`。
8. commit-object 反查确认 `parent=8cae6c260c8bc2930be96eaecc7d6d24d470e00a`、pathset精确 3 个、stable patch-id仍为 `412e73c…`；3 个 result blob OID逐一等于旧 `2ec0cb8…`。主树 HEAD／main ref仍为 `b91e58a…`。

建议的机械验收矩阵：

| 维度 | 必须为绿的正确样本 | 必须为红／失败的错误样本 |
|---|---|---|
| 默认行为 | dry-run stdout 含三份 unit；unit dir／state dir 不存在 | 默认执行发生任何持久写入 |
| manager 副作用 | fake `systemctl` 调用记录不存在 | helper 任一路径调用 `systemctl` |
| verify | fake／real `systemd-analyze --user verify` 成功；工具缺失明确降级 | verify 非零却返回成功或吞 stderr |
| apply | 精确三文件、`0644`、重复 apply bytes／mtime 不变 | 目录等 `exists and not is_file` 目标被覆盖；写入异常遗留同目录临时文件 |
| timeout parity | rendered values 来自 S3 公共事实，且 manager deadline严格大于 app timeout | 回退到 fd-only `ExecStart`、硬编码独立 deadline或相等 deadline |
| 路径 | 绝对路径、空格、`%`、非 ASCII 经 unit escaping 后可 verify | `--apply` 接受相对 `XDG_CONFIG_HOME`，或接受不存在／不可执行 Python |
| rootless unit | service 无 `User／Group／[Install]`，socket 才能 `WantedBy=sockets.target` | 引入 `/opt`、`/etc`、`/var/lib` 或把 service 自动 enable |
| atomicity 声称 | 单文件替换原子、幂等 | 把三文件部分成功误报为 all-or-nothing |

## 明确未做与不可外推

- 已在 actual S3 `8cae6c2…` 上生成本地 S4 commit `d3fabfa…`；没有猜测 SHA，也没有把最初 staged S3冒充提交。
- 未修改、重排或混入 S3 的 9 个路径；S3 由并行工作先行形成独立 commit，S4 只以该 commit为 parent。
- 未修改主树、refs、Plan、user／system unit 目录或 manager 状态。
- 未运行 `systemctl`，未安装 unit，未占用或切换 `localhost:4141`。
- 本报告不证明真实 user manager activation、fd 传递、effective cgroup limits、accepted-connection drain、部署、cutover 或 rolling。
- 旧 S4 的已知后补项——三文件失败恢复合同、备份／uninstall manifest、symlink／权限 hardening——继续保留为后续工作，但不应偷渡进本次 reviewed S4 重建而改变已冻结切片边界。

## 复现证据

本报告中的提交拓扑由 `git show -s --format='%H %P %s'`、`git merge-base` 与 ancestry probe 核对；pathset由 `git diff-tree --no-commit-id --name-only -r <commit> -- . ':(exclude)docs/agents/systemd-runtime/plan.md'` 核对。S3 staged bytes 与旧 code-only S3 的相同性由两侧独立生成 stable patch-id 得到同一个 `26dcc6fbfffe0db7d3358728ff244fec36078be1`；该结果只说明 patch 内容相同，不把 index 升格为 commit。

`e16c2a7…` 与 `2ec0cb8…` 的 S4 最终树差异集中在相同 3 个路径：helper 增加 S3 常量 import与 timeout render／validation，installer smoke 增加同源 timeout assertions，README 把 rootless 说明接到 S3 的 shutdown 合同上。它们共同确定并已完成本轮裁决：**以 `e16c2a7…` 冻结 rootless installer 基础语义，以 `2ec0cb8…` 冻结 S3 parent adaptation 形态，在实际 S3 `8cae6c2…` 上生成新的 3-path、non-Plan S4 `d3fabfa…`。**

## 结构怪味与方案反思

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `docs/agents/deployment-systemd/README.md:73` 对 `contrib/systemd/install-user.py:188-193` | 文档原子性措辞强于实现；“三份文件原子写入”容易被解读为整组 all-or-nothing | 本轮不改 reviewed S4 bytes；本报告已把合同收紧为逐文件原子。后续 helper hardening统一修改 README 措辞，并用第二／第三文件失败回归固定“前件可能已落地、无临时残留、重跑收敛” |
| `contrib/systemd/install-user.py:168-182` | 单文件 replacement仅 `fsync` 文件，不 `fsync` parent directory；这是 crash-durability 边界，不影响进程内原子可见性 | 记为后续耐久性 hardening；本轮不把既有“原子替换”扩大成断电持久性承诺 |
| `contrib/systemd/install-user.py:168-172` | `Path.is_file()` 跟随 symlink，现有“非文件拒绝”不是 symlink 安全边界 | 与既有 S4 后补项合并；后续先冻结允许／拒绝 symlink 的产品合同，再以 `lstat`／`O_NOFOLLOW` 等平台能力实现，不在重建切片里擅自改行为 |
| `tests/smoke/test_systemd_user_install.py:59,89,97,108` | 环境 sentinel 不泄露只能证明 helper 未打印任意环境值，不能直接证明 EnvironmentFile 内容未读取 | 当前代码路径确实不打开该文件，故不构成产品 bug；后续测试可创建不可读／带 sentinel 的真实 EnvironmentFile 作为更直接正控 |

三向反思：

1. **更好的内部替代方案**：直接 cherry-pick 旧 S4 会携带错误 parent identity；手工重写又可能漏掉 reviewed bytes。本轮采用实际 S3 parent 上的无提交 patch应用，再以 pathset、stable patch-id和逐 blob identity 三层核对，是当前仓库内最稳妥路径。
2. **判据判别力**：只看 patch-id会漏掉 pathset外夹带文件，只看最终 blobs会漏掉 parent不对；本轮同时固定 parent、3-path 集合、patch-id、3 个 result blobs、定向行为测试与全仓回归。测试执行数与 collect-only计数一致只证明选择器规模一致，不单独证明所有语义均覆盖，因此仍保留 reviewed source／timeout parity和零副作用行为断言作为独立 oracle。
3. **成熟第三方方案**：unit 语法继续交给 `systemd-analyze --user verify`，进程与测试继续使用 pytest／Ruff／Pyright；没有必要引入第三方 installer framework。文件组事务、symlink安全和 crash durability若进入后续范围，应优先采用成熟的 filesystem primitives与明确平台合同，而不是继续叠加字符串检查。
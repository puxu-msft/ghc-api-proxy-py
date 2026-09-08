# systemd-next 合并态独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-next` 的 `integrate/260807-systemd-next@0a93e7f18f197bf8a2395eaaf20afda446f92d6b`，精确 base／current main 为 `80bc8f252b46c511f428af1d97159a5980ee9dc9`。覆盖线性两提交 `91f95f7d30c0b399eef98d997c0f88f57c2d0284 feat: configure graceful shutdown timeout` 与 `0a93e7f18f197bf8a2395eaaf20afda446f92d6b feat: add rootless systemd user installer` 的最终合并态；重点检查组合冲突、system／user unit graceful timeout 与 `TimeoutStopSec`、installer dry-run／apply／check、既有 system units、tests 与每提交路径。目标树只读；主树唯一写入为本报告。
- **总体 verdict**：**可进入下一阶段；两提交可按当前顺序回放到 current main。** 基础 systemd runtime 已在 base／current main，当前两提交均为该 base 的线性后继。未发现组合级 blocker 或 major；installer 的逐文件原子性问题维持既有裁决的非阻断 minor，可后补。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1，继承自 installer source review，已裁决允许后补；本轮未发现新增 minor。

## 双视角覆盖证据

### 机械核对视角

- 固定目标物理 root、branch、exact HEAD 与 clean worktree，确认 base `80bc8f2…` 是 HEAD 祖先；提交图严格为 2 个 non-merge commits，顺序为 `80bc8f2… → 91f95f7… → 0a93e7f…`。
- 清点每提交路径：graceful 提交修改 system service、CLI、config、共享 timeout 常量、system smoke、CLI／config tests 与两份 living docs；installer 提交只新增 helper／user smoke并更新同两份 docs。合并 diff 共 12 个声明路径，`git diff --check` 通过，未出现无关产品路径或遗漏测试路径。
- 以 stable patch-id 对账 reviewed sources：`865a5b7…` 与 `91f95f7…` 完全相同；installer source `e16c2a7…` 与集成提交 patch-id 不同，逐行审计确认差异仅为在已含 S3 的 parent 上给 user service 增加 `--graceful-timeout 300`、把 `TimeoutStopSec` 表达为 `330` 常量、增加对应 text validation／测试，并同步 living docs。未发现 reviewed installer 行为被删除或改写。
- 对账最终 system service、user renderer 与应用常量：两类 service 均为 application `300s`、manager `330s`、严格正余量 `30s`，并共同保留 `KillSignal=SIGTERM`、`KillMode=control-group`、fd 3、socket `Accept=no` 与同名 slice resource facts。
- 检查 installer 全部副作用面：默认 dry-run 不调用 `_apply()`；`--check` 只做内置文本检查与可用时的临时 `systemd-analyze --user verify`；只有显式 `--apply` 写 `$XDG_CONFIG_HOME/systemd/user`；代码无 `systemctl`、reload、enable、start、restart 或 stop 路径。
- 对照 source reviews `docs/tmp/260807-review-code-graceful-timeout.md`、`docs/tmp/260807-review-code-systemd-user-install.md` 与裁决 `docs/tmp/260807-arbitrate-user-install-atomicity.md`。没有直接沿用其 verdict：本轮重新读取最终代码、最终 tests、提交路径，并独立执行组合 timeout／installer probe。

### 第一人称执行视角

- 以 system administrator 使用 system units 的路径模拟：system `.service` 从 fd 3 启动 Uvicorn，CLI 显式 `300s` 覆盖同名 env，manager 在 `330s` 才到 hard deadline；正确样本通过，把 `TimeoutStopSec` 临时变为 `300s` 后，独立 oracle 以“manager deadline must strictly exceed app timeout”目标原因转红。
- 以普通用户首次运行 helper 的路径模拟：全新临时 HOME／XDG 根执行默认 `--check`，真实 user parser 通过，config／state 根仍不存在，`systemctl` 调用为零；随后显式 `--apply --check` 只生成 service／socket／slice 三份 `0644` 文件；再次 apply 三份均 `UNCHANGED`，bytes 与 `mtime_ns` 不变。
- 以 graceful shutdown 路径模拟：真实 listener、受控 upstream 与阻塞中的 `/v1/messages` 请求使用 `--graceful-timeout 1`；SIGTERM 后命中 Uvicorn timeout 分支，随后仍完成 FastAPI lifespan cleanup 并有界退出。
- 以维护者回放路径模拟：先回放 graceful，再回放 installer，第二提交能够读取第一提交新增的 `app.graceful_timeout` 测试常量；反向顺序则不满足其最终 test/import 依赖，因此报告明确要求保持当前顺序。

## 验证结果

- **定向 pytest**：固定 same HEAD、目标 import oracle 指向目标 worktree；`tests/unit/test_cli.py`、`tests/unit/test_config_loader.py`、`tests/smoke/test_systemd_units.py`、`tests/smoke/test_systemd_user_install.py` 原始日志为 `33 passed in 15.25s`。同范围 collect-only 为 33 个 node IDs。
- **独立组合 probe**：YAML `11`、env `12`、CLI `13` 最终传入 Uvicorn `13`；system 与 user timeout 均为 `300／330`；deadline 漂移正控按目标原因转红；dry-run 零持久写／零 `systemctl`；apply 精确三文件且重复运行 mtime 不变；system 与 user unit 的真实 `systemd-analyze` 均通过。
- **短 timeout 单项**：`test_short_graceful_timeout_cancels_inflight_request_and_runs_lifespan` 独立执行通过。
- **证据边界**：本轮交互终端存在旧命令积压，两次新发 full-suite 命令未形成可信日志，已明确丢弃，不把它们写成全仓 green。source branches 各自已有 exact-HEAD 全仓 pytest／Ruff／Pyright 通过，工作区上下文也记录同一 integration HEAD 的 `verify-systemd-next-integration` task 退出码为零；本 merged verdict 的独立执行证据以本轮可直接复核的 33 项定向 suite、黑盒 probe、正控与 parser logs 为准。

## 事实性发现

[minor] `contrib/systemd/install-user.py:163-189`、`docs/agents/deployment-systemd/README.md:63-77`、`docs/agents/systemd-runtime/plan.md:230-244` — apply 是固定顺序的逐文件原子替换，不是三份 unit 的 group all-or-nothing transaction，文档“原子写入”仍可能被误读；现有合并态 tests 仍未固化第二／第三次 replace 失败后的恢复合同 — 既有独立故障注入已证明失败会显式非零、无临时文件残留、不会 reload manager，修复外部故障后重跑可收敛 — 按 `docs/tmp/260807-arbitrate-user-install-atomicity.md` 的既有裁决维持 non-blocking minor，后补统一措辞为“逐文件原子替换”并增加一个参数化失败／重跑收敛测试；不为本项引入三文件事务或 rollback。

除上述已知且已裁决 minor 外，未发现事实性问题。尤其未发现 graceful timeout／`TimeoutStopSec` 漂移、user 与 system unit 组合冲突、dry-run 写盘、check 伪绿、apply 自动操作 manager、system units 回归或提交路径污染。

## 主观建议

[建议] `src/app/graceful_timeout.py:1-5` 与 `contrib/systemd/install-user.py:20-21` — user renderer 仍复制 `300／330` 常量，而不是直接复用应用模块 — 预期影响是未来维护者可能只改一处；当前定向 test 和本轮 parity probe 已能让漂移转红，因此不构成 correctness finding — 保留独立 renderer 边界，但长期把公共 timeout facts 放入无应用依赖的共享模块，或保持一条明确的 system／user parity regression。

## 结构怪味与方案反思

- **结构怪味**：`contrib/systemd/install-user.py:20-21`｜跨 renderer 重复 timeout facts｜本轮不阻塞，已有 parity tests；后续可提取轻量共享 facts。`contrib/systemd/install-user.py:163-189`｜单文件原子与整组事务措辞边界｜维持已裁决 minor并后补回归。其余扫描范围未发现新的职责错位、抽象泄漏或重复弱实现。
- **内部替代方案**：当前复用 Uvicorn 原生 graceful shutdown、FastAPI lifespan 与 systemd 原生 deadline／parser，优于新增 signal owner或自研 unit parser；显式 user renderer也优于从 system template 做脆弱字符串删除。
- **判据判别力**：timeout 相等负控能按目标原因变红；真实短 timeout 走生产 CLI／Uvicorn／lifespan；installer 黑盒 probe 对 dry-run 写盘、manager 调用和幂等有直接副作用 oracle。已知缺口仅为逐文件 replace 的错误路径，已登记 minor。
- **成熟第三方方案**：unit 语义交给官方 `systemd-analyze`；单文件 durable replace 使用 Python 标准库即可。未发现需要引入第三方 installer framework 的事实基础。

## 最终结论

**0 blocker／0 major；两提交可按 `91f95f7…` → `0a93e7f…` 的当前顺序回放到 current main `80bc8f2…`。** 基础 systemd runtime 已在 main，当前组合保持 system／user timeout、socket、slice、dry-run／apply／check 和零 manager side effect 合同一致。唯一已知 installer atomicity minor 已裁决允许后补，不阻塞本次回放。本 verdict 不表示 unit 已安装、真实 user manager／effective cgroup 已验证、部署／cutover 或 rolling 已完成。

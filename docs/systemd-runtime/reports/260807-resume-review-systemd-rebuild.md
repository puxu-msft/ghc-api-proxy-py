# systemd new-main rebuild merged-state 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume` 的 `integrate/260807-systemd-rebuild-resume@d3fabfadfba57af6c2d63e543e3198444777df54`，精确 base 为 `b91e58a29324b11840002efc53ed6f869b800c39`。范围内严格只有两条线性 non-merge commits：`8cae6c260c8bc2930be96eaecc7d6d24d470e00a feat: configure graceful shutdown timeout` → `d3fabfadfba57af6c2d63e543e3198444777df54 feat: add rootless systemd user installer`。按派活明确排除 living Plan，不评判或修改其当前内容；旧 `docs/tmp/260807-review-systemd-code-only.md` 仅作为待复验线索消费，没有把旧 verdict 或旧 commit identity直接外推到本链。
- **总体 verdict**：**可进入下一阶段。0 blocker／0 major，明确可以按 `8cae6c2…` → `d3fabfa…` 的顺序逐片 squash 回放到 `main@b91e58a…`。** 每片仍应在主树当时的 identity／preimage gate 通过后回放，并在该片 main-side tests gate 通过后才进入下一片；任一 gate 失败即停。本结论不授权安装 unit、调用 manager、部署、cutover 或发布。
- **blocker 数**：0。
- **major 数**：0。
- **严重级别过滤**：按派活只报告 blocker／major；未发现这两个级别的问题。

## 双视角覆盖证据

### 机械核对视角

- 每个作为结论依据的 shell 调用都在同一调用内打印并验证目标物理 root 与 exact HEAD；被共享终端其他会话串流或 `Ctrl-C` 污染的结果均明确废弃并重跑，不纳入证据。
- 提交图精确为 `b91e58a… → 8cae6c2… → d3fabfa…`，范围内恰有两条 non-merge commits。第一片 changed-path 集与旧 reviewed `862f4cf…` 相同，第二片 changed-path 集与旧 reviewed `2ec0cb8…` 相同。
- 两种独立方法确认逐片语义等价：稳定 patch-id 分别为 `26dcc6fbfffe0db7d3358728ff244fec36078be1` 与 `412e73c47064720386c1075bfac0d3d8d08c6d26`，各自与旧两片相等；`git range-diff 862f4cf^..2ec0cb8 b91e58a..d3fabfa` 对两片都给出 `=`。
- 逐路径 blob 表确认 11 个 touched paths 中，9 个在 old tip 与 new tip 直接 blob-identical；`src/app/config/settings.py` 与 `tests/smoke/test_systemd_units.py` 保留了 new main 相对旧 base 的同期变化。旧 base→new base 与旧 tip→new tip 在这两路径上的稳定 patch-id 均为 `172b62419c5cf08c1255ddab1397e53064428668`，说明 new-main 适配既未吞掉同期变化，也未额外改写它们。
- living Plan 在 `b91e58a…`、`8cae6c2…` 与 `d3fabfa…` 的 blob 均为 `a390efd0d2cd5393fa6d935f5c8c078a2d245253`；两片均未修改 `docs/agents/systemd-runtime/plan.md`。
- system service 最终为 application graceful timeout `300s`、manager `TimeoutStopSec=330s`，严格正余量 `30s`；保留 `KillSignal=SIGTERM`、`KillMode=control-group`、socket fd 3 与 `Accept=no` 合同。user renderer同样生成 `300／330`。
- installer 代码的唯一 subprocess 路径是可选的 `systemd-analyze --user verify`；没有 `systemctl`、daemon-reload、enable、start、restart 或 stop 执行路径。默认与 `--check` 不进入 `_apply()`；只有显式 `--apply` 写 `$XDG_CONFIG_HOME/systemd/user`。相同 bytes 不重写，mtime 保持不变。
- 最终 exact HEAD 的全仓 pytest 为 `474 passed in 15.73s`；同一 `tests` 范围的独立 collect-only 为 `474 tests collected in 3.33s`。Ruff 为 `All checks passed!`，Pyright 为 `0 errors, 0 warnings, 0 informations`。所有测试均使用目标 worktree `.venv` 与目标 `PYTHONPATH`，并禁用 bytecode／pytest cache 写入。
- 定向结果包括 CLI／配置／installer 25 项通过，以及 system unit／真实 inherited-fd／短 graceful-timeout smoke 8 项通过。测试前后目标树状态摘要保持一致；派活开始前已存在的唯一未跟踪 `docs/tmp/` 目录未发生变化。

### 第一人称执行视角

- 作为逐片回放执行者，先回放 `8cae6c2…`：该片在 new main 上建立共享 graceful timeout 配置、CLI→Uvicorn 接线、system unit `300／330` 合同与真实短超时 smoke，同时保留 new main 已新增的 settings／smoke 内容。该片 gate 通过后，才回放直接以它为 parent 的 installer 片 `d3fabfa…`。
- 作为 system service 使用者，`ExecStart ... --fd 3 --graceful-timeout 300` 将值传给 Uvicorn `timeout_graceful_shutdown`；systemd 在 `330s` 才达到 hard deadline。真实短 timeout 流程阻塞生产 `/v1/messages`，发送 SIGTERM 后经过 Uvicorn timeout 分支、FastAPI lifespan cleanup并有界退出。
- 作为普通用户运行 helper，默认或 `--check` 只 render／validate 三份 user units，不创建真实 config／state 目录且不连接 user manager。显式 `--apply` 只写精确三文件；重复 apply 相同内容为 `UNCHANGED`；所有路径均不调用 `systemctl`。
- 作为 living Plan 维护者，回放载荷完全不含 Plan bytes，因此不会采用旧 reviewed chain 的 Plan postimage，也不会覆盖主树现有 living checkpoint；每片回放后的 Plan fresh update仍是主流程另行执行的动作。
- 作为部署执行者，不会把本次 `0 blocker／0 major` 外推为 unit 已安装、真实 user manager／effective cgroup 已验证、部署完成、cutover 获授权或 rolling 已实现。

## 事实性发现

未发现 blocker 或 major。

## 最终结论

**0 blocker／0 major；可以按 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` → `d3fabfadfba57af6c2d63e543e3198444777df54` 逐片 squash 回放到 `main@b91e58a29324b11840002efc53ed6f869b800c39`。** 两片的 patch 语义与旧 reviewed code-only 链逐片相等，同时完整保留 new main 在 `src/app/config/settings.py` 与 `tests/smoke/test_systemd_units.py` 的同期差异；living Plan blob未变。每片仍须执行 main-side identity／preimage／tests gate，失败即停。

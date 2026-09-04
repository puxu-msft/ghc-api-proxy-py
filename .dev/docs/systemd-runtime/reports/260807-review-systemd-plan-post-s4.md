# systemd living Plan S4 后定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 current `docs/agents/systemd-runtime/plan.md`，内容身份 SHA-256 `6cc03c07e02cd25a9e33c1323d4c0536744ed7b324ca0d1d9e22d022259b4465`；固定 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28`。本轮定向核对 S3／S4 main commits、main-side gates、reviewed-source archives、Plan `LIVING`、S5 本机 `BLOCKED` 后转可销毁 VM／container 的执行路线、S7 后续独立切片、三个 non-blocking minor 与 `NO_CUTOVER`。未重跑产品测试，未执行安装、manager／cgroup 操作、服务／端口变更、部署、cutover、Git ref 或 index 变更；唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。Current Plan 为 0 blocker／0 major，可 checkpoint。** Plan 准确记录 S3、S4 已进入 main 且不得重放，两个 reviewed-source archive 已建立，S5 在当前本机环境保持 `BLOCKED`，下一动作转到具备独立 login session／user manager 与 delegated cgroup v2 的可销毁 systemd-nspawn container 或 VM；S7 rolling 仍为后续独立切片。该 checkpoint 不表示 S5 已通过、unit 已安装、真实 manager／effective cgroup 已验证、S7 已实现、部署完成或 cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0 个新增。既有 **3 个 non-blocking minor**——shutdown config precedence 永久测试判别力、installer 逐文件 atomicity 故障恢复回归、timeout facts 重复 owner——均被完整保留，不阻断本 Plan checkpoint 或后续 S5 隔离续诊。

## 双视角覆盖证据

### 机械核对视角

- 在同一次 shell 调用内验证物理 root、Git top-level、`main` 分支与 exact `HEAD=e9fb2771d6e040c761bb4074e3fcf2547caece28`；GNU `sha256sum` 与 Python `hashlib.sha256` 两种实现均得到目标 Plan SHA-256 `6cc03c07e02cd25a9e33c1323d4c0536744ed7b324ca0d1d9e22d022259b4465`。
- Git 对象确认 `c53849e2b5103c6426a67a8cbab687f2e45c1fa0` 是 current HEAD 的祖先，S4 main commit 即 current `e9fb2771d6e040c761bb4074e3fcf2547caece28`。`archive/260807-systemd-graceful-timeout` 现场解析为 reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5`；`archive/260807-systemd-user-install` 现场解析为 reviewed source `e16c2a700f23f66535e7347ab7357518eb8e56bd`。
- `docs/agents/systemd-runtime/plan.md:3-8,15,26,45-46,98-102,199,203-258,284-312,337-343,428-440` 的页首、固定事实、看板、阶段正文、disposition 与 kick-off 一致写明：S3、S4 已在 main 并完成各自 main-side gate；source identities 与 archives 只作 provenance；旧 integration 与旧 Plan postimage 禁止回放；Plan 继续 `LIVING` 且不收口。
- S3 的既有 main-side gate 由 `docs/tmp/260807-resume-review-systemd-plan-post-s3.md:13-16` 精确绑定 `main@c53849e…`，记录关键 30 项、全仓 585 项、同范围 collect-only 585 个 node IDs、Ruff 与 Pyright 通过。Current Plan 在 `docs/agents/systemd-runtime/plan.md:45,98,203-231,363` 保持同一口径，没有把 source 阶段 437 项或旧 integration 440／474 项误写成 S3 main gate。
- S4 current main gate 在 `docs/agents/systemd-runtime/plan.md:3,15,46,99,237-254,290,308,340,363,428` 一致记录关键 systemd tests、全量 pytest 588 项、Ruff 与 Pyright 通过；这些位置同时明确测试不连接真实 manager，未把仓库 gate 外推为 S5 live smoke。S5 执行记录与诊断报告均精确绑定同一 `main@e9fb277…`，与 Plan 的 current identity 一致。
- `docs/tmp/260807-verify-systemd-rebuild-resume.md:8,116-118` 给出 `PASS，0 blocker／0 major／3 non-blocking minor`，三项依次为 timeout facts 重复 owner、shutdown config precedence 永久测试判别力、installer 三文件非事务／逐文件 atomicity 故障恢复合同。Current Plan 在 `docs/agents/systemd-runtime/plan.md:8,26,45-46,99,101,199,231,254,290,308,339-341,409-411,432-438` 保留同一组三项，没有丢项、换项或升级为 S5 前置门。
- 当前代码仍支持这三个 minor 的“未关闭”状态：`src/app/graceful_timeout.py:1-5` 与 `contrib/systemd/install-user.py:20-21` 各自表达 timeout facts；`tests/unit/test_config_loader.py:92-109` 的专属用例仍只断言最终 CLI 值 `13`；`contrib/systemd/install-user.py:168,188` 的 `_write_atomic()`／`_apply()` 仍按三文件循环执行逐文件原子替换，`tests/smoke/test_systemd_user_install.py:81` 起的 happy-path test 覆盖 apply／幂等但没有第二／第三次 replace 失败后的恢复回归。
- `docs/tmp/260807-systemd-user-manager-smoke.md:3-20,72-86` 与 `docs/tmp/260807-systemd-user-manager-diagnosis.md:3-43` 共同确认：private D-Bus 与临时 XDG 树可建立，但独立 `systemd --user` 在 private control socket 出现前以 `rc=1` 退出；真实 activation、effective cgroup、restart 与 manager stop 未执行。诊断证明当前调用上下文缺少可写 delegated cgroup 子树，但没有把它夸大为 systemd 内部静默退出的唯一已定位根因，也没有把问题误判为产品代码缺陷。
- Plan 的 S5 路线在 `docs/agents/systemd-runtime/plan.md:100,134-136,199,256-284,308,338,343,432-440` 一致要求转到可销毁 VM／container，先由 PID 1 为专用测试 UID 建立正常 `user@UID.service`、独立 login session／user manager、delegated cgroup v2 与 private control socket，再允许对该 fixture 执行 `systemctl --user`。任何前置失败都继续 `BLOCKED`，不得退回宿主 manager、sudo、静态 verify 或 direct-fd 假绿。
- S7 在 `docs/agents/systemd-runtime/plan.md:102,199,308,310-327,399,432-440` 始终是后续独立切片；拓扑、readiness 切流、状态隔离、drain、回滚与并发规则均仍待冻结，没有被 S5 或单实例 socket activation 冒充完成。
- `NO_CUTOVER` 在 `docs/agents/systemd-runtime/plan.md:3,15,199,306-308,337-343,428-440` 与 S5 两份现场记录中一致：checkpoint、main commits、仓库 tests、静态 parser、direct inherited-fd 或未来备用 manager smoke 均不授权安装、操作生产 manager、占用／释放 `4141`、停止旧 Bun、部署或 cutover。

### 第一人称执行视角

- 作为 Plan checkpoint 执行者，我只冻结当前 Plan bytes，不重复回放 M1、S3 或 S4，也不把 reviewed-source archive 当成后续开发 HEAD。若 main、Plan hash 或 archive identity 漂移，我会停止沿用本 verdict 并重新复评。
- 作为 S5 实施者，我不会在当前 WSL／VS Code `/init.scope` 上继续变换环境重试同构 standalone manager，也不会连接宿主 user manager。下一步是在可销毁 systemd-nspawn container 或 VM 中先证明 PID 1、专用测试 UID、独立 login session／user manager、delegated cgroup v2 与 private control socket；门通过后才对该 fixture 使用 `systemctl --user`。
- 进入 live smoke 后，我会使用 S4 渲染结果、动态 loopback 备用端口与隔离状态根，依次验证真实 socket activation／fd inheritance、readiness、restart、graceful／force timeout、实际 cgroup 归属与 effective limits、cleanup。任一前置或 live 项失败都保持 `BLOCKED`；helper、`systemd-analyze` 或 direct inherited-fd 绿灯不替代真实 manager／cgroup 结果。
- 作为后续 rolling 设计者，我会在 S5 独立闭合后另开 S7，先冻结稳定 listener／proxy 拓扑、readiness 切流、writer 状态隔离、accepted-connection drain、回滚与并发规则；不会把单实例 listener continuity 写成双实例 rolling 或 accepted-connection zero-downtime。
- 作为部署／cutover 执行者，我会被 `NO_CUTOVER` 与显式授权边界阻止：本 checkpoint 不允许写真实 unit 目录、reload／start／restart manager、停止旧 Bun、释放或接管生产 `localhost:4141`。S5 即使未来在可销毁 fixture 通过，也仍不是生产 cutover 授权。

## 事实性发现

未发现问题。Current Plan 在本轮定向范围内为 **0 blocker／0 major／0 新增 minor**，可以形成 checkpoint。

既有 3 个 non-blocking minor 仍准确登记且未关闭：

1. `tests/unit/test_config_loader.py:92-109`——shutdown config precedence 永久测试只观察最终 CLI 值，YAML／environment 中间层可同时失效而测试仍绿；本次既有独立 verifier 已补足验收判别力，永久回归仍待增强。
2. `contrib/systemd/install-user.py:168,188` 与 `tests/smoke/test_systemd_user_install.py:81`——实现只保证三份 unit 各自原子替换，现有测试尚未固化第二／第三文件失败后的显式失败、无临时残留与重跑收敛。
3. `src/app/graceful_timeout.py:1-5` 与 `contrib/systemd/install-user.py:20-21`——application／manager timeout facts 有两个文本 owner；当前 parity gate 与四个单侧 drift 正控阻止静默漂移，但 owner 尚未收敛。

这些都是继承项，不是本轮新发现，也不阻断 S5；Plan 没有把它们静默删除或误写成已完成。

## 主观建议

无。当前执行顺序、隔离边界与证据分层已经足够明确，没有需要在 checkpoint 前追加的主观优化项。

## 结构怪味与方案反思

- **结构怪味扫描**：扫描 `docs/agents/systemd-runtime/plan.md:3-51,90-136,195-312,330-344,359-440`，判据为 current identity 重复处是否漂移、已完成 S3／S4 是否仍残留回放入口、archive 是否被误作开发 HEAD、S5 `BLOCKED` 是否被 direct evidence 降级、S7 是否被提前吞并、三个 minor 是否丢项、`NO_CUTOVER` 是否出现旁路。未发现新的重复实现、职责错位、抽象泄漏或强弱不一致；既有 timeout owner 重复已作为三项 minor 之一明确保留。
- **内部替代方案**：S5 转到由 PID 1 正常建立 user manager 与 delegated cgroup 的可销毁 VM／container，比继续手搓当前 `/init.scope` 下的 standalone manager、复用宿主 manager 或以 namespace 假装获得 delegation 更符合被测合同；未发现更好的项目内路线。
- **判据判别力**：private control socket 与 delegated cgroup 是进入 fixture manager 操作的必要门；真实 activation／effective cgroup／restart／stop 另作结果门。该分层既阻止静态／direct 证据假绿，也允许能力不足的环境诚实保持 `BLOCKED`，未发现 false-red 分支。
- **成熟方案**：继续使用 systemd PID 1、`user@UID.service`、official `systemd-analyze` 与 systemd-nspawn／VM 能力优于新增自制 manager 编排或证明框架；S7 仍须单独评估稳定 listener／proxy 拓扑，不在本轮预选实现。

## 最终结论

**0 blocker／0 major，可 checkpoint。** 本结论只绑定 Plan SHA-256 `6cc03c07e02cd25a9e33c1323d4c0536744ed7b324ca0d1d9e22d022259b4465` 与 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28`。S3、S4 main／archive／gates 状态一致且不再回放；Plan 继续 `LIVING`。下一动作是在可销毁 VM／container 中继续 S5，当前本机结论保持 `BLOCKED`；S7 rolling 仍为后续独立切片。既有 3 个 non-blocking minor 全部保留且不升级为 S5 前置门。整体继续 **`NO_CUTOVER`**，本报告不授权安装、生产 manager 操作、端口接管、部署、cutover 或发布。

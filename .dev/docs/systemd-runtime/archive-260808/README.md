# systemd runtime 本会话终态记录

## 文档性质

本文是 2026-08-08 收尾时的历史记录，不是systemd runtime的第二状态源。S3～S7的当前状态、后补minor、环境要求与下一动作均以live [systemd runtime Plan](../plan.md)为准；产品与替代现服的实时边界以 [Implementation](../../anthropic-responses-bridge/implementation.md)和[Readiness](../../service-cutover/readiness.md)为准。

本记录不移动、不改写原始report，也不授权安装unit、操作真实manager、占用生产端口、部署或cutover。

## 本会话终态

- M1 systemd socket activation runtime已作为`cf53334a10a717a3a3d30d6c0e8a297f5000d90c`进入main，reviewed source由`archive/260807-systemd-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`保留。
- S3 graceful timeout已作为`c53849e2b5103c6426a67a8cbab687f2e45c1fa0`进入main，reviewed source由`archive/260807-systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5`保留。
- S4 rootless user installer已作为`e9fb2771d6e040c761bb4074e3fcf2547caece28`进入main，reviewed source由`archive/260807-systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`保留。
- S3／S4的仓库内代码、静态unit、direct inherited-fd、graceful timeout与installer dry-run／临时apply证据已经形成；这不等于unit已安装或真实manager运行态已通过。

## S5：`BLOCKED`

S5本机隔离probe的helper渲染、临时目录apply、动态loopback unit verify以及不经过manager的direct inherited-fd／liveness／readiness／graceful关键路径通过；但独立`systemd --user`在创建临时`XDG_RUNTIME_DIR/systemd/private` control socket前以`rc=1`退出。

因此，以下真实运行项统一保持`BLOCKED`而不是`PASS`：

- 真实user-manager `daemon-reload`与socket／service activation。
- systemd向应用交付inherited fd。
- manager启动实例的liveness／readiness。
- service实际cgroup path及`memory.high`、`memory.max`、`cpu.max`、`pids.max` effective值。
- `Restart=on-failure`、manager stop、SIGTERM、graceful timeout与`KillMode=control-group`运行态。

诊断确认当前VS Code调用进程位于root所有且不可写的`/init.scope`，无法在既定“不连接宿主user manager、不使用sudo”的边界内获得独立manager所需delegated cgroup。下一有效环境是具备独立login session／user manager与delegated cgroup v2的可销毁VM或container；不得用静态unit、`systemd --user --test`或direct-fd绿灯替代S5。

关键point-in-time证据：

- [S3＋S4 new-main review](../reports/260807-resume-review-systemd-rebuild.md)
- [S3＋S4 independent verification](../reports/260807-resume-verify-systemd-rebuild.md)
- [S5 user-manager／cgroup smoke](../reports/260807-systemd-user-manager-smoke.md)
- [S5 private manager diagnosis](evidence/user-manager-diagnosis.md)

## 未闭合范围与部署边界

S5真实manager／cgroup未闭合；双fd／IPv4＋IPv6 activation、真实manager graceful／force stop与S7 rolling仍未完成。三个既有non-blocking minor及其最新处置不得从本历史记录判断，应回到live Plan。

整体部署状态保持`NO_CUTOVER`。S3／S4已进入main只代表仓库checkpoint完成，不授权写入真实unit目录、执行`daemon-reload`／enable／start／restart、停止旧Bun、接管`localhost:4141`或触碰`cc-daemon`。

## Current live carriers

- [Systemd runtime Plan](../plan.md)：S3～S7、S5阻塞、后补项与下一动作的live载体。
- [Bridge Implementation](../../anthropic-responses-bridge/implementation.md)：current main、bridge与runtime组合状态的易变真相源。
- [Service cutover Readiness](../../service-cutover/readiness.md)：真实运行面与替代现服前的实时矩阵。
- [Service cutover Plan](../../service-cutover/plan.md)：安装、接管、rollback与观察的live顺序和授权边界。

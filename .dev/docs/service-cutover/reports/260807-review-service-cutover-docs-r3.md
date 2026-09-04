# Service cutover Plan／Readiness 联合定向复评 R3

- **评审范围**：current `docs/agents/service-cutover/plan.md` SHA-256 `6644126a9aee556ef7fc8a3993d822220f4390227cc8e276984c6d7b4b8a2c8a` 与已提交 current `docs/agents/service-cutover/readiness.md` SHA-256 `a8abccf4ffd3168c5b3eaa5531de24f24f423948d72235a383e7a220e8101270`。定向复核联合 R2 的状态链 major、Plan 独立 R3、main／候选分层、`NO_CUTOVER／FOUNDATIONS_ONLY`、43 行与 `REL-06`、旧 Bun `4141`、`cc-daemon`、data／fence／time 门及备用端口／manager dry-run 准备；未执行任何运行态或 cutover 操作。
- **总体 verdict**：**修复 major 后可进入。** Plan 自身已由独立 R3 绑定同一 `6644126a…` bytes 给出 `0 blocker／0 major／0 minor`，因此 **Plan 可独立 checkpoint 提交并继续 living implementation／无执行准备**；但联合态不能给出 0-major 放行，因为已提交 Readiness 仍把同一 `main@380c757` 中已提交 Implementation 的 current SHA-256 错写为旧值。该问题不绕过生产门，故不是 blocker。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **边界结论**：Plan 的独立 checkpoint 不是 Plan 收口、readiness 通过、完整 bridge 产品 `PASS`、unit 安装／部署完成、真实 manager 验收或 `localhost:4141` cutover 授权。Readiness 修订并复评达到 0 major 后，也只允许两份 living 文档继续动态实施；任何真实 manager 操作、旧 Bun fence、数据动作或生产切换仍需阶段证据门与当次明确授权。
- **证据基线**：每次有效 shell 调用均在同一次调用内验证物理 root 与当前目录为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、`HEAD == 380c757087dcb8688d98619e7ad8c4d572b6f040`。Plan 为工作树 current bytes；Readiness 与 Implementation 的 worktree blob 均精确等于 `HEAD` blob，故发现不是未提交漂移。
- **双视角覆盖证据——机械核对**：完整读取 Plan、Readiness、联合 R2 与 Plan 独立 R3；用 `sha256sum` 与 Python `hashlib.sha256` 交叉核对身份。Git ancestry 确认 foundations `d274f584… → 798ba3e… → 1c13fda…` 与 systemd `cf53334…` 已在 main，happy `7e4b642…` 与 usage `aca3ced…` 尚未进入。Readiness 矩阵经 Python 分节解析与独立 `awk` 状态机均得 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43；`REL-06` 行仍含 request／global 两级预算 owner、有限 queue、charge-before-read、终态 release 及 global-only 与 single-block／16 MiB 相反缺陷控制。已提交 Implementation 实际 SHA-256 为 `60e09d3b6310361dad0025e88802f3774d0dc4ff8d264bdabe483bfc7635ba2a`，与 Readiness 第 9 行声明的 `4ace302283e2b4b539c8195e55a2a23020f692d40fe0df868546dd58312036e2` 不同。
- **双视角覆盖证据——第一人称执行模拟**：从 Plan 走“只准备备用端口”与“只准备真实 manager dry-run”，happy／usage 未进 main 时均停在 config／manifest／probe／expected 或 user unit render／check，不启动实例、不写真实 unit 目录、不执行 `daemon-reload`／enable／start／restart，也不占用 `4141`。从 Readiness 走 P0→P1→P2→P3，完整候选、真实入口、真实 manager、inventory＝ledger、backup／restore、三道 fence、七个时间门、rollback 与观察均未闭合；旧 Bun 继续持有双栈 `4141`，`cc-daemon` 只允许只读比对。唯一误导是入口身份把旧 Implementation bytes 当作 current。

## 事实性发现

[major] `docs/agents/service-cutover/readiness.md:9` — R2 的 current 状态链 major 尚未完全关闭：Readiness 声称 Implementation current SHA-256 为 `4ace302283e2b4b539c8195e55a2a23020f692d40fe0df868546dd58312036e2`，但 `main@380c757087dcb8688d98619e7ad8c4d572b6f040` 已提交的 `implementation.md` 实际为 `60e09d3b6310361dad0025e88802f3774d0dc4ff8d264bdabe483bfc7635ba2a`；两文件工作树 blob 又都等于各自 `HEAD` blob，因此这是同一提交内的正式文档矛盾，不是并发 WIP — 它会让实施者从错误的 living Implementation 身份出发；Plan 虽已绑定正确值且所有 `NO_CUTOVER` 门仍阻止生产动作，两份联合文档仍不能同时判为 current、0 major — 将 Readiness 的身份与状态描述同步到已提交 `60e09d3b…`，逐项确认 foundations／systemd、happy／usage 与产品 `UNVERIFIED` 结论仍一致，再对新 Readiness bytes 定向复评；不得用 Plan 的正确引用豁免 Readiness 自身错误。

## 已通过的联合轴

- **Plan 独立 checkpoint**：通过。独立 Plan R3 精确绑定 current `6644126a…`，结论为 `0 blocker／0 major／0 minor`；Plan 可单独 checkpoint，随后仍须持续 living 更新。
- **main／候选分层**：通过。Foundations 与 systemd runtime 已进入 main；happy／usage 仍待进入；完整 bridge 继续 `UNVERIFIED`。
- **`NO_CUTOVER／FOUNDATIONS_ONLY`**：通过。总览、P0～P3、尾部结论与不可声称边界一致；旧 Bun 仍是生产双栈 `4141` owner，当前没有切换授权。
- **43 行与 `REL-06`**：通过。两种独立计数一致，容量门有独立状态、owner、可判别 next smoke 与相反方向缺陷控制。
- **备用端口／manager dry-run 准备**：通过。Plan 只产出无执行准备；真实备用实例、真实 manager、unit 安装和生产端口操作均后置并要求另行授权。
- **data／fence／time／rollback**：通过。逐项 disposition、inventory＝ledger、backup／restore、旧 supervisor／listener／writer 三道 fence、七个时间门、观察阈值与 rollback dry-run 均保持硬门。
- **`cc-daemon`**：通过。两文档均禁止停止、重启、reload、修改或发送信号；后续 smoke 只允许前后只读比较 active state、MainPID、`InvocationID`、cgroup 与 socket。
- **授权边界**：通过。技术评审 0 major、文档 checkpoint、隔离准备或未来 readiness `PASS` 均不等于生产接管授权；`4141` 动作仍要求全部阶段门闭合及用户对当次动作明确授权。

## 主观建议

无。

## 结构怪味扫描

- **扫描范围**：两份 current 文档的状态入口、阶段矩阵、P0～P3、data ledger、cutover／rollback、`cc-daemon` 不变量、下一动作与 kick-off，并对账同一提交内的 Implementation／Readiness 身份及 Git ancestry。
- **判据**：冲突 current 状态源、局部 checkpoint 冒充产品／部署态、准备动作泄漏为运行操作、单 fd／单地址族冒充目标合同、writer owner 分叉、fence／time 门失去失败路径、`cc-daemon` 被纳入操作范围。
- **处置**：发现一处“同一提交内 current 内容身份冲突”，即上述 major；其余既有 single-fd、system-level unit、shutdown 接线、数据双写与 shadow 副作用怪味均已登记并留在后续门中。

## 结论

本轮为 `0 blocker／1 major／0 minor`。**Plan `6644126a…` 可独立 checkpoint 提交且继续 living；联合 Plan／Readiness 需先修正 Readiness 的 Implementation current identity，再复评到 0 major。** 无论本轮还是后续 0 major，都不是文档收口、完整产品通过、真实 manager／unit 部署完成或 cutover 授权。

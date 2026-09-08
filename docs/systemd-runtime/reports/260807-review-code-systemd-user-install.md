# Rootless systemd user installer 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-systemd-install` 的 `feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`，base `80bc8f252b46c511f428af1d97159a5980ee9dc9`。覆盖 installer、smoke tests、deployment README 与 living Plan；重点检查默认 dry-run 零写、apply 原子边界／幂等、user unit 路径／targets／`StateDirectory=`／`%S`、零 `systemctl`／reload／enable／start、`--check` 诚实性、临时 `HOME` smoke 与 secret 非泄露。
- **总体 verdict**：**可进入下一阶段；可以 squash。** 未发现 blocker 或 major；有 1 个不阻塞 squash 的原子性合同／错误路径测试 minor。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **评审基线**：目标树评审期间固定为上述 HEAD 且 clean；只读目标树，本报告是本轮唯一主树写入。

## 双视角覆盖证据

### 机械核对视角

- 清点 base→HEAD 的单提交和 4 个变更路径，读取最终代码／测试／文档并执行 `git diff --check`。
- 扫描全部进程、写入和输出面：唯一外部进程是 `systemd-analyze --user verify`；无 `systemctl`、reload、enable、start、restart 或 stop。测试用退出 99 的记录器验证 dry-run、apply、重复 apply 均不调用 `systemctl`。
- 对账三份 unit：目录为 `$XDG_CONFIG_HOME/systemd/user` 或 `~/.config/systemd/user`；service 无 `User=`／`Group=` 和 `[Install]`；socket 为 `WantedBy=sockets.target`；状态合同为 `StateDirectory=ghc-api-proxy`、mode `0700`、`UMask=0077` 与 `%S/ghc-api-proxy/...`。
- 本机 systemd 255 的本地官方手册确认 `%S` 对 user manager 表示其 `XDG_STATE_HOME` 状态根；真实 `systemd-analyze --user verify` 接受渲染结果。该证据不外推为 manager 已加载、状态目录已创建或 cgroup limits 已生效。
- `--check` 在 parser 非零时失败；工具缺失时明确打印仅 text validation 通过和 parser unavailable，不伪称 verify 通过。临时 verify 文件自动回收。
- helper 只引用 EnvironmentFile 路径、不读取内容；执行探针与 smoke sentinel 均证明环境 secret 不出现在 stdout／stderr。
- exact HEAD 全仓 gate：`437 passed`，独立 collect 同为 437 个 node ID；Ruff 通过；Pyright 为 `0 errors, 0 warnings, 0 informations`；import oracle 指向目标 worktree。

### 第一人称执行视角

- 全新临时 `HOME`／XDG 根执行默认路径：只输出 dry-run 和三份 unit，config／state 根均不创建，也不触发 manager 命令。
- 分别模拟 parser 可用／缺失的 `--check`，两者都不要求运行中的 user manager，不写 user unit／state。
- 临时 config 根执行 `--apply --check`：仅生成三份 mode `0644` 的 unit；重复 apply 报告 `UNCHANGED`，bytes 与 `mtime_ns` 不变；含空格路径通过真实 parser。
- 注入第二次文件写入失败：第一份已换为新 generation，其余仍是旧 generation。故实现是逐文件原子替换，不是三文件 all-or-nothing；失败返回非零且从不 reload manager，修复后重跑可收敛。
- 模拟后续人工 enable：用户只需显式 enable socket，`sockets.target` 拉入 `.socket`，socket activation 再拉起无 `[Install]` 的 service；helper 不代替用户执行。

## 事实性发现

[minor] `contrib/systemd/install-user.py:163-191` — apply 只保证单文件原子替换，不保证三份 unit 整组事务；现有测试只覆盖成功路径与幂等 — `_apply()` 顺序调用三次 `_write_atomic()`，故障注入在第二次写入失败后得到新旧混合 generation；README／Plan 的“三份文件原子写入”“显式 apply 原子写入”容易被理解为整组 all-or-nothing。因 helper 不 reload manager、失败明确非零且重跑可恢复，当前不阻塞 squash — 建议文档和 CLI help 改成“逐文件原子替换”，并增加第二／第三文件失败后无临时文件残留、非零退出及重跑收敛的回归。若合同确实要求整组事务，再设计 generation staging＋单点切换或可验证 rollback。

除上述 minor 外，未发现事实性问题。default dry-run 零写、成功 apply 幂等、user unit 路径／targets／状态合同、零 manager 状态变更、诚实 check、临时 HOME smoke 与 secret 非泄露均有独立证据。

## 主观建议

[建议] `contrib/systemd/install-user.py:53-110` 与 system-level templates — user renderer 独立复述 timeout、socket 与 resource facts，未来可能漂移 — 预期影响是两套 unit 各自 verify 通过但合同不一致 — 保留两套明确 renderer，同时增加共享 facts 的机械 parity 测试，不改为脆弱的全文字符串替换。

## 结构怪味处置

- `contrib/systemd/install-user.py:163-191`｜合同边界含混｜本轮记 minor，明确逐文件原子并补故障恢复测试。
- `contrib/systemd/install-user.py:53-110`｜跨模板重复事实｜后续加机械 parity；当前不合并完整模板，因为 user／system manager 合同确有差异。
- 其余扫描范围未发现新的重复实现、职责错位或抽象泄漏。

## 方案反思

1. **更好的内部替代方案**：显式 user renderer 优于从 system templates 做字符串删除；应补共享 facts parity，而非强行合并模板。
2. **判据判别力**：成功／幂等／零 manager／parser／secret 判据有效；原子性此前缺少失败对照，故障注入已暴露覆盖缺口，应固化回归。
3. **成熟第三方方案**：unit 语法继续交给官方 `systemd-analyze --user verify`，单文件 durable replace 使用标准库足够；若升级为整组事务，应先冻结 systemd load-path 下的单点切换设计。

## 结论

**0 blocker／0 major；可以 squash。** 唯一 minor 是单文件原子与整组事务的表述／测试边界，不影响默认 dry-run、显式 apply happy path 或“绝不操作 manager”的核心目标。本 verdict 不表示真实 user manager 已 reload／enable／start，也不表示 effective cgroup 或运行态 activation 已验证。

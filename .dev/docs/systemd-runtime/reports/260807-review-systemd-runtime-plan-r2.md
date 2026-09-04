# systemd runtime living plan 独立复评 R2

- **评审范围**：稳定快照 `docs/agents/systemd-runtime/plan.md` 全文，精确 SHA-256 为 `c1c5fd8a84c71363a4d57f374a0696b3dc5b1074498982a0dc15bd840e42009a`；定向对账上一轮 `docs/tmp/260807-review-systemd-runtime-plan.md` 的 3 项 major、`docs/tmp/260807-review-code-systemd-runtime.md`、`docs/tmp/260807-systemd-socket-feasibility.md`、已落盘的 `docs/tmp/260807-review-code-systemd-runtime-r2.md`，以及候选 `feat/systemd-cgroup-runtime@1a220e04a99c6ce07b4bdd6bb0876b4180d4c489` 的 current bytes。只复核既定范围：reports 消费、StateDirectory 启动失败修复、M1 squash 门、non-TDD living 节奏，以及 `Type=exec`／`KillMode=control-group`、continuity、timeout、helper、cgroup 与 rolling 的阶段边界。未修改计划或候选，未安装、启动、停止、reload 任何 unit。
- **总体 verdict**：**修复 major 后可进入**。上一轮 3 项 major 的目标方向中，StateDirectory 启动失败与首次回并节奏已经关闭，旧 code／systemd reports 也已有明确 disposition；但 current plan 没有消费已经存在的 `candidate@1a220e4` code R2，把当前状态错误写成“R2 尚未落盘／只余独立复评门”。该 R2 实际 verdict 为 `0 blocker／1 major`，发现 systemd 默认权限会把 History 与 tokenization 状态创建为同机其他用户可读，因此 current candidate 仍不可 squash。计划先回写这一新 major、把下一动作改为修复权限并复评；修复后的 candidate 一旦独立 code review 达到 `0 blocker／0 major`，即可明确继续实施并立即准备 squash／回并，不等待 continuity 深化、timeout、helper、cgroup observability 或 rolling。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **稳定快照证据**：首次读取时连续两次 `sha256sum` 均得到 `c1c5fd8a84c71363a4d57f374a0696b3dc5b1074498982a0dc15bd840e42009a`；落盘前又由 `sha256sum` 与 Python `hashlib.sha256` 两种调用路径交叉确认同一值。所有 shell 取证均在单次调用内验证主树为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`；候选取证另验证物理树、分支、HEAD、基线祖先关系与 clean 状态。
- **双视角覆盖证据——机械核对**：逐行对账 plan 的基线、完成定义、事实区、状态看板、S0～S7、disposition、验证命令与 kick-off；逐项映射上一轮 3 项 major；核对三份 code／systemd 报告与 current code R2 的 verdict／findings；直接读取候选 service、CLI、部署 README、真实 fd smoke、History writer 与 tokenization writer；用本机 systemd 255 手册核实 system unit 默认 `UMask=0022`、`StateDirectoryMode=0755`；候选定向 pytest 在 `candidate@1a220e4` 上以 0 退出，pytest 自报 `16 passed`，该数量未作第二原理交叉计数，仅作为命令现场输出而非验收阈值。
- **双视角覆盖证据——第一人称执行**：按 current plan 从 S1 执行到 M1，依次模拟“读取看板→取得 code R2→决定下一动作→判断能否 squash”；该路径在 plan 宣称“R2 尚未落盘”处与仓库事实冲突，并会让执行者重复派评审而不是先修 code R2 已定位的权限 major。另模拟无可写 HOME 的 inherited-fd 启动、预连接 backlog、liveness、readiness 503、History 落盘、tokenization 后续写盘、service-only restart、accepted connection drain、M1 后 timeout／helper／cgroup／rolling 切片；确认旧启动失败已关闭，但状态文件保密权限仍未进入计划。

## 事实性发现

[major] `docs/agents/systemd-runtime/plan.md:6,38,87,127-181,312-315,395` — living plan 未消费已经落盘的 `docs/tmp/260807-review-code-systemd-runtime-r2.md`，因此把候选状态和 M1 下一动作写错，并漏掉 current candidate 的新 code major — plan 多处断言 current R2“尚未在主树落盘”、M1“仅余独立复评门”，kick-off 仍要求先做该 R2；实际报告已经精确绑定 `candidate@1a220e04a99c6ce07b4bdd6bb0876b4180d4c489`，verdict 为 `0 blocker／1 major`、明确“不可 squash”。独立核验候选 `contrib/systemd/ghc-api-proxy.service:13-14` 发现只有 `StateDirectory=ghc-api-proxy` 与两条状态路径，没有 `StateDirectoryMode=` 或 `UMask=`；本机 systemd 255 手册规定 system unit 默认 `UMask=0022`、状态目录默认 `0755`。再以该默认 umask 调用候选真实 `HistoryWriter` 与 `TokenizationStateStore`，得到目录 `0755`、`history.db` `0644`、`tokenization.json` `0644`；History schema 会持久化 request payload、response、usage 与 error，故这是当前 system-level 模板的实际本地数据暴露，而非通用加固建议。修复路线是：先在 plan 的评审输入、事实区、S1／S2／M1 看板、disposition 与 kick-off 中消费 code R2，记录当前为 `0 blocker／1 major`；把下一动作改为在候选增加 `UMask=0077` 与 `StateDirectoryMode=0700`，收紧自管覆盖目录文档并补真实 writer 权限回归；随后做 current HEAD code R3。R3 达到 `0 blocker／0 major` 后，明确可继续实施并立即 squash／准备回并，code R2 的非阻断 readiness／tokenization／EnvironmentFile 覆盖 minor 可排入回并后强化，不得反向扩大 M1。

## 上一轮 3 项 major 关闭矩阵

| 上一轮 major | R2 结论 | current bytes 证据 |
|---|---|---|
| 未消费 code／systemd reports | **旧 reports 已消费，但 current code R2 再次漂移，故以本轮 major 续开** | `plan.md:6,38` 已列 R1 code review、socket feasibility、上一轮 plan review 并记录 `Type=exec`／`KillMode=control-group` 等 disposition；但漏列已存在的 code R2，状态真相再次滞后。 |
| 漏掉默认状态目录启动失败 | **原 major 已关闭** | `plan.md:17,35,149-168,312` 把 `StateDirectory=ghc-api-proxy`、显式 History／tokenization 路径和 `HOME=/nonexistent` 真实 fd smoke 纳入 M1。候选 service 与设置接线一致；定向真实 fd smoke 通过，History 实际落盘。新权限 major 不推翻“可启动”结论，但必须在 squash 前关闭。 |
| 所有强化完成后才回并 | **已关闭** | `plan.md:12-24,84-93,164-188,395-400` 已把 M1 定义为骨架＋真实 inherited-fd／backlog／HTTP／History smoke＋current code `0 blocker／0 major`，达到即 squash／准备回并；continuity 深化、timeout、install helper、cgroup observability 与 rolling 明确后置。 |

## 已核对且通过的轴

- `docs/agents/systemd-runtime/plan.md:98-127` 正确保持 `LIVING` 与非强制 TDD：按“骨架／happy path→执行 smoke→尽快回并→后续强化”推进，不把传统 test-first 设为流程门，同时要求补强切片具备可判别回归。
- `docs/agents/systemd-runtime/plan.md:17-20,140-188,306-315,395-400` 对 `Type=exec`、`KillMode=control-group`、`--fd >= 1`、StateDirectory 启动修复与 readiness 独立 oracle 的方向正确。`Type=exec` 没有被冒充应用 ready，`control-group` 没有沿用 mixed 的错误长期理由。
- `docs/agents/systemd-runtime/plan.md:40-67,164-178` 正确区分 listener continuity、queued／unaccepted continuity 与旧进程 accepted connection drain；M1 只要求当前真实 inherited-fd smoke，`systemd-socket-activate` happy path、service-gap listener identity、accepted drain／timeout 与 main＋child manager-level stop 均后置，不错误阻塞首次回并。
- `docs/agents/systemd-runtime/plan.md:190-306` 正确把 graceful timeout、默认 dry-run 的 rootless user install helper、cgroup declared／effective／runtime 三层读取与 observability、双实例／rolling 拆为回并后独立切片。rolling 明确要求 readiness 切流、状态隔离、drain 与回滚，不把单实例 socket activation 冒充 rolling。
- current code R2 的唯一 minor 不应成为 M1 squash 门。它要求补 readiness 200、tokenization 实际落盘及 EnvironmentFile 覆盖目录的运行态证据；这些是有价值的后续强化，但报告本身明确标为非阻断，符合“code 0 major 即 squash，不等强化”的既定裁决。

## 主观建议

未提出额外主观建议。本轮发现均可由 current files、systemd 255 手册和真实 writer mode probe 直接裁决；不以 ROI／YAGNI 缩减 timeout、helper、cgroup 或 rolling 的后续范围。

## 结构怪味扫描

- `docs/agents/systemd-runtime/plan.md:6,38,87,312-315,395` — **living 状态真相源漂移／下一动作滞后一阶段** — 本轮作为 major 处理：消费 code R2，把“去做 R2”改为“修复 R2 major→做 R3”，并保持 `0 major` 后立即 squash 的门。
- 扫描范围还包括 unit→状态路径→writer 权限、socket→CLI→Uvicorn fd、service restart→listener／accepted connection、shutdown owner、helper 写入边界、cgroup reader／metrics 与 rolling 拓扑；除上述漂移外，未发现新的职责重复、抽象泄漏或不必要自研机制。

## 方案反思

1. **更好的内部替代方案**：继续使用 systemd 原生 `StateDirectoryMode=` 与 `UMask=` 闭合目录及派生文件权限，优于在两个 Python writer 中分别补 chmod；它位于所有状态写入者共享的部署编排层。
2. **判据判别力**：现有 smoke 能让“无可写 HOME 且无显式状态路径”的旧缺陷变红，却不能区分 `0644` 与 `0600`；真实 writer mode probe 在默认 `0022` 下稳定得到 `0644`，加入 group／other 位断言后才能覆盖新 major。正确样本也应在 `0077`／`0700` 下得到目录和文件均无 group／other 权限，防止判据只会报红。
3. **成熟第三方方案**：systemd 已提供所需目录所有权、mode 与进程 umask 合同，无需新增库或自研权限管理器；后续 activation、cgroup 与 shutdown 也应继续优先使用 systemd／Uvicorn 现有机制。

## 继续实施条件

1. current plan 消费 `docs/tmp/260807-review-code-systemd-runtime-r2.md`，把 candidate／M1 状态改为 `0 blocker／1 major，不可 squash`，并记录其非阻断 minor 为回并后强化。
2. candidate 增加 `UMask=0077`、`StateDirectoryMode=0700`，收紧覆盖目录文档并补真实 History／tokenization writer 权限测试；复跑 unit verify、无 HOME 真实 fd smoke、权限正负样本与项目 gates。
3. 独立 code R3 对修订后 candidate 给出 `0 blocker／0 major`。达到该条件后，本计划应**明确标记“可继续实施，可立即 squash／准备回并”**；不等待 listener continuity 深化、graceful timeout、install helper、cgroup observability 或 rolling。

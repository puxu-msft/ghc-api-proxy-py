# systemd runtime living plan 独立评审

- **评审范围**：`docs/agents/systemd-runtime/plan.md` 全文，对照候选 `feat/systemd-cgroup-runtime@66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`、`docs/tmp/260807-review-code-systemd-runtime.md` 与 `docs/tmp/260807-systemd-socket-feasibility.md`。覆盖 living plan 动态性、`Type=exec`／`KillMode=control-group` 纠偏、rootless socket activation smoke、listener continuity 与 accepted connection drain、graceful timeout、install helper dry-run、cgroup declared／effective／runtime 分层、回并节奏及 rolling 后续边界。未修改候选、未安装或操作任何 unit、未触碰运行中的服务。
- **总体 verdict**：**修复 major 后可进入**。计划的技术方向总体可行，continuity、graceful timeout、rootless helper、cgroup 三层事实与 rolling 后续边界写得清楚；但它没有消费已经存在的两份独立评审、完全漏掉已复现的状态目录启动 major，并把回并放到所有强化切片之后，违背本线“骨架→真实 smoke→尽快回并→继续强化”的既定节奏。按下列建议修订计划即可继续实施，不需要改成传统 test-first／强制 TDD 流程。
- **blocker 数**：0。
- **major 数**：3。
- **minor 数**：2。
- **双视角覆盖证据——机械核对**：逐行对账计划的完成定义、事实区、living 看板、S0～S7、评审待办、验证命令、未采纳项和 kick-off；逐行核对两份 systemd 评审的 verdict 与 findings；从候选提交读取 `.service/.socket/.slice`、CLI 与测试原始 blob，确认 `Type=simple`、`KillMode=mixed`、无 `StateDirectory`、`--fd` 下界为 0 及静态 smoke 的真实状态；查本机 systemd 255 的 `systemd-socket-activate(1)` 与 `systemd.unit(5)`，核对 activator child 生命周期和 `Requires=` 停止／重启传播语义。
- **双视角覆盖证据——第一人称执行**：按计划从 S0 开始模拟实现者执行：先消费现有评审、修 unit、跑 rootless activation、在 service gap 建立新连接、让旧 accepted connection drain、对齐 stop deadlines、渲染 user units、读取 effective cgroup files、做 merged-state review 与回并；同时走了无可写 home、`--fd 0`、错误 `ExecStart`、main＋child stop、activator child 退出、listener owner 保持／退出、accepted 长连接超时、helper 默认执行、无 delegated cgroup、rolling readiness 失败与回切分支。该执行模拟暴露出“计划宣称尚无评审”“完整执行仍不修状态目录”和“强化全部结束前不回并”三处流程断点。

## 事实性发现

[major] `docs/agents/systemd-runtime/plan.md:28-37,82-88,127,145-170,325-338,364-366` — living plan 没有消费已经到达的两份独立评审，反而多处断言候选“尚未形成独立评审 verdict”并要求 S1 重新确认已确认方向 — `260807-review-code-systemd-runtime.md:1-17,30-32` 已给出 0 blocker／1 major／2 minor，`260807-systemd-socket-feasibility.md:1-8,52-72` 也已给出 0 blocker／1 major／2 minor；两份报告都支持 `Type=exec`，也都推荐 `KillMode=control-group`，只是对后者严重级别判断不同。现计划既没有记录该分歧的 disposition，也没有把共同结论转成直接下一动作，导致执行者重复评审并可能再次把已确认纠偏当成未决选择 — 将 S0 改为“已完成两份独立评审、尚未修复／未合并”，列出两份报告及其 findings；把 S1 改成直接实施 `Type=exec`＋`KillMode=control-group`、保留 readiness 独立 oracle，并对 KillMode 严重级别分歧注明“方向一致、仅分级不同，不阻塞纠偏”。每次修订后继续回写 HEAD、测试与复评 verdict，才符合 `LIVING` 身份。

[major] `docs/agents/systemd-runtime/plan.md:13-22,78-89,127-144,145-170,247-307,325-338` — 计划完全漏掉代码／部署评审已复现的默认状态目录启动 major，因此即使 S0～S6 全部按文执行，system account 仍可能在 FastAPI startup 阶段因 History 路径不可写而退出 — 候选 `.service` 没有 `StateDirectory=` 或等价固定可写目录；`260807-review-code-systemd-runtime.md:13-17` 已用 `HOME=/nonexistent` 复现默认 History 创建 `/nonexistent/.local/share/ghc-api-proxy/history.db` 时的 `PermissionError`。S4 只设计未来 rootless user-unit helper，不能闭合当前 system-unit 模板的状态目录；S2 还要求 health smoke，却未把“无可写 home 且默认 History 开启”设为正样本，所以 smoke 可通过显式临时 HOME 掩盖真实部署缺陷 — 在第一次可回并切片中加入确定状态目录：优先使用 `StateDirectory=ghc-api-proxy`，并把 History 与 tokenization 路径显式绑定到受管目录，或记录并测试等价安装合同；新增 `HOME=/nonexistent` 的真实 fd startup／readiness／落盘 smoke。把该项写入完成定义、看板、S1 修复范围、S2 smoke 和 merged-state gate，关闭后再谈候选可回并。

[major] `docs/agents/systemd-runtime/plan.md:82-89,298-307,400-416` — 计划把 S3 timeout、S4 install helper 与 S5 cgroup observability 全部放在 S6 回并之前，执行节奏实际是“骨架→所有强化→一次回并”，不是已定的“骨架→smoke→尽快形成可回并切片→继续强化” — S6 明确要求 S1～S5 组合后才进入回并流程，kick-off 也重复这一顺序。这样会把已经能独立交付的 fd／unit／rootless activation 基座与 public metrics、helper CLI、完整 shutdown 时间模型捆绑成一个大候选，扩大评审与重放面，也违背计划第 4.2 节自己声明的渐进节奏 — 把回并拆成至少两个里程碑：M1 在关闭现有评审 findings、完成真实 rootless activation／listener-gap／accepted-drain smoke并取得新 HEAD 0 blocker／0 major 后立即准备回并；M2 在已回并骨架上继续 S3～S5 强化，每片独立提交、测试、评审并更新 living plan。回并代码不等于部署，仍保持禁止安装与 cutover 边界。这里不要求传统 TDD；继续采用“骨架＋happy path→执行 smoke→回并→错误路径与完整强化”的节奏。

[minor] `docs/agents/systemd-runtime/plan.md:171-202` — S2 把 `systemd-socket-activate` 与“能在 child 换代期间继续自持同一 listener 的 harness”写成近似可互换，但默认非 `--accept` 的 activator 在首次连接后启动目标进程，不能直接承担计划第 183 行所需的独立、可重复 child supervisor 角色 — 本机 systemd 255 手册把它定义为监听后 launch child 的调试工具；计划第 183 行却要求终止应用、保持 harness 持有 listener、再启动新应用。实现者若用同一 `systemd-socket-activate` 进程完成两步，会在 child 生命周期处卡住或误测另一条路径 — 明确分成两个 probe：用 `systemd-socket-activate` 证明真实 activation 环境与 fd 3 happy path；用测试父进程自持并复制同一 listener fd，分别启动旧／新 child，证明 service gap 中 listener identity 与 queued connection continuity。若选择临时 user manager 代替后者，仍须保证自动销毁且不写真实 manager 持久状态。

[minor] `docs/agents/systemd-runtime/plan.md:127-170,186-202,325-338` — 已知 `--fd 0` 合同缺陷没有进入明确 disposition，只被 S2 的泛化“fd 不存在”负测间接覆盖 — 候选 `src/app/cli.py:53` 使用 `min=0`，但 Uvicorn 0.40.0 的绑定分支不会把 0 当继承 socket；`260807-review-code-systemd-runtime.md:15` 已将其列为 minor。`fd 不存在` 与“数值 0 被 CLI 接受却被依赖解释成无 fd”不是同一失败机制，泛化测试可能继续漏掉该回归 — 在第一次修复提交中把 `--fd` 下界改为 1，并增加精确 `--fd 0` 拒绝测试；在 findings disposition 表中标记关闭，不必等 S2 全套错误路径强化。

## 已核对且通过的轴

- `docs/agents/systemd-runtime/plan.md:41-66` 对 listener continuity、queued／unaccepted connection continuity 与 accepted connection graceful drain 的边界清楚，明确排除连接迁移、无限 backlog、客户端无限等待和单实例 rolling；未发现过度承诺。
- `docs/agents/systemd-runtime/plan.md:206-236` 没有用旧 `60s＋120s` 为 `330s` 背书，而是要求从 Uvicorn、signal、lifespan 与 cleanup 真实接线重建单一 deadline 公式，并覆盖正常 drain 与 force-timeout；方向可执行。
- `docs/agents/systemd-runtime/plan.md:238-257` 的 helper 默认 render／diff、显式 install、临时 HOME 测试、不自动 reload／enable／start 合同满足 dry-run 与无外部副作用边界。
- `docs/agents/systemd-runtime/plan.md:68-77,259-288` 正确分离 unit declared limits、cgroupfs effective limits 与 runtime events／metrics，并以 fake tree 作为稳定 CI 层、delegated user cgroup 作为可选 live probe；没有把 unit 文本冒充运行时事实。
- `docs/agents/systemd-runtime/plan.md:309-323,384-386` 把双实例／rolling 明确保留为后续独立设计，要求 readiness 切流、状态隔离、drain 与回滚，不把单实例 socket activation 冒充 rolling。该范围保留正确。
- `docs/agents/systemd-runtime/plan.md:102-117` 明确采用渐进开发而非强制传统 test-first；要求 smoke 与有判别力的回归 gate，但不让 TDD 阻塞骨架和 happy path，符合本线风格。

## 主观建议

[建议] `docs/agents/systemd-runtime/plan.md:78-89` — 为 living 看板增加“证据来源／review disposition／reviewed HEAD”列 — 预期影响是评审到达后不再只改自然语言状态，能机械看出某 finding 是 open、accepted、rejected 还是 closed，以及结论是否仍对应当前候选 — 推荐至少记录两份现有报告、候选 HEAD、各 finding 的 disposition 和下一次复评入口。

[建议] `docs/agents/systemd-runtime/plan.md:247-288` — 将 exact Prometheus metric API 的冻结与 reader／fake-tree 基础能力拆成两个提交 — 预期影响是 public metric 命名裁决不会阻塞 declared／effective 解析基础设施，且后者可先形成可回并、无公共 API 的内部切片 — 推荐先实现 typed reader 与测试，再经 observability 评审接入现有 telemetry。

## 结构怪味扫描

- `docs/agents/systemd-runtime/plan.md:28-37,82-88` — **living 状态与证据源漂移** — 本轮列为 major，要求消费两份现有评审并持续记录 disposition。
- `docs/agents/systemd-runtime/plan.md:13-22,78-89` — **完成定义遗漏真实 startup 前置** — 本轮列为 major，要求把状态目录纳入首次可回并切片。
- `docs/agents/systemd-runtime/plan.md:298-307,400-416` — **阶段聚合过大／回并门后置** — 本轮列为 major，要求拆出 smoke 后的早期回并里程碑。
- `docs/agents/systemd-runtime/plan.md:171-202` — **两个 harness 能力边界混写** — 本轮列为 minor，要求分开 activation happy path 与 listener-owner continuity probe。
- 其余扫描范围包括 timeout owner、helper 写入边界、cgroup reader 与 telemetry 职责、rolling 拓扑和验证矩阵；未发现需要用 ROI／YAGNI 缩减正确功能，也未发现应放弃 systemd／Uvicorn 现成机制而自造 supervisor 的理由。

## 继续实施条件

1. 回写两份既有评审及逐项 disposition，直接确认 `Type=exec`＋`KillMode=control-group` 的纠偏方向，同时保持 readiness 独立。
2. 把确定可写状态目录与 `--fd 0` 修复纳入第一次候选修订，并补对应运行／回归证据。
3. 将真实 rootless activation、listener gap 与 accepted drain smoke 作为首次回并门；修订后的候选 HEAD 独立复评达到 0 blocker、0 major 后即可继续回并实施，不必等待 S3～S5，也不必改成强制 TDD。
4. 回并后继续 graceful timeout、install helper 与 cgroup observability 强化；每片更新 living plan 并评审，最终再做组合态复核。

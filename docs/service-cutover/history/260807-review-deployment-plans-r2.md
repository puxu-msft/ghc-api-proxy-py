# Deployment living plans 联合定向复评 R2

- **评审范围**：稳定快照 `docs/agents/service-cutover/plan.md` 与 `docs/agents/systemd-runtime/plan.md`，仅复核各自上一轮报告 `docs/tmp/260807-review-service-cutover-plan.md` 的 4 项 major、`docs/tmp/260807-review-systemd-runtime-plan.md` 的 3 项 major，以及 living plan／non-TDD 渐进规则；联合对账两计划的状态、systemd 候选 HEAD、回并与 `localhost:4141` cutover 边界。本轮不重做 systemd、进程、socket、数据库、客户端或主机状态调查，不执行实现测试、安装、部署或 cutover。
- **总体 verdict**：**修复 major 后可进入**。两份 current plan 未消费 planner 修订：上一轮 7 项 major 均仍存在。当前只能继续其既有边界内的无副作用 inventory、仓库内实现、测试与 rootless／备用端口 probe；不得把本轮解释为候选通过、部署授权或 cutover 授权。
- **blocker 数**：0。
- **major 数**：7。
- **状态结论**：两份 plan **尚不能按修订完成态继续下一实施门**。关闭下列 major 并重新定向复评达到 `0 blocker／0 major` 后，应明确写为“**两份 living plan 可继续实施**”；该结论仍然**不是收口**，不表示计划封存、候选合规、已回并、已部署或 `localhost:4141` 可切换。
- **稳定输入证据**：两次连续独立读取均得到 service-cutover SHA-256 `52f285983cd55c10b4fbef9e4861e56f97fb2d18cd02e627c125cb9a69061f67`、systemd-runtime SHA-256 `789fa08696bc52241daa02547999e77b57983e3879feb52d5c0fcc46176f8ce0`；第二次读取机械比较通过。每次 shell 调用均在同一次调用内验证物理 root `/home/xp/src/ghc-api-proxy-py`、分支 `main`、HEAD `ed77c9d191df81c451c25161420515cca52ce6a4`。
- **双视角覆盖证据——机械核对**：逐项对照两份上一轮报告的 7 项 major 与 current plan 对应段落；扫描 review 状态、TDD／test-first 措辞、inventory asset ledger、旧 Bun supervisor fence、cutover／rollback deadlines、既有 systemd review provenance、状态目录、早期回并里程碑；验证两计划都引用 `feat/systemd-cgroup-runtime@66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`，本地 branch ref 也指向该 commit；对账禁止安装／部署与 `NO_CUTOVER` 边界。
- **双视角覆盖证据——第一人称执行**：分别模拟实施者从 service plan 的 inventory → 备用端口 → systemd dry-run → 数据 freeze → `4141` cutover，以及从 systemd plan 的 S0 → S1 unit 修订 → S2 smoke → 首次可回并骨架 → S3～S5 强化；再模拟 planner／实现者收到既有评审后更新 living 状态的路径。执行在 service plan 的强制 test-first、未逐项盘点资产、旧 supervisor 可复活和无冻结时间门处中断；在 systemd plan 的“尚未评审”、状态目录缺口与 S1～S5 全部完成后才回并处中断。

## 事实性发现

[major] `docs/agents/service-cutover/plan.md:10,77,109,133-139,456,486,492` — 上一轮 service M1 未关闭，且与 systemd plan 的 non-TDD 渐进规则直接冲突 — current service plan 仍写“独立计划评审尚未完成”，并以“先红后绿”“先写失败测试”“按 TDD 先写失败测试”“以测试先行”作为阶段或 kick-off 的普遍前置；`docs/agents/systemd-runtime/plan.md:111-114` 则明确“骨架＋happy path → 冒烟测试 → 尽快形成可回并切片”且不把传统 test-first 当作阻塞条件。实施者无法同时遵守两份计划 — 把 service plan 改为与 systemd plan 一致的 non-TDD 渐进合同：实现、测试与 living 状态同步推进；已有骨架可直接补强；只要求在 gate 标记 `PASS` 或进入下一有副作用阶段前具备有判别力的自动测试或真实 probe。保留阻断 gate 的正反控制与真实执行证据，但不规定测试必须先落盘。

[major] `docs/agents/service-cutover/plan.md:268-299` — 上一轮 service M2 未关闭，data disposition ledger 仍未逐项承接 current inventory 的全部可变资产 — current plan 未出现 `archive.db`、`telemetry.db`、`thinking-quarantine.db`、`learned-limits.json`、`negotiation-states.json`、`request-telemetry.json`、`system-prompts/` 与 `history-search/` 的逐项行，也没有 inventory asset ID 与 ledger ID 的集合相等 gate。实施者仍可仅关闭 History 主路径便误判“每项资产均有决定” — 从 current inventory 生成逐项 ledger，记录 producer／consumer、open fd／writer、格式、owner、disposition、备份／恢复 probe 和状态；新增资产默认将数据门恢复为 `UNVERIFIED`，并以资产 ID 集合精确相等作为退出门。

[major] `docs/agents/service-cutover/plan.md:333-349,397-404` — 上一轮 service M3 未关闭，首次接管前仍没有 current Bun `--restart` parent／child supervisor 的机械 fence — cutover 序列仍先“通过旧进程的精确 owner”停止，再检查端口；查自动拉起源仍放在退役阶段。若只停 listener child，parent 可在一次端口空读之后重拉旧 child／writer — 在 cutover 前识别并先冻结或停用已验证的 restart owner；要求 parent inactive 或 restart 被技术性 fenced，且旧 child、双栈 listener 与全部旧 writer 在连续观测窗口内未复活。rollback manifest 同步冻结恢复 supervisor 与 child 的确定顺序。

[major] `docs/agents/service-cutover/plan.md:87,323-369,375-390,442` — 上一轮 service M4 未关闭，计划仍使用“可立即回滚”“快速恢复”却没有机械时间门 — current plan 没有旧 listener 释放上限、systemd 双栈 listener 建立上限、新 readiness＋最小 canary 上限，以及回滚后旧 listener＋readiness＋真实请求恢复上限，也没有对应客户端 retry／timeout 预算与超限动作。半切换状态仍无法机械决定继续等待还是回滚 — 在 cutover 前冻结上述 deadlines，并在隔离演练实测；正式切换记录单调时钟时间线。若业务尚未裁决可接受中断／恢复目标，则保持 `NO_CUTOVER`，删除“立即／快速”声称并写“恢复时间未验证”。

[major] `docs/agents/systemd-runtime/plan.md:37,82-88,127,145-170,327-338,364-366,412` — 上一轮 systemd M1 未关闭，living plan 仍宣称“尚未形成独立评审 verdict”“未评审”，且未引用或 disposition 两份既有 systemd 评审 — current plan 没有 `docs/tmp/260807-review-code-systemd-runtime.md` 或 `docs/tmp/260807-systemd-socket-feasibility.md`，仍把 `Type=exec`＋`KillMode=control-group` 当作待重复确认的起点。living 状态与已存在证据漂移 — 把 S0 回写为“两份独立评审已完成、findings 未修复／未合并”，逐项记录报告、finding、disposition 与 reviewed HEAD；直接把 `Type=exec`＋`KillMode=control-group` 作为下一实施动作，注明两评审只在 `KillMode` 严重分级上不同、纠偏方向一致，同时保留 readiness 独立 oracle。

[major] `docs/agents/systemd-runtime/plan.md:13-22,34-37,78-89,145-202,287-307` — 上一轮 systemd M2 未关闭，默认状态目录启动缺陷仍未进入计划 — current plan 没有 `StateDirectory=`／等价确定可写路径，也没有 `HOME=/nonexistent` 的真实 startup／readiness／落盘 smoke。按 current S0～S6 执行仍可能让 system account 在默认 History 路径创建时退出 — 把确定状态目录与 History／tokenization 路径合同纳入首次可回并切片，并补 `HOME=/nonexistent` 的真实 inherited-fd startup／readiness／落盘 smoke及 finding disposition。

[major] `docs/agents/systemd-runtime/plan.md:82-88,287-307,412-416` — 上一轮 systemd M3 未关闭，声明的“尽快形成可回并切片”仍被实际阶段顺序否定 — S6 仍是唯一回并入口，kick-off 仍要求先完成 S1～S5，再 merged-state review 和准备回并。执行者会把 fd／unit／真实 activation 基座与 timeout、helper、cgroup observability 捆成一个大候选 — 拆为至少两个里程碑：M1 在关闭现有评审 findings、完成真实 rootless activation／listener-gap／accepted-drain smoke并取得新 HEAD 的 `0 blocker／0 major` 后立即准备回并；M2 在已回并骨架上继续 S3～S5，每片独立提交、测试、评审并更新 living plan。明确回并代码不等于安装、部署或 cutover。

## 联合一致性结论

- **一致**：`docs/agents/service-cutover/plan.md:36` 与 `docs/agents/systemd-runtime/plan.md:4` 都绑定 systemd candidate `66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff`；本地 `feat/systemd-cgroup-runtime` ref 也指向该 commit。
- **一致**：service plan 保持 `NO_CUTOVER`，systemd plan 禁止安装、启用、启动、停止或替换任何 system／user unit并禁止触碰 current `copilot-api-js`；仓库内回并与运行态部署／`4141` 接管被正确分离。
- **不一致**：service plan 强制 test-first／TDD，systemd plan 明确 non-TDD 渐进节奏；见第一项 major。
- **不一致**：两份 plan 都是 living 文档，但仍把已存在的独立评审写成尚未完成／不存在，无法作为 current 状态真相源；关闭各自 review provenance major 后需同步更新时间、candidate HEAD、finding disposition 与下一动作。

## 主观建议

未新增主观建议。本轮严格限制为上一轮 majors、living／non-TDD 渐进规则及两计划联合边界复核，不扩展系统调查或引入新范围。

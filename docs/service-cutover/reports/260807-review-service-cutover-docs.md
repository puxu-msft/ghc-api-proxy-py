# Service cutover Plan／Readiness current 稳定快照联合评审

- **评审范围**：`docs/agents/service-cutover/plan.md` SHA-256 `ab840f2a37407877bc1c6c9526ff811ab7364e795012ffad0596927f3a3a4765` 与 `docs/agents/service-cutover/readiness.md` SHA-256 `483396dbccc0c9786f3696a11de454a76fedb1a4bbf6dae0d38f0b9d4f490d67` 的 current 稳定快照。联合对账 Plan R2、current inventory、Anthropic Responses Spec／Acceptance／Implementation、systemd runtime plan／code R2，以及 current systemd 候选身份；未执行服务、socket、systemd、数据、认证、网络、进程或 cutover 操作。
- **总体 verdict**：**修复 major 后可进入**。Plan R2 对同一 Plan bytes 的 `0 blocker／0 major` 结论仍成立；两文档也持续可靠地保持 `NO_CUTOVER／FOUNDATIONS_ONLY`。但联合态的 current 输入身份与 systemd 候选已经漂移，且 43 行 readiness 矩阵没有为 Acceptance 的 required limits／backpressure gate 建立行级状态与下一证据动作。因此当前不能给出“两文档 0 major、可直接继续动态实施”的结论。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **稳定快照证据**：每次有效 shell 调用均在同一次调用内验证物理 root 与当前目录为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。Plan／Readiness hash 均由 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉复核一致，写报告前再次采样未变化。
- **双视角覆盖证据——机械核对**：完整读取两份目标文档；对账精确绑定同一 Plan hash 的 `docs/tmp/260807-review-service-cutover-plan-r2.md`、current inventory、Spec、Acceptance、Implementation、systemd runtime plan与code R2；扫描 living／non-TDD、`NO_CUTOVER`、`FOUNDATIONS_ONLY`、数据、认证、systemd、rollback、`cc-daemon`及完整 Anthropic→Responses gate。Readiness 行数由 Python 分节解析与独立 `awk` 计数两种方法交叉验证，均得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43。另核对 current systemd worktree为 clean `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`，其 HEAD 已含 `StateDirectoryMode=0700`与`UMask=0077`，但主树尚无绑定该 HEAD 的 R3 报告。
- **双视角覆盖证据——第一人称执行**：模拟实施者从 Plan“下一最小动作”进入 foundations回放、备用端口、user systemd、数据 disposition、完整替代验收、旧 supervisor／listener／writer fence、`4141`接管、自动rollback、观察与退役；另模拟 readiness 行逐项升级、candidate／oracle漂移、43行全部关闭、局部0／0拼接、认证provider会写refresh、SQLite新增资产、单地址族、旧parent复拉、rollback超时及`cc-daemon`身份变化。当前文档能拦截生产切换和大多数假绿，但会把systemd下一动作导向已经完成的权限实现，并在P0行级矩阵中漏掉required容量门。

## 事实性发现

[major] `docs/agents/service-cutover/plan.md:10,36,39,515-520`；`docs/agents/service-cutover/readiness.md:9,40-43,72,147-151` — current living 状态链条落后一轮，Plan／Readiness绑定的评审、Implementation与systemd候选不再是现场current事实 — Plan R2已精确绑定本轮Plan SHA-256并给出`0 blocker／0 major`，但Plan仍写`READY_FOR_REREVIEW`并把再次复评列为第一下一动作；Readiness声称current Implementation SHA-256为`052bda8eea562ffee40bb9106d999832c4c98149b5508b5bd7090ccf85a748e0`，现场实际为`16b10e69ec0fc2b38921b96da54828478d9c13889c2fdc6a1e917f9bd4a8122f`。Plan仍把systemd候选写成`66551e45…`，Readiness则绑定`1a220e04…`并要求实现`UMask=0077`／`StateDirectoryMode=0700`；现场clean候选已前进到`49fb1988621bba4356e7a5039a6994c2e6d19604`且包含这两项修复，但尚无绑定该HEAD的R3 verdict。Plan还写“current Spec要求新的targeted rereview”，而current Spec已是`FINALIZED@5e362822…`、Acceptance已是`FINALIZED_ACCEPTANCE_ORACLE@224b020d…`；产品仍是`UNVERIFIED`，但oracle文档门已经关闭 — 照文档执行会重复实现已完成的权限修复、继续等待已完成的Plan／Spec复评，并漏掉真正下一门“对`49fb198…`做独立R3、再决定能否squash”。这不会直接授权cutover，故不是blocker；但它破坏了readiness作为实时真相源和Plan作为下一动作来源的核心用途 — 消费Plan R2并更新Plan评审状态；把Spec／Acceptance状态改为current finalized但产品`UNVERIFIED`；将Implementation hash重绑current bytes并逐行检查其状态变化；把systemd current候选改为`49fb198…`，明确“权限修复已实现、尚待R3，不得预写0／0”，下一动作改为R3复评及其后按verdict推进。任何后续candidate／input漂移继续按Readiness自身规则把受影响行退回`UNVERIFIED`。

[major] `docs/agents/service-cutover/readiness.md:47-64`；`docs/agents/service-cutover/plan.md:316-331`；`docs/agents/anthropic-responses-bridge/acceptance.md:39,239-244` — 43行矩阵的数量真实，但P0语义覆盖不完整：Acceptance required的limits／backpressure域没有独立行级状态、owner与next smoke — 两种独立计数均确认Readiness确有43行，且P0十行覆盖route、request、response、buffering／delivery、retry、usage、error、tool、reasoning与lifecycle；但全文只有shutdown admission和observation capacity的零散提及，没有承接`REL-06`冻结的普通per-request aggregate＋global resident reservation、有限queue、charge-before-read、两级计账、backpressure、capacity／deadline／cancel终态及拒绝新admission。Plan“完整bridge产品”总门和Readiness P0退出段都引用Acceptance全部required gates，因此该缺口不会让实际cutover合法放行；然而第一人称逐行执行时，实施者无法从43行矩阵知道容量gate当前状态、owner、最小正反控制或candidate漂移影响，矩阵也无法诚实声称逐项表达完整替代readiness — 保持43行口径，不必机械新增第44行；把现有“Block-level buffering／continuous prefix／delivery frontier”扩为“Block-level buffering／delivery frontier／resident budgets与backpressure”，在evidence中明确`REL-06`当前为`UNVERIFIED`，owner增加request／global memory quota与admission owner，next smoke加入配置化`request_budget < global_budget`、多resident owner聚合、global-only与single-block／16MiB两种单侧变异、慢consumer、有限queue、charge／release归零、容量恢复和拒绝新admission。同步在Plan替代验收门中显式点名limits／backpressure，避免只靠“Acceptance全部required gates”这一汇总引用隐藏该必需域。

## 已通过的联合轴

- **Living／non-TDD**：通过。Plan明确采用骨架→happy path→真实smoke→尽快squash未集成纵向切片→边界／fault／正反控制，不把传统test-first设为普遍准入门；状态升级前仍要求能区分正误的自动测试或真实probe。
- **`NO_CUTOVER`**：通过。两文档均明确不授权停止旧服务、释放或绑定生产`4141`、安装／启动unit、reload manager、迁移／删除数据或触碰`cc-daemon`；P3生产动作持续为`NO_CUTOVER`。
- **`FOUNDATIONS_ONLY`**：通过。局部converter／parser／carrier／liveness／systemd评审均未被拼成完整产品`PASS`；同一candidate、config、unit bytes、inventory与data disposition原则明确。
- **43行矩阵诚实性**：数量通过，语义完整性因第二项major未通过。当前精确口径为P0 10、P1 8、P2 11、P3 12、`cc-daemon` 2，共43行；没有虚报第43行，但缺少required容量域的行级承载。
- **数据与认证**：通过当前保守状态。Inventory＝ledger集合门、SQLite主文件／WAL／SHM、逐项disposition、backup／restore、writer fence、config语义迁移与GitHub credential refresh唯一owner均保持`IN_PROGRESS`／`UNVERIFIED`／`NOT_STARTED`，没有把只读复用或`ABANDON`解释成可删除。
- **systemd与前门**：边界通过、current身份需修。User unit、双fd／双栈、readiness、graceful、cgroup与生产`4141`均未被局部system-level单socket模板冒充；当前candidate漂移归入第一项major。
- **rollback与旧runtime**：通过。旧`--restart`supervisor、child、双栈listener、writer三重fence，配置化deadline、完整旧启动件恢复、自动rollback触发、观察baseline与退役顺序均未被一次`ss`空结果或只kill listener替代。
- **`cc-daemon`**：通过。其两个unit与活会话树始终是只读外部不变量，不是canary、修复或rollback工具；任何PID／`InvocationID`变化都会停止阶段。
- **完整Anthropic→Responses替代门**：除limits／backpressure行级缺口外，其余关键域均有保守状态与真实入口下一证据动作；Spec／Acceptance current oracle本身已定稿，候选产品仍明确`UNVERIFIED`。

## 主观建议

无。本轮两项发现均由current文件、内容hash、候选HEAD、既有独立报告和required gate对账直接支持，不需要以主观偏好扩大或缩减范围。

## 结论

本轮为`0 blocker／2 major／0 minor`。Plan R2的`0 major`结论仍有效，但新建Readiness与其联合current输入尚不能一起判为`0 major`。关闭上述两项major并完成定向复评后，若结果为`0 blocker／0 major`，两份living文档即可继续动态实施、无副作用inventory、仓库内实现、备用端口与rootless／隔离runtime验证；该结论仍只放行下一实施切片，**不是candidate产品`PASS`、不是部署完成，更不是`localhost:4141` cutover授权**。实际cutover必须在P0～P3全部门绑定同一冻结候选闭合后，由用户对当次生产动作另行明确授权。

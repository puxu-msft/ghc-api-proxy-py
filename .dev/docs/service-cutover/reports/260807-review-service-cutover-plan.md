# service cutover living plan 独立评审

- **评审范围**：主树 `main@ed77c9d191df81c451c25161420515cca52ce6a4` 上未跟踪的 `docs/agents/service-cutover/plan.md`，对照 `docs/tmp/260807-current-service-cutover-inventory.md`、current systemd 候选计划及既有 socket 可行性／代码评审证据。重点复核渐进切片、备用端口、smoke／live、socket dry-run、数据 disposition／writer fence、可回滚 `localhost:4141` 切换、观察／退役、不可声称边界与替代验收门。本轮未执行服务、socket、systemd、数据库或网络状态变更。
- **总体 verdict**：**修复 major 后可进入下一实施门**。当前允许继续无副作用 inventory、仓库内实现、备用端口与隔离 dry-run，但不得进入生产 `4141` 切换。即使后续达到 `0 blocker／0 major`，该 verdict 也只批准 living plan 继续实施，不代表计划收口、候选验收通过或 cutover 获得授权。
- **blocker 数**：0。
- **major 数**：4。
- **评审基线**：评审时 `plan.md` SHA-256 为 `52f285983cd55c10b4fbef9e4861e56f97fb2d18cd02e627c125cb9a69061f67`；每次取证 shell 均在同一调用内验证物理 root、`main` 与完整 HEAD。
- **双视角覆盖证据——机械核对**：逐节扫描计划的状态、切片矩阵、TDD／验证措辞、inventory、数据 ledger、替代验收门、cutover／rollback 序列、观察／退役和 kick-off；逐项对账 current inventory 中的双栈 Bun listener、`--restart` 父子进程、`cc-daemon` 禁触碰边界、打开的 `history-v3.db` WAL writer、其他 SQLite／状态资产以及 systemd 候选限制；检查 current 引用文件存在性和不可声称边界。
- **双视角覆盖证据——第一人称执行**：按实施者身份走完“重取 inventory → 隔离备用端口 → 协议 smoke／live canary → user socket dry-run → 数据 freeze → 停旧 listener → systemd 双栈接管 → 新服务失败回滚 → 观察 → 退役”主路径，并分别模拟旧 Bun 父进程因 `--restart` 拉起新 child、非 History 状态库仍有 writer、首切 readiness 超时、回滚恢复过慢、已 accept 长连接断开及 `cc-daemon` 身份变化分支。

## 事实性发现

[major] `docs/agents/service-cutover/plan.md:77,107-109,133-139,227-233,486,492` — 计划把 TDD／“先红后绿／先写失败测试”设成所有实现切片和 kick-off 的普遍前置纪律，与本任务已定的“不要要求 TDD；living plan 应支持随写随做”直接冲突 — 实施者照文末 kick-off 执行时，即使已有骨架、运行态 probe 或可并行实现路径，也会被要求先补失败测试；这会把测试编排方式误当成阶段准入条件，而不是在状态提升前必须补齐的证据 — 删除普遍的 TDD 强制措辞，将节奏改为“实现、测试与 living plan 同步推进；已有骨架可直接补强；每个 gate 在标记 `PASS` 或进入下一有副作用阶段前必须具备能区分正确／错误状态的自动测试或真实 probe”。保留高风险 gate 的正反控制、mutation 与真实执行证据，但不规定测试必须先于实现落盘。

[major] `docs/tmp/260807-current-service-cutover-inventory.md:56-64` 对比 `docs/agents/service-cutover/plan.md:268-291` — 数据 disposition ledger 没有逐项承接 current inventory 已发现的旧可变资产，因而“每项资产均有决定”的退出门可被不完整清单假绿 — inventory 明列 `archive.db`、`telemetry.db`、`thinking-quarantine.db`、`learned-limits.json`、`negotiation-states.json`、`request-telemetry.json`、`system-prompts/`、`history-search/` 及多代 History；ledger 只专列旧 History、新 History、泛化的搜索索引／cache、凭据、配置、连接、日志和临时文件，没有为这些资产逐项记录 producer、当前 open fd／writer、schema／格式兼容性、切换 owner、备份与回滚语义 — 执行者可把 `history-v3.db` 安全冻结后误判数据门完成，而独立 telemetry／archive／quarantine writer 或状态文件仍被旧进程写入，造成双写、丢状态或无法按旧版本回滚 — 让 ledger 从 current inventory 生成逐项资产行，至少为每个数据库及 WAL／SHM、每个状态 JSON／目录记录 producer／consumer、writer fence 观测点、disposition、备份／恢复 probe 与状态；增加集合相等 gate，要求 inventory 的全部可变资产 ID 与 ledger ID 精确对账，新增资产默认使数据门回到 `UNVERIFIED`。

[major] `docs/tmp/260807-current-service-cutover-inventory.md:21-30` 对比 `docs/agents/service-cutover/plan.md:16,98-105,340-344,400-402` — 首次接管序列没有把 current Bun 的 `--restart` 父子监督关系转化成切换前的机械 fence — inventory 证明 listener child 与父进程都以 `start --restart` 运行，但计划第 4 步只要求通过“旧进程的精确 owner”发起 graceful stop，第 5 步随即检查端口释放；若只停止持有 socket 的 child，仍存活父进程可能在 systemd socket bind 前或 bind 后重拉 Bun，产生端口争抢、旧 writer 复活或错误地把瞬时无 listener 当作 freeze 成功。退役阶段才查自动拉起源，时序过晚 — 在 inventory 退出门中明确识别 parent／child／supervisor 的 restart 合同与精确停止原语；在旧 child 停止之前先冻结或停用已验证的旧 restart owner，并以“父进程身份不再活动或 restart 被技术性 fenced＋旧 child／listener／全部旧 writer 在连续观测窗口内未复活”为 cutover gate。rollback manifest 必须包含恢复该 supervisor 与 child 的确定顺序；不得只凭一次 `ss` 空结果进入新 socket bind。

[major] `docs/agents/service-cutover/plan.md:323-369,375-390,442` — 计划承认首次接管有监听窗口并多次使用“立即回滚／快速恢复／可立即回滚”，但没有冻结可机械执行的 cutover 与 rollback 时间门 — 当前只有新服务 readiness 的“已冻结上限”，没有定义从旧 listener 释放到新双栈 listener／readiness／关键 canary 成功的总上限，也没有定义触发回滚后旧双栈 listener、旧 readiness 和真实请求恢复的上限；current inventory 也明确不得声称恢复时间目标已满足 — 实施者面对半切换状态时无法机械判断何时停止等待并回滚，观察记录也无法证明“窗口缩短”或“快速恢复” — 在切换前冻结至少四个 deadline：旧 listener 释放上限、systemd 双栈 listener 建立上限、新服务 readiness＋最小 canary 上限、回滚后旧 listener＋readiness＋真实请求恢复上限；同时冻结客户端重试／timeout 预算和超限动作。备用端口／隔离演练必须实测这些门，正式切换记录单调时钟时间线。若业务尚未裁决可接受中断与恢复目标，则保持 `NO_CUTOVER`，并删除“立即／快速”声称，只写“恢复时间未验证”。

## 已覆盖的关键面

除上述 major 外，计划已形成可继续补强的执行骨架：切片顺序保持渐进且允许 inventory、bridge、systemd 与数据研究并行；备用端口与数据根隔离明确；smoke／live 同时覆盖真实 HTTP、SSE、WebSocket、SDK、strict grammar、local fault 与副作用边界；socket dry-run 区分静态 verify、真实 fd activation、双栈、多 fd、readiness、graceful shutdown 与 cgroup；首次切换不声称零停机或 accepted connection 迁移；`cc-daemon` 明确禁触碰并设 PID／`InvocationID` 不变量；回滚、观察和退役保持串行，旧资产默认只读保留而非删除；替代验收门拒绝用局部测试、旧 hash 或 helper-only 证据替代完整产品验收。

## 结论

当前为 `0 blocker／4 major`，可继续 living implementation，但不可进入 `localhost:4141` 生产切换。关闭上述 major 后应重新评审修订后的 merged plan；若复评达到 `0 blocker／0 major`，结论仅为“可继续实施下一切片”，不等于计划封存、最终候选 `PASS`、服务已部署或 cutover 已获授权。

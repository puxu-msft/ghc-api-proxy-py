# Stream facts living checkpoint 联合定向复评

- **评审范围**：联合定向复评主树 `/home/xp/src/ghc-api-proxy-py` 的 `docs/agents/anthropic-responses-bridge/implementation.md`，精确 SHA-256 `1fe507f6004d330d6d23cdeccf843d95c39b3d8b565a31efdceaa06ba5676c56`；以及 `docs/agents/service-cutover/readiness.md`，精确 SHA-256 `8aaa4c17d55f95b733628bd87aed29e0f49c9817d838bab010b467c3361db32f`。仓库基线固定为 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28`。本轮只核对 `4fa7a87…` final review 为 0 major、可以 squash 但尚未进入 main，current-main backup smoke 的范围与缺口，以及下一 checkpoint → squash／main-side gate；同时检查其余 S3／S4／S5、`LIVING／UNVERIFIED／NO_CUTOVER` 没有状态漂移。不重审候选代码，不重跑 backup smoke；为核实两份文档新增转述的全量回归事实，本轮在 exact `4fa7a87…` 上重跑全量 pytest与 collect-only。未执行 checkpoint、squash、Git ref、安装、manager、部署或 cutover 操作。唯一工作树写入为本报告。
- **总体 verdict**：**可进入下一阶段。两份文档均为 0 blocker／0 major，可以共同形成 living checkpoint。**
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **checkpoint 裁决**：上述两个精确内容身份可以 checkpoint。该 checkpoint 只冻结 `main@e9fb277…` 下的 current living 状态；不表示 `4fa7a87…` 已进入 main、main-side gate 已通过、完整 bridge／Acceptance 已 `PASS`、S5 已解除阻塞、unit 已安装、部署完成或 cutover 获授权。

## 双视角覆盖证据

### 机械核对

- 每个承载事实的 shell 调用均在同一调用内核验物理 cwd、Git top-level、branch `main`、`HEAD == refs/heads/main` 与完整提交 `e9fb2771d6e040c761bb4074e3fcf2547caece28`。两份目标文档的 SHA-256 分别用 `sha256sum` 与 Python `hashlib.sha256` 交叉复核，均与本报告绑定值一致；`git diff --check` 通过。
- Git 拓扑核验确认 `refs/heads/fix/stream-request-facts` 精确指向 `4fa7a87728376f14bd84b4b5853f8212d5bc786b`，其直接 parent 为 current `main@e9fb2771d6e040c761bb4074e3fcf2547caece28`，且 `4fa7a87…` 不是 `main` 的祖先，因此候选确实尚未进入 main。
- `docs/tmp/260807-review-stream-request-facts-r2.md` 精确绑定 `4fa7a87…`，原文 verdict 为 `0 blocker／0 major／1 minor`、明确“可以 squash”；其唯一 minor 是无 projection 普通失败测试未注入非空 request fact，不是现存行为错误，也不阻断 squash。`docs/tmp/260807-arbitrate-stream-request-facts.md` 同时确认 completed、post-commit partial failure 与 delivery-uncertain 均应保留最终 selected attempt 的 request conversion observations。
- `docs/tmp/260807-final-backup-port-smoke-r2.md` 对 current `main@e9fb277…` 的精确 verdict 是 `PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`；`docs/tmp/260807-review-final-backup-port-smoke-r2.md` 将其独立归纳为 `0 blocker／0 major／1 minor`。两份目标文档均保留唯一 stream History request-facts 缺口，并明确不覆盖 semantic reorder、完整 usage／terminal／History 矩阵、retry、quota／resident backpressure、真实 socket partial-write／RST、完整 shutdown 竞态、持久化 harness／变异控制或完整 Acceptance。
- 两份文档在顶部状态、进度／矩阵、活动线、收敛规则、下一步、结构怪味与结尾摘要中的重复承载一致：`4fa7a87…` 已完成 0-major final review且可以 squash；候选尚未 main；下一门统一为先形成本轮 living checkpoint，再执行 squash／main-side identity、preimage、声明范围与回归／组合 gate。6 个定向 case来自候选终审的 execution／collect-only与 base正样本对照；由于既有仓库报告没有保存“全量 590 项”绑定 exact候选的原始出处，本轮在 `/home/xp/src/ghc-api-proxy-py-stream-facts` 重新核验 physical root、branch与 exact HEAD后执行全量 pytest，结果为 `590 passed in 17.52s`；独立 collect-only结果为 `590 tests collected in 2.19s`。两次退出码均为0，候选工作树 status digest前后均为空树 SHA-256 `e3b0c442…`。该证据支持声明范围回归已绿，但不替代 checkpoint后的 main-side gate，也不把祖先 main上的 backup smoke冒充候选真实入口复跑。
- 受保护状态对账未见漂移：S3 `c53849e…` 与 S4 `e9fb277…` 均保持已进入 main并归档；S5 保持因独立 manager 未创建 private control socket而 `BLOCKED`，下一入口仍是可销毁容器或虚拟机；Implementation 保持 `LIVING`，完整产品保持 `UNVERIFIED`，部署保持 `NO_CUTOVER`。Readiness 从旧 `FOUNDATIONS_ONLY` 提升为 `NO_CUTOVER／PARTIAL` 有 current-main R2真实主路径 scoped PASS 支撑，同时 P0 仍为 `PARTIAL`、P1 仍为 `FOUNDATIONS_ONLY`，没有升级为完整域或产品 `PASS`。
- Readiness 行数由 Python 分节解析与独立 `awk` 状态机两种方法交叉验证，均得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43；两个目标文档中的本地 Markdown 链接解析缺失数为 0。

### 第一人称执行模拟

1. **作为 living checkpoint 执行者**：我会提交这两份精确 bytes 与本报告，只冻结 current 状态；不会把 checkpoint 读成文档收口、候选已 main、S5 已完成或完整产品已通过。
2. **作为 stream request facts 收敛执行者**：checkpoint 后先重新核验 `4fa7a87…` identity、current-main parent／preimage、声明范围与当时工作树，再形成 squash并运行 main-side回归／组合复核；在这些门完成前，任何入口都仍要求写“候选尚未 main”。
3. **作为 backup smoke 结果使用者**：我只能把 `e9fb277…` 读取为关键主路径 scoped PASS，并保留唯一 stream History request-facts缺口；即使 `4fa7a87…` 进入 main，也只能关闭该定向缺口，不能跳过 semantic reorder、完整 usage／terminal／History、retry、quota／backpressure、真实 partial-write或完整 Acceptance。
4. **作为 systemd 后继执行者**：我不会重复 S3／S4 回放；S5 仍从 current main在具备独立 user manager与 delegated cgroup v2 的可销毁环境续诊，不会退回宿主 user manager，也不会把仓库绿灯外推为 unit运行态、部署或 cutover证据。
5. **作为生产切换执行者**：`NO_CUTOVER`、P0 `PARTIAL`、P1 `FOUNDATIONS_ONLY`、S5 `BLOCKED`、P2／P3未闭合与 `cc-daemon` 禁触碰边界会持续阻止停止旧 Bun、抢占生产 `4141`、安装／启动 unit、迁移数据或执行切换。

## 事实性发现

未发现问题。

- `4fa7a87…` 的候选身份、直接 parent、未进入 main状态与 0-major final review／可 squash verdict均有独立上游证据支持。
- Backup smoke 的 scoped PASS、唯一 facts缺口与未验证矩阵在两份文档中保持完整，没有被洗成候选或完整产品 `PASS`。
- 下一动作在所有 current 承载点均收敛为 living checkpoint → squash／main-side gate，没有遗漏 main-side关闭条件或提前声明候选已 main。
- S3／S4／S5、`LIVING／UNVERIFIED／NO_CUTOVER` 的 current事实与执行边界一致；Readiness 的 `PARTIAL` 升级有真实 scoped smoke依据，同时没有放宽任何完整产品或生产门。

## 主观建议

无。

## 结构怪味扫描与方法复盘

- **扫描范围**：两份目标文档的 current-state入口、状态表、下一动作、结构怪味和结尾摘要，以及四份直接上游报告和候选 Git拓扑。判据为重复状态是否弱一致、局部 PASS是否外推、已完成项是否仍列为待办、候选是否被提前写成已 main、S5是否被仓库证据误升级、以及下一执行顺序是否跳过 main-side gate。未发现新的结构怪味；两份文档已显式登记多点复述风险，本轮各承载点保持一致。
- **更好的内部替代方案**：本轮目标是精确 living checkpoint，不宜借机重构两份大型状态文档。当前“顶部 current 状态＋详细矩阵／下一步”的结构可执行，后续仍应优先更新顶部入口并同步所有副本。
- **判据判别力**：错误状态不能通过的反例包括把 `4fa7a87…` 写成已 main、把 backup smoke 写成完整 Acceptance `PASS`、把 S5 写成运行态通过或省略 main-side gate；正确状态也不能被误拒，即 current-main关键主路径确已取得 scoped PASS，Readiness 因此可从 `FOUNDATIONS_ONLY` 提升为有明确上限的 `PARTIAL`。当前文本同时满足两侧。
- **成熟第三方方案**：本轮是仓库内部 living 状态与证据链对账，不涉及可由第三方库替代的实现机制。

## 最终结论

**Implementation SHA-256 `1fe507f6004d330d6d23cdeccf843d95c39b3d8b565a31efdceaa06ba5676c56` 与 Readiness SHA-256 `8aaa4c17d55f95b733628bd87aed29e0f49c9817d838bab010b467c3361db32f` 在 `main@e9fb2771d6e040c761bb4074e3fcf2547caece28` 上联合为 `0 blocker／0 major／0 minor`，两文件可以形成 living checkpoint。** `4fa7a87…` 已完成 0-major final review并可 squash，但尚未进入 main；backup smoke仍是带唯一 stream History request-facts缺口的 scoped PASS；下一动作固定为 checkpoint后执行 squash／main-side gate。S3／S4／S5与 `LIVING／UNVERIFIED／NO_CUTOVER` 边界未漂移。

## 报告评审状态

本会话是叶子 reviewer，不能派生另一名 reviewer。本报告已完成事实证伪、双视角执行模拟与写后自查；按 wrap-up artifact规则，主会话仍须对本报告中的 current-state断言安排独立复核。该义务不改变本轮对两份被评 exact bytes的 `0 blocker／0 major`与可 checkpoint结论，但不能把本报告自述冒充报告文本自身已经取得二次评审。

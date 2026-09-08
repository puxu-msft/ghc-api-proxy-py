# Living checkpoint current tracked modifications 只读审计

- **评审范围**：固定 `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`，只读审计 current tracked modifications：`docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/service-cutover/plan.md`、`docs/agents/service-cutover/readiness.md`、`docs/agents/systemd-runtime/plan.md` 与 `docs/agents/anthropic-responses-bridge/README.md`。核对每文件 HEAD／index／worktree 三层身份、current-byte 最新 0-major 报告、checkpoint 范围、README 修订后的复评路由，以及精确 `git add` 集合是否会夹带 `docs/tmp/**` verification 证据。未修改五份被审计文档，未修改 index，未执行部署、服务、systemd、网络、数据或 cutover 操作；唯一写入本报告。
- **总体 verdict**：**修复 major 后可进入完整五文件 checkpoint；三份已有 current-byte 0-major 证据的 living 文档可先形成独立 checkpoint。** `implementation.md`、`service-cutover/readiness.md` 与 `systemd-runtime/plan.md` 已被 current-byte 联合 R2 放行；`service-cutover/plan.md` 与新版 `README.md` 没有绑定当前 SHA-256 的 0-major 报告，不能借用旧报告或本轮集合审计冒充既有复评证书。README 修订后应做 `README.md`＋`implementation.md` 的 living-docs R3 定向联合复评；Service-cutover Plan 应与 current Readiness 做联合 R3，消费旧联合 R2 的状态链 major。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：1。
- **checkpoint 结论**：当前可直接依据既有报告 checkpoint 的精确三文件集合是 `implementation.md`、`service-cutover/readiness.md`、`systemd-runtime/plan.md`。`service-cutover/plan.md` 与 `README.md` 内容审计未发现新的状态外推错误，但在各自 current-byte 复评完成前不得加入该已证 checkpoint。完整五文件 checkpoint 需两个复评路由均达到 0 blocker／0 major。

## 双视角覆盖证据

### 机械核对视角

1. 每次 shell 调用均在同一调用内验证物理 root 与当前目录为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 精确为 `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。
2. 对五份目标逐一取得 `git status --porcelain`、HEAD blob、index blob、worktree blob 与 SHA-256。五文件均为 ` M`，即 index 与 HEAD 相同、仅 worktree 修改；当前 index path 数为 0，`git write-tree` 在审计前后均为 `fa084a0790a2fab84ac8e59a641fc37842474edb`。
3. 五份 SHA-256 均由 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉核对一致。报告匹配不是按文件名或修改时间推断，而是以报告正文是否包含目标 current SHA-256 为门。
4. 反查 `docs/tmp` 得到：Implementation `60e09d3b…`、Readiness `a8abccf4…` 与 Systemd Plan `6646cb72…` 均由 `docs/tmp/260807-review-living-after-main-replay-r2.md` 绑定并给出 0 major；Systemd Plan 还由 `docs/tmp/260807-review-systemd-runtime-plan-r5.md` 独立绑定并明确可 checkpoint。Service-cutover Plan `6644126a…` 与 README `eb52f5a4…` 均没有 current SHA 报告命中。
5. 对精确五路径候选集合和精确三路径已证 checkpoint 集合分别做集合检查。当前未跟踪 `docs/tmp` 中名称含 `verify`／`verification` 的证据文件共 10 份；它们与两个显式目标集合的交集均为 0。数字口径是当前 `git status --porcelain=v1 --untracked-files=all -- docs/tmp`，并由 shell 与 Python 集合运算交叉验证。
6. 完整读取五份 current bytes及其 diff，扫描 `main`、archive、happy、usage、`UNVERIFIED`、`NO_CUTOVER`、`FOUNDATIONS_ONLY`、checkpoint、living、收口、下一动作与重复回放表述。未发现把 foundations／systemd 已进入 main 错写为完整产品 `PASS`，也未发现把 happy／usage candidate-side 证据错写为 main-side 或 cutover 授权。

### 第一人称执行视角

1. 以接手实现者身份从 current `main` 按文档顺序执行：foundations 与 systemd 不重复回放；先消费 happy 四片并逐片 main-side gate，再消费 child usage，随后进入 route wiring。README、Implementation、Systemd Plan 与 Readiness 在这条顺序上相容。
2. 以部署执行者身份沿 Service-cutover Plan／Readiness／Systemd Plan 执行：仓库 M1 checkpoint 不等于 unit 已安装、manager 已改变或生产 `4141` 可抢占；Readiness 保持 `NO_CUTOVER／FOUNDATIONS_ONLY`，`cc-daemon` 与现服仍在禁止触碰边界内。
3. 以提交执行者身份模拟精确暂存：显式列出三个已证路径时，Git 不会递归扩张到 `docs/tmp`；显式列出全部五个目标路径时同样不含 verification 文件。但是五路径集合的内容证书尚不齐，路径安全不等于 checkpoint 已获放行，因此当前应优先使用三路径集合，或等待两个复评闭合后再使用五路径集合。
4. 以文档维护者身份处理 README 修订：旧 `docs/tmp/260807-review-living-bridge-docs-r2.md` 绑定 README `2de36b12…` 与 Implementation `4ace3022…`，不能覆盖当前 README `eb52f5a4…`。所需复评是两份 living 入口的 current-byte R3 定向联合复评，重点验证 README 对 Implementation 最新事实的导航转述、foundations／systemd 已入 main、happy／usage 尚未入 main、产品仍 `UNVERIFIED`；不需要重做 Spec／Acceptance 全文终审。

## 文件状态、报告与 checkpoint 矩阵

| 文件 | Git XY | HEAD blob／index blob | Worktree blob | Current SHA-256 | 最新有效 current-byte 0-major 报告 | 结论 |
|---|---:|---|---|---|---|---|
| `docs/agents/anthropic-responses-bridge/implementation.md` | ` M` | `0529ec2fffa1ae9506bb880dd3929c5fe6aa4c1f`／相同 | `6dccec46421cc5326e214438f23886b05a79e4fa` | `60e09d3b6310361dad0025e88802f3774d0dc4ff8d264bdabe483bfc7635ba2a` | `260807-review-living-after-main-replay-r2.md`，0 major | **可 checkpoint** |
| `docs/agents/service-cutover/plan.md` | ` M` | `67ef6c776f1b4ffc5c68a949c902a25c68716122`／相同 | `b14ead68cf5861b375c92cf86e223f1ff288028d` | `6644126a9aee556ef7fc8a3993d822220f4390227cc8e276984c6d7b4b8a2c8a` | **无 current SHA 命中**；旧联合 R2 为 1 major且绑定旧 bytes | **暂不 checkpoint；需 Service-cutover 联合 R3** |
| `docs/agents/service-cutover/readiness.md` | ` M` | `8cc795eab16f47643113345f76d1567a02ca638b`／相同 | `e83c33b7609f4bb5e694951b8acc24c261d45092` | `a8abccf4ffd3168c5b3eaa5531de24f24f423948d72235a383e7a220e8101270` | `260807-review-living-after-main-replay-r2.md`，0 major／1 minor | **可 checkpoint；保留 identity minor** |
| `docs/agents/systemd-runtime/plan.md` | ` M` | `c7b2e0ef7b8cf2b748b654858a279c36af08ff8c`／相同 | `ae73fdf88e104ff1f256e47fb8a51a02713a9834` | `6646cb727e1bc92ce02ec2bd76f825bb8c9b7d190dbd907ed9f9a6e776f156e6` | `260807-review-systemd-runtime-plan-r5.md` 与 living 联合 R2，均 0 major | **可 checkpoint** |
| `docs/agents/anthropic-responses-bridge/README.md` | ` M` | `a0f693e91f90f8e597f20fa52c988de2e0099a58`／相同 | `65eeb5fffa8a30cd1726f813349ef07babdfb8c0` | `eb52f5a4b09d04a4acaa549c8e5df12a29312427fb70e5c47d7eabf9fa50da67` | **无 current SHA 命中**；旧 living R2 绑定旧 README／Implementation bytes | **暂不 checkpoint；需 README＋Implementation living R3** |

“最新有效”的口径是：报告明确包含目标文件本轮 current SHA-256，并在该 SHA 的命中集合中采用最后形成且 verdict 为 0 major 的报告。仅文件名相关、仅绑定旧 SHA、或范围明确排除目标文件的报告不算 current-byte 证据。

## 事实性发现

[major] `docs/agents/service-cutover/plan.md` current worktree bytes — 当前内容没有任何 0-major 报告绑定其 SHA-256 `6644126a…`，而最新联合 Service-cutover R2 仍是旧 bytes 上的 1 major verdict — 若把 Plan 与已获 living 联合 R2 放行的 Readiness 一并暂存，会把“Readiness current-byte 已复评”错误扩张成“两份 Service-cutover 文档都已复评”，执行者无法确认旧 R2 的状态链 major是否在联合态关闭 — 对 current Plan `6644126a…` 与 current Readiness `a8abccf…` 做 Service-cutover docs R3 联合复评，消费旧 R2 finding并重新走 `NO_CUTOVER`、Implementation identity、systemd main checkpoint、下一 smoke和 43 行矩阵接缝；达到 0 blocker／0 major后再把 Plan 加入 checkpoint。

[major] `docs/agents/anthropic-responses-bridge/README.md` current worktree bytes — README 已从旧复评绑定的 `2de36b12…` 修订为 `eb52f5a4…`，且这次修订重写了 current main、foundations／systemd归档、happy／usage gate和下一步；没有 current SHA 0-major 报告 — 旧 `260807-review-living-bridge-docs-r2.md` 明确绑定旧 README／Implementation bytes，不能沿用；未经复评就加入 checkpoint会让导航层新增事实缺少独立 current-byte 对账 — 做 README＋Implementation living-docs R3 定向联合复评，绑定 README `eb52f5a4…` 与 Implementation `60e09d3b…`，复核导航转述、候选顺序、局部证据边界与完整产品 `UNVERIFIED`；不重做 Spec／Acceptance终审。

[minor] `docs/agents/service-cutover/readiness.md:9` — 当前文件内嵌的 Implementation SHA-256 仍是 `4ace302283e2b4b539c8195e55a2a23020f692d40fe0df868546dd58312036e2`，current Implementation 则是 `60e09d3b6310361dad0025e88802f3774d0dc4ff8d264bdabe483bfc7635ba2a` — 这是 current living 联合 R2 已明确接受的唯一 non-blocking minor，不反转三文件 checkpoint、`UNVERIFIED` 或 `NO_CUTOVER`，但会让按哈希追溯 Implementation 的执行者定位到旧 bytes — 在下一次 Readiness 同步或 Service-cutover R3 中更新并重绑；本轮不自行修改。

除以上证据链与 identity 问题外，**未发现新的内容正确性问题；未发现 blocker。**

## 精确暂存集合安全性

### 当前已有 current-byte 0-major 证据的 checkpoint 集合

1. `docs/agents/anthropic-responses-bridge/implementation.md`
2. `docs/agents/service-cutover/readiness.md`
3. `docs/agents/systemd-runtime/plan.md`

### 两个复评闭合后的完整 living checkpoint 候选集合

1. `docs/agents/anthropic-responses-bridge/README.md`
2. `docs/agents/anthropic-responses-bridge/implementation.md`
3. `docs/agents/service-cutover/plan.md`
4. `docs/agents/service-cutover/readiness.md`
5. `docs/agents/systemd-runtime/plan.md`

两组都必须以逐路径显式 pathspec 暂存，不得使用 `docs/`、`docs/agents/`、`.`、`-A`、`-u` 或 glob。当前 `docs/tmp` verification 候选 10 份，与两个显式集合的交集均为 0；因此**精确路径集合本身不会夹带 verification**。但暂存执行后仍必须在同一 `main` gate 调用中机械检查：cached path集合精确等于所选集合、每个 index blob等于本报告绑定的 worktree blob、`git diff --cached --check`通过、`docs/tmp/**` 命中为 0。路径安全不替代 current-byte 复评证书。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `readiness.md:9` 与 `implementation.md` | 跨 living 文档手工复制全量 SHA，易在并行更新时漂移 | **记后续**：Service-cutover R3 重绑；保留 identity 门，不因维护成本取消 provenance |
| README 与 Implementation 的 current 状态摘要 | 同一事实在导航层和真相源重复，导航层可能落后 | **本轮不改**：要求 living-docs R3 联合复评，并继续声明冲突时以 Implementation 最新修订为准 |
| Service-cutover Plan 与 Readiness | 计划与实时矩阵可各自通过却在联合身份／下一动作上漂移 | **本轮不改**：当前 Plan＋Readiness 做联合 R3，而不是拿 Readiness 的单独 0-major外推到 Plan |

## 主观建议

[建议] living checkpoint 执行入口 — 将“current SHA→报告 verdict→允许暂存”的映射做成只读 manifest 或小型检查脚本 — 预期影响是减少手工反查旧报告造成的误绑定，同时保留 current-byte 证据门 — 推荐 manifest 只记录精确路径、SHA-256、报告路径、verdict和生成时 main HEAD，任何内容漂移自动失效；不自动执行 `git add`。

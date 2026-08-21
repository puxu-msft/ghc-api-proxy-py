# systemd living Plan current-resume 独立评审

- **评审范围**：current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 的 working-tree `docs/agents/systemd-runtime/plan.md`，SHA-256 `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e`；重建审计 `docs/tmp/260807-audit-systemd-next-rebuild.md`；current code-only merged-state review `docs/tmp/260807-review-systemd-code-only.md`；独立验收 `docs/tmp/260807-verify-systemd-code-only.md`。本轮只评审 current Plan bytes 是否正确消费 rebuilt code-only 策略、能否形成自身文档 checkpoint、后续执行顺序是否保持 living 且不收口；未修改 Plan、其他三份 living docs、Git index、HEAD、branch、refs、代码或运行态。唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。Current Plan 可 checkpoint。** 精确 SHA-256 `0f372ab2…` 为 `0 blocker／0 major`；它已把旧 `91f95f7…`／`0a93e7f…` 限定为历史 provenance，并把 current 执行路线更新为 four-docs checkpoint 后按 `862f4cfa…` → `2ec0cb8…` 逐片消费 code-only 语义。每片仍须 main-side gate，第一片 gate 后 fresh 更新并 checkpoint Plan，第二片只能在该 checkpoint 后回放，第二片 gate 后再次 fresh 更新 Plan。两片进入 main 后继续真实 user-manager／cgroup 与 rolling 独立切片；Plan 保持 `LIVING`，不因本 checkpoint 或两片回放而收口。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。Plan 多处把权威重建审计要求的“四份 current living docs 共同 checkpoint”简写为“living 文档 checkpoint”或“文档 checkpoint”，存在执行者误读为只提交本 Plan 即可开始第一片的有限风险；该风险由 Plan 明确要求先消费重建审计、以及本报告下述 checkpoint 裁决补足，不阻断 current Plan 自身 checkpoint。
- **checkpoint 裁决边界**：本 verdict 精确绑定 current Plan SHA `0f372ab2…`，不沿用旧 R8／checkpoint 报告绑定的 SHA `5655958e…`。它只证明本 Plan 是 four-docs checkpoint 的合格组成项，不单独证明其余三份 living docs 的 current bytes 已闭环，也不单独放行代码回放。第一片开始前仍须形成四份 current living docs 的共同 checkpoint，并在执行现场重验 main、四份文档、code-only refs／commits、parents、pathsets、clean index／worktree 与适用性。

## 双视角覆盖证据

### 机械核对视角

- 每个承载结论的 shell 调用均在同一次调用内固定物理 root `/home/xp/src/ghc-api-proxy-py`、`main` 分支、`HEAD == 80bc8f252b46c511f428af1d97159a5980ee9dc9` 与目标 Plan SHA。`sha256sum` 与 Python `hashlib.sha256` 两种实现均得到 `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e`。
- 完整通读 current Plan 与三份指定对照材料，并扫描 `5655958…`、`91f95f7…`、`0a93e7f…`、`862f4cfa…`、`2ec0cb8…`、`integrate/260807-systemd-code-only`、`checkpoint`、`living` 及待 review／verify／rebuild 的残留措辞。未发现 current Plan 把旧 integration 写回 current 执行路线，也未发现把 Plan 标为完成或收口。
- 独立核验提交图为 `80bc8f2… → 862f4cfa… → 2ec0cb8…`，两提交均为 non-merge；`862f4cfa…` 的 parent 为 `80bc8f2…`，`2ec0cb8…` 的 parent 为 `862f4cfa…`。本地 ref `refs/heads/integrate/260807-systemd-code-only` 精确指向 `2ec0cb8…`，对应 worktree 也固定在该 tip；old ref `refs/heads/integrate/260807-systemd-next` 精确指向 `0a93e7f…`。
- 独立列出两片路径集合：第一片只包含 Plan 所列 graceful timeout 的代码、部署文档与测试路径；第二片只包含 installer、部署文档与 installer smoke。两片均不含 `docs/agents/systemd-runtime/plan.md`。Base、第一片与第二片的 Plan Git blob 均为 `ae73fdf88e104ff1f256e47fb8a51a02713a9834`。
- `git diff --quiet 0a93e7f… 2ec0cb8… -- . ':(exclude)docs/agents/systemd-runtime/plan.md'` 返回 0，独立确认 current code-only tip 与旧 reviewed integration 的所有非 Plan bytes 相同。该结论与指定 merged-state review 的 blob-map 交叉证据一致。
- Current Plan 对 exact code-only tip 的证据边界与指定 review／verify 一致：merged-state code review 为 `0 blocker／0 major／2 non-blocking minor`，独立 verify 为 `PASS`，全仓 pytest 执行与 collect-only 均为绑定 `2ec0cb8…` 的 440 项；这些证据不外推为真实 manager activation、effective cgroup、安装、部署、cutover 或 rolling。
- `git diff --check -- docs/agents/systemd-runtime/plan.md` 通过。旧 R8 与 checkpoint 报告精确绑定 `5655958e…`，current SHA 已变化，因此本轮没有复用旧 current-byte verdict。

### 第一人称执行视角

- 作为 four-docs checkpoint 执行者，我先把本报告视为 current Plan 自身的 exact-hash `0 major` 证书；我仍需对 Acceptance、Implementation、Readiness 各自取得 current-hash 独立 `0 major` 证书，并把四份文档形成共同 checkpoint。只提交本 Plan 后立即回放第一片不满足重建审计的唯一安全策略。
- 作为第一片回放执行者，我从 four-docs checkpoint 后的 actual current main 开始，重新验证 `862f4cfa…` 的 parent／preimage、精确 pathset 不含 Plan、工作树没有重叠修改，再消费第一片。Main-side gate 失败即停；通过后只从 checkpoint Plan bytes fresh 写入 actual main commit 与 gate 结果并再次 checkpoint Plan，不从 `91f95f7…` 的 Plan postimage解冲突。
- 作为第二片回放执行者，我只在第一片 main-side gate 与 fresh Plan checkpoint 都成立后消费 `2ec0cb8…` 的 installer 语义，保持 S3-parent timeout adaptation。第二片 gate 失败即停；通过后再次 fresh 更新 Plan，不采用 `0a93e7f…` 的旧 Plan postimage。
- 作为后续实施者，我在两片进入 main 后进入 S5，使用备用动态端口、隔离状态根与可回收 user-manager fixture 验证真实 activation、restart、graceful／force timeout、cgroup 归属及 cleanup，并对账 declared／effective／runtime 三层事实。S7 rolling 仍需先冻结拓扑、readiness 切流、状态隔离、drain 与回滚，不能由单实例 socket activation 自然推出。
- 作为部署或运维执行者，我不会把文档 checkpoint、code-only review、仓库 gate 或 rootless probe解释为 unit 已安装、manager 已变更、服务已替换、端口已 cutover 或发布已授权。

## 事实性发现

[minor] `docs/agents/systemd-runtime/plan.md:25`、`:96-99`、`:195`、`:300-302`、`:331-335`、`:426` — 开始 code-only 回放的前置门多次写成“living 文档 checkpoint”或“文档 checkpoint”，没有在本文件内明确说这是四份 current living docs 的共同 checkpoint — 权威重建审计 `docs/tmp/260807-audit-systemd-next-rebuild.md:4-8` 明确唯一 0-major 策略从 four-docs checkpoint 开始，且 `:21`、`:26` 要求四份文档分别完成 current hash→独立 0-major report→共同 checkpoint；若执行者只读 Plan 的状态看板或 kick-off，可能把“本 Plan 可 checkpoint”误读成“第一片已获单文档放行” — 本轮报告明确裁决 current Plan 可作为共同 checkpoint 的合格组成项，但不能单独放行回放；下次 fresh Plan update 应把关键入口统一写成“四份 current living docs 的共同 checkpoint”，并列出四路径或引用固定 gate，避免继续依赖外部审计补语义。该措辞缺口不构成 major，因为 Plan `:6`、`:424` 明确要求消费重建审计，current code-only 路线、执行顺序与 stop conditions 本身均正确。

除上述 non-blocking minor 外，未发现事实性问题。特别是未发现旧 `91f95f7…`／`0a93e7f…` 被允许回放、old Plan postimage 被允许用于冲突解决、code-only 两片调序或合并、后补 installer atomicity／配置测试判别力被错误升级为回放门、S5／S7 被误写为已完成、部署边界被外推或 Plan 被标为收口。

## 主观建议

[建议] `docs/agents/systemd-runtime/plan.md` 的 checkpoint 入口 — 当前路线在页首、状态看板、M1 下一动作、S6、disposition 与 kick-off 多次复述，信息完整但容易随 living 更新漂移 — 预期影响是后续每片 fresh update 的维护成本较高，某一处可能再次遗留旧 identity 或弱化共同 gate — 保留页首摘要、状态看板和 kick-off 三个执行入口，其余章节引用状态看板；不要在 S3／S4 回放前做结构重写，以免扩大 checkpoint diff。

## Current Plan checkpoint 裁决

1. **Current bytes 身份**：`docs/agents/systemd-runtime/plan.md` SHA-256 `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e`。
2. **内容 verdict**：`0 blocker／0 major／1 non-blocking minor`，**明确可形成自身文档 checkpoint**。
3. **Plan 状态**：保持 `LIVING`，继续且不收口。
4. **共同门**：该 checkpoint 必须与另三份 current living docs 一起形成 four-docs checkpoint 后，才进入代码回放；任一文档 bytes 或 verdict漂移都重新绑定。
5. **current 代码路线**：只消费 `862f4cfa55b124ef9ad21ff2ded2b944ee3307bc` → `2ec0cb81832691685bfe8d98ad03071d2d5e5316` 的 code-only 语义；旧 `91f95f7…`／`0a93e7f…` 仅作历史 provenance，禁止回放，禁止采用其 Plan postimage。
6. **逐片门**：第一片 main-side gate → fresh Plan update／checkpoint → 第二片 main-side gate → fresh Plan update／checkpoint；任一 gate 失败即停。
7. **后续 living 范围**：继续 S5 真实 user-manager／cgroup，随后另行设计和验收 S7 rolling；本 checkpoint、两片回放及后续仓库 gate均不表示部署或 cutover。

## 结构怪味与方案反思

- `docs/agents/systemd-runtime/plan.md:1-8`、`:88-102`、`:191-197`、`:282-302`、`:320-339`、`:420-432`｜同一 current execution state 在多个章节复述，存在更新漂移风险｜本轮不改；Plan 第 9 节已识别 living state 与 code patch 耦合，code-only 重建已先解决最危险的提交耦合。下次 fresh update 可在不删减 living 信息的前提下收敛重复入口。
- **更好的内部替代方案**：直接回放 old commits 会重新引入过时 Plan patch；current code-only 两片已复用全部 reviewed 非 Plan bytes并保持独立回滚，是当前更好的内部路线。
- **判据判别力**：只检查 Plan 写有新 commit IDs 会漏掉 old Plan patch混入；本轮同时核对两片 pathset、三个 Plan blobs与 old／new 非 Plan bytes等价性。只看 code-only review 又会漏掉 four-docs 前置门；本轮以第一人称从 checkpoint 到两片再到 S5／S7完整模拟执行。
- **成熟方案**：Git 原生 commit graph、pathset、blob identity 与 diff已足以验证 code-only 重建，不需要自造迁移机制；systemd 运行态继续交给 S5 的真实 user-manager／cgroup probe，而不是由 Plan 文本或静态 parser冒充。

## 最终结论

**Current Plan SHA `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e` 为 0 blocker／0 major，明确可 checkpoint；Plan 保持 `LIVING` 且不收口。** 本结论不复用旧 `5655958…` 的 R8 证书。执行路线已正确切换为 four-docs checkpoint 后按 `862f4cfa…` → `2ec0cb8…` 逐片消费 code-only 语义，每片 gate 后 fresh 更新并 checkpoint Plan；旧 `91f95f7…`／`0a93e7f…` 只保留 provenance，绝不可直接回放或恢复其 Plan postimage。两片完成后继续真实 user-manager／cgroup 与 rolling，任何仓库 checkpoint 都不表示安装、部署或 cutover。

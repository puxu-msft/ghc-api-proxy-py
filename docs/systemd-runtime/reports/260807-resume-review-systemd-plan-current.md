# systemd living Plan current 定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 working-tree `docs/agents/systemd-runtime/plan.md`，预期并实测 SHA-256 均为 `1b936c11eeab3489459e46048dddd2382da5cd49c881b13c3d1a9a92b2bb3344`；主树身份为 `main@b91e58a29324b11840002efc53ed6f869b800c39`。定向核对 new-main rebuild `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` → `d3fabfadfba57af6c2d63e543e3198444777df54`、旧 `862f4cfa…`／`2ec0cb8…` 的历史边界、Plan `LIVING` 状态、每片 main-side gate 后 fresh Plan update／checkpoint、S5 真实 manager／cgroup、S7 rolling 以及 `NO CUTOVER`。本轮未修改 Plan、代码、Git index、HEAD、branch、refs、运行态或其他文档；唯一仓库写入为本报告。
- **总体 verdict**：**修复 major 后可进入下一阶段；当前不可 checkpoint。** Plan 的长期边界正确，但 current 执行状态滞后：仓库中已经存在基于 exact `b91e58a…` 的 new-main rebuild `8cae6c2…` → `d3fabfa…`，Plan 却在所有主要执行入口持续写成“两片尚未产生、下一步重新构造 S3 再构造 S4”。执行者照 Plan 会重复重建，并无法对现有两片建立正确的 main-side gate 与 fresh checkpoint 账本。
- **blocker 数**：0。
- **major 数**：1。

## 双视角覆盖证据

### 机械核对

- 用 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉确认 Plan SHA-256 为 `1b936c11eeab3489459e46048dddd2382da5cd49c881b13c3d1a9a92b2bb3344`，与派活预期一致。
- 用 Git commit 对象核对新链：`8cae6c260c8bc2930be96eaecc7d6d24d470e00a` 的唯一 parent 是 `b91e58a29324b11840002efc53ed6f869b800c39`，主题为 `feat: configure graceful shutdown timeout`；`d3fabfadfba57af6c2d63e543e3198444777df54` 的唯一 parent 是 `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`，主题为 `feat: add rootless systemd user installer`。两片位于 `integrate/260807-systemd-rebuild-resume`，均尚不是 `main` 的祖先，因此准确状态应是“new-main rebuild 已构造，但尚未进入 main／尚待适用 gate”，而不是“commit 尚未产生”。
- 新链两提交中的 Plan blob 与 `b91e58a…` 的 Plan blob相同，current working-tree Plan 又是其后的独立 WIP；仓库文档扫描未找到 `8cae6c2` 或 `d3fabfa`，也未找到绑定这两片的 main-side gate／fresh Plan checkpoint 记录。不能把“commit 已存在”外推成 gate 或 checkpoint 已完成。
- Plan `docs/agents/systemd-runtime/plan.md:3-10,15,90-104,194-204,234-257,285-305,334-340,423-437` 反复保持旧恢复态。最直接的冲突包括：`:98-101` 写 S3／S4 new-main identities 尚未形成；`:198,204,236` 写提交尚未产生并要求重新重建；`:287,303-305` 写 new-main identities 未形成并给出未来构造流程；`:334-338` 仍把当前动作写为从 `b91e58a…` 重建；`:425-433` 的 kick-off 再次命令先重建尚不存在的 S3，然后才构造 S4。
- 旧 `862f4cfa…`／`2ec0cb8…` 在 Plan 中始终被限定为 old-base 语义 oracle／历史 provenance，未发现把旧 identity 重新写成 current payload 的回归。
- `docs/agents/systemd-runtime/plan.md:1,3,15,26,90-104,194-200,309,425-437` 一致保持 Plan 为 `LIVING` 且不收口；S5 在 `:255-281` 仍要求备用端口、隔离状态根、真实 user manager、真实 cgroup 归属与 declared／effective／runtime 三层对账；S7 在 `:307-321` 仍是后续独立 rolling 设计；`:9-10,49,97,131-135,200,297-301,431-437` 明确禁止安装、生产端口接管、manager 持久变更与 cutover。这些定向要求均通过。

### 第一人称执行

- 作为恢复执行者，我从 kick-off 开始会被要求在 `main@b91e58a…` “重建尚未产生的 S3”。但仓库已存在 parent 正好是该 main 的 `8cae6c2…`；继续照做会制造第二个 S3 identity，而不是验证和推进现有 new-main rebuild。
- 即使我发现 `8cae6c2…`，状态看板仍声称 S4 必须等待未来 S3 gate＋fresh Plan checkpoint 才能产生；然而 `d3fabfa…` 已经是其直接后继。Plan 没有告诉执行者这是已构造但尚未完成 main-side gate／fresh checkpoint 的链，也没有记录中间 fresh Plan checkpoint 是否缺失，因此无法诚实决定下一步是 gate、重建、回退还是重新形成 checkpoint。
- 正确执行语义应改为：承认 `8cae6c2…` → `d3fabfa…` 是当前 new-main rebuild identity；明确两者仍在 integration branch、尚未进入 main；逐片重新取得适用于 current main 的 gate，且每片 main-side gate 后立即从 current bytes fresh 更新并 checkpoint Plan。对没有证据的 S3／S4 gate 或 fresh checkpoint必须写“未完成／待验证”，不得因提交存在而补写成已通过。
- 两片及其 fresh Plan checkpoint完成后，执行路径仍进入 S5 的备用端口真实 manager／cgroup smoke，再进入独立 S7 rolling；任何仓库 gate 都不授权安装、停止旧 Bun、接管 4141、改变 manager 持久状态或 cutover。Plan 当前对这些后续边界的指导可直接保留。

## 事实性发现

[major] `docs/agents/systemd-runtime/plan.md:3-8,15,32,45-48,98-101,123,198,204,236,257,287,303-305,334-338,384,411,425-433` — Plan 未消费已经存在的 new-main rebuild `8cae6c2…` → `d3fabfa…`，仍把 S3／S4 identities 写成尚未产生并命令重新构造 — Git 对象证明 `8cae6c2…` 直接基于 exact `main@b91e58a…`，`d3fabfa…` 又直接基于 `8cae6c2…`；两片当前只在 `integrate/260807-systemd-rebuild-resume`，尚未进入 main。Plan 与两提交中的 Plan blob均未记录这条链，仓库文档也没有绑定该链的 main-side gate／fresh Plan checkpoint 证据。照 current Plan 执行会重复创建 S3／S4 identity，并可能把现有链绕过逐片 gate或误记为未做 — 全文统一切换到 actual new-main chain `8cae6c260c8bc2930be96eaecc7d6d24d470e00a` → `d3fabfadfba57af6c2d63e543e3198444777df54`；将旧 `862f4cfa…`／`2ec0cb8…` 保持为历史 oracle；明确新链“已构造、未进入 main、main-side gate与 fresh Plan checkpoints 未由现有证据证明”；把下一动作改为逐片适用性／main-side gate与每片后的 fresh Plan update／checkpoint，而不是再次重建。修订须同步页首、事实区、看板、shell gate、M1 下一动作、S3、S4、S5 前置、S6、disposition、未采纳方案、结构怪味和 kick-off，避免只修一个入口后其余入口继续误导。

除上述 major 外，未发现其他 blocker 或 major。特别是未发现旧 `862f4cfa…`／`2ec0cb8…` 被当作 current payload、Plan 被收口、S5 真实 manager／cgroup 被删减、S7 rolling 被冒充已支持，或仓库状态被外推为安装／部署／cutover。

## checkpoint 裁决

当前为 **`0 blocker／1 major`，不可 checkpoint**。先把 Plan 准确切换到 `8cae6c2…` → `d3fabfa…`，并诚实标注现有证据未证明两片 main-side gate／fresh Plan checkpoint；保持 `LIVING`、S5、S7 与 `NO CUTOVER` 边界。新稳定 bytes需重新绑定 SHA并定向复评；达到 `0 blocker／0 major` 后方可 checkpoint。

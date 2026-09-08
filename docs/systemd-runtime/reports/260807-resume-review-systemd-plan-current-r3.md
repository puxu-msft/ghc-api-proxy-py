# systemd living Plan current R3 定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 working-tree `docs/agents/systemd-runtime/plan.md`，SHA-256 `3c639fcd73ad1deed9a164ece43eb0f982da7f2ae8259e5903e7a7d9c9a7054f`；主树固定为 `main@b91e58a29324b11840002efc53ed6f869b800c39`。本轮只复核 R2 唯一 major：current new-main merged-state review `docs/tmp/260807-resume-review-systemd-rebuild.md` 的 `0 blocker／0 major` 与 `docs/tmp/260807-verify-systemd-rebuild-resume.md`、`docs/tmp/260807-resume-verify-systemd-rebuild.md` 两份 exact-tip verify `PASS`，是否已在页首、评审输入、S6 与 kick-off 准确消费；并定向复核逐片 squash／main-side gate／fresh Plan update、旧链历史边界、`LIVING`、S5、S7、三个 non-blocking minor 与 `NO_CUTOVER`。未重审候选代码，未重复运行候选测试，未执行 squash、安装、manager 操作、服务／端口变更或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。当前 Plan 为 0 blocker／0 major，可 checkpoint。** R2 唯一 major 已关闭：current merged-state code review 与两份 verify 已作为三个角色不同、互不替代的 current 证据进入全部四个执行入口；逐片 main 收敛顺序与片间／片后 fresh Plan checkpoint 也没有执行歧义。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0 个新增 minor。既有三个 non-blocking minor 继续登记并明确不阻断当前 checkpoint 或 main 收敛。
- **报告自身评审状态**：本会话处于叶子 reviewer 模式，不能派生独立 reviewer；主会话仍须安排对本报告文本的独立复核。该待复核状态不改变本轮底层 Git／文档证据或 Plan checkpoint verdict，也不能被表述为报告自身已经二次评审。

## 双视角覆盖证据

### 机械核对视角

- 每个承载结论的 shell gate 都在同一次调用内验证物理 root、Git top-level、`main` 分支、exact `HEAD=b91e58a29324b11840002efc53ed6f869b800c39` 与 Plan SHA-256。`sha256sum` 和 Python `hashlib.sha256` 两种实现均得到 `3c639fcd73ad1deed9a164ece43eb0f982da7f2ae8259e5903e7a7d9c9a7054f`。
- Git commit object 证明 current candidate 精确为线性链 `b91e58a29324b11840002efc53ed6f869b800c39 → 8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`。S3 为 9 个非 Plan paths，S4 为 3 个非 Plan paths；base、第一片与 tip 的 Plan blob 均为 `a390efd0d2cd5393fa6d935f5c8c078a2d245253`。
- `docs/agents/systemd-runtime/plan.md:3` 的页首同时记录 current merged-state review 的 exact base／tip、`0 blocker／0 major` 与逐片授权，并并列记录两份 verify `PASS`、474 项执行／collect-only、Ruff、Pyright、deadline 正控和 installer 零 manager 操作；同句明确这些证据不覆盖真实 user manager／cgroup、安装、部署或 cutover。
- `docs/agents/systemd-runtime/plan.md:6` 的评审输入精确引用并消费 `260807-resume-review-systemd-rebuild.md`、两份 verify，明确三份 current 证据角色不互相替代，也不冒充本轮新 Plan bytes 已经复评。
- `docs/agents/systemd-runtime/plan.md:287,303-305` 的 S6 状态、评审与回并边界再次准确记录 review `0 blocker／0 major`、两份 verify `PASS`、current exact chain、两片排除 Plan、逐片授权和失败即停条件。
- `docs/agents/systemd-runtime/plan.md:427-431` 的 kick-off 要求执行者并列消费 current review 与两份 verify，明确旧链证据角色不同；下一动作固定为 S3 单片 squash → identity／preimage／main-side tests gate → actual main SHA 的 fresh Plan checkpoint → S4 单片 squash → 同类 gate → 第二次 fresh Plan checkpoint，且禁止合并两片或跳过片间 checkpoint。
- 三个证据文件的 Markdown 相对链接均从 Plan 位置解析到存在的文件。Current review 文件名与两份 verify 文件名在 Plan 中各至少出现四次，覆盖页首、评审输入、S6 和 kick-off，而不是只在单一附注中出现。
- 旧 `91f95f7… → 0a93e7f…` systemd-next 链与 `862f4cfa… → 2ec0cb8…` code-only 链的 commit objects 均存在，但 Plan 在 `docs/agents/systemd-runtime/plan.md:338-340,384` 只把它们保留为历史 provenance／oracle，禁止 direct replay、cherry-pick 与采用 old Plan postimage；current payload 始终是 `8cae6c2… → d3fabfa…`。
- `docs/agents/systemd-runtime/plan.md:1,3,15,26,431,435` 保持 `LIVING`、继续且不收口。S5 在 `:255-281,435` 继续要求备用端口、隔离状态根、可回收 user-manager fixture、真实 activation／lifecycle／cgroup 三层事实；S7 在 `:307-321,435-437` 继续作为独立 rolling 切片，未被冒充成 S3／S4 的自然结果。
- 三个既有 non-blocking minor 均保留：配置 precedence 永久测试判别力在 `docs/agents/systemd-runtime/plan.md:225,407`，installer 逐文件 atomicity／失败恢复合同在 `:253,408`，timeout facts 重复 owner 在 `:406`。它们没有被删除，也没有被错误升级为当前收敛门。
- `docs/agents/systemd-runtime/plan.md:3,9-10,200,303,431-439` 明确禁止把 review／PASS／main checkpoint 外推为真实 manager／cgroup、安装、部署、停止旧 Bun、接管 4141 或 cutover；最终生产动作仍要求用户另行明确发起。`git diff --check -- docs/agents/systemd-runtime/plan.md` 通过。
- 初版反向语义探针曾因要求无空格精确子串 `Plan继续living`，对正文实际的 `Plan 继续 living` 产生 false-red。该运行没有被当作 Plan 缺陷；修正为对空白不敏感且要求同时存在 `` `LIVING` `` 与“不收口”的结构判据后，全部定向检查和链接检查通过。修正后的 gate 使用 `&&` 短路，任何失败都会真正阻断后续步骤。

### 第一人称执行视角

- 作为 main 收敛执行者，从页首进入时，我会先识别 current exact candidate、merged-state review `0 blocker／0 major` 与两份 verify `PASS`，不会把 verify 误当 code review，也不会因缺失 review 记录而重复发起已经闭合的 candidate review。
- 按评审输入与 S6 执行时，我只能使用 `8cae6c2… → d3fabfa…` 作为 current payload。旧 systemd-next 与 old-base code-only 链只提供历史语义／provenance，不能替代 current identity、不能携带旧 Plan patch，也不能成为 direct replay 载荷。
- 第一片执行流程没有跳步：先重取 actual main、candidate parent／tip、pathset、Plan 排除、preimage 与 result bytes；再单独 squash S3；main-side tests gate 通过后立即把 actual 完整 main SHA、结果和 S4 前置条件 fresh 写回 Plan并形成 checkpoint。任一 identity、preimage、Plan bytes、pathset 或 tests gate 漂移即停。
- 第二片只能从 S3 gate 与片间 Plan checkpoint 后的 actual main继续；单独 squash S4、通过同类 main-side gate 后再次 fresh 更新 Plan。Plan 明确禁止把两片压成一个提交或跳过片间 checkpoint，因此“逐片可独立归因／回滚”与“living truth source 及时更新”可以同时成立。
- 两片进入 main并完成最终 fresh Plan checkpoint 后，我仍必须进入 S5 的备用端口真实 user-manager／cgroup smoke；静态 parser、direct inherited-fd smoke、474 项测试或 repository checkpoint 都不能替代该阶段。S7 仍需独立冻结拓扑、readiness 切流、状态隔离、drain 与回滚。
- 在任何阶段，我都不会把本 checkpoint 解读为 unit 已安装、旧 Bun 可停止、4141 可释放／占用、manager 状态可修改、服务已部署、rolling 已实现或 cutover 已获授权。

## 事实性发现

未发现问题。R2 的唯一 major 已由 current Plan 在页首、评审输入、S6 与 kick-off 四处完整关闭；未发现只补文件名却遗漏 verdict／授权、只补机械摘要却保留错误执行顺序、或修复 review 消费时削弱其他既有边界的情况。

## 主观建议

未提出额外主观建议。本轮是定向复评，不应借机重开候选代码、重复已经闭合的 review／verify，或把三个 non-blocking minor升级为当前 checkpoint 门。

## checkpoint 裁决

Current Plan SHA-256 `3c639fcd73ad1deed9a164ece43eb0f982da7f2ae8259e5903e7a7d9c9a7054f` 为 **0 blocker／0 major，可 checkpoint**。该 checkpoint只冻结 current living Plan 的准确执行状态；它不表示 S3／S4 已进入 main、unit 已安装、真实 manager／cgroup 已验收、服务已部署、rolling 已完成或 cutover／发布获授权。

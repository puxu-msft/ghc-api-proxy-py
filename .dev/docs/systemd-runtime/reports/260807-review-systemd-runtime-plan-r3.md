# systemd runtime living plan 定向复评 R3

- **评审范围**：current `docs/agents/systemd-runtime/plan.md` 全文，精确 SHA-256 为 `c1c5fd8a84c71363a4d57f374a0696b3dc5b1074498982a0dc15bd840e42009a`；定向消费上一轮 `docs/tmp/260807-review-systemd-runtime-plan-r2.md` 的唯一 major，并对账已落盘的 `docs/tmp/260807-review-code-systemd-runtime-r2.md`、候选 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 及当前 code R3 落盘状态。只检查 Plan 是否同步 latest candidate／permissions、code R3 待／已结论、living／non-TDD 节奏、M1 骨架 smoke 达到 0 major 即 squash 的门，以及回并后强化范围；未修改 Plan 或候选，未安装、启用、启动、停止、restart 或 reload 任何 unit。
- **总体 verdict**：**修复 major 后可进入**。Plan 的技术边界、living／non-TDD 节奏、M1 早期回并门和后续强化拆分均正确；唯一问题是 current bytes 仍停在 `candidate@1a220e04…` 与“code R2 尚未落盘／待 R2”，没有消费上一轮 Plan R2 已点名的 code R2 权限 major，也没有同步已修权限的 `candidate@49fb198…`。当前没有 `docs/tmp/260807-review-code-systemd-runtime-r3.md`，因此 Plan 应准确写成“code R2 为 0 blocker／1 major；权限 major 及其非阻断覆盖项已在 `49fb198…` 实现；code R3 并行待结论；R3 达到 0 blocker／0 major 后即可继续并立即 squash／准备回并”。不得提前写 R3 已关闭，也不得继续要求重复执行 R2。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：逐行扫描 Plan 的头部状态、完成定义、候选事实、Living 看板、S1／S2／M1、评审 disposition、验证命令与 kick-off；共定位到候选 SHA、提交数、R2 落盘状态、待办和 squash 提交集合等一组贯穿全文的同源状态残留。直接核对候选提交链为 `66551e45…` → `1a220e04…` → `49fb198…`；读取 `49fb198…` 的 service、部署 README 与 smoke，确认 `StateDirectoryMode=0700`、`UMask=0077`、真实 History／SQLite WAL／SHM／tokenization writer 权限回归，以及 readiness 200、tokenization 落盘和 EnvironmentFile 等价覆盖路径均已进入候选。定向 `tests/unit/test_cli.py tests/smoke/test_systemd_units.py` 在固定候选、候选 import oracle 与隔离进程组下以退出码 0 完成。主树现场没有 code R3 报告，故本轮不推测其 verdict。
- **双视角覆盖证据——第一人称执行**：按 Plan 从看板进入 S1，模拟“读取 current candidate → 消费已到达评审 → 选择下一动作 → 判断是否 squash”。执行者会被当前文本引向 `1a220e04…` 并重复请求 code R2，而不是识别 `49fb198…` 已按 R2 修权限、只需等待并消费 code R3；M1 动作还会错误地只 squash 两个提交，漏掉权限修复提交。另模拟 code R3 两种分支：若为 0 blocker／0 major，应立即 squash 三提交并准备回并；若仍有 major，应继续修复并复评。Plan 的 S3～S7 后续强化在两条分支中均保持，不应反向扩大 M1。

## 事实性发现

[major] `docs/agents/systemd-runtime/plan.md:5-6,17,28-38,85-87,143-183,310-315,349,393-395` — living plan 未消费上一轮 Plan R2 的唯一 major，候选身份、权限状态、评审阶段和 squash 集合整体滞后一轮 — Plan 仍把 current candidate 写成 `1a220e04…`、提交链写成两提交，并多处声明 code R2“尚未落盘／待 R2”；实际 code R2 已落盘且 verdict 为 `0 blocker／1 major`，其权限 major 要求 `StateDirectoryMode=0700`、`UMask=0077`、收紧覆盖目录文档和真实 writer 权限回归。候选 `49fb198…` 已精确实现这些要求，并同时覆盖 R2 非阻断的 readiness 200、tokenization 实际落盘与 EnvironmentFile 等价覆盖路径；但 code R3 当前尚未落盘，不能把“修复已实现”升级为“major 已独立关闭”。若执行者照 current Plan 行动，会重复派 R2、忽略权限提交，并在 M1 squash 动作中漏掉 `49fb198…` — 按下节逐项同步状态；保持最终 gate 为 current code R3 `0 blocker／0 major`。R3 未到前写“并行待结论，不可 squash”；R3 若为 0 major，立即改为“可继续实施，可立即 squash／准备回并”；若 R3 仍有 major，则记录 finding 并继续候选修复，不改动后续强化范围。

## 精确修订清单

1. **头部候选与评审输入，`plan.md:5-6`**：
   - 候选实现改为 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`。
   - 提交链改为规划基线 → `66551e45…`（骨架）→ `1a220e04…`（R1／可行性 findings 修复）→ `49fb198…`（code R2 权限 major 与非阻断 smoke 覆盖修复）。
   - 评审输入补入 `docs/tmp/260807-review-code-systemd-runtime-r2.md` 与 `docs/tmp/260807-review-systemd-runtime-plan-r2.md`；写明 code R2 绑定 `1a220e04…`、verdict 为 `0 blocker／1 major`，Plan R2 要求消费该结论。
   - current 状态写为：`49fb198…` 已实现权限修复，code R3 并行待结论；当前未发现 R3 报告，首次回并门仍开放但不可提前宣称通过。

2. **M1 完成定义，`plan.md:16-20`**：
   - 在 findings 中补入 `StateDirectoryMode=0700`、`UMask=0077`、覆盖目录最小权限文档和真实 writer mode 回归。
   - 把“findings 是否正式关闭由 current code R2 独立裁决”改为“R1／可行性 findings 已由 code R2 关闭；code R2 新权限 major 已在 `49fb198…` 实现，是否正式关闭由 current code R3 裁决”。
   - smoke 证据同步为 readiness 200、真实 Anthropic 请求、History 与 tokenization 落盘、EnvironmentFile 等价覆盖目录，以及目录／数据库／WAL／SHM／临时与最终状态文件无 group／other 权限。
   - 保持原门不变：current HEAD 独立代码复评达到 0 blocker／0 major 即准备 squash／回并，不等待 S3～S7。

3. **候选事实，`plan.md:28-38`**：
   - 锚点从 `1a220e04…` 更新为 `49fb198…`，提交数量从两个更新为三个。
   - 新增 code R2 disposition：旧启动 major、fd 下界、`Type=`、`KillMode=` 与主要真实 fd smoke 已关闭；新发现权限 major及一项非阻断覆盖缺口。
   - 新增 `49fb198…` 实际内容：`StateDirectoryMode=0700`、`UMask=0077`、覆盖目录 `0700`／文件 `0600` 合同、真实 writer 权限测试，以及 readiness 200、tokenization 落盘、环境覆盖写入 smoke。
   - 删除“独立代码 R2 verdict 尚未在主树落盘”；替换为“code R2 已消费，code R3 尚未落盘，因此权限修复已实现但尚未独立关闭，M1 仍不得宣称 0 major”。

4. **Living 状态看板，`plan.md:85-87`**：
   - S1 改为“R1／可行性 findings 已由 code R2 关闭；R2 权限 major 已在 `49fb198…` 实现，待 code R3 关闭”，证据列出 `0700／0077` 和真实 writer mode 回归，下一动作仅为消费 current HEAD code R3。
   - S2 改为“已扩展并待 code R3 复核”，证据增加 readiness 200、真实 request、History＋tokenization、覆盖路径和权限 smoke；不要再写“待 R2”。
   - M1 改为“权限修复已实现，仅待 current code R3 的 0 blocker／0 major verdict”；下一动作保持“达到即 squash／准备回并，不等待 S3～S7”。

5. **S1／S2／M1 正文，`plan.md:143-183`**：
   - S1 状态改为 `49fb198…` 已实现 code R2 修复，R3 并行待结论；新增权限修复与扩展 smoke 的已完成清单。
   - 将“R2 验收”改为“R3 验收”，范围精确为关闭 code R2 的权限 major并复核新增 smoke；不得重开已经由 code R2 关闭的旧 findings。
   - 回滚说明保留 `1a220e04…` 的 hardening 边界，并补充 `49fb198…` 是独立权限修复提交；不得回退到 world-readable 状态合同。
   - S2 状态和 M1 门均改为 current `49fb198…`／code R3，不再写“待 R2”。
   - M1 动作把“候选两提交”改为“候选三提交”，最终 reviewed report 路径和 verdict 应绑定 code R3；R3 为 0 major 后 squash `66551e45…`＋`1a220e04…`＋`49fb198…`。

6. **评审 disposition，`plan.md:310-315`**：
   - `Type=exec`、`KillMode=control-group`、StateDirectory／显式路径和 `--fd 0` 改为“已由 code R2 关闭”，不再写“待 current R2”。
   - 新增“状态最小权限”一行：code R2 major；`49fb198…` 已实现 `StateDirectoryMode=0700`、`UMask=0077`、覆盖目录文档与真实 writer mode 回归；待 code R3 正式关闭。
   - M1 smoke 改为扩展 smoke 已实现、待 code R3 复核；M1 squash 门绑定 `49fb198…` 与 code R3 `0 blocker／0 major`。

7. **未采纳项与 kick-off，`plan.md:349,393-395`**：
   - “current R2 只复核正确性”改为历史结论：“code R2 已关闭 `Type=`／`KillMode=` 等旧方向，current R3 只复核权限修复及其新增测试，不重开已决方向”。
   - kick-off 的 current candidate 改为 `49fb198…`；删除“先做独立代码 R2”，替换为“消费 code R2 与 Plan R2，核对 `49fb198…` 权限修复，等待／消费并行 code R3”。
   - 分支写明：R3 达到 0 blocker／0 major 时，明确标记“可继续实施，可立即 squash／准备回并”，squash 三提交；R3 有 major 时继续修复并复评。两种分支都不等待 graceful timeout、完整 continuity、install helper、cgroup observability 或 rolling。

8. **R3 到达时的最后同步门**：修改 Plan 前先再次检查 `docs/tmp/260807-review-code-systemd-runtime-r3.md`。若届时已落盘，必须消费其实际 candidate SHA、verdict 和 findings，不能机械保留本报告现场的“待结论”；只有该报告明确为 0 blocker／0 major，Plan 才可把 M1 状态改为“可继续／可立即 squash”。

## 上一轮 R2 major 关闭矩阵

| R2 major | 本轮结论 | current 证据 |
|---|---|---|
| Plan 未消费 code R2，漏记权限 major并错误要求重复 R2 | **实现侧已推进，但 Plan 侧未关闭，故以本轮唯一 major 续开** | `49fb198…` 已含 `StateDirectoryMode=0700`、`UMask=0077`、覆盖目录最小权限文档和真实 writer mode 回归；Plan 仍全篇绑定 `1a220e04…`／待 R2。code R3 尚未落盘，因此正确状态是“修复已实现、R3 待结论”。 |

## 已核对且通过的轴

- **Living／non-TDD**：`plan.md:3,12,98-125` 保持计划与开发同步、已决切片直接推进，不把传统 test-first／强制 TDD 当流程门；同时要求补强切片有可判别回归。无需改方向。
- **骨架 smoke 0 major 即 squash**：`plan.md:12-22,164-188` 已明确 current candidate 独立评审达到 0 blocker／0 major 后立即准备 squash／回并，不等待强化。只需把 gate 身份从 R2／`1a220e04…` 更新为 R3／`49fb198…`，并把 squash 集合改为三提交。
- **强化后续**：S3 graceful timeout、S4 默认 dry-run 的 rootless install helper、S5 declared／effective／runtime cgroup observability、S6 组合复核与 S7 rolling 均完整保留且明确后置；本轮不以状态修订为由删减或提前阻塞这些范围。
- **保证边界**：listener continuity、queued／unaccepted continuity、accepted connection drain 与双实例／rolling 的区分仍准确；权限修复不改变这些架构结论。
- **R2 非阻断覆盖项**：`49fb198…` 已实现在受控 generic upstream 下的 readiness 200、真实请求、tokenization revision／落盘及 EnvironmentFile 等价覆盖路径。Plan 应记录为已实现、待 R3 复核，而不是继续列为回并后尚未实现的 minor；这不会扩大 M1，因为实现已随权限提交进入候选。

## 主观建议

未提出额外主观建议。本轮唯一 finding 是可由 Plan、已落盘 code R2、候选提交链与 current R3 文件状态直接裁决的 living 状态漂移；技术路线与后续范围无需重写。

## 结构怪味扫描

- `docs/agents/systemd-runtime/plan.md:5-6,28-38,85-87,143-183,310-315,393-395` — **living 状态真相源整页滞后／同一状态多点手工复述** — 本轮按 major 处理并给出逐位置同步清单。后续每次候选或 verdict 变化，应在同一修订中更新头部、事实区、看板、阶段正文、disposition 与 kick-off，避免再次只改一处。
- 扫描范围还包括 M1 与 S3～S7 的阶段边界、权限合同、真实 fd smoke、continuity、timeout、helper、cgroup 与 rolling；除上述状态漂移外，未发现新的职责错位、范围回退、抽象泄漏或不必要自研机制。

## 方案反思

1. **更好的内部替代方案**：无需改变 Plan 架构；最小且完整的修法是同步现有状态真相源，而不是重排里程碑或把后续强化塞回 M1。权限继续由 systemd 原生 `StateDirectoryMode=`／`UMask=` 在共享部署层闭合，优于分散修改 writer。
2. **判据判别力**：新增权限测试读取 unit mode／umask并运行真实 writers，能区分旧 `0755／0022 → 0644` 与新 `0700／0077 → 0600`；扩展 smoke 又走真实 CLI／Uvicorn、readiness、request、History、tokenization 与覆盖路径。它仍不证明真实 systemd manager 已安装或真实 cgroup 已施加，Plan 已正确把这些留给后续强化。
3. **成熟第三方方案**：当前继续复用 systemd 与 Uvicorn 原生机制，无需新增库；本轮只是 Plan 状态同步，不存在应引入第三方工具的新实现面。

## 继续实施条件

1. 按上述清单把 Plan 从 `candidate@1a220e04…／待 code R2` 同步为 `candidate@49fb198…／code R2 已消费／权限修复已实现／code R3 待结论`。
2. 若修订时 code R3 已落盘，消费其实际 verdict：只有 `0 blocker／0 major` 才把 M1 标为“可继续实施，可立即 squash／准备回并”；否则记录新 finding 并继续修复／复评。
3. code R3 为 0 major 时，squash 三个候选提交并在回并目标上重跑 M1 gates；不要等待 listener continuity 深化、graceful timeout、install helper、cgroup observability 或 rolling。

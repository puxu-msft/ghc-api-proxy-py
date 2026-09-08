# Implementation current 独立定向复评 R3

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 current `docs/agents/anthropic-responses-bridge/implementation.md`，精确 SHA-256 `7134cd99af9bfdf7f04d9d2967b8d391659bb68c57e77592e5abfa0393aab049`；固定 `main@b91e58a29324b11840002efc53ed6f869b800c39`。定向核对 History `2e3a6d2…` R2、reasoning capability `8bff1c3…`、stream `bc436af…` R2 与现场修复状态、systemd `8cae6c2… → d3fabfa…` 的 review／verification／未 main 边界、Readiness current verdict、备用端口 smoke R3、Implementation living／`UNVERIFIED`／`NO_CUTOVER` 及下一动作。除本报告外未修改文档、代码、Git refs、worktree、服务或运行态。
- **总体 verdict**：**修复 major 后可进入。当前不可 checkpoint。** Stream、systemd、Readiness、产品与部署边界仍准确，但 History、capability、备用端口计划三项 current identity 已前进，文档仍保留旧状态；同时“下一步”把 living checkpoint 排在继续改代码与 systemd 回放之后，与本文自身的先更新事实再继续纪律相冲突。当前为 **0 blocker／4 major**。
- **blocker 数**：0。
- **major 数**：4。
- **checkpoint 条件**：关闭下列四项 major，并对新 `implementation.md` SHA-256 定向复评至 **0 blocker／0 major** 后，必须明确允许该 exact bytes 立即形成 living checkpoint。该 checkpoint 只放行 current 状态记录与后续实施，不表示 Implementation 收口，不升级完整产品 `UNVERIFIED`，也不改变部署 `NO_CUTOVER`。

## 双视角覆盖证据

### 机械核对

- 每个承载结论的 shell 调用均在同一次调用内验证物理 cwd、Git top-level、`main@b91e58a29324b11840002efc53ed6f869b800c39` 与目标文档 SHA-256 `7134cd99af9bfdf7f04d9d2967b8d391659bb68c57e77592e5abfa0393aab049`。共享终端返回但缺少本轮 gate 标记的串线输出全部作废；只有重新取得完整 gate 的结果进入本结论。
- History worktree 精确为 `fix/responses-history-facts@2e3a6d2022244a6bca0e2db05e079bc27d94a585`，parent 为 `e5db34bcf7be017e602fb1ee3f666b3ad2e96a3f`，tracked tree clean。`docs/tmp/260807-resume-review-history-facts-r2.md` 已绑定该 exact candidate并给出 `0 blocker／1 major／1 minor`、不可 squash；唯一 major 是生产 `TokenCalibrationSuccessObserver` 仍可在最终 hook／严格验证失败前写 success calibration fact。现场没有后继 commit或未提交 tracked修复可证明该 major已经关闭。
- Capability worktree 已从旧未提交 WIP 前进为 clean candidate `fix/responses-reasoning-capability@8bff1c3fbd721060a87f18b0ef9d90d7d998a997`，parent 精确为 `b91e58a…`，subject 为 `fix: fail closed on ambiguous reasoning efforts`，只修改 `src/app/anthropic/client.py` 与 `tests/smoke/test_anthropic_responses_route.py`。在 `docs/tmp/**/*.md` 中检索完整 HEAD 无命中，因此旧 WIP 的 `0 blocker／1 major` 报告不覆盖该 commit；current 状态应为“clean candidate 已形成，待精确绑定独立评审”。
- Stream worktree 仍为 `feat/anthropic-responses-stream-route@bc436af647507df4ea45f3b01ca8942fade4f036`，有 9 个 tracked文件修改，符合“在同一 R2 HEAD 上正修”的现场状态。`docs/tmp/260807-resume-review-code-stream-route-r2.md` 明确为 `0 blocker／5 major`、不可 squash；限定验收 R2 的 `PASS` 不覆盖 cancellation-resilient cleanup、authoritative text一致性、缺失 usage、delivery uncertainty History与terminal identity／seal五项 major。目标文档对此范围和禁止外推边界准确。
- Systemd rebuilt链仍为 `b91e58a… → 8cae6c260c8bc2930be96eaecc7d6d24d470e00a → d3fabfadfba57af6c2d63e543e3198444777df54`，tip未进入main；目标 worktree的tracked tree未漂移，仅有既存未跟踪`docs/tmp/`。`260807-resume-review-systemd-rebuild.md`为`0 blocker／0 major`并允许按序逐片squash，`260807-verify-systemd-rebuild-resume.md`与`260807-resume-verify-systemd-rebuild.md`均为exact-tip `PASS`。目标文档准确保留逐片main-side identity／preimage／tests gate，以及未安装、未操作真实manager／cgroup、未部署、未cutover边界。
- Readiness报告 `docs/tmp/260807-resume-review-readiness-current-r2.md` 精确绑定 SHA-256 `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8`，结论为 `0 blocker／0 major`、exact bytes可 checkpoint。该报告自身仍绑定当时的旧stream `2087f8f…`事实，因此它只证明该Readiness内容身份取得过0 major；目标Implementation没有把它外推为current stream候选通过。
- 备用端口计划已形成新文件 `docs/tmp/260807-resume-backup-port-smoke-r3.md`，由 `sha256sum` 与 Python `hashlib` 交叉得到 SHA-256 `2bf1dbd5c977728be802d818b752f33a626f98b0382b3c993cd1b0ea1f061821`。R3明确为`PLAN_ONLY／NOT_RUN`，通过精确argv schema、hash-free cmdline与同一完整candidate独立`0 blocker／0 major`硬门来处置R2两项major；但在`docs/tmp/**/*.md`检索该完整hash无命中，所以只能写“R3已形成、待独立定向复评”，不能写成R2两项major已经获复评关闭或计划可执行。
- 目标文档继续明确保持 Implementation `LIVING`、完整bridge `UNVERIFIED`、部署 `NO_CUTOVER`，并禁止由局部review、阶段`PASS`、主树回归或备用端口current-layer smoke升级产品／部署结论；未发现该边界倒退。

### 第一人称执行

- **作为 History 修复者**：现文会让我对 `2e3a6d2…`“执行 R2”，但 R2 已经完成并发现生产 builtin observer时序 major；照文执行会重复评审旧HEAD，而不是修该 major、形成新完整身份并复评。
- **作为 capability 修复者**：现文仍让我在 `main@b91e58a…` 的“未提交 WIP”上继续修并在 0／0 前不得 commit，但候选已经作为 clean commit `8bff1c3…` 形成。照文执行会在错误身份上重复修改或误以为没有可绑定评审载体；正确下一动作是直接评审 `8bff1c3…`，不得沿用旧 WIP verdict。
- **作为 stream 修复者**：我会保留 `bc436af…` 的五项major，继续在当前dirty工作树修复，形成新完整HEAD后复评；不会把限定验收`PASS`拼成代码放行，也不会在0／0前squash或进入STREAM-MERGE。现文在此路径可执行。
- **作为 systemd回放者**：我会按S3→S4逐片执行main-side identity／preimage／tests gate，任一失败即停；不会重复candidate-side review／verification，也不会安装unit、操作manager／cgroup、触碰生产`4141`或执行cutover。现文在此路径可执行。
- **作为备用端口计划维护者**：现文会让我继续“修订R2计划”，但R3已经存在；正确动作是绑定R3 hash进行独立定向复评。即使R3文档复评为0 major，也只有完整stream candidate本身取得独立0／0后才可执行，当前仍保持`PLAN_ONLY／NOT_RUN`。
- **作为living文档维护者**：现文第1步先继续三条代码线、第2步执行systemd回放、第3步才形成checkpoint。任一前两步都会再次改变current事实，使刚评审的Implementation在checkpoint前再次陈旧；capability与History本轮漂移已经实证这一失败模式。正确顺序是先修本轮文档major、定向复评、立即checkpoint，再继续代码／回放；后续每次事实变化再次更新与checkpoint。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md:11,42,76,82,92,105,210,244,263,270,278` — History `2e3a6d2…` 的 R2 已落盘且仍有 1 major，文档却反复写成“待 R2” — `260807-resume-review-history-facts-r2.md:3-6,39,49` 精确绑定该 HEAD，结论为 `0 blocker／1 major／1 minor`、不可 squash；tracked tree现场仍clean于同一HEAD，没有后继身份证明该major已修。现文下一动作“直接进入R2”会重复旧评审并漏掉真实阻断，即生产builtin token calibration observer在最终失败前写success fact — 将所有current入口统一改为“R2已完成，0 blocker／1 major／1 minor，不可squash；处于修复阶段，现场尚无后继tracked候选”。下一动作改为修复observer事件时序、补真实builtin负向回归、形成新完整HEAD并复评到0／0；不得把“施工阶段”写成major已关闭。

[major] `docs/agents/anthropic-responses-bridge/implementation.md:11,44,75,82,91,101,105,210,244,263,278` — Capability 已形成 clean candidate `8bff1c3…`，文档仍把它写成 `b91e58a…` 上的未提交WIP和“正修首评1 major” — Git现场确认该commit以`b91e58a…`为parent、只改两条声明路径且worktree clean；旧`260807-resume-review-reasoning-capability-wip.md`只绑定未提交patch身份，`docs/tmp`没有精确绑定`8bff1c3…`的报告。现文甚至要求“0／0前不commit”，与已发生的commit事实矛盾，会让执行者重复修复或错误选择评审对象 — 统一更新为“clean candidate `8bff1c3…`已形成，旧WIP 1 major的修复已提交但尚未经该HEAD独立复评；main major仍open”。下一动作是直接对`8bff1c3…`做精确绑定代码评审／验证；只有0／0及后续回放门完成后才能改变main状态。

[major] `docs/agents/anthropic-responses-bridge/implementation.md:15,45,210,247,263,272,278` — 备用端口状态停在R2 `0 blocker／2 major`与“先修订计划”，遗漏已经形成但尚待复评的R3 — `260807-resume-backup-port-smoke-r3.md@2bf1dbd5…`已把CLI credential／raw cmdline旁路和完整candidate 0／0硬门写成新计划，状态为`PLAN_ONLY／NOT_RUN`；没有报告精确绑定该hash，因此不能把R3自述冒充两项major已获独立关闭。现文会让执行者重复编写计划或误改历史R2，而不是评审current R3 — 更新为“R2历史评审为0／2；R3新bytes已形成、意图关闭两项major、待独立定向复评”。下一动作是复评R3；在R3 0／0及同一完整stream candidate代码0／0之前均不得执行STREAM-MERGE，`PASS_CURRENT_LAYER`仍不得外推。

[major] `docs/agents/anthropic-responses-bridge/implementation.md:8-9,240,244-247` — “下一步”把living checkpoint排在继续修改三条代码线和systemd回放之后，执行顺序会保证待提交内容再次陈旧 — 本文自身要求任何新代码、评审、回放或新发现都先更新current事实再继续，并说明0／0可形成checkpoint；但当前顺序要求先完成多项会改变History／capability／stream／main HEAD的动作，最后才checkpoint当前文档。Capability与History已在本轮从文档记录状态前进，正是该顺序的现实反例 — 把当前第一动作改为“消费本轮R3 findings，更新全部current入口，对新hash定向复评；达到0 blocker／0 major后立即checkpoint”。Checkpoint之后再并行执行History修复、capability exact-HEAD评审、stream五项修复／复评、backup smoke R3文档复评与systemd逐片main-side gate；每个事实变化后再次更新living文档，不等待所有代码线结束才记录。

## 已通过的定向核对

- **Stream current 状态准确**：`bc436af…`代码R2仍为`0 blocker／5 major`，现场tracked WIP证明修复正在同一HEAD后继续；限定验收`PASS`没有被误作代码放行。
- **Systemd current 状态准确**：`8cae6c2… → d3fabfa…`已获merged-state review `0 blocker／0 major`与两份exact-tip `PASS`，仍未main；下一代码动作确为逐片main-side gate，不是重复candidate-side review／verify。
- **Readiness verdict引用准确**：`c1e8494e…`的独立R2为`0 blocker／0 major`且允许其exact bytes checkpoint；Implementation没有把该文档verdict外推为current stream或产品通过。
- **Living／产品／部署边界准确**：Implementation保持`LIVING`，完整bridge保持`UNVERIFIED`，部署保持`NO_CUTOVER`；没有授权安装unit、操作真实manager／cgroup、停止旧Bun、接管`4141`或执行cutover。

## 主观建议

无。本轮四项均是可复现的current-state或执行顺序错误，不以主观精简建议替代事实性finding。

## 结构怪味复核

- **范围**：顶部current状态、major处置表、总体进度、活动开发线、文档复评表、收敛策略、下一步、结构怪味表与尾部总结。
- **发现**：`docs/agents/anthropic-responses-bridge/implementation.md:11,15,42,44-45,75-77,82,91-93,101,105,210,244-247,263,270-272,278` — **弱一致性副本／living checkpoint滞后** — 同一候选身份和gate被复制到多个current入口，且checkpoint被排到事实继续变化之后，导致三类状态只更新了部分表面。该怪味已由上述四项major覆盖，不另计严重级别。修复时必须全文同步，不得只改顶部或“下一步”。

## 最终结论

本轮为 **0 blocker／4 major**，因此精确 SHA-256 `7134cd99af9bfdf7f04d9d2967b8d391659bb68c57e77592e5abfa0393aab049` 的 current Implementation **不可 checkpoint**。

关闭四项major后，对新内容身份重新定向复评。若新一轮达到 **0 blocker／0 major**，则应明确裁定：**该 exact Implementation bytes 可以立即形成living checkpoint**。该裁定只批准状态记录与后续实施，不表示文档定稿或收口，不表示History／capability／stream候选已进入main，不表示systemd已安装或部署，不升级完整bridge `UNVERIFIED`，也不改变`NO_CUTOVER`。

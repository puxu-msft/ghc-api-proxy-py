# Identity living checkpoint 联合定向复评

- **评审范围**：联合复评 `docs/agents/anthropic-responses-bridge/implementation.md` 的精确 SHA-256 `4d182174052419fd7e70846935c43d7ea40dc1803652cad0187672e52bf145ef`、`docs/agents/service-cutover/readiness.md` 的精确 SHA-256 `9f57037fba237a90782142d699abfdfacf6697ead13c86f49e35ef77edf5acfb`，以及现场 `main@c188165dd413b7683a65472781ca3bef9c1a29b3`。只核对 token identity、resident 主线归属、真实 readiness／canary、response identity 候选终审与主线归属、manager 阻塞、`LIVING／UNVERIFIED／NO_CUTOVER`、readiness 43 行及下一 checkpoint。本轮不复评候选代码，不修改两份被评文档，不执行 squash、canary、服务操作、部署或 cutover。
- **总体 verdict**：**修复 1 项 major 后可进入 checkpoint；当前不是 0 major。** 两份文档的主体边界正确，但都把已经完成且为 0 major 的 identity 终审继续写成“待终审”，导致下一执行序列多出一个已完成步骤。修订为“终审 0 blocker／0 major／0 minor，可 squash但未 main；下一 checkpoint 为 identity squash→同一真实 canary 复跑”后，可重新定向复评该新内容身份。
- **Blocker 数**：0。
- **Major 数**：1。
- **Minor 数**：0。
- **双视角覆盖证据**：
  - **机械核对**：现场验证物理 repo root、`main` 分支、`HEAD == refs/heads/main == c188165dd413b7683a65472781ca3bef9c1a29b3`；以 `sha256sum` 复算两份指定文档 SHA；以 Git object、ancestor 与 archive ref 核对 token identity、resident primitive／wiring及 identity candidate 的主线归属；读取 identity R2 终审、identity squash 审计与 S5 manager 执行记录；扫描两文档全部“待终审／先终审”复述；用 Python 分节计表与独立 AWK 状态机两种原理交叉复算 43 行。
  - **第一人称执行模拟**：按文档当前“下一步”从 `main@c188165…`执行时，执行者会先重复发起已经完成的 `1bc5a818…`终审，而不是消费既有 0 major verdict 进入 squash；按正确路径则应先重验 squash gate，在 identity 进入 main 后以同一 `route_override=responses`、真实 Copilot 启动路径和 `gpt-5.3-codex`保留 non-stream 200 正控并复跑 stream。另模拟了把真实 readiness 200误当 manager/cgroup 通过、把 candidate 绿灯误当已 main、把 resident 主线绿灯误当完整产品通过三条错误路径，两份文档均明确阻止这些外推。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md:14,17,60,101,125,238,250,292,307`；`docs/agents/service-cutover/readiness.md:6,9,42,55,124,150,160,181` — 两份 living 真相源仍把 identity candidate `1bc5a8185a6a19101679e13c9a3a0bda3072bab4`写成“待独立终审”，并把下一 checkpoint 排为“identity 终审→squash→同一真实 canary 复跑” — `docs/tmp/260807-review-copilot-response-identity-r2.md:4-7`已经精确绑定同一 base `c188165…`与 candidate `1bc5a818…`，结论为 `0 blocker／0 major／0 minor，可 squash`；`docs/tmp/260807-audit-copilot-response-identity-squash.md:3-13`又独立确认可进入单一 squash。Git 现场同时证明 `1bc5a818…`不是 `main`祖先，所以正确 current 状态是“终审已完成且 0 major，可 squash但未 main”，不是“待终审”也不是“已 main”。执行者照当前文档会重复已完成的 gate，且 living checkpoint 会冻结错误的下一动作 — 在两份文档所有 current 状态、进度表、活动线、阻塞链、结构怪味与结尾汇总中同步改为“identity R2 终审 0／0／0，可 squash、未 main”；把下一 checkpoint 统一改为“identity squash→同一真实 canary 复跑”。保留 squash 前对当时 main identity、preimage、pathset、并行 WIP及 main-side tests的重验，不得把终审绿灯写成已 main或真实 stream 已修复。

除上述 major 外，未发现其他事实性问题。

## 已核对且成立的边界

1. **Token identity 已进入 main。** 现场 `main`为 `c188165dd413b7683a65472781ca3bef9c1a29b3`；`archive/260807-copilot-token-identity`精确指向 reviewed source `8f164d897966fd80f9a5087083f420f2caf79ac9`。两份文档在此轴一致。
2. **Resident 已进入 main。** Resident primitive `29c0ce3230181a113363eb398dfa24d8e41a9012`与 production stream resident wiring `941299fe5a5275c4a5fc327d172a1deeccfb3085`均为 current main祖先。两份文档没有把该局部主线事实外推为完整 quota、partial-write或完整 Acceptance `PASS`。
3. **真实 current layer 边界一致。** 两份文档均记录真实启动 readiness 200、模型目录 32／10、正式 Responses override下 `gpt-5.3-codex` non-stream HTTP 200，以及 stream HTTP 502／typed `response_id_mismatch`。本轮只核对两文档间一致性与既有证据链，不重新发起真实网络 canary；因此修复候选未 main前，stream真实缺口仍保持开放。
4. **Identity candidate 终审已归零但未 main。** R2终审明确为 0 blocker／0 major／0 minor且可 squash；Git ancestor探针明确返回 candidate尚未进入 main。候选测试绿灯与终审结论都不能替代 main-side squash gate或 canary复跑。
5. **Manager 仍为 `BLOCKED`。** `docs/tmp/260807-systemd-user-manager-smoke.md:5,16-19`记录独立 `systemd --user`未创建 private control socket，真实 activation、fd inheritance、effective cgroup、restart与manager stop均未执行。真实应用 readiness 200不是 manager／cgroup证据，两份文档对此没有错误升级。
6. **状态边界保持。** Implementation继续为 `LIVING`，完整产品继续为 `UNVERIFIED`，部署继续为 `NO_CUTOVER`。Identity终审 0 major只放行 squash gate，不改变上述三态。
7. **Readiness 43 行成立。** 两种独立计数方法均得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43。该数字口径绑定 readiness SHA-256 `9f57037f…`与本轮现场文件，不外推到后继 bytes。

## 正确的下一 checkpoint

1. 消费已经完成的 `1bc5a818…` R2终审 0／0／0与 squash审计，不再重复“先终审”。
2. 在当时 current main重新核验 identity、preimage、五路径、并行 WIP与 staged result，只形成单一 identity squash，并运行 main-side定向＋全量 tests、Ruff与Pyright；任一门失败即停。
3. Identity进入 main后，以同一正式 `route_override=responses`、同一真实 Copilot启动路径与 `gpt-5.3-codex`复跑 canary：先复核 readiness 200与32／10目录，保留 non-stream 200正控，再要求 stream不再返回502／`response_id_mismatch`且满足既有 strict Anthropic SSE终态合同。
4. 即使同一 canary转绿，完整quota、真实sink partial-write／delivery-uncertain、完整credential disposition、真实manager／cgroup、P2／P3与完整Acceptance仍分别保持原状态，不得升级为完整产品或 cutover `PASS`。

## 主观建议

无。当前问题是可证实的 living 状态漂移，不是措辞偏好。

## 报告评审状态

本报告由叶子 reviewer产生，已完成双视角核对、数字双算法交叉验证与全文复读。按项目规则，它作为承载 current-state断言的评审产物仍需由主会话安排独立复核；该义务不改变本轮 `0 blocker／1 major／0 minor`结论。

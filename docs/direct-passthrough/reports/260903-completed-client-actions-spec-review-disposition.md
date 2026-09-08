# `completed` 与 client actions 规格评审处置

日期：2026-09-03

对象：[`../spec.md`](../spec.md)、[`../../tui/spec.md`](../../tui/spec.md)、[`../../tui/deferred.md`](../../tui/deferred.md)

首轮评审结论：0 blocker、5 major，全部采纳并已修订；后续复评与整改见下。原 reviewer 位于隔离 worktree，其写入主树 `.dev` 的动作被 harness 拒绝；本文件是主会话的处置记录，不冒充 reviewer 原报告。完整首轮报告保留在本会话 transcript，未代 reviewer 绕过被拒的写入。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| F01：彩色 expected 与既有工具名灰色合同冲突 | 采纳 | C | TUI 验收改为逐字断言 `completed` 与 action type 不着色、普通 action name 使用 `DIM`；纯文本集成断言另行比较，避免把 ANSI 与无色输出混成一个 oracle |
| F02：action 顺序 authority 未定义，端到端判据看不见反序 `done` | 采纳 | C | 顺序明确为 Responses `output_index` 数值升序，不读 `done` 到达顺序；集成样本加入两个重复 `function_call` 与一个无名 `custom_tool_call`，闭合顺序反转，断言 exactly-once 的完整尾段；另列按 `done` 排序的缺陷注入控制 |
| F03：policy bool 无法表达 `unknown`，却被当作事实分类 | 采纳 | C | direct Spec §7.1 改为 `required`、`not_required`、`unknown` 三态事实分类，`requires_client_action` 只作 policy 布尔投影；unknown 保留原生 type/name，展示为 `client_action?(...)`，并与 required 一样阻止 `completed` 变绿，但不声称已确认模型在等待 |
| F04：正文写 direct 全路径，设计与 oracle 实际只覆盖 streaming | 采纳 | C | 本轮定义域明确为原生 Responses 流式直连；非流式 `/responses` 的 whole-body reader 仍由 TUI deferred 第 0 条持有，不将缺席写成已覆盖 |
| F05：把顺序、重复、无名、unknown 都归作用户明确裁决 | 采纳 | C | provenance 拆开：用户主动指出 `completed + function_call/custom_tool_call` 不代表工作结束，并选择两槽组合判读；三态、顺序、重复、无名、unknown 与 streaming 定义域明确标为本规格推导 |

## 第二轮复评处置

第二轮报告位于 reviewer 隔离 worktree 的 `review-completed-client-actions-spec-round2.md`。F01、F02、F04、F05 closed；F03 partially closed，新增 1 个 major。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| round2-01：空 actions 不能证明整组 output items 已完成分类 | 采纳，初版整改后被第三轮收窄 | C | 新增集合级 `client_action_classification_complete` 与 terminal `response.output` authority。初版还要求 stream 无未闭合 item；第三轮核验后确认这把 terminal snapshot 分类与交付完整性绑成一格，最终定义改为只回答 terminal `output` 是否存在为数组并逐项得到三态分类，stream 完整性继续由既有 verdict、detail 与 `cut_mid_block` 回答 |

## 第三轮复评处置

第三轮报告位于 reviewer 隔离 worktree 的 `review-completed-client-actions-spec-round3.md`。数据合同已确认闭合，新增 1 个 major 指向验收对 terminal authority 与集合条件覆盖不足。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| round3-01：terminal authority、显式空数组、错误 output、越界与 unattributed 边界缺少可判否 oracle | 部分采纳，待原 reviewer 合议 | C | 采纳 terminal authority、显式 `output=[]`、缺席或错误类型 output、unattributed 不影响完整 terminal snapshot 四类可判否对照，并让 `done` snapshot 与 terminal output 在名称上故意分歧以证明 source of truth；第四轮随后指出这一控制尚未覆盖承重的 requirement，见下。未采纳把 stream 越界 index 与未闭合 item 继续列为 `client_action_classification_complete` 条件：该字段只回答 terminal snapshot 的 action 分类是否完备，交付完整性已有 §4、§7.2、`cut_mid_block`、verdict 与 detail；把两者绑定会为一个颜色修复建立第二套交付状态机。相应条件已从 Spec 删除，因此不再欠其颜色验收；这一 C 级分歧交回原 reviewer 明确表态 |

## 第四轮复评处置

第四轮报告位于 reviewer 隔离 worktree 的 `review-completed-client-actions-spec-round4.md`。Reviewer 明确接受 terminal snapshot 分类与 stream delivery 完整性的职责分离，并撤回把越界或未闭合 item 纳入完备标志的建议；剩余 1 个 major 只指向 source-of-truth oracle 没有让 requirement 分歧。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| round4-01：done/terminal 分歧只覆盖 name，未覆盖决定绿色的 requirement | 采纳，action-list 半面关闭后由第五轮补齐 color 半面 | C | route (e) 先让 `output_index=0` 在 done snapshot 中为 `tool_search_call(execution=server)`、terminal output 中为 `function_call(Bash)`，形成 `not_required` 对 `required` 的相反三态；第五轮指出其它 done item 仍可让 done-side `any(required)` 为 true，见下 |

## 第五轮复评处置

第五轮报告位于 reviewer 隔离 worktree 的 `review-completed-client-actions-spec-round5.md`。Action facts 的 terminal authority 已关闭，剩余 1 个 major 是颜色消费者仍可偷读 done-side bool。

| Finding | 处置 | 级别 | 理由与改动 |
|---|---|---|---|
| round5-01：action 列正确时，颜色仍可由 done-side `_saw_client_action` 驱动 | 采纳 | C | route (e) 的三个 done snapshots 全部改为 `tool_search_call(execution=server)`，使 done-side `any(required)` 为 false；terminal output 三项全部为 required。正确实现仍显示三项 action 且 `completed` 不绿，混合来源实现会在 action 列正确的同时把 `completed` 染绿。缺陷列表显式加入“action 列读 terminal、颜色偷读 done bool”，要求颜色断言单独变红 |

## 第六轮终评

第六轮报告位于 reviewer 隔离 worktree 的 `review-completed-client-actions-spec-round6.md`。结论为 **pass：0 blocker、0 major，可定稿**。Action-list consumer 与 color consumer 都必须服从 terminal output，并各有能单独判红的 oracle；clean `completed` 与 action-present `completed` 的正反方向同时保留。未重开此前已关闭项。

未采纳项：round3-01 中“把 stream 越界与未闭合 item 纳入 terminal snapshot 分类完备”的建议未采纳；原 reviewer 已在第四轮明确接受理由并撤回该建议，C 级分歧 closed。

复评范围：F01～F05 的原发现、本轮整改，以及整改相邻的 §4、§7.1、§10、TUI 封闭颜色白名单与 deferred 第 0 条和第 1 条。
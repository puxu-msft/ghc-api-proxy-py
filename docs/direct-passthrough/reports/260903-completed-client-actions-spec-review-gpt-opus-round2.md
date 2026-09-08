---
report_id: review-completed-client-actions-spec-round2
attempt_id: agent-a40c43530f7a688a4-round2
status: in-review
reviewed_at_rev: "main@4b7d74f56b8b0264b481a2fefe275a233979fbb2; .dev dotdev@15baeb1820d750bd190c78d874a674052b250004 + 2026-09-03T23:06:17+00:00 filesystem snapshot"
---

# `completed` 与 client actions Spec 第二轮复评

## 评审范围

仅复核上一轮 F01～F05、`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260903-completed-client-actions-spec-review-disposition.md` 的处置主张，以及整改相邻的 direct-passthrough §4、§7.1、§10、TUI 封闭颜色白名单与 deferred 第 0／1 条。未评审尚未编写的实现。

## 总体判定

**VERDICT：needs-fix。blocker 0，major 1。** F01、F02、F04、F05 已关闭；F03 的三态合同本身已修正，但新引入的 `unknown`／集合完整性分支仍没有可判否的验收，且 `client_actions` 为空仍可能把“尚未得到分类”误读成“已确认没有 action”，因此 F03 只部分关闭。处置记录的“全部采纳并已修订”成立，但若据此主张 F01～F05 全部 closed，则站不住。

## F01～F05 关闭状态

| Finding | 状态 | 复评依据 |
|---|---|---|
| F01 | **closed** | `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:131-145,188` 的彩色 exact expected 已包含普通名称的 `DIM...RESET`，并单独声明 action type 与 `completed` 不着色；与封闭颜色白名单一致。 |
| F02 | **closed** | `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:670` 与 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:160,188` 已把顺序 authority 钉为 `output_index` 数值升序；反序 `done`、重复、无名与 exactly-once 都穿过真实 streaming `/responses` 内部链，并配有错误排序控制。 |
| F03 | **partially-closed** | `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:517-531,665-673` 已把事实三态与 policy bool 分开，也保留 native type；但下述 round2-01 仍让 unknown／未分类缺席无法由验收识别。 |
| F04 | **closed** | `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:3,160,170,200` 与 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:4,667,711` 均明确本轮只覆盖 Responses streaming direct；`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/deferred.md:7-21` 继续持有 buffered `/responses` whole-body reader。 |
| F05 | **closed** | `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:145,160,200` 与 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:673,711` 已区分用户主动指出／选择的核心与 Spec 推导出的三态、顺序、重复、无名、unknown、streaming 定义域。 |

## Findings

### review-completed-client-actions-spec-round2-01
severity: major | primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:131,145,188`
related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:182-197,517-531,665-671`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:171-200,285-323`；`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/delivery/test_responses_passthrough.py:155-196`
证据：颜色合同说只有“output items 已确认不要求行动”才绿，但可观察载体只列 `required/unknown client_actions`；§4 明确允许 terminal 到达时仍有未闭合或 unattributed item。只读 probe 对 `function_call added → response.completed → EOF` 得到 `terminal_seen=True, stop_reason=end_turn, unfinished=1`，此时没有 `done` 可形成最终 action fact，列表空不等于确认无 action。
影响：一个仍按已批准草案在 `done` 时记 fact、或漏掉 `unknown` 的实现，会把该 `completed` 染绿；现验收的所有 action 都完整 `done`，且没有 unknown／known-not-required 的真实路由对照，所以这种假修复以及“所有 item 都判 unknown”的反向假修复均可全绿。
建议：规范一个集合级“分类已完备”事实或等价判据，明确未闭合／unattributed item 如何影响 `completed` 颜色；验收至少加入 complete `not_required` 仍绿、complete `unknown` 不绿、terminal 时 action item 未闭合不绿三组内部路由对照。

## 相邻条款一致性

- §4 的 wire 顺序与 TUI 的展示排序已明确分离：wire 不重排，展示 facts 按 `output_index` 排序，不冲突。
- §7.1 的三态与 buffering policy 的布尔投影现在职责清楚；问题只剩集合级缺席与验收，不能再用 per-item bool 解决。
- §10 继续明确 `terminal_status` 不覆盖 `Terminal.stop_reason`，未重新破坏 framing、delivery 或 continuation。
- deferred 第 0 条仍持有 buffered reader，第 1 条仍持有 translated Responses status；没有误结案或范围外推。

## 未采纳／被排除路线

1. **不重开 F01、F02、F04、F05。** 当前文本已逐项消除原始矛盾，继续要求修改只会重复评审已关闭字节。
2. **不把 mock upstream 冒充真实上游。** 新验收仍明确只证明本代理 collector／trace／line 接线；该限定成立。
3. **不要求把 buffered 或 translated Responses 纳入本轮。** 两项都由 deferred 的现存条目继续承载，且本轮 streaming 定义域已明确。
4. **不接受“合法上游一定完整，所以无需表示分类是否完备”。** direct Spec §4 与当前 assembler 已把 terminal＋未闭合／unattributed 作为支持状态处理；同一份 Spec 不能在颜色层假定该状态不存在。

## 搜索面与命令证据

读取了四份指定文档的整改区间、direct §4／§7.1／§10、TUI 颜色与验收、deferred 0／1，以及现有 assembler 与其 interleaving／unfinished／unattributed 测试。只读 probe 使用当前 source 构造 `function_call added → response.completed` 而不发送 `done`，输出为 `terminal_seen= True stop_reason= end_turn unfinished= 1`。未运行全量测试，因为本轮只复评待实现 Spec 的判据；未修改主树 `.dev`。

## 我最没把握的三个判断

1. **round2-01 的具体数据形态。** `classification_complete` 只是候选，不是唯一修法；也可由 terminal `response.output` 与已完成 item 对账。承重结论仅是“列表为空不能独自证明全体已分类”。
2. **unattributed 对颜色的统一处置。** audio 事件可能明确不要求客户端行动，不能简单规定任何 unattributed 都阻止绿色；Spec 应给可判定分类／完备规则，而不是采用一律不绿。
3. **terminal＋未闭合 item 的线上频率。** 当前证据证明代码与 Spec 支持该状态，不证明真实 Copilot 已产生；major 定级依据是 acceptance 对 Spec 已纳入状态失明，而不是生产频率声称。

## 执行本契约时遇到的摩擦

none

## 整体判定

F01、F02、F04、F05 可保持 closed；F03 需补齐集合级 unknown／分类完备合同与对应可判否验收后再关闭。当前仍不可定稿。

## 交付声明

delivery_complete: true
completed_at: 2026-09-03T23:06:17+00:00
finding_total: 1
blocker_count: 0
major_count: 1
minor_count: 0
nit_count: 0

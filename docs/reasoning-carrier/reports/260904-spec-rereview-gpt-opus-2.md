# Reasoning carrier Spec 第二轮限定复评

复评对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`、`/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec-review-disposition.md`。

基准报告：`/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/reports/260904-spec-review-gpt-opus-1.md`。本轮只复核原 M1～M6、对应修订及修订直接触及的相邻合同，不作全量新评审。

## Verdict

**needs-fix**。原 M3、M5、M6 已闭合；M1、M2、M4 的主要方向已采纳，但修订仍留下 3 项 major。当前尚不可进入实施；没有 blocker。

## 原 findings 处置复核

| 原 finding | 复核结论 | 依据 |
|---|---|---|
| M1 summary event authority | 部分闭合，余 R1 | `spec.md:223-230` 已改用 `summary_index`，列出四类事件和 closing／part.done／text.done／delta precedence，也如实限定为 SDK 3.3.1 依据；但两个 SDK-declared 字段语义仍未处置。 |
| M2 same-format bypass | 部分闭合，余 R2 | `spec.md:181-187` 已把 resident guard 放在所有 target 的 `attempt.prepare`，选择 send 前稳定拒绝而非为 direct path虚构 `Conversion`；但扫描集合没有覆盖永久兼容的 `copilot-api` synthetic v1。 |
| M3 streaming／subscriber owners | 已闭合 | `spec.md:223,234-241,286-304` 已纳入 `Draft`、`CompletedBlock`、唯一 projection adapter、subscriber本体／注册／composition，并固定 blank-text → reasoning last-mile → trailing-assistant；同时裁掉 `blank_text.py` 的第二个 separator owner。 |
| M4 slot profile | 部分闭合，余 R3 | `spec.md:151-161,191-219` 已建立互斥 slot profiles与分类 precedence，解决一个 Responses item 恢复多个 Anthropic block 的歧义；但 profile 与 presentation 的判定边界自相冲突。 |
| M5 legal fixture | 已闭合 | `spec.md:260-264` 的正控已补齐三个 `type:"summary_text"`，expected为独立 literal，并分别要求经过 buffered、streaming和request-side decoder。 |
| M6 legacy helper | 已闭合 | `spec.md:301-304` 与 disposition 第 23 行已指定统一 core 为唯一语义 owner；旧 helper／protocol facade若保留只能薄委托，旧 tests迁到 core且 facade只留 delegation smoke。 |

## Remaining major findings

### R1 — 四类 summary event authority 仍丢 `part.added.text`，并把 incomplete `part.done` 当完成态（原 M1）
- `spec.md:225-227` 只把 `part.added` 当 type／extensions 基线，并无条件把 `part.done.part` 作为第二级完整 authority；但 SDK 3.3.1 的 `ResponseReasoningSummaryPartAddedEvent.Part` 明确含 `text`（`.venv/lib/python3.14/site-packages/openai/types/responses/response_reasoning_summary_part_added_event.py:10-17`）。
- `ResponseReasoningSummaryPartDoneEvent` 还声明可选 `status="incomplete"`（`.../response_reasoning_summary_part_done_event.py:21-47`）；仓内无真实 cassette，故没有依据假定 added text恒空或 done恒完整。
- 这足以让合法非空 added baseline丢字，或把已明确 incomplete 的 part封成完整 block／lossless carrier。应规定 added text为最低级 baseline并由delta追加、done覆盖；若无更高 closing summary，`status=incomplete`必须进入既有截断／失败生命周期，不能降级采用低层 accumulator。

### R2 — Resident guard 只识别项目 namespace，仍会泄漏永久兼容的 synthetic v1（原 M2）
- `spec.md:185` 的扫描谓词仅为 `ghc-api-proxy:synthetic-reasoning:*`，但同一 Spec 永久保留 `copilot-api-js` v1 consumer（`spec.md:13,200-202,245-250`），该值也是代理 carrier而非 Anthropic native signature。
- 当前统一 classifier 的兼容常量为 `copilot-api:synthetic-reasoning:v1[:...]`，并将其归为 `upstream_v1`／bare／malformed（`src/app/pipeline/translation_driver/reasoning_carrier.py:15-16,69-74,90-100`）。原 M2 已证 same-format route不调用 translator。
- 因而旧客户端历史中的合法 `copilot-api` carrier仍可在 Anthropic direct path穿过 guard到 provider，违反 `spec.md:39`。Guard必须覆盖 classifier认出的两套 synthetic namespaces／全部支持形态，而不是只匹配项目 prefix；last-mile capture也要各放一个兼容 v1 正控。

### R3 — Slot profile 的 visible约束抢先吞掉 presentation mismatch，分类 precedence仍不唯一（原 M4）
- Anthropic slot profile规定 `thinking` 必须与 layout描述的拼接相同（`spec.md:155-159`），而 precedence 又先把违反 profile visible形态归为 `project_v2_profile_mismatch`，随后才把 lengths总和／UTF-8边界／visible内容不符归为 `project_v2_presentation_mismatch`（`spec.md:205-215`）。
- 例如 layout `lengths:[1]` 配 visible `thinking:"ab"` 同时命中 profile表和 presentation规则；这直接违反“首个命中即停止、同一 carrier不得重新解释”。
- 应把 profile限定为 outer slot、record family与record cardinality等结构条件，把 layout↔visible跨字段关系全部留给 presentation；其中“cardinality”明确为 record cardinality。并在 `spec.md:254-278` 增加 profile／presentation的独立静态向量与跨 driver／helper／streaming一致性用例，当前列表只显式枚举旧 malformed／unknown／foreign路径。

## 进入实施条件

处置 R1 的两个遗漏字段、R2 的 compatibility namespace集合、R3 的互斥分类边界和对应验收后，原 M1～M6 即无剩余 blocker／major，可进入实施。当前 verdict 仍为 **needs-fix**。

边界结清判断：本轮仅产生这份限定复评报告，没有源码、Spec、测试、临时资产或 Git 状态需要清理／归档，不启动额外 closeout。

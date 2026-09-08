---
report_id: token-task3a-prediction-contract-rereview-2-claude
attempt_id: task3a-prediction-contract-rereview-claude-2
status: in-review
reviewed_at_rev: "spec-sha256:f734f8bfe70c8153fe75e609a291c9f3cf2fdcf73e17b03a438cee6072957cdd; plan-sha256:3dc7d33595d1412d2779fc034ce400d22a80d95b9ee0f868746e5f3a2b74e664; prior-rereview-sha256:2a6ad301748b2f089488b7ed1996a51c623d495e1961332d775752e132882d9e; prefix-rereview-sha256:75ffc629683544bd2fb20701bba04602d3e042f41a5bf1c08a8157c33fdcc6b1; dotdev-amendment:7684215"
reviewed_at: 2026-09-07
reviewer_role: Token Task 3A prediction-contract second scoped re-reviewer
---

# Token Task 3A prediction contract second scoped re-review

## 评审范围

本轮只核上一轮 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/reports/260907-task3a-prediction-contract-rereview-claude.md` 的new findings 01～03、原prediction DTO gap Findings 01／03的剩余open predicates、prefix reviewer `T3APCRR-01`及本次整改的直接相邻合同。Current behavior authority绑定Spec SHA-256 `f734f8bfe70c8153fe75e609a291c9f3cf2fdcf73e17b03a438cee6072957cdd`，plan绑定SHA-256 `3dc7d33595d1412d2779fc034ce400d22a80d95b9ee0f868746e5f3a2b74e664`，整改provenance为dotdev commit `7684215`。

未重审visual finding的原始设计论证、Task 3 cancellation／migration等已闭合合同或任何source；只做seven pairs／per-key bounds／visual slot／decision边界的相邻无回归核对。未运行tests，因为当前被检对象是living contract amendment，Task 3A source尚未启动。

## 总体 verdict

**APPROVED。Blocker 0，Major 0，Minor 0。** 上一轮三个new findings全部`ADDRESSED`；原Findings 01／03剩余open predicates和prefix reviewer `T3APCRR-01`均已关闭；本轮未发现新finding。Task 3A合同现在可以启动source实施。Task 4A仍须等待Task 3A source完成独立review并更新exact base，不可越过该顺序直接启动。

## 上一轮 new findings逐项状态

### token-task3a-prediction-contract-rereview-claude-01：ADDRESSED

- Spec §6.0现在把represented method精确定义为“该record至少有一个candidate key的method”，每个represented method恰有一个champion，absent method必须没有champion；missing represented champion、absent extra champion、wrong-method／missing key全部非法。
- Cold-start candidate始终存在；global selected从represented且eligible的champions按四个既有method顺序取第一项。A8给出empty snapshot的exact cold-only object：只含`cold-start/deterministic` candidate、cold champion和同一selected key，absent exact／prefix／profile没有champion。
- A32-P及plan Task 3／3A／4A分别转录cold-only合法正控和represented missing、absent extra、wrong／missing key负控，不再把“missing champion”无条件应用到absent methods。
- Spec §7.3把error evidence明确分为每candidate-key sequence与record冻结的point-in-time method-champion sequence；前者供variant comparison／diagnostics，后者供demotion／recovery／drift。§6.2 prefix variant selection、§6.3 profile variant selection、§6.2 demotion／recovery和§9 drift分别读取正确的槽，并禁止当前algorithm事后重选历史champion。

结论：上一轮cold-only反例与双sequence ambiguity都已消失，不改变七种pair或四个public methods。

### token-task3a-prediction-contract-rereview-claude-02：ADDRESSED

Living plan中上一轮点名的active restatements已全部同步：

- Continuous improvement第6项改为每candidate key独立newest128 budget，并同时区分candidate-key与method-champion sequences。
- Strategy／orchestration boundary明确`TokenPrediction`只是durable candidate value，prequential入口构造`PredictionRecord`，request-side入口返回ephemeral `PredictionDecision`，只有decision可携intent。
- Learning lifecycle明确Task 5只排request decision intent，prequential challenger不排use。
- Task 3 queue／predictor boundary、graph、bounds和anchor-use条款均改为represented methods、candidate-key evaluations及request-decision-only intent。
- Plan新增Task 3A preflight amendment，明确旧method-level budget／direct intent-return措辞不再有效。本轮对上一轮旧短语执行exact search，结果为exit 1；未发现残留active restatement。

Prefix reviewer `T3APCRR-01`也由plan Strategy line 128的同一修正关闭：高发现率summary不再把request-side结果写成`TokenPrediction`。

### token-task3a-prediction-contract-rereview-claude-03：ADDRESSED

Spec §11新增`Unnamed tuple decision carrier`独立行：记录`tuple[TokenPrediction, AnchorUseIntent | None]`虽然能传值，但没有named constructor拥有method／kind／identity／epoch跨字段validation，未来扩展只会堆position slots；因此采用immutable `PredictionDecision`。否决路线及理由已进入living behavior authority，不再只存在点时review report。

## 原Findings 01／03剩余open predicate

| 原finding | 第二轮状态 | 依据 |
|---|---|---|
| `token-task4a-prediction-dto-gap-review-claude-01` | **ADDRESSED** | Same-method variants不变成public methods；七种closed pair、candidate-key evaluation、represented-method champion／eligibility、selected key、V1 method＋variant PK／CHECK／graph与每candidate-key 128均闭合；cold-only和全部invalid champion shapes已有可判否transcription。 |
| `token-task4a-prediction-dto-gap-review-claude-03` | **ADDRESSED** | Spec、plan architecture、Tasks 3／3A／4A／5及A36一致选择ephemeral `PredictionDecision`；durable record／candidate／event codec排除intent，Task 5只排request decision intent，prequential challenger不冒充actual use。 |

## 必核合同逐项结果

1. **Cold-only／represented champion：PASS。** Cold-only exact object、absent methods无champion、represented missing、absent extra、wrong／missing key、selected eligible order均在Spec与plan tests逐项出现。
2. **双error sequences：PASS。** Candidate variants只读candidate-key evaluations；demotion／recovery／drift只读record冻结的point-in-time method champion。Persistent diagnostics不冒充完整method-champion history。
3. **Plan restatements与`T3APCRR-01`：PASS。** Continuous loop、strategy boundary、lifecycle、Task 3 queue／bounds／anchor-use均同步；旧措辞exact scan无命中。
4. **Unnamed tuple route：PASS。** Spec §11保存路线、结论及不采用理由。
5. **既有整改无回归：PASS。** `PredictionMethod`仍只有exact／prefix／profile／cold-start四项且顺序不变；V1仍只允许七种method／variant pair；diagnostics仍按candidate key独立128；nullable visual slot及29＋6／6-vs-8 oracle保持；`PredictionDecision`仍不进入durable codec。

## New findings

**无。** 本轮没有Blocker、Major、Minor或Nit finding。

## 启动判定

**Task 3A source可以启动。** 依据是本scope达到0 Blocker／0 Major且无剩余Minor；实施base和隔离worktree仍由coordinator按current status安排。这个批准只覆盖Task 3A candidate／visual／decision persistence合同，不批准尚未实现的source，也不替代Task 3A完成后的独立source review。**Task 4A仍blocked于Task 3A reviewed source。**

## 搜索面与证据边界

- 开始时复算Spec／plan完整SHA并与fixed authority逐字相等。
- 完整读取current Spec §6.0～§7.3、§8.2／§8.5、§9、§11、A8／A20／A23／A27／A32-P／A36／A39、§13及latest revision；读取plan preflight amendment、continuous loop、strategy boundary、lifecycle、Task 3、Task 3A、Tasks 4A～4C、Task 5及cross-task evidence table。
- 读取prefix scoped re-review绑定版本及`T3APCRR-01`原predicate，未从status摘要反推其含义。
- 对上一轮六类旧restatement拼写运行plan exact scan并记录exit 1；这只证明这些旧文本形态已移除，正面接口闭合另由完整子句阅读确认。
- 未运行source tests、未审source、未重审visual rationale或Task 3其它机制，因而本报告不声称实现已正确或tests已通过。

## 我最没把握的三个判断

1. **Recovery clause本身仍简称“prefix median APE”。** 置信度高：§7.3的cross-clause rule明确method demotion／recovery读取point-in-time champion sequence，plan也同样转录，因此不是残余fork；实现test仍应按method champion构造。
2. **Recommended data model summary没有逐字段重列`capability_visual_tokens`。** 置信度高：它没有给出相反representation，Task 3A／Spec／evidence table均明确专槽，所以省略不构成finding。
3. **APPROVED只表示contract可实施。** 这是范围限定，不是对未来Task 3A source或V1 migration mechanics的预测；任何source偏离仍由后续review裁断。

## 执行本契约时遇到的摩擦

Dotdev commit仍因isolated-agent git guard无法直接`git show`；本轮以coordinator给定`7684215`记录provenance，并对current Spec／plan完整SHA绑定的实际bytes逐子句复核。没有因此留下未核的scope predicate。

## 交付声明

- `delivery_complete`: true
- `completed_at`: 2026-09-07
- `finding_total`: 0
- `blocker`: 0
- `major`: 0
- `minor`: 0
- `nit`: 0
- `previous_new_findings_addressed`: 3
- `previous_new_findings_open`: 0
- `original_remaining_findings_addressed`: 2
- `original_remaining_findings_open`: 0
- `prefix_finding_addressed`: 1
- `verdict`: APPROVED

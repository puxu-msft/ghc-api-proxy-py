# Effort translation Spec 独立评审报告

- status：NEEDS_FIX
- attempt_id：effort-translation-spec-gpt-opus-a1
- review_started_at：2026-09-03T09:19:57+00:00
- review_scope：`spec.md`、`acceptance.md`、`implementation.md` 的 current working tree
- checklist_sha256：`0d25e6f5d1fd31770826aeccad4f698e29d35067def518d11ab134d9d2258d6e`
- spec_sha256：`c993a7a2f75c458105ce014ab9d08260e1989e477378979e411a61d69d04790a`
- acceptance_sha256：`d89ffd12509e4844df4f289b0ef35a73f9a313930353681068d574bc239e7d93`
- implementation_sha256：`165b75296faff527757202c5b04a9080bf18db7d7575434ced320cd8a0d7065e`

## 范围与方法

本报告只评审上述内容身份对应的当前工作树文档，不把历史 commit 或旧评审结论当作 current。评审按协调者清单逐条核验 C1～C12，并对文档引用的官方与本地源做可复核核对；在交付哨兵出现前，本文件只表示进行中状态。

## 已核对的外部与本地依据

- Anthropic 官方《Effort》，`https://platform.claude.com/docs/en/build-with-claude/effort`，2026-09-03 本轮读取：顶层 `output_config.effort` 字符串档位为 `low／medium／high／xhigh／max`，省略等价于 `high`；逐消息 effort 需要 `mid-conversation-output-config-2026-07-01`，由空 content 的 `role=system` 消息携带并从下一 `user` turn 起生效，且仅若干列明模型支持。
- Anthropic 官方 Messages API reference，`https://platform.claude.com/docs/en/api/messages/create`，2026-09-03 本轮读取：`thinking` union 为 `disabled`、`adaptive`、`enabled`；`auto` 不在 wire schema，`enabled` 要求 `budget_tokens>=1024`。官方《Extended thinking》同时说明 manual `enabled＋budget_tokens` 仅在 4.6 上 deprecated、在 4.7+ 被拒、在 4.5 及更早支持 thinking 的模型上仍是合法模式。
- OpenAI SDK 3.3.1 本地生成类型：`openai/types/shared/reasoning_effort.py` 将 `ReasoningEffort` 定义为 nullable `none／minimal／low／medium／high／xhigh／max`；`openai/types/shared_params/reasoning.py` 明示不是每个 reasoning model 都支持每个值。
- Claude Code 2.1.241 extracted source：`app.pretty.js:98537-98543` 将 settings `ultracode=true` 解析为 `xhigh`；`app.pretty.js:99105-99107` 的档位集合为五档并保留 `ultracode→xhigh` alias；`app.pretty.js:41764` 把 ultracode 描述为 `xhigh effort plus standing dynamic-workflow orchestration`；`app.pretty.js:428490-429022` 的 request builder 最终把实际 effort 写入 `output_config.effort`。
- 当前代码只用于判断规格可实现性而非反向定义合同：`src/app/pipeline/driver.py:81-129,262-290` 显示 send／count 共用 `shape_request`，且 path policy 当前会在 translator 之前清空 translated-path headers；`src/app/pipeline/request_headers.py:46-47` 的 translated whitelist 为空；因此新 reader 必须按 Spec 要求在该清空点之前认领 beta fact并让两个入口共用。


## C1～C12 逐条结论

- C1：PASS。2026-09-03 用户裁决的八个要点均在 `spec.md:14-15,212-216,273-285,612-614,626-628` 同向出现，没有用现实现限制改写裁决。
- C2：FAIL，见 EFFORT-M01。五个 effort 字符串档位与缺省 `high` 正确，但 thinking 合法形状、manual budget 的 model-specific 状态和逐消息功能的 model capability 被写宽。
- C3：PASS。`spec.md:231-239,275` 与 OpenAI SDK 3.3.1 的 nullable 七值 `ReasoningEffort` 及 `Reasoning` 的 model-specific 注释一致。
- C4：PASS。`spec.md:273-281` 的 `ThinkingEffortIntent | None` 分开了无 intent、启用状态、有效档位及四种 effort source，且明确排除 `budget_tokens`；这些状态足以表达清单所列来源差异。
- C5：FAIL，见 EFFORT-M02、EFFORT-M03。正向 enabled 集合没有排除 `none`，反向 capability 对齐也未形成全域算法与终态。
- C6：PASS。`spec.md:285` 明确两条同格式 direct leg 原样转发，`acceptance.md:92` 也把直连不变作为通过条件。
- C7：PASS，限定为规格可实现性判断。当前 send／count 共用 `shape_request`，source header 在 `driver.py:105` 清空前可读；`spec.md:278,284` 明令 reader 必须在该点前认领并让两入口共用，因此存在可实现接缝，但本结论不冒充代码已接线。
- C8：PASS。`spec.md:215,238,283` 同时规定同格式重建完整 sibling、跨格式只记录未携带子字段且不重复记 effort loss；`acceptance.md:89-92` 把两向 residual 与精确 loss 纳入正样本和通过判据。
- C9：FAIL，见 EFFORT-M04。静态 expected 与证据层边界写对了，但正样本分母大于缺陷注入控制覆盖面。
- C10：PASS。REQ-05B 仍只约束 response-level reasoning item／signature carrier；本轮 request-level effort 只在 REQ-05A，未改写双格式 carrier oracle。
- C11：FAIL，见 EFFORT-M05、EFFORT-M06。Effort 表与正文大体同向，但 current Spec、Acceptance 和 Implementation 仍保留互相冲突的 current／冻结 restatement。
- C12：PASS，按本轮 effort 切片的窄范围判断。`implementation.md:18` 只陈述 Spec／Acceptance 已改、生产代码未改、文档待复核，并明确旧 reasoning canary 不证明本轮 effort；其余 stale current identity 另按 C11 的 EFFORT-M06 处理，不把它混成 canary 外推。

## Blocker 与 major

本轮没有 blocker。以下 6 条均为 major；minor 与 nit 均为 0，因此没有被省略的低级别正文。

### EFFORT-M01
- severity：major
- primary_location：`spec.md:212-214,277-279`
- related_locations：`acceptance.md:88-92`；Anthropic 官方《Messages API reference》《Effort》《Extended thinking》，本轮 2026-09-03 读取
- 失败场景与证据：`thinking.type=auto`、`enabled` 无必需 `budget_tokens` 以及不支持 per-message effort 的 source model 都会被 Spec 当合法输入，而官方 schema 无 `auto`、manual `enabled` 要求 `budget_tokens>=1024`，且逐消息功能只列明 Fable／Mythos 5.1 与 Opus 5；官方还只把 manual budget 在 4.6 标成 deprecated，4.5 及更早仍依赖它。
- 建议：按 source model capability 写出合法 thinking／per-message 形状及稳定拒绝；继续遵守用户裁决——合法 budget 只作为无法跨格式携带的字段记录，不得重新参与 effort 档位选择。

### EFFORT-M02
- severity：major
- primary_location：`spec.md:280`
- related_locations：`spec.md:213,273-281`；`acceptance.md:88-92`
- 失败场景与证据：Anthropic enabled＋`low` 面向只发布 `none` 的 Responses capability 时，“取不强于请求档位的最强已发布档”唯一会选 `none`，把 enabled 静默改成 disabled；这直接违反 `enabled` 与 effort 分槽以及 disabled 优先的用户裁决。
- 建议：正向 enabled 对齐必须从候选集合排除 `none`；目标只剩 `none` 时定义稳定 reject 或明确 not-carried 终态，并为该单点反例加同入口控制。

### EFFORT-M03
- severity：major
- primary_location：`spec.md:281`
- related_locations：`spec.md:235-239,280`；`acceptance.md:89-92`
- 失败场景与证据：Responses `xhigh` 面向只发布 `low／medium`、空集合或仅不可排序名字的 Anthropic target 时，正文只说“再按 target model catalog 对齐”，没有引用正向算法，也没有规定 downward、floor、unknown 各自发送值、loss 与拒绝／继续终态；不同实现可分别选 `medium`、`low`、省略或拒绝而都自称对齐。
- 建议：把反向 exact／downward／floor／missing／empty／unrankable 的总函数及 loss 写进 Spec，并在 REQ-05A 为这些终态补静态 expected 与单缺陷控制。

### EFFORT-M04
- severity：major
- primary_location：`acceptance.md:86-92`
- related_locations：`spec.md:273-285`
- 失败场景与证据：正确样本要求 catalog exact／downward／floor／missing、尾部控制、Responses effort 缺席／null、siblings 重建、send／count parity 与 direct-leg bypass，但缺陷注入清单没有逐类触发这些断言；例如删掉 reverse sibling merge 或让 count 忽略 beta fact，现有强制变异仍可全部按文档完成。
- 建议：以关键语义类别而非篇幅删减为分母，为上述每类补同入口单侧变异，并要求先证明目标正样本绿、变异只因目标 wire／loss／调用次数断言变红。

### EFFORT-M05
- severity：major
- primary_location：`spec.md:626`
- related_locations：`spec.md:8-9,371-373`；`acceptance.md:322-347`
- 失败场景与证据：Spec 的“已冻结决策”仍写首 block 前零 headers，而 current 条款要求第一次 upstream 200 即提交 headers 并允许首块前 ping；Acceptance 的 current `CAL-04-GRAMMAR-v1` 仍禁止同一转移，虽然 `acceptance.md:339-341` 已承认被推翻。实现者跟随冻结摘要或 current grammar 会违反现行用户裁决。
- 建议：立即同步 Spec restatement 与 Acceptance oracle／fixtures 版本，不把已知错误留待独立切片；历史判据留在 point-in-time report，不继续作为 current authority。

### EFFORT-M06
- severity：major
- primary_location：`implementation.md:6`
- related_locations：`implementation.md:18,230-241,250-257,313`；本轮内容身份 `spec@c993a7a…`、`acceptance@d89ffd12…`
- 失败场景与证据：同一 living document 一面在 2026-09-03 活动行说新 Spec／Acceptance 待复核，另一面多次把旧 `FINALIZED@4c9beed…` 与 `FINALIZED_ACCEPTANCE_ORACLE@f99492a…` 称为 current；接棒者可能据后者跳过本轮复核或按旧 oracle 实施。
- 建议：把所有 mutable current restatement 同步到本轮身份与状态，或收敛为指向单一 current authority 的引用；旧 hash 只保留带日期／阶段的历史陈述。

## 整体判定

结论为 `needs-fix`。当前内容身份下没有权限、文件或工具阻塞使评审不完整，但 6 条 major 中 EFFORT-M01～M04 直接影响 request-level effort 的合法输入、状态闭包与验收分辨力，EFFORT-M05～M06 使三份 current 文档仍可给出相反执行依据；修复并重新独立复核前不宜把本轮 Spec／Acceptance 称为可定稿。

## 我最没把握的三个判断

1. EFFORT-M03 的强度最低：作者可能希望“按 target model catalog 对齐”隐式复用上一条正向算法；但该短语没有规范引用，Acceptance 也没有反向 capability controls，所以当前文本不足以让两个独立实现收敛。此判断足以要求补清，但不证明预期算法一定要与正向逐字相同。
2. EFFORT-M01 中 source-model capability gate 的产品边界次不确定：用户可裁定代理提供超出官方某模型的兼容扩展；当前材料没有这种独立裁决，而 C2 明确要求不超出官方合同，所以我按缺陷处理。若协调者能提供相反用户裁决，应只撤销这一子项，不撤销 `auto`／manual enabled schema 与 blanket deprecation 的其余证据。
3. C7 的 PASS 依赖“可实现接缝”而非现有接线：我确认两个入口共享 `shape_request` 且清空前有 header，但没有把某个尚不存在的 `ThinkingEffortIntent` carrier 当作已实现。实现若把 reader 留在当前 payload-only translator 之后，C7 会立即转为失败。

## 执行本契约时遇到的摩擦

- 用户要求首先加载 `my-agents:as-reviewer`，但本 harness 的 Skill registry 返回 `Unknown skill`；我没有派生 agent，改用本契约、项目规则与 `my-skills:qualifying-a-claim-and-its-coverage` 完成同一只读评审职责。
- Agent worktree isolation 阻止 `Write／Edit` 直接写主工作树唯一存在的 `.dev`；我在确认报告不存在后，用精确绝对路径与 Python `open("x")` 创建，后续只以 append／唯一字符串替换修改该报告。
- 为读取锁定 OpenAI SDK 类型，我误用 `uv --directory ... run`，它在隔离 worktree 自动创建了未跟踪／ignored 的 `.venv`；没有改动被评审对象或主工作树，但这超出“只修改报告”的字面边界。我没有在只读评审中自行删除它，协调者关闭本隔离 worktree时需一并处置。
- CodeGraph 对本隔离 worktree报告没有 `.codegraph/` 索引；我按项目规则退回 `rg` 与逐文件 `Read`。这只增加检索摩擦，不降低上述结论的证据层。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-03T09:25:42+00:00
- finding_total: 6
- blocker_count: 0
- major_count: 6
- minor_count: 0
- nit_count: 0

# Effort translation final whole-branch review

> 本文件由coordinator从final reviewer `af77bda4`完整末轮转录；reviewer因运行时规则禁止新建报告文件而返回正文。以下正文保持原结论与证据边界。

## Scope 与 evidence boundary

- 审查根目录：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/effort-translation`。
- 固定范围：Base `b67634d929b22f3cdcc83cf5607cd37c4eb35c2c`，Head `505d62fd2622c4ecb35e701fad33e1ca12300fb6`。
- 固定 package：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/effort-translation/.superpowers/sdd/plan-effort-translation-5cd3d7fd3f3b/review-b67634d..505d62f.diff`，共24个文件、3036行新增、545行删除。
- 通过 `/home/xp/src/ghc-api-proxy-py/.git/refs/heads/worktree-effort-translation`确认目标分支指向精确Head。由于本subagent自身处在另一隔离worktree，运行时guard拒绝对目标worktree执行`git -C`，所以没有独立取得目标worktree的`git status`；本轮结论绑定固定review package与上述精确ref，不声称目标工作树当前干净。
- 用户要求首先加载的`my-agents:as-reviewer`在当前skill registry中不存在，调用返回`Unknown skill`。本轮随后按用户给出的C1～C12、D1～D5和`my-skills:qualifying-a-claim-and-its-coverage`完成独立评审，没有派生任何subagent。
- 复用controller在精确Head上取得的证据：Ruff all checks passed；Pyright 0 errors／warnings／informations；pytest 2175 passed／2 skipped；coverage 91.17%。本轮没有重复全量运行，这些结果只证明已收集测试在该Head通过，不证明缺少判别场景的组合行为。
- 本轮对cassette做了只读结构探针：共有3个authenticated interactions，路径依次为token、models、responses；Responses capture的`response.created`、`response.in_progress`、`response.completed`三阶段均含`reasoning.effort="high"`。该证据仅适用于当前PONG＋`gpt-5.5`＋explicit high录制，不外推其他模型或effort。
- 精确legacy-symbol scan在`src`与`tests`中对`ReasoningIntent`、`BUDGET_LADDER`、`BUDGET_FLOOR`、`ADAPTIVE_EFFORT`等返回`rg` exit 1，即这些拼写无命中。固定diff内也没有Workflow实现。
- 本轮为只读评审，没有修改源码、测试、Spec、Git index、Git refs或cassette。

## 总体结论

该分支的主体设计与大多数静态映射正确，但还不能集成。发现2个major：逐消息effort在首块提交前的流式replay中丢失source beta header，以及Spec对同pattern配置覆盖语义与已实现、已要求的deep-merge合同相反。另有1个真实diagnostic defect、3个具有明确邻近假绿的测试缺口，以及1个docstring polish。

所有问题范围局部，可由一次fix wave处理，不需要重构translation architecture，也不需要新建mutation framework。

## C1～C12 合同裁决

### C1 — PASS

`src/app/pipeline/translation_driver/anthropic_messages.py:67-172`把thinking enablement与effort分开读取：省略thinking为enabled，省略effort为`high`，显式`output_config.effort`决定档位，budget只被验证和作为residual／loss保留，disabled只改变enabled状态。`tests/unit/pipeline/translation_driver/test_translation_driver.py:295-413,661-703`覆盖不同budget同wire、默认high、thinking只决定enablement；`tests/int/test_pipeline_app.py:3792-3806,3878-3910`覆盖公开入口默认high与disabled优先。

### C2 — FAIL

初次翻译上的candidate识别、system／empty content／effort-only校验、beta token解析、同值也更新provenance、future-only不生效并从target input移除，代码均正确，见`src/app/pipeline/translation_driver/anthropic_messages.py:175-275`。单元与公开入口错误边界见`tests/unit/pipeline/translation_driver/test_translation_driver.py:789-876`和`tests/int/test_pipeline_app.py:3932-4041`。

但合法逐消息控制在流式首块提交前replay时会失败：第一次`handle()`清空`context.client_headers`，replay只恢复body并再次调用`handle()`，第二次读取到空source headers并报`beta-required`。详见finding `F-MAJ-1`。此外，同值provenance和future-only original payload retention缺少直接状态oracle，详见D2／`F-MIN-3`。

### C3 — PASS

`src/app/pipeline/translation_driver/reasoning.py:55-141`稳定实现exact、downward、floor、missing、empty和unrankable；`src/app/pipeline/translation_driver/openai_responses.py:1008-1062`排除enabled候选中的`none`，拒绝known-only-none，并要求disabled target明确发布`none`。已发送effort始终属于resolved catalog且enabled不发送`none`。纯函数测试见`tests/unit/pipeline/translation_driver/test_reasoning.py:19-85`，公开入口终态见`tests/int/test_pipeline_app.py:3809-3928`。

### C4 — PASS

Wire与fail-closed合同通过。`src/app/pipeline/translation_driver/openai_responses.py:101-129`实现`none`、`minimal`与其余五档reader；`src/app/pipeline/translation_driver/anthropic_messages.py:504-608`先按profile渲染thinking，再按Anthropic-compatible catalog对齐effort。Always-on、manual budget、mode fallback、`budget < max_tokens`、missing profile及disabled effort上限均fail closed。测试依据为`tests/unit/pipeline/translation_driver/test_translation_driver.py:469-620`和`tests/int/test_pipeline_app.py:4241-4426`。

相关的loss detail仍有真实错误，但不改变本条要求的wire或终态，因此单列为D3／`F-MIN-1`。Minimal二阶段组合缺完整oracle，见D4／`F-MIN-4`。

### C5 — PASS

两侧reader均只接受协议列明值，literal`ultracode`经translated path稳定返回`effort-invalid`，见`src/app/pipeline/translation_driver/anthropic_messages.py:151-169`和`src/app/pipeline/translation_driver/openai_responses.py:115-122`。`xhigh`作为普通档位进入`ANTHROPIC_EFFORTS`／`RESPONSES_EFFORTS`，逐消息公开入口证明可正常发送。固定diff对Workflow零命中，没有代理侧orchestration新增。

Direct path故意原样保留literal`ultracode`，这属于C7的bypass合同，不是C5 translated-path拒绝的反例。

### C6 — PASS，但存在C12文档漂移

运行时行为满足断言。`src/app/config/bundled-config.yaml:57-78`逐行转录六条profile；`src/app/pipeline/routing.py:377-421`进行startup compile、resolved model`fullmatch`和最后命中胜出；`src/app/config/loading.py:37-53`执行递归deep merge；`src/app/config/schema.py:232-259`提供严格schema。正负regex域、last-match用户override及同pattern部分override分别由`tests/unit/config/test_config_loading.py:380-503`覆盖。

不过Spec声称同pattern整体替换，与上述deep merge相反，详见`F-MAJ-2`。

### C7 — PASS

`src/app/pipeline/driver.py:192-205,311-321`只在`route.translation_required`为真时调用translator。Direct Anthropic与Direct Responses分别由`tests/int/test_pipeline_app.py:4045-4062,4446-4459`证明原始不合法扩展仍按原字节／对象到达原协议上游，且direct Responses record的facts为空。Translated-path compatibility reader不会进入direct path。

### C8 — FAIL

初次send与count都在`shape_request()`前保存headers并传入同一helper，代码见`src/app/pipeline/driver.py:143-168,299-318`，对应测试见`tests/int/test_pipeline_app.py:354-443`。成功与`TranslationRefused` facts出口也共用`src/app/pipeline/driver.py:143-163`。

但保存值只活在单次函数调用栈，不能跨流式replay。`src/app/server/routes/inference.py:395-421`再次调用同一send入口时，`context.client_headers`已被第一次`shape_request()`清空。该状态使C8对同一request生命周期不成立，见`F-MAJ-1`。

### C9 — PASS，测试鉴别力有缺口

Reader正确从被认领对象中剥离owned effort并保留siblings，见`src/app/pipeline/translation_driver/anthropic_messages.py:133-172`和`src/app/pipeline/translation_driver/openai_responses.py:101-129`。`src/app/pipeline/translation_driver/semantic.py:181-192`同格式复制nested residual，跨格式逐字段、排序后记录loss。两侧writer先merge residual再写owned effort，见`src/app/pipeline/translation_driver/openai_responses.py:955-956,1056-1059`和`src/app/pipeline/translation_driver/anthropic_messages.py:637-640,665-669`。

当前实现顺序正确，但Responses same-format测试未放入冲突的stale residual effort，反转顺序后仍会绿，见D1／`F-MIN-2`。

### C10 — PASS

`Conversion.facts`独立于losses，`lossless`只读取losses，见`src/app/pipeline/translation_driver/semantic.py:58-123`。Profile成功与拒绝先后产生selected／rejected，拒绝把当前facts复制成tuple snapshot，见`src/app/pipeline/translation_driver/anthropic_messages.py:477-557`。

RequestContext→Trace→RequestLine→JSONL链路位于`src/app/pipeline/driver.py:135-163`、`src/app/observability/request_trace.py:135-144,193-217,225-266`和`src/app/observability/request_log.py:103-159`。Console formatter不读取facts，loss metric只迭代`line.losses`。公开入口success、override、missing、always-on拒绝、count transport和direct empty facts测试位于`tests/int/test_pipeline_app.py:4108-4349,4446-4459`。

### C11 — PASS

`tests/int/recorded/record_cassette.py:57-112`用同一`httpx2.AsyncClient(transport=RecordingTransport())`构建token manager、catalog provider及responses transport；zero interactions在destination write前抛错，`main()`返回非零。对应回归见`tests/int/test_recorded_upstream.py:294-433`。

`tests/int/recorded/cassettes.py:182-197,316-342,345-388`以排序后的完整request body计算digest并在replay精确比较，因此当前replay通过会绑定实际发送的explicit`reasoning.effort=high`。只读cassette探针确认三个response阶段均为high。Field-name递归scrub和response-header allowlist位于`tests/int/recorded/cassettes.py:25-62,80-163`，当前cassette未发现既定credential／identifier字段或allowlist外response headers。

结论只覆盖当前录制场景，不证明其他模型、effort或未来新增identifier field。

### C12 — FAIL

Schema、bundled config与大部分测试同向，legacy effort resolver已从`src`与`tests`消失，Task 1～5主体入口均已接线。但以下状态阻止“无漂移、无新回归”的全称断言成立：

1. 流式replay丢失逐消息effort beta source header，形成真实生命周期回归，见`F-MAJ-1`。
2. Spec同pattern replacement与C6要求、loader、plan及测试的deep merge相反，见`F-MAJ-2`。
3. D1、D2、D4分别留下可具体构造的邻近假绿。
4. D3的durable loss detail描述了错误的catalog集合。

## D1～D5 deferred重新裁决

### D1 — 测试缺口，minor

裁决成立。`tests/unit/pipeline/translation_driver/test_translation_driver.py:250-267`只构造`{"summary":"auto"}`residual。若把writer-owned effort写在residual merge之前，结果仍是`{"effort":"high","summary":"auto"}`，测试不会变红；它因此不能证明测试名声称的merge order。

最小修复是在同一test的nested residual加入`effort="low"`，保持owned intent为`high`，断言完整reasoning仍为`{"effort":"high","summary":"auto"}`。

### D2 — 测试缺口，minor

裁决成立。实现本身正确：`src/app/pipeline/translation_driver/anthropic_messages.py:267-274`在pending控制实际遇到user时无条件把source设为`ANTHROPIC_PER_MESSAGE`，不依赖值是否变化；`src/app/server/inbound.py:54-67`把working payload与original payload分开。

现有公开入口测试只用`medium→xhigh`，没有`high→high`的provenance assertion；future-only测试只断言outbound input与active effort，没有读取`context.original_payload`或History。最小修复为一个reader级同值控制测试，加一个公开入口或subscriber spy断言future-only控制仍存在于original payload／History。

### D3 — 真实defect，minor

裁决成立。`align_anthropic_effort()`先过滤非Anthropic候选，却把过滤后的tuple传给使用通用“this model”措辞的`align_effort()`。因此loss detail把“没有Anthropic-compatible候选”误报为“整个model没有reasoning efforts”，并在混合集合的floor路径忽略被过滤档。Wire与终态正确，错误位于durable diagnosis。

最小修复是让alignment reason明确描述“Anthropic-compatible published candidates”，并为交集为空及混合候选floor各加一个完整detail oracle。

### D4 — 测试缺口，minor

裁决成立。当前`minimal→low`test只使用包含low的catalog，generic alignment tests又不经过minimal first-step，因而没有任何test覆盖两个loss同时存在且有序的组合。

最小修复为两个静态oracle：`minimal＋medium-only`断言wire effort为medium及两条ordered approximation losses；`minimal＋catalog absent`断言省略output_config，并依次记录minimal→low approximation和low not-carried。无需新建测试框架。

### D5 — 仅polish，nit

裁决成立。`src/app/pipeline/translation_driver/semantic.py:69-75`的`TranslationRefused`docstring只说明code／field_path，未说明facts是拒绝时的immutable snapshot；`:103-107`的`Conversion`docstring只描述loss，未说明non-loss facts及其不影响lossless。代码行为没有错误。

最小修复只更新这两段docstring。

## Findings

### Blocker

无。

### Major

#### F-MAJ-1 — 流式replay丢失逐消息effort所需的source beta header

- 位置：`src/app/pipeline/driver.py:109-111,166-168`；`src/app/server/routes/inference.py:395-421`；`src/app/pipeline/translation_driver/anthropic_messages.py:238-243`。
- 具体输入／状态：translated`/v1/messages` streaming request带合法`mid-conversation-output-config-2026-07-01`header及effort-only system控制；第一次Responses stream在首个完整block提交前撕裂，delivery进入transparent replay。
- 错误结果：第一次`handle()`在局部变量中保存header后，`shape_request()`把`context.client_headers`清为空。Replay只恢复`context.payload`并再次调用`handle()`；第二次局部快照因此是空mapping，合法控制项被判为缺beta并抛出`TranslationRefused(code="beta-required")`。第二个upstream attempt不会发出，原本符合transparent replay条件的请求转成失败。
- 为什么属于本分支：本分支新增逐消息effort对source header的语义依赖，也新增了“单次调用栈内、shape之前”的header快照，却没有沿既有`_reopen()`生命周期保存该事实。普通无控制请求和首attempt测试均看不见该接缝。
- 最小修法：在`RequestContext`或一个明确的typed extras slot中保存第一次进入pipeline时的source header snapshot，后续send／count／replay都读取该immutable snapshot，同时继续让`context.client_headers`服从upstream path policy。增加一个真实stream delivery integration test：首attempt在首块前撕裂，second attempt成功；请求含合法逐消息控制；断言upstream调用为2、第二attempt仍使用正确effort、控制message未进入input且客户端最终成功。

#### F-MAJ-2 — Spec把同pattern覆盖写成整体替换，但实现和C6合同执行deep merge

- 位置：`.dev/docs/anthropic-responses-bridge/spec.md:281`；对照`src/app/config/loading.py:37-53`、`tests/unit/config/test_config_loading.py:484-503`及`.dev/docs/anthropic-responses-bridge/plan-effort-translation.md:180-203`。
- 具体输入／状态：用户config只给已有bundled pattern的`manual_budget_tokens: 4096`，不重复写`modes`、`can_disable`或`disabled_max_effort`。
- 错误结果：当前loader递归合并并保留三个未点名字段，测试明确固定该行为；Spec却写“用户以同一pattern重写时直接替换该profile”。按该句读取，用户mapping应整体替换并因缺少required fields失败，或至少不得继承bundled字段。规范权威与实际用户行为给出相反答案。
- 为什么属于本分支：thinking profile配置、该覆盖测试及其公共合同全部由本分支新增。C6还明确要求“用户deep-merge覆盖”，因此不能通过修改代码去迁就当前Spec句子。
- 最小修法：先在Spec revision record登记本次纠正，再把`:281`改成同pattern按配置通用递归deep merge、未点名字段保留；Acceptance REQ-05A补同pattern部分override这一正样本。实现与现有测试无需改变。

### Minor

#### F-MIN-1 — Anthropic-compatible effort过滤后的loss detail误述整个model catalog

- 位置：`src/app/pipeline/translation_driver/reasoning.py:79-91,94-141`；持久化调用位于`src/app/pipeline/translation_driver/anthropic_messages.py:592-607`。
- 具体输入／状态：Responses desired`high`，target catalog为`("none","minimal","future-level")`；或desired`low`，catalog为`("minimal","medium")`。
- 错误结果：第一例正确省略Anthropic output_config，却记录“this model advertises no reasoning efforts”，尽管model明确发布三个档位；第二例正确发送medium，却记录requested effort比“anything this model offers”都弱，忽略model发布的minimal。真正为空／参与排序的是Anthropic-compatible候选集合。
- 为什么属于本分支：本分支新增`align_anthropic_effort()`和反向durable loss detail。
- 最小修法：让reason带明确candidate domain，例如“no Anthropic-compatible reasoning efforts”；floor／downward措辞同样限定为Anthropic-compatible candidates。增加交集为空和混合集合的完整detail测试。

#### F-MIN-2 — Responses same-format merge-order测试无法判否stale residual覆盖owned effort

- 位置：`tests/unit/pipeline/translation_driver/test_translation_driver.py:250-267`。
- 具体输入／状态：owned intent effort为high，nested residual应构造`{"reasoning":{"effort":"low","summary":"auto"}}`。
- 错误结果：当前测试没有残留effort；若实现将residual merge移到writer-owned effort之后，错误wire会变成low，但当前test仍绿。也就是说当前绿不能证明其测试名声称的precedence。
- 为什么属于本分支：nested residual与owned effort merge order是本分支新增的C9合同。
- 最小修法：在现有test中加入stale low并继续断言完整reasoning为high＋summary。

#### F-MIN-3 — Same-value per-message provenance与future-only original retention缺直接oracle

- 位置：`tests/int/test_pipeline_app.py:3932-3996`；相关实现位于`src/app/pipeline/translation_driver/anthropic_messages.py:247-275`。
- 具体输入／状态：顶层high，实际生效的逐消息控制也为high；另一请求在最后一个user之后带合法xhigh控制。
- 错误结果：若实现错误地只在value变化时把source切成`ANTHROPIC_PER_MESSAGE`，现有不同值test仍绿；若future-only控制从working与original／History一起被原地删除，当前test仍只看outbound body并保持绿色。
- 为什么属于本分支：provenance和future-only original retention是本分支新增的C2合同。
- 最小修法：reader级断言同值后`effort_source is ANTHROPIC_PER_MESSAGE`；公开入口或subscriber spy断言future-only控制从Responses input缺席但仍存在于`context.original_payload`／History。

#### F-MIN-4 — Minimal二阶段mapping缺medium-only和catalog-absent的ordered双loss oracle

- 位置：`src/app/pipeline/translation_driver/anthropic_messages.py:578-608`；现有测试位于`tests/unit/pipeline/translation_driver/test_translation_driver.py:569-610`。
- 具体输入／状态：Responses effort minimal，target分别只发布medium和缺失catalog。
- 错误结果：一个实现可错误地只留下minimal→low第一条loss、跳过第二阶段loss，或者在minimal路径绕过catalog alignment；现有minimal test因catalog包含low仍绿，generic alignment tests又不经过minimal first-step。
- 为什么属于本分支：minimal first-step与Anthropic-compatible second alignment均由本分支新增。
- 最小修法：加入两条静态完整wire＋ordered losses oracle，不需要建立常驻mutation设施。

### Nit

#### F-NIT-1 — Conversion与TranslationRefused docstrings没有描述新增non-loss facts合同

- 位置：`src/app/pipeline/translation_driver/semantic.py:69-75,103-107`。
- 具体输入／状态：维护者只读公开类型docstring理解`Conversion`与`TranslationRefused`。
- 错误结果：docstring把`Conversion`描述成仅含loss，把拒绝描述成仅携带code／field_path，没有说明facts不影响lossless及exception携带拒绝时snapshot。运行行为正确，但接口说明不完整。
- 为什么属于本分支：`ConversionFact`、`facts`及refusal snapshot均由本分支新增。
- 最小修法：只补两段docstring。

## 考察但未采纳的建议

1. 未把Responses same-format的空`reasoning={}`或显式`effort:null`未按字节原样重建列为finding。理由是direct Responses路径由C7原样绕过translator，而Spec把effort absent与null都定义为enabled＋unspecified；C9明确要求的是nested siblings和owned precedence，不足以要求claimed null保留原拼写。
2. 未要求same-format translator重新插入已折叠的逐消息控制message。Direct Anthropic路径不会调用translator，translated path则按Spec必须把控制message从target prompt移除；未来控制的权威副本是`original_payload`／History。真正缺的是D2的状态oracle，而不是在target wire恢复控制message。
3. 未建议扩大cassette redaction字段或引入新的secret检测。当前命名资产、字段集合、header allowlist和用户给出的安全边界均通过；没有观察到新的具体credential／identifier leak，扩大属于security theater。
4. 未要求为其他model／effort重录live cassette，也未把当前high capture外推为其他档位。用户明确限定了唯一真实场景；其他组合应继续由local mock与静态oracle验证。
5. 未要求常驻mutation framework、coverage gate或形式化proof infrastructure。D1、D2、D4各自只需一个直接、可判否的测试。
6. 未建议重写通用alignment architecture。D3只需要让reason知道被比较的是Anthropic-compatible候选集合，全面重构会扩大修复面而不增加合同价值。

## 最没把握的三个判断

1. `F-MAJ-2`的严重级别把握最低。冲突本身是明确的，但有人可能把Spec的“直接替换该profile”解释为“deep merge完成后，以一个新runtime profile对象替换旧对象”。这种解释与普通配置语义及现有test名称不自然；考虑项目的“Spec不得落后实现”硬约束，我仍判major。若用户确认该句原本就是上述runtime-object含义，可降为措辞polish，但仍应改清楚。
2. D2中future-only original retention是否必须新增专门integration assertion把握中等。`build_context()`的deep copy和当前filter的非原地实现已提供结构性保证，且仓库另有generic original-payload测试；不过Acceptance明确把这一状态列为effort控制oracle，而当前effort测试完全不观察它，因此仍判minor test gap。
3. 未把same-format`reasoning.effort=null`拼写丢失列为finding把握中等。若“同格式重建完整对象”被用户解释成claimed字段也必须byte／presence exact，而不是语义重建，则需要给IR增加presence fact并补测试；当前C7 bypass与Spec对null／absent的同义定义支持不报该项。

## 建议的一次 fix wave

1. 先修source header生命周期并补首块前tear＋per-message beta replay integration test。
2. 同步修订Spec revision record、profile override条款及Acceptance的同pattern deep-merge正样本。
3. 修正Anthropic-compatible catalog的loss detail，并补empty／mixed候选测试。
4. 补D1、D2、D4的最小判别测试。
5. 更新D5两段docstring。
6. 运行相关targeted tests后，按项目规则在最终候选Head复用或重新执行Ruff、Pyright和全量pytest；无需新增proof framework或真实上游调用。

SPEC: FAIL
QUALITY: FAIL
COUNTS: blocker=0 major=2 minor=4 nit=1
Ready for one fix wave: YES

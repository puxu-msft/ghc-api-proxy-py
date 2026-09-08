# Direct buffered Chat Completions 计划验证评审

## 评审范围

被评对象是主树 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-buffered-chat-completions/plan.md` 当前内容。判据来自同主题 `design.md`／`decisions.md`、`direct-passthrough/spec.md`、`error-envelope/spec.md`、`tui/spec.md` 与当前源码和测试配置；重点核对各 Task 的测试步骤、Task 8、C1～C8、同源 oracle、真空断言、证据外推及测试范围冲突。未执行计划中的测试或真实 provider 调用，也未评审尚不存在的实现代码。

## 总体 verdict

**needs-fix，不可定稿。** 当前发现 0 blocker、6 major。

**Blocker 数：0。**

## Major findings

### F-01：Raw SSE 兼容 probe 的 actual 与 oracle 在重构后同源

- **位置：** `plan.md:255-272`；相关判据为 `direct-passthrough/spec.md:137-167`。
- **问题：** Step 1 先把 `read_events()` 改成消费 `RawSseFrameDecoder`，Step 2 再比较 decoder 输出与“existing `read_events()`”；两侧此时共享同一个新 decoder，分帧错误会一起变化，无法证明“as before”。
- **影响：** 该 probe 可在 CR/LF、mixed separator 或 EOF-tail 兼容性已回归时仍通过，属于只能证明自洽的同源 oracle；C1 及额外要求的同源-oracle检查不成立。
- **要求：** 在替换前冻结独立 literal 输入→`SseEvent`期望，或保留不调用新 decoder 的旧实现作一次对照；正确样本和单变量 separator／EOF 缺陷必须落在同一独立断言上。

### F-02：cap 算法与测试漏掉“同一 transport chunk 内先 `[DONE]`、后越界 tail”

- **位置：** `plan.md:255-268,366-382,625-645`；权威合同为 `direct-passthrough/spec.md:337-346,694-696`。
- **问题：** decoder 被要求先把整个 chunk 追加进私有 buffer，collector 才做 prospective cap；这没有说明如何在同一 chunk 内保留完整 `[DONE]` frame、拒绝其后的越界 tail，同时始终不持有超过 cap 的副本。
- **证据缺口：** Task 3 只列“`[DONE]` frame 自身越界”和“post-terminal tail 越界”，未要求把 terminal 与越界 tail 放在同一个输入 chunk；Task 6/8 的“matrix/cap behavior”也没有补这个构造。
- **影响／要求：** 当前计划可实现为整 chunk 预拒绝或短暂超 cap，二者都违约；需明确 bounded feed/逐 frame 接纳接口，并用该单 chunk 反例及 append-before-check 单变量控制判红。C1、C3 不成立。

### F-03：计划没有实现 Spec 要求的“同一 state／只解析一次”component 判别入口

- **位置：** `design.md:157-161`明确要求共享同一 `ChatAttemptState` 实例的component test以reader调用计数约束构造 seam；`plan.md:307-311,709-715`只列reader/state单测和production-entry投影断言。
- **问题：** “mode-adapted non-stream使用state snapshot、不重解析synthetic body”只是预期描述；现有条目没有可注入／计数的reader seam，也没有断言 aggregation、retry verdict、observation读取同一state实例。
- **影响：** 实现可在adapter或observation中再解析一次，所有最终payload／JSONL／console黑盒断言仍然通过；production black box虽未被文字冒充为内部证明，但所需component证明缺席。C7不成立。
- **要求：** 在component层用计数reader与对象身份／调用次数断言覆盖一次完整attempt，并注入“observation重解析synthetic body”这一单变量缺陷；production test只保留接线结论。

### F-04：event limiter 与外层 client deadline 的关键新路径没有可判别测试

- **位置：** `design.md:153-155`要求event rate-limit的mode／默认等待／单次server-error预算及client deadline不随retry重置；实现步骤在 `plan.md:488-506`，Task 8断言在 `plan.md:751-754`。
- **缺口一：** `test_rate_limiting.py:94-139`现有测试只覆盖HTTP status入口；计划虽新增`observe_event_rate_limit()`，却没有列event signal→LIMITED→默认interval→下一attempt acquire和预算只花一次的正例／缺陷控制。
- **缺口二：** 计划只测“每attempt新deadline”及post-`[DONE]`单attempt client deadline；现有`test_pipeline_app.py:7498-7544`只保护Anthropic block replay，不能判红Chat adaptation／runner把request deadline按candidate重启。
- **影响／要求：** wrong clock或event limiter只接半程仍可通过Task 8；在两条Chat retry入口各保留同一client deadline instant，并补event-limit全链路的调用数、ledger、mode、等待值和单变量控制。C1、C3不成立。

### F-05：Task 4～7的“验证步骤”没有可重放的精确命令

- **位置：** 全局约束`plan.md:23`要求每个Task使用其列出的精确Ruff／Pyright命令；Task 4～7却只写“targeted Ruff／Pyright”或“targeted … pytest”（`plan.md:508-510,574-576,651-653,717-719`）。
- **附带不一致：** 文件地图`plan.md:66-70`仍列出不存在的`tests/unit/model_provider/test_github_copilot.py`；当前GitHub provider harness实际位于`tests/unit/model_provider/test_model_provider.py:9-107`，Task 1命令已经改用后者。
- **影响：** 四个切片无法按计划复跑同一scope，执行者可任意缩窄“targeted”，而Task 8全量通过不能追溯证明这些切片声称的定向静态检查。C6不成立。
- **要求：** 逐Task列出完整可复制命令并删除虚构文件条目；保留`pyproject.toml:56-61`的默认`tests/tui`排除，当前计划未触发`src/app/observability/tui.py`专属suite且未出现`ruff format`，这两点本身无问题。

### F-06：证据分层漏写 cassette 层，却在自审中宣称四层边界已齐

- **位置：** `plan.md:21-22,270-272,570-572,713-715,779-793,822`；当前cassette harness为`tests/int/test_responses_observation_cassettes.py:17-38,81-108`。
- **问题：** 计划清楚限定fake、本地probe及未执行真实P6，但全文没有Chat cassette输入、执行项或“本次无Chat cassette证据”的声明；最终full regression会顺带运行现有Responses live-recording cassette，容易被总括为本特性的上游shape证据。
- **影响：** `plan.md:822`的“fake/cassette/live evidence boundaries are stated”是事实错误，Task 8的完成记录也没有槽位区分“历史Responses录制通过”与“direct Chat无录制／无本轮实况”。C4不成立。
- **要求：** 不必新增cassette；只需在Task 8证据记录中明确本特性各层的实际集合与上限：fake/local只证proxy逻辑，现有Responses cassette不证Chat，Chat cassette未使用，P6/live未执行且不得记pass。

## C1～C8逐条结论

| Claim | 结论 | 证据 |
|---|---|---|
| C1 | **不成立** | `plan.md:27,753`给出全称要求，但F-01～F-04提供反例：同源probe、未覆盖的同chunk cap边界、缺失的shared-state计数入口，以及未指定的event limiter／跨retry client-deadline控制。Task 5的`plan.md:566-572`也只有正例清单，没有逐项对应的单变量缺陷控制。 |
| C2 | **成立** | Byte fidelity明确使用独立literal且禁止产品encoder生成expected（`plan.md:309-311,647-649`）；multi-choice／TUI要求完整对象、显式缺席、排序、重复与winner exactly-once（`plan.md:709-715,751-753`），与`tui/spec.md:168-187,209-222`一致。 |
| C3 | **不成立** | calls／ledger／prepare／admission／mode／raw accounting／candidate promotion已有明确断言（`plan.md:504-506,568-576,641-649,751-753`），但F-02、F-04所列cap、event limiter和client deadline缺口仍允许wrong clock或半接线通过。 |
| C4 | **不成立** | fake／local边界及P6未执行状态写明（`plan.md:21-22,270-272,570-572,779-781,803-805`），但cassette层完全缺席而自审声称已声明（`plan.md:822`）；见F-06。 |
| C5 | **成立** | `plan.md:14-16,24`明确先实现后测试、不走TDD、不追coverage；仅复用固定80%命令，全文未引入manifest、hash gate或proof framework。 |
| C6 | **不成立** | Task 1～3及Task 8有可复制命令，但Task 4～7没有精确命令，且文件地图仍有不存在路径，见F-05。`pyproject.toml:56-61`正确让默认pytest排除`tests/tui`，计划未改`tui.py`且未要求`ruff format`。 |
| C7 | **不成立** | 计划没有把production black box文字冒充内部parse-count证明，但缺少`design.md:159-161`要求的shared-state component判别入口；见F-03。 |
| C8 | **成立（仅流程结构）** | `plan.md:783-809`包含一次full regression、独立merged-state review、finding核验与采纳／驳回理由、受影响证据复跑、状态更新和closeout；`plan.md:21-22,805,809`不要求P6／真实upstream／cutover／push。它不能替代F-01～F-06缺失的判据。 |

## 被否决建议及原因

1. **否决“本次必须运行P6或真实provider才能定稿”。** 用户已在`decisions.md:14-15`裁定不运行P6；正确处置是保留`deferred.md:4-10`的未实测状态并限制结论，不是扩大实施范围。
2. **否决“为所有控制建立mutation manifest／hash gate／proof framework”。** `plan.md:15,24`及项目规则要求直接测试与一次性受控缺陷检查；补齐具体反例即可，新建证明平面既超范围也不增加这些oracle的独立性。
3. **否决“把本次所有console／durable测试迁入`tests/tui`”。** `tests/tui/conftest.py:0-14`说明该suite专用于真实终端环境；本计划修改的是pure formatter／record projection，不改`src/app/observability/tui.py`，默认suite排除本身正确。
4. **否决“新增Chat cassette来修F-06”。** 当前合同允许本次不取真实上游证据；F-06要求的是诚实记录“未使用Chat cassette／未运行live”，而非把录制变成交付门槛。

## 搜索面与限制

- 已读规范与设计：`direct-buffered-chat-completions/design.md`、`decisions.md`、`README.md`、`status.md`、`deferred.md`，以及`direct-passthrough/spec.md` §5.4／§8／§9.3／§10、`error-envelope/spec.md`相关条款、`tui/spec.md`及`tui/design.md`。
- 已读当前实现／harness：`pyproject.toml`、`tests/tui/conftest.py`、`pipeline/{request,driver,retry,rate_limiting,response_observation}.py`、`direct_driver/base.py`、`delivery/{stream,sse_source}.py`、`server/routes/inference.py`、`observability/active_requests.py`，以及direct-driver、rate-limit、timeout、one-shot、pipeline-app与cassette observation测试。
- 只执行了`fd`／`rg`／文件读取等只读检查；未运行pytest／Ruff／Pyright，因为计划中的新文件尚不存在，且本任务不允许测试运行可能产生的cache等额外写入。因此本报告不声称任何当前或未来测试已通过。

## 结论

**不可定稿。** 需关闭上述6条major后再复评受影响的C1、C3、C4、C6、C7；C2、C5与C8的当前结论可沿用，除非修订触及对应条款。

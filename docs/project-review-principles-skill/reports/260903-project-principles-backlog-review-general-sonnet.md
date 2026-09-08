# Project principles backlog 原报告独立复审

- `report_id`：`project-principles-backlog-report-review-general-sonnet-260903`
- `attempt_id`：`260903-project-principles-review-general-sonnet-1`
- `reviewed_at_rev`：`e1b2baa99637349d2f552343c57769a311bfb179`
- `.dev` 快照：`dotdev` HEAD `019b36be32a961b402c320b7f0af1ede4b90cca3`；`.dev` 是独立仓库，本文对其引用是本次读取时的工作树快照，不由主仓 revision 标识。
- 评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md`
- 核查清单：`/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-report-review-checklist.md`
- 边界：这是对既有报告及其三条 finding 的复审，不是重新执行一次无边界项目审计；只读了清单要求的活文档、三条 finding 的当前生产源码，以及为判断排序与工作边界所必需的相邻合同。

## 整体判定

**VERDICT：needs-fix。** 原报告的 F-01、F-02、F-03 均成立，severity 也基本合适；F-01 的根因与修法方向不是“加日志”，而是让 native 路径把 typed side facts 写入共享摘要，且这一方向已由 `direct-passthrough/spec.md` §10 授权。报告仍有两处会改变交付判断的 major：一是 Anthropic native selector 的完成边界漏了现行 signature reshape；二是 D-5 的第一顺位只能作为条件性偏好，现有报告没有把 primary product path 上已裁未做的 hosted web search D6 与 `empty_result` 放进同一比较面，却仍宣称证据足以完成排序。

结论强度：三条原 finding 的成立性足以据以行动；D-5 暂列第一只是中等强度的排序倾向，不能作为已闭合的绝对排序。没有发现合同性 blocker。

## C1-C9 逐项回应

### C1：F-01 的 cassette parity 与 producer／consumer 数据流

**结论：finding 成立，但 cassette 的经验覆盖需收窄，见 `PPRR-260903-03`。** 当前 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:164-200` 在每个 item `done` 上只增加 `Terminal.blocks`，并用 item 判定 `_saw_client_action`；它没有调用 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/assembling.py:50-59` 的 `Terminal.record()`，也没有等价的 native item observation 写入口。`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:608-623` 无条件把 assembler 的 `Terminal` 交给 `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py:183-194` 的 `absorb()`，因此默认空 `thinking`／`tools` 会进入 operator-facing record。该数据流不回写 client wire，原报告对此边界表述正确。

我对两份 cassette 的 `/responses` SSE 逐帧解析：`anthropic_to_responses_stream.json` 有 12 帧，`history_responses_stream.json` 有 125 帧；两者都只有一个 `reasoning` item 与一个 `message` item，各自有一对 `added`／`done`，没有 tool item。由此，两份录制直接支持 `reasoning` parity 反例；“native 路径的 tool 名也不会写入摘要”由当前控制流确定，但不是这两份 cassette 的经验对照结果。

### C2：F-01 的修法与授权

**结论：pass。** `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:661-667` 明确要求 wire 以原生事件为 source of truth，同时旁路记录 item 计数、需客户端行动的 tool 名称／类型、reasoning、terminal、usage、failure／截断／replay 来源；无法分类必须是 unknown，不得伪装成 absent。原报告建议 dialect／item 产出 typed side facts，再由 `Terminal` 或替代摘要类型拥有唯一分类入口，符合该合同。它没有建议从摘要重建 wire，也没有把增加日志当根因修复。§2.3 的 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:57-60` 又明确把 §10 定性为 Spec 推导，可由评审共识修正，无需新增用户裁决。

否决的替代解释：把 F-01 修成一条 warning。理由是 warning 只能宣布当前观察器缺字段，不能让 completion record 得到 reasoning／tool 的 typed facts，也不能消除两种 producer 各自判断同一事实的结构分叉。

### C3：F-02 count-tokens

**结论：pass。** `/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:217-260` 的成功路径仍在 `:238` 直接写 `trace.usage = {"input_tokens": tokens}`；全 `src/` 当前检索只得到两个 `trace.absorb(...)` 与这一处 reply-field 直接赋值。`/home/xp/src/ghc-api-proxy-py/.claude/skills/project-review-principles/SKILL.md:29-35,55-68` 明确把 upstream-backed count 纳入该原则，并把这个赋值形状列为已知 C2 召回点，因此它不是 reviewer 擅自扩张定义域。

原报告把即时危害写成“今天未复现，未来换算或键扩展的漂移风险”，把 severity 定为 minor，权重合适。建议建立具名、同源的 count usage observation，而不是把 count 假装成完整 `Terminal`，也与当前领域边界一致。

否决的替代解释：因为 count 没有完整 reply，所以直接赋值必然正当。理由是该原则并未要求 count 伪装成完整 reply；它要求 upstream-backed token fact 进入同一 observation 构造约束。若设计最终裁定 count usage 与 reply usage 不同源，应该收窄原则定义域，而不是把当前旁路当作已经无违背。

### C4：F-03 三处承诺面

**结论：pass。** 三处当前仍在：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/blocks.py:23-24` 由 `DeliveryError` 断言 upstream failure “is retryable”；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/subscribers/server_tools.py:262-270` 的 INFO 文案断言 upstream “would have rejected” 被 flatten 的历史；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/subscribers/blank_text.py:111-116` 的 DEBUG 文案断言 upstream accepts 被置空的 assistant turn。三句都能影响调用方或运维对 retry／rewrite 的理解，同时结局分别由 retry policy 或外部 upstream 拥有，不归这三个 surface 自己拥有。

`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:30-32` 只把具名 status 列为可重试候选；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:114-158` 与 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/stream.py:455-478` 又证明真正 replay 还受 delivery position 与 budget 约束。因此 `DeliveryError` docstring 的全称确实越权。另两处的同源测量／理由已经保存在紧邻注释中，撤回端点断言不会丢掉事实。

否决的替代解释：日志既然同时说了本模块的实际动作，就有权保留完整因果句。理由是本模块只拥有“flattened”或“emptying”动作，不拥有未来 upstream 对该 body 的必然结局；把外部结局留在附近 rationale 注释足够，不必让 operator-facing line 承担会独立腐坏的保证。

### C5：D-5 第一顺位

**结论：仅条件性成立，见 `PPRR-260903-02`。** 原报告尾部 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:140-149` 已正确撤回“Anthropic direct 是主产品路径”，并承认没有 route 流量占比。当前权威 `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:50` 明定 primary product path 是 Anthropic Messages input served through an OpenAI Responses upstream。D-5 仍有强理由暂列第一：用户已裁形态；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery_policy.py:57-72,122-132` 证实 Anthropic direct selector 尚未启用 native；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/deferred.md:67-89` 说明不闭合续写顺序与 carrier 类型就不能安全启用该 selector。

但“暂列第一”与“已经证明没有更高项”不是同一声称。现有证据缺少 route frequency，而且报告没有比较 hosted web search D6／`empty_result`，故不能把表格顺位读成绝对结论。F-01 是当前可达但只错 operator-facing record；retry §16 是 `/responses` client + Anthropic upstream 的 served 语义错误；hosted web search D6 位于 primary product crossing，但 feature 默认关闭；D-5 是关键 Claude direct route 上的已裁 root-cause work。这些事实支持一个暂定偏好，不支持无条件全序。

### C6：D-7、D-6 与 signature reshape 的依赖边界

**结论：D-7 与 D-6 已在尾部更正，signature reshape 仍遗漏，见 `PPRR-260903-01`。** 原报告尾部 `:146-149` 已把 D-7 放入 D-5 自身切片，并把 D-6 改为 `D-5 infrastructure → D-6 mapping → enable selector / declare externally complete`，这两项修正成立。

遗漏的是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:101-114` 已裁定的 Anthropic signature reshape preservation：native 接线不得改变当前默认 `signature_delta`。当前 `/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:375` 仍默认启用该行为，`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery_policy.py:106-112` 仍由 `AnthropicFramer` 执行它。selector 启用 native 前必须给 passthrough 路径接上等价、具名的 reshape；D-4 尚待用户裁的是长期“默认开、可关”还是“常驻、不可关”，不是这次接线是否保留现行默认。

### C7：遗漏的现行 backlog

**结论：有遗漏，并进入 `PPRR-260903-02`。** `/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/status.md:55-61` 的 D6 已由用户裁决，当前 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py:667-673` 仍把 `web_search_call` 降成一行 text；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/openai_responses.py:344-355` 也明确说明 streaming 与 non-streaming 都还缺原生块对。它不是仅存在于旧报告的历史项。

同一 status 的 `:83-97` 还登记了 2026-08-24 用户裁决的 `empty_result`。当前 `/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:26,227` 的 policy 仍只有 `error`／`drop_fields`，`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/openai_responses.py:285-309` 仍是 `if policy == "error"` 后把其余值吞进 drop 行为。`empty_result` 未进入当前可配置行为，通常不足以单独翻转 D-5 第一顺位；D6 则属于 primary product crossing，虽然默认关闭，仍必须进入同一排序比较。

否决的替代解释：hosted web search 默认关闭，所以可从现行候选排序中排除。理由是它是可显式启用的 served path，启用后当前就给客户端错误 carrier，而且 D6 已裁；默认关闭可降低优先权，不能把它变成不存在。对 `empty_result` 的判断更弱：它尚不可选，所以当前失败后果较 D6 小，但用户已裁的实现项仍属于 backlog 全集。

### C8：五条原则的扫描范围与“未发现”

**结论：pass，证据只支持限定后的“本轮未发现”。** 原报告逐条写了当前命中、人工判定、退役判断，并披露原则 1 的路径腐坏、原则 3 的自指噪音、原则 4 的 `--since`／`async def` 漏检。原则 4 还明确说没有逐一 mutation，结论不等于所有测试都有完备分辨力；这符合 `/home/xp/src/ghc-api-proxy-py/.claude/skills/project-review-principles/SKILL.md:13-17` 的“命令给候选，不给结论”。原报告的“未发现”没有被我读成全集证明。

保留限定：报告没有保存五组原始命令输出，只给了命中数与人工摘要，因此只能审其叙述与若干抽查锚，不能复算全部人工分诊。该限制不推翻任何一条现有 finding，也不改变当前排序，所以不升格为独立 major。

### C9：尾部交付声明

**结论：pass。** 原报告有两份声明，但 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:140-142` 明确规定后附更正与文末最新声明优先，`:176-191` 又说明旧 `contract_blocker_count: 1` 是 checklist 尚未读到时的点时状态，并以 `supersedes_completed_at` 关联旧声明。最新声明的 `finding_total=3`、`major_count=1`、`minor_count=2`、`open_count=3` 与正文三条 finding 一致，contract blocker／open 均为 0。文件头的旧 `status` 仍会给只读开头的读者造成摩擦，但尾部 supersession 足以解除事实冲突，不改变 finding、顺序或工作边界。

## Findings

### PPRR-260903-01

- `finding_id`：`PPRR-260903-01`
- `severity`：`major`
- `status`：`open`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:101-114`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/deferred.md:48-64,67-119`；`/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:375`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery_policy.py:57-72,96-112,122-132`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:146-149`
- 证据：Spec §2.7 已规定接线不得改变现行 reshape 默认值；当前 `signature_delta` 默认开着并由 `AnthropicFramer` 执行。原报告补核只把 D-6 与 D-7 纳入 selector 前置，候选排除段却把 D-4 整体归为“需用户裁决”，没有拆开“现行默认必须保留”与“长期默认形态待裁”这两个不同事实。
- 失败后果：若按原报告给出的完成边界实施，D-5 continuation 与 D-6 mapping 都闭合后仍可能直接启用 native selector，导致 Anthropic direct 腿失去当前默认的 signature reshape，违反 Spec §2.7；该回归发生在 selector 首次启用时，而不是之后可独立清理的事项。
- 建议：把对外完成顺序改成 `D-5 continuation carrier + D-7 count → D-6 failure mapping → preserve current Anthropic signature reshape on passthrough → enable Anthropic native selector / declare D-5 externally complete`。各项可按语义独立提交，但后三项都不得晚于 selector。D-4 对长期常驻性与可配置性的用户裁决继续保留，不把它误当作保留当前默认所需的新授权。
- 否决的替代解释：D-4 需用户裁决，所以本轮不能把 signature 工作列进前置。否决理由是用户待裁的是长期配置合同，Spec 已经裁定这次接线保留当前默认；把整条 D-4 都挡在裁决后面会漏掉现有授权。

### PPRR-260903-02

- `finding_id`：`PPRR-260903-02`
- `severity`：`major`
- `status`：`open`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:91-111,140-178`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:50`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/hosted-web-search/status.md:55-61,83-97`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py:667-673`；`/home/xp/src/ghc-api-proxy-py/src/app/config/schema.py:26,227`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/translation_driver/openai_responses.py:285-309,344-355`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/deferred.md:317-331`
- 证据：原报告正确撤回了 D-5 位于 primary product path 的论据，也承认缺少 route traffic，但排序表与最终结论仍说证据足以保持第一。与此同时，排序表没有 hosted web search D6／`empty_result`；D6 是已裁、当前实现仍错 carrier 的 primary-product-path 工作，`empty_result` 是已裁但 schema 与分支仍未实现的 backlog。没有把它们纳入比较，不能支撑“没有发现比 D-5 更应优先”的全集声称。
- 失败后果：coordinator 若按该表锁定全序，会把一个未被比较的 current primary-path contract 排除在外；即使最终仍选择 D-5，决策依据也缺了会改变权重的一项。F-01 与 retry §16 的相对描述基本充分，缺口主要在 hosted web search。
- 建议：把整体判定降为“D-5 暂定第一，等待当前运营优先级或 route traffic 证据”；在排序表加入 D6 与 `empty_result`，分别标出“primary crossing、feature 默认关闭但启用即错 carrier”与“尚不可配置的已裁功能”。如 coordinator 有近期要启用 hosted web search 的运营事实，重新比较 D6 与 D-5；没有该事实时可以继续暂列 D-5 第一，但不得称为无条件闭合。
- 否决的替代解释：D6 默认关闭且 `empty_result` 尚不可选，所以两者都不参与“当前”排序。否决理由是 D6 的显式启用路径当前可达且行为不合合同；`empty_result` 可以因不可达而排低，却不能从 backlog 全集消失。

### PPRR-260903-03

- `finding_id`：`PPRR-260903-03`
- `severity`：`minor`
- `status`：`open`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/tests/int/cassettes/anthropic_to_responses_stream.json` 与 `/home/xp/src/ghc-api-proxy-py/tests/int/cassettes/history_responses_stream.json`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/passthrough.py:164-200`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/assembling.py:50-59`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:25-35,95-97`
- 证据：两份 cassette 都只含 `reasoning` 与 `message` item，不含 function／custom／client-action tool item。它们直接复现 `thinking=['enc']` 对 `thinking=[]`，却不能经验性对照 tool name；后者由 `PassthroughAssembler` 对所有 done item 都不调用 `Terminal.record()` 的源码事实推出。
- 建议：把“Spec §10 与两份 cassette 已闭合”收窄为“两份 cassette 闭合 reasoning 反例；源码控制流同时证明 tool classification 入口缺失”。不要把 tool parity 说成已被这两份录制观察。实施时可用一条拥有 tool item 的 recorded sample 或一条针对本项目 side-fact 合同的 focused test 验证修法，但无需为本次报告复审建立新证明系统。
- 否决的替代解释：源码全称已经足够，所以 cassette 内容无需区分。否决理由是原报告特意用“真实录制”提高经验权重；该权重只能覆盖录制实际携带的 item 类型，不能替源码推断背书未出现的 tool 场景。

## 被否决的替代解释汇总

1. “F-01 只是日志缺字段。”否决：缺的是 producer 到共享摘要的 typed side facts；日志只能消费事实，不能拥有分类。
2. “D-4 全部待裁，所以 signature reshape 不属于 D-5 完成边界。”否决：长期默认合同待裁，但本次保留现行默认已由 Spec §2.7 裁定。
3. “D6 默认关闭，所以不属于当前排序。”否决：显式启用路径 served 且当前错 carrier；默认关闭只降低权重。
4. “两份 cassette 已覆盖 F-01 的全部 item 事实。”否决：它们只包含 reasoning／message，没有 tool item；tools 缺失是源码推断。
5. “count 没有完整 reply，所以不受共同 observation 约束。”否决：项目原则已明确把 upstream-backed count 纳入同一记录事实；修法可以是具名 count observation，不必伪装成 `Terminal`。

## 我最没把握的三个判断

1. **D-5 与 hosted web search D6 谁应暂列第一。** D-5 有更新、更明确的用户裁决与 selector 依赖闭包；D6 位于 primary product crossing，但默认关闭。缺少近期启用计划与 route traffic 时，我的判断只能支持“D-5 暂列第一”，不能支持绝对顺位。置信度：中。
2. **signature reshape 应与 D-5 同一个 commit 还是独立 commit。** 它必须在 selector 之前闭合，这个依赖边界很强；按项目语义提交纪律，它可以独立提交，是否与 D-5 carrier 合并没有足够依据。置信度：依赖顺序高，commit 分组低。
3. **F-03 的实际运营代价。** 三处均满足原则的两条件，成立性较强；其中两处分别是 INFO／DEBUG，当前没有误操作或客户端错误证据，所以维持 minor。置信度：成立性高，实际影响低到中。

## 执行本契约时遇到的摩擦

1. 用户指定的 `my-agents:as-reviewer` 不在当前 skill registry；调用返回 `Unknown skill: my-agents:as-reviewer`。我记录失败后按 coordinator checklist 继续，没有以缺 skill 缩小核查范围。
2. CodeGraph 工具可调用，但 `/home/xp/src/ghc-api-proxy-py` 当前没有 `.codegraph/` 索引；按项目规则改用 `Read` 与 `rg`，没有自行建索引。
3. 隔离机制拒绝向主树 `REPORT_FILE` 写入，错误明确要求只编辑 worktree；因此按用户预授权 fallback 写到 `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-general-sonnet.md`。没有创建或覆盖主树目标文件。
4. 隔离 guard 两次拒绝内联执行 cassette 解析脚本，即使输入都在 worktree。为保留逐帧证据，我创建 test-only 临时脚本 `/tmp/review_cassette_items_260903.py`，随后只读运行；它不在项目或 `.dev` 仓库内。没有修改原报告、源码、测试、Spec、deferred 或 status。
5. 作为 leaf executor，我没有派生其他 reviewer。本轮产物本身的后续处置与是否要求再审由 coordinator 决定。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-03T09:01:02+00:00`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 2`
- `minor_count: 1`
- `open_count: 3`
- `closed_count: 0`

## 窄复评：原报告追加更正与 coordinator 处置账

本轮只复核 `PPRR-260903-01`～`PPRR-260903-03`、原报告 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:194-240` 的追加更正，以及 coordinator 处置账 `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-disposition.md:21-35`。主仓仍为 `e1b2baa99637349d2f552343c57769a311bfb179`，`.dev` HEAD 仍为 `019b36be32a961b402c320b7f0af1ede4b90cca3`；没有相关源码或相邻合同变化这一升级信号，因此沿用上一轮已确证的源码与 Spec 事实，不重跑五条原则全量扫描。

### PPRR-260903-01：closed

原报告更正 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:198-203` 已把 current `signature_delta` preservation 纳入 selector／D-5 对外完成前置，并准确拆开两个不同事实：本次接线保留当前默认已经由 Spec §2.7 授权；D-4 待用户裁的只是长期“默认开、可关”与“常驻、不可关”分叉。它还把 D-5／D-7、D-6、signature reshape 写成 selector 前必须闭合的前置集合，而没有制造这些独立 semantic commit 之间无证据的全序。

处置账 `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-disposition.md:25` 对该更正的 `adopted` 裁定成立。被否决的反向解释是“只改报告而未改 Spec／plan，所以 finding 仍开”：本 finding 审的是原报告遗漏的工作边界，Spec 本来就正确且用户明确禁止本 reviewer 修改 Spec／plan；更正把边界恢复进报告即闭合本 finding，产品实现仍未完成是另一组 `PPR-260903-*` open finding，不应混同。

### PPRR-260903-02：closed

原报告更正 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:204-213` 已将 hosted web search D6 与 `empty_result` 补回候选全集，分别记录 D6 的 primary product crossing／默认关闭但显式启用即错 carrier，以及 `empty_result` 尚不可配置、当前射程较弱。它把 D-5 改成有明确条件的中等置信暂定首选，并写出会触发重新比较的运营事实：近期 hosted-search rollout／启用计划。原先“没有更高项”的无条件全集否定也被逐字收窄。

处置账 `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-disposition.md:26` 对该更正的 `adopted` 裁定成立。被否决的反向解释是“仍未取得 route traffic，所以 D-5 不能排第一”：修订不再声称绝对全序，而是在具名缺口下给出条件性偏好；缺 traffic 限制结论强度，却不禁止 coordinator 在当前没有已记录 rollout 信号的条件下作暂定排序。若后来出现该信号，报告已要求重比 D6 与 D-5，不会把旧顺位冒充永久结论。

### PPRR-260903-03：closed

原报告更正 `/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260903-project-principles-backlog-review-gpt-opus.md:215-219` 已明确分离证据层级：两份 cassette 只实证 reasoning parity；tool classification 缺口来自 `PassthroughAssembler` 不调用 `Terminal.record()` 且没有等价 observation 入口的源码控制流。它不再把未出现在录制中的 tool item 计入 cassette 权重，也没有为收窄措辞新建证明系统。

处置账 `/home/xp/.claude/jobs/f5849771/tmp/260903-project-principles-backlog-review-disposition.md:27` 对该更正的 `adopted` 裁定成立。被否决的反向解释是“没有新增 tool cassette，所以 finding 仍开”：本 finding 针对的是经验声称越过录制样本，而非要求生产缺口只能由 recorded sample 证明；把经验反例与源码全称各自限定到它们真实覆盖的层，已经修复报告缺陷。

## 窄复评整体判定

三条 review finding 均已关闭，coordinator 的三项处置站得住；没有新 blocker、major 或 minor。原报告现可交付。这里的 `closed=3` 只指 `PPRR-260903-01`～`PPRR-260903-03` 三条报告 finding；原报告自身的 `PPR-260903-01` major、`PPR-260903-02` minor、`PPR-260903-03` minor 仍因产品尚未修复而保持 open，原报告最新声明已如实区分 `adopted` 与实现闭合。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-03T09:05:53+00:00`
- `verdict: pass`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 2`
- `minor_count: 1`
- `open_count: 0`
- `closed_count: 3`
- `remaining_blocker_count: 0`
- `remaining_major_count: 0`
- `remaining_minor_count: 0`
- `supersedes_completed_at: 2026-09-03T09:01:02+00:00`

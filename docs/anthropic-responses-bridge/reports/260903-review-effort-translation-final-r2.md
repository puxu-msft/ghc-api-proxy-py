# Effort translation final scoped re-review R2

> 本文件由coordinator从原final reviewer `af77bda4b11267754`完整末轮转录；reviewer因运行时规则禁止新建报告文件而返回正文。以下保持原结论与证据边界。

## Scope 与 evidence boundary

- 本轮是唯一scoped R2，只复核原R1的7项finding、代码范围`505d62fd2622c4ecb35e701fad33e1ca12300fb6..ed6addd017f461c15abc494584e727f1badec633`、对应文档修订及修复直接触及的相邻合同，没有重新执行whole-branch review。
- 原R1：`reports/260903-review-effort-translation-final.md`。
- 固定fix package：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/effort-translation/.superpowers/sdd/plan-effort-translation-5cd3d7fd3f3b/review-505d62f..ed6addd.diff`，包含8个文件、266行新增、35行删除。
- `/home/xp/src/ghc-api-proxy-py/.git/refs/heads/worktree-effort-translation`当前精确指向`ed6addd017f461c15abc494584e727f1badec633`。
- `/home/xp/src/ghc-api-proxy-py/.dev/.git/refs/heads/dotdev`当前精确指向文档checkpoint`958d8f9711fde583edaab09e487d250cf4e8cbf4`。
- 采用已有代码证据：agent source与squash净diff等价；effort unit 187 passed；完整pipeline integration 179 passed；focused 7 passed；changed-path Ruff通过；changed-path Pyright为0 errors／warnings／informations；旧header读取方式的受控变异使新增replay test精确以`beta-required`失败，恢复后同一test通过。
- 本轮没有重跑全量测试。下文的PASS只覆盖本次scoped R2；最终候选仍须在精确Head运行项目规定的full verification。
- 本轮只读，没有修改代码、文档或Git状态，也没有派生subagent。

## R1 findings逐项状态

### F-MAJ-1 — ADDRESSED

`src/app/pipeline/request.py:73-101`新增request-lifetime`source_headers`及一次初始化的`source_headers_for_translation()`。`None`与合法空mapping明确分离，直接构造的测试context只在首次读取时复制当时的`client_headers`。

`src/app/server/inbound.py:60-70`从`forwarded_client_headers()`的同一结果分别初始化attempt-facing`client_headers`和独立副本`source_headers`。`src/app/pipeline/driver.py:167-200,300-319`让send与count均在`shape_request()`前读取该request-lifetime snapshot；后续path policy仍只改写`client_headers`。

新增integration test位于`tests/int/test_pipeline_app.py`的`test_per_message_effort_survives_a_pre_block_translation_replay`：第一attempt在完整block前撕裂，第二attempt成功；两次wire均发送controlled high、input均只含user message、两个upstream request均不携带`anthropic-beta`，客户端只得到一个成功Anthropic lifecycle。受控旧行为变异在第二次`handle()`精确触发`beta-required`，证明test命中原finding而非仅命中普通replay。

相邻合同没有被破坏：初始化为空的snapshot不会从仍带header的`client_headers`重新填充；source header仍不会转发upstream；send与count使用同一读取路径；direct leg没有新增translator调用。

### F-MAJ-2 — ADDRESSED

`spec.md:17`新增修订记录，明确原“直接替换profile”是agent错误转录而非用户裁决，记录触发报告、纠正内容及runtime不变边界。

`spec.md:282`现已与loader及C6合同一致：同pattern按通用recursive deep merge逐子字段覆盖，未点名字段继承bundled profile，mapping以外的值整体替换。

`acceptance.md:90`同步加入同pattern部分override的正样本；`:95`加入把该路径错误改成whole-profile replacement时必须使未点名字段继承判据变红的反向控制。Spec、Acceptance、loader与既有partial-override test现已同向。

### F-MIN-1 — ADDRESSED

`src/app/pipeline/translation_driver/reasoning.py:80-157`保留公开`align_effort()`的原有generic措辞，并让`align_anthropic_effort()`通过共享私有helper显式传入`candidate_domain="Anthropic-compatible"`。

Missing catalog、空交集、downward与floor现在都描述实际参加选择的Anthropic-compatible candidates，不再把过滤后的集合冒充整个model catalog。新增oracles覆盖：

- Raw catalog为`("none","minimal","future-level")`时，明确报告没有Anthropic-compatible candidates。
- Raw catalog为`("minimal","medium")`且desired为low时，明确报告medium是最弱Anthropic-compatible candidate。
- Downward路径明确说明desired不在已发布的Anthropic-compatible candidates中。
- Generic Responses alignment继续使用旧措辞，未被反向污染。

### F-MIN-2 — ADDRESSED

`tests/unit/pipeline/translation_driver/test_translation_driver.py`中的`test_responses_same_format_nested_extensions_are_merged_before_owned_effort`现构造stale residual`reasoning.effort="low"`，同时把writer-owned effort设为high，并断言完整结果仍为high加summary。

如果写入顺序反转，stale low会覆盖owned high，当前test会直接判红；原R1指出的假绿已消除。

### F-MIN-3 — ADDRESSED

同文件新增`test_equal_per_message_effort_still_records_per_message_provenance`，以top-level high＋per-message high断言最终`effort_source is ANTHROPIC_PER_MESSAGE`，因此实现若错误地只在value变化时更新provenance会判红。

`tests/int/test_pipeline_app.py`中的future-only测试现通过真实inference`build_context`spy取得最终`RequestContext`，同时断言控制message不进入Responses input且完整`original_payload`与入站payload相等。该测试直接观察了原R1要求的状态，不再只观察outbound wire。

### F-MIN-4 — ADDRESSED

`tests/unit/pipeline/translation_driver/test_translation_driver.py`新增两个静态完整oracle：

- `minimal＋medium-only`得到adaptive thinking与`output_config.effort="medium"`，loss顺序严格为minimal→low后low→medium floor approximation。
- `minimal＋catalog absent`得到adaptive thinking且省略output_config，loss顺序严格为minimal→low后low not-carried。

这两项同时固定wire、loss code、detail及顺序，没有引入常驻mutation或proof framework。

### F-NIT-1 — ADDRESSED

`src/app/pipeline/translation_driver/semantic.py:70-108`现已说明：

- `TranslationRefused.facts`是拒绝点可用non-loss observations的immutable snapshot。
- `Conversion`同时拥有losses与non-loss facts。
- Facts不改变只由losses决定的`lossless`。

修订仅涉及接口说明，没有改变runtime行为。

## Docs sync verdict

**PASS。**

### Spec 与 Acceptance

- Spec revision record、正文与Acceptance正反控制已同步recursive deep-merge合同。
- 修订记录明确区分“纠正agent转录”与“改变用户裁决”，没有制造用户授权。
- Acceptance正样本固定部分override继承，反向控制固定whole-profile replacement这一邻近错误；没有借修复引入新的profile行为。

### Candidate config文档

`human-controlled-docs-candidates/effort-thinking-profiles-config-example.md`准确区分了以下边界：

- `:4,12`明确本文只描述translated Responses→Anthropic Messages writer，direct Anthropic→Anthropic与Responses→Responses不读该表改写请求。
- `:16-18`准确说明resolved-model`fullmatch`、最后命中、同pattern recursive deep merge及新增pattern必须提供完整required fields。
- `:33-54`给出新增窄pattern的完整profile，并区分manual-only与adaptive fallback。
- `:56-68`给出bundled同pattern部分override，只覆盖`disabled_max_effort`并继承其余字段。
- `:70-82`给出完整的第六条bundled pattern partial override，并提醒宽pattern会同时影响其覆盖的所有resolved models。
- `:84-88`准确区分profile facts与conversion loss，并没有把候选文档冒充权威。

候选索引`human-controlled-docs-candidates/README.md:41`对该文档的摘要与正文一致，链接有效。

### Implementation 与 Disposition

`implementation.md:18`忠实记录了Tasks 1～5、R1 counts、唯一fix wave、squash candidate、旧Head全量证据与当前Head只完成scoped验证的边界；仍明确写着scoped R2和full suite pending，没有提前宣称最终完成。

`review-disposition-effort-translation-code.md`逐项记录了R1全部7项的采纳、代码／文档修法、证据层级及当前`awaiting-final-scoped-re-review`状态。它没有把R2或full verification写成已完成，符合当前checkpoint。

`reports/260903-effort-translation-final-fix.md`保留implementer当时“Spec／Acceptance由coordinator处理、未跑full suite”的point-in-time边界，并在末尾另记controller squash事实，没有回写或伪造历史报告。

## Fix相邻合同与 new breakage

- Request header forwarding仍由`context.client_headers`承担；translation-only snapshot是独立副本。新增replay test和initialized-empty test共同证明header既不会在replay丢失，也不会重新进入upstream headers。
- Direct legs的translation gate未改；source snapshot的存在不触发reader／writer。
- Generic`align_effort()`仍由`candidate_domain=None`走原措辞，Anthropic-specific domain只作用于过滤后的反向alignment。
- Same-format owned effort、per-message provenance、future-only retention及minimal二阶段改动均只增强测试判别力，没有改变production wire。
- Docstring修订不触及数据模型或lossless计算。
- 未观察到新的code、test或normative-doc contract回归。

NEW_BREAKAGE: none

## 六条未采纳路线裁决

1. **Same-format空`reasoning={}`或显式`effort:null`要求presence／bytes exact：维持`no_change_needed`。** Direct Responses leg原样绕过translator；translated IR按Spec把absent与null归一为enabled＋unspecified。R1处置理由成立。
2. **Same-format writer重新插入已折叠的per-message control message：维持`no_change_needed`。** Translated target prompt必须移除控制message，future-only控制由`original_payload`／History保存；新增retention oracle正好固定了该边界。
3. **扩大cassette redaction字段或新增泛化secret detector：维持`rejected`。** 本轮没有新的具体credential／identifier leak、protected asset或failure mode；扩大仍属于security theater。
4. **为其他model／effort继续录制live cassette：维持`not_adopted_in_scope`。** 当前真实证据仍只覆盖PONG＋`gpt-5.5`＋explicit high，所有文档继续明确不外推；本次fix不依赖新的真实上游事实。
5. **新建常驻mutation framework、coverage gate或proof infrastructure：维持`rejected`。** 各缺口已由局部、可判否test关闭；新增replay test另有一次旧行为控制，现有证据已经与finding匹配。
6. **为diagnostic修复重写通用alignment architecture：维持`rejected`。** 私有共享helper＋可选candidate domain修复了实际错误，同时保留generic Responses合同；全面重构没有额外收益。

六条处置理由均站得住，无需反驳或重开。

## 最没把握的判断

1. Candidate文档使用Anthropic target侧名称`max_tokens`描述manual profile渲染条件。我将其解释为writer即将构造的目标字段，因此不列finding；若未来摘取文本主要面向`/responses`调用者，改成“入站`max_output_tokens`，翻译后成为Anthropic`max_tokens`”会更不易误读，但这只是措辞polish，不影响当前合同或full verification。
2. Acceptance没有单独新增“逐消息beta＋首块前replay”的组合条目。我没有把它列为漂移，因为该行为由既有REQ-05A source-header合同与REL-01 replay合同组合推出，且产品已有直接回归和旧行为控制；要求Acceptance枚举每个跨域组合会无边界扩大oracle。
3. `source_headers`类型是`Mapping`而不是物理不可变容器。我没有列finding，因为`RequestContext`按项目合同本来就是可写记录，生产构造与lazy初始化都创建独立dict，当前没有其他writer，修复所需的不变量是“不被path policy重绑定”，不是防御任意内部代码主动篡改。

本轮没有load-bearing finding。Candidate可以进入精确Head上的full verification；无需再扩展scoped review。

SPEC: PASS
QUALITY: PASS
COUNTS: blocker=0 major=0 minor=0 nit=0
READY_FOR_FULL_VERIFICATION: YES

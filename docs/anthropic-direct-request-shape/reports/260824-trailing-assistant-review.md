---
report_id: anthropic-trailing-assistant-review-260824
attempt_id: main-review-1
status: in-review
reviewed_at_rev:
  main_head: 7e8a9488eb8467c32b3f004102dd7eca89cfc8a6
  dev_head: 764c1e54996d15f36d06570a9a99bd33de1a1635
reviewed_at: 2026-08-24
---

# Anthropic 尾随 assistant 增量实施评审

## 评审范围

本次只评以下未提交增量：`src/app/pipeline/subscribers/anthropic_trailing_assistant.py`、`src/app/pipeline/subscribers/__init__.py` 中本片的注册与顺序改动、`src/app/pipeline/translation_driver/semantic.py` 中新增的 `LossCode.SYNTHETIC_TURN_ADDED`、`tests/unit/pipeline/subscribers/test_anthropic_trailing_assistant.py`、`tests/unit/pipeline/subscribers/test_builtin_subscribers.py` 中本片的顺序表与 `original_payload` 变更、`.dev/docs/anthropic-direct-request-shape/spec.md` 的新增 §2.5 与 §6，以及 `.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md` 的新增两节。上一片提交 `7e8a948` 的 thinking／output_config 能力门不在本次范围。

明确排除共享主工作树中的并行未提交改动：`docs/.human-controlled/config.example.yaml`、`docs/.human-controlled/message-translation.md`、Docker 资产、实验目录，以及其他未由任务点名的文件。最高权威文档虽然作为判据读取，但不评其并行改动，也不修改。

## 判据来源与预先固定的承重要求

判据在打开被评对象前按任务指定顺序建立。第一层是 `docs/.human-controlled/README.md`、`request-pipeline.md`、`message-translation.md`、`message-format-reshape.md`、`api.md`、`ghc-api.md`、`module-org.md`、`test-org.md` 与 `config.example.yaml` 的相关段落；第二层是项目 `CLAUDE.md` 与 `.claude/rules/00-development-workflow.md`；第三层先读 `.dev` 提交 `764c1e5` 中修改前的 `anthropic-direct-request-shape/spec.md`，把本轮新增条款留到被评阶段；第四层是前轮 `reports/260824-implementation-review.md` 与 `review-disposition.md`。

预先固定的要求如下：所有目标格式为 Anthropic Messages 的出站请求在 translation 后接受同一 `attempt.prepare` 订阅链；订阅者顺序是正式扩展契约；直连路径只在确有上游不兼容时改写；真实上游行为须由实测记录而不是 mock 想象；observable behavior 必须先由 living Spec 完整拥有；generation 与 count 两腿都必须构造实际会发送的最终形状；测试应覆盖本片真实改变的失败机制且有分辨力。用户提供并要求沿用的 2026-08-24 实测事实是：尾随 assistant 的字符串与块数组形状均被真实上游以 prefill 400 拒绝；temperature／top_p／top_k 各种组合被接受；`repair_tool_pairs` 与 `drop_blank_text_blocks` 各有一条合法输入会被改写成 assistant 结尾。这些事实强到可用于本片判据，但只证明所述模型、路径与样本，不自动证明上游会如何解释合成文本。

## 总体判定

**Verdict：needs-fix。Blocker：0。发现：5 项，其中 major 2 项、minor 3 项。**

本片确实修到了两条已实测的生产失败路径：原始 Anthropic 请求以 user 结尾，`repair_tool_pairs` 或 `drop_blank_text_blocks` 删除最后一轮后，当前 subscriber 会在 generation 与 count 两腿追加合法的非空 user 轮；顺序约束也足以覆盖当前事件上的所有消息删除者。可是判别器把“原件的 `messages` 末尾不是 assistant”等同于“末尾 assistant 是本代理造成的”，这个等式在 translated-to-Anthropic 路径上不成立；它还把已实测可接受的 `assistant content: []` 误归入必须修复的 prefill。两处都会把客户端没有说过的 `Please continue.` 放进真实模型上下文，命中核心语义正确性，故在修复前不应进入下一阶段。

## Major findings

### ATRA-01：translated-to-Anthropic 路径没有同形 `messages` 原件，客户端自己的末尾 assistant 被误判成代理造成

- `finding_id`：`ATRA-01`
- `severity`：`major`
- `primary_location`：`src/app/pipeline/subscribers/anthropic_trailing_assistant.py:54-63`
- `related_locations`：`.dev/docs/anthropic-direct-request-shape/spec.md:4-6,229-239,252-258`；`src/app/server/inbound.py:54-65`；`src/app/pipeline/translation_driver/openai_responses.py:79-103,331-392`；`src/app/pipeline/translation_driver/anthropic_messages.py:229-258`；`tests/unit/pipeline/subscribers/test_anthropic_trailing_assistant.py:204-212`
- 具体失败场景：客户端向 `/responses` 发送 `input=[user message, assistant message]`，请求的 Claude 模型只发布 Anthropic Messages endpoint，因此路由把 Responses 翻译成 Anthropic Messages。翻译后的 `context.payload.messages` 以 assistant 结尾，但 `context.original_payload` 是 Responses body，角色在 `input` 中，根本没有 `messages` 键。`_last_role(context.original_payload)` 因而返回 `None`，第 58 行把它当作“不是客户端自己的 prefill”，第 63 行追加合成 user 轮。
- 实际结果：完整 `route_for_path('/responses') → build_context → handle → provider.send` 本地组成探针观察到上游 body 为 `user / assistant / user('Please continue.')`，并记录 `synthetic-turn-added`；`TRANSLATED_ORIGINAL_HAS_MESSAGES` 为 `False`。客户端明确提供的末尾 assistant 被静默改成一次新的 user 指令，这正是 §6.3 声称不得做的事。
- 判据：Spec 范围明确覆盖所有 target format 为 Anthropic Messages 的请求，§6.3 又规定客户端自己的 prefill 不修。`original_payload` 保存的是客户端原协议 body，不保证具有 Anthropic 的 `messages` 形状；在跨协议腿上用 Anthropic 专属读取器判断来源，无法成立。
- 证据强度：**强到可据以行动。** 生产 registry、真实 route 决策、两段 translator 与 subscriber 全部在同一组成探针中执行；结果不依赖 mock 对上游语义的猜测，mock 只记录本代理实际构造的 body。若把 Responses 末尾 assistant 另行裁成“允许代理主动续写”，结论会改变，但那是新的 observable contract，必须先改 Spec；现行 Spec 明确选择保留客户端意图。
- 建议：不要从 `original_payload.messages` 推断跨协议来源。优先在 translation 前用对应 source reader 得到“客户端末尾语义角色”并作为显式 provenance 随 context／semantic request 传到出站阶段；至少要为 Responses 的 `input` message、`function_call`、`reasoning` 等会翻成 assistant 的形状给出统一判据。新增一条真正的 Responses → Anthropic 组成测试；当前名为 `test_a_translated_route_is_none_of_this_module_s_business` 的测试只设置 Anthropic payload + Responses target，覆盖的是相反方向。

### ATRA-02：角色判据漏掉已实测可接受的 `assistant content: []`，对无需修复的请求注入可见文本

- `finding_id`：`ATRA-02`
- `severity`：`major`
- `primary_location`：`src/app/pipeline/subscribers/anthropic_trailing_assistant.py:33-42,54-70`
- `related_locations`：`.dev/docs/anthropic-direct-request-shape/spec.md:19,225-248`；`.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md:77-83`；`src/app/pipeline/subscribers/blank_text.py:90-125`；`exp/260820-empty-text-probe/FINDINGS.md:40-69`；`exp/260820-empty-text-probe/raw/F4-final-assistant-turn-with-empty-content-array.json`
- 具体失败场景：客户端发送 `user(text) / assistant(blank text) / user(blank text)`。`drop_blank_text_blocks` 把 assistant 的 blank text 修成 `content: []`，并删除最后一个全 blank 的 user 轮；新 subscriber 只看尾部角色与原始尾部 user，于是再追加 `Please continue.`。
- 实际结果：完整本地组成探针观察到出站 `user / assistant(content=[]) / user('Please continue.')` 及一条 `SYNTHETIC_TURN_ADDED`。但本仓 2026-08-20 的真实上游探针 F4 已对同一 `claude-sonnet-5`、非流式、末轮 assistant `content: []` 得到 200；F6 还证明中间位置也得 200。这里没有 400 失败面，追加 user 轮反而改变模型上下文、token 数与可能的回答。
- 判据：项目要求上游行为按实测记录，并明确反对为没有具体失败面的形状建守卫。当前 Spec 的“messages 不得以 assistant 结尾”把本轮两个非空 prefill 400 样本扩成了全称，却与已有 F4 第一手证据冲突；角色不是充分判据，至少还要区分空 `content`。
- 证据强度：**强到可据以行动。** 本地探针证明当前代码确实注入；F4 raw capture 是同模型、同 endpoint 的真实 200 正样本。它不证明别的模型或流式也接受空 assistant，但本片用来建 guard 的 400 证据同样只覆盖这个模型与非流式，不能选择性扩大一边、缩小另一边。
- 建议：立即修 living Spec、candidate、实现与测试的转录，明确非空 assistant prefill 与 `content: []` 的不同实测结果。当前证据下，最终 assistant 的 `content` 是空 list 时不应追加；若要对其他模型采取不同策略，先取得对应模型的失败证据或模型能力判据。新增“blank pass 清空 assistant 且删除尾 user”组成测试，断言最终保持空 assistant 且不记录 synthetic loss。

## Minor findings

### ATRA-03：核心判别器依赖 production deep copy，但现有测试把两份 copy 手工造好，浅拷贝回归仍全绿

- `finding_id`：`ATRA-03`
- `severity`：`minor`
- `primary_location`：`tests/unit/pipeline/subscribers/test_anthropic_trailing_assistant.py:92-104`
- `related_locations`：`src/app/server/inbound.py:54-65`；`tests/unit/server/test_server_inbound.py:83-89`；`src/app/pipeline/anthropic_request_hook.py:155-216`
- 具体失败场景：若 `build_context` 的 `working = deepcopy(dict(payload))` 被回归成 `working = dict(payload)`，`payload` 与 `original_payload` 会共享 nested `messages`。`repair_tool_pairs` 就地删除末尾 orphan user 时也同步改掉“原件”，trailing subscriber 随后看到两边都以 assistant 结尾，把代理造成的形状误当成客户端 prefill，最终把已知 400 body 发给上游。
- 变异结果：M-1 精确把 production `deepcopy` 改成浅 `dict`；runtime probe 显示 `nested_shared=True`，执行 `fix_anthropic_request` 后 `original_roles_after_fix=['user','assistant']`。然而 `test_server_inbound.py` 与本片新测试共 30 项全部通过。原因不是注入没生效，而是 server test 只测顶层新增键，本片 helper 又自行 `deepcopy` 两次，绕开 production builder。
- 当前代码结论：**实现当前正确。** generation 与 count 的实际 `build_context` 探针均显示 nested 对象不共享，repair 后 source body／`original_payload` 仍为 `user / assistant / user`，发出／计数 body 为 `user / assistant / user(synthetic)`。这条 finding 只针对测试分辨力，不指控当前 production bytes。
- 证据强度：**强到可据以行动。** 变异已由 `inspect.getsource` 与 runtime identity 双重证明，测试仍绿，反例明确。
- 建议：至少增加一条 nested-copy 回归：由 `build_context` 构造含 orphan `tool_result` 或 blank 尾轮的 context，走真实 repair 后断言 `original_payload` 未变且 subscriber 会追加。最好让 generation 与 count 两个 anchor case 各有一条经对应 route 的 `build_context` 入口，避免 helper 再次替 production 预先满足关键不变量。

### ATRA-04：新增 §6 后有三处旧编号没有同步，规范与候选把读者指到错误章节

- `finding_id`：`ATRA-04`
- `severity`：`minor`
- `primary_location`：`.dev/docs/anthropic-direct-request-shape/spec.md:161,203`
- `related_locations`：`.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md:136-146`
- 具体失败场景：读者从 §3.2 的“反应式作为增强留在 §7 延后项”或 §4.4 的“见 §7”跳转，会落到当前的“## 7. 不做什么”，而真正的待裁表已移到 §8。candidate 第 138 行也说编号来自 Spec §7，紧接的 A-1～A-6 实际属于 §8。
- 错误结果：living Spec 的 pending owner 无法沿引用找到对应 A 项；candidate 被摘取或裁决时会带着错误 provenance，尤其 §4.4 的 A-3 与反向降级 A-2 都会被误认为没有登记。
- 证据强度：**强到可据以行动。** 这是当前文档标题与引用的直接不一致，由本片插入新 §6 并整体顺延后产生。
- 建议：把 Spec 第 161、203 行和 candidate 第 138 行的 `§7` 改为 `§8`，并全文机械复扫本次顺延影响到的 `§6`／`§7` 引用；已经正确更新的引用不要再动。

### ATRA-05：Spec §2.5 带了实测边界，供用户摘取的候选转述却把边界丢了

- `finding_id`：`ATRA-05`
- `severity`：`minor`
- `primary_location`：`.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md:85-91`
- `related_locations`：`.dev/docs/anthropic-direct-request-shape/spec.md:114-139,288`
- 具体失败场景：用户按 candidate 的用途把“Claude 5 一族三个参数经 Copilot 都收 200，因此不用管”摘进最高权威文档。该段没有写 `claude-sonnet-5`、非流式、每格一次调用；脱离当前 Spec 后，它会读成对 Copilot 上所有 Claude 5 模型与流式形态的结论。
- 错误结果：单模型、单模式样本被提升为全族契约，未来若另一个模型或流式路径真的返回字段 400，维护者会被这条无条件“无需守卫”结论错误挡住。一个 200 不证明上游照做这一限定保留了，但“样本覆盖谁”这个更基础的限定丢失了。
- 对 Spec §2.5 的判断：**本身写得足够清楚。** 它在矩阵前写明模型与非流式，在结尾再次写明只测一个模型、每格一次，并明确 200 只证明接收、不证明采纳。该证据强到足以决定“当前不为已测路径建守卫”，不够支撑参数有效性或全模型兼容性；正文已经正确区分。
- 证据强度：**强到可据以行动。** 两份文本逐句对照即可成立，不需要猜测其他模型实际会不会失败。
- 建议：candidate 原地补齐 `claude-sonnet-5`、非流式、每格一次调用，并把“无需守卫”限定为当前已测路径／当前证据；写明若别的 resolved model 出现实测 400，则按模型能力重开，而不是让本段成为全局否决。

## 明确核查且未发现问题的方面

1. **`original_payload` 当前 production 接线正确。** `inference.py` 对 generation 与 count 都只调用一次 `build_context`；working copy 是 nested `deepcopy`，原件指向解析后的 body 且下游不改它。generation、count 两腿的本地组成探针均确认 nested identity 不同，`repair_tool_pairs` 未污染 source body 或 original。证据强度：强到可据以行动。
2. **当前顺序约束足够。** `repair_tool_pairs` 在 translation 前运行；它删消息后仍会经过 `attempt.prepare`。该事件上当前只有 `drop_blank_text_blocks` 会再删除整条消息；`server_tools` 只重写 content 且产出非空文本，thinking gate 不碰 messages，hosted gate 不增加／删除消息。`after=(BLANK_TEXT_BLOCKS_ID,)` 因而覆盖当前完整删除面，且用户已提供的 before 变异会打红 6 条。证据强度：代码调用面完整枚举＋既有变异正控，足以行动。
3. **边界形状不会让新 subscriber 崩溃。** `messages=[]`、`messages` 非 list、末尾非 dict 都由 `_last_role` 返回 `None` 并原样交上游；客户端原始 body 直接以 assistant `content: []` 结尾时，original tail 也是 assistant，当前实现不追加。后者的代理生成变体有 ATRA-02，其余三项行为符合“无法可靠理解就不静默改写”。
4. **追加的内容不会再次触发 blank-text guard。** blank pass 已先运行，且合成 block 的 text 非空；本事件后面没有另一个 request rewriter。重试时末尾已是 user，subscriber 返回，Loss 不重复。证据强度：控制流与幂等测试。
5. **既有 blank-block 测试补 `original_payload` 是正当修复，不是削弱。** 它让手工 `RequestContext` 与 production 的“两份不共享 body”契约一致，并继续逐字断言 blank block 被删后的完整 provider body；没有放宽 blank 判据或删除断言。若不补，测试会因另一个 subscriber 的 synthetic turn 失败，测到的不是它标题声称的机制。
6. **`LossCode.SYNTHETIC_TURN_ADDED` 与日志通道接线正确。** 同格式修复虽然不是 translator，但 body 已偏离客户端原话，沿现有 `conversion_losses` 到 request trace 是当前唯一会被读到的路径；generation 与 count 都保留该列表，第二次运行不重复记录。
7. **`Please continue.` 作为确需合成时的文本可保留，不值得另造词或加配置。** 非空 user 内容是绕开 prefill 400 的必要条件，任何可发送替代词都会进入模型上下文；`Please continue.` 只表达本次修复所需的“继续”，没有额外任务语义，并与第一方 `messagesApi.ts:198-223` 的出货选择一致。配置开关会把 protocol correctness 变成 operator 偏好，却没有一个具体失败面。真正要收紧的是 ATRA-01／02 的触发谓词，不是让每个部署发明不同暗语。该判断强到可用于当前实现；它不保证模型回答逐字不变，合成 prompt 本来就不可能提供这种保证。
8. **Spec §2.5 的反向结论本体合格。** 它没有把 200 写成“参数生效”，也没有隐藏单模型、非流式、每格一次的边界；只据此拒绝当前无失败面的守卫，符合项目“上游行为记录而非想象”的规则。candidate 的限定丢失另列 ATRA-05。
9. **target-format 门与 idempotent 分支有行为测试。** Responses target 会原样保留；已修复 user tail 会在第二次运行直接返回。M-2 进一步证明 synthetic role 的关键行为不是同源假绿。

## 否决掉的候选发现

1. **否决“`original_payload` 与 working payload 共享 nested messages，所以判别器现在就失效”。** 当前 `build_context` 明确 `deepcopy(dict(payload))`，本地 generation／count probe 也观察到 identity 分离；真正成立的是 ATRA-03 的回归测试缺口，而不是当前 production bug。
2. **否决“`after=(blank-text,)` 还必须显式列出 repair_tool_pairs”。** repair_tool_pairs 不在这个 event 上，且固定在 translation 前；event dependency 只能指同 event subscriber。当前 subscriber 无论如何都在它之后，伪造一个跨阶段 id 反而会让 freeze 因 unknown subscriber 失败。
3. **否决“合成文本应换得更中性或变成配置”。** 空白文本会被上游拒绝；`Please continue.` 已是对“继续生成”最窄的自然语言要求。没有观察到词本身造成的独立缺陷，已观察到的是触发范围过宽，见 ATRA-01／02。
4. **否决“给既有 blank-block 测试补 original 是为了让新功能过关而削弱 oracle”。** 新版仍精确断言 provider body，补的是 production prerequisite，不是豁免或更宽 expected。
5. **否决“空 messages／非 list／尾项非 dict 应由本 subscriber 合成或本地拒绝”。** 本片只拥有代理造成的 trailing assistant，无法理解的客户端 body 交给上游命名符合既定原则；没有证据要求在这里新建 validator。

## 变异验证记录

每轮先写只含该 mutation 的 frozen patch 到 `/tmp`，`git apply --check` 后应用；运行前用 imported `inspect.getsource` 或 runtime object identity 证明测试实际加载 mutated copy；用同一 patch `git apply --reverse --check` 后 reverse-apply。INT／TERM／EXIT trap 覆盖异常恢复。没有使用 `git checkout`、`git restore`、整文件覆盖或 hunk discard。

| Mutation | 改动 | 预期 | 实际 | 恢复 |
|---|---|---|---|---|
| M-1 production original copy | `src/app/server/inbound.py` 的 `deepcopy(dict(payload))` 改为 `dict(payload)` | 若测试锁住判别器所依赖的 nested isolation，应红；独立 probe 应观察原件被 repair 污染 | presence 为 `dict(payload)`；`nested_shared=True`；repair 后 original 从三轮变两轮；相关 30 tests **全绿**，形成 ATRA-03 | reverse patch 后 SHA-256 从并回到 `283eee565445a2082d2f7f16658d91b500627c223b111beaa930debcb0c0002b`；同 30 tests 再跑全绿；`git diff --exit-code -- src/app/server/inbound.py` 为空 |
| M-2 synthetic role | 合成 turn 的 role 从 `user` 改为 `assistant` | 两条 anchor、count 与 idempotency 应红 | runtime source 显示 mutated append；8 tests 中 **4 failed、4 passed**，失败正是末尾 role／重复追加不符 | reverse patch 后 SHA-256 从并回到 `e69e4870ab32c5b560b127df24cfe55608e79df9ea56c7b3856900c1f64d0a82`；两个目标文件 26 tests 再跑全绿 |

用户给出的两次既有变异作为背景沿用而未重复消耗：删除 `original_payload` 判别器会红 2 条；把 `after=` 改成 `before=` 会红 6 条，其中 3 条是行为测试。它们与 M-2 一起证明 direct Anthropic anchor、顺序与合成 role 有分辨力；M-1 证明 production copy seam 仍是盲区。

## 运行与搜索面

- 目标测试：`test_anthropic_trailing_assistant.py` 与 `test_builtin_subscribers.py` 共 26 passed；恢复两轮 mutation 后分别重跑 30／26 项，均通过。
- 相关回归：tool-pair repair、blank-text、trailing subscriber、built-in wiring、translation driver、server inbound 共 123 passed。
- 静态检查：对本片 source／tests 运行 `ruff check`，通过；运行 Pyright，0 errors／0 warnings／0 informations。
- 生产形状 probe：Responses → Anthropic client-authored assistant tail；blank pass 生成 empty assistant tail；generation 与 count 的 nested original isolation，全部走 `build_chain`／`build_context`／`handle` 或 `handle_count_tokens` 到 recording provider。
- 上游证据：没有重复发真实请求，按任务要求沿用 2026-08-24 已核实矩阵；另读取本仓现有 2026-08-20 F4／F6 raw captures，确认 empty assistant 200 与新增全称冲突。
- 调用面：枚举 production `build_context` call site、所有 `RequestContext` 构造、`messages` list mutation、`attempt.prepare` publisher／subscriber、translator registry 与 Responses→Anthropic role 映射。
- 未覆盖面：未跑完整 `pytest tests`、全仓 Ruff／Pyright；未评同伴的 human-controlled、Docker、experiment 等并行改动；未对真实上游重新计费调用；未评 response SSE、retry policy 或其它 Spec 章节的既有内容。
- 被评文件快照 SHA-256：core `e69e4870ab32c5b560b127df24cfe55608e79df9ea56c7b3856900c1f64d0a82`；registry `99ed28e732be399c2efb73850fe4f3eb09ba49dca87d041a0fe75907f9779c22`；semantic `b7a8038e832a8fabee841c866738c9e01aea15ac0c675556b5031ff1cac62e4e`；new tests `593955b42b66b16775db30a676b33bf21c53038e27d1293f2f0fd1e026fcb727`；built-in tests `7819e93581738abc1343ebb248f52088a4b81e3119dde1c5af62630ee99ff093`；Spec `367daaece7cf0b13a06c4481093640dfbd6192a372eb123419b1048ca5121f2f`；candidate `77bec0108040782b13a1b90d9cd69c2d547b53e356bce937e1355fa013e9d7e9`。
- 背景报告锚：前轮 `260824-implementation-review.md` 的自身 `reviewed_at_rev` 为 main `a7a0e058fc1940c188626e8d3f4aa38e0393ea9c`、dev `f7c54017108da54f21fba5cb9ebe1f6936cbbdfc`，本次读取 bytes SHA-256 `571ece382b0aa0b16d82f96197db3260e123d8359eeffcc9946d9523821f6333`；处置 `review-disposition.md` 在本次 dev HEAD `764c1e54996d15f36d06570a9a99bd33de1a1635` 下读取，bytes SHA-256 `f594cc1592bb6e14daa417e8b599aed28a4dddd3df8ee2cfa5bc20423bc5085c`。

## 我最没把握的三个判断

1. **ATRA-02 定为 major 而非 minor。** 触发形状比两条主 anchor 少见，但它把一条已知可接受的 body 改成含新用户指令的 body，且 living Spec 的核心全称直接与第一手证据冲突；我按语义影响而不是频率定为 major。若调用方只按当前发生频率定级，可重判级别，事实与修复义务不变。
2. **Responses 末尾 assistant 的产品语义。** “当前判别器无法证明它是代理造成”是确定事实，现行 §6.3 又明确要求保留客户端所写内容，所以 ATRA-01 成立；但最终应该透传让 Anthropic 拒绝、在 translation 层显式拒绝为不可携带，还是另立可见的 continuation contract，需要 Spec owner 选择，评审建议不替它决定。
3. **ATRA-05 的实际后果。** candidate 确实丢了模型／stream／样本数限定，但尚未进入 human-controlled authority，当前不会直接改变运行行为，所以定 minor。若用户总是连同 Spec 一起摘取，误读概率更低；这不改变候选文本自身应能安全摘取的义务。

## 执行本契约时遇到的摩擦

共享树含多组不在范围内的 dirty files，且 `.dev` 是独立仓库；所有命令都显式绑定 `/home/xp/src/ghc-api-proxy-py`，变异只触及两份冻结 patch 所列的一行并逐轮 reverse-apply。没有修改任何被评对象，报告文件是唯一持久新增。除此之外 none。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-08-24`
- `finding_total: 5`
- `blocker: 0`
- `major: 2`
- `minor: 3`
- `nit: 0`

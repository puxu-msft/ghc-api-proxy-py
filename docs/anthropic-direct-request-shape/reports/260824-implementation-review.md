---
report_id: anthropic-direct-request-shape-implementation-review-260824
attempt_id: main-review-1
status: draft
reviewed_at_rev:
  main_head: a7a0e058fc1940c188626e8d3f4aa38e0393ea9c
  dev_head: f7c54017108da54f21fba5cb9ebe1f6936cbbdfc
  reviewed_files_sha256: a1a361c96735c5e5f380ab6caf2010d2974cb832c7245e5f2a3b677ee48a5995
reviewed_at: 2026-08-24
---

# Anthropic direct request shape implementation review

## 评审范围

本次只评用户指定的 13 个对象：`src/app/model_provider/types.py`、`src/app/model_provider/github_copilot.py`、`src/app/pipeline/routing.py`、`src/app/pipeline/request.py`、`src/app/pipeline/translation_driver/reasoning.py`、`src/app/pipeline/subscribers/anthropic_thinking.py`、`src/app/pipeline/subscribers/__init__.py`、`src/app/config/schema.py`、`src/app/server/composition.py`、`tests/unit/pipeline/subscribers/test_anthropic_thinking.py`、`tests/unit/pipeline/subscribers/test_builtin_subscribers.py`、`.dev/docs/anthropic-direct-request-shape/spec.md` 与 `.dev/docs/anthropic-direct-request-shape/README.md`。

判据按用户指定顺序建立：先读 `docs/.human-controlled/` 中 `message-format-reshape.md`、`message-translation.md`、`upstream-retry-and-continuation.md`、`config.example.yaml`、`request-pipeline.md`、`api.md`、`ghc-api.md` 与 `README.md`；再读项目 `CLAUDE.md` 和 `.claude/rules/00-development-workflow.md`；然后读本次新 Spec 与 README；最后读归属调查 `.dev/docs/tmp/260824-adaptive-thinking-spec-ownership.md`。在读实现前已固定承重判据，不从实现反推。

明确排除用户点名的并行改动：`src/app/server/routes/inference.py`、`src/app/pipeline/delivery/stream.py`、`tests/int/test_pipeline_app.py`、`docs/.human-controlled/config.example.yaml` 与 `docs/.human-controlled/message-translation.md`。评审期间共享树又出现 `src/app/observability/request_log.py`、`src/app/observability/request_trace.py`、`src/app/streaming/keepalive.py`、若干 observability／delivery／streaming 测试及 Docker 资产的改动；它们同样不在本次语义评审范围内，也没有被修改。完整回归会自然加载当前共享树，但其通过不等于我评了这些并行改动。

未读取 388KB rejection capture 全文；任务已给出该事实背景并允许不复查。我只把用户提供的已核实字段作为背景，同时以新 Spec 中相同字段的记录交叉核对。未发真实上游请求；依赖上游真实契约的 count_tokens 字段合法性由 2026-08-24 在线 API reference 与本地项目路径共同核查。

## 总体判定

**Verdict：needs-fix。Blocker：0。发现：7 项，其中 major 3 项、minor 4 项。**

核心 400 的正向修复路径成立：目录能力已进入 `ModelDescriptor`，路由把同一个 descriptor 带到请求上下文，`enabled` 在 adaptive 模型上被改成 `adaptive` 并移除 budget，display 默认透传，客户端自己的 `output_config` 不被覆盖，subscriber 注册到实际 `attempt.prepare` 链路。证据强度：强到可据以行动，依据是最终代码逐处比对、完整链路行为探针、针对性变异与 1676 项回归。

但当前候选仍不满足完整契约：常见的“省略 `thinking`”请求会让显式配置的 effort 完全失效；Rule 4 在目录只发布本地 ladder 未知的新档位时违反 Spec；实现还把行为扩展到了 Spec 明确排除的 translated-to-Anthropic 腿。三项都命中关键目标、公共契约或项目的“Spec 必须先完整”硬规则，因此定为 major。

## Major findings

### ADTR-01：请求省略 `thinking` 时，显式配置的 `model_thinking_effort` 不会上 wire

- `finding_id`: `ADTR-01`
- `severity`: `major`
- `primary_location`: `src/app/pipeline/subscribers/anthropic_thinking.py:86-92`
- `related_locations`: `src/app/pipeline/subscribers/anthropic_thinking.py:117-129`；`.dev/docs/anthropic-direct-request-shape/spec.md:119-146`；`tests/unit/pipeline/subscribers/test_anthropic_thinking.py:128-166`
- 具体失败场景：配置 `model_thinking_effort: {claude-sonnet-5: xhigh}`，目录 descriptor 发布 `reasoning_efforts=(low, medium, high, xhigh, max)`，客户端向 Anthropic Messages 直连腿发送合法请求但省略顶层 `thinking`。`adapt_thinking_capability` 在第 89-92 行发现 `thinking` 不是 dict 后直接返回，所以后面的 resolved-model 配置查找和 `output_config` 写入都不可达。完整 `build_chain → handle → provider.send` 探针观察到实际 wire body 只有 `model` 与 `messages`，没有 `output_config`。
- 错误结果：operator 明确配置的 `xhigh` 被静默忽略；既没有 `output_config`，也没有 Spec Rule 2 所要求的能力缺席日志，因为整个 effort 分支未运行。对 Sonnet 5 这类省略 `thinking` 仍默认 adaptive 的模型，这不是“没有思考”的请求。
- 判据：Spec §2.4 明确写 `thinking` 与 `output_config` 并列、互不相干；§4.2 只把“模型没有配置项”“目录未发布”“已发布／未发布如何对齐”作为是否发送的条件；§4.4 唯一额外禁止是 `thinking.type == disabled`。当前 early return 增加了 Spec 没有的“必须有 thinking object”门。
- 证据强度：强到可据以行动。代码控制流直接成立，且生产组成路径探针实际打印 `{'model': 'claude-sonnet-5', 'messages': [...]}`。若“effort 只在客户端显式携带 thinking 时才生效”其实是新需求，则结论会改变；但那会修改用户给出的 per-model 配置语义，必须先修 Spec，不能由 early return 暗中决定。
- 建议：把“thinking shape 整形”和“effort 注入”拆成两个顺序阶段。缺席 `thinking` 时跳过前者，但仍执行客户端 `output_config` 保护、resolved-model 配置查找和目录对齐；只有可读对象且 type 为 `disabled` 时跳过代理注入。补一条完整 `build_chain → handle → provider.sent` 测试，输入不含 `thinking`，断言 `output_config.effort == xhigh`。

### ADTR-02：Rule 4 遇到目录只发布 ladder 未知档位时会错误省略 effort，并声称目录没有发布任何档位

- `finding_id`: `ADTR-02`
- `severity`: `major`
- `primary_location`: `src/app/pipeline/translation_driver/reasoning.py:158-166,169-209`
- `related_locations`: `.dev/docs/anthropic-direct-request-shape/spec.md:129-138`；`src/app/pipeline/subscribers/anthropic_thinking.py:53-69`；`tests/unit/pipeline/subscribers/test_anthropic_thinking.py:151-181`
- 具体失败场景：operator 配置 `max`，未来目录只发布一个本项目尚未认识的合法 effort `('turbo',)`。Spec Rule 3 已明确承认目录可以发布 `EFFORT_LADDER` 外的名字，Rule 4 又要求 exact miss 后“取不到则取最弱的已发布档”；只有一个 published 值时，最弱值没有歧义，就是 `turbo`。实际 `align_effort('max', ('turbo',))` 返回 `ReasoningResolution(effort=None, approximated=True, reason='this model advertises no reasoning efforts')`。
- 错误结果：subscriber 不发送 `output_config`，上游回到自己的默认；日志还把“发布了一个未知名字”误报成“没有发布 reasoning efforts”。这同时违反 Rule 4 的 wire 结果和日志事实。
- 根因：`_weakest()` 只遍历本地 `EFFORT_LADDER`，完全看不见 published 中的未知名字。若 published 混有多个未知名字，Spec 的“最弱”本身又没有可执行定义，因为同一文件已经明确目录列表不承诺排序；这部分是 Spec 自身需要先补齐的开口。
- 测试鉴别力：删除 `align_effort` 的 `if desired in supported: return ...` 整个 exact-published 分支后，`test_anthropic_thinking.py` 21 项仍全绿。现有 `xhigh`／`max` 样本都在本地 ladder 上，会被 `_at_or_below` 另一分支顺便返回同一个值，因此没有锁住 Rule 3 最关键的“目录发布未知名字也原样发出”。
- 证据强度：强到可据以行动。单未知 published 的反例不依赖未知档位间排序；函数行为已实际执行。多未知值时该发哪个是未决设计，不能由 reviewer 发明。
- 建议：先修 Spec Rule 4，明确 unranked published values 的处理。最低限度应覆盖两类：configured 自身被发布时始终原样发送；configured 未被发布且 published 中没有任何可排名档位时，单一值可直接作为 floor，多值则必须明说“无法排序时省略并准确记录”或另立可信顺序来源。随后按修订契约改实现，并增加 `configured='turbo', published=('turbo',)` 与 `configured='max', published=('turbo',)` 两条测试；第一条必须让删除 exact 分支变红。

### ADTR-03：实现修改 translated-to-Anthropic 请求，但 Spec 的规范范围只允许 direct route

- `finding_id`: `ADTR-03`
- `severity`: `major`
- `primary_location`: `.dev/docs/anthropic-direct-request-shape/spec.md:5`
- `related_locations`: `.dev/docs/anthropic-direct-request-shape/README.md:3-9`；`src/app/pipeline/subscribers/anthropic_thinking.py:78-86`；`src/app/pipeline/driver.py:142-172`；`src/app/pipeline/translation_driver/anthropic_messages.py:261-281`
- 具体失败场景：一个 `translation_required == True` 的请求被翻译到 Anthropic Messages target，翻译产物携带 `thinking: {'type':'enabled','budget_tokens':N}`，目标 descriptor 发布 adaptive。driver 在 translation 后运行 `attempt.prepare`，subscriber 只检查 `target_format is ANTHROPIC_MESSAGES`，因此会改成 adaptive、删 budget、应用 display 并可能注入 effort。可是 Spec 第 5 行把范围限定为 `translation_required == False`，README 第 3 行也只称 direct leg；该 observable rewrite 没有任何规范条款拥有。
- 错误结果：实现行为可能本身是合理的，但它先于完整 Spec 落地，触发项目规则中“你已经在改行为，而编辑的不是 Spec”的明确定义。后续 reviewer 无法回答 translated leg 上 §3.1、§4.2 与 §5 是否同样成立，也无法判断未来改窄 target guard 是修复还是回归。
- 当前影响限定：默认 registry 今天唯一能从 Responses 翻译到 Anthropic 的 reader `from_openai_responses` 没有把标准 `reasoning` 填入 `SemanticRequest.reasoning`，所以标准 Responses request 当前不会经 `_restore_thinking` 生成 enabled／adaptive；我否决了“今天标准 Responses reasoning 已会触发该 400”的候选结论。未知顶层 extension、手工构造的 semantic request，以及未来补齐 reasoning reader 后的路径仍会进入这段 subscriber。这个限定降低当前触发频率，不消除 Spec bypass。
- 证据强度：实现范围与 Spec 范围的矛盾是强到可据以行动的静态事实；“标准 Responses reader 当前不触发 `_restore_thinking`”也由完整函数与 registry 调用面核实。translated leg 最终应采用相同规则还是不同规则是设计判断，需由 Spec owner 决定。
- 建议：我偏好扩展本 Spec 的范围为“所有发往 Anthropic Messages target 的出站请求，在 translation 之后的最终 shape”，因为能力是目标模型属性，subscriber 和 count_tokens 的实际阶段也都按这个边界运行；README 只需继续明确排除 Anthropic→Responses 的 reasoning mapping，而不是笼统排除 translated-to-Anthropic。若 owner 选择维持 direct-only，则实现必须加 `translation_required == False` guard，并另给 translated leg 建 owner。无论选哪侧，先改 Spec，再改代码与测试。

## Minor findings

### ADTR-04：count_tokens 腿的刻意接线没有判别性测试，整条能力门可被跳过而 39 项相关测试全绿

- `finding_id`: `ADTR-04`
- `severity`: `minor`
- `primary_location`: `tests/unit/pipeline/subscribers/test_anthropic_thinking.py:316-349`
- `related_locations`: `tests/unit/pipeline/subscribers/test_builtin_subscribers.py:199-220`；`src/app/pipeline/subscribers/anthropic_thinking.py:78-84`；`src/app/pipeline/driver.py:237-266`
- 具体失败场景：有人依据 `COUNTING_ONLY` 给 subscriber 加一个 early return，使 generation 仍正确改写，但 `/v1/messages/count_tokens` 把原来的 enabled／budget body 直接交给上游。新文件的 production-path 测试只走 `handle()`，不走 `handle_count_tokens()`；built-in counting 测试虽然发布 `attempt.prepare`，其 payload 没有 thinking、descriptor 也没发布 adaptive，所以无论该 subscriber 是否执行，断言都相同。
- 错误结果：generation 与 count_tokens 对“真正会发送的 body”产生分叉；adaptive 模型的 count request 可能重现 enabled 400，或者本地校准基于与 generation 不同的 shape。当前实现没有这个错误，但测试不能防它。
- 变异证据：在 target-format guard 后插入 `if context.extras.get("counting_only"): return`，运行 `test_anthropic_thinking.py` 与 `test_builtin_subscribers.py` 共 39 项，全部通过。恢复后同样 39 项通过。另一个不改源码的完整 `build_chain → handle_count_tokens → provider.counted` 探针确认当前正确行为是 `thinking={'type':'adaptive','display':'omitted'}` 且 `output_config={'effort':'xhigh'}`；因此这是测试分辨力缺口，不是对现实现行为的误报。
- 证据强度：强到可据以行动。变异已在测试实际加载的 module path 上由 `inspect.getsource` 证明生效；绿灯不是注入失败。
- 建议：新增一条通过 `handle_count_tokens` 的 seam test，provider descriptor 发布 adaptive 与 efforts，输入使用实测 enabled／63999／omitted 形状，断言 `provider.counted` 收到 adaptive、无 budget、resolved-model effort，并断言 conversion loss 只出现一次。

### ADTR-05：Spec A-1 把生产不可达的 defensive state 写成“当前实现按透传”，五项待裁表中这一项并非本 topic 的真实开口

- `finding_id`: `ADTR-05`
- `severity`: `minor`
- `primary_location`: `.dev/docs/anthropic-direct-request-shape/spec.md:167-175`
- `related_locations`: `src/app/pipeline/routing.py:54-57,97-101`；`src/app/pipeline/subscribers/anthropic_thinking.py:97-99`；`tests/unit/pipeline/subscribers/test_anthropic_thinking.py:98-105`；`tests/unit/pipeline/test_direct_driver.py:199-206`
- 具体失败场景：resolved model 不在 provider catalog，`provider.describe()` 返回 `None`。A-1 写“当前实现按透传”，但 `decide_route` 第 97-99 行立刻抛 `UnknownModel`，根本不会产生 Route，不会执行 `apply_route`，subscriber 更不会看到 descriptor None。`Route` 自己的注释也明确说 production `decide_route` 返回的每条 route 都有 descriptor；None 只来自手工测试 Route。
- 错误结果：读者会把未知模型的现行行为理解成“body 透传给 upstream，由 upstream 拒绝”，实际是 proxy 路由阶段本地拒绝。`test_an_undescribed_model_is_left_exactly_as_the_client_wrote_it` 只证明函数在手工构造 context 上的 defensive 行为，不证明系统行为。
- 判据：项目规则要求 living Spec 立即纠正已知事实；延后台账不能寄存一个已经能由现有路由契约回答的“当前实现是什么”。是否要改变 unknown-model routing 是更宽的路由产品裁决，不是 direct request shape subscriber 的未决分支。
- 证据强度：强到可据以行动。调用顺序和既有路由测试直接锁定；无需猜测 upstream。
- 建议：从本 topic 的 open 表移除 A-1，或改写为“若未来允许无 descriptor 的 route，subscriber 应采取什么 defensive policy”，明确今天生产不可达。若真正要裁决 unknown model 是本地拒绝还是 upstream passthrough，应登记到 routing owner，并同步修正 subscriber 注释与测试名，避免把 unit-only state冒充现行系统行为。

### ADTR-06：两个新配置被 closure 固定在 build_chain 时，但权威配置文档默认承诺热重载

- `finding_id`: `ADTR-06`
- `severity`: `minor`
- `primary_location`: `src/app/pipeline/subscribers/__init__.py:40-79`
- `related_locations`: `src/app/server/composition.py:485-501`；`src/app/config/schema.py:33-54,297-304,366-378`；`docs/.human-controlled/config.example.yaml:21-24`
- 具体失败场景：服务以 `display=passthrough`、`model_thinking_effort[claude-sonnet-5]=low` 建链后，operator 按人控文档“除非另有说明，所有设置均支持热重载”改为 `summarized`／`xhigh`。subscriber lambda 已捕获旧 mapping 与旧 string，每个请求继续用旧值；这两个 path 又没有列入 `NOT_HOT_RELOADABLE`，所以 schema 侧会把它们呈现为无需重启。
- 错误结果：配置快照与实际 wire 行为分叉，直到重启才生效。当前仓库的 production 代码尚未把 `ConfigProvider.reload()` 接进 Chain，这说明热重载存在更宽的既有实现缺口；但新注释仍明确把二者称为“startup decisions”，与权威默认冲突，不能把更宽缺口当作本次新键的豁免。
- 证据强度：足以登记但定级为 minor。静态 capture 与 restart-only 表是确定事实；当前进程没有 production reload caller，所以我没有声称已复现一次真实热重载。若项目另有未在 `src/app` 中的整链重建机制，该结论需要重判；本次全仓 `src tests` 搜索未找到。
- 建议：二选一并先更新 Spec／候选配置文本。若这些设置应热重载，subscriber 应在每个 request 使用该请求捕获的 config snapshot，或 reload 时重建完整 subscriber registry／Chain；若当前只支持 restart，则把两个 dotted path 加入 restart-only authority，并在 `.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md` 明说，交用户追认，而不是让 closure 暗中决定。

### ADTR-07：module docstring 把“未配置模型不发 output_config”一并标成 2026-08-24 用户裁决，超出了给定原话

- `finding_id`: `ADTR-07`
- `severity`: `minor`
- `primary_location`: `src/app/pipeline/subscribers/anthropic_thinking.py:9`
- `related_locations`: `.dev/docs/anthropic-direct-request-shape/spec.md:119-146`；`.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md:1-8,66-72`
- 具体失败场景：后续讨论是否给未配置模型一个 default effort 时，维护者读到 docstring 的完整句子“effort comes from model_thinking_effort ... and an unset model gets no output_config at all. Ruled 2026-08-24”，会把“unset 的默认行为”视为用户已关闭的问题，跳过重新裁决。
- 依据：本任务给出的用户原话只覆盖“不从 budget_tokens 推导 effort；新增 model_thinking_effort 映射、按模型给值并与实际上游发布能力对齐”。它没有逐字规定配置项缺席时必须 omission，也没有规定不得存在全局 default。Spec Rule 1 的 omission 有自洽的 agent rationale，但 candidate 第 3 行又正确标明“我方推导，在摘取前不是用户裁决”。
- 错误结果：agent 推导被提升为用户决定，未来不会被当作可修订的 derived rule。当前 wire 默认是否合理不受这条发现否定；问题只在决定归属。
- 证据强度：足以登记但这是我最不确定的 attribution 判断之一。“按模型给值”可以自然推导出“没键就没值”，但自然推导不等于逐字裁决；若主会话持有更宽的用户原话，应以那份一手锚覆写本判断。
- 建议：把 docstring 拆成两句，精确标注用户裁定的部分；把“absent entry means omit”标为 Spec §4.2 的 derived default 与理由。不要删除该行为，也不要把整段改成“用户没决定任何东西”。

## 明确核查且未发现问题的方面

1. **§3.1 改写表的当前实现正确。** enabled＋adaptive 会改成 adaptive 并删除 budget；enabled＋无 capability 原样保留；adaptive、disabled、未知 type 与非对象在默认 passthrough 下不改 type；budget 删除写入 `conversion_losses`。证据强度：强到可据以行动，来自逐分支代码、实测 body 测试与 display／幂等变异。
2. **display policy 的值集合没有缺项或多项。** `passthrough`、`drop`、`omitted`、`summarized` 正好对应用户裁定与 Spec 表；`drop` 对 disabled 也删除，rewrite 值对 disabled 不新增。默认 passthrough 经过 full chain，实测输入的 `display='omitted'` 保留。证据强度：强到可据以行动。
3. **disabled display 分支的测试有分辨力。** 把 conditional rewrite 变成 unconditional 后，专门测试因多出 `display='summarized'` 变红；不是假绿。证据强度：变异正控。
4. **subscriber 幂等性当前成立且测试有分辨力。** 第二次运行看到 adaptive，不再记录 budget loss；把条件扩成 enabled／adaptive 都进入后，幂等测试观测到 loss 数从 1 变 2 并变红。证据强度：变异正控。
5. **catalog capability 接线完整。** `parse_adaptive_thinking` 只接受 literal True；`replace_catalog` 写入 descriptor；`decide_route` 把同一 descriptor 放进 Route；`apply_route` 携带到 context；full-chain test 从 alias mapping 一直断言到 provider wire。用户提供的既有变异又说明切断 `apply_route` 只有 seam test 会红，其他 unit 不冒充接线覆盖。证据强度：代码路径＋异源变异事实，足以行动。
6. **resolved-model 匹配在代码和 Spec 中一致。** map lookup 使用 `context.resolved_model`；composition 不把 alias 预处理成另一张表；schema、Spec、candidate 与测试都明确不是 requested alias／`model_mappings` key。顶层 placement 作为“跨 provider 的 operator model preference”在当前单一 provider 产品边界内合理，实际 capability 仍由 route descriptor 按 provider 校验。证据强度：强到可据以行动；多 provider 同 id 但需要不同 preference 是未来产品选择，不在现有裁定里。
7. **客户端自己的 output_config 被保护。** key 只要存在就不覆盖，包括其中不只有 effort 的未来 shape；disabled request 也不会由 proxy 新增 effort。证据强度：直接分支与测试。
8. **没有从 budget 推导 effort。** 新 path 只读 config，复用的 ladder 仅用于配置值与 published membership 对齐；63999 只进入 dropped-field loss detail。证据强度：完整数据流搜索与行为测试。
9. **反应式 400 retry 没有被引入。** subscriber 在 attempt send 前主动改写，失败分类和 retry policy 未被本次改动触碰。证据强度：调用顺序与 diff。
10. **count_tokens 上执行同一 reshape 的判断本身正确。** 当前官方 Token Count API reference 明列 top-level `thinking` 与 `output_config.effort` 为合法 body parameters，且 user guide 说明 count endpoint 接受 message creation 的同类 structured inputs。完整本地 probe 穿过 `handle_count_tokens` 并观察 provider 收到 adaptive／xhigh，不影响既有成功响应或 calibration 学习入口。证据强度：2026-08-24 live docs＋生产路径 probe，足以行动；未对 GHC 的具体 count endpoint 做 live credentials call。
11. **证据限定在正文中基本被正确带走。** first-party vscode-copilot-chat 的“已归档、停在 2026-04/05、硬编码三档不可照抄”和目录“活数据、表只是快照”都在使用证据的 §2.2／§2.4 当地重复，而不只停在 §8 表。A-5 所称 candidate 已提交也经文件存在与内容核实。证据强度：直接文件核对。
12. **用户裁定的两项核心归属在 Spec 中准确。** §4.0 只把“不从 budget 推导、改用 per-model config 并与 published capabilities 对齐”归给用户；§5 把 display 可改写／drop、默认 passthrough 归给用户，均与任务提供的逐字裁定同范围。ADTR-07 只针对 module docstring 顺带扩张的 unset default，不否定这两项。

## 否决掉的候选发现

1. **否决“count_tokens 不接受 output_config，因此 subscriber 会新造 400”。** 2026-08-24 live API reference 的 count_tokens Body Parameters 明列 `output_config`，其 `effort` 集合含 low／medium／high／xhigh／max，也明列 enabled／disabled／adaptive thinking。实际本地 provider probe也顺利经过 `_countable` 与 provider chain。没有 GHC live call，因此结论限定为官方 contract＋本项目路径，不冒充 GHC 实测。
2. **否决“translated-to-Anthropic 的标准 Responses reasoning 今天会经 `_restore_thinking` 生成 adaptive／enabled 并触发旧模型 400”。** registry 的唯一相关 inbound reader `from_openai_responses` 当前没有设置 `SemanticRequest.reasoning`，所以标准 `reasoning` field 不到 `_restore_thinking` 分支。保留 ADTR-03 的原因是 implementation scope 仍比 Spec 宽，且未知 extension／未来 reader 会进入；不是把未发生路径说成已发生故障。
3. **否决“subscriber 不该跑 count_tokens，因为计数只关心文本”。** 官方文档专门展示带 thinking 的 count request，历史 thinking block 是否计入与 request shape 有关；项目自己的 `handle_count_tokens` 契约也是测“真正会发送的 body”。正确结论是应继续跑，但要补 ADTR-04 的判别性测试。
4. **否决“model_thinking_effort 应放进 model_mappings 或 provider section”。** 用户裁定的是 per-model preference；resolved id 匹配加 descriptor capability alignment 已把 alias 与 provider capability分开。当前只有一个 provider，移进 model_mappings 会再次把 requested alias 与 resolved capability混为一谈。多 provider 同 id 是否要不同 preference 是尚无具体失败面的未来需求。
5. **否决“ThinkingDisplayPolicy 应包含 disabled”。** `disabled` 是 `thinking.type`，不是 display 的处置动作；display policy 的四项完整表达 passthrough／drop／两种合法 rewrite 值。

## 变异验证记录

所有变异前先把 `anthropic_thinking.py` 与 `reasoning.py` 的当前未提交 bytes 保存到 `/tmp/ghc-adaptive-review-baseline/` 作为 baseline 证明，但不使用整文件覆盖恢复。每次先写一份只含该 mutation 的 frozen patch，`git apply --check` 后应用；用独立 Python 进程打印实际 imported module path 与 `inspect.getsource`，证明测试加载了 mutated copy；测试后以同一 patch `git apply --reverse --check` 再 reverse-apply；INT／TERM／EXIT trap 负责异常恢复。每轮恢复后跑 affected suite。最后用 `git diff --no-index` 比较两个 mutation files 与 baseline，均无输出，说明 byte-identical；没有用 `git checkout`／`git restore`／整文件回拷。

| Mutation | 改动 | 预期 | 实际 | 恢复 |
|---|---|---|---|---|
| M-1 display disabled | 删除 `_apply_display` 的 `if kind != 'disabled'`，让 rewrite 无条件写 display | disabled 专测应红 | 1 failed，因实际多出 `display: summarized` | reverse patch 后专测 1 passed；最终 full file 21 passed；bytes exact |
| M-2 exact published effort | 删除 `align_effort` 的 `if desired in supported` 整个分支 | 若测试真锁住 Rule 3，应红 | 21 passed；known ladder 上的 xhigh／max 被 `_at_or_below` 另一分支给出相同结果 | reverse patch 后 21 passed；bytes exact；形成 ADTR-02 的测试证据 |
| M-3 idempotency | 把 rewrite condition 从 `kind == enabled` 扩成 `kind in (enabled, adaptive)` | 第二次运行会重复记录 loss，幂等专测应红 | 1 failed，loss 长度 2 而非 1 | reverse patch 后 full file 21 passed；bytes exact |
| M-4 count_tokens reachability | target-format guard 后新增 `if context.extras.get('counting_only'): return` | 若测试覆盖刻意的 counting behavior，应红 | 两个相关测试文件共 39 passed | reverse patch 后同样 39 passed；bytes exact；形成 ADTR-04 |

## 运行与搜索面

- 相关 unit 集合：model provider、routing／direct driver、reasoning、两个 subscriber test、config loading，共 144 passed。
- 完整项目检查：`ruff check src tests` 通过；`pyright src tests` 为 0 errors／0 warnings；`pytest tests --cov=app --cov-report=term --cov-fail-under=80` 为 1676 passed、2 skipped、coverage 90.26%。这些命令的 pytest rootdir 是 `/home/xp/src/ghc-api-proxy-py`。完整绿灯只说明当前树没有一般回归，ADTR-01／02 的反例和 M-2／M-4 假绿仍然成立。
- 行为 probe：完整 generation path 复现“无 thinking 时配置 effort 不上 wire”；`align_effort` 直接执行 exact unknown 与 unknown-only fallback；完整 count path 观察 adapted thinking／effort。
- 官方 contract：读取 `claude-api` skill 的 `brief/thinking-and-effort.md` 与 2026-08-24 live `https://platform.claude.com/docs/en/build-with-claude/token-counting`、`https://platform.claude.com/docs/en/api/messages-count-tokens`。
- 调用面：读完 `shape_request`、`handle`、`handle_count_tokens`、DirectDriver prepare loop、translator registry、Anthropic／Responses request readers／writers、MessagesRequest 与 Anthropic estimator；全文搜索 ModelDescriptor／Route constructors、counting marker、config reload caller、reasoning restore tests。
- 未覆盖面：没有使用 credentials 对 GHC live endpoint 实发；没有评并行会话文件的语义；没有评 response SSE、error envelope、retry body、delivery 或 observability 本身；没有修改任何被评代码／Spec。

## 我最没把握的三个判断

1. **ADTR-03 定为 major。** Spec bypass 是确定事实，但标准 Responses reader 今天不触发 `_restore_thinking`，所以若 severity 只按当前 production frequency 而不按项目硬规则，可降为 minor。我的判断依据是项目明确把“完整 Spec 先于 observable implementation”列为 non-negotiable 公共契约。
2. **ADTR-06 是否应归本 patch。** 新键 startup-bound 是确定事实，但 production config reload 整体尚未接线，属于跨切面既有缺口。我的判断是新字段仍不能无说明继承一个实现不兑现的“默认热重载”承诺，故列 minor 而非删掉。
3. **ADTR-07 对用户原话 scope 的读取。** 我只持有任务给出的两条逐字裁定；若主会话另有更宽原话明确说“未配置就省略，绝不提供默认”，该 finding 应撤销。当前证据只足以判“这里提供的一手原话没覆盖”，不支持全称断言“用户从未说过”。

## 执行本契约时遇到的摩擦

共享工作树在评审期间继续变化，新增了多个非目标 dirty files。每轮 mutation 都以 frozen patch reverse-apply，只比较本次触及的两个文件与 pre-mutation baseline；我没有试图把全树 status 恢复到起始列表，也没有撤销任何 peer 改动。除此之外 none。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-08-24`
- `finding_total: 7`
- `blocker: 0`
- `major: 3`
- `minor: 4`
- `nit: 0`

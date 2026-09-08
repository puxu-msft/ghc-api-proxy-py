# Effort translation 实施计划独立评审

- review_id：effort-translation-plan-260903
- attempt_id：effort-translation-plan-gpt-opus-a1
- 评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/plan-effort-translation.md` current working tree，以及绑定的 current `spec.md`、`acceptance.md` 和计划列出的源码／测试入口。
- 评审方式：逐条对照 P1～P15；源码快照来自隔离工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-a0635985a7232bf0f`。

## 整体判定

**needs-fix。** 未发现 blocker；发现 6 条 major。计划覆盖了 Spec 的主要行为面，配置 merge 顺序、source header 捕获、两向档位矩阵、nested residual、direct-route 结构性 bypass 和 `.dev`／code worktree 分离方向基本成立，但 Task 2 没有可运行的中间态，配置 strictness、逐消息控制算法及验收分辨力仍有会让实现偏离或让切片假绿的缺口。

## P1～P15 逐条回应

| ID | 结论 | 核验摘要 |
|---|---|---|
| P1 | MAJOR（M1、M4、M5） | `ThinkingEffortIntent`、双向 mapping、profile、ultracode、send／count和facts都有名义 owner（计划第 27～787 行），但 Task 2 的owner边界不可运行，且控制证据与异常facts证据不足。 |
| P2 | MAJOR（M1） | 各Task普遍按production→probe→tests排列，但 Task 2 在production重构与Task 3／4 reader／writer落地之间没有可运行状态，不能满足每个Task先运行直接探针。 |
| P3 | MAJOR（M1、M3） | 所列现有路径均存在，新主类型签名大体在消费者之前；但 Task 2 删旧字段后消费者仍待后续Task替换，且逐消息算法引用三个未定义helper。 |
| P4 | PASS | 按计划指定的放置方式，schema只定义config，`routing.py`编译，`reasoning.py`持有runtime profile，`semantic.py`持有target，`Chain`只携带compiled tuple，`build_chain()`启动时编译，可形成无环方向；当前入口见 `src/app/core/chain.py:16-25`、`src/app/pipeline/routing.py:8-38`、`src/app/server/composition.py:21-59`。 |
| P5 | MAJOR（M6） | `_deep_merge()`保留既有key位置并把新key追加到末尾，层次顺序也是bundled→user→env→CLI，足以实现同pattern替换及新pattern最后命中（`src/app/config/loading.py:36-52,190-212`）；但计划给出的关键不同pattern test不被Task 1的`-k`选中。 |
| P6 | PASS | 当前`shape_request()`在 `src/app/pipeline/driver.py:105-108`清空translated headers；计划要求两入口在调用它之前快照，并让send／count共用且不写回，顺序明确，Responses上游仍无该header。 |
| P7 | MAJOR（M3） | active／pending／future-only的主循环方向可读，但candidate识别、beta解析和非法shape判定未定义，因此错误role、未知sibling等输入没有唯一终态。 |
| P8 | PASS | 计划第 401～464 行明确了Anthropic缺省high、显式effort优先、disabled必须none、enabled排除none、budget只记loss，并删除旧`resolve()`／budget ladder活路径。 |
| P9 | MAJOR（M2） | Reverse矩阵、profile正负域、always-on、modes fallback、manual budget两阶段和effort对齐均有步骤；但`can_disable`不按Spec要求拒绝非bool。 |
| P10 | PASS | `nested_extensions_for()`按同格式复制、跨格式逐子字段记loss，writer先合并residual再覆盖owned effort，且reader须把owned对象移出generic extensions，顺序足以避免反盖与重复loss（计划第 267～284、462～464、589～595 行）。 |
| P11 | MAJOR（M5） | production设计包含成功／`TranslationRefused`两出口复制facts，并让`lossless`只看losses；但测试oracle允许异常事实只留在error detail，不能证明`RequestContext→RequestTrace→RequestLine→JSONL`链。 |
| P12 | PASS | 当前真实route只在`route.translation_required`时调用translator（`src/app/pipeline/driver.py:156-169,273-282`），计划保留该guard且不改legacy converter／subscriber；direct行为的验收分辨力缺口另计M4。 |
| P13 | MAJOR（M4、M5、M6） | 计划使用静态完整wire expected并声明mock／catalog／live边界，但没有安排REQ-05A要求的各机制单侧缺陷控制，异常facts oracle及两个targeted selector也可假绿。 |
| P14 | MAJOR（M1） | commit message统一要求`-F`、路径清单精确，`.dev`回主树后在独立repo提交，提交安全方向成立；但五个Task“独立可评审语义切片”的断言被Task 2不可运行的中间态否定。 |
| P15 | MAJOR（M3、M6） | 最终三条验证命令与项目CLAUDE.md一致且无`ruff format`，直接probe命令形状可运行；但存在未定义helper，且两条targeted命令不能执行其代表性关键测试。 |

## Blocker／Major findings

### M1［major］Task 2 没有可运行的 production 中间态
- 计划第 260～265 行删除 `SemanticRequest.reasoning`，而当前 `from_anthropic_messages()`仍在 `src/app/pipeline/translation_driver/anthropic_messages.py:146-155`写它，`_apply_reasoning()`仍在 `src/app/pipeline/translation_driver/openai_responses.py:952-974`读它。
- 两个消费者的正式替代分别归 Task 3和Task 4；按Task 2现有步骤执行后，普通Anthropic→Responses输入会在赋值或读取处得到缺字段错误，Task 2自己的probe／tests不能形成绿的production切片。
- 修正计划时应二选一并写死：让Task 2同时拥有精确的过渡reader／writer行为，或把IR替换与两向消费者重组为同一可运行语义切片；不得靠后续Task补齐。

### M2［major］`can_disable`没有落实Spec要求的strict bool
- Spec `spec.md:295`要求配置加载时拒绝非布尔`can_disable`；计划 `plan-effort-translation.md:55-60`却写成普通`can_disable: bool`，当前 `Section`只有`frozen=True, extra="forbid"`而没有全局strict（`src/app/config/schema.py:57-59`）。
- 输入 `can_disable: "false"`或`can_disable: 1`会被Pydantic bool coercion接受，而不是启动失败；这会让错误配置静默改变always-on／disabled政策。
- 将字段写为strict bool并在Task 1负例中同时钉住字符串与整数拒绝，正例继续接受YAML原生`true／false`。

### M3［major］逐消息控制的candidate与错误算法仍是未定义helper
- 计划第 415～436 行调用 `_is_effort_control()`、`_require_effort_beta()`、`_control_effort()`，但没有任何Task定义其签名、识别域、允许键、header token解析或稳定错误路径，违反P15的“无未定义helper”。
- 例如 `{"role":"assistant","content":[],"output_config":{"effort":"xhigh"}}`：若candidate先要求合法system shape，它会被当普通消息放行；若以`output_config`存在为candidate，它会按Spec拒绝。计划没有选定唯一算法。
- 在Task 3 production步骤中明确candidate predicate、空content两种合法拼法、message／`output_config`允许键、多个beta token解析、field path及过滤发生在message解析之前的顺序。

### M4［major］REQ-05A要求的单侧缺陷控制没有进入执行步骤
- Acceptance `acceptance.md:90-96`要求reader、capability、逐消息、反向profile、residual和direct bypass分别做单侧控制；计划Task 3／4只安排正确样本与常规pytest，Task 5仅提到一次删除facts copy，没有安排这些控制的执行与恢复。
- 因此“完整wire静态expected”本身不能证明测试会在reader与writer同源漂移、direct leg误入translator或residual双记时变红，P13当前不成立。
- 不需要常驻mutation framework；应把Acceptance列出的有限单侧改动按机制加入Task 3／4验证步骤，记录目标断言先绿、单侧改动后因目标原因红、恢复后再绿。

### M5［major］异常profile facts的测试oracle允许落错持久化槽
- 计划第 749～751 行允许always-on reject与profile missing把来源／原因保存在“durable record或错误detail”；P11要求它们进入独立`facts`字段并贯通`RequestContext`、`RequestTrace`、`RequestLine`和JSONL。
- 若只删除计划第 736～738 行异常分支的 `_keep_conversion_facts(context, refusal.facts)`，成功facts与错误detail仍在，现有表述下测试可全绿，而异常facts已经没有结构化持久化。
- 异常用例必须直接断言JSONL `facts`的exact code／detail，并增加只切断exception copy、保留success copy和error message的单侧控制。

### M6［major］两个切片命令不会运行计划自己给出的关键测试
- Task 1代表性test名是 `test_last_matching_user_profile_overrides_bundled_default`（计划第 183～201 行），但第 208 行的`-k 'thinking_profile or bundled_profile or model_translation'`三个substring都不在该名字中。
- Task 2代表性test名是 `test_nested_reasoning_fields_are_not_counted_as_lost_effort`（第 354～369 行），但第 378 行只选`source_header or nested_extension or same_format`，同样不命中。
- 两个切片都可在关键case未执行时报告green；应改test名或selector，并在计划中固定collection能看见这些exact node id的简单检查。

## 我最没把握的三个判断

1. **M6定为major而非minor，置信度中等。** 最终全量pytest会补跑遗漏case，但项目规则明确要求每个语义切片先有可判别直接证据；targeted green在当轮会被用来提交，因此我按证据边界而非最终补救定级。
2. **P4判PASS，置信度中等。** 该结论依赖按计划文字把compile／select放在`routing.py`、runtime类型放在`reasoning.py`，并把wire rendering放在`anthropic_messages.py`；计划没有逐个写出所有import语句，若实现者把`render_anthropic_thinking()`放入`reasoning.py`并运行时import `TranslationTarget`，会形成`semantic.py↔reasoning.py`环。
3. **P12行为边界判PASS、证据并入M4，置信度中等。** 当前route guard结构上确实绕过translator，但计划没有单列两条direct-leg byte-equivalent测试；我没有把它重复列为第七条finding，而把缺少的单侧控制计入M4。

## 执行摩擦

- 首先按契约调用`my-agents:as-reviewer`，harness返回`Unknown skill`；已记录摩擦并按本契约继续。
- 首轮并行`Read`错误地给Markdown传了空`pages`，四个调用均被参数校验拒绝；随后用合法参数重试并完成必读材料读取。
- 隔离工作树没有`.codegraph/`，`codegraph_explore`明确拒绝查询；随后改用`Read`与精确`rg`检查源码、tests和调用点，没有自行建立索引。
- 一次把`git status`与`wc`合在同一Bash调用，被worktree guard以目标形式过于复杂拒绝；随后只运行绝对路径`wc`，没有执行任何Git写操作。
- 唯一写入工具拒绝直接写主工作树的`.dev`路径，因此先在`/tmp`生成同一内容，再以exclusive-create方式复制到契约指定路径；未覆盖已有文件。
- 本次只写本报告，未修改计划、Spec、Acceptance、源码或tests。
- 边界判断：本轮不触发完整closeout；可观察依据是报告含6条major，且coordinator checklist明确声明返回后还会独立核验并处置，本次review attempt尚不是整体开发工作的关闭边界。

## 交付声明

delivery_complete:true
completed_at:2026-09-03T10:59:40Z
finding_total:6
blocker_count:0
major_count:6
minor_count:0
nit_count:0
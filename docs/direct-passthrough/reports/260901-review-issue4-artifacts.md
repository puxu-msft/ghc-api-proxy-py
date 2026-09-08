# issue #4 相关产物的独立评审

日期：2026-09-01
评审者：独立 agent（异源模型，`as-reviewer`／`as-pending-decisions-checker`）
verdict：**needs-fix**。blocker 0、major 5、minor 2。

> **落盘说明**：该评审 agent 受自身 developer 指令限制，不能创建 `.md` 文件，完整内容经消息交回主会话，由主会话逐字落盘于此。除本框与下方「主会话按语」外，正文为评审原文。
>
> **主会话按语**：七条全部采纳，无驳回。处置见 [`260901-issue4-sealed-reasoning-id.md`](260901-issue4-sealed-reasoning-id.md) §7 与 [`../spec.md`](../spec.md) §12 的 v17 行。

## 范围与判据来源

范围：测试 `tests/int/test_pipeline_app.py::test_a_sealed_reasoning_item_keeps_the_id_its_seal_was_cut_against`；`direct-passthrough/spec.md` 的 v16 改动；`deferred.md` D-8；`260901-issue4-sealed-reasoning-id.md`。

判据先读了用户控制的 `message-translation`、`message-format-reshape`、`request-pipeline`，以及 reviewer／pending-decision 两份技能。未发真实上游请求。

## 发现

### issue4-review-01（major）｜测试的夹具消掉了它必须辨别的真实差异

`tests/int/test_pipeline_app.py:2519-2532` 在 `added`／`done` 两个事件中都写同一组 `id="rs_1"`、`encrypted_content="sealed"`，但 `tests/int/cassettes/history_responses_stream.json:28、31` 记录的是同一 reasoning lifecycle 的 `id_002`／`id_003` 两组不同 pair；`tests/int/cassettes/anthropic_to_responses_stream.json:214、229` 也如此。

测试自己在 `2522` 说 id instability 应由 cassette 承载，却在 `2638-2673` 用这个无 instability 的 stand-in 审 id。

反例：实现把 `done` 的 id 统一改成 `added` 的 id、密文不动；此夹具输出不变、测试绿，真实流中却会把第二份密文挂到第一份 id，重现绑定失败。

对象级断言本身是正确选择，问题在 oracle 输入无鉴别力。

### issue4-review-02（major）｜它只测第一轮 response half，不测下一轮 request half

测试请求的 `input` 为空（`test_pipeline_app.py:2654-2657`），所以任何将入站 sealed reasoning id 删除／改写／送进 carrier decoder 的回归都不可见；`spec.md:321` 自己明确说 request translator gate 需要一条回归测试。

故 `test_pipeline_app.py:2645`、`spec.md:325`、报告 `:102-104` 所称「pair travels as one」只能限定为 synthetic stream 的 upstream→client 方向，不能称 round trip。报告 §6 也漏报了这项局限。

### issue4-review-03（major）｜D-8 的「不加」建议主要依赖「自清」，但依据不成立

报告 `:79-80` 明写 4141 仍是早于 `1fb37cd` 的旧构建；在明确 cutover 前它仍可制造新污染，因此 `deferred.md:139` 的「本代理再也不会产生」当前为假。

即使部署后，集合也只是 non-growing，并非 self-clearing：一个保存完整 rollout、失败后不推进也不裁剪历史的客户端会永久重发同一坏 item；这正是 D-8:126 描述的会话。

另有未充分展开的更窄方案：按实际 `rs_<canonical uuid4>_<index>` 而非「`rs_`＋任意＋数字」识别，并按 provider／显式 opt-in 限域。

当前建议材料系统性高估死代码、低估可持续污染。

### issue4-review-04（major）｜D-8 被停放在错误的权威层

`deferred.md:4` 明定需用户裁决的产品分叉进 Spec §11；`D-8:124、136` 自称产品分叉；`spec.md:491-503` 又明定 §11 收这类问题且当前只有 O-1。v16 却只从 `spec.md:3、511` 指到 deferred D-8，没有把它列入 §11。这是项目「Spec 级事实不得停在 deferred」规则的直接违背。

`pending-decisions-checker` 结论仍是「放行上桌」：是否为历史污染引入显式兼容 reshape 会改变外部请求，且旧会话价值只有用户知道；应修正材料并迁入 §11，不应由作者自行裁掉。

### issue4-review-05（major）｜报告诚实承认措辞分支未闭合，却随即把原始 issue 的因果说成不受影响

报告 `:94-96` 只证明同一 body 在 16:50 当前上游因 id mismatch 被拒，并不能证明 16:32 的 generic `resource not found` 来自同一分支；若上游行为／校验顺序在两次之间不同，原始那次可能先命中另一分支。

id 缺陷及修法已强到可行动，但「它就是 16:32 观测的根因」仍是高置信推断，不是直接观测。`§6:110-113` 应把这条精确负空间写明；`spec.md:3、297、511` 与测试 docstring `:2639` 的 issue-root-cause 措辞也应带同样限定。

### issue4-review-06（minor）｜两组全称过头

`test_pipeline_app.py:2643` 与 `spec.md:309` 的「nothing／任何观测看不出」不成立：代理若比较 upstream event 与交付 event，第一轮即可发现；正确限定是 first-turn 200／客户端在回放前看不到验证失败。

`test_pipeline_app.py:2643` 与 `spec.md:307` 的「no upstream／没有哪个上游会这么拼」也未被证据支持；代码链只足以证明本代理确实如此拼：`request.py:68` → `inference.py:326-330` → `delivery_policy.py:96` → `openai_responses.py:136、155-156`。

### issue4-review-07（minor）｜报告把 non-stream 原样返回定位错了文件

报告 `:112` 把 non-stream 原样返回定位在 `inference.py`，实际分支在 `src/app/pipeline/reply.py:18-31`，`inference.py:545` 只是调用。结论「未实测、按构造不经 framer」成立，文件归属错误。

## 逐句核 docstring

`response_id` 是代理 `uuid4` 为真，证据链见上；binding 对本次 Copilot 实测为真但不可无条件外推所有 upstream；「每个 later turn 都拒绝」是依赖继续重发坏 item 且上游规则不变的推断；「first turn 无人可见」为假全称；901,008-byte replay 与具体报文有报告 `:64-71、84-88` 支撑；native response path 不 mint 为真（`delivery_policy.py:56-71、95-98`；`passthrough.py:315-339`）；「pair travels as one」仅窄范围真；mutation 声称为真。

## 变异复核

baseline 1 passed；将 `carries_upstream_natively` 最终返回改 `False` 后，测试在 `test_pipeline_app.py:2672` 因 `rs_<uuid4>_0 != rs_1` 失败；快照覆盖还原后 `git diff --exit-code` 对 `delivery_policy.py` 为空，复跑 1 passed。

该变异恰当地证明测试能区分历史 translating route 与现 native response route，并击中旧 remint 机制；**不证明**真实 `added`／`done` 双 pair、下一轮 request、non-stream 或真实上游 200。

## Spec 权限与一致性

§2.3 明列 id policy 为 Spec 自己的推导，v16 新增的是实测事实及其对既有推导的补全，不改用户裁决，**未越权**；§6.2 仍保留客户端连续性兼容的取舍，新段只对 sealed pair 增加硬性正确性约束，是**补充而非推翻**。状态行把 main 的代码状态与 D-8 历史污染分开，除 D-8 权威落点问题外成立。

## 强词核验

报告 `:55` 的模型排除由同报告 `:58` 的 `gpt-5.6-sol` baseline 200 补强；`:58-60` 的「全部」仅覆盖列出的 singleton probes，文字已这样限定；`:75、86-88` 的 id 因果由同 body 删除 id 的对照与 fresh correct pair 的两轮正控支撑，足以针对当日 Copilot 行动；`:106` 的 1999／2／full-suite 本评审未重跑，不判伪；`:111` 的一次两轮样本限定诚实；`:112` non-stream 未实测限定诚实但文件写错。

最大未声明边界是上述 real event pair、request half、provider／time generalisation、原始 16:32 分支。

## 验证与排除

验证：`uv run pytest tests/int/test_pipeline_app.py -k sealed -q` → 1 passed, 148 deselected；变异 → 1 failed，精确失败在 id；还原后复跑同命令 → 1 passed；`uv run ruff check tests/int/test_pipeline_app.py` → clean；`uv run pyright src tests` → 0 errors。**未跑全量 pytest，未测 non-stream，未打真实 upstream。**

排除路线（纯推理排除，显式记下）：对象级断言不是问题；`response_id=uuid4` 不是错；Spec v16 补事实未越权；§6.2 新旧论述不矛盾；`False` mutation 不是不当，只是覆盖有限。

收尾：`delivery_policy.py` 已还原且无 diff，worktree 仅原测试文件为 `M`；`/tmp/260901-review-issue4-delivery_policy.py.snapshot` 保留，未执行未经授权删除。

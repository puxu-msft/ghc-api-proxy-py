# `spec.md`／`acceptance.md` 修订候选评审

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260820-spec-revision-candidate.md`。代码事实按当前工作树读取，Git HEAD 为 `f5c2e9f274bfd576ef58a8755561ac7e359c8bda`；规范事实以当前 `spec.md` 与 `acceptance.md` 为准；生产／上游事实只采用任务指定的两份 2026-08-20 证据报告。结论强度：以下 C1—C8 均由指定权威或当前代码直接支持，足以据此裁决候选；评审发现均为会使规范自相矛盾、遗漏可执行 oracle 或承诺无法兑现的 blocker／major。

## C1—C8 核验

### C1 — CONFIRMED

`src/app/pipeline/translation_driver/reasoning_carrier.py:111` 原文为：

```python
if not isinstance(document, dict) or document.keys() != _PROJECT_V1_FIELDS:
    return None
```

`_PROJECT_V1_FIELDS = frozenset({"tag", "encrypted_content"})` 见同文件 `:18`。这是精确 key 集合比较，任何新增成员都会使 v1 decode 失败；候选所说的 v1 不可原地扩展已确认。

### C2 — CONFIRMED

`docs/agents/anthropic-responses-bridge/spec.md:220` 原文为：「carrier 不编码 item id、model、upstream identity……新增字段或语义必须发布新 version，不能在 v1 payload 中静默扩展。」两项声称都准确。

### C3 — WRONG

`spec.md:204` 原文为：「item identity、resolved model 与 upstream identity 只能作为内部 typed facts 保存，不得塞进 carrier。」反对候选的最强理由是：identity 不等于字段名为 `id` 的上游标识；一个 response 内唯一指认某 reasoning item、并在回送时据此判断它是否被丢弃／重排／合并的 ordinal，本身就是 contextual item identity。`spec.md:220` 另行使用更窄的「item id」，说明 `:204` 的宽词并非只是 `id` 字段的同义反复；`spec.md:354` 又把 `reasoning semantic identity` 明定为内部 ledger 事实。候选一面用 `i` 识别 item，一面断言它不是 identity，属于为保留旧句而缩窄普通词义的 motivated reasoning；若用户要允许位置载体，必须同步修订 `:204` 或明确 carve-out，不能宣称原句不受影响。

### C4 — CONFIRMED

`spec.md:8` 的同一条 bullet 标题是「已裁决且不可重开」，正文明确写「reasoning signature 的 producer 固定使用本项目主 v1」。两项均确认。

### C5 — WRONG

候选对内容的概括基本正确，但引用范围不正确，因此整个 bundled claim 不能标为 confirmed。`spec.md:460` 原文要求达到全局压力线后「停止新准入或暂停……upstream 读取」；`:462` 原文禁止「超卖全局预算、无限等待、磁盘 spill 或 live forwarding」；`:467` 把 `global buffered bytes` 与「并发bridge数」列为必须可观测的限制类别。可是 `:468` 是空行，规则总句实际在 `:469`，调用前拒绝在 `:471`，不提交 partial block 在 `:472`，不 live forward 在 `:473`，稳定 Anthropic error 在 `:474`，清理在 `:475`；候选写成 `:468-473`，漏引了支撑其「稳定 error」概括的 `:474`。

### C6 — CONFIRMED

`acceptance.md:243` 确有前置条件 ``0 < request_budget < global_budget``。命令 `rg --line-number -e 'request_budget|global_budget' /home/xp/src/ghc-api-proxy-py/src` 返回 1，按显式分支记录为 `src search: 0 matches`。因此按当前代码不存在这两个配置键，该正确样本无法构造其明定配置，候选称它当前不可执行是正确的。

### C7 — CONFIRMED

`src/app/server/pipeline_app.py:391-394` 把 `InFlightLimit` 作为 app middleware 挂载；`src/app/server/admission.py:47-48` 先在 semaphore 的 `async with` 中取得名额，随后才调用内层 app。路由进入 `_serve` 后，`pipeline_app.py:224` 才调用 `handle_bounded`；`src/app/server/handler.py:190-195` 又是在该函数内部读取 `client_request_deadline` 并进入 `asyncio.timeout`。所以 admission gate 的等待发生在 deadline scope 外，排队时间不计入 `client_request_deadline`。这项结构结论足以行动；候选声称的具体 `0.30`／`0.35` 秒样本没有附命令输出，只能视为未单独核验的旁证。

### C8 — CONFIRMED

豁免一半由 `src/app/server/admission.py:22` 的 `UNGATED_PATHS = frozenset({"/health", "/health/liveness", "/health/readiness", "/metrics"})` 与 `:44-45` 的 bypass 分支确认。实际服务一半由 `src/app/server/ops_routes.py:30,36-37,74` 的四个 route decorator 确认，且 `src/app/server/pipeline_app.py:387` 确实 `include_router(ops_router)`。四条路径完全一致。

## Blockers

### B1 — carrier v2 没有对应的 `acceptance.md` 替换文本

- 候选只给出 REL-06 的 acceptance 重写方向，却在落地顺序中声称会同时修订甲＋乙；当前 `acceptance.md:36-37,108-111,141-144,439` 仍把项目 v1 exact bytes、v1 bare marker 与「默认只输出 v1」作为硬 oracle。
- 因此采用候选的 v2 spec 后，一个正确输出 v2 的实现仍会被冻结 acceptance 判红；这正是题目所问的 load-bearing 遗漏。
- 修订候选必须在交给用户前补齐 v2 producer vectors、v2／v1／upstream v1 识别顺序、`i` 判据、unknown／malformed 行为与 mixed-history oracle 的可直接采用文本。

### B2 — `i` 与仍保留的 `spec.md:204` 正面冲突

- 候选 `:120` 主张「位置不是身份」，但 `i` 的唯一用途正是区分同一 response 内的 item，并在回送时识别哪个 item 丢失、移位或合并。
- `spec.md:204` 禁的是宽义 `item identity`，`:220` 才另行禁窄义 `item id`；把前者偷偷缩成后者没有文本依据。
- 若用户裁决允许 ordinal 进入 carrier，必须显式覆盖 `:204`；保持原句不变会让新 v2 合同同时要求并禁止 `i`。

### B3 — 等待文本同时删除并保留「不得无限等待」，且仍违反既有有界合同

- 候选 `:28-34` 的替换明确把等待定为设计并删掉旧 `:462` 的「不得无限等待」，但 `:42-46` 又说该真实问题未裁决、未裁决前「不动这一条 spec」；两种动作不能同时采用。
- C7 已确认 admission 等待位于 deadline 外，故当前等待确实没有该 deadline 的上界；`spec.md:23` 又仍要求队列与时间均有边界。
- 在排队 deadline／取消／shutdown 语义获裁决前，候选不能把无上界等待写成已冻结替换文本；用户已裁决的是 waiting-not-refusing，不等于裁决了永不超时。

## Majors

### M1 — ordinal 序列不能兑现「检测丢弃／重排／合并」的全称承诺

- 原序列 `[0,1]` 若客户端丢掉末项，或把两个 thinking blocks 合并后保留第一项 signature，恢复序列都是 `[0]`，仍满足「从 0 起连续升序」，真实 corruption 会静默通过。
- `i` 还是 optional，bare marker 又无 payload，进一步使部分 item 没有可校验 ordinal；而多轮历史会反复从 0 开始，候选也未规定按哪个 assistant turn／response 分组校验。
- 该字段至多检测部分 prefix loss、inversion、gap 与 duplication；要么收窄 normative 承诺，要么补足能检测 suffix loss／merge 的计数或边界事实并定义分组。

### M2 — 「忽略未知成员」会把拼写错误和未来必需语义静默接受

- v2 表中只有 `tag` 必需，`encrypted_content` 与 `i` 均 optional；于是 `encrypted_contnet` 或 `I` 这类未知拼写会被忽略，并被成功降格成 summary-only／无 ordinal，而不是 malformed。
- 这也与仍被候选援引的「新增字段或语义必须发布新 version」相冲突：真正的 v3 会有 v3 prefix，v2 decoder 无须靠吞掉 v2 未知成员来读取它。
- 合同还未定义 duplicate key、producer 字段顺序、optional 组合的 canonical vectors 与 unknown 分类；在这些边界补齐前，它不是可冻结的 wire contract。

### M3 — consumer-first 正确，但「producer 单独成片以便回退」遗漏了不可安全回退窗口

- 新 build 按 block 解 v2→v1，因此同一 conversation 混有历史 v1 与新 v2 本身没有问题，这一点候选是对的。
- 但 producer 一旦把 v2 signature 交给客户端，回退到只认识 v1 的旧 build 会把其分类为 `project_unknown_version`，并按当前 `spec.md:246` 丢掉整个 thinking block；滚动部署中命中旧实例也一样。
- 所以最后切 producer 并不天然「便于回退」；候选必须说明旧 build 回读 v2 的兼容边界及 rollout／rollback 顺序，不能把可见字符串切换描述成普通可逆片。

### M4 — 残留清单计数错误且漏掉仍会承重的规范行

- 候选 `:24` 自称「其余 12 处」，实际列出 13 个 line number；其所指报告也未覆盖 `spec.md:530` 的外部验收条款：「global budget／queue 压力只产生普通 admission control、backpressure 或明确 capacity／timeout 终态」。
- `spec.md:23` 的「队列、并发、时间均有边界」也不是简单删掉全局 byte budget 就能自动满足，正与当前无 deadline 的 admission wait 冲突。
- 这些不是历史说明，而是目标／验收行为；若留在 adopted spec 中，正确实现仍面对互相冲突或已不存在的机制。

### M5 — 候选把推论写成「全部实测，非推断」

- `:67` 的全称标签过强：指定证据只证明所扫描样本中 894／894 与 3110 个事件的 `id` 形态，不证明所有未来 upstream reasoning item；观测范围 1—135 也不足以单独推出「多个 item 是常态」，因为没有给出大于 1 的频率分布。
- `:110` 的「拿它当身份从一开始就是错」只由 added→done 不稳定支持为「不能作跨 lifecycle correlation key」；另一报告 `:120-131` 反而记录 final id 被 10／10 原样回送且成功。
- `:45` 用「一天 429 个请求」推出 50 并发基本够不着，同样缺少峰值并发数据；日总量不能裁决 burst。上述句子须按证据能力收窄为 sample fact 或明确 inference。

## Verdict

**needs-fix。** Blocker 3，major 5。等待式准入与引入 v2 两项用户裁决本身不需重开，但当前候选不能作为可直接采用的规范修订：它遗漏 v2 acceptance、与 `item identity` 禁令冲突、尚未裁决 admission wait 的终止边界，并对 `i` 的检测能力与 v2 forward compatibility 作了过强承诺。

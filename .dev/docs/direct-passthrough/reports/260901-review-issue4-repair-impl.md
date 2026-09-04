---
report_id: issue4-repair-impl-review
attempt_id: issue4-repair-impl-review-1
status: in-review
reviewed_at_rev: 32ac0e0677acc1387e15dd0a79a9e2d7707bbe94
base_rev: fb5ed7f5ee1187ea2c1bd4d50474985637278d72
criteria_snapshot_sha256: 963ea7abeb62b45a6f4cb9e7303e566e7269d9d966b77c8eeb481522b00de1bd
---

# issue #4 已铸 reasoning id 修补实现独立评审

## 评审范围

被评对象是 `fb5ed7f5ee1187ea2c1bd4d50474985637278d72..32ac0e0677acc1387e15dd0a79a9e2d7707bbe94`，即 `b8e6f944db2b2fdb752ca518a96a2fb9a75baa92` 与 `32ac0e0677acc1387e15dd0a79a9e2d7707bbe94` 的最终提交态。规范判据先取自 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md` §6.5.1～§6.5.5，读取快照 SHA-256 为 `963ea7abeb62b45a6f4cb9e7303e566e7269d9d966b77c8eeb481522b00de1bd`；实测旁证取自 `reports/260901-issue4-sealed-reasoning-id.md`，快照 SHA-256 为 `09c11d4b5c6311bcfd2d524ba303ed50cc37ae8fed8c7b02f098d307231cb27c`；用户亲笔配置示例快照 SHA-256 为 `a79889a1ef430f1c4ab9ec387a1c543f8c3e15cb75c8632e03c6fdd12fbca8dc`。没有发真实上游请求。

评审开始时被评 worktree 干净。评审期间另一个写入者向 `tests/unit/pipeline/subscribers/test_minted_reasoning_ids.py` 加入了一条尚未提交的参数化用例；它不属于上述 reviewed revision，本报告涉及测试数量与行号时均以 `32ac0e0` 的提交态为准。与此同时，Spec §6.5 也被并行补入了真实 body 统计与 `rs_resp_…_N` 残余限制，当前文件 SHA-256 已变为 `37fab6da20af456154295b98c728adc4c1a544aaab5f004833df044a3b417245`；本报告的规范判断仍绑定开评时先读的 `963ea7…` 快照，不能把评审开始后的修改倒算进被评对象。我的两次受控变异分别只改了 `src/app/pipeline/subscribers/minted_reasoning_ids.py` 与 `src/app/config/schema.py`，均从逐文件快照还原，两个被变异文件的 `git diff --exit-code -- <path>` 都为空；全树 `git diff` 仍显示前述他人测试 WIP，因此不能诚实地声称全树为空。

## 总体 verdict

`needs-fix`。

blocker 数：0。major 数：3。minor 数：5。finding 总数：8。

## 发现

### issue4-repair-impl-review-01｜`major`｜所谓“精确笔迹”仍会误认非 `uuid4` 与带前导零的 index

- `finding_id`: `issue4-repair-impl-review-01`
- `severity`: `major`
- `primary_location`: `src/app/pipeline/subscribers/minted_reasoning_ids.py:21-24`
- `related_locations`: `src/app/pipeline/request.py:56-68`；`src/app/pipeline/delivery/formats/openai_responses.py:135-156`；`src/app/pipeline/delivery_policy.py:74-98`；`src/app/server/routes/inference.py:325-330`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:352-360`；`tests/unit/pipeline/subscribers/test_minted_reasoning_ids.py:54-87@32ac0e0`
- **我读到的事实**：生产入口 `build_context` 没有传 `RequestContext.id`，所以 `request.py:67` 的 `str(uuid4())` 是当前内建路径的来源；仓库内没有 `context.id = ...`，唯一生产 `ResponsesFramer` 构造位于 `delivery_policy.py:95-98`，其调用方在 `inference.py:325-330` 逐字传 `context.id`。`_item_id()` 在 `openai_responses.py:154-156` 只做字符串拼接。因此，已知历史生产路径产生的 UUID 部分一定是 version 4 且 RFC variant 合法，index 是 Python 非负整数的十进制 `str()`，不会有前导零。没有发现上游 `response.id` 流入 `response_id` 的路径；测试可以直接用任意 `response_id` 构造 framer，但那不是生产调用链。
- **我执行到的证据**：当前正则会删掉 `rs_00000000-0000-1000-8000-000000000000_0`，它是 version 1，不可能来自 `uuid4()`；也会删掉 `rs_136b08ff-f6b2-4b41-8f38-ae6d74eb7496_00`，而 `_output_index` 的 `str()` 不会生成 `00`。两个探针都实际得到 `removed=True`。
- **漏修方向的结论**：对当前仓库内建路径与已知历史污染集合，未发现漏修；`str(uuid4())` 的小写连字符形式与普通非负 index 都能命中。`ResponsesFramer` 作为可独立构造的类确实能在测试中发出 `rs_resp_test_0`，而 `RequestContext` 按契约又是可写记录，因此源码中“`_item_id` can actually emit and nothing else”以及“only possible author”是比已证生产路径更宽的全称，不能成立；这不等于已观测到另一类历史污染。
- **误伤方向的结论**：已证正则集合严格大于本代理已知生产铸造集合。真实 Copilot 新会话样本是无 `rs_` 前缀的不透明 base64，见实测报告 `:90-96`，所以本次证据足以排除当前 Copilot 正常新会话的碰撞；它不能排除另一个 upstream 合法使用 `rs_<uuid-like>_<index>`，而 Spec 自己正是用换 upstream 的误伤来论证必须“窄”。
- **为什么是 major**：用户裁决的承重限定是“窄形态”，实现与 Spec 都把判据解释为“只认本代理笔迹”，但集合并不相等；一旦碰撞，修补会删除本来有效的签发 id，制造本功能最要避免的正常会话破坏。
- **建议**：先修 Spec §6.5.1，把权威判据写成实际 `uuid4` 文本集合与无前导零的 index，再同步实现与反例测试。若坚持只用正则，UUID 第三组首位应固定 `4`、第四组首位应限制为 `[89ab]`，index 应为 `0|[1-9][0-9]*`；也可解析 UUID 后检查 version、variant 与规范化回写相等。Spec `:358` 的“`8-4-4-12`”还漏写了一组，标准分组本身是 `8-4-4-4-12`。

### issue4-repair-impl-review-02｜`major`｜实现没有执行 Spec 的 direct-leg 定义域，且用于省略门的理由与 translator 事实相反

- `finding_id`: `issue4-repair-impl-review-02`
- `severity`: `major`
- `primary_location`: `src/app/pipeline/subscribers/minted_reasoning_ids.py:43-56`
- `related_locations`: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:374-378`；`src/app/pipeline/driver.py:156-171`；`src/app/pipeline/translation_driver/openai_responses.py:561-582,732-756,865-901`
- **我读到的事实**：Spec `:376` 要求 `translation_required is False` 且 `inbound_format == openai-responses`。实现只检查 `target_format == OPENAI_RESPONSES`。其 docstring `:46` 声称 translated body 没有 Responses `input` 数组；但 `to_openai_responses()` 在 `openai_responses.py:877-880` 无条件创建 `input` 数组，`_reasoning_item()` 在 `:732-756` 还能在翻译腿上生成带 `encrypted_content` 的 reasoning item。
- **我执行到的证据**：用本项目自己的 reasoning carrier 构造 Anthropic thinking，再调用正式 `from_anthropic_messages()` 与 `to_openai_responses()`，得到 `input=[{"type":"reasoning",...,"encrypted_content":"seal-from-responses"}]`。把它置于 `inbound_format=ANTHROPIC_MESSAGES`、`target_format=OPENAI_RESPONSES`、`translation_required=True` 的 context 后调用 subscriber，确认它进入一个真实存在的 `input` 数组。当前 translator 不把任何 item id 写到这个 reasoning item 上，所以本探针观察到 `changed=False`；这排除了“今天已误删该标准翻译产物”，但不能挽救定义域与注释。
- **推断，明确标注**：当前 translator 若未来忠实携带某种 reasoning id，或增加另一条会产出 id 的 Responses translator，这个缺失的门会立刻把 direct-leg 兼容修补扩展到翻译腿；现有测试没有任何一条把 `translation_required=True` 且 inbound 为 Anthropic 放进反例组。
- **为什么是 major**：这不是实现细节偏好，而是 Spec 明订的作用域；实现靠一个已被源码与执行共同证伪的“构造性保证”绕过了两道门。用户要求的修补是窄且 opt-in，不能把“当前恰好没有 id，因此没有改动”当成定义域实现。
- **建议**：逐字实现 `context.translation_required is False` 与 `context.inbound_format is WireFormat.OPENAI_RESPONSES` 两道门，并加入翻译腿反例测试；删除“translated body has no input array”的错误说明，改为说明门直接来自 Spec 的产品定义域。

### issue4-repair-impl-review-03｜`major`｜canary skill 删除了错误 route override，却没有留下能证明 Anthropic→Responses 路径真的被测到的路由判据

- `finding_id`: `issue4-repair-impl-review-03`
- `severity`: `major`
- `primary_location`: `.claude/skills/real-copilot-backup-canary/SKILL.md:24-33,48-59`
- `related_locations`: `.claude/skills/real-copilot-backup-canary/SKILL.md:7-13,65-69`；`src/app/config/loading.py:1-6`；`src/app/config/loader.py:1-6`；`src/app/pipeline/routing.py:290-335`；`src/app/server/routes/ops.py:62-107`
- **我读到的事实**：skill `:9` 的目标明确包含 Anthropic-to-Responses，最小 canary `:58-59` 实际向 `/v1/messages` 发请求；但模型选择 `:50` 只要求 endpoint 集合包含 `/responses`，没有排除同时支持 `/v1/messages`，也没有检查最终 route。`routing.py:320-326` 会优先选 inbound endpoint，只要模型也支持 `/v1/messages` 就不会翻译。skill `:33` 又说需要测 Anthropic-to-Responses 时去 `AppSettings` 设置 `anthropic.route_override`；`config/loading.py:5` 与 `config/loader.py:1-6` 明载当前所有入口用 `ProxyConfig`，旧 `AppSettings` 没有 production caller，因此该建议对本 skill 启动的当前服务不生效。更直接的文本矛盾是 `:33` 用“canary posts to `/responses` directly”论证 override 不需要，而 `:58-59` 定义的 minimal canary 发的是 `/v1/messages`。此外，skill `:11` 把进程启动时间说成能说明代码有多旧，`:69` 要求记录两边 commits；但当前 `/api/status` 的实际 body 位于 `src/app/server/routes/ops.py:99-106`，不含 build revision，PID/start time/cwd/argv 也都不能唯一识别进程启动时加载的 commit。启动时间在已知提交发生于其后时可以证明进程不含那些后来提交，却不能恢复一个精确 commit；skill 没有给出取得运行中 commit 的可执行方法。
- **旁证及其权重**：解析仓库 cassette `tests/int/cassettes/anthropic_to_responses_stream.json` 中的 42 条模型目录记录，12 个支持 `/responses`，当时没有一个同时支持 `/v1/messages`；这足以说明该 cassette 快照下模型选择仍会走翻译腿，但只是一个 2026-08-20 左右的 point-in-time 目录，不能支撑一个长期 skill 省掉路由断言。
- **为什么是 major**：该 workflow 的核心 claim 是验证 Anthropic-to-Responses；在合法的未来目录状态下它会静默跑 direct Anthropic，却仍按 skill 的 verdict 声称翻译路径已验证。测试别的路径而报告目标路径通过，是 canary 的核心判别力失效。
- **建议**：选择 `supported_endpoints` 包含 `/responses` 且不包含 `/v1/messages` 的模型，并在请求完成记录或断言实际 route 的 `target_format`/`translation_required`，不要再把无 production caller 的 `AppSettings.route_override` 当当前服务的操作出口。若没有符合条件的模型，应明确判定该 canary 无法覆盖此路径，而不是退化为另一条腿。

### issue4-repair-impl-review-04｜`minor`｜int“控制组”同时换了 id 与开关，不能保护显式 opt-in 的配置默认值

- `finding_id`: `issue4-repair-impl-review-04`
- `severity`: `minor`
- `primary_location`: `tests/int/test_pipeline_app.py:2719-2779@32ac0e0`
- `related_locations`: `src/app/config/schema.py:389-395`；`tests/unit/pipeline/subscribers/test_minted_reasoning_ids.py:90-96@32ac0e0`
- **我读到的事实**：被称为 control 的测试 `:2733-2742` 在默认配置下发送 `id_003`；opt-in 测试 `:2762-2772` 同时把配置改为 true 并把 id 改成会命中的 `rs_<uuid>_0`。两者不是只差开关一个变量。单测 `:90-96` 直接把 `enabled=False` 传给函数，绕过 schema、composition 与 registry，不能替代配置接线控制。
- **我执行到的证据**：把 `FixResponsesRequestHook.repair_minted_reasoning_ids` 的 schema 默认值从 `False` 受控变异为 `True`，这两条 int 测试仍然 `2 passed`。因此它们不能区分“明确 opt-in”与“默认已开启”。schema 从快照恢复后该文件 `git diff --exit-code` 为空。
- **建议**：用同一个会命中的 poisoned item 做成 true/默认两条端到端测试，唯一变量是配置；默认组必须断言 id 原样到达 upstream。现有 `id_003` 测试继续承担 §6.4 正常签发 id 透传，不应冒充 §6.5 的 off-state control。

### issue4-repair-impl-review-05｜`minor`｜用户可见的 opt-in 键没有进入用户亲笔配置示例，也没有候选材料

- `finding_id`: `issue4-repair-impl-review-05`
- `severity`: `minor`
- `primary_location`: `docs/.human-controlled/config.example.yaml:596-600`
- `related_locations`: `src/app/config/schema.py:389-395`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:342-350`；`/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/`
- **我读到的事实**：schema 与 Spec 都把 `hook_fix_responses_request.repair_minted_reasoning_ids` 定义为具名、用户可见、默认关闭的开关；用户亲笔示例在同族 `hook_fix_responses_request` 下只列 `rename_call_id_as_fc_id`，没有新键。对 `.dev/human-controlled-docs-candidates/` 的搜索也没有找到该键。
- **判断**：配置落在 `ProxyConfig.hook_fix_responses_request` 与既有 request hook 同族，结构位置本身合理；缺口是用户面可发现性，不是 schema 归属。开发者不得改用户亲笔文档，因此正确处置不是直接补 `docs/.human-controlled/config.example.yaml`。
- **建议**：在 `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/` 提供一份最小候选补丁/片段，说明默认 false、只用于 `1fb37cd` 前污染历史及启用后的有意改写，交由用户自行摘取。

### issue4-repair-impl-review-06｜`minor`｜subscriber package 仍全称宣告 built-ins 不可配置，与本功能的显式开关直接矛盾

- `finding_id`: `issue4-repair-impl-review-06`
- `severity`: `minor`
- `primary_location`: `src/app/pipeline/subscribers/__init__.py:4-7`
- `related_locations`: `src/app/pipeline/subscribers/__init__.py:54-65,98-105`；`src/app/config/schema.py:389-395`；`src/app/server/composition.py:543-557`
- **我读到的事实**：package docstring 仍说 built-ins “Not configurable, on purpose”，并把 protocol repair 全称描述成 mandatory sanitizer；同一文件新增的注册函数参数 `repair_minted_reasoning_ids_enabled=False` 与 lambda 却明确受配置控制，schema 和 composition 也完整接上了 `hook_fix_responses_request.repair_minted_reasoning_ids`。Spec §6.5 要求它必须显式 opt-in，所以实现是对的，package 的架构说明已经错。
- **影响**：这不会改变运行行为，但会把下一位读者送向相反的配置模型，也使“既有 built-in 是否允许有开关”出现两个权威答案。
- **建议**：把 package 总述收窄为“默认的 protocol sanitizers 通常是 mandatory；显式列出的 compatibility reshapes 可由各自 Spec 定义 opt-in”，并回指 §6.5，不能继续保留不可配置的全称。

### issue4-repair-impl-review-07｜`minor`｜§6.5.5 的“长期为零就提出退役”没有可判定的零、时间窗或触发者

- `finding_id`: `issue4-repair-impl-review-07`
- `severity`: `minor`
- `primary_location`: `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:380-388`
- `related_locations`: `src/app/pipeline/subscribers/minted_reasoning_ids.py:58-70`；`tests/unit/pipeline/subscribers/test_minted_reasoning_ids.py:129-139@32ac0e0`
- **我读到的事实**：实现仅在 `repaired > 0` 时写一条 `logger.info`，包含本请求正命中数。这足以满足 §6.5.4 的最低要求“修补过的请求至少记下修补数”，相应 caplog 测试也确实能读到 `2`；因此我不把 `logger.info` 本身判为不足。
- **为什么 §6.5.5 不可执行**：没有零命中日志或累计 metric，日志缺席无法区分“功能启用且有足量流量但零命中”“功能未启用”“没有流量”“INFO 未收集”；“长期”没有时间窗或请求量门槛；也没有谁在何时检查、由什么事件触发“提出退役”。因此当前只有正命中能被观察，生产长期为零这个前提没有 oracle。
- **建议**：Spec 先定义可证伪的复查条件，例如明确启用状态、观察窗口或最小请求量、正命中累计值、数据来源与复查责任/时点；实现再提供足以区分上述缺席状态的简单计数来源。不要把“没有看到 INFO”当零。

### issue4-repair-impl-review-08｜`minor`｜若干 measured/only/any 句子把推断、未知位置或词法前缀写成了已证全称

- `finding_id`: `issue4-repair-impl-review-08`
- `severity`: `minor`
- `primary_location`: `src/app/pipeline/subscribers/minted_reasoning_ids.py:4-8`
- `related_locations`: `src/app/config/schema.py:389-395`；`tests/unit/pipeline/subscribers/test_minted_reasoning_ids.py:1-3,14,80-82,130-144@32ac0e0`；commit `32ac0e0677acc1387e15dd0a79a9e2d7707bbe94` message；`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/reports/260901-issue4-sealed-reasoning-id.md:47-51,69-82`
- **`correct id exists only inside the sealed blob`**：实测报告能证明的是 reasoning carrier 只保存 `encrypted_content`、原始 upstream id 已丢失，不能证明 id 作为可恢复字段“存在于 blob 内”；绑定也可能通过 authenticated associated data 或 upstream 侧状态实现。若该前提为假，“本代理无法重建正确 id，因此选择删除”仍由“没有保留原始 id”独立支撑，所以这是错误的地点声称，不推翻修法。应改成“本代理没有保留且无法从现有字段重建 upstream id”。
- **`Measured ... any mismatched id is a 400`**：报告 `:71-78` 实际测了三个不匹配 id，不是任意集合。错误消息与绑定语义使“任意不相等值都会失败”成为强推断，足以指导修补，但不能在 `Measured` 后伪装成全称观测。应写成“三个不同不匹配 id 均 400；错误逐字说明 item_id mismatch”。
- **“宽形态会删一个 legitimate id”**：现有证据证明 OpenAI reasoning id 使用 `rs_` 前缀，却没有提供一个既合法又实际匹配 `rs_.+_[0-9]+` 的正样本；仅有前缀不足以推出会命中带尾部 index 的宽正则。受控变异中变红的两条是合成的 `rs_not-a-uuid-at-all_0` 与大写 UUID，它们精确编码了用户排除宽形态的裁决，但没有证明这两个 id 是 upstream 接受的正常会话 id。用户裁决本身足以要求测试变红，不需要借一个未举证的真实误伤来增强它。
- **`no amount of upgrading changes that` / `permanently`**：代理升级本身不会改客户端既有 history，这一窄读成立；客户端升级若迁移、裁剪或重建 history 则可能改变。应把主语写成“只升级本代理不会自愈”，不要写没有主语的绝对句。
- **`no new item of this shape can be produced`**：已证的是 `1fb37cd` 后 direct Responses→Responses 生产腿不再经过该 framer。`ResponsesFramer` 类本身仍能从带本项目 carrier 的 `CompletedBlock` 生成同形 sealed item；我执行该构造实际得到 `rs_<uuid>_0` 加 `encrypted_content`。我没有找到当前 production 路由会把这种 block 送到该 framer 的事实，因此这里应收窄成已证生产腿，而不能反向宣称已发现集合仍在增长。
- **测试 docstring 的两个过头点**：文件开头说断言了“default”，实际只直传 `enabled=False`，见 finding 04；`:80-82` 说每一种漏判方式都有 case，version/variant/前导零均没有，见 finding 01；`:143-144` 把无 `input` context 归作 embeddings/count-tokens，但 embeddings 的 `target_format` 不是 Responses，而 Anthropic→Responses count translator 在 `openai_responses.py:877-880` 总会建立 `input`。该测试仍可作为 malformed direct Responses body 的不崩溃检查，例子应换成真实路径。

## 测试鉴别力逐组结论

`32ac0e0` 提交态共有 14 个 unit case（一个正例、八个参数化反例、五个独立行为 case）与本提交新增的一个 int case；用户点名的 pre-existing request-half int case另算一条 control。没有一条是无论实现怎样都会通过的数学恒真式，但多条测试的名字或 docstring 声称了它没有观察的层。

| 组 | 真正能判什么 | 看不见什么 |
|---|---|---|
| 正例整对象相等，`test_a_minted_id_on_a_sealed_item_is_removed_and_nothing_else_is` | 命中时只删 `id`，seal、summary、type 保留 | 判据是不是过宽；配置与接线 |
| 八个参数化反例 | 分别能挡住前缀过宽、非 UUID 宽形态、大写、非 fullmatch、无/空 seal、错误 type、非 dict；每个都有可使其变红的实现破法 | 不含 UUID version、variant、index 前导零；“everything”不是穷尽 |
| `enabled=False` unit | 函数参数为 false 时不改 body | schema 默认值、composition 是否传对，见 finding 04 |
| 非 Responses target unit | 保留 `target_format` 这道门 | Spec 要求的 inbound 与 `translation_required` 两道门；它反而把错误实现门写成了 oracle |
| 多 item unit | 不只处理第一个命中项 | 混合数组里的非命中 dict 是否仍保留自己的 `id`；其他反例分开覆盖了后者 |
| caplog unit | 正命中时 INFO 文本含正确数量 | 零命中、生产 logger 配置、§6.5.5 的长期零 |
| 无 `input` unit | malformed direct context 不崩溃 | docstring 所称 embeddings/count-tokens 真实路径并未构造 |
| 新增 int repair case | `ProxyConfig` override → composition → registry → `attempt.prepare` → upstream bytes 的正接线成立 | 默认关闭；谓词反例；response `200` 由 fake 固定，真正 oracle 是 `seen[-1].content` |
| pre-existing sealed passthrough int case | 默认配置下合法 `id_003` 与 seal 原样发出 | 因 id 本来不命中，即使默认开关错误地为 true 也不变，不能充当 opt-in control |

用户指定的宽判据变异把正则改成 `rs_.+_[0-9]+\Z`。当前 worktree 因他人新增一条未提交参数 case 共收集 17 项，结果 `2 failed, 15 passed`；扣除那条不属于 reviewed revision 且仍通过的 WIP case，提交态对应结果是 `2 failed, 14 passed`。红的恰是 `rs_not-a-uuid-at-all_0` 与大写 UUID 两条；它们确实编码“不要放宽为该正则”的用户裁决。两个 int case都仍绿，所以这次变异只验证 unit predicate 反例，不验证接线。反向缺口同样明确：version 1、错误 variant、前导零 index 都没有测试，finding 01 的两个实际探针会被当前实现误删。

另一次控制变异把 schema 默认值改成 true，两个 int case仍 `2 passed`，证实所谓 control 不能约束显式 opt-in。两次变异都用逐文件 snapshot 还原，没有使用 `git checkout`；被变异的两个源文件逐文件 `git diff --exit-code` 都为空。

## 已确认成立而不列为发现的路线

- **正常 Copilot 新会话没有撞当前正则**：实测报告 `:90-96` 的流式与非流式样本都使用上游无 `rs_` 前缀的不透明 base64 id；这是两个同 provider、同模型、同日样本，强到足以排除本次已测正常会话，不能外推所有 upstream 或永远不变。
- **没有发现 upstream response id 流入历史 `_item_id()`**：生产 `ResponsesFramer` 只有一个构造点，调用链传的是 `RequestContext.id`；production `RequestContext` 又只走默认 `uuid4()`，仓库没有赋值写回。历史 `1fb37cd^` 的对应调用仍是 `message_id=context.id`。这足以否决“已知污染其实还有 upstream response-id 形态”这一疑问；可写 `RequestContext` 或直接构造 framer 的外部扩展不在已观测历史集合内。
- **处置字段正确**：命中循环只 `del item["id"]`，正例以整个 item 相等断言 seal 与其余字段不动；int 断言落在 fake upstream 实收字节上，满足 §6.5.2 与 §6.5.3 的发送前观察面。
- **配置归属正确**：`ProxyConfig.hook_fix_responses_request` 与现有 request hook 同层，默认 false，composition 逐字传入 registry；问题只是文档可发现性与控制测试，不是配置放错 section。
- **§6.5.4 的当次可观测最低线成立**：只有修过的请求才负有该节的日志义务，当前 INFO 包含实际 repair count；我没有把“必须是 metric”倒灌进该节。metric/denominator 的需要来自另一个命题——§6.5.5 要证明长期零。
- **`b8e6f94` 的三项原修正各有事实基础**：`--account-type` 已不在当前 CLI；未配置时 token 路径由 `github_token_path()` 生成 `github_token-<provider>.txt`；当前 `--config` 走 `ProxyConfig`，放 `anthropic.route_override` 会被 extra-forbid。finding 03 不是要求恢复旧写法，而是指出删掉错误 override 后缺少等价的实际路由证明。

## 搜索面与执行证据

读取并逐处比对了两条提交的最终 diff 与 commit message、全部八个 changed files、Spec §6.5.1～§6.5.5、issue 实测报告 §2～§6、用户配置示例、`RequestContext`/inbound 构造、driver 与 direct-driver、routing、delivery policy、Responses framer、Anthropic→Responses translator、legacy/current config loader、status endpoint以及相关测试。用 `git show 1fb37cd^` 检查历史 mint 调用，用仓库级搜索核 `RequestContext.id` 写入点、所有 `ResponsesFramer`/`framer_for` 调用点和 repair 配置引用。

执行结果：目标测试 baseline 在含一条并行 WIP case 的当前树上 `17 passed`；宽正则变异 `2 failed, 15 passed`；默认值变异的两条 int `2 passed`；还原后 `uv run ruff check src tests` 通过，`uv run pyright src tests` 为 `0 errors, 0 warnings, 0 informations`，全量 `uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80` 为 `2016 passed, 2 skipped`、coverage `90.87%`。全量运行包含并行写入者新增且通过的一个参数化 case，因此相对 `32ac0e0` 会多收集一项；绿灯不改变上述集合、作用域与 test-oracle 缺陷。

明确未覆盖：没有打真实 upstream；没有操控或探测生产 `4141`；没有运行会发真实请求的 canary skill；没有从 OpenAI primary API 取得一个实际匹配 `rs_.+_[0-9]+` 的合法 id，因此对该真实误伤的声称保持未验证；没有审两提交之外的产品功能。TUI 组依项目默认不在本次 pytest sweep，且与该 request subscriber 无关。

## 我最没把握的三个判断

1. **finding 02 定为 major 而非 minor**：当前 translator 的 reasoning item 不带 id，所以已执行反例只证明 subscriber 越域运行、没有证明今天会改写翻译产物；我仍定 major，因为 Spec 的显式定义域被省掉且省略理由已证伪，未来正常扩展会在没有新门的情况下变成数据改写。若调用方严格只按今日可观察损害定级，可重判为 minor，但事实与修复要求不变。
2. **finding 03 定为 major**：记录 cassette 当前没有 dual-endpoint 模型，所以今天按现有目录挑一个 Responses 模型通常仍能走翻译；我按 canary 的长期核心 claim 定 major，因为流程没有 oracle，目录一变就会把另一条腿冒充通过。若该 skill 明确只服务固定目录快照，级别可降，但它现文没有这个限定。
3. **finding 08 对“仍能产出同形 item”的限定**：我证明了 `ResponsesFramer` 类仍可构造该 pair，却没有找到当前 production 路由把 proxy-carrier block 送给它；所以只要求收窄全称，没有把它升级为“§6.5 集合正在增长”的行为发现。

## 执行本契约时遇到的摩擦

`my-skills:as-reviewer` 未注册到当前 Skill 工具，首次调用返回 unknown skill；我在读取任何被评对象前定位并读取了其 canonical 本地定义 `/home/xp/.claude/my/my-agents/skills/as-reviewer/SKILL.md`。worktree 隔离策略拒绝 `Write` 直接写主树 `.dev`，而项目与用户都明确要求报告落在只存在于主树的独立 `.dev` 仓库；因此报告先增量写入 `/tmp/260901-review-issue4-repair-impl.md`，再用简单 `cp` 同步到指定路径。评审中另有写入者并行修改 unit test 与 Spec，已按 revision/hash 钉住边界，没有覆盖或回滚其内容。

## 收尾状态

最终冻结仍为分支 `worktree-260901-issue4-repair-minted-ids`、HEAD `32ac0e0677acc1387e15dd0a79a9e2d7707bbe94`；feature worktree 唯一 diff 是另一写入者的 `tests/unit/pipeline/subscribers/test_minted_reasoning_ids.py`，本评审没有暂存、提交、合并、push、删除 ref 或结束 worktree。指定报告已装到 `.dev` 独立仓库路径，但本 leaf 没有在共享 `.dev` 仓库提交它。`/tmp` 下本轮自己的 probe、两个 snapshot 与报告中转副本均未删除，因为 leaf 不能派独立 manifest reviewer；它们的结论已经提炼进本报告，留待 harness 过期。当前角色受 leaf 约束不能派 report reviewer，因此报告保持 `status: in-review`；调用方需要先核报告本身，再处置 findings。

本轮可复用候选有两条，均已登记在报告而未擅自改 rule/skill：精确识别“某 producer 的集合”时要同时约束 UUID version/variant 与整数的词法规范；验证跨协议 canary 时必须断言实际 route，不能由模型支持列表间接推定。它们都有本次实例，但是否上升为通用资产由调用方决定。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-09-01T19:01:29Z`
- `finding_total: 8`
- `blocker: 0`
- `major: 3`
- `minor: 5`
- `nit: 0`

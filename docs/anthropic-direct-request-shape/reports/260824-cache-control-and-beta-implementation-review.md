---
report_id: cache-control-and-beta-implementation-review-260824
attempt_id: independent-review-gpt56sol-1
status: in-review
reviewed_at_rev:
  main_head: 2c4ba5928c5f9ea1937a87b35b47c71d83d5c5d0
  main_scoped_bundle_sha256: f9072385a77de99f10aa56125cfd58ba3745a9006da1353f0ef7ad1c49646607
  dev_head: 4c0ac095089816dc46e36bec08e1bebdbe1c5877
  dev_scoped_diff_sha256: c3bd0e8f734f4496a5a4da60c2ad2ed1291675d74a9085d9d64c1c6e3d91e3d1
  evidence_report_sha256: 4d1699d1da53cae3a36b3a6e572a8eb5f54567346b91621437ab992575491dd9
reviewed_at: 2026-08-24T19:00:35+00:00
---

# `cache_control` 与 gateway beta 实施评审

## 评审范围

本次只评任务点名的未提交增量：`src/app/pipeline/subscribers/anthropic_cache_control.py`、`src/app/pipeline/subscribers/__init__.py`、`src/app/pipeline/request_headers.py`、`src/app/pipeline/driver.py`、`src/app/pipeline/translation_driver/semantic.py`、两份 subscriber 测试、两份 request header 测试增量、`exp/260824-beta-and-cache-control-probe/`、`.dev/docs/anthropic-direct-request-shape/spec.md`、`status.md` 与 `reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md`。

`docs/.human-controlled/config.example.yaml` 与 `message-translation.md` 的并行修改只作为最高权重判据读取，不评、不改。Docker、其他实验、其他 worktree、其他 `.dev` 报告均不在评审对象内。为核对重编号波及，额外只读检查了同 topic 的 living index 与 `.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md`；这两份文件不是被评实现，但其被本次重编号弄旧的引用列为 related location。

## 总体判定

**Verdict：needs-fix。Blocker：1。发现：7 项，其中 blocker 1 项、major 2 项、minor 4 项。**

两个线上样本的直接修复路径确实接上了：`system[]`／一层 `messages[].content[]`／`tools[]` 上的 `scope` 会被删，`tool-search-tool-2025-10-19` 会在真实 `shape_request` 路径被剥；目标测试 60 项通过，项目规定的 Ruff 与 Pyright 也通过。可是默认 `passthrough` 下无条件删 `scope` 与用户亲笔的“as-is”及 `sanitize` 专门负责剥 `scope` 的四档定义直接冲突，而 Spec 自己也承认尚待用户追认；这个未决点不能由较低权重 Spec 的“断点／词汇表正交”解释覆盖。另有两个关键缺口：白名单没有覆盖当前 Messages API 的顶层自动缓存和 `tool_result.content[]` 等嵌套 cacheable block，gateway beta 行为则尚无规范条款且把单一 enterprise host 的测量无条件施加到所有可配置 host。当前候选不应进入下一阶段。

## Blocker findings

### CCBIR-01：默认 `passthrough` 被无条件改写，直接绕过用户亲笔的四档语义

- `finding_id`：`CCBIR-01`
- `severity`：`blocker`
- `primary_location`：`src/app/pipeline/subscribers/anthropic_cache_control.py:84-96`
- `related_locations`：`docs/.human-controlled/config.example.yaml:474-483`；`src/app/config/schema.py:343-345`；`.dev/docs/anthropic-direct-request-shape/spec.md:4-7,305-312,339-340`；`.dev/docs/anthropic-direct-request-shape/status.md:77-84`
- 具体失败场景：使用默认配置 `hook_fix_anthropic_request.cache_control: passthrough`，客户端在 `system[]` 发 `{"cache_control":{"type":"ephemeral","scope":"organization"}}`。最高权重文档把 `passthrough` 定义为“forward client cache_control as-is”，并把“strip non-standard fields like scope”明确放在另一档 `sanitize`；当前 subscriber 不读取该配置，只按 `target_format` 无条件删除 `scope`。
- 实际结果：我运行本地探针，`ProxyConfig().hook_fix_anthropic_request.cache_control` 为 `passthrough`，working payload 的三处 marker 均从 `{type,scope}` 变成只含 `{type}`；这不是仅在 `sanitize` 下发生。原始请求副本保持不变，说明问题不是意外 alias，而是明确的默认行为选择。
- 判据：用户亲笔文档是本任务的最终权威。Spec §7.3 提出的“那句话只管断点位置，不管对象词汇”是 agent 的新解释；同节下一段与 A-8 已经准确承认，用户原话没有明示该区分、仍需追认。较低权重文档不能一边标成未决，一边让实现先采用其中一侧。
- 证据强度：**强到可据以行动。** 配置默认值、subscriber 签名和实跑结果共同证明默认档被改写；权威冲突来自逐字条款，不依赖我对上游的猜测。阻断的是“能否按现状进入下一阶段”，不是否认剥 `scope` 能修掉已测 400。
- 建议：在合入前由用户明确裁定二选一。若用户重定义 `passthrough` 为“保留断点位置与数量，但允许网关词汇消毒”，先更新 human-controlled authority，再保留常驻行为；若 `as-is` 按字面成立，则 subscriber 必须接入四档并只在获授权的档位改写，同时由用户决定默认档面对该 400 的产品行为。不要用当前 Spec 自己提出的解释代替裁决。

## Major findings

### CCBIR-02：所谓“每一个 `cache_control`”只走了三条浅层路径，漏掉顶层自动缓存和合法嵌套块

- `finding_id`：`CCBIR-02`
- `severity`：`major`
- `primary_location`：`src/app/pipeline/subscribers/anthropic_cache_control.py:68-81,98-123`
- `related_locations`：`.dev/docs/anthropic-direct-request-shape/spec.md:283-295`；`tests/unit/pipeline/subscribers/test_anthropic_cache_control.py:44-76,123-145,214-246`；已安装官方 SDK 生成类型 `.venv/lib/python3.14/site-packages/anthropic/types/message_create_params.py:128-132`、`tool_result_block_param.py:17-35`、`search_result_block_param.py:14-26`、`content_block_source_content_param.py:7-12`；[Anthropic Messages API reference](https://platform.claude.com/docs/en/api/messages)
- 具体失败场景：合法 Messages 请求在顶层使用自动缓存 `cache_control`，或在 `messages[].content[]` 的 `tool_result.content[]` 文本块上放 marker，并带客户端的 `scope`。当前 `_prune_blocks` 只检查外层 block 自己，主函数也不检查 `payload["cache_control"]`，因此两个 `scope` 都原样到 wire；若 Copilot 对这些位置复用已测的 strict `CacheControlEphemeral` schema，请求会继续得到 `Extra inputs are not permitted` 400。
- 实际结果：我用同一个 context 同时放入顶层 marker 与 `tool_result.content[0]` marker，调用 `prune_cache_control_fields` 后，两处仍逐字保留 `{type:"ephemeral",scope:"organization"}`，且没有记录任何 loss。这个“实现未覆盖”已实跑确认；这些位置上的 `scope` 是否在当前 enterprise gateway 得到同形 400 没有重新发真实请求，是基于同一官方 schema 与已测 strict 拒绝的强推断，不冒充实测。
- 外部契约：当前官方 API reference 明列 request 顶层 `cache_control`，并明列 `tool_result` 外层与其 `content` union 中的 `TextBlockParam`、`ImageBlockParam`、`SearchResultBlockParam`、`DocumentBlockParam`、`ToolReferenceBlockParam`、`BrowserStateBlockParam` 均可带 `cache_control`。`search_result.content[]` 及 `document.source.content[]` 还形成更深嵌套。相反，`thinking` 与 `redacted_thinking` 不允许直接带 `cache_control`，所以 thinking 不是遗漏的第四处。
- 证据强度：**实现遗漏强到可据以行动；具体 gateway 400 为有明确依据但未实测的推断。** 官方 live schema、该环境中由 OpenAPI 生成的 SDK 类型与本地反例一致。当前 Spec 的“三处位置都要覆盖”不是 API 全集，且与同段“每一个对象”的全称自相矛盾。
- 建议：先把 Spec 的位置集合改完整，再按 schema-aware traversal 覆盖顶层和所有合法嵌套 cacheable block。不要对任意 dict 做盲递归，否则会误删 `tool_use.input`、工具 JSON Schema 或普通 tool output 数据中恰好名为 `cache_control` 的业务字段。增加顶层、外层 `tool_result`、嵌套 `tool_result.content[]` 三个最小判别用例；需要覆盖更深 union 时从官方请求 schema 派生清单。

### CCBIR-03：gateway beta 的新外部行为没有规范条款，且实现范围超过实测条件

- `finding_id`：`CCBIR-03`
- `severity`：`major`
- `primary_location`：`.dev/docs/anthropic-direct-request-shape/spec.md:321-342`
- `related_locations`：`src/app/pipeline/request_headers.py:22-36,128-137`；`src/app/pipeline/driver.py:101-121`；`.dev/docs/anthropic-direct-request-shape/status.md:16-18,77-85`；`.dev/docs/anthropic-direct-request-shape/reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md:4-7,48,94-99`；`src/app/server/composition.py:332-344,381-393,407-443`
- 具体失败场景：客户端向任一可配置 Copilot API base URL 发送 `anthropic-beta: output-128k-2025-02-19` 或 `tool-search-tool-2025-10-19`。当前 generic pipeline 不看 provider、base URL、账号类型或已测 deployment，都会删除；但 Spec 的规范范围仍只列 body 字段，唯一提到该机制的 A-10 反而写“机制上还没分开”，同时 status 又写已经落地。维护者按 Spec 实现另一入口或重构 header path 时，会合理地不复制这条未定义规则；另一个 host 若接受并依赖其中一个 flag，当前实现则会在没有对应测量的情况下静默拿掉协商。
- 实际结果：代码层面“对所有 Anthropic inbound 的 direct path 无条件删”已由调用链核实；证据报告明确把测量限定为 `api.enterprise.githubcopilot.com`、`claude-opus-5`、非流式，项目当前又允许由账号探测或 `api_base_url` 选择不同 host。其他 host 是否真的接受或需要这些 flag **未验证**，所以我不把条件性运行时后果冒充已发生；确定缺陷是 observable behavior 没有 normative owner，且测量限定没有进入行为边界。
- 判据：项目纪律要求完整 behavioral Spec 先于实现，Spec 级事实不得只落在 report、status 或代码注释。A-10 是待裁／延后条目，不是条款，而且其“还没分开”与同一工作树的实现相反。
- 对“两个清单是否只是话术”的判断：**不是话术。** gateway vocabulary 与 per-model capability 的错误信封、判定主体和 key 维度确实不同；把 gateway 固有拒绝项塞入用户的 per-model 表会混淆两个命题。我接受“并列机制”这一架构方向。缺的是该机制本身的规范、适用 provider／deployment 范围、staleness 行为与 exact list owner，不是要求把它们重新合并。
- 证据强度：**Spec bypass 与当前全局调用范围强到可据以行动；跨 host 的行为差异未决。** 若所有 GitHub Copilot hosts 有一份被项目承认的统一 gateway vocabulary 契约，补上来源即可收窄这一 finding；现有单 host 实测不具备这个量词。
- 建议：在实现之前的 living Spec 中新增 beta vocabulary 正文条款，写清 exact list、适用 provider／base URL 范围、谁能更新及过期时行为，并把 A-10 从“尚未分开”迁出 open 表。若无法取得跨 host 契约，至少把行为约束到已测 gateway，或将其作为 provider capability 而不是 generic inbound-format rule。

## Minor findings

### CCBIR-04：Spec 要求逐处记录 loss，实现和测试却把多处删除聚成一条且不保留路径

- `finding_id`：`CCBIR-04`
- `severity`：`minor`
- `primary_location`：`src/app/pipeline/subscribers/anthropic_cache_control.py:125-130`
- `related_locations`：`.dev/docs/anthropic-direct-request-shape/spec.md:295-297`；`tests/unit/pipeline/subscribers/test_anthropic_cache_control.py:109-120`
- 具体失败场景：一个请求在 `system`、message block 与 tool 各带一个 `scope`。Spec 说“每一处删除记一条 loss”，实际三处全部改写后只有一个 `Loss`，detail 只有 `3 marker(s)` 和字段名，没有三个路径；请求记录的读者无法判断哪些断点被改变，也无法满足条款的 cardinality。
- 实际结果：本地探针输出 `loss_count 1`，第二次运行后仍为 `1`；现有测试也明确断言三处删除对应一个 loss。幂等性正确，第一次的记录粒度不符合 Spec。
- 证据强度：**强到可据以行动。** 这是规范文字、代码 append 次数和运行输出的直接对照。
- 建议：要么按每个 `(path, field)` 记录独立 `Loss`，要么若聚合才是想要的契约，先把 Spec 改成“一次 pass 聚合一条”并说明路径是否必须保留；不要让测试把当前实现反向写成规范。

### CCBIR-05：关键策略仍有四组“实现正确但测试可静默退化”的绿

- `finding_id`：`CCBIR-05`
- `severity`：`minor`
- `primary_location`：`tests/unit/pipeline/subscribers/test_anthropic_cache_control.py:19-170,214-246`
- `related_locations`：`tests/unit/pipeline/test_client_request_headers.py:378-509`；`tests/unit/pipeline/subscribers/test_builtin_subscribers.py:36-57`；`src/app/pipeline/subscribers/anthropic_cache_control.py:27-28,84-123`；`src/app/pipeline/request_headers.py:33-36`
- 具体失败场景一：把白名单实现退化成“只删 `scope`”的 blacklist，当前 cache tests 仍全绿，因为唯一未知键始终是 `scope`；下一个客户端字段到来时会穿过并触发 strict-schema 400。
- 具体失败场景二：从 `GATEWAY_UNSUPPORTED_BETAS` 删除 `output-128k-2025-02-19`，当前 tests 仍全绿；带该 flag 的请求重新得到已测 gateway 400。全仓测试对这个新增 tuple 成员零命中。
- 具体失败场景三：把 guard 从 target format 误改成 inbound Anthropic，当前正向 tests 仍绿，因为所有会执行 sanitizer 的 context 都是 Anthropic inbound；一个 Responses → Anthropic 请求上的 marker 将逃过修复。现有 Responses-target test只覆盖负向半边。
- 具体失败场景四：给 sanitizer 增加 `COUNTING_ONLY` 早退，当前新测试仍绿；`/v1/messages/count_tokens` 带 `scope` 时会把不可发送 body 交给上游。built-in 的 count 测试没有 cache marker。
- 已有分辨力：作者给出的“删除 subscriber 注册”和“删除 driver gateway strip 调用”两次变异与测试结构相符，我沿用其结果；幂等测试会抓重复 loss，Responses target 的负向 guard 会抓无条件运行，`ttl` 用例会抓误删已接受键。这些绿不是全无价值。
- 证据强度：**前三组由测试输入全集与符号零命中静态确认，第四组由 count 测试输入确认；本轮没有在共享工作树实施新 mutation。** 这条只指测试回归分辨力，不指控当前对应分支的生产实现错误。
- 建议：各补一个最小判别输入：未知键不用 `scope`；逐项断言 tuple 的两个成员；非 Anthropic inbound 但 Anthropic target 的正向组成；真实 `handle_count_tokens` 携带 marker。不要扩大成穷举矩阵。

### CCBIR-06：§7 插入后的 living 引用仍有旧编号，A-10 的状态引用又与实现相反

- `finding_id`：`CCBIR-06`
- `severity`：`minor`
- `primary_location`：`.dev/docs/anthropic-direct-request-shape/status.md:16-18,77-85`
- `related_locations`：`.dev/docs/anthropic-direct-request-shape/spec.md:328-342`；`.dev/docs/anthropic-direct-request-shape/reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md:94-99`；`.dev/human-controlled-docs-candidates/anthropic-thinking-capability.md:143-153`
- 具体失败场景：读者从 status 的 beta 实现行跳到 `spec §9 A-10`，看到的却是“机制上还没分开”且仍列在待裁／延后表；用户从 candidate 第 145 行按“Spec §8 编号”查 A-1～A-6，会落到“## 8. 不做什么”而非当前 §9；新 evidence report 第 97 行说“spec §7 与 A-4”，但相关的 per-model table owner 在当前 §8 与 §9 A-4。读者会把已实现项当未实现，或沿错误章节判断授权。
- 实际结果：我对 living topic 与 candidate 做全文引用扫描，确认上述三处；scoped 三份 Markdown 的相对文件链接本身均可解析，问题是 section semantics，不是文件不存在。历史旧报告按项目规则未列为需改对象。
- 证据强度：**强到可据以行动。** 当前 heading 与引用逐字不一致。
- 建议：同步 status、当前新 report 与 candidate；A-10 若已转为规范条款，应从 open 表迁出并回链正文。不要改写已归档的历史报告原件。

### CCBIR-07：支撑“剥 beta 后完整 tool-search 生命周期仍安全”的第二轮结果没有随探针落盘

- `finding_id`：`CCBIR-07`
- `severity`：`minor`
- `primary_location`：`exp/260824-beta-and-cache-control-probe/probe_tool_reference.py:1-8,59-108`
- `related_locations`：`src/app/pipeline/request_headers.py:27-30`；`.dev/docs/anthropic-direct-request-shape/status.md:49-63`；`.dev/docs/anthropic-direct-request-shape/reports/260824-cache-control-scope-and-gateway-beta-vocabulary.md:78-92`；`exp/260824-beta-and-cache-control-probe/raw/`
- 具体失败场景：未来无凭据的评审者需要核对“去掉 beta 后，第二轮 `tool_result.content[]` 的 `tool_reference` 仍得 200”。目录中只有会发请求并打印 stdout 的脚本，没有其 stdout／JSON 结果；`raw/run-main.txt` 与 `raw/run-controls.txt` 也没有 R0～R3。若该脚本从未成功跑完或后续 gateway 改变，源码与 status 的 200 主张无法区分，恰好会漏掉“第一轮成功、第二轮 400”的失败。
- 实际结果：`git status --short --untracked-files=all` 与目录文件枚举只找到 `results.json`、`run-main.txt`、`run-controls.txt` 三份 raw；evidence report §4 记录 D0～D2／T2～T3，但没有 R0～R3。任务发起者明确告知这些背景已实测，因此本轮把运行时结论作为有来源的前提沿用，不把它反说成 false；finding 只针对证据没有落盘以及 source/status 把它写成可复核实测。
- 证据强度：**强到可据以行动。** “没有对应 artifact”是文件集合事实；“真实上游是否确实返回 200”在本轮未重跑，仍是用户提供的可信前提。
- 建议：把该脚本两次运行的逐格结果写入新的 raw 文件，并在 evidence report 加 R 系列表与限定。主矩阵／controls 的“两遍一致”若要长期作为复现性证据，也应保留两轮而不是只留会被下一轮覆盖的单份输出。

## 对重点问题的逐项结论

1. **白名单与位置**：`{type,ttl}` 与已测 gateway 结果一致；当前三条浅层 loop 不完整。第四处至少有 request 顶层自动缓存，另外还有 `tool_result.content[]` 等合法嵌套。thinking／redacted_thinking 不是合法直接 marker 位置；tools 的服务端工具变体已经由 `tools[]` 的通用 dict loop 覆盖。
2. **就地修改**：当前安全。`build_context` 对 working payload 做 nested `deepcopy`，`original_payload` 不随 subscriber 改动；attempt 在 subscriber 后重取 `dict(context.payload)`；重试第二次运行不再发现未知键，不重复 loss；`rejection_capture` 读取的正是修整后的 outbound payload。本地探针和 67 项相关 lifecycle tests 均支持。当前 checkout 没有请求体 history writer 可继续核查，能验证的是 original payload、request record loss 与 rejection capture 三个表面。
3. **顺序**：`after=(SERVER_TOOL_CAPABILITY_ID,)` 的“load-bearing”理由不成立。`server_tools._as_text` 只把同一个 source block 的 marker 搬到 replacement；若 cache pass 先跑，source marker 已经被原地修净，随后搬过去仍是干净的。我分别跑“cache → server”与“server → cache”，最终 payload 完全相等。当前其他 subscriber 不会在 cache pass 后引入 marker。该 edge 作为防御性约定可以保留，但文档不能称其为当前正确性的必要条件；因未产生现行错误，本项不计 severity finding。
4. **`passthrough` 张力**：不是我拿不准的灰区。现有最高权重文字明确把 as-is 与 sanitize／strip scope 分成两档，§7.3 的正交解释是尚未获用户确认的新语义；见 CCBIR-01。
5. **内置 beta 清单**：gateway vocabulary 与 model capability 的区分真实成立，不应硬塞进用户 per-model table；但新机制必须有自己的规范 owner 与 deployment scope，见 CCBIR-03。我拿不准的是其它 Copilot hosts 是否行为相同，不拿不准的是当前代码确实把 enterprise 单点测量作用到所有 host。
6. **测试分辨力**：接线两次变异有效；幂等与 Responses-target 负向 guard 有判别力；白名单本体、第二个内置 beta、translated-to-Anthropic 正向 guard、count 腿仍是假绿空间，见 CCBIR-05。
7. **重编号**：Spec／status 主体大部分已同步；candidate、新 report 与 A-10 状态仍漏，见 CCBIR-06。历史报告未要求改写，未把其旧行号／旧编号计为 finding。
8. **工程纪律**：项目规定的 `ruff check src tests` 与 `pyright src tests` 均通过；未发现新增 prose 硬折行。额外把 `exp/260824-beta-and-cache-control-probe` 纳入 Ruff 时出现两条非 canonical-scope 告警：`probe.py:250` 的 unused `noqa: BLE001` 与 `probe_controls.py:8` import order；因项目明确 lint 入口只含 `src tests`，本报告如实记录但不另立 finding。

## 明确核查且排除的问题

1. **排除“保留 `ttl` 是未经验证的臆测”。** raw C4／C5 与 E4 都支持 gateway 接受 `ttl`；官方当前 schema 也只有 `type` 与可选 `ttl`。证据对已测 enterprise／Opus 5 路径强到可行动，不自动外推其它 host。
2. **排除“补上 `prompt-caching-scope-2026-01-05` 就能免删 `scope`”。** C2／C3 同形 400，而 beta 单独发送得 200；修复方向必须在 body，不是补 header。
3. **排除“`tool_result` 整体未覆盖”。** 外层 `tool_result` 本身就是 `messages[].content[]` 的一个 dict，现有 loop 会修它；遗漏的是它的 `content[]` 子块，以及其它合法嵌套 cacheable block。
4. **排除“thinking 是遗漏位置”。** 官方当前 request schema 明确 `ThinkingBlockParam` 与 `RedactedThinkingBlockParam` 不声明 `cache_control`，prompt-caching 文档也说 thinking block 不能直接标记；对非法位置做子字段清洗并不能把它变合法。
5. **排除“服务端 tool variant 是第四层”。** 所有 tool variant 都是 `tools[]` 条目，现有 loop 不按 type 分支，会处理其顶层 marker。未证明的是不同 gateway 对所有 variant 的 schema 行为都相同，但 traversal 本身不漏。
6. **排除“就地修改污染客户端原件”。** `server/inbound.py:54-65` 的 deep copy、实际探针中的 original 三处仍含 `scope`、相关 lifecycle tests 67 passed，共同支持当前隔离成立。
7. **排除“重试会重复 loss”。** 第一次改写后未知键不再存在，第二次运行 loss count 保持 1；现有 idempotence test 也锁定该结果。CCBIR-04 讨论的是第一次应记几条，不是否定幂等。
8. **排除“rejection capture 会记录发送前 body”。** driver 在 subscriber 后更新 attempt payload并发送，`rejection_capture.py:71-77` 保存 `context.payload` 与 SDK 实际 sent bytes；两者都位于改写后。若未来 provider 在序列化中再改 body，`sent` 仍是独立事实。
9. **排除“另一个当前 subscriber 会在 cache pass 后新造未知 marker”。** 全 `src/app` 搜索仅发现 translation 在事件之前生成 metadata、`server_tools` 搬运既有 marker；thinking、blank-text、trailing-assistant 与 hosted-web-search 不创建 cache marker。
10. **排除“gateway／model 两张表没有真实语义差别”。** 错误 envelope、匹配维度与实测邻近 flag 都支持两层区分；CCBIR-03 不要求合并，只要求规范化并收窄其证据射程。
11. **排除“作者给出的两个 mutation 没有价值”。** 删除 subscriber 注册能抓 production wiring，删除 driver 调用能抓 header wiring；它们证明的就是这两条接线，不证明白名单、列表每一成员或其它 route，边界在 status 里也基本写清。
12. **历史报告不改是正确的。** 本次只把新 report 与 living/candidate 引用的错位列出；旧 review 原件里的旧编号与旧行号是时点记录，不应追改。

## 运行、搜索面与结果

- 判据先于被评对象读取：先加载 `my-skills:as-reviewer`，再读 `docs/.human-controlled/config.example.yaml:430-519`、`message-format-reshape.md`、`message-translation.md`、`request-pipeline.md`、`upstream-retry-and-continuation.md`，以及 Anthropic 官方 prompt-caching／Messages API reference；之后才打开 diff、实现、测试、Spec 与 report。
- 版本边界：main HEAD `2c4ba5928c5f9ea1937a87b35b47c71d83d5c5d0` 加任务列出的未提交 source／test／exp，deterministic scoped bundle SHA-256 `f9072385a77de99f10aa56125cfd58ba3745a9006da1353f0ef7ad1c49646607`；`.dev` HEAD `4c0ac095089816dc46e36bec08e1bebdbe1c5877` 加三份点名文档，diff SHA-256 `c3bd0e8f734f4496a5a4da60c2ad2ed1291675d74a9085d9d64c1c6e3d91e3d1`。
- `git -C … status --short --untracked-files=all`：确认共享树还有 human-controlled、Docker、其它 exp/worktree 等并行改动，均未纳入结论或修改；`.dev` 为独立仓库。
- `uv run pytest -q tests/unit/pipeline/subscribers/test_anthropic_cache_control.py tests/unit/pipeline/subscribers/test_builtin_subscribers.py tests/unit/pipeline/test_client_request_headers.py`：`60 passed in 3.81s`。
- `uv run pytest -q tests/unit/pipeline/test_attribution_stripping.py tests/unit/observability/test_rejection_capture.py tests/unit/pipeline/test_direct_driver.py`：`67 passed in 2.66s`。
- `uv run ruff check src tests`：`All checks passed!`。`uv run pyright src tests`：`0 errors, 0 warnings, 0 informations`。
- 额外 scoped Ruff：把 `exp/260824-beta-and-cache-control-probe` 加入命令后 exit 1，只有 `probe.py:250 RUF100` 与 `probe_controls.py:8 I001` 两项；标准项目命令不含 exp。
- 本地遗漏位置探针：顶层 `cache_control.scope` 与 `tool_result.content[0].cache_control.scope` 调用 sanitizer 后均保留，`losses None`。
- 默认模式／隔离／loss 探针：默认 mode 为 `passthrough`；working payload 三层的 `scope` 均删除；`original_payload` 三层均保留；第一次 loss count 为 1，第二次仍为 1。
- 顺序探针：对带 `cache_control.scope` 的 `web_search_tool_result` 分别执行“cache → server”与“server → cache”，两份最终 JSON 相等，replacement marker 均只含 `type`。
- 文档检查：scoped 三份 Markdown 的相对文件链接无断链；语义 section 引用的错位见 CCBIR-06。
- 未重跑：全量 `pytest tests --cov=app --cov-report=term --cov-fail-under=80` 与真实上游付费探针。用户给出的 `1769 passed`／`90.51%` 与两次真实测量作为带来源的背景沿用，不冒充本轮执行结果。
- 未覆盖：个人、business、self-hosted／override gateway 的真实 beta 与 cache schema；流式与其它模型的线上行为；仓库外旧 Bun 服务的 history 数据库。本轮没有修改任何被评对象，唯一持久新增是本报告。

## 我最没把握的三个判断

1. **CCBIR-01 定为 blocker 而非 major。** 事实部分没有疑问：默认 `passthrough` 被改写且用户亲笔把剥 `scope` 写在 `sanitize`。级别取 blocker，是因为项目纪律明确禁止实现先越过 Spec／用户裁决，且 Spec A-8 自己仍把它标为待追认；如果调用方把 blocker 只留给“代码无法运行”，可重判为 major，但不能把冲突判成已解决。
2. **CCBIR-02 对 nested／top-level 的最终 400。** 位置合法与实现漏走均已确认；当前 enterprise gateway 在这些位置是否逐字返回同一个 400 没有实测。共享 strict 类型使推断很强，但若 gateway 对顶层自动缓存或 nested content 根本采用另一层规则，具体错误可能不同；无论如何，当前 Spec 的“每一个对象”与实现覆盖集合仍然不成立。
3. **CCBIR-03 的跨 host 风险大小。** 代码全局应用与证据只覆盖 enterprise 是确定事实；个人／business／self-hosted 是否实际持有不同 vocabulary 未测。我因此没有声称现网另一 host 已坏，只把“无 normative owner + 未经支撑的全局量词”定为 major。若项目另有一手契约证明所有 Copilot hosts 共用该 gateway schema，补入 Spec 后这一半可关闭。

## 执行本契约时遇到的摩擦

- Web search 服务本轮返回 unavailable；改用 Anthropic 官方文档的直接 URL 通过 WebFetch，并用本环境安装的 OpenAPI-generated SDK types 做交叉核对。
- 共享工作树与 `.dev` 都有大量无关 dirty files；所有命令均用绝对路径或 `-C`／`--directory` 绑定，未写入被评对象，也未触碰用户亲笔文件。
- 用户要求末轮返回报告路径、severity 计数与核心结论，与通用四行 handoff 模板不同；最终回复按本次用户的更具体要求执行。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-08-24T19:00:35+00:00`
- `finding_total: 7`
- `blocker: 1`
- `major: 2`
- `minor: 4`
- `nit: 0`

# Request converter server-tool 合同冲突裁决

## 裁决摘要

- **评审范围**：只读裁决主仓 `/home/xp/src/ghc-api-proxy-py` HEAD `47d9ef101c4b81ac70d805b1da157b34d021d33d` 与 request worktree `/home/xp/src/ghc-api-proxy-py-request` HEAD `f8a11ad3c3cd8f2330333634f1fe963f9aa2c444` 之间的 server-tool request converter 合同冲突。依据为主仓现行 `docs/agents/anthropic-responses-bridge/spec.md`、既有 `docs/2604-rewrite/tool-use.md`、有意删除合同、候选实现与测试，以及两份相互冲突的 review／verification 报告；`copilot-api-js` 规格仅用于判定 verifier 引用的 oracle 适用域。
- **总体 verdict**：**可按 reviewer 结论进入后续修复；verifier 的 server-tool F1 无效，不构成 request converter 实现缺陷。**
- **blocker 数**：0。
- **唯一裁决**：`web_search_20250305` 在本项目现行合同下属于明确拒绝的 Anthropic 原生 typed／server tool。候选实现的 `server_tool_not_supported` 是正确行为。`copilot-api-js` §9.1 在其项目内是一项针对 Claude Code 专用 WebSearch 子请求的已授权产品能力，但把它移植为本项目验收 oracle 属于**跨项目规格越权**。当前不得把“代理执行 server tool”“将 Anthropic server tool 映射为 Responses hosted builtin”“处理历史 server-tool blocks”拆成可分别暗中启用的实现类别；任何一种白名单映射都必须先取得本项目单独用户裁决。

## 双视角覆盖证据

### 机械核对

- 对账了主仓现行规格的状态声明、Tools 条款、双向字段矩阵、response conversion、block completion、冻结决策与 M4 处置。`spec.md:8` 明示“不得恢复 Anthropic 原生 server-tool 编排”；`:136` 将 web search 等 typed／server tools 固定为 request capability gate 显式拒绝，并规定任何白名单都是新的产品能力与单独用户裁决；`:159` 与 `:180` 分别把 request typed tool 和 response server-tool call／result 固定为 `REJECT`；`:237` 明示基础规格没有白名单；`:513` 再次冻结 server-tool no-revive；`:555` 记录 M4 已按“白名单须另行裁决”关闭。
- 对账了既有合同。`docs/2604-rewrite/tool-use.md:12` 明确本项目不支持 Anthropic 原生 server-tool 编排，并区分“未知字段透传”与“代理提供能力”；`:32` 的 typed declaration 只是在同协议预处理阶段“不改写、仅透传”，不是跨协议映射授权；`:34` 再次说明 tool-search wire extension 不等于 server-tool 执行或响应过滤能力。
- 对账了有意删除边界。`docs/2604-rewrite/hooks-tokenization-spec.md:126` 明确只处理 client tools，历史 `server_tool_use`／`*_tool_result` 不获降级、过滤或 retry 支持，残留历史被拒绝是有意 breaking removal；`docs/2604-rewrite/ROADMAP.md:63` 将原生 server-tool 编排／过滤／降级标为拒绝。
- 对账了候选代码。`src/app/protocols/anthropic_responses.py:161-162` 对历史 server-tool block 抛出 typed `server_tool_not_supported`；`:310-313` 对非空 `tool.type` 的 typed／server declaration 执行同一 no-revive 拒绝；`:392-393` 识别 `server_tool_use` 与 `*_tool_result`。对应测试在 `tests/unit/test_anthropic_responses_request.py:292-324` 覆盖 typed declaration 与历史 block，并断言稳定错误码。
- 对账了冲突报告。reviewer 在 `docs/tmp/260806-review-code-request-converter.md:25,39` 判定现实现符合 no-revive；verifier 在 `docs/tmp/260806-verify-request-converter.md:29,83-101` 依据另一个仓库的 §9.1 将同一拒绝判为 F1。
- 查证了 verifier 的外部 oracle。`/home/xp/src/copilot-api-js/docs/spec/2026-08-06-responses-anthropic-semantic-bridge.md:19,94` 将目标限定为 Claude Code 外层 client `WebSearch` 发起的专用 Messages 子请求；`:699-710` 冻结该项目自己的 request builtin 映射与 response degraded presentation；`:769` 把 `server_tool_use` 纳入其第一批支持集合。该规格描述的是另一个项目经专门需求建立的产品能力，不能覆盖本项目相反且更近的用户裁决与现行规格。

### 第一人称执行模拟

- 模拟普通 client function tool：声明没有非空 `type`，继续按 Responses function tool 转换，不受本裁决影响。
- 模拟 `web_search_20250305` typed declaration：本项目 converter 在 upstream 调用前返回稳定 incompatibility error，符合 `REJECT` 矩阵；若照 verifier 建议改成 `{type:"web_search"}`，代理将首次启用 upstream-hosted server tool，并必须同步承担 choice、response item、stream lifecycle、History 与 partial-failure 合同，直接越过“白名单须单独裁决”的门。
- 模拟历史 `server_tool_use`／`web_search_tool_result`：当前显式拒绝，不过滤、不降级、不合成结果，符合有意 breaking removal。仅映射 request declaration、仍拒绝 response／history artifacts，会形成单向半支持；进一步补 response degraded presentation 则是在完整引入新产品能力，而不是修复现有 converter。
- 模拟 `copilot-api-js` 的 Claude Code WebSearch 子请求：其外层虽由 client tool 触发，内层仍明确声明并强制选择真正的 server tool。该包装解释了外部项目为何选择 request 映射＋response degradation，但不会把内层 server tool 重新分类为本项目已支持的 client-executed function tool。
- 模拟正确样本与错误样本两端：普通 function tool 应通过；任何 Anthropic typed／server declaration 或历史 server block 应稳定拒绝。候选实现同时满足两端，不存在 false-red／false-green 的 server-tool 合同缺口。

## 事实性发现

### [blocker] 无

未发现阻断性问题。

### [裁决] verifier 的 F1 属跨项目规格越权，不是实现缺陷

- **位置**：`docs/tmp/260806-verify-request-converter.md:29,83-101`。
- **问题**：报告把 `/home/xp/src/copilot-api-js` 的专用 bridge 规格 §9.1 当作本项目冻结 Spec，并据此要求 `web_search_YYYYMMDD → {type:"web_search"}`。但报告自己在 `:12-15` 标出的 oracle 来自另一仓库；主仓实际行为 oracle 明确给出相反合同。
- **证据／失败场景**：若采纳 F1，修改 `anthropic_responses.py:310-313` 取消 typed-tool 拒绝，就会违反主仓 `spec.md:136,159,513,555` 和 `tool-use.md:12`，在没有本项目用户裁决的情况下恢复新产品能力。外部规格之所以允许映射，是因为它在自己的 `:19,94,699-710` 明确面向 Claude Code WebSearch 子请求，并配套 response degraded presentation；这不是可跨项目继承的协议事实。
- **判定**：F1 撤销。verifier 对真实运行结果“Python 拒绝、JS 映射”的观察成立，但其规范归因和 FAIL 结论不成立。

### [裁决] 候选实现的 server-tool 拒绝正确

- **位置**：`/home/xp/src/ghc-api-proxy-py-request/src/app/protocols/anthropic_responses.py:161-162,310-313,392-393`。
- **问题**：无。实现同时拒绝 typed declaration 与历史 server-tool block，使用稳定 `server_tool_not_supported`，没有静默丢弃，也没有把 server tool 伪装成普通 function tool。
- **证据／执行结果**：`tests/unit/test_anthropic_responses_request.py:292-324` 固化了两类输入的拒绝合同；这与主仓 `spec.md:136,159,180,237,302` 一致。
- **判定**：不修改实现，不修改对应测试。

### [裁决] 当前不采纳“两类 server tool 语义拆分”作为修复

- **位置**：主仓 `spec.md:136,555`；外部规格 `2026-08-06-responses-anthropic-semantic-bridge.md:19,94,699-710`。
- **问题**：技术上可以区分“代理本地执行”“跨协议映射为 upstream hosted builtin”“响应降级展示”“历史 continuation”，但这些是未来产品能力的内部子合同，不是当前合同中可独立开启的既有类别。
- **证据／失败场景**：只开启 request 映射会制造单向半支持；同时开启 response presentation／continuation 又会跨过主仓已冻结的 no-revive 边界。现行规格已把 web search、code execution、tool search 及未来 server-executed 类型整体纳入 `REJECT`，并明确要求任何白名单另行裁决。
- **判定**：本轮不拆分、不实现。若未来用户决定引入 Responses hosted web search，应以独立产品规格一次性冻结 declaration、forced choice、response presentation、stream lifecycle、History／continuation、错误与 capability gate，不能借 request converter 映射表增量恢复。

## 主观建议

未另列主观建议。

## 需执行的最小动作

1. 将 `docs/tmp/260806-verify-request-converter.md` 的 F1 标记为**已撤销／oracle 不适用**；不要据此改代码或测试。无需重写该历史报告正文，主会话在处置表或后续验收汇总中记录本裁决即可。
2. 保留 `anthropic_responses.py:161-162,310-313,392-393` 与 `test_anthropic_responses_request.py:292-324` 原样。
3. 后续修复只处理两份报告中不依赖该合同冲突的其余有效发现；server-tool 不新增实施项，也不修改现行规格。

## 最终结论

**唯一裁决：reviewer 在 server-tool 冲突上成立。候选实现无此项缺陷；当前主仓规格没有越权，越权发生在 verifier 将 `copilot-api-js` 的项目专用 §9.1 作为本项目 oracle。两类／多类 server-tool 子语义只有在未来单独用户裁决后才应拆分建模，本轮最小动作是撤销 verifier F1 并保持代码、测试与规格不变。**

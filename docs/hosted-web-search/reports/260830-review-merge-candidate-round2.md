---
report_id: merge-candidate-review-round2
attempt_id: merge-candidate-review-round2-01
status: in-review
reviewed_at_rev: 38f67418adfbf5efa38dd172fe16bd31375e3578
criteria_docs_rev: 9045d85
reviewed_at: 2026-08-30
reviewer_role: independent-reviewer
filed_by: coordinator
filing_note: 评审 subagent 的 developer 约束禁止它创建报告文件，正文由它返回、主会话逐字落盘。除本段外未做任何编辑。
---

# GitHub issue #1 合并候选态复评

## 评审范围

被评对象是分支 `worktree-260830-issue1-websearch-gate` 相对 `main` 的 9 个提交合并态，候选 HEAD 为 `38f67418adfbf5efa38dd172fe16bd31375e3578`。本轮重点复核上一轮 4 条发现的处置，以及新增提交 `03e9d10` 的块编号改动与 `38f6741` 的文字、测试修正。

工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260830-issue1-websearch-gate` 已确认 clean。未修改 `src/` 或 `tests/`，未调用真实 upstream。

## 总体 verdict

**needs-fix。**

上一轮 finding 03 与 04 已关闭；finding 01 与 02 只部分关闭。当前活 Spec 另有两处仍以规范口吻要求已经废止的「能力门失败后剥离声明」，因此 blocker 仍在。另有一条此前未定级的 cassette 正控缺口，现定为 minor。

## blocker 数

**1。** 另有 major 0、minor 2、nit 0。

## 上一轮发现处置

| finding | 状态 | 复核结论 |
|---|---|---|
| `merge-candidate-review-01` | **partially-closed** | §8.3 首条、§10 表格和 `status.md:16` 已改；但 Spec §3.6、§4 仍保留同一错误规范，`status.md:66` 也仍把已经修正的 §8.3 描述成失真状态 |
| `merge-candidate-review-02` | **partially-closed** | 多数源码注释已补默认值、配置上限、429 例外与「模型行为未测」限定；但 Spec §8.3 及数处源码／测试文字仍保留绝对断言 |
| `merge-candidate-review-03` | **closed** | 新测试精确断言 `WebSearchNotExecutable` 子类与 web-search 专属 message 后缀；目标测试通过，且所述 `searches_only=False` 变异有明确分辨力 |
| `merge-candidate-review-04` | **closed** | 两处证据路径均已改为 `.dev/docs/hosted-web-search/reports/260830-claude-code-web-fetch-client-behaviour.md` |

## 发现

### merge-candidate-review-01

- `finding_id`：`merge-candidate-review-01`
- `severity`：blocker
- `primary_location`：`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:132`
- `related_locations`：同文件 `:147,216`；`.dev/docs/hosted-web-search/status.md:64-68`
- 发现：上一轮点名的 §8.3 首条与 §10 表格确已就地重写，但同一活 Spec 仍有两条当前规范要求能力门不通过时「剥离」声明。§3.6 写「web search 族但能力门不通过时走 §8.3 剥离」；§4 又写「被指向的 web search 声明因能力门未通过而被剥离时」应清理 `tool_choice`。现行实现与 §8.3 的正确条款均是抛 `WebSearchNotExecutable` 后合成失败块对，不会剥离后继续请求。§5.4 另将 `_REJECTED_TYPE_PREFIXES` 称为订阅者的「剥离清单」，属于同一遗留术语。
- 状态文档也未闭合：`status.md:66` 仍把「§8.3 仍将必须剥离写成规范」列为当前失真，然而 §8.3 本身已经修正；真正尚未修的是 §3.6 与 §4。
- 排除结果：Spec 中其余「剥离」命中已逐项分类。修订记录、旧裁决原貌、被划除文本、反应式重试禁令、字段级剥离与「不得剥离」均是合法元文本或其他行为，不属于残留；不能据此把 §3.6／§4 两条规范性命中也归为元文本。
- 影响：活 Spec 继续给同一当前行为两套互斥指令，违反项目不可协商的「发现已知错误即当场修订 Spec」规则。后继者照 §3.6 或 §4 实现会恢复已被用户裁决推翻的 drop 路径。
- 建议：将 §3.6 改成「能力门不通过时由后置 gate 抛 `WebSearchNotExecutable`，按 §8.3 合成失败块对」；将 §4 改成「能力门拒绝时请求不发往上游，因此不产生 dangling forced choice」；将 §5.4 的「剥离清单」改为当前真实职责名称，并同步更新 `status.md:64-68`。
- 结论强度：**强，足以继续阻止合并。** 两条位于规范章节、使用「必须」与行为分支措辞，无法解释成历史记录。

### merge-candidate-review-02

- `finding_id`：`merge-candidate-review-02`
- `severity`：minor
- `primary_location`：`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:326`
- `related_locations`：`src/app/pipeline/delivery/formats/anthropic_messages_synthetic_reply.py:15-19`；`src/app/pipeline/driver.py:192,200`；`tests/int/test_pipeline_app.py:529,582-586,616,2646`
- 发现：`38f6741` 已把多数目标位置收窄为「400 不重试、429 通常重试、默认 10 次重试、配置可提高、模型是否重复调用未测」，但仍有若干相邻绝对句未同步。
- Spec §8.3 仍写「429／5xx 上限 10 次」，没有默认值、`CLAUDE_CODE_MAX_RETRIES` 非 watchdog 上限 15、watchdog 上限 300 的限定；同句仍断言失败 tool result「不会招来重复调用」，而取证只证明没有客户端机制性重试，主对话模型是否再次调用未测。
- synthetic reply 同一段先明确「模型是否重复调用未测」，两行后又写「Nothing retries it」，内部直接矛盾。其「raised to 15 by `CLAUDE_CODE_MAX_RETRIES`」也宜改为「可覆盖，非 watchdog 模式封顶 15」，因为该变量并不必然把值设成 15。
- driver 首句仍写「A failed tool result draws no repeat call」，测试仍写「A failed tool is not retried」；另有两处「retry storm」将尚未实测的合成效果写成既成因果。`assert …, "an HTTP error here is retried by the client"` 虽可宽泛解释成模型重复调用，但在这轮刚区分 actor 的语境里仍会把读者带回旧归因。
- 已确认成立的部分：传输层对 400 重试 0 次；408、409、401、≥500 进入重试；429 通常重试但有例外；默认上限是 10 次**重试**而非 10 次总尝试；transcript 中的 3 次是主对话模型重新调用 `WebSearch`。
- 建议：以 synthetic reply 新增的限定段为唯一表述基线，并删除或收窄其后所有绝对句；同时修订 Spec §8.3，而不是只改代码注释。
- 结论强度：**强，足以要求文字修正，不影响当前 runtime 行为。**

### merge-candidate-review-05

- `finding_id`：`merge-candidate-review-05`
- `severity`：minor
- `primary_location`：`tests/int/test_pipeline_app.py:2595-2633`
- `related_locations`：`tests/int/cassettes/responses_web_search_stream.json`
- 发现：`test_a_direct_responses_client_survives_an_upstream_that_really_searched` 当前有真实分辨力，cassette 也确实包含 `web_search_call`；但测试没有把这个承重前提写成断言。若以后重录得到一个没有执行搜索的普通 Responses 流，当前所有断言仍会通过：HTTP 200、`response.completed`、无 `server_tool_use`、无 Anthropic event name 都是普通响应本来就满足的。
- 这不是当前假绿：本轮直接读取 cassette 确认它含 `response.output_item.added`／`done` 的 `item.type="web_search_call"`，目标测试也通过。缺陷在于 test 自称是「将来守」，而 cassette 是项目明确允许重录的资产；重录正是会让其前提改变的合法操作。
- 建议：在送入 app 前按 SSE 结构解析 cassette，断言至少一个 output item 的 `type` 为 `web_search_call`。不要只做裸 substring 断言，因为请求摘要或正文也可能出现同名字符串。
- 定级理由：这是局部测试 oracle 缺口，不影响今天的生产行为，但可在合法重录后使专门的回归门静默失去分辨力，超过纯可读性 nit，故定 minor。
- 结论强度：**强。** 普通 Responses 流满足当前全部输出断言，缺少输入正控是结构事实。

## 新提交 `03e9d10` 复核

未发现行为缺陷。

1. `Draft.index=-1` 没有遗留读取者。全 `src/` 与 `tests/` 扫描只找到 Anthropic assembler 继续读取自己构造的 `draft.index`；Responses assembler 的两个 `Draft(index=-1, …)` 构造点之后均不再读取该字段。
2. `DISCARDED` item 在返回前不会推进 `_emitted`，后续第一个真正产出的 block 得到 index 0；新增测试直接断言这一结构，回退到旧按 item 开号的实现会变红。
3. `cut_short` 在构造 block 时会先占 `_emitted`，但当前协议不产生外部空洞：若随后释放，该 block 使用已保留的连续编号；若因 hand-over stop reason 丢弃，它后面不再有 assembler block，合成 hand-back block 的编号取 `DeliverySession.committed_count`，不读 `_emitted`。这一结论依赖现有约束「incomplete item 是最后一个 item」；若将来 upstream 出现 incomplete item 后继续输出其他 item，需要重开排序判断。
4. `ResponsesFramer` 完全不读 `CompletedBlock.index`，继续由自己的 `_output_index` 在实际 framing 时连续编号，因此不受该改动影响。
5. 当前注释把 `_emitted` 描述为「发出时分配」略有物理时点上的简化，因为 held `cut_short` 在真正发出前已经占号；但上述两条出口证明当前 wire 行为仍连续，未将此列为 finding。

## 其余特别关注项

- `web_fetch` 与混合声明走 400 的行为继续符合 Spec §8.3／§13；纯 web-search 的原 message 后缀仍保留。
- finding 03 的正向 control 已补齐，且目标测试同时断言 exception subtype 与 search-only message。fetch control 也明确反证该 subtype。
- finding 04 的两条报告路径均已修复。
- `6e16678` 经逐 hunk `git show` 确认只修改 docstring／注释，没有可执行代码变化。
- `c82a558` 经提交范围和最终 diff 确认只修改 docstring／注释／测试说明，没有可执行行为变化。
- `test_a_direct_responses_client_survives_an_upstream_that_really_searched` 的价值判断窄义成立：它能防未来将 Anthropic pair 无差别交给 direct Responses framer；它不是 direct Responses 语义完整性的验收，也没有证明当前将 search item 摊成文本是最终正确行为。

## 显式排除掉的可能性

1. **`03e9d10` 让 hand-over block 留下 index 洞。** 排除。hand-over index 取 `session.committed_count`，不取 assembler 的 `_emitted`。
2. **`ResponsesFramer` 会消费 `Draft.index` 或 `CompletedBlock.index`。** 排除。它只使用自己的 `_output_index`。
3. **`Draft.index=-1` 会污染 Anthropic assembler。** 排除。两种 assembler 各自构造 Draft；Anthropic 路径仍赋真实 index。
4. **§3.6／§4 的「剥离」只是修订记录。** 排除。两处都在当前规范正文中使用将来行为与「必须」措辞。
5. **Spec §8.3 的 retry 句已经由 `38f6741` 自动同步。** 排除。`.dev/` 是独立仓库，当前 `9045d85` 仍保留旧绝对句。
6. **cassette guard 今天已经是假绿。** 排除。当前 cassette 确有真实 `web_search_call`，本轮测试通过；风险发生在合法重录后。
7. **为防重录应钉 cassette 文件名或 substring。** 排除。文件名不证明内容，裸字符串也不证明命中了 item discriminator；应断言解析后的结构。
8. 其余排除项：无。

## 搜索面与执行证据

读取并比对：完整 `main...38f6741` 合并 diff；9 提交 log；`6e16678` 与 `38f6741` 的逐提交 patch；当前 hosted-web-search Spec、status、error-envelope Spec、web-fetch 客户端取证、两轮 prior review；全部直接改动文件及 block delivery、hand-over、cut-short 相邻调用链。

机械扫描：全部 `Draft(`／`draft.index`；全部 retry 相关措辞；Spec／status 中全部「剥离」命中并逐项分类；翻译成 Anthropic 拼法的残留；`git diff --check`。

执行结果：

- worktree clean，HEAD 为 `38f6741`。
- 目标回归：12 passed。
- 完整默认测试：1944 passed、2 skipped，coverage 90.74%。
- Ruff：all checks passed。
- Pyright：0 errors、0 warnings、0 informations。
- `git diff --check`：无输出。
- 首次目标测试因 `uv run --project` 不改变进程 cwd，cassette 相对路径从 `.dev` 解析而出现 1 个 `FileNotFoundError`；改用 `uv run --directory <worktree>` 后同一组 12 项全部通过。该失败属于命令装位，不是候选缺陷。

未覆盖：没有真实 Copilot upstream 调用；没有实施控制变异；变异结论通过代码结构与现有报告复核，未冒充本轮实跑。

## 整体判定

生产代码改动本身未发现新的 blocker／major，`03e9d10` 的块编号修复成立，完整测试与静态检查均通过。但当前活 Spec 仍有两处规范性旧行为，且 retry 事实仍未同步到 Spec 和全部转述；因此候选不能合并。

## 我最没把握的三个判断

1. **finding 01 保持 blocker。** 事实成立度很高；不确定性只在严重度。按本项目「Spec 先行且已知错句必须当场改」的不可协商规则，它继续阻止进入合并阶段，因此保留 blocker。
2. **finding 05 定 minor 而非 nit。** 今天没有 runtime 失败，但它是专门为未来改动设置的守卫，合法重录即可让守卫静默空转，因此属于测试正确性而非文字精度。
3. **cut-short 不留洞的结论依赖 incomplete item 为最后一个 item。** 这是当前实现与既有观测共同采用的约束；若以后出现反例，`_emitted` 在 hold 时提前占号需要重新评审。当前没有证据支持把未观测形态升级成 finding。

## 执行本契约时遇到的摩擦

初轮 harness 阻塞已解决：`git -C <worktree>` 的单一简单命令可运行；测试必须额外使用 `uv run --directory <worktree>`，因为 `--project` 只选项目而不改变 cwd。当前 developer 约束仍禁止本 subagent 创建评审报告文件，因此正文直接返回协调者落盘。

## 交付声明

- `delivery_complete: true`
- `completed_at: 2026-08-30`
- `finding_total: 3`
- `blocker_count: 1`
- `major_count: 0`
- `minor_count: 2`
- `nit_count: 0`
- `verdict: needs-fix`
- `merge: no`

---

## 主会话的处置（2026-08-30，落盘时补记）

三条全部处置，见提交 `f049836` 与 `.dev` 的规格修订：

- **01（blocker）**：§3.6、§4、§5.4 三处就地改写（§5.4 是主会话自己机械扫描扫出来的，不在本报告点名之列），`status.md:66` 的失真登记结案。修订记录里写明了教训——上一轮只改被点名的两处而没有扫全同类。
- **02（minor）**：Spec §8.3 的 retry 条整条重写（补默认值、`CLAUDE_CODE_MAX_RETRIES` 非 watchdog 封顶 15、watchdog 300、429 例外，并把「不会招来重复调用」改成「没有机制性重试，模型行为未测」）；代码侧四处绝对句与两处断言消息一并收窄。
- **05（minor）**：cassette guard 现在解析 SSE 并断言至少一个 output item 的 `type` 为 `web_search_call`，结构判据而非 substring。换成不含搜索的 cassette 可复现失败。

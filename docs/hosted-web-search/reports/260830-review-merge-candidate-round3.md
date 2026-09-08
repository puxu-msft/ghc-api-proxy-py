---
report_id: merge-candidate-review-round3
attempt_id: merge-candidate-review-round3-01
status: closed
reviewed_at_rev: f04983682409f7c8c7dbd262bf623a62ad078673
criteria_docs_rev: 670ed75
observed_docs_head: 87084ee
reviewed_at: 2026-08-30
reviewer_role: independent-reviewer
filed_by: coordinator
filing_note: 评审 subagent 的 developer 约束禁止它创建报告文件，正文由它返回、主会话逐字落盘。除本段与末尾的处置段外未做任何编辑。
---

# GitHub issue #1 合并候选态第三轮复评

## 评审范围

被评对象是分支 `worktree-260830-issue1-websearch-gate` 相对 `main` 的 10 个提交合并态，候选 HEAD 为 `f04983682409f7c8c7dbd262bf623a62ad078673`。本轮重点复核上一轮 `merge-candidate-review-01`、`merge-candidate-review-02`、`merge-candidate-review-05` 的处置，以及 `_emitted` 注释与 cut-short 前提。

协调者指定的 `.dev` 修订是 `670ed75`。复核期间 `.dev` 已前进到 `87084ee`；两者之间只修订同一 Spec 的 §5.3 与文档状态，没有改动本轮所判的 §3.6、§4、§5.4、§8.3 retry 条，因此本轮结论未被该并行提交失效。

工作树已确认 clean。未修改 `src/` 或 `tests/`，未调用真实 upstream。

## 总体 verdict

**pass。**

未发现 blocker 或 major。上一轮三条发现的实质行为与测试缺口均已关闭；仍有一条 retry 数值转述 minor，以及两条注释／Spec 精度 nit。按严重度语义，候选可以进入合并阶段。

## blocker 数

**0。** major 0、minor 1、nit 2。

## 上一轮发现处置

| finding | 状态 | 复核结论 |
|---|---|---|
| `merge-candidate-review-01` | **closed** | §3.6、§4、§5.4 与 status 的遗留均已改；独立枚举全部「剥离」命中后，未再发现把能力门失败写成当前 drop 行为的规范句 |
| `merge-candidate-review-02` | **partially-closed** | Spec 与绝大多数源码／测试文字已准确区分 transport、model、默认值与未测边界；synthetic reply 仍把 watchdog 的 300 写成 cap |
| `merge-candidate-review-05` | **closed** | cassette guard 已解析 SSE，并在输出断言前结构性要求 `item.type == "web_search_call"`；目标测试通过 |

## 发现

### merge-candidate-review-02

- `severity`：minor
- `primary_location`：`src/app/pipeline/delivery/formats/anthropic_messages_synthetic_reply.py:15`
- `related_locations`：`.dev/docs/hosted-web-search/reports/260830-claude-code-web-fetch-client-behaviour.md:222`
- 发现：该句现在写成默认 10 次重试、由 `CLAUDE_CODE_MAX_RETRIES` 覆盖，并「capped at 15 outside its watchdog mode, 300 inside it」。后半句在语法上把 300 也写成 watchdog 模式的 cap；取证报告支持的是：非 watchdog 模式下 `CLAUDE_CODE_MAX_RETRIES` 被封顶到 15，watchdog 模式的**默认值**是 300，但该环境变量仍可覆盖且没有记录一个 300 cap。
- 其余 retry 修正已成立：400 不发生 transport retry；408、409、401、5xx 与通常的 429 会重试；429 有配额例外；10 是 retry 次数而非总 attempt 数；失败 tool result 没有客户端机制性重试，而模型是否再次调用未测。
- 建议：改成「ten retries by default; watchdog mode defaults to 300; `CLAUDE_CODE_MAX_RETRIES` overrides the count and is capped at 15 only outside watchdog mode」。
- 结论强度：**强。** 取证报告逐字区分了「watchdog 默认 300」与「非 watchdog 封顶 15」。

### merge-candidate-review-06

- `severity`：nit
- `primary_location`：`.dev/docs/anthropic-responses-bridge/hosted-web-search-spec.md:148`
- 发现：本条的核心区分正确——能力门拒绝时请求不发往上游，不需要删除一个 dangling `tool_choice`；`spec.md` 的通用原子处理条款也应保留。精度问题只在括号里的例子：「§3.4 的字段级剥离」保留 web-search declaration，因此 named choice 仍有目标，并不形成 dangling choice。§3.4 真正另行要求删除 choice 的是 `empty_result` 分支，该要求已在 §3.4 自己写明。
- 影响：当前规范主行为没有冲突，但该例子可能让读者误以为 `drop_unsupported_fields` 也应删除仍然有效的 forced choice。
- 建议：把例子改成「§3.4 的 `empty_result` 分支已有自己的显式删除要求」，或只保留「`spec.md` 的通用条款本身不改」而不举字段级剥离为例。
- 结论强度：**强。**

### merge-candidate-review-07

- `severity`：nit
- `primary_location`：`src/app/pipeline/delivery/formats/openai_responses.py:414-419`
- 发现：注释说 block number 在 block「is emitted」时分配，但代码在构造 `CompletedBlock` 后立即推进 `_emitted`，随后才检查 `cut_short`。held block 因而会在真正发出前占号，并可能在 hand-over ending 上被丢弃。当前 wire 行为仍正确，但注释描述的物理时点不精确，变量名 `_emitted` 也不是严格的「已经发出数量」。
- 为什么当前不构成行为缺陷：held block 若释放，会使用预留的连续编号；若被丢弃，当前协议约束下它是最后一个 item，后面不再有 assembler block；hand-back block 的编号来自 `DeliverySession.committed_count`，不读 `_emitted`；`ResponsesFramer` 也使用自己的 `_output_index`。
- 建议：改成「block number 在形成一个可能交付的 block 时分配，而不是 item 打开时分配；held cut-short block 会预留编号」。可顺带回指上一段的 last-item 约束。
- 结论强度：**强。**

## 对协调者两个问题的明确答复

1. `_emitted` 注释建议改，定级为 **nit**。行为正确，但「发出时分配」不是代码实际时点。
2. 「incomplete item 是最后一个 item」的前提不需要另开一条 finding，因为它其实已经写在紧邻位置：`openai_responses.py:411` 明说「upstream cuts the last one short and then stops」。建议只在修改 `_emitted` 注释时回指这条现有约束，不必重复安装第二份独立断言。

## Spec 全量「剥离」复扫结论

已独立枚举 `hosted-web-search-spec.md` 与 `status.md` 中全部「剥离」命中，并逐项分类。

- §3.6 已明确写「能力门不通过时不剥离，由后置 gate 抛异常并合成」。
- §4 对能力门拒绝与 dangling choice 的区分正确，只有 finding 06 所述例子精度问题。
- §5.4 已改成「拒绝清单（`_REJECTED_TYPE_PREFIXES`）」。
- §8.3、§10 与 status 当前行为已同步。
- 其余命中属于修订记录、被推翻旧裁决、删除线、字段级剥离、反应式重试禁令、否定句或参考项目的过度剥离，不是残留的当前 drop 规范。

因此上一轮 blocker 已关闭。

## retry 文本复扫结论

除 finding 02 的 watchdog 数值措辞外，未再发现旧绝对句。

- synthetic reply、driver、subscriber、semantic exception 与 integration test 均已写明模型重复调用与 transport retry 是不同层。
- 「没有客户端机制性重试」与「模型是否重复调用未测」已并列保留。
- 两条 assertion message 已改为「HTTP error draws repeat calls from the model」。
- Spec §8.3 已完整记录默认 10、非 watchdog 封顶 15、watchdog 300、429 例外及模型行为未测。

## cassette guard 复核

`test_a_direct_responses_client_survives_an_upstream_that_really_searched` 现在先拼回 cassette 的完整 SSE，再逐个解析 `data:` JSON，检查顶层 `item.type == "web_search_call"`。该判据命中实际驱动 assembler 的 `response.output_item.added`／`done` 结构，不靠文件名或裸 substring。若换成不含搜索 item 的普通 Responses cassette，正控会先失败，后面的 200／terminal／协议词汇断言不再能够伪装成有效 guard。上一轮 minor 已关闭。

## `_emitted` 与 cut-short 最终结论

- Responses assembler 的 `Draft(index=-1)` 没有遗留读取者；Anthropic assembler 读取的是自己构造的真实 index。
- `DISCARDED` item 不推进 `_emitted`，新增测试能区分旧行为。
- held cut-short 的预留编号在释放时连续；被丢弃时不会在当前协议下留下后续 assembler block 的洞。
- hand-over block 使用 `session.committed_count`。
- `ResponsesFramer` 使用自己的 `_output_index`，不消费 `CompletedBlock.index`。
- 未发现 `03e9d10` 引入的行为问题。

## 显式排除掉的可能性

1. **§3.6、§4 或 §5.4 仍要求能力门失败后 drop declaration。** 排除；全量「剥离」扫描与逐项分类没有这种当前规范。
2. **§4 应删除能力门拒绝路径上的 `tool_choice`。** 排除；请求不发往上游，不形成 dangling payload。
3. **`spec.md` 的通用 dangling-choice 条款应被删除。** 排除；它仍约束真正删除或拒绝目标 declaration 的其他路径。
4. **`drop_unsupported_fields` 本身形成 dangling choice。** 排除；它只删 unsupported subfields，declaration 仍存在。这正是 finding 06 要修正例子的原因。
5. **cassette 正控只是在匹配字符串。** 排除；它解析 JSON 后检查 item discriminator。
6. **held cut-short 被丢弃后会让 hand-back block 跳号。** 排除；hand-back 编号来自 `session.committed_count`。
7. **last-item 前提完全没有记录。** 排除；`openai_responses.py:411` 已明确记录。
8. **watchdog 模式的 300 是已证实的绝对 cap。** 排除；取证只支持其默认值为 300，`CLAUDE_CODE_MAX_RETRIES` 可覆盖。
9. 其余排除项：无。

## 搜索面与执行证据

读取并比对：`f049836` 提交 patch、最终相关源码与测试、当前 Spec／status、指定 `.dev` 修订 `670ed75` 到当前 `87084ee` 的差异、客户端取证报告、前两轮复评结论。

机械扫描：Spec 与 status 的全部「剥离」命中；全部 touched retry 表述；`Draft.index`、`_emitted`、`CompletedBlock.index`、`session.committed_count` 与 hand-over 调用链。

执行结果：

- worktree clean，HEAD 为 `f049836`。
- 目标回归：6 passed。
- 完整默认测试：1944 passed、2 skipped，coverage 90.74%。
- Ruff：all checks passed。
- Pyright：0 errors、0 warnings、0 informations。
- `git diff --check`：无输出。

未覆盖：没有真实 Copilot upstream 调用；没有在本轮亲自替换 cassette 或实施源码控制变异。后者由代码结构与协调者给出的变异结果交叉核对，不冒充本轮执行。

## 整体判定

`f049836` 已关闭上一轮 blocker 与 cassette guard minor，`03e9d10` 的块编号修复成立，完整回归与静态检查均通过。剩余一条 minor 与两条 nit 均为文字精度，不改变 runtime、协议分支或测试分辨力。

**可否合并：yes。**

## 我最没把握的三个判断

1. **finding 02 保持 minor 而非 nit。** 它只影响文字，但重试上限正是本轮反复纠正的承重事实；把 watchdog 默认写成 cap 会被后继者当作运行边界复用，因此高于普通措辞 nit。
2. **finding 06 定 nit。** 更具体的 §3.4 已写清各分支行为，当前实现也未受影响；缺陷是例子指错分支，而不是规范主行为错。
3. **不为 last-item 前提另开 finding。** 该前提已经在相邻 `openai_responses.py:411` 明写；再写一份独立断言只会增加同步面。把它回链进 `_emitted` 注释即可。

## 交付声明

- `delivery_complete: true`
- `finding_total: 3`
- `blocker_count: 0`
- `major_count: 0`
- `minor_count: 1`
- `nit_count: 2`
- `verdict: pass`
- `merge: yes`

---

## 主会话的处置（2026-08-30，落盘时补记）

三条全部按建议处置，见工作树提交 `9e990d6` 与 `.dev` 的 Spec 修订：

- **02（minor）**：改为 `ten *retries* by default, or 300 in its watchdog mode; CLAUDE_CODE_MAX_RETRIES overrides the count and is capped at 15 only outside watchdog mode`。
- **06（nit）**：§4 的例子改为 `empty_result` 分支，并显式写出 `drop_unsupported_fields` 是**反例**（它保留声明，choice 仍有目标），同时注明 2026-08-30 首版举错了例子。
- **07（nit）**：注释改为「形成一个可能交付的 block 时分配」，并按第 2 条答复**回指** `openai_responses.py:411` 的 last-item 约束而非另立断言。

合并已执行：`main` 上的 squash 提交为 `78030df`，源提交保存在不可变分支 `archive/260830-issue1-websearch-gate`（指向 `9e990d6`，**不是** squash 提交）。合并后主树 gate：1944 passed、2 skipped，coverage 90.74%，Ruff 与 Pyright 干净。

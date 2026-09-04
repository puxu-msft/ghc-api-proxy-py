# Responses completed client actions 实施计划评审

## 评审范围

被检对象是主树 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md` 新增的 §10（v13，2026-09-04）。独立判据来自用户给出的 C1～C8、`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md` §7.1／§10、`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md` 的着色／文本／验收合同，以及当前主树源码、测试和项目工作流规则。只评可执行性、依赖闭合、范围隔离、数据来源、传播、真实入口、测试鉴别力与提交顺序；没有评审 §0～§9 的既有实现状态，也没有执行尚不存在的候选代码。

## 总体 verdict

**needs-fix**。Blocker：0。Major：3。当前计划的核心数据模型与测试设计可执行，但必须先关闭下面 3 项，才能按该计划实施并据此宣称候选完成。

## Findings

### F01 — major：计划把未获当前 Spec 覆盖的 `response.incomplete` 也切到新展示分支
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md:261` 要在 `response.completed` **或** `response.incomplete` 上填新 facts；`:329` 随后让任何非空 `terminal_status` 压过 legacy `stop_reason`／`tools` 展示。
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md:667,669-672` 把本轮 producer 明确写成 `response.output_item.*` 与 `response.completed`，且本轮判读合同只定了 `completed`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/tui/spec.md:131,145,160,188` 也只给 `completed` 组合判读 oracle，并仍规定 `max_tokens` 为黄色。
- `source_evidence`：当前 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/openai_responses.py:700-724` 把 `response.incomplete` 的 `max_output_tokens` 映为 `max_tokens`，`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py:51-56,383-387` 会把它以黄色 legacy ending 显示；计划会把它改成未着色的原生 status，却没有相应验收。
- `impact`：这是 Responses streaming direct 内部仍然真实可见的范围外行为变化，不只是多记一个字段；照计划实施会在 Spec 之前改变 incomplete completion line，并让现有 `max_tokens` 信息从该行消失。
- `required_correction`：二选一必须先定案并写回 living Specs：本切片只在 `response.completed` 填新 facts，或把 `response.incomplete` 的 status／action／legacy reason 组合文本与颜色合同补进 direct／TUI Specs并新增正反 oracle；不能只在计划中选择后一种行为。

### F02 — major：所谓“最终完整回归”排在会改动候选的 review／disposition 之前
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md:375-381` 的顺序是 targeted/static → full regression → implementation review／处置 → source commit。
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:28-30` 要求候选只做一次最终 full regression，并评审最终候选；`/home/xp/.claude/rules/00-user/30-use-of-agents.md:34-40` 要求非平凡产物在提交前完成独立评审。
- `source_evidence`：计划 `:379` 明令处置 findings 直到 0 blocker／major，而 `:377` 又承认 relevant bytes 改变时必须重跑；一旦评审导致修复，第一次 full run 不是最终证据，若再跑则物理上跑了两次 full regression。
- `impact`：计划无法同时保证 C8 的“一次最终 full regression”和“评审修复后的最终候选有新鲜验证”，执行者只能留下陈旧证据或自行偏离顺序。
- `required_correction`：先完成 merged-state review、finding 处置、受影响 targeted／mutation controls 与必要复评；候选字节稳定且评审达成共识后，再运行一次最终 Ruff、Pyright、full regression，随后提交 source 语义单元。

### F03 — major：source commit 步骤没有把新文件纳入 index 的动作，所写命令不能提交完整切片
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/plan.md:162` 创建未跟踪的 `openai_responses_actions.py`，但 `:381-397` 只要求 `git commit -F … -- <pathspec>` 与 cached-path 核对；§10 没有任何 `git add` 步骤。
- `related_locations`：Git 官方 `git-commit(1)` DESCRIPTION（https://git-scm.com/docs/git-commit）明确说 path arguments 记录 listed files 的工作树内容，而这些文件“must already be known to Git”；未跟踪的新模块不满足该前提。
- `source_evidence`：`:381` 的 cached-path 核对也看不见未 staged 的 tracked working-tree 内容，而同一条 pathspec commit 会绕过其它 staged paths；因此该核对与实际 commit payload 不是同一个对象。
- `impact`：按文字执行会因精确列出的未跟踪路径报错而不产生 commit，或在执行者临时删掉该路径时产生缺少 action module 的提交；两种结果都不满足 C8 的精确 source 语义单元。
- `required_correction`：在 cached audit 前明确执行 `git add -- <同一份精确 source/test pathspec>`，核对 staged diff／cached path 集，再执行 `git commit -F <file> -- <同一份精确 pathspec>`；保留并核对其它会话已有 staged entries，不得清空 index。

## C1～C8 核验矩阵

| Criterion | 结论 | file:line/source 证据 |
|---|---|---|
| C1 | 通过，但受 F01 的 incomplete 越界限定 | 计划 `plan.md:150-152,231-265` 把 producer 限到 direct adapter，并明令 shared reader／`ResponsesAssembler` 不动；当前 `src/app/pipeline/reply.py:58-69` 的 nonstream `reply_summary` 不在 Files 中，计划自身 `plan.md:98` 也明确保留其空摘要测试。 |
| C2 | 通过 | 计划 `plan.md:162,170-176` 将 records 放在 `assembling.py`、classifier 放在只依赖 records 的 `openai_responses_actions.py`；当前 `assembling.py:7-16` 不依赖 formats，`openai_responses_passthrough.py:11-17` 单向依赖 shared reader／engine，因此所述新边不会回指 formats。 |
| C3 | 通过 | 计划 `plan.md:170-195` 定义完整三态、唯一 bool projection、按 integer item index 合并 opening／closing，并保留无 index item 的单独分类；当前反例与预定落点真实存在于 `passthrough.py:78-109,144-193`、`test_responses_passthrough.py:334-383`，Anthropic 现语义在 `anthropic_messages_passthrough.py:39-46`。 |
| C4 | completed 定义域内通过；F01 所述 incomplete 扩张不通过 | 计划 `plan.md:232-265` 让最终 actions／completeness 只读 terminal `response.output`，并以 deliberate disagreement 测试隔离；当前 `_saw_client_action` 与 shared stop-reason consumer 位于 `passthrough.py:161-193`、`openai_responses.py:689-724`。 |
| C5 | 通过 | 计划 `plan.md:231,279-300,311-331` 一一传播三字段，默认 `""／()／False` 与 explicit empty 的 `True` 可区分，并以 `terminal_status` 门隔离旧 renderer；真实传播链是 `request_trace.py:147-207,220-270` → `request_log.py:102-159,337-411` → `request_log_file.py:30-42`。 |
| C6 | 通过 | `Chain.capabilities` 真实存在于 `src/app/core/chain.py:29-46`，请求每次从 app state 读取 chain（`src/app/server/app_state.py:17-24`），测试已有 replacement 范式（`tests/int/test_pipeline_app.py:1966-1975,2024-2026`）；`logging.py:93-108` 在 `colors=False` 时只不新增 outer paint，非 pending 的 message body 仍逐字采用已含 ANSI 的 `event`。 |
| C7 | 通过 | TUI Spec oracle 在 `tui/spec.md:180-188`；计划 `plan.md:337-359` 复用真实 `/responses` app route、用 terminal/done deliberate disagreement 分开击中 action-list 与 color consumer，并把 mock 能力边界写明；mutation 只用 `$CLAUDE_JOB_DIR` 快照、逐次单变量、同步恢复及 `cmp`，没有新增持久 gate／proof framework。 |
| C8 | 不通过，见 F02、F03 | 语义单元、精确 pathspec、单独 `.dev` commit 的目标在 `plan.md:381-403` 是对的；但 `:375-381` 的 full/review 顺序和 `:162,381-397` 的未 staged create file 使实际流程不闭合。 |

## 额外可执行性与边界检查

- 所有现有文件与现有 symbol 均已在当前主树定位：`Terminal`、`RawEventBatch`、`Dialect`、`PassthroughAssembler`、`ResponsesAssembler`、`read_responses_terminal`、`RequestTrace`、`RequestLine`、`TerminalCapabilities`、`setup_logging`、`_chain_of`、`_request_lines` 均真实存在；新增 enum／record／reader／formatter／fixture helper 均在首次使用前由 Task 10.1～10.5 明确定义。
- 计划列出的 targeted pytest、`ruff check`、Pyright 与 full regression 入口和路径均存在；未发现错误 test root、`ruff format`、production `4141` 操作、checkout／restore／stash、或新 proof infrastructure。
- 计划的 source/test pathspec 覆盖其 Files 列出的全部预期变更；`request_log_file.py` 无须修改，因为现有 `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log_file.py:30-42` 已由 `dataclasses.asdict` 序列化 `RequestLine`。
- 行号均与 2026-09-04 当前主树对应到目标 symbol；它们是计划时点定位，不应在实施后当稳定锚使用。

## 未采纳／排除路线

- 未把 `plan.md:146` 的两种 execution skill 记为 major：`subagent-driven-development` 已给出推荐默认，选择只影响编排，不改变产品或验收结果；这是最多 minor 的措辞问题。
- 未把“新增默认字段会污染 translated／Anthropic”记为问题：C5 与 Specs 明确要求 durable fields 保留默认值，而 producer isolation 与 `terminal_status` renderer gate 分别由 Task 10.2～10.4 的测试锁定。
- 未采纳“`setup_logging(colors=False)` 会剥掉 route (e) message ANSI”的假设：`logging.py:93-108` 的 source 直接证明 renderer 不清洗 `event`，计划通过 app-state `capabilities.color=True` 形成的内层 spans 可被 `_request_lines` 观察。
- 未把 mock upstream 当作真实上游 provenance：该测试只裁本代理 collector／routing／presentation，计划与 TUI Spec 均明确声明这一证据边界；无需改用 billed upstream 或 cassette。

## 搜索面与未覆盖面

已读主树两份 Specs、§10 计划、spec review disposition、项目与用户工作流规则；已读相关 delivery／observability／app-state／logging 源码及 unit／integration tests，并核对安装的 OpenAI SDK 3.3.1 `ResponseToolSearchCall.execution` 与 `ResponseFunctionShellToolCall.environment` discriminator。执行了只读 symbol／heading／path 搜索和 `CLAUDE_JOB_DIR` 存在性检查；没有修改主树，没有运行 Git 写操作，没有运行尚未实现的测试。未覆盖实际实施 diff、实际测试输出与 mutation 结果——它们不存在，须在实施候选形成后由 Task 10.6 的 implementation review 核验。

# Reasoning carrier Spec 实现可行性与路径一致性评审

评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`

源码范围：`/home/xp/src/ghc-api-proxy-py/src`；并以隔离 worktree 的提交 `e1b2baa99637349d2f552343c57769a311bfb179` 检查未提交 WIP 依赖。

## Verdict

**needs-fix**。没有发现需要推翻 typed v2 carrier 方向的 blocker，但有 6 项 major 必须在进入实现前落入 living Spec；当前文本尚不能保证一次实现、同一路径语义和完整 owner 覆盖。

执行说明：按要求首先调用 `Skill(my-agents:as-reviewer)`，harness 返回 `Unknown skill: my-agents:as-reviewer`；随后严格按用户给定 reviewer 角色与 C1–C9 检查项完成只读评审。未修改源码或 Spec。

## Major findings

### M1 — Streaming fallback 引用了不存在的 `content_index`，并漏掉 summary part 事件（C2、C7）
- Spec `spec.md:196-200` 要求按 `content_index` 分组，但 OpenAI 3.3.1 的四种 reasoning-summary 事件都用 `summary_index`；命令 `uv --directory /home/xp/src/ghc-api-proxy-py run python ...` 输出 `ResponseReasoningSummary{PartAdded,PartDone,TextDelta,TextDone}Event` 字段均含 `summary_index`，不含 `content_index`。
- 当前 assembler 只接收 `response.reasoning_summary_text.delta`，并把所有 delta 拼进 `Draft.text`（`src/app/pipeline/delivery/formats/openai_responses.py:492-500,556-560`）；cassette 搜索命令 `rg --count-matches ... 'response\.reasoning_summary_(?:part|text)\.' tests/int/cassettes` 返回 `rg_exit=1`，故仓内录制不能替错误字段背书。
- 必须把 authority 规则改为 `summary_index`，并明确 `output_item.done.item.summary`、`reasoning_summary_part.done`、`reasoning_summary_text.done/delta` 的优先级与空 part／extensions 合并规则；否则 closing item 缺 summary 时无法满足结构保真。

### M2 — Same-format 直通会绕过两槽 consumer，项目 carrier 可原样到达 provider（C3、C6）
- `routing.py:328-336` 以格式相同判定 `translation_required=False`；`driver.py:157-169` 只在需要翻译时调用 registry，`direct_driver/base.py:139-151` 随后直接发送 subscriber 处理后的 `context.payload`。buffered response 同样在 `reply.py:31-39` 对直通跳过 response registry。
- 这与 Spec `spec.md:39,159,167,169-173,190-192` 的“项目 carrier 绝不到 provider”冲突：Anthropic signature slot 和 Responses encrypted-content slot 都能在同格式路由绕过 decoder；这种路径也没有 `SemanticRequest.conversion` 可记录 `not-portable`。
- Spec 必须指定一个对两种 target 都生效的 resident pre-send／last-mile carrier pass、其错误时点与 loss sink：native opaque 原样通过，project carrier 只向 record 命名的目标恢复，其他情形在 send 前拒绝或按既定 foreign-state policy 省略并记录。

### M3 — 实施范围漏掉共享 streaming IR 与 last-mile subscriber 的实际 owner（C1、C2、C4、C5）
- Spec `spec.md:53-64,194-200` 要求 `ReasoningContent` 为共同 truth，但 buffered 使用 `translation_driver/content.py:43-86` 的 `ContentBlock`，streaming 仍使用 `delivery/assembling.py:149-160` 的 `Draft.text` 和 `delivery/blocks.py:67-83` 的 Anthropic-shaped `CompletedBlock.payload`；`spec.md:254-266` 未纳入后两位 owner，也未定义无泄漏 adapter。
- `destack_content()` 当前在路由前运行（`anthropic_request_hook.py:245-265`）；可行的 target last-mile 接缝是每次 attempt 的 `attempt.prepare`（`direct_driver/base.py:139-151`），counting 也确实发布它（`driver.py:275-298`），因此 direct Messages、translated-to-Messages、retry 与 counting 可统一覆盖。
- 但落地必须把新 subscriber 本体、`pipeline/subscribers/__init__.py:57-130` 的注册／顺序和 `server/composition.py:543-557` 的配置绑定列为 owner，并说明它与 blank-text pass 的顺序；同时明确 Draft/CompletedBlock 是加 typed 字段还是经同一 projection adapter 后才进入 wire-shaped payload。

### M4 — v2 grammar 未限定合法 record 组合，无法唯一恢复 block cardinality／顺序（C1、C3、C6）
- `spec.md:98-113` 允许任意不重复 records；`spec.md:132-143` 又允许 `anthropic.messages.thinking.signature` 与 `anthropic.messages.redacted_thinking.data` 各自恢复到不同 Anthropic block，却没有禁止二者出现在同一个 Responses-slot envelope。
- 一个 Responses reasoning item 若同时携带两条 record，consumer 无法判断应恢复一个还是两个 block，也无法恢复两者原顺序；这与 `spec.md:40,64,192` 的 cardinality／order lossless 条件相冲突。
- 必须定义 outer-slot 合法 record set、跨方向混合的分类，并至少规定 Responses slot 中 signature 与 redacted-data 互斥；对 grammar 合法但组合非法的 envelope 给出唯一的 malformed／direction／presentation 分类和失败时点。

### M5 — Summary 正控本身不是合法 wire fixture（C8）
- `spec.md:68-81` 规定每个合法 part 必须是 `{"type":"summary_text","text":"..."}`，但 `spec.md:231` 强制使用的正控 `[{"text":"一"},{"text":""},{"text":"😀二"}]` 全部缺少 `type`。
- 若 literal 喂 reader，它应得到 unsupported／invalid，而不是旧实现的“合并后丢边界”；若测试 helper 自动补 `type`，又没有直接验证真实 reader wire contract。
- 应把 fixture 改成三个完整 `summary_text` objects，并分别通过 buffered reader、streaming closing/delta 入口和 request-side decoder；`spec.md:224-246` 的独立静态向量、双方向与 last-mile capture 其余设计足以避免仅靠产品 codec 自证 roundtrip。

### M6 — 旧 helper 的处置仍是实现分叉，而不是单一语义委托（C5）
- 生产搜索 `rg ... 'responses_reasoning_to_anthropic|decode_anthropic_thinking|convert_*_responses' src` 显示 `app/anthropic/thinking/responses_reasoning.py` 只被两个旧 `app/protocols/*` bridge 导入；active registry 走 `translation_driver/registry.py:139-165`，但 `translation_driver/responses.py:25-28` 又使旧 response module 因 usage helper 被生产态加载。
- Spec `spec.md:38,192,265` 只说统一／涉及兼容模块，没有裁定删除还是委托；现状 tests 仍直接锁定旧 helper（`tests/unit/anthropic/test_responses_reasoning.py`、`tests/unit/protocols/test_responses_anthropic_nonstream.py`、`tests/unit/anthropic/test_anthropic_responses_request.py`）。
- 建议本 patch 删除独立 reasoning helper 语义并迁移这些 tests 到 active core；若旧 protocol facades 暂留，则其 reasoning entrypoints 必须成为对统一 typed codec/projection 的薄委托，禁止另写 v2 分支。

## C1–C9 逐项结论

| Criterion | 结论 | 依据 |
|---|---|---|
| C1 | 设计足够，owner 未闭合 | `spec.md:53-85` 的 `visible_text + summary_parts + opaque_state + carrier_records + source_format + raw` 能恢复 `_summary_text()` 在 `openai_responses.py:522-568` 丢掉的 cardinality／empty／extensions；普通 message/function/tool 分支独立于 reasoning（`openai_responses.py:498-521,655-687`）。M3 必须补 streaming owner。 |
| C2 | 不通过 | buffered 的 `blocks_from_item()/item_from_block()` 与 streaming 的 `ResponsesAssembler/ResponsesFramer` 有共同 codec 可调用，但当前 streaming state 仍在 `Draft.text`，且 Spec 的 delta key/authority 错误；见 M1、M3。 |
| C3 | cross-format 路径可挂载，lifecycle 不完整 | request registry 在 `driver.py:157-169`、buffered response registry 在 `reply.py:31-41`、streaming 的 upstream assembler/client framer 交叉选择在 `delivery_policy.py:77-138`，所以 Anthropic→Responses client→Anthropic upstream 的标准反向路径可实现；same-format 绕过见 M2。 |
| C4 | 可实现，需补 owner／顺序 | 当前过早调用点为 `anthropic_request_hook.py:245-265`；`attempt.prepare` 在 direct、translation 后、每次 retry 与 counting 均可达（`direct_driver/base.py:139-151`、`driver.py:275-298`），并能以 `RequestContext.target_format`（`request.py:77-85`）只作用于 Anthropic target，因此不会向 Responses 注入 separator；见 M3。 |
| C5 | 不通过 | `spec.md:254-266` 未覆盖 `delivery/assembling.py`、`delivery/blocks.py`、subscriber 注册与 composition owner；旧 helper 处置未裁定。见 M3、M6。 |
| C6 | 架构可表达，但直通与组合规则缺失 | `Conversion.lossless` 由 loss 列表决定（`translation_driver/semantic.py:98-115`），`LossCode.REASONING_STATE_NOT_PORTABLE` 已存在（`:33-70`），`TranslationRefused` 可在 upstream 前携带稳定 code/path（`:73-84`）；same-format 没有 Conversion owner且组合分类不唯一，见 M2、M4。 |
| C7 | 不通过 | closing item 可在 `_close()` 取得（`delivery/formats/openai_responses.py:566-683`），但当前 delta 合并不看 part index；OpenAI SDK 3.3.1 声明的 wire model 使用 `summary_index` 并另有 part added/done，而仓内 Copilot cassettes 对这组事件没有样本；见 M1。 |
| C8 | 一处 major 后可满足 | `spec.md:224-246` 已区分 producer/consumer 静态向量、buffered/streaming、双 carrier 方向及 provider last-mile capture，且禁止 consumer expected 由产品 encoder 生成；唯一直接冲突是非法正控，见 M5。 |
| C9 | 通过，不依赖当前 WIP | `git -C /home/xp/src/ghc-api-proxy-py/.claude/worktrees/agent-aa13878caa6ad9658 rev-parse HEAD` 得 `e1b2baa99637349d2f552343c57769a311bfb179`。对 10 个相关 owner 逐文件 `cmp`：reasoning carrier/content/responses/delivery/request-hook/subscriber/composition 与主树相同；三份差异输出只涉及 `translation_driver/{anthropic_messages,openai_responses}.py` 的并行 tool-choice／tool-result WIP和 `driver.py` 的 count observability WIP。实现可从该提交独立起步且不依赖这些 WIP；后续集成需按同文件 hunk 合并，但这不是语义依赖。 |

## 定稿前最小处置顺序

1. 先修 M1、M4、M5 的 wire 与验收文本，使 codec 输入、状态机和 oracle 唯一。
2. 再把 M2、M3 的 pre-send owner、streaming state owner、subscriber 注册／顺序写入 §9、§10、§13。
3. 最后在 §11／§13 明确 M6 的 delete-or-delegate 决策及旧 tests 迁移；完成后可再次做一次只看修订 clauses 的规格复评。

边界结清判断：本轮是只读 Spec／源码评审，唯一产物为本报告；未创建 test-only 资产、未改源码或 Spec、未产生 commit／临时分支，因此没有额外归档、清理或删除事项，不启动完整 closeout。

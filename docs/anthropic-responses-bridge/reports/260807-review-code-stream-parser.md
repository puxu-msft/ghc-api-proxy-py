# Responses stream parser 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-stream-parser`，branch `feat/responses-stream-parser`，HEAD `af5956be47ecf222ecd25c044436a36656206bce`，相对用户指定 base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 的唯一提交 `feat: assemble Responses stream events`。改动仅含 `src/app/openai/responses_stream_parser.py` 与 `tests/unit/test_responses_stream_parser.py`。按 happy-path 骨架切片评审，不要求全 grammar；重点覆盖 text／tool／reasoning event identity、complete-only 产出、authoritative done、交错顺序事实、terminal 不伪造、unknown typed failure、对象不可变、后续 sequencer API 与 smoke 假绿。
- **总体 verdict**：**修复 major 后可进入；当前不可 squash。** blocker 0、major 1、minor 2。核心 text／tool／reasoning complete-only 组装大体成立，semantic DTO 为 frozen dataclass，authoritative text／tool value 有基本一致性检查；但跨 block 类型的 source-order 事实在 API 层不成立，独立 sequencer 无法在保持完整 block 与增量提交的同时可靠决定连续前缀。用户要求的“0 major 明确可 squash”条件未满足。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：2。
- **双视角覆盖证据——机械核对**：完整阅读新增实现与测试；对账 finalized Spec／Architecture 中的 block identity、complete-only、authoritative done、source-order、terminal、unknown 与 sequencer 边界；扫描全部 event dispatch、draft 创建点、completion 条件、terminal `open_blocks` 与 frozen DTO；核对提交谱系、变更路径与候选树 clean 状态。定向 pytest 在进程内断言实际导入 `/home/xp/src/ghc-api-proxy-py-stream-parser/src/app/openai/responses_stream_parser.py` 后得到 `7 passed`；全仓 pytest 得到 `372 passed`；另以 pytest collect-only 交叉核对为 `7 tests collected` 与 `372 tests collected`；另以 pytest collect-only 交叉核对为 `7 tests collected` 与 `372 tests collected`；Ruff 为 `All checks passed!`；Pyright 为 `0 errors, 0 warnings, 0 informations`。这些数字的口径均为候选 HEAD `af5956b…`，使用主仓 `.venv` 的 Python 且 `PYTHONPATH` 指向候选 `src`。
- **双视角覆盖证据——第一人称执行**：模拟后续 sequencer 消费“先 added 的 message 尚无 content event，后 added 的 function call 已完整 done，再完成 message”的真实交错流程；模拟仅收到 message item added 后直接收到 `response.completed`；模拟 unknown item added／done／terminal；模拟 reasoning part done 与 item done 两层 authoritative value 不一致；并走过 text、function call、reasoning 的正常 delta→done→item done、terminal 后再来 event、对象外部赋值失败等路径。

## 事实性发现

### [major] `src/app/openai/responses_stream_parser.py:140-234,388-408,530-534` — `first_observed_order` 不是统一的 source-order 事实，且 API 不发布前置占位，后续 sequencer 无法安全提交

**问题**：function call／reasoning 在 `response.output_item.added` 时立即取得 `first_observed_order`，message text 却直到第一条 text delta／done 才取得；`response.output_item.added` 对已知 item 一律返回空 tuple。于是同一字段在不同 block kind 上代表不同生命周期时点，且消费者在较早 message 尚未出现 content part 时看不到任何“前方有未完成 item／block”的 typed 事实。

**可复现证据**：在候选 HEAD 上依次输入：

1. `output_item.added(output_index=0, message msg_a)`；
2. `output_item.added(output_index=1, function_call fc_b)`；
3. `fc_b` arguments done；
4. `fc_b` item done；
5. `msg_a` text done。

实际先产出的 tool block 为 `BlockIdentity(output_index=1, ...)`、`first_observed_order=0`、`completion_order=0`；随后较早 source item 的 text block 为 `BlockIdentity(output_index=0, ...)`、`first_observed_order=1`、`completion_order=1`。这不是仅靠 sequencer “改用 output_index 排序”就能完整修复：一个 message item 可有多个 `content_index`，而 parser 在 content event 到来前没有发布其 part identity 或 item-open 占位；若 sequencer 立即提交已完成的 tool，会越过较早 message，若等待未知的更早 part，则缺少可证明何时可前进的 API 合同。

**现有 smoke 为何假绿**：`tests/unit/test_responses_stream_parser.py:155-202` 的 interleave 用例只覆盖 message／message，并在任一 block 完成前按 source 顺序先发送两个 text delta，恰好让两个 text drafts 依次取得 0、1；它没有覆盖 message／tool 或 message／reasoning 的跨类型 draft 创建时点，也没有断言 sequencer 在较晚 block 先完成时必须看到前置 open identity。

**失败场景**：后续 block-level sink 若按 `completion_order` 或当前 `first_observed_order` 提交，会把 tool B 发在 text A 前；若尝试按当前可见 completed blocks 的 `(output_index, content_index)` 排序，B 完成时尚不知道 A 是否会产生哪个 content part，仍可能提前提交。该缺陷直接破坏用户指定的“交错顺序事实”和“API 可供后续 sequencer”，因此当前不可 squash。

**修复建议**：先冻结 parser→sequencer 的 typed 合同，再实现统一顺序事实。至少应满足：所有 semantic source identities 在同一生命周期层分配 order；已知 item added 能向 sequencer 建立 open item／known source-order 占位；message content part 出现后以 `(source item order, content_index, semantic kind)` 形成稳定 block key；item done／terminal 能明确关闭“不再会出现更早 part”的边界。不要让 sequencer从“没有事件”猜测空洞。新增跨类型正反样本：message A 先 added 但无 delta，tool／reasoning B 后 added且先完成，A 后完成；B 在 A 前不得可提交，A 完成后连续前缀固定为 A、B。再用故意恢复当前异步 order 分配的缺陷注入证明测试按目标原因变红。

### [minor] `src/app/openai/responses_stream_parser.py:359-386,537-551` — terminal 会把仅已 added 的 message item 报成没有 open block

**问题**：`_open_blocks()` 只扫描已经创建的 `_TextDraft`、未 emitted function call 与 reasoning draft；message item 在收到首个 text event 前只有 `_ItemDraft`，不会进入 `open_blocks`。因此 `output_item.added(message)` 后直接 `response.completed` 会产出 `ResponsesTerminal(kind="completed", open_blocks=())`。

**证据或失败场景**：只输入 message item added，再输入 completed terminal，已复现实得 `open_blocks=()`。这会让 driver／sequencer把 malformed lifecycle 看成合法零 content 成功，违反“terminal 不补造也不掩盖未闭合 block”的目标。它与 major 共用“item-open 占位缺失”的根因，但 terminal 表达还需独立回归测试。

**修复建议**：让 item lifecycle 有显式 open／done 状态，并在 terminal 处要么返回能表达未闭合 item 的 typed identity，要么直接抛稳定的 malformed lifecycle error；不能用空 `open_blocks` 表示“无待处理语义”。补一条 added-only message→completed 的负例，并保留合法零 content response 的独立正例，防止判据过严。

### [minor] `src/app/openai/responses_stream_parser.py:184-270,537-551` 与 `tests/unit/test_responses_stream_parser.py:204-250` — unknown item 只在 added 阶段 typed，后续 done 静默返回且 completed terminal仍可伪装正常成功

**问题**：unknown item added 会写入 `_items` 并返回 `UnsupportedResponsesEvent`；同一 unknown item 的 `response.output_item.done` 通过 identity／type 校验后落到 `_on_output_item_done()` 末尾 `return None`，`process()` 因而返回空 tuple。terminal 的 `open_blocks` 又不包含 unknown item。现有测试只断言 unknown added 和无关 future delta typed，随后明确期待普通 completed terminal与空 `open_blocks`，没有走 unknown item done。

**证据或失败场景**：一个 strict consumer若逐 event 检查 typed unsupported，只能看到 added 的 observation；若调用方未在第一条 observation 立刻中止，后续 lifecycle 与最终 terminal会恢复成“正常完成”的表象。Parser API 没有给出“该 attempt 已被 unsupported item 污染／必须失败”的持续 typed fact，也没有保证 unknown 的每个相关事件保持 typed。

**修复建议**：在当前 strict Spec 下，unknown output item应在首次识别时产生稳定 protocol／conversion failure，或记录 attempt-local fatal unsupported state并保证 done／terminal不能恢复成 success。若 parser层有意只发布 observation而由 driver决定失败，则必须把该义务写入返回类型合同，并让 unknown done 与 terminal继续携带可机械关联的 typed state。补 unknown added→done→completed 的端到端负例；不要只测孤立 added event。

## 后续非阻断边界缺口

以下不升级为本轮 major，因为用户明确要求 happy-path 骨架切片而非全 grammar；但应在 parser 合同扩展时进入后续 backlog：

- `src/app/openai/responses_stream_parser.py:249-303,445-528`：reasoning summary part done 与 item done summary不一致时，当前无交叉校验，item-level 值静默覆盖 part-level authoritative 值。已用 `part-value`／`item-value` 复现产出 `item-value`。需先用 OpenAI capture／官方事件合同确认两层都应相等还是 item done才是唯一 oracle，再决定 mismatch failure；不要凭实现偏好升级 grammar。
- function argument deltas目前只收集、不与 authoritative arguments交叉核对；tool happy path仍以 authoritative done值产出，未造成 partial block，但后续 strict malformed lifecycle gate应决定 delta mismatch是否为错误。
- 缺 refusal content part、clean EOF／`[DONE]` 等属于 framing／完整 grammar切片，不作为本次 parser骨架 squash门；接入 SSE framing时必须单独评审。

## 主观建议

### [建议] `ResponsesStreamParser.process()` 返回契约 — 区分 observation、fatal protocol failure 与 semantic completion

**预期影响**：当前 tuple union 把 `CompletedBlock`、unknown observation 与 terminal放在同一平面，调用方还需猜“unsupported是否只是记录还是必须中止”。随着 sequencer／driver接入，这会把 strict unknown policy和terminal真值散落到调用方。

**推荐做法**：保留 immutable semantic DTO，但考虑用明确 discriminated event variants表达 `SourceOpened`／`BlockCompleted`／`UnsupportedFatal`／`Terminal`，或让 strict unknown直接抛稳定 typed protocol error。重点不是增加类数量，而是让消费者无需查实现即可知道哪些事件推进顺序、哪些终止 attempt、哪些只作诊断。

## Smoke 真假绿结论

现有 smoke **真执行、但对关键 invariant 假绿**：

- 真执行：候选进程内 source oracle精确指向候选 parser；定向 `7 passed`，全仓 `372 passed`，Ruff与Pyright均绿，候选树评审后保持 clean。
- 假绿原因：测试只证明已枚举的同类型 happy paths。跨类型交错反例让实现返回错误 `first_observed_order`，added-only message terminal反例让实现返回虚假的空 `open_blocks`，但全套测试仍绿；因此绿色 suite不能支持“sequencer API已可用”或“terminal不伪造”的结论。
- 修复后的最低可信门：新增上述跨类型顺序与 malformed terminal测试；先在正确样本为绿，再注入“message晚分配 order／terminal漏 item-open”的目标缺陷并确认按目标原因变红，恢复后重跑定向、全仓、Ruff、Pyright。

## 放行结论

当前 **blocker 0、major 1，不可 squash**。修复统一 source-order／open-source API并补有判别力的跨类型 sequencer测试后，连同两个 minor一起复评；只有新 HEAD达到 0 major，才可按用户条件明确标记 **可 squash**。本轮未修改候选树，唯一写入为本报告。

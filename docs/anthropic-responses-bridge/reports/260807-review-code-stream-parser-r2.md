# Responses stream parser 独立代码定向复评 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-stream-parser`，branch `feat/responses-stream-parser`，HEAD `73a6aa114647440262691651cd17e9127785c75a`，相对用户指定 base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`；定向复核上一轮 `docs/tmp/260807-review-code-stream-parser.md` 的 `1 major + 2 minor`，并检查修复提交 `73a6aa1 fix: preserve Responses stream source order` 引入的新问题。评审对象仍是 Responses event assembler／sequencer 前置骨架，不把 clean EOF、SSE framing、refusal、严格事件先后或完整 grammar 纳入本轮 squash 门。
- **总体 verdict**：**可进入下一阶段；骨架可 squash。** blocker 0、major 0、minor 0。上一轮 `SourceOpened`／跨类型 source-order major、added-only message terminal minor、unknown item lifecycle minor 均已关闭；未发现修复增量引入新的骨架级问题。此 verdict 只放行当前 parser semantic-facts 骨架，不表示完整 Responses stream grammar 已实现或已验收。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：完整阅读最终 `src/app/openai/responses_stream_parser.py` 与 `tests/unit/test_responses_stream_parser.py`，对比上一轮 HEAD `af5956be47ecf222ecd25c044436a36656206bce` 到 current HEAD 的修复 diff；扫描 current HEAD 内 `ResponsesStreamParser`、`SourceOpened`、`open_blocks`、`first_observed_order` 的全部生产者与消费者，确认 feature 内尚无生产消费者，只有 parser 与单测使用新 API；对账 Spec 的 complete-only／authoritative done／unknown typed policy 与 Architecture 的 continuous-prefix sequencer 边界。候选导入 oracle 精确指向 `/home/xp/src/ghc-api-proxy-py-stream-parser/src/app/openai/responses_stream_parser.py`。在 current HEAD 上，定向 pytest 实跑 `11 passed`，全仓 pytest 实跑 `376 passed`，并以 collect-only 分别交叉核对为 `11 tests collected` 与 `376 tests collected`；Ruff 为 `All checks passed!`；隔离进程组 Pyright 退出码为 0。上述数字口径均为 current HEAD、主树 `.venv` Python、`PYTHONPATH` 绑定候选 `src`，pytest 禁用无关插件自动发现并显式加载 `pytest-asyncio`；最初两次 Pyright 被共享终端的外部 `SIGINT` 中断，未计入结论。
- **双视角覆盖证据——第一人称执行**：模拟 message A 在 `item.added` 打开但尚无 content event，后加入的 function call／reasoning B 先完整完成，再由 message A 完成并关闭 item；模拟 added-only message 直接遇到 `response.completed`；模拟 unknown item 的 added→done→completed 全生命周期；模拟后续 sequencer 只根据 `SourceOpened`、`CompletedBlock` 与 `open_blocks` 判断连续可提交前缀。另以进程内 monkeypatch 分别破坏 source-order 分配、`open_blocks`、unknown done typed result 与 unknown terminal 降级，四个目标用例均按对应机制变红，恢复后目标用例全绿且候选树保持 clean。

## 事实性发现

未发现问题。

## 上一轮发现逐条处置

### [已关闭 major] `src/app/openai/responses_stream_parser.py:46-49,146-200,425-440,579-602` — `SourceOpened` 在 `item.added` 发布统一 item 级 source-order 屏障

**关闭证据**：已知 message／function call／reasoning 都在 `response.output_item.added` 时取得唯一 `source_order`，并立即返回 immutable `SourceOpened(BlockIdentity(output_index, item_id, None), source_order)`；message 后续 text draft 复用所属 item 的 `source_order`，不再按首条 text event 晚分配。`open_blocks` 在 item done 前保留 item 级 identity，因此后加入且先完成的 tool／reasoning block不能隐藏较早 message 的未完成屏障。

**执行证据**：`tests/unit/test_responses_stream_parser.py:204-269` 分别覆盖 message A→function call B 与 message A→reasoning B，B 先完成时 `parser.open_blocks` 仍为 A，A 完成并收到 item done 后才清空。将 `_take_source_order()` 变异为恒定 0 时目标用例按 source-order 断言变红，证明新增测试不是只检查对象存在。

**边界说明**：`SourceOpened` 是 item 级顺序事实，不是可下游交付的完整 block；同一 message 的 content parts仍由后续 sequencer结合 `content_index` 排序。当前 feature 尚无生产 sequencer consumer，因此本轮验证的是骨架 API 具备必要 typed facts，不是完整交付链已接线。

### [已关闭 minor] `src/app/openai/responses_stream_parser.py:133-135,384-409,579-602` — added-only message 不再被 terminal 报成无 open block

**关闭证据**：`_open_blocks()` 先枚举所有 `not item.done` 的 item 级 identity；`response.completed` 若存在 open block，会转换为 `ResponsesTerminal(kind="incomplete", error_code="incomplete_lifecycle", open_blocks=(identity, ...))`，不再伪装合法零 content success。

**执行证据**：`tests/unit/test_responses_stream_parser.py:272-291` 固定 added-only message→completed 的 expected terminal。将 `_open_blocks()` 变异为恒空 tuple 后，该用例按 terminal 真值断言变红。

### [已关闭 minor] `src/app/openai/responses_stream_parser.py:200-236,384-405,579-602` — unknown item done 保持 typed，completed terminal 不恢复成功

**关闭证据**：unknown item 在 added 时记录 `unsupported=True`；其 `output_item.done` 完成统一 identity／type／duplicate-done 校验后继续返回 `UnsupportedResponsesEvent`；terminal 检测 attempt 内任一 unsupported item，把原 `response.completed` 转为 `kind="incomplete"`、`error_code="unsupported_output_item"`，并保留该 item identity 于 `open_blocks`。

**执行证据**：`tests/unit/test_responses_stream_parser.py:294-329` 覆盖 unknown added→done→completed。分别变异为吞掉 unknown done result、允许 unknown terminal success时，同一用例分别按 typed result与 terminal 真值变红。

## 新问题扫描

未发现修复增量引入新的 blocker、major、minor。机械扫描确认：新增 `_ItemDraft.source_order／done／unsupported` 由单一 item lifecycle 维护；`SourceOpened`、`CompletedBlock`、`ResponsesTerminal` 均为 frozen DTO；已知 item 的重复 done 统一进入 `duplicate_done`；unknown item不会在 done或 terminal阶段静默恢复为普通成功；`open_blocks` 按 source order与 content index稳定排序。

## 完整 grammar 后续边界

以下仍是明确的后续工作，不影响本轮骨架 squash，也不得被本轮 0 major 误写为已经完成：

- current parser仍接受 message `output_item.done` 之后才到达的 `output_text.done`。只读反例实跑确认该 late content仍产出 `CompletedBlock`；完整 grammar需冻结事件先后并决定稳定 protocol error。
- message item added→item done、从未出现 content part→`response.completed` 当前得到合法 completed terminal与空 `open_blocks`。这可能是合法零 content response，也可能是 malformed message lifecycle，必须由 raw capture／官方协议合同与完整 grammar裁决，不能由本轮骨架自行猜测。
- 上一轮已记录的 reasoning part done与item done summary一致性、function argument delta与authoritative arguments一致性、refusal content part、clean EOF／`[DONE]`、CRLF／multi-line `data:`／fragmentation、truncation与完整 terminal grammar仍待后续实现及独立验收。
- 任意 future unknown event目前可作为 typed observation后继续成功；完整 strict grammar需按事件类别冻结“记录并忽略／extension bag／fatal”的 policy。当前关闭项仅保证 unknown output item 的 added→done→terminal lifecycle不会失去 typed failure事实。

## 结构怪味扫描

- `src/app/openai/responses_stream_parser.py:41-49,425-440` — **同一顺序事实存在 `first_observed_order` 与 `source_order` 两个名称** — **后续 grammar／sequencer接线时统一或明确注释，不阻断本轮**。当前两者值同源且测试固定语义，没有造成错误；但 production consumer接线后若把 `first_observed_order` 误解为 content-part首次观察顺序，可能重新引入歧义。
- `src/app/openai/responses_stream_parser.py:384-405` — **terminal 内直接承载 strict unknown／incomplete policy** — **完整 grammar阶段评估是否抽成 typed policy，不阻断本轮**。当前逻辑局部、可读且满足本轮关闭项；当 unknown event分类扩展后，继续堆叠条件会让 parser兼任 policy engine。

## 主观建议

### [建议] sequencer 接线时把 `SourceOpened` 明确命名为 item-level barrier

**预期影响**：避免 consumer 把 `content_index=None` 的 identity当成可渲染 block，或误以为一条 `SourceOpened` 等于 message只有一个 content part。

**推荐做法**：在 sequencer contract或类型命名中明确“opened source item／commit barrier”，并用集成测试固定“item barrier 保持到 authoritative item done；已观察 content parts按 content index展开；只有连续完成前缀可交付”。不要让 consumer从空事件或稀疏 `output_index` 自行猜测。

## 最终放行结论

**blocker 0、major 0、minor 0；当前 Responses stream parser 骨架可 squash。** 本结论只覆盖 HEAD `73a6aa114647440262691651cd17e9127785c75a` 的 semantic-facts 骨架及上一轮 3 项修复；完整 grammar、framing、strict lifecycle 与生产 sequencer接线继续作为后续独立工作，不得沿用本报告替代其验收。

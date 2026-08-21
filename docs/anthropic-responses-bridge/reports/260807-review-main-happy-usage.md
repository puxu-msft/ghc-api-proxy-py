# current main happy／usage merged-state 独立评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。只评审刚回放的 reasoning carrier＋direct Messages strip、Responses→Anthropic non-stream converter、Responses stream semantic parser、typed route policy、non-stream usage facts，以及它们与既有 foundations／systemd 的合并态接缝；不把尚未实现的完整 Anthropic→Responses route、block delivery、graceful timeout 或 systemd user install 当成本轮实现范围。
- **总体 verdict**：**修复 major 后可继续真实 route 接线。** 当前切片不能以 merged-state 直接进入真实 route 接线：同一空 reasoning item 在 non-stream 与 stream semantic core 中产生不同 block 集合，stream parser 还会接受互相冲突的 authoritative lifecycle 值。完整 route 尚未接线，因此候选产品及完整 bridge 继续为 **`UNVERIFIED`**；这项状态不计作本轮缺陷。
- **blocker 数**：0。
- **major 数**：2。
- **双视角覆盖证据——机械核对**：每次承载结论的 shell 调用均在同一调用中打印并验证物理 root、`pwd`、分支与完整 HEAD；逐文件读取 carrier、direct strip、request／response converter、stream parser、route policy、usage facts及其测试；检索生产消费者，确认 route policy、stream parser 与 `ResponseUsageFacts` 当前只被测试消费，符合“完整 route 未接”的已知边界；对五个 replay commit 与对应 archive ref 做拓扑、路径、patch-id及最终 blob 对账。前四个 replay commit因把 archive 上的后续修复压入单个语义提交而 patch-id 不同，但其全部目标实现／测试 blob与 archive tip逐文件相等；usage replay commit与 archive tip patch-id及目标 blobs均相等。定向 pytest覆盖 carrier、direct strip、request converter、non-stream converter、stream parser、route policy、happy-path usage、CLI与systemd units并通过；完整测试收集口径为 `tests` 下 434项，但此前完整运行的 shell最终退出码被共享终端中断为130，故不把该次“434 passed”文本当作本报告放行证据。
- **双视角覆盖证据——第一人称执行模拟**：按真实使用顺序模拟了 direct Messages发送前剥离项目／upstream synthetic carrier并保留native signature；模拟 Responses non-stream reasoning／text／tool／usage转换；按 `.added → delta／done → item.done → terminal` 驱动stream parser，覆盖交错source order、empty／summary-only／encrypted-only reasoning及冲突authoritative值；按resolved model、override、endpoint capability与transport availability走route真值表；最后以“未来真实route把这些模块串起来”为执行者视角比较stream／non-stream normalized blocks与usage facts。完整route尚未存在，所以没有把helper／smoke通过外推为route-level产品符合性。

## 事实性发现

[major] `src/app/anthropic/thinking/responses_reasoning.py:38-69`、`src/app/openai/responses_stream_parser.py:485-505` — 空 reasoning item 在 non-stream 与 stream 路径中产生不同 normalized content — 对同一上游语义 `{type: "reasoning", summary: []}`，non-stream helper无条件追加一个 `thinking=""`＋项目bare marker block，而stream parser在summary为空且无`encrypted_content`时返回零个`CompletedBlock`。独立运行探针得到 `EMPTY_REASONING_NONSTREAM_BLOCKS=[{"type":"thinking","thinking":"","signature":"ghc-api-proxy:synthetic-reasoning:v1"}]`、`EMPTY_REASONING_STREAM_EVENTS=()`、`PARITY=False`。这违反Spec `spec.md:255,277`的stream／non-stream归一化等价合同，也与Acceptance `acceptance.md:139`中“empty payload且无summary不凭空制造可恢复block”冲突；真实route若分别接入两条路径，同一Responses结果会因客户端stream开关而改变content cardinality — 修复建议：把“reasoning item是否形成semantic block”的判定下沉为两条路径共享的单一normalizer／constructor；按冻结Acceptance让空summary＋无／空payload产生零block，并新增同一fixture同时走non-stream与stream的独立parity回归测试。

[major] `src/app/openai/responses_stream_parser.py:336-347,362-380,508-555` — parser接受彼此冲突的delta done与item done authoritative值，静默选择后到值 — function path在`response.function_call_arguments.done`只保存`arguments`，没有与此前累计delta比较；reasoning path虽校验summary delta与`summary_text.done`，但`response.output_item.done`随后直接以item summary覆盖该结果，也没有一致性检查。最小探针中，function delta为`{"a":1}`而两个done为`{"a":2}`时仍产出`FunctionCallBlock(arguments='{"a":2}')`；reasoning `summary_text.done="first"`而item done summary为`"second"`时仍产出`ReasoningBlock(summary='second')`。Spec `spec.md:185,297,322-325,387`要求malformed lifecycle显式拒绝、delta与authoritative data进入同一assembler，并禁止以正常terminal掩盖冲突；当前行为会让损坏或实现漂移的上游事件被悄然改写为成功block。现有parser测试只覆盖一致值，未覆盖这两个冲突分支 — 修复建议：在function arguments done时比较累计delta与authoritative arguments；在reasoning item done时把逐summary-index的authoritative part与item summary作一致性核对，冲突抛稳定typed protocol error。分别新增function与reasoning mismatch回归，并保留合法“无delta、仅authoritative done”的正样本，避免修成false-red。

## 主观建议

未提出主观建议。本轮两个结论均有冻结Spec／Acceptance和可重复运行探针支撑；未以完整route未接线、测试资产尚未全落地或Architecture尚未获用户接受制造额外发现。

## 合并态与后续边界

- **commit／archive**：五个replay commit的目标最终内容与对应archive tip一致；未发现漏文件、错误archive ref或commit内容与目标切片不符。前四个patch-id差异由squash纳入后续fix造成，最终blob对账已确认内容一致。
- **foundations／systemd回归**：本轮定向集包含既有reasoning/request foundations、CLI与systemd unit tests，均通过；未发现本次五个replay切片对既有foundations/systemd的回归。
- **结构怪味处置**：`src/app/anthropic/thinking/responses_reasoning.py:38-69`＋`src/app/openai/responses_stream_parser.py:485-505`为“同一语义规则双实现且行为漂移”，本轮记为major并要求route接线前修；`src/app/openai/responses_stream_parser.py:336-380,508-555`为“authoritative来源未统一校验”，本轮记为major并要求在parser共享基座修复。其余扫描范围为五个replay切片全部实现与测试、direct strip接缝、foundations/systemd定向回归，未发现第三处blocker／major级结构怪味。
- **状态边界**：即使修复上述major，本报告也只允许“继续真实route接线”，不把产品升级为`PASS`。完整route、block delivery、usage/history observer、retry／lifecycle与route-level Acceptance仍须在接线后独立验收；在此之前完整bridge保持`UNVERIFIED`。

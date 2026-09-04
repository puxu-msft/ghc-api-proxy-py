# Semantic parity 独立验收 R2

- **验收对象**：`/home/xp/src/ghc-api-proxy-py-semantic-parity` 的 `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`。
- **冻结 oracle**：候选树与主树的 `docs/agents/anthropic-responses-bridge/spec.md` SHA-256 均为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；文档状态为 `FINALIZED`。另采用用户最终裁决 `docs/tmp/260807-arbitrate-empty-reasoning.md`：empty reasoning 在 stream／non-stream 均为恰好一个 `thinking=""` bare carrier block。
- **总体判定**：**PASS**。
- **缺陷数**：未发现阻断缺陷或行为偏差。
- **写入边界**：候选树全程只读，验收前后均为固定 HEAD 且 tracked／untracked clean；本轮唯一新增文件为主树本报告。

## 独立验收矩阵

| 验收项 | 从 Spec／最终裁决推导的 expected | 独立运行结果 | 判定 |
|---|---|---|---|
| empty reasoning，`encrypted_content` absent | stream 与 non-stream 各恰好一个 `thinking=""` block，signature 为项目 bare marker；echo 后恢复 `summary=[]`，不伪造 `encrypted_content` | non-stream public content 精确为一个 bare block；stream `item.done` 精确产生一个 `ReasoningBlock("", None)`，经项目 producer 渲染为同一 bare block；echo 无 ciphertext | PASS |
| empty reasoning，`encrypted_content=""` | 与 absent 同义，仍各恰好一个 bare block | 两条路径与 absent 得到相同精确结果 | PASS |
| non-empty encrypted-only | 两条路径各恰好一个 `thinking=""` payload carrier block；echo 后 `encrypted_content` value-exact | 使用含 Unicode、NUL 与 padding-like bytes 的 `opaque-😀\x00ENC==`；两条路径 carrier 相同，echo value-exact | PASS |
| unknown／future reasoning summary part | non-stream 与 stream 均 typed `REJECT`，不得静默接受 | `future_summary` 与 `unknown_summary_v2` 均触发 non-stream `ResponseConversionError(code="invalid_reasoning", field_path="output[0]")`；stream 均触发 `ResponsesStreamProtocolError(code="invalid_reasoning", event_type="response.output_item.done")` | PASS |
| function arguments authoritative 冲突 | typed `REJECT` | delta `{"x":1}` 与 authoritative `{"x":2}` 冲突触发 `authoritative_arguments_mismatch`，event type 为 `response.function_call_arguments.done` | PASS |
| reasoning authoritative 冲突 | typed `REJECT` | summary-part done 为 `first`、item.done authoritative 为 `second` 时触发 `authoritative_reasoning_mismatch`，event type 为 `response.output_item.done` | PASS |
| item.done-only function | 没有 argument delta／arguments.done 事件时，只要 item.done 携带完整 authoritative arguments，仍合法完成一个 function block | item.done 单独携带 `{"city":"Paris"}`，精确产生一个 `FunctionCallBlock`，call id、name 与 arguments 均 value-exact | PASS |
| 静默接受 unknown 正控 | 临时把两条 unknown-summary gate 改为 permissive 后，上述 typed-REJECT 验收必须转红；恢复后必须转绿 | 仅在隔离 Python 进程内 monkeypatch non-stream producer 与 stream summary parser；两条验收均以 `silent_unknown_acceptance` 原因按预期转红；恢复原对象后两条均重新 typed `REJECT` | PASS |

## Spec 对应关系

- `docs/agents/anthropic-responses-bridge/spec.md:185` 将未知 output item／content part 固定为 `REJECT`；`:550` 明确排除 unknown item silent drop。
- `docs/agents/anthropic-responses-bridge/spec.md:204,325` 要求每个 reasoning item 一对一形成 thinking block，并明确 summary-only 与非空 encrypted-only 均保持一 item 一 block，空 ciphertext 与 absent 同义。
- `docs/agents/anthropic-responses-bridge/spec.md:277` 要求 stream／non-stream 对相同 fixture 的 normalized message 等价。
- `docs/agents/anthropic-responses-bridge/spec.md:324` 允许 function call 在 item.done 到达且 authoritative arguments 完整时完成，并要求 arguments strict conversion。
- 最终用户裁决进一步消除了 empty reasoning 的旧歧义：empty item 不是零 block，而是一个 bare block。

## 实现接缝证据

- Non-stream reasoning conversion 在 `src/app/protocols/responses_anthropic.py:107-112` 调用逐-item producer；producer 在 `src/app/anthropic/thinking/responses_reasoning.py:43-80` 对每个 reasoning item独立构造 block，并在 `:61-64` strict gate summary part type。
- Stream authoritative item.done 在 `src/app/openai/responses_stream_parser.py:255-300` 完成 function／reasoning；function 完成与 authoritative conflict gate 位于 `:478-493,513-546`。
- Stream summary part strict gate 与 authoritative conflict gate 位于 `src/app/openai/responses_stream_parser.py:552-599`。
- 候选已有回归分别位于 `tests/unit/test_responses_stream_parser.py:156,175,290,321,357`；这些测试只作为补充证据，核心 verdict 来自上述独立 runtime probe 和正控。

## 实际执行与结果

初始身份门在同一次 shell 调用内验证物理 root、分支、完整 HEAD 与 clean 状态；后续每轮候选运行均在对应调用内至少复核完整 HEAD 与 clean 状态，定向回归与全量 gate 另外重复验证物理 root、分支和工作目录。采纳为证据的运行退出码均为零。

1. **身份门**：候选 root、`fix/responses-semantic-parity`、完整 HEAD 与 clean 状态全部匹配；候选和主树 Spec SHA-256 相同；主树报告路径写入前不存在。
2. **定向候选回归**：运行 reasoning、non-stream converter 与 stream parser 三个单测文件，pytest 原始摘要为 `43 passed in 0.55s`。该计数未用不同原理交叉验证，只记录 runner 原始摘要，不作为 PASS 的独立 oracle。
3. **独立 runtime probe**：直接构造本报告矩阵中的输入并调用生产入口；关键输出为 `EMPTY_ABSENT=PASS`、`EMPTY_EMPTY=PASS`、`ENCRYPTED_NO_LOSS=PASS`、`UNKNOWN_FUTURE_SUMMARY=PASS`、`FUNCTION_CONFLICT=PASS`、`REASONING_CONFLICT=PASS`、`ITEM_DONE_ONLY_FUNCTION=PASS` 与 `INDEPENDENT_PROBE=PASS`。
4. **permissive 正控**：基线输出 `CONTROL_BASELINE=PASS typed_REJECT_both`；注入静默接受后输出 `POSITIVE_CONTROL_NONSTREAM=RED reason=silent_unknown_acceptance` 与 `POSITIVE_CONTROL_STREAM=RED reason=silent_unknown_acceptance`；恢复后输出 `CONTROL_RESTORED=PASS typed_REJECT_both`。
5. **候选全量回归**：全量 pytest 原始摘要为 `443 passed in 14.09s`；Ruff 输出 `All checks passed!`；本次相关生产与测试文件的定向 Pyright 输出 `0 errors, 0 warnings, 0 informations`。pytest 计数与 Pyright diagnostics 数未用不同原理交叉验证，只记录各 runner 原始摘要；是否符合 Spec 的结论由独立行为 probe 与正控决定。
6. **只读复核**：每轮运行后均再次验证候选完整 HEAD 未变且 `git status --porcelain` 为空。

## 未验证项

无。用户本轮指定的 semantic parity 项均已由真实生产入口执行；本报告不外推为完整 Anthropic Responses bridge、route、buffering、retry、lifecycle 或部署验收。

## 结论

`fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` 对本轮冻结范围的判定为 **PASS**。Empty reasoning 两条路径均恰一 bare block，non-empty encrypted-only 无损，unknown／future summary part 与两个 authoritative conflict 均 typed `REJECT`，item.done-only function 合法；静默接受 unknown 的正控能在两条路径上可靠把验收打红，恢复后重新转绿。未发现需要交回 debugger 或 implementer 的缺陷。
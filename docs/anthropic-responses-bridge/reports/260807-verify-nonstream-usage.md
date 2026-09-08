# Non-stream usage 独立复验

- **总体判定**：**PASS**。
- **候选范围**：只读复验 `/home/xp/src/ghc-api-proxy-py-nonstream-usage` 的 `feat/nonstream-usage-details@aca3ced6e38efabf13ffe43d5935697801c74857`，base 为 `7e4b642be8bd526d8f20f3f8d7e2d7848278a443`。
- **冻结 oracle**：主树 `docs/agents/anthropic-responses-bridge/spec.md`，复验时 SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，状态为 `FINALIZED`。Usage 判据来自该文件第 363～370 行。
- **写入边界**：候选树复验前后 `git status --porcelain` 均为空；唯一持久化写入是主树本报告。

## 独立验收矩阵

验收向量在读取候选既有测试前从 Spec 推导，并刻意不复用 Spec 表格与候选测试中的 `100／20／10／30／12` 数字。独立输入为：

- `T=137`
- `R=29`
- `W=11`
- `O=47`
- `Q=13`
- upstream `total_tokens=999`
- 额外 input detail：`audio_tokens=7`
- 额外 output details：`accepted_prediction_tokens=17`、`rejected_prediction_tokens=3`

| 验收项 | 独立预期 | 实际结果 | 判定 |
|---|---|---|---|
| cache 净 input | `I=max(0,137-29-11)=97` | Anthropic wire `input_tokens=97`，cache read `29`，cache creation `11` | PASS |
| output 保持上游值 | `output_tokens=47` | wire 与 exact fact 均为 `47` | PASS |
| reasoning detail 不二次计数 | `Q=13` 保留为 detail；normalized total 为 `97+29+11+47=184`，不得为 `197` | `reasoning_tokens=13`，`total_tokens=184`，且显式断言不等于 `197` | PASS |
| upstream total 不一致 fact | `999 != 137+47`，只记录 `usage.total_tokens` inconsistency，不改 normalized 值 | 唯一 `usage_inconsistent` 路径为 `usage.total_tokens`；`upstream_total_tokens=999`、normalized total `184` 均保留 | PASS |
| details 保留 | 输入／输出 details value-exact 保留，包括未来键 | `audio_tokens=7`、`accepted_prediction_tokens=17`、`rejected_prediction_tokens=3` 与 cache／reasoning details 全部原样保留 | PASS |
| usage 缺失 estimated | wire 使用零值；不得伪装为精确 upstream usage；必须有 estimated fact | wire 四个 usage 字段均为 `0`，`usage_facts is None`，facts 含且仅含 usage 相关的 `usage_estimated@usage` | PASS |

独立第二种算术实现使用 `awk` 重新计算同一向量，输出为 `input=97 total=184 forbidden_double_count=197`，与 Python runtime harness 的结果一致。

## 正控

正控的被测对象是“验收断言是否真实依赖 reasoning detail 映射”，不是整个测试套件。复验在单次 Python 进程内取得候选 `_convert_usage()` 源码，只把：

`reasoning = output_details.get("reasoning_tokens", 0)`

替换为：

`reasoning = 0  # POSITIVE CONTROL: reasoning mapping deleted`

未写回任何文件。随后对相同独立向量重跑同一 `reasoning_tokens == 13` 判据，得到：

`POSITIVE_CONTROL_RED mutation=delete_reasoning_mapping failure=expected reasoning_tokens=13, got 0`

正控按目标机制变红，证明“reasoning detail 保留”判据能够捕获删除映射缺陷，而不是假绿。

## 实际执行结果

1. 独立 runtime harness：
   - `VECTOR_PASS input=97 cache_read=29 cache_creation=11 output=47 reasoning=13 normalized_total=184 upstream_total=999`
   - `DETAILS_PASS input={'cached_tokens': 29, 'cache_write_tokens': 11, 'audio_tokens': 7} output={'reasoning_tokens': 13, 'accepted_prediction_tokens': 17, 'rejected_prediction_tokens': 3}`
   - `INCONSISTENCY_FACT_PASS paths=['usage.total_tokens']`
   - `ABSENT_PASS wire={'input_tokens': 0, 'output_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0} estimated_fact=usage_estimated@usage`
   - 正控结果如上一节所示，为目标原因 RED。
   - 退出码 `0`；执行后候选树 status 为空。
2. 候选相关回归：`tests/unit/test_responses_anthropic_nonstream.py` 与 `tests/smoke/test_anthropic_responses_happy_path.py`，结果为 `22 passed in 1.60s`。
3. changed-file Ruff：`All checks passed!`。
4. targeted Pyright 首次运行收到外部 `SIGINT`，后续共享终端／wrapper 的 stdout 行为不稳定；该辅助检查不计入 PASS 证据，也不据此报告产品缺陷。全量 pytest 同样受共享终端交错影响，未作为本 verdict 的证据。上述未采信项不影响本次指定 usage 行为，因为六项均已有直接 runtime oracle、独立数字交叉核验与 reasoning 删除正控。

## 可追溯实现接缝

候选 `src/app/protocols/responses_anthropic.py:214-280` 是本次 runtime 调用的 non-stream usage 转换接缝：缺失 usage 生成零值与 `usage_estimated` fact；存在 usage 时读取 cache／reasoning details，计算净 input 与 normalized total，记录 inconsistency，并把完整 details 放入只读 `ResponseUsageFacts`。本 verdict 只证明本报告矩阵中的 non-stream usage 行为，不扩张为整个 Anthropic Responses bridge 已符合完整 Spec。

## 结论

`aca3ced6e38efabf13ffe43d5935697801c74857` 相对 base `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` 的 non-stream usage 行为通过本次独立验收：cache 净 input、output 原值、reasoning detail 不二次计数、upstream total 不一致 fact、details 保留与 usage 缺失 estimated 六项均为 **PASS**；删除 reasoning 映射正控为 **RED**。未发现本次范围内的阻断缺陷。

# Stream request conversion facts 在 History 失败态的窄裁决

## 评审范围与总体 verdict

- 主树行为 oracle：`main@e9fb2771d6e040c761bb4074e3fcf2547caece28` 的 current Spec，即 `docs/agents/anthropic-responses-bridge/spec.md`。
- 候选现场：`/home/xp/src/ghc-api-proxy-py-stream-facts` 的 `fix/stream-request-facts@4fa7a87728376f14bd84b4b5853f8212d5bc786b`，工作树干净；相对 `e9fb277…` 的累计 diff SHA-256 为 `f27b97563d1fd38200f5dde1da97b094ad5a7f6f699ef6957eb3d7f4b0ea7125`，由 `sha256sum` 与 Python `hashlib.sha256` 交叉复核一致。
- 唯一裁决问题：最终 selected attempt 已完成 Anthropic request → Responses request 转换后，stream 随后以 completed、post-commit partial failure 或 delivery-uncertain 终止时，History 是否保留该 attempt 的 request conversion degradation facts。
- **总体 verdict：可进入下一阶段。Blocker：0。Major：0。唯一最小动作：保持候选。** 不限于 completed，也不按上述三种终态分类清空；三者均保留最终 selected attempt 的 request conversion observations。

## 双视角覆盖证据

### 机械核对

- 对账 Spec 的事实类型与作用域：`attempt-local state` 包含 conversion degradation，retry 时整体丢弃并重建（`spec.md:34-39`）；转换在每个 attempt 的 `PRE_SEND` 后执行（`spec.md:108-110`）；`DEGRADE` 必须作为结构化 `ConversionFact` 进入 History、metrics 与 trace（`spec.md:142`）；History 明确保留 attempts 与 capability／degradation facts，并区分 conversion failure、partial failure 等终态（`spec.md:418-424`）。
- 对账 success-only 限制：Spec 将“仅最终成功 attempt”明确绑定到 success usage／token calibration，并禁止失败 attempt 的 body、usage、headers、blocks 与 terminal 泄漏（`spec.md:275-276,347-348,356-369,528-529`）。这些条款没有把 request-side `DEGRADE` 定义为 success fact，也没有授权在最终 selected attempt 的 stream 后续失败时抹除已经发生的 request conversion observation。
- 对账候选 owner 与 provenance：`execute_anthropic_pipeline()` 仅在当前 attempt 得到成功 upstream response 后，从该 attempt 的 `converted_request_facts` 写入带 `attempt_number` 的 `RequestConversionFactRecord`；non-stream response facts另行追加。retry 的早期非成功 attempt不会成为该投影来源（候选 `src/app/pipeline/executor.py:294-303,370-379`）。
- 对账 History 投影：显式 stream response projection 存在时，completed 与 failed 都走同一 `_stream_usage_summary()`，其中 request／response provenance 仍由 typed record 区分（候选 `src/app/history/consumer.py:26-47,123-148,150-172`）。
- 对账预审：`docs/tmp/260807-review-stream-request-facts.md:25,29` 的 major 把 request conversion facts称为“request conversion success facts”，但未给出 Spec 将该事实归入 success-only 集合的依据，也未处理 `DEGRADE` 必须进入 History 与 partial failure 必须保留可区分事实的明文合同。因此该 major 的前提不成立。

### 第一人称执行模拟

1. **completed**：最终 selected attempt 在 `PRE_SEND` 后转换请求，明确丢弃不受支持的 `cache_control`／非 allowlist metadata，并把转换后的 wire 发给 upstream；stream 合法 terminal 且全部提交完成。History 保留该 attempt 的 request degradation，正确说明“此次请求以何种有损形态实际发送”。
2. **post-commit partial failure**：同一 selected attempt 已以转换后的 wire 发出，随后至少一个完整 block 已提交，再发生协议／conversion failure。History 必须同时保留已提交 prefix、failed 终态、终止原因和该 attempt 的 request degradation。清空 request facts会把已发生的 request-side loss伪装成不存在，与 Spec 的可审计与 `DEGRADE` 合同相反。
3. **delivery-uncertain**：不确定的是 downstream 某次写入是否被客户端观察，不是 upstream request 是否按该 converted wire 发出。History 必须保留代理已知的 request conversion observation，同时把 delivery frontier 标为 uncertain；两类事实正交，不能用 delivery uncertainty 抹除 request provenance。
4. **retry 的早期失败 attempt**：其 attempt-local conversion degradation必须在 reset时丢弃，不能混入最终 selected attempt 的成功／partial／uncertain投影。候选只从最终返回 `PipelineResult` 的 successful HTTP attempt发布 context facts，符合该边界。
5. **没有显式 stream projection 的失败**：`HistoryConsumer.finalized()` 在 `response is None` 且状态非 completed时不构造 usage／conversion facts；本裁决不把 request facts扩张到 approval failure、pre-send failure、HTTP失败或无 committed／uncertain response projection 的普通失败记录。

## 裁决理由

### “success facts”与“已发生的 request conversion observations”必须分开

- **Success facts** 是只有成功 terminal 才成立或才能进入成功结果／计费校准的 response-side事实，例如最终 usage、success terminal、成功 response body、成功 headers 与 token calibration。FAILED 不得把这些伪装成成功。
- **Request conversion observations** 是当前 attempt 在发送 upstream wire 前已经发生的转换处置，例如某字段被 `DEGRADE` 并从 wire省略。它描述“实际发送了什么、损失了什么”，其真值时点早于 stream terminal，不因随后 partial failure或 delivery uncertainty而变假。
- `response.is_success` 在这里不是“整条 stream 已成功”的证明，只是候选取得当前 attempt request facts 的接缝；真正令 facts成立的是该 attempt 的 converted request 已被选中并发往 upstream。候选保留它不等于把 stream标为 completed，因为 History status、response error与delivery frontier仍分别表达失败终态。

### 为什么不选另外两个动作

- **不选“只限 completed”**：它会在 partial／uncertain History中删除 Spec 强制可审计的 request-side degradation，造成错误的无损表象；这正是 false-red——正确失败记录反而被禁止保存真实 observation。
- **不选“按终态分类”**：completed、post-commit partial与 delivery-uncertain 对 request conversion observation的真值没有差异。为它们建立不同保留规则没有语义依据，只会把 downstream delivery状态错误耦合到 upstream request provenance。

## 事实性发现

未发现阻断性问题。

预审的 1 条 major **驳回**：它把 request conversion observation误分类为 success fact。候选当前语义符合 Spec；无需修改代码，也无需扩测试。

## 主观建议

无。

## 范围边界

本裁决只覆盖最终 selected attempt 的 request conversion degradation facts在 completed、post-commit partial failure与 delivery-uncertain History投影中的保留语义。它不裁决 response conversion facts、失败 usage数值是否应持久化、History schema是否应把 conversion facts从 `usage` 中拆出，也不证明完整 stream实现或测试矩阵通过。

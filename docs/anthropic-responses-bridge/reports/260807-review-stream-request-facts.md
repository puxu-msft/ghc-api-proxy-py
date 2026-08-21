# Stream request conversion facts 只读预审

## 评审范围

- 基线：`main` 与 candidate `HEAD` 均为 `e9fb2771d6e040c761bb4074e3fcf2547caece28`。
- 候选：`/home/xp/src/ghc-api-proxy-py-stream-facts` 当前未提交 diff，冻结 SHA-256 为 `f27b97563d1fd38200f5dde1da97b094ad5a7f6f699ef6957eb3d7f4b0ea7125`。
- 唯一检查范围：request conversion facts 从 client／attempt result 到 context／stream History 的单 owner、attempt provenance、失败不写 success facts，以及 nonstream 不回退。

## 总体 verdict

**修复 major 后可进入下一阶段**。Blocker：0。Major：1。

## 双视角覆盖证据

### 机械核对

- 对账了 `AnthropicAttemptResult.converted_request_facts` 的生产、`execute_anthropic_pipeline()` 的 context 发布点、`HistoryConsumer` 的 nonstream／stream 两条投影，以及候选新增测试的成功／失败参数。
- 候选把 request facts 的 context 写入集中在 `src/app/pipeline/executor.py:294-303`，记录当前 `attempt_number`；nonstream 在 `src/app/pipeline/executor.py:370-380` 只追加 response facts，未发现回退到其他 attempt。
- 定向运行候选新增／修改测试：在明确从 candidate `src` 导入代码后为 `4 passed`。同一测试的失败参数也证明当前预期会在失败 History 中保存 request facts。

### 第一人称执行模拟

- retry 后 stream 成功：首次 `429` 不发布 facts，终局 `200` 使用当前 attempt result，History 中的 attempt provenance 为终局 attempt；未发现单 owner 或回退问题。
- nonstream 成功：仍由当前成功 attempt 直接产生 request facts，再追加同 attempt 的 response facts；未发现回退。
- stream 失败：上游先返回 `2xx`，executor 立即把 request facts 写入 context；若随后发生 postcommit 协议错误、断连或 delivery uncertainty，路由把 context 置为 `FAILED`，但带 partial／uncertain response 的 History finalize 仍序列化这些 facts，违反“失败不写 success facts”。

## 事实性发现

[major] `src/app/pipeline/executor.py:294-303`、`src/app/history/consumer.py:37-44,145-173`、`tests/component/test_history_store.py:143-171,199-251` — stream 失败记录会写入 request conversion success facts — `response.is_success` 只表示上游 HTTP 已接受，尚不表示 stream terminal 成功；候选此时即发布 `context.conversion_facts`。随后 `_stream_usage_summary()` 无条件序列化 context facts，而参数化测试对两个 `RequestState.FAILED` 分支仍期待同一 request fact，令错误状态全绿。实际失败场景包括已有 partial response 后的协议错误，以及 delivery uncertain；两者都会以 `response != None`、`usage != None` 进入该投影 — 保留 executor 作为当前 attempt provenance 的单 owner，但在 History 投影时仅对 `RequestState.COMPLETED` 输出 request facts，失败态固定输出空列表；同步把现有两个失败参数的期望改为空，不新增测试矩阵。

## 主观建议

无。

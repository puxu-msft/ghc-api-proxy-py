# HTTP 499 retry 评审核查清单

评审输入版本：Git `45e7cfb972b6f9df5874a8455d9961d692f2bba2` 上的工作树。

输入哈希：

- `src/app/model_provider/ghc_client/errors.py`：`5c4562b301dd8744cce87ebf9727536e1c89b7f8f8219c7d7337d0f033e6632a`
- `tests/unit/model_provider/ghc_client/test_http_499_retry.py`：`3c192008f3005d1f54c19b6224cfcc9008835bf9b24d34c65e230e6f30b99d59`
- `.dev/human-controlled-docs-candidates/260904-http-499-retry.md`：`368e5c1dd842835c86b56be6833bbf70422d17df8177d1d35613d5d1a0f42c28`

## 必须逐条核验的断言

- C1：生产 OpenAI Responses 发送路径把 SDK `APIStatusError(499)` 交给 `normalize_upstream_error()`；加入 `RETRYABLE_STATUSES` 后产物是 `UpstreamError(status_code=499)`，而不是 `UpstreamRejected`。
- C2：该 `UpstreamError` 经 `classify()` 得到 `RETRY`，经 `reason_for()` 得到 `RetryReason.SERVER_ERROR`，并由现有 `LedgerBudget` 同时受 `serverError.max_retries` 与共享 `max_total` 限制。
- C3：在首个 499 后第二次尝试成功时，driver 返回成功且 attempts 恰为 2；`serverError.max_retries=1` 且第二次仍为 499 时，driver 停止在 2 次，`PipelineAbort.cause` 保留最后一个 499，最终错误状态仍是 499。
- C4：相邻且未列出的 498 仍归一化为 `UpstreamRejected` 并终止；此次变更没有把未知异常或全部 4xx 泛化为可重试。
- C5：`capture_rejection()` 仅写 `UpstreamRejected`；499 改为 `UpstreamError` 后不会再落 rejected request capture，但尝试数与失败仍沿现有 driver/observability 路径记录。若“仍记录”缺少足够证据，必须指出候选 Spec 应收窄到什么可证范围。
- C6：重试发生在上游 HTTP 状态尚未形成下游响应之前，不会重复已经交付的语义事件；draining、deadline 与现有预算门均未被此次改动绕过。
- C7：测试具有判别力：旧实现上至少会因 499 成为 `UpstreamRejected` 而失败；新实现覆盖 classification、成功重试、预算耗尽和 498 负控。测试假对象没有跳过生产决策层。
- C8：Spec 候选准确区分已观测事实、用户直接裁决与未知成因，没有把 2.86 MB 或约 123 秒相关性写成因果，也没有擅改 `docs/.human-controlled/`。
- C9：没有遗漏需要同步的状态表、配置示例、导出或错误 envelope；若无需修改，给出调用链与既有契约依据。
- C10：代码与测试符合项目习惯，未引入不必要的专用策略、driver 特判、等待或重试配置面。

## 已有运行证据

- 修复前：`tests/unit/model_provider/ghc_client/test_http_499_retry.py` 的首个断言失败，实际值为 `UpstreamRejected('upstream rejected the request: upstream said no')`。
- 修复后：目标 retry/classification 组合共 51 项通过。
- `ruff check`：两个变更 Python 文件通过。
- `pyright`：两个变更 Python 文件为 0 errors、0 warnings、0 informations。

Reviewer 不得仅采信这些摘要；应读取产物和调用链，并按需独立运行窄测试。

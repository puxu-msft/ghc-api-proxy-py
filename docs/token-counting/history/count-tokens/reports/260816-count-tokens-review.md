# `17b84ee` 评审报告

评审范围：提交 `17b84ee` 的 `/v1/messages/count_tokens` provider-chain 接线、配置契约、旧路由兼容性、状态生命周期与新增测试。

已读取／执行的证据：人控 `MAIN.md` 与 `config.example.yaml`；提交 diff、生产 CLI／`create_app()` 调用链、旧 `routes/anthropic.py` 与新 pipeline；`uv run pytest -q tests/http/test_pipeline_app.py -k count_tokens`（6 passed）和 `tests/unit/test_model_provider.py -k count_tokens`（1 passed）；运行时探针、in-memory 变异对照。

总体 verdict：存在 blocker，不能进入下一阶段。blocker 数量：1。

## 事实性发现

[blocker] `src/app/cli.py:125`、`src/app/server/app_factory.py:182`、`src/app/server/pipeline_app.py:51` — 新接线仍没有生产调用者。CLI 只构造 `create_app()`，后者注册的是旧 `anthropic_router`；运行时列出的实际端点是 `app.routes.anthropic.count_tokens`，而 `rg` 未找到 `src/` 内对 `create_pipeline_app()`／`build_chain()` 的外部调用。

证据／失败场景：真实服务继续走旧 `routes/anthropic.py:293` 与 `tokenization/service.py`，`inbound.anthropic_count_tokens.providers`、`max_retries` 和本提交的 `handle_count_tokens()` 均不生效；新增六个 HTTP 测试只启动孤立的 `create_pipeline_app(chain)`。

修复建议：在实际服务组合根中有意选择 provider-chain 处理该端点，并连上它的生命周期；按用户裁决保留旧 router／service，不要删除它们。

[major] `src/app/pipeline/count_tokens.py:66-67`、`src/app/server/handler.py:124-157` — `ProviderError` 被通用 `except Exception` 记为一次失败后降级到 `local`，因此到不了 `error_status()` 的 400 映射，违反 C2／C4 的 capability gate 和 provider-error 契约。

证据／失败场景：`gpt-model` 仅宣称 `/responses`，其 `provider.count_tokens()` 正确抛 `EndpointNotSupported`，但通过新 HTTP app 得到 `200 {"input_tokens": 6, "estimated": true}`、0 次上游请求；直接调用链也返回 `local`。现有 HTTP 测试只覆盖无任何能力的 `mute-model`，unit test 没覆盖 chain 这个接缝。

修复建议：在 provider-chain 的通用降级捕获之前重抛 `ProviderError`，或在选择 counter 前按 Anthropic Messages capability 明确拒绝；补一条 pipeline HTTP 回归，断言 `gpt-model` 返回 400 且无本地回退。

[major] `src/app/server/composition.py:91-100`、`src/app/server/pipeline_app.py:108-112`、`src/app/tokenization/state_store.py:47-96` — 新 `Chain.tokenization` 确实构造不做 I/O，但没有调用 `load()`、周期 `flush()` 或关闭时 `flush()`；`Chain.aclose()` 只关闭 HTTP client。

证据／失败场景：`rg` 只找到旧 `app_factory` 对另一份 `runtime.tokenization_state` 的 load／flush；新 chain 唯一使用点是 `handler.py:121`。每次新 pipeline 进程重启都会从空 calibration 开始，`tokenization_state_path()` 与“keep what it has learnt”的提交理由不成立。

修复建议：给实际 chain app 加 lifespan，在接流量前 `await chain.tokenization.load()`，周期 flush，并在 shutdown flush；用重启后的 local estimate 保留校准样本的集成测试固定行为。

[major] `tests/http/test_pipeline_app.py:452-461` — C5 的现有代码实现正确，但验收测试没有断言上游 payload 不含补入的 `max_tokens`，因此无法区分关键的错误实现。

证据／失败场景：当前运行探针显示上游 payload 不含 `max_tokens`；将 `_countable()` 仅在内存中改为直接对传入 payload `setdefault("max_tokens", 1)` 后，六条新增 HTTP 测试仍全部通过，但上游实际收到 `"max_tokens": 1`。

修复建议：将该测试保留 `seen`，断言未提供 `max_tokens` 的请求发往 `/count_tokens` 的 JSON 仍不含该键；这同时覆盖 `countable` 与 `payload` 必须为不同字典的边界。

## 逐项核查结论（未另列 blocker／major）

C1：隔离 pipeline 中 `ghc` 返回 `{"input_tokens": N}`、`local` 返回带 `estimated: true` 的形状；旧 `routes/anthropic.py:293` 与 `tokenization/service.py` 仍在。生产未接线的问题见 blocker。

C3：`handler.py:155` 以 `learn("anthropic", route.model_id, estimate, result.tokens)` 回灌，参数顺序与旧实现一致，且只在 `result.provider == "ghc"` 时调用。

C4：503 分支不是死代码。配置允许 `providers: [ghc]`；以 `max_retries=2` 连续失败实测正好三次请求后抛 `CountTokensUnavailable`。当前 handler 的 `local` callback 是同步 calibration，正常路径不会自行失败；注释“including local one”过强，但不改变分支可达性。

C5：当前代码在 `_countable()` 使用 `dict(payload)`，随后另以 `dict(context.payload)` 形成上游 payload，实际探针确认未泄漏；测试缺口见 major。

C6：`tests/unit/test_direct_driver.py` 与 `tests/unit/test_timeout_enforcement.py` 的替身均显式 `raise NotImplementedError`，不会静默伪装为已计数。

重试与并发：新 HTTP app 中默认 `max_retries=2` 的连续 500 实测向上游发出三次 `/v1/messages/count_tokens` 请求后回退，符合“每 provider 各自重试”。单一 asyncio 事件循环中 `calibration.learn()` 内没有 `await`，不会被另一协程穿插；代码未为跨线程共享同一 `Chain` 提供锁，但当前部署调用路径未证明存在这种共享。


## 复评

评审范围：HEAD `59c9e45` 相对首轮的 M1、M2、M3 与 C4 修复，以及 B1 的 C 级处置和候选文档更正。

已读取／执行的证据：`17b84ee..59c9e45` diff、当前生产／新 app 调用链、候选 gap 文档；`uv run pytest -q tests/http/test_pipeline_app.py tests/unit/test_tls_and_count_tokens.py tests/unit/test_tokenization_state_store.py`（51 passed）、相关 Ruff 与 Pyright（0 errors）；三个 in-memory 正控和一次 lifespan 关闭顺序探针。

总体 verdict：可以定稿。blocker 数量：0。

## 事实性发现

未发现 blocker 或 major。

## 复评核验

M1 已在共享 `pipeline/count_tokens.py:68-75` 修复：`ProviderError` 在通用捕获前重抛。`ProviderError` 的当前定义是请求发出前的 provider 拒绝，`GithubCopilotProvider.count_tokens()` 的三个可达子类均属“不能服务该模型”，不应重试或降级。把 handler 实际绑定的 counter 临时替换为旧的 broad-catch 实现后，新 `gpt-model` HTTP 测试如预期转红，说明它命中了链而非只命中 handler。

M2 达到要求。`pipeline_app.py:131-139` 在进流量前 load、启动周期 flush，并在取消 task group 前 await 最后一次 flush。用 trace state 实测 shutdown 事件顺序为 `load → periodic_start → flush → flush_done → periodic_cancelled`；因此正常 lifespan shutdown 不会被自身的 `cancel_scope.cancel()` 抢在最后写入之前。将运行时 `load` 或 `flush` 分别置空，重启持久化测试分别以“successor did not read”与“lifespan must flush”失败，两个正控均有效。

M3 已修复且判据有分辨力：缺少 `max_tokens` 时当前上游 payload 不含该键；新增断言直接检查 wire JSON，原先会泄漏该键的 in-memory 变异不再能通过。

C4 注释已收窄且与代码一致：`providers: [ghc]`、`max_retries: 2` 连续失败会得到三次尝试后 503；含 `local` 的正常 estimate 路径不以 `CountTokensUnavailable` 结束。

B1 的事实仍成立，但 C 级处置已把它从本 slice 的合并阻断条件降为明确的迁移缺口：`config-schema-gap.md:74` 如实说明真实 CLI 仍走旧 router，配置暂不影响真实流量。基于用户已说明入口切换会同时静默损失四项运维能力，我不主张在入口切换前阻止合入这个已正确标注为“新处理链”的准备性改动；不得将其对外表述为已服务生产流量。

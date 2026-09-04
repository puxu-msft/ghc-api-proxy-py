# HTTP 499 retry 实现状态

- status: complete
- updated_at: 2026-09-04
- implementation_commit: 2026-09-04 `fix: retry upstream HTTP 499 responses`
- requirement_commit: 2026-09-04 `update docs to make HTTP 499 retryable`
- product_requirement_authority: `docs/.human-controlled/upstream-retry-and-continuation.md`
- implementation_notes: `http-499-retry.md`
- candidate_disposition: `../../../human-controlled-docs-candidates/260904-http-499-retry.md`

## 当前实现

`src/app/model_provider/upstream_errors.py` 将 upstream HTTP 499 归一化为带 status 的 `UpstreamError`。既有 retry policy 随后把它归入 `serverError`，同时受 `upstream_request_retry.strategies.serverError.max_retries` 与共享 `max_total` 限制；SDK 自身 retry 仍关闭，重试由本项目的 `DirectDriver` 统一驱动。该 normalization 模块于 2026-09-04 随 `feat: add xingchen model provider` 从 GHC client 子包提升为所有 model provider 共享边界，499 集合成员与行为未变。

该重试发生在 upstream 499 尚未形成 downstream response 之前，不会重复已经交付的语义事件。预算耗尽或 draining 拒绝 retry 时，最后一次 499 保留为 `PipelineAbort.cause`，再由通用 direct/translated error envelope 呈现。499 不再进入只接收 `UpstreamRejected` 的 rejected request capture；完成记录保留最终尝试总数，但目前不单独持久化被 header-stage retry 替换的 failure category。

## 回归测试

`tests/unit/model_provider/ghc_client/test_http_499_retry.py` 覆盖四个可区分路径：499 的 normalization/classification、499 后第二次尝试成功、`serverError` 预算耗尽后保留最后 499，以及相邻未列出的 498 仍确定性终止。

2026-09-04 在提交所含字节上运行：

- `uv run ruff check src tests`：通过。
- `uv run pyright src tests`：0 errors、0 warnings。
- `uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80`：2213 passed、2 skipped，coverage 91.53%。
- `PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest --override-ini addopts='' -p no:cacheprovider tests/unit/model_provider/ghc_client/test_http_499_retry.py`：4 passed。此命令是 reviewer 要求的隔离缓存复核；旧实现上的正控曾在首个 `isinstance(..., UpstreamError)` 断言处得到 `UpstreamRejected` 并失败。

## 评审与处置

首轮独立评审见 `reports/260904-http-499-review-general-opus.md`：0 blocker、3 major、1 minor，四项均针对候选 Spec 的 attribution、error-envelope、observability 或 authority 表述，未否定生产 retry 实现。

修订候选稿后，限定复评见 `reports/260904-http-499-rereview-general-opus.md`：首轮四项全部 fixed，0 blocker、0 major，并判定候选稿可交给用户决定并入。复评新增的 1 条 minor 指出处置账曾使用非法复合 `statement_kind`；现已拆成合法的 `fact` 与 `judgment` 双轴。

最终 closeout review 见 `reports/260904-http-499-closeout-review-general-sonnet.md`：生产代码与专项测试没有功能缺陷，但发现 2 条 major——现行用户控制 Spec 尚未并入 499 条款，以及 `.dev` 缺少项目约定的 Git 持久载体；另 2 条 minor 已修正。用户随后给出两项裁决：授权把候选转录到目标 Spec 但保持未提交以供审核，并选择专用 `origin/dotdev` 分支持久化开发文档。用户裁决整合评审见 `reports/260904-http-499-user-ruling-integration-review-general-opus.md`；它要求 living docs 记录真实执行阶段，并在首次 push 前把该轮 checklist/report 一并纳入 dotdev。

用户最终接受精简后的 `499 Client Closed Request` requirement，并明确把正确的详细解释留在需求文档之外；这些解释现由 `http-499-retry.md` 承载。最终处置与未采用路线见 `review-disposition.md`。Spec review finding 已关闭；用户完成首次 push 后，主会话核实 `origin/dotdev` 与 local `dotdev` 指向同一 tip，且本任务的 `docs: preserve accepted HTTP 499 rationale` 是该 tip 的祖先，storage finding 也已关闭。

## 文档权威与剩余事项

用户已经审核并接受 `docs/.human-controlled/upstream-retry-and-continuation.md` 中精简的 `499 Client Closed Request` 修订，并以 2026-09-04 `update docs to make HTTP 499 retryable` 提交。用户删除的详细机制解释本身仍被确认正确，但不属于该需求文档；它们已经迁入 `http-499-retry.md`。候选处置记录保留在 `.dev/human-controlled-docs-candidates/260904-http-499-retry.md`，说明哪些内容进入需求层、哪些内容转入中间层。

用户已经选择专用 `origin/dotdev` 分支持久化 `.dev`。远端最初不存在该 ref；本轮在独立临时 worktree 中创建 orphan local `dotdev`，只复制本任务拥有的路径并逐文件校验哈希，随后创建本地提交。后台 push 先后因连接超时和缺少交互凭据失败，用户随后在带凭据的前台完成 push。2026-09-04 的远端复核显示 `origin/dotdev` 与 local `dotdev` 指向同一 tip；并行 timeout 与 reasoning-carrier 会话是在本任务提交之上追加，没有覆盖或分叉本任务文档。

功能实现、测试、Spec 用户审核、详细解释归位和 dotdev 持久化均已闭合。当前没有剩余产品或 storage action。

## 本轮边界

- 未启动、停止、重启或接管现有 4141 服务，也未执行生产 cutover。
- 两次后台 `dotdev:dotdev` push 在发布前失败，随后用户在带凭据的前台完成首次 push；未 push `main` 或其它 ref，未创建 PR。
- 未修改或清理共享树中其他会话的 WIP、worktree、ref、harness output 或用户 rejected capture。
- `$CLAUDE_JOB_DIR/tmp` 当前包含 clean local `dotdev` worktree。该 branch 在本轮末段被并行会话继续使用并推进，故本轮选择 keep，不执行 worktree 删除；harness task outputs 由 harness 管理并原样保留。
- 本次未使用 Claude Plan Mode，没有计划临时文件需要迁移。

# HTTP 499 retry 实现状态

- status: implemented-spec-draft-awaiting-user-review-dotdev-push-needs-auth
- updated_at: 2026-09-04
- implementation_commit: 2026-09-04 `fix: retry upstream HTTP 499 responses`
- product_requirement_authority: `docs/.human-controlled/upstream-retry-and-continuation.md`
- pending_requirement_candidate: `../../../human-controlled-docs-candidates/260904-http-499-retry.md`

## 当前实现

`src/app/model_provider/ghc_client/errors.py` 将 upstream HTTP 499 归一化为带 status 的 `UpstreamError`。既有 retry policy 随后把它归入 `serverError`，同时受 `upstream_request_retry.strategies.serverError.max_retries` 与共享 `max_total` 限制；SDK 自身 retry 仍关闭，重试由本项目的 `DirectDriver` 统一驱动。

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

最终处置与未采用路线见 `review-disposition.md`。Spec finding 仍等待用户审核；storage finding 已由用户裁决并正在由 coordinator 执行，只有远端 ref 建立且精确文件集可恢复后才转为 fixed。

## 文档权威与剩余事项

用户已经针对本次变更明确授权 agent 把已评审候选转录到 `docs/.human-controlled/upstream-retry-and-continuation.md`，同时要求“不提交该文件，我再审核”。目标 Spec 目前只存在于 main 工作树，未 staged、未 committed；本轮不得把它纳入任何提交。候选材料保留在 `.dev/human-controlled-docs-candidates/260904-http-499-retry.md`，记录转录来源、派生决策与未采用方案；用户审核接受后，目标 Spec 条款成为现行 requirement authority，代码常量与专项测试作为其转录。

用户已经选择专用 `origin/dotdev` 分支持久化 `.dev`。远端最初不存在该 ref；本轮在独立临时 worktree 中创建 orphan local `dotdev`，只复制本任务拥有的 11 个路径并逐文件校验哈希，随后以 2026-09-04 `docs: establish dotdev development records` 创建 root commit。首次 push 未发布任何 ref：第一次连接 GitHub 443 超时，第二次因后台会话无法读取 GitHub HTTPS 用户名而失败。storage finding 当前需要用户在带凭据的前台 shell 中执行精确 `dotdev:dotdev` push。

功能实现和测试已经闭合。任务 closeout 仍有两项执行状态：

1. Spec 已转录且保持未提交，等待用户审核。
2. dotdev 的 11 文件 root commit 已创建；首次 push 因后台会话无 GitHub HTTPS 凭据而失败。用户需运行 `git -C /home/xp/src/ghc-api-proxy-py push --set-upstream origin dotdev:dotdev`，随后重新读取 `origin/dotdev` 验证远端 OID并回写 storage finding。

在用户审核 Spec 之前，本状态不发出“完整完成”信号。

## 本轮边界

- 未启动、停止、重启或接管现有 4141 服务，也未执行生产 cutover。
- 两次只针对 `dotdev:dotdev` 的 push 均在发布前失败，`origin/dotdev` 尚未创建；未 push `main` 或其它 ref，未创建 PR。
- 未修改或清理共享树中其他会话的 WIP、worktree、ref、harness output 或用户 rejected capture。
- `$CLAUDE_JOB_DIR/tmp` 在收尾枚举时为空；harness task 目录中的四个输出文件由 harness 管理并原样保留，本轮没有执行删除。
- 本次未使用 Claude Plan Mode，没有计划临时文件需要迁移。

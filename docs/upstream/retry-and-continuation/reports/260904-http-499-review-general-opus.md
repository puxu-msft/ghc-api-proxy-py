# HTTP 499 retry 独立评审

- status: in-review
- report_id: http499-review-general-opus-260904
- attempt_id: http499-review-opus-1
- reviewed_at_rev: 45e7cfb972b6f9df5874a8455d9961d692f2bba2
- reviewed_at: 2026-09-04

## 评审范围

本轮评审固定检查主树 `/home/xp/src/ghc-api-proxy-py` 中由三项 SHA-256 标识的生产改动、单元测试与 Spec 候选稿，并沿最终生产调用链检查 retry classification、预算、driver、错误透传、rejection capture、deadline、draining、响应交付边界以及可能需要同步的契约面。明确不评审 Agent worktree 中的旧副本，不修改被评审对象，也不把清单中的已有运行摘要当作独立证据。因 pinned worktree 的写入隔离层拒绝原定主树报告路径，报告正文暂写到此隔离树路径；被评审输入仍全部来自主树绝对路径。

## 总体 verdict

`needs-fix`。HTTP 499 的生产 normalization、retry classification、两级预算、success／exhaustion 状态机、498 负控以及 deadline／draining 接缝均成立；但候选 Spec 有三项 major contract／authority 缺陷，另有一项 minor observability 过度声称。最终完成状态与计数以尾部 `## 交付声明` 哨兵为准。

## blocker 数

0。评审输入身份完整，未因工具或权限缺失缩减 C1-C10 的裁定范围。

## 输入身份校验

PASS。命令在 `/home/xp/src/ghc-api-proxy-py` 打印并校验物理路径后运行 `sha256sum`；三个结果分别为 `5c4562b301dd8744cce87ebf9727536e1c89b7f8f8219c7d7337d0f033e6632a`、`3c192008f3005d1f54c19b6224cfcc9008835bf9b24d34c65e230e6f30b99d59`、`368e5c1dd842835c86b56be6833bbf70422d17df8177d1d35613d5d1a0f42c28`，与清单逐项一致。主树 `.git/HEAD` 指向 `refs/heads/main`，该 ref 内容为 `45e7cfb972b6f9df5874a8455d9961d692f2bba2`。

## Findings

### http499-review-general-opus-260904-01：候选条款错误声称每次 499 失败都会进入现有请求记录

- finding_id: http499-review-general-opus-260904-01
- severity: minor
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:18`
- related_locations: `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:135-158`；`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:355-387`；`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py:154-159,306-348`

**证据。** `DirectDriver.run()` 会把首个 499 的字符串写入 `RequestContext.attempts[0].error` 后继续，但成功返回时 `DriverOutcome` 不携带中间错误。`_dispatch()` 在 `handle_bounded()` 返回后只把 `context.attempt_count` 投影到 `trace.attempts`；最终 `RequestLine.replaced_failures` 来自 `trace.replaced_failures`，而该列表只在流式响应已经建立后由 `_reopen()` 为 body replay 追加，header-stage 的 `DirectDriver` retry 没有对应写入。CodeGraph 对主树所有 `RequestContext.attempts`、`Attempt.error` 与 `Attempt.status_code` 的生产读取面检索也未找到另一条持久化路径。因此一次“499 后第二次成功”的完成记录可证明 `attempts=2`，但不能说明被替换失败是 499；候选稿的“各次失败……仍进入既有请求可观测记录”超出了现有证据。

**失败场景。** 生产中首次尝试返回 499、第二次成功时，operator 只能从 `attempts=2` 看出发生过 retry，却无法从现有请求记录区分首次失败是 499、timeout 还是其他 `serverError`。若候选条款并入用户控制 Spec，后续调查会把实际上已丢失的 failure category 当成可查询事实。

**建议。** 若本次不扩大实现范围，把候选稿第 18 行收窄为“最终尝试数仍进入既有请求可观测记录”，删除“各次失败”；若用户确实要求逐次失败可见，则把 driver 内部 retry 的被替换异常投影进 `trace.replaced_failures` 或等价的权威记录，并增加“499 后成功仍记录首次 499”的判别测试。

### http499-review-general-opus-260904-02：候选稿把用户对“支持 retry”的要求扩张成了整套策略细节的用户裁决

- finding_id: http499-review-general-opus-260904-02
- severity: major
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:24-26`
- related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:4,16-20,28-32`

**证据。** 候选稿给出的用户原话只有“分析并支持 HTTP 499 retry”。这句话足以把“499 必须得到 retry 支持”归给用户，却没有裁定它必须复用 `serverError`、不得增加冷却、预算耗尽时保留哪些响应部分、不得写 rejected capture、不得新增策略配置或不得在 driver 特判。后面这些选择在候选稿自己的“未采用的方案”中也明确由现有分类与维护理由推导；但第 26 行又把未加限定的“行为结论”整体归为“用户对 499 重试的直接裁决”。此外，候选稿没有给出可逐字回指到用户发言的持久锚；本评审只能核到候选稿对原话的转述，不能把转述本身当作一手来源。这里不主张用户从未说过，只裁定当前归属证据与 scope 不足。

**失败场景。** 未来若测得 499 需要独立 backoff，或 rejected capture 的产品边界需要调整，维护者会因为候选稿把整套细节标成用户裁决而绕过正常重议，即使用户真正决定的只有“应支持 retry”。这样会永久关闭用户从未覆盖的策略问题，并使 agent 自己的派生选择伪装成不可改的用户合同。

**建议。** 将来源拆成两层：只把“499 应支持 retry”标为用户直接要求，并补一手对话锚或让用户在并入时明确追认；把 `serverError` 映射、沿用两级预算、无专用 cooldown／配置、capture 行为与错误透传分别标为“依现有用户控制 Spec 的既有契约推导”或“agent 在 delegated scope 内作出的实现决定”，附对应契约位置。第 26 行应把“行为结论”收窄到用户原话实际覆盖的那一层。

### http499-review-general-opus-260904-03：候选条款承诺透传最后一次 499 body，但现有 error envelope 在两个合法路径上不会这样做

- finding_id: http499-review-general-opus-260904-03
- severity: major
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:18`
- related_locations: `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:90-117,148-180`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/error_classify.py:68-119,198-215`；`/home/xp/src/ghc-api-proxy-py/src/app/server/http_errors.py:75-102`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/errors.py:40-88`

**证据。** 候选稿无条件写“向下游返回最后一次上游 499 的状态、响应头和已观察到的响应体”。现有 edge contract 不是无条件 body passthrough：`error_response()` 只有在 `translated is False` 且 `ErrorInfo.source_bytes` 非空时才直接返回 upstream bytes。生产样本恰是 observed empty body；`normalize_upstream_error()` 会得到 `body_observed=True`、`body_bytes=b""`，但 `ErrorInfo` 不携带 `body_observed`，于是 `bool(source_bytes)` 为假，direct path 也改写成 JSON error envelope。主产品的 Anthropic Messages → OpenAI Responses translated path则无论 body 是否非空都写目标 dialect 的 envelope；能解释的 upstream body只被概括进 message，不能解释的非空 body才放进 `upstream_error` extension。status 与可转发 headers 会保留，但“已观察到的响应体”并不普遍原样返回。

**失败场景。** 如果实际 499 与已观测样本相同为空体，direct Responses client 在预算耗尽后收到的是代理合成的非空 JSON error，而不是 upstream 的空 body；如果 499 带可解释 JSON 且走主产品 translated path，Anthropic client收到的是 Anthropic error envelope，也不是 upstream 原 body。把候选条款并入后，客户端作者和后续测试都会依错误契约判断 wire body。

**建议。** 不要为 499 绕过既有 error envelope；把候选稿改成“预算耗尽或 draining 拒绝 retry 时，`PipelineAbort.cause` 保留最后一次 499，并由现有 error envelope 按 direct／translated 与有无 source bytes 的规则呈现 status、可转发 headers 和 body”。如用户真正要求所有 499——including observed empty body——逐字透传，则先修订 error-envelope Spec 与 `ErrorInfo` 的 observed-empty 表达，再同步实现和判别测试。

### http499-review-general-opus-260904-04：候选条款把 Spec 写成了代码常量的转录

- finding_id: http499-review-general-opus-260904-04
- severity: major
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:20`
- related_locations: `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:8-13`；`/home/xp/src/ghc-api-proxy-py/CLAUDE.md:2,6`；`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:30-32`；`/home/xp/src/ghc-api-proxy-py/tests/unit/model_provider/ghc_client/test_http_499_retry.py:84-134`

**证据。** 第 20 行写“本条款由 `RETRYABLE_STATUSES` 转录”，语义上把用户控制 Spec 条款放在代码常量的下游。项目指令规定相反的权威方向：Spec 是行为 authority，代码、映射表或测试若重述其值就是 Spec 的 transcription，并且 clause 要命名哪些文件转录它。这里虽然同时要求三者同步，但没有命名冲突时谁胜出；结合“由代码转录条款”的主谓方向，未来读者会把常量当 canonical source。

**失败场景。** 后续开发者若从 `RETRYABLE_STATUSES` 删除或新增状态，会据这句话先改用户控制条款以匹配代码，而不是先取得 Spec 层行为变更；这正好把项目禁止的 implementation-first 漂移包装成“同步”，使测试与文档一起保持绿色却共同偏离用户 contract。

**建议。** 反转句子为“`src/app/model_provider/ghc_client/errors.py` 的 `RETRYABLE_STATUSES` 与 `tests/unit/model_provider/ghc_client/test_http_499_retry.py` 转录本条款；本条款变化时同步更新两处转录”，并明确冲突时当前用户控制 Spec 为 authority。候选稿位于 `.dev/human-controlled-docs-candidates/`、没有直接修改 `docs/.human-controlled/`，这一处理边界本身是正确的；应由用户决定是否并入。

## C1-C10 逐项裁定

| ID | 裁定 | 证据与反例检查 |
|---|---|---|
| C1 | PASS | `/home/xp/src/ghc-api-proxy-py/src/app/server/composition.py:421-458` 以 `max_retries=0` 构造两个 SDK client；`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/github_copilot.py:154-188` 将 `OPENAI_RESPONSES` dispatch 到 `GhcApiClient.send_responses()`；`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/client.py:99-111,153-167` 在 SDK await 边界把 `APIStatusError` 交给 `normalize_upstream_error()`；`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:148-180` 因 499 在 `RETRYABLE_STATUSES` 内而构造带 `status_code=499` 的 `UpstreamError`。SDK 自身 retry 已关闭，没有隐藏重试层截走该状态。 |
| C2 | PASS | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/exceptions.py:130-143` 把 `UpstreamError` 分类为 `RETRY`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:35-57` 把带非 401、非 `>=500` 的有状态 `UpstreamError` 落到 `SERVER_ERROR`；同文件 `:60-95` 先检查共享 `max_total`，再检查 `serverError.max_retries` 并同时记账。`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py:72-79,173-189` 证明一个 `RetryLedger` 绑定整条客户端请求且生产 driver 使用 `LedgerBudget`。 |
| C3 | PASS | `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:135-158,219-241` 每轮先 `begin_attempt()`，获预算后循环；预算拒绝时以当前 error 作为 `PipelineAbort.cause`。`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/error_classify.py:198-215` 优先展开 cause，保留最后一次 499 的 status。`/home/xp/src/ghc-api-proxy-py/tests/unit/model_provider/ghc_client/test_http_499_retry.py:98-126` 对成功两次与 `max_retries=1` 后第二个 499 的 terminal cause／status 作出精确断言。coordinator 代执行固定主树命令，provenance 为 `/home/xp/src/ghc-api-proxy-py`，收集 4 项并得到 `4 passed in 1.34s`。 |
| C4 | PASS | `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:139-184` 仍只翻译已识别 SDK／transport 类，并只让明确 set 内状态绕过一般 4xx rejection；`/home/xp/src/ghc-api-proxy-py/tests/unit/model_provider/ghc_client/test_http_499_retry.py:129-134` 以 498 证明邻接负控仍为 `UpstreamRejected`／`ABORT`。删除 499 这一单个 set member 即恢复旧分支，不存在全 4xx 泛化。 |
| C5 | FAIL | `/home/xp/src/ghc-api-proxy-py/src/app/observability/rejection_capture.py:45-51` 只写 `UpstreamRejected`，所以 499 不再进入 rejected capture；`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:355-387` 会记录最终 `attempt_count`。但 header-stage retry 的中间 499 没有进入最终请求记录，详见 `http499-review-general-opus-260904-01`。 |
| C6 | PASS | HTTP status exception在 `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/client.py:99-111` 被抛回 driver；只有 driver 返回 response 后，`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:379-420` 才建立 downstream delivery，因此首个 499 没有可重复的语义事件。attempt deadline 覆盖 prepare／rate-limit／send，见 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:135-151,243-282`；client deadline 不随 retry 重置，见 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py:391-418`；draining 在每次 failure 获预算前读取，见 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/direct_driver/base.py:61-81` 与生产注入 `/home/xp/src/ghc-api-proxy-py/src/app/pipeline/driver.py:173-188`。此次 set-member 变更没有新并发状态或绕过这些门。 |
| C7 | PASS | `/home/xp/src/ghc-api-proxy-py/tests/unit/model_provider/ghc_client/test_http_499_retry.py:84-134` 分别覆盖 normalization／classification、成功 retry、per-reason budget exhaustion 和 498 负控。旧 set 上 499 会命中 `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:161-171` 的 `UpstreamRejected` 分支，使首个 `isinstance(..., UpstreamError)` 断言变红。driver 测试虽以已归一化异常为 provider outcome，但仍经过生产 `DirectDriver._handle_failure()`、`classify()` 与 `LedgerBudget`；SDK normalization 是同文件前置测试的独立 seam。主树 4 项实跑全绿，且静态反事实证明不是无法开火的绿灯。 |
| C8 | FAIL | `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:24-26` 明确把 2,859,854 bytes 与约 123.1 秒标为相关观测，并否认对 Copilot 成因的推断，这部分 PASS；文件位于候选目录且 coordinator 执行 `git -C /home/xp/src/ghc-api-proxy-py --no-optional-locks status --short -- docs/.human-controlled` 得到空输出，证明当前主树没有修改用户控制目录，这部分 PASS。但用户直接裁决的 scope 被扩张到 agent 派生的策略细节，详见 `http499-review-general-opus-260904-02`，故整项 FAIL。 |
| C9 | FAIL | 配置面无需新增：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/retry.py:35-95` 已有完整 mapping／预算；错误类型与 envelope 无需新增 export：`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/exceptions.py:23-47,118-143`、`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/error_classify.py:68-119,198-215` 已按 `UpstreamError`／`PipelineAbort.cause` 泛化；用户控制 retry Spec 的同步由候选稿承担，agent 没有越权直改。但候选稿把现有 error-envelope wire 行为写成无条件 body passthrough，并反转 Spec／transcription authority，详见 `http499-review-general-opus-260904-03` 与 `http499-review-general-opus-260904-04`。因此无需新增代码状态表或配置，不等于当前同步文本已经闭合。 |
| C10 | PASS | 生产改动仅在 `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:30-32` 的既有状态 set 加入 499；重用现成 `UpstreamError`、`serverError`、`LedgerBudget` 与 driver，没有 499 专用策略、driver branch、sleep、backoff 或配置。测试复用现有 `DirectDriver` 与配置模型，没有建立新 proof framework。 |

## 运行证据

- 输入 SHA-256：在固定主树打印并断言 `pwd -P` 后执行 `sha256sum`，三项结果与 coordinator checklist 完全一致。
- 窄测试：由于当前 reviewer 进程被 pinned worktree 隔离层禁止以主树为执行 cwd，coordinator 按原样代执行 `PYTHONDONTWRITEBYTECODE=1 uv --directory /home/xp/src/ghc-api-proxy-py run --frozen pytest --override-ini addopts='' -p no:cacheprovider /home/xp/src/ghc-api-proxy-py/tests/unit/model_provider/ghc_client/test_http_499_retry.py`；输出确认 rootdir 与 cwd 都是 `/home/xp/src/ghc-api-proxy-py`，4 项全部通过，耗时 1.34 秒。该运行证明当前输入可执行；旧实现会失败的结论另由 C7 的 branch-level 反事实支撑，而不是从绿灯外推。
- 用户控制目录：coordinator 代执行带 `--no-optional-locks` 的 scoped `git status`，`docs/.human-controlled` 输出为空。该证据只支持当前 working tree 未改此目录，不冒充对历史所有提交的全称结论。

## 搜索面与未覆盖面

逐条读取了 coordinator checklist、三项哈希固定输入和用户控制 retry Spec，并沿主树读取 `GhcApiClient`、`GithubCopilotProvider`、composition root、`DirectDriver`、retry ledger、pipeline exceptions／classification、request context、server inference edge、rejection capture、request trace、error writers、config schema及相关既有单元测试。CodeGraph 用于建立调用地图，但其索引会混入 `.claude/worktrees` 的同名符号；所有影响裁定的源码证据均重新以 `/home/xp/src/ghc-api-proxy-py/...` 绝对路径读取，未采信 Agent worktree 中的旧副本。

未对真实 Copilot 重新发起 billed request，也未读取 2026-09-03 生产 capture 原件；因此 2,859,854 bytes 与 123.1 秒仅能裁定为候选稿明确标注的既有观测，不能由本轮独立复测升级为成因证据。未运行全量 pytest、Ruff 或 Pyright；本轮变更面很窄，窄测试与调用链审查足以裁定 C1-C10，但不支持“仓库全套检查当前全部通过”的更宽声称。

## 未报告的候选问题

- 没有把 dedicated feature test 未在本文件内再次证明共享 `max_total` 列为 finding。`/home/xp/src/ghc-api-proxy-py/tests/unit/pipeline/test_retry_strategies.py:66-72` 已直接证明不同 retry reason 共用总预算，而 499 到 `SERVER_ERROR` 的 mapping 由本文件首个测试证明；重复同一 ledger case不会增加判别力。
- 没有要求新增 499 专用 cooldown、counter 或 config。现有 `serverError` 与共享总预算已经表达所需状态，新增策略面反而会分裂同一类 retry 决策。
- 没有把缺少真实 upstream replay test 列为 finding。SDK exception translation、retry driver 与 error edge 都有可分辨的局部 seam；本次变化是 closed status set 的单个成员，不依赖尚未录入 cassette 的 upstream chunk shape。

## 整体判定

`needs-fix`，结论强度为“足够据此行动”。生产代码的核心 HTTP 499 retry 机制通过 C1-C4、C6、C7 与 C10；当前不可直接把候选条款并入用户控制 Spec，因为 C5、C8 与 C9 暴露了 3 项 major 和 1 项 minor。修复不需要推翻 retry 实现：优先收正候选稿的 decision provenance、error-envelope 表述与 Spec／transcription 方向，再在“收窄 observability 声称”与“让 header-stage replaced failure 真正进入请求记录”之间作一项明确选择。未发现 blocker。

### 承重前提核验

- 前提：三项 SHA-256 精确标识本轮被评输入。它支撑“本报告裁定的是 coordinator 指定版本”这一结论；若为假，全部结论失去版本身份并应改判 `blocked`。本轮开始与结束各在固定主树重新计算一次，六个读数均与 checklist 一致，因此该前提足够据此行动。
- 前提：候选稿第 4 行提供的“分析并支持 HTTP 499 retry”是当前可审计材料所覆盖的完整用户话语范围。它支撑 finding `http499-review-general-opus-260904-02`；若另有更宽的一手用户原话明确裁定 `serverError`、cooldown、capture 与 error edge 细节，该 finding 必须按那段逐字 scope 重判。当前没有这样的持久锚，因此不能先假定它存在。
- 前提：现有 `error_response()`／`write_error()` 仍是 499 预算耗尽后的通用 wire contract。它支撑 finding `http499-review-general-opus-260904-03`；若用户另有一手裁决要求 499 无条件 raw passthrough，则该 finding 不会消失，而会扩大成“实现与候选稿都必须先同步 error-envelope Spec”的代码缺陷。当前生产调用链没有 499 特判，故按现有通用 contract 裁定。

## 我最没把握的三个判断

1. `http499-review-general-opus-260904-02` 的事实部分置信度高、定级置信度中等。候选稿确实只展示了窄原话且没有持久一手锚；不确定的是 parent session 是否另持有更宽原话。即使有，必须逐字覆盖策略细节才会改变 finding，而不能用“用户确实提过 499”替代 scope 核验。
2. `http499-review-general-opus-260904-04` 定为 major 而非 minor 的置信度中等。单句改写成本很小，但 severity 按影响而非修复行数；它会把用户控制 Spec 的 authority 反转给代码 constant，并直接碰到项目标为 non-negotiable 的 Spec-first 规则，所以我保留 major。若 coordinator 认为候选稿语法只能被理解为“代码转录条款”，而非“条款来自代码”，可降级，但应先改成无歧义主谓关系。
3. C6 对 draining 的 PASS 置信度中等偏高。`LedgerBudget.take_for()` 在 retry 决策点读取实时 draining，获准后 driver 同步进入下一轮 `begin_attempt()`，既有测试也覆盖 drain 在 failure 前变化的情形；我没有把“drain 在这个同步线性化点之后才开始”误判为绕过。若产品 contract 把线性化点定义为底层 socket 真正写出首字节，而不是 retry attempt 获准／创建，则 token lookup 或 subscriber await 期间仍需二次 gate；现有 Spec 与代码注释没有给出该更强定义，因此本轮不制造这一 finding。

## 执行本契约时遇到的摩擦

- `Skill` 对用户指定的 `my-agents:as-reviewer` 返回 `Unknown skill`。为同时满足“先加载再读对象”，我在读取任何被评输入前定位并直接读取了权威文件 `/home/xp/.claude/my/my-agents/skills/as-reviewer/SKILL.md`；这是唯一一次 Read 不在目标主树内，原因是 skill 本身不属于项目树，且不这样做就无法满足更上游前置要求。
- pinned worktree 的隔离层拒绝 `Write`／`Edit` 到原定主树 REPORT_FILE，也拒绝以主树为 cwd 运行 pytest 或 git read-only 命令，即使命令显式绑定 provenance。coordinator 因此指示报告先完整写入隔离树，并承诺交付后逐字复制；窄测试与两个 scoped git 查询由 coordinator 在主树代执行，完整命令、provenance、退出码与输出已回传。本轮没有把执行者身份伪装成 reviewer 自己。
- CodeGraph 的项目索引会把 `.claude/worktrees/*` 同名符号混入结果，即使 query 明确要求排除。所有影响结论的源码最终都通过目标主树绝对路径读取；混入的 worktree source 只用于发现文件名，没有用作裁定证据。
- 评审途中共享主树短暂出现未列入哈希的 `test_upstream_error_normalization.py` 499 重复 hunk。coordinator 确认那是本轮自己的竞态遗留并精确删除；删除后 working tree、HEAD blob 与基线 blob 的 SHA-256 均恢复为 `a8bec54a1b3d97ceaf390867dec66ae09b6951ae73ead0893ed7a372137eebbb`。三项固定输入哈希始终未变，因此没有把该瞬时额外 hunk计入 findings，也没有据此改判 input blocker。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-03T21:38:33+00:00
- finding_total: 4
- blocker: 0
- major: 3
- minor: 1
- nit: 0

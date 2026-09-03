# HTTP 499 retry 评审处置账

- status: active
- source_report: `reports/260904-http-499-review-general-opus.md`
- source_report_sha256: `2d8b692cf2a9cfa0157918bb4597ad21a6878fceff1d10fcdf863e6d96aa3e04`
- source_rereview: `reports/260904-http-499-rereview-general-opus.md`
- source_rereview_sha256: `1baa597f05755121579e46442a007f343ecadbff53ca2a68a8f592788a7953ec`
- source_closeout_review: `reports/260904-http-499-closeout-review-general-sonnet.md`
- source_closeout_review_sha256: `b6f7a1c0b017839a386a6b0ec8600102b657a73d86e03af445151cc061cbaa59`
- source_integration_review: `reports/260904-http-499-user-ruling-integration-review-general-opus.md`
- source_integration_review_sha256: `268f9f977f46ffdf834ef844e4d3c5fe9d09757e1b7e29d030120f3e5d122259`
- source_integration_rereview: `reports/260904-http-499-user-ruling-integration-rereview-general-opus.md`
- source_integration_rereview_sha256: `2d412ef76d1ea99566799f2046404288b461c018fa7df9fb4d72b5897c39b25f`
- source_detail_placement_review: `reports/260904-http-499-detail-placement-review-general-sonnet.md`
- source_detail_placement_review_sha256: `1831b64f99bfd2af730ed0f3d1f10bc96ee1d2981f313725cde4d9aedd677b71`
- received_at: 2026-09-04
- counts_declared: blocker=0 major=3 minor=1 nit=0
- counts_verified: yes
- rereview_counts_declared: fixed=4 not_fixed=0 regressed=0 blocker=0 major=0 minor=1 nit=0
- rereview_counts_verified: yes
- reviewed_input_rev: `45e7cfb972b6f9df5874a8455d9961d692f2bba2` 加报告所列三项 SHA-256

## 处置

### http499-review-general-opus-260904-01

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: minor
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: `src/app/server/routes/inference.py:357-388` 只把 `context.attempt_count` 投影到 trace；`src/app/observability/request_trace.py:155-159,343-344` 的 `replaced_failures` 没有 header-stage retry 写入点。
- action: 将候选稿收窄为“请求记录保留最终尝试总数，但不单独保留被替换的 header-stage 499 failure category”。
- rejected_alternative: 本次不新增 header-stage `replaced_failures` 持久化，因为用户要求的控制流是 499 retry；该可观测扩展不是 retry 正确性的前置条件，且候选稿已经明确记录现状，后续若需要可单独修订 observability Spec。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-review-general-opus-260904-02

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: major
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: 用户原话只覆盖“分析并支持 HTTP 499 retry”；候选稿此前把 `serverError`、预算、cooldown、capture 与 error envelope 等派生选择整体归为用户裁决。
- action: 把来源拆为 `user-initiated` 的“499 应支持 retry”和 `agent-decided-within-delegated-scope` 的实现策略，并加入 session 锚；只有用户并入候选后，完整条款才成为用户控制 Spec 的权威行为来源。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-review-general-opus-260904-03

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: major
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: `src/app/server/http_errors.py:76-103` 仅在 direct 且 `source_bytes` 非空时原样传递 body；`src/app/pipeline/error_classify.py:199-216` 从 `PipelineAbort.cause` 恢复最后 upstream failure，但不让 observed-empty body 绕过 error writer。
- action: 候选稿改为由既有 direct/translated error envelope 呈现最后 499，精确区分 non-empty direct body 与 translated/observed-empty envelope。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-review-general-opus-260904-04

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: major
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: 项目 `.claude/rules/00-development-workflow.md` 规定 Spec 是 behavior authority，代码与测试是 transcription；候选稿此前的主谓方向相反。
- action: 明确候选条款并入后成为权威来源，`RETRYABLE_STATUSES` 与专项测试转录它；冲突时以当前用户控制 Spec 为准。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-rereview-general-opus-260904-01

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: minor
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: 首版处置账四次使用未定义复合值 `statement_kind: fact + judgment`；处置协议只允许 `fact`、`judgment` 或 `decision` 单值。
- action: 每条原 finding 均拆为一项 `fact` 及其 `claim`，再拆为一项 `judgment` 及其 `judgment_status`；未改 finding ID、severity、证据或处置结论。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-closeout-review-general-sonnet-260904-01

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: major
- disposition_level: A
- fix: adopted
- outcome: fixed
- evidence: 当前用户控制 Spec 已按用户最终编辑写入 `499 Client Closed Request`，并由用户以 2026-09-04 `update docs to make HTTP 499 retryable` 提交；用户接受需求修订，并明确详细解释本身正确但不属于该文档。
- action: 保留目标 Spec 的精简 requirement；把已验证的详细机制、观测边界与未采用方案迁入 `.dev/docs/upstream/retry-and-continuation/http-499-retry.md`，不再要求目标 Spec 完整转录实现说明。

裁决：

- statement_kind: decision
- decision_status: user-reviewed-approved-with-placement-correction
- decision_origin: user-initiated
- ruling: 用户表示“接受修订，但你加入了详细解释，而这些解释不应该放入该文档（但解释本身是对的）”。精简 requirement 成为权威；详细解释归中间层开发文档。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-closeout-review-general-sonnet-260904-02

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: major
- disposition_level: A
- fix: open
- evidence: `.dev/.git` 与 `.dev/README.md` 不存在，父仓忽略整个 `.dev/`；本轮候选、报告、处置账和 status 当前没有项目规则所述的独立 Git 持久版本。

待决事项：

- statement_kind: decision
- decision_status: user-selected-blocked-on-credentialed-push
- decision_origin: user-selected-from-proposal
- ruling: 用户选择“专用的 origin/dotdev 分支”。该裁决授权创建并首次 push 专用 orphan `dotdev`，不授权 push `main`、目标 Spec 或其它 ref。
- execution: local orphan root commit `docs: establish dotdev development records` 已创建；第一次 push 连接 GitHub 443 超时，第二次 push 因后台会话无法读取 GitHub HTTPS 用户名而失败，均未发布 remote ref。
- next_actor: user-credentialed-shell
- response_required: true
- pending_annotation_ids: http499-closeout-review-general-sonnet-260904-02

### http499-closeout-review-general-sonnet-260904-03

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: minor
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: 候选稿曾同时写“待独立复评”与“可供用户决定”，而限定复评已经完成。
- action: 候选稿先改为限定复评已通过；用户最终审核后又改写成 `adopted-in-concise-form` 处置记录，并把详细解释迁入中间层 implementation notes。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-closeout-review-general-sonnet-260904-04

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: minor
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: closed disposition 曾只以路径引用承重的限定复评，没有固定其协作期版本。
- action: 已加入 `source_rereview_sha256: 1baa597f05755121579e46442a007f343ecadbff53ca2a68a8f592788a7953ec`；限定复评若发生实质变化，处置账必须重新绑定或重开。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-user-ruling-integration-review-general-opus-260904-01

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: major
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: candidate 已记录 Spec 转录，README 已记录 dotdev 裁决，但 status/disposition 曾把两项写成尚待用户裁决，造成后继执行路由错误。
- action: candidate 已补 dotdev 裁决及权限边界；status 已改写为 Spec 转录待审核、dotdev 执行中；两条 decision 已登记为用户作出并分别路由给 user-reviewer 与 coordinator。限定复评确认该整改 fixed。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-user-ruling-integration-review-general-opus-260904-02

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: minor
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: dotdev 首批 8 文件不含在其后产生的 integration checklist 与本轮报告，因此拟发布 snapshot 当时不完整。
- action: 两份 integration 评审件及更新后的 candidate/status/disposition 已通过精确路径复制并逐文件核对哈希；限定复评确认当前集合完整。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

### http499-user-ruling-integration-rereview-general-opus-260904-01

事实陈述：

- statement_kind: fact
- claim: confirmed

判断陈述：

- statement_kind: judgment
- judgment_status: concurred
- severity: minor
- disposition_level: C
- fix: adopted
- outcome: fixed
- evidence: status 曾在 integration checklist/report 已补齐后仍把它们写成待补齐，可能让后继重复同步。
- action: status 已改为 integration checklist、review 与限定复评报告均已补齐，11 个精确文件只等待 commit/push。
- next_actor: none
- response_required: false
- pending_annotation_ids: none

## 当前共识状态

- overall: blocked-on-dotdev-push
- consensus: 首轮 4 条 finding、限定复评 1 条 minor、closeout review 的 Spec major 与 2 条 minor、integration review 2 条 finding 及 integration rereview 1 条 minor 均 fixed；用户接受精简的 499 requirement 并把正确的详细解释留在中间层文档。仅 storage major 保持 open，等待带凭据首次 push。
- open: 1
- disputed: 0
- fixed: 11
- rejected: 0
- deferred: 0
- pending_annotation_ids: http499-closeout-review-general-sonnet-260904-02

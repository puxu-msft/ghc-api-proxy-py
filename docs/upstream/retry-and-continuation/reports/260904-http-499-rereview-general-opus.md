# HTTP 499 retry 限定复评报告

- status: in-review
- report_id: http499-rereview-general-opus-260904
- attempt_id: http499-rereview-opus-1
- reviewed_at_rev: 45e7cfb972b6f9df5874a8455d9961d692f2bba2
- reviewed_at: 2026-09-04
- source_report: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-review-general-opus.md`
- source_report_sha256: `2d8b692cf2a9cfa0157918bb4597ad21a6878fceff1d10fcdf863e6d96aa3e04`

## 复评范围

本轮只复核首轮四条 finding 的整改结果，不重新展开 C1-C10 全量评审。复核对象为整改后的候选稿、处置账，以及四条整改直接涉及的 decision provenance、error envelope、observability 与 Spec authority 相邻契约。

输入 SHA-256 已逐项重算并与 coordinator 给定值一致：

- 生产代码：`5c4562b301dd8744cce87ebf9727536e1c89b7f8f8219c7d7337d0f033e6632a`
- 专项测试：`3c192008f3005d1f54c19b6224cfcc9008835bf9b24d34c65e230e6f30b99d59`
- 整改后候选稿：`5e43bf1df9041ec3573106744b908d72f5eaf14d8c359d5cf429728650b2d679`
- 处置账：`bb5c725bbdc17c665f7686b95420d14dadad10a6ce7c7316a1796e6484a6ca53`

生产代码与专项测试的哈希仍是首轮所审版本，因此本轮不重复运行测试，不把候选稿整改扩大成代码复验。

## 原 finding 逐条 outcome

| 原 finding | outcome | 复评结论 |
|---|---|---|
| `http499-review-general-opus-260904-01` | fixed | 候选稿不再声称每次 499 failure 都进入现有请求记录。 |
| `http499-review-general-opus-260904-02` | fixed | 用户直接裁决与 agent 派生策略已经分开记录，并补上可核的一手 session 锚。 |
| `http499-review-general-opus-260904-03` | fixed | 候选稿已准确描述现有 direct／translated error-envelope 行为与 observed-empty 分支。 |
| `http499-review-general-opus-260904-04` | fixed | Spec 与代码／测试 transcription 的权威方向已经纠正。 |

- fixed: 4
- not-fixed: 0
- regressed: 0

### F01：observability 过度声称

- original_finding_id: http499-review-general-opus-260904-01
- outcome: fixed
- evidence: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:23,39`；`/home/xp/src/ghc-api-proxy-py/src/app/server/routes/inference.py:357-388`；`/home/xp/src/ghc-api-proxy-py/src/app/observability/request_trace.py:155-159,307-349`

候选稿第 23 行现在只承诺“既有请求记录仍写最终尝试总数”，并明确说明成功 retry 替换的 header-stage 499 failure category 当前不会单独进入 `replaced_failures`。第 39 行把扩展 header-stage observability 明确列为本次未采用的独立改动。这与生产代码只把 `context.attempt_count` 投影到 `trace.attempts`、而不把 driver 内部 retry failure 写入 `trace.replaced_failures` 的现状一致。

处置账第 12-25 行忠实保留原 severity、成立度与整改选择，并记录了未采用 observability 扩展的理由。原 finding 已闭合，没有回归。

### F02：decision provenance 越界归因

- original_finding_id: http499-review-general-opus-260904-02
- outcome: fixed
- evidence: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:6-10,29-31,41-43`；Claude Code session `00409e7f-6b11-4954-9cfc-56d755db19dd` 的 human-origin typed user message

候选稿第 8 行把用户直接裁决严格限定为“499 应支持 retry”；第 9 行把 `serverError` 映射、两级预算、无专用 cooldown／配置、沿用 error envelope 与 capture 行为明确归为 `agent-decided-within-delegated-scope`。第 31 行也只让用户裁决支撑“499 应支持 retry”，不再让它承载策略细节。

本轮独立定位了候选稿所引 session。该 session 的首条 human-origin、`promptSource: typed` 用户消息逐字以“分析并支持 HTTP 499 retry”开头，session ID 与候选稿一致，足以支撑候选稿现在声明的窄 scope。它不被外推为用户对后续实现细节的裁决。

处置账第 27-39 行对原问题、整改动作与 severity 的记录忠实。原 finding 已闭合，没有回归。

### F03：error-envelope 行为表述错误

- original_finding_id: http499-review-general-opus-260904-03
- outcome: fixed
- evidence: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:21,38`；`/home/xp/src/ghc-api-proxy-py/src/app/server/http_errors.py:59-103`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/error_classify.py:69-120,199-216`；`/home/xp/src/ghc-api-proxy-py/src/app/pipeline/delivery/formats/errors.py:41-89`

候选稿第 21 行现在准确区分：

- `PipelineAbort.cause` 保留最后一次 499。
- status 与可转发响应头继续保留。
- 只有 direct 且 `source_bytes` 非空时原样传递 upstream body。
- translated 路径或 observed-empty body 进入客户端格式的 error envelope。

这与 `describe()` 展开 `PipelineAbort.cause`、`error_response()` 以 `not translated and bool(info.source_bytes)` 选择 raw direct path，以及 error writer 处理 translated／empty source 的现有调用链一致。第 38 行也明确拒绝为 499 新建第二套 error body 特判。

处置账第 41-53 行准确记录了原缺陷与整改后的 contract。原 finding 已闭合，没有回归。

### F04：Spec／transcription 权威方向颠倒

- original_finding_id: http499-review-general-opus-260904-04
- outcome: fixed
- evidence: `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:25`；`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:9-14`；`/home/xp/src/ghc-api-proxy-py/CLAUDE.md:2,6`

候选稿第 25 行现在明确写明：候选条款由用户并入后成为 authority，`RETRYABLE_STATUSES` 与专项测试是它的 transcription，冲突时以当前用户控制 Spec 为准。该方向与项目的 Spec-first 规则及用户控制文档边界一致，也没有让 agent 直接修改 `docs/.human-controlled/`。

处置账第 55-67 行忠实记录了原 authority 缺陷和实际整改。原 finding 已闭合，没有回归。

## 处置账忠实度

处置账对四条首轮 finding 的以下内容均与 source report 及整改候选稿一致：

- source report 路径与 SHA-256 正确。
- 首轮计数 `blocker=0 major=3 minor=1 nit=0` 正确。
- 四条 finding 的 severity、claim、judgment outcome、整改动作与未采用方案没有被改写成较弱的问题。
- `open=0`、`disputed=0`、`adopted_pending_confirmation=4` 准确描述复评前状态。
- `overall: pending-rereview` 与 `next_actor: original reviewer` 在本报告交付前是正确路由；coordinator 接收本报告后应把四项确认结果回写为终态，而不应继续保留 `pending-rereview`。

内容忠实度通过。但处置账存在一项不阻断候选稿合并的 schema minor，见下节。

## 新 finding

### http499-rereview-general-opus-260904-01：处置账使用了未定义的复合 `statement_kind`

- finding_id: http499-rereview-general-opus-260904-01
- severity: minor
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md:14`
- related_locations: `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md:29,43,57`

**证据。** 四条处置都写成 `statement_kind: fact + judgment`。当前处置协议给 `statement_kind` 定义的合法单值是 `fact`、`judgment` 或 `decision`；复合陈述需要拆开后分别进入 `claim` 与 `judgment_status` 轴，不能发明一个既不是枚举值、又让两个轴同时悬挂在同一未拆陈述上的复合 spelling。

**失败场景。** 后续若按处置 schema 机械检查或聚合，`fact + judgment` 无法进入任一合法分支；人工读者也无法确定 `claim: confirmed` 究竟确认了事实部分，还是把 severity／fix 选择等判断一并标成了事实。

**建议。** 保留四条 finding ID、severity 与处置结论不变，把每条的事实 claim 与判断结论拆成两个明确子项，或采用项目已批准的等价双轴字段，使每个 `statement_kind` 只取一个合法值。该问题只影响内部处置账的结构表达，不改变候选条款内容、四条整改 outcome 或 HTTP 499 行为。

## 是否可合

可合。

四条首轮 finding 全部 fixed，未发现 not-fixed 或 regressed；唯一新增问题是处置账的 minor schema 缺陷，不影响候选稿行为准确性，也不应阻断用户将候选条款并入 `docs/.human-controlled/upstream-retry-and-continuation.md`。处置账应在本轮收口时机械订正该字段，并将 `pending-rereview`／`adopted_pending_confirmation` 更新为与本报告一致的终态。

## 整体 verdict

`pass`。候选稿达到可交给用户决定并入的状态；处置账剩余 1 项 minor，需在内部收口时修正，但不得据此继续扩大为新的全量评审。

## 不确定判断

1. 新增 minor 的成立依赖当前已加载处置协议对 `statement_kind` 的单值枚举定义。限定范围内未发现项目另行批准 `fact + judgment` 这一复合值；若 coordinator 能给出更近层级的正式 schema authority，则应按该 authority 重判，而不是仅凭既有文件中出现四次便把 spelling 当成合法。
2. 候选稿把用户要求日期写为 2026-09-04，而 transcript timestamp 是 `2026-09-03T19:46:50.132Z`。同一用户消息附带的运行日志发生在本地次日凌晨，二者与本地日期／UTC 日期差异一致；这不影响 session 身份、原话或言语行为的核验。
3. 本轮没有重跑专项测试，因为生产代码与测试 SHA-256 均未变化。该选择只支持“首轮代码证据仍适用于同一字节输入”，不支持主树其他并行改动或全量检查仍然通过。

## 执行本契约时遇到的摩擦

- decision provenance 的 session 搜索命中行包含完整用户 prompt 与大量伴随上下文，`rg` 输出超过工具显示上限并被 harness 持久化。预览仍完整展示了 human-origin typed user message、session ID、逐字开头与 timestamp，足以裁本轮窄 provenance 命题；没有把其余截断内容外推为额外裁决。
- 首轮报告已经由 coordinator 转录到主树，本轮直接读取该转录件并核验其 SHA-256，没有再依赖会自动清理的隔离 worktree。
- 按限定复评要求，本轮没有重新探索 C1-C10、没有重跑全量测试，也没有扫描与四条整改无关的模块。

## 交付声明

- delivery_complete: true
- completed_at: 2026-09-04
- original_outcome_total: 4
- fixed: 4
- not_fixed: 0
- regressed: 0
- new_finding_total: 1
- blocker: 0
- major: 0
- minor: 1
- nit: 0

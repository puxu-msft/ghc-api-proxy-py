# HTTP 499 retry 最终 closeout 评审

- `report_id`：`http499-closeout-review-general-sonnet-260904`
- `attempt_id`：`http499-closeout-sonnet-1`
- `reviewed_at_rev`：
  - implementation：2026-09-04 `fix: retry upstream HTTP 499 responses`，OID `39274d7bc3601f2236ffdfc52ea6f34f885ba405`
  - status SHA-256：`c362dcfc97641794fc4146bb4d7d5490332a00f18b0b4ff8d179baf53f36677d`
  - candidate SHA-256：`5e43bf1df9041ec3573106744b908d72f5eaf14d8c359d5cf429728650b2d679`
  - disposition SHA-256：`f9d5258d32dd26c804dfa6903562c2826cc7f536f90b5db15950f60d370b5de1`
  - initial review SHA-256：`2d8b692cf2a9cfa0157918bb4597ad21a6878fceff1d10fcdf863e6d96aa3e04`
  - limited rereview SHA-256：`1baa597f05755121579e46442a007f343ecadbff53ca2a68a8f592788a7953ec`

## 评审范围

评审对象是主树 `/home/xp/src/ghc-api-proxy-py` 中用户列出的九项文件，以及核验 HTTP 499 normalization、retry classification、budget、driver、error envelope、rejection capture 与 observability 所需的相邻生产调用链。隔离 worktree 中的副本不属于评审对象。

当前主树源码与专项测试的 SHA-256 分别为：

- `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py`：`5c4562b301dd8744cce87ebf9727536e1c89b7f8f8219c7d7337d0f033e6632a`
- `/home/xp/src/ghc-api-proxy-py/tests/unit/model_provider/ghc_client/test_http_499_retry.py`：`3c192008f3005d1f54c19b6224cfcc9008835bf9b24d34c65e230e6f30b99d59`

## 总体 verdict

`needs-fix`

生产代码与专项测试没有发现 HTTP 499 retry 的功能性缺陷，但当前 closeout 仍有 2 项 major：实现已经先于现行 requirement authority 生效；承载候选条款和评审闭环的 `.dev` 当前也没有项目规则要求的独立 Git 持久化。因此不可发出最终完成信号。

## blocker 数

0。评审范围已覆盖，没有因权限或工具限制改判 `blocked`。

## C1–C8 逐项裁定

| ID | 裁定 | 核验结论 |
|---|---|---|
| C1 | **PASS** | 当前 `/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:31-33,149-181` 把 499 归一化为带 status 的 `UpstreamError`；`reason_for()` 将其归入 `serverError`，`RetryLedger` 同时执行该策略预算与 `max_total`；`DirectDriver` 在响应交付前完成重试，预算或 draining 拒绝时以当前异常作为 `PipelineAbort.cause`。rejection capture 只接受 `UpstreamRejected`，request trace 只保留尝试总数而不记录 header-stage failure category。status 与 candidate 对这些行为的描述一致。candidate `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:28-32` 明确把 2,859,854 bytes 与约 123.1 秒限定为相关观测，没有写成 Copilot 产生 499 的因果事实。 |
| C2 | **PASS** | candidate `/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:7-10` 只把“499 应支持 retry”归为 `user-initiated`，并给出 session 锚；`serverError` 映射、预算、cooldown、capture 与 error envelope 都归为 `agent-decided-within-delegated-scope`。用户控制目录没有被 agent 改写。status 中指向 candidate 的相对路径实际解析到现存文件，candidate 的目标 Spec 路径也存在。 |
| C3 | **PASS** | 首轮 3 major、1 minor 与 disposition 中四个原 finding 逐项对应；限定复评的四个 outcome 全部为 `fixed`，新增 schema minor 也单独登记并修正。当前每个 `statement_kind` 都是合法单值 `fact` 或 `judgment`；`status=closed`、`open=0`、`disputed=0`、`pending_annotation_ids=none`，总计 `fixed=5`。首轮未采用的 observability 扩展有明确 `rejected_alternative`，没有 finding 被静默拒绝或遗漏。缺少 rereview revision 锚是另一个 auditability minor，不改变本次对当前固定字节的一一对账结果。 |
| C4 | **PASS** | status 使用“在提交所含字节上运行”，没有声称这些命令必然在 commit 落位之后执行。用户给定的 Ruff、Pyright、全量 pytest、缓存隔离专项测试与旧实现正控结果由主会话执行并提供；本 reviewer 没有把它们写成自己重跑的结果。当前源码与测试哈希与既有评审输入一致，status 也没有把运行结果外推为真实 Copilot canary、发布或 cutover 证据。提交仅含两个任务路径、index 状态和共享 WIP 边界同样按主会话给定证据采用，未冒充本 reviewer 的 Git 复查。 |
| C5 | **PASS** | `/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md:5-7,32-36` 正确把 `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md` 命名为 requirement authority，把 candidate 标为待用户决定，并把 status 限定为实现现状报告。candidate 也正确规定：只有条款并入后，代码与测试才是条款的 transcription。当前存在的时间顺序缺口不改变这条“权威方向”本身是对的，但导致 C8 失败。 |
| C6 | **FAIL** | 文档的目录落点、相互链接以及暂不归档均正确。根据已加载的 `handing-off-through-documents`，报告头部 `status: in-review` 与有效尾部交付哨兵可以同时成立，因此两份报告的 `in-review` 本身不是未交付证据；candidate 尚待用户决定，也不应提前把相关材料归档。但是 candidate 顶部仍写“待独立复评”，与已经完成的限定复评冲突；更严重的是 `.dev/.git` 与 `.dev/README.md` 均不存在，而父仓 `/home/xp/src/ghc-api-proxy-py/.gitignore:24-26` 忽略整个 `.dev/`。这与项目规则要求 `.dev` 为独立 repository 并提交开发文档不符，当前材料没有可恢复的 Git 持久版本。 |
| C7 | **PASS** | status 的零删除、未使用 Plan Mode、未发布、未 cutover、未控制 4141 服务及未处理其他会话 WIP 的边界，与主会话给定的 closeout 摘要自洽。本 reviewer 没有执行删除、清理、ref/worktree 操作、发布或 cutover，也没有把隔离 worktree 的生命周期算入本任务。此裁定确认的是给定证据与文档表述一致，不是对历史所有文件系统操作的独立审计。 |
| C8 | **FAIL** | 功能代码已经实现，专项测试覆盖 normalization/classification、成功重试、预算耗尽和 498 负控；没有发现尚未完成的代码项。唯一剩余产品决定确实是用户是否并入 candidate。但是 `/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:9-14` 明令完整行为 Spec 必须先于 observable implementation，而当前用户控制 Spec `/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md:13-20` 尚未包含 499。因而“只剩用户决定”是真的，“已经完整交付且该决定不阻塞 closeout”则不成立。 |

## Findings

### http499-closeout-review-general-sonnet-260904-01：实现已先于现行 requirement authority 生效

- `finding_id`：`http499-closeout-review-general-sonnet-260904-01`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md:32-36`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:9-14`；`/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/upstream-retry-and-continuation.md:13-20`；`/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:7-26`；`/home/xp/src/ghc-api-proxy-py/src/app/model_provider/ghc_client/errors.py:31-33`
- **evidence**：现行用户控制 Spec 的可继续列表只有网络中断、timeout、429 与 5xx，没有 499。candidate 明确声明自己尚待用户并入，status 也承认代码与测试要在并入后才成为条款 transcription；与此同时，主树代码已经把 499 加入 `RETRYABLE_STATUSES`，status 第 36 行却把 Spec 决定称为不阻塞当前支持。项目规则明确禁止 implementation 先于完整 Spec 改变 observable behavior。
- **failure scenario**：如果用户不接受 candidate，生产代码仍会执行一套没有现行 requirement authority 的 499 策略。如果后继维护者依当前 Spec 把 499 当作未列出的 4xx 恢复为 deterministic rejection，代码、status 与 Spec 会分别给出互相冲突、但各自看似有依据的答案。
- **suggestion**：在发出完成信号前，让用户决定 candidate。用户并入时同步目标 Spec 的条款与修订记录，使现有代码和测试正式成为 transcription；用户拒绝或修改时，按其裁决调整实现。若用户有意豁免本次 Spec-first 顺序，应由用户明确裁决并记录，不能由 status 自行宣布该决定“不阻塞”。

### http499-closeout-review-general-sonnet-260904-02：`.dev` closeout 材料没有项目约定的耐久载体

- `finding_id`：`http499-closeout-review-general-sonnet-260904-02`
- `severity`：`major`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.claude/rules/00-development-workflow.md:41-44`；`/home/xp/src/ghc-api-proxy-py/.gitignore:24-26`；缺失的 `/home/xp/src/ghc-api-proxy-py/.dev/.git` 与 `/home/xp/src/ghc-api-proxy-py/.dev/README.md`
- **evidence**：直接文件系统探针确认 `/home/xp/src/ghc-api-proxy-py/.dev/.git` 不存在；读取 `/home/xp/src/ghc-api-proxy-py/.dev/README.md` 得到文件不存在；父仓 `.gitignore` 忽略 `.dev/`。因此 status、candidate、两轮报告和 disposition 虽然当前存在于主树文件系统，却既不属于主仓提交，也没有项目规则所述的独立 `.dev` Git history。
- **failure scenario**：新 clone 无法恢复任何本轮 candidate、评审报告或 disposition；对 ignored 文件执行清理或丢失当前主工作树后，用户唯一待决定的 Spec 候选及其审计依据会同时消失。当前五个 SHA-256 只能证明本次读取的字节，不能从持久 Git object 重建这些字节。
- **suggestion**：由有权处理项目持久状态的一方恢复项目规则规定的独立 `.dev` repository，并把本轮在途材料提交进去；如果 filesystem-only 或独立分支才是用户现在想要的约定，应先由用户裁决并同步项目规则，再为这些材料建立相应的可恢复快照。candidate 尚未并入用户 Spec，不能用提前归档代替持久化。

### http499-closeout-review-general-sonnet-260904-03：candidate 顶部状态仍错误地等待已经完成的复评

- `finding_id`：`http499-closeout-review-general-sonnet-260904-03`
- `severity`：`minor`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/human-controlled-docs-candidates/260904-http-499-retry.md:5`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/status.md:26-30`；`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md:122-131`
- **evidence**：candidate 同时写“修订后待独立复评”和“可供用户决定是否并入”，而 status、限定复评报告与 closed disposition 都确认复评已经完成，首轮四项及新增 schema minor 均已修正。
- **failure scenario**：用户从 candidate 顶部开始阅读时会认为评审门尚未完成而推迟决定；后继会话也可能据此重复派发同一轮复评，产生新的报告和处置分支。
- **suggestion**：把 candidate 状态更新为“限定复评已通过，待用户决定是否并入”或项目采用的等价词；保持其在途位置，不提前归档。

### http499-closeout-review-general-sonnet-260904-04：closed disposition 没有绑定其承重 rereview 的版本

- `finding_id`：`http499-closeout-review-general-sonnet-260904-04`
- `severity`：`minor`
- `primary_location`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/review-disposition.md:4-12`
- `related_locations`：`/home/xp/src/ghc-api-proxy-py/.dev/docs/upstream/retry-and-continuation/reports/260904-http-499-rereview-general-opus.md:3-9,135-147`
- **evidence**：disposition 为首轮报告记录了 `source_report_sha256`，却只以路径引用承重的限定复评，没有 `source_rereview_sha256`。该复评当前仍处于允许协作注记的 `in-review` 生命周期，路径本身不能说明 closed disposition 采用的是哪一版内容。当前固定版本的已知 SHA-256 是 `1baa597f05755121579e46442a007f343ecadbff53ca2a68a8f592788a7953ec`。
- **failure scenario**：如果 rereview 在合法协作期追加更正或被替换，disposition 仍显示 `closed` 和 `fixed=5`，但未来读者无法证明这些终态究竟依据修改前还是修改后的 rereview。
- **suggestion**：在 disposition 中加入当前 `source_rereview_sha256`，并在 rereview 后续发生实质变化时同步重开或重新绑定处置。不要通过覆写报告原文来消除差异。

## 搜索面与证据边界

逐项读取了用户列出的九项主树绝对路径，并读取当前 `retry.py`、`exceptions.py`、`DirectDriver`、`GhcApiClient`、composition root、pipeline driver、error classification、HTTP error writer、rejection capture、request trace 与 inference edge。五项指定文档 hash、源码 hash、测试 hash及 candidate 相对路径均由本 reviewer 直接重算或解析。

没有重新运行 Ruff、Pyright、pytest 或旧实现正控；这些结果按主会话提供的执行证据采用，并保留执行者身份。隔离层拒绝对主树运行 Git 命令，因此提交两文件集合、index 状态和共享 WIP 边界同样没有冒充本 reviewer 的独立 Git 结果。直接读取 `/home/xp/src/ghc-api-proxy-py/.git/HEAD` 与 `/home/xp/src/ghc-api-proxy-py/.git/refs/heads/main` 确认 main 当前指向给定 OID。

未发起真实 Copilot billed request，未读取 2026-09-03 capture 原件，未检查其他会话 worktree 的内容，也未审计 4141 运行态。因此报告不把生产观测升级为 499 成因证明，也不对共享 WIP 作超出给定 closeout 摘要的全称断言。

## 我最没把握的三个判断

1. **`.dev` 缺少独立 repository 定为 major 而非 minor。** 当前文件确实位于主工作树，足以跨过本 reviewer worktree 的自动清理；但 candidate 是用户剩余决定的唯一输入，而项目规则明确要求 `.dev` 独立版本化。新 clone 无法恢复它这一失败场景使问题触及长期交付义务，因此按 major 处理。若用户已另行决定 filesystem-only 持久化，则应提供该裁决并同步项目规则，届时可重判。
2. **没有把两份报告的 `status: in-review` 单独列为 finding。** 已加载的报告协议明确规定：有效尾部哨兵决定是否交付，`in-review` 表示已交付并处于协作期，不等于草稿。candidate 仍待用户决定也支持相关材料继续留在活跃位置。若项目另外要求 disposition 一关闭就立刻把报告转为 `settled`，这最多形成一个附加 lifecycle minor，不推翻报告已经交付的事实。
3. **C4 与 C7 的 PASS 使用了主会话给定证据。** 当前文件 hash 和 main ref 是本 reviewer 直接核验的；测试运行、commit 两文件集合、index 与零删除历史不是。本契约明确提供这些事实并要求不要伪装执行者，所以按其原始来源采用。若这些输入后来被证明错误，C4 或 C7 应降为 `INCONCLUSIVE`，不能保留现有 PASS。

## 执行本契约时遇到的摩擦

- `my-agents:as-reviewer` 未出现在可路由 Skill 列表中，因此按用户指定 fallback，在读取任何被评对象前直接读取了 `/home/xp/.claude/my/my-agents/skills/as-reviewer/SKILL.md`。第一次 Read 因误传空 `pages` 参数被工具拒绝，随即以合法参数重试成功；该失败发生在任何被评对象读取之前。
- CodeGraph 报告 auto-sync 因锁竞争关闭，并把多个 `.claude/worktrees` 的同名符号混入结果。所有承重源码结论都改用目标主树绝对路径直接读取；混入的 worktree 内容没有进入裁定。
- pinned worktree 的隔离层拒绝对 `/home/xp/src/ghc-api-proxy-py` 执行主树 Git 命令。没有绕过隔离层，而是以 `sha256sum`、直接读取 `.git/HEAD` 与 main ref、文件系统存在性探针完成可独立完成的部分；其余提交和运行事实明确保留为主会话提供的证据。
- 本轮没有修改、暂存、提交、清理或删除任何文件，也没有操作 ref、worktree、服务、发布或 cutover。

## 交付声明

- `delivery_complete`：`true`
- `completed_at`：`2026-09-04`
- `finding_total`：`4`
- `blocker`：`0`
- `major`：`2`
- `minor`：`2`
- `nit`：`0`
- `completion_signal_allowed`：`false`。当前不是“只剩 minor”的状态；两个 major 关闭或经用户明确裁决前，不可宣告本任务完整 closeout。

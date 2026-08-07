# 文档渐进式重组实施计划

> 状态：R4、merged-state R2 与定向终审 R7 指出的 major 均已修订，连同既有修订待定向独立复评；复评达到 0 blocker、0 major 后可执行
> 规划基线：`47d9ef101c4b81ac70d805b1da157b34d021d33d`
> 基线日期：2026-08-06
> 计划位置：`docs/agents/documentation-restructure/plan.md`

## 1. 目的与完成定义

本计划把 `docs/2604-rewrite/` 中混合存在的当前实现说明、已决产品合同、未来设计、调研、评审和已完成实施材料，渐进式重组为可持续维护的活文档、开发文档与归档文档。实施只重组文档，不顺带修改产品行为，不替用户作新的产品或架构裁决。

重组完成必须同时满足以下条件：

1. `docs/README.md` 是活文档统一入口，读者无需阅读旧目录或临时报告，就能找到 Anthropic Messages、OpenAI Responses upstream、streaming、API、配置、History、运维和路线图的当前真相。
2. `docs/` 中每项“当前支持”都可追溯到生产 route、settings、schema、lifespan、真实调用点或可执行探针；helper、配置字段或测试中存在某符号，不能单独证明生产已接线。
3. 当前实现与已决目标明确分栏。尚未实现的目标必须紧邻标注“当前未接线”，并链接到对应 `docs/agents/<topic>/` 开发文档。
4. block-level buffering 被准确写成基础产品合同：上游可流式读取，代理以完整 block 为下游提交单元，block 完成前不暴露局部内容，下游不承诺 token/event 级 live streaming。当前 raw-byte/chunk passthrough 只作为实现差距记录，不能反向改写目标合同。
5. Anthropic Messages 与 OpenAI Responses upstream 的产品优先级在活路线图、主题规格和实施顺序中一致。
6. 本计划第 5 节列出的 42 份 Markdown 候选均有且只有一个 disposition、一个 `final move phase` 和一个 canonical source-retention destination；每项的 `extract phases` 与精确 pathspec 均被冻结，无遗漏、无未标注的正文副本、无活文档继续依赖旧目录。
7. 旧文档记录的每项功能都有 `docs/ROADMAP.md` 或具体 topic spec 去向。不得因成本、ROI、复杂度或 YAGNI 删除、降级或无限期推迟功能；改变范围必须取得新的用户裁决。
8. 旧零缓冲、整响应 opt-in、块级延后以及其他已被当前裁决取代的方案，只保留在带取代说明的 archive 中，不再充当当前入口。
9. 仓库级 Markdown 链接、route/settings/schema 对账、源内容 provenance／精确与近似重复 gate、bridge 规范输入 identity gate、临时报告归纳 matrix gate、项目质量门和独立合并态评审全部通过；阶段 0A 只在父 HEAD 不存在 protocol marker、bootstrap kernel、latest pointer 与任何 closed generation 时提交做过 repo 外冻结 fixture 双向控制的 checker／schema／fixtures及不可变 marker，阶段 0B 再用已提交 0A checker 生成并关闭 generation 0，之后所有依赖动作只消费 latest non-stale closed generation，并在执行前通过精确绑定的 closure-review certificate 与 post-cut report impact gate。
10. 文档重组按主题切片独立提交，不抢占产品实现主线。产品紧急工作可在任一已提交切片后安全插入，文档工作恢复时从下一切片继续，而不是要求一次性搬完。

## 2. 已裁决结构与不可变约束

### 2.1 文档分层

用户已裁决以下目录职责，实施者不得自行改为其他分类：

- `docs/`：活文档，承载当前运行态真相、已裁决且长期成立的产品合同，以及明确标注的当前实现缺口。
- `docs/agents/<topic>/{spec,plan,etc.}`：开发文档，承载目标规格、实施计划、PoC、验收 oracle、评审与进行中状态。
- `docs/agents/<topic>/archive-<date>/`：归档文档，承载已被取代的方案、完成后的过程文档、历史评审和 handover。

临时调查材料不是长期权威，也不进入新的规范引用链。`docs/tmp/**` 不得成为未登记的权威来源：报告中任何会改变当前合同、实现状态、验收 verdict、下一动作或 gate 的结论，都必须先按第 2.5 节登记并归纳到正式 owner；正式文档必须在不依赖临时报告继续存在的前提下提供当前结论、证据边界和下一动作。迁移提交不得纳入 `docs/tmp/**`。

渐进迁移窗口内，任何在阶段 1 结束后仍留在 `docs/2604-rewrite/` 的 Markdown 都是“迁移输入”，不是当前真相源。阶段 1 必须给这些文件加统一、醒目的迁移期 banner，并在 `docs/README.md` 明示旧目录整体不再具有真相源地位。banner 只能说明取代关系、现行入口、已裁决优先级、buffering 高层合同和最终移交阶段；它不得借文档迁移补写未裁决产品设计，也不得把未实现目标写成当前行为。

### 2.2 产品优先级

产品与文档切片顺序固定为：

1. Anthropic Messages。
2. OpenAI Responses upstream，包括 HTTP 与 WebSocket 上游接线的真实边界。
3. 两条主线共享的 pipeline、配置、History、可观测性和运维基础。
4. Chat Completions、Azure、Gemini 等次级协议与增强能力。

文档重组服务产品主线，不反客为主。每个阶段形成独立、可停靠的提交；如果产品工作需要优先推进，先完成或回退当前文档切片，再暂停重组，不占用连续的大段主线开发窗口。

### 2.3 Streaming 产品合同

以下合同已经裁决，不属于本计划可重新选择的技术方案：

- block-level buffering 是基础能力，不是 opt-in backlog。
- 上游可以流式读取，但代理以完整 block 为下游提交单元。
- block 完成前不向下游暴露其局部内容。
- 下游不承诺 token/event 级 live streaming 体验。
- 当前基线代码仍以 raw-byte/chunk passthrough 为主。活文档必须并列写出“已决目标”和“当前实现”，不得把目标写成已经实现，也不得用当前实现否定目标。

高层合同没有自动统一所有协议，但也不得覆盖已经由更具体规格冻结的逐协议合同。阶段 1 必须按 topic／protocol 分栏，并遵守“具体且已接受的绑定内容版本优先于本计划，旧 `docs/2604-rewrite/` 只作历史素材”的顺序。对 Anthropic Messages 入站选择 OpenAI Responses upstream 的 bridge，行为与验收规范输入冻结为下表的已接受内容对；路径存在、文件名不变或读取到某个“current”版本都不能替代内容身份、状态与绑定关系检查。

| 角色 | 路径 | 必需状态 | 当前绑定 SHA-256 | 绑定关系 |
|---|---|---|---|---|
| 行为规范 | `docs/agents/anthropic-responses-bridge/spec.md` | `FINALIZED` | `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` | Acceptance 必须显式绑定本内容身份 |
| 验收规范 | `docs/agents/anthropic-responses-bridge/acceptance.md` | `FINALIZED_ACCEPTANCE_ORACLE` | `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4` | 文件内行为 oracle 必须绑定上述 Spec SHA-256，并保留已完成的七域 `POLICY-MANIFEST-v1` 对账 |

上述两项 current SHA-256 已在 `main@ed77c9d191df81c451c25161420515cca52ce6a4` 同一 shell gate 中分别用 `sha256sum` 与 Python `hashlib.sha256` 现场交叉复核。两者已经冻结 Anthropic content block 边界、pre-commit／post-commit retry frontier、memory-only／no spill／无 16 MiB 特例、Anthropic SSE delayed-start、cancel／cleanup 以及 History 时点，阶段 1 不得把这些事项重新列为未决。`docs/agents/anthropic-responses-bridge/architecture.md` 在 current Acceptance 中明确是“架构参考而非行为 oracle”；无论其内容是否与 Spec 一致、是否通过文档评审，只要尚未形成另行接受的 ADR，它都不得进入行为 `normative_inputs`、不得产生或改写 expected，只能作为非规范参考记录。只有其他协议或共用机制中未被现有 accepted Spec／ADR／Acceptance 覆盖的部分，才保留为第 9 节门控问题。

阶段 0 生成规范输入 manifest 前和阶段 1 任一 bridge 相关 gate 开始前，都必须重新计算两份文件的 SHA-256、读取其规范状态并验证 Acceptance → Spec 绑定。任一内容 hash、状态、绑定关系或七域对账身份漂移时，所有阶段 1 bridge 相关生成、检查、提交与阶段推进立即停止；不得自动接受新 bytes、不得只刷新 hash，也不得退回“路径仍存在所以继续”。恢复必须先完成新内容对的规范对账与独立复评，再以独立验证资产提交显式更新 manifest；Architecture 的变化不能作为刷新行为 expected 的理由。

### 2.4 完整需求保留

不得因成本、ROI、YAGNI、旧文档中的“默认关闭”“简化”“缓存”“延后”或本轮产品优先级而删除功能。未进入当前主线的能力应迁入对应 topic spec 或 `docs/ROADMAP.md`，保留需求、依赖、前置条件和验收意图。若旧文档标为拒绝但找不到直接用户裁决，状态只能写为“待重裁”，不能沿用旧作者的取舍作为用户决定。

### 2.5 临时报告命名与归纳

- 从本规则生效起，新建的 `docs/tmp/*.md` 报告必须使用实际创建日和主题命名为 `YYMMDD-<topic>.md`，不得沿用固定历史日期。同一主题在同日产生多份或多轮报告时，使用 `YYMMDD-<topic>-rN.md`，或使用能够说明轮次或报告性质的明确后缀，例如 `-arbitration`、`-verification` 或 `-distillation`；不得覆盖旧报告或使用含义不明的临时编号。
- 既有无日期前缀报告可原样保留为历史临时输入，不要求批量重命名；不得为了符合新规则而复制旧报告并赋予新的日期前缀或新命名，避免同一历史证据形成两个身份。
- `docs/tmp/` 只承载待归纳的临时证据，不是长期状态或结论载体。每份 `docs/tmp/*.md` 报告都必须进入阶段 0B 建立的机器可读 generation 协议。`docs/agents/documentation-restructure/verification/report-distillation-ledger.json` 只保存 generation 索引、前代 closure hash、latest non-stale closed `<ordinal, revision>` pointer 与 current kernel version；每代不可变 revision 的冻结输入、身份、逐结论归纳和 closure 分别位于 `report-generations/generation-<N>/revision-<R>/{inventory,identity,distillation-ledger,closure}.json`。每个 `distillation-ledger.json` 条目至少记录 `report_path`、`report_sha256`、逐条 `conclusion_id`、verdict、对应正式落点与 anchor、`coverage_status`、未覆盖项、正式 owner、受影响 action／topic、`unresolved_action_impacts` 和失效条件。正式落点必须位于对应 topic 的长期文档或正式易变状态载体，不能仍是 `docs/tmp/**`。
- `coverage_status` 只允许 `covered`、`partial`、`pending`。`covered` 表示每条 load-bearing 结论都已有可解析的正式落点与 anchor，读者无需读取临时报告即可知道当前结论、证据边界与下一动作；`partial`／`pending` 必须列出未覆盖结论、正式 owner 和被阻断动作，不能作为继续执行的通行证。checker 必须拒绝漏登记报告、漏结论、正式落点不存在或落回 `docs/tmp/**`、anchor 不存在、`covered` 仍有未覆盖项，以及 `partial`／`pending` 未声明阻断范围。
- 每代 cut-off 必须由 checker 在一次受同调用 root／HEAD gate 约束的扫描开始事件中机械生成：按路径排序冻结当时全部 `docs/tmp/*.md` 的路径集合与每项 content SHA-256，并记录 cut-off 时间、仓库 HEAD、checker commit／content hash、schema version 和前代 closure hash。generation `<N,R>` 的 checker 只验证该 revision 冻结的 inventory、identity、distillation ledger 与正式落点；不得把扫描结束后新增的报告正文反向并入 `<N,R>`，也不得仅因当前目录比 inventory 多文件而改写已关闭 revision。这个不改写规则不豁免 action gate：post-cut 报告仍须按 verdict／action impacts／hash 立即判定未消费授权是否 stale。冻结集合内的报告消失或 bytes 改变、正式落点失效、closure 组件 hash 不一致时，`<N,R>` 必须失败。
- generation 状态只允许 `dirty`、`pending`、`closed`、`stale`，身份是 `<ordinal, revision>`。ordinal `N` 表示受管动作序位，revision `R` 表示该动作尚未消费前对同一 ordinal 授权的不可变修订；初版是 `<N,0>`。只有授权尚未消费且新报告直接评审或影响该 generation／action 时，才可用 `<N,R+1>` 关闭同 ordinal 修订；旧 revision 保留但标为 `stale`，永不可消费。动作一经消费，同 ordinal 不得再修订，任何新报告归入 `N+1`。扫描 cut-off 后新增的报告仍机械创建或更新后继 dirty inventory，不得把正文回写到已冻结 revision；但“归入后继代”不等于“对当前授权延迟生效”。在授权动作执行前，checker 必须按报告 verdict 与 action impacts 重新分类所有 post-cut 报告：任何 blocker／major，或任何 verdict 下影响当前 `action_id`、action type、subject identity 或 topic 的报告，立即使相关 revision 与 action `stale`。修复与正式归纳完成后，必须先关闭精确包含该报告身份的同 ordinal revision，或在协议不允许同 ordinal 修订时关闭下一 generation，旧授权不得先被消费。报告 bytes／hash 漂移、subject generation 不匹配或 impact 字段缺失同样 fail closed。
- 关闭 `<N,R>` 时，已提交 checker 以显式 generation identity 验证冻结报告集合与 ledger 双向精确相等、全部 action-relevant 结论均 `covered`、正式 anchor 可解析，并对 inventory／identity／ledger 的 canonical bytes 写入 closure payload。独立 closure review 必须先产出不含 certificate 的人类可读 review report，再由 checker 从已冻结 report bytes 生成独立的 machine-readable certificate；二者不得是同一文件，certificate 也不得写回 report，避免 report 自哈希。certificate 至少精确绑定 review report path＋SHA-256、`subject_generation_id=<N,R>`、closure payload hash、唯一 action identity、review verdict、blocker／major 计数、observed post-cut report path＋hash 集合、逐项 action impacts 与 `unresolved_action_impacts`；closure 再绑定 certificate path＋SHA-256。只有 verdict 为 `PASS`、blocker／major 均为 0、subject／payload／action／observed-set 精确匹配且 `unresolved_action_impacts=[]` 时，才允许把 certificate identity 纳入 closure，并把被其绑定的 review report 正文窄化 carry forward 到后继 dirty generation；这只授权 certificate 精确绑定的一个动作，不是泛化豁免。review report 与 certificate 都进入后继 inventory；任一 bytes／hash 漂移或 certificate 后又出现未被 observed-set 覆盖的 post-cut 报告时，当前 action 立即 stale，必须重新评审并关闭修订版或下一代。
- “及时”的机械截止点不是自然日，而是受管动作序列。每个 non-stale closed generation revision 只授权一个精确动作实例，closure 必须记录唯一 `action_id`、动作类型、受影响 topic、subject identity 与预期 HEAD／payload manifest 或清理目标；动作集合固定包括 `docs_commit`、`phase_advance`、`product_replay`、`archive_cleanup`、`worktree_cleanup`、`user_ruling`。对 `docs_commit`，subject identity 是按路径排序的 staged payload path＋blob SHA-256 manifest；payload 明确排除本代 machine-readable certificate、`closure.json` 与 generation index，certificate 绑定 closure payload，closure 单向绑定 certificate identity 与该 payload manifest hash，index 只绑定 closure hash，避免任何文件直接或间接哈希自身。完整 staged allowlist 仍必须包含这三个控制面文件并与实际 staged paths 精确相等，排除只影响 action payload hash，不形成漏提交豁免。动作 gate 必须在执行前重扫 post-cut report identity／verdict／impacts并验证 certificate observed-set，且只允许消费 latest non-stale closed revision 与精确相等的 action request；一次动作完成后，任何下一受管动作都必须使用后继 ordinal。对本动作无影响且经 PASS certificate 证明 unresolved impacts 为空的报告可窄化 carry forward；无关 topic 的结论不造成 false-red，但仍保留在后继 inventory 与 ledger 中并记录其 action scope。
- 禁止任何自评 bootstrap 豁免：不得提供 `--skip-ledger`、`--bootstrap`、空 ledger 即成功、checker 不存在即跳过、按分支名／操作者声明识别首次运行等路径。阶段 0A 的唯一入口命名为 `bootstrap_kernel_commit`，它是与 generation gate 不同但机械一次性的构建步骤。固定 marker 路径是 `docs/agents/documentation-restructure/verification/protocol-marker.json`，固定 kernel namespace 是 `docs/agents/documentation-restructure/verification/bootstrap-kernel/`，latest pointer 是 `docs/agents/documentation-restructure/verification/report-distillation-ledger.json`。`bootstrap_kernel_commit` 必须从待创建提交的父 HEAD 读取状态；只有父 HEAD 同时不存在 marker、kernel namespace 下任何 path、latest pointer 和任何 closed generation closure 时才允许继续。marker 一旦存在，原 bytes 或换 bytes 的任何再次调用都必须在写 commit 前确定性失败，不能以 marker 内容损坏、checker 更新或新 fixture 为由重进 0A。
- 0A staged allowlist 必须精确等于固定 marker path，加上 `bootstrap-kernel/bootstrap-assets.txt` 逐字列出的 checker／schema／fixtures／fixture hash manifest／bootstrap test instructions；该清单必须列出自身路径且不使用 glob，bootstrap harness 必须验证 staged paths 双向精确相等。不可变 marker 至少记录 protocol id、bootstrap protocol version、父 HEAD、`bootstrap-assets.txt` blob identity、`bootstrap-kernel/` subtree Git tree OID，以及按 literal path 排序的全部非 marker kernel asset path＋Git blob OID 所形成的 canonical kernel identity；marker 自身位于 kernel namespace 外且不进入 subtree／blob identity，避免自哈希，独立 0／0 receipt 反向绑定 marker blob OID、kernel subtree tree OID、kernel blob identity 与候选 repository tree identity。稳定失败合同固定为：marker 已存在返回 `40/bootstrap_marker_exists`，kernel footprint 已存在返回 `41/bootstrap_kernel_exists`，latest pointer 已存在返回 `42/bootstrap_latest_exists`，closed generation 已存在返回 `43/bootstrap_closed_generation_exists`，staged allowlist 不相等返回 `44/bootstrap_staged_allowlist_mismatch`，kernel tree／blob identity 不匹配返回 `45/bootstrap_kernel_identity_mismatch`，repo 外 fixture identity 不匹配返回 `46/bootstrap_fixture_identity_mismatch`，独立回执不合格返回 `47/bootstrap_review_receipt_rejected`；不得把这些失败降级为 warning 或继续 commit。0A 必须对 repo 外只读冻结 fixture 运行正反控制，并在提交前取得上述独立回执；回执不进入 staged paths，其路径＋hash 由 harness 记录，随后由 0B generation 0 正式登记。0A 成功后 marker 永不修改或删除；任何 checker／schema／fixture／kernel 协议升级都必须作为普通 versioned migration generation，记录递增 kernel version、前代 kernel identity、新 kernel identity 与精确 `docs_commit` action，通过同一 closure certificate／action gate 后更新 latest pointer，绝不得再次执行 0A。阶段 0B 及其后的所有受管动作一律由 committed kernel 验证 generation，不存在人工判定“这次特殊”的入口。
- `docs/tmp/260807-tmp-distillation-matrix.md` 只作为本条设计时的 current 示例与一次性迁移输入：它展示“报告 → 正式落点 → coverage → 截止动作”的所需维度，但不是永久 schema、运行时 oracle 或 checker 依赖。阶段 0B 必须在 generation 0 cut-off 中从当时实际 `docs/tmp/*.md` 集合和各正式 owner 重建 inventory／identity／ledger，吸收该示例中仍有效的条目，并把该矩阵自身也登记；checker 运行不得要求该临时文件继续存在，也不得复制其中的点时计数作为 current 结论。

## 3. 规划基线与已知事实约束

### 3.1 基线口径

- 仓库根目录：`/home/xp/src/ghc-api-proxy-py`。
- 规划 HEAD：`47d9ef101c4b81ac70d805b1da157b34d021d33d`。
- 候选集合：该 HEAD 下 `docs/2604-rewrite/**/*.md` 的 42 份 Markdown。实施阶段 0 必须用文件清单工具和 Python `Path.rglob()` 两种不同原理重新交叉验证，并冻结实际集合。
- 阶段 0 必须为每个源冻结原始字节 `SHA-256`、剥离受管迁移／归档头后的正文 `SHA-256`、canonical source-retention destination、`destination_kind`、`extract phases`、唯一 `final move phase` 和逐阶段精确 pathspec。canonical destination 通常是 archive；第 5 节明确迁成仍有效开发资产／研究资产的少数文件，其目标文件本身是唯一 source-retention destination，不得再保留第二份未标注 archive 快照。
- 可复现验证资产固定放在 `docs/agents/documentation-restructure/verification/` 并分两个独立提交：阶段 0A 只含固定 `protocol-marker.json` 与 `bootstrap-kernel/bootstrap-assets.txt` 逐字列出的 checker、schema、fixtures、fixture hash manifest 与 bootstrap test instructions；阶段 0B 只含由已提交 0A checker 生成并验证的 42 项 manifest、规范输入 identity、逐阶段 pathspec 清单、generation 0 inventory／identity／distillation ledger／closure、closure-review certificate 及 generation index。运行输出、缓存、repo 外冻结 fixture 副本和一次性报告只放系统临时目录，不提交，也不得进入 `docs/tmp/**`。
- 规划时工作树已有未跟踪材料。所有阶段必须保存阶段开始时的 `git status --short`，只提交本切片精确 pathspec，不纳入既有脏项。
- 固定规划 HEAD 是事实起点，不是后续每次 shell 都必须相等的恒等 gate。首次执行确认它是当前 HEAD 的祖先；之后记录每个切片自己的开始 HEAD 和结束 HEAD。

### 3.2 当前实现与旧文档的关键冲突

下列事实是迁移时必须逐项复验的最低约束，不是完整正确性证明：

1. Anthropic 当前只注册 `/v1/messages` 与 `/v1/messages/count_tokens`；没有 `/anthropic` 别名前缀和 Anthropic models route。
2. Anthropic 流式生产链当前由 idle timeout、History usage tap、raw-byte passthrough 与 cleanup 组成；block-level buffering、delayed commit、stream keepalive 和 repetition detector 没有进入该生产链。
3. OpenAI Responses HTTP 位于 `src/app/routes/openai.py`，WebSocket 位于 `src/app/routes/responses_ws.py`。二者不得被写成“复用 Anthropic 完整 pipeline”。
4. OpenAI／Responses router 有三重前缀；Anthropic router 没有对应三重前缀。
5. 配置在 `create_app()` 与 lifespan 启动时固定；当前没有 YAML PUT、settings 原子替换或运行时热重载路径。
6. `stream_keepalive_*`、`stream_commit_after_sec`、`upstream_keepalive` 和 `upstream_h2_ping` 等字段或 helper 的存在不等于 transport／route 已消费。
7. Azure 和 Gemini 只共享部分设施。Gemini 有专用逐帧转换，Azure 使用 OpenAI wire 适配；通用跨协议 translator 不能写成当前生产能力。
8. 当前只有 Anthropic 流式 route 接入 idle timeout。其他协议是否接入必须逐 route 取证。
9. History 当前没有旧文档宣称的完整 zstd、可靠重试、统一 in-flight 保证、完整响应 accumulator、分页搜索或流式 export 契约；Anthropic consumer 与其他协议 finalize 路径必须分开描述。
10. 代理当前不提供 server-tool 执行、过滤或拒绝后降级能力；wire 字段可能透传不等于代理支持 server tools。
11. Anthropic cache-control 四模式与自动 context editing 当前没有完整 settings 和请求准备链接线。

任何“支持”“始终”“所有”“热生效”“异步不阻塞”等全称断言，都必须主动寻找反例路径。审计没有点名的句子仍须从生产入口重新验证，不能因为未列入上述清单而直接提升。

## 4. 目标文档模型

| 主题 | 活文档 | 开发文档主题 | 内容边界 |
|---|---|---|---|
| 文档入口与架构 | `docs/README.md`、`docs/ARCH.md` | `docs/agents/architecture/` | 当前组件、装配、真实数据流、文档状态约定 |
| API 与协议矩阵 | `docs/API.md` | `docs/agents/anthropic-routing/`、`docs/agents/multi-protocol/` | 实际端点、入站协议、真实 upstream、转换与 wrapper 矩阵 |
| 产品路线图 | `docs/ROADMAP.md` | `docs/agents/product-roadmap/` | 已决优先级、完整待实现能力、依赖与状态 |
| Anthropic Messages | `docs/ANTHROPIC_MESSAGES.md` | `docs/agents/anthropic-messages/`、`anthropic-cache-context/`、`anthropic-feature-negotiation/`、`anthropic-sanitize/`、`anthropic-tool-use/` | 当前请求准备、兼容边界、headers、thinking、tools、目标与缺口 |
| OpenAI Responses upstream | `docs/OPENAI_RESPONSES.md` | `docs/agents/openai-responses/` | HTTP／WS 当前 upstream、pipeline 差异、History 与 buffering 接入顺序 |
| Buffering 与流消费 | `docs/STREAMING.md` | `docs/agents/buffering/`、`streaming-resilience/`、`stream-consumers/`、`upstream-keepalive/` | 已决下游合同、逐协议现状、待实现语义与探针 |
| 配置 | `docs/CONFIG.md` | `docs/agents/configuration/`、`config-hot-reload/` | 当前 schema、默认值、生效时点、保留但未消费字段 |
| 认证与模型 | `docs/AUTHENTICATION.md`、`docs/MODEL_RESOLUTION.md` | `docs/agents/authentication/`、`model-resolution/` | 当前 token/provider 与模型解析契约 |
| 请求处理 | `docs/REQUEST_PIPELINE.md`、`docs/SANITIZE_PIPELINE.md` | `docs/agents/request-pipeline/`、`anthropic-sanitize/` | 当前 Anthropic pipeline、重试所有权、mandatory sanitizer |
| Hooks 与 Tokenization | `docs/HOOKS.md`、`docs/TOKENIZATION.md` | `docs/agents/hooks-tokenization/` | 当前运行态摘要与已实施规格／计划历史 |
| History | `docs/HISTORY.md` | `docs/agents/history-durability/`、`history-api/` | 当前 schema、写入时序、REST／WS；可靠性与 API 扩展分开规划 |
| 运行与可观测性 | `docs/OPERATIONS.md`、`docs/OBSERVABILITY.md`、`docs/APPROVAL.md` | `docs/agents/operations/`、`observability/`、`approval/` | 当前关闭、deadline、metrics、tracing、TUI、审批接线 |
| 依赖选型 | 无独立活文档；必要结论链接到 `docs/ARCH.md` | `docs/agents/dependency-selection/` | 调研、选择、证据日期与版本复核 |
| 旧整体实施 | 无 | `docs/agents/2604-rewrite/archive-2026-08-06/` | 已完成总计划、kick-off、handover 与评审历史 |

主题目录只在对应切片开始时创建，不预建空目录。每个新主题至少包含有实质内容的 `spec.md`、`plan.md`、`research.md` 或归档文件。

## 5. 完整 old → new 映射

“拆分”表示先把经验证的当前事实写入活文档，把仍有效的未来需求写入 topic spec，再把原文件完整移入 archive。“迁移”同样要求在一个提交内修正标题、状态、链接和事实错误，不能机械改名。活文档不得保留一份未标注的旧正文副本。

### 5.1 顶层设计与主题文档

| 旧文件 | 方式 | 新位置／产物 | 提升前 gate |
|---|---|---|---|
| `docs/2604-rewrite/260403-docs-review-01-claude.md` | 归档 | `docs/agents/architecture/archive-2026-08-06/260403-docs-review-01-claude.md` | 加归档头，链接现行正式入口 |
| `docs/2604-rewrite/BACKLOG.md` | 拆分 | 需求进入 `docs/ROADMAP.md` 与各 topic `spec.md`；原文进入 `docs/agents/product-roadmap/archive-2026-08-06/BACKLOG.md` | 移除以成本／ROI／YAGNI 砍功能的依据；buffering 改为基础能力；每项有去向 |
| `docs/2604-rewrite/DESIGN.md` | 拆分 | 当前架构进入 `docs/ARCH.md`；实际路由进入 `docs/API.md`；产品合同进入对应活文档；未来设计进入 topic specs；原文进入 `docs/agents/architecture/archive-2026-08-06/DESIGN.md` | 修复 buffering、路由、热重载、History 与兼容矩阵事实 |
| `docs/2604-rewrite/ROADMAP.md` | 重写并归档原文 | 新版 `docs/ROADMAP.md`；原文进入 `docs/agents/product-roadmap/archive-2026-08-06/ROADMAP.md` | 优先级改为 Anthropic Messages → OpenAI Responses upstream；buffering 不得延后；旧能力全部归位 |
| `docs/2604-rewrite/anthropic-compat.md` | 拆分 | 当前矩阵进入 `docs/ANTHROPIC_MESSAGES.md`；cache／context 目标进入 `docs/agents/anthropic-cache-context/spec.md`；原文进入 `docs/agents/anthropic-messages/archive-2026-08-06/anthropic-compat.md` | 修复 server-tool、cache control、context management、路由及“wire 透传 ≠ 代理支持” |
| `docs/2604-rewrite/approval-system.md` | 核实后拆分 | 当前合同进入 `docs/APPROVAL.md`；未来设计进入 `docs/agents/approval/spec.md`；旧超前内容进入 `docs/agents/approval/archive-2026-08-06/approval-system.md` | 从 route、gate、WS manager 与测试生成 REST／WS／timeout 矩阵 |
| `docs/2604-rewrite/authentication.md` | 核实后拆分 | 当前合同进入 `docs/AUTHENTICATION.md`；未来能力进入 `docs/agents/authentication/spec.md`；原文进入 `docs/agents/authentication/archive-2026-08-06/authentication.md` | 删除热重载现在时，核对 provider 顺序、refresh、CLI 与脱敏 |
| `docs/2604-rewrite/config-system.md` | 重写并归档 | 当前合同进入 `docs/CONFIG.md`；热重载目标进入 `docs/agents/config-hot-reload/spec.md`；原文进入 `docs/agents/configuration/archive-2026-08-06/config-system.md` | 配置表由当前 Pydantic schema 生成，标注启动冻结／运行消费／保留未接线 |
| `docs/2604-rewrite/data-models.md` | 拆分 | wire 契约进入 `docs/API.md`；当前内部模型进入 `docs/ARCH.md`；未来设计进入 `docs/agents/data-models/spec.md`；原文进入 `docs/agents/data-models/archive-2026-08-06/data-models.md` | 对照 Pydantic、dataclass 与 schema，移除不存在的对象图和 History 字段 |
| `docs/2604-rewrite/feature-negotiation.md` | 核实后拆分 | 当前摘要进入 `docs/ANTHROPIC_MESSAGES.md`；完整合同进入 `docs/agents/anthropic-feature-negotiation/spec.md`；原文进入 `docs/agents/anthropic-feature-negotiation/archive-2026-08-06/feature-negotiation.md` | 同时核对 enum、生产构造、管理 API 与测试；不得恢复 server-tool 类别 |
| `docs/2604-rewrite/header-forwarding.md` | 核实后拆分 | 当前用户合同进入 `docs/ANTHROPIC_MESSAGES.md`；详细设计进入 `docs/agents/header-forwarding/spec.md`；原文进入 `docs/agents/header-forwarding/archive-2026-08-06/header-forwarding.md` | 对照 request preparation 和实际 request／response header 链 |
| `docs/2604-rewrite/history-system.md` | 拆分 | 当前事实进入 `docs/HISTORY.md`；可靠性目标进入 `docs/agents/history-durability/spec.md`；API 扩展进入 `docs/agents/history-api/spec.md`；原文进入 `docs/agents/history-durability/archive-2026-08-06/history-system.md` | 修复压缩、写入等待、异常、in-flight、schema、分页、export 与 WS 事件事实 |
| `docs/2604-rewrite/hooks-system.md` | 核实后迁移 | 当前合同进入 `docs/HOOKS.md`；完整内部合同由 `docs/agents/hooks-tokenization/spec.md` 承载；原文进入 `docs/agents/hooks-tokenization/archive-2026-08-06/hooks-system.md` | 对照 registry build、loader、executor、built-ins 与 lifespan；不得宣称热替换 |
| `docs/2604-rewrite/hooks-tokenization-spec.md` | 迁移并校正引用 | `docs/agents/hooks-tokenization/spec.md` | 保留“已实施”状态前逐条复验验收标准与当前代码 |
| `docs/2604-rewrite/model-resolution.md` | 核实后拆分 | 当前合同进入 `docs/MODEL_RESOLUTION.md`；未来能力进入 `docs/agents/model-resolution/spec.md`；原文进入 `docs/agents/model-resolution/archive-2026-08-06/model-resolution.md` | 用 resolver 测试与 catalog 路径复验优先级、规范化和 override |
| `docs/2604-rewrite/multi-protocol.md` | 拆分 | 当前矩阵进入 `docs/API.md` 与 `docs/ARCH.md`；translator 目标进入 `docs/agents/cross-protocol-translation/spec.md`；次级协议缺口进入 `docs/agents/multi-protocol/spec.md`；原文进入 `docs/agents/multi-protocol/archive-2026-08-06/multi-protocol.md` | 修复“共享完整 pipeline”、通用 translator、idle timeout 全覆盖和 buffering 延后表述 |
| `docs/2604-rewrite/project-structure.md` | 核实后合并 | 当前模块与生命周期进入 `docs/ARCH.md`；开发约束进入 `docs/agents/architecture/spec.md`；原文进入 `docs/agents/architecture/archive-2026-08-06/project-structure.md` | 用真实目录与 lifespan 复验，不复制目标模块树 |
| `docs/2604-rewrite/request-pipeline.md` | 核实后拆分 | 当前 Anthropic 合同进入 `docs/REQUEST_PIPELINE.md`；未来接线进入 `docs/agents/request-pipeline/spec.md`；原文进入 `docs/agents/request-pipeline/archive-2026-08-06/request-pipeline.md` | 明确协议适用范围，单列 OpenAI Responses 差异 |
| `docs/2604-rewrite/sanitize-pipeline.md` | 核实后拆分 | 当前合同进入 `docs/SANITIZE_PIPELINE.md`；未来需求进入 `docs/agents/anthropic-sanitize/spec.md`；原文进入 `docs/agents/anthropic-sanitize/archive-2026-08-06/sanitize-pipeline.md` | 对照 mandatory sanitizer 生产顺序、幂等测试与 hook 边界 |
| `docs/2604-rewrite/shutdown.md` | 拆分 | 当前运行合同进入 `docs/OPERATIONS.md`；未来阶段、reaper、deadline 与错误持久化进入 `docs/agents/operations/spec.md`；原文进入 `docs/agents/operations/archive-2026-08-06/shutdown.md` | 必须有 lifespan／signal 接线和执行探针，不能从类存在推导支持 |
| `docs/2604-rewrite/streaming-resilience.md` | 拆分并归档 | buffering 合同进入 `docs/STREAMING.md`；实现规格进入 `docs/agents/buffering/spec.md`；keepalive／delayed commit 进入 `docs/agents/streaming-resilience/spec.md`；TCP／H2 保活进入 `docs/agents/upstream-keepalive/spec.md`；原文进入 `docs/agents/streaming-resilience/archive-2026-08-06/streaming-resilience.md` | 不得提升 live anchor、delayed commit、keepalive、整响应 opt-in 或 transport 保活为当前能力 |
| `docs/2604-rewrite/streaming.md` | 重写并归档 | 新版 `docs/STREAMING.md`；逐协议缺口进入 `docs/agents/stream-consumers/spec.md`；原文进入 `docs/agents/buffering/archive-2026-08-06/streaming.md` | 以 block-level 合同取代零缓冲不变量；修复 accumulator、WS 路径、idle timeout、detector 与 translator 事实 |
| `docs/2604-rewrite/telemetry-observability.md` | 核实后拆分 | 当前合同进入 `docs/OBSERVABILITY.md`；未来设计进入 `docs/agents/observability/spec.md`；原文进入 `docs/agents/observability/archive-2026-08-06/telemetry-observability.md` | 从 setup、route、exporter、配置和真实探针生成支持矩阵 |
| `docs/2604-rewrite/thinking-pipeline.md` | 拆分 | 当前用户边界进入 `docs/ANTHROPIC_MESSAGES.md`；内部合同进入 `docs/agents/thinking/spec.md`；原文进入 `docs/agents/thinking/archive-2026-08-06/thinking-pipeline.md` | 删除热重载现在时，核实 protection／destack／quarantine 生产调用与持久化边界 |
| `docs/2604-rewrite/tokenization.md` | 核实后拆分 | 当前合同进入 `docs/TOKENIZATION.md`；完整规格保留在 `docs/agents/hooks-tokenization/spec.md`；原文进入 `docs/agents/hooks-tokenization/archive-2026-08-06/tokenization.md` | 对照 Anthropic／Gemini route、state store、管理 API 与 calibration 消费者 |
| `docs/2604-rewrite/tool-use.md` | 核实后拆分 | 当前合同进入 `docs/TOOL_USE.md`；未来能力进入 `docs/agents/anthropic-tool-use/spec.md`；原文进入 `docs/agents/anthropic-tool-use/archive-2026-08-06/tool-use.md` | 明确 client tools、tool search 和 server tools 的边界 |

### 5.2 依赖选型调研

这些文件是开发证据，不直接提升为活文档。选型结论只有在复核当前 lockfile／依赖元数据、生产 import 和维护状态后，才能由 `docs/ARCH.md` 引用；版本与外部事实必须标注核验日期。

| 旧文件 | 新位置 |
|---|---|
| `docs/2604-rewrite/lib-survey/260715-selections-review-01-claude.md` | `docs/agents/dependency-selection/archive-2026-08-06/260715-selections-review-01-claude.md` |
| `docs/2604-rewrite/lib-survey/HANDOVER.md` | `docs/agents/dependency-selection/archive-2026-08-06/HANDOVER.md` |
| `docs/2604-rewrite/lib-survey/SELECTIONS.md` | 核实后形成 `docs/agents/dependency-selection/research.md`；不复制第二份未标注快照 |
| `docs/2604-rewrite/lib-survey/_briefing.md` | `docs/agents/dependency-selection/archive-2026-08-06/_briefing.md` |
| `docs/2604-rewrite/lib-survey/domain1-llm-sdk.md` | `docs/agents/dependency-selection/research/domain1-llm-sdk.md` |
| `docs/2604-rewrite/lib-survey/domain2-reliability.md` | `docs/agents/dependency-selection/research/domain2-reliability.md` |
| `docs/2604-rewrite/lib-survey/domain3-streaming-sse-ws.md` | `docs/agents/dependency-selection/research/domain3-streaming-sse-ws.md` |
| `docs/2604-rewrite/lib-survey/domain4-storage-config.md` | `docs/agents/dependency-selection/research/domain4-storage-config.md` |
| `docs/2604-rewrite/lib-survey/domain5-observability.md` | `docs/agents/dependency-selection/research/domain5-observability.md` |
| `docs/2604-rewrite/lib-survey/domain6-hot-path-foundations.md` | `docs/agents/dependency-selection/research/domain6-hot-path-foundations.md` |

### 5.3 已完成计划、kick-off、handover 与评审

| 旧文件 | 新位置 | 状态说明 |
|---|---|---|
| `docs/2604-rewrite/plan/260715-implementation-plan-review-01-claude.md` | `docs/agents/2604-rewrite/archive-2026-08-06/260715-implementation-plan-review-01-claude.md` | 完成态整体计划评审 |
| `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md` | `docs/agents/hooks-tokenization/archive-2026-08-06/implementation-plan.md` | 已实施计划，不再作为待办 |
| `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_KICKOFF.md` | `docs/agents/hooks-tokenization/archive-2026-08-06/kickoff.md` | 已消费 kick-off |
| `docs/2604-rewrite/plan/IMPLEMENTATION_HANDOVER.md` | `docs/agents/2604-rewrite/archive-2026-08-06/IMPLEMENTATION_HANDOVER.md` | 历史 handover，顶部链接现行入口 |
| `docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md` | `docs/agents/2604-rewrite/archive-2026-08-06/IMPLEMENTATION_PLAN.md` | 完成态大计划，不再作为当前状态真相源 |
| `docs/2604-rewrite/plan/PHASE_0_KICKOFF.md` | `docs/agents/2604-rewrite/archive-2026-08-06/PHASE_0_KICKOFF.md` | 已消费 kick-off |

### 5.4 42 项提炼阶段、最终移动所有权与精确源 pathspec

本表与第 5.1～5.3 节共同构成 canonical mapping。`extract phases` 表示可从仍在旧位置的源提炼内容的阶段；`final move phase` 是唯一有权移动该源的阶段。`source → canonical destination` 两端都是提交时必须使用的精确 literal pathspec，不得以目录 glob、`git add docs` 或“对应旧内容”等自判范围替代。阶段 0 将本表逐项写入机器可读 manifest，并为每个阶段生成只含 literal path 的 `phase-<n>-pathspec.txt`；共享产物的精确路径采用第 5.1～5.3 节“新位置／产物”列，manifest 不得新增表外目标。阶段 1 的 banner pathspec 另由 manifest 中 `final move phase > 1` 的源精确展开，仍然不得用 glob。

| 源 | extract phases | final move phase | source → canonical destination |
|---|---:|---:|---|
| `docs/2604-rewrite/260403-docs-review-01-claude.md` | 3 | 3 | `docs/2604-rewrite/260403-docs-review-01-claude.md` → `docs/agents/architecture/archive-2026-08-06/260403-docs-review-01-claude.md` |
| `docs/2604-rewrite/BACKLOG.md` | 9 | 9 | `docs/2604-rewrite/BACKLOG.md` → `docs/agents/product-roadmap/archive-2026-08-06/BACKLOG.md` |
| `docs/2604-rewrite/DESIGN.md` | 3 | 3 | `docs/2604-rewrite/DESIGN.md` → `docs/agents/architecture/archive-2026-08-06/DESIGN.md` |
| `docs/2604-rewrite/ROADMAP.md` | 9 | 9 | `docs/2604-rewrite/ROADMAP.md` → `docs/agents/product-roadmap/archive-2026-08-06/ROADMAP.md` |
| `docs/2604-rewrite/anthropic-compat.md` | 1, 5 | 5 | `docs/2604-rewrite/anthropic-compat.md` → `docs/agents/anthropic-messages/archive-2026-08-06/anthropic-compat.md` |
| `docs/2604-rewrite/approval-system.md` | 7 | 7 | `docs/2604-rewrite/approval-system.md` → `docs/agents/approval/archive-2026-08-06/approval-system.md` |
| `docs/2604-rewrite/authentication.md` | 5 | 5 | `docs/2604-rewrite/authentication.md` → `docs/agents/authentication/archive-2026-08-06/authentication.md` |
| `docs/2604-rewrite/config-system.md` | 3 | 3 | `docs/2604-rewrite/config-system.md` → `docs/agents/configuration/archive-2026-08-06/config-system.md` |
| `docs/2604-rewrite/data-models.md` | 3 | 3 | `docs/2604-rewrite/data-models.md` → `docs/agents/data-models/archive-2026-08-06/data-models.md` |
| `docs/2604-rewrite/feature-negotiation.md` | 1, 5 | 5 | `docs/2604-rewrite/feature-negotiation.md` → `docs/agents/anthropic-feature-negotiation/archive-2026-08-06/feature-negotiation.md` |
| `docs/2604-rewrite/header-forwarding.md` | 1, 5 | 5 | `docs/2604-rewrite/header-forwarding.md` → `docs/agents/header-forwarding/archive-2026-08-06/header-forwarding.md` |
| `docs/2604-rewrite/history-system.md` | 6 | 6 | `docs/2604-rewrite/history-system.md` → `docs/agents/history-durability/archive-2026-08-06/history-system.md` |
| `docs/2604-rewrite/hooks-system.md` | 4 | 4 | `docs/2604-rewrite/hooks-system.md` → `docs/agents/hooks-tokenization/archive-2026-08-06/hooks-system.md` |
| `docs/2604-rewrite/hooks-tokenization-spec.md` | 4 | 4 | `docs/2604-rewrite/hooks-tokenization-spec.md` → `docs/agents/hooks-tokenization/spec.md` |
| `docs/2604-rewrite/model-resolution.md` | 5 | 5 | `docs/2604-rewrite/model-resolution.md` → `docs/agents/model-resolution/archive-2026-08-06/model-resolution.md` |
| `docs/2604-rewrite/multi-protocol.md` | 8 | 8 | `docs/2604-rewrite/multi-protocol.md` → `docs/agents/multi-protocol/archive-2026-08-06/multi-protocol.md` |
| `docs/2604-rewrite/project-structure.md` | 3 | 3 | `docs/2604-rewrite/project-structure.md` → `docs/agents/architecture/archive-2026-08-06/project-structure.md` |
| `docs/2604-rewrite/request-pipeline.md` | 4 | 4 | `docs/2604-rewrite/request-pipeline.md` → `docs/agents/request-pipeline/archive-2026-08-06/request-pipeline.md` |
| `docs/2604-rewrite/sanitize-pipeline.md` | 4 | 4 | `docs/2604-rewrite/sanitize-pipeline.md` → `docs/agents/anthropic-sanitize/archive-2026-08-06/sanitize-pipeline.md` |
| `docs/2604-rewrite/shutdown.md` | 7 | 7 | `docs/2604-rewrite/shutdown.md` → `docs/agents/operations/archive-2026-08-06/shutdown.md` |
| `docs/2604-rewrite/streaming-resilience.md` | 1 | 1 | `docs/2604-rewrite/streaming-resilience.md` → `docs/agents/streaming-resilience/archive-2026-08-06/streaming-resilience.md` |
| `docs/2604-rewrite/streaming.md` | 1 | 1 | `docs/2604-rewrite/streaming.md` → `docs/agents/buffering/archive-2026-08-06/streaming.md` |
| `docs/2604-rewrite/telemetry-observability.md` | 7 | 7 | `docs/2604-rewrite/telemetry-observability.md` → `docs/agents/observability/archive-2026-08-06/telemetry-observability.md` |
| `docs/2604-rewrite/thinking-pipeline.md` | 1, 5 | 5 | `docs/2604-rewrite/thinking-pipeline.md` → `docs/agents/thinking/archive-2026-08-06/thinking-pipeline.md` |
| `docs/2604-rewrite/tokenization.md` | 4 | 4 | `docs/2604-rewrite/tokenization.md` → `docs/agents/hooks-tokenization/archive-2026-08-06/tokenization.md` |
| `docs/2604-rewrite/tool-use.md` | 1, 4 | 4 | `docs/2604-rewrite/tool-use.md` → `docs/agents/anthropic-tool-use/archive-2026-08-06/tool-use.md` |
| `docs/2604-rewrite/lib-survey/260715-selections-review-01-claude.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/260715-selections-review-01-claude.md` → `docs/agents/dependency-selection/archive-2026-08-06/260715-selections-review-01-claude.md` |
| `docs/2604-rewrite/lib-survey/HANDOVER.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/HANDOVER.md` → `docs/agents/dependency-selection/archive-2026-08-06/HANDOVER.md` |
| `docs/2604-rewrite/lib-survey/SELECTIONS.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/SELECTIONS.md` → `docs/agents/dependency-selection/research.md` |
| `docs/2604-rewrite/lib-survey/_briefing.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/_briefing.md` → `docs/agents/dependency-selection/archive-2026-08-06/_briefing.md` |
| `docs/2604-rewrite/lib-survey/domain1-llm-sdk.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/domain1-llm-sdk.md` → `docs/agents/dependency-selection/research/domain1-llm-sdk.md` |
| `docs/2604-rewrite/lib-survey/domain2-reliability.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/domain2-reliability.md` → `docs/agents/dependency-selection/research/domain2-reliability.md` |
| `docs/2604-rewrite/lib-survey/domain3-streaming-sse-ws.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/domain3-streaming-sse-ws.md` → `docs/agents/dependency-selection/research/domain3-streaming-sse-ws.md` |
| `docs/2604-rewrite/lib-survey/domain4-storage-config.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/domain4-storage-config.md` → `docs/agents/dependency-selection/research/domain4-storage-config.md` |
| `docs/2604-rewrite/lib-survey/domain5-observability.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/domain5-observability.md` → `docs/agents/dependency-selection/research/domain5-observability.md` |
| `docs/2604-rewrite/lib-survey/domain6-hot-path-foundations.md` | 10 | 10 | `docs/2604-rewrite/lib-survey/domain6-hot-path-foundations.md` → `docs/agents/dependency-selection/research/domain6-hot-path-foundations.md` |
| `docs/2604-rewrite/plan/260715-implementation-plan-review-01-claude.md` | 10 | 10 | `docs/2604-rewrite/plan/260715-implementation-plan-review-01-claude.md` → `docs/agents/2604-rewrite/archive-2026-08-06/260715-implementation-plan-review-01-claude.md` |
| `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md` | 4 | 4 | `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_IMPLEMENTATION_PLAN.md` → `docs/agents/hooks-tokenization/archive-2026-08-06/implementation-plan.md` |
| `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_KICKOFF.md` | 4 | 4 | `docs/2604-rewrite/plan/HOOKS_TOKENIZATION_KICKOFF.md` → `docs/agents/hooks-tokenization/archive-2026-08-06/kickoff.md` |
| `docs/2604-rewrite/plan/IMPLEMENTATION_HANDOVER.md` | 10 | 10 | `docs/2604-rewrite/plan/IMPLEMENTATION_HANDOVER.md` → `docs/agents/2604-rewrite/archive-2026-08-06/IMPLEMENTATION_HANDOVER.md` |
| `docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md` | 10 | 10 | `docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md` → `docs/agents/2604-rewrite/archive-2026-08-06/IMPLEMENTATION_PLAN.md` |
| `docs/2604-rewrite/plan/PHASE_0_KICKOFF.md` | 10 | 10 | `docs/2604-rewrite/plan/PHASE_0_KICKOFF.md` → `docs/agents/2604-rewrite/archive-2026-08-06/PHASE_0_KICKOFF.md` |

阶段 0 的 manifest checker 必须机械证明：恰有 42 行；源集合与两种枚举结果双向相等；每个源只出现一次；每项 `final move phase` 恰有一个整数；每个 canonical destination 唯一；每个 `extract phase ≤ final move phase`；逐阶段 pathspec 展开后没有目录 glob，且任一源移动只出现在其唯一 final owner 阶段。manifest 还必须把第 5.1～5.3 节每个“新位置／产物”规范化为 `required_outputs`，逐项记录精确输出路径、唯一 `producer_phase`、`source_extract_inputs`、结构化只读 `normative_inputs` 和 `historical_inputs`；checker 必须证明每个输出恰有一个 producer、每条 source → output 提炼边不晚于该输入源的 `final_move_phase`，并且输出 literal path 出现在 producer 阶段 pathspec。每个 `normative_inputs` 项必须记录 `path`、规范角色、必需状态、已接受内容 `sha256`、被绑定输入及 policy reconciliation evidence；对 bridge Acceptance 还必须记录其绑定的 Spec SHA-256 与 `POLICY-MANIFEST-v1` 七域完成状态。`normative_inputs` 不转移源文件 ownership，也不进入阶段 staged path；它冻结的是已接受内容身份与优先级，不是可随路径内容漂移的文件名。凡 `normative_inputs` 与 `historical_inputs` 冲突，输出必须服从前者；凡执行时内容身份、状态或绑定漂移，checker 必须停止而不是自动采纳新内容。非规范 Architecture 不得进入行为 `normative_inputs`。共享活文档可在计划已明确列出的后续阶段继续更新，因此 producer 唯一性不得被错误实现为“该路径永远只能出现在一个阶段”；本轮三份阶段 1 spec 没有后续阶段更新，其唯一 `final_owner_phase = 1` 由阶段 1 表另行冻结并要求只进入阶段 1 pathspec。完整分配正 fixture 必须为绿；漏掉一个派生产物、同一路径分配给两个 producer、在输入源 final move 后才首次生产，或遗漏 producer 阶段 pathspec 均必须为红。阶段 4／5 等后继阶段只能从 manifest 指定的仍存旧路径或 canonical destination 取材，不能自行猜测位置。

## 6. 统一切片执行协议

每个阶段都必须遵守以下协议；它是各阶段独立提交、可暂停和不污染产品主线的基础。

### 6.1 Shell 与 HEAD gate

每次 shell 调用都在同一次调用内：

1. `cd` 到 `/home/xp/src/ghc-api-proxy-py` 并验证 `pwd -P` 精确相等。
2. 打印 `git rev-parse HEAD` 和 `git status --short`。
3. 第一次执行验证规划 HEAD 是当前 HEAD 的祖先；后续记录阶段开始 HEAD，不错误要求 HEAD 永远等于规划基线。
4. 对读取、验证、提交分别使用仓库绝对根或同调用目录绑定，不依赖先前 shell 的 cwd。

### 6.2 TDD 等价流程

文档迁移不能用产品代码红灯直接证明正文正确，因此每个切片采用可复现的“oracle 先行”流程：

1. **先固定 oracle**：从 route、settings、schema、lifespan、生产调用图和现有测试生成该主题的期望集合或行为矩阵；跨阶段共用 oracle 必须落实为 `docs/agents/documentation-restructure/verification/` 中的已提交 checker、fixture、manifest 或明确版本化输入，不能只存在系统临时目录。
2. **双向控制**：正确 fixture 必须为绿；注入目标缺陷的 fixture 必须为红，并确认失败来自目标检查而非旁路错误。会阻断阶段提交的 gate 同时要有正确样本和错误样本，避免 false-red 与 false-green；断链、不存在 route、未消费字段、临时目录引用、重复正文和错误 fragment 分别有独立缺陷注入。
3. **先观察旧文档失败**：记录旧文档在该 oracle 下的事实冲突，避免检查器从一开始就是假绿。
4. **迁移与修真**：只处理本切片文件，当前实现和已决目标分栏。
5. **复跑 oracle**：同一检查转绿，再运行 Markdown 链接检查、`git diff --check` 和主题相关项目测试。
6. **合并态复验**：阶段 11 重新验证跨文档接缝，避免每片单独为绿而整体矛盾。

### 6.3 提交边界

- 每阶段只提交该阶段列出的精确 pathspec，禁止使用 `git add docs` 等宽范围命令。
- 精确 pathspec 以阶段 0B 已提交的 `phase-<n>-pathspec.txt` 为机械真相源，使用 `git add --pathspec-from-file=<file>` 或逐字列出同一集合；提交前 checker 必须确认 staged paths 与该阶段允许集合精确相等。阶段 1 的 banner 集合和阶段 10 的剩余移动集合也必须由 manifest 展开，不能人工临场选择。
- 提交前单独运行并确认 `git diff --check`、`git diff --name-only`、链接检查和主题 oracle；检查与 commit 之间使用能传播失败的 gate，不以无条件换行串联。
- 明确排除 `docs/tmp/**`、仓库根部既有 `verification/**` 和任何阶段开始前脏项。阶段 0A staged paths 必须精确等于固定 `protocol-marker.json` 加无 glob、含自身路径的 `bootstrap-kernel/bootstrap-assets.txt` 所列 checker／schema／fixtures／fixture hash manifest／bootstrap test instructions 集合，且不得包含 inventory、ledger、manifest 或 phase pathspec；阶段 0B staged paths 必须精确等于由已提交 0A checker 生成的 manifest／identity／phase pathspec／generation 0 数据集合。后续 checker／fixture 语义修复不得修改 marker 或重跑 0A，只能另起普通 versioned migration generation 与独立验证资产提交，不得与主题迁移提交混合；该修复的评审报告按 verdict／action impacts 进入同 ordinal revision 或下一 generation gate。
- 提交后打印新 HEAD 和 status，记录验证命令、范围与结果。
- 每阶段对应一个或少量语义完整 Conventional Commits。阶段 0 固定拆为 0A 与 0B 两个提交；其他阶段若需要多个提交，必须按“活文档真相”“开发规格归位”“历史归档”形成可独立 revert 的边界，不能按编辑时间随意拆分。
- 每个旧源文件只移动一次：其可供后续阶段提炼的内容全部落地后，只由 manifest 指定的唯一 `final_move_phase` 移入第 5.4 节 canonical destination。跨多个阶段的源文件保留在旧目录直到最后一项内容完成；final owner 在同一移动提交内把迁移期 banner 替换为永久 archive／provenance 头。阶段 10 只移动自身 `final_move_phase = 10` 的精确集合，不得兜底接管任何前序遗漏，也不得重复归档。

### 6.4 风险与回滚

阶段失败时不提交。已提交后发现问题，优先 revert 该阶段的独立提交；不得用整树 `restore` 覆盖共享工作树。存在并行改动时，只逆转已冻结且归属明确的精确 patch。每阶段开始前的 status 与 diff 是归属证据，不是删除他人改动的授权。

### 6.5 依赖动作前的报告归纳 gate

阶段 0A 只走第 2.5 节 `bootstrap_kernel_commit`：先机械证明父 HEAD 中 marker／kernel／latest／closed generation 全部不存在，再验证固定 staged allowlist、kernel identity、repo 外冻结 fixture 与独立回执；不调用尚未存在的 generation checker，也不得靠“首次运行”自评跳过任何检查。阶段 0B 在已提交且由不可变 marker 绑定的 0A kernel 上创建 generation `<0,0>` cut-off，生成 inventory／identity／distillation ledger，取得精确绑定 closure payload 与 action 的 PASS certificate 后关闭 generation 0，并让其唯一授权 `action_id` 精确绑定阶段 0B `docs_commit` 的 staged payload manifest；该 manifest 排除本代 certificate、closure 与 index，closure 单向绑定 certificate identity 与 payload manifest hash，index 只绑定 closure hash。

阶段 0B 之后，每次准备执行 docs 提交、阶段推进、产品回放、archive／worktree 清理或用户裁决，都必须以动作类型、受影响 topic 和 subject identity 请求一个新 ordinal。checker 在扫描开始时冻结该 revision 的报告路径＋content hash cut-off，从该冻结集合生成 ledger；它不得把 cut-off 后报告正文回写本 revision。只有本代全部 action-relevant 条目为 `covered`、正式落点与 anchor 可解析、inventory／identity／ledger／closure payload hashes 一致，且独立 closure review 为 PASS、certificate 精确绑定 subject／payload／action／observed post-cut set、blocker／major 为 0、`unresolved_action_impacts=[]` 时才能 closed。动作执行前必须重扫 post-cut report path＋hash、verdict 与 impacts；blocker／major、当前 action／topic impact、报告 hash 漂移、certificate mismatch 或 observed-set 外新增报告都会立即使授权 stale。授权未消费时先关闭同 ordinal 新 revision；不符合修订条件时关闭下一 generation。任何情况下都不能先消费旧授权。`partial`／`pending` 永不通行；对 ledger、checker、closure 或其评审报告适用同一规则，不存在人工豁免。

## 7. 渐进实施阶段

### 阶段 0：以 0A／0B 两个提交冻结验证协议与 generation 0

**目标**：不移动源文件，先用不依赖 ledger 的机械 bootstrap 提交 checker，再由该已提交 checker 生成并关闭 generation 0，建立可跨暂停／恢复边界重复执行的文件 disposition、事实 oracle、链接／provenance gate 和工作树保护基线。

**前置依赖**：无。首次执行确认规划 HEAD 是实际 HEAD 的祖先。

**动作**：

- 用两种不同原理枚举 `docs/2604-rewrite/**/*.md`，冻结集合并与第 5 节双向精确对账。
- 记录开始 HEAD、status、既有脏项和项目现有 Markdown／lint／test 命令。
- **阶段 0A——一次性提交 protocol marker 与 bootstrap kernel**：新建固定 `docs/agents/documentation-restructure/verification/protocol-marker.json`，并在固定 `verification/bootstrap-kernel/` namespace 内新建 README、Markdown link checker、源 provenance／重复 checker、规范输入 identity checker、report-distillation generation／matrix checker、状态词 checker、route/settings/schema 探针、机器可读 schema、`fixtures/`、fixture hash manifest、bootstrap test instructions 与 `bootstrap-assets.txt`。checker 与 fixture 文件名可按项目 Python 约定细分，但 `bootstrap-assets.txt` 必须用 literal paths 完整列出 marker 之外的 0A kernel 资产及自身、禁止 glob；`bootstrap_kernel_commit` 必须先检查父 HEAD 无 marker／kernel／latest／closed generation，再证明 staged paths 精确等于 marker＋该清单、marker 中 canonical kernel identity 与 staged blob identities 相等。0A 不能包含任何真实仓库 inventory、ledger、manifest 或 phase pathspec。
- 在运行 0A checker 前，把正样本与每类目标 mutant 的 fixture bytes、路径和 SHA-256 冻结到 repo 外只读目录；bootstrap harness 先验证 repo 外 hash manifest，再让待提交 checker 读取该目录。正样本必须为绿；错误链接／fragment、额外正文副本、producer 冲突、规范输入漂移、报告漏登记、`pending`／`partial`、closure hash 错误等各自 mutant 必须因目标机制为红。不得在观察结果后同步修改 checker 与 repo 外 fixture 来“对齐”；fixture 需要变更时重新冻结新身份并从头运行整组控制。
- marker＋kernel staged paths 与固定 allowlist 精确相等、repo 外双向控制全绿、`git diff --check` 通过后，对最终候选 bytes 做独立评审；只有回执精确绑定 marker blob OID、kernel subtree tree OID、canonical blob identity、候选 repository tree identity且达到 0 blocker／0 major，`bootstrap_kernel_commit` 才能形成独立提交。该回执按正常命名写入 `docs/tmp/`，其路径＋hash 由 bootstrap harness 记录并供 0B generation 0 cut-off 纳入；0A 不要求尚不存在的 ledger 来登记回执，但也不得由执行者自称“已评审”或排除该报告。提交后立即以新 HEAD 为父分别重放原 bytes 与变更 kernel bytes 的 `bootstrap_kernel_commit`，两者都必须确定性返回 `40/bootstrap_marker_exists` 且不产生新 commit。
- **阶段 0B——生成并关闭 generation 0**：只使用已提交 0A checker，不从 0B 工作树加载候选 checker。`manifest.json` 为 42 项逐一记录 `source`、原始字节 `source_sha256`、`source_body_sha256`、`extract_phases`、唯一 `final_move_phase`、`canonical_destination`、`destination_kind`、`required_outputs` 与逐阶段 exact pathspec。每个 `required_outputs` 项记录精确输出路径、唯一 `producer_phase`、精确 `source_extract_inputs`、结构化只读 `normative_inputs` 和 `historical_inputs`；第 5.1～5.3 节列出的所有新产物必须进入该集合，不能只登记 42 个源及其 canonical destination。本轮阶段 1 表冻结的三份 spec 还必须各自记录唯一 `final_owner_phase = 1`。阶段 1 的 `docs/agents/buffering/spec.md` 及下表中涉及 bridge buffering／retry／SSE consumer 的派生 specs，必须把第 2.3 节绑定的 Spec `FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` 与 Acceptance `FINALIZED_ACCEPTANCE_ORACLE@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4` 记录为只读规范输入，并记录 Acceptance 绑定同一 Spec SHA-256 与七域 policy 对账完成；把 `docs/2604-rewrite/streaming.md` 与 `streaming-resilience.md` 记录为历史输入。bridge Architecture 只可登记为非规范参考，不得进入行为 `normative_inputs`。规范输入不得被加入阶段 1 staged path，也不得因其不属于 42 项迁移源而漏记。42 项迁移源 hash 只以规划基线原始内容为准；阶段 1 banner 改变工作树内容后，另记 `bannered_sha256`，不得覆盖原 hash。受管 header 的起止标记与剥离算法也必须在 checker 和 fixtures 中冻结，不能把任意首段误当 header 删除。
- 0B 在一次 gated 扫描开始事件中冻结 generation `<0,0>` 的 `inventory.json`，覆盖当时全部 `docs/tmp/*.md` 的 sorted path＋content hash；生成 `identity.json`，绑定不可变 marker blob、kernel version／identity、0A checker commit／content hash、schema version、仓库 HEAD、bridge 规范输入身份和空前代 closure；生成 `distillation-ledger.json`，逐报告登记正式落点、coverage、owner、verdict、受影响 action／topic、unresolved impacts 和失效条件；再生成排除本代 machine-readable certificate、closure／index 的 staged payload path＋blob SHA-256 manifest与 canonical closure payload。独立 closure review report 冻结后，checker 生成精确 PASS certificate；0A checker 再生成单向绑定 certificate identity 的 `closure.json`，index 只在 closure 完成后记录其 hash。generation 0 唯一授权动作必须精确绑定该 payload manifest，且包含 certificate／closure／index 的完整 staged path 仍必须等于 0B 允许集合。`docs/tmp/260807-tmp-distillation-matrix.md` 只帮助核对初始字段，不能成为 schema 或 current 状态源。
- 对整个目标 `docs/**` 建 provenance gate：精确正文 hash 扫描先只剥离 checker 明确认识的受管迁移／归档头。`destination_kind = retained_exact` 时，`source_body_sha256` 必须只在 manifest 指定的 canonical destination 出现一次；`destination_kind = transformed_asset` 时，canonical destination 必须携带源路径与原始 hash 的 provenance，旧正文完整 hash 在目标树中的期望基数为零。任何种类都不允许在其他位置出现额外完整副本。近似正文块扫描只产生候选，逐条记录“合法提炼／带 provenance 的引用／意外副本” disposition，不自动删除。合法提炼必须标明源路径、源 hash 和现行入口，不能伪装成第二份当前真相。
- 冻结链接 gate 的被测边界与 renderer。canonical renderer 是 GitHub 仓库 Web UI 的 GitHub Flavored Markdown：分别验证相对目标文件、Markdown heading fragment 和 GitHub source line fragment；heading ID 按 GitHub 语义处理 Unicode、标点和重复标题后缀，line fragment 只接受 `#L<n>` 或 `#L<n>-L<m>` 且行号／范围在目标文件内。checker 使用能解析 Markdown AST 的成熟实现，并以已冻结 fixture 校准 renderer 语义，禁止仅用正则抽链接后宣称完整支持。
- 为链接 gate 提交三组以上双向 fixtures：移动后已按新基准 rebasing 的相对链接为绿、仍用旧相对路径为红；合法 heading fragment 与标题改名后的新 fragment 为绿、旧 fragment 为红；合法 Unicode heading 和合法重复标题 suffix 为绿、错误 slug 为红；合法 archive 链接和范围内 GitHub line fragment 为绿、畸形／越界 line fragment 为红。
- 为 provenance gate 提交双向 fixtures：添加受管 archive header 后正文 hash 仍只在 canonical destination 命中一次为绿；`transformed_asset` 有 provenance 且无完整旧正文为绿；“source mapping 正确但正文被额外复制一份”必须红；伪造相似首段但不含受管 header 标记时不得被剥离；近似但已明确 provenance／disposition 的正确样本不得被误报为阻断性 false-red。
- 为派生产物 ownership 与输入优先级 gate 提交双向 fixtures：每个 required output 都有唯一 producer、完整 source extract inputs、规范输入与历史输入，且输出 literal path 进入 producer 阶段时为绿；漏登记一个输出、重复 producer、producer 晚于输入源 final move，或遗漏 producer 阶段 pathspec 时分别为红。阶段 1 buffering fixture 必须证明 bridge 栏服从 current bridge Spec／Acceptance，旧 2604 文档中冲突的零缓冲、整响应 opt-in、块级延后或其他旧方案只能作为带 provenance 的历史素材；故意让历史输入覆盖 Anthropic content block、retry frontier、memory-only／no spill／无 16 MiB 特例、SSE delayed-start、cancel 或 History 时点中的任一冻结值时必须为红。另为本轮三份阶段 1 spec 验证唯一 final owner，并以“任一路径进入阶段 2～11 pathspec”为反 fixture。该 gate 必须覆盖第 5.1～5.3 节全部产物的 producer，不得只为本轮发现的三个 streaming spec 写 producer 特例；也不得把计划显式要求的共享活文档后续更新误报为重复 producer。
- 为规范输入 identity gate 提交双向 fixtures：第 2.3 节 current Spec／Acceptance 内容 hash、状态、Acceptance → Spec 绑定和七域对账身份全部一致时为绿；Spec bytes 改变但 Acceptance 未重做对账、Acceptance bytes 漂移、任一状态非 finalized、Acceptance 内嵌 Spec hash 不一致、或只刷新 hash 而缺少新独立复评／policy reconciliation evidence 时分别为红。Architecture 缺席或内容变化不得改变行为 expected；把非规范 Architecture 填入行为 `normative_inputs` 或让它覆盖 Spec／Acceptance 时必须为红。阶段 0B 建 manifest 与阶段 1 开始前都运行同一 identity gate。
- 为 report-distillation generation／matrix gate 提交双向 fixtures：bootstrap 正样本只能在父 HEAD 无 marker／kernel／latest／closed generation、没有 repo ledger、staged allowlist 精确且 repo 外 fixture 身份正确时通过；首次 0A 提交后以原 bytes 或换 bytes 重跑均必须返回 `40/bootstrap_marker_exists`，marker 缺失但 kernel、latest 或 closed generation 分别存在时必须返回 41、42、43，staged path 缺失／越界、kernel identity 漂移、fixture hash 漂移和独立回执不合格分别返回 44、45、46、47，且都不得产生 commit。generation `<N,R>` 的冻结报告及全部 load-bearing 结论均有正式落点且为 `covered`，closure review verdict 为 PASS、certificate 精确绑定 subject／payload／action／observed set且 unresolved impacts 为空时，精确绑定的 `docs_commit`、`phase_advance`、`product_replay`、`archive_cleanup`、`worktree_cleanup` 或 `user_ruling` 动作为绿；相关报告只登记 `pending`／`partial` 便 close、报告在 cut-off 时已存在但漏登记、`covered` 仍缺正式 anchor、部分覆盖遗漏剩余项、正式落点仍指向 `docs/tmp/**`、action identity 不匹配、非 latest non-stale closed revision、closure／certificate／report hash 漂移时分别为红。历史报告已有完整正式落点时应为绿，无关 topic 且 certificate 证明无 unresolved impact 的 covered 结论不得造成 false-red。
- 增加 post-cut verdict／impact 与 self-reference 终止控制：先为 generation `<N,0>` 形成 closure payload；post-cut closure review 为 PASS、0 blocker／0 major、observed report set 精确且 `unresolved_action_impacts=[]` 时，certificate 纳入 closure，报告正文只进入 `N+1`，精确绑定的当前动作仍为绿，这是 narrow carry-forward 正控制。分别注入 blocker、major、任意 verdict 但影响当前 action／topic、伪造 subject generation、遗漏 impact、certificate observed-set 不完整、certificate 或任一报告 hash 漂移，当前 revision 与动作必须立即 stale；未消费动作必须先把报告归纳并关闭 `<N,1>`，或按协议关闭 `N+1`，旧 `<N,0>` 不得先执行。随后尝试在后继代漏登记 PASS receipt、保留 `pending`／`partial` 或复用已消费 ordinal 授权下一动作，必须分别为红；把 carry-forward 报告归纳为 `covered`、关闭下一 ordinal 并绑定下一动作后才重新为绿。另对 generation 冻结集合内报告改 hash，该 revision 必须为红，防止 cut-off 被误实现成忽略身份漂移。
- 对 route/settings/schema 与状态词 checker 同样做正反控制。执行输出写系统临时目录；仓库只提交可复现资产。

**验收**：0A 仅在父 HEAD 不存在 marker／kernel／latest／closed generation 且不存在 repo ledger时，凭固定 staged allowlist 与 repo 外只读冻结 fixture 完成正反控制；不可变 marker 精确绑定 kernel tree／blob identity，独立复评回执绑定 marker／kernel／候选 tree且为 0 blocker／0 major。成功后原 bytes 与换 bytes 重跑均以固定失败码拒绝且不产生 commit；不存在 skip／自评 bootstrap 分支，后续 kernel 升级只能走普通 versioned migration generation。0B 只使用已提交且由 marker 绑定的 0A checker。冻结集合与第 5 节一一对应；42 项 source ownership／hash／destination 与第 5.1～5.3 节全部派生产物的 producer／source inputs／producer-stage pathspec 均通过机械不变量，本轮三份阶段 1 spec 另通过唯一 final owner 检查；bridge 规范输入的内容身份、finalized 状态、Acceptance → Spec 绑定与七域对账身份在 generation 0 全绿；generation 0 cut-off 时全部 `docs/tmp/*.md` 均已进入 inventory 与 ledger，相关结论均为 `covered`，closure 精确授权排除 certificate／closure／index 的 0B staged payload manifest，PASS certificate 精确绑定 closure payload、action 与 observed post-cut set且 unresolved impacts 为空，closure 单向绑定 certificate identity，index 只绑定 closure hash，包含三个控制面文件的完整 staged path 仍精确等于 0B 允许集合。post-cut PASS／无 impact 报告可窄化 carry forward；blocker／major、当前 action／topic impact、subject／certificate／report hash 漂移立即使旧授权 stale，必须先关闭同 ordinal revision 或下一 generation，不能先执行旧动作。所有 gate 完成双向控制并确认目标失败机制。从一个全新临时工作目录仅凭 0A＋0B 已提交资产即可重跑，不依赖 `docs/tmp/260807-tmp-distillation-matrix.md` 继续存在；仓库无产品改动，`docs/tmp/**` 无 staged path。

**独立提交**：0A 为 `test(docs): add documentation verification bootstrap`，只提交固定 protocol marker 与 bootstrap-kernel allowlist 中的 checker／schema／fixtures／fixture hash manifest／bootstrap test instructions；0B 为 `test(docs): freeze documentation migration generation zero`，只提交由 marker 绑定的 0A checker 生成并验证的 manifest／规范 identity／phase pathspec／generation 0 inventory／identity／distillation ledger／closure／certificate identity／index。两者都必须在任何 banner、活文档或旧源移动之前落地，不能互相 squash，也不能与阶段 1 合并。

**风险／回滚**：主要风险是 checker 自己 false-green／false-red、重复 bootstrap 重建信任根，或 generation closure 被自指报告无限追赶。父 HEAD marker／kernel／latest gate与固定失败码封死重复 0A；repo 外冻结 fixture 校准原始 kernel，后续升级走 versioned migration generation；closure payload／certificate 分层避免自哈希，ordinal revision 只在动作未消费时修订，PASS／无 impact 才窄化 carry forward，其余报告先 stale 再关闭修订，兼顾终止性与当前动作安全。0A、0B 可按依赖逆序独立 revert；revert 任一提交后不得继续阶段 1，因为后续阶段以两者共同形成的验证基线为 gate。若 marker 已在任何后代 HEAD 出现，不得通过 revert 后重跑 0A 来“修复”，必须走普通 versioned migration generation。

### 阶段 1：Anthropic Messages 与 buffering 合同

**目标**：先建立最高优先级产品线的最小可信文档面，并消除旧文档中“零缓冲默认、块级延后”的 blocker。

**涉及文件**：

- 新建 `docs/README.md`、`docs/ANTHROPIC_MESSAGES.md`、`docs/STREAMING.md`。
- 新建 `docs/agents/buffering/spec.md`、`docs/agents/anthropic-messages/spec.md`。
- 新建 `docs/agents/streaming-resilience/spec.md`、`docs/agents/upstream-keepalive/spec.md`、`docs/agents/stream-consumers/spec.md`。三者的 producer、输入、stage pathspec 与唯一 final owner 冻结如下，不得由执行者临场推断：

| 阶段 1 派生产物 | producer phase | source extract inputs | stage pathspec | 唯一 final owner |
|---|---:|---|---|---:|
| `docs/agents/streaming-resilience/spec.md` | 1 | `docs/2604-rewrite/streaming-resilience.md` | `docs/agents/streaming-resilience/spec.md` | 1 |
| `docs/agents/upstream-keepalive/spec.md` | 1 | `docs/2604-rewrite/streaming-resilience.md` | `docs/agents/upstream-keepalive/spec.md` | 1 |
| `docs/agents/stream-consumers/spec.md` | 1 | `docs/2604-rewrite/streaming.md` | `docs/agents/stream-consumers/spec.md` | 1 |

上述三条必须原样进入阶段 0 manifest 的 `required_outputs` 和 `phase-1-pathspec.txt`。它们必须在各自输入源由阶段 1 最终移动前完成提炼；后续阶段可更新相关活文档或消费这些 specs，但不得重新取得这三个文件的生产／最终所有权，也不得把同一路径加入其他阶段 pathspec。
- 阶段 1 的 buffering 规范输入与历史素材按下表冻结。`source extract inputs` 只说明历史材料的 provenance／移动来源，不赋予其产品规范权威；bridge Spec／Acceptance 必须是第 2.3 节绑定的已接受内容版本，作为只读输入不改变其 ownership，也不进入本阶段 pathspec。

| 阶段 1 输出／分栏 | 规范输入 | 历史素材 | 强制处置 |
|---|---|---|---|
| `docs/agents/buffering/spec.md` 的 Anthropic Responses bridge 栏 | 第 2.3 节绑定的 `FINALIZED` Spec 与 `FINALIZED_ACCEPTANCE_ORACLE` Acceptance 内容对 | `docs/2604-rewrite/streaming.md`、`docs/2604-rewrite/streaming-resilience.md` | 原样承接 bridge 已冻结合同与 required gates；历史冲突只记录取代关系，禁止重新列为未决 |
| `docs/agents/streaming-resilience/spec.md` 的 bridge retry／cancel／backpressure 栏 | 同上 | `docs/2604-rewrite/streaming-resilience.md` | pre-commit／post-commit frontier、memory-only／no spill／无 16 MiB 特例与 cancel 已决；仅 bridge Spec 未覆盖的共用 resilience 机制保留未决 |
| `docs/agents/stream-consumers/spec.md` 的 bridge Anthropic SSE／History 栏 | 同上 | `docs/2604-rewrite/streaming.md` | delayed-start、完整 content block commit、cancel 终态与 History 时点已决；仅其他 protocol consumer 或共用 sink 未覆盖部分保留未决 |
| `docs/agents/upstream-keepalive/spec.md` | 已接受的 protocol-specific Spec／ADR；bridge Spec 只提供“heartbeat 不得穿过未完成 block 或充当 commit”的约束 | `docs/2604-rewrite/streaming-resilience.md` | 不从 bridge 合同推导通用 keepalive 设计；未被规范覆盖的 transport keepalive 仍为未决 |

`docs/agents/anthropic-responses-bridge/architecture.md` 不进入上表任何行为规范输入单元。它可以作为非规范架构参考帮助定位接缝，但不得改变已绑定 Spec／Acceptance 的合同、required gate 或 expected；若未来 Architecture 经用户裁决形成 ADR，应以该 ADR 的独立内容身份和适用范围另行登记，不能追认 current 非规范提案为既有 oracle。

- 按第 5 节建立 `anthropic-cache-context`、`anthropic-feature-negotiation`、`header-forwarding`、`thinking`、`anthropic-tool-use` 的最小有内容 specs；未经复验的主题只记录状态和缺口，不提升支持结论。
- 只移动 manifest 指定 `final move phase = 1` 的 `docs/2604-rewrite/streaming.md` 与 `docs/2604-rewrite/streaming-resilience.md` 到第 5.4 节 canonical destinations；其他源即使本阶段已提炼最小 spec，也不得提前移动。
- 给 manifest 中所有 `final move phase > 1`、因而阶段 1 后仍留在旧目录的源加入统一迁移期非真相 banner。其 exact pathspec 由已提交的阶段 1 banner 清单逐字展开；banner 明示“非当前真相源”、`docs/README.md` 现行入口、Anthropic Messages → OpenAI Responses upstream 优先级、block-level buffering 高层裁决、该源唯一 final move phase，以及“文档迁移不替代 topic spec／ADR 中的产品设计与用户裁决”。
- `docs/README.md` 在首屏可见位置声明 `docs/2604-rewrite/` 整体仅为迁移输入，搜索结果直达旧文件时以文件内 banner 为准，旧优先级／零缓冲／块级延后表述均不得作为当前合同。

**先行 oracle 与测试**：

- 从 FastAPI route table 与 route decorators 两种来源生成 Anthropic 端点集合，要求精确相等。
- 从 `src/app/routes/anthropic.py` 生产调用链核对 idle timeout、History tap、passthrough 与 cleanup 顺序。
- 用 AST／调用图确认 keepalive、delayed commit、buffered retry 和 repetition detector 是否存在生产消费者，不以文本零命中作为唯一证据。
- 对活文档执行状态词与合同检查：不得把“默认零缓冲”“块级延后”“下游逐 token／event live”写成产品合同；每个未接线目标都有明确标签和 spec 链接。
- 对按 topic／protocol 分栏的 buffering specs 执行规范优先级检查：Anthropic Responses bridge 栏必须逐项链接 current bridge Spec／Acceptance，并把 Anthropic content block、pre-commit 可透明 retry／post-commit 默认 partial failure、memory-only／no spill／无 16 MiB 专属阈值、SSE delayed-start、cancel／cleanup 与 History 时点标为“已冻结、当前实现待验收”，不得标成“待裁决”；其他协议或共用机制只有在没有更具体 accepted Spec／ADR／Acceptance 时才保留未决。
- 在生成任何 bridge 派生正文和运行上述规范优先级检查前，先运行规范输入 identity gate：重新计算 Spec／Acceptance SHA-256，验证 `FINALIZED`／`FINALIZED_ACCEPTANCE_ORACLE`、Acceptance → Spec 绑定与七域对账身份均精确匹配阶段 0 manifest。任一漂移立即停止阶段 1 相关工作，不得按路径读取新内容继续。
- 运行已提交的 banner 完整性检查，要求每个仍留旧目录的 manifest source 都有且只有一个 banner，banner 的 final move phase 与 manifest 一致；故意删除一个 banner 的 fixture 必须红，已在本阶段移动的两个源不应被错误要求 banner。
- 运行已提交的派生产物 ownership checker，要求上表三个精确输出均由阶段 1 唯一生产和最终持有、输入源精确匹配、全部 literal path 进入且只进入 `phase-1-pathspec.txt`；漏产物、重复 owner、晚生产或跨阶段 pathspec 的反 fixtures 必须红。
- 运行已提交的 renderer-aware 链接检查，禁止链接临时目录；对本阶段两个 moved files 输出 before → after link target 清单并验证 relative rebasing、heading fragment 与 line fragment。
- 在阶段 1 docs 提交与阶段推进前分别创建并关闭一个新 ordinal；每个动作只消费与自身 action／subject identity 精确绑定的 latest non-stale closed revision。本阶段产生或消费且会影响合同、gate、verdict 或下一动作的报告必须在其所属 generation 归纳到正式 owner 并转为 `covered`。post-cut 报告正文进入后继 dirty generation，但其 verdict／action impacts 对尚未执行的当前授权立即生效：只有 closure review PASS、certificate 精确绑定且 unresolved impacts 为空才可窄化 carry forward；blocker／major、当前 action／topic impact或报告 hash 漂移立即使授权 stale，必须先关闭同 ordinal revision 或下一 generation。`partial`／`pending` 不允许 close、提交或推进。

**验收**：README 可从空上下文导向 Anthropic 当前端点、当前流式链、已决 buffering 合同和实现缺口，并在首屏否定旧目录的当前真相源地位；所有仍保留旧源都有迁移期 banner；`streaming-resilience`、`upstream-keepalive`、`stream-consumers` 三份 spec 均已从表定源提炼并由阶段 1 唯一持有，phase-1 pathspec 无需执行者推断；目标与现状没有混写；bridge 栏只消费第 2.3 节绑定的 finalized Spec／Acceptance 内容对，没有把已冻结合同降级为未决，也没有把非规范 Architecture 提升为行为输入；其他协议／共用机制中确实未覆盖的部分仍明确列为门控问题；docs 提交与阶段推进分别消费与自身精确绑定的 latest non-stale closed revision，相关临时报告均已按 cut-off 进入本代或后继代并归纳为 `covered`，且执行前 post-cut verdict／impact／hash gate 证明没有未关闭的当前 action impact；文档迁移没有替代产品设计或新增公共合同。

**独立提交**：`docs: establish Anthropic Messages buffering truth`

**风险／回滚**：最大风险有三个方向：一是借迁移自行定义未覆盖协议的 block 合同，二是用旧 2604 文档反向重开 bridge 已冻结合同，三是同一路径内容漂移后仍沿用旧 finalized 身份。前者只记门控；后两者严格服从绑定 Spec／Acceptance 内容对，并用输入优先级与内容身份反 fixture 阻断。提交可独立 revert，不影响产品代码。

### 阶段 2：OpenAI Responses upstream

**目标**：建立第二产品主线，准确区分 HTTP、SSE 与 WebSocket 的 route、client、History、approval、cleanup 和 buffering 边界。

**涉及文件**：新建 `docs/OPENAI_RESPONSES.md` 与 `docs/agents/openai-responses/spec.md`，更新 `docs/STREAMING.md` 和 `docs/README.md`。本阶段从生产代码与测试重建事实，不移动或改写任何 manifest 源；旧源中的跨协议材料仍由第 5.4 节指定的阶段 3／8 final owners 处理。

**先行 oracle 与测试**：

- 从 route table 和 decorators 两种来源生成 Responses HTTP／WS 三重前缀组合，分别核对 method 与 upgrade 语义。
- 从 `src/app/routes/openai.py`、`src/app/routes/responses_ws.py` 和实际 client 绘制两条生产调用链。
- 对模型验证、approval、History、重试、idle timeout、buffering 和 cleanup 逐项标记“共享／不同／未接线”。
- 在临时期望集合中故意加入不存在别名，确认 route 集合检查会红。

**验收**：文档不引用不存在的 `routes/responses.py`，不宣称复用 Anthropic 完整 pipeline，不暗示通用 translator 已接线；HTTP／WS 差异可由代码和测试复现。

**独立提交**：`docs: document OpenAI Responses upstream truth`

**风险／回滚**：统一转换目标只进入 `cross-protocol-translation` spec，不阻塞当前真相文档。单提交可 revert。

### 阶段 3：API、架构与配置骨架

**目标**：建立两条主线共享的查阅入口，不提前把所有次级协议改造成一个虚假的统一架构。

**涉及文件**：新建 `docs/API.md`、`docs/ARCH.md`、`docs/CONFIG.md`，更新 `docs/README.md`，拆分／归档 `DESIGN.md`、`config-system.md`、`data-models.md`、`project-structure.md` 的对应部分。

**先行 oracle 与测试**：

- 用 OpenAPI 与 `app.routes` 两种方法生成 API 表；解释并解决差异。
- 从 `server.py` lifespan、`RuntimeState`、deps 与真实 clients 反推架构，不复制目标模块树。
- 从 Pydantic schema 生成配置键、类型与默认值，再从生产调用点补“消费位置／生效时点／未消费”列。
- 特别验证 resilience 与 transport keepalive 字段当前是否未接线，以及配置修改是否需要重启。
- 写入文档的数量必须带 commit、路径和命令口径，并经不同原理交叉验证。

**验收**：当前 route、组件装配与配置状态可机械复现；“字段存在”和“生产消费”分列；不存在热重载现在时。

**独立提交**：`docs: add current API architecture and config references`

**风险／回滚**：动态 route 可能被静态扫描遗漏，因此必须保留运行时 route table 对照。单提交可 revert。

### 阶段 4：Anthropic pipeline、sanitize、hooks 与 tokenization

**目标**：迁移已实施且直接服务 Anthropic 主线的共享能力，不把其契约泛化到未接线协议。

**涉及文件**：新建 `docs/REQUEST_PIPELINE.md`、`docs/SANITIZE_PIPELINE.md`、`docs/HOOKS.md`、`docs/TOKENIZATION.md`、`docs/TOOL_USE.md`；迁移 `docs/agents/hooks-tokenization/spec.md`；归档已完成 hooks／tokenization 计划和 kick-off。

**先行 oracle 与测试**：

- 每篇文档从生产入口追到实现，不以孤立单测或 helper 定义证明接线。
- Hooks 核对 registry 启动期冻结、module failure、observer isolation 与 built-ins。
- Tokenization 分别验证 Anthropic 上游优先／fallback 与 Gemini 本地估算。
- Tool Use 分开验证 client tools、tool search 与 server tools 的生产边界。
- 运行主题 targeted tests、链接检查和文档 oracle。

**验收**：每项“已实施”由代码和测试独立重建；协议适用范围明确；完成态计划不再出现在待办入口。

**独立提交**：`docs: migrate Anthropic pipeline hooks and tokenization docs`

**风险／回滚**：旧 spec 的“已实施”自述不构成证据。若验收项无法复验，状态降为“未验证”并进入开发缺口。单提交可 revert。

### 阶段 5：认证、模型解析与剩余 Anthropic 内部合同

**目标**：补齐 Anthropic 主线的可操作文档，把用户可见合同与内部机制分层。

**涉及文件**：新建 `docs/AUTHENTICATION.md`、`docs/MODEL_RESOLUTION.md`，完善 `docs/ANTHROPIC_MESSAGES.md`，归位 authentication、model-resolution、feature-negotiation、header-forwarding 和 thinking 资料。

**先行 oracle 与测试**：

- 复验 token provider 顺序、account type、refresh、CLI 与脱敏。
- 用表驱动样本验证 model alias、normalize、override、disabled model 与 catalog 交互。
- 从生产调用链验证 feature negotiation、thinking quarantine 和 header policy 的实际范围。
- 检查所有配置变更描述是否明确当前重启要求。

**验收**：活文档只保留用户可观察合同；内部算法进入 topic spec；不存在 server-tool 或热重载超前陈述。

**独立提交**：`docs: migrate authentication and model contracts`

**风险／回滚**：过度压缩可能丢失未来需求，因此每项被移出活文档的内容必须有 spec 或 archive 去向。单提交可 revert。

### 阶段 6：History 真相与后续能力分离

**目标**：修复 History 的时序、持久性、schema 与 API 超前陈述，为两条主产品路径建立可信记录语义。

**涉及文件**：新建 `docs/HISTORY.md`、`docs/agents/history-durability/spec.md`、`docs/agents/history-api/spec.md`，拆分并归档 `history-system.md`。

**先行 oracle 与测试**：

- 从 SQLite schema 和 Python types 两种来源生成字段交集／差异并逐项解释。
- 分别绘制 Anthropic consumer 与其他 protocol-history 的 `in-flight → queue accepted → SQLite commit/failure → removal/broadcast` 时序。
- 从真实 route signature 验证 REST 参数，从 broadcaster 验证 WS event，从 export 实现验证内存行为。
- 写盘失败语义由故障注入或已有失败测试证明；无充分 oracle 时在活文档标“未验证”，并在 spec 要求补测。

**验收**：不把未来 zstd、重试、流式 export、分页／搜索字段写成当前能力；两条 finalize 路径不互相冒充保证。

**独立提交**：`docs: reconcile History storage and API truth`

**风险／回滚**：History 时序容易被单一路径样本误导。验收必须覆盖两条生产路径。单提交可 revert。

### 阶段 7：运维、可观测性与审批

**目标**：迁移影响操作正确性的文档，严格区分已装配服务与未接线 helper。

**涉及文件**：新建 `docs/OPERATIONS.md`、`docs/OBSERVABILITY.md`、`docs/APPROVAL.md` 及 `operations`、`observability`、`approval` topic specs，拆分并归档对应源文档。

**先行 oracle 与测试**：

- 关闭、deadline、stale reaper 与 error persistence 均要求 server／lifespan／signal 的真实接线证据。
- 实际抓取 metrics route，核对 content type 与关键指标；tracing／TUI 按配置和启动路径验证。
- 用现有集成测试或可复现 probe 核对 approval REST／WS／timeout／shutdown rejection。
- 对每项“支持”至少运行一次真实 app probe 或集成测试。

**验收**：配置字段存在但未消费时只进入缺口；运维步骤可执行，未装配 helper 不出现在支持表。

**独立提交**：`docs: reconcile operations observability and approval docs`

**风险／回滚**：静态存在最容易造成假绿，必须使用运行态探针。单提交可 revert。

### 阶段 8：次级协议与跨协议设计

**目标**：在两条主线和共享基础稳定后整理 Chat Completions、Azure、Gemini，不让次级协议抢占主线迁移节奏。

**涉及文件**：完善 `docs/API.md`、`docs/ARCH.md`、`docs/STREAMING.md`，新建 `docs/agents/multi-protocol/spec.md` 与 `docs/agents/cross-protocol-translation/spec.md`，拆分并归档 `multi-protocol.md` 对应内容。

**先行 oracle 与测试**：

- 对每个端点列“入站协议／实际 upstream API／请求转换／响应转换／共享设施／idle timeout／buffering／History”，从 route 到 client 逐项取证。
- 只有存在生产消费者的 translator 才能进入当前支持矩阵。
- Gemini 专用转换、Azure OpenAI wire 适配和其他路径单列，不为表格整齐强造统一架构。

**验收**：协议矩阵允许真实差异；次级协议未实现能力仍保留于 specs／ROADMAP，没有因低优先级删除。

**独立提交**：`docs: reconcile secondary protocol routing and translation`

**风险／回滚**：最大的风险是以抽象一致性替代生产事实。矩阵必须接受非统一结果。单提交可 revert。

### 阶段 9：路线图与完整需求归位

**目标**：在当前真相稳定后，把旧 BACKLOG／ROADMAP 中全部能力逐项归位，形成不以成本理由静默砍功能的活路线图。

**涉及文件**：完成 `docs/ROADMAP.md`、`docs/agents/product-roadmap/` 与必要 topic specs，拆分并归档旧 `BACKLOG.md` 与 `ROADMAP.md`。

**先行 oracle 与测试**：

- 对旧 BACKLOG／ROADMAP 每项建立 disposition：已实现、已决待实现、待用户重裁、被明确取代。
- 从旧源到新路线图正向核对，再从新路线图反向核对，要求能力集合相等且每项只有一个当前状态。
- 确认 Anthropic Messages 与 buffering 位于首位，OpenAI Responses upstream 位于第二位。
- 对旧“拒绝／简化／缓存／延后”逐项查找直接用户裁决；找不到则标“待重裁”。

**验收**：无“无去向”能力；所有未进入当前实施序列的能力仍保留依赖与验收意图；迁移者没有新增产品范围裁决。

**独立提交**：`docs: reconcile product roadmap without scope loss`

**风险／回滚**：旧作者判断容易被误当用户决定。无法证明的拒绝一律进入待重裁，不自行接受或推翻。单提交可 revert。

### 阶段 10：开发资料归档与旧入口切换

**目标**：新活文档可用后，最后迁移调研、完成态计划和旧源快照，移除 `docs/2604-rewrite/` 的入口职责。

**涉及文件**：只迁移第 5.4 节中 `final move phase = 10` 的 dependency-selection 和完成态材料；更新仓库内 Markdown 链接；仅当 manifest 证明其他 final owners 均已完成且旧目录为空时移除空目录。阶段 10 不接管前序阶段漏移的源。

**先行 oracle 与测试**：

- 阶段 10 自身移动的每个 archive 文件把迁移期 banner 替换为统一永久归档头：历史状态、取代原因、取代日期、现行入口、原始 source path、阶段 0 source hash 和基线 commit；迁成有效开发／研究资产的 canonical destination 使用 provenance 头而非伪装 archive 头。对前序 final owners 的目标只做只读完整性审计，发现仍有迁移期 banner 就回到所属阶段修复，不在阶段 10 越权批量改写。
- 迁移前冻结集合与 canonical destination／final move disposition 精确相等；阶段 10 只能移动 manifest 指定 `final move phase = 10` 的源，不能兜底接管其他阶段遗漏项。发现遗漏必须回到唯一 final owner 阶段修复。
- 对 `docs/**` 全树运行受管 header 规范化后的精确正文 hash 与近似正文块扫描。`retained_exact` 必须在唯一 canonical destination 命中一次，`transformed_asset` 必须有 provenance 且完整旧正文命中零次；任何额外精确副本一律失败。近似候选逐条 disposition，未标注来源或现行入口的正文副本不得通过。注入“canonical move 正确且额外复制一份”的 fixture 必须红，合法提炼 fixture 必须绿。
- 仓库级 renderer-aware Markdown 链接全绿；活文档不得链接 `docs/2604-rewrite/` 或临时目录。每个 moved file 输出 before → after link target 清单，移动后相对路径、heading fragment、Unicode slug 和 GitHub line fragment均按阶段 0 fixtures 的同一语义复验。
- 搜索旧含混状态词和零缓冲／块级延后合同，只允许在明确标记的 archive 中出现。
- `git diff --name-only` 不含临时目录、既有 verification 材料或产品文件。

**验收**：旧目录不再是入口；42 项均位于 manifest 唯一 canonical destination，且移动提交均来自唯一 final owner；无精确重复和未 disposition 的近似正文候选；README／ARCH／ROADMAP 不把 archive 当当前真相源。

**独立提交**：`docs: archive 2604 rewrite development artifacts`

**风险／回滚**：这是首次大规模移动，但内容已在前序切片稳定。使用 Git move 保留历史；链接 gate 失败则不提交。单提交可 revert。

### 阶段 11：合并态验证与定稿

**目标**：验证逐切片全绿没有掩盖跨文档接缝错误，并形成可交付 verdict。

**合并态验收**：

1. 从空上下文沿 `docs/README.md` 完成三个任务：找到 Anthropic 当前端点与缺口；找到 Responses HTTP／WS upstream 路径；找到 buffering 已决合同与当前未接线状态。
2. 重新生成 route、settings、History schema、WS event 与生产调用矩阵，与全部活文档对账。
3. 对每个全称断言主动寻找反例。
4. 检查每篇文档是否明确区分当前实现与已决目标。
5. 无条件运行阶段 0A／0B 已提交且经过双向控制的 renderer-aware link checker、manifest checker、banner／archive 状态 checker、provenance／重复 checker、bridge 规范输入 identity checker 和 report-distillation generation／matrix checker；项目若另有 Markdown／lint gate，再并行运行，不能用后者替代前者。
6. 运行 Ruff、Pyright strict 与全量 pytest。它们不证明 Markdown 语义正确，只证明迁移没有误改产品文件、配置或测试。任何测试数量都必须记录命令、commit 和路径口径，并用不同原理交叉验证。
7. 复核 HEAD、分支、工作树和 `docs/ROADMAP.md`，逐条验证 pending、当前状态、归属与下一步。
8. 对最终 docs 提交、阶段完成声明、产品回放、archive／worktree 清理及仍待进行的用户裁决分别创建并关闭 generation ordinal；每个动作只消费 action／subject identity 精确匹配的 latest non-stale closed revision。该代所有相关报告必须为 `covered`，正式落点和 anchor 必须可解析，`docs/tmp/**` 不得是 current 结论的唯一载体；任一 dirty／pending／partial／stale revision 都不能被消费。执行前必须重扫 post-cut reports 并验证 closure PASS certificate 的 subject／payload／action／observed set／hash 与空 unresolved impacts；blocker／major、当前 action／topic impact或任一报告 hash 漂移必须先经同 ordinal revision 或下一 generation 关闭，不能先执行旧授权。
9. 进行独立评审，同时检查 false-green 和 false-red：错误状态能否混入活文档，以及正确状态会不会被过严规则误报。逐条 disposition，修改后复评。

**提交**：仅修链接、索引或措辞时使用 `docs: finalize migrated documentation index`；发现主题事实错误时回到拥有该事实的阶段形成语义提交，不把多主题事实修复塞入 finalize 提交。

**风险／回滚**：merged-state 问题按所属主题修复并复跑全部门。不得为追求最终单提交而重写前序历史。

## 8. 非功能要求

### 8.1 可验证性与可观测性

- 活文档中的支持矩阵尽可能由 route、schema 或 settings 探针生成，人工只补语义和已决目标。
- 任何数字都带 commit、路径和命令口径，并由不同原理交叉验证；无法交叉验证时明确写“未交叉验证”。
- 外部依赖版本和维护状态注明核验日期，不把一次调研快照写成永久事实。
- 归档头和状态词使用一致模板，确保搜索命中者能立即辨认历史材料。
- 每份临时报告的 load-bearing 结论都有正式 owner、稳定 anchor、coverage、verdict、action／topic impacts 与依赖动作；action-scoped checker 只消费 latest non-stale closed revision 的冻结 inventory／identity／ledger／closure／certificate 和正式落点，不把 `docs/tmp` 的存在性冒充归纳完成。cut-off 后新增报告正文进入后继 dirty generation且不改写旧 revision bytes，但其 verdict／impacts／hash 对未消费授权立即生效；只有 PASS certificate 精确绑定且 unresolved impacts 为空才可窄化 carry forward，其余必须先关闭修订版或下一代。

### 8.2 性能与产品行为

本计划不修改运行时代码，因此不得声称改善或回归产品性能。质量门的作用是证明没有误改产品路径。Anthropic Responses bridge 的 memory-only、no spill、普通 per-request aggregate＋global reservation／backpressure 与“无 16 MiB 专属阈值”已由 current bridge Spec／Acceptance 冻结，文档迁移只能如实承接；其他协议或跨协议共用机制的内存、spill、背压和并发预算，只有未被更具体规范覆盖的部分才作为后续产品规格门控，不在文档迁移中凭空决定。

### 8.3 兼容与迁移安全

- 新入口先建立，旧入口最后切换，避免迁移窗口出现“所有资料先归档但活文档尚不可用”。
- 每阶段链接只指向已经存在且已经验证的文档，不预链接未来空目录。
- 每次移动都生成本切片 before → after 链接目标清单，并用同一个 GitHub renderer oracle 验证相对路径 rebasing、heading fragment、Unicode heading 与 line fragment；文件存在性只是一层必要条件，不代表 fragment 有效。
- archive 保留历史上下文，但必须清晰指向现行入口。
- 每阶段独立提交，使文档工作可暂停、可恢复、可按主题回滚，不绑架产品发布节奏。

## 9. 门控问题

### 9.1 Buffering 合同按 topic／protocol 分栏

| Topic／protocol | 合同轴 | 当前状态 | 规范输入与阶段 1 处置 |
|---|---|---|---|
| Anthropic Messages → OpenAI Responses bridge | semantic block | **已冻结**：一个 semantic block 就是一个 Anthropic content block；完整 block 是最小下游可观察提交单元 | 以第 2.3 节绑定 Spec 的“术语”“Semantic block 的冻结定义与完成条件”和绑定 Acceptance `STR-01`～`STR-03` 为准；禁止从旧 streaming 文档重开 |
| Anthropic Messages → OpenAI Responses bridge | pre-commit／post-commit retry | **已冻结**：首 block commit 前，符合统一策略与预算的故障可透明 retry；commit 后不得从头重放，未获独立 resume contract 时固定 partial failure | 以 bridge Spec 的“Retry ownership 与 delivery semantics”及 Acceptance `REL-01`～`REL-04` 为准；实现状态可为 `UNVERIFIED`，合同状态不得写成未决 |
| Anthropic Messages → OpenAI Responses bridge | memory／spill／backpressure | **已冻结**：memory-only、no spill、不得退化为 live forwarding；使用普通 per-request aggregate 与 global reservation／backpressure，不设 16 MiB 专属阈值、fixture、metric 或状态分支 | 以 bridge Spec 的“一般 memory-only 与全局背压政策”和 Acceptance `REL-06` 为准；旧大对象／整响应方案只作历史素材 |
| Anthropic Messages → OpenAI Responses bridge | downstream Anthropic SSE | **已冻结**：首个完整 block 前零 HTTP success headers、零 `message_start`、零 body event；首 block 与 `message_start` 同一串行 batch，随后按完整 envelope 提交 | 以 bridge Spec 的“Downstream Anthropic SSE”和 Acceptance `STR-01`、`STR-02`、`CAL-04` 为准；delayed-start 是现行目标合同，不是可重裁选项 |
| Anthropic Messages → OpenAI Responses bridge | cancel／cleanup | **已冻结**：cancel 向当前 upstream 传播、不 retry、不提交 partial block，资源关闭与 finalize 恰好一次；已提交前缀保留、未提交状态丢弃 | 以 bridge Spec 的“Client cancel”与 Acceptance `REL-05` 为准 |
| Anthropic Messages → OpenAI Responses bridge | History／usage／observer 时点 | **已冻结**：一个 request id 对应一条 History；失败 attempt 不贡献成功 response／usage；成功仅在合法 terminal 且 committed blocks drain 后成立；post-commit failure、cancel 与 shutdown 使用可区分终态，finalize 恰好一次 | 以 bridge Spec 的“History”及 Acceptance `LIFE-01`、`STR-05`、`REL-03`、`REL-05` 为准 |
| Anthropic direct Messages leg | 上述六轴 | **仅未覆盖部分未决** | bridge Spec 不替 direct leg 新增合同；先查 direct-leg accepted Spec／ADR／现有外部合同，只有仍无答案的轴进入 `docs/agents/buffering/spec.md` 未决栏 |
| 原生 OpenAI Responses HTTP／WS 公共入口 | 上述六轴 | **仅未覆盖部分未决** | bridge Spec 不改变原生 Responses route 的公共合同或 lifecycle owner；阶段 2 从该 topic 的 accepted Spec／实现 oracle 取证，缺口保持未决 |
| Chat Completions／Azure／Gemini 等次级协议 | 上述六轴 | **仅未覆盖部分未决** | 按协议分别查 accepted Spec／ADR；不得把 bridge 的 Anthropic content block 或 Anthropic SSE envelope 泛化过去，也不得因旧文档没有答案而静默选择 |
| 跨协议共用机制 | sink acknowledgement、delivery-uncertain、共用 quota／queue、公平性、transport keepalive、统一 observability | **仅未覆盖部分未决** | 可复用 bridge 已冻结的不变量作为该 bridge 的约束，但共用 API、职责、预算分配和其他协议语义必须另有 accepted architecture／ADR；没有时保留门控，不从 bridge 单向外推 |

阶段 1 的 `docs/agents/buffering/spec.md` 必须保存这组分栏：bridge 六轴写为“已冻结、实现待验收”，其他协议／共用机制只对未被更具体 accepted Spec／ADR／Acceptance 覆盖的单元写“未决”。任何实现计划只能从已经冻结的分栏派生；仍未决的单元必须先完成对应架构裁决和验收 oracle 评审。旧 `docs/2604-rewrite` 文档不得成为规范输入，也不得把“当前实现未接线／尚未通过 Acceptance”误写成“产品合同未决定”。

### 9.2 必须交回主会话重裁的问题

- 旧 BACKLOG／ROADMAP 中标为拒绝、简化、缓存或延后，而找不到直接用户裁决的能力。
- server-tool 的重新引入。当前边界是不支持；恢复它属于新规格，不属于文档纠错。
- 配置热重载、TCP keepalive、H2 PING、History durability／API 扩展和统一 translator 的具体架构。
- 任何改变公共 API、协议语义、持久化 schema、兼容策略、技术栈或部署拓扑的提议。

## 10. 未采纳方案

### 一次性移动 `docs/2604-rewrite/*` 到 `docs/`

未采纳。它会同时提升已证伪的当前态描述、未来设计和历史材料，并在一个提交中制造事实冲突与断链，无法独立回滚。

### 先全部归档，再从零写活文档

未采纳。迁移窗口会失去可查上下文，也容易漏掉不能因 ROI／YAGNI 删除的旧需求。正确顺序是先建立可验证的新入口，最后归档旧源。

### 按旧文件一对一改名

未采纳。多个旧文件同时混合当前事实、目标设计和历史取舍，一对一改名无法恢复真相层次。

### 只修已知 blocker／major 的句子

未采纳。已知发现只是最低检查集合，不是剩余正文正确性的证明。每个活文档必须从生产入口重建事实并主动寻找反例。

### 把所有未来能力继续放在单一 BACKLOG

未采纳。它会再次混合优先级、架构问题、实施计划和被取代方案。未来能力应进入稳定路线图与具体 topic spec，并保留依赖和验收意图。

### 为了减少文档工作而删减低优先级功能

未采纳。产品优先级只决定实施顺序，不构成删除或无限期推迟需求的授权。

### 从 ledger 中排除 checker／ledger 自身评审报告

未采纳。是否“属于自评报告”会退化为执行者自判豁免，并让会改变 gate 正确性的结论永久绕开归纳。所有此类报告正文都进入 cut-off 后的后继 generation；但其 verdict、action impacts 与 hash 对未消费授权立即生效。只有精确 PASS certificate 且 unresolved impacts 为空时才允许窄化 carry forward，其他情况先把当前授权标为 stale 并关闭同 ordinal revision 或下一代；该分层既解决终止性，也不删除当前动作前的检查义务。

### 用一个实时可变 ledger 与当前 `docs/tmp` 永远精确相等

未采纳。评审 ledger 的报告会要求改 ledger，改后的 ledger 又需要评审，形成无终点闭环。generation cut-off 冻结本 revision 的正文输入，后续报告正文进入后继 dirty generation；若报告 PASS 且对当前 action 无 unresolved impact，精确 certificate 允许窄化 carry forward。否则当前授权立即 stale，并在动作尚未消费时关闭同 ordinal revision，或按协议关闭下一 generation；不能以终止性为由先消费旧授权。

## 11. 实施 kick-off

在 `/home/xp/src/ghc-api-proxy-py` 执行 `docs/agents/documentation-restructure/plan.md`，先只完成阶段 0A、0B 和阶段 1。每次 shell 调用必须在同一调用内绑定并验证仓库绝对路径，打印 HEAD 与 `git status --short`；首次确认规划基线 `47d9ef101c4b81ac70d805b1da157b34d021d33d` 是实际 HEAD 的祖先，之后记录每个切片自己的开始和结束 HEAD。

阶段 0A 的唯一入口是 `bootstrap_kernel_commit`。它只提交固定 `docs/agents/documentation-restructure/verification/protocol-marker.json` 与 `verification/bootstrap-kernel/bootstrap-assets.txt` 逐字列出的 checker／schema／fixtures／fixture hash manifest／bootstrap test instructions。开始前机械验证父 HEAD 中 marker、bootstrap kernel namespace、latest pointer 和任何 closed generation 全部不存在；marker 绑定 protocol version、父 HEAD、bootstrap-assets blob 与非 marker kernel 的 sorted path＋Git blob OID identity。运行前把正样本和目标 mutants 按路径＋SHA-256 冻结到 repo 外只读目录，先验 hash，再让候选 checker 对该冻结集合做正反控制；staged paths 必须与 marker＋allowlist 双向精确相等。固定失败码 40～47 分别覆盖 marker、kernel、latest、closed generation、allowlist、kernel identity、fixture identity 与 review receipt 失败，任何失败都不得写 commit。不得要求尚不存在的 ledger checker 前置，不得提供 `--skip-ledger`、`--bootstrap`、空 ledger 成功或任何操作者自评豁免。最终候选必须取得绑定 marker blob、kernel identity 与候选 tree identity 的独立复评 0 blocker／0 major 回执，才能形成 `test(docs): add documentation verification bootstrap` 提交；提交后原 bytes 与换 bytes 重跑都必须以 `40/bootstrap_marker_exists` 失败。回执正常进入 `docs/tmp/`，其路径＋hash 由 harness 记录并由 0B 纳入 generation 0。marker 永不修改；后续 kernel 升级只能走普通 versioned migration generation。

阶段 0B 只能使用已提交且由 marker 绑定的 0A checker，在扫描开始时冻结 generation `<0,0>` 的全部 `docs/tmp/*.md` sorted path＋content hash cut-off，生成并验证 42 项 hash／owner／pathspec manifest、全部派生产物 producer coverage、规范输入 identity、逐阶段 pathspec、generation 0 inventory／identity／distillation ledger／canonical closure payload。独立 closure review 只有在 verdict 为 PASS、0 blocker／0 major、certificate 精确绑定 generation／payload／action／observed post-cut report set且 `unresolved_action_impacts=[]` 时才能关闭 revision；generation 0 closure 只授权与 0B staged payload manifest 精确相等的 `docs_commit`，payload manifest 排除 machine-readable certificate／closure／index，closure 单向绑定 certificate identity 与 payload manifest hash，index 只绑定 closure hash，完整 staged allowlist 仍包含三者。0B 形成独立 `test(docs): freeze documentation migration generation zero` 提交。评审 checker／ledger 自身所产生的新报告正文进入 generation 1；若 PASS 且不影响当前 action，可由精确 certificate 窄化 carry forward，若为 blocker／major、影响当前 action／topic、subject 不匹配或报告 hash 漂移，则 generation 0 action 立即 stale，必须先关闭 `<0,1>` 或 generation 1，不能先提交 0B。所有后续 `docs_commit`、`phase_advance`、`product_replay`、`archive_cleanup`、`worktree_cleanup`、`user_ruling` 都只消费与自身 action／subject identity 精确匹配的 latest non-stale closed revision；dirty／pending／partial／stale 不通行，每个 revision 只授权一个动作，动作消费后下一动作必须使用后继 ordinal。不得让 checker 永久依赖 `docs/tmp/260807-tmp-distillation-matrix.md`。

bridge 规范输入精确绑定为 Spec `FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` 与 Acceptance `FINALIZED_ACCEPTANCE_ORACLE@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`，Acceptance 必须继续绑定同一 Spec hash 与已完成七域 policy 对账；非规范 Architecture 不得成为行为 normative input。阶段 0B 建 manifest 前与阶段 1 开始前都重算并检查，任一漂移立即停止相关 gate，先完成规范对账、独立复评和验证资产更新，禁止只按路径存在继续。

阶段 1 严格按 manifest 精确 pathspec 建立活入口，只移动 final owner 为 1 的两个 streaming 源，并在移动前从表定历史输入生成 `docs/agents/streaming-resilience/spec.md`、`docs/agents/upstream-keepalive/spec.md`、`docs/agents/stream-consumers/spec.md`；这三份 spec 的 producer 与唯一 final owner 都是阶段 1，路径必须进入且只进入 `phase-1-pathspec.txt`。bridge 栏原样承接已冻结的 Anthropic content block、pre-commit／post-commit retry、memory-only／no spill／无 16 MiB 特例、SSE delayed-start、cancel／cleanup 与 History 时点；旧 `docs/2604-rewrite/streaming*.md` 仅作带 provenance 的历史素材，禁止反向重开合同。其他协议／共用机制只保留未被更具体 accepted Spec／ADR／Acceptance 覆盖的未决项。给所有仍保留旧源加非真相 banner；`docs/README.md` 必须首屏明示旧目录不再是当前真相源。

严格遵守已裁决分层：`docs/` 是活文档，`docs/agents/<topic>/` 是开发文档，`archive-<date>/` 是带取代说明的历史材料。先从生产 route、settings、schema、lifespan、调用点与测试建立 oracle，并对检查器做正反控制，再迁移正文并复跑同一 oracle。产品优先级固定为 Anthropic Messages → OpenAI Responses upstream；block-level buffering 是基础合同，下游不承诺 token/event 级 live streaming，当前未接线必须明确标注；文档迁移只记录已决合同与未决项，不替代产品设计、ADR 或新的用户裁决。不得因成本、ROI、YAGNI 或低优先级删除、降级或无限期推迟任何旧需求。每阶段形成独立 Conventional Commit，只提交已冻结的 literal pathspec，绝不纳入 `docs/tmp/**`、仓库根部既有 `verification/**` 或其他阶段开始前脏项。阶段 1 验证并提交后暂停，向主会话报告开始／结束 HEAD、文件清单、oracle、测试结果、结构怪味与待裁问题，再由主会话安排后续阶段；不要让文档重组连续占用产品主线。

## 12. 独立评审 major 处置表

| Major | 处置 | 落点 | 验收证据 |
|---|---|---|---|
| 阶段 0 oracle 只在临时目录，无法跨暂停复现 | 采纳。checker、schema、fixtures 与执行说明由阶段 0A 提交，manifest、pathspec 与 generation 0 正式 ledger 由阶段 0B 提交；两者都位于 `docs/agents/documentation-restructure/verification/` 并先于文档迁移落地，临时目录只留运行输出和 repo 外冻结 fixture 副本。 | 第 3.1、6.2、6.3 节与阶段 0 | 全新临时工作目录只凭 0A＋0B 已提交资产可复跑；0A staged paths 与 `bootstrap-assets.txt`、0B staged paths 与生成清单分别双向精确相等，0A 最终候选另有绑定 hashes 的独立 0／0 回执。 |
| 迁移窗口仍保留旧冲突源，旧优先级／buffering 合同可被直达 | 采纳。阶段 1 给所有 `final move phase > 1` 的旧源加统一非真相 banner，`docs/README.md` 首屏声明旧目录整体仅为迁移输入，并写明文档迁移不替代产品设计。 | 第 2.1 节与阶段 1 | banner checker 对 retained source 集合精确相等；缺一 banner 的反 fixture 红，已移动源不产生 false-red。 |
| 跨阶段提炼与最终移动 owner 含糊 | 采纳。为全部 42 项增加 `extract phases`、唯一 `final move phase` 和 literal source → canonical destination；阶段 pathspec 由机器 manifest 冻结。R2 发现 source move owner 闭合仍不足以覆盖派生产物，因此进一步把第 5.1～5.3 节全部新产物纳入 `required_outputs` producer gate，并为本轮三份阶段 1 spec 单独冻结唯一 final owner。 | 第 5.4、6.3 节、阶段 0、阶段 1、阶段 10 | 42 行 source ownership checker、final owner 唯一性、extract 不晚于 final move、全部 required output 的 producer／source inputs／producer-stage pathspec 唯一完整；三份阶段 1 spec 另满足 final owner 唯一且不进入阶段 2～11 pathspec；staged path 与 phase pathspec 精确相等。 |
| 映射全绿仍可能留下未标注正文副本 | 采纳。冻结每项原始字节与受管 header 规范化后的正文 content hash、canonical destination 和 `destination_kind`，对 `docs/**` 做精确 hash 和近似正文块候选扫描；近似候选逐条 disposition，并加入额外复制缺陷注入与合法提炼正样本。 | 第 3.1 节、阶段 0、10、11 | `retained_exact` canonical 单份与 `transformed_asset` provenance 提炼为绿；mapping 正确但多复制一份为红；未 disposition 的近似候选阻断提交。 |
| 链接 gate 未定义 fragment／renderer／移动 rebasing | 采纳。renderer 固定为 GitHub 仓库 Web UI 的 GitHub Flavored Markdown，分别检查文件、heading fragment 与 GitHub line fragment；冻结移动 rebasing、Unicode、重复 heading、line range 的正反 fixtures。 | 阶段 0、1、10、11 与第 8.3 节 | 正确 rebasing／heading／Unicode／line fragment 为绿；旧相对路径、旧 heading slug、错误 Unicode slug、畸形或越界 line fragment 为红。 |
| R2：阶段 1 最终移动两个 streaming 源，但三个派生 spec 没有 producer phase、source extract inputs、stage pathspec 和唯一 final owner | 采纳。将 `docs/agents/streaming-resilience/spec.md`、`docs/agents/upstream-keepalive/spec.md`、`docs/agents/stream-consumers/spec.md` 明确分配给阶段 1，并冻结各自输入源、literal pathspec 与唯一 final owner；同时把 ownership gate 泛化到第 5.1～5.3 节全部派生产物，避免只修三个特例。没有调整阶段 2～11 的既定范围。 | 第 5.4 节末、阶段 0、阶段 1 | 三份 spec 均在输入源最终移动前由阶段 1 生产；完整分配为绿，漏产物、重复 owner、晚生产和跨阶段 pathspec 四类 fixture 分别为红；`phase-1-pathspec.txt` 精确包含三条输出且其他阶段不含这些路径。 |
| 临时报告缺少跨日期命名与正式归纳合同 | 采纳。新增前瞻性仓库规则：新建 `docs/tmp/*.md` 按实际创建日使用 `YYMMDD-<topic>.md`，同日多份或多轮使用 `-rN` 或明确的轮次／性质后缀；既有无前缀报告可原样保留但不得复制成新命名。临时结论必须及时归纳到对应 `docs/agents/<topic>/`，并由正式状态文档记录报告到正式落点的覆盖状态。该修订只补文档治理合同，不调整迁移阶段 0～11 的文件范围、所有权或顺序。 | 第 2.5 节 | 未来新报告名可由创建日、主题与轮次／性质唯一解释；旧无前缀报告保持单一历史身份；每个会改变当前状态或 gate 的报告都能在对应正式状态文档找到“报告或报告族 → 正式落点 → 覆盖状态”记录。 |
| Merged-state：计划把 Anthropic Responses bridge 已冻结的逐协议 buffering 合同重新生成成未决问题 | 采纳并关闭计划缺陷。门控问题改为按 topic／protocol 分栏；bridge 的 Anthropic content block、pre-commit／post-commit retry frontier、memory-only／no spill／无 16 MiB 特例、SSE delayed-start、cancel／cleanup 和 History 时点均以 current bridge Spec／Acceptance 标为已冻结。阶段 0 manifest 新增规范输入／历史输入身份与优先级；阶段 1 buffering specs 只读消费 bridge Spec／Acceptance，旧 2604 streaming 文档仅作历史素材且不得反向重开。其他协议／共用机制只保留未被更具体规范覆盖的未决单元。 | 第 2.3、5.4、8.2、9.1 节，阶段 0、阶段 1 与实施 kick-off | 正 fixture 中 bridge 六轴均为“已冻结、实现待验收”，旧冲突只保留 provenance；任一历史输入把六轴之一改回未决或旧方案时 gate 为红。其他 protocol 栏在存在 accepted Spec／ADR／Acceptance 时不得误报未决，在确无覆盖时仍保留门控。 |
| R4：bridge `normative_inputs` 只绑定路径，无法证明阶段 1 消费的仍是已接受内容版本 | 采纳并关闭计划缺陷。绑定 Spec `FINALIZED@a193da…` 与现场交叉复核的 Acceptance `FINALIZED_ACCEPTANCE_ORACLE@31673…`，同时冻结 Acceptance → Spec `a193da…` 关系与七域 policy 对账身份；阶段 0／1 都重算内容身份并 fail closed。Architecture 明确保持非规范参考，不得进入行为 expected。内容漂移只能经新规范对账、独立复评与验证资产提交恢复，禁止只刷新 hash。 | 第 2.3、5.4、6.5 节，阶段 0、阶段 1 与实施 kick-off | 正确内容对为绿；Spec 漂移、Acceptance 漂移、状态错误、绑定不一致、只刷新 hash 未重做对账分别为红；Architecture 改变不改 expected，把 Architecture 提升为行为输入时为红。 |
| R4：“及时归纳”允许 `pending` 长期存在，没有下一动作前的机械截止门 | 采纳并关闭计划缺陷。每份 `docs/tmp/*.md` 必须进入其 cut-off 所属 generation 的 `distillation-ledger.json`，逐结论登记正式落点、coverage、owner、受影响动作与失效条件；在 docs 提交、阶段推进、产品回放、archive／worktree 清理或用户裁决中最早相关动作前，所属 generation 必须转为 latest closed，且相关结论为 `covered`。current 260807 临时矩阵只作一次性示例，不成为永久依赖或权威。 | 第 2.1、2.5、6.5、8.1 节，阶段 0、阶段 1、阶段 11 与实施 kick-off | 完整正式落点为绿；漏登记、只登记 `pending`／`partial` 便 close、缺 anchor、漏剩余项、落点仍为 `docs/tmp/**` 分别为红；无关 topic 的 covered 结论不误阻断。checker 在临时示例文件不存在时仍可重跑。 |
| Merged-state R2：阶段 0 首次提交依赖尚未提交的 checker，且评审 checker／ledger 新增报告会无限反向使 ledger 失效 | 采纳并关闭计划缺陷。阶段 0 固定拆为两个不可 squash 的提交：0A 先用 repo 外只读冻结 fixture 与独立 0／0 回执校准并提交原始 kernel；0B 只使用 committed kernel，在扫描开始时冻结 generation 0 报告集合＋content hashes，生成 inventory／identity／distillation ledger／closure。每个 revision 只冻结自身 cut-off 正文；post-cut 报告正文进入后继代，PASS／无 action impact 才可由精确 certificate 窄化 carry forward，其余先使未消费授权 stale 并关闭修订。每个 non-stale closed revision 只授权一个精确动作实例；禁止 skip、空 ledger 或操作者声明式 bootstrap 豁免。 | 第 1、2.5、3.1、6.3、6.5、8.1 节，阶段 0、阶段 1、阶段 11 与实施 kick-off | 0A fresh 父状态可凭 repo 外冻结正样本为绿、目标 mutants 为红，staged paths 与清单双向相等，独立回执绑定最终 identities；0B 只能加载 committed 0A kernel。PASS／无 impact report 由 exact certificate 保持当前精确 action 为绿并进入 `N+1`；漏登记 carry-forward report、`pending`／`partial` close、复用已消费 ordinal、action identity 不匹配均红；blocker／major／当前 action impact 与报告 hash 漂移立即 stale 当前授权。 |
| R7：0A 没有机械一次性 marker，控制面建立后仍可再次绕过 generation gate | 采纳并关闭计划缺陷。固定不可变 `protocol-marker.json` 与 `bootstrap-kernel/` namespace，`bootstrap_kernel_commit` 只允许父 HEAD 同时不存在 marker／kernel／latest／closed generation；marker 绑定 protocol version、父 HEAD、bootstrap-assets blob 和非 marker kernel sorted path＋blob identity，独立回执再绑定 marker blob与候选 tree。staged allowlist 固定为 marker＋bootstrap-assets literals，失败码 40～47 稳定区分八类拒绝。marker 成功后永不修改，所有 kernel 升级改走普通 versioned migration generation。 | 第 1、2.5、3.1、6.3、6.5 节，阶段 0、阶段 11 与实施 kick-off | fresh 父状态＋精确 allowlist 为绿；原 bytes 或换 bytes 重跑均为 `40/bootstrap_marker_exists`；marker 缺失但 kernel／latest／closed generation 存在分别为 41／42／43；allowlist／kernel identity／fixture identity／receipt 缺陷分别为 44～47，全部不产生 commit。后续 kernel version 只能由 latest non-stale generation 的精确 `docs_commit` action 推进。 |
| R7：post-cut 报告无论 verdict 都延迟到 N+1，major／blocker 或当前 action impact 也不能阻断旧授权 | 采纳并关闭计划缺陷。generation 身份扩展为 `<ordinal, revision>`；报告正文仍按 cut-off 进入后继 inventory，但 verdict、action／topic impacts 与 hash 对尚未消费的授权立即生效。closure review certificate 精确绑定 report hash、subject generation、canonical closure payload、唯一 action 与 observed post-cut set；只有 PASS、0 blocker／0 major且 unresolved impacts 为空才能窄化 carry forward。其余报告或任一 hash 漂移立即使旧 revision／action stale，必须先关闭同 ordinal revision或下一 generation，不能先消费旧授权。 | 第 1、2.5、6.5、8.1 节，阶段 0、阶段 1、阶段 11、非功能要求与实施 kick-off | PASS＋exact certificate＋empty unresolved impacts 时当前精确 action 为绿且报告进入后继代；blocker、major、任意 verdict 的当前 action／topic impact、伪造 subject、遗漏 impact、observed-set 不完整及 closure／certificate／report hash 漂移分别为红；修订关闭前旧 action 始终不可执行，carry-forward 报告漏入下一代也为红。 |

处置 verdict：上一轮 5 条 major、R2 剩余 1 条 major、临时报告归纳评审相关 1 条 major、merged-state 指向本计划的合同重开 major、R4 的 2 条 major、merged-state R2 的阶段 0 bootstrap／自指 major，以及 R7 的 2 条 major 均已采纳并映射到可验收的计划条款。R2 指出的三个阶段 1 派生 spec 已有显式 producer、source extract inputs、stage pathspec 和唯一 final owner，且检查扩展到全部派生产物。bridge 已冻结合同不再只靠路径或“current”自述：阶段 0B／阶段 1 必须精确验证 finalized 内容对、Acceptance → Spec 绑定和七域对账身份，非规范 Architecture 不产生行为 expected。阶段 0A 不依赖尚不存在的 ledger，但现在还由父 HEAD marker／kernel／latest／closed-generation absence gate、不可变 marker、kernel tree／blob identity、固定 allowlist 与失败码机械保证只能成功一次；后续升级只能走 versioned migration generation。临时报告正文按 cut-off 进入后继代以保持有限终止，但 verdict／action impacts／hash 不再被无条件延迟：只有精确 PASS certificate 且 unresolved impacts 为空才能窄化 carry forward，其他情况立即 stale 当前未消费授权并先关闭同 ordinal revision 或下一代。current 260807 临时矩阵不会成为永久依赖。其他协议／共用机制的未覆盖单元仍保留门控。没有改变 42 项 source owner、全部派生产物 producer、literal pathspec、其他阶段范围、identity／distillation gate 或 bridge 规范输入绑定，没有以成本、ROI 或 YAGNI 缩减功能，也没有借文档迁移替用户补做产品设计裁决。修订版仍需定向独立复评达到 0 blocker、0 major 后方可执行。

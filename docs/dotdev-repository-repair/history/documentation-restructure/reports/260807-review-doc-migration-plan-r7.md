# 文档重组计划独立定向终审 R7

- **评审范围**：稳定快照 `docs/agents/documentation-restructure/plan.md`，SHA-256 `eba0666f1cd25b36edb2371c12b1eee35f21cd06a67405a1dd126a549b2bfeca`，分支 `main`，`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`。本轮只复核 `docs/tmp/260807-review-docs-merged-r2.md` 的 M3 关闭条件，并以 `docs/tmp/260807-review-doc-bootstrap-protocol.md` 的 8 条必要不变量为反例清单；同时回归确认 R4 两项 major 的 identity／distillation gate，以及 42 项 source owner、required-output producer 与 literal pathspec 未退化。未重新评审其他计划内容或 42 份源文档正文。
- **总体 verdict**：**修复 major 后可进入；Plan 当前不可提交执行。** 0A／0B 拆分、cut-off、无自哈希 payload／closure、六类 action gate 与 N+1 延迟已建立，但 0A 仍缺少机械的一次性信任根判据，且 post-cut 独立评审无论 verdict 都保持 generation N 的已绑定动作有效；两条路径都会让错误状态通过。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对视角

- 每次 shell 调用均在同一调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`，并在任何读取或写入证据前断言 Plan SHA-256 精确等于 `eba0666f1cd25b36edb2371c12b1eee35f21cd06a67405a1dd126a549b2bfeca`。
- 完整通读 current Plan、merged-state R2、bootstrap 协议预审、R4、R5 与 R6；逐项对账 0A／0B staged allowlist、receipt、cut-off、inventory／identity／ledger／closure、latest closed、六类 action、N+1 归纳和正反控制条款。
- 用 Plan 第 5.4 节机器解析、Python `Path.rglob()` 与 `git ls-files` 三个载体对账 `docs/2604-rewrite/**/*.md`：同一 HEAD／worktree 口径下三者均为 42 项且集合双向相等；42 个 source 与 42 个 canonical destination 分别唯一，全部 `extract phase ≤ final move phase`，第 5.4 节 42 行与 R6 所绑定的 index 快照逐行相同。
- R4 identity gate 的合同未回归：Plan 仍冻结 Spec `FINALIZED@a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`、Acceptance `FINALIZED_ACCEPTANCE_ORACLE@31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091`、Acceptance → Spec 绑定与七域对账身份，并要求阶段 0B／1 漂移时 fail closed。现场 Spec 仍匹配冻结 hash；现场 Acceptance 为 `19635e04886052fa2c2c98e42aab1c87c23c1fb9c8935753201928eaa8463498`，不匹配冻结 hash，因此按 Plan 自身规则应停止 bridge 相关执行。这是 identity gate 应拒绝的输入漂移，不是把新 bytes 自动采纳为规范输入的理由。
- R4 distillation gate 的六类 action 集合未回归：`docs_commit`、`phase_advance`、`product_replay`、`archive_cleanup`、`worktree_cleanup`、`user_ruling` 均要求 exact action／subject identity、latest closed generation、`covered` 正式落点和有效 anchor；`pending`／`partial`、漏登记、落回 `docs/tmp/**`、closure hash 漂移与非 latest 均有红色 fixture 要求。
- `git diff --check -- docs/agents/documentation-restructure/plan.md` 通过；报告写入前确认目标路径不存在。

### 第一人称执行视角

- 从空 verification 目录模拟 0A：冻结 repo 外 fixture → 校验 staged paths 与 `bootstrap-assets.txt` 精确相等 → 取得绑定候选 hashes 的独立 0／0 receipt → receipt 不进入 staged candidate → 提交 0A。该路径已消除“receipt 必须被自身哈希覆盖”的直接自指，但执行相同 bootstrap gate 第二次时没有协议 marker／父 HEAD／已有 generation 判据阻断。
- 模拟 0B：只加载已提交 0A checker → 冻结 generation 0 cut-off → 生成 inventory／identity／ledger → 生成排除 closure／index 的 staged payload manifest → closure 绑定 payload hash → index 绑定 closure hash → 执行精确绑定的 `docs_commit`。payload／closure／index 的哈希方向无直接环，0B 可以有限终止。
- 模拟一般 generation N：关闭 N 并绑定动作 A → cut-off 后产生对 checker／ledger 的独立评审报告。Plan 明确要求该报告只进入 N+1，同时 N 与动作 A 仍为绿；即使报告 verdict 为 major 或 blocker，current 条款也没有使尚未消费的 A stale。只有 A 之后的下一受管动作被迫关闭 N+1，故错误的控制面仍可先执行一次 A。
- 模拟 R4 六类 action：相关报告为 `covered` 且 anchor 有效才能通行；`pending`／`partial`、漏登记、action identity 不匹配、非 latest 或 closure hash 漂移均失败。该部分判别方向同时覆盖正确状态可通过与错误状态被拒绝。
- 模拟阶段 1 的三份派生 spec：producer、source extract input、literal stage pathspec 与 final owner 均保持阶段 1，且不得进入阶段 2～11 pathspec；未发现 R4 后修订破坏 42 项 owner／producer／pathspec。

## 事实性发现

### [major] `docs/agents/documentation-restructure/plan.md:84,308-310,319,323,661` — 0A receipt 已不再直接自指，但 bootstrap gate 没有机械的一次性 marker，已建立控制面后仍可再次绕过 generation gate

**问题**：Plan 把 0A 定义成“与 generation gate 不同且路径固定的构建步骤”，并以 staged allowlist、repo 外冻结 fixture 与独立 0／0 receipt 约束内容；但没有要求父 HEAD 中不存在 protocol marker／closed generation／latest pointer，也没有规定 0A 成功后写入并检查不可重复的 kernel identity。当前 bootstrap 反 fixture 只覆盖 staged path 越界、fixture hash 漂移和 skip／空 ledger，没有覆盖“0A 已成功后再次执行 0A”。

**证据或失败场景**：先合法提交 0A，再修改 checker／schema／fixtures，使 staged paths 仍精确等于 `bootstrap-assets.txt`，重新冻结 repo 外 fixture并取得新的独立 0／0 receipt。因为 0A 明确不调用 generation checker，且没有 committed marker／父状态判据，第二次调用仍满足 current Plan 的全部机械门，从而在 generation 0 已存在或应受 N+1 管理时再次走 bootstrap 通道。此路径不是“操作者声明首次运行”，但效果等同于可重复的 bootstrap 豁免。

**修复建议**：让 0A commit 写入固定 protocol marker／kernel identity，并要求 0A checker机械验证父 HEAD 中不存在该 marker、任何 closed generation和 latest pointer；marker 一旦存在，重复 0A 必须非零退出。为“空状态首次 0A 为绿、成功后原样或换 bytes 重复 0A 为红”增加双向 fixture，并明确 0B／generation 0 完成后所有 checker／schema 修订都只能走普通 generation 控制面。

### [major] `docs/agents/documentation-restructure/plan.md:82-83,294,320,323,663,685` — current generation 的独立评审报告无条件延迟到 N+1，major／blocker verdict 也不能阻断 N 尚未消费的授权动作

**问题**：Plan 正确切断了“评审 N → 回写 N → 再评审 N”的哈希闭环，但把所有 post-cut checker／ledger 评审报告一律视为 N+1 输入，并把“generation N 与其已绑定动作仍为绿”写成正控制。该规则没有区分允许关闭的 PASS receipt 与指出 major／blocker／未处置 action impact 的评审报告，也没有 closure certificate 将 review verdict、subject generation identity 和 carry-forward 义务机械绑定。

**证据或失败场景**：关闭 N 并绑定 `docs_commit` A，随后独立评审发现 N 的 checker 为 false-green 并给出 major。报告在 cut-off 后产生，按 `plan.md:82,294,320` 只令 N+1 dirty，不反向撤销 N 或 A；`plan.md:320` 还要求 A 保持为绿。执行者因此可先消费错误 checker 授权的 A，再在下一受管动作前处理 major。现有“下一动作必须关闭 N+1”只保护 A 之后的动作，未保护这份评审实际评审的 A／N。

**修复建议**：把 closure review 作为关闭 N 的 certificate 输入而不是普通的无条件 post-cut 报告：certificate 精确绑定 review 路径＋hash、`subject_generation_id=N`、verdict 与 unresolved action impacts；只有 0 blocker、0 major且无未处置 action impact 才能关闭 N／消费 A。该报告正文仍强制进入 N+1 ledger，以一代延迟保留归纳义务；但 major／blocker、hash 漂移、subject 不匹配或未处置 action impact 必须使 N／A 失败。正反 fixture应分别覆盖 PASS review 关闭 N 并 carry forward、major／blocker review 不得关闭或执行 A、N+1 漏纳 PASS receipt、以及伪造 review subject／hash。

## 已确认关闭或未回归的定向条件

- **0A receipt 直接自指**：已关闭。receipt 不进入 0A staged paths，只绑定最终候选 asset hashes，并由 0B generation 0 正式登记；候选 bytes 不需要包含其评审报告自身。
- **0B 哈希闭环与有限终止**：已关闭。staged payload manifest 排除本代 closure 与 index，closure 只绑定 payload manifest hash，index 只绑定 closure hash；没有文件直接或间接哈希自身。
- **current generation review 进入 N+1**：路径已建立，但 verdict 语义未闭合，构成本轮第二条 major。报告身份和归纳义务能进入 N+1；问题是非 PASS 报告仍不能阻断它所评审的 N／动作。
- **R4 identity gate**：设计未回归，并现场正确暴露 Acceptance bytes 已漂移。恢复必须按 Plan 先完成新规范对账、独立复评和验证资产提交，不能只刷新 hash。
- **R4 distillation gate**：六类 action、latest closed、exact subject identity、`covered`／anchor 与 `docs/tmp` 非权威边界均保持。
- **42 owner／producer／pathspec**：未回归。42 项集合、source／destination 唯一性、extract／final move 顺序和第 5.4 节逐行内容均保持；三份阶段 1 spec 的 producer／source／pathspec／final owner 约束仍闭合。

## 主观建议

无。本轮两项均是可构造错误状态仍通过的事实性 major，不是范围或风格偏好。

## 结构怪味复核

- `plan.md:84,308-310,661` — **一次性信任根仅靠流程顺序，不靠 committed state 机械判定** — 本轮应修；否则 bootstrap 通道可重复进入。
- `plan.md:82-83,294,320` — **把评审身份归属与评审 verdict 效力合并成同一条无条件延迟规则** — 本轮应修；归属可以进入 N+1，但非 PASS verdict 必须立即阻断被评审 subject。
- 扫描范围：M3 的 0A／0B、cut-off、generation identity／closure、review carry-forward、latest action、六类 action fixtures，以及 R4 identity／distillation gate和第 5.4 节 42 项映射。除上述两处外，未发现新的定向结构怪味。

## 结论

稳定快照 `eba0666f1cd25b36edb2371c12b1eee35f21cd06a67405a1dd126a549b2bfeca` 的定向终审结果为 **0 blocker、2 major、0 minor**。R4 两项 major 的 gate 设计与 42 项 owner／producer／pathspec 均未回归；0A receipt 的直接自指和 0B 的 payload／closure 哈希环已经关闭。但 0A 仍可在既有控制面后重复执行，且 current generation 的 major／blocker 评审报告仍可被无条件推迟到 N+1、让 N 的尚未消费动作先执行。**Plan 当前不可提交执行；修复这两项并对新 bytes 定向复评达到 0 blocker、0 major 后，方可明确判定 Plan 可提交执行。**

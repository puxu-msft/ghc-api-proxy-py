# 文档治理 bootstrap generation 设计预审

- **评审范围**：只读预审 `main@ed77c9d191df81c451c25161420515cca52ce6a4` 的 current `docs/agents/documentation-restructure/plan.md`，以及 `docs/tmp/260807-review-docs-merged-r2.md` 的第 3 条 major；不重做全计划，不修改 Plan，也不等待 planner。本报告只给 planner 修订后复评所需的 bootstrap generation 必要不变量，**不是 normative 设计或执行授权**。
- **输入身份**：Plan SHA-256 为 `53f7a02c936801e5f68fb67701449521941f2599c1d0092a8cf11eea1a6190ad`，R2 报告 SHA-256 为 `b62711635cdcfd34adcf406073bae9ef2f156e4378b1a999920b7e0e0dc7c2d9`；二者均在上述 HEAD、路径口径下由 `sha256sum` 与 Python `hashlib.sha256` 交叉复核。
- **总体 verdict**：**修复 major 后可进入**。R2 M3 指出的 bootstrap／自指缺口在 current Plan 中仍存在；以下协议给出可机械终止的最小闭环，但须由 planner 写回 Plan 并接受定向独立复评后，才可成为执行合同。
- **blocker 数**：0。
- **major 数**：1。
- **双视角覆盖证据——机械核对**：对账 Plan 的全动作 gate（`plan.md:287-289`）、阶段 0 首次生成 checker／ledger（`plan.md:293-317`）与 kick-off（`plan.md:641-643`），并逐步验证“已提交 checker”在首次提交前不可调用，以及实际 `docs/tmp/*.md` 双向集合会被评审新报告改变。
- **双视角覆盖证据——第一人称执行**：分别模拟从空验证目录执行 0A、执行 0B、关闭一般 generation N、评审该 generation、将评审报告纳入 N+1，以及在 N 与 N+1 之间尝试 `docs_commit`、`phase_advance` 和清理动作；主路径在有限步骤内结束，漏报告、改报告、伪造代链和提前执行动作均有确定失败点。

## 事实性发现

### [major] `docs/agents/documentation-restructure/plan.md:287-317,643` — 首次 checker 提交与“全部实际 tmp 报告”闭包没有代际边界

current Plan 同时要求首次阶段 0 提交使用尚未提交的 checker，并要求把评审阶段 0 资产所产生的新报告纳入同一份被评审 ledger。前者没有既存信任根，后者要求被评对象包含对自身的评审结果；两者都不能靠多跑一次评审收敛。结构怪味为**控制面 bootstrap 与受控数据快照职责混合，并把动态报告全集误写成同代闭包**。处置应是本轮修复：拆出 0A／0B，冻结报告 cut-off，并让 closure review 单向进入后继代。

## 必要不变量

### 1. 0A 只建立一次性 bootstrap kernel，不建立 current generation

0A 的 action type 固定为 `bootstrap_kernel_commit`，只允许在父 HEAD 中不存在 protocol marker、closed generation 和 latest pointer 时执行一次。其 staged allowlist 只能包含 schema、checker、generation builder、固定正反 fixtures、执行说明和机器可读 `bootstrap-review` receipt；不得包含 current manifest、current report inventory／ledger、topic 文档、迁移正文或任何“当前结论”。候选 checker 必须先对固定 fixtures 做双向控制，再校验 staged paths 与 allowlist 精确相等，并校验独立评审 receipt 绑定 staged blob identity 且 verdict 为 `0 blocker, 0 major`。0A 是唯一允许没有 `latest_closed_generation` 的 kernel 提交；marker 一旦存在，重复 0A 必须非零退出。

### 2. 0B 只用已提交 0A 关闭 generation 0，不混入领域动作

0B 的 action type 固定为 `bootstrap_generation_commit`，前置条件是 HEAD 直接或经允许的只读提交后代包含唯一 0A kernel，且运行的 checker blob identity 与 0A marker 一致。0B 才生成 current manifest、pathspec、首份 report ledger、generation 0 payload、closure certificate 和 latest pointer；staged allowlist 只允许这些控制面数据，不得同时建立 banner、活文档或移动源文件。已提交的 0A checker必须验证 0B candidate、closure review 与 staged bytes 精确相等。`bootstrap_generation_commit` 仅允许 ordinal `0` 且只允许一次；generation 0 关闭后，任何普通动作都不得再走 0A／0B 路径。

### 3. cut-off 是不可变的报告内容集合，不是时间或“扫描过”的自述

每代 N 在开始 closure review **之前**生成 `report-inventory-N`，按 UTF-8 路径字节排序记录 cut-off 时实际 `docs/tmp/*.md` 的每个 `(report_path, sha256)`，并记录扫描 root 与 base HEAD；inventory 的精确 bytes 进入 generation payload。cut-off 后新增的唯一报告路径归 N+1；已收录路径若改 bytes 或消失属于 immutable-input violation，不能伪装成 N+1 新版本，相关 closure／action 必须失败。N 的 ledger 只允许覆盖 inventory N 的精确集合，不使用 mtime、创建日或墙钟时间判断归属。

### 4. generation identity、父链与 latest 都必须由内容机械决定

每代使用分离文件，避免自哈希：`generation-N.payload.json` 以冻结的 canonical bytes 编码 `schema_version`、`ordinal`、`parent_generation_id`、`base_head`、`kernel_identity`、`report_inventory_sha256`、`ledger_sha256` 和必要正式落点摘要；`generation_id = sha256(payload bytes)`。closure certificate 另行绑定 `generation_id`、closure review 报告路径与 hash、机器可读 verdict 和 unresolved action impacts；它不回写 payload。checker 必须证明 ordinal 连续递增、parent 精确指向前一 closed generation、无 fork／重号／缺代、certificate 与 subject bytes 相符，且 `latest` 精确指向唯一最高 closed generation；手改 pointer 不能制造“最新代”。

### 5. closure review 报告属于 N+1，但以 certificate 关闭 N

reviewer 评审的是 cut-off 后冻结的 generation N candidate；其报告必然不在 inventory N。若报告给出允许关闭的 verdict，closure certificate 记录该报告的路径、hash、`subject_generation_id=N` 与 `carry_forward_to=N+1`，从而关闭 N，而不把报告塞回 N 的 payload／ledger。N+1 的 inventory 与 ledger 必须包含并归纳该精确报告；遗漏、hash 不同、subject 不同或跳到 N+2 都失败。若 closure review 有 blocker、major 或未处置的 action impact，则 N 不得关闭；修订后重新冻结 candidate 与 cut-off，同 ordinal 重试，失败评审报告作为普通输入进入新的 candidate，不递增 closed-generation ordinal。

### 6. 正常动作必须消费 latest closed generation，只有控制面 closure 有窄例外

`docs_commit`、`phase_advance`、`product_replay`、`archive_cleanup`、`worktree_cleanup`、`user_ruling` 和完成声明都必须由 committed 0A checker解析线性代链，消费唯一 `latest_closed_generation`，并对 action type／topic 运行其 ledger matrix；调用方不得传入较旧 generation。唯一例外是 0A、0B，以及 `generation_close`：后者只可从 latest closed N 构造并关闭 N+1，且 staged paths 只能是 generation 控制面 allowlist，不能夹带被 gate 的领域动作。没有 generation 0 时，所有普通动作确定失败。

### 7. post-cut 报告使相关动作变 stale，但本代 PASS closure review 有严格 carry-forward 豁免

latest closed N 之后出现任何未收录报告时，checker 先分类：只有被 N 的 closure certificate 精确绑定、verdict 允许关闭、`subject_generation_id=N`、`carry_forward_to=N+1` 且 unresolved action impacts 为空的那一份 closure review，可在 N 与 N+1 之间作为控制面 carry-forward，不使普通动作自动失效；它仍必须在实际创建 N+1 时纳入。其他新增报告、closure review 的 hash 漂移、非允许 verdict，或声明影响当前 action／topic 的结论，都使相应普通动作 stale，必须先关闭 N+1。该豁免由 certificate 字段与内容 hash 判定，不能靠文件名含 `review` 或执行者声称“只是评审自身”判定。

### 8. 正负控制必须证明可启动、可前进、可终止，也能拒绝两类假结果

正控制至少覆盖：空状态下仅 0A 可成功且重复 0A 失败；已提交 0A 可关闭 0B／generation 0；generation N 的 PASS closure review 被 certificate 挂起后普通动作可按第 7 条继续；创建 N+1 时该报告被精确纳入；无新 action-impacting 报告时一次 normal action 在有限调用内成功。负控制至少覆盖：generation 0 前执行普通 `docs_commit`；0A staged 集合夹带 current ledger；cut-off 后修改／删除已收录报告；N+1 漏掉 N 的 closure review；伪造 parent、重号、fork 或仅手改 latest；带 blocker／major／未处置 action impact 的 review 仍关闭；新增相关 post-cut 报告后仍用 N 执行动作。每个反例都须确认失败来自目标不变量，并为每个 gate 保留正确样本，防止“永远拒绝”的 false-red。

## 机械终止性

对任一 candidate N，inventory 在 review 前冻结且有限；review 报告不回写 N，只产生一个 certificate 输入和一个 N+1 carry-forward obligation，因此关闭 N 不依赖关闭 N+1。失败 review 只重试未关闭的同一 ordinal；PASS review 关闭 N。普通动作最多需要先关闭由**非豁免、action-impacting** post-cut 报告触发的下一代；本代 PASS closure review 自身不会再次迫使立即关闭下一代。由此切断“评审 N → 改 N → 再评审 N”的结构性自指，同时保留下一代对评审报告的正式归纳责任。

## 主观建议

未提出范围性建议。内部替代方案“一次提交加 bootstrap 豁免”无法机械区分首次合法调用与以后绕过，故不推荐；判据判别力由第 8 条双向控制约束；generation 链、SHA-256 与 Git blob／tree identity 可直接使用现有 Git 和语言标准库，不需要为本协议另造共识算法或引入新的状态数据库。

## 复评入口

planner 修订后，复评只需检查：0A／0B 是否按上述边界拆开；cut-off 与 generation payload／certificate 是否无自引用；closure review 是否由 N certificate 绑定且强制进入 N+1；普通 action 与 `generation_close` 的权限是否互斥；第 8 条正负 fixtures 是否同时存在。若五项均有可执行字段、失败码和 staged allowlist，且 current Plan 不再保留与之冲突的“一次性阶段 0 提交”措辞，R2 M3 才可关闭。

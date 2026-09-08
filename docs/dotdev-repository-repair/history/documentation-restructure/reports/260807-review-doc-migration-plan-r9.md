# 文档重组 living Plan 独立定向复评 R9

- **评审范围**：主树 current `docs/agents/documentation-restructure/plan.md`，稳定 SHA-256 `054087655a539ad95babb2a15f918bc0467aa0fd6726d6e17569169f31f12aee`。评审前已在两次独立、均绑定物理 root `/home/xp/src/ghc-api-proxy-py`、分支 `main`、`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4` 的 shell 调用中，分别以 `sha256sum` 与 Python `hashlib.sha256` 取得相同 hash。本轮完整通读 current Plan 与 R8，定向复核 current carrier identities、0A marker、post-cut stale、42 owner 和 distillation 截止；未重新评审 42 份源文档正文，未执行迁移或产品验收。
- **总体 verdict**：**可进入下一阶段。current living Plan 可继续执行。** 本轮为 0 blocker、0 major；**计划评审不是文档迁移收口**，也不替代阶段 0A／0B、阶段 1～11、产品实现、合并态验收或各受管动作自己的 gate 与独立评审。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对视角

- 稳定身份：两种 hash 实现连续得到 Plan `054087655a539ad95babb2a15f918bc0467aa0fd6726d6e17569169f31f12aee`。R8 绑定同一 Plan bytes 且 verdict 为 0 blocker、0 major，本轮没有把旧 verdict 外推到不同 Plan bytes。
- current carrier：Spec 为 `FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；Acceptance 为 `FINALIZED_ACCEPTANCE_ORACLE@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。两者均经 `sha256sum` 与 Python 交叉复核。Acceptance `:7` 绑定同一 Spec，`:27-39` 保留 route、request、response、buffering、retry、lifecycle、limits 七域 `POLICY-MANIFEST-v1` 对账；Plan `:64-69,320,667` 精确绑定这组 identities，Architecture 仍不是行为 oracle。
- 0A：Plan `:85-86,312,321,663,688` 保留固定 marker／kernel／latest／closed-generation absence gate、kernel identities、失败码 40～47，以及首次成功后原 bytes／换 bytes 重入均返回 `40/bootstrap_marker_exists` 的要求。后续升级只能走普通 versioned migration generation。
- post-cut stale：Plan `:81-84,296,321-322,689` 仍要求 blocker、major、当前 action／topic impact、subject／impact 缺失或 hash 漂移立即 stale 未消费授权；旧授权不得先消费。只有 PASS、0／0、精确绑定且 `unresolved_action_impacts=[]` 才能窄化 carry-forward。
- 42 owner：从 Plan 第 5.4 节机器解析 42 行，与 Python `Path.rglob()` 及 `git ls-files` 三路对账，均为同一 42 项；42 个 source 与 42 个 canonical destination 各自唯一，全部 `extract phase ≤ final move phase`。
- distillation 截止：Plan `:84,296,321,375,570,585,686` 仍把截止定义为最早相关受管动作而非自然日；六类 action identity 固定，`partial`／`pending` 永不通行，post-cut impact 对未消费动作立即生效。
- `git diff --check` 对 current Plan、Spec、Acceptance 与 R8 通过。

### 第一人称执行视角

- 0A 正路径：父 HEAD 四类 footprint 均不存在时，按 literal allowlist 暂存 marker＋kernel，校验 repo 外冻结 fixtures、kernel identities 与独立 0／0 receipt，可形成唯一 0A commit，不会因尚不存在的 ledger 而 false-red。
- 0A 反路径：首次成功后用原 bytes 或换 bytes 重入，均先由 marker 以 40 拒绝；marker 异常缺失时仍由 kernel／latest／closed-generation footprints 以 41／42／43 拒绝，不能借升级重开 bootstrap。
- post-cut 正路径：先冻结人类可读 report，再从固定 bytes 生成 certificate；仅 PASS 0／0、subject／payload／action／observed-set 全匹配且无 unresolved impact 时，当前精确 action 继续。report 仍进入后继 inventory，不形成永久豁免。
- post-cut 反路径：注入 major、blocker、当前 action impact、hash 漂移、subject mismatch、impact 缺失或 observed-set 漏项，均立即 stale 当前未消费授权，必须先关闭同 ordinal revision 或下一 generation。
- distillation 路径：docs commit 与 phase advance 是两个动作实例，各自需要后继 ordinal 与精确 subject identity；相关报告仍为 `pending`／`partial`、正式落点仍在 `docs/tmp/**` 或 anchor 不可解析时均不能通行。无关 topic 且已 covered 的结论不造成 false-red，但仍进入后继 ledger。
- carrier 漂移路径：阶段 0B 与阶段 1 bridge 工作前均重算两份 carrier 的 hash、状态、绑定及七域 identity；任一漂移都 fail closed，不能只刷新 hash或提升非规范 Architecture。

## 事实性发现

未发现问题。R8 后同步的 current Spec／Acceptance identities 已正确反映在 Plan；0A marker、post-cut stale 修订、42 owner 与 distillation 动作截止均未回归。

## 回归结论

- **current identities**：通过。Spec `FINALIZED@5e362822…`；Acceptance `FINALIZED_ACCEPTANCE_ORACLE@224b020d…`，绑定同一 Spec 与七域 policy reconciliation。
- **0A marker**：通过。fresh 正路径可执行，成功后原 bytes／换 bytes 重入均被机械拒绝。
- **post-cut stale**：通过。除精确 PASS 0／0 无 impact 外，旧授权不能先消费。
- **42 owner**：通过。Plan、文件系统与 Git tracked set 均为同一 42 项，source／destination 唯一且阶段顺序有效。
- **distillation 截止**：通过。截止仍绑定最早相关动作，`pending`／`partial` 不通行。

## 结构怪味扫描

扫描了 marker／kernel identity 重复定义、bootstrap／generation 职责混淆、report 正文归属／verdict 生效混写、certificate／closure 自指、source owner／required-output producer 错位，以及自然日／动作序列双截止。未发现新的定向结构怪味。

## 主观建议

无。

## 结论

current Plan `054087655a539ad95babb2a15f918bc0467aa0fd6726d6e17569169f31f12aee` 的 R9 结果为 **0 blocker、0 major、0 minor**。**living Plan 可继续执行。** 该结论不是迁移收口；Plan、Spec、Acceptance 或 action subject bytes 漂移后，本报告不得覆盖新身份。

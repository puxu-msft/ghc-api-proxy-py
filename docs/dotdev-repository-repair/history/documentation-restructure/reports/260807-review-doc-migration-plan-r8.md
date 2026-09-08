# 文档重组计划独立定向复评 R8

- **评审范围**：current `docs/agents/documentation-restructure/plan.md`，SHA-256 `054087655a539ad95babb2a15f918bc0467aa0fd6726d6e17569169f31f12aee`；先现场读取并复核 `docs/tmp/260807-review-doc-migration-plan-r7.md`，SHA-256 `ae72f79f373e926a704016dc3b0ea1078b106585a85b09a76a433d195cad74e1`。本轮只复核 R7 的两项 major：0A 一次性 protocol marker／kernel identity／重复调用拒绝，以及 post-cut verdict／action impact／hash 漂移的即时 stale 与 PASS 0／0 无 impact certificate 窄化 carry-forward；同时回归 42 项 source owner 和 carrier 重裁后的 current Spec／Acceptance 内容身份。未重新评审计划其他内容或 42 份源文档正文。
- **总体 verdict**：**可进入下一阶段。Plan 可继续执行，并保持 living plan。** R7 两项 major 均已关闭；current Plan 达到 0 blocker、0 major。后续实施仍须逐阶段消费本 Plan 定义的 current identity、generation、certificate 与 action gate；“可继续执行”不把计划快照冻结成不可更新文档，也不替代实施阶段自己的验证和独立评审。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **证据基线**：每次 shell 调用均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、`HEAD=ed77c9d191df81c451c25161420515cca52ce6a4`；四个现场 SHA-256 均以 `sha256sum` 与 Python `hashlib.sha256` 两种不同原理交叉复核。

## 双视角覆盖证据

### 机械核对视角

- 完整通读 current Plan 与 R7，逐项对账 R7 两项 major 的问题、失败场景和建议修法；另检查 current Plan 相对 index 的实际修订，而不是只读取第 12 节处置自述。
- 对 0A 检查固定 marker path、固定 kernel namespace、父 HEAD 四重 absence gate、marker 对 parent／assets blob／kernel subtree tree／sorted asset blob identity 的绑定、稳定失败码 40～47、原 bytes 与换 bytes 重入拒绝，以及后续 kernel 升级只能走普通 versioned migration generation。对应落点为 `plan.md:85-86,283,294,310-312,321,325,329,663`。
- 对 post-cut 检查 `<ordinal, revision>`、review report 与 certificate 分离、certificate 对 report hash／subject generation／closure payload／唯一 action／observed set 的精确绑定、blocker／major／current action impact／hash 漂移即时 stale，以及唯一 PASS 0／0 且 `unresolved_action_impacts=[]` 的窄化 carry-forward。对应落点为 `plan.md:81-84,294-296,314,321-325,375,570,585,653,657,665,689`。
- 用第 5.4 节机器解析、Python `Path.rglob()` 与 `git ls-files` 三路回归 42 项 owner：三者均为同一 42 项集合；source 与 canonical destination 各自唯一，全部 `extract phase ≤ final move phase`。本轮 R7 修订未改变 source owner、destination 或阶段顺序。
- carrier 重裁后的 current Spec SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，状态为 `FINALIZED`；current Acceptance SHA-256 为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`，状态为 `FINALIZED_ACCEPTANCE_ORACLE`。Plan `:64-69,320,667` 绑定这组 current identities；Acceptance 内仍绑定同一 Spec identity并保留七域 `POLICY-MANIFEST-v1` 对账。本轮没有沿用 R7 所见的旧 carrier hash，也没有把 Architecture 提升为行为 oracle。
- `git diff --check` 对 current Plan、current Spec、current Acceptance 与 R7 均通过；写入前确认 R8 目标路径不存在。

### 第一人称执行视角

- **0A 正路径**：从父 HEAD 同时不存在 marker、kernel namespace、latest pointer 与 closed generation 开始，按 literal allowlist 暂存 marker＋kernel，校验 repo 外冻结 fixtures，构造 marker 的 parent／assets／subtree／sorted blob identity，取得绑定 marker blob、kernel identity 与候选 repository tree identity 的独立 0／0 receipt，然后提交。该流程有明确可满足的绿路径，没有把一次性门写成永远无法通过的 false-red。
- **0A 反路径**：成功后分别以原 bytes 和变更 kernel bytes 再调用 `bootstrap_kernel_commit`。父 HEAD 已存在 marker，两条路径都必须在写 commit 前以 `40/bootstrap_marker_exists` 确定失败；即使 marker 缺失，kernel／latest／closed generation footprint 仍分别以 41／42／43 拒绝。checker／schema／fixture 升级不能删除或改写 marker 来重开 0A，只能消费普通 generation 的精确 `docs_commit` action。R7 的重复 bootstrap 反例已被机械封死。
- **post-cut 唯一正路径**：generation `<N,R>` closure payload 形成后，人类可读 review report 先冻结，checker 再从其 frozen bytes 生成独立 certificate；仅当 verdict 为 PASS、blocker 0、major 0、subject／payload／action／observed set／hash 全部精确匹配且 `unresolved_action_impacts=[]` 时，当前精确 action 继续为绿，report 与 certificate 正文进入后继 inventory。该路径保持有限终止且允许真正无影响的 review 通过。
- **post-cut 反路径**：分别注入 blocker、major、任意 verdict 的 current action／action type／subject／topic impact、report hash 漂移、subject generation 不匹配、impact 字段缺失和 observed-set 缺口；current revision 与尚未消费 action 均立即 stale，必须先关闭同 ordinal revision 或下一 generation，旧授权不得先消费。R7 的“非 PASS 报告仍可让旧动作先执行”反例不再成立。
- **动作消费后路径**：同 ordinal 不得修订或复用，下一受管动作必须使用后继 ordinal；carry-forward report 若在后继 inventory／ledger 漏登记或仍为 `pending`／`partial`，后继动作失败。因此窄化 carry-forward 只解决当前精确动作的自指终止，不形成永久豁免。

## 事实性发现

未发现问题。R7 两项 major 均已形成正文协议、执行顺序、稳定失败合同与双向 fixture 要求，不是只在处置表中声明“已关闭”。

## 已确认关闭的 R7 major

### 0A 一次性 protocol marker 与 kernel identity

**结论：已关闭。** `protocol-marker.json` 位于 kernel namespace 外，避免 marker 自哈希；marker 同时绑定父 HEAD、`bootstrap-assets.txt` blob、kernel subtree tree OID 与 sorted non-marker asset path＋blob identity。父 HEAD 的 marker／kernel／latest／closed-generation 四重 absence gate 保证 fresh 0A 有唯一机械入口；marker 一旦存在，原 bytes 或换 bytes 的重复调用都必须先于 commit 确定失败。稳定码 40～47与对应正反 fixtures把首次成功、重复拒绝和各类 identity failure 分开，后续升级只能进入普通 versioned migration generation。

### Post-cut 即时 stale 与窄化 carry-forward

**结论：已关闭。** Plan 已把“report 正文属于哪个 generation”与“report verdict 何时影响当前授权”分离：正文按 cut-off 进入后继 inventory，但 blocker／major、当前 action impact、subject／impact 缺陷及任一 report／certificate hash 漂移对未消费授权立即生效。只有独立 certificate 精确证明 PASS、0 blocker、0 major、完整 observed set 且无 unresolved action impact 时，才允许当前一个精确 action carry forward；report 与 certificate 仍须进入后继 inventory，不能绕过下一动作的归纳义务。

## 回归结论

- **42 owner**：通过。计划表、工作树 `Path.rglob()` 与 Git tracked set 在 `main@ed77c9d…` 口径下均为同一 42 项；source／destination 唯一，extract／final move 顺序有效。
- **current Spec identity**：通过。`FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。
- **current Acceptance identity**：通过。`FINALIZED_ACCEPTANCE_ORACLE@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`，并绑定同一 current Spec 与七域 policy reconciliation。
- **结构怪味定向扫描**：扫描 0A 身份发布与重入门、generation／revision 状态职责、report／certificate／closure 哈希方向、post-cut action gate、42 项 owner 及 normative-input identity。未发现 R7 修订引入新的定向结构怪味；marker 与 kernel identity、report 归属与 verdict 效力、closure payload 与 certificate identity 均已分责。

## 主观建议

无。本轮范围内没有需要以偏好替代事实判据的建议。

## 结论

current Plan `054087655a539ad95babb2a15f918bc0467aa0fd6726d6e17569169f31f12aee` 的定向复评结果为 **0 blocker、0 major、0 minor**。R7 两项 major 均已关闭，42 owner 与 carrier 重裁后的 current Spec／Acceptance identities 未回归。**Plan 可继续执行，并保持 living plan；后续若 Plan、Spec、Acceptance、review report、certificate 或 action subject identity 漂移，仍必须按其自身 gate 重新判定，不沿用本报告覆盖新 bytes。**

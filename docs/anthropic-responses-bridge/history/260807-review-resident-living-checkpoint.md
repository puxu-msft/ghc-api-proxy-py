# Resident living checkpoint 联合定向复评

- **评审范围**：联合复评 `docs/agents/anthropic-responses-bridge/implementation.md` SHA-256 `7f6db92600e46ca2ff12a01122797cb7c112f09dd320e79b1fb1b4653faa93d0`、`docs/agents/service-cutover/readiness.md` SHA-256 `e4ccfbb85a987f7cf79d701e948f6933e05bfdc772f2d87284fcd36f101cf45b`，以及主树 `main@29c0ce3230181a113363eb398dfa24d8e41a9012`。范围只核对 headers-before Responses network retry与exhaustion永久回归门已进入main、resident-byte最小primitive已进入main并归档、current main 611项tests／Ruff／Pyright、production quota接线仍未完成且Responses stream reservation后继线刚建立、Backup smoke R3的祖先边界、真实socket partial-write与真实manager／cgroup仍未验证、`LIVING／UNVERIFIED／NO_CUTOVER`及Readiness 43行口径。不重新评审代码，不执行服务、manager、端口、部署或cutover操作；唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段，可形成 living checkpoint。** 两份指定内容身份未发现 blocker、major或minor；按用户门槛，0 major可checkpoint。该checkpoint只冻结current living状态，不表示Implementation收口、production quota接线完成、完整产品`PASS`或部署／cutover获授权。
- **Blocker 数**：0。
- **Major 数**：0。
- **Minor 数**：0。

## 双视角覆盖证据

### 机械核对

- 在同一次主树绑定调用中验证物理仓库根、branch `main`与`HEAD == refs/heads/main == 29c0ce3230181a113363eb398dfa24d8e41a9012`。两份文档的 SHA-256分别以`sha256sum`与Python `hashlib.sha256`交叉计算，均精确命中本报告绑定身份。
- Git祖先检查确认stream request facts `d903d726baf3f15bf46ddf17384564fee154ed6a`、network retry `fb5c027b38cc72910dd4495979a26a57fbbaa99b`与exhaustion test `080105b54614e1320a5c193d7206dcaa584c9b41`均为current main祖先；提交主题分别对应stream request facts、Responses headers前连接失败retry及retry exhaustion回归测试。
- Archive ref对象级核对确认`archive/260807-responses-network-retry`精确指向reviewed source `584e63ba3724a7b6999d2163266d3daf8e731221`，`archive/260807-resident-byte-budget`精确指向reviewed source `8fb6a97e97fe7db9034b1b68636bc40beaf7cec6`。Resident main复核报告又证明`main@29c0ce3…`四个结果blob与该final reviewed source一致，且限定范围为opt-in resident primitive而非production quota完整接线。
- 在exact `main@29c0ce3…`现场运行全量pytest、Ruff与Pyright：`611 passed in 15.73s`、Ruff `All checks passed!`、Pyright `0 errors, 0 warnings, 0 informations`。测试数另以`pytest --collect-only -q`摘要与独立node-id行数交叉核对，均为611；运行前后工作树porcelain指纹一致。
- 新后继worktree `/home/xp/src/ghc-api-proxy-py-reservation-wiring` 的branch为`feat/resident-budget-wiring`，HEAD仍等于`29c0ce3230181a113363eb398dfa24d8e41a9012`，相对main ahead count为0、changed paths为0、status为空。因此可准确表述为“Responses stream reservation接线新线刚建立，尚无实现增量”，不能写成production接线已完成。
- 对Readiness五组required表分别用AWK章节状态机与独立Python表解析器计数，两者均得到P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43。两份文档对`29c0ce3…`、611项门、两个archive、Backup smoke祖先、quota／partial-write／manager未验及状态词的复述一致。

### 第一人称执行模拟

- 按Implementation `docs/agents/anthropic-responses-bridge/implementation.md:263-266`执行下一步：先冻结`fb5c027… → 080105b… → 29c0ce3…`及祖先smoke边界，再从current main进入刚建立的Responses stream reservation接线后继线；不会重复实现retry／exhaustion或resident primitive，也不会把空后继线误判为已有接线成果。
- 按Readiness `docs/agents/service-cutover/readiness.md:53-59`逐项判断P0：network retry只覆盖headers形成前的窄连接失败与exhaustion，resident primitive只提供opt-in两级reservation／lease lifecycle；production stream reservation、完整request／global quota、charge-before-read、有限queue、admission、metrics／History与真实partial-write仍保持`UNVERIFIED`。正确的局部绿灯可以继续实施，错误的完整产品升级会被这些边界阻止。
- 沿Backup smoke证据链执行：R3报告精确绑定`main@d903d726…`并取得`PASS_KEY_BACKUP_PORT_SMOKE_R3`；`d903d72…`虽为current main祖先，但R3没有运行network retry、resident primitive、quota或partial-write。因此执行者只能把它用于该祖先上的scoped主路径与stream request conversion fact缺口关闭，不能外推为`29c0ce3…`运行证据。
- 沿运行态分支执行：Readiness `docs/agents/service-cutover/readiness.md:72-79,149-153`把真实user manager／cgroup保留为`BLOCKED`或未验，把真实socket partial-write保留为未验证，并要求转到可销毁VM／container或loopback fault入口；仓库611项绿灯不会触发unit安装、旧Bun停止、`4141`接管或`cc-daemon`操作。
- 沿状态升级路径执行：Implementation保持`LIVING`，完整产品保持`UNVERIFIED`，Readiness保持`NO_CUTOVER／PARTIAL`。形成本文checkpoint后只能继续最小reservation接线，不能把文档0 major解释为Implementation收口、完整Acceptance `PASS`或production cutover授权。

## 事实性发现

未发现问题。定向核对确认以下结论同时成立：

1. Network retry `fb5c027…`与exhaustion永久回归门`080105b…`已进入main；retry reviewed source由精确archive保留。
2. Resident-byte最小primitive已作为`main@29c0ce3…`进入主树并由精确archive保留；current main全量611项tests、Ruff与Pyright通过。
3. Responses stream reservation接线后继线刚建立且尚无提交或路径增量；production request／global quota与resident backpressure完整接线仍未完成。
4. Backup smoke R3只绑定祖先`d903d72…`，不得外推为retry／resident后current main、真实upstream、quota或partial-write运行证据。
5. 真实socket partial-write／delivery uncertainty与真实manager／cgroup／unit运行态仍未验证；manager当前本机证据为`BLOCKED`，不是`PASS`。
6. Implementation保持`LIVING`，完整产品保持`UNVERIFIED`，部署保持`NO_CUTOVER`；Readiness 43行口径精确成立。

## 主观建议

未提出额外主观建议。

# Token-counting downstream readiness review

核验日期：2026-09-07。工作目录：`/home/xp/src/ghc-api-proxy-py`。

## 评审范围

核对 `.dev/docs/token-counting/spec.md`、`plan.md`、`status.md`、`README.md`、`HANDOVER.md`，以及 `.superpowers/sdd/serialized-moseying-corbato-2b21444c53e0/progress.md`、`task-4A-brief.md`。重点是 4B-P 的顺序与状态、旧 Task 4A brief 的 `SUPERSEDED` 处置、TaskList／SDD 的投影归属，以及 authority review 之后未重新评审的 writeback。未启动 source，未生成 implementation brief，未修改生产代码或已有文档；本文件是本次要求的唯一新增文件。

TaskList 的具体 JSON 不在当前工作目录内；本报告对其状态只采用已落盘的 authority review 证据，不把它反推为 authority。该 review 明确记录它检查了 TaskList `#13/#14/#15/#16/#26/#27`，并判断依赖边正确（`reports/260907-task3b-authority-review-gpt-high.md:7-13,112-116`）。

## 总体 verdict

**NOT READY for downstream implementation dispatch.** Blocker：0。主要未闭合项：authority review 之后的执行入口 writeback 尚未重新评审；Task 3B authority review 的 4 Major／1 Minor 仍然 open，source authorization 仍被拒绝。4B-P 的顺序本身已在 Spec／Plan 与当前投影中对齐，但这不等于 authority review 已通过。

## 证据与一致性结论

### 1. 4B-P 的 authority 顺序已经明确，当前投影也已补齐

当前 Spec 修订记录把任务顺序固定为 `3B → 4A → 4B-P → 4B → 4C`（`spec.md:698`）；Plan 的 prerequisite amendment 同样明确该拆分（`plan.md:29`），Task 4A 与 Task 4B-P 的职责边界分别在 `plan.md:400-420`、`plan.md:422-446`。README 也把该顺序和 4B-P 的设计来源写清楚（`README.md:49-57`）。

当前 `status.md` 已有独立的 `4B-P．Learned prefix variants` 行，状态为 pending、依赖 Task 4A、tracker 为 `#27`；4B 行改为依赖 4B-P（`status.md:118-122`）。这与 Plan 的 `4A → 4B-P → 4B`（`plan.md:400-460`）一致。

但这次补齐发生在 authority review 之后。`progress.md` 明确记载：handover 期间才给 status 增加 4B-P，并给旧 brief 加 `SUPERSEDED`，两项均为未评审变化，不能据此关闭 `T3B-AUTH-03`（`progress.md:164-166`）。`HANDOVER.md` 以同样措辞再次限定为“部分处理、待复核”（`HANDOVER.md:21-26`、`HANDOVER.md:67-69`）。因此结论是：**4B-P 的内容和顺序对齐，但该执行入口 writeback 的 review 状态仍是 pending。**

### 2. 旧 Task 4A brief 已正确标记 `SUPERSEDED`，但仍只能作为被否路线证据

旧 brief 的首部现在明确写着 `SUPERSEDED／不得派发`，并要求按当前 Plan 重拆为 `3B → deterministic 4A → 4B-P → 4B`，Task 3B reviewed source 完成后重新生成 Task 4A brief（`task-4A-brief.md:1-3`）。这已经阻止了“直接派发旧 brief”的明显路径。

旧 brief 正文仍保留被 review 证伪的旧合同，例如“exact miss 才考虑 prefix”、whole-request suffix subtraction、Task 4A 内的 learned variants、demotion／recovery replay（`task-4A-brief.md:7`、`81-140`）。这不是当前 authority 的自相矛盾，因为首部已经把它降为 superseded artifact；风险在于下游忽略首部而按正文执行。`HANDOVER.md:14`、`HANDOVER.md:41`、`HANDOVER.md:167` 已明确要求先读该标记，且不得修补后继续派发。

最小结论：**不应删除或重写旧 brief 正文，也不能把加标记误报成 authority finding 已关闭；必须由 fresh authority review 后重新生成新的 3B brief、收窄的 4A brief，并在 4B-P 启动前单独生成 4B-P brief。** 该生成顺序已在 `HANDOVER.md:148-152` 写明。

### 3. TaskList 与 SDD 只能是 projection，不能升格为 authority

Spec 的权威顺序明确：Spec 是完整行为 authority，Plan 规定实施顺序，Status 是唯一 volatile projection；Plan／Status 不能另立行为合同（`spec.md:26-36`）。README 对同一关系作了入口级说明：Spec 是唯一行为 Spec，Plan 是实施计划，Status 是唯一 volatile 状态投影（`README.md:7-18`）。Plan 顶部也明确其任务勾选不另立项目级当前状态（`plan.md:1-3`）。

SDD 目前自我降级为“已被 HANDOVER 取代、停止更新”（`progress.md:1-3`），但其历史 ledger 仍可作为恢复 map 和点时证据。它的 Task status 与 Plan 一致，包含 `4B-P pending／Task 4A`、`4B pending／Task 4B-P`（`progress.md:14-28`）；它不能覆盖当前 Spec／Plan，也不能证明 authority review 通过。`HANDOVER.md:40-41` 还明确要求把该 progress 视为已被 handover 取代。

TaskList 同样只承担调度依赖。已落盘 authority review 的结论是其 `#13 → #27 → #14 → #15 → #16` 依赖边正确，但该结论不能替代 Spec／Plan，也不能修复旧 brief 的正文入口（`reports/260907-task3b-authority-review-gpt-high.md:51-60,112-116`）。本次没有把 TaskList 或 SDD 当成 authority，也没有通过修改它们来“关闭”任何 finding。

### 4. authority review 后的 writeback：Spec／Plan hash 未漂移，执行入口变化仍未评审

当前 `spec.md` SHA-256 为 `8405215aa6582728961e9066064cdb59081e519c43bf228267eb6ac21c1086ec`，`plan.md` SHA-256 为 `030fa1bd1be40dfb12b8bd07ef20acfeb2c752bff809bc12ac12d9fc93ea6311`，与 authority review 的固定输入完全一致（review report: `:7-8`；当前 `HANDOVER.md:5`；实际 `sha256sum` 复算一致）。因此本次没有证据表明 Spec／Plan 在该 review 后又发生了隐藏的行为 writeback。

相反，README 的当前 SHA-256 是 `7aba977f16aec718f367083daa35f04926fa33c70505c4a6040b63b98688c720`，而 review 固定的 README SHA 是 `774364f7ea641c385bca1efefb0507554bdef49da670f0b49fe40342e1cb725b`（review report `:9`）。README 作为入口投影已在 review 后变化，当前内容仍正确回指 Spec／Plan／Status，但这次变化本身没有新的独立 review 证据。

更直接的未评审变化是 `status.md` 与旧 brief。`status.md` 当前 mtime 为 18:21，旧 brief 为 18:21；`progress.md:166` 和 `HANDOVER.md:24、67-69` 都明确说它们是在 authority review 后补写，不能把 `T3B-AUTH-03` 标为 closed。`HANDOVER.md:3、9` 还把 handover 自身定为“草稿·未评审”，并保留 `NEEDS FIXES／0 Blocker／4 Major／1 Minor` 与 source authorization denied。

这组证据的边界很重要：**“4B-P 行已出现”和“旧 brief 已有 superseded 头”是当前投影事实，不是 fresh review verdict；“Spec／Plan 当前 hash 与 review 输入相同”也不代表它们已经通过该 review。** 当前 authority writeback 仍包含未解决的 T3B-AUTH-01～05，且 `HANDOVER.md:5、9` 明确禁止据此启动 source。

## 最小同步方案

1. **当前不改 Spec／Plan。** 它们是 behavior／implementation authority；下一步应针对 T3B-AUTH-01～05 修订并在 Spec revision record 留痕，而不是为匹配代码或投影回写而改写合同。
2. **把当前 status／README／handover／旧 brief 的状态视为“候选 projection writeback，待 fresh scoped authority review”。** 4B-P 行和 `SUPERSEDED` 头可以保留为安全性标记，但不能把它们计入 finding closure。
3. **保持 SDD progress 停止更新，保持 TaskList 仅作为依赖投影。** 若调度器需要当前入口，只读 `HANDOVER.md`、`status.md`，并回指 Spec／Plan；不要从 SDD 或 TaskList 推导行为合同。
4. **先修 authority，再评审，再生成 brief。** 依次为：修 AUTH-01～05 → fresh scoped authority review 达到 0 Blocker／Major → 生成 Task 3B implementation brief 并独立 review → 生成收窄的 Task 4A brief → 在启动时再生成 4B-P brief。该顺序与 `HANDOVER.md:148-152` 一致。
5. **下游 readiness 结论保持 fail-closed。** 在 fresh authority review 之前，不启动 Task 3B／4A／4B-P source，不生成 implementation brief，不执行 source integration。

## 未采用路线

- **不采用“status 已补 4B-P，所以 AUTH-03 已关闭”。** 原因：该 writeback 明确发生在 authority review 之后，且 `progress.md:166`、`HANDOVER.md:24、69` 已标为未评审。
- **不采用“旧 brief 加了 SUPERSEDED 就可以修补正文后继续派发”。** 原因：首部要求重新生成；正文仍是旧设计的点时证据，不能被当成当前任务合同。
- **不采用“TaskList／SDD 顺序正确，所以它们可以反向授权 source”。** 原因：`spec.md:30-32`、`README.md:7-18` 明确规定它们是实施顺序或状态投影，不能另立 behavior authority。
- **不采用“authority review 已有 0 Blocker，所以可以继续”。** 原因：同一 review 是 `0 Blocker／4 Major／1 Minor`，并明确 `NEEDS FIXES` 与 source authorization denied（review report `:18-24、138-144`；`HANDOVER.md:9`）。
- **不采用删除 SDD、删除旧 brief 或清理历史报告来消除冲突。** 原因：它们是点时证据与复发防线；最小方案是保留、降级为 projection／superseded artifact，并在新 brief 与 fresh review 中建立新入口。

## 搜索面与未覆盖面

已读上述七个指定文件、项目 workflow、`docs/.human-controlled/README.md`、`api.md`、`message-translation.md`，以及当前 Task 3B authority review；复算了七个文件的 SHA-256 与 mtime，并用行号核对关键段落。未运行测试、source、真实 upstream 或 4141 服务；未修改任何既有文件。TaskList JSON 未在当前工作目录检出，因此未对其原始 JSON 做第二次直接读取，相关判断仅采用已落盘 authority review 的明确记录。

# `main@b91e58a` 四份 living docs checkpoint 只读审计

- **评审范围**：`main@b91e58a29324b11840002efc53ed6f869b800c39` 下 Acceptance `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`、Implementation `455d101441591b817643fa7623e77119761aa9284e0da62772efa34026bc160d`、Readiness `466090223e717366d20d79b4ab2393eb339f32d1a463b8face93915ff3c9255b`、Systemd Plan `1b936c11eeab3489459e46048dddd2382da5cd49c881b13c3d1a9a92b2bb3344`；current复评、真实index、tracked WIP、精确四pathspec prospective staging／commit、排除`docs/tmp`／`verification`及diff-check。唯一仓库写入为本报告，未修改真实index。
- **总体 verdict**：**存在 blocker，当前不可暂存或提交四文档 checkpoint。**
- **blocker 数**：2。
- **major 数**：0。首个blocker由被审计Plan current复评的`1 major`触发。
- **pending复评数**：2。Implementation与Readiness只记`PENDING`。

## 双视角覆盖证据

### 机械核对

- 可靠nonce gate确认物理root、Git top-level及HEAD精确为主树`b91e58a…`；四个SHA均与指定值一致。
- Acceptance已有精确`0 blocker／0 major／0 minor`证据，但当前无tracked diff。
- `docs/tmp/**/*.md`中没有绑定Implementation `455d1014…`或Readiness `46609022…`的产物，二者为`PENDING`。
- `docs/tmp/260807-resume-review-systemd-plan-current.md`绑定Plan `1b936c11…`与`main@b91e58a…`，verdict为`0 blocker／1 major`、不可checkpoint。其major是Plan仍声称new-main S3／S4尚未产生，但Git中已有直接基于`b91e58a…`的`8cae6c260c8bc2930be96eaecc7d6d24d470e00a`及后继`d3fabfadfba57af6c2d63e543e3198444777df54`。
- 真实index为空。Tracked WIP精确只有Implementation、Readiness、Systemd Plan三路径，Acceptance已与HEAD相同。
- 精确四pathspec的`git commit --dry-run`及`/tmp`隔离index staging都只得到上述三路径；`docs/tmp`／`verification`未进入prospective commit。
- Worktree `git diff --check`及隔离index staged `diff --cached --check`均通过。真实index演练前后SHA-256均为`ca07c6f204f899600c286813c880fad0feed3ed284368d039e4e5c77d0491a28`且路径为空。

### 第一人称执行

- 内容门先失败：Implementation／Readiness仍`PENDING`，Systemd Plan已有`1 major`。
- 精确列四pathspec不会创造Acceptance差异；实际提交只有三文档，不能冒称四文档checkpoint。
- 固定hash组合不能原地转绿：修Plan会改变Plan hash；让Acceptance成为WIP也需有意新bytes、新hash和新复评。
- 未来checkpoint只放行living实施，不表示产品`PASS`、安装、部署或cutover授权。

## 事实性发现

[blocker] `docs/agents/systemd-runtime/plan.md` — Current复评已有`1 major` — Plan未消费已存在的new-main rebuild `8cae6c2… → d3fabfa…`，仍命令重新构造S3／S4，会制造第二条identity并丢失逐片gate／fresh checkpoint账本 — 全文同步actual chain，标记尚未进入main且main-side gate／fresh checkpoints待验证，保持旧链仅作oracle及`LIVING`／S5／S7／`NO CUTOVER`边界；新bytes重新hash并复评。

[blocker] 四目标路径Git边界 — tracked WIP不是恰四路径，精确四pathspec只能形成三路径prospective commit — 真实diff、dry-run和临时index均只有Implementation、Readiness、Systemd Plan；Acceptance已在HEAD — 若严格要求四文档commit，须先有意修改Acceptance并取得新hash复评；若只提交实际变化，须由用户明确改判为三文档checkpoint，不能静默缩减。

## Current复评状态

| 文档 | Current SHA-256 | Current复评 | 门 |
|---|---|---|---|
| Acceptance | `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001` | 0 blocker／0 major／0 minor | 内容通过；无tracked diff |
| Implementation | `455d101441591b817643fa7623e77119761aa9284e0da62772efa34026bc160d` | `PENDING` | 待复评 |
| Readiness | `466090223e717366d20d79b4ab2393eb339f32d1a463b8face93915ff3c9255b` | `PENDING` | 待复评 |
| Systemd Plan | `1b936c11eeab3489459e46048dddd2382da5cd49c881b13c3d1a9a92b2bb3344` | 0 blocker／1 major | 阻断；修订后新hash复评 |

## 已通过但不放行

主树身份、四SHA、空index、旁路文件排除、worktree及prospective staged diff-check均通过；它们不证明存在四份差异或内容复评闭合。

## 条件式提交门

1. Gate物理root、Git top-level、`main`及当时完整HEAD。
2. 记录新的四SHA；每份须有精确绑定的独立`0 blocker／0 major`报告。关闭两个`PENDING`与Plan major；Acceptance若有新diff也重评。
3. 真实index为空；tracked WIP集合精确等于四目标路径，不能多也不能少。
4. 四路径worktree `git diff --check`通过。
5. 隔离临时index演练精确四path staging；staged集合严格四路径、数量4，无`docs/tmp`／`verification`或其他路径；staged diff-check通过。
6. 才执行真实精确四path staging，并再次核对集合与diff-check。
7. 精确四path commit dry-run仍为四路径后才提交；提交后核对commit pathset、index为空及untracked资产未提交。
8. Checkpoint不授权产品、安装、部署、运行态变更或cutover。

若改为只提交实际变化，则是三文档checkpoint，必须由用户明确裁决，且仍须先关闭两个`PENDING`与Plan major。

## 主观建议

[建议] 先修Plan并取得新hash复评，再完成Implementation／Readiness复评；最后按Acceptance是否确有新内容，明确选择严格四文档或三文档边界，避免为必然失效的旧hash补证书。

## 结论

Current四hash快照为**2 blocker／0 major，当前不可暂存或提交**。真实index为空且保持不变，`docs/tmp`／`verification`未夹带，diff-check通过；但Plan有current major，两个current复评pending，且tracked WIP／prospective commit只有三路径。须在新候选快照上重新审计。

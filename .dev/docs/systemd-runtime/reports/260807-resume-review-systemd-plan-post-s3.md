# systemd living Plan S3 后定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 current `docs/agents/systemd-runtime/plan.md`，内容身份 SHA-256 `6f32c06f3e918eb88bb751637561d54bd75aecf1e150c584c1a0b94f5b1fb9e0`；固定 `main@c53849e2b5103c6426a67a8cbab687f2e45c1fa0`。本轮定向核对 S3 main commit／main-side gates／reviewed-source archive、S4 exact source与既有 integration证据仍待单独 squash、Plan checkpoint前置、S5／S7、三个 non-blocking minor、`NO_CUTOVER`与`LIVING`。未执行 S4 squash、安装、manager操作、服务／端口变更、部署或cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。Current Plan 为 0 blocker／0 major，可 checkpoint。** Plan准确记录S3已进入main且不再重放，S4仍须在本Plan checkpoint之后从exact candidate第二片单独squash，并在main-side gate通过后fresh更新Plan，才可进入S5。该checkpoint不表示S4已进入main、真实manager／effective cgroup已验证、unit已安装、S7 rolling已实现、部署完成或cutover获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0个新增。既有三个non-blocking minor——shutdown配置优先级永久测试判别力、installer逐文件atomicity／三文件非事务措辞、timeout facts重复owner——均被完整保留，不阻塞本Plan checkpoint或后续S4 main收敛。

## 双视角覆盖证据

### 机械核对视角

- 在同一调用内验证物理root、Git top-level、branch与exact `HEAD=c53849e2b5103c6426a67a8cbab687f2e45c1fa0`；`sha256sum`与Python `hashlib.sha256`两种实现均得到目标Plan SHA-256 `6f32c06f3e918eb88bb751637561d54bd75aecf1e150c584c1a0b94f5b1fb9e0`。
- Git对象确认S3 main commit subject为 `feat: configure graceful shutdown timeout`，parent为 `ae84aa9d4330e56b83aefdad977e7d93190ff0d4`，精确修改9个非Plan路径；其stable patch-id `26dcc6fbfffe0db7d3358728ff244fec36078be1`与rebuilt S3 `b91e58a… → 8cae6c2…`相等。
- `archive/260807-systemd-graceful-timeout`现场解析为reviewed source `865a5b71210e2436b36786b5de67146939d1e0f5`，没有误指rebuilt commit或main squash commit。
- 在exact `main@c53849e…`重跑Plan声明的S3 main-side gates：三个定向文件为 `30 passed in 9.23s`；全仓 `tests`为 `585 passed in 17.93s`；同范围collect-only独立计得585个node IDs且pytest自报 `585 tests collected`；Ruff为 `All checks passed!`；Pyright为 `0 errors, 0 warnings, 0 informations`。执行前后未编辑产品或Plan文件。
- 固定candidate `/home/xp/src/ghc-api-proxy-py-integrate-systemd-rebuild-resume` 的branch `integrate/260807-systemd-rebuild-resume`、tip `d3fabfadfba57af6c2d63e543e3198444777df54`与parent `8cae6c260c8bc2930be96eaecc7d6d24d470e00a`。S4精确只有 `contrib/systemd/install-user.py`、`docs/agents/deployment-systemd/README.md`、`tests/smoke/test_systemd_user_install.py` 三个路径，不含Plan，stable patch-id为 `412e73c47064720386c1075bfac0d3d8d08c6d26`。
- 使用 `git cat-file -e`显式区分缺失路径后，current main三个S4目标preimage与candidate parent逐项一致：两个新增文件两侧均为`ABSENT`，deployment README两侧blob均为 `bed9f5e960169592011ee4c047fb55e87f490c75`。因此S4在当前main上确实处于“exact source与证据已存在、fresh-main preimage成立、仍待checkpoint后单独squash”的状态。
- 完整通读Plan页首、固定事实、状态看板、S3～S7、disposition、验证边界与kick-off；`docs/agents/systemd-runtime/plan.md:3-8,15,45-46,98-102,231,237-248,288-306,337-343,426-440`在身份、顺序、未验证边界与状态词上前后一致。

### 第一人称执行视角

- 作为Plan checkpoint执行者，我先只冻结current Plan bytes；不会因S3代码、tests与archive均完成而跳过本次新Plan hash的独立checkpoint，也不会把本报告、其他`docs/tmp/**`或代码夹带进checkpoint。
- 作为S4执行者，我从checkpoint后的actual main重新固定身份，只消费 `8cae6c2… → d3fabfa…` 的三路径parent-adapted delta；先核对candidate、pathset、fresh-main preimage与result bytes，再单独形成S4 squash并运行main-side gate。不会重放S3、使用旧 `2ec0cb8…`／`0a93e7f…`、直接应用reviewed source `e16c2a7…`的原始patch、采用旧Plan postimage或把Plan混入代码载荷。
- 作为后续实施者，只有S4 main-side gate通过并fresh更新／checkpoint Plan后才进入S5真实user-manager／cgroup smoke；S5使用备用端口、隔离状态根和可回收fixture，不触碰生产4141。S7仍是须先冻结拓扑、readiness切流、状态隔离、drain与回滚规则的独立后续切片，不会被S4或S5自然“顺带完成”。
- 作为部署执行者，我始终把repository checkpoint、candidate review／verify、静态parser与备用运行态probe分层；任何一层全绿都不会被解释为unit已安装、manager已加载、effective limits已生效、rolling成立或生产cutover获授权。

## 事实性发现

未发现问题。当前Plan在本轮定向范围内为 **0 blocker／0 major／0新增minor**，可以形成checkpoint。

## 已核对的关键状态

1. **S3 main／gates／archive**：`main@c53849e…`为九路径单一S3语义commit；本轮重跑30项定向、585项全仓、585项collect-only、Ruff与Pyright均通过；archive精确指向reviewed source `865a5b7…`。
2. **S4 exact source／integration证据**：`d3fabfa…`仍是`8cae6c2…`的三路径第二片，Plan排除且current-main preimage成立；`docs/tmp/260807-resume-review-systemd-rebuild.md`的merged-state verdict为`0 blocker／0 major`，`docs/tmp/260807-verify-systemd-rebuild-resume.md`与`docs/tmp/260807-resume-verify-systemd-rebuild.md`对同一exact tip均为`PASS`。这些证据放行checkpoint后的单片squash流程，不表示S4已经进入main。
3. **checkpoint前置**：Plan在页首、看板、S6回并边界与kick-off均先要求当前hash形成checkpoint，再允许S4 identity／preimage／tests gate；没有路径引导执行者跳过checkpoint或重复S3。
4. **开放范围与边界**：S5真实user-manager／cgroup和S7 rolling完整保留；三个non-blocking minor仍有明确owner／后补方向；Plan持续`LIVING`且不收口，整体持续`NO_CUTOVER`。

## 主观建议

无。当前执行顺序与证据分层已经足够明确，没有需要在checkpoint前追加的主观优化项。

## 最终结论

**0 blocker／0 major，可checkpoint。** 本结论只绑定Plan SHA-256 `6f32c06f3e918eb88bb751637561d54bd75aecf1e150c584c1a0b94f5b1fb9e0`与`main@c53849e2b5103c6426a67a8cbab687f2e45c1fa0`。Checkpoint后可按Plan进入S4 exact identity／fresh-main preimage／单片squash／main-side gate；通过后fresh更新Plan，再进入S5。Plan继续`LIVING`，三个minor、S7与`NO_CUTOVER`边界继续有效。

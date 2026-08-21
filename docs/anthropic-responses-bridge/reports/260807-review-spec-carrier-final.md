# Anthropic Responses bridge current Spec carrier 终审

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/spec.md`，仅终审 carrier 定向评审后的状态／provenance，以及双格式行为是否保持不变：项目主 versioned v1 producer、`copilot-api-js` upstream v1 合法主路径 consumer compatibility、非全 malformed 边界一致、一 Responses reasoning item 对应一 Anthropic thinking block且普通模式 no-loss、consumer 识别顺序、strip／echo、Direct Messages strip 和 unknown／foreign／malformed 最低止血。未重审 bridge 其余章节，未评审候选实现是否已符合 Spec。
- **总体 verdict**：**可进入下一阶段**。current Spec 的状态与 provenance 闭合，双格式合同未发生语义漂移；**当前 Spec 可提交，实施可继续**。这里放行的是 SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` 的 current worktree bytes，不把主线 compatibility primitive 或任何候选实现视为项目主 v1、forward cardinality 与 no-loss 已完成的证据。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **评审基线**：所有采信的 shell 证据均在同一次调用内确认物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。一次被并发终端输出串占、显示其他 worktree gate 的调用已明确剔除，未用作证据。
- **双视角覆盖证据——机械核对**：完整通读 current Spec 的文档状态、双向字段矩阵、Reasoning wire contract、双格式识别顺序与最低止血、Compatibility、验收行为、结论及评审处置表；对账 `docs/tmp/260807-review-spec-carrier-dual-format.md` 的 0 blocker／0 major verdict 和允许恢复 `FINALIZED` 的结论；验证全部 provenance 文件存在；扫描旧“upstream 是项目主 producer／所有 malformed 边界须与 Node 一致”的肯定性合同残留；执行 staged 与 unstaged `git diff --check`，均无格式错误。current Spec SHA-256 由 `sha256sum` 与 Python `hashlib.sha256` 两种原理一致重算为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。
- **双视角覆盖证据——第一人称执行**：按实现者与 consumer 视角依次走项目 v1 payload、项目 bare marker、项目 unknown version、upstream v1 payload、upstream bare prefix、upstream legacy bare sentinel与 foreign signature 7 个分类入口；独立重算项目 canonical signature，以及 upstream `ENC==`、`opaque-😀` 两个合法向量。再模拟 summary＋ciphertext、summary-only、encrypted-only、multiple reasoning items、普通 echo、显式 strip、Direct Messages sanitizer、project malformed 与 upstream malformed 路径；每条路径都有唯一处置，显式 strip 未冒充 no-loss，malformed 也不会 fallback 为成功 carrier。

## 事实性发现

未发现问题。

### 状态与 provenance 核对

1. `spec.md:5-8` 已恢复 `FINALIZED`，并明确 carrier 双格式合同冻结、current forward cardinality 仍是开放实现缺口；状态没有把规格放行误写成实现完成。
2. carrier 定向评审 `docs/tmp/260807-review-spec-carrier-dual-format.md:3-10,32` 对 SHA-256 `0d81c21fb6efcc71e217b162418a89cf53cc7f392669e5b0b280651de512691e` 的双格式合同给出 0 blocker／0 major，并明确允许随后恢复 `FINALIZED`、同步 D4-R2。current Spec 在该评审后加入状态与 provenance 收口内容，现场 SHA 因而变为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；本终审直接核对 current bytes，不沿用旧 SHA 冒充 current verdict。
3. `spec.md:571,575,584-587` 如实记录 D4 二次重裁、旧 R3 verdict 的适用边界、D4-R2 定向评审及其 0／0 结果；既没有把旧 verdict 延伸到新 bytes，也没有把 compatibility primitive 写成完整实现证据。
4. 当前 Git 状态中 Spec 为 `AM`：HEAD `ed77c9d…` 尚无该文件，index 与 worktree bytes 不同。本报告的“可提交”指经终审的 current worktree SHA `5e3628…`；实际提交前必须把 current bytes 更新进 index，不能提交现有 stale index blob。

### 双格式行为未变核对

1. **项目主 versioned 格式仍为默认 producer**：`spec.md:204-222` 固定项目 namespace、v1 prefix、bare marker、tag、唯一最小字段、canonical base64url、roundtrip、echo 与 strip；`spec.md:483,525,537` 在 Compatibility、验收行为和冻结决策中保持同一主格式。
2. **`copilot-api-js` v1 仍只兼容合法主路径**：`spec.md:224-232` 将固定 upstream commit 的 payload、bare prefix 与 legacy sentinel限定为 consumer compatibility oracle，并明确不复制有损聚合；`spec.md:246-248,525,551` 明确不要求非 canonical／全部 malformed 边界与 Node 逐字节一致。
3. **一 item 一 block、普通模式 no-loss 和顺序保持**：`spec.md:177-183,204-210,221,325,329,352-359,525` 共同要求每个 reasoning item 独立形成 thinking block，encrypted-only 不丢失，multiple items 不聚合／错配，并按上游语义顺序分配连续 block index。
4. **consumer 顺序唯一**：`spec.md:234-248` 固定 first-match-wins 顺序为项目 v1、项目 unknown version、upstream v1、upstream legacy bare、foreign；decode／schema 失败不得改走另一 decoder。项目 canonical signature、7 个分类入口和 2 个 upstream 合法向量均已独立重算／模拟通过。
5. **strip／echo 边界稳定**：`spec.md:205,209,221-222,232,525` 规定普通 echo value-exact，显式 `stripThinkingSignature` 每 item 保持 block cardinality并记录有意 payload removal，Direct Messages sanitizer 无条件剥离项目 synthetic namespace、upstream prefix form 与 legacy sentinel。
6. **最低止血完整且不过度扩张**：`spec.md:164-165,244-249,483-485,525` 要求 project／upstream malformed、unknown version 与 foreign 稳定分类，不恢复 `encrypted_content`，不抛裸异常，不泄漏完整 signature／payload，整个对应 block 不进入 Responses wire；同时明确不新增 HMAC、keyring、domain binding、carrier 专用阈值或泛化安全状态机。

## 主观建议

无。

## 放行结论

current Spec SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` 的状态、provenance 与 carrier 双格式行为一致，未发现 blocker、major 或 minor。**current Spec 可提交，实施可继续。** 提交时应纳入 current worktree bytes；后续实现验收仍须分别证明项目主 v1 producer／consumer、upstream 合法主路径兼容、分类止血、逐 item cardinality、顺序、strip／echo 与普通模式 encrypted-only no-loss。

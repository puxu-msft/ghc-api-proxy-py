# Anthropic Responses bridge Spec carrier 双格式定向评审

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/spec.md` 的 2026-08-07 carrier 双格式修订，仅核对最新用户重裁的七个直接要求：项目主版本化格式、`copilot-api-js` v1 合法主路径兼容边界、consumer 识别顺序、unknown／foreign／malformed 最小止血、一 item 一 block 与 encrypted-only no-loss、字段矩阵／验收行为同步，以及不引入安全过度设计。未重审其他 Spec 章节，也未评审候选实现是否已经符合该 Spec。
- **总体 verdict**：**可进入下一阶段**。本轮未发现 blocker 或 major；该 Spec **可恢复 `FINALIZED` 并按冻结合同继续实施**。此结论只放行规格状态，不把主线现有 upstream compatibility primitive 或候选实现视为项目主 v1、forward cardinality 与 no-loss 已完成的证据。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **评审基线**：每次 shell 调用均在同一次调用内确认物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。
- **双视角覆盖证据——机械核对**：完整通读 current Spec；逐项对账文档状态、双向字段矩阵、Reasoning wire contract、Compatibility、验收行为、结论与评审处置表；扫描旧“upstream 唯一 producer／全 malformed byte-exact oracle”措辞残留；核对固定 `copilot-api-js` commit `8d5c861c2e079b92401dd8ccd49695a363d078fe` 的 producer、consumer、legacy sentinel 与 direct Messages strip 实现；独立重算项目主 v1 canonical JSON／base64url signature 和两个 upstream 合法向量；执行 `git diff --check`，无格式错误。
- **双视角覆盖证据——第一人称执行**：按实现者视角依次模拟项目 v1 payload、项目 bare marker、项目 unknown version、项目 malformed v1、upstream v1 payload、upstream bare prefix、upstream legacy bare sentinel、foreign signature 与原生 `redacted_thinking` 的分类；再模拟 summary＋ciphertext、summary-only、encrypted-only、multiple reasoning items、普通 echo、显式 strip 和 direct Messages sanitizer 两条用户路径。各分支均能从识别入口走到唯一处置，不需要猜测 fallback，也不会把显式有损 strip 误称为 no-loss。

## 事实性发现

未发现问题。

### 定向核对结论

1. **项目主版本化格式足够实现**：`spec.md:212-222` 冻结 namespace、payload prefix、bare marker、紧凑 UTF-8 JSON producer 形态、字段顺序、base64url canonicalization、唯一字段集合、duplicate-key 处置、固定 tag、非空 ciphertext、canonical vector、版本扩展边界、roundtrip 与 strip／echo。实现者无需自行决定 v1 wire grammar。
2. **upstream v1 兼容范围不过度**：`spec.md:224-232` 把固定 upstream commit 的 prefix、unpadded base64url payload、bare prefix、legacy sentinel 和合法向量限定为 consumer compatibility oracle；明确排除复制 non-stream／stream 的有损聚合，也不要求项目 producer 复刻 upstream bytes。该范围与固定 commit 的真实代码一致。
3. **consumer 识别顺序无歧义**：`spec.md:234-243` 给出 first-match-wins 顺序，并禁止 decode／schema 失败后把同一 signature fallback 为其他格式。项目 v1、项目 unknown version、upstream v1、upstream legacy 与 foreign 的入口互斥；原生 `redacted_thinking` 保持独立合同。
4. **unknown／foreign／malformed 已做最小止血**：`spec.md:244-251` 冻结稳定分类、禁止恢复 ciphertext、禁止裸异常与完整 signature／payload 泄漏、整 block 不进入 Responses wire、服从既有 memory／cancel／deadline／cleanup 合同，并明确不把非 canonical Node 边界全空间升级为兼容合同。
5. **一 item 一 block 与 encrypted-only no-loss 保持闭环**：字段矩阵 `spec.md:182-183`、Reasoning 合同 `spec.md:203-210`、wire roundtrip `spec.md:220-221`、block 完成条件 `spec.md:322` 和验收行为 `spec.md:525` 一致要求逐 item、有序、普通模式下 encrypted-only 不丢失；显式 strip 单独标记为有意 payload removal，未冒充 no-loss。
6. **字段矩阵与验收行为同步**：request 矩阵 `spec.md:161-165` 覆盖项目主 v1、upstream v1、三种 bare／legacy、unknown／malformed、foreign／redacted；Compatibility `spec.md:483-485` 与验收行为 `spec.md:525` 使用同一双格式边界和 malformed 范围，没有残留旧 producer 合同。
7. **未引入安全过度设计**：`spec.md:219` 与 `spec.md:248-251` 明确排除 issuer、nonce、HMAC、`kid`、key rotation、domain binding、JCS、carrier 专用阈值与安全状态机；保留的严格 UTF-8、schema gate、日志裁剪和既有资源预算均直接服务于确定性解析与最小止血，不构成额外认证系统。

## 主观建议

无。

## 放行结论

当前 carrier 双格式修订满足本轮最新用户重裁，且未发现 blocker／major。主会话可将 `docs/agents/anthropic-responses-bridge/spec.md` 从 `READY_FOR_TARGETED_REREVIEW` 恢复为 **`FINALIZED`**，同步 D4-R2 处置状态后继续实施。实施验收仍须分别证明项目主 v1 producer／consumer、upstream 合法主路径兼容、分类止血、逐 item cardinality 与普通模式 encrypted-only no-loss；本报告不替代这些实现证据。

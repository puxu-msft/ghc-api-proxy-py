# Anthropic Responses bridge Acceptance 双 carrier 独立终审

- **评审范围**：主树 current `docs/agents/anthropic-responses-bridge/acceptance.md`，内容身份 SHA-256 为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。本轮核对 current Spec／Architecture hash、`POLICY-MANIFEST-v1` 七域映射，重点终审 `REQ-05`／`NS-03` 的“本项目主 v1 默认 producer＋`copilot-api-js` v1 合法主路径 compatibility consumer”、非全 malformed Node byte-exact、unknown／foreign／malformed 最小止血、producer／consumer 独立 oracle，以及其余域是否漂移。未执行候选产品 gate，也未评审完整 bridge 产品符合性。
- **总体 verdict**：**可进入下一阶段；Acceptance 可提交。** 本轮未发现 blocker 或 major。current Acceptance 忠实承接 current Spec 的双 carrier 合同，七域 manifest 未把 Architecture 提案提升为 expected，其余 gate 未发生政策漂移。该结论只放行 Acceptance oracle，不构成产品通过证据。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **产品状态**：候选产品及完整 bridge 仍为 **`UNVERIFIED`**。
- **评审基线**：每次 shell 调用均在同一次调用内确认物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。current Spec SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，current Architecture SHA-256 为 `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d`；两者均与 Acceptance 内嵌绑定一致。
- **双视角覆盖证据——机械核对**：完整通读 current Acceptance、current Spec 与 current Architecture；以 `sha256sum` 和 Python `hashlib.sha256` 交叉验证 Spec／Architecture hash；清点 `POLICY-MANIFEST-v1` 恰含 route、request、response、buffering、retry、lifecycle、limits 七域；清点 35 个 required gate 标题；逐项对账双向字段矩阵、Reasoning wire contract、Compatibility、验收行为、状态与处置表；扫描旧 upstream-only producer、全 malformed Node byte-exact、`Node-compatible decode` 与 Python 私有 carrier 等残留；独立重算项目主 v1 canonical JSON／base64url exact vector及两个 upstream 合法向量；读取固定 `copilot-api-js@8d5c861c2e079b92401dd8ccd49695a363d078fe` 的 producer、consumer、legacy sentinel 与 direct sanitizer 源码；执行重复长行扫描和 `git diff --check`。旧口径命中仅存在于“已被覆盖／不得沿用”的历史说明或禁止性反例中，未作为 current expected 复活。
- **双视角覆盖证据——第一人称执行**：以验收实现者身份依次模拟项目 v1 payload、项目 bare marker、项目 unknown version、项目 malformed v1、upstream v1 payload、upstream bare prefix、upstream legacy sentinel、代表性 upstream malformed、foreign signature与原生 `redacted_thinking` 的 first-match 分类；再模拟 summary＋payload、summary-only、非空 encrypted-only、multiple reasoning items、authoritative `.done`、普通 echo、显式 strip 与 direct Messages sanitizer。随后分别按 producer-only 与 consumer-only 变异路径执行判据：producer expected 不经过 consumer，consumer expected 旁路 producer，固定 upstream bytes 与 Responses event corpus各有独立观测链。所有分支均能走到唯一 expected，不要求实现者猜测 fallback，也不会把 strip 的有意移除冒充 no-loss。
- **证据边界**：评审开始时，Acceptance 对 READY 候选 `787b5c386dd6c623d66e47e2c26d2b84bb605db66dc0db97a6ee9dc1a2379afb` 的 0／0仅为源文档自述，仓库中尚无独立报告可作为证据；本轮没有沿用该自述或旧 R7／R8 verdict，而是直接重审并绑定 current `224b020d…` 全文。故本报告的放行对象是 current bytes，不把不可独立恢复的中间快照差异冒充已验证事实。

## 事实性发现

未发现问题。

### 七域与重点合同结论

1. **Hash 与权威边界一致**：Acceptance 内嵌 Spec `5e362822…`、Architecture `c6088a…` 均与现场 current bytes一致；Spec 是唯一行为 oracle，Architecture 明确保持非规范参考。Architecture 的旧 `ADR-BRIDGE-06` upstream-only carrier 只被列为已知陈旧承载记录，未进入 `REQ-05`／`NS-03` expected。
2. **七域 manifest 完整且未漂移**：route、buffering、retry、lifecycle、limits 延续既有 expected；request、response 只改变 carrier producer ownership、合法 compatibility 范围与 malformed 边界。route precedence、server-tool no-revive、block withholding、continuous-prefix commit、post-commit partial failure、single lifecycle owner、per-request aggregate＋global reservation等非 carrier合同保持原义。
3. **`REQ-05` 默认 producer 正确**：项目 producer 只输出 `ghc-api-proxy:synthetic-reasoning:v1:` payload form或 `ghc-api-proxy:synthetic-reasoning:v1` bare marker；version、tag、最小字段集合、紧凑 UTF-8 JSON、unpadded canonical base64url、empty handling、strip marker与 authoritative `.done` 均有静态 expected。独立标准库重算 `opaque-😀` exact vector与文档完全一致。
4. **upstream v1 仅作 consumer compatibility oracle**：固定 `copilot-api-js@8d5c861…` 的真实源码确认合法主路径为 `prefix + base64url(UTF-8 encrypted_content)`，bare prefix与legacy sentinel均可消费，direct Messages sanitizer按 synthetic marker无条件 strip。Acceptance 要求 consumer 接受这些合法输入，但明确禁止 producer 输出 upstream v1或复制 upstream 的有损聚合。
5. **不再要求全 malformed Node byte-exact**：项目格式执行自身 canonical/schema gate；upstream 只承诺合法主路径、bare、legacy及代表性 malformed 分类。所有要求逐 malformed 边界等同 Node 的变异均被明确排除，避免把 Node 宽松 decoder偶然语义升级为产品合同。
6. **unknown／foreign／malformed 最小止血闭合**：project unknown、project malformed、upstream malformed与foreign均有稳定分类；对应整个 thinking block不进入 Responses wire，不恢复 visible summary或 `encrypted_content`，不改写成普通 assistant text，不抛裸异常，不泄漏完整 signature，并继续服从既有 size／memory／cancel／deadline／cleanup合同。
7. **producer／consumer oracle 独立**：项目 exact bytes、静态项目 consumer vectors、固定 upstream bytes与固定 Responses event corpus形成四条 provenance链；producer-only／consumer-only变异不能通过共享 codec同步改写 expected与actual。判据同时覆盖项目 producer稳定性、两类 consumer输入互操作及 semantic normalizer接缝，而非同源 roundtrip。
8. **`NS-03` cardinality与no-loss保持**：每个 Responses reasoning item独立形成一个 Anthropic thinking block；普通模式下非空 encrypted-only value-exact往返，多 item不跨 item聚合 summary、不覆盖 ciphertext、不重排。显式 strip仍保持每 item block cardinality并记录有意 payload removal，不被误报成普通模式 no-loss。
9. **oracle与产品状态分工正确**：`FINALIZED_ACCEPTANCE_ORACLE` 只表示验收规范可提交并可作为执行 oracle；候选产品尚未运行 required gate、单侧变异、live canary、capture provenance与local fault流程，完整 bridge继续为 `UNVERIFIED`，基础 integration或局部测试的 `PASS`不得外推。

## 主观建议

无。

## 放行结论

current `acceptance.md@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4` 在本轮指定范围内为 **0 blocker／0 major／0 minor**。**Acceptance 可提交。** 此结论不改变候选产品及完整 bridge 的 **`UNVERIFIED`** 状态；产品只有在 current Acceptance 所列全部 required gate及其独立正反控制、真上游／corpus provenance与本地故障注入均取得可复现实证后，才可升级为 `PASS`。

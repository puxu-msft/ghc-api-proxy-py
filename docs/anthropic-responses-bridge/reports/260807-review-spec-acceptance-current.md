# Anthropic Responses bridge current Spec／Acceptance 联合终审

- **评审范围**：current `docs/agents/anthropic-responses-bridge/spec.md` 与 `docs/agents/anthropic-responses-bridge/acceptance.md` 的只读联合终审；Architecture 只按 Acceptance 的绑定关系和非行为 oracle 边界读取。Spec SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`，Acceptance SHA-256 为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`，Architecture SHA-256 为 `c6088a2d2ce89e2355627372d10973bea6a0794ddc45b84b33b4aaa5a9f29b8d`。未执行候选产品 gate，也未评审完整 bridge 的产品符合性。
- **总体 verdict**：**可进入下一阶段。current Spec 与 Acceptance 均可提交，实施可按两份 current 文档继续。** 本轮为 0 blocker、0 major；唯一 minor 是 Acceptance 对一个不可独立恢复的 READY 中间快照作了已完成复评的 provenance 自述，但现有独立 current-byte 终审已直接覆盖最终 Spec／Acceptance bytes，因此不阻断提交或实施。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **产品状态**：候选产品及完整 bridge 继续为 **`UNVERIFIED`**。文档 `FINALIZED`、`FINALIZED_ACCEPTANCE_ORACLE`、局部实现评审或基础 integration 的 `PASS` 均不得外推为产品 `PASS`。
- **证据基线**：有效 shell 基线在同一次调用内确认物理 root 与当前目录为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。三份 current 文档 SHA-256 分别为上述 `5e362822…`、`224b020d…`、`c6088a…`。一次并发终端串入其他 worktree 输出的调用没有本轮 nonce／gate，已明确剔除，不作为证据。
- **双视角覆盖证据——机械核对**：完整通读 current Spec、Acceptance 与被绑定的 Architecture；逐项对账文档状态、SHA-256 绑定、carrier 双格式、双向字段矩阵、识别顺序、最小止血、验收行为、产品状态与评审处置表；清点 `POLICY-MANIFEST-v1` 恰含 route、request、response、buffering、retry、lifecycle、limits 七域；核对 35 个 required gate 标题；独立重算项目主 v1 canonical vector及两个 upstream v1 合法向量；核对 `docs/tmp/260807-review-spec-carrier-final.md` 直接绑定 current Spec `5e362822…` 并为 0 blocker／0 major，`docs/tmp/260807-review-acceptance-dual-carrier.md` 直接绑定 current Acceptance `224b020d…` 并为 0 blocker／0 major；扫描 READY 候选 `787b5c38…` 的落盘引用，确认没有可独立恢复的对应评审报告。
- **双视角覆盖证据——第一人称执行**：以实现者身份依次模拟项目主 v1 payload／bare producer、项目 unknown／malformed、upstream v1 payload／bare／legacy consumer compatibility、foreign signature、summary＋payload、summary-only、非空 encrypted-only、multiple reasoning items、普通 echo、显式 strip 与 Direct Messages sanitizer；各分支都能得到唯一合同，一 item 一 block与普通模式 no-loss没有被 upstream 有损聚合覆盖。以验收执行者身份按七域 manifest 进入 required gates，Architecture 的旧 upstream-only carrier只能帮助定位接缝、不能生成 expected；执行结束仍必须把未跑完整 gate 的产品保持为 `UNVERIFIED`。

## 事实性发现

### [minor] `docs/agents/anthropic-responses-bridge/acceptance.md:9,11,400,404,429` — READY 中间快照的独立复评 provenance 不可恢复

**问题**：Acceptance 多处断言独立定向复评已绑定 READY 候选 SHA-256 `787b5c386dd6c623d66e47e2c26d2b84bb605db66dc0db97a6ee9dc1a2379afb` 并给出 0 blocker／0 major，但 `docs/tmp/**` 中没有承载该完整 hash 的独立评审报告。现有 `docs/tmp/260807-review-acceptance-dual-carrier.md:12` 也明确说明该 READY 结论当时只是源文档自述，并未沿用。

**证据或失败场景**：后续审计者若只按 Acceptance 的 provenance 链追溯，会在 `787b5c38…` 处断链，无法独立验证“随后只恢复状态与处置记录”这一历史差分。不过，`docs/tmp/260807-review-acceptance-dual-carrier.md:3-12,36` 已直接重审并绑定 current Acceptance `224b020d…` 全文，结论为 0 blocker／0 major／0 minor；`docs/tmp/260807-review-spec-carrier-final.md:4-9,38` 也直接绑定 current Spec `5e362822…` 并允许提交和继续实施。因此中间 provenance 缺口不削弱 current bytes 的最终独立 verdict。

**修复建议**：后续维护 Acceptance provenance 时，把中间 READY 自述改为“该中间报告不可独立恢复，最终证据由 `260807-review-acceptance-dual-carrier.md@224b020d…` 直接覆盖 current bytes”，或补入真实存在且内容身份可验证的中间报告路径与 SHA-256。不要继续把不可恢复的中间自述当作 current 放行依据。

### 其余事实性结论

1. **Spec 状态与 current-byte provenance 闭合**：`spec.md:5-7` 为 `FINALIZED`，冻结项目主 v1 producer＋upstream v1合法主路径 compatibility consumer，并明确当前 forward cardinality 仍是实现缺口；`260807-review-spec-carrier-final.md` 直接绑定 current `5e362822…`，允许 Spec 提交并继续实施。
2. **Acceptance 状态与绑定闭合**：`acceptance.md:7-11` 绑定 current Spec `5e362822…` 与 Architecture `c6088a…`，状态为 `FINALIZED_ACCEPTANCE_ORACLE`；`260807-review-acceptance-dual-carrier.md` 直接绑定 current `224b020d…`，允许 Acceptance 提交。
3. **Carrier 双格式一致**：Spec 的字段矩阵、项目主 v1 wire contract、upstream v1兼容合同、first-match识别顺序、Compatibility 与验收行为使用同一边界；Acceptance 的 REQ-05／NS-03 忠实转成独立 producer／consumer oracle，没有恢复“upstream 唯一 producer”或“全部 malformed 与 Node byte-exact”的旧合同。
4. **Cardinality／no-loss 一致**：两文档都要求一 Responses reasoning item 对应一 Anthropic thinking block、普通模式下非空 encrypted-only value-exact 往返、多 item不聚合／不错配；显式 strip只作为有意损失并保持 block cardinality。
5. **七域 manifest 完整**：route、request、response、buffering、retry、lifecycle、limits 七域均存在；request／response仅按最新 carrier 重裁更新 producer ownership、合法 compatibility范围和 malformed边界，其余 expected保持原合同。Architecture 的旧 carrier文字被明确排除，不能反向覆盖 Spec。
6. **产品状态没有误升级**：Acceptance 在状态、最终放行清单和处置表中持续把 oracle定稿与产品符合性分开。当前没有运行完整 required gates、单侧缺陷注入、live canary、capture provenance与local fault，因此产品必须继续为 `UNVERIFIED`。

## 主观建议

无。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `acceptance.md:9,11,400,404,429` | 当前状态多处复述，且中间评审 provenance 只有源文档自述、没有可恢复独立 artifact | **记为本轮 minor，不阻断提交**；后续以直接绑定 current `224b020d…` 的独立终审作为唯一 current 放行证据，并清理不可恢复的中间断言 |

除上述 provenance 重复／断链外，未发现 carrier政策在 Spec、Acceptance 与 Architecture参考边界之间重复实现且强弱不一，也未发现 Acceptance从非规范 Architecture生成第二套 expected。

## 最终放行结论

current `spec.md@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1` 与 `acceptance.md@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4` 的联合终审结果为 **0 blocker／0 major／1 minor**。Carrier 双格式、一 item一 block、普通模式 no-loss、七域 manifest、Architecture非行为 oracle边界及产品 `UNVERIFIED` 状态相互一致。**两份 current 文档均可提交，实施可继续；该结论不构成候选产品 `PASS`。**

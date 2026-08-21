# Implementation main／happy current-state 定向复评

- **评审范围**：current `docs/agents/anthropic-responses-bridge/implementation.md`，现场 SHA-256 `22cb196c4df1f419f1131a2e7787eca8beb878571260563299f53bcca813dff2`；仓库基线为 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。只复核 happy／usage 主线与 archive、main 434 门、四条后继线、merged-state 两项 major、产品 `UNVERIFIED` 与 living 边界；不重审四个新候选代码或 Spec／Acceptance／Architecture 全文。
- **总体 verdict**：**修复 major 后可继续。** Happy／usage 已进入 main、五个 archive refs、main 434 门、merged-state `0 blocker／2 major`、产品 `UNVERIFIED` 与 Implementation 继续 living 均准确；但四条后继线都已产生 clean candidate commit，文档仍反复写成“HEAD 在基线、只有未提交 WIP、尚无 commit”。该漂移会让执行者重复实施、错过候选评审，并误判没有回滚点。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：同调用验证物理 root、`main` 与完整 HEAD，并固定被评文档 SHA-256。逐项验证 happy／usage 五个 main commits均为 `80bc8f2…` 祖先；五个 `archive/260807-*` refs精确指向 `8301ee9…`、`7ddf173…`、`73a6aa1…`、`84a22c0…`、`aca3ced…`。固定 main 上独立执行全仓 pytest得到 `434 passed`，collect-only node ID计数同为434，Ruff为 `All checks passed!`，Pyright为 `0 errors, 0 warnings, 0 informations`。读取 `260807-review-main-happy-usage.md` 与 `260807-verify-main-happy-usage.md`，确认 merged-state `0 blocker／2 major`、pure-path `PASS` 未外推为产品通过。四个 worktree均为各 1 个 commit且 clean；在 `docs/tmp/**` 以四个完整 hash检索均无精确绑定报告。
- **双视角覆盖证据——第一人称执行模拟**：从“总体进度”进入时，旧文字会要求继续形成首个 candidate，实际已有 candidate，可能重复实现或把后续修复混入首个 checkpoint；从“当前并行开发线”进入评审时，会因“无可绑定 HEAD”而跳过现有 commit；从“回滚”执行时，会把四个独立 commit误当成仅存于工作树的 WIP；沿产品放行边界执行时，文档仍正确保留 merged-state 两项 major、完整 route／delivery 缺口与 `UNVERIFIED`。

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/implementation.md:58-61,69-74,183,211,244` — 四条后继线的 current identity 陈旧，且同一错误重复出现在进度表、并行线表、汇总、文档状态、回滚和结尾 — Git 现场显示四个 worktree均 clean并各自领先 `main@80bc8f2…` 一个提交：Route happy 为 `feat/anthropic-responses-route-happy@f3a5a768491c542224103a87b75e5bb39803ac4a`，提交 `feat: serve Anthropic requests via Responses`；Block delivery 为 `feat/anthropic-block-delivery@e3fceb1cd14c44527bf2625acee0873421386caf`，提交 `feat: add Anthropic block delivery skeleton`；Graceful timeout 为 `feat/systemd-graceful-timeout@865a5b71210e2436b36786b5de67146939d1e0f5`，提交 `feat: configure graceful shutdown timeout`；Rootless user install 为 `feat/systemd-user-install@e16c2a700f23f66535e7347ab7357518eb8e56bd`，提交 `feat: add rootless systemd user installer`。四个完整 hash在 `docs/tmp/**` 中均无命中，因此只能写“candidate commit已形成且worktree clean，尚无精确绑定该 HEAD 的review verdict”，不能预写通过。现文档却仍称“HEAD仍为基线”“有未提交WIP”“尚无checkpoint／candidate commit”，并称“没有可引用的新切片回滚点” — **精确修订**：①第58～61行分别改为上述完整HEAD，gate改为“candidate commit已形成、worktree clean、尚无精确绑定该HEAD的review verdict；不得外推为通过”；②第69～72行同样替换，保留`80bc8f2…`为建树base而非current HEAD；③第74、183、244行统一为“四线各有一个clean candidate commit，尚待逐HEAD review／verification，旧verdict不覆盖”；④第211行改为“四线已有各自独立候选回滚点，但依赖、逆向回滚边界及是否可回并仍待各自计划／评审确认”；⑤“下一步”四线动作先固定上述HEAD并执行声明范围gate与独立review，只有review要求继续修复时才追加提交并对新完整HEAD复评；⑥修订后全文检索并清除“当前HEAD仍为基线／只有未提交WIP／尚无candidate commit／没有回滚点”等旧current-state措辞。

## 已核实为准确的状态

- Happy四片与usage已作为 `a0d807f… → cdc080e… → a815948… → d913a03… → 80bc8f2…` 进入main；五个reviewed-source archive refs精确匹配文档。
- `main@80bc8f2…` 全仓pytest为434 passed，collect-only独立计数同为434；Ruff与Pyright全绿。该门只证明current主树回归，不证明完整Acceptance。
- Current merged-state verdict确为 `0 blocker／2 major`。空reasoning parity与冲突authoritative lifecycle仍是route／delivery组合前的开放修复门。
- 完整route、block delivery及完整Acceptance required gates尚未在同一候选闭合，产品继续为 `UNVERIFIED`；四个新commit不改变该结论。
- `implementation.md` 继续是living document。修复本轮漂移只放行候选评审与实施，不表示文档收口、产品`PASS`、部署完成或cutover获授权。

## 主观建议

未提出主观建议。本轮唯一发现有Git对象、worktree状态与文档执行路径共同支撑。

## 复评门

按上述清单修订后，固定新 `implementation.md` SHA-256，并重新验证四个完整candidate HEAD、clean状态与对应review报告状态。若候选期间前进，必须写新完整HEAD。修订版达到 `0 blocker／0 major` 后可继续living implementation；这仍不关闭merged-state两项代码major，也不升级产品`UNVERIFIED`。

# Semantic parity integration 最终回放门

- **评审范围**：只读审计 `/home/xp/src/ghc-api-proxy-py-integrate-semantic` 的 `integrate/260807-semantic-parity@04bdfcbf75bfa7e9709d55869c70106c49146db6`，对照 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 与 reviewed source `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`。范围包括单提交拓扑、两条路径、完整 source range 的 stable patch-id／tree／result blob 等价、current main preimage、精确 review／verification verdict 与 archive target；未重跑产品测试，未修改任何 Git ref、index、branch、commit、worktree 代码或运行态。
- **总体 verdict**：**可进入下一阶段；0 major 明确允许 checkpoint 后回放。** Integration HEAD 是 current main 上的单一 non-merge squash，结果与 reviewed source 完整两提交范围等价，精确 source review 为 `0 blocker／0 major／0 minor`，独立 verification 为 `PASS`，current main preimage 闭合。本报告形成最终回放 checkpoint；执行者仍须在实际回放前重验 identity、preimage 与工作树，回放后运行 main-side gate。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **checkpoint 结论**：**当前为 0 blocker／0 major，可 checkpoint；checkpoint 后可回放 `04bdfcbf75bfa7e9709d55869c70106c49146db6`。** 该结论只放行 semantic parity 这一独立切片从精确 current main preimage 回放，不表示提交已进入 main、main-side gate 已通过、完整 Anthropic Responses bridge 为 `PASS`、部署完成或 cutover 获授权。
- **archive 结论**：回放且 main-side gate 通过后，immutable archive target 必须精确指向 reviewed pre-squash source HEAD `f5bca39ac582911b61d278fd678ec9298ad0c08e`，不得指向 integration squash `04bdfcbf…` 或未来 main replay commit。当前 archive refs 中没有指向 `f5bca39…` 的 ref；本轮不创建 ref。

## 双视角覆盖证据

### 机械核对

- 每次 load-bearing shell 均在同一次调用内固定三棵树：主树物理 root、`main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`；integration 物理 root、`integrate/260807-semantic-parity@04bdfcbf75bfa7e9709d55869c70106c49146db6` 且 clean；source 物理 root、`fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` 且 clean。
- Integration 拓扑严格为 `80bc8f252b46c511f428af1d97159a5980ee9dc9 → 04bdfcbf75bfa7e9709d55869c70106c49146db6`，范围内恰有 1 个 non-merge commit、0 个 merge commit。Source 完整范围严格为 `80bc8f2… → 1cde3d58338eeefb3cf8040f970c3612d451668b → f5bca39ac582911b61d278fd678ec9298ad0c08e`；integration 的单提交形状是这两个 reviewed source commits 的内容等价 squash，而不是声称 source 自身只有一个提交。
- Integration 与 source 完整范围都只修改两条路径：`src/app/openai/responses_stream_parser.py`、`tests/unit/test_responses_stream_parser.py`。两个 path 集合精确相等，`git diff --check` 对 integration range 与 source range 均通过。
- Integration commit 的 `git show --binary` stable patch-id、`main..integration` stable patch-id 与 source 完整两提交 range stable patch-id 均为 `4e7b96c163311c775ad68b95057195c5a5f66202`。Integration tree 与 source tip tree 均为 `84cc08959fc61ede4b03d835ac07b696b5662204`。
- `src/app/openai/responses_stream_parser.py` 的 main commit、main index、main worktree 与 integration parent preimage blob均为 `f1eb3a0c901111ee24b363869e97ee0a3d6b2337`；integration 与 source result blob均为 `df3353f1a1882fd4035657563280bfa5f93989ab`。
- `tests/unit/test_responses_stream_parser.py` 的 main commit、main index、main worktree 与 integration parent preimage blob均为 `a0d045df8225904fe3ce941091d4715a0253ab97`；integration 与 source result blob均为 `bb77e15edce5c05f4abbf9c1a9b819635b804ec8`。
- `docs/tmp/260807-review-code-semantic-parity-r2.md` SHA-256 经 `sha256sum` 与 Python `hashlib.sha256` 交叉得到 `97e79e3826a863320dada383ced36c1eddce25dc9fd5b4a56566b292da4ba366`，精确绑定 source `f5bca39…`，结论为 `0 blocker／0 major／0 minor`、可 squash。
- `docs/tmp/260807-verify-semantic-parity-r2.md` SHA-256 经同样两种方法交叉得到 `3948065b70cca09409573e152c9cd18dc593115dfd5e7a5ff9377ec57d8f2886`，精确绑定 source `f5bca39…`，独立总体判定为 `PASS`，未发现阻断缺陷或行为偏差。
- 枚举 `refs/heads/archive/` 后，当前指向 `f5bca39…` 的 archive ref 数为 0；因此 archive 仍是回放并完成 main-side gate 后的动作，不是当前已完成事实。

### 第一人称执行

- 作为回放执行者，从 current main `80bc8f2…` 应用 integration 单提交时，两条 touched path 的 commit／index／worktree bytes均与 commit parent preimage一致，不需要冲突猜测、整文件选边或吸收并行文档 WIP。
- 回放内容不是未经评审的新实现：integration 的 patch-id、最终 tree 与两个 result blobs分别等于 reviewed source 的完整两提交 range和 exact tip。单一 squash保留最终内容，但 archive仍指向 source `f5bca39…`，从而保留 review／verification provenance。
- 精确 source code review 已同时检查错误状态能否穿过与合法状态会否被误拒；独立 verification 另执行 empty／encrypted reasoning、unknown summary typed reject、authoritative conflict、item.done-only function及 permissive正控。因此执行者可以消费已有 `0 major／PASS`，但不能把 integration身份对账替代实际回放后的 main-side regression gate。
- 若实际执行时 main HEAD不再是`80bc8f2…`、任一 touched path不再匹配上述preimage、integration／source ref漂移或工作树出现相关重叠，应立即停止并重新审计，不得沿用本 checkpoint。
- 回放成功后先运行 semantic main-side gate；只有 gate通过后才创建精确指向`f5bca39…`的immutable archive并进入后续route／block流程。不得先建archive冒充回放完成，也不得把semantic局部绿灯外推为完整产品`PASS`。

## 事实性发现

未发现问题。Integration 的单 non-merge commit、两条路径、完整 source range 等价性、current main preimage、精确 `0 major／PASS` 证据与 archive target均满足最终回放 checkpoint。

## 主观建议

无。

## 结构怪味与替代方案复核

- **扫描范围**：integration 单提交拓扑、source 两提交 provenance、两条 touched path、review／verification绑定与 archive生命周期。
- **判据**：尾提交是否冒充完整 range、patch-id 是否缺少 result blob／tree 交叉验证、source verdict 是否错误外推到不同 bytes、archive 是否提前建立或错指 squash、checkpoint 是否被误写为产品 `PASS`。
- **结果**：未发现上述怪味。Integration 使用一个内容等价 squash是明确的回放载体，source完整两提交仍由reviewed HEAD与archive target保留provenance；无需引入第三方库，也没有应在本轮另行重构的生产代码。

## 结论

本轮为 **0 blocker／0 major／0 minor**。`integrate/260807-semantic-parity@04bdfcbf75bfa7e9709d55869c70106c49146db6` 是 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 上的单一 non-merge、两路径、内容等价 squash，精确承载已获代码 `0 major` 与独立 verification `PASS` 的 source `f5bca39ac582911b61d278fd678ec9298ad0c08e` 完整范围。**当前明确可 checkpoint；checkpoint 后重验现场 identity／preimage即可回放，回放后必须完成 main-side gate，随后 archive精确指向 `f5bca39…`。**

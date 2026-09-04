# Semantic parity 回放现场恢复审计

- **评审范围**：只读恢复 semantic parity 回放现场。主树固定为 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`；integration 固定为 `/home/xp/src/ghc-api-proxy-py-integrate-semantic` 的 `integrate/260807-semantic-parity@04bdfcbf75bfa7e9709d55869c70106c49146db6`；reviewed source 固定为 `/home/xp/src/ghc-api-proxy-py-semantic-parity` 的 `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`。消费 `docs/tmp/260807-final-semantic-replay-gate.md`，重新核对 WSL 重启后的 main preimage、两条 touched path 的 commit／index／worktree blobs、integration／source refs与 clean 状态、内容等价、四文档 current checkpoint及 archive 前置状态。本轮未运行 `cherry-pick`，未修改 Git ref、index、branch、commit、代码或运行态；唯一写入是本报告。
- **总体 verdict**：**可进入下一阶段；0 major 明确允许四文档 checkpoint 后回放 `04bdfcbf75bfa7e9709d55869c70106c49146db6`。** WSL 重启后现场身份、preimage、integration／source 内容等价及 clean 状态均未漂移。该结论不表示回放已执行、main-side gate 已通过、完整 bridge 已 `PASS`、部署完成或 cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **checkpoint 结论**：四份 current living docs 均为 `0 blocker／0 major`，可形成本轮四文档 checkpoint。Acceptance 与 Readiness 分别由精确 current-byte 独立报告闭合；本轮对 current Implementation 与 current Systemd Plan bytes完成独立双视角复评，未发现 blocker、major 或 minor。四文档当前仍是主树 tracked WIP，index 为空；本报告只确认内容 checkpoint 门，不声称已形成 Git checkpoint commit。
- **archive 结论**：只有回放成功且 semantic main-side gate 通过后，才可创建 immutable archive；target 必须精确为 reviewed pre-squash source `f5bca39ac582911b61d278fd678ec9298ad0c08e`，不得指向 integration squash `04bdfcbf…` 或未来 main replay commit。当前指向该 source 的 `refs/heads/archive/*` 数量仍为 0。

## 双视角覆盖证据

### 机械核对

- 每次 load-bearing shell 都在同一次调用内 gate 对应物理 root、cwd、分支与完整 HEAD；主树同时验证 `HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`，integration 与 source 同时验证各自 branch ref 等于目标 HEAD。
- Main tree 仍为 `a149d1dc5fdfca36e09c938380e95df34faa77dd`。`src/app/openai/responses_stream_parser.py` 的 main commit／index／worktree与 integration parent blob均为 `f1eb3a0c901111ee24b363869e97ee0a3d6b2337`；`tests/unit/test_responses_stream_parser.py` 的四层 blob均为 `a0d045df8225904fe3ce941091d4715a0253ab97`。
- Integration root、branch与 ref精确为 `integrate/260807-semantic-parity@04bdfcbf75bfa7e9709d55869c70106c49146db6`，parent精确为 current main，tracked diff、cached diff与untracked count均为0。两个结果 path 的 commit／index／worktree blobs分别为 `df3353f1a1882fd4035657563280bfa5f93989ab` 与 `bb77e15edce5c05f4abbf9c1a9b819635b804ec8`。
- Source root、branch与 ref精确为 `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e`，merge-base精确为 current main，tracked diff、cached diff与untracked count均为0。两个结果 path 的 commit／index／worktree blobs与 integration逐项相等。
- Integration 范围严格包含1个non-merge commit、0个merge commit；source范围严格包含2个non-merge commits、0个merge commits，拓扑为 `80bc8f2… → 1cde3d5… → f5bca39…`。两者均只修改 parser与其unit test两条路径，且两个range的`git diff --check`均通过。
- Integration 与 source完整range的stable patch-id均为 `4e7b96c163311c775ad68b95057195c5a5f66202`，最终tree均为 `84cc08959fc61ede4b03d835ac07b696b5662204`。这与两个result blobs共同证明 integration 是reviewed source完整范围的内容等价squash，而不是仅等价于source尾提交。
- 四文档 SHA-256 均由 `sha256sum` 与 Python `hashlib.sha256` 两种原理交叉一致：Acceptance `6457b896ff8ae2f865e7d92443cfe893504b5757b482b4fbe61174072ff3f001`；Implementation `ccdf6edf83aa9703a6a95a74801e11e433df8248d76d7b9f077ab18664d5ffe2`；Readiness `ad36f43aea165b2a8cb1d6eaa6bbc08a0eca75278e6c7b6f1b623a514e44fd0a`；Systemd Plan `0f372ab29b3b4852c6cfb387c923bcc2e9da295e3469c117ab20881adb1e180e`。
- Acceptance current bytes由 `docs/tmp/260807-review-acceptance-empty-reasoning-r2.md` 精确绑定并给出 `0 blocker／0 major／0 minor`、可checkpoint；Readiness current bytes由 `docs/tmp/260807-review-readiness-current-r8.md` 精确绑定并给出 `0 blocker／0 major／0 minor`、可checkpoint。本轮完整通读并独立复评 current Implementation 与 current Systemd Plan：两者一致使用 rebuilt systemd code-only路线 `862f4cfa… → 2ec0cb8…`，一致使用bridge successor路线 `04bdfcb… → 088d66d… → c43db35…`，一致保持living／产品`UNVERIFIED`／`NO_CUTOVER`边界，未发现 blocker、major或minor。
- Main tracked WIP精确为上述四份living docs，cached diff为空。其存在不会改变两条代码path的preimage，但必须先形成四文档checkpoint；本轮未暂存、提交或覆盖这些WIP。
- 枚举`refs/heads/archive/`后，当前指向`f5bca39ac582911b61d278fd678ec9298ad0c08e`的archive ref数量为0，符合“回放＋main-side gate后才归档”的顺序。

### 第一人称执行

- 作为四文档checkpoint执行者，我先以current hash逐份消费Acceptance、Implementation、Readiness与Systemd Plan。四份文档都把checkpoint解释为“允许继续living实施与逐片回放”，没有把它写成完整产品`PASS`、部署完成或cutover授权；current Implementation与Systemd Plan也不再沿用旧systemd-next回放链，而是明确使用排除Plan patch的code-only路线。
- 作为semantic回放执行者，我从current main `80bc8f2…`进入时，两条目标path的commit／index／worktree bytes均精确等于integration parent preimage；integration本身clean且只改变这两条路径，因此无需冲突猜测、整文件选边、stash、restore或吸收并行四文档WIP。
- 回放载荷不是未经评审的新实现：integration单提交的range patch-id、最终tree与两个result blobs均等于reviewed source完整两提交range；`docs/tmp/260807-review-code-semantic-parity-r2.md`给出`0 blocker／0 major／0 minor`且可squash，`docs/tmp/260807-verify-semantic-parity-r2.md`给出scoped `PASS`。
- 执行顺序只有一个：先形成四文档checkpoint；随后重验main、integration ref、两path preimage与clean状态；再回放`04bdfcbf75bfa7e9709d55869c70106c49146db6`；回放成功后立即运行semantic main-side gate。任何身份、preimage或gate失败都必须停止，不能继续route／block，也不能创建archive冒充完成。
- 只有semantic main-side gate通过后，才创建精确指向`f5bca39ac582911b61d278fd678ec9298ad0c08e`的immutable archive。之后才进入successor route `088d66d…`；不得把semantic局部绿灯外推为完整stream、完整bridge或生产readiness。

## 事实性发现

未发现问题。WSL重启后main preimage、integration／source refs、两条path的commit／index／worktree blobs、integration／source clean状态、完整range内容等价及archive前置状态均未漂移。四份current living docs均满足`0 blocker／0 major`内容checkpoint门。

## 主观建议

无。

## 结构怪味与方案反思

- **扫描范围**：main两条代码path与四份tracked living docs、integration单提交、source两提交range、semantic review／verification、archive生命周期。
- **判据**：旧report是否被错误外推到current bytes、source尾提交是否冒充完整range、patch-id是否缺少tree／blob交叉验证、tracked文档WIP是否与代码preimage混淆、archive是否提前建立、semantic scoped `PASS`是否被外推为完整产品或cutover状态。
- **处置**：未发现需要修复或登记backlog的结构问题。旧四文档集合审计与旧Implementation／Plan reviews绑定历史bytes，未被用于覆盖current bytes；本轮直接复评current内容。Integration使用内容等价squash作为回放载体，reviewed source由回放后archive保留provenance。
- **内部替代方案**：直接从source两提交逐个回放会偏离已完成的integration审计；压缩后续route／block边界会失去逐片归因。保持现有semantic单片回放及逐片main-side gate是当前最可靠的项目内路径。
- **判据判别力**：commit／index／worktree三层preimage能区分代码path被WIP污染；stable patch-id加最终tree与result blobs能区分patch语义与最终内容；四文档hash加逐份内容复评能区分“文件存在”与“current checkpoint已闭合”。
- **成熟第三方方案**：本轮是Git对象与文档证据链审计，Git原生对象、diff与patch-id已足够，不存在需要引入第三方库的机制。

## 结论

本轮为 **0 blocker／0 major／0 minor**。WSL重启后semantic parity回放现场未漂移，四份current living docs明确达到0 major内容checkpoint。**四文档checkpoint后可回放`04bdfcbf75bfa7e9709d55869c70106c49146db6`；回放后必须先完成semantic main-side gate，随后archive精确指向reviewed source`f5bca39ac582911b61d278fd678ec9298ad0c08e`。** 本轮未执行回放、未创建archive、未改变Git状态或运行态。

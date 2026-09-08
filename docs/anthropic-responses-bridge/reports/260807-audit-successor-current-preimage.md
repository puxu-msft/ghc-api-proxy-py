# Bridge successor current-preimage 只读审计

- **评审范围**：current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、四份 tracked docs WIP、successor integration `04bdfcbf75bfa7e9709d55869c70106c49146db6` → `088d66d3f12bd39be7ce7f61877336f490e7dbdb` → `c43db35a7a5851225b55ce31b8edbec2cf90917f`，以及 `docs/tmp/260807-final-successor-replay-gate.md`。本轮只复核 checkpoint 后的补丁适用性、路径隔离与 archive targets；不重做 code review、verification、测试或产品验收，不执行 checkpoint、代码回放、归档、部署或 cutover。唯一仓库写入是本报告。
- **总体 verdict**：**可进入下一阶段。条件式 0-major 回放门成立：四份 docs 各自形成 current checkpoint 后，可按 `04bdfcb… → 088d66d… → c43db35…` 逐片应用。** 每片仍须在真实 main 上重验目标路径 preimage、执行对应 main-side gate，失败即停。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **边界**：本报告不声称四文档 checkpoint 已经提交，也不把 successor scoped `PASS` 外推为完整 bridge `PASS`。四文档 checkpoint 后全树 OID 会包含文档变化，因此真实回放应核对每片目标路径的 preimage／result blobs与四文档 bytes 保持，不应要求全树 OID继续等于旧 integration commit tree。

## 双视角覆盖证据

### 机械核对

- 主树固定为 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`；真实 index 中四文档 blob均仍等于 HEAD，worktree blob均已变化。Tracked WIP 精确为 `acceptance.md`、`implementation.md`、`service-cutover/readiness.md`、`systemd-runtime/plan.md` 四项。
- Successor 拓扑严格线性：`80bc8f2… → 04bdfcb… → 088d66d… → c43db35…`，零 merge commit。三片路径数分别为 2、10、3，共15条且彼此零重叠；与四份 docs路径交集为零。
- 在自动清理的仓库外临时目录中，以 `main@80bc8f2…` tree加四份 current docs bytes构造合成 checkpoint preimage。三片依次通过 `git apply --check`与 apply；每片所有目标路径的应用前 blob等于其 integration parent，应用后 blob等于对应 integration commit，四文档 SHA-256全程不变。最终15条result blobs精确等于`c43db35…`。
- Final replay gate SHA-256为`65bf2e23d9a85a4fffeb9794735646710b7aa3a21bf2b4c8e00acca6808cdb96`，绑定同一main与三片并给出0 blocker／0 major。Merged-state review与scoped verification分别绑定`c43db35…`；本轮仅消费其身份和既有verdict，不重新评审代码。
- Archive targets固定为semantic `f5bca39ac582911b61d278fd678ec9298ad0c08e`、route `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`、block `e506bf87318424e4075b6422772ee0c7e9b8694a`。当前`refs/heads/archive/`对三者的精确指向计数均为0；只能在对应slice真实回放且main-side gate通过后建立，不得指向integration squash或未来main replay commit。

### 第一人称执行

- 先完成四份docs各自的current checkpoint；若任一文档bytes或其checkpoint门漂移，停止并重新审计，不把本报告当作文档内容复评。
- 从checkpoint后的actual main开始，先核对semantic两条path仍与`80bc8f2…` preimage一致，应用`04bdfcb…`并运行semantic gate；通过后才archive `f5bca39…`并进入route。
- Route阶段核对十条path与`04bdfcb…` postimage一致，应用`088d66d…`并运行route／hooks／header gate；通过后才archive `dd376d6…`。Block阶段同理核对三个新增path仍不存在，应用`c43db35…`并运行parser→delivery／single-writer gate；通过后才archive `e506bf8…`。
- 三片完成后重跑merged-state gate。四文档必须保留checkpoint bytes；不得用旧integration全树OID不相等误判冲突，也不得用15条代码result blobs相等冒充完整产品验收。

## 事实性发现

未发现问题。四文档路径与successor 15条路径完全隔离；四文档进入基线后，三片仍可按既定顺序逐片应用并保持文档bytes不变。

## 主观建议

无。

## 结论

本轮为 **0 blocker／0 major／0 minor**。四份docs形成current checkpoint后，`04bdfcb… → 088d66d… → c43db35…` 的逐片应用门成立；真实执行仍须逐片重验preimage、运行main-side gate，并仅在该片通过后建立对应reviewed-source archive。完整bridge继续由后续Acceptance required gates裁决。

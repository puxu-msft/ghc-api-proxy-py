# Anthropic Responses bridge successor 最终逐片回放门

- **评审范围**：只读在独立临时 index 中从 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、tree `a149d1dc5fdfca36e09c938380e95df34faa77dd` 起，严格按 semantic `04bdfcbf75bfa7e9709d55869c70106c49146db6` → route `088d66d3f12bd39be7ce7f61877336f490e7dbdb` → block `c43db35a7a5851225b55ce31b8edbec2cf90917f` 逐片执行 cached `git apply --check` 与 apply，核验每片 parent／preimage、path 集合、result blobs、reviewed source range 等价和 post-tree，并对账 main-side targeted gates、archive targets 与最终 successor tree。未运行真实 main 回放后的测试，未修改 main ref、HEAD、真实 index、worktree代码、服务或数据；唯一仓库写入是本报告。
- **总体 verdict**：**可进入下一阶段；当前为 0 blocker／0 major，明确可 checkpoint，checkpoint 后可按 `04bdfcb… → 088d66d… → c43db35…` 逐片回放 main。** 三片在临时 index 中均从精确 parent tree 通过 apply check，逐片 post-tree 精确等于对应 integration commit tree，最终 tree 精确等于 successor tip tree。真实回放仍须每片先重验当时 main preimage、回放后完成对应 main-side gate，最后完成 merged-state gate；本 verdict 不表示三片已经进入 main、main-side gates 已通过、完整 Responses stream 产品为 `PASS`、部署完成或 cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **checkpoint 结论**：精确绑定 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 与 successor `c43db35a7a5851225b55ce31b8edbec2cf90917f`。`docs/tmp/260807-review-code-bridge-successor.md` 已给出 merged-state `0 blocker／0 major／0 minor`，`docs/tmp/260807-verify-bridge-successor.md` 对本轮 scoped 轴判为 `PASS`；本轮又独立完成逐片临时 index 回放与 tree／blob 对账。因此 **0 major checkpoint 已明确形成，checkpoint 后可回放**。若 main、三片 OID、source refs、任一 preimage 或相关工作树 bytes 漂移，本 checkpoint 立即失效，必须重新审计。
- **archive 结论**：三个 reviewed pre-squash source target 固定为 semantic `f5bca39ac582911b61d278fd678ec9298ad0c08e`、route `dd376d6f1e9dc2997bc2f95d03a352fed4df1412`、block `e506bf87318424e4075b6422772ee0c7e9b8694a`。当前 `refs/heads/archive/` 对三者的精确指向计数均为 0。每个 archive 只能在对应 slice 已真实回放 main 且该 slice 的 main-side gate 通过后建立，必须指向 reviewed source HEAD，不得指向 integration squash或未来 main replay commit；本轮不创建任何 ref。

## 双视角覆盖证据

### 机械核对

- 每次 load-bearing shell 均在同一调用内打印并断言物理 root `/home/xp/src/ghc-api-proxy-py`、branch `main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。三片拓扑严格线性：`80bc8f2… → 04bdfcb… → 088d66d… → c43db35…`；每片 commit 的唯一 parent 精确等于上一节点。
- 临时 index 以 `GIT_INDEX_FILE=/tmp/ghc-successor-replay-91e4/index` 隔离，并从 `80bc8f2…^{tree}` 初始化。真实 main index SHA-256 在预演前后均为 `663fbf24e628c1eec203cd2c5ef46c4a1c697e050faff949539f06b179c85cfc`，main ref 与 HEAD 前后均为 `80bc8f2…`。临时目录在成功后删除；真实 index、ref与 worktree代码未被预演修改。
- 三片完整 path 集合分别为 2、10、3 条，彼此无重叠；每片 integration path 集合与对应 source 的 `80bc8f2… → source-tip` 完整 range path 集合排序后哈希相等。每个已存在 preimage 均同时匹配 commit、真实 main index与真实 main worktree blob；新增文件在 commit、index与 worktree均为 `ABSENT`。
- 每片 stable patch-id 与对应 reviewed source 完整 range 相等：semantic `4e7b96c163311c775ad68b95057195c5a5f66202`，route `d990e5457fc1fa29392cf80f5c71957e98a1154b`，block `b44e8ca968ecaf63132da5d20ac432e2ab41ef2b`。每条 result blob也逐路径等于 source tip，避免仅以 patch-id自证。
- 临时 index 的每片 `git apply --cached --check` 均通过；post-tree 依次为 `84cc08959fc61ede4b03d835ac07b696b5662204`、`ccf8ec498a6dc5c70f9c22f7b8557adb6ca34f37`、`cf67198a69c9d183ff08f58213198f6ee172af31`，分别精确等于 `04bdfcb…`、`088d66d…`、`c43db35…` 的 commit tree。
- 最终临时 index tree `cf67198a69c9d183ff08f58213198f6ee172af31` 与 successor tip `c43db35…^{tree}` 精确相等。该结论同时依赖逐片 parent tree门、逐路径 blob门和最终 tree门，不是只把现成 successor tree重新打印一次。
- 精确 source code reviews分别为 semantic R2、route R3、block R2，均为 `0 blocker／0 major／0 minor`；semantic与route各有绑定精确 source HEAD的独立 `PASS`，block轴由绑定 successor `c43db35…` 的独立 verification判为 scoped `PASS`。Merged-state review又绑定同一 successor HEAD并明确允许三片回放。
- `refs/heads/archive/` 的 objectname枚举显示对 `f5bca39…`、`dd376d6…`、`e506bf8…` 的精确指向计数分别为 0、0、0；archive仍是每片真实回放和 main-side gate后的动作，不是本轮已完成事实。

### 第一人称执行

- 作为 semantic回放执行者，我先要求真实main仍为`80bc8f2…`，两条path仍匹配slice 1 preimage；应用`04bdfcb…`后必须得到tree`84cc089…`，立即运行semantic parser／reasoning parity gates。只有这些gate通过，才允许建立指向`f5bca39…`的archive并进入route。
- 作为route回放执行者，我不从原始`80bc8f2…`直接应用，也不只摘source尾提交`dd376d6…`；我要求当前main tree等于semantic post-tree`84cc089…`，十条path匹配slice 2 preimage，再应用完整route squash`088d66d…`并得到tree`ccf8ec4…`。随后运行真实ASGI route／header／hooks矩阵和持久化targeted tests；通过后archive精确指向`dd376d6…`。
- 作为block回放执行者，我要求当前main tree等于route post-tree`ccf8ec4…`，三个新增path仍全部不存在；应用`c43db35…`后得到tree`cf67198…`，运行parser→typed delivery、terminal与single-writer gates。通过后archive精确指向`e506bf8…`。
- 作为最终验收者，我不把三个source各自绿色或临时index可应用当作main回放完成。三片进入main后还要重跑merged-state 10 smoke、两个完整smoke文件、semantic parser unit、全仓pytest、Ruff、Pyright，并重新对账最终main tree与15条result blobs。完整Responses stream因仍无生产route→parser／delivery接线而继续为`UNVERIFIED`。
- 任一片gate失败时停止在该片，不创建该片archive，也不继续后片。不得用后续整体验证掩盖前片失败，不得把临时index预演的`PASS`写成真实main测试已通过。

## 逐片 identity、preimage 与 result blobs

### Slice 1：semantic

- Integration：`04bdfcbf75bfa7e9709d55869c70106c49146db6`。
- Parent：`80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- Reviewed source：`f5bca39ac582911b61d278fd678ec9298ad0c08e`。
- Pre-tree：`a149d1dc5fdfca36e09c938380e95df34faa77dd`。
- Post-tree：`84cc08959fc61ede4b03d835ac07b696b5662204`。
- Stable patch-id：integration／source均为`4e7b96c163311c775ad68b95057195c5a5f66202`。

| Path | Preimage blob | Result／source blob |
|---|---|---|
| `src/app/openai/responses_stream_parser.py` | `f1eb3a0c901111ee24b363869e97ee0a3d6b2337` | `df3353f1a1882fd4035657563280bfa5f93989ab` |
| `tests/unit/test_responses_stream_parser.py` | `a0d045df8225904fe3ce941091d4715a0253ab97` | `bb77e15edce5c05f4abbf9c1a9b819635b804ec8` |

### Slice 2：route

- Integration：`088d66d3f12bd39be7ce7f61877336f490e7dbdb`。
- Parent：`04bdfcbf75bfa7e9709d55869c70106c49146db6`。
- Reviewed source：`dd376d6f1e9dc2997bc2f95d03a352fed4df1412`。
- Pre-tree：`84cc08959fc61ede4b03d835ac07b696b5662204`。
- Post-tree：`ccf8ec498a6dc5c70f9c22f7b8557adb6ca34f37`。
- Stable patch-id：integration／source均为`d990e5457fc1fa29392cf80f5c71957e98a1154b`。

| Path | Preimage blob | Result／source blob |
|---|---|---|
| `src/app/anthropic/client.py` | `48d374e84e0a65be286b0ad126ee9240e327d8cf` | `2c05425a2b0a90b5a03488a7919dbb5d0470c1ce` |
| `src/app/anthropic/header_policy/__init__.py` | `4a01d7b49a3b26436d8c902cad9fb2e5298e36ba` | `819cb95965b9d2f4f814fdf576e612efde303d93` |
| `src/app/config/settings.py` | `2fcf4c39fce438dbbc19db3741c41c6f6daae3a9` | `b6983eee29ec898cc8b1cfc6bb31c8ffd02a183d` |
| `src/app/pipeline/context.py` | `293b87fe47bcff49d9d938726e25507355ccfe39` | `9c8074fbb38c9a663c229e0c7666af86a8f3b218` |
| `src/app/pipeline/executor.py` | `c1a2d6e3d012eaba6346a6905665735edf14da9c` | `75ace9cbbfadec87e35501b1cea4b54023a81fa5` |
| `src/app/routes/anthropic.py` | `b2b639195ab3e8546cfcad7b3f85d4f4220a6c86` | `d6905a86f556c7dd008751c00276d44875b0f5e0` |
| `src/app/upstream/bootstrap.py` | `e1083db748d206c12291a88c79efef162d6a3270` | `48281355e305d76906ae4cd590ee939b7c7a20c6` |
| `tests/component/test_pipeline_executor.py` | `f9264fd2ab708dd5440d05b8af4e86fb55c9c982` | `8b5f7dcf4deca9abc08471ae14378ff83e4e7856` |
| `tests/smoke/test_anthropic_responses_route.py` | `ABSENT` | `54f3e6c3788463edb0d0620a31d057da88f84e80` |
| `tests/smoke/test_systemd_units.py` | `78866bede2150838b8bbaaf155f9dc4268438dcc` | `7e67c524a7dbec9b14ef8ff75de0ba032c7b1d96` |

### Slice 3：block

- Integration：`c43db35a7a5851225b55ce31b8edbec2cf90917f`。
- Parent：`088d66d3f12bd39be7ce7f61877336f490e7dbdb`。
- Reviewed source：`e506bf87318424e4075b6422772ee0c7e9b8694a`。
- Pre-tree：`ccf8ec498a6dc5c70f9c22f7b8557adb6ca34f37`。
- Post-tree：`cf67198a69c9d183ff08f58213198f6ee172af31`。
- Stable patch-id：integration／source均为`b44e8ca968ecaf63132da5d20ac432e2ab41ef2b`。

| Path | Preimage blob | Result／source blob |
|---|---|---|
| `src/app/delivery/__init__.py` | `ABSENT` | `e9efab0f9877a1f4d5f4e9881e754a76d94e43d5` |
| `src/app/delivery/anthropic_sse.py` | `ABSENT` | `932567e1eec3d26934a761ff5c59bd0ec240de19` |
| `tests/smoke/test_anthropic_block_delivery.py` | `ABSENT` | `2c1f4bfcd26cbdcb292e9ca3bd746f26341b34b8` |

## Main-side targeted gates 清单

以下均是**真实main逐片回放后的待执行门**，不是本轮已运行事实。每次运行必须在同一shell调用内打印并断言物理root、branch、当时完整main HEAD与import path；测试执行与`--collect-only`使用同一选择器交叉核对，不能只看一个绿色摘要。

### Gate S1：semantic回放后

1. 身份／preimage后验：main tree必须为`84cc08959fc61ede4b03d835ac07b696b5662204`，两条result blob与Slice 1表一致，真实index／worktree与新main commit一致。
2. Targeted pytest：`tests/unit/test_responses_stream_parser.py`、`tests/unit/test_responses_reasoning.py`、`tests/unit/test_responses_anthropic_nonstream.py`。既有source gate仅记录runner摘要`43 passed`，该数字未用不同原理交叉验证，不作为本报告断言；main侧须重新执行并以同一选择器`--collect-only`交叉核对，不得直接沿用43。
3. Targeted Ruff／Pyright：parser、reasoning normalizer、non-stream converter及上述三份测试；退出码必须为0。
4. 独立semantic oracle：empty／encrypted reasoning、unknown summary typed reject、authoritative conflict、item-done-only function与合法permissive正样本均须通过。
5. 通过后才可建立精确指向`f5bca39ac582911b61d278fd678ec9298ad0c08e`的immutable archive；失败则停止，不进入Slice 2。

### Gate S2：route回放后

1. 身份／preimage后验：main tree必须为`ccf8ec498a6dc5c70f9c22f7b8557adb6ca34f37`，十条result blob与Slice 2表一致，真实index／worktree与新main commit一致。
2. 持久化targeted pytest：`tests/smoke/test_anthropic_responses_route.py`、`tests/http/test_anthropic_routes.py`、`tests/component/test_pipeline_executor.py`；执行与`--collect-only`选择器一致。
3. 真实ASGI独立矩阵：unknown capability、Responses override mismatch、selected Responses＋`stream=true` typed reject均要求`REQUEST_RECEIVED → ERROR → FINALIZE`、零attempt、零upstream、History同一identity各一次；另验Responses non-stream success／header filtering／429 error与dual-capability Messages回归。
4. Observer正控：`ERROR`／`FINALIZE` observer抛错仍须被记录并隔离，原typed rejection、零network和单History终态不变；finalizer被旁路时同一oracle须按缺失terminal lifecycle原因转红。
5. Targeted Ruff／Pyright覆盖十条变更路径及直接route／hooks／header依赖；退出码必须为0。
6. 通过后才可建立精确指向`dd376d6f1e9dc2997bc2f95d03a352fed4df1412`的immutable archive；失败则停止，不进入Slice 3。

### Gate S3：block回放后

1. 身份／preimage后验：main tree必须为`cf67198a69c9d183ff08f58213198f6ee172af31`，三个result blob与Slice 3表一致，真实index／worktree与新main commit一致。
2. Targeted pytest：完整`tests/smoke/test_anthropic_block_delivery.py`，并与`tests/unit/test_responses_stream_parser.py`共同运行；执行与`--collect-only`选择器一致。
3. Parser→delivery矩阵：同一item多parts、较晚item先完成、合法零block source、连续source prefix、typed/manual隔离、incomplete／failed／error terminal与missing usage均须保持合同。
4. Single-writer正控：并发consume和deliver／finish不得重叠writer；仅在进程内旁路operation lock时，同一oracle必须观察到并发write并按目标原因转红，恢复后重新绿色。
5. Targeted Ruff／Pyright覆盖delivery实现、parser接缝与相关测试；退出码必须为0。
6. 通过后才可建立精确指向`e506bf87318424e4075b6422772ee0c7e9b8694a`的immutable archive。

### Gate M：三片main merged state

1. 精确定义的10 smoke：完整route smoke选择器，加block文件中的parser→delivery多part顺序与并发block／terminal single-writer两项；在successor tip的既有执行／收集基线均为10项。
2. 完整两个smoke文件：`tests/smoke/test_anthropic_responses_route.py`与`tests/smoke/test_anthropic_block_delivery.py`；successor tip既有执行／收集基线均为24项。
3. Semantic parser unit：完整`tests/unit/test_responses_stream_parser.py`；successor tip既有执行／收集基线均为20项。
4. 全仓pytest：`tests`；successor tip既有执行／收集基线均为468项。真实main若计数不同，必须解释新增／删除来源，不得删测试凑数或硬改门。
5. 全仓Ruff与全仓Pyright必须退出码为0；Pyright文字计数只作工具摘要，不单独充当正确性oracle。
6. 最终main tree必须为`cf67198a69c9d183ff08f58213198f6ee172af31`，15条result blob必须与本报告三表一致，且生产caller扫描仍确认route当前对Responses stream typed reject、delivery／parser无生产route caller、没有第二writer或第二delivery finalizer。
7. 重新取得绑定最终main HEAD的merged-state review `0 blocker／0 major`与独立scoped verification `PASS`。完整stream仍标记`UNVERIFIED`，直到真实route→parser→delivery→ASGI SSE生产接缝及同请求E2E建立。

## 事实性发现

未发现问题。三片严格线性、逐片preimage／paths／result blobs与reviewed source range闭合，临时index逐片apply check及apply均通过，逐片post-tree和最终tree精确匹配，main真实index与ref保持不变；现有精确review／verification满足0 major checkpoint。

## 主观建议

无。

## 结构怪味与替代方案复核

- **扫描范围**：三片commit边界、15条path、source provenance、临时index隔离、逐片gate、archive生命周期，以及route／delivery生产调用边。
- **判据**：只验最终tree而漏逐片preimage、用尾提交代表完整source range、对新增path伪造preimage、用source绿灯替代main-side gate、提前建archive、把typed delivery骨架冒充stream E2E、或把三片压成一个不可归因整体。
- **结果**：未发现上述怪味。保留semantic／route／block三个commit边界是当前更好的内部方案，便于逐片归因、停止、回滚与archive provenance；无需第三方库。未来真实Responses stream wiring建立后，必须新增同一request owner的hooks＋parser＋delivery＋ASGI SSE E2E与变异正控，该长期正确事项未被本checkpoint删除。

## 结论

本轮为 **0 blocker／0 major／0 minor**。从 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 起，在隔离临时index中按`04bdfcb… → 088d66d… → c43db35…`逐片应用全部通过；每片pre-tree、path集合、preimage、result blobs、source完整range patch-id与post-tree均闭合，最终tree精确等于successor tip的`cf67198a69c9d183ff08f58213198f6ee172af31`，main真实index与ref未变化。

**0 major checkpoint已明确形成，checkpoint后可按三片顺序回放。** 真实回放必须逐片重验preimage、逐片完成main-side gate并在通过后分别archive`f5bca39…`、`dd376d6…`、`e506bf8…`，最终完成merged-state gate；本报告不替代这些尚未执行的main-side证据。

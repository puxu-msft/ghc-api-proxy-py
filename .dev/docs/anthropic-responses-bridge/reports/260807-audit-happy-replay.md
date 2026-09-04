# Happy integration → current main 只读回放预检

- **评审范围**：只读预检 current `/home/xp/src/ghc-api-proxy-py` 的 `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 与 `/home/xp/src/ghc-api-proxy-py-integrate-happy` 的 `integrate/260807-bridge-happy-path@7e4b642be8bd526d8f20f3f8d7e2d7848278a443`。核验 frozen foundations base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 的 main-side 语义落地、happy 四提交拓扑／paths／稳定 patch-id／blob oracle、四个 reviewed source HEAD 与未来 archive targets、R2／verify 结论，并以独立临时 index 从 current main 逐提交模拟三方应用。本轮不修改 main index、工作树、refs、branches 或 worktree registration，不执行真实 cherry-pick，不运行回放后的产品 gate。
- **总体 verdict**：**可进入下一阶段。0 major，happy 四 commits 明确可按 `1ed13ad → 80b3cfa → c950912 → 7e4b642` 逐个回放 current main。** 临时 index 实际应用四片均无冲突，逐片 patch-id 与 changed blobs 均等于冻结 integration commit，最终 happy path 全部 blobs 等于 `7e4b642…`。该 verdict 只放行真实回放及逐片 main-side gate，不把预检模拟写成已回放，不把 integration／R2／verify 绿色替代为 main-side gate，也不把 happy checkpoint外推为完整 bridge 产品 `PASS`。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **双视角覆盖证据——机械核对**：每次 load-bearing shell 调用都在同一次调用内验证 main physical root、`main`、现场 HEAD 与 target physical root、branch、精确 HEAD；target worktree始终 clean。Git 计数确认 `6a00f6f…..7e4b642…` 恰有 4 个 commits、4 个 non-merge、0 个 merge，每个提交只有一个 parent且 parent首尾精确相接。对每个 integration commit以 commit patch与 parent→commit diff两种入口交叉核对 stable patch-id；冻结每片精确 path与 changed blob。前三片的 integration patch／path／blob分别与完整 source range `6a00f6f…..8301ee9…`、`6a00f6f…..7ddf173…`、`6a00f6f…..73a6aa1…` 全等；第四片的两个 route source blobs与 `84a22c0…`全等，并按预定多出独立 happy smoke，因此不得错误要求整片与 route source range patch／path全等。Foundations base的三个 commits分别与 current main三个 cherry-pick commits有一一相等stable patch-id。四个 reviewed source refs仍精确指向指定HEAD；对应 happy archive refs当前尚不存在，符合“回放＋main-side gate通过后才归档”的状态。另对账 current Implementation、happy merged-state R1／R2与独立 verify，未把旧HEAD或不同范围的 verdict混为 current target证明。
- **双视角覆盖证据——第一人称执行**：以回放者身份从 current main tree建立独立临时 index，依次将四个 integration commit的 parent→commit binary patch通过 `git apply --cached --3way` 应用到临时 index。每片应用后检查 unmerged entries为零、写出新tree、比较“上一模拟tree→新tree”的stable patch-id与source commit patch-id，并逐个比较本片changed blob；四片均得到 conflict=no、patch_equal=yes、changed_blobs_equal=yes。最终模拟tree对 frozen happy完整path并集逐blob等于`7e4b642…`。模拟前后验证真实main HEAD、`refs/heads/main`、真实index diff hash与既存tracked status完全不变。随后按实际执行顺序逐片推演“身份门→cherry-pick→累计blob门→定向／交叠／全仓／Ruff／Pyright gate→archive reviewed source→进入下一片”，并检查carrier-first语义依赖、parser semantic-only边界、route pure-policy边界及产品持续`UNVERIFIED`没有被跳过。
- **写入边界**：唯一持久化写入为本报告 `docs/tmp/260807-audit-happy-replay.md`。主树在本轮开始前已有三份 living docs 的 tracked修改、`docs/tmp/`及`verification/`下未跟踪内容；本轮未修改、stash、restore、stage或清理这些既存状态。

## Current main 已包含 frozen foundations 语义

`6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 不是 current main 的 commit ancestor；二者共同祖先为 `ed77c9d191df81c451c25161420515cca52ce6a4`。这不表示 foundations缺失，因为三片已经以不同commit IDs逐片进入main。Stable patch-id机械映射如下：

| Frozen foundations commit | Current main commit | Stable patch-id | 结论 |
|---|---|---|---|
| `9e5f874d5b547bd9d733b0ee134e165f818de205` | `d274f584219f8ae32f59d15d08ac007c45058c8d` | `d5a27f67b536a3144c8b9e33add8a4779b5cf337` | Reasoning cardinality语义等价进入main |
| `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` | `798ba3e7653b513c3c9c732019e793f828ae0890` | `80976d48781b46e56ca9dc142ead02f488d201b2` | Session liveness语义等价进入main |
| `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7` | `1f8c17fe1c12d4a3fe050a5754b6d54ae6b85811` | Anthropic→Responses request converter语义等价进入main |

Current main在这三片之后另含`cf53334…` systemd语义及living docs历史；这些main-side新增内容没有阻止临时index应用happy carrier对共享request／reasoning paths的补丁。`git log --left-right --cherry-pick 6a00f6f...cf53334`只保留main独有提交，也从另一原理确认base三片已有patch-equivalent counterparts。结论是：实际回放必须从current main继续，不得先重复cherry-pick`6a00f6f…`或从feature source重建第二条foundations链。

## Happy 四提交拓扑、paths与稳定oracle

固定链为：

`6a00f6f… → 1ed13ad… → 80b3cfa… → c950912… → 7e4b642…`

计数口径为`git rev-list 6a00f6f…..7e4b642…`：总计4、non-merge 4、merge 0。总计由完整rev-list，non-merge与merge由互补过滤交叉核对，且逐提交parent等式再次验证线性关系。

### 1. Carrier v2 integration commit

- **Commit**：`1ed13ad7e19385b9f86a1cd292547438f6137179`。
- **Parent**：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。
- **Subject**：`feat: add versioned reasoning carrier codec`。
- **Tree**：`920f36514b9fd91bc78e9b6371da45c89aa8c5a8`。
- **Stable patch-id**：`67e66ccc765074c98599c6381509e710280fb7e0`。
- **完整source range**：`6a00f6f…..8301ee938601ad86c7f72d313abc6c976a74b2a9`；range stable patch-id同为`67e66ccc…`，精确9 paths与每个source HEAD blob均相等。

| Status | Path | Expected blob after slice |
|---|---|---|
| M | `src/app/anthropic/request_preparation.py` | `f0e518046ced0d0783c4b5033d4834fecc086748` |
| A | `src/app/anthropic/thinking/reasoning_carrier.py` | `7686b90f41d9b5f6c1620139d9a9962585cbeae2` |
| M | `src/app/anthropic/thinking/responses_reasoning.py` | `5b71443ac963eab47041a1cd030ffb074a14874d` |
| M | `src/app/protocols/anthropic_responses.py` | `7f8f4fa09add615fb5b8eb56dbf88f7e468de4f1` |
| M | `tests/unit/test_anthropic_client.py` | `3d461001d51f49536b940b2ec715c9a720935079` |
| M | `tests/unit/test_anthropic_preparation.py` | `73216e0928856ae3d3752eb03c634d0cf658ec35` |
| M | `tests/unit/test_anthropic_responses_request.py` | `2bdcd9e6bb6bcb37bd6fcb4e8346283cc69c56c7` |
| A | `tests/unit/test_reasoning_carrier.py` | `678ca7502db6b13fcdd8f192389126a2f13ecd37` |
| M | `tests/unit/test_responses_reasoning.py` | `228382df131693d18fac88f591a46e5615bbcd9d` |

### 2. Non-stream response integration commit

- **Commit**：`80b3cfade000cd9e1626074d14b1f9c9d5294891`。
- **Parent**：`1ed13ad7e19385b9f86a1cd292547438f6137179`。
- **Subject**：`feat: convert Responses JSON to Anthropic messages`。
- **Tree**：`08d5a6635478a75d0f48cfeee368f8a3ca8109c2`。
- **Stable patch-id**：`c947d52bd902b1140211952454a323b7501307df`。
- **完整source range**：`6a00f6f…..7ddf17364d97349638d44352bbd9a9b025723ccc`；range stable patch-id同为`c947d52b…`，精确2 paths与每个source HEAD blob均相等。

| Status | Path | Expected blob after slice |
|---|---|---|
| A | `src/app/protocols/responses_anthropic.py` | `c39fe3eb27b76a38b99d569010ba5a955593b02a` |
| A | `tests/unit/test_responses_anthropic_nonstream.py` | `477c91fdb573ffa8b58a4c5726ff0c3fbca11100` |

### 3. Stream parser integration commit

- **Commit**：`c950912ad739f85c39397ab0f2c4d25b82dddcb7`。
- **Parent**：`80b3cfade000cd9e1626074d14b1f9c9d5294891`。
- **Subject**：`feat: assemble Responses stream events`。
- **Tree**：`be611e48b0a3e15125c163e85803c2c3c07b7448`。
- **Stable patch-id**：`35c3332dadede958158df47bd102caf179ce9599`。
- **完整source range**：`6a00f6f…..73a6aa114647440262691651cd17e9127785c75a`；range stable patch-id同为`35c3332d…`，精确2 paths与每个source HEAD blob均相等。

| Status | Path | Expected blob after slice |
|---|---|---|
| A | `src/app/openai/responses_stream_parser.py` | `f1eb3a0c901111ee24b363869e97ee0a3d6b2337` |
| A | `tests/unit/test_responses_stream_parser.py` | `a0d045df8225904fe3ce941091d4715a0253ab97` |

### 4. Route policy＋happy smoke integration commit

- **Commit**：`7e4b642be8bd526d8f20f3f8d7e2d7848278a443`。
- **Parent**：`c950912ad739f85c39397ab0f2c4d25b82dddcb7`。
- **Subject**：`feat: add typed protocol route policy`。
- **Tree**：`9099d52562c7066777d5c9bd01278993971867fd`。
- **Integration stable patch-id**：`6fd013e08f7b1320f666c9cbae1f001f73cfb808`。
- **Route source range**：`6a00f6f…..84a22c07db3923768db44a1314e5ae6d5aed2e98`，stable patch-id为`621d68b2ed53767adfe82e1e2e6348aba7c4aecb`，只含route implementation与route smoke两个paths。Integration commit按冻结策略额外加入独立happy-path smoke，因此整提交patch-id与path集合**预期不等于**route source range；两个route paths的blobs仍与source HEAD逐字相等。

| Status | Path | Expected blob after slice | Provenance |
|---|---|---|---|
| A | `src/app/pipeline/route_policy.py` | `03533eed8ad3ca30d240e3ba43259ae987d47d83` | 与`84a22c0…`相等 |
| A | `tests/smoke/test_route_policy.py` | `63445d9e6c06839b1e1354f1e2042580155f2827` | 与`84a22c0…`相等 |
| A | `tests/smoke/test_anthropic_responses_happy_path.py` | `8290af7fef8366f1b63e09a16057b5ae70f6aa6e` | Integration专有、R2修订后的独立wire oracle |

## Source archive targets

四个reviewed source活动refs现场均精确，且对应future archive refs当前均不存在。不存在不是缺陷：归档必须在对应integration commit真实进入main且该片main-side gate通过后创建。Archive target必须是reviewed source HEAD，不得指向integration squash commit。

| Slice | Current reviewed source ref | 精确target | Future immutable archive ref | Current archive状态 |
|---|---|---|---|---|
| Carrier v2 | `feat/reasoning-carrier-v2` | `8301ee938601ad86c7f72d313abc6c976a74b2a9` | `archive/260807-anthropic-responses-reasoning-carrier-v2` | absent；gate后创建并指向`8301ee9…` |
| Non-stream | `feat/responses-anthropic-nonstream` | `7ddf17364d97349638d44352bbd9a9b025723ccc` | `archive/260807-anthropic-responses-nonstream` | absent；gate后创建并指向`7ddf173…` |
| Stream parser | `feat/responses-stream-parser` | `73a6aa114647440262691651cd17e9127785c75a` | `archive/260807-anthropic-responses-stream-parser` | absent；gate后创建并指向`73a6aa1…` |
| Route policy | `feat/anthropic-responses-route-policy` | `84a22c07db3923768db44a1314e5ae6d5aed2e98` | `archive/260807-anthropic-responses-route-policy` | absent；gate后创建并指向`84a22c0…` |

上述archive ref名称按现有`archive/260807-anthropic-responses-*`命名约定给出；不可变的核心oracle是右侧四个完整reviewed source object IDs。若主会话已有更具体且已裁决的ref名称，应沿用已决名称，但target object不得改变。

## 临时index逐commit冲突模拟

模拟对象边界是“将每个integration commit的parent→commit patch依序应用到current main tree”，与真实逐片cherry-pick的内容变换对齐。探测层级明确为Git index／tree，不执行commit hooks、不创建commit对象、不运行产品代码；因此它证明内容三方应用与tree结果，不替代真实cherry-pick后的hooks、tests、lint或type gates。

| Step | Input simulated tree | Output simulated tree | Unmerged entries | Patch-id equality | Changed blob equality |
|---|---|---|---:|---|---|
| Start | current `main@cf53334…` | `fa084a0790a2fab84ac8e59a641fc37842474edb` | 0 | N/A | N/A |
| Carrier `1ed13ad…` | `fa084a07…` | `9785f2c84c6bbd49844bfbd08749aa5167103d44` | 0 | yes | yes |
| Nonstream `80b3cfa…` | `9785f2c8…` | `6935aba4173ca87ae802110e9add5ff3b39743a5` | 0 | yes | yes |
| Parser `c950912…` | `6935aba4…` | `fc5592a2e5b325adbbce004850ca2354ebed9cbc` | 0 | yes | yes |
| Route／smoke `7e4b642…` | `fc5592a2…` | `6eb1bc474a70f87d3b919015fe647845bfba5406` | 0 | yes | yes |

最终模拟tree对`6a00f6f…..7e4b642…`完整happy path并集逐blob比较为`yes`。模拟后主树仍为`main@cf53334…`，真实index仍无staged paths，既存tracked status的内容hash未变，`CHERRY_PICK_HEAD`／`MERGE_HEAD`／`REVERT_HEAD`均不存在。

## R2／verify结论对账

1. `docs/tmp/260807-verify-happy-path.md`绑定amend前候选`d78b3cdc172ecad42873a70f1df31438ecca1663`，在happy-path primitives／pure-path阶段给出`PASS`，并明确真实route wiring、single-owner lifecycle、transport、strict SSE sink、commit／retry、History／hooks／tokenization、resource limits与error matrix仍为`UNVERIFIED`。它不能单独证明current`7e4b642…`。
2. `docs/tmp/260807-review-code-happy-path.md`同样绑定`d78b3cdc…`，产品行为未发现blocker／major，但发现组合smoke的carrier expected与产品codec同源，判为1 major，并明确当时不能放行回放。
3. `docs/tmp/260807-review-code-happy-path-r2.md`绑定current`7e4b642…`，确认amend只修改`tests/smoke/test_anthropic_responses_happy_path.py`，把expected改为Spec静态完整signature；错误`v9` producer正控准确转红，目标定向与superset测试恢复为绿。R2 verdict为blocker 0、major 0、minor 0，并明确在foundations先落main后可按四提交顺序回放。
4. 因此current放行链是“verify证明amend前产品pure-path范围PASS＋R1定位测试oracle major＋R2在current bytes关闭该major并放行四提交”，而不是把verify的旧HEAD直接冒充current target验收。完整bridge继续为`UNVERIFIED`。

## 每片真实main-side gate

以下gate是实际回放时必须执行的门，不是本轮已执行结果。每片只有全部通过后才能进入下一片；任一失败都停止，不得用integration侧旧绿、临时index模拟或`ours`／`theirs`覆盖失败。

### 所有切片共同前置与收尾门

1. 每次shell调用内重新验证physical root为`/home/xp/src/ghc-api-proxy-py`、branch为`main`、`HEAD == refs/heads/main`，并记录完整现场HEAD；确认无`CHERRY_PICK_HEAD`、`MERGE_HEAD`、`REVERT_HEAD`，真实index无未裁决staged changes。
2. 验证target integration仍为clean `integrate/260807-bridge-happy-path@7e4b642…`；待回放commit的parent、subject、stable patch-id与精确paths等于本文冻结值。消费现有integration commit，不从source refs重建第二条链。
3. 回放后验证本片changed blobs等于本文oracle，并验证前序累计happy blobs没有回退；提交的新OID可因parent不同而变化，不要求等于integration commit OID或tree OID。
4. 运行本片定向测试与交叠oracle，再运行current main完整`tests/`、全量Ruff与全量Pyright；Python import／module-resolution必须指向main worktree。只有全部绿色才能记录该片main-side gate通过。
5. Gate通过后创建并机械验证该片immutable archive ref精确指向reviewed source HEAD；不得指向integration commit。Archive完成前不得删除对应feature worktree／branch。共享happy integration载体须保留到四片全部进入main、四片gate与archive都完成、merged-state复评完成且worktree仍clean；实际清理仍需独立授权。
6. 更新living Implementation中的main commit、gate与archive事实；不得写“bridge PASS”“nonstream complete”“stream complete”或“route enabled”。

### Slice 1：Carrier v2

- 回放`1ed13ad…`，验证9个changed blobs及patch-id`67e66ccc…`。
- 定向pytest至少覆盖`tests/unit/test_anthropic_client.py`、`tests/unit/test_anthropic_preparation.py`、`tests/unit/test_anthropic_responses_request.py`、`tests/unit/test_reasoning_carrier.py`与`tests/unit/test_responses_reasoning.py`。
- 独立wire oracle使用Spec硬编码项目主v1 `opaque-😀`完整signature，不调用产品encoder／decoder生成expected；验证一item一block、encrypted-only、source order与逐block reverse。
- 双腿黑盒验证Responses leg消费项目主v1及允许的upstream v1合法形态，direct Messages final preparation剥离项目synthetic namespace／upstream synthetic forms，同时保留真实Anthropic `CAIS` signature。
- 运行全量pytest、Ruff、Pyright；绿色后创建carrier archive精确指向`8301ee9…`。

### Slice 2：Non-stream response

- 回放`80b3cfa…`，验证2个changed blobs及patch-id`c947d52b…`，并复核Slice 1累计blobs未回退。
- 定向pytest覆盖`tests/unit/test_responses_anthropic_nonstream.py`以及carrier／reasoning交叠测试。
- 独立组合oracle从Responses reasoning item经公开nonstream converter取得Anthropic block，硬编码断言项目主v1 exact wire，再经公开reverse consumer value-exact恢复；覆盖multiple reasoning、encrypted-only、source order、public `msg_` identity不泄漏`resp_*`与upstream identity facts保留。
- 保留usage reasoning detail为已知后继切片；不得以full-Spec nonstream verifier整体FAIL否决本checkpoint，也不得把本组合gate写成usage已完成。
- 运行全量pytest、Ruff、Pyright；绿色后创建nonstream archive精确指向`7ddf173…`。

### Slice 3：Stream parser

- 回放`c950912…`，验证2个changed blobs及patch-id`35c3332d…`，并复核前两片累计blobs未回退。
- 定向pytest覆盖`tests/unit/test_responses_stream_parser.py`；独立oracle覆盖跨类型interleave、较晚source先完成时的open barrier、authoritative item done payload、source order与completion order分离、unknown typed failure，以及terminal不得在open／unsupported item存在时伪装成功。
- 静态负门确认parser仍不import或调用carrier encoder／signature wire逻辑，不新增renderer或delivery owner行为。
- 运行全量pytest、Ruff、Pyright；绿色后创建parser archive精确指向`73a6aa1…`。

### Slice 4：Route policy＋happy smoke

- 回放`7e4b642…`，验证3个changed blobs及integration patch-id`6fd013e0…`，并复核前三片累计blobs未回退。不要错误使用route source range patch-id`621d68b2…`作为整个integration commit expected。
- 定向pytest覆盖`tests/smoke/test_route_policy.py`与`tests/smoke/test_anthropic_responses_happy_path.py`；重跑R2静态Spec carrier vector与错误version正控，确保producer／consumer同漂移不能假绿。
- Route oracle验证双支持默认Messages、单能力选择、显式override优先且失败不fall through、unknown／missing／conflict fail closed、protocol capability与physical transport正交；静态负门确认pure policy无网络import／send／connect。
- Happy组合oracle验证carrier→nonstream→echo→consumer双腿、request conversion、nonstream公开identity及parser semantic facts；不得把pure policy green外推为真实handler／transport接线。
- 运行全量pytest、Ruff、Pyright；绿色后创建route archive精确指向`84a22c0…`。
- 四片全部完成后执行final merged-state代码复评；只有该复评仍为blocker 0／major 0，才进入后继usage`aca3ced…`。完整bridge仍保持`UNVERIFIED`。

## 事实性发现

未发现问题。审计范围内blocker 0、major 0、minor 0；current main具备frozen foundations等价语义，happy四提交线性、非merge、身份稳定，临时index逐片回放无冲突且最终blobs完全等于target。**明确可按`1ed13ad → 80b3cfa → c950912 → 7e4b642`逐个回放current main。**

## 主观建议

无。实际执行应严格使用现有integration链、本文逐片oracle与main-side gates，不扩大为source重组，也不缩减后续required产品范围。

## 结构怪味扫描

- `tests/unit/test_responses_anthropic_nonstream.py`与共享reasoning helper——**同源expected风险**——本轮不改；main-side Slice 2与Slice 4必须保留Spec硬编码完整signature和公开producer→consumer正控，不能只跑该unit。
- `7e4b642…`相对route source range——**integration commit混合route source与组合smoke，不能使用source-range整片patch-id作oracle**——本轮已在身份规则中显式拆分：integration patch-id验证整个回放commit，source HEAD逐blob只验证两个route paths，第三个smoke使用integration专有blob。
- `6a00f6f…`与current main——**squash／cherry-pick后ancestor关系不再代表语义落地**——本轮采用三对stable patch-id与临时index真实应用，而非重复回放base或依赖`git branch --merged`。

## 方法反思

1. **更好的内部替代方案**：只做`git apply --check`会证明patch可套用，却不证明逐片结果tree与frozen target相同。本轮使用临时index实际三方应用、每片写tree并校验patch-id／blobs，证据更强且不触碰main。
2. **判据判别力**：无冲突本身可能假绿，因为错误patch也可能干净应用；本轮同时要求每片stable patch-id相等、changed blobs相等、最终完整happy path blobs相等。反向的false-red也通过route片例外处理：不错误要求含额外happy smoke的integration commit与仅两path的route source range整片patch-id相等。
3. **成熟第三方方案**：全部使用Git原生object database、`patch-id --stable`、temporary index、three-way apply、tree与blob primitives，没有手写merge算法或自建patch解析器。

## 最终结论

**可逐个回放。** Current main `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`已以`d274f58… → 798ba3e… → 1c13fda…`包含frozen base三片语义；happy target `7e4b642…`恰为四个线性non-merge commits。临时index从current main依序应用四片均无冲突，每片patch与changed blobs精确，最终tree的happy paths逐blob等于target。R2在current target上为0 blocker／0 major／0 minor并关闭R1测试oracle major；独立verify仍只证明其声明的happy pure-path范围，完整产品继续`UNVERIFIED`。

实际执行顺序固定为`1ed13ad → 80b3cfa → c950912 → 7e4b642`。每片必须在进入下一片前完成本文main-side gate并把archive精确指向`8301ee9`、`7ddf173`、`73a6aa1`、`84a22c0`对应的reviewed source HEAD。本文没有执行cherry-pick、main-side测试、归档或清理，也不授权部署、安装或cutover。

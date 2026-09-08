# Current worktree／branch 清理清单只读复审 R2

- **评审范围**：只读审计 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、18 个 registered worktrees、18 个 non-archive local branches 与 10 个 `archive/*` refs。目标是确认 foundations、happy、systemd 与 non-stream usage 已以等价语义进入 current main 且 reviewed source 已精确归档，从而更新可清理清单；同时确认新建 route-happy、block-delivery、graceful-timeout、systemd-install 四组 worktree／branch 必须保留。未重新评审产品代码，未执行任何清理、ref 更新、branch 切换、stash、reset、restore 或 clean。
- **总体 verdict**：**可按本文机械门清理 13 个旧 worktrees 及其同名活动 branches；4 个新 worktrees／branches 与全部 10 个 archive refs 必须保留。** 每一组只在执行当刻重新满足本文完整 gate 时才可清理；任一对象、dirty 状态、archive ref、main HEAD 或 patch／blob identity 漂移即停止该组，禁止使用 force、discard 或整树恢复绕过。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **写入边界**：唯一持久化写入为本报告 `docs/tmp/260807-audit-worktree-cleanup-r2.md`。本轮没有删除 worktree／branch，没有创建、移动、删除或 force-update archive ref。主树开始前已有 `docs/tmp/` 与三个 `verification/` 路径的未跟踪状态；本轮未触碰这些既存内容。

## 双视角覆盖证据

### 机械核对

- 每个承重 shell 调用均在同一调用内验证 physical root `/home/xp/src/ghc-api-proxy-py`、branch `main` 与完整 `HEAD=80bc8f252b46c511f428af1d97159a5980ee9dc9`；没有从其他 worktree 的 ambient cwd 推断主树状态。
- `git worktree list --porcelain` 与 `git for-each-ref refs/heads` 交叉清点为 18 个 registered worktrees、28 个 local heads，其中 10 个为 `archive/*`、18 个为 non-archive branches；每个 non-archive branch 恰绑定一个已枚举 worktree，没有游离活动 branch 被漏出清单。
- 对 17 个非主 worktrees 逐项读取 physical top-level、branch、完整 HEAD 与 porcelain status；全部 `dirty=0`。Clean 仅是必要条件，不是充分条件；四个新 worktrees 即使 clean 也判为强制保留。
- Foundations 的 cardinality／liveness／request integration commits 与 current main `d274f584…`／`798ba3e765…`／`1c13fda4…` stable patch-id 一一相等；旧 liveness integration `8e9aef69…`、reviewed source range `47d9ef10…..f27a8c04…` 与 main liveness commit 的 stable patch-id 均为 `80976d48…`。
- Systemd integration `fe9c2031…` 与 main `cf53334a…` stable patch-id 同为 `eab37d38…`。
- Happy integration 四片 `1ed13ad7…`／`80b3cfad…`／`c950912a…`／`7e4b642b…` 与 main `a0d807fe…`／`cdc080e1…`／`a815948e…`／`d913a033…` stable patch-id 一一相等。Carrier、nonstream、parser 的完整 source ranges 相对 frozen base `6a00f6f7…` 分别与前三片 integration commits 相等；route integration 因额外包含 happy smoke，不错误要求其整片与 route source range 相等，而是另验证 route source 两个 blobs 在 reviewed source、integration、main commit 与 current main 四处完全相等。
- Usage source `aca3ced6…` 与 current main tip `80bc8f25…` stable patch-id 同为 `e53b2de9…`。
- 十个 archive refs 均与其 reviewed source HEAD 做完整对象等式核对，全部精确；这些 refs 是清理后保留历史身份的唯一长期载体，不得移动或删除。

### 第一人称执行模拟

- 模拟执行 foundations／systemd 清理：先机械确认 archive 精确、worktree clean、integration→main patch-id 等价，再移除 worktree，最后删除对应活动 branch；清理后 reviewed source 仍由 archive ref 可达，current main 仍持有等价语义。
- 模拟执行 happy／usage 清理：四个 source worktrees先由各自 archive 精确覆盖，happy integration四片再与main四片逐片等价，usage source与main tip等价；按“source worktrees → happy integration → usage worktree”的顺序清理后，不会丢失 reviewed source身份或已落main语义。Route片采用两个source blobs＋integration专有smoke的分层门，避免整片patch-id false-red。
- 模拟误删四个新 worktrees：它们当前都从 `80bc8f25…` 新建且尚未产生独立提交，但分别是 route wiring happy path、block delivery、graceful timeout、systemd user install 的活动实施载体；clean且tip等于main不构成清理授权。本文将其列为强制保留对象。
- 模拟误删 archive refs：活动 source branch清理后，reviewed source commit虽可能暂时仍可由对象库或其他历史间接到达，但不再有受合同保护的命名身份；因此 archive refs必须从所有删除命令与批量匹配中明确排除。

## Current main 语义落地矩阵

| 领域 | Source／integration 对象 | Current main 对象 | Identity oracle | 结论 |
|---|---|---|---|---|
| Foundations cardinality | `9e5f874d5b547bd9d733b0ee134e165f818de205` | `d274f584219f8ae32f59d15d08ac007c45058c8d` | stable patch-id `d5a27f67b536a3144c8b9e33add8a4779b5cf337` | 已进入 main |
| Foundations liveness | `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` | `798ba3e7653b513c3c9c732019e793f828ae0890` | stable patch-id `80976d48781b46e56ca9dc142ead02f488d201b2` | 已进入 main |
| Foundations request | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `1c13fda4f5eac5e42ca0025d503f91eb0563f0e7` | stable patch-id `1f8c17fe1c12d4a3fe050a5754b6d54ae6b85811` | 已进入 main |
| Systemd runtime | `fe9c20315b0137ca5b2253fdbd86a30d504255ef` | `cf53334a10a717a3a3d30d6c0e8a297f5000d90c` | stable patch-id `eab37d38b63730f895be3e55fd256f0547209630` | 已进入 main |
| Happy carrier | `1ed13ad7e19385b9f86a1cd292547438f6137179` | `a0d807fe807629b739ab16c5463f99bc27bc7aac` | stable patch-id `67e66ccc765074c98599c6381509e710280fb7e0` | 已进入 main |
| Happy nonstream | `80b3cfade000cd9e1626074d14b1f9c9d5294891` | `cdc080e1795ee1ac63d589ee00a10acd581b460e` | stable patch-id `c947d52bd902b1140211952454a323b7501307df` | 已进入 main |
| Happy parser | `c950912ad739f85c39397ab0f2c4d25b82dddcb7` | `a815948ef1b8e739e4bd49e31894be4dffc06950` | stable patch-id `35c3332dadede958158df47bd102caf179ce9599` | 已进入 main |
| Happy route／smoke | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | `d913a033252693022f0871f1e92c1b996d05eb71` | stable patch-id `6fd013e08f7b1320f666c9cbae1f001f73cfb808` | 已进入 main |
| Non-stream usage | `aca3ced6e38efabf13ffe43d5935697801c74857` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | stable patch-id `e53b2de91c45471e405af6890eb8c245fa481b5d` | 已进入 main |

Main first-parent 顺序为 foundations 三片 → systemd runtime → living docs → happy 四片 → usage。上述 identity oracle 用于识别 squash／replay 后的语义对应关系；不得用 `git branch --merged main` 或 commit ancestry 代替，因为 reviewed source与integration commits预期不是main ancestors。

## Archive refs 保留矩阵

| Archive ref | 必须保持的精确 object |
|---|---|
| `archive/260806-anthropic-responses-reasoning` | `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b` |
| `archive/260807-anthropic-responses-reasoning-cardinality` | `b876e626dda821b267535b0bcffc9d81ced12763` |
| `archive/260807-anthropic-responses-liveness` | `f27a8c04cd3470bd50d7194a30371ca5404f727e` |
| `archive/260807-anthropic-responses-request` | `fdd2f75fcec11e592b04f2686c4664262052a964` |
| `archive/260807-reasoning-carrier-v2` | `8301ee938601ad86c7f72d313abc6c976a74b2a9` |
| `archive/260807-responses-anthropic-nonstream` | `7ddf17364d97349638d44352bbd9a9b025723ccc` |
| `archive/260807-responses-stream-parser` | `73a6aa114647440262691651cd17e9127785c75a` |
| `archive/260807-anthropic-responses-route-policy` | `84a22c07db3923768db44a1314e5ae6d5aed2e98` |
| `archive/260807-nonstream-usage-details` | `aca3ced6e38efabf13ffe43d5935697801c74857` |
| `archive/260807-systemd-runtime` | `49fb1988621bba4356e7a5039a6994c2e6d19604` |

**机械门**：清理前必须对整张表逐项执行 `refs/heads/<archive> == <完整 object>` 等式；清理后再次逐项执行同一等式。删除 branch时 pathspec必须是精确活动 branch全名，不得使用 `archive/*`、通配符、前缀批量删除或包含 `refs/heads/archive/` 的 refspec。

## 可清理清单

以下 13 组均在审计时 `dirty=0`，其source身份已有精确archive覆盖，且语义已有current-main identity oracle。每组均按“前置门 → 移除worktree → 确认registration消失且archive未变 → 删除精确活动branch → 再次确认archive未变”的顺序执行；本文没有执行这些动作。

| 组 | Worktree | Activity branch | 审计时 HEAD | 额外 identity gate |
|---|---|---|---|---|
| Foundations cardinality | `/home/xp/src/ghc-api-proxy-py-reasoning-cardinality` | `fix/reasoning-cardinality` | `b876e626dda821b267535b0bcffc9d81ced12763` | archive精确；`9e5f874d…` ↔ main `d274f584…` patch-id相等 |
| Foundations liveness | `/home/xp/src/ghc-api-proxy-py-liveness` | `feat/session-liveness` | `f27a8c04cd3470bd50d7194a30371ca5404f727e` | archive精确；`cae83f46…` ↔ main `798ba3e7…` patch-id相等 |
| Foundations request | `/home/xp/src/ghc-api-proxy-py-request` | `feat/anthropic-responses-request` | `fdd2f75fcec11e592b04f2686c4664262052a964` | archive精确；`6a00f6f7…` ↔ main `1c13fda4…` patch-id相等 |
| Foundations integration | `/home/xp/src/ghc-api-proxy-py-integrate-bridge` | `integrate/260806-bridge-foundations` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | 三个foundations patch-id映射全部仍成立 |
| Old liveness integration | `/home/xp/src/ghc-api-proxy-py-integrate-liveness` | `integrate/260806-session-liveness` | `8e9aef69cc8606c4ca25286da617da8fc74d5c55` | source range、integration、main三方patch-id仍同为`80976d48…` |
| Happy carrier source | `/home/xp/src/ghc-api-proxy-py-carrier-v2` | `feat/reasoning-carrier-v2` | `8301ee938601ad86c7f72d313abc6c976a74b2a9` | archive精确；source range ↔ integration `1ed13ad7…` ↔ main `a0d807fe…` identity链成立 |
| Happy nonstream source | `/home/xp/src/ghc-api-proxy-py-response` | `feat/responses-anthropic-nonstream` | `7ddf17364d97349638d44352bbd9a9b025723ccc` | archive精确；source range ↔ integration `80b3cfad…` ↔ main `cdc080e1…` identity链成立 |
| Happy parser source | `/home/xp/src/ghc-api-proxy-py-stream-parser` | `feat/responses-stream-parser` | `73a6aa114647440262691651cd17e9127785c75a` | archive精确；source range ↔ integration `c950912a…` ↔ main `a815948e…` identity链成立 |
| Happy route source | `/home/xp/src/ghc-api-proxy-py-route-policy` | `feat/anthropic-responses-route-policy` | `84a22c07db3923768db44a1314e5ae6d5aed2e98` | archive精确；两个route source blobs在source／integration／main／current四处相等 |
| Happy integration | `/home/xp/src/ghc-api-proxy-py-integrate-happy` | `integrate/260807-bridge-happy-path` | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` | 四个integration→main stable patch-id全部仍相等；四个happy archive仍精确 |
| Non-stream usage source | `/home/xp/src/ghc-api-proxy-py-nonstream-usage` | `feat/nonstream-usage-details` | `aca3ced6e38efabf13ffe43d5935697801c74857` | archive精确；source ↔ main tip `80bc8f25…` patch-id仍为`e53b2de9…` |
| Systemd source | `/home/xp/src/ghc-api-proxy-py-systemd` | `feat/systemd-cgroup-runtime` | `49fb1988621bba4356e7a5039a6994c2e6d19604` | archive精确；integration `fe9c2031…` ↔ main `cf53334a…` patch-id相等 |
| Systemd integration | `/home/xp/src/ghc-api-proxy-py-integrate-systemd` | `integrate/260807-systemd-runtime` | `fe9c20315b0137ca5b2253fdbd86a30d504255ef` | systemd archive精确；integration ↔ main patch-id仍为`eab37d38…` |

### 每组精确机械门

1. **Main identity门**：physical root必须仍为 `/home/xp/src/ghc-api-proxy-py`，branch必须为 `main`，且 `HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。若main已前进，本文旧verdict不得沿用；必须重新审计受影响identity与worktree集合。
2. **Worktree identity门**：目标路径必须仍是registered worktree；`rev-parse --show-toplevel`必须精确等于表中绝对路径；symbolic branch与完整HEAD必须精确等于表值；不得接受detached HEAD、不同branch或缩写SHA。
3. **Clean双向门**：`git status --porcelain`必须为空；同时确认无 `CHERRY_PICK_HEAD`、`MERGE_HEAD`、`REVERT_HEAD`、rebase或bisect状态。任一非空都停止，不使用`--force`、discard、stash或整文件恢复代替裁决。
4. **Archive门**：先逐项验证完整十ref矩阵精确，再验证本组直接对应archive；清理worktree后与删除branch后各复验十ref矩阵完全不变。
5. **Main语义门**：按表中对应规则重算stable patch-id或route blobs，不接受文档自述、subject相同、clean状态、ancestor关系或`branch --merged`作为替代。
6. **Removal后门**：worktree移除后，`git worktree list --porcelain`不得再出现该绝对路径，而精确活动branch必须仍指向审计HEAD；只有此时才删除该活动branch。若registration仍存在或branch已漂移，停止。
7. **Branch删除后门**：精确活动branch必须不存在，十个archive refs必须仍逐项等于表值，main与四个保留branches必须仍存在且对象未变。不得用批量前缀或通配符删除。
8. **逐组执行门**：一次只处理一组并完整完成上述后验；不得把13组删除打包成一个不可分辨的批量动作。任一组失败不影响已验证但尚未动作的其他组，后续组仍须现场重跑全部前置门。

## 强制保留清单

| Worktree | Branch | 审计时 HEAD | 保留理由 |
|---|---|---|---|
| `/home/xp/src/ghc-api-proxy-py` | `main` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 主工作树与当前集成真相源，不是清理对象 |
| `/home/xp/src/ghc-api-proxy-py-route-happy` | `feat/anthropic-responses-route-happy` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 新 route wiring happy-path 实施载体，用户明确要求保留 |
| `/home/xp/src/ghc-api-proxy-py-block-delivery` | `feat/anthropic-block-delivery` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 新 block delivery 实施载体，用户明确要求保留 |
| `/home/xp/src/ghc-api-proxy-py-graceful-timeout` | `feat/systemd-graceful-timeout` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 新 graceful timeout 实施载体，用户明确要求保留 |
| `/home/xp/src/ghc-api-proxy-py-systemd-install` | `feat/systemd-user-install` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | 新 systemd user install 实施载体，用户明确要求保留 |

四个新worktrees审计时均clean且tip等于main；这只证明其尚未产生独立提交，不表示可清理。任何自动化清理名单都必须以精确路径与branch allowlist排除这四组，并在每个旧组清理后复验它们仍registered、branch仍存在、对象未变。

## 事实性发现

未发现阻断清理的事实性问题。Foundations、happy、systemd与usage均已在current main找到精确语义对应；十个reviewed source archive refs精确；13个旧worktrees均clean；四个新worktrees均存在、clean且对象为current main，并已明确排除在清理范围外。

## 结构怪味扫描

- `git branch --merged`／ancestor-only判断 —— **squash／replay后提交身份与语义身份混淆** —— 本报告不采用；以archive object、stable patch-id、source-range与特殊route blob oracle组合判定。
- Happy route source与integration —— **integration额外携带happy smoke，整片source-range patch-id会false-red** —— 本报告按两个route source blobs与integration专有smoke分层核对，不把预期差异误判成未落main。
- Worktree clean状态 —— **必要条件被误作充分条件** —— 四个新worktrees是反向样本；虽然clean且HEAD等于main，仍因活动实施职责与用户裁决必须保留。

## 方法反思

1. **更好的内部替代方案**：按branch名称或`--merged`批量清理会漏掉squash语义并误伤新空分支；当前“精确对象＋archive＋patch／blob identity＋逐组后验”更可审计。
2. **判据判别力**：正样本是13个clean、archived、main-equivalent旧载体；反样本是4个同样clean且HEAD等于main、但必须保留的新载体。该组合能区分“可清理”与“看起来空闲但仍承担实施职责”。
3. **成熟第三方方案**：全部身份与集合判定使用Git原生worktree porcelain、refs、object IDs、trees、blobs与stable patch-id；没有自建branch数据库或手写patch解析器。

## 最终结论

**可清理但本轮未清理**：foundations的3个source、2个integration；happy的4个source、1个integration；non-stream usage source；systemd source与integration，共13个worktrees及其精确活动branches。执行时必须逐组通过本文八道机械门，任何漂移即停止且重新审计。

**必须保留**：主worktree／`main`，新route-happy／block-delivery／graceful-timeout／systemd-install四组worktree／branch，以及全部10个archive refs。Archive refs不得移动、删除或force-update；四个新worktrees不得因clean或尚无独立提交而被清理。

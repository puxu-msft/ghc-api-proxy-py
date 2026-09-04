# Current worktree／branch 清理清单独立复核 R2

- **评审范围**：独立复核 `docs/tmp/260807-audit-worktree-cleanup-r2.md`，并以 `/home/xp/src/ghc-api-proxy-py` 的 current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`、current local refs 与 registered worktrees 为事实源。只判断 13 组旧 worktree／activity branch 是否可按机械门清理、10 个 archive refs 是否精确、5 个新 worktree／branch 与其他进行中对象是否必须保留；未重新评审产品代码，未执行任何清理、ref 更新、branch 删除、stash、reset、restore 或 clean。
- **总体 verdict**：**可进入执行阶段。0 major，13 组旧 worktree／activity branch 可按本文修正后的逐组机械门清理。** `main`、5 个新 worktree／branch、全部 10 个 archive refs 必须保留。原 R2 报告生成后新增了 `semantic-parity`，因此其“18 个 worktrees／4 个新 worktrees”快照已过时；current 精确集合是 19 个 worktrees、29 个 local heads，其中 10 个 archive heads、19 个 non-archive heads。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。原 R2 的 route source blob oracle 写错了两个文件路径；本文已给出可执行的精确修正，不阻断 13 组旧对象清理。
- **写入边界**：唯一持久化写入为本报告 `docs/tmp/260807-review-worktree-cleanup-r2.md`。本轮未修改被评审报告，未修改代码、refs、worktree registration 或其他文件。

## 双视角覆盖证据

### 机械核对

- 固定验证 physical root `/home/xp/src/ghc-api-proxy-py`、symbolic branch `main`、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- 以 `git worktree list --porcelain` 与 `git for-each-ref refs/heads` 独立重建 current 全集：19 个 registered worktrees、29 个 local heads、10 个 `archive/*` heads、19 个 non-archive heads；每个 non-archive head 恰绑定一个 registered worktree。集合精确分解为 `main` 1 组、旧可清理 13 组、新／进行中必须保留 5 组。
- 对 13 个旧 worktrees 逐项核对 absolute top-level、symbolic branch、完整 HEAD、`git status --porcelain -uall` 与 Git 操作中标记。13 组均无 tracked／untracked 改动，且无 merge、rebase、cherry-pick、revert 或 bisect 状态。
- 对 13 个旧 worktrees 使用 `git ls-files --others --ignored --exclude-standard` 展开 ignored 文件全集。命中仅位于 `.coverage`、`.pytest_cache`、`.ruff_cache`、`.venv`、`src/**/__pycache__` 与 `tests/**/__pycache__` 等可重建测试、环境及字节码产物；未发现 `.env`、数据库、草稿或其他不在白名单内的本地数据。执行当刻若 ignored 根集合新增任何类别，必须停止该组并重新人工裁决。
- 独立重算 9 对 integration／source commit 到 current main commit 的 stable patch-id、3 个 happy source range 到 integration commit 的 stable patch-id，以及 old-liveness source range／integration／main 三方 patch-id，全部相等。
- 独立查出并修正 route oracle：reviewed source `84a22c07…` 的两个 source blobs 实际为 `src/app/pipeline/route_policy.py` 与 `tests/smoke/test_route_policy.py`，不是原报告隐含的其他 route 文件。两 blob 在 source `84a22c07…`、integration `7e4b642…`、main commit `d913a033…` 与 current main 四处分别精确相等；integration／main 额外包含 `tests/smoke/test_anthropic_responses_happy_path.py`，因此仍不得用整个 source range 对 route integration 做等价要求。
- 逐项验证 10 个 `archive/*` refs 与本文 archive 矩阵的完整 object 等式，全部精确。

### 第一人称执行模拟

- 模拟逐组执行旧树清理：先冻结 main、全集、目标 worktree identity、clean／operation state、ignored 白名单、archive 矩阵和该组 main identity；再移除单个 worktree；确认 registration 消失而 activity branch 与 archives 未变；最后只删除该精确 activity branch，并复验 main、5 个保留组与 10 个 archives。该顺序不会在移除 worktree 前先丢 branch 身份，也不会把一个失败扩散成 13 组批量破坏。
- 模拟执行 route source 组：若照原 R2 的错误 blob 路径运行，Git 会报目标路径不存在，机械门不可执行；改用本文两个精确路径后，source／integration／main／current blob 等式成立，route source 组可与其余 12 组同样清理。
- 模拟执行 `semantic-parity` 缺失的旧保留清单：按原报告只保护 4 个新组会漏掉 current 第 5 个活动实施载体 `/home/xp/src/ghc-api-proxy-py-semantic-parity`／`fix/responses-semantic-parity`。本文将其纳入精确保留集合，并要求每个旧组清理后复验全部 5 组。
- 模拟误把“无独立提交”当作“可清理”：`semantic-parity` 当前仍指向 main，而其余 4 个新组已各自前进到独立提交；两种形态都不改变其进行中职责。清理授权以本文精确旧组 allowlist 为准，不以 `HEAD == main`、clean、提交数或 branch 命名猜测。

## 修正后的可清理集合

以下 13 组在本次固定快照下机械可清理。执行时必须逐组重跑后文完整门；不得从表中推导前缀、通配符或批量 refspec。

| 组 | Worktree | Activity branch | 固定 HEAD |
|---|---|---|---|
| Foundations cardinality | `/home/xp/src/ghc-api-proxy-py-reasoning-cardinality` | `fix/reasoning-cardinality` | `b876e626dda821b267535b0bcffc9d81ced12763` |
| Foundations liveness | `/home/xp/src/ghc-api-proxy-py-liveness` | `feat/session-liveness` | `f27a8c04cd3470bd50d7194a30371ca5404f727e` |
| Foundations request | `/home/xp/src/ghc-api-proxy-py-request` | `feat/anthropic-responses-request` | `fdd2f75fcec11e592b04f2686c4664262052a964` |
| Foundations integration | `/home/xp/src/ghc-api-proxy-py-integrate-bridge` | `integrate/260806-bridge-foundations` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` |
| Old liveness integration | `/home/xp/src/ghc-api-proxy-py-integrate-liveness` | `integrate/260806-session-liveness` | `8e9aef69cc8606c4ca25286da617da8fc74d5c55` |
| Happy carrier source | `/home/xp/src/ghc-api-proxy-py-carrier-v2` | `feat/reasoning-carrier-v2` | `8301ee938601ad86c7f72d313abc6c976a74b2a9` |
| Happy nonstream source | `/home/xp/src/ghc-api-proxy-py-response` | `feat/responses-anthropic-nonstream` | `7ddf17364d97349638d44352bbd9a9b025723ccc` |
| Happy parser source | `/home/xp/src/ghc-api-proxy-py-stream-parser` | `feat/responses-stream-parser` | `73a6aa114647440262691651cd17e9127785c75a` |
| Happy route source | `/home/xp/src/ghc-api-proxy-py-route-policy` | `feat/anthropic-responses-route-policy` | `84a22c07db3923768db44a1314e5ae6d5aed2e98` |
| Happy integration | `/home/xp/src/ghc-api-proxy-py-integrate-happy` | `integrate/260807-bridge-happy-path` | `7e4b642be8bd526d8f20f3f8d7e2d7848278a443` |
| Non-stream usage source | `/home/xp/src/ghc-api-proxy-py-nonstream-usage` | `feat/nonstream-usage-details` | `aca3ced6e38efabf13ffe43d5935697801c74857` |
| Systemd source | `/home/xp/src/ghc-api-proxy-py-systemd` | `feat/systemd-cgroup-runtime` | `49fb1988621bba4356e7a5039a6994c2e6d19604` |
| Systemd integration | `/home/xp/src/ghc-api-proxy-py-integrate-systemd` | `integrate/260807-systemd-runtime` | `fe9c20315b0137ca5b2253fdbd86a30d504255ef` |

## 修正后的强制保留集合

| 类型 | Worktree／ref | Branch／object | 本次固定状态 | 保留理由 |
|---|---|---|---|---|
| 主工作树 | `/home/xp/src/ghc-api-proxy-py` | `main` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | current 集成真相源 |
| 新／进行中 | `/home/xp/src/ghc-api-proxy-py-route-happy` | `feat/anthropic-responses-route-happy` | `f3a5a768491c542224103a87b75e5bb39803ac4a` | route happy-path 进行中载体 |
| 新／进行中 | `/home/xp/src/ghc-api-proxy-py-block-delivery` | `feat/anthropic-block-delivery` | `e3fceb1cd14c44527bf2625acee0873421386caf` | block delivery 进行中载体 |
| 新／进行中 | `/home/xp/src/ghc-api-proxy-py-graceful-timeout` | `feat/systemd-graceful-timeout` | `865a5b71210e2436b36786b5de67146939d1e0f5` | graceful timeout 进行中载体 |
| 新／进行中 | `/home/xp/src/ghc-api-proxy-py-systemd-install` | `feat/systemd-user-install` | `e16c2a700f23f66535e7347ab7357518eb8e56bd` | systemd user install 进行中载体 |
| 新／进行中 | `/home/xp/src/ghc-api-proxy-py-semantic-parity` | `fix/responses-semantic-parity` | `80bc8f252b46c511f428af1d97159a5980ee9dc9` | R2 报告后新增的 semantic-parity 活动载体；必须保留 |

Current refs／worktrees 中没有游离的其他 non-archive branch 或未归类 registered worktree。后续若再新增任何 worktree／branch，它默认属于保留集合，除非另有独立审计明确纳入旧组清理 allowlist。

## Archive refs 精确保留矩阵

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

全部 archive refs 必须在每组清理前、worktree 移除后、activity branch 删除后逐项保持等式；不得移动、删除或 force-update。

## 执行时的完整机械门

1. **冻结 current main 与全集**：要求 physical root、`main`、`HEAD` 与 `refs/heads/main` 仍精确等于 `80bc8f252b46c511f428af1d97159a5980ee9dc9`；要求 current worktree／head 集合仍精确等于本文 19／29 对象。任何新增、删除、重绑或 main 前进均使本文 verdict 失效，先重审，不把新增对象猜成可清理。
2. **目标 identity**：目标路径必须仍为 registered worktree，physical top-level、symbolic branch 与完整 HEAD 必须逐项等于可清理表；不接受 detached HEAD、缩写 SHA 或同名前缀。
3. **未提交与操作状态**：`git status --porcelain -uall` 必须为空，且不得存在 merge、rebase、cherry-pick、revert 或 bisect 状态。任一非空即停止，不得 stash、restore、discard 或 force 绕过。
4. **ignored 删除面**：展开 `git ls-files --others --ignored --exclude-standard`；只允许本轮已核实的 `.coverage`、`.pytest_cache`、`.ruff_cache`、`.venv`、`src/**/__pycache__`、`tests/**/__pycache__` 可重建类别。出现 `.env`、数据库、草稿、未知目录或任意新增类别即停止并人工裁决。
5. **archive 精确性**：逐项验证本文 10-ref 矩阵，不只验证该组直接 archive。
6. **main 语义 identity**：重算原 R2 的 patch／range identity。Route source 组必须改用 `src/app/pipeline/route_policy.py` 与 `tests/smoke/test_route_policy.py` 两个 blob 在 `84a22c07…`、`7e4b642…`、`d913a033…` 与 current main 四处相等的门。
7. **逐组、先树后 branch**：一次只移除一个精确 worktree，不使用 `--force`；确认 registration 消失、精确 activity branch 仍指向固定 HEAD、main／5 个保留组／10 archives 未变后，才以安全删除方式删除该精确 activity branch。安全删除若拒绝，停止，不改用强制删除。
8. **逐组后验**：要求精确 activity branch 不存在；main、5 个保留 worktrees／branches 仍存在且对象未漂移；10 archives 仍逐项精确。完成后才进入下一组并从第 1 门重新开始。

## 事实性发现

[minor] `docs/tmp/260807-audit-worktree-cleanup-r2.md` 的 route blob oracle — 报告声称核对 route source 的两个 blobs，但其可执行门未给出正确文件；独立探测 `84a22c07…` 显示实际 source 文件为 `src/app/pipeline/route_policy.py` 与 `tests/smoke/test_route_policy.py` — 使用错误路径会得到“path does not exist”，使 route 组门 false-red；按本文精确路径重算后，两 blob 四处相等 — 采用本文第 6 门替代原 route blob 表述。

除上述局部可修正问题外，未发现阻断性问题。13 个旧 worktree／activity branch 的身份、clean／operation 状态、ignored 删除面、archive 身份和 current-main 语义 identity 均满足机械清理前提。

## 主观建议

未提出额外主观建议。本文只修正事实集合与可执行机械门，不扩大或缩减用户指定的清理范围。

## 最终结论

**0 major，明确可执行旧组清理。** 可清理对象严格限于本文列出的 13 个 worktree 及其精确 activity branches；执行时逐组通过八道门，不执行 force／discard／批量前缀删除。

**必须保留**：`main`、route-happy、block-delivery、graceful-timeout、systemd-install、报告后新增的 semantic-parity，共主树 1 组加新／进行中 5 组；以及全部 10 个精确 archive refs。任何当前未列入 13 组 allowlist 的对象均默认保留。

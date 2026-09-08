# Bridge foundations integration commits 只读回放预检

- **评审范围**：只读预检 `/home/xp/src/ghc-api-proxy-py-integrate-bridge` 的 `integrate/260806-bridge-foundations@6a00f6f7aaa5083cebd7387208eca65b7df3bd79`，base 固定为 `ed77c9d191df81c451c25161420515cca52ce6a4`。本轮只核验 Git 提交拓扑、精确 subject／path、第三提交 amend 身份、worktree cleanliness、逐提交 patch／tree／diff 身份、future-main blob／archive 回放 oracle，以及 source feature refs 是否仍指向最终 reviewed HEAD；没有重做代码 review，也没有执行候选代码测试。
- **总体 verdict**：**可逐个回放**。审计范围内 blocker 0、major 0；base 后恰好三个线性、非 merge commits，三个 source feature refs 均未漂移，第三提交包含已复评关闭的 amend 修复，目标 worktree clean。未来仍须按顺序逐个 cherry-pick，并在每片 main-side gate 通过后才创建对应 archive ref；本报告不把 integration 侧既有绿色结果替代为 future-main gate。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **写入边界**：目标 integration worktree 全程只读；本轮唯一写入是主树本报告。未执行任何会修改 Git index、refs、branch、tag、worktree registration 或提交对象的命令。

## 双视角覆盖证据

### 机械核对视角

- 每次 load-bearing shell 调用均在同一调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py-integrate-bridge`、当前分支为 `integrate/260806-bridge-foundations`、HEAD 为 `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。写报告时另验证主树为 `/home/xp/src/ghc-api-proxy-py`、分支 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。
- `git merge-base --is-ancestor` 确认 base 是 HEAD 的祖先；`git rev-list --count` 得到 `all=3`、`nonmerge=3`、`merge=0`。first-parent 顺序与完整 range 顺序完全相同，每个提交只有一个 parent，并形成 `ed77c9d… → 9e5f874… → cae83f4… → 6a00f6f…`。
- 分别以 `diff-tree --name-status` 核对每个提交的精确 path，以完整 commit object 核对 subject、parent 和 tree；stable patch-id 由 commit patch 与 parent→commit diff 两种入口交叉验证；binary full-index diff SHA-256 由 shell `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉验证。
- `git status --porcelain=v2 --untracked-files=all` 与后续 `git status --porcelain=v1 --untracked-files=all` 均无输出，目标 worktree clean。
- 对账 merged-state 代码 R2：它绑定 amended HEAD `6a00f6f…`，结论为 blocker 0、major 0，并明确可以按当前三个 squash commits 回放。对账独立 verification R2：它绑定同一 HEAD，在追加范围内为 `PASS`，但不外推为完整 bridge 产品 PASS。
- 对账三个 source feature 终审报告：reasoning cardinality、session liveness R3、request converter R3 均分别绑定下文完整 reviewed HEAD，均为 blocker 0、major 0、明确可 squash。当前 local source refs 与这些 HEAD 精确相等。

### 第一人称执行视角

- 作为 future-main 回放者，先从 current main 逐个消费现有 integration commits，而不从 feature branches 重建第二条集成链。每一步先验证当前提交的 parent／patch 身份与精确 path，再 cherry-pick；回放后验证本报告列出的累计 blob OID，执行该片 main-side tests／Ruff／Pyright／全仓 gate，通过后才进入下一片。
- 第一片回放后，验证 reasoning implementation 与 test blob；通过 cardinality main-side gate 后，archive reviewed source HEAD `b876e62…`。第二片回放后，验证前片 blobs 未回退并验证 liveness blobs；通过 liveness gate 后，archive `f27a8c0…`。第三片回放后，验证共享 reasoning blob 已更新为 amended integration 结果、此前 test／liveness blobs未回退，并验证 request converter／test blobs；通过 request 与跨片 gate 后，archive `fdd2f75…`。
- 模拟误操作分支：若只按 subject 猜提交、从 source feature tips 重建、把 integration commit 当作 archive target、在 main-side gate 前归档，或第三片只回放 amend 前的 `614cacd…`，都会违反现有收敛合同。本报告提供 commit patch identity、累计 blobs 和 reviewed source refs，分别拦截这些错误。
- future main 在 docs commit 后会产生不同的 commit OID 与整体 tree OID，因此不能要求 cherry-picked commit／tree 等于 integration 对象；应验证 patch-id、精确 paths 与相关 file blob OID。若 future main 在这些相关 paths 上另有变化，导致 blob oracle不能精确成立，应停止回放并重新裁决，而不是把差异解释为正常 cherry-pick 改号。

## 提交拓扑与精确身份

| 顺序 | Commit | Parent | Subject | Tree | Stable patch-id | Binary full-index diff SHA-256 |
|---|---|---|---|---|---|---|
| 1 | `9e5f874d5b547bd9d733b0ee134e165f818de205` | `ed77c9d191df81c451c25161420515cca52ce6a4` | `fix: preserve reasoning item cardinality` | `5e9ec5356ab791b16ee7ba429fc35ee953a0819a` | `d5a27f67b536a3144c8b9e33add8a4779b5cf337` | `8ad352e87829573d6301303dd645a8345d663ad1fca1fd76bb055a77a800323d` |
| 2 | `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` | `9e5f874d5b547bd9d733b0ee134e165f818de205` | `feat: add session liveness coordinator` | `c006600210c28f9abaf2450db208789a18d64378` | `80976d48781b46e56ca9dc142ead02f488d201b2` | `79116fab21916e63f606103666118f51c87ef57f067d32853443d409605a2895` |
| 3 | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` | `feat: convert Anthropic requests to Responses` | `5dedbe78281a08e10030a3da26d1a6d86491e23d` | `1f8c17fe1c12d4a3fe050a5754b6d54ae6b85811` | `9fb45f419b085f658e52e35403a06612f52672140820dc92a135b4cba0159b2b` |

哈希口径固定如下：stable patch-id 是 `git patch-id --stable` 对该提交 parent→commit patch 的第一列；diff SHA-256 是 `git diff --no-ext-diff --binary --full-index --no-renames <parent> <commit> --` 原始字节的 SHA-256。Tree 是 source integration commit 自身的完整 tree identity，用于冻结当前对象，不是 future main cherry-pick 后的预期 tree。

## 每个提交的精确 paths

### 1. Reasoning cardinality

`9e5f874d5b547bd9d733b0ee134e165f818de205` 只包含：

- `M src/app/anthropic/thinking/responses_reasoning.py`
- `M tests/unit/test_responses_reasoning.py`

### 2. Session liveness

`cae83f467aa66ebae74c27ad2270a79f5dd9aa8e` 只包含：

- `M src/app/streaming/keepalive.py`
- `M tests/unit/test_streaming_resilience.py`

### 3. Anthropic request converter

`6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 只包含：

- `M src/app/anthropic/thinking/responses_reasoning.py`
- `A src/app/protocols/anthropic_responses.py`
- `A tests/unit/test_anthropic_responses_request.py`

没有第四个提交承载 amend 修复；修复已包含在第三个 squash commit 中。

## 第三提交 amend 核验

- Amend 前对象：`614cacde72568d53170be714ea5c9a9b4d889a05`。
- Amend 后对象：`6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。
- 两者 parent 相同，均为 `cae83f467aa66ebae74c27ad2270a79f5dd9aa8e`；subject 相同，均为 `feat: convert Anthropic requests to Responses`。
- Author date 均为 `2026-08-07T01:31:52+00:00`；commit date 从 `2026-08-07T01:31:52+00:00` 更新为 `2026-08-07T01:49:37+00:00`。
- `614cacd… → 6a00f6f…` 的精确增量只有两条 path：`src/app/protocols/anthropic_responses.py` 增加 6 行，`tests/unit/test_anthropic_responses_request.py` 增加 78 行，没有删除行，也没有其他 path。
- 最终 tip 中存在 converter-local empty content-list typed reject：`invalid_content` 与 `message content list must not be empty`；测试覆盖 user／assistant 空 turn。最终 tip 也存在真实 `responses_reasoning_to_anthropic()` → request converter 的跨片回归，包含 encrypted-only `ENC-ONLY` 样本。
- Merged-state R2 对账同一增量并确认上一轮两个 major 均关闭，结论为 blocker 0、major 0；独立 verification R2 对同一 amended HEAD 的追加 oracle为 `PASS`。因此 future main 必须回放 `6a00f6f…`，不得退回 amend 前 `614cacd…`。

## Future-main 逐片 blob oracle

以下均为 Git blob OID。它们验证相关文件内容，而不要求 future main 的新 commit OID 或整体 tree OID等于 integration 对象。

### 回放第 1 片后

| Blob OID | Path |
|---|---|
| `09586654260a1a9dcfa0467cc4cdbbf990ac68f4` | `src/app/anthropic/thinking/responses_reasoning.py` |
| `3f6658d95dfc1259212649b0a73b5a38d1b9eaa9` | `tests/unit/test_responses_reasoning.py` |

该阶段 main-side cardinality gate 通过后，未来应创建：

- `refs/heads/archive/260806-anthropic-responses-reasoning-cardinality` → `b876e626dda821b267535b0bcffc9d81ced12763`

### 回放第 2 片后

| Blob OID | Path |
|---|---|
| `09586654260a1a9dcfa0467cc4cdbbf990ac68f4` | `src/app/anthropic/thinking/responses_reasoning.py`，前片必须保持 |
| `3f6658d95dfc1259212649b0a73b5a38d1b9eaa9` | `tests/unit/test_responses_reasoning.py`，前片必须保持 |
| `3aeb655cf667b6ee7bc207f21dadd9efa509dee2` | `src/app/streaming/keepalive.py` |
| `5f072f6290177789632fec19fe4c0dec7bfa87ec` | `tests/unit/test_streaming_resilience.py` |

该阶段 main-side liveness gate 通过后，未来应创建：

- `refs/heads/archive/260806-anthropic-responses-liveness` → `f27a8c04cd3470bd50d7194a30371ca5404f727e`

### 回放第 3 片后

| Blob OID | Path |
|---|---|
| `6a7614a356debb983511e5ff504205ae11cc3f56` | `src/app/anthropic/thinking/responses_reasoning.py`，amended shared-file 结果 |
| `3f6658d95dfc1259212649b0a73b5a38d1b9eaa9` | `tests/unit/test_responses_reasoning.py`，第一片测试必须保持 |
| `3aeb655cf667b6ee7bc207f21dadd9efa509dee2` | `src/app/streaming/keepalive.py`，第二片实现必须保持 |
| `5f072f6290177789632fec19fe4c0dec7bfa87ec` | `tests/unit/test_streaming_resilience.py`，第二片测试必须保持 |
| `858a6ab2deed9cccac61f1c3ee5a92ce373341ac` | `src/app/protocols/anthropic_responses.py` |
| `9e1e72625cd36be2e1680484e819b4a8b4379a0c` | `tests/unit/test_anthropic_responses_request.py` |

该阶段 request＋跨片 main-side gate 通过后，未来应创建：

- `refs/heads/archive/260806-anthropic-responses-request` → `fdd2f75fcec11e592b04f2686c4664262052a964`

上述三条 future archive refs 当前均不存在，这与“尚未回放 main、尚未完成 main-side gate”的状态一致。既有 `refs/heads/archive/260806-anthropic-responses-reasoning` 必须继续保持指向 `d90c90d7b52533e0dc5bd8baadc4c387a8511c3b`，不得移动或复用来归档 cardinality correction。

## Source feature refs 防漂移核验

| Source ref | 当前 target | 最终 review | 结论 |
|---|---|---|---|
| `refs/heads/fix/reasoning-cardinality` | `b876e626dda821b267535b0bcffc9d81ced12763` | `260806-review-code-reasoning-cardinality.md`：blocker 0、major 0、明确可 squash | 精确相等，未漂移 |
| `refs/heads/feat/session-liveness` | `f27a8c04cd3470bd50d7194a30371ca5404f727e` | `260806-review-code-liveness-r3.md`：blocker 0、major 0、可以 squash | 精确相等，未漂移 |
| `refs/heads/feat/anthropic-responses-request` | `fdd2f75fcec11e592b04f2686c4664262052a964` | `260806-review-code-request-r3.md`：blocker 0、major 0、可以 squash | 精确相等，未漂移 |
| `refs/heads/integrate/260806-bridge-foundations` | `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` | `260806-review-code-bridge-foundations-r2.md`：blocker 0、major 0；`260806-verify-bridge-foundations-r2.md`：范围内 PASS | 精确相等，未漂移 |

Archive target 必须使用表中前三个 reviewed feature HEAD，不能使用三个 integration commits替代。

## 回放门与边界

1. 只消费已冻结的 integration 链，顺序固定为 `9e5f874… → cae83f4… → 6a00f6f…`；不得从 feature refs重建第二套链，也不得使用 amend 前 `614cacd…`。
2. 每次 cherry-pick 前核验 current main、source integration ref、目标提交 parent／subject／paths、stable patch-id 与相关路径未发生未裁决变化。
3. 每次 cherry-pick 后先验证本报告对应阶段的累计 blob OID，再执行该片 main-side tests、交叠接缝测试、全仓回归、Ruff 与 Pyright；绿色后才进入下一片。
4. 每片 archive ref 只在该片进入 main 且 main-side gate 通过后创建，并必须精确指向最终 reviewed feature HEAD；不得指向 integration squash commit。
5. 前两片完成后仍保留共享 integration worktree／branch，因为它继续承载尚未进入 main 的后续提交。只有三片全部进入 main、三片 main-side gate 全绿、整链身份已记录且 integration worktree clean 后，才满足共享载体清理的技术门；实际清理仍需单独授权。
6. 本报告没有重做代码 review。它只证明当前冻结对象满足回放前 Git 身份与证据连续性要求；完整 bridge 产品状态仍为 `UNVERIFIED`。

## 事实性发现

未发现问题。审计范围内 blocker 0、major 0；当前三提交链可按上述顺序与 gate 回放。

## 主观建议

无。

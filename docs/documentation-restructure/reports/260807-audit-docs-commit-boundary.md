# Current 7 份正式文档提交边界只读审计

- **评审范围**：`main@ed77c9d191df81c451c25161420515cca52ce6a4` 的 current Git index／worktree，只审计下列 7 个精确正式文档路径的提交边界，以及 `docs/tmp/`、`verification/` 是否会被夹带。除本报告外未写仓库文件；未修改真实 index，未执行 commit。
- **总体 verdict**：**修复 major 后可进入**。当前 index 不能直接提交；先按本文机械门精确 `git add` 7 路径并冻结、核对 index 后，才可形成仅含 7 份最终 worktree bytes 的提交。现有链接审计绑定的 3 个 source hash 已漂移，必须先在 current frozen bytes 上重跑并取得 0 blocker／0 major。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。

## 双视角覆盖证据

### 机械核对

1. 每次 shell 调用均在同一次调用内验证物理 root 为 `/home/xp/src/ghc-api-proxy-py`、分支为 `main`、HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。
2. 对 7 个精确路径连续执行两轮 SHA-256；两轮逐路径完全相等。随后分别对 `git status --short`、`git diff --cached --name-status`、`git diff --name-status`、index stage blob 与 worktree blob 做对账。
3. 以真实 index 文件 SHA-256 前后夹住 `git commit --dry-run --only -- <7 paths>`。该命令因未跟踪的 `README.md` 返回 1；真实 index 前后均为 `2b56de0de74cb7d47de7f20dda9f1739d44acbba492c0990605c116053cdf90c`，确认 dry-run 未修改 index。
4. 复制真实 index 到 `/tmp`，同时使用独立临时 object directory，模拟精确 `git add -- <7 paths>`。模拟 index 相对 HEAD 的 staged 集合精确等于 7 路径，每个 index blob 均等于对应 worktree blob；`git diff --cached --check HEAD -- <7 paths>` 通过；随后 `git commit --dry-run --only -- <7 paths>` 返回 0，并只将 7 份文档列为待提交。真实 index 在模拟前后仍保持上述 SHA-256 不变。
5. 对 `docs/tmp/` 与 `verification/` 分别检查 staged／unstaged／untracked 状态。它们当前均未进入 staged 集合；模拟 dry-run 仅把它们列在 `Untracked files`，没有纳入待提交集合。

### 第一人称执行模拟

1. 模拟直接照“`git commit --only -- <7 paths>`”执行：执行者会在 `README.md` 遇到 `pathspec ... did not match any file(s) known to git`，命令返回 1，无法形成提交。
2. 模拟忽略 `AM` 的第二列而直接普通 commit：6 份 `AM` 文档会取 index 中较旧的 staged blobs，不会取已复评的最终 worktree blobs；`README.md` 为 `??`，不会进入提交。该路径会得到错误提交边界。
3. 模拟先精确 add 7 路径，再逐个核对 index blob＝worktree blob，并确认 staged 集合精确等于 7 路径：普通 commit 会消费刚刚冻结且已验证的 index，不会夹带 `docs/tmp/` 或 `verification/`。
4. 模拟 add 后仍使用 `commit --only`：在当时 worktree 未漂移时，临时 index dry-run确实只选择 7 份最终内容；但 `--only` 的目标是直接从指定 worktree 路径形成提交，而不是消费前一步已经验证的 index 快照。若核验后、commit 前 worktree bytes 再变化，它会绕过已冻结的 blob 身份。因此推荐普通 commit，而不是把 `--only` 作为最终提交机制。

## 精确路径与冻结内容

| Path | Current status | Worktree SHA-256 | Current index blob | Worktree blob | Index＝worktree |
|---|---:|---|---|---|---:|
| `docs/agents/anthropic-responses-bridge/README.md` | `??` | `3f48e6a3cab32545591bad32ae3ee96682a4d9cc870408fbe1da87f664b9b920` | none | `5aef0d2c24f32949ddd29e502d9e3ec13a41ebb8` | no |
| `docs/agents/anthropic-responses-bridge/spec.md` | `AM` | `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694` | `32dbb8644a1504f20e9ef8eff219951521bdff41` | `717a3107bda7f0599b4a45a50313a3c3ad090144` | no |
| `docs/agents/anthropic-responses-bridge/architecture.md` | `AM` | `6de919d696514eb69949a57de0916dc7650e055929b174c9af6386afe0f3f327` | `24685e1d63ca239937c5085ab960c898bfd26030` | `95391513c2f5130f4919fb5aa1f0fa161db5a95b` | no |
| `docs/agents/anthropic-responses-bridge/acceptance.md` | `AM` | `31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091` | `f87e7509af8d51914e87f71d89651bd2b22e3b09` | `fa681e956dc8d7ee6c4ce0113e8bfbfd5aa4e989` | no |
| `docs/agents/anthropic-responses-bridge/research.md` | `AM` | `54cf0cde2bc7122516bec9948f62a65f7900c775d5bd1da6200cb224f184856e` | `aefdd33c8f8065dfd10b4f5f4314e1af69c642d2` | `65bfbe1054e51dbe0e24a1fc6655cebab40d1841` | no |
| `docs/agents/anthropic-responses-bridge/implementation.md` | `AM` | `e43fd96003a8de3a1b9c5e165a65d711e25e76d1cc6444415088af0a994dda65` | `b0146833a1215d75fbee92efc74cc7b8e7d9b9ac` | `2116cd5c8c1ece7af2c2b113705d81a912720c14` | no |
| `docs/agents/documentation-restructure/plan.md` | `AM` | `53f7a02c936801e5f68fb67701449521941f2599c1d0092a8cf11eea1a6190ad` | `c451c74f646976c76fb156d0a3e3ba30ca260f25` | `afe0147ddb0bd25d46522740849d7af87eb9630c` | no |

`AM` 的第一列 `A` 表示 index 相对 HEAD 是新增文件，第二列 `M` 表示 worktree 又相对 index 修改；因此当前 staged blob 不是最终 worktree blob。`??` 表示路径尚不为 Git 所知；它既不在 index，也不能直接被 `commit --only` pathspec 接受。本轮没有 plain `A`；若精确 add 成功，7 路径都应变为 plain `A`，且 index blob 应等于 worktree blob。

## 事实性发现

### [major] 当前 index 不是可提交的最终文档快照

- **位置**：上述 7 个正式文档路径。
- **问题**：6 路径为 `AM`，其 index blob 全部不同于 worktree blob；`README.md` 为 `??`，不在 index。
- **失败场景**：现在直接执行普通 commit，只会提交 6 个旧 staged blobs并遗漏 README。现在直接执行 `git commit --only -- <7 paths>`，会因 README pathspec 未被 Git 跟踪而返回 1。
- **修复建议**：精确 add 7 路径；立即验证 staged 集合精确相等、无 unmerged stage、每个 index blob＝worktree blob、冻结 SHA-256 未漂移且 cached diff check 通过；随后用普通 commit消费已验证 index。

### [major] 现有链接审计不能作为 current bytes 的提交证据

- **位置**：`docs/tmp/260807-audit-doc-links.md` 的“输入快照”与“若任一 source SHA-256 改变”失效条款。
- **问题**：该报告绑定的 `README.md`、`implementation.md`、`plan.md` SHA-256 分别为 `b7281a1f…`、`5b20c8ab…`、`b3235905…`；current frozen hashes已分别变为 `3f48e6a3…`、`e43fd960…`、`53f7a02c…`。
- **失败场景**：沿用旧 0／0 verdict 会把旧 bytes 的链接结论冒充 current 7 文档结论，违反该报告自身的失效条件。
- **修复建议**：在本文冻结的 7 个 SHA-256 上重新执行相对 Markdown 链接审计。新报告必须明确绑定 `main@ed77c9d…`、完整 7-source hash manifest，并取得 blocker 0、major 0；若任一 source hash再变，重新审计。

## 主观建议

### [建议] 选择“精确 add＋验证 index＋普通 commit”，不要以 `commit --only` 取代冻结

- **位置**：最终提交动作。
- **改进点**：把已评审 worktree bytes转成一个明确、可机械对账的 index 快照，再提交该快照。
- **预期影响**：同时关闭 `AM` stale index、`??` README、旁路 staged 文件夹带，以及核验后 worktree 漂移被 `--only` 重读的风险。
- **推荐做法**：先运行下方预提交机械门；门全绿后，另起一次显式 commit 操作。最终 commit 使用普通 `git commit -m '<message>'`，不带 pathspec。提交动作本身不包含在本文脚本中。

## 可复制的预提交机械门

以下脚本会**修改 index**，因为它代表未来获准提交时的精确冻结步骤；它不会执行 commit。当前只读审计没有运行此脚本中的真实 `git add`。

```bash
set -euo pipefail
ROOT=/home/xp/src/ghc-api-proxy-py
EXPECTED=ed77c9d191df81c451c25161420515cca52ce6a4
cd "$ROOT"
test "$(git rev-parse --show-toplevel)" = "$ROOT"
test "$(git symbolic-ref --short HEAD)" = main
test "$(git rev-parse HEAD)" = "$EXPECTED"

paths=(
  docs/agents/anthropic-responses-bridge/README.md
  docs/agents/anthropic-responses-bridge/spec.md
  docs/agents/anthropic-responses-bridge/architecture.md
  docs/agents/anthropic-responses-bridge/acceptance.md
  docs/agents/anthropic-responses-bridge/research.md
  docs/agents/anthropic-responses-bridge/implementation.md
  docs/agents/documentation-restructure/plan.md
)

TMP=$(mktemp -d /tmp/260807-doc-commit-gate.XXXXXX)
trap 'rm -rf -- "$TMP"' EXIT

for p in "${paths[@]}"; do test -f "$p"; done
for p in "${paths[@]}"; do sha256sum -- "$p"; done > "$TMP/hash-1"
for p in "${paths[@]}"; do sha256sum -- "$p"; done > "$TMP/hash-2"
cmp -s "$TMP/hash-1" "$TMP/hash-2"
cat > "$TMP/expected-hashes" <<'HASHES'
3f48e6a3cab32545591bad32ae3ee96682a4d9cc870408fbe1da87f664b9b920  docs/agents/anthropic-responses-bridge/README.md
a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694  docs/agents/anthropic-responses-bridge/spec.md
6de919d696514eb69949a57de0916dc7650e055929b174c9af6386afe0f3f327  docs/agents/anthropic-responses-bridge/architecture.md
31673f4af6d3a7fe7d8ccdec7ef8d69f9d20559e0976826d8607999548906091  docs/agents/anthropic-responses-bridge/acceptance.md
54cf0cde2bc7122516bec9948f62a65f7900c775d5bd1da6200cb224f184856e  docs/agents/anthropic-responses-bridge/research.md
e43fd96003a8de3a1b9c5e165a65d711e25e76d1cc6444415088af0a994dda65  docs/agents/anthropic-responses-bridge/implementation.md
53f7a02c936801e5f68fb67701449521941f2599c1d0092a8cf11eea1a6190ad  docs/agents/documentation-restructure/plan.md
HASHES
cmp -s "$TMP/expected-hashes" "$TMP/hash-1"

# 硬前提：先取得绑定上述完整 hash manifest 的新链接审计 0 blocker／0 major verdict。
# 当前 docs/tmp/260807-audit-doc-links.md 的输入 hashes 已漂移，不能放行本门。

git add -- "${paths[@]}"

printf '%s\0' "${paths[@]}" | sort -z > "$TMP/expected-paths"
git diff --cached --name-only -z HEAD | sort -z > "$TMP/staged-paths"
cmp -s "$TMP/expected-paths" "$TMP/staged-paths"
test -z "$(git ls-files --unmerged -- "${paths[@]}")"

for p in "${paths[@]}"; do
  index_blob=$(git ls-files --stage -- "$p" | awk '$3 == 0 {print $2}')
  worktree_blob=$(git hash-object -- "$p")
  test -n "$index_blob"
  test "$index_blob" = "$worktree_blob"
done

# cached diff 覆盖新加入的 README；普通 worktree diff 不覆盖未跟踪文件，不能替代此门。
git diff --cached --check HEAD -- "${paths[@]}"

# 旁路目录必须仍未 staged；它们可以继续保持 untracked。
test -z "$(git diff --cached --name-only -- docs/tmp verification)"

git status --short --untracked-files=all -- "${paths[@]}" docs/tmp verification
printf '%s\n' 'READY: exact seven-path index snapshot verified; no commit executed.'
```

## 提交动作与提交后机械核验

预提交门全绿后，推荐另起一次显式操作执行普通 commit。不要把 commit追加在 gate 的同一段 shell 中；先人工确认 gate 输出，再提交。本文不执行也不代为授权该动作。

提交完成后，以下脚本验证提交边界和预期 status。它本身不修改 index，也不创建提交：

```bash
set -euo pipefail
ROOT=/home/xp/src/ghc-api-proxy-py
PARENT=ed77c9d191df81c451c25161420515cca52ce6a4
cd "$ROOT"
test "$(git rev-parse --show-toplevel)" = "$ROOT"
test "$(git symbolic-ref --short HEAD)" = main
test "$(git rev-parse HEAD^)" = "$PARENT"

paths=(
  docs/agents/anthropic-responses-bridge/README.md
  docs/agents/anthropic-responses-bridge/spec.md
  docs/agents/anthropic-responses-bridge/architecture.md
  docs/agents/anthropic-responses-bridge/acceptance.md
  docs/agents/anthropic-responses-bridge/research.md
  docs/agents/anthropic-responses-bridge/implementation.md
  docs/agents/documentation-restructure/plan.md
)

TMP=$(mktemp -d /tmp/260807-doc-postcommit-gate.XXXXXX)
trap 'rm -rf -- "$TMP"' EXIT
printf '%s\0' "${paths[@]}" | sort -z > "$TMP/expected-paths"
git diff-tree --no-commit-id --name-only -r -z HEAD | sort -z > "$TMP/commit-paths"
cmp -s "$TMP/expected-paths" "$TMP/commit-paths"

test -z "$(git status --porcelain=v1 --untracked-files=all -- "${paths[@]}")"
test -z "$(git diff --cached --name-only)"
for p in "${paths[@]}"; do
  commit_blob=$(git rev-parse "HEAD:$p")
  index_blob=$(git ls-files --stage -- "$p" | awk '$3 == 0 {print $2}')
  worktree_blob=$(git hash-object -- "$p")
  test "$commit_blob" = "$index_blob"
  test "$index_blob" = "$worktree_blob"
done

git diff-tree --check HEAD^ HEAD -- "${paths[@]}"
test -z "$(git diff --cached --name-only -- docs/tmp verification)"
printf '%s\n' 'Expected remaining status: the seven formal docs are clean; docs/tmp and verification remain untracked and uncommitted.'
git status --short --untracked-files=all -- docs/tmp verification
```

## 提交后 status 预期

- 7 个正式文档路径不再出现在 `git status --short -- <7 paths>` 中。
- index 没有 staged leftovers；commit tree、index blob 与未再修改的 worktree blob逐路径相等。
- 新提交相对 parent `ed77c9d…` 的 changed-path 集合精确等于 7 路径。
- `docs/tmp/` 与 `verification/` 继续显示为 `??`，包括本报告；它们不进入新提交，也不因正式文档提交而被清理或改写。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| 6 个 `AM` 正式文档 | index／worktree 双快照漂移，同一路径存在两版内容 | 本轮不修改 index；提交前用精确 add统一到最终 worktree blob，并逐路径机械对账 |
| `README.md` 的 `??` 与直接 `commit --only` | 提交策略没有覆盖 untracked path 的入口条件 | 禁止直接 `commit --only`；先精确 add，再验证 index |
| `260807-audit-doc-links.md` 与 current 3 个 source hashes | 证据绑定对象漂移 | 在 current frozen 7-source manifest 上重跑链接审计，旧 verdict 不沿用 |

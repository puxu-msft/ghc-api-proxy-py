# systemd runtime squash 只读回放审计

- **评审范围**：只读审计 `/home/xp/src/ghc-api-proxy-py-integrate-systemd` 的 `integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef`，目标父提交固定为 `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1`；对照 `/home/xp/src/ghc-api-proxy-py-systemd` 的 reviewed source range `ed77c9d191df81c451c25161420515cca52ce6a4..49fb1988621bba4356e7a5039a6994c2e6d19604`。本轮核验提交拓扑、精确 8 paths、stable patch-id、binary full-index diff、结果 blobs、目标 HEAD 测试证据与 clean 状态；没有安装、启用、启动、停止、restart 或 reload unit，也没有修改任何 Git ref。
- **总体 verdict**：**可回放。** 目标相对 `ec5…` 恰为单一非 merge commit；其补丁与 reviewed source 三提交 range 相对原始 base `ed77…` 完全等价；目标与 source worktree 均 clean；目标 squash HEAD 的定向及全仓质量门通过。审计范围内 **0 blocker／0 major**。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **写入边界**：integration 与 source worktree 全程只读；唯一写入是主树本报告 `docs/tmp/260807-audit-systemd-squash.md`。本报告不授权安装 unit、改变 systemd manager 状态、切换生产 listener、删除 worktree 或发布远端。

## 双视角覆盖证据

### 机械核对视角

- 固定物理目标 root、branch 与 HEAD，确认 `fe9c203…` 的唯一 parent 是 `ec5e8f5…`；`ec5…→fe9c…` 的提交数为 1，merge commit 数为 0，subject 为 `feat: add systemd socket activation runtime`。
- 分别从目标 `ec5…→fe9c…` 与 source `ed77…→49fb…` 枚举 name-status，两个集合逐字一致且恰含 8 paths。source range 是三条线性提交：`66551e45…`、`1a220e04…`、`49fb198…`。
- 对两侧使用同一口径 `git diff --no-ext-diff --binary --full-index --no-renames <base> <tip> --`。两侧 stable patch-id 均为 `eab37d38b63730f895be3e55fd256f0547209630`，原始 diff SHA-256 均为 `efd8db7147b02e577747b2391ef108ccd83e33b473ea2edb4663d6d11298c8b0`，且 8 个结果 blob OID 逐 path 相等。patch-id、原始 diff bytes 与结果 blob 是三种不同粒度的交叉证据。
- `git status --porcelain=v2 --untracked-files=all` 在目标和 source 验证前后均为空。目标门结束后再次确认目标 worktree clean。
- 对账 `docs/tmp/260807-review-code-systemd-runtime-r4.md`：它精确绑定 source `49fb…`，结论为 `0 blocker／0 major`、明确可 squash；本审计没有把该 verdict 当作补丁身份的替代证据，而是独立重算 source range 与 squash 的 patch 身份。

### 第一人称执行视角

- 作为 main 回放者，先确认 current main 仍为目标 parent `ec5…`，integration ref 仍精确指向 `fe9c…`，目标树 clean，再消费这个已冻结 squash；不从 source 三提交重新构造第二条集成链。
- 回放后先核对精确 8 paths 与下文 8 个 blob OID，随后确认 Python import oracle 指向 main 自身 `src/app/__init__.py`，执行定向 pytest、全仓 pytest、全仓 Ruff 与全仓 Pyright，最后复核 main clean／仅存在预期回放提交及既有主树工作项。
- 模拟错误分支：若从 `ec5…` 错误比较 source `49fb…`，会把 source 基于旧 base 而未拥有的后续主线文档误判为删除；正确比较必须是目标 `ec5…→fe9c…` 对 source `ed77…→49fb…`。若 archive 指向 integration squash `fe9c…`，则丢失 reviewed feature lineage；archive target 必须是 `49fb…`。
- 只有回放后的 main-side gates 全绿，才创建 archive ref。仓库态测试不等于 unit 已安装或真实 manager／cgroup 已验收，不能从本报告外推部署完成。

## 提交身份与精确 paths

目标提交：

- Commit：`fe9c20315b0137ca5b2253fdbd86a30d504255ef`
- Parent：`ec5e8f5240c6a587544e022b449aa7b392ba7ca1`
- Subject：`feat: add systemd socket activation runtime`
- Stable patch-id：`eab37d38b63730f895be3e55fd256f0547209630`
- Binary full-index diff SHA-256：`efd8db7147b02e577747b2391ef108ccd83e33b473ea2edb4663d6d11298c8b0`

精确 8 paths：

- `M README.md`
- `A contrib/systemd/ghc-api-proxy.service`
- `A contrib/systemd/ghc-api-proxy.slice`
- `A contrib/systemd/ghc-api-proxy.socket`
- `A docs/agents/deployment-systemd/README.md`
- `M src/app/cli.py`
- `A tests/smoke/test_systemd_units.py`
- `M tests/unit/test_cli.py`

Reviewed source range：

1. `66551e451d15ebd95a2bcfb5f0eaa227e8cb82ff` — `feat: add systemd socket activation runtime`
2. `1a220e04a99c6ce07b4bdd6bb0876b4180d4c489` — `fix: harden systemd runtime contract`
3. `49fb1988621bba4356e7a5039a6994c2e6d19604` — `fix: restrict systemd state permissions`

Source range 的原始 base 是 `ed77c9d191df81c451c25161420515cca52ce6a4`。目标 squash 的 parent 是后续 main `ec5e8f5…`；两边 parent 不同，因此不得要求完整 tree OID 相等，正确 oracle 是补丁 bytes、patch-id、path 集合与受影响文件的结果 blob 一致。

## Main 回放后 blob oracle

| Blob OID | Path |
|---|---|
| `2dedabf34ff8c61ed8f5d80718e1abeb2661d41a` | `README.md` |
| `33fe7a27ef92dd0c4c45e65f8311963919dada8d` | `contrib/systemd/ghc-api-proxy.service` |
| `26004f5d3921b8e1d6851a1c2039cd85e206ee79` | `contrib/systemd/ghc-api-proxy.slice` |
| `f41f01f29e67e6d63947a8cd4fc7f7ecb60dce81` | `contrib/systemd/ghc-api-proxy.socket` |
| `2e6c5b43dd280e26564a922672c33c4103dcd75b` | `docs/agents/deployment-systemd/README.md` |
| `aaada4f20b34519d6bec98b0dbe344134a5e3d22` | `src/app/cli.py` |
| `78866bede2150838b8bbaaf155f9dc4268438dcc` | `tests/smoke/test_systemd_units.py` |
| `62575181a8d50152e56a2c778bc49db500461315` | `tests/unit/test_cli.py` |

这些 blob OID 是回放后相关文件的精确内容 oracle，不要求 future main 的新 commit OID 或整体 tree OID等于 integration 对象。若任一相关 path 已有未裁决变化或 cherry-pick 产生冲突，应停止并重新裁决，不能以“回放改号”解释 blob 差异。

## 测试证据

在 `integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef` 上，Python import oracle 为 `/home/xp/src/ghc-api-proxy-py-integrate-systemd/src/app/__init__.py`。本轮实际完成：

- 定向 `pytest -p no:cacheprovider -q tests/unit/test_cli.py tests/smoke/test_systemd_units.py`：`17 passed`；同一 HEAD 的独立 `--collect-only` 交叉核对为 `17 tests collected`。
- 全仓 `pytest -p no:cacheprovider -q tests`：`301 passed`；同一 HEAD 的独立 `--collect-only` 交叉核对为 `301 tests collected`。
- 全仓 `ruff check src tests`：通过。
- 全仓 `pyright --pythonpath /home/xp/src/ghc-api-proxy-py/.venv/bin/python src tests`：通过，`0 errors, 0 warnings, 0 informations`。
- 所有完成门之后，目标 `git status --porcelain=v2 --untracked-files=all` 为空。

首次全仓 pytest 尝试受到共享终端外部 `Ctrl-C` 中断，不计为通过或失败；随后以忽略共享终端 SIGINT 的隔离进程完整重跑并通过。测试没有连接真实 systemd manager、安装 unit 或验证生产 cgroup effective limits；这些边界保持在后续部署／运行态 gate。

## Main 回放后 gate

1. **回放前身份门**：主树物理 root 为 `/home/xp/src/ghc-api-proxy-py`、branch 为 `main`、HEAD 为 `ec5e8f5240c6a587544e022b449aa7b392ba7ca1`；integration ref 为 `fe9c203…`；目标 worktree clean。若 main 已前移或 8 个相关 paths 已变，先重新裁决，不机械沿用本 verdict。
2. **只消费冻结 squash**：回放 `fe9c20315b0137ca5b2253fdbd86a30d504255ef`，不得改从 source 三提交重建；确认产生单一语义提交且精确变更面仍为上述 8 paths。
3. **补丁与内容门**：回放结果相对回放前 main 的 stable patch-id 应为 `eab37d38…`，并逐项核对上述 8 个 blob OID。若主树上下文导致 patch-id 或 blob 变化，停止并重新审查差异。
4. **目标树 import 门**：设置 `PYTHONPATH=<main>/src`，确认 `import app` 解析到主树自身 `src/app/__init__.py`，不得通过共享环境加载相邻 worktree。
5. **代码门**：执行定向 pytest、全仓 pytest、全仓 Ruff 与全仓 Pyright，命令口径与本报告“测试证据”一致；所有命令必须完整退出 0，不能采信被中断、超时、提前返回或只跑 source worktree 的结果。
6. **clean 与提交门**：核对回放提交 subject／paths、`git diff --check`、主树 status 仅含回放前已知工作项且没有测试副产物；若需提交，精确限定本切片 paths，避免吸收主树其他并行 WIP。
7. **archive 门**：只有回放后的 main-side gates 全绿，才创建 `refs/heads/archive/260807-systemd-runtime`，并让它精确指向 reviewed source `49fb1988621bba4356e7a5039a6994c2e6d19604`。不得指向 integration squash `fe9c203…`，不得在 main-side gates 之前归档。
8. **边界门**：回放与 archive 不授权清理 source／integration worktree 或 branch，不授权任何远端发布，也不授权 unit 安装、daemon-reload、enable、start、restart 或生产 cutover。

## 事实性发现

未发现问题。审计范围内 blocker 0、major 0、minor 0；`integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef` 明确可按上述 gate 回放。

## 结构怪味扫描与处置

- `source ed77…→49fb…` 与 `target ec5…→fe9c…` — **同一补丁跨不同 parent，若误用同一 base 比较会制造虚假删除** — 本轮已用每侧真实 parent 比较 stable patch-id、binary diff 与结果 blobs；回放 gate 固化该边界。
- `fe9c203…` 与 `49fb198…` — **integration 对象与 reviewed lineage target 职责不同** — 本轮明确回放对象是 `fe9c…`，archive target 是 `49fb…`，防止把 squash commit 当作 feature 归档点。
- 测试证据 — **共享终端可注入 `Ctrl-C`，单次中断输出可能被误读为产品失败或假绿** — 本轮废弃中断尝试，以忽略共享 SIGINT 的完整重跑作为证据；回放后也必须要求完整退出 0。

## 主观建议

无。

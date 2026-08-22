# 会话收尾记录 — `strip_anthropic_beta_flags` 与请求头黑白名单

**日期**：2026-08-22
**触发**：用户「schema 没建模我新加的 strip_anthropic_beta_flags 导致测试红了，实现这个部分，更新相关文档」，其后追加七条裁决与一次权威文档更新。
**实现细节与裁决处置**：`260822-beta-flag-strip-implementation.md`（本文件不复述，只承载本次会话的**终态事实**）。

本文件存在的原因很具体：临时证据清单 `$CLAUDE_JOB_DIR/tmp/DISPOSITION.md` 的多行把「结论的载体」指向了一份当时**尚未写下**的终态报告，独立评审（`../../tmp/260822-review-disposition-manifest.md`，major-1/major-2）逐条证否。补上载体，而不是改软那些行的措辞。

---

## 1. 交付了什么，落在哪

主仓 `ghc-api-proxy-py`：

| 提交 | 内容 |
|---|---|
| `a2169de` | `strip_anthropic_beta_flags` 建模 + 接进新链路 + 单元与端到端测试 |
| `80068eb` | 七条裁决落地：键改按 resolved_model 正则匹配先匹配者赢、删 `strip_attribution_header`、修 8 处文档断链与 `loader.py` 过时 docstring、请求头黑白名单两级机制、`request_headers` 大小写不敏感合并 |
| `959e8d1` | 权威文档新明确的「大小写不敏感」的回归测试 |
| `81c36d2` | 去掉一条因用户改正 typo 而过时的测试 docstring 说明 |

`.dev`（独立仓，**从不推送**）：`0ca6da8`、`41e98ef`、`2ab949a`、`cb472f7` —— 实现报告及其两轮修订，加三份评审/调查原件。

**均未推送。** 主仓 `main` 领先 `origin/main`，这是既有状态，本会话没有也不打算改变它。

## 2. 验证：命令、结果、锚点

**门跑在 `959e8d1`**（当时的 HEAD；本文件写定时 HEAD 已被同伴推进到 `1459320`，那之后的提交与本切片无交集）。三项均为本次会话**新产出**，不是复用的旧证据：

| 命令 | 结果 |
|---|---|
| `uv run ruff check src tests` | **All checks passed** |
| `uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80` | **1787 passed / 2 skipped / 0 failed**，覆盖率 **89.33%** |
| `uv run pyright src tests` | **21 errors** |

**那 21 个 pyright 错全部落在 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`**，是同伴的区域（`stream_cap.py` committed at `2b20be7`，其测试当时有同伴未提交改动），我改动的文件零错。判定方法是把 pyright 输出里的路径抽出去重：

```bash
rg -o '^\s*/home/xp/src/ghc-api-proxy-py/(\S+\.py)' -r '$1' <pyright 输出> | sed 's/:.*//' | sort -u
```

### 历史上几次门的读数（供比对，非终态）

| 时刻 | 树 | 结果 | 说明 |
|---|---|---|---|
| 首轮 | 工作树（含同伴改动） | 1738 passed / 1 failed | 那条失败是瞬时的——同伴在那 105 秒内改树，单独重跑整个 int 文件 113 全绿 |
| 裁决前 | 工作树 | 1757 passed / 0 failed / 91.13% | |
| 裁决后 | 工作树 | 1768 passed / **5 failed** | 五条全在 `tests/unit/test_cli.py`，来自同伴进行中的 `pidfile` → `pidfile_dir` 重构（`StandaloneOptions` 无 `pidfile` 属性）；我的 diff 不含 `StandaloneOptions`，`cli.py` / `lifecycle/entry.py` 均在同伴的脏文件集里 |
| 干净 checkout `80068eb` | 一次性 worktree | 1771 passed / **1 failed** | `test_authoritative_example_config_parses`，**父提交 `1c91870` 上同样红**；成因是同伴的 `fa0b281` 提交了 `config.example.yaml` 的旧快照（仍带 `streamReplay`），用户工作树里的当前版本早已删掉它 |
| 收尾 | 工作树（`959e8d1`） | **1787 passed / 0 failed / 89.33%** | 终态 |

**一次门跑在过滤后的文件子集上**：14:57 那轮，因同伴的 `tests/int/test_standalone_lifecycle.py` 带有 `F821: Undefined name 'standalone_pidfile_path'`，我把 ruff 的目标缩到自己动过的文件。那一轮的 ruff 结论**只覆盖我的文件**，不是全仓结论；全仓结论由上表收尾那一行承担。

## 3. 变异验证：四轮，证明了什么、没证明什么

| 变异 | 打红的测试 |
|---|---|
| `denied_by_model=` → `{}`（接线断开） | `..._does_not_reach_upstream`、`..._translated_path_too` |
| `models=` → 只传 `resolved_model` | `test_the_table_fires_on_the_alias_the_client_asked_for` |
| `configured` 取客户端拼写而非配置拼写 | `..._counted_under_the_configured_spelling`、`..._reported_as_configured` |
| `REQUEST_FLOOR` 比对去掉 `.lower()` | `test_the_blacklist_is_case_insensitive_for_every_entry_the_document_names` |

四轮全部恢复：`rg MUTATION-PROBE src tests` 无匹配，且与变异前备份 `diff` 逐字节一致。

**证明了**：配置 → `shape_request` → `client_headers` → 上游请求头这条接线是活的；键匹配按 resolved 生效；指标标签取配置拼写；floor 的大小写不敏感是有意为之而非构造性为真。
**没有证明**：剥掉那四个 flag 之后上游真的不再 400——那是上游行为，只有实测能答。

## 4. worktree 生命周期

本会话在共享仓上建过**三棵一次性 detached worktree**，全部位于 `$CLAUDE_JOB_DIR/tmp` 下，全部已 `git worktree remove --force` 移除，移除前均确认 `git status --porcelain` 为 0 行且 HEAD 为 detached：

| 名字 | 锚点 | 用途 | 状态 |
|---|---|---|---|
| `verify-head` | `8b71266` | 验证 `a2169de` 的提交自洽 | 已移除 |
| `verify-head2` | `80068eb` | 干净 checkout 上跑全量 | 已移除 |
| `verify-parent` | `1c91870` | 判定那条红是否先于我的提交 | 已移除 |

复测：`git worktree list` 只剩主树与三棵**同伴的**（`826d4cda/tmp/review`、`delivery-keepalive`、`upstream-error-events`），三个目录在文件系统上也已不存在。移除时用了 `GIT_DISCIPLINE_OK=1` 前缀绕过纪律护栏，每次都先自检归属与干净度——护栏拦的是「删同伴的 worktree」，这三棵是我自己刚建的。

## 5. 分支与发布

**没有开分支。** 本会话全程在共享主树上直接向 `main` 提交，符合项目对中小改动的约定。因此 `finishing-a-development-branch` 的 merge / keep / discard 三选一不适用——没有分支要处置。

**未推送，也未请求推送。** 用户没有给出当前的、明确的发布指令。

## 6. 同伴工作的保全

共享主树全程有同伴并行工作。本会话采取的措施与实测结果：

- **提交一律带 pathspec**，且提交前对每个路径跑 `git diff -- <path>` 逐 hunk 认领。
- `src/app/config/schema.py` 是混合文件（同伴在做 `pidfile` → `pidfile_dir`），走**内容级构造 + 私有索引 + CAS `update-ref`**：从基线 `git show HEAD:<path>` 造出只含我那两处改动的完整内容，`hash-object -w` 成 blob，私有索引 `write-tree` → `commit-tree` → `update-ref <new> <old>`。提交前用 `git diff-index --cached -p HEAD` 逐行确认不含 `pidfile_dir`。
- 用户自己暂存的 `docs/.human-controlled/*` 与 `CLAUDE.md` **全程未被卷入**任何一次提交。
- **踩到并修复了一处**：`update-ref` 只移动分支、不碰索引，于是主索引停在旧 HEAD，12 个文件变成 `MM`——等于暂存了一份「回退我全部改动」的版本，任何人跑一次裸 `git commit` 就会把它提交上去。用 `git reset -- <我提交过的路径>` 修复（带 pathspec 的 reset 只动索引、不碰工作树），复测 `git status --short | rg '^MM'` 无输出。

## 7. 文档去向

- **实现与裁决**：`260822-beta-flag-strip-implementation.md`（活文档，本切片的权威）
- **本文件**：终态事实
- **评审与调查原件**（时点记录，不改写）：`../../tmp/260822-review-beta-flag-strip.md`、`../../tmp/260822-verify-beta-flag-strip-docs.md`、`../../tmp/260822-header-forwarding-surface.md`、`../../tmp/260822-review-disposition-manifest.md`、`../../tmp/260822-review-closeout-claims.md`
- **对账过的活文档**：`../../hosted-web-search/status.md` §4.5 —— 该节曾说这条红「需要用户确认要不要实现」，已改写为指向实现报告。

## 8. 遗留给他人的、本会话未处置的

均已在实现报告 §4 记录，此处只列指针：

- `test_authoritative_example_config_parses` 在权威配置文件缺席时**静默 skip**（skip 的静默性待用户裁决）；该文件现已进入版本控制，所以当前不 skip，但那是触发条件变了而非问题解决了。
- 客户端发两个 `anthropic-beta` 头时第一个会在 `forwarded_client_headers` 的 dict 推导里被丢掉（先于本切片）。
- `upstream_request_retry.strategies.streamReplay` 是 HEAD 上那条红的成因，属 retry 主题且 `pipeline/retry.py` 正被同伴改动，本会话未碰。
- legacy `config/settings.py` 的 `beta_strip_headers` 仍是零消费者的旧配置面，未动。

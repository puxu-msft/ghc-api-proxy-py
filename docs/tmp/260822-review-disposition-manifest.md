# 评审：job a444a483 收尾处置清单（`DISPOSITION.md`）

**评审者**：独立评审 subagent（`agent-a41f494856b72f36e`，dispatch 时刻 2026-08-22T15:59:36Z）
**被审对象**：`/home/xp/.claude/jobs/a444a483/tmp/DISPOSITION.md`（mtime 2026-08-22 15:58，8393 B）
**结论**：**needs-fix**。无 blocker（处置是零删除，没有不可逆动作，也没有证据被销毁）；4 条 major，7 条 minor，3 条 nit。
**三条停止判据**：① 不成立 ② 不成立 ③ 成立。详见 §5。

---

## 1. 事件源的身份与覆盖范围

| 项 | 事实 |
|---|---|
| 主 transcript | `/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/a444a483-9a82-42ff-99ed-b67d66e273b9.jsonl`，3236731 B |
| 行数 / 解析 | 2066 行，**0 行不可解析** |
| 事件时间跨度 | `2026-08-22T11:50:24.986Z` → `2026-08-22T16:00:09.713Z`（我读取时刻为 16:00 UTC，机器时区 = UTC） |
| 记录类型 | `attachment` 785、`assistant` 435、`user` 242、`last-prompt` 80、`agent-setting`/`mode`/`permission-mode`/`atis-latch`/`ai-title`/`agent-name` 各 79、`queue-operation` 16、`file-history-delta` 16、`system` 14、`file-history-snapshot` 4 |
| 子代理转录 | `.../a444a483-.../subagents/`，4 份：`agent-ae985683cfd700df2`（gpt-opus，评审实现）、`agent-a43d5e6a98547b27e`（核查文档声称）、`agent-acbd4c2defe96561e`（调查头转发面）、`agent-a41f494856b72f36e`（= 本次评审，我自己） |

**覆盖范围的三处限制，如实写出**：

1. **`my-skills:claude-code-transcripts` 的 typed 解析层对这份 transcript 无适配器。** 该 transcript 的 `version` 是 `2.1.239`（1476 行带此字段，590 行无 `version` 字段），skill 的 `iter_records` 把全部 2060 条判为 `UnknownRecord`（`kind=None`）——这正是它「没有 adapter 就没有 typed interpretation」的设计。**我因此改用原始 JSON 逐行解析**（`json.loads` + `type`/`timestamp`/`message.content[].tool_use` 字段），对本次任务（枚举命令、Edit、Agent 派发、工具结果的 `is_error`）是无损的，但我没有使用 skill 的逻辑消息折叠与 token 聚合，也没有做谱系判定（本次不需要）。
2. **会话仍在进行中。** 我的枚举截止于事件 `16:00:09.713Z`；此后主会话又执行了至少一条 Bash（16:00:20 写 `msg4.txt`）。我用文件系统与 git 补测了 16:00–16:05 的后果（见 major-3），但 16:00:20 之后的 transcript 事件不在我的枚举里。
3. **4 份子代理转录我只读了 meta（`agentType`/`description`/`toolUseId`/`spawnDepth`）**，没有逐条枚举子代理内部的命令。理由：清单 §B 只从「本会话可枚举的事件」取候选，子代理的产物有独立载体（`.dev/docs/tmp/260822-header-forwarding-surface.md`、`260822-verify-beta-flag-strip-docs.md`、`260822-review-beta-flag-strip.md`），我逐一验证了这些文件存在。**这是一个已知的覆盖缺口**：若子代理内部产生了未写进其报告的候选，我看不见。

---

## 2. 我做了什么独立枚举（方法）

先枚举、后对账，**没有拿着清单逐条点头**。

**（a）执行过的命令与其失败**：从 435 条 assistant 记录里抽出全部 `tool_use`，得 `Bash` 160、`Edit` 52、`Agent` 5、`TaskUpdate` 5、`Write` 4、`TaskCreate` 4、`Read` 3、`Skill` 1。把 161 条 Bash（含 16:00:20 那条）按时序编号打印命令全文，并用 `tool_use_id` 反查每条的 `tool_result.is_error`，得 22 条失败调用（编号 17、33、38、39、50、56、69、72、75、83、85、94、106、107、111、120、127、132、133、134、144、157）。对其中我无法从命令文本直接解释的 8 条（58、106、107、111、120、133、134、157），打印了完整输出。

**（b）放弃的路线 / （c）被证伪的归因**：从 52 条 `Edit` 的 `old_string`/`new_string` 差分重建实现的形态演化（`model: str` → `models: Sequence` 并集 → `compile_beta_flag_denials` 正则；单一 allowlist → 两级 floor/blacklist/whitelist），并从失败命令的输出里读归因翻转。

**（d）变异与探针**：对 161 条 Bash 全文正则搜 `MUTATION-PROBE|update-ref|hash-object`，得 10 条；**再对 52 条 Edit 搜同一标记**——第一轮变异是用 `Edit` 而非 Bash 打进去的（Edit #15/#16，12:55:00/12:55:14），只搜 Bash 会漏掉它。

**（e）提交**：从 Bash 命令里取 `git commit` / `update-ref` 调用点与 `cat > .../*msg*.txt` 的时刻，再到两个仓库（主仓与 `.dev`）用 `git log -1 --format=%B` 取回消息实体，与 job tmp 里的消息文件逐字节 `diff`。

**文件层核对**：`find "$ROOT" \( -type f -o -type l \) -printf` 与 `fd -H -I --base-directory` 交叉，两者均为 **22**（含 `DISPOSITION.md` 本身），符号链接 0；评审末尾复测为 **24**（见 major-3）。

---

## 3. A 节（文件清单）逐行核实

### 3.1 已验证成立的行

| # | 文件 | 我跑的验证 | 结果 |
|---|---|---|---|
| 1 | `commitmsg.txt` | `diff <(git log -1 --format=%B a2169de) commitmsg.txt` | **等价**（仅差 `%B` 附加的一个尾随空行） |
| 2 | `msg2.txt` | 同上 vs `80068eb` | **等价**（同一尾随空行差） |
| 3 | `msg3.txt` | 同上 vs `959e8d1` | **等价**（同一尾随空行差） |
| 4 | `devmsg.txt` | `.dev` 仓 `0ca6da8` | 提交存在，消息一致 |
| 5 | `devmsg2.txt` | `.dev` 仓 `41e98ef` | 提交存在，消息一致 |
| 6 | `devmsg3.txt` | `.dev` 仓 `2ab949a` | 提交存在，消息一致 |
| 8 | `header_policy.orig.py` | `diff <(git show 959e8d1:src/app/anthropic/header_policy/__init__.py) -` | **逐字节相同** |
| 9 | `private.index` | 复制到 `/tmp` 后 `GIT_INDEX_FILE=… git ls-files --stage`，与 `git ls-tree -r 80068eb` 的 (blob, path) 集合比对 | **520 条目对 520 条目，差集为 0 行** |
| 10 | `schema_head.py` | `diff <(git show 1c91870:src/app/config/schema.py) -` | **逐字节相同** |
| 11 | `schema_mine.py` | `diff <(git show 80068eb:src/app/config/schema.py) -` | **逐字节相同** |

第 9 行我特意用了副本 + 只读命令（`ls-files --stage`），没有跑 `write-tree`，避免向共享对象库写入。

### 3.2 第 7 行：归因写错（major-4）

清单原文：

> 内容 = `git show 1c91870:src/app/server/handler.py` 之后我的编辑，已在 `80068eb` 里

我把 `handler.orig.py` 对六个候选版本逐一 `diff`，得 diff 行数：

| 版本 | diff 行数 |
|---|---|
| `1c91870` | 40 |
| `ec8b2a5`（报告自述的基线） | 14 |
| **`a2169de`** | **0** |
| `80068eb` | 60 |
| `959e8d1` / 当前 HEAD | 72 |
| 当前工作树 | 80 |

**`handler.orig.py` 逐字节等于 `a2169de:src/app/server/handler.py`。** 清单给的两个锚点都不对：

- `1c91870` 的提交时刻是 14:28，而这个备份是 13:18 创建的（Bash #69 里 `cp src/app/server/handler.py "$CLAUDE_JOB_DIR/tmp/handler.orig.py"`）。**基线不可能是一个当时还不存在的提交**，这是时间上就能判否的。
- 「已在 `80068eb` 里」也不成立——`80068eb` 的同名文件与它差 60 行。正确的、可一条命令验证的接收者是 `git show a2169de:src/app/server/handler.py`。

这不是零删除处置下的资产风险（文件没被删），但它是**记忆 `verify-commit-attribution-before-writing-it-down` 的原样复发**：归因写错比事实写错更难被发现，而这一行的整个价值就在于「将来谁想找回这份内容，照它给的命令去找」。

### 3.3 第 12–21 行：接收者指向不存在的文档或不含该结论的章节（major-1、major-2）

我打开了被引用的报告 `.dev/docs/hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`（27606 B，mtime 15:56:19），列出全部标题，并对每个被引数字做了仓库级搜索。

**先说事实：这些门输出本身是什么。**

| 文件 | 实际内容（我读的） |
|---|---|
| `ruff.txt` / `ruff2.txt` / `close-ruff.txt` | `All checks passed!` |
| `pyright.txt` / `pyright2.txt` / `close-pyright.txt` | `21 errors, 0 warnings`；按文件拆分 = `src/app/upstream/stream_cap.py` 4 条 + `tests/unit/upstream/test_stream_cap.py` 19 条。**清单说的「21 错全在同伴 stream_cap 区域」为真** |
| `pytest.txt` | `1 failed, 1738 passed, 2 skipped`，coverage 91.13% |
| `pytest2.txt` | `1757 passed, 2 skipped`，coverage 91.16% |
| `pytest3.txt` | `5 failed, 1768 passed, 2 skipped`，coverage 91.15%；5 条全是 `tests/unit/test_cli.py` 的 pidfile / `StandaloneOptions` 用例。**清单说的「归同伴 pidfile 重构」为真** |
| `close-pytest.txt` | **`1787 passed, 2 skipped`，0 failed**，coverage 89.33% |

**再说接收者。** 报告里与门有关的只有一句，在 §3.4：

> **门的结果（干净 checkout of `80068eb`）**：`ruff check src tests` 全过；`pytest tests` **1771 passed / 2 skipped / 1 failed**。

那个 `1771` 来自 15:03 在 `verify-head2` 一次性 worktree 里跑的 `uv run pytest tests`（Bash #133），**与 job tmp 里这四份 pytest 输出中的任何一份都不是同一次运行**。仓库级搜索：

- `rg -e '1738' -e '1757' -e '1768' -e '1771' -e '1787' -e '91\.1' -e '89\.3'` 打在该报告上，**只命中第 221 行那一处 `1771`**；
- `rg -e '1738 passed' -e '1757 passed' -e '1768 passed'` 打在整个 `.dev/docs/`，**无命中**；
- `rg -e '1787' -e '89\.33'` 打在整个 `.dev/docs/`，命中的全是别的主题里的时间戳与请求 id，无一条是本次覆盖率；
- `rg -e 'pyright' -e 'stream_cap'` 打在该报告上，**无命中**；
- `rg -e 'pidfile'` 打在该报告上，**无命中**。

于是：

| 行 | 清单声称的接收者 | 核实结果 |
|---|---|---|
| 12、13 | 「结论记于报告 §3.3」 | §3.3（「变异验证」）只有变异表，**不含任何 ruff 结论**。ruff 全过的结论在 §3.4，且限定于 `80068eb` 的干净 checkout。**指错章节** |
| 14 | 「结论记于终态报告」 | **没有终态报告这份文档** |
| 15、16 | 「结论（21 错全在同伴 `stream_cap` 区域）记于报告与终态报告」 | 报告里 `pyright`、`stream_cap` **都不出现**；终态报告不存在。**两个接收者皆假** |
| 17 | 「同上」 | 同上 |
| 18 | 「结论（1738 passed / 91.13%）记于报告 §3.3」 | §3.3 无此数字，全仓无此数字。**假** |
| 19 | 「结论（1757 passed / 91.16%）记于报告」 | 全仓无此数字。**假** |
| 20 | 「结论（1768 passed，5 failed 归同伴 pidfile 重构）记于报告」 | 数字与 `pidfile` 二词在报告中皆不出现。**假**（但该归因本身经我核对为真） |
| 21 | 「收尾门输出；结论记于终态报告」 | 终态报告不存在；`1787`/`89.33%` 全仓无载体。**假** |

**为什么这是 major 而不是 nit**：处置结论是「原地弃置」，其唯一依据就是 §A 的接收者列——「这些文件可以不管，因为结论在别处」。**接收者写错比不写更糟**：不写的话，下一个人还会去找；写了一个不存在的接收者，搜索就在这里停了。收尾门（`959e8d1` 之上 1787 passed / 0 failed / 89.33%，pyright 21 错全属同伴）恰恰是本切片「我这边是绿的、红的那部分不归我」的**唯一证据**，而它现在只活在 harness 到期就回收的 job tmp 里。

### 3.4 计数

`find` 与 `fd -H -I` 在我第一次核对时（16:00 前）都给 **22**（21 行清单 + `DISPOSITION.md` 自身），符号链接 0，与 §A 的行数自洽。**评审末尾复测为 24**，见 major-3。

清单页首脚注写「三者计数一致 = **20**（本清单定稿前会重列一次，`close-pytest.txt` 当时尚在写入）」，而 §A 列了 21 行、§C 说 21——读者要自己把 20 / 21 / `ls` 看到的数调和一遍，脚注没有说清「20 是 15:56 那次枚举的数、定稿数是 21」。nit。

---

## 4. B 节双向对账

### 4.1 方向一：清单列了、事件源里找不到的（可能是夸大）

**没有。零条。**

我逐行回溯了 §B 的 5 类共 16 行，每一行都在 transcript 里定位到了具体事件：

| 类 | 行 | 事件源定位 |
|---|---|---|
| 1 | 并集键匹配被推翻 | Edit #23（13:15:51，`model: str` → `models: Sequence`）→ Edit #34（14:46:27，替换为 `compile_beta_flag_denials`） |
| 1 | canonical 折叠 → 正则 | Edit #3（12:51:59 引入 `from app.pipeline.model_resolution import canonical`）→ Edit #35/#36（14:46:31 引入 `import re`） |
| 1 | 保留 `strip_attribution_header` 被推翻 | Bash #115（14:59:58）改写报告 §2.1「保留」→「已删除（裁决 2）」 |
| 1 | 直连黑名单保持空 | 代码里 `DIRECT_PATH_BLACKLIST` 上方 8 行注释确实写着「Empty, and that is the finding rather than an omission」——**载体存在且写的正是这个理由** |
| 2 | `beta_strip_headers` 从未出现（证否） | 报告第 50 行给出 `git log --all -S` 命中 `53fec22` 的复核；记忆 `git-log-is-blind-to-a-never-committed-file.md` 存在（1785 B，13:24 创建） |
| 2 | `AppSettings` 走 `--fd` 路径（证否） | Bash #99（14:47:57）查 `--fd` 实际链路；`loader.py` 的 Edit 存在 |
| 2 | `test_a_turn_that_ran_out_of_room` 归因（证否） | Bash #56（12:58:37）查 HEAD 与同伴 diff、#57 单跑、#58 整文件重跑 |
| 2 | 干净 checkout 的 config parse 红（证否） | Bash #133（15:03:06，`verify-head2`）与 #134（15:05:21，`verify-parent` = `1c91870` 同样红） |
| 2 | Anthropic 腿代理凭据必然胜出（证否） | 子代理 `acbd4c2` 的报告 `.dev/docs/tmp/260822-header-forwarding-surface.md`（30311 B，14:53）**存在**；`80068eb` 的提交消息也写了这一条 |
| 3 | `rg -rn "strip"` | Bash #4（12:47:45） |
| 3 | `rg '^[+-][^+-]'` 吃掉 Markdown 列表项 | Bash #151（15:55:41）、#160（16:00:09） |
| 3 | `"strip_attribution_header" not in out` 命中自己的注释 | Bash #120–#123（15:01:03–15:01:31，#120 的输出正是 `AssertionError: my deletion did not apply`） |
| 3 | 替换断言未命中却 `2 passed` | Bash #70（13:18:29，缩进 12 空格的 `old` 没打中）→ #72（13:18:56，改成 8 空格并加 `assert ... f"count={...}"`） |
| 3 | 私有索引后 12 个文件变 `MM` | Bash #124（15:01:39）建索引、#131（15:02:52）修复；记忆 `git-commit-takes-the-whole-index.md` 第 164 行确有小节「### 2026-08-22 第三次击发」，正文写的就是 12 个文件与主索引停在旧 HEAD |
| 5 | 变异 `denied_by_model=` → `{}` | **Edit #15（12:55:00）/ #16（12:55:14）**——注意这一轮是 `Edit` 打的，不在 Bash 里 |
| 5 | 变异 `models=` → 单 `resolved_model` | Bash #69（13:18:08，先 `cp` 备份再 mutate）/ #70 恢复 |
| 5 | 变异 `configured` 取客户端拼写 | Bash #72（13:18:56）/ #73（13:19:08）恢复 |
| 5 | 变异 `REQUEST_FLOOR` 去 `.lower()` | Bash #144（15:46:26，先 `cp header_policy.orig.py`）/ #145（15:46:40）恢复 |
| 5 | 正样本对照 `rg -c "message-format-reshape"` | Bash #98（14:47:49）末尾，紧跟在「残留应为空」之后 |
| 6 | 头部剥离探针 | Bash #143（15:46:01，`PYTHONPATH=src uv run python - <<PY`） |
| 6 | 子代理 MockTransport 头合并测量 | 子代理 `acbd4c2`（14:45:16 派出），报告文件存在 |

清单说「四轮变异全部恢复，`rg MUTATION-PROBE src tests` 空」——我复测 `rg -c 'MUTATION-PROBE' src tests` 退出码 1（无匹配），**成立**。

### 4.2 方向二：事件源里找到、清单没列的（遗漏）

**三条实质遗漏 + 两条边角。**

**遗漏 1（major-3）：清单定稿之后又产生了证据文件与提交，清单未涵盖。**

我在评审末尾复测 job tmp，得 **24 个文件**：

```
msg4.txt      215 B   16:00
devmsg4.txt   298 B   16:00
```

两者都是 16:00 之后写的（transcript Bash #161 在 16:00:20 写 `msg4.txt`），且**都已落成提交**：主仓 `81c36d2 docs: drop a note about a typo the config author has since fixed`（改 `tests/unit/pipeline/test_client_request_headers.py`，-2 行），`.dev` 仓 `cb472f7 docs: record the typo as fixed rather than as raised`。§A 是 21 行，§C 说「21 个文件……全部」，**现在实际是 23 个证据文件**（24 减去 `DISPOSITION.md` 自身）。

这不是作者的疏忽那么简单：清单在页首承诺「本清单定稿前会重列一次」，而定稿后会话继续产出。**处置若要生效，清单必须在弃置动作发生的那一刻重列**，否则「弃置了什么」这件事本身没有记录。同一形状：主仓 HEAD 此刻已是 `1459320`（同伴的提交），不再是清单隐含的 `959e8d1`。

**遗漏 2（minor）：三棵一次性 git worktree 被建在 job tmp 里又被强制删除，清单不见其踪。**

- `verify-head`（13:24，Bash #85–#87）
- `verify-head2`、`verify-parent`（15:03–15:05，Bash #132–#137）

三次都用 `GIT_DISCIPLINE_OK=1 git worktree remove --force` 清理。**问题不在于清理得对不对（我复测 `git worktree list` 与 `.git/worktrees/` 目录，本 job 的三棵均已消失，无残留），而在于清单的扫描方法结构性地看不见它们**：`find` 跑在 15:56，那时它们早已被删；而 §B 的六类里也没有「本会话在共享仓库里创建又销毁的状态」这一项。它们还**动过共享仓库的状态**（`.git/worktrees/` 条目、`uv` 在每棵树里装了 78 个包），这超出了「job tmp 目录内」的处置边界。清单应当记一句「本会话另在共享仓建过 3 棵临时 worktree，已核实无残留」——不记的话，读者从这份清单读不出「除了 tmp 目录，别处还动过什么」。

**遗漏 3（minor）：门曾在过滤后的文件子集上运行，未被记录。**

14:57:48（Bash #111）全树 `ruff check src tests` 红在 `tests/int/test_standalone_lifecycle.py:508` 的 `F821 Undefined name standalone_pidfile_path`——**同伴写到一半的状态**。会话随即在 #113 改成对 `git status` 过滤后的文件子集跑 ruff。这是一次**门的作用域收窄**，其结论（「全树 ruff 红不归我，我只能验证自己那批」）没有任何持久载体。它与 §A 第 20 行「5 failed 归同伴 pidfile 重构」是同一家族，值得并到 §B 类 2 或类 3 里。

**边角 1（nit）**：14:47:03（Bash #95）跑过 `uv run ruff check --fix --select I001`，即让工具自动改了源文件的 import 顺序。项目规则禁的是 `ruff format`，`--fix` 不在禁令内，所以不是违规；但「本会话有一次源码改动不是我手写的」这件事没被记下来。

**边角 2（nit）**：14:56:00（Bash #106）撞到 `RUF003`（注释里的全角括号 `（`），迫使把注释里的「（暂无）」改写成半角。属于 lint 约束的一次发现，价值低，可不记。

---

## 5. 三条停止判据的裁定

判据来自派单（零删除的原地弃置，停止判据不是「证明差集为空」）。

### 判据 ①：每一个被发现的候选，只要能指导未来行动，都有可定位的持久载体 —— **不成立**

- §B 的 16 行候选，载体我逐一验证**全部存在**（报告章节、代码注释、三份记忆文件、两份子代理报告），这一半是干净的。
- 但 §A 的门输出行不成立：**收尾门的三项结论目前无任何持久载体**——`959e8d1` 之上 `1787 passed / 2 skipped / 0 failed / 89.33%`、`ruff` 全过、`pyright` 21 错全属同伴 `stream_cap`。这三项能指导未来行动（它们是「本切片交付时是绿的、红的那部分不归我」的唯一证据），而它们只存在于 harness 到期即回收的 `close-*.txt` 里。同理 `1738 / 1757 / 1768` 三次中途门。
- 判据①失败的形态还被 §A 末尾那句全称句掩盖了：「**没有任何一行的处置是「持久化」**：每一条的结论都已有仓库载体」。这句话是假的，且它正是让人不再去核对的那句话。

### 判据 ②：清单记录了扫描方法、发现、以及各自的载体 —— **不成立**

- **扫描方法**：记了（`find` + `fd -H -I` + 裸 `fd` 三者交叉、符号链接计数）。我复现得到一致结果。但计数已过期（20 / 21 / 实际 23），且方法只覆盖 job tmp 目录，未声明这一边界（遗漏 2 就落在边界外）。
- **发现**：记了，而且质量高——双向对账方向一为**零条夸大**，这在这类清单里不常见，值得说。
- **载体**：**8 行为假**（§3.3 的表）。「记录了载体」与「记录的载体是真的」是两件事，判据②要的是后者，否则它记录的是一个会让搜索提前停止的假接收者。

### 判据 ③：清单没有声称「差集已被证明为空」 —— **成立**

§B 前言明写「从**本会话可枚举的事件**中取，不做全局审计」，§C 三条也只说「已有仓库载体、拟原地弃置、留标记而非清空」，**没有出现任何「已穷尽」「无遗漏」「差集为空」的断言**。这一条干净成立。

唯一瑕疵是同一句前言里的「每行标 provisional」——**§B 实际上没有任何一行带 provisional 标记**。这是一句自述的纪律没有落实，属 minor；它不构成对空集的声称，所以不推翻判据③。

---

## 6. 分级发现清单

**blocker：无。** 处置是零删除，不含不可逆动作；我没有发现任何证据被销毁、被覆盖或不可重建。所有 4 条 major 都是「记录不实 / 记录缺失」，修法是改清单与补载体，不涉及数据风险。

### major

- **major-1｜§A 第 14/15/16/17/18/19/20/21 行的「接收者/替代证据」为假**：其中 14/17/21 指向一份**根本不存在的「终态报告」**，15/16 声称报告记了 pyright 结论而报告中 `pyright`、`stream_cap` 二词均不出现，18/19/20 引用的三组测试数字（1738 / 1757 / 1768）与 `pidfile` 归因在整个 `.dev/docs/` 中无一处出现。
- **major-2｜收尾门的结论没有持久载体，判据①因此不成立**：`959e8d1` 之上 `1787 passed / 0 failed / 89.33%`、ruff 全过、pyright 21 错全属同伴 `stream_cap` —— 这三项现在只活在 job tmp 的 `close-*.txt` 里，弃置即失。
- **major-3｜清单已过期**：定稿后又产生 `msg4.txt`、`devmsg4.txt` 两个证据文件与两个提交（主仓 `81c36d2`、`.dev` 仓 `cb472f7`），§A 未列，§C 的「21 个文件」现为 23；主仓 HEAD 也已被同伴推到 `1459320`。
- **major-4｜§A 第 7 行的 git 归因写错**：`handler.orig.py` 逐字节等于 `a2169de:src/app/server/handler.py`（diff 0 行），既不是「`1c91870` 之后我的编辑」（diff 40 行，且 `1c91870` 的 14:28 晚于该备份的 13:18，时间上就不可能），也不「已在 `80068eb` 里」（diff 60 行）。

### minor

- **minor-1｜§A 末尾的全称句「每一条的结论都已有仓库载体」为假**，且它恰好是让读者停止核对的那一句。
- **minor-2｜三棵一次性 worktree（`verify-head`、`verify-head2`、`verify-parent`）建于共享仓、用 `GIT_DISCIPLINE_OK=1 --force` 删除，清单完全未提**；它们动的是 job tmp 之外的共享仓状态，而 `find` 式扫描结构性地看不见（我已复测：无残留）。
- **minor-3｜§B 前言自称「每行标 provisional」，实际无一行标注**。
- **minor-4｜门曾在过滤后的文件子集上运行（14:57，因同伴的 `F821` 破坏了全树 ruff），其结论无载体**，应并入 §B 类 2 或类 3。
- **minor-5｜§A 第 12/13 行引 §3.3，而 ruff 结论实际在 §3.4**，且 §3.4 那句限定于 `80068eb` 的干净 checkout，与 `ruff.txt`/`ruff2.txt` 不是同一次运行。
- **minor-6｜第 7 行的「`handler.py` 相对 HEAD 干净」是易变声称，未锚定 HEAD 与时刻**；我复测时它已是 ` M`（同伴的 `LedgerBudget(draining=...)` 改动），读者无从判断这句是过期还是错。
- **minor-7｜§B 类 2/3 的载体多为 `~/.claude/projects/.../memory/*.md`，不在任何仓库内**，与 §A 「仓库载体」的措辞不一致。三份记忆文件我都验证存在（`git-log-is-blind-to-a-never-committed-file.md` 1785 B、`the-pattern-is-not-the-predicate.md` 2881 B、`git-commit-takes-the-whole-index.md` 20433 B 且含 2026-08-22 第三次击发小节），持久性没问题，只是「仓库」二字说得过宽。

### nit

- **nit-1｜「`rg -rn "strip"` 是会话第二条命令」不准**：它是第 4 条 Bash 调用（12:47:45），第 2 条是另一条 rg。
- **nit-2｜页首脚注的「三者计数一致 = 20」与 §A 的 21 行、§C 的 21 之间需要读者自己调和**，脚注没写清 20 是 15:56 那次枚举的数。
- **nit-3｜`DISPOSITION.md` 自身未列入 §A**，于是 §C 的计数与 `ls` 看到的数天然差一，可接受但值得一句说明。

---

## 7. 建议的最小修补（供主会话裁决，我未执行任何修改）

按性价比排序，前两条是让判据①②成立的必要条件：

1. **把收尾门的三项结论写进报告**（一个 §3.5 或在 §3.4 后追加即可）：`959e8d1` 上 `ruff` 全过、`pytest` 1787 passed / 2 skipped / 0 failed / 89.33%、`pyright` 21 错全在 `src/app/upstream/stream_cap.py`(4) + `tests/unit/upstream/test_stream_cap.py`(19)，并注明这 21 条不属本切片。**做完这一条，major-1 与 major-2 一起消**。
2. **重列文件清单并补上 `msg4.txt` / `devmsg4.txt` 两行**（接收者分别是主仓 `81c36d2` 与 `.dev` 仓 `cb472f7`），把 §C 的 21 改成实际数，并把「定稿前会重列一次」兑现在弃置动作发生的那一刻。
3. **改正第 7 行**：接收者写成 `git show a2169de:src/app/server/handler.py`（我已验证 diff 为 0 行），删掉 `1c91870` 与 `80068eb` 这两个不成立的锚点。
4. **§B 补一行「共享仓状态」**：3 棵一次性 worktree 已建已删、`git worktree list` 与 `.git/worktrees/` 已复测无残留。
5. **删掉或改写 §A 末尾的全称句**，改成「§A 的 1–11 行有可验证的仓库载体；12–21 行的门输出结论见报告 §3.x」。
6. 顺手把 §B 前言那句「每行标 provisional」落实，或删掉这句自述。

我**没有**建议给这份清单加任何门、检查脚本或验收装置——它是一次性的收尾记录，加装置的成本高于收益。

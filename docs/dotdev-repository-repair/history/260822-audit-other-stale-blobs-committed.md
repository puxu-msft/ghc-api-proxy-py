# 陈旧索引内容是否还落进了别的提交 —— 独立核查

- 核查者：verifier subagent（**只读**：未 commit、未 stage、未改动工作树；唯一写入是本报告文件）
- 主快照时刻：**2026-08-22T09:41:26+00:00**；核查期间同伴又落了一个提交，追加复核时刻 **2026-08-22T09:51:03+00:00**
- 工作目录：`/home/xp/src/ghc-api-proxy-py`（所有命令均 `cd` 到该路径或用 `git -C`）

## 0. 固定 SHA

| 名字 | SHA | 说明 |
|---|---|---|
| HEAD-A（主快照，09:41） | `51196e24e80c19907545c5b23ab81aedb4b7ceba` | `feat: hold the whole client request to its deadline…` |
| HEAD-B（复核，09:51） | `8f654b44ad81ca200cff3d8d2b44808a50e336b7` | `feat: wire the replay, and give one client request one retry budget`（同伴 09:45:13 提交） |
| 受损索引快照 | `91f67a186292b283f16481196f854749eb6c0842` | `backup: index snapshot before repairing the stale-index damage` |
| 受损索引 parent | `2bcf03b03d667a782a285b8e3a3ab459d4f11118` | ref 已删，对象可达 |
| 当时正确 HEAD | `8703cad8b700d3714321b1433061e28b73c47df5` | `feat: implement the proxy priority…` |
| 已知阳性样本 | `1b0cdd2c769a98d023c5d31de5aaf92b57c268f5` | 提交了陈旧 `src/app/cli.py`（blob `9ac78d4d`） |
| 修复提交 | `8469cfafb8c02e3f25cc53270d08874cd6fdad76` | `fix: hand build_http_client the proxy tier again…` |

结构事实（`git merge-base --is-ancestor` 退出码 0；`git rev-list --count`；`git rev-list --merges` = 0）：

- `2bcf03b` 与 `8703cad` 都是 HEAD-A 的祖先；`8703cad^ == 2bcf03b`。
- `2bcf03b..HEAD-A` 共 **22** 个提交（任务描述说「几十个」，实际 22）；`8703cad..HEAD-A` 共 **21** 个。
- 从 HEAD 可达的历史里**没有 merge 提交**，是线性历史 —— 后面所有「祖先版本」推理都建立在这个事实上。

## 1. 对背景事实的一处修正（先说，因为它改变了判据的选取）

任务背景把 `91f67a1` 描述为「受损索引的完整快照」，隐含它就是产生 `1b0cdd2` 缺陷的那份索引。**实测不成立，`91f67a1` 早于 `1b0cdd2`，也早于 `8703cad`。**

```
git cat-file -p 91f67a1        # committer 1787343193 +0000 = 2026-08-21 20:13:13
stat -c %y .git/objects/91/f67a1...   # 2026-08-21 20:13:13.575548386 +0000
```

三个 loose object 的落盘 mtime 与它们各自的 committer date 完全一致（对象从未被 repack，是两路独立信号）：

| 提交 | committer date | loose object mtime |
|---|---|---|
| `91f67a1`（索引快照） | 2026-08-21 20:13:13 | 2026-08-21 20:13:13.575 |
| `8703cad`（正确 HEAD） | 2026-08-21 21:22:19 | 2026-08-21 21:22:19.285 |
| `1b0cdd2`（缺陷提交） | 2026-08-21 23:05:32 | 2026-08-21 23:05:32.122 |

而 `1b0cdd2` 提交的 `src/app/cli.py`（`9ac78d4d`）来自**另一个时点**：

```
git diff 92725a4d:src/app/cli.py 1b0cdd2:src/app/cli.py   # 只差一行（文档路径改写）
git log -1 92725a4d   # 2026-08-21 18:29:41  feat: confirm before gen-config replaces an existing file
git rev-list --count 92725a4d..8703cad   # 4
```

而 `91f67a1` 里的 `cli.py`（`b09429ba`）是 `ff0ac3cb`（2026-08-21 17:43，落后 `8703cad` 14 个提交）的版本。

**结论（可据以行动）**：共享索引至少在 **两个不同时点**处于陈旧状态，`91f67a1` 只冻结了其中一个（20:13 那次，且那次的 `cli.py` 比 `1b0cdd2` 实际提交的还要旧）。因此——

> `git diff 8703cad 91f67a1` 给出的那 51 条路径，**不是**「有风险路径」的权威清单，只是其中一个时点的切片。

这直接决定了本次核查的方法：**不以 51 条路径为扫描域，而是对 `2bcf03b..HEAD` 全部提交 × 全部改动路径做扫描**（66 对，见第 3 节）。51 条路径只作为一条独立的交叉验证线索（第 4 节）。

## 2. 三个探测器，以及它们各自的分辨力（先做正样本对照）

### 探测器 1 —— blob 等值回退（任务建议的判据）

对每个 `(提交 C, 路径 P)`：`C:P` 是否等于 `P` 在**任何**其它提交处的 blob（深度 = `git log --format=%H --all -- P`，即全部 ref、全部深度）。

**正样本对照：不通过。** 已知阳性样本抓不到：

```
for C in $(git log --format=%H --all -- src/app/cli.py); do
  b=$(git rev-parse "$C:src/app/cli.py"); [ "$b" = 9ac78d4dcfa2645214270b6bf6f6198a124c41cc ] && echo "MATCH at $C"; done
# → MATCH 只出现在 1b0cdd2 自己（扫描深度 62 个提交）
```

这正是任务提醒的坑：`1b0cdd2` 是「回退 + 一处新改写」的混合体，blob 不等于任何历史版本。

**机制对照（证明循环本身能工作）**：把比较目标换成 parent blob 后重跑同一循环，66 对中有 parent 的 64 对**全部命中**（另 2 对是新增文件，无 parent）。所以「探测器 1 空结果」= 遍历与比较无误但确实没有纯回退，**而不是**循环写坏了。

### 探测器 2 —— 内容向某个更早版本靠拢（我加的）

对每个 `(C, P)`：在 `git rev-list C^ -- P`（从 C 的父提交可达、全深度）里找出与 `C:P` 行距最小的祖先版本 V，比较 `d(C:P, V)` 与 `d(C^:P, V)`。陈旧写入的特征是**新内容离某个旧版本极近**（绝对距离小），并且比父提交更近。脚本：`/tmp/aud_dist.sh`。

**正样本对照：通过。**

```
  README.md      | step=54 | nearest old ver=d3cdb420 (2026-04-02) d(new,V)=41 d(parent,V)=59 | MOVED_TOWARD_OLD(drop 18)
  src/app/cli.py | step=14 | nearest old ver=92725a4d (2026-08-21) d(new,V)=2  d(parent,V)=12 | MOVED_TOWARD_OLD(drop 10)
```

`cli.py` 的 `d(new,V)=2` 是决定性的；`README.md` 那条是同一提交里的合法重写（缩写文档），`d=41` 并不近 —— 说明**判读要看绝对距离，不能只看 drop**。

### 探测器 3 —— 早先提交的改动是否消失（任务要求的交叉验证角度）

对 `(提交 A, 路径 P, 目标树 T)`：把 `git diff A^ A -- P` 反向应用到 `T:P`（在 `/tmp/aud_scratch` 里做，`git apply -R --check --unsafe-paths`，全程不碰仓库工作树）。能反向应用 = A 的改动在 T 里仍然完整存在。

**正样本对照：通过，且正反两向都对。**

```
8703cad 对 src/app/cli.py 的改动：
  against tree 8703cad -> SURVIVES            (预期存活)
  against tree 1b0cdd2 -> LOST-OR-SUPERSEDED  (预期丢失 —— 就是这次缺陷)
  against tree HEAD-A  -> SURVIVES            (预期已由 8469cfa 修回)
```

## 3. 任务一的扫描结果：`2bcf03b..HEAD` 全量

扫描域：`git rev-list 8703cad^..HEAD-A`（= `2bcf03b..HEAD-A`，22 个提交）× 各自改动路径 = **72 对**（含 `8703cad` 自身的 6 对；不含它时为 66 对）。

### 探测器 1（全 `--all` 深度）

```
=== Detector 1 (full --all depth) ===
(detector-1 scan finished)      ← 零命中
```

每条路径实际扫描深度记录在循环内（例：`src/app/cli.py` 深度 62、`src/app/server/handler.py` 36、`src/app/server/pipeline_app.py` 55、`tests/int/test_pipeline_app.py` 16）。注意 `git rev-list HEAD -- src/app/cli.py` 只有 39，而 `--all` 是 62 —— 有 23 个改过 `cli.py` 的提交在 archive/worktree 分支上，从 HEAD 不可达。**扫描用的是 62 那一版。**

结论权重：因为正样本对照失败，**这个空结果只能排除「纯回退」，不能排除混合式陈旧写入**，单独看它没有分辨力。

### 探测器 2（全 72 对）

72 对里被标记 `MOVED_TOWARD_OLD` 的只有 4 条，逐条判读：

| 提交 | 路径 | d(new,V) | 判读 |
|---|---|---|---|
| `1b0cdd2` | `src/app/cli.py` | **2** | **已知缺陷**（唯一真阳性） |
| `1b0cdd2` | `README.md` | 41 | 假阳性。读 `git diff 1b0cdd2^ 1b0cdd2 -- README.md`：是一次刻意的精简重写（把不再支持的端点划掉、换成 `uvx` 用法），最近旧版本是 2026-04-02 的初始提交，缩短文件自然拉近行距 |
| `8469cfa` | `src/app/cli.py` | **2** | **就是修复本身**，刻意回到 `8703cad` 的内容（见第 5 节），符合预期 |
| `767d0f23` | `src/app/config/bundled-config.yaml` | 6 | 假阳性。`git diff 8703cad HEAD -- <file>` 是**纯删除**整个 `models_support_web_search` 块；删除让文件在行距上靠近旧版本。该正则并未丢失，已搬到 `src/app/config/schema.py:126` 的 `default_factory=lambda: [r"gpt-[5-9]\.\d+.*"]`，`git grep 'gpt-\[5-9\]' HEAD` 可见，配套的三行论证也搬到了 schema.py 的注释里 |

其余 68 对的最近旧版本距离都在 9 行以上，且多数比父提交更远（内容在往前走）。

### 探测器 3（全 72 对，目标树 = HEAD-A）

20 对报 `LOST-OR-SUPERSEDED`。为了让它有判别力，我又跑了一次**归因扫描**：对每条路径按时序找出「第一个让早先改动不再存活的后续提交」，得到 21 组 `A → 被 B 顶掉`。逐组判读：

| 组 | 判读 |
|---|---|
| `8703cad → 1b0cdd2` on `src/app/cli.py` | **已知缺陷** |
| `1b0cdd2 → 8469cfa` on `src/app/cli.py` | 修复提交，预期 |
| `de459e32 → ee8646bf → caf50157 → da906831` on `.claude/skills/project-review-principles/SKILL.md` | 同一份文档连续四轮迭代改写，提交信息自述即为修订（「按两份评审修正」「补上判据的第二个必要条件」「修正 caf5015 的三处错」） |
| `40d9c76a → 9aa31f95` on `config/schema.py`、`pipeline/retry.py`、`test_config_schema.py`、`test_retry_strategies.py`、`test_stream_ending.py`（5 条） | `9aa31f95` = `refactor: a torn body is a network failure, not a kind of its own`，刻意撤掉一个重试类别，探测器 2 对这 5 条全部判 `ok`（新内容远离旧版本） |
| `0b57645b → a2c9b778 → 96eb2fa4 → 9aa31f95 → 51196e24` on `pipeline/delivery/stream.py`；`9c7e9716/0b57645b/96eb2fa4` on `test_stream_delivery.py`（8 条） | delivery 一条主线上的连续演进，每一步 step 都很大（45/12/112/10/13），探测器 2 全判 `ok` |
| `767d0f23 → b64003ea` on `subscribers/__init__.py`、`hosted_web_search.py`、`server/composition.py`、`test_builtin_subscribers.py`（4 条） | `b64003ea` = `fix: scope the web-search model list to the provider that owns it`，同一话题的紧接返工 |

我另外单独看了绝对距离次小的一条 `tests/unit/config/test_config_schema.py @ 9aa31f95`（`d(new,V)=2`）：diff 是**一行断言**从 `strategies.streamReplay.max_retries == 100` 改成 `strategies.network.max_retries == 9`，跟着 schema 重构走，不是回退。

### 任务一结论

**在 `2bcf03b..HEAD-B` 范围内，除了已知的 `1b0cdd2` 的 `src/app/cli.py` 之外，没有第二处陈旧内容落进提交。**

判据交叉：一处真正的陈旧写入应当**同时**被探测器 2（内容离某个旧版本极近）和探测器 3（早先提交的改动消失）命中；全范围内同时命中且不能用「同话题连续返工」解释的，只有 `1b0cdd2 / src/app/cli.py` 一条。

结论权重：**足以据此行动**。理由：三个探测器里有两个（2 和 3）在已知阳性样本上双向对照通过；探测器 1 的机制对照通过（64/64）。已知的盲区写在第 6 节。

## 4. 交叉验证：51 条路径当前状态

虽然第 1 节已说明 51 条不是权威清单，它仍是一条独立线索。

```
比对 8703cad 与 HEAD-B 上这 51 条路径的 blob：
  identical-to-8703cad = 42
  changed-since        = 9
```

- **42 条**在 `8703cad` 之后从未被改动，HEAD blob 与 `8703cad` 逐字节相同 → 不可能带有陈旧内容。
- **9 条**被改过：`src/app/cli.py`、`config/bundled-config.yaml`、`config/schema.py`、`pipeline/subscribers/__init__.py`、`pipeline/subscribers/hosted_web_search.py`、`server/composition.py`、`server/handler.py`、`tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py`、`tests/unit/pipeline/subscribers/test_builtin_subscribers.py`。

对这 9 条量了「HEAD 相对受损索引版本是走近还是走远」：

| 路径 | d(8703cad, 受损版) | d(HEAD, 受损版) | 走向 |
|---|---|---|---|
| `src/app/cli.py` | 19 | 21 | 远离 |
| `src/app/config/bundled-config.yaml` | 8 | 6 | 靠近（已判读为纯删除造成，见第 3 节） |
| `src/app/config/schema.py` | 46 | 78 | 远离 |
| `src/app/pipeline/subscribers/__init__.py` | 5 | 18 | 远离 |
| `src/app/pipeline/subscribers/hosted_web_search.py` | 52 | 96 | 远离 |
| `src/app/server/composition.py` | 172 | 182 | 远离 |
| `src/app/server/handler.py` | 2 | 35 | 远离 |
| `tests/.../test_upstream_error_normalization.py` | 2 | 38 | 远离 |
| `tests/.../test_builtin_subscribers.py` | 63 | 215 | 远离 |

另外，这 9 条路径在范围内每个提交的 `parent blob` 都等于上一个提交的 `new blob`（无跳变），且除 `cli.py` 外没有任何提交的 blob 等于 `91f67a1:P` 或 `8703cad:P`。

## 5. 任务二：核验修复提交 `8469cfa`

### 5.1 只改了 `src/app/cli.py`？—— 是

```
git show --stat 8469cfa
 src/app/cli.py | 12 ++++++------
 1 file changed, 6 insertions(+), 6 deletions(-)
```

### 5.2 结果 == `8703cad:cli.py` + 第 288 行注释路径改写？—— 是，逐字节符合

```
git diff 8703cad:src/app/cli.py 8469cfa:src/app/cli.py
@@ -285,7 +285,7 @@ def start(
-        # in `docs/agents/anthropic-responses-bridge/implementation.md`.
+        # in `.dev/docs/anthropic-responses-bridge/implementation.md`.
```

**整个 diff 只有这一处 hunk**，别无其它。行号核对：`git show 8469cfa:src/app/cli.py | sed -n '286,290p'` 的第三行（即第 288 行）正是改写后的 `.dev/docs/...`。

补充：这一行改写并非 `8469cfa` 新加的，它是 `1b0cdd2` 那次唯一有价值的部分（`git diff 92725a4d:cli.py 1b0cdd2:cli.py` 只有这一行），修复把它保留了下来 —— 也就是说 `8469cfa` 撤销了 `1b0cdd2` 的回退，同时没有连带撤销它的有效改动。这一点是对的。

`git diff 8469cfa:src/app/cli.py HEAD-A:src/app/cli.py` 为空，`8469cfa` 之后无人再动过该文件。

### 5.3 调用点是否一致？—— 是

`git grep -n -E 'build_http_client|serve_inherited|_serve_pipeline|transport_options|proxy_from_cli' HEAD-A -- src tests`，产品代码侧：

| 位置 | 形态 |
|---|---|
| `src/app/server/composition.py:112` | `def transport_options(config, *, proxy_from_cli: bool)` —— 关键字参数、**无默认值** |
| `src/app/server/composition.py:135` | `def build_http_client(config, *, proxy_from_cli: bool)` —— 同上 |
| `src/app/cli.py:141` | `async def serve_inherited(config, fd, *, proxy_from_cli: bool)` |
| `src/app/cli.py:146` | `build_http_client(config, proxy_from_cli=proxy_from_cli)` |
| `src/app/cli.py:162` | `async def _serve_pipeline(config, options, *, proxy_from_cli: bool)` |
| `src/app/cli.py:168` | `build_http_client(config, proxy_from_cli=proxy_from_cli)` |
| `src/app/cli.py:303` | `run(partial(serve_inherited, proxy_config, fd, proxy_from_cli=proxy is not None))` |
| `src/app/cli.py:338` | `run(partial(_serve_pipeline, proxy_config, options, proxy_from_cli=proxy is not None))` |
| **`src/app/debug/models.py:230`** | `build_http_client(config, proxy_from_cli=False)` —— **任务点名的这处在位** |

测试侧 `tests/unit/server/test_http_client_build.py`、`tests/unit/upstream/test_stream_cap.py`、`tests/unit/debug/test_debug_models.py`、`tests/unit/test_cli.py` 的所有调用与桩函数签名都带 `proxy_from_cli`。

用 `rg` 扫过整棵工作树（含未跟踪文件，排除 `.git/` 与 `.dev/`），出现这三个名字的文件只有上表涉及的 7 个，**没有第八个调用点**。

对照缺陷态（证明这套检查确实能看出问题）：在 `1b0cdd2` 上，`composition.py:135` 的签名已经要求 `proxy_from_cli`，而 `cli.py` 的 141/146/162/168/303/338 六处全部不带该参数 —— 正是任务背景描述的 `TypeError`。

### 5.4 有没有误伤同伴暂存在共享索引里的内容？—— 没有

- `8469cfa` 的树与其父树**只差 `src/app/cli.py` 一个文件**（`--stat`），没有把索引里任何别的东西顺带提交进去。
- `git status --porcelain -- src/app/cli.py` 当前**输出为空** —— 该文件在索引和工作树里都与 HEAD 一致，没有被谁的在制品覆盖，也没有覆盖谁的在制品。
- 「被覆盖的旧内容里是否含同伴的新工作」：`8469cfa` 顶掉的 `9ac78d4d` 已证明等于 `92725a4d:cli.py`（4 个提交前）+ 一行文档路径改写，而那一行**被保留了**。所以被丢弃的只有陈旧内容本身。
- 全部 ref 里改动过 `cli.py` 但从 HEAD 不可达的最新提交是 `b83d84ea`（2026-08-21），它只存在于 `refs/heads/archive/260821-proxy-priority` 与 `refs/heads/worktree-proxy-priority`，即 `8703cad` 被 squash 前的评审源，不是被误伤的在制品。

### 任务二结论

**`8469cfa` 完全符合任务描述的四项判据，没有发现问题。**结论权重：**足以据此行动**（四项都由命令输出直接支撑，其中 5.3 还做了缺陷态对照）。

## 6. 已知盲区（不写下来的话，上面的「没有别的」会被读得比它实际支持的更强）

1. **扫描域是 `2bcf03b..HEAD-B` 的 main 线。** `2bcf03b` 之前落进提交的陈旧内容不在本次范围内，其它分支（archive/worktree）上的提交也没扫。
2. **探测器 2 的盲区**：如果某次陈旧写入同时**掺入了足够多的新内容**，结果就不会「离任何旧版本极近」，它可能落进 `ok`。探测器 3 在这种情况下仍会报 `LOST`，但 `LOST` 在正常返工中大量出现（本次 21 组里 19 组是合法返工），所以真正的兜底是我对这 21 组逐组读过提交语义 —— 这一步是人工判读，不是机器判据。
3. **探测器 3 用的是 hunk 级反向应用**：若某个后续提交碰巧改到相邻行，也会报 `LOST`，这会放大噪声（保守方向），不会漏报。
4. **未运行测试或类型检查。** 任务要求只读，`pytest` / `pyright` 会在仓库里写缓存，因此 5.3 的一致性是**静态**核对（签名 + 全部调用点 + 全树 `rg`），不是「跑起来确实不抛 TypeError」的运行时证据。若需要运行时证据，请另行授权。
5. **同伴在持续提交。** 本报告的判断截至 `8f654b44`（09:45:13 提交，09:51:03 复核）。09:41 之后落地的那一个提交我已用探测器 1 与 2 补扫过（4 条路径，深度 5/36/55/16，零命中，全部 `ok`），此后新增的提交不在覆盖内。
6. 主树当前有同伴未提交的在制品（`CLAUDE.md`、`docs/.human-controlled/*`、`src/app/pipeline/request.py`、`src/app/server/handler.py`、`src/app/server/pipeline_app.py` 等）。本次核查只读提交态，**未读也未动**这些在制品；工作树里的陈旧内容（如果有）不在本次结论覆盖范围内。

## 7. 附：本次实际执行的关键命令

```bash
cd /home/xp/src/ghc-api-proxy-py

# 结构
git merge-base --is-ancestor 2bcf03b 51196e24…; git rev-list --count 2bcf03b..51196e24…
git rev-list --merges 51196e24… | wc -l

# 受损索引切片
git diff --name-only 8703cad 91f67a1 > /tmp/aud_51.txt

# 探测器 1（全 --all 深度）+ 机制对照
for C in $(git rev-list --reverse 8703cad..HEAD); do
  for P in $(git diff-tree --no-commit-id --name-only -r "$C"); do
    new=$(git rev-parse "$C:$P")
    for A in $(git log --format=%H --all -- "$P"); do … done
  done
done

# 探测器 2
/tmp/aud_dist.sh <commit> <path>     # 见第 2 节说明

# 探测器 3（在 /tmp/aud_scratch 里做，绝不碰仓库工作树）
git diff "$A^" "$A" -- "$P" \
  | git -C /tmp/aud_scratch apply -R --check --unsafe-paths --directory=/tmp/aud_scratch -

# 时间线取证
git cat-file -p 91f67a1
stat -c %y .git/objects/91/f67a1…

# 任务二
git show --stat 8469cfa
git diff 8703cad:src/app/cli.py 8469cfa:src/app/cli.py
git grep -n -E 'build_http_client|serve_inherited|_serve_pipeline|proxy_from_cli' HEAD -- src tests
rg -e build_http_client -e serve_inherited -e _serve_pipeline . --glob '!.git/**' --glob '!.dev/**' -l
git status --porcelain -- src/app/cli.py
```

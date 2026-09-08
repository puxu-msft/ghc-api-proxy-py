# 收尾对账：遗漏枚举评审（会话 23a78bec）

**角色**：独立的「遗漏枚举」评审者。不核查主会话结论的对错（另有评审做那件事），只做一件事——**先从事件源独立枚举本会话真正发生过什么，再与主会话的清单双向对账**。

**判据（按派发要求）**：本次处置是就地处置、不删任何文件，因此停止条件**不是**「证明差集为空」。停止条件是三条：(1) 每一个**被发现的**、能指导未来行动的线索都有一个可定位的持久载体；(2) 记录写清了扫描方法与边界；(3) **不声称差集已被证明为空**。本报告按此结论。

**只读声明**：本次评审只写本文件。未修改仓库任何其他文件，未执行任何写操作的 git 命令（核对方式见文末「扫描方法与边界」）。

---

## 0. 扫描方法（先说方法，结论才可被复核）

事件源与切片方式：

| 源 | 路径 | 我怎么切的 |
|---|---|---|
| 主 transcript | `/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/23a78bec-3ecd-45d0-b2eb-5b4a5f43ba48.jsonl`（2.4 MB） | 自写 `/tmp/pair.py` 把 `tool_use` 与 `tool_result` 按 `tool_use_id` 配对成 174 条记录，再按时间窗与关键词切片；另用 `jq` 单独抽取全部 assistant text 块与全部 `is_error==true` 的结果 |
| 子智能体转录 | 同目录 `…/23a78bec…/subagents/agent-*.jsonl`（3 个） | `meta.json` 定身份，转录按工具调用与结论切片 |
| job 临时目录 | `/home/xp/.claude/jobs/23a78bec/tmp/` | `ls`；21 个文件 |

**先枚举后对账**：本报告第 1~6 节的全部条目在打开主会话清单（`DISPOSITION.md` 与收尾报告）之前就已从事件源产出；第 7 节才做双向对账。

**这套方法看不见什么**（边界，必须先说）：

- **看得见工具调用与文本，看不见「想过但没写出来」的判断**。任何只存在于模型内部、既没落工具调用也没落文字的取舍，本方法结构上不可见。
- **看得见错误信号，看不见「跑了、有输出、结论仍错且从未被察觉」的那一类**——除非它后来被同一份 transcript 里的另一次动作打脸。第 3 节能列出的都是**已经被打脸过的**；未被打脸的同型错误留在盲区里。这正是为什么停止条件不能是「差集为空」。
- **子智能体的内部工具调用可见，但其上下文里被截断/压缩的部分不可见**。
- 主 transcript 只覆盖本会话。同伴会话在同一棵共享工作树上的动作，只能通过本会话观测到的痕迹（`git status`、文件 mtime、提交历史）间接看到。
- **实测**：本 transcript 的 97 条 `thinking` 记录只有 `signature` 与密文，**没有明文**。所以「只在思考里做过、没落到工具或文字上的判断」在结构上不可能被本方法枚举到。

两条方法本身的坑，我踩到并记下来（对下一个做同类对账的人有用）：

1. **用户指令不一定是 `type=="user"` 记录**。本会话第 6 条用户指令（把 `count()` 改名 `provider()`）是 `type=="queue-operation"` 记录，`.message` 为 `null`。只按 `select(.type=="user")` 枚举会**静默漏掉它**，而且没有任何失败信号——scan 会正常返回 5 条。本会话的 record type 分布：`assistant` 347、`user` 183、`attachment` 590、`queue-operation` 4、`system` 13，另有 `file-history-delta` 15 / `file-history-snapshot` 5。
2. **`system` 记录里的 `away_summary` 会带出一条正文里不显眼的悬置项**（见 §7 的 O-3）。

**我没读什么**（刻意的）：同批派出的另一位评审 `agent-a82c02483ee1b13a3`（"Verify closeout factual claims"）的转录我没有打开，以保持本次枚举独立于它的结论。

**一次被护栏拦下的自身操作，如实记录**：我把第 1 节表格用 heredoc 追加进本文件时，bash 护栏按命令形态拦截了——因为正文里出现了 `git worktree remove` 这个字面串。改用 `Edit` 追加（不经 bash）即可。这说明**形态匹配的护栏会误伤「只是在谈论该命令」的文本**，是写这类复盘文档时会重复撞到的一堵墙。

---

## 1. 试过又放弃的路线（独立枚举）

编号 `A-n`。「有没有载体」留到第 7 节对账时判定，此处只记事实与出处时刻。

| # | 路线 | 试了什么、怎么被否决的 | 出处（事件时刻） |
|---|---|---|---|
| A-1 | `git add <整文件>` 提交本切片 | 判定不可用：共享主树里同伴的在途改动与本切片混在同一批文件（`handler.py`、`pipeline_app.py`、`tests/http/test_pipeline_app.py`），整文件 add 会裹走别人没做完的东西 | 17:20:05 文字；18:02:31 复核 |
| A-2 | `git commit -- <pathspec>` | 判定不可用：pathspec 提交取的是**工作区内容**，同样会带上同伴的在途改动。**这条与项目记忆 `git-commit-takes-the-whole-index` 的推荐正面冲突**——那条记忆写的是「提交一律带 pathspec」，而本会话的场景（同伴改动落在**同一个文件**里）让该推荐失效 | 18:05:12 文字 |
| A-3 | 不带 pathspec 的 `git reset` 清空索引再暂存 | **用了三次**，事后自判为错：会静默取消暂存索引里同伴的全部条目。后两次改成只 `git update-index` 自己那一个路径 | 18:07 / 18:08 / 18:19 前后；18:28:49 自陈；18:34:36 文字 |
| A-4 | 私有索引 `GIT_INDEX_FILE` | **本会话没用**，收尾时才发现项目记忆里早写着这个更好的做法。属于「已有更优解而当时没取用」 | 18:34:36 文字 |
| A-5 | `rm -rf "$WT"` 预清理临时 worktree | 被删除护栏拦下（缺 `DELETE_DISCIPLINE_OK` / `MANIFEST`）。判定为无谓：该路径本来就不存在，直接去掉该行 | 18:08:32 hook 拦截 |
| A-6 | 在共享主树跑测试来证明自己的提交 | 判定证明不了：主树里全是同伴的未提交改动。改为另开两棵临时 worktree（`verify-wt` 在我的提交上、`verify-base` 在基线上） | 18:08:29 文字 |
| A-7 | 在临时 worktree 里 `git checkout <sha>` | 被 git 纪律护栏按**命令形态**拦下。第一反应是「用第二棵 worktree 绕开、不必豁免」，后续才改为显式 `GIT_DISCIPLINE_OK=1` 并写明理由（树是本任务新建、无同伴） | 18:09:50 拦截；18:09:59、18:11:56 文字 |
| A-8 | 用 `worktree remove` 清理两棵临时树 | 被护栏拦一次，先补做「两棵树 `git status` 均为空」的尽调，再加豁免重跑 | 18:27:18 拦截 → 18:27:23 尽调 → 18:27:29 执行 |
| A-9 | **用 `upstream_counts` 布尔判定降级原因** | 一条真正的设计路线否决，而且是**推翻自己上一轮给用户的公开建议**（17:46 的方案里写的就是它）。否决理由：运维可以把 `ghc` 从 `providers` 去掉、或把 `local` 排在它前面，此时上游根本没被问过，既不是缺计数器也不是失败，写成 `ghc-failed` 就是撒谎。改为读 `handle_count_tokens` 自己传出的 `upstream_absent_reason` 字面串 + 尝试轨迹里有无 `ghc:` 开头条目，并为这种情形留出**第五档** | 17:46:15 提出 → 17:57:08 推翻 |
| A-10 | 候选写法 `count(ghc→local)`（**模型自己标了「推荐」**） | 用户在 `AskUserQuestion` 里选了另一档 `count(local:ghc-failed)` | 17:46:28 提问 → 用户裁决 |
| A-11 | 候选「行上不动，只把 `count_tokens_attempts` 落进 JSONL，靠 request_id join」 | 同上，未被选中 | 17:46:28 |
| A-12 | 候选「降级那半染黄（与 `max_tokens` 同级）」 | 用户选「不着色」 | 17:46:28 |
| A-13 | 把 F6（`count(local)` 分不出三种情形）判为「可选、非本次引入」推迟 | 用户一句质疑推翻；自陈「那个判断偏轻」。**这个推迟判断本身就是被否决的路线** | 17:39 处置 → 17:44 用户质疑 → 17:46:15 自陈 |
| A-14 | 在展示层解析字符串来还原降级原因 | 明确否决：判定放在 `handle_count_tokens`，展示层不做形状解析 | 17:57:08 文字 |
| A-15 | 字段名用裸 `provider` | 否决：`RequestLine` 上会与「哪个模型 provider 服务了这一轮」撞义，最终用 `count_provider` / `count_provider_reason` | 18:28:49 文字 |
| A-16 | `ruff format` | 全程**未跑**并显式声明。项目规则要求的「不做」，本会话确实没做 | 17:57:08 文字 |

## 2. 被证伪的因果解释（独立枚举）

| # | 先归因于 | 后来证明 | 证据 |
|---|---|---|---|
| B-1 | 「上游拒绝 count 时代码拿不到 response，所以降级行上**不会**有上游那条腿」——这句被写进了 `handler.py` 注释 | **反例成立**：上游可以 200 却给不出可用的 `input_tokens`，此时两条腿在、答案仍是 `local`。第一次是自己的测试跑红发现「SDK 先抛、拿不到 response」，注释改了一半；评审 F1 再用实测把整句证伪，最终新增第三档并加测试钉住 | 17:15:01 测试红（`test_a_count_that_asked_upstream_and_estimated_anyway_shows_both`）→ 17:16:01 自陈「我之前那句注释说错了」→ 评审 F1 → 17:35:18 补测试 |
| B-2 | 隔离 worktree 上 **44 个失败**疑为自己的提交引入 | 证伪：基线 `6ef4b03` 同样 44 失败 | 18:09:46 文字 → 18:11:59 双树对比 |
| B-3 | 第一次建的 BASE worktree 得到的基线数字 | 作废：BASE 落在了错的提交上，用显式 SHA 重来 | 18:11:29 文字 |
| B-4 | 改名提交 `40681ce` 上 **75 个失败**，第一眼像改名做漏了 | 证伪：缺口不在我的提交里，而在 `main`——`request_log.py` 的 `count_tokens` 字段与 `format_completion_line(status=)` 参数还躺在同伴工作区没提交，而引用它们的 `pipeline_app.py` 与测试已被提交。**且缺口是两个不是一个**（见 §5.2） | 18:20:14 → 18:22:07 差分探针 → 18:25:43 确认同伴 `ea0417c`/`b97930b` 补上 |
| B-5 | `test_a_domain_restriction_refuses_before_upstream_is_called` 失败 | 证伪不是本切片引入：同伴正在改的 web search 策略（schema 默认已改 `drop_fields`，测试仍期望 400） | 17:18:09 → 17:18:56 文字 |
| B-6 | 「我的 `handler.py` 改动丢了」 | 证伪：不是丢了，是被同伴的提交 `064ba63` 整文件裹走了 | 18:02:50 → 18:02:51 `git log -S` 定位 |

## 3. 被纠正的解析/口径错误——命令跑了、有输出、结论仍错（独立枚举）

这一类**不产生任何失败信号**，是本报告最要紧的一节。

| # | 错在哪 | 为什么没有失败信号 | 会话内是否被察觉 | 出处 |
|---|---|---|---|---|
| C-1 | `rg -rn "count_tokens" tests/ -l`：`-r` 是 `--replace` 且吞掉了 `n`，`-n` 根本没生效 | `-l` 只印文件名，把被替换的正文盖掉了，**输出看起来完全正常** | ❌ 从未被察觉 | 17:10:34 |
| C-2 | `rg -rn "async def count_tokens" --type py src/`：同一个误用，这次没有 `-l` | 输出是 `src/app/routes/anthropic.py:n(` 这种正文被替换成字面 `n` 的行，**退出码 0**，看着像「命中了 4 个文件」 | ❌ 从未被察觉（下一步靠文件名猜对了要读哪个文件，误用因此没造成后果） | 17:10:55 |
| C-3 | 残留写法扫描里混入反引号 `` `count\(` `` | 反引号触发 **shell 命令替换**：bash 报 `count(: command not found`，替换结果为空 → pattern 出现**空分支** → **匹配一切**。输出里赫然是 `test_systemd_user_install.py` 的 import 行，而同一条命令里硬编码的 `echo "(空=无残留)"` **照样印了出来** | ✅ 被察觉 | 18:34:20 |
| C-4 | 第二次尝试 `rg -n -F 'count(ghc' -e 'count(local' …`：`-F` 不带参数，于是 `'count(ghc'` 落到**路径位**，rg 报 `No such file or directory` | 硬编码的 `echo "--- 上面为空即无残留 ---"` 再次照印。**连续两次拿到「无残留」结论，而两次命令都是坏的** | ✅ 第三次改成 `--fixed-strings -e … -e … --` 才真正成立 | 18:34:38 → 18:34:44 |
| C-5 | 收尾处置记录里的文件计数写成 15 个副本 / 20 个文件 | 纯计数口径错误，无任何工具会报错 | ✅ 自查纠正为 16 个副本 / 落记录后 21 个 | 18:37:56 |
| C-6 | 「基线 44 失败 → 我的提交 44 失败」这个判据本身 | 判据是**计数相等**而非**失败集合相等**。若同时一条既有测试转红、一条既有失败转绿，计数不变而结论会错。（passed 1184→1190 与新增 6 条测试自洽，所以结论仍站得住，但支撑强度是「计数级」不是「集合级」） | ❌ 会话内未被点出 | 18:11:59 |

**C-1/C-2 的教训有没有载体**：有——`~/.claude/rules/00-user/20-tool-use-preference.md` 用整张表专讲 `rg -rn` 这一族误用，其中 `rg -rn PAT .` 退出码 0、`-rln` 吞掉 `-l` 两条**逐字对应**本次踩到的形态。所以这不是知识要丢，是**规则在场却仍被绕过**（同一会话内两次）。C-3/C-4 则是该规则**没有覆盖**的新形态：不是 rg 选项误用，而是「shell 引号 + 把结论文案硬编码进 echo」。

## 4. 本会话产生或修订的标定值（独立枚举）

全部为实测输出，非估算。**口径不同的数字并排放最容易被误用，所以每行都写明测量对象与测量位置。**

| 时刻 | 数字 | 测量对象 | 测量位置 |
|---|---|---|---|
| 17:17:03 | 1 failed / 1239 passed | `tests/unit` + `tests/http` | **共享主树**（含同伴未提交改动） |
| 17:36:52 | 1244 passed / 0 failed | 同上 | 共享主树 |
| 17:53:05、17:55:43 | 1243 passed / 0 failed | 同上 | 共享主树 |
| 18:08:38 | 44 failed / 1190 passed / 1 skipped | 同上 | 隔离 worktree，我的提交 `9e3d374` |
| 18:11:59 | **44 failed / 1184 passed / 1 skipped** | 同上 | 隔离 worktree，**真正的基线 `6ef4b03`** |
| 18:11:59 | 75 failed / 1170 passed / 1 skipped | 同上 | 隔离 worktree，当时的 main `f76f395` |
| 18:20:14 | 75 failed / 1180 passed / 1 skipped | 同上 | 隔离 worktree，改名提交 `40681ce` |
| 18:22:07 | 75 failed / 1180 passed / 1 skipped（**但失败信息位移**） | 同上 | 同上 + 人为补回 `count_tokens` 字段 |
| 18:24:00 | 1272 passed | 同上 | **共享主树**（含同伴未提交改动，所以比 main 多） |
| 18:25:53 | **1257 passed / 1 skipped** | 同上 | 隔离 worktree，main `fa1df74` |
| 18:33 | 20 → 21 个文件 | `/home/xp/.claude/jobs/23a78bec/tmp/` | job 临时目录 |

派生标定：**「我的三个提交引入零新失败」的量化依据 = 基线 44 → 我的提交 44，且 passed +6（恰为本切片新增的 6 条测试）**。强度见 C-6：计数级。

另一条口径陷阱：**1272（共享树）> 1257（隔离 main）**，两个数字都真，差额来自同伴尚未提交的测试。任何把它们并列成「涨了/跌了」的叙述都是错的。

## 5. 实际执行过的变异与正样本对照（独立枚举）

### 5.1 评审子智能体 `agent-a9a182bcd27c319d8` 的四次受控变异

全部在 **`/tmp/mutant/` 的源码副本**上做（`cp -a src /tmp/mutant/`，`PYTHONPATH=/tmp/mutant/src` 遮蔽，并先验证 `app.observability.request_log.__file__` 确实解析到副本），仓库工作树全程未被写入；每次变异后用 `cp -a` 从真树重新拷贝还原再做下一个。

| 变异 | 改坏的符号 | 触发的测试 | 失败形态 |
|---|---|---|---|
| A | `handler.py` 里 `context.extras["count_tokens_upstream_protocol"]` / `["count_tokens_bytes_in"]` 两行整体删除 | `tests/http/test_pipeline_app.py` 的 `assert lines[0].startswith("H1/H1 …")` | 断言失败（行退化成单腿）。**这条断言是「handler 那两行 extras 是否接线」的唯一守卫，有牙** |
| B | `pipeline_app.py` 把 `isinstance` 守卫换成 `str(... or "HTTP/1.1")`，无条件声称上游腿 | 同一条 `startswith` 断言 | `'H1/H1 200 …'.startswith('H1 200 …')` == False |
| C | `request_log.py` 的 `if line.counted:` 改成 `if False and line.counted:` | `tests/unit/test_request_log.py::test_a_token_count_is_not_a_turn_that_lost_its_reply` | 整行相等断言失败 |
| D | `pipeline_app.py` 的 `counted=trace.counted` 改成 `counted=trace.counted or "ghc"` | `tests/http` **5 条既有测试**同时变红（`test_a_stream_cut_after_its_stop_reason_is_not_called_truncated` 等） | `assert 'end_turn' in …` 失败——`counted` 泄漏会吞掉 stop_reason |

变异 A 的第一次运行**没跑成**（`cd /tmp/mutant` 后 `uv run pytest` 报 `Failed to spawn: pytest`），第二次从仓库根重跑才拿到结果。这条小挫折反而证明变异证据当时是「跑出来的」而非推断的。

**额外的正样本对照（没人点名，但它连响两次）**：`tests/unit/test_request_log_file.py::test_a_successful_request_writes_one_complete_structured_record` 断的是 JSONL 记录的**完整键集合**。本会话每加一个 `RequestLine` 字段它就红一次——加 `counted` 时红（17:16:38），加 `counter_reason` 时又红（17:52:51）。它是「新字段会自动流进落盘记录」这件事的活守卫。

### 5.2 主会话的一次差分探针（不是破坏式变异，是「补回缺失符号看错误信息位移」）

| 项 | 内容 |
|---|---|
| 位置 | 隔离 worktree `…/jobs/23a78bec/tmp/verify-wt`，HEAD = `40681ce` |
| 动作 | 用 python 定点插入 `count_tokens: bool = False` 到 `RequestLine` |
| 观察 | 总数不变（75 failed / 1180 passed），但首条失败从 `RequestLine.__init__() got an unexpected keyword argument 'count…'` **位移**到 `format_completion_line() got an unexpected keyword argument 'sta…'` |
| 结论 | main 上缺的是**两处**不是一处，且都在同一个文件 |
| 还原 | 同一次 Bash 调用内 `GIT_DISCIPLINE_OK=1 git -C "$WT" checkout --quiet -- <file>` |

**这条探针的产物已不存在**（worktree 于 18:27 整体删除），它现在只活在 transcript 里。

## 6. 实际跑过的运行时/外部能力探针（独立枚举）

| # | 探针 | 观察到什么 | **不能证明什么** |
|---|---|---|---|
| P-1 | `PYTHONPATH=src uv run python -c "from app.observability.request_log import RequestLine, format_completion_line; …"`（17:38:40、17:54:14 两次） | 直接构造 `RequestLine` 打印真实渲染行，肉眼确认五档形态 | 只证明**渲染函数**给定字段会印成什么。**不证明**服务路径真会把这些字段填成那样——那要靠 `tests/http` 的服务路径测试 |
| P-2 | 评审的 `/tmp/probe_count_line.py`（复用 `tests/http/test_pipeline_app.py` 的 `make_client`，上游桩返回 `200 {"input_tokens": 0}`） | 复现 F1 的反例：上游 200 但答案不可用 → 两条腿 + `local` | 只证明**这一种**「响应可得但答案不可用」的走法。不证明超时、传输中断等其他上游失败形态的行形状 |
| P-3 | `git log -S "count_tokens_reason" -- src/app/server/handler.py` | 定位到自己的改动被同伴的 `064ba63` 整文件裹走 | 只证明该字符串**首次进入历史**的提交。不证明同伴是有意还是无意 |
| P-4 | `ls -l --time-style=+%H:%M:%S` 看 mtime + `date` 对表（18:03:58） | `tests/unit/test_request_log.py` 15 秒前刚被改过 → 判定同伴此刻在树里工作 | mtime 只证明**文件被写过**。不证明是谁写的、写了什么，也不证明同伴仍在场 |
| P-5 | 每次提交前的索引指纹核对：`git diff --cached --name-only` 比对硬编码 EXPECTED 清单 + `rg -c "COUNT_TOKENS_SUFFIX\|status=status\|STATUS_COLOURS\|count_tokens: bool\|with_deadline_at"` | 每次都确认索引里只有自己那几个 blob | 关键词清单是**手写的同伴标志物白名单**，只挡得住已知形态；同伴换个写法就挡不住。这是抽样不是证明 |
| P-6 | 两棵一次性 worktree（`verify-wt` / `verify-base`） | 在与共享树隔离的树上取得基线与提交后的两组数字 | 证明的是**提交出来的树**的行为，不证明共享工作区当下的行为（那里还有同伴的未提交改动） |
| P-7 | 收尾时 `find … -printf` 与 `ls` 两种枚举交叉核对 job tmp 目录 | 两种枚举一致，20 个文件 | 只覆盖 job tmp 目录。**不覆盖仓库外、job 目录外的证据**——实测：`/tmp/probe_count_line.py` 此刻仍在，`/tmp/mutant/` 已不在 |

---

## 7. 双向对账

对账对象：`/home/xp/.claude/jobs/23a78bec/tmp/DISPOSITION.md` 的「非文件线索的载体」表，以及 `docs/tmp/260820-closeout-count-tokens-log-line.md`（该文件第 5 行自标「草稿，未经独立评审」，第 79-81 行「可复用资产建议」尚空——对账时它正在被补写）。

### 7.1 方向一：清单里有、事件源里找不到或被夸大

我逐条核对了两份清单里的**每一个可证伪主张**：提交 SHA（13 个全部 `git cat-file` 存在）、载体文件与行号、测试名、文件计数（16 + 4 + 1 = 21，与目录实际一致）、worktree 清单、五种渲染形态。**没有发现虚构。** 三处需要降级或订正：

| # | 主张 | 事件源实际支持的 | 判定 |
|---|---|---|---|
| **D1-1** | `DISPOSITION.md:31`「**同样的 44 条**，且多 6 条通过」 | 两次运行只印了**计数**（基线 44 failed / 1184 passed，我的提交 44 failed / 1190 passed）。**失败测试的集合同一性从未被核对**——没有 `--tb=no -q` 的名单比对，也没有 `--last-failed` 交集 | **夸大**。应写成「同样**多**的 44 条」。结论（零新失败）仍站得住，因为 passed +6 恰等于本切片新增的 6 条测试；但支撑强度是计数级，不是集合级 |
| **D1-2** | `DISPOSITION.md:31` / 收尾报告:55「那 44 条属同伴当时在途的超时改动，**已由其 `783f023` 修复**」 | 从未在 `783f023` 单点跑过测试。可观测的只有：基线与我的提交上都是 44 条超时类失败；`fa1df74` 上 0 失败。「是 783f023 修的」是从提交标题（"make each of the three upstream timeouts guard the phase it names"）推出的**推断** | **需标注为推断**而非观测。合理，但两份文档都把它写成了既成事实 |
| **D1-3** | 收尾报告:49 / `DISPOSITION.md:32`「1257 passed / **0 failed**」 | 实测输出为 `1257 passed, 1 skipped`。"0 failed" 为真，但 **1 skipped 被丢掉了** | 极轻。补一个 `1 skipped` 即可 |

另有一处**只出现在对话文本、没有污染持久文档**的时序错误，仍值得记（因为它把教训说反了）：18:28:49 的对话说「后面两次我改用了只 `update-index` 我那一个路径」。实际时间线相反——干净做法（`stage_a.py` / `stage_b.py`，纯 `hash-object` + `update-index`，脚本内无 reset，已核对）用在**最早的两个提交**（18:06、18:08），三次不带 pathspec 的 `git reset --quiet` 出现在**之后**（18:19:05、18:19:57、18:25:46）。所以真实教训是「**会话后期反而退回了更差的做法**」，而不是「后来改好了」。收尾报告第 73 行没有复述这句，未受污染。

### 7.2 我核对为**真**的载体主张（正面确认，避免只报问题）

| 清单主张 | 核对结果 |
|---|---|
| B-1 的载体「`handler.py` 注释 + 测试 `test_a_count_upstream_answered_uselessly_keeps_the_leg_it_flew`」 | ✅ 测试在 `tests/http/test_pipeline_app.py:1422`；注释在 `src/app/server/handler.py:237`，且把「腿的含义比『上游答了计数』更窄」这句写全了 |
| A-9 的载体「`handler.py` 判定处注释」 | ✅ `src/app/server/handler.py:279` 逐字记下了否决理由（运维可把 `ghc` 移出 `providers` 或把 `local` 排前） |
| A-14「展示层不解析字符串」 | ✅ `handler.py:278` 末句 "Left to the display layer they would be one string." |
| A-10 箭头写法被否决 | ✅ `.dev/docs/tui/spec.md:98` |
| A-12 不着色的裁决**与理由** | ✅ `.dev/docs/tui/spec.md:147`，并解释了为什么不进结束原因那条阶梯 |
| A-11「只进 JSONL」这一档 | ✅ 以「做法」的形式活在 `.dev/docs/tui/deferred.md:76`，未被静默砍掉 |
| 改名 `count(` → `provider(` 的**理由** | ✅ `.dev/docs/tui/spec.md:98` 与提交 `fa1df74` 的标题 |
| 文件计数 16 / 4 / 1 = 21 | ✅ 与 `/home/xp/.claude/jobs/23a78bec/tmp/` 实际内容逐个吻合 |
| 剩余 worktree 不属本会话 | ✅ `git worktree list` 现为主树 + `826d4cda/tmp/review` + `.claude/worktrees/delivery-keepalive` |
| 三次不带 pathspec 的 `git reset` | ✅ 精确 3 次，时刻已列于 7.1 |

### 7.3 方向二：事件源里有、清单里没有

**判定顺序按要求执行：先查是否已有载体，再评严重度。**

| # | 线索 | 已有载体？ | 严重度与理由 |
|---|---|---|---|
| **O-1** | **收尾那次「活文档无残留」的扫描，连续两条命令都是坏的，而硬编码的 `echo "(空=无残留)"` 照样印出了结论**：第一条因反引号触发 shell 命令替换 → 正则出现空分支 → 匹配一切（输出里是 `test_systemd_user_install.py` 的 import 行）；第二条 `-F` 不带参数导致 pattern 落到路径位 → rg 报 `No such file or directory`。第三条才成立 | ❌ **无任何载体** | **高**。这是本次任务点名的第 3 类的教科书样本，而且发生在**支撑收尾结论的那一步**上。可泛化的判据：**把结论文案硬编码进 `echo`，等于让一条坏命令自动通过**；空输出与命令失败在这种写法下同形。现有规则（`20-tool-use-preference.md`）覆盖 rg 选项误用，**不覆盖**这个形态 |
| **O-2** | **在共享主树上 `git worktree add --detach "$BASE" HEAD~2` 取到的不是预期基线**：那一刻主树 HEAD 已被同伴推进到 `f76f395`，`HEAD~2` 落成了**我自己的提交 `9e3d374`**。结果是 18:08:38 与 18:10:02 两次看似「不同点位」的数字（都是 44 failed / 1190 passed）其实是**同一个提交测了两遍**。靠 `git log --oneline -1` 的回显才发现，随后改用显式 SHA 重来 | ❌ 无载体（收尾报告只写了最终那次正确的基线对比） | **中高**。教训可直接泛化：**共享工作树上，任何相对 revision（`HEAD~n`、`<branch>^`）作为 worktree 起点或基线都不安全**，因为 HEAD 由同伴推进。这条比「我用了两棵 worktree」有用得多，且与项目已有的共享树纪律同族 |
| **O-3** | 评审报告 `docs/tmp/260820-review-count-tokens-log-line.md:135-150` 的四次变异表，用的全是**改名前**的符号（`counted=trace.counted`、`if line.counted:`、`counted=trace.counted or "ghc"`）。改名 `40681ce` 之后这些字符串在仓库里**已不存在**，照着复现会找不到锚点 | 变异证据本身 ✅ 有载体（该报告已随 `86f4a46` 提交）；**「它已过时」这件事 ❌ 无标注** | **中**。会话在 18:34:53 判定「报告里的 5 处 `count(` 属运行记录，保持原样」——那个判断对，但只覆盖了叙述，没覆盖**变异表里的可执行锚点**。建议在该报告加一行「符号名为 `40681ce` 之前的；现名 `count_provider` / `format_count_provider`」 |
| **O-4** | 同一会话内**两次** `rg -rn` 误用（`-r` 是 `--replace` 并吞掉了 `n`），第二次的输出是被替换成字面 `n` 的行（`src/app/routes/anthropic.py:n(`），退出码 0，**全程零察觉** | ✅ 载体充分：`~/.claude/rules/00-user/20-tool-use-preference.md` 用整张表覆盖这一族，`rg -rn PAT .` 退出码 0、`-rln` 吞掉 `-l` 两条**逐字对应**本次形态 | **中**。知识没有要丢的风险，问题是**规则在场而零触发**。这不是「再写一遍规则」能解决的，值得作为一条观察交给用户：该规则本会话的实际拦截率为 0/2 |
| **O-5** | 项目记忆 `git-commit-takes-the-whole-index` 的头号建议是「**提交一律带 pathspec**：`git commit --file=<msg> -- <你的路径…>`」。本会话实测该建议在此场景**失效**——同伴的在途改动落在**同一个文件**里，pathspec 提交取的是工作区内容，照样会裹走 | 事实 ✅ 在收尾报告第 71 行；但**跨会话权威载体（记忆）未更新** | **中**。18:35 对该记忆的补写只加了「不带 pathspec 的 `git reset`」，没有给头号建议加上适用条件。下一个会话读到的仍是无条件推荐。属 `one-authority-allows-contextual-restatement` 意义上的权威源落后于派生记述 |
| **O-6** | §5.2 那次**差分探针**：在隔离 worktree 里补回缺失字段、观察失败信息从 `RequestLine.__init__(…'count…')` **位移**到 `format_completion_line(…'sta…')`，从而判定 main 上缺的是**两处**而非一处 | 结论 ✅ 在收尾报告第 77 行（两处都点了名）；**方法 ❌ 无载体**，且 worktree 已删、产物不存在 | **中**。「计数不变而错误信息位移 = 还有下一个缺口」是一条可复用的诊断手法，成本极低 |
| **O-7** | `ls -l --time-style=+%H:%M:%S` + `date` 对表，判定「`tests/unit/test_request_log.py` 15 秒前刚被改过 → 同伴此刻在树里」，并据此改变了提交策略 | ❌ 无载体 | **中低**。共享树作业里判断「同伴是否在场」的实用手法；它的边界（mtime 只证明文件被写过，不证明是谁、不证明仍在场）也值得同时记下 |
| **O-8** | 两次 git 纪律护栏拦截的处置先例：对**自己刚建的一次性 worktree**，正确做法是先做尽调（`git status` 为空、树是本任务新建）再显式 `GIT_DISCIPLINE_OK=1` 豁免并写明理由，而不是绕开。会话第一次选择了绕开，第二次才改为豁免 | 半个：护栏文案本身写了「先自检…独占此树 → 加前缀放行」 | **低**。知识在护栏里，缺的是「绕开也是一种代价」的先例 |
| **O-9** | `/tmp/probe_count_line.py` **此刻仍在磁盘**（`/tmp/mutant/` 已不在）。收尾报告「临时状态」一节只清点 job 目录，未声明这个边界 | ✅ 评审报告第 205 行明写「`/tmp/mutant/`、`/tmp/probe_count_line.py` 未清理，可随时删」 | **低**。索引不全，不是知识要丢。补一句「仓库外证据见评审报告末节」即可 |
| **O-10** | 标定值 1272（共享树）与 1257（隔离 main）并列在同一张验证表里，**未写明差额来自同伴尚未提交的测试** | 两行的「测量位置」列已区分 | **低**。但下一个读者很容易把它读成「涨了 15」 |
| **O-11** | 候选方案的否决记录，`DISPOSITION.md` 的「放弃的路线」一行只列了箭头写法与 `upstream_counts` 两条；`AskUserQuestion` 实际给出的另外两个未选项（只进 JSONL、降级染黄）不在该行 | ✅ 两者都有载体（`deferred.md:76`、`spec.md:147`），且都带了理由 | **低**。纯索引问题，`record-what-not-adopted` 的实质要求已满足 |
| **O-12** | `provider(no-counter,local)` 这个拼法**用户没给过例子**，仍待确认。会话结束时的 `away_summary` 把它列为「下一步」 | 收尾报告第 43 行有记，但**不在「待裁决/未做」一节** | **低**。位置问题；放进待裁决一节就闭合 |
| **O-13** | `rm -rf "$WT"` 被删除护栏拦下（该路径本就不存在，去掉即可） | ❌ 无载体 | **可不记**。无可泛化内容 |

---

## 8. 结论

**VERDICT: needs-fix**（针对两份清单，不针对代码改动本身）。

按派发给定的三条停止条件逐条回答：

1. **每个被发现的线索都有可定位的持久载体** —— **尚未满足**。O-1、O-2、O-6、O-7 四条**完全没有载体**（O-13 判为不值得记）；O-3、O-5 两条的载体存在但**内容已过时或与新事实冲突**。其余条目经核对**都已有载体**，只是索引不全。
2. **记录写清了扫描方法与边界** —— 本报告 §0 已写；两份清单原本各写了一句边界（`DISPOSITION.md:35` 的「不含 `tests/tui` 与冒烟测试」、收尾报告第 55 行同句），是好的实践，建议保留并按 O-9/O-10 补两句。
3. **不声称差集已被证明为空** —— 本报告**明确不作此声称**。§0 已说明本方法结构上看不见「只在思考里发生的判断」（97 条 `thinking` 记录无明文），也看不见「跑了、有输出、结论仍错且**从未被打脸**」的那一类。§3 能列出的六条全都是**事后被别的动作打脸过的**；同型而未被打脸的，留在盲区里。

**建议的最小闭合动作**（按 ROI 排序，均为追加，不改既有结论）：

- 把 O-1、O-2 写进收尾报告的「可复用资产建议」一节（该节正好还空着）。这两条是本会话最贵的两个教训，且都不是本项目特有的。
- 给评审报告的变异表加一行符号名时效说明（O-3）。
- 给记忆 `git-commit-takes-the-whole-index` 的头号建议补上适用条件（O-5）——它是跨会话权威源，落后代价最大。
- 收尾报告里把 D1-1 的「同样的 44 条」改成「同样**多**的 44 条」，D1-2 的 `783f023` 标注为推断（各一处措辞）。
- O-6、O-7 可并入 O-2 同一条「共享树验证手法」里，不必单列。

**我这次没有做、也不建议做的**：不建议为「集合级失败对比」补跑一次测试来加固 D1-1。那三个提交已经落到 `main` 并被后续提交覆盖，重跑的成本与它能改变的结论不成比例；把强度如实标成计数级就够了。


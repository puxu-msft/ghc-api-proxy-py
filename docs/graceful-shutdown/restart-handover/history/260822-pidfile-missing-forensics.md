# standalone.pid 失踪取证：写过，被后来的临时实例删掉了

**日期**：2026-08-22
**性质**：只读取证。除本报告外未修改任何文件，未启停任何进程，未运行任何测试。
**结论把握程度**：**足以据此行动**。关键一环有直接的一手观测记录（当时读到了那份 pidfile 的内容），删除机制在代码里可逐行核对，删除者的三次调用都有带时间戳的转录留存。

---

## 0. 一句话结论

pidfile **被写过**。旧实例 537115 在 2026-08-21 13:10 启动时正常写入了 `~/.local/share/ghc-api-proxy/standalone.pid`（内容 `537115\n2467590`，13:17:36 有直接观测）。它是在 **13:42:45** 被一个临时起的 `uvx ... ghc-api-proxy start --port 41411` 实例正常退出时删掉的，随后 **15:41:05** 又被第二个临时实例（`--port 41412`）重复了一次同样的覆盖—删除。这两个临时实例都没带 `--pidfile`，于是落在同一个默认路径上；也都没带 `--restart`，所以它们没有向旧实例发 SIGUSR2，旧实例毫发无损地继续服务到今天 11:50 —— 只是从此在磁盘上"查无此人"。

**这不是偶发事故，是一个仍然活着的缺陷**：pidfile 的默认路径与端口无关，任何一次临时 `ghc-api-proxy start`（哪怕换个端口、哪怕是 uvx 装的另一个版本）都会静默顶掉生产实例的记录，并在自己退出时把它删干净。详见 §5。

---

## 1. 时间线

所有时间为 UTC。

| 时间 | 事件 | 证据来源 |
|---|---|---|
| 2026-08-21 12:38:30 | 提交 `fce9311` —— 旧实例后来加载的版本 | `git log -1 fce9311` |
| 2026-08-21 13:10:17 | **旧实例启动**：`uv run --directory /home/xp/src/ghc-api-proxy-py ghc-api-proxy start --port 4141 --restart`，uv=537112 / python=537115 | 主会话已核实（背景事实） |
| 2026-08-21 13:10:1x | 旧实例 `on_serving` 触发，写入 pidfile `537115\n2467590` | 由 13:17:36 的观测反推（§2.1） |
| 2026-08-21 13:16:54 | `history.db-wal` 被截为 0 | `ls -la --time-style=full-iso` |
| **2026-08-21 13:17:36** | **subagent 直接读到该 pidfile**，内容为 `537115\n2467590`；13:17:50 复核 `pid 537115 proc_exists True`，cmdline 正是 `.../ghc-api-proxy start --port 4141 --restart` | transcript（§2.1） |
| 2026-08-21 13:36:47 | 提交 `2924a8c`（httpx2 迁移） | `git log -1 2924a8c` |
| 2026-08-21 13:37:45 | 另一会话跑 `uvx --refresh --from git+file://...@2924a8c ghc-api-proxy start --port 41411`，**未带 `--pidfile`、未带 `--restart`**；13:37:55 起来，`pid=607694`。**此刻 pidfile 被覆写为 607694** | transcript（§2.2） |
| **2026-08-21 13:42:45** | `timeout 300` 到期发 SIGTERM，日志 `[ OK ] 13:42:45 stopped`。`run_standalone` 正常返回 → `remove_pidfile` 命中自己的 pid → **unlink。旧实例的记录从此消失** | transcript + 代码（§2.2、§3） |
| 2026-08-21 15:04:46 | 提交 `b71e83d`（当时的 main HEAD） | `git log --before` |
| 2026-08-21 15:38:10 | `uvx --constraints <URL> ... --port 41412` 第一次尝试，**constraints 取不到直接报错，服务器从未起来**，不写 pidfile | transcript（§2.3） |
| 2026-08-21 15:38:34→15:38:43 | 同一探针重跑成功，`pid=744537` 起在 41412。**pidfile 被再次创建，内容 744537** | transcript（§2.3） |
| **2026-08-21 15:41:05** | `timeout 150` 发 SIGTERM，日志 `[ OK ] 15:41:05 stopped` → 再次 unlink。**这是最后一次删除** | 同上 |
| 2026-08-21 20:53:36 | `config.yaml` 被改（用户侧） | `ls` |
| 2026-08-21 23:57:50 | `requests-20260821.jsonl` 最后写入 —— 旧实例一直在正常服务 | `ls` |
| 2026-08-22 11:30:50 | `tokenization.json` 写入（旧实例仍在跑） | `ls` |
| 2026-08-22 11:45:40 | **新实例 2254087 启动**，带 `--restart`；`live_predecessor()` 读不到文件 → 返回 None → 不发 SIGUSR2 | 主会话已核实 |
| 2026-08-22 11:45:44.396 | 新实例 `write_pidfile` 建出当前 inode，内容 `2254087\n10599823` | `stat` Birth |
| 2026-08-22 11:50 前后 | 用户手动 SIGINT 旧实例 | 主会话已核实 |

---

## 2. 每条证据及其取得方式

### 2.1 决定性证据：13:17:36 时 pidfile 存在，且记录的就是旧实例

**取得方式**：扫描 `~/.claude/projects/-home-xp-src-ghc-api-proxy-py/` 下全部 738 个 transcript JSONL（含 `subagents/`），抽出 `tool_use` 与其配对的 `tool_result`，按正则 `standalone\.pid|ghc-api-proxy start` 过滤，再按 `timestamp` 限定窗口。脚本落在 `/tmp/scan_tx3.py`（一次性探针，非仓库产物）。

**探针自证**：同一扫描在无时间窗口时命中 120 处、在 08-21 12:00–08-22 13:00 窗口内命中 15 处，其中包含本次调查自己刚发出的几条命令 —— 说明扫描器确实读到了当天的记录，不是空转。

命中记录（`0b4f21e6-.../subagents/agent-ae96c229efc1e05b8.jsonl`，`2026-08-21T13:17:36.168Z`）：

```
--- 命令 ---
pid_path = Path('/home/xp/.local/share/ghc-api-proxy/standalone.pid')
print('pid_file', pid_path.read_text().strip())
pid = int(pid_path.read_text().strip())
...
--- 输出 ---
Exit code 1
pid_file 537115
2467590
Traceback ...
ValueError: invalid literal for int() with base 10: '537115\n2467590'
```

那位 subagent 的脚本假设文件只有一行 PID，于是在 `int()` 上崩了 —— **正因为它崩了，它把文件的完整两行原样打印了出来**。14 秒后（13:17:50）它改写脚本重跑：

```
pid 537115 proc_exists True
cmdline /home/xp/src/ghc-api-proxy-py/.venv/bin/python3 /home/xp/src/ghc-api-proxy-py/.venv/bin/ghc-api-proxy start --port 4141 --restart
pid 2467590 proc_exists False
```

第一行 `537115` 是 PID，第二行 `2467590` 是 `/proc/537115/stat` 字段 22（starttime，时钟嘀嗒数），即 `PidfileEntry.start_token`。格式与 `pidfile.py::PidfileEntry.rendered()` 完全吻合。

**这一条单独就排除了"从未被写过"。**

### 2.2 第一次删除：13:37:45 的 uvx 实例

同一扫描命中（`ca953617-....jsonl`，`2026-08-21T13:37:45.484Z`）：

```
cd /home/xp/.claude/jobs/ca953617/tmp && timeout 300 uvx --refresh \
  --from "git+file:///home/xp/src/ghc-api-proxy-py@2924a8c" ghc-api-proxy start --port 41411 > .../uvx.log 2>&1
```

其 `tool_result`：

```
(exit 124)
Installed 66 packages in 203ms
[ OK ] 13:37:55 ghc-api-proxy v0.1.0 pid=607694
...
[ OK ] 13:37:56 listening on http://127.0.0.1:41411
[DRIN] 13:42:45 SIGTERM received, draining, waiting for in-flight requests
[DRIN] 13:42:45 SIGTERM received, interrupting in-flight requests
[ OK ] 13:42:45 stopped
```

要点：

- 命令行**没有 `--pidfile`** → `StandaloneOptions.pidfile_path()` 回落到 `standalone_pidfile_path()`，也就是那个真实路径。端口不同**不影响** pidfile 路径。
- 命令行**没有 `--restart`** → `predecessor = None` → 不会给 537115 发 SIGUSR2。这解释了为什么旧实例安然无恙。
- `exit 124` + `SIGTERM received` 说明是 `timeout 300` 到点杀的，起止差正好 300 秒。
- **`[ OK ] 13:42:45 stopped` 这一行本身就是删除已发生的证据**：该行由 `cli.py::report_shutdown` 打印，而 `report_shutdown` 在 `_serve_pipeline` 里排在 `await run_standalone(...)` **之后**（`src/app/cli.py:164-169`）。`run_standalone` 正常返回的唯一路径会先执行 `else: remove_pidfile(pidfile)`（`src/app/lifecycle/entry.py`）。

### 2.3 第二次删除：15:38:34 的 uvx 实例

同一会话，`2026-08-21T15:38:34.377Z`，`timeout 150 uvx --refresh --constraints <URL> --from git+file://...@$HEAD ghc-api-proxy start --port 41412`：

```
constraints reachable: aiofiles==25.1.0
Installed 66 packages in 180ms
[ OK ] 15:38:42 ghc-api-proxy v0.1.0 pid=744537
[ OK ] 15:38:43 listening on http://127.0.0.1:41412
[DRIN] 15:41:05 SIGTERM received, draining, waiting for in-flight requests
[ OK ] 15:41:05 stopped
```

同样无 `--pidfile`、无 `--restart`。这一次把文件重建成 `744537`，再于 15:41:05 删除。

它前面 24 秒还有一次（15:38:10）失败尝试，`error: Error while accessing remote requirements file` —— 服务器从未启动，**不写 pidfile**，与本案无关，列出仅为闭合当天的调用清单。

### 2.4 全局扫描：窗口内没有第四个候选

把扫描面扩到 `~/.claude/projects/` **与** `~/.openclaude/projects/` 全部 4040 个 JSONL（`/tmp/scan_all.py`），正则 `ghc-api-proxy\s+start|standalone\.pid|app\.lifecycle\.entry|run_standalone`，窗口 08-21 13:15 → 08-22 11:46：

- 候选文件里共扫到 **20297** 次 Bash `tool_use`（探针自证：确实在读命令，不是零命中）；
- 窗口内匹配 **5** 条，即 §2.1 的两条读取 + §2.2/§2.3 的三条 start。

有 12 个文件读失败（`READFAIL`，全部集中在 `-home-xp-src-copilot-api-js--claude-worktrees-history-content-docs/` 这一个已被删掉的 worktree 项目目录下，是 `rglob` 枚举到的悬空条目）。这些是 **copilot-api-js** 项目的转录，不是本项目的，且属于另一个仓库的 worktree；**这是本次扫描唯一的覆盖缺口**，但它不影响结论 —— §2.1 的正面观测已经独立证明了"写过"，而 §2.2 的日志已经独立证明了"至少有一次删除真的发生了"。

### 2.5 文件系统旁证

`stat` / `ls -la --time-style=full-iso`（本次亲自跑，输出见 §1 表格来源）：

- pidfile 的 **Birth = 2026-08-22 11:45:44.396**、mtime = `.400`、size 17、inode 5835376。
- **注意**：Birth 在这里 **不能** 用来推断"文件第一次出现的时间"。`write_entry` 走的是"写临时文件 + `Path.replace()` 原子改名"（`pidfile.py`），**每写一次就换一个 inode**，Birth 只反映最近一次写。所以 Birth=11:45:44 只说明"新实例写过"，既不支持也不反对"之前存在过"。这一条我一开始差点读反，特此写明。
- 父目录 `~/.local/share/ghc-api-proxy/` 的 mtime 是 **2026-08-22 11:53:49**，与 `tokenization.json` 的 mtime 同一时刻 —— 也是原子改名造成的目录 mtime 更新。**目录 mtime 同样无法用来定位 pidfile 的删除时刻**，它早已被后续写入覆盖。
- `requests/requests-20260821.jsonl` 写到 23:57:50、`tokenization.json` 写到 08-22 11:30:50，佐证旧实例在两次删除之后仍在正常服务 —— 删除的是记录，不是进程。

### 2.6 shell history：覆盖不到，明确记为盲区

- `~/.bash_history` 存在，268348 字节，**mtime = 2026-08-21 06:27:07**。
- 解析后共 2295 条带时间戳的条目，**最大时间戳 = 2026-08-21 06:27:04**。
- 探针自证：`rg -c 'ghc-api-proxy' ~/.bash_history` → **108**，且解析出 135 条含 `ghc-api-proxy`/`uv run` 的命令，包括 `2026-08-20 13:46:20 uv run ghc-api-proxy start --port 4141 --restart`。所以解析器是好用的。
- `~/.zsh_history` **不存在**（`ls` 报 `No such file or directory`，非静默失败）。

**结论**：bash history 的覆盖在 08-21 06:27 就断了 —— 那之后的交互式 shell 还没退出、历史尚未落盘。**它对本案是零信息量的盲区，不是"没找到第三个实例"**。这个区别很重要：如果只看 history 就下"没有第三个实例"的结论，会是彻头彻尾的探针失败读成否定结论。真正的答案来自 transcript（§2.2/§2.3），那里确实找到了。

---

## 3. 机制核对（读码，逐行）

`src/app/lifecycle/entry.py::run_standalone`：

```python
pidfile = options.pidfile_path()          # 无 --pidfile 时 = standalone_pidfile_path()
predecessor = live_predecessor(pidfile) if options.restart else None   # 无 --restart 时恒为 None
...
async def announce() -> None:
    write_pidfile(pidfile)                # 覆盖式写入，不看原内容是谁的
    announced = True
    if predecessor is not None:
        signal_restart(predecessor)
...
server = StandaloneServer(adapter, ..., on_serving=announce, ...)
try:
    report = await server.serve()
except BaseException:
    ...
else:
    remove_pidfile(pidfile)               # 正常退出路径，无条件调用
```

`src/app/lifecycle/standalone.py::StandaloneServer.serve`：`on_serving` 紧跟 `await self._adapter.arm()` 之后被 await，且 `arm()` 之后就是在 accept 了。**只要进程真的开始服务，`write_pidfile` 就一定跑过**；若它抛 `PidfileError`，异常会经 `_abandon_startup` 向外传播，进程根本起不来。旧实例服务了 22 小时，所以写入必然发生过 —— 这与 §2.1 的直接观测互相印证。

`src/app/lifecycle/pidfile.py::remove_pidfile`：

```python
resolved = os.getpid() if pid is None else pid
entry = read_pidfile(path)
if entry is None or entry.pid != resolved:
    return False        # 只在"文件还记着我自己"时才删
path.unlink()
```

这道守卫是为"后继者已经覆写过、我不该删活人的记录"设计的。它防住了 A→B 平滑接管的场景，**但防不住 B 先覆写再自删**：B 写完之后文件记的就是 B，`entry.pid == resolved` 成立，unlink 照删不误，而 A 的记录早在 B 的 `write_pidfile` 那一刻就没了。两次 uvx 运行走的正是这条路。

`write_pidfile` 记的是 `os.getpid()`；启动日志 `pid=607694` 来自 `src/app/server/pipeline_app.py:989` 的 `os.getpid()`，**同一个数**，所以日志里的 pid 就是写进文件里的 pid。

`StandaloneOptions.pidfile` 只从 CLI 的 `--pidfile` 来（`src/app/cli.py:319 pidfile=pidfile`），**配置文件无法影响它**，所以 08-21 20:53 那次 `config.yaml` 改动与本案无关。

---

## 4. 版本核对（避免跨版本按行号推断）

按纪律要求，实际取出三个提交的文件内容比对 sha256，而不是看行号：

| 文件 | `fce9311`（旧实例加载的） | `2924a8c`（13:37 那次 uvx） | `HEAD` (`db6f549`) |
|---|---|---|---|
| `src/app/lifecycle/entry.py` | `b7340b71f067` | `b7340b71f067` | `b7340b71f067` |
| `src/app/lifecycle/pidfile.py` | `b5efd0f52ffe` | `b5efd0f52ffe` | `b5efd0f52ffe` |
| `src/app/config/paths.py` | `199bfa694ec3` | `199bfa694ec3` | `199bfa694ec3` |

三者**逐字节相同**。`git diff --stat fce9311 HEAD -- src/app/lifecycle/ src/app/config/paths.py src/app/cli.py` 只报出 `src/app/cli.py`（29+/45-），逐行读完该 diff，改动是 `gen-config` 独立成命令、删 `--ghc-api-base-url`、加 `proxy_from_cli` 与 `resolve_provider_base_urls`、一处文档路径重指 —— **`pidfile=pidfile` 与 `restart=restart` 的传参、`run_standalone` 的调用位置均未变**。15:38 那次 uvx 用的是当时 main 的 HEAD `b71e83d`（`chore: lock the versions a fresh install actually resolves`），它在 `fce9311` 与 `db6f549` 之间，同样落在这段"未变更"的区间里。

所以：不存在"那时的写入条件与现在不同"的可能。

---

## 5. 这不是一次性事故（本案最该带走的一条）

pidfile 的默认路径由 `user_data_path() / "standalone.pid"` 决定，**与端口、与安装方式（`uv run` / `uvx` / 系统安装）、与代码版本都无关**。于是：

> 任何一次不带 `--pidfile` 的 `ghc-api-proxy start`，无论跑在哪个端口、由谁启动、装的是哪个 commit，都会在开始服务的一瞬间把生产实例的 pidfile 记录覆盖掉；等它自己正常退出，再把这个文件删干净。生产实例对此毫无察觉，日志里一个字都没有。

后果就是本案：下一次真正的 `--restart` 平滑重启找不到前任，**静默降级成"两个进程同时 `SO_REUSEPORT` 抢同一个端口"**，而不是接管。这比报错更糟 —— 它长得像成功。

`--restart` 那条路更凶：临时实例若碰巧带了 `--restart`，它会真的给生产实例发 SIGUSR2，把线上服务排空掉。本次两个临时实例都没带，纯属运气。

这条属于"发现了但不在本次任务范围内"的东西，按 `no-silently-cut-but-defer` 记在这里，交由用户裁决要不要修、怎么修。可能的方向（**未采纳、未实施，仅供参考**）：把 pidfile 路径与监听端口绑定；或让 `write_pidfile` 在覆盖一个"记录着另一个活进程"的文件时拒绝/告警；或给非默认端口的启动默认换一个 pidfile。哪一个都会改变对外行为，不该由我定。

---

## 6. 已排除的假设及排除理由

| # | 假设 | 排除理由 | 强度 |
|---|---|---|---|
| H1 | **从未被写过**（`on_serving` 因某条早返回路径没触发） | §2.1 的 13:17:36 直接读到了文件内容 `537115\n2467590`。另外 §3 证明只要 `arm()` 过了 `on_serving` 就必被 await，而旧实例服务了 22 小时 | 决定性，排除 |
| H2 | `--fd` / systemd 路径绕过了 pidfile | 旧实例命令行是 `--port 4141 --restart`，不含 `--fd`；`serve_inherited` 那条分支要求 `fd is not None`。且 H1 已被正面观测推翻，此假设失去对象 | 排除 |
| H3 | TLS 模式下 `on_serving` 不触发 | 读 `entry.py`：三种 TLS 形态只影响构造哪个 adapter，`on_serving=announce` 的挂载在分支之外，与 TLS 无关 | 排除 |
| H4 | **某个测试跑到了真实路径** | 全仓 + 三棵同伴工作树逐一核对：<br>· `rg 'standalone_pidfile_path\|user_data_path' src tests` —— **没有任何测试引用 `standalone_pidfile_path()`**（探针自证：同一条命令在 `src/` 下正常命中 7 处）。<br>· 唯二构造 `StandaloneOptions` 的测试都显式给了路径：`tests/int/test_standalone_lifecycle.py:523` 用 `pidfile=pidfile`（tmp_path fixture），`tests/int/test_standalone_process.py:65-71` 用 `pidfile=Path(os.environ["PIDFILE"])`，而 `PIDFILE` 由 `tmp_path` fixture 经 `env` 传给子进程。<br>· `tests/unit/lifecycle/test_lifecycle_pidfile.py` 全部 20+ 个用例的路径都是 `tmp_path / "..."`。<br>· 三棵工作树（`260822-complete-not-abandon`、`delivery-keepalive`、`upstream-error-events`）的这三个测试文件与主树 **sha256 完全一致**。<br>· 另有 `tests/unit|int|systemd/conftest.py` 的 autouse fixture 把 `XDG_DATA_HOME` 改到 tmp（08-20 落地，早于本案），是第二道保险 | 排除 |
| H5 | 用户手动 `rm` 掉了 | 未在任何 transcript 中出现，且 bash history 覆盖不到那段时间 —— **这一条严格说是"未证伪"而非"已排除"**。但它已无解释力：§2.2/§2.3 已经给出了两次机制明确、时间点精确、日志齐全的删除，不需要再假设一个人手操作 | 无需援引 |
| H6 | 第三个实例带 `--restart` 顶掉了旧实例 | 若如此，旧实例会收到 SIGUSR2 而排空退出。事实是它一路服务到 08-22 11:50 被用户 SIGINT。两次 uvx 的命令行也确实都没有 `--restart` | 排除 |
| H7 | Birth/目录 mtime 能约束删除时刻 | `write_entry` 是"临时文件 + rename"，每写一次换 inode；目录 mtime 也被后续原子写覆盖。两者都只反映最近一次写入，对"之前有没有存在过"无鉴别力 | 该证据本身无效，已弃用 |

---

## 7. 覆盖缺口（诚实登记）

1. **bash history 断在 08-21 06:27**，之后的交互式命令一概不可见（§2.6）。
2. **12 个 transcript 文件读失败**，全部属于 `copilot-api-js` 的一个已删除 worktree（§2.4），不是本项目的记录。
3. `~/.codex/history.jsonl` 存在但未展开扫描 —— 它是另一个 agent 前端的用户输入历史，不含本项目的 Bash 执行记录；若日后要把"没有第四个删除者"提到"决定性"，这是唯一剩下的补扫面。
4. 本报告没有证明"13:42:45 与 15:41:05 之间不存在别的写入/删除"。这不影响结论：从 13:42:45 起旧实例的记录就已经不在了，后面发生什么都改不了 08-22 11:45 读不到它这件事。

上述任何一条都不动摇 §0 的结论 —— 它的两根支柱（13:17:36 的正面观测、13:42:45 的日志 + 代码路径）各自独立成立。

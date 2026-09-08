# 评审：pidfile 按端口区分 + `--restart` 找不到前任时告警

**日期**：2026-08-22
**评审对象**：工作树未提交改动，限定 8 个文件（`src/app/config/paths.py`、`src/app/lifecycle/pidfile.py`、`src/app/lifecycle/entry.py`、`src/app/cli.py`、`tests/unit/config/test_config_paths.py`、`tests/unit/lifecycle/test_lifecycle_pidfile.py`、`tests/unit/test_cli.py`、`tests/int/test_standalone_process.py`）
**基线 HEAD**：`f191e4d`
**性质**：只读评审。未修改任何文件，未 `git add`/`commit`/`stash`，未启停任何进程，未向 `~/.local/share/` 写入。跑过 ruff、pyright、指定的 pytest 子集，以及三个一次性只读探针。

**结论**：`needs-fix`。**4 条 major，0 条 blocker。** 修法本身（端口入名 + 告警 + 接上 config 键）方向正确、实现基本干净；`live_predecessor` 的等价性、`address[1]` 的取值、回滚路径都经核对无误。问题集中在**告警实际上不响**（major-1，已实测），以及三处「写下的理由与现实对不上」。

> **工具说明**：任务要求使用 `my-skills:as-reviewer` 技能，该技能在本环境的 skill 列表中不存在（`Unknown skill`）。改用 `trusting-a-green-result` 承担鉴别力判断部分。这一条不影响任何发现的成立与否，但请主会话核对技能名。

---

## 0. 验证命令的实际结果

| 命令 | 结果 |
|---|---|
| `uv run ruff check src tests` | `All checks passed!` |
| `uv run pyright src tests` | 21 errors，**全部**位于 `src/app/upstream/stream_cap.py` 与 `tests/unit/upstream/test_stream_cap.py`，与任务说明的既有问题逐条吻合。本次 8 个文件**零报错** |
| `uv run pytest tests/unit/lifecycle tests/unit/config tests/unit/test_cli.py tests/int/test_standalone_process.py -q` | `174 passed in 22.36s` |

绿是真的，但见 major-1 与 major-3：其中两项关键性质的绿不具备鉴别力。

---

## 1. major-1 — `status="warning"` 让这行告警渲染成一条**暗色的 `[....]`**，与「请求刚开始」的例行行完全同形

**严重度**：major　**把握程度**：**决定性**，已端到端实测，不是推断
**位置**：`src/app/lifecycle/entry.py:101-104`

### 事实

`src/app/observability/logging.py:41-49` 的 `_add_status_prefix`：

```python
status = event_dict.get("status")
if isinstance(status, str):
    event_dict["prefix"] = STATUS_PREFIXES.get(status.lower(), "[....]")
    return event_dict          # ← 提前返回，不再回落到 LEVEL_PREFIXES
level = event_dict.get("level")
...
event_dict["prefix"] = LEVEL_PREFIXES.get(severity.lower(), "[....]")
```

`STATUS_PREFIXES`（`logging.py:11-24`）只有 `pending / streaming / draining / ok / success / fail / failure / gone / retry` 九个键，**没有 `warning`**。`warning` 只存在于 `LEVEL_PREFIXES`（`logging.py:30`），而带了 `status` 的记录根本走不到那里。

于是 `status="warning"` → `prefix = "[....]"`，接着在 `_render_text:105` 命中 `body = paint(event, DIM, ...)`——**整行连消息体一起被调暗**；`level` 又在 `:98` 被 pop 掉，所以文本模式里连 "warning" 这个词都不存在，`grep` 也搜不到。

### 实测（通过真实 structlog 链路，非直调 processor）

```
$ PYTHONPATH=src uv run python -c "
from app.observability.logging import setup_logging, get_logger
setup_logging(log_format='text', log_level='INFO', colors=False)
get_logger('app.lifecycle').warning('--restart found no predecessor to take over from: no record at /x.pid; serving as an independent listener', status='warning')
get_logger('app.lifecycle').warning('SAME LINE WITHOUT the status kwarg')
get_logger('app.lifecycle').info('a routine pending line', status='pending')
"
[....] 13:06:51 --restart found no predecessor to take over from: no record at /x.pid; serving as an independent listener
[WARN] 13:06:51 SAME LINE WITHOUT the status kwarg
[....] 13:06:51 a routine pending line
```

开色时第一行是 `\x1b[2m[....]\x1b[0m ... \x1b[2m<整条消息>\x1b[0m`（DIM），与第三行同色同前缀。

### 为什么这是 major

这次改动的**全部价值**就是「把一个静默失败变成响一声」。当前实现把它渲染得**比一条普通请求行还不起眼**，落在启动瞬间的一堆 uvicorn/lifecycle 行里，操作者不会注意到。`logging.py:25` 那段注释恰好把这个失效形态写清楚了——「第三方 ERROR 不只是难找，是根本 unfindable」——这次改动踩的是同一个坑，只是方向反了一步（主动传了个不被识别的 `status`）。

它还连累 finding-5：不做兼容层的理由第一条是「告警现在会明确响一声」，而这个前提当前不成立。

### 修法（二选一，我倾向第一个）

1. **删掉 `status="warning"`**，只留 `.warning(...)`。`add_log_level` 会填 `level="warning"` → `LEVEL_PREFIXES["warning"] = "[WARN]"` → `PREFIX_COLOURS["[WARN]"] = YELLOW`。一行删除，落在本次评审范围内的文件里，不动 `logging.py`。JSON 模式仍有 `level: "warning"`，无损。
2. 若确实想让它带一个自命名的 status，就得在 `logging.py:11-24` 的 `STATUS_PREFIXES` 里补 `"warning": "[WARN]"`。但那属于本次范围外的文件，且 `logging.py:45` 的注释明说「status 优先于 level」是刻意设计，为一条日志新增一个与 level 同名的 status 收益不大。

### 顺带：这个 API 有个陷阱，值得记一笔（不是本次的锅）

`rg -no 'status="[a-z]+"' src/` 得到实际在用的取值是：`completed / draining / fail / failed / incomplete / ok / pending / retry / streaming / warning`。其中 **`completed`、`failed`、`incomplete`、`warning` 四个都不在 `STATUS_PREFIXES` 里**，全部静默降级成 `[....]`。`_add_status_prefix` 对未知 status 走 `.get(..., "[....]")`，既不报错也不回落 level——**拼错一个 status 的代价是这行日志变成暗色 pending，而且没有任何东西会告诉你**。这条超出本次评审范围，只作为交给主会话的观察项登记（其余三个的实际影响需另行核对，我没查）。

---

## 2. major-2 — `pidfile_path` docstring 给出的两条理由，在生产入口上**一条都到不了**

**严重度**：major（针对注释准确性；代码本身无害）　**把握程度**：高，基于 grep 全量与逐行读码
**位置**：`src/app/lifecycle/entry.py:51-56`（docstring）、`entry.py:93`（同源注释）

新 docstring 写：

> The port is a parameter rather than read off `self.port` because that field is a request, not an outcome: `--fd` inherits a listener whose port it never names, and port 0 asks the kernel to choose.

两条理由逐条核对：

**`--fd`**：CLI 的 `--fd` 分支在 `src/app/cli.py:268-289` **提前 `return`**，走的是 `serve_inherited`（`cli.py:128-146`），它直接构造 `uvicorn.Server(uvicorn.Config(..., fd=fd, ...))`，**完全不经过 `run_standalone`、不经过 `StandaloneOptions`、不写 pidfile**。函数自己的 docstring 就写着「Not `run_standalone`」。

`StandaloneOptions.fd` 这个字段在整个 `src/` + `tests/` 里**没有任何一处被赋非 None 值**：

```
$ rg -n 'run_standalone|adopt_listener|options\.fd|StandaloneOptions' src/ tests/
```

唯一的 `fd=` 出现在 `cli.py:140`，那是 `uvicorn.Config(fd=fd)`，不是 `StandaloneOptions`。`tests/unit/test_cli.py:209` 反而有一条 `assert options.fd is None`。也就是说 `entry.py:87 adopt_listener(options.fd)` 这条分支目前是**死代码**。

**port 0**：`--port` 的 typer 声明是 `typer.Option("--port", "-p", min=1, max=65535)`（`cli.py:210`），配置侧 `server.port` 是 `Field(default=4142, ge=1, le=65535)`（`config/schema.py:70`）。`rg -n 'port=0|"--port", "0"' tests/` 零命中。**两条路都到不了 0。**

### 判断

把解析点移到 bind 之后**本身是对的**——从 `getsockname()` 读回来的端口严格强于配置里请求的端口，代价为零，将来接 `--fd` 或 port 0 时不用回头改。我不建议改回去。

问题在于：这个项目的注释是设计记录，而这一条把两个**当前不可达**的路径写成了既成事实。下一个读者会据此相信 `--fd` 走这里，进而在错误的位置排查。按 `sync-live-docs-timely` 与本项目「注释解释为什么」的约定，应改写成实际成立的说法，例如：

> 端口取自 bind 后读回的地址而非 `self.port`：后者是请求，前者是结果。今天两者恒等（`--port` 与 `server.port` 都被约束在 1..65535，且 `--fd` 走 `serve_inherited`、根本不到这里），但把文件名钉在真实 endpoint 上是唯一在这些约束松动后仍然正确的写法。

`entry.py:93` 那条行内注释同理。

### 同一条链上的另一处静默失败（point 7）

`--fd` 分支在 `cli.py:288` 提前 return，**跳过了 `cli.py:305-308` 那个 `for option, reason in inactive` 的告警循环**。后果：

- `ghc-api-proxy start --fd 3 --restart` —— `--restart` 被完整接受、完全忽略、**一个字都不说**；
- `--fd 3 --pidfile /x` —— 同样；
- `--fd 3 --manual` 等本来有 inactive 提示的选项，在这条路上也一并静默。

这正是 `cli.py:306-307` 那条注释所反对的形态（「一个被接受然后被忽略的选项比一个被拒绝的更糟，因为没有任何东西能把它和生效区分开」），也正是本次改动为 `--restart` 修的那一类。**属于 point 7 要求的「同一条链上未被发现的其它断点」，且是三者里最具体的一个。** 不属于本次范围，建议登记为后续小切片（一条 `typer.BadParameter` 或一条 inactive 告警即可）。

---

## 3. major-3 — 端到端测试里表达该性质的那条断言是**恒真的**，鉴别力被托付给了一个 20 秒超时

**严重度**：major　**把握程度**：高（静态判定，且与实施者自己观测到的变异结果完全吻合）
**位置**：`tests/int/test_standalone_process.py:424-456`

### 问题

测试自己拼出了期望路径：

```python
incumbent_pidfile = data_home / "ghc-api-proxy" / f"standalone-{incumbent_port}.pid"
throwaway_pidfile = data_home / "ghc-api-proxy" / f"standalone-{throwaway_port}.pid"
```

于是第 443 行的

```python
assert incumbent_pidfile != throwaway_pidfile
```

比较的是**测试自己**用两个不同端口号格式化出来的两个字符串。只要 `incumbent_port != throwaway_port`，它就必然成立——**任何生产代码的变异都无法让它变红**。这是同源 oracle 的一个变体：测试复制了一份命名规则，然后断言自己那份复制品是自洽的。

这解释了实施者观测到的现象。把 `standalone_pidfile_path` 改回共享名之后，生产代码去写 `standalone.pid`，而测试仍在等 `standalone-<port>.pid`，两个文件都永远不出现 → 红在 `wait_until_serving` 的 `AssertionError(f"child never started serving: {pidfile}")`。**这句话是假的**——子进程起来了、也在服务，只是把记录写到了别处。下一个人拿着这条红去查启动失败，会查错方向。

### 修法

用生产函数导出期望路径，让测试断言**性质**而非**拼写**：

```python
monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
incumbent_pidfile = standalone_pidfile_path(incumbent_port)
throwaway_pidfile = standalone_pidfile_path(throwaway_port)
```

（`standalone_pidfile_path` 从 `app.config.paths` 导入；`user_data_path()` 每次调用都重读环境变量，所以 `monkeypatch.setenv` 就够，且子进程本来就从 `os.environ` 复制，`data_home=data_home` 那条也仍然成立。）

改完之后，同一个「改回共享名」的变异会走成：两个路径**相等** → `wait_until_serving(incumbent_pidfile)` 正常返回 → throwaway 起来并覆写 → **第 443 行精确变红**。即使把第 443 行删掉，第 449 行 `assert throwaway_pidfile.exists() is False` 与第 453 行 `surviving.pid == incumbent_pid` 也各自会红。三重击发，且每一处的失败消息都说的是真话。

拼写本身已经由 `tests/unit/config/test_config_paths.py:117-118` 的 `test_the_pidfile_is_named_after_the_port` 单独钉住，两层职责分得很干净——这一点是对的，只是集成层没有用上它。

**顺带**：`test_two_ports_do_not_share_one_pidfile`（`test_config_paths.py:121-127`）**是**有鉴别力的（改回共享名它会红），这条没问题。

---

## 4. major-4 — 用户亲笔文档现在说的默认路径是错的，需要交回用户

**严重度**：major（对外契约漂移）　**把握程度**：决定性
**位置**：`docs/.human-controlled/config.example.yaml:228 / 231 / 235`

```
# 默认是 $XDG_DATA_HOME/ghc-api-proxy/standalone.pid。
# Defaults to $XDG_DATA_HOME/ghc-api-proxy/standalone.pid when unset.
# pidfile: "/run/ghc-api-proxy/standalone.pid"
```

改动之后实际默认是 `$XDG_DATA_HOME/ghc-api-proxy/standalone-<port>.pid`。前两行现在是**假的**，第三行只是示例值、无所谓。

按项目记忆 `human-controlled-docs-are-final-authority`，`docs/.human-controlled/` 由用户亲笔、压过一切推导产物，**实施者不得修改**。所以这一条的处置不是「改掉」，而是**必须显式交回用户裁决**：要么用户更新这两行，要么用户否决端口入名的裁决。在用户更新之前，代码与人写权威文档处于公开矛盾状态。

另外，该文件当前处于暂存区（`git status` 显示 `AM`），是同伴在途的改动之一，更需要用户自己动手而不是任何 agent 顺手改。

CLI `--pidfile` 的帮助文本（`cli.py:231`）没有描述默认值，不受影响。`docs/.human-controlled/lifecycle.md`、`cli.md`、`release-and-deployment.md` 全部零命中（`rg -i 'pidfile|\.pid'`），无其它漂移点。

---

## 5. minor-1 — 「has since exited or been replaced」也覆盖了「读不到 `/proc`」，那种情况下前任可能还活着

**严重度**：minor　**把握程度**：中（机制确定；现实触发概率我判断很低，未实测）
**位置**：`src/app/lifecycle/pidfile.py:150-154`

`process_start_token()`（`pidfile.py:48-58`）在 `OSError` 时返回**空字符串**。进入第 150 行时 `entry.start_token` 已被上一分支保证非空，所以「`/proc/<pid>/stat` 读不到」与「token 真的对不上」**走同一条分支**，都输出：

> the record at <path> names pid <pid>, which has since exited or been replaced

前者的实情是「我们无法核实」，而非「它已经不在了」。给操作者的这句话把一个未经核实的判断陈述成了事实——恰好是这次改动整体上在反对的那种事。

现实触发面很窄：Linux 上 `/proc/<pid>/stat` 是 world-readable，跨用户也读得到；PID namespace 隔离或 `hidepid=2` 才会命中。**我不认为这需要独立的防御性检查**，只建议把措辞改成不越界的说法，例如「no longer matches the process holding that pid」。

---

## 6. minor-2 — 缺两条负控：告警在**不该响**的时候到底响不响，没有任何东西钉住

**严重度**：minor　**把握程度**：高
**位置**：`tests/int/test_standalone_process.py:386`、`:348`

代码上告警被 `if options.restart:`（`entry.py:96`）挡着，所以**不会**在没带 `--restart` 时响——这一点我读码确认了，回答任务的 point 3。但这是「读出来的」，没有任何测试钉住它。整套新测试全是正向的：只断言该响的时候响了。

两处各加一行即可，成本近乎为零，且正好补上矩阵里对称的那一格：

- `test_a_start_without_restart_leaves_the_incumbent_alone`（:386）→ 加 `assert "found no predecessor" not in said`
- `test_a_replacement_takes_the_port_and_retires_its_predecessor`（:348，真实接管的 happy path）→ 同上。这一条更值：它证明「找到了前任时不会误报」，而误报会训练操作者忽略这行。

（这不是「补覆盖率」，是补一个具体的失效面：一条只会响不会闭嘴的告警等于没有告警。）

---

## 7. minor-3 — 集成测试断言的是消息子串，因此 major-1 从它底下整个穿了过去

**严重度**：minor（作为测试鉴别力问题；它导致的那个缺陷本身是 major-1）　**把握程度**：决定性
**位置**：`tests/int/test_standalone_process.py:418-420`

```python
assert "found no predecessor" in said, said
assert "no record" in said, said
```

子串匹配对前缀、颜色、级别一概不敏感，所以一条渲染成暗色 `[....]` 的告警照样让它变绿。**这就是 major-1 得以在全绿套件下存活的原因**，属于 `trusting-a-green-result` 里「判据不覆盖真正要紧的那条性质」的标准形态。

修 major-1 的同时补一句即可：

```python
assert "[WARN]" in said, said
```

子进程已经 `setup_logging(log_format="text", ...)`，`[WARN]` 是文本模式下这行必然携带的前缀（`logging.py:30` + `PREFIX_COLOURS`），`colors` 由 `detect_terminal()` 决定而管道下为 False，所以不会有 ANSI 序列插在中间。这一条断言恰好会在 `status="warning"` 存在时变红——即它对 major-1 有鉴别力。

---

## 8. nit

- **nit-1**：`test_a_run_on_another_port_leaves_the_incumbent_its_record` 连调两次 `free_port()`（:428-429）。两次各自 bind 端口 0 后立刻 close，内核理论上可以返回同一个端口，届时该测试会以一种极难读的方式失败。既有测试也是这个写法，不是本次引入；若顺手，加一句 `assert incumbent_port != throwaway_port` 就闭合了（且这句**不是**恒真的，它约束的是 fixture 而非生产代码）。
- **nit-2**：`look_up_predecessor` 里 `path.exists()` 为 False 时报 "no record"，但父目录权限不足同样得到 False。注释已经声明了「`exists` 只在塑造一行日志，这里的竞态代价是一个词而不是一个决定」，把这层也一并涵盖了，**我认为不必改**，仅登记。
- **nit-3**：`child_script()` 里新增的 `setup_logging(...)`（`test_standalone_process.py:36-38`）对该文件全部 12 个测试生效，而只有 1 个读日志。我判断这是**改进**而非违反「不同目标的测试组各自准备环境」——真实 CLI 入口本来就调 `setup_logging`，加上它让子进程更像生产。不建议改。

---

## 9. 逐条回答任务里的 7 个问题

### Q1 — pidfile 解析推迟到 bind 之后，回滚路径与早期返回

**回滚路径正确，未发现问题。**

`pidfile`（`entry.py:94`）与 `predecessor`（:95-98）都在 `announce` 闭包被**定义**之前完成绑定，而 `announced` 只可能在 `announce()` 体内被置 True。因此 `except BaseException` 分支（:151-160）里 `announced is True` 严格蕴含 `pidfile` 与 `predecessor` 都是已定值，且是 `write_pidfile` 当时用的那一个。`write_entry(pidfile, predecessor)` 把前任原样写回、`remove_pidfile(pidfile)` 删自己，两条都仍然指向正确的文件。

没有任何早期返回或异常路径会「跳过 pidfile 逻辑但仍然开始服务」：`bind_listener` / `adopt_listener` 抛出时整个函数向外传播，服务从未开始；:94-104 之间没有 return，也没有可捕获的分支。

一处理论上的次要回归，**我判断不构成发现**：改动前 `live_predecessor` 在 bind 之前调用，改动后在之后，所以若查找抛异常，已经 bind 的 listener 会泄漏。但 `look_up_predecessor` 不会抛——`read_pidfile` 吞掉 `OSError`，`process_start_token` 吞掉 `OSError`，`Path.exists()` 按 CPython 文档不抛 `OSError`。而且这条路上早已有同形泄漏（:110 与 :123 的 `raise ValueError("TLS mode requires certificate material")`），是既有的，未被本次触碰。

### Q2 — `look_up_predecessor` 与 `live_predecessor` 的关系

**设计意图达成，且逐条等价。** 判断只存在于 `look_up_predecessor` 一处，`live_predecessor` 是 `return look_up_predecessor(path).entry`，不含任何自己的判断，不存在漂移空间。

分支对照（旧 `entry.py` HEAD 版 vs 新 `pidfile.py:133-155`）：

| 条件 | 旧返回 | 新 `.entry` | 等价 |
|---|---|---|---|
| `read_pidfile` → None | None | None | ✅ |
| `entry.pid == os.getpid()` | None | None | ✅ |
| `not entry.start_token` | None | None | ✅ |
| `start_token != process_start_token(pid)` | None | None | ✅ |
| 其余 | `entry` | `entry` | ✅ |

顺序也逐条一致（旧版把前两个条件合并在一个 `or` 里，新版拆成两个 `if`，短路语义相同）。**唯一的行为差异**：`entry is None` 时新增一次 `path.exists()` 的 stat 调用，只影响 `reason` 字符串，不影响返回值。`tests/unit/lifecycle/test_lifecycle_pidfile.py` 里既有的 `live_predecessor` 分支测试全部保留且通过（174 passed 中包含它们）。

### Q3 — 告警本身

- **文案**：好。「发生了什么」（`--restart found no predecessor to take over from: <reason>`）与「后果是什么」（`serving as an independent listener`）都说到了，`reason` 还带上具体路径和 pid。四种 reason 各自有单测钉住（`test_lifecycle_pidfile.py:131-176`）。
- **`status="warning"` 不是日志层认识的取值** —— 见 **major-1**，实测确认渲染成暗色 `[....]`。
- **不该响的时候会不会响**：不会。`if options.restart:`（`entry.py:96`）是唯一入口。但没有测试钉住 —— 见 **minor-2**。

### Q4 — `address[1]` 取的是不是端口

**是，IPv6 也不会取错。**

`address` 来自 `listeners.identities()[0].address`，类型是 `ListenerIdentity.address: tuple[str, int]`（`src/app/lifecycle/activation.py:27`）。这个二元组**不是** `getsockname()` 的原始返回，而是 `bind_listener`（`listener.py:96-101`）和 `adopt_listener`（`listener.py:64-69`）各自用 `ExpectedListener(host=str(bound[0]), port=int(bound[1]))` 规范化出来的。IPv6 的 4 元组在这一步就被截成 `(host, port)`，`[1]` 恒为端口。`_resolve`（`listener.py:33-50`）同样只取 `address[0:2]`。

（AF_UNIX 经 `--fd` 继承会让 `getsockname()` 返回 str，`int(bound[1])` 抛 `ValueError` —— 但那在 `adopt_listener` 里今天就已经是这样，属既有行为，且 `--fd` 根本到不了这段代码，见 major-2。）

### Q5 — 不做向后兼容回退层，是否可接受

**可接受。而且我实测到一个把它从「可接受」推到「明显正确」的事实。**

现场状态（只读观测，2026-08-22 13:0x）：

```
$ ps aux | rg ghc-api-proxy
xp 2254087 ... /home/xp/src/ghc-api-proxy-py/.venv/bin/ghc-api-proxy start --port 4141 --restart   （11:45 起，仍在跑）

$ ls -la ~/.local/share/ghc-api-proxy/
config.yaml  github_token  history.db  history.db-shm  history.db-wal  requests/  tokenization.json
```

**`standalone.pid` 现在已经不存在了。** 取证报告记录 2254087 在 11:45:44 写出过它（inode Birth 有据），而现在没有。也就是说这个缺陷**在取证报告写完之后又击发了一次**，同一天之内。

（我确认这不是我造成的：`tests/unit/conftest.py:18` 与 `tests/int/conftest.py:18` 都有 autouse 的 `monkeypatch.setenv("XDG_DATA_HOME", tmp)`，`start_child` 从已被 patch 的 `os.environ` 复制；且工作树版本的默认名是 `standalone-<port>.pid`，写不出也删不掉 `standalone.pid`；再者 `remove_pidfile` 只在文件记着自己的 pid 时才 unlink，我的任何进程都不可能记成 2254087。至于是谁删的——最可能是某个同伴会话跑了一次 HEAD 版本的 `start`，但我没有取证到具体那一次，**这一句是推测，不要当结论用**。）

对兼容层决定的意义：**一个读 `standalone.pid` 的过渡层今天读到的是「不存在」**，与不加它的结果完全相同。它换不来任何东西，却会成为一份没人负责删除的永久残留。实施者的四条理由里，「旧文件会被那个旧实例自己退出时删掉」这条其实已经提前发生了。

**唯一的附加条件**：不做兼容层的理由第一条是「告警现在会明确响一声」，而按 major-1 它当前不响。**这个决定的成立以 major-1 被修复为前提。** 两者一起交付即可。

我找不到一个需要兼容层的失效场景。最坏情况是：用户在 major-1 修好之前拿新版本对 2254087 做一次 `--restart` —— 那会得到两个进程同时服务 4141，且告警是暗的。但那个坏结果**与命名无关**（记录本来就已经不在了），加不加兼容层都一样。

### Q6 — 测试鉴别力

- **变异 (a) 的鉴别力不足** —— 见 **major-3**。它确实会红，但红在一个说假话的超时上，而唯一表达该性质的断言是恒真的。给出了具体修法，修完之后同一变异会在正确的行上三重击发。
- **变异 (b)（删告警 → 精确红在断言行）成立**，但那条断言本身太宽 —— 见 **minor-3**：它对「告警存在」有鉴别力，对「告警可被看见」没有，而后者正是本次真实缺陷所在。
- **该覆盖没覆盖的格子**：
  1. 告警的**可见性**（前缀 / 级别）—— minor-3，这是最重要的一格，因为它正是漏掉 major-1 的原因；
  2. 两条**负控**（没带 `--restart` 时不响；找到真前任时不响）—— minor-2；
  3. `pidfile_path(port)` 取的是**实际绑定端口**而非 `options.port` —— 目前无任何测试，且因 major-2 在生产上不可达，两者恒等。**我不建议为此补测试**：那会去钉一条今天没有生产入口的路径，属于给不可达分支建证明。正确的动作是把 docstring 改准（major-2），而不是加测试。

### Q7 — 同一条链上其它未被发现的断点

1. **`--fd` 分支静默吞掉 `--restart` / `--pidfile` / `--manual` 等**（`cli.py:288` 提前 return，跳过 `cli.py:305-308` 的 inactive 告警循环）。与本次修的是同一类失效，且 `cli.py:306-307` 的注释已经把这类失效判为不可接受。**详见 major-2 末节。** 建议单独切片。
2. **同端口的临时实例仍然会顶掉并删掉生产记录。** 端口入名解决的是「换个端口的临时实例」，但 `announce()`（`entry.py:134-140`）里的 `write_pidfile` 依然是无条件覆盖，不看原内容记的是不是另一个活进程。所以 `ghc-api-proxy start --port 4141`（不带 `--restart`，比如手滑重开一个）依旧完整复现取证报告 §5 的全过程。这是取证报告列出的三个候选方向里未被采纳的那一个（「让 `write_pidfile` 在覆盖一个记录着另一个活进程的文件时拒绝/告警」），**用户只裁决了两条修法，这一条按 `no-silently-cut-but-defer` 登记，交由用户裁决**。现在实现它的成本比之前低——`look_up_predecessor` 已经就位，在 `announce()` 里对非 `--restart` 的启动做一次同样的查找并告警，就是对称的另一半。
3. **`remove_pidfile` 的守卫本身没有问题**，我核对过正常接管序列：A 在 4141，B 带 `--restart` 起来 → B 写入记录（记 B）→ signal A → A 排空退出 → A 的 `remove_pidfile` 读到 B 的 pid ≠ 自己 → 返回 False 不删。正确。

---

## 10. 我明确**没有**发现问题的地方

- `cli.py:309-312` 的 `--pidfile` > config 优先级：正确，`proxy_config.pidfile` 默认是空串（`schema.py:384`），falsy 判断得当；三条新单测（`test_cli.py:344-385`）覆盖了 config 生效 / CLI 压过 config / 都不给时保持 `None` 三格，其中第三条（`pidfile is None`）是有价值的——它钉住了「不在 CLI 层提前解析路径」这个约束。
- `PredecessorLookup` 作为返回类型：`reason: str = ""` 的空串约定由 `test_a_found_predecessor_carries_no_reason` 显式钉住（含注释说明它是正控），做得好。
- `pidfile.py` 新增代码的注释风格与周围一致，讲的都是「为什么这么做、不这么做会怎样」。
- **无硬折行违规**：新增/修改的长注释与 docstring 全部单行成句（`paths.py:31-35`、`entry.py:54`、`entry.py:93`、`entry.py:100`、`cli.py:309`、`pidfile.py:125-126`、`pidfile.py:136`，以及测试里的几处），符合 `no-hard-wrap`。既有的硬折行（如 `entry.py:74-84`、`pidfile.py` 模块 docstring）未被本次触碰，按约定不计。
- ruff / pyright 对这 8 个文件零报错。

---

## 11. 建议的落地顺序

1. **删 `entry.py:103` 的 `status="warning"`**（major-1）—— 一行，收益最大。
2. **改准 `entry.py:51-56` 与 `:93` 的注释**（major-2）。
3. **`test_standalone_process.py:428-429` 改用 `standalone_pidfile_path` 导出期望路径**（major-3），并在 `:418-420` 加 `assert "[WARN]" in said`（minor-3）。
4. **把 `config.example.yaml` 的默认路径描述交给用户更新**（major-4）—— 不要自己动手。
5. minor-1 / minor-2 顺手；nit 可不动。
6. 登记两条 deferred 交用户裁决：`--fd` 分支的静默忽略、同端口临时实例仍会顶掉记录。

修完 1-3 之后需要重跑的是 `tests/int/test_standalone_process.py` 与 `tests/unit/lifecycle`；改动都很小，不需要重新全量评审。

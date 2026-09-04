# 评审：`pidfile_dir` 改名 / 拒绝覆盖活记录 / `--fd` 冲突报错（第二批）

评审人 Opus，2026-08-22。只读评审，未修改主树任何文件。

## 评审对象与快照

主树 `HEAD = 80068eb`（评审开始时是 `8b71266`，期间同伴提交了两次，均与本批无关）。工作树未提交改动，只评 8 个文件。

**实施者在我评审期间仍在编辑这些文件**，我读到过两个不同版本。为了让结论可核对，我把评审时刻（2026-08-22T15:18:04+00:00）的 8 个文件快照到 `/tmp/review-snapshot-b2/`，下文所有行号与结论都针对这份快照：

| 文件 | sha256（前 12 位） |
|---|---|
| `src/app/config/schema.py` | `eb4e78d84ea3` |
| `src/app/config/paths.py` | `32bd190a6c61` |
| `src/app/lifecycle/entry.py` | `a7f7dbf83600` |
| `src/app/cli.py` | `982aff0d9c2a` |
| `tests/int/test_standalone_process.py` | `9bf3e9b53fae` |
| `tests/int/test_standalone_lifecycle.py` | `0b551c3e932a` |
| `tests/unit/test_cli.py` | `dc8c9c89178406` |
| `tests/unit/config/test_config_paths.py` | `9419165c25c9` |

如果这些哈希与当前工作树不符，请先核对差异再采纳本报告。

**两条派发时给我的前提，在我读到的最终快照上已经不成立**，实施者自己先修掉了：

1. 「`--manual`、`--graceful-timeout` 等选项在 `--fd` 路径上同样被静默忽略（inactive 播报循环仍被跳过）」——`cli.py` 已重构：`--fd` 分支从第 266 行前移到第 284 行，**排在 inactive 播报循环之后**，`_load_spec_config` 只调用一次。`--manual` / `--rate-limit` / `--github-token` 现在在 `--fd` 路径上也会告警，且有 `test_fd_still_reports_the_options_the_config_cannot_carry` 三个参数化用例钉住。
2. 「陈旧记录不会被挡」无测试——已补 `test_a_record_whose_process_has_gone_does_not_block_a_start` 与 `test_a_record_whose_pid_was_recycled_does_not_block_a_start`。

我对这两条都做了独立变异验证，结果在下文「我自己跑的验证」。

## 结论

**0 blocker，1 major，6 minor，4 nit。** 另有 2 条越界观察（不属于本批，供登记）。

本批的三条裁决都落地了，语义边界正确。major 那条不是逻辑错误，是这条拒绝的操作者可见面：它以 Python traceback 的形式出现，而这条拒绝的全部价值在于那句可读的指示。

---

## 逐条发现

### M-1（major，把握：机制确定，处置属于取舍）拒绝以 traceback 的形式呈现给操作者

`entry.py:113` 抛出的 `PidfileError`（`RuntimeError` 子类）一路穿过 `_serve_pipeline` → `anyio.run` → click，**中途无人捕获**（我 grep 过 `cli.py` 与 `__main__.py`，无任何 `except`；click 的 `standalone_mode` 只处理 `ClickException` / `Abort`）。所以操作者看到的是解释器默认的完整 traceback，退出码 1。

对照同一个函数里 `--fd` 冲突走的是 `typer.BadParameter`：一行干净的错误，退出码 2。

为什么这条比 `ListenerBindError` 更值得处理：那些是「起不来」，这条是**日常会撞上的操作失误**（重复 `start` 正是最常见的一种），而且它携带的信息是**指示性的**——「pass --restart to take over from it, or --force-write-pidfile to claim the record anyway」。把一句指示埋在十几行栈帧里，等于要求操作者先判断这是不是崩溃。整批改动的立论就是「一件事发生了要看得见」，这里它看得见但看起来像事故。

测试对此是盲的：`test_a_start_without_restart_refuses_to_erase_the_incumbents_record:454` 把 `stdout + stderr` 拼起来做子串断言，traceback 与干净消息在这个断言下同形。（我在自己的变异跑里实际看到过输出，形如 `STARTING\nTraceback (most recent call last):\n  File "<string>", line 55, ...` 后面才是那句消息。）

建议（小改，局部）：在 `start` 里把这一次调用包起来，`except PidfileError as error: raise typer.BadParameter(str(error)) from error`，或用 `click.ClickException`。若采纳，顺手把上面那条测试加一句 `assert "Traceback" not in said`，否则改完仍然没有东西钉住它。

我接受另一种处置：判为「与既有启动期错误一致，单独立项统一处理」。那样请写进未采纳表，理由不要写成「不重要」——它只是与既有缺陷同形而已。

### m-1（minor，把握：事实确定，可达性窄）活着但无法验证身份的记录会被静默覆盖

拒绝的判据是 `lookup.entry is not None`（`entry.py:109`），而 `look_up_predecessor` 在两种情况下对一个**仍在运行**的进程返回 `entry=None`：

- 记录只有一行 PID、没有身份令牌 → reason 是 `names pid N but carries no identity to verify`；
- `/proc/<pid>/stat` 读不到 → reason 是 `no longer matches the process holding that pid`（`pidfile.py:151` 的注释本身就承认这句覆盖了「读不到」）。

我实测确认了第一种（探针 `/tmp/review-pidfile-copy-a1/probe_unverifiable.py`，对一个活着的子进程写入 `PidfileEntry(pid=holder.pid, start_token="")`）：

```
holder alive: True
lookup.entry: None
lookup.reason: the record at .../standalone-4141.pid names pid 2719589 but carries no identity to verify
=> refusal fires? False
```

于是这一支上「记录指着一个活进程」和「记录是垃圾」走同一条路：直接覆盖，一声不吭。这正是本批要堵的那类事件。

**我没有把它判为 major，因为可达性确实窄**：`write_pidfile` 总是调 `process_start_token(os.getpid())`，在 Linux 上读自己的 `/proc` 不会失败，所以无令牌记录基本只能来自手写文件或非 Linux 平台；令牌读不到则要 `hidepid=1/2` 或命名空间隔离。`config.example.yaml` 建议的 `/run/ghc-api-proxy` 共享目录让跨用户场景不算臆想，但普通 Linux 的 `/proc/<pid>/stat` 对所有用户可读，所以那不足以触发。

建议**告警而不是拒绝**：拒绝会在没有 `/proc` 的平台上把每一次启动都挡住（那些平台上 `signal_restart` 本来就直接抛 `smooth restart needs pidfd support`，但那是 `--restart` 才走的路，普通 `start` 不该被牵连）。一行就够，`lookup.reason` 已经把话说全了，现在只是在这一支上没被用：

```python
elif lookup.reason and read_pidfile(pidfile) is not None:
    get_logger(LIFECYCLE_LOGGER).warning(f"claiming {pidfile}: {lookup.reason}")
```

（形式仅示意；关键是「记录存在但判不出所以放行」这件事要留下一行。）若判为不值得，请写进未采纳表并注明可达性是理由。

### m-2（minor，把握高）`entry.py` 里没有一句话交代检查与写入之间的窗口

派发提示说「实施者在注释里明确承认了」——**代码注释里没有**。我 grep 过 `entry.py` 的 `window|race|between the|TOCTOU|serial`，唯一命中是第 152 行，讲的是 `signal_restart` 与查找之间的另一个窗口。承认写在 `.dev/docs/graceful-shutdown/restart-handover/README.md:56`。

取舍本身我认为**可以接受**：`look_up_predecessor` 在 bind 之后、`write_pidfile` 在 `on_serving` 里，中间隔着适配器构造和 uvicorn 起服务，是毫秒到几十毫秒量级。它挡的是「操作者手滑再敲一次」这种顺序场景，那个量级远大于窗口。真正的原子所有权要进程间串行化，已作为遗留登记，我不要求实现。

但这个项目自己的规矩是「注释是设计记录」，而且上一轮评审刚因为一句 docstring 把不可达路径写成既成事实而要求改写。这里是**遗漏**而不是错话，性质轻一档，可代价是一样的：只读 `entry.py:109-116` 的人会把这条拒绝读成所有权保证。第 110 行那段注释花了整段讲「为什么拒绝」，正好缺一句讲「它挡不住什么」。

建议在第 110-111 行之间补一句，大意：这条拒绝挡的是先后发生的两次启动；两个同时启动的进程可以都看到空记录并各自写入，这里没有做 compare-and-swap，真正的原子所有权需要进程间串行化。（一行，不折行。）

### m-3（minor，把握：实测）`listeners.close()` 的注释把理由说反了一半

第 111 行现在写的是：「letting the exception carry it out of scope would leave the port held by a process that is about to exit」。

「about to exit」这半句站不住：一个马上要退出的进程，内核会在退出时回收全部 fd，什么都不做也会释放。我实测过（探针 `/tmp/review-pidfile-copy-a1/probe_close.py`，异常出了 `except` 块之后再 bind）：**删掉 `listeners.close()`，端口照样释放**——CPython 引用计数在 `run_standalone` 帧销毁时就关掉了 socket。

真正的机制是另一回事，我用第二个探针（`probe_close2.py`，把 bind 挪进 `except` 块内、异常仍然活着的时候）分出了差别：

| entry.py | 结果 |
|---|---|
| 有 `listeners.close()` | `PORT RELEASED: bind succeeded` |
| 删掉 `listeners.close()` | `PORT STILL HELD: [Errno 98] Address already in use` |

所以 `close()` 是**必要的**，理由是：异常的 `__traceback__` 引着 `run_standalone` 的帧，帧引着 `listeners`，只要调用方还持有这个异常（记日志、重试、pytest 抓着 `ExceptionInfo`），作用域退出就不会释放。用一个不带 `SO_REUSEPORT` 的普通 socket 去 bind 是能分出这件事的判据（有 `SO_REUSEPORT` 就分不出，因为它本来就允许共存）。

`close()` 本身是正确的释放方式：`ActivatedSocketSet.close()`（`activation.py:150`）把 `_masters` 置空并逐个 `socket.close()`，此刻还没有 `duplicate_for_accept()`，所以 master 就是全部。之后没有任何代码再碰 `listeners`。

建议把注释换成实测出来的说法，例如：监听器在此已经绑定，而抛出的异常会通过它的 traceback 一直引着这一帧和帧里的 `listeners`，所以只靠作用域退出并不释放——调用方多持有这个异常一会儿，端口就多被占一会儿。

**bind 之后还有哪些路径抛出却不关**（回答重点项 2）：除实施者已知的两处 `raise ValueError`（第 122、135 行）外，还有 `build_server_ssl_context(material)`（第 139 行，材料坏掉会抛）、`Config(...)` 与 `UvicornListenerAdapter(...)` 的构造（第 123-131、136-140 行）、以及 `on_observable(adapter.connection_count)`（第 145 行，回调是外部传入的）。全部是既有同形，本批没有新增第二处——新增的这一处自己关了。若要一次性收拾，`listeners` 从 bind 到交给 `StandaloneServer` 之间用一个 `try/except BaseException: listeners.close(); raise` 包起来即可，那是一处改动覆盖全部；是否做交给用户，我不主张在本批做。

### m-4（minor，把握高）`listeners.close()` 没有任何测试钉住

我删掉这一行跑了 `tests/int/test_standalone_process.py`、`test_standalone_lifecycle.py`、`tests/unit/test_cli.py`、`tests/unit/lifecycle`，**137 passed，全绿**。

这不是疏忽，是结构性的：集成测试里被拒绝的是子进程，子进程退出时内核回收 fd，泄漏从外面根本看不见。唯一能看见它的位置是进程内调用面，而那正是 `close()` 唯一起作用的场景（m-3）。

建议在 `tests/int/test_standalone_lifecycle.py` 加一个进程内测试，形状就是我的 `probe_close2.py`：起一个长活的占位进程 → `write_pidfile(standalone_pidfile_path(port, tmp_path), holder.pid)` → `pytest.raises(PidfileError)` → **在 `with` 块内**（异常还活着）用一个不带 `SO_REUSEPORT` 的普通 socket bind 同一端口 → 断言成功。我已验证它对「删掉 `listeners.close()`」精确变红（Errno 98）。这不是新建证明设施，是补一格现有测试文件里的用例。

### m-5（minor，把握高）`test_fd_refuses_the_lifecycle_options_it_cannot_honour` 的 docstring 描述的是已经不存在的结构

`tests/unit/test_cli.py:434`：

> The `--fd` branch returns before the loop that announces which options this path ignores, so each of these used to be accepted in full and then dropped without a word

重构之后 `--fd` 分支在第 284 行，**排在播报循环（第 279-282 行）之后**，这句话的前半截在现在时下是假的。后半截「used to be」是对的。旁边那个 `test_fd_still_reports_the_options_the_config_cannot_carry`（第 295 行，docstring 在第 300 行）用的是正确的过去时说法（「loaded its own config and threw the second return value away」）。

同一批测试里两句话讲同一件事、一句现在时一句过去时且现在时那句已经不成立，下一个读者会以为代码还是旧结构。建议把这一句改成过去时并指向重构后的位置。

### m-6（minor，把握高）改名彻底，但 `pidfile_dir` 这个键名没有权威 oracle 覆盖

改名核查结论：**彻底**。全仓（排除 `.claude/worktrees/` 里同伴的隔离树）grep `pidfile` 后剔除所有合法标识符，没有任何残留的 `proxy_config.pidfile`、`options.pidfile`、`--pidfile`（非 `-dir`）、或仍按「文件路径」语义使用的地方。`NOT_HOT_RELOADABLE` 已同步（`schema.py:42`），它被 `config/provider.py:75` 按 dotted path 消费，改名保持一致才有效。`contrib/systemd/ghc-api-proxy.service:23` 与 `install-user.py:78` 都是 `--fd 3 --graceful-timeout 300`，不涉及 pidfile。

一个值得记下的限制：`tests/unit/config/test_config_schema.py:13` 的 `test_authoritative_example_config_parses` 会拿 `docs/.human-controlled/config.example.yaml` 当 oracle 去撞 `extra="forbid"`——**但 `pidfile_dir` 在那份文件里是注释掉的**（`# pidfile_dir: "/run/ghc-api-proxy"`），注释行不参与解析。所以这个 oracle 并没有交叉验证新键名。现在唯一钉住它的是 `test_the_configured_pidfile_dir_reaches_the_options`，而那个测试自己写 YAML 字面量——如果 schema 字段和它同时写错同一个名字，两边一致就照样绿。

我**不建议**为此加任何东西：schema 字段名与 CLI 之间的一致性已经由 `test_the_configured_pidfile_dir_reaches_the_options` 走完整 CLI 覆盖了，剩下的风险只是「字段名与用户文档不一致」，而用户文档不允许我们碰，也不该由测试去强制。记在这里是为了让人知道这一格的判据来自哪儿，不要误以为 oracle 覆盖了它。

### n-1（nit）`start_token="999999"` 是一个可能撞上真值的令牌

`tests/int/test_standalone_process.py:536` 用 `"999999"` 冒充「别人的启动时刻」。`/proc/<pid>/stat` 第 22 字段是自开机以来的时钟节拍数，999999 在 100Hz 下约等于开机后 2.78 小时——不是天文数字级别的不可能。撞上的概率极低但不为零，而换成一个**不可能是节拍数**的字符串（`"not-a-real-start-time"`）走的是完全相同的分支（非空 → 走 mismatch 判断），代价为零。

### n-2（nit）`test_force_write_pidfile_claims_the_record_anyway` 手写了 `wait_until_recorded` 的循环

第 488-495 行的轮询与新加的 `wait_until_recorded`（第 152 行）逻辑一致，只是失败消息略弱（「the forced start never claimed the record」不说当前记录里是谁，而 helper 会说 `it holds N`）。既然 helper 就是为这个形状写的，这里直接用它更好。

### n-3（nit）两个新加的「不该挡」测试里，第一条的等待路径值得一句注释

`test_a_record_whose_process_has_gone_does_not_block_a_start` 用 `wait_until_recorded` 而不是 `wait_until_serving`，原因（记录一开始就在，presence 不等于「新进程起来了」）写在 helper 的 docstring 里而不是调用处。helper 的 docstring 写得很清楚，所以这条很弱；提出来只是因为这正是「夹具辅助函数会把 bug 钉进测试」那类坑的位置，调用处一句「`wait_until_serving` 在这里会立刻返回死进程的 pid」会让下一个人不必跳去读 helper。

### n-4（nit）`--pidfile-dir` / `--force-write-pidfile` / `--restart` 都没有 `help=`

`ghc-api-proxy start --help` 只显示裸标志名。对 `--force-write-pidfile` 尤其可惜：它的语义是「你正在故意重演那次生产事故」。

**但我不建议在本批改**：`start` 的全部选项都没有 `help=`，只给新标志加会造出第二种风格。要么整个命令一起补，要么不动。登记在这里供用户决定。

---

## 对重点审查项的直接回答

### 1. 拒绝的语义边界

三种「不该挡」逐条核对：

| 场景 | 是否被挡 | 依据 |
|---|---|---|
| `--restart` 合法接替 | **否** | `entry.py:102` 的 `if options.restart:` 与拒绝分支是 `if/elif`，restart 为真时 `elif` 不可达。变异验证（把 `elif` 改成独立 `if`）精确变红两个测试 |
| 陈旧记录（进程已退、PID 被回收） | **否** | `look_up_predecessor` 两个分支都返回 `entry=None`。两个新测试覆盖，变异验证精确变红 |
| `--force-write-pidfile` | **否** | 条件里的 `and not options.force_write_pidfile`；`test_force_write_pidfile_claims_the_record_anyway` 覆盖 |

「该挡的确实被挡」：记录指向活着且令牌匹配的进程 → 挡住，`test_a_start_without_restart_refuses_to_erase_the_incumbents_record` 覆盖，我做的正对照变异（把消息里的 `still records pid` 改掉）精确变红，证明这个断言真的在跑。

**一个例外**见 m-1：活着但**无法验证身份**的记录不被挡，且不声张。

另：`--restart` 与 `--force-write-pidfile` 同时给出时，`elif` 不可达，force 被忽略——这是对的，接替本来就包含覆盖，无需第二道许可。

### 2. `listeners.close()`

对。但注释的理由说错了一半，见 m-3（含实测数据）。`close()` 是正确的释放方式（关 master socket，此时还没有 accept 用的副本）。其它 bind 后抛出的路径已在 m-3 末尾列全，都是既有同形。

### 3. 检查与写入之间的窗口

取舍**可以接受**，理由见 m-2。但注释**没有**说清它挡不住什么——那句承认只存在于 `.dev` 的 README 里。我不要求实现进程间串行化。

### 4. 改名是否彻底

**彻底**，见 m-6（含一条关于 oracle 覆盖面的限制说明）。

### 5. `--fd` 冲突列表是否恰当 —— 我的判断

**当前列表（`--host`、`--port`、`--restart`、`--pidfile-dir`、`--force-write-pidfile`）是对的，不该扩大。**

判据不是「这个选项在 `--fd` 路径上有没有用」，而是「它请求的那件事在这条路径上**在语义上不可能**」。五个都通过：前两个要求选端点，后三个要求拥有并让渡/记录 listener，而 listener 是 systemd 的。

不该加进来的两类，理由不同：

- **`--manual` / `--rate-limit` / `--github-token`**：它们和 `--fd` 不矛盾，只是在 `ProxyConfig` 里没有落脚点——两条路径上都没有。把同一个选项在一条路径上判致命、在另一条路径上判劝告，是不自洽的。项目 2026-08-17 的裁决是「这类选项要播报」，重构后的 `cli.py` 正是这么做的，还有三个参数化测试钉住。**这条已经解决**，不需要再动。
- **`--graceful-timeout`**：派发提示说它「在 `--fd` 路径上同样被静默忽略」——**这个前提是错的**。`serve_inherited`（`cli.py:117-136`）把 `config.graceful_cleanup_timeout` 传给了 `uvicorn.Config(timeout_graceful_shutdown=...)`，而该值正来自 `--graceful-timeout` 经 `_load_spec_config` 的覆盖。更硬的证据：`contrib/systemd/ghc-api-proxy.service:23` 出厂就写着 `--fd 3 --graceful-timeout 300`——把它加进冲突列表会当场打死自己发的 unit 文件。

所以：这一格已经收口，两侧机制（矛盾者拒绝、无落脚点者播报）各就各位。

### 6. 测试鉴别力

`pidfile` → `pidfile_dir` 的夹具迁移我逐个核对了 11 个测试，**没有削弱任何既有断言**：8 个是纯机械替换（新增一行 `pidfile = standalone_pidfile_path(port, pidfile_dir)`，断言原样）；`test_a_half_sent_request...` 的 `marker` 从 `pidfile.parent / "entered"` 变成 `pidfile_dir / "entered"`，两者相等；TLS 材料目录 `pidfile.parent / "tls"` → `pidfile_dir / "tls"` 同理，连断言消息都跟着改了。

唯一语义变化的是 `test_a_start_without_restart_leaves_the_incumbent_alone` → `..._refuses_to_erase_the_incumbents_record`。旧测试的两条断言（`first.poll() is None`、`"found no predecessor" not in said`）都保留了，另加了五条。旧测试独有的覆盖面是「无 `--restart` 时两个进程能在 `SO_REUSEPORT` 下共存」——那个场景现在被 `test_force_write_pidfile_claims_the_record_anyway` 接住（它断言两个进程都活着）。**没有孤儿格。**

变异表我复核了实施者报告的四条形状，另外自己跑了四次（见下），结论：**够了**。剩下的空格只有一个，就是 m-4 的 `listeners.close()`——那一格结构上要进程内测试才够得着。

### 7. 同一条链上还有没有未发现的断点

按 CLI 解析 → 冲突检查 → 配置加载 → inactive 播报 → 分叉 → bind → 派生路径 → 查找 → 拒绝/告警 → 适配器 → serve → `announce`（写 pidfile + 发信号）→ 关闭阶梯 → `remove_pidfile` 走了一遍。本批范围内没有找到第二处逻辑断点。M-1 是这条链的出口（异常怎么变成操作者看到的东西），m-1 是查找那一步的一个 fail-open 支路。

`--force-write-pidfile` 的强制实例退出时会 `remove_pidfile`（它记的是自己，所以删得掉），于是原来的实例又变成「无记录可查」——正是那次生产事故的状态。这**是逃生舱的固有代价，不是缺陷**，而且 `entry.py:51` 的注释已经把话说明白了（「doing that is what left a serving process unfindable in the first place」）。不算发现，记在这里以免下一个评审重新提。

---

## 我自己跑的验证

主树上（HEAD `80068eb`，工作树含同伴改动）：

```
uv run ruff check src tests                       → All checks passed!
uv run pytest tests/int/test_standalone_process.py tests/int/test_standalone_lifecycle.py \
              tests/unit/test_cli.py tests/unit/config tests/unit/lifecycle -q   → 197 passed（第一次读到的版本）
```

变异验证在隔离副本 `/tmp/review-pidfile-copy-a1/` 做，**主树一个字节都没动过**。副本用 `cp -a` 复制 `src/ tests/ pyproject.toml`，用主仓的 `.venv/bin/python` + `PYTHONPATH=<副本>/src` 运行。

**先证明探针真的在跑**（副本里装的 `app` 是指向主树 `src` 的 editable install，不证不能信）：

- `import app.lifecycle.entry` 解析到 `/tmp/review-pidfile-copy-a1/src/app/lifecycle/entry.py`；
- pytest `rootdir: /tmp/review-pidfile-copy-a1`，`configfile: pyproject.toml`；
- **正对照**：把副本里拒绝消息的 `still records pid` 改成别的字符串 → `test_a_start_without_restart_refuses_to_erase_the_incumbents_record` 精确变红。副本确实是被测对象。

（副本比主树少跑一个测试：`test_authoritative_example_config_parses` 因为副本没有 `docs/` 而 skip。它不碰 `entry.py`，不影响下述结论。）

同步到评审快照后基线：`201 passed, 1 skipped`。

| 变异 | 结果 | 说明 |
|---|---|---|
| 拒绝改成「只要文件存在就挡」（`read_pidfile(...) is not None`） | **精确变红 2 个** | `never came to name pid N; it holds M`。证明两个新加的「不该挡」测试确有鉴别力 |
| 拒绝不再豁免 `--restart`（`elif` → `if`） | **精确变红 2 个** | `successor never recorded itself`；`test_a_failed_handover_leaves_the_predecessor_its_pidfile` 的 `Regex pattern did not match` |
| 删掉 `listeners.close()` | **全绿（137 passed）** | 见 m-4 |
| 删掉 `listeners.close()` + 异常存活时 bind 探针 | **Errno 98 → 释放** 的对照 | 见 m-3 |

另有一个非变异探针（m-1）：对活进程写入空令牌记录 → `look_up_predecessor` 返回 `entry=None`，拒绝不触发。

**变异全部只发生在副本里**，主树 `src/app/lifecycle/entry.py` 的 sha256 自始至终是 `a7f7dbf83600...`，与快照一致。

## 交回主会话的事项

1. **M-1 的处置需要裁决**：是本批修（小改），还是登记为「与既有启动期错误统一处理」的单独项。
2. **m-1 的处置需要裁决**：加一行告警，还是判为可达性太窄不做。两种我都能接受，但请写进未采纳表。
3. **越界观察一（不属本批，建议单独登记）**：`serve_inherited`（`cli.py:117-136`）完全不读 `proxy_config.server.tls`——没有 `ssl_certfile`/`ssl_keyfile`，也没有 `FirstByteRoutingAdapter`。而 `config.example.yaml` 出厂就是 `tls.mode: both`（`test_config_schema.py` 里有 `assert config.server.tls.mode == "both"` 为证，schema 默认值则是 `False`）。也就是说，用出厂配置跑 systemd socket activation 的人拿到的是纯明文，而且没有一行提示。项目的部署目标正是 systemd，值得单独立项。
4. **越界观察二（既有，nit）**：`cli.py:254-278` 那一整块 `cli_overrides` / `auth_overrides` / `upstream_overrides` 计算完之后**从未被消费**（`_load_spec_config` 不接受它）。本次重构把 `--fd` 分支移到了它后面，让这块死代码夹在冲突检查与配置加载之间，更显眼了。删它属于既有清理，不在本批。
5. **实施者仍在编辑被评审文件**。本报告针对 `/tmp/review-snapshot-b2/` 那份快照（哈希见开头）。若已再次变动，请核对哈希后再采纳。

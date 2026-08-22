# 平滑重启的接替（`--restart` 与 pidfile）

2026-08-22。监听器那一半里「后继如何找到前任」这一段。父话题 README 提到这部分原先散在 `../../systemd-runtime/`、`../../systemd-rolling/`、`../../deployment-systemd/`，尚未并进来；本目录只覆盖 pidfile 与 `--restart` 的接替语义，不试图收编那三处。

权威规范仍是主仓库 `docs/.human-controlled/lifecycle.md` 与 `config.example.yaml`，本目录是围绕它们的过程记录。**其中 `config.example.yaml` 关于 pidfile 默认路径的两句话，在本次改动后已与实现不符，需用户亲自更新**——见下文「遗留」。

## 起因

一次生产事故。2026-08-21 一个跑在 41411 端口的临时实例（`uvx` 装的另一个提交，未带 `--pidfile`、未带 `--restart`）把 4141 生产实例的 pidfile 记录覆盖成自己，退出时又把文件删掉。生产实例继续服务，但从此在磁盘上查无此人。次日一个带 `--restart` 的新实例读不到 pidfile，于是不发 SIGUSR2，而 `SO_REUSEPORT` 让它照样 bind 成功——两个进程并存服务 4141，全程零报错零日志。

根因是三件事叠在一起，缺一不可：

1. pidfile 默认路径与端口无关，于是任何 `start` 都是同一份记录的争夺者；
2. `--restart` 找不到前任时静默 fail-open；
3. `SO_REUSEPORT` 吃掉了唯一会自然报错的信号（EADDRINUSE）。

净效果是**一次失败的平滑重启与一次成功的平滑重启完全同形**。

完整取证：`../../tmp/260822-pidfile-missing-forensics.md`（含时间线、每条证据的取得方式、7 条已排除假设）。关键一环有直接一手观测：13:17:36 另一个 subagent 的脚本因为假设 pidfile 只有一行 PID 而在 `int()` 上崩了，**正因为崩了才把完整两行原样打印出来**。

## 用户裁决（2026-08-22）

分两批。第一批两条：

1. `--restart` 找不到前任时打一行告警。
2. pidfile 按监听端口区分，不同端口用不同 pidfile。

实施者当时提议的是另一条（让 `write_pidfile` 拒绝覆盖活进程的记录），用户选了按端口区分。**用户的裁决更好**：平滑重启的语义本就是接替同一个监听端点，跑在别的端口上的实例不是它的前任，按端口分文件在语义上更正确，且天然堵住临时实例的污染面。实施者先前「绑定端口会让换端口重启失去接管能力」的保留意见是错的——换端口本来就不是接管，是起新服务。

第一批落地并评审完毕后，用户更新了 `config.example.yaml`（把配置项从 `pidfile` 改为 `pidfile_dir`，目录语义），并把本文档「遗留」里当时登记的三条全部裁决为实现：

3. 配置项改为 `pidfile_dir`，默认 `$XDG_DATA_HOME/ghc-api-proxy`，文件名 `standalone-<最终生效端口>.pid`。
4. `write_pidfile` 拒绝覆盖活进程的记录，新增 `--force-write-pidfile` 强制覆盖。
5. `--fd` 遇到矛盾选项报错中止，不再静默吞掉。

所以「同端口的临时实例仍会顶掉记录」这条——第一批只解决了「换个端口」那一半——在第二批被补上了对称的另一半。

## 落地

| 位置 | 改动 |
|---|---|
| `app/config/schema.py` | `pidfile: str` → `pidfile_dir: str`；`NOT_HOT_RELOADABLE` 同步改名 |
| `app/config/paths.py` | `standalone_pidfile_path(port, directory=None)` 产出 `<dir>/standalone-<port>.pid` |
| `app/lifecycle/pidfile.py` | 新增 `PredecessorLookup` 与 `look_up_predecessor()`，判断收在一处并附带原因；`live_predecessor()` 退化为 `return look_up_predecessor(path).entry` |
| `app/lifecycle/entry.py` | pidfile 路径解析推迟到 bind 之后，端口取自实际监听地址；`--restart` 找不到前任时打 `[WARN]`；不带 `--restart` 而记录指向活进程时**拒绝启动**；`force_write_pidfile` 跳过拒绝；`signalled_predecessor` 只记录实际送达的 pid |
| `app/cli.py` | `--pidfile` → `--pidfile-dir`；新增 `--force-write-pidfile`；接上 `ProxyConfig.pidfile_dir`；`--fd` 与五个矛盾选项冲突时 `typer.BadParameter` 并点名实际冲突项；配置加载与 inactive 播报提到两条 serve 路径分叉之前 |

`--fd` 那两条改动针对的是**两类不同的失效**，混为一谈会修错：

- **矛盾选项**（`--host`/`--port`/`--restart`/`--pidfile-dir`/`--force-write-pidfile`）与 systemd 拥有 listener 直接冲突——这个进程既没选择那个端点也不拥有它，无法重新绑定、交接或记录。**报错中止**。
- **inactive 选项**（`--manual`/`--rate-limit`/`--github-token`）并不与 inherited listener 矛盾，只是 `ProxyConfig` 没有承载它们的位置。项目既有裁决要求**播报警告**而非拒绝。它们此前在 `--fd` 路径上完全静默，是因为该分支自己加载了一份配置并把第二个返回值丢掉了。

第二轮评审用一手 CLI 探针确认了这个区分：`--graceful-timeout`/`--history`/`--proxy` 在 inherited 路径上**确实生效**（实测进入最终 `ProxyConfig`，`serve_inherited` 读 `graceful_cleanup_timeout`），所以不能把它们一并拒绝。

配置项此前**没有任何消费者**：被解析进 `ProxyConfig`、登记进 `NOT_HOT_RELOADABLE`、写进 `config.example.yaml`，然后从未被读取。设置它的人得到默认路径且毫无迹象。

### 拒绝的语义边界

拒绝**不针对** `--restart` 的合法接替：那时覆盖前任的记录正是接替本身。拒绝针对的是「没说要接替，却有个活进程记在那里」。判据复用 `look_up_predecessor()`——记录必须指向一个活着**且身份令牌匹配**的进程，所以一份陈旧记录（进程已退出、或 PID 已被回收）不会挡住任何人。

拒绝发生在 bind 之后（文件名要等实际端口）、开始服务之前，抛出前先 `listeners.close()`，否则异常会带着一个已绑定的监听器离开作用域。

检查与写入之间存在一个窗口：检查时无人，`announce()` 时可能已有人。这里没有做 compare-and-swap，因为堵住的是「操作者手滑再起一个」这类顺序场景，不是并发争抢。真正的原子所有权需要进程间串行化，见「遗留」。

### 两个容易读错的设计点

**端口取自 bind 之后的实际地址而非 `options.port`。** 今天两者在所有 CLI 路径上恒等（`--port` 与 `server.port` 都被约束在 1..65535，`--fd` 走 `serve_inherited` 根本不到这里）。保留这个写法是因为它是唯一在约束松动后仍正确的，且从 socket 读回来代价为零。**第一版的 docstring 把 `--fd` 和 `port 0` 写成了既成事实，那是错的**，已按评审改为诚实说法——这个项目的注释是设计记录，写成事实会让下一个读者在错误的位置排查。

**`look_up_predecessor` 与 `live_predecessor` 的关系。** 意图是判断只存在一处，避免同一事实在两条路径各推导一遍而漂移。评审逐条核对了五个分支的等价性，唯一行为差异是 `entry is None` 时多一次 `path.exists()`，只影响 reason 字符串。第二批加入拒绝逻辑时，这个单一判断点直接复用，没有第二份实现。

## 评审处置

两位异源评审（Opus / GPT）独立并行，各自 0 blocker。**两份独立收敛到同一条最重要的发现**：`status="warning"` 不在 `STATUS_PREFIXES` 里，告警被渲染成暗色 `[....]`——与「请求刚开始」的例行行完全同形，整条改动的核心价值落空。两份都给了端到端实测。

### 已采纳并修复

| 条目 | 内容 | 处置 |
|---|---|---|
| 告警渲染成 `[....]` | `status=` 选的是 `STATUS_PREFIXES`，无 warning 档，未知值回落 `[....]` 且整行调暗；`level` 又被 `_render_text` pop 掉，文本模式里 grep 都搜不到 | 删掉 `status=`，走 `LEVEL_PREFIXES` 得 `[WARN]`；集成测试加 `assert "[WARN]" in said` |
| 端到端断言恒真 | `assert incumbent_pidfile != throwaway_pidfile` 比较的是测试自己用两个端口格式化出的两个字符串，任何生产变异都打不红 | 改用 `standalone_pidfile_path()` 导出期望路径 |
| docstring 说了不可达的路径 | 见上「两个容易读错的设计点」 | 改写为诚实说法 |
| `signal_restart` 返回值被丢弃 | 返回 `False`（前任在查找与发信号之间退出）时仍把 pid 写进 `signalled_predecessor` | 只记录实际送达的 |
| reason 措辞越界 | 「has since exited or been replaced」也覆盖了「读不到 `/proc`」，那种情况下前任可能还活着 | 改为「no longer matches the process holding that pid」 |
| 缺负控 | 全部新测试都是正向的，没有东西钉住「不该响时不响」 | 两处各加一行：不带 `--restart` 时、以及找到真前任时都不得出现告警 |
| 无测试钉住实际端口 | 把 `address[1]` 改成 `options.port`，原有测试全绿 | 加 `port=0` 测试（内核选端口，两者第一次不同） |
| `free_port()` 可能撞号 | 两次 `bind(0)` 理论上可返回同一端口 | 加 `assert incumbent_port != throwaway_port`（约束 fixture 而非生产代码，不恒真） |

### 未采纳，及理由

- **两位评审在 `port=0` 测试上直接冲突**：GPT 要求覆盖它，Opus 认为那是「给今天没有生产入口的分支建证明」，建议只改准 docstring 不加测试。**采纳 GPT 一侧**：那是 `run_standalone` 自身的调用面（`StandaloneOptions` 是公开 dataclass），测试成本极低，且它是唯一挡在「有人把 `address[1]` 简化成 `options.port`」前面的东西。同时也采纳 Opus 的 docstring 修改。测试的 docstring 里写明了它测的是直接调用面而非 CLI 路径。
- **跨版本迁移不做兼容层**（GPT 判为 major）。评审期间实测发现 `standalone.pid` **此刻已经不存在**（当天之内该缺陷又击发了一次），所以一个回退去读旧名的兼容层今天读到的同样是「不存在」，换不来任何东西，却会成为没人负责删除的永久残留。Opus 独立得出同一结论并称其为「明显正确」。迁移影响与手工补记录的命令写在 `.dev/human-controlled-docs-candidates/pidfile-port-scoping.md`。
- **信号处理器安装窗口**（GPT major）。`StandaloneServer.serve` 的顺序是 `arm()` → `on_serving()`（写 pidfile、发信号）→ 才安装 handler，所以从 pidfile 对外宣称「可接管」到 SIGUSR2 真正被接住之间有一个窗口，窗口内 SIGUSR2 走默认动作直接杀进程。评审用子进程探针证实（返回码 `-12`）。**不在本次修**：这是先于本次改动就存在的缺陷，与用户裁决的两条无关，修它要动关闭阶梯的核心时序，需要单独立项和单独验证。评审称本次改动「扩大了它的可达性」，该论证偏弱——把查找挪到 bind 之后并未改变 `arm()` 到 handler 安装之间的窗口长度。
- **并发回滚覆盖后来者**（GPT major）。A 找到前任 P 并发布 A，B 随后发布 B，若 A 的启动尾部抛异常，A 的回滚会把 P 原样写回，覆盖正在服务的 B。评审自己也确认单后继场景正确。**不在本次修**：同为既有缺陷，且真正修它需要同端口的进程间串行化（「先 read 再 write」仍有 TOCTOU），远超本次范围。
- **`signal_restart` 返回 `False` 分支的测试**（GPT 建议补）。`signalled_predecessor` 目前全仓无消费者，为一个无人读取的字段构造 shutdown 时序测试，成本高于收益。等它有了消费者再补。
- **`look_up_predecessor` 里 `path.exists()` 的权限歧义**（Opus nit-2）。父目录权限不足同样得到 False。注释已声明「`exists` 只在塑造一行日志，这里的竞态代价是一个词而不是一个决定」，已涵盖，不改。
- **`child_script()` 里的 `setup_logging` 对全部 12 个测试生效而只有 1 个读日志**（Opus nit-3）。评审自己判为改进而非违规——真实 CLI 入口本就调它，加上去让子进程更像生产。不改。

## 测试鉴别力

七次变异验证，每次都用 sha256 核对了恢复后与变异前逐字节一致：

| 变异 | 结果 |
|---|---|
| 撤掉 config pidfile 接线 | 精确红在 `assert None == PosixPath(...)` |
| 删掉告警 | 精确红在告警断言行 |
| 路径退回共享名（**修断言之前**） | 红在 `wait_until_serving` 超时，且那句 `child never started serving` **说的是假话**——子进程起来了、在服务，只是写到了别处 |
| 路径退回共享名（**修断言之后**） | 精确红在 `assert incumbent_pidfile != throwaway_pidfile`，消息直接显示两个路径同名；耗时从 20 秒降到 0.93 秒 |
| 端口取请求值而非实际绑定值 | 精确红在 `assert 0 != 0` |
| 把 `status="warning"` 加回去 | 精确红，输出实测为 `[....] --restart found no predecessor...` |
| 让告警无条件响（不动信号路径） | 精确红在 happy-path 负控 |

有一条**没有**独立验出分辨力，如实记录：「不带 `--restart` 时不告警」这条负控。能让它单独触发的变异（把告警挪出 `if options.restart:`）同时会改变 `predecessor` 的赋值，从而真的发出 SIGUSR2，于是先被更早的那条既有断言拦下。该负控目前只由代码结构保证。

第二批（`pidfile_dir` / 拒绝覆盖 / `--fd` 报错）另做四次：

| 变异 | 结果 |
|---|---|
| 从不拒绝（退回旧行为，**第一次写法**） | 红在 `subprocess.TimeoutExpired`——通用超时消息不说明问题，与第一批那条被评审批评的形态相同 |
| 从不拒绝（**改进断言之后**） | 精确红在 `the second start was not refused: it is still serving, and the record is now its own` |
| `--force-write-pidfile` 不被尊重 | 精确红在 `the forced start never claimed the record` |
| `--fd` 不再拒绝新三项 | 三个参数化用例全红在 `assert 0 != 0`（退出码应非零） |

「改进断言之后」那一条是本次唯一一处把评审教训直接用上的地方：一个红在超时上、且超时消息说不出所以然的测试，会让下一个人查错方向。

第二轮评审后又补两次：

| 变异 | 结果 |
|---|---|
| 拒绝判据放宽成「文件存在即拒绝」 | 两条新测试精确红在 `never came to name pid X; it holds Y` |
| inactive 播报重新对 `--fd` 不可达 | 三个参数化用例全红 |

第一条是第二轮评审 F2 点出的盲区：在补上「陈旧记录/回收 PID 不得误伤」这两个格子之前，把判据改宽**不会**让任何测试变红——四次变异只验了 false-negative 一侧。

第三轮（两份第二批评审的处置）再做三次：

| 变异 | 结果 |
|---|---|
| 拒绝重新以 traceback 逃逸 | 精确红；判据是 `not isinstance(result.exception, PidfileError)`，因为退出码 1 两种情形都会给出 |
| 删掉 `listeners.close()`（**第一版测试**） | **全绿——测试无鉴别力** |
| 删掉 `listeners.close()`（**持有异常之后**） | 精确红在 `Errno 98 Address already in use` |
| 去掉「无法核实的记录」告警（**补测试前**） | 全绿 |
| 去掉「无法核实的记录」告警（**补测试后**） | 精确红 |

`listeners.close()` 那条值得记：第一版测试写成 `with pytest.raises(...)` 不带 `as`，异常在块结束后就没有强引用，帧随之释放、端口跟着释放——于是删不删 `close()` 结果一样，测试绿得毫无意义。改成 `as refusal` 并在 bind 前 `assert refusal.value.__traceback__ is not None`，才把「异常仍被持有」这个前提真正建立起来。**这一格是评审用探针先发现的，我照着写的第一版仍然没抓住，是变异验证把它揪出来的。**

## 第二批评审处置

两位异源评审再次独立并行，各 0 blocker。GPT 报 1 major 1 minor，Opus 报 1 major 6 minor 4 nit。Opus 把 8 个文件快照到 `/tmp` 并在报告开头列出 sha256，因为**实施者在它评审期间仍在改这些文件**（正在修 GPT 那两条）；采纳前已逐一对哈希，八个全部一致。

### 已采纳并修复

| 条目 | 内容 | 处置 |
|---|---|---|
| `--fd` 仍静默吞掉三个 inactive 选项 | 冲突检查只管矛盾选项，而 `--fd` 分支自己加载配置并丢掉第二个返回值，`--manual` / `--rate-limit` / `--github-token` 的播报仍不可达 | 配置加载与播报循环整体提到两条 serve 路径分叉之前，一处解决 |
| 拒绝以 traceback 呈现 | `PidfileError` 一路穿到默认 excepthook，那句「pass `--restart` 或 `--force-write-pidfile`」被埋在十几行栈帧里，而这条拒绝的全部价值就是那句指示 | CLI 层捕获，`typer.echo` + `Exit(1)` |
| 拒绝的 false-positive 一侧无保护 | 把判据改宽成「文件存在即拒绝」，原有测试全绿——而那正违反「陈旧记录不得挡住启动」 | 补两个测试：进程已退出、PID 被回收 |
| 活着但无法核实身份的记录被静默覆盖 | 记录只有一行 PID（无身份令牌）时拒绝不触发，与「记录是垃圾」走同一条路 | 不拒绝（否则在读不到 `/proc` 的平台上每次启动都被挡），但打一行 `[WARN]` |
| `entry.py` 里没交代检查与写入之间的窗口 | 那句承认只写在本文档里，代码注释没有 | 在拒绝处补一句，说明它挡的是先后两次启动、不是并发争抢 |
| `listeners.close()` 的注释理由说反了一半 | 原写「进程即将退出」——但进程退出时内核本就回收 fd。评审用两个探针分出真机制：异常的 traceback 引着帧、帧引着 `listeners`，调用方多持有异常一会儿端口就多占一会儿 | 换成实测出的机制 |
| `listeners.close()` 无测试 | 删掉它 137 passed 全绿 | 加进程内测试（详见变异表，第一版仍无鉴别力） |
| 测试 docstring 描述了已不存在的结构 | 重构后 `--fd` 分支已排在播报循环之后，那句现在时描述成了假的 | 改写 |
| `start_token="999999"` 可能撞真值 | 该字段是自开机的时钟节拍数，999999 约合 100Hz 下 2.78 小时 | 换成 `"not-a-real-start-time"`，走完全相同的分支 |
| force 测试手写轮询 | 与 `wait_until_recorded` 逻辑重复且失败消息更弱 | 改用 helper |
| 两处 `wait_until_recorded` 调用缺一句说明 | 为什么不用 `wait_until_serving` 的理由只在 helper 的 docstring 里 | 调用处各补一句 |

### 未采纳，及理由

- **给新选项加 `help=`**（Opus n-4）。`start` 的**全部**选项都没有 `help=`，只给新标志加会造出第二种风格。要么整个命令一起补，要么不动。评审自己也不建议在本批改。登记，交用户决定。
- **把 `--manual` / `--rate-limit` / `--github-token` 加进 `--fd` 冲突列表**。两位评审独立给出同一判断：它们与 inherited listener 不矛盾，只是在 `ProxyConfig` 里没有落脚点，而项目 2026-08-17 的裁决是这类选项要播报而非拒绝。把同一个选项在一条路径上判致命、另一条判劝告是不自洽的。
- **把 `--graceful-timeout` 加进冲突列表**。派发给评审的提示里说它「在 `--fd` 路径上同样被静默忽略」——**这个前提是我写错的**。评审查证：`serve_inherited` 把 `config.graceful_cleanup_timeout` 传给了 `uvicorn.Config(timeout_graceful_shutdown=...)`，而 `contrib/systemd/ghc-api-proxy.service` 出厂就写着 `--fd 3 --graceful-timeout 300`——加进去会当场打死自己发的 unit 文件。
- **为 `pidfile_dir` 键名加权威 oracle 交叉验证**（Opus m-6）。评审自己也不建议：`test_authoritative_example_config_parses` 拿用户文档撞 `extra="forbid"`，但 `pidfile_dir` 在那份文件里是注释掉的，所以没有交叉验证到；剩下的风险只是「字段名与用户文档不一致」，而用户文档不允许我们碰，也不该由测试去强制。记录在此是为了让人知道这一格的判据来自哪里。

### 越界观察（不属本批，建议单独立项）

1. **`serve_inherited` 完全不读 `proxy_config.server.tls`**——没有 `ssl_certfile`/`ssl_keyfile`，也没有 `FirstByteRoutingAdapter`。而 `config.example.yaml` 出厂是 `tls.mode: both`。**用出厂配置跑 systemd socket activation 的人拿到的是纯明文，且没有一行提示。** 项目的部署目标正是 systemd，这条值得优先。
2. `cli.py` 里那一整块 `cli_overrides` / `auth_overrides` / `upstream_overrides` 计算完之后**从未被消费**（`_load_spec_config` 不接受它）。本批把 `--fd` 分支移到它后面，让这块死代码更显眼了。属既有清理。

## 遗留

第一批留下的三条，用户已在第二批全部裁决为实现，不再是遗留。当前剩下的是：
1. ~~**`GHC_API_PROXY_PORT` 这个拼写**~~ —— **2026-08-22 已裁决并实现**（提交 `1459320`）。`src/app/config/loading.py` 的 `ENV_ALIASES` 把无 `__` 的扁平名 `port` / `host` 指向 `server.port` / `server.host`。在此之前设 `GHC_API_PROXY_PORT` 不是「端口没生效」而是**进程起不来**：该名字映射到顶层键 `port`，撞上 `extra="forbid"`。`host` 是一并做的——两者总是一起设置，只给 `port` 加别名会让 `GHC_API_PROXY_HOST` 成为完全相同的陷阱。别名位于环境层，`--port` 仍压过它；两种拼写同时设置时嵌套写法确定性胜出（别名与显式名分开收集再合并，否则答案取决于环境变量遍历顺序）。详见候选文档同名一节。
2. **信号处理器安装窗口**（既有缺陷，建议单独立项）。`StandaloneServer.serve` 的顺序是 `arm()` → `on_serving()`（写 pidfile、发信号）→ 才安装 handler，所以从 pidfile 对外宣称「可接管」到 SIGUSR2 真正被接住之间有一个窗口，窗口内 SIGUSR2 走默认动作直接杀进程。评审用子进程探针证实（返回码 `-12`）。修它要动关闭阶梯的核心时序。
3. **并发回滚覆盖后来者**（既有缺陷，建议单独立项）。A 找到前任 P 并发布 A，B 随后发布 B，若 A 的启动尾部抛异常，A 的回滚会把 P 原样写回，覆盖正在服务的 B。单后继场景正确。真正修它需要同端口的进程间串行化（「先 read 再 write」仍有 TOCTOU）——第二批加入的拒绝逻辑也共享这个窗口，见上「拒绝的语义边界」。
4. **`listening on http://{host}:{port}` 在 `--fd` 路径上是假的**（既有缺陷，`src/app/server/pipeline_app.py`）。协议硬编码 `http://`，地址取自配置而非实际监听的 socket，所以继承 fd 时端口和协议都不对。2026-08-22 给该路径加上 TLS（提交 `fb06150`）之后，这行从「端口错」变成「端口和协议都错」。未修：该文件当时正被同伴改动。

## 报告原件

- `../../tmp/260822-pidfile-missing-forensics.md` —— 取证
- `../../tmp/260822-review-pidfile-port-scoping-opus.md` —— 评审（Opus）
- `../../tmp/260822-review-pidfile-port-scoping-gpt.md` —— 评审（GPT）

三份都留在 `tmp/` 而未搬入本目录：它们已被会话与本文档按该路径引用，搬动会造成断链，且 `.dev` 是同伴共用的独立仓库。报告原件是时间点记录，其中的路径与行号是当时的快照。

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

1. `--restart` 找不到前任时打一行告警。
2. pidfile 按监听端口区分，不同端口用不同 pidfile。

实施者当时提议的是另一条（让 `write_pidfile` 拒绝覆盖活进程的记录），用户选了按端口区分。**用户的裁决更好**：平滑重启的语义本就是接替同一个监听端点，跑在别的端口上的实例不是它的前任，按端口分文件在语义上更正确，且天然堵住临时实例的污染面。实施者先前「绑定端口会让换端口重启失去接管能力」的保留意见是错的——换端口本来就不是接管，是起新服务。

## 落地

| 位置 | 改动 |
|---|---|
| `app/config/paths.py` | `standalone_pidfile_path(port)` 返回 `standalone-<port>.pid` |
| `app/lifecycle/pidfile.py` | 新增 `PredecessorLookup` 与 `look_up_predecessor()`，判断收在一处并附带原因；`live_predecessor()` 退化为 `return look_up_predecessor(path).entry` |
| `app/lifecycle/entry.py` | pidfile 路径解析推迟到 bind 之后，端口取自实际监听地址；`--restart` 找不到前任时打 `[WARN]`；`signalled_predecessor` 只记录实际送达的 pid |
| `app/cli.py` | 接上 `ProxyConfig.pidfile`，CLI `--pidfile` 优先于 config |

第四条是顺带修的第三个断点：该配置项被解析进 `ProxyConfig`、登记进 `NOT_HOT_RELOADABLE`、写进 `config.example.yaml`，然后**从未被任何代码读取**。设置它的人得到默认路径且毫无迹象。

### 两个容易读错的设计点

**端口取自 bind 之后的实际地址而非 `options.port`。** 今天两者在所有 CLI 路径上恒等（`--port` 与 `server.port` 都被约束在 1..65535，`--fd` 走 `serve_inherited` 根本不到这里）。保留这个写法是因为它是唯一在约束松动后仍正确的，且从 socket 读回来代价为零。**第一版的 docstring 把 `--fd` 和 `port 0` 写成了既成事实，那是错的**，已按评审改为诚实说法——这个项目的注释是设计记录，写成事实会让下一个读者在错误的位置排查。

**`look_up_predecessor` 与 `live_predecessor` 的关系。** 意图是判断只存在一处，避免同一事实在两条路径各推导一遍而漂移。评审逐条核对了五个分支的等价性，唯一行为差异是 `entry is None` 时多一次 `path.exists()`，只影响 reason 字符串。

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

## 遗留

三条已登记在 `.dev/human-controlled-docs-candidates/pidfile-port-scoping.md`，交用户裁决：

1. **`config.example.yaml` 那两句默认路径描述现在是假的**，需用户亲自更新（人写文档权威，模型不改）。
2. **同端口的临时实例仍会顶掉并删掉生产记录**——按端口区分只解决了「换个端口」那一半。对称的另一半是让 `write_pidfile` 在覆盖一个记录着活进程的文件时拒绝或告警，`look_up_predecessor` 已经就位，成本比事故当时低。
3. **`--fd` 分支静默吞掉 `--restart` / `--pidfile`**——提前 `return` 跳过了 inactive 播报循环，与本次修的是同一类失效。

另有两条本次未修的既有缺陷（信号处理器窗口、并发回滚），理由见上「未采纳」，建议各自单独立项。

## 报告原件

- `../../tmp/260822-pidfile-missing-forensics.md` —— 取证
- `../../tmp/260822-review-pidfile-port-scoping-opus.md` —— 评审（Opus）
- `../../tmp/260822-review-pidfile-port-scoping-gpt.md` —— 评审（GPT）

三份都留在 `tmp/` 而未搬入本目录：它们已被会话与本文档按该路径引用，搬动会造成断链，且 `.dev` 是同伴共用的独立仓库。报告原件是时间点记录，其中的路径与行号是当时的快照。

# pidfile 按端口隔离修复评审

**日期**：2026-08-22

**评审范围**：只评审用户指定的 8 个文件的未提交工作树 diff，并只为核对调用链读取相邻实现与权威生命周期文档；未评审、未修改其余在途改动与暂存内容。

**结论**：`needs-fix`。共 0 blocker、3 major、3 minor、0 nit。

**证据权重**：下列 6 条发现均“足以据此行动”。其中 M1、M2、M3、m1、m2 来自逐行控制流核对；M2 另有隔离子进程实测；m1 与 IPv6 结论另有运行探针；m3 来自测试枚举与可判别变异分析。

> 运行时未提供用户点名的 `my-skills:as-reviewer`，调用返回 `Unknown skill`；本评审改用 `verifying-authoritative-claims` 与 `trusting-a-green-result` 做事实核验和测试鉴别力审查。

## Findings

### M1 — major — 高把握：首次从旧版默认路径升级时，新版必然找不到仍在运行的旧版前任，事故会在修复首次部署时重演一次

**位置**：`/home/xp/src/ghc-api-proxy-py/src/app/config/paths.py:30-41`，`/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:90-103`

旧版默认实例只写 `$XDG_DATA_HOME/ghc-api-proxy/standalone.pid`，新版只查询 `standalone-<port>.pid`。因此，一个由当前已发布代码启动、使用默认 pidfile 的前任即使仍在同端口服务，新版 `--restart` 也会在新路径得到 `None`，打印告警后继续作为独立 listener 服务，却不会向旧进程发送 SIGUSR2。`SO_REUSEPORT` 随即留下两个进程共同服务同一端口；这正是本次事故的结果，只是这次多了一行告警。显式 `--pidfile`／config pidfile 不受影响，但默认部署的第一次跨版本平滑重启必受影响。

这不是对“按端口区分”裁决的反对，而是旧命名到新命名之间缺少迁移语义。取证报告证明事故实例使用的正是旧默认名；从任何采用旧默认名的发布版升级都具备同一条件。

**建议**：在合入前明确并实现一次性的旧名迁移／兼容接管语义，且不得靠无条件信任旧共享文件而重新引入跨端口误杀；如果无法安全自动判断旧记录是否属于同一监听端点，就把首次升级定义为明确的 stop-then-start 操作，而不能继续把它当作平滑 `--restart`。增加一条跨版本端到端用例：旧式 incumbent 只留下 `standalone.pid`，新版按端口启动时必须得到已裁决的迁移结果，不能静默留下两个 listener。

### M2 — major — 高把握：pidfile 在 SIGUSR2 handler 安装前就公开了当前进程；同端口并发后继可让它按默认信号动作被直接杀死

**位置**：`/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:133-139`，`/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/standalone.py:147-165`

`StandaloneServer.serve()` 的顺序是 `arm()` → `on_serving()` → 退出 startup `try` → 进入 `_signal_handlers()`。`on_serving()` 又先写当前 PID，再可能向前任发信号。因此，从 pidfile 对外宣称“这个进程可接管”开始，到 SIGUSR2 handler 真正安装之间存在窗口。另一个几乎同时启动的 `--restart` 进程可以读取这个新记录、写入自己的记录并向它发送 SIGUSR2；窗口内 Python 对 SIGUSR2 的默认动作是终止进程，而不是进入 graceful drain。

把 predecessor lookup 挪到 bind 后会扩大这个既有窗口的可达性：第二个后继可以先完成 bind，再等第一个后继发布 pidfile，之后少了一段 bind 工作便可进入接管链。受控子进程探针在 `on_serving` 内向自己发送 SIGUSR2，进程返回码为 `-12`，且无任何 shutdown 输出；这直接证明该阶段 handler 尚未生效。实际双进程是否命中取决于调度，但没有任何同步原语排除它，后果是强制退出并截断在途请求。

这条路径不经过 `/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:148-159` 的 `except BaseException` 回滚；内核信号的默认终止不会让 Python 执行该回滚。

**建议**：在 pidfile 发布之前安装 SIGUSR2 handler，或先阻塞该信号并在 handler 就绪后解除阻塞；保证任何能够从 pidfile 找到当前进程的后继都只能触发 lifecycle ladder。增加确定性测试，在 serving hook 与 handler 就绪的边界注入 SIGUSR2，并断言进程进入 graceful drain 而非返回 `-SIGUSR2`。

### M3 — major — 高把握：失败回滚会无条件覆盖后来者的 pidfile；同端口并发启动可再次制造“活进程查无此人”

**位置**：`/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:148-159`

单一后继场景中，移动 lookup 后的 `predecessor` 初始化与原样 `write_entry(pidfile, predecessor)` 回滚仍然正确；bind 失败发生在这段 `try` 之前，也不会错误引用未初始化变量。并发场景则不正确：A 找到前任 P、发布 A；B 随后发布 B；若 A 的 `signal_restart(P)` 或其 startup 尾部抛出异常，A 的回滚不检查 pidfile 是否仍归 A 所有，直接把 P 写回并覆盖正在服务的 B。结果是 B 活着但磁盘记录指向 P，下一次 `--restart` 又找不到 B。

端口隔离只能去掉不同端口之间的争用，无法去掉同一端口上的合法重启并发；lookup 改到 bind 后也让多个已绑定 claimant 的交错成为本次顺序调整必须处理的状态。简单的“先 read 再 write”检查仍有 TOCTOU，不能真正关闭窗口。

**建议**：为同一端口的 lookup → publish → signal／rollback 建立进程间串行化，或提供真正原子的所有权比较与恢复；回滚只能恢复仍由本进程发布的那一代记录，绝不能覆盖后来 claimant。补一条带 barrier 的确定性交错测试，固定 A 发布、B 发布、A 失败的顺序，并断言 B 的记录仍在。

### m1 — minor — 高把握：`status="warning"` 不是 logging renderer 认识的 status，默认文本日志把告警渲染成 `[....]`

**位置**：`/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:100-103`；关联实现 `/home/xp/src/ghc-api-proxy-py/src/app/observability/logging.py:34-48`、`:91-107`；测试 `/home/xp/src/ghc-api-proxy-py/tests/int/test_standalone_process.py:401-418`

`STATUS_PREFIXES` 没有 `warning`。只要显式带 `status`，`_add_status_prefix()` 就不会再根据 `level="warning"` 回退，而是给未知值 `[....]`；文本 renderer 随后删掉 `level`，并把 `[....]` 当 pending 整行弱化。实测同一 processor 输入 `status="warning", level="warning"` 得到 `[....]`，只保留 `level="warning"` 则得到 `[WARN]`。告警文字仍会输出，所以不是完全静默，但默认运维界面把事故告警伪装成普通 pending 行。

现有测试只搜索 `found no predecessor` 与 `no record`，删除整个告警会精确变红，却无法发现告警严重度被错误 status 覆盖。

**建议**：移除这个 `status`，让 warning level 走既有 `[WARN]` 映射，或把 `warning` 正式加入 status 合同；测试默认 text renderer 的前缀为 `[WARN]`。同时建议把文案直接说成“restart handover did not occur; another process may still be serving this port”，比“serving as an independent listener”更明确地说明操作后果。

### m2 — minor — 高把握：`signal_restart()` 的布尔结果被丢弃，outcome 会声称已经 signal 一个实际未收到信号的 predecessor

**位置**：`/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:138-139`、`:162-166`；关联实现 `/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/pidfile.py:170-208`

`signal_restart()` 明确以 `False` 表示被 lookup 接受的进程在 pidfd 重验时已经退出或被替换，但 `announce()` 忽略返回值，最终仍把 `predecessor.pid` 写入 `StandaloneOutcome.signalled_predecessor`。这不会向错误 PID 发信号，且前任已退出时通常不再有双 listener 后果，所以严重度为 minor；但 outcome 的事实陈述错误，调用者也无法区分“查到过”与“确实发送成功”。

**建议**：单独记录实际发送成功的 PID，仅在 `signal_restart()` 返回 `True` 时设置 `signalled_predecessor`；为 `False` 分支补测试。是否同时告警应依据已裁决的语义决定，不能把“前任已自然退出”自动等同于“仍有未接管 listener”。

### m3 — minor — 高把握：新增测试能杀死“退回共享名”的变异，但不能证明路径使用的是实际 bound port

**位置**：`/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:85-94`；测试 `/home/xp/src/ghc-api-proxy-py/tests/int/test_standalone_process.py:423-455`、`/home/xp/src/ghc-api-proxy-py/tests/unit/config/test_config_paths.py:115-127`

共享名变异令端到端测试在等待 `throwaway_pidfile` 时超时，虽然没有走到最终“incumbent 记录仍在”断言，但它确实在被测生产入口上拒绝了共享名，因此对“不同端口得到不同默认路径”这一机制已有足够鉴别力；失败位置较早不使这个变异无效。

它没有覆盖顺序调整真正依赖的另一层：所有新增进程测试都传固定非零 port，故 requested port 与 actual bound port 相同。把 `/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:93` 改成 `options.pidfile_path(options.port)`，当前新增测试仍会全绿。相关 lifecycle 测试中也没有 `port=0` 或直接 `StandaloneOptions(fd=...)` 场景。CLI 的 `--fd` 实际走 `serve_inherited` 并按权威 spec 跳过 pidfile，因此至少应覆盖 lower-level 支持中真实可达的 `port=0`，不要让注释里的 `--fd` 论据代替产品入口事实。

**建议**：增加一个 `StandaloneOptions(port=0, pidfile=None)` 的真实 listener 测试，依据 `outcome.address[1]`／实际 identity 断言创建和清理的是 `standalone-<kernel-selected-port>.pid`，并用 requested `0` 作为负断言。只有在 `run_standalone(fd=...)` 是受支持的直接调用面时才另补 inherited-FD 用例；不要为 CLI systemd 路径虚构 pidfile 要求。

## 已核对、未发现问题的重点项

1. **IPv6 端口索引正确**：实测原生 `AF_INET6.getsockname()` 返回 `('::1', 36105, 0, 0)`，索引 1 是端口；项目的 `ActivatedSocketSet.identities()` 又在 `/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/activation.py:131-147` 把它规范化成 `('::1', 45559)`。因此 `/home/xp/src/ghc-api-proxy-py/src/app/lifecycle/entry.py:93` 的 `address[1]` 没有 IPv6 取错问题。
2. **`live_predecessor()` 行为等价**：旧实现的 4 个拒绝条件与成功返回逐条原样进入 `look_up_predecessor()`；现有 missing／malformed／self／no-token／stale-token／live／dead 测试全部通过。`live_predecessor()` 只投影 `.entry`，没有第二份判断。`signal_restart()` 的 pidfd 重验是信号发送时防 PID 回收所必需的第二阶段验证，不是漂移的 lookup 副本。
3. **告警触发范围本身正确**：只有 `options.restart` 为真且 lookup 没有可 signal entry 时触发；普通 start 不响。m1 说的是渲染严重度，M1 说的是迁移状态，不是否定该触发条件。
4. **单后继异常回滚仍保留原 predecessor token**：`write_entry(pidfile, predecessor)` 没有重新推导身份；M3 只针对并发后来者已取得所有权的交错。

## 验证记录

- `uv run ruff check src tests`：通过。
- `uv run pytest tests/unit/lifecycle tests/unit/config tests/unit/test_cli.py tests/int/test_standalone_process.py -q`：`174 passed in 21.78s`。
- `git diff --check -- <8 个指定路径>`：通过。
- IPv6 探针：原生四元组索引 1 与项目规范化二元组索引 1 均为实际端口。
- warning prefix 探针：显式 `status="warning"` 得到 `[....]`，只依赖 warning level 得到 `[WARN]`。
- handler ordering 探针：在 `on_serving` 内发送 SIGUSR2 的隔离子进程返回 `-12`，证明 handler 尚未安装。

## 测试鉴别力结论

- 已知变异 (a) 对“共享默认名”有足够鉴别力；红在 `wait_until_serving` 超时仍是目标机制导致的确定性失败，但测试应避免让这个负例白等 20 秒，并另补 m3 所述 actual-port 判据。
- 已知变异 (b) 精确证明告警文本分支被测试执行；它不证明 warning 的渲染级别正确，也不覆盖查到 predecessor 后实际 signal 失败的 m2 分支。
- 当前绿灯不覆盖跨版本旧名迁移、publication-before-handler 并发窗口、失败 rollback 覆盖后来者这三条 major 链路。

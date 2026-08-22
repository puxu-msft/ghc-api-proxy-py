# 第二批 `pidfile_dir`／拒绝覆盖／`--fd` 评审

评审日期：2026-08-22。

评审快照：主仓库 `HEAD 80068ebb5737`，指定 8 个文件未提交 diff 的 SHA-256 为 `1040fd8af28bd5438c6e3962eac1cfff7e611807d3aea50d3f2ce276e452dc3f`。本报告只评价用户指定的 8 个文件；工作树中其他已修改或未跟踪文件未纳入评审。

## 结论

**Verdict：needs-fix。Blocker 0，Major 1，Minor 1。**

核心拒绝逻辑、`--restart` 合法接替、`--force-write-pidfile`、陈旧／回收 PID 放行、拒绝前释放监听器，以及 `pidfile_dir` 目录语义本身均正确。需要修复的是 `--fd` 路径仍会把 3 个既有 inactive 选项无声吞掉；此外，陈旧记录与 PID 回收记录的“不得误伤”只在 lookup 单元层被钉住，尚未在本批新增的拒绝接线层形成回归保护。

## Findings

### F1 — Major，高把握：`--fd` 仍无声吞掉 `--manual`、`--rate-limit` 与 `--github-token`

位置：`src/app/cli.py:221-235`、`src/app/cli.py:272-285`，相关生产者在 `src/app/cli.py:103-113`。

本批在 `src/app/cli.py:221-235` 只拒绝了 5 个 **fd-specific contradictions**：`--host`、`--port`、`--restart`、`--pidfile-dir`、`--force-write-pidfile`。这个集合本身恰当，但它没有修复早退分支丢弃 inactive 播报的问题：`src/app/cli.py:272` 仍把 `_load_spec_config()` 的第二个返回值接成 `_`，随后在 `src/app/cli.py:285` 直接 `return`。因此 `_load_spec_config()` 明确产出的 `--manual`、`--rate-limit/--no-rate-limit`、`--github-token` 三条 inactive 诊断仍不可达。

一手 CLI 探针分别执行 `start --fd 3 --manual`、`start --fd 3 --rate-limit`、`start --fd 3 --github-token token`，在 mock 掉实际 server runner 后三者均为 `exit_code == 0`、输出为空、runner 已调用。证据强度足以行动：它直接走 Typer 的真实入口，复现了用户点名的“选项被静默吞掉”。

不建议把这三项机械加入 fd 冲突列表。它们不是与 inherited listener 矛盾，而是当前 `ProxyConfig` 没有承载位置；项目既有裁决和注释要求对它们播报警告，而不是仅在 `--fd` 下改判为错误。可操作修法是保留当前 5 项 fd 冲突检查，同时让 fd 分支接收 `inactive` 并在 `run(...)` 前复用 `src/app/cli.py:299-302` 的播报循环，或把共同的 inactive 播报提到两个 serve 分支分叉之前。

用户开放问题里举出的 `--graceful-timeout` 与上述三项不同，不应加入冲突列表，也没有被忽略。`_load_spec_config()` 在 `src/app/cli.py:94-99` 把 `--graceful-timeout`、`--history`、`--proxy` 写入 `ProxyConfig`，`serve_inherited()` 在 `src/app/cli.py:130` 使用 `graceful_cleanup_timeout`。真实入口探针得到 `cleanup=7`、`history=False`、`proxy=http://127.0.0.1:8080`，且 `proxy_from_cli=True`。证据强度足以排除“这些选项也应被拒绝”的建议。

### F2 — Minor，高把握：拒绝接线的测试矩阵缺少“陈旧记录不得误伤”两格

位置：`tests/int/test_standalone_process.py:408-479`，被测分支在 `src/app/lifecycle/entry.py:97-115`；已有 lookup 单元覆盖位于 `tests/unit/lifecycle/test_lifecycle_pidfile.py:92-127`。

当前真实进程集成测试钉住了“匹配的活进程记录应拒绝”和“force 应放行”，既有测试也钉住了“restart 找到前任时应合法接替”。但是没有集成测试让 `run_standalone()` 面对以下两种记录并证明能够开始服务：记录对应的进程已经退出；PID 仍存活但 identity token 不匹配，代表 PID 已回收。已有单元测试只证明 `look_up_predecessor()` 对这两种输入返回 `None`，没有钉住 `entry.py` 必须继续以 `lookup.entry` 而不是 `pidfile.exists()` 等更宽判据作拒绝决定。

这使四次本批变异只验证了 false-negative 一侧，没有验证拒绝过宽的 false-positive 一侧。把 `src/app/lifecycle/entry.py:108` 的判据错误地改成“文件存在即拒绝”时，本批两个新增真实进程测试仍会通过，而这正好违反用户重点指定的陈旧记录边界。证据强度足以要求补一条针对性回归，但不足以把它上升为生产缺陷，因为当前生产实现经实际进程探针验证是正确的。

可操作建议：在 `tests/int/test_standalone_process.py` 增加两个小场景或一个参数化场景。其一先用真实子进程写入合法记录，再终止该进程，然后启动 server 并断言它写入自己的记录且可服务；其二保留一个真实子进程但写入错误 token，再作同样断言。无需新增测试框架，也无需扩大到并发串行化。

## 重点审查结论

### 1. 拒绝逻辑的语义边界

`src/app/lifecycle/entry.py:97-115` 当前实现正确：只在非 `restart`、lookup 找到 token 匹配的活进程、且未指定 force 时拒绝。`restart` 在 `src/app/lifecycle/entry.py:101-108` 单独走合法接替；force 在 `src/app/lifecycle/entry.py:108` 绕过拒绝；进程退出和 PID 回收都由 `look_up_predecessor()` 的 identity 比对归为 `entry is None`。

实际进程探针验证了 3 条边界：匹配的活记录被拒绝；进程已退出的记录被放行并完成一次 serve／SIGTERM；活 PID 配错误 token 的回收模拟记录也被放行并完成一次 serve／SIGTERM。请求的 targeted suite 还以真实进程覆盖了 restart 接替与 force 覆盖。证据强度足以确认当前实现，不支持把 F2 的测试缺口误写成代码错误。

### 2. `listeners.close()`

`src/app/lifecycle/entry.py:110-111` 的释放方式正确。`bind_listener()` 把原 socket 交给 `ActivatedSocketSet` 时由后者持有 duplicate，原 socket 在 `src/app/lifecycle/listener.py:107-109` 关闭；`ActivatedSocketSet.close()` 在 `src/app/lifecycle/activation.py:149-152` 关闭所有 master duplicates。拒绝发生在 adapter 与 accept duplicates 创建之前，因此这里没有遗漏第二层 socket。

实际探针在捕获 `PidfileError` 后，立即以 `reuse_port=False` 重新绑定同一端口并成功，证明拒绝路径没有留下监听占用。TLS 两处既有同形泄漏按用户要求未计入本批 finding。

### 3. 检查与写入窗口

`look_up_predecessor()` 在 bind 后执行，`write_pidfile()` 在 `on_serving` 中执行，二者之间确有 TOCTOU 窗口。README 对它的描述是诚实的：它明确限定本批只堵顺序误操作，不声称解决并发争抢，也把真正的原子所有权留给进程间串行化。按用户明确边界，本评审不要求在本批实现锁或 compare-and-swap。

### 4. 改名完整性

在主仓库的 `src/`、`tests/`、`docs/` 中分别搜索旧 schema／dataclass 字段形态、旧构造关键字和精确旧 CLI 选项 `--pidfile`，没有发现旧名残留。`ProxyConfig.pidfile_dir`、`NOT_HOT_RELOADABLE`、CLI `--pidfile-dir`、`StandaloneOptions.pidfile_dir` 与相关测试均已同步。

仍保留的 `pidfile` 局部变量、`write_pidfile(path)`、`read_pidfile(path)` 及其 docstring 表示最终派生出的**文件**，不是旧配置项，继续使用文件路径语义是正确的。`standalone_pidfile_path(port, directory)` 也把“操作员选目录、生产代码派生文件名”的边界表达完整。

### 5. `--fd` 冲突列表

当前 5 项 fd-specific 冲突列表是恰当的，不应把所有其他 start 选项一律扩大进去。`--graceful-timeout`、`--history`、`--proxy`、`--verbose`、`--config` 在 inherited path 上有真实作用；`--manual`、`--rate-limit`、`--github-token` 则应按既有裁决播报 inactive，而非伪装成 fd 所特有的冲突。完整判断与需修处见 F1。

### 6. 测试鉴别力与 fixture 迁移

实施者记录的四次本批变异能支撑以下窄结论：拒绝逻辑不能整体删除；force 必须到达生产分支；新增 3 个 lifecycle CLI 选项必须在 fd 路径报错。它们不能支撑“拒绝边界完整”这一更强结论，因为没有变异或场景针对拒绝过宽，见 F2。

`tests/int/test_standalone_process.py` 中从单文件 fixture 到目录 fixture 的机械迁移没有削弱原有生命周期断言。11 个既有调用点都先用 `standalone_pidfile_path(port, pidfile_dir)` 得到最终文件，再把目录交给子进程；TLS material 与 marker 也改为目录下的相应位置。文件命名合同另由 `tests/unit/config/test_config_paths.py:116-143` 的字面期望独立锚定，因此集成测试使用生产 helper 定位文件不会让命名错误完全同源自洽。

### 7. 同链其他断点

除 F1 和 F2 外，没有发现本批改动引入的其他断点。尤其是 normal start、restart、force、pidfile cleanup、失败 handover 回滚和配置到 `StandaloneOptions` 的接线仍闭合。

## 已知环境变量事实核对

已确认用户提供的事实无误。`environment_values()` 在 `src/app/config/loading.py:117-132` 只用 `__` 分层；实测 `GHC_API_PROXY_PORT=5000` 生成顶层 `port` 并被 `ProxyConfig(extra="forbid")` 拒绝，错误位置为 `('port',)`；`GHC_API_PROXY_SERVER__PORT=5000` 被接受且最终端口为 5000。此项是既有待裁决问题，不计 finding。

## 验证记录

- `uv run ruff check src tests`：通过。
- `uv run pytest tests/int/test_standalone_process.py tests/int/test_standalone_lifecycle.py tests/unit/test_cli.py tests/unit/config tests/unit/lifecycle -q`：`197 passed in 24.12s`。
- 实际进程边界探针：匹配活记录拒绝并释放监听；退出记录放行；错误 token 的活 PID 记录放行，三项通过。
- Typer 真实入口加 mock runner 探针：3 个 inactive 选项在 `--fd` 下均 `exit_code == 0`、空输出且 runner 已调用；支持 F1。
- Typer 真实入口加 mock runner 探针：`--graceful-timeout 7 --no-history --proxy ...` 在 `--fd` 下进入最终 `ProxyConfig`；支持不扩大 fd 冲突列表的判断。

这些证据足以评价本次 8 文件 diff；没有重跑实施者声称的全量 `1778 passed, 2 skipped`，因此本报告不把该全量结果升级为本评审独立复验结论。

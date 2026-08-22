# pidfile 的目录、命名与端口来源

原名《pidfile 与端口的绑定》。2026-08-22 用户更新 `config.example.yaml` 并裁决了三条修法之后重写。

本文件现在只剩**一个**待裁决点（`GHC_API_PROXY_PORT` 这个拼写），其余部分是已落地事实的记录，供对照。

> **2026-08-22 二次核对**（`.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md`）：本文各条现场复核后**全部仍然成立**，仅补上了几处可复算的代码位置。

## 已被采纳

用户于 2026-08-22 亲笔更新了 `docs/.human-controlled/config.example.yaml:227-235` 的 pidfile 一节，把配置项从 `pidfile`（文件）改为 `pidfile_dir`（目录）：

```yaml
# 优雅重启使用的 pidfile 所在目录，systemd/pm2 完全跳过 pidfile 机制。
# 默认是 $XDG_DATA_HOME/ghc-api-proxy，pidfile 命名形如 standalone-${GHC_API_PROXY_PORT}.pid
```

（英文对照在同节 `:230-231`，示例值 `# pidfile_dir: "/run/ghc-api-proxy"` 在 `:235`，并于 `:233` 标注不支持热重载。）

本目录早先提出的替换文案（保留 `pidfile` 文件语义）**未被采纳，已删除**：目录语义更好，一个设置覆盖操作者跑的所有端口，而文件名不必、也不应由操作者选——后继必须能只凭端口推导出它。

同日裁决并已实现的三条：

| 裁决 | 实现 |
|---|---|
| pidfile 按端口区分 | `src/app/config/paths.py:30` 的 `standalone_pidfile_path(port, directory)` 产出 `standalone-<port>.pid`；端口取自 bind 后的实际监听地址（`src/app/lifecycle/entry.py:60`） |
| `--restart` 找不到前任时告警 | `[WARN]` 一行（`src/app/lifecycle/entry.py:107-109`），说明四种原因中的哪一种（`lookup.reason`），以及「没有接管、旧进程可能仍在服务该端口」 |
| `write_pidfile` 拒绝覆盖活进程的记录，`--force-write-pidfile` 可覆盖 | 不带 `--restart` 而记录指向一个活进程时启动被拒绝并说明两条出路（`src/app/lifecycle/entry.py:110-118`）；`--restart` 的合法接替不受影响 |
| `--fd` 遇矛盾选项报错中止 | `--fd`（`src/app/cli.py:202`）与 `--host` / `--port` / `--restart` / `--pidfile-dir` / `--force-write-pidfile`（`cli.py:217-219`）同时出现时 `typer.BadParameter`（`cli.py:255`），并点名实际冲突的那几个 |

配置项 `ProxyConfig.pidfile_dir`（`src/app/config/schema.py:383`，并登记在 `:42` 的 `NOT_HOT_RELOADABLE`）现在真的被读取了。改名之前它叫 `pidfile`，被解析进 schema、登记进 `NOT_HOT_RELOADABLE`、写进 `config.example.yaml`，然后**从未被任何代码读取**——设置它的人得到默认路径且毫无迹象。CLI `--pidfile-dir` 优先于配置文件。

## 待裁决：`GHC_API_PROXY_PORT` 这个拼写

新 spec 把默认文件名写作 `standalone-${GHC_API_PROXY_PORT}.pid`。作为「最终生效的那个端口」的占位记号，这没有歧义，实现也正是这么做的——文件名取自 bind 后从 socket 读回的实际端口，无论它来自 `server.port`、`--port` 还是别处。

但 `GHC_API_PROXY_PORT` 同时**长得像一个真实的环境变量**，而它现在不是。实测（2026-08-22）：

| 写法 | 结果 |
|---|---|
| `GHC_API_PROXY_SERVER__PORT=5001` | 生效，`server.port` = 5001 |
| `GHC_API_PROXY_PORT=5000` | **进程启动失败** |

原因是 `environment_values()` 以 `GHC_API_PROXY_` 为前缀、`__` 为分层符，所以 `GHC_API_PROXY_PORT` 映射到顶层键 `port`，而 `ProxyConfig` 是 `extra="forbid"`，顶层没有 `port` 字段：

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for ProxyConfig
port
  Extra inputs are not permitted [type=extra_forbidden, input_value='5000', input_type=str]
```

也就是说，一个照着 spec 读的人如果去设 `GHC_API_PROXY_PORT`，得到的不是「端口没生效」，而是**服务起不来**。

三条出路，**我倾向第一条**：

1. **实现它**，让 `GHC_API_PROXY_PORT` 成为 `server.port` 的顶层别名。理由：`GHC_API_PROXY_` + `PORT` 是这个前缀下最自然的拼写，用户自己写文档时就这么写了，说明它符合直觉；而 `GHC_API_PROXY_SERVER__PORT` 拗口且容易把双下划线写成单个。代价是在扁平命名与嵌套命名之间开了一个特例，将来 `HOST` 之类会不会也要跟进，需要一并想清楚。
2. **换记号**，文档改用 `standalone-<端口>.pid` 或 `${PORT}`，避免读者把它当环境变量。代价最小，但放弃了一个好拼写。
3. **保持现状**。不推荐：踩中的人得到的是启动失败，而失败信息里只有 `port  Extra inputs are not permitted`，与 pidfile 毫无关联，很难自己走回来。

若选第一条，另有一个次级问题需一并裁决：三个来源同时出现时的优先级。现有分层是 bundled < YAML < 环境 < CLI，`GHC_API_PROXY_PORT` 落在「环境」那一层最自然，即 `--port` 仍然压过它。

## 切换到新版本时的一次性影响

**现场在 2026-08-22 13:15 复核过**：`~/.local/share/ghc-api-proxy/standalone.pid` 已经不存在，而 pid 2254087 仍在服务 4141。取证报告记录该进程曾在 11:45:44 写出过这个文件，如今没了——同一个缺陷在取证报告写完之后、当天之内又击发了一次（最可能是某个会话跑了一次 `start`，未取证到具体哪一次，此句为推测）。

**2026-08-22 16:0x 再次复核，结论不变**：`ss -lntp | grep -w 4141` 仍报 `pid=2254087`，而 `ls ~/.local/share/ghc-api-proxy/` 里既无 `standalone.pid` 也无 `standalone-4141.pid`。下面那段补记录的操作因此仍然适用。

也就是说，当前生产实例此刻正处在与事故当事人相同的状态：活着、在服务、磁盘上查无此人。

这顺带让「要不要做旧名兼容层」失去了争议：一个回退去读 `standalone.pid` 的兼容层今天读到的同样是「不存在」，换不来任何东西，却会成为没人负责删除的永久残留。因此没有实现。

如果希望新版本第一次 `--restart` 就能接管当前这个进程，先为它补一份记录。**不能手写**——文件第二行是 `/proc/<pid>/stat` 的第 22 个字段（进程启动时刻），用于区分同一 PID 的前后两任，而 `comm` 字段自身可能含空格，按列切分不可靠。用项目自己的函数：

```bash
cd /home/xp/src/ghc-api-proxy-py
PYTHONPATH=src uv run python -c "
from pathlib import Path
from app.lifecycle.pidfile import write_pidfile
print(write_pidfile(Path.home() / '.local/share/ghc-api-proxy/standalone-4141.pid', 2254087))
"
```

（`2254087` 换成届时 `ss -lntp | grep 4141` 报出的实际 pid。）

不做也可以，但要注意新的拒绝行为已经生效：**不带 `--restart` 直接起第二个实例现在会被拒绝**（记录指向活进程时）。当前这个进程没有记录，所以拒绝不会触发；补了记录之后，就必须用 `--restart` 接管，或 `--force-write-pidfile` 强行占用。

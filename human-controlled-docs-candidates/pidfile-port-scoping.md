# pidfile 与端口的绑定

覆盖 `docs/.human-controlled/config.example.yaml` 中 pidfile 一节与实现的**已知冲突**，以及一个尚未裁决的相邻问题。

冲突是 2026-08-22 的一次改动造成的，改动本身由用户当场裁决，但那份 spec 由用户亲笔控制，模型不改，所以在此提请更新。

## 现状

### 触发这次改动的事故

2026-08-21 13:10 起，一个 `ghc-api-proxy start --port 4141 --restart` 实例在 4141 上正常服务。同日 13:37，另一个会话为了验证一个提交，跑了 `uvx --from git+file://...@2924a8c ghc-api-proxy start --port 41411`——端口不同，未带 `--pidfile`，未带 `--restart`。

当时 pidfile 的默认路径与端口无关，两者落在同一个文件上。于是这个临时实例：开始服务时用 `write_pidfile` 把 4141 实例的记录覆盖成了自己；13:42:45 退出时 `remove_pidfile` 判断「文件记的正是我」，把文件 unlink 掉。4141 实例毫发无损地继续服务，但从此在磁盘上查无此人。

次日 11:45，一个带 `--restart` 的新实例启动，`live_predecessor()` 读不到文件返回 `None`，**没有发出 SIGUSR2**；而 `SO_REUSEPORT` 让它照常 bind 成功。结果是两个进程并存服务 4141，内核在两者间分发连接，全程没有报错、没有失败的 bind、也没有一行日志。一次失败的平滑重启与一次成功的平滑重启，在操作者眼里完全同形。

完整取证见 `.dev/docs/tmp/260822-pidfile-missing-forensics.md`。

### 代码事实

- `src/app/config/paths.py` 的 `standalone_pidfile_path(port)` 现在返回 `$XDG_DATA_HOME/ghc-api-proxy/standalone-<port>.pid`，签名多了 `port` 参数。
- `src/app/lifecycle/entry.py` 的 `run_standalone` 把 pidfile 路径的解析推迟到 bind 之后，端口取自实际监听地址而非请求值。`--fd` 继承的监听器从不声明自己的端口，`--port 0` 由内核选端口，这两种情况下用请求值都会算出错误的文件名。
- `src/app/lifecycle/entry.py` 在 `--restart` 找不到前任时打一行 `[WARN]`，说明找不到的原因（文件不存在 / 无法解析 / 记录的进程已退出或被替换 / 记录无身份可验证）以及后果（本进程将作为独立监听者服务，而非接管）。
- `src/app/cli.py` 现在会读 `ProxyConfig.pidfile`，命令行 `--pidfile` 优先于配置文件。**在此之前该配置项没有任何消费者**：它被解析进 `ProxyConfig`（`src/app/config/schema.py`）、被登记进 `NOT_HOT_RELOADABLE`、被写进 `config.example.yaml`，然后从未被读取——设置它的人得到的是默认路径，且没有任何迹象表明设置被丢弃了。

### 与现行 spec 的冲突

`docs/.human-controlled/config.example.yaml` 中 pidfile 一节的中英两句都写着默认路径是 `$XDG_DATA_HOME/ghc-api-proxy/standalone.pid`。实现已不再产生这个路径。**这两句需要更新**，否则照 spec 设置的人会对不上实际文件名。

同一节的示例值 `# pidfile: "/run/ghc-api-proxy/standalone.pid"` 不受影响：显式指定的路径原样使用，不追加端口。

## 提案

以下是替换文案的候选，可整段丢弃。措辞尽量贴合该文件既有的中英并列风格。

```yaml
# 优雅重启使用的 pidfile，systemd/pm2 完全跳过 pidfile 机制。
# 默认是 $XDG_DATA_HOME/ghc-api-proxy/standalone-<端口>.pid，按实际监听的端口区分：
# 平滑重启接替的是同一个监听端点，跑在别的端口上的实例不是它的前任。
# 显式指定时按原样使用，不追加端口。
#
# Pidfile used by graceful restart, not used by systemd/pm2.
# Defaults to $XDG_DATA_HOME/ghc-api-proxy/standalone-<port>.pid, scoped to the port actually
# listened on: a smooth restart replaces one listening endpoint, and a run on another port is
# not its predecessor. An explicit path is used as given, with no port appended.
#
# NOT hot-reloadable (requires restart). / 不支持热重载（需重启）。
#
# pidfile: "/run/ghc-api-proxy/standalone.pid"
```

## 待裁决

### 一、切换到新版本时的一次性影响

**现场情况在 2026-08-22 13:15 复核过，比原先设想的更简单**：`~/.local/share/ghc-api-proxy/standalone.pid` **此刻已经不存在**，而 pid 2254087 仍在服务 4141。取证报告记录该进程曾在 11:45:44 写出过这个文件，如今没了——**同一个缺陷在取证报告写完之后、当天之内又击发了一次**（最可能是某个会话跑了一次 `start`，未取证到具体是哪一次，此句为推测）。

也就是说：当前生产实例此刻正处在与事故当事人完全相同的状态——活着、在服务、但磁盘上查无此人。

这件事顺带把「要不要做旧名兼容层」这个问题变成了没有争议的：一个回退去读 `standalone.pid` 的兼容层，今天读到的同样是「不存在」。它换不来任何东西，却会成为一份没人负责删除的永久残留。因此实现上没有加。

如果希望新版本第一次 `--restart` 就能接管当前这个 2254087，需要先为它补一份记录。**不能手写**——文件第二行是 `/proc/<pid>/stat` 的第 22 个字段（进程启动时刻），用于区分同一个 PID 的前后两任，而 `comm` 字段自身可能含空格，按列切分并不可靠。用项目自己的函数生成：

```bash
cd /home/xp/src/ghc-api-proxy-py
PYTHONPATH=src uv run python -c "
from pathlib import Path
from app.lifecycle.pidfile import write_pidfile
print(write_pidfile(Path.home() / '.local/share/ghc-api-proxy/standalone-4141.pid', 2254087))
"
```

（`2254087` 换成届时 `ss -lntp | grep 4141` 报出的实际 pid。）

不做这一步也可以：新版本会作为独立监听者启动，并打出一行 `[WARN]` 说明没有接管、旧进程可能仍在服务该端口。此时两个进程会同时服务 4141，需要手动停掉旧的。

### 二、`write_pidfile` 是否该拒绝覆盖一个活进程的记录

按端口区分堵住了本次事故的路径——两个端口不再共用一个文件。但它没有堵住另一条：**同一端口**上跑一个临时实例（例如为了复现问题而在 4141 上再起一个），仍然会覆盖并在退出时删掉生产实例的记录。

`remove_pidfile` 现有的守卫（只在「文件仍记着我自己」时才删）防的是接替场景中后来者的记录被前任误删，防不住「先覆写、再自删」。

上面「一、」里记录的那次复发说明这条路径不是理论上的：它当天就又发生了一次。

可能的做法是让 `write_pidfile` 在即将覆盖一个「记录着活着且身份匹配的进程」的文件时拒绝或告警——判据是现成的，`look_up_predecessor()` 现在已经就位，在 `announce()` 里对不带 `--restart` 的启动做一次同样的查找并告警，就是这次改动对称的另一半，成本比事故当时低。这会改变对外行为（某些启动会失败或变吵），所以未实施，提请裁决。

2026-08-22 用户裁决当时只涉及告警与按端口区分两条，此项不在其中。

### 三、`--fd` 分支静默吞掉 `--restart` 与 `--pidfile`

`ghc-api-proxy start --fd 3 --restart` 会完整接受 `--restart` 然后完全忽略它，一个字都不说。`--pidfile`、`--manual` 等同理。

原因是 `--fd` 分支提前 `return` 走 `serve_inherited`，跳过了下方那个逐条播报「本路径上此选项无效」的循环——而那个循环旁边的注释恰好写着「一个被接受然后被忽略的选项比一个被拒绝的更糟，因为没有任何东西能把它和生效区分开」。

这与本次为 `--restart` 修的是同一类失效，只是发生在另一条分支上。修法很小（一条 `typer.BadParameter`，或把那几个选项纳入既有的 inactive 播报），但它决定「传了无效选项该报错还是该警告」，属于对外行为，故提请裁决而非径直实施。

两位独立评审中的一位在本次评审里发现此项。

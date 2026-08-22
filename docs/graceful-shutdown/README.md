# 优雅关闭

进程从收到关闭信号到退出之间的一切。

主仓库 `docs/.human-controlled/lifecycle.md` 是**用户亲笔的权威规范**，定义了三档信号语义与部署方式；本目录是围绕它的开发过程记录，一切以它为准。

## 子话题

| 目录 | 内容 | 状态 |
|---|---|---|
| `client-side/` | 面向已连接客户端的那一半：停止准入、放掉连接、在途工作的保全、收尾行的计数与分级 | 已落地进 main，2026-08-20 |
| `restart-handover/` | 后继如何找到前任：pidfile 按端口区分、`--restart` 找不到前任时的告警、以及一次「活进程查无此人」事故的取证 | 已落地进 main，2026-08-22 |

`client-side/` 的 README 末尾有一节「遗留张力，交给用户裁决」，列着 6 条尚未裁决或未修的开放项；另有一份归档评审（`client-side/reports/260820-closeout-review.md`）仍有若干 minor/nit 未处理。接手前先读那两处。

`restart-handover/` 末尾同样有一节「遗留」，三条交由用户裁决（spec 的默认路径措辞、同端口临时实例仍会顶掉记录、`--fd` 静默吞掉 `--restart`），另有两条本次未修的既有缺陷（信号处理器安装窗口、并发回滚覆盖后来者）建议各自单独立项。

监听器那一半的其余部分（socket activation、代际生命周期）仍散在 `../systemd-runtime/`、`../systemd-rolling/`、`../deployment-systemd/` 三个话题下，尚未并进来。（2026-08-21 之前它们在主仓库 `docs/agents/` 下。）

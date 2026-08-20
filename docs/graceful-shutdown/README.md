# 优雅关闭

进程从收到关闭信号到退出之间的一切。

主仓库 `docs/.human-controlled/lifecycle.md` 是**用户亲笔的权威规范**，定义了三档信号语义与部署方式；本目录是围绕它的开发过程记录，一切以它为准。

## 子话题

| 目录 | 内容 | 状态 |
|---|---|---|
| `client-side/` | 面向已连接客户端的那一半：停止准入、放掉连接、在途工作的保全、收尾行的计数与分级 | 已落地进 main，2026-08-20 |

`client-side/` 的 README 末尾有一节「遗留张力，交给用户裁决」，列着 6 条尚未裁决或未修的开放项；另有一份归档评审（`client-side/reports/260820-closeout-review.md`）仍有若干 minor/nit 未处理。接手前先读那两处。

监听器那一半（socket activation、`SO_REUSEPORT` 平滑重启、代际生命周期）目前还散在主仓库 `docs/agents/systemd-*`、`deployment-systemd` 下，尚未搬进来。

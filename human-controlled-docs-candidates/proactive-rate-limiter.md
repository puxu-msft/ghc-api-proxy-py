# 候选：`proactive_rate_limiter` 在 `config.example.yaml` 中的表述

本文只针对 `docs/.human-controlled/config.example.yaml:341-343` 那三行。提案部分可整段丢弃。

> **2026-08-22 复核**：三条提案与一个待裁决点**全部仍然打开**，用户文档那三行一字未改。本次只修正了行号与代码位置——原文写的 `:350-352`、`schema.py:301`、`schema.py:150`、`handler.py:190` 都取自更早的快照，现已不指向对应内容。

## 现状

用户文档当前这样写（`config.example.yaml:341-343`）：

```yaml
# # 主动式速率限制 / Proactive rate limiting
# proactive_rate_limiter:
#   max_inflight: 5
```

代码侧的事实：

- 键名与层级与实现一致——`src/app/config/schema.py:396` 挂载 `proactive_rate_limiter`，`schema.py:203` 定义 `max_inflight: int = Field(default=50, ge=0)`。**结构是对的。**
- 该配置**已经接线并生效**，不是规划项：`src/app/server/pipeline_app.py:979` 把 `InFlightLimit` 挂在整个 ASGI app 的最外层（commit `f5589ec`）。
- 超过上限的请求在 `asyncio.Semaphore` 上**按到达顺序等待**，不被拒绝、不返回 429、连接不关闭（`src/app/server/admission.py:25` 的 `InFlightLimit`）。这是 2026-08-19 用户裁决「更多请求卡在接受连接而不要断开」的直接落地。
- `0` 表示关闭该门，不表示「不准入任何请求」。
- `/health`、`/health/liveness`、`/health/readiness`、`/metrics` 不占用名额（`src/app/server/admission.py:22` 的 `UNGATED_PATHS`，commit `7e9b62d`），否则饱和时 supervisor 拿不到应答，会把「正忙」误判成「已死」。同一处的注释还点明：`/models` **故意不豁免**，因为它面向客户端且可能触达上游。

## 提案

三点建议，各自独立，可分别取舍：

**一、解注释。** 当前是 `# #` 双井号整段注释，读起来像「尚未实现的规划项」，而它是已生效配置。相邻的 `reactive_rate_limiter`（`config.example.yaml:350`）是未注释的，两者并列时这个反差会让读者以为主动式那套还没做。

**二、示例值与默认值分开写。** 示例写的是 `5`，代码默认是 `50`，而文档没有任何一处说明默认值，读者会把 `5` 当默认。建议要么把示例值改成 `50`，要么在注释里点明默认值。

**三、写明超限行为是等待。** 这是最容易被误解的一点——同一文件 `:345-346` 紧接着就在谈 429（那处指的是**上游**返回的 429，与本机制无关），两段相邻很容易被读成「超过 `max_inflight` 就给客户端 429」。

合并后的候选文本：

```yaml
# 主动式速率限制 / Proactive rate limiting
#
# 同时在途的客户端请求数上限。超过上限的请求按到达顺序等待空位，不会被拒绝、不返回 429、连接也不会被关闭。
# Caps concurrent in-flight client requests. Requests over the cap wait in arrival order; they are never refused, never answered 429, and their connections are never closed.
#
# 0 表示关闭该上限（不是「不准入任何请求」）。健康检查与 metrics 不占用名额。
# 0 disables the cap (it does not mean "admit nothing"). Health checks and metrics do not consume a slot.
#
# 不支持热重载（需重启） / Not hot-reloadable (requires restart).
proactive_rate_limiter:
  # 默认 50 / Default 50
  max_inflight: 50
```

## 一个尚未裁决的点

等待没有时限。`client_delivery.client_request_deadline`（默认 3600 秒，`config.example.yaml:377`）是在**请求进入处理之后**才起算的（`src/app/server/handler.py:354` 的 `handle_bounded`），而 `InFlightLimit` 在它外面，所以**排队时间不计入任何 deadline**。

这一条是**实测**而非推断：按真实层级搭一个探针（上限 1、deadline 0.30 秒、前一个请求占位 0.60 秒），排队的那个请求总耗时 0.35 秒却没有超时——它的时钟直到拿到名额才开始走；同一轮里只有占位的那个请求因为自身确实跑了 0.60 秒而超时。

这在当前流量下基本够不着——实测口径是一天 429 个请求，而上限是 50 并发。但一旦真的排上队，队列里的请求没有任何超时，客户端只能干等。

三条路，未采纳任一之前不动代码：

1. **保持现状**——等待即设计，排队时间不设限。最贴合裁决原话。
2. **把排队时间纳入 `client_request_deadline`**——仍然是等待，但总时长有界，超时按 504 收尾而不是按拒绝收尾。
3. **给排队单独一个时限**——多一个配置键，收益存疑。

模型倾向第 2 条：它不违背「等待而非断开」（超时是超时，不是准入拒绝），又消除了无界等待。但这属于对裁决的**补全**而非执行，所以留给用户裁。

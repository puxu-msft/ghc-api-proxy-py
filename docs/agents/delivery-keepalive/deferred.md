# 待办与已知缺口

调查依据：`docs/tmp/260820-deferred-d3-d5-d6.md`（含实测探针与逐条读码）。

**分类口径**：「缺陷」= 正确做法唯一，不需要任何人裁决，排期做掉即可；「裁决」= 存在真实岔路，不同选择导向不同产品行为或不同代价。初版把若干缺陷错写成裁决项，已更正。

## 已解决

### D-1【已由并行会话修复】提前关闭交付不会及时释放上游

`main` 的 `926cabf fix: release the upstream when the client stops reading` 修掉了，用的正是本文初版预测的 `finish_stream_cleanup`。本工作树的调和已吸收该实现。

## 归用户

### D-2 合成窗口与人写文档的冲突

`docs/.human-controlled/config.example.yaml:404-409` 定义的窗口是「上游都没有响应头」且合成物是「半块」；实现从响应头**到达之后**才起算，且只发 `message_start`。**用户已表示会自行修订人写文档**，本项目侧不动实现，等文档定稿后再对齐。

## 已裁决，待实现

### D-3a `upstream_transport.tcp_keepalive_interval` 该怎么办 —— **用户裁决 A1**

**2026-08-20 用户裁决：实现成真的 `SO_KEEPALIVE`（A1）。** 下面的选项表保留备查。

实现这条时必须先证明的一件事：自建 `AsyncHTTPTransport` 会让 httpx 关掉 `HTTP_PROXY`/`HTTPS_PROXY` 支持（`httpx/_client.py:1399`），而人写文档明确规定了代理的优先级——**必须自己补回环境变量代理解析，并且用测试钉住它没有静默回归**。另需一个独立的连接池过期时长配置键（新键在人写文档里，落地时请用户过目）。顺带可以把 D-3b、D-3c 一并修掉，它们同在 `composition.py` 那几行。

名字承诺「TCP 保活间隔」，实际被换算成 `httpx.Limits(keepalive_expiry=...)`——那是**连接池里一条空闲连接能躺多久才被回收**，从不往 socket 写任何字节，且请求在飞期间根本不生效（`_expire_at` 为 `None`）。所以它在任何意义上都不是保活。

三个互斥选项：

| | 动作 | 代价 | 后果 |
|---|---|---|---|
| **A1** | 实现成真的 `SO_KEEPALIVE`（`AsyncHTTPTransport(socket_options=[SO_KEEPALIVE, TCP_KEEPIDLE, TCP_KEEPINTVL, TCP_KEEPCNT])`），并给连接池过期时长一个自己的键 | 中。**自建 transport 会让 httpx 关掉 `HTTP_PROXY`/`HTTPS_PROXY` 支持**（`httpx/_client.py:1399`），必须自己补回环境变量代理解析——而人写文档明写了该优先级。另需一个新配置键（在人写文档里，要用户点头） | 名实相符；上游腿获得当前唯一默认开启的活性探测 |
| **A2** | 只改名，承认它是连接池空闲过期时长 | 低，但**改的是人写文档**，只能由用户做 | 名实相符；上游腿继续没有任何活性探测 |
| **A3** | 保留现状加注释 | 极低 | 一个键继续承载两个不相干语义，下一个读它的人会再撞一次 |

**调查方的偏好是 A1**，理由不是「防中间设备掐断」——那条风险在本部署形态（直连、无代理、静默尺度差一个数量级、唯一观测到的连接死亡是 GOAWAY）判**低**——而是**上游腿的三道守卫当前全部失效**（两道默认关，第三道因 D-6 失效），`SO_KEEPALIVE` 是唯一成本可控、默认开启、不依赖猜测的活性探测。A3 被判为不可接受：它把一个已知的错误命名再冻结一轮。

`SO_KEEPALIVE` 的可行性已实测（带反向对照：设了读回 15/15/4，对照组读回 `SO_KEEPALIVE 0`）。

## 缺陷（无岔路，排期修）

### D-3b `0 = 禁用` 的语义在实现里是反的

`composition.py:73` 把 0 映射成 `keepalive_expiry=None`，而 `None` 让 `has_expired()` 的时间分支恒假，即空闲连接**永不**因超时被回收。人写文档写的是「0 = 禁用」，落地成了「关掉空闲回收」。

### D-3c 出站连接数当前无上限

`composition.py:82` 只传了 `keepalive_expiry`，`max_connections` / `max_keepalive_connections` 为 `None`，httpcore 换成 `sys.maxsize`。httpx 自己的默认与 `docs/2604-rewrite/streaming-resilience.md:245` 写的都是 100 / 20。

### D-3d `upstream_transport.http2_ping_interval` 无法实现，应固化为结论

httpcore 1.0.9 不提供发送 PING 的接口；h2 有 `ping()` 但 httpcore 从不调用、也无后台读循环。**缺能力的是 httpcore**，实现等于分叉传输层。键保留 + 现有「NOT IMPLEMENTED」标注即可，另需把 `docs/2604-rewrite/streaming-resilience.md:264-280` 那段伪代码改写成这个结论。

### D-3e `settings.py:73-74` 的 `upstream_keepalive` / `upstream_h2_ping` 是死键

零引用，非人写文档内容，且它们所在的 `AppSettings` 整体是不被服务的 legacy 配置面。删除不触碰任何已裁决的东西。

### D-5 `response_header_overrides` 被拿去覆盖 `upstream_request_deadline`

`src/app/server/handler.py` 把 `timeouts.response_header_overrides` 当作 `upstream_request_deadline` 的按模型覆盖表。这是两个不同的量。**正确写法唯一**：`attempt_deadline = timeouts.upstream_request_deadline`——不存在 `upstream_request_deadline_overrides`，人写文档与 schema 都没有这个概念。当前部署下**零行为变化**（两张覆盖表都是 `{}`），不碰红任何现有测试。

与之相邻但独立的两件事：`response_header` 这个守卫**从未实现**（工作项）；**要不要新增一张 deadline 覆盖表**（这一条才是裁决项，但优先级低，等有人真的需要按模型区分再提）。

### D-6 `upstream_request_deadline` 对流式请求实际不生效

`src/app/pipeline/direct_driver/base.py` 的 docstring 称该 deadline「bounds the whole attempt」。**这不是文档写错，是实现漏了**：`asyncio.timeout` 只包住 `await send`，流式请求拿到响应头即退出该上下文，body 由 `pipeline_app.py` 在上下文之外迭代。docstring 描述的正是人写文档 `config.example.yaml:308-314` 的语义（拦住一直滴水但永不结束的尝试），所以**只改 docstring 等于用实现判人写文档的负**。

与「绝不误杀合法长思考」不冲突：那条不变量管的是静默类终止器，且 1200s 远高于实测的客户端 300s 天花板。

**同一个病 `handle_bounded` 也有一份**，建议合成一个 slice 一起修。

## 暂缓

### D-4 `client_delivery.hedge` 只有配置项没有实现

用户已裁决：**未来做，目前暂缓**。它的触发条件字面上就是 `spec.md` §2 治理的下游静默，因此归在 §2 名下，不是相邻问题。

## 文档侧顺手项（无岔路）

`docs/2604-rewrite/streaming-resilience.md:284-288` 的配置表用的是旧 `AppSettings` 键名，与新链路的 `upstream_transport.*` 对不上；`:286` 的 `upstream.keepalive_expiry = 30` 也不是新链路的生效值。该表应按实际重写。

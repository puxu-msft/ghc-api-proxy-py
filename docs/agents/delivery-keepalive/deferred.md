# 待办与已知缺口

调查依据：`docs/tmp/260820-deferred-d3-d5-d6.md`（含实测探针与逐条读码）。

**分类口径**：「缺陷」= 正确做法唯一，不需要任何人裁决，排期做掉即可；「裁决」= 存在真实岔路，不同选择导向不同产品行为或不同代价。初版把若干缺陷错写成裁决项，已更正。

## 已解决

### D-1【已由并行会话修复】提前关闭交付不会及时释放上游

`main` 的 `926cabf fix: release the upstream when the client stops reading` 修掉了，用的正是本文初版预测的 `finish_stream_cleanup`。本工作树的调和已吸收该实现。

## 归用户

### D-2 合成窗口与人写文档的冲突

`docs/.human-controlled/config.example.yaml:404-409` 定义的窗口是「上游都没有响应头」且合成物是「半块」；实现从响应头**到达之后**才起算，且只发 `message_start`。**用户已表示会自行修订人写文档**，本项目侧不动实现，等文档定稿后再对齐。

## 已实现（`1a2daac`，本轮）

### D-3a `tcp_keepalive_interval` 实现成真的 `SO_KEEPALIVE` —— 用户裁决 A1

`SO_KEEPALIVE` 开启，`TCP_KEEPIDLE` 与 `TCP_KEEPINTVL` 取配置值，探测四次。上游腿因此有了它名字一直承诺、却从未有过的活性探测——**射程见本文「代理在场时 keep-alive 到底探的是谁」一节：直连时探的是上游本身，有代理时只到代理那一跳。**

A1 那个已知陷阱**已补偿并钉住**：自建 transport 会让 httpx 关掉 `HTTP_PROXY`/`HTTPS_PROXY`（`allow_env_proxies` 是 `trust_env and transport is None`），所以环境变量代理映射在 `composition.py` 里重建并挂载，由 `test_environment_proxies_are_still_honoured` 保证 httpx 改动这个私有辅助时会**红**，而不是代理支持静默消失。

**不新增任何配置键，也没有兼容范围要谈。** 这一点我先前搞错了，用户当场指出：所谓「连接池保留时长」**从来没有被裁决过**——它是这个 bug 的副产物，`tcp_keepalive_interval` 被错映射成 `keepalive_expiry`，于是碰巧产生了 15 秒。我却把这个副产物当成契约，为保住它新造了一个面向用户的键 `pool_idle_expiry`，还写了迁移规则。那是在给一个缺陷的意外行为立约，并擅自铸造配置面。

已撤销：`pool_idle_expiry` 删除，`composition.py` 不再向 transport 传 `limits`，池的一切回到 httpx 自己的默认。核对过用户亲笔 `docs/.human-controlled/` 里从未出现 `keepalive_expiry` / 池相关的任何裁决。

### D-3b `0 = 禁用` 的语义反转 —— 随错映射一并消失

反转本身是错映射的产物：一个名为「keepalive 间隔」的键，0 被映射成「连接池永不回收空闲连接」。错映射删掉之后，`tcp_keepalive_interval: 0` 就是字面意思——不开 keepalive。没有第二个键需要为 0 定义语义。

### D-3c 出站连接数无上限 —— 已修，且不是靠新配置

根因是「只传了一个字段的 `Limits`」：`httpx.Limits(keepalive_expiry=...)` 让另外两个值留成 `None`，httpcore 读成 `sys.maxsize`。现在**根本不传 `limits`**，httpx 自己的 100 / 20 / 5.0 就是生效值。不为此立任何配置项，也不写死任何数字。

## 已裁决

### D-3f SOCKS 路径的 keep-alive —— 用户裁决 S2：接受限制并告警

**用户 2026-08-20 裁决：接受这个限制，保留告警。** 当前代码已是这个形态：配置或环境里出现 SOCKS 代理且 keepalive 开启时，构造期发一条 warning，只记 origin 不记凭据。

原因：`AsyncSOCKSProxy` 根本没有 `socket_options` 参数——不是「传了没生效」（HTTP 代理那条是，已覆写修好），而是「没得传」。要覆盖它得接管 `AsyncNetworkBackend` 并自己构造 SOCKS 池。

### 一并厘清：代理在场时 keep-alive 到底探的是谁

用户在裁决时追问 SOCKS 路径的 `SO_KEEPALIVE` 是不是只能表示「我们 ↔ SOCKS 代理」。**是，而且这不限于 SOCKS。**

TCP keep-alive 是逐连接的，而代理会终结 TCP 连接。实测（`getpeername()`）：

| 形态 | socket 对端 | 这条 keep-alive 说明什么 |
|---|---|---|
| 直连 | 上游本身 | 上游还活着 |
| HTTP forward 代理 | 代理 | 到代理这一跳还活着 |
| HTTPS CONNECT 隧道 | **代理**（不是 TLS origin） | 同上 |
| SOCKS | 代理（当前读回 0，即什么也没探） | —— |

**所以「HTTP 代理路径的 keep-alive 已修好」这句话的射程只到第一跳**，代理到上游那一段是代理自己的 socket，我们既看不见也设不了选项。我先前把它说成「上游腿获得活性探测」是说过了头，已在 `schema.py`、`composition.py` 与本节更正。只有直连形态下这个键才谈得上探测上游本身——而本项目的部署形态正是直连。

## 已由并行会话接手

### D-3d `http2_ping_interval` 固化为结论 —— 已完成

并行会话已把 `http2` 拆成独立键，并给 `http2_ping_interval` 加上 NOT IMPLEMENTED 标注。剩下的只有文档侧那张表（见文末）。

### D-5 / D-6 上游超时语义 —— 并行会话正在做

2026-08-20 查看其未提交改动：`direct_driver/base.py` 已把 `response_header_timeout` 拆成独立参数（D-5 的错配），并把 `attempt.deadline_at` 固定成整次尝试的时刻、由交付链承担 body 那一段（D-6），docstring 也改成了与实测一致的说法。**我不重复做。**

## 已删除

### D-3e `settings.py` 的 `upstream_keepalive` / `upstream_h2_ping` —— 已被取代，已删

用户 2026-08-20 裁决：被取代就删。逐条核对确实被取代——原始意图在 `.dev/docs/archived-2604-rewrite/streaming-resilience.md:284-288`：

- `timeouts.upstream_keepalive`（「上游 TCP keepalive 首次探测延迟秒数」）→ 由 `upstream_transport.tcp_keepalive_interval` 取代，且该文档给出的代码草案（`SO_KEEPALIVE` + `TCP_KEEPIDLE 15` + `TCP_KEEPINTVL 15`）正是本轮实现的东西。
- `timeouts.upstream_h2_ping`（「上游 HTTP/2 PING 心跳间隔秒数」）→ 由 `upstream_transport.http2_ping_interval` 取代。**这一项为什么至今没实现**：httpx 不暴露周期性 PING 的接口，httpcore 1.0.9 从不调用 h2 的 `ping()`、也没有后台读循环，没有可挂接的点，实现等于分叉传输层。该文档当年已写到「需要在 httpcore 的连接对象层面接入」，本轮把它坐实为「在当前依赖版本上做不到」，并写进了 `http2_ping_interval` 的注释。

先前我用 `extra="forbid"`（删键会让写着它的配置加载失败）当理由挡下删除。那个风险是真的，但射程比我说的小：`AppSettings` 只从 `GHC_` 前缀的环境变量读，这两个键只出现在一份已归档的我方设计文档里，从未进入用户亲笔配置。

## 暂缓

### D-4 `client_delivery.hedge` 只有配置项没有实现

用户已裁决：**未来做，目前暂缓**。它的触发条件字面上就是 `spec.md` §2 治理的下游静默，因此归在 §2 名下，不是相邻问题。

## 文档侧顺手项（无岔路）

该文档已被并行会话移到 `.dev/docs/archived-2604-rewrite/streaming-resilience.md`，属归档件。其 `:284-288` 的配置表用旧 `AppSettings` 键名，且 `upstream.keepalive_expiry = 30` 从来不是生效值——但归档件记录的是当时的设计意图，不是当前事实，**不必回头改它**。当前事实以 `schema.py` 的注释与本文件为准。

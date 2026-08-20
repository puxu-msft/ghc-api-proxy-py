# 待办与已知缺口

调查依据：`docs/tmp/260820-deferred-d3-d5-d6.md`（含实测探针与逐条读码）。

**分类口径**：「缺陷」= 正确做法唯一，不需要任何人裁决，排期做掉即可；「裁决」= 存在真实岔路，不同选择导向不同产品行为或不同代价。初版把若干缺陷错写成裁决项，已更正。

## 已解决

### D-1【已由并行会话修复】提前关闭交付不会及时释放上游

`main` 的 `926cabf fix: release the upstream when the client stops reading` 修掉了，用的正是本文初版预测的 `finish_stream_cleanup`。本工作树的调和已吸收该实现。

## 归用户

### D-2 合成窗口与人写文档的冲突 —— 两条里已消解一条

权威表述在 `spec.md` §2.2 的【需用户裁决】块，本条只作索引。**不引行号**：该文件正被用户持续修订，行号已失效过一次。

- **窗口定义仍冲突。** 人写文档说的是「若很久上游都没有响应头」，实现的计时从响应头**到达之后**才起算。**待用户裁决**，未裁之前实现维持现状。
- **合成物已不冲突。** 用户 2026-08-20 已把中文原文改成「合成 HTTP 200 以及一个 `message_start`」，与实现一致。（英文半句仍写 `half-block`，见下方「交还用户的文档问题」一节。）

## 已实现（`main` 上的 `52d877c`，本轮）

> **不要去看 `1a2daac`。** 本节初版把标题挂在它上面，那是这条归档链（`archive/260820-upstream-keepalive`）的**第一个**提交，也正是用户裁决 7、8 推翻掉的那一版——它当时新造了 `pool_idle_expiry`、整份传 `Limits`、并且只给两个 legacy 键加注释而没有删。真正落地的形态是 `main` 上的 `52d877c`（隔离树里的源提交是 `e12003a`，tree 与提交信息逐字节相同）。

### D-3a `tcp_keepalive_interval` 实现成真的 `SO_KEEPALIVE` —— 用户裁决 A1

`SO_KEEPALIVE` 开启，`TCP_KEEPIDLE` 与 `TCP_KEEPINTVL` 取配置值，探测四次。上游腿因此有了它名字一直承诺、却从未有过的活性探测——**射程见本文「代理在场时 keep-alive 到底探的是谁」一节：直连时探的是上游本身，有代理时只到代理那一跳。**

A1 那个已知陷阱**已补偿并钉住**：自建 transport 会让 httpx 关掉 `HTTP_PROXY`/`HTTPS_PROXY`（`allow_env_proxies` 是 `trust_env and transport is None`），所以环境变量代理映射在 `composition.py` 里重建并挂载。钉住它的护栏是 `test_environment_routing_matches_native_httpx`（`tests/unit/server/test_http_client_build.py`），它对四个目的地逐个与**原生 httpx 的路由结果**比对。

（本节初版点的是 `test_environment_proxies_are_still_honoured`。那个测试**已经不存在了**：`review-transport-keepalive.md` 判定它几乎没有分辨力——只设一个 `HTTPS_PROXY`、然后断言「有某个非空 transport 匹配上了」，这对大量错误答案同样成立——因而被删除重写。把一个被判无效的测试当作「已钉住」的证据挂在这里，是本文自己犯的同一类错误：**证据名要指向现在跑得起来的那一个**。）

**不新增任何配置键，也没有兼容范围要谈。** 这一点我先前搞错了，用户当场指出：所谓「连接池保留时长」**从来没有被裁决过**——它是这个 bug 的副产物，`tcp_keepalive_interval` 被错映射成 `keepalive_expiry`，于是碰巧产生了 15 秒。我却把这个副产物当成契约，为保住它新造了一个面向用户的键 `pool_idle_expiry`，还写了迁移规则。那是在给一个缺陷的意外行为立约，并擅自铸造配置面。

已撤销：`pool_idle_expiry` 删除，`composition.py` 不再向 transport 传 `limits`，池的一切回到 httpx 自己的默认。核对过用户亲笔 `docs/.human-controlled/` 里从未出现 `keepalive_expiry` / 池相关的任何裁决。

### D-3b `0 = 禁用` 的语义反转 —— 随错映射一并消失

反转本身是错映射的产物：一个名为「keepalive 间隔」的键，0 被映射成「连接池永不回收空闲连接」。错映射删掉之后，`tcp_keepalive_interval: 0` 就是字面意思——不开 keepalive。没有第二个键需要为 0 定义语义。

### D-3c 出站连接数无上限 —— 已修，且不是靠新配置

根因是「只传了一个字段的 `Limits`」：`httpx.Limits(keepalive_expiry=...)` 让另外两个值留成 `None`，httpcore 读成 `sys.maxsize`。现在**根本不传 `limits`**，httpx 自己的 100 / 20 / 5.0 就是生效值。不为此立任何配置项，也不写死任何数字。

## 未解决（缺陷，无岔路，排期做掉）

### D-7 proxy 优先级无法实现：三个来源在 `load_proxy_config()` 里被压平，没有 provenance

**这一条被声称「已记入本文」三次，实际一次都没写进来。** 第一次是我在协调消息里说的，`review-transport-keepalive-r3.md` 的 R3-F2 查了 commit tree 与工作树、指出没有；第二次仍未落盘；第三次是生产测试 `tests/unit/server/test_http_client_build.py::test_an_explicit_proxy_reaching_httpx_shuts_the_environment_out` 的 docstring 里写着「Recorded in `docs/agents/delivery-keepalive/deferred.md`」——而本文里依旧没有。现在写下来。

**缺口本身**：用户亲笔 `docs/.human-controlled/config.example.yaml` 规定的优先级是 CLI `--proxy` > `HTTP_PROXY`/`HTTPS_PROXY` > 配置文件 `proxy`。但 `load_proxy_config()` 把 CLI、`GHC_PROXY` 与 YAML 三个来源压平进同一个字段，**不保留任何来源信息**，于是下游无从分辨「这个 proxy 是命令行给的还是配置文件给的」，也就无法把环境变量插在两者中间。当前实际行为是：只要 `config.proxy` 非空就走它、且完全不看环境变量（httpx 语义下等于 `all://`），环境变量因此永远排在配置文件之后，与人写文档规定的顺序相反。

**它先于本轮改动存在**，本轮没有引入也没有修复。之所以不顺手修：修它要改的是配置加载的数据形状（给 proxy 带上来源标记），那是另一条链路的接口改动，与保活无关；而 `test_an_explicit_proxy_reaching_httpx_shuts_the_environment_out` 之所以刻意**不**按那条产品规则命名，正是为了避免把「httpx 面向的行为」冻结成「产品优先级规则已实现」。

**分类**：缺陷，不是裁决点——正确做法唯一（让优先级与人写文档一致），只是要排期。

## 交还用户的文档问题（我方不改人写文档）

按裁决 2，`docs/.human-controlled/` 由用户自行修订，我方不改。以下两处是我方在核对时发现、但**不属于我方能改的范围**，记在这里而不是默认用户会自己发现：

1. **`synthesized_response_headers_after_sec` 的中英不一致。** 用户已把中文改成「合成 HTTP 200 以及一个 `message_start`」（与实现一致），但同一条目的英文半句仍是 `synthesize a half-block to the client`。
2. **`http2_ping_interval` 仍被描述成一个生效的保活。** 该键在人写配置文档里写作「HTTP/2 PING 保活间隔（0 = 禁用）」，默认 15，没有任何未实现标注，读起来就是开着的。我方 `schema.py` 的注释已把「做不到、为什么做不到」写清楚，但那是我方 schema，不是用户会读的那一份。见下方 D-3d。

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

并行会话已把 `http2` 拆成独立键，并给 `http2_ping_interval` 加上 NOT IMPLEMENTED 标注。剩下的只有文档侧那张表（见「文档侧顺手项」一节）。

### D-5 / D-6 上游超时语义 —— 已由并行会话完成，但**是两个提交**

两条都修好了，修它们的不是同一个提交，这一点值得写准，因为本文档的价值就在这本账上：

- **D-5**（`064ba63 fix: refuse a search this endpoint cannot run…`，17:51）：`upstream_request_deadline` **被 `response_header_overrides` 解析**——运维给某个模型调低 header 等待，实际砍掉的是那个模型的整次尝试。`handler.py` 里的 `resolve_timeout(route.model_id, timeouts.upstream_request_deadline, timeouts.response_header_overrides)` 已改成直接读它自己那个字段。同一个提交也把 `stream_idle_seconds` 的 overrides 解析去掉了。
- **D-6**（`783f023 fix: make each of the three upstream timeouts guard the phase it names`，18:09）：body 不在 deadline 之内。`attempt.deadline_at` 在 `direct_driver/base.py` 里被固定成整次尝试的一个时刻，header 等待与 `pipeline_app.py` 的 body 流读同一个值——**一个上界，两处执行**。这个提交同时删掉了 `schema.py` 里的两个 override 字段。

**初版这里写反了主语**：把 D-5 写成「`response_header` 被 `response_header_overrides` 解析」。那按字面是覆盖表的正常用法、根本不是缺陷，而且与紧随的「等于用一个 header 守卫去砍整次尝试」自相矛盾——后半句只有在被覆盖的是 deadline 时才成立。权威定义见 `docs/tmp/260820-deferred-d3-d5-d6.md` §2 的标题。**`response_header` 无消费方是同一节里的另一件事**（一道从未实现的守卫），不要与 D-5 并成一条。

**D-6 的修复推翻了 `spec.md` §2.2 的一整段断言**（它说 `upstream_request_deadline`「恰好且仅仅覆盖首字节前那一段」），spec 已同步更正。记这一笔是因为：D-6 修好之后 1200s 从「首字节前的静默上界」变成了「整次尝试的总时长上界」，任何据前者做出的调参判断都不再成立。

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

## 合入后复评查出的三条 —— 已修

评审报告：`review-merged-upstream-keepalive.md`（异源模型，真实 socket 与真实连接池探针）。派这一轮的直接原因是：上游 slice 的代理修复机制在评审通过**之后**被换掉过（替换池 → 只补 `create_connection`），换掉的那一版没有任何人审过。逐参数比对的结论是新机制在 httpcore 1.0.9 上没有漏传或错传，但同时查出下面三条。

### D-8【中等，已修】同一个池按 `NO_PROXY` mount 数被反复包装，长列表触发 `RecursionError`

这是我扩展 `cap_streams_per_connection` 去覆盖 mounts 时引入的。`_proxy_mounts` 有意让所有 `NO_PROXY` 规则共享同一个 direct transport，而 cap 不按对象身份去重，于是每条规则都给同一个 `create_connection` 再套一层。

**数值上没错**——池只把 request 赋给最外层 wrapper，内层因身份不同恒计 0，只继续委托，所以限流值仍是对的。**但层数随规则数线性增长**：1100 条合法 `NO_PROXY` 规则（几十 KiB 的环境变量，完全正常）下，`create_connection` 在**任何网络 I/O 之前**稳定抛 `RecursionError`。也就是说这个缺陷的表现不是「限流不准」，而是「一个普通配置直接让请求发不出去」。

修法是按 `id()` 去重后每个池只 `_cap_one` 一次。用 `id()` 而不是 `set()` 是刻意的：这里要的是**同一性**，而 `set` 表达的是相等性；transport 今天没有 `__eq__`，两者一致，但若将来 httpx 给它加上值相等，`set` 会把两个不同的池折叠掉、让其中一个**静默失去限流**——那正是 `stream_cap` 整个模块在防的失效形态。

回归：`test_one_pool_is_capped_once_however_many_mounts_reach_it`（断言包装层数，且先断言「确实有多个 mount 且确实是同一个对象」以防空过）与 `test_a_long_no_proxy_list_still_opens_a_connection`（1100 条，钉住用户可见的那个故障）。两条都已验证在修复前变红。

### D-9【低，已修】两个 `create_connection` 补丁的顺序没有被回归锁住

我的 keep-alive 补丁与 `stream_cap` 的 cap 补丁**改的是同一个方法**，谁后装谁在外层。当前顺序（keep-alive 先、cap 后）是对的，两者叠加。但**反序不会报错**：keep-alive 闭包会直接盖掉 cap 闭包，cap 从此不可达，而 socket options 依旧完全正确——于是本文件里每一条 keep-alive 断言照样通过。实测反序后 CONNECT/H2 路径由 4 条隧道（`[2,1,1,1]`）退化成 1 条（`[5]`）。

已补两半：`build_http_client` 里写下顺序约束与反序后果，以及回归 `test_a_proxy_pool_keeps_both_the_cap_and_the_keepalive`（同时开启两项，断言代理池产出的仍是 capped wrapper 且其连接带着 `SO_KEEPALIVE`）。已验证在接缝处模拟反序时变红。

### D-10【低，已修】SOCKS 告警对 IPv6 输出的不是合法 origin

`_origin_of` 用 `parsed.host` 拼串，而 httpx 返回不带方括号的 IPv6 host，于是 `socks5://user:secret@[::1]:1080` 被打印成 `socks5://::1:1080`——读回时 httpx 直接抛 `InvalidURL: Invalid port: ':1:1080'`。凭据确实没有进日志，这不是泄漏，是「声称打印 origin 而打印的不是」。已加方括号，回归 `test_the_socks_warning_prints_an_ipv6_origin_that_can_be_read_back` 断言的是**能否读回**（host 与 port 各自解析正确）而不是字符串相等。

同一个表达式还有第二处边界，由复评查出并一并修掉：端口的存在与否用的是**真值判断**而不是 `is not None`，于是显式的 `:0` 被当成「没有端口」丢掉（httpx 会把 `:0` 解析成整数 0）。端口 0 不是可工作的代理目的端口，所以影响限于诊断输出失真，但那正是这个函数唯一的职责。回归 `test_the_socks_warning_keeps_an_explicit_port_zero`，已验证退回真值判断时变红。

### 未采纳的建议

评审建议 D-9 的回归「用可复用的 H2 CONNECT fixture 断言每连接 batch 请求数不超过 cap」。**采纳了它的判断，没有采纳它的手段，理由限定在范围与 ROI，不是两个判据等价。**

D-9 要防的是「两行被调换」。就这一个目标而言，`create_connection` 返回的是不是 capped wrapper 已经是充分判据——反序时代理池必然产出裸 `AsyncTunnelHTTPConnection`，实测已确认（受控反序变异下该回归变红，红的原因正确）。

**但 wrapper 形状断言与真实并发上界不是同一个性质，这一点我先前写错了。** 复评逐条列出了并发断言**额外**能抓、而当前判据抓不到的四种失效形态：① `build_http_client` 仍装 wrapper 但把错误的 cap 数值传下去（配 2 传 999，只看类型仍会通过）；② wrapper 还在，但 `assigned_request_count()` 与真实 `AsyncHTTPProxy` 池的 bookkeeping 脱节，或未来 httpcore 让代理池走另一条分配路径；③ 被检查的池仍产出 wrapper，但请求路由以后改走别的 transport 或池（当前显式 proxy 下 `_mounts == {}`，所以今天不存在这个缺口）；④ wrapper 与 socket options 都在，但 CONNECT / TLS / ALPN / H2 multiplexing 的接缝变化使池不再按 wrapper 的 availability 答案控制每条隧道的并发数。

不新建 fixture 的理由因此是：**这四种形态里，核心调度机制已由 `test_the_real_pool_opens_another_connection_once_one_is_full` 这条真实池并发测试覆盖，剩下的是代理特化路径的未来漂移；在本次任务里为它新建一套 CONNECT 并发 fixture，额外收益不足以抵偿复杂度。** 这是范围取舍，不是证明力等价——若将来代理路径的接线真的改动，应当补这条 fixture。评审给出的真实连接数分布（当前顺序 `[2,1,1,1]`、反序 `[5]`）记在这里备查。

# 评审处置：多 provider 路由

四轮独立评审，48 条发现。本文记录每一条的处置，包括**不采纳的**与其理由。

| 轮次 | 对象 | 报告 | 发现 |
|---|---|---|---|
| 1 | Spec v1 事实对账 | [reports/260827-spec-review-facts.md](reports/260827-spec-review-facts.md) | 1 major、7 minor |
| 2 | Spec v1 规则完备性 | [reports/260827-spec-review-rules.md](reports/260827-spec-review-rules.md) | 1 blocker、8 major、10 minor、3 建议 |
| 3 | 实现 `bb1c5f5` 独立验收 | [reports/260827-impl-verify.md](reports/260827-impl-verify.md) | 1 major、2 minor（65 条判据 60 通过、2 未验证） |
| 4 | 实现 `bb1c5f5` 代码评审 | [reports/260827-impl-review.md](reports/260827-impl-review.md) | 3 major、9 minor、3 nit、3 建议 |

## 第 1、2 轮：Spec 的 27 条

**全部采纳**，逐条记入 `spec.md` 自己的「条款修订记录」表，不在此重复。两条值得单独点名，因为它们推翻的是本 Spec 作者的推导而非细节：

- **facts-01 / F-04（两轮独立发现同一条）**：首版断言「passthrough 的名字从来不会真的发给上游」，据此论证「保持 `resolved = requested` 没有可观察后果」。**假的。** `describe()` 查的是 `resolved`，而 passthrough 把它设回原始请求名，所以原始名本身可用时请求照常发出、映射被静默放弃。规则评审给的例子不需要构造：随包 `claude-opus-4.5: claude-opus-5` 在缺 `claude-opus-5` 的账号上即触发。结论（维持既有行为）不变，理由整段重写。
- **F-01（blocker）**：首版 §3 规定「请求侧命中后走现有的别名解析」，而现有解析对值一无所知，会把 `A/claude-opus-5` 整串当模型名去查目录——在 §6.2 推荐的配置形态下 `A/opus` **必然** `UnknownModel`，恰好否掉这条语法存在的理由。新写 §3.1 的三条规则。实现当时恰好没踩这个坑，但 Spec 规定的是一个会失败的做法。

## 第 3、4 轮：实现的 21 条

### 采纳并已修

| # | 严重度 | 问题 | 处置 |
|---|---|---|---|
| CFG-08 | major | schema 接受 `A/B` 与 `""` 作为 provider 名，两者都无法被限定语法引用；空名还反转了 §5.1.2 | `ProxyConfig` 校验期拒绝，Spec §2.1 补上「由配置边界强制」 |
| MPR-01 | major | 每 provider 的 httpx client 从无关闭路径——`Chain.aclose()` 零调用者 | 三个入口（两个 serve + `collect_catalogs`）在 `finally` 调用；`Chain.aclose()` 改为只关自己创建的，所有权划清 |
| MPR-02 | major | `build_chain` 构造中途抛异常时已建 client 不可达，而新的 dangling fallback 校验必然踩到 | 把不需要分配的校验（provider type、default/fallback 名字存在）全部前移到建 client 之前 |
| MPR-03 | major | `refresh_catalogs` 无隔离，次要 provider 的过期 token 能让 default 终身 503 | 逐 provider 保护 + `sorted` 顺序；新增 Spec §8.4 |
| impl-verify-02 | minor | WARN 说「会走 fallback」却不说是哪个 | `inspect_mappings` 改收 fallback 名而非 bool |
| MPR-04 | minor | 配置侧 `RoutingError` 报 mapping 的键，而指名坏 provider 的是值 | 消息改报值，`ProviderDiscovery` 加 `value` 字段承载它 |
| MPR-05 | minor | `serviceable` 的 `disabled` 判定用精确匹配，周围每处都折叠 | 改用 `canonical` 比较 |
| MPR-06 | minor | 环 WARN 报折叠后的键名，运维 grep 配置找不到 | 比较用折叠形式、报告用原始拼写，两个并行列表 |
| MPR-09 | minor | `driver.py` 一处 docstring 漏改 `ghc` | 改 |
| MPR-10 | minor | SOCKS 警告每 provider 各打一遍 | `build_http_client` 加 `warn_about_proxies`，per-provider 循环关掉 |
| MPR-11 | minor | `_report_for` 不剥 `@format`，路由表与真实请求给出不同答案 | 加 `split_format_suffix`，与 `decide_route` 同序 |
| MPR-12 | minor | `hosted_web_search.py:90` 的陈旧引用（Spec §8.3 点名要修，实现漏了） | 改，并说明 `or default_provider` 已是不可达的 fail-closed 底线 |
| nit-1 | nit | `test_error_classify.py` 仍构造 `ghc:0:...` 的 trail 条目 | 改 |

每条都配了回归测试，除 MPR-10（纯日志噪音，无断言价值）与 MPR-09 / MPR-12（注释）。

### 采纳但只做一半

- **MPR-07**（`route_table` 的 docstring 两处失实 + 每请求 O(N²)）。**注释改成事实**——撤销了「linear」与「有 background refresh」两个说法，换上实测数字（2 × 81 条目 2.5 ms，2 × 161 条目 12 ms）。**性能只做了 `available_ids` / `disabled_ids` 的重复读取合并（每行 3 次 → 1 次）**，没有按建议把 `_index(mappings)` 提到循环外。

  不做的理由：那需要给 `discover_provider` 加一个预建索引参数，而它是**每个请求都走的热路径**；为两个低频、且都在准入闸门内的端点改热路径函数的签名，代价与收益不匹配。真到目录规模成为问题时，正确的做法是给 `route_table` 加缓存并在 `replace_catalog` 时失效，那是一个独立改动。

### 采纳其观察、不改代码

- **MPR-08**（`Route.provider_origin` 写了没人读，注释却说 `/api/status` 在读它）。**只改注释**，字段保留。项目的 `richest-context-flow` 说携带比丢弃好，而这个字段是路由决策已经产出的事实；问题从来不是字段存在，是注释把一个不存在的消费者写成了事实。

### 不采纳

| # | 建议 | 不采纳的理由 |
|---|---|---|
| nit-2 | `inspect_mappings` 不检查空 **键**，`"": "A/x"` 在路由表、`/v1/models` 与启动 WARN 里三处皆不可见 | 空键在 YAML 里罕见，且它不可能被任何请求命中（入站空模型名先被拒）。加一条检查是可以的，但它属于「mapping 表的静态卫生」这个更大的题目，不该只补这一个孔。**记入 `deferred.md`。** |
| nit-3 | `inspect_mappings` 用 `config.model_providers` 的键，路由用 `providers.names`；`build_chain(providers=...)` 注入路径下两者可以不一致 | 只在测试注入路径可达。生产路径下两者同源。改它要给 `build_chain` 增加一条「注入的 providers 必须与配置一致」的约束，那是给测试便利加生产约束。 |
| 建议 1 | `fallback_model_provider` 应与 `default_model_provider` 一起进 `NOT_HOT_RELOADABLE` | 评审自己指出 `default_model_provider` **今天也不在那张表里**，而热重载在这条链上根本没接（`ConfigProvider` / `pin_restart_only` 零消费者）。只加新键会造成「两个同类键一个在表内一个在表外」的不一致，比都不加更难读。热重载真接上时两个一起加。 |
| 建议 3 | `build_chain` 的 provider 循环加 `try/except` 关掉已建 client | `build_chain` 是同步函数，`AsyncClient.aclose()` 不是——同步上下文里没有正确的关闭写法。改成 async 会波及 32 个调用点，其中多数是同步的测试 fixture。改用「前移抛出点」（MPR-02 的处置），并在注释里写明剩余风险的实际大小：这些 client 从未发过请求，连接池是空的，泄漏的是会被 GC 回收的 Python 对象而不是 socket。 |

### 未验证，如实记录

- **ISOLATION-01 / ISOLATION-02**：连接池隔离与凭据隔离**没有运行证据**，只有结构证据（两个不同的 `AsyncClient`、各自装了 stream cap、`aclose` 后都关闭）。用户裁掉了真实双账号 canary，本环境也没有第二份凭据。已写入 Spec §10.2，措辞明确说「以免后来者从『测试全绿』读出它已被验证过」。

## 一处需要用户裁决的范围问题

MPR-03（`refresh_catalogs` 无隔离）**涉及既有代码**，不在 `bb1c5f5` 的 diff 内。评审把「要不要在本次修」列为范围裁决。

**我判定在范围内并已修**，理由：改动前配第二个 provider 没有任何意义（Spec §0），所以这个失效形态是**本次特性把它变成可达的**；而且它直接推翻 §4.3 那条已被用户裁决的判据所依赖的前提。若用户认为应当拆成独立改动，回退它只需还原 `refresh_catalogs` 一个函数与 `tests/unit/server/test_catalog_refresh.py`。

# 实现评审：`bb1c5f5` 多 provider 路由

**评审范围**：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing` 分支 `worktree-multi-provider-routing` 的 HEAD 提交 `bb1c5f5`（29 文件 +1260/-134）。评的是**代码本身**：正确性、资源与并发、错误处理、可维护性、与项目既有约定的一致性。判据来源：`.dev/docs/multi-provider-routing/spec.md`（v1 + 条款修订记录，读于评审开始、读实现之前）、项目 `CLAUDE.md` 与 `.claude/rules/00-development-workflow.md`、以及仓库内既有的同类实现（`resolve_provider_base_urls`、`admission.py`、`config/provider.py`）作为一致性参照。

**明确不在范围内**：实现是否符合 Spec 的行为（另一位验收者在做）；`docs/.human-controlled/` 的候选材料；`.dev/` 文档本身的质量；测试是否覆盖 Spec 每一条验收项。

**总体 verdict**：`needs-fix`

**blocker 数**：0

严重度按实际影响判，不按修复行数。下面每条都给了一个**会真的发生的触发输入**；标 `[已实测]` 的条目附有可复现探针，脚本在 `/home/xp/.claude/jobs/0e3de57b/tmp/`。

---

## ⚠ 评审期间工作树发生了并发改动，MPR-01 正在被修

**必读，否则下面的 MPR-01 会被当成陈旧信息。**

我在评审开始时查过 `git status --short`，工作树是干净的。写完报告主体后再查，出现了未提交的修改，而且在我核对期间还在继续增长。**下面描述的是一个快照**：`2026-08-27T06:48:26Z`，`git diff | git hash-object --stdin` = `349f9c81307d42b219133bcab978827f2a503d80`。这类观察保质期以分钟计，复核前请重测。

该快照包含四个文件：

```
 M src/app/cli.py
 M src/app/config/schema.py
 M src/app/core/chain.py
 M src/app/debug/models.py
```

- `cli.py` + `core/chain.py`：正是 MPR-01 的修复。两个 serve 入口各加 `chain: Chain | None = None` 与 `finally` 里的 `if chain is not None: await chain.aclose()`；`Chain.aclose()` 同时改成**不再**关 `http_client`，改由 `cli.py` 在同一个 `finally` 里关（顺序先 chain 后 http_client）。`Chain` 在 `cli.py:18` 已 import，写法成立。
- `debug/models.py`：同一形状的修复补到了 `collect_catalogs`，所以我原先说的 “`debug/models.py` 那条腿没被碰” 在这个快照里**已经不成立**。
- `config/schema.py`：新增 `_reject_unaddressable_provider_names`，在配置边界拒绝含 `/` 或空白的 `model_providers` 键。这是我没有报告的一类缺陷（我只从值侧与请求侧考虑过含斜杠的名字，见排除方向），补得对。

**这不改变本报告对 `bb1c5f5` 的判定** —— 被评对象是那个提交，不是工作树。对调用方直接可用的结论有两条：

1. **MPR-01 在这个快照里看起来已被完整关闭**（两个 serve 入口 + `debug/models.py`）。请按 `git diff` 自行复核，不要凭本节；我没有把这份未提交改动纳入评审。
2. **MPR-02 在这个快照里完全没有被触及。** `build_chain` 构造中途抛异常时 `chain` 仍是 `None`，三处 `finally` 里的 `if chain is not None` 恰好全部跳过，已建的 client 照旧不可达。新增的那个 schema validator 反而**多了一个抛出点**（不过它在 `ProxyConfig` 校验期抛，早于 `build_chain`，所以不加重 MPR-02）。

我没有对这四个文件做任何操作。若调用方希望我对这份修复本身出复核意见，需要它先落到一个提交上，或明确授权我评审未提交状态。

---

## major

### MPR-01 · 每 provider 的 httpx client 从来没有被关闭过 `[已实测]`

> **状态提示**：评审期间同伴已在工作树上修这一条（未提交）。按 `2026-08-27T06:48:26Z` 的快照，两个 serve 入口与 `debug/models.py` 都补上了 `chain.aclose()`，看起来已完整关闭；详见文首的并发改动一节。下面的描述与证据针对的是 `bb1c5f5` 本身，取证时工作树是干净的。

**主位置**：`src/app/core/chain.py:57-61`
**相关位置**：`src/app/server/composition.py:464-472`、`src/app/cli.py:144-176`、`src/app/cli.py:184-198`、`src/app/debug/models.py:230-260`、`src/app/server/pipeline_app.py:54-86`

本次给每个 provider 建了独立的 `httpx2.AsyncClient`，并把清理逻辑加进了 `Chain.aclose()`：

```python
    async def aclose(self) -> None:
        # Providers first, then the client the caller handed in. Each provider's client is this chain's to close because this chain created it; ...
        for client in self.provider_clients.values():
            await client.aclose()
        await self.http_client.aclose()
```

`Chain.aclose()` **在 `src/` 与 `tests/` 里没有任何调用者**。三个真实入口 —— `cli.serve_inherited`、`cli._serve_pipeline`、`debug.models.collect_catalogs` —— 的 `finally` 都只写 `await http_client.aclose()`，关的是调用方自己造的那一个；`pipeline_app._lifespan` 的收尾只做 `chain.tokenization.flush()`。也就是说 `provider_clients` 里的 N 个 client 在进程正常退出时全部处于未关闭状态。

`Chain.aclose` 在本次改动前就已经是死方法（diff 只是往里加了行），但**本次新增的资源把它当成了唯一的回收路径**，而 `chain.py` 的注释明写 “held here so shutdown can reach them”、“`http_client` is closed here too and again by whoever built it, which httpx tolerates” —— 这两句描述的都是不会发生的事。

实测（`probe_lifecycle.py` 第 1、4 节）：两 provider 配置下 `chain.provider_clients == ['A', 'B']`，两者 `is_closed` 均为 `False`，且对象被回收时 **httpx 不发 `ResourceWarning`**，所以泄漏是完全静默的。

**触发输入**：任意两 provider 的正常部署，收到 SIGTERM 走 graceful shutdown。后果是 upstream 的 keep-alive 连接不被主动关闭，由进程退出交给内核处理；`report_shutdown` 关心的 `severed_connections` 这类指标看不到它。`debug/models.py` 那条路更直接：真正发出目录请求的是 provider client，`finally` 关掉的却是没发过请求的那一个。

**修复方向（交调用方裁决）**：要么在三处入口把 `chain.aclose()` 接进 `finally`（注意 `debug/models.py` 里 `chain` 的作用域），要么让 `_lifespan` 在 `yield` 之后关闭 chain。前者与 `cli.py:182` 的既有原则（“whoever creates it has to close it”）一致。

---

### MPR-02 · `build_chain` 中途抛异常时，已建的 provider client 全部泄漏；而本次新增的启动校验恰好在循环之后抛 `[已实测]`

**主位置**：`src/app/server/composition.py:464-492`
**相关位置**：`src/app/server/composition.py:539-545`（`ProviderRegistry(..., fallback=config.fallback_model_provider)`）

循环里先 `client = build_http_client(...)`、`provider_clients[name] = client`，再做可能抛异常的构造。没有 `try/finally`，`Chain` 尚未存在，所以已建的 client 无人可关、也无引用可达。

本次改动新增了一个**必然发生在循环全部完成之后**的抛出点：`ProviderRegistry.__init__` 对 dangling fallback 抛 `ProviderNotConfigured`（`registry.py:35-36`）。也就是说 “dangling fallback 在启动时失败” 这条新特性，每次生效都会顺带泄漏 N 个 client。

实测（`probe_lifecycle.py` 第 2、3 节）：

- `fallback_model_provider: typo` + 两个 provider → `no model provider named 'typo' is configured`，此时 A、B 两个 client 已建成且不可达。
- 第二个 provider 的 `type` 非法 → `unsupported provider type 'not_a_provider'`，第一个 provider 的 client 已建成一轮。

**触发输入**：`fallback_model_provider: typo`（写错一个字母），两 provider 配置。

**影响评估**：这条路上进程随后就会退出，所以运行期危害小于 MPR-01；把它记为 major 而非 minor 的理由是它与 MPR-01 同源（`build_chain` 造的东西没有任何一条可靠的回收路径），修 MPR-01 时如果只接一个 `chain.aclose()` 而不管构造失败路径，这一半仍然开着。最省事的写法是把循环体包进 `try`，失败时关掉 `provider_clients` 里已有的。

---

### MPR-03 · `refresh_catalogs` 没有 per-provider 隔离：一个次要 provider 挂掉可以让 **default** provider 的目录永远加载不上 `[已实测]`

**主位置**：`src/app/server/composition.py:553-562`
**相关位置**：`src/app/server/pipeline_app.py:66-72`、`src/app/server/routes/ops.py:29-38`

```python
    for name in chain.providers.names:
        await chain.providers.get(name).refresh_catalog()
```

`refresh_catalog()` 会抛（`github_copilot.py:141` 的 `request_headers()` 在没有 token 时抛，`fetch_models` 的网络错误也抛）。循环没有 try/except，第一个抛的 provider 直接终止整趟；`_lifespan` 把它吞成一句 warning，进程照常启动。

`chain.providers.names` 返回 `frozenset`，**迭代顺序由哈希决定、不由部署选择**。次要 provider 排在前面时，default provider 的 `refresh_catalog()` 根本不会被调用。

实测（`probe_refresh.py`，两种顺序各跑一次）：

```
  order=('B', 'A')  raised='A: no GitHub token'  default provider B loaded: True
  order=('A', 'B')  raised='A: no GitHub token'  default provider B loaded: False
```

而本次新增的 `_is_ready` 判据正是 `bool(chain.providers.default.available_ids)`，于是 `/health/readiness` 恒 503。更糟的是**没有任何东西会重试**：`refresh_catalogs` 只在 `_lifespan` 里调一次，`ghc_client/models.py:45` 的 `run_model_refresh_loop` 在全仓**没有调用者**，`model_refresh_interval` 这个配置键在这条 chain 上没有消费者。所以这是进程终身的 503。

这直接打脸 Spec §4.3 选择 `bool(default)` 而否决 `all()` 的理由（“一个次要 provider 挂了只影响被显式限定到它的那部分请求，那是**降级**，不是不可用”）：readiness 的判据是对的，但把目录填进去的那条路没有相应的隔离。

**触发输入**：两个 provider（default=B，次要 A），A 的 `github_token_file` 不存在或已过期；`frozenset({"A","B"})` 迭代先给出 A。

**说明其归属**：`refresh_catalogs` 本身不在本次 diff 里，是既有代码。但在本次改动之前，配第二个 provider 没有任何意义（Spec §0：“配置层允许配两个，路由层不支持按模型分流”），所以这个失效形态是**本次特性把它变成可达的**。要不要在本次修，交调用方裁。同一模块里的姊妹循环 `resolve_provider_base_urls`（`composition.py:349-397`）已经做了逐 provider 的 `continue`，是现成的样板。

---

## minor

### MPR-04 · 配置侧限定认不出时，`RoutingError` 报的是 mapping 的**键**，而键并不指名任何 provider `[已实测]`

**主位置**：`src/app/pipeline/routing.py:110-124`（`_fallback_name` 的消息）
**相关位置**：`src/app/pipeline/routing.py:151`（`_fallback_name(providers, discovery.matched_key or model_name)`）

实测（`probe_routes.py` 第 1 节），配置 `model_mappings: {claude-opus-4.8: a/claude-opus-5}`、未配 fallback，请求 `claude-opus-4.8`：

```
'claude-opus-4.8' names a model provider this deployment does not configure, and no `fallback_model_provider` is set to catch it (configured providers: A, B)
```

`claude-opus-4.8` 是**键**，指名坏 provider 的是**值** `a/claude-opus-5`。这句话字面为假，且会把运维引去检查键。这正是 Spec §5.2 花一整节要消灭的失效形态（“只报 `claude-opus-4.8` 会把人引去检查别名**键**有没有写错，而错的是值”）—— `UnknownModel` 那一侧照做了（`types.py:33-38` 会带上 `target`），`RoutingError` 这一侧没有。

请求侧前缀的那条路径（`_fallback_name(providers, model_name)`）消息是对的，因为 `model_name` 本身就带着那个前缀。

**触发输入**：如上。运维打错 provider 名且未配 `fallback_model_provider`。

**为什么定 minor 而非 major**：启动时 `inspect_mappings` 已经发过一条措辞正确、同时点名键与值的 WARN（`model_resolution.py:192-201`），运行期这条是第二次告知。但 WARN 会淹没在启动日志里，而这条是客户端唯一看得到的东西 —— 如果调用方认为它该升级为 major，我不反对；升级的依据是 “错误消息字面为假且指向错误的配置行”。

**修复方向**：把值（或值的头段）带进消息，例如复用 `inspect_mappings` 已经拼好的那句。

### MPR-05 · `serviceable` 在拼写等价的情况下会把 `disabled` 报成 `absent` `[已实测]`

**主位置**：`src/app/pipeline/routing.py:229-236`

```python
    elif choice.target in provider.disabled_ids:
        serviceable = "disabled"
```

这是**精确字符串匹配**，而它周围每一处模型名比较都走 `canonical()`（大小写不敏感、`.` 与 `-` 等价）：上一行的 `provider.describe(resolution.resolved)`、`resolve_against_catalog` 里的 `available_index`、`_candidate_names` 的去重，全都折叠过。

实测（`probe_routes.py` 第 3 节），A 的目录含 `gpt-5.6-terra` 且它在 `disabled_models` 里：

```
  value='A/gpt-5.6-terra'      -> serviceable='disabled'
  value='A/gpt-5-6-terra'      -> serviceable='absent'
  value='A/GPT-5.6-terra'      -> serviceable='absent'
```

Spec §4.2.2 设立 `disabled` 这个取值的全部理由，就是不让运维被告知 “不在 A 的目录里” 而跑去查目录、发现它明明在。这三种拼写在这套代码的其他每一处都是同一个模型，只有这一处不是。

**触发输入**：`model_mappings: {y: "A/gpt-5-6-terra"}`，A 的目录 id 是 `gpt-5.6-terra` 且被 `disabled_models` 禁用。项目自己的 `canonical` 就是为了容忍这种拼写差异而存在的，`config.example.yaml` 的 `disabled_models` 有 41 条，运维手抄时用 `-` 代 `.` 是完全可能的。

**修复方向**：`canonical(choice.target) in {canonical(i) for i in provider.disabled_ids}`，或让 provider 暴露一个折叠过的集合。

### MPR-06 · 环检测的 WARN 报的是折叠后的键名，可能在配置文件里逐字搜不到 `[已实测]`

**主位置**：`src/app/pipeline/model_resolution.py:256-263`（`marker = canonical(matched_key)`，`path` 收的是 marker）
**相关位置**：`src/app/pipeline/model_resolution.py:214-225`（`detail` 直接把 `cycle` 拼进消息）

`MappingProblem.keys` 的 docstring 说 “`keys` names the mapping keys involved”。对 `unknown-provider` 与 `empty-model` 这两类它确实是原始键（`keys=(key,)`），对 `cycle` 却是 `canonical()` 之后的形式。

实测（`probe_cycles.py` 用例 “case/dot spelling variants”）：`{"claude-opus-4.5": "Claude-Opus-4-5"}` 报出的环是 `('claude-opus-4-5',)`，而配置文件里写的是 `claude-opus-4.5`。运维拿这个字符串去 grep 配置会一无所获。

**触发输入**：任意含 `.` 或大写字母的 mapping 键构成的环，例如 `claude-opus-4.5: claude-sonnet-4.5` 与 `claude-sonnet-4.5: claude-opus-4.5`。

**修复方向**：`path` 收原始 `matched_key`，排序/去重仍按 canonical。

### MPR-07 · `route_table` 的 docstring 有两处事实不成立，而它是每请求重算 O(N²) 的唯一辩护 `[已实测]`

**主位置**：`src/app/pipeline/routing.py:249-258`

> Recomputed per call rather than cached. It is **linear in names times chain length** over a few dozen names, and the inputs it reads — catalogs — **change under a background refresh**, so a cache would be answering about a catalog that has already moved.

两点都不对：

1. **复杂度不是 names × chain length**。主导项是 names × 目录大小：`_report_for` 每一行都会 `resolve_against_catalog` → 重建一次 `available_index`（对整个目录），`choose_provider` → `discover_provider` → `_index(mappings)` 重建一次全表，且 `provider.available_ids` 每行被读 3 次，而 `GithubCopilotProvider.available_ids` 是 `frozenset(self._descriptors) - self._disabled`，每次访问都重建。实测（`probe_cost.py`，模拟真实 provider 的重建行为）：

   | 场景 | 候选名 | 每次 `/api/status` 或 `/v1/models` |
   |---|---|---|
   | 2 × 81 条目目录 + 15 条 mapping | 95 | **2.47 ms** |
   | 2 × 161 条目目录 + 15 条 mapping | 255 | **12.20 ms** |

   候选数 2.7 倍，耗时 4.9 倍，明显超线性。这段是**同步代码跑在 async handler 里**，整段时间事件循环不转。今天可以接受（`/api/status` 在准入闸门内，`/v1/models` 客户端启动时打一次），但 “linear” 这个说法会让下一个人以为目录翻倍没关系。

2. **这条 chain 上没有 background refresh**。`refresh_catalogs` 只在 `_lifespan` 里调一次；`ghc_client/models.py:45` 的 `run_model_refresh_loop` 全仓无调用者；`model_refresh_interval` 无消费者（见 MPR-03）。不缓存这个决定本身没问题（结构简单、正确性无风险），但给出的理由今天不成立。

**触发输入**：读这段注释的下一个开发者。真要触发性能面，把两个 provider 各指向一个 160 条目的目录即可。

**修复方向**：注释改成事实；顺手把 `available_ids` 与 `_index(mappings)` 提到循环外（`_report_for` 改成接收预算好的索引），复杂度即降回 names × chain length，正好让注释成真。

### MPR-08 · `Route.provider_origin` 写了没人读，注释却说 `/api/status` 在读它

**主位置**：`src/app/pipeline/routing.py:67-68`
**相关位置**：`src/app/pipeline/routing.py:312`（唯一写入点）、`src/app/pipeline/routing.py:334-341`（`apply_route` 不取它）

```python
    # How `provider_name` was arrived at, carried for the same reason `descriptor` is: ... `/api/status` reports this per route, ...
    provider_origin: ProviderOrigin = "default"
```

`rg provider_origin src/ tests/` 只有定义与赋值两处，没有任何读取，测试也不断言它。`/api/status` 报的是 `RouteReport.origin`，由 `route_table` 独立算出，与任何 `Route` 实例无关。

同族的还有本次为 `Route.resolution` 新穿进去的 `matched_key=` / `hops=` 两个参数：`Route.resolution` 在 `src/` 里同样没有读者（只有测试读）。

按项目的 `richest-context-flow`，携带比丢弃好，所以我不建议删字段；问题在**注释把一个不存在的消费者写成了事实**，下一个人会据此以为改这个字段会影响 `/api/status`。

**触发输入**：任何人为了改 `/api/status` 的 `origin` 而去改 `Route.provider_origin`。

### MPR-09 · 改名漏了一处 live docstring

**主位置**：`src/app/pipeline/driver.py:259`

```
    The two counters are not interchangeable. `ghc` returns upstream's own number and is worth learning from; `local` returns an estimate ...
```

Spec §1.3 点名的 “`driver.py` 里连带要改的四处字面量” 都改了，但同一文件里这句 docstring 用旧名字描述计数腿。这正是本次改名要消灭的读法歧义（读者会去 `model_providers` 找一个叫 `ghc` 的 provider）。

**触发输入**：读 `handle_count_tokens` 的下一个人。

**改名的其余部分我核过，没有改过头**：`ghc_proxy_translation_losses_total` 等三个指标名（`observability/metrics.py:14,21,31`）未动；`ghc_client` 模块未动；`bundled-config.yaml:53` 的 provider 名 `ghc` 与 `default_model_provider: ghc` 未动；`GHC_API_PROXY_*` 环境变量前缀未动。

### MPR-10 · SOCKS 警告现在每个 provider 各打一遍

**主位置**：`src/app/server/composition.py:471`（循环里调 `build_http_client`）
**相关位置**：`src/app/server/composition.py:173`（`_warn_about_socks`）、`src/app/server/composition.py:234-254`

`build_http_client` 内部无条件调用 `_warn_about_socks`，它对每个解析出的 SOCKS origin 打一条 WARN。改动前每进程调用一次 `build_http_client`，现在是 1（调用方的）+ N（每 provider）。

**触发输入**：`ALL_PROXY=socks5://127.0.0.1:1080` 且 `upstream_transport.tcp_keepalive_interval` 非空（否则 `options.socket_options is None` 直接 return），两个 provider → 启动时 3 条逐字相同的 WARN。

**影响**：纯日志噪音，无行为影响。记下来是因为 `_warn_about_socks` 的 docstring 专门论证过 “一处过报是可接受的”，作者当时算的是一次调用的口径，这个前提被本次改动改掉了。

### MPR-11 · `_report_for` 不剥 `@format` 后缀，路由表与真实请求会给出不同答案 `[已实测]`

**主位置**：`src/app/pipeline/routing.py:206-212`
**相关位置**：`src/app/pipeline/routing.py:296`（`decide_route` 先 `split_format_suffix` 再 `choose_provider`）

`decide_route` 的顺序是 `split_format_suffix` → `choose_provider`；`_report_for` 直接把候选名交给 `choose_provider`。所以一个含 `@` 的 mapping 键在表里与在真实请求里走两条不同的解析。

实测（`probe_routes.py` 第 5 节），mapping 键 `x@anthropic-messages: A/model-a-3`：

```
RouteReport(name='x@anthropic-messages', provider='A', model='model-a-3', origin='qualified', serviceable='yes')
```

`/v1/models` 于是把 `x@anthropic-messages` 作为可服务 id 列出；而真实请求会被拆成模型 `x` + 格式 `anthropic-messages`，`x` 无条目落 default，多半直接 `UnknownModel`。

这与 `RouteReport` 自己的 docstring 冲突：“`/v1/models` and `/api/status` both read this and nothing else, so the two cannot answer the same question differently” —— 它们确实读同一张表，但那张表跟 `decide_route` 之间还差一步。

**触发输入**：运维写 `claude-sonnet-5@anthropic-messages: A/x`，误以为能钉死目标格式（`docs/.human-controlled/request-pipeline.md:11` 用的正是 `model@format` 这种写法描述映射，所以这个误解有来源）。概率不高，但代价是 `/v1/models` 承诺了一个发不出去的 id。

### MPR-12 · Spec §8.3 点名要修的陈旧引用没修

**主位置**：`src/app/pipeline/subscribers/hosted_web_search.py:90`

> `context.provider_name` is set from the route before the attempt begins (`server/handler.py`)

实际写入点是 `apply_route`（`routing.py:334-341`）。Spec §8.3 结尾把这一条列为 “顺带修一处陈旧引用”，本次未做（该文件不在 diff 的 29 个文件里）。同一行下面的 `context.provider_name or default_provider`（`hosted_web_search.py:99`）在本次之后已经是纯冗余分支了 —— `provider_name` 现在必然由 `apply_route` 填好 —— 这一半我不建议动（它是 fail-closed 兜底，删掉没有收益）。

**触发输入**：按注释去 `server/handler.py` 找写入点的人。

---

## nit

- `tests/unit/pipeline/test_error_classify.py:87` 仍构造 `CountTokensUnavailable(("ghc:0:UpstreamRejected",), ...)`。断言不看这个前缀，所以测试是绿的，但它编码了一条改名后不可能再出现的 trail 条目。
- `src/app/pipeline/routing.py:196`（`_candidate_names` 的 `if not key or key in seen`）会静默丢掉 canonical 形式为空的 mapping 键，而 `inspect_mappings` 也不检查空**键**（只检查空值）。`"": "A/x"` 因此在路由表、`/v1/models` 与启动 WARN 里三处皆不可见。YAML 里写空键很罕见，但 schema 是 `dict[str, str]`，它能通过校验。
- `inspect_mappings` 拿的是 `frozenset(config.model_providers)`，而路由拿的是 `providers.names`（registry）。`build_chain(providers=...)` 注入路径下两者可以不一致，于是启动 WARN 描述的 provider 集合与实际路由用的不是同一个。只在测试注入路径可达，所以是 nit。

---

## 主观建议（不占严重度档位）

1. **`fallback_model_provider` 应当与 `default_model_provider` 一起进 `NOT_HOT_RELOADABLE`**（`src/app/config/schema.py:40-55`）。两者都在 `ProviderRegistry.__init__` 被捕获一次、之后永不重读，而 `chain.config.model_mappings` 是每请求实时读的。今天没有实际影响 —— `config/provider.py` 的 `ConfigProvider` / `pin_restart_only` 在 `src/` 里没有任何消费者，热重载没有接进这条 chain。所以这是 “等热重载真的接上时会立刻踩到” 的一条，预期影响是 `/api/config` 与路由行为在一次 reload 之后不一致。注意 `default_model_provider` 今天也不在那张表里，所以这条要么两个一起加，要么都不加。
2. **`_report_for` 的三次 `provider.available_ids` 读取可以合并成一次**（`routing.py:216-231`）。与 MPR-07 的修复是同一处，预期影响是 `/api/status` 的延迟降一个常数因子，且让那段 docstring 的复杂度描述变成真的。
3. **`build_chain` 的 provider 构造循环值得一个 `try/except` 把已建的 client 关掉**（见 MPR-02），这样即使 MPR-01 只在入口处修一半，构造失败路径也不再泄漏。

---

## 我查过但认为没问题的

逐条列，不用 “其余均正确” 概括。

1. **`find_alias_cycles` 的算法正确性 `[已实测，含控制变异]`**。任务点名要独立验证的七种输入我全部构造了，另加五种：自环、二元互指、三元环、多个入口指向同一个环、两个不相交的环、链尾接环、带限定的边（不成环）、限定认不出的边（也不成环）、纯链无环、大小写/点号折叠后才闭合的环、环声明在入口之前、空值、bracket 后缀（`opus[1m]` ↔ `opus`）。15 个用例全部通过，且与一个**独立的暴力参考实现**（每个起点各走 `len(nodes)+2` 步、不做跨走 memo）结果一致，无漏报、无重复报告（`probe_cycles.py`）。
   为确认这个绿有分辨力，我另跑了两个故意打坏的变体（`control_cycles.py`）：去掉 `safe` 跨走 memo → 15 个用例中 8 个变红（全是重复报告）；忽略 `qualified` 终止条件 → 3 个变红。**用例表对这两类缺陷都能打红**，所以上面的 “无缺陷” 是有分辨力的结论，不是同形的绿。
   `safe` 集合的正确性我也单独论证过：这是函数图（每个键至多一个后继），所以一个节点进了 `safe` 就意味着它下游的整条路径在之前某次走完过；归纳下去，先前那次要么走到链尾、要么遇终点、要么已报出它所在的环。因此提前 break 不会漏报。
2. **`disabled_ids` 与 `available_ids` 的口径，以及 `models + disabled == 目录大小` 这条不变量**。`available_ids = frozenset(descriptors) - disabled`，`disabled_ids = frozenset(descriptors) & disabled`（`github_copilot.py:90-97`），两者不相交且并集恰为 `descriptors`，所以 `/api/status` 里 `len(available) + len(disabled)` 恒等于目录条目数。`_disabled` 取自 `config.disabled_models` 的原样字符串，与目录取交集，所以配置里那些 “上游从来没提供过” 的陈旧行不计入 —— 与注释一致。
3. **`ModelProvider` protocol 新增三个成员后各实现的一致性**。生产实现只有 `GithubCopilotProvider` 一个（`rg "def available_ids"` 在 `src/` 只命中它与 protocol 本身），三个成员齐备。测试 fake 共 11 处，diff 里每处都补上了 `disabled_ids` / `base_url` / `catalog_refreshed_at`，pyright 0 错误对结构化 Protocol 是有效证据。
4. **`catalog` 字段与 `serviceable: "unknown"` 用的是同一条谓词**：`ops.py:88` 的 `"ok" if available or disabled else "empty"` 与 `routing.py:225` 的 `if not provider.available_ids and not provider.disabled_ids` 是同一个判断的正反面，不会出现 “catalog 说 ok 而每行都 unknown” 这种自相矛盾。
5. **`ready` 只有一个判据函数**。`_is_ready(chain)` 同时供 `/health/readiness`（`ops.py:44`）与 `/api/status`（`ops.py:101`）使用，没有第二处重算。
6. **`/api/status` 与准入闸门的关系**。`admission.py:22` 的 `UNGATED_PATHS` 是 `{"/health", "/health/liveness", "/health/readiness", "/metrics"}` —— 拆分后 `/api/status` 落在闸门内、三条 health 路径全部在闸门外（包括 `readiness` handler 上那个额外的 `/health`），与 “重量级查询该被闸门管住、健康检查不该” 一致。
7. **`route_table` 的并发/线程安全**。`route_table` 全程同步、无 await，而 `replace_catalog` 只是重绑 `self._descriptors`（原子），且目录刷新跑在同一个事件循环上，所以一行报告内多次读 `available_ids` 不会读到半张目录。进程里确实有第二个线程（`rich.Live` 的刷新线程，见 `active_requests.py:3-5`），但它只碰上锁保护的 `ActiveRequestRegistry`，不碰 provider。
8. **`@` 与 `/` 的解析顺序**。`decide_route` 先 `split_format_suffix`（`rpartition("@")`）再 `choose_provider`（`partition("/")`），与 Spec §3 要求的顺序一致；`A/claude-opus-5@anthropic-messages` 能正确拆成 provider=A、模型=`claude-opus-5`、格式=`anthropic-messages`。（表侧不做这一步，见 MPR-11。）
9. **请求侧前缀不会被链上的限定抢走**。`choose_provider` 在 `request_qualified` 分支里只取 `discovery.target`，完全不看 `discovery.provider`，也不调 `_fallback_name`；`A/opus` 遇上 `opus: B/x` 仍然去 A。
10. **`_candidate_names` 的去重按声明工作 `[已实测]`**。顺序是 “目录名（跨 provider 合并后排序）→ mapping 键（排序）”，按 `canonical` 去重、保留先出现的拼写。`probe_routes.py` 第 6 节的输出证实目录名先出、mapping 键后出，同时是目录 id 与 mapping 键的名字只出现一次且用目录的拼写。
11. **`_report_for` 的 `except RoutingError` 捕获范围不过宽**。`try` 里只有 `choose_provider` 一次调用；`choose_provider` 内部唯一的 `RoutingError` 抛出点是 `_fallback_name`（`split_provider_qualifier` 与 `discover_provider` 都不抛）。`providers.get()` 在 `try` 之外，所以 `ProviderNotConfigured` 不会被误吞。硬编码的 `origin="fallback"` 与唯一抛出路径一致。另外 `choose_provider` 返回的 provider 名恒在 registry 里（explicit 经精确匹配、`discovery.provider` 同理、fallback 与 default 在 `ProviderRegistry.__init__` 已校验），所以后面的 `providers.get()` 不会抛。
12. **`/v1/models` 的 `owned_by` 不会是 `null`**。`RouteReport.provider` 只在 `unroutable` 那一行为 `None`，而 `/v1/models` 只取 `serviceable == "yes"` 的行，两者互斥。
13. **`fallback_model_provider` 的配置可达性**。`config/loading.py:21` 的环境变量映射是通用前缀 + `__` 嵌套，新顶层键自动支持 `GHC_API_PROXY_FALLBACK_MODEL_PROVIDER`，不需要额外登记；`config/settings.py` 是另一套遗留 schema（`UpstreamConfig`/`AuthConfig` 那一族），不参与这条 chain，所以不存在 “两套 schema 只改了一套” 的问题。
14. **`_reject_renamed_counter` 的实现**。`mode="before"` 的 validator 在 pydantic 的枚举校验之前跑，所以 `providers: [ghc, local]` 得到的是那句点名改名的消息而不是原始枚举报错；`isinstance(value, list)` 的窄化被拆进独立函数以免污染 validator 返回类型，注释解释得对。
15. **`debug/models.py` 没有传 `proxy_from_cli` 是对的**，不是漏传：该命令没有自己的 `--proxy`，`composition.py` 默认值 `False` 与 `models.py:229` 那句注释给出的理由一致。（但它同样受 MPR-01 影响。）
16. **`rate_limiters` 与 `CopilotTokenManager` 已经是 per-provider**，本次的路由改动让 `driver.py:187` 的 `chain.rate_limiter_for(provider.name)` 第一次真的按路由结果取限流器；`rate_limiters` 的键集合与 `providers` 同源，不会 KeyError。
17. **测试改动没有被削弱**。`test_direct_driver.py` 的 `provider=FakeProvider()` → `providers=routing_registry()` 是签名变更的机械跟随，断言未动；`test_error_envelope.py`、`test_builtin_subscribers.py` 的改动只是 `ghc` → `upstream` 的字符串跟随；11 个 fake 各加的 13 行都是新 protocol 成员。`tests/unit/pipeline/test_model_resolution.py` 与 `tests/int/test_pipeline_ops_routes.py` 65 个用例我实跑过，全绿（2.50s）。
18. **本项目 “绝不硬折行” 的约定**。新写的注释与 docstring 全部是整段单行（`model_resolution.py:9,96-98,117-119,235-239`、`routing.py:96-99,111-113,190-195` 等），没有按列宽断句。`inspect_mappings` / `_fallback_name` 里跨行的 f-string 是运行期消息的拼接（拼出来仍是单行），不属于文本硬折行，且与仓库既有写法一致。
19. **提交信息**里没有 `Co-authored-by`，格式是 `feat: <description>` 加正文，末尾 `Spec:` trailer 指向 `.dev/docs/multi-provider-routing/spec.md`，符合项目的 conventional-commits 与 “commit message is an index, not a document” 约定。
20. **`replace_catalog` 的时间戳只在成功替换处打**（`github_copilot.py:132-133`），304 与抛异常都不更新，与 `catalog_refreshed_at` 声称的 “最近一次**成功**刷新” 一致；从未成功时为 `""`，`ops.py:92` 再转成 JSON `null`。

---

## 我考虑过但排除的怀疑方向

1. **`route_table` 每请求重算会不会被并发放大成 DoS**。排除：`/api/status` 在准入闸门内（`admission.py:22` 不豁免它），`/v1/models` 同理，两者都受 `max_inflight` 约束；实测单次 2.47 ms（真实规模），并发放大受闸门上限约束。性能观察改为 MPR-07 的一部分（口径是注释失实，不是 DoS）。
2. **两个 provider 共享 `_descriptors` 或 `_disabled`**。排除：`GithubCopilotProvider.__init__` 里每个实例各自持有 `dict`/`frozenset`，`compile_supported_by_provider` 也是 per-provider 的（`composition.py:507`），没有跨 provider 的可变共享状态。
3. **`ProviderRegistry` 的 `_providers = dict(providers)` 是浅拷贝，外部还能改**。排除：唯一构造点是 `build_chain`，传入的 dict 之后不再被写；这不是本次引入的形态，也没有可达的写入者。
4. **热重载会让 `providers.fallback_name` 与 `chain.config.fallback_model_provider` 脱钩**。排除为 “今天不可达”：`config/provider.py` 的 `ConfigProvider` 与 `pin_restart_only` 在 `src/` 里没有任何消费者，这条 chain 没接热重载。降级为主观建议第 1 条。
5. **`transform/model_resolver.py` 里已有一个环检测（`model override cycle detected`），新写的 `find_alias_cycles` 是不是重复造轮子**。排除：前者是单次解析途中撞环即抛、语义含 overrides / family preference / 日期后缀剥离，后者是静态枚举全部环用于 WARN，职责不同；而且 `ModelResolver` 这个类在 `src/` 里没有实例化点（只有 `normalize_for_matching` 被 `tokenization/` 用），是既有孤儿模块，按用户 “不得擅自删除已实现的功能” 的裁决不动它。
6. **`provider_clients` 为空是不是 `build_chain(providers=...)` 注入路径的 bug**。排除：注入路径下 provider 是调用方造的、用调用方的 client，chain 不该替它关；docstring 明写了这一点，行为与文档一致。（真正的问题在非注入路径，见 MPR-01。）
7. **`catalog_refreshed_at` 输出 `+00:00` 而 Spec 示例写 `Z`**。排除出本次范围：这是对外 JSON 契约的取值形态，属于 “实现是否符合 Spec 的行为”，归另一位验收者；代码本身没有正确性问题（`datetime.now(UTC).isoformat(timespec="seconds")` 是合法 ISO 8601）。
8. **`/v1/models` 不再列出次要 provider 未被映射到的模型，是不是少报**。排除出本次范围：Spec §4.1 第 6 条明确规定 “只有该 provider 确实服务解析后的那个模型时才列出”，这是裁决过的行为，不是代码缺陷。
9. **`decide_route` 抛出的 `RoutingError` 会不会没有错误信封映射**。排除：`error_classify.py:43` import 了它，`:235` 有 `isinstance(error, RoutingError)` 分支，映射路径存在。
10. **`shape_request` 不再读 `context.provider_name` 会不会打断某条入站路径**。排除：`server/inbound.py` 不设该字段，Spec §0 也核过 `src/app` 里唯一写入点是 `apply_route`；测试里那五处直接赋值现在会被 `apply_route` 覆盖，而测试全绿说明没有依赖它作为输入。
11. **`hosted_web_search.py:99` 的 `context.provider_name or default_provider` 现在是不是死分支**。排除为 “不建议动”：它在 `provider_name` 恒非空之后确实不会走 else，但删掉一个 fail-closed 兜底属于 `choosing-technical-approaches` 里点名要谨慎的那类，收益为零。只把同一处的陈旧引用记成 MPR-12。
12. **`build_http_client` 每 provider 一次会不会重复安装全局补丁**。排除：`_keep_proxy_connections_alive` 与 `cap_streams_per_connection` 都作用在各自 client 的 transport/pool 实例上，不写模块级或类级状态，N 次调用互不干扰。唯一的跨调用可见效果是日志（MPR-10）。

---

## 搜索面（我看了什么、没看什么）

**读过的源文件（最终状态，非仅 diff）**：`src/app/pipeline/model_resolution.py`（全文）、`src/app/pipeline/routing.py:1-120` 及 diff 全文、`src/app/server/composition.py:140-254,336-406,449-562`、`src/app/server/routes/ops.py`（diff 全文）、`src/app/core/chain.py`、`src/app/cli.py:135-200`、`src/app/debug/models.py:215-262`、`src/app/server/pipeline_app.py:50-87`、`src/app/server/admission.py:22-50`、`src/app/model_provider/github_copilot.py:30-155`、`src/app/model_provider/registry.py`、`src/app/model_provider/types.py`（diff）、`src/app/model_provider/base.py`（diff）、`src/app/config/schema.py:1-130,398-435`、`src/app/config/provider.py`、`src/app/config/settings.py:1-40`、`src/app/config/bundled-config.yaml:40-70`、`src/app/pipeline/driver.py`（diff + 250-268）、`src/app/pipeline/count_tokens.py`（diff）、`src/app/observability/request_log.py`（diff）、`src/app/transform/model_resolver.py:52-105`。

**读过的测试**：`tests/int/test_pipeline_ops_routes.py:1-110` 与相关断言、`tests/unit/pipeline/test_model_resolution.py` 的 fallback/inspect 段、五个小测试文件的完整 diff。

**跑过的命令**：`uv run pytest tests/unit/pipeline/test_model_resolution.py tests/int/test_pipeline_ops_routes.py -q`（65 passed）；四个自建探针 + 一个控制变异脚本（下列）。

**探针脚本**（均在 `/home/xp/.claude/jobs/0e3de57b/tmp/`，未改动工作树任何文件）：

| 脚本 | 用途 | 运行方式 |
|---|---|---|
| `probe_cycles.py` | `find_alias_cycles` 15 个用例 + 独立参考实现对照 | `PYTHONPATH=src uv run python <路径>` |
| `control_cycles.py` | 两个故意打坏的变体，证明上表有分辨力 | `PYTHONPATH=src:<tmp> uv run python <路径>` |
| `probe_routes.py` | 错误消息、`disabled` 精确匹配、`@` 键、`/v1/models` 顺序、粗略计时 | `PYTHONPATH=src uv run python <路径>` |
| `probe_cost.py` | 模拟真实 provider 重建行为的 `route_table` 计时 | `PYTHONPATH=src uv run python <路径>` |
| `probe_lifecycle.py` | provider client 的归属与三条泄漏路径 | `PYTHONPATH=src uv run python -W always <路径>` |
| `probe_refresh.py` | `refresh_catalogs` 的失败传播与迭代顺序 | `PYTHONPATH=src uv run python <路径>` |

**工作树改动**：**我一处也没有做**。所有验证都在 `/home/xp/.claude/jobs/0e3de57b/tmp/` 下的独立脚本里完成，我没有对 `src/` 或 `tests/` 做过任何修改，因此没有需要还原的东西。评审开始时 `git status --short` 输出为空；结束时同伴在同一棵树上留下了四个文件的未提交修改（快照与指纹见文首的并发改动一节），其中没有一处出自我。核对方式：`git -C /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing status --short`，并注意该输出还在变化。

**没有覆盖的面**（明确声明，避免被读成 “查过了没问题”）：

- **Spec 行为符合性**：按分工交给另一位验收者，我只在正确性与内部一致性撞上 Spec 时引用它。
- **`/api/status` 与 `/v1/models` 的 JSON 字段名、取值集合是否逐字符符合 Spec §4.1/§4.2** —— 同上。
- **真实上游验证**：Spec §10.2 已声明凭据隔离与连接池隔离不做真实验证；我也没有跑任何真实账号的调用。MPR-01/MPR-02 说的是 client 对象的生命周期，不是连接池行为的实测。
- **翻译层、streaming、keepalive、TUI**：本次 diff 未触及，未看。
- **`tests/` 的完整回归**：我只跑了两个直接相关的测试文件；任务给出的全量绿（1855 passed / 90.65%）我没有复跑。就本报告而言那个全量绿能证明的是 “本次改动没有打破既有断言”，**不能**证明新资源被正确释放（`provider_clients` 在 `tests/` 里零引用）、也不能证明 `refresh_catalogs` 的多 provider 失败路径（无对应测试）—— MPR-01 与 MPR-03 正是这两个盲区里的东西。

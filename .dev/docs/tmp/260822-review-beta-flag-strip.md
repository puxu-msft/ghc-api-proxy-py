# 评审：`strip_anthropic_beta_flags` 的落地（`hook_strip_anthropic_request_headers`）

**日期**：2026-08-22
**评审对象**：主会话在共享主树上的未提交改动，限于 `src/app/config/schema.py`、`src/app/pipeline/request_headers.py`、`src/app/server/handler.py`、`src/app/observability/metrics.py`，以及 `tests/unit/pipeline/test_client_request_headers.py`（新增 8 条）与 `tests/int/test_pipeline_app.py`（新增 3 条）。
**被评审者自述**：`.dev/docs/hooks-subscription-migration/reports/260822-beta-flag-strip-implementation.md`
**结论**：`needs-fix`。**没有 blocker**——接线是真的活着，端到端剥离在直连腿与翻译腿上都实测生效。但有一条 major 的语义分叉：剥离表按 `resolved_model` 匹配，而用户亲笔 `config.example.yaml` 里那唯一一张表的键 `claude-sonnet-4.6` 在同一份文件里恰好是 `model_mappings` 的**键**（映射到 `claude-sonnet-5`）；两段配置同时生效时整张表空转，且现有测试完全看不见这个差别。

---

## 0. 评审是怎么做的（以及为什么结论可以照单采信）

**主树在评审期间是坏的，所有验证都不在主树上做。** 13:03 观察到 `src/app/config/loading.py` 因同伴的未提交编辑而 `IndentationError`，整个 `app` 包 import 不了（这是**有保质期的阻断性观察**，复述时请重测，不要当成现状）。因此：

- 用 `git archive HEAD | tar -x` 在 `/tmp/beta-probe` 拉出干净 HEAD 树，再 `git apply` **只属于被评审者的那份 diff**（4 个源文件 + 单测文件）。同伴的改动一律不进这棵树。
- 探针加载路径已自证：`app.server.handler.__file__ == /tmp/beta-probe/src/app/server/handler.py`。
- **主树未被写入、未被修改、未被提交任何一个字节**。变异一律在 `/tmp/beta-probe` 上做，做完从 `/tmp/pristine_*.py` 还原并复跑 baseline 确认恢复（`baseline again: GREEN`）。

评审中途 HEAD 从 `f191e4d` 前进到 `1743a0b`，隔离树按新 HEAD 重建了一次。见 §6 的 HANDOFF。

基线（隔离树，新 HEAD + 本切片 diff）：

- `tests/unit/pipeline/test_client_request_headers.py` + 3 条新增 int 测试 → **20 passed**
- `tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses` → **passed**（把 `docs/.human-controlled/` 复制进隔离树之后；见 minor-10）
- `ruff check` 4 个源文件 + 单测文件 → All checks passed
- `pyright` 同一组文件 → 0 errors, 0 warnings

---

## 1. 问题 1：接线是否真的活着 —— **是，且只有一个漏斗**

逐条核对报告 §2.3 的声称，全部属实：

| 声称 | 核对结果 |
|---|---|
| 新链路 `pipeline_app` → `handler.shape_request` 会执行到剥离 | **属实**。`driver.run` 全项目只有一处（`handler.py:181`），`DRIVERS[...]` 也只有一处（`handler.py:172`），二者都在 `shape_request` 之后。没有第二个入口能绕过它。 |
| 直连腿与翻译腿都覆盖 | **属实**，且不是靠读代码断定的：int 测试断言在 `MockTransport` 收到的真实请求头字节上，翻译腿那条还额外验证了剥空后头整个消失。 |
| 必须在 `apply_route` 之后 | 代码位置属实，但**这条设计声称本身没有任何测试鉴别力**，见 major-2。 |

补充核对了报告没写、但你点名要问的三个绕过面：

- **retry 重发**：`direct_driver/base.py:244` 每次 `_send` 都现读 `context.client_headers`。剥离是对该字段的**整体覆写**，所以每一次重试拿到的都是已剥离的那份。没有绕过。
- **delivery 触发的续写 attempt**：`pipeline_app.py:662` 的 `_reopen()` 复用**同一个 context 对象**再走一遍 `handle` → `shape_request`。它显式重置了 `context.payload = deepcopy(inbound_payload)`，但**不重置 `client_headers`**——于是第二遍剥离作用在已剥离的头上，`removed` 为空、提前返回、头不变、计数器也不重复自增。**幂等，且是对的**。
- **hedge**：`HedgeConfig` 只在 `config/schema.py` 出现，`src/` 下没有任何消费者。今天不存在并行 attempt 这条路径。
- **`/v1/messages/count_tokens`**：`shape_request` 确实覆盖它，但见 minor-5——那条腿**根本不转发 `anthropic-beta`**，覆盖是空的。

---

## 2. 问题 2：正确性 —— 语义洞逐个实测

用探针直接调 `strip_denied_beta_flags` / `forwarded_client_headers`（隔离树，输出原样抄录）：

```
raw items:            [('anthropic-beta', 'flag-a'), ('anthropic-beta', 'flag-b'), ('anthropic-version', '2023-06-01')]
forwarded:            {'anthropic-beta': 'flag-b', 'anthropic-version': '2023-06-01'}

mixed-case header name:            ({'Anthropic-Beta': 'ctx'}, ())
mixed-case flag value:             ({'anthropic-beta': 'keep'}, ('CTX-Flag',))
duplicate flag:                    ({'anthropic-beta': 'keep'}, ('ctx', 'ctx'))
two canonical-equal config keys:   ({'anthropic-beta': 'b'}, ('a',))
empty header value:                ({'anthropic-beta': ''}, ())
whitespace kept, nothing denied:   ({'anthropic-beta': ' a , , b '}, ())
```

对应的结论分别落在 minor-1/2/3/4 与 nit-1/2。

**`canonical()` 折叠会不会误命中？——今天不会，且这个问题问错了层。** 拿 `exp/260820-websearch-probe/raw/models-live.json`（42 个真实上游 model id）算过：按 `canonical` 折叠后**零碰撞**。最接近的一对是 `gpt-4.1`（→ `gpt-4-1`）与 `gpt-41-copilot`，折叠后仍不同。更重要的是，`canonical` 正是 `model_mappings` / `resolve_model` 自己用的那把尺子——这里若能误命中，路由早就先误命中了。**这个决定是对的，不要改。**

---

## 3. 问题 3：是否偏离用户亲笔需求

**范围守卫 `inbound_format is WireFormat.ANTHROPIC_MESSAGES` 是对的。** 用户亲笔 `message-format-reshape.md` 在《客户端输入 Anthropic Messages》标题下第一句就是「这部分仅在 `/messages` 或 `/messages/count_tokens` 端点入口生效」，而 `inbound.py:ROUTES` 里只有这两条路由是 `ANTHROPIC_MESSAGES`。守卫与文档的范围逐字对齐。

**没有做多。** 无通配、无 glob、无内置 flag 名表，`strip_anthropic_beta_flags` 之外没有新增任何键。报告 §4 的三条未采纳项逐条核对属实。

**做少的地方在 §4 没记**：requested vs resolved 这条分叉（major-1）。以及一条更早就存在、本切片把它固化进断言的偏离（nit-3）。

---

## 4. 发现清单

### major

#### major-1 剥离表按 `resolved_model` 匹配，而用户亲笔配置里那个键是 `model_mappings` 的键——两段配置同时生效时整表空转

**失败场景**（实测，非推演）。把用户 `config.example.yaml` 的两段配置一起用：

```yaml
model_mappings:
  claude-sonnet-4.6: claude-sonnet-5      # 第 123 行，用户亲笔
hook_strip_anthropic_request_headers:
  strip_anthropic_beta_flags:
    claude-sonnet-4.6: [context-management-2025-06-27, ...]   # 第 442-447 行，用户亲笔
```

客户端请求 `model: claude-sonnet-4.6` + `anthropic-beta: context-management-2025-06-27,effort-2025-11-24` →

```
A) operator key is the alias the client asks for (the example config's shape)
  status=200  upstream anthropic-beta = 'context-management-2025-06-27,effort-2025-11-24'
  stripped? NO
B) operator key is the resolved upstream id
  status=200  upstream anthropic-beta = 'effort-2025-11-24'
  stripped? YES
```

（探针：真 ASGI app + MockTransport，`mappings={'claude-sonnet-4.6': 'claude-model'}`，断言在上游实际收到的请求头上。）

即：请求被路由到 `claude-sonnet-5`，`_denied_for('claude-sonnet-5', {...'claude-sonnet-4-6'...})` 返回空集，**四个 flag 一个都没剥**，上游照旧 `400 invalid beta flag`。这正是报告 §2.3 自己担心的那个失效形态——「剥离从未触发的失效形态是一个 400，没人能把它追溯回这张表」——只是它防住了拼写轴，没防住命名空间轴。`model_mappings` 的**键**是入站名字空间，**值**才是上游 id；剥离表的键取了前者的拼法，代码却拿后者去比。

**这不是一个纯粹的 bug，是一个该问用户而没问的分叉。** 两侧都有依据：

- 支持按 **resolved** 匹配：beta 是回答请求的那个模型的能力，报告 §2.3 的论证在语义上站得住。且 `claude-sonnet-4.6` **确实是一个真实的上游 model id**（在 42 个 live id 里），所以只要运维不把它 remap 掉，resolved 就等于它，实现工作正常。
- 支持按 **requested** 匹配：用户那张表的键与同一份文件里 `model_mappings` 的键逐字相同，而 `model_mappings` 的键从来只是入站别名；用户写下 `# 400 invalid beta flag` 时观察到的那次 400，在他自己的映射下是 `claude-sonnet-5` 报的，他仍然按客户端点名的名字给这张表起了键。

**建议**：交用户裁，不要自己选。可选项与代价——

1. 按 requested 匹配：与用户文件的字面一致，但语义上把「模型能力」挂在了别名上。
2. requested ∪ resolved 都查（命中任一即剥）：两种读法下都不会空转，**但有自己的失效**——运维把 `claude-sonnet-4.6` 重映射到 `claude-opus-5` 时，opus 本来支持的 beta 会被按 4.6 的表剥掉，body 里靠该 beta 启用的字段变成 unrecognised field，换来另一个 400。
3. 维持现状 + 在 schema 注释与 `deferred.md` 里写明「键是**上游 id**，不是 `model_mappings` 的键」，并请用户确认他的实盘配置里 `claude-sonnet-4.6` 没被 remap。

无论选哪条，`no-silently-cut-but-defer` 要求这条分叉进 `deferred.md` 或 `decision-pending.md`，而不是只活在实现者脑子里。

#### major-2 没有任何测试能区分 requested 与 resolved，于是 major-1 在测试面上完全不可见

**变异证据**（隔离树，正样本对照见下）：把 `handler.py` 的 `model=context.resolved_model` 改成 `model=context.requested_model` → **20 条测试全绿**。

原因是三条 int 测试都不配 `model_mappings`，requested 与 resolved 恒等。于是报告 §2.3 花了整段论证的「必须在 `apply_route` 之后」这条设计声称，**鉴别力为零**——把接线整个挪到 `apply_route` 之前也没有任何东西会红。

**修法（一条测试即可）**：`make_client(mappings={'alias-model': 'claude-model'}, overrides=_beta_strip('claude-model', ...))`，请求 `model: alias-model`，断言上游头已剥离。这条测试同时把 major-1 的裁决固化下来——它是用来表达「键属于哪个名字空间」的那条测试。

### minor

#### minor-1 metric 的 `flag` 标签取的是客户端拼写，`metrics.py` 里「两个标签都由配置表封顶」的注释不成立

实测：`strip_denied_beta_flags({'anthropic-beta': 'CTX-Flag,keep'}, model='m', denied_by_model={'m': ['ctx-flag']})` → `removed == ('CTX-Flag',)`。标签值来自 header 的原样拼写，而匹配是 casefold 的，所以同一个 flag 的 N 种大小写写法产生 N 条 series，客户端可控。`model` 标签同理：`Claude-Sonnet-4.6` 与 `claude-sonnet-4-6` 折叠后同键、却是两个标签值。

失败场景：一个把 header 大小写随机化的客户端（或两个 SDK 的两种拼法）在 Prometheus 里长出多条同义 series，运维问「现在还在给哪个模型拿掉哪个 flag」时读到的是分裂的计数。

修法：标签用**配置里的规范拼写**（`_denied_for` 已经 casefold 过），或至少 `flag=spelling.casefold()`、`model=canonical(resolved_model)`。一行的事，注释也就重新成立了。

#### minor-2 同一请求里重复的 flag 会让计数器重复自增

实测：`'ctx,ctx,keep'` → `removed == ('ctx', 'ctx')`，`BETA_FLAGS_STRIPPED` 对同一请求同一 flag 自增两次。失败场景：客户端（或中间层拼接）产生了重复 flag，指标读数变成「剥了 2 次」而实际只是一个请求。修法：`removed` 去重，或在 handler 里 `for flag in set(stripped_flags)`（顺序无所谓，标签是集合语义）。

#### minor-3 配置里两个 canonical 等价的键，只有第一个生效，第二个被静默丢弃

实测：`denied_by_model={'m.1': ['a'], 'm-1': ['b']}`，model `m.1` → 只剥了 `a`，`b` 原样发出。`_denied_for` 用 `next`-like 的首次匹配返回，第二个等价键连警告都没有。

失败场景：运维为两种拼法各写一段（很自然，因为 `model_mappings` 里日期后缀那组就是这么写的），以为是并集，实际只有 YAML 里靠前的那个生效 → 剩下的 flag 继续 400，而表看上去写得好好的。**这是 major-1 同一族的静默失效。** 修法：把所有 canonical 等价的键**合并**成一个集合，而不是取第一个。

#### minor-4 客户端发两个 `anthropic-beta` 头时，第一个在剥离之前就已经被丢掉

实测：Starlette `Headers(raw=[('anthropic-beta','flag-a'), ('anthropic-beta','flag-b'), ...])` → `forwarded_client_headers` 返回 `{'anthropic-beta': 'flag-b', ...}`。字典推导取最后一个，`flag-a` 静默消失。

**先于本切片存在**（`forwarded_client_headers` 的老行为），但值得记在这里：这个模块现在是 `anthropic-beta` 语义的归属地，把重复头按逗号合并是它的自然归宿。失败场景：一个把 header 拆成两行发的客户端/中间代理，其协商掉的 beta 有一半到不了上游，body 里靠它启用的字段变成 unrecognised field → 400，且这个 400 的成因在代码里没有任何一处提到过。

#### minor-5 `count_tokens` 腿根本不转发 `anthropic-beta`，报告 §2.3 的「正好覆盖」是空覆盖

实测（真 app，`POST /v1/messages/count_tokens` 带 `anthropic-beta: ctx-flag,keep-flag`）：

```
upstream url:              https://copilot.example/v1/messages/count_tokens
upstream anthropic-beta:   <absent>
upstream anthropic-version: 2023-06-01
```

`anthropic-version` 是 Anthropic SDK 自己加的；`ghc_client.send_anthropic_count_tokens` 压根没有 `extra_headers` 形参，`provider.count_tokens` 也不接 context。所以剥离在这条腿上跑了、但对线上字节没有任何影响。

这不是本切片引入的缺陷，剥离已就位、将来一旦开始转发就自动生效。但报告里「`shape_request` 同时服务这两个入口，正好覆盖」这句会让读者以为 count_tokens 端点被验证过——**它被执行过，没有被覆盖过**。顺带：用户文档把这一节的范围写成两个端点，隐含前提是两个端点都会转发这个头；今天不是。这条值得进 `deferred.md`。

#### minor-6 metric 发射完全没有测试

变异：删掉 `handler.py` 里那两行 `BETA_FLAGS_STRIPPED.labels(...).inc()` → **20 条全绿**。标签名写错、标签顺序写反、整段被误删，都没有东西会红。int 测试里已经 import 了 `prometheus_client.REGISTRY`，加一条 `REGISTRY.get_sample_value('ghc_proxy_beta_flags_stripped_total', {'model': ..., 'flag': ...})` 断言是最便宜的补法——而且它顺带把 minor-1 的标签拼写固定下来。

#### minor-7 flag 名大小写不敏感这条行为没有测试

变异：把 `spelling.casefold() in denied` 改成 `spelling in denied`（即大小写敏感）→ **20 条全绿**。8 条单测全用小写拼写。失败场景：将来有人为了「省一次 casefold」把它删掉，或改成 `lower()` 处理土耳其语 I 之类的边角，没有任何东西拦得住。一条 `'Context-Management-2025-06-27'` 的单测即可。

#### minor-8 `if not removed: return dict(headers), ()` 这条早退没有测试

变异：删掉它 → **20 条全绿**。它承担的语义是「一个 flag 都没剥时，头值保持客户端原样的字节」；删掉之后 `' a , , b '` 会被重排成 `'a,b'`（实测早退生效时原样返回 `' a , , b '`）。失败场景：客户端对自己发出的头做签名或做等值比较时，一次「什么都没剥」的请求却改变了头的字节。补一条「配了模型但无交集 → 头值逐字节不变」的单测。

#### minor-9 docstring 给出的不修改调用方 mapping 的理由，在当前代码里没有依据；而字段本身被整体覆写了

`strip_denied_beta_flags` 的 docstring 说「Returns a new mapping; the caller's is not touched, because it is also what the request record reports the client sent」。核对：`context.client_headers` 在 `src/` 下的**唯一消费者**是 `direct_driver/base.py:244`，没有任何 record / history / 日志读它。所以这个理由指向的消费者不存在。更要紧的是 `handler.py:118` 把 `context.client_headers` 整个覆写了——即便那个 record 存在，它读到的也是剥离后的版本。

不是今天的缺陷（没有消费者），但方向和用户亲笔的相邻小节相冲：《总是剥离 attribution header》一节写着「额外提醒，历史记录中的原始客户端请求不应受此处理影响」。等 history 开始记录入站头时，当前的覆写会直接违反它。**修法**：把剥离后的头放进一个新字段（如 `context.upstream_headers`）而不是覆写 `client_headers`；或者至少把 docstring 里那句没有依据的理由删掉，别让下一个人以为有人在守护它。

#### minor-10 触发本切片的那道 gate，在文件缺席时静默 skip

`test_authoritative_example_config_parses` 用 `@pytest.mark.skipif(not SPEC_PATH.is_file())`。而 `docs/.human-controlled/` 目前只是 **staged 未提交**（`git status` 是 `A`），所以从 HEAD 拉出来的任何一棵树里这条 gate 都直接 skip——我的隔离树第一次跑就是 `13 passed, 1 skipped`，把文件复制进去之后才 `1 passed`。

先于本切片存在，但它正是本切片的触发者：这道 gate 是「schema 漏建模用户新键」的唯一探测器，而它在最需要它的场合（干净 checkout、CI、隔离 worktree）会安静地不存在。至少该让 skip 的理由出现在默认输出里，或者把权威文件提交进去。

### nit

- **nit-1** `strip_denied_beta_flags` 隐含要求 header 键已小写：实测传 `{'Anthropic-Beta': 'ctx'}` 静默返回 `((原样), ())`。当前唯一调用方喂的是 `forwarded_client_headers` 的输出（已小写），所以安全；但这是个没有写下来的前置条件。docstring 里加一句，或者查找时兜一层小写。
- **nit-2** 客户端自己发 `anthropic-beta:`（空值）时原样透传：实测 `{'anthropic-beta': ''}` 返回不变。docstring 论证「空值是双方都没有约定含义的第三态」，但这个论证只在「剥空了」的分支上执行；客户端自带的空值头照样发给上游。两种处理都说得通，只是当前实现与它自己的说理不一致。
- **nit-3** 翻译腿本不该转发 `anthropic-beta`。用户亲笔《剥离请求头》一节写明：直连路径用黑名单，**翻译路径用白名单，且「（暂无）」**。`forwarded_client_headers` 是全局白名单，两条腿都放行 `anthropic-beta` / `anthropic-version`。**先于本切片存在**，但 `test_the_strip_applies_on_the_translated_path_too` 现在把「翻译腿会带这个头」固化成了断言——将来若按用户文档收紧翻译腿，这条测试会以「实现回归」的姿态挡路。值得在测试 docstring 里点一句，或者进 `deferred.md`。

---

## 5. 问题 5：三个「不动」的决定

| 决定 | 评价 |
|---|---|
| 保留 `strip_attribution_header` 字段 | **可接受，但方向可辩，建议交用户。** 报告的理由是「删掉会让写了 `false` 的运维在 `extra="forbid"` 下启动失败，比开关空转更响」。核对属实。但代价是一个**静默说谎的开关**：运维写 `false`，attribution 照剥（`pipeline_app.py:426` 常驻执行），而且用户亲笔文档已裁定「现在我认为这是应该常驻的」，`config.example.yaml` 里也已经没有这个键——会写 `false` 的只可能是拿着旧配置的人，而那正是最该被一次点名报错叫住的人。项目其他地方的偏好（`extra="forbid"` 本身、`never-swallow-errors`）是**响而不是静默**。字段旁的注释已经把事实写清楚了，所以不至于误导下一个开发者；只是运维读不到注释。 |
| 不动 legacy `config/settings.py:81 beta_strip_headers` | **核实属实且合理。** 逐条查过：`AppSettings`（`extra="forbid"`）由 `config/loader.py` 从 `config_file_path()` = `XDG_CONFIG/.../config.yaml` 加载，而 spec 的 `ProxyConfig` 走 `spec_config_file_path()` = `XDG_DATA/.../config.yaml`——**是两个不同的文件**，用户的新键打不到 legacy 面上。而且 legacy 的字段挂在 `anthropic.beta_strip_headers` 下，结构也不同。本切片不碰它是对的。 |
| 不动 `build_anthropic_beta_headers` 的 `strip` 形参 | **合理。** 零调用方、legacy 链路（`app.routes` / `app_factory` / `AnthropicClient`），不是主产品路径。扩到那里会把本切片变成两条链路的改动，收益为零。 |

---

## 6. 对报告本身的核对

| 报告章节 | 核对结果 |
|---|---|
| §2.1 改名而非新增，`beta_strip_headers` 从未出现在用户亲笔配置里 | **属实**。全仓 grep `beta_strip_headers` 只剩 `src/app/config/settings.py:81` 一处（legacy）。 |
| §2.3 接线点、两条腿、两个入口 | **属实**，除「count_tokens 正好覆盖」是空覆盖（minor-5），以及「必须在 `apply_route` 之后」零鉴别力（major-2）。 |
| §3.3 变异结果 | **逐条复现属实**：把 `denied_by_model=` 改成 `{}` → `test_a_beta_flag_...` 红、`test_the_strip_applies_on_the_translated_path_too` 红、`test_an_unconfigured_model_still_gets_the_whole_header` 绿，8 条单测不受影响（它们直接调函数，本就不该受影响）。第三条保持绿的解释也是对的，是构造性的、且分工正确。 |
| §3.3「变异已恢复，`rg MUTATION-PROBE src tests` 空」 | 未复核（主树在评审期间坏过，且我不在主树上跑任何东西）。当前主树 diff 里没有任何变异残留痕迹。 |
| §4 未采纳项 | **属实**，但**漏了本次最重要的未决分叉**（major-1 的 requested vs resolved）。按 `no-silently-cut-but-defer`，它该进 `deferred.md` / `decision-pending.md`。 |
| §5 需要实测才能关闭的问题 | 同意，且当前实现对此确实中立（代码不内置任何 flag 名）。 |

**正样本对照**（证明我的变异 harness 有分辨力，不是「怎么改都绿」）：

| 变异 | 结果 |
|---|---|
| M1 删掉 metric 发射 | 绿（存活 → minor-6） |
| M2 删掉 `if not removed` 早退 | 绿（存活 → minor-8） |
| M3 flag 匹配改成大小写敏感 | 绿（存活 → minor-7） |
| M4 `resolved_model` → `requested_model` | 绿（存活 → **major-2**） |
| M5 剥空后发空值头而非删头（对照） | **红** |
| M6 模型键改成精确字符串相等（对照） | **红** |

---

## 7. HANDOFF（给主会话）

1. **同伴的提交 `1743a0b`（“fix: answer whether upstream finished…”）已经把你的 3 条 int 测试卷进去了。** `git show 1743a0b -- tests/int/test_pipeline_app.py` 里能看到 `+def test_a_beta_flag_the_resolved_model_refuses_does_not_reach_upstream` 等三条。这是 pathspec 提交扫走他人工作树改动的那个已知形态（项目记忆 `git-commit-takes-the-whole-index` 的反向面）。你的 4 个源文件 + 单测文件仍是未提交状态，于是**测试已经进 HEAD、实现还没有**——现在 HEAD 是半截的。这不影响本评审的结论（我在隔离树上把两半拼齐了跑的），但你提交时要知道自己在提交什么。
2. **主树在 13:03 因同伴编辑 `src/app/config/loading.py` 而整体 import 失败**（`IndentationError`）。这是有保质期的观察，现在可能已经好了；我没有为此做任何事，也没碰主树。
3. major-1 需要用户裁决，建议在提交前把它写进 `deferred.md` 或 `decision-pending.md`；major-2 的那条测试无论用户怎么裁都要补，因为它是把裁决固化下来的载体。
4. `.dev/docs/tmp/260822-verify-beta-flag-strip-docs.md`（13:07，同伴）与本报告是不同视角，未交叉核对。

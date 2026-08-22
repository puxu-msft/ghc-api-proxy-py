# `strip_anthropic_beta_flags` 落地：从「配置已冻结、实现缺席」到新链路上真的执行

**日期**：2026-08-22
**性质**：实现切片 + 文档对账。改动了 `src/`、`tests/`，未改动 `docs/.human-controlled/`。
**基线**：动手时 `ec8b2a5`，写定时 `1743a0b`（同伴在此期间推进了 `f191e4d`、`1743a0b`，与本切片无交集）。工作树上同时有同伴的未提交改动（`tests/int/test_pipeline_app.py`、`src/app/cli.py`、`lifecycle/*`、`pipeline/retry.py`、`translation_driver/responses.py`、`server/pipeline_app.py` 等），本切片的提交按 pathspec 精确到自己动的文件。
**触发**：用户在 `docs/.human-controlled/config.example.yaml` 里把配置键改名为 `hook_strip_anthropic_request_headers.strip_anthropic_beta_flags`，schema 没跟上，`tests/unit/config/test_config_schema.py::test_authoritative_example_config_parses` 因 `extra="forbid"` 变红。

**核查回执**：本文初稿有四条事实错误，由独立核查者查出并已改正，逐条依据见 `../../tmp/260822-verify-beta-flag-strip-docs.md`。错的是 §2.1 的改名叙述、§2.1 对 `settings.py` 归属的判断、§4 对 `strip` 形参调用方的绝对陈述、§1 表格里一处引文出处的行号。**下文是改正后的版本。**

## 0. 用户 2026-08-22 的七条裁决

本报告初版把若干问题挂着待裁。用户已逐条裁决，代码与本文都已按裁决改写。**下文正文以裁决后的形态为准**；被推翻的中间形态保留在各节的说明里，因为推翻的理由本身有信息量。

| # | 提问 | 裁决 | 落地 |
|---|---|---|---|
| 1 | 剥离表按 requested 还是 resolved 匹配 | **按实际上游尝试**（resolved） | §2.2 |
| 2 | `strip_attribution_header` 留还是删 | **删掉** | §2.1 |
| 3 | 6 处指向已改名文档的断链 | **修** | §2.5 |
| 4 | `test_authoritative_example_config_parses` 在做什么 | 提问，**尚未裁决** | §7 |
| 5 | 翻译腿仍在转发 `anthropic-beta` | **不转发，建立文档所说的黑白名单机制** | §2.4 |
| 6 | `config/loader.py` docstring 过时 | **更新** | §2.5 |
| 7 | 模型键通配是否 deferred | **不 deferred，用正则，从上到下先匹配者赢** | §2.2 |

---

## 1. 这条红到底是什么

不是配置笔误，也不是 schema 打字打错。用户亲笔的需求文档 `docs/.human-controlled/message-format-reshape.md` 有一整节《按需剥离 `anthropic-beta` 请求头的部分 flag》，正文给出了机制与实测依据：

> `anthropic-beta` 请求头表示希望访问的功能特性，是与模型能力相关的，不满足则报错 `400 invalid beta flag`。

所以它是一条待实现的需求，红测试只是它露头的方式。

**之前的状态是「配置已冻结、实现缺席」**，而且这件事早被记录过至少三次，都停在「发现」而没有进到「实现」：

| 记录 | 说了什么 |
|---|---|
| `260820-external-rewrite-surface.md:36`（§1.1） | `ProxyConfig.hook_strip_anthropic_request_headers`（含 `strip_attribution_header`、`beta_strip_headers`）**零消费者**；`rg` 对这两个字段名在 `src/` 下只命中 schema 定义本身与 legacy `config/settings.py`。同一份报告 `:404` 把它列进「需要用户裁决的点」 |
| `../../sync-refs/sxwxs-ghc-api/260821-round-disposition.md:97` | 记的是「键名不一致」（文件里 `strip_anthropic_beta_flags`，schema 里 `beta_strip_headers`），当作既存红绕开了 |
| `../../hosted-web-search/status.md` §4.5（改写前） | 判为「先于本切片存在」，标注「需要用户确认要不要实现」 |

用户 2026-08-22 的指令就是那个确认。

## 2. 实现

### 2.1 schema：跟上用户的改名

`src/app/config/schema.py` 的 `StripRequestHeadersHook.beta_strip_headers` 改名为 `strip_anthropic_beta_flags`，类型 `dict[str, list[str]]` 不变。

**这是跟上用户的改名，不是发明一个新名字。** 初稿在这里写反了，值得留下过程：`beta_strip_headers` 这个拼法**曾经**就是用户亲笔 `config.example.yaml` 里的拼法——`git log --all -S 'beta_strip_headers' -- docs/.human-controlled/config.example.yaml` 命中 `53fec22`，其 blob 第 486 行正是 `beta_strip_headers:`，下面挂着同样那四个 flag 和 `# 400 invalid beta flag` 注释。用户在 08-20 之后、08-21 之前把它改名成了 `strip_anthropic_beta_flags`，schema 没跟上，于是变成键名不一致。

之所以容易看反：`config.example.yaml` **不在 HEAD 里**（索引状态 `AM`），唯一收录过它的提交只存在于非祖先分支 `a/2026-08-20-split-53fec22`。`git log` 不加 `--all` 在这个文件上什么都看不到，而「查不到」看起来和「从未有过」一模一样。

结论不变但理由要换：改名不会让任何在用的配置失效，因为**用户亲笔文件当前已是新拼法，且旧拼法零消费者**——而不是因为旧拼法从未存在过。

同一个 class 里的 `strip_attribution_header` **已删除（裁决 2）**。用户在同一轮编辑里把这一条整个从 example config 删掉了（`message-format-reshape.md` 写明该行为应常驻而非配置），它同样零消费者。中间版本曾保留字段，理由是删掉会让运维手上写了 `strip_attribution_header: false` 的配置在 `extra="forbid"` 下变成启动错误；用户裁定删除——一个静默说谎的开关比一次响亮的启动失败更糟。

`src/app/config/settings.py:81` 的 legacy `AppSettings.beta_strip_headers` **未动**。它是 **legacy 链路**（`app.routes` / `AnthropicClient` / `deps.py`）的旧配置面，与 `ProxyConfig` 是两套，同样零消费者。

> ⚠️ 初稿在这里写的是「那是 `--fd`(systemd) 路径的旧配置面」，**不成立**。那句话抄自 `config/loader.py:1` 的 docstring，而该 docstring 已过时。该 docstring 已按裁决 6 更新，见 §2.5。

### 2.2 剥离函数：`strip_denied_beta_flags`

放在 `src/app/pipeline/request_headers.py`，与 §2.4 的两级转发策略同一模块——它们处理同一个头的两个问题：这条路径能不能转发这个头，以及转发的那个头里哪些 flag 该拿掉。

签名：

```python
def strip_denied_beta_flags(
    headers: Mapping[str, str],
    *,
    model: str,
    denials: Sequence[tuple[re.Pattern[str], tuple[str, ...]]],
) -> tuple[dict[str, str], tuple[str, ...]]
```

#### 键匹配：正则，按配置顺序先匹配者赢（裁决 1 + 7）

**裁决 1：按实际上游尝试匹配**，即 `context.resolved_model`。中间版本取过 requested ∪ resolved 的并集，理由是用户配置里 `:443` 的表键 `claude-sonnet-4.6` 同时是 `:123` 的 `model_mappings` 键（`claude-sonnet-4.6: claude-sonnet-5`），按 resolved 匹配则整表空转。用户裁定语义优先：能力属于回答请求的那个模型，别名要被看穿。

**这条裁决的直接后果**：用户当前 `config.example.yaml` 里那条表项**是惰性的**——没有请求会 resolve 到 `claude-sonnet-4.6`。这不是代码要绕开的事，但也不该是个惊喜，所以固化成了测试 `test_a_table_keyed_on_an_alias_does_not_fire`。要让它生效，把表键改成 `claude-sonnet-5`，或者去掉那条 model_mappings。

**裁决 7：键是正则，不 deferred 通配。** 照本项目对 `models_support_web_search` 的既有约定实现：

- **启动时编译**（`compile_beta_flag_denials`，从 `build_chain` 调用，编好的表放在 `Chain.beta_flag_denials`）。坏正则是启动失败并点名那个键；留到运行时编译，一个笔误会变成「这个模型的 flag 从来没被剥过」——正是这张表要防的失效。
- **`fullmatch` 而非 `search`**，否则 `claude-sonnet-4.6` 会连 `claude-sonnet-4.6-experimental` 一起认领。
- **按配置书写顺序，第一个命中者赢**，且不与后面的合并。合并会让「窄条目放在宽条目上面」失去意义——那种写法的用处正是**少剥一些**，union 只能多剥。
- `.` 是通配符，所以 `claude-sonnet-4.6` 顺带认领 `claude-sonnet-4-6`。这在本项目里恰好是想要的（两种拼法是同一个模型），但**它是正则语法的副作用，不是折叠规则**；要精确钉住写 `claude-sonnet-4\.6`。大小写敏感，要不敏感写 `(?i)`。

#### 其余四个已决定的行为点

1. **剥 flag，不剥头。** 运维没为这些模型点名的 flag，按客户端原样的拼写继续走。
2. **剩空了就把头删掉**，不发空值。跟 `build_anthropic_beta_headers` 在没选中任何 beta 时返回 `{}` 是同一个选择。客户端自己发的空值原样保留——本函数只删 flag，而那里没有 flag 可删。
3. **返回新 mapping，不改调用方的**，这样任何还持有客户端原始 headers 的调用方拿到的仍是到达时的样子。

flag 名比对两侧都 `strip()` + `casefold()`；保留下来的 flag 用客户端原来的拼写重新 join，而**返回的名字是配置里的拼写**——它要去打标签，客户端控制的字符串进 Prometheus label 是无界基数（评审实测 `CTX-Flag` 会自成一条 series）。同一请求里重复出现的 flag 两份都被剥掉，但只上报一次。

### 2.3 接线点：`shape_request`，路由之后

`src/app/server/handler.py::shape_request`，在 `apply_route` 之后、`fix_anthropic_request` 之前，与后者共用 `inbound_format is WireFormat.ANTHROPIC_MESSAGES` 的守卫。

- **必须在 `apply_route` 之后**：要 `context.resolved_model`。
- **必须在 driver 之前**：`direct_driver/base.py::_send` 把 `context.client_headers` 整个交给 provider，它没有任何依据判断这个模型拒收哪些 flag。
- **守卫按用户亲笔文档的范围**：`message-format-reshape.md` 把这一节放在《客户端输入 Anthropic Messages》标题下，并写明「这部分仅在 `/messages` 或 `/messages/count_tokens` 端点入口生效」。`shape_request` 同时服务这两个入口（`handler.py:153` 与 `:235`）。
  ⚠️ **但 count_tokens 那一半是空覆盖**：评审实测该腿根本不转发 `anthropic-beta`（上游收到的是 `<absent>`）。初稿写的「正好覆盖」不准确——正确说法是「这道剥离在 count_tokens 腿上也会执行，但那条腿本来就没有 `anthropic-beta` 可剥」。这是既有行为，不是本切片造成的，也没有改。
- **两条腿都覆盖**：直连腿（`/v1/messages` → 上游 `/v1/messages`）与翻译腿（`/v1/messages` → 上游 `/responses`）都从 `shape_request` 过，都从 `_send` 发出 `client_headers`。
  ⚠️ **但翻译腿现在不转发 `anthropic-beta` 了**（裁决 5，见 §2.4），所以那条腿上这道剥离同样无事可做。剥离仍然为它执行，是因为它不该依赖上游那一级的策略碰巧是什么。
- **retry / 续写 / hedge**：评审核实这些都复用同一个 `context.client_headers`，`shape_request` 是唯一漏斗；重复执行幂等（已剥掉的 flag 第二次扫不到）。

### 2.4 请求头黑白名单机制（裁决 5）

用户裁定「翻译腿不转发 `anthropic-beta`，建立如文档所说的黑白名单机制」。`message-format-reshape.md`《剥离请求头》一节说：直连路径黑名单（`Forwarded` chain / `Cookie` / `X-Api-Key` / `Host` / `Content-Length` / `Content-Encoding` / `Accept-Encoding`），翻译路径白名单（暂无）。

改动前 `forwarded_client_headers` 对所有路径都用同一个**白名单** `{anthropic-beta, anthropic-version}`，与文档两头都不符。

#### 照字面实现会造成一个凭据缺陷

派了专门调查（`../../tmp/260822-header-forwarding-surface.md`），实测结论：

- `GhcApiClient.request_headers` 做的是 `{**client, **proxy}`，而代理头把 `Authorization`、`X-Interaction-Id`、`X-Interaction-Type`、`X-Agent-Task-Id` 拼成**大写**，转发来的客户端头是**小写**——dict 里是两个不同的键，两个都活下来。
- Anthropic SDK 经 `httpx2.Headers.__setitem__` 会折叠大小写，代理值胜出；**OpenAI SDK 的 `_build_request` 读 `multi_items()`，两条 `authorization` 一起发到线上**。
- 也就是说：直连路径改成黑名单、`authorization` 进入 `extra_headers` 之后，Responses 腿会把客户端凭据一并发给上游。

所以**文档那份黑名单是参考实现 `SENSITIVE_DENYLIST` 的分类摘要**，漏掉了 `authorization` 本身、`proxy-authorization`、`api-key`、跳段组、`x-github-*` / `openai-*`，以及「动态排除代理自己的 core key」那一整层。copilot-api-js 从不把 `Authorization` 交给上游，双重挡。

#### 用的是仓库里已经写好、从未接线的那个模块

`src/app/anthropic/header_policy/__init__.py::forward_request_headers` 已经完整实现了这套规则，`REQUEST_FLOOR` 28 项与参考实现的 `SENSITIVE_DENYLIST` 逐项一致——**生产调用者为零，只有测试在用**。这是「守卫被留在 legacy 链路上」的第四次击发。本切片把它接起来，没有另写一份。

#### 两级，因为两个问题的答案在不同时刻才有

| 级 | 位置 | 管什么 |
|---|---|---|
| **floor** | `build_context`（解析后、路由前） | 无条件剥掉凭据、代理身份、跳段头、forwarded chain。`build_context` 原有注释承诺「下游任何地方都不会持有客户端凭据」，这一级是它的实现 |
| **路径策略** | `shape_request`（`apply_route` 之后） | 直连走黑名单、翻译走白名单。此时 `translation_required` 才有值 |

拆成两级正是为了让 floor 守住那个承诺：解析时还没路由，一个路径相关的过滤器在那里只能靠猜；而只放在路由之后，客户端凭据会在中间那段时间躺在 context 上。

`DIRECT_PATH_BLACKLIST` 目前是**空的**，而这是结论不是遗漏：文档为直连路径列的七项**全部已在 `REQUEST_FLOOR` 里**，floor 一级就实现了文档要的清单。留作具名接缝，因为文档自己的 TODO 说那些条目抄自 copilot-api-js、原因尚未搞清——哪天某一项被判定属于这里而非 floor，位置已经在了。

`TRANSLATED_PATH_WHITELIST` 是空的，字面照文档。于是翻译腿不再转发任何客户端头，`anthropic-beta` 在内。

#### 顺带修掉的既有缺陷

`request_headers` 的合并改成**大小写不敏感**：任何与代理自有头同名（不论拼法）的转发头直接丢弃，不进 dict。此前 Anthropic 腿的安全依赖 SDK 内部的 `Headers.__setitem__` 折叠，不是任何代码声明的不变式——参考实现的注释专门写了「The guard is NOT the spread order」。新测试 `test_a_forwarded_header_never_travels_beside_the_one_it_collides_with` 断言在 `get_list()` 上而非 `headers[...]`，因为按名查找会折叠大小写、根本看不见第二条。

#### 用户随后更新了权威文档，两条新增当时已经满足

2026-08-22，本节实现落地之后，用户在 `message-format-reshape.md` 的直连黑名单上加了两处：

```diff
-直连路径的黑名单有：
+直连路径的黑名单有：（大小写不敏感）
 - `Forwarded` chain
-- `Cookie` `X-Api-Key`
+- `Authrization` `Cookie` `X-Api-Key`
```

也就是**追认了本节 §「照字面实现会造成一个凭据缺陷」提出的两点**：`Authorization` 必须进黑名单，且匹配大小写不敏感。两条在写下时就已成立，无需改代码：

- `authorization` 本来就在 `REQUEST_FLOOR` 里（那张表照抄参考实现的 `SENSITIVE_DENYLIST`，本来就比文档那份摘要长）。
- `forward_request_headers` 的三道判据——`REQUEST_FLOOR`、core key、`x-github-` / `openai-` 前缀——以及 `_matches` 的 fnmatch，**全部**两侧 `lower()`；`request_headers` 的合并也已在本切片改成大小写不敏感。
- 实测（`PYTHONPATH=src uv run python` 探针）：`Authorization` / `AUTHORIZATION` / `AuThOrIzAtIoN` 三种拼法连同文档列的其余每一项都被剥掉，翻译腿零转发。

新增回归测试 `test_the_blacklist_is_case_insensitive_for_every_entry_the_document_names` 把这条钉住——文档此前没明说大小写，所以也没有测试覆盖过混合拼法。变异验证：把 floor 的比对改成大小写敏感，该测试变红。

> 该条目最初拼作 `Authrization`（少一个 `o`）。当作真实头名它匹配不到任何东西——实测 `forwarded_client_headers({"Authrization": "x"})` 原样保留它。实现没有从文档逐字读这份清单（读的是 `REQUEST_FLOOR`），所以行为从未受影响；但照文档字面实现的人会正好在凭据那一项上留一个洞。提请后**用户已于同日改正为 `Authorization`**。`docs/.human-controlled/` 归用户亲笔，全程未代改。

### 2.5 断链与过时 docstring（裁决 3 + 6）

- `docs/.human-controlled/message-format-sanitize.md` 已被用户改名为 `message-format-reshape.md`。指向旧名的 8 处引用全部改指新名：`anthropic_request_hook.py` 4、`pipeline_app.py` 1、`test_pipeline_app.py` 1、`test_attribution_stripping.py` 2。改完 `rg` 全仓无残留，并跑了正样本对照确认那条 grep 命令本身能命中新名字。
- `config/loader.py` 的模块 docstring 说 `AppSettings`「now serves only the `--fd` (systemd) path」，**不成立**：`cli.py:258` 的 `--fd` 走 `_load_spec_config` → `ProxyConfig` → `serve_inherited`，`load_settings` 在 `src/` 下除 `config/__init__.py` 再导出外已无调用方。改写为如实描述：它是 legacy 链路（`app.routes` / `AnthropicClient` / `app.deps`）的旧配置面，新链路一处不读。

### 2.6 指标

`src/app/observability/metrics.py` 新增 `BETA_FLAGS_STRIPPED`，标签 `("model", "flag")`。

带标签而非像邻居 `ATTRIBUTION_LINES_STRIPPED` 那样裸计数：后者只有一个触发原因、只拿掉一样东西；这里运维回头要问的是「现在还在给哪个模型拿掉哪个 flag」。`flag` 取**配置里的拼写**而非客户端的——客户端控制的字符串进 Prometheus label 是无界基数；`model` 是 resolved id，由 catalog 封顶。

不打日志：它对配了这张表的模型**每个请求都会触发**，per-request INFO 是噪音。理由与 `ATTRIBUTION_LINES_STRIPPED` 旁边那条注释同源。

## 3. 测试与鉴别力

### 3.1 单元：`tests/unit/pipeline/test_client_request_headers.py`

14 条，覆盖：只剥点名的 flag、未配置的模型原样通过、模型键的三种拼法都命中、剩空了删头、`a, b` 带空格不漏、空表是恒等、不改调用方的 mapping、没有该头时不动，以及评审后补的六条——按 requested 别名命中、按 resolved id 命中、两个 canonical 等价键都参与、flag 名大小写不敏感且按配置拼写上报、重复 flag 只报一次、配置了但一个都没命中时头值逐字节不变。

### 3.2 接线：`tests/int/test_pipeline_app.py`

6 条，走真 ASGI app + MockTransport，**断言在上游请求实际携带的字节上**，不是断言函数被调用了：

- `test_a_beta_flag_the_resolved_model_refuses_does_not_reach_upstream` —— 直连腿
- `test_the_strip_applies_on_the_translated_path_too` —— 翻译腿（主产品路径），且验证剩空后头整个消失
- `test_an_unconfigured_model_still_gets_the_whole_header` —— 默认必须惰性
- `test_the_table_fires_on_the_alias_the_client_asked_for` —— 用户配置实际所处的形态（表键是 `model_mappings` 的键）
- `test_the_table_fires_on_the_resolved_id_when_the_client_used_an_alias` —— 并集的另一半
- `test_a_stripped_flag_is_counted_under_the_configured_spelling` —— 指标真的发射，且标签是运维的拼写

之所以坚持端到端断言：这个字段此前的状态正是「schema 有、配置有、没人调用」，和项目记忆 `guards-stranded-on-the-legacy-chain` 记录的那三次生产 400 同形。只测 `strip_denied_beta_flags` 本身，会在守卫再次被留在链路外时全绿。

### 3.3 变异验证

三轮，每轮都先确认探针真的落进文件（有一次 `python3` 替换断言没打中，测试仍然 2 passed——那是**未变异代码的假绿**，差点被读成「测试没鉴别力」）：

| 变异 | 变红的 |
|---|---|
| `denied_by_model=` → `{}`（接线断开） | `..._does_not_reach_upstream`、`..._translated_path_too` |
| `models=` → 只传 `resolved_model` | `test_the_table_fires_on_the_alias_the_client_asked_for` |
| 上报客户端拼写而非配置拼写 | `..._counted_under_the_configured_spelling`、`..._reported_as_configured` |

`test_an_unconfigured_model_still_gets_the_whole_header` 在第一轮里保持绿是**构造性的、且是对的**：它断言「不该剥的没被剥」，接线断开时这个命题当然仍成立。它防的是过度剥离，不防接线缺失。

变异全部恢复：`rg MUTATION-PROBE src tests` 空，`handler.py` 与变异前备份 `diff` 无差异。

**这几轮变异证明的范围**：证明了「配置 → `shape_request` → `client_headers` → 上游请求头」这条接线是活的、键匹配两侧都生效、指标标签取的是配置拼写。**没有**证明剥掉这四个 flag 之后上游真的不再 400——那是上游行为，只有实测能答，见 §5。

## 3.4 裁决后重跑的变异与门

裁决把并集改回单键、把折叠改成正则之后，测试整体重写过一轮：单元 26 条、端到端 6 条、`test_client.py` 新增 1 条。变异仍然打红——把 `models=` 换回单 `resolved_model` 时 `test_the_table_fires_on_the_alias_the_client_asked_for` 变红（该测试已按裁决改写为反向断言），把指标标签换成客户端拼写时两条变红。

**门的结果（干净 checkout of `80068eb`）**：`ruff check src tests` 全过；`pytest tests` **1771 passed / 2 skipped / 1 failed**。

那一条失败是 `test_authoritative_example_config_parses`，**不是本切片造成的，父提交 `1c91870` 上同样红**：同伴的 `fa0b281` 把 `docs/.human-controlled/config.example.yaml` 的**旧快照**提交进了仓库，那份里还带着 `upstream_request_retry.strategies.streamReplay`，而用户工作树里的当前版本早已删掉它。等当前版本被提交，这条红自行消失。属于 retry 主题、且 `pipeline/retry.py` 正被同伴改动，本切片不碰。

顺带：这也回答了本报告 §7 里「那道门在干净 checkout 里静默 skip」的观察——**它现在不 skip 了**，因为权威配置文件进了版本控制。skip 的静默性仍然是个待裁决的问题（文件缺席时应当报「未执行」而非跳过），但触发条件已经变了。

## 4. 未采纳与已知边界

- **不支持 `*` 通配键，也不支持 glob。** 用户亲笔配置里只出现按具体模型名的键，需求正文也只说「按需剥离」。`stream_idle_overrides` 用的是子串匹配，那是它自己的历史，没有依据推广到这里。加通配是廉价的，但没人要求，且一旦加了，「哪条键赢」就成了要定的规则。**记为 deferred，不静默实现。**
- **不改 legacy 链路。** `app/anthropic/features.py::build_anthropic_beta_headers` 早就有 `strip: Iterable[str]` 形参，而**唯一的生产调用方 `request_preparation.py:58` 从不传它**（`tests/unit/anthropic/test_feature_negotiation.py:55` 传了，那是单测直接调的）。那条链路（`app.routes` / `app_factory` / `AnthropicClient`）不是主产品路径，本切片不扩到那里。该形参保持原样。
- **`strip_attribution_header` 仍是空转开关。** 见 §2.1，是刻意保留的，且已提请用户裁决要不要删。
- **`config/loader.py:1` 的 docstring 已过时**（见 §2.1 的警告块）。发现于本切片但不属于本切片，未改，记在这里。
- **`docs/.human-controlled/message-format-sanitize.md` 已被用户改名为 `message-format-reshape.md`**，而 `src/app/pipeline/anthropic_request_hook.py`（5 处）与 `src/app/server/pipeline_app.py:422`（1 处）的注释仍指向旧名，现在是断链。本切片只改正了自己新写的那一处（`config/schema.py`），其余 6 处未动——`pipeline_app.py` 当时有同伴的未提交改动，按 pathspec 提交它会连同伴的工作树改动一起带走。记在这里，另行提请。

## 5. 需要实测才能关闭的问题

用户配置里为 `claude-sonnet-4.6` 列了四个 flag，注释写着 `400 invalid beta flag`。这四个是不是**当前**仍会 400、以及是否还有第五个，本切片没有测。这属于「上游行为要录，不要想」的范畴，要么实测探针、要么 cassette。当前实现对此是中立的：表是运维填的，代码不内置任何 flag 名。

## 6. 本次同时对账的文档

- `../../hosted-web-search/status.md` §4.5 —— 该节说这条红「需要用户确认要不要实现」，用户已确认并已实现，改写为指向本报告。
- 以下是时点记录（report / tmp），**按项目规约不改**：`260820-external-rewrite-surface.md`、`../../sync-refs/sxwxs-ghc-api/260821-round-disposition.md`、`../../upstream/retry-and-continuation/reports/260822-review-*.md`、`../../tmp/260822-h2-streamreset-cancel-diagnosis.md`。它们对当时的描述都是准确的。

## 7. 评审处置

两轮独立评审，报告原件：

- `../../tmp/260822-verify-beta-flag-strip-docs.md` —— 文档事实核查，查出本文初稿四条错误，全部已改（见文首回执）。
- `../../tmp/260822-review-beta-flag-strip.md` —— 代码评审，0 blocker / 2 major / 10 minor / 3 nit。

| 发现 | 处置 |
|---|---|
| major-1 按 `resolved_model` 匹配使用户配置整表空转 | **已改**：改为 requested ∪ resolved，并标注待用户裁决（§2.2） |
| major-2 无测试能区分 requested 与 resolved | **已补**：单元 2 条 + 端到端 2 条，变异可红 |
| minor-1 metric 标签取客户端拼写、基数无界 | **已改**：改为上报配置拼写，`metrics.py` 注释同步改正 |
| minor-2 重复 flag 让计数器重复自增 | **已改**：同请求内同一 flag 只上报一次 |
| minor-3 canonical 等价的第二个键被静默丢弃 | **已改**：所有等价键合并 |
| minor-6/7/8 指标发射、大小写、早退三处无测试 | **已补** |
| minor-9 docstring 理由指向不存在的消费者 | **已改**：改成「任何还持有客户端原始 headers 的调用方」 |
| nit-1 隐含要求 header 键已小写 | **已改**：写进 docstring 的前置条件 |
| minor-5 count_tokens 腿是空覆盖 | **未改行为，改了说法**（§2.3 的警告块）。既有行为，本切片不扩 |
| nit-3 翻译腿本不该转发 `anthropic-beta` | **未改行为，改了测试 docstring**，标明是固化现状而非契约。分歧先于本切片，已提请用户 |
| minor-4 客户端发两个 `anthropic-beta` 头时第一个被丢 | **未改**。缺陷在 `forwarded_client_headers` 的 dict 推导，先于本切片，不属于本切片 |
| minor-10 权威配置文件缺席时那道 gate 静默 skip | **未改**。先于本切片，是另一个话题（`making-a-gate-actually-fire` 的形态），记在此 |
| 保留 `strip_attribution_header`（评审判「可接受但方向可辩」） | **保留**，理由与代价都写进字段注释，并提请用户裁决 |

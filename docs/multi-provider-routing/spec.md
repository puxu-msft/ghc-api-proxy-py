# 多 model provider 与按模型路由

**这份是 Spec**，答「应该是什么样」，规范性。**这是活文档，不冻结。** 新的用户裁决、实测或发现一旦与本文任何一处冲突或限定它，**当场修订本文**——不把已知错误的条款留在原地，也不把修正寄存到延后台账或评审报告里。权威永远是本文的当前版本；某条何时因何而变，读下面的条款修订记录。

**条款修订记录**：

| 日期 | 条款 | 变化 | 依据 |
|---|---|---|---|
| 2026-08-27 | **§2.4、§2.3、§5.2** | **首版的核心推导是错的，撤销。** 原文断言「passthrough 的名字从来不会真的发给上游」，据此论证「保持 `resolved = requested` 没有可观察后果」。实测推翻：`describe()` 查的是 `resolved`，而 passthrough 把 `resolved` 设回原始请求名，所以原始名本身在目录里时，`passthrough=True` 与 `describe() is not None` 同时成立，请求照常发出。结论（维持既有行为）不变，但换了一条不依赖该错误事实的理由；§2.3 的「必被拦成 `UnknownModel`」与 §5.2 的前提一并收窄 | 事实评审 facts-01，附可复现探针：provider 提供 `real-model`，表里写 `real-model: missing-target` |
| 2026-08-27 | §0 | 「全仓唯一写入点」过宽。`src/app` 里确实只有 `apply_route`，但测试有五处直接赋值，且 `shape_request` 在 `decide_route` 之前读它——所以该字段技术上**是**可写的路由输入，缺的是入站路径去填它 | 事实评审 facts-02 |
| 2026-08-27 | §1.3 | 误读注释。`driver.py` 那句「neither test has to guess」指的是紧随其后的两个**运行时判定**，不是测试套件。另补上 `count_tokens.py` 里的三处字面量，首版只数了 `driver.py` 的四处 | 事实评审 facts-03 |
| 2026-08-27 | §8.2 | 引文归错文件。「模型 id 唯一不代表两个 provider 跑它的方式相同」在 `hosted_web_search.py:60`，不在 `composition.py:488`（后者说的是另一件事） | 事实评审 facts-04 |
| 2026-08-27 | §4.2 | `/api/config` 不是「完整 dump」：字段是全集，但 `proxy` 的 userinfo 被改写 | 事实评审 facts-05 |
| 2026-08-27 | §8.3 | 「本项目没有 history 实现」过宽。完整实现归档在 `src/.archived/app/history/`，只是 live chain 不可达。首版漏看的原因是 `fd` 默认跳过点号开头的目录 | 事实评审 facts-06 |
| 2026-08-27 | §7.1 | 扫描结果的计数与分类不准：是 3 个不同取值、6 处出现，第三项是测试素材目录 `e2e/claude/cassettes/` 而非插件路径；`disabled_models` 是 41 条而非「30 余个」 | 事实评审 facts-07，独立正则复扫 |
| 2026-08-27 | **§7.2、§8.1** | 两处过宽，一并收窄。`cap_streams_per_connection` 是给每个 distinct pool 各加一次，不是「那一个池」；两个 provider 也**不必然**同 host——`resolve_provider_base_urls` 按各自 token 的订阅类型解析，individual/business/enterprise 是不同 host。成立的陈述改为「解析到同一 origin 且走同一 mount 时共享连接」，§8.1 的结论不变 | 事实评审 facts-08 |
| 2026-08-27 | **新增 §3.1、§3.2、§3.3** | **首版 §3 规定了一个必然失败的做法。** 「模型名部分仍需经过现有的 `model_mappings` 别名解析」——而现有解析对值一无所知，会把 `A/claude-opus-5` 整串当模型名去查目录，于是在 §6.2 推荐的配置下 `A/opus` 必然 `UnknownModel`，恰好否掉这条语法存在的理由；且 `B/opus` 遇上 `opus: A/…` 时与 §2.3 给出两个答案而无优先级。新写三条规则（链照跳、链上 provider 一律丢弃、fallback 不参与），并补 §3.2 的 passthrough 名字与 §3.3 的作用面 | 规则评审 F-01（blocker）、F-13、F-18 |
| 2026-08-27 | **新增 §2.5** | **首版隐瞒了一处行为变更。** discovery pass 取代了 `resolve_model` 的逐跳目录检查，于是「链中间节点可用、链末不可用」的请求由「就地返回中间节点」变成 passthrough——这是单 provider 部署也会跟着变的行为，而首版只声明了 passthrough 名字那一项「维持不变」。变更是必需的（不走到链末就读不到链末的限定），但必须声明 | 规则评审 F-02 |
| 2026-08-27 | §2.2 | 规则表加「带出的模型名」一列，规则 4 拆成 4a（无条目命中）与 4b（撞跳数上限）。首版只规定了 provider，而 §2.4 入参、§4.2 的 `model` 字段、§5.2 的错误消息三处都要用这个值 | 规则评审 F-03 问题一、S-3 |
| 2026-08-27 | **新增 §2.2.1** | `origin: "default"` 混装三件事（没有条目／链走完无限定／撞环或超长），而 §1.2 为「没写」和「写错了」分槽的理由在这里没被应用。§9.2 关于「自环被消解」的论证只覆盖自映射，不覆盖互指环，而首版读起来像是全覆盖 | 规则评审 F-03 问题二 |
| 2026-08-27 | §2.2 | 「provider 来源恰好三种」加上「配置侧」限定——系统里有第四种，即 §3 的请求侧指定，它不进入 `origin` 字段 | 规则评审 F-12 |
| 2026-08-27 | **§4.1** | 候选集从「`available_ids` 并集」改为「并集 ∪ 所有 mapping 键」，与 §4.2 同口径；补上「列候选名而非解析结果」「按 canonical 去重、目录拼写优先」「`serviceable` 的权威定义在 §4.2」三条。首版的候选集不含别名，导致 A 承接的模型在目录里完全不可见——声称报可达集合却漏掉一整类可达名字 | 规则评审 F-05、S-2 |
| 2026-08-27 | **§4.2** | `serviceable` 由布尔改为五值枚举（`yes`/`absent`/`disabled`/`unknown`/`unroutable`），`detail` 取消；`provider` 在无处可去时填 `null`；补 `providers` 各字段口径；示例改为自洽（首版 B 的 `catalog: empty` 与三行 serviceable 冲突）；「别名优先」撤销改为明确的去重规则；`ready` 必须与 `/health/readiness` 共用判据函数；撤销「扫一眼 origin 就能发现」这句过强的推导 | 规则评审 F-06、F-07、F-11、F-16、F-17 |
| 2026-08-27 | §4.3 | 补上对称的已知代价二：判据会**谎报不可用**——流量全走限定的部署，default 挂掉时实例退出轮转而它其实能服务 | 规则评审 F-19 |
| 2026-08-27 | §5.1 | 新增 §5.1.1（WARN 要区分「会走 fallback」与「必然报错」）与 §5.1.2（增加两类纯静态 WARN：限定的模型名为空、别名链成环）。后者扩大了用户裁决时的清单，列入 §12 待确认 | 规则评审 F-15、S-1 |
| 2026-08-27 | §2.1 | 明说 mapping 的值**不支持** `@format`，免得沉默被 §3 的「必须钉死顺序」反推成支持 | 规则评审 F-14 |
| 2026-08-27 | §10.1 | 验收清单补上五项：§3 全部、§2.4 的 passthrough、§2.5 的行为变更、§5.2 的错误消息、§4.1 的候选集 | 规则评审 F-09 |
| 2026-08-27 | §11 | 候选材料清单从一处扩到五处。最要紧的是 `config.example.yaml:100-102`——用户亲笔的解析算法描述正在描述代码已经不做的事 | 规则评审 F-08 |
| 2026-08-27 | **新增 §12** | 把四处「越出用户原裁决边界」的推导集中列出，便于用户单独推翻其中任何一条 | 本次自查 |
| 2026-08-27 | **§1.3 整节推翻重写** | **首版把这个字段读反了。** 它断言 `inbound.anthropic_count_tokens.providers` 里的 `ghc` 命名的是「上游那条腿」、与 `model_providers` 无关，据此改名为 `upstream` 并加静态校验拒绝 `ghc`。用户裁定：`ghc` 有效正是因为配置里有个叫 `ghc` 的 provider，`Literal["ghc","local"]` 这个类型本身就错——它等于宣布只有 provider 恰好叫 `ghc` 的部署能问上游要计数。改名与那条静态校验一并撤销；类型改 `list[str]`，校验改为相对 `model_providers` 的跨字段检查 | 用户 2026-08-27 直接纠正 |
| 2026-08-27 | §2.1 | 补上「provider 名不得含 `/`、不得为空」**由配置边界强制**。首版写了规则却没有任何地方执行它：`A/B` 与 `""` 都能通过校验并启动，前者对每条指名它的限定都悄悄指向别处，后者反转了 §5.1.2 对空 head 的定义 | 实现评审 CFG-08（major） |
| 2026-08-27 | **新增 §8.4** | 目录加载必须逐 provider 隔离。`refresh_catalogs` 原本一个 provider 抛出就终止整趟，而迭代顺序来自 `frozenset` 哈希，于是次要 provider 的过期 token 能让 **default** 的目录永不加载、readiness 终身 503——§4.3 那条「降级不是不可用」的理由正好被这条路推翻 | 实现评审 MPR-03（major） |
| 2026-08-27 | §4.2.2 | `serviceable` 的 `disabled` 判定改用 `canonical` 折叠比较。周围每一处模型名比较都折叠，只有这一处是精确匹配，于是 `A/gpt-5-6-terra` 对着目录里的 `gpt-5.6-terra` 报 `absent`——正是这个取值存在的理由所要消灭的那句话 | 实现评审 MPR-05 |
| 2026-08-27 | §4.1、§4.2.1 | 候选名在解析前先剥 `@format`，与 `decide_route` 同序。否则一个带格式后缀的 mapping 键在表里与在真实请求里走两条不同的解析，`/v1/models` 会列出一个发不出去的 id | 实现评审 MPR-11 |
| 2026-08-27 | §5.3 | 配置侧限定认不出时，错误消息报 mapping 的**值**而非键。首版报键，那句话字面为假，且把运维引向条目的另一半——正是 §5.2 花一整节要消灭的失效形态，`UnknownModel` 那侧做到了、`RoutingError` 这侧没有 | 实现评审 MPR-04 |

## 修订记录

| 版本 | 变化 | 触发 |
|---|---|---|
| v1 | 首稿 | 用户 2026-08-27 逐条裁决，18 个决策点 |

## 0. 这份 Spec 的来源与效力

2026-08-26 用户问「现在是否允许配置两个 GHC API model provider，将不同的模型请求路由到不同的 model provider」。当时的答案是：配置层允许配两个，路由层不支持按模型分流——`context.provider_name` 在实践中是路由的**输出**而非输入。`src/app/pipeline/driver.py:92` 取 `context.provider_name or chain.providers.default_name`，看着像个可以喂的口子，但 `src/app` 里唯一给它赋值的是 `apply_route`（`routing.py:151`），在 `decide_route` **之后**；入站构造器 `src/app/server/inbound.py` 不设置它。所以每个到达的请求读到的都是空串，`or` 每次都落到 default。

措辞上要精确一点，因为首版把它说得太绝对：这个字段是**可写的**，`shape_request` 在 `decide_route` 之前读它，所以一个预先填好的值在技术上确实是路由输入——测试就这么用（`tests/unit/pipeline/subscribers/test_builtin_subscribers.py` 有五处直接赋值）。缺的从来不是能力，是**没有任何入站路径去填它**。本次改动把这个 `or` 整个删掉，provider 改由 `decide_route` 决定，于是它才真正成为纯输出。

用户随后要求「全面实现」，并在一场逐条拷问中裁决了 18 个决策点。本文是那些裁决的规范化表述。

**本文中「用户裁决」与「本次推导」是两种不同强度的条款**，逐条标注。推导项可由评审共识修订；裁决项的改动需要用户同意。这个区分不是形式主义——项目规则要求区分「纠正自己推导出的表」和「改变用户裁决过的事」，前者按评审共识走，后者必须先问。

## 1. 配置面

### 1.1 `model_mappings` 的值可携带 provider 限定

**用户裁决。** 路由判据的载体是 `model_mappings` 的**值**，不是新增的顶层路由表，也不是 per-provider 的 `serves` 表。

```yaml
model_mappings:
  claude-opus-4.8: A/claude-opus-5      # 带限定：去 provider A，模型名 claude-opus-5
  opus: claude-opus-5                    # 不带限定：别名，继续解析
```

被否决的三个替代方案，以及否决理由，记在 §9.1。

### 1.2 新增 `fallback_model_provider`

**用户裁决。** 顶层新键，与 `default_model_provider` 并列，语义**不同**：

| 键 | 何时生效 |
|---|---|
| `default_model_provider` | 解析全程**没有出现过**任何 provider 限定 |
| `fallback_model_provider` | 出现了限定，但斜杠前那段**不是**已配置的 provider 名 |

「没写」和「写错了」是两件事，各占一个槽。合成一个槽会让「运维没配」和「运维配错了」在行为上不可区分，而后者需要被发现。

`fallback_model_provider` **可以不配**。不配时，走到 §2 规则 2 的请求直接报错，见 §5.3。

`fallback_model_provider` 若配置了一个 `model_providers` 里不存在的名字，**启动失败**——与 `default_model_provider` 今天的行为一致（`ProviderRegistry.__init__` 对 `default not in providers` 抛 `ProviderNotConfigured`）。**本次推导**，理由是两个键的失效后果同构，没有理由一个拦在启动、一个拖到运行时。

### 1.3 计数腿的取值是 provider 名，校验相对配置而非静态枚举

**用户裁决**（2026-08-27，纠正本 Spec 作者的一处根本误读）。

`inbound.anthropic_count_tokens.providers` 里的每一项，要么是 `local`（本代理的校准估算），**要么是一个已配置的 `model_providers` 键**。`ghc` 之所以合法，是因为随包配置里有一个叫 `ghc` 的 provider——不是因为这个字符串特殊。

#### 首版在这里错得很彻底，记下来是因为错的方式有普遍性

首版断言：这个值命名的是「上游那条腿」，与 `model_providers` 的键无关，单 provider 时两者恰好同名。据此把它改名为 `upstream`，并加了一个**静态校验**去拒绝 `ghc`。

用户的原话：「这不是静态的，是因为有个 model_provider 是 ghc，所以才有效，为什么要静态验证？」

三层错：

1. **读反了因果。** 不是「碰巧同名所以两种读法都对」，是它本来就在引用那个 provider。用户亲笔的 `config.example.yaml` 只给 `local` 写了注释、`ghc` 没写——因为在那份文件里 `ghc` 不需要注释，上面 `model_providers:` 就是它。
2. **`Literal["ghc", "local"]` 这个类型本身就是错的**，而首版只想着改里面的字符串。把它钉成静态枚举，等于宣布「只有 provider 恰好叫 `ghc` 的部署才能问上游要计数」——这条规则没有任何人定过，它是类型选择的副产品。多 provider 让它现形：运维把 provider 叫 `A`、`B` 时，这个字段**写不出 `[A, local]`**。
3. **然后我在错误的类型上加了静态校验**，去拒绝一个在有 `ghc` provider 的部署里完全合法的值。那是把缺陷固化成了纪律。

#### 规范

- 类型是 `list[str]`，不是 `Literal`。
- 校验在 `ProxyConfig` 层（跨字段），判据是「`local`，或本配置 `model_providers` 里存在的键」。
- **不校验默认值。** `["ghc", "local"]` 是随包配置的 provider 名；运维改了 provider 名却没动这个键，什么错也没犯——上游那条腿问的是**路由选中的** provider，所以默认值里那个字符串只需要「不是 local」就能正确工作。运维**写下**的才是声明，才检查；继承来的不是。
- **不校验没有任何 provider 的配置。** 那种 `ProxyConfig` 在 `resolve_default_name` 就会失败，且失败信息指向真正缺的东西；在这里报错只会用后果盖住原因。
- 运行时判据从「等于某个字面量」改成「不是 `local`」。trail 条目与日志标签用**实际的 provider 名**，于是两个 provider 的部署里 `provider(ghc-failed,local)` 说的是哪个上游没答上，而不只是「有一个没答上」。

#### 一处已知的名实不符，本次不动

配置里的名字**不选择** provider，路由选择：`driver.py` 的 `ask_upstream` 闭包捕获的是 `shape_request` 定下的那个 provider。所以 `providers: [A, local]` 而某请求路由到了 B 时，问的是 B。

单 provider 下两种读法行为完全一致，这个偏差一直不可见；多 provider 让它可见了，但它是**既有行为**，不是本次引入的。要不要让配置真正选择计数用的 provider（并处理「用 A 数 B 的模型」是否有意义），是一个独立问题。**记入 `deferred.md` D-4。**

## 2. 解析规则

**这是本 Spec 的核心条款。**

### 2.1 discovery pass

在现有 `resolve_model` 之前增加一趟 discovery pass，职责是**只回答「provider 是谁」**。它**全程不查 `available`**，沿用 `_MAX_ALIAS_HOPS = 8` 的跳数上限（**本次推导**：沿用而非另设，因为它约束的是同一件事——一条别名链能有多长）。

先定义值的限定判读：

```
qualify(value):
    若 value 不含 "/"                                  -> 未限定
    否则 head, _, tail = value.partition("/")          -> 取第一个斜杠
        若 head 精确命中 model_providers 的键          -> 限定，认得，(head, tail)
        否则                                            -> 限定，认不出，(None, tail)
```

`partition` 而非 `rpartition`：provider 名不得含 `/`，模型名部分含斜杠则原样保留在 `tail` 里。**用户裁决**，§1.1 的语法细则。

**「provider 名不得含 `/`」在配置边界强制，不是一句约定**（**本次推导**，2026-08-27 实现评审 CFG-08 发现首版只写了规则、没有人执行它）。`model_providers` 的键若含 `/` 或为空/纯空白，`ProxyConfig` 校验期即失败：

- 含 `/` 的名字**无法被本特性引用**。`A/B` 写进限定就是 `A/B/model`，按第一个斜杠拆开读成未知 provider `A`，于是走 fallback——配置能启动、provider 能作为 default 服务无前缀请求，却对每一条指名它的限定都悄悄指向了别处。
- 空名字会**反转 §5.1.2**。`/model` 的空 head 被定义为「认不出的 provider」，正是为了让漏写 provider 名的条目走补救道；真配一个名为 `""` 的 provider，这条安全网就变成了命中。

两者都是名字的静态性质，放在配置边界拒绝而不是在请求期补救。

限定的剥离必须发生在 `canonical()` **之前**。`canonical()` 会转小写并把 `.` 换成 `-`，跑在前面会破坏 provider 名。**用户裁决。**

provider 名是**精确匹配**，不套用模型名那套「大小写不敏感、`.` 与 `-` 等价」的等价拼写规则——`model_providers` 的键是 YAML 键，不是模型名。**用户裁决。**

**mapping 的值里不支持 `@format` 后缀。** **本次推导**，规则评审 F-14 指出首版对此只字未提，而读者会从 §3「必须钉死 `@` 与 `/` 的顺序」反推出值侧也支持。事实是 `split_format_suffix` 只作用于入站的 `requested_model`（`routing.py`），`src/` 与 `tests/` 里没有任何 mapping 值带 `@`。所以 `x: A/gpt-5.6-terra@openai-responses` 会得到模型名 `gpt-5.6-terra@openai-responses`，查不到目录，走 passthrough 报错。

这个写法**有人会写**：用户亲笔的 `docs/.human-controlled/request-pipeline.md:11` 就用 `claude-sonnet-5 -> gpt-5.6-terra@openai-responses` 描述映射关系。本次不实现值侧的 `@`（那是另一件事——让配置能钉死某条映射的目标格式），但把「不支持」写在这里，免得沉默被读成支持。要不要支持，列入 §11 的候选材料一并请用户裁。

### 2.2 四条规则

沿 mapping 链跳，每跳读一次值：

| # | 条件 | 是不是终点 | provider | **带出的模型名** | origin |
|---|---|---|---|---|---|
| 1 | 值带限定，斜杠前**认得** | 是 | 斜杠前那一段 | 斜杠后那一段 | `qualified` |
| 2 | 值带限定，斜杠前**认不出** | 是 | `fallback_model_provider`（未配置则 §5.3 报错） | 斜杠后那一段 | `fallback` |
| 3 | 值**不带**斜杠 | 否，继续跳 | — | 当前名换成该值，继续 | — |
| 4a | 跳到无条目命中 | 是 | `default_model_provider` | 链末那个名字 | `default` |
| 4b | 撞跳数上限（8 跳） | 是 | `default_model_provider` | 第 8 跳读到的那个值 | `default` |

「带出的模型名」这一列是 2026-08-27 规则评审 S-3 补的。首版只规定了 provider，而 §2.4 的入参、§4.2 的 `model` 字段、§5.2 的错误消息三处都要用这个值——尤其 4b，链中间的一个名字成了答案，这件事必须写出来而不是让读者从 §2.4 的入参倒推。

**规则 1、3、4a 是用户裁决**：「形如 `claude-opus-4.8: A/claude-opus-5` 这种带 provider 的，视为终点；形如 `opus: claude-opus-5` 这种视为别名，非终点；非终点可以多次解析，最终仍无显式指定的，走 default provider」。**规则 4b 是本次推导**——用户只说了「跳到底」，没说跳不完怎么办；沿用既有的 8 跳上限并把链中间那个名字带出去，是不引入新失败模式的做法。

**规则 2 是用户裁决**：「如果 provider 认不出来就剔除，只保留后续的模型名，提供 `fallback_model_provider` 用于该情况」。其中「**仍是终点**」这一句是单独裁决过的：字面套规则 3，剔除后的值不带斜杠、本应降级为别名继续跳，用户裁定它保持终点身份。

理由值得记下来，因为它是这套规则里最不直观的一条。设 `x: a/claude-opus-5`，`a` 是打错的 provider 名，而表里另有 `claude-opus-5: B/claude-opus-5`。若降级为别名继续跳，会跳到后者、读到限定 `B`——**运维打错一个字母，请求去了 B，不报错、不走 fallback**。保持终点身份堵死这条路。

附带的好处是**配置侧**的 provider 来源被收敛成恰好三种（`qualified`、`fallback`、`default`），没有第四种，`/api/status` 的 `origin` 字段（§4.2）因此是一个闭集。

「配置侧」这个限定是 2026-08-27 规则评审 F-12 补的，首版把它写成了系统级的绝对表述。系统里其实有第四种来源——§3 的请求侧显式指定。它不进入 `routes`（那张表渲染的是配置解析的结果，不是某一次真实请求），所以就该字段而言闭集仍然成立；但任何将来想用 `origin` 解释「这一次请求为什么去了那里」的读者，都必须知道请求侧那一类无处安放。

### 2.2.1 规则 4 里混着三件事，其中一件是运维最该发现的

**本次推导**，来自规则评审 F-03 的第二问题。

`origin: "default"` 同时表达三种情形：

- **(a)** 这个名字压根没有条目——§6.1 认领的已知缺口，运维**需要**发现；
- **(b)** 链走完了，全程没有限定——配置正常，运维不必关心；
- **(c)** 链有环或过长，撞了 8 跳上限（规则 4b）——配置有 bug，运维**最需要**发现。

这与 §1.2 为「没写」和「写错了」各开一个槽的理由是同一条，而首版没有把它应用到这里。

(c) 值得单独说，因为 §9.2 关于「自环被消解」的论证只覆盖了**自映射**（`X: A/X`，值带限定所以一读就停）。它不覆盖**互指环**：`opus: claude-opus-5` 是随包默认就有的，运维为了让两个拼法互通再写一行 `claude-opus-5: opus`，两个名字之间就会来回跳满 8 跳。§9.2 自己描述过这个症状——「表现为解析成了链中间那个名字，不报错」——那个症状在采纳的设计里**依然存在**，而 §9.2 读起来像是它已被消除。

**处置**：本次不为 (c) 新增 `origin` 值（那会改变 §4.2 已经裁决的闭集），改为在 §5.1 的启动校验里增加一类纯静态的环检测，见 §5.1。环是配置的性质、不依赖目录，与 §5.1 已有的那一类同源。

### 2.3 终点范围

**用户裁决。** 「终点」终的是 provider **和**模型名两者。

`claude-opus-4.8: A/claude-opus-5` 读出 provider=`A`、模型=`claude-opus-5` 之后，**不再回 `model_mappings` 查 `claude-opus-5` 有没有下一跳**，直接进入 §2.4。

被否决的替代（只锁 provider、模型名继续沿链解析）会引入两条额外规则——后续条目也带限定时怎么办、以及 provider 已锁定这件事在配置文本里读不出来——换来的只是救一种运维本就不该写的写法。

**已知代价**：`claude-opus-4.8: A/opus-alias` 这种「限定值指向另一个别名」不会继续解析。`opus-alias` 不在 A 的目录里，于是走 §2.4 的 passthrough，回退到客户端原本请求的 `claude-opus-4.8`——而那通常是个别名键、不在任何目录里，所以结果是 `UnknownModel`，不会把垃圾名字发给上游。

**但这不是无条件的**，理由见 §2.4 修订后的说明：若客户端请求的那个名字本身恰好是 A 目录里的一个模型，回退会命中它，请求就以那个名字发出。判为可接受——那是既有的 passthrough 语义，不是本次引入的，而且它命中的是一个 A 确实提供的模型，不是一个凭空的字符串。

### 2.4 最终解析

discovery pass 结束后得到 `(provider, model_name)`。此时才查该 provider 的 `available_ids`：

- `canonical(model_name)` 命中 → `resolved` 取目录里那个 id，保留目录的原始拼写
- 不命中 → **passthrough**

**passthrough 时 `ModelResolution.resolved` 仍返回原始请求名**（`requested.strip()`），维持今天的行为不变。**本次推导。**

这个选择**有**可观察后果，而本 Spec 的首版把它写成了没有后果的。首版的原话是「passthrough 的名字既不在 `available_ids` 也不在 `_descriptors` 里，必然得到 `None`，于是 `raise UnknownModel`——passthrough 的名字从来不会真的发给上游」。**那是错的**，2026-08-27 由事实评审用可复现探针推翻：`describe()` 查的是 `resolved`，而 passthrough 恰恰把 `resolved` 设回**原始请求名**——所以只要原始名本身在该 provider 的目录里，`passthrough=True` 与 `describe(resolved) is not None` 就同时成立，请求以原始名正常发往上游。构造它只需要一条指向不存在目标的映射：provider 提供 `real-model`，而表里写着 `real-model: missing-target`。

规则评审（F-04）独立发现了同一条，并给了一个**不需要构造**的例子：随包 `bundled-config.yaml` 本来就有 `claude-opus-4.5: claude-opus-5`，而某个账号的目录里有 `claude-opus-4.5`、没有 `claude-opus-5`（未获授权，或该 id 尚未对其开放）。请求 `claude-opus-4.5` 于是走 passthrough，`describe("claude-opus-4.5")` 命中，请求真的发往上游——**映射被静默忽略**。

它还指出一个首版完全没想到的连带后果：`model_thinking_effort` 按 **resolved id** 命中（`schema.py` 那条注释是特意写的），`strip_anthropic_beta_flags` 与 `cache_control_sanitize` 同理。所以这条路径上，这些表会按**被映射前**的名字生效。这也是可观察差异，不只是错误消息。

所以真实语义是：**一条映射的目标不可用时，解析放弃该映射，回退到客户端原本请求的名字；那个名字可用就用它**。这是既有行为，`model_resolution.py` 里那句「the spec says pass through」指的正是它。

本次维持不变，理由与首版给的那个不同，且不依赖那个错误事实：这条语义与多 provider 无关。改它会改变**单 provider 部署**的可观察行为——一部分今天能被服务的请求会开始报错——而本次改动没有任何一条需要它改。

`UnknownModel` 带上链末名字（§5.2）因此是对**另一半**情况的补救：原始名也不可用、于是确实抛错的那一半。

### 2.5 这**改变**了单 provider 的既有行为，声明在此

**本次推导**，由 2026-08-27 规则评审 F-02 逼出。首版把 discovery pass 说成「在现有 `resolve_model` **之前**增加一趟」，那句话留下了两种读法，而它们发给上游的模型可以不同。本 Spec 采纳的是：**discovery pass 取代 `resolve_model` 的逐跳目录检查，§2.4 的那一次是全过程中唯一一次查目录。**

差别在于旧算法**每跳都查目录、第一个命中就返回**（`model_resolution.py` 原循环），新算法要走到链末（或遇限定、或耗尽跳数）才查。当链上某个**中间**节点在目录里、而链末不在时，两者分道扬镳：

随包已有 `claude-opus-4.7: claude-opus-5`；运维按 §6.1 追加 `claude-opus-5: A/claude-opus-6`（把 claude 赶到 A，顺手升级 id），而 A 的目录此刻只有 `claude-opus-5`、还没有 `claude-opus-6`。请求 `claude-opus-4.7`：

- **旧行为**：第一跳就发现 `claude-opus-5` 在目录里，返回它，请求成功发出。
- **新行为**：走到链末 `claude-opus-6`，A 的目录没有，passthrough → `UnknownModel`。

**这个改变是必需的，不是副作用。** 不走到链末就读不到写在链末的限定——`fable: claude-opus-5` 会在第一跳命中目录并返回，`claude-opus-5: A/claude-opus-5` 那条限定永远读不到（§9.2 的完整论证）。用户裁决「沿链走、不看 available」时选的就是这个。

**代价照单记下**：这是一处单 provider 部署也会跟着变的行为，某些今天能被服务的请求会开始报 `UnknownModel`。它影响的是「映射链的中间节点恰好可用、而终点不可用」这一形状，而那正是一条**半坏的配置**——终点不可用本来就该被发现，旧行为让它悄悄工作在一个运维没有指定的模型上。所以判为改得对，但必须声明，不能藏在「新增一趟 pass」这种说法后面。

连带：`model_thinking_effort`、`strip_anthropic_beta_flags`、`cache_control_sanitize` 都按 resolved id 命中，上面那个例子里它们从命中 `claude-opus-5` 变成不再命中。

**`docs/.human-controlled/config.example.yaml:100-102` 用用户自己的话描述了旧算法**（「若目标在可用模型列表中，直接解析命中；否则，当作别名再次尝试解析」），本次取代了它的第一句。那份文件不由本任务修改，改动写成候选材料，见 §11。

## 3. 请求侧显式指定

**用户裁决。** 请求里的模型名支持 `provider/model` 前缀，**优先级最高**，覆盖配置路由。

```
POST /v1/messages  {"model": "A/claude-opus-5"}
```

判读规则与 §2.1 的 `qualify` 完全一致：斜杠前必须精确命中 `model_providers` 的键；认不出则剔除前缀、走 `fallback_model_provider`，未配置则报错。

**与 `@format` 后缀的解析顺序必须钉死**：先 `rpartition("@")` 剥 wire format（现有 `split_format_suffix`），再 `partition("/")` 剥 provider 前缀。一个在尾一个在头，互不干扰，`A/claude-opus-5@anthropic-messages` 因此能正确解析。

### 3.1 前缀剥掉之后，模型名怎么解析

首版这里只写了一句「不再进入 discovery pass，模型名部分仍需经过现有的 `model_mappings` 别名解析」，**那句话规定了一个必然失败的做法**，2026-08-27 规则评审 F-01 指出。现有的别名解析对值一无所知，会把 `A/claude-opus-5` 整串当模型名拿去查目录；而 §6.2 恰恰要求运维给每个别名各写一遍限定，于是这些值全都带斜杠、永远查不到，请求 `A/opus` 必然 `UnknownModel`——正好否掉这条语法存在的理由。

正确的做法要三条规则，逐条钉死：

1. **模型名部分仍走 §2.1 的 discovery pass**，不是走一个对限定无感的旧解析。也就是说链照跳，限定值照样在被读到时终止那条链。
2. **链上读到的 provider 一律丢弃**。请求侧已经指名了 provider，链上任何限定都不能把它抢走。没有这一条，`A/opus` 遇上 `opus: B/claude-opus-5` 就会被送到 B，把「优先级最高」读反了。
3. **链上出现规则 2 形态（限定认不出）时，`fallback_model_provider` 不参与**。provider 已由请求定死，fallback 是「没人指定 provider 时的补救」，此处没有需要补救的空位；那条限定退化成「只提供模型名」。

于是 `A/opus` 在 `opus: A/claude-opus-5` 下解析为 provider=A、模型=`claude-opus-5`，与不带前缀的 `opus` 落到同一个地方——这正是首版想要而没写出来的性质。

### 3.2 passthrough 时报哪个名字

**本次推导**（规则评审 F-18 指出首版未定义）。请求 `A/opus` 走到 §2.4 的 passthrough 时，`resolved` 取**剥掉前缀之后**的 `opus`，不是 `A/opus`。

前缀是路由指令，不是模型名的一部分；把它留在 `resolved` 里会让它流进 `describe()` 的查询、错误消息、日志行和 `model_thinking_effort` 的键，而那些位置期待的都是模型名。

### 3.3 这个语法在哪些端点上成立

**本次推导**（规则评审 F-13 指出首版未限定作用面）。前缀剥离做在读取请求体 `model` 字段的那一层，因此：

- **成立**：模型名在**请求体**里的端点——`/v1/messages`、`/v1/messages/count_tokens`、`/chat/completions`、`/responses`、`/embeddings` 及其 `/v1`、`/openai/v1` 前缀变体。
- **不成立**：模型名在 **URL 路径段**里的端点——Gemini 的 `/v1beta/models/{model}:{method}` 与 Azure 的 `/openai/deployments/{deployment}/…`。在那里写 `A/claude-opus-5` 会改变 URL 的分段结构，请求根本匹配不到 handler，客户端拿到 404。

不为这两个面另造一种表达（查询参数、请求头）。这个语法的用途是运维手工调试（§3 开头那条理由），而调试完全可以在请求体端点上做；为路径参数端点再发明一套写法，等于为一个调试手段维护两种语法。

**已知代价三项**：

1. `/v1/models` 不会列出 `A/claude-opus-5` 这种形式（§4.2 的 `routes` 键是裸名，§4.1 的候选集同理），所以这个语法只在文档里存在，客户端无法自动发现。它是给人用的调试手段。
2. 客户端若发送一个真的含斜杠的模型名，会被剔掉前半截。今天 GHC 目录里没有这种 id，见 §7.1，风险与配置侧同源。
3. 它是 `/api/status` 答不了的那一类问题的答案——那个端点报的是配置意图的解析结果，不是「这个 provider 现在真的能不能答」。

## 4. 对外端点

### 4.1 `GET /models`、`/v1/models`、`/openai/v1/models`

**用户裁决。** 从「只列 default provider 的 `available_ids`」（今天的行为，`src/app/server/routes/ops.py:55`）改为**报路由可达集合**。

首版把这件事写漏了一半，2026-08-27 规则评审 F-05 指出：候选集只取 `available_ids` 的并集，而 `available_ids` 里全是**上游真名**，客户端真正会发的那些别名一个都不在。用 §4.2 的示例配置对照——`claude-opus-4.8: A/claude-opus-5`、default=B——`claude-opus-5` 作为候选落到 B（无条目），列成 `owned_by=B`，**这一行是对的**；错在 `claude-opus-4.8` 根本不是候选，于是 A 承接的那条路在目录里完全看不见。声称报「可达集合」而漏掉一整类可达名字，与用户裁掉的「少报」是同一种病。

修正后的定义，**本次推导**：

1. **候选集 = 所有 provider 的 `available_ids` 并集 ∪ 所有 `model_mappings` 的键**，与 §4.2 的 `routes` 同一个口径。首版让两个端点用不同集合回答「有哪些名字可用」，没有理由。
2. 去重按 `canonical()`，**保留先出现的拼写**，顺序是「目录名（排序后）→ mapping 键（排序后）」。目录名优先，因为那是上游的权威拼写；`claude-opus-4.5` 同时是目录 id 和 mapping 键时只出现一次。
3. 对每个候选跑一遍 §2 的路由规则，得到 `(provider, 模型名)`。**跑之前先剥 `@format`**，与 `decide_route` 同序——否则一个带格式后缀的 mapping 键在这张表里与在真实请求里走两条不同的解析，而表会列出一个发不出去的 id。格式名认不出的候选无法被任何请求路由到，报 `serviceable: "unroutable"` 而不是从表里抹掉。
4. **列出的 `id` 是候选名本身**，不是解析后的模型名。这个端点回答的是「你可以发什么」，而客户端能发的正是候选名；列解析结果会同时制造重复项和一个发不出去的名字。
5. `owned_by` 填第 3 步算出来的 provider 名。
6. 只有该 provider **确实服务**解析后的那个模型时才列出。「确实服务」的权威定义在 §4.2 的 `serviceable`，此处引用而非另行推导（规则评审 S-2：两个端点各判一次，迟早会各自演化出一套）。

被否决的两个替代：维持现状会**少报**；简单取并集而不跑路由会**多报**（只在 A 目录里、却没有任何条目指向 A 的模型，实际走 default 被拒，列出来等于承诺了一个会拒绝服务的模型）。

这个 handler 的 docstring 今天写着「The catalog routing consults」——它本来就该和路由看同一份答案，今天做得到只是因为路由只有一个 provider 可看。改动方向与它自己的声明一致，不是新加的耦合。

`owned_by` 由此第一次有真实含义。今天它填 default provider 名，对每一行都一样，等于一个常量。

**这条推导的代价要摆出来，因为用户没有见过它**：把 mapping 键收进候选集，意味着 `/v1/models` 会列出 `fable`、`opus`、`sonnet`、`gpt`、`haiku` 以及四条日期后缀别名——随包配置就有十几个。目录会变长，而客户端（Claude Code 一类）读它时会看到一批不是上游真名的条目。判断是这仍比漏报好：它们**确实可以被发送并被服务**，而 `/v1/models` 的契约就是这个。若用户认为噪音不可接受，退路是只收「解析结果与自身不同」的那些 mapping 键（即真正构成重定向的），代价是自映射式的限定条目又会看不见。**列入待用户确认清单。**

### 4.2 `GET /api/status`

**用户裁决：现有内容删除，改成最佳的。**

先说清它为什么可以被推倒。`docs/.human-controlled/api.md`（用户亲笔，最终权威）把运维端点分成两组——健康检查是 `/health/liveness`、`/health/readiness`，而 `/api/status` 属于「状态与配置」组。当前实现把 `/api/status` 和 `/health/readiness` 做成了**同一个 handler**（`ops.py:29-30`），理由写在 `ops.py:36`：两者回答同一个问题，做成两个会漂移。那个理由在单 provider 下成立，因为那时「状态」确实只剩 readiness 一件事可说。多 provider 之后不再成立。

两个佐证说明拆开是安全的：`docker-compose.yml:27` 的 healthcheck 打的是 `/health/liveness` 而非 `/api/status`；`src/app/server/admission.py:22` 的 `UNGATED_PATHS` 收了 `/health/readiness` 却**没收** `/api/status`——同一个 handler、两条路径，一条绕过准入闸门一条不绕。拆开正好消掉这个不一致。

新结构：

```json
{
  "ready": true,
  "default_model_provider": "B",
  "fallback_model_provider": "A",
  "providers": {
    "A": {"models": 38, "disabled": 12, "base_url": "https://api.githubcopilot.com",
          "catalog": "ok", "catalog_refreshed_at": "2026-08-27T10:03:11Z"},
    "B": {"models": 26, "disabled": 24, "base_url": "https://api.githubcopilot.com",
          "catalog": "ok", "catalog_refreshed_at": "2026-08-27T10:03:12Z"}
  },
  "routes": {
    "claude-opus-4.8": {"provider": "A", "model": "claude-opus-5",  "origin": "qualified", "serviceable": "yes"},
    "opus":            {"provider": "B", "model": "claude-opus-5",  "origin": "default",   "serviceable": "yes"},
    "claude-opus-5":   {"provider": "B", "model": "claude-opus-5",  "origin": "default",   "serviceable": "yes"},
    "x":               {"provider": "A", "model": "opus-alias",     "origin": "fallback",  "serviceable": "absent"},
    "y":               {"provider": "A", "model": "gpt-5.6-terra",  "origin": "qualified", "serviceable": "disabled"}
  }
}
```

**HTTP 状态码恒 200**——就绪判定已经归 `/health/readiness`，见 §4.3。

**`ready` 必须由 §4.3 的同一个判据函数产出**，不是在这里另算一遍。这是首版遗漏的一处（规则评审 F-16），而且是它自己引用过的那种漂移形态：`ops.py:36` 拒绝拆成两个 handler 的理由就是「同一个问题两处各答一遍会漂移」，拆开之后如果让 `ready` 自己算，漂移就从 handler 层搬到了字段层。

### 4.2.1 `routes` 的键集合

收 **「所有 mapping 键 ∪ 所有 provider 的 available_ids」**。**用户裁决**，选的是全集而非「只收 mapping 键」或更小的集合。

去重与拼写取舍**与 §4.1 第 2 条相同**：按 `canonical()` 去重，保留先出现的拼写，顺序是目录名先、mapping 键后。首版只写了「去重，别名优先」，规则评审 F-11 指出那句话既没定义等价类（按字面还是按 `canonical`），在新规则下也没有可观察效果——路由结果只由 §2 决定，与名字来自哪个集合无关。所以「别名优先」这个说法撤销，改为上面这条明确的拼写规则。

收全集的理由：省下的那几十条恰恰是「我没配它、所以它走 default」这一类——而「走 default」正是 §6.1 那个已知缺口最容易出错的一格。上游新上线 `claude-opus-6`，没人给它写条目，它静默落 default；全集会把这一行**列出来**，较小的集合里它根本不出现，和「这个模型不存在」长得一样。

**首版在这里多说了一句站不住的话**（规则评审 F-17）：「运维扫一眼 `origin` 就能发现有个 claude 落在 B 上」。撤销。随包配置里 `fable`、`opus`、`sonnet`、`gpt`、`haiku` 加四条日期后缀条目，只要没被改写成限定形式，`origin` 全是 `default`；default provider 自己目录里的每个 id 也全部无条目、全部 `default`。新上线的 `claude-opus-6` 在这几十行里与它们**逐字同形**。全集的价值是让那一行**存在**（这仍然远好过不存在），不是让它显眼。

### 4.2.2 `serviceable` 是枚举，不是布尔

**本次推导**，由规则评审 F-06 逼出。首版写成布尔加一个自由文本 `detail`，而它要表达的事实至少有四类，运维动作各不相同：

| 值 | 含义 | 运维该做什么 |
|---|---|---|
| `yes` | 该 provider 现在就能服务这个模型 | 无 |
| `absent` | 解析出的模型不在该 provider 的目录里 | 等上游，或改映射的值 |
| `disabled` | 在目录里，但被该 provider 的 `disabled_models` 禁掉了。判定按 `canonical` 折叠比较，与这套代码里其它每一处模型名比较一致——运维从 41 行的 `disabled_models` 里抄 id 时把 `.` 写成 `-` 完全可能，而精确匹配会让这一行退回 `absent`，说出这个取值本来要消灭的那句话 | 改自己的配置 |
| `unknown` | 该 provider 的目录尚未加载（`catalog` 不是 `ok`） | 看认证与网络，别去查模型 |
| `unroutable` | 没有 provider 可去：`origin` 是 `fallback` 而 `fallback_model_provider` 未配置 | 配 fallback，或修正那条限定 |

首版的布尔把前四类压成一个 `false`，而它给出的唯一 `detail` 例句「not in A's catalog」**对 `disabled` 那一类是错的**——它就在目录里，是你禁的。运维照着这句话去查 A 的目录，会发现它明明在。`detail` 字段随之取消：枚举已经说清了，一个没有取值词表的自由文本只会再长出一套方言。

`unroutable` 那一行的 `provider` 填 **JSON `null`**。这是规则评审 F-07 指出的洞：§1.2 允许不配 fallback，§5.1 只 WARN 不阻塞启动，§5.3 让这类请求在运行时报错——三条合起来允许一个正常启动、正常运行的部署里存在「没有 provider 可去」的条目，而首版的结构里 `provider` 只有一个字符串槽，实现者只能在 `null`、空串、和撒谎填 default 之间猜。`null` 是唯一不撒谎的那个。

### 4.2.4 `intended`：当实际发出的名字不是配置要的那个

**本次推导**，实现期补入。§2.4 说明了一条映射的目标不可用时，解析会放弃该映射、回退到客户端自己的名字——而那个名字可能恰好可用，于是请求以它发出、映射被静默放弃。

这是两个同时为真的事实：**会发出去的名字**，和**配置本来要的名字**。一个字段装不下，所以 `routes` 的行在两者不同时多带一个 `intended`：

```json
"claude-opus-4.5": {"provider": "B", "model": "claude-opus-4.5", "intended": "claude-opus-5",
                    "origin": "default", "serviceable": "yes"}
```

`serviceable` 仍是 `yes`——请求确实会被服务，报 `absent` 会撒谎。运维要看的是 `intended` 与 `model` 不一致这件事本身。

两者相同时**不输出**该字段，而不是输出一个等于邻居的值：一个多数时候与旁边那格相同的字段，会把读者训练成跳过它。

### 4.2.3 `providers` 各字段的口径

| 字段 | 定义 |
|---|---|
| `models` | `len(available_ids)`，即**可用**数，已减去 `disabled_models` |
| `disabled` | `disabled_models` 里**确实出现在该目录中**的数量。目录总条目数 = `models + disabled` |
| `catalog` | `"ok"`（目录非空）或 `"empty"`（尚未加载成功，或加载到了空目录） |
| `catalog_refreshed_at` | 最近一次**成功**刷新的 ISO 时间戳；从未成功过则为 `null` |

首版的示例在这里自相矛盾（规则评审 F-06 问题三）：B 被写成 `"catalog": "empty", "catalog_refreshed_at": null`，却同时有 `"models": 26`，而下面三行路由到 B 的记录全是 serviceable。上面的示例已改为两个 provider 都 `ok`，并另加了 `absent` 与 `disabled` 两行来展示枚举。

`serviceable` 补上 §5.1 裁掉的两类启动校验（模型不在目录、被 `disabled_models` 禁用），形式是「随时可查」而非「启动时打日志」——查的是运行中实例的当前状态，包括目录刷新之后的变化。

与 `/api/config` 的分工：后者是 `ProxyConfig` 的字段全集快照（`ops.py:88`），说「配置里写了什么」——全集但不逐字，`proxy` 的 userinfo 被替换成 `***`，那是它唯一改写的值；本端点说「它实际解析成了什么、现在能不能服务」。

### 4.3 `GET /health/readiness`

从 `/api/status` 拆成独立 handler。**就绪判据改为「`default_model_provider` 有目录」**。**用户裁决。**

今天的判据是 `any(entry["models"] for entry in providers.values())`——任一 provider 有目录即就绪。多 provider 下它会**谎报**：default 是 B，B 的目录刷不出来（token 过期、网络故障）而 A 好好的，`any` 报 200，supervisor 把流量发过来，然后每一个没写限定的请求（绝大多数）都撞 `UnknownModel`。这正是现有 docstring 拒绝用布尔值时担心的那件事的升级版——它当时担心「空目录报就绪等于让 supervisor 把流量发给一个会全部拒绝的进程」，多 provider 只是让「空」变成了「关键的那个空」。

`all`（全部 provider 都有目录才就绪）被否决：一个次要 provider 挂了只影响被显式限定到它的那部分请求，那是**降级**，不是不可用；让整个实例退出轮转，代价远大于收益。

**已知代价一**：`fallback_model_provider` 挂了不影响就绪判定，于是「provider 名认不出 → 走 fallback → fallback 没目录 → `UnknownModel`」这条路上的失败，readiness 看不见。判为可接受——那条路本来就是配置写错时的补救道，不该参与就绪判定。

**已知代价二**（规则评审 F-19 补，首版只记了对称的另一半）：这个判据会**谎报不可用**。按 §6.2 推荐的写法，一个把常用模型全部限定到 A 的部署，其真实流量可以几乎不经过 default provider B；B 的 token 过期时，实例被判 not-ready 退出轮转，而它此刻能正常服务绝大部分实际流量。这与 §4.3 要消灭的「谎报可用」是同一枚硬币的两面。

判为可接受，理由是 §6.1 让 B 永远不是纯摆设——**任何没有条目的名字都落 B**，包括上游新上线的模型和客户端拼错的名字。B 挂了，那一整类请求就全废。但它是一条已知代价，本节既然显式列代价，缺了它会让读者以为这个方向不存在。

**响应体**（实现期定，本次推导）：`{"status": "ready" | "uninitialized", "default_model_provider": <名字>, "models": <可用数>}`。带上后两项而不只是 status，是因为拆分后这个端点仍要能独立回答「不就绪是谁的问题」——而在多 provider 下，那个答案不再显然。

**`admission.py` 的 `UNGATED_PATHS` 不需要改**（首版这里写的是「顺带对齐」，含糊）。它今天收了 `/health/readiness`、`/health/liveness`、`/metrics`，没收 `/api/status`——**拆分之后这恰好就是对的**：健康检查必须在准入闸门之外，好让 supervisor 在过载时仍能探测；而 `/api/status` 现在要跑一遍完整路由表，是重量级查询，被闸门管住是合适的。首版之所以把它列为待办，是因为当时两条路径共用一个 handler，同一段代码一边受闸门管一边不受——那个矛盾由拆分本身消除，不需要额外改动。

### 4.4 日志行不报 provider

**用户裁决。** `RequestLine`（`src/app/observability/request_log.py:104`）**不新增** provider 字段，控制台行不显示请求去了哪个上游。要查就用 §4.2 的 `/api/status`。

被否决的替代是「多 provider 部署时每行都报」。记下它被否决这件事，是因为它有一个真实论据而非只是啰嗦：`RequestLine` 的 docstring 已经为 `model` 立过规矩——空就整段省略、不打占位符；「缺席」这个位置已被占用，若再让缺席额外承载「= default」，一个位置就要表达两件事。用户裁定不报，于是这个论据不再适用，但它对将来任何「要不要按条件打印 provider」的提议仍然有效。

## 5. 校验与错误

### 5.1 启动校验只做一类

**用户裁决。** 只校验「限定的 provider 名不在 `model_providers` 里」，以 WARN 形式报出涉及的 mapping 键，**不阻塞启动**。

这一类**不看目录**，是纯静态检查，因此校验点落在**配置加载完成**那一刻，不必等 `refresh_catalogs`。

被裁掉的两类——限定的模型名不在该 provider 目录里、被该 provider 的 `disabled_models` 禁用——**不做启动校验**，交给 §4.2 的 `serviceable` 随时可查，以及运行时的 `UnknownModel`。此裁决同时让原本为它们准备的两条约束失效，不再需要：「目录为空的 provider 跳过校验」与「只在启动时校验一次、不随 `model_refresh_interval` 重复」。

### 5.1.1 WARN 要说清后果，不只说「认不出」

**本次推导**（规则评审 S-1）。启动时已经同时知道「哪些键的限定认不出」和「`fallback_model_provider` 配没配」，所以这条 WARN 应当区分两种未来：

- 配了 fallback：「这些键会走 fallback 到 X」——降级运行，运维可以从容处理。
- 没配 fallback：「这些键的请求**必然报错**」——已经坏了，只是还没有人发过这些请求。

用户裁掉的是**启动失败**这个方向，不是「在 WARN 里把话说完」。第二种情形下，运维能在第一个请求到来之前就知道自己坏了。

### 5.1.2 另外两类纯静态检查，一并 WARN

**本次推导，且扩大了用户裁决时的清单，列入待确认清单。**

理由是它们与用户**保留**的那一类同源（纯静态、不看目录、配置加载完即可判），而与用户**裁掉**的那两类不同源（那两类依赖 live catalog）。用户裁决的理由针对的是「依赖目录」，不是「除了 provider 名以外一律不查」。

1. **限定的模型名部分为空**（规则评审 F-15）。`x: A/` 会走规则 1、provider=A、模型名是空串，一路带着空串走到 §2.4 的目录查询（必然不命中）、§5.2 的错误消息、§4.2 的 `"model": ""`。这必然是配置错误，零成本可判。同族的还有 `x: ""`（schema 是 `dict[str, str]`，空值能通过校验）。
   顺带明确一个读者可能以为未定义的输入：`x: /claude-opus-5`（斜杠开头）头段是空串、不是任何 provider 名，走规则 2 → fallback。**这是对的**——少打一个 provider 名就是配错了，走补救道正合适。
2. **别名链成环**（规则评审 F-03）。`opus: claude-opus-5` 是随包默认就有的；运维为让两个拼法互通再写 `claude-opus-5: opus`，两个名字之间就会跳满 8 跳、静默落 default（§2.2.1 的 (c)）。环是配置的纯粹性质，不依赖目录，一次遍历即可查出。

两条都是 WARN、都不阻塞启动——与用户为第 1 类定的调子一致。

### 5.2 `UnknownModel` 的消息带上链末名字

**本次推导。** passthrough 把 `resolved` 设回原始请求名（§2.4）。当原始名**也**不可用时——这是 passthrough 里真正报错的那一半——`decide_route` 抛 `UnknownModel`，而它手上只有原始名。为了让错误对运维有用，`UnknownModel` 的消息除了报 `resolved`，还要带上 discovery pass 走到的链末模型名。

`claude-opus-4.8: A/claude-opus-5` 而 A 的目录里没有 `claude-opus-5` 时，运维需要看到的是「`claude-opus-5` 在 A 上不存在」；只报 `claude-opus-4.8` 会把人引去检查别名**键**有没有写错，而错的是值。

两个名字相同时不重复输出，否则每条普通的「模型不存在」都会拖一句同义反复。

### 5.3 未配置 `fallback_model_provider` 时的请求报错

**用户裁决。** 走到 §2.2 规则 2、而 `fallback_model_provider` 未配置时，**该请求报错**，不落 default。

这是请求级错误，不是启动失败——用户明确裁掉了「启动失败」这个方向。错误在任何网络请求之前抛出，与现有 `RoutingError` 的定位一致（「Raised before any network request, so an unroutable request never reaches upstream」）。

错误信封按 `.dev/docs/error-envelope/spec.md` 的既有规则渲染；本文不重复定义那套映射。

## 6. 已知缺口

本节记的是这套设计**明知**会漏、且用户知情接受的情况。它们不是待办，是设计的边界。

### 6.1 没有条目的模型静默落 default

**用户裁决**：「用 default model provider」。

路由信息只存在于 mapping 条目里，而 `resolve_model` 有两条不经过任何条目的出口——客户端直接发一个上游真名、且该名字没有自己的 mapping 条目时，整个解析不碰任何条目。对着现有 `bundled-config.yaml` 核过：`claude-opus-5` 自己没有条目，`fable: claude-opus-5` 是别名指向它。

所以「所有 claude 走 A」**无法用一条规则表达**，得让每个要路由的 claude 模型 id 都有一条属于自己的条目。自映射 `claude-opus-5: A/claude-opus-5` 即可——它带限定所以是终点，不产生自环。

**代价是静默的**：上游哪天上线 `claude-opus-6`，它没有条目，落 default，不报错、不打日志。缓解手段是 §4.2 的 `routes` 全集——运维扫 `origin` 能发现它。

被否决的两个替代：让 mapping 的**键**支持正则（会让一张表里同时存在两种匹配语义，且要再定一套优先级规则）；在限定之外再加一个兜底路由表（等于把被否决的顶层路由表塞回来，语义分散到两处）。

### 6.2 别名各写各的限定

§2.3 的终点语义意味着，同一个模型的每个别名若都要走 A，就得各写一遍限定：`fable: A/claude-opus-5`、`opus: A/claude-opus-5`、`claude-opus-4-5-20251101: A/claude-opus-5`、`claude-opus-5: A/claude-opus-5`。漏写一行，那个拼法走 default，同样无声。

同样靠 §4.2 的 `routes` 全集缓解：每个别名都是一行，`origin` 不一致会显出来。

### 6.3 含斜杠的上游模型 id 无法映射

§2.1 规定斜杠前必须精确命中 provider 名，认不出就剔除前缀。所以若上游哪天出现 `vendor/model` 形态的 id，它既不能作为 mapping 的值原样写出（前半截会被当作 provider 名剔掉），在请求侧也会被剔掉前半截。

今天不存在这种 id，见 §7.1。真出现那天，逃生舱是结构化值写法（`{provider: A, model: vendor/x}`），成本不比现在加高。

## 7. 支撑本设计的实测

### 7.1 GHC 目录里没有含斜杠的模型 id

2026-08-26 全仓扫描，2026-08-27 由事实评审用独立正则复核：`docs/.human-controlled/config.example.yaml` 的 `disabled_models` 共 41 条（含注释掉的），全部不含 `/`；对 `src`、`tests`、`docs` 扫「vendor 前缀 + 斜杠」形状的 token，得到 **3 个不同取值、6 处出现**，无一是模型 id——`claude-cli/2.0.0` 是 User-Agent（4 处），`gpt-model/responses` 是一段 Azure 路径（1 处），`e2e/claude/cassettes/` 是测试素材目录（1 处，在 `docs/.human-controlled/test-org.md`）。首版 Spec 把这第三项写成了「一条插件路径」，并把 3 个取值说成 3 处命中。

**权重：足以支撑「今天没有」，不足以支撑「将来不会有」。** GHC 目录横跨 OpenAI、Anthropic、Google、Microsoft 四家 vendor，而 `vendor/model` 命名在业界常见。§6.3 因此存在。

### 7.2 两个 GHC provider 的连接会被复用到一起

`httpx2.AsyncClient` 在 `src/app/server/composition.py:173` 构造一次，传给 `build_chain`，**所有 provider 共享**——`composition.py:460-484` 把同一个 client 交给循环里的每一个。

共享的后果要说得比首版精确，两处收窄都来自 2026-08-27 的事实评审：

- **不是「一个池」。** `cap_streams_per_connection` 遍历 default transport 与全部 mounted transport，给每个 distinct pool 各加一次 cap（`src/app/upstream/stream_cap.py:124`）。首版说 cap 打在「那一个池」上，不对。
- **不是「必然同 host」。** httpx 按 scheme/host/port 复用连接，而 `resolve_provider_base_urls`（`composition.py:333-405`）用每个 provider **自己的 token** 去探测订阅类型，individual / business / enterprise 解析出的是不同 host（`ghc_client/config.py:35-44`）。两个同类型账号会落到同一个 origin，一个个人版加一个企业版不会。

于是真正成立的陈述是：**当两个 provider 解析到同一个 origin 且走同一条 mount 时，它们的请求共享同一批 TCP 连接。**

这仍是 §8.1 的依据，且收窄之后依然成立——只要存在会共享连接的配置（而两个同类型账号正是最常见的那一种），隔离就得由结构提供，不能寄望于运维恰好用了两个不同订阅。项目已为连接级故障付过一次代价：`.dev/docs/upstream/h2-goaway/findings.md` 记的那次，一个 GOAWAY 在同一瞬间打断 4 个在飞请求。

## 8. 运行时隔离

### 8.1 每个 provider 一个 httpx client

**用户裁决。** 各自连接池，`cap_streams_per_connection` 各打各的。

§7.2 说明了共享的后果——**在两个 provider 落到同一 origin 的那些配置里**：A 那边触发的 GOAWAY 会打断 B 的在飞请求，而 `max_streams_per_connection: 1` 这种配置的字面承诺（一条连接一个请求）仍然成立、**隔离却没有**，因为它限的是流数不是归属。

token 走 header 不走连接，所以共享连接不会串号——这一点不是问题，记在此以免后来者重新担心一遍。

被否决的「按 `api_base_url` 分组共享」保留的恰恰是最坏的情况：两个同类型账号（两个 individual，或两个 business）会被 `resolve_provider_base_urls` 解析到同一个官方 host，分组在那种配置下等于完全共享；它只在两个 provider 的 origin 本就不同时才生效，而那时 httpx 本来就不会复用连接。也就是说，分组恰好在需要它的场合无效、在不需要它的场合才动作。

**代价**：连接数乘以 provider 数，`composition.py:173` 的构造从「一个」变成「每 provider 一个」，生命周期（关闭）跟着变。provider 数是个位数。

### 8.2 三张表维持全局

**用户裁决。** `model_thinking_effort`、`hook_fix_anthropic_request.cache_control_sanitize`、`hook_strip_anthropic_request_headers.strip_anthropic_beta_flags` 仍是全局的，两个 provider 共用同一份。

这与隔壁 `models_support_web_search` 的 per-provider 归属**不一致**，而项目还专门论证过那一张不能合并——`composition.py:488` 说的是「每个 provider 的 patterns 分开保存，免得空列表继承别人的条目」，而那句更锋利的「模型 id 唯一，不代表两个 provider **跑**它的方式相同」在 `src/app/pipeline/subscribers/hosted_web_search.py:60`（首版 Spec 把两处归成了一处）。不一致是有理由的，它们问的不是同一类问题：

- 三张表记的是**上游 API schema 拒收什么**（`cache_control` 的 `scope` 子字段、某些 beta flag 名、某个模型发不发 `output_config.effort`）。那是 Copilot 这个产品的行为，与用哪个账号访问无关。
- `models_support_web_search` 记的是**哪些模型实际会执行搜索**，是手工维护的运维知识——2026-08-20 实测 42 个模型的 `capabilities.supports` 里没有任何 web-search 位，目录答不了这个问题。那是「这个部署能不能」，确实可能因 provider 而异。

**失效条件**：若某个 provider 被指向企业版 base_url（`api_base_url` 与 `auth_base_url` 都可配，schema 注释说企业安装会同时挪这两个），它的 API schema 就可能与公有云不同，全局表会对其中一个 provider 说错话。今天没有这样的部署。

迁移路径（真到那天）：键下放到 `model_providers.<name>`，全局那份作为默认值。这与 `composition.py:488` 反对的合并不是一回事——它反对的是 provider **之间**互相继承（A 的空列表捡到 B 的条目），而「全局默认 + per-provider 覆盖」是层级覆盖，不会让一个 provider 拿到另一个 provider 的许可。

### 8.3 明确不动的

| 对象 | 现状 | 为何不动 |
|---|---|---|
| metrics | 三个 Counter，均不带 provider 标签 | 它们的语义本就与 provider 无关（按模型计的翻译损失与 flag 清洗）。「A 承接了多少请求、错了多少」这类指标**今天根本不存在**，单 provider 也没有，不是本次改动造成的缺口 |
| `rejection_capture.py:66` | 已在记 `context.provider_name` | 多 provider 下自动就是对的 |
| `model_mappings` 的**键**语义 | `canonical` 与 `candidate_keys` 的等价拼写规则 | 本次只动值，不动键 |
| `proxy`、`upstream_transport` | 全局 | 超出本次范围。真需要时下放到 `model_providers.<name>` |
| history | live chain 无实现、无端点；完整实现归档在 `src/.archived/app/history/` | `ops.py:7` 的原话限定为「这条 chain 不拥有它需要的状态，所以端点缺席，而不是拿一个像模像样的桩去糊弄」。首版 Spec 把这句扩写成了「本项目没有实现」，过宽——归档目录以点号开头，`fd` 默认跳过隐藏目录，第一次清点因此没看见它 |
| `rate_limiters` | 已 per-provider（`composition.py:528`） | 本来就对 |
| 每 provider 的 `CopilotTokenManager` | 已 per-provider | 本来就对 |

顺带修一处陈旧引用：`src/app/pipeline/subscribers/hosted_web_search.py:90` 的 docstring 说 `provider_name` 由 `server/handler.py` 设置，实际是 `apply_route`。

### 8.4 目录加载必须逐 provider 隔离，否则 §4.3 的理由不成立

**本次推导**，2026-08-27 实现评审 MPR-03 发现。

`refresh_catalogs` 原本是一个没有保护的循环：任何一个 provider 的 `refresh_catalog()` 抛出（token 文件缺失、上游不可达），整趟就结束。而 `chain.providers.names` 是 `frozenset`，迭代顺序来自哈希、不来自配置。所以**次要 provider 排在前面且认证失效时，default provider 的目录根本不会被加载**。

后果是致命的，因为没有任何东西会重试：`refresh_catalogs` 只在 `_lifespan` 里调一次，`run_model_refresh_loop` 全仓无调用者，`model_refresh_interval` 在这条链上没有消费者。于是 `/health/readiness` 会**终身 503**，而那个能服务绝大部分流量的账号完好无损。

这直接打脸 §4.3 选择「default 有目录即就绪」而否决 `all()` 的理由——那条理由说「次要 provider 挂了只影响被显式限定到它的那部分请求，是降级不是不可用」。判据本身是对的，但把目录填进去的那条路没有相应的隔离，于是「次要 provider 挂了」实际会变成「整个实例不可用」。

**规范**：每个 provider 在自己的保护里刷新，失败记 WARNING 并继续；迭代顺序取 `sorted(names)`，让同一份部署的两次启动刷新顺序相同。同模块的 `resolve_provider_base_urls` 早已是这个形状。

## 9. 被否决的方案

### 9.1 路由判据的载体，§1.1 的三个替代

| 方案 | 否决理由 |
|---|---|
| 新增顶层 `model_provider_routing`，正则映射到 provider，首个命中生效 | 用户选择了 `model_mappings` 载体。此方案曾被本文作者推荐，理由是 `model_mappings` 在 spec 里是「模型名映射的唯一来源」，让它同时承担改名和去向会让一个键坏掉两个语义 |
| 每个 provider 各带 `serves` 正则表，启动时合并 | 归属看似更正确，但路由是**全局仲裁**，把仲裁拆到 N 处再合并，等于把冲突检测从「读一张表」变成「跑一次合并」 |
| 只认客户端显式指定，配置侧不做隐式路由 | Claude Code 这类客户端不会发 provider 后缀，功能形同虚设。**但它作为补充而非替代被采纳了**，见 §3 |

### 9.2 限定沿别名链的读法

用户选了「沿链走、不看 available」，并把终止条件精化成「遇到限定即终点」。这个组合有个不明显的好处：**自环问题被消解了**。

若沿用今天 `resolve_model` 的循环顺序（先查 available、命中就返回），`fable: claude-opus-5` 会在第一跳就因 `claude-opus-5` 在目录里而返回，`claude-opus-5: A/claude-opus-5` 那条**永远读不到**——同一个模型两种去向，取决于客户端发 `fable` 还是发 `claude-opus-5`，无声。

而若沿链走到底再看 available，自映射 `claude-opus-5: A/claude-opus-5` 就成了自环，要靠 `_MAX_ALIAS_HOPS` 兜底，白跑 8 跳且吃掉 hop 预算——链再长就会在中途被截断，表现为「解析成了链中间那个名字」，不报错。

「遇到限定即终点」同时避开两者：带限定的值一读到就停，自映射根本不跳。

**但它只消解了自映射的环，不消解互指环。** `X: Y` 与 `Y: X` 全程无限定，不受终点规则保护，仍会跳满 8 跳并静默落 default——上一段描述的那个症状（「解析成了链中间那个名字，不报错」）在采纳的设计里依然存在。首版这一节读起来像是环的问题已经整体消失，那是过头的。处置在 §5.1.2：加一条纯静态的环检测 WARN。

## 10. 验收

### 10.1 验收方式

**用户裁决：mock 为主，不做真实账号验证。**

这次改动几乎全是本地逻辑——解析规则、配置校验、两个端点的渲染。上游行为不参与任何判据，换个上游这些判据照样成立，所以不需要新录 cassette。

- 解析规则表五行（1、2、3、4a、4b），含终点范围、剔除与 fallback、未配 fallback 的报错：unit
- **§2.4 的 passthrough 行为**：目标不可用而原始名可用时请求照常发出（这是 §2.4 修订后才写清的语义，必须有一条测试钉住它，否则下一个人会把它当 bug 修掉）；原始名也不可用时抛 `UnknownModel`：unit
- **§2.5 的行为变更**：链中间节点可用而链末不可用时走 passthrough，而不是就地返回中间节点：unit
- **§3 全部**：请求侧 `provider/` 前缀、`@` 与 `/` 的解析顺序（`A/claude-opus-5@anthropic-messages`）、§3.1 的三条规则（链照跳、链上 provider 丢弃、fallback 不参与）、§3.2 的 passthrough 名字：unit
- **§5.2 的 `UnknownModel` 消息**含链末模型名，两名相同时不重复：unit
- 配置校验：§5.1 的三类 WARN（provider 名认不出、空模型名、成环）、§5.1.1 的两种措辞、§1.2 的启动失败、§1.3 的改名报错：unit
- `/v1/models`（含 §4.1 的候选集与去重规则）、`/api/status`（含 `serviceable` 五个值）、`/health/readiness`：unit
- 「claude 走 A、其余走 B」：component 级，双 mock provider

首版的清单漏了其中五项（规则评审 F-09），其中 §3 最要紧——它是一条用户裁决的、对外可见的语法，且 Spec 自己强调「解析顺序必须钉死」，而把两个 `partition` 写反、或对 `@` 误用 `partition` 而非 `rpartition`，没有测试就没人会发现。

### 10.2 未验证事项

**§8.1 的凭据隔离与连接池隔离不经真实验证。** 用户裁掉了真实双账号 canary（需要第二个 GitHub Copilot 账号）与同账号双 provider 实测两个选项。

这意味着：「两套凭据各自认证、两个连接池互不干扰」这一条**只有代码结构上的保证，没有运行证据**。本条显式记在此，以免后来者从「测试全绿」读出它已被验证过。

真要验证时的最小手段：同账号配成两个 provider 起服务，能覆盖除凭据隔离外的一切（路由、`/api/status`、请求侧 `A/model` 语法）；凭据隔离只有两份真 token 才能证明。

## 11. 交付约束

- `docs/.human-controlled/` 下的文件（`config.example.yaml`、`api.md`）**一律不由本任务修改**。需要它们改动的地方写成候选材料放 `.dev/human-controlled-docs-candidates/`，等用户摘取。`config.example.yaml` 在本任务开始时处于用户手上的未提交修改状态。

  **候选材料清单**（首版只点名了第 1 条，其余由规则评审 F-08 补出）：

  1. ~~`config.example.yaml:71` 的 `ghc` 改名为 `upstream`~~ — **已撤销**，2026-08-27。改名本身建立在对该字段的误读上，见 §1.3。这一行不需要任何改动。
  2. **`config.example.yaml:100-102`** — 用户亲笔的解析算法描述「若目标在可用模型列表中，直接解析命中；否则，当作别名再次尝试解析；仍不可用则放弃映射、直接透传」。§2.5 取代了它的第一句：新算法全程不查目录，走到链末才查一次。**这一条最要紧**——一份用户亲笔的文档正在描述代码已经不做的事。
  3. **`config.example.yaml:74-78`** — 「模型名映射：请求模型 → 目标模型」「这是模型名映射的唯一来源」。§1.1 让**值**多承担一个 provider 限定，「目标模型」这个说法不再完整。
  4. **新增顶层键 `fallback_model_provider`**（§1.2）——`config.example.yaml` 是带注释的完整样例，新键不在里面，运维无从知道它存在，而 §5.3 让它成为一整类请求能不能工作的开关。
  5. **`request-pipeline.md:11`** 用 `claude-sonnet-5 -> gpt-5.6-terra@openai-responses` 描述映射关系，而 §2.1 明确 mapping 的值**不支持** `@format`。是纠正该文档的写法，还是把值侧的 `@` 实现出来，请用户裁。

## 12. 待用户确认清单

本节列的是**本次推导中越出了用户原裁决边界的四处**。它们都有明确的理由，实现按它们进行，但用户可以推翻其中任何一条——记在这里是为了让推翻这件事不需要先把整份 Spec 读一遍。

| # | 条款 | 推导了什么 | 越出在哪 | 若被推翻 |
|---|---|---|---|---|
| 1 | §4.1 | `/v1/models` 的候选集加入所有 mapping 键 | 用户在「路由可达集合」上裁决过，但没见过它的后果：目录会多出 `fable`、`opus`、`sonnet` 等十几个别名 | 退路是只收「解析结果与自身不同」的 mapping 键，代价是自映射式的限定条目又看不见 |
| 2 | §5.1.2 | 启动 WARN 增加两类：限定的模型名为空、别名链成环 | 用户裁的是「三类里只留第 1 类」。新增两类与保留的那类同源（纯静态、不看目录），与裁掉的两类不同源（依赖 catalog） | 去掉即可，两者都不影响路由行为 |
| 3 | §2.1 | mapping 的值**不支持** `@format` | 用户没被问过这件事。它今天本来就不支持，Spec 只是把沉默改成明说 | 若要支持，是一个独立特性，不在本次范围 |
| 4 | §3.3 | `provider/` 前缀只在模型名位于请求体的端点上生效 | 用户裁的是「支持请求侧指定」，没被问过作用面。Gemini 与 Azure 把模型名放在 URL 路径段上，写前缀会打断路由匹配 | 若要覆盖那两个面，需要另一种表达（查询参数或请求头），是一个独立特性 |
- 实现在隔离 worktree `worktree-multi-provider-routing` 进行，完成后 squash 回 `main`。**用户裁决**，理由是本次要动 `resolve_model` 与 `decide_route` 这两个几乎所有请求都经过的函数，中间必然有一段解析处于半成品状态；主树此刻有 4 个活跃 worktree 的同伴在并行改 `src/`，他们撞上半成品时无法分辨是自己改坏的还是别人改坏的。
- `.dev/` 只存在于主树，worktree 里没有副本。本文与后续报告写回主树的 `.dev/docs/multi-provider-routing/`。

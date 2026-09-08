# 评审报告：`multi-provider-routing/spec.md` 规则完备性与内部一致性

- **评审对象**：`/home/xp/src/ghc-api-proxy-py/.dev/docs/multi-provider-routing/spec.md`（2026-08-27 05:30 版本，v1 首稿）
- **评审轮次**：首轮，独立评审
- **总体 verdict**：`needs-fix`
- **blocker 数**：1（F-01）
- **major 数**：8（F-02、F-03、F-04、F-05、F-06、F-07、F-08、F-09）
- **minor 数**：10（F-10 ~ F-19）

## 评审范围

**在范围内**：§1 ~ §11 全文，评的是「这套规则作为一份规范，能不能被无歧义地实现，以及有没有自相矛盾」。具体覆盖：`qualify` 与 §2.2 四条规则对任意输入的覆盖与互斥性、§2 与 §3 的交互、§4.1／§4.2 两个端点的集合定义与字段语义、`origin`／`serviceable`／`default`／`fallback` 四处「一个槽装几个事实」、§6／§8.3／§10 与 §1-§5 的前后一致性、以及「只读这份 Spec 的人会不会不得不猜」。

**明确不在范围内**：Spec 引用的代码位置是否属实（另一位评审者负责）。用户裁决条款本身是否正确——我只指出后果，不评是非。扩展性建议（§9 已记录被否决的方案）。§7.2／§8.1 的连接池与凭据隔离论证（不属于规则完备性）。

**我读过的判据来源**（均在读 Spec 之前或为核对具体输入时读）：`docs/.human-controlled/config.example.yaml`（`model_mappings` 语义的用户亲笔权威，第 74-134 行）、`docs/.human-controlled/api.md`、`ghc-api.md`、`request-pipeline.md`、`module-org.md`；现有解析契约 `src/app/pipeline/model_resolution.py`、`src/app/pipeline/routing.py`、`src/app/config/bundled-config.yaml`、`src/app/config/schema.py` 的相关行、`src/app/model_provider/base.py` 的 `available_ids` 契约。读这些不是为了核 Spec 的引用是否准确，而是为了判断我举的输入是不是真的会发生。

**没有执行任何测试或探针**：本轮全部结论来自对规则文本的推演，以及对现有解析器代码逐行走查（手工执行 `resolve_model` 的循环）。凡涉及「今天的行为是什么」的断言，依据是 `model_resolution.py` 的当前代码；凡涉及「配置里真会这么写」的断言，依据是 `bundled-config.yaml` 与 `config.example.yaml` 的实际内容。

**一个贯穿全文的前提**：`bundled-config.yaml:5` 写明「用户配置**叠加**在本文件之上，而不是取代它」，所以 `fable: claude-opus-5`、`opus: claude-opus-5`、`claude-opus-4.5: claude-opus-5`、`claude-haiku-4.5: gpt-5.6-luna` 这些条目在**每一个部署里都存在**，除非被逐键覆盖。下面多条发现的「具体输入」就建立在这个事实上——它们不是我构造的假想配置，是随包默认配置加上 Spec 自己推荐的写法。

---

## 发现

### F-01 `blocker` — §3 的请求侧解析与 §2.3 的终点语义直接冲突，且在 §6.2 推荐的配置形态下，§3 的功能必然失效

**位置**：§3「请求侧显式指定」，原句：「请求侧指定命中后，**不再进入 §2 的 discovery pass**——provider 已由请求决定，模型名部分仍需经过现有的 `model_mappings` 别名解析与 §2.4 的目录查询。**本次推导**：请求侧只覆盖 provider 的选择，不覆盖别名系统，否则 `A/opus` 这种写法就不能用了。」

**相关位置**：§2.3「「终点」终的是 provider **和**模型名两者」；§6.2「同一个模型的每个别名若都要走 A，就得各写一遍限定：`fable: A/claude-opus-5`、`opus: A/claude-opus-5`……」

**问题**：这段话把请求侧的模型名交给「现有的 `model_mappings` 别名解析」，而现有的别名解析（`model_resolution.py:64-105`）对值一无所知——它把值当作普通模型名，拿去 `available_ids` 里查。可是 §6.2 明确要求运维给**每个别名各写一遍限定**，于是这些值全都是 `A/claude-opus-5` 这种带斜杠的字符串。带斜杠的字符串永远不会命中任何 provider 的 `available_ids`（§7.1 实测：目录里没有含斜杠的 id），于是别名解析走到 passthrough，`resolved` 变回请求名，`describe()` 查不到，抛 `UnknownModel`。

**结果是：§3 这句话的理由（「否则 `A/opus` 这种写法就不能用了」）恰好被它自己的规则否掉——在 §6.2 推荐的配置下，`A/opus` 正是不能用的那一个。**

**具体输入 1（功能必然失效）**：配置按 §6.2 写成 `opus: A/claude-opus-5`（provider A 与 B 均已配置，A 的目录含 `claude-opus-5`）。

- 请求 `{"model": "opus"}` → 走 §2，规则 1 命中 → provider A、模型 `claude-opus-5` → 成功。
- 请求 `{"model": "A/opus"}` → 走 §3，provider 定为 A，模型名 `opus` 交给现有别名解析 → 命中条目 `opus`，值为 `A/claude-opus-5` → 该值不在 A 的 `available_ids` 里 → 下一跳以 `A/claude-opus-5` 为键查表，无条目 → passthrough → `resolved = "opus"` → `describe("opus")` 为 `None` → **`UnknownModel`**。

同一个 provider、同一个模型，加上前缀反而失败。

**具体输入 2（两条规则给出两个不同的 provider，Spec 没有定优先级）**：同样的配置 `opus: A/claude-opus-5`，请求 `{"model": "B/opus"}`。

- 按 §3「优先级最高，覆盖配置路由」→ provider 应为 B。
- 按 §2.3「终点终的是 provider **和**模型名两者」→ 别名 `opus` 的值是一个终点，它同时定死了 provider=A 与模型=`claude-opus-5`。

Spec 说了「请求侧只覆盖 provider 的选择」，也说了「终点终 provider 和模型名两者」，两句话对这个输入给出 B 和 A 两个答案，没有任何一条规则裁决谁赢。实现者只能猜。

**具体输入 3（§6.1 推荐的自映射同样中招）**：配置按 §6.1 写 `claude-opus-5: A/claude-opus-5`，请求 `{"model": "A/claude-opus-5"}` → §3 剥前缀得 `claude-opus-5` → 现有别名解析命中自映射条目、值为 `A/claude-opus-5`、不在目录里 → passthrough → `UnknownModel`。而不带前缀的 `{"model": "claude-opus-5"}` 是成功的。

**Spec 需要补的是什么**：§3 的模型名解析不能是「现有的别名解析」，它必须是一趟**限定感知**的解析——沿链跳、遇到限定值时剥掉 provider 段只取模型名、并且明确规定被剥掉的那个 provider 是被丢弃（请求侧赢）还是被采纳（配置侧赢）；同时要规定链上遇到「认不出的 provider 段」（rule 2 形态）时，请求侧已选定的 provider 与 `fallback_model_provider` 谁赢。这三条规则一条都没写。

**定级理由**：这不是措辞含糊，是一条被裁决为「优先级最高」的用户可见语法，在 Spec 自己推荐的配置形态下必然报错，且与另一条核心条款给出互相矛盾的答案。实现者无论怎么选都会有一半的 Spec 落空。

---

### F-02 `major` — discovery pass 究竟是「在 `resolve_model` 之前」还是「取代 `resolve_model` 的逐跳目录检查」，两读会发给上游不同的模型

**位置**：§2.1，原句：「在现有 `resolve_model` 之前增加一趟 discovery pass」；§2.4，原句：「discovery pass 结束后得到 `(provider, model_name)`。此时才查该 provider 的 `available_ids`」。

**问题**：这两句支持两种读法，且它们的输出不同。

- **读法 A**：discovery pass 走完链，链末模型名就是最终模型名，§2.4 的单次目录查询是**唯一**一次目录查询——即 discovery pass **取代**了 `resolve_model` 的循环。
- **读法 B**：discovery pass 只回答 provider（§2.1 的字面：「职责是**只回答「provider 是谁」**」，且是「在现有 `resolve_model` **之前**增加」），随后现有 `resolve_model` 照常在选定 provider 的 `available_ids` 上跑一遍，**它是逐跳查目录、命中即返回的**（`model_resolution.py:81-96`）。

现有解析器在每一跳都查目录并在第一个命中处返回；discovery pass 明确「全程不查 `available`」。当链上某个中间节点在目录里、而链末不在时，两种读法产出不同的模型名。

**具体输入**：随包默认配置已有 `claude-opus-4.7: claude-opus-5`；运维按 §6.1 追加 `claude-opus-5: A/claude-opus-6`（把 claude 都赶到 A，同时顺手升级到新 id），而 A 的目录此刻还没有 `claude-opus-6`、只有 `claude-opus-5`。请求 `claude-opus-4.7`：

- 读法 A：链走到底 → provider=A、模型=`claude-opus-6` → A 的目录没有 → passthrough → `UnknownModel`。
- 读法 B：`resolve_model("claude-opus-4.7", …, available=A.available_ids)` 在第一跳就发现 `claude-opus-5` 在 A 的目录里 → 返回 `claude-opus-5` → **请求成功，发往 `claude-opus-5`**。

一个报错，一个成功并发出一次真实上游调用。

**连带后果**：`schema.py:389` 明确 `model_thinking_effort` **keyed on the resolved model id**。两种读法的 `resolved` 不同，这张表的命中与否也跟着不同——影响面不止错误消息。

**另一个必须一并写清的点**：如果作者的本意是读法 A（§9.2 的论证强烈暗示是），那么这是对**单 provider 部署既有行为的改变**：今天「目标在可用列表中就直接命中」，改后要走到链末才查。§2.4 只声明了 passthrough 名字这一项「维持今天的行为不变」，没有声明这一项**变了**。见 F-08。

---

### F-03 `major` — 跳数上限耗尽时，Spec 没说带出去的模型名是谁；而且它的 `origin` 与「运维根本没配」同形

**位置**：§2.2 规则 4，原句：「跳到无条目命中，或撞跳数上限 | 结束，provider 取 `default_model_provider` | `default`」。

**问题一（输出未定义）**：规则 4 只规定了 provider，没规定 `model_name`。「跳到无条目命中」的情形下模型名显然是当前链末名字；「撞跳数上限」的情形下模型名是第 8 跳读到的那个值，它是**链中间的一个名字**，Spec 从未说过它是答案。而 §2.4 的输入契约是 `(provider, model_name)`，§4.2 要渲染 `"model"` 字段，§5.2 要把「discovery pass 走到的链末模型名」写进错误消息——三处都需要这个值，Spec 三处都没定义它在耗尽时是什么。

**问题二（两个事实挤进一个 `origin` 槽）**：`origin` 的 `default` 同时表达三件事：（a）这个名字压根没有条目（§6.1 的已知缺口，运维**需要**发现的那件事）；（b）链走完了、全程没有限定（配置正常，运维**不需要**关心）；（c）链有环或超长（配置有 bug，运维**最需要**发现）。§1.2 为了区分「没写」和「写错了」专门开了 `fallback_model_provider` 一个新槽，理由是「合成一个槽会让「运维没配」和「运维配错了」在行为上不可区分，而后者需要被发现」——同一条理由在这里没有被应用。

**具体输入**：运维想让两个拼法互相兼容，写下 `opus: claude-opus-5` 与 `claude-opus-5: opus`（前者是随包默认就有的，所以他只需要写后面一行）。请求 `opus`：链在两个名字之间来回跳 8 次耗尽预算 → origin=`default`、provider=default → 模型名按奇偶取到 `opus` 或 `claude-opus-5`，Spec 没说是哪个。若取到 `claude-opus-5` 且它在目录里，请求**静默成功**；若取到 `opus`，passthrough 后 `UnknownModel`。`/api/status` 的这一行显示 `origin: "default"`，与旁边十几条正常别名长得一模一样。§5.1 的启动校验只查 provider 名，也不会报这个环。

**注意 §9.2 的措辞**：「「遇到限定即终点」同时避开两者：带限定的值一读到就停，自映射根本不跳。」这句话只对**自映射**（`X: A/X`）成立。上面这种**互指环**（`X: Y`、`Y: X`，全程无限定）不受终点规则保护，§9.2 自己描述过它的症状——「表现为「解析成了链中间那个名字」，不报错」——那个症状在采纳的设计里依然存在，而 §9.2 读起来像是它已被消除。

---

### F-04 `major` — §2.4 的推导依据「passthrough 的名字从来不会真的发给上游」是假的，反例是随包配置就会遇到的

**位置**：§2.4，原句：「`decide_route` 在 `resolve_model` 之后立刻 `provider.describe(resolution.resolved)`，passthrough 的名字既不在 `available_ids` 也不在 `_descriptors` 里，必然得到 `None`，于是 `raise UnknownModel`——**passthrough 的名字从来不会真的发给上游**。唯一的可观察差异是错误消息与日志行里显示哪个名字。」（标注为**本次推导**，因此完全在可评范围内。）

**问题**：passthrough 的 `resolved` 等于**原始请求名**，而原始请求名完全可以是目录里的一个真 id——只要它本身是一个映射键、而它的目标不可用。这时 `describe()` 命中，请求照常发出，**映射被静默忽略**。所以「必然得到 `None`」不成立，「从来不会真的发给上游」不成立，「唯一的可观察差异是错误消息」也不成立。

**具体输入**：随包默认配置已有 `claude-opus-4.5: claude-opus-5`。某账号的目录里还有 `claude-opus-4.5`，但没有 `claude-opus-5`（账号未获授权，或该 id 尚未对其开放）。请求 `claude-opus-4.5`：链末 `claude-opus-5` 不在目录 → passthrough → `resolved = "claude-opus-4.5"` → `describe("claude-opus-4.5")` **命中** → 请求真的发往上游的 `claude-opus-4.5`。

同一路径下，`model_thinking_effort`（keyed on resolved id）、`strip_anthropic_beta_flags` 等按 resolved id 命中的表，都会按被映射前的名字生效——这也是可观察差异，不是错误消息。

**这条为什么值得改而不只是提醒**：§2.4 用这个论证来支持「不改既有行为」，§5.2 又建立在同一个论证上（「§2.4 说明了 passthrough 的名字必然走到 `UnknownModel`」）。结论（不改 `resolved`）可能仍然正确，但理由必须重写为「passthrough 的名字**通常**走不到上游，例外是原始请求名本身就在目标 provider 的目录里；此时映射被静默放弃，与 `config.example.yaml:100-102` 描述的「上游随后拒绝它」不同——上游会接受它」。多 provider 之后这个例外还多了一层：passthrough 时拿去 `describe` 的是**路由选出的那个 provider**，于是「A 收到了一个本该被映射走的名字」成为可能。

---

### F-05 `major` — §4.1 拿上游真名去跑路由规则，却没说列出来的是候选名还是解析后的名字，也没说怎么去重

**位置**：§4.1，原句：「1. 取所有 provider 的 `available_ids` 并集作候选；2. 对每个候选跑一遍 §2 的路由规则，算出它实际会去哪个 provider；3. 那个 provider 确实服务它，才列出；`owned_by` 填算出来的 provider 名」。

**问题**：候选是**上游真名**，而 §2 的路由规则的入口是**请求名**。一个上游真名完全可以是某个 mapping 条目的键，于是「跑一遍路由规则」会把它改写成**另一个模型**。这时第 3 步的「确实服务**它**」指的是候选还是改写后的名字？「列出」列的又是哪个名字？三种做法都说得通，客户端看到的目录完全不同：

- 列候选名（诚实：客户端发这个名字确实能用，但 `owned_by` 说的是另一个模型的归属）；
- 列改写后的名字（会产生重复项，且丢掉了一个可用名字）；
- 只列「解析到自己」的候选（会漏掉一批可用名字）。

**具体输入**：随包默认配置有 `claude-haiku-4.5: gpt-5.6-luna`（`config.example.yaml:125` 那行被注释掉的 `# haiku: claude-haiku-4.5` 说明 `claude-haiku-4.5` 是一个真实目录 id，否则不需要为它写重定向）。于是候选 `claude-haiku-4.5` 跑完路由规则得到模型 `gpt-5.6-luna`、provider=default。`/v1/models` 该列 `claude-haiku-4.5`、还是列 `gpt-5.6-luna`（与它自己作为候选时重复）？Spec 答不了。同样的输入还有随包的 `gpt-5.5: gpt-5.6-terra`、`claude-opus-4.5: claude-opus-5`。

**第二个问题（集合与目标不一致）**：§4.1 声称改成「报**路由可达集合**」，但候选集不含 mapping 键，于是**客户端真正该发的那些名字一个都不在里面**。用 §4.2 自己的示例配置对照：`claude-opus-4.8: A/claude-opus-5`、default=B。候选并集里有 `claude-opus-5`，它跑路由规则落到 B（无条目），于是列出 `claude-opus-5 / owned_by=B`；而 A 提供的那份 `claude-opus-5` 只能通过别名 `claude-opus-4.8` 到达，`claude-opus-4.8` 不是候选、不会被列出。**结果是：A 承接的模型在 `/v1/models` 里完全不可见，而 `owned_by` 恰好把它说成 B 的。** §4.1 说「`owned_by` 由此第一次有真实含义」，在这个例子里它给出的是一个误导性的含义。

**第三个问题（与 §4.2 的集合口径不一致）**：§4.2 的 `routes` 收「mapping 键 ∪ available_ids」，§4.1 只收 `available_ids`。两个端点对「有哪些名字可用」给出不同答案，Spec 没有说明为什么口径不同。

---

### F-06 `major` — §4.2 的 `serviceable` 一个布尔装三类事实，唯一的 `detail` 例句对其中一类是错的；`providers[].catalog` 的取值域未定义，且示例自相矛盾

**位置**：§4.2，原句：「`serviceable` 补上 §5.1 裁掉的两类启动校验（模型不在目录、被 `disabled_models` 禁用），形式是「随时可查」而非「启动时打日志」」；示例 JSON 中的 `"serviceable": false, "detail": "not in A's catalog"` 与 `"B": {"models": 26, "disabled": 24, …, "catalog": "empty", "catalog_refreshed_at": null}`。

**问题一（两个事实一个槽）**：`available_ids` 的契约已经把被禁用的模型排除在外（`model_provider/base.py:26`：「A disabled model is not on offer」）。所以「不在 `available_ids`」这一个判断同时意味着「上游根本没有这个模型」和「你自己在 `disabled_models` 里禁了它」——而这两件事的运维动作完全相反（等上游 / 改自己的配置）。Spec 说 `serviceable` 要「补上**两类**」校验，却只给了一个布尔加一个自由文本 `detail`，而给出的唯一 `detail` 例句 `"not in A's catalog"` 对被禁用的那一类**是错的**：它在目录里，是你禁的。`detail` 的取值词表、是否必填、`serviceable: true` 时是否出现，都没有定义。

**问题二（第三类事实也落进同一格）**：provider 的目录尚未加载（`catalog: "empty"`）时，指向它的**每一行**都会 `serviceable: false`，`detail` 仍然是「不在目录里」——这句话此刻既不是「上游没有」也不是「你禁了」，而是「还不知道」。

**具体输入**：`config.example.yaml` 的 `disabled_models` 列了 30 余个真实 id。运维在 provider A 上禁用 `gpt-5.6-terra`，同时写了 `gpt-5.5: A/gpt-5.6-terra`。`/api/status` 该行显示 `serviceable: false`，`detail` 按示例的写法会说「not in A's catalog」——运维照着去查 A 的目录，会发现它明明在。

**问题三（示例自相矛盾）**：示例里 B 是 `default_model_provider`，其条目为 `"models": 26, "disabled": 24, "catalog": "empty", "catalog_refreshed_at": null`；而下面三行路由到 B 的记录全是 `"serviceable": true`。若 B 的目录是空的、且从未刷新过（`refreshed_at: null`），那 26 个 `models` 是从哪儿数出来的、那三行凭什么 serviceable？`catalog` 字段的取值域（是不是 `ok` / `empty` 的二值枚举？有没有 `error` / `stale`？）与 `models` 的口径（是可用数还是目录总数？与 `disabled` 是相加还是包含关系？）都未定义。

**这条为什么比一般的字段定义问题重**：§6.1 与 §6.2 两个「已知缺口」的**唯一缓解手段**都被指定为 §4.2 的这个端点（「缓解手段是 §4.2 的 `routes` 全集」「同样靠 §4.2 的 `routes` 全集缓解」）。缓解手段的字段语义不成立，等于两个已知缺口的可接受性依据也跟着松动。

---

### F-07 `major` — `origin: "fallback"` 而 `fallback_model_provider` 未配置时，§4.2 那一行没有 `provider` 可填

**位置**：§4.2 的 `routes` 结构（每行必有 `"provider"` 字段）；§1.2「`fallback_model_provider` **可以不配**」；§5.1「以 WARN 形式报出涉及的 mapping 键，**不阻塞启动**」；§5.3「走到 §2.2 规则 2、而 `fallback_model_provider` 未配置时，**该请求报错**」。

**问题**：这四条合起来允许一个**能正常启动、正常运行**的配置，其中存在若干条目走到规则 2 而无 fallback 可去。`/api/status` 必须为这些条目渲染一行，而这一行同时要成立两件事：`origin` 是 `fallback`（限定出现过、但认不出），以及**根本没有 provider**。结构里只有一个字符串槽。实现者必须自己发明：填 `null`？填空串？填 `default` 的名字（那就撒谎了）？还是干脆不渲染这一行（那就把最需要看见的一类藏起来了）？

**具体输入**：不配 `fallback_model_provider`，写 `claude-opus-4.8: Aa/claude-opus-5`（provider 实际叫 `A`，多打了一个字母）。启动：§5.1 WARN 一行，服务照常起来。`GET /api/status` 必须渲染 `"claude-opus-4.8": {"provider": ???, "model": "claude-opus-5", "origin": "fallback", "serviceable": ???}`。`serviceable` 同样无法计算——没有 provider 就没有目录可查，而它是个布尔，`false` 会被读成「模型不存在」，`true` 是错的。

这正是 §1.2 自己立下的标准（「「没写」和「写错了」是两件事，各占一个槽」）在渲染层没有被贯彻的地方。

---

### F-08 `major` — §11 的候选材料义务只落实了一处；`config.example.yaml` 里被本 Spec 取代或扩展的三处未列出

**位置**：§11，原句：「`docs/.human-controlled/` 下的文件（`config.example.yaml`、`api.md`）**一律不由本任务修改**。需要它们改动的地方写成候选材料放 `.dev/human-controlled-docs-candidates/`，等用户摘取。」§1.3 是全文唯一一处指名了具体行（`config.example.yaml:71`）的地方。

**问题**：本 Spec 至少还改变或扩展了该文件的三处叙述，一处都没有被点名为需要候选材料。这不是文档洁癖——那份文件是用户亲笔、是 `model_mappings` 语义的最终权威，改动落地后它会继续被引用，而它描述的算法已经不是代码在做的事。

1. **`config.example.yaml:100-102`**（用户亲笔的解析算法）：「若目标在可用模型列表中，直接解析命中；否则，当作别名再次尝试解析；仍不可用则放弃映射、直接透传（上游随后拒绝它）。」——§2.1 的 discovery pass「**全程不查 `available`**」与 §9.2 记录的用户选择「沿链走、不看 available」正面取代了这段话的第一句。Spec 没有在任何地方声明这一取代，也没有把它列进候选材料。**这同时是 F-02 的另一半**：一份文档说逐跳查目录，另一份说全程不查，两份都在生效。
2. **`config.example.yaml:74-78`**（「模型名映射：请求模型 → 目标模型」「这是模型名映射的唯一来源」）：§1.1 让**值**多承担一个 provider 限定，该段的「目标模型」不再准确。§9.1 自己承认过这个张力（「让它同时承担改名和去向会让一个键坏掉两个语义」），但那是作为被否决方案的理由记的，没有转成文档同步项。
3. **新增顶层键 `fallback_model_provider`**（§1.2）：`config.example.yaml` 是带注释的完整配置样例，新增的顶层键不在里面，运维无从知道它存在，而 §5.3 让它成为一整类请求能不能工作的开关。

另外 `docs/.human-controlled/request-pipeline.md:11` 用 `claude-sonnet-5 -> gpt-5.6-terra@openai-responses` 描述映射关系，与本 Spec 的值语法（`provider/model`）是两套写法，是否需要候选材料对齐，Spec 也没有表态（另见 F-14）。

---

### F-09 `major` — §10.1 的验收清单漏掉 §3 全部内容与另外三条规范条款，而 §10.2 只声明了 §8.1 未验证

**位置**：§10.1 的四条清单；§10.2「未验证事项」只列了 §8.1 的凭据与连接池隔离。

**问题**：Spec 把「已验证」与「显式声明未验证」两类之外的东西留成了空白，而空白里躺着 §3——一条用户裁决的、对外可见的请求语法，且它自带一个 Spec 自己都强调「**必须钉死**」的解析顺序（`@` 与 `/`）。清单里没有它，`未验证事项`里也没有它。§10.2 的最后一段反而顺口提到「能覆盖除凭据隔离外的一切（路由、`/api/status`、**请求侧 `A/model` 语法**）」，把请求侧语法归进了「真要验证时的手段」——那等于承认它现在没被验证，却没写进 §10.2 的正文。

**清单没有覆盖到的规范条款**：

- §3 全部（请求侧前缀、`@` 与 `/` 的顺序、请求侧命中后的别名解析——也就是 F-01 的那一片）；
- §2.4 的 passthrough 行为（`resolved` 保持原始请求名）；
- §5.2 的 `UnknownModel` 消息内容（这是一条「必须带上链末模型名」的可测断言）；
- §4.1 的「候选跑一遍路由规则」（F-05 指出它的语义未定，验收本可以逼出这个问题）；
- 跳数上限耗尽的行为（F-03）。

**具体输入角度**：`A/claude-opus-5@anthropic-messages` 这个 Spec 亲自举出的例子，在整份验收里没有对应项。而它是最容易实现反的一处——把两个 `partition` 写反顺序、或者对 `@` 用 `partition` 而非 `rpartition`，单元测试不覆盖就没人会发现。

---

### F-10 `minor` — §3 的交叉引用指错了小节

**位置**：§3「已知代价三项」第 1 条，原句：「`/v1/models` 不会列出 `A/claude-opus-5` 这种形式（§4.1 的 `routes` 键是裸名）」。

**问题**：`routes` 是 §4.2 的字段，§4.1 通篇没有 `routes` 这个键。而且即便改指 §4.2，那里的 `routes` 键集合是「mapping 键 ∪ available_ids」，与 §4.1 的候选集不是同一个东西——结论（`A/model` 形式不会出现在目录里）是对的，指路是错的。Spec 的交叉引用是承重的（§2.2 指 §4.2、§4.2 指 §2.2、§6.1 指 §4.2、§5.2 指 §2.4），错一处会让读者顺着去读一个不存在的定义。

---

### F-11 `minor` — §4.2 的「去重、别名优先」没有定义等价类，而这套规则下「别名优先」本身是描述性的、没有可观察效果

**位置**：§4.2，原句：「`routes` 的键收 **「所有 mapping 键 ∪ 所有 provider 的 available_ids」**，去重，别名优先（因为解析就是这个顺序）。」

**问题一**：去重按字面串还是按 `canonical()`？这不是理论问题：`config.example.yaml` 用点写法（`claude-opus-4.5`），而入站与目录用杠写法（该文件 82-84 行自己举的例子就是「入站 `claude-opus-4-5` 命中 `claude-opus-4.5`」）。若按字面去重，`/api/status` 会出现 `claude-opus-4.5` 与 `claude-opus-4-5` 两行、路由结果完全相同；若按 canonical 去重，就得再规定保留哪个拼写——而这才是「别名优先」可能想说的事，Spec 没这么说。

**问题二**：在新规则下，任何一个入站名的路由结果都只由 §2 决定，与它「来自哪个集合」无关（链走完之前永远先查表，不查目录）。所以「别名优先」在计算层面是个空转的限定——它要么是在复述解析顺序（那就不该写成集合构造规则），要么是在指拼写取舍（那就没写清）。实现者只能猜作者指的是哪一个。

---

### F-12 `minor` — §2.2 的「provider 的来源恰好三种，没有第四种」在 §3 存在之后不成立

**位置**：§2.2，原句：「附带的好处是 provider 的来源被收敛成恰好三种（`qualified`、`fallback`、`default`），没有第四种，`/api/status` 的 `origin` 字段（§4.2）因此是一个闭集。」

**问题**：系统里 provider 的来源有第四种——§3 的请求侧显式指定。闭集只对 §4.2 那个**只渲染配置侧**的字段成立，不对系统成立。这句绝对表述会误导两类读者：一类会以为 `origin` 可以直接用来解释任意一次真实请求的去向（不能，请求侧指定不产生任何 `origin`）；另一类在将来给日志或 history 加 provider 归因时，会照抄这个三值闭集，然后发现请求侧的那一类无处安放。建议把范围限定语补上（「就配置侧解析而言」）。

---

### F-13 `minor` — §3 没有限定作用面；在模型名位于 URL 路径的两个端点上，`A/model` 写法无法成立

**位置**：§3，原句只给了 `POST /v1/messages  {"model": "A/claude-opus-5"}` 一个例子，没有说这个语法适用于哪些入站端点。

**问题**：`docs/.human-controlled/api.md` 列出的端点里，至少两个把模型名放在 URL 路径段上：Gemini 的 `POST /v1beta/models/{model}:{generateContent|…}` 与 Azure 的 `POST /openai/deployments/{deployment}/…`。在这两个位置上写 `A/claude-opus-5` 会改变 URL 的分段结构，路由匹配根本到不了 handler。所以 §3 的语法在这两个面上要么不可用、要么需要另一种表达（查询参数、请求头），Spec 没有表态。实现者会遇到一个明确的分叉：把前缀剥离做在共用的路由层（那么 body 里带模型名的端点全部自动获得该语法，路径参数端点自动没有），还是逐 handler 做。两种做法的对外行为不同。

**具体输入**：`POST /v1beta/models/A/claude-opus-5:generateContent`——这个 URL 不会命中 `/v1beta/models/{model}:{method}` 的路由，客户端拿到 404，而 Spec 让人以为这个语法是全局的。

---

### F-14 `minor` — 值侧的 `@format` 没有规则；§3 只钉了请求侧的顺序

**位置**：§3，原句：「**与 `@format` 后缀的解析顺序必须钉死**：先 `rpartition("@")` 剥 wire format（现有 `split_format_suffix`），再 `partition("/")` 剥 provider 前缀。」§2.1 的 `qualify` 对 `@` 只字未提。

**问题**：Spec 为请求侧钉死了顺序，却没说 mapping 的**值**里出现 `@format` 时怎么办。按 §2.1 的字面，`x: A/gpt-5.6-terra@openai-responses` 会得到模型名 `gpt-5.6-terra@openai-responses`，`canonical()` 之后当然查不到目录，走 passthrough 报错——一个看起来很自然的写法安静地失效。

**这是「要不要支持」而不是「已支持却漏写」**：我核过，`split_format_suffix` 只作用于入站的 `requested_model`（`routing.py:90`），`src/` 与 `tests/` 里没有任何一个 mapping 值带 `@`。但用户亲笔的 `docs/.human-controlled/request-pipeline.md:11` 恰恰用 `claude-sonnet-5 -> gpt-5.6-terra@openai-responses` 这种写法描述映射关系，所以运维照着写出来的概率不低。Spec 至少应该有一句「值不支持 `@format`」，否则读者会从 §3 的「必须钉死顺序」反推出值侧也支持。

---

### F-15 `minor` — 空模型名部分（`A/`、`x: ""`）规则上有确定答案，但会一路带着空串走到错误消息和 `/api/status`

**位置**：§2.1 的 `qualify` 定义；§5.1「只校验「限定的 provider 名不在 `model_providers` 里」」。

**问题**：`qualify` 是个全函数，这几个输入都有确定答案，**不是覆盖漏洞**，但产物是空串：

- `x: A/` → 规则 1 终点，provider=A，模型名 `""` → §2.4 目录必然不命中 → passthrough → `UnknownModel`，而 §5.2 要求消息里带「链末模型名」，那是一个空串；§4.2 会渲染 `"model": ""`。
- `x: ""`（YAML 里写 `x: ""`，schema 是 `dict[str, str]`，能通过校验）→ 不含斜杠 → 规则 3 别名继续跳 → 空串查不到任何条目 → 规则 4 → default，模型名 `""`，同上。
- `x: /claude-opus-5` → 头段是空串，不是任何 provider 名 → 规则 2 → fallback。这个行为是对的（少打一个 provider 名就是配错了），值得在 §2.1 或 §5.1 明说一句，否则读者会以为「以斜杠开头」是未定义。

§5.1 的静态校验此刻只看 provider 名认不认得，`A/` 的 A 认得，于是全部放行。「限定的模型名部分为空」是一个纯静态、零成本、必然是配置错误的判断，与 §5.1 已经在做的那一类同源（不看目录、配置加载完成即可判），把它一并 WARN 是自然的补法。

---

### F-16 `minor` — §4.2 的 `ready` 字段与 §4.3 的就绪判据没有绑定，而 Spec 自己引用过「做成两个会漂移」的担忧

**位置**：§4.2 的示例首字段 `"ready": true`；§4.3「就绪判据改为「`default_model_provider` 有目录」」；§4.2 引用的 `ops.py:36`「两者回答同一个问题，做成两个会漂移」。

**问题**：Spec 论证了拆分 handler 是安全的（论据扎实：docker-compose 打的是 `/health/liveness`、`admission.py:22` 的 `UNGATED_PATHS` 只收了 `/health/readiness`），但拆完之后 `/api/status` 仍然保留一个 `ready` 字段，Spec 没有说它必须由 §4.3 的同一个判据函数产出。这恰好是被引用的那句担忧所指的漂移形态：同一个语义，两处各算一遍。补一句「`ready` 与 `/health/readiness` 共用同一个判据函数」即可闭合。

---

### F-17 `minor` — §4.2 全集 `routes` 的理由被稀释：随包配置里十几条别名与「新模型静默落 default」同形

**位置**：§4.2，原句：「上游新上线 `claude-opus-6`，没人给它写条目，它静默落 default；全集会把它明白列成 `{"provider": "B", "origin": "default"}`，运维扫一眼 `origin` 就能发现有个 claude 落在 B 上。」

**问题**：随包默认配置里 `fable`、`opus`、`sonnet`、`gpt`、`haiku` 以及四条日期后缀条目，只要它们的目标没被写成限定形式，`origin` 全是 `default`。多 provider 部署按 §6.2 会把常用的那些改成限定，但没改到的、以及所有 default provider 自己的目录 id（它们全部无条目 → 全部 `origin: default`），仍然是几十行 `default`。新上线的 `claude-opus-6` 在这几十行里与它们逐字同形，「扫一眼 `origin` 就能发现」这个说法比实际能做到的强。

这条不否定「收全集」这个用户裁决（全集确实让那一行**存在**，比不存在强得多），否定的是那句关于**可发现性**的推导。真要让它可扫，需要的是一个能区分「default 是因为没有条目」与「default 是因为条目链走完没有限定」的信号——也就是 F-03 的第二问题所指的那一格。

---

### F-18 `minor` — §2.4 说 passthrough 返回「原始请求名」，在 §3 路径上没说是剥前缀之前还是之后的那个

**位置**：§2.4，原句：「**passthrough 时 `ModelResolution.resolved` 仍返回原始请求名**（`requested.strip()`）」；§3「请求侧指定命中后……模型名部分仍需经过现有的 `model_mappings` 别名解析与 §2.4 的目录查询」。

**问题**：请求 `A/opus` 走到 passthrough 时，`resolved` 是 `"A/opus"` 还是 `"opus"`？这决定错误消息、日志行、以及 `describe()` 拿去查的字符串。两者都说得通（前者更「原始」，后者才是模型名）。Spec 没说。这是 F-01 的连带项，修 F-01 时一并定义即可。

---

### F-19 `minor` — §4.3 只记了 fallback 挂掉这一个已知代价，反方向的代价（default 挂掉但流量全走限定）没记

**位置**：§4.3，原句：「**已知代价**：`fallback_model_provider` 挂了不影响就绪判定……」；就绪判据「`default_model_provider` 有目录」。

**问题**：§4.3 用「`any` 会谎报」的论证换到「只看 default」，并记下了 fallback 方向的代价，但没记对称的那一侧：按 §6.2 推荐的写法，一个把常用模型全部限定到 A 的部署，其真实流量可以 100% 不经过 default provider B；B 的 token 过期时，实例会被判为 not-ready 退出轮转，而它此刻能正常服务全部实际流量。这是「谎报不可用」，与 §4.3 要消灭的「谎报可用」是同一枚硬币的两面。

§6.1 的存在让 B 永远不是纯摆设（任何没有条目的名字都落 B），所以这个代价是**可接受**的——但它是一条已知代价，§4.3 是一个显式列已知代价的小节，缺了它会让读者以为这个方向不存在。

---

## 主观建议（不占严重度档位）

- **S-1**：§5.1 的 WARN 目前只说「涉及的 mapping 键」。启动时已经能同时知道「`fallback_model_provider` 配没配」，于是这条 WARN 可以区分两种未来：「这些键会走 fallback 到 X」与「这些键的请求必然报错，因为没有 fallback」。用户裁掉的是**启动失败**这个方向，不是「WARN 里说清楚」。预期影响：配错 provider 名且没配 fallback 的部署，能在第一个请求到来之前就知道自己坏了。
- **S-2**：§4.1 与 §4.2 各自都要判断「这个 provider 现在能不能服务这个模型」（前者是第 3 步，后者是 `serviceable`）。Spec 应该指定其中一处为权威定义、另一处引用它，否则两个端点会各自演化出一套判断。预期影响：消掉一个「同一事实在两条交付路径各推导一遍」的漂移点。
- **S-3**：§2.2 的四条规则目前以表格形式给出，`model_name` 的传递是隐含的。给规则表加一列「带出的 model_name」，F-03 的问题一会自动闭合，读者也不必从 §2.4 的入参倒推。

---

## 我查过但认为没问题的

以下每一条我都对着具体输入推演过，结论是无歧义、且与 Spec 其它条款自洽。

1. **`qualify` 是全函数**。对任意字符串都有确定答案：不含 `/` → 未限定；含 `/` → 按第一个斜杠切分，头段认得／认不出两路。`""`、`"/"`、`"/m"`、`"A/"`、`"a/b/c"` 全部落在既有分支里，没有输入掉出定义域。（`"A/"` 与 `""` 的**产物**有问题，见 F-15，但那不是覆盖漏洞。）
2. **§2.2 四条规则互斥且穷尽**。规则 1/2/3 按「值含不含斜杠 × 头段认不认得」三分，规则 4 的前提是「没有值可读」（无条目命中或跳数耗尽），与前三条的前提不相交。不存在两条同时适用而需要定优先级的输入。（唯一的优先级冲突在 §2 与 §3 之间，见 F-01。）
3. **`origin` 三值在配置侧确实互斥**。任何一条链上至多一个成立：限定值一读到就终止，所以「全程没出现过限定」与 `origin=default` 是等价的，§1.2 的表与 §2.2 的规则表对得上。（越界的绝对表述见 F-12；`default` 内部混装多个事实见 F-03。）
4. **provider 名精确匹配 + 「剥离必须在 `canonical()` 之前」是自洽的**。输入 `x: GHC/claude-opus-5` 而 provider 实际叫 `ghc`：不会因为大小写等价而静默命中，落规则 2 走 fallback，且 §5.1 会在启动时 WARN。这一组三条规则（精确匹配、剥离顺序、启动 WARN）互相支撑，没有缝。
5. **`partition` 而非 `rpartition` 与 §6.3 一致**。`A/a/b` → provider=A、模型 `a/b`；`zzz/a/b` → fallback、模型 `a/b`。tail 保留斜杠这件事在 §2.1 说了、在 §6.3 承认了后果，两处一致。
6. **§2.2 规则 2「仍是终点」的理由成立**。我按 Spec 给的反例构造了 `x: a/claude-opus-5` 加 `claude-opus-5: B/claude-opus-5`：若把剔除后的值降级为别名继续跳，确实会读到第二条的限定、把请求送到 B，且不报错不走 fallback。保持终点身份确实堵死了这条路。这条最不直观的规则，理由是硬的。
7. **§6.1 的自映射写法不产生自环**。`claude-opus-5: A/claude-opus-5` 的值带限定 → 规则 1 → 一读到就终止，不会再拿 `claude-opus-5` 回表。§9.2 关于「自环被消解」的论证对**自映射**成立。（对互指环不成立，见 F-03。）
8. **§4.2 示例 JSON 的四行 `routes` 与 §2 的规则逐条对得上**（在随包 `opus: claude-opus-5`、且 `claude-opus-5` 无条目的前提下）：`claude-opus-4.8` → 规则 1 → A/qualified ✓；`opus` → 规则 3 跳一次 → 规则 4 → B/default，模型 `claude-opus-5` ✓；`claude-opus-5` → 无条目 → 规则 4 → B/default ✓；`x` → 规则 2 → fallback=A、模型 `opus-alias`、A 目录没有 → `serviceable: false` ✓，且与 §2.3 的「已知代价」段落举的例子一致。示例本身在**路由**这一维上是正确的。（同一段示例在 `catalog` 维上自相矛盾，见 F-06。）
9. **§2.4 的目录查询口径与现有实现一致**：只做 `canonical()`，不做 bracket（`[1m]`）展开、不再回 `model_mappings` 查下一跳。这与 §2.3 的终点语义一致，也与现有 `available_index.get(canonical(current))` 的做法一致。终点模型名不再享受别名待遇是设计意图，不是遗漏。
10. **§3 的 `@` 与 `/` 顺序确实唯一可解**。`A/claude-opus-5@anthropic-messages`：`rpartition("@")` 取尾、`partition("/")` 取头，两个分隔符一头一尾，且 `split_format_suffix` 对「`@` 前为空」已有兜底。Spec 说的「互不干扰」成立。（它没有被任何验收项覆盖，见 F-09。）
11. **§5.3 与 §1.2 自洽**：fallback 可不配 → 走到规则 2 的请求报错、而不是落 default。错误在任何网络请求之前抛出，与 `RoutingError` 的既有定位（`routing.py:41` 的 docstring）一致，且明确把错误信封的渲染交给 `error-envelope/spec.md`，没有在这里重复定义一套映射——这是正确的权威归属。
12. **§10.1 判定「mock 为主、不需要新录 cassette」是对的**。这次的判据（解析规则、配置校验、两个端点的渲染）确实不依赖上游真实行为，换个上游照样成立。§10.2 又显式把 §8.1 的凭据／连接池隔离标成「只有代码结构上的保证，没有运行证据」，并写明「以免后来者从「测试全绿」读出它已被验证过」——这一句是本文档质量最高的地方之一，它主动声明了一个绿灯**不能**证明什么。（清单本身有覆盖缺口，见 F-09；这一条评的是判定方法与声明纪律。）
13. **§1.3 的改名不会与 provider 名冲突**。`CountTokensProvider` 与 `model_providers` 的键在两个命名空间里，随包配置的 provider 恰好叫 `ghc` 不构成歧义；且 `bundled-config.yaml` 没有显式写 `inbound.anthropic_count_tokens.providers`，走 schema 默认值，所以随包默认配置在改名后仍能启动——Spec 只点名了 `config.example.yaml:71` 会被挡下，这个范围判断是准的（我核过 bundled 文件，没有第二处）。
14. **mapping 的键含斜杠这类输入**（例如 `A/opus: claude-opus-5`）：这个键在 A 是已配置 provider 时永远不会被命中（请求侧会先剥掉前缀）。但这与 §6.3 已经认领的缺口是同一枚硬币（含斜杠的名字在配置侧和请求侧都会被剥），Spec 已声明并给了逃生舱（结构化值写法），不另开条目。
15. **权威归属抽查**：Spec 逐条标注了「用户裁决」与「本次推导」，§0 明确了两者的修订权限差异。我抽查了标注密度最高的 §2.2——四条规则的裁决归属被拆成「规则 1、3、4 是用户裁决」「规则 2 是用户裁决」并附了用户原话的转述，其中「仍是终点」这一句还单独声明了「是单独裁决过的」。这个粒度足以让后来者知道哪里能改、哪里要问。**我无法核验这些转述是否逐字忠于用户原话**（历史对话不可访问），按 `unverified` 记；但标注结构本身是合规的，没有出现「把推导整条归给用户」的形状。

---

## 我考虑过但排除的怀疑方向

1. **怀疑 `origin` 需要第四个值来表达「请求侧指定」。** 查 §4.2：`routes` 只渲染配置侧解析，请求侧指定不会进入这个字段，所以就该字段而言闭集成立，不需要第四个值。越界的只有 §2.2 那句系统级的绝对表述 → 降级为 F-12，不作为字段设计缺陷。
2. **怀疑 discovery pass 与后续解析各吃一份 8 跳预算，导致总跳数翻倍或链被截断两次。** 只在 F-02 的读法 B 下成立；读法 A 下只有一次遍历。这是 F-02 的下游后果，不单列。
3. **怀疑 `model_thinking_effort`（`schema.py:389` 明确 keyed on resolved id）会因本次解析顺序变化而错位。** 确实会——但它同样是 F-02 的下游后果，已并入 F-02 的「连带后果」，不单列为新发现。
4. **怀疑 §4.1 的候选并集会把 `disabled_models` 禁掉的模型带进 `/v1/models`。** 查 `model_provider/base.py:26` 的契约：「A disabled model is not on offer, so callers cannot route to it by accident」——`available_ids` 已排除 disabled。不成立。（但同一个事实反过来造成了 F-06 的「两个事实一个槽」。）
5. **怀疑 mapping 的值已经支持 `@format`，因而 §2.1 是漏写。** 查 `routing.py:90`：`split_format_suffix` 只作用于入站的 `requested_model`；`src/` 与 `tests/` 里没有任何 mapping 值带 `@`（两次 rg 均无命中）。所以这是「要不要支持」的开放问题，不是「已支持却漏写」→ 按 F-14 的措辞落笔，避免把一个未定的功能说成已存在的契约。
6. **怀疑 §5.1「校验点落在配置加载完成那一刻」会漏掉配置热重载后的新配置。** 我没有找到任何声称支持配置热重载的条款（`model_refresh_interval` 刷的是**目录**不是配置，§5.1 也正是拿它作对比），所以「重载后不再校验」这个问题在本 Spec 的世界里不存在。不作为发现。
7. **怀疑 §8.2 的三张全局表在多 provider 下会答错。** §8.2 已写明失效条件（企业版 base_url）与迁移路径，并论证了它与 `models_support_web_search` 不一致是有理由的。这是 provider 行为归属问题，不是规则完备性问题，本轮不计。
8. **怀疑 §1.2（fallback 名字不存在 → 启动失败）与 §5.1（值里的 provider 名不存在 → 只 WARN）自相矛盾。** 两者处理的不是同一件事：顶层键是运维对 provider 的直接指名，映射值的头段按设计本来就有 fallback 这条补救道。§1.2 的类比对象是 `default_model_provider`（同为顶层键），类比成立。不构成矛盾。
9. **怀疑 §4.1「那个 provider 确实服务它，才列出」在 default provider 目录为空时会把整个 `/v1/models` 清空。** 会——但那正是 §4.3 判定 not-ready 的同一个状态，语义一致（此时实例本就不该接流量），不是新增缺陷。
10. **怀疑 §2.4 的 passthrough 在多 provider 下会把名字发给错误的 provider。** 会走到 `describe()` 的是路由选出的那个 provider，行为是定义好的；真正的问题是 §2.4 声称这条路必然抛错 → 已按 F-04 落笔，不重复计一条。

---
report_id: impl-verify-multi-provider-routing
attempt_id: 0e3de57b-impl-verify-01
status: draft
reviewed_at_rev: bb1c5f5
spec_path: /home/xp/src/ghc-api-proxy-py/.dev/docs/multi-provider-routing/spec.md
spec_sha256: a697e4a8a0cf3f676b3c3e283f8c147de6eb326ca8aab50cc8d39332bca09636
matrix_freeze_evidence: written before the first implementation or test read in the session transcript
---

# 多 model provider 路由独立验收

## 范围与方法

本报告只判断提交 `bb1c5f5` 的用户可观察行为是否符合当前 Spec。验收矩阵在读取 Plan、`src/` 与既有测试之前，仅从 Spec 独立推导并冻结。冻结后允许补记由 Spec 反向扫描发现的漏项，不因实现形状改写既有判据。

证据权重约定：真实入口或直接调用公开业务入口并观察输出的结果，足以对对应判据作通过或偏差判断；只读源码所得结构事实只足以定位或划定盲区，不冒充运行证据；未经真实双账号或真实连接故障注入的连接池与凭据隔离只能标为未验证。

## 冻结验收矩阵

| ID | Spec | 独立判据 | Oracle 与预期观察 | 结论 |
|---|---|---|---|---|
| CFG-01 | §1.1、§2.1 | mapping 值 `A/target` 将 provider 限定为精确配置键 `A`，并带出 `target`。 | 构造双 provider 配置并解析该键；观察 provider=`A`、model=`target`。 | 通过 |
| CFG-02 | §2.1 | 限定只按第一个 `/` 分割，模型名余下的斜杠原样保留。 | 解析 mapping 值 `A/vendor/model`；观察 provider=`A`、model=`vendor/model`。 | 通过 |
| CFG-03 | §2.1 | provider 名精确匹配，不做大小写折叠，也不把 `.` 与 `-` 等价；模型名的 canonical 规则仍保持。 | 配置 provider `A.One`，分别打 `A.One/model`、`a-one/model`；前者走 A，后者被视为未知限定并走 fallback。 | 通过 |
| CFG-04 | §1.2、§5.3 | `fallback_model_provider` 可省略；省略本身不阻止启动，但真正命中未知限定的请求报错且不落 default。 | 启动无 fallback 的有效配置，再解析 `typo/model`；启动成功，解析在任何 upstream 请求前失败。 | 通过 |
| CFG-05 | §1.2 | fallback 配成不存在的 provider 时启动失败。 | 加载 `fallback_model_provider: missing`；观察 `ProviderNotConfigured` 类配置失败。 | 通过 |
| CFG-06 | §1.3 | count-tokens provider 的合法值与默认值改为 `upstream`、`local`；显式旧值 `ghc` 启动失败，并直说已更名为 `upstream`。 | 分别加载默认配置、显式 `[upstream, local]`、显式 `[ghc, local]`；前两者成功，最后一者失败且消息包含两个名称与更名关系。 | 通过 |
| CFG-07 | §2.1 | mapping 值不解析 `@format`；`A/model@fmt` 的模型名就是 `model@fmt`。 | 解析该 mapping；观察 format 不被剥离，目录只含 `model` 时目标不命中。 | 通过 |
| CFG-08 | §2.1、§5.1.2 | provider 名不得含 `/`，且空 head 不是合法 provider 名；配置层不能接受一个语法上无法被限定引用的 provider 键。 | 分别加载 provider 键 `A/B` 与空串；预期在启动前拒绝。若接受，再打 `A/B/target` 与 `/target`，不得出现“配置已接受但请求语法无法表达”或把空 head 识别成 provider 的状态。 | 偏差 |
| ROUTE-01 | §2.2 规则 1、§2.3 | 已知 provider 限定是 provider 与模型名共同的终点，后续同名 mapping 不再被读。 | 配 `x: A/y`、`y: B/z`；请求 `x` 必须停在 A/y，不得去 B/z。 | 通过 |
| ROUTE-02 | §2.2 规则 2 | 未知 provider 限定仍是终点；剔除前缀后不得把模型名重新当 alias 跳转。 | 使用 Spec 反例：`x: a/target`、`target: B/other`、fallback=A；请求 `x` 必须去 A/target，不得去 B/other。 | 通过 |
| ROUTE-03 | §2.2 规则 3 | 不带 `/` 的值不是终点，可连续沿 mapping 链跳。 | 配 `x: y`、`y: z`、`z: A/real`；请求 `x` 得 A/real。 | 通过 |
| ROUTE-04A | §2.2 规则 4a | 无 mapping 命中时以链末名和 default provider 结束。 | 配 `x: y` 且 y 无条目；请求 x 得 default/y。 | 通过 |
| ROUTE-04B | §2.2 规则 4b | 第 8 跳撞上限时，以 default provider 与第 8 跳读到的值结束。 | 构造至少 9 跳且无限定的链；观察 provider=default，model 为第 8 次读取所得值，不继续到第 9 跳。 | 通过 |
| ROUTE-05 | §2.4 | 目标不可用、原始请求名在选中 provider 可用时，映射被放弃，请求以原始名照常发出。 | provider 仅提供 `real-model`，mapping `real-model: missing-target`；走真实路由决策，观察成功且 upstream model=`real-model`、passthrough=True。 | 通过 |
| ROUTE-06 | §2.4、§5.2 | 目标与原始名都不可用时抛 `UnknownModel`。 | provider 目录不含两者；请求 mapping 键，观察请求级错误且 upstream 未被调用。 | 通过 |
| ROUTE-07 | §2.5 | 链中间模型可用、链末不可用时仍走到链末，不就地返回中间模型。 | provider 目录仅含链中间名，原始名不可用；请求链首，观察 `UnknownModel`，不得成功返回中间名。 | 通过 |
| ROUTE-08 | §6.1 | 完全没有 mapping 条目的模型静默走 default。 | 双 provider 都可构造同名目录；请求无条目名，观察选 default。 | 通过 |
| ROUTE-09 | §6.2 | 每个 alias 独立决定去向；一个 alias 的限定不自动作用于另一个 alias。 | 一个 alias 限定 A，另一个 alias 只无条件跳到同一真名；观察前者去 A、后者按自己的链落 default。 | 通过 |
| ROUTE-10 | §2.4 | canonical 命中时 resolved 保留目录原始拼写。 | 请求与目录只在大小写或 `.`/`-` 上等价；观察发往 upstream 的 id 等于目录拼写。 | 通过 |
| REQUEST-01 | §3 | 请求体里的已知 `provider/model` 前缀优先级最高，覆盖配置路由。 | 请求 `A/model`，同时让配置路由把 model 指到 B；观察最终 provider=A。 | 通过 |
| REQUEST-02 | §3 | 请求侧未知 provider 前缀剥除后走 fallback；未配 fallback 时请求报错。 | 打 `typo/model` 两次，分别有无 fallback；前者去 fallback/model，后者请求级失败且不落 default。 | 通过 |
| REQUEST-03 | §3 | 先剥尾部 `@format`，再剥头部 provider。 | 请求 `A/claude-opus-5@anthropic-messages`；观察 format=`anthropic-messages`、provider=A、model=`claude-opus-5`。 | 通过 |
| REQUEST-04 | §3.1 规则 1 | 请求 `A/opus` 仍沿 model mapping 链跳。 | 配 `opus: alias`、`alias: A/target`；观察 A/target，而不是直接查 A/opus。 | 通过 |
| REQUEST-05 | §3.1 规则 2 | 请求侧 provider 压过链上 provider。 | 配 `opus: B/target`；请求 `A/opus` 必须去 A/target，不得去 B。 | 通过 |
| REQUEST-06 | §3.1 规则 3 | 请求侧 provider 已定时，链上未知限定只贡献模型名，fallback 不参与。 | 配 `opus: typo/target`、fallback=B；请求 `A/opus` 必须去 A/target。 | 通过 |
| REQUEST-07 | §3.2 | 请求侧显式 provider 路径进入 passthrough 时，原始回退名是剥前缀后的裸名。 | 请求 `A/opus`，mapping 目标不可用而 A 目录有 `opus`；观察 upstream model=`opus`，错误或日志不得出现 `A/opus` 作为模型名。 | 通过 |
| REQUEST-08 | §3.3 | 所有请求体携带 model 的端点及 `/v1`、`/openai/v1` 变体采用同一前缀语义。 | 对 Messages、count_tokens、chat completions、responses、embeddings 的已注册请求体入口各送 `A/model`；观察 handler 可达并由 A 路由，而非把前缀当模型名。 | 通过 |
| REQUEST-09 | §3.3 | Gemini 与 Azure 的 path-model 端点不支持该语法；斜杠改变 URL 分段并得到 404。 | 对相应真实 URL 路由发送带 `A/` 的 path model；观察 404，而不是悄悄按 provider 前缀解析。 | 通过 |
| MODELS-01 | §4.1 | models 候选集是所有 provider `available_ids` 与所有 mapping 键的 canonical 并集；mapping alias 也可被列出。 | 双 provider 目录加仅存在于 mapping 键的 alias，调用 `/v1/models`；可服务 alias 出现在 id 列表。 | 通过 |
| MODELS-02 | §4.1 | 列表只保留 serviceable=`yes` 的候选，不承诺实际不可服务项。 | 同时构造 yes、absent、disabled、unknown、unroutable 候选；只 yes 出现在 models 目录。 | 通过 |
| MODELS-03 | §4.1 | 返回 id 是客户端候选名，不是解析后的 target。 | alias 路由至不同 target；观察列表 id=alias。 | 通过 |
| MODELS-04 | §4.1 | `owned_by` 是候选实际路由到的 provider。 | 分别构造 A 与 B 可服务候选；观察每行 owned_by 对应 A/B。 | 通过 |
| MODELS-05 | §4.1、§4.2.1 | canonical 去重保留先出现拼写，顺序按已排序目录名后接已排序 mapping 键；目录拼写优先。 | 目录与 mapping 放入 canonical 等价但拼写不同的名称；观察仅一行，保留目录拼写，并核对整体顺序。 | 通过 |
| MODELS-06 | §4.1 | `/models`、`/v1/models`、`/openai/v1/models` 三条入口结果一致。 | 调用三条实际 HTTP 路径并比较结构。 | 通过 |
| STATUS-01 | §4.2 | `/api/status` 与 readiness 分离，HTTP 状态恒 200，即使 default 无目录。 | default 目录为空时调用真实 endpoint；观察 200。 | 通过 |
| STATUS-02 | §4.2、§4.2.1 | routes 键是 available ids 与 mapping 键的 canonical 并集，去重和拼写规则与 models 相同。 | 构造交叉集合和等价拼写；观察键集合、拼写和顺序。 | 通过 |
| STATUS-03 | §4.2.2 | `serviceable=yes` 可达。 | 路由目标在 provider 可用目录；观察 yes。 | 通过 |
| STATUS-04 | §4.2.2 | `serviceable=absent` 可达。 | provider 目录已加载但不含解析目标，且原始候选也不可用；观察 absent。 | 通过 |
| STATUS-05 | §4.2.2 | `serviceable=disabled` 可达。 | 目标存在于原始目录但被该 provider disabled；观察 disabled。 | 通过 |
| STATUS-06 | §4.2.2 | `serviceable=unknown` 可达。 | 目标 provider 的 catalog 非 ok；观察 unknown，而不是 absent。 | 通过 |
| STATUS-07 | §4.2.2 | `serviceable=unroutable` 可达，且该行 `provider` 是 JSON null。 | 未配 fallback 并构造未知限定 mapping；观察 unroutable、provider=null。 | 通过 |
| STATUS-08 | §4.2.4 | 映射目标不可用但原始候选可用时，`model` 报实际会发出的原始名、`intended` 报映射目标、serviceable=yes；两名相同时省略 intended。 | 构造两类 route 行并检查字段存在性和值。 | 通过 |
| STATUS-09 | §4.2.3 | providers 汇总中 models 是扣除 disabled 后的可用数，disabled 只数确实在目录中的禁用项，catalog 由非空性决定，refreshed_at 是最近成功刷新时间或 null。 | 构造含有效禁用项和不存在禁用项的目录快照并读取 status。 | 通过 |
| STATUS-10 | §4.2、§4.3 | status.ready 与 readiness 使用同一 default-catalog 判据。 | default 有目录与无目录各跑一次；观察 ready 布尔与 readiness HTTP 结论一致。 | 通过 |
| STATUS-11 | §4.2.2 | route 行不输出已取消的自由文本 `detail` 字段。 | 覆盖五个 serviceable 值并检查每行字段集合；均不得含 detail。 | 通过 |
| STATUS-12 | §4.2.3 | `/api/status` 每次反映当前 catalog；成功刷新后，serviceable、计数与 `catalog_refreshed_at` 随之变化。 | 同一 provider 先为空、后换入含目标的 catalog 并更新时间，再调用两次 status；观察 unknown→yes 和刷新时间更新。 | 通过 |
| READY-01 | §4.3 | default 有目录时就绪，即使次要 provider 目录为空。 | 调用 `/health/readiness`；观察 200 与 ready。 | 通过 |
| READY-02 | §4.3 | default 无目录时不就绪，即使次要 provider 有目录。 | 调用 `/health/readiness`；观察非 200 与 uninitialized。 | 通过 |
| READY-03 | §4.3 | fallback 无目录不影响 readiness。 | default 有目录、fallback 空；观察 ready。 | 通过 |
| READY-04 | §4.3 | readiness 响应体带 status、default_model_provider、default 可用 models 数。 | 在 ready 与 uninitialized 两态核对三个字段。 | 通过 |
| READY-05 | §4.3 | readiness/liveness/metrics 保持在准入闸门外，重量级 `/api/status` 仍受闸门约束。 | 用一个占满唯一 slot 的请求制造饱和；readiness 必须立即返回，而 `/api/status` 必须等 slot 释放。 | 通过 |
| WARN-01 | §5.1、§5.1.1 | 未知限定 provider 的 mapping 键在配置加载完成时触发 WARN，不阻止启动；配 fallback 时 WARN 直说会去哪个 fallback。 | 捕获配置启动日志；核对 level、相关键与 fallback 名。 | 偏差 |
| WARN-02 | §5.1、§5.1.1 | 未配 fallback 时同类 WARN 直说相关请求必然报错。 | 捕获日志；核对相关键及必然失败语义。 | 通过 |
| WARN-03 | §5.1.2 | 限定后空模型名触发 WARN，不阻止启动。 | 配 `x: A/`；捕获日志。 | 通过 |
| WARN-04 | §5.1.2 | 空 mapping 值触发 WARN，不阻止启动。 | 配 `x: ""`；捕获日志。 | 通过 |
| WARN-05 | §5.1.2 | 无限定 alias 环触发 WARN，不阻止启动。 | 配 `x: y`、`y: x`；捕获日志。 | 通过 |
| WARN-06 | §5.1 | 目录缺模型或 disabled 不属于启动 WARN；它们只体现在运行时与 status。 | 配已知 provider、缺目标或禁用目标，捕获启动日志；不得出现这两类 catalog 校验告警。 | 通过 |
| ERROR-01 | §5.2 | passthrough 真正失败时 `UnknownModel` 同时指出原始请求名、链末模型名和目标 provider。 | 请求 alias，目标与原始均不可用；检查错误文本。 | 通过 |
| ERROR-02 | §5.2 | 原始名与链末名相同时不重复输出。 | 请求无 mapping 的未知模型；检查名字只出现一次。 | 通过 |
| ERROR-03 | §5.3 | 无 fallback 的未知限定错误发生在任何网络请求之前。 | 带调用计数的 mock upstream；请求失败后计数仍为 0。 | 通过 |
| COMPONENT-01 | §1.1、§6.1、§10.1 | 双 mock provider 下，配置可让 claude 候选走 A、无条目的其余模型走 B。 | 经真实请求 pipeline 分别发送两类模型；观察两个 mock upstream 的实际接收方与 model。 | 通过 |
| LOG-01 | §1.3、§4.4 | 请求日志不新增路由 provider 字段；count-token trail/日志中的旧标签 `ghc` 改成 `upstream`。 | 生成普通请求与 count-tokens fallback 日志；普通行不出现 provider 路由段，count-token provider 标签采用 upstream。 | 通过 |
| ISOLATION-01 | §8.1、§10.2 | 每个 provider 使用不同 httpx client 与连接池，各自应用 stream cap。 | 若只靠对象结构或 mock，只能记结构符合；只有真实连接故障注入证明互不干扰后才能验收运行时隔离。 | 未验证：结构检查符合；未做真实连接故障注入 |
| ISOLATION-02 | §8.1、§10.2 | 两套凭据分别用于对应 provider，不串用。 | 需要两份真实 token 与双账号上游观察；没有该环境则必须标未验证。 | 未验证：用户裁掉真实双账号验证，本环境也未提供两份真实 token |
| ISOLATION-03 | §8.1 | 每 provider 新建的 httpx client 在服务退出时必须经 `Chain.aclose()` 关闭，不能只关闭用于启动探测的 bootstrap client。 | 令生产 `_serve_pipeline` 正常返回，用可观测 close 状态的 chain 与 bootstrap client 代替真实对象；预期两者均 closed。 | 偏差 |

矩阵主体已于读取实现前冻结。CFG-08、STATUS-11、STATUS-12、ISOLATION-03 是收尾时按“从 Spec 逐句反向找对应行”补出的漏项；它们只补入 Spec 已写明而首轮矩阵遗漏的行为，没有按实现形状改变原判据。

## 发现

### impl-verify-multi-provider-routing-01：配置接受语法上非法、无法可靠限定引用的 provider 名

- finding_id：`impl-verify-multi-provider-routing-01`
- severity：major
- primary_location：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/config/schema.py:418-428`
- related_locations：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/pipeline/model_resolution.py:86-105`；`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/model_provider/registry.py:24-37`
- Spec 条款：§2.1 明定 provider 名不得含 `/`；§5.1.2 明定 `/model` 的空 head 不是任何 provider 名。
- acceptance criterion ID：CFG-08
- 推导判据：配置层不得接受 `A/B` 或空串作为 provider 名。否则前者无法用 `provider/model` 语法无歧义引用，后者会把 Spec 明定应为未知限定的空 head 变成已知 provider。
- oracle：分别用 `A/B` 与空串作为 `model_providers` 键并加载 `ProxyConfig`；合法结果只能是配置失败。若错误地接受，再打 `A/B/target` 与 `/target`，观察解析结果以证明不是纯静态洁癖。
- observed result：两种键都被 `ProxyConfig` 接受。只配置 provider `A/B` 后，请求名 `A/B/target` 被按首个 `/` 拆成未知 provider `A`，报 `RoutingError`，错误信息甚至同时列出“configured providers: A/B”；只配置空名 provider 后，`/target` 的空 head 被识别成已知 provider `""`，与 §5.1.2 的明确语义相反。
- 影响：这是被 schema 接受并可启动的配置，不是畸形请求。含 `/` 的 provider 可能作为 default 处理无前缀请求，却无法通过本功能新增的 mapping/request 前缀稳定寻址；空名 provider 则改变 `/model` 的 fallback 语义。它破坏公开配置语法，故定为 major。
- 证据权重：强到足以行动。配置接受与请求解析均由目标提交的真实对象执行；结论不依赖源码猜测。
- 复现命令：`cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/verify_multi_provider.py`，查看 `CFG-08`；最终摘要为 `total=66 pass=63 fail=3 failures=WARN-01,ISOLATION-03,CFG-08`。
- 建议：在配置边界验证每个 `model_providers` 键非空且不含 `/`，错误消息说明该字符保留给 `provider/model` 限定语法；同一验证应覆盖 default/fallback 所引用的键，而不是在请求期补救。

### impl-verify-multi-provider-routing-02：已配置 fallback 时 WARN 不说目标 provider 名

- finding_id：`impl-verify-multi-provider-routing-02`
- severity：minor
- primary_location：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/pipeline/model_resolution.py:165-199`
- related_locations：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/server/composition.py:493-499`
- Spec 条款：§5.1.1。
- acceptance criterion ID：WARN-01
- 推导判据：配置 `fallback_model_provider: B` 且 mapping 含未知限定 `x: typo/a` 时，启动 WARN 必须同时指出键 `x` 和将承接它的 provider `B`。
- oracle：捕获真实 `build_chain` 的 `app.server.composition` WARN，要求后果子句包含 fallback 的实际名称，而不是只出现泛称；`B` 仅出现在“configured: A, B”列表不算。
- observed result：实际 WARN 为 `requests for 'x' will be served by the fallback provider`。它列出 configured providers `A, B`，但没有说明二者中的哪一个是 fallback。实现把 `fallback_configured` 作为 bool 传入静态检查，因此该层根本拿不到名称。
- 影响：路由行为正确，启动不被阻断，但多 provider 运维告警缺少 Spec 要求的直接去向；读者必须再查配置才能知道请求会去哪，属于局部可观测性偏差。
- 证据权重：强到足以行动。初版探针曾因只查字符串 `B` 而被“configured: A, B”假绿；收紧为匹配后果子句中的目标后稳定失败。
- 复现命令：`cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/verify_multi_provider.py`，查看 `WARN-01`。
- 建议：让 `inspect_mappings` 接收 fallback 名本身，或由调用方在渲染 WARN 时补入名称；无 fallback 分支现有 `REFUSED` 措辞已符合，不应被一并改弱。

### impl-verify-multi-provider-routing-03：生产退出路径只关 bootstrap client，未关闭每 provider client

- finding_id：`impl-verify-multi-provider-routing-03`
- severity：minor
- primary_location：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/cli.py:178-197`
- related_locations：`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/cli.py:136-175`；`/home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing/src/app/core/chain.py:56-60`
- Spec 条款：§8.1 的“构造从一个变为每 provider 一个，生命周期（关闭）跟着变”。
- acceptance criterion ID：ISOLATION-03
- 推导判据：生产 serve 函数正常或异常退出时，必须调用拥有 `provider_clients` 的 `Chain.aclose()`；只关闭启动探测用的 `http_client` 不够。
- oracle：用记录 `aclose()` 调用状态的 chain 与 bootstrap client 替换真实对象，让 `_serve_pipeline` 正常返回；两者都必须 closed。该 monkeypatch 只替换外部运行与对象构造，保留被检的 `_serve_pipeline` finally 控制流。
- observed result：`bootstrap_client_closed=True`，`chain_closed=False`。`Chain.aclose()` 已能关闭所有 `provider_clients`，但 `_serve_pipeline` 从不调用它；`serve_inherited` 的 finally 同样只调用 bootstrap `http_client.aclose()`。
- 影响：真实进程退出时操作系统最终会回收 socket，因此没有证明会串 provider 或污染请求；但 async connection pool 未走自身关闭协议，在嵌入式调用、测试内重复启停或未来进程内重启时会积留资源。核心路由仍可用，故定为 minor。
- 证据权重：强到足以行动。生产控制流被真实执行，观察的是两个对象各自的 close 状态；对 socket 长期后果只作条件性说明，不冒充已实测泄漏量。
- 复现命令：`cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/verify_multi_provider.py`，查看 `ISOLATION-03`。
- 建议：让两个 serve 路径在取得 chain 后都以 `await chain.aclose()` 收口，并明确 bootstrap client 的所有权，避免同一 client 重复关闭与 provider clients 漏关并存。

## 我验过且符合的

- CFG-01：`x: A/target` 实测得到 provider=A、model=`target`。
- CFG-02：`A/vendor/model` 实测按第一个 `/` 分割，tail 保留为 `vendor/model`。
- CFG-03：provider `A.One` 只被相同拼写命中；`a-one` 被判未知限定，没有套 model canonical。
- CFG-04：无 fallback 的 registry 可建立；命中 `typo/model` 时抛请求级 `RoutingError`，没有落 default。
- CFG-05：fallback=`missing` 在 registry 构造期抛 `ProviderNotConfigured`。
- CFG-06：count-tokens 默认与显式合法值均为 `[upstream, local]`；旧值 `[ghc, local]` 的 ValidationError 明说 `ghc` renamed to `upstream`。
- CFG-07：mapping `x: A/model@anthropic-messages` 的 target 实测保留完整 `model@anthropic-messages`，未解析值侧 format。
- ROUTE-01：`x: A/target` 后即使另有 `target: B/b` 仍停在 A/target。
- ROUTE-02：Spec 反例 `x: a/target`、`target: B/b`、fallback=A 实测去 A/target，没有继续跳到 B。
- ROUTE-03：三跳无限定链最后读到 A 限定，实测 provider=A、model=`target`、hops=3。
- ROUTE-04A：`x: b` 且 b 无条目时实测 default=B、model=`b`、hops=1。
- ROUTE-04B：超过 8 跳的链实测停在第 8 次读出的 `n8`，origin=`default`、hops=8。
- ROUTE-05：目标缺失而原始名 `original` 可用时，真实 ASGI 请求返回 200，A 的 mock upstream 实际收到 model=`original`，resolution 标为 passthrough。
- ROUTE-06：目标与原始名都缺失时实测抛 `UnknownModel`。
- ROUTE-07：链中间 `middle` 可用、链末 `end` 不可用时，真实 ASGI 请求返回 404，两个 mock upstream 的发送计数都未增加；没有就地使用 middle。
- ROUTE-08：无 mapping 的 `target` 实测由 default B 承接。
- ROUTE-09：`alias-a: A/target` 去 A；另一个只写 `alias-b: target` 的拼法独立落 default B。
- ROUTE-10：target 与目录仅在大小写和 `.`/`-` 上等价时，实测发出的 id 保留目录拼写 `Canonical.Model`。
- REQUEST-01：请求 `A/alias` 遇配置 `alias: B/target` 仍实测去 A/target。
- REQUEST-02：请求 `typo/target` 有 fallback=A 时去 A；无 fallback 时请求级失败。
- REQUEST-03：`A/target@anthropic-messages` 实测先剥 format 再剥 provider，结果 A/target。
- REQUEST-04：请求 `A/opus` 在 `opus: alias`、`alias: A/target` 下继续走完整链到 target。
- REQUEST-05：请求 `A/opus` 在 `opus: B/target` 下丢弃链上 B，仍去 A/target。
- REQUEST-06：请求 `A/opus` 在 `opus: typo/target`、fallback=B 下没有使用 fallback，仍去 A/target。
- REQUEST-07：请求 `A/original` 的 mapping 目标缺失但 A 提供裸名 original 时，实测 passthrough model=`original`，没有把 `A/` 带入模型名。
- REQUEST-08：经生产 router 与 pipeline 实测 `/v1/messages`、`/v1/messages/count_tokens`，以及 chat completions、responses、embeddings 的无前缀、`/v1`、`/openai/v1` 共 11 条请求体入口；每条均返回 200，A 实际收到裸 model=`all-model`。
- REQUEST-09：Azure `/openai/deployments/A/model/chat/completions` 与 Gemini `/v1beta/models/A/model:generateContent` 均由真实 router 返回 404，没有把 path 中的斜杠前缀当请求侧 provider 语法。
- MODELS-01：`/v1/models` 同时列出可服务的目录名与仅存在于 mapping 键的 `alias-a`。
- MODELS-02：构造 yes、absent、disabled、unknown、unroutable 后，目录只列 yes 候选。
- MODELS-03：别名行返回 id=`alias-a`，没有用解析后的 target `a` 代替；直接候选 `a` 因实际落到不可服务的 default 而未被多报。
- MODELS-04：A、B 两条可服务路由的 `owned_by` 分别为 A、B。
- MODELS-05：目录 `Canonical.Model` 与 mapping 键 `canonical-model` 按 canonical 去重，只保留目录拼写；最终顺序为 `Canonical.Model`、`b`、`original`、`alias-a`。
- MODELS-06：`/models`、`/v1/models`、`/openai/v1/models` 三个真实入口返回完全相同的 data。
- STATUS-01：default 目录为空时 `/api/status` 仍返回 HTTP 200，且 `ready=false`。
- STATUS-02：routes 键集合实测等于目录名与 mapping 键的 canonical 并集，目录拼写优先且顺序符合定义。
- STATUS-03：路由目标可用时 serviceable=`yes` 可达。
- STATUS-04：已加载目录缺目标时 serviceable=`absent` 可达。
- STATUS-05：目标被 provider 禁用时 serviceable=`disabled` 可达。
- STATUS-06：目标 provider 的 catalog 未加载时 serviceable=`unknown` 可达。
- STATUS-07：未知限定且无 fallback 时 serviceable=`unroutable` 可达，provider 实测为 JSON null。
- STATUS-08：mapping 目标缺失而原始名可用时，route 行实测 model=`original`、intended=`missing-target`、serviceable=`yes`；普通相同名行不输出 intended。
- STATUS-09：providers 汇总实测 models=2、disabled=1、catalog=`ok`、base_url 正确、`catalog_refreshed_at` 为成功刷新时间。
- STATUS-10：default 有目录与无目录两态下，status.ready 与 readiness 的 200/503 结论一致。
- STATUS-11：覆盖所有 route 行后均未出现已取消的自由文本 `detail` 字段。
- STATUS-12：同一运行对象的目录从空变为含 target 后，连续两次 status 实测从 serviceable=`unknown` 变为 `yes`，刷新时间同步更新。
- READY-01：default B 有目录、次要 A 为空时 readiness 返回 200 ready。
- READY-02：default B 为空、次要 A 有目录时 readiness 返回 503 uninitialized。
- READY-03：default 有目录而 fallback/次要 provider 为空不影响 readiness。
- READY-04：ready 与 uninitialized 两态响应均带 status、default_model_provider、models，值分别与 default 目录一致。
- READY-05：一个请求占满唯一 admission slot 时，`/health/readiness` 在 1 秒界内立即返回，而 `/api/status` 保持等待直到 slot 释放；移除 readiness 豁免的 monkeypatch 正控使探针按预期失败。
- WARN-02：无 fallback 的未知限定 WARN 实测包含 mapping 键并明确写 `REFUSED`。
- WARN-03：`x: A/` 实测触发 empty-model WARN 且 chain 仍建立。
- WARN-04：`x: ""` 实测触发 empty-model WARN 且 chain 仍建立。
- WARN-05：`a: b`、`b: a` 实测触发 cycle WARN，列出 `a -> b -> a` 和 8-hop 后果。
- WARN-06：已知 provider 下的 catalog 缺模型和 disabled 模型没有产生启动 WARN。
- ERROR-01：失败 passthrough 的 `UnknownModel` 实测同时包含 provider A、原始名 alias、链末 `target-missing`。
- ERROR-02：原始名与链末名相同的普通未知模型消息只出现一次模型名。
- ERROR-03：无 fallback 的未知限定经真实 ASGI 请求返回 400，A、B 两个 mock upstream 的发送计数都没有增加。
- COMPONENT-01：双 mock provider 真实 pipeline 中，`claude-alias` 请求由 A 收到为 `claude-model`，无条目的 `gpt-model` 由 default B 收到。
- LOG-01：真实请求输出与 formatter 探针都未在普通请求行增加路由 provider 段；count-token 降级格式为 `provider(upstream-failed,local)`，没有旧标签 ghc。
- ISOLATION-01（仅结构子判据）：构造双 provider 时得到两个不同 AsyncClient，对两个 client 各调用一次 stream cap；手工调用 `Chain.aclose()` 后两者均 closed。真实故障隔离仍列在下一节，不把结构绿冒充运行证据。

## 我推导出判据但没能打到的

- ISOLATION-01 的运行时半边，Spec §8.1、§10.2：我能写出“让 A 的同 origin HTTP/2 连接遭遇 GOAWAY，同时观察 B 的在飞请求不受影响”的判据，但 mock transport 不具有真实 TCP/HTTP2 连接池与 GOAWAY blast radius，不能证明池间故障隔离。用户已裁定本次 mock 为主、不做真实账号验证，因此该项结论是未验证。结构证据只证明两个 AsyncClient 对象不同且各自装了 cap，不冒充运行证据。
- ISOLATION-02，Spec §8.1、§10.2：我能写出“两份真实 token 各只出现在对应 provider 的 auth/inference leg”的判据，但本环境没有两份真实 Copilot 凭据，且用户明确裁掉真实双账号 canary。该项结论是未验证。
- 权威归属边界：本任务的用户指令明确要求把 Spec 中标为“用户裁决”的条款作为判据，因此本轮按该授权执行；没有提供 18 个原始裁决的逐字 transcript，我没有独立核实 Spec 对每一条的归属。它不改变本次行为验收结果，但不能由本报告外推成“裁决归属已取证”。
- 除以上三项外，没有写得出可执行判据却未执行的矩阵行；每一行均已收敛为通过、偏差或未验证。

## 我考虑过但排除的怀疑方向

- 初轮 models 探针把 A 目录中的裸名 `a` 预期为必列，实际未列，曾产生 MODELS-01、03、05 三个失败。我排除实现缺陷：`a` 自己没有 mapping，按 §6.1 必须走 default B，而 B 不提供它，所以 serviceable 不是 yes，`/v1/models` 正应过滤。修正独立 oracle 后三项转绿；原始失败保存在 `verify-multi-provider-output.json`，修正结果保存在 `verify-multi-provider-output-2.json` 及最终输出。
- WARN-01 初轮只要求消息同时包含 `B` 与 `fallback`，因 `B` 出现在 `(configured: A, B)` 而假绿。我排除“这已满足 Spec”的判断：configured 集合不能说明谁是 fallback。将谓词收紧为后果子句必须直接命名 B 后，稳定得到 finding 02。
- 我怀疑过 `/api/status` 的 disabled 行同时出现 model=原始 alias、intended=被禁目标是否自相矛盾。对照 §2.4 与 §4.2.4 后排除：model 是 passthrough 真正会尝试的原始名，intended 是配置目标；serviceable=disabled 解释导致这次映射不可服务的配置目标，三个事实可以同时成立。
- 我怀疑过 A 目录里的模型出现在候选集却被 `/v1/models` 过滤是否违背“所有 provider 并集”。排除理由与第一项相同：并集定义候选，§4.1 第 6 条另要求候选实际 serviceable 才能列；两步不能合并成简单并集。
- 我检查到 `rejection_capture.py` 会保存 `context.provider_name`，但没有判成 §4.4 违约。§4.4 禁的是给 `RequestLine` 与控制台行新增 provider 字段，并明确把 rejection capture 列为不动；结构化拒绝记录不是那条展示面。
- 真实日志会把请求侧 `A/all-model` 显示在“asked”一侧，同时 resolved 显示裸名 `all-model`。我没有把前缀出现在整条日志中判成 §3.2 违约：该条禁止前缀留在 resolved model 并流入 describe、错误和 resolved 展示，不禁止忠实记录客户端原始 requested name。
- §2.1 明说 `A/vendor/model` 按第一个 `/` 分割并保留 tail；§6.3 又把“含斜杠 id 无法映射”列为缺口。我按更具体、标为用户裁决的 §2.1 执行，实测该 qualified 形式保留 `vendor/model`；§6.3 的“原样写出”只按无 provider 前缀的 `vendor/model` 理解，没有据此把实现支持 qualified tail 判成缺陷。
- mapping 键为空或全空白时，候选集合代码会跳过它。我考虑过按“所有 mapping 键”报集合缺项，但没有立项：入站解析明确拒绝空模型名，Spec 只为 mapping 的空值规定 WARN，没有把空键定义为合法可发送候选；在缺少相反条款时，把不可请求的空键列成可达名字反而会误报。
- disabled id 与 mapping target 只在大小写或 `.`/`-` 上等价时，status 的 disabled 分类可能依赖 disabled 配置的精确拼写。我没有立项：本 Spec 明定 canonical 的位置是 available_ids 命中与候选去重，没有裁定 `disabled_models` 自身采用 canonical 等价；把这个猜测升级成验收缺陷会越过判据。
- `driver.py` 的 count-tokens docstring 仍有一句旧词 `ghc`。我没有把它列为行为发现：运行时 provider 值、trail、判断与控制台渲染均实测已改为 upstream；本岗位不做文档/源码措辞评审。若主会话另做代码评审，这是一处可顺手清理的陈旧注释。
- 我检查了 target commit 的文件集合，没有修改 `docs/.human-controlled/`；因此没有触发 §11 禁止本任务修改用户文件的交付违约。
- 除以上方向外，无其他纯推理排除项。

## 验证资产与实际执行

所有一次性资产都位于用户指定的 job tmp，没有改生产代码或既有测试：

- 主验收探针：`/home/xp/.claude/jobs/0e3de57b/tmp/verify_multi_provider.py`
- 主探针最终原始输出：`/home/xp/.claude/jobs/0e3de57b/tmp/verify-multi-provider-output-final.json`
- 解析规则随机差分探针：`/home/xp/.claude/jobs/0e3de57b/tmp/fuzz_route_rules.py`
- 解析规则分辨力正控：`/home/xp/.claude/jobs/0e3de57b/tmp/fuzz_route_rules_control.py`
- admission 行为探针：`/home/xp/.claude/jobs/0e3de57b/tmp/verify_admission_paths.py`
- admission 分辨力正控：`/home/xp/.claude/jobs/0e3de57b/tmp/verify_admission_paths_control.py`
- 报告矩阵计数脚本：`/home/xp/.claude/jobs/0e3de57b/tmp/count_report.py`

实际执行及结果：

1. `sha256sum /home/xp/src/ghc-api-proxy-py/.dev/docs/multi-provider-routing/spec.md`：初次与收尾两次均为 `a697e4a8a0cf3f676b3c3e283f8c147de6eb326ca8aab50cc8d39332bca09636`，说明矩阵冻结后 Spec 未变。
2. `cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/verify_multi_provider.py > /home/xp/.claude/jobs/0e3de57b/tmp/verify-multi-provider-output-final.json`：退出 1 是预期的偏差汇总；`total=66 pass=63 fail=3 failures=WARN-01,ISOLATION-03,CFG-08`。66 项包括 60 个通过矩阵行、3 个偏差矩阵行、两个分辨力正控与 ROUTE-05 的额外 E2E 复验；两个未验证矩阵行没有伪造成探针 PASS。
3. `cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/fuzz_route_rules.py`：固定 seed 260827，5000 张随机 mapping 表；40000 个 discovery case 与 50000 个 request-side provider choice case 全部与独立五行规则 oracle 一致。
4. `cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/fuzz_route_rules_control.py`：把生产模块运行时 hop limit 从 8 monkeypatch 为 7，并先从 `discover_provider.__globals__` 证明变异生效；oracle 在第 4 组样本按预期拒绝，随后 finally 恢复为 8。
5. `cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/verify_admission_paths.py`：`health_bypassed_occupied_slot=true`、`api_status_waited_for_slot=true`。
6. `cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run python /home/xp/.claude/jobs/0e3de57b/tmp/verify_admission_paths_control.py`：移除 readiness 豁免并证明变异生效后，探针按预期超时/失败；finally 恢复原常量。
7. `cd /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing && uv run pytest --quiet tests/unit/pipeline/test_model_resolution.py tests/int/test_pipeline_ops_routes.py tests/unit/config/test_config_schema.py`：`80 passed in 2.28s`。这只证明相关既有回归仍绿，不作为独立验收 oracle。
8. `git -C /home/xp/src/ghc-api-proxy-py/.claude/worktrees/multi-provider-routing status --short --branch` 与 `rev-parse HEAD`：最终仍是 clean `worktree-multi-provider-routing`，HEAD=`bb1c5f5fadeaeb9c590b6d20462b412e5c61c98b`。本轮没有临时修改后还原生产代码；所有变异都是进程内 monkeypatch，并由 finally 恢复。
9. `python /home/xp/.claude/jobs/0e3de57b/tmp/count_report.py`：65 个矩阵判据 ID 唯一，结论为通过 60、偏差 3、未验证 2、待执行 0。

没有重跑用户已告知为 1855 passed 的全套测试；同源全绿对本岗位的独立判据不增加证据。目标改动的关键真实入口已由独立 ASGI probe 覆盖，相关既有测试只作回归旁证。

## 整体判定

总体判定：**有偏差，needs-fix**。

65 个验收判据中，60 个通过，3 个偏差，2 个按 Spec §10.2 如实未验证。核心五行解析表、规则 2 的“仍是终点”反例、§2.4 passthrough 实际发送、§2.5 行为变更、请求侧三条优先级规则、`@`/`/` 顺序、models/status/readiness 与 `ghc` 改名错误均实测符合。

不能直接判 pass 的承重项是 CFG-08：公开配置接受 Spec 明禁的 provider 名，并产生“配置存在但新增路由语法无法引用”或空 head 被误认成 provider 的行为。其余两项偏差分别是 WARN 未命名 fallback 目标、生产退出未关闭每 provider client。

## 我最没把握的三个判断

1. CFG-08 定为 major 而非 minor：观测事实没有疑问，犹豫只在定级。支持 major 的依据是它违反公开配置语法，且 schema 接受后允许服务启动，失败落到请求期；支持 minor 的依据是只有选择非法 provider 键的部署才触发，改名有直接绕行。我按“公共契约未满足”定 major，置信度中等，强到足以阻止本次判 pass。
2. ISOLATION-03 定为 minor：控制流事实已证实，但真实 CLI 进程通常在 serve 返回后立即退出，OS 会回收 socket，所以我没有把未 await AsyncClient close 外推成已发生的跨 provider 污染或长期泄漏。若产品存在进程内重启或把 `_serve_pipeline` 当可重复调用库函数的契约，影响应上调；当前证据只支持 minor。
3. disabled route 行的 model/intended/serviceable 三元语义：我按 §2.4 与 §4.2.4 解释为“实际 passthrough 名、配置目标、目标为何不可服务”，因此没有报矛盾。Spec 示例是在 intended 字段加入前写的，未展示 disabled 的新版完整行；若权威意图是 serviceable 必须只描述 model 字段本身，这里会需要另一次语义裁决。当前实现与全文合读更支持现有解释，但置信度低于其他通过项。

## 执行本契约时遇到的摩擦

- `as-verifier` skill 把判据来源称为“冻结 Spec”，而项目规则与本任务明确说 Spec 是活文档。我没有冻结文档本身，只在读取实现前把当时 Spec 的 SHA 与独立矩阵落盘；收尾重核 SHA 未变。
- 初版主探针有三个 models 假失败和一个 WARN 假绿。前者把“候选并集”误读成“全部列出”，后者让 fallback 名在 configured 列表里的偶然出现冒充后果子句。两轮都保留原始输出，并在最终 oracle 中收紧；这是探针纠错，不是改判据迎合实现。
- 一次用于统计报告行的 Bash heredoc 被 worktree guard 拒绝执行。我改为在用户指定 tmp 写独立只读脚本，再以简单命令运行；没有放宽权限或绕过 guard。
- none 以外无其他权限、文件或工具阻塞。

## 交付声明

- delivery_complete: true
- completed_at: 2026-08-27T06:43:42+00:00
- finding_total: 3
- blocker: 0
- major: 1
- minor: 2
- nit: 0
- matrix_total: 65
- matrix_pass: 60
- matrix_deviation: 3
- matrix_unverified: 2
- overall_verdict: needs-fix


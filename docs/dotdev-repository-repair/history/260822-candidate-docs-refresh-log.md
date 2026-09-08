# 候选材料刷新日志（2026-08-22）

**依据**：`.dev/docs/tmp/260822-candidates-vs-user-updates-reconciliation.md` 的逐条对账。
**范围**：`.dev/human-controlled-docs-candidates/` 下指定的 11 份，外加索引 `README.md`（任务允许「若索引需要更新则改」，它确实需要）。**未碰** `upstream-retry-and-continuation-supplements.md`，那份由主会话维护。
**约束遵守**：`docs/.human-controlled/` 一字未改；所有写入的 `file:line` 均于本次会话现场核过（`rg -n` / `sed -n` / `nl -ba`）；未改写任何归档报告里的引文与路径；未跑 `ruff format`，未动源码与测试，未提交。

## 改动表

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `uncovered-modules.md` | 整体重写 | 对照基准由 `MAIN.md` 换成 `module-org.md` / `api.md` / `request-pipeline.md` / `message-translation.md` / `ghc-api.md`；撤下已追认的四行并留表记录落点；`delivery/` 一行改写为「被追认的是 `pipeline/delivery`，顶层 legacy `src/app/delivery/` 仍无位置」；撤下对三个「有疑虑」包的归属建议（用户已挂起该问题）；`auth/` 一行收紧为「只剩来源链无位置」；无生产消费者清单按现场 grep 重算 |
| `config-schema-gap.md` | 撤下＋改写＋重指＋修正引用 | 撤下 4 条（C-2、continuation 续写构造、`max_tokens_as_retryable`、`synthesized_response_headers_after_sec`），§七 由「提案」改写为「部分已采纳」，全篇符号补上核过的行号 |
| `config-migration-gaps.md` | 撤下＋改写＋重指＋修正引用 | §一 四节缩为两节（`approval` / `tokenization` 端点已被标「暂不支持」），§三「常驻字节预算」整条撤下，§五 顺序重排 |
| `existing-rulings.md` | 撤下＋重指＋修正引用 | §二 撤下 cgroup 的「rolling 一侧」一行；§三 表的「来源」列由 `MAIN.md` 逐行重指到拆分后的文档，并补入两条新裁决行（pidfile、rolling 删除）；`model-translation.md` → `message-translation.md` |
| `instructions-shape-conflict.md` | 重指＋修正引用 | 目标文档更名，全篇重指；§六 三条测试的现名、新位置与改名前后对照全部更新（文件已移到 `tests/unit/pipeline/translation_driver/`） |
| `pidfile-port-scoping.md` | 修正引用 | 内容全部仍然成立，只补上可复算的代码位置与一次现场复核（4141 仍是 pid 2254087，pidfile 仍不存在） |
| `deployment.md` | 撤下＋改写＋修正引用 | 撤下 rolling 与 generation 两张模块表、「当前未闭合项」一节；纠正「`--fd` 走 `uvicorn.run` 且服务旧链」这一过时描述；`shutdown.py` 的去留仍然打开 |
| `systemd-shutdown.md` | 改写＋修正引用 | 被否决的提案原样留档；§五 四条不一致的行号全部重新核准（原来的 `:235` / `:238` / `:240` / `existing-rulings.md:92` 都已失效）；依赖 `rolling/runtime.py` 的三处顺带收益就地标注为已失效 |
| `rolling-removal.md` | 修正引用 | 建议仍然打开；`MAIN.md` 的零停机表述重指到 `lifecycle.md:46`；标注「两级裁决日期」本文与另两份不一致 |
| `pipeline-subscriptions.md` | 改写＋重指＋修正引用 | 标题与引文由 `MAIN.md` 重指到 `request-pipeline.md:15-19`；「一个订阅者」改写为「三个订阅者＋一个共用载体」；`RequestContext` 字段数 20 → 21；新增第 4 个待裁决点（文档名与代码名不一致）；三条外链重指 |
| `proactive-rate-limiter.md` | 修正引用 | 三条提案与待裁决点全部仍然打开；`config.example.yaml` 与 `schema.py`、`handler.py` 的行号全部纠正 |
| `README.md`（索引） | 改写 | 表头去掉 `MAIN.md`；补上此前漏列的三份（`rolling-removal.md`、`instructions-shape-conflict.md`、`upstream-retry-and-continuation-supplements.md`）；「已被采纳的部分」补 2026-08-22 一段，并点名四条**已被否决**的建议，提醒不要换个说法再提 |

计数：**改动文件 12 份**（11 份指定范围 ＋ 索引 `README.md`）。按条目粗计：**撤下 9 条**、**改写 12 条**、**重指 8 处**、**修正引用 30 余处**。

### `uncovered-modules.md` 细目

- **撤下**：`config/`、`history/`、`observability/`、`cli.py` 四行（已进 `module-org.md:7-17`），改为「已被采纳的部分」一张对照表。
- **改写**：`delivery/` 行 → 明确所指为顶层 legacy 包，并给出复算（`rg -n 'app\.delivery' src` 三处命中，唯一外部消费者是 `src/app/routes/anthropic.py:12`，属旧链）。
- **改写**：`anthropic/`、`openai/`、`context/` 三行 → 只陈述职责，删去「应由 `app.pipeline` 涵盖」的归属建议。
- **改写**：`auth/` 行 → device flow 已落 `ghc-api.md:5-8`，来源链仍缺，并与 `config-migration-gaps.md` 的「token 来源」互指。
- **重算**：无生产消费者清单。`observability/tui.py` **移出**（`src/app/server/pipeline_app.py:38` 导入 `footer_tui_or_none`、`:1026` 调用）；其余 15 项复算仍成立；新增了复算命令与「子串匹配会误报」的提醒。
- **补入**：`graceful_timeout.py` 与 `core/` 两行进支撑设施表。

### `config-schema-gap.md` 细目

- **重指**：规则出处 `MAIN.md` → `docs/.human-controlled/README.md:3`。
- **改写**：§一 `pidfile` 行 → `pidfile_dir`，指向 `pidfile-port-scoping.md`。
- **改写**：§一 `upstream_request_retry.*` 行 → 删去「continuation」，说明规格已放弃。
- **修正引用**：C-1 的既有裁决出处补全为 `.dev/docs/anthropic-responses-bridge/architecture.md:656`（U1）与 `:664`（U3，2026-08-19 覆盖 U1 的容量机制部分并明确保留 `buffer_cap_bytes`）；判断由「可能不矛盾」升为「不矛盾」，待确认项保留。
- **撤下**：C-2（continuation 是否构成独立 ADR）——前提消失（`upstream-retry-and-continuation.md:42`「代理内续写（已放弃）」），留一段记录并指出替代物是 `:28-40` 的 MCP-driven 合成续写。原文引的 `spec.md` ADR-BRIDGE-05 现已不在 `spec.md` 中（`architecture.md` 里对应条目现记作 `n`），一并作废。
- **撤下**：§四 continuation 续写请求构造行（`continuation_messages()` 已从 `src` 与 `tests` 中消失）、`max_tokens_as_retryable` 行（被 `hand_over_stop_reasons` 取代，`config.example.yaml:339` / `schema.py:187`）、前言里 `synthesized_response_headers_after_sec` 的「已接入」记录（键已被裁决删除）。
- **修正引用**：§四 前言全部符号补上现场核过的行号；`signature_frame()` 由已不存在的 `pipeline/delivery/anthropic_sse.py` 重指到 `pipeline/delivery/formats/anthropic_messages.py:59`；hedge 行补上「除 schema 外无任何命中」的复算结论。
- **改写**：§七 由「提案」改为「部分已采纳」——中文行 `config.example.yaml:303` 已逐字采纳提案，英文行 `:304` 只采纳了适用范围那半句、仍写 `SSE events`，中英口径不一致；提案收窄为只改这一行，两行解释性注释不再重提。

### `config-migration-gaps.md` 细目

- **重指**：端点出处 `MAIN.md` → `api.md:14-21`。
- **改写／收紧**：§一 四节缩为两节。`approval`（`api.md:20`）与 `tokenization`（`api.md:21`）的端点已被用户划掉标注「暂不支持」，配置缺失与该裁决一致，不再算缺口；两节转为「已撤下」记录，并说明旧实现留着即可。
- **修正引用**：`history` / `observability` 旧字段补 `src/app/config/settings.py:51-55`、`:120-124`；`hooks` 六个订阅点补 `config.example.yaml:420-437` 并列出名字；token 来源补 `settings.py:32,35`；generic 上游补 `settings.py:18-21` 与 `config.example.yaml:150-152`、`module-org.md:15`。
- **撤下**：§三「常驻字节预算」——2026-08-19 U3 重裁把字节级预算整体删除、改以并发数封顶，旧实现已不存在（`rg` 无命中），不存在「切换时静默丢掉」的东西。记录了裁决出处与替代物（`src/app/server/admission.py:25` 的 `InFlightLimit`）。
- **改写**：§五 实施顺序按上述缩减重排。

### `existing-rulings.md` 细目

- **重指**：规则出处与对照基准全部改指拆分后的文档；§三 表的「来源」列逐行落到 `request-pipeline.md:19`、`api.md:8,12`、`ghc-api.md:28,31`、`module-org.md:15-16`、`lifecycle.md:7,18-22,33`、`config.example.yaml:377`。
- **撤下**：§二 的「cgroup 资源限制（rolling 一侧）」一行——`ghc-api-proxy-rolling.slice` 已不存在，缺口消失。记录里保留了单进程一侧已具备的事实，并把 `tests/smoke/` 重指到 `tests/systemd/test_systemd_units.py:288-292`。
- **收紧**：§二 的运维配置节一行由「四节」改为「两节」，理由与出处同 `config-migration-gaps.md` §一。
- **补入**：§三 表新增两行——pidfile 目录语义（2026-08-22）、rolling 删除（2026-08-19），使裁决台账不再断在 08-17。
- **修正引用**：C-1 行的 `config.example.yaml:240` → `:243`。

### `instructions-shape-conflict.md` 细目

- **重指**：`model-translation.md` → `message-translation.md`，正文引用落到 `:34-62` 与 `:62`。
- **修正引用**：§六 三条测试。文件由 `tests/unit/test_translation_driver.py` 移到 `tests/unit/pipeline/translation_driver/test_translation_driver.py`；前两条已改名（`test_system_becomes_a_single_instructions_string`（`:47`）、`test_the_lost_block_metadata_is_named_rather_than_dropped`（`:68`）），第三条同名在 `:145`。改写成对照表，原名保留以便回查，并写明第二条守的东西已从「保全」变成「不静默」。
- **保留**：§五 第 2 条的自撤（划掉的那条）原样保留。

### `pidfile-port-scoping.md` 细目

- **修正引用**：`config.example.yaml:227-235`（含 `:230-231` 英文、`:233` 热重载标注、`:235` 示例值）；实现侧补 `src/app/config/paths.py:30`、`src/app/lifecycle/entry.py:60,107-109,110-118`、`src/app/cli.py:202,217-219,255`、`src/app/config/schema.py:42,383`、`src/app/lifecycle/pidfile.py:94`。
- **保留**：`GHC_API_PROXY_PORT` 拼写这个待裁决点（三条出路、倾向第一条）原样保留；B6 的否决记录原样保留。
- **补入**：一次现场复核——`ss -lntp | grep -w 4141` 仍报 `pid=2254087`，`~/.local/share/ghc-api-proxy/` 里既无 `standalone.pid` 也无 `standalone-4141.pid`，所以补记录的操作仍然适用。

### `deployment.md` 细目

- **撤下**：`app.lifecycle.rolling` 与 `.generation` 两张模块表（8 个模块）、「当前未闭合项」四行表。各留一段记录，说明前三项是「不做了」而非「没做完」，第四项（生产切换）转到 `pidfile-port-scoping.md`。
- **改写**：`--fd` 一段。原文写「仍走 `uvicorn.run`、三级阶梯是否适用是待裁决项」，两点都不对——它现在构造 `create_pipeline_app(chain)`（`src/app/cli.py:155`），用的是 `uvicorn.Server.serve()` 的子类 `_DrainAnnouncingServer`（`cli.py:153-165`），而关闭级数已于 2026-08-17 裁决为两级。
- **修正引用**：三张保留的模块表全部补上现场核过的符号行号；`app.core` 一行改写为「rolling 删除后只剩两个消费者」并给出复算。
- **保留**：`shutdown.py` 的去留仍然打开（复算：`rg -l 'app\.shutdown' src` 无命中）；补入 `systemctl.py` 与 `notify.py` 同样无消费者的事实。

### `systemd-shutdown.md` 细目

- **保留**：被否决的提案（§二～§四）原样留档，首部的否决声明未动。
- **修正引用**：§三 的 `config.example.yaml:235`／`:238`／`:234` → `:238`／`:241`／`:237`；§四 的 `contrib/systemd/ghc-api-proxy.service:23` → `:28`，`/etc/systemd/system.conf:49` 核对无误；§五 第 1 条 `:240` → `:243`；§五 第 3 条改用**行名**引用 `existing-rulings.md`（那份文档本次重排过，行号会变，行名不变）。
- **就地标注失效**：§二 表的「systemd（现状）」一列描述的是 `rolling/runtime.py`，已删除；§二 顺带收益与 §六 第 4 步同理；§二 第 3 点的 `os._exit` 问题**已自行解决**（复算：`rg -n 'os\._exit' src` 只剩 `standalone.py:16` 的一句 docstring）。
- **重指**：调研报告 `docs/tmp/260817-systemd-escalation-research.md` → `.dev/docs/systemd-runtime/reports/`。

### `rolling-removal.md` 细目

- **保留**：第四节的修订建议仍然打开（`lifecycle.md:65-89` 原样在），并在首部标明这一点。
- **重指**：`MAIN.md` 的 `must not be described as full zero-downtime migration` → `lifecycle.md:46` 的中文原句，并说明是同一意思换了承载文件。
- **修正引用**：`lifecycle.md:65-89`、`:67`（那句 2026-08-16 原话）、`src/app/lifecycle/entry.py:70`、`src/app/cli.py:155,185`、`src/app/server/app_factory.py:155`。
- **标注不一致**：本文原记 systemd 两级裁决于 2026-08-18，而 `existing-rulings.md` 与 `systemd-shutdown.md` 都记 2026-08-17。**未擅自改写，只在原句旁标明两处相符、以它们为准。**

### `pipeline-subscriptions.md` 细目

- **重指**：标题与引文出处由 `MAIN.md` 改为 `request-pipeline.md:15-19`；三条外链（`hooks-system.md`、`tool-use.md`、websearch 设计文档）分别重指到 `.dev/docs/archived-2604-rewrite/` 与 `.dev/docs/hosted-web-search/reports/`，并附上「该目录已被用户判为过期笔记」的提醒。
- **改写**：「订阅机制有了第一个订阅者」→ 三个订阅者（`server_tools` / `hosted_web_search` / `blank_text`）加一个共用载体 `counting.py`，注册处补 `src/app/server/composition.py:530`、顺序表补 `src/app/pipeline/subscribers/__init__.py:13-15`。
- **修正引用**：`RequestContext` 字段数由 20 改为 21（`src/app/pipeline/context.py:70` 现场数得），并注明原文写 20 时确是 20；`HookErrorMode` 补 `src/app/hooks/types.py:18`；`hooks` 一节补 `config.example.yaml:420-437`。
- **补入**：待裁决点第 4 条——用户文档 `request-pipeline.md:16` 写 `ClientRequest` / `UpstreamAttempt`，代码是 `RequestContext` / `Attempt`，给了甲乙两条出路交用户选。同时给「修改上下文对象需要写入规则」补了一个现实佐证（`counting.py` 的 docstring 正是为了回避所有权问题才把共用事实放进 `extras`）。

### `proactive-rate-limiter.md` 细目

- **修正引用**：`config.example.yaml:350-352` → `:341-343`；`schema.py:301` → `:396`；`schema.py:150` → `:203`；`handler.py:190` → `:354`；「同一文件 354 行谈 429」→ `:345-346`；`reactive_rate_limiter` 补 `:350`；`client_request_deadline` 补 `:377`；`InFlightLimit` 补 `src/app/server/admission.py:25`，豁免路径补 `:22` 的 `UNGATED_PATHS`。两个 commit 哈希 `f5589ec`、`7e9b62d` 现场 `git cat-file -t` 核过，均存在。
- **保留**：三条提案与「排队时间不计入任何 deadline」的待裁决点原样保留，只在首部标明全部仍然打开。
- **补入**：`UNGATED_PATHS` 旁注释里「`/models` 故意不豁免」的理由。

## 我拿不准、留给主会话或用户的

以下 9 条按重要性排。前 4 条是**我与对账报告判定不一致或报告证据已过期**的地方——报告是我的作业依据，所以这几处我做了取舍，但都摆在这里由主会话复核。

1. **【与报告不一致，且直接影响主会话正在改的文件】`upstream-retry-and-continuation.md` 在报告写完之后又被改过。** 该文件 mtime 是 15:51，而报告的对账基准截止到 15:26。报告 A4 判「已采纳（措辞不同）」，证据是 `:28`「非流式请求只接入适合无痕重试的情形，**不支持合成续写**」。**当前文件里这句话不在了**：`:62-64` 的「## 非流式请求」一节现在写的是「非流式请求也支持无痕重试、**合成续写机制**」——结论被反转。这直接关系到 `upstream-retry-and-continuation-supplements.md` §四 的处置，以及报告 A1／A2 里「『不能续写』这一格真实存在」的论据（其两条支撑之一就是 `:28`，现已失效；另一条 `:40`「只给 anthropic-messages 客户端」仍在）。**主会话改那份文件前请先重读一遍现在的 `upstream-retry-and-continuation.md`。**

2. **【与报告不一致，我改了判定】`config-migration-gaps.md` 的「常驻字节预算」（报告 E5）。** 报告判「仍然打开」，理由是「规格仍只有 `buffer_cap_bytes`」。这句话本身没错，但它描述的是规格侧；而这一条的诉求是「切换时会**静默丢掉**旧实现的全局预算」，**旧实现已经不存在了**：`.dev/docs/anthropic-responses-bridge/architecture.md:664` 的 U3 行记录用户 2026-08-19 重裁——删除 `src/app/delivery/reservation.py` 与两个 resident-bytes 配置项，改以 `proactive_rate_limiter.max_inflight` 封顶；复算 `rg -n 'global_resident_bytes|request_resident_bytes|reservation' src --glob '*.py'` 无命中。所以我按「已过期（前提消失）」处理并撤下了。**如果主会话认为 U3 是开发文档里的转述、不足以推翻，可以把它改回「仍然打开」。**

3. **【报告证据不准】`config-schema-gap.md` §七（报告 D12）实际是「部分已采纳」，不是「仍然打开」。** 报告的证据写「`config.example.yaml:303-304` 仍是『SSE 事件之间的最大间隔秒数』」。现场读到的 `:303` 是「单次尝试上游，SSE **活动**之间的最大间隔秒数（0 = 不超时）。适用于所有流式路径。」——与候选提案的中文首行**逐字一致**。英文 `:304` 只采纳了「Applies to all streaming paths.」那半句，仍写 `SSE events`。该文件 mtime 14:48，早于报告，所以不是「报告之后又改的」，是报告读岔了。我据现场把该节改写成「部分已采纳，提案收窄为只改英文那一行」。

4. **【报告理由不准，结论不受影响】`uncovered-modules.md` 的无消费者清单（报告 C7）。** 报告给的理由是「清单含已删除的 rolling 相关项」。逐项核过：**那 16 项里没有任何 rolling 模块**（该文件 mtime 是 08-15，rolling 删除在 08-19，但它列的本来就不是 rolling 模块）。清单确实需要重算，真正的理由是 `observability/tui.py` 现在有生产消费者了。结论不变，我按现场重算。

5. **这份清单不是全量重扫，我在文件里写明了。** 本次只对既有 15 项逐个复算，没有对 `src/app/**` 做全量扫描。已知至少还有 `lifecycle/systemd/notify.py` 与 `systemctl.py` 两个无生产消费者的模块不在表内。要不要补一次全量扫描，请主会话或用户定——那是一次独立的、可能挖出十几项的作业，不适合塞进本次刷新。

6. **`rolling-removal.md` 里「systemd 两级裁决」的日期与另两份文档冲突（08-18 vs 08-17）。** 我**没有**擅自改写，只在原句旁标明另两处相符、以它们为准。若主会话确知哪个对，可以直接定稿。

7. **`config-schema-gap.md` §三「规格已定案、实现有缺口」那张五行表（报告 D6）我原样保留了，但没有逐行复验。** 报告判「仍然打开：人写文档无变化」——那是对**规格侧**的判断，成立；但表的第三列写的是**旧实现的现状**（`model_overrides` 仍带三条硬编码默认、`transform/model_resolver.py` 仍在剥日期后缀等），这些我这次没有逐条跑过。如果要把这张表当作可行动的依据，需要再核一遍。

8. **`docs/.human-controlled/README.md:18` 指向一份不存在的 `observability.md`，且清单里没有 `release-and-deployment.md`（该文件确实存在）。** 这是用户自己文档的小疏漏，报告 §五.7 建议作为新候选材料提出。我只在 `config-migration-gaps.md` §一 里顺带提了一句「该文件尚未创建」，**没有**为此新建候选文档——新建候选属于「提新建议」，超出「让现有材料与现状对齐」这个任务范围。要不要单开一份，请主会话定。

9. **`config-schema-gap.md` C-2 撤下时顺带发现的一处断链**：原文引 `spec.md` 的 `ADR-BRIDGE-05`，而 `.dev/docs/anthropic-responses-bridge/spec.md` 里现在搜不到这个 ID，`architecture.md` 中对应的条目改记作 `n`（「无 resume contract 时的 post-commit failure」）。因为 C-2 整条已撤，这个断链随之作废，我没有去修。但**其他文档若还引着 `ADR-BRIDGE-05`，会踩到同一个坑**——本次未做全库排查。

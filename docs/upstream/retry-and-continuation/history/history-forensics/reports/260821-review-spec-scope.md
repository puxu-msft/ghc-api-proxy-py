# 评审：取证记录行为 Spec（范围与可实施性向）

- 评审对象：`.dev/docs/history/spec.md`（825 行，文件 mtime 2026-08-21 18:24）
- 评审角度：**范围与可实施性**。事实核对由另一路负责；本文只在「事实错误直接改变范围判断」时才碰事实，并逐条标注重叠。
- 核对基线：`git HEAD = 1b0cdd2`（2026-08-21）。**Spec 自称基线是 `be63418`，该提交距 HEAD 已有 22 个提交**，其中至少三个改动了 Spec 直接引用的符号。
- 背景已读：`proposal.md`（r4）、`reports/260821-structured-logging-design.md`、`reports/260820-*` 全部六份。
- 性质：只读。未修改任何源文件与被评审文档，唯一落盘产物是本文件与 `/tmp/sqlprobe2/` 下的一次性探针。

## 0. 结论先说

**不能按现状冻结。** 三条 blocker 里有两条直接作用在「冻结」这个动作本身：§2–§8 自称是冻结契约，但其中至少五处的取值由 §9 的未裁项决定；§7.4 冻结了一条在 §9.4 推荐形态下做不到的条款。第三条 blocker 作用在优先级论证上——§1.3 的四缺口表对 L1 做了「是不是已经被同伴解决了」的核对，对 L2 没做，而 `rejection_capture.py` 已经在生产闭包里落盘上游错误原文。

但这不是一份要重写的 Spec。它的数据模型、采集点分工、I1–I8 与 §6 的七条查询隔离都扎实，且大部分能直接施工。真正要动的是三处：**把冻结面缩到不依赖待裁项的那一部分**、**把优先级表按 HEAD 重算**、**把三处比例失当的基础设施（ChunkSpool、17 个配置键、10 个指标）交回用户而不是当成已定**。

统计：blocker 3、major 11、minor 6、nit 2。

---

## 1. 忠实度：Spec 有没有偏离 2026-08-20 的裁决

**逐条对过，六项裁决全部被忠实执行，没有一处把用户裁过的东西改回去。** 这一节我尽量说清「凭什么判它忠实」，而不是只给一个勾。

| 裁决 | Spec 的落点 | 判定 |
|---|---|---|
| A1：L1+L2+L3 全做 | §2.1 / §2.2 / §2.3 三张表都在，没有任何一层被降级或加条件 | 忠实 |
| 完整 HTTP、不做 CLI、非 RESTful、动作式路径 | §5 十个端点全部 `POST /history/api/<resource>/<action>`，标识符走请求体；全文零处 `debug history` 子命令 | 忠实 |
| 硬约束：查询不得拖慢请求处理 | §6 落成 Q1–Q7 七条规范条款，且 I7 把它标成「用户点名的唯一危害，是设计约束而不是一般性能考量」；§6 末尾还把它扩到写路径 | 忠实，且**强于**裁决要求（见 §3.4 的比例性讨论） |
| 全量 + 按会话聚合 + 定期归档化 | I8「不删，归档」；§7.3 归档触发；§7.2 `SessionSummary` 为派生视图；§8.1 明确拒绝复用 `success_limit`/`failure_limit` 并说明「这是语义重定，不是改名」 | 忠实。**拒绝复用淘汰式键名这一条做得对**，它是最容易悄悄滑回去的地方 |
| 日志结构化、TUI 从结构化日志解析 | Spec 按任务范围不覆盖，§10.3 显式交代 | 忠实（但结论要修，见 §7.3） |
| 三个可选增量全做 | `replay` §5.6、`export-cassette` §5.7、日志文件 sink 交给结构化日志那份 | 忠实 |

**没有发现「悄悄扩大」。** 我特意查了三处最容易扩大的位置：

- **端点数量**：十个端点全部能追溯到裁决或人写文档。`entries/list`+`get` 是查询面主体；`pin`/`unpin` 是归档裁决的必需配套（「免于归档」没有入口就是一列死字段，这正是 r2 评审 N2 指出过的形状）；`sessions/list`+`get` 来自「按会话聚合」；`archives/list` 来自「定期归档化」；`replay` 与 `export-cassette` 是两个可选增量；`GET /history/ws` 是 `MAIN.md` 第 38 行亲笔列出的产品端点。**十个端点不是镀金**，这一条我判得比较硬。
- **脱敏**：§2.5「取证库本身不脱敏」，并明写这是推定、列出供否决。这是对的——没有臆想的安全措施，也没有在用户没点名的地方加保护。
- **认证**：§5.0 写「无。这些端点与推理端点同在一个监听面上，本项目不为它们单设认证」。同上，克制得对。

一处措辞上的越界，不影响裁决忠实度，但值得点出：§5.0 写「本 Spec 落地后那句话要一并更新」，指的是 `ops_routes.py` 模块 docstring 里那句「History and the management API need state this chain does not own yet, and are absent rather than answered with a plausible stub」。**那句话是既有代码的自述，改它属于实施动作，不是 Spec 能替实施者预先承诺的**。写成「落地时应当同步更新」即可。（nit）

---

## 2. Blocker

### B1 —— blocker —— §2–§8 自称冻结，但其中五处的取值由 §9 的未裁项决定

Spec 开头写：「§2–§8 为冻结契约，实施切片按它验收。**§9 的六项未裁决，未裁之前不得当作已定**」。这两句合起来不成立，因为冻结面被待裁项穿透了：

| 冻结面里的条款 | 由哪一项未裁项决定 |
|---|---|
| §8.2 整张键表的前缀（`history.*` 还是 `forensics.*`） | §9.2 |
| §8.2 第一行 `history.enabled` 是不是总开关 | §9.1 |
| §7.4 归档的物理形态（同库冷表 / 分片库文件 / 压缩包） | §9.4 |
| §5.8 响应里的 `location` 字段形态、§5.1 `include_archived` 的代价、§2.1 `archived_batch` 的取值语义 | §9.4 |
| §2.1 字段表按「两份并存」写、L1 的分量大小 | §9.6（Spec 自己在 §1.2 承认这一点） |

也就是说：**冻结的 §7 与 §8 有相当一部分是「等裁决落下来才知道是什么」**，而实施切片被要求「按它验收」。这不是措辞瑕疵——分片 7（归档）与分片 9（配置键）按现状根本不能开工，而 Spec 没有说这件事。

**修法（我的主张）**：把冻结面显式缩成「不依赖待裁项的那一部分」，并在 §7、§8 的章首各加一行「本章在 §9.x 裁决前不构成验收依据」。具体地：§2.1–§2.3 的字段表（除 `archived_batch` 语义）、§3 全部、§4 全部、§5.0–§5.7、§6 全部可以立即冻结；§5.8、§7.3–§7.5、§8.2 待裁。这样冻结这个动作才有意义。

**严重度：blocker。** 冻结是一个会被下游当成事实引用的动作，一份「冻结了但有五处待定」的契约在实施期会被读成「这些都定了」，而定错的方向是「以为有、实际没有」。
**可信度：可据以行动**（五处引用逐条对回 §9 原文核过）。

### B2 —— blocker —— §1.3 的缺口表对 L1 做了「已被独立解决」的核对，对 L2 没做；`rejection_capture` 已经在落盘上游错误原文

§1.3 是整份 Spec 的优先级基座，也是任务问题 5 直接问的东西。它的表格写：

| 缺口 | 次数 | 归属 | Spec 判定 |
|---|---|---:|---|
| 上游错误响应体原文 | 2 | L2 | 「**仍然缺**。只在日志 `detail` 留只言片语」 |
| 实际发往上游的字节级 body | 4 | L2 | 「**仍然缺**。数据在手（`response.request.content`），未保存」 |

**第一条在 HEAD 上不成立，第二条只对了一半。** `src/app/observability/rejection_capture.py`（生产闭包内，`pipeline_app._dispatch` 有两个调用点：`handle_bounded` 抛错分支与 `handled.response is None` 分支）把下面这些写进 `user_data_path()/rejected/<时刻>-<状态码>-<request_id>.json`：

- `"upstream": error.body` —— **上游错误响应体原文**，逐字；
- `"payload": context.payload` —— 翻译之后、每个 `attempt.prepare` 订阅者都改过之后的 body（模块自己的注释：「This is the payload as it stood when the attempt was made」）；
- 外加 `status` / `requested_model` / `resolved_model` / `provider` / `endpoint` / `translation_required` / `route_reason` / `attempts`。

它的适用面是 `UpstreamRejected`，即「非限流的 4xx」——正是需求盘点里那两次 400（web search、空 text block）的形状。模块 docstring 逐字点名了这两次事故作为它存在的理由。

所以缺口表在 HEAD 上应当是：

| 缺口 | 现状 |
|---|---|
| 实际发往上游的字节级 body | **4xx 拒绝路径上已有 payload 字典**（非序列化后的字节）；成功路径、5xx、超时、连接失败路径**仍然缺**；「字节级」这一点在所有路径上仍然缺 |
| 上游错误响应体原文 | **4xx 拒绝路径上已解决**；`UpstreamError`（5xx）与 `UpstreamRateLimit` 也带 `body` 字段但**没有落盘路径**，仍然缺 |

**为什么这是 blocker 而不是 major**：Spec 在 §1.2 花了整整一节做「proposal 的这条支撑已经作废」的核对，理由是同伴独立解决了 L1 的那个缺口。**同一个动作没有对 L2 做**，而 L2 恰恰是 Spec 用来重排优先级的那一层。结论方向不变（L2 仍然最值），但「一个人解决四次点名与两次点名的两个缺口」这句话是错的，用户读到的成本对比因此偏高。一个建立在过期表上的优先级排序，正是这份 Spec 自己在 §1.2 判为不可接受的形态。

**与事实向评审的重叠**：`rejection_capture` 是否在闭包内、写了什么，属于事实核对；**但「它改变了 §1.3 的缺口归属与优先级论证」属于范围**。我按范围报，事实那一路若也报了，按同一条合并。

**顺带**：`~/.local/share/ghc-api-proxy/` 下**没有** `rejected/` 目录（实测），说明该路径自落地以来未触发过或生产上跑的仍是旧 Bun 服务。这不影响判定（代码在闭包内是事实），但意味着这条能力**尚未被真实事故检验过**，Spec 若要引用它，得带上这个限定。

**可信度：可据以行动**（读了 `rejection_capture.py` 全文、`_dispatch` 两个调用点、`errors.py` 的 `normalize_upstream_error` 对四类异常都填 `body`）。

### B3 —— blocker —— §7.4 冻结的「一次搬迁是一个事务」，在 §9.4 推荐的形态下做不到

§7.4 把这条列为「无论选哪种都冻结」：

> **一次搬迁是一个事务。** 三张表的行必须在同一个 writer 事务里插入目标、删除源。

而 §9.4 推荐「独立的按日期分片库文件」，§6 Q1 要求 WAL（「WAL 下读不阻塞写、写不阻塞读」）。**这三者不可兼得。** SQLite 官方 WAL 文档的缺点清单第 2 条：

> "Transactions that involve changes against multiple ATTACHed databases are atomic for each individual database, but are not atomic across all databases as a set."

我另跑了一次探针确认行为面（Python 3.14 / SQLite 3.53.4，`/tmp/sqlprobe2/`）：两个 WAL 库 ATTACH 之后，跨库事务**照常提交、不报错、不降级 journal_mode**——也就是说这条限制**不会以任何错误的形式出现**，它只在崩溃时表现为一半搬过去了、一半还在源库。

Spec 自己给的顺序（「写目标 → 校验目标行数 → 删源 → 提交」）让失效形态是良性的（重复而非丢失），**所以这不是一个设计缺陷，而是一条写错了的冻结条款**：它承诺了一个 SQLite 在这个形态下不提供的保证，并用「否则一次崩溃会留下既没有 blob 也没有 spool 的空洞」当理由。实施者照着做会以为自己拿到了原子性。

**修法**：把这条拆成两句——同库内的搬迁是一个事务；跨库搬迁不是原子的，靠「写目标 → 校验 → 删源」的顺序把失效收敛成重复，并在归档批次上记一个 `complete` 标记，重启时按标记回收半截批次。同时把这条代价写进 §9.4 的选项表（现在那张表只写了「`include_archived` 要 attach 多个库」这一条代价，漏了原子性这条更重的）。

**严重度：blocker。** 一条冻结的、做不到的契约条款，且它正好落在唯一一个「数据可能永久丢失」的动作上。
**可信度：可据以行动**（SQLite 官方文档原句 + 本机探针确认无报错、无降级）。

---

## 3. 有没有镀金：逐项审视

先说判定口径：**「用户没要」不等于镀金**——达成已裁目标必需的东西不算。我按「拿掉它，已裁决的目标还成不成立」来判。

### 3.1 十个 HTTP 端点：不是镀金

见 §1 的追溯。十个全部有出处，且没有一个是「顺手加的」。唯一可议的是 `entries/unpin` 能否并进 `pin`（一个 `pinned: bool` 参数），但动作式路径风格下两个动词更自洽，且幂等语义已在 §5.4 写清。**nit，不建议改。**

值得肯定的一处克制：§5.9 明写「**不推 chunk 级事件**：一次流式请求的 chunk 有数千个，推它们会让这条 WebSocket 变成第二条上游流」。这是主动砍掉了一个显而易见的扩张方向。

### 3.2 十七个配置键（Spec 自称 18）：**是镀金，且与项目立过两次的先例正面冲突**

先说数：§8.2 的表实际是 **17 行**（`enabled`、`db_path`、`levels`、`queue_size`、`write_timeout_s`、`spool_max_bytes`、`blob_level`、`hot_max_bytes`、`hot_max_age_days`、`archive_interval_s`、`archive_path`、`query_workers`、`query_concurrency`、`query_timeout_s`、`limit_default`、`limit_max`、`websocket`），而 §9.2 的论证里写「这一节从 1 个键长到 18 个键」。数字对不上，且这个数字正是那一项待裁的成本依据。（minor，但要改）

真正的问题是立场。本项目**已经立过两次先例，且两次都把理由写进了模块 docstring**：

- `rejection_capture.py`：「**Always on, and derived rather than configured.** These are supposed to be rare; the run where one first happens is the run whose evidence is wanted, and a switch that has to be turned on beforehand is a switch that is off when it matters. `config.example.yaml` has no key for this, and **inventing one would put a decision in the operator's hands that they can only get wrong in one direction**.」
- `rejected_requests_dir()`：「Derived rather than configured, for the same reason as `tokenization_state_path`: the spec names no key for it, and one invented here would be a decision the operator did not ask to make.」
- `request_log_file.py` 同形（无键，派生路径，`KEEP_DAYS = 14` 写死）。

`260821-structured-logging-design.md` §4.2 已经把这条先例总结为「**派生而不是发明配置键**」，并据此决定通用日志文件不设配置键。**Spec 没有引用这条先例，也没有说明取证系统为什么例外。**

加上一条硬成本：`ProxyConfig` 是 `extra="forbid"`（`schema.py:56`/`381` 实测），所以**每一个新键都必须同时进 `schema.py` 与用户亲笔的 `config.example.yaml`**。17 个键等于向用户的亲笔文档提交 17 行需要他逐个理解并接受的调参面。而其中至少 9 个（`queue_size`、`write_timeout_s`、`spool_max_bytes`、`blob_level`、`query_workers`、`query_concurrency`、`query_timeout_s`、`limit_default`、`limit_max`）是**没有任何操作者需求驱动的内部调参**——它们的默认值是这份 Spec 自己拟的，也没有任何场景说明操作者何时会想改。

**我的主张：键表砍到 3 个以内，其余全部派生为常量。**

| 保留 | 理由 |
|---|---|
| `history.enabled` | **已经在人写文件里**，不是发明的。接上它是兑现一个已有的键（见 §9.1） |
| `history.levels`（或等价的 `l3` 单独开关） | L3 是体积的唯一来源，且它的开关会改变磁盘占用一个量级——这是操作者真会想改的那一类 |
| `history.db_path`（可选） | 与 `rejection_capture` 的先例略有不同：库文件位置在多实例、外挂盘场景下有真实需求。**但若无场景，也该派生** |

其余 14 个写成模块常量，理由与 `rejection_capture.KEEP_NEWEST = 50`、`request_log_file.KEEP_DAYS = 14` 完全同形。**这样 §9.2 那一项也随之消解**——「键放 `history.*` 还是 `forensics.*`」在只有 2–3 个键的时候不成其为分叉。

**严重度：major。** 它不改变功能，但它把一份 Spec 变成了需要用户逐行审阅并写进亲笔文档的东西，而项目已经两次决定不这么做。
**可信度：可据以行动**（三处 docstring 原文 + `extra="forbid"` 实测 + 结构化日志设计已独立得出同一条）。

### 3.3 十个 Prometheus 指标：**是镀金**

全项目现存的 Prometheus 指标是 **2 个**（`TRANSLATION_LOSSES`、`ATTRIBUTION_LINES_STRIPPED`，`src/app/observability/metrics.py`，实测 `rg` 全仓仅此两处定义）。Spec 为一个子系统提出 **10 个**——是全项目现有指标面的 5 倍。

按「拿掉它，已裁目标还成不成立」筛：

| 指标 | 判定 |
|---|---|
| `forensic_l1_dropped_total`、`forensic_l2_dropped_total`、`forensic_l3_chunks_dropped_total` | **必需**。§4.2 说「记录看着完整但其实丢过东西是本 Spec 最不能接受的形态」，而 I4 要求缺席可读——丢弃计数是这条纪律在指标面的唯一载体 |
| `forensic_l1_written_total`、`forensic_l2_written_total`、`forensic_l3_chunks_written_total` | 可砍。写入条数从表里 `COUNT(*)` 就有，且没有任何判据依赖它 |
| `forensic_queue_depth`、`forensic_spool_bytes`、`forensic_hot_bytes` | `hot_bytes` 保留（§7.3 的告警条件直接读它）；另外两个是内部状态，Gauge 还要额外的采样接线 |
| `forensic_archive_runs_total` | 保留（§7.3 的告警判据是「runs 在增长而字节数不降」，需要它） |
| `forensic_query_seconds`（按 endpoint 分标签的 Histogram）、`forensic_query_pool_saturation` | **砍。** §6 末尾自己写了「这是一个检验，不是一道门」，而这两个指标是给那个检验用的常驻仪表。一次性的 p99 对照用探针做即可，不需要在生产上常驻一个分标签 Histogram |

建议保留 5 个：三个 dropped、`hot_bytes`、`archive_runs_total`。**严重度：major**（不是因为指标贵，而是因为它是「为一个还没跑起来的子系统预建观测面」这一类扩张的典型形态）。
**可信度：可据以行动**（现存指标数实测；筛选依据逐条对回 Spec 自己的判据）。

### 3.4 `ChunkSpool`：**这一层给 L3 提供了超出 C1 裁决要求的耐久性，代价与 I7 同向冲突**

这是本次评审里我最想让用户亲自看一眼的一条。

**它的收益边界比 §2.4 写的窄。** §2.4 说它存在的全部理由是「按 attempt 合并压缩只有在 attempt 结束时才做得到，而进程被 kill 恰恰发生在结束之前」。但 §3.3 已经把「attempt 收尾」定义成三种结局全覆盖（上游流自然结束、上游撕裂、下游走人），并挂在 `finally` 语义位置上。所以：

- 请求挂死 242 秒然后客户端断开 → 收敛照常触发，spool 不贡献任何东西；
- graceful shutdown 取消在途流 → 收敛照常触发（`_tracked_delivery` 与 `_AccountedStreamingResponse.__call__` 两层 `finally` 已经把这条路证明过了）；
- **只有 `SIGKILL` / 进程崩溃 / 断电** → spool 是唯一还留着那些字节的地方。

**代价是每天百万量级的行插入 + 同量的删除。** 按 Spec 自己的数（§5.6 示例 `chunk_count: 412`；§5.9 说「一次流式请求的 chunk 有数千个」）与实测流量（`requests-20260820.jsonl` 3,305 行/天），每天 spool 的写入是 10^6 量级，且它们**全部落在与查询同一个数据库文件、同一个 writer 队列上**。用户点名的唯一危害是「history 拖慢请求处理」，而 §6 末尾自己把这条约束扩到了写路径（「写路径与读路径都不许在事件循环上碰磁盘」）。spool 不在事件循环上，所以不违反那句话的字面；但它是这套设计里唯一一个把 10^6/天 的写放大引入热库的组件，方向与硬约束相反。

**更关键的是它与 C1 裁决的关系。** C1 裁的是「L2/L3 bounded best-effort，队列满即丢并计数」。spool 的存在，是为 L3 提供「进程被 SIGKILL 也不丢」这一档耐久性——**那比 durable 的 L1 还强**（L1 在队列满超时后是会放弃的，见 §4.1）。**用一个超出裁决要求的手段去实现一个被裁为 best-effort 的层**，这是比例失当的定义。

**替代主张**：在途 chunk 的字节与元数据在**内存**里按 attempt 累积，收尾时一次性压缩落盘（blob + 批量元数据行）。丢失面：进程崩溃时丢掉在途 attempt 的 chunk——而这正是 C1 允许的。内存占用与 `spool_max_bytes` 同量级（Spec 自己给的上界是 256 MiB 未压缩，说明作者接受这个量级），且上界更好实施（一个计数器，不是一张表加一次 `SUM`）。随之消掉的还有：`ChunkSpool` 整张表、`spool_open` 列、§3.5 的 P3 启动恢复、`spool-recovered-at-startup` / `spool-full` 两个 `truncated` 取值、`history.spool_max_bytes` 配置键、`forensic_spool_bytes` 指标。**六样东西，全部由同一个决定支撑。**

**这不是我能替用户裁的**——「崩溃现场的字节值不值这个代价」是产品取舍。我的建议是把它作为 §9 的第七项交回，附上上面这组数。

**严重度：major。**
**可信度：可据以行动**（收敛触发面读了 `_tracked_delivery` / `_AccountedStreamingResponse.__call__` / `_StreamAccounting.finish` 的实际代码；量级用 Spec 自己的数与实测 JSONL 行数）。

### 3.5 §5.1 的十四个过滤器：两个是镀金，且与 §6 Q6 矛盾

见 M6。`has_error_body` 与 `min_attempts` 是「便于直接捞出……」的便利过滤器，没有需求来源，且它们恰好是唯一两个无法在 Q6 的约束下实现的。

---

## 4. 有没有缺：按 Spec 能不能真的动手

### M1 —— major —— §3.4 的观测合同：冻结的方向对，但缺了实施者第一天就会撞上的那件事

任务点名要看这一条。判定：**Spec 冻结的「显式携带」是对的，且它防住了一个真实的静默失效（靠 `__cause__` 摸 `.response.request`）。但它漏了一件实施者立刻会撞上的事，同时高估了另一件的成本。**

**漏的**：当前 `DirectDriver._handle_failure` 发布 `EVENT_ATTEMPT_FAILED` 时，**订阅者拿不到异常对象**。签名是 `await self._publish(EVENT_ATTEMPT_FAILED, context, outcome)`，而此刻 `outcome.error` 还是 `None`（它只在终结分支被赋值）。`attempt.error = str(error)` 确实在 `run()` 里先设了，但那是一个字符串，正是 §2.2 说「不能替代」的那个。所以 §3.4 写的「失败 attempt：归一后的 `PipelineError` 携带 `status_code`/`headers`/`body`……由合同显式带出」，在事件面上**不是「带出来就行」，而是「那条路径上今天连异常对象都没有传递」**。Spec 应当把这句写进去，否则实施者会以为只需加字段。

**高估的**：§3.4 说「这个扩展是 L2 的真实成本」，读起来像是要动一大片。实测不是——`Handler[T]` 的类型参数只在三处被实例化使用：`src/app/pipeline/subscribers/__init__.py` 里的三个 `registry.subscribe(...)`，**且全部挂在 `attempt.prepare` 上**。也就是说 `attempt.succeeded` / `attempt.failed` 今天**一个订阅者都没有**，L2 记录器会是第一个。改动面是：`events.py` 的 `Handler`/`Subscription` 类型、`DirectDriver._publish` 的调用、三个既有 lambda 的签名。**这比 Spec 的措辞给人的印象小一个档**，而这个印象直接影响用户对「L2 先做」的成本判断（见 §5 的优先级建议）。

**可信度：可据以行动**（读了 `direct_driver/base.py` 全文、`events.py` 全文、`subscribers/__init__.py` 的三个注册点）。

### M2 —— major —— 分片 3 要求的「热区上限临时形态」，Spec 里没有任何行为规范

proposal §6.1 的分片 3 明写「L1 落盘 + **热区上限同片交付**」，并要求「分片 3 的上限可以先用最简形态（超限即停写并告警，或先落一个简单冷表），分片 7 再换成正式归档。**这个临时形态必须在分片 3 的说明里写明是临时的**」。

Spec §7.3 只描述了完整形态：三个触发条件全部驱动「归档运行」，而归档运行的定义（§7.3、§7.4）依赖会话选取、跨表事务搬迁、归档批次——**全部在分片 7**。**Spec 里没有任何一句描述那个临时形态的行为**：超限之后到底发生什么？停写 L1？停写 L3？只告警不动作？记录上留什么痕？

按 Spec 的现状，分片 3 无法交付它被要求交付的那一半。**修法**：§7.3 加一小节「归档器就位前的上限行为」，或者按我在 §5 的建议——把上限从分片 3 拿掉（有独立理由，见 §5）。

**可信度：可据以行动**（proposal §6.1 原文 vs Spec §7.3/§7.4 全文对照）。

### M3 —— major —— 全文没有 schema 版本与迁移策略

Spec §2 用一整段说明为什么不复用 `HistoryEntry`：「`writer._insert` 以无列名的 14 个位置参数写整行、按固定下标反序列化，**加列要同步改写所有 positional SQL 与 reader**」。它准确诊断了旧实现的病，**然后对新实现只字不提免疫措施**。

而分片化交付**必然多次改表**：分片 3 建 L1；分片 4 建 L2（其中 `chunk_count`/`chunk_bytes`/`chunks_blob`/`blob_codec`/`blob_bytes`/`spool_open` 六列在分片 6 之前无写者）；分片 6 建 L3 与 spool；分片 7 加 `archived_batch` 的实际语义与归档库；分片 9（按 proposal）还要动配置。用户已有的取证库在这期间**一直在写真实流量**——按 §9.1 若接上开关，升级后默认就开始记录。

缺的是：schema 版本号放哪、迁移在哪一步跑（启动时？writer 首次打开时？）、版本不匹配时的行为（拒绝启动？只读降级？自动迁移？）、以及**旧版本进程遇到新库怎么办**（systemd 回滚是这个项目的现实场景）。

**至少要一句话的策略**，例如「`PRAGMA user_version` + 启动时按版本号顺序跑幂等的 `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN`，只加不改不删」。这已经足够让实施者动手，也符合项目反对不成比例基础设施的立场。

**可信度：可据以行动**（Spec 全文 `rg` 无 `migration` / `user_version` / `schema_version` / `版本` 相关条款）。

### M4 —— major —— L1 字段表缺 `losses`，且 Spec 的事实基线已落后 22 个提交

§2.1.1 写「实测一条 `requests-20260821.jsonl` 记录的键恰为 `at` + `status` + `RequestLine` 的全部 **28** 个字段」。HEAD 上 `RequestLine` 有 **29** 个字段——`a07f74a`（2026-08-21 18:03:55，`feat: report what a translation lost`）加了 `losses: tuple[dict[str, str], ...]`。Spec 文件 mtime 是 18:24，即这一列在 Spec 写作期间落地。

后果不只是数字差一：**`losses` 恰恰是排障高价值字段**（「这次请求的哪个字段没能跨过翻译层」），它已经进了 JSONL、进了终端行、也进了 `TRANSLATION_LOSSES` 指标，**唯独没进 L1 表**。按 §1.4 的纪律（「任何新字段都加在 `RequestLine` 上」），L1 应当自动继承它。

更一般的问题：Spec 开头写「本文对现状的每一条陈述都在 2026-08-21（HEAD `be63418`）的工作树上核对过」。`be63418` 提交于 13:21，距当前 HEAD 有 **22 个提交**，其中至少三个改了 Spec 直接引用的符号（见 M5 与本条）。**「事实基线」这个声明本身需要带上「核对时刻」而不是只带提交号**，否则读者会以为它是当前的。

**可信度：可据以行动**（`git log -S`、两个提交的字段计数实测）。

### M5 —— major —— §3.5 的 P1 已经被同伴解决，分片 0 因此只剩两件与取证系统无因果的清理

§3.5 P1 写：「**非流式路径有洞**：`_serve` 捕获 `_dispatch` 抛出的 `BaseException` 后只从 active registry 删除再 `raise`，不记录……**补洞后 I1 才成立。**」

`9557700`（2026-08-21 13:34:37，`fix: account for a request that leaves the buffered path by raising`）已经补了。HEAD 上 `_serve` 的 except 分支是：

```python
except BaseException as failure:
    chain.active_requests.remove(trace.request_id)
    trace.status_override, trace.detail = _aborted(failure)
    _log_completion(chain, trace, None, bytes_out=trace.received or None)
    raise
```

代码注释还逐字记了 Spec 引用的那次实测（「a probe raising from `Request.body()`, and an upstream answering 200 with a body `response.json()` cannot parse, each produced zero `app.request` records」）与幂等性论证（「Exactly-once is structural here rather than guarded by a flag」）。**这个提交比 Spec 的基线 `be63418` 晚 13 分钟，比 Spec 的 mtime 早 5 小时。**

**范围后果**（这才是我报它的理由）：proposal 分片 0 的三件事，现在只剩两件——「测试库改落 `tmp_path`」和「取证库独立文件名」。而后者已经由 §8.2 的默认值（`forensics.db`）在 L1 落地那一刻自动满足，不需要单独一片；前者是对**旧链路** `history.db` 的缺陷修复，与取证系统**没有因果关系**（新库是另一个文件）。

**主张：分片 0 应当解散。** 「测试库改落 `tmp_path`」提成一个独立的小提交立刻做掉（它是既有缺陷，且每跑一次测试都在恶化），不要挂在这个工程的关键路径上；取证库独立文件名并进 L1 那一片。这样这个工程的第一片就是真正产出能力的那一片。

**与事实向评审的重叠**：P1 是否已修属于事实；**分片 0 是否还成立属于范围**。

**可信度：可据以行动**（`git show be63418:` 与 HEAD 逐行对照 + `git log -S` 定位提交）。

### M6 —— major —— §5.1 的两个过滤器与 §6 Q6 直接矛盾，跨归档库的 cursor 未定义

Q6 冻结：「强制 `limit`、**按索引列过滤**、**无全表扫描**」。§2.1 的索引是 `(started_at DESC)`、`(session_id, started_at DESC)`、`(status, started_at DESC)`、`(resolved_model, started_at DESC)`、`(pinned)`、`(archived_batch)`；§2.2 的索引是主键、`(request_body_digest)`、`(spool_open)`。对照 §5.1 的十四个过滤器：

| 过滤器 | 能否满足 Q6 |
|---|---|
| `session_id` / `status` / `resolved_model` / `since`/`until` / `pinned` | 有索引，OK |
| `agent_id` / `status_code` / `requested_model` / `inbound_format` / `path` | **无索引**。作为 `started_at` 索引扫描后的残余过滤可以接受（有 `limit` 兜底），但 Q6 的字面说的是「按索引列过滤」——需要 Spec 明说「非索引列只作为已排序扫描上的残余过滤」 |
| `min_attempts` | 同上，且它的选择性通常很低（绝大多数请求 `attempts=1`），扫描量不可控 |
| `has_error_body` | **做不到**。`error_body` 在 L2 上，L2 没有对应索引，且这是一个跨表存在性判定；在 Q6 的约束下它要么全表扫 L2，要么在 L1 上冗余一列 |
| `status` / `status_code` 传数组 | 多值使 `(status, started_at DESC)` 索引退化为多次扫描后归并，与 cursor 分页叠加后语义不平凡 |

另外：§5.0 的 cursor 是 `(started_at, id)` 的编码，排序恒为 `started_at DESC, id DESC`。**`include_archived = true` 时要跨多个归档库合并分页，Spec 没有定义这种情况下 cursor 的稳定性**（归档批次在翻页期间被新增会怎样？跨库的 `id` 是否全局唯一——是 `uuid4`，所以唯一，但排序归并需要每库各持一个游标）。

**修法**：砍掉 `has_error_body` 与 `min_attempts`（无需求来源，见 §3.5）；Q6 改写成「排序恒走索引；非索引列只作为该扫描上的残余过滤，`limit` 是唯一的量级保证」；`include_archived` 的分页语义补一句（最简单的正确答案是：跨归档查询不支持 cursor，只支持一次性 `limit`，并在 `meta` 里说明）。

**可信度：可据以行动**（索引清单与过滤器清单逐条对照）。

### M7 —— major —— §9.6 与结构化日志设计 §4.1 是同一个问题的两次提问，选项集与倾向都不同

- Spec §9.6：「L1 与 `requests-*.jsonl` 是什么关系」，三选项：**并存** / 取证库取代 JSONL / JSONL 降级为溢出兜底。倾向**并存**。
- `260821-structured-logging-design.md` §4.1（分叉 2）：「通用日志文件与既有 `requests-*.jsonl` 的关系」，三选项：并存 / 合并 / **分层**（`requests-*.jsonl` 文件合同不变，但改由订阅结构化流的 sink 写）。倾向**分层**。

两份文档会同时摆到用户面前，问的是同一个对象（`requests-*.jsonl` 的去留与写者），**给的选项集不重合，倾向也不同**。用户若先裁 Spec §9.6「并存」，再读结构化日志那份，会发现「并存」在那边对应的是被判为次优的那一项；反过来若先裁「分层」，Spec §9.6 的三个选项里**没有一个能承接它**。

而且有顺序依赖：**「谁来写 `requests-*.jsonl`」由结构化日志那份决定，L1 的分量由这个答案决定**（Spec §9.6 自己说「这条裁决影响实施顺序」）。所以结构化日志分叉 2 是 Spec §9.6 的上游，不能倒过来问。

**修法**：把两处合并成一个裁决项，放在结构化日志那份里（因为它才是 `requests-*.jsonl` 写者的归属地），Spec §9.6 改成引用它并说明「无论怎么裁，L1 都取同一份 `RequestLine`；裁决只影响 L1 要不要接管 JSONL 的落盘职责」。

**可信度：可据以行动**（两份文档原文对照）。

### M8 —— major —— 分片 9 才给 pin 入口与配置键，而归档在分片 7 就上线

proposal §6.1：分片 7 是「会话聚合 + 归档机制 + `/sessions/*`、`/archives/*`」，分片 9 才是「`/history/ws` 实时推送、**`pin`/`unpin`**、**配置键**」。

Spec §7.5 明写 pin 的语义是「免于归档」，§7.3 明写「永不搬迁……任何 `pinned = 1` 的记录所在的会话」。**于是分片 7 到分片 9 之间，归档器在跑、`pinned` 恒为 0、没有任何入口能置位**——正在排查的记录会被搬走。这正是 r2 评审 N2 指出过的形状（「设计依赖一个用户无法触发的机制」）的第二次出现，只不过这次它藏在分片顺序里而不是藏在缺失的入口里。

配置键同理：分片 3 要热区上限（`hot_max_bytes` / `hot_max_age_days`）、分片 6 要 `spool_max_bytes`、分片 7 要 `archive_*`，而配置键整体排在分片 9。

**修法**：`pin`/`unpin` 两个端点并进分片 7（成本是两条 `UPDATE` 加两个端点壳子）；配置键跟着各自的消费者走（若采纳 §3.2 的砍键主张，这个问题基本消失）。**Spec 应当在 §8.2 的表里加一列「哪一片落地」**——它现在没有任何一处把键与分片对上。

**可信度：可据以行动**（proposal §6.1 分片表 vs Spec §7.3/§7.5/§8.2）。

---

## 5. 分片可行性：十片逐片判「交付后有人能用它回答一个真实问题吗」

| # | proposal 的内容 | 自足？ | 判据 |
|---|---|---|---|
| 0 | 前置三件 | **应当解散** | 第三件已由 `9557700` 完成（M5）；第二件由 §8.2 默认值自动满足；第一件与取证系统无因果，应独立提交。proposal 自己也承认「本身不产出可用能力」 |
| 1 | 结构化日志承载 | 自足（但归 `260821-structured-logging-design.md` §6.1 管，且那份自己诚实标注：交互式终端下本片不生效） | Spec 不覆盖 |
| 2 | TUI 改消费者 | 自足 | 同上 |
| 3 | L1 + 热区上限 + 路由模块 + `entries/list`/`get` | **半自足** | 能答的问题（「哪条请求出事、哪个模型、几次 attempt」）**JSONL 已经能答**（§1.2 自己说的）。真实增量是「按会话/模型/状态过滤着查」+ provisional 行（进程被 kill 时的痕迹）。这是真的但比表述小。**且「热区上限」按 Spec 无法实施**（M2） |
| 4 | L2 | **自足，且是十片里价值密度最高的** | 「我们发了什么、上游原话是什么」——4xx 拒绝路径已被 `rejection_capture` 覆盖一半（B2），但成功路径、5xx、超时、以及**字节级**在所有路径上仍然只有 L2 能答 |
| 5 | `replay` | 自足，依赖 4 | 「上游对这个 body 现在还怎么反应」。需求盘点里手写 curl 探针出现三次 |
| 6 | L3 | 自足 | 「上游什么时候回的、中间停了多久」——`downstream-keepalive-defect.md` 那句「未坐实」只有它能变成可核实 |
| 7 | 会话聚合 + 归档 + `/sessions/*`、`/archives/*` | **被待裁项阻塞** | §9.4（归档物理形态）不裁就动不了；且 §7.4 的冻结条款在推荐形态下做不到（B3）。**pin/unpin 必须并进来**（M8） |
| 8 | `export-cassette` + codec 提升 | 自足，依赖 4 与 6 | 「从生产流量派生固件」。codec 提升要把 `tests/int/recorded/cassettes.py` 变成可安装模块，影响所有录制测试——工作量被 Spec 一句话带过，实际不小 |
| 9 | ws + pin/unpin + 配置键 | **不自足，且顺序错** | pin 必须提前（M8）；配置键必须跟消费者走（M8）；剩下只有 `/history/ws` 一件，它自足但价值最低（实时推送在一个块级交付的代理上，观众只有 TUI，而 TUI 有自己的 `ActiveRequestRegistry`——见结构化日志设计 §3.4「当前的 footer 其实不需要读日志流」） |

**结论**：十片里真正自足且不被阻塞的是 4、5、6、8；3 是半自足且缺规范；7 被待裁项挡住；0 应解散；9 应拆散并入别处；1、2 归另一份文档。

---

## 6. 优先级：Spec §1.3 排对了一半，分片顺序应该跟着改

**§1.3 的排序方向是对的**：它明确写了「实施顺序上，**L2 的价值密度最高**」，也写了「L1 仍然要先落，但理由是**结构性的**……**不是因为它更急**」。这两句都成立。

**但它停在了「说明理由变了」，没有动分片顺序**——§1.3 最后一句是「这与 proposal §6.1 的分片表不矛盾（那张表里 L2 就排在 L1 之后一片），但**它给出的理由变了**」。任务问的正是这里：**应不应该跟着改？**

**我的主张：应该改，改法如下。**

| 顺序 | 内容 | 理由 |
|---|---|---|
| 立刻（不占片） | 测试库改落 `tmp_path` | 既有缺陷，每跑一次测试都在恶化，与本工程无因果（M5） |
| **P1** | **L1 最小形态**：三张表建起来（L1 完整、L2/L3 空壳）、provisional + 终态两次写、`entries/list` + `entries/get`、新路由模块 | 结构性前提：L2 的行需要父行、查询面需要一张能过滤的表。**但要砍到最小**——不含热区上限（见下）、不含 pin（那时还没有归档）、不含 `include_archived` |
| **P2** | **L2 + 观测合同扩展** | 价值密度最高。且成本比 Spec 的措辞低一档：`attempt.succeeded`/`attempt.failed` 今天零订阅者，改动面是 `events.py` 类型 + `_publish` 调用 + 三个既有 lambda 签名（M1） |
| P3 | `replay` | 依赖 P2，增量极小，替代需求盘点里出现三次的手写 curl |
| P4 | **L3 + 容量上限同片** | 见下 |
| P5 | 会话聚合 + 归档 + `pin`/`unpin` + `sessions/*`、`archives/*` | 依赖 §9.4 裁决 |
| P6 | `export-cassette` + codec 提升 | 依赖 P2 + P4 |
| P7 | `/history/ws` | 价值最低，且它唯一的消费者（TUI）当前不需要它 |

**其中一条是对 proposal 既有结论的翻案，我给理由**：proposal r2 轮采纳的评审发现是「容量上限必须与首次持久化同片，否则存在『默认写盘、无任何上限』的中间态」。**那条结论在 r2 的模型下成立，在当前模型下不成立**——它的隐含前提是「首次持久化就会带来体积问题」。而实测：`RequestLine` 落 JSONL 是 **0.9 KB/请求**（结构化日志设计 §1.5 实测），流量 ~3.3k/天，即 **~3 MB/天**；L1 表比 JSONL 更紧凑（定长列、无键名重复），一年的 L1 行也就几百 MB。**体积的唯一来源是 L3 的 blob**（§2.3 的样本是单请求 17 KB 与 7.4 KB 压缩后，即 L3 比 L1 大 10–20 倍）。

所以正确的绑定是「**容量上限与 L3 同片**」，不是与 L1 同片。这样做同时消掉 M2（分片 3 那个没有规范的临时上限形态不再需要存在），也让 P1 真正变小、变快、变得能独立验收。

**可信度：可据以行动**（0.9 KB/请求与 3,305 行/天是实测；L3 的相对量级用 Spec 自己的压缩样本）。**这一条是我对 proposal 既有结论的推翻，请连同上面的数一起看，不要只看结论。**

---

## 7. §9 的六项待裁：逐项判「建议站不站得住」「用不用问」

### §9.1 死开关 —— 建议成立，但作用域没定义

「接上」的建议站得住，理由 Spec 给对了（既然裁了全量记录，一个真能关掉的开关比装饰性开关有用），而且它与 §3.2 的「派生而非发明键」先例不冲突——**`history.enabled` 已经在用户亲笔文件里，接上它是兑现而不是发明**。

**缺的是作用域**：接上之后，`--no-history` 关掉的是哪些东西？只关取证库？还是连 `requests-*.jsonl` 与 `rejection_capture` 一起关？后两者当前是「always on, derived rather than configured」的立场（`rejection_capture` docstring 逐字写了理由）。**若总开关覆盖它们，等于推翻那条立场；若不覆盖，用户会以为 `--no-history` 关掉了所有历史记录而实际没有。** 这一项必须在选项里说清，否则用户裁的是一个语义不明的开关。（major 级的补充，附在 §9.1 上）

### §9.2 配置键放哪 —— **问题问偏了**

如 §3.2，真正该问的是「要不要 17 个键」。若砍到 2–3 个，「放 `history.*` 还是 `forensics.*`」不成其为分叉（直接放 `history.*`，与人写文件已有的那一节连续）。**建议把这一项重写成「键表要不要砍到 3 个以内，其余派生为常量」**，并附上 `rejection_capture` / `request_log_file` 两次先例的原文。

### §9.3 旧链路去留 —— **不用问，已经答了**

三条独立依据都指向「不动」：

1. 项目记忆「不得擅自删除已实现的功能」——Spec 自己引了（「不是我该判的」）；
2. 用户 2026-08-20 的八项裁决里从未涉及旧链路；
3. 本次工程范围是新链路，旧链路不服务生产，动它不产生任何交付价值。

Spec 自己的建议就是「完全不动」，**而「不动」是默认值**。把一个默认成立的不动作包装成裁决项，会占用用户的注意力预算，也会让读者以为这里有一个真实的取舍。**建议：从 §9 移出，写进 `deferred.md` 一行。**（minor）

### §9.4 归档物理形态 —— 真分叉，建议方向合理，但**选项代价表漏了最重的一条**

它确实是真分叉，且 Spec 发现「proposal §3.4 说列入 4.6，而 §4.6 实际只列了三项，它掉了」——这个考古做得好。

建议「独立的按日期分片库文件」的理由（热库始终小、可整体移走）成立。**但代价表只写了「`include_archived = true` 要 attach 多个库」，漏了 B3 那条**：WAL 下跨 attached 库的事务不是整体原子的，所以「搬迁的原子性」在这个选项下要靠顺序 + 批次标记来补，而不是靠事务。**这条代价必须进选项表**——它是三个选项之间最实质的差别（同库冷表没有这个问题）。

### §9.5 replay 记不记 —— 真分叉，建议站得住

「记」的理由（不留痕的旁路 + 「我刚才重放的那次上游回了什么」正是下一步要查的）成立，反对理由（污染统计口径）也被诚实列出了，且给了 `record` 默认值的对应改法。**这一项的呈现质量是六项里最好的。**

一处补充：§10.7 说 replay 的并发限制「建议复用 §6 Q7 的并发闸」。**那个闸的语义不对**——Q7 是查询侧线程池的并发上限，而 replay 是一次真实上游调用（消耗配额、走限流器、可能重试）。它应当受 `RateLimiter` 与一个独立的小并发上限管，不是查询闸。（minor）

### §9.6 L1 与 JSONL 的关系 —— 真分叉，且是六项里最重要的一项，但**问法与另一份文档打架**

见 M7。这一项本身站得住（它确实决定 L1 的分量），Spec 的建议「并存，但 JSONL 不再扩字段」也有道理。**但它必须与结构化日志设计 §4.1 合并成一个问题**，且顺序上后者是上游。

---

## 8. §10 的十条：真缺口还是过度解读

| # | 判定 |
|---|---|
| 10.1 完成记录已落盘 | **真缺口，且是整份 Spec 最有价值的一节**。它做了「proposal 的支撑作废了吗」的核对并改写了定位。唯一的问题是同样的动作没有对 L2 做（B2） |
| 10.2 `_Trace.failed` 已不存在 | 真（HEAD 上确为 `status_override: LogStatus \| None`）。已在 §2.1 处理，列进「缺口」略冗余但无害 |
| 10.3 分片 1 没有 Spec 可依 | **结论对了一半，且已过期**——见下 |
| 10.4 归档物理形态在文档内部掉了 | 真。考古准确 |
| 10.5 `message.id` 只对流式路径成立 | **真，且是被低估的一条**。它决定了任何「服务端记录 ↔ 客户端 transcript」join 脚本的正确性，非流式流量上会静默匹配不到。建议把这个限定同时写进 §2.1 那一行的说明里（现在只写了「见 §10.5」） |
| 10.6 压缩依赖归属 | 真，且已解决（标准库 `compression.zstd`）。写得干净 |
| 10.7 端点副作用边界 | 真。且它诚实标注了「这几条是我拟的，不是裁决过的，评审时应当重点看」——我看了，`replay` 用当前凭据不重放旧凭据是对的；`export` 缺字段就 409 不补值是对的；`path` 缺省只返回不落盘是对的。**唯一要改的是并发闸的归属**（见 §9.5 补充） |
| 10.8 六个钩子点 | 真，且定位准确（不实现但留接缝） |
| 10.9 `2604-rewrite` 的三处引证 | 真。三条改读方式都对，尤其 `busy_timeout` 那条——「对不上的可能恰恰是笔记」这个判断是对的，且 §4.3 按新 writer 自己的形态重判了 |
| 10.10 TUI 历史面板 | 真。且与结构化日志设计 §3.4 一致（那份实测「当前的 footer 其实不需要读日志流」，真正需要的是历史面板） |

**没有一条是过度解读。** 十条都指向真实的文档缺陷或事实变化。

### 10.3 的结论要改

§10.3 说：「本文按任务范围没有覆盖结构化日志改造，**不是判它不需要 Spec，而是它需要一份自己的**」。

**「需要一份自己的」这个判断对，但「还没有」这个隐含前提已经不成立。** `.dev/docs/history/reports/260821-structured-logging-design.md`（43 KB，2026-08-21 13:35）已经把那份的实质内容写出来了：现状测绘（§1）、落地机制与三个实测出来的坑（§2）、TUI 消费形态（§3）、文件 sink 的完整合同（§4：路径/格式/轮转/写失败/flush）、兼容面与 13 处受影响测试（§5）、分片与顺序不可交换的理由（§6）、人眼验收清单（§7）、三个待裁分叉（§8）、三个风险（§9）。

**所以正确的结论是**：那份材料已经存在，缺的是「把它冻结成 spec」这个动作，以及**它的三个待裁分叉与本 Spec 的 §9.6 合并**（M7）。§10.3 现在的写法会让读者以为分片 1、2 还处在「没人写过」的状态，从而低估已完成的工作、也错过 M7 那个冲突。

**并进这一份吗？我的判断：不并。** 两者的行为面确实不共享契约（一个是日志承载与终端呈现的分层，一个是取证记录的数据模型与查询面），且结构化日志那份有一个本 Spec 完全没有的验收维度——**人眼验收**（终端逐字节对照、时钟时区、能力降级三种路径）。把它并进来会让这份 Spec 从「机器可查的行为契约」变成两种验收方式混装的东西。**但两份必须共享一个裁决面**（§9.6 / 那份的分叉 2），且顺序上那份在前。

---

## 9. 其余发现（minor / nit）

| # | 严重度 | 发现 |
|---|---|---|
| m1 | minor | **§5.0「未知字段 400」是对的判断，但它与 `session_id: null` 的语义有实施陷阱。** §5.1 写「传 `null` 显式筛『无会话』的记录」，而缺席表示「不过滤」。Pydantic 的默认行为分不清「字段缺席」与「字段为 `null`」——必须用 `model_fields_set` 或一个显式 sentinel。这正是 I4「缺席可读」在查询面上的镜像，值得在 §5.0 写一句 |
| m2 | minor | **§5.9 的 `hello.since` 语义未定义。** 服务端发 `{"type":"hello","version":1,"since":"<ISO>"}`——`since` 是「本连接从这一刻起推送」还是「会补发这一刻之后的记录」？后者需要一次查询，与 Q5「读路径一条都不许进 writer 队列」以及推送的 best-effort 定位都有关 |
| m3 | minor | **§9.2 里「18 个键」与 §8.2 实际的 17 行不一致**，而这个数字是那一项的成本依据 |
| m4 | minor | **`entries/unpin` 可并入 `pin`**（一个 `pinned: bool`）。不建议改，动作式风格下两个动词更自洽，记录在此说明已考虑过 |
| m5 | minor | **§2.2 的 `chunk_count`/`chunk_bytes` 默认 0 与 I4 冲突。** §2.3 说空 attempt 是 `chunk_count = 0` + `chunks_blob` 为 `NULL`，而 L3 被关掉（`history.levels` 不含 `l3`）时也是 `chunk_count = 0`。「没记 chunk」与「确实没有 chunk」在这两列上同形——正是 I4 要防的那件事。`chunk_count` 应当可空，或另有一列说明 L3 当时开没开 |
| m6 | minor | **§7.3 的「热区超限时按 `last_at` 从旧到新取够为止」与「永不搬迁 pending/pinned」叠加后可能无限循环**：如果热区被 pending 记录撑爆，归档器每轮都选不出可搬的会话。Spec 说「告警而不是强行搬」是对的，但没说归档器此时**要不要退避**——不退避就是每 `archive_interval_s` 跑一次全表选取，本身成了 I7 的负担 |
| n1 | nit | §5.0 那句「本 Spec 落地后那句话要一并更新」应改为实施动作的表述（见 §1 末） |
| n2 | nit | §2.1 `attempts` 行写「与 L2 行数应当一致；不一致本身是线索」——但流式请求只有最终 attempt 会产生 chunk，前序失败 attempt 也有 L2 行，所以「一致」是对的；不过 §5.1 的 `exchanges_missing = attempts - exchange_count` 在 L2 被丢弃**之外**还有一个来源：`history.levels` 关掉 L2 时它恒等于 `attempts`。同 m5，属于同一族问题 |

---

## 10. 判定

**Spec 不能按现状冻结并据以进入实施。** 需要的动作按代价从小到大：

1. **改冻结声明**（B1）：把 §7.3–§7.5、§8.2、§5.8 划出冻结面，注明「待 §9.2/§9.4 裁决」。**这一条不改，冻结这个词就是错的。**
2. **改 §7.4 那条做不到的条款**（B3），并把原子性代价补进 §9.4 的选项表。
3. **按 HEAD 重算 §1.3 的缺口表**（B2）与 §3.5 的 P1（M5），据此解散分片 0、重排优先级（§6 给了一版）。
4. **把三处比例失当的东西交回用户而不是当成已定**（§3.2 配置键、§3.3 指标、§3.4 ChunkSpool）——尤其 ChunkSpool，它是唯一一个会改变运行时形状的。
5. **补三处让实施者能动手的信息**：schema 迁移策略（M3）、分片 3 的临时上限行为（M2 —— 若采纳 §6 的重排则自动消失）、`attempt.failed` 事件上今天连异常对象都没有（M1）。
6. **把 §9.6 与结构化日志设计的分叉 2 合并**（M7），并按那份在前的顺序提交给用户。

做完 1–3 与 6，这份 Spec 的 §2–§6 就可以真正冻结，P1/P2 两片可以立刻开工。4、5 可以与实施并行推进，不必挡在前面。

**最后说一句它做对了什么**，因为这些地方在下一轮修订里最容易被误伤：I4「缺席可读」贯穿了整份文档并真的改变了字段设计；I6「记录点在解析之前」附带写清了为什么不能在 `BlockAssembler` 之后再记一份；§2.5 主动声明脱敏立场是推定并列出供否决；§5.0 拒绝为这些端点单设认证；§6 的七条把用户点名的那一条硬约束落成了可执行的规范而不是口号；§10 十条全部是真缺口。这几处不要在修订中被顺手改掉。

---

## 附：本轮核查记录

只读。未修改任何源文件或被评审文档。

**读**：`spec.md` 全文 825 行；`proposal.md` 全文 497 行；`reports/260821-structured-logging-design.md` 全文 469 行；`reports/260820-forensic-demand-audit.md`、`reports/260820-review-history-forensics-scope-r2.md` 全文；`reports/` 下其余四份按需检索。

**读代码**（HEAD `1b0cdd2`）：`src/app/pipeline/direct_driver/base.py` 全文、`src/app/pipeline/events.py` 全文、`src/app/pipeline/subscribers/__init__.py`、`src/app/server/pipeline_app.py`（`_serve` / `_dispatch` / `_StreamAccounting` / `_AccountedStreamingResponse` / `_counted_upstream` / `_tracked_delivery`）、`src/app/observability/rejection_capture.py` 全文、`src/app/observability/request_log.py`（`RequestLine` 字段）、`src/app/observability/metrics.py`、`src/app/model_provider/ghc_client/errors.py`、`src/app/server/ops_routes.py` 头部、`src/app/config/schema.py`（`HistoryConfig` / `extra="forbid"`）、`src/app/history/sqlite/writer.py`（符号存在性）、`docs/.human-controlled/MAIN.md` 第 38 行、`docs/.human-controlled/config.example.yaml` 的 `history:` 与 `hooks:` 两节。

**Git 实测**：`be63418` 是 HEAD 的祖先，相距 22 个提交；`9557700`（13:34）补了非流式终结器，晚于 Spec 基线 13 分钟；`a07f74a`（18:03）加了 `RequestLine.losses`，`RequestLine` 字段数 28 → 29；`git show be63418:src/app/server/pipeline_app.py` 确认基线上 except 分支确实只有 `remove` + `raise`。

**探针**：`/tmp/sqlprobe2/`（一次性，可重跑）——两个 WAL 库 ATTACH 后跨库事务照常提交、不报错、journal_mode 不降级，Python 3.14 / SQLite 3.53.4。配合 SQLite 官方 WAL 文档缺点清单第 2 条原句，支撑 B3。

**未验证、按二手材料采信的**：`260821-structured-logging-design.md` 里的 structlog 探针结果与 0.9 KB/请求的落盘量级（该报告自标【实测】且脚本路径可重跑，本次未重跑）；`requests-*.jsonl` 的行数（Spec 与该报告两处独立给出且互相吻合，本次未重数）。这两样支撑 §6 的优先级建议，取信档位：**足以据此排序，若要据它做容量承诺则应重测**。

**来源**：[SQLite WAL 文档](https://www.sqlite.org/wal.html)

# 评审：取证记录能力方案的「意图与范围」（260820）

评审对象：`/home/xp/src/ghc-api-proxy-py/docs/agents/history-forensics/proposal.md`
评审角度：意图与范围。**不逐条核事实**（另有一路在核），但为判断范围而必需的代码事实我自己实测了，逐条给 `file:line`。
纪律：只读。本次未修改任何源文件、未修改被评审文档、未执行任何写操作，唯一落盘产物是本文件。

严重度口径：**blocker** = 按现状裁决会得到错误结论或无法裁决；**major** = 会显著改变用户的选择或让某个选项被误判；**minor** = 影响文档可信度或后续返工成本；**nit** = 措辞与整洁。
可信度口径：**可据以行动** / **仅是倾向** / **仅存档**。

统计：blocker 2、major 9、minor 7、nit 2，合计 20 条。逐条见第 6 节汇总表。

---

## 0. 先说结论

这份方案的调查质量高，事实层扎实，「不采纳的选项」一节的存在本身值得肯定——项目规则要求 `record-what-not-adopted`，它做到了。我的批评集中在**这一节被用来消化掉了本该交给用户的分叉**，以及**分叉 A 的推荐理由把两条不同的论证链捆在了一起**。

一句话概括我的判断：**方案对「增强调研能力」的解读方向是对的，但它把「用户已经写下来的东西」和「需求盘点自己点名的最便宜修法」都排除在选项之外了**，用户读完这份文档做出的裁决，会在他没有察觉的情况下否掉他自己亲笔写过的产品面。

---

## 1. 有没有跑偏——「增强调研能力」的解读

### 1.1 现有解读站得住，但它回答的是任务的后半句，不是前半句

任务原话两段：「**接上 history 功能**」+「用户希望**增强调研能力**」。

方案对后半句的解读（取证记录 + 消费面）**站得住，且有硬证据**：`260820-forensic-demand-audit.md` 是对已发生取证动作的盘点而非发明需求，缺口按被点名次数排序，第 2 名「服务端完成记录」有现成雏形。这条论证链我认可，**可信度：可据以行动**。

问题在前半句。「接上 history 功能」在方案里被实际执行成了：**不接现有 history 功能，只复用它的存储层，另写一个 recorder**（§2.2），旧链路 history 原样不动（D1），REST/WS 论证掉（§四），而 `history-system.md` 里已 spec 的 session 识别、SessionSummary 聚合、pin/unpin、in-flight 双源、崩溃回收（`interrupted`）**一个都没有出现在文档里**——既没有被采纳，也没有被列入「不采纳」并说明理由。

这不是「解读错了」，是**「history 功能」这个词的语义面被静默收窄了**，收窄过程对用户不可见。详见第 3 节。

### 1.2 同样合理、但文档完全没提的解读

逐个说明该补进选项还是该排除。

#### (a) REST/WS 查询面 —— **必须补进选项。这是 blocker。**

`docs/.human-controlled/MAIN.md:38`，在「运维与调试端点」标题下，用户亲笔写着：

```
- 历史：`/history/api/*`、`/history/ws`
```

同一份文档的开头写着「已经存在的内容，如果与本系列文档相违背，都需要用户再次裁决」，而且同一份文档**演示过怎么标注不做的东西**——`MAIN.md:30` 把 Responses WebSocket 明确标为「已裁决 暂不支持」，`MAIN.md:34` 还补了 2026-08-16 的处置说明。历史端点旁边**没有任何这类标注**。

方案 §四 第四条把「先上 REST/WS 查询面」列为不采纳，理由是「`history-system.md` 那套是为旧链路 web UI 写的，新链路没有消费者」。这个理由在技术上有内容，但它**通篇没有提到 `MAIN.md` 说过这件事**。用户读这份裁决材料时，看到的是「一个 agent 推导出的 spec 里的东西，没有消费者，所以不做」，而实际情况是「用户自己在最高权威文档里列为产品端点的东西，正在被论证掉」。

项目记忆 `human-controlled-docs-are-final-authority` 的原话是：`docs/.human-controlled/` 压过一切我推导的 ADR/spec。方案的处理正好把优先级倒过来了——用 `history-system.md`（agent 推导）的「为旧链路 web UI 写的」这一属性，去否定 `MAIN.md`（人写）里的一行声明。

**我不是主张必须做 REST/WS。** 用户完全可能就是想撤掉它。但那必须是**他看着 `MAIN.md:38` 做的裁决**，而不是在不知道自己写过这行的情况下顺着推荐勾了 CLI。

**严重度：blocker。修法：把它从 §四「不采纳」提升为第五个分叉，选项文本里直接引 `MAIN.md:38` 原文，并说明「若否决，`MAIN.md` 需要一条 2026-08-20 的标注，格式参照 `MAIN.md:34` 对 Responses WebSocket 的处置」。**
**可信度：可据以行动**（`MAIN.md:38` 逐字核对过，`MAIN.md:30`/`:34` 的对照标注也核对过）。

#### (b) TUI 历史回看 —— 该补一句，不必成为分叉

`docs/agents/tui-request-log/SPEC.md:130` 在「明确不做」里写着「分层遥测、请求历史面板等，均已有各自归属文档」——也就是说**请求历史面板是已知的、有归属的候选**，只是不归 TUI 那次切片。同一节 `SPEC.md:128` 还写着「现有 reducer 的 `panel_list` / `detail` 两态保留，本次不接线」——**骨架已经在了**。

所以「新链路没有 UI 消费者」这句话（§2.4）严格说不准确：没有 web UI 消费者是真的，但 TUI 侧有两个已存在、等着被接线的状态。

**严重度：minor。** 我不主张本次做 TUI 面板——`SPEC.md:128` 自己警告了 `rich.Live` 的 footer 模型可能不够用、需要重估 DECSTBM，这不是顺手能做的。但方案应当一句话交代：「TUI 历史面板已在 `tui-request-log/SPEC.md:130` 归属他处，本方案产出的记录是它未来的数据源，本次不接线。」这样用户知道这条路没被堵死。

#### (c) 全文搜索 —— 该排除，但要给出正确的排除依据

`history-system.md:18` 与 `:451` 已经把全文搜索裁决为 `[缓存/延后，见 BACKLOG#2]`，默认走「SQL 列过滤 + `preview_text` 的 `LIKE`」。

方案完全没提这件事。**正确的排除依据不是「没人要」，而是「已被 BACKLOG#2 裁决延后」**，一句话的事。

**严重度：nit。**

#### (d) 会话级聚合分析 —— **该补进选项，而且它现在被一个字段决定着生死。见 3.5。**

`history-system.md:181-221` spec 了 `SessionSummary`（request_count / agent_count / token 合计 / 各状态计数 / models），`:249-262` spec 了从 6 个 header 里按优先级取 `session_id`、从 `x-claude-code-agent-id` 取 `agent_id`。

这对本项目的实际工作方式高度相关：`260820-forensic-demand-audit.md:26` 那一行，事件 A 要判定的第一个问题就是「哪一次请求、什么模型、`session_id`/`agent_id`」，当时**唯一来源是客户端 transcript**。

方案的 L1 定义是「`_Trace` 的全部字段 + request_id + 起止时间戳 + 最终 status」（§2.1 表），而 `_Trace`（`src/app/server/pipeline_app.py:64-93`）**没有 session_id、没有 agent_id**。实测：`rg -n 'session.id|agent.id' src/app/server/ src/app/pipeline/ src/app/observability/` 的命中**全部落在旧链路**（`src/app/pipeline/context.py:43-44`、`:90-91`，`src/app/pipeline/executor.py:138-139`、`:201-209`、`:242`），新链路一处没有。

后果见 3.5——这不只是「少一个选项」，是方案自己的 §2.4 已经写了一个查不动的过滤器。

#### (e) 给 subagent 调研提供数据接口 —— **该补进选项，成本近乎为零**

这个项目的调研是**派 subagent 去做的**（`.claude/rules/00-development-workflow.md`「Parallel work」一节，以及 `docs/tmp/` 下这一大批 `260820-*` 报告本身就是产物）。一个 agent 做取证时最需要的不是好看的终端输出，而是**能喂给下一个工具的结构化输出**。

`debug models` 已经立好了先例：`src/app/cli.py:404-411` 的 `--json` 选项，帮助文本是「Print the complete decoded upstream payload」。方案 §2.4 的三条 CLI 子命令**都没有提 `--json`**。

这条同时呼应用户规则 `richest-context-flow`（上游阶段少过滤，终端阶段再裁）。一个 `--json` 让整批 `docs/tmp/` 式调研能直接把记录喂进 `jq`/Python，而不是解析人类可读表格。

**严重度：major（作为 §2.4 的缺项）。修法：§2.4 三条子命令统一带 `--json`，并说明它是给 agent 调研用的，沿用 `debug models` 的既定形态。**
**可信度：可据以行动**（`cli.py:404-411` 已核对）。

#### (f) 改善日志本身的可检索性 —— **必须补进选项。这是最便宜的一条，而它被整个漏掉了。**

`260820-forensic-demand-audit.md:102`，第 4 节反向核对的第 3 条，原话：

> pts/tmux 的终端回滚缓冲……**它本来就是「日志只写 stdout 不落盘」这个已知问题的症状之一，正确的修法是加文件 sink**，不是指望终端缓冲。

同一份报告 `:92` 又说：「落地成本主要是**加一个文件/数据库 sink**」。

**方案只取了「数据库」，把「文件」丢了，而且没说为什么。**

实测当前日志出口：`src/app/observability/logging.py:150` 只有一个 `logging.StreamHandler()`，`src/app/observability/terminal.py:126` 默认 `sys.stderr`，`src/app/observability/tui.py:122` 也是 `sys.stderr`。**全项目没有任何文件 handler。** `src/app/config/schema.py` 里也没有任何 log 文件路径/轮转配置（grep 命中只有 `github_token_file`、`pidfile`）。

这为什么是范围问题而不是实现细节：

1. **L1 只救完成行，救不了别的日志行。** 空 text block 400 那次调查的**入口证据**是「06:00:21/22 的生产日志」（`260820-forensic-demand-audit.md:42`），那是一条错误日志，不是完成行。L1 落库之后，这类行**依然只在 stderr，依然一滚动就没**。
2. **它更便宜。** 一个 `RotatingFileHandler` 加一个配置键，对比一个新 recorder + schema 增量 + reaper + 档位开关。
3. **两者不互斥、且互补**：文件 sink 覆盖「所有日志行、包括没有结构化字段的告警」，L1 覆盖「结构化查询」。

**严重度：major。修法：把「日志文件 sink（含轮转）」作为一个独立选项写进 §三，明确它与 L1 是互补而非替代；我的倾向是它应当排在分片 1 之前——它是本方案里投入产出比最高的一条，而且不依赖任何其他决定。**
**可信度：可据以行动**（三处 sink 位置与 schema 缺项均实测）。

#### (g) 一条方案与我都没提、但值得提的：记下我方发给客户端的 `message.id`

项目记忆 `client-transcripts-are-the-last-forensic-resort` 的操作要点是「扫描要覆盖 `subagents/`，按 `message.id` 归组」。也就是说，**客户端 transcript 的主键是 `message.id`**。

而我方在 `src/app/pipeline/delivery/stream.py:145` 与 `:165` 发出 `message_start(message_id, model)`——**这个 id 我们自己就是签发者**，此刻在手里。

把它记进 L1，服务端记录与客户端 transcript 的关联就从「按时间戳凑」变成「按主键 join」。成本是一个字段。

**严重度：minor（增强建议，非缺陷）。可信度：可据以行动**（`stream.py:145`/`:165` 已核对）。

### 1.3 该排除的解读，以及排除理由

- **把现有 `~/.local/share/ghc-api-proxy/history.db` 的 8534 行做起来查询面**：排除。`260820-history-wiring-audit.md` §5 已证实那是测试污染（无一条 `anthropic-messages`，`request_payload` 平均 46.66 字节），对它建查询面是给垃圾数据修路。
- **复刻 copilot-api-js 的内容寻址去重**：排除，方案 §四已给出正确理由（跨请求去重的前提本项目不成立）。这条我认可。
- **记 L4 下行块**：排除，方案理由（零次被点名 + 可由 L3 推出）成立。补一条支持证据：块级交付下下行块是我方产物，出问题时真正的分辨点是「上游给了什么」而不是「我们发了什么」，后者可由代码复算。

---

## 2. 有没有悄悄扩大范围

### 2.1 先给结论：L3 不是搭顺风车，但 **export-cassette 是**，而且 **L3 的 schema 是被 cassette 需求写坏的**

主会话的假设是「L3 记帧 + export-cassette 这一支服务的是测试固件而不是调研」。我的核查结论是**一半成立，而且不成立的那一半问题更严重**。

**L3 本身有独立的取证依据，不是搭车。** `260820-forensic-demand-audit.md:70`：「上游 SSE 帧的字节级时序」被点名 3 次，`downstream-keepalive-defect.md` §3/§5 因为拿不到它而只能停在「相容」，拒绝升级为根因。这个需求不依赖 cassette 存在。

**但方案给出的 L3 schema 满足不了这个需求。** §2.2 的建表语句：

```sql
CREATE TABLE IF NOT EXISTS upstream_frames (
    entry_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event TEXT,
    data_zstd BLOB NOT NULL,
    data_bytes INTEGER NOT NULL,
    PRIMARY KEY (entry_id, sequence)
);
```

**没有时间戳列。**

取证需求要的原话是「delta 到达**时刻**、静默窗口内**是否真的在发**」（`forensic-demand-audit.md:70`），以及 `:85` 那一行「或至少每个 `content_block_start/delta/stop` 与 `output_item.added/done` 的**到达时间戳**」。`sequence` 只给顺序，**顺序推不出时刻**：一个 200 秒静默然后爆发 50 帧的流，和一个每 4 秒一帧的流，在这张表里的记录**逐字节相同**。而这两者的区分，正是 `downstream-keepalive-defect.md` 那次调查唯一缺的东西。

再看这张表是从哪来的：`260820-history-as-fixture-source.md:56-63` 的建议 schema，**五列逐列相同**，每一列的注释都是「服务 cassette 的 X」——`sequence` 注释是「服务 cassette 的 chunk 顺序」，`data_zstd` 注释是「服务 cassette 的 chunks[]」。**这张表是按 cassette 的数据结构画的，cassette 不需要时间戳，所以它没有时间戳。**

方案 §2.1 把 L3 的「依据」写成「需求排名第 3；且是 cassette 派生的必要条件」，两个依据并列，但**落到 schema 上只有后一个被满足了**。

**这就是「悄悄扩大范围」的镜像形态**：不是多做了东西，而是**用取证的名义立项、按固件的规格交付**。用户批了 A1，以为买到的是「下次能坐实上游是不是真的沉默了」，实际买到的是「下次能生成 cassette」。

**严重度：blocker。修法：`upstream_frames` 增一列 `received_at REAL NOT NULL`（相对请求起点的单调秒数即可，不必墙钟），并在 §2.1 的 L3 行里把「时序」与「帧内容」拆成两个可分别裁决的东西——因为如果用户只想要 cassette，那一列可以省；如果他想要的是取证，那一列是全部理由所在。**
**可信度：可据以行动**（两份文档的 schema 逐列对照过，取证需求原文逐字引用）。

### 2.2 export-cassette 确实是搭车，且它污染了分叉 A 的推荐理由

`debug history export-cassette`（§2.4 第三条、§5 分片 5）服务的是**测试固件**，不是调研。这一点方案自己也承认——§2.4 的论证是「替代已失效的 `from_history.py`」，`from_history.py` 是 `tests/integration/recorded/` 下的测试工具。

它是不是该做？**该做**，理由充分：项目规则明写「Upstream behaviour is recorded, not imagined」，而 `260820-history-as-fixture-source.md:38` 实测确认旁边那个 Bun 服务 2026-08-15 之后不再写 `frame` 对象，这条派生路径**已经断了**。这不是我或方案发明的需求，是一个已经失效的既有能力。

**问题在于它被放在哪。** 方案 §三分叉 A 的推荐理由里写着：

> L3 额外换来 cassette 派生能力，这是本项目测试纪律（「上游行为是录下来的，不是想象的」）明确依赖的东西。

这句话把**两条论证链完全不同的东西捆在了一起**：取证深度（用户遇到线上问题时能查到多少）和固件供应（开发时能不能造出可信测试样本）。用户对这两件事的优先级完全可能不同——他可能觉得取证急、固件不急，或者反过来（固件断供是**已经发生**的能力损失，取证缺口是**已经发生过三次**的排障阻碍，两者都真实）。

捆在一起的后果是：**想要 cassette 的用户被迫连 L2 一起买，想要取证的用户被迫连 export 一起买。**

**严重度：major。修法：拆成两个分叉。分叉 A 只问取证深度（L1 / +L2 / +L3）；新增一个分叉只问「是否本次一并恢复 cassette 派生能力」，并在其中说明它依赖 L3 落地（含或不含时间戳列都可以派生 cassette）。**
**可信度：可据以行动。**

### 2.3 没有发现的扩大：证明基础设施

主动核查了一遍，**方案没有搭建不成比例的证明基础设施**：§5 分片 1 只说「附一个判别性冒烟测试」，没有 manifest、没有投票、没有 gate、没有验证状态机。这符合项目规则「Solve the requested task before building proof infrastructure」。

**这一点值得明确说出来**，因为它是这份方案做对的地方，不该被上面的批评淹没。

### 2.4 一处轻微扩大：双维度限流

§2.3 末句「容量按**条数与压缩后总字节数双维度**限流」。这条的出处是 `260820-history-as-fixture-source.md:106`，而那份报告自己在 `:130` 的「未采纳/待裁决事项」里明写：「本报告基于真实分布提出的建议，**尚未经用户裁决**，未采纳/未实现」。

方案把它从「待裁决建议」直接升格成了 §2.3 的设计陈述句，中间没有经过用户。论证是合理的（90KB 长尾会让纯条数限制失准，`from_history.py` 的实测分布支持这一点），但**它是一条新增机制**，多一个维度就多一套配置键和一套 reaper 逻辑。

**严重度：minor。修法：在 §2.3 标注它是从未裁决建议继承的，或并入分叉 C 末尾那个「配置键放哪」的提问里一起裁。**

---

## 3. 有没有悄悄缩小范围

主会话点名了四项，逐项判：哪些是合理分片，哪些是在替用户做本该他做的决定。

### 3.1 旧链路 history 的去留（分叉 D）—— **合理，这条做对了**

D1「本次完全不动」，理由「D3 触及『不得擅自删除已实现的功能』——旧链路是否还有用不是我该判的」。

**这条完全正确**，而且正确地把它做成了分叉而不是自己拍板，符合项目记忆 `never-delete-implemented-functionality-unsolicited`。D2（合并 `protocol_history.py`）的 ROI 判断我也认可——在一条不服务生产的链路上做整洁性重构，收益确实低。

**唯一的缺项：D1 的代价没写。** 见 3.4 与 5.3——D1 不是零成本选项，它意味着「两个写者共用同一个 `entries` 表」这个局面被保留下来，而方案又要 `ALTER TABLE entries`。用户在 D1/D2/D3 之间选择时，看不到 D1 的这笔账。

**严重度：minor（作为 D1 的信息缺项）。**

### 3.2 `protocol_history.py` 的重复实现 —— 合理分片，无异议

`260820-history-wiring-audit.md` §1 路径 B 已经把它查清楚了：四个协议路由绕开 `HistoryConsumer`、手写一份等价逻辑。方案 D2 判它 ROI 低、本次不做。

**我同意，不提异议。** 它不影响新链路，不影响本方案任何一片，不构成前置条件。这是干净的分片。

### 3.3 六个钩子点未实现 —— **不合理。这是把分叉降格成了「不采纳」。**

方案 §四第一条把「用 `hooks:` 那六个订阅点实现记录」列入不采纳，理由是：它们在 `src/app/config/schema.py:209-214` 只有配置键，管线里没有一处真的触发；建在不存在的平面上要先付实现钩子分发的代价，而这笔代价与取证无关。

**技术理由本身是对的**，实测确认：`rg -n 'on_upstream_request_ready|on_client_sse_block_ready|on_upstream_sse_block_ready' --glob '!docs/**' -l` 只命中 `src/app/config/schema.py` 一个文件。这也正是项目记忆 `verify-the-surface-exists-before-building-on-it` 要求的核查，方案做了，值得肯定。

**但把它放进「不采纳」而不是「分叉」，判断过重了。** 三条依据：

1. **这六个键在用户亲笔的 `config.example.yaml` 里**（`docs/.human-controlled/config.example.yaml:434-450`），每一条都带用户自己写的中文注释。它们不是某个 agent 推导出来的设计，是用户写下的意图。
2. **`schema.py:203-207` 的 docstring 说这六个是「the operator-facing points」**，与驱动内部的 `attempt.*`/`request.*` 事件区分开。而取证记录**恰恰是 operator-facing 的头号消费者**——用户写这六个点的时候，脑子里想的十有八九就是这类东西。
3. **成本对比没有方案说的那么悬殊。** 方案要接的点是 `_log_completion`（`pipeline_app.py:103`）和 `read_events`（`sse_source.py:65`）。这两处对应的钩子名是 `on_client_request_closed` / `on_upstream_request_closed` 与 `on_upstream_sse_block_ready`。也就是说，**本方案无论如何都要在这两处开接缝**——差别只是接缝的另一头是「一个写死的 recorder」还是「一个按配置键分发的列表」。后者多出来的是一个「按名字查函数、按顺序调用」的分发器，不是一整套钩子子系统。

方案自己在 §四写了「钩子点本身值得实现，但那是另一个任务」——**这句话就是它该被做成分叉的证据**：一件「值得做、且本次正好路过、且用户写在自己文档里」的事，被单方面推到了别的任务。这正是项目规则 `no-silently-cut-but-defer` 说的情形（中途发现用户从未明确裁决过、与当前任务相关的功能，应当纳入考虑或提醒用户，而不是自己裁掉）。

**严重度：major。修法：做成分叉——(1) 直接挂 `_log_completion` / `read_events`，钩子另议；(2) 本次顺带实现这两处的钩子分发，recorder 作为它的第一个订阅者。并把成本差写成一句话（多一个「按名字查函数并按序调用」的分发器），让用户自己判这笔账值不值。我的倾向是 (1)——先让取证跑起来，但必须让用户看见 (2) 存在。**
**可信度：可据以行动**（三处代码位置与 `config.example.yaml` 均实测）。

### 3.4 测试往用户真实数据目录写库 —— **不合理。这不是「附带发现」，是本方案的前置条件。**

方案 §1.1 的处理是一个引用块：

> **附带发现，需要单独处理**：测试正在往用户真实数据目录写文件。这不在本方案范围内，但应当记一笔——测试库该落在 `tmp_path` 里。

「不在本方案范围内」——**我认为这句话是错的，而且错得有具体后果。**

事实链：

1. 旧链路测试写 `~/.local/share/ghc-api-proxy/history.db`，已在库里堆了 8534 行垃圾（`260820-history-wiring-audit.md` §5，`:158` 也把它记为「测试隔离缺口」）。
2. 方案 §2.2 要复用 `app.history` 存储层，`history-system.md:420` 规定默认路径就是 `$XDG_DATA_HOME/ghc-api-proxy/history.db`——**同一个文件**。
3. 于是：**新 recorder 上线后，每次本地跑 `tests/http/*`，测试数据就会被灌进用户正在用来取证的那个库。**

后果不是「不整洁」，是**取证库的信噪比被自己的测试套件破坏**。现在那个库里 8534 行有 0 行真实流量；方案落地后它会变成「真实取证记录 + 每天几百行测试噪音」混在一起，而 `debug history list` 分不出来。更糟的是 reaper——`success_limit` 默认 50（`history-system.md:270`），**一次测试跑动就足以把你正在查的那条真实记录挤出成功桶**。

顺带确认这不是孤例：仓库里还躺着 `data/history.db`（root 所有，20480 字节，mtime 2026-08-12），同源污染，方案没提。

**严重度：major。修法：把测试隔离（`tmp_path` 或强制 `db_path` 注入）**升格为分片 1 的前置条件**，或者至少写进 §5 作为分片 0。它很便宜，而且它是「新记录能不能被信任」的前提。**
**可信度：可据以行动**（三条事实链每一环都有出处；`data/history.db` 为实测 `ls -la`）。

### 3.5 一项主会话没点名、但更严重的缩小：L1 的字段集，以及它导致的自相矛盾

前面 1.2(d) 已经铺垫，这里给完整判断。

**方案 §2.4 写：**

> `debug history list` —— 按时间倒序列出，支持 `--model` / `--status` / `--since` / `--session` 过滤

**方案 §2.1 写：** L1 = 「`_Trace` 的全部字段 + request_id + 起止时间戳 + 最终 status」。

**而 `_Trace`（`src/app/server/pipeline_app.py:64-93`）的全部字段是**：method、path、request_id、inbound_format、client_protocol、upstream_protocol、requested_model、model、attempts、detail、failed、started、bytes_in、received、usage、stop_reason、tools、thinking、dialect。

对照 §2.4 的四个过滤器：

| 过滤器 | L1 里有数据源吗 |
|---|---|
| `--model` | 有（`model` / `requested_model`） |
| `--status` | 有（`status_code` + `failed`） |
| `--since` | **有条件**——`trace.started` 是 `time.monotonic()`（`pipeline_app.py:148`），**不是墙钟**，跨进程、跨重启都无意义。方案的「+ 起止时间戳」如果指的就是补墙钟，那没问题，但文档没说清这是一项新增采集而非现有字段 |
| `--session` | **完全没有。** 新链路一处都没有 session/agent 的采集，实测命中全在旧链路（`pipeline/context.py:43-44`、`:90-91`） |

**这是方案内部的直接矛盾**：§2.4 承诺的过滤器，§2.1 定义的数据层供不出来。

更要紧的是它对**分片 1 的可交付性**的影响（这正是主会话的问题 4，详见第 4 节）。

**严重度：major。修法：L1 字段集必须显式列出，而不是写「`_Trace` 的全部字段」。至少补三项：墙钟起止时间（`--since` 与跨进程关联的前提）、`session_id`/`agent_id`（`--session` 的前提，采集规则 `history-system.md:249-262` 已 spec 好，是照抄不是设计）、我方签发的 `message.id`（`stream.py:145`，客户端 transcript 的 join key）。**
**可信度：可据以行动**（字段表逐条核对 `pipeline_app.py:64-93`，session 采集缺失以两次反向 grep 确认）。

### 3.6 另一项未点名的缩小：pin/unpin 被漏掉了，而分叉 B 正需要它

`history-system.md:311-313` spec 了 pin：「调试/复现问题时常需要保留某条关键样本，pin 之后该行既不计入所在桶的配额、也不会被淘汰」。`HistoryStore` **已经实现了** `set_pinned`（`260820-history-wiring-audit.md:125` 列出的方法签名里有）。

方案通篇没有 pin。

**这与分叉 B1 直接冲突**：B1 是「失败全留 + 成功留最近 N 条（N 默认 50 上下）」。取证的典型节奏是「今天出事，明天派 agent 去查」——而 50 条成功记录在一个活跃的代理上可能撑不过一小时。**没有 pin，B1 的滚动窗口会在调查进行中吃掉调查对象。**

这是「已实现能力 + 已 spec 行为 + 当前设计正需要」三者齐备却被漏掉，成本近乎为零（store 里已有方法，CLI 加一个 `debug history pin <id>`）。

**严重度：major。修法：pin 纳入分片 2（跟 `list`/`show` 一起），并在分叉 B1 的描述里点明「滚动窗口靠 pin 兜底」——因为**没有 pin 的 B1 和有 pin 的 B1 是两个不同的选项**，用户对前者的接受度会低得多。**
**可信度：可据以行动**（`history-system.md:311-313` 与 store 方法清单已核对）。

### 3.7 小结：哪些是合理分片，哪些不是

| 项 | 方案的处理 | 我的判定 |
|---|---|---|
| 旧链路 history 去留 | 分叉 D，推荐 D1 | **合理**（仅缺 D1 的代价说明） |
| `protocol_history.py` 重复 | D2，不做 | **合理分片**，无异议 |
| 六个钩子点 | §四「不采纳」 | **不合理**——应为分叉（major） |
| 测试写真实数据目录 | §1.1 引用块「不在范围内」 | **不合理**——是前置条件（major） |
| L1 字段集 / session | 未讨论 | **不合理**——静默缩小 + 内部矛盾（major） |
| pin/unpin | 未提及 | **不合理**——B1 的必要配套（major） |

---

## 4. 分片顺序是否真的每片自足可交付

### 4.1 §5 开头那句话与它自己的结尾自相矛盾

§5 开头：「每片**自足**、可独立评审与合入，符合项目『完成一个自足小补丁就立即集成』的要求」。
§5 结尾：「分片 1 与 2 之后就已经补上了……**是第一个真正有用的里程碑**」。

**「第一个真正有用的里程碑在 2 之后」这句话，本身就承认了分片 1 不自足。**

「可独立评审与合入」和「自足可交付」是两个不同的判据。项目规则的原话是「Complete and integrate each self-contained small patch immediately. Do not wait for a large feature or design batch when a smaller slice is already **reviewable and useful**」——**reviewable **and** useful**，两个条件。分片 1 满足前者，不满足后者。

### 4.2 直接回答：分片 1 交付之后，有人能用它回答一个真实问题吗

**不能，有三层障碍，前两层是方案自己造成的：**

**第一层：没有读取面。** 分片 1 只有 recorder，`debug history list/show` 在分片 2。所以分片 1 之后的唯一读法是 `sqlite3 ~/.local/share/ghc-api-proxy/history.db 'select ...'`——而且 `request_payload`/`response` 是 **zstd 压缩的 BLOB**（`history-system.md:108`），`sqlite3` 命令行**读不出来**，得写 Python。这不是「有人能用」，这是「作者能用」。

**第二层：拿它去回答历史上那三次真实问题，会卡在字段上。** 用事件 A（256.9s 超时）实测代入：

| 要判定的 | 分片 1 之后能答吗 |
|---|---|
| 哪一次请求、什么模型 | **半个**——有 model，但**没有 session/agent id**（3.5），对不上客户端 transcript 里那次调查 |
| 什么时候、多长时间 | **duration 能答，绝对时刻不能**——`trace.started` 是 monotonic（`pipeline_app.py:148`）。「07:45:09 那次」这个提法在库里查不到，除非「+ 起止时间戳」确实新增了墙钟采集，而文档没说 |
| 走的哪个进程、哪份配置 | 不能（方案也没承诺，`forensic-demand-audit.md:27` 说这靠 `/proc`，合理） |
| 为什么慢 | 不能（那是 L2/L3，方案也这么说，诚实） |

**第三层：库里还混着测试噪音**（3.4），50 条的成功桶可能已经被测试挤空。

### 4.3 分片顺序本身的其他问题

- **分片 6「配置与容量」排在最后是危险的。** 分片 1 一旦落地，`history.enabled` 默认 `true`（`config.example.yaml:429-430`，用户亲笔），意味着**从分片 1 合入的那一刻起就开始无条件记录**，而限流（reaper 的双维度、档位开关）要等到分片 6 才有。中间这段时间库只涨不清。分叉 C 的提醒（「接上之后默认就开始记录」）只提了行为变化，**没提「限流要等五个分片之后」**。
- **分片 4（L3）与分片 5（export-cassette）之间缺一个验证环节。** 判断「派生出来的 cassette 是不是真能回放」需要拿它跑一遍现有回放测试，这在分片 5 里没写。这不是要建证明基础设施，是一句「用 `tests/integration/recorded/` 的既有回放跑一次新产出的 cassette」。

### 4.4 修法

1. **合并分片 1 与 2**，或把 §5 开头改成「每片可独立评审与合入；第一个可用交付是 1+2 合并后」。我倾向合并——一个只能用 Python 解压 BLOB 才能读的记录层，不是一个可以「用起来」的补丁。
2. **把限流的最小形态（哪怕只有条数上限）提到分片 1**，或把默认值改成关，由用户在分叉 C 里明确知道这个取舍。
3. **在分片 1 之前插入「测试隔离」**（3.4）。
4. 分片 5 补一句回放验证。

**可信度：可据以行动**（zstd BLOB、monotonic、默认 `true` 均实测）。

---

## 5. 文档本身作为裁决材料是否够用

### 5.1 结论

**不够用，但差距不大，主要是三处「会让人选错」和两处信息缺口。** 文档的结构（事实 / 设计 / 分叉 / 不采纳 / 分片）是对的，密度也合适，没有明显废话。

### 5.2 会让人选错的地方

**(a) 分叉 B 对 B3 的反对理由是错的 —— major**

§三分叉 B 原文：

> B3 的问题不是体积（3.6MB/千条不贵），而是在没有明确需求时对热路径无条件加负担。

**这个理由对 B1 同样成立，所以它区分不出 B1 和 B3。**

推理：L2/L3 要在请求进行中采集。B1 是「失败全留 + 成功留最近 N 条」——但**请求结束前你不知道它会不会失败**，所以成功请求的帧也必须先被采下来（旁路 `read_events`、压缩、入队），只是事后被 reaper 删掉。**热路径的负担 B1 和 B3 完全相同**，差别只在磁盘保留量和 reaper 工作量。

除非 B1 的意思是「成功请求先在内存缓冲、终态判定后再决定写不写」——那是另一套机制，方案没说，而且它会引入「一个长流式请求要在内存里攒完整帧序列」的新问题（§1.6 说长尾单条原始 90KB）。

**后果**：一个在意热路径性能的用户会因为这句话选 B1，以为自己省下了热路径开销，实际什么也没省。而如果他知道「热路径成本一样，只差磁盘」，他可能直接选 B3（3.6MB/千条确实不贵，而 B3 免掉一整套档位逻辑）。**这句话可能让用户为了一个不存在的收益，买下一套不必要的复杂度。**

**修法**：把 B1 与 B3 的真实差异写清楚——热路径成本相同，差异是磁盘占用与 reaper 复杂度；B1 的收益是「库不会被成功流量淹没、`debug history list` 更好用」，这才是它真正的卖点。

**(b) 分叉 A 的推荐理由捆了两条论证链 —— major，已在 2.2 展开**

**(c) 分叉 C 没提两个同名 `HistoryConfig` —— minor**

§三分叉 C 说「`HistoryConfig` 目前只有 `enabled` 一个字段，而 `history-system.md` 已经 spec 了五个键」。但 `260820-history-wiring-audit.md:111` 已经查明：**存在两个不同的 `HistoryConfig` 类**——`src/app/config/settings.py:49-55`（旧链路，六个字段，默认 `success_limit=50`/`failure_limit=200`/`reaper_interval=600`）和 `src/app/config/schema.py:198-199`（新链路，只有 `enabled`）。

C1「接上这个开关」时，用户需要知道他面对的是「新 schema 补齐到与旧 settings 一致」还是「两套配置类长期并存」。这个信息在支撑材料里有，被方案漏掉了。

### 5.3 信息缺口

**(a) 工作量量级完全缺失 —— major**

用户要在 A1/A2/A3 之间选，文档给的唯一量化是「A1 是三层里最大的工作量」。**没有任何相对量级**（A1 是 A2 的两倍还是十倍？分片 3、4 各是多大？）。

这直接影响裁决：如果 L2+L3 是 L1 的 1.5 倍，A1 显然划算；如果是 5 倍，用户可能想先 A2 观察。**没有这个数，分叉 A 实际上无法被理性裁决**，用户只能顺着推荐走——而「顺着推荐走」正是这类文档应该避免的结果。

修法：每个分片给一个粗量级（新增文件数/改动点数量级即可，不需要工时）。

**(b) 新记录落在哪个物理库，没说 —— minor**

§2.2 只说「复用 `app.history` 的存储层」。但没说：**用同一个 `~/.local/share/ghc-api-proxy/history.db` 还是新开一个文件？** 这个问题的答案决定三件事：

- 是否与旧链路测试并发写同一文件（3.4）；
- `ALTER TABLE entries` 加的两列会不会影响旧链路读写（加可空列应该安全，但需要一句话确认）；
- 那 8534 行历史垃圾要不要清、怎么清（`debug history list` 会不会一上来就列出 2000 条 `openai-chat-completions`？）。

修法：一句话定死，并说明对既有 2.4MB 库的处置（我倾向新开一个文件，名字区分开——它记的东西和旧 entries 语义不同，且天然规避了上面三个问题）。

**(c) `--history/--no-history` 现在到底会怎样，说了一半 —— minor**

§1.1 说这个死开关「按 `cli.py` 自己对 `_NO_HOME_IN_SPEC` 的处理惯例，这类选项应当在启动时明说『无效』，现在它连这个都没有」。分叉 C 的 C2 就是「先让 `cli.py` 明说它无效」。

但 C1（推荐）落地之后，**这个提醒是不是就不需要了**？文档没说。看起来是不需要了（开关真的生效了），但用户读到 C1 时会疑惑「那 C2 里说的那件事还要不要做」。一句话的事。

### 5.4 废话与冗余

密度总体是好的。两处可压：

- **§1.2 的四行闭包大小表（`app.history.types` 6 / `writer` 6 / `store` 9 / `consumer` 34）** 对裁决没有作用。结论「存储层可以复用，不需要改边界测试」才是有用的那一句，数字可以删。**nit**。
- **§1.5 与 §1.6** 大段复述 `260820-history-as-fixture-source.md`。保留是合理的（用户不该被迫去翻支撑材料），但 §1.5 那两个坑的完整来龙去脉可以压到两句，展开留给引用。**nit**。

### 5.5 做得好、不该被上面的批评淹没的地方

按 `state-decisiveness`，正面判断也要说：

1. **§1.1 把「history 从未接在生产链路上」作为第一事实端出来**，而不是埋在后面。这是整份文档最重要的一句话，位置对。
2. **§1.4 的反向核对**（「以下五类记了也没用」）是这份文档最有价值的部分之一——它防住了「补记录就能覆盖所有缺口」这个最容易犯的错。
3. **§1.5 的硬纪律「不要在 `assembler` 之后再记第二份」**，附带说明了理由（记下来的东西恰好丧失了记录它的理由）。这是真正能防住未来某次重构的一句话。
4. **§2.5 主动声明「这条是我按既有立场推定的，不是你明确裁决过的，所以列在这里供你否决」**。这正是 `what-decided-is-decided` 要求的做法。而且脱敏立场本身也正确——按用户规则，取证库落在本机、含临时 token 不构成敏感面，**不该为它加任何保护措施**，方案没有加，对。
5. **§四拒绝钩子点时先核查了「这个平面存不存在」**，符合 `verify-the-surface-exists-before-building-on-it`。判断过重（3.3），但方法对。

---

## 6. 全部发现汇总

| # | 严重度 | 位置 | 一句话 | 可信度 |
|---|---|---|---|---|
| 1 | **blocker** | §四第四条 | REST/WS 被论证掉，但用户亲笔 `docs/.human-controlled/MAIN.md:38` 把 `/history/api/*`、`/history/ws` 列为产品端点且未标「暂不支持」，文档未告知这一冲突 | 可据以行动 |
| 2 | **blocker** | §2.2 建表 / §2.1 L3 | `upstream_frames` 无时间戳列，而 L3 的取证依据正是「帧的到达时序」；schema 逐列抄自固件报告，取证需求被静默丢弃 | 可据以行动 |
| 3 | major | §三分叉 A | cassette 派生（测试固件）被捆进取证深度分叉，两条论证链不同，应拆成独立分叉 | 可据以行动 |
| 4 | major | §三分叉 B | B3 的反对理由（热路径负担）对 B1 同样成立，区分不出两者；会让用户为不存在的收益买下复杂度 | 可据以行动 |
| 5 | major | §2.1 / §2.4 | L1 字段集缺 session/agent id、墙钟时间、`message.id`；`--session` 过滤器无数据源，文档内部矛盾 | 可据以行动 |
| 6 | major | §四第一条 | 六个钩子点从分叉降格为「不采纳」；它们在用户亲笔 `config.example.yaml:434-450` 里，且本方案无论如何都要在同两处开接缝 | 可据以行动 |
| 7 | major | 全文缺失 | 日志文件 sink 完全缺席，而它是需求盘点自己点名的「正确的修法」（`forensic-demand-audit.md:102`），更便宜且覆盖所有日志行 | 可据以行动 |
| 8 | major | §1.1 引用块 | 测试写用户真实数据目录被判「不在范围内」，实为前置条件——新 recorder 与之共用同一文件，测试噪音会挤掉真实取证记录 | 可据以行动 |
| 9 | major | 全文缺失 | pin/unpin（已实现 + 已 spec）未提及，而分叉 B1 的滚动窗口正需要它兜底 | 可据以行动 |
| 10 | major | §2.4 | 三条 CLI 子命令均无 `--json`，而调研由 subagent 做，`debug models`（`cli.py:404-411`）已立先例 | 可据以行动 |
| 11 | major | §三分叉 A | 全文无工作量量级，用户无法在 A1/A2/A3 之间理性权衡，只能顺着推荐走 | 可据以行动 |
| 12 | minor | §5 | 「每片自足」与「分片 1+2 之后才是第一个真正有用的里程碑」自相矛盾；分片 1 之后只能靠写 Python 解 zstd BLOB 才能读 | 可据以行动 |
| 13 | minor | §5 分片 6 | 限流排在最后，而 `history.enabled` 默认 `true`，分片 1 起就无条件记录、五个分片内无上限 | 可据以行动 |
| 14 | minor | §2.2 | 未说明新记录落在同一个 `history.db` 还是新文件，也未处置既有 8534 行垃圾 | 可据以行动 |
| 15 | minor | §三分叉 C | 未点明存在两个同名 `HistoryConfig`（`settings.py:49-55` 六字段 / `schema.py:198-199` 一字段） | 可据以行动 |
| 16 | minor | §2.3 | 「双维度限流」从固件报告的未裁决建议（`history-as-fixture-source.md:130`）直接升格为设计陈述 | 可据以行动 |
| 17 | minor | §1.2 补充 | TUI 历史面板（`tui-request-log/SPEC.md:130`，reducer 的 `panel_list`/`detail` 已存在）作为未来消费者未被提及 | 可据以行动 |
| 18 | minor | §2.1 补充 | 我方签发的 `message.id`（`stream.py:145`）是与客户端 transcript join 的天然主键，成本一个字段，未提 | 可据以行动 |
| 19 | nit | §1.2 | 闭包大小表（6/6/9/34）对裁决无作用 | 可据以行动 |
| 20 | nit | §四 / §1.1 | 全文搜索未提（`history-system.md:451` 已裁决延后，一句话即可）；`data/history.db`（root 所有）是同源测试污染，未提 | 可据以行动 |

---

## 7. 我的整体建议（供主会话取舍，非指令）

**这份方案不该被推翻，该被改小改准之后再送给用户。** 具体四步：

1. **补两个分叉**：REST/WS 查询面（引 `MAIN.md:38` 原文）、钩子点是否顺带实现。**拆一个分叉**：cassette 派生从分叉 A 里独立出来。
2. **改一处 schema 与一处选项描述**：`upstream_frames` 加时间戳列；重写 B1 vs B3 的差异说明。
3. **补三类信息**：L1 的显式字段清单（含 session/agent/墙钟/`message.id`）、每片工作量量级、新库的物理落点与旧数据处置。
4. **调分片顺序**：测试隔离提到最前，1 与 2 合并，最小限流提到分片 1。

改完之后，这份文档就是一份合格的裁决材料。**不建议在改之前送给用户**——按项目规则 `no-rush-for-user-review`，以及更实际的理由：发现 1 会让用户在不知情的情况下否掉自己写过的东西，发现 2 会让他买到不是自己想要的东西。这两条都是「用户读完做出的决定与他的真实意图不符」，而这正是裁决材料唯一不能出的错。

---

## 附：本次评审做过的核查

只读操作，未修改任何源文件或被评审文档。

- 读：`proposal.md`、三份支撑材料全文、`docs/2604-rewrite/history-system.md`、`docs/.human-controlled/MAIN.md`、`docs/.human-controlled/config.example.yaml`（history/hooks 段）、`docs/agents/tui-request-log/SPEC.md`+`deferred.md`
- 读代码：`src/app/server/pipeline_app.py:55-175`、`src/app/observability/request_log.py:83-110`、`src/app/config/schema.py:190-215`、`src/app/cli.py:350-445`、`src/app/debug/__init__.py`、`src/app/pipeline/delivery/assembler.py:41-66`、`src/app/pipeline/delivery/stream.py:139-170`
- 反向 grep：`on_upstream_request_ready|on_client_sse_block_ready|on_upstream_sse_block_ready`（只命中 `schema.py`）；`session.id|agent.id|x-claude-code-*`（新链路零命中，全部落在 `pipeline/context.py`、`pipeline/executor.py`）；日志 sink（只有 `logging.py:150` 的 `StreamHandler` 与两处 `sys.stderr`）
- 实测：`ls -la data/`（root 所有的 20480 字节 `history.db`）、`git log --oneline -5`（HEAD `eb93215`）


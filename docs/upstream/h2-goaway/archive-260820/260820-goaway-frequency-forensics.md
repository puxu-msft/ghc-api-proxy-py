# 上游连接中断的频率取证（GOAWAY / 传输层打断）

**日期**：2026-08-20
**性质**：一次性只读取证。数据源为运行中服务的 history 数据库，全程 `?mode=ro` 打开或先复制再查，未写入任何 history 库、未触碰 4141 端口上的进程。
**触发**：`docs/agents/upstream-h2-goaway/findings.md` —— 2026-08-20 15:01:59 一帧上游 GOAWAY 同时打掉四条在飞流式请求。用户判断「这种情况出现的概率不低，但原因未知」。

---

## 摘要（先看这个）

三条结论，按证据强度排列。

**1. 频率：传输层打断占全部生成请求的 0.64%（594 / 93125，跨 21 个有数据的日历日）。这是**强证据**，但计的是**现网 `copilot-api-js`**，不是本项目。**
按天算，繁忙日 178–235 次/天（2026-08-07/08），安静日 0–11 次/天。**但这个 0.64% 是被时长强烈支配的**：5 秒以内的请求命中率 0.011%，160–320 秒的请求命中率 24.9%。本次事故的四条请求时长 5.3–15.9 秒，落在**最低危险区**。所以「按请求算 0.64%」这个数**不能**直接拿来估计本次事故那一类事件的频率。

**2. 最强的一个模式：一次上游事件同时打掉多条在飞流，这是真实存在的，而且现网服务已经在 2026-07-22 修掉了它——用的正是「每条 H2 连接只跑一条流」。本项目当前没有这个防护。**这是**强到可据此改代码**的证据，且不是我推出来的，是现网仓库的提交与设计文档写死的：

```
b5892380f 2026-07-22 feat(transport): cap concurrent streams per h2 session (default 1)
  Each concurrent request now gets its own h2 connection, so a session-level
  upstream teardown (GOAWAY / edge drain) takes down at most one in-flight
  request instead of every concurrent stream sharing the multiplex —
  the blast radius behind the observed waves of concurrent `rstCode=0` failures.
```

我在数据里**找到了那次触发修复的生产事件本身**（2026-07-22 22:09，8 条同 pid 请求同时死，含 3 条在同一秒内 1.3–1.5 秒被秒拒），并做了修复前后对照：

| 窗口 | 生成请求数 | 传输失败 | **成批失败的占比** |
|---|---|---|---|
| 修复前（H2 多路复用，2026-07-17 .. 07-22） | 16392 | 33 | **57.6%**（19/33） |
| 修复后（N=1，2026-07-22 .. 08-19） | 76733 | 561 | **5.9%**（33/561） |

差了近 10 倍。修复前的失败类别以 `closed_before_response (rstCode=0)`（GOAWAY/边缘 drain 的形态）为主，修复后这一类几乎消失（20 → 13，且总量涨了 17 倍）。

**3. 「随机」这个假说被部分证伪，但方向不是我预期的那个。** 传输失败**不是**在时间上均匀撒开的：小时分布 χ² = 113.5（23 自由度，0.1% 临界值约 49.7）。但超额集中在**少数几段几小时长的发作**（2026-08-06 20h – 08-08 中午那一段，以及 2026-08-07 17h 单小时 9.65%），**不是**每天重复出现的固定时段。所以「上游部署窗口」这个具体猜想**没有**被支持；被支持的是「上游会进入若干小时的不健康期」。

---

## 一、数据源清单

### 1.1 现网 `copilot-api-js` 的 History（**主力数据源，唯一能回答频率的**）

路径：`~/.local/share/copilot-api/history-v3*.db`（SQLite，WAL 模式）。

活跃库指针：`~/.local/share/copilot-api/history-v3-current.txt` → `history-v3-20260818-044224.db`。

用到的表是 `v3_operation_summaries`（由 `v3_operations` 上的触发器投影而来）。关键列：

```
operation_id, summary_json, operation_kind, session_id, agent_id,
started_at, ended_at, endpoint, state, pid, request_model, response_model,
response_success, duration_ms, input_tokens, output_tokens, ...
```

真正有用的是 `summary_json`，字段（4000 条抽样枚举）：

```
id operationKind startedAt endedAt endpoint state active pinned lastUpdatedAt
attemptCount pid requestModel messageCount responseModel responseSuccess usage
durationMs requestBytes previewText responsePreviewText responseBytes sessionId
rawPath queueWaitMs multiplier stream agentId responseError currentStrategy
```

**`responseError` 是本次取证的核心字段**，只在 112/4000 条上存在（即只有失败/中止的记录才有）。

时间覆盖（UTC，只算 `operationKind = 'generation'`）：

```
history-v3-260807.db           n= 20653  2026-07-17 16:59:23 .. 2026-08-06 20:25:43  transport-fail=  58 (0.28%)
history-v3-260809.db           n= 39022  2026-08-06 20:26:54 .. 2026-08-09 00:21:42  transport-fail= 460 (1.18%)
history-v3-260811.db           n=  5944  2026-08-10 06:46:10 .. 2026-08-11 07:47:30  transport-fail=  19 (0.32%)
history-v3.db                  n= 24102  2026-08-11 08:11:58 .. 2026-08-15 17:48:46  transport-fail=  53 (0.22%)
history-v3-20260815-183721.db  n=   792  2026-08-15 18:41:06 .. 2026-08-16 16:01:49  transport-fail=   0 (0.00%)
history-v3-20260816-160151.db  n=   896  2026-08-16 16:02:18 .. 2026-08-16 20:13:16  transport-fail=   0 (0.00%)
history-v3-20260817-050754.db  n=   571  2026-08-17 05:08:01 .. 2026-08-18 04:41:47  transport-fail=   1 (0.18%)
history-v3-20260818-044224.db  n=  1145  2026-08-18 04:42:43 .. 2026-08-19 19:39:59  transport-fail=   3 (0.26%)
```

合计 94912 条 operation，其中 93125 条是 generation。

**两处覆盖空洞，必须记住**：

- **2026-07-24 .. 2026-08-05 完全没有记录**（13 天）。`history-v3-260807.db` 的时间跨度看似横跨这一段，但按天统计里这些天一条都没有。
- **2026-08-20（事故当天）没有任何记录**。最后一条是 2026-08-19 19:39:59。

关于「2026-08-15 之后不再存储 frames」这个已知边界：**请求级记录仍在，而且完整**——`state` / `responseError` / `durationMs` / `requestBytes` / `responseBytes` 全都有。丢的是逐帧的 timeline，本次分析不需要它。所以那条边界**不影响**本次取证。

### 1.2 本项目自己的 History（**对本问题无用**）

路径：`~/.local/share/ghc-api-proxy/history.db`（`HistoryConfig.db_path` 为空时的默认位置）。Schema：

```sql
CREATE TABLE entries (
    id TEXT PRIMARY KEY, session_id TEXT, agent_id TEXT,
    started_at REAL NOT NULL, ended_at REAL, endpoint TEXT NOT NULL,
    status TEXT NOT NULL, requested_model TEXT NOT NULL, resolved_model TEXT NOT NULL,
    request_payload BLOB NOT NULL, response BLOB, usage BLOB,
    error_message TEXT, pinned INTEGER NOT NULL DEFAULT 0
);
```

8966 条，2026-07-16 .. 2026-08-20 14:17:47。**全部是测试流量**：

```
endpoint 分布：
openai-chat-completions 2790 | openai-responses-websocket 2240 | azure-responses 564
azure-embeddings 564 | azure-chat-completions 564 | gemini-streamGenerateContent 563
gemini-generateContent 563 | openai-responses 559 | openai-embeddings 559

model：gpt-test / gemini-test / deployment
endpoint like '%anthropic%' or '%messages%' 的条数：0
error_message 直方图：<null> 8966（全部为空）
```

三点结论：

1. 本项目 History **一条生产 `anthropic-messages` 流量都没有**，全是测试套件产生的。
2. `error_message` **一条都没写过**。
3. 最后一条是 14:17:47，**早于 15:01:59 的事故**。

所以本项目的 History **完全答不了这个问题**。而且即便当时开着，也答不了——`findings.md` 已经登记了这一点：`context.reply` 仍 gate 在 `terminal.seen`，失败的流根本不会落 History（「未闭合的另一半：failed History」）。**这本身就是一条待办：我们目前对自己的传输失败没有任何持久化观测能力。**

### 1.3 日志文件 / journald（**都是死路，已确认**）

- 本项目服务当前以 pid 1282496 运行：`ghc-api-proxy start --port 4141 --restart`，`/proc/1282496/fd/1` 与 `fd/2` 都指向 `/dev/pts/49`。**stdout/stderr 只进终端，没有落盘。**
- `systemctl list-units` 与 `systemctl --user list-units` 里**没有** ghc / copilot 相关单元；两个服务都不在 systemd 下跑。
- `journalctl --grep "GOAWAY|ConnectionTerminated|RemoteProtocolError"` 跨全部 9 个 boot：`-- No entries --`。
- `~/.local/share/ghc-api-proxy/` 与 `~/.local/share/copilot-api/` 下没有服务日志文件（只有一个 2026-07-18 的归档校验日志）。

### 1.4 Claude Code transcript（**事故那四条请求的唯一记录**）

`~/.claude/projects/-home-xp-src-ghc-api-proxy-py/3c6e81a2-0895-436a-8872-51a00fdedce3.jsonl`，第 8 条记录，时间戳 `2026-08-20T15:02:54.075Z`。

### 1.5 现网 `copilot-api-js` 源码与设计文档（**因果解释的来源**）

`~/src/copilot-api-js`。见第四节。

---

## 二、查询脚本

全部在 `/home/xp/.claude/jobs/3c6e81a2/tmp/`：

| 文件 | 内容 | 输出 |
|---|---|---|
| `analyze.py` | 基础遍历：覆盖范围、错误分类直方图、按天频率、按结束时刻聚簇、时长/大小分位、按模型/端点/小时的失败率 | `analyze-out.txt` |
| `analyze2.py` | 修复前后 blast radius 对照、同 pid 聚簇、危险率（hazard）分桶、条件化请求大小、失败时已收字节、并发度 | `analyze2-out.txt` |
| `analyze3.py` | 逐小时时间序列、部署窗口检验、条件化模型效应、最大同时失败事件转储、多受害者事件频率 | `analyze3-out.txt` |
| `ghc-history.db` | 本项目 history.db 的只读副本 | — |

分类判据（`analyze*.py` 中的 `TRANSPORT_PATTERNS`），按 `responseError` 子串匹配：

```python
("nghttp2_cancel",          "NGHTTP2_CANCEL"),
("nghttp2_other",           "NGHTTP2_"),
("closed_before_response",  "upstream stream closed before any response"),
("truncated",               "upstream stream truncated"),
("tls_timeout",             "TLS connect timeout"),
("dns",                     "getaddrinfo"),
("econnreset",  "ECONNRESET"), ("socket_hangup", "socket hang up"), ("epipe", "EPIPE"),
```

时区：宿主机是 `Etc/UTC`（`timedatectl` 确认）。**第一轮我按 +08 算错了 8 小时，已修正**；本文所有时刻均为 UTC。

---

## 三、频率（原样输出）

### 3.1 全体分类直方图

```
== transport-interruption class histogram (all time) ==
  nghttp2_cancel           479
  truncated                78
  closed_before_response   33
  tls_timeout              2
  dns                      2
  TOTAL 594  = 0.638% of generations
```

三类的语义各不相同，**不要混为一谈**：

- `NGHTTP2_CANCEL`（479）：流被 RST_STREAM(CANCEL) 掐断。中位已收 416 KB，说明是**内容已经流了很久之后**被掐。
- `upstream stream truncated: closed without message_stop / finish_reason`（78）：H2 层面干净结束，但语义上缺终止事件。这正是本项目 STR-04 修的那一类。
- `upstream stream closed before any response (rstCode=0)`（33）：`NO_ERROR` 关闭且**一个响应字节都没有**。33 条全部 < 2 KB。**这一类才是 GOAWAY / 边缘 drain 的形态。**

### 3.2 按天

```
  2026-07-17  n=   875  transport-fail=   0    0.00%
  2026-07-18  n=  2697  transport-fail=   0    0.00%
  2026-07-19  n=  1283  transport-fail=   0    0.00%
  2026-07-20  n=  2424  transport-fail=   2    0.08%
  2026-07-21  n=  3810  transport-fail=  11    0.29%
  2026-07-22  n=  5737  transport-fail=  27    0.47%
  2026-07-23  n=  3633  transport-fail=  15    0.41%
  2026-08-06  n=  2735  transport-fail=  50    1.83%
  2026-08-07  n= 15595  transport-fail= 235    1.51%
  2026-08-08  n= 20480  transport-fail= 178    0.87%
  2026-08-09  n=   406  transport-fail=   0    0.00%
  2026-08-10  n=  2726  transport-fail=  10    0.37%
  2026-08-11  n=  7915  transport-fail=  39    0.49%
  2026-08-12  n=  3471  transport-fail=   3    0.09%
  2026-08-13  n=  7992  transport-fail=   8    0.10%
  2026-08-14  n=  6124  transport-fail=  11    0.18%
  2026-08-15  n=  2189  transport-fail=   1    0.05%
  2026-08-16  n=  1317  transport-fail=   0    0.00%
  2026-08-17  n=   570  transport-fail=   1    0.18%
  2026-08-18  n=   854  transport-fail=   3    0.35%
  2026-08-19  n=   292  transport-fail=   0    0.00%
```

日率跨度 0.00% – 1.83%，将近两个数量级。**说「稳定 0.64%」是错的**，正确的说法是「基线 0.1–0.3%，会阵发到 1.5–1.8%」。

### 3.3 恢复掉的那部分（这个 0.64% 是不是下界？）

`v3_tracks.attempt_index` 记录上游 dispatch 的重试次数：

```
history-v3-260807.db:  max_attempt_index 0 → 71702 op；1 → 82；2 → 2；3 → 2
history-v3-260809.db:  0 → 39855；1 → 72
history-v3.db:         0 → 24428；1 → 97；2 → 14；3 → 2；4 → 3
history-v3-20260818:   0 → 1162；1 → 1；4 → 1
```

即约 273 条 operation 发生过重试，量级 0.2%。加上可见失败的 0.64%，**上游传输打断事件的真实总量在 1% 上下，不会是 5% 或 10%**。这条是**中等强度**：`attemptCount` 与 `attempt_index` 的语义我没有逐行读代码核实，只是从字段名与分布推断，且 buffered retry 是否会 bump `attempt_index` 我没有验证。

---

## 四、模式（优先证伪）

### 4.1 成批失败：真实存在，且已被现网服务修掉（**强证据**）

`analyze2.py` 输出：

```
-- PRE  (h2 multiplex, all concurrent streams share 1 session)
   window 2026-07-17 16:59:23 .. 2026-07-22 23:10:28
   generations=16392  transport-fails=33 (0.20%)
   classes: {'nghttp2_cancel': 10, 'closed_before_response': 20, 'truncated': 3}
   same-pid clusters (2s): sizes={1: 14, 2: 4, 3: 2, 5: 1} -> 19/33 = 57.6% of fails are in a batch
      n=5 @ 2026-07-22 22:09:27 pid=2708411 {'truncated': 2, 'closed_before_response': 3} durs=[19.0, 126.0, 206.3, 164.6, 21.9]
      n=3 @ 2026-07-21 21:25:17 pid=379686 {'closed_before_response': 3} durs=[16.0, 38.6, 33.8]
      n=3 @ 2026-07-22 22:09:30 pid=2708411 {'closed_before_response': 3} durs=[1.5, 1.3, 1.3]
      n=2 @ 2026-07-21 17:36:56 pid=3096364 {'closed_before_response': 2} durs=[9.7, 1.9]
      n=2 @ 2026-07-21 18:36:12 pid=3096364 {'closed_before_response': 2} durs=[10.1, 49.3]
      n=2 @ 2026-07-22 20:39:51 pid=2091381 {'closed_before_response': 2} durs=[6.9, 28.8]
      n=2 @ 2026-07-22 20:40:11 pid=2091381 {'closed_before_response': 1, 'truncated': 1} durs=[18.4, 18.9]

-- POST (N=1, one h2 session per concurrent request)
   window 2026-07-22 23:10:31 .. 2026-08-19 19:39:59
   generations=76733  transport-fails=561 (0.73%)
   classes: {'nghttp2_cancel': 469, 'closed_before_response': 13, 'truncated': 75, 'tls_timeout': 2, 'dns': 2}
   same-pid clusters (2s): sizes={1: 528, 2: 12, 3: 3} -> 33/561 = 5.9% of fails are in a batch
```

分界点取自 `~/src/copilot-api-js` 的提交 `b5892380f`（author date 2026-07-22 23:10:30 UTC）。**部署时刻未知，这个边界是近似的。** 但 07-23 之后 `closed_before_response` 从 20 掉到 13、同时总量涨了 17 倍，与设计意图完全一致。

配置项本身写得很清楚（`src/lib/config/schema.ts`）：

> Soft cap on concurrent streams multiplexed onto a SINGLE upstream h2 session (0 = unlimited). … **Default 1** — each concurrent request gets its own connection, so a session-level upstream teardown (GOAWAY / edge drain) takes down at most one in-flight request instead of every concurrent stream sharing the connection.

而设计文档 `docs/upstream-transport/2026-07-22-h2-pool-capacity-routing-and-pre-response-retry.md` 记的是一次**实时复现**：

```
| ② pre-commit 秒拒（3 条并发 opus） | 68/69/70 | 否 | 1.2–1.4s |
  决策 1 blast-radius 实时复现（3 条压同一死 session 被一起秒拒）
| ① 上游静默数分钟后死 | 57/58/63 | 是 | 126/164/206s |
  上游收下大请求后 0 帧干挂 2–3 分钟才 rstCode=0
| ③ mid-stream 截断 | 66/67 | 是 | 19–22s |
```

**这三组请求就是我在数据里挖出来的那个 n=8 簇**（`analyze3.py` 输出 J 节）：

```
  n=8  2026-07-22 22:09:27  pid=2708411  [PRE-mitigation]
      start=2026-07-22 22:09:08 dur=    19.0s rq=   610198 rs=     1467 claude-sonnet-5 :: "upstream stream truncated: closed without message_stop"
      start=2026-07-22 22:07:21 dur=   126.0s rq=   694292 rs=      906 claude-sonnet-5 :: [http2] upstream stream closed before any response (rstCode=0)
      start=2026-07-22 22:06:01 dur=   206.3s rq=   671075 rs=     1226 claude-sonnet-5 :: [http2] upstream stream closed before any response (rstCode=0)
      start=2026-07-22 22:06:43 dur=   164.6s rq=   267443 rs=     1066 claude-sonnet-5 :: [http2] upstream stream closed before any response (rstCode=0)
      start=2026-07-22 22:09:06 dur=    21.9s rq=   916578 rs=      932 claude-sonnet-5 :: "upstream stream truncated: closed without message_stop"
      start=2026-07-22 22:09:29 dur=     1.5s rq=  1135853 rs=      101 claude-opus-4.8 :: [http2] upstream stream closed before any response (rstCode=0)
      start=2026-07-22 22:09:29 dur=     1.3s rq=   522910 rs=      101 claude-opus-4.8 :: [http2] upstream stream closed before any response (rstCode=0)
      start=2026-07-22 22:09:29 dur=     1.3s rq=   913639 rs=      101 claude-opus-4.8 :: [http2] upstream stream closed before any response (rstCode=0)
```

时长 126/164/206s、19/21.9s、1.5/1.3/1.3s，与文档表格逐项对得上。**这是独立的双向确认**：文档里的实时复现记录，与数据库里的原始记录，指的是同一次生产事件。

多受害者事件的频率：

```
  PRE  span=5.26d  gens=16392  transport-fails=33 (6.3/day)  multi-victim events=6 (1.14/day)  victims/event=3.17
  POST span=27.85d gens=76733  transport-fails=561 (20.1/day) multi-victim events=16 (0.57/day) victims/event=2.19
```

**修复前：平均每天 1.14 次「一次打掉一批」的事件，每次平均 3.17 条受害者**，负载约 3100 请求/天。这是与本次事故形态最接近的数字。

需要说清的限定：PRE 窗口只有 33 条传输失败，**样本小**。57.6% 这个比例的置信区间很宽。但它不是孤证——现网仓库的提交信息、配置注释、设计文档三处独立记录了同一现象，而且我在数据里定位到了原始事件。**综合起来强到可据此改代码。**

**「随机独立故障」这个假说在 blast-radius 这一点上被证伪了。**

### 4.2 时长：真正的主导变量（**强证据**）

```
== C. HAZARD: is the failure rate proportional to time on the wire? ==
   bucket_s     at_risk   died   hazard/req   hazard_per_sec
   [    0,    5)     93125     10     0.00011   2.15e-05
   [    5,   10)     72874     13     0.00018   3.57e-05
   [   10,   20)     45276     18     0.00040   3.98e-05
   [   20,   40)     22752     24     0.00105   5.27e-05
   [   40,   80)      8964     40     0.00446   1.12e-04
   [   80,  160)      3029    141     0.04655   5.82e-04
   [  160,  320)       922    230     0.24946   1.56e-03
   [  320,  640)       219     99     0.45205   1.41e-03
   [  640, 9999)        37     19     0.51351   9.17e-04
```

`hazard/req` 从 0.011% 涨到 51%，跨越四个数量级。更关键的是**每秒**危险率也涨了约 70 倍（2.15e-05 → 1.56e-03）——**这不是「暴露时间更长所以更容易被随机事件打到」那种线性关系**，长流会被以远超比例的速度杀掉。跑过 160 秒的流有四分之一活不下来。

分位数对照：

```
  completed.durationMs         n= 91834 p10=   3,655 med=   9,666 p90=  37,775 p99= 128,295 max=1,678,813
  transportfail.durationMs     n=   594 p10=  33,737 med= 192,480 p90= 428,369 p99= 913,326 max=  935,171
```

**这与本次事故的关系**：那四条的时长是 5.3 / 5.8 / 12.6 / 15.9 秒，全部落在 0.011%–0.040% 的最低危险区。**所以本次事故不是这个机制。** 长流被杀是「常见但慢性」的问题；本次是「罕见但一次带走一批」的问题。两者要分开处理，别用一个数去估另一个。

### 4.3 请求大小：条件化之后信号消失（**证伪**）

粗看有信号（失败中位 1.44 MB vs 完成 0.94 MB）。但按时长分桶之后：

```
   duration bucket | completed med rq | fail med rq | fail n
   [    0,    5)       618,495     1,255,886     10
   [    5,   10)     1,010,867     1,041,174     13
   [   10,   20)     1,124,510       740,387     18
   [   20,   40)     1,120,664       996,497     24
   [   40,   80)     1,044,327       618,517     40
   [   80,  160)       816,624       620,484    141
   [  160,  320)       643,173     2,231,789    230
   [  320,  640)       732,122     2,362,672     99
   [  640, 9999)       888,886     2,162,094     19
```

20–160 秒这几桶里失败的请求**反而更小**。只有超过 160 秒的长流才显出「又大又慢」。

**结论：请求大小不是独立的驱动因素。** 本次事故那四条 329 KB – 1.7 MB，在完成请求的常规分布之内（完成中位 943 KB，p90 2.07 MB），**不算大**。`findings.md` 里「都不小」这个印象，我用数据不支持它。**这条是证伪，强度足够。**

### 4.4 模型：条件化之后信号完全消失（**证伪**）

粗看差 10 倍：

```
== transport-fail rate by responseModel (n>=200) ==
  claude-opus-5                n= 31929 fail=  54   0.17%
  gpt-5.6-sol                  n= 24260 fail= 410   1.69%
  gpt-5.6-terra                n= 14918 fail=  70   0.47%
  claude-sonnet-5              n= 13308 fail=  36   0.27%
```

按时长条件化之后：

```
   bucket_s               claude-opus-5       claude-sonnet-5           gpt-5.6-sol         gpt-5.6-terra
   [    0,   20)       13/ 25115= 0.05%       7/ 10806= 0.06%       8/ 15590= 0.05%       7/ 13110= 0.05%
   [   20,   80)        5/  6388= 0.08%      10/  1733= 0.58%      35/  7353= 0.48%       9/  1639= 0.55%
   [   80,  320)       23/   392= 5.87%      17/   741= 2.29%     270/  1180=22.88%      49/   159=30.82%
   [  320, 9999)       13/    34=38.24%       2/    28= 7.14%      97/   137=70.80%       5/    10=50.00%
```

**0–20 秒桶里四个模型全是 0.05%，一模一样。** 表观差异全部来自「gpt-5.6-sol 的请求跑得久」。80 秒以上还有残余差异（22.9% vs 5.9%），但那一段样本小且与推理时长深度纠缠，我不据此下结论。

**结论：模型选择不是驱动因素。这条是证伪。**

### 4.5 端点

```
  anthropic-messages           n= 92638 fail= 594   0.64%
  openai-responses             n=   483 fail=   0   0.00%
  openai-chat-completions      n=     2 fail=   0   0.00%
```

`openai-responses` 只有 483 条且零失败——**样本太小，答不了**，不要当成「Responses 端点更安全」。

### 4.6 一天中的分布：拒绝均匀，但不是固定时段（**中等强度**）

```
  overall rate 0.638%
    00h n=  2194 obs=  24 exp=   14.0 ratio= 1.71  <<<
    01h n=  1411 obs=  27 exp=    9.0 ratio= 3.00  <<<
    ...
    17h n=  3309 obs=  42 exp=   21.1 ratio= 1.99  <<<
    ...
    23h n=  4782 obs=  51 exp=   30.5 ratio= 1.67  <<<
  chi2 = 113.5 on 23 dof (critical 0.1% ~ 49.7)
```

χ² 远超临界值，**均匀假设被拒绝**。但逐日看，超额是少数发作贡献的，不是每天复现的窗口：

```
  2026-08-07
    17h n=  228 fail= 22  9.65% ######################
  2026-08-08
    17h n=  884 fail= 13  1.47% #############
```

17h 的尖峰基本由 2026-08-07 单日贡献。而 2026-08-06 20h 到 2026-08-08 中午是一整段连续的高发期（多数小时 1.5%–3.8%，基线 0.1–0.3%）。

**所以：证据支持「上游会进入若干小时到一两天的不健康期」，不支持「有一个每天重复的部署窗口」。** 后者这个具体猜想，被现有数据证伪。

### 4.7 并发度（**弱，仅存档**）

```
   concurrent peers in flight when a transport failure hit: mean=4.25
   baseline (every 37th completed, n=2492): mean=3.35
```

4.25 vs 3.35，方向对但差距小，而且有明显混杂：失败的请求活得更久，自然重叠更多同伴。**这条只存档，不能用于决策。**

### 4.8 一个必须剔除的伪模式

`analyze3.py` 的 J 节里最大的几个「同时失败」事件其实是 **`copilot-api-js` 自己的内部缺陷**，不是上游：

```
  n=10  2026-08-08 18:46:43  pid=1171081  [post-mitigation]
      ... 10 条全部 :: "[model-operation-record] candidate candidate:0 has 1 open dispatch(es)"
  n=5  2026-08-07 00:47:54  pid=521192
      ... 5 条全部 :: "Server is shutting down"    ← 是它自己在关闭
```

我的传输分类器（4.1 用的那个）已经把这两类排除在外。**记在这里是为了让下一个人不要把这些当成上游事件重新数一遍。**

---

## 五、本次事故那四条请求

### 5.1 能定位到什么

**在任何 History 数据源里都定位不到。** 三条原因：

1. `copilot-api-js` 的 history 最后一条是 2026-08-19 19:39:59，**不覆盖 08-20**；而且这四条走的是本项目的服务，不是它。
2. 本项目 history.db 里**没有一条生产流量**，最后一条是 14:17:47 的测试。
3. 即便当时开着 History，也记不下——`context.reply` gate 在 `terminal.seen`，无终止事件的流不写 History（`findings.md` 已登记）。

**唯一的记录是终端日志**，保存在 Claude Code transcript `3c6e81a2-…jsonl` 第 8 条（`2026-08-20T15:02:54.075Z`）里。原样四行：

```
[FAIL] 15:01:59 H1/H2 200 anthropic-messages/claude-opus-5  5.8s ↑1.7MB   ↓2.1KB: stream failed before a terminal event: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>
[FAIL] 15:01:59 H1/H2 200 anthropic-messages/claude-opus-5 12.6s ↑1.3MB   ↓5.9KB: stream failed before a terminal event: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>
[FAIL] 15:01:59 H1/H2 200 anthropic-messages/claude-opus-5  5.3s ↑386.0KB ↓595B:  stream failed before a terminal event: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>
[FAIL] 15:01:59 H1/H2 200 anthropic-messages/claude-opus-5 15.9s ↑329.5KB ↓593B:  stream failed before a terminal event: <ConnectionTerminated error_code:0, last_stream_id:2147483647, additional_data:None>
```

### 5.2 失败时已经收到了多少内容、到哪个语义位置

这是任务里点名要的一条，直接关系到后续「重试/续写/完成」的裁决。

| | 时长 | 推算起始 | 上行 | **下行** |
|---|---|---|---|---|
| 1 | 5.8s | 15:01:53.2 | 1.7 MB | **2.1 KB** |
| 2 | 12.6s | 15:01:46.4 | 1.3 MB | **5.9 KB** |
| 3 | 5.3s | 15:01:53.7 | 386.0 KB | **595 B** |
| 4 | 15.9s | 15:01:43.1 | 329.5 KB | **593 B** |

**四条全部拿到了 HTTP 200**，说明上游已经受理并开始响应；但下行 593 B – 5.9 KB，量级只够 Responses SSE 的开场（`response.created` + `response.in_progress` 一类）。第 3、4 条的 595 B 与 593 B 几乎相同，而它们的时长差了 3 倍（5.3s vs 15.9s）——**这两条在 15.9 秒里没有收到任何新增内容**，明显停在「上游在思考、还没吐第一个 token」的位置。

**语义位置的判断（中等强度）**：四条都停在**首个内容块之前**。我没有原始 SSE 帧可查，这个判断是从字节量 + 200 状态 + 两条几乎相同的 593/595 B 推出来的，不是直接观测。但如果成立，它对裁决 B（「在块级缓冲窗口内重试」）很有分量：`findings.md` 说 B 的前提「失败时下游零字节」当前未观测——**这四条的下行字节全部是上游到我方的量，而 Anthropic 侧一个内容块都还没成形，所以下游极可能确实是零字节**。这值得用一次针对性的观测去坐实（在 `stream_delivery` 里记录已交付给下游的字节数），而不是继续推断。

### 5.3 与历史形态的对比

本次形态是**第三种**，不完全等同于 `copilot-api-js` 的任何一类：

| 形态 | HTTP 200？ | 下行字节 | 我们这次 |
|---|---|---|---|
| `closed_before_response (rstCode=0)` | 否 | 101–748 B（33 条全 <2 KB） | — |
| `NGHTTP2_CANCEL` | 是 | 中位 416 KB | — |
| `truncated` | 是 | 中位 19.9 KB | — |
| **本次** | **是** | **593 B – 5.9 KB** | ← |

「拿到 200、但内容几乎为零、然后连接级终止」。最接近 `closed_before_response` 的**时机**（响应刚开始），但我们已经收下了 headers。这个差异很可能只是两边客户端栈的差别：Node 的 http2 在 GOAWAY 后是否已经把 headers 交付给上层，与 httpcore 的行为不必相同。**不要据此断言「上游对我们的行为与对它不同」。**

---

## 六、对本项目的直接推论

**本项目当前完全暴露在 blast radius 之下。** `src/app/server/composition.py`：

```python
def build_http_client(config: ProxyConfig) -> httpx.AsyncClient:
    options = transport_options(config)
    return httpx.AsyncClient(
        proxy=options.proxy,
        http2=options.http2,
        limits=httpx.Limits(keepalive_expiry=options.keepalive_expiry),
    )
```

没有任何「每连接并发流上限」。httpcore 会把同一 origin 的所有并发请求复用到一条 H2 连接上，直到上游 SETTINGS 的 `MAX_CONCURRENT_STREAMS` 用完为止——**这正是 `copilot-api-js` 在 2026-07-22 之前的状态，也正是它花一整个计划去消灭的东西**。而且 httpcore 1.0.9 **没有**对应的旋钮：它不提供 per-connection 流上限，无法像 `copilot-api-js` 那样配 N=1。

`findings.md` 待裁决表里的 C（降级 HTTP/1.1）写着「收益取决于回收的是单条连接还是整节点全部连接，当前证据无法区分」。**本次取证给了这个问题一个偏向性的答案**：修复前后 57.6% → 5.9% 的对照说明，「每条请求一条连接」这个动作在现网上确实把成批失败压下去了。如果上游回收的是整节点的全部连接，那这个修复不会有效——它有效，所以回收的（至少多数时候）是单条连接。

**这条是中等偏强**：对照是观测数据不是受控实验，修复部署时刻不精确，两段窗口的上游状态也可能变了。但它是目前唯一一份能区分这两个假说的证据，而且方向明确。

`http2: bool = True` 这个开关（`src/app/config/schema.py:97`）已经在 2026-08-20 加好了，是现成的实验手段。**HTTP/1.1 的代价是每条请求一次 TLS 握手**——考虑到我方请求上行常常超过 1 MB、时长中位近 10 秒，握手开销占比很小。

---

## 七、数据答不了什么

按重要性排序，**每一条都是真答不了，不要在报告里被当成结论**：

1. **本项目自己的传输失败频率，完全没有数据。** 本项目 History 里一条生产流量都没有，日志不落盘，不在 systemd 下所以 journald 也没有。本文所有频率数字都是 `copilot-api-js` 的，迁移到本项目需要假设「同一上游、同一账号、同一模型、相似负载」——前三条成立，第四条不成立（本项目负载远低）。**这是本次取证最大的缺口，也是最容易补的：把失败的流也写进 History。**

2. **不能直接数 GOAWAY 帧。** `copilot-api-js` 的 `responseError` 记的是它自己的错误分类，不是协议帧。它内部确实有 GOAWAY ledger（`src/lib/transport/http2-goaway-ledger.ts`）与 termination snapshot，数据落在 `v3_operation_arenas` / `manifest_gz` 的压缩 blob 里——**解出来需要复现它的 manifest 编码，本次没做**。所以「一帧 GOAWAY 打掉一批」这个假说，我是用**同 pid 同秒成批失败**这个代理指标验证的，不是直接看到 GOAWAY 帧。这是本次取证最值得追加的一步。

3. **事故当天（2026-08-20）没有任何 history 覆盖**，2026-07-24 .. 2026-08-05 有 13 天空洞。

4. **PRE 窗口只有 33 条传输失败**，57.6% 这个比例的样本量小。结论靠的是它与提交信息、配置注释、设计文档的三重吻合，不是这一个数字本身。

5. **修复部署的确切时刻不知道**，我用的是 commit author date。边界附近（07-22 23:10 到 07-23）的归类可能有几条错位。

6. **不知道 GOAWAY 来自源站还是边缘/中间 TLS 终止节点。** 这个 `findings.md` 已经登记为未决，本次数据也回答不了。

7. **`↓` 字节到底是上游到我方还是我方到下游**，我按项目记忆（`observability-describes-the-upstream-exchange`：`↓` 收自上游边到边计）理解为前者。5.2 节「下游可能零字节」的推论依赖这一点，**没有读代码核实**。

8. **恢复率（0.2%）的口径没核实。** 见 3.3。

9. **`openai-responses` 端点只有 483 条样本**，零失败说明不了任何事。

---

## 八、建议追加的三件事（都不需要新基础设施）

按 ROI 排序，**都是建议，不是我已经做了的事**：

1. **让失败的流也落 History。** 当前我们对自己的传输失败零观测能力，这是本次取证一路撞到的墙。`findings.md` 已把它登记为「未闭合的另一半」并指出它与 `terminal.seen` gate 的裁决绑定。
2. **在 `stream_delivery` 里记一个「已交付给下游的字节数」。** 这一个数字就能把裁决 B 的前提从「未观测」变成「已观测」，代价是一个计数器。
3. **解 `copilot-api-js` 的 manifest，把 GOAWAY 帧直接数出来。** 这能把 4.1 从「代理指标」升级成「直接观测」，也能回答第 6 条（帧里的 `additional_data` 可能带来源信息）。工作量中等，因为要复现它的 manifest 编码。

---

## 附：完整原样输出

`/home/xp/.claude/jobs/3c6e81a2/tmp/analyze-out.txt`、`analyze2-out.txt`、`analyze3-out.txt`。脚本可直接重跑（只读，无副作用）：

```bash
cd /home/xp/.claude/jobs/3c6e81a2/tmp
/home/xp/src/ghc-api-proxy-py/.venv/bin/python analyze.py
/home/xp/src/ghc-api-proxy-py/.venv/bin/python analyze2.py
/home/xp/src/ghc-api-proxy-py/.venv/bin/python analyze3.py
```

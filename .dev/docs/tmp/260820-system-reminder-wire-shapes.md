# `<system-reminder>` 在真实上行 body 里的形态普查

日期：2026-08-20。取证对象：copilot-api-js 抓下的真实客户端上行请求体。只读，未对任何 history 库执行写入、VACUUM 或删除。

## 0. 口径、方法与可信度

### 数据源与提取路径

| 项 | 值 |
|---|---|
| 库 | `~/.local/share/copilot-api/history-v3-20260815-183721.db`、`-20260816-160151.db`、`-20260817-050754.db`、`-20260818-044224.db` |
| 时间窗 | 2026-08-15 18:41:06 → 2026-08-19 19:39:59 |
| 操作数 | 3440，全部 `endpoint = anthropic-messages`（798 + 906 + 572 + 1164） |
| 请求体总字节 | 4,385,680,151 |
| 消息总条数 | 2,069,992（user 721,745 / assistant 718,303 / **system 629,944**） |
| `tool_result` 块总数 | 754,573 |

`from_history.py` 只做响应侧 frame，它那句「history records no request body」在本库上是**过时的**：请求体确实在库里，但不在 `v3_objects` 的 `payload` 里，而是「骨架 + 序列」两段式存储。提取路径如下，已照抄 `from_history.py` 的 zstd + manifest 惯例：

1. `v3_operations.manifest_gz`（zstd → JSON）里的 `record.arena.payloads` 给出每个 payload handle 的 `origin.stage` / `origin.track` / `provenance` / `derivedFrom` / `transformId`。
2. `manifest.objectHashes["payload:N"]` → `v3_objects`（kind `payload-skeleton`）是把 `messages` / `system` / `tools` 置为 `null` 的骨架。
3. `manifest.payloadSequences["payload:N"]` 给出每个被抽空字段的 `rootHash` + `length` + `overlays`。从 `rootHash` 沿 `v3_sequence_nodes.parent_hash` 回溯到头，收集 `item_hash`，逐个到 `v3_objects`（kind `sequence-item`）取回，反转即得原序列；再把 `overlays` 打回去（本例是 `cache_control` 标记）。

**取的是变换图的根**：`payload:0` 的 `origin = {stage: "ingress", track: "client"}`、`provenance = "source"`，无 `derivedFrom`。`payload:1`（`effective-request`）与 `payload:2`（`wire-request`）都是 `derived`，`transformId` 分别为 `request:effective` 与 `request:prepare-wire`。全文只使用 `payload:0`。

### 两项自证（证据强度：强，足以据此行动）

**重建是逐字节正确的。** 重建后 `orjson.dumps` 长度与 `summary_json.requestBytes` 完全相等。样本 `req_1786896109832_792`：重建 2,405,060 B，`requestBytes` 2,405,060。

**这批数据里 copilot-api-js 没有改写 reminder。** 抽 5 个操作对比 `payload:0`（ingress）、`payload:1`（effective-request）、`payload:2`（wire-request）三者的 `<system-reminder>` 出现次数：

```
req_1787168399205_1145  payload:0 opens=8  payload:1 opens=8  payload:2 opens=8
req_1787150173334_1144  payload:0 opens=8  payload:1 opens=8  payload:2 opens=8
req_1787150147037_1143  payload:0 opens=8  payload:1 opens=8  payload:2 opens=8
req_1787150021424_1142  payload:0 opens=8  payload:1 opens=8  payload:2 opens=8
req_1787149988111_1141  payload:0 opens=8  payload:1 opens=8  payload:2 opens=8
```

字节数差异极小（effective 比 ingress 多 1078 B，wire 多 812 B），是 model 映射与 header 相关字段，不涉及 reminder。所以本报告的数字既是「客户端原始发来的」，也恰好等于「上一代服务发出去的」——这两件事在本窗口内不需要区分。

### 一个必须先说清楚的混淆源

**语料被用户自己的开发内容严重污染。** 用户在这段时间里正在开发的就是 reminder 剥离功能，于是仓库源码、文档、配置、grep 输出、CLAUDE.md 规则正文里到处是**字面字符串** `<system-reminder>`，它们经由 Read/Bash 结果和系统提示进入上行 body。

因此全文严格区分两类：

- **well-formed（真注入）**：能配上 `<system-reminder> … </system-reminder>` 成对标签的。
- **unclosed / 字面提及**：只有开标签、配不上的，一律是被读进来或被引用的文本，不是 Claude Code 注入的。

全语料 14,756 次 `<system-reminder>` 开标签中，**well-formed 只有 5,816 次（39.4%）**，其余 8,940 次（60.6%）是字面提及。不做这个切分会把结论整个搞反。

---

## 1. `<system-reminder>` 到底出现在哪（Q1）

### 1.1 well-formed（真注入），按结构路径

`n = 5816`。字节数为 reminder 自身（含标签）的长度，按 wire 出现次数加权。

| 结构路径 | 块类型 | 命中次数 | 占比 | 字节 |
|---|---|---:|---:|---:|
| `messages[*].content[*].text` | `text` | 3445 | 59.23% | 372,028,331 |
| `messages[*].content`（content 是裸字符串） | — | 1622 | 27.89% | 2,306,402 |
| `messages[*].content[*].content` | `tool_result`，**字符串形态** | 542 | 9.32% | 97,164 |
| `messages[*].content[*].input.prompt` | `tool_use` | 119 | 2.05% | 4,672 |
| `messages[*].content[*].input.command` | `tool_use` | 44 | 0.76% | 2,068 |
| `messages[*].content[*].input.content` | `tool_use` | 44 | 0.76% | 2,068 |

对照用户点名的几个位置：

| 用户问的位置 | 结果 |
|---|---|
| `tool_result` 的 `content`，**字符串形态** | 542 次（9.32%），是 tool_result 里的**全部** |
| `tool_result` 的 `content`，**块列表形态** | **零命中**。查询即上表，路径 `messages.*.content.*.content.*.text` 一次都没出现 |
| user 轮里独立的 `type == "text"` 块 | 3445 次（59.23%），字节占比 99.35% |
| `system` 数组里 | **well-formed 零命中** |
| 其它位置 | `messages[*].content` 裸字符串 1622 次；`tool_use.input.*` 共 207 次（这些是用户自己写给工具的文本，不是注入） |

`tool_result.content` 形态分布佐证（近 100 个请求，49,086 个 tool_result 块）：`str` 48,400 / `list` 686。`list` 形态只出现在 `Agent`（490）与 `SendMessage`（196），**Read 的 tool_result content 在本语料中 100% 是字符串**（1372/1372）。

### 1.2 unclosed（字面提及），按结构路径

`n = 8940`。这些**不是**注入，列出是为了说明 `system` 与 `tools` 的「命中」从何而来。

| 结构路径 | 次数 | 占比 | 实际是什么 |
|---|---:|---:|---|
| `system[*].text` | 3322 | 37.16% | 用户 CLAUDE.md / rules 正文里引用了这个 tag（如 `injected-reminders-may-be-wrong` 一条） |
| `messages[*].content[*].content`（tool_result） | 2724 | 30.47% | Read/Bash 读到的本项目源码、文档、配置、grep 输出 |
| `tools[*].description` | 2372 | 26.53% | 本 env 的 skill description 里逐字引用了这个 tag |
| `messages[*].content[*].input.new_string` | 308 | 3.45% | 用户往文件里写这个字符串 |
| 其余 | 214 | 2.39% | 同类 |

**所以对「`system` 数组里有没有」的直接回答是：零。** 3322 次全部是用户自己规则正文里的字面提及，一次真注入都没有。`tools[]` 同理，2372 次全部是 skill 描述文本。

---

## 2. Read 工具结果里的 reminder（Q2）

映射方式：在同一个 body 内先扫全部 assistant 轮的 `tool_use` 块建 `id → name`，再用 `tool_result.tool_use_id` 反查。3440 个请求各自独立建映射。

### 2.1 按工具名归类的 well-formed 命中

| 工具 | well-formed 次数 | 占 tool_result 命中 | 字节 |
|---|---:|---:|---:|
| Bash | 171 | 31.5% | 15,928 |
| **Read** | **371** | **68.5%** | **81,236** |
| 其它工具（Edit/Write/Agent/…） | 0 | 0% | 0 |

分母：`Read` 的 tool_result 块共 **44,076** 个，含 well-formed reminder 的是 **371** 个 → **0.84%**。
（另有 1354 个 Read 结果含 `<system-reminder>` 字面串，差额 983 个是读到了本项目自己的源码文档。）

工具侧 tool_result 块总量（供参考）：Bash 550,567 / Edit 94,853 / Read 44,076 / Write 27,789 / SendMessage 13,550 / Agent 9,565 / TaskOutput 5,455 / AskUserQuestion 4,083 / Skill 3,422 / EnterWorktree 490 / ExitWorktree 352 / WebFetch 306 / TaskStop 44 / WebSearch 21。

### 2.2 Read 结果里出现的**全部**变体，逐字全文

去重后只有两种。两种都给出完整样本（长度不足 300 字节，无截断）。

**变体 A** — `sha256[:16] = 2be865614a36dd51`，出现 296 次，241 字节。位置：**贴在 tool_result content 的最前面**（`at_start = 296/296`，`at_end = 0/296`，宿主串中位长度 482 B，即 reminder 之后还跟着文件内容）。

```
<system-reminder>This memory is 30 days old. Memories are point-in-time observations, not live state — claims about code behavior or file:line citations may be outdated. Verify against current code before asserting as fact.</system-reminder>
```

**变体 B** — `sha256[:16] = b6d0359f68eb8e4b`，出现 75 次，132 字节。位置：**整个 tool_result content 就是它**（`at_start = at_end = whole = 75/75`，宿主串长度就是 132）。

```
<system-reminder>Warning: the file exists but is shorter than the provided offset (2076). The file has 2074 lines.</system-reminder>
```

### 2.3 结论（证据强度：强，足以据此行动；作用域见 §6）

**用户假设的那种「通用的、与文件无关的、每次都一样的安全提醒」，在这 3440 个真实上行 body 的 44,076 个 Read 结果里，一次都没有出现。**

实际出现的两条，都**不是**通用样板：

- 变体 A 只在读 memory 文件时出现，且 `30 days old` 里的天数随文件而变（本窗口内碰巧只观测到一个取值）。它告诉模型「这份内容可能过期」——这是真实信号。
- 变体 B 只在 `offset` 越过文件末尾时出现，正文里的 `(2076)` 与 `2074 lines` 都是本次调用的实参与实测值。它是**唯一的返回内容**，剥掉等于把整个工具结果清空。

**剥掉这两条会改变模型被告知的内容，且两次都是往坏的方向改。** 剥变体 A 会让模型把一份 30 天前的观察当成 live state（这恰好是用户 memory 索引里 `verifying-authoritative-claims` 想防的失效）；剥变体 B 会让模型看到一个空结果，无法区分「文件为空」与「offset 越界」。

### 2.4 Bash 结果里的三种（全部是误报，仅供对照）

| sha | 次数 | 字节 | 内容 |
|---|---:|---:|---|
| `8f0f03c74797b8dc` | 88 | 47 | `<system-reminder>\nBE BRIEF\n</system-reminder>`（**字面反斜杠 n**，是测试 fixture 源码） |
| `1ba3c20b49a2832f` | 39 | 88 | `<system-reminder>\n<total_tokens>… tokens left</total_tokens>\n</system-reminder>`（同样是字面 `\n`，JSON 输出） |
| `0a4fc999f56929b7` | 44 | 190 | 一段 TypeScript 类型定义，`ReminderSegment` 的注释里跨行引用了开闭标签，被正则误配 |

三者 `at_start = at_end = 0`，都嵌在更长的输出中间。**Bash 结果里没有任何真注入。**

---

## 3. `tool_result` 块上有没有 `tool_name` 字段（Q3）

在 754,573 个真实 wire 上的 `tool_result` 块上做的全字段频次统计：

| 字段名 | 次数 | 占比 |
|---|---:|---:|
| `content` | 754,573 | 100.00% |
| `tool_use_id` | 754,573 | 100.00% |
| `type` | 754,573 | 100.00% |
| `is_error` | 559,020 | 74.08% |
| `cache_control` | 159 | 0.02% |

字段集合组合：

| 组合 | 次数 |
|---|---:|
| `content` \| `is_error` \| `tool_use_id` \| `type` | 558,891 |
| `content` \| `tool_use_id` \| `type` | 195,523 |
| `cache_control` \| `content` \| `is_error` \| `tool_use_id` \| `type` | 129 |
| `cache_control` \| `content` \| `tool_use_id` \| `type` | 30 |

**`tool_name` 零命中：0 / 754,573。** 也没有 `name`、`tool`、`toolName` 或任何近似字段——上表就是出现过的全部字段名，没有第六种。

这在真实 wire body 上复核了用户在转录里测得的 859/859 结论，样本量放大了约 878 倍，且换了一个完全独立的取证面（转录 vs 上行请求体）。**经 `tool_use_id` 反查工具名是唯一可行的路径，这一点是确定的。**

---

## 4. 剥掉 Read 结果里的 reminder 能省多少（Q4）

| 指标 | 值 |
|---|---|
| 全语料 Read-reminder 字节 | 81,236 |
| 全语料请求体字节 | 4,385,680,151 |
| 占比 | **0.001852%** |
| 3440 个请求里**能省到东西**的 | **371 个（10.78%）** |
| 其余 3069 个请求 | 省 0 字节 |
| 在能省的那 371 个上：平均 | 219 B |
| 在能省的那 371 个上：最大 | 241 B |
| 在能省的那 371 个上：占自身 body 平均 | 0.01077% |
| 在能省的那 371 个上：占自身 body 最大 | 0.01718% |
| **全体平均** | **23.6 B / request** |

### 几个大请求样本

10 个最大的请求（本语料 body 字节前十）：

| body 字节 | Read-reminder 字节 | 占比 | 全部 well-formed reminder 字节 | 占比 | operation |
|---:|---:|---:|---:|---:|---|
| 2,813,017 | **0** | 0.00000% | 112,652 | 4.005% | `req_1787066497351_329` |
| 2,806,538 | **0** | 0.00000% | 112,652 | 4.014% | `req_1787066449202_328` |
| 2,805,111 | **0** | 0.00000% | 112,652 | 4.016% | `req_1787066429015_327` |
| 2,803,545 | **0** | 0.00000% | 112,652 | 4.018% | `req_1787066408236_326` |
| 2,801,678 | **0** | 0.00000% | 112,652 | 4.021% | `req_1787066094597_325` |
| 2,799,947 | **0** | 0.00000% | 112,652 | 4.023% | `req_1787066082379_324` |
| 2,798,087 | **0** | 0.00000% | 112,652 | 4.026% | `req_1787066062329_323` |
| 2,792,380 | **0** | 0.00000% | 112,652 | 4.034% | `req_1787065923491_322` |
| 2,790,722 | **0** | 0.00000% | 112,652 | 4.037% | `req_1787065910638_321` |
| 2,789,090 | **0** | 0.00000% | 112,652 | 4.039% | `req_1787065887993_320` |

**最大的十个请求，一个字节都省不到。** 那 112,652 B 全部来自 §5 排名第一的 claudeMd 注入，与 Read 无关。

按 4 字符/token 的粗算，23.6 B/request 约合 6 个 token/请求。这个量级低于单次请求的测量噪声。

---

## 5. 普查：还有哪些高频重复、与本轮无关的注入片段（Q5）

分类方法：对每条消息的字符串内容（`content` 裸字符串、`text` 块）做前缀正则归族。字节数取整条字符串长度（因为这些注入独占一条消息），唯一例外是 `budget:total_tokens`，它是贴在别的内容前面的短标签，单独按标签自身长度计。

| 排名 | family | 总字节 | 占 body | 出现次数 | 涉及请求 | **单请求最多** | 平均 B/请求 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `reminder:claudeMd` | 372,009,217 | 8.48% | 3,349 | 3,349 | 1 | 108,142 |
| 2 | `note:file-modified` | 119,500,907 | 2.72% | 17,406 | 1,556 | **45** | 34,739 |
| 3 | `hook:PostToolUse` | 95,043,753 | 2.17% | 60,052 | 2,300 | **84** | 27,629 |
| 4 | `note:file-changed` | 47,709,497 | 1.09% | 6,596 | 585 | **23** | 13,869 |
| 5 | `budget:total_tokens`（仅标签） | 28,937,718 | 0.66% | 590,414 | 2,953 | **763** | 8,412 |
| 6 | `compaction:summary` | 26,440,862 | 0.60% | 1,711 | 1,711 | 1 | 7,686 |
| 7 | `list:skills` | 25,959,905 | 0.59% | 1,113 | 1,069 | 2 | 7,546 |
| 8 | `nudge:task-tools` | 15,423,680 | 0.35% | 34,095 | 1,292 | **71** | 4,484 |
| 9 | `list:agents` | 13,262,620 | 0.30% | 355 | 355 | 1 | 3,855 |
| 10 | `mcp:disconnected` | 12,679,010 | 0.29% | 482 | 482 | 1 | 3,686 |
| 11 | `hook:SessionStart` | 12,066,562 | 0.28% | 306 | 306 | 1 | 3,508 |
| 12 | `reminder:background-task` | 2,311,930 | 0.05% | 1,626 | 496 | 4 | 672 |
| 13 | `mcp:instructions` | 1,841,541 | 0.04% | 1,269 | 1,269 | 1 | 535 |
| 14 | `reminder:other` | 20,376 | 0.00% | 92 | 92 | 1 | 6 |

供对照：**Read reminder 全语料 81,236 B**，排在这张表最后一名的四分之一。

### 按「值不值得剥」重排的候选

#### 候选 1：`nudge:task-tools` —— 最干净的剥离对象

15.4 MB，34,095 次，**单请求最多 71 次，每次逐字相同的 421 字节**。位置：`role: "system"` 的裸字符串消息，散布在 messages 中段。

逐字全文：

```
The task tools haven't been used recently. If you're working on tasks that would benefit from tracking progress, consider using TaskCreate to add new tasks and TaskUpdate to update task status (set to in_progress when starting, completed when done). Also consider cleaning up the task list if it has become stale. Only use these if relevant to the current work. This is just a gentle reminder - ignore if not applicable.
```

风险：**低**。文本本身声明自己是 gentle reminder、可忽略；同一请求里出现 71 份完全相同的副本，其中至多一份（最后一份）反映当前状态，其余 70 份是历史轮次的残留。保留最后一次出现、删除全部更早的副本，模型被告知的内容不变。若整族全删，则等于关掉一个 nudge——这是产品行为变更，需要用户裁决，不应由实现自行决定。

#### 候选 2：`budget:total_tokens` —— 重复度最高

590,414 次，**单请求最多 763 次**，仅标签就 28.9 MB。形如：

```
<total_tokens>14240597 tokens left</total_tokens>
```

风险：**低到中**。除最后一次外全部是陈旧数字，语义上已经失效，且一个请求里出现七百多个互相矛盾的余额读数本身就是噪声。但它是本 harness 自己贴上去的（不是 Claude Code 原生），剥它属于改本地 harness 行为，先确认它由谁产生。

#### 候选 3 / 4：`note:file-modified` 与 `note:file-changed` —— 字节最大，但**不能整族剥**

合计 167 MB（3.81% of body），单请求最多 45 + 23 条。每条都内嵌**完整的变更片段或整份新文件内容**（观测到的单条最大 42,620 B）。

样本（`note:file-modified`，774 B）：

```
Note: /home/xp/src/ghc-api-proxy-py/src/app/ghc_client/headers.py was modified, either by the user or by a linter. This change was intentional, so make sure to take it into account as you proceed (ie. don't revert it unless the user asks you to). Don't tell the user this, since they are already aware. Here are the relevant changes (shown with line numbers):
48	    if vision:
49	        headers["copilot-vision-request"] = "true"
50	    if model_request_headers:
51	        protected = {name.lower() for name in headers}
52	        headers.update(
53	            {
54	                name: value
55	                for name, value in model_request_headers.items()
56	                if True  # MUTANT: protection removed
57	            }
58	        )
59	    return headers
```

样本（`note:file-changed`，8616 B，此处截前 300 B）：

```
Note: /home/xp/src/ghc-api-proxy-py/src/app/lifecycle/pidfile.py changed on disk since you last read it. That's usually deliberate, so take it as the current state rather than reverting it; if the change looks wrong, say so rather than undoing it yourself — otherwise no need to call it out. Here are the relevant changes (shown with line numbers):
```

风险：**整族剥离为高**——每条携带不同的、真实的、模型未必从别处知道的变更内容。
可安全回收的部分：**同一路径的多条通知里，只有最后一条描述当前状态**。按 `Note: <path> ` 归组、只保留每个路径的最后一条，是无信息损失的压缩。上表的 17,406 次分布在 1,556 个请求（平均 11.2 条/请求，最多 45 条），去重收益可观且不改变模型被告知的最终状态。这条需要用户确认后再做，因为「最后一条描述当前状态」这个前提依赖 Claude Code 生成这些通知的实现，本次未从代码侧验证，仅从文本语义推断。

#### 候选 5：`hook:PostToolUse` —— 单请求最多 84 条，逐条不同

95 MB。样本（449 B，本项目自己的 no-hard-wrap hook 产出）：

```
PostToolUse:Write hook additional context: no-hard-wrap：/home/xp/src/ghc-api-proxy-py/src/app/ghc_client/config.py 有 1 处疑似硬折行（句子中间断行）。
  第 13 行  …模块的 `AppSettings`——库不应该知道宿主的配置模型。调用方负责把自己的  ⏎  设置映射成本类型。…
这是**候选不是判决**：并列条目、命令用法块、文件清单、参数表、表格都会被误报，它们本来就该各占一行。
上面的片段是**截断**的，可能正好截掉行首的结构标记。判断前请打开那一行看完整内容，别只凭片段下结论。
确属折断时的改法：**一次只处理一处、只把这两行接成一行**。
明确不要做的三件事——① 不要整段重排（reflow）；② 不要用 `MultiEdit` 或脚本批量处理这些位置，实测会把并列条目接坏；③ **不要以「把警告清零」为目标**，判定误报就留着它，本工具不要求归零。
```

风险：**中到高**。每条对应一次具体的工具调用与具体的文件位置，是真信息。但**同一 hook 的固定说明段落在同一请求里重复了最多 84 遍**——上例中「这是候选不是判决 …… 本工具不要求归零」这一大段每次都一模一样，只有前两行随文件变化。这是用户自己的 hook，压缩它属于改自己的 hook 输出（把固定说明只在首次出现时给出），成本最低、收益远高于剥 Read reminder。**这是本次普查里我个人推荐优先处理的一项**，但它不在代理层，而在 hook 侧。

#### 候选 6：`list:skills` / `list:agents` / `mcp:disconnected` / `hook:SessionStart`

这四族合计 64 MB，特点是**每请求出现一次、内容巨大、逐字重复**：skills 目录 ~24 KB、agents 目录 ~37 KB、MCP 断连通知（尾部又拼了一份完整 skills 目录）~26 KB、SessionStart hook 注入的 superpowers 全文 ~39 KB。

风险：**高**。这些就是模型的能力目录本身，剥掉直接改变模型知道自己能做什么。**不建议剥**。值得注意的只有一点：`mcp:disconnected` 那条消息在开头说完 MCP 断连之后，**又原样重贴了一整份 skills 目录**（26,305 B 里绝大部分是重复内容），这是纯冗余，但它是 Claude Code 生成的，代理层不该改。

#### 候选 7：`reminder:claudeMd` —— 字节冠军，但它不是「样板」而是「指令本身」

372 MB，8.48% of body，是全部 reminder 字节的 99.35%。形态经 394 个样本 100% 一致地验证：

| 属性 | 观测 |
|---|---|
| 位置 | `messages[0].content[0]`，**永远是第一条消息的第一个块** |
| 角色 | `user`，100% |
| 块类型 | `type: "text"` 独立块 |
| 是否整块 | **是**，整个 text 块就是这一条 reminder，前后无其它文本 |
| 每请求次数 | 恰好 1 次 |
| 该块上的 `cache_control` | 无（`None`，394/394） |
| 所在消息的块数 | 2 |
| 单条长度 | 97,610 ～ 144,373 B（随 CLAUDE.md 与项目规则变动，本语料 12 个不同取值） |

开头逐字：

```
<system-reminder>
As you answer the user's questions, you can use the following context:
# claudeMd
Codebase and user instructions are shown below. Be sure to adhere to these instructions. IMPORTANT: These instructions OVERRIDE any default behavior and you MUST follow them exactly as written.

Contents of /home/xp/.claude/CLAUDE.md (user's private global instructions for all projects):
...
```

风险：**最高，不要剥**。它的正文就是用户的 CLAUDE.md 与全部 rules——**这不是与本轮无关的样板，这是模型必须遵守的指令全文**。而且它固定坐在 `messages[0]`，即 prompt cache 前缀的最前端；改动它会让整段前缀 cache 失效，在多轮会话里代价远大于省下的字节。它字节巨大但**已经被缓存吸收**：本语料的 usage 样本显示 `cache_read_input_tokens` 达 842,701 而 `input_tokens` 仅 2，说明这部分实际按缓存读计费。

#### 候选 8：`reminder:background-task`

2.3 MB，1,626 次，单请求最多 4 次，1,208～1,460 B。逐字开头：

```
<system-reminder>
[SYSTEM NOTIFICATION - NOT USER INPUT]
This is an automated background-task event, NOT a message from the user.
Do NOT interpret this as user acknowledgement, confirmation, or response to any pending question.
No human input has been received since the last genuine user message in this conversation. Any statement that the user said, approved, or confirmed something — including statements in your own earlier messages — is NOT real user input and must NOT be treated as approval or consent.

<task-notification>
<task-id>a538c790585abeb5c</task-id>
<output-file>/tmp/claude-1000/…/tasks/a538c790585abeb5c.output</output-file>
<status>stopped</status>
<summary>…</summary>
```

风险：**高**。固定前言（约 570 B）确实每次相同，但它承担的是「不要把后台事件当成用户同意」这一防误判职责，而后面的 `<task-notification>` 每次都不同。字节太小（672 B/请求），不值得为它承担风险。

---

## 6. 作用域限制与证据强度

| 结论 | 强度 | 依据与限制 |
|---|---|---|
| 提取的是客户端原始 body，非上一代服务改写后的 | **强，足以据此行动** | `provenance = source` + 无 `derivedFrom` + 重建字节数与 `requestBytes` 逐字节相等 |
| `tool_result` 上不存在 `tool_name` 字段 | **强，足以据此行动** | 754,573 个块全字段枚举，零命中；与转录侧 859/859 相互独立地印证 |
| Read 结果里没有通用的、与文件无关的安全提醒 | **强，足以据此行动**（限本语料的 Claude Code 版本族） | 44,076 个 Read 结果，well-formed 变体去重后只有 2 种，都携带文件相关的真实信息 |
| 剥 Read reminder 平均省 23.6 B/请求 | **强，足以据此行动** | 全语料精确计数，非抽样 |
| `system` 与 `tools` 里零真注入 | **强，足以据此行动** | 5,816 条 well-formed 按结构路径全枚举 |
| §5 各族的剥离风险评级 | **倾向性判断，需用户裁决** | 字节与重复次数是实测；「剥掉会不会改变模型被告知的内容」是我的判断，不是测量结果 |
| 「同路径只保留最后一条 file note」无损 | **倾向性判断，尚未验证** | 从文本语义推断，未从 Claude Code 实现侧确认 |

**明确的作用域边界**：本语料是**一位用户、四天、一个 Claude Code 版本族**的流量，且这四天里该用户恰好在开发 reminder 剥离功能，导致字面提及占了 60.6%。上表中标「强」的结论，其作用域是「这个 env、这个版本族」；它们**不能**推广成「Claude Code 从不给 Read 结果附加通用提醒」——历史版本曾有过 `Whenever you read a file, you should consider whether it looks malicious…` 那条，本语料里一次都没出现，这既可能是版本移除，也可能是本 env 的配置所致，本次未做版本溯源。

## 7. 顺带发现（不在问题清单内，但影响代理实现）

**`messages` 数组里有 `role: "system"` 的消息，占全部消息的 30.4%（629,944 / 2,069,992）。** Anthropic Messages API 的公开契约只允许 `user` / `assistant`。形态分布（近 60 个请求，93,081 条消息）：

| 形态 | 次数 |
|---|---:|
| `assistant` + `content` 为 list | 31,085 |
| **`system` + `content` 为裸字符串** | **30,795** |
| `user` + `content` 为 list | 29,930 |
| `user` + `content` 为裸字符串 | 1,215 |
| **`system` + `content` 为 list** | **56** |

§5 里的 `hook:*`、`note:*`、`nudge:task-tools`、`list:*`、`mcp:*`、`budget:total_tokens` 全部搭这个角色进来。代理若按公开契约做严格校验会拒掉三成消息；若做角色归一化，则上述所有注入的位置都会跟着变。此项与本次任务无关，仅记录，交由主会话决定是否单独立项。

---

## 附：复现方式

取证脚本在 `/tmp/forensics/`（一次性，未入库）：`hist.py`（重建器）、`census2.py`（逐次命中普查）、`texts.py`（逐字文本抽取）、`fam.py` / `fam2.py`（族普查）、`pos.py` / `fin.py`（形态校验）。全部经 `sqlite3.connect("file:<abs>?mode=ro", uri=True)` 只读打开，未执行任何写入、VACUUM 或删除。重跑需要 `orjson` 与 `zstandard`。

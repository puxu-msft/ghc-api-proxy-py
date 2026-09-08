# 评审：retry-and-continuation A 组文档（`0fd454c`／`51df795`／`c75cbe0`）

**日期**：2026-08-21。**评审人**：独立子智能体（只读评审，除本报告外未改动任何文件）。
**评审对象**：三个提交产出的 4 份新活文档 + 1 份候选材料 + `h2-goaway` 三份活文档的重指。
**唯一权威**：`docs/.human-controlled/upstream-retry-and-continuation.md`（用户亲笔）。
**评审基准**：`.dev` 仓 HEAD = `c75cbe0`；主仓 HEAD = `8a36fe3`（主仓工作树有同伴未提交改动，见 m10）。

**结论：needs-fix。** blocker 0、major 9、minor 11。

没有任何一条与权威文档相违背或改写其含义——**这一点是逐条比对过的**（判据见第 6 节）。所有 major 都是内部一致性、证据强度与「候选 vs 既定」边界的问题。

---

## 1. Major

### M1. `status.md:96` 拿未挂载的 legacy 文件当 live 证据用，违反本文件自己第 9 行的告警

**位置**：`.dev/docs/upstream/retry-and-continuation/status.md:96`

原文：

> **`usage` 排除在 token 校准之外**——不需要。校准只学输入侧（`token_calibration.py:53-63`，`input_tokens + cache_read + cache_creation` 配 `estimate_anthropic_input`）……

**为什么错**：该文件的实际路径是 `src/app/hooks/builtin/token_calibration.py`，而**同一份 status.md 的第 9 行**已经写明：

> ⚠️ `app/delivery/`、`pipeline/executor.py`、`app/hooks/` 是**未挂载的 legacy 链路**。按它们读会把结论读反——本主题的所有代码事实都取自 live 链路。

已核实 `app/hooks` 确实不可达 live 链路：`src/app/server/pipeline_app.py` 与 `src/app/server/composition.py` 都不 import `app.hooks`；引用它的是 `app/runtime.py`、`app/server/app_factory.py`（legacy 入口）、`app/pipeline/executor.py`（status.md 自己标为 legacy）、`app/anthropic/client.py`。

live 链路自己的校准在 **`src/app/server/handler.py:234-303`**（`pipeline_app.py:43` import 了它）：`estimate_anthropic_input(_countable(context.payload))` → `calibration.learn(protocol, route.model_id, estimate, result.tokens)`，学习点在 **count_tokens 路径**，`result.tokens` 是上游 count 接口的回答，**与任何一次模型响应的 `usage` 无关**。

**建议怎么改**：把引用换成 `src/app/server/handler.py:234-303`，并把论证改成更强的那一版——live 链路的校准根本不从响应 `usage` 学习，所以「`usage` 排除在校准之外」不是取舍而是现状。归档报告 `archive-proxy-side-continuation/reports/spec-stream-continuation.md:160` 也引了这个 legacy 文件，但那是时间点记录，**不要改**。

---

### M2. `status.md:18` 把调查报告的「我没有找到可达路径」升级成了「不可达」

**位置**：`.dev/docs/upstream/retry-and-continuation/status.md:18`

原文：「……；`error_status` 的 429 分支在 driver 路径上**不可达**。」

**为什么错**：来源报告 `reports/260821-upstream-error-handling-survey.md:140` 写的是：

> `error_status` 的 429 分支和 `error_headers` 的 `Retry-After` 分支在当前 driver 路径上**我没有找到可达路径**。

「未找到可达路径」是搜索结果，「不可达」是全称否定。这正是本项目 `h2-goaway` 四轮评审每轮都命中的那一型。同一行里「客户端拿到 502」有实测断言支撑（`tests/int/test_pipeline_app.py:755` 已逐字核对为 `assert response.status_code == 502`，✔），这一句没有。

**建议怎么改**：改为「`error_status` 的 429 分支在当前 driver 路径上**未找到可达路径**（`reports/260821-upstream-error-handling-survey.md:140`，静态阅读，未做可达性证明）」。

---

### M3. `status.md:38` 的 `category` 值集没有出处，且遗漏了唯一确定会到达合成点的形态

**位置**：`.dev/docs/upstream/retry-and-continuation/status.md:38`

原文：「合成工具调用时传给 MCP 的 `category`，实际只可能取到 `network` 与 `internal` 那一小撮，**取不到 `client`／`auth`／`rate_limit`**。这三格的回复文案配了也不会被用到。」

**两个问题**：

1. **值集无出处。** 权威文档只写了 `turn_interrupted(num_messages, category, message)` 的形参名，没有定义 `category` 的取值；`.dev/docs/upstream/retry-and-continuation/` 全目录搜不到任何定义这五个字面量的地方（已 grep）。这五个名字来自哪个 MCP 实现、哪个版本，文档没说。跨仓依赖（status.md:92 自己承认要与改 MCP 的同伴对齐）在这里没有落到值集上。
2. **推论本身漏了一格。** 按上方那张表，`stop_reason` 类（`max_tokens`、`refusal`）**只可能在「已交付」**，即 `max_tokens` 是唯一确定会走到合成点的形态。它既不是 `network` 也不是 `internal`。所以「只可能取到 network 与 internal」与同页表格互相打架。

第 40 行已经带了前提声明（「这是推论不是裁决——前提是『已交付分支不发起新 attempt』」），这一点做得对；缺的是值集出处与 `max_tokens` 那一格。

**建议怎么改**：把值集的出处写出来（或标为「待与 MCP 侧对齐，取值未定」），并补上 `max_tokens` 对应哪个 category；把结论收窄成「HTTP 状态码类的三格（client／auth／rate_limit，若 MCP 侧确为这些名字）取不到」。

---

### M4. `status.md` E 阶段把三条尚未获用户裁决的候选建议写成了既定路线

**位置**：`.dev/docs/upstream/retry-and-continuation/status.md:83`、`:87`、`:88`

三条：

| status.md 写法 | 权威文档怎么说 | 候选文档同一时刻怎么说 |
|---|---|---|
| `:83` 「`status:"incomplete"` 的块丢弃规则：**有任何完整块才丢；只有未完成块则保留**」 | **完全没有这一格** | §2 标题就是「文档目前完全没有这一格」，给的是「**建议措辞**」 |
| `:87` 「仅在 anthropic-messages 客户端请求上生效；**两条上游腿都适用**」 | 第 41 行句尾是「其他**上游请求**暂不使用该机制」——歧义未消 | §7 明确说这是「一处措辞残留」，**建议**用户改，`c75cbe0` 的提交信息也自陈「that is flagged rather than assumed」 |
| `:88` 「`max_tokens` **一律走合成**，不回落到无痕重试」 | 第 23 行是「`max_tokens` **不应无痕重试**」+ 一个 TODO | §1a 给的是「**建议措辞**（替换第 23 行的 TODO）」 |

**为什么错**：同一轮里，候选文档把这三条标为「供用户摘取、不是裁决」，status.md 却已经把它们当成 E 阶段的实现条目。按 `what-decided-is-decided`，只有用户指定或裁定的才能直接照做；这三条目前都只是我方推荐。更要紧的是 `deferred.md` 第 1 行自称「只列**需要用户裁决**或已知未闭合的项」，而这三条一条都没列进去——于是「待裁决」这个状态在本主题里没有任何一份文档承载。

`:87` 的读法我认为是对的（合成 `tool_use` 块看的是发给客户端的格式），但**对不对与该不该标待裁决是两件事**。

**建议怎么改**：在 status.md 的 E 阶段这三条上各加一句「**待用户裁决**，候选措辞见 `.dev/human-controlled-docs-candidates/upstream-retry-and-continuation-supplements.md` §2／§7／§1a」，并在 `deferred.md` 的「已知未闭合」下新增一条把这三项列全。

---

### M5. 归档 README 把「`usage` 只取最终成功 attempt」列为「仍然有效」，与 status.md 直接冲突

**位置**：`.dev/docs/upstream/retry-and-continuation/archive-proxy-side-continuation/README.md:32`

原文（「哪些结论没有被推翻，仍然有效」清单末条）：「**`usage` 只取最终成功 attempt，不累加。**」

**为什么错**：MCP-driven 下**没有成功的上游 attempt**——合成 `tool_use` 交回客户端时，这一轮上游是失败的。而同一主题的两份文档都要求报失败 attempt 的值：

- `status.md:90`：「`usage` 报失败 attempt 实报值。」
- 候选文档 §6：「`usage` 报本次失败 attempt 上游实报的值——被交付的块确实进了客户端的 transcript……这里报零会让客户端对上下文占用的估计持续偏低。」

原文 `spec-stream-continuation.md:157` 的措辞是「downstream 成功 `usage` 仍**只取最终成功 attempt**」，它的适用前提是「这一条 message 最终成功收尾」。MCP-driven 恰好把这个前提拆了。所以这条**不是「没有被推翻」，而是「适用条件被换掉了」**。

**建议怎么改**：把该条移出「仍然有效」清单，改写为：「原文 5.1／6 的『`usage` 只取最终成功 attempt』**其前提在新方向下不再成立**——MCP-driven 的一轮没有成功 attempt，处置改由 `../status.md:90` 承担。仍然有效的是它背后那条理由：估算与实测必须来自同一个实际请求（原文 6，`:159`）。」——后半句在新方向下反而更容易满足，status.md:96 已经用上了。

---

### M6. 归档 README 的「仍然有效」清单漏掉了原文 5.1 中同样约束无痕重试（D 阶段）的三条

**位置**：`.dev/docs/upstream/retry-and-continuation/archive-proxy-side-continuation/README.md:28-32`（五条清单）

原文 `spec-stream-continuation.md:135-142`（5.1 节）自陈「**REPLAY 与 CONTINUE 均适用，现在就生效**」，共列六条。归档只继承了其中两条（单个 `message_start` + 不发终止性帧；每 attempt 新建 assembler／Terminal／buffer 且 frontier 不回退），漏掉的三条都直接落在 D 阶段头上：

1. **`:140`「后续 attempt 的身份不得泄漏到 wire」**——downstream `message_id`、model、HTTP status 与已提交 response headers 在首个可见 batch 后冻结。这是无痕重试「无痕」二字的定义之一。
2. **`:142`「每个 attempt 有自己的 `deadline_at`」**（`context.begin_attempt()`），不得沿用上一个已过期的 deadline。
3. **`:138` 的接线陷阱**：「若把每个 attempt 分别交给现有 `stream_delivery`，它在第一次 EOF 就会发出 `error` 并返回，wire 从此不可恢复。**REPLAY 同样会踩**——所以这一条不能等到 CONTINUE 启用才生效。」

`status.md` 的 D 阶段（`:68-79`）一条都没承接。归档一旦被当作「已作废方案」束之高阁，这三条就没有活文档承载了。

**建议怎么改**：把三条补进归档 README 的「仍然有效」清单（或更好：直接写进 `status.md` D 阶段的验收要点），并注明出处 `reports/spec-stream-continuation.md:138,140,142`。

---

### M7. README 证据表首行用了全称词「一定」，却把样本边界丢在了报告里

**位置**：`.dev/docs/upstream/retry-and-continuation/README.md:37`

原文：「撞 `max_output_tokens` 时，上游**一定**为被截断的 item 发出 `output_item.done`……| 录制，n=20，逐例 |」

**为什么错**：来源报告 `reports/260821-max-tokens-block-completeness.md:57-59` 自己把话说全了：

> - **强到可以据此行动**：……20/20 无反例，覆盖 message / function_call / reasoning 三种 item 类型和两个模型。
> - **样本时间窗**：2026-08-04 ～ 2026-08-08 之间（旧服务 copilot-api-js），模型为 `gpt-5.6-sol` / `gpt-5.6-terra`。**上游行为随时间/模型变化的可能性未被排除。**

README 只留了 `n=20`，丢了时间窗、模型与那句免责。同一轮的候选文档 §1b **带了**（「样本边界（建议一并写进文档）」），所以这不是资料没查到，是索引层把它掉了。README 是本主题的证据入口，读者最可能只读这张表。

顺带：报告 `:21` 还记了「现有 cassette 里**没有** incomplete / max_tokens 场景」，README 也没带——而按项目规矩「上游行为要靠 cassette 回放」，这条空缺对 E 阶段的可测性直接相关。

**建议怎么改**：该行证据等级列改为「录制，n=20，逐例；2026-08-04～08，`gpt-5.6-sol`／`terra`，时间与模型外推未排除」。

---

### M8. `h2-goaway/findings.md` 新增的移交注，把一个还没发生的前提写成了既成事实

**位置**：`.dev/docs/upstream/h2-goaway/findings.md:6`（`51df795` 新增）

原文末句：「**R4（合成 `message_start` 而零块）那一格也随 `synthesized_response_headers_after_sec` 的删除而不再可达**。」

**为什么错**：那个配置项**还在**——已核对 HEAD：`git show HEAD:src/app/config/schema.py` 第 264 行仍是 `synthesized_response_headers_after_sec: int = Field(default=240, ge=0)`。删除它是 status.md D 阶段的**计划**（`:72`）。「随……的删除而不再可达」这个句式预设了删除已发生。

同一条推论在 `status.md:79` 是写对的：

> 前提是那个配置项确实被删；**它若回来，这条推论随之失效**。注意这是**构造性保证**——live 链路一条相关断言都没有……

`findings.md` 是 `h2-goaway` 的入口活文档，读者停在那里不会看到 status.md 的限定。

**建议怎么改**：改成「R4（合成 `message_start` 而零块）那一格**将随 D 阶段删除 `synthesized_response_headers_after_sec` 而不再可达**；该配置项目前仍在（`src/app/config/schema.py:264`），前提未兑现前这条不成立，见 `../retry-and-continuation/status.md:79`」。

---

### M9. 候选文档 §4 把一条「口头裁决」记在用户名下，`.dev` 里查无此记录

**位置**：`.dev/human-controlled-docs-candidates/upstream-retry-and-continuation-supplements.md:89`

原文标题：「## 四、非流式路径（文档没写，**你已口头裁决**）」

**为什么错**：本文档自陈「性质：候选材料，供用户摘取，**不是裁决**」（`:3`），唯独这一节反过来声称用户已经裁过。我在 `.dev/docs/` 全目录搜过「非流式」与「口头裁决」：`deferred.md` 记了五条带日期的「用户 2026-08-21 裁决」，**没有这一条**；能找到的最接近的东西是归档报告 `spec-stream-continuation.md:171` 的「明确不做｜非流式路径的续写｜没有 commit frontier，失败即整体重试」——那是**Spec 作者的**取舍，不是用户裁决。

我无法证伪会话里是否真的说过这句话。但按本项目「用户裁决要落到 `deferred.md`／`decision` 文档」的做法，一条查无记录的裁决归属，读者没有办法核。裁决归属记错比事实记错更难被发现。

**建议怎么改**：二选一——(a) 补上出处（哪份文档、哪一行记着这条裁决），或 (b) 降级成「**建议**」，与本文档其余七节保持同一性质。

---

## 2. Minor

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| m1 | `status.md:20` 引用 `logging.py:22,68` | `:22` ✔ 是 `"retry": "[RETRY]"`；`:68` 差一行，落在 `"[WARN]": YELLOW` 上，`[RETRY]` 的配色在 **`:69`** | 改为 `logging.py:22,69` |
| m2 | `status.md:13` | 「network 9 次、serverError 9 次、`max_total` 20」三个数字**不在**所引的 `base.py:126-176`／`:228` 里，它们在 `src/app/config/schema.py:163-175,184`（已核对：9／9／20／streamReplay 100 全对）。`:228` 引得很准，它正是 `_send` docstring 里「止于响应头」那句 | 补上 schema.py 的出处 |
| m3 | `status.md:96` | `token_calibration.py:53-63` 覆盖到三字段求和为止，「配 `estimate_anthropic_input`」在 `:64-65`，落在范围外（此条与 M1 独立，即使换成 live 文件也要给准范围） | 范围改 `53-65` |
| m4 | `archive-.../README.md:11` | 「共 18 + 5 + 1 条发现全部采纳」**重复计数**：原文 `:3` 的「18」已经是 (4 blocker + 7 major) + (5 major + 2 minor) 两轮之和，修订表 `:198-199` 也写着 11 + 7 | 改「11 + 7 + 1」或「18 + 1」 |
| m5 | `archive-.../README.md:20` | 4.2 作废的范围列了「稳定身份、内容摘要、carrier digest」，漏了原文 `:97` 同时要求的「**独立 commit state**」——而 MCP-driven 的那道门（已交付过至少一个完整块）恰恰要靠它，status.md:15 也正把「读不出来」列为现状缺口 | 补一句：identity／digest 那部分作废，**可读的 committed frontier 不作废，改由新方向的门继承** |
| m6 | `README.md:37` | 该行前半是录制事实，后半「该 item 自己会被交付成一个完整块」是**代码事实**（`assembler.py:231-232` → `_close`，已核对 ✔），两种证据混挂在「录制，n=20」一个等级下 | 拆成两行，或在证据等级里同时标出两种 |
| m7 | `README.md:38` | 「实测 15 次（其中 4 次在 `function_call` 上）」这个 n 在候选文档 §2 里有，README 只写「录制」不带 n | 补 n |
| m8 | `status.md:15` | 「`DeliverySession.delivered` 是 `stream.py:215` 的函数内局部变量」——`:215` 是 `session = DeliverySession(buffer=buffer)`，函数内局部变量是 `session`；`delivered` 是它的字段，定义在 `blocks.py:141-142`。结论（无外部读取者、`committed_count` 零生产调用点）**已核实为真** | 改成「`session` 是 `stream.py:215` 的函数内局部变量，`DeliverySession.delivered`／`committed_count`（`blocks.py:141-142`）因而没有外部读取者」 |
| m9 | `status.md:19`、`deferred.md:43` | 用 `pipeline_app.py:590-591` 支撑「**不发任何错误帧**」。已核对：`:590-591` 是 `if self.failure is not None: return "fail", ...`，那是**日志判定**，能支撑「只进服务端日志」，支撑不了「不发帧」这个否定命题（否定命题要枚举发帧点） | 拆开：「只进服务端日志」引 `:590-591`；「不发任何错误帧」另注明是按 `stream.py` 的发帧点枚举得出（并给出枚举范围） |
| m10 | `status.md:5` | 「**当前状态：一行代码都还没动**」只带日期不带提交锚点。已核实它在 `.dev` 仓 HEAD 时刻对主仓 HEAD `8a36fe3` 成立；但主仓工作树**此刻已被同伴改动**：`git status` 显示 `src/app/pipeline/retry.py`、`src/app/config/schema.py` 及四个测试文件 modified，改后的 `retry.py` docstring 自陈「This function used to name a fourth……ruled out on 2026-08-21」——B 阶段已在飞 | 加锚点「对主仓 `8a36fe3` 而言」；这不是文档写错，是可变陈述缺 provenance |
| m11 | `findings.md:96` 的重指 | 重写该表格行时，原「状态」列里一条**仍然成立**的施工约束被丢掉了：「要动的 `pipeline_app.py`／`handler.py` 正被并行会话大改（`direct_driver` 重构），共用同一棵工作树时同改一文件是互相覆盖而非合并冲突」。新主题 `status.md` D 阶段（风险最高的一组）没有承接它。m10 的 `git status` 正好是这条约束的活证据 | 把它挪进 `status.md` D 阶段的施工注意事项 |

---

## 3. 查过并且没有问题的（判据一并列出）

按你给的六类风险逐项交代，**没有空清单免检**。

### 3.1 报告原件是否逐字未改（风险 4 的一半）—— ✔ 通过

判据：`git show 0fd454c:docs/upstream/h2-goaway/spec-stream-continuation.md > /tmp/orig-spec.md && diff` 当前归档件 → **完全一致，零差异**。另三份报告（plan-g2、poc、review）在 `51df795` 中是 100% rename（`--find-renames=100%` 下 `git show --stat` 报为纯新增/纯改名、无内容 diff）。归档 README `:43` 那句「报告原件逐字保留，不因归档而改写——包括其中指向旧路径的引用」，**做到了**。

### 3.2 归档对四个前提「整片作废」的归纳（风险 4 的另一半）—— 基本准确

逐条对着 `spec-stream-continuation.md` 原文核过：

- 「四条前提」「第 4.3 条没有解」「四个方案（A 不抑制／B 块级摘要／C 前缀重叠裁剪／D 只上报不删除）没有一个能讨清」「D 在任何 eligible continuation 上退化成等于 A，靠一条走不到的分支」——全部对得上原文 `:101-116`，**无一处说反**。
- 「该文作者主观推荐先不启用，并把该代价列为待裁决第 1 项」——对得上 `:13`、`:177-181`。
- 4.1／4.3／4.4 判为作废的理由都成立：4.4 的 ABANDON 理由确实是「代理拿不到 `tool_result`，无法构造协议完整的 resume turn」（`:123`），MCP-driven 下代理不构造 resume turn，前提消失。
- 「三轮独立评审」✔（v1 评审、v2 复核、v4 第三轮），只有条数算错（m4）。
- 遗漏见 M5、M6、m5。

### 3.3 与权威文档的一致性（风险 3）—— ✔ 逐条比对，未发现相违背

| 权威文档条款 | 各文档怎么写 | 判定 |
|---|---|---|
| 「无法继续」五格（客户端断开／代理保护机制／400／401／refusal） | README `:15` 只提前三类作为「不是上游失败」的分流，`status.md:31-36` 的表是**位置**轴（未交付／已交付）不是**可否继续**轴，两轴不冲突 | ✔ 未违背 |
| 「一般可以继续」五格（网络中断／超时／429／5xx／max_tokens） | 同上；D 阶段（`status.md:68-75`）逐条覆盖网络中断、读流中断、429、本侧结束 | ✔ |
| 工具名 `turn_interrupted` | README `:18`、`status.md:84` 均为 `turn_interrupted`。全目录 grep `upstream_error`：仅在两份调查报告里作为**无关的错误类型字面量**出现（`error_type = "upstream_error"`、`normalize_upstream_error`），**没有任何一处把它当工具名**。旧工具名零残留 | ✔ |
| 适用范围 = anthropic-messages **客户端**请求 | README `:18` 写「客户端请求」✔；`status.md:87` 写「客户端请求」✔。上游腿那半句见 M4 | ✔（措辞正确） |
| `max_tokens` 不无痕重试 | 见 M4（方向对，性质标错） | 方向 ✔ |
| 次数上限「不需要」 | `status.md:97`、`deferred.md:61` 都写「不设」，且都归因到用户 2026-08-21 裁决与「门本身保证零进展的一轮到不了这里」 | ✔ |
| `num_messages` = 客户端请求 `messages`／`input` 的长度 | `status.md:84` 写「取**客户端请求**的 `messages` 长度」——省了 `/ input`，但适用范围本就限定 anthropic-messages，取 `messages` 正确 | ✔ |
| 429 → 反应式限流器，预算耗尽返回真实 429 + `Retry-After` | `status.md:73` 逐字对应 | ✔ |
| 工具定义缺失 → 打 warning 但照发 | `status.md:85` | ✔ |
| 配置项 `client_delivery.auto_retry_tool_call_full_name` | `status.md:86` | ✔ |
| 已删除 `synthesized_response_headers_after_sec` 相关的半开 `message_start` 顾虑 | `status.md:79` 与候选 §8 都把它标成**推论**并写明前提，措辞正确 | ✔（`findings.md` 那一份见 M8） |

### 3.4 证据等级与「零观测」的处理（风险 1 的正面成绩）

这一类**大部分做得好**，值得记下来：

- `deferred.md:25-32` 把 `model_context_window_exceeded` 两条腿分开定级：Responses 腿「结构性不存在，值空间里没有。权重强，可据此行动」／Anthropic 腿「13 万次请求零观测。**这是『未观测』，不是『不可能』**。所以分类表里不要把它写成已排除」。这正是本项目要求的写法。
- `deferred.md:34-38`、README `:39` 对上游 `error` 帧一律写「零观测」+ 样本量，没有写成「不会发生」。
- `deferred.md:64-66` 主动记下了 `from_history.py` 根帧判据在 2026-07-17 19:41 前的 366 个 operation 上**恒真失效**——这是给后来人的反向警告，与报告 `260821-upstream-termination-reasons.md:75-80` 逐字对得上。
- `status.md:40`、`:79`、候选 §8 都在推论后面显式写了「前提变了它就失效」。

### 3.5 数字与引用的抽查（风险 2）

README 证据表里的每个计数都回原报告核过，**全部命中**：`response.completed` 64 351 ✔、`response.incomplete` 20 ✔、134 336 个 operation ✔（= 69 586+36 322+22 836+5 592）、约 3000 万根帧 ✔、`tool_use` 124 927 ✔、`end_turn` 8 290 ✔、`max_tokens` 24 ✔、`refusal` 1 ✔、CC 2.1.226 ✔。

逐条打开核对过的 `文件:行号`（除 M1／M8／m1／m2／m3／m8／m9 已列出的以外，**以下全部正确**）：

`cli.py:23,151,176` ✔（`create_pipeline_app` 的 import 与两个调用点）｜`base.py:126-176` ✔（正是 `run` 方法的首尾两行）｜`base.py:214` ✔（`outcome.error = PipelineAbort(...)`）｜`base.py:228` ✔（`_send` docstring「止于响应头」那句）｜`stream.py:215` ✔（`session = DeliverySession(...)`，措辞见 m8）｜`stream.py:253-262` ✔（合成 `message_start` 的分支首尾；且「唯一单独发」这一点成立——`:267-273` 那处 `message_start` 与 `remaining` 块同批发出）｜`stream.py:279-288` ✔（`if not terminal.seen:` → `error_frame` → `return`）｜`assembler.py:231-232` ✔｜`assembler.py:279` ✔（`def _close`）｜`assembler.py:330-338` ✔（`response.incomplete` → `max_tokens`／`end_turn`）｜assembler 对 item `status` **零命中** ✔（`rg '\.status|"status"'` 退出码 1）｜`request_log.py:65` ✔（`type LogStatus = Literal["ok","fail","gone"]`）｜`request_log.py:70` ✔（`STATUS_COLOURS`，被引用的「restated rather than imported」注释在紧上一行 `:69`，可接受）｜`schema.py:264` ✔（HEAD 与工作树都对）｜`tests/int/test_pipeline_app.py:755` ✔｜`pipeline_app.py:590-591` ✔（行对，支撑力见 m9）｜`translation_driver/responses.py:114-130` ✔（`_responses_stop_reason` 整个函数）｜`handler.py:425-426` ✔（`conversion.losses`）｜`limits.py:10-13` ✔（两条正则，含 `prompt token count of N exceeds the limit of M`）｜`token_calibration.py:53-63` 行对（归属见 M1、范围见 m3）｜`~/.claude/skills/debugging-claude-agent-tools/reference/source-symbols.md:21` ✔（`cc(n3.options.tools, i, ...)` 查不到就发 `No such tool available`）。

**「9 条 `DeliveryOrderError`」（`status.md:79`、候选 §8）** —— 核对结论：**成立且精确**。`src/app/delivery/anthropic_sse.py` 全文共 31 处 `raise DeliveryOrderError`，但 `DeliveryFrontier`（`:266` 起）内部恰好 9 处（`:320,337,339,342,345,350,363,365,368`），即那句「相关断言」指的范围。更要紧的那半句也成立：`rg DeliveryOrderError src tests` 的命中只有 `src/app/delivery/`（legacy）与 `tests/int/test_anthropic_block_delivery.py`（测的也是 legacy），**live 的 `pipeline/delivery/` 一条都没有**。

**live／legacy 边界的其余引用** —— 全部核对为 live：`pipeline/delivery/{stream,assembler,blocks}.py`、`pipeline/direct_driver/base.py`、`observability/{request_log,logging}.py`、`server/{pipeline_app,handler}.py`、`config/schema.py`、`pipeline/translation_driver/responses.py`、`tokenization/limits.py`。唯一越界的是 M1。

### 3.6 相对路径与目录结构 —— ✔ 全部解析正确

一开始我以为 `../../anthropic-responses-bridge/spec.md` 是断链（`.dev/docs/upstream/` 下没有这个目录），**是我算错了**：从 `.dev/docs/upstream/retry-and-continuation/` 出发 `../..` = `.dev/docs/`，指向 `.dev/docs/anthropic-responses-bridge/spec.md`，**存在**。逐条验证过的链接：

`README.md:7` → `../../../../docs/.human-controlled/upstream-retry-and-continuation.md` ✔ 存在｜`README.md:50` → `../../anthropic-responses-bridge/` ✔｜`deferred.md:49` → `spec.md:264-265` ✔（`:264` 就是「未知 incomplete reason 必须保留原因事实，不能仅映射成看似正常的 `end_turn`」，正是被违反的那条；`:265` 相邻，多引一行无害）｜归档 README `:47` → `../../h2-goaway/` ✔｜`:48` → `../../../tmp/260821-truncated-anthropic-stream-diagnosis.md` ✔ 存在｜`status.md`／README 引的四份 `reports/*.md` 与归档四份 ✔ 全部存在。

### 3.7 重指是否伤及记录（风险 5）—— ✔ 未越界，一处遗漏

三处改动逐 hunk 读过：

- **`h2-goaway/README.md`**：只在文首**加了一段注**，`5c1afbe` 那张落地提交表**一个字没动**，注里还明说「记的是**当时**那个函数做了什么，仍然准确」。这是正确做法。
- **`h2-goaway/deferred.md:26-33`**：改的是**未闭合待办**的描述（欠账移交、CONTINUE 那格作废），属于活文档的正常更新，没有改写任何历史陈述。标题仍叫「三条路」而正文谈四条，是本次之前就有的措辞（`findings.md:80` 标题「三条路的裁决」／`:82` 正文「四条路而非三条」），**不是本次引入的**。
- **`h2-goaway/findings.md`**：改了状态行与待办表格行，两处都把被删内容在「状态」列里复述了出来（「原本写在这里的第三条路……已被用户裁决作废」），**没有丢失历史陈述**。归档目录 `archive-260820/` 的十份原件本次未被触碰。

问题只有两个：注文本身的既成事实化（M8），以及一条被顺手丢掉的施工约束（m11）。

**该重指而漏掉的活文档**：我按 `rg 'spec-stream-continuation|260821-plan-g2|260821-poc-continuation|260821-review-g2'` 扫过 `.dev/docs/` 全部活文档，除归档 README 自己以外**没有别的活文档引用这四份被搬走的报告**，所以没有断链。

### 3.8 候选文档是否越权（风险 6）—— 除 M9 外 ✔ 边界守得住

七节里六节都用「**建议措辞**」引出、并把它排版成引用块与正文区分开；`:3` 明写「候选材料，供用户摘取，**不是裁决**」；`:8`「本文只写目标文档**尚未涵盖**的部分」；§8 主动标注「一条推论（不是裁决，前提变了它就失效）」，还写了「可放可不放」。§3、§7 都用「建议」而非断言。§1a 的八仓表格逐仓给了判据与出处，我抽查了 `copilot-api-js` 与 `vscode-copilot-chat` 两行，与 `reports/260821-reference-projects-max-tokens.md` 对得上。唯一越界的是 §4 的「你已口头裁决」（M9）。

---

## 4. 处置建议的优先级

1. **M4**（候选 vs 既定的边界）——它决定后面几个阶段是不是在照未经裁决的东西施工，先改这个。
2. **M1／M2／M8**——三条都是「证据强度不匹配」，改起来都是一句话。
3. **M5／M6**——归档是这些条款仅存的载体，D 阶段动工前必须补。
4. **M9／M7／M3**——归属与边界，改完这一批本主题的证据表就可以当索引用了。
5. minor 一批可以合一次改完。

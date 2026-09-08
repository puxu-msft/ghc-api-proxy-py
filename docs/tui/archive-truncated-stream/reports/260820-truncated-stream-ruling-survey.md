# 调查：上游流截断（无终止事件）相关的既有裁决检索

调查范围：`docs/.human-controlled/`（优先）、`docs/.human-controlled-candidates/`、`docs/` 下 spec/ADR、`docs/agents/`、`docs/tmp/`。方法：`rg` 定向检索关键词（`truncat`、`terminal`、`stop_reason`、`message_stop`、`clean EOF`、`OK`/`FAIL`、`assembler` 等），逐条读取命中上下文；未做全量通读。

---

## 结论摘要

| # | 问题 | 结论 |
|---|---|---|
| 1 | 截断时应下发合成 `message_delta`+`message_stop`、不补、还是发 `error`？ | **有明确裁决，且与当前代码行为相反**：`docs/agents/anthropic-responses-bridge/spec.md`（状态 `FINALIZED`）明文裁定「没有合法 terminal event 的 EOF 是 truncation，不是成功」，且「已提交后使用 Anthropic SSE error event，且不得再发 `message_stop` 冒充成功」 |
| 2 | 截断请求日志行应为 `[ OK ]` 还是 `[FAIL]`？ | **未检索到专门针对「截断」这一情形的 OK/FAIL 判据**；只有通用定义（`[ OK ]`=请求成功完成，`[FAIL]`=请求失败），未见文档把「截断」显式归类到其中一侧 |
| 3 | `Terminal.stop_reason` 默认 `"end_turn"` 的设计意图 | **未检索到专门文档**；相关的是一次已修复的回归（该默认值曾误经聚合记录进入日志行），修复范围只覆盖日志摘要读取路径，未见对默认值本身意图的说明 |
| 4 | 是否有文档提到「截断」「truncated」情形的处理 | **有，且相当具体**：`spec.md` 与 `acceptance.md` 多处直接使用「truncation」「clean EOF」措辞并给出验收判据；但 `docs/agents/anthropic-responses-bridge/implementation.md` 与 `docs/agents/service-cutover/readiness.md` 同时标注这部分验收**尚未执行**（`UNVERIFIED`） |

---

## 1. 截断时应下发什么——有明确裁决

出处：`/home/xp/src/ghc-api-proxy-py/docs/agents/anthropic-responses-bridge/spec.md`

文档状态（文件开头）：

> 状态：正式开发规格，当前为 **`FINALIZED`**……本文件是实现与验收的行为 oracle，但不替代另行接受的 ADR。

原文摘录（第 296-306 行，`### Upstream Responses HTTP SSE` 与 `### Upstream Responses WebSocket` 两节）：

- L298：
  > `response.completed`、`response.incomplete`、`response.failed`、terminal `error` 与 clean EOF 的语义必须区分。**没有合法 terminal event 的 EOF 是 truncation，不是成功。**
- L304（WebSocket 一节，同一原则的另一处表述）：
  > `response.completed`、`response.incomplete`、`response.failed` 与 `error` 是 terminal frames；**disconnect without terminal 是 truncation**。

第 291 行（`### Downstream Anthropic SSE` 第 5 条）给出下游侧的直接裁决：

> terminal error 在尚未提交 HTTP success 时使用 Anthropic HTTP error；已提交后使用 Anthropic SSE error event，**且不得再发 `message_stop` 冒充成功**。

第 264 行（Content 与 terminal status 一节）：

> `incomplete` 且原因为 output-token limit 时，`stop_reason` 为 `max_tokens`。completed 且无 tool call 时，`stop_reason` 为 `end_turn`。content filter、cancelled 与未知 incomplete reason 必须**保留原因事实，不能仅映射成看似正常的 `end_turn` 后丢失 side-channel**。

配套验收判据，出处 `/home/xp/src/ghc-api-proxy-py/docs/agents/anthropic-responses-bridge/acceptance.md`：

- STR-04（第 185 行）：
  > 覆盖 completed、incomplete、response.failed、Responses `error` event、**没有 terminal 的 clean EOF**、malformed SSE 与 converter exception。**成功只在合法 terminal 且全部 block drain 后产生 `message_delta`＋`message_stop`；其他路径产生确定 Anthropic error／连接终止和 failed History。**
  > 缺陷注入控制：在 **clean EOF 上调用正常 flush**、failed 后仍发 `message_stop`……route-level consumer 必须变红。
  > 通过判据：**成功 terminal 与错误 terminal 互斥；任何 failure 后不得出现成功 terminal。**
- REL-01（第 201 行）：分别在 response headers 前、首 block 未完成时注入「transport reset／clean truncation」。
- REL-03（第 218 行）：commit 后失败，「客户端得到明确 partial-degrade／stream error」。

**结论**：这是一条明确、正式冻结的裁决，直接回答问题 1 ——截断（没有合法 terminal event 的 EOF）必须被当作失败/错误处理（HTTP error 或 SSE `error` event），**禁止**补发伪装成功的 `message_delta`+`message_stop`。这与当前代码 `src/app/pipeline/delivery/stream.py:171-177` 的行为（只要 `started` 为真就无条件补发 `message_delta`+`message_stop`，不看 `terminal.seen`）**直接矛盾**。

**范围提示**：`spec.md` 的标题是「Anthropic Messages endpoint → OpenAI Responses upstream」，字面对象是 Responses 桥接路径；但背景材料已确认 `assembler.py`/`stream.py` 是流式交付的共享框架（`tui-request-log/SPEC.md` 也提到 `assembler_for` 按 `dialect_for` 分派、两条上游共用同一交付核心），所以该裁决在实现层面覆盖的正是当前这份共享代码，不是另一套独立实现。是否要把这条裁决字面上扩大到 Anthropic 直通上游（若两者走的不是同一 `Terminal`/`stream_delivery` 实例）本次未核实，留作待确认点。

---

## 2. 截断请求日志行 OK/FAIL 判据——未检索到专门裁决

出处：`/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/telemetry-observability.md`（L44-49，design spec，非 human-controlled）：

```
| `[ OK ]` | 请求成功完成 |
| `[FAIL]` | 请求失败 |
```

以及 `docs/agents/tui-request-log/SPEC.md`（L62，已实现规格）：

> 沿用现有 structlog 的定宽前缀格式（`[ OK ]` / `[FAIL]` / `[<-->]` / `[....]` / `[RETRY]`），本次不改。

这两处只给出前缀的**通用语义**（成功/失败），**没有**任何一处把「上游流被截断（无终止事件）」显式归类为 OK 或 FAIL。同一份 `tui-request-log/SPEC.md`（L78、L88）为「结束原因」列着色做了细致裁决——`max_tokens` 黄、`refusal` 红、`end_turn`/`stop_sequence` 绿——但这是**闭集白名单**（L90：「表以外的结束原因一律不着色」），且这些值全部来自**上游真实返回**的 stop_reason，不覆盖「压根没有 stop_reason 事件、由代码合成默认值」这种情形。

背景材料已确认：`pipeline_app.py:128` 目前写死 `status_for(status_code, failed=False)`，即 OK/FAIL 完全由响应头阶段的 HTTP 状态码决定，与流是否被截断无关。**未检索到任何文档裁决过或质疑过这一判据是否应该把截断计入 FAIL。**

**结论**：未检索到——这是一处真实的裁决空白，不是我牵强附会。

---

## 3. `Terminal.stop_reason` 默认 `"end_turn"` 的设计意图——未检索到专门说明

检索未发现任何文档正面解释这个默认值「是为合成路径设计的」或给出其他意图说明。唯一相关的一手材料是一次**已修复的回归**，出处：`/home/xp/src/ghc-api-proxy-py/docs/agents/tui-request-log/deferred.md`（第 0 节）：

> 2026-08-20 的 `f8f5854` 一度让它变成显示一个伪造的 `end_turn`（`Terminal` 类默认值经聚合记录进入日志行），该回归当日已修，并由 `tests/http/test_pipeline_app.py::test_a_route_whose_reply_cannot_be_read_claims_nothing_about_it` 钉住。

核对了对应提交 `f8f5854a53dc4782433dc8e9e86731a9698d3ec8`（`refactor: describe a reply once, where both delivery paths can read it`）：该提交改的是 `assembler.py` 的 `Terminal.record()` / `terminal_from_anthropic()`、`request.py`、`pipeline_app.py` 三处，**目的是让「读不到回复内容」时日志行不要冒充读到了默认值**，修复范围限定在**日志摘要（reply summary）读取路径**——即背景材料提到的、`pipeline_app.py:321` 那个读 `terminal.seen` 的唯一读者。这个修复**没有触及** `stream.py:171-177` 的 `stream_delivery` 收尾逻辑（该提交 diff 不含 `stream.py`）。

**结论**：未检索到对默认值本身意图的文档说明；已修复的回归只证明「默认值不该被当真实值读」这条原则在**日志侧**已被裁决并落地，但没有推广到**下发给客户端的 SSE 帧**这一侧——而这正是当前背景材料指出仍然存在问题的地方。

---

## 4. 「流被截断」「truncated」「unterminated」的处理——有文档提到，且相当具体，但标注为未验证

除第 1 节引用的 `spec.md`/`acceptance.md` 正面裁决外，还检索到以下相关但需要区分层次的材料：

### 4.1 已冻结的裁决原文（同第 1 节，不重复摘录）

`spec.md` L298、L304、L291、L264；`acceptance.md` STR-04（L185）、REL-01（L201）、REL-03（L218）、REL-03B（L226，sink partial-write／delivery-uncertain）。

### 4.2 明确标注「尚未验证」——当前实现与规格之间已知有缺口

出处：`/home/xp/src/ghc-api-proxy-py/docs/agents/service-cutover/readiness.md` L59：

> Error／terminal／transport failure | `UNVERIFIED` | `ae84aa9…`代码复核与既有备用端口happy smoke已覆盖关键precommit typed 502、postcommit Anthropic error且无`message_stop`、disconnect cleanup；R3又覆盖首block前cancel与上游断连，但Acceptance要求的HTTP 4xx／429／5xx、failed／incomplete各reason、malformed body、**clean EOF**、真实RST／partial-write与terminal互斥完整矩阵**尚未执行**。

出处：`/home/xp/src/ghc-api-proxy-py/docs/agents/anthropic-responses-bridge/implementation.md` L76（Stream route 一行）：

> 已进入main；main stream定向review为0 blocker／0 major；reviewed source已归档；**完整stream仍`UNVERIFIED`** | 按backup smoke已列真实缺口补semantic reorder、usage／terminal／History矩阵、retry、buffer cap 下的背压、真实partial-write与完整Acceptance

也就是说：**裁决本身是既有的、`FINALIZED` 的**，但 `implementation.md`/`readiness.md` 这两份「实现进度」文档同时承认「postcommit Anthropic error 且无 `message_stop`」这一子集已有代码复核覆盖，而**「clean EOF」「terminal 互斥」这部分完整矩阵还没有测试执行**。这与背景材料描述的 `stream.py:171-177` 现状（无条件补发 `message_delta`+`message_stop`，不看 `seen`）吻合——即：**裁决已经存在，实现尚未对齐裁决，且这个差距本身已经被记录为已知缺口**，不是本次调查才发现的新事实。

### 4.3 相邻但不是同一件事的材料（记录以防混淆，不作为本题证据）

- `docs/.human-controlled/config.example.yaml:630-639`（`hook_fix_anthropic_sse.rewrite_refusal`）：`as_end_turn = 合成 text 块 + 把 stop_reason 改成 end_turn + 补 message_stop`。这是针对**上游明确返回 `end_reason=refusal`** 这一已知、有信息的场景做的兼容改写，与「压根没有终止事件、用默认值顶替」是两回事，不构成对截断场景的裁决。
- `docs/agents/tui-request-log/SPEC.md` L78/L88：结束原因着色表，闭集白名单，只覆盖上游真实给出的 stop_reason，不含截断这种「没有 stop_reason」的情形。
- `docs/agents/anthropic-responses-bridge/research.md` L176（`terminal repair`／`repair-if-incomplete`）：讨论的是 reasoning item 的 completeness repair，与 SSE 层面的 terminal event 无关。

---

## 检索方法记录（供复核）

- `rg` 关键词：`truncat`、`unterminat`、`premature`、`disconnect`、`incomplete`、`clean EOF`、`terminal\.seen`、`stop_reason`、`message_stop`、`message_delta`、`assembler`、`status_for`、`failed=`、`\[FAIL\]`、`\[ OK \]`，范围分别限定在 `docs/.human-controlled`、`docs/.human-controlled-candidates`、`docs`、`docs/agents`、`docs/2604-rewrite`、`docs/tmp`（仅用于定位文件名，未逐篇通读 `docs/tmp`）。
- 逐一读取的文件：`docs/.human-controlled-candidates/existing-rulings.md`（全文）、`docs/.human-controlled/config.example.yaml`（相关片段）、`docs/agents/tui-request-log/SPEC.md`（全文）、`docs/agents/tui-request-log/deferred.md`（全文）、`docs/2604-rewrite/telemetry-observability.md`（相关片段）、`docs/agents/anthropic-responses-bridge/spec.md`（相关片段，约 150 行）、`docs/agents/anthropic-responses-bridge/acceptance.md`（相关片段，约 110 行）、`docs/agents/anthropic-responses-bridge/implementation.md`、`docs/agents/service-cutover/readiness.md`（命中行片段）、提交 `f8f5854` 的 diff。
- 未通读：`docs/2604-rewrite/` 下未直接命中关键词的文件、`docs/agents/` 下 systemd/deployment 相关文档（与本题无关）、`docs/tmp/` 中未命中关键词的绝大多数文件。

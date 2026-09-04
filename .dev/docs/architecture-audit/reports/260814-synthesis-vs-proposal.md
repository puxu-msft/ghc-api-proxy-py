# 对账报告：既有提案 ↔ 独立体检

> **来源与转录说明**：本文内容由独立对账 agent（未参与前 7 轮体检）产出。该 agent 的 `Write` 工具被 harness 禁用，它明确**没有**用 Bash 绕过禁用，而是把全文内联返回；本文由主会话转录落盘。
> **主会话独立复验的部分**在文末「主会话复验记录」一节单列——未列入该节的条目为 agent 自述，尚未经第二方核实。
> **锚点**：代码 `main@44471c6ceedd8a06a7e0cca480314f8fc205e7c0`。提案 `architecture.md` 锚 `ed77c9d`；`implementation.md` 锚 `c1de6bf`。

## 口径更正

`git rev-list --count c1de6bf..44471c6` = **8**，不是派活时说的 7。且这 8 个提交改动的 26 个 `src/` 文件**无一在 bridge 路径**（全是 rolling/systemd/history/approval）——所以 `implementation.md` 的 bridge 事实在 HEAD 上仍然成立，陈旧的只是 HEAD 锚点与「下一步」清单。

## 一、重合面（两条互不知情的路径撞到同一处）

| # | 提案表述 | 体检表述 | 复验 |
|---|---|---|---|
| R1 | `architecture.md:40` 把「流式与非流式 converter 漂移」列为方案 B 消除的 5 类结构风险之一；`:349` 要求两者调用相同 block constructors；`:507` 给出「语义单源」可证伪判据 | duplication D1/D2/D4，3 处**已实测漂移** | **提案预测的类，体检抓到了实例**。本次对账最强的一处重合：一方是纯设计推理，一方是进程内探针，撞到同一点 |
| R2 | `architecture.md:524` retry decision 是 wire-shaped + boolean 混合 | typing-leaks 表第 3 行同一位置，同一诊断 | HEAD 复验：`strategies/__init__.py:11-15` `RetryDecision(should_retry: bool, payload: dict[str, object])` 原样在 |
| R3 | `architecture.md:525` executor 同时内联 hook/wire 构造/send/observer/finalize | module-boundaries 轴 3 建议拆 3 个模块 | `execute_anthropic_pipeline` 现为 `:196-513`（318 行）。两方连**建议的切分维度都一致** |
| R4 | `architecture.md:528` Responses HTTP/WS 各自暴露不同 exchange 形态 | duplication D12（`TERMINAL_EVENTS` 两份）；lifecycle「transport 打开/关闭非单一 owner」 | `openai/client.py:49-62` 与 `responses_ws.py:31-38` 行号未漂，形态仍不同 |
| R5 | `architecture.md:530` History final state/projection/receipt 压成一次调用 | lifecycle「History 投影发布非单一 owner」；typing-leaks「持久化 projection 可变 dict，写者不唯一」 | `history/consumer.py:19-24`/`:26-53`；`routes/anthropic.py:104-117` 就地改写已冻结的 `_committed_response` |
| R6 | `architecture.md:529` `buffered_retry` 整 response collector 易被误当 block buffering，处置「保留或**退役**」 | dependency-graph：该模块**零生产消费者** | 体检把提案的「或退役」变成了可执行判断——它已经事实退役 |
| R7 | `implementation.md:274` 登记「同一 semantic rule 双实现曾发生漂移」（空 reasoning 轴） | duplication 整表 | 提案侧只登记了**一条轴**且标为「已仲裁冻结」；体检证明同一模式在另外 4 条轴上仍活着 |

## 二、提案覆盖不到的发现

### 2.1 `spec.md` 已经裁决了这 3 处漂移，两侧各错一次

| 用例 | 非流式 | 流式 | `spec.md` 冻结裁决 | 谁错 |
|---|---|---|---|---|
| `incomplete`/`max_output_tokens` | `unsupported_response_status` → 502 | 200 + `stop_reason:"max_tokens"` | `:263` | **非流式违规** |
| message content 为空 | 200 + `[{"type":"text","text":""}]` | `ApiError: response completed without content` → 502 | `:266` | **流式违规** |
| `input_tokens_details:"oops"` | `invalid_response` → 502 | 静默当空字典，200 | `:363` | **流式违规** |

**并且这 3 例全部同时违反 `spec.md:255`**：「非流和流式转换必须共享同一个语义映射核心。两条路径对相同 Responses output 的归一化 Anthropic content、stop reason、usage、degradation 与 error 必须等价。」

⇒ duplication 报告 D4 写「正确方向未裁定，不应由实现者自行统一」——**该句不成立**。方向已由 FINALIZED spec 裁定。根因是主会话派活时只禁读 architecture/implementation，未指出 `spec.md` 是应读的冻结 oracle。

### 2.2 第 4 处漂移（体检只写了半句）

`T=5,R=4,W=3,O=5,Q=2`（`spec.md:378` 表里的 `inconsistent cache` 向量）：

- 非流式：`usage_inconsistent` fact + `ResponseUsageFacts(reasoning_tokens=2, inconsistent=True)`
- 流式：wire 四个数字相同，但**无 `usage_inconsistent`、`reasoning_tokens=2` 直接丢弃**（`TerminalUsage` 只有 4 个字段）

`rg -n usage_inconsistent src/` 全仓命中 3 处，**全在 `protocols/responses_anthropic.py`**，流式侧零生产者。违反 `spec.md:365` 与 `:368`。

### 2.3 应该抓住这 4 处的验收层根本不存在

`acceptance.md` 显式定义 `STR-05 流式 usage 与 nonstream 等价`，`:60` 要求「不得由同一个产品 serializer 同时生成 expected 与 actual」，并点名 6 个测试文件：

```
MISSING tests/acceptance/test_anthropic_responses_conversion.py
MISSING tests/acceptance/test_anthropic_responses_http.py
MISSING tests/acceptance/test_anthropic_responses_lifecycle.py
MISSING tests/acceptance/test_anthropic_responses_stream.py
MISSING tests/acceptance/test_anthropic_responses_resilience.py
MISSING tests/acceptance/test_anthropic_responses_ws.py
```

`tests/acceptance/` 目录本身不存在。**808 项测试全绿，而唯一能证否这 4 处漂移的那一层从未建立。** 这正是 `implementation.md` 声明 `UNVERIFIED` 的机制解释。

### 2.4 方案 B 范围**之外**的重复（干净的覆盖缺口）

- **D8**：两份手写 SSE 帧解析。`streaming/anthropic_usage.py:21` 只认 `data: `（带空格），`streaming/openai_sse.py:44-48` 两种都认。前者服务**原生 Anthropic 直通腿**，不是 bridge。`:26-27` 对 JSON 解析失败静默 `continue`。方案 B 碰不到它。
- **D9**：`CopilotUpstream`/`GenericUpstream` 12 个方法手抄 6 种形态，只有 2 个做 `APIStatusError` 归一化。方案 B 的 `ResponsesTransport` port 只收敛 Responses leg。
- **D10/D11**：`routes/openai.py::_response` 与 `routes/azure.py::_response` 逐字节相同；Gemini 流式转换藏在 `routes/`。完全在方案 B 范围外。
- **D13**：Anthropic error 信封 4 副本、字段集不一致，其中 2 处不属 bridge 交付链。

⇒ **提案覆盖 bridge 腿的重复，覆盖不到非 bridge 腿的重复**，后者有 4 条。

### 2.5 16 个零消费者模块 —— 提案 15/16 未提

`anthropic/feature_negotiation`、`anthropic/sanitize/deduplicate_tool_calls`、`anthropic/thinking/signature_compat`、`context/error_persistence`、`history/sessions`、`observability/tui`、`openai/responses_stream_accumulator`、`openai/stream_accumulator`、`pipeline/manager`、`repetition_detector`、`shutdown`、`streaming/buffered_retry`、`streaming/delayed_commit`、`streaming/translator`、`transform/system_prompt`、`transform/translator`。

提案两份文档中只有 `streaming/buffered_retry.py` 被点名（`architecture.md:529`），其余 15 个零命中。

`TODO_CURRENT.md` 把它们**全部标为 `[x]` 已交付**；`TODO_CURRENT.md:74` 更明写 `transform/system_prompt.py`「跨协议共用，被 Phase 4 请求准备调用」——**该句在 HEAD 上为假**。

### 2.6 测试同源（只有体检有实证）

test-structure S-1 变异实验：改 v1 载荷线格式后 `test_responses_reasoning.py` **10/10 依旧全绿**（expected 由生产编码器自己算）。而 `implementation.md` 把 reasoning 切片记为「R2/R3 0/0 已归档」——那些 0/0 是在这份聋判据之上取得的。

## 三、提案怪味登记在 HEAD 的对账

`architecture.md:520` 七行，**6 行仍成立、1 行行号失效**：

| 提案行号 | HEAD 实况 | 判定 |
|---|---|---|
| `strategies/__init__.py:11-60` | `RetryDecision` `:11-15`、`RetryCoordinator` `:30-66` | 仍成立，行号应改 |
| `executor.py:190-267` | `execute_anthropic_pipeline` `:196-513` | 仍成立，范围严重低估 |
| `routes/anthropic.py:99-120` | 现为 `committed_response` 补写 + `history.finalized` | 仍成立，语义已变 |
| `anthropic/client.py:148-184` | 该区间现为 `prepare()` `:155-170` | **行号已失效**，对应符号是 `observe_stream_finalized` `:366-423` |
| `openai/client.py:49-62` + `responses_ws.py:31-38` | 符号原位 | 仍成立，行号未漂 |
| `streaming/buffered_retry.py:8-18` | `collect_with_limit` `:8-18` | 仍成立，且可强化为「零消费者」 |
| `history/consumer.py:20-33` | `started` `:19-24`、`finalized` `:26-53` | 仍成立，漂 1 行 |

`implementation.md:275`「stream route 必须消费 current parser，不另建 normalizer」在字面上被遵守了（流式确实调 `ResponsesStreamParser`），但被绕开的是另一件事——**非流式那条腿有自己一整套规则，而登记表只单向约束了 stream 侧**。这是 `fix-at-the-shared-base` 的典型形态：不变量写成了单方向。

## 四、冲突面

**唯一实质冲突**：`routes/anthropic.py:102-117`

- typing-leaks 判 `major`：持久化 projection 是可变 `dict[str, Any]`，写者不唯一
- lifecycle 判 `minor`：不旁路 delivery 链，不是第二个 History 发布者

**裁决**：两边论据都成立，但测的是不同轴，不构成真冲突。`render_responses_as_anthropic_sse` 的 `finally` 里 `freeze_committed_response()` 产出该 dict，`committed_response` property 返回**同一对象**，route 随后原地写。确实是两个顺序写者；但当前唯一消费者是紧随其后的 `history.finalized`，无可复现的错误行为。

⇒ **判 `minor`，但带一个已命名的触发条件**：一旦 `committed_response` 出现第二个消费者（方案 B 的 `HistoryProjectionFacts` 正是这样一个消费者），route 的事后改写就变成跨 owner 写入。方案 B 核心第 5 条恰好修这个——所以应作为「B 落地时必须一起改」的登记项，而非独立 major。

其余各体检报告之间未发现相互矛盾的事实判断。

## 五、必答问题：`D-ARCH` / `D-MIGRATION` 是否仍是对的问题？

### 支持「提案仍然正确」

`architecture.md:40` 把流式/非流式 converter 漂移列为方案 B 要消除的风险；`:349` 规定两侧共用 block constructors；`:507` 给出可证伪的「语义单源」判据。体检在完全不知情的情况下撞出的 4 个实例，**逐一落在这条判据的覆盖面内**。这是对提案诊断力的强背书。怪味表 6/7 仍成立，方案 A/C 的拒绝理由未被任何体检事实动摇。

### 支持「前提已被改变」

`D-ARCH` 与 `D-MIGRATION` 的每一个分支，对下面三件事的处置**完全相同**：

1. 4 处对 FINALIZED spec 的违规（A、B、C 都得修；M1、M2 都不决定何时修）
2. `tests/acceptance/` 整层缺失（提案把它写成「route 启用前置门」第 6 条，而 route policy 默认已是 `auto`，Responses-only 模型无需 override 即可进入该腿——**门被写成前置，路已经通了**）
3. 16 个零消费者模块

**并且 `D-MIGRATION` 的退出判据在当前仓库失去判别力**：`architecture.md:640` 规定 M2 退出条件为「adapter 消费者已归零」。在一个已有 16 个模块处于「零消费者但仍在 `src/` 且 `TODO_CURRENT.md` 标 `[x]`」状态的仓库里，「消费者归零」既不能证明 adapter 退役成功，也无法把它与「从来没接上」区分开。这不是提案写错，是提案成文时不知道有这 16 个模块。

### 结论

**`D-ARCH` 仍是对的问题，`D-MIGRATION` 的判据需补一个前提；但两者都不再是「最先要问的问题」。**

**(a) 4 处漂移在方案 B 下会怎样？** 会被解决，但存在「被无声选错侧」的具体风险。方案 B 合并两份实现时必须为每处选一个行为；`architecture.md` 只说「必须一致」，不说「一致到哪个值」，而 `spec.md` 说了。M2 的过渡形态是「受约束的 A 形 adapter」，A 形以 Anthropic/非流式为 canonical 起点——**恰好在 `max_output_tokens` 这一例上，非流式是错的那一侧**。一个只读 `architecture.md` 的执行者会以最自然的方式把 502 固化下来。**处置**：B 动工前把这 4 条的正确侧连同 `spec.md` 行号写进迁移输入，或先修好并用回归钉住。

**(b) 方案 B 会如何处理 16 个未接线模块？** 不会处理，它们在方案 B 视野之外。方案 B 的建模对象是「一个入站请求的生命周期」；这 16 个模块的问题不是建模错了，是**它们不在任何生命周期里**。最可能的结果是原样留在原地，下一轮体检再被发现一次。

**(c) 是否存在提案里没有的第三类工作？** 是，两类：

> **第三类 A（必须排在 `D-ARCH` 之前）：修 4 处 spec 违规 + 建立 stream/non-stream parity 验收 gate。**
> 理由：①它们是对 FINALIZED spec 的违规，不依赖任何架构裁决，A/B/C 都得修；②**没有 parity oracle 就无法安全执行方案 B 的核心合并动作**——合并时若无外部判据，实现者只能在两个已知不同的行为里挑一个，那是在无声地做产品裁决。`acceptance.md:60` 已写明该 oracle 的关键约束（不得由同一产品 serializer 同时生成 expected 与 actual）。

> **第三类 B（可与 `D-ARCH` 并行）：16 个零消费者模块逐个裁决——接线 / 明确降级为测试支持代码 / 删除。**
> 理由：①污染 `D-MIGRATION` 的退出判据；②`TODO_CURRENT.md` 标为已交付且带虚假接线断言，任何以它为输入的规划都会高估现状；③module-boundaries 已把其中 2 个标为「先由用户裁决」——这是一个已被识别但未上报到提案层的裁决点。

**不建议撤回 `D-ARCH` 的推荐（B），也不建议改推 A 或 C。** 体检没有产生任何反对 B 的事实；相反 B 的 5 条不可拆分核心里，第 1、4、5 条都被体检从三条独立轴线佐证。**真正要改的是排序与前置输入，不是目标。**

## 待用户裁决（对账者不代裁）

1. 第三类 A/B 是否排在 `D-ARCH` 之前——这改变了用户被要求裁决的顺序，属范围决定
2. `test_spec_deletions` 那一类缺席守卫（`auto_truncate` 不得复活，实测仍成立但无人守）是补回还是明确退役
3. `sse-starlette` 是否授权黑盒 PoC（与既有 `SELECTIONS.md` 的落地存在偏离）

## 对账者的主观建议

`TODO_CURRENT.md:74` 那类「被 X 调用」的接线断言应改为可重算的命令（如 `rg -c 'app.transform.system_prompt' src/`）而非固化的完成态文字——本轮 16/16 的错误率说明这类断言写下即开始过期，读者无从判断它还准不准。

## 主会话复验记录

以下条目由主会话独立复验（非采信 agent 自述）：

| 条目 | 复验方式 | 结果 |
|---|---|---|
| `spec.md:255` 语义单源要求 | `sed -n '255p'` 读原文 | 确认，原文要求两条路径「必须等价」 |
| `spec.md:263` max_tokens 裁决 | 同上 | 确认，非流式违规 |
| `spec.md:266` 空内容裁决 | 同上 | 确认，流式违规 |
| `spec.md:363` malformed usage 裁决 | 同上 | 确认，流式违规 |
| `tests/acceptance/` 不存在 | `ls -d` | 确认不存在 |
| `usage_inconsistent` 流式侧零生产者 | `rg -n` 全仓 | 确认 3 处命中全在 `protocols/responses_anthropic.py` |

未经主会话复验的条目（agent 自述，采信但标注）：怪味表 7 行的逐行对账、`git rev-list` 计数 8、第 4 处漂移的探针复现、`acceptance.md` 点名的 6 个文件清单。

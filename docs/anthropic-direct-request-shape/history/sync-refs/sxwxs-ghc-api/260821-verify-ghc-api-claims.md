# 核查：`260821-ghc-api-lessons-for-us.md` 中关于 `sxwxs/ghc-api` 的事实主张

> 核查日期：2026-08-21。被核查文档：`/home/xp/src/ghc-api-proxy-py/.dev/docs/tmp/260821-ghc-api-lessons-for-us.md`。
> 被转述对象：`/home/xp/.claude/jobs/89874ec2/tmp/ghc-api`，HEAD `0cb1087`（`git status --short` 干净，未做任何修改）。
> 范围限定：**只核查关于 ghc-api 的主张**。凡涉及 `/home/xp/src/ghc-api-proxy-py`（「我方」）的断言一律不判，另有核查员负责。
> 权威源选择：一律回到 ghc-api 当前 checkout 的源码与测试；`docs/decisions/*.md`、`README.md`、`benchmarks/*.md` 只在核查「文档原文怎么写」时当权威，绝不当代码事实的证据。
> 独立探针：把 `ghc_api/{anthropic_responses,json_guard,compat_profiles,reasoning_carrier}.py` 四个文件**复制**到 `/tmp/ghcapi-probe/ghc_api/`（附空 `__init__.py`，绕开需要 Flask 的包初始化），在 Python 3.14.7 下复算了 §3 的审计报告体积。被调研仓库未被写入。

## 0. 总览

共核查 14 组、约 50 条事实主张。判定分布：**忠实 39 条、过度概括 7 条、失真 3 条、无法判定 0 条**。

三条失真中，只有一条会直接误导行动（§2.3 的「每一档都先检查 profile」——报告明确建议抄这个写法，而代码里五档中有三档没有这个检查）。另两条是数字与状态描述失准（能力位个数、「未修」）。

按任务要求特别关注的三类问题各命中情况：
- **(a) 把文档自述当代码事实**：未发现硬性误用。报告在 §2.1 明确标注了表格出自决策文档，我逐行回代码核过（见 §2 本文）；§2.9 引用的决策文档自述（0.5 是占位值、失效模式不对称）报告并未升格为代码事实。唯一擦边的是 §4.2「未修」——那是照抄决策文档的开放项清单，而代码已经改了一半。
- **(b) 把一条路径的行为概括成整个项目**：命中 2 条（§1 的「门控全部 id 比较」、§2.1 的未知 content part 档）。这两条都不是错，是**执行者被记错了**——不在转换器里，在审计器里；或者只覆盖一部分比较点。
- **(c) 否定性主张**：4 条（无测试、无读者、「那句话是错的」、fake 不校验 body）。全部证否成立，方法见各条。

---

## 1. 失真（3 条，按影响排序）

### 1.1 §2.3：「每一档都先检查目标方言是否支持该 effort 名」——**失真**

> 转述原文：「`enabled` 按 `budget_tokens` 分档（≥30000 → max、≥16000 → xhigh、≥8000 → high、≥3000 → medium、其余 low）。阈值是拍脑袋的，但**每一档都先检查目标方言是否支持该 effort 名**，而不是硬编码一套名字发出去——这个写法值得抄，阈值我方自己定。」

证据：`ghc_api/anthropic_responses.py:854-863`

```python
if numeric >= 30000 and "max" in profile.reasoning_efforts:
    effort = "max"
elif numeric >= 16000 and "xhigh" in profile.reasoning_efforts:
    effort = "xhigh"
elif numeric >= 8000:
    effort = "high"
elif numeric >= 3000:
    effort = "medium"
else:
    effort = "low"
```

准确的说法：**五档里只有 `max`（:854）和 `xhigh`（:856）带 profile 检查；`high` / `medium` / `low` 三档是硬编码的名字，不查 `profile.reasoning_efforts`。** 另外两个入口确实带检查——`disabled → "none" if "none" in profile.reasoning_efforts else "low"`（:843）、`adaptive`/`auto → "high" if "high" in ... else profile.reasoning_efforts[-1]`（:845）——报告很可能是从这两处外推到了全部分档。

为什么要紧：这条是报告里唯一一处「机制强到可直接采纳」而阈值仅存档的推荐，被推荐的正是这个「写法」。照抄一个只有一半兑现的写法，等于把「能力位门控」写成一个凭巧合成立的约定：当前三个方言（`public_responses`、`copilot_public_responses`、`copilot_responses_lite`，`:289-341`）恰好都含 `low`/`medium`/`high`，所以这三档漏检不发作。方言表一变就发作，而且是静默发出上游不认的 effort 名。

我方若采纳，建议的准确表述：「把 effort 名当成 profile 能力位查表，而不是硬编码——ghc-api 只在 `max`/`xhigh` 两档做到了这一点，剩下三档是漏的，抄的时候要补齐。」

### 1.2 §4.2：「三条流式路径有三种 pre-header 语义（0.5 秒 / 0.5 秒 / 整整 30 秒）…项目自己记为「Converge them or document why they differ」但未修」——**失真（两处）**

**第一处：「三种」与括号里给出的两个值自相矛盾。** 代码事实（HEAD）：

| 路径 | 位置 | pre-header 等待 |
|---|---|---|
| `/v1/responses` | `ghc_api/routes/openai.py:1743` | `min(responses_pre_header_grace, sse_keepalive_interval)` = **0.5 s** |
| `/v1/messages` → Responses（翻译路径） | `ghc_api/routes/anthropic.py:1732-1735` | 同一表达式 = **0.5 s** |
| `/v1/messages` direct | `ghc_api/routes/anthropic.py:2156` | `pending_response.get(timeout=state.sse_keepalive_interval)` = **30 s** |

默认值出处：`ghc_api/state.py:85`（grace 0.5）、`:79`（keepalive 30）。三条路径**两种**语义。

**第二处：「未修」不成立。** `docs/decisions/RESPONSES_PRE_HEADER_KEEPALIVE.md:163-165` 的原话是「`/v1/messages` direct waits a full keepalive interval, **the translated path commits immediately**, `/v1/responses` waits the grace」——即写文档时确实是三种。之后提交 `f3e8bae`（2026-08-15，`Bound the Messages->Responses pre-header wait by the same grace`）把翻译路径收敛到了 grace，代码注释写着「Same pre-header grace as /v1/responses」（`routes/anthropic.py:1725`）。

准确的说法：「决策文档记了三种语义并留了 `Converge them or document why they differ`；此后 `f3e8bae` 把翻译路径收敛到 grace，HEAD 上剩两种（0.5 / 0.5 / 30），未收敛的是 direct `/v1/messages`。**决策文档的开放项本身已经过期而没有更新**——这恰好是同一族问题的另一个样本，比『未修』更值得我方引以为戒。」

同段的另一半是**忠实**的：「`cancel()` 的所有权修复只落到三条路径中的两条」。决策文档 `:148-149` 写的是「applied to `openai.py` only」（三分之一），但报告核的是代码：HEAD 上 `.cancel()` 出现在 `routes/openai.py:361` 与 `routes/anthropic.py:1472,1544`，后两处都在 `_stream_pending_anthropic_responses_request` 的 `generate()` 里（函数起于 `:1286`，`generate` 起于 `:1329`），`_stream_pending_direct_anthropic_request` 没有。**报告在这里正确地用代码覆盖了文档，只是相邻的那半句没有同样处理。**

### 1.3 §2.7：「12 个能力位」/「12 个字段值」——**失真（数字）**

证据：`ghc_api/anthropic_responses.py:268-285`，`ResponsesWireProfile` 共 **14** 个字段，除 `name` 外的能力位是 **13** 个：`tools_in_input`、`supports_native_web_search`、`native_server_tools_in_input`、`supports_prompt_cache_breakpoint`、`supports_temperature`、`supports_top_p`、`supports_max_output_tokens`、`supports_message_phase`、`supports_reasoning_context`、`preserves_reasoning_item_ids`、`reasoning_efforts`、`default_text_verbosity`、`stable_ids`。

影响很小（报告的论点是「值得抄的是规则不是字段值」），但这是可机械核对的数字，写 13 即可。

---

## 2. 过度概括（7 条）

### 2.1 §1 表格：「`stable_ids` 能力位门控**全部** id 比较」——**过度概括**

`stable_upstream_ids` 门控的比较点（`ghc_api/sse/anthropic_responses.py`）：`web_search_call` 的 item id（:288-295）、终局 `response.id`（:662）、重复 `response.created` 的 id（:759）、annotation 的 `item_id`（:790-797）、web search 生命周期事件的 `item_id`（:825-832）。

**未被门控**：`call_id` 变异（:296-304，`responses.call_id_mutation`）与 `name` 变异（:305-312）。这两条无论 profile 如何都无条件比较。

准确的说法：`stable_ids` 门控的是**上游 item id / response id 这一类会被 Copilot 每帧重新加密的标识**（profile 注释 `anthropic_responses.py:283-285` 就是这么写的），`call_id` 与工具名不在其内、始终强校验。这不是缺陷（`call_id` 与 item id 是不同来源），但「全部 id 比较」这句话会让读者以为门控是一刀切的。

### 2.2 §2.1 表格第 3 行：「未知 content part 类型 → 拒绝 502」——**过度概括（执行者记错了层）**

结论本身成立，但**不是转换器做的**：

- **SSE 转换器不拒**。`sse/anthropic_responses.py:894-902`：`part_type` 不是 `output_text`/`refusal` 时，既不报错也不记账，直接 `return self._drain()`。
- **非流式转换器也不拒**。`anthropic_responses.py:1834-1835`：未知 message content part 只 `report.mark(..., PRESERVATION_UNSUPPORTED)` 然后 `continue`；对比同一函数里未知 **output item** 类型是 `raise AnthropicResponsesConversionError`（:1903-1908）。
- **真正 502 的是审计器**。`compat_profiles.py:1585-1599`（item 内的 content/summary part）与 `:1707-1719`（事件里的 `part`）用 `fail_always=True` → `action == "reject"`（`:752`）→ `CompatibilityAudit.should_fail`（`:714-715`）。流式在 `sse/anthropic_responses.py:1189-1194` 转成 `responses.profile_drift` 协议错误（502）；非流式在 `routes/anthropic.py:1970-2015` 对终局 body 跑同一个 `audit_responses_event` 并 502。

准确的说法：这一行的执行者是 `compat_profiles.audit_responses_event`，两条路径都在**调用转换器之前**跑它。我方若只照抄「转换器对未知 item 拒绝、对未知 content part 拒绝」的判据而不建对应的审计层，第 3 行不会自动成立。

（第 1、2、4、5 行均已逐条回代码核实，见下节「忠实」清单。）

### 2.3 §3：「实测：1.3 MiB 请求产出 594 KiB 审计报告（约 44%）」——**数字忠实，比例过度概括**

我独立复算（`/tmp/ghcapi-probe`，非引用调研报告的数字）：

| 形状 | 请求体 | records | `report.to_dict()` JSON | 比值 |
|---|---|---|---|---|
| 50 条 × 800 字符 | 42 KiB | 178 | 19 KiB | 44% |
| 400 条 × 800 | 337 KiB | 1403 | 148 KiB | 44% |
| 1600 条 × 800 | **1349 KiB** | 5603 | **594 KiB** | 44% |
| 1600 条 × 3200 | 5099 KiB | 5603 | **594 KiB** | 12% |

「1.3 MiB → 594 KiB」重现无误。但 **44% 不是这个机制的性质，只是「800 字符/条」这个形状的性质**：第 4 行同样 5603 条 records、同样 594 KiB，比值掉到 12%。报告体积只跟叶子数走。报告紧接着写了「信息量最低的 `exact` 记录正是体积的来源」，方向是对的，但把 44% 当成可记忆的比例会诱导错误外推。建议改成「报告体积与请求叶子数成正比、与字节数无关；1600 条消息的请求稳定产出约 594 KiB 报告」。

同一格里的另一半是**忠实**：`cache._truncate_oversize_bodies`（`ghc_api/cache.py:58-74`）只替换 `request_body`、`original_request_body`、`raw_events`、`response_body`，`conversion_report` 不在名单里，因此超限请求的 body 变占位符之后报告仍完整驻留内存。

### 2.4 §3：「E2E …**只能测性能不能证明正确性**——它自己没划清这条线」——**过度概括**

代码事实全部成立：`benchmarks/e2e/runner.py:88-89` 的唯一失败判据是 `response.status_code >= 400`；`:72-84` 解析 SSE 只为识别终止（`data: [DONE]` / `message_stop` / `response.completed`），不比对内容；`benchmarks/e2e/fake_backend/app.py:489-517` 只读 `model`、`stream`（`:40` 读 `metadata`），从不校验代理发上来的 body 形状。

但「它自己没划清这条线」偏重：`benchmarks/e2e/README.md:1` 的标题就是 *E2E performance benchmark*，末段自限为「compare variants or code revisions on the same otherwise-idle machine」；`benchmarks/E2E_TEST_REPORT.md` 把「功能测试结果」一节（`:48-78`）明确归给 `pytest -q`，与第 4 节的 benchmark 分开写，第 5 节「发现和限制」列了 5 条限制。

准确的说法：项目从未主张这套 bench 能证明正确性，功能验证归 pytest；**缺的是一句显式的「本 harness 不校验内容，转换缺陷不会让它变红」**。「没划清」→「没写下」。

### 2.5 §2.2：「日志按 `(code, path, 指纹)` 五分钟去重打印，但计数不去重」——**忠实但键描述不全**

`ghc_api/routes/anthropic.py:148`：`key = (code, path, profile + "\x00" + cli_version + "\x00" + fingerprint)`；`:151` `should_log = now - last >= 300`；`:159` `counters.incr(...)` 在 `if should_log` **之外**，`:160-166` 打印在其内。另有 4096 条上限的老化（`:154-158`）。

即：去重键是 `(code, path, profile, cli_version, fingerprint)` 五元组。报告写「指纹」把后三项并成一项，语义没错但不精确。五分钟、计数不去重两点完全属实。

### 2.6 §2.4 第 1 条：「对 `""` 替换成确定性替身」——**范围略窄**

`ghc_api/anthropic_responses.py:1048-1057`：分支是 `if isinstance(description, str) and description.strip()` / `elif "description" in tool`，代码注释自己写的是「a blank (or **non-string**) one」。所以空串、纯空白、以及任何非字符串值（`None`、数字……）都会被换成 `f"Tool: {original_name}."`。缺席保持缺席属实。

测试确实覆盖三个分支且断言无告警：`tests/test_anthropic_responses_translation.py:579-614`——缺席 → `assertNotIn("description", forwarded)` + `assertEqual(report.warnings, [])`（:597-598）；`""` 与 `"   "` → `"Tool: do."` + 恰好一条 `/tools/0/description` 告警（:600-608）；正常描述 → 原样 + 无告警（:610-614）。路由层另有 `tests/test_anthropic_responses_route.py:625-650`。

### 2.7 §2.2 末尾：「`_map_reasoning_effort` **无条件**先 mark」——**忠实但需加一个限定**

`ghc_api/anthropic_responses.py:841` 的 `report.mark("/thinking/type", PRESERVATION_SEMANTIC, "/reasoning/effort")` 之前有两道闸：`output_config.effort` 命中且被 profile 支持时函数在 `:836` 就返回了（此时 `/thinking/type` 反而**不会**被标，靠 `_mark_known_output_config` 的补账 `:1089-1092` 兜的是 `/output_config/effort` 而不是它）；`thinking` 不是 dict 时在 `:838-839` 返回。

在报告实际讨论的场景（有 `thinking` dict、`thinking.type` 未知）下，转述完全成立：`:841` 先标 `semantic`，三个分支（`disabled` :842、`adaptive`/`auto` :844、`enabled` :846）都不命中，`:866` 返回 `None`。`semantic` 不进告警（`ConversionReport.mark` 只对 `approximation`/`unsupported` 生成 warning，`:219-228`），`/thinking/type` 进了 `_marked_paths`（`:216`）所以 `account_unknown_paths`（`:245-254`）不会把它算成未登记叶子。**审计线索说它被映射了，实际什么也没发生**——成立。

建议把「无条件」改成「不管 `thinking.type` 是什么都先标」。

---

## 3. 忠实（逐条，含否定性主张的证否方法）

### §1 对照表（4 行）

1. **`output_index` 做键 + `stable_ids` 能力位**：`sse/anthropic_responses.py:154-155`、profile 注释 `anthropic_responses.py:283-285`。「门控全部 id 比较」的收窄见 2.1。
2. **保活计时读上游那一侧**：`sse/keepalive.py:185` `q.get(timeout=interval)`——队列每收到上游一行就被喂一次，超时才吐 `KEEPALIVE`（:186-188）。**装反**属实。
   **翻译路径对 tool call / reasoning 整块缓冲**：`sse/anthropic_responses.py:446-459` `_state_ready`——`function_call` 与 `custom_tool_call` 要求 `state.done`（:454、:458，注释写明「Buffer the complete argument string」）；`reasoning` 在 `_drain` 里 `if not state.done: break`（:480-482）。只有 `message` 文本是增量的（:450）。所以「上游忙、下游零字节」的窗口真实存在。
   **无测试覆盖该场景**（否定性主张，**成立**）。证否方法两步：① `rg -ln "keepalive|KEEPALIVE|ping" tests/` 得 13 个文件，逐个看测试名与 fixture；② `rg -n "sleep" tests/*.py` 穷举所有能构造时序的地方——命中 `test_sse_base.py:570`、`test_sse_keepalive.py:31/132`、`test_anthropic_responses_route.py:1015/1055/1210`、`test_anthropic_pre_response_keepalive.py:73/112`、`test_responses_pre_response_keepalive.py:381/416`。**每一处的形态都是「上游 idle / 上游 header 迟到」**（如 `_SlowResponse.iter_lines` 先 `sleep` 再 yield 唯一一行，`test_sse_keepalive.py:23-36`），没有任何一处让上游持续吐行而下游静默。计时器只能被这两种输入驱动，所以枚举完 sleep 即枚举完可能的构造。
   「项目自己未意识到」：`docs/decisions/RESPONSES_PRE_HEADER_KEEPALIVE.md` 的开放项列了「backoff sleeps are silent」（`:161-162`）却没有这一条；`sse/keepalive.py` 的模块 docstring（:3-13）把问题定义成「upstream goes silent」，即从头就只建模了上游侧。判为**倾向性证据足以支持「文档中无记录」，不足以支持「无人知道」**——建议我方引用时说「项目文档未记录」。
3. **自有版本化 reasoning 载体**：前缀 `ghc-api:responses-reasoning:v1:`（`reasoning_carrier.py:22`）；canonical base64url 往返校验 `:99-101`；拒重复键 `:106-112`；键集必须恰好相等 `:122-125`。
4. **能力位取保守值并写证据出处**：`anthropic_responses.py:329-330` 注释「The supplied dump proves prompt_cache_key but not explicit breakpoints.」紧贴 `supports_prompt_cache_breakpoint=False`。

### §2.1 边界表（逐行回代码）

| 行 | 判定 | 代码证据 |
|---|---|---|
| 未知 SSE 事件类型 → 告警并跳过 | 忠实 | `sse/anthropic_responses.py:1077-1092`，`_warn(..., "approximation")` 后 `return self._drain()`；注释 `:1077-1086` 就是表格「理由」列的原文。审计器侧 `compat_profiles.py:1650-1664` 不带 `fail_always` |
| 未知 output item 类型 → 502 | 忠实 | `sse/anthropic_responses.py:857-858`（`added` 事件）与 `:557-558`（drain）→ `_protocol_error` → `error_status_code = 502`（:628）；审计器 `compat_profiles.py:1524-1533` `fail_always=True`；非流式 `anthropic_responses.py:1903-1908` raise |
| 未知 content part 类型 → 502 | **过度概括**，见 2.2 | — |
| 未知非流式 `response.status` → 502 | 忠实 | `routes/anthropic.py:1929-1969`：`terminal_event_types.get(status)` 为 `None` 即记 `responses.unknown_response_status` 并返回 502，注释 `:1937-1940` 与表格「理由」列一致 |
| 流结束但无终局事件 → 502 | 忠实 | `sse/anthropic_responses.py:1094-1097` `finalize_interrupted` → `_protocol_error("responses.stream_ended_without_terminal")` |

### §2.2 三段分工

- 头只放 code 集合、排序、逗号连接、截 1024：`routes/anthropic.py:169-175`（`sorted({...})` + `",".join(codes)[:1024]`），注释 `:173-174` 明说「diagnostic hint, not the authoritative report」。**注**：`[:1024]` 切的是 str 字符数；code 全为 ASCII，与字节数等价。
- 完整列表进请求记录：`routes/anthropic.py:1153` `"compatibility_warnings": warnings` 写进缓存记录；流式侧 `sse/anthropic_responses.py:1238-1241` 把三处 warnings 合并进 `extra_cache_fields`。
- 日志五分钟去重、计数不去重：见 2.5。

### §2.3 映射规则（除失真项外）

优先读 `output_config.effort` 属实（`anthropic_responses.py:830-837`，且不被 profile 支持时记 `unsupported` 并落回 `thinking`）。`disabled → none`（:843，带 profile 检查）、`adaptive`/`auto → high`（:845，带检查）、分档阈值 30000/16000/8000/3000（:854-863）全部属实。

### §2.4 三条上游兼容性事实

1. 空 description：见 2.6（范围略宽于「空串」，其余忠实）。
2. **孤儿 `tool_result` 丢弃 / 孤儿 `tool_use` 保留**：忠实。`anthropic_responses.py:677-694`，代码注释逐字给出报告转述的两条判据——「makes the whole upstream call fail with "No tool call found for function call output"」与「synthesising an output would invent a tool answer the model never produced」。
3. **`x-anthropic-billing-header:` 前缀 system 文本整块丢弃、记 `semantic`**：忠实。字符串 system `anthropic_responses.py:787-794`，block 数组 `:809-816`，均 `PRESERVATION_SEMANTIC` + `subtree=True` + `return`/`continue`。（旧链路另有 `translator.py:78-83` 与 `routes/anthropic.py:793-796`，与本条不冲突。）

### §2.5 严格解析

- fail-closed 与 docstring：`anthropic_responses.py:1669-1699`，docstring `:1676-1679` 原文「Sending a scalar, array, malformed JSON, or an object with duplicate keys as an Anthropic `tool_use.input` can make the CLI execute a call with a different contract. This is therefore a fail-closed boundary」。
- **五个样本存在**：`tests/test_sse_anthropic_responses.py:299-319`，`for arguments in ("[]", "1", "null", "not-json", '{"x":1,"x":2}')`，逐个断言 `assertIn("error", ...)` 且 `assertNotIn("content_block_start", ...)`。非流式侧的对应五样本在 `tests/test_anthropic_responses_translation.py:1010-1034`（重复键样本写作 `{"duplicate":1,"duplicate":2}`）。
- 嵌套守卫：`json_guard.py` 共 84 行、只 import `re`；`MAX_JSON_NESTING_DEPTH = 100`（:29）；结构字节线性扫描 `_STRUCTURAL_RE = re.compile(rb'["\[\]{}]')` + `finditer`（:34、:59-84），模块 docstring `:15-22` 解释了为什么不能用正则匹配字符串字面量（会退化成二次方）。不靠 `RecursionError`：docstring `:6-8`「CPython's C scanner only raises `RecursionError` near 10k levels on 3.12」，下游 `copy.deepcopy` 约 500 层（`:4-6`）。`silent=True` 不捕获 `RecursionError` 的说法在 `ghc_api/app.py:78-79` 有明文。`parse_strict_json_bytes` 里对 `RecursionError` 的兜底自称「Defence in depth」（`anthropic_responses.py:95-97`）。

### §2.6 载体三策略

1. 三种解析结局：`reasoning_carrier.py:78-138`——不带前缀 `return None`（:85-86）、带前缀但畸形 `raise ValueError`（:87-137）、合法返回 `ReasoningCarrier`。docstring `:79-83` 明写这个区分的用途。调用方兑现：`anthropic_responses.py:713-722`，`except ValueError` → `carrier = None` + `PRESERVATION_APPROXIMATION`（因此产告警）+ `summary_text` 仍然进 `reasoning_item`（:749-755）。
2. 模型/方言不匹配保 summary 丢密文：`anthropic_responses.py:725-748`，`carrier.model != target_model or not profile_matches` → APPROXIMATION，`encrypted_content` 保持 `None`；匹配才回填（:740-748）。载体里确实同时写了 `model` 与 `wire_profile`（`reasoning_carrier.py:61-66`）。
3. 跨路径剥离：`reasoning_carrier.py:160-206` `strip_reasoning_carriers_from_messages_payload`，docstring `:163-167` 给出理由（「forged thinking signature … can make the upstream reject the request」）；调用点 `routes/anthropic.py:1011`、`:1052`。

### §2.7 profile（除字段数失真外）

- 两个 profile 是不同的东西：`CompatibilityProfile`（`compat_profiles.py:683-703`：name/protocol/cli_version/anthropic_version/betas/fingerprint，客户端身份审计）vs `ResponsesWireProfile`（`anthropic_responses.py:268-285`，上游方言能力矩阵）。忠实。
- 三个方言名：`public_responses` / `copilot_public_responses` / `copilot_responses_lite`（`:288-341`）。归属：`copilot_public_responses` ↔ Grok 有代码支撑（`api_helpers.py:350-357` 的 `"grok-*"` 内置规则 + 注释「xAI's Grok backend expects the public Responses dialect」，另 `state.py:59`）。`copilot_responses_lite` ↔ GPT-5.x **半支撑**：`state.py:58` 只显式映了 `gpt-5.6-sol`，它同时是**全局兜底**（`state.py:56`、`api_helpers.py:409`），所以准确说法是「除 grok-* 外的默认方言」。`public_responses` ↔「真 OpenAI」是**报告的推断**：没有任何内置规则会选中它（只能由运维在 `anthropic_responses_model_profiles` 里配，且配给 `grok-*` 时会被 `api_helpers.py:401-402` 改写回 `copilot_public_responses`），其字段值（`supports_temperature=True`、`supports_prompt_cache_breakpoint=True`）与公有 OpenAI 一致，推断合理但不是代码事实。
- `copilot_public_responses` 同时 `stable_ids=False`（`:320`）与 `preserves_reasoning_item_ids=True`（`:318`）：**忠实**，且两处都真在用——`sse/anthropic_responses.py:514-518` 用 `preserves_reasoning_item_ids` 决定是否把 item id 塞进载体，`:288`/`:662`/`:759` 等处用 `stable_ids` 决定是否比较 id。报告说「一边宣布不能用作身份键，一边又回填进载体发回上游」成立。

### §2.8 四条小项

1. 重试重建 headers、两个理由写在注释里：**忠实**。`routes/anthropic.py:1685-1696` 的 `build_request_headers` docstring 逐字写了「re-send a token that ensure_copilot_token() has just replaced -- turning a recoverable retry into a 401」与「would repeat one request id across attempts, defeating upstream correlation and deduplication」。`X-Request-Id` 由 `api_helpers.py:141` 每次 `get_copilot_headers()` 现生成。
   自己违反：**忠实**。`routes/anthropic.py:2130` `headers = get_anthropic_headers(...)` 在 `:2137` 的 `for attempt in range(max_retries + 1)`（`max_retries = 3`，:2133）**之外**，四次尝试共用同一个 dict、同一个 `X-Request-Id`、同一个 token 快照。
2. 序幕事件白名单恰好三个 + 布尔闸门 + 畸形 JSON 算内容：**忠实**。`sse/openai_responses.py:28-32` `_PRE_OUTPUT_EVENTS = {"response.created", "response.in_progress", "response.queued"}`；闸门是 `output_started` 布尔（:111、:117-119、:126-129），不是字节计数；`_event_type` 对 `json.JSONDecodeError` 返回 `""`（:94-100），注释原文「A malformed data payload is still downstream-visible output and therefore commits the stream」。
3. `.text` 做成 property + 专门回归测试：**忠实**。`sse/openai_responses.py:48-60`（注释解释 `Response.text` 走 `Response.content` 会把流吸干），测试 `tests/test_sse_base.py:389-404` `test_construction_does_not_read_the_streaming_body`，`_LazyStreamResponse` 用 `text_accessed` 标记（:355-371）。
4. 无读超时长连由并发上限兜底：**忠实**。`webiq.py:354-365`——GET 走 `timeout = (connect_timeout, None)`，注释 `:357-359`「The route-level concurrency cap prevents these intentionally unbounded reads from consuming the entire waitress thread pool」；上限 4（`state.py:124` `webiq_mcp_max_concurrent_streams`）对线程池 16（`state.py:150` `server_threads`）；超限立即 503 + `Retry-After: 1`（`routes/webiq.py:428-448`），非阻塞 `try_acquire`（`:62-79`）。

### §2.9 pre-header 分流

- D1 判据「按有没有拿到 HTTP 响应分流」：**忠实**，且代码兑现——`routes/openai.py:1758-1785`，立即拿到且 `ok` 走流式 handler，`immediate_response is None`（超时）才 commit SSE，**立即拿到但非 OK 的落回普通路由循环**（`:1782-1787` 注释「An immediate non-success response has not committed downstream SSE headers. Preserve the original HTTP status/body」→ `:1787` 的 `while conn_attempt <= connection_retries`）。丢 429/401 与面板不一致的历史论证见决策文档 `:38-47`（这一段是**决策文档自述**，不是我复现的观测）。
- `min(max(0.0, x), 5.0)` 与参数顺序理由：**忠实**，且**在代码里**——`ghc_api/main.py:288-295`，注释逐字包含「Argument order matters: max(0.0, nan) is 0.0 but max(nan, 0.0) is nan」；`ValueError`/`OverflowError`/`nan` 静默关超时的后果表述见决策文档 `:80-85`。（严格说是一个表达式跨两行，:294-295。）
- 默认值 0.5：**忠实**，`state.py:85` + `generate_config.py:175`。
- 「失效模式不对称」论证：**忠实转述决策文档** `:70-72`。
- 「这一行取代了原先一整张说明表」：**忠实转述决策文档** `:219-222`。

**代码事实 vs 文档自述的分界（任务点 11 要求区分）**：属于代码事实的是——分流控制流、钳制表达式与其注释、默认值 0.5、三条路径各自的等待值。属于决策文档自述、我未复现的是——「早期版本对所有非 2xx 都走流式」的历史、「cross-region RTT 50–200 ms」的经验值、「0.5 是占位值不是测量值」（`:140` 原文 "The grace default is a placeholder, not a measurement."）、以及 §1 里 3.01 s→0.51 s 的 TTFB 测量。**报告没有把这些升格成代码事实，也没有引用「0.5 是占位值」这一句**——这一点上报告是干净的；若我方后续引用 0.5 这个数，需要连带说明它按项目自述并非实测所得。

### §3 表格（要求核查的四项，其余略）

1. 594 KiB / `conversion_report` 不在截断名单：见 2.3（数字忠实、比例过度概括、截断名单忠实）。另附核：`compat_profiles.py` 1762 行（「1600+ 行」忠实）、`KNOWN_CLAUDE_CLI_VERSIONS = frozenset(("2.1.197", "2.1.207"))`（`:28`，2 个版本忠实）、注释 `:30-34` 明写「all 29 built-in tool contracts」（29 个忠实）。
2. sidecar「增量仍要哈希整个旧文件」：**忠实**。`request_file_stats.py:565-571` 进 incremental 前先 `_content_signature(request_path, meta["size_bytes"])`，而 `_content_signature`（`:373-383`）逐块读满 `length` 字节做 sha256；随后 `:606-613` 把旧 sidecar 整份复制到临时文件再追加。「增量只减少 JSON 重解析」准确。
   「损坏自动重建只覆盖 metadata 解析失败 / sidecar 缺失 / 长度不符，等长内容损坏是盲区」——**否定性主张，成立**。证否方法：通读 `_load_meta`（`:415-445`）列举其全部校验项——JSON 可解析、`schema_version`、`source_file`、四个整数字段、`processed_bytes <= size_bytes`、`content_sha256` **格式**、以及 `index_path.stat().st_size != meta["index_size_bytes"]`。**没有任何一处对 sidecar 内容本身取摘要**，因此等长内容改写不触发重建。（补充事实：`read_request_detail:1271` 会在读取时比对源行 sha256，等长损坏最终表现为 `RequestFileChangedError`，而不是自动重建——这与报告的判断方向一致。）
   「51KB」：`ls -la` 得 50913 字节，忠实。
3. `redact_responses_event_for_cache` 在任何 warn 告警下换成哈希：**忠实**。`compat_redaction.py:97-103`，判据是 `if audit.warnings:`——不区分 `action`，`warn` 级同样触发（`redacted_value` 只留 `_redacted/_reason/_size/_sha256`，`:31-38`）。
   「代码里那句『raw bytes are still retained』是错的」——**否定性主张，成立**。证否方法（三步 MRO 追踪）：① 那句话在 `sse/anthropic_responses.py:1140-1141` 的 `forward_malformed_data`；② 基类 `sse/base.py:176-179` 的 `raw_events_for_cache` 确实 `return list(self.raw_events)` 原文；③ **但子类覆写了它**——`sse/anthropic_responses.py:1157-1172`，畸形 payload 走 `except` 分支变成 `redacted_value(raw, "malformed Responses event")`，而 `base.py:225` 的 `_complete_cache` 用的是覆写后的版本。所以对这个 handler 而言原文进不了缓存。
4. E2E load generator 只在 status ≥400 时失败：见 2.4（代码事实忠实，「没划清这条线」偏重）。

### §4 反面样本（6 条）

1. 保活守卫读上游侧 + **退避睡眠期间静默**：**忠实**。`time.sleep(min(2 ** conn_attempt, 8))` 共 10 处（`routes/anthropic.py:613,1376,1782,2208,2374`；`routes/openai.py:267,1018,1309,1453,1838`），其中 `anthropic.py:1376` 落在 `_stream_pending_anthropic_responses_request`（起 `:1286`）的 `generate()`（起 `:1329`）**内部**——即已经 commit 了 SSE 之后、在生成器里睡最多 8 秒且不吐 keepalive。决策文档 `:161-162` 亦记为开放项。
2. 新机制只接到部分入口：`cancel()` 2/3 **忠实**；「三种 pre-header 语义」与「未修」**失真**，见 1.2。
3. 记账早于判断成败：**忠实**，见 2.7。
4. `target_path` 会失真而看起来像权威记录：**忠实**。`_convert_system` 按当时下标记账（`anthropic_responses.py:796` `f"/input/{len(input_items)-1}/..."`、`:818` `f"/input/{item_index}/content/{len(parts)}"`），随后工具转换 `input_items.insert(0, ...)`（`:1198`、`:1205`）把所有下标顶一位；紧跟其后的注释 `:1199-1200` 原文「Existing target paths in records are descriptive only; the insert does not alter preservation semantics.」
5. direct Anthropic 路径对任意非 2xx 重放 4 次、共用同一个 `X-Request-Id`：**忠实**。`routes/anthropic.py:2251-2307`——非 OK 分支先记日志与缓存，然后只有两种情况会 `continue`（web search fallback `:2277-2282`、孤儿 tool_result `:2285-2307`）；**其余情况既不 `break` 也不 `return`，直接落到 `for attempt` 的下一轮**，因此任何 400 都要打满 `max_retries + 1 = 4` 次。headers 共用见 §2.8.1。决策文档 `:166-170` 记作「One-line fix」，HEAD 上确实仍未修（这一条与 1.2 不同：这里代码与文档一致）。
6. 限流槽位可能永久泄漏：**忠实**，且报告自己标注了「可达性未证」，这个自限是对的。机制核实：`routes/webiq.py:428` 在**创建生成器之前** `try_acquire`；`release()` 只出现在 `:458`（`WebIQError` 早退）、`:473`（异常早退）、`:526`（`generate()` 的 `finally`）。若 WSGI 层拿到 `Response` 却从未开始迭代，`generate()` 的函数体从未进入，`finally` 不运行。Python 语义我用独立探针复核过（未启动的生成器 `close()` → `finally` 不执行；已启动的 → 执行）。`_MCPStreamLimiter.release` 有 `if self._active > 0` 下限保护（`:76-79`），所以是「可用槽位少一个」而非计数为负；累积到 4 即所有 MCP 请求恒 503。

### §5 三条方法论转述（对照 `RESPONSES_PRE_HEADER_KEEPALIVE.md` 原文）

1. 「当一次测量说没有差异时，先验证测量装置能不能观测到那个差异」：**忠实**。原文 `:209-216`「when a measurement says "no difference", verify the harness can actually observe the difference before believing it」，三个前提（fake 上游在 SSE body 之后仍持有连接、keepalive 留在 30 s 默认值、于是客户端离开期间没有写失败）与报告转述一一对应；配套的三条测试前置条件在 `:187-193`。
2. 「对每一条新回归测试做变异测试」：**忠实**。原文 `:217-218`「Each new test was run against the code with its fix reverted; a test that still passes is not guarding anything.」
3. 「先测量再建缓解措施」：**忠实**。原文 `:223-225`（并发上限被规格化后故意推迟，代价四个计数器 ~0.3 µs/请求，「The deferral is only defensible because the observation landed with it」）；预先写死的阈值在 D6 表格 `:120-123`（peak inflight < `server_threads` 16 → do nothing；peak > 64 或 cancelled > 10/min → 建）。`server_threads` 默认 16 见 `state.py:150`。
4. 附带的第四条「防御性散文应当变成可执行代码」：**忠实**，原文 `:219-222`。

---

## 4. 给主会话的处置建议

必须改的三处：
1. **§2.3**：把「每一档都先检查目标方言是否支持该 effort 名」改成「只有 `max`/`xhigh` 两档做了 profile 检查，`high`/`medium`/`low` 三档硬编码——**这个写法要抄的是意图，不是它现在的实现**」。这条直接影响我方要不要照抄以及怎么抄。
2. **§4.2**：改成「HEAD 上是两种语义（0.5/0.5/30）；决策文档记的三种里，翻译路径已被 `f3e8bae`（2026-08-15）收敛，文档的开放项没跟着更新」。顺带值得作为一条独立教训记下：**决策文档的开放项清单本身会过期，而它看起来像当前状态**——与 §4.4「审计线索失真比没有审计线索更危险」同族。
3. **§2.7**：12 → 13 个能力位。

建议补一句限定的四处：§1 的「门控全部 id 比较」（call_id / 工具名不在门内）、§2.1 第 3 行（执行者是审计器不是转换器，我方照抄判据时要连审计层一起建）、§3 的 44%（比例随形状变，机制上只与叶子数相关）、§3 的「没划清这条线」（改成「没写下这条边界」）。

其余 39 条转述可以按原样使用。特别值得记的是：报告在 §4.2 前半（`cancel()` 2/3）**正确地用代码覆盖了决策文档**，在 §2.9 **正确地没有把决策文档的自述升格成代码事实**——本次核查中它翻车的两处，恰好都发生在同一段里紧挨着的另一半句子上。

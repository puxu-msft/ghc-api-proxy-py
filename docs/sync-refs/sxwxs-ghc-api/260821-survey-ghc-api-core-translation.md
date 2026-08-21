# 调研报告：sxwxs/ghc-api 的 Anthropic Messages ↔ OpenAI Responses 转换与 SSE 交付

- 被调研对象：`https://github.com/sxwxs/ghc-api`，本地 clone 于 `/home/xp/.claude/jobs/89874ec2/tmp/ghc-api`，HEAD = `0cb1087`（`Merge pull request #48 from sxwxs/docs/add-deepwiki-badge`）
- 调研日期：2026-08-21
- 调研范围：`ghc_api/anthropic_responses.py`、`ghc_api/sse/anthropic_responses.py`、`ghc_api/sse/base.py`、`ghc_api/compat_profiles.py`、`ghc_api/routes/anthropic.py`、`ghc_api/json_guard.py`、`ghc_api/reasoning_carrier.py` 及对应测试
- 提问方：`/home/xp/src/ghc-api-proxy-py`（同样是 Anthropic Messages 输入 → OpenAI Responses 上游的 Python 代理）

**证据约定**：正文中 `文件:行号` 一律指向上述 clone 的 HEAD。凡标注「README 说」「注释说」的，表示我只核到了文字声明；凡直接给出代码摘录的，表示我核到了代码里确实这么写。

**权重档约定**（依 `state-decisiveness`）：

- `强到可直接采纳`：代码里读到了完整实现，且有测试或注释交代了它是被真实故障逼出来的；判断不依赖我对上游行为的猜测。
- `是个倾向、需更多样本`：代码这么写了，但我只看到单一实现、无测试佐证，或它的正确性依赖于该项目特定的上游/部署假设。
- `仅存档、不据以决策`：我只读到声明（README/注释/命名），没有独立核实，或它明显与我方立场冲突而只有档案价值。

---

## 0. 一句话总览

ghc-api 把「协议转换」当成一次**有审计记录的有损投影**来做：每一个源 JSON 叶子路径都必须被显式登记一种处置（`exact` / `semantic_encoding` / `sidecar` / `approximation` / `unsupported`），没登记的叶子会在 `finalize()` 阶段被自动兜底成 `unsupported` 并产生一条客户端可见的兼容性告警。这套「全叶子记账」是它与一般实现最大的结构性差异，也是本报告最值得我方评估的抽象。

---

## 1. Anthropic → Responses 请求转换：字段与边界

### 1.1 记账骨架：`ConversionReport` 与「未登记即 unsupported」

`anthropic_responses.py:155-265` 定义了 `PreservationRecord` / `ConversionReport`。核心机制在 `finalize`：

```python
# anthropic_responses.py:245-257
def account_unknown_paths(self, source: Any) -> None:
    self.unaccounted_paths = []
    for path in iter_json_leaf_paths(source):
        if not self._is_accounted(path):
            self.unaccounted_paths.append(path)
            self.mark(path, PRESERVATION_UNSUPPORTED,
                      detail="No registered conversion rule for this source path")
```

`iter_json_leaf_paths`（`:136-152`）把整个请求体展开成 RFC-6901 风格的叶子路径（空容器也算一个叶子，`:139-141`）。`_is_accounted`（`:230-243`）支持「子树标记」：`mark(..., subtree=True)` 之后，该路径下所有后代都算已登记。

五档处置常量在 `:28-32`；其中 `approximation` 与 `unsupported` 会自动追加一条 warning（`:219-228`）：

```python
if disposition in (PRESERVATION_APPROXIMATION, PRESERVATION_UNSUPPORTED):
    warning = {"code": "conversion.approximation" if ... else "conversion.unsupported",
               "path": source_path, "action": disposition}
```

**这条设计的实际价值**：新版本 Anthropic 客户端加了一个我们没实现的字段时，不是静默丢弃，而是自动变成一条带精确 JSON 指针的告警。它把「我忘了处理这个字段」从一类沉默 bug 变成了一条可观测输出。

权重：`强到可直接采纳`（机制完整，`tests/test_anthropic_responses_translation.py` 有直接断言 `unaccounted_paths` 为空的用例，见 §6）。

### 1.2 system

`_convert_system`（`:780-825`）：

- `system` 为 str → 一条 `{"type":"message","role":"developer","content":[{"type":"input_text",...}]}`（`:795`）。注意用的是 `developer` 而不是 `system` role。
- `system` 为 block 数组 → 只接受 `type == "text"` 的块，其余 `unsupported`（`:805-807`）；所有文本块合并成**单个** developer message 的多个 part（`:824-825`）。
- 有一处很特别的坑：`:787-794` 和 `:809-816` 都会把以 `x-anthropic-billing-header:` 开头的 system 文本整块丢掉，标为 `semantic`，理由写作「Synthetic Anthropic billing metadata omitted from model input」。这是 Claude Code 客户端注入的合成计费头，直接发给上游模型是污染。

权重：`是个倾向、需更多样本`。`developer` role 的选择与 billing-header 剥离都是对特定上游/客户端的经验判断，我方需要用自己的 cassette 核实 Copilot 是否同样接受 `developer`。

### 1.3 tools

`_convert_tools`（`:995-1082`）：

- **web_search 服务端工具单独成路**：`type` 以 `web_search_` 开头的走 `_convert_web_search_tool`（`:922-992`）；如果这类工具带了 `input_schema`，直接 `raise`（`:1013-1015`），理由是 Anthropic 服务端工具不允许定义 schema。
- **不把未知服务端工具悄悄降级成 function**（`:1031-1035`）：

```python
# Other Anthropic server tools have a provider-specific `type` and may
# not include input_schema. They are not silently coerced to functions.
if tool_type and tool_type != "custom" and "input_schema" not in tool:
    report.mark(path, PRESERVATION_UNSUPPORTED, detail=f"Unsupported Anthropic server tool type: {tool_type}")
    continue
```

- **空 description 的替身**（`:1048-1057`）——这是明显踩过坑之后加的，注释写得很直白：

```python
elif "description" in tool:
    # Copilot's /responses rejects a tool whose description is present
    # but empty, so a blank (or non-string) one gets a deterministic
    # stand-in instead of being forwarded as "".  A description that
    # is absent stays absent: the target schema treats it as optional,
    # which is exactly what the Anthropic tool declared.
    target["description"] = f"Tool: {original_name}."
```

「缺席」与「存在但为空」被区别对待——缺席保持缺席，空串才替换。这一区分正是一般实现会做错的地方（通常会无条件补一个默认 description）。

- `strict` 必须是 bool，否则 `raise`（`:1039-1041`）。
- 工具扩展字段 `cache_control` / `defer_loading` / `allowed_callers` 记为 `sidecar`（`:1079-1081`）。

**web_search 的边界检查**（`_convert_web_search_tool`，`:922-992`）值得单列：

- `allowed_domains` 与 `blocked_domains` **同时出现直接 raise**（`:945-948`），不是二选一容错。
- `user_location` 用白名单键集合 + 「至少一个非空字符串字段」双重校验（`:962-975`），不合法则 raise。
- `max_uses` 校验为正整数（含 `isinstance(bool)` 排除，`:984`），但由于 Responses 侧没有等价上限，只记 `approximation` 不 raise。

权重：`强到可直接采纳`（空 description 那条）；其余 `是个倾向、需更多样本`。

### 1.4 tool_choice

`_convert_tool_choice`（`:869-919`）：

- 字符串 `"any"` → `"required"`（`:877`）。
- 对象形式：`auto`/`any`/`none`/`tool` 四种（`:889-903`）；`type == "tool"` 且 `name == "web_search"` 且本请求确实转出了原生 web_search 服务端工具时，映射为 `{"type":"web_search"}` 而非 function（`:897-899`）。
- `disable_parallel_tool_use` 非 bool 直接 raise（`:907-917`），映射到 `/parallel_tool_calls`（`:1279-1281`，取反）。
- **交叉校验**（`:1252-1271`）：`tool_choice.type == "tool"` 指定的名字如果不在本次实际转换出的工具集合里，直接 `raise`：

```python
if chosen_name not in available_names:
    report.mark("/tool_choice/name", PRESERVATION_UNSUPPORTED,
                detail="tool_choice names a tool that was not converted")
    raise AnthropicResponsesConversionError("Anthropic tool_choice names an unavailable tool", report)
```

这是一处**本地前置校验代替上游 400 往返**的设计。

权重：`强到可直接采纳`。

### 1.5 thinking → reasoning.effort

`_map_reasoning_effort`（`:828-866`）：

- 优先读 Anthropic 新字段 `output_config.effort`，落在 profile 支持的 effort 集合里就 `exact` 透传（`:830-837`）。
- 否则从 `thinking` 推断：`disabled` → `none`（profile 不支持 `none` 则退 `low`，`:842-843`）；`adaptive`/`auto` → `high`（不支持则取 profile 列表最后一项，`:844-845`）；`enabled` 则按 `budget_tokens` 分档（`:846-865`）：

```python
if numeric >= 30000 and "max" in profile.reasoning_efforts: effort = "max"
elif numeric >= 16000 and "xhigh" in ...: effort = "xhigh"
elif numeric >= 8000: effort = "high"
elif numeric >= 3000: effort = "medium"
else: effort = "low"
```

分档阈值本身是拍脑袋的，但**每一档都先检查 profile 是否支持该 effort 名**，而不是硬编码一套名字发出去。

- `thinking` 里其余未识别的键统一记 `sidecar`（`:1298-1302`），避免污染 `unaccounted_paths`。

权重：`是个倾向、需更多样本`（阈值是经验值，无测试佐证其正确性；但「先查 profile 支持集」的写法值得抄）。

### 1.6 image / document / 多模态

- `_convert_image_block`（`:468-491`）：`source.type == "base64"` → `input_image` + data URL（`_data_url`，`:437-438`），默认 media_type `image/png`；`source.type == "url"` → 直接 `image_url`；其余 `unsupported` 且返回 `None`（该块被丢弃但已登记）。
- `_convert_document_block`（`:494-525`）：`base64` → `input_file` + `file_data` data URL（默认 `application/pdf`）；`url` → `file_url`；`text` → **降级为 `input_text`** 并记 `semantic`（`:511-514`，注释写明 "Public Responses has no byte-identical document-text part"）。`title` / `context` / `citations` 三个 Anthropic 专有字段记 `sidecar`（`:520-522`）。

权重：`是个倾向、需更多样本`。

### 1.7 cache_control

`_cache_control_to_part`（`:441-465`）：profile 支持显式断点时映射为 `{"prompt_cache_breakpoint": {"mode": "explicit"}}`；如果 Anthropic 侧还带了 `ttl` 或 `scope`，处置从 `semantic` 降级为 `approximation`（`:456-457`）——即「边界保住了，但 TTL/scope 语义可能不同」。profile 不支持时记 `sidecar` 并说明理由（`:459-465`）。

另外，会话级缓存键是**派生**而非透传的（`:1376-1388`）：

```python
cache_scope = f"{tenant_scope}\x00{session_id}\x00{model}"
responses["prompt_cache_key"] = hashlib.sha256(cache_scope.encode("utf-8")).hexdigest()
```

用 `\x00` 作分隔符防止字段拼接歧义，且把 model 纳入 scope。`copilot_responses_lite` 额外再发一个 `client_metadata.session_id`（不含 model 的另一个 hash）。

权重：`强到可直接采纳`（`\x00` 分隔 + model 纳入 scope 这两点）。

### 1.8 tool_use / tool_result 与「配对与排序」

这一节是我认为最值得我方直接借鉴的部分。

**（a）消息被 tool_use / tool_result 切段**。`_append_message_items`（`:587-777`）维护 `current_parts` 与 `flush_message()`（`:616-626`）：遇到 `tool_use`（`:651-652`）或 `tool_result`（`:695`）就先 flush 掉当前累积的 message item，再 append 一个独立的 `function_call` / `function_call_output` item。这样 Anthropic 的「一条 assistant 消息里文本和 tool_use 混排」被正确展开成 Responses 的有序 item 列表，且**顺序保持源顺序**。

**（b）assistant `phase` 的推断**（`:621-623`）：

```python
if role == "assistant" and profile.supports_message_phase:
    item["phase"] = "commentary" if has_tool_use else "final_answer"
```

`has_tool_use` 是**整条消息级别**的预扫描（`:612`），不是当前段级别。

**（c）孤儿 tool_result 的本地丢弃**（`:677-694`）——注释直接写明了故障：

```python
if original_id not in called_tool_ids:
    # A tool_result whose tool_use is not in this request (history
    # truncation, compaction, a client-side edit) makes the whole
    # upstream call fail with "No tool call found for function call
    # output".  The converter sees the entire conversation, so the
    # pairing is decided here instead of by an upstream round trip:
    # the block is dropped and reported.  The other direction (a
    # tool_use with no result) is left untouched -- synthesising an
    # output would invent a tool answer the model never produced.
    report.mark(path, PRESERVATION_APPROXIMATION, detail="tool_result has no paired tool_use in this request and was dropped", subtree=True)
    continue
```

两个方向被区别对待：孤儿 `tool_result` 丢弃（因为上游会硬失败），孤儿 `tool_use` 保留（因为补一个假 output 等于编造工具答案）。`called_tool_ids` 在 `convert_anthropic_to_responses` 里跨消息累积（`:1214`, `:1230`），所以判据是「本次请求全量对话里有没有」，而不是「上一条消息里有没有」。

**（d）`is_error` 的可逆信封**（`_convert_tool_result_output`，`:528-584`）：

```python
if block.get("is_error") is True:
    # Responses has no native tool-result error bit. Use a namespaced,
    # deterministic JSON envelope ...
    return _canonical_json({"ghc_anthropic_tool_result": {"is_error": True, "content": copy.deepcopy(content)}})
```

同时在 `:701-705` 对 `is_error: False` 与 `is_error: True` 给不同处置（False 等同默认成功语义，记 `semantic`；True 记 `approximation`）。

权重：（a）(c) `强到可直接采纳`；（b）(d) `是个倾向、需更多样本`。

### 1.9 IdentifierCodec：函数名与 call_id 的可逆编码

`anthropic_responses.py:354-408`。目的：Responses 侧对 function name / call_id 有字符集与长度约束（`^[A-Za-z0-9_-]+$`，默认 64 字符），Anthropic 侧没有。

关键设计是**请求作用域内保持单射**（`:392-401`）：

```python
# A client can deliberately choose a valid identifier equal to the
# hashed representation of another value. Keep the codec injective
# instead of silently aliasing two tools or call IDs.
for attempt in range(1024):
    candidate = self._hashed_candidate(value, kind, attempt)
    owner = self._encoded_to_original.get(candidate)
    if owner is None or owner == value:
        encoded = candidate
        break
```

即：合法标识符直接透传（`:380-387`，且要求该值尚未被别的原值占用）；否则 `ghc_tool_` / `ghc_call_` 前缀 + 清洗后的可读片段 + sha256 前 16 位，冲突则加 attempt 盐重试。同一个 codec 实例在整条请求-响应-流式链路上被共享（`AnthropicToResponsesResult.name_codec`，`:414-415`；流式端 `sse/anthropic_responses.py:1123-1124`），因此回程 `decode` 一定能还原。

**注意这是有意的「非全局稳定」**：codec 是请求作用域的，跨请求不保证同一个名字编出同一个 ID。这对多轮对话意味着：历史里的 `tool_use.id` 每轮都被重新编码，但因为同一请求内 encode/decode 成对，所以自洽。

权重：`强到可直接采纳`（单射保证那段）。

### 1.10 其余请求字段

| Anthropic 字段 | 处理 | 位置 |
|---|---|---|
| `model` | exact 透传 | `:1184-1185` |
| `stream` | 非 bool 直接 raise | `:1166-1176` |
| `max_tokens` | → `max_output_tokens`，profile 不支持则记 approximation 且不发 | `:1329-1334` |
| `temperature` / `top_p` | 由 profile 开关决定发不发 | `:1335-1341` |
| `top_k` | 无条件 `unsupported`（Responses 无此参数） | `:1342-1343` |
| `stop_sequences` | **不发给上游**，记 approximation，改由代理在输出侧执行 | `:1345-1352` |
| `metadata` | 非字符串值转成 canonical JSON 文本，记 sidecar | `:1354-1374` |
| `service_tier` | `standard_only` → `default` 等映射表 | `:1390-1397` |
| `output_config.format` | 只支持 `json_schema`，未知字段直接 raise | `:1093-1145` |
| `context_management` | 只认 `clear_thinking_20251015` + `keep: all` → `reasoning.context = "all_turns"` | `:1304-1327` |

固定注入的三个字段（`:1177-1183`）：`store: False`、`include: ["reasoning.encrypted_content"]`。

`output_config.format` 的 schema name 生成值得一提（`:1114-1124`）：客户端给的 name 不合法（非标识符 / 超 64 字符）时，用 schema 的 canonical JSON 的 sha256 生成 `ghc_schema_<16hex>`，**同一个 schema 永远得到同一个 name**。

权重：整表 `是个倾向、需更多样本`；`stop_sequences` 在代理侧执行那条见 §2.5，权重更高。

---

## 2. Responses → Anthropic：响应与流式转换的组织方式

### 2.1 分层：纯状态机 + 传输适配器

`sse/anthropic_responses.py` 分成两层（模块 docstring `:1-6` 明写）：

- `ResponsesAnthropicEventTranslator`（`:115-1097`）：纯函数式状态机，`process(event_type, event) -> List[(anthropic_event_type, event_dict)]`，不碰 Flask、不碰 cache、不碰网络。
- `AnthropicResponsesStreamHandler`（`:1100-1256`）：继承 `SSEStreamHandler`，只负责把状态机接到共享 SSE/cache 传输上。

`sse/base.py` 提供的模板方法有一个值得注意的设计（`base.py:101-107`）：**上游每一条 `data:` payload 原样进 `self.raw_events`，先记账再解析**（`base.py:319-322`）：

```python
# Record the raw payload before anything else so even
# malformed JSON is preserved in the cache.
self.response_wire_bytes += len(data.encode("utf-8"))
self._capture_raw_value(self.raw_events, data)
```

于是「上游发了什么」与「我们翻译成了什么」两件事在故障现场都能拿到。`finally` 块（`base.py:382-387`）保证客户端断连也会落一条完整 cache 记录。

权重：`强到可直接采纳`（先记账后解析 + finally 落盘）。

### 2.2 `output_item.added` 与 `.done` 之间 item id 变化 —— 这是它明确处理过的

**这是我方最关心的一点，结论：它不用 item id 做跨事件身份，而是用 `output_index`；并且把「id 是否稳定」提升成了 profile 的一个显式能力位。**

证据链有三处，互相印证：

**（a）profile 上的显式能力位**，`anthropic_responses.py:283-285`：

```python
# Copilot may encrypt the same logical response/item id differently in
# every SSE frame. Such ids cannot be used as cross-event identity keys.
stable_ids: bool = True
```

三个 profile 中，`copilot_public_responses` 与 `copilot_responses_lite` 都是 `stable_ids=False`（`:320`, `:339`），只有 `public_responses` 保持 `True`。`copilot_public_responses` 的注释（`:305-308`）交代得更细：

```python
# Grok uses the standard Responses request shape through Copilot, but
# Copilot still re-encrypts response and item ids independently in
# every SSE frame. It therefore cannot use public_responses' stable-id
# stream invariants.
```

**（b）身份键是 `output_index`，不是 id**。`_OutputState`（`sse/anthropic_responses.py:93-112`）以 `output_index` 为主键，`_state()`（`:207-217`）用 `int(output_index)` 查表。`_merge_item`（`:271-381`）在合并 added/done/terminal 三次看到的同一个 item 时，**对 `id` 字段完全不比较**——它只比较 `type`（`:279-285`）、`call_id`（`:296-304`）、`name`（`:305-312`）、以及 `arguments`/`text` 的前缀单调性（`:314-372`）。唯一比较 `id` 的地方是 `web_search_call`，而且被 `stable_upstream_ids` 门控（`:288-295`）：

```python
if effective_type == "web_search_call" and self.stable_upstream_ids:
    incoming_id = item.get("id")
    existing_id = state.item.get("id") if isinstance(state.item, dict) else None
    if incoming_id is not None and existing_id is not None and str(incoming_id) != str(existing_id):
        return ("responses.web_search_id_mutation", f"/output/{state.output_index}/id")
```

同样被门控的还有：终局 `response.id` 与 created 的比对（`:662`）、`response.created` 重复出现时的 id 比对（`:757-761`）、annotation 事件的 `item_id` 比对（`:790-797`）、web_search 生命周期事件的 `item_id` 比对（`:825-832`）。

**（c）测试直接把 id 轮换写成了正样本**，`tests/test_sse_anthropic_responses.py:601-662`：

```python
def test_copilot_profiles_accept_per_event_opaque_response_ids(self):
    """Copilot returns a different encrypted response.id on every event of
    one stream, including for Grok's standard Responses request dialect.
    Only call_id is stable on these profiles."""
```

测试里 `response.id` 走 `opaque-A → opaque-B → opaque-C`，item id 走 `opaque-item-A → opaque-item-B → opaque-item-C`，断言 `protocol_failed` 为 False、输出文本完整、客户端可见的 `message_start.id` 不随上游 id 轮换而改变（`:657-662`）。同一份测试文件的 `:143-160` 还专门验证 web_search 生命周期事件在 lite profile 下允许 `item_id` 每帧不同。

**评价**：这套做法比「猜哪个 id 是真的」或「用 id 做键并在变化时重建 state」都干净。关键洞见是：**Responses SSE 本来就自带一个稳定的身份键 `output_index`，id 是冗余的**；只要不去用它，缺陷就不存在。而 `stable_ids` 位保留了在真正稳定的上游上继续做 id 一致性校验的能力，不是一刀切放弃校验。

权重：`强到可直接采纳`。判据不依赖我对 Copilot 的猜测——代码、注释、测试三处互证，且与我方已知的上游真实缺陷完全吻合。

### 2.3 reasoning / thinking signature 的承载与版本化

载体定义在 `reasoning_carrier.py`：

- 前缀常量 `REASONING_CARRIER_PREFIX = "ghc-api:responses-reasoning:v1:"`（`:22`）——命名空间 + 版本号写死在字符串里。
- 负载是 canonical JSON（`sort_keys=True, separators=(",",":"), allow_nan=False`，`:35-42`）再 base64url 无填充（`:67`）。
- 四个字段固定：`encrypted_content` / `item_id` / `model` / `wire_profile`（`:61-66`）。

**解析是严格的，且区分三种结局**（`parse_reasoning_carrier`，`:78-138`）：

1. 不带前缀 → 返回 `None`（外来签名，不是我们的东西）。
2. 带前缀但畸形 → `raise ValueError`。docstring（`:79-83`）说明了为什么要区分：「lets callers drop corrupt opaque state while still preserving the visible reasoning summary and reporting a compatibility warning」。
3. 合法 → 返回 `ReasoningCarrier`。

严格性包括：base64url 字符集正则（`:90`）、长度模 4 不能为 1（`:90`）、**规范性回环校验**（`:99-101`，重新编码必须字节相同，杜绝非规范 base64 变体）、payload 内部也走一遍拒绝重复键 + 拒绝非有限数的 JSON 解析（`:103-119`）、键集合必须精确等于四元组（`:122-125`）。

**回程使用时的三重门控**（`anthropic_responses.py:708-767`）：

```python
profile_matches = (
    carrier.wire_profile == profile.name
    or (profile.name == "copilot_public_responses" and carrier.wire_profile == "public_responses")
)
if carrier.model != target_model or not profile_matches:
    report.mark(path, PRESERVATION_APPROXIMATION,
        detail="Responses reasoning carrier belongs to a different model or wire profile; visible summary retained", subtree=True)
else:
    encrypted_content = carrier.encrypted_content
    carrier_item_id = carrier.item_id
```

即：模型或 wire profile 不匹配时，**丢掉 encrypted_content 但保留可见的 summary 文本**，并出一条 approximation 告警；`public_responses` → `copilot_public_responses` 单向兼容（历史配置迁移，见 `api_helpers.py:398-402`）。`item_id` 只在 `profile.preserves_reasoning_item_ids` 为真时回填（`:756-757`）。

**尺寸兜底**：`MAX_REASONING_CARRIER_CHARS = 1MB`（`:23`）；构造超限时上层降级为「不带 encrypted_content 的空载体」并记 approximation，而不是整体失败（`anthropic_responses.py:1774-1792`，`sse/anthropic_responses.py:521-539`，两条路径写法一致）。

**跨路径卫生**：`strip_reasoning_carriers_from_messages_payload`（`reasoning_carrier.py:160-206`）在请求转去原生 Anthropic 端点或 legacy chat-completions 翻译器之前，把这些合成 thinking 块摘掉（调用点 `routes/anthropic.py:1011-1013` 与 `:1052-1054`），理由是「Sending it to a native Anthropic model would present a forged thinking signature and can make the upstream reject the request」（`:166-168`）。摘干净后变成空 content 的 assistant turn 会被整条丢弃（`:194-198`）。

**缓存卫生**：`redact_reasoning_carriers_for_cache`（`:141-157`）把载体替换成 `[Responses reasoning carrier: N bytes, sha256=...]`。注意这是**可逆状态**而非「敏感信息」的考虑——`routes/anthropic.py:992-998` 的注释写的是 "Reasoning carriers are reversible and must never be persisted verbatim"。

**与我方的关系**：我方也用自有版本化 reasoning 载体。ghc-api 这一份可以当作一个成熟同类实现来对照，特别是「畸形载体降级而非失败」「模型/profile 不匹配时保 summary 丢密文」「跨路径剥离」三条策略。

权重：`强到可直接采纳`（三条策略）；载体的具体编码格式对我方 `不适用`（我方已有自己的格式，且互不兼容也无所谓）。

### 2.4 未知 output item 类型：fail closed 502 —— 核实结论「部分属实，但更精细」

README 的说法我核实了，需要**拆成三个不同的层面**，它们的处理并不相同：

| 未知的东西 | 处理 | 证据 |
|---|---|---|
| 未知 **output item type** | fail closed | `compat_profiles.py:1525-1534` `fail_always=True`；`sse/anthropic_responses.py:857-858` 与 `:557-558` 走 `_protocol_error`；非流式 `anthropic_responses.py:1903-1908` 直接 `raise` |
| 未知 **content part type** | fail closed | `compat_profiles.py:1586-1600` 与 `:1708-1719` `fail_always=True`；`anthropic_responses.py:1834-1835` `unsupported` |
| 未知 **SSE event type** | **只告警，跳过** | `compat_profiles.py:1650-1664`（无 `fail_always`）；`sse/anthropic_responses.py:1077-1092` |

第三行的注释把理由写得很完整（`sse/anthropic_responses.py:1077-1086`）：

```python
# An event type this build does not know. Skipping it is not the same
# as losing its payload: the terminal response.completed/.incomplete
# carries the full output array and _hydrate_terminal merges it, so any
# model output the skipped event previewed is still delivered -- at the
# end of the stream rather than incrementally. Anything that would
# actually corrupt or drop output still fails closed elsewhere: an
# unknown item type or content part is rejected by the auditor and by
# convert_responses_to_anthropic, a conflicting item index trips
# item_type_mutation, and a stream with no terminal event trips
# stream_ended_without_terminal.
```

`compat_profiles.py:1651-1657` 从运维角度补了另一半理由：「Copilot's /responses is an evolving upstream; rejecting every additive event would take the whole Anthropic compatibility path down on someone else's deploy.」

配套的兜底是 `finalize_interrupted`（`:1094-1097`）：流结束却没见到终局事件 → `responses.stream_ended_without_terminal` 协议错误。测试 `test_unknown_event_is_skipped_and_terminal_hydration_recovers_output`（`tests/test_sse_anthropic_responses.py:791`）与 `test_unknown_event_without_a_terminal_event_still_fails_closed`（`:822`）分别钉住这两半。

**注意一个例外**：非流式路径上，未知的 `response.status` 是 fail closed 的，理由与流式未知事件相反（`routes/anthropic.py:1936-1946`）：「this body is the terminal answer, and the status is what says whether the output is complete, truncated, or failed. Reject rather than guess.」

这个「按**可恢复性**而不是按**未知性**来决定 fail open / fail closed」的判据，是整份代码里我认为最值得学的一条设计原则。

权重：`强到可直接采纳`。

### 2.5 交付顺序：`_drain` 与块的生命周期

`_drain()`（`:461-623`）是整个流式转换的心脏。规则：

1. 严格按 `next_output_index` 递增消费（`:463`），一个 index 没就绪就整体停住（head-of-line blocking）。这保证 Anthropic 侧的 `content_block` index 单调递增且每块恰好一次 start / 一次 stop。测试 `test_interleaved_parallel_calls_each_start_and_stop_once`（`tests/test_sse_anthropic_responses.py:277-297`）就是钉这个的：上游 index 0/1 的 delta 交错到达，输出仍是 `starts == [0,1]`、`stops == [0,1]`。
2. `_state_ready`（`:446-459`）决定每种 item 何时可以开始吐：
   - `message`：有文本就吐（增量交付）。
   - `function_call` / `custom_tool_call`：**必须等 `done`**，注释写明理由（`:451-453`）：「Buffer the complete argument string so malformed/non-object JSON can never be partially committed to an Anthropic tool block.」
   - `reasoning` / `web_search_call`：等 `done`。
3. `_start_block` 里有一道自检（`:391-394`）：如果发现另一个 output_index 的块还开着就报协议错误，注释是「The drain algorithm should make this impossible」——**给不变量配一个显式断言，而不是相信它**。

**与我方立场的对照**：ghc-api 是「文本增量 + 工具参数整块」的混合模式。我方的块级交付是更强的约束（一个完整 content block 才是交付单元）。ghc-api 的 `_drain` 骨架（按 output_index 排序、就绪判定与吐出解耦、块生命周期集中在 `_start_block`/`_close_block`）在块级交付下同样成立——只要把 `_state_ready` 里 `message` 那一支也改成 `state.done`。这是一个**可以只改一行就切换交付粒度**的结构。

权重：`强到可直接采纳`（结构）；`_state_ready` 的具体粒度选择对我方 `不适用`。

### 2.6 stop_sequences 在代理侧执行

两套实现，非流式与流式各一：

- 非流式 `_truncate_blocks_at_stop`（`anthropic_responses.py:1433-1481`）：把连续的 text 块按「同一个来源 item」分段（`group_ids`，来自 `content_group_ids`，`:1730`/`:1798`/`:1823`/`:1892`），**跨块拼接后再找 stop**，命中后截断并丢弃其后的一切（包括 tool_use）。注释 `:1441-1443`：缺少来源信息时每块自成一段，「safer than matching across a hidden tool/item boundary」。
- 流式 `StopSequenceScanner`（`sse/anthropic_responses.py:45-90`）：`push()` 永远保留 `max_length - 1` 个字符不吐出（`:76-82`），确保跨 chunk 的 stop 前缀不会先泄漏给客户端；`finish()` 在 item done 时把尾巴放出来。测试 `test_matches_across_chunks_without_leaking_prefix`（`tests/test_sse_anthropic_responses.py:16`）与 `test_stop_sequence_across_text_deltas`（`:709`，`"before<ST"` + `"OP>after"` → 只吐 `"before"`）钉住。
- 命中后，`_drain` 会把后续 item 的块**平衡关闭但不吐内容**（`:560-571`），`test_stop_sequence_suppresses_later_tool`（`:721`）验证上游后来的 function_call 完全不出现在客户端流里。

这里有一个我方要注意的**权衡**：因为 `stop_sequences` 不发给上游（`anthropic_responses.py:1350`），上游仍会把 stop 之后的 token 全部生成完并计费，代理只是不转发。ghc-api 把这一点记成了 `approximation` 告警，是诚实的。

权重：`强到可直接采纳`（`StopSequenceScanner` 的 `max_length - 1` 保留策略，以及命中后平衡关闭块的做法）。

### 2.7 `X-GHC-Compatibility-Warnings` 头是怎么产生和聚合的

链路（全部在 `routes/anthropic.py`）：

1. **四个来源**：请求侧 profile 审计 `audit_anthropic_request(...).warnings`（`:1578-1585`）、请求转换报告 `conversion.report.warnings`（`:1660`）、响应侧事件审计 `audit_responses_event(...).warnings`（`:1970-1980`）、响应转换报告 `translated.report.warnings`（`:2081-2083`）。流式路径上第四项来自 `translator.compatibility_warnings`（`sse/anthropic_responses.py:1238`）。
2. **净化**：`_sanitise_compatibility_warning`（`:103-114`）**白名单重建**每条 warning，只保留 `code` / `path` / `action` 加上 `profile` / `cli_version` / `observed_type` / `fingerprint` 四个可选字段，且都必须是非空字符串。`_compatibility_warning`（`:84-100`）的 docstring 直说：「Build a warning that cannot accidentally contain request content.」
3. **去重合并**：`_merge_compatibility_warnings`（`:117-129`）用 `tuple(sorted(warning.items()))` 做键，保持插入序。
4. **落头**：`_compatibility_header_value`（`:169-175`）**只取 code 集合、排序、逗号连接、截断到 1024 字节**：

```python
codes = sorted({str(item.get("code")) for item in warnings if item.get("code")})
if not codes:
    return None
# This is a diagnostic hint, not the authoritative report. Keep it within
# conservative proxy header limits; the complete list stays in cache.
return ",".join(codes)[:1024]
```

完整列表进请求缓存（`extra_cache_fields`，`sse/anthropic_responses.py:1237-1256`），头只是索引。
5. **日志限流**：`_log_compatibility_warnings`（`:136-166`）按 `(code, path, profile+cli_version+fingerprint)` 五分钟去重打印，且字典超过 4096 条时淘汰最旧的 1024 条（`:154-158`），注释是「Bound a long-running process even under adversarial field drift」。同时无条件 `counters.incr("compat." + code...)`，即**计数不限流、打印才限流**。

`_WarningCollector.add`（`compat_profiles.py:738-784`）在源头就保证了 warning 不含值：证据只进 `fingerprint` 的 sha256，不进 warning 本体（`:754-767`）；未知字段名如果不匹配安全正则会被替换成 `<redacted-key>`（`compat_profiles.py:898-903`）。

**评价**：「头是索引、缓存是权威、日志限流但计数不限流」这三条分工很干净。至于「warning 不含请求值」这一条——按我方立场（`no-imagined-security-theater`）需要甄别：ghc-api 的模块 docstring（`compat_profiles.py:5-7`）把它当成硬约束，但它的**副作用是 fingerprint 稳定**（同一形状的漂移不论具体 prose 都得到同一指纹，`:755-757`），这才是对我方有价值的部分，而不是「防泄漏」那一层动机。

权重：聚合与分工 `强到可直接采纳`；「warning 绝不含值」的动机部分 `仅存档、不据以决策`（那是它的威胁模型，不是我方的）。

---

## 3. `compat_profiles.py` 的 "wire profile" 到底是什么

**先纠正调研提问里的一个前提**：`compat_profiles.py` 里**没有** wire profile。项目里有两个都叫 profile 的东西，它们职责完全不同：

| | `ResponsesWireProfile` | `CompatibilityProfile` |
|---|---|---|
| 定义处 | `anthropic_responses.py:268-341` | `compat_profiles.py:682-703` |
| 是什么 | **上游 Responses 方言的能力矩阵** | **客户端/上游报文形状的身份指纹** |
| 回答什么问题 | 「这个上游收不收 `temperature`？tools 放顶层还是塞进 input？它的 id 稳不稳？」 | 「这个请求长得像不像我见过的 Claude Code 2.1.207？」 |
| 谁选它 | `api_helpers.anthropic_responses_wire_profile(model_id)`（`:387-409`），按模型 id 匹配，运维配置 > 内置规则 > 全局兜底 | `_make_anthropic_profile()` 从 User-Agent / anthropic-version / anthropic-beta 头推出 |
| 影响什么 | 请求体的实际构造与流式不变量的强弱 | 只产生 warning，几乎不改变行为 |

### 3.1 `ResponsesWireProfile`：值得抄的那个

12 个能力位（`:268-285`）：`tools_in_input`、`supports_native_web_search`、`native_server_tools_in_input`、`supports_prompt_cache_breakpoint`、`supports_temperature`、`supports_top_p`、`supports_max_output_tokens`、`supports_message_phase`、`supports_reasoning_context`、`preserves_reasoning_item_ids`、`reasoning_efforts`（元组）、`default_text_verbosity`、`stable_ids`。

**它解决的问题**：Copilot 的 `/responses` 不是一个方言，是好几个——GPT-5.x 走 `copilot_responses_lite`（tools 塞进 input 的 `additional_tools` item、有 `phase`、不认 temperature、reasoning 支持 `max` 档、默认 `text.verbosity=low`），Grok 走 `copilot_public_responses`（标准请求形状但 id 不稳），真·OpenAI 公有端点走 `public_responses`。如果没有这层抽象，这些差异会以 `if model.startswith("grok-")` 的形式散落在转换器的几十个分支里。

**每个能力位都带着它的证据出处**，这点很重要。例如 `:326-331`：

```python
# The live backend accepts native server tools only in top-level tools;
# placing web_search inside additional_tools silently removes it.
native_server_tools_in_input=False,
# The supplied dump proves prompt_cache_key but not explicit breakpoints.
supports_prompt_cache_breakpoint=False,
```

「dump 证明了 A 但没证明 B，所以 B 取保守值」——这是**用录制证据反推能力矩阵**，与我方的 cassette 立场同源。

**值不值得抄？值得，但要抄对层次。** 真正的价值不是这 12 个字段（那是它的上游），而是三条规则：

1. **能力位由录制证据决定，未被证明的取保守值**，并把证据出处写在字段旁边的注释里。
2. **能力位要影响流式不变量的强弱，而不只是请求体字段**。`stable_ids` 是全项目最好的例子：它让「校验 id 一致性」这件事从「要么全做要么全不做」变成了 per-profile 的选择。
3. **profile 名要进 reasoning 载体**（`reasoning_carrier.py:30`, `anthropic_responses.py:726-739`），这样跨 profile 的历史重放会被识别出来并降级，而不是把 A 方言的密文喂给 B 方言。

反面：`get_wire_profile` 用 `WIRE_PROFILES` 全局字典硬编码（`:288-348`），加一个上游要改源码；`api_helpers.py:387-409` 又叠了一层运维配置覆盖 + 一条 Grok 专用的历史迁移 hack（`:398-402`）。这套两层选择逻辑我方不必照抄。

权重：三条规则 `强到可直接采纳`；12 个字段的具体取值 `仅存档、不据以决策`（那是它对 Copilot 的观测，我方应该用自己的 cassette 得出）。

### 3.2 `CompatibilityProfile` / 客户端漂移审计：我方大概率不需要

`compat_profiles.py` 有 1762 行，其中约 620 行是**声明式的形状表**（`_TOP_LEVEL_TYPES` / `_CONTENT_BLOCK_FIELDS` / `_RESPONSES_EVENT_FIELDS` / `_RESPONSES_EVENT_REQUIRED_FIELDS` / `_RESPONSES_ITEM_FIELDS` / …，`:134-618`），剩下是遍历这些表的通用检查器（`_check_type` / `_check_enum` / `_unknown_fields` / `_require_fields`，`:862-935`）。

它还内置了 **29 个 Claude Code 内置工具契约的 sha256 基线**，两个 CLI 版本各一份（`:35-98`）。注释说明了为什么存哈希而不存原文（`:30-34`）：「Hashes let the runtime detect same-version contract drift without embedding proprietary prompt or description text in this repository.」`canonical_tool_contract_hash`（`:1150-1162`）在算哈希时特意排除 `cache_control`，理由是「request-placement state rather than part of a tool's callable contract」。

**我的判断**：这一整块对我方是 `不适用` 或 `存疑`。

- 它在解决的是「Claude Code 客户端升级后偷偷改了报文形状，我要第一时间知道」这个**运维可观测性**问题，不是转换正确性问题。它的 warning 绝大多数 `action == "warn"`，不改变任何行为。
- 维护成本极高：29 个工具 × N 个 CLI 版本的哈希基线需要人肉重新采集；`KNOWN_CLAUDE_CLI_VERSIONS` 只认两个版本，任何别的版本都会稳定产出一条 `claude_cli.unknown_version` 告警（`:1447-1454`），噪音基线不低。
- 按我方的 `build-proof-infrastructure-only-if-requested`，这属于「为任务额外搭建的证明基础设施」。

**但其中两个零件值得单独摘出来**：

1. `audit_responses_item` 的 `fail_always=True`（`:1521`, `:1532`, `:1582`, `:1598`, `:1718`）——把「未知 item / 未知 content part」变成硬失败的那一小段，是 §2.4 fail-closed 的实际执行者，与 1600 行的形状表可以解耦。
2. `_json_type`（`:642-659`）里 `isinstance(value, bool)` 排在 `isinstance(value, int)` 前面，`_matches_types`（`:662-667`）显式处理「JSON Schema 的 number 包含 integer」。Python 里 `True` 是 `int` 这个坑，整个仓库到处都在防（`anthropic_responses.py:984`, `:1503`, `:1559`, `sse/anthropic_responses.py:226`）。

权重：整块 `不适用`；两个零件 `强到可直接采纳`。

---

## 4. 严格 JSON 解析：实现在哪、怎么做的、代价多大

分三层，职责不重叠。

### 4.1 第一层：全局嵌套深度守卫（`json_guard.py`，84 行）

`app.py:74-108` 注册了一个 `before_request` 钩子，对**所有** endpoint 生效：

```python
if not request.is_json:
    return None
if not exceeds_max_nesting(request.get_data(cache=True)):
    return None
```

docstring（`app.py:75-87`）交代了动机：`request.get_json()` 在足够深的 body 上抛 `RecursionError`，而 `silent=True` **不会**捕获它（那不是 parse error）；下游的 `copy.deepcopy` 和 `json.dumps` 更早就崩。所以几 KB 的 `[[[[...` 会变成 500。钩子跑在 auth gate 之后（`:85-86`），免得未认证客户端白嫖这次扫描。

`exceeds_max_nesting`（`json_guard.py:41-84`）的实现值得细看，它显式拒绝了两种更直觉的写法：

- **不靠 `RecursionError`**：CPython 的 C 加速 scanner 到约 10k 层才抛，而下游 `copy.deepcopy` 约 500 层就死（`json_guard.py:3-10`）。限值定在 `MAX_JSON_NESTING_DEPTH = 100`（`:29`），注释说「Orders of magnitude above any real request (tool JSON Schemas nest a dozen levels at most)」。
- **不用正则匹配字符串字面量**（`:16-22`）：

```python
# That rules out matching string literals with a regex: every ``"`` that
# opens an unterminated literal costs a full-length failed match, and
# re-scanning from the next byte makes the whole thing quadratic.
```

实现是用 `re.compile(rb'["\[\]{}]')` 只找结构字节（`:34`），非结构字节（含所有多字节 UTF-8 续字节）由 C 层跳过；转义引号靠**向左数反斜杠个数的奇偶**判断（`:69-74`），并附上了线性性论证：「Each run of backslashes is consumed by at most one quote, so the walk back stays linear over the whole body.」

未闭合字符串的处理也给了正确性论证（`:48-52`）：之后的一切看起来都像字符串内容，深度停止增长——这是**安全的**（不只是可容忍），因为解码器从左往右读，只可能递归进未闭合字面量**之前**开的那些容器，而那些已经数过了。

**代价**：一次 `finditer` 扫全 body，只在结构字节上做 Python 层工作。对典型请求体，结构字节占比很低。`tests/test_json_nesting_guard.py` 有 231 行专门测这个。

### 4.2 第二层：严格解析（`parse_strict_json_bytes`，`anthropic_responses.py:68-124`）

入口在 `routes/anthropic.py:977-983`：

```python
# Capture the exact wire body before Flask normalises JSON. Duplicate keys,
# non-finite numbers, invalid UTF-8 and trailing data are ambiguous and are
# rejected rather than silently changed by a permissive parser.
original_request_raw = request.get_data(cache=True)
anthropic_payload = parse_strict_json_bytes(original_request_raw)
```

拒绝清单与实现手段：

| 拒绝的东西 | 手段 | 行号 |
|---|---|---|
| 过深嵌套 | 先调 `_reject_deep_nesting` | `:70` |
| 非 UTF-8 | `raw.decode("utf-8", errors="strict")`，报告出错字节偏移 | `:71-74` |
| `NaN` / `Infinity` / `-Infinity` | `parse_constant=reject_constant` | `:76-77, 89` |
| 重复键 | `object_pairs_hook=unique_object` | `:79-85, 88` |
| 尾随数据 | `decoder.raw_decode(text)` 后检查 `text[end:].strip()` | `:92, 100-101` |
| 落网的非有限浮点 | 解析后迭代遍历再查一次 `math.isfinite` | `:105-109` |
| 未配对代理项 | 遍历时对每个 str 做 `encode("utf-8", errors="strict")` | `:110-116` |
| `RecursionError` | 兜底捕获转成 `StrictJSONError`，注释标注 "Defence in depth" | `:95-97` |

后置遍历用**显式栈而非递归**（`:104-106`）：「Walk iteratively so the validation boundary cannot itself overflow the Python stack after the decoder accepted a deeply nested document.」路径追踪用 `$.<key>` / `$[i]` 形式，报错能指出具体位置。

**关键点**：用 `raw_decode` 而不是 `json.loads`，才能把「尾随数据」和「合法 JSON 后面跟垃圾」区分开——`json.loads` 只会给一个笼统的 `Extra data` 错误位置。

### 4.3 第三层：把严格解析用在两个非请求体的地方

这是最容易被漏掉、但价值最高的两处：

1. **上游 SSE 每一帧**（`sse/anthropic_responses.py:1133-1137`）：覆写 `parse_event_data`，把基类的 `json.loads`（`base.py:157-158`）换成 `parse_strict_json_bytes`。解析失败走 `forward_malformed_data`（`:1139-1155`），**不透传畸形载荷**，改吐一个 Anthropic 形状的 error 事件并把整条流标成 502：「Never leak a foreign/malformed Responses payload into an Anthropic stream. The raw bytes are still retained by the base cache handler.」
2. **上游返回的 function call arguments 字符串**（`_strict_function_arguments`，`anthropic_responses.py:1669-1699`；流式对应 `sse/anthropic_responses.py:580-593`）。docstring 说明了 stake：

```python
"""Decode a Responses function argument string as one strict JSON object.

Sending a scalar, array, malformed JSON, or an object with duplicate keys
as an Anthropic ``tool_use.input`` can make the CLI execute a call with a
different contract.  This is therefore a fail-closed boundary in both
compatibility modes, not a best-effort projection.
"""
```

测试 `test_function_arguments_fail_closed_unless_strict_json_object`（`tests/test_sse_anthropic_responses.py:299-319`）遍历 `"[]"`, `"1"`, `"null"`, `"not-json"`, `'{"x":1,"x":2}'` 五个样本，断言每个都出 error、都不产生 `content_block_start`、都不产生 `message_stop`。最后那个重复键样本正是严格解析在这里的**唯一**理由——普通 `json.loads` 会静默取后者。

**代价评估**：

- 实现代价：`json_guard.py` 84 行 + `parse_strict_json_bytes` 57 行 = 约 141 行，无第三方依赖。
- 运行时代价：请求体被扫描两遍（一次结构字节 finditer，一次解析后的全叶子遍历），加上 `raw_decode`。对 Claude Code 那种几百 KB 的请求体这是可感知但很小的开销；真正的问题是**它跟 `ConversionReport.finalize()` 的全叶子遍历是第三遍**。
- 兼容性代价：**这是真实存在的**。拒绝重复键会拒掉某些客户端；拒绝 `NaN` 会拒掉某些 Python 侧 `json.dumps(allow_nan=True)` 生成的 body。ghc-api 接受这个代价，理由写在 `routes/anthropic.py:974-976`：这些形状是**歧义的**，与其让宽容解析器悄悄改语义，不如 400。

权重：第一层与第三层 `强到可直接采纳`（尤其是把严格解析用在 function arguments 上——那是真正的安全边界）；第二层里「拒绝重复键 / 尾随数据」`是个倾向、需更多样本`（收益依赖我方是否真的遇到过歧义体，代价是可能拒掉合法客户端）。

---

## 5. 阅读中发现的具体细节

本节所有「实测」条目由一个只读探针得出：把 `json_guard.py` / `reasoning_carrier.py` / `anthropic_responses.py` 三个纯模块（不依赖 Flask，模块 docstring `anthropic_responses.py:1-8` 明说）按 sha256 校验后复制到 `/tmp/ghcprobe/ghc_pure/`，Python 3.14.7 直接调用。探针本身做了正样本对照（先证明它能观察到「深嵌套被拒」这个已知行为，再读其余数字）。**未修改被调研仓库的任何文件。**

### 5.1 它做对了、而一般实现会做错的

**（1）用 `output_index` 而不是 item id 做跨事件身份，并把「id 稳不稳」升格成 profile 能力位。** 见 §2.2，此处不重复。这是本次调研最重要的单条发现。

**（2）fail-open / fail-closed 的判据是「可恢复性」而不是「未知性」。** 未知 SSE 事件跳过（终局事件会重放完整 output 数组），未知 item / content part 硬失败（没有任何后续事件会以已知形状重述它），未知非流式 `response.status` 硬失败（它就是终局答案本身）。三处判断分别在 `sse/anthropic_responses.py:1077-1092`、`compat_profiles.py:1521-1534`、`routes/anthropic.py:1936-1946`，且每处都写了理由。一般实现会一刀切（要么全部宽容、要么全部拒绝）。

**（3）「字段缺席」与「字段存在但为空」被区别对待。** `anthropic_responses.py:1048-1057`：Anthropic 工具没有 `description` 是合法的，转换后也必须保持没有；`description: ""` 才替换成 `f"Tool: {name}."`。测试 `test_tool_description_is_never_forwarded_as_an_empty_string`（`tests/test_anthropic_responses_translation.py:579-614`）三个分支都钉住了，还断言合法无描述工具**不产生任何 warning**。一般实现会无条件 `tool.get("description", "")` 或无条件补默认值。

**（4）孤儿 tool_result 与孤儿 tool_use 的处理方向相反。** `anthropic_responses.py:677-694`。判据是「上游会不会硬失败」和「补偿会不会编造内容」，不是对称性。

**（5）`isinstance(value, bool)` 一律排在 `isinstance(value, int)` 之前。** `compat_profiles.py:647-650`、`anthropic_responses.py:984`（`max_uses`）、`:1503`（token 计数）、`:1559`（`num_requests`）、`sse/anthropic_responses.py:226`（`content_index`）。Python 里 `True` 是 `int` 的子类，这个坑在协议校验代码里几乎必然被踩到一次。

**（6）流式 stop 匹配永远保留 `max_length - 1` 个字符。** `sse/anthropic_responses.py:76-82`。一般实现会逐 chunk 独立匹配，于是 `"before<ST"` + `"OP>after"` 这种跨 chunk 的 stop 会漏掉，而且**前缀已经吐给客户端了**。测试 `:16` 与 `:709` 各钉一半。

**（7）给「算法应该保证的不变量」配显式断言。** `sse/anthropic_responses.py:391-394`：

```python
if self.open_output_index is not None and self.open_output_index != state.output_index:
    # The drain algorithm should make this impossible. Treat it as a
    # protocol error rather than reopening a closed Anthropic index.
    return self._protocol_error("responses.interleaved_open_block", f"/output/{state.output_index}")
```

**（8）重试时重新构造 headers，而不是复用同一个 dict。** `routes/anthropic.py:1685-1696` 的 docstring 把两个真实故障都写出来了：复用 dict 会在 token 刷新后重发旧 token（把可恢复重试变成 401），并且会在多次尝试里重复同一个 `X-Request-Id`（破坏上游关联与去重）。

**（9）`request_size` 量的是客户端发来的原始字节，不是转换产物。** `routes/anthropic.py:1662-1669` 的注释解释了为什么：缓存用 `request_size` 决定要不要丢弃 body，而转换可以把 body 缩小几个数量级（未知顶层键、thinking 块记账后就不上行了），量错就会让 1 MB 的 body 在「219 字节」的账下被完整保留。**量对了尺寸，截断策略才有意义。**

**（10）终局语义只有一份实现，流式与非流式共用。** `sse/anthropic_responses.py:716-725` 在流式路径上直接调用 `convert_responses_to_anthropic({"type": terminal_event_type, "response": response}, ...)` 来算 `stop_reason` / `stop_sequence` / `usage`，`_response_object`（`anthropic_responses.py:1663-1666`）负责拆信封。一般实现会在流式里另写一套 stop_reason 推断，然后两套慢慢分叉。

**（11）Anthropic 流不发 `data: [DONE]`。** `sse/base.py:67-71` 把这做成了基类开关，`sse/anthropic_responses.py:1106` 设为 `False`，注释说明 Anthropic 用 `message_stop` 收尾、逐行按 Anthropic JSON 解析的客户端会被裸 `[DONE]` 噎住。同理 `keepalive_event` 被覆写成 `event: ping`（`:1130-1131`）而不是基类的 SSE 注释行。这是复用 OpenAI SSE 管道时最经典的一类漏改。

**（12）reasoning 出现在可见输出之后是致命错误。** `anthropic_responses.py:1743-1754` 与 `sse/anthropic_responses.py:483-487`。因为 Anthropic 要求 thinking 块必须在前，事后无法补救，所以宁可 502 也不产出一个客户端会拒绝的消息。

### 5.2 它做错了或做得笨重的（我方不要照抄）

**（A）缓存里的上游原始事件被脱敏成了哈希，故障现场恰恰在漂移时消失。**

`sse/anthropic_responses.py:1157-1172` 覆写 `raw_events_for_cache`，每条事件先 `audit_responses_event`，然后 `redact_responses_event_for_cache`。而 `compat_redaction.py:97-103`：

```python
audit = audit_responses_event(event)
if audit.warnings:
    result = redacted_value(event, "unknown, invalid, or drifted Responses event")
```

`audit.warnings` **包括所有 `action == "warn"` 的告警**，比如「上游多了一个我不认识的字段」。也就是说：上游一旦发生任何加性漂移，整条事件在缓存里就只剩 `{_redacted: true, _size: N, _sha256: ...}`。**你最需要原始报文的那一刻，正是它被替换成哈希的那一刻。**

更糟的是 `forward_malformed_data` 的注释（`sse/anthropic_responses.py:1140-1141`）写着「The raw bytes are still retained by the base cache handler」——**这句是错的**。基类的 `raw_events_for_cache`（`base.py:176-179`）确实返回原文，但子类覆写了它；`_complete_cache`（`base.py:225`）用的是覆写后的版本，畸形 payload 落进缓存时已经是 `redacted_value(raw, "malformed Responses event")`，即一个哈希。原文只活在进程内的 `self.raw_events` 列表里，请求结束即消失（我 grep 过 `raw_events` 的全部消费者，`cache.py` 与 `routes/dashboard.py` 拿到的都是覆写后的投影）。

按我方立场（`no-imagined-security-theater`、`richest-context-flow`，以及项目记忆里「完整日志与请求记录不因为含有临时凭据就是敏感的」），这整层脱敏都不适用。

权重：`强到可直接采纳`（作为反面教材）。依据：两处调用点我都读了，`raw_events` 的消费者我 grep 全了。

**（B）审计报告本身没有体积上限，而请求体有。** 实测（探针，Python 3.14.7）：

| 形状 | 请求体 | 嵌套守卫 | 严格解析 | 转换+记账 | `report.to_dict()` | records 数 | 报告 JSON 体积 |
|---|---|---|---|---|---|---|---|
| 50 条消息 × 800 字符 | 42 KiB | 0.4 ms | 0.8 ms | 0.9 ms | 0.1 ms | 176 | 18 KiB |
| 400 条 × 800 | 337 KiB | 4.0 ms | 6.9 ms | 5.8 ms | 0.7 ms | 1401 | 147 KiB |
| 1600 条 × 800 | 1349 KiB | 15.3 ms | 27.7 ms | 23.2 ms | 3.3 ms | 5601 | **594 KiB** |
| 1600 条 × 3200 | 5099 KiB | 27.4 ms | 51.3 ms | 27.6 ms | 1.2 ms | 5601 | **594 KiB** |

两点读数：

1. **CPU 成本可接受**：1.3 MiB 请求上三层合计约 66 ms 纯 CPU，相对上游动辄数秒的延迟可以忽略。报告体积只跟**叶子数**走，跟字节数无关（第 3、4 行 records 与报告体积完全相同）。
2. **内存成本是真问题**：一个 1.3 MiB 的请求留下 594 KiB 的审计报告，约为请求体的 44%。而 `cache._truncate_oversize_bodies`（`cache.py:58-74`）只截断 `request_body` / `original_request_body` / `response_body` / `raw_events`——**`conversion_report` 不在名单里**。于是超限请求的 body 被换成占位符之后，那份 594 KiB 的报告仍然完整躺在内存缓存里。这与 `:1662-1668` 那段「量对尺寸才能正确截断」的细致注释形成了讽刺性的对照。

他们已经为这套机制付过一次性能账：`tests/test_anthropic_responses_translation.py:652-654` 写着「The previous list-scan de-duplication took ~10 seconds for this shape」，即最初的去重是列表线性扫描、在这个形状上跑了 10 秒，后来才改成 `_seen_records` 集合。

权重：`强到可直接采纳`（数字是我实测的；截断名单是我读的代码）。

**（C）审计报告里的 `target_path` 会失真，而它看起来像权威记录。** 实测：

```
input item types: ['additional_tools', 'message', 'message']
record /system -> {'source_path': '/system', 'disposition': 'exact', 'target_path': '/input/0/content/0/text'}
actual system text at /input/1/content/0/text = 'SYSTEM PROMPT'
```

原因是 `_convert_system` 先 append 了 developer message 并按当时的下标记账（`anthropic_responses.py:795-796`），随后工具转换用 `input_items.insert(0, {"type": "additional_tools", ...})`（`:1198`）把所有下标顶了一位。代码自己承认了（`:1199-1200`：「Existing target paths in records are descriptive only」），但报告是要给人读、要进缓存、要当审计线索的，「descriptive only」不是一个读者能从字段名里读出来的限定。

权重：`强到可直接采纳`（实测复现）。

**（D）记账机制存在一个「记了但没做」的洞：未知 `thinking.type` 被静默丢弃，且报告声称已映射。** 实测：

```
输入 thinking = {"type": "future_unknown_mode"}
reasoning in payload: None
record: {'source_path': '/thinking/type', 'disposition': 'semantic_encoding', 'target_path': '/reasoning/effort'}
warnings: []
```

代码路径：`_map_reasoning_effort`（`:838-841`）在确认 `thinking` 是 dict 之后**无条件**打上 `report.mark("/thinking/type", PRESERVATION_SEMANTIC, "/reasoning/effort")`，然后三个已知分支都没命中，落到 `:866` 的 `return None`。于是叶子被「记账」了（不会进 `unaccounted_paths`），处置是 `semantic_encoding`（不产生 warning），但实际上什么也没发生。

**这正是这套机制存在的理由所要防的那种失败**——一个未来的 Anthropic thinking 模式会被无声吞掉，而审计线索说它被映射了。**教训对我方直接适用：先记账、后判断成败的顺序是错的；记账必须发生在知道结果之后，或者失败时必须回改处置。**

权重：`强到可直接采纳`（实测复现，且逻辑路径我逐行读过）。

**（E）传输适配器伸手调状态机的私有方法。** `sse/anthropic_responses.py:1142`（`self.translator._warn(...)`）、`:1177` 与 `:1190`（`self.translator._protocol_error(...)`）。分层做得很干净，然后在三处捅穿了。这说明状态机缺一个公开的「外部注入协议错误」入口。

**（F）`copilot_public_responses` 的两个 profile 位看起来自相矛盾。** 实测：

```
public_responses           stable_ids=True  preserves_reasoning_item_ids=True
copilot_public_responses   stable_ids=False preserves_reasoning_item_ids=True
copilot_responses_lite     stable_ids=False preserves_reasoning_item_ids=False
```

中间那行：一边声明「这个上游的 id 每帧重新加密，不能用作身份键」（`anthropic_responses.py:305-308`），一边又在 reasoning 载体里回填 `item.get("id")`（`:1767-1771`、`sse:514-518`）并在下一轮请求里发回去（`:756-757`）。回填一个自己刚宣布无意义的 id，至少是可疑的。我没有 Copilot 对 Grok reasoning item 的真实行为样本，无法判定这是 bug 还是「这个 id 对上游有意义、只是对我们不可比」。

权重：`是个倾向、需更多样本`。依据：两个字段的组合是我实测确认的，但「这是不是错的」需要上游 cassette 才能判。**我方若采纳 profile 抽象，应把这两个语义拆清楚：「我能不能拿它做跨事件比较」与「我能不能把它发回上游」是两件事。**

**（G）核心词汇已经漂移，但名字没跟着改。** `PRESERVATION_SIDECAR` 的 docstring（`:180-183`）：「``sidecar`` is a historical disposition name meaning that a source field is not represented on the client wire」。一个五档分类里有一档需要靠注释说明「这个名字是历史遗留、现在含义不同」，是明确的命名债。我方若采纳这套分类，改名成本几乎为零，现在改。

**（H）`routes/anthropic.py` 2622 行，其中大量近乎逐字重复的失败落缓存调用。** `_cache_responses_local_failure(...)` 的 15~20 行参数块在 `:1588`、`:1623`、`:1642`、`:1947`、`:2057` 等处反复出现，差别只有 `message` / `status_code` / 多一两个可选参数。这是「每条失败路径都要完整落一次审计记录」这个正确目标的笨重实现方式，我方应该用一个上下文对象或装饰器承担。

**（I）warning 去重仍是列表线性扫描。** `anthropic_responses.py:227`（`if warning not in self.warnings`）与 `sse/anthropic_responses.py:385`（`if warning not in self.compatibility_warnings`）。他们已经把 `records` 的去重改成集合（并留下了 10 秒的教训注释），却漏了 warnings。实践中 warning 的**不同形状**数量有界，所以影响小；但这是同一个错误的残留，值得作为「修一处要搜同类」的例子记住。

**（J）Claude Code 工具契约哈希基线是一条维护跑步机。** `compat_profiles.py:35-98` 硬编码了 29 个内置工具 × 2 个 CLI 版本的 sha256。`KNOWN_CLAUDE_CLI_VERSIONS` 只有 `2.1.197` 和 `2.1.207`（`:28`），任何其他版本都会稳定产出一条 `claude_cli.unknown_version`（`:1447-1454`）。客户端每次升级都要人肉重采。我方不应照抄。

---

## 6. 结论表：我方是否值得借鉴

「我方是否已实现」我一律不猜，标为「需主会话核对」。

| # | 发现 | 位置 | 权重档 | 值得借鉴？ | 理由 |
|---|---|---|---|---|---|
| 1 | 用 `output_index` 而非 item id 做跨事件身份 | `sse/anthropic_responses.py:93-112, 207-217, 271-381` | 强到可直接采纳 | **值得**（需主会话核对是否已实现） | 直接对症我方已知的上游 id 不稳缺陷；代码/注释/测试三处互证 |
| 2 | `stable_ids` 作为 profile 能力位门控所有 id 比较 | `anthropic_responses.py:283-285, 320, 339`；门控点 `sse:288, 662, 757, 790, 825` | 强到可直接采纳 | **值得** | 保留了在稳定上游上继续校验的能力，不是一刀切放弃 |
| 3 | fail-open/closed 按「可恢复性」判定 | `sse:1077-1092`、`compat_profiles.py:1521-1534`、`routes/anthropic.py:1936-1946` | 强到可直接采纳 | **值得** | 判据独立于具体上游；README 的描述与代码一致，已核实 |
| 4 | 未知 output item / content part → 502 fail closed | 同上 | 强到可直接采纳 | **值得**（需主会话核对） | 我方块级交付下同样成立：无法表示的东西不能半吐 |
| 5 | 严格 JSON 用于上游 function arguments | `anthropic_responses.py:1669-1699`、`sse:580-593` | 强到可直接采纳 | **值得** | 重复键会让 CLI 按不同契约执行工具，这是真实的正确性边界而非防护戏 |
| 6 | 全叶子记账 `ConversionReport` | `anthropic_responses.py:155-265` | 强到可直接采纳（机制）；成本见 #17 | **存疑** | 收益（新字段不会静默丢失）真实且大；成本（594 KiB/1.3 MiB 请求、无截断、见 #17/#18 两个洞）也真实。建议先做一个「只记 approximation/unsupported + unaccounted_paths」的轻量版 |
| 7 | 「记账在判断成败之前」导致的静默丢弃洞 | `anthropic_responses.py:838-841, 866` | 强到可直接采纳 | **值得**（作为反面教材） | 若采纳 #6，必须先修正记账顺序，否则机制在最该生效处失效 |
| 8 | 孤儿 `tool_result` 本地丢弃、孤儿 `tool_use` 保留 | `anthropic_responses.py:677-694` | 强到可直接采纳 | **值得**（需主会话核对） | 避免一次必然失败的上游往返；两个方向的非对称处理有明确理由 |
| 9 | 工具 `description`：缺席 ≠ 空串 | `anthropic_responses.py:1048-1057` | 强到可直接采纳 | **值得**（需主会话核对） | 上游确实拒空 description；有三分支测试 |
| 10 | `IdentifierCodec` 请求作用域内保持单射 | `anthropic_responses.py:354-408` | 强到可直接采纳 | **值得**（需主会话核对） | 客户端可以构造出与哈希产物相同的合法名字；不防会导致两个工具别名 |
| 11 | `StopSequenceScanner` 保留 `max_length-1` | `sse:45-90` | 强到可直接采纳 | **存疑** | 技术本身正确。但我方是块级交付：整块拿到后一次性匹配即可，不需要跨 chunk 扫描器。若我方 stop 处理在块内做，此条 **不适用** |
| 12 | 终局语义流式/非流式共用一份实现 | `sse:716-725`、`anthropic_responses.py:1663-1666` | 强到可直接采纳 | **值得** | 防止两条路径的 stop_reason/usage 推断慢慢分叉 |
| 13 | Anthropic 流不发 `[DONE]`、keepalive 用 `ping` | `sse/base.py:67-71`、`sse:1106, 1130-1131` | 强到可直接采纳 | **值得**（需主会话核对） | 复用 OpenAI SSE 管道时最经典的漏改 |
| 14 | 重试时重建 headers 而非复用 dict | `routes/anthropic.py:1685-1696` | 强到可直接采纳 | **值得**（需主会话核对） | 复用会重发刷新前的 token 并重复 X-Request-Id |
| 15 | `request_size` 量原始上行字节 | `routes/anthropic.py:1662-1669` | 强到可直接采纳 | **值得** | 量错尺寸会让截断策略整体失效 |
| 16 | 兼容告警：头只放 code 索引、缓存放权威、日志限流而计数不限流 | `routes/anthropic.py:117-182` | 强到可直接采纳 | **值得** | 三者分工清晰，可独立于 #6 采纳 |
| 17 | 审计报告体积无上限、不参与缓存截断 | `cache.py:58-74`；实测 594 KiB | 强到可直接采纳 | **值得**（作为必修项） | 若采纳 #6，报告必须进截断名单 |
| 18 | 报告 `target_path` 在 `insert(0)` 后失真 | `anthropic_responses.py:795-796, 1198`；实测复现 | 强到可直接采纳 | **值得**（作为反面教材） | 审计线索失真比没有审计线索更危险 |
| 19 | 嵌套深度守卫（结构字节线性扫描，不靠 RecursionError） | `json_guard.py` 全文、`app.py:74-108` | 强到可直接采纳 | **值得** | 84 行、无依赖；防的是 `deepcopy`/`dumps` 在 ~500 层就崩这个真实故障，不是想象出来的威胁 |
| 20 | 严格解析拒绝重复键/NaN/尾随数据 | `anthropic_responses.py:68-124` | 是个倾向、需更多样本 | **存疑** | 正确性收益真实，但会拒掉部分合法客户端。建议先在我方 cassette 上统计是否真出现过歧义体 |
| 21 | reasoning 载体：畸形降级、profile/model 不匹配保 summary 丢密文、跨路径剥离 | `reasoning_carrier.py:78-138, 160-206`、`anthropic_responses.py:708-767` | 强到可直接采纳 | **值得**（需主会话核对） | 三条策略与具体编码格式无关，可直接套用到我方自有载体 |
| 22 | 载体编码格式本身（`ghc-api:responses-reasoning:v1:` + base64url canonical JSON） | `reasoning_carrier.py:22-71` | 仅存档 | **不适用** | 我方已有自有版本化载体；格式互不兼容无所谓 |
| 23 | `ResponsesWireProfile` 能力矩阵抽象 | `anthropic_responses.py:268-348` | 强到可直接采纳（三条规则） | **值得** | 采纳的是规则：能力位由录制证据决定、未证明取保守值、能力位要能影响流式不变量强弱、profile 名进载体。12 个具体字段值仅存档 |
| 24 | `copilot_public_responses` 的 `stable_ids=False` + `preserves_reasoning_item_ids=True` | 实测确认 | 是个倾向、需更多样本 | **存疑** | 我方若采纳 #23，应把「能不能做跨事件比较」与「能不能发回上游」拆成两个位 |
| 25 | `CompatibilityProfile` 客户端漂移审计（1600+ 行形状表） | `compat_profiles.py` 主体 | 仅存档 | **不适用** | 解决的是运维可观测性而非转换正确性；按我方 `build-proof-infrastructure-only-if-requested` 属于额外证明基础设施 |
| 26 | Claude Code 内置工具契约哈希基线 | `compat_profiles.py:35-98` | 仅存档 | **不适用** | 维护跑步机；每次客户端升级都要人肉重采 |
| 27 | 上游原始事件在缓存里被脱敏成哈希 | `compat_redaction.py:97-103`、`sse:1157-1172` | 强到可直接采纳（作为反面教材） | **不适用** | 与我方 `no-imagined-security-theater` / `richest-context-flow` 直接冲突；且漂移时恰好销毁现场。附带发现：`sse:1140-1141` 那句「raw bytes are still retained」是错的 |
| 28 | `isinstance(bool)` 先于 `isinstance(int)` | `compat_profiles.py:647-650` 等五处 | 强到可直接采纳 | **值得** | 协议校验代码里的必踩坑 |
| 29 | 给「算法应保证的不变量」配显式断言 | `sse:391-394` | 强到可直接采纳 | **值得** | 低成本、高价值 |
| 30 | 传输适配器调状态机私有方法 | `sse:1142, 1177, 1190` | 强到可直接采纳 | **不适用**（避免） | 分层做干净了又捅穿；应给状态机一个公开的错误注入入口 |
| 31 | `PRESERVATION_SIDECAR` 命名已漂移 | `anthropic_responses.py:180-183` | 强到可直接采纳 | **值得**（作为反面教材） | 若采纳 #6，趁现在改名，成本为零 |
| 32 | 失败落缓存的调用块大面积重复 | `routes/anthropic.py:1588, 1623, 1642, 1947, 2057` | 是个倾向、需更多样本 | **不适用**（避免） | 目标对、实现笨重；用上下文对象承担 |
| 33 | warning 去重仍是列表线性扫描 | `anthropic_responses.py:227`、`sse:385` | 仅存档 | **不适用** | 实践影响小；价值在于「修一处要搜同类」这个教训 |

### 需主会话决策的两个点

1. **要不要引入全叶子记账（#6）**。这是本次调研里唯一一个「结构性大件」。我的主观倾向：**引入一个轻量版**——保留「未登记叶子自动成为 unsupported 告警」这个核心收益与 `unaccounted_paths`，但不保留每个叶子一条 `exact` 记录（那是 594 KiB 的来源，且信息量最低）。同时必须先修 #7（记账顺序）和 #17（进截断名单），否则机制在最该生效处失效。
2. **`stop_sequences` 的执行位置（#11）**。ghc-api 不把 stop 发给上游、在代理侧截断，代价是上游照常生成并计费。我方是块级交付，在块内匹配更简单，但「要不要发给上游」这个决策与它无关，需要单独裁决。

---

## 附录：实测探针的可复现说明

本报告中所有标「实测」的数字与输出由以下步骤产生，**不修改被调研仓库**：

```bash
SRC=/home/xp/.claude/jobs/89874ec2/tmp/ghc-api/ghc_api
DST=/tmp/ghcprobe/ghc_pure
rm -rf /tmp/ghcprobe && mkdir -p "$DST"
: > "$DST/__init__.py"
cp "$SRC/json_guard.py" "$SRC/reasoning_carrier.py" "$SRC/anthropic_responses.py" "$DST/"
# 逐个 sha256sum 比对副本与原文件，不一致则中止
```

为什么要复制：`ghc_api/__init__.py:5` 会 `from .app import create_app`，而 `app.py` 依赖 Flask（本机未安装）。`anthropic_responses.py` 自身不依赖 Flask（模块 docstring 明说），只用相对导入引 `json_guard` 与 `reasoning_carrier`，所以给它一个只含这三个文件的最小包即可原样运行。

三份副本的 sha256（对应 HEAD `0cb1087`）：

- `json_guard.py` — `aaa3ff1632486efd769fa6d242807b9724dd33a78cd361907139aef0b3f66b69`
- `reasoning_carrier.py` — `647c75e4754d582b1fa3d8df6a0e457f444eced5a06987de159d78af987ab4ba`
- `anthropic_responses.py` — `d3cc118bbd779a1f31cb91109c8d54bce31bcb9736da53607acef60a82a49ebf`

探针脚本：`/tmp/ghcprobe/probe.py`（性能与报告体积）、`probe2.py`（`target_path` 失真）、`probe3.py`（未知 `thinking.type`）。运行环境 Python 3.14.7。

`probe.py` 在读任何数字之前先做正样本对照：构造 200 层嵌套的 body，断言 `parse_strict_json_bytes` 抛 `StrictJSONError`；不抛就以退出码 2 中止并打印「探针不可信」。这是为了排除「模块没真正加载 / 加载的是别的东西 / 函数根本没跑」这类形状正确的假数字。对照实际输出：

```
loaded from: /tmp/ghcprobe/ghc_pure/anthropic_responses.py
正样本对照 OK: 深嵌套被拒 -> JSON nesting is too deep: exceeds the maximum of 100 levels
```

`/tmp/ghcprobe/` 可随时删除，报告不依赖它继续存在。

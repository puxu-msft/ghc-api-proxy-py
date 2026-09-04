# 候选：`instructions` 的形态与上游实况冲突

> 本文是候选素材，无效力。需要用户裁决是否修改 `docs/.human-controlled/message-translation.md`。
>
> 触发：2026-08-18 实测 Anthropic→Responses 主干路径时，规格所载的 `instructions` 形态被上游拒绝。
>
> **2026-08-22 重指**：目标文档原名 `model-translation.md`，已更名为 `message-translation.md`（提交 `2afa0c4`）。内容未变，本文所有引用相应重指；第六节的三条测试也已改名并移位，一并更新。

## 一、规格怎么写的

`message-translation.md:34-62` 的「如何提供系统提示词？」一节给出 openai-responses 的形态是**对象数组**，每个对象带 `role` 与 `content`，`content` 内的每个 block 保留 `cache_control`：

```json
{"instructions": [{"role": "system", "content": [{"type": "text", "text": "…", "cache_control": {"type": "ephemeral"}}]}]}
```

同节末句（`message-translation.md:62`）：「可见 `instructions` 具有更丰富的语义，只是目前我们用不到这层灵活性。」

## 二、上游实测

对 `gpt-5.6-terra` 打 GHC 的 `/responses`，其余字段固定为可通过的最小体，只变 `instructions`：

| `instructions` 形态 | 结果 |
|---|---|
| 纯字符串 | **HTTP 200** |
| `[字符串]` | 400 `failed to parse request` |
| `[{role, content: 字符串}]` | 400 |
| `[{role, content: [{type: "text", text}]}]`（**规格形态**） | 400 |
| 同上 ＋ 每 block 带 `cache_control` | 400 |
| `[{role, content: [{type: "input_text", text}]}]` | 400 |
| `[{type: "message", role, content: [{type: "input_text", text}]}]` | 400 |

**六种数组形态全部被拒，只有字符串可用。** 复现方式：构造上表各体，经 `GhcApiClient.send_responses` 直发。

## 三、判断

规格描述的是 **OpenAI Responses 这个格式**能表达什么；我们实际对话的是 **GitHub Copilot 对该格式的实现**，后者更窄。两者的字面对象不是同一件事，所以这不是「规格错了」，而是「规格描述的那层灵活性在这条上游上不存在」。

规格自己那句「目前我们用不到这层灵活性」也指向字符串。

## 四、代价（实测后已大幅缩小）

塌缩成字符串会丢掉 system block 上的 `cache_control` marker。我起初判断这等于在 Responses 路径上失去 prompt caching——**实测证明这个判断是错的**。

对 `gpt-5.6-terra` 发同一个 24082 token 的请求两次，`instructions` 为纯字符串、不带任何缓存字段：

| | `input_tokens` | `cached_tokens` |
|---|---:|---:|
| 第 1 次（前缀是冷的） | 24082 | **0** |
| 第 2 次（同前缀） | 24082 | **24079** |

**GHC 的 Responses 端点做自动前缀缓存**，不需要显式 breakpoint。第一次 `cached=0` 证明前缀确实冷，第二次几乎全部命中。

补充实测：
- 把 Anthropic 的 `cache_control` 原样放进 `input[].content[]` → **400** `Unknown parameter: 'input[0].content[0].cache_control'`。
- Responses 自己的显式机制是 `prompt_cache_breakpoint: {mode: "explicit"}`，放在 `input[].content[]` 上，GHC **接受**（200）。但按上表，不用它也已经命中。
- `prompt_cache_key` 是顶层的路由/亲和性提示，不写缓存条目、不规定 block 边界或 TTL，**不是 `cache_control` 的同义物**。

**结论**：丢的是 marker，不是缓存。仍记入 `Conversion.losses`（字段确实没了，不该静默），但它不构成性能回退。

**仍未验证的一点**：Anthropic 的 `cache_control` 可带 `ttl`（如 `"1h"`）。今天的真实流量里 `ttl` 出现 **0 次**（1263 个 `cache_control` 全是裸的 `{"type":"ephemeral"}`），所以这条今天不触发；若将来客户端开始发 `ttl`，Responses 侧的对应物是 `prompt_cache_options.ttl` / `prompt_cache_retention`，需要另行映射。

### 旁证：既有服务的做法相同

`copilot-api-js` 对 `gpt` 走的**也是** Anthropic→Responses（`src/lib/codec/openai-responses/openai-responses-cell.ts:12-21,109-124`），它发往上游的 `instructions` **也是字符串、也是 `"\n\n"` join**，`cache_control` 同样丢在翻译边界——其活跃 history 里 `payload:0` 有 breakpoint、最终 `upstream-request` 的 body 无任何缓存字段。它的 cache 处理只在 Anthropic 原生腿上（`src/lib/anthropic/request-preparation.ts:992-1045`）。

## 五、待裁决

1. 确认把 `message-translation.md:34-62` 的 `instructions` 形态改为字符串（并注明原数组形态是该格式的通用能力、GHC 不支持）。**这一条 2026-08-22 复核后仍然打开**：该节至今是对象数组，`:62` 末句也仍是「只是目前我们用不到这层灵活性」。
2. ~~确认接受 Responses 路径上 system 侧 prompt caching 的损失~~ —— **本项已由第四节的实测解除**：缓存并未损失。若你仍希望显式表达缓存边界（例如将来客户端开始发 `ttl`），可再裁决是否把 system 改走 `input` + `prompt_cache_breakpoint`；按当前证据它不是必需的。

## 六、连带受影响的既有测试

**2026-08-22 更新引用。** 这三条测试已随目录重排移到 `tests/unit/pipeline/translation_driver/test_translation_driver.py`，前两条也已改名（原名保留在此，以便回查）：

| 现名与位置 | 原名 | 守的是什么 |
|---|---|---|
| `test_system_becomes_a_single_instructions_string`（`:47`） | `test_system_becomes_one_instructions_entry_with_the_system_role` | 断言已由规格的数组形态改为实测的字符串形态；其 docstring `:54` 反向指回本文件，并写明「记录上游做什么，不是偏好」 |
| `test_the_lost_block_metadata_is_named_rather_than_dropped`（`:68`） | `test_per_block_metadata_survives_the_crossing` | 原守「`cache_control` 跨格式保全」，现改守「这个损失被显式记进 `Conversion.losses`」——字符串形态下保全已不可能，能守的是不静默 |
| `test_round_trip_through_the_intermediate_preserves_the_request`（`:145`） | 同名 | 守往返无损；system 现在会被合并成一块，`:167-176` 的注释说明为什么断言写成「合并后的单块」而不是删掉 |

**这三条是 guard，不是过时测试。** 改动依据是本文第二节的实测，最终是否成立取决于第五节的裁决。

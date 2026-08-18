# 候选：`instructions` 的形态与上游实况冲突

> 本文是候选素材，无效力。需要用户裁决是否修改 `docs/.human-controlled/model-translation.md`。
>
> 触发：2026-08-18 实测 Anthropic→Responses 主干路径时，规格所载的 `instructions` 形态被上游拒绝。

## 一、规格怎么写的

`model-translation.md` 的「如何提供系统提示词？」一节给出 openai-responses 的形态是**对象数组**，每个对象带 `role` 与 `content`，`content` 内的每个 block 保留 `cache_control`：

```json
{"instructions": [{"role": "system", "content": [{"type": "text", "text": "…", "cache_control": {"type": "ephemeral"}}]}]}
```

同节末句：「可见 `instructions` 具有更丰富的语义，只是目前我们用不到这层灵活性。」

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

## 四、代价（这是需要你裁决的部分）

塌缩成字符串会**丢掉 system block 的 `cache_control`**，也就是在 Responses 路径上失去系统提示词的 prompt caching。今天的真实流量每条请求带 842 个 system 侧 `cache_control`（全为 `{"type":"ephemeral"}`），量不小。

已实现的处置：`to_openai_responses` 用 `\n\n` 连接各 block 的文本，并把丢弃的 metadata 键记入 `Conversion.losses`，不静默消失。Anthropic 直通路径不受影响，blocks 原样保留。

**未验证的替代路径**：Responses 可能在别处表达缓存意图（例如 `prompt_cache_key`，真实流量的 Responses 侧请求体里出现过该字段）。本轮没有测它是否能替代 `cache_control`。若你认为缓存必须保住，这是下一步该验的方向。

## 五、待裁决

1. 确认把 `model-translation.md` 的 `instructions` 形态改为字符串（并注明原数组形态是该格式的通用能力、GHC 不支持）。
2. 确认接受 Responses 路径上 system 侧 prompt caching 的损失，或要求先验证 `prompt_cache_key` 一类替代。

## 六、连带受影响的既有测试

`tests/unit/test_translation_driver.py` 有三条测试直接依据规格示例编写，本轮按实测改写，原断言与来历保留在各自 docstring 中：

- `test_system_becomes_one_instructions_entry_with_the_system_role` — 守规格的数组形态。
- `test_per_block_metadata_survives_the_crossing` — 守 `cache_control` 跨格式保全。
- `test_round_trip_through_the_intermediate_preserves_the_request` — 守往返无损；system 现在会被合并成一块。

**这三条是 guard，不是过时测试。** 改动依据是本文第二节的实测，最终是否成立取决于第五节的裁决。

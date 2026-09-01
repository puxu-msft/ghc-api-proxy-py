# `hook_fix_responses_request.repair_minted_reasoning_ids` 的配置示例候选

日期：2026-09-01
性质：**候选材料**，供用户自行摘取进 `docs/.human-controlled/config.example.yaml`。我不修改用户亲笔文档。

权威：[`.dev/docs/direct-passthrough/spec.md`](../docs/direct-passthrough/spec.md) §6.5（用户 2026-09-01 裁决：「加，按窄形态 ＋ 显式 opt-in」）。

## 建议摘取的片段

现有示例文件里，`hook_fix_responses_request:` 这一段**已经存在但整段注释掉**（约 596 行），里面是 `rename_call_id_as_fc_id`。建议在同一段内追加：

```yaml
# hook_fix_responses_request:
#   # 从 Chat Completions 格式的`call_xxx` ID 转为 Responses API 的 `fc_xxx`。
#   # Convert Chat Completions `call_xxx` IDs to Responses API `fc_xxx`.
#   rename_call_id_as_fc_id: true
#
#   # 修补 `1fb37cd` 之前由本代理自铸 item ID 而损坏的历史会话。默认 false。
#   # 入站 reasoning item 若同时满足：带 encrypted_content、且 id 逐字等于本代理旧
#   # 版本会铸出的形状（rs_ + uuid4 + _ + 序号），则删掉它的 id，其余字段逐字保留。
#   # 上游把 encrypted_content 与签发时的 item ID 绑定并在回传时校验，而自铸的 ID
#   # 必然对不上——这类会话每轮 400 且不会自愈，因为坏 item 存在客户端的历史里。
#   # 只在你手上有一条 `1fb37cd` 之前建立、又不愿放弃的会话时打开；新会话不需要。
#   #
#   # Repair conversations damaged by item IDs this proxy minted before `1fb37cd`.
#   # Off by default. An inbound reasoning item is repaired only when it carries
#   # `encrypted_content` *and* its id matches exactly the shape the old code emitted
#   # (`rs_` + a uuid4 + `_` + index); its id is dropped and nothing else is touched.
#   # Upstream binds `encrypted_content` to the item id it issued and verifies that
#   # binding, so a minted id can never satisfy it — such a conversation returns 400
#   # every turn and never recovers, because the bad items live in the client's own
#   # history. Turn this on only for a pre-`1fb37cd` conversation worth keeping.
#   repair_minted_reasoning_ids: true
```

## 一并提请注意：这一段目前取消注释就会启动失败

`rename_call_id_as_fc_id` **在 schema 里不存在**，而 `ProxyConfig` 的每个 Section 都是 `extra="forbid"`。所以照抄这段并取消注释，服务会以 `ValidationError: hook_fix_responses_request — rename_call_id_as_fc_id — Extra inputs are not permitted` 拒绝启动。

`repair_minted_reasoning_ids` 已实现，单独取消注释它是可用的。

同样情况的还有旁边的 `hook_fix_responses_sse.fix_stream_ids`——那一段也是未实现的候选。

**这只是陈述现状，不是要求。** 那两个键是不是要实现、示例里要不要保留注释形态，都是用户的事。

# Direct buffered Chat Completions 技术可实施性最终定向复评

日期：2026-09-06

结论：**形成 0 blocker／0 major 共识。** 本轮仅复核上一轮新增的 1 major与2 minor及其相邻文字；三项均已闭合，未发现修订新造的不可实施接口。未变内容不在本轮重审范围。

## 1. 复评快照

- `direct-buffered-chat-completions/design.md` SHA-256：`fed22fcba6fb189696ab4d18eb5ad375e440e3cbea31974addeb9c869eceb35d`。
- `direct-passthrough/spec.md` SHA-256：`716bc36d7cbcd99d0e3bd3c7e515d7000e80227010780dfaa364d8f1173972a2`。
- `error-envelope/spec.md` SHA-256：`71c5331ad7d02493b3addab2e10bc82af8fb2e1d0ff1578caf678b2381df46d8`。
- `xingchen/spec.md` SHA-256：`54e9693d3e83eaf089a711f0630cbf9e486b86ab44deac19118faf1454057873`。

## 2. 定向 findings复核

### NEW-M-01：Response mode不支持误用 `CapabilityMissing`

**状态：closed。**

- `direct-buffered-chat-completions/design.md` §4.1明确新增typed `ResponseModeNotSupported`，并明确不复用更窄的 `CapabilityMissing`。
- `direct-passthrough/spec.md` §9.3 mode矩阵第四行在联网前抛 `ResponseModeNotSupported`，把“endpoint存在但requested response mode不受支持”与“endpoint集合为空”分开。
- `error-envelope/spec.md` §5.1新增独立source row：`CLIENT`／400，携带provider、model、requested mode与available modes，OpenAI code固定为 `unsupported_response_mode`。
- 紧邻 `CapabilityMissing`行仍保留原定义“descriptor endpoint集合为空”，没有被新语义拓宽。

该接口可按现有 `ProviderError`模式实现：新增一个带四项事实的subclass，并在 `_PROVIDER_ROWS`及OpenAI code override处显式分类。它不要求改变 `ModelProvider.send()`、routing descriptor或HTTP edge的基本签名。

### NEW-m-01：`ChatSendPlan`与 `Attempt.payload`双重final payload authority

**状态：closed。**

- `design.md` §4.1明确 `ChatSendPlan`只保存client mode、upstream mode与capability snapshot。
- 同段明确final payload唯一authority为 `Attempt.payload`；pipeline在该mapping应用defaults，provider从它序列化／发送，prepared retry只从它建立新的private copy。
- `direct-passthrough/spec.md` §9.3同步写明 `ChatSendPlan.upstream_stream`只承担mode，`Attempt.payload`保存真正发送的final payload。
- 定向残留扫描未发现 `ChatSendPlan.payload`、`ChatSendPlan.final_payload`或“ChatSendPlan保存最终payload”的旧写法。

该结构与现有 `DirectDriver`已经把final private mapping写入 `Attempt.payload`的生命周期一致，没有引入第二份可独立变异的mapping。

### NEW-m-02：Capability provenance字段名不一致

**状态：closed。**

- `design.md` §4.1将Python字段统一命名为 `ChatEndpointCapabilities.provenance`。
- `xingchen/spec.md` descriptor pseudo shape统一写作 `chat.provenance`。
- 定向残留扫描未发现 `capability_provenance`或 `chat.capability_provenance`旧写法。

`chat.provenance`是descriptor内嵌Chat capability的路径表达，与结构体成员 `provenance`一致，不再构成两套字段名。

## 3. 相邻文字一致性

- `stream_options_include_usage_default`与 `tool_stream_default`现在收窄为 `Literal[True] | None`，与Spec“只有缺席时补true，显式client值优先”一致；不会再容纳语义未定义的false capability default。
- `ResponseModeNotSupported`只覆盖“selected Chat endpoint存在、但requested mode不支持且无合法反向adapter”，不与 `EndpointNotSupported`或 `CapabilityMissing`重叠。
- Prepared retry仍以 `Attempt.payload`为source建立private copy，不改变single-attempt collector／two retry owners的既有结论。
- Xingchen继续只签名provider收到的最终bytes；provenance命名修订不影响签名、catalog generation或route snapshot。

## 4. 否决建议

1. **继续否决把 `ResponseModeNotSupported`并回 `CapabilityMissing`或 `EndpointNotSupported`。** 三者分别表示mode缺失、endpoint事实全空、指定endpoint不支持，客户端与operator下一步不同。
2. **继续否决在 `ChatSendPlan`重新加入payload mapping。** Mode plan与attempt final payload分槽是prepared retry保持单一事实源的前提。
3. **继续否决恢复 `capability_provenance`别名。** 当前 `provenance`／`chat.provenance`已经一致；兼容别名会重新产生两份转写，且项目尚无已发布字段需要兼容。

## 5. 最终判定

- 本轮定向范围：0 blocker、0 major、0 minor。
- 上一轮新增1 major／2 minor：全部closed。
- 是否形成0 blocker／0 major共识：**是。**

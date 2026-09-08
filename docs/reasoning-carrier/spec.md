# Reasoning 跨协议 carrier 与结构保真规格

状态：imported living specification；另一 source clone 曾在隔离 worktree 实施并评审，当前 checkout 未集成，且原 source ref／worktree 不可达。恢复条件见 [`tracking.md`](tracking.md)。

## 1. 权威边界与修订来源

本规格是 `anthropic-messages` 与 `openai-responses` 之间 reasoning 跨协议表达的行为权威，覆盖客户端可见 carrier、内部 reasoning 表示、请求回送、buffered／streaming 等价和相邻 thinking 整形的作用域。其他请求字段、普通文本、工具、终态与 usage 仍由各自既有规格负责。

2026-09-04，用户明确要求借助 Anthropic Messages `thinking.signature` 或 OpenAI Responses `reasoning.encrypted_content` 搭建格式化内部结构，以传递另一种协议无法原生表达的独有细节，并要求从根因修复多个 `summary_text` 分段被拼接后不能还原的问题。本裁决 supersede 迁移前最后一版 `docs/agents/anthropic-responses-bridge/spec.md` 中“项目主 v1 只承载 `encrypted_content`，不承担通用扩展信封职责”的限制，但不撤销以下既有合同：

- 一个 Responses reasoning item 对应一个 Anthropic thinking block，不得按 summary part 拆成多个 thinking blocks。
- provider 原生 opaque state 只能回送给签发它的协议腿；不得把 Anthropic 原生 signature 冒充 Responses `encrypted_content`，也不得反向冒充。
- 本项目 v1 与 `copilot-api-js` v1 的合法 consumer 兼容必须永久保留。
- carrier 不是认证信封，不增加 HMAC、keyring、issuer、nonce 或密钥轮换机制。
- 完整 Anthropic content block 仍是最小下游交付单元，不为获取一轮 item 总数而退化成整响应缓冲。

迁移前的完整 bridge Spec 已离开当前文档树，且其中多项非 carrier 行为已被后续实现和裁决改变；本规格只接管其 carrier／reasoning 合同，不把整份历史文档复活为当前权威。

## 2. 问题状态

当前项目主 v1 carrier 使用 `ghc-api-proxy:synthetic-reasoning:v1:` namespace，将 Responses 的非空 `encrypted_content` 编码为严格 JSON 后放进 Anthropic `thinking.signature`。它能 value-exact 恢复该字符串，但 payload key 集合固定为 `{tag, encrypted_content}`，只覆盖 Responses→Anthropic 一个方向，不能承载其他独有结构。

Responses reasoning item 的 `summary` 是有序 `summary_text` parts。当前 buffered reader、streaming assembler 和旧 helper 都先把这些 parts 拼成一个字符串，内部 `ContentBlock` 也只有一个 `text` 字段；回送时只能重建一个 `summary_text`。因此 part 数量、空 part 和分段边界在进入 carrier 之前已经丢失。

当前路径还存在四种不一致：

1. translation driver 把项目 unknown version 和 malformed v1 都当成无 payload 的合法代理 carrier，恢复为 summary-only reasoning 且不记录 loss；旧 helper 则拒绝恢复。
2. buffered Anthropic→Responses 遇到原生 Claude signature 时删除整个 reasoning 并记录 loss；streaming 路径保留 summary、静默丢 signature。
3. `destack_content()` 在目标协议尚未决定时运行，可能把 `[ghc-api-proxy: thinking separator]` 作为普通 assistant `output_text` 送进 Responses history。
4. `app.anthropic.thinking.responses_reasoning`、`app.protocols.*`、translation driver 与 streaming delivery 各自实现 reasoning 映射，codec 共享而语义不共享。

## 3. 目标

- 建立一个版本化、双向、typed 的项目 carrier envelope，可放进 Anthropic `thinking.signature` 或 Responses `reasoning.encrypted_content`。
- 保留 Responses `summary_text` parts 的数量、顺序、空 part、每段文本和当前已知 per-part 字段，使 Responses→Anthropic→Responses 在 JSON value 层恢复原结构。
- 保留 Anthropic 原生 `thinking.signature`，使 Anthropic→Responses client→Anthropic upstream 的正常回送 value-exact。
- 保留 Responses 原生 `encrypted_content`，使 Responses→Anthropic client→Responses upstream 的正常回送 value-exact。
- 统一 buffered、streaming 和兼容 helper 的解析、分类、投影与回送语义。
- 代理 carrier 只跨越“代理→跨格式客户端→代理”，不得到达任何 provider 原生 upstream。
- 无法保真的路径显式分类和记录；不得把有损转换报告为 `Conversion.lossless`。

## 4. 非目标

- 不承诺原始 JSON 的空白、object key 顺序或 escape spelling 字节级还原；承诺的是协议字段、列表顺序和字符串值的 JSON value 等价。
- 不把任意原始 Responses item 或 Anthropic block 整体塞进 carrier；每个 record 必须有明确 owner、恢复目标和字段处置规则。
- 不自动携带 Responses item `id`、model、upstream identity、timestamp 或 transport metadata。已知 item id 可能在 `.added`／`.done` 间漂移并可能与 opaque seal 绑定，必须另有规格和测量才能加入。
- 不用 carrier 解决认证、完整性、防篡改或跨租户信任问题。
- 不改变 reasoning effort／thinking budget 的请求侧配置映射。
- 不把 summary part 拆成多个 Anthropic thinking blocks，也不借普通文本 delimiter 保存边界。

## 5. 中间表示

### 5.1 一份 typed reasoning truth

内部 `ContentBlock(kind=REASONING)` 必须引用一份 typed reasoning 内容，而不是仅用 `text: str` 加一个 opaque 字符串。该内容至少表达：

- `visible_text`：投影到 Anthropic `thinking` 或默认 Responses 单 part summary 的可见字符串。
- `summary_parts`：当来源是 Responses 时，按原序保留每个 `summary_text` part，包括空字符串。
- `opaque_state`：provider 原生 continuation state，带明确的 `format` 与 value。
- `carrier_records`：当前consumer不负责解释、但grammar合法的v2 records，只保留到分类与诊断完成；当前没有允许其继续发往provider或代理间透明转交的边界。
- `source_format`：决定原生 opaque state 合法回到哪一条协议腿。
- `raw`：只作为 richest-context 来源；已知字段是否回送仍由字段处置规则决定，不能用 raw 绕过 writer。

同一 reasoning item 的可见投影、summary 结构和 opaque state 必须在一个对象内共同移动；不得用平行数组或“最后一个 ciphertext”槽关联。

### 5.2 Responses summary parts

当前已知合法 part 为：

```json
{"type":"summary_text","text":"..."}
```

reader 必须保留：

- part cardinality；
- source order；
- `text` 的 Unicode 字符串值，包括空字符串；
- 当前 reader 尚未建模但 wire grammar 允许的 per-part 字段，作为该 part 的 extensions。

遇到未知 summary part `type` 时不得拼接、跳过或伪装成 `summary_text`；在完整 block 下游可见前产生稳定的 unsupported-part 结果。

### 5.3 Anthropic visible projection

一个 Responses reasoning item 映射为一个 Anthropic thinking block。其 `thinking` 等于所有 `summary_text.text` 按原序无分隔拼接；分段信息由 v2 carrier record 保存，而不是由可见文本中的 delimiter 保存。

## 6. 项目主 v2 carrier wire contract

### 6.1 外层 spelling

- payload carrier：`ghc-api-proxy:synthetic-reasoning:v2:` 加 canonical unpadded Base64URL payload。
- bare carrier：`ghc-api-proxy:synthetic-reasoning:v2`。
- 同一 spelling 可出现在 Anthropic `thinking.signature` 或 Responses `reasoning.encrypted_content`，由所在 wire slot 决定外层方向；payload 内 record type 决定内容来源和合法恢复目标。
- v1 producer 在迁移完成前继续输出；v2 consumer 必须先行，并与 v1 consumer 永久共存。

### 6.2 Envelope grammar

v2 payload 解码后是紧凑 UTF-8 JSON object，顶层 key 集合严格等于 `{records}`：

```json
{
  "records": [
    {"type": "openai.responses.reasoning.encrypted_content", "value": "ENC"},
    {"type": "openai.responses.reasoning.summary_text_layout", "value": {"lengths": [3, 0, 7], "extensions": [{}, {}, {}]}}
  ]
}
```

`records` 必须是非空数组；空数组不是 payload carrier 的另一种 bare spelling。每个 record 的 key 集合严格等于 `{type, value}`。`type` 必须完整匹配 ASCII dotted namespace grammar `[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+`；单段 `x`、空segment、非ASCII或该grammar之外的字符均为`project_malformed_v2`。同一 envelope 内不得重复 record type。`value` 是任意合法 JSON value，但每个已知 record 还必须通过自己的 typed schema。

producer 按 record type 的 Unicode code-point lexical order 输出 records；每个 record 固定按 `type`、`value` 顺序输出字段，顶层固定先输出 `records`。JSON 使用紧凑分隔符、strict UTF-8、`ensure_ascii=false`且禁止`NaN`／`Infinity`／`-Infinity`等非JSON constants，随后使用 RFC 4648 URL-safe alphabet且不含`=`padding的Base64URL。Consumer必须先以strict UTF-8解码 bytes再解析JSON，不得让JSON库从bytes自动探测UTF-16／UTF-32；`parse_constant`等入口同样拒绝非JSON constants。Consumer不依赖JSON object key输入顺序或合法Unicode escape spelling，但必须拒绝duplicate key、non-canonical Base64URL、非UTF-8、非object、顶层额外／缺失字段和record shape错误。

carrier grammar 的版本与 record vocabulary 分离：新增 record type 不改变 envelope grammar，但要求 consumer 先部署相应 record codec。未知但 grammar 合法的 record 分类为 `unsupported_record`，不得误报 malformed，也不得在 same-format direct path 原样送往 provider；当前请求在 upstream send 前拒绝。未来若要让旧 consumer 透明转交未知 record，必须先定义一个不会把项目 carrier 送进 provider opaque slot 的代理间传输边界，本规格没有该边界。

### 6.3 已知 v2 records

#### `openai.responses.reasoning.encrypted_content`

- `value` 必须是字符串，包括空字符串。
- record 是否存在精确保留原字段 presence；因此 absent 与 present-empty 不再被 v2 producer 合并。
- 只能恢复到 Responses 原生 `reasoning.encrypted_content`。

#### `openai.responses.reasoning.summary_text_layout`

- 任何 Anthropic signature slot 的 v2 payload envelope 都必须恰好携带一个 layout record；包括原 summary 为 `[]`、单个 part 和没有 extensions 的形态。只有 bare v2 可以不携带 layout。
- `value` 的 key 集合严格等于 `{lengths, extensions}`。`lengths` 是非负整数数组；每个整数是对应 summary part `text` 的 UTF-8 byte 长度。`extensions` 是 object 数组，按相同位置保存该 part 除 `type`／`text` 外的字段。
- `lengths`、`extensions` 与原 summary part cardinality 三者相等；零长度保存空 part，空 summary固定编码为 `{"lengths":[],"extensions":[]}`。
- 所有长度之和必须等于 Anthropic `thinking` 的 UTF-8 byte 长度；每个切分边界必须位于合法 UTF-8 code-point 边界。extensions entry 不得含 `type` 或 `text`，也不得含 duplicate JSON key。
- layout 有且只有上述 object spelling；不存在纯数组缩写、payload内省略或根据可见文本猜测原 cardinality的第二种canonical producer spelling。
- bare v2只用于 canonical summary-only projection：`thinking == ""` 恢复 `summary=[]`；非空 `thinking` 恢复单个无extensions的 `summary_text` part。若原wire是一个空part、多个parts或任一part带extensions，producer必须使用payload envelope和layout record。

#### `anthropic.messages.thinking.signature`

- `value` 必须是非空字符串，value-exact 保存 Anthropic 原生 signature。
- 只能恢复到 Anthropic 原生 `thinking.signature`。
- 该 record 只能出现在 Responses `reasoning.encrypted_content` 中的项目 carrier；放进 Anthropic signature 会形成无意义自嵌套，producer 禁止，consumer 分类为 direction mismatch。

#### `anthropic.messages.redacted_thinking.data`

- `value` 必须是非空字符串，value-exact 保存 Anthropic 原生 `redacted_thinking.data`。
- 只能恢复为 Anthropic `redacted_thinking` block。
- 对 Responses 客户端没有可见 summary；不得把 redacted payload 投影为可见文字。

### 6.4 Bare v2

bare v2 只表示“这是代理产生的 canonical summary-only reasoning，没有额外 record”：

- Anthropic slot 中，`thinking == ""` 恢复 `summary=[]`；非空 `thinking` 恢复一个 `summary_text` part。
- 当Responses source没有`encrypted_content` field，且summary恰好是上述canonical `[]`或单个非空、无extensions part时，v2 producer必须选择bare，不得产生layout-only payload的第二种producer spelling。
- Consumer为了兼容可接受profile合法的layout-only payload，并按layout恢复；接受输入不授权producer输出它，也不把它变成第二个canonical vector。
- Responses slot 中不得产生 bare v2，因为 Anthropic原生 thinking 至少有一个必须保留的 signature record；consumer 见到时分类为`project_v2_direction_mismatch`。
- 项目v1 payload／bare与兼容`copilot-api` v1 payload／bare／legacy sentinel都是Anthropic signature-slot carriers；它们出现在Responses `reasoning.encrypted_content` slot时统一分类为`project_v2_direction_mismatch`。Malformed、project unknown version与foreign值不进入该映射，分别保留自身structural classification。

### 6.5 Outer-slot profiles

Grammar合法不等于该slot中的record组合合法。Consumer在typed record校验之后按下表执行profile校验：

| Outer slot | 合法known-record profile | 禁止组合 |
|---|---|---|
| Anthropic `thinking.signature` | bare v2；或payload中恰好一个`summary_text_layout`，加可选的一个`openai.responses.reasoning.encrypted_content` | 任何`anthropic.messages.*` record；缺layout的payload；额外known record |
| Responses `reasoning.encrypted_content`，来源为Anthropic thinking | payload中恰好一个`anthropic.messages.thinking.signature` | `redacted_thinking.data`、任何`openai.responses.*` record、bare v2、额外known record |
| Responses `reasoning.encrypted_content`，来源为Anthropic redacted thinking | payload中恰好一个`anthropic.messages.redacted_thinking.data` | `thinking.signature`、任何`openai.responses.*` record、bare v2、额外known record |

Profile只判outer slot、known record family、record组合和record cardinality，不判断layout与visible text是否一致，也不判断Responses summary的可见内容。`thinking.signature`与`redacted_thinking.data`互斥；一个Responses reasoning item永远只恢复一个Anthropic block。Known records个体schema合法但组合不在表中时分类为`project_v2_profile_mismatch`，不是malformed，也不得自行选择一条record恢复。

### 6.6 Presentation contracts

Profile通过后才校验record与outer visible content的跨字段关系：

- Anthropic signature slot：`thinking`必须等于layout描述的全部summary part text拼接；lengths必须对该字符串给出完整、合法UTF-8切分。
- Responses encrypted slot＋`anthropic.messages.thinking.signature`：summary必须是canonical投影，非空thinking对应恰好一个无extensions的`summary_text` part，空thinking对应`summary=[]`；恢复出的Anthropic `thinking`取该visible投影。
- Responses encrypted slot＋`anthropic.messages.redacted_thinking.data`：summary必须为`[]`且不得有可见reasoning text。

这些关系失败统一分类为`project_v2_presentation_mismatch`，不得被较早的profile分类吞掉。

## 7. 双向状态机

### 7.1 Responses upstream → Anthropic client → Responses upstream

1. Responses reader保留完整 summary parts 和 `encrypted_content` presence／value。
2. Anthropic writer生成一个 thinking block；可见 `thinking` 是 summary 文本拼接，signature 是 v2 envelope或 canonical bare v2。
3. 客户端必须原样回送整个 thinking block。
4. 请求 reader 解码 v2，校验 summary layout 与 visible text，并恢复原始 Responses reasoning item。
5. Responses last-mile writer只发送解包后的原生 fields，绝不发送 `ghc-api-proxy:*` carrier 本身。

### 7.2 Anthropic upstream → Responses client → Anthropic upstream

1. Anthropic reader保留 thinking／redacted thinking 的原生 opaque state。
2. Responses writer生成一个 reasoning item；可见 thinking 投影为 canonical summary，`encrypted_content` 放置包含 Anthropic原生 state record 的 v2 envelope。
3. Responses client原样回送 reasoning item。
4. 请求 reader识别 v2，恢复原始 Anthropic thinking／redacted thinking block。
5. Anthropic last-mile writer发送原生 signature／data；项目 carrier 本身不得到达 Anthropic upstream。

### 7.3 Same-format、换模型与 resident last-mile guard

- source 与 target 是同一 wire format时，provider 原生 opaque state原样通过，不使用项目 carrier。
- 项目 carrier 所携带的原生 state只能恢复给 record type命名的目标格式。正常跨格式路径必须在translator内完成解包，使last-mile只看见provider原生fields。
- `attempt.prepare`必须挂载一个对两种target都生效的resident carrier guard；它扫描当前attempt即将发送的target wire，并调用共享classifier识别所有非provider原生synthetic forms：本项目`ghc-api-proxy:synthetic-reasoning:`下的v1、v2、unknown version与malformed payload，以及兼容`copilot-api:synthetic-reasoning:v1`的payload prefix、bare prefix和legacy bare sentinel。不得只匹配项目prefix。
- Guard若仍发现任一上述carrier，说明same-format direct path绕过了consumer、路由已换到无法消费其state的provider，或translator漏了解包。Guard在网络调用前返回稳定的`reasoning_carrier_not_unwrapped` translation error，保留字段路径和carrier分类但不记录完整payload。
- Guard不负责猜测或恢复跨格式语义，也不把carrier原样送出。这样same-format direct path不需要临时构造`SemanticRequest.conversion` loss sink，也不会静默drop后继续一个已失去continuation的turn。
- 原生foreign state在正常cross-format translator中的既有`reasoning-state-not-portable`行为不变；不得借guard把native opaque误判成项目carrier，也不把可见summary降级为普通文本。

## 8. 分类与失败语义

consumer 必须区分：

- `project_v2`；
- `project_bare_v2`；
- `project_malformed_v2`；
- `project_v2_unsupported_record`；
- `project_v2_direction_mismatch`；
- `project_v2_profile_mismatch`；
- `project_v2_presentation_mismatch`；
- 既有 `project_v1`／bare／malformed；
- 既有 `upstream_v1`／bare／malformed；
- `project_unknown_version`；
- `foreign`。

分类按以下precedence执行，首个命中即停止，同一carrier不得在不同调用方中重新解释：

1. outer namespace／version识别；不属于项目或兼容namespace才进入foreign。
2. Base64URL、UTF-8、JSON、duplicate key、顶层grammar、空records、record shape、duplicate record type和known record typed schema任一失败，分类为`project_malformed_v2`。
3. 存在未知但grammar合法的record type，分类为`project_v2_unsupported_record`。
4. Responses slot中命中§6.4所列项目／兼容v1 Anthropic-signature form，分类为`project_v2_direction_mismatch`；其malformed／unknown／foreign形态保留structural classification。
5. record family与outer slot方向不符，分类为`project_v2_direction_mismatch`。
6. known records的family、组合或record cardinality违反§6.5 profile，分类为`project_v2_profile_mismatch`。
7. profile合法，但违反§6.6的record↔visible跨字段关系，包括summary lengths总和、UTF-8切分边界或visible summary形态／内容不符，分类为`project_v2_presentation_mismatch`。
8. 全部通过才是`project_v2`。

extensions cardinality和extensions entry shape属于known record typed schema，失败是malformed；它们不是presentation mismatch。Presentation mismatch只描述结构合法但与outer visible text矛盾的跨字段关系。

发生presentation mismatch时不能用stale layout声称精确恢复，也不能保留opaque state后猜测一个新summary；在upstream调用前返回稳定translation error。Malformed、unsupported、direction和profile mismatch也在send前拒绝；任何same-format路径都不得原样转交项目carrier。

translation driver、兼容helper、buffered response与streaming response必须调用同一classifier／record codec，不得各自把分类折叠成不同的布尔判断。所有有损结果必须进入`Conversion`；`Conversion.lossless`只在carrier records、summary结构、opaque state、block cardinality和顺序均满足本规格时为真。

## 9. Buffered／streaming 等价

- 两条路径共享同一`ReasoningContent`、carrier codec和writer projection。Streaming的`Draft`／`CompletedBlock`可以保留wire-shaped payload用于framing，但reasoning内容必须另带同一个typed object或通过唯一projection adapter构造，不能继续把`Draft.text`当reasoning truth。
- `CompletedBlock`同时常驻wire-shaped payload与typed `ReasoningContent`时，`size_bytes`必须把两份resident representation都纳入`buffer_cap_bytes`。不能只计payload而让多part text、extensions或opaque state绕过内存上界；允许以保守上界重复计算共享字符串引用，但不得低估typed结构。
- OpenAI Responses reasoning-summary事件使用`summary_index`，不是`content_index`。Assembler按`summary_index`持有独立part state；同一index内delta按event顺序拼接，不同index不得累加进一个无边界字符串。
- authority precedence从高到低固定为：`response.output_item.done.item.summary`中存在的完整summary列表；对应index的`response.reasoning_summary_part.done.part`；对应index的`response.reasoning_summary_text.done.text`加`part.added`extensions；同index的text deltas加`part.added`extensions。高层source存在时完整取代低层accumulator，不进行重复拼接。
- `response.reasoning_summary_part.added`建立该`summary_index`的part type、extensions和初始`part.text`基线；后续`text.delta`在该baseline后按event顺序追加，不能假设added text恒空。`text.done`以其完整text替换该index文本；`part.done`在`status`字段缺失时以完整part替换该index。SDK 3.3.1没有`status="completed"` spelling。
- `part.done.status == "incomplete"`不形成完整part。若更高authority的closing item携带完整summary，closing summary仍按precedence接管summary内容；若closing item缺失summary，则该reasoning item进入既有截断／失败生命周期，不得从added／delta低层state合成lossless carrier。Closing summary的内容authority不覆盖`output_item.done.item.status == "incomplete"`这一item-level终态；后者仍由既有cut-short lifecycle处理。
- Index重复open、done后delta、缺失index或非`summary_text` part进入既有malformed lifecycle错误。Closing item若携带summary则按precedence覆盖较早状态，不把合法的closing authority变化误报成矛盾。
- Closing item显式携带`summary: []`时，空列表是authoritative结果，不得fallback到delta；只有closing item完全缺失`summary`字段时才按上述per-index state重建。重建按非负`summary_index`升序且要求从0连续；空part由part事件或zero-length done保留。
- 仓内当前cassette没有这组summary事件样本，因此本节的事件字段依据是项目安装的OpenAI SDK 3.3.1 wire types；不得把“未录到”写成upstream已实测。实现测试须直接构造SDK声明的四类事件，并保留将来用真实cassette校准authority差异的入口。
- block-level delivery不要求知道本轮reasoning item总数。历史v2候选的ordinal`i`不进入本次producer；若未来需要，作为独立record另行修订本规格，不与summary保真捆绑。
- 对同一完整语义响应，buffered与任意合法SSE chunking最终产生相同的Anthropic blocks、v2 payload records和回送后的Responses reasoning items。

## 10. 相邻 thinking 整形作用域

`destack_content()` 是 Anthropic Messages upstream 对相邻 thinking／redacted thinking blocks的 last-mile兼容整形，不是 inbound Anthropic message的通用标准化。

- 只有最终`target_format == anthropic-messages`时可运行。挂载点是每次attempt发送前与counting wire形成后的`attempt.prepare`，因此direct Messages、translated-to-Messages、retry和counting走同一处置。
- 新增一个resident last-mile subscriber，负责§7.3 carrier guard与Anthropic target destack；subscriber本体、`pipeline/subscribers/__init__.py`注册／顺序和`server/composition.py`配置绑定是同一功能的owner，不得只写函数而不挂载。
- 顺序固定为blank-text先删除无内容block，reasoning last-mile subscriber随后统一检查carrier泄漏并处理因此形成的thinking邻接，trailing-assistant repair最后读取成形后的message list。`blank_text.py`不再自行插入separator，避免两个owner各自修同一邻接。
- Anthropic→Responses翻译不得在reader之前或中间表示阶段插入`[ghc-api-proxy: thinking separator]`。
- Responses reasoning items在Responses wire中保持独立top-level items，不需要ordinary assistant text充当间隔。
- Anthropic last-mile若必须插入separator，该文本只存在于发往Anthropic upstream的兼容历史中；不得被解释为reasoning carrier，也不得回写到原始请求事实。

## 11. 兼容与迁移

1. 先部署 v2 consumer和统一 classifier；producer继续输出v1。
2. v2 consumer覆盖 Anthropic signature slot与Responses encrypted_content slot，并永久保留项目v1、`copilot-api-js` v1合法主路径和bare forms。
3. 所有 active实例可读v2后，再切换v2 producer。
4. producer回退可恢复发v1，但v2 consumer一旦发布不得撤回；客户端历史可能已经保存v2。
5. 本规格取代此前仅为ordinal `i`设计的候选v2。原`exp/carrier-v2/`脚本已降格为具名historical counterexample，不再自称canonical／frozen，也不作为当前oracle。当前v2独立静态vectors位于`exp/reasoning-carrier-v2/gen_vectors.py`，不import产品codec；tests中的expected不得调用产品encoder生成。
6. 不改写v1 payload schema；所有新结构只进入v2。

## 12. 可证伪验收

### 12.1 Codec 与分类

- 独立静态向量覆盖v2 bare、每一种已知record、record排序、非ASCII Unicode、present-empty、duplicate record type、duplicate JSON key、非法Base64URL、strict UTF-8拒绝UTF-16／UTF-32、拒绝`NaN`等非JSON constants、拒绝非dotted record type、unknown record、direction mismatch和unknown outer version。
- Profile vectors独立覆盖：Anthropic slot缺layout、两个Anthropic state records并存、跨source-family混合、额外known record、Responses slot bare v2，以及Responses slot中的项目／兼容v1 payload／bare／legacy forms；它们必须只得到profile或direction分类，不得被presentation吞掉。Helper、reader与last-mile guard对后一组forms必须逐项得到同一`project_v2_direction_mismatch`。
- Presentation vectors在profile合法的前提下独立覆盖：layout lengths总和不符、非法UTF-8边界、thinking text与layout不符、signature profile携带非canonical summary、redacted profile携带可见summary；它们必须只得到presentation mismatch。
- producer-only变异任一prefix、record type、UTF-8、Base64URL padding、record排序或present-empty行为时，静态向量失败。
- consumer-only直接喂各分类输入，expected不调用产品encoder生成；unknown／malformed不得恢复为summary-only成功，也不得落入foreign。上述classification vectors必须分别经过translation driver、兼容facade和streaming projection使用的同一classifier入口，三条路径结果一致。

### 12.2 Summary structure

- 原始summary为`[]`、一个非空part、一个空part、多个parts、首／中／尾空part、Unicode astral字符和per-part extensions时，Responses→Anthropic→Responses恢复后的summary列表与原始JSON value完全相等。
- 正控必须使用`[{"type":"summary_text","text":"一"},{"type":"summary_text","text":""},{"type":"summary_text","text":"😀二"}]`，expected直接写出同一完整列表；分别经过buffered reader、streaming closing／delta入口和request-side decoder。旧实现必须只因归并为单part而失败，新实现恢复原列表JSON value。
- 删除layout record、改变一个UTF-8长度或把长度单位误换成UTF-16 code units时，回归测试必须失败或得到明确presentation mismatch，不得仍报告lossless。

### 12.3 双向 opaque state

- Responses非空、空和absent `encrypted_content`分别往返，field presence和值均恢复。
- Anthropic原生thinking signature经Responses客户端形态回送后value-exact恢复。
- Anthropic redacted thinking经Responses客户端形态回送后恢复原block且不产生可见summary。
- 任一项目carrier或兼容`copilot-api:synthetic-reasoning:v1` payload／bare／legacy sentinel被捕获在发往provider upstream的实际wire时，测试失败；last-mile capture至少分别用一个项目v2和一个兼容v1正控证明guard覆盖两套namespace。
- native Claude signature不得被直接写成Responses原生`encrypted_content`；native Responses opaque不得被直接写成Anthropic原生signature。

### 12.4 路径一致性

- 同一semantic fixture分别走buffered和streaming，比较归一化block、carrier records和回送wire，而不是只比较拼接文本。
- Streaming正控包含非空`part.added.text`后继续delta，证明baseline未丢且未重复；`part.done.status="incomplete"`且closing缺summary时必须进入截断／失败，加入完整closing summary后则由closing authority恢复成功。
- translation driver、兼容helper和streaming framer对malformed／unknown／foreign／profile／presentation分类相同。
- buffered与streaming Anthropic原生signature跨Responses客户端时均保留在项目carrier中，不得一条drop、一条summary-only。`redacted_thinking`同样必须在AnthropicAssembler形成typed reasoning，并经Responses client carrier恢复原block。
- 构造wire payload尚未超过cap、但typed reasoning携带大extensions后超过cap的block；`BlockBuffer`必须据完整resident size触发`BufferCapExceeded`。移除typed reasoning计量后该正控必须变红。

### 12.5 Separator 作用域

- Anthropic输入含两个相邻、可恢复的proxy thinking carriers并路由到Responses时，实际Responses input只有两个reasoning items且顺序不变，没有assistant separator message。
- 同一输入路由到Anthropic Messages upstream时，last-mile按配置完成destack。
- 用户真实输出恰好等于`[ghc-api-proxy: thinking separator]`时，不得被carrier decoder或Responses路径清理器误删。

## 13. 实施范围

预计涉及：

- `src/app/pipeline/translation_driver/content.py`
- `src/app/pipeline/translation_driver/reasoning_carrier.py`和新的统一typed reasoning codec／projection owner
- `src/app/pipeline/translation_driver/anthropic_messages.py`
- `src/app/pipeline/translation_driver/openai_responses.py`
- `src/app/pipeline/translation_driver/responses.py`
- `src/app/pipeline/delivery/assembling.py`
- `src/app/pipeline/delivery/blocks.py`
- `src/app/pipeline/delivery/formats/openai_responses.py`
- `src/app/pipeline/anthropic_request_hook.py`，从中移除pre-translation destack
- 新的resident last-mile subscriber、`src/app/pipeline/subscribers/__init__.py`注册与排序、`src/app/server/composition.py`配置绑定
- `src/app/pipeline/subscribers/blank_text.py`，移除其独立separator owner
- `src/app/anthropic/thinking/responses_reasoning.py`及仍引用它的`src/app/protocols/*`兼容facade
- 对应unit／integration tests与新的v2独立vector脚本

统一typed codec／projection是唯一reasoning语义owner。旧`responses_reasoning.py`和`protocols/*`facade若因兼容import暂留，只能调用统一core，不得保留独立v2 parser／writer或summary accumulator；旧helper tests迁移到core，只保留facade delegation smoke test。能够确认无生产／外部import依赖的旧入口可以在本patch删除，但删除前必须按项目收尾规则独立评审，不能为去重自行扩大破坏面。

实现不得提前修改observable behavior；本规格通过独立评审并完成finding处置后才进入worktree代码阶段。

## 14. 修订记录

- 2026-09-04，v1草案：依据用户本轮“使用两种协议的opaque槽搭建格式化内部结构、传递独有细节，并根因修复summary分段丢失”的指示，建立双向typed v2 envelope、结构化IR、统一路径和last-mile destack合同；取代历史v1的非通用限制及未落地的ordinal-only v2候选。
- 2026-09-04，v2评审修订：采纳两份独立评审的全部findings，取消payload内layout omission，冻结outer-slot profiles与分类precedence，修正streaming字段为`summary_index`并补齐event authority，增加same-format resident guard与完整subscriber／streaming owner，裁定旧helper薄委托统一core，修正summary正控，并同步降格ordinal-only v2实验。处置 authority为`spec-review-disposition.md`。
- 2026-09-04，v3复评修订：补`part.added.text`baseline与`part.done.status=incomplete`，将last-mile guard扩到兼容`copilot-api` synthetic v1，严格分离profile结构判定与presentation跨字段判定并增加独立vectors；同时采纳wire复评的两条minor，收窄unknown records职责并固定canonical bare producer spelling。
- 2026-09-04，v4评审收口：两条独立评审线均PASS；按最后一条minor删除不存在的`status="completed"` spelling，并明确closing summary只决定内容authority、不覆盖item-level incomplete终态。评审处置见`spec-review-disposition.md`。
- 2026-09-04，v5实施评审修订：实现review反例证明Python JSON bytes入口会自动接受UTF-16／UTF-32、默认JSON encoder／decoder会接受`NaN`，并暴露record namespace、Responses-slot legacy-v1 direction classification、redacted streaming与typed reasoning buffer accounting的规格缺口。补exact dotted grammar、strict UTF-8／JSON constants、v1 slot映射、resident size与对应验收；触发者为`reports/260904-implementation-review-general-opus-1.md`、`reports/260904-implementation-review-gpt-opus-1.md`及closeout review。

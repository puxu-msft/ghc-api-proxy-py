# Reasoning carrier v2 实现评审处置

状态：closed。两条实现评审线最终均为PASS，0 blocker／0 major。

评审原件位于`reports/`：

- `260904-implementation-review-general-opus-1.md`
- `260904-implementation-review-gpt-opus-1.md`
- `260904-implementation-rereview-general-opus-2.md`
- `260904-implementation-rereview-gpt-opus-2.md`
- `260904-implementation-rereview-general-opus-3.md`
- `260904-implementation-rereview-gpt-opus-3.md`
- `260904-implementation-rereview-general-opus-4.md`

## 第一轮处置

| Finding | 处置 | 级别 | 实施证据 |
|---|---|---|---|
| codec接受UTF-16／UTF-32、NaN和非namespaced record type | 采纳 | C | UTF-8 strict decode后再JSON parse；producer `allow_nan=False`，consumer拒绝非JSON constants；record type执行dotted namespace grammar；独立Unicode／UTF-16／NaN／namespace反例已进入tests。 |
| slot-aware classification未传播，facade／guard误报粗`project_v2` | 采纳 | C | 统一slot-aware classify helpers传播到facade与guard；unsupported／direction／profile／presentation矩阵进入core和facade tests。 |
| guard漏扫`redacted_thinking.data` | 采纳 | C | Anthropic last-mile对thinking signature和redacted data使用同一synthetic判断，actual subscriber正控已加入。 |
| Anthropic redacted streaming未形成typed reasoning | 采纳 | C | `redacted_thinking`成为delivery block kind，AnthropicAssembler构造ReasoningContent，ResponsesFramer输出v2 redacted carrier；SDK stream回放和回送正控通过。 |
| typed reasoning未计入buffer size | 采纳 | C | `CompletedBlock.size_bytes`同时计payload与typed reasoning resident表示；大extensions正反样本证明cap在payload-only尚未越界时触发。 |

## 第二轮处置

两条复评线共同发现Responses slot bare v2被slot-aware helper提前返回为粗`project_bare_v2`，而reader已按Spec判为direction mismatch。采纳（C），并把修复扩到项目／兼容v1的payload／bare／legacy全部Anthropic-signature forms；helper、reader与last-mile guard矩阵现一致。

## 最终复评

- `260904-implementation-rereview-general-opus-3.md`：PASS；六种Responses-slot carrier形态在helper、reader、guard三路径均为direction mismatch。
- `260904-implementation-rereview-gpt-opus-3.md`：PASS；分类修复未重开redacted streaming或size accounting。
- `260904-implementation-rereview-general-opus-4.md`：PASS；最终Pyright所需的纯fixture类型注解不改变runtime JSON bytes或strict UTF-16反例。

没有不采纳、暂定、deferred或待用户裁决的finding。所有observable refinement已进入living Spec v5。

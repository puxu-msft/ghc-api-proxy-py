# Direct buffered Chat Completions 最终定向规范复评

日期：2026-09-06。

评审范围严格限定为上一轮复评的 R-1、R-2、n-1及其相邻文字；未重审未变化内容。前序报告为 [`260906-spec-consistency-review.md`](260906-spec-consistency-review.md) 与 [`260906-spec-consistency-rereview.md`](260906-spec-consistency-rereview.md)。本文是时点复评报告，不替代 living Spec。

## 结论

**三项均已闭合，定向复评达到 0 blocker／0 major。** 本轮没有发现新的 blocker、major或minor；可以就当前书面设计形成 **0 blocker、0 major共识**。

## 逐项复核

| Finding | 状态 | 证据 |
|---|---|---|
| R-1　聚合表的“其它已知top-level snapshot字段”未封闭 | **CLOSED** | `direct-passthrough/spec.md` §9.3.1第792行把last-explicit-wins集合封闭为 `service_tier`、`system_fingerprint`、`moderation`三个逐字字段，并明令新增成员须先修表、SDK类型不得自动扩大；第801行规定凡未逐字枚举者一律按原JSON层级投影到top-level／choice／message／tool／function object，冲突即 `unassemblable`。同一输入不再因实现者或SDK版本对“known”的认知不同而在success／502间摇摆 |
| R-2　`event:error` parsed flat object没有最终JSON carrier | **CLOSED** | `error-envelope/spec.md` §8第383行明确：含top-level `error`的object原值保留；其余由SSE event名 `error` 或flat `type:"error"`确认的parsed object，整个object作为标准OpenAI envelope的 `error` 值，且不得补写或覆盖原字段。正文直接列出 `event:error` + `{"code":"server_error","message":"…"}` 正例；429／502、malformed raw、headers与content type的相邻规则仍唯一。§10.2第427行精确回指§8，没有平行映射 |
| n-1　Capability default类型宽于行为Spec | **CLOSED** | `direct-buffered-chat-completions/design.md` §4.1已把两字段收窄为 `Literal[True] | None`，与 `direct-passthrough/spec.md` §9.3的 `true`／`None`闭集及Xingchen descriptor完全一致；显式client `false`仍只属于payload值，不再可能被误当descriptor default |

## 相邻文字一致性

1. §9.3.1仍保持“本项目字段表是authority、OpenAI SDK accumulator只作实现基础、SDK升级不得静默改输出”，封闭集合修订与该原则一致。
2. Unknown字段现在同时定义分类、原层级投影、冲突结局和direct raw streaming例外，没有把SDK helper字段带入client JSON；`unassemblable`仍为502且不retry。
3. Error reader的三种carrier识别与error-envelope最终body现在一一对应：nested object、flat `type:"error"` object、event-name确认的其它parsed object，以及non-object／unparseable raw均有唯一归宿。
4. 新增flat carrier分支没有覆盖上游现有type／code，也没有改变rate-limit 429、其它stream error 502或“无真实 `Retry-After` 不合成header”的既有合同。
5. Capability收窄没有改变当前CodeBuddy／Xingchen／GitHub三个profile，也没有重开provider内容处理；provider仍只声明capability并发送pipeline最终payload。
6. 三项修订没有改变post-`[DONE]`语义、candidate observation promotion、TUI schema、client-leg direct／translated边界、HTTP 499状态或translated multi-choice deferred。

## 否决建议及原因

1. **否决重新引入“其它已知字段”或让SDK typed model决定last-wins集合。** 这会复现R-1并违反Spec authority。
2. **否决为event-name flat carrier另造proxy默认type／code。** 当前整object保留已闭合信息保真；补写会覆盖或冒充上游事实。
3. **否决把descriptor default扩回普通 `bool | None`。** `false`是显式client payload值，不是当前capability algebra成员。
4. **否决借最终复评重开Chat block-level delivery、continuation、streaming proxy error frame、translated multi-choice或真实P6／canary。** 这些内容均未因三项局部修订改变，且前序报告已记录边界与理由。
5. **否决重审未变化内容或新增proof gate。** 协调者明确要求定向复核；三项修订可由当前living Spec直接判定，不需要扩大验证体系。

除上述五项外，本轮没有其他审查后否决的建议。

## 最终共识

本定向复评确认前序复评的2项major与1项minor均已闭合，且修订未产生新的同级问题。当前书面设计candidate可记录为 **0 blocker、0 major**。

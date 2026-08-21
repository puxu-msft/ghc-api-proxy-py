# Anthropic Responses Bridge Architecture 独立复评 R2

## 评审摘要

- **评审范围**：主树工作区当前 `docs/agents/anthropic-responses-bridge/architecture.md`，SHA-256 `74fef4675ebc61c89dbc31648acce6c21c8554649b8473ed20236c8a4e7e683c`，Git blob id `d025b3e4abe28628d756fc399db1ca4c2341d0bf`；复评时本地 `main` HEAD 为 `ed77c9d191df81c451c25161420515cca52ce6a4`。目标文档是主树工作区新增文件，不是该 HEAD 中的 tracked blob，因此内容身份以本段 hash 为准。
- **总体 verdict**：**修复 major 后可定稿；当前不可定稿。**
- **计数**：blocker 0，major 3。本文按要求不报告 minor 或 nit。
- **双视角覆盖证据——机械核对**：逐条对账上一轮 M1～M5 与用户后续两项重裁；核对 exchange context／cancel／close outcome、`AnthropicBlockKey`、headers／`message_start`／block／terminal frontier、History projection ownership、request-local journal 与 SQLite durability、默认 History 精简投影、global reservation／admission／spill 禁令、reasoning v1 prefix／base64url／legacy sentinel／foreign signature。另对照当前主线新增的 `responses_reasoning.py` 与对应测试、既有 `history-system.md` 和 `HistoryConsumer`。每次 shell 取证均先确认工作树分支为 `main` 且 HEAD 等于本地 `refs/heads/main`。
- **双视角覆盖证据——第一人称执行**：模拟了 success、parse failure、client cancel、shutdown 与 cleanup 中再次 cancellation 的 exchange 退出；同一 Responses item 多 content parts、跨 item 交错完成和连续前缀提交；HTTP success headers 已 accepted 但 `message_start` 未 accepted、body write outcome uncertain；大 response projection 被 History queue accepted 后 request FINALIZE、随后 SQLite durable／failed；多个 reasoning items 经当前主线 helper 聚合后再按目标架构的一对一 block sequencer 执行；普通 reservation 等待、容量恢复和拒绝新 admission。当前环境没有 `pytest` 模块，故未把 `pytest` 声称为通过；改从真实测试文件发现并直接执行全部无 fixture 的 `test_*` 函数，均完成，确认当前主线的实际 reasoning 合同是“多个 reasoning item 聚合为至多一个 leading thinking block”。

## 逐项复核结论

| 项目 | 结论 | 复核摘要 |
|---|---|---|
| M1 exchange close／cancel | **未完全关闭，见 R2-M1** | async context manager、typed cancel／close outcome、幂等 close 和唯一 owner 已补；但重复 cancellation 可截断 `__aexit__` 中的 cleanup，且 primary failure 与 close failure 的机械优先级未冻结。 |
| M2 Anthropic block identity | **关闭** | `AnthropicBlockKey(attempt_id, source_item_identity, content_part_identity, semantic_kind)` 能区分同 item 多 parts；协议 output／content order 与连续前缀 sequencer 已分开，正反控制同时覆盖合法 multi-part 与非法 lifecycle。 |
| M3 headers／`message_start` frontier | **关闭** | delayed response-start owner、headers／`message_start`／block／terminal 的 accepted／uncertain 状态及分状态 failure matrix 已形成可执行闭环；assembler／renderer 完成不再冒充 committed。 |
| M4 History ownership | **部分关闭，见 R2-M2** | cleanup 前生成 immutable projection、连 reservation token 移交、queue 按 job／bytes 有界及 accepted／durable 分离已解决原 cleanup-after-read 缺陷；但 FINALIZE 后的 durable／failed fact 没有合法 journal owner。 |
| M5 journal vs persisted summary | **关闭** | request-local journal 与默认持久化投影已明确分层；默认 SQLite 只保存既有 response、标量和必要终态摘要，不落逐-attempt 对象图或 raw event 序列，未重裁轻量终态 History。 |
| 用户重裁：无 oversized debt／spill | **关闭** | 16 MiB 不参与状态选择；无 per-block threshold、超大 block debt、spill、victim selection 或 overflow-to-live；只保留普通 global reservation／有限队列／backpressure，并在已决最小止血条件下拒绝新 admission。 |
| 用户重裁：reasoning 兼容 | **部分关闭，见 R2-M3** | v1 carrier 的 prefix、unpadded base64url、bare prefix、legacy bare sentinel 与 foreign signature 边界已冻结；但 block identity 与当前主线已集成且测试固化的 helper 的跨 item 聚合合同冲突。 |

## 事实性发现

### [major] R2-M1 `architecture.md:284-290, 464` — exchange cleanup 仍可被第二次 cancellation 截断，且 secondary close failure 的优先级未形成可执行合同

**问题**：文档规定 `__aexit__` “无条件等待 `aclose()`”、`cancel()`／`aclose()` 幂等、close failure 不覆盖原始业务 failure，但没有规定 cleanup 如何跨越后续 cancellation 完成，也没有把 primary cancellation／parser error／业务 failure 与 secondary close failure 的最终传播优先级写成机械规则。幂等只防重复副作用，不保证第一次 cleanup 一定完成。

**证据或失败场景**：client cancel 使 driver 进入 `__aexit__`，正在 settle producer task 或关闭 HTTP／WS 时 shutdown 再次 cancel 同一 task；普通 `await aclose()` 会再次抛 `CancelledError`，底层 `finally` 尚未跑完，资源计数不能归零。另一条路径中 parser 已抛 primary error，而 `aclose()` 又失败；若 `__aexit__` 直接传播 close error，就违反文档自己的“不得覆盖原始业务 failure”，若吞掉 close error，又违反 close failure 必须可观测。现有“重复调用返回同一 typed outcome”验收抓不到第一次调用被中途截断的状态，可能 false-green。

**修复建议**：冻结 cancellation-resilient cleanup protocol：首次 close 创建唯一 cleanup task；调用方在后续 cancellation 下持续观察该 task直到资源进入 terminal close state，再恢复 primary cancellation／exception。明确异常优先级：存在 primary 时最终传播 primary，secondary close failure 写入 typed close fact／metrics／journal；不存在 primary 时 close failure 才成为最终错误。验收增加“cleanup 中点二次 cancel”、`cancel + close error`、`parser error + close error`、`normal exit + close error` 四条确定性路径，并同时断言底层 close 至多一次、producer／connection 归零和 secondary failure 已被观察。

### [major] R2-M2 `architecture.md:415-423, 431-436, 518` — FINALIZE 后异步产生的 `history.durable`／`history.persistence_failed` 没有合法事实 owner

**问题**：文档把 `history.durable` 和 `history.persistence_failed` 列为 request-local fact journal 事件，又规定 journal 是 driver 发布事实的请求内真相、observer 不得回写 driver state；同时允许 History 在 FINALIZE 后异步 durable。FINALIZE 时 request terminal facts 已冻结且 request owner 可结束，因此后续 SQLite commit／failure 既不能追加到已冻结 request-local journal，也不能由 History observer 回写。原 M4 的 projection 资源所有权已解决，但 durability receipt 的事实所有权仍自相矛盾。

**证据或失败场景**：driver 将 projection 与 reservation token 移交，发布 `history.projection_accepted` 并 FINALIZE；writer 稍后 SQLite commit。若 writer 追加 request-local journal，就破坏“observer 不回写”与 FINALIZE 冻结；若不追加，`history.durable` 永远不在文档声称的完整 journal 中；若为了等待 durable 延后 FINALIZE，又违背“默认 History 可以在 FINALIZE 后异步 durable”，并把磁盘 I/O 重新拉回请求生命周期。writer 最终失败时同样没有地方承载 `history.persistence_failed`，而 reservation token 的释放事实也无法与该 receipt 对账。

**修复建议**：把事实面显式拆成两本账：request-local lifecycle journal 只记录 `history.projection_accepted|rejected` 和 projection id，随 FINALIZE 冻结；History writer 拥有独立的 persistence receipt journal／metrics，以 projection id 记录 `durable|failed`、token release 与时间。若必须从 request 视图查询 durable 状态，只通过 projection id 关联投影，不回写 request journal。同步修改事件清单、owner 表、FINALIZE 判据与验收，分别证明 accepted 后 request 可结束、writer 后续 durable／failed 均可观测且 reservation 恰好释放一次。

### [major] R2-M3 `architecture.md:323-342, 366, 514-516, 530` — reasoning block identity 与当前主线已集成且测试固化的跨 item 聚合行为冲突，迁移形态未裁决

**问题**：目标架构以 source item／part／semantic kind 建独立 `AnthropicBlockKey`，并要求 assembler 逐目标 Anthropic block 产出 `CompletedBlock`；Reasoning identity 又写成“恢复每个 block 自己的 `encrypted_content` 与 summary”，复审证据要求覆盖多个 reasoning blocks。当前 `main` 的已集成 helper `src/app/anthropic/thinking/responses_reasoning.py:55-95` 则明确接收完整 item 序列，聚合全部 summary、只保留最后一个非空 `encrypted_content`，并至多返回一个 leading thinking block；`tests/unit/test_responses_reasoning.py:64-93` 固化该行为。两者不能同时作为实现合同。

**证据或失败场景**：上游依次返回 reasoning item A 与 B，各有不同 summary／encrypted payload。实现者若复用当前主线 helper，会在 assembler 前把 A、B 合成一个 block，导致架构的 per-source-item identity、独立完成时点与多个 block ledger 消失；实现者若照架构一对一产出两个 blocks，则会绕过或替换刚集成并评审通过的 helper。carrier prefix 与 base64url 完全兼容并不能解决这个语义冲突，因为冲突发生在“几个 Responses item 映射成几个 Anthropic blocks”而不是 carrier bytes。当前主线 helper 的直接执行结果与其测试一致，因此这不是仅靠静态阅读推测的风险。

**修复建议**：在架构中明确作出并记录迁移裁决。若目标仍是一 item一 block，则写明当前聚合 helper 仅是旧 upstream 兼容切片、不得进入 bridge response normalizer，并列出替换／退役路径及一对一正反控制；若要保留当前聚合 helper，则必须同步修改 `AnthropicBlockKey`、completion/order、ledger、History projection 和多 reasoning 验收，使“聚合后的一个目标 block”成为唯一合同。不能只保留 U2 的 carrier 字节说明而让实现者自行选择 block cardinality。

## 定稿裁决

**当前不可定稿。** 上一轮 M2、M3、M5 与用户的低概率容量重裁已经形成一致、可执行且不引入 oversized debt／spill 的合同；M4 的 projection ownership 主缺陷也已修复。剩余三项 major 都位于实现者无法自行安全猜测的 owner／lifecycle／semantic cardinality 接缝：exchange cleanup 在重复取消下是否完成、FINALIZE 后 durability receipt 归谁、多个 reasoning items 到底映射成一个还是多个 Anthropic blocks。修订 R2-M1～R2-M3 后应再次逐条复核；三项关闭且未引入新的 blocker／major时，本文可定稿进入下一阶段。

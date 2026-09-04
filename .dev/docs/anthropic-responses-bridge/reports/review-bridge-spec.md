# Anthropic Responses bridge 规格独立评审

## 评审结论

- **评审范围**：`docs/agents/anthropic-responses-bridge/spec.md`，并对账同目录 `research.md`、`architecture.md`、`acceptance.md`、当前生产代码与 `docs/2604-rewrite/tool-use.md`。目标主仓固定 `HEAD=47d9ef101c4b81ac70d805b1da157b34d021d33d`；主 upstream 复核至 `2e7e998bc2ba150723f2fbe48fefd9eb5b6dbe03`，相对研究快照的受关注代码路径无变化。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **计数**：blocker 0，major 6。
- **命题结论**：C1 不通过；C2 名义范围齐全但关键合同不完整，故不通过；C3 不通过；C4 通过；C5 不通过。

## 双视角覆盖证据

- **机械核对**：逐节清点 route/model/request/response/tool/reasoning/signature/nonstream/SSE/WS/retry/order/no-dup/no-loss/usage/error/header/approval/hooks/history/tokenization/shutdown/cancel/backpressure/limits；逐项对账 A～E 待裁决清单、当前代码引用、既有 tool 产品边界及 upstream 固定快照。每次 shell 均在同一调用内校验目标 repo top-level 与 `HEAD=47d9ef101c4b81ac70d805b1da157b34d021d33d`。
- **第一人称执行**：模拟了双 endpoint 模型路由、B2 首 block 前失败与 retry、多 system/未知字段、server-tool 输入输出、foreign/旧版 signature、多 reasoning usage、sink 不确定失败；同时用合法多 block、合法 unknown metadata、合法 encrypted-only reasoning 检查规格是否会 false-red。

## 事实性发现

[major] `spec.md:8,166-172,410` — B2 允许首个完整 block 前下发 `message_start`，直接重开了“完整 block 是最小可观察提交单元”的已决边界。
失败场景：按 B2 早发 `message_start` 后 upstream 在首 block 前失败，失败 attempt 已泄漏 downstream event，却仍被 `spec.md:222` 视为可透明 retry。
修复建议：排除 B2；或明确首 block 前下游零 header/body event，`message_start` 只能与首个完整 block batch 一起提交。

[major] `spec.md:72-81,381,426-440,470` — 双 endpoint／vendor 的默认 route precedence 仍只是“提案”，却未进入 A～E 用户裁决项，验收又假定 route policy 已确认。
失败场景：模型同时广告 Messages 与 Responses，或非 Anthropic vendor 广告 Messages 时，两种实现可作不同选择并都声称符合规格。
修复建议：新增独立 route-policy 裁决，冻结 model mapping、override、vendor、双 endpoint、unknown capability 与 transport availability 的完整优先级。

[major] `spec.md:98-102,119-121,128,142,343-344` — 规格要求显式字段处置矩阵，却未提供矩阵，并把 reject/degrade/repair/strict/permissive 的公开行为留给实现者。
失败场景：合法但不可直映的 cache metadata、typed tool、foreign signature 或未来字段可被一个实现拒绝、另一个降级；过严实现会拒绝本可保真的正确输入。
修复建议：逐字段冻结 preserve/transform/reject/degrade 及默认 compatibility mode；需产品选择的项目加入用户裁决清单。

[major] `spec.md:119,142` 与 `docs/2604-rewrite/tool-use.md:12,34` — 规格允许“受支持 server-tool result”映射，却未声明这不能改变当前“不支持 Anthropic 原生 server-tool 编排”的既有边界，也未请求重裁。
证据：当前文档明确不执行、不合成、不过滤、不降级重试 server tools；bridge 规格中的“受支持”没有来源、白名单或批准状态。
修复建议：基础规格固定 no-revive＋显式拒绝／降级；任何 server-tool 映射白名单作为单独用户裁决和产品能力规格。

[major] `spec.md:241-246` — Anthropic usage 算术未冻结，尤其把 reasoning 是否计入 output total 留成任选口径，无法形成唯一验收 oracle。
命令证据：`git show 2e7e998b:src/lib/openai/translate/responses-to-anthropic.ts` 的 `mapUsage()` 直接采用 `usage.output_tokens` 并另存 reasoning detail；目标 `Usage.total_tokens` 又等于 input＋output。
修复建议：冻结 cache 净 input、output、reasoning detail 与 total 的精确公式，明确 reasoning 是 output 子集且不得二次相加，并给出数值向量。

[major] `spec.md:126-131,342,384` — synthetic signature 被定义为跨轮公共兼容协议，却只要求“版本化＋byte-exact”，缺少可互操作的 carrier schema 与信任边界。
失败场景：不同实现对版本、编码、source/model domain、完整性、空 payload、大小上限、旧版支持窗口和 strip policy 作不同选择，producer→echo→consumer 无独立 oracle。
修复建议：冻结 wire grammar、域绑定、完整性校验、limits、版本迁移／拒绝规则和公开测试向量；产品取舍列为用户裁决。

## 主观建议

未列；以上均为可复现的规格完整性或既有合同冲突。

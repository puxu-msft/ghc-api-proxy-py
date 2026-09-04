# Anthropic Responses bridge acceptance 独立复评 R2

- **评审范围**：`docs/agents/anthropic-responses-bridge/acceptance.md`；逐项对账上一轮 `docs/tmp/review-bridge-acceptance.md` 的 2 个 blocker 与 5 个 major，并以当前内容哈希绑定的 `spec.md` 为行为 oracle、`architecture.md` 为非覆盖性架构参考。固定 upstream carrier 另以 `/home/xp/src/copilot-api-js` commit `8d5c861c2e079b92401dd8ccd49695a363d078fe` 的原始源码复核。
- **总体 verdict**：**修复 major 后可进入下一阶段**。当前 acceptance 尚不能作为最终放行 oracle；修复下列 2 个 major 并复评后，才可明确升级为“可作为 oracle”。候选 bridge 的实现状态仍为 **`UNVERIFIED`**，本轮未把规范完整性评审误写成实现通过。
- **blocker 数**：0。
- **major 数**：2。
- **基线证据**：每次 shell 调用均在同一调用内通过仓库根、当前分支和 `HEAD == refs/heads/main` gate；最终复评基线为本地 `main` commit `ed77c9d191df81c451c25161420515cca52ce6a4`。评审对象位于该主线工作树但尚未形成提交；复核时 `acceptance.md` SHA-256 为 `43181f7b6ea988ca3a26e90ec307b2cefd15b4bf37e96483609ea78036ddc32e`，其绑定的 Spec、Architecture 与上一轮报告哈希分别与正文声明一致。

## 双视角覆盖证据

- **机械核对**：逐项复核 policy binding、`LIVE-CANARY`／`CAPTURE-CORPUS`／`LOCAL-FAULT` 三层拆分、reasoning producer-only／consumer-only 独立 carrier vectors、continuous completed prefix、sink partial write 与 `delivery-uncertain`、SDK 前 raw capture provenance、strict grammar 与 SDK compatibility 分离，以及“无 `>16 MiB` 专门 gate”。同时将每项 expected 与当前 Spec 字段矩阵、route precedence、server-tool no-revive、post-commit failure、limits 合同逐行对账，并读取固定 upstream commit 的 carrier builder、extractor 与 authoritative `.done` 代码，未以候选 Python 实现或同源 round-trip 代替 oracle。
- **第一人称执行模拟**：模拟验收实现者从 manifest 绑定 Spec 开始，依次建立 route／conversion gates、live canary、历史 raw corpus、本地 fault replay、strict SSE state machine、官方 SDK compatibility、连续前缀 sequencer、partial-write sink 和 memory reservation tests；重点走过 policy hash 变化、托管上游本轮不产生异常、A 未完成而 B 先完成、producer／consumer 单侧变异、response-start／block／terminal 不同 offset 的不确定交付、SDK 宽松接受非法 feed、单请求聚合 resident bytes 持续增长但全局尚有余量，以及跨过 16 MiB 但仍属普通大小维度的分支。

## 上一轮问题逐项结论

| 上一轮 ID | R2 结论 | 复核依据 |
|---|---|---|
| B1 policy expected 未冻结 | **已关闭** | `acceptance.md:7-11,45,361-364` 绑定当前 Spec 内容哈希、冻结基础行为，并把未来未冻结扩展明确留为 `UNVERIFIED`；required expected 不再由候选实现选择。 |
| B2 真上游异常不可按需制造 | **已关闭** | `acceptance.md:52-56,285-312,362` 将确定性 live、真实／官方 capture corpus 与本地 fault 分开；不可控异常未出现不判缺陷，缺失或过期 corpus 只使受影响范围 `UNVERIFIED`。 |
| M1 signature 闭环同源 | **已关闭** | `acceptance.md:89-96` 固定 upstream commit、exact bytes 与三条 provenance 链，强制 producer-only／consumer-only 单侧变异；固定 upstream 源码复核确认 prefix、Node base64url、legacy 与 authoritative `.done` 描述一致。 |
| M2 完成即提交与原序冲突 | **已关闭** | `acceptance.md:151-156` 明确只有最早未提交位置起的连续已完成前缀可立即提交，并覆盖 A 未完成、B 先完成后仍零写入的正反样本。 |
| M3 sink partial write 缺口 | **已关闭** | `acceptance.md:202-207` 在 response-start、`message_start`、block 与 terminal 的多个 offset 注入短写／RST／取消，分别记录客户端 bytes 与代理 frontier，并禁止 uncertain 后重发或成功 terminal。 |
| M4 raw capture 与 SDK／transport 同源 | **已关闭** | `acceptance.md:285-312` 强制 recorder 位于产品 SDK、自动 retry、parser、chunk merger 与 error normalizer 之前；SDK 结果仅作第二条兼容观察。 |
| M5 SDK 兼容冒充 strict grammar | **未完全关闭，形成下列 R2-M1** | `acceptance.md:314-326` 已正确拆成 CAL-04 strict validity 与 CAL-05 SDK compatibility，但 strict expected 的外部冻结来源仍未落地。 |

## 事实性发现

### 1. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:314-319` — CAL-04 引用了不存在且未绑定来源的“冻结 grammar table／fixtures”

**问题**：CAL-04 声称 strict state machine 的 expected 来自“冻结 Anthropic SSE grammar fixtures”与“冻结 grammar table”，但文档没有给出该 table／fixture 的内容、文件路径、内容哈希、官方协议版本或可复现生成来源。仓内针对 `grammar table`、`grammar fixture`、`strict grammar` 与 CAL-04 的全文搜索只命中 acceptance 自己及上一轮报告，没有找到独立冻结资产。CAL-05 与官方 SDK 的职责虽已正确分离，CAL-04 的 expected 仍只能由未来测试作者现场创造。

**证据或失败场景**：第一位执行者可以自行把“index 必须连续”“signature delta 的精确位置”“error 与 success terminal 的完整互斥关系”写入测试 table；另一位执行者也可以基于不同协议理解写出另一张 table。两者都满足“不是产品 parser、不是 SDK”的表面条件，却会对同一 feed 给出相反 verdict。对 strict oracle 自身做 mutation 只能证明它遵守了自己写下的 expected，无法证明 expected 对应冻结外部合同；因此上一轮 M5 的同源问题只是从 SDK 移到了未溯源的测试 fixture。

**修复建议**：在 acceptance 中直接冻结最小完整 grammar table，或绑定一个独立资产的路径＋内容哈希＋协议来源／版本。至少明确顶层事件顺序、block index 分配规则、各 block type 允许的 delta type与顺序、signature delta 位置、terminal／error 互斥、零 content 和 post-error 行为；再要求 CAL-04 manifest 绑定该内容版本。若其中某条无法从已接受 Spec 或官方协议确定，该条保持 `UNVERIFIED`，不能由测试作者补成 policy。

### 2. [major] `docs/agents/anthropic-responses-bridge/acceptance.md:223-228` — 去掉 16 MiB 专门 gate 时遗漏了 Spec 要求的普通 per-request aggregate buffered-bytes gate

**问题**：REL-06 已正确禁止 `>16 MiB` 专门 fixture、阈值和状态分支，但它只要求所有对象进入同一个 global reservation／resident 计账，并测试全局压力下拒绝新 admission。当前 Spec 在 `spec.md:443-451` 另行要求 `per-request buffered bytes` 与 `global buffered bytes` 都是必须存在且可观测的普通 limit 类别；acceptance 没有断言单个已接纳请求跨多个 draft、completed blocks、预渲染 envelope 与 History 移交对象累计超过其普通 request-level budget 时的行为。

**证据或失败场景**：实现可以只做进程全局 reservation，不设或不执行 per-request aggregate limit。只要全局尚有容量，一个请求就能持续占用绝大多数 resident bytes；REL-06 的现有 slow-consumer、并发、charge／release 与全局 admission 断言仍可全绿。反向地，为补缺口而重新引入 16 MiB single-block cap 又会违反最新裁决。缺失的不是“大 block 专门政策”，而是与大小类别无关、对每个 request 聚合 resident bytes 生效的普通公平性／资源边界。

**修复建议**：在 REL-06 增加普通 request-level aggregate reservation gate：以多个不同普通大小的 blocks 和多个 resident owner 累积到配置化 per-request budget，断言超额前正常背压／继续，达到普通 request limit 后产生稳定 capacity／limit 终态、停止继续读取、不提交 partial block、释放计账且不影响其他请求；同时注入“只检查 global、不检查 request aggregate”与“按单个 block／16 MiB 分支”的两种相反缺陷。测试参数不得把 16 MiB 设为语义边界，也不得据此引入专属 metric 或状态机。

## 主观建议

无。以上两项都会让验收 expected 或必需资源边界缺失，均属于事实性 major；未发现 blocker。

## 最终结论

上一轮 2 个 blocker 已关闭，5 个 major 中 4 个已完整关闭，strict／SDK 分离项完成了职责拆分但尚缺独立冻结 grammar 来源。本轮另发现普通 per-request aggregate buffered-bytes gate 在移除 16 MiB 专门路径时被一并遗漏。

**当前 acceptance 尚不能作为最终放行 oracle；修复 R2-M1 与 R2-M2 并完成独立复评后，可进入 oracle 放行判断。无论规范何时放行，bridge 候选实现都必须继续标记为 `UNVERIFIED`，直到规范要求的正确样本、单侧缺陷注入、确定性 live canary、有效 raw capture provenance、local fault 与 route-level delivery gates 全部取得可复现实证。**

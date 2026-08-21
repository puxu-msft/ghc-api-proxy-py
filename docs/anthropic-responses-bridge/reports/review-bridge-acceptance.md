# Anthropic Responses bridge acceptance 独立评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py/docs/agents/anthropic-responses-bridge/acceptance.md`；对账其引用的五份 SHA-256 快照、同主题 `spec.md` 与 `architecture.md`，但不把当前实现结构或参考实现行为当作正确性 oracle。
- **总体 verdict**：**存在 blocker**。当前规范不能作为最终放行 oracle；先修复 2 个 blocker，并关闭下列 major 后再进入验收资产实施。
- **blocker 数**：2。
- **major 数**：5。
- **基线证据**：同一次 shell 调用中的目录 gate 与 HEAD gate 均通过，仓库为 `/home/xp/src/ghc-api-proxy-py`，HEAD 为 `47d9ef101c4b81ac70d805b1da157b34d021d33d`；文档声明的五个 SHA-256 与当前对应临时文件逐项相等。

## 双视角覆盖证据

- **机械核对**：逐项映射 C1～C7；清点 request、nonstream、stream、block、pre/post commit、no-dup/no-loss/order、tool、reasoning/signature、usage、error、retry、cancel、backpressure、HTTP、WS、History、hooks、approval、tokenization，表面主题均有 gate；对账每个 gate 的正确样本、目标缺陷、执行层与通过判据；复核五份输入快照哈希；把 `acceptance.md` 的 expected policy、commit 语义和最终 `PASS` 条件与 `spec.md` 的未决 A～E 分叉及 `architecture.md` 的顺序／sink 语义交叉核对；为 fake、真实上游 capture、Anthropic SDK consumer 和产品 converter 追踪 producer、观测点与共同上游。
- **第一人称执行模拟**：模拟实现者依次落地 route selection、request conversion、nonstream、stream assembler、block sequencer、retry、HTTP／WS、lifecycle 与 calibration；重点走了 unknown capability 的两种合法政策、A 未完成而 B 先完成、signature 共享 codec 同步变异、完整 batch 写到一半断链、真上游无法按需制造 500／truncation／queue pressure，以及官方 SDK 对非法 SSE 宽松接受的分支。

## 事实性发现

### 1. [blocker] `acceptance.md:13` — 宣称 oracle 完整，但多个 expected 仍由未裁决政策决定

**问题**：文档把“验收 oracle 已完整定义”作为当前状态，但 REQ-01、REQ-02、REQ-03、NS-01、NS-02、REL-03、REL-06 等 gate 使用“unsupported”“按已声明策略”“repair”“continuation”“cap”等 expected，而同主题 `spec.md:414-440,470` 仍明确等待 B～E 裁决，A 的 semantic block 定义也尚未冻结。

**证据或失败场景**：实现者选择 unknown capability fail-closed 与 legacy permissive，或选择 strict failure 与 explicit degradation，均可能符合当前规格分叉；验收者却没有独立事实判断哪一个是正确样本。候选实现因而能反向选择 expected，或一个合法实现被判红，直接违反 C5、C6。该缺口也使目标缺陷注入的“失败原因来自目标机制”无法稳定判断，因为同一行为在另一政策下可能是预期行为。

**修复建议**：在规范中逐项绑定已接受 ADR／冻结 spec 的 policy id 与版本；未裁决项只能标记 `UNVERIFIED`，不得同时宣称 oracle complete。若确实允许多政策，正确样本必须显式输入 policy 配置，并为每个受支持政策给出不同的独立 expected 与负样本。

### 2. [blocker] `acceptance.md:285-295,337` — 必需真上游 gate 包含无法按需、确定性制造的状态，导致 `PASS` 可能永久不可达

**问题**：CAL-02 要求真 upstream 捕获 failed、error、正常 close 与可观测 truncation，CAL-03 要求真 upstream 产生 network failure 与 queue pressure；最终规则又规定任一 `POC-UPSTREAM` 未运行即 `BLOCKED`。调用方通常不能控制托管 upstream 在一次验收中产生 5xx、协议 truncation、特定 close code 或 queue pressure。

**证据或失败场景**：一个完全正确的 bridge 在稳定 upstream 上无法采到 truncation／failed／queue-pressure 样本，因此永远不能 `PASS`，这是确定的 false-red。反过来，用本地代理主动断链只能校准本地 fault injector 和客户端观察路径，不能证明“真 upstream 的 truncation 行为”，把它记作真 capture 又会形成假证据。该问题直接违反 C6，并阻断最终放行。

**修复建议**：把 gate 拆成三类：可确定调用的 live canary、来自真实事件且带 provenance 的版本化 capture corpus、可确定执行的本地 transport fault injection。只有上游明确提供触发机制或官方 fixture 的状态才设为每轮必需 live gate；不可控异常由已认证 capture 回归加本地 fault gate覆盖，并规定 capture 过期／缺失时的精确 `UNVERIFIED` 范围，而不是让整个验收永久不可完成。

### 3. [major] `acceptance.md:89-92` — signature 的 producer→echo→consumer 闭环仍可能是同源 oracle

**问题**：REQ-05 要求真实 response converter 的输出原样进入 request converter，但没有要求 producer 与 consumer 的 carrier 格式 oracle 独立，也没有规定共享 codec 只能单侧变异。

**证据或失败场景**：若 producer 与 consumer 共用 sentinel／base64url／version helper，一次共享 helper 变异会同时改变编码与解码；`encrypted_content` 仍可 byte-exact round-trip，整个 gate 保持绿色。真 upstream 只看到恢复后的原始 ciphertext，也无法发现 carrier 格式、旧版本兼容或 foreign-signature 边界已经被共同改写。这正是“两个路径最终追到同一上游”的同源 oracle。

**修复建议**：冻结由测试侧独立生成的逐版本 carrier vectors、旧版本兼容 vectors、foreign／损坏 vectors及其 exact bytes；分别对 producer-only 和 consumer-only 注入目标缺陷。报告 provenance 图，明确两侧 producer、观测点和共同 helper；共享 helper 变异不能算此 gate 的有效红色控制。

### 4. [major] `acceptance.md:152,156-159` — “每个完成 block 立即可见”与原序提交在合法交错流上矛盾

**问题**：STR-02 无条件要求每个完成 block 立即可见；STR-03 又要求按 semantic input order 精确提交。若先出现的 A 尚未完成、后出现的 B 已完成，B 不能立即提交，否则必然重排。

**证据或失败场景**：执行合法交错序列 `A.start → B.start → B.done` 时，遵守 STR-02 会先暴露 B，违反 STR-03；等待 A 则违反 STR-02 的“立即可见”。`architecture.md:308-313,329` 已明确 commit sequencer 应让 B 等待连续前缀，因此当前文字会把正确实现判成 false-red。

**修复建议**：把“立即”限定为“该 block 已完成且它之前的 semantic blocks 均已完成时，连续可提交前缀立即可见”。新增正样本 `A incomplete／B complete` 时零写入，随后 `A complete` 后按 A、B 提交；缺陷注入为按完成顺序提交 B。

### 5. [major] `acceptance.md:149-152,193-196,338` — commit gate 漏掉 sink 部分写入这一跨判据缝隙

**问题**：STR-02 验证 block 完成前不写，REL-03 验证上游在下一 block 中途失败，最终清单要求 route-level commit frontier 实证；但没有 gate 在完整 block 已 materialize、sink 开始写、ack／yield 完成前注入下游写失败。

**证据或失败场景**：完整 envelope 可能已向 socket 写出前半段后连接失败。若 frontier 仍未推进而 driver 重写整个 batch，会重复已见前缀；若提前推进，则会把半个 envelope 记作 committed 并造成 loss。两边现有 gate 都可绿色，因为 block 在写前确实完整、故障也不是 upstream mid-block。`architecture.md:317-319,357-359` 已承认网络分片与 `delivery-uncertain`，但 acceptance 没有把该状态变成 oracle。

**修复建议**：增加 `AUTO-SOCKET` sink-failure gate，在 block envelope 的多个 byte offset 注入断开／短写；断言不得 retry 同一 batch、不得发送 success terminal，History 为 `delivery-uncertain`／failed，frontier 与实际已观察 bytes分别记录且不互相冒充。此 gate 的目标不是声称 TCP 原子写，而是防止不确定交付被错误分类成可重试或成功。

### 6. [major] `acceptance.md:278-295` — fake 校准虽指向真 upstream，但 capture 观测链未要求与产品 transport／SDK 独立

**问题**：CAL-01～03 要求真实 capture provenance，却未规定 raw observation 位于 SDK 自动 retry、解析、chunk 合并和错误归一化之前，也未禁止使用与产品相同的 Responses SDK／transport recorder 生成 fixture。

**证据或失败场景**：若 capture 与产品都经过同一 SDK，该 SDK 可合并 SSE chunks、补 retry、把 close 转成统一 exception 或丢弃未知字段；fake 精确重放的是已被同源归一化的结果，fake parity 与产品测试全部绿色，但真实 wire 差异已在共同上游被抹掉。仅写 upstream/model/SDK revision 不能证明独立性。

**修复建议**：为每类 capture 强制 provenance 图：真实 upstream 是 producer，独立 raw HTTP／WS recorder 是观测点，fixture generator 只做可审计脱敏；记录 recorder revision、自动 retry 关闭状态、raw status／headers／frames／close 与内容 hash。产品 SDK 的解析结果只能作为第二条兼容性观察，不能成为 raw fixture 的唯一来源。

### 7. [major] `acceptance.md:299-302` — 把官方 Anthropic SDK consumer 当成协议有效性的唯一 oracle 会漏掉双方共同接受的非法序列

**问题**：CAL-04 要求项目 strict consumer 与官方 SDK 对非法 feed 同样拒绝，并称真实 SDK 是独立 consumer oracle；但 SDK 是兼容性 consumer，不保证严格验证所有 Anthropic SSE grammar 不变量。

**证据或失败场景**：若官方 SDK 宽松接受 duplicate stop、delta-after-stop 或 duplicate terminal，项目 strict consumer 被注入同样的宽松行为后，两者结果一致，缺陷注入仍绿；若规范强制项目拒绝而 SDK 接受，“同样拒绝”又成为不可满足的 false-red。SDK 独立于产品 parser，不等于它是协议合法性的独立来源。

**修复建议**：分离两个 oracle：由冻结的 Anthropic wire grammar／官方协议文档驱动 strict validity gate，SDK 只做真实客户端兼容 gate。非法序列的 expected 由 grammar fixture 独立给出；SDK 的实际接受／拒绝仅记录兼容行为，不覆盖 strict verdict。

## 主观建议

无。以上均为会改变 gate 判别力或最终可达性的事实性问题。

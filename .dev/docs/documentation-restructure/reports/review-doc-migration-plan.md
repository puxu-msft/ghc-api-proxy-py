# 文档重组计划独立评审

## 评审摘要

- **评审范围**：`/home/xp/src/ghc-api-proxy-py/docs/agents/documentation-restructure/plan.md`，基于仓库 `HEAD 47d9ef101c4b81ac70d805b1da157b34d021d33d`；同时只读核对 `docs/2604-rewrite/**/*.md`、旧冲突合同、现存相对链接和项目质量门声明。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：5。
- **机械核对覆盖证据**：用 `fd --type f --extension md` 与 Python `Path.rglob('*.md')` 两种方法独立枚举规划 HEAD 下的源集合；结果均为 42 份。机器解析第 5 节得到 42 行、42 个唯一旧路径，`MISSING=[]`、`EXTRA=[]`、`DUPLICATES=[]`。逐项对账 C1～C8，并扫描阶段 0～11 的验收与提交条款、项目 `pyproject.toml`／`README.md` 中的 Ruff／Pyright strict／pytest 门，以及旧目录内 311 个当前可解析的相对 Markdown 链接。规划数字口径均为仓库根目录、上述 HEAD 和 `docs/2604-rewrite/**/*.md`。
- **第一人称执行覆盖证据**：模拟了“阶段 0 建 oracle→阶段 1 提交后暂停→后续恢复→阶段 11 复验”的恢复流程；模拟了一个源文件同时向阶段 1 最小 spec、阶段 4／5详细文档和最终 archive 供料的移动流程；模拟了保留旧 `ROADMAP.md` 直到阶段 9 时读者直接从搜索结果进入旧合同的路径；模拟了“意外复制两份正文但映射和链接仍全绿”的 false-green；模拟了移动含相对路径与 fragment 的旧文件后，文件存在检查对错误 anchor 假绿、不同 slug 规则对正确链接假红的两种路径。

## C1～C8 结论

| 命题 | 结论 | 证据摘要 |
|---|---|---|
| C1 用户三层目录裁决精确体现 | 通过 | `plan.md:29-35` 精确区分 `docs/`、`docs/agents/<topic>/`、`archive-<date>/`，并排除 `docs/tmp/**` 进入正式引用链。 |
| C2 42 份源文件唯一去向、无遗漏／重复 | **部分失败，见 major 3、4** | 旧路径集合是一一对应的，但跨阶段最终移动 owner 不唯一，且验收不能识别目标树中的意外正文副本。 |
| C3 迁移渐进、不抢产品主线 | 通过 | `plan.md:39-46`、`234-430` 和 `519` 按产品优先级切片，阶段 1 后明确暂停。恢复证据持久性另见 major 1。 |
| C4 每阶段有链接／事实／状态验收与独立提交 | **失败，见 major 1、2、5** | 统一协议覆盖事实与链接，但阶段 0 的 oracle 不持久化，阶段 1 pathspec 不可确定，fragment 控制不完整。 |
| C5 `docs/tmp` 报告不提交 | 通过 | `plan.md:35`、`204`、`225`、`519` 多重排除；当前 `docs/tmp/` 也保持未跟踪。 |
| C6 buffering 与 Anthropic→Responses 优先级不被旧文档推翻 | **迁移窗口失败，见 major 2** | 最终目标正确，但阶段 1～8 仍可直接命中未加取代头的旧 `ROADMAP.md`。 |
| C7 不因成本／ROI／YAGNI 删功能 | 通过 | `plan.md:60-62`、`395-410`、`513-515` 明确保留并要求无裁决项回主会话。 |
| C8 不自行裁决未决 buffering 细节 | 通过 | `plan.md:58`、`473-482` 把 block 定义、重试、History 时点、预算、背压、取消和 envelope 全部列为后续门控。 |

## 事实性发现

### 1. [major] `plan.md:191-198, 215-230, 442` — 阶段 0 的 oracle 被要求“可复现”，却只存在系统临时目录且不提交，暂停或环境清理后阶段 11 无法复用

- **问题**：统一协议要求每个切片固定并复跑同一 oracle；阶段 0 又把 link checker、状态词扫描和 route／settings／schema 探针只放系统临时目录，并明确无提交；阶段 11 却要求再次运行“阶段 0 经过双向控制的临时 link checker”。计划还要求阶段 1 后暂停，正好跨越最容易丢失临时文件的恢复边界。
- **证据或失败场景**：执行者完成阶段 0 和阶段 1 后退出会话或系统清理临时目录。恢复到阶段 2 或阶段 11 时，只剩报告中的“曾通过”自述，没有 checker 内容、fixture、版本或 SHA-256，无法证明复跑的是同一判据，也无法复核当时的正反控制。阶段 0 因无仓库产物，也不满足 C4 的“每阶段独立提交”字面要求。
- **false-green／false-red**：后继者可临时重写一个更弱 checker 并得到假绿；也可能用不同 Markdown slug／archive 规则重写一个更严 checker而产生假红。
- **修复建议**：把可复现的 checker、fixture、期望集合和执行说明作为非临时开发资产放入对应 `docs/agents/documentation-restructure/` 或项目既有验证目录，并在阶段 0 形成独立提交。运行输出可以留在系统临时目录，`docs/tmp/**` 仍保持不提交。若用户坚持阶段 0 零提交，则至少在阶段 1 提交中冻结脚本内容、fixture 和 hash，并把阶段 0 明确改成“准备步骤”而非声称每阶段都独立提交。

### 2. [major] `plan.md:243, 397, 420-426` — 渐进窗口没有给仍留在旧目录的冲突文档加临时取代标记，旧优先级会在阶段 9 前继续与新入口并存

- **问题**：阶段 1 只笼统迁移“本阶段直接拥有”的 Anthropic／streaming 源；旧 `BACKLOG.md` 和 `ROADMAP.md` 明确延后到阶段 9，统一归档头则到阶段 10 才要求。计划没有要求给暂留在 `docs/2604-rewrite/` 的冲突文件添加迁移期 banner，也没有在阶段 1 明确让 `README` 对旧目录作不可作为真相源的可见声明。
- **证据或失败场景**：`docs/2604-rewrite/streaming-resilience.md:7` 仍写“默认路径永远是零缓冲直通流”，该文件第 225 行明确“不采纳块级缓冲重试”；`docs/2604-rewrite/ROADMAP.md:51,58-59` 仍把整响应缓冲设为 opt-in／默认关，并把块级缓冲标成“缓存／延后”。即使阶段 1 移走 streaming 文档，旧 `ROADMAP.md` 仍会一直存在到阶段 9；从仓库搜索或旧交叉链接直接进入它的读者不会先经过新 `README`，因而仍会读到推翻 C6 的优先级与合同。
- **修复建议**：阶段 1 在不搬动尚需后续提炼的源文件前，先给所有仍保留的旧入口和冲突源加统一迁移期头，明确“非当前真相源”、现行入口、已被取代的 buffering／优先级裁决和计划移交阶段；该 banner 应随阶段 1 一起提交并纳入状态词 oracle。阶段 9／10 最终归档时再替换成永久 archive 头。

### 3. [major] `plan.md:207, 240-243, 294-331` — 阶段 1 的源文件移动 owner 不可机械确定，并与阶段 4／5 对同一资料的后续“归位”重叠

- **问题**：统一规则说跨多个阶段的源文件必须保留到“最后一项内容”完成后再由最后阶段移动，但阶段 1 只写“迁移／归档本阶段直接拥有的 Anthropic 与 streaming 源文档”，没有列精确旧路径或每个源的 last-owner。与此同时，阶段 1 要从 feature negotiation、header forwarding、thinking、tool use 等主题建立最小 spec；阶段 4 要迁移 `TOOL_USE.md`，阶段 5 又要归位 feature negotiation、header forwarding 和 thinking 的详细资料。
- **证据或失败场景**：执行者若把 `feature-negotiation.md`、`header-forwarding.md`、`thinking-pipeline.md`、`tool-use.md` 当成阶段 1 “直接拥有”并移入 archive，阶段 4／5 后续取材位置与 pathspec 失真；若全部不移动，阶段 1 的“迁移／归档”验收又没有一个可机械判断的预期集合。两名执行者可作出相反选择且都声称遵守正文，破坏 C2 的唯一 disposition 和 C4 的精确独立提交。
- **修复建议**：在第 5 节为 42 个源增加 `extract phases`、`final move phase` 和精确 stage pathspec 三列；每个源只能有一个 `final move phase`。阶段 1 的“涉及文件”直接列出确切旧路径，阶段 4／5 只消费仍在旧位置的源或已经明确的 archive 路径，不再使用“直接拥有”“对应旧内容”之类需自判的范围词。

### 4. [major] `plan.md:19, 223, 421, 426` — C2 的验收只证明旧路径集合被处置，不能证明目标树没有未标注正文副本

- **问题**：机器核对确认第 5 节对 42 个旧路径确实一一覆盖，但阶段 0 和阶段 10 的 oracle 都是“冻结源集合与映射／新位置精确相等”。它们没有目标树 provenance、内容 hash 或重复候选检查，无法兑现完成定义中的“无未标注正文副本”。
- **证据或失败场景**：把某个旧文件移动到规定 archive，同时意外再复制一份到另一个 topic archive；删除旧源并保持两份链接都有效。此时 42 个源路径全部有 disposition、旧目录为空、链接全绿、状态词也可全绿，现有 gate 仍会通过。这是确定可构造的 false-green，而不是表述偏好。
- **修复建议**：阶段 0 冻结每个源文件的 content hash 和唯一 canonical archive destination；阶段 10 对整个 `docs/agents/**/archive-*` 扫描相同 hash，并对近似正文块产生候选清单。精确重复必须只有 canonical destination 一份；语义提炼产生的重叠应携带 provenance／现行入口而不是被误判。对重复候选逐条 disposition，并加入一个“复制两份但路径映射仍正确”的缺陷注入控制。

### 5. [major] `plan.md:115, 225-226, 251, 420-422, 467` — 相对链接 gate 未冻结 fragment 与重定位语义，既可能漏掉错误 anchor，也可能误报正确的 renderer-specific 链接

- **问题**：计划要求迁移时修链接、每阶段链接全绿，并对“断链”“临时目录引用”“合法 archive 引用”做控制，但没有声明被测边界是文件存在、Markdown heading fragment、GitHub line fragment，还是特定 renderer 的完整解析结果；也没有针对移动后相对基准目录变化的 fixture。
- **证据或失败场景**：在规划 HEAD 下扫描到 311 个当前文件级可解析的相对 Markdown 链接。例如 `docs/2604-rewrite/lib-survey/HANDOVER.md:21` 使用 `../project-structure.md#L444`，`docs/2604-rewrite/lib-survey/domain3-streaming-sse-ws.md:22` 使用中文 heading fragment；大量顶层文件又以同目录相对路径互链。移动到不同 topic/archive 后，链接文件可能仍存在但 fragment 因标题修真而失效，纯存在检查会假绿；反之，若 checker 自行采用与仓库渲染器不同的 Unicode slug 或不支持 `#Lnnn`，正确链接会假红。
- **修复建议**：先声明链接 gate 的对象和 renderer：至少分别验证相对路径目标、heading fragment、仓库宿主支持的 line fragment。增加三组双向控制：移动文件后未 rebasing 的相对链接必须红；标题变更后旧 fragment 必须红且新 fragment 绿；合法 Unicode heading 与合法 archive／line fragment 必须绿。每阶段对本切片所有 moved files 输出 before→after link target 清单，最终阶段再做全仓链接图对账。

## 主观建议

无。以上均是可复现的计划正确性或验收判别力缺口，不是风格偏好。

## 结论

未发现 blocker。C1、C3、C5、C7、C8 的方向与约束清楚；C2 的 42 份旧路径集合也已机械证明完整且唯一。当前不应直接执行，因为 5 条 major 会让暂停恢复、迁移窗口合同、跨阶段移动、重复正文和相对链接验收出现可确定的假绿／假红。修复后应重新评审更新版计划，重点复跑 42 项 stage-owner 对账与 link-checker 双向控制。

# `.dev` git re-root 前最终独立就绪审阅

## 评审范围

- **目标**：独立确认 `.dev/docs` 在 2026-09-08 合并、归档与 15 个候选主题退役后，是否具备创建 `.dev` git checkpoint、继而进入 dotdev re-root/worktree 挂载的文档前置条件。
- **被检对象**：`.dev/docs` 当前文件树；`.dev/docs/dotdev-repository-repair/README.md` 与其 2026-09-08 evidence index；排除 `reports/`、`history/`、`archive*` 与 repair control-plane 后的 retained living Markdown；`tests/int/recorded/cassettes.py` 中 vcrpy 历史指针；作为 checkpoint/re-root 承重接缝的 active `.dev/README.md`、active/nested tree 与只读 Git 状态。
- **判据来源**：本次审阅委托列出的六项核验要求与顺序门；repair README/ledger/report 只作为待独立核验的 claim 与 point-in-time evidence，不从其自述反推判据。
- **明确不在范围内**：执行 `.dev` checkpoint、re-root/worktree 挂载、产品测试、retained topics 自身未完成工作的验收；任何移动、删除、修复、`git add`、commit 或 push。
- **审阅方式**：只读文件树与 Git 状态；自行解析 Markdown 相对本地链接及 fragment；对 ledger 计数、迁移报告和 current living owner 做交叉对账。

## 总体 verdict

**NEEDS-FIX。** 当前不应把这棵树建立为“最终、可进入 re-root”的 `.dev` checkpoint。发现 **3 major、2 minor、0 blocker**：retained living/current consumers 仍指向已经退役或删除的 2604 原件；repair README 的 59-link evidence index 漏列 TUI 的 3 项迁移记录；即将成为 re-root 顶层入口的 `.dev/README.md` 仍描述退役前目录与相反的 repository-root 模型。前述三项必须先闭合并重跑 final scan。两个 minor 不单独阻断结构重构。

若“checkpoint”仅指明确标成 **intermediate/known-broken** 的保险提交，技术上当然可以保存任何状态；本 verdict 否定的是 repair README 所要求、可作为 re-root 前门的**最终文档 checkpoint**。

## Blocker 数

**0**

## Findings

### PRR-02 — 退役/清空后仍有 current/retained consumers 指向已不存在的 2604 与 top-level tmp 原件

- **severity**：major
- **status**：open；**阻止创建最终文档 checkpoint**
- **primary_location**：`.dev/docs/tui/spec.md:9,13`
- **related_locations**：
  - `src/app/observability/request_log.py:3`
  - `src/app/pipeline/driver.py:432`
  - `.dev/docs/anthropic-responses-bridge/research.md:63`
  - `.dev/docs/upstream/retry-and-continuation/evidence/probe-reasoning-item-control.py:11,46`
  - `.dev/docs/upstream/retry-and-continuation/README.md:40`
  - `.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md:61,73,94` 及 EF-2604-TUI／EF-2604-TOKEN 原子约束
  - `.dev/docs/tui/history/260908-residual-history-migration.md`
- **claim**：15 个候选目录虽已从 filesystem 消失、top-level `tmp/` 虽已无 regular files，但 consumer 改链没有全部与原件迁移原子完成。当前 TUI Spec、两个 production source comments 仍把不存在的 2604 路径作为 reasoning/provenance；bridge `research.md` 还以两个已不存在的旧路径支撑“已独立核验”的结论；current upstream evidence index 引用的 probe 仍从已清空的 top-level tmp child 读输入。
- **evidence**：
  - `tui/spec.md:9` 引用 `docs/2604-rewrite/telemetry-observability.md`，`:13` 引用 `docs/2604-rewrite/lib-survey/SELECTIONS.md`；canonical originals 已在 `.dev/docs/tui/history/2604-rewrite/`。
  - `request_log.py:3` 仍引用 `.dev/docs/archived-2604-rewrite/DESIGN.md`，其 canonical original 已迁至 `.dev/docs/tui/history/2604-rewrite/DESIGN.md`。
  - `driver.py:432` 仍引用 `.dev/docs/archived-2604-rewrite/tokenization.md`，其 canonical original 已迁至 `.dev/docs/token-counting/history/2604-rewrite/tokenization.md`。
  - residual ledger 明确要求 EF-2604-TUI、EF-2604-TOKEN “移动和改链同一变更”；TUI migration report 自己明确说因路径所有权限制而**没有**执行 consumer 改链。当前 filesystem scan 证明该后续没有发生。
  - `anthropic-responses-bridge/research.md:63` 仍引用 `/home/xp/src/ghc-api-proxy-py/docs/2604-rewrite/tool-use.md` 与 `request-pipeline.md`。前者已有 `.dev/docs/hosted-web-search/history/2604-tool-use.md` successor；后者已按 residual ledger 删除且没有同名原件。该段仍把两者写成当前论证依据，不能以“不是 Markdown link”排除。
  - `upstream/retry-and-continuation/README.md:40` 把 `evidence/probe-reasoning-item-control.py` 作为 current evidence；该 probe 的 `EV` 仍硬编码 `.dev/docs/tmp/260821-max-tokens-evidence` 并读取其 `scan_hits.txt`。top-level tmp child 已不存在，canonical evidence 已在 `upstream/retry-and-continuation/evidence/max-tokens-block-completeness/scan_hits.txt`，所以当前 probe 会在读输入前失败。
- **impact**：当前 tree 不满足“retired path/basename/top-level tmp consumer 清零”的结构门；若现在 checkpoint，会把已删除 source 与仍在消费它的 retained/current 文档、代码注释和可复现 probe 一起冻结，re-root 后路径不会自行恢复。普通 Markdown path parser 报 `retired direct links=0`、`tmp direct links=0` 只证明没有 `[](...)` 形式的直接 link，无法覆盖 inline-code literals 与 executable paths，绿灯缺乏本门所需分辨力。
- **minimal_next_step**：在 checkpoint 前完成 4 个已有 2604 canonical destination 的精确改链，并把 probe 的 `EV` 改为 topic-local canonical evidence directory；对 `research.md:63` 将 `tool-use` 指向 retained canonical history，并按 current authority 重述或移除已删除 `request-pipeline.md` 的证据依赖。随后对 retained living Markdown、retained evidence assets、`src/`、`tests/`、`pyproject.toml` 同时重跑 retired exact path、legacy alias、top-level tmp child、unique basename 与 Markdown target 扫描。

### PRR-03 — README 的 residual evidence index 少了 TUI 3 项迁移记录

- **severity**：major
- **status**：open；**阻止创建最终文档 checkpoint**
- **primary_location**：`.dev/docs/dotdev-repository-repair/README.md:38`
- **related_locations**：
  - `.dev/docs/tui/history/260908-residual-history-migration.md`
  - `.dev/docs/dotdev-repository-repair/reports/260908-final-ledger-refresh.md:15,34`
  - `.dev/docs/dotdev-repository-repair/subtopics/260908-candidate-residual-disposition.md`「按 retained target topic 汇总」
- **claim**：README 所列“residual canonical-history implementation evidence”只有 9 份 `reports/260908-residual-history-migration.md`，合计覆盖 180 项，不是 ledger 的 183 项；缺失的 3 项由 TUI topic 下另存于 `history/` 的迁移报告承载。因此当前 59 个 local links 均存在，但 evidence index 不完整。
- **evidence**：从 candidate residual ledger 独立解析得到 canonical-history rows=183，按 destination topic 为 17+33+7+4+84+4+12+6+3+13。README 链接的 9 份同名 residual reports 覆盖除 TUI 外的 180 项；`.dev/docs/tui/history/260908-residual-history-migration.md` 另列 `DESIGN.md`、`telemetry-observability.md`、`lib-survey/SELECTIONS.md` 三项，且 3 个 destination 均存在、SHA-256 与报告一致。该报告没有被 README 的 59 links 或 final-ledger-refresh 的“9 份 reports”表述纳入。
- **impact**：`183/183` 的 filesystem 结果成立，但 current execution entry 不能仅凭其链接 evidence 完整复核；59-link“missing=0”掩盖的是**缺链接**而非断链。对要求“可审查、可恢复”的 checkpoint，这是 control-plane 完整性缺陷。
- **minimal_next_step**：把 TUI migration report 加入 README residual evidence index，并把“9 份 reports”改成能准确表达“9 份 reports + 1 份 TUI history migration record”的措辞；更新 local-link count 后再复核。

### PRR-05 — 即将成为 re-root 顶层入口的 `.dev/README.md` 仍描述退役前目录与旧存储模型

- **severity**：major
- **status**：open；**阻止创建最终文档 checkpoint**
- **primary_location**：`.dev/README.md`「与主仓库及远端分支的关系」「已有话题」
- **related_locations**：
  - `.dev/docs/dotdev-repository-repair/README.md`「唯一剩余结构性顺序」
  - `.dev/docs/reasoning-carrier/tracking.md`
  - `.dev/docs/timeout-408/status.md`
- **claim**：active `.dev/README.md` 是 re-root 后仓库顶层会直接暴露的入口，但它仍把 remote canonical tree 定义为“只含 `.dev/` 前缀、不得把本地仓库根直接推到 `origin/dotdev`”，并在“已有话题”中列出已退役的 `documentation-restructure`、`git-housekeeping`、`pipeline-rewrite-parity`、`architecture-audit`、`early-verification`、`archived-2604-rewrite`、`docs-tmp-migration` 等目录；同时把 `reasoning-carrier` 写成 source unreachable/main 未集成，把 `timeout-408` 写成当前 checkout 尚未装位实现。
- **evidence**：current active `.dev/` 顶层已有 `README.md`、`docs/`、`exp/` 等目标树，而当前 dotdev `HEAD` 顶层仅有嵌套 `.dev/`。repair README 明确要求 re-root 后分支顶层直接为 `docs/`、`exp/` 等；15 个 retired paths 的 `lstat` 均为 absent；`reasoning-carrier/tracking.md` 与 `timeout-408/status.md` 已在 2026-09-08 刷新为 current main 审计基线。根 README 与这三类事实同时冲突。
- **authority note**：根 README 还把旧 remote-root 模型归为“用户于 2026-09-04 选择”，但本次检查到的 control-plane/report 只有转述与 Git 结果，没有可逐字回指的用户一手原话；本报告不据此断言用户从未作过该选择，只是不继续把这条未能独立核实的归属当作阻止 current re-root 的更高权威。
- **impact**：若把 active root 直接纳入 checkpoint/re-root，它会立即成为错误的仓库入口，指导下一位操作者恢复旧的 prefix 模型并寻找不存在的主题。该缺陷不在 `.dev/docs` 的 59-link scan 内，但属于 checkpoint/re-root 接缝上的承重文档。
- **minimal_next_step**：在 checkpoint 前把根 README 的 repository/worktree 模型、topic inventory 与 reasoning/timeout 状态边界对齐到 current repair ledger；保留历史模型时明确标为 pre-reroot history，不再作为当前操作说明。

### PRR-01 — retained living 文档保留了一个失效的同文件 fragment

- **severity**：minor
- **status**：open
- **primary_location**：`.dev/docs/upstream/retry-and-continuation/decisions.md:117`
- **related_locations**：`.dev/docs/upstream/retry-and-continuation/deferred.md:303`
- **claim**：`decisions.md` 的 `22 之四` 链接被写成同文件 fragment `#22-之四-一条状态断言在写下时就已经过期`，但该文件没有对应 heading；实际墓碑 heading 位于 `deferred.md`。
- **evidence**：对 114 份 retained living Markdown 的 local/same-file fragment 按 GitHub heading slug 规则与目标文档 headings 对照，仅此 1 个 fragment 无匹配。全文搜索显示短语对应 heading 为 `deferred.md:303` 的 `### 22 之四. 一条状态断言在写下时就已经过期 —— 已移入教训文档（2026-08-27）`，而 `decisions.md` 仅有该引用。
- **impact**：读者从 current decisions 页无法跳到所指的 provenance/墓碑。它是 retained living link 完整性缺陷，但目标不落入 15 个 retired topic 或 top-level `tmp/<file>`，不会造成 retired consumer，也不阻断 checkpoint/re-root。
- **minimal_next_step**：在 checkpoint 前或后单独把链接目标改为 `deferred.md#22-之四-一条状态断言在写下时就已经过期--已移入教训文档2026-08-27`，并重跑 fragment 校验；不需要恢复任何 retired directory。

### PRR-04 — GHE residual migration report 的一项 SHA-256 抄写无效

- **severity**：minor
- **status**：open
- **primary_location**：`.dev/docs/ghe-device-flow/reports/260908-residual-history-migration.md:17`
- **related_locations**：
  - `.dev/docs/ghe-device-flow/history/copilot-token-identity/reports/260807-audit-token-identity-squash.md`
  - dotdev current `HEAD:.dev/docs/copilot-token-identity/reports/260807-audit-token-identity-squash.md`
- **claim**：该行的 before/after digest 均写为 62 个 hex 字符的 `d3e8aadb856e66aa7a8925b77f31a8cefd4dad6f36dd4a0c4bf22024a93e0b`，不是合法 SHA-256；current destination 的真实摘要为 `d3e8aadb856e66aa7a8925b77f31a8cefdad4dad6f36dd4a0c4bf22024a93e0b`。
- **evidence**：对 destination 直接执行 SHA-256 得到后者；对当前 `.dev` Git `HEAD` 与 index 中尚可读的原 source blob `:.dev/docs/copilot-token-identity/reports/260807-audit-token-identity-squash.md` 只读取证，也得到后者。故迁移原件实际字节一致，错误仅在报告摘要漏写 `ad`。
- **impact**：不会导致原件丢失，也不推翻 4/4 GHE destination/source 状态；但报告声称的机械完整性证据有一行不可验证，若不修会进入 checkpoint。
- **minimal_next_step**：在 checkpoint 前更正 before/after 两格的 digest，并重跑该报告四行摘要对账。

## 已通过项

- 文件树中 15 个指定 retired topic path 均不存在，且用 `lstat` 复核没有 dangling symlink：`architecture-audit`、`archived-2604-rewrite`、`copilot-token-identity`、`count-tokens`、`docs-tmp-migration`、`documentation-restructure`、`early-verification`、`empty-text-block`、`git-housekeeping`、top-level `history`、`hooks-subscription-migration`、`lifecycle-reorg`、`pipeline-rewrite-parity`、`sync-refs`、`test-infrastructure`。
- `httpx2-migration/` 与 `systemd-runtime/` 均仍存在；repair README 正确把它们列为 retained exceptions，没有把二者写进 15-topic retired set。
- `.dev/docs/tmp/` 目录存在，顶层 regular files 为 0；`interaction-context/spec.md` 与 `interaction-context/history/260907-interaction-context-design.md` 均存在。
- retained living Markdown 的相对本地 path targets 当前未发现缺失，且未发现指向 retired top-level topic 或 top-level `tmp/<file>` 的直接 Markdown link；fragment 例外见 PRR-01。
- residual ledger 的 183 个 canonical destinations 全部存在；10 份实际迁移记录（README 链接 9 份，加上遗漏的 TUI history report）中，182 个格式正确的 SHA-256 与 current destination 逐项一致。GHE 报告的 1 个 malformed digest 另待定级记录。
- 当前 dotdev `HEAD` 顶层仍只有 `.dev/`，active worktree 顶层则已有 `docs/`、`exp/`、`human-controlled-docs-candidates/`、`tools/` 等目标树；这与“checkpoint 后再 re-root”的现阶段形态一致，但也使根 README 与 nested/active tree 的逐路径核对成为 checkpoint 的必做门。

## Ledger、计数与报告对账

### Original top-level `tmp` ledger

从 `260908-tmp-final-disposition.md` 的 item rows 独立解析得到恰好 77 项：

| disposition | ledger | current observation | 结论 |
|---|---:|---|---|
| canonical history | 72 | 72 source absent；72 destination present；72 个 destination SHA-256 与各 2026-09-08 migration report 唯一记录逐项一致 | PASS |
| exact deletion | 4 | 4 source absent | PASS |
| interaction-context extraction | 1 | tmp source absent；living `spec.md` 与 history original 均 present | PASS |
| **合计** | **77** | **77/77** | **PASS** |

FRR-01 的额外 reasoning review 也已闭合记录层：tmp source absent，`reasoning-carrier/history/260908-reasoning-encrypted-include-review.md` present，SHA-256 `e290f8107afbdccdb2bafbf1c81a8b1ab3f0eb5f6034000194e1cc2d3e629c79` 与 migration report 一致；`tracking.md` 的 `RC-TF-01` 是明确 open 的 current test follow-up。

### FRR-02 residual ledger

从 `260908-candidate-residual-disposition.md` 的逐行表独立解析：

| disposition | ledger | current observation | 结论 |
|---|---:|---|---|
| canonical history | 183 | 183 destination present；182 个合法 report digests 与 destination 一致；剩余 1 项实际 destination 与 dotdev `HEAD`/index old-source blob 相同，但 report digest 抄错（PRR-04） | 内容 PASS；报告有 minor |
| exact deletion | 36 | 15 source directories 全部 absent，因此 36 exact sources absent | PASS |
| needs-user-decision | 0 | 无 | PASS |
| **合计** | **219** | **219/219 disposition 已实施** | **PASS** |

按 retained destination topic 的 183 项分布为 `anthropic-direct-request-shape=17`、`anthropic-responses-bridge=33`、`delivery-keepalive=7`、`dotdev-repository-repair=84`、`ghe-device-flow=4`、`graceful-shutdown=4`、`server-layout=12`、`token-counting=6`、`tui=3`、`upstream/retry-and-continuation=13`。正是 `tui=3` 没有进入 README 的 residual evidence index（PRR-03）。

### Repair README local links

- `markdown-it-py 4.2.0` 解析结果：local Markdown link occurrences=59，unique destinations=58，missing=0。
- 唯一重复 occurrence 是 `reports/260908-residual-history-migration.md`，一次作为 repair control-plane evidence，一次作为 repository-repair residual migration evidence；重复本身合理。
- “59/59 都能解析”成立，但不是 evidence index completeness 的证明：TUI migration report 根本不在 59 个 link 中，见 PRR-03。

## 执行顺序与结构门判定

repair README 的抽象顺序 **final independent scan → `.dev` git checkpoint → dotdev re-root/worktree mount** 正确，且没有把 re-root 提前到 checkpoint 前。但本报告就是第一步 final scan，其 verdict 为 NEEDS-FIX，所以当前不得进入第二步的 final checkpoint。

只读 Git/tree 观察进一步确认 checkpoint 本身必须是显式、逐路径操作：

- dotdev branch 为 `dotdev@862b137`，`HEAD` 顶层只有 `.dev/`；active `.dev/` 顶层则直接有 `README.md`、`docs/`、`exp/`、`human-controlled-docs-candidates/`、`tools/` 等目标内容。
- `git -C .dev status --short` 在本报告写入前共有 128 个聚合 entries：119 deleted、3 modified、6 untracked roots。该状态不是本次发现的新故障，而是 README 已预期要在 checkpoint 中逐路径对账的 nested-tracked/active-root 差异。
- nested `.dev/.dev/docs` 与 active `.dev/docs` 不是可机械互换的镜像：前者仍含 retired sources，后者含迁移后的 canonical histories/current updates。不得 bulk-copy 旧 nested tree 覆盖 active tree。

## 主仓 vcrpy 指针

`tests/int/recorded/cassettes.py:3` 已改为 `.dev/docs/server-layout/history/test-infrastructure/reports/260818-vcrpy-poc.md`，目标存在；旧 `.dev/docs/test-infrastructure/...` 指针已不在该文件。`git diff --check -- tests/int/recorded/cassettes.py` 通过。

该改动当前在**主仓**显示为 modified，而不属于 `.dev` Git checkpoint。它不是 re-root 的文档内容 blocker，但在实施 checkpoint/cutover 时必须作为跨仓接缝单独持久化或明确保留，不能误以为 `.dev` commit 会包含它。

## 结构重构 blocker 与 retained-topic 未完成工作的区分

### 会阻止当前 final checkpoint/re-root 的事项

1. PRR-02：retired/removed 2604 source 与已清空 top-level tmp child 仍被 retained/current consumers 使用。
2. PRR-03：repair current entry 的 183 项 evidence index 少 3 项 TUI migration record。
3. PRR-05：future repository-root README 仍描述旧 prefix 模型、退役 topic inventory 和过期 current status。

这些都是 repository structure/control-plane 的完整性问题；在它们闭合前，re-root 只会把错误路径和错误入口换一个根继续保存。

### 不阻止 repository structure re-root 的 retained-topic 工作

- `httpx2-migration` step 4 仍是 deferred/living：旧包 prose、当前 `httpx2`/`httpcore2` logger 筛噪及验证未闭合；`pyproject.toml:16` 仍正确指向其 Plan。这阻止**该 topic 退役**，不阻止保留该 topic 后 re-root。
- `systemd-runtime` S5 仍受真实 user-manager/delegated cgroup v2 环境门阻塞；static verify/direct-fd 不能替代。它阻止 **S5 PASS 与该 topic 退役**，不阻止保留该 topic 后 re-root。
- `reasoning-carrier` 的 `RC-TF-01` 仍 open/待独立复验。它是 test discriminability follow-up，不是 FRR-01 归档、候选目录退役或 re-root 的结构前置。

三项都被 current living owner 诚实保留，没有必要为结构重构伪装成“已完成”；结构要求只是不能误删、误归档或误称退役。

## 最小下一步

按依赖顺序：

1. 关闭 PRR-02：完成 4 个已有 2604 canonical destination 的 current consumer 改链，把 upstream evidence probe 改到 topic-local canonical evidence directory，并处置 bridge `research.md:63` 对已删除 2604 原件的证据依赖。
2. 关闭 PRR-03 与 PRR-05：把 TUI migration record 纳入 repair README/final-ledger evidence index；同步 future root `.dev/README.md` 的 repository model、topic inventory 与 current status。
3. 建议同批关闭两个不阻断 minor：修正 PRR-01 fragment 与 PRR-04 digest。
4. 重跑同一 final scan：15 paths（含 symlink）、top-level tmp regular files、retained CommonMark links/fragments、retired exact paths/legacy aliases/unique basenames、10 份 residual evidence、root README current-state 对账。
5. final scan 通过后，才创建明确的 `.dev` checkpoint；逐路径比较 nested tracked tree 与 active root，不用旧 nested tree bulk overwrite 新 tree；同时单独处理主仓 `cassettes.py` 的持久化边界。
6. checkpoint 可审查、可恢复后，才执行 dotdev re-root/worktree mount，并按 README 验收 direct-root layout、ancestor chain、mount 与主仓 `git status` 可见性。

## 搜索面与执行记录

- 目录枚举：`.dev/docs` 顶层目录、15 个 retired paths、2 个 retained exceptions、`tmp/`、`interaction-context/`。
- Markdown 范围：被检树在写入本报告前共 1176 份 Markdown；按委托排除 `reports/`、`history/`、任一 `archive*` component 与整个 `dotdev-repository-repair/` control-plane 后，retained living safe superset 为 114 份。本报告自身位于被排除的 repair reports，不改变 114 分母。
- 链接解析：用 `markdown-it-py 4.2.0` 按 CommonMark token 而非正文 regex 解析 114 份文件，得到 732 个 Markdown links，其中 703 个为带 path 的 relative local file links；path missing=0，retired-topic direct link targets=0，top-level `tmp/<file>` direct link targets=0。全体 local/same-file Markdown fragments 中 unmatched=1（PRR-01）。
- Literal/consumer scan：另扫 retained safe superset 的 inline-code/path literals、retained evidence assets，并扫描 `src/`、`tests/`、`pyproject.toml`；这一步发现了普通 Markdown link parser 不会看到的 PRR-02。
- Ledger/report scan：解析 77-row tmp ledger、219-row residual ledger、9 份 README-linked residual reports、额外 TUI history migration report；逐 destination 做 existence/SHA-256，对 malformed GHE 行再从 dotdev `HEAD` 与 index 读取 old source blob 交叉核对。
- Git/tree scan：只读 `git status`、`ls-tree`、`log`、`diff --check`；比较 active/nested root 的文件集合与 common-file hashes。没有执行 `git add`、commit、push、restore、move 或 delete。
- 未运行产品 tests：本审阅判据是文档迁移、链接、证据账与 repository structure readiness；没有把 retained-topic 产品验证误作 re-root 绿灯。没有执行 checkpoint 或 re-root。

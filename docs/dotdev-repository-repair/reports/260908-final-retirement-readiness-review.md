# 2026-09-08 `.dev/docs` 首批退役与 dotdev re-root 最终独立审阅

**评审范围**：以 `/home/xp/src/ghc-api-proxy-py` 当前工作树（主仓 `HEAD/main = 3097c5cb0142d3e066f16921bf7c606780a7f3f3`）为准，复核 `.dev/docs/dotdev-repository-repair/README.md`、两份既有独立审阅、retirement reference map、tmp final disposition、first retirement batch、全部 24 份文件名含 `260908` 与 `migration` 的迁移报告，以及这些材料所声明的当前源、目标、living consumer 和候选目录。产品代码只用于核实 `interaction-context/spec.md` 与 `httpx2-migration`／`systemd-runtime` 的 current-source 断言；没有评审其它并行产品改动。历史 `reports/`、`history/`、`archive-*` 内故意保留的旧路径不纳入 living-link 必须可解析门，repair control-plane 自身列出的迁移前路径也不反算成产品依赖。

**总体 verdict**：**needs-fix；现在不能删除首批候选目录，也不能随后执行 dotdev re-root。** 原 77 份 tmp ledger 的 `72 canonical history + 4 删除 + 1 interaction-context 提炼` 已逐项实施正确，15 个候选的 retained-living 入站依赖也已清零；但当前顶层 `tmp/` 又出现 1 份未处置的新报告，且 15 个候选目录仍保有 219 份 residual 原件，尚无逐份 canonical-history／删除 disposition。repair 执行入口仍描述迁移前状态，无法作为当前删除与 re-root 的可靠账本。

**blocker 数**：0（major 3，minor 0）。

## Findings

### FRR-01（major）：原 77 份 tmp 清单已闭合，但顶层 `tmp/` 又有 1 份未处置报告，不能宣称已经清空

**primary_location**：`.dev/docs/tmp/260908-reasoning-encrypted-include-review.md`

**related_locations**：

- `.dev/docs/dotdev-repository-repair/subtopics/260908-tmp-final-disposition.md`
- `.dev/docs/dotdev-repository-repair/README.md`「执行顺序」第 2、4、5 步

对 ledger 的 77 行重新做了机器对账：72 个 canonical destination 全部存在，72 个旧 `tmp/<basename>` source 全部不存在；4 个授权删除项全部不存在；`260907-interaction-context-design.md` 的 tmp source 不存在，living Spec 与 history 原稿均存在。72 个目标均与 24 份 migration reports 中声明的 SHA-256 一致，且 basename 在活动 `.dev/docs/` 中各只有一个 canonical 原件。

但当前 `find .dev/docs/tmp -maxdepth 1 -type f` 不是 0，而是 1。新增的 `260908-reasoning-encrypted-include-review.md` 不在 77 行 ledger 中；它包含一个尚未关闭的 `should-fix`、实现与测试搜索面、候选人控文档的权威边界，显然不能当作可直接删除的空目录残渣。顶层 tmp 作为交换机制可以继续存在，但本轮要求的“内容已清空、所有材料已有去向”不成立。

**影响**：若按旧 ledger 的 `77/77 pass` 直接进入退役/re-root，会漏掉一份当前点时证据；若直接删除则丢失 review finding 与处置上下文。

**最小修正**：为这 1 份报告补一行 current disposition，迁入唯一 retained owner 的 `history/`（并保留它只绑定当前 dirty working tree、不是 current authority 的边界），或给出可追溯删除理由；随后确认顶层 `tmp/` regular file count 为 0。

### FRR-02（major）：15 个候选只关闭了 topic-level 依赖门，219 份 residual 原件仍未逐份处置

**primary_location**：`.dev/docs/dotdev-repository-repair/subtopics/260908-first-retirement-batch.md`「执行时的不可省略释放门」第 1、4、5 项

**related_locations**：

- `.dev/docs/dotdev-repository-repair/README.md`「执行顺序」第 3、5 步
- 15 个候选目录当前内容（合计 219 个 regular files）

本轮复扫确认：15 个候选都已不再被 retained living Markdown 以相对 Markdown link 指向；原来阻塞 `archived-2604-rewrite`、`documentation-restructure`、`history` 的 current consumer／待确认事项也均已迁出或改链。因此它们的**主题级 authority/link gate 已闭合**。

这不等于目录可以整棵删除。first-retirement-batch 明确要求先对 residual 原件逐份给出唯一 retained-topic history destination，或给出逐项、可追溯的删除 disposition；当前 12 个首批目录仍有 117 份，另 3 个后续解锁目录有 102 份，合计 219 份。现有 2026-09-08 migration reports 只覆盖先前承重原件和 tmp ledger，不是这 219 份 residual 的最终处置表。

**影响**：现在删除任何一个候选目录都会跳过 repository repair 的明确内容保全门。即使目录中没有 current authority，也无法据现有账本区分“应留作 canonical history”与“证据价值已由 successor 完整承接、可删”的文件。

**最小修正**：为 219 份 residual 建立并实施逐份 disposition；迁移项核对 source absent、destination present、hash unchanged、basename 唯一，删除项保留逐项理由。目录实际清空后再删除空目录。不能把“0 个 living incoming”当成批量删除授权。

### FRR-03（major）：repair current entry 与执行清单仍停留在迁移前状态

**primary_location**：`.dev/docs/dotdev-repository-repair/README.md`

**related_locations**：

- `.dev/docs/dotdev-repository-repair/subtopics/260908-first-retirement-batch.md`
- `.dev/docs/dotdev-repository-repair/subtopics/260908-retirement-reference-map.md`
- `.dev/docs/dotdev-repository-repair/subtopics/260908-tmp-final-disposition.md`
- 24 份 2026-09-08 migration reports

README 自称本工作的“执行入口”，但当前仍写：

- `reasoning-carrier`、`timeout-408` 为“需更新”，尽管对应 2026-09-08 状态更新已经落地；
- `history` 只列 §6.1／§6.2 迁移前置，未反映 §5 查询面也已迁至 successor；
- R-01～R-21、93→77→0 的迁移仍以待执行语气出现；
- 未登记新建 retained `interaction-context`；
- 未把 `archived-2604-rewrite`、`documentation-restructure`、`history` 的 topic-level 解锁纳入当前候选批次；
- 没有记录 FRR-01 的新 tmp 文件和 FRR-02 的 219 份 residual 门。

first-retirement-batch 仍只列 12 个候选，并把“完成 77 份 tmp 实际迁移”写成全局前置；tmp final disposition 与 reference map 都清楚声明自己是迁移前快照/准备清单，不能替代当前执行状态。点时报告本身无需倒改，但 current README 至少要汇总“已完成、仍待做、当前计数与唯一下一步”。

**影响**：在删除和 re-root 这种不可逆步骤前，操作者若只按权威执行入口，会重复已完成工作、漏掉新增 tmp 与 3 个已解锁候选，并看不到 219 份 residual 才是真正未闭合门。当前控制面不能支持可审计执行。

**最小修正**：更新 README（或建立 README 明确指向的 current execution ledger），把 77 项实施、interaction-context、15 个候选 topic-level 状态、219 项 residual disposition 状态、新 tmp 文件和 re-root 前提交门统一对账。历史审阅/迁移报告保持点时原貌。

## Blocker 与 minor

- **blocker：0。** 未发现需要外部权限、缺失文件或不可取得工具才能闭合的门；上述三项都可在当前仓库内通过文档归口、逐份处置和账本更新完成。
- **minor：0。** 本轮只报告会改变删除/re-root 决策的高置信问题，没有把点时报告中的旧 SHA、历史原件内部故意保留的旧路径或纯格式问题升级成 finding。

## 顶层 `tmp/` 与 canonical history 复核

### 原 77 行 ledger

| 项目 | 期望 | 当前实测 | 结论 |
|---|---:|---:|---|
| canonical history | 72 | 72 个 destination present；72 个旧 tmp source absent；72 个 migration-report SHA-256 与当前 destination 一致；活动 docs 内 basename 唯一 | **通过** |
| 可删除 | 4 | 4 个精确 source 均 absent | **通过** |
| interaction-context | 1 | tmp source absent；`interaction-context/spec.md` 与 `history/260907-interaction-context-design.md` present；原稿 SHA-256 `a5e13fb123580439736256f38660ecb6bdf65f431bd2dcda27eb0ac39099bf4b` 与迁移报告一致 | **通过** |
| ledger 合计 | 77 | 77/77 | **通过** |

另对 12 份从退役候选迁出的承重原件逐项检查 source absent、canonical destination present；其中 migration report 明列 hash 的项目也逐项匹配。覆盖 `sync-refs` 2 份、`hooks-subscription-migration` 1 份、`archived-2604-rewrite` 5 份、`empty-text-block` 1 份、`git-housekeeping` 2 份、`count-tokens` 1 份。未发现这些已迁原件丢失或重复。

### 当前 tmp 终态

原 ledger 实施后又新增 `260908-reasoning-encrypted-include-review.md`，所以当前是：

```text
original_ledger_sources_remaining = 0
new_unledgered_tmp_files = 1
tmp_regular_files_total = 1
```

结论必须分开写：**“72+4+1 已正确实施”成立；“顶层 tmp 内容已清空”不成立。**

## `interaction-context/spec.md` 忠实性复核

**结论：通过，未发现伪称用户裁决或把 WIP 升级成 current behavior。**

重新对照了 current working tree 的：

- `pipeline/session_identity.py`：六候选顺序、case-insensitive、strip/blank-skip 与全部候选移出 header bag；
- `server/inbound.py`：先抽取 identity，再把过滤后的 mapping 同时写入 `client_headers`／`source_headers`；
- `pipeline/request.py`：`id`、`interaction_id`、memoized `provider_interaction_id` 与 `interaction_id_for_provider()`；
- `model_provider/base.py`、`direct_driver/base.py`、`model_provider/github_copilot.py` 与 GHC client/header builder：显式 provider seam、GHC inference 非空要求、owned `X-Interaction-Id`、非 GHC 忽略边界；
- GHC `count_tokens`：不经过 inference seam，使用 provider-instance fallback；
- translated/direct/retry 的现有测试与调用路径。

Spec 把各项明确分为 **current implementation**、**仍待验证**、**非目标**；原设计稿的 2026-09-07 HEAD/dirty WIP、推荐方案与测试矩阵只留在 history。它还明确写出 `count_tokens` 当前不绑定 client interaction 不是“永远不得绑定”的用户裁决。全文没有 `resolved-by-user`、`用户已裁决` 或等价权威升级。

定向复跑：

```text
PYTHONDONTWRITEBYTECODE=1 uv run pytest -p no:cacheprovider -q \
  tests/unit/server/test_server_inbound.py \
  tests/unit/pipeline/test_direct_driver.py \
  tests/component/model_provider/ghc_client/test_headers.py \
  tests/component/model_provider/ghc_client/test_client.py \
  tests/int/test_pipeline_app.py \
  -k 'interaction or session_identity or session_id or no_client_headers_sends_none'

6 passed, 343 deselected, 1 warning in 2.57s
```

该绿灯只复现 Spec extraction report 声明的现有覆盖；Spec 已诚实把六候选全矩阵、direct e2e、delivery reopen、anonymous cross-request 与 inbound-session count negative 保持为待验证，没有拿这 6 项替代它们。

## Retained living Markdown 相对链接与退役路径依赖

扫描集合采用安全超集：排除 15 个退役候选、顶层 `tmp/`、`dotdev-repository-repair` control-plane，以及任一路径分量为 `reports`、`history` 或 `archive-*` 的文件后，共 **114 份 Markdown**。该集合包含全部 retained living Markdown，并故意多收导航／review-disposition 类文件。

### 解析结果

| 项目 | 结果 |
|---|---:|
| 解析的本地相对 Markdown links | 705 |
| 指向 15 个候选目录的 link | 0 |
| 指向顶层 `tmp/` 文件的 link | 0 |
| 真正断裂的相对 link | 0 |
| parser 初筛“断链” | 2，均为正文 regex 字面量 `[?:7\|8]` 被朴素 inline-link parser 误识别，不是 Markdown link |

另对 24 份 2026-09-08 migration reports 单独解析 **79 个**本地相对 links，`broken=0`。上一轮 MSR-06 的 5 个报告自身相对路径问题已关闭。

### 旧路径 literal 扫描

retained current/living 文档中没有对 15 个候选或具体顶层 `tmp/<file>` 的 current path dependency。仍能看到的旧路径只在：

- `hosted-web-search/260908-external-reference-migration-note.md` 的迁移前后对照表；
- topic-local `history/README.md` 的 provenance 原路径；
- archived/reports 原件中的点时路径；
- `auto-mode-classifier/spec.md` 对“历史报告内部旧路径有意不改”的说明；
- 泛指顶层 tmp 机制、而非指向某个现存 tmp 原件的文字。

这些不是 current evidence consumer，不要求给退役主题延寿。`anthropic-responses-bridge/implementation.md` 已改指 repository repair；2604 的承重证据均改指 retained-topic history；`history` 的 current ownership 与 §24～§26 来源均已迁入 upstream successor。

## 15 个候选逐项裁定

这里区分两个问题：

1. **主题级能否退役**：是否仍有 living authority、未迁待裁事项或 retained-living consumer；
2. **目录现在能否删除**：residual 原件是否已逐份处置、目录是否实际清空。

15 项的第一问均为“能进入退役处置”；第二问均为“现在不能删除”。

| 候选 | 当前 residual files | 主题级结论 | 当前删除结论 |
|---|---:|---|---|
| `architecture-audit` | 9 | 仅时点审计 reports；living incoming 0 | **不可立即退役**：9 份未逐份 disposition |
| `archived-2604-rewrite` | 38 | 旧学习笔记已明确非 current authority；5 份承重快照已迁，current old-path consumer 0 | **不可立即退役**：38 份 residual 未逐份 disposition |
| `copilot-token-identity` | 4 | 仅 token identity 时点评审／验收；同名 archive ref 不是 docs dependency | **不可立即退役**：4 份未逐份 disposition |
| `count-tokens` | 3 | successor 为 `token-counting`；承重原件与 TUI 改链已完成 | **不可立即退役**：3 份未逐份 disposition |
| `docs-tmp-migration` | 25 | 旧迁移过程与批次账；不再是 current control-plane | **不可立即退役**：25 份未逐份 disposition |
| `documentation-restructure` | 36 | current owner 已改到 repository repair；living incoming 0 | **不可立即退役**：36 份旧计划／reports 未逐份 disposition |
| `early-verification` | 17 | 历史 acceptance/runner snapshot，不是当前验证入口 | **不可立即退役**：17 份未逐份 disposition |
| `empty-text-block` | 7 | current contract 已由 retained request-shape／keepalive 承接；承重报告已迁 | **不可立即退役**：7 份未逐份 disposition |
| `git-housekeeping` | 23 | current repair owner 已迁到 repository repair；两份承重 provenance 已迁 | **不可立即退役**：23 份未逐份 disposition |
| `history` | 28 | §6.1、§6.2 和 §5 HTTP 查询面均已迁为 upstream `deferred.md` §24～§26；old current paths 0 | **不可立即退役**：28 份 proposal/spec/decisions/reports 未逐份 disposition |
| `hooks-subscription-migration` | 4 | migration 完成，current beta-strip owner 与证据已迁 | **不可立即退役**：4 份未逐份 disposition |
| `lifecycle-reorg` | 4 | 仅重组与 closeout 时点记录；living incoming 0 | **不可立即退役**：4 份未逐份 disposition |
| `pipeline-rewrite-parity` | 5 | 一次性前身项目对照调研；living incoming 0 | **不可立即退役**：5 份未逐份 disposition |
| `sync-refs` | 13 | 承重的 2 份外部调研原件已迁，current consumer 已改链 | **不可立即退役**：13 份未逐份 disposition |
| `test-infrastructure` | 3 | 仅 PoC／hang／hygiene 时点记录；living incoming 0 | **不可立即退役**：3 份未逐份 disposition |

### 可立即退役清单

**空。** 当前没有一个候选满足“residual 已逐份处置且目录已清空”的最终删除门。

### 已满足主题级门、完成 residual disposition 后可退役

`architecture-audit`、`archived-2604-rewrite`、`copilot-token-identity`、`count-tokens`、`docs-tmp-migration`、`documentation-restructure`、`early-verification`、`empty-text-block`、`git-housekeeping`、`history`、`hooks-subscription-migration`、`lifecycle-reorg`、`pipeline-rewrite-parity`、`sync-refs`、`test-infrastructure`。

### 当前不可退役清单

严格按“现在能否删除”回答：上述 15 项全部不可立即退役；原因统一为 FRR-02，而不是重新发现了 living consumer。另有两个 retained topic 仍因产品/运行时未闭合而不可进入主题退役：

- `httpx2-migration`
- `systemd-runtime`

## 两个明确不可退役主题

### `httpx2-migration`：仍是 current living residual owner

不可退役理由重新核实成立：

1. `plan.md` 明确把步骤 4 标为 `deferred，未完成，继续 living`。
2. `reports/260908-residual-audit.md` 对活动 `src/` 的逐处审计列出 53 个位置、75 次旧包完整词出现；其中既有需要保留版本限定的历史 `httpx/httpcore`，也有把当前 `httpx2/httpcore2` 写成旧名的 live prose，不能机械替换或按命中数结案。
3. `src/app/observability/logging.py` 当前仍只把 `"httpx"`、`"httpcore"` logger 提升到 `WARNING`；已安装当前库使用 `httpx2` 与 `httpcore2.*` logger。这是运行时筛噪行为，不只是文案。
4. `pyproject.toml:16` 仍指向 `.dev/docs/httpx2-migration/plan.md`，且在步骤 4 未闭合时这个指针仍正确。

必须先由源码 owner 处理三组 deferred、验证当前 logger 筛噪、复跑语义审计，再更新/移除 `pyproject.toml` 指针并重审主题。现状不允许退役。

### `systemd-runtime`：S5 仍是唯一未闭合运行时门

不可退役理由重新核实成立：

1. S3 graceful timeout 与 S4 rootless installer 已在 main，S7 current owner 已移交 `systemd-rolling`；这些都不能替代 S5。
2. S5 的 private `systemd --user` 在创建临时 `XDG_RUNTIME_DIR/systemd/private` control socket 前以 `rc=1` 退出。
3. 当前调用进程位于 root 所有、当前用户不可写的 `/init.scope`；允许的无特权 namespace 手段不能补出 delegated cgroup v2 子树。
4. 因此真实 manager activation、fd inheritance、effective `memory.high`／`memory.max`／`cpu.max`／`pids.max`、restart 与 manager stop 均未验收。静态 unit verify、direct inherited-fd smoke、仓库测试或 archive review 的绿灯都不能替代这些运行态观察。
5. 下一环境必须是具备独立 login session/user manager 与 delegated cgroup v2 的可销毁 VM 或 container；三个已知 non-blocking minor 不是 S5 的阻塞理由。

S5 闭合并把仍有效结论迁入唯一 current owner 前，`systemd-runtime` 必须保留。

## 到 dotdev re-root 前的最小必需剩余动作

按依赖顺序：

1. **处置新 tmp 文件**：给 `260908-reasoning-encrypted-include-review.md` 唯一 canonical owner／删除 disposition，实施后确认顶层 `tmp/` regular files 为 0。
2. **为 219 份候选 residual 建最终处置账并实施**：每份只能是 retained-topic canonical history 或有理由的删除；迁移项做 source/destination/hash/basename 四项核对。
3. **删除实际清空的 15 个候选目录**：只能在第 2 步逐目录完成后进行；`httpx2-migration` 与 `systemd-runtime` 不在删除集合中。
4. **重跑最终扫描**：retained living safe superset 的候选路径、候选 basename、顶层 `tmp/<file>` consumer 均为 0；所有新增相对 Markdown links 可解析；24 份 migration reports 与新 residual-disposition reports 的 canonical links 无断裂。
5. **更新 current control-plane**：README/执行 ledger 写入真实计数、15 项状态、tmp=0、明确保留的 `httpx2-migration`/`systemd-runtime` 理由，并把旧 subtopic 文件标成已执行的点时记录而不是当前待办。
6. **提交 `.dev` 文档整理与主题退役结果**：当前 `.dev` checkout 仍有嵌套 tracked deletions与活动根 `docs/`、`exp/`、`human-controlled-docs-candidates/`、`tools/` 的 untracked tree；在 re-root 前必须形成可审查 checkpoint，并按 README 逐路径确认嵌套树与活动根目标一致。
7. **另行执行并验收 re-root/worktree 挂载**：re-root 前后都保留 dotdev 完整祖先链；重构后验证分支顶层直接为 `docs/`、`exp/` 等，主工作树 `.dev/` 通过 worktree 挂载，且 `git status` 能直接观察 `.dev/docs/` 修改。

`httpx2-migration` 步骤 4与 `systemd-runtime` S5 是各主题自己的 living 工作，不要求在本批 re-root 前解决；要求的是它们必须被保留且 current links/owners 不因 re-root 丢失。

## 断链与内容丢失风险结论

### 已排除

- 原 72 个 tmp canonical history destination 缺失：**未发现**。
- 原 72 个 tmp source 残留／复制而非移动：**未发现**。
- 4 个授权删除 source 残留：**未发现**。
- interaction-context 原稿丢失或 hash 改写：**未发现**。
- 12 个退役候选承重 source 仍在旧位置、canonical destination 缺失：**未发现**。
- retained living Markdown 的真实相对断链：**未发现**。
- 24 份 2026-09-08 migration reports 的相对断链：**未发现**。
- retained living 文档仍消费 15 个候选或具体顶层 tmp 原件：**未发现**。

### 仍存在

- **高置信内容丢失风险**：15 个候选的 219 份 residual 还没有逐份 disposition；整目录删除会越过明确保全门。
- **高置信内容丢失风险**：新 tmp review 不在原 ledger；直接按“tmp 已清空”删除会丢失其 finding 与处置上下文。
- **高置信执行风险**：repair current entry 未对账最终状态，不能直接作为删除/re-root runbook。

## 搜索面与命令

**判据与控制面全文读取**：

- `dotdev-repository-repair/README.md`
- `reports/260908-inventory-review.md`
- `reports/260908-merged-state-review.md`
- `subtopics/260908-retirement-reference-map.md`
- `subtopics/260908-tmp-final-disposition.md`
- `subtopics/260908-first-retirement-batch.md`
- 24 份 2026-09-08 migration reports（共 731 行）

**被检状态读取/枚举**：

- 77 行 tmp ledger 及其全部 current source/destination；
- 当前顶层 `tmp/`；
- `interaction-context` 的 README、Spec、history 原稿/索引与 extraction report；
- 15 个候选目录的全部文件清单，及 `archived-2604-rewrite`、`documentation-restructure`、`history` 的根级权威/重定文档；
- `httpx2-migration` living Plan、residual audit、`pyproject.toml` 指针与 current logger config；
- `systemd-runtime` living Plan、S5 diagnosis/cleanup 报告和 `systemd-rolling` 交接边界；
- `.dev` 与主仓只读 `git status`、当前 HEAD/main identity。

**机器复核**：

- 从 tmp final ledger 解析 77 行并按类别计数；
- 72 个 destination existence、source absence、SHA-256、basename uniqueness；
- 12 个 candidate-source canonical moves 的 source absence/destination presence/hash；
- retained safe superset 114 份 Markdown、705 个本地相对 links 的路径解析；
- 15 个候选与顶层 tmp 的 Markdown link及 path-literal consumer 扫描；
- 24 份 migration reports 的 79 个本地相对 links 解析；
- interaction-context 定向 tests：6 passed。

**未覆盖**：

- 没有替实施者为 219 份 residual 判定最终 owner 或删除价值；这正是 FRR-02 尚未完成的工作，不能用抽样冒充逐份处置。
- 没有运行全量产品测试；本审阅的用户可观察目标是文档迁移、链接与退役安全，interaction-context 只跑了与其 current contract 直接相关的定向测试。
- 没有把历史 reports/archive 内的旧路径改成自包含档案；判据明确将它们排除出本轮 living-link 释放门。
- 没有执行移动、删除、`git add`、commit、push 或 re-root。

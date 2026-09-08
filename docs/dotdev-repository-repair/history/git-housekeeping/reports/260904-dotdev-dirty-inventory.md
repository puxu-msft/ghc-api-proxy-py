# `.dev` 脏文件语义盘点与处置建议

日期：2026-09-04。
状态：调查已执行，报告未经独立评审，供主会话整理时逐项对账。

调查范围：独立仓库 `/home/xp/src/ghc-api-proxy-py/.dev` 的 tracked modified 与 untracked 文件。任务为只读调查；除本报告外，没有编辑、暂存、提交或运行任何被检脚本。

本报告是本次整理的临时处置输入，不是任何产品行为、当前验收状态或项目优先级的 authoritative carrier。整理者完成蒸馏和归档后，应按实际处置决定本报告的归档位置；不得把本报告留作 living status。

## 结论

初始盘点基线为 `.dev` 分支 `dotdev`、HEAD `0b761e387ade952828efaeb00e3af405b953a243`。基线共有 29 个脏文件：tracked modified 1 个、untracked 28 个、staged 0 个。分类为 A 26 个、B 1 个、C 1 个、D 1 个。本报告写入后新增第 30 个脏文件；它自身属于 B 类临时处置输入，不计入上述初始 29 个文件的分类总数。

最重要的处置顺序是：先把 `docs/tmp/260903-next-root-fix-backlog-analysis.md` 的增量合同蒸馏进 direct-passthrough 的 living Spec／plan／deferred，再把 8 月 30 日和 9 月 3 日的报告原件按话题归位；保留 `probe_cap_designs.py` 的可复现实验价值并补入口说明；不要把 `stage_migration.py` 当作长期工具提交；`verification/` 全部是当前项目早期阶段的历史验收资产，不是外部项目，也不是当前 `main` 的验收入口，应按完整历史快照归档而不是更新成现行工具。

证据强度：上述分类足以作为本轮整理的行动依据。唯一方法限制是 harness 拒绝从隔离 worktree 对目标仓库执行 `git -C`；因此文件状态由只读解析 `.git/index` v2、HEAD commit/tree objects 与工作树字节重建，而非直接采用 `git status` 输出。重建读取了 1074 个 HEAD entries 与 1074 个 index entries，缺失 object 为 0，并逐文件比较 mode 与 blob SHA-1；`.dev/.gitignore`、`.dev/.git/info/exclude` 与用户级 ignore 也已读取，列出的 28 个 untracked 文件没有命中额外 ignore。这个方法足以区分本次集合，但不冒充对 Git 所有未来 index 格式的通用实现。

## 分类口径

- A：必须逐字保留的报告、评审、处置账或验收快照。它可以移动到正确话题或 archive，但不得为了写成“当前结论”而覆写正文。
- B：结论尚未被 living authority 完整接管，先蒸馏到已有 living doc，再决定原件作为 research／历史分析归档。
- C：可复现实验或工具，当前仍回答 living doc 的问题；补可执行入口、参数与能力边界后保留。
- D：一次性上下文已经结束、且现有 carrier 已接管其用途的临时冗余候选。这里只判定候选，不授权删除。

## 一、按语义主题归组

### 1. 已在正确话题中的评审原件：A

| 文件 | 状态 | 分类 | 处置与证据 |
|---|---|---|---|
| `docs/delivery-keepalive/reports/review-proxy-priority.md` | untracked | A | 保留原文并提交到现路径。`docs/delivery-keepalive/decisions.md:106` 已引用该报告，改名或移走会断开 living decision 的 provenance；报告自身在 `:8-14` 锚定候选与初轮结论，在 `:141-211` 追加定向复核，是不可改写的多轮评审记录。拒绝把它改写成当前状态。 |
| `docs/upstream/retry-and-continuation/reports/260822-review-one-ending-decision.md` | untracked | A | 保留原文并提交到现路径。正文按候选 revision 保存四轮评审、变异与最终 PASS；它分析的是定格 commit，不是 living plan。 |
| `docs/upstream/retry-and-continuation/reports/260823-review-h2-classification.md` | untracked | A | 保留原文并提交到现路径。后续报告已经引用它，例如 `reports/260824-review-round-seven.md:147,155`；正文保存五轮逐提交评审与 exact-commit 证据，任何“更新到当前代码”的改写都会伪造原观察。 |

否决路线：没有把这三份归 B。它们的用途是“当时对哪个候选发现了什么”，不是承载当前行为；当前结论应由各话题的 decisions／status／spec／deferred 承担。

### 2. `project-review-principles` skill 的评审原件：A，但应归到既有 skill 话题

| 文件 | 状态 | 分类 | 建议归位 |
|---|---|---|---|
| `docs/graceful-shutdown/client-side/reports/260820-review-principles-entries.md` | untracked | A | 原文移动到 `docs/project-review-principles-skill/reports/` 后提交。它的评审对象是 `.claude/skills/project-review-principles/SKILL.md` 的条目 3／4，不是 graceful-shutdown 功能本身；现有 skill 话题已经有三份同类 260820 报告。 |
| `docs/tmp/260903-project-principles-backlog-review-gpt-opus.md` | untracked | A | 原文移动到 `docs/project-review-principles-skill/reports/`。它是 2026-09-03 对五条原则的实际执行记录，含三条仍 open 的产品 finding。 |
| `docs/tmp/260903-project-principles-backlog-review-general-sonnet.md` | untracked | A | 与原报告一起移动，保留初审与窄复评追加；不得把旧 `needs-fix` 段删成只有最终 PASS。 |
| `docs/tmp/260903-project-principles-backlog-review-disposition.md` | untracked | A | 与两份报告一起移动。它是处置账，`adopted` 与产品实现仍 open 的区别是承重事实。 |

已有 authoritative carriers 并非空白：主仓 `.claude/skills/project-review-principles/SKILL.md` 是原则与检索方法的 living authority；其中 `one-reply-fact-...` 已明确记下 count-tokens 直写 `trace.usage` 的结构缺口，`explanation-...` 已明确列出三个承诺面问题。`.dev/docs/direct-passthrough/spec.md` §10 与 `plan.md` §6 已承载 native side facts 的目标及“尚未迁移 reasoning 等事实”的当前状态。因此三份 9 月 3 日文件不能取代这些 living carriers。

仍需同步的一处是 skill 的 `### 当前状态`：当前文件仍写“其中只有 `one-reply-fact-...` 经过一次真实复查”“其余四条仍未被真实复查”，而 9 月 3 日原报告实际执行了五条原则。整理时应更新这段 review history，并处理原报告指出的已腐坏命令路径；这是 living skill 的同步，不是覆写报告原件。

否决路线：没有把这些文件归 B 后直接重写为 terminal prose。评审原件与处置账的证据价值来自 point-in-time 内容。需要蒸馏的是 finding 与“已执行过一次真实复查”的状态，不是把报告正文改造成 living doc。

### 3. 2026-08-30 `custom_tool_call` 取证：A，authoritative carrier 已存在

| 文件 | 状态 | 分类 | 建议归位 |
|---|---|---|---|
| `docs/tmp/260830-custom-tool-call-forensics.md` | untracked | A | 原文移动到 `docs/direct-passthrough/reports/` 后提交。报告基线明确为主仓 `78030df`、OpenAI SDK 3.3.1；它只能作为该时点的协议／实现取证，不是当前 SDK union 或当前代码的 authority。 |

该报告的承重结论已经被接管：current `docs/direct-passthrough/spec.md:26,88,277` 明确记录 issue #2、`custom_tool_call_input` 事件必须原样携带及“词汇不列 item 类型”；`plan.md:3,85-106` 记录 issue #2 已随 Responses direct passthrough 修复；当前主仓 `src/app/pipeline/delivery/formats/openai_responses.py:425-432,551,605` 保存 translating 路径的显式 `UNKNOWN`，而 `tests/int/test_pipeline_app.py:2875-2912` 与 passthrough 单测锁住 direct 路径原样携带。故不应再把报告 §3 的 28-member 表蒸馏成一张 living allowlist；那会违背现行 Spec“词汇只描述边界，不描述 item 类型学”的根修。

否决路线：否决 B。报告已完成取证，当前 Spec／plan／实现已经接管结论；剩余动作只是把原件从 `tmp` 归到正确 reports 目录。也否决 C：它不是可运行探针，且其 SDK 类型清单会随 SDK 版本腐坏。

### 4. 2026-09-03 direct-passthrough 下一个根修分析：一份 B，两份 A

| 文件 | 状态 | 分类 | 建议归位与先决动作 |
|---|---|---|---|
| `docs/tmp/260903-next-root-fix-backlog-analysis.md` | untracked | B | 先蒸馏进 `docs/direct-passthrough/spec.md`、`plan.md` 与 `deferred.md`，再按 research／历史分析归入 `docs/direct-passthrough/reports/`。 |
| `docs/tmp/260903-next-root-fix-analysis-review-general-opus.md` | untracked | A | 保留初审、两轮窄复评与三份尾部声明的原文，随分析归入 direct-passthrough reports。 |
| `docs/tmp/260903-next-root-fix-analysis-review-disposition.md` | untracked | A | 保留为闭合处置账，随分析与评审归入 direct-passthrough reports。 |

B 类判断的关键依据是现有 living carrier 只接管了旧边界，没有接管 9 月 3 日分析新增的完整闭包。current Spec §2.8 与 deferred D-5 已记录 streaming 下 terminal 先出门、`CompletedBlock`／`RawEventBatch` 类型冲突及用户要求 direct continuation；plan 也仍只说 Anthropic 腿挡在 D-5／D-6。它们尚未写入以下增量：streaming 与 non-streaming 共用 format-neutral continuation intent；whole-body finalization；native failure 的 replay／continuation／final failure 动作矩阵；D-6 必须先于 selector 启用与 D-5 对外完成；current `signature_delta` reshape preservation 是启用前置；native typed side facts 与真实 route 验收边界。`rg` 在现有 Spec／plan／deferred 中没有找到 `ContinuationIntent` 或等价 finalization contract；而 current plan v13 的 2026-09-04 增量处理的是 terminal status／client actions，不是 D-5 实施计划。

建议蒸馏落点：

1. `spec.md`：补两种 streaming 方言与两种 non-stream body 的 finalization contract、native failure 动作矩阵、共同不变量与现行 reshape preservation；这些是行为规格，必须先行。
2. `plan.md`：新增 D-5 实施切片，区分完成边界与 semantic commit 边界，并把 D-7、D-6、side facts、reshape、selector 的依赖关系写清。
3. `deferred.md`：更正 D-6 目前“D-5 闭合之后紧接着做”的过期顺序；D-7 保留为 D-5 完成边界；若 native side-fact 工作未进入 plan，则以新的 open item 登记，不让它只活在 9 月 3 日报告里。

否决路线：否决把分析本身升级为 living plan。它含条件性优先级、调查前提与大量推导证据，生命周期是 research input；直接保留在 `tmp` 会制造第二个当前计划。也否决把两份 review 文件归 B 重写，它们是对定格分析稿的 point-in-time review。

### 5. `httpx2` 迁移实验与一次性 staging helper：C 与 D

| 文件 | 状态 | 分类 | 处置与证据 |
|---|---|---|---|
| `exp/httpx2-migration/probe_cap_designs.py` | tracked modified | C | 保留修改，但在 `docs/httpx2-migration/plan.md` 或脚本 module docstring 补可执行入口、`PROBE_CORE`／`PROBE_CAP`／`PROBE_SCENARIOS` 参数、预期输出与能力边界后再提交。 |
| `exp/httpx2-migration/stage_migration.py` | untracked | D | 不暂存、不提交为长期工具；保留在工作树等整理者决定归档或删除。 |

`probe_cap_designs.py` 已被 `docs/httpx2-migration/plan.md:31-34,66-88` 明确指定为 D3' 的判据，属于 living plan 的可复现实验。此次 tracked diff 只做四件事：让 cap 与场景可由环境变量配置；统计 attempts／rejections；把两项打印到每组结果；用 `SCENARIOS` 代替固定 tuple。它与 plan §8 的 F2 测量直接对应：plan 已写 `attempts/rejections` 数字，但旧脚本不打印这两个量。修改方向成立，且没有改 success predicate。不过 plan 的“度量三项”仍只列 `peak/conns/closed_in_use`，也没有给环境变量命令，故 C 类入口说明尚未闭合。

`stage_migration.py` 与 plan 没有任何引用关系；全 `.dev` 唯一的 `stage_migration.py` 文本命中是脚本自己的 Usage。它把“5 个混有同伴 WIP 的文件”、主仓当前 HEAD 与 private index staging 当作前提，解决的是当时一次迁移提交的共享索引切片，不是迁移行为本身。它还在 docstring 宣称 `--check`，但 argparse 只定义 `--write`，因此 advertised command 本身不可执行。当前主仓 `pyproject.toml:15-30` 已把 httpx2 与版本 floors 落地，迁移 staging 上下文结束；继续把它列作工具会诱使后来者对任意当前 diff 运行一次只为历史 WIP 形态写的 index writer。

否决路线：否决把 `probe_cap_designs.py` 归 A，因为它仍被 living plan 当作可复跑判据且本次 diff 提升了同一测量；否决把 `stage_migration.py` 归 C，因为它没有 living consumer、advertised `--check` 不存在、且写路径服务的是一次性共享索引状态。D 只是冗余候选，不是删除授权。

另一个需要 living doc 后续处理的事实是 `docs/httpx2-migration/plan.md` 顶部状态停在 2026-08-21 的“步骤 4 进行中／步骤 5 未做”，而 current main 已完整依赖 httpx2。这个状态过期不影响本次两个文件的 A/B/C/D 分类，但在提交 C 类 probe 变更时应同步 plan，避免一个 completed migration 继续以 in-flight plan 出现。

### 6. `verification/`：A 类历史验收快照，不是当前验收工具

以下 16 个文件全部归 A，并应作为两个相互关联的历史快照整体归档；不得逐个“修到能跑”，也不得把其中的 PASS 当成 current main 的验收结论。

| 文件 | 状态 | 分类 |
|---|---|---|
| `verification/HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` | untracked | A |
| `verification/PHASE3_ACCEPTANCE_REPORT.md` | untracked | A |
| `verification/phase3_acceptance.py` | untracked | A |
| `verification/final_acceptance/MANIFEST.md` | untracked | A |
| `verification/final_acceptance/README.md` | untracked | A |
| `verification/final_acceptance/REPORT.md` | untracked | A |
| `verification/final_acceptance/SUMMARY.md` | untracked | A |
| `verification/final_acceptance/run_all.sh` | untracked | A |
| `verification/final_acceptance/probes/00_cli_smoke.sh` | untracked | A |
| `verification/final_acceptance/probes/01_dynamic_port_startup.py` | untracked | A |
| `verification/final_acceptance/probes/02_anthropic_protocol.py` | untracked | A |
| `verification/final_acceptance/probes/03_openai_three_prefixes.py` | untracked | A |
| `verification/final_acceptance/probes/04_responses_websocket.py` | untracked | A |
| `verification/final_acceptance/probes/05_history_metrics.py` | untracked | A |
| `verification/final_acceptance/probes/06_approval_system.py` | untracked | A |
| `verification/final_acceptance/probes/07_gemini_azure.py` | untracked | A |

身份判断：这些资产对应当前 Python 仓库 `ghc-api-proxy-py` 在 2026-07-15～17 的早期 Phase 0-8／hooks-tokenization 阶段，不是外部项目；但也不对应 2026-09-04 current main。`HOOKS_TOKENIZATION_ACCEPTANCE_REPORT.md` 的 oracle 是已迁入 `docs/archived-2604-rewrite/hooks-tokenization-spec.md` 的早期规格；`PHASE3_ACCEPTANCE_REPORT.md` 与 final report 都明确写验收日期和“Phase 0-8”范围。current `.dev/README.md:64` 已将 `archived-2604-rewrite` 定性为整体过期、仅供参考。

不属于 current main 的一手与既有交叉证据如下：

- current main `pyproject.toml:15-30` 依赖 `httpx2[http2,socks,ws]`，不依赖 `httpx`／`httpx_ws`；六个 final probes 仍 `import httpx`，`phase3_acceptance.py:342-390` 仍要求 `httpx_ws`。
- `verification/final_acceptance/run_all.sh:5-8` 把 probe 目录硬编码为主仓根的 `verification/final_acceptance/probes`，但 current main 根下不存在 `verification/`，资产现在位于独立 `.dev` 仓库，故总入口按现路径不可运行。
- `phase3_acceptance.py` 仍导入旧的 `app.models.openai`、`app.openai.*`、`app.routes.*` 与 `app.server.create_app`；current main 已迁到 `app.server.routes` 与新的 pipeline／delivery 布局。
- `docs/architecture-audit/reports/260814-synthesis-gaps.md:161-165` 已实际观察 pytest green 与 standalone `phase3_acceptance.py` 的 3 blocker／1 major 相冲突，并把至少三项判为 script drift，而不是产品缺陷。
- `docs/tmp/260822-ghc-api-conformance-responses-ws.md:88-100` 已明确判定 `phase3_acceptance.py` 与 WebSocket probe 陈旧；`docs/httpx2-migration/reports/260821-httpx-usage-inventory.md:691-697` 把 final probes 明确归为“不参与产品构建、可后置或放弃的一次性验收探针”。

为什么整个 bundle 仍归 A，而不是把脚本拆成 C 或 D：报告的证据声称依赖当时的 probe 输入与 runner；将报告保留、把脚本按“当前不可跑”删除，会把验收快照拆成只有结论没有原始方法的残片。`.dev` 的职责本来包括“工作证据”，且这些文件从未进入 `.dev` 历史；先完整归档能避免不可恢复的丢失。建议在 `docs/archived-2604-rewrite/` 下以 2026-07-16 验收快照为一个整体落位，或建立一个明确标为 historical 的 verification archive；具体目录由整理者按既有索引决定。不要更新原文中的路径、依赖、PASS 或 line number；用 archive entry 说明它们被什么 current carrier 取代。

当前验收 authority 是项目规则中的三条验证命令与 current `tests/`，不是此 bundle。`final_acceptance/README.md`／`MANIFEST.md`／`SUMMARY.md` 内的“快速执行”和“验收通过”只在 2026-07-16 快照下成立；它们若留在顶层 `verification/` 会被误读为 current tool，故“提交到原位不动”不是可接受终态。

否决路线：

1. 否决 C。脚本没有 current entry、依赖与路由前提均已漂移，不能以“补一段 README”恢复为现行可复现实验；那实际上会重写整套验收系统，并违反“不要自行建立新的 proof infrastructure”。
2. 否决 D 直接删除。它们与报告组成一个历史验收 artifact，且未进入 `.dev` history；先删脚本会不可逆地损失 point-in-time 方法。只有在完整快照已经由另一 durable carrier 接管、并经单独删除授权后，才有资格重新讨论去重。
3. 否决把它们判成外部项目垃圾。文件内路径、模块与报告标题都明确指向 `ghc-api-proxy-py`；“早期且过期”不等于“外部”。

## 二、完整文件清单与分类计数

初始 29 个脏文件均已在上表逐项列出。汇总如下：

| 分类 | 数量 | 文件集合 |
|---|---:|---|
| A | 26 | 3 份已归位 topical reports；4 份 project-review-principles 报告／处置；1 份 260830 forensics；2 份 next-root review／disposition；16 份 verification 历史验收 bundle |
| B | 1 | `docs/tmp/260903-next-root-fix-backlog-analysis.md` |
| C | 1 | `exp/httpx2-migration/probe_cap_designs.py` |
| D | 1 | `exp/httpx2-migration/stage_migration.py` |

本报告 `docs/tmp/260904-dotdev-dirty-inventory.md` 是写入后的新增第 30 个脏文件，分类为 B。它应在实际整理处置完成后由整理者更新 disposition 记录或归档，但不得被当成项目状态 authority。

## 三、建议的非破坏性整理批次

1. 先处理 B：更新 direct-passthrough living Spec／plan／deferred，使 9 月 3 日分析不再是唯一完整 carrier；不要先移动或提交分析后就宣称已蒸馏。
2. 再处理 A 报告归位：`custom_tool_call` 与 next-root 进入 `direct-passthrough/reports/`；四份 principles reports 进入 `project-review-principles-skill/reports/`；已有 topical reports 保持路径。移动时检查 inbound references，尤其 `review-proxy-priority.md` 与 `260823-review-h2-classification.md` 已有引用，不要为统一命名破坏链接。
3. 将 `verification/` 作为完整历史 bundle 移入明确 historical 的 archive，并在 archive entry 写明 current authority；不要逐脚本现代化。
4. 处理 C：补 probe 的运行命令、环境参数与输出解释，同时修正 `httpx2-migration/plan.md` 的当前状态与“只度量三项”过期描述。
5. D 保留待裁：`stage_migration.py` 不进入本轮“合并并提交”集合；不删除、不暂存、不运行 `--write`。
6. 最后重新枚举 `.dev` 状态，确认所有原件仍可达、living docs 已接管 B 类结论、D 类仍被明确排除，再按语义提交。不要用一次大范围 `git add` 扫入 D 或尚未蒸馏的 B。

## 四、被否决的总体路线

- “所有 untracked 都直接提交”：否决。`stage_migration.py` 是一次性 private-index helper，next-root analysis 仍未被 living authority 完整接管。
- “所有 `docs/tmp/` 都删或原样搬进 archive”：否决。9 月 3 日 next-root analysis 尚有未蒸馏合同；先归档会把 open work 埋入历史。其余 tmp 报告应按话题归位，不能因目录名一刀切。
- “verification 既然陈旧就删除”：否决。它是本仓早期验收快照且尚未进入 `.dev` history，报告与 probes 是一个 artifact；陈旧只决定它不再是 current authority，不自动取消历史证据价值。
- “把 verification 脚本修成 current acceptance suite”：否决。当前项目已有 tests 与项目级验证命令；修这套旧 runner 等于新建第二套 proof system，并会让维护者再次面对两个相反验收面。
- “把 260830 forensics 的 SDK member 清单抄入 living Spec”：否决。current direct-passthrough Spec 明确选择无类型学的边界词汇；一张版本化 allowlist 会重新制造 unknown-item 天花板。
- “把所有 review 终稿只保留最后 PASS 段”：否决。初轮 finding、后续处置与复评是报告存在的理由；删掉旧 verdict 会抹掉因果与审计轨迹。
- “因 `probe_cap_designs.py` 已被 plan 引用就无需补说明”：否决。此次 diff 新增可配置 env 与 attempts／rejections 度量，而 plan 仍声称只度量三项；入口与 living doc 已发生可检查的漂移。

## 五、未执行事项与交接

- 没有运行任何 `verification/` probe、`probe_cap_designs.py` 或 `stage_migration.py`。后两者中 `stage_migration.py --write` 会写 private index／object，不属于只读调查。
- 没有编辑 living Spec、plan、deferred、skill、原报告或实验脚本；没有暂存、提交、删除、移动或推送。
- 本报告未获得独立 reviewer 复核。作为 leaf investigator，我不能派生 reviewer；主会话在实际整理前应按文件与本报告逐项对账，尤其核定 verification bundle 的最终 archive 路径和 next-root B 类蒸馏是否完整。

# `.dev` 合并候选最终评审

日期：2026-09-04。
状态：最终候选独立评审完成；候选需修订后复评。

评审对象：`/home/xp/src/ghc-api-proxy-py/.dev` 当前工作树。按要求首先调用 `my-agents:as-reviewer`，harness 返回 `Unknown skill`，遂按用户清单直接评审。隔离 harness 拒绝本 reviewer 对共享 checkout 执行 `git -C`，故 C11 的索引事实采用 `260904-dotdev-dirty-inventory-disposition.md:9-11` 保存的主会话真实 status／空 cached diff 回执，并与当前文件系统对账；未冒充本轮新跑的 Git 命令。

## Verdict

**needs-fix。** 共 5 条：blocker 1、major 4。C2、C3、C12 不成立；其余断言在 blocker／major 阈值下成立。

## Blocker／Major findings

### F-01　[blocker] Native failure 矩阵漏掉 streaming 已完整但未提交、replay 不可用的可达状态
- `docs/direct-passthrough/spec.md:275,296-297,570,579`：`full`／未触发 `until-tool-use` 会持有已完成 group；replay 被拒或预算耗尽后进入 finalization，但 continuation 行只接受“已提交”或“whole-body 已保留”，eligibility 又接受“可保留的完整单位”。
- 此时 taxonomy 可继续、eligibility 成立，却不满足 replay、continuation 或不可继续／decline 任一行，因而没有 `EndingAction`；实现无法按 Spec 唯一落地。
- 修复须为 streaming 持有的完整单位补明确动作，并同步 §5.3、§7.2、plan §11 与 D-5 完成边界；不能靠把未定义的“预算”临场解释成 decline 补洞。

### F-02　[major] 共同 eligibility 的“至少一个完整单位”硬前提收窄 max-token continuation
- `docs/direct-passthrough/spec.md:275`、`plan.md:461`；对照 human authority `docs/.human-controlled/upstream-retry-and-continuation.md:60` 和现实现 `src/app/pipeline/delivery/stream.py:611-613`。
- 人写合同对 `max_tokens`／`max_output_tokens` 明定丢弃未完成块后能续写则续写；现实现也特意允许该 stop reason 在 `committed_count == 0` 时继续，v22 却把“有可保留完整单位”提升为所有 ending 的共同下限。
- 这会把首个块因 max-token 未闭合且无其它完整单位的既有 continuation 改成原 ending，属用户可观察行为收窄；须把 max-token 特例与普通 failure 进展前提分开，或先取得用户裁决。

### F-03　[major] `budget` 的种类、所有者与 intent 真值时点冲突，可能凭空建立 continuation 上限
- `spec.md:273,275`、`plan.md:431,433,439`；对照 human authority `upstream-retry-and-continuation.md:38`。
- Spec 用未定义的“剩余预算”门控 eligibility 并把 eligibility outcome 放进 intent；plan 又把 decline 放在 intent 外、声明 driver 拥有预算，却说 budget 拒绝时 intent 不存在。
- 若指 continuation 次数预算，违反用户“不需要次数上限”；若指 replay budget，driver 已在 policy 前裁过 replay；若指 deadline／其它预算，则没有字段、所有者或判定时点。需具名预算并统一 outcome／intent／proposed effect，或删去该门。

### F-04　[major] “每条直连腿”被正文与完成边界静默缩成两种方言
- `spec.md:4,96,132,283-287,302,770`、`plan.md:498`：定义域是所有 `translation_required is False` 路由，2026-09-01 裁决记为“每条直连腿”，但投影与完成边界只覆盖 Anthropic Messages／OpenAI Responses，Chat Completions 块级交付仍写“不因本规格重开”。
- 两读不能并存：若裁决实际只覆盖两种 block-aware 方言，应收窄定义域和“每条”并给 provenance；否则 Chat Completions 是未覆盖义务，不能关闭 D-5／宣称每腿完成。
- Embeddings 若因没有生成回合而不适用，也应由显式 applicability 排除，不能靠两方言表的缺席完成缩域。

### F-05　[major] Spec v22 正文保留已被自身修订记录推翻的 current 状态
- `spec.md:71` 对 `:771`；`:219` 对 `:273-302,630-633`；`:453,527` 对 `:536`，且与文首“仅 O-1 待裁”冲突。
- §2.5 仍称 §§5～10 无 Responses 专有事实，而 v14 明说该全称已被六个反例推翻；§5 仍称本腿无 continuation、§8 已裁 SSE error，而 v22 已改成共同 continuation。
- §6.6 顶部／标题仍称 `fix_stream_ids` 默认值待裁，后文却写 2026-09-02 已定默认关。三处均在当前规范正文，须改成有时态的历史说明或删除，并同步顶部、正文、§12。

## C1～C12

- **C1 PASS**：`docs/git-housekeeping/reports/260904-dotdev-dirty-inventory.md:11-15,139-148` 建立 29 文件分母；处置账 `:16-23` 将 3 topical、4 principles、1 custom-tool、3 next-root、probe、stage helper、16 early-verification 与调查报告逐组落位。当前只读检查得到 `topical_reports_present=3`；early-verification 为 17 文件，即 16 原件加入口 README。未发现原件删除。
- **C2 FAIL**：F-01、F-02、F-04、F-05。v22 虽新增 intent、streaming／whole-body、failure、side facts、reshape 与 selector 边界，但 action 状态空间、max-token 特例、定义域和旧正文未闭合。
- **C3 FAIL**：F-01、F-03。`plan.md:431-443` 的 typed variants、driver-owned finalization、生命周期与 accepted／completed 分槽方向成立，且 `:499` 明拒 proof framework；但 budget 与缺失 action 使 outcome 不能唯一指导实现。
- **C4 PASS**：`deferred.md:68-92` 把 D-5 标为已裁待做，`:95-108` 将 D-6 定为 selector／D-5 前置，`:112-121` 将 D-7 放入 plan §11.2；与 `plan.md:425-498` 的依赖和“semantic commit ≠ 对外完成”一致。
- **C5 PASS**：260830 custom-tool、4 份 direct 260903 原件及 3 份 principles 260903 原件均归入对应 reports；`plan.md:426` 与 principles `README.md:6-14` 从 living carrier 指向现路径。旧报告内旧绝对路径是点时原文，未被冒充 current。
- **C6 PASS**：principles `README.md:2,6-14,18-20` 指定主仓 skill 为唯一原则 authority，并明说报告通过不等于产品修复；`deferred.md:4-20` 分别承载 stale skill／命令、PPR-02、PPR-03，`:22-24` 单向移交 PPR-01。未称主仓 skill 已修。
- **C7 PASS**：`fd --type f . .../docs/early-verification | wc --lines` 输出 17；`README.md:8-14` 枚举 3 个 archive 共 16 原件，`:2-5,16-22` 指定 current authority并明确旧 runner 不从新路径运行。历史原件旧链接保留为快照，不冒充 current。
- **C8 PASS**：probe 的参数、五项输出和 exit 条件在 `probe_cap_designs.py:13-20,33,40-43,199-208` 与 plan `:32,74` 对齐；处置账 `:41-43` 保存实际运行／Ruff／compile 回执。httpx2 plan `:3,23-24,32-41` 分开记录核心迁移、V2、残余散文；`:36` 与 archive README `:2-6` 禁止 stage helper 当前使用。
- **C9 PASS**：9 份新增／living 入口文档只读链接检查输出 `entry_docs=9 relative_links=99 broken=0`；根 README `:51-68` 可发现 principles、early-verification 与按目录名可读主题。处置账与调查报告同目录互链可达。
- **C10 PASS**：处置账 `:14-23` 逐组记录采纳与 stage helper 暂定调整，`:45-52` 记录未采纳／暂定路线及理由，`:54-58` 记录未做事项和待收口。
- **C11 PASS**：处置账 `:9-11` 保存真实状态复核为初始 29、staged 0，并明确未改 human-controlled、主仓 source／tests／skill／config、未删原件、未推送；本 reviewer 只尝试写本报告且被 isolation guard 拒绝，没有暂存或运行被检脚本。本项采用已有真实 Git 回执，不冒充新跑命令。
- **C12 FAIL**：文首为 v22（`spec.md:3`）且 §12 有 v22 行（`:760`），plan 文首为 v14（`plan.md:2`）且 §11 存在（`:424-500`）；F-05 证明 Spec 正文仍与修订记录冲突。

## 其余主动检查

- 三份其它待提交 topical reports 均在既有 topical reports 路径，保留多轮历史与最新结论；未见 blocker／major 级归位或 authority 冒充。
- 新建／living 文档未见 blocker／major 级硬折行；归档 stage helper 的旧换行属于历史原文，不应为格式统一改写。
- 两个 Python 脚本未见本轮需报的 blocker／major 级明显 correctness 问题；stage helper 的 Usage／argparse 不一致已在 archive README 明示且禁止当前运行。
- 未运行 probe、历史 runner 或 stage helper，避免改写 `__pycache__`、索引或其它状态。

## 未采纳建议

无。仅提出关闭上述 blocker／major 所必需的修订，没有另列可选清理、proof framework 或 minor 建议。

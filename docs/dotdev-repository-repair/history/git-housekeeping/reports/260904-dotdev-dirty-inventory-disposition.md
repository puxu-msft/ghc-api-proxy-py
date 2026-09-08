# `.dev` 脏文件盘点处置账

日期：2026-09-04。
状态：closed。原调查者第二轮 pass；最终候选独立评审首轮的 1 blocker／4 major 全部采纳，第二轮剩余 1 major，第三轮复评 pass，最终 remaining blocker=0、major=0、minor=0。
调查报告：[`260904-dotdev-dirty-inventory.md`](260904-dotdev-dirty-inventory.md)。

## 接收回执

初始集合 29 个脏文件：tracked modified 1、untracked 28、staged 0。调查报告另新增自身 1 个文件。主会话以真实 `git --no-optional-locks status` 与空 `git diff --cached` 复核了集合；并行会话明确确认已经停止写 `.dev`，没有未落盘、已暂存或禁止整理的路径。

调查报告的 A=26、B=1、C=1、D=1 是处置输入，不直接充当提交清单。以下逐项采用 C 级可逆文档判断；没有修改用户亲笔 `docs/.human-controlled/`，没有修改主仓源码、测试、skill 或配置，没有删除任何原件，没有推送。

## 逐组处置

| 组 | 调查建议 | 裁定 | 实际落点与理由 |
|---|---|---|---|
| 三份已归位 topical reports | A，原位保留 | 采纳 | `delivery-keepalive/reports/review-proxy-priority.md` 与 `upstream/retry-and-continuation/reports/260822-review-one-ending-decision.md`、`260823-review-h2-classification.md` 原文原位提交；已有 living 引用不改名 |
| 四份 project-review-principles 报告／处置 | A，移入 skill 主题 | 采纳 | `260820-review-principles-entries.md` 与三份 260903 文件移入 `docs/project-review-principles-skill/reports/`，原文不改；新增专题 `README.md` 与 `deferred.md` 承接当前状态 |
| 260830 `custom_tool_call` 取证 | A，移入 direct-passthrough reports | 采纳 | 移入 `docs/direct-passthrough/reports/`；不把 SDK 3.3.1 的 28-member 表抄成 living allowlist，现行 Spec 仍以“词汇不枚举 item 类型”防止重建天花板 |
| 260903 next-root 分析 | B，先蒸馏再归位 | 采纳 | Spec 升到 v22，新增格式无关 continuation intent、streaming finalization、native failure 动作矩阵、non-stream body 投影与 native side facts；plan 升到 v14 并新增 §11 outcome／生命周期／实施切片；deferred 更正 D-5／D-6／D-7 状态和依赖。分析、评审、处置原件随后移入 direct-passthrough reports |
| `probe_cap_designs.py` | C，补入口后保留 | 采纳 | Module docstring 与 httpx2 plan 补 `PROBE_CORE`／`PROBE_CAP`／`PROBE_SCENARIOS`、`attempts`／`rejects` 与 exit 语义；修正“httpcore 1.0.9 today”过期注释和 import order |
| `stage_migration.py` | D，不作长期工具；建议先留待裁 | **采纳分类，调整去向（C，暂定）** | 不删除、不修复成当前工具、不留在 live experiment 根。原文移入 `exp/httpx2-migration/archive-260821/`，旁置 README 说明它只服务当时五个混合 WIP 文件、Usage 与 argparse 不一致、不得对当前工作树运行 `--write`。这样既不把它呈现成 living tool，也不让 `.dev` 永久保留一个无人负责的未跟踪文件 |
| 16 个 `verification/` 文件 | A，完整历史归档 | 采纳 | 新建 `docs/early-verification/README.md`，按 2026-07-15 Phase 3、07-16 final、07-17 Hooks／Tokenization 三个 archive 保存原件；旧 `verification/` 下剩余文件为 0。入口明确当前 authority 是项目根 `CLAUDE.md` 与主仓 `tests/`，旧 runner 不从新路径运行，不把历史 PASS 当 current verdict |
| 调查报告自身 | B，处置后归档 | 采纳 | 从 `docs/tmp/` 移入 `docs/git-housekeeping/reports/`，本处置账单独记录实际决定；调查原文不改写成 terminal prose |

## Living carrier 同步

### Direct passthrough

Spec v22 把 2026-09-01 用户已经裁定的“直连与翻译的块级交付路径原生 continuation”从方向性要求闭成当前两种 applicable block-aware 生成方言——Anthropic Messages 与 OpenAI Responses——上的可实施合同，但不把实现写成已完成。Passthrough 整体定义域仍覆盖所有 `translation_required is False` 路由；Chat Completions 块级解析继续作为独立推迟项，Embeddings 不适用 continuation。Plan §11 将策略与 driver 通过 typed `ContinuationDecision`／`ContinuationIntent`／`EndingAction` 连接：策略负责领域 eligibility 和 observation，driver 负责 replay ledger、commit frontier、顺序、取消、发送与 emitted effect；数据可见而职责不越界。D-7、D-6、side facts、当前 `signature_delta` reshape 与 selector 属同一个对外完成边界，但可以是不同 semantic commits。

### Project review principles

260903 报告的三条产品 finding 不再只活在报告里。`PPR-260903-01` native side facts 由 direct-passthrough Spec §10 与 plan §11.7 承接；`PPR-260903-02` count usage observation 与 `PPR-260903-03` 三处越权承诺面进入 `docs/project-review-principles-skill/deferred.md`。同轮还证实主仓 skill 的“当前状态”和三组候选命令已腐坏；本次用户只要求合并提交 `.dev`，没有顺带修改主仓指令文本，因此作为 deferred D-1 登记，并明确其未来属于 B 级跨模型评审。

### httpx2 migration

Plan 不再把核心迁移写成仍在实施，也没有反向假装所有散文审计完成。核心依赖、stream cap、WebSocket、OTel 与迁移回归标为历史完成；原 V2 由 2026-08-23 current-stack 实测及当前 normalization 承接；剩余 `httpx` 文本因混有历史版本、logger／module 真实名字与可能的过期包名，继续标为未逐条闭合的残余项，未以命中数判定完成。

## 验证记录

- Cap 探针按文档示例运行：`PROBE_CORE=httpcore2 PROBE_CAP=1 PROBE_SCENARIOS='50,100 200,100 500,100' uv run python .dev/exp/httpx2-migration/probe_cap_designs.py`。httpcore2 2.12.0 下，`not_available` 在全部场景 `peak=1`、`closed_in_use=0`；200 burst 的 attempts/rejects 为 362/162 与 374/174，500 burst 为 1814/1314 与 1799/1299。该结果足以验证参数入口与输出，不能冒充生产负载测量。
- `uv run ruff check .dev/exp/httpx2-migration/probe_cap_designs.py` 初次准确报 I001；根因是新增 `importlib`／`os` 被放在标准库 import block 后半。最小重排后复跑 clean；`python -m py_compile` 通过。
- `docs/early-verification/` 共 17 文件：原始 16 个验收资产加新入口 README；旧 `verification/` 下文件数为 0。

## 未采纳与暂定裁定

1. **未采纳“所有 untracked 原位直接提交”**：它会让 next-root analysis 成为第二份 living plan，让旧 verification 冒充当前工具，也让一次性 private-index helper 看起来可复用。
2. **未采纳“verification 陈旧即删除”**：报告与 probe 是同一个点时 artifact，删除脚本会留下无方法的 PASS／BLOCKER；完整归档后再讨论去重才有可逆基线。
3. **未采纳“把旧 verification 修到当前可跑”**：当前项目已有测试与验证命令，现代化旧 suite 会制造第二套 proof system，并伪造 2026-07-15～17 的执行记录。
4. **未采纳“顺带修改主仓 project-review-principles skill”**：这会扩大用户只指定 `.dev` 的提交范围，且指令文本修改需要 B 级未卷入跨模型评审；本轮把已确认问题登记到该主题 deferred，不让它消失。
5. **暂定调整 D 类去向**：调查建议把 `stage_migration.py` 留作未跟踪文件等待裁定；本处置改为原样归档并明确禁止当前使用。理由是用户要求合并并提交 `.dev`，归档完整保留字节而不把它放在 live tool 面。此项交原调查者复核；若其指出归档会产生具体误导或丢失，本轮在提交前改正。
6. **未采纳“httpx2 核心迁移完成＝步骤 4 全部完成”**：没有逐条处置账就没有这个结论，残余散文审计继续保持 open。

## 最终候选评审处置

原调查者首轮发现 Spec 两条 major：upstream-native terminal 原样承诺与 synthetic continuation terminal 冲突，以及 non-stream item 错写 event-level `output_index`。两条均采纳并修正；第二轮 [`260904-dotdev-dirty-inventory-disposition-recheck-r2.md`](260904-dotdev-dirty-inventory-disposition-recheck-r2.md) 判 pass、0 blocker、0 major。

未卷入跨模型 reviewer 的首轮报告是 [`260904-dotdev-merge-review-gpt-opus.md`](260904-dotdev-merge-review-gpt-opus.md)，共 1 blocker／4 major，全部采纳（C 级）：

| Finding | 处置 |
|---|---|
| F-01 held complete units 无 final action | Spec §5.3／§7.2 与 plan §11 明确：replay 不发生时，`full`／未触发 `until-tool-use` 持有的完整 group 先进入 commit frontier，再作为普通 failure continuation 的进展事实；补齐 `EndingAction` |
| F-02 max-token 被完整单位前提收窄 | 按用户亲笔合同恢复特例：丢弃未完成单位后，零完整单位也可 continuation，synthetic call 可成为唯一 content／output；普通 failure 仍需已交付或 held-and-about-to-commit 的完整单位 |
| F-03 未定义 budget 可能制造 continuation 上限 | 删除 eligibility 的模糊预算门；明确 continuation 无次数预算，replay ledger 只决定 `REPLAY` 且在 policy 前读取；deadline／protection／no-write 各用具名 condition |
| F-04 “每条直连腿”被两方言实现静默缩域 | 对照人写合同与 2026-08-22 Chat Completions 推迟裁决，确认错误在本规格的过宽转述。§2.6 明定 applicability 为当前能识别完整生成单位并能表达 executable synthetic call 的 Anthropic Messages／OpenAI Responses；Chat Completions 块级解析仍为独立欠项，Embeddings 不适用。v15 revision 明标“每条”不是用户原话 |
| F-05 current 正文保留已推翻状态 | §2.5 去掉方言无关全称；§5／§7.2／§8 同步 continuation finalization；§6.6 改为已实现、默认关，并从 deferred 删除已闭合 D-3；Spec v22 修订行同步覆盖所有更正 |

没有驳回 finding，也没有暂定驳回。本次整改没有把 reviewer 的可选建议扩成 proof framework；只修 authoritative contract 与其 plan/deferred restatements。

## 评审收口

同一跨模型 reviewer 的第二轮关闭 F-01、F-02、F-03、F-05，留下 F-04 两处 mutable restatement；同步 plan 顶部与本处置账后，第三轮 [`260904-dotdev-merge-review-gpt-opus-r3.md`](260904-dotdev-merge-review-gpt-opus-r3.md) 判 pass，remaining blocker=0、major=0、minor=0，未引入相邻 blocker／major。

文档处置与独立评审已闭合；余下动作只有本地链接、脚本、Git 范围核验和按语义提交。用户未授权推送，本轮不推送。
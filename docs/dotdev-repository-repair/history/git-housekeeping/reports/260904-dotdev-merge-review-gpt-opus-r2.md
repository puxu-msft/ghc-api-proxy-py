# `.dev` 合并候选最终评审窄复评

日期：2026-09-04。

评审对象：当前 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-passthrough/spec.md`、`plan.md`、`deferred.md`，首轮报告 `docs/git-housekeeping/reports/260904-dotdev-merge-review-gpt-opus.md`，以及 `docs/git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition.md` 的最终候选评审处置。范围严格限于首轮 F-01～F-05 及整改触及的 §5.1、§5.3、§7.2、§8、§9.2、plan §11、deferred D-4／D-5／D-6／D-7、v22 revision；只读，没有修改或新建文件。

## Verdict

**needs-fix。** 首轮 5 条 finding 中 4 条 closed，F-04 仍 open；remaining blocker=0、remaining major=1、remaining minor=0。没有发现独立于首轮范围的新 blocker／major。

## 首轮 finding 逐条复评

### F-01　closed

`spec.md:295-303` 现在给出互斥 final-action 全表；`:300` 明确覆盖 replay 不可用／被拒／replacement 未建立且 streaming 已交付或持有完整单位的普通 failure，并点名 `full` 与未触发的 `until-tool-use`。`spec.md:580-603` 又规定 held group 在 §7.2 步骤 2 进入 commit frontier，随后只执行一个 final action；`:623-632` 将同一结果传播到 policy × ending 总表。`plan.md:458-461,484-486` 要求真实 driver 覆盖该场景，`deferred.md:75-76` 同步完成边界。原来没有 `EndingAction` 的状态已有唯一落点，未再用“预算”假装 decline。

### F-02　closed

`spec.md:277` 把完整单位前提按 ending 拆开：普通 failure 需要已交付或 held-and-about-to-commit 的完整单位，`max_tokens`／`max_output_tokens` 明确不需要；`:301` 给零完整单位单独的 `EMIT_CONTINUATION` 行，`:583,591,629` 传播到 §7.2，`:709-710` 对 non-stream 两方言都允许 synthetic call 成为唯一 `content`／`output`。`plan.md:460-461,477,485` 同时保存正向控制，`deferred.md:57` 仍明确 max-token 是既有用户裁决。首轮指出的可观察行为收窄已消除。

### F-03　closed

`spec.md:275-281` 现在分开 `ContinuationDecision` 与 requested-only intent，逐字声明 continuation 没有次数预算；replay ledger 只在 policy 前决定 `REPLAY`，deadline／protection／no-write 使用具名条件。`plan.md:431-443` 将 policy、driver、adapter 的所有者与生命周期分开，`:439` 明确 observations、intent、proposed／emitted effect 的真值时点，`:452` 要求测试“replay ledger 拒绝不冒充 policy decline”。`dirty-inventory-disposition.md:64` 的处置与此一致。没有 continuation budget，也没有让 driver 依据 raw error 二次裁 eligibility。

### F-04　open（major）

规范主体和 §11 实施边界已经正确收窄：`spec.md:89-100` 保留 passthrough 整体对全部 `translation_required is False` 路由的定义域，同时把 continuation applicability 明定为当前能识别完整生成单位并表达 executable synthetic call 的 Anthropic Messages／OpenAI Responses；Chat Completions 块级解析继续按既有裁决推迟，Embeddings 明确不适用。`spec.md:307`、`plan.md:425-427,498`、`deferred.md:53-76` 与 v22／v15 修订记录 `spec.md:769,777` 均与此一致。

但两个当前 mutable restatement 仍保留被本次整改否掉的广义措辞：`plan.md:3` 仍写“**用户已裁的每腿原生 continuation**”，`docs/git-housekeeping/reports/260904-dotdev-dirty-inventory-disposition.md:29` 仍写用户已经裁定“**每条直连腿原生 continuation**”。后者同一文件 `:65` 又说“每条”是本规格过宽转述，前后冲突；前者位于实施计划顶部状态，比 §11 更先被读到，并把模型自己的全称错误归给用户。

因此 F-04 的 normative applicability 和实施任务已修，但当前计划／处置状态没有闭包，不能判 closed。需把 `plan.md:3` 与处置账 `:29` 同步为“当前两种 applicable block-aware 生成方言”，并保留 passthrough 整体定义域、Chat Completions 独立推迟项与 Embeddings 不适用三者的区别；这不是改报告原件。

### F-05　closed

`spec.md:68-72` 已撤掉 §§5～10 全部方言无关的全称并列出 adapter 差异；`:221,229-235,273-307,636-643` 已把 §5／§8 当前状态同步为统一 continuation finalization；`:456-470,532-536` 将 §6.6 明确标成已实现、默认关、显式 opt-in。`deferred.md` 当前从 D-2 直接到 D-4，已闭合 D-3 不再占 living ledger。v22 revision `spec.md:765-769` 同步列出上述更正及 F-01～F-04 的合同变化；顶部仍为 v22 待复评，与当前阶段一致。

## 相邻合同检查

- `spec.md:229-235` 的 §5.1 将 native failure、clean EOF 与 replacement 未建立分别路由到 replay 后的 §7.2／§5.3，没有重新制造旧 terminal 与 replacement failure 双 carrier。
- `spec.md:273-307`、`:570-643` 的 decision、action、policy ending 与 failure／EOF 表使用同一组 typed action；`EMIT_CONTINUATION` 是 `EMIT_UPSTREAM_ENDING` 原样承诺的具名例外，没有重开 synthetic terminal 冲突。
- `spec.md:703-714` 的 §9.2 与 streaming 共用 decision，明确 max-token 零完整单位、Responses non-stream 位置由数组索引表达而不写 event-level `output_index`；未发现新 blocker／major。
- `plan.md:425-500` 将 D-7、streaming、writers、whole-body、D-6、side facts、reshape、selector 分为 semantic commits而共享对外完成边界，没有新 proof framework。
- `deferred.md:34-50` 正确区分 D-4 当前默认必须保留与长期常驻性待裁；`:53-108` 的 D-5／D-6／D-7 状态和依赖与 Spec／plan 一致。D-4 `:44` 的“不阻塞接线”只能读作“不需要新的用户裁决”，而实现仍由 plan §11.7 作为 selector 前置；该措辞有轻微歧义，但不足以在本轮升为 major。

## 未采纳建议

无。唯一 remaining major 是首轮 F-04 的 current-state restatement 未同步；没有新增可选机制、测试治理或 proof framework 建议。

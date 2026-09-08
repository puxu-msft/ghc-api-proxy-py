# nested dotdev 冲突处置与 re-root 门最终复核

## 评审范围

- **目标**：复核 `.dev/docs/multi-provider-routing/reports/260908-nested-dotdev-conflict-disposition.md` 对嵌套树三份未提交文档的处置，并判断当前状态能否进入 archive-ref + final `.dev` checkpoint。
- **被检对象**：active `.dev/docs/multi-provider-routing/{deferred.md,spec.md,review-disposition.md}`，nested `.dev/.dev/docs/multi-provider-routing/` 的对应三份 tracked 修改，active `history/` 的两份 snapshot 与索引，冲突处置报告，repair README/final ledger/final-pre-reroot review，以及当前 active docs、retired paths、top-level `tmp`、retained/current consumers 和相关只读 Git 状态。
- **判据来源**：本次委托的六项核验要求；repair README 规定的“final scan → checkpoint → re-root”顺序；`as-reviewer` 对用户裁决归属必须有一手逐字来源或可逐字回指锚的要求。被检报告与既有 review 的自述仅作为待核验 claim。
- **明确排除**：执行 archive ref、checkpoint、re-root/worktree 挂载、产品测试或 retained topic 未完成工作的验收；任何被检对象的修改、移动、删除，以及 `git add`、commit、push。
- **只读边界**：除按委托新增本报告外，未修改被检对象；所有 filesystem、hash、Git 与内容检查均为只读。

## 总体 verdict

**NEEDS-FIX。** 两份 snapshot 完整、active 文档确实保留并增强了 nested 的现行行为语义、三份 nested 修改边界准确，且既有 final-pre-reroot 结构门尚未观察到回退；但 current `review-disposition.md` 只有“用户本次裁决”的转述，没有用户逐字原话或可逐字回指的会话/材料锚。冲突处置报告把它称为“来源已保留”不成立。当前不应把这次冲突处置视为完成，也不应进入作为 re-root 前门的 archive-ref + final checkpoint。

## Blocker 数

**0**

## Findings

### CRR-01 — 所谓“已保留的用户裁决来源”只有无锚转述

- **severity**：major
- **status**：open；阻止本次冲突处置放行与 archive-ref + final checkpoint
- **primary_location**：`.dev/docs/multi-provider-routing/review-disposition.md:12-16`
- **related_locations**：
  - `.dev/docs/multi-provider-routing/reports/260908-nested-dotdev-conflict-disposition.md:14`
  - `.dev/docs/multi-provider-routing/history/README.md:6`
  - `.dev/docs/multi-provider-routing/history/260908-nested-dotdev-spec-before-reroot.md:16,349`
  - `.dev/docs/multi-provider-routing/history/260908-nested-dotdev-deferred-before-reroot.md:31`
- **claim**：current `review-disposition.md` 保存了裁决结论及其实施去向，但没有保存或链接用户的一手言语行为；因此不能证明该内容确为用户裁决，也不能承担冲突处置报告所称的“来源”角色。
- **evidence**：
  - `review-disposition.md:14` 仅转述“用户本次裁决改为：默认 provider 保留裸模型名，非默认 provider 额外公开 `provider/model` 限定名……”，没有引号中的逐字原话、用户消息标识、会话锚或一手文档链接；`:16` 只记录 Spec/commit/test 的落地去向。
  - 冲突处置报告 `:14` 自己承认“本次没有一手逐字材料”，却同时声称“该来源已在当前 `review-disposition.md` 保留”；history README `:6` 又传播同一 claim。转述可以保存结论，不能补出缺失的一手来源。
  - 全面搜索 active `.dev/docs` 与 `.dev/human-controlled-docs-candidates` 中关于 `secondary provider`、`ttthree`、自动发现与限定名的记录，只找到该转述、nested snapshot 中同样无锚的“用户直接裁决”标签，以及实现/status 文档；未找到能逐字回指 2026-09-08 用户发言的锚。这里不据此断言用户从未作出裁决，只判定当前被检材料未举证。
  - nested `review-disposition.md` 的未提交增量正是新增 `:12-16` 这三段；active 与 nested 文件 SHA-256 相同，说明合并没有漏掉这段转述，但“同内容”不能提升其来源证据等级。
- **impact**：re-root/checkpoint 后，未来会话会把一项外部可见行为永久视为 `resolved-by-user`，却无法复核用户是否作出陈述、陈述范围是否覆盖 `/v1/models`、`/api/status.routes`、默认/非默认 provider 和 ttthree 示例。snapshot 虽保留旧措辞，也只保留同一无锚归属，不能恢复来源。
- **minimal_next_step**：若可访问原始用户消息，给 `review-disposition.md` 增加逐字引文及稳定会话/材料锚，并逐项限定其覆盖范围；若不可访问，则停止传播“用户裁决来源已保留”，把归属改为可证实的事实（例如 2026-09-08 决策记录/实现提交），保留后续回填一手来源的出口。随后同步修正冲突处置报告与 history README 的“来源”表述，再做限域复核。

## 六项核验结果

### 1. 两份 snapshot 与 nested 原件：PASS

| snapshot / nested 原件 | SHA-256 | 逐字比较 |
|---|---|---|
| `history/260908-nested-dotdev-deferred-before-reroot.md` / `.dev/.dev/docs/multi-provider-routing/deferred.md` | `bdabbd7a05e67e0359ceda73b3e66b01df8eace3a1a040a591c9efef02ba4b15` | `cmp` exit 0 |
| `history/260908-nested-dotdev-spec-before-reroot.md` / `.dev/.dev/docs/multi-provider-routing/spec.md` | `9a9d2ba23f6b7e27ea6c4425e40552caf56e9b81e63bb524319a8968cf3f0adf` | `cmp` exit 0 |

两个 digest 与冲突处置报告记录完全一致。snapshot 是 nested 当前未提交字节的保真副本，不只是语义近似。

### 2. active `deferred.md` / `spec.md` 的语义承接和证据增强：PASS

- `deferred.md` 两侧的 D-1、D-2、D-4 字节内容相同；D-3 的差异是重排与证据边界收紧。nested `:27-33` 说 secondary provider 限定目录名已获裁决、剩四项待确认；active `:39-45` 保留同样四项——mapping 键候选、两类新增 WARN、mapping 值 `@format`、路径参数端点作用面——并把已落地行为锚到 `52d57a09`。没有把四项中的任何一项误关。
- active Spec `:284,298-304,351-355` 仍明确规定：非 default provider 公开 `provider/model` 限定名；裸目录、限定目录与 mapping 键共同生成候选；模型列表只返回 serviceable 项；`/api/status.routes` 保留非 serviceable 诊断状态；`owned_by` 是实际 provider；三个模型列表入口支持按最终 `owned_by` 精确 `provider` 筛选。nested 的 secondary provider 可发现行为没有丢失。
- active Spec `:36-37,614` 比 nested 多出实现/测试锚：`52d57a09`、`3b223e8e`、`tests/int/test_pipeline_ops_routes.py`，并把测试面从单个 `/v1/models` 扩写到 `/models`、`/v1/models`、`/openai/v1/models`、限定目录、serviceability、去重与 provider filter。
- 只读核对提交内容：`52d57a09` 在 `routing.py` 增加 non-default qualified catalog 候选，并新增 `test_the_model_list_exposes_non_default_catalogs_with_provider_qualifiers`；同一提交还先加入 provider filter 测试。紧随其后的 `3b223e8e` 在 `ops.py` 以 `row.provider == provider_name` 实现精确筛选。若移除 qualified 候选，测试取 `entries["ttthree/secondary-model"]` 会失败；若移除 filter，断言只含 A 的两个条目会收到 B 的条目，证据对相应机制有分辨力。
- 未运行产品测试：本次是只读文档/历史复核；上述结论来自提交 diff、测试断言与最终文档交叉对账，不把未实跑结果表述为“tests green”。

active Spec `:280` 把请求体端点语法的用途单独表述为人工调试，而 `:284` 紧接着明确相同可路由名称用于 secondary provider 自动发现；这是把请求端点作用面与目录行为拆开说明，不是撤销 nested 的自动发现语义。

### 3. current `review-disposition.md` 的裁决记录与来源：PARTIAL / MAJOR

- **记录未丢**：`:12-16` 有“2026-09-08 后续裁决：自动发现 secondary provider 模型”，覆盖默认 provider 裸名、非默认 provider `provider/model` 限定名、ttthree 自动发现、Spec 落点、`52d57a0` 与测试文件；这正是 nested Spec `:16,279,283,297-300,349-351,612` 依赖的新增结论。
- **来源未保全**：该段没有一手逐字原话或可逐字回指锚，不能支持“用户裁决来源已保留”。详见 CRR-01。故“合并没有漏段落”为 PASS，“避免合并丢失来源”为不成立。

### 4. nested 与 active `review-disposition.md`：PASS

两份文件 SHA-256 均为 `e337be6bc2c4eeaac50b576f0568ba239fe639ca7c23baf211cc584a226a6eae`，`cmp` exit 0。冲突处置报告“无需合并、两侧相同”的机械 claim 成立；CRR-01 是两侧共同存在的 provenance 缺口，不是 active 合并漏字节。

### 5. nested tracked `.dev/docs` 的额外未提交修改：PASS

以 nested repository root `.dev/` 执行只读 scoped status，tracked `.dev/docs` 只有：

```text
 M .dev/docs/multi-provider-routing/deferred.md
 M .dev/docs/multi-provider-routing/review-disposition.md
 M .dev/docs/multi-provider-routing/spec.md
```

排除这三条后的 tracked modification count=`0`。未把 active direct-root `docs/` 的 untracked 目标树混入“nested tracked `.dev/docs`”口径。

### 6. active docs、retirement 与 final-pre-reroot 前置：基础结构 PASS；冲突门仍被 CRR-01 阻止

- active `.dev/docs/` 顶层共有 29 个 retained topic/mechanism directories；`httpx2-migration`、`systemd-runtime`、`interaction-context`、`multi-provider-routing` 均存在。`multi-provider-routing` 根级 current docs 包含 `README.md`、`deferred.md`、`review-disposition.md`、`spec.md`、`status.md`。
- 15 个 retired path 均为 absent，且同时用 `-e` / `-L` 检查，未发现 dangling symlink：`architecture-audit`、`archived-2604-rewrite`、`copilot-token-identity`、`count-tokens`、`docs-tmp-migration`、`documentation-restructure`、`early-verification`、`empty-text-block`、`git-housekeeping`、top-level `history`、`hooks-subscription-migration`、`lifecycle-reorg`、`pipeline-rewrite-parity`、`sync-refs`、`test-infrastructure`。
- `.dev/docs/tmp/` 机制目录存在，top-level regular files=`0`。
- 对 retained/current docs 与 evidence（排除任一 `reports/`、`history/`、`archive*` component 和整个 repair control-plane）、`src/`、`tests/`、`pyproject.toml`、active `.dev/README.md` 共 1350 个路径，扫描 15 个 retired exact path、`docs/2604-rewrite` legacy alias 与具体 `.dev/docs/tmp/<child>` literal，current consumer hits=`0`。
- 上轮 final-pre-reroot review 的后时点附录仍是文件末尾；其 FPRR-01 两个 source comment 当前分别指向存在的 `token-counting/history/2604-rewrite/tokenization.md` 与 `ghe-device-flow/history/260822-ghc-api-conformance-summary.md`。FPRR-02 当前 href 明确指向 `deferred.md#...`，且 target heading 位于 `deferred.md:303`。本轮 broad scan 未观察到这两个已关闭项回退。
- 因而，既有 final-pre-reroot review 对 **retired/tmp/legacy consumer 门** 的 PASS 仍成立；但它早于本次 conflict disposition，且其附录明确没有提前授权 re-root。新增冲突处置必须作为 checkpoint 前的逐路径核对内容接受复核。CRR-01 使本次新增内容尚不能进入 final checkpoint。

## archive-ref + checkpoint 门判定

- **当前不能进入 archive-ref + final checkpoint 的组合阶段。** 不是 snapshot 或 tree integrity 失败，而是冲突处置把一个无一手锚的转述提升为“用户裁决来源已保留”。final checkpoint 的目的包括可审查、可恢复；冻结这个归属会把不可复核的 authority claim 一并固化。
- 修复 CRR-01 后只需限域复核三点：`review-disposition.md` 的一手锚与覆盖范围；冲突处置报告/history README 不再夸大来源；两份 snapshot 和三份 nested status/hash 未发生漂移。通过后，现有 15 paths/tmp/consumer 基础门支持进入 archive-ref + final checkpoint。
- archive ref 即使单独作为历史保险，也不能替代 provenance 修复：它能保留旧 blob/commit ancestry，不能把没有写入任何 blob 的用户逐字来源补回来。本报告未执行或授权任何 ref/checkpoint 操作。

## Severity 汇总

| severity | count |
|---|---:|
| blocker | 0 |
| major | 1 |
| minor | 0 |

未发现 blocker 或 minor。唯一 major 是 authority provenance；其修复不要求改行为或重做 snapshot，但在 final checkpoint 前必须闭合。

## 搜索面与执行记录

- 内容对比：完整 diff active/nested `deferred.md`；完整 hunk map 与承重段逐段读取 active/nested `spec.md`；完整读取两侧相同的 74 行 `review-disposition.md`；读取 snapshot/history index 与冲突处置报告。
- integrity：四次 `sha256sum` 核对两个 snapshot/nested pair；三次 `cmp` 核对两个 snapshot pair 和 active/nested review pair。
- Git：主仓状态只用于识别外部并行修改；nested repository 以 `git -C .dev status --short --untracked-files=no -- .dev/docs` 限域核对；读取 nested diff 与 `52d57a09`、`3b223e8e` 的提交/测试 diff。没有执行 stage、commit、push 或 ref 操作。
- repair 门：读取 repair README、final ledger、pre-reroot review、final-pre-reroot review及其后时点附录；复核 15 paths、top-level `tmp`、active direct-root children、retained key paths、旧 consumer 和附录三个修复锚。
- authority 搜索：在 active `.dev/docs` 与 `.dev/human-controlled-docs-candidates` 搜索 secondary provider、ttthree、自动发现、限定名相关记录；没有找到 2026-09-08 用户逐字裁决锚。该负面结果只证明被检材料未举证，不外推为“用户从未说过”。
- 未运行产品 tests、网络请求或真实 provider canary；它们不是本次文档冲突与 repository 结构门的 ground truth。

---

## 附录：CRR-01 限域复审（2026-09-08）

### 范围与结论

本附录只复审 CRR-01，不重新执行或扩大正文的 tree/consumer/final-pre-reroot 全面检查。只读核对：

- `multi-provider-routing/review-disposition.md` 的 2026-09-08 段；
- `reports/260908-nested-dotdev-conflict-disposition.md`；
- `history/README.md`；
- 两份 `history/260908-nested-dotdev-*-before-reroot.md` snapshot。

**限域 verdict：PASS。CRR-01=closed。可以进入 archive-ref + final checkpoint。** 本附录的后时点结论取代正文中仅由 CRR-01 导致的 NEEDS-FIX 和 gate 拒绝；它不宣称 archive ref 或 checkpoint 已执行，也不提前验收其内容或恢复性。

### CRR-01：closed

- current `review-disposition.md:12` 已把标题从“后续裁决”改为“后续记录”；`:14` 将内容限定为“2026-09-08 的开发记录将当前行为记为”，并明确“本目录未保留该记录的一手逐字锚，因此这段只能说明当时的记录和实现结论，不能单独证明用户裁决的来源或覆盖范围”。它不再把无锚转述升级为已保留的用户裁决来源。
- conflict disposition 的 `spec.md` 处置行现明确区分三层：nested 较宽的“用户直接裁决”措辞不回写；current `review-disposition.md` 只保留当时转述；一手逐字来源未保留，故“不能扩写或传播该归属”。没有继续传播正文 CRR-01 所指出的“来源已保留”claim。
- `history/README.md` 同样只称 current disposition 保存“当时转述及实现去向”，并明写“没有一手逐字来源”。snapshot 里的旧归属措辞因此被保留为 point-in-time 原文，而不是由 history index 提升为 current authority。
- 三处当前材料都采用“缺少可举证来源／不能单独证明”的证据边界，没有写成“用户未作过裁决”或任何等价否定。它们保留了未来取得一手锚后重新核验的空间。

### current behavior 的实现与测试来源仍在

- `review-disposition.md:16` 继续记录行为落点：Spec §3.3、§4.1、§4.2.1，实施提交 `52d57a0`，以及覆盖目录生成、provider filtering、`owned_by` 的 `tests/int/test_pipeline_ops_routes.py`。
- conflict disposition 继续记录 active Spec 的增强来源：`52d57a09` 的 secondary provider 限定目录行为、`3b223e8e` 的 `provider` 筛选、serviceability 区分及测试依据。
- 修复只收窄 authority attribution，没有撤销或弱化 current behavior，也没有把实现/测试事实重新归给用户。

### snapshots 完整且未被改写

| snapshot | 当前 SHA-256 | 正文既有 SHA-256 | 行数 | 结论 |
|---|---|---|---:|---|
| `260908-nested-dotdev-deferred-before-reroot.md` | `bdabbd7a05e67e0359ceda73b3e66b01df8eace3a1a040a591c9efef02ba4b15` | 相同 | 45 | unchanged |
| `260908-nested-dotdev-spec-before-reroot.md` | `9a9d2ba23f6b7e27ea6c4425e40552caf56e9b81e63bb524319a8968cf3f0adf` | 相同 | 648 | unchanged |

snapshot 中原有的“用户已单独裁定”／“用户直接裁决”措辞仍逐字存在；这是完整性所要求的冲突前原文。current disposition 与 history index 已明确不把这些无锚历史措辞当作一手来源，故保真与停止传播错误归属可以同时成立。

### archive-ref + final checkpoint 门

CRR-01 的唯一开放问题已关闭。结合正文已经通过且本附录未重新推翻的 snapshot integrity、active behavior、nested tracked 修改边界、15 retired paths、top-level `tmp=0`、current consumer=`0` 与 final-pre-reroot 后时点前置，**现在可以进入 archive-ref + final checkpoint**。顺序与边界仍为：

1. 先建立并核对 archive ref，确保旧 nested ancestor chain 可恢复；
2. 再建立可审查、可恢复的 final `.dev` checkpoint，并逐路径核对 active direct-root 与 nested tracked tree；
3. checkpoint 自身审查通过后，才进入 re-root/worktree 挂载与其后验收。

本次限域复审除追加本附录外未修改、移动或删除被检对象，未执行 `git add`、commit、push、archive ref、checkpoint、re-root 或 worktree 挂载。

### 限域复审后的有效 severity

| severity | open count |
|---|---:|
| blocker | 0 |
| major | 0 |
| minor | 0 |

# 收尾产物独立评审

## 结论

**VERDICT：needs-fix。** 未发现 blocker；发现 5 项 major、3 项 minor。变异表的 8 行均准确，因此没有触发任务指定的 blocker 条件；主要问题集中在 marker 的人口与 carrier 对账不闭合、已明确发现的非文件事件仍被清单遗漏，以及 living docs 仍保留已被评审证伪的解释。

本结论的证据强度为“足以据此修正收尾产物”。依据是对 transcript、当前文件、Git object 与隔离 clone 中的实际变异运行做了独立交叉核验，而不是复述作者清单。

## 评审锚点与枚举方法

- 主 transcript：`/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/5bd4e615-2897-4257-bd05-3151f8ee5c8e.jsonl`，2593 行，2593 行均可解析，时间窗 `2026-08-23T06:40:29.670Z` ～ `2026-08-23T11:19:01.769Z`。
- 在本评审开始前已经完成的 subagent transcript 实际有 **6 份而不是派发提示写的 5 份**：`agent-a5d24ceed34a5d735`、`agent-a21d14c62c1ed9d35`、`agent-a24cc23e566dcee80`、`agent-a0e567ed141a54418`、`agent-a9cf0ef9dcf89b239`、`agent-a14e335a529db6ccc`。当前评审自己的 `agent-a66d20f11511dd2be` 不计入被审 session 人口。
- 覆盖范围：主 transcript 的 282 次 tool call、170 个 assistant text block、145 个 assistant thinking block，以及上述 6 份历史 subagent transcript 的全部已解析消息。先提取事件，再读取 `/home/xp/.claude/jobs/5bd4e615/tmp/DISPOSITION.md`，避免被 marker 锚定。
- Git 锚点：主仓 `e0c7ed4302d979c0cd08f60be3df5ee0b9253f2f`，`.dev` 仓 `3e3b3137114d5337f6d5d97df5578ef5284cf7ef`。

## 发现汇总

### Major

#### M1．marker 的人口与 commit-message carrier 对账未闭合

`DISPOSITION.md:6-8` 冻结了 23 个原始文件，并把 marker 自己列成第 24 个；但关闭 marker 的同一个 Bash 调用随后又创建了 `commit-dev-8.txt`，当前 `find` 与 `fd -H -I` 都返回 **25**，集合完全一致。第 25 个文件没有出现在 marker 的任何类别中。证据：主 transcript `:2555-2557` 先改 marker，随后创建 `commit-dev-8.txt` 并提交 `3e3b313`；当前命令输出为 `find_count=25`、`fd_count=25`、双向差集均为空。

`DISPOSITION.md:14` 还把 12 份 commit-message 输入映射到 11 个哈希。所列 11 个哈希全部存在，且各自完整 commit message 与对应文件逐字匹配；但第 12 份 `commit-dev-2.txt` 的真实 carrier 是被漏列的 `.dev` commit `31db448`。当前又多出 `commit-dev-8.txt` → `3e3b313`，所以磁盘现状是 **13 个 commit-message 文件、13 个逐字匹配的 commit object**。独立映射结果：`commit-dev-2.txt` → `31db448`，`commit-dev-8.txt` → `3e3b313`，其余 11 个与 marker 所列哈希一致。

这不是数据已丢失：13 个 carrier 都存在。问题是 marker 声称的分类人口与它实际制造出的终态不一致，不能据此说目录已完整处置。

#### M2．restore-backup 类的 durable carrier 断言对 1 个文件不成立

`DISPOSITION.md:16` 声称 6 个 restore backup 的 mutated state 已恢复并提交，committed state 是 durable copy。对 5 个文件成立；对 `auto_mode_classifier.py.bak` 不成立。独立执行 `git hash-object` 后，以 `git rev-list --objects --all` 对主仓所有可达 object 交叉验证：该文件 blob 为 `e0e177c8bcef962e9f8f98edec21cd7591095682`，`reachable=False`，也不等于当前源文件。其余 5 个 backup blob 均可达，其中 `mutation-backups-v2/auto_mode_classifier.py` 与当前 classifier 相同，`driver.py.wiring.bak`、`mutation-backups-v2/driver.py` 与当前 driver 相同。

该 backup 是第一次手工变异前、第一轮评审尚未提交时的 classifier 快照；随后修复后的代码才进入 `2b28d07`。所以“committed state 是它的 durable copy”是错误 carrier 说明。当前没有删除，尚可诚实裁决：要么保存这个点时快照，要么明确承认它会随 job 过期并解释为何报告本身已足够；不能继续声称它已入 Git。

#### M3．非文件清单的边界声明与 transcript 中已明确发现的事件冲突

`DISPOSITION.md:35` 一方面诚实声明清单不是穷举，另一方面又声称“Every candidate that was discovered has a locatable receiver named above”。后一句不成立。作者在写 marker 前已经明确说出 `head -3` 截断、`grep -v` 误伤，以及多项被证伪的测试与解释，但这些不在 7 行表中，receiver 也没有“named above”。主 transcript 证据：`:2454` 明说 `head -3` 只看到一份、实际两份报告未提交；`:2489` 明说 `grep -v` 误伤 spec；`:2275-2308` 明说 reason wiring 的原测试绕过 driver，硬编码变异仍全绿。

更基础的人口也被低估：收尾开始时主会话称 session 派出 4 个 subagent 产物（主 transcript `:2439`），给本评审的派发提示又写 5 份；独立枚举得到 6 份历史完成 transcript。虽然 6 份的最终报告均在磁盘上，但这种人口误差正是 transcript-first closeout 要防的遗漏来源。

按下文 B 节的固定口径，独立事件清单共 26 类，7 类在 marker 中，**marker-minus-transcript 为空，transcript-minus-marker 有 19 类**。其中很多已经在 spec、status、deferred 或评审报告里有 carrier，问题不是知识全丢了，而是 marker 对“已发现候选均已列出并指明 receiver”的陈述不诚实。

#### M4．living docs 仍把已被评审证伪的 M2 理由写成强理由，并在 closed-item 注记中陈述已经失效的现状

`status.md:39` 仍把“尾部 `\n` 容易配错且静默失效”称为“更硬的理由”。但第二轮评审已经证明这条理由同样适用于保留为配置项的 M1，因而不具鉴别力；`spec.md:155` 已正确把它降为“次要的一条理由”“不足以单独支撑钉死的决定”。marker 自己也在 `DISPOSITION.md:26` 承认该解释被证伪。三者相互冲突。

`deferred.md:4` 说 D5 已关闭，因为“那两个键重新可配置”；当前 M2 恰恰已经再次降为常量，`deferred.md:8-18` 的 D6 又明确说它没有配置开关。关闭 D5 本身可以成立，因为“标量导致两个键都无处配置”的旧问题已消失；但现有关闭理由已不是当前事实，应改成“标量时代的整体能力损失已关闭，M2 后续按独立裁定钉死，其单独代价见 D6”。

相同的过强理由还残留在 production schema 注释 `src/app/config/schema.py:326-330`，而 spec 已经收窄。虽然本次不重新评审特性代码，这仍是 closeout 文档同步问题：同一裁决的当前 restatement 不应一处写“有限辅助”，另一处写“更硬／worse than noise”。

#### M5．用户候选文档仍重复了已经被第一轮评审指出的循环证据

`.dev/human-controlled-docs-candidates/auto-mode-classifier.md:55-60` 先说“两条判据在两个独立方向上验证过”，再把“2300 条真实请求全中”作为流量侧支持。对 M2 而言，这 2300 条正是用 `previewText LIKE '<transcript>%'` 选出来的，不能作为自身召回率的独立测量；`spec.md:47-51` 已专门写明这一点并给出非循环链。候选文档面向用户取用，证据强度一节却保留了已被证伪的较强说法，closeout 未完成同步。

### Minor

#### m1．候选文档有两个不能按所在位置解析的相对引用

逐行提取 4 份 living docs 的 inline file references，并对固定提交逐个执行 `git cat-file -e <commit>:<path>`，共得到 29 个“文档—路径”对，27 个可达，2 个失败：`.dev/human-controlled-docs-candidates/auto-mode-classifier.md:51` 的裸 `spec.md` 与 `deferred.md` 会按候选目录解析成 `.dev/human-controlled-docs-candidates/spec.md`、`.dev/human-controlled-docs-candidates/deferred.md`，二者不存在。该行后半已经给了完整的 `.dev/docs/auto-mode-classifier/spec.md`，但 `deferred.md` 没有等价的完整引用。

#### m2．status/spec 仍有低风险的当前状态陈旧项

`status.md:56` 写全量覆盖率 89.56%，而最终修复后的全量命令在主 transcript `:2389-2391` 返回 `1545 passed, 2 skipped, Total coverage: 89.88%`。89.56% 是较早阶段的结果，不是最终候选。

`status.md:10` 只写初始两次提交并称“随后一次配置项改名”，没有反映后续结构化、M2 常量化、第二轮修复与 `.dev` 收尾提交；后文虽描述行为演进，当前提交状态句本身已过期。`spec.md:2` 在实现、两轮评审和提交完成后仍标“状态：草案”，与 `status.md:8` 的“实现完成”不协调。它们不改变行为，但不符合 living docs 的当前状态职责。

#### m3．保留报告原件中的旧路径是正确选择，但需要在 living doc 补一句迁移说明

报告原件中保留 3 处旧路径：`260823-auto-mode-traffic-samples.md:10`、`260823-review-claude.md:20`、`:173`。不改是正确的：它们记录作者当时实际读到的位置，改写会伪造点时记录；项目规则也明确要求报告原件保留快照路径。

但旧路径现在确实不存在，直接从报告打开会断。当前只有 commit message 解释“原件不改”，living docs 没有同等说明。建议在 topic 的 status 或 evidence 段补一句“报告内部的 `docs/tmp` 路径是点时快照；当前位置见 `reports/`”，不改报告原文。

## A．marker 各断言核验

### A1．Population

**结论：major，不属实于 marker 声称的关闭终态。** 原始 census 的 23 与当时命令输出一致，marker 自身使其变 24；但关闭 marker 的同一调用随后创建 `commit-dev-8.txt`，当前两种方法一致返回 25。当前 25 个文件全部仍在，原始 23 个也一个不少。

独立命令结果：`find_count=25 find_unique=25`；`fd_count=25 fd_unique=25`；`find_only=[]`；`fd_only=[]`。

### A2．Commit-message inputs

**结论：列出的 11 个 carrier 均真实且 message 对得上，但 12 文件人口漏了 1 个 carrier；当前又新增第 13 个。** `commit-dev-2.txt` → `31db448` 未列；`commit-dev-8.txt` → `3e3b313` 在 marker 写完后产生。当前 13 份文件均有唯一、逐字一致的 commit message carrier。

### A3．Mutation drivers

**结论：pass，置信度高。** `status.md:59-68` 与 `verify_mutations_v2.py:17-66` 的符号、替换和顺序逐行一致。为避免依赖作者运行结果，我在 `/tmp/ghc-closeout-mutation-review.lWbpIW/repo` 的 isolated shared clone 重写脚本 ROOT/BACKUP 后运行；结果为 baseline 42 passed，8 个变异依次红 `4/2/2/2/1/2/1/2`，恢复后 42 passed，`mutations not caught by any test: none`。表足以重建最终 8 个变异，没有 blocker。

### A4．One-shot text fixers

**结论：pass，置信度高。** ECMAScript `\s` 显式字符类位于 `tests/unit/pipeline/test_auto_mode_classifier.py:101-108`；U+00E9、U+017F、U+0661、U+001C 的测试数据均以 `\u...` 形式存在于 `:448-463`，旁边注释说明与 Python 默认语义的差异。三个 fixer 的目标与当前产物一致。

### A5．Restore backups

**结论：major。** 6 个文件均还在，恢复运行当时也有 byte-identical 回执；但 durable carrier 断言对 `auto_mode_classifier.py.bak` 不成立，详见 M2。

### A6．“Nothing was deleted”

**结论：pass。** 原 census 的 23 个文件全部还在，另有 marker 与 `commit-dev-8.txt`，总数 25。没有删除证据。

## B．非文件候选双向对账

### B1．枚举口径与覆盖

只纳入以下事件：明确走过后放弃的实现／判据路线；明确提出后被反例或评审推翻的因果解释；命令成功返回但因 option、ignore、截断或过滤范围而读错的结果；实际改变被测代码的变异；实际改变结论强度的运行探针。排除普通文件读取、正常绿测试、单纯 lint 修复和未影响任何判断的工具报错。该口径覆盖主 transcript 的完整时间窗和 6 份历史 subagent transcript。

### B2．marker 有、transcript 找不到

**差集为空。查了，为空。** 7 行都能在 transcript 找到对应事件：bool 推断见主 transcript `:1594`、`:1979`；M2 静默配置理由及其证伪见 `:2107`、`:2267`；配置位置／形状演进见用户提示 `:1409`、`:1858`、`:2089` 及相邻提交；untracked pathspec 见 `:2455-2469`；ignored `.dev` 扫描见 `:2476-2483`；unbun 见 `:181-263` 与 `agent-a5d24ceed34a5d735`；最终 8 变异见 `:2376` 的输出。

### B3．每一行 receiver 核验

1. **bool 推断 → `status.md`：pass。** `status.md:37` 完整记录错误推断、YAML 1.1 论证为何不适用于 `passthrough`。
2. **M2 静默配置理由 → `spec.md`：pass，但存在冲突 restatement。** `spec.md:155` 正确写成有限辅助；`status.md:39` 与 schema 注释仍写成强理由，见 M4。
3. **配置路线 → `status.md`：pass。** `status.md:31-39` 按顺序记录原 `inbound`、标量误读、结构化最终形状、M2 后续常量化。
4. **untracked pathspec → memory：pass。** `/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/memory/git-commit-takes-the-whole-index.md:15` 记录失败形状与 `git cat-file -e` 判据。
5. **`rg` ignore → user rule：pass。** `/home/xp/.claude/rules/00-user/20-tool-use-preference.md:66` 明确说明 `.gitignore` 与 `-u/-uu/-uuu`。
6. **unbun → memory：部分通过。** `/home/xp/.claude/projects/-home-xp-src-ghc-api-proxy-py/memory/unbun-extracts-claude-code-source.md:10-20` 承载提取方法、产物和三版本对照能力；“三版本实际比较得到什么”不在该 memory，真实 carrier 是 `reports/260823-cc-auto-mode-request-shape.md` 与 `spec.md`，marker 没有把它们命名为该行 receiver。
7. **8 变异 → `status.md`：pass。** 独立隔离运行验证见 A3。

### B4．transcript 有、marker 没有

**差集有 19 类，逐条如下。** 这些是“表中没有”，不等于都没有任何其他 carrier；括号里注明当前 receiver 或缺口。

1. 最初把接入路线定成 subscriber 识别 → raise → synthetic reply，后来实际改为 `handle()` 直接短路；marker 没记录路线放弃及原因（主 transcript `:165`，当前实现 `src/app/pipeline/driver.py:117-140`；spec 只记录终态）。
2. `max_tokens` 被提议为第四结构门槛后因 dynamic config 会改 token budget 而拒绝（`spec.md:45` 有 receiver）。
3. 把 M1 收窄到 `system[0]` 的路线被 attribution block 证据否决（`spec.md:33-37`、`status.md:105` 有 receiver）。
4. 一份评审把 B-05 当作“刻意攻击”判不成立，作者改以正常请求误伤为因果重新采纳结构门槛（`status.md:114-124` 有 receiver）。
5. “失效方向只会漏判、绝不会答错”的一般性承诺被 severity 协议与 100 阈值两条反例证伪（`spec.md:53-59`、`status.md:102` 有 receiver）。
6. “M2 在 2300 条里全中”作为独立召回证据被指出是选择判据证明自己（`spec.md:47-51` 有 receiver；candidate 仍残留，见 M5）。
7. 负向 wiring test 期待异常向外抛出，实际 driver 把异常装进 `outcome.error`；作者明确说断言方式错了（主 transcript `:651`，测试 `test_auto_mode_classifier.py:544-559` 有 receiver）。
8. 原 `test_the_reason_reaches_the_reply` 直接调用 formatter，不能证明 config → driver → reply 接线；硬编码 driver 后仍 42 passed（主 transcript `:2275-2308`，`status.md:82` 有 receiver）。
9. `pytest.raises(ValidationError)` 的 removed-key 测试对任何未知键都绿，键名零鉴别力（`status.md:84` 与测试 `:224-235` 有 receiver）。
10. `< block >no` 用例与客户端 regex 无关，守卫改坏也恒绿（`status.md:85` 与测试 `:311-317` 有 receiver）。
11. “schema 默认值与用户文档逐字一致”被实测证伪，多了 `configuration` 一词（`status.md:83` 与 candidate `:51` 已修）。
12. C-02 的立即修复路线因 `_answered_failed_search` 同形、需跨 observability 层而放弃，转入 deferred（`deferred.md:20-34` 有 receiver）。
13. `git -C .dev status --short --branch | head -3` 截断后只看见一份未提交报告，实际有两份（主 transcript `:2440-2454`；marker 表未列，也没有“named above”的 receiver）。
14. 为排除 report 原件而写的 `grep -v '\.dev/docs/tmp/260823'` 同时过滤了 spec 行里的完整旧路径，得到错误范围（主 transcript `:2483-2489`；marker 表未列）。
15. 主 transcript `:135`、`:1035` 两次使用 `rg -rn`；在 ripgrep 中 `-r` 是 `--replace` 并吞掉 `n`，不是 recursive + line-number。前一次同时有 `--files-with-matches`，后一次仍保留文件名，所以没有证据表明最终裁决因此错误；但它是未被作者识别、未进入 marker 的 silent parse error，证据强度只到“命令解析错”，不外推成结果错。
16. 真实流量探针扫描 8 个 history DB、145781 operations，重建 3 个 body、识别 2300 条并区分“0 命中”与“不可观测”（carrier：`reports/260823-auto-mode-traffic-samples.md`）。
17. 第一轮两份评审实际执行 parser 差分、误伤、跨 endpoint、subscriber/event 与 client retry 相关探针，推翻 8 个初始实现断言（carrier：两份第一轮报告与 `status.md` 处置表）。
18. 第二轮两份评审实际执行 A1-A7 输入探针、Node/Python parser 对照及 reason-wiring 受控变异，发现此前的 false green（carrier：两份第二轮报告与 `status.md`）。
19. 配置演进期间多次执行用户当前 YAML → schema → classifier/`handle()` 的 end-to-end probe，并在用户文件并发变化后重读确认；这些探针支持 `status.md:41`，marker 未列。

## C．归档与引用完整性

### C1．`git mv` 历史

**结论：pass。** `.dev` commit `9438a21` 对两份报告均记录 `R100`；`git log --follow` 能继续追到 `27000a8` 的原始 `docs/tmp/...` 新增记录。历史保留完整。

### C2．living docs 对两份取证报告的链接

**结论：pass。** 4 份 living docs 中旧 `docs/tmp`／`../tmp` 引用为 0；`spec.md:193-194` 与 `deferred.md:52,58,72` 均指向 topic 下 `reports/...`，在 `.dev@3e3b313` 上逐个 `git cat-file -e` 成功。

### C3．报告原件内部旧路径

**结论：取舍正确，minor 说明缺口。** 原件 3 处旧路径未改，符合点时记录原则；但应由 living doc 解释迁移，见 m3。

### C4．living docs 是否引用未提交文件

**`.dev` 证据文件方面：没有。** 四份评审报告、两份取证报告、spec/status/deferred 及当前 source/test 路径都在各自固定 commit 上通过 `git cat-file -e`。

**有一个明确例外：`docs/.human-controlled/config.example.yaml` 的路径在主仓 `e0c7ed4` 已存在，但 living docs 所引用的 auto-mode 三键内容只存在于用户当前未提交的 working-tree 版本。** 独立结果为 `authority_path_committed=True`、`committed_blob_has_feature=False`、`working_tree_has_feature=True`。这是用户控制文件的已知状态；本报告不建议提交它，也不把它当作本 session 可处置的仓库杂务，只如实说明 `.dev` 历史单独 checkout 时不能重建该权威内容。

另有两个 candidate 内部相对引用根本不存在于 `.dev` commit，见 m1；这是 broken reference，不是未提交文件。

## D．诚实性与当前状态

### D1．marker 的“不声称”边界

**结论：major。** “不穷举”这一边界诚实；“每个已发现候选都在上表命名 receiver”不诚实。`head -3`、`grep -v`、reason-wiring false green 等在 marker 写前已经被作者明确发现，却不在表中。边界应收窄为“表只列了一部分高价值候选；其余已知事件见 status/reports 或尚未沉淀”，或者把已知差集补齐。

### D2．当前已不成立的 living-doc 陈述

**结论：needs-fix。** 主要陈旧项是 `status.md:39` 的已证伪强理由、`deferred.md:4` 的“两键重新可配置”、candidate `:55-60` 的循环证据；低风险陈旧项是 `status.md:10,56` 与 `spec.md:2`。详见 M4、M5、m2。

当前配置键名与 source 一致：`decision`、`block_reason_str`、`match_system_prompt_prefix`；42 测试数量也由隔离 baseline 复核为真。D6 是当前未闭合项，不是已关闭事项误留在 ledger。

### D3．是否把“未验证”写成“已验证”

**结论：pass，置信度高。** `status.md:12` 明说“尚未在真实流量上验证过一次命中”；`deferred.md:36-46` 明说全部证据来自客户端源码与历史流量、没有一次 end-to-end 真实命中；`spec.md:197-199` 说明当前 `bypassPermissions` 下无可处置流量。`status.md:41` 的“已实测”有明确窄范围，只指当前 YAML 解析、配置值接线与合成 verdict，不声称真实 Claude Code traffic 命中。未找到把 D2 写成已闭合或暗示已实战验证的措辞。

## 建议处置顺序

1. 先修 marker 人口与 carrier：纳入 `commit-dev-8.txt`／`3e3b313`，补 `commit-dev-2.txt`／`31db448`，把总数改成当前 25；对不可达的 `auto_mode_classifier.py.bak` 给出真实处置而不是“已提交”。
2. 修 living docs 的已证伪 restatement：`status.md:39`、`deferred.md:4`、schema 相邻注释，并把 candidate 的证据强度改成 spec §3 的非循环链。
3. 修 candidate 的 `spec.md`／`deferred.md` 相对引用，再刷新 status 的最终 coverage 与 commit 状态；给报告原件旧路径补一条 living 迁移说明。
4. 最后重写 marker 的“不声称”边界，明确它是选摘而非“所有已发现候选”；无需为此新增门禁或证明基础设施。

# HANDOVER 接手性检查报告

## 评审范围

被检对象是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/HANDOVER.md`。检查目标不是判断其中每句话是否正确，而是判断一个没读过原会话的人能否只凭这份交接继续工作。检查遵循 `as-handoff-inspector`：先执行后通读，随后抽查不同性质的动作，再通读并完成九项检查。未修改 `HANDOVER.md`、`spec.md`、`plan.md`、`status.md` 或其他 authority 文件。

## 总体 verdict

**接不住。**

主要原因是交接笺没有可识别的动作表或 `ready` 动作，第一步无法按技能规定确定；而且它给出的 shared main 和 dotdev 快照已经与当前 refs 不一致。文档仍提供了足够线索让一个谨慎的接手者自行修复这些缺口，但这依赖额外的 Git 调查，不能算“只凭交接即可顺畅接手”。

严重度统计：**blocker 0，major 3，minor 3，nit 0**。

## 我实际尝试执行到哪里

### 1. 第一可执行动作：动作表检查

技能要求先打开动作表并挑第一个标记为 `ready` 的动作。我先对 HANDOVER 做了限定搜索：

```text
rg -n '(?i)(action|动作|ready|可执行|evidence|证据)' .dev/docs/token-counting/HANDOVER.md
```

结果没有发现动作表、`ready` 标记、`evidence` 字段或 `locator` 字段。标题扫描也只得到“可复制 kick-off”“必读清单”“下一步与验收／证伪”等普通章节，没有动作表。因此第一步已经卡住：我无法知道作者认为哪个动作是第一个可执行动作，也无法按文档给出的追踪项和证据定位执行。这是 **HND-01 major** 的直接执行证据。

因为技能明确要求第一动作卡住后继续调查，我没有停在这里，而是把“可复制 kick-off”中的第一件事作为替代动作执行，并把这次替代记录为额外补全文档缺口，而不是把它伪装成文档中的 `ready` 动作。

### 2. 替代执行的第一个动作：重新冻结 refs、worktrees 和 authority hashes

我执行了以下命令：

```text
git status --short --branch
git show-ref --verify ...
sha256sum .dev/docs/token-counting/spec.md .dev/docs/token-counting/plan.md .dev/docs/token-counting/status.md
git worktree list --porcelain
git log --oneline --decorate -n 8 --all -- .dev/docs/token-counting/HANDOVER.md .dev/docs/token-counting/status.md
```

得到的关键结果如下：

```text
## main...origin/main [ahead 3]
?? .claude/worktrees/
?? .dockerignore
?? Dockerfile
?? docker-compose.yml
?? exp/260820-h2-stream-cap/

main -> 42fb23299bc9487d1751749668277ac4304861f8
integration/token-learning-store -> 16a0904496f0af0a7832e4dd4bcb18fdc69919f9
archive/260907-token-prediction-persistence -> c59cdd66a008f8ae8248b781a0c74fc36e129287
archive/260907-token-learning-store -> 9ff21cef4d0f2377d1e60eba962e3b450584902c
dotdev-token-counting-learning -> b1dd960d6e5a5781f46610be8ff9ed212eaca5c0

spec.md 8405215aa6582728961e9066064cdb59081e519c43bf228267eb6ac21c1086ec
plan.md 030fa1bd1be40dfb12b8bd07ef20acfeb2c752bff809bc12ac12d9fc93ea6311
status.md 9ae648abc78321d79b94bf84830e6a872b4709b564980e94f4b7f14a99f74161
```

Handover 声称的 `spec.md` 和 `plan.md` SHA-256 与当前文件一致；但它声称 shared main 为 `18c7c690...`，实际为 `42fb2329...`，声称 `main...origin/main [ahead 2]`，实际为 `[ahead 3]`，声称 dotdev 为 `7119473d...`，实际为 `b1dd960d...`。`git log 18c7c690..main` 显示至少新增：

```text
42fb2329 (HEAD -> main) feat: use routed upstream for token counting
```

这不是文档内部的轻微表述差异，而是会改变接手者选择 integration base、判断 path overlap 和执行合并态验证的实际输入。

### 3. 依赖较多的动作抽查

我按 kick-off 的第一步继续核对了它要求先读的 authority、review、SDD 和旧 brief，并执行了相对链接解析。14 个 Markdown 相对链接全部解析到现存文件；以下关键文件也都存在：

```text
status.md
spec.md
plan.md
reports/260907-task3b-authority-review-gpt-high.md
reports/260907-task4a-brief-review-claude.md
reports/260907-task4a-prerequisite-design-gpt-high.md
reports/260907-task4a-prerequisite-design-review-grok.md
.superpowers/.../progress.md
.superpowers/.../task-4A-brief.md
```

但“同步 transcription map”没有给出文件路径或唯一锚点；在 token-counting 文档中只能通过全文搜索猜到它可能是 `spec.md` §13 或 Plan 的 mutation 清单。这是接手者必须自行补全的依赖边。

我还抽查了不同性质的 worktree 和旧 brief：

```text
task3-integration actual HEAD = 16a0904496f0...，tracked status clean
dotdev actual HEAD = b1dd960d6e5...，branch ahead 47，tracked status clean
reviewed-source worktree actual HEAD = c59cdd66a008...，只有未跟踪 .dev
task-4A-brief.md 顶部存在 SUPERSEDED／不得派发
progress.md 顶部声明已被 HANDOVER 取代
```

因此部分依赖可以走通，但 dotdev 锚点已经过时，且 reviewed-source worktree 的 `.dev` 未跟踪状态没有在 HANDOVER 中说明。

### 4. 通读后的动作和边界确认

完成上述执行与抽查后，我才通读 HANDOVER 全文，复核了当前 open review、任务链、未做事项、Git/worktree 边界、复发点和清理说明。没有执行 source、没有运行 broad tests、没有移动或清理 worktree、没有操作 4141，也没有修改被检对象。

## 发现

### HND-01 — major：没有动作表，无法执行技能要求的第一个 `ready` 动作

- `primary_location`：`HANDOVER.md` 全文，尤其“可复制 kick-off”和“下一步与验收／证伪”。
- `problem`：文档是编号清单和长段落，不是有 `ready`／依赖／追踪项／`evidence.locator` 的动作表。技能规定的第一步无法执行。
- `counterexample`：我只能自行把 kick-off 中“第一件事重新冻结 refs...”解释为替代动作；这已经是接手者替作者补全文档结构，而不是按交接执行。
- `impact`：不同接手者可能选择“修 authority”“读取 status”或“重新冻结 refs”作为第一步，执行顺序不再由交接保证。
- `minimum_fix`：增加明确的动作表，至少为每项动作给出 ID、状态（包括 `ready`／blocked／frozen）、依赖、追踪项、命令入口、证据 locator 和完成判据。
- `severity`：`major`。

### HND-02 — major：Git 快照已陈旧，且陈旧范围影响执行基线

- `primary_location`：`HANDOVER.md:7`、`:98`、`:126`。
- `related_locations`：当前 `git status --short --branch`、`git rev-parse main`、`git rev-parse dotdev-token-counting-learning`。
- `problem`：HANDOVER 写的是 main `18c7c690...`、ahead 2、dotdev `7119473d...`；实际 main 为 `42fb2329...`、ahead 3，dotdev 为 `b1dd960d...`。main 在旧快照之后新增 `feat: use routed upstream for token counting`。
- `impact`：接手者若直接使用文档里的 main 或 dotdev 锚点，会在错误的共享基线或错误的 authority projection 上继续。文档虽要求“先重新冻结”，但没有给出可复制的核验命令或更新后的投影。
- `minimum_fix`：更新 snapshot，明确 `origin/main`、main、integration、archive、dotdev 的完整 refs 和核验命令；同时说明当前 root 的 tracked/untracked 状态。保留“先重冻”作为动作前置，而不是让接手者从陈旧摘要推断。
- `severity`：`major`。

### HND-03 — major：状态投影与当前状态差异没有在交接内闭合

- `primary_location`：`HANDOVER.md:7`、`:69`、`:94-124`、`:138-143`。
- `related_locations`：当前 `status.md`、SDD `progress.md`、实际 worktree status。
- `problem`：HANDOVER 把“unknown-owner tracked／untracked WIP”作为 main 快照的一部分；当前 root `git status` 只显示 `.claude/worktrees/`、`.dockerignore`、`Dockerfile`、`docker-compose.yml`、`exp/260820-h2-stream-cap/` 等 untracked 项，没有 HANDOVER 所列的 tracked WIP。与此同时 dotdev 已从 `7119473d...` 前进到 `b1dd960d...`，但 HANDOVER 没有说明哪些 post-handover commit 已改变 projection。
- `impact`：接手者无法仅凭 HANDOVER 判断哪些“交接后改动未 review”仍属于 AUTH-03，哪些只是已被后续文档提交更新的投影；这会导致重复修复、错误复核或误把旧快照当当前状态。
- `minimum_fix`：列出 snapshot 与当前 refs 的差异，逐项说明差异是“已提交但未 review”“仅 projection 更新”还是“仍需重新验证”，并为 status、SDD、TaskList、transcription map 指定同一时点的 authority snapshot。
- `severity`：`major`。

### HND-04 — minor：否定式证据没有故意坏样本和原始失败输出

- `primary_location`：`HANDOVER.md:71-82`、`:146-152`。
- `problem`：文档提到 mutation、证伪和“必须红”，但没有附任何故意构造的坏样本、实际命令、退出码或失败原始输出。当前 authority review 也明确写着没有运行 broad tests、SQLite mutation 或 provider probe。
- `impact`：接手者知道未来验收应当能证伪什么，却无法验证这些否定靶子已经存在或当前命令确实会判失败。
- `minimum_fix`：每个关键 acceptance control 附一条可运行的坏样本命令和原始失败输出；若尚未运行，明确标记 `unverified`，不要用“证伪”文字替代证据。
- `severity`：`minor`。

### HND-05 — minor：数字主要是手写投影，缺少可重放的计数命令

- `primary_location`：`HANDOVER.md:7`、`:49-55`、`:148-152`。
- `problem`：`4 Major／1 Minor`、`111／211`、`3,358 tests／2 skipped`、`90.33%` 等数字都有叙述或报告来源，但 HANDOVER 没有给出重新计算它们的命令，也没有把数字与不可变 report revision 绑定。对文档 corpus 的机械重数只能得到引用次数，例如 `3,358` 出现 5 次，不能证明它对应的测试树仍未变。
- `impact`：接手者需要回读多个报告和 status 才能确认数字，且无法区分“报告当时的结果”和“当前 checkout 的结果”。
- `minimum_fix`：为每个重要数字给出可重放命令、输入 revision、输出摘要和 `unverified` 条件；不要把引用次数当成实际测试计数。
- `severity`：`minor`。

### HND-06 — minor：执行依赖中的 transcription map 没有唯一定位

- `primary_location`：`HANDOVER.md:26`、`:65`、`:78`、`:148`。
- `problem`：文档多次要求同步“transcription map”，但没有文件路径、章节、行号或稳定 revision。接手者只能根据关键词猜测它是 Spec §13、Plan mutation 清单或 Task 4B-P 相关投影。
- `impact`：修 authority 时可能只更新其中一处，造成 Spec、Plan、status、SDD 和测试转录之间的隐性漏边。
- `minimum_fix`：给 transcription map 指定单一权威文件和稳定锚点，并把需要同步的每个表／章节列入动作依赖。
- `severity`：`minor`。

## 九项必查结果

### 1. 空跑

HANDOVER 没有结构化 `evidence` 字段，因此不存在可机械枚举的 evidence locator 集合。对它明确提到的真实文档 corpus 做了有限重数：

```text
T3B-AUTH-01 -> 4
T3B-AUTH-02 -> 3
T3B-AUTH-03 -> 2
T3B-AUTH-04 -> 3
T3B-AUTH-05 -> 2
16a0904496f0af0a7832e4dd4bcb18fdc69919f9 -> 10
18c7c690aca125c9ef3a60831737aea99e42f4ac -> 2
7119473dc3d28a97dd8678e5a070651f418c4508 -> 2
3,358 -> 5
```

这些只是文档中出现的引用次数，不是 runtime／production 语料中的结构计数。由于没有 evidence schema 和真实生产样本，凡要求“真实语料出现几次”的部分都记为 **unverified**，不能据此判通过。

### 2. 否定式靶子

未发现故意坏样本及其原始失败输出。HANDOVER 只描述 mutation 应当判红，未提供执行结果；记为 **unverified**。

### 3. 状态词 vs 产物

可核实的正面部分：`spec.md` 与 `plan.md` hash 匹配；`task-4A-brief.md` 确有 `SUPERSEDED／不得派发`；SDD `progress.md` 确有“已被 HANDOVER 取代”；stacked integration HEAD 与 HANDOVER 中的 `16a09044...` 一致；Task 3A archive HEAD 与 `c59cdd66...` 一致。

反面部分：HANDOVER 自身及本报告路径均被 `.gitignore:27:.dev/` 忽略，`git ls-files` 不返回它们；dotdev 和 main 投影已发生未在 HANDOVER 中反映的变化。`草稿·未评审` 没有被误写成已通过，但文档中的部分“已完成”事实仍依赖历史 archive/ref，而不是当前 main。结论为 **部分可验证，部分 unverified**。

### 4. 计数

数字均是手写或从历史报告转述。没有提供会在多表、标题不唯一时报错的重数命令；`4 Major／1 Minor` 可在当前 review report 中读到，但不能由 HANDOVER 自身机械导出。记为 **部分验证，整体 unverified**。

### 5. 负空间

HANDOVER 有“明确未做”一节，也明确说未启动 source、未 restack、未跑合并态 gate、未操作 4141。这是正面信息。但它没有写“没有动作表／ready 标记”、没有写 snapshot 与当前 refs 的差异、没有写 transcription map 的缺失定位，也没有写机械检查不可用。上述执行中撞到的盲区未被负空间覆盖，因此该项不通过。

### 6. 依赖闭包

显式任务链 `#13 → #27 → #14 → #15 → #16` 以及 `3B → 4A → 4B-P → 4B → 4C` 可读，且旧 brief 已实际标记 superseded。仍有未闭合依赖：transcription map 无路径，当前 main/dotdev 快照已移动，status／SDD／TaskList 的统一 snapshot 未定义。动作没有 `ready` 状态和依赖字段，无法证明不存在“open/unknown 依赖却可执行”的漏边。

### 7. 冻结理由

部分冻结理由具体且可操作：authority review 为 `NEEDS FIXES`，未到 0 Major 不得启动 source；main dirty／已前进时不得直接 ff-only；旧 brief 已被 review 证伪并标记 superseded；清理因缺 manifest review 而 fail-closed 保留。缺陷在于当前 main 已再次移动，原冻结理由没有同步新的快照，因而冻结锚点本身失效。

### 8. 锚的可解析性

14 个相对 Markdown 链接全部存在；`spec.md` 和 `plan.md` SHA-256 全部匹配；integration/archive refs 与声明匹配；Task 3A reviewed-source worktree HEAD 与声明匹配。`main` 和 `dotdev` 锚点不匹配当前 refs。worktree 状态也有一个未记录差异：reviewed-source worktree 仅有未跟踪 `.dev`。没有 `sha:path:line` 或 `(report_id, finding_id, reviewed_at_rev)` 形式的 HANDOVER 自身稳定 action locator。

### 9. 投影的原像

抽查 `HANDOVER` 对 `status.md`、Git refs 和 SDD marker 的投影后，发现：

- `spec.md`／`plan.md` 的 hash 投影与原文件一致。
- integration、两个 archive 和旧 brief `SUPERSEDED` 投影与实际一致。
- shared main、origin ahead 数和 dotdev HEAD 投影与实际不一致。
- root tracked/untracked WIP 投影与当前 `git status` 不一致，且没有说明这些差异是否已由后续 commit 吸收。
- 文档只保证了“历史报告引用存在”，没有证明历史报告中的 source／test 数字仍对应当前 checkout。

因此汇总表不能被视为当前状态的可靠原像；该项不通过。

## 机械检查

没有找到项目提供的 HANDOVER 专用检查脚本或测试：`.github`、`tests` 和 token-counting 文档范围内均未找到针对 HANDOVER 的 checker。按技能要求记为“机械检查不可用”，没有把自写的相对链接解析脚本冒充项目闸门。自写解析结果仅为：14 个相对链接，0 个缺失。

## 结论

这份 HANDOVER 不是空白：它正确保留了当前 authority review 的 4 Major／1 Minor、旧 brief 的 superseded 状态、主要任务链和不少安全边界；一个有经验的接手者可以通过额外 Git 调查把工作继续下去。但它没有完成“让没读过原会话的人直接接手”的要求。第一动作只能由接手者自行推断，关键 refs 已陈旧，projection 差异和否定式证据没有闭合，因此最终 verdict 为 **接不住**。

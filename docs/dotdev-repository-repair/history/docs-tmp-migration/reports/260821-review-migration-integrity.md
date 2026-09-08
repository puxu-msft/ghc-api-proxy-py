# 独立证伪评审：`docs/tmp` + `docs/agents` 搬入 `.dev/docs` 的完整性与可逆性

- 评审对象：主仓库 `0b01cdc`（删除）、`0a72f52`（重指）；`.dev` `5e94b75`（接收）、`0d81c7b`（重指）。中间的 `f679ee7` 一并核过。
- 评审时刻：2026-08-21。主仓库 HEAD `0a72f52`，`.dev` HEAD `0d81c7b`。
- 角色：只读证伪。未修复任何问题，未改动两个仓库的任何被检文件；除本报告外无写入。
- 判定：**pass with findings** —— 0 blocker，4 major，7 minor。四条命题里前三条成立，第四条（活文档链接可解析）不成立。

> **读这份报告前必须知道的一件事。** `.dev` 与主仓库都有并行会话在动。本次评审全程以 **git 树状态**（`0d81c7b` / `0b01cdc^`）为准绳，磁盘现状只作为线索。这不是形式主义：我第一遍用磁盘 `find` 得到的「`implementation.md` 三处链接断了」是**假发现**，成因是并行会话此刻正把 9 份报告从 `documentation-restructure/reports/` 搬走（已 staged 未提交）。详见第五节。

---

## 一、命题 1：没有文件丢失 —— **成立**

### 1.1 被跟踪的 106 份：逐字节 1:1，零丢失

```bash
git -C /home/xp/src/ghc-api-proxy-py ls-tree -r 0b01cdc^ --format='%(objectname) %(path)' | grep -E '^[0-9a-f]+ docs/(tmp|agents)/' | sort > old-blobs.txt
git -C /home/xp/src/ghc-api-proxy-py/.dev ls-tree -r 5e94b75 --format='%(objectname) %(path)' | sort > dev-blobs-recv.txt
# 按 blob hash 内连接
```

结果：

- `0b01cdc` 恰好 106 条纯删除（`D`），**全部**落在 `docs/tmp/` 或 `docs/agents/` 之下（43 + 63）。
- 106 个旧 blob 在 `5e94b75` 里**全部**能按 hash 找到对应文件，join 后恰好 106 行、106 个不同旧路径，**无一落空**。
- 逐条比对 basename：**没有任何一份在搬迁中被改名**。

即：被跟踪那一半，内容与文件名都逐字节未变。

### 1.2 未跟踪的 355 份：用 archive 分支做独立底片

未跟踪文件没有 git 兜底，是最该核的一类。可用的独立底片有两处，都用上了。

**底片 A —— 全 ref 扫描。** 主仓库有大量 `archive/*` 分支，其中许多在被删除之前**曾经跟踪过**这些 `docs/tmp/` 文件：

```bash
for r in $(git -C /home/xp/src/ghc-api-proxy-py for-each-ref --format='%(refname)'); do
  git -C /home/xp/src/ghc-api-proxy-py ls-tree -r "$r" --format='%(objectname) %(path)' 2>/dev/null | grep -E '^[0-9a-f]+ docs/(tmp|agents)/'
done | sort -u
```

得到 592 组 `(blob, path)`、506 个不同路径。以此为底片核对 `5e94b75` 收下的 461 份：

| 类别 | 份数 | 判读 |
|---|---:|---|
| 与某个历史 commit 的 blob **逐字节相同** | 438 | 内容确未在搬迁中被改动 |
| 有历史但内容不同 | 8 | 见下，8 份全部由 **2026-08-20 的另一次搬迁**改写，与本次无关 |
| 任何 ref 里都没有过 | 12 | 全是 08-20／08-21 新写、从未提交的报告，加一份 `.md~`，形态合理 |

那 8 份的 mtime 全是 `2026-08-20 16:32:45`（一份是 14:14:35），而 `.dev` 的 `ec0a220`（「take in the candidate docs moved out of the main branch」）时间戳是 `2026-08-20 16:34:44`。差值两分钟。7 份的 diff 内容也一致：`docs/.human-controlled-candidates/` → `.dev/human-controlled-docs-candidates/`。**是上一次搬迁的重指遗留，不是本次的。** 第 8 份（`260820-empty-text-block-synthesis.md`）的 diff 是追加了第五轮评审记录，属正常文档演进。

**底片 B —— 批次清单与引用反查。** `batches/batch-*.txt` 合计 417 行、去重后仍 417，与 README 的声称一致；417 个文件名在 `5e94b75` 的 461 个新增里**全部**能按 basename 找到。461 = 417 + 1 份 `refs-go-bridges.md~` + 43 份 `docs/agents/`，与 `5e94b75` 的 482 减去 21 份迁移记录**恰好对上**。63 份被跟踪的 `docs/tmp/` 文件名也**全部**在批次清单里，说明清单不是漏采样。

再做一次反向证伪：把两个仓库里所有形如 `docs/tmp/<name>.md` 的引用全抓出来（282 个不同名字），减去 `.dev/docs` 下现存的全部 basename，只剩 5 个：

- `x.md`、`xxx.md` —— 迁移 README 自己举的占位例子。
- `260807-real-copilot-canary.md`、`260807-systemd-user-manager-diagnosis.md` —— 任何 ref 里都不存在、批次清单里也没有，**搬迁前就不存在**。
- `260820-debug-models-review-disposition.md` —— 在某 archive 分支里存在过，但 `0b01cdc^` 的树里已无，早于本次搬迁就已改名为 `.dev/docs/cli-commands/debug-models/review-disposition.md`。

**没有任何一个引用指向一份因本次搬迁而消失的文件。**

### 1.3 全 ref 里有、`.dev` 里没有的四个名字，全部与本次无关

`SPEC.md`（`docs/agents/tui-request-log/`）、`260820-debug-models-review-disposition.md` 都是更早的 `.dev` 搬迁（`d00fee6` 等）改名带走的；`mvp-final-acceptance.md`、`mvp-final-code-review.md` **只在 `refs/heads/archive/260810-systemd-rolling-apply` 上存在过、从未进过 main**，因此 `0b01cdc^` 的工作树里也没有它们，本次搬不到它们。这两份的内容今天仍可由该 archive 分支取回。

### 1.4 `.dev/docs/tmp/` 现有 21 份的来源已逐份对上

14 份来自 `5e94b75`（13 份未分类 + `.md~`），7 份 `260821-*` 是 `b858358`（18:07，早于搬迁）就已在 `.dev` 里的同伴产物。`refs-go-bridges.md~` 与正本 `anthropic-responses-bridge/reports/refs-go-bridges.md` 确实内容不同，README 的说法属实。

---

## 二、命题 2：没有卷走同伴的东西 —— **成立**

| 提交 | 形态 | 核验结论 |
|---|---|---|
| `0b01cdc` | 106 `D` | 全部落在 `docs/tmp/`、`docs/agents/`。无越界 |
| `0a72f52` | 10 `M`，`+13 / -12` | 全文 diff 已逐行读过：**每一行改动都只是文档路径重指**，没有一行代码语义、没有一处同伴的暂存改动被带走 |
| `5e94b75` | 482 `A`，**零 `M`、零 `D`** | 纯新增，结构上不可能卷走同伴对既有文件的改动 |
| `f679ee7` | 2 `A` | 与搬迁无关，也未触碰 `reports/` 或 `archive-*/` |
| `0d81c7b` | 24 `M` + 1 `A` | 见下 |

`0d81c7b` 里属于本次搬入的 16 份活文档，我用一个「把路径样式 token 换成 `<PATH>` 后再比对」的分类器逐行核过：

```
16 份文件，changed line pairs 合计 76，非路径改动 0，纯新增 0，纯删除 0
```

分类器先跑过正样本对照（`结论成立` vs `结论不成立` → DIFFERENT；同一句只换路径 → EQUAL），确认它有分辨力才采信这个 0。

`docs/.human-controlled/` 完好：10 个文件均在，`0b01cdc` 与 `0a72f52` 都没碰它，其中也没有任何 `docs/tmp` / `docs/agents` 引用需要重指。主仓库 `docs/` 现在只剩这一个目录，与 README 一致。

---

## 三、命题 3：归档报告原件未被改写 —— **成立**

三条互相独立的证据：

1. **git 层面。** `0d81c7b` 与 `f679ee7` 修改的路径里，**没有一条**落在 `*/reports/*` 或 `*/archive-*` 下。`0a72f52` 没有修改任何 `docs/` 下的文件。
2. **mtime 层面。** 461 份搬入文件中，mtime 落在 `2026-08-21 18` 的恰好 16 份，**全部是话题根的活文档**，`reports/` 与 `archive-*/` 下**一份都没有**。搬迁若用 `sed -i` 之类改写过报告，mtime 必然被顶到搬迁时刻。
3. **内容层面。** 第 1.2 节那 8 份「内容与历史 blob 不同」的报告，时间戳与 diff 内容都指向 2026-08-20 的上一次搬迁（`ec0a220`），不是本次。

顺带一条对 README 的独立确认：它说「`reports/` 与 `archive-*/` 下的约 2400 处旧路径保持原样」——这一条我核到的是「本次没有改动这些文件」，至于 2400 这个数字本身我没有复算，也不需要。

---

## 四、命题 4：活文档的链接真的能解析 —— **不成立**，3 处 major

方法：对 `0d81c7b` 触碰的 25 个文件，抽出 diff 中 **`+` 行新引入的**全部路径样式 token（含 inline code 与 markdown link），逐条按文件所在目录解析；另对 `.dev/docs` 下 126 份活文档（排除 `reports/` 与 `archive-*/`）做全量 markdown 链接可达性扫描。链接检查器先在合成正样本上验过分辨力（3 个植入坏链全部报出，2 个好链与 1 个 URL 不误报）。

### F1 [major] `research.md` 的 7 处绝对路径被改坏，指向一个不存在的目录

- 位置：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/research.md:49`
- 现状：7 处写作 `/home/xp/src/ghc-api-proxy-py/reports/upstream-route-decision.md` 一类。
- 搬迁前：`/home/xp/src/ghc-api-proxy-py/docs/tmp/upstream-route-decision.md`。
- 事实：`/home/xp/src/ghc-api-proxy-py/reports/` **这个目录根本不存在**（`ls -d` 确认）。7 份文件实际都在 `.dev/docs/anthropic-responses-bridge/reports/` 下（逐份 `find` 确认存在）。
- 成因：重指把「相对形式的替换值 `reports/<name>`」直接塞进了**绝对路径**，丢掉了 `.dev/docs/anthropic-responses-bridge/` 这一段。
- 排除误报：这 7 处出自 `0d81c7b` 的 diff `+` 行本身（`git -C .dev diff 0d81c7b^ 0d81c7b -- docs/anthropic-responses-bridge/research.md`），与并行会话无关；目标文件在 `0d81c7b` 的 git 树里就在 bridge 的 `reports/` 下。
- 复现：`rg -n -F '/home/xp/src/ghc-api-proxy-py/reports/' /home/xp/src/ghc-api-proxy-py/.dev`

### F2 [major] `history/proposal.md` 的 8 份评审报告被指向 `../tmp/`，而它们在 `history/reports/`

- 位置：`.dev/docs/history/proposal.md`，两行，分别以 `../tmp/260820-review-history-forensics-proposal.md` 与 `../tmp/260820-history-wiring-audit.md` 开头，各带 4 个与 2 个后续裸文件名。
- 事实：这 8 份在 `0d81c7b` 的 git 树里全部位于 `docs/history/reports/`（`git ls-tree -r 0d81c7b` 确认）。`../tmp/` 从 `docs/history/` 出发解析为 `.dev/docs/tmp/`，那里没有它们。正确写法是 `reports/`。
- 成因：重指算的是「`docs/tmp/` 这个**目录**搬到哪了」的相对路径，而不是「这**份文件**搬到哪了」。后面 6 个裸文件名同样因此变成相对 `docs/history/` 解析，一并不可达。
- 排除误报：目标位置取自 git 树而非磁盘；并行会话的 staged 改动里不含这 8 份。

### F3 [major] 被引用的 commit trailer 原文被改写，与同一句话自相矛盾

- 位置：`.dev/docs/graceful-shutdown/client-side/README.md:120`
- 现状：**当时几条提交的 `Docs:` 尾注指向 `../../tmp/260820-*.md`，那些文件现已搬到本目录 `reports/`**，对照关系见下——历史没有重写，尾注保持原样。
- 事实：那些提交的尾注**逐字写的是** `Docs: docs/tmp/260820-...`（`git log --all --format='%h %s%n%b' | rg 'Docs: docs/tmp/260820'` 有 8 条命中）。
- 为什么算 major：这句话是**对不可变 git 历史的引述**。改写之后，(a) 引述与被引述物不符；(b) 同一句里紧跟着「尾注保持原样」，读者据此去 `git log` 里搜 `../../tmp/` 会一无所获；(c) 它恰好违反本次搬迁自己立的那条原则——快照不得改写。这条原则在 `reports/` 目录层面被严格遵守了（第三节），却在活文档里**引述快照**的地方失守。
- 复现：`rg -n -F '尾注' /home/xp/src/ghc-api-proxy-py/.dev/docs/graceful-shutdown/client-side/README.md`

### 关于 README「3 处断链是搬迁之前就断的」这个声称

**独立验证结论：三条逐条属实，但这句话的范围没有标注。**

| 声称的断链 | 独立核验 |
|---|---|
| `systemd-runtime/plan.md` → `260807-systemd-user-manager-diagnosis.md` | 属实。该名字不在批次清单、不在任何 ref、`0b01cdc^` 树里也没有。搬迁前就断 |
| `systemd-rolling/plan.md` → `copilot-api-js-comparison.md` | 属实。搬迁前原文是 `docs/agents/systemd-rolling/copilot-api-js-comparison.md`，该文件既未被跟踪也不在批次清单，**搬迁前就不存在** |
| `systemd-rolling/plan.md` → `tests/systemd_vm/README.md` | 属实。主仓库没有 `tests/systemd_vm/` |

范围问题见 m6。

---

## 五、必须与本次搬迁分开记的一件事（**不是缺陷**，但会误导下一个人）

`.dev` 工作树此刻有一批 **staged 未提交**的重命名，把 9 份报告从 `documentation-restructure/reports/` 移到 `anthropic-responses-bridge/reports/`（7 份）与 `service-cutover/reports/`（2 份）：

```
R  docs/documentation-restructure/reports/260807-resume-review-implementation-post-s3.md -> docs/anthropic-responses-bridge/reports/...
R  docs/documentation-restructure/reports/260807-resume-review-readiness-current-r2.md   -> docs/service-cutover/reports/...
（另 7 条同形）
```

依据是同一目录下一份**尚未纳入版本控制**的同伴报告 `reports/260821-audit-classification-sample.md`（它在我开始评审后才出现在磁盘上）。

后果：`anthropic-responses-bridge/implementation.md` 的 3 处链接（第 23、221、223 行）指向 `../documentation-restructure/reports/...`。**在 `0d81c7b` 那一刻它们是对的**（git 树可证），在**今天的磁盘上**它们是断的。

我第一遍用磁盘 `find` 时把这 3 处当成了搬迁缺陷，改用 git 树复核后推翻。记在这里有两个用处：一是提醒下一个评审者别重复这个假发现，二是**这 3 处链接需要在同伴那批重命名落地时一并重指**，否则它会以「搬迁遗留」的面目留下来。

---

## 六、Minor

- **m1** `.dev/docs/graceful-shutdown/README.md:15` —— 「目前还散在**主仓库** `../systemd-*`、`deployment-systemd` 下」。路径被机械替换、句子没跟着改：这些目录已经不在主仓库了，而 `../systemd-*` 是个 glob，`deployment-systemd` 连前缀都没了。整句现在自相矛盾。
- **m2** `.dev/docs/tui/deferred.md` —— 前半句的路径被正确改成 `../count-tokens/reports/260820-review-count-tokens-shared-pipeline.md`，紧跟的括注「（后者属另一切片，**仍在主仓 `docs/tmp`**）」没改，成了假陈述。
- **m3** `.dev/docs/cli-commands/debug-models/review-disposition.md` —— 「本文件是 `../../tmp/` 下的临时评审处置记录」。本文件在 `.dev/docs/cli-commands/debug-models/`，不在 `.dev/docs/tmp/`。原文（`docs/tmp/`）在被改之前就已经是假的，这次只是换了个形式继续假。属于「自述位置」这类最容易被后人当真的陈述。
- **m4** `.dev/docs/systemd-runtime/plan.md:259` —— 未重指的 `../../tmp/260807-systemd-user-manager-diagnosis.md`。不重指本身是对的（目标未知，不该猜，README 也说了不猜）；但 `../../tmp/` 从 `.dev/docs/systemd-runtime/` 出发指向 `.dev/tmp/`，**这个目录根本不存在**。搬迁前它至少指向一个真实存在的目录，读者能看出「本该在 `docs/tmp` 里」。现在连这点线索都没了。同一行里另一处 `[S5执行记录]` 已被正确改成 `reports/...`，两者并排更容易让人误以为前者也已重指。
- **m5** `.dev/docs/systemd-rolling/plan.md:23,225` —— `../systemd-rolling/copilot-api-js-comparison.md`。文件自己就在 `docs/systemd-rolling/`，写成「上跳一级再回到本目录」是机械换算的产物，直接写文件名即可。不影响解析（目标本来就不存在），纯冗余。
- **m6** 迁移 README 的「**3 处断链**是搬迁之前就断的」没有标注范围。它成立的范围是「本次重指的 27 份活文档」。对 `.dev/docs` 下全部 126 份活文档做 markdown 链接全扫，得到 **11 处**断链：9 处在 `docs/archived-2604-rewrite/` 下、来自 `3d666ac`（2026-08-20 17:50）导入时就带着的坏链，本次未触碰；1 处是上表的 systemd-runtime；另 1 处是 systemd-rolling 那两条中以 inline code 形式写的（链接扫描不计）。其中 `archived-2604-rewrite/thinking-pipeline.md:19` 的 `../agents/anthropic-responses-bridge/spec.md` 值得单独提：它是一处**显式的 `agents/` 引用**，两条重指规则都没接住它（规则一只匹配字面 `docs/agents/`，规则二按旧位置解析得到 `.dev/docs/agents/`，那个目录从未存在过）。它在搬迁前也是断的，所以不是本次弄断的；但今天它的目标已经近在咫尺（`../anthropic-responses-bridge/spec.md`），是顺手可修的一处。
- **m7** `.dev/README.md` 的「已有话题」表在这次重写中删掉了 `docs/graceful-shutdown/`（原说明「关闭信号到进程退出之间的一切；目前只有 `client-side/`」）与 `docs/tui/`、以及两条 `exp/` 具体条目，换成了一条通用的 `exp/<name>/`。新表头声明「只解释不能从目录名读出来的那些」，`tui` 与 `exp/*` 删得合理；但 graceful-shutdown 那条的「目前只有 `client-side/`」恰恰是读不出来的信息，删掉是净损失。

---

## 七、开放风险（不属于四条命题，但没被任何文档记下来）

### R1 [major] 四棵同伴 worktree 仍然携带 `docs/tmp/` 与 `docs/agents/`，合并即复活

```bash
git -C /home/xp/src/ghc-api-proxy-py worktree list
for r in 9557700 7839b02 1e4a228 fd6b591; do
  echo "$r: $(git -C /home/xp/src/ghc-api-proxy-py ls-tree -r $r --name-only | grep -cE '^docs/(tmp|agents)/')"
done
```

| worktree | HEAD | 携带份数 |
|---|---|---:|
| `/home/xp/.claude/jobs/405f4b84/tmp/slice0/wt` `[slice0/exactly-once]` | `9557700` | 105 |
| `/home/xp/.claude/jobs/826d4cda/tmp/review` （detached） | `7839b02` | 21 |
| `.claude/worktrees/delivery-keepalive` `[worktree-proxy-priority]` | `1e4a228` | 105 |
| `.claude/worktrees/upstream-error-events` `[fix/upstream-error-events]` | `fd6b591` | 106 |

这四条分支都是 `0b01cdc` 的祖先侧。按项目约定它们最终以 squash 进 `main`——**squash 的 tree 来自分支侧，会把 `docs/tmp/`、`docs/agents/` 一起带回主仓库**，而且是静默的：没有冲突、没有报错，只是那两个目录又出现了。

`.claude/rules/00-development-workflow.md` 与 `.github/copilot-instructions.md` 里新写的「**Do not create `docs/tmp/` or `docs/agents/` again**」拦不住这件事——它约束的是「新建」，不是「合并带回」。迁移记录里也没有提到这四棵树。

我只报告，不处理。可行方向（供主会话裁决，我没有实施授权）：在这四条分支各自集成前先删掉这两个目录再 squash；或在集成后立刻复核 `docs/` 是否只剩 `.human-controlled/`。

### R2 CLAUDE.md 第 9 行确已过时，且该文件未被跟踪

`/home/xp/src/ghc-api-proxy-py/CLAUDE.md:9` 仍写「曾经用户选用过 `docs/agents/`，你可以逐步按主体迁移」。README 已披露此事并正确地没有改动它（用户控制）。补充一条 README 没说的事实：**该文件未纳入 git 跟踪**（`git ls-files CLAUDE.md` 无输出），所以它既不会被任何提交带走，也没有历史兜底。交给用户处理。

---

## 八、我做过、结果为「无异常」的核验（便于后续复用，不必重跑）

- `0b01cdc` 的 106 条删除 100% 落在应删范围；无一条越界。
- `0a72f52` 十份文件的**全文 diff** 逐行读过，`+13/-12` 全为路径重指；`0a72f52` 引入的 8 个 `.dev/...` 目标**逐个 `ls` 确认存在**。
- 主仓库被跟踪文件里残留的 `docs/tmp|docs/agents` 引用只剩 2 处，均为「不要再重建它们」这类刻意保留的散文。
- `docs/.human-controlled/` 十份文件均在，且内部无需重指的引用。
- 12 份「任何 ref 都没有过」的搬入文件逐个看过落点，形态合理，无可疑。
- `refs-go-bridges.md~` 与正本内容确实不同（README 的说法属实）。
- 两个检查器（链接可达性、路径-only diff 分类器）都先跑过正样本对照，确认有分辨力后才采信其「0」与「MISS」。

## 九、我没有核的（说明边界）

- 未复算 README 声称的「约 2400 处旧路径」「180 处引用」「27 个活文档」这三个数字。命题 3 我是从「本次未修改这些文件」这一侧证明的，不依赖这些计数。
- 未评估分类本身的对错（哪份报告该归哪个话题）。同伴已有一份 `260821-audit-classification-sample.md` 在做这件事，见第五节。
- 未对 `reports/` 与 `archive-*/` 下约 2400 处快照路径做可达性扫描——按本次原则它们本来就该断，扫了也没有判据。

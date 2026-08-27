# 评审：门槛 2 与「归属（2026-08-22 已决）」的改写

- **日期**：2026-08-22
- **被检对象**：`/home/xp/src/ghc-api-proxy-py/.claude/skills/project-review-principles/SKILL.md` 工作树未提交改动（`git diff` 的三个 hunk：L267、L310-320、L329-331），基线 HEAD `0a72f52`
- **判据来源**：用户 2026-08-22 原话（由派发方逐字给出，视为一手）；`~/.claude/skills/organizing-project-docs/SKILL.md`（当前工作树版本，mtime 2026-08-22 07:43）；本文件自身的「进来的门槛 / 退出的判据」两节；`~/.claude/my/skills/skills/as-reviewer/SKILL.md`
- **总体 verdict**：needs-fix
- **blocker 数**：2

发现 8 条：blocker 2、major 3、minor 3。其中 F8 在本次改动之外，单列。

---

## blocker

### F1 · L267 / L316 断言了一个与 user 级的干净对应关系，而这个对应关系当场就不成立

L267：

> 通用形态已落在 user 级 `organizing-project-docs` 的「Axis 2 — claim role」一节（需求层／中间层／产物层，含两个方向的误置）。**本条不复述它，只做本仓这一端的落地与检索**

L316：

> **复查时若发现两边说的不一样，以 user 级那份为准并回来改这里**；仅仅「听着像同一件事」不是修改理由。

两边现在就说得不一样，而且是这条最核心的那件事：**承载面的归类**。

- `organizing-project-docs:69` 把 **code comments** 明确列进**中间层**的 carriers，并在 `:72` 解释「The middle is read as reasoning already, so it can carry everything: derivations, measurements, what we tried and dropped」。
- 本条的违背实例集里有两处 code comment：L302 的「driver docstring 断言 `which is retryable` 与 `nothing has been shown to the client yet`」，以及 L304 的独立实例 `blocks.py:20`。已核实 `blocks.py` 那处确为类 docstring（当前在 `src/app/pipeline/delivery/blocks.py:20`，`class DeliveryError` 的 docstring）。

按 Axis 2 的 placement rule（`:74`「a fact belongs to the layer that decides it」），docstring 是推理该待的地方，这两处**不是**误置。按本条，它们是违背，且 `blocks.py:20` 还被当成「本条命令漏检」的证据（L281）。同一批句子，两份给相反判定。

第二处不对齐：本条 L263 定义的承载面是「运维填的那个值、运维或客户端读到的那一行」——运行时 warning 字符串与客户端错误体。已核实这两类真实存在（`src/app/server/composition.py:105-108` 的 keep-alive 警告、`:239-241` 的 SOCKS 警告、`semantic.py` 的 `TranslationRefused` docstring 说明 `code`/`field_path` 送客户端）。而 Axis 2 的 carrier 表（`:68-70`）列的是 requirements / config contract / public API / human-written authority / `DESIGN` / `adr/` / `TRACKING` / status ——**没有任何一格是运行时字符串**。也就是说本条覆盖的面在 Axis 2 里根本没被枚举，谈不上「只做本仓这一端的落地」。

这一条判 blocker，因为本次改动的立论就是「重复可以，矛盾必须解决或澄清」。矛盾在，且没被解决或澄清，立论落空。

**改法**（二选一，都要具体写出来，不要留给「复查时再说」）：

1. 在 L267 后补一句划界：「Axis 2 的 carrier 表不枚举运行时字符串与错误体，本条覆盖的正是这一类面；code comment 在 Axis 2 属中间层，本条把 docstring 计入违背是因为 ⟨写出理由⟩ ——两边在这一点上判定不同，以本条为准 / 以 user 级为准 ⟨择一⟩。」
2. 或者按 Axis 2 重判实例集：把 L302 的 docstring 面与 L304 的 `blocks.py:20` 从违背实例移出（它们仍可留作「命令精度」的实证），并相应修正 L306「真违背 3 处」的口径。

若两条都不做，至少不能保留 L316 那句「复查时若发现两边说的不一样」——它把一个已发生的事推给未来。

### F2 · L329-331 门槛 2 的两段互相抵消，且新判据把「重复」的解禁扩成「矛盾是唯一否决理由」

L329-331：

> 2. **复查问题依附本项目结构**，或是通用方法在本项目的具体落法。找到对应的 user 级 skill 时**引用**它，别整段抄——抄写会让两边各自演化。
>
>    **用户 2026-08-22 裁决**：项目级与用户级**允许交叉重复**，同一件事有两个家是可以的；**只有矛盾必须解决或澄清**。所以「这条听着通用」本身不构成退出理由；要判它出局，得指出它与 user 级那份**说的不一样**。

两个缺陷叠在一起：

- **内部抵消**。第一段禁「整段抄」，第二段说要判出局必须指出与 user 级**说的不一样**。一份忠实的整段抄按定义与原件一致、不矛盾，因而必然通过第二段的检验。第一段的禁令被架空，读者拿不准该用哪一段。
- **越过原话**。用户原话是「一般地，……允许交叉重复，只有矛盾是必须解决或澄清的」。这句解除的是**「重复」这一条否决理由**，并且带着「一般地」这个限定词。第二段把它改写成「矛盾是唯一出局理由」，等于连带作废了本门槛自己前半句的落地要求（「依附本项目结构，或是通用方法在本项目的具体落法」）和门槛 3 的可跑命令要求——那两条都不需要指出任何矛盾就能否决一个条目。这正是派发时问的「有没有把裁决用过头」：用过头了，过头处就在「要判它出局，得指出它与 user 级那份说的不一样」这半句。

结果是这份清单的入选标准确实松到失效：只要与 user 级不矛盾，任何通用条目都过。

**改法**：把第二段限缩成解禁而非立新闸，并把可执行判据挂回本门槛已有的正面要求。建议改成：

> **用户 2026-08-22 裁决**：项目级与用户级**允许交叉重复**，同一件事有两个家是可以的；**只有矛盾必须解决或澄清**。所以「这条听着通用」本身不再构成否决理由。**其余否决理由不受影响**：本条仍必须指得出本仓的具名落点（哪个文件、哪个面），仍必须满足门槛 3 的实测命令；只写得出通用判据、写不出本仓落点或写不出命令的，照样不收。发现它与 user 级那份**说的不一样**时，那是必须当场解决或澄清的事，不是收录与否的问题。

---

## major

### F3 · L314 / L331 的「用户 2026-08-22 裁决」只有转述，没有一手锚

L314：「**该 blocker 已由用户裁决解除**：项目级与用户级允许交叉重复……」；L331 同形。两处都是转述，没有逐字原话，也没有能回指到那次发言的锚（会话日期／转录路径／记下原话的文档）。对照 `organizing-project-docs:61-62`，同一位用户的两次裁决在那边是带「」的逐字引文并各自标了日期——同一件事在两份文件里的举证强度不一致。

这不是形式问题：F2 的越权恰恰来自转述时丢掉的「一般地」。下一个会话读到 L331 无从发现这个限定词存在过，也就无从发现范围被撑宽了。

**改法**：在 L331 的裁决段里逐字引原话（连同「一般地」），格式照 `organizing-project-docs:61-62`，并注明出处锚。L314 可以只留一句并回指 L331，不必两处各转述一遍。

### F4 · L320 的退役条件挂在本条自陈**不覆盖**的那一端上

L320：

> 若 `docs/.human-controlled/` 不再作为独立契约面（本条的两端之一因此消失），连同实证移进 `.dev/docs/<topic>/archive-*/`。

与 L267 直接打架：

> 因此**本条的检索只覆盖实现面这一端**

本条全部可执行部分——「怎么查」的两条命令搜索根都是 `src/`，「什么算违背」四条里有三条针对端点字符串，L306 的三处真违背全在 `src/`——都落在**实现面**。`docs/.human-controlled/` 只出现在第 4 条违背（L288），而那条自陈「查不了」。所以按 L320，那一端消失时要归档一个可执行部分完好无损、仍能查出违背的条目。这正是本文件 L18 警告的反面（「实现基础没了却还留着，比没有这条更糟」的对偶：基础还在却被判退役）。

括注「（本条的两端之一因此消失）」是本次新加的，旧版没有这句理由——理由一写出来就露了馅。

**改法**：退役条件改挂实现面：「本仓不再由自己产出面向运维/客户端的字符串（该职责整体迁出、或端点文案改由外部生成）时」。`docs/.human-controlled/` 那一端降格为局部条件：「若该目录不再作为独立契约面，删掉 L288 那条违背即可，不触发整条退役。」

### F5 · L331 用「出局」措辞，凭空开了一条「退出的判据」一节没有的退出路径

L331 末句「要判它**出局**，得指出它与 user 级那份说的不一样」，而 L334-341「退出的判据」明写：

> 只由**可证伪的结构事实**触发：
> - 条目自带的退役条件成立……
> - 该原则已被另一条**现存条目**完整覆盖，且做过召回面对账。

这份封闭列表里没有「与 user 级 skill 矛盾」。现在两节各说一套：一节说出局看与 user 级矛不矛盾，另一节说出局只看那两条结构事实。而且「矛盾」怎么可证伪地判定，两节都没写——F1 恰好证明这不是理论顾虑，肉眼对读就能读出分歧，但「算不算矛盾」当场就有争议。

另有一层措辞错位：门槛 2 属**进来的门槛**，管的是收不收录；「出局」是退出侧的词。

**改法**：把 L331 的「出局」改成「不予收录」，退出侧一律交给「退出的判据」一节；若确实想让「与 user 级矛盾」成为退出路径，就在 L338 的列表里补第三条，并写明判定方式（例如：两份对同一具名位置给出相反判定，且举得出该位置）。

---

## minor

### F6 · L267「含两个方向的误置」漏掉了本条对应的那个方向，也漏了对面已经点名回指本条

`organizing-project-docs:76-80` 列的是**三**条（「Both misplacements」之后紧跟第三个 bullet）：产物层→需求层、需求层→产物层、**中间层→任一端**。第三条才是本条对应的形态，而且 `:80` 逐字写着：

> That is the shape `explanation-does-not-belong-on-a-surface-that-is-read-as-a-promise` catches.

即 user 级那份已经按名字回指了本条。现在的括注既数错了方向数，又把这条唯一相关的方向和已有的双向链接一起漏掉了。

**改法**：改成「（需求层／中间层／产物层，列了三个方向的误置；其中『中间层→任一端』就是本条抓的形状，那份在 `Axis 2` 末尾按名字回指本条）」。

### F7 · L267「本条不复述它」紧挨着一句复述，且没交代「两端／中间带」这套本地措辞的处境

同句前半就是上位形态的复述：「信息有层次，中间层丰富，**两端则可能是精炼的、克制的**」。按新裁决，复述本身不再是缺陷，所以问题只在句子自相矛盾——读者会以为下文还有一块被有意省略的内容。

另一层信息缺失更值得补：`organizing-project-docs:64` 明写「the earlier wording (『端点/中间层』) was explicitly ruled project-local, and these three names replace it here」，并说「If you meet the old pair in a project-level document, that is the same idea under its local name, not a second scheme」。所以本条继续用「两端／中间带」是**对**的、是被点名允许的。但 L267 没说这一点，对读两份的人会误判本条没跟上裁决。

**改法**：把「本条不复述它」改成「本条只在需要时引它，不搬它的分层表」，并补半句：「『两端／中间带』是这套判据在本仓的本地叫法——user 级已裁定该措辞为 project-local，由需求层／中间层／产物层替代，并注明在项目级文档里遇到旧叫法是同一件事的本地名。」

### F8 · （本次改动之外，同文件）L347「六条」与 L351 指向的条目都已失效

L347「六条，都立于 2026-08-20」，L353「其余五条」——两句互相矛盾；正文实际只有 5 条（`## \`` 标题在 L28/91/148/206/261）。L351 整段讲的 `a-failure-path-must-not-produce-the-ordinary-value` 已在 `a469dba`（2026-08-20）被删除，该提交同时把 `a-setting-says-what-it-bounds-not-what-follows` 换成了现在这条，但没同步「当前状态」一节。

不在本次三处改动内，也不影响上面任何一条的判定，单独修即可。**改法**：「六条」改「五条」，删掉 L351 整段（或改写为「上一条 `a-failure-path-…` 已于 `a469dba` 退役，实证在 ⟨归档路径⟩」）。

---

## 搜索面

**读过**：`.claude/skills/project-review-principles/SKILL.md` 全文 360 行（工作树版）与其 HEAD 版；`~/.claude/skills/organizing-project-docs/SKILL.md` L40-129（含 Axis 1/2、role map、authority ladder、rewrite tiers）；`~/.claude/my/skills/skills/as-reviewer/SKILL.md` 全文。

**跑过**：`git diff`、`git log/show`（`a469dba` 的标题增删）、`git log -S`；`rg` 定位 `Axis`、`logger.`、`_warn_about_socks`；`sed` 读 `src/app/server/composition.py:94-112,213-255`、`src/app/pipeline/delivery/blocks.py:14-26`、`src/app/pipeline/translation_driver/semantic.py:45-60`。**未修改任何文件，未 `git add`/`commit`**。

**没看的面**：

- 用户 2026-08-22 那句原话的一手出处（转录未定位，按派发方逐字给出采信）——F3 因此只判「文档里缺锚」，**不判**「归属不成立」。
- `docs/.human-controlled/` 目录内容（未被 git 追踪，未读）——F4 只依据本文件自陈的覆盖面推理。
- 本条「怎么查」两条命令的召回力**未实测**（本次不是复查，是文档评审）。L265/L306 里 `composition.py:98` / `:217` 这两个行号顺带发现已腐坏（现为 `:105` / `:239`），但这两行不在本次改动内，且文件 L357-359 已把它们标为带时点的快照，故不单独立条。
- Axis 2 之外的 `organizing-project-docs` 章节（role slots、rewrite tiers）与本条的关系未逐条对读。

**工具状态**：`Skill(my-skills:as-reviewer)` 报 `Unknown skill`；该 skill 实际位于 `/home/xp/.claude/my/skills/skills/as-reviewer/SKILL.md`（不在 `~/.claude/skills/` 下，故未被登记到 Skill 工具），已直接读取全文并据其主流程、三条必查面（权威归属 → F3；一个绿的分辨力 → 无绿可判；安全 → 不适用）与定级口径工作。

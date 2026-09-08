# 评审：acceptance.md 切除（446→353）与新 skill `writing-acceptance-criteria-that-can-fail`

- **日期**：2026-08-24
- **评审者**：未卷入本次改动的独立异源评审者（`my-skills:as-reviewer` + `evolving-skills` 判据）
- **改动级别**：B 级（改变模型收到的指令与加载行为）
- **总体 verdict**：needs-fix
- **blocker 数**：1；**major 数**：7（本轮上限 8 条，minor 留待下一轮）

## 评审范围

- 被检对象 A：`/home/xp/src/ghc-api-proxy-py/.dev/docs/anthropic-responses-bridge/acceptance.md`（切除后 353 行，`.dev` HEAD = `52dbdee`）；切除前原文取自 `git show HEAD~1:docs/anthropic-responses-bridge/acceptance.md`（446 行）。**注意：任务书说原文在 `HEAD:` 是错的，`HEAD` 就是切除提交本身。**
- 被检对象 B：`/home/xp/.claude/skills/writing-acceptance-criteria-that-can-fail/SKILL.md`（75 行，未提交）。
- 附带读入：`reports/260807-acceptance-review-disposition.md`（移出目的地）、`docs/service-cutover/plan.md`、`spec.md`／`architecture.md` 各版本内容哈希、邻居 skill `trusting-a-green-result`／`making-a-gate-actually-fire`／`declaring-something-done`／`verifying-authoritative-claims`／`running-a-procedure-as-written`。
- 跑过的命令：`git show` 逐版取内容、`sha256sum`、`rg --count-matches` 词频对账、Python 逐节字符数统计。
- **未看的面**：`spec.md` 正文与各 gate 的行为正确性（不在本次改动范围）；`tests/` 下是否真有对应资产（CAL-04 已自陈无实现）；minor 级问题（按任务约定不报）。

---

## 发现

### F-01 `blocker` — 唯一幸存的 SHA-256 钉版早已失配，却挂在「Current authority」下

**位置**：`acceptance.md:3`

切除把 SHA-256 从 25 处（12 行、20 个不同哈希）压到 1 行，但留下的恰好是**当前失配的那一行**：它写「2026-08-08 最终输入为 Spec `4c9beed133b8…` 与 Architecture `746adc7a…`」。实测：

| 文件 | 文中所钉 | 实际当前 | 最后一次成立 |
|---|---|---|---|
| `spec.md` | `4c9beed133b8…` | `1bdb2b7f5af4…` | `5e94b75`（2026-08-21），此后经 `0d81c7b`／`1197da7`／`66811b1` 三次改写 |
| `architecture.md` | `746adc7a…` | `360ac0ad…` | 在 `.dev` 历史中从未成立 |

**为什么是问题**：这不是「一句陈旧的注记」。本文件自称 `LIVING_ACCEPTANCE_ORACLE`、用户当日裁定「绝不能绕开 Spec」，而这一行是全文**唯一**把判据绑到某个 Spec 版本上的锚。后来者按它去取 Spec，取到的是一份树里已不存在的内容；而失配与「有人改了行为」在信号上不可区分——这正是被检对象 B 自己 `SKILL.md:68` 点名的失效。同一串提交里 `c436b61` 的标题是「哈希钉版换成提交锚定」，即作者认为已经改完了；实物显示没有。

**建议改法**：把这两个哈希换成提交锚（`.dev@66811b1` 之类）或直接删除并只留「以 `spec.md` 当前内容为准」；若要保留 2026-08-08 的历史事实，把整句移进移出的点时记录里，不要留在 `Current authority` 段。

### F-02 `major` — CAL-04 的活指令指向已被移出本文件的评审行，且新报告是孤儿

**位置**：`acceptance.md:313`（活指令）；`reports/260807-acceptance-review-disposition.md`（移出目的地）

`acceptance.md:313` 是一条**当前必须执行**的待办：「其 `ping` 转移行、下面那句、以及**已闭评审行 R3-M1／R4-M1／R5-M1**……需要作为一次独立切片一起重做并升版」。R3-M1／R4-M1／R5-M1 三行本轮被移进了 `reports/260807-acceptance-review-disposition.md`。

**为什么是问题**（两重，且互相锁死）：① 全仓 `rg -F '260807-acceptance-review-disposition'` **零命中**——包括 `acceptance.md` 自己。执行这条指令的人在本文件里找不到 R3-M1，也没有任何指针告诉他去哪儿找。② 就算他找到了，那份报告的抬头写着「**点时记录，内容一字未改**」，即禁止修改；而指令要求把那三行「一起重做并升版」。于是这条指令按当前布局**在构造上不可执行**。这正是 `evolving-skills` 的 `retiring-must-leave-a-forwarding-address`：搬走内容而不留转发地址，不会报错，只是此后没人找得到。

**建议改法**：把 `acceptance.md:313` 里的「R3-M1／R4-M1／R5-M1」改写成对该报告的显式链接 + 说明「历史行不改，升版时在本文件新写一条 `CAL-04-GRAMMAR-v2` 的裁决记录」；并在文件头部或 CAL-04 节加一句指向该报告的路由。

### F-03 `major` — 状态词汇 `UNVERIFIED`／`BLOCKED`／`PASS` 成了悬空词汇，两边都找不到定义

**位置**：`acceptance.md:328`、`acceptance.md:290`、`acceptance.md:3`（用），定义原在被删的 `状态与判定` 与 `最终放行清单`

作者为 8 个证据标签补了分级表，理由写得完全正确——「只删定义会留下悬空词汇，这是通读查不出来的那类缺陷」。**同一个缺陷在状态词汇上原样存在，没有被补**。切除后 `UNVERIFIED` 仍用 6 次、`BLOCKED` 1 次、`PASS` 1 次，而三者的定义全在被删的两节里。

最刺眼的是 `acceptance.md:328`：「未校准的新行为及过期 corpus 覆盖范围一律标记 `UNVERIFIED`，**不得误判 `BLOCKED`**」——一条区分两个词的指令，而这两个词现在都没有定义。原文里被删掉的那条规则是承重的：*正确样本红／注入不变红／已证实的丢失重排 → `BLOCKED`；证据未取得／corpus 过期／政策未裁决 → `UNVERIFIED`，不得误报成实现缺陷*。它防的是一类具体的错误——把「我们没跑」写成「实现有缺陷」。skill 只承接了单向的「未执行就标未执行，不折算为通过」（`SKILL.md:54`），**反向那半（未取得证据 ≠ 实现缺陷）两边都没有**。

**建议改法**：在「证据分级」节后加 3 行，只写三个词各自的判据，不要恢复「最终放行清单」的报告格式。

### F-04 `major` — Spec 章节 → gate 的映射两边都找不到，「随 Spec 修订同步更新」因此不可执行

**位置**：原 `POLICY-MANIFEST-v1`（切除前 `acceptance.md:29-43`）；现无对应物

`POLICY-MANIFEST-v1` 里确实大半是证明装置（对账结论、`FINALIZED` 恢复声明、hash 门），删得对。但那张表还承载一件**不是装置**的东西：七个 policy 域各自的 **current Spec 规范来源章节名 → 本文件哪几条 gate**。切除把整表删了，映射随之消失。

**为什么是问题**：文件头 `acceptance.md:3` 保留了义务「随 Spec 条款修订同步更新」，本文件的**唯一存续条件**就是它。但现在没有任何东西能回答「Spec 改了『Usage 契约』这一节，我该重做哪几条 gate」。各 gate 正文只有「按绑定 Spec 的 route 真值表」「按冻结矩阵」这类不指名章节的散引。于是这条义务在纸面上成立、在执行时无从下手——正是被检对象 B 的邻居 `making-a-gate-actually-fire` 管的那类失效。用户当日的两条裁决是「废除冻结」**且**「绝不能绕开 Spec」，删掉可追溯性只落实了前一条。

**建议改法**：不要恢复表格与对账结论。给每条 gate 的现有 bullet 列表加一个字段 `- **Spec 依据**：〈章节名〉`（约 35 行，无装置），或在「证据分级」后放一张两列表（Spec 章节 → gate id）。

### F-05 `major` — 新 skill 的「异源 oracle」一节与 `trusting-a-green-result` 实质重复，且它自己声明了相反的权威归属

**位置**：`SKILL.md:25-38`（`the-oracle-must-not-share-a-source-with-the-thing-under-test`）与 `SKILL.md:72`（边界节）

`trusting-a-green-result` 的 description 明写它管「同源 oracle」，正文 pattern #1「Same-source roundtrip」的修法是「build the ground truth from the source object's *full* field set, serialized independently of the code under test, and compare everything」——这与新 skill 第 1 条（不要用产品 serializer 同时生成 expected 与 actual）和第 4 条（完整对象相等）是同一条判据的两种写法。而新 skill `SKILL.md:72` 又写着 `trusting-a-green-result` 是 canonical，管「变异、正样本对照、恢复协议、**以及一个绿证明不了什么**」——同源 oracle 恰恰属于最后那一项。**同一份文件既把权威让给了邻居，又在正文里把它重写了一遍**，且两处措辞不同、无交叉引用。按 `one-authority-allows-contextual-restatement`，重述必须回指权威；这里没有。后果不是冗余，是两边会各自演化，而没人知道以哪份为准。

同一形态还有第二处：`SKILL.md:56-68` 是用户规则 `build-proof-infrastructure-only-if-requested` 和项目 `CLAUDE.md` 同名条款的展开，但 skill 全文没提这条规则，规则那边也没有触发词指向这份 skill。`evolving-skills` 要求边界写在**三处**（rule、skill、索引），现在一处都没写。

**建议改法**：`SKILL.md:25-38` 缩成「写判据时的增量」——即第 3 条（唯一标记 oracle）与第 4 条（缺席断言、顺序断言），第 1、2 条改成一句指针「同源 oracle 的形态与修法见 `trusting-a-green-result` pattern #1」；边界节把「同源 oracle」从 canonical 清单里点名。另在 `SKILL.md:56` 节首加一句「本节是 always-on 规则 `build-proof-infrastructure-only-if-requested` 的展开，冲突时以规则为准」。

### F-06 `major` — 「每条判据都必须跑两种控制」没有范围限定，直接与本 skill 自己的第四节矛盾

**位置**：`SKILL.md:14`

原文：「**每条判据都必须在同一个测试入口上跑两种控制，缺一条这条判据就不成立**」。全称、无例外、无 ROI 门。

**为什么是问题**（不是「我不喜欢这个写法」，是可指出的失效）：① 它承接的那份 `trusting-a-green-result:16` **明确写了范围**——「Worth it for: correctness-critical invariants, anything irreversible downstream… **Skip it for straightforward behavior already covered by watching a normal TDD red→green**」。搬迁时这个限定成分被丢掉了，方向是单向放大（`restating-a-text-drops-its-qualifiers` 的典型形态）。② 照字面执行，任何项目里每写一条断言都要配一次缺陷注入 + 恢复 + 复跑，那就是给判据外面套了一整圈证明机器——**正是 `SKILL.md:56` 那一节禁止的东西**。③ 它还与本项目 `CLAUDE.md` 的「不为覆盖率而测」「不预建完整状态空间」直接冲突，而本项目正是这份 skill 的来源项目。

**建议改法**：在 `SKILL.md:14` 后补一句范围限定即可（不需要新段落）：「范围与 `trusting-a-green-result` 一致——正确性关键的不变量、下游不可逆的判据、以及第一次跑就绿的非平凡性质；普通 TDD 红→绿看过一遍的行为不需要。」

### F-07 `major` — 「判据只占三分之一」与实物相反，且被作者自己的 diffstat 证伪

**位置**：`SKILL.md:64`

原文：「某份 446 行的验收规范里，**判据只占三分之一**，其余是上述装置」。逐节量了两种口径（脚本按行区间累加字符数与行数）：

| 口径 | 判据（REQ／NS／STR／REL／TR／LIFE／CAL，切除前 76-369 行） | 全部装置（状态与判定＋manifest＋Gate 执行规则＋放行清单＋处置表＋额外落实） |
|---|---|---|
| 字符数 | 32961 / 57879 = **56.9%** | 21874 / 57879 = **37.8%** |
| 行数 | 294 / 446 = **65.9%** | 106 / 446 = **23.8%** |

**为什么是问题**：这不是四舍五入的出入，是**方向相反**。判据是多数，装置是四分之一到三分之一。最直接的证伪来自作者自己：本次切除删了 106 行 / 446 = 23.8%，如果判据真只占三分之一，删掉「其余」应当删掉约三分之二。这个数字是 `do-not-grow-a-proof-plane-around-the-criteria` 全节的招牌实证，写在一份此后每次加载都会被读到的 user 级 skill 里；数字错了，读者据此形成的比例直觉就是错的，而这一节本身并不需要这个数字才成立。附带：`SKILL.md:64` 的「12 处 SHA-256」也是行口径（含 SHA-256 的行数 = 12），按出现次数是 25 处、不同哈希 20 个——真实数字对论点**更有利**，没有理由用小的那个。另，这段实证**没有写出处仓库与 `file:line`**，读者无法自行复核。

**建议改法**：把该句改成「判据占约三分之二，其余三分之一是上述装置；本次切除删掉了其中的 106 行」，把 12 改成 25（或写明「12 行内共 25 处」），并补上 `.dev@52dbdee^:docs/anthropic-responses-bridge/acceptance.md` 这样的锚点。

### F-08 `major` — 「它从未执行过一次」这个绝对断言被它所引的文件本身证伪

**位置**：`SKILL.md:64`

原文：「那道门在 2026-08-22 就已失配，两天无人察觉；**它从未执行过一次**。」逐条核：

- 「446 行」✔ 可复现。「2026-08-22 失配」✔ 可复现——`1197da7` 日期正确，且 `docs/service-cutover/plan.md:11` 有同样记载。
- **但归属错了。** 2026-08-22 失配的是 `service-cutover/plan.md` 与 `readiness.md` **指向 acceptance.md** 的那两个绑定（`FINALIZED@4c9beed…`、`FINALIZED_ACCEPTANCE_ORACLE@f99492a…`），不是 skill 句子主语所指的「acceptance.md 里那 12 处、用来保证所依据的规格没被偷改」的绑定。两者在不同文件、守相反方向。
- **「从未执行过一次」被引文自身推翻。** 切除前的 `acceptance.md` 第 9、10、11、13 行反复记载「本轮现场以 `sha256sum` 与 Python `hashlib.sha256` **交叉复核**」——R3～R7 各轮都真的算了、也真的比对了。执行过，只是从未阻断过任何东西，也从未有任何测试 manifest 绑定过它（那部分才是真的没发生：全文自陈「本次没有运行候选实现测试」）。
- 唯一的旁证 `plan.md:11`「这条门从来没有人执行过」是**同一次改动、同一作者当天写下的**，不构成独立证据（`verifying-authoritative-claims`）。

**为什么是问题**：绝对断言写进 user 级 skill 后会被后来者当既定事实转述，而它现在只要有人翻开切除前的原文就会被当场推翻，连带削弱整节的可信度。**证据支持一个更弱也更准的说法，而那个说法对论点一样有力。**

**建议改法**：降级为「**那道门从未阻断过任何东西**：既没有任何测试 manifest 绑定过它，失配后也没有任何东西报警——它只是写在文里。」并把主语改回 `plan.md`／`readiness.md` 那两处绑定，或把「12 处」与「2026-08-22 失配」拆成两句、各自指明是哪一处。

---

## 分组结论

**第 1 组｜覆盖面对账**：切除前四节切成 23 条可拦错/可召回项，逐条核完——**两边都找不到的有 3 条**（状态词汇 `UNVERIFIED`/`BLOCKED`/`PASS` 的定义与「未取得证据 ≠ 实现缺陷」，见 F-03；Spec 章节→gate 映射，见 F-04；「扩展项一律记 `UNVERIFIED`、不得由实现临时创造 expected」的**全局**表述，其 per-gate 实例尚在故未单列），**断链 1 条**（F-02）。其余幸存情况见下表。

| 切除前的条目 | 现在在哪 |
|---|---|
| 双向控制（正确样本 + 缺陷注入 + 核红的来源） | skill `SKILL.md:12-23` ✔，且每条 gate 正文仍各带两个 bullet ✔ |
| 「注入用冻结 patch／可替换策略对象；恢复后复跑正确样本」 | skill 指向 `trusting-a-green-result`，该份 `:42`／`:97` 有 ✔ |
| 判据独立性 ①完整对象相等+缺席+顺序 | skill 第 4 条 ✔ |
| 判据独立性 ②真实 Anthropic SDK consumer 重放 | skill 第 2 条 ✔（通用化）＋ `acceptance.md:124/127/138` 保留项目实例 ✔ |
| 判据独立性 ③stream/nonstream 归一化后比较、不共用 serializer | skill 第 1 条 ✔（serializer 半）＋ `acceptance.md:152/226` 保留归一化半 ✔ |
| 判据独立性 ④唯一 marker 恰好一次 + 顺序精确相等 | skill 第 3 条 ✔ |
| 判据独立性 ⑤记录 commit／命令／退出码／注入目标；未执行标 UNVERIFIED | 后半在 skill `:54` ✔；前半（记录四要素）两边皆无 —— 判为**有意切除的证明装置**，不单列 |
| 判据独立性 ⑥测试 manifest 绑定 Spec SHA-256，hash 不同则 UNVERIFIED | 有意切除；skill `:68` 给了替代（钉提交）✔，但 acceptance.md 未落实（见 F-01） |
| 8 个证据标签定义 | `acceptance.md:23-32` ✔（`LIVE-CANARY` 丢了「queue pressure」、`LOCAL-FAULT` 丢了「close」，minor） |
| `POLICY-MANIFEST-v1` 的对账结论／`FINALIZED` 恢复声明／hash 门 | 有意切除 ✔ 正确 |
| `POLICY-MANIFEST-v1` 的域→Spec 章节→gate 映射 | **两边都无**（F-04） |
| 「架构是参考不是行为 oracle、不产生 expected」 | `acceptance.md:3` 保留 ✔ |
| 「Spec 修订则本文必须同改」 | `acceptance.md:3` 保留 ✔ |
| 最终放行清单的报告格式 | 有意切除 ✔ 正确 |
| 最终放行清单的三档判定规则 | **两边都无**（F-03） |
| 「用户最新约束的额外落实」7 条 | 7 条全部在 `acceptance.md` 的 REQ-05:68-74／NS-03:101-104／REL-06:204-206／CAL-04:294-320 里有等价正文 ✔ ——移出未造成损失 |

**第 2 组｜新 skill 的四病**：**过于宽泛——不成立**。三个不该触发的反例（「跑一下测试看有没有过」「把某个 flaky 测试改稳」「决定这次要不要写测试」）拿 description 去比，都因「手里还没有绿／正在写判据」而不命中。**过于收紧——不成立**（唯一擦边的是「已有绿、正在为下一片补判据」，但 `recall-over-precision` 下这属可接受的边界模糊）。**方言与普适——基本正确**：`SKILL.md:38` 有显式方言标注、`:46` 写了「形态跨项目，名字随项目起」，做得比多数 skill 好；但 `SKILL.md:14` 把邻居的范围限定丢了、写成了无条件全称（F-06），`SKILL.md:64` 的实证没有仓库与 `file:line` 锚点（F-07 附带）。**拆合——判定不该拆也不该合**，但 `SKILL.md:25-38` 该缩成指针（F-05）。

**第 3 组｜与邻居的重复与召回边界**：**分界站得住，不应合并。** 反向召回（决胜）：一个正在给模块列验收项、手里一条测试都没有的读者，不会去检索「信一个绿之前」——把内容并进 `trusting-a-green-result` 会让这个读者永远召不回 `each-evidence-tier-declares-what-it-may-not-impersonate` 与 `do-not-grow-a-proof-plane-around-the-criteria`，而这两节是全新的、邻居五份里都没有。正向召回也过（带「我这条验收判据将来判不判得了否」去检索，四节全部召回）。与 `making-a-gate-actually-fire`（门有没有被执行）、`declaring-something-done`（宣称完备前的自查）、`verifying-authoritative-claims`（别人的主张可不可信）、`running-a-procedure-as-written`（照着做能不能跑通）均无实质重叠。**唯一的真重复是 `SKILL.md:25-38` 对 `trusting-a-green-result` pattern #1 的重写，以及权威归属自相矛盾（F-05）——那是一节的问题，不是整份的问题。**

**第 4 组｜事实核查**：6 条断言里 **3 条可复现**（446 行 ✔；22 处 `UNVERIFIED` ✔，行口径，按出现次数是 23；2026-08-22 失配 ✔），**1 条口径可疑**（12 处 SHA-256 = 含该词的行数，实际 25 处 / 20 个不同哈希，见 F-07 附带），**2 条不成立**（判据占三分之一 → 实际约三分之二，F-07；「从未执行过一次」→ 被引文自身证伪，应降级为「从未阻断过任何东西」，F-08）。

---

## 我否决了什么

考虑过、查过、判定**不成立或不属本轮**的路线，逐条记下理由，免得日后有人重走：

1. **「移出『评审问题处置表』埋掉了用户的现行约束」** —— 一开始判为 blocker：`### 用户最新约束的额外落实` 那 7 条不是点时记录，是现行规范，跟着处置表一起被移出去了。逐条核完**撤销**：7 条在留下来的 gate 正文里全部有等价表述（REQ-05:68-74、NS-03:101-104、REL-06:204-206、CAL-04:294-320），包括「不建立 >16 MiB 专门 gate」「ping 与 batch 完整性是两个独立控制轴」这两条最容易丢的。移出未造成语义损失。
2. **「新 skill 应当并入 `trusting-a-green-result`」** —— 按反向召回测试判否，理由见第 3 组。写下来是因为纯推理排除的路线事后捞不回：不并的决定性依据是「手里还没有绿的读者不会去检索『信一个绿之前』」这一条，不是篇幅或主题相近。
3. **「证据分级表丢了两个限定词」** —— `LIVE-CANARY` 少了「queue pressure」、`LOCAL-FAULT` 少了「close」和「验证产品错误路径」。真丢了，但 `acceptance.md:287/290` 在 CAL-03 正文里仍写着 queue pressure，召回路径存在；判 minor，本轮不报。
4. **「文件头那句『下文出现的旧 hash、`upstream-only`、`READY_FOR_FINAL_REVIEW`、R2～R7 verdict』现在没有指涉对象」** —— 属实（切除后正文里这些基本不再出现），但它是一条兜底豁免句，无指涉对象时不产生错误行为，只是冗余。判 minor。
5. **「新 skill 的 description 在本次会话的可用技能清单里显示为空」** —— 观察属实：本次系统提示里 `writing-acceptance-criteria-that-can-fail` 与另外约 10 份既有 skill（`refactoring-shared-state`、`merging-upstream-selectively`、`reconciling-ledger-vs-artifacts` 等）一样只列出名字、不列 description。查过 frontmatter：description 存在且为 532 字符，长度、`: ` 出现与否、中英文都与「显示正常」的那批无法区分。**判定不成立为本次改动的缺陷**——同症状在多份未被本次触碰的 skill 上先已存在，因此不可归因。但如果 selector 真的看不到 description，这份 skill 就召不回，那是 B 级改动的致命面：**建议主会话另开一个便宜的探针**（在新会话里问一句只能靠 description 命中的话，看它浮不浮现），本评审无法从文件侧判定。
6. **「切除应当同时删掉 `acceptance.md:3` 里 `LIVING_ACCEPTANCE_ORACLE` 这个状态字面量」** —— 想过，判否。用户当日只裁了废除「冻结」，`LIVING_*` 是相反方向的标记；且切除前的正文明确记录改名属机制变更、待用户裁决。不擅自扩大。
7. **「没有为切除本身跑一次分辨力验证」** —— 想过要求作者证明「删掉这些装置不会让任何现有检查失效」，判**不适用**：这些装置从未接入任何可执行检查（F-08 已确认），没有可变异的对象，要求这一步就是在建它自己禁止的证明平面。

# Auto mode classifier 独立评审（Claude）

- 评审日期：2026-08-23
- 评审对象：`/home/xp/src/ghc-api-proxy-py` 当前未提交工作树（`git status` 见下方「评审基线」）
- 结论：**needs-fix**
- 发现计数：blocker 0，major 5，minor 6，nit 3

## 评审基线

被评审的五个文件（`git status --short`）：

```
 M src/app/config/schema.py
 M src/app/pipeline/delivery/formats/anthropic_messages_synthetic_reply.py
 M src/app/pipeline/driver.py
?? src/app/pipeline/auto_mode_classifier.py
?? tests/unit/pipeline/test_auto_mode_classifier.py
```

阅读顺序按任务要求：先 `.dev/docs/auto-mode-classifier/spec.md`，再两份取证报告（`.dev/docs/tmp/260823-cc-auto-mode-request-shape.md`、`.dev/docs/tmp/260823-auto-mode-traffic-samples.md`），再代码，再 `app.pretty.js`。另读了 `.dev/human-controlled-docs-candidates/auto-mode-classifier.md`。同伴报告 `.dev/docs/auto-mode-classifier/reports/260823-review-gpt.md` 在我形成全部发现之后才读，只用于标注重合与分歧，不用于产生发现。

### 我实际执行的验证（不是重复既有验证）

1. **把 JS 解析器真的跑起来做差分。** 从 `app.pretty.js` 逐字复制 `dLl` / `oLl` / `UGw` 到 Node（`/tmp/amc/run.mjs`），对 25 条对抗性输入取真值，再与测试文件里的 `parses_as_block` / `parses_as_severity` 逐条比对：**0 处不一致**。用例覆盖大小写变体、闭合与未闭合 `<thinking>`、yes/no 同现、`\b` 边界（`<block>yesterday`）、多个 `<severity>`、小数、前后空白、以及本特性实际会产出的全部文本。
2. **给这套差分做负样本对照**（否则「0 处不一致」可能只是探针没有分辨力）：把 Python 侧故意改坏三处——去掉 `re.IGNORECASE`、去掉 `oLl` 的前置双拼扫描、把 severity 的「恰好一处」放宽成「取第一处」——分别得到 2 / 2 / 1 处不一致。**探针有分辨力，因此那个 0 是真的 0。**
3. **对 severity 无 `stop_sequences` 的形状做端到端探针**（`/tmp/probe_auto_mode.py`），得到 major-1 的可执行反例。
4. **对 `reason` 过滤做大小写探针**，得到 major-3 的可执行反例，并跑了小写正样本对照确认过滤在小写下确实生效。
5. **顺 `app.pretty.js` 读完调用链**：`fhr`（368576）→ `zGw`（368453）→ `p1m`（368542）→ `oLl` / `QRl` / `UGw` / `iLl`，以及 severity 阈值来源 `DUi`（368356）/ `nLl`（368350）/ `aM`（150117）与 `Age`（429850）的 system 块拼装。

未重复执行的：`ruff check`、`pyright`、那 23 个测试。我没有理由怀疑它们的结果，但下文 minor-3 与 nit-3 说明那个绿灯**没有**覆盖到什么。

## 总体判断

这份实现的工程质量高于本项目的平均线：判据的证据链是真的（两个独立方向、有正样本对照）、失效方向是被设计过的、`verdict_text` 针对的是客户端解析器而不是格式手册、短路点的位置我逐项核对过基本正确。**问题集中在一处**：协议判别只实现了 spec 承诺的两条判据里的一条，于是「谓词半命中」这个本来被排除的状态真的存在，而它产生的是错误答复而不是透传——这同时证伪了代码、schema 注释、spec 与用户文档候选四处写下的同一句承诺。其余 major 各自独立且修法都很便宜。

没有 blocker。我与同伴报告在这一点上分歧明确，理由写在 §「与同伴报告的分歧」。

---

## Major

### major-1：severity 协议只靠 `stop_sequences` 判别，而客户端在三种形态下都不发这个字段——半命中会产出错误答复

- 严重度：major
- 置信度：机制**高**（有可执行反例 + 客户端源码控制流）；触发条件**中**（需要服务端下发的 gate 配置，本地不可见、2300 条样本中未出现）
- 位置：`src/app/pipeline/auto_mode_classifier.py:89-97`（`_protocol_of`）、`src/app/pipeline/auto_mode_classifier.py:100-119`（`classify` 的返回）、`.dev/docs/auto-mode-classifier/spec.md:43`
- 客户端证据：`app.pretty.js:368459-368460`（阶段 1 的 `...l !== "fast" && { stop_sequences: [u ? "</severity>" : "</block>"] }`）、`368474`（阶段 2 的请求对象**根本没有** `stop_sequences`）、`368454`（`G = u ? (Y) => QRl(Y) !== null : void 0`）、`368576-368612`（`fhr` 里 `c = i.severityEligible ? L1m(...) : null`，`Q = i.severitySite !== void 0 && c !== null ? "both" : i.twoStageMode ?? XGw()`）

`_protocol_of` 的判别式是「`stop_sequences` 里有 `</severity>` 就是 severity，否则一律 block」。但客户端决定用哪个解析器的开关是 `u`（severity 阈值对象）**是否存在**，与 `stop_sequences` 无关：只要 `u` 非空，`G` 就固定为 `QRl`，客户端就用 severity 解析器读回复。而 `stop_sequences` 只在 `l !== "fast"` 的阶段 1 出现。两者交叉后有三种形态是「用 severity 解析、却不带 `stop_sequences`」：

| 形态 | 触发条件 | 我方判别 | 客户端解析器 |
|---|---|---|---|
| `fast` 模式阶段 1 | `severityByModel` 命中但 `severitySite === undefined`（`DUi` 走 `NGw` 分支，`fhr:368612` 的 `Q` 因此不被强制成 `"both"`） | block（错） | `QRl` |
| `both` 模式阶段 2 | `decision: block` 时阶段 1 判 block，客户端继续发阶段 2 | block（错） | `QRl` |
| `thinking` 模式（只有阶段 2） | `twoStageMode` 或 `XGw()` 给出 `"thinking"` | block（错） | `QRl` |

可执行反例（`/tmp/probe_auto_mode.py`，用测试文件自己的转写解析器求值）：

```
protocol detected: block | text: '<block>no</block>'
client would parse it as severity -> None
```

`None` 即 `UGw` 找不到 `<severity>`，`QRl` 返回 `null`。后果分两段，都不好：

1. `p1m`（`368542`）的循环条件是 `while (s.count <= a && !l(u) && iLl(u) === "unparseable")`，`l` 此时是 `G`（QRl 版）。于是客户端**重试**，每次重试是一次完整的 710 KB 请求打到本代理。
2. 重试耗尽后，`fast` 模式走 `368465` 的 `Ne === null` 分支、`thinking`/阶段 2 走 `368477` 的 `de === null` 分支，两者都返回 `shouldBlock: true`。**配置的 `allow` 被客户端读成 block。**

这不是「漏判 → 透传」。谓词命中了、代答了、代答的内容客户端读不懂，于是客户端按自己的安全默认硬拦。这正是 spec §3 与 `classify` 的 docstring 宣称不会发生的那一类。

**触发条件的诚实描述**：`u` 来自 `aM()`，而 `aM()` 是 `nt("tengu_auto_mode_config", dgi)`（`app.pretty.js:150117-150121`），即一份由服务端下发的 dynamic config。所以 severity 模式的开关既不在客户端版本里、也不在本机配置里，Anthropic 可以随时翻转它而本地无任何信号。2300 条样本里没有 severity 形态（阶段 1 全是 `["</block>"]`），所以**今天不会触发**；但它不需要客户端升级就能触发，而客户端升级恰恰是本特性唯一设计过的失效通道。

**这一半是被静默砍掉的，不是没想到。** spec §4.1 的判别方式一栏写的是「请求 `stop_sequences == ["</severity>"]`，**或** system 文本含 severity 版 Output Format」；代码只实现了前半。取证报告 `260823-cc-auto-mode-request-shape.md:209` 也已经标注这条判据「**只在 both 模式的阶段 1 出现，覆盖不全**」。

**建议的修法（我倾向第一种）**：

1. **两个标签一起发，取消协议判别这个问题本身。** 我验证过 `<block>no</block>\n<severity>0</severity>` 同时被两个解析器接受：

   ```
   '<block>no</block>\n<severity>0</severity>' -> block: False severity: 0.0
   '<block>yes</block>\n<severity>100</severity>\n<reason>…</reason>' -> block: True severity: 100.0
   ```

   `oLl` 不看 `<severity>`，`UGw` 不看 `<block>`，`eLl`/`tLl` 各读各的。代价是回复里多一个当前协议没要的标签——但解析器不在意，而 prompt 的措辞本来就不是契约。收益是 `_protocol_of` 连同它依赖的那条字面量一起消失。
2. 补上 spec §4.1 的第二条判别（system 文本含 `$Gw` 的 Output Format，`368814`）。这是照 spec 办，但它又引入一条会静默失效的字面量，而这条失效时的方向仍然是错的。
3. 保守兜底：判不出协议就 `return None` 透传。能保住失效方向，但把「阶段 2 一律 block 协议」这个**在非 severity 场景下正确**的默认也一起放弃了。

无论选哪条，`_protocol_of` 的 docstring（`auto_mode_classifier.py:92`）里「Stage 2 carries none at all, and defaults to `block`」这句都要改：它把 bug 本身写成了设计。

### major-2：`_SEVERITY_BLOCK = 100` 无法保证落在 block 一侧，因为客户端允许阈值恰好是 100

- 严重度：major
- 置信度：机制**高**（客户端源码里阈值范围与严格比较都可读）；触发条件**低**（需服务端把阈值下发成 100，等于「永不拦截」）
- 位置：`src/app/pipeline/auto_mode_classifier.py:26-28`、`src/app/pipeline/auto_mode_classifier.py:133-135`、`.dev/docs/auto-mode-classifier/spec.md:87-91`
- 客户端证据：`app.pretty.js:368350`（`nLl` 接受 `e >= 0 && e <= 100`）、`368353`（`XGt` 用 `nLl` 过滤）、`368463` 与 `368474`（两处都是严格 `>`）、`368814`（默认值 `JRl = 15`、`ZRl = 20`）

`nLl` 把 `100` 认作合法阈值，比较是 `re > u.t1`。`t1 = 100` 时 `100 > 100 === false`，我方的 `block` 被读成 allow；更糟的是 `both` 模式下阶段 1 判 allow 会**立即返回**（`368464`），没有第二次机会。

spec §5.1 写「端点值在任何合理阈值下都落在正确一侧」——这句话在客户端自己定义的合法取值上就有反例。默认值是 15 / 20，所以要撞上必须有人显式下发 100，而下发 100 的含义正是「让分类器永不拦截」，这本身是个说得通的配置。

`UGw` 不做 `0-100` 范围校验（`368422-368428`，只有 `\d+(?:\.\d+)?` 与 `Number()`），所以 `101` 可以越过客户端允许的**全部**阈值，改动成本是一个字符。allow 侧的 `0` 没有对称问题：`0 > t` 对任何 `t >= 0` 恒假。

顺带：`_SEVERITY_ALLOW` / `_SEVERITY_BLOCK` 上方那段注释（`auto_mode_classifier.py:26`）说得很好——「只有端点值能被证明落在正确一侧」——但它选的端点是量程的端点（0/100），而需要的是**阈值定义域的端点之外**。把 100 改成 101 之后那段注释也要跟着改，否则它会解释一个已经不成立的理由。

### major-3：`reason` 的消毒是大小写敏感的，而客户端的扫描是 `/gi`

- 严重度：major
- 置信度：高（可执行反例 + 小写正样本对照）
- 位置：`src/app/pipeline/auto_mode_classifier.py:140`（`if verdict.should_block and reason and "<block>" not in reason`）
- 客户端证据：`app.pretty.js:368408`（`e.matchAll(/<block>(yes|no)\b/gi)`）、`368542-368566`（`p1m` 的重试循环）

`oLl` 的前置扫描带 `i` 标志，我方的守卫是 `"<block>" not in reason`，纯小写子串。反例（实测输出）：

```
emitted: '<block>yes</block>\n<reason>the rule literally says <Block>no</Block></reason>'
guard dropped the reason? False
client parse result: None      ← 不可解析，触发重试
```

小写正样本对照（`the rule says <block>no</block>`）确实被拦下并输出 `<block>yes</block>`，解析为 `True`。所以守卫在设计意图内是有效的，缺的只是大小写。

`reason` 是 schema 无约束的自由文本配置字段，一个操作者在里面引用客户端标签是完全可以想象的写法（这正是这条守卫存在的理由）。修法：把判据换成客户端自己的谓词，`re.search(r"<block>(yes|no)\b", reason, re.IGNORECASE)`，比现在的子串匹配既更准（不会因为无害的 `<block>` 字样丢掉整条理由）又更严（覆盖大小写）。

**关于那次变异验证**：作者做的「去掉 `verdict_text` 里的 reason 消毒条件」变异确实让 `test_a_reason_containing_a_decision_word_is_dropped` 变红了——但那只证明测试对**小写**拼法有分辨力。测试用例本身就是小写，所以它对本条缺陷是恒绿的。这是「变异打红只证明它打到的那一层」的一个干净实例。

### major-4：短路没有入口格式边界，非 Anthropic 入站请求会收到 Anthropic body

- 严重度：major
- 置信度：机制**高**（控制流可逐行读）；触发概率**低**
- 位置：`src/app/pipeline/driver.py:119-127`、`src/app/pipeline/reply.py:25-28`

`handle()` 对所有入站格式无条件调用 `classify()`。`_matches_transcript_open` 读的是 `messages[-1].content[0]`，而 OpenAI Chat Completions 的 body **也有** `messages`，其 `content` **也可以**是 `[{"type": "text", "text": …}, …]` 的 parts 数组。一旦命中，`_answered_auto_mode` 产出 Anthropic body，`response_payload`（`reply.py:25`）因为 `handled.synthesized` 直接原样返回，客户端拿到的是错协议的 200。

spec §1 自己把适用范围限定为 `/v1/messages`，代码比 spec 宽。修法是一个条件：

```python
if context.inbound_format is WireFormat.ANTHROPIC_MESSAGES:
    verdict = classify(...)
```

顺带把 §「误伤面」整体收窄一档——这是本次评审里性价比最高的一处改动。

### major-5：四处文档与注释写下了一句代码并不成立的承诺

- 严重度：major（属于「诚实性」而非功能缺陷，但它会让下一个读者据此放弃防护）
- 置信度：高
- 位置：`src/app/pipeline/auto_mode_classifier.py:103`（"a predicate that decays costs the bytes it was saving, **never a wrong answer to a security question**"）、`src/app/config/schema.py:93-94`、`.dev/docs/auto-mode-classifier/spec.md:28`（「失效方向是漏判——请求照常转发上游……不产生错误答复」）、`.dev/human-controlled-docs-candidates/auto-mode-classifier.md:66` 与 `:70`（「不会答错」/ "never a wrong answer"）

这四处说的是同一件事，而 major-1 与 major-2 各自给出了一条「谓词命中之后仍然答错」的路径。它们描述的失效通道也偏窄：四处都把失效归因于「客户端改写措辞（升级）」，但 major-1 的实际触发通道是**服务端下发的 dynamic config**，不需要客户端改一个字。

修 major-1 与 major-2 之后这些句子基本成立，但仍建议把失效通道从「客户端升级」扩写成「客户端升级**或**服务端下发的 gate 配置变化」，因为后者不可观测、不可控，而前者至少有版本号。用户文档候选那一份（`:64-72`）是操作者唯一会读的地方，尤其值得改准。

---

## Minor

### minor-1：spec §3 的 P1 写的是 `system[0].text`，代码扫描任意 system 块——**代码是对的，spec 是陈的**

- 严重度：minor
- 置信度：高（客户端源码可读）
- 位置：`.dev/docs/auto-mode-classifier/spec.md:25`、`src/app/pipeline/auto_mode_classifier.py:47-60`

我核对了代码注释里那个理由，它成立：`Age()`（`app.pretty.js:429850`）第 429857 行拼 system 数组时是 `D = [M ? { type: "text", text: M } : null, ...(d ? [] : [...]), ...system]`，其中 `M` 是 attribution 文本块，而分类器请求设了 `forceAttributionHeader: true`（`368459`）。所以 attribution 在 `system[0]`、监控 prompt 在 `system[1]` 是客户端的正常形态之一。再叠一层：本代理的 attribution 剥离（`inference.py:174` 一带）作用域是「`system[0]` 的起始若干行」，剥完仍在 index 0 留着一个块。

所以**不要**按 spec 把 P1 收回 `system[0]`；要改的是 spec。同时应该在 spec 里记下：这次放宽不损失精度——取证报告 §3.1 的排他性扫描（`260823-auto-mode-traffic-samples.md:95`）本来就是在对象字节里找「这句话出现在任何位置」，145781 条 operation 里只出现在分类器请求中。

我把同伴报告 B-05 里「实现比规格还宽 = 缺陷」这半条判为**不成立**，理由即上。

### minor-2：P2 的证据在 spec 里是循环的

- 严重度：minor
- 置信度：高
- 位置：`.dev/docs/auto-mode-classifier/spec.md:26`、`.dev/docs/tmp/260823-auto-mode-traffic-samples.md:80` 与 `:238`

spec 说 P2「2300 条全中」。但那 2300 条正是用 `json_extract(summary_json,'$.previewText') LIKE '<transcript>%'` **选出来的**（traffic report §3 首行）。用选择判据去证明选择判据的召回率，这句话是恒真的，读者却会把它读成一次独立测量。

非循环的论证存在，只是没人写下来：**P1 匹配了这 2300 条全部，而 P1 在 145781 条里排他**，于是 P2 ⊆ P1 ⊆ 分类器，P2 在该语料上零误报。召回侧则由结构保证——`zGw` 的 `Q`（`368454`）恒以 `<transcript>\n` 起头，且它恒是最后一条消息的 `content[0]`。

建议 spec §3 把这两句补上。这不是要求补测量，是要求把已有证据的推理链写对。

### minor-3：测试里的解析器转写在 ASCII 之外与 JS 不等价

- 严重度：minor（**我明确不同意把它判为 blocker**，理由见 §「与同伴报告的分歧」）
- 置信度：高（差分实测）
- 位置：`tests/unit/pipeline/test_auto_mode_classifier.py:98-123`

实测差异（左 JS 真值、右 Python）：

```
DIFF  '<block>yesé'          JS: (True, None)  PY: (None, None)
DIFF  '<block>yeſ</block>'   JS: (None, None)  PY: (False, None)
DIFF  '<severity>١</severity>' JS: (None, None) PY: (None, 1.0)
```

三处根因分别是：JS 非 `u` 正则的 `\b` 按 ASCII word 判定而 Python 按 Unicode；JS 的 `/i` 规范化拒绝把非 ASCII 折叠到 ASCII（`ſ` 不等于 `s`）而 Python `re.IGNORECASE` 会折；JS 的 `\d` 恒为 `[0-9]` 而 Python 匹配全部 Unicode 十进制数字。`\s` 也不严格等价（ECMAScript 与 Python 的空白集合各有对方没有的成员）。

**它今天不会让任何回复被错判**：生成器能产出的文本只有 `<block>yes|no</block>`、`<severity>0|100</severity>` 与 `<reason>` 包裹的配置文本，全在 ASCII 域内；我那 25 条差分用例覆盖了这个域的边界形态，0 处不一致。所以缺陷是**测试文件对自己的宣称说过了头**（docstring:5 说 "the client's own regexes, transliterated"），而不是产品行为已经错。

修法（便宜）：block 两处正则加 `re.ASCII | re.IGNORECASE`；severity 的 `\d` 写成 `[0-9]`；`\s` 要么显式写出 ECMAScript 的空白集合，要么在 docstring 里注明「等价性在 ASCII 输入域内成立，这也是本项目生成器的全部值域」。后者是诚实且够用的选择。

需要提醒的是：如果按 major-3 修 `reason` 的大小写，**修完必须用改好的 oracle 验**——用当前这个 IGNORECASE 语义不同的版本去证明大小写处理正确，是拿一把刻度不对的尺子量刚校准的东西。

### minor-4：完成行把一次本地作答记成了一次 HTTP/1.1 上游交换

- 严重度：minor（与既有 `_answered_failed_search` 共享，本改动是扩大而非引入）
- 置信度：高
- 位置：`src/app/pipeline/driver.py:211`、`src/app/pipeline/driver.py:218-222`、消费点 `src/app/server/routes/inference.py:267-270`

`_answered_auto_mode` 造的 `httpx2.Response` 带一个 `content=b""` 的假 request，于是 `trace.bytes_in = len(response.request.content)` 得 0、`trace.upstream_protocol = http_label(response.http_version)` 得 `HTTP/1.1`（httpx 对手工构造的 response 的默认值）、`received` 记的是我们自己写的 body 长度。本项目对这组字段的既定约定是「报 proxy↔upstream 那一段」（见项目记忆与 `request_log` 的注释），而这条路径上根本没有那一段。

`_answered_failed_search` 有同样的形状，但它至少真的飞过一次上游腿；auto mode 是**第一条完全没有上游交换的路径**，所以这里第一次出现「整行都是虚构」。

建议：让 synthetic 路径把这三个字段留缺席（本项目自己的约定是「缺席即没有可报的东西」，`reply.py:56-61` 明确写过这个读法），或者显式标成 local。`log_hit` 那条 INFO 是对的、有价值的，但它不能替另一条完成记录纠错——两行会被不同的人在不同的时候读。

### minor-5：本地成功不发布 `request.succeeded`

- 严重度：minor
- 置信度：高（控制流）
- 位置：`src/app/pipeline/driver.py:121-127`、`src/app/pipeline/direct_driver/base.py:33` 与 `:182`

短路在 driver 构造之前返回，因此 `EVENT_REQUEST_SUCCEEDED` 不会发布。跳过 `attempt.*` 是**对的**（没有 attempt，发布它们才是撒谎），跳过 reactive rate limiter 也是对的（它学的是上游 429/502）。但 `request.succeeded` 描述的是「这次客户端请求成功了」，而这次确实成功了。

现实影响今天为零：`subscribers/__init__.py` 里注册的三个 built-in 全是 `attempt.prepare`，没有任何生产代码订阅 `request.succeeded`。所以这是一处**契约失真**而不是功能回归，按 minor 记。

### minor-6：客户端会把这个常量答复呈现成一次模型判定，四份文档都没提

- 严重度：minor
- 置信度：高（客户端源码）
- 位置：`.dev/human-controlled-docs-candidates/auto-mode-classifier.md:25-29`、`.dev/docs/auto-mode-classifier/spec.md:17`

先说好话：候选文档 §2 那三行是本次改动里最诚实的一段——「效果接近 `bypassPermissions`，区别在于客户端仍以为自己在受审」把要害说清楚了，`decision`/`reason` 的默认值也不美化自己。**我没有找到任何一处把这个特性说得比它实际更聪明。**

差的是另一侧：客户端不只是「以为」，它还会**对用户展示**这是模型判的。`zGw` 在放行时返回 `reason: "Allowed by fast classifier"`（`368464`），并打 `lvr("success", o4, { classifierType, classifierModel … })`（同处）遥测。也就是说，Claude Code 的界面与统计里，这次放行与一次真实的模型审查**同形**。当操作者与使用者不是同一个人时（本项目的 subagent 场景就是），使用者没有任何本地信号能分辨。

建议在候选文档 §2 补一句，措辞可以直白：「打开后客户端仍会把每次放行显示为『Allowed by fast classifier』并计入 auto mode 的统计——它不知道是代理答的。」这句话属于操作者做决定时需要知道的后果，不是恐吓。

---

## Nit

### nit-1：`log_hit` 的字节数是一次重新序列化，不是收到的字节数

`src/app/pipeline/driver.py:208` 的 `len(dumps(source))` 与客户端实际发出的 body 长度不等（空白、Unicode 转义、键序都可能不同）。docstring（`:204`）说它是「the number that was actually going to cross the wire」，严格说是「我们把它再序列化一遍会有多长」。`inference.py:139` 的 `await request.body()` 读了原始字节但没留长度，所以现状是唯一低成本的选择——改 docstring 措辞即可，或者顺手把 body 长度记到 context 上。附带一提：每次命中要重新序列化 710 KB，量级 ~1 ms，可接受但不是零。

### nit-2：`parses_as_severity` 没有转写 `QRl` 的 `stop_reason` 闸门

`tests/unit/pipeline/test_auto_mode_classifier.py:115-123` 只转写了 `UGw`。`QRl`（`368418`）的 `stop_reason ∈ {stop_sequence, end_turn}` 这一层是靠另一个测试（`test_the_stop_reason_satisfies_both_parsers`）单独断言 body 字段来覆盖的，两个事实从未在同一处组合。让 `parses_as_severity` 收 body 而不是 text，两行就能把闸门包进去，severity 的往返测试就变成真正的端到端。

### nit-3：severity 协议从未走过 `handle()`

`TestTheShortCircuitIsWiredIn` 两个用例都是 block 协议。severity 只在 `TestProtocolSelection` / `TestTheClientCanParseTheAnswer` 里以 `classify` + `verdict_text` 的组合出现，没有一次经过 `_answered_auto_mode` 与 `auto_mode_body`。这不是覆盖率问题——**加一个「severity 语境但不带 `stop_sequences`」的夹具就会直接抓到 major-1**。修 major-1 时建议顺手把这个夹具补上，它是这一条缺陷唯一的回归防线。

---

## 逐项回答任务里的五个重点

1. **转写忠实性**：`oLl` / `dLl` / `UGw` 的结构转写**忠实**，我用真 JS 做了 25 条差分并配了三处负样本对照。唯一的不等价在 ASCII 之外（minor-3），不影响本特性能产出的任何文本。`QRl` 只覆盖了一半（nit-2）。
2. **误伤面**：真正找到的是 major-4（入口格式无边界）。P1 放宽到「任意 system 块」我判为**正确且必要**（minor-1），不构成误伤——它的排他性证据本来就是「这句话出现在任何位置」。P2 的精度靠 P2 ⊆ P1 传递得到，论证成立但 spec 没写（minor-2）。我没有找到「Claude Code 正常发送的普通请求」能撞上任一谓词的形态：P2 要求最后一条 user 消息的 `content[0]` **整块恰等于** `<transcript>\n`，客户端的普通用户轮要么是单块整段文本、要么以 `tool_result` 开头，都不满足。
3. **短路点位置**：位置基本正确。逐项核对结果——admission、body 读取、client deadline（`handle_bounded` 在外层）、routing、`on_routed`、header policy、denied-beta strip 及其 metric、attribution strip、`fix_anthropic_request` **全部在短路之前**，没有被绕过；`begin_attempt` / attempt deadline / RetryLedger / draining gate / reactive rate limiter / `attempt.prepare` 订阅者全部被跳过，且**跳过是对的**（没有上游腿）；`attempt_count == 0` 我查了所有消费点（`inference.py:249/261/264/301`、`request_log.py:382`、`footer.py:61`、`request.py:104`），全部安全——`current_attempt` 返回 `None` 且 `inference.py:330` 有 `attempt is not None` 保护，`attempts > 1` 的显示分支不触发。本项目 `src/app` 内没有 history writer，所以不存在被绕过的 history。真正的两处问题是 minor-5（`request.succeeded`）与 minor-4（虚构的上游腿）。`synthesized=True` 的交付路径对非流式与流式都成立（`delivery_policy.py:29/45`、`reply.py:25` 三处 carve-out 齐全），但流式**只有单元级形状断言**、没走过 `handle()`（`test_the_streaming_form_carries_the_same_decision` 只调 `auto_mode_sse`）；考虑到没有任何真实分类器请求是流式的，我认为这个覆盖深度是恰当的，不要求补。
4. **安全语义的诚实性**：没有任何一处把它说得更聪明——`spec.md:17`、`schema.py:83-87`、模块 docstring 与候选文档 §2 四处都反复说「是开关不是分类器」，措辞一致且不美化。反方向有两处会让操作者低估后果：major-5（承诺了一个不成立的失效方向）与 minor-6（客户端会把它显示成模型判定）。
5. **默认值与失效方向**：默认 `passthrough` 落实到位——`classify` 第一行就返回 `None`（`auto_mode_classifier.py:105-106`），有测试，`handle()` 里两次字典查找的开销描述属实；`NOT_HOT_RELOADABLE` 不含这个键，所以可以热改，这是对的。**失效方向不成立于两条路径**：major-1（谓词命中但协议判错 → 客户端硬拦）与 major-2（协议判对但分值不够 → 配置的 block 变 allow）。两条都属于任务里点名的「谓词半匹配时产生错误答复」。

## 与同伴报告的分歧

只列判断不同的，重合的不复述。同伴报告：`.dev/docs/auto-mode-classifier/reports/260823-review-gpt.md`。

- **它的 A-02（转写不忠实）判 blocker，我判 minor-3。** 事实层面我们一致（我独立复现了同类反例）。分歧在权重：那些反例全部落在生成器不可能产出的字符域外，因此它不构成「测试可能放过一个客户端会拒绝的回复」的**现实**风险，只构成 docstring 宣称过强。判 blocker 会让一条注释措辞问题与「配置的 allow 被读成 block」同级，这不利于排修复顺序。
- **它的 A-04（severity 100）判 blocker，我判 major-2。** 机制我完全同意并独立核对了 `nLl` 与两处严格比较。分歧在触发条件：需要服务端把阈值下发成 100（默认是 15/20），这既无流量证据也不是常见配置。修法免费，所以该修；但它不是「合入即坏」。
- **它的 B-05（谓词劫持）判 blocker，我拆成两半：** P1 放宽那半我判**不成立**（minor-1，代码正确、spec 陈旧，有 `Age()` 429857 的源码证据）；P2 那半我判 minor-2（论证链没写全，但结论正确）。它举的反例——「普通请求把第二个 system 块设成监控句」「普通请求的最后一条 user 消息第一块恰为 `<transcript>\n`」——都需要客户端刻意构造这个形状；本项目的威胁模型里没有这样的行为体，按项目规则不为想象的攻击者加防护。真正该收紧的是入口格式（major-4），那一条我们一致。
- **它的 C-01 / C-02 我同意，但降为 minor**：C-01 今天零订阅者、零影响；C-02 与既有 `_answered_failed_search` 同形，是被本改动扩大的既有缺陷，不宜记在这一次改动头上的严重度栏里。

## 建议的修复顺序

1. major-4（一个条件，收窄整个误伤面）。
2. major-1（我倾向「两个标签一起发」，它同时消掉 `_protocol_of` 与它依赖的字面量），并按 nit-3 补一个「severity 语境无 `stop_sequences`」的夹具作为回归防线。
3. major-2（`100` → `101`，并改掉 `auto_mode_classifier.py:26` 与 spec §5.1 里已经不成立的理由）。
4. major-3（换成客户端自己的谓词），修完用 minor-3 校准过的 oracle 验。
5. major-5 + minor-1 + minor-2 + minor-6：四处文档的同步，一起改，因为它们说的是同一批事实。
6. minor-4 / minor-5 / nit-1 / nit-2：可以留到下一个切片，不阻塞本次合入。

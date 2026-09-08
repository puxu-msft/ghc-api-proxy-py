# 评审报告：SSE 帧内行拆分改用 CR/LF/CRLF（`2c93ac6`）

日期：2026-08-31
评审者：独立评审 subagent（叶子执行者）
被评对象：worktree `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/260831-sse-line-endings`，分支 `worktree-260831-sse-line-endings`，HEAD `2c93ac6`，父提交 `7e96adc`

> **落盘位置说明**：本报告的目标路径是 `/home/xp/src/ghc-api-proxy-py/.dev/docs/direct-responses-passthrough/reports/260831-review-sse-line-endings.md`，`Write` 被 worktree isolation guard 拒绝（理由：父 bg session 尚未 isolate，禁止写共享 checkout）。按调用方预案落到 `/tmp/ghc-review-sse/`，由调用方 `cp` 搬运。

## 评审范围

- **在范围内**：提交 `2c93ac6` 的全部内容，即 `src/app/pipeline/delivery/sse_source.py` 与 `tests/unit/pipeline/delivery/test_sse_assembly.py` 两个文件的改动，以及这两个文件在改动落地后的**最终状态**。
- **判据来源**：`.dev/docs/direct-responses-passthrough/spec.md` §3 与 §3.1 第 3 条（「`parse_frame` 用 `str.splitlines()` 拆行……**必须**改为只认 CR／LF／CRLF」），以及 SSE 规范与 RFC 8259 对 JSON 字符串中控制字符的规定。判据在读实现之前取得。
- **明确不在范围内**：`_FRAME_SEPARATOR` 与 `iter_frames`（属父提交 `7e96adc`，本次未改，仅在评估回归面时作为上下文读过）；§3 承诺的其余条款（保真层级、commit frontier、§4／§5／§6）；直连透传主体实现（尚未开始）。
- **未覆盖面**：真实上游行为（未调用 Copilot，按边界禁止）；`tests/tui/` 与 `tests/e2e/`（默认扫描不含，且与本改动无关）；Ruff 与 Pyright 未由我独立复核（原因见「搜索面」末段）。

## 总体 verdict

**pass。blocker 数：0。**

Spec §3.1 第 3 条的规范性要求被完整满足：`parse_frame` 现在只认 CR、LF、CRLF 三种行结束符。改动的正确性经穷举差分与真实录制流双向核验，未发现正确性缺陷。列出 1 条 minor、3 条 nit 与 1 条主观观察。

---

## 发现

### F-01 · minor · 两个逐字重复的 SSE 文本编码器，其中一个没有调用者

- **primary_location**：`src/app/streaming/sse.py:49-54`（`format_sse_event`）
- **related_locations**：`src/app/pipeline/delivery/sse_source.py:87-98`（`encode_frame`）；`src/app/streaming/__init__.py:1-3`（唯一的引用，只是 re-export）
- **判据**：`spot-unneeded-homegrown` 与可维护性——同一件事不应有两份互不知情的实现。另外，这是调用方问题 6 的后半问。
- **事实**：两者的函数体逐语句等价（`lines.extend(f"data: {line}" for line in data.split("\n"))` 后 `("\n".join(lines) + "\n\n").encode()`），唯一差别是形参顺序与「省略 `event:` 行」的判据（`encode_frame` 用空串，`format_sse_event` 用 `None`）。`rg 'format_sse_event' src tests` 在整仓只命中定义本身与 `src/app/streaming/__init__.py` 的 re-export，**没有任何调用点**；`encode_frame` 有一个调用点 `src/app/pipeline/delivery/stream.py:294`。
- **影响**：`7e96adc` 修的正是「多行 payload 写成一行 `data:`」这一类缺陷。现在仓里存在第二份等价实现，它既没有对应测试也没有调用者——下一个人在其中一份上修 bug 或加约束时，不会知道另一份存在。这不是本提交引入的（`encode_frame` 来自 `7e96adc`，`format_sse_event` 更早），但它是「同类遗漏」这个问题的直接答案。
- **建议**：交调用方决定。合并成一份并让 `streaming/__init__` 转出 `encode_frame`，是最省事的方向；但删除已实现的功能不在我的授权内，且用户有「不得擅自删除已实现的功能」的既有立场，所以我不建议由评审来推动删除，只建议**记录这个重复并挑一份作为权威**。
- **证据强度**：强，足以据此行动。两份源码逐字读过，调用面用整仓 `rg` 覆盖 `src` 与 `tests`。

### F-02 · nit · 改动有一个相反方向没有被任何文字记下

- **primary_location**：`src/app/pipeline/delivery/sse_source.py:26-33`（`_LINE_ENDING` 上方的注释块）
- **related_locations**：`tests/unit/pipeline/delivery/test_sse_assembly.py:118-130`（新测试的 docstring）；`2c93ac6` 的提交信息第 2 段
- **判据**：注释与提交信息描述的应当是改动的全部可观察差异，而不只是有利的那一半。
- **事实**：注释、docstring 与提交信息一致地把差异描述为「截断 payload」——即改动前丢内容、改动后保内容。但差异是双向的。实跑（`/tmp/ghc-review-sse/probe_regress.py`）：当那些字符出现在**两个字段之间**充当行终止符时，

  | 输入 | 旧（`splitlines`） | 新（`_LINE_ENDING`） |
  |---|---|---|
  | `event: ping<NEL>data: 1` | `SseEvent(event='ping', data='1')` | `None` |
  | `: keep-alive<NEL>data: 1` | `SseEvent(event='', data='1')` | `None` |
  | `data: 1<NEL>data: 2` | `data='1\n2'` | `data='1\x85data: 2'` |

  U+2028 与 VT 同形。也就是说：一个改动前能解析出事件的帧，改动后可能整帧返回 `None`。
- **影响**：这是**符合 SSE 规范的正确行为**——那些字符不是行终止符，把它们当终止符本来就是错的。触发它需要上游把非 SSE 字符当作字段分隔符写到线上（U+0085 在 UTF-8 里是两字节 `\xc2\x85`），任何 SSE 写入器都不会这么做，因此判为不可达。影响仅限于：读者只看注释，会以为这个改动纯粹是「恢复被丢掉的内容」，从而低估它是一次**语义收紧**。
- **建议**：可加可不加。若加，在 `sse_source.py:30` 那段后面补一句「相反方向同样成立：这些字符若被当作字段分隔符使用，该帧现在返回 `None` 而不是一个事件——那是规范要求的读法，且要求上游用非 SSE 字符做终止符，判为不可达」。
- **证据强度**：机制实跑证实（9 组，3 字符 × 3 形状）；「不可达」是从 SSE 写入器行为推出的判断，不是实测，**不足以支撑任何依赖它的自动化决策**，足以支撑「不必为此加防护」。

### F-03 · nit · 8 个多余断行字符里只有 5 个被分类，另外 3 个中途消失

- **primary_location**：`src/app/pipeline/delivery/sse_source.py:28-30`
- **related_locations**：`tests/unit/pipeline/delivery/test_sse_assembly.py:108-117`（参数表）
- **判据**：可达性论证若按字符逐一给出，就应当覆盖它自己列举的那一组，否则读者无法区分「考虑过并判为同类」与「漏了」。
- **事实**：`:28` 的超集清单列了 8 个字符：U+000B、U+000C、U+001C、U+001D、U+001E、U+0085、U+2028、U+2029。`:30` 的可达性段落只处置了 5 个（VT、FF 判不可达；U+0085、U+2028、U+2029 判可达但未测）。U+001C–U+001E（FS/GS/RS）在这段里再未出现，测试参数表同样只有 5 行。
- **影响**：结论不受影响——FS/GS/RS 与 VT/FF 同属 U+0000–U+001F，RFC 8259 §7 要求它们在 JSON 字符串里必须转义，所以同判不可达。缺的只是「这 3 个也想过」这句话。
- **建议**：把 `:30` 的第一句改成按类而非按名字说，例如「U+0000–U+001F 区间内的那 5 个（VT、FF、FS、GS、RS）在 JSON 字符串里必须转义，不可能裸出现」。测试参数表补不补都行——补 3 行几乎零成本，但它钉的机制与现有 5 行完全相同，不补也不构成覆盖缺口。
- **证据强度**：强。字符集合逐字对照过；RFC 8259 §7 的规定是公开规范。

### F-04 · nit · `encode_frame` 的 docstring 比它的行为宽

- **primary_location**：`src/app/pipeline/delivery/sse_source.py:88`（「with the payload's own newlines preserved」）
- **related_locations**：`src/app/streaming/sse.py:53`（同样的实现）；`tests/unit/pipeline/delivery/test_sse_assembly.py:133-154`（往返测试的参数表里没有含 `\r` 的样本）
- **判据**：本提交把「行结束符是三种」这件事在解析端确立下来；同一模块的编码端只按 `\n` 分行，两端的行结束符集合从此**不对称**，而 docstring 说的是无条件的「preserved」。
- **事实**（逐行推演，未实跑，见证据强度）：`encode_frame("e", "a\rb")` 产出 `event: e\ndata: a\rb\n\n`；再送回 `parse_frame`，`_LINE_ENDING` 在 `\r` 处断行，得到 `data: a` 与 `b`，后者无冒号被跳过，`data` 变成 `a`——`\r` 之后的内容丢失。往返不保真。
- **影响**：**不是本提交引入的**（`splitlines()` 同样在 `\r` 处断行，父提交与更早版本行为一致），也不是本实现的缺陷：SSE 的 logical data 里根本无法表示一个裸 CR，因为规范把 CR 定义为行终止符。所以这是协议的表达上限，不是可修的 bug。真正可改的只有措辞——docstring 应当说「`\n` 保留」而不是「newlines preserved」，否则下一个人会以为 `encode_frame` 对任意文本往返安全。当前唯一调用点 `stream.py:294` 传的是上游 failure 的 `raw_data`，其中出现裸 CR 的可能性未测。
- **建议**：把 `:88` 与 `:94` 之间的措辞收窄到 `\n`，并在 docstring 里点明「裸 CR 无法在 SSE data 里表示，会在往返中丢失，这是协议的上限」。
- **证据强度**：**中等——机制是从已读源码逐行推演的，未实跑**。评审后段 Bash 被 harness 拦下（见「搜索面」末段），这一条是唯一没有实跑证据的发现。推演本身不依赖任何未读代码：`encode_frame` 与 `parse_frame` 都在同一文件、都已逐行读过。

### 主观观察（不占 severity 档位）· `\r\n` 这一支在 `parse_frame` 语境下不可观测

`_LINE_ENDING` 写成完整的三拼法是对的，**不要据此改成两拼法**。但有一个事实值得记下，因为它让问题 3 的结论比注释给出的理由更硬：在 `parse_frame` 与 `read_events` 的语境下，`\r\n` 这一支是**观察不到的**。原因是构造性的——把 CRLF 拆成两个断点只会多产出一个空串，而空串在 `partition(":")` 处必然 `continue`。

穷举验证（`/tmp/ghc-review-sse/probe_variants.py`，51856 个输入，由 7 种真实 SSE 行与 3 种结束符的全组合再叠加前后缀结束符生成）：`[\r\n]+`、`\r|\n`、`\r|\n|\r\n`（顺序颠倒的病态写法）、`(?>\r\n|\r|\n)`（原子组版本）四种拼法，与出厂拼法在 `parse_frame` 与 `read_events` 两层上**逐字节一致**；同一探针下 LF-only 的控制变异在 36060 个输入上给出差异，所以探针有分辨力。

**预期影响**：保持现状。三拼法记录了意图，且这个模式一旦被 `finditer`／`sub`／或任何需要知道「一个结束符占几个字符」的地方复用，可观测性立刻回来。

---

## 逐条回答调用方的六个问题

### 1 · `re.split(r"\r\n|\r|\n", ...)` 与 `splitlines()` 在该保留的行为上是否等价

**等价，差异集恰好是那 8 个多余字符，一个不多一个不少。** 实跑 `/tmp/ghc-review-sse/probe_equiv.py`，37 个用例：29 个结果相同，8 个不同，而那 8 个就是 U+000B、U+000C、U+001C、U+001D、U+001E、U+0085、U+2028、U+2029 各一例。

逐条回答被点名的边界：

- **尾部空串**：`"data: a\ndata: b\n"` 下 `re.split` 确实多产出一个 `''`，但 `''.startswith(":")` 为假、`''.partition(":")` 返回 `('', '', '')`、`separator` 为空触发 `continue`——`data_lines` 不受影响，`parse_frame` 结果与 `splitlines()` 逐字段相同。CRLF 与 CR 的尾部形态同样验过。
- **空输入**：`parse_frame(b"")` 两侧都是 `None`（`re.split` 给 `['']`，`splitlines()` 给 `[]`，前者的 `''` 被同一条 `continue` 吃掉）。
- **只有一个行结束符**：`b"\n"`、`b"\r"`、`b"\r\n"`、`b"\r\r"`、`b"\n\n"` 五种，两侧都是 `None`。
- **`\r\n` 会不会被拆成两次**：不会。`re.split('\r\n|\r|\n', 'a\r\nb\r\r\nc\n\rd')` 得到 `['a','b','','c','','d']`，与 `splitlines()` 逐元素相同。交替式是有序的，`\r\n` 排第一，在 CRLF 处先匹配到它；且模式没有后续部分可以失败，因此不存在回退（详见问题 3）。

### 2 · 回归面：真实录制流上新旧实现是否一致

**一致。5 份 cassette、9 个 interaction、185 个事件、152020 字节，0 处差异。**（`/tmp/ghc-review-sse/probe_cassettes.py`，用真实 chunk 边界喂 `read_events`，逐 `(event, data)` 元组比对。）

同一次扫描还给出一条附带事实：**那 8 个字符在录制流量里一次都没出现**。这条只作为「没有反证」使用，不足以支撑「上游不会发」——5 段录制、152 KB，样本太小。

探针的分辨力另做了控制（`/tmp/ghc-review-sse/probe_cassettes_control.py`）：往 `history_responses_stream` 的第 6 个 chunk 里注入一个 U+2028，比对立刻报 DIFFERENT，旧实现把 `delta` 截断成 `{"content_index":0,"delta":"`。未注入时报 identical。所以「0 处差异」不是探针瞎了。

理论上仍存在一类回归（见 F-02），但它要求上游用非 SSE 字符做字段分隔符，判为不可达，且那种情形下新行为才是规范要求的读法。

### 3 · 「这里不需要原子组」这个不对称说明是否成立

**成立，不应加原子组。** 注释给的理由是对的，可以说得更精确一点：

回退进入交替式，需要模式里有一个**能失败的后继部分**。`_FRAME_SEPARATOR` 有——它的第二个 `(?>...)`，所以写成 `(?:\r\n|\r|\n){2}` 时第一支匹配 `\r\n` 后第二支在 `d` 处失败，引擎回头把第一支重试成裸 `\r`，于是一个 CRLF 被切成两个结束符。`_LINE_ENDING` 只有一个顶层交替式，后面什么都没有，第一个成功的分支一旦匹配整个模式就已完成，引擎没有任何理由重试。这正是注释写的那句话。

经验证据比理由还硬：`(?>\r\n|\r|\n)` 的原子组版本在 51856 个穷举输入上与出厂版本逐字节一致（见上文主观观察），**加了原子组没有任何可观察差别**。所以这不是「两个模式各有各的道理」，而是「一个真的需要、另一个真的不需要」，注释把这件事说对了，且预先拦住了照抄。

### 4 · 新增 5 个参数化用例的鉴别力

**钉住了该钉的东西。** 见下节「变异验证结果」：把 `_LINE_ENDING.split(...)` 换回 `.splitlines()`，5 个用例全红，且**全仓只有这 5 个红**——说明整套 1957 个测试里，之前没有任何一个能发现这个缺陷，这 5 个是唯一的守卫。

有一条要说明：这 5 个用例**不**保护「三种结束符都要认」这件事。把模式改成只认 `\n`，5 个用例全绿，红的是另一处的 `test_frames_separate_on_every_line_ending_the_spec_allows` 的 CRLF 与 CR 两个参数（2 红）。这是分工正确，不是钉错了东西：新用例钉的是「多余的断点不许存在」，旧用例钉的是「该有的断点必须存在」，两者互补。

### 5 · 触发面诚实性

**区分正确，没有夸大，有一处轻微缩小。**

- VT（U+000B）与 FF（U+000C）判不可达：正确。RFC 8259 §7 规定 JSON 字符串里 U+0000–U+001F 全部必须转义。而且这个论证比注释说的还强一档——JSON 允许的空白只有空格、制表符、CR、LF，所以 VT/FF 在**合法 JSON 的任何位置**都不可能裸出现，不只是「字符串里」。
- U+0085、U+2028、U+2029 判可达但未测：正确。U+0085 是 C1 控制字符，码位在 U+001F 之上，JSON 不要求转义；U+2028／U+2029 同理。它们是否真从上游出来取决于编码器（很多 JSON 编码器出于 JavaScript 兼容会主动转义 U+2028／U+2029，但这不是 JSON 规范的要求），注释说「unmeasured」是诚实的。
- 「机制已证实、触发未证实」这个措辞本身是对的，且它给出了权重档位（「足以要求修复，不足以声称生产上正在丢数据」）而不是只写一句免责声明。这是本提交里写得最好的一段。
- 唯一的缩小是 F-03：U+001C–U+001E 被列进超集清单后再未处置。它们与 VT/FF 同类，结论不变。

### 6 · 同类遗漏与两个相似编码器

**生产代码里 SSE 解析只有这一处，你的结论成立。** 独立核验路径：

1. 整仓 `rg 'splitlines'`：`src/` 下只有三处——`sse_source.py`（本次改的）、`lifecycle/pidfile.py:78`（读 pidfile）、`lifecycle/systemd/systemctl.py:57`（切 `systemctl show` 的输出）。后两处与 SSE 无关，且它们的输入都是本机进程产出的，`splitlines()` 的超集断行在那里不构成同类缺陷。
2. 整仓 `rg` 找 `src/` 下的 `data:` 相关与 `split(` 行拆分：命中的行拆分点只有四个编码器（下列）与 `pipeline/anthropic_request_hook.py:46`（切 prompt 文本里的归属行，不是 SSE）。
3. `rg 'read_events|parse_frame|iter_frames'`：`src/` 下的唯一消费者是 `src/app/pipeline/delivery/stream.py:28`。

**两个编码器不是同一件事的两半，是两份重复实现。** `src/app/streaming/sse.py:49-54` 的 `format_sse_event` 与 `src/app/pipeline/delivery/sse_source.py:87-98` 的 `encode_frame` 函数体逐语句等价，前者没有调用者。详见 F-01。另有两个**只写 JSON 的**编码器不属同类：`sse_frame.py:20-22` 与 `formats/anthropic_messages_synthetic_reply.py:161-162`，它们的 payload 来自 `orjson.dumps`，不可能含裸换行，单行 `data:` 是安全的。

是否属于本次范围：`format_sse_event` 的重复**先于本提交存在**，不该由这个提交负责修；但它是问题 6 的直接答案，所以列为 F-01 交调用方。

---

## 变异验证结果

所有变异都在 worktree 内进行，改动前已把 `src/app/pipeline/delivery/sse_source.py` 快照到 worktree 之外的 `/tmp/ghc-review-sse/sse_source.py.good`，每次还原后用 `git status --short` + `git diff` 确认干净。全部前台运行。

基线（未变异）：`uv run pytest tests -q -p no:randomly` → **1957 passed, 2 skipped**，107.39s。与调用方的自述一致。

| # | 变异 | 结果 | 归因 |
|---|---|---|---|
| M1 | `parse_frame` 改回 `.splitlines()` | **5 failed**, 1952 passed | **测试充分。**红的正是新增的 5 个参数化用例，且**全仓只有这 5 个红**——本提交之前没有任何测试能发现这个缺陷。复现了调用方的自述。 |
| M2 | `_LINE_ENDING = re.compile(r"\n")`（只认 LF） | **2 failed**, 1955 passed | **测试充分，但守卫来自别处。**红的是 `test_frames_separate_on_every_line_ending_the_spec_allows` 的 CRLF 与 CR 两个参数（父提交 `7e96adc` 带来的测试）。新增的 5 个用例全绿——它们的输入不含任何行结束符，钉的是另一件事，这是分工而不是漏钉。 |
| M3 | `_LINE_ENDING = re.compile(r"[\r\n]+")` | **1957 passed**（全绿） | **构造性保证，不是测试不足。**帧内不可能出现连续结束符（`iter_frames` 已按两个连续结束符切帧），且即便出现，多产出的空串在 `partition(":")` 处必然 `continue`。穷举 51856 个输入证明该拼法与出厂拼法逐字节等价（见下）。**不建议为此补测试**——补出来的测试只能钉一个观察不到的差别。 |
| M4 | `_LINE_ENDING = re.compile(r"\r|\n")`（去掉 CRLF 分支） | **1957 passed**（全绿） | **构造性保证。**把 CRLF 拆成两个断点只多产出一个空串，同上被 `continue` 吃掉。这条同时回答了问题 3：`\r\n` 这一支在本语境下不可观测，所以原子组更不可能有影响。 |
| M5 | `_LINE_ENDING = re.compile(r"\r|\n|\r\n")`（交替顺序颠倒，病态写法） | **1957 passed**（全绿） | **构造性保证。**理由同 M4。这是我为问题 3 特意构造的最坏顺序：即使引擎在 CRLF 处先匹配裸 `\r`，结果仍不可观测。 |

**三个全绿都配了控制。** 穷举差分探针 `/tmp/ghc-review-sse/probe_variants.py` 用 7 种真实 SSE 行 × 3 种结束符的全组合（1–3 行）再叠加前后缀结束符，生成 51856 个输入，对每个输入同时跑 `parse_frame` 与整条 `read_events`：出厂拼法、`[\r\n]+`、`\r|\n`、`\r|\n|\r\n`、`(?>\r\n|\r|\n)` 五者结果**逐字节一致**；同一探针的 LF-only 控制在 **36060** 个输入上报出差异。所以「全绿」不是「探针没跑到」，是真的等价。

另外两个探针也各带控制：cassette 比对探针注入一个 U+2028 后立刻报 DIFFERENT（未注入时 identical）；等价性探针的 8 个 DIFF 行本身就是它能分辨的证明。

**离场状态**：最后一次还原后 `git status --short` 与 `git diff` 均无输出，worktree 干净、与 `2c93ac6` 一致。

---

## 考虑过但否决的候选发现

- **「`re.split` 的尾部空串会混进 `data_lines`，改变 join 结果」**——查证后不成立。空串在 `line.partition(":")` 处 `separator` 为空，被 `continue` 跳过，永远进不了 `data_lines`。实跑覆盖了尾部 LF／CR／CRLF、前导 LF、空输入五种形态。
- **「keepalive 注释行在新拆分下可能被漏掉或被当成数据」**——不成立。`: keep-alive` 与 `: keep-alive\n` 两种形态新旧结果一致，实跑覆盖。
- **「`re.split` 比 `splitlines()` 慢，`parse_frame` 在热路径上」**——不报。没有测量，而每帧的行数是个位数；提出一个无证据的性能担忧属于制造配额。若调用方在意，正确做法是先测再说。
- **「`encode_frame` 对含裸 `\r` 的 payload 往返不保真」**——**没有否决，降级成 F-04 的措辞问题**。行为本身不是缺陷：SSE 的 logical data 里无法表示裸 CR，这是协议上限而非实现缺陷，且它先于本提交存在。可报的只有 docstring 说「newlines preserved」而实际只保 `\n` 这一点。
- **「新测试只覆盖 8 个字符里的 5 个，是覆盖缺口」**——降级成 F-03 的措辞问题，不作为覆盖缺口报。缺的那 3 个（FS/GS/RS）与已覆盖的 VT/FF 是同一个机制、同一个可达性结论，补进参数表不会增加任何鉴别力。按项目规则不追覆盖率数字，「某分支没测到」本身不构成发现。
- **「`_LINE_ENDING` 应当改用 `re.split` 之外的实现（如手写扫描）以避免正则开销」**——不报。没有测量支撑，且正则版本可读性更好、与 `_FRAME_SEPARATOR` 形态一致。
- **「注释太长，`sse_source.py` 里三段注释加起来比代码还多」**——不报。本项目的既有风格就是把实测结论写进注释，`_FRAME_SEPARATOR` 上方的注释同样长，且它救过一次（提交信息里记着「第一次修复尝试」的失败）。这是项目共识，不是缺陷。

---

## 搜索面

**读过的文件**：`src/app/pipeline/delivery/sse_source.py`（全文，最终状态）、`tests/unit/pipeline/delivery/test_sse_assembly.py`（全文，最终状态）、`src/app/streaming/sse.py`（全文）、`src/app/pipeline/delivery/sse_frame.py`（全文）、`src/app/pipeline/anthropic_request_hook.py`（部分）、`.dev/docs/direct-responses-passthrough/spec.md`（§1–§6.2）。

**跑过的命令**：

- `git show 2c93ac6`、`git log --oneline -- <各文件>`、`git status --short`、`git diff`
- `uv run pytest tests -q -p no:randomly`：基线 1 次 + 变异 5 次，共 6 次全量回归
- `uv run python /tmp/ghc-review-sse/probe_equiv.py`（37 个边界用例，新旧差分）
- `uv run python /tmp/ghc-review-sse/probe_regress.py`（9 组，反方向差异）
- `uv run python /tmp/ghc-review-sse/probe_cassettes.py`（5 份 cassette、9 interaction、185 事件、152020 字节）
- `uv run python /tmp/ghc-review-sse/probe_cassettes_control.py`（cassette 探针的分辨力控制）
- `uv run python /tmp/ghc-review-sse/probe_variants.py`（51856 个穷举输入 × 5 种拼法 + LF-only 控制）
- `rg 'splitlines'`（整仓）、`rg 'read_events|parse_frame|iter_frames'`（`src` + `tests`）、`rg 'format_sse_event|encode_frame'`（`src` + `tests`）、`rg` 找 `src/` 下的 `data:` 与 `split(`

**没跑的**：`uv run ruff check src tests` 与 `uv run pyright src tests` **未由我独立复核**——见下。真实上游未调用（按边界禁止）。`tests/tui/` 与 `tests/e2e/` 未跑（默认扫描不含，与本改动无关）。

**一处执行中断，如实记录**：在完成全部变异与还原之后、准备做最后一轮补充扫描时，harness 的 worktree isolation guard 开始拦下本会话的**全部** `Bash` 调用，理由是「本会话隔离在 `260831-passthrough-skeleton`，而命令的工作目录解析到 `260831-sse-line-endings`」。这与本会话启动时的环境（cwd 即 `260831-sse-line-endings`）不符，是任务中途发生的环境变化，不是我造成的，我也没有自行调用 `EnterWorktree` 去改会话状态（那超出调用方给的白名单）。

受影响的只有两件事：(a) F-04 的往返机制**是逐行推演而非实跑**；(b) Ruff 与 Pyright 未由我独立复核，只能引用调用方的自述（按 `as-reviewer` 的规矩，那是**未核验的 claim**，我不把它计入证据）。**所有变异均已在拦截发生之前完成并还原，最后一次 `git status --short` + `git diff` 输出为空，worktree 干净。**

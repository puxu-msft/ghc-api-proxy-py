# 本次收尾的未完成项：独立枚举与双向对账

日期：2026-08-20
性质：独立核对报告。核对者未参与本次实现，先独立枚举再看主会话清单。
基线 HEAD：`7086c93`（枚举期间 `c57a15d`／`7086c93` 于 20:46 落入，晚于本次工作的多数提交）

**只读核对，未修改任何源码、测试或既有文档。**

## 0. 方法与证据强度

枚举来源：`rg` 全仓扫描、`docs/tmp/260820-websearch-responses-leg-mapping.md`、`docs/agents/anthropic-responses-bridge/hosted-web-search-spec.md`（DRAFT）、`docs/.human-controlled/test-org.md`、`.claude/rules/00-development-workflow.md`，以及两次实跑。

每条结论标注证据强度：

- **强（可直接据此行动）**：有 `file:line` 或命令输出直接支撑。
- **中（需再确认一步）**：代码事实清楚，但「它在生产链路上是否可达」这类问题依赖既有结论。
- **弱（仅记账）**：未探针，只能说「没有证据说它不会发生」。

## 1. 当前测试状态（实跑）

| 命令 | 结果 |
|---|---|
| `uv run pytest -q` | **1552 passed, 2 skipped**，104.66s，exit 0 |
| `uv run pytest tests/e2e tests/tui -q` | **11 passed**，18.32s，exit 0 |
| `uv run pytest tests/e2e -q` | **5 passed**，9.18s（`claude` 二进制在位，整组**没有**被跳过） |

对照：`260820-websearch-responses-leg-mapping.md:202` 记的是「1424 passed」。那是切片当时的快照，今天已不成立。

## 2. 独立枚举

### 2.1 实现缺口（代码事实）

**G1. 我们自己合成的 server-tool 块，回到 Responses 腿时被静默丢弃。强。**

合成回复给客户端的是真正的 Anthropic 块对（`src/app/pipeline/delivery/synthetic.py:79-100`：`server_tool_use` + `web_search_tool_result`）。客户端下一轮会原样回传。此时：

- `src/app/pipeline/translation_driver/anthropic_messages.py:67-103` 的 `_block_from_anthropic` 对这两种 `type` 都不认，落到最后一行 `return ContentBlock(BlockKind.UNKNOWN, raw=raw)`（:103）。
- `src/app/pipeline/translation_driver/openai_responses.py:479-480`：`conversion.record(LossCode.BLOCK_NOT_CARRIED, ...)` 后 `return None` —— **块被丢掉，只留一条没有消费者的 loss**（见 G5）。
- `builtin:server-tool-capability` 摊平历史，但 `src/app/pipeline/subscribers/server_tools.py:244` 明确 `if context.target_format is not WireFormat.ANTHROPIC_MESSAGES: return`，Responses 腿不走它。

后果：模型在下一轮完全看不到「上一轮尝试过搜索且失败了」。spec §5.4 与 §10 要求 Responses 腿**必须**把历史 server-tool 块摊平成文本（用共享渲染实现），**未实现**。

附带更正一条规格陈述：spec §5.4 与 §10 都写「今天是 `REJECT`」，指向 `src/app/protocols/anthropic_responses.py:408-409` 的 `server_tool_not_supported`。那个文件只被 `src/app/anthropic/client.py:20` 与 `src/app/protocols/responses_anthropic.py:14` 引用，属旧链路（旧链路的判定依据：`docs/agents/history-forensics/proposal.md:44`）。**生产链路上的真实行为是静默丢弃，不是 400。** 这正是「守卫被留在了 legacy 链路上」那一族。

`rg -ln "server_tool_use" tests/` 显示无任何测试覆盖「历史里带这对块 → 走 Responses 腿」。

**G2. 三个 `web_search_call` 专有事件既未被记录，也未被识别。强／中。**

- 生产链路（`src/app/pipeline/delivery/assembler.py:218-234`）：`push` 的最后一行是裸 `return ()`，任何未列举的事件类型被静默忽略。**流不会坏，但 spec §6.2 要求的「记录 event type 与 provenance」没有发生。**
- 旧链路（`src/app/openai/responses_stream_parser.py:899-914` 的 `_unsupported` → `src/app/delivery/anthropic_sse.py:884` 的 `ResponsesDeliveryError`）：这三个事件会落进默认分支并变成交付错误。旧链路挂在 `app_factory.create_app()`（`src/app/server/app_factory.py:168`）上，生产用的是 `create_pipeline_app`，所以这条**当前不可达**（中：依赖既有的旧链路判定）。

**G3. 其余 Anthropic typed tool 仍原样透传。强。**

`src/app/pipeline/translation_driver/openai_responses.py:149`：`_ANTHROPIC_SERVER_TOOL_FAMILIES = ("web_search_",)` —— 只有一族。`web_fetch_20250910`、`bash_20250124`、`text_editor_*`、`computer_*`、`memory_*`、`tool_search_*` 全部走 `_function_tool` 原样发往 `/responses`，整轮 400。spec §13 要求 `web_fetch` 本地明确 `REJECT`，也未实现。

**G4. `tool_choice` 只有「指向 web search 的那一条」跨得过协议边界。强。**

`_carry_forced_search`（:579-607）确实把 Anthropic 的 `tool_choice` 带过了格式边界，但**仅当**它按名字指向一条被映射的 web search 声明。其余全部形态（`auto`／`none`／`any`／指向普通 function tool）仍随 `extensions_for()` 整体丢弃并记 `EXTENSIONS_NOT_CARRIED`（`src/app/pipeline/translation_driver/semantic.py:116-125`）。spec §4 的五行映射表，实现了一行。

**G5. `conversion_losses` 写了没人读。强。**

全仓只有三处写、零处读：`src/app/server/handler.py:124`、`:207`、`:412`。上面 G1 记的 `BLOCK_NOT_CARRIED` 就落在这里。

**G6. `url_citation` 全无踪迹。强。**

`rg -n "url_citation|annotation" src/app/` 除 `from __future__ import annotations` 外零命中。spec §5.3 要它当作 `web_search_tool_result.content` 的**唯一**数据来源。

**G7. `tool_usage.web_search.num_requests` 未采集。强。**

`rg -n "num_requests" src/` 只命中四处**注释**（`openai_responses.py:160`、`:197`、`:591`、`:616`），无任何读取代码。spec §5.3 要求它必须进可观测 facts。

**G8. D6 原生块对未做。强。**

`src/app/pipeline/delivery/assembler.py:314` 与 `openai_responses.py:364-368` 都产出单个 `BlockKind.TEXT`／`{"type": "text"}`。spec §5.3 的块对、§6.3 的推迟成块时点、§5.3 的三分支归因，一项都没有。

**G9. 并发 `web_search_call` 的 `done` 逆序会逆序交付。弱。**

`assembler.py:279-320` 的 `_close` 对所有 item 即到即发，无按 index 排序的缓冲。非本次引入。上游是否真会乱序发 `done`，**未探针**。

**G10. `count_tokens` 腿的缺口比 spec §10 记的窄一点，但仍在。中。**

`src/app/pipeline/subscribers/server_tools.py:246-252`：计数腿现在**会**摊平历史块，只豁免声明拒绝（`_refuse_declarations`）。所以声明仍会发往上游 count 端点并 400，退回本地估算，客户端看不到失败、tokenization 校准停止学习——spec §10 记的这一半仍然成立，但「该腿今天未接订阅者」的表述已经过期。

### 2.2 规格与裁决层

**S1. `web_search_domain_restrictions` 的默认值与取值集，偏离了用户已裁决的 D1。强。这是我认为最该请用户裁决的一条。**

- 用户 2026-08-20 裁决 D1（spec §3.4、§14）：三个取值 `error`（默认）／`drop_unsupported_fields`／`drop_web_search`。
- 实现：`src/app/config/schema.py:29` 是 `Literal["error", "drop_fields"]`——**两个取值，且第二个名字也不同**；`:249` 默认 `"drop_fields"`。
- `schema.py:242-248` 的注释坦白写了这一点：「The default is `drop_fields`, which is *not* what the spec's D1 ruling wrote down」，理由是 190 个真实 Claude Code 子请求**每一个**都带非空 `allowed_domains`，取 `error` 会让 web search 永久不可用。

理由本身很强，但它推翻的是**用户亲自裁决的默认值**，而 spec §3.4 至今仍写着默认 `error`。这属于「已裁决事项被实现单方面改写」，应回到用户手上确认，而不是靠代码注释结案。

**S2. spec 的 DRAFT 状态块自称「实现前必须先关闭这些项」，而实现已经落地。强。**

`hosted-web-search-spec.md:16` 逐条列着未处置项：MJ-1／MJ-2（§12 证据权重表与探针表未随裁决更新、P12 未登记）、MJ-4（§8.3 与 §3.4 组合情形未定义）、MJ-5（§9.3 默认值两解并存）、MJ-7（§5.3 三分支条件不互斥）、MJ-8（派生 id 唯一性范围未声明），以及**全部 minor**。结尾一句是「**实现前必须先关闭这些项。**」

其中 P12 在 `260820-websearch-responses-leg-mapping.md:113` 已有答案（`unavailable` 合法），但 spec 本体未更新。

**S3. spec §8.3 与实现、以及与用户后来的裁决，三方冲突。强。**

§8.3 写「能力门未通过时**必须**剥离声明……**不得** `REJECT` 整个请求」。实现是第三条路：`src/app/pipeline/subscribers/hosted_web_search.py:57-62` 抛 `WebSearchNotExecutable`，由交付侧合成失败结果。这条路来自用户 2026-08-20「去除 drop 策略」的裁决，**比 §8.3 更新**，但 §8.3 一字未改。规格现在把一条已被推翻的做法写成 `必须`。

**S4. §14 待裁决项仍悬着：D2（`max_uses`）、D3（未请求的 `web_search_call`）、D7（`num_requests` 是否写入 wire usage）。强。**

D3 尤其值得点名：spec §8.4 要求覆盖 `spec.md` 的冻结条款，而该覆盖**未获用户裁决**，实现侧也没有对应分支。

**S5. spec §12 关于 cassette 的那条要求未闭合。强。**

`hosted-web-search-spec.md:425` 要求本规格落地后**必须**把该场景挪进 `record_cassette.py` 的 `SCENARIOS`，用产品链重录。今天 `tests/int/recorded/record_cassette.py:42-49` 的 `SCENARIOS` **只有** `anthropic_to_responses_stream` 一项。两份 web search cassette 现在确实在被回放（`tests/int/test_pipeline_app.py`、`tests/e2e/claude/_upstream.py` 都读它们），但**无法用产品链重录**——那句「它们目前没有任何测试在回放」已过期，而「必须挪进 SCENARIOS」仍未做。

**S6. `README.md` 的「权威边界」表仍未收录本规格。强。**

`rg -n "hosted-web-search|web search" docs/agents/anthropic-responses-bridge/README.md` 零命中。这是规格自己在状态块里登记的「索引待补」。

**S7. `implementation.md`（自称「易变实施状态真相源」）对整个 web search 切片零字。强。**

`rg -n "web_search|hosted web search" docs/agents/anthropic-responses-bridge/implementation.md` 零命中。按 `.claude/rules/00-development-workflow.md` 的文档章节，live docs 应及时蒸馏；今天这条切片的全部结论只活在 `docs/tmp/` 与一份 DRAFT 规格里。

### 2.3 文档漂移（同一事实在代码与文档里说法不同）

**D1. 三处代码内注释已被自己的代码推翻。强。**

| 位置 | 写的 | 实际 |
|---|---|---|
| `openai_responses.py:277` | 「There is no capability gate in front of this」 | 能力门已在产：`subscribers/hosted_web_search.py` 全文 + `composition.py:392` 接线 |
| `openai_responses.py:200` | 「the configuration does not exist yet, so what is implemented here is that default」 | 配置项已存在：`schema.py:249` |
| `schema.py:114-115` | 「A model left out that could search has its declaration **removed**, which is reported at INFO」 | 不是剥离，是合成失败结果（`hosted_web_search.py:53-62`） |

**D2. `260820-websearch-responses-leg-mapping.md` 四处自相矛盾或已过期。强。**

| 位置 | 写的 | 实际 |
|---|---|---|
| §2.4（:59-67） | 能力门「不通过时返回 400」 | 抛 `WebSearchNotExecutable` → 合成失败结果，不是 400 |
| §5.3（:176-178） | 「能力门未实现……本片未做」 | 已实现（与同文 §2.4 直接打架） |
| §5.2（:170-174） | 「Anthropic 客户端的 forced tool choice **从未**到达上游」 | `_carry_forced_search`（:579）让指向 web search 的那条到达了上游 |
| §7（:202） | 「1424 passed」 | 今天 1552 passed |

另有结构缺陷：`### 5.6` 排在 `## 8` 之后（:229），编号与位置不一致。

**D3. `260820-client-e2e-group.md` 的每一条路径都已过期。强。**

该文通篇写 `tests/client_e2e/`、`upstream.py`、`harness.py`、`--ignore=tests/client_e2e`（:1、:24-26、:38、:41）。重排后实际是 `tests/e2e/claude/` 与 `_upstream.py`／`_harness.py`，`pyproject.toml:56` 写的是 `--ignore=tests/e2e`。这是该测试组唯一的说明文档。

**D4. `exp/260820-websearch-probe/record.py` 的 docstring 两处过期。强。**

`:3` 给的命令是 `PYTHONPATH=src:tests/integration`（该目录已不存在，现为 `tests/int`）；`:5` 说「today the Responses leg does not emit any `web_search` tool……Move it into a scenario once the mapping exists」——映射已经存在了。

### 2.4 测试组织与流程

**T1. `tests/` 重排本身符合 `test-org.md`。强。**

逐条核对（`docs/.human-controlled/test-org.md`）：

| 要求 | 现状 | 判定 |
|---|---|---|
| `unit/<类似 src 的包结构>/` | 21 个子目录，与 `src/app` 对齐 | 符合 |
| `component/{ghc_client,history}/` | 有二者，另有 `pipeline/` | 符合（「被测目标复杂可再拆子目录」） |
| `int/` | 在 | 符合 |
| `e2e/claude/` | 在 | 符合 |
| `tests/{tui,systemd}/` | 二者都在 | 符合 |
| conftest 按组拆分、无根级 | 5 份（`e2e/claude`、`int`、`systemd`、`tui`、`unit`），**无 `tests/conftest.py`** | 符合 |
| 不设 `tests/upstream/` | 无 | 符合 |
| cassettes 放测试目录内 | `tests/int/cassettes/` 五份 | 符合（`tests/cassettes/` 与 `tests/e2e/claude/cassettes/` 是文档给的**可选位置**，不存在不算缺项） |

`CLAUDE_DATA_DIR` 的问题**已经不存在**：`test-org.md:12` 现写 `CLAUDE_CONFIG_DIR`，全仓 `rg -n "CLAUDE_DATA_DIR"` 零命中。

**T2. 新测试组 `tests/e2e` 的排除未写进项目规则。强。**

`.claude/rules/00-development-workflow.md:21` 只说了 TUI 组被排除、怎么跑；`rg -n "e2e" .claude/rules/00-development-workflow.md` 零命中。`pyproject.toml:54` 的注释同样只解释了 tui，而 `:56` 的 `addopts` 同时 `--ignore` 了两个目录。等于新增了一个默认不跑的测试组，而项目规则里没有它的名字。

**T3. 改名后的 `__pycache__` 残留。弱，仅记账。**

`tests/e2e/claude/__pycache__/` 里仍有 `__init__.cpython-314.pyc`、`harness.cpython-314.pyc`、`upstream.cpython-314.pyc`——三个来源文件都已不存在。无害，但说明改名后没扫干净。

**T4. `docs/tmp/` 的蒸馏与归档未做。强。**

`docs/tmp/` 下日期为 `260820-` 的文档共 **78** 份（`ls docs/tmp | grep -c 260820`）。按 `.claude/rules/00-development-workflow.md` 的文档章节，结论应及时蒸馏进 live docs、临时报告应归档到 `docs/agents/<topic>/archive-<date>/`。当前 live docs（`implementation.md`）对本次切片零字（见 S7）。

### 2.5 提交历史反向扫描（我做了，有结果）

扫描方式：对 2026-08-20 全部提交，比对「conventional 前缀」与「实际改动的文件集」。

**C1. `9fc5f25 docs: say what is known about the guard's placement and what is not` 是 `docs:` 前缀下的实现提交。强。**

`git show --stat 9fc5f25`：10 files changed, 301 insertions(+), 41 deletions(-)，其中包含

- `src/app/pipeline/delivery/assembler.py`：新增「`done` 无 `added` 时补登记」的实际逻辑分支；
- `src/app/pipeline/translation_driver/openai_responses.py`：新增 `_WEB_SEARCH_IGNORED`／`_WEB_SEARCH_DROPPED` 等常量与 `TranslationRefused` 引入；
- `tests/unit/test_translation_driver.py` +92 行、`tests/unit/test_sse_assembly.py` +41 行新测试。

这不是文档提交。其余 `docs:` 前缀触碰 `src/` 的提交（`f219f4d`、`bbbcb37`、`fa1df74`、`1385791`、`2c3ba7b`、`d00fee6`、`587520e`）抽查均为注释／docstring 改动，属实。

**C2. `f3c9de7` 的提交信息由两条独立 subject 拼成。强，但不归我处置。**

`chore: update .gitignore … / feat(config): enhance model mappings …`，改动 `.gitignore`、`refs/.gitignore`、`bundled-config.yaml`。作者是 `Pu Xu <puxu@microsoft.com>`，即用户本人的提交。记录在此供用户自行判断，不建议代为改写。

**C3. 20:46 有两个提交（`c57a15d`、`7086c93`）晚于本次收尾工作。弱。**

可能是并行会话。若本次要做归档或历史操作，基线应重新取。

## 3. 与主会话 13 条清单的对账

| # | 清单条目 | 判定 | 证据／修正 |
|---|---|---|---|
| 1 | D6 原生块对未做 | **成立** | G8。`assembler.py:314`、`openai_responses.py:364-368` |
| 2 | `bash_20250124`／`web_fetch_*` 透传 → 400 | **成立** | G3。`openai_responses.py:149` 只有 `web_search_` 一族 |
| 3 | `tool_choice` 跨协议整体丢弃，只有指向 web search 的被携带 | **成立** | G4。`_carry_forced_search:579`、`semantic.py:116-125`。注意映射文档 §5.2 与这条清单**矛盾**，文档说「从未到达上游」，是错的 |
| 4 | `conversion_losses` 无消费者 | **成立** | G5。`handler.py:124/207/412` 三写零读 |
| 5 | `domain_restrictions: error` 仍返回 400，客户端会重试 3 次 | **成立，但漏了更要紧的一半** | 400 路径确在（`tests/int/test_pipeline_app.py:452-492`）。漏掉的是：**默认值已从用户裁决的 `error` 改成 `drop_fields`，取值集从三个缩到两个**，见 S1 |
| 6 | 并发 `done` 逆序会逆序交付，未探针 | **成立** | G9 |
| 7 | `url_citation` 丢弃 | **成立** | G6，全仓零命中 |
| 8 | `num_requests` 未采集 | **成立** | G7，只在注释里 |
| 9 | `count_tokens` 腿的 server tool 支持 | **成立但需收窄** | G10。历史摊平**已经**覆盖计数腿（`server_tools.py:246-252`），仍缺的是声明处置，上游 count 仍 400 退本地估算 |
| 10 | `test-org.md` 写 `CLAUDE_DATA_DIR` 而 CLI 读 `CLAUDE_CONFIG_DIR` | **不成立（已解决）** | `test-org.md:12` 现写 `CLAUDE_CONFIG_DIR`；全仓 `CLAUDE_DATA_DIR` 零命中 |
| 11 | `.dev/exp/upstream-payloads/` 未落实 | **成立，但优先级低于清单暗示** | `test-org.md:25` 用的是「**可以**放在」，非强制。录制脚本现在 `exp/260820-websearch-probe/record.py`（在 git 跟踪内），`.dev/exp/` 已存在但无 `upstream-payloads/` |
| 12 | 更早历史的反向扫描未做 | **我做了，有结果** | C1（`9fc5f25` 是 `docs:` 前缀下的实现提交）、C2、C3 |
| 13 | 本次 6 份文档未蒸馏、未归档 | **成立，但数量级不对** | T4：`docs/tmp/` 下 `260820-` 共 **78** 份，不是 6 份；且 live doc `implementation.md` 对该切片零字（S7） |

### 3.1 我列了但证据不支持的（给主会话）

- 第 10 条：`CLAUDE_DATA_DIR` 问题已不存在，`test-org.md` 现为 `CLAUDE_CONFIG_DIR`。
- 第 13 条的「6 份」：实际是 78 份 `260820-` 文档。
- 第 9 条的表述偏宽：计数腿的历史摊平已经接上，缺的只剩声明处置那一半。
- 第 11 条的「未落实」偏重：原文是「可以」，不是要求。

## 4. 主会话清单漏掉的（本报告重点）

按我判断的紧要程度排序：

1. **G1**：合成的 `server_tool_use`／`web_search_tool_result` 块回到 Responses 腿时被**静默丢弃**（`BLOCK_NOT_CARRIED` 且无人读），模型看不到上一轮搜索失败过；spec §5.4／§10 要求的摊平未实现；且规格里「今天是 REJECT」描述的是旧链路 `protocols/anthropic_responses.py:409`，生产链路上并非如此。
2. **S1**：`web_search_domain_restrictions` 的默认值被从用户裁决的 `error` 改成 `drop_fields`，三个取值缩成两个且名字也变了，只有代码注释解释，spec §3.4 未改，用户未重新裁决。
3. **S3**：spec §8.3 仍把「必须剥离、不得 REJECT」写成规范，而实现走的是用户后来裁决的第三条路（合成失败结果）——规格把一条已被推翻的做法写成 `必须`。
4. **S2**：spec 状态块自称「实现前必须先关闭」的 MJ-1／2／4／5／7／8 与全部 minor 仍未关闭，实现已经落地。
5. **D1**：三处代码内注释被自己的代码推翻（「没有能力门」「配置还不存在」「未通过时剥离声明」）。
6. **D2**：映射文档 §2.4 与 §5.3 自相矛盾（一处说门返回 400、一处说门未实现），§5.2 关于 forced choice 的断言是错的，§7 的测试数过期，§5.6 编号错位。
7. **S7 / T4**：live doc `implementation.md` 对整个 web search 切片零字；`docs/tmp/` 下 78 份 `260820-` 文档未蒸馏未归档。
8. **S5**：spec §12 要求的「把 web search 场景挪进 `record_cassette.py` 的 `SCENARIOS`」未做，两份 cassette 今天能回放但**不能用产品链重录**。
9. **S6**：`README.md` 权威边界表仍未收录 `hosted-web-search-spec.md`（规格自己登记的「索引待补」）。
10. **T2**：新测试组 `tests/e2e` 被 `--ignore` 排除出默认 sweep，但 `.claude/rules/00-development-workflow.md` 里没有它的名字（tui 有）。
11. **D3**：`260820-client-e2e-group.md` 作为该组唯一说明文档，全部路径已过期（`tests/client_e2e/`、`upstream.py`、`harness.py`、`--ignore=tests/client_e2e`）。
12. **C1**：`9fc5f25` 用 `docs:` 前缀提交了 301 行的实现与新测试——反向扫描的第一个真结果。
13. **G2**：三个 `web_search_call` 专有事件在生产链路上被静默忽略（spec §6.2 要求记录 provenance）；在旧链路上会变成交付错误，但那条链路当前不可达。
14. **S4**：§14 的 D2／D3／D7 仍未裁决，其中 D3 覆盖了 `spec.md` 的冻结条款却没有用户点头。
15. **D4**：`exp/260820-websearch-probe/record.py` 的 docstring 命令路径与前提都已过期。
16. **T3**：`tests/e2e/claude/__pycache__/` 里三个改名前的 `.pyc` 残留。

## 5. 一条方法性观察

本次枚举里，**六条**（G1、D1×3、D2×2、S3）属于同一族失败：*事实变了，而描述那个事实的第二处文本没有跟着变*。它们都不会有任何东西报错——测试全绿，1552 passed。代码注释与 tmp 文档在同一次切片内被反复改写，最后留下的版本与代码不同步，而下一个读者没有办法分辨哪一处是权威。

这不是「文档债」这种轻量说法能概括的：G1 之所以到今天才被看见，正是因为规格里写着「今天是 REJECT」，读起来像是一个已知且响亮的行为，而真实行为是静默丢弃。**一处过期的描述把一个静默缺陷伪装成了一个已知的响亮缺陷。**

# auto mode 拦截：`2b28d07..HEAD` 三次未评审改动的独立复评

- 日期：2026-08-23
- 评审对象：`git diff 2b28d07..4087a86` 在四个文件上的差异 —— `src/app/config/schema.py`、`src/app/pipeline/auto_mode_classifier.py`、`src/app/pipeline/driver.py`、`tests/unit/pipeline/test_auto_mode_classifier.py`
- 涉及提交：`d6edd1a`（改名 + 压成标量）、`2ba08e2`（改回结构化 section）、`4087a86`（`match_transcript_open` 降为常量）
- 范围外未看：`f5b5e3a`（同伴归档 Gemini 实现）
- 结论：**needs-fix（仅 minor / nit，无 blocker、无 major）**。前两轮的 8 条已修缺陷**全部仍修着**，没有一条在三次重写中丢失。

## 0. 我核对的基线与两个状态事实

- 代码基线是 `4087a86`（HEAD），工作树在这四个文件上是干净的。
- **`docs/.human-controlled/config.example.yaml` 的那一节尚未提交**（`git status` 显示 `M`）。也就是说 HEAD 的提交态里，这份「最高权威」还没有 `intercept_auto_mode_classifier` 这一节，我比对用的是**工作树版本**。这只是一个供你知情的状态事实，不是待办：那个文件归你写，归属与提交时机不该由我催。
- 我复跑了 `uv run pytest tests/unit/pipeline/test_auto_mode_classifier.py --no-cov -q` → `42 passed`。任务里已做过的 ruff / pyright / 全量回归 / 七条变异验证我没有重复。

## 1. 回归核对：前两轮 8 条已修缺陷在当前 HEAD 上的状态

一句话结论：**8 条全部仍修着，零回归。**

| # | 缺陷 | 结论 | 证据 |
|---|---|---|---|
| 1 | B-01 / major-1：severity 协议判别读两处 | **仍修着** | `src/app/pipeline/auto_mode_classifier.py:149-158`。`_protocol_of` 先读 `stop_sequences`（:149-151），命不中再遍历 system 块找 `_SEVERITY_MARKER`（:152-157）。两条信号都在，且 `_SEVERITY_MARKER = "<severity>"` 定义在 :32。回归防线在 `tests/unit/pipeline/test_auto_mode_classifier.py:408-419`（`classify` 级）与 `:549-570`（经 `handle()` 的端到端，含 `QRl` 的 `stop_reason` 闸门）。 |
| 2 | A-04 / major-2：block 分值 > 100 | **仍修着** | `auto_mode_classifier.py:39` `_SEVERITY_BLOCK = 101`，:34-38 的注释仍然写着 `101` 的理由（客户端 `score > threshold` 严格大于、`nLl()` 接受 `t == 100`）。断言在 `test_auto_mode_classifier.py:421-432`，钉的是 `score > 100` 而不是 `score == 101`，形状而非字面量，这是对的。 |
| 3 | A-03 / major-3：`<block>` 过滤大小写不敏感 | **仍修着** | `auto_mode_classifier.py:44` `_DECISION_TAG = re.compile(r"<\s*block\s*>", re.IGNORECASE)`，使用点在 :209。附带一句独立核对：我们的过滤比客户端的 `/<block>(yes|no)\b/gi` **更宽**（不要求紧跟 `yes\|no`，且容忍 `< block >`），方向是过滤过度而非过滤不足，安全。参数化用例在 `test_auto_mode_classifier.py:301-316`，三种拼法都在。 |
| 4 | B-06 / major-4：短路以 `inbound_format is WireFormat.ANTHROPIC_MESSAGES` 为前置 | **仍修着** | `src/app/pipeline/driver.py:123`。`classify()` 的调用（:124-126）整个包在这个 `if` 里。回归防线 `test_auto_mode_classifier.py:572-591`，走 `handle()` 并断言 `synthesized is False` + `ExplodingProvider` 被真的调用过。 |
| 5 | B-05：两条标记都不得单独成立 | **仍修着** | `auto_mode_classifier.py:174` `if not _has_classifier_shape(payload): return None` 排在两条标记判断（:177、:179）**之前**；`_has_classifier_shape` 在 :114-137，三项门槛齐全（无 `tools` :127、非流式 :129、无 assistant 轮 :134-137）。`TestItDoesNotHijackOrdinaryRequests`（`test_auto_mode_classifier.py:356-404`）五个用例全在。 |
| 6 | A-02 / minor-3：JS parser 转写用 ECMAScript 语义 | **仍修着** | `test_auto_mode_classifier.py:104` `_ES_SPACE` 显式字符类、:107-108 `re.IGNORECASE \| re.ASCII`、:110 `[0-9]` 而非 `\d`。而且 `TestTheParserOracleMatchesEcmascript`（:435-463）四个反例用例原封不动保留，这一条是**自带鉴别力的**：改回 Python 默认语义会直接打红。 |
| 7 | C-01 / minor-5：短路路径发布 `request.succeeded` | **仍修着** | `driver.py:132-134`：`outcome.events.append(EVENT_REQUEST_SUCCEEDED)` 后遍历订阅者并 `await`。位置仍在 `return HandledRequest(...)` 之前。 |
| 8 | major-5：删掉「衰减只会漏判、绝不答错」的一般性承诺 | **仍修着** | 全仓 grep（`src` / `tests` / `docs` / `.dev/docs/auto-mode-classifier` / `.dev/human-controlled-docs-candidates`）只剩两处**反向表述**：`auto_mode_classifier.py:166`（"That safe direction covers recognition, and only recognition… An earlier version of this docstring said a decayed predicate could never produce a wrong answer"）与 `spec.md:58`。`status.md:92` 的「门槛过严只会漏判」是对**结构门槛**这一件事的有界陈述，不是被证伪的那句一般性承诺，保留是对的。旧的 `schema.py:93-94` 那段随 section 重写一并消失。 |

### 顺带做的一次反向验证（不在 8 条里，但值得记）

第 1 条的修法引入了一个**反方向**风险：`_protocol_of` 只要在任一 system 块里看到 `<severity>` 就判 severity，那么如果 block 模式的 110k 字符 prompt 本身提到这个标签，就会把 block 运行误判成 severity。我实测查了 2.1.241：

- `SVi()`（`app.pretty.js:367602-367742`）全文只出现 4 次 `severity`，全部是英文单词（"scope, severity, or destructiveness"、"high-severity" 等），**没有一次是 `<severity>` 标签形态**。
- block 模式的 `## Output Format` 段（`app.pretty.js:367728` 起）只有 `<block>` / `<category>` / `<reason>`，无 `<severity>`。
- `OGw()`（`:368332-368337`）只替换尾部 `\n## Output Format\n[\s\S]*$`，`$Gw`（`:368814`）才是唯一带 `<severity>` 字面量的串。

所以在 2.1.241 上，这个判别在两个方向都成立。这是**足以据此行动**的强度：判据是源码而非样本推断，但只覆盖 2.1.241 一个版本，未查 2.1.207 / 2.1.226。

## 2. 新发现

### minor-1 — `test_the_transcript_wrapper_is_not_a_setting` 对键名零鉴别力

- 位置：`tests/unit/pipeline/test_auto_mode_classifier.py:226-232`
- 置信度：**高**（实测）

这个测法是**可靠的**（`Section` 在 `src/app/config/schema.py:56` 设了 `extra="forbid"`，`ValidationError` 一定抛），但它**证明不了 docstring 声称的那件事**。实测：

```
match_transcript_open      -> ValidationError
zzz_definitely_not_a_key   -> ValidationError
transcript_open            -> ValidationError
```

任意不存在的键名都抛。docstring 写「Pinned as a test because "we removed a key" is exactly the kind of decision a later refactor re-adds without noticing」——但如果后来的重构把旋钮**以别的拼法**加回来（尤其是它在 `2b28d07` 时的原名 `transcript_open`），这个测试照样绿。它实际钉住的只有两件事：`extra="forbid"` 还开着，以及 `match_transcript_open` 这一个拼法不是字段。

建议改成钉**语义**而不是钉一个拼法，例如断言 `InterceptAutoModeClassifierConfig.model_fields.keys() == {"decision", "block_reason_str", "match_system_prompt_prefix"}`——这同时把「三个键、与人写文档逐字一致」也钉住了，一条顶两条，且再加一个知情的 key 会被迫改测试（那正是想要的摩擦）。

### minor-2 — 候选文档声称「取值逐字一致」，实测不成立

- 位置：`.dev/human-controlled-docs-candidates/auto-mode-classifier.md:53`（「实现已按它落地，键名与取值逐字一致」）对 `src/app/config/schema.py:325`
- 置信度：**高**（实测）

实测比对：

| 键 | 用户亲笔（`config.example.yaml`，工作树） | schema 默认值 |
|---|---|---|
| `decision` | `allow` | `passthrough` |
| `match_system_prompt_prefix` | `You are a security monitor for autonomous AI coding agents.` | 同 |
| `block_reason_str` | `Blocked by proxy, without a model review.` | `Blocked by proxy **configuration**, without a model review.` |

`decision` 的差异是设计（例子是作者调优值，默认必须惰性），文件抬头「本文件中的是作者调优的值」也说清了这一点。但 `block_reason_str` 差了一个词，而候选文档那句「取值逐字一致」把这事说成了对的。这是一条**被自己的文档证伪的断言**，属于「归因写下前先核」的那一类。

两条出路，我倾向前者：**把 schema 默认值改成用户写的那句**（`docs/.human-controlled/` 是最高权威，而这里没有任何保留另一种措辞的理由），或者改那句文档并注明默认值有意不同。这条影响面很小——默认 `passthrough` 时这个字符串根本不会被发出——所以是 minor 而不是 major。这条严格说在四文件范围之外，但它是对范围内文件的断言，故一并报。

### minor-3 — `match_transcript_open` 降为常量的论证：一条腿站不住，且丢了一个没被提到的能力

- 位置：`src/app/pipeline/auto_mode_classifier.py:24-27`、`src/app/config/schema.py:326-330`、`.dev/docs/auto-mode-classifier/spec.md:149-159`
- 置信度：**中高**（推理为主，能力丢失一项是实测）

论证**整体成立**，我不反对这个裁决。但两点：

1. **「配错无声」这条腿不具鉴别力。** 注释说 M2 该钉死是因为「值必须带尾部 `\n`，配错只表现为命中数为零」。可 `match_system_prompt_prefix` 配错**同样**只表现为命中数为零——把 prompt 首行抄错一个字符，失效形态一模一样，而它是配置项。真正把两者区分开的只有**易变性不对等**那一条（散文会被润色 vs 结构标签稳定）。留着这条不具鉴别力的理由，会让后来人以为「配错无声」是钉死的充分理由，从而对 M1 得出相反的结论。建议把这条降级为附注或删掉。

2. **作者没提到的反面：M2 丢掉了它唯一的关闭开关。** `2b28d07` 时 `transcript_open: ""` 可以单独关掉 M2（被删掉的 `test_the_predicates_are_configurable` 用的正是这一手），而 `_matches_system_prompt` 的 `if not prefix: return False`（`auto_mode_classifier.py:68-69`）至今让 M1 保留着同样的关闭能力。现在两条标记的能力是**不对称**的：M1 可改可关，M2 既不可改也不可关。如果 M2 哪天开始误伤——即某个合法请求同时越过结构门槛**并且**带完整的 `<transcript>\n` … `</transcript>\n` 包裹——运维手上没有任何缩窄识别的旋钮，只能 `decision: passthrough` 把整个特性关掉。

   考虑到 B-05/A-01 找到的正是「合法请求踩中裸标记」这一类失败，丢掉 per-marker 的关闭能力不是零成本。但我**不主张现在加回来**：结构门槛已经把那一类挡住并有五个用例钉着，兜底手段（`passthrough`）存在，且再加一个键会把刚清掉的配置面又铺开。这条应该进 `deferred.md`，措辞类似「M2 误伤时无 per-marker 关闭手段，届时的动作是改代码或整体 passthrough」——这样它是**被知情地推迟**，而不是被静默裁掉。

### nit-1 — `test_either_marker_survives_the_other_being_reworded` 有一半是更弱的重复

- 位置：`tests/unit/pipeline/test_auto_mode_classifier.py:199-208`
- 置信度：高

`prompt_reworded` 这一半（:204-205）与 `test_the_transcript_wrapper_is_recognised_on_its_own`（:172-177）构造的是同一个请求，而后者还多断言了 `matched == "transcript-open"`，严格更强。真正新增的只有 `wrapper_reworded` 那一半（:207-208，M1 单独成立）。而那一半只断言 `is not None`，没断言 `matched == "system-prompt"`。

建议：两半都补上 `matched` 断言，或者把重复的上半删掉。不改也不算错，只是这个测试的名字承诺的比它断言的多。

### nit-2 — `schema.py` 的三处空白/注释瑕疵

- 位置：`src/app/config/schema.py:332-335`（`match_system_prompt_prefix` 与 `class FixAnthropicRequestHook` 之间**三个**空行，全文件其余处都是两个）、`src/app/config/schema.py:316`（`decision` 正上方一个后面什么都没有的空 `#` 行）
- 置信度：高（`cat -A` 实测）

ruff 放行是因为 E303 在 ruff 里属 preview 规则、未启用；这不是 ruff 该管的事，是 `2ba08e2` 手写 section 时留下的。`#` 空行在本文件里是**段落分隔符**（`block_reason_str` 上方那三段之间就是这么用的），但 :316 那个后面直接就是字段，分隔了个寂寞。两处都只需删行。

**不建议用 `ruff format` 处理**——项目已裁决禁用，且它会顺手改掉别的东西。

### nit-3 — `driver.py:219` 未换行，与 12 行前的同类调用风格不一致

- 位置：`src/app/pipeline/driver.py:219`（121 字符）对 `src/app/pipeline/driver.py:124-126`
- 置信度：高

`E501` 在 `pyproject.toml:73` 被 ignore，所以合法。只是同一个特性、同一条配置路径，上面那处拆了三行、下面这处没拆。取一致即可，随手事。

### nit-4 — `_matches_transcript_wrapper` 留了配置时代的参数、死分支和过时理由

- 位置：`src/app/pipeline/auto_mode_classifier.py:79-87`
- 置信度：高

`4087a86` 之后，这个函数唯一的调用点（:179）传的是非空常量 `_TRANSCRIPT_OPEN`，于是：

- `:86-87` 的 `if not opener: return False` **不可达**。
- docstring `:84` 那句「The closer is derived from the opener rather than configured separately: they are one wrapper, and a configuration that let them disagree would only ever be a mistake」在辩论一个**已经不存在的配置选项**。

保留 `opener: str` 参数本身我认为是合理的（函数是纯的、可单测、常量在模块顶部命名），不必内联。但那个空值守卫和那句理由应该走，否则下一个读者会以为这里还有配置面。对照：`_matches_system_prompt:68-69` 的同款守卫是**活的**（`match_system_prompt_prefix: ""` 是合法配置），两者现在看起来一样但性质不同，这本身就是误导。

## 3. 查了、没找到问题的方向

以下每一条我都实际查过并给出查的范围，不是「看起来没问题」：

1. **配置契约与人写文档逐字一致。** 用 `yaml.safe_load` 读 `docs/.human-controlled/config.example.yaml` 的工作树版本，取出 `hook_fix_anthropic_request.intercept_auto_mode_classifier`，与 `InterceptAutoModeClassifierConfig.model_fields` 做集合比对：**两边都恰好是 `{decision, block_reason_str, match_system_prompt_prefix}`，无多余键、无缺失键**。并且把**整份** `config.example.yaml` 喂给 `ProxyConfig.model_validate` → 通过（`extra="forbid"` 之下这意味着全文件没有任何孤儿键）。值的差异见 minor-2。

2. **`test_the_prompt_marker_is_configurable` 是否变成恒真断言。** 不是，仍有鉴别力。它的两个断言只差 `config` 一处输入而结论相反（`:218` 断 `None`、`:224` 断 `not None`），请求体两条标记都被改词，唯一能让第二个断言成立的路径就是 `classify` 真的读了 `config.match_system_prompt_prefix`。任何「忽略该字段、写死 MONITOR_PROMPT」的实现都会让 `:224` 打红。被删掉的旧测试额外证明的能力（`transcript_open: ""` 关掉 M2）随该键一起消失，没有遗留未覆盖的行为。

3. **`decision` 从 `false` 中途态残留。** 全仓 `rg "decision\s*(==|is)\s*(False|false)|AutoModeDecision"` 于 `src` + `tests`：只有 `schema.py:29`（`Literal["passthrough","allow","block"]`）、`schema.py:317`（默认值）和测试里四处类型标注。`classify` 的开关是 `config.decision == "passthrough"`（`auto_mode_classifier.py:172`），无 `False` 分支、无死代码。注意 `schema.py:20-21` 的 `AssistantMessageLayout` / `ContentBlockStartCompat` **确实**用 `Literal[False, …]`，那是另外两个设置的既有形态，不是这次的残留；`schema.py:28` 的注释还专门解释了为什么这个键不跟它们走同一条路。

4. **旧配置路径的残留引用。** `rg "auto_mode_classifier|AutoModeClassifierConfig|system_prompt_prefix|transcript_open"` 于 `src` + `tests`：零处指向 `inbound.auto_mode_classifier` 或旧类名。`InboundConfig` 只剩 `anthropic_count_tokens`。

5. **热重载语义没被这次搬家改变。** `NOT_HOT_RELOADABLE`（`schema.py:37-52`）里既没有旧路径 `inbound.auto_mode_classifier`，也没有新路径 `hook_fix_anthropic_request*`；两个路径都挂在同一个 `chain.config` 对象上，读取方式（`driver.py:124`、`:219`）也都是每次请求现读。搬家前后都可热改。

6. **schema 注释里新增的客户端事实断言。** `schema.py:317` 上方新写的「the client still presents each answer as a model's — it renders an allow as `Allowed by fast classifier` and counts it in auto mode's telemetry」是这三次改动里**新加**的、未经评审的事实主张。我去 `app.pretty.js:368465` 核了：`Ne === false` 分支确实返回 `{ shouldBlock: false, reason: "Allowed by fast classifier", … }` 并调 `lvr("success", …)` 上报。断言属实。

7. **交付路径与 `synthesized` 契约。** 这三次改动没有碰 `anthropic_messages_synthetic_reply.py` / `delivery_policy.py` / `reply.py`，`git diff --stat` 只有四个文件。上一轮已核过的短路点位置、`attempt_count == 0` 的消费点等结论不受这三次改动影响，我没有重查。

8. **文档同步。** `spec.md:95-160` §5 已完整改写成三键结构化形态，包含「M2 是常量」一节与 `101` 的理由（§5.1）；`status.md:21-52` 记了三次改动各自做了什么。`.dev/human-controlled-docs-candidates/auto-mode-classifier.md:35-53` 已作废并指向用户文档。除 minor-2 那句外，文档与代码一致。

## 4. 处置建议的优先级

我的主观排序（前两条值得现在做，后面的随手）：

1. minor-1 —— 把 `test_the_transcript_wrapper_is_not_a_setting` 改成钉字段集合。收益是它同时替 §3.1 那条人工比对上岗，以后 schema 与人写文档漂移会被测试抓到，而不是靠下一个评审者手动 `yaml.safe_load`。
2. minor-3 第 2 点 —— 把「M2 无 per-marker 关闭手段」记进 `deferred.md`。这条不是要改代码，是**不要让它被静默裁掉**。
3. minor-2 —— 对齐 `block_reason_str` 默认值，或改掉那句「取值逐字一致」。二选一，我倾向对齐。
4. minor-3 第 1 点 + nit-4 —— 清掉两处已经不成立的理由文字与一个死分支。
5. nit-1 / nit-2 / nit-3 —— 随手。

以上没有一条阻断这三次改动进入下一个 squash 候选。

## 5. 我的判据与本次评审的盲区

- 判据来源：四文件的实际字节（HEAD `4087a86`）、`docs/.human-controlled/config.example.yaml` 的**工作树版本**、`/home/xp/.claude/refs/claude-code-2.1.241/app.pretty.js` 的原文行、以及一次实际执行的 pydantic 探针与一次 pytest 运行。凡写「实测」的都跑过命令；凡写「推理」的都没有。
- **盲区一**：客户端事实我只核了 2.1.241。2.1.207 / 2.1.226 的 `SVi()` 里是否也从不出现 `<severity>` 标签形态，我没查。
- **盲区二**：我没有重跑全量回归、ruff、pyright 与七条变异验证，直接采信了任务给出的结论。如果那七条变异中有任何一条实际上是在旧版本代码上做的，本报告第 1 节的「仍修着」仍然成立（那是我自己读代码得出的），但「有测试接得住」这半句就要打折。
- **盲区三**：我没有验证短路路径在**流式**入站下的行为，也没有碰 minor-4（虚构上游腿）那条已知未闭合项——两者都不在这三次改动的差异里。

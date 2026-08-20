---
name: project-review-principles
description: "本项目的定期复查清单：拿几条已经付过代价的原则去对当前代码，判断有没有被违背、能不能据此消掉一处怪味。定期复查、用户说「复查一下」「有没有什么该清理的」「这块是不是又走歪了」、一大块工作合并之后、或者接手别人做了一半的模块时用。也用于反向问题——某条原则是不是已经不成立了、该不该退役。**不是 always-on 规则**：它不在每次改动时触发，也不产生阻断；它产出的是判断和候选工作项。不管日常提交与暂存纪律（→ `git-preference:coordinating-a-shared-git-worktree`）、绿灯有没有分辨力（→ `trusting-a-green-result`）、按命题选 ground truth 的一般方法（→ `verifying-authoritative-claims`）、会话收尾（→ `closing-a-development-session`）。"
---

# 项目复查原则

## 这是什么

一份**已经付过代价**的清单，用来做定期复查。每条都对应本项目真实发生过、且不止一次的缺陷形态。

**不是 always-on 规则。** 它不该在每次改动时浮现——那样会退化成噪音，而它要抓的东西按定义是「写的时候看不出来、攒一段时间才显形」的。

**不是门禁。** 项目规矩明确禁止把结果检查升级成阻断装置。产物只有三种：判定「没问题」、判定「违背了，这是修法」、判定「违背了但不值得现在修，记入 `deferred.md`」。**判断权留在人手里。**

**命令给候选，不给结论。** 下面每条检索都会打出需要人看一眼的位置，其中一部分看完就排除了。实证：写这份清单时，「重复判定热点」那条命令打出 `translation_driver/responses.py:65-67` 有一处 usage 原样拷贝，看进去发现它在 `from_anthropic_response` 里——读的是 Anthropic 载荷，键本来就对，拷贝正确。**命令没错，它就该把这个位置交出来。**

**条目会退役。** 每条都写明什么结构事实一旦成立就该删。实现基础没了却还留着，比没有这条更糟。

## 一次复查怎么走

对每条原则：跑命令拿**当前**事实（别凭上次记忆）→ 对照「什么算违背」→ 违背了就分「本次能收口」还是「要单独切片」，后者写进 `.dev/docs/<topic>/deferred.md` 并说明不做的理由 → 顺手用条目自带的退役判据判一次它还该不该留着。

违背项与处置要落到某处（提交信息、`deferred.md`、或告知用户）；没违背的条目**不必留痕**。

---

## `one-reply-fact-one-answer-across-both-reply-modes`

**一个描述「上游回复了什么」的事实，必须由同一段代码判定，无论这次回复走哪种处理模式。**

**范围限定在当前 CLI 所用的 `pipeline_app`**，它对正常上游回复有两种处理模式：

- **live upstream 上的 block-level delivery**（对应请求的 `stream=true`）——经 `assembler.py` 的 `Terminal`。注意术语：下游交付单位是完整的 Anthropic content block，SSE 只是信封，别把它写成语义上的「流式交付」。
- **whole-body 回复**——`pipeline_app.py:313` 先 `response_payload()`（内部走 translator registry 做响应翻译），`:316` 再由 `handler.reply_summary()` 汇总。**顺序是先翻译后汇总**，`reply_summary` 调用的是 `terminal_from_anthropic`，不会下行到 `translation_driver/responses.py`。

仓库里还有一条 legacy 交付链（`src/app/routes/anthropic.py`、`src/app/delivery/`），**本条不覆盖它**——它不在当前 CLI 的正常回复路径上。若哪天它重新上线，这条原则的事实清单与命令都要先扩，不能默认适用。

### 怎么查

```bash
# A 事实清单（内省，不依赖行窗口）
PYTHONPATH=src uv run python -c "
import dataclasses
from app.pipeline.delivery.assembler import Terminal
print(' '.join(f.name for f in dataclasses.fields(Terminal)))"

# B 生产者：含 record() 的调用点与它内部的 append，这是 tools/thinking 唯一可见的地方
rg -n "Terminal\(|\.record\(|tools\.append|thinking\.append|(stop_reason|usage|dialect|seen)\s*=" \
   src/app/pipeline/delivery/assembler.py src/app/pipeline/translation_driver/responses.py src/app/server/handler.py

# C 消费者：两条 absorb 调用点都必须出现（一条 whole-body、一条 block-level）
rg -n "absorb\(|\.reply\b" src/app/server/pipeline_app.py src/app/pipeline/delivery/stream.py

# D 重复判定热点：同一语义在两个文件里各判一次
rg -n "stop_reason|usage" src/app/pipeline/delivery/assembler.py src/app/pipeline/translation_driver/responses.py | rg "=\s|def |if "
```

### 什么算违背

- **某字段只在一种模式下被写。** 另一模式的消费者拿到**类默认值**，而默认值是个断言——它会声称一件没人说过的事。
- **同一语义有两处独立表达式。** 「什么算 `tool_use` 块」「怎么区分可读推理与密封签名」「缓存要不要从 `input_tokens` 里减掉」出现两份，就是漂移的开始：修好一份时另一份不会有人动。
- **分派条件写了两遍。** 「这是哪种上游」若两处各判一次，两种模式可以对同一请求得出不同答案。
- **某条路径没有读取器却仍产出记录。** 空记录与「没读」是两个事实，混同会让下游把「读不出来」当成「回复里没有」。

### 修法方向

分类逻辑放在**记录自身**（`Terminal.record`，当前是 `tools`/`thinking` 的共同分类点，被两个 assembler 与 whole-body 构造共三处调用）；whole-body 侧用同形状构造函数产出同一种记录；分派**派生自单一函数**（现状：`assembler_for` 基于 `dialect_for` 的结果分派，`handler.py`）；没有读取器时返回 `None` 而不是空记录。

回归测试应**断言两种模式彼此相等**，而不是各自对字面量。⚠️ 要确认这类判据真有分辨力——尤其两处修法互相冗余、逐个变异都不红时——**此时加载 `trusting-a-green-result`**，那才是它的地盘，本条只负责指出这个不变量跨两种模式。

### 凭什么在这里

2026-08-20 一场之内同一形状发作三次，每次都由评审或用户事后发现：`tools`/`thinking` 两处各自分类；usage 只在 block-level 那侧换算，导致同一路由因 `stream` 开关给出两套契约、且 whole-body 那套破坏了下游 schema；`Terminal.stop_reason` 的类默认值在「读不出内容」的路径上伪造出 `end_turn`。详见 `.dev/docs/tui/archive-request-log/` 与 `archive-token-accounting/`。

**权重：足以作为暂定复查项执行**——依据是同一机制在三个独立代码点造成了具名缺陷，不是单次印象。**不足以支撑「上面这组命令有召回力」**：它们从未在一次真实复查里被检验过，首次复查应当把「有没有该抓到却没抓到的位置」一并记下来。

### 什么时候退役

两种处理模式在结构上合并成一条、重复推导不再可能产生时；或 `Terminal` 的字段不再进入任何对外契约、只剩单一具名消费者时。**注意分辨**：模式变成三种不是退役条件，是这条更重要了；legacy 链重新上线同样不是。

---

## `assertions-about-copilot-wire-need-a-recorded-counterpart`

**当一条断言的期望值在声称「Copilot 实际会发什么／会接受什么」时，本仓必须有对应的录制证据；期望值若由本项目自己的合同与逻辑拥有，手写输入是恰当的。**

判别的轴是**期望值归谁所有**，不是「换个上游还成立吗」——后者会误判：路由分支的结果可能随上游能力变化，但它仍由本项目的规范与逻辑裁决，不因此需要录制。

按命题选 ground truth 的一般方法在 `verifying-authoritative-claims`，本条不重写它。**这里只管本仓的复查问题**：哪些断言在声称外部 wire，它们有没有落到 `tests/cassettes/` + `tests/integration/recorded/`。项目对录制基建本身的约定（为什么拒绝 vcrpy、chunk 边界为何要保留、`from_history.py` 的适用边界）是 always-on 的，在 `CLAUDE.md`，不在这里。

### 怎么查

```bash
# 手写上游结构的候选点，按文件计数排序便于分诊
rg -c --type py 'input_tokens_details|output_tokens_details|"type":\s*"response\.|"output":\s*\[|"content_block":' tests/ | sort -t: -k2 -rn

# 从 cassette 取真实终结事实：按 SSE 帧解 data: 行，不要用正则啃 JSON
python - <<'PY'
import json, pathlib
def terminal_usage(name):
    p = pathlib.Path("tests/cassettes") / name
    for it in json.loads(p.read_text())["interactions"]:
        blob = "".join(c.get("text", "") for c in (it["response"].get("chunks") or []))
        for line in blob.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if event.get("type") == "response.completed":
                return event["response"]["usage"]
for n in ("history_responses_stream.json", "responses_web_search_stream.json", "anthropic_to_responses_stream.json"):
    print(f"{n:38} {terminal_usage(n)}")
PY
```

第一条给的是**候选点**，不是完备清单——它按结构键匹配，换一种写法就漏。对每个候选点问那句话：这里的期望值是在声称外部 wire，还是本方合同？

### 什么算违背

- 一个**声称外部 wire** 的期望值，只由手写 fixture 支撑，仓库里没有对应的录制断言。
- 为确认一件 cassette 已能回答的事，**反复**去打真实上游。
- 期望值靠印象写，而不是从录制里读出来。

### 凭什么在这里

同一场里这条线上错了三次：反复实测真实上游（用户裁定「这种任务根本不应该反复实测上游，mock upstream 是最佳测试方案」）；手写了一份 usage fixture，而它的字段结构恰恰是需要被录制的东西——录制证明 `input_tokens` **含**缓存、`cache_write_tokens` 可能整键缺席；以及用纯文本 grep 搜 cassette 搜不到（chunk 存成 `{"text": ...}`），一度误判评审说错了。

同源小实证：给那条录制断言写期望值时，输入侧三项从录制读出、一次命中，唯一凭印象写的 `output_tokens` 错了。**再一次**：本节上一版给的正则提取脚本会在 `input_tokens_details` 处提前截断，输出不是合法 JSON，而我看了输出没发现——现在这版按 SSE 帧解析。

**权重：足以作为暂定复查项执行**——三次命中都有具名后果。**判别轴（期望值归属）本身尚未在真实复查中用过**，首次使用时应留意有没有它判不了的情形。

### 什么时候退役

本项目不再对外部 wire 作这类断言时；或该职责整体迁出本仓时。**cassette 基建被换成另一种录制格式不是退役条件**——那只要更新上面的命令；方法与复查问题都还在。

---

## 这份清单怎么长、怎么退

### 进来的门槛（三条都要满足）

1. **发作过不止一次**，或一次但代价足以让人记住。一次性教训写进记忆或归档文档，不占这里的位置。
2. **复查问题依附本项目结构**。通用方法学去找对应的 user 级 skill 并**引用**它，不要在这里复制一份——否则同一件事会有两个家，各自演化。
3. **能用可跑的检索命令表达判据**，且命令要**实测过**。写不出「怎么查」的条目，复查时会退化成凭感觉。

### 退出的判据

只由**可证伪的结构事实**触发：

- 条目自带的退役条件成立（重复推导已因结构合并而不可能产生、职责已迁到具名现役机制、断言对象已消失）。
- 该原则已被另一条现存条目**完整覆盖**，且做过召回面对账。

复查历史本身**不是**退出条件。「连续两次没查出违背」只能作为**发起退役复核的弱信号**——两次干净的观测只支持「这两次没发现当前违背」，推不出「防线已内化进结构」，在命令本身可能漏检时尤其推不出。不要为此建立评分、投票、注册表或状态机。

删除时把条目连同实证移进对应话题的 `.dev/docs/<topic>/archive-*/`，正文不留残句。

### 当前状态

两条，2026-08-20 立，**都还没被真实复查检验过**。第一次复查时要留意：命令是否漏掉了该抓的位置、判别轴是否有判不了的情形。命令不好用就改命令，**不要改判据去迁就命令**。

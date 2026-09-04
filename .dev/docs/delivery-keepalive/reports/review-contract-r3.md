# 复评（r3）：最后一轮确认

- 评审对象：`6a55adf`（保活到期结算）与 `fcbda79`（文档处置），基线 `3160285`
- 前两轮：`review-contract.md`（F1–F11）、`review-contract-r2.md`（R2-0～R2-10）
- 工作树 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/delivery-keepalive`，HEAD `fcbda79`，`git status` 干净；全程只读，探针在 `/tmp/probe_keepalive/`
- 按要求只确认两件事，不重复评审 `6a55adf` 的控制流

**结论：这份 spec 可以固定为规范。** 两个待确认项都成立，另有两条上一轮列过的低成本项未落实（次要，不阻断），以及一条新的引用范围精度问题（次要）。

---

## 1. 五处文档修改是否落实，有无新的不实陈述

| 项 | 落实 | 独立复核 |
|---|---|---|
| **R2-1** 删掉「降到 300 以下是现成的调整手段」 | **是** | spec.md:60-62。原句已删；新增一段明确写出它是终止器、按 §4 分类它决定何时放弃上游、调低换来的是「代理主动掐断」而不是「客户端不再超时」，并以「**本规范不提议这种覆盖**」收口 |
| **F10** 恢复「为什么是注释帧而不是 `ping` 事件」 | **是** | spec.md:29，内容与被删版本一致，含「若将来发现某个客户端只认事件不认注释，这条要重新裁决」 |
| **F6** 补另一半死旋钮 | **是** | spec.md:83 与 `deferred.md` D-3。`rg -n "upstream_keepalive|upstream_h2_ping" src/` → 只有 `settings.py:73-74` 两处定义，**零消费方**，「除定义外没有任何引用」属实 |
| **行号** `cli.py:142,167` → `140,165` | **是** | spec.md:91；`rg -n "create_pipeline_app" src/app/cli.py` → 19、**140**、**165**，现已对上 |
| **D-4 交叉引用 / 全角 `／`** | **是** | `deferred.md:44` 改指 §2.3 并补了归属理由；:18 的 `／` 已改为「Starlette 与 uvicorn」。两份文档全量标点扫描：spec 9 处、deferred 2 处命中全部是标题编号、`---` 与量值小数点，**无真实违例**；无硬折行（最长段落 417 字符单行） |

### 1.1 R2-1 改写后对 `config.example.yaml:280-289` 的转述：**逐字准确**

两处引文与原文比对：

- spec 写「**用户冻结的不变量是绝不误杀合法长思考**」← 原文 :282「用户冻结的不变量是绝不误杀合法长思考：……」**逐字一致**
- spec 写「运维可显式配置非零值以选择有界等待，但那是对该不变量的主动覆盖」← 原文 :283 **逐字一致**（仅省句号）

### 1.2 【次要 / 高】唯一的新问题：这段引用的**适用范围**比原文宽

`config.example.yaml:280-289` 那段注释在 YAML 里紧贴的是 `response_header`（:290），不是 `upstream_request_deadline`（:314）。两处细节使「调低 `upstream_request_deadline` 属于覆盖该不变量」这个推论不是从原文直接读出来的：

1. 原文说「因此 bundled defaults **全部禁用**此类终止器」，而 `upstream_request_deadline` 的 bundled default 本身就是**非零的 1200**——用户没有把它禁用掉。
2. 用户给它写了**另一段**说明（:308-312）：「单次上游尝试的最大存活秒数……与另外两个上游守卫互补：`response_header` 只管首字节前，`stream_idle` 只管帧间空档，两者都拦不住『一直滴水但永不结束』的尝试」。按这个描述它是**总时长**上界，不是**静默**上界，也就不是 :282 所说的「此类终止器」。

**推论本身仍然成立，但成立的理由是实现而不是原文**：因为 D-6（`asyncio.timeout` 只包住 `await send`），这个旋钮对流式请求**当前确实退化成了 pre-header 静默上界**——spec.md:60 自己也写了「恰好且仅仅覆盖这一段」。所以它现在确实落在那条不变量的射程内。

不影响结论（无论怎么读，「本规范不提议这种覆盖」都是对的），只影响一个照着链接去读原文的人会不会觉得对不上。**建议补一个从句**：指出该不变量的正文写在 `response_header` 名下、`upstream_request_deadline` 的 bundled default 本身是非零的 1200（:308-314），它落进同一条不变量是 D-6 造成的当前行为。

### 1.3 其余新增陈述的复核

- spec.md:35（`6a55adf` 新增）关于「结算点必须在真正的 EOF 之前」的论证**成立**：`task.result()` 在 EOF 时重抛 `StopAsyncIteration`，经内层 `try` 直达 `except ... : return`，控制流不会回到顶部结算点。实测印证：所有探针的事件序列都以 `message_stop` 收尾，**没有流末凭空多出的 ping**；`test_an_empty_upstream_stream_produces_nothing` 仍绿。
- 同段的「10.46s 内 173125 次已到期却被跳过」是插桩计数，**我没有独立复现**（复现需要改 `_events_with_ping` 加计数器，超出只读范围）。但它的**形态**被我的正样本对照独立证实了：同一上游形态在 `6a55adf^` 上 4 秒窗口内 **0 个 ping、最大间隔 4.00s**（见 §2）。按证据强度，这个具体数字记为「作者实测、未经我复核」，形态结论记为「已独立证实」。
- `settings.py:73-74`「各默认 15」属实；「上游侧一共四个旋钮都不产生任何保活行为」属实。

---

## 2. `6a55adf` 之后，§2 的判据是否已被实现完全兑现

**是。** 只看契约兑现，不看控制流。

判据：一旦交付已经开始，客户端不得连续 `sse_ping_interval` 秒收不到任何字节。

把三种曾经击穿它的上游形态、以及一个把「连发」与「真等待」交替起来的组合形态，跨三种 `buffering_policy` 全测一遍，直接测量**实际的字节间最大间隔**（`/tmp/probe_keepalive/probe_contract_met.py`，`sse_ping_interval=1`、`synthesized_...=2`、4 秒窗口）：

```bash
PYTHONPATH=src uv run python /tmp/probe_keepalive/probe_contract_met.py
```

| 上游形态 | policy | pings | 首字节 | **最大间隔** | 判定 |
|---|---|---|---|---|---|
| always-ready（从不交出控制权） | block | 3 | 0.00s | **1.00s** | 满足 |
| always-ready | full | 2 | 2.00s | **1.00s** | 满足 |
| always-ready | until-tool-use | 2 | 2.00s | **1.00s** | 满足 |
| chatty（快过 interval，但让出调度） | block | 4 | 0.00s | **1.00s** | 满足 |
| silent（首块后完全静默） | block | 3 | 0.00s | **1.01s** | 满足 |
| ready-run 与 wait 交替 | block | 5 | 0.00s | **1.00s** | 满足 |
| chatty | full | 2 | 2.00s | **1.00s** | 满足 |
| silent | full | 1 | 2.01s | **1.00s** | 满足 |
| ready-run 与 wait 交替 | full | 3 | 2.00s | **1.00s** | 满足 |

九种组合全部满足，最大间隔上确界 1.01s ≈ `sse_ping_interval`。首字节要么 0.00s（`block` 立即交付），要么 2.00s（被扣住时落在合成上界上），两个维度都在承诺内。

**正样本对照**（同一探针跑在 `6a55adf^` 的源码上，用 `git archive` 抽到 `/tmp/probe_keepalive/pre/` 并以 `PYTHONPATH` 覆盖加载，已打印 `_keepalive_due not in source` 确认）：

| 上游形态 | policy | pings | 首字节 | 最大间隔 | 判定 |
|---|---|---|---|---|---|
| always-ready | block | **0** | 0.00s | **4.00s** | **击穿** |
| always-ready | full | **0** | **4.00s**（流末） | — | **击穿**（零字节直到流末） |
| always-ready | until-tool-use | **0** | **4.00s**（流末） | — | **击穿** |
| ready-run 与 wait 交替 | block | 4 | 0.00s | **1.80s** | **击穿** |
| ready-run 与 wait 交替 | full | 2 | 2.00s | **2.20s** | **击穿** |

探针有分辨力：修复前 5 处击穿，修复后 0 处。（表中 `full`/`until-tool-use` 两行修复前之所以间隔列为空，是因为它们**一个字节都没发出去**直到流末——那是最坏情况而非通过，靠「首字节」列才看得出来。这是我这个判定函数只看字节间间隔的局限，特此点明。）

**因此 r2 §5.0 提出的「spec §2 的固定时点应与在途改动对齐」这个条件，已经满足。** 该在途改动已落为 `6a55adf`，§2 的判据在我已知的全部敌对上游形态下都被实现兑现。

补充静态确认：`uv run ruff check src/ tests/` → All checks passed；`uv run pytest tests/unit tests/component -q` → **1037 passed, 1 skipped**（较 `3160285` 的 1036 多出的一条就是新增的 `test_an_always_ready_upstream_does_not_starve_the_keep_alive`）。

---

## 3. 仍未落实的项（次要，不阻断固定）

上一轮列在「建议同批一起改掉」里的两条没有动，我不认为它们该拦住固定，但记在这里免得丢失：

- **R2-6** — spec.md:39「这是代码里唯一的那道门」。`src/app/pipeline/delivery/blocks.py:137,154,164` 还有一个 `DeliverySession.started`（「有没有块被释放过」）。它不参与 `_deliver` 的任何判断，所以不构成第二个答案；但句子是全称的，建议收窄为「这是**这三个决策**共用的唯一那道门」。
- **R2-7** — spec.md:92「`upstream_request_timeouts.stream_idle`……**在新链路上**没有任何消费方」。实际是新旧两条链路都没有（`rg -n "upstream_request_timeouts" src/` 只有 `schema.py:295` 定义与 `handler.py:99`，后者只取 `upstream_request_deadline` 与 `response_header_overrides`）。删掉「在新链路上」五个字即可。

另外两条纯记录：

- spec.md:85 的「**这两个名字**目前在说谎」现在紧跟在 :83「一共四个旋钮」之后，指代略糊。`deferred.md` D-3 已用「前两个」消歧，spec 侧可比照。
- 关于三个空行：`src/app/pipeline/delivery/stream.py:112-114` 实际是**三个**空行（你说的是两个），不过 `ruff check` 确实通过——Ruff 的 `E303` 属 preview 规则，当前 `select` 下不生效。所以你的结论对，计数差一个。纯外观，不必单独改。

---

## 4. 能否固定为规范

**能。**

- 五处文档修改全部落实，引文逐字准确，没有引入新的不实陈述；唯一的新问题（§1.2）是引用范围比原文宽一档，不改变任何结论，补一个从句即可。
- §2 的判据在 `6a55adf` 之后被实现完全兑现：九种敌对上游形态跨三种 buffering policy 实测，最大字节间隔上确界 1.01s，正样本对照在修复前击穿 5 处。r2 §5.0 提出的对齐条件已满足。
- 剩余三条（R2-6、R2-7、§1.2）都是措辞与引用精度，不影响规范的正确性，也不影响读者据此行事的方向。

一句自我限定，接在 r2 结尾那句后面：**我说「§2 的判据已被兑现」，射程是「在我已知并构造得出的上游形态下」。** 这一轮我补了「从不交出控制权」和「连发与等待交替」两种上一轮想不到的形态，正样本对照也确实击发了——但前两轮各漏一个窗口的记录摆在那里，所以这句话是「已知的都测过了」，不是「不可能再有第四种」。要把它升级成后者，需要的不是再多几个探针，而是换一种论证方式（例如对 `_events_with_ping` 的到期判断做可达性论证），那超出本轮范围，也不是固定这份规范的前提。

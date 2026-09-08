# 候选材料 × 人写文档最新状态：逐条对账

**日期**：2026-08-22。**性质**：调查报告，只判定不改动。任何一个字都没有写进 `docs/.human-controlled/`，候选文档也未被修改。

**对账基准**：

- 人写文档：工作树当前状态（含 4 份未提交改动：`client-side-block-delivery.md`、`config.example.yaml`、`module-org.md`、`upstream-retry-and-continuation.md`）。基线提交为 `2afa0c4`（2026-08-22 13:36，该目录当前唯一的内容提交）。
- 候选材料：`.dev/human-controlled-docs-candidates/` 下除 `README.md` 外的 12 份。
- 代码事实：工作树当前状态（含未提交的 `pidfile_dir` 改造）。

**一个贯穿全局的前提变化，先说在前面**：`docs/.human-controlled/MAIN.md` 已不存在——它在 `2afa0c4` 里被拆成 `module-org.md` / `api.md` / `request-pipeline.md` / `message-translation.md` 等多份（`git ls-tree --name-only HEAD docs/.human-controlled/` 无 `MAIN.md`；`git log --all --name-only -- 'docs/.human-controlled/*'` 显示它只存在于历史）。有 4 份候选文档（`uncovered-modules.md`、`config-schema-gap.md`、`config-migration-gaps.md`、`existing-rulings.md`）通篇以 `MAIN.md` 为对照基准并按它的章节引用，`instructions-shape-conflict.md` 的目标文档 `model-translation.md` 也已更名为 `message-translation.md`。这些指针一律判为**已过期**，与其内容是否仍成立无关。

## 判定汇总

| 判定 | 条数 |
|---|---:|
| 已采纳 | 10 |
| **已采纳但走法不同** | **6** |
| **已明确否决** | **4** |
| 仍然打开 | 40 |
| 已过期 | 18 |
| 现状记录（不含提案，无待办） | 3 |
| 合计 | 81 |

## 总表

标注约定：条目名取该条的小节号或表格行；证据列给出人写文档或代码的 `file:line`。

### `upstream-retry-and-continuation-supplements.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| A1 | §一 回答 TODO：`max_tokens` 不无痕重试、**一律**走合成续写（n=20，不存在零块交付） | **走法不同** | `upstream-retry-and-continuation.md:60-62` |
| A2 | §二 被截断的块要不要交付（`status: incomplete` 判据 + 三条规则） | **走法不同** | 同上 62 行；`formats/openai_responses.py:393` |
| A3 | §三 400 一格点明涵盖上下文超限 | 已采纳（简化） | `upstream-retry-and-continuation.md:9` |
| A3b | §三 两条腿的 `error.code` 形态差异措辞、`parse_prompt_limit_error` 在主路径返回 `None` | 仍然打开 | 文档无对应文字 |
| A4 | §四 非流式路径只能无痕重试、不能续写 | 已采纳（措辞不同） | `upstream-retry-and-continuation.md:28` |
| A5 | §五 无痕重试不设间隔 | 已采纳 | `upstream-retry-and-continuation.md:20` |
| A6 | §六 观测面（客户端算成功／上游尝试算失败、`[RETY]`、`usage` 报实报值） | 仍然打开 | 文档无对应文字；`observability.md` 本身不存在 |
| A7 | §七 措辞残留「其他**上游请求**暂不使用该机制」 | 仍然打开 | `upstream-retry-and-continuation.md:42` |
| A8a | §八 删 `continuation` 五行 | 已采纳 | `2afa0c4` 的树里已无该块 |
| A8b | §八追加 删 `streamReplay` 两行 | 已采纳 | `git diff` 该 hunk |
| A8c | §八 顺带：两处 continuation 注释（中／英） | 仍然打开 | `config.example.yaml:316,319,372` |
| A8d | §八 `max_tokens_as_retryable` 保留 | 已过期 | 该键在 `config.example.yaml` 与 `src/app/config/schema.py` 中均已不存在 |
| A8e | §八 顺带发现：`hook_strip_anthropic_request_headers` 的第二处红 | 已过期 | `schema.py:407` 已有对应物；`tests/unit/config/test_config_schema.py` 14 passed |
| A9 | §九 半开 `message_start` 的「给实现者的提醒」 | **已明确否决** | `upstream-retry-and-continuation.md:26` |
| A10 | §十 删掉 `hand_over_stop_reasons` 里的 `max_output_tokens` | **已明确否决** | `config.example.yaml:339` + `upstream-retry-and-continuation.md:62` |
| A11 | §十一 `client-side-block-delivery.md:16` 节名改 `upstream_request_timeouts` | 已采纳（逐字） | `client-side-block-delivery.md:16` |

### `pidfile-port-scoping.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| B1 | `pidfile`（文件）改为 `pidfile_dir`（目录） | 已采纳 | `config.example.yaml:227-235` |
| B2 | 默认文件名按端口区分 `standalone-<port>.pid` | 已采纳 | `config.example.yaml:228,231` |
| B3 | 同日三条裁决的实现记录（`--restart` 告警、`write_pidfile` 拒绝覆盖＋`--force-write-pidfile`、`--fd` 冲突报错） | 已采纳（记录） | `src/app/lifecycle/entry.py:110-117`、`src/app/cli.py:218-236,268-271` |
| B4 | 待裁决：`GHC_API_PROXY_PORT` 这个拼写（三条出路，倾向实现顶层别名） | 仍然打开 | `config.example.yaml:228,231` 仍用该记号；`src/app/config/loading.py:22,117` |
| B5 | 切换时的一次性影响：为当前 4141 进程补一份 pidfile 记录 | 仍然打开 | 运维动作，用户未表态 |
| B6 | 本目录早先「保留 `pidfile` 文件语义」的替换文案 | **已明确否决** | 候选文件自身第 16 行已记录并删除该文案 |

### `uncovered-modules.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| C1 | `delivery/` 行 | **走法不同** | `module-org.md:18-19` 追认的是 `pipeline/delivery`，而候选指的是顶层 `src/app/delivery/` |
| C2 | `context/` 行 | **走法不同** | `module-org.md:24-31`「尚未确认、有疑虑」 |
| C3 | `anthropic/`、`openai/` 两行 | **走法不同** | 同上 |
| C4 | `config/`、`history/`、`observability/`、`cli.py` 四行 | 已采纳 | `module-org.md:10,12,17,7` |
| C5 | `auth/` 行 | **走法不同** | `ghc-api.md:5-8` 只承载 device flow 与换 token，未承载「CLI/env/file 来源链」 |
| C6 | `protocols/`、`transform/`、`streaming/`、`models/`、`upstream/`、`hooks/`、`tokenization/`、`errors.py`、`wire_json.py`、`repetition_detector.py`、`deps.py`、`runtime.py` | 仍然打开 | `module-org.md` 全文无这些名字 |
| C7 | 「已实现但无生产消费者」清单 | 已过期 | 清单含已删除的 rolling 相关项；`src/app/pipeline/subscribers/` 已有 4 个模块 |
| C8 | 全文以 `MAIN.md` 为对照列 | 已过期 | `MAIN.md` 不存在 |

### `config-schema-gap.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| D1 | §一 结构对照表 `pidfile` 行 | 已过期 | 已改名 `pidfile_dir` |
| D2 | §一 `upstream_request_retry.*` 行「全新：具名策略表、`max_total`、continuation」 | 已过期 | continuation 已从规格删除 |
| D3 | C-1 `buffer_cap_bytes` 与 16 MiB 既有裁决的相容确认 | 仍然打开 | `config.example.yaml:391-393` 措辞未变 |
| D4 | C-2 continuation 是否即构成独立 ADR | 已过期 | `upstream-retry-and-continuation.md:44`「代理内续写（已放弃）」 |
| D5 | C-3 热重载粒度与触发机制 | 仍然打开 | `config.example.yaml:24`；`ConfigProvider` 仍只被 `provider.py` 自身引用 |
| D6 | §三 五行「规格已定案、实现有缺口」 | 仍然打开 | 人写文档无变化 |
| D7 | §四 continuation 的续写请求构造 | 已过期 | 同 D4 |
| D8 | §四 `max_tokens_as_retryable` | 已过期 | 被 `hand_over_stop_reasons` 取代且已接线（`schema.py:187`、`pipeline_app.py:529`） |
| D9 | §四 hedge | 仍然打开 | `config.example.yaml:401-407` 仍在规格里，代码无消费者 |
| D10 | §四 其余六项能力缺口 | 仍然打开 | `config.example.yaml` 相应节未变 |
| D11 | §四 前言里「`synthesized_response_headers_after_sec` 的计时已接入」 | 已过期 | 该键已被用户裁决删除（`upstream-retry-and-continuation.md:26`） |
| D12 | §七 `stream_idle` 注释措辞提案 | 仍然打开 | `config.example.yaml:303-304` 仍是「SSE 事件之间的最大间隔」 |
| D13 | §六 与既有实现相容的部分 | 现状记录 | — |

### `config-migration-gaps.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| E1 | §一 `history` 五字段、`approval`、`observability`、`tokenization` 四节 | 仍然打开 | `config.example.yaml:413-414` 只有 `enabled`；另三节全文无 |
| E2 | §二 `hooks` 列表项语义与单 hook 超时 | 仍然打开 | `config.example.yaml:420-437` 六个订阅点仍是裸 `[]` |
| E3 | §二 token 来源 | 仍然打开 | 规格无承载 |
| E4 | §二 generic 上游 | 仍然打开 | `config.example.yaml:150-152` 仍只有 `type: github_copilot` |
| E5 | §三 常驻字节预算（global／request resident bytes） | 仍然打开 | 规格仍只有 `buffer_cap_bytes` |
| E6 | §三 `anthropic.route_override` 是否保留部署级默认 | 仍然打开 | 规格无对应项 |
| E7 | 以 `MAIN.md` 为端点清单出处 | 已过期 | 端点现在在 `api.md` |

### `existing-rulings.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| F1 | C-3 两条路径的平滑重启机制各用各的、不统一——待确认 | 仍然打开 | `lifecycle.md:28-35,44` 未表态 |
| F2 | §二 `--systemd` 参数仍不存在 | 仍然打开 | `lifecycle.md:42` 要求；`src/app/cli.py` 只有 `--fd` |
| F3 | §二 四个运维配置节 | 仍然打开 | 同 E1 |
| F4 | §二 cgroup 资源限制「缺 rolling 一侧」 | 已过期 | rolling 已整体删除；`tests/smoke/` 目录也不存在 |
| F5 | §二 持久化状态的平滑重启交接 | 仍然打开 | `lifecycle.md:36-38` 仍是 TODO |
| F6 | §三／§四 的裁决记录与对照基准（`MAIN.md`、`model-translation.md`） | 已过期（指针） | 两个文件名都已不存在 |

### `deployment.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| G1 | `app.lifecycle.rolling` 与 `.generation` 两张模块表 | 已过期 | `git ls-files src/app/lifecycle/rolling` 为空（仅剩 `__pycache__` 残留） |
| G2 | 「当前未闭合项」表（apply 闸、`feat/systemd-rolling-apply` 等） | 已过期 | 同上 |
| G3 | `shutdown.py` 的去留交用户判断 | 仍然打开 | `src/app/shutdown.py` 仍在且仍无生产消费者 |
| G4 | `activation.py` / `adapter.py` / `systemd/` 模块表 | 现状记录 | 文件仍在 |

### `systemd-shutdown.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| H1 | 第二至四节的三级重组提案 | **已明确否决**（2026-08-17，文件首部已自标） | 候选文件第 3-6 行 |
| H2 | §五1 `lifecycle.md:59` 的「（30s）」应改 60s | 仍然打开 | `lifecycle.md:59` 仍写 30s；`config.example.yaml:243` 是 60 |
| H3 | §五2 三处 `client_request_timeout` 键名已不存在 | 仍然打开 | `lifecycle.md:59`、`config.example.yaml:238,241` |
| H4 | §五3 公式基数究竟是 1200 还是 3600 | 仍然打开 | 无一手出处 |
| H5 | §五4 `lifecycle.md:52-55` 的 TODO 与两级流程 | 仍然打开 | `lifecycle.md:52` 的「（TODO systemd 是否支持三级处理？）」仍在 |

### `rolling-removal.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| I1 | 建议删除或改写 `lifecycle.md` 的「代（generation）生命周期」整节 | 仍然打开 | `lifecycle.md:65-89` 原样保留 |
| I2 | 若改写为历史记录，保留 2026-08-16 那句原话并补 `archive/260819-rolling` | 仍然打开 | 同上 |
| I3 | §六 旧链 `create_app` 已无生产入口 | 现状记录 | — |

### `pipeline-subscriptions.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| J1 | 待决点1「修改公共对象」的写入规则 | 仍然打开 | `request-pipeline.md:17` 仍只写「能够修改上下文对象」 |
| J2 | 待决点2 `HookErrorMode` 是否并入异常体系 | 仍然打开 | `request-pipeline.md:19` 只定了异常闭集 |
| J3 | 待决点3 `hooks` 六个订阅点列表项语义与单 hook 超时 | 仍然打开 | 同 E2 |
| J4 | 提案1 事件点取自现有 `POST_SANITIZE` / `PRE_SEND` | 仍然打开 | 用户文档未表态 |
| J5 | 提案3 三个内置 hook 作首批迁移样本 | 仍然打开 | `src/app/hooks/builtin/` 三个仍在原地 |
| J6 | 「现状」段的两处：`RequestContext` 命名、「只有一个订阅者」 | 已过期 | `request-pipeline.md:16` 已改称 `ClientRequest` / `UpstreamAttempt`；`src/app/pipeline/subscribers/` 现有 4 个模块 |

### `proactive-rate-limiter.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| K1 | 提案一 解注释 | 仍然打开 | `config.example.yaml:341-343` 仍是 `# #` 双井号 |
| K2 | 提案二 示例值 5 与默认值 50 分开写 | 仍然打开 | 同上 |
| K3 | 提案三 写明超限行为是等待 | 仍然打开 | 同上 |
| K4 | 待裁决：排队时间不计入任何 deadline | 仍然打开 | 用户未表态 |

### `instructions-shape-conflict.md`

| # | 条目 | 判定 | 证据锚点 |
|---|---|---|---|
| L1 | 待裁决1 `instructions` 形态改为字符串 | 仍然打开 | `message-translation.md:36-62` 仍是对象数组形态，末句仍为「只是目前我们用不到这层灵活性」 |
| L2 | 待裁决2 接受 prompt caching 损失 | 已过期（候选自撤） | 候选文件第 68 行已划掉 |
| L3 | 目标文档 `model-translation.md` | 已过期（指针） | 现为 `message-translation.md` |

---

## 判定所依赖的时序证据（先交代，因为「否决」这一类要靠它）

区分「用户尚未处理」与「用户看过之后决定不改」，需要知道候选材料与人写文档的先后。仓库里这几份文件都未提交，唯一可用的一手序列是 mtime：

| 时刻 | 文件 |
|---|---|
| 12:48 | `docs/.human-controlled/module-org.md` |
| 13:36 | 提交 `2afa0c4`（该目录进入仓库） |
| 14:05 | `.dev/human-controlled-docs-candidates/upstream-retry-and-continuation-supplements.md` |
| 14:48 | `docs/.human-controlled/config.example.yaml` |
| 15:03 | `.dev/human-controlled-docs-candidates/pidfile-port-scoping.md` |
| 15:06 | `docs/.human-controlled/client-side-block-delivery.md` |
| 15:26 | `docs/.human-controlled/upstream-retry-and-continuation.md` |

**这条证据的份量：足以支撑「用户看过 §9/§10/§11 之后才写下现在这版」，不足以支撑「用户逐条读完了整份候选文档」。** mtime 只说明文件在那一刻被写过，不说明写的是哪一段。因此下面每一条「已明确否决」都另外配了一条**内容层面的对位证据**——用户写下的那句话正面回答了候选提出的那个问题——判定建立在内容对位上，mtime 只是佐证。

反过来，A8b（删 `streamReplay`）与 A11（改节名）这两条**采纳**的证据是逐字比对，不依赖时序。

一处需要主会话知道的**引用瑕疵**：`§八追加` 说 `streamReplay` 在「第 339–340 行」，而 `2afa0c4` 的树里它在 336–337 行；`§十` 说 `hand_over_stop_reasons` 在第 339 行，这与「`streamReplay` 已被删掉之后」的行号吻合。两节的行号取自同一天不同时刻的工作树快照，互不自洽。**内容引文本身逐字准确**，所以不影响判定，但候选文档里的行号不可当作可复算的坐标。

---

## 一、已明确否决（4 条，逐条展开）

### A9 — 「半开 `message_start` 由构造保证、没有任何守卫」这条提醒，用户拒绝写进权威文档

候选 §九建议在文档里补一句给实现者的提醒：

> 该性质由构造保证，不由任何断言保证——live 链路一条相关守卫都没有（9 条 `DeliveryOrderError` 全在未挂载的 legacy 侧）。将来谁再引入单独发 `message_start` 的路径，不会有任何东西报错。

用户在同一段落里正面回答了它。`upstream-retry-and-continuation.md:26`（本次新增，原文是段内括注，现改为引用块）：

> 用户已裁决删除 `client_delivery.synthesized_response_headers_after_sec`，因为这种情况下没有交付过完整块，也不再出现半开 `message_start` 需要考虑。**事实上目前不应该有半开 `message_start`，但这不属于本节讨论范围，是一条推论，不应由我们写死。**

加粗那半句是新写的。它承认了推论的内容（「目前不应该有」），同时给出两条不采纳的理由：**不属于本节范围**，以及**推论不应由我们写死进权威文档**。

**这意味着什么**：被否的不是事实判断，而是「把一条由代码构造保证的性质固化成需求文档条款」这一动作。候选 §九自己已经标了「可放可不放」，用户选了「不放」。**主会话该做的是把 §九从候选材料里撤下**，并且不要以任何形式（补 ADR、补 spec、补守卫需求）把它再送一遍；如果确实认为缺守卫是风险，那属于实现侧的事，走代码与测试，不走人写文档。

### A10 — `hand_over_stop_reasons` 里的 `max_output_tokens`，用户不但保留，还写进了正文

候选 §十的建议是：删掉 `max_output_tokens`，与 schema 默认 `["max_tokens"]` 一致；若想保留作提示则改成注释。§十的补充还把结论加强到「配置成它也不会生效」。

用户的处置：

1. `config.example.yaml:339` **原样保留** `hand_over_stop_reasons: ["max_tokens", "max_output_tokens"]`。同一次编辑里，紧邻它上方的 `streamReplay`（同一份候选 §八追加提出的）被删掉了——**用户在这一段动过手，且采纳了同段的另一条建议**。
2. 更强的证据在最后一次编辑（15:26）里：`upstream-retry-and-continuation.md:60-62` 新增了一整节，把两个拼法并列成同一情形的两种协议写法：

> ## 输出超长
>
> 对于 SSE stop_reason = `max_tokens` (anthropic-messages) / `max_output_tokens` (openai-responses) 的情形，不应无痕重试。……

也就是说，用户的心智模型是：**`stop_reason` 的取值随协议而异，`max_tokens` 是 anthropic-messages 的拼法，`max_output_tokens` 是 openai-responses 的拼法，配置里两个都列才算覆盖两条腿。**

**代码与这个心智模型的差距，精确地是三处：**

**（1）比较发生在归一化之后，所以 `max_output_tokens` 永远匹配不到。** `src/app/pipeline/delivery/formats/openai_responses.py` 的 `push()` 里，`response.incomplete` 先走 `_read_terminal()`（513-514 行）把 `incomplete_details.reason == "max_output_tokens"` 改写成 `"max_tokens"`，然后同一分支的 393 行才拿 `self._terminal.stop_reason` 去和 `hand_over_stop_reasons` 比。非流式在 `src/app/pipeline/translation_driver/responses.py:125-126` 做同一次归一。两条腿到达这个键时看到的都是 `max_tokens`。

**（2）因此这份权威样例正在把一个惰性值展示成有意义的取值。** 危害不是「多一个值」，而是下一个读者可能反向推断——上游明明说 `max_output_tokens`，于是把 `max_tokens` 删掉或替换掉。此后所有撞上限的回合都不再交接，且**同一个键还决定被截断的块丢不丢**（`formats/openai_responses.py:393`），门不中就保留半截块正常收尾，客户端拿到一个截断块 + `stop_reason: max_tokens`，没有 tool call、没有告警。是静默失效。

**（3）用户的两分支写法与代码的分支判据不是同一条。** 文档说「能续写 → 丢弃未完成的块；不能续写 → 直接返回给客户端」，而代码里**丢弃只由 `stop_reason ∈ hand_over_stop_reasons` 决定**（`formats/openai_responses.py:393`），**能不能续写却另有一道闸**：`src/app/server/pipeline_app.py:552` 的 `if route.wire_format is not WireFormat.ANTHROPIC_MESSAGES: return None`。而 assembler 的选择只看**上游方言**，不看客户端格式（`src/app/server/handler.py:614-624` 的 `assembler_for` 依 `dialect_for`，`handler.py:533-545` 表明它取 `route.target_format`）。于是存在一个用户文档没有描述的形态：**一个非 anthropic-messages 的客户端走 Responses 上游撞上限时，被截断的块被丢掉，而交接用的 `tool_use` 块不会生成——两条分支都没走成，客户端既没拿到半截内容，也没拿到续写入口。**

**结论**：A10 判为**已明确否决**（删除建议被用户以一次正面书写驳回），但它暴露的（1）和（3）**不是被否决的东西**——（1）是「用户的配置写法与代码的比较时机不一致」，（3）是「用户文档的二分与代码的三态不一致」。候选材料应当**改写而不是删除**：删掉「建议删除 `max_output_tokens`」这个诉求，改为陈述归一化时机与第三种形态，交由用户决定是让代码去迎合文档（在比较前保留原始拼法，或把 wire format 闸并进同一条判据）还是让文档补一句。

### B6 — 「保留 `pidfile` 文件语义」的替换文案

这条是候选目录自己已经记录的否决：用户改成了目录语义（`config.example.yaml:227-235`），候选文档第 16 行写明「本目录早先提出的替换文案（保留 `pidfile` 文件语义）未被采纳，已删除」，理由是「一个设置覆盖操作者跑的所有端口，而文件名不必、也不应由操作者选」。**无需主会话再处置**，列在这里只为让否决类的清单完整。

### H1 — systemd 侧三级关闭的重组提案

2026-08-17 已被用户否决，候选文件首部第 3-6 行自标：「本文的提案已被用户否决——仅作调研留档，不要照它实施」。人写文档侧的对应事实是 `lifecycle.md:52-55` 至今仍是两级流程。**同样无需再处置**，但要注意 H2–H5 四条文档不一致是这份候选里**仍然有效**的部分，不要连同被否决的提案一起丢弃。

---

## 二、已采纳但走法不同（6 条，逐条展开）

这一类最要紧：它说明我们对用户意图的理解有偏差，候选材料若照原样留着，下一次会把偏差再送一遍。

### A1 — TODO 被回答了，但答案的**形状**不同：我们要「一律」，用户要「两分支」

候选 §一给出的建议措辞是：

> 特殊地，`max_tokens` 不应无痕重试，**一律走 MCP-driven 合成续写**。……撞顶时上游一定为被截断的 item 发出 `output_item.done`……**不存在零块交付的形态**。所以 `max_tokens` 总是落在「已交付过完整块」那一格。

用户删掉了原第 23 行的 TODO（`git diff` 可见），另起一节 `upstream-retry-and-continuation.md:60-62`：

> 对于 SSE stop_reason = `max_tokens` (anthropic-messages) / `max_output_tokens` (openai-responses) 的情形，不应无痕重试。要么在能续写的情况下，丢弃未完成的块，走下文合成续写机制；要么在不能续写的情况下，直接返回给客户端。

**采纳的部分**：「不应无痕重试」逐字采纳；「走合成续写」采纳。

**走法不同的部分**：我们要求的是无条件（「一律」「总是落在那一格」），用户写的是有条件的二分。而且用户的版本**更对**——`upstream-retry-and-continuation.md:28`（非流式不支持合成续写）与 `:42`（只给 anthropic-messages 客户端用该机制）都会让「不能续写」这一格真实存在，我们的 n=20 证据只覆盖了「流式 + Anthropic 客户端」这一格，却写成了全称。

**主会话该做的**：把 §一里「一律」「总是」这类全称措辞改掉，明确 n=20 的适用域是「流式、Responses 上游、撞 `max_output_tokens`」；n=20 的结论仍然有用——它说明在那一格里「零块交付」不会发生——但它不再是用来推翻二分的论据。用户没有采纳的另外两件（n=20 的样本边界、参考项目综述），属于证据材料而非规格文本，留在 `.dev` 即可，不必再往人写文档送。

### A2 — 「丢弃被截断的块」被采纳，但**触发条件**换了一套，且 wire 判据没被采纳

候选 §二的建议措辞是三条规则：已经有任何完整块时丢弃被截断的那个；只有未完成块时保留它；reasoning item 上游不带 `status` 字段、无信号故不特殊处理。判据是 `output_item.done` 上的 `status: "incomplete"`。

用户写的是：「要么在能续写的情况下，丢弃未完成的块」（`:62`）。

差异有三层：

1. **条件不同**。我们绑「已经交付过几个完整块」，用户绑「能不能续写」。代码实际绑的是第三样东西——`stop_reason ∈ hand_over_stop_reasons`（`formats/openai_responses.py:393`）。三者在主路径上恰好重合，但在「非 anthropic-messages 客户端」这一格上分叉（见 A10 第（3）点）。
2. **判据没进文档**。`status: "incomplete"` 这个 wire 信号一个字都没进人写文档；代码里对应的是 `_upstream_cut_this_item_short`（`formats/openai_responses.py:520`）。这不是问题——用户文档写的是需求不是实现——但**候选材料不该继续把它当作「待用户采纳的措辞」**，它已经是实现事实。
3. **「保留半截块」那一格没有对应文字**。用户的「不能续写 → 直接返回给客户端」可以读成「连同半截块一起返回」，但没有明说。这一格值得单独向用户确认。

### C1 — `pipeline/delivery` 被追认，但被追认的不是候选说的那个包

`module-org.md:18-19`（本次新增）：

```
    pipeline            # 模型请求的处理管线
        delivery            # 客户端侧的块级交付机制
```

候选 `uncovered-modules.md:15` 那一行说的是**顶层** `src/app/delivery/`（该表其余各行 `anthropic/`、`openai/`、`protocols/`、`transform/`、`streaming/`、`context/`、`hooks/`、`models/`、`upstream/` 全是 `src/app/*` 的顶层包），职责写的是「Anthropic SSE 渲染、单一 sink、交付前沿、常驻字节预留」。

现实是两个包并存：`src/app/pipeline/delivery/`（新链，8 个模块＋`formats/`）与 `src/app/delivery/`（legacy，`anthropic_sse.py`、`responses_anthropic_stream.py`）。用户追认的是前者。**所以同一个问题被解决了——块级交付终于在模块图里有了位置——但候选那一行指的那个包仍然没有位置。**

**主会话该做的**：把 `uncovered-modules.md` 的该行改写为「legacy `src/app/delivery/`」，并说明与已追认的 `pipeline/delivery` 的关系（同一件事的两代形态，一如该文件末尾已为 `transform/translator.py` 与 `streaming/translator.py` 写过的那句）。

### C2／C3 — `context/`、`anthropic/`、`openai/` 有了位置，但位置是「有疑虑」

`module-org.md:24-31`：

```
尚未确认、有疑虑的模块如下：

app
    anthropic
    context
    openai
```

候选逐行给出了这三个包的职责并建议「决定是否需要在自己的文档里给它一个位置」。用户给了位置，但给的是一个**待处置队列**，而不是候选设想的「归入 `app.pipeline` 的转变一节」（`uncovered-modules.md:11-12` 的建议列写的是「未提；`app.pipeline` 的『转变』应涵盖」）。

**这条偏差的含义**：用户不打算把这三个包简单地并进 `pipeline`，而是把它们的存在本身挂起待议。候选材料若继续写「应由 `app.pipeline` 涵盖」，等于替用户把一个他已经挂起的问题擅自答掉。改成陈述职责、不给归属建议更妥。

### C5 — `auth/` 的一半被承载

`ghc-api.md:5-8` 给了 `app.model_provider.ghc_client.auth` 位置，职责写的是 device code 流程与 github_token → copilot_token 交换。候选 `uncovered-modules.md:27` 说的是两件事：device flow（已移入）＋「GitHub token 来源链（CLI／环境变量／文件）」。**来源链那一半仍无位置**，而且它与 `config-migration-gaps.md` 的 E3（token 来源无配置承载）是同一件事的两面。合并处理更省事。

---

## 三、已采纳（10 条，证据从简）

- **A11**：`client-side-block-delivery.md:16` 现为 `upstream_request_timeouts.upstream_request_deadline`，与候选 §十一 给出的节名逐字一致。代码侧三处佐证仍成立：`src/app/config/schema.py` 的 `UpstreamRequestTimeoutsConfig`、`src/app/server/handler.py` 的 `timeouts.upstream_request_deadline`、以及 `config.example.yaml:290-313` 的分节。**候选 §十一可以整节撤下。**
- **A8b**：`streamReplay: max_retries: 100` 两行已从 `config.example.yaml` 消失（`git diff` 的删除 hunk）。**§八追加 可以撤下。**
- **A8a**：`continuation` 那五行在 `2afa0c4` 的树里就已不存在，属于更早采纳。**§八 前半可以撤下。**
- **A3**：`upstream-retry-and-continuation.md:9` 由「400」改为「400，包括请求非法和输入超长」，即候选 §三 的核心诉求。用户采纳了「点明 400 涵盖上下文超限」，未采纳两条腿 `error.code` 形态差异的详细措辞——那部分列为 A3b，仍然打开。
- **A4**：`:28` 新增「作为对比，非流式请求只接入适合无痕重试的情形，不支持合成续写」，与候选 §四 同义。
- **A5**：`:20` 句末新增「无痕重试不设冷却间隔」，与候选 §五 同义；候选提到的 429 例外在 `:24` 已有独立段落承载。
- **B1／B2／B3**：`config.example.yaml:227-235` 改为 `pidfile_dir` ＋ 按端口命名；实现侧 `src/app/config/paths.py:30`、`src/app/config/schema.py:42,383`、`src/app/cli.py:218-236,268-271`、`src/app/lifecycle/entry.py:50-117` 全部对齐（这些改动尚未提交）。
- **C4**：`config/`、`history/`、`observability/`、`cli` 都已出现在 `module-org.md` 的已追认清单里。

---

## 四、已过期（18 条，按失效原因归类）

**因 `MAIN.md` 拆分而失效的指针**（C8、E7、F6、L3，以及 D／E 两份的对照基准行）：候选文档整体需要一次指针重定向，内容多数仍成立。注意 `docs/.human-controlled/README.md:18` 还列着一份不存在的 `observability.md`，且未列入已存在的 `release-and-deployment.md` —— 这是用户自己的文档，不归我们改，但值得作为候选材料提一句。

**因 continuation（代理内续写）被放弃而失效**：D2、D4、D7，以及 A8d（`max_tokens_as_retryable` 在 `config.example.yaml` 与 `src/app/config/schema.py` 里都已不存在，被 `hand_over_stop_reasons` 取代且已接线）、D8（同上）、D11（`synthesized_response_headers_after_sec` 已被裁决删除）。

**因 rolling 被删除而失效**：F4、G1、G2。可复算：`git ls-files src/app/lifecycle/rolling contrib/systemd/rolling` 输出为空，磁盘上只剩 `__pycache__` 残留目录——**顺带一提，那两个残留目录清掉更干净，但那是工作树杂务，不在本次任务授权范围内，未动。**

**因缺陷已被修复而失效**：A8e。`hook_strip_anthropic_request_headers` 现在有 schema 对应物（`src/app/config/schema.py:407`），`uv run pytest tests/unit/config/test_config_schema.py` 14 passed——候选 §八 声称的两处红**当前都不存在了**。

**因代码演进而失效的「现状」描述**：C7（无生产消费者清单需重算）、J6（`RequestContext` 的命名在 `request-pipeline.md:16` 已改为 `ClientRequest` / `UpstreamAttempt`，而代码里仍是 `RequestContext` / `Attempt`——**这本身是一条新的、值得单独提给用户的不一致**；另订阅者已有 4 个而非 1 个）。

**候选自撤**：L2。

---

## 五、给主会话的处置建议（不含执行）

1. **撤下已完成的**：A11、A8a、A8b 三节可以整段删除；A3 的核心诉求已落地，只留 A3b 的余项。
2. **改写而非删除 A10**：删除诉求已被否决，但归一化时机（比较前已把 `max_output_tokens` 改写成 `max_tokens`）与第三种形态（非 anthropic-messages 客户端：块被丢、tool_use 不生成）是新问题，应改写成陈述 + 待裁决点。
3. **A1／A2 收紧适用域**：把全称改成「流式 + Responses 上游 + Anthropic 客户端」这一格，别再用 n=20 去推翻用户的二分。
4. **A9 不再送第二遍**：用户已明说推论不写进权威文档。
5. **`uncovered-modules.md` 需要一次整体重写**：指针（`MAIN.md`）、`delivery/` 那一行的所指、三个「有疑虑」包的归属建议、无消费者清单，四处都要动。
6. **四份候选里重复的同一件事**可以合并：`hooks` 列表项语义与单 hook 超时同时出现在 E2、J3；四个运维配置节同时出现在 E1、F3；token 来源同时出现在 E3、C5。
7. **可以顺带作为新候选材料提出的两条**（本次对账中发现，均属人写文档自身的小不一致，我未改动）：`docs/.human-controlled/README.md:18` 指向不存在的 `observability.md` 且漏列 `release-and-deployment.md`；`upstream-retry-and-continuation.md:62` 的「走**下文**合成续写机制」方向写反了——合成续写一节在 `:30`，位于该行之上。


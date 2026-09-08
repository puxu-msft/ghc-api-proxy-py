# auto mode 分类器本地处置 — 状态

> 权威来源：行为契约见 `spec.md`；未闭合事项见 `deferred.md`。本文只说「现在是什么状态、评审怎么处置的」。
>
> 快照日期：2026-08-23。

## 当前状态

实现完成，两轮独立评审的全部 blocker 与 major 已处置（C-02 除外，见下）。默认 `passthrough`，即不打开就完全不改变现有行为。

已全部提交，**未推送**。特性与其后的三次配置改动、两轮评审的处置都在主仓；文档、四份取证与评审报告在 `.dev` 仓。此处不再列举哈希——这一节被评审抓到过两次陈旧，每提交一次就要改一次的清单没人会维护。要当前范围就跑 `git log --oneline 2b28d07^..HEAD -- src/app/pipeline/auto_mode_classifier.py src/app/config/schema.py src/app/pipeline/driver.py tests/unit/pipeline/test_auto_mode_classifier.py`。

**尚未在真实流量上验证过一次命中**——本机 `~/.claude/settings.json` 当前是 `defaultMode: "bypassPermissions"`，该模式下客户端不调用分类器，所以没有可用于端到端验证的真实请求。全部验证是单元级 + 对客户端源码的静态核对。详见 `deferred.md` D2。

## 配置项归属与形状

用户 2026-08-23 分三次裁定，**均亲笔写进** `docs/.human-controlled/config.example.yaml`。最终形态（该文件当前内容，三个键）：

```yaml
  # 拦截并直接响应 auto mode 分类器的请求。
  intercept_auto_mode_classifier:
    #   passthrough: 透传
    #   allow: 直接允许
    #   block: 直接拒绝
    decision: allow

    match_system_prompt_prefix: "You are a security monitor for autonomous AI coding agents."

    block_reason_str: "Blocked by proxy, without a model review."
```

三次分别是：① 从 `inbound.auto_mode_classifier` 移到 `hook_fix_anthropic_request.intercept_auto_mode_classifier`；② 定下结构化形状与键名（我曾据其第一版误读为标量，见下）；③ 把 `match_transcript_open` 从配置项降为常量。

**归属**比原来的 `inbound` 贴切：这一族就是 `on_client_request_parsed` 那一刻，作用域本来就限定在 Anthropic Messages 那条腿，而短路点正是在 `fix_anthropic_request()` 返回之后、翻译之前。它也把评审挑出的那道入口边界（B-06）从「代码里的一个 if」变成了配置结构本身表达的东西。

**键名**比我原来的好，而且省掉了本来要靠注释解释的事：`match_` 前缀直说它是识别用的、不影响答什么；`block_reason_str` 直说它只在拦截时用。

中间我有一处推断错了并已纠正：从用户第一版写的标量加 `false: 透传` 那行注释，我推断禁用态该用布尔（理由是 YAML 1.1 把裸 `off` 读成布尔，本项目 `assistant_message_layout` 等正是为此用 bool）。用户第二版写的是 `passthrough`——而 `passthrough` 根本不在那个坑里，所以那条论证在此不适用。以用户的为准。

**第三次裁定（同日）**：`match_transcript_open` 不该是配置项，写死。理由用户给的是「`<transcript>` 不是会常变的内容」，成立——两条标记的**易变性不对等**，M1 是一句会被润色的英文散文，M2 是结构标签。当时我还给了第二条理由——M2 的值必须精确到尾部 `\n`，容易配错且配错无声——**收尾评审证明它不具鉴别力**：`match_system_prompt_prefix` 配错了同样无声。真正支撑这个决定的只有易变性判断那一条。钉死不削弱兜底：易变的那条给旋钮，稳定的那条接住它；代价是 M2 没有单独关闭的开关，见 `deferred.md` D6。

**已实测**：用户那份 config 解析通过、三个键的值都被读到生效位置、一条分类器形状的请求拿到 allow verdict、`block` 时 `<reason>` 里是用户写的那句话、schema 默认 `passthrough` 返回 `None`。

### 落地清单

| 文件 | 内容 |
|---|---|
| `src/app/pipeline/auto_mode_classifier.py` | 新增。识别谓词、协议判别、决定文本生成 |
| `src/app/pipeline/delivery/formats/anthropic_messages_synthetic_reply.py` | 新增 `auto_mode_body` / `auto_mode_sse` |
| `src/app/pipeline/driver.py` | `handle()` 内短路 + `_answered_auto_mode` + 发布 `request.succeeded` |
| `src/app/config/schema.py` | `AutoModeDecision` 类型、`FixAnthropicRequestHook.intercept_auto_mode_classifier` |
| `tests/unit/pipeline/test_auto_mode_classifier.py` | 42 个测试 |

### 验证

- `ruff check src tests` 全过；`pyright` 在上述五个文件上 0 错误（仓库既有的 `stream_cap.py` 相关错误与本改动无关，未触碰）
- 本特性自己的测试：`uv run pytest tests/unit/pipeline/test_auto_mode_classifier.py` → **42 passed**（锚定 `2402a85`）
- 全量回归**通过**，覆盖率在门槛 80 之上。此处刻意不写全量条数与覆盖率数字：这棵树同时有多个会话在提交，那两个数随别人的工作漂移，写下来只会变成一个没人维护的陈旧断言——评审已抓到过一次（记的是 89.56%，实际已是 89.88%，再跑又成了 89.75%）。要当前值就跑 `uv run pytest tests --cov=app --cov-report=term --cov-fail-under=80`
- **变异验证**：八个不变量逐个回退，对应测试全部变红，基线字节级还原后仍 42 passed。驱动脚本是一次性的、未收编，因此变异表记在这里——有它就能重建，没有它脚本本身才是证据：

| 改坏什么（符号） | 变成什么 | 变红条数 |
|---|---|---|
| `classify` 里 `_has_classifier_shape` 那道守卫 | 整段删除 | 4 |
| `_SEVERITY_BLOCK` | `101` → `100` | 2 |
| `_protocol_of` 读 system 文本 `<severity>` 的分支 | 整段删除 | 2 |
| `verdict_text` 的 `_DECISION_TAG.search(reason)` | 换回大小写敏感的 `"<block>" not in reason` | 2 |
| `driver.handle` 的 `inbound_format is ANTHROPIC_MESSAGES` | 换成 `if True` | 1 |
| `_TRANSCRIPT_OPEN` | 换成永不匹配的值 | 2 |
| `driver._answered_auto_mode` 读 `block_reason_str` 的那次 config 查找 | 换成字面量 | 1 |
| `classify` 的 `decision == "passthrough"` 短路 | 换成 `if False` | 2 |

最后两行是第二轮评审的产物：倒数第二条此前**不会**变红，那正是被发现的接线盲区。其中一个是把 `decision == "passthrough"` 的短路拆掉，两条测试变红，所以「默认关闭」是被守住的而不是碰巧成立的。脚本一次性，未收编

## 第二轮评审（配置改动，2026-08-23）

三次配置改动（`d6edd1a` 改名+标量化、`2ba08e2` 结构化、`4087a86` M2 降常量）当时**未经评审**，事后补做两轮独立评审：`reports/260823-review-2-claude.md`、`reports/260823-review-2-gpt.md`。

**核心结论：零回归。** 第一轮修好的八个缺陷（severity 双信号判别、severity 分值 >100、`<block>` 大小写过滤、入口格式边界、结构门槛先行、ECMAScript 语义转写、`request.succeeded`、删除被证伪的一般性承诺）在当前 HEAD 上**全部仍修着**，两份报告各自给出行号证据，异源那份还逐条构造输入实跑验证。

异源评审另有一条反向验证值得记：实测 2.1.241 里 block 模式的 `## Output Format` 全文**不含 `<severity>` 标签形态**，所以「system 文本含 `<severity>` 即判 severity 协议」这条修法在两个方向都成立，不会把 block 请求误判成 severity。

| 发现 | 报告编号 | 处置 |
|---|---|---|
| 配置里的 `block_reason_str` 到达输出这条**接线无测试保护**（改成硬编码后全绿） | gpt major-2 | **已修**，新增经 `handle()` 的接线测试，并加入常设变异集 |
| `block_reason_str` 的 schema 默认值与用户权威文件不一致（多一个 `configuration`） | gpt major-1 / claude minor-2 | **已修**，改为逐字一致 |
| `test_the_transcript_wrapper_is_not_a_setting` 对键名零鉴别力 | 两份独立发现 | **已修**，改为断言 `model_fields` 集合 |
| `< block >no` 参数用例恒绿 | gpt minor | **已删**，并写明为何它证明不了任何事 |
| M2 降常量的论证有一条腿不具鉴别力；且丢失了单独关闭能力 | claude minor-3 | **已修措辞**，代价记入 `deferred.md` D6 |
| `_matches_transcript_wrapper` 死守卫 + 过期 docstring | claude nit-4 | **已修** |
| `status.md` 标量时代残留 | gpt minor | **已修** |

未采纳的：claude nit-1（`test_either_marker_survives_the_other_being_reworded` 上半重复）保留——它与下半分别覆盖两条标记各自失效的方向，读起来对称，删掉省不了什么。nit-2/nit-3（空行数、单行长度）不改，本项目无此格式约定且已裁决禁用 `ruff format`。

## 评审处置表

两轮独立评审：`reports/260823-review-gpt.md`（异源，6 blocker + 2 major）、`reports/260823-review-claude.md`（同源，0 blocker + 5 major + 6 minor + 3 nit）。两者**独立发现了同样的四个核心缺陷**，这是本次最强的证据信号。

| 发现 | 两报告编号 | 处置 | 说明 |
|---|---|---|---|
| severity 协议只读 `stop_sequences`，阶段 2 误判 | B-01 / major-1 | **已修** | `_protocol_of` 增读 system 文本里的 `<severity>` |
| severity `100` 被阈值 `100` 读成 allow | A-04 / major-2 | **已修** | 改 `101`，理由写进 `spec.md` §5.1 |
| `reason` 过滤大小写敏感 | A-03 / major-3 | **已修** | 改用 `/i` 正则，与客户端 `/gi` 对齐 |
| 短路无入口格式边界 | B-06 / major-4 | **已修** | 加 `inbound_format is ANTHROPIC_MESSAGES` |
| 四处写下被证伪的失效承诺 | — / major-5 | **已修** | 四处措辞改写，并补上「服务端 dynamic config」这条无版本号的失效通道 |
| 测试 parser 与 JS 在 ASCII 外不等价 | A-02 / minor-3 | **已修** | `re.ASCII`、`[0-9]`、显式 ECMAScript `\s` 集合；三处实测反例固化为测试 |
| 谓词可劫持普通请求 | B-05 / **判不成立** | **采纳 gpt，加结构门槛** | 裁决理由见下 |
| P1 应收回 `system[0]` | B-05 半条 / minor-1 判不成立 | **采纳 claude，不收回** | 客户端 `forceAttributionHeader` 会把归因塞进 `system[0]`，收回反而漏判。改的是 spec |
| spec 里 P2 的证据是循环论证 | — / minor-2 | **已修** | spec §3 补上非循环链：M2 ⊆ M1 ⊆ 分类器 |
| 客户端把常量答复显示成模型判定 | — / minor-6 | **已修** | spec §2 与用户文档候选各补一条 |
| `log_hit` 字节数是重新序列化 | — / nit-1 | **已修措辞** | 收到的字节长度没留存，重新序列化是唯一低成本选择；docstring 不再声称它是 wire 长度 |
| `parses_as_severity` 漏了 `QRl` 的 stop_reason 闸门 | — / nit-2 | **已修** | 新增 `severity_of_reply` 收 body |
| severity 从未走过 `handle()` | — / nit-3 | **已修** | 新增端到端用例，且它正是 B-01 的回归防线 |
| 本地成功不发 `request.succeeded` | C-01 / minor-5 | **已修** | 短路路径发布该事件；attempt 级事件仍不发（没有上游腿） |
| 合成回复被记成 HTTP/1.1 上游交换 | C-02 / minor-4 | **未修，见 `deferred.md`** | 既有缺陷，`_answered_failed_search` 同形 |

### 一处采纳了「被判不成立」的发现

gpt 报告的 B-05（谓词可劫持普通请求）被 claude 报告明确判为**不成立**，理由是那些反例需要刻意构造，而项目规则反对为想象的攻击者加防护。

**仍然采纳并加了结构门槛**，理由与两份报告都不同：

1. 这里防的不是攻击者，是**误伤**。「用户发了一个最后一条消息首块恰为 `<transcript>\n` 的请求」是正常使用（「总结下面的转录」），不是攻击。`no-imagined-security-theater` 针对的是想象的威胁，不是正常使用下的功能错误。
2. claude 论证 M2 的精度靠「M2 ⊆ M1 ⊆ 分类器」传递，而这条链**只在 Claude Code 发出的流量语料里成立**。本代理服务任何 Anthropic 客户端，语料的排他性不能外推到语料之外。
3. 代价接近零：真实分类器请求 100% 满足那三项结构条件，它们本来就是从真实样本读出来的。

失败模式的不对称是决定性的：误伤一次，用户的真实请求被静默替换成一句伪造的决定，**用户看不到**；而门槛过严只会漏判，代价是省不下那 710 KB。

### 一处两报告都提了、我判为超范围

C-02（合成回复被记账成一次真实上游交换）成立，但它是**既有缺陷**：`_answered_failed_search` 走的是同一形状，本改动只是又加了一条同样的路径。修它要跨 observability 层并一并修两条路径，属于独立工作项，记入 `deferred.md` 而不是塞进本次。

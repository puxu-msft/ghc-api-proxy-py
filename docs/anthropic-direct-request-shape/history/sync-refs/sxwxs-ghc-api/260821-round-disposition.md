# 本轮六项任务的处置与待裁决事项

- 日期：2026-08-21
- 落地提交：`a07f74a`（损失出口 + attribution 剥离）、`955bc58`（thinking → effort）、`ae472f3`（端到端测试）、`408e3fc`（两轮评审的修复）
- 评审：`260821-review-reasoning-effort.md`（另一名评审员因 harness 限制未落盘，结论转录于 §4）、`260821-review-losses-attribution.md`
- 实测：`260821-probe-upstream-sanitize-rules.md`（54 次真实上游调用）

## 1. 六项任务逐项状态

| # | 任务 | 状态 |
|---|---|---|
| 1 | 材料移入 `sync-refs/sxwxs-ghc-api/` | 完成。**期间出过一次错并已纠正**：通配符 `260821-*.md` 把并行会话的七份在飞文档一起搬走了，已移回 `.dev/docs/tmp/` 并修好两处引用 |
| 2 | 翻译损失的持久指标存储，SQLite 是否合适 | 已答并已落地。详见 `260821-answer-loss-persistence.md` |
| 3 | thinking 请求参数在活链路落地 | 完成 |
| 4 | 验证 empty tool description 非法后剥离 | **前提已被实测证否，剥离未做**。见 §2 |
| 5 | 在 endpoint 解析后、路由前剥离 attribution | 完成 |
| 6 | 核对人写文档里那部分理解是否正确 | 完成。**用户的核心断言不成立**。见 §3 |

## 2. 第 4 项：前提被证否，未执行剥离

任务原文是「**验证** empty tool description 真的非法，**然后**剥离该情形」。验证做了，结论是**合法**：

| 形状 | Responses 上游 |
|---|---|
| `description` 键完全不存在 | 200 |
| `description: ""` | 200 |
| `description: "   "` | 200 |
| `description: null` | 200 |
| `description: 123`（整数） | **400** `{"error":{"message":"Invalid type for 'tools[0].description': expected a string, but got an integer instead.","code":"invalid_request_body"}}` |

跨 `gpt-5.6-terra` / `gpt-5.5` / `gpt-5.6-luna` / `grok-4.6` 四个模型一致；空 description 的工具在 `tool_choice` 强制调用下参数依然正确；Anthropic 直连路径同样接受。

所以「然后剥离」的条件没有满足，我没有执行。第三方 ghc-api 之所以做这件事，很可能是针对某个更早的网关行为或别的端点——它的注释只说「Copilot's /responses rejects a tool whose description is present but empty」，没有留下证据。

**但实测顺带暴露了一个真实缺口**：`description` 为非字符串非 `null`（整数、对象等）时上游会 400，而我方 `_function_tool` 原样透传。这是一个有实测依据、修复成本很低的兼容性问题，但它不是任务 4 说的那件事，所以**没有擅自做**——请裁决是否要修。

## 3. 第 6 项：用户理解的核对结果

对照 `docs/.human-controlled/message-format-sanitize.md` 的「总是剥离 attribution header」一节：

| 文档的陈述 | 核对结果 |
|---|---|
| Claude Code 把 attribution header 放在请求体 `system[0]`，形如 `x-anthropic-billing-header: cc_version=…; cc_entrypoint=…;` | **成立**（该形状被用作探针输入，形态无误） |
| 「GHC API 不认，需要剥离」 | **不成立**。15 个变体全部 200：这个名字、别的属性名、真 HTTP 头名 `Content-Type:`、在 `instructions` 里、在 `system[0]` 文本块里、独立成块、纯字符串 `system`、带 `cache_control`、流式、作为真实 HTTP 请求头、以及 `count_tokens`——没有一种被拒 |
| 处置：路由前剥离整个属性行，剥离后 `system[0]` 为空或纯空白则删除该项 | **已按此实现** |
| 早期旧版通过 HTTP 头 `x-anthropic-billing-header` 发送，现已不再使用 | **未验证**（这是客户端历史，探针不覆盖）。但实测确认 HTTP 头形态即使发出去上游也接受 |
| `CLAUDE_CODE_ATTRIBUTION_HEADER=0` 可以关掉 | **未验证**（客户端行为） |

### 文档里那个 TODO 的答案

> TODO：用户想知道 GHC API 不认 `x-anthropic-billing-header:` 还是 GHC API 不认 `system[0]` 中的任何 attribution？

**都不是，两个都认。** 不是不认特定名字，不是不认任何 attribution 行，也不是不认 HTTP 头形态。

### 剥离仍然值得做，但依据要换

原依据（上游拒收）不成立，两条新依据成立：

1. **token 净损耗**，实测 34 token/请求（`count_tokens` 端点：同一段 system，无此行 43 token，有此行 77 token）。Claude Code 每个请求都带它。
2. **prompt 卫生**：这行文本原样进入模型上下文，是一行与任务无关的伪 HTTP 头。它对模型行为的**实际影响本轮未能测得**——探针的 prompt 都是 trivial 的，「200 且返回 PONG」支撑不了「对模型无害」，更支撑不了「有害」。

代码与提交信息已按新依据写，并明确标注这不是兼容性修复。**`message-format-sanitize.md` 第 25 行的前提句需要修正**，但那是用户亲笔文档，我没有改。

## 4. 评审发现的处置

两轮异源评审共 27 条发现，无「阻断」。

### 已采纳并修复（`408e3fc`）

| 发现 | 处置 |
|---|---|
| attribution 正则误删 23 条候选中的 21 条真实 prompt 首行 | **最重的一条**。判据收紧为「`x-` 前缀 **或** `k=v;` 参数串值」，21 条全部作为回归样本写入测试 |
| count 路径的测试删掉接线仍通过 | 改为从它记录的 loss 读取 resolution；已用变异验证会红 |
| ladder 测试删掉 `max` 仍通过（两边同时收缩） | 每一档钉到具体输入 |
| `_dispatch` 第五个持有 context 的 return 漏收集损失 | 补上；docstring 改为陈述规则而非会漂的数字 |
| `thinking` 被 reader 认领后，未读字段与同格式往返都静默丢失 | 未读字段记 loss；`to_anthropic_messages` 重建 `thinking` |
| 计数器按 loss 条数计（一次带截图的请求 +30） | 改为每请求每 code 计一次 |
| 三处注释声称超出实现（console line 显示 losses、downstream 完全看不到 attribution、解析出的 body 保持原样） | 三处均改为陈述实现 |
| lossless 测试用未翻译路由，是构造性绿 | 改用会翻译但无损的路由 |

### 未采纳，记录理由

| 发现 | 不采纳的理由 |
|---|---|
| 剥离只看 `system[0]`，其余位置一律漏 | **符合人写文档的规约**（它明确只说 `system[0]`）。已把过宽的注释改成陈述实现范围。扩大作用域需要用户先扩大规约 |
| 损失逐块记录，实测单请求 30 条 / 4106 字节进 JSONL | 明细的价值就在于逐条；截断会让「丢了 30 个块」和「丢了 3 个块」同形。体积（约 4KB/请求上限形态）在 14 天保留下可接受。若日后成为问题，正确的做法是在取证库那一层分页，而不是在源头丢信息 |
| `resolve` 在目录出现 ladder 之外的新档位时不会选它 | fail-safe：不认识的名字不发，比猜一个安全。已在注释说明 |
| desired 低于所有支持档时会向上取最低档 | 这是无法避免的：`disabled` 对一个最低只有 `medium` 的模型没有向下选项，而不发等于拿到上游默认值。已记为 approximation 并在注释里说明这是唯一会向上的路径（原注释只写了「向下」，是不准确的） |
| 未做「从 legacy 提升共享 policy leaf」（设计方案的候选 C） | legacy 那套是 band-based，为 Claude 模型的 `min/max_thinking_budget` 设计；真实 Responses 模型**不发布这两个字段**，所以那套算法对本路径会因 bands 为空而拒绝 enabled/adaptive。提升一个不适用的算法会造成错误复用。新写的 resolver 面向 effort 枚举，约 60 行 |

## 5. 待用户裁决

1. **`message-format-sanitize.md` 第 25 行的前提句**与实测不符（上游并不拒收）。文档是用户亲笔，我未改动。剥离行为本身已按 token 损耗这一新依据实现。
2. **attribution 判据的宽度**。文档说「不仅是 `x-anthropic-billing-header`」，我取了最窄且仍满足这句话的读法（`x-` 前缀，或 `k=v;` 值）。是否要更宽或更窄，取决于「不仅是」的本意。
3. **`hook_strip_anthropic_request_headers.strip_attribution_header` 配置项**。文档说这应当常驻，所以实现不读它——**于是这个配置项现在设成 `false` 也不生效**，比原来的空转更糟。请裁决：删掉它，还是让实现读它（默认 `true` 即常驻效果）。同一节的 `beta_strip_headers` 仍然完全没有实现。
4. **`description` 为非字符串时的 400**（§2 末）。要不要修。
5. **`config.example.yaml` 与 schema 的键名不一致**：文件里是 `strip_anthropic_beta_flags`，schema 里是 `beta_strip_headers`，导致 `test_authoritative_example_config_parses` 一直红。这个失败**先于本轮工作存在**，且 `config/schema.py` 正被并行会话修改，我没有碰。
6. **thinking 映射的产品参数**（设计文档 §9 列了 13 项，我按下列默认实现，均可推翻）：budget 阈值 3000/8000/16000/30000；`adaptive` → `high`；不支持时向下取；`disabled` 在无 `none` 的模型上取最低档并记 approximation；目录未发布 effort 时不发 `reasoning` 并记 not-carried；不引入配置项。
7. **原始客户端请求的取证留存**。文档要求「历史记录中的原始客户端请求不应受此处理影响」，但新链路上没有保存原始 body 的地方——`repair_tool_pairs` 在剥离之后一步就地改写了 `messages`。要现在给 `RequestContext` 加一个 `original_payload`，还是记入 deferred。

## 6. 顺带发现（超出本轮范围）

**`claude-sonnet-5` 不支持 Responses API**：`{"error":{"message":"model claude-sonnet-5 does not support Responses API.","code":"unsupported_api_for_model"}}`。这意味着「Anthropic Messages → OpenAI Responses」的翻译路径承载不了 Claude 系模型，它们只能走 `/v1/messages` 直连。本轮未验证其他 Claude 型号，建议单独立项。

# 档案：词元用量的换算

从「日志行里缓存分段没显示」查起，最后修掉的是一个**下游契约缺陷**。2026-08-20。

## 一、症状与真正的问题

用户看到（Anthropic Messages 入站 → OpenAI Responses 上游，流式）：

```
[ OK ] 09:02:14 H1/H2 200 anthropic-messages/gpt-5.6-sol 51.6s ↑964.6KB ↓475.4KB ↑135.5k ↓2.7k function_call(Write) reason(enc:5)
```

`↑135.5k` 后面没有缓存分段，也没有 `↻` 命中率——用户的描述是「TUI 信息残缺」。

**但少显示字段是小事。** 两边对 `input_tokens` 的定义是相反的：

| | `input_tokens` 的含义 |
|---|---|
| OpenAI Responses | 输入总量，**包含**从缓存读取的部分（明细在 `input_tokens_details.cached_tokens`） |
| Anthropic | 新发出的输入，**不含**缓存读取（缓存另计 `cache_read_input_tokens`） |

所以把 Responses 的 usage 按 Anthropic 的键去读，不只是丢字段——**一个 97% 命中缓存的轮次被显示成全价轮次**。上面那行真实的构成是 3.5k 新输入 + 135.0k 缓存命中。

## 二、根因与两次修复

### 第一次（`eb93215`）：流式路径

`ResponsesAssembler._read_terminal` 把 Responses 的 usage 原样存进 `Terminal.usage`，而这条记录的所有读者都按 Anthropic 的键读。

修法：复用 `protocols/responses_anthropic.py` 里**已经存在**的换算（它会做减法，并记录不一致事实），导出为公开的 `anthropic_usage_from_responses()`。**没有重写第二份减法**——减法是承重部分，两份拷贝一定会漂移。

### 第二次（`1ac5ab2`）：缓冲路径，以及第一次造成的不对称

这一次的提交信息里我写了「缓冲路径已经换算过」。**这句话是错的。** 它只对旧的 `app.anthropic.client` 路径成立，不对当前 `pipeline_app` 实际走的路径成立。

评审指出后独立复现，看的是**客户端实际收到的响应体**：

```json
{"input_tokens": 138500, "input_tokens_details": {...}, "output_tokens": 2700, "total_tokens": 141200}
```

这不是日志问题，是**下游契约被破坏**：Anthropic 客户端拿到自己没有 schema 的键，没有 `cache_read_input_tokens`，而 `input_tokens` 的含义与它的理解相反。

而且第一次修复**制造了不对称**：`stream.py` 发的是换算后的 usage，非流式仍逐字透传——同一路由只因 `stream` 开关不同就给出两套 usage 契约。

修法：在 `from_openai_responses_response` 复用同一个换算。格式非法时留空而非透传原形状，与流式路径同姿态。

## 三、异常处理的取舍

换算函数在 usage 格式非法时抛 `ResponseConversionError`。两处调用点都**捕获并返回空**，不向上传播。

理由：流式那处跑在流的终结事件上，那时块已经发出去了；缓冲那处的回复本身完整合法。**为了一个没人在等的计数中断一个已交付的响应，是拿答案换它的账单。** 透传原始形状则会把客户端读不懂的结构放回去，更糟。

代价（已记入 `../deferred.md` 第 0.5 条，**未做**）：

- 换算的副产物 `ResponseConversionFact`（`usage_inconsistent`）与 `ResponseUsageFacts`（含 `reasoning_tokens`、上游原始 totals）被丢弃。于是上游报了自相矛盾的 usage 时，管线照常给出看起来正常的数字（`max(0, ...)` 兜住了），而没有任何地方说明它来自矛盾输入。
- 运行时没有信号，「上游没报 usage」与「上游报了坏数据」在日志上完全一样，异常自带的 `code` 与 `field_path` 被丢掉。

不做的理由：修法要么把 facts 挂到某处再由有 request context 的层消费（独立切片），要么在 pipeline 层直接打日志——而当前 `src/app/pipeline/` 下**没有任何模块** import `app.observability.logging`，为一个 minor 引入这个依赖方向不划算。

## 四、录制的证据（这一块最有价值的部分）

判据依赖「上游 usage 的真实字段结构」，所以不能用手写 fixture 定案。仓库既有 cassette 给出的真实数据：

| cassette | `input_tokens` | `cached_tokens` | `cache_write_tokens` |
|---|---|---|---|
| `responses_web_search_stream` | 4693 | 3712 | 0 |
| `history_responses_stream` | 56919 | 55680 | **键不存在** |
| `anthropic_to_responses_stream` | 12 | 0 | 0 |

这组数据证明了手写 fixture 证明不了的两件事：

1. `input_tokens` 确实**含**缓存（4693 里 3712 是命中的）；
2. `cache_write_tokens` **可能整个缺席**——所以换算对缺键取 0 是对的，不是偷懒。

推论：真实流量里 cache write 恒为 0，因此 `↻hit%` 后面的 `+new%` 不出现是**符合上游实际**，不是缺陷。若上游今后在流式终结事件里报非零 `cache_write_tokens`，现有换算与渲染都会显示它，无需为了凑出 `+new%` 伪造 cache creation。

基于录制的断言在 `tests/integration/test_history_fixtures.py`。

### 检索 cassette 的坑

第一次用纯文本 `grep` 搜 `cached_tokens` **搜不到**，我一度以为评审说错了。实际是 cassette 的 chunk 存成 `{"text": ...}` 结构，纯文本检索命中不了。**这是我的检索方式错了，不是数据没有。** 要按结构解析。

另一处同源的教训：写那条录制断言时我把 `output_tokens` 凭印象写成 218，录制里是 637。输入侧三项一次命中说明换算正确，而那个错数字恰好演示了手写期望值的风险——与这一整节要说的是同一件事。

当时的评审报告原件：`reports/260820-review-translated-usage-and-colour.md`（它同时覆盖着色，那部分的重写在 `../archive-request-log/`）。

## 五、遗留

- `../deferred.md` 第 0.5 条：诊断信号无落点（见上）。
- `../deferred.md` 第 0 条：`/responses` 入站的回复汇总为空，其中就包括 usage。
- 推理词元（`output_tokens_details.reasoning_tokens`）目前不显示。Responses 的 `output_tokens` **包含**它，所以 `↓2.7k` 不算错，只是没拆开。Anthropic 的 usage 没有这个字段，要显示就得新增一列——**未向用户提出裁决**，此处记录以免被当成疏漏。

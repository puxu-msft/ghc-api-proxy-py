# 客户端腿的格式与交付

**这个主题管什么**：客户端用哪种协议问，回复就用哪种协议答——以及这件事在 `src/app/pipeline/delivery/` 里是怎么落地的。

用户 2026-08-22 在这一片下了四条裁决 + 一条命名裁决，此前它们只活在提交信息里。本文是当前状态的权威；分项调查与评审报告在 `reports/`，它们是时点记录，不要拿来当现状对账。

## 一、两条腿，两个契约

一次请求有**两条腿**，它们是不同的格式，判定它们的函数也不同：

| | 问的是什么 | 由谁回答 | 代码 |
|---|---|---|---|
| **上游腿** | 是哪个上游答的 | `dialect_for` → `assembler_for` | `server/handler.py` |
| **客户端腿** | 客户端在哪种协议里问的 | `route.inbound_format` → `framer_for` | `server/handler.py` |

**主产品路径上这两者不同**：请求以 Anthropic Messages 进来、由 Responses 上游服务，于是用 **Responses 的 assembler** 读、用 **Anthropic 的 framer** 写。

> ⚠️ **成帧器绝不能按 `dialect_for` 选。** 那样会让主路径开始向 Claude Code 发 `response.*` 事件。这条有两条 int 测试守着，变异验证过：把 `framer_for` 换成 `dialect_for`，两条都变红。

## 二、每种客户端腿现在怎么答

| 入站格式 | 出站 | 依据 |
|---|---|---|
| Anthropic Messages | `AnthropicFramer`，块级 | 既有行为 |
| OpenAI Responses | `ResponsesFramer`，块级 `response.*` | 用户 2026-08-22 裁决 |
| OpenAI Chat Completions | **一次性交付**：整段缓冲后原样转发 | 用户 2026-08-22 裁决 |

Chat Completions 走一次性交付的原因：它的块边界藏在 `choices[].delta` 里，本项目没有任何东西读它。在此之前那些字节进了 `AnthropicAssembler`，一个事件名都匹配不上，客户端拿到 **200 + 0 字节 + 没有错误帧**。用户裁定「先缓冲，边界解析留待未来」。

`delivers_blocks` 判的就是「这条客户端腿有没有出站成帧器」；`framer_for` 返回 `None` 即走一次性交付。

## 三、`ResponsesFramer` 的几个非显然处

都是实测逼出来的，改动前先读理由：

- **`output_index` 自己重编号**，不用 `CompletedBlock.index`。后者来自 assembler 的计数器，而它对被丢弃的 item 也会前进；SDK 直接按下标取 `snapshot.output`，空洞就是 `IndexError`。
- **id 一律自铸，不转发上游的**。实测三份 Responses 流式录制：每个事件里的每个 id 字段两两互不相同（12/12、16/16、125/125），`response.id` 在 created/in_progress/completed 三处都不同。唯一必须原样转发的是 `function_call.call_id`——客户端要用它回填。
- **usage 取 `Terminal.upstream_usage`**，不是 `Terminal.usage`。后者已经过 Anthropic 化转换（减掉缓存部分、丢弃 `reasoning_tokens`），反向再转一次是两次有损转换的复合。
- **截断发 `response.incomplete`**，与 `response.completed` 互斥。SDK 只从后者填最终响应，所以截断的流拿不到 `get_final_response()`——真实上游也是这个行为。

## 四、包的结构：通用 vs 特定格式

用户 2026-08-22 裁定「应该平等、正确区分通用、特定格式的」，形状如下：

```
delivery/
  blocks.py  sse_frame.py  sse_source.py    # 通用：块，与线信封（写/读）
  assembling.py  framing.py                 # 通用：入站/出站两个契约
  stream.py                                 # 通用：交付循环
  formats/
    anthropic_messages.py                   # 该格式的 assembler + framer
    anthropic_messages_synthetic_reply.py   # 该格式的合成回复
    openai_responses.py                     # 该格式的 assembler + framer
```

规矩：**通用件不带格式名；只服务一种格式的东西一律以该格式为前缀，并说明它产出什么。** 两个格式模块互不导入。

「说明产出什么」这半条是 2026-08-22 补的。`anthropic_messages_synthetic` 说了格式却漏了名词——这个包在不同尺度上合成好几种东西（一整条回复、一个块、消息内部的一个标记），光说「合成的」等于只说了它会合成。也不按住户命名：搜索跑不了只是当前唯一的住户，模块存在的理由是通用的（见下）。

改之前的三类错配（都已消除）：`SseFrame` 这个两边共用的线信封住在 Anthropic 模块里，逼得 Responses 从它导入；`assembler.py` 名字通用却混放两种实现；`synthetic.py` 名字通用却只写 Anthropic。另外 `"tool_use"` 曾在三处各定义一次，现在只在 `blocks.py`。

## 四·五、「合成」是一个类别，不是一次特例

`anthropic_messages_synthetic_reply` 存在的理由，不是「搜索会失败」，而是：**代理无法转发一个请求时，在客户端协议内自答，比在传输层失败得到的客户端行为更好。** 实测依据——Claude Code 把 HTTP 错误当传输问题重试三次，而跑不起来的搜索不会在第三次开始工作；一个失败的**工具**则不会被重试。

这个类别**已经有第二个成员**，只是尺度不同、因而不在这个模块里：`ContinuationSupport.synthesize` 合成的是单个 `tool_use` **块**，用来把完不成的回合交还客户端——也就是 `docs/.human-controlled/upstream-retry-and-continuation.md` 里的「MCP-driven 合成续写」。

它留在原地是有理由的，别急着搬：它的主体是**请求策略**（客户端有没有声明那个工具、失败归到哪个类别、还有一个待用户命名的暂定值），只有末尾几行是这个格式的形状；搬进格式模块会把策略一起拖过去。等第二个整条回复出现、或那个类别被命名之后，再看要不要收拢。

「合成」是项目自己的词，与推理载体、`assistant_message_layout` 里的用法同义——**代理造出来的，不是从上游收到的**。2026-08-22 一份评审曾把它报为「三处重名」，那是错的：那是同一个意思的多个实例。

## 五、这一片之外，同日的三条裁决

- **base URL 只有两条路**：按订阅探测（`composition.resolve_provider_base_urls`），或在 `model_providers.<name>.api_base_url` 手写完整 URL。**不设 `account_type` 配置项**。已配置就不探测。
- **探测失败**：401/403 上抛（凭据不对，后续每个请求都会被拒）；其余 HTTP 状态与传输类失败记 warning 后继续。理由是 socket activation 下旧进程已交出 listener，因一次 GitHub 抖动起不来是服务中断。
- **copilot token 无后台刷新循环**，只有 `get_token()` 的懒刷新。原循环只从 legacy app factory 启动，在实际服务的链路上从未跑过。
- `--ghc-api-base-url` 已删除——它因字段改名遗漏，写的是不存在的字段名，是静默空操作。
- `--account-type` 随后一并删除（用户 2026-08-22 裁决）。它写进 legacy `AppSettings.auth`，而 `app_factory` 在 `src/` 下零调用者，服务的那条链读不到它。两者同族，只删一个会让处置无从解释。

## 目录

- `deferred.md` — 本轮已知但未做的缺口与怪味
- `reports/` — 分项调查、探针、评审的原件（时点记录）

## 已完成的清理记录

以下 18 条于 2026-08-27 从 `deferred.md` 迁入。逐项对照当前 `src/` 或对应测试后仍成立；原文未压缩。另有两条因当前源码不支持原来的完成声明而留在台账中等待文档对账。

**2026-08-22 第三批**：

- U-4 `anthropic_messages_synthetic.py` → `anthropic_messages_synthetic_reply.py` —— `1c91870`。定案理由见 README 第四·五节：不按住户（`failed_search`）命名，因为模块存在的理由是通用的；保留「合成」，因为那是项目自己的词，评审报的「三处重名」是误判。`ContinuationSupport.synthesize` 不搬。

**2026-08-22 第二批**（用户裁决「缺陷类问题都要修复」之后）：

- U-2 删除 `--account-type` —— `e7cf57a`
- U-3 `stream_delivery` 的 framer 改为必填，`signature_compat` 从 `StreamSettings` 移到成帧器 —— `800eb5b`
- D-1 未识别的 stop reason 不再进 `incomplete_details.reason`（改为正向映射表，无合法拼法即 null）—— `75273e1`
- D-2 未知 block kind 当场 `raise`，不再静默降级成空 message item —— `75273e1`
- D-3 `Terminal.upstream_usage` 默认值由 `{}` 改为 `None`，「没观测」与「观测到空」分开 —— `75273e1`
- D-4 `refresh_in` 不再解析、不再必填 —— `1d1e45b`
- D-6 守卫触发时交出已缓冲的字节再抛 —— `800eb5b`；新增 `test_one_shot_delivery.py`，此前该路径零覆盖
- n-2 保活测试改为断言线上的序号，而不是只断言注释帧的字节 —— `57d5b0e`
- n-3 `pytest.raises(Exception)` 收窄为 `httpx2.HTTPStatusError` —— `1d1e45b`
- n-4 `resolve_provider_base_urls` 的返回值改走 `model_validate` —— `285af55`
- n-5 `stream_settings(chain)` 每请求只读一次 —— `800eb5b`

**第一批**：

- `response.function_call_arguments.done` 缺 SDK 必填的 `name`、两个 `output_text` 事件缺 `logprobs` —— `db6f549`
- `incomplete` 透传进 `incomplete_details.reason` —— `db6f549`
- reasoning docstring 声称「照三份录制抄」而实际 summary 全为空 —— `db6f549`
- 一次性交付路径自称「以同样方式收尾」 —— `db6f549`
- `openai_responses.py` docstring 里的陈旧模块名、两处 `__init__` 的「一个格式一个模块」 —— `3e70ee8`
- 语料基数写成「三份 cassette」而仓库有五份 —— 本轮

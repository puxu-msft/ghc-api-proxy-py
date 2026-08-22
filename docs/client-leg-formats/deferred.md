# 待办与已知缺口

来源：两份评审（`reports/260822-four-rulings-implementation-review.md`、`reports/260822-delivery-restructure-review.md`）逐条处置后的剩余项，加上按 `project-review-principles` 复查跑出来的。

**分类口径**（沿用 `delivery-keepalive/deferred.md`）：「缺陷」= 正确做法唯一，排期做掉即可；「裁决」= 存在真实岔路，不同选择导向不同产品行为或代价，归用户。

---

## 归用户裁决

### U-1 没有带 `function_call` 的 Responses 流式录制

`formats/openai_responses.py` 的 `_function_call` 那组帧、以及 reasoning item 的 `summary_text` 形状，都是**据 openai SDK 3.3.1 的类型与解析器推出来的，不是从录制读的**。仓库五份 cassette 一份都没有 `function_call`。

代码里已如实声明。补录要用凭据、发真实上游请求（`tests/int/recorded/record_cassette.py`），未擅自执行。

**不补的代价**：那组帧的形状只由 SDK 类型担保。SDK 的 `construct_type` 是宽松构造，不校验——所以缺字段在当前 oracle 下不可见。已加一条「逐事件对账 SDK 必填字段」的测试兜住这一层（`test_openai_responses_format.py`），但它管不了「字段齐全而语义错」。



### U-4 `synthetic` 一词在仓库里指三件事

`formats/anthropic_messages_synthetic.py`（搜索失败时合成的回复）、`handler.HandledRequest.synthesized`（整条回复由本代理写）、`stream.ContinuationSupport.synthesize`（流中途合成工具调用收尾）。本轮只给第一个加了格式前缀，没碰这层歧义。

---

## 小项

- **n-1** `response.id` 是裸 UUID，没有 `resp_` 前缀。上游真实值是 416 字符的 base64 串，我们本来就不模仿它；但 OpenAI 生态里 `resp_` 前缀是惯例。未修：它是兼容性口味问题，不是缺陷，改不改取决于要不要迁就按前缀识别 id 的客户端。

## 已在本轮修掉的（不要重复处理）

**2026-08-22 第二批**（用户裁决「缺陷类问题都要修复」之后）：

- U-2 删除 `--account-type` —— `e7cf57a`
- U-3 `stream_delivery` 的 framer 改为必填，`signature_compat` 从 `StreamSettings` 移到成帧器 —— `2afa0c4`
- D-1 未识别的 stop reason 不再进 `incomplete_details.reason`（改为正向映射表，无合法拼法即 null）—— `75273e1`
- D-2 未知 block kind 当场 `raise`，不再静默降级成空 message item —— `75273e1`
- D-3 `Terminal.upstream_usage` 默认值由 `{}` 改为 `None`，「没观测」与「观测到空」分开 —— `75273e1`
- D-4 `refresh_in` 不再解析、不再必填 —— `1d1e45b`
- D-5 一次性交付的前提写成断言（路由被翻译过就 raise）—— `2afa0c4`
- D-6 守卫触发时交出已缓冲的字节再抛 —— `2afa0c4`；新增 `test_one_shot_delivery.py`，此前该路径零覆盖
- n-2 保活测试改为断言线上的序号，而不是只断言注释帧的字节 —— `8ce22b9`
- n-3 `pytest.raises(Exception)` 收窄为 `httpx2.HTTPStatusError` —— `1d1e45b`
- n-4 `resolve_provider_base_urls` 的返回值改走 `model_validate` —— `285af55`
- n-5 `stream_settings(chain)` 每请求只读一次 —— `2afa0c4`

**第一批**：

- `response.function_call_arguments.done` 缺 SDK 必填的 `name`、两个 `output_text` 事件缺 `logprobs` —— `db6f549`
- `incomplete` 透传进 `incomplete_details.reason` —— `db6f549`
- reasoning docstring 声称「照三份录制抄」而实际 summary 全为空 —— `db6f549`
- 一次性交付路径自称「以同样方式收尾」 —— `db6f549`
- 启动期探测失败一律阻止启动 —— `44fa576`（用户裁决后）
- `openai_responses.py` docstring 里的陈旧模块名、两处 `__init__` 的「一个格式一个模块」 —— `3e70ee8`
- 语料基数写成「三份 cassette」而仓库有五份 —— 本轮

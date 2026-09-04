# 待办与已知缺口

来源：两份评审（`reports/260822-four-rulings-implementation-review.md`、`reports/260822-delivery-restructure-review.md`）逐条处置后的剩余项，加上按 `project-review-principles` 复查跑出来的。

**分类口径**（沿用 `delivery-keepalive/deferred.md`）：「缺陷」= 正确做法唯一，排期做掉即可；「裁决」= 存在真实岔路，不同选择导向不同产品行为或代价，归用户。

---

## 归用户裁决

### U-1 没有带 `function_call` 的 Responses 流式录制

`formats/openai_responses.py` 的 `_function_call` 那组帧、以及 reasoning item 的 `summary_text` 形状，都是**据 openai SDK 3.3.1 的类型与解析器推出来的，不是从录制读的**。仓库五份 cassette 一份都没有 `function_call`。

代码里已如实声明。补录要用凭据、发真实上游请求（`tests/int/recorded/record_cassette.py`），未擅自执行。

**不补的代价**：那组帧的形状只由 SDK 类型担保。SDK 的 `construct_type` 是宽松构造，不校验——所以缺字段在当前 oracle 下不可见。已加一条「逐事件对账 SDK 必填字段」的测试兜住这一层（`test_openai_responses_format.py`），但它管不了「字段齐全而语义错」。




---

## 小项

- **n-1** `response.id` 是裸 UUID，没有 `resp_` 前缀。上游真实值是 416 字符的 base64 串，我们本来就不模仿它；但 OpenAI 生态里 `resp_` 前缀是惯例。未修：它是兼容性口味问题，不是缺陷，改不改取决于要不要迁就按前缀识别 id 的客户端。

## 报告建议关闭、但当前源码不支持原完成声明的

以下两条不是重新打开的产品功能，而是尚未完成的文档对账。2026-08-27 按 `../../tmp/260827-deferred-survey.md` 复核时，当前源码不支持原先的「已修掉」表述，因此没有迁入 `README.md` 的完成记录。

- **D-5 一次性交付的前提写成断言（路由被翻译过就 raise）——原记录指向 `800eb5b`。** 当前 `src/app/server/routes/inference.py` 的 `if framer is None:` 分支没有该断言；全 `src/` 搜索 `translation_required` 与 `raise`/`assert` 的组合也没有相符实现。需要核对这是后来重构时移除了守卫，还是前提已由别的构造性约束承接；核清前不按完成项处理。
- **启动期探测失败一律阻止启动——原记录指向 `44fa576`（用户裁决后）。** 当前源码明确不是「一律阻止」：`resolve_provider_base_urls()` 对 401/403 继续上抛，但对其它 HTTP 状态与 `httpx2.TransportError` 记 warning 后继续；`pipeline_app.py` 还会捕获 `refresh_catalogs()` 的异常并以 not-ready 状态启动。现行 `README.md` 第五节也记录了这一较窄行为。需要核对原记录被哪次后续裁决或改动取代；核清前不把这句作为完成事实迁出。

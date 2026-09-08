# 按 dialect 分档的下行字节阈值独立评审

## 结论

**Verdict：needs-fix。** 实现方向、查表方式和 `384KiB/4MiB` 数值均可保留；没有发现按 dialect 取阈值的运行时行为缺陷，也没有发现遗漏的着色调用点。合入前必须收窄 `request_log.py` 与新增测试说明中的因果断言，因为“每个事件都有 item id”“每个输出 token 一个事件且不合批”“任意回复都有约 58KB 底噪”都强于现有证据，其中后两项已有直接反例。

我倾向保留 `384KiB`，不改成 `512KiB`。在 2026-08-21 12:33:22 UTC 的评审快照中，当前持续增长的数据集有 4,807 条记录，其中 4,752 条有整数 `bytes_out`；Responses 的 `384KiB/4MiB` 点亮率为 `9.10%/0.79%`，`512KiB/4MiB` 则为 `6.20%/0.79%`，而 Anthropic 的 `10KiB/100KiB` 为 `11.62%/0.05%`。`384KiB` 更接近“约 top decile”的 notable 语义，而且它是 `3 × 128KiB`，并不是难以解释的任意十进制数。证据强度：notable 档高，足以据此裁决；heavy 档只有 6 个 Responses 样本，属于可采用但不宜宣称精确标定的趋势证据。

更准确的判据不是“两个 dialect 的两个百分比逐项相等”，而是明确规定颜色语义为“notable 约 top decile，heavy 为极少数约 top percentile”。当前阈值满足这个定性形状；Anthropic heavy 只有 2 条，Responses heavy 有 6 条，`0.05%` 与 `0.79%` 并不构成精确匹配。无需因此改数值，但注释不应写成两个 share 已经相配，也不应写“only the share can carry that”；这是选择的判据，不是唯一可能的判据。

## 评审范围与基线

- 基线为 `/home/xp/src/ghc-api-proxy-py` 当前工作树，起始 `HEAD 172adc26f129b6f96317ed94178c602f93777cb6`。只裁改动文件 `/home/xp/src/ghc-api-proxy-py/src/app/observability/request_log.py` 与 `/home/xp/src/ghc-api-proxy-py/tests/unit/observability/test_request_log.py`；为核调用面与证据，只读检查了 `footer.py`、`tui.py`、`active_requests.py`、`pipeline_app.py`、原始抓包、cassette 和生产 JSONL。其他并行改动未纳入质量判断。
- 用户指定的 `my-skills:as-reviewer` 在本运行环境中未注册，调用返回 `Unknown skill`；本评审改用 `verifying-authoritative-claims` 与 `trusting-a-green-result` 的同类方法，逐条对齐命题、证据范围和测试分辨力。该工具缺失没有阻止完成评审。
- 生产数据文件在评审期间持续增长。上述 12:33:22 UTC 快照得到 Responses 旧阈值 `10KiB/100KiB` 的点亮率为 `98.94%/51.19%`，新阈值为 `9.10%/0.79%`；相对用户给出的旧快照 `98.8%/49.6%` 与 `9.8%/0.9%` 没有显著偏移。证据强度：高，足以确认“旧阈值几乎恒亮，新阈值恢复分辨力”。
- `uv run pytest tests/unit/observability/test_request_log.py` 为 `46 passed`；目标文件的 `ruff check` 与 `pyright` 均通过。扩大到 `tests/unit/observability` 时，收集被并行工作树中的 `ModuleNotFoundError: httpx_ws` 阻断；该错误经过 `responses_ws.py`，不由本 diff 引入，因此不作为本改动的发现，也不能拿来确认实现者所述的另一轮 `101 passed`。

## 必须改

### M1．注释把“item 级事件”扩大成“每个 SSE 事件”，并把细粒度 delta 扩大成“一 token 一事件”

位置：`src/app/observability/request_log.py:38`、`tests/unit/observability/test_request_log.py:555`。

证据强度：高，直接解析指定的未脱敏抓包，足以要求修改。

`C2-responses-search-stream-response.txt` 有 16 个 SSE 事件。13 个 item 级事件各带一个 distinct 的 `item.id` 或 `item_id`，长度确实全部为 416 字节；另外 3 个 response 生命周期事件携带的是 `response.id`，不是 item id，且 `response.completed` 还在完整 output 中再带两个 item id。因此，“13 个 distinct item id 全为 416 字节”成立，“每个 SSE 事件都带 item_id”不成立。若想表达真正观察到的共同成本，应区分“item 级事件的 416 字节 item id”和“生命周期快照的 416 字节 response id”。

抓包中 3 个 `response.output_text.delta` 的完整 SSE frame 合计 1,960 字节，其中 item id 合计 1,248 字节，占 `63.67%`；真实 delta 文本合计 70 字节，占 `3.57%`。因此注释中的 `64%` 与 `3.6%` 数字成立，但必须注明它是这 3 个 delta frame 的聚合比例，而不是任意单个事件的固定比例。

“一 event per output token with no batching”有直接反例。该抓包只有 3 个 text delta，首个 delta 一次交付 45 个 UTF-8 字节的多词文本，而最终 usage 是 95 output tokens，其中 43 reasoning tokens；显然不是一 token 一事件。`history_responses_stream.json` 也只有 115 个 text delta，对应 637 output tokens，其中 516 reasoning tokens；即使只拿非 reasoning 的 121 个 token 比也不相等。可以说“text delta 很细，固定 ID 开销会在大量 delta 上重复”，不能说“一 token 一个且不合批”。

建议替换为类似事实范围：“在该抓包中，13 个 item 级事件各带一个 416-byte opaque item id；3 个 text delta frame 中这些 ID 占总字节的 63.7%，文本占 3.6%。Responses 以细粒度 delta 重复这项固定开销。”测试 docstring 无需复述完整因果链，只需说明生产分布导致同一阈值失去分辨力。

### M2．“约 58KB 是任意大小回复的固定底噪”把当前客户端工具集的观测扩大成协议恒量

位置：`src/app/observability/request_log.py:38`、`tests/unit/observability/test_request_log.py:567`。

证据强度：高，指定的两个 fixture 已足以证伪全称；生产短回复数据只支持带条件的窄结论。

三个 lifecycle snapshot 确实各自完整回显 `tools`。在 `history_responses_stream.json` 中，16-tool 数组以 wire 同款 compact JSON 序列化后每份是 7,853 字节，Python 默认带空格的序列化才是 8,530 字节；三份分别约 23.0KiB 或 25.0KiB。三个完整 snapshot chunk 合计 27,000 字节，整个 115-delta cassette 合计 53,710 字节。故“工具数组重复是重要固定成本”成立，但“它本身造成约 58KB”不成立。

更直接的反例是指定的 C2 抓包：它只声明一个 web-search tool，整个文件含说明头也只有 16,016 字节。因此“puts a floor near 58KB under a reply of any size at all”不是 Responses 协议事实。生产记录中 7～8 output tokens 的当前 GPT 请求确实落在 57,432～58,233 字节，支持的窄命题是：“在当前生产客户端所带的固定工具集和请求形状下，极短 GPT 回复也观测到约 58KB 基线。”这项基线会随 tool declarations、schema 大小和 Responses 事件形态改变。

同段的“the same reply still costs roughly forty times more”也没有同一语义回复跨两个上游的配对样本。当前生产样本的 median bytes/output-token 是 Responses `652.1` 对 Anthropic `10.6`，按输出 token 区间比较时约为 25～75 倍；这足以说“该生产分布中通常是数十倍”，不支持精确地说“同一回复约四十倍”。阈值选择并不依赖这个精确倍数，删掉或收窄它不会削弱设计理由。

### M3．点亮率说明把定性对齐写成精确匹配和唯一判据

位置：`src/app/observability/request_log.py:40`。

证据强度：高，用户快照自身已经显示 `9.8%/0.9%` 对 `11.8%/0.1%`，足以裁决文字强度。

notable share 对齐良好，heavy share 只是都很少，并没有逐项 matching；评审快照也得到 `9.10%/0.79%` 对 `11.62%/0.05%`。建议把“chosen so that its share ... matches”改成“chosen to restore the same qualitative shape: roughly the top decile is notable and fewer than one percent are heavy”，并把“only the share can carry that”改成“the display therefore uses path-relative frequency rather than a byte-ratio scaling”。这样仍完整说明设计选择，但不把经验判据写成唯一逻辑可能。

## 建议改

### S1．新增测试能抓回退旧阈值，但没有锁定两个新阈值的下边界

位置：`tests/unit/observability/test_request_log.py:552-572`。

证据强度：高，已做进程内、无持久副作用的正控，足以据此补两个边界断言。

实现者的变异证明了测试能抓住“Responses 又使用 Anthropic 阈值”这一主要回归，这一点成立。它也能抓住把 notable 提到 `512KiB` 或把 heavy 提到 `5MiB`。但现有断言只约束 `100KiB < notable ≤ 384KiB` 与 `384KiB < heavy ≤ 4MiB`；评审探针在运行时把 Responses 阈值改成错误的 `(256KiB, 3MiB)` 后，`test_how_large_is_large_is_read_off_the_dialect` 仍然通过。

建议沿用既有 `test_the_thresholds_are_the_round_numbers` 的可见行为写法，补 `384KiB - 1` 仍为 DIM、`384KiB` 为 plain，以及 `4MiB - 1` 仍为 plain、`4MiB` 为 YELLOW。无需直接断言字典内部结构，也无需另建验证设施。分类为“建议改”而不是“必须改”，因为当前测试已经对本次最重要的跨 dialect 分流有分辨力，缺口只在精确防止阈值向下漂移。

## 已确认正确或无需改

### 数值与判据

- 保留 `384KiB/4MiB`。`384KiB` 比 `512KiB` 更好地维持 notable 约 top decile；`4MiB` 是易读的二进制整值，并会让用户观察到的 `4.9MB` 请求进入 heavy。heavy 尾部样本少，因此不要把 `4MiB` 包装成统计上的精确最优点，但目前没有证据要求改成 `5MiB`。
- “按 dialect 的自身分布判断 unusual”与这个展示的语义一致。按原始 byte ratio 等比例放大，会让阈值受固定 envelope、tool schema 和 delta 粒度混合影响，反而难以解释。若未来生产分布显著变化，再用带日期快照重新标定即可；现在不需要配置开关或动态 percentile 系统。

### 调用面

证据强度：高，已在 `src/` 与 `tests/` 枚举 `volume_colour`、`format_bytes`、`bytes_out` 和 `format_completion_line` 的当前调用面。

- 完成日志中，下行 byte 的唯一着色点就是 `request_log.py:349-355`，本改动覆盖正确。
- `footer.py` 只把进行中 byte 格式化为文本；`FooterTui._render` 在终端支持颜色时把整条 footer 统一设为 DIM，没有 notable/heavy 阶梯，也没有逐请求着色。它不是漏掉了旧全局阈值，而是根本不表达字节告警，因此不应为了本改动给 `ActiveRequest`、registry 和 footer 新增 dialect 字段。
- 当前 `tui.py` 的实际运行面只有上述 footer；`ProxyTui` 的 panel/detail reducer 明确未接入 live footer，也没有 byte renderer。未来若实现会着色的 detail view，应从聚合记录携带 dialect 后复用同一阈值 authority；这不是当前切片的遗漏。

### 直接下标

`RECEIVED_BYTES_THRESHOLDS[line.dialect]` 的取舍正确。`ReplyDialect` 是闭合的 `StrEnum`，同文件的 `REASONING_WORD[dialect]` 与 `TOOL_WORD[dialect]` 已采用同一 fail-loud 约定；新增 dialect 却漏定阈值会立即暴露，而 `.get(..., anthropic_default)` 会把新路径静默按错误分布判断。当前没有需要默认值来防御的具体合法输入，因此不建议加 fallback、校验层或配置开关。

## 最终处置建议

1. 必须收窄两处长注释和测试 docstring/comment，保留已证实的 `416`、`63.7%/3.6%`、三次 tools echo 与生产点亮率，删除或条件化“一 token 一事件”“任意回复 58KB floor”“同一回复四十倍”“share 精确 matching/唯一可用”的表述。
2. 建议补 Responses 两个阈值各自的 just-below 可见行为断言。
3. 不改 `384KiB/4MiB`，不改直接下标，不扩展 footer/TUI 数据模型，不引入配置或动态标定设施。

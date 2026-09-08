# Responses History facts 独立终审 R2

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-history-facts`，branch `fix/responses-history-facts`，candidate `2e3a6d2022244a6bca0e2db05e079bc27d94a585`，base `b91e58a29324b11840002efc53ed6f869b800c39`。评审候选最终代码、两笔候选提交、上一轮报告 `docs/tmp/260807-resume-review-history-facts.md` 的 3 个 major，以及 History、hooks、retry、Anthropic SDK 与 BACKLOG 接缝。
- **总体 verdict**：**修复 major 后可进入下一阶段。** 当前为 **0 blocker／1 major／1 minor**，**不可 squash**。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：1。

## 双视角覆盖证据

### 机械核对

- 每个采信的 shell 结果均在同一次调用内验证候选物理 root、Git top-level、branch 与完整 HEAD。缺少本轮 gate 标记的并行终端串线输出全部作废；候选树在可信测试前后状态哈希一致且最终 `git status --short` 为空。唯一仓库写入产物是主树本报告；测试输出仅落在 `/tmp`。
- 逐条对账上一轮 3 个 major：request-side conversion facts 已进入 `AnthropicAttemptResult`，并与 response facts 以 typed provenance 和最终成功 attempt 编号投影；严格 wire validator 已改用 Anthropic SDK `Message` 判别联合并逐个遍历全部 content blocks；limiter 与 retry strategy 的 success callback 已移动到 body 读取、response hook、严格校验和 conversion facts 写入之后。
- 独立运行时校准锁定依赖 `anthropic==0.79.0`。SDK `Message.content` 联合实际含 6 类：`TextBlock`、`ThinkingBlock`、`RedactedThinkingBlock`、`ToolUseBlock`、`ServerToolUseBlock`、`WebSearchToolResultBlock`。对每类构造合法 wire，`validate_messages_response_wire()`、SDK `Message` 和内部 `MessagesResponse` 均接受，且内部投影保留 block JSON。
- History 成功路径从严格验证后的 `final_response_payload` 形成 entry；现有 component test 断言客户端 response bytes 解出的 JSON 与 SQLite 读回 `entry.response` 相等。既有 writer 对 response／usage 使用 JSON blob，round-trip test 原样读回 conversion facts。未发现新增列、第二个 History owner或逐-attempt对象图。
- request-side degradation test覆盖 `system[0].cache_control` 与 `metadata.tenant`，同时断言原始 Anthropic request payload不变。retry test得到 attempts `[429, 200]`，History facts 的 attempt 集合仅为 `{1}`，provenance 顺序为 request、response、response，满足只投影最终成功 attempt 的已声明策略。
- BACKLOG 第 4 节仍把完整 per-attempt journal／typed query schema归为未来可选详细模式；本轮只把 exact usage、估算／不一致标记与 conversion facts 摘要写入既有 usage JSON，与精简 History 已决归属一致。
- 显式设置 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-history-facts/src` 后，先断言加载模块为候选树 `src/app/anthropic/response_validation.py`，再运行严格 validator、旧 3 项修复、retry provenance、History JSON equality／round-trip 的最小定向集，结果为 **27 passed in 1.61s**；测试前后候选状态哈希相同。
- false-green 检查发现：新增负向测试只记录 limiter 与 retry strategy 的 success calls，没有注册生产 builtin success observer。因此 27 个定向测试全绿，但真实 builtin observer 仍可在最终失败前写 success fact。独立探针复现了这一接缝。
- false-red 检查发现：SDK 全部 6 类合法 block 均通过当前 validator 与内部投影，未发现合法 wire 被误拒。永久测试只覆盖其中 4 类，属于测试覆盖缺口而非当前产品 false-red。

### 第一人称执行

- **合法 Responses 成功＋response hook 修改 text**：读取 200 body，先发布 `ObserverEvent.RESPONSE`，再执行 hook，严格验证最终 body，把最终 payload、最终成功 attempt 的 request／response facts 与 exact usage写入同一 `RequestContext`，随后 limiter／strategy success、完成 transition与单次 History finalize。客户端 response JSON 与 History response JSON一致。
- **合法 200 body＋hook 改成 `{}`**：driver 在 hook 前先发布 `ObserverEvent.RESPONSE`。生产 `TokenCalibrationSuccessObserver` 从原始 200 body读取 usage并调用 `calibration.learn()`；hook随后使严格 validator报 `ApiError(code="invalid_anthropic_response_body")`，请求最终 failed，History不写response／usage，但token calibration已新增样本并标记 dirty。故“failure零success facts”仍不成立。
- **429 后最终成功**：第一次 attempt不进入conversion facts终态投影；第二次重新转换并成功，History只保存 attempt 1 的 request／response facts，strategy success恰好一次。
- **逐 block严格校验**：validator用 `zip(..., strict=True)`遍历所有 raw／SDK blocks，并按SDK实际判别出的类型字段集合拒绝mixed fields；第二个block非法时不会因首块合法而漏检。6类SDK合法block正样本均通过。
- **失败终态**：hook异常、hook后wire非法与body读取失败均不触发 limiter／strategy success；但 pre-hook `ObserverEvent.RESPONSE` 的成功副作用是未覆盖分支，构成下述 major。

## 上一轮 3 个 major 复核

1. **success callbacks 时序：部分修复，仍未关闭。** limiter 与 retry strategy 已后移；生产 builtin `TokenCalibrationSuccessObserver` 仍在严格 hook／validator 前由 `ObserverEvent.RESPONSE` 触发，最终失败仍写 success calibration fact。见本轮唯一 major。
2. **request-side facts：已关闭。** request 与 response facts 均有 typed provenance 和 attempt，History只投影最终成功 attempt；原始 request payload保持不变。
3. **严格 hook body validator：产品实现已关闭。** SDK独立校准和6类合法block正样本通过，缺顶层type／role、缺必填字段、mixed fields、未知block及第二block非法均被拒绝。永久正样本漏两类SDK block，另列minor。

## 事实性发现

[major] `src/app/pipeline/executor.py:334-355`、`src/app/hooks/builtin/token_calibration.py:35-65` — 最终 response hook／严格校验失败前仍发布生产 success observer，违反“failure零success facts”，上一轮 success-callback major未完全关闭 — executor先对原始200 body发布`ObserverEvent.RESPONSE`，随后才运行可失败的response hook和wire validator；生产默认注册的`TokenCalibrationSuccessObserver`监听该事件并调用`calibration.learn()`。独立只读探针从空calibration开始，合法200 body含`input_tokens=200`，hook改成`{}`后最终得到`ApiError:invalid_anthropic_response_body`，但snapshot新增`anthropic:claude-test`的`sample_count=1`且state变为dirty。新增测试只断言limiter／strategy为零，因此产生“27 tests green但真实builtin副作用已写入”的false-green — 将原始upstream-response观察与“最终成功”事件拆开，或把`ObserverEvent.RESPONSE`及其成功副作用移到response hook、严格wire校验、最终payload／conversion facts写入之后；若仍需观察原始body，应使用不承诺成功的独立事件，禁止success observer订阅。新增使用真实`register_builtin_hooks()`与`TokenizationStateStore`的负向测试，覆盖hook异常、hook后非法body和读取失败，逐条断言calibration snapshot不变且not dirty；合法最终body只学习一次，并明确校准使用原始usage还是最终client-visible usage。

[minor] `tests/unit/test_anthropic_response_validation.py:23-47` — SDK独立校准的合法block永久测试漏`server_tool_use`与`web_search_tool_result`，依赖升级或validator改动可能让这两类合法响应回归而测试仍绿 — 锁定的Anthropic SDK 0.79.0实际联合有6类，当前参数化正样本只列text、tool_use、thinking、redacted_thinking；本轮运行时探针证明当前实现接受缺失的两类，所以不是现存产品错误 — 把两类合法fixture加入参数化正样本，并断言validate结果、SDK模型、内部MessagesResponse投影与原始block JSON一致；可从SDK判别联合导出已知类型集合并与显式fixture集合比较，使SDK新增类型时测试明确提醒补校准，而不是静默少测。

## 主观建议

无。

## 结论

当前 candidate 为 **0 blocker／1 major／1 minor**，**不可 squash**。request-side facts、最终成功 attempt provenance、History response JSON一致性、严格逐block wire validator和BACKLOG归属均已达到本轮目标；唯一阻断squash的问题是生产 builtin success observer仍在最终hook／validation失败前写token calibration事实。修复该事件时序并用真实builtin observer补负向回归后复评；达到0 major时方可squash。

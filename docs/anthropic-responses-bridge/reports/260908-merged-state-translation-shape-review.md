# Merged-state 审查：长期翻译形状接缝

- **评审范围**：当前 `main` 工作树 merged-state（`HEAD c0fadf8d` + 未提交改动）中，candidate `worktree-260908-translation-shape@38a123c0` 的长期翻译形状接缝。对照 current Spec（`.dev/docs/anthropic-responses-bridge/spec.md`）与 Architecture（`D-ARCH=B`）。不审 observability／debug／config 无关变更。
- **总体 verdict**：**有 major，无 blocker。** 共享 item／terminal／usage 单源、tool-search／hosted-search typed facts、post-header byte replay、delivery plan、legacy `app.protocols` 退休在接缝上成立。semantic retry re-encode 在生产 adapter 上违反 DirectDriver 自己的合同，已复现。
- **blocker 数**：0
- **major 数**：1
- **minor 数**：0
- **审查身份**：独立只读；判据先于实现。未改生产代码。

## 边界

**在范围内**

- `src/app/pipeline/handled.py`、`driver.py`、`direct_driver/base.py`、`request.py`、`reply.py`、`delivery_policy.py`
- `src/app/server/routes/inference.py` 的 delivery plan／reopen／replay 接缝
- `translation_driver/{openai_responses,responses,responses_events,responses_items,responses_terminal,usage}.py`
- `response_observation.py` 对共享 event／usage 的消费
- `delivery/formats/openai_responses.py`
- 对应 translation／delivery／module-boundary tests

**明确不在**

- observability／debug／config／Dockerfile 等并行改动，除非碰到上述接缝
- 完整方案 B 是否已落地（先前反方审查已覆盖 HEAD 形状；本轮只问 merged-state 接缝回归）
- hosted-web-search D3（未裁决的 unsolicited 文本路径）

## 判据来源（先于被检对象）

- Spec：每 attempt 在 PRE_SEND 之后转换；禁止 loop 外转换一次后复用陈旧 Responses payload；未知 item REJECT；stream／non-stream 终态／usage 等价；headers 绑定第一次 HTTP 200；post-commit 禁止透明 full replay。
- Architecture：`ResponsesRequestCodec` 在每次 attempt 的 PRE_SEND 之后运行；PRE_SEND 后重新 decode 成新的 attempt-local semantic request。
- 人写：`message-translation.md` 经 IR；`client-side-block-delivery.md` headers；`upstream-retry-and-continuation.md` 无痕重试。
- DirectDriver 合同：`test_retry_reencodes_the_attempt_payload_after_prepare` 要求 reencode 看见 PREPARE 之后的 payload。

## 发现

### F1 — 生产 retry re-encode 丢弃 PREPARE 对 Responses wire 的修改

- **finding_id**：`F1`
- **severity**：`major`
- **primary_location**：`src/app/pipeline/driver.py:308-323`
- **related_locations**：
  - `src/app/pipeline/direct_driver/base.py:379-384`（PREPARE 之后才 reencode）
  - `src/app/pipeline/subscribers/reasoning_encrypted_include.py:41-61`（`always_add` 在 PREPARE 写 `include`）
  - `tests/unit/pipeline/test_direct_driver.py:466-485`（合同测试只覆盖消费 payload 的 lambda，不覆盖生产 adapter）
- **问题**：candidate 给 Responses 翻译路径装了「target-wire → IR → target-wire」retry adapter，但生产闭包 `del payload`，始终从第一次翻译留下的 `context.semantic_request` outbound。DirectDriver 的顺序是 `EVENT_ATTEMPT_PREPARE` 然后 `reencode(context.payload)`。因此 PREPARE 写入的 Responses 字段在第 2 次 attempt 被 IR 重放抹掉。
- **证据**：工作树探针，`hook_fix_responses_request.reasoning_encrypted_include=always_add`，第一次 upstream 502、第二次 200：
  - attempt 0：`include=['reasoning.encrypted_content']`
  - attempt 1：`include` 缺席
  - `handle()` 两次 attempt 且 succeeded。
  这与 Spec「每个 attempt 在 PRE_SEND 之后转换、不得复用陈旧 Responses payload」相反，也与 `always_add` 自己写的「retry 在上一轮留下的 body 上再跑、且幂等」相反。默认 `passthrough` 不触发；开启 `always_add` 或任何其它会改 Responses wire 的 PREPARE（如 `repair_minted_reasoning_ids`）就会。
- **最小修复**：生产 adapter 必须消费 PREPARE 后的 payload，而不是 `del payload`。最小做法是对当前 Responses wire 做 inbound→outbound（`include` 不在 `_PASSTHROUGH_KEYS` 里，会进 same-format extensions 并被 replay）。不要只调换 DirectDriver 顺序来迁就这个闭包——那个测试已经把「PREPARE 先于 reencode」钉死了。补一条经 `handle()` 的回归，令 `always_add` 在 502 重试后第二次 payload 仍带 `include`。

## 承重面核对（无独立 finding）

| 面 | 结论 |
|---|---|
| tool-search／hosted-search facts | 已从 extras 升到 `RequestContext`／`SemanticRequest`；`handle`、`assembler_for`、`reply.response_payload` 同读。`test_tool_search_wiring` 走真实 `handle()`。 |
| post-header byte replay | `replay_prepared` 深拷贝 source attempt payload；`_prepared_payload is not None` 时跳过 reencode。connection-bound 401 同样写入 `_prepared_payload`。 |
| delivery plan | `HandledRequest.delivery_plan` 由 driver 装配，inference 在 stream／reopen 上取 assembler／buffer／framer。与 38a123c0 字节相同（`handled.py`、`delivery_policy.py`）。 |
| terminal／usage 单源 | assembler、buffered codec、observer 共用 `responses_items`／`responses_terminal`／`usage`。未知 item 两侧 REJECT。multipart 保持 part 基数。 |
| legacy namespace | `src/app/protocols` 已删；`test_the_archived_chain_is_not_importable_at_all` 与 `test_translation_driver_does_not_reach_legacy_protocol_converters` 覆盖。 |
| 38a123c0 vs 工作树 | 上列翻译模块与 `handled.py`／`request.py`／`reply.py`／`delivery_policy.py`／`delivery/formats/openai_responses.py` 与 candidate 逐字节相同。分叉在 `driver.py`（本 finding 的闭包来自 candidate；并行会话只把 `semantic_request` 赋值从 `_translate_with_facts` 挪到 `handle`，未引入 F1）、`direct_driver/base.py` 与 `inference.py` 的 capture／failure-detail（本轮不审）。 |

## 搜索面

- 读过：Spec 请求／响应／retry／usage／SSE 合同；Architecture converter／frontier／D-ARCH 五项；人写 translation／delivery／retry；上列生产文件与对应测试。
- 跑过：`pytest` 上述 in-scope 选择器 219 passed；`always_add`+502 探针（F1）。
- 未跑：全量 pytest／真实 Copilot。未把 `response.failed` HTTP 200 非流路径做成用户可观察探针（stream 走 `_FAILURE_EVENTS`，buffered 经 `stop_reason_from_response` 会变成 `end_turn`；此差异更像既有行为，不是本切片新接缝，标 `unverified` 不占 severity）。
- 并行 observability 改动未审。

## 一个绿的分辨力

in-scope 219 绿不能分辨 F1：唯一的 reencode 测试给 DirectDriver 注入了消费 payload 的 lambda，生产闭包从不进入该测试。探针把 `always_add` 弄成「重试后应仍在」后变红。

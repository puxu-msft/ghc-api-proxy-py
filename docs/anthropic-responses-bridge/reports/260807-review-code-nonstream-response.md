# Responses → Anthropic non-stream happy-path 骨架独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-response` 分支 `feat/responses-anthropic-nonstream`，固定 `HEAD=b5b82f87f17ce229e8ec85f29071f7ff6280fecf`、base `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。完整读取 base→HEAD 最终实现与测试，仅评会阻止本 happy-path 骨架回并的 blocker／major；对照主树 current Spec 的 response conversion、non-stream、usage、error 与最新双 carrier 合同。Carrier bytes 的 producer 归共享 `responses_reasoning_to_anthropic()` helper，本轮只评 converter 是否正确消费该 helper，不要求本切片复制 carrier codec。
- **总体 verdict**：**修复 major 后可进入**。内容映射骨架方向可用，但 public response identity 与必须保留的 upstream identity 仍被压成同一个字段，违反 Spec 的 API 边界；当前不可 squash 回并。
- **blocker 数**：0。
- **major 数**：1。
- **双视角覆盖证据——机械核对**：核对目标 root／branch／HEAD／base、clean worktree、单提交与两份新增文件；逐项扫描 text、多 content parts、function call、tool-name restore、malformed arguments、reasoning 多 item、encrypted-only、usage cache 算式、tool/end-turn stop reason、server-tool no-revive、failed status 与 unknown item 显式失败；对账 Spec 的 public id／model 与 upstream identity 分离要求；检查 converter 的所有仓库调用点，确认本提交尚未接入 route。固定 HEAD 导出到临时目录后，定向 7 项测试全部通过；变更文件 Ruff 通过，Pyright 为 0 error／0 warning；AST 独立清点同一测试文件确有 7 个 `test_*`。全仓测试曾两次被共享终端的外部 `SIGINT` 中断，本报告不把它写成绿色证据，也不把中断归因于候选代码。
- **双视角覆盖证据——第一人称执行**：模拟调用方把一个完整 Responses JSON 交给 converter，依次走 reasoning→text→tool→text→encrypted-only 的 source-order 路径、两个 function calls 的 tool-use stop reason、malformed arguments、server-tool、future unknown item、failed status、无 content 成功与 usage 缺失路径；再把返回值当作 `/v1/messages` public body 使用。内容路径可形成 Anthropic blocks，但 response identity 路径会把 upstream `resp_*` 直接暴露为 Anthropic message id，且调用方无法从返回值同时取得独立 upstream id／conversion facts。另在隔离快照把 unknown-item 分支变异为静默 `continue`，定向测试按目标机制变红，证明该 smoke 对 unknown silent-drop 具备判别力；独立 public-id oracle 则在 current 实现上按预期变红，实际值为 `resp_upstream`。

## 事实性发现

[major] `src/app/protocols/responses_anthropic.py:24-25,76-83`，`tests/unit/test_responses_anthropic_nonstream.py:29-31` — converter 把 upstream Responses id 原样写入 Anthropic public `MessagesResponse.id`，并丢失“public identity 与 upstream identity 分离”的 API 边界 — Spec 的 response matrix 明确要求 upstream response id／model 执行 `TRANSFORM＋PRESERVE`，即生成 Anthropic-compatible public id／model，同时在诊断 facts 中 value-exact 保留 upstream id 与 resolved model；Non-stream contract 再次要求 public id／model 满足 Anthropic wire contract，upstream id／selected endpoint 只能作为诊断 metadata。当前 `response_id = response["id"]` 后直接 `id=response_id`，返回类型又只有 `MessagesResponse`，没有承载 upstream identity 或 response conversion facts 的位置；测试还断言 public id 等于 `resp_123`，把该边界固化为绿色期望。隔离独立 oracle 对 `resp_upstream` 断言 public id 为 Anthropic message identity 时稳定失败，说明现有 7 项绿色测试没有覆盖这一 API seam。**修复建议**：让 response normalizer 返回具名 typed result，例如 `ConvertedResponse(message, facts, upstream_response_id, resolved_model／upstream_model)`；由共享、流／非流共用的 identity helper 生成 Anthropic public message id，并在独立字段 value-exact 保存 `resp_*`。测试应分别断言 public id 与 upstream id，且 expected 不由被测 identity helper同时生成；完成后定向复评至 0 blocker／0 major，才可明确 squash 回并。

## 可后续切片承接的边界

以下缺口不按本轮 major 报告，因为用户已将本提交限定为新项目 happy-path 骨架；它们必须继续保留在后续 normalizer／driver／route／stream 切片和 Acceptance gate 中，不能因本轮未阻断而视为已实现：

- refusal → text＋`DEGRADE` fact，以及通用 response `ConversionFacts`。
- `incomplete/max_output_tokens` → `max_tokens`、content filter／cancelled／unknown incomplete reason 的 typed terminal 处置。
- `output_tokens_details.reasoning_tokens`、modality／future details、`usage_inconsistent`、usage 缺失时 `estimated=true`；当前仅证明基础 cache read／write 净 input 算式。
- Responses HTTP 400／429／500、failed body message、Anthropic error envelope、header policy、response close、History／finalize、response hooks 与 limits；纯 converter 的 typed `failed_response` 不能替代这些 route-level gate。
- stream／non-stream 共享 semantic core与等价性；当前分支没有 production route 调用点，这符合渐进骨架切片，但不得表述为 API 已接线或端到端 smoke 已通过。
- 双 carrier 的项目主 v1 producer／upstream v1 consumer 兼容、strip 与 malformed 分类由共享 carrier 切片负责；本 converter 应继续只调用共享 producer，合并态需重跑多 item／encrypted-only 接缝测试。

## 主观建议

无。按本轮只报 blocker／major 的范围，不另列 minor／nit。

## 回并结论

当前为 **0 blocker／1 major**，所以**不可 squash 回并**。关闭上述 public／upstream identity API major，并在同一最终 HEAD 上取得定向测试、Ruff、Pyright与独立复评 0 blocker／0 major 后，可明确标记为 **可 squash 回并**；全仓门仍需在不受共享终端外部中断的隔离执行环境中补取。

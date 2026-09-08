# Copilot response identity WIP 只读预审

- 评审范围：`/home/xp/src/ghc-api-proxy-py-response-identity`，分支 `fix/copilot-response-identity`，基于未提交 diff `cbb02a557c0ecb5027e533b3790f5d6fcac46fa45a12c3e9f323683971abfb46`。
- 总体 verdict：**PENDING**。
- 本轮只检查：默认严格、Copilot 显式放宽、每帧 nested `id` 仍为 required、generic 不回归、terminal seal 其他规则不放宽、最小测试判别力。

## 双视角覆盖证据

- 机械核对：逐项对账 parser 默认值、route 到 renderer 的参数传播、Copilot／generic 测试入口、terminal 解析与 seal；扫描现有测试是否覆盖 missing nested `response.id`；运行相关 parser unit 与 Anthropic Responses route smoke 文件，现有测试均通过。
- 第一人称执行：分别模拟 Copilot 生命周期换 `response.id`、generic 生命周期换 `response.id`、strict／relaxed terminal 缺失 nested `response.id`、relaxed terminal 后继续来帧。Copilot 换 ID 被接受；generic 换 ID 被拒绝；terminal 后事件仍以 `event_after_terminal` 被拒绝；但 missing nested ID 的 strict／relaxed 结果与要求相反。

## PENDING 原因

[major] `src/app/openai/responses_stream_parser.py:468-474` — terminal nested `response.id` 的 required 条件写反。当前代码仅在 `require_stable_response_id=False` 且事件不是顶层 `error` 时调用 `_require_string()`，默认 strict 反而走 `_optional_string()`。不落盘探针得到：默认 `ResponsesStreamParser()` 接受缺少 `response.id` 的 `response.completed`，返回 `ResponsesTerminal(response_id=None, ...)`；relaxed parser 对同一帧报 `invalid_event`。这违反“每帧 nested id 仍 required”，也使默认严格语义变松。建议对所有带 nested `response` 的 `response.completed`／`response.incomplete`／`response.failed` terminal 无条件 `_require_string(response_object, "id", event_type)`；仅无 nested `response` 契约的顶层 `error` 保留 `None`。

[major] `tests/unit/test_responses_stream_parser.py:842-861`、`tests/smoke/test_anthropic_responses_stream_route.py:1449-1539` — 最小测试矩阵没有覆盖 missing nested ID，因此相关测试全绿仍漏掉上述反向实现。现有 unit 只验证 strict 的“不同 ID 被拒绝”；route smoke 只验证 Copilot 的“不同 ID 被接受”和 generic terminal mismatch／terminal 后事件。建议至少增加 strict 与 relaxed 两种 parser 模式下，`response.in_progress` 及各 nested-response terminal 缺失／空 `id` 均失败的判别测试；route 层保留一条 Copilot 正向与一条 generic 反向即可。

## 已核对且当前未发现 major 的边界

- 默认严格：`ResponsesStreamParser(require_stable_response_id=True)` 与 renderer 默认参数均保持严格；generic route 显式传入 strict，并由 mismatch smoke 覆盖。
- Copilot 显式放宽：`src/app/routes/anthropic.py:238-245` 仅在 `settings.upstream.type == "copilot"` 时关闭稳定 ID 比较；Copilot 跨 `created`／`in_progress`／terminal 不同 ID 的 route smoke 已通过。
- 非 terminal nested ID：`response.created` 与 `response.in_progress` 仍经 `_require_string(response, "id", ...)`，放宽只跳过跨帧相等比较。
- terminal seal：`process()` 的 seal 检查位于所有事件分派之前；relaxed 模式下 terminal 后事件仍确定性报 `event_after_terminal`。
- 其他 terminal 规则：放宽标志只影响 response ID 比较；open blocks、unsupported items、empty content、incomplete reason 与 terminal-after-terminal 分支未被条件包住。

## 恢复条件

修正 terminal nested ID 的 required 逻辑，并补能让当前反向实现变红的最小测试后，再做完成态复审；完成态只报告 blocker／major。

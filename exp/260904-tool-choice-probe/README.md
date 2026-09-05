# Tool-choice 既有实测

`raw/` 保存 2026-09-04 的请求体及响应体原件，供工具选择翻译参考。本次接管仅核对、整理并提交这些记录，没有再次调用真实上游。

## 观察与使用边界

| 样本 | 观察 |
|---|---|
| T1／T2／T4／T6 | 返回 200，输出为 message；分别为无选择、auto、none 与禁并行标志。 |
| T3／T5 | 返回 200，输出含 function_call；所测 required 和 named function 请求在不需要工具的简单问题上仍调用了工具。 |
| T7／T8 | 所测裸 `tool_search` choice 返回 400。 |
| T9／T10 | 所测带 tools 数组的 `tool_search` choice 返回 400；T10 原文明确要求类型为 `allowed_tools`，不是模型不支持错误。 |
| T11 object-form | 所测 `allowed_tools` 返回 200，但输出只有 message；这个形状没有强制调用。 |
| T11 named-form／T12 | 返回 400，不能作为成功映射依据。 |
| A1～A5 | 返回 `model_not_supported`，不能用来确认 Responses→Anthropic 的真实互操作。 |

上述单次样本足以支持保留已测成功拼写，并拒绝把所测非强制白名单当作强制选择的等价物；它们不能证明所有潜在的 tool-search 强制拼写都不存在，也不能替代其他模型／版本的实测。

翻译行为以 `.dev/docs/anthropic-responses-bridge/spec.md` 的 Tools 与 tool choice 为准。局部 unit／HTTP 测试验证代理的转换与拒绝，不冒充真实模型的执行结果。

## 手动重跑

需要有效的本地 GitHub 凭据，会产生真实上游请求；不属于默认测试。

```bash
PYTHONPATH=src uv run --frozen python exp/260904-tool-choice-probe/probe.py search
PYTHONPATH=src uv run --frozen python exp/260904-tool-choice-probe/probe.py anthropic
```

新记录写入 `runs/<UTC 时间>/`，不覆盖 `raw/`；该目录默认忽略。脚本现有两个 group 分别运行 T7／T8／T11 object-form 与 A1～A5，不声称能重建其余历史探针。HTTP 拒绝也是记录结果；传输或解析异常打印失败并以非零状态结束，不自动重试。

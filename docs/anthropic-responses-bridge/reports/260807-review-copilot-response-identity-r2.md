# Copilot Responses identity 定向终审 R2

- 评审范围：候选工作树 `/home/xp/src/ghc-api-proxy-py-response-identity`，分支 `fix/copilot-response-identity`，HEAD `1bc5a8185a6a19101679e13c9a3a0bda3072bab4`，base `c188165dd413b7683a65472781ca3bef9c1a29b3`。仅复核 Responses stream identity 的真实失败机制、route 开关和既有定向测试判别力。
- 总体 verdict：**可进入下一阶段；0 major，可 squash。**
- Blocker 数：0。
- Major 数：0。
- Minor 数：0。
- 双视角覆盖证据：
  - 机械核对：核验了候选的 PWD、Git top-level、分支、完整 HEAD/base SHA、干净工作树、base→HEAD 的 5 个变更文件、完整 source diff、parser/renderer 全部构造与调用点、`upstream.type` 的配置取值、最终行号、`git diff --check`，并对实现与 unit/smoke 测试逐项对账。
  - 第一人称执行模拟：依次走查了 generic 默认严格且 created→terminal ID 不一致、Copilot relaxed 下 created→in_progress→completed 使用三个不同且非空 nested ID、五类非 `error` lifecycle/terminal 缺失或空 ID、`error` 携带不一致 ID、Copilot 与 generic route 分流，以及成功 terminal 在 `message_stop` 前完成身份校验的路径。

## 事实性发现

未发现问题。

## 定向结论

1. **generic 默认保持 stable ID 相等约束。** `ResponsesStreamParser` 的 `require_stable_response_id` 默认值仍为 `True`，renderer 的公开入口默认值也为 `True`；因此所有未显式放宽的调用继续执行严格匹配。证据：`src/app/openai/responses_stream_parser.py:149-150`、`src/app/delivery/responses_anthropic_stream.py:159-193`。
2. **Copilot relaxed 精确允许非空 nested ID 漂移。** relaxed 模式只跳过 created/in_progress/completed 之间的相等性检查，不跳过结构与非空字符串校验。候选 smoke 路径使用 `resp_copilot_created`、`resp_copilot_in_progress`、`resp_copilot_completed` 并成功结束。证据：`src/app/openai/responses_stream_parser.py:760-780`、`tests/smoke/test_anthropic_responses_stream_route.py:1449`。
3. **所有非 `error` lifecycle/terminal 仍要求 ID。** `response.created` 与 `response.in_progress` 继续经 `_require_object` 和 `_require_string`；`response.completed`、`response.incomplete`、`response.failed` 现在也统一经 `_require_string`。relaxed 模式没有绕过这一约束。证据：`src/app/openai/responses_stream_parser.py:468-474`、`src/app/openai/responses_stream_parser.py:760-768`、`tests/unit/test_responses_stream_parser.py:864`、`tests/unit/test_responses_stream_parser.py:898`。
4. **`error` identity 保持既有严格语义。** `error.response.id` 仍可按既有协议缺省；一旦存在且此前已观察到 created ID，`event_type == "error"` 会强制相等，不受 relaxed 开关影响。证据：`src/app/openai/responses_stream_parser.py:468-475`、`src/app/openai/responses_stream_parser.py:770-780`、`tests/unit/test_responses_stream_parser.py:910`。
5. **只有 Copilot route 启用 relaxed。** parser 和 renderer 默认严格；Anthropic Responses route 仅在 `settings.upstream.type == "copilot"` 时传入 `False`，generic 明确保持 `True`。未发现其他显式放宽调用点。证据：`src/app/routes/anthropic.py:239-245`、`src/app/delivery/responses_anthropic_stream.py:165-193`。
6. **既有 mismatch 测试与 Copilot lifecycle 测试具有双向判别力。** Copilot route 测试会在开关未放宽或放宽未贯穿 renderer→parser 时于 in_progress 的第二个 ID 处失败；generic mismatch 参数会在 route 被错误地普遍放宽时错误地产生成功 terminal/`message_stop`，从而使其“必须 error、不得 message_stop”的断言失败。unit 测试另行钉住 parser 默认严格、relaxed 下所有非 `error` 事件仍需非空 nested ID，以及 relaxed 下 `error` mismatch 仍失败。证据：`tests/smoke/test_anthropic_responses_stream_route.py:1449`、`tests/smoke/test_anthropic_responses_stream_route.py:1513-1553`、`tests/unit/test_responses_stream_parser.py:843-922`。

## 最小验证

- 绑定环境：`/home/xp/src/ghc-api-proxy-py-response-identity`，HEAD `1bc5a8185a6a19101679e13c9a3a0bda3072bab4`。
- Unit 定向节点：strict mismatch、terminal ID required 的 strict/relaxed 两个参数、五类 relaxed nonempty ID 参数、relaxed error mismatch。pytest 报告 `9 passed`；按参数展开独立复核为 `1 + 2 + 5 + 1 = 9`。
- Smoke 定向节点：Copilot 三阶段 ID 漂移，以及 generic terminal mismatch/terminal 后事件两个参数。pytest 报告 `3 passed`；按参数展开独立复核为 `1 + 2 = 3`。
- 两组测试均返回成功，测试前后候选工作树状态哈希相同，且均为对空 `git status --porcelain -z` 输出计算所得的 SHA-256；未扩展测试矩阵。

## 结构与方案复核

- 结构怪味扫描范围：上述 5 个变更文件；判据为 provider 条件是否泄漏进 parser、默认严格语义是否被反转、同一 identity 规则是否出现重复实现、route 分支是否影响非 Responses 路径。未发现结构怪味。
- 更好的内部替代方案：当前“parser policy 参数 + renderer 透传 + route 单点选择”已经把 provider 决策留在边界，并让 parser 保持 provider-agnostic；本轮未发现更优且同等清晰的项目内方案。
- 判据判别力：generic 拒绝与 Copilot 接受形成正反两侧，非空 ID 与 `error` 严格性由 unit 参数化测试补齐；对本次定向机制足够。
- 第三方方案：这是局部协议不变量，不存在比当前直接校验更合适的成熟第三方组件。

## 主观建议

无。

## 评审边界

本轮遵从要求，仅运行最小定向 tests，不对其他 stream 行为扩展矩阵。候选工作树未修改；本报告是主树唯一写入。报告本身由叶子 reviewer 产出，若主流程要求对终审报告再做独立复核，应由主会话另行安排。

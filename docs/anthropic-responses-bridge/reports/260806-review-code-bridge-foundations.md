# Bridge foundations merged-state 代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-bridge` 分支 `integrate/260806-bridge-foundations`，`HEAD 614cacde72568d53170be714ea5c9a9b4d889a05`，相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的最终 merged state；覆盖 `9e5f874` reasoning cardinality、`cae83f4` session liveness、`614cacd` request converter 三个 squash commit及六个最终变更文件。严格只读评审目标树；唯一写入是本报告。
- **总体 verdict**：**修复 major 后可进入下一阶段**。完整 source ranges 和共享 reasoning 文件的手工语义合成都已保留，但 request converter 存在一个可复现的 silent-drop API 边界缺陷，且预审要求的真实 forward→converter 跨片回归门尚未落地。因此当前不应按三个 squash commits 回放 `main`。
- **blocker 数**：0。
- **major 数**：2。

## 双视角覆盖证据

### 机械核对视角

- 每次 shell 调用均在同一调用内验证物理 root、分支、精确 HEAD，并执行 `git merge-base --is-ancestor ed77c9d191df81c451c25161420515cca52ce6a4 HEAD`；评审前后目标 worktree 均为 clean。
- 对账 `base..HEAD` changed paths、三个 commit 的 subject／path集合与最终源码；`9e5f874` 的两个 blobs 与 reviewed cardinality HEAD `b876e626dda821b267535b0bcffc9d81ced12763` 精确相等，`cae83f4` 的两个 blobs 与 reviewed liveness HEAD `f27a8c04cd3470bd50d7194a30371ca5404f727e` 精确相等，`614cacd` 的 converter源码 blob 与 reviewed request HEAD `fdd2f75fcec11e592b04f2686c4664262052a964` 精确相等。Request 测试 blob 的差异仅是 integration 新增的双 thinking-block reverse测试。
- 逐段核对 forward list cardinality、逐 block reverse decode、Node-compatible malformed vectors、request static allowlists、reasoning capability facts、request-scoped tool mapper、liveness cleanup priority以及 route import graph。最终树没有 conflict marker、旧单-block forward call-site或新 foundation 的 runtime route consumer；“无 route 接线”与本轮范围一致。
- 运行 merged state 的三份定向测试、全仓 `pytest tests`、全仓 `ruff check src tests`与覆盖六个变更文件的 targeted Pyright，均通过。首次 Pyright 被共享终端外部 `Ctrl-C` 中断，随后使用隔离进程组重跑并得到零诊断；中断轮未被计作通过证据。

### 第一人称执行视角

- 模拟 Responses 侧三个 reasoning items（summary＋ciphertext、multi-part summary＋ciphertext、encrypted-only）经 forward helper生成三个 thinking blocks，再作为同一 assistant turn进入 request converter；最终恢复三个有序 reasoning items，各自 ciphertext正确，multi-part summary只在 item 内合成。
- 模拟 malformed／foreign thinking、named tool mapping碰撞、unknown formal fields、reasoning capability unknown／explicit-unbounded边界，以及 consumer cancel、重复 cancellation、pull／close双失败清理路径；代码与既有测试的终态／cause优先级一致。
- 模拟一个真实 converter调用者提交三轮消息，其中中间 assistant turn为合法通过当前 `MessagesRequest` 模型的 `content=[]`。模型保留三轮，converter却输出两个相邻 user items且不产生 `ConversionFact`或 typed error，确认发现 M1。
- 模拟后续维护者只改 forward producer或只改 converter consumer：当前 integration新增测试手写 carrier bytes，不调用 forward helper；reasoning测试又只调用低层 reverse helper，不进入 request converter。因此预审要求的组合接缝没有成为自动回归门，确认发现 M2。

## 事实性发现

[major] `src/app/protocols/anthropic_responses.py:374-385` — 合法通过当前模型的空 content-list turn 被静默删除，破坏 turn 顺序且可能产生两个相邻同角色 items — `AnthropicMessage.content` 在 `src/app/models/anthropic.py:27-29` 接受任意 `list[ContentBlock]`，没有非空约束；`_convert_blocks()` 对空 list返回空列表，`_convert_messages()` 直接 `extend`，没有 `REJECT`、`DEGRADE`或占位 message。只读复现输入 `user("first") → assistant([]) → user("second")` 时，模型保留三个 turns，而 Responses wire只剩两个相邻 user message items，`facts == ()`。这违反正式 Spec 的 turn／block顺序 preserve 与 silent drop 禁令，也使公共 converter 对自己接受的输入产生不可审计语义丢失 — 在 converter边界 fail closed，针对 `messages[i].content` 返回稳定 `invalid_content`／`unsupported_content_block` typed error；若目标 Responses schema明确支持空 message，则应保留显式空 turn而不是删除。补 user／assistant空 list、夹在异角色 turns之间及不产生相邻同角色合并的回归测试。

[major] `tests/unit/test_anthropic_responses_request.py:652-688` — 预审要求的 forward→request-converter 跨片 cardinality gate没有真正落地 — integration新增测试手写两个 synthetic carrier后只测 reverse converter；该文件不导入或调用 `responses_reasoning_to_anthropic()`。另一侧 `tests/unit/test_responses_reasoning.py:145-187` 虽覆盖多个 forward items，但只逐 block调用低层 `anthropic_thinking_to_responses()`，不经过 request模型、block traversal、field-path facts或最终 `wire["input"]`。因此两个分片可以各自全绿，却没有测试证明最终公开组合接缝持续满足 N items → N blocks → N wire items；预审明确把这一组合测试及旧聚合／last-decode变异识别力列为集成 gate — 新增一条真实组合测试：三类 reasoning items先调用 forward API，再把得到的 blocks交给 `convert_messages_request_to_responses()`，断言归一化后的 cardinality、顺序、item-local summary与 ciphertext；并补单个 malformed夹在多个 blocks中时只有对应精确 field path产生 fact，以及 portable／foreign／portable保持 2 items相对顺序的组合用例。至少用旧跨-item聚合变异和 consumer仅保留最后 decode变异确认该 gate分别变红。

## 主观建议

无。当前两项均是可复现的正确性／验收门缺陷，不是风格偏好。

## 回放结论

当前 **不能** 按 `9e5f874`、`cae83f4`、`614cacd` 三个 squash commits回放 `main`。关闭上述两个 major、重跑定向测试／全仓回归／Ruff／targeted Pyright，并由独立复评确认 major 为零后，才可按这三个 squash commits的现有顺序回放。

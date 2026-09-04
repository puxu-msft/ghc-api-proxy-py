VERDICT：NEEDS-FIX（原 3 个 major 中 2 个已关闭，1 个仍为 major）。
Major C3／C4 仍未完全关闭：`classify_responses_carrier()` 在 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/reasoning-carrier-v2/src/app/pipeline/translation_driver/reasoning_bridge.py:82-84` 对任何非 payload-v2 分类直接返回，故 Responses `encrypted_content` 中的 bare v2 得到 `project_bare_v2`；同文件 `read_responses_reasoning():215-219` 则按 Spec §6.4 正确判为 `project_v2_direction_mismatch`。实跑反例分别打印这两个结果，且 last-mile guard 调用前者，所以同一 carrier 仍被不同调用方重新解释并向 guard 暴露错误分类。
原 redacted-stream major 已关闭：独立 `REDACTED_THINKING` kind、AnthropicAssembler typed reasoning、ResponsesFramer v2 carrier、Terminal accounting 与 redacted-data guard 均接通，SDK replay／回送反例通过。
原 size-accounting major 已关闭：`CompletedBlock.size_bytes` 现同时计入 payload 与 typed `ReasoningContent`；大 extensions 正控证明 cap 会在仅 payload 尚未越界时触发。
相关反例按只读约束从 `/tmp` 运行且禁用 bytecode／pytest cache：redacted assembler、SDK framer round-trip、facade slot classification、large-extension cap、redacted-data guard 共 `5 passed in 3.16s`；另一个直接 classifier／reader 对照打印 `project_bare_v2` 与 `project_v2_direction_mismatch`；未重跑全量。
复评对象已锚定修复提交 `5be74ee00ba3ba5cf5e0ad7524816e3f63c3c52f`，其相对前一候选为单提交、15 个变更路径；本轮未写源码或测试。

# Reasoning cardinality 代码独立评审

## 结论

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-reasoning-cardinality` 分支 `fix/reasoning-cardinality`，固定 `HEAD=b876e626dda821b267535b0bcffc9d81ced12763`、base `ed77c9d191df81c451c25161420515cca52ce6a4`。只评审 `src/app/anthropic/thinking/responses_reasoning.py`、`tests/unit/test_responses_reasoning.py` 的最终文件与 diff，并对照裁决 `docs/tmp/260806-arbitrate-reasoning-aggregation.md` 及 `/home/xp/src/copilot-api-js@ccb645f5ea58a17fa6977f47367564b8babb5bba` 的固定 carrier、stream、reverse、nonstream 行为；未冷启动全仓评审。
- **总体 verdict**：**可进入下一阶段。0 major，明确可 squash。**
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **nit 数**：0。

## 双视角覆盖证据

### 机械核对

- 每次 load-bearing shell 都在同一调用内校验目标绝对路径、仓库顶层、分支、完整 `HEAD` 和 base 祖先关系；两份评审文件的 worktree blob 与目标 `HEAD` blob 相等，评审开始和测试结束时目标工作树均为 clean。
- 精确 diff 只有两份声明文件：实现从“序列聚合为至多一个 block”改为“按 reasoning item 返回有序 block 列表”，测试同步反转 encrypted-only 丢失与跨 item 聚合的旧 oracle。
- 固定 upstream commit tree 显示 carrier primitive 位于 `src/lib/anthropic/synthetic-reasoning.ts:32-67`：prefix、legacy sentinel、UTF-8→unpadded base64url、bare prefix 与 Python 实现一致；reverse 在 `src/lib/openai/translate/anthropic-to-responses-request.ts:258-275` 对每个 synthetic thinking block 重建一个 reasoning item。
- 固定 upstream 的 nonstream `src/lib/openai/translate/responses-to-anthropic.ts:163-218` 和 stream `src/lib/openai/translate/responses-to-anthropic-stream.ts:126-186,228-279` 仍有跨 item summary／ciphertext 单槽行为；按既有裁决，这两者只作为待拒绝的行为反例，不覆盖 carrier／reverse 兼容要求。
- 全仓 Python 静态调用扫描只发现定义与本单测引用，没有现有生产调用方依赖旧的 `AnthropicThinkingBlock | None` 返回形状。因此本 commit 的 list API 变化不会破坏当前仓内已接线调用；它也是裁决要求的有序 block 列表 API。
- 以 AST 清点得到该测试文件 9 个 `test_` 定义；在显式绑定 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-reasoning-cardinality/src`、并用 `module.__file__` 证明导入目标 worktree 后，定向 pytest 执行同一口径的 9 项并得到 `9 passed`。这是两种不同原理对测试数量的交叉验证。
- 定向 pyright 对两份评审文件得到 `0 errors, 0 warnings, 0 informations`。首次尝试被共享终端外部 `Ctrl-C` 中断，不作为结果；可信结果来自后续 `setsid` 隔离进程组运行。
- 以内存 monkeypatch 注入“保留 list API、但恢复跨 item 聚合＋last-ciphertext-wins＋encrypted-only 丢失”的旧语义，不改文件；同一 9 项测试得到 `3 failed, 6 passed`。失败分别命中 encrypted-only、block cardinality／order、逐 block roundtrip，证明绿灯不是仅靠返回容器变化获得。

### 第一人称执行模拟

- **cardinality／order**：依次输入 `A/ENC-1`、非 reasoning item、encrypted-only `ENC-ONLY`、`B/no payload`，实际得到 3 个 thinking blocks，`thinking` 顺序为 `A+detail`、空串、`B`；非 reasoning item 不生成 block，也不扰乱 reasoning 相对顺序。
- **item 内 summary**：同一 item 的 `A` 与 `+detail` 拼成 `A+detail`；实现于 `responses_reasoning.py:68-84` 为每个 item 重建 `summary_text` 容器，没有跨 item 复用。
- **encrypted-only no-loss**：非空 payload 且空 summary 在 `responses_reasoning.py:81-94` 生成 `thinking=""` block，而不是因 visible text 为空被跳过；reverse 恢复 `summary=[]` 与原始 `ENC-ONLY`。
- **roundtrip**：逐 block reverse 的实跑结果依次恢复 `A+detail/ENC-1`、空 summary／`ENC-ONLY`、`B/no payload`，没有跨 item ciphertext 覆盖。单测另覆盖含 `NUL` 与 emoji 的 byte-compatible carrier roundtrip。
- **empty／absent 边界**：只有 `thinking` 为空且 `encrypted_content` absent／empty 的 item 才在 `responses_reasoning.py:84-86` 省略；非空 encrypted-only 不会走该分支。这符合裁决中的允许省略边界。
- **API 使用路径**：以未来 converter 调用者身份消费返回值时，可直接按 list 顺序插入 ordered semantic blocks；无 reasoning 或全部可省略 item 返回空 list，invalid shape 仍返回 `None`，两者保持可区分。仓内当前没有旧单-block生产调用方需要迁移。

## 事实性发现

未发现问题。

## 主观建议

无。

## 结构怪味扫描

- **扫描范围**：两份最终文件、base→HEAD 精确 diff、转换函数全部 Python 静态调用点，以及固定 upstream carrier／stream／reverse／nonstream 接缝。
- **判据**：跨 item 可变状态、职责重复、返回 cardinality 隐藏、carrier codec 分叉、测试与实现同源假绿、生产调用方对旧返回类型的残留依赖。
- **结果**：未发现需在本轮修复或记录 backlog 的结构怪味。函数名使用复数 `responses_reasoning` 且返回注解显式为 `list[...] | None`，当前 API 没有把新 cardinality 隐藏给类型检查器；carrier／reverse 保留为单一 primitive，没有另造 wire schema。

## 最终裁决

`b876e626dda821b267535b0bcffc9d81ced12763` 满足既有裁决：保留 carrier／reverse wire compatibility；forward 按 source reasoning item 生成有序 thinking block；同 item 内 summary 才拼接；non-empty encrypted-only 无损；逐 block reverse 不发生跨 item 覆盖。定向测试在正确 worktree 上全绿，目标旧缺陷变异会转红，且仓内没有生产调用方受返回类型变化影响。**0 major，可 squash。**

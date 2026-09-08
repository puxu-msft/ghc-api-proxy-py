# 三片 bridge foundations 集成策略只读预审

## 评审结论

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@ed77c9d191df81c451c25161420515cca52ce6a4`，source tips `b876e626dda821b267535b0bcffc9d81ced12763`、`f27a8c04cd3470bd50d7194a30371ca5404f727e`、`fdd2f75fcec11e592b04f2686c4664262052a964`，以及主树 `docs/agents/anthropic-responses-bridge/spec.md`、`docs/agents/anthropic-responses-bridge/architecture.md`。本轮只预审集成策略，没有修改代码、Git index、分支或 worktree，也没有执行候选实现测试。
- **总体 verdict**：**可进入集成实现，但必须按 range 集成并对共享 reasoning 文件作手工语义合并；不得使用整文件或全局 `ours`／`theirs`。** 三片目标兼容，没有产品合同冲突。当前有两项必须由实现者落实的 major gate：不能只摘取第二、第三片 tip 的最后一个提交；第一与第三片在 `responses_reasoning.py` 上必须合成两侧语义并补跨片 cardinality 测试。
- **blocker 数**：0。
- **major 数**：2。
- **minor 数**：0。
- **本报告用途**：供集成实现者执行后，由独立评审者按本文语义清单和组合测试清单复核。本文不是实现完成或测试通过的证明。

### 双视角覆盖证据

- **机械核对视角**：每次 shell 读取分别 gate 物理 worktree、Git 顶层目录和精确 HEAD；核对三个 tip 的单提交 `diff-tree`、相对真实 merge-base 的 source range、精确 changed paths、提交父链、第一与第三片的 `merge-tree` 冲突面、主树 Spec／Architecture 关键合同及工作树 SHA-256。主树 oracle 工作树哈希为：Spec `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`，Architecture `5f6b8bd2f24247ae762cf5e76c129171772b7857839bb5db4fa455cfc5245752`。这些哈希只锚定本轮读取内容，不宣称文件已提交。
- **第一人称执行视角**：按“集成者先落第一片，再落第三片并解决共享文件，最后落独立 liveness 片”的路径模拟；逐步检查只 cherry-pick tip、使用 `ours`、使用 `theirs`、自动文本合并但不跑跨片测试四种失败方式；再沿 Responses reasoning items → Anthropic thinking blocks → request converter 逐 block decode → Responses input items 的完整调用链检查 cardinality、顺序和 encrypted-only no-loss。

## Source 基线与精确路径

### 第一片：reasoning cardinality

- **source worktree gate**：`/home/xp/src/ghc-api-proxy-py-reasoning-cardinality`，分支 `fix/reasoning-cardinality`，HEAD `b876e626dda821b267535b0bcffc9d81ced12763`。
- **真实 merge-base**：主树基线 `ed77c9d191df81c451c25161420515cca52ce6a4`；该片是基于主树的单提交。
- **source range 提交**：
  - `b876e626dda821b267535b0bcffc9d81ced12763` — `fix: preserve reasoning item cardinality`
- **tip 单提交 diff 与完整 source range 的精确路径相同**：
  - `M src/app/anthropic/thinking/responses_reasoning.py`
  - `M tests/unit/test_responses_reasoning.py`
- **必须保留的目标语义**：forward API 从“全部 reasoning items 聚合为至多一个 block”改为“每个有效 reasoning item 生成自己的 Anthropic thinking block”；同一 item 内 summary parts 按序拼接，但 item 间不聚合；每个 block 绑定本 item 的 `encrypted_content`；非空 encrypted-only item 生成 `thinking=""` 的合法 block；输出保持 source order；非 reasoning item 不生成 block；结构 malformed 仍 fail closed 为 `None`，没有可输出 reasoning block 时当前实现返回空 list。

### 第二片：session liveness 与 cancellation-resilient cleanup

- **source worktree gate**：`/home/xp/src/ghc-api-proxy-py-liveness`，分支 `feat/session-liveness`，HEAD `f27a8c04cd3470bd50d7194a30371ca5404f727e`。
- **真实 merge-base**：`47d9ef101c4b81ac70d805b1da157b34d021d33d`。该 source tip 不是当前主树 HEAD 的直接后继，不能把最后一个提交等同于完整功能片。
- **完整 source range 提交，按顺序**：
  - `74cff321d3ce993f7def73790b55dee8d44b9d2c` — `feat: add session liveness coordinator`
  - `135f5b4bf0946f7c5c9cd032f54f97cc04698210` — `fix: close liveness streams without task warnings`
  - `f27a8c04cd3470bd50d7194a30371ca5404f727e` — `fix: preserve liveness cleanup failures`
- **完整 source range 精确路径**：
  - `M src/app/streaming/keepalive.py`
  - `M tests/unit/test_streaming_resilience.py`
- **tip `f27a8c04...` 自身也只显示上述两条路径，但它只增加 cleanup failure／repeated cancellation 语义，不包含前两个提交引入的完整 liveness coordinator 基础。** 只 cherry-pick tip 不是有效集成策略。
- **与当前主树的路径重叠**：从真实 merge-base 到当前主树，这两条 source 路径没有主树侧变化；预计不需要内容冲突裁决，但仍必须集成完整三提交 range。
- **必须保留的目标语义**：一个 upstream `anext` 在 heartbeat 期间持续 in-flight；heartbeat 不重启 upstream pull；upstream idle deadline 与 heartbeat deadline 分离；downstream pause 不计为 upstream idle；item 与 idle deadline 同时成立时 item 优先；退出时 settle pending pull 并关闭 iterator；cleanup 使用唯一 task，重复 cancellation 只被记住而不截断 cleanup；已有 primary exception／cancellation 保持 primary，close failure 作为显式 cause；无 primary 时 close failure 向外传播。

### 第三片：Anthropic Messages → Responses request converter

- **source worktree gate**：`/home/xp/src/ghc-api-proxy-py-request`，分支 `feat/anthropic-responses-request`，HEAD `fdd2f75fcec11e592b04f2686c4664262052a964`。
- **真实 merge-base**：主树基线 `ed77c9d191df81c451c25161420515cca52ce6a4`。该分支从主树发出，但 source tip 包含三个提交；只 cherry-pick 最后一个 tip 会漏掉 converter 主体。
- **完整 source range 提交，按顺序**：
  - `cb286059b656d960225c2afff84f204b9123810d` — `feat: convert Anthropic requests to Responses`
  - `028f1f2ba7f7ac8ff30e609acb4b0661aff6124f` — `fix: harden Anthropic Responses request conversion`
  - `fdd2f75fcec11e592b04f2686c4664262052a964` — `fix: fail closed on unknown reasoning limits`
- **tip `fdd2f75...` 单提交 diff 精确路径**：
  - `M src/app/protocols/anthropic_responses.py`
  - `M tests/unit/test_anthropic_responses_request.py`
- **完整 source range 精确路径**：
  - `M src/app/anthropic/thinking/responses_reasoning.py`
  - `A src/app/protocols/anthropic_responses.py`
  - `A tests/unit/test_anthropic_responses_request.py`
- **必须保留的目标语义**：request conversion 是纯转换边界，不拥有 transport／retry；严格拒绝未知 formal fields、未知 content variants、server tools 和无等价字段；显式记录允许的 degradation；保持 text／image／tool／thinking 的原顺序；tool declaration、历史 call 与 forced choice 共用 request-scoped 双向 name mapping；reasoning capability facts 必须明确，unknown budget limits fail closed；正整数 budget validation 在 capability lookup 前执行；显式 unbounded 与 unknown limits 分开表达；carrier reverse decode 与固定 Node vectors 兼容，并为非 canonical／malformed payload 产生精确 conversion fact。

## 第三片共享文件冲突：必须保留的语义清单

经典三方 `merge-tree(main, b876e626..., fdd2f75...)` 报告 `src/app/anthropic/thinking/responses_reasoning.py` 为 `changed in both`。正确结果不是选一侧，而是以下语义并集。

### 必须从第一片保留

1. `responses_reasoning_to_anthropic()` 返回逐 item 的 `list[AnthropicThinkingBlock] | None`，而不是单个聚合 block。
2. 每个 reasoning item 使用独立 `summary_text` accumulator；不得把 accumulator 放在 item loop 外。
3. 每个 item 的 signature 只能编码该 item 自己的 `encrypted_content`；不得使用“最后一个 ciphertext 胜出”的共享变量。
4. 非空 encrypted-only item 必须生成 `thinking=""` 加本 item carrier；不得因 visible summary 为空而丢弃。
5. 多 reasoning items 的输出顺序与 source order 相同；中间出现非 reasoning item 不得导致前后 reasoning 合并或错配。
6. 现有 carrier prefix、base64url 正向编码和 legacy reverse 兼容行为保持 byte-compatible。

### 必须从第三片保留

1. `AnthropicThinkingDecode` typed result，至少同时携带 `item` 与 `malformed_payload`，让 converter 不必从返回值猜测 degradation。
2. `_decode_encrypted_content()` 的 Node-compatible 容错语义与 malformed 分类：接受固定 oracle 覆盖的 base64／base64url 变体，标记非 canonical 字符、截断和 UTF-8 replacement，而不是简单抛错或静默归一后丢失诊断。
3. `decode_anthropic_thinking()` 作为 detailed reverse API；它对单个 Anthropic thinking block 返回零或一个 Responses reasoning item及 malformed fact。
4. `anthropic_thinking_to_responses()` 兼容 wrapper 仍保留，并委托 detailed API；不能因新增 detailed result 破坏已有单 block consumer。
5. `src/app/protocols/anthropic_responses.py` 对 `decode_anthropic_thinking` 的 import 和调用必须继续成立。
6. foreign signature 不伪装为 portable reasoning；malformed synthetic carrier 可按固定 Node 结果转换，但必须产生 `malformed_reasoning_carrier` fact；字段路径精确到原始 content block。

### Request converter 调用 reasoning API 的 cardinality 核对

- `_convert_blocks()` 按 Anthropic `message.content` 顺序逐 block 迭代。
- 每遇到一个 `thinking` block，恰好调用一次 `_convert_thinking(block, path)`；`_convert_thinking()` 又恰好调用一次 `decode_anthropic_thinking()`。
- 每次 detailed decode 最多返回一个 `ResponsesReasoningItem`；非 `None` 时立即 append 到 `items`。因此 reverse 边界是 **1 Anthropic thinking block → 0 或 1 Responses reasoning item**，不是“一组 blocks → 一个聚合 item”。
- converter 不调用 forward `responses_reasoning_to_anthropic()`。第一片和第三片的 API 关系是互补方向：forward 负责 **N Responses reasoning items → N Anthropic thinking blocks**；第三片 converter 逐 block reverse 后恢复 **N blocks → N Responses reasoning items**。
- 现有第三片测试只覆盖单个 portable carrier和 malformed vector；现有第一片测试直接逐 block 调用 reverse helper。它们分别为绿仍不足以证明组合接缝无损，因此必须增加下节的跨片测试。

## 为什么不能使用 `ours`／`theirs`

1. **在共享文件上选择第一片／当前侧，相当于丢弃第三片 detailed decoder。** 直接后果是 `decode_anthropic_thinking`、`AnthropicThinkingDecode` 和 malformed classification 消失，第三片 converter import 失败，或被迫退回无法记录 malformed fact 的旧 API。
2. **在共享文件上选择第三片侧，相当于丢弃第一片 forward cardinality 修复。** 代码会恢复跨 item summary 聚合、last-ciphertext-wins 和 encrypted-only loss，直接违反主树 Spec 与 Architecture。
3. **所需结果是同一文件内不同职责的语义并集，不是文件级偏好。** 第一片改 forward cardinality；第三片改 reverse decode observability。它们可以共存，但 Git 的整文件 `ours`／`theirs` 无法表达“forward 取第一片、reverse 取第三片、共享 codec 同时保持兼容”。
4. **全局 `-X ours`／`-X theirs` 风险更高。** 它会把偏好应用到当前或未来所有冲突，可能无提示丢掉测试 oracle或新增严格校验；即使本轮只有一个文本冲突，也不能把未来路径集合当作冻结事实。
5. **自动文本合并成功也不是语义证明。** 两侧编辑区域部分分离时，合并器可能产出可解析文件，但 return type、wrapper、import、测试期望和 per-item state 仍可能不一致。必须按本文清单和组合测试验收。

## 推荐集成顺序

1. 先集成第一片 `b876e626...`，把主树公开的 forward cardinality 缺口关闭，并先运行其 targeted tests。
2. 再集成第三片完整 range `cb286059...` → `028f1f2...` → `fdd2f75...`。在共享 `responses_reasoning.py` 上手工合成上述语义并集，不作整文件取舍。
3. 立即执行 reasoning 跨片组合测试；确认 `responses_reasoning_to_anthropic` 的返回类型、第三片 import 和 detailed decode facts 同时成立后，再验收第三片其余 converter tests。
4. 最后集成第二片完整 range `74cff321...` → `135f5b4...` → `f27a8c04...`。它与前两片没有路径重叠，可独立落地，但不能只取 tip。
5. 运行三片联合 targeted suite、targeted static analysis 和项目级回归；之后交给未参与实现的评审者按本文复核。不要把“各 source worktree 自己的测试曾通过”转述为“组合态已通过”。

第二片也可在第一步前独立集成；推荐把它放最后只是为了先收敛唯一真实冲突，不表示 liveness 优先级较低，也不授权遗漏完整 range。

## 组合测试清单

### A. 第一片既有回归必须保持

至少覆盖以下现有测试语义：

- plain summary → 单 block bare carrier。
- encrypted-only → 可逆的空 visible thinking block。
- mixed summary parts 仅在 item 内拼接。
- 多 reasoning items → 多个独立 blocks，source order 保持。
- carrier 字段与 bytes round-trip。
- 多 item round-trip 不发生 cross-item summary／ciphertext loss。
- foreign、redacted、legacy 和 malformed carrier 保持既定兼容边界。

对应文件：`tests/unit/test_responses_reasoning.py`。

### B. 第三片既有回归必须保持

完整运行 `tests/unit/test_anthropic_responses_request.py`，重点不得遗漏：

- system empty segment、text／image／tool interleaving 与 request 不变性。
- unknown formal fields、未知 content variants、server tools 和无等价字段 fail closed。
- request-scoped tool-name bijection 对 declaration、historical call、choice 原子一致。
- portable reasoning carrier reverse；foreign carrier degradation；固定 malformed Node vectors及精确 field path。
- enabled／adaptive／disabled thinking capability mapping。
- missing capability facts、unknown budget limits、非法非正 budget、范围外 budget拒绝。
- explicitly unbounded limits 与 unknown limits 可区分。
- min／max 边界值精确接受，unsupported effort／band 明确拒绝。

### C. 第二片既有回归必须保持

完整运行 `tests/unit/test_streaming_resilience.py`，重点不得遗漏：

- heartbeat silence、多个 heartbeat 不重启 upstream pull、silence 后 upstream order。
- upstream stop、idle timeout、activity 后 deadline reset、downstream pause 不算 upstream idle。
- item 与 idle deadline 竞态时 item 优先。
- close／cancel 均关闭 upstream iterator。
- 第二次 cancellation 不截断 cleanup。
- cancellation／upstream error 为 primary，close failure 为 cause。
- normal exit 无 primary 时 close failure 向外传播。
- cancellation 必须观察同步完成的 pull，覆盖 item／stop／error 三种 outcome。
- heartbeat 可关闭，旧 `keepalive_stream()` compatibility wrapper 行为保持。

### D. 必须新增或确认存在的跨片 reasoning cardinality 测试

1. **完整 round-trip cardinality**：构造三个 Responses reasoning items——summary＋ciphertext、multi-part summary＋ciphertext、encrypted-only；先调用第一片 forward API得到三个 thinking blocks，再把这些 blocks 作为同一个 assistant message 的 content 输入第三片 converter；断言 `wire["input"]` 恰有三个 reasoning items，顺序一致，各自恢复自己的 summary 和 `encrypted_content`。
2. **逐 block detailed fact 隔离**：在多个 thinking blocks 中只让一个 carrier malformed；断言 item cardinality 不塌缩，只有对应 `messages[i].content[j]` 产生 `malformed_reasoning_carrier` fact，其他 blocks 无误标。
3. **foreign block 的 0／1 cardinality**：portable、foreign、portable 三个 thinking blocks 按序输入；断言两个 portable items 保持相对顺序，foreign 仅产生自己的 degradation fact，不导致前后两个 item 聚合。
4. **top-level reasoning config 与历史 reasoning items 正交**：请求同时带 `thinking.enabled` 和 assistant 历史 synthetic thinking blocks；断言 top-level `wire["reasoning"]` 只表达本次生成配置，`wire["input"]` 逐 block 保留历史 reasoning state，两者不覆盖、不合并。
5. **空输出边界**：forward 输入无 reasoning items或只有 summary 为空且无 ciphertext 的 reasoning item时，确认调用方正确处理空 list；不得把空 list误当成一个空 thinking block，也不得因旧 API 的 `None` 假设崩溃。
6. **mutation positive control**：临时恢复主树旧的跨 item聚合／last-ciphertext-wins 实现时，第 1 项必须变红；临时把 converter 改为只保留最后一次 decode 时，第 1、2、3 项必须变红。恢复变异后再跑全套。变异须在隔离 worktree 以 exact patch 注入和反向应用，不能整文件覆盖共享工作树。

### E. 组合态静态与回归 gate

- 对组合态精确运行三份 targeted test files，而不是只在三个 source worktrees 分别运行。
- targeted Pyright 至少覆盖：
  - `src/app/anthropic/thinking/responses_reasoning.py`
  - `src/app/protocols/anthropic_responses.py`
  - `src/app/streaming/keepalive.py`
  - 三份对应 unit test files
- 运行项目既有 formatter／linter 与全量 test suite；先核对项目声明的命令，不在本预审中臆造固定参数。
- 对共享文件确认没有 conflict markers、重复定义、失效 import 或旧单-block return type 的 call-site 残留。
- 用独立方法核对 changed paths：既看 source range diff，也看最终集成分支相对 `ed77c9d...` 的 diff；最终路径超出本文集合时逐条解释来源，不能默认为无关噪声。

当前三片只提供 foundations，第二片 liveness 与第三片 request converter 尚无直接运行时接线。不要为了“跨片测试”人为构造无产品意义的 converter＋heartbeat 单测；真正必须新增的接缝测试是第一片 forward 与第三片逐 block reverse 的 cardinality round-trip。第二片在未来接入 Responses transport exchange 时，再按 Architecture 的 cleanup 合同做 transport-level 集成测试。

## 事实性发现

[major] `f27a8c04...` 与 `fdd2f75...` 只是各自功能分支的 tip 最后一提交，不能单独 cherry-pick作为完整片 — 第二片完整 range含 `74cff321...`、`135f5b4...`、`f27a8c04...`；第三片完整 range含 `cb286059...`、`028f1f2...`、`fdd2f75...`。tip 单提交 diff只展示最后一轮修补，不包含 coordinator／converter主体 — 集成者应按文中有序 range集成，复核者应以 merge-base→tip 的净变化而不是 tip commit diff 判定完整性。

[major] `src/app/anthropic/thinking/responses_reasoning.py` 需要第一片 forward cardinality 与第三片 detailed reverse decoder 的语义并集 — `merge-tree` 明确报告 `changed in both`；取第一片会让第三片 `decode_anthropic_thinking` import／malformed fact 失效，取第三片会恢复 Spec 明令禁止的聚合与 encrypted-only loss — 手工合并并以跨片 N→N round-trip 测试验收。

## 主观建议

[建议] 集成提交顺序 — 先 reasoning cardinality、再 request converter、最后 liveness，可把唯一共享文件冲突集中在一个阶段，并让 converter 的跨片测试紧邻冲突解决 — 推荐按“单片 targeted tests → 跨片 tests → 三片联合 tests → 全量回归”的节奏落本地语义提交。

[建议] 复评证据 — 独立复评时同时展示最终共享文件源码、跨片 round-trip 断言、targeted Pyright 和三片联合 test 输出；不要只给 Git conflict 已清零或各 source branch 既有绿测 — 这样能区分文本合并成功与真正的 cardinality／diagnostic 语义同时保留。

## 结构怪味扫描

- `src/app/anthropic/thinking/responses_reasoning.py`：**同一 codec 文件同时承载 forward cardinality 与 reverse decode diagnostics，形成高冲突热点**。本轮处置：不在预审中改结构；集成时先保持行为并补组合测试，后续可评估拆成共享 codec＋forward adapter＋reverse decoder，但不得在冲突解决时顺手重构扩大变量。
- `src/app/protocols/anthropic_responses.py`：**request converter 同时含字段政策、tool mapping、reasoning capability mapping 和 block traversal，文件较大**。本轮处置：本片是明确 foundation，先保持 source语义；若后续 driver 接线继续增长，记录为可维护性重构候选，不在本次集成中把正确性合并与结构迁移混做。
- `src/app/streaming/keepalive.py`：**通用 liveness wrapper 与 cancellation-resilient cleanup 共处，但职责边界仍可读，测试覆盖退出优先级**。本轮处置：按 source range原样集成，不建议为消除表面复杂度改回普通 `await aclose()` 或吞掉 secondary failure。

## 复评交接

实现完成后的独立复评应先回答四个机械问题：

1. 最终分支是否包含第二、第三片各自的完整提交语义，而非只有 tip 修补？
2. `responses_reasoning.py` 是否同时具有逐 item forward list 与 detailed single-block reverse decode？
3. request converter 是否仍对每个 thinking content block独立调用一次 detailed decode，并按 source order append零或一个 item？
4. 跨片测试是否能让旧聚合实现和“只保留最后 decode”两种缺陷分别变红？

四项均有源码与运行证据后，才可把本预审 verdict升级为“组合态可进入后续 driver／transport 接线”。

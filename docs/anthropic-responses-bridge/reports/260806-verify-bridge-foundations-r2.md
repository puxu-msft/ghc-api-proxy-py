# Anthropic Responses bridge foundations 独立复验 R2

## 判定

- **候选**：`/home/xp/src/ghc-api-proxy-py-integrate-bridge`，分支 `integrate/260806-bridge-foundations`，HEAD `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。
- **base**：`ed77c9d191df81c451c25161420515cca52ce6a4`。每次 load-bearing shell 调用都在同一调用内打印并校验物理工作目录、Git 顶层目录、分支、完整 HEAD，并以 `git merge-base --is-ancestor` 验证 base 是候选祖先；执行前后候选 worktree 均为 clean。
- **总体 verdict**：**PASS**。上一轮 foundations PASS 后，merged-state review 新增的两项 major 均已通过独立追加 oracle：空 `user`／`assistant` content list 在产生任何 Responses wire item 前以稳定 typed error 拒绝；真实 production forward 的多个 reasoning items 经 thinking blocks、`MessagesRequest` validation 与 public request converter 后保持 $N \rightarrow N$、顺序、item-local ciphertext 与 encrypted-only no-loss。
- **范围边界**：本轮不重跑上一报告已经通过的全量基础调查，只对新增两项执行独立 oracle，并对 reasoning primitive 与 session liveness 做代表性回归抽样。上一报告明确排除的 route、transport、response assembler、block sink／commit frontier、retry、History、approval、hooks、tokenization、cancel、shutdown、backpressure 与 quota 接线仍为**未验证**；本报告不把 foundations PASS 外推为完整 bridge 产品 PASS。
- **写入纪律**：候选 integration worktree 全程只读；Python 使用 `PYTHONDONTWRITEBYTECODE=1`，pytest 使用 `-p no:cacheprovider`。唯一主树写入为本报告 `docs/tmp/260806-verify-bridge-foundations-r2.md`。

## 冻结 oracle 与追加验收矩阵

行为 oracle 为主树 `docs/agents/anthropic-responses-bridge/spec.md`。本轮在 `main@ed77c9d191df81c451c25161420515cca52ce6a4` 下分别用 `sha256sum` 与 Python `hashlib.sha256` 计算内容身份，两种不同实现均得到 `a193da7179fbdab2464ee3ae987477ffd6b334e38041a6481994f4cd69c99694`。

本轮先从 Spec 独立推导以下 expected，再读取 merged-state review、实现与新增测试：

| ID | Spec 条款／用户可观察行为 | 独立 expected | 结果 |
|---|---|---|---|
| R2-01 | Request conversion 的 turn 顺序 `PRESERVE`、unknown／不可表达语义不得 silent drop；空 list 的后续裁决固定 `REJECT` | 共享 `MessagesRequest` 即使接受 `content=[]`，Responses converter 也必须在 wire 产生前抛 `RequestConversionError`；`code="invalid_content"`，`field_path="messages[i].content"`。`user` 与 `assistant` 两种角色都不得因删除空 turn 而制造相邻 same-role wire items；非空 block list 不能被误拒 | PASS |
| R2-02 | 每个 Responses reasoning item 一对一形成 thinking block；多个 items 不得聚合；每项 carrier 只绑定本项 ciphertext；非空 encrypted-only 不得丢失；source order 保持 | 构造 3 个有效 reasoning items，其中包含 item 内多 summary parts、非 reasoning 间隔项与 encrypted-only item；沿真实 forward → blocks → `MessagesRequest` → public converter 链路后必须得到 3 个有序 reasoning wire items，summary 只在 item 内拼接，3 个 ciphertext 各自 value-exact 恢复 | PASS |
| R2-PC | R2-02 判据判别力 | 仅在进程内把 production forward 替换为旧式“跨 item 聚合 summary＋只保留最后 ciphertext”机制；同一链路 oracle 必须因目标 cardinality 失败而红，恢复后必须重新变绿 | PASS，目标变异红于 `blocks=1 expected=3`，恢复后重绿 |

## 实现与测试观测点

以下位置只用于标明本轮实际执行接缝，不作架构或风格评审：

- `src/app/protocols/anthropic_responses.py:385`：空 content-list 的稳定错误消息；guard 位于 message 遍历和 `_convert_blocks()` 之前。
- `src/app/anthropic/thinking/responses_reasoning.py:67`：production Responses reasoning items → Anthropic thinking blocks forward 入口。
- `src/app/protocols/anthropic_responses.py:526`：converter 对每个 thinking block 的 detailed reverse decode 入口。
- `tests/unit/test_anthropic_responses_request.py:83`：`user`／`assistant` 空 list 参数化回归。
- `tests/unit/test_anthropic_responses_request.py:716`：真实 forward → blocks → `MessagesRequest` → converter 跨片回归。

独立运行进程检查了 `responses_reasoning`、`models.anthropic` 与 `protocols.anthropic_responses` 三个模块的 `__file__`；三者经 `Path.resolve()` 后均位于 `/home/xp/src/ghc-api-proxy-py-integrate-bridge` 下，输出为 `LOAD_ORACLE=TARGET_TREE`，未误加载主树或共享安装中的同名代码。

## 实际执行证据

### 独立追加 oracle

在 nonce `VERIFY_BRIDGE_R2_260807_A7F3` 包围的同一次 gated shell 中，使用主树虚拟环境 Python，并把 `PYTHONPATH` 显式绑定到候选 `src`。进程退出码为 `0`，关键输出如下：

- `EMPTY_LIST_ORACLE=GREEN roles=user,assistant typed=invalid_content path=messages[1].content wire=none`
- `EMPTY_LIST_FALSE_RED_CONTROL=GREEN nonempty-list-with-empty-text=accepted`
- `REASONING_CHAIN_ORACLE=GREEN source=3 blocks=3 request=validated wire=3 order=exact ciphertext=exact encrypted-only=preserved`
- `POSITIVE_CONTROL=RED mutation=legacy-aggregate-last-ciphertext reason=blocks-1-vs-3`
- `MUTATION_RESTORE=GREEN`
- `INDEPENDENT_ORACLE_SUMMARY=PASS`

R2-01 的输入分别为 `assistant("a") → user([]) → assistant("b")` 与镜像的 `user("a") → assistant([]) → user("b")`。共享 Pydantic 模型实际保留中间空 list，但 converter 没有返回 `ConvertedRequest`，而是在 `messages[1].content` 抛 `invalid_content`；因此不存在可被后续 provider 合并的相邻 same-role wire items。独立 false-red 控制另以非空 list 中的空 text block验证 guard 没有把 `[]` 与 `[{"type":"text","text":""}]` 混为一谈，后者按 Spec 保留并通过。

R2-02 的源输入含 3 个 reasoning items：`first／C1`、两段 summary 的 `second+detail／C2`、以及 `summary=[]／C3` encrypted-only item；中间插入 1 个非 reasoning item以防类型过滤改变 reasoning 相对顺序。真实 forward 产生 3 个 thinking blocks，`MessagesRequest.model_validate()` 成功，public converter 最终产生 3 个 reasoning wire items；独立 expected 直接写明每项 summary 与 ciphertext，没有使用 converter 输出反算 expected。

### 目标正控变异

正控只在该 Python 进程内 monkeypatch `responses_reasoning_to_anthropic`，没有编辑候选文件。变异精确恢复已被 Spec 排除的旧机制：跨 reasoning items 聚合全部 summary，并只使用最后一个非空 ciphertext生成 1 个 thinking block。相同 R2-02 oracle 按目标原因失败为 `blocks=1 expected=3`；不是导入失败、fixture 解析失败或旁路断言。`finally` 恢复原函数后，同一基线链路再次通过并与变异前结果相等。

### 新增测试与上一 PASS 代表性抽样

先用 pytest `--collect-only -q` 精确选择以下节点，再用相同节点执行；collect 输出经节点行计数确认实际收集 **8 个测试实例**，执行结果为 **`8 passed in 0.62s`**，退出码 `0`：

- 空 content-list 参数化回归，共 2 个角色实例。
- 真实 forward → converter reasoning round-trip，共 1 个实例。
- encrypted-only reasoning primitive，共 1 个实例。
- multiple reasoning items no cross-item loss，共 1 个实例。
- heartbeat 期间不重启 upstream pull，共 1 个实例。
- upstream idle deadline，共 1 个实例。
- 无 primary error 时传播 close failure，共 1 个实例。

该数字口径为候选 `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`、上述 7 个 pytest node selectors 展开的 8 个参数化后实例，不是全仓测试数。执行后再次校验候选 `git status --short` 为空。

## 与上一 PASS 的关系

上一报告 `docs/tmp/260806-verify-bridge-foundations.md` 绑定旧候选 `614cacde72568d53170be714ea5c9a9b4d889a05`，已对 reasoning carrier／cardinality、request 字段矩阵、server-tool no-revive、tool identity、thinking capability facts与 session liveness primitive执行独立 probe和全量回归，并给出范围内 PASS。Merged-state review `docs/tmp/260806-review-code-bridge-foundations.md` 随后新增两项 major：空 content-list silent drop，以及缺失真实 forward→converter 跨片门。

本轮候选 HEAD 相对旧候选新增修复提交 `6a00f6f7aaa5083cebd7387208eca65b7df3bd79`。本报告不重复声称旧全量测试在新 HEAD 全部重跑，而是以两项独立追加 oracle、目标正控变异和上述代表性回归证明确认 review 新增的两个缺口已关闭，且抽样未发现上一 PASS 范围回归。

## 未验证边界

以下项目本轮没有执行，状态保持**未验证**，不是已证实缺陷：

- Anthropic route 的 Responses leg 选择与 capability／override precedence。
- HTTP SSE、upstream WebSocket、真实 ASGI route、wire headers 与 error envelope。
- Responses response assembler、stream／non-stream parity 与 terminal lifecycle。
- 完整 content-block buffering、continuous commit frontier、sink batch 与 delivery uncertainty。
- Route-level retry、approval、hooks、History、tokenization、cancel、shutdown、backpressure 与 resident quota。

## 结构怪味与方案反思

- `src/app/protocols/anthropic_responses.py:374-388` — **接受域与 transport 可表达域不同**：共享 `MessagesRequest` 接受空 list，而 Responses adapter 无合法等价表达。处置：本轮确认在 converter 专属边界 typed reject，不收紧共享模型，以免改变 direct Messages leg 公共接受域。
- `tests/unit/test_anthropic_responses_request.py:716` — **跨片 seam 曾缺少 production-chain 回归**：forward 与 reverse primitive 各自绿不能证明组合态。处置：新增测试已调用真实 forward、共享模型 validation 与 public converter；本轮再用独立 expected 和旧聚合变异验证其判别方向。
- **更好的内部替代方案**：对空 list 而言，全局 Pydantic `min_length=1` 会误改其他 protocol leg；占位、drop 或 merge 都改变语义。Converter-local typed reject仍是当前冻结合同下最准确的边界。Reasoning 链路没有比 production-chain oracle 更强而更小的内部替代；只测 codec 或单侧 helper 会重建同源假绿窗口。
- **判据判别力**：R2-01 同时有两种角色负样本与非空 list 正样本，分别防 silent drop 和 false-red；R2-02 的目标旧聚合变异按 cardinality 原因变红并恢复重绿，证明判据能区分目标正确／错误机制。本轮没有执行 converter“仅保留最后 decode”的第二种变异，因为用户要求一个目标正控，本次选取的 producer 聚合变异已经同时破坏 $N \rightarrow N$ 与 item-local ciphertext 合同。
- **成熟第三方方案**：Pydantic 能表达非空 list，但不能替项目决定约束应位于共享入站模型还是 Responses adapter；reasoning cardinality／carrier 是项目协议合同，也不存在可替代该跨层验收的通用第三方库。本轮无需新增依赖。

## 最终结论

候选 HEAD `6a00f6f7aaa5083cebd7387208eca65b7df3bd79` 在本轮追加范围内满足冻结 Spec：空 `user`／`assistant` content list 均以精确 typed error fail closed，未制造相邻 same-role wire items；3 个真实 reasoning items 经 production forward、thinking blocks、`MessagesRequest` 与 public converter 后保持 3→3、顺序、ciphertext 与 encrypted-only。目标旧聚合变异按预期原因变红，恢复后重绿；8 个新增／代表性回归实例通过，候选树保持 clean。

**范围内 verdict：PASS。完整 bridge verdict：本报告不作判定。**

> 评审状态：本报告是包含当前状态与验收结论的非平凡交付物。当前执行角色为 leaf verifier，按编排边界不得派生 reviewer；主会话在把它作为最终回放或放行依据前仍需安排独立文档复核。

# Anthropic Responses bridge research 独立事实评审

## 评审结论

- **评审范围**：`/home/xp/src/ghc-api-proxy-py/docs/agents/anthropic-responses-bridge/research.md`，逐项裁决 C1～C7；只报告 blocker／major。
- **总体 verdict**：**修复 major 后可进入下一阶段**。
- **blocker 数**：0。
- **major 数**：1。

## 固定证据基线

- 目标主仓：`/home/xp/src/ghc-api-proxy-py` @ `47d9ef101c4b81ac70d805b1da157b34d021d33d`。
- 主 upstream 当前 HEAD：`/home/xp/src/copilot-api-js` @ `2e7e998bc2ba150723f2fbe48fefd9eb5b6dbe03`；研究文档固定 baseline 为 `8d5c861c2e079b92401dd8ccd49695a363d078fe`。对 route／request／response／stream／delivery／相关 tests 的限定路径执行 `baseline..current` commit-tree 比较，changed paths 与 commits 均为空，因此本文基于旧 baseline 的 direct-bridge 结论在当前 HEAD 上未因这些路径的后续提交而失效。工作树有其他会话改动，本评审只采信固定 commit tree。
- refs：`ghc-api-py` @ `8d064a27308ed249da8c9ce7ecc54c89ee68c151`；`caozhiyuan-copilot-api` @ `6b97876927b7209a1e0f498e81927b32cc443e52`；`hooyoo-copilot-bridge` @ `2032fdd782aa1166eea0286977c59ab93eb5cab2`；`vscode-copilot-chat-upstream` @ `d62bf252c865fbf41550ce3076e918c52f0bced7`；`github-copilot-chat` @ `6ad6a351c60c8dab1b9a1e620ef9156b28005893`；`CLIProxyAPIPlus` @ `0c48ef58e0d37220367401b8f7cf689e2e50a701`；`awsl-maxx` @ `03d018fac3645b14d7b6d51b223b2148227c8992`。

## 双视角覆盖证据

### 机械核对

- 每次 shell 均在同一调用内 gate 目标主仓、主 upstream 与引用 refs 的物理 top-level 和 HEAD；读取外仓证据时使用 `git show <HEAD>:<path>`，未把脏工作树当作来源。
- 抽样超过最低 20 个最终 `file:line` 引用；其中明确逐行复核的引用组包括：目标仓 Anthropic／OpenAI routes、buffer primitive、Responses accumulator、SDK retry owner、pipeline retry、server-tool 决策文档；主 upstream resolver、router、driver、cell assembly、hub translation、request translator、tool-name sanitizer、non-stream response translator、reasoning carrier、commit boundary、ledger、buffered reducer、delivery owner；refs 的 request／stream translators、reasoning gate、并行 tool 状态、terminal 状态机与 Go 双向 converter。
- 对账了“已独立核验”“仅 agent 报告待核验”“未运行验证”三类标签；hooyoo 两项只把符号／调用点存在视为独立事实，没有把尚未闭合的行为升级为结论。
- 扫描了 direct bridge 的生产调用链与测试调用链；确认 request、non-stream response 和 stream translator 已进入 pipeline／cell 体系，且存在 unit／integration 测试源码。研究文档只声称测试源码存在并明确写“本轮未运行”，没有把源码存在冒充测试 green。

### 第一人称执行模拟

- 以新接手实施者身份按文档执行 route decision → direct request bridge → non-stream response → stream parser → block delivery → retry／error 分类，分别走 stream／non-stream、pre-commit／post-commit、unknown event、tool／reasoning、HTTP／WS 与 cap overflow 分支。
- 以同步维护者身份执行 old HEAD → current HEAD、changed paths、生产接线、测试接缝、采纳／不采纳与 provenance 记录流程；watch list 和四类 delta 判定可直接执行，且明确禁止仅凭 commit title、helper 存在或测试源码更新状态。
- 以产品边界检查者身份追踪所有 live sink／retreat-to-live 描述：研究文档把 upstream 的 live retreat 明确列为不可照搬，并反复要求目标实现只能 block-level commit、背压／spill／显式失败，没有推翻用户 buffering 裁决。

## C1～C7 裁决

| 命题 | 裁决 | 依据摘要 |
|---|---|---|
| C1 来源 repo＋HEAD 明确 | 通过 | 目标仓、主 upstream 与全部 refs 都给出绝对 repo 和完整固定 HEAD；本评审实测 HEAD 如上。 |
| C2 `file:line` 引用真实支持命题 | **major** | 大多数抽样支持命题，但多处核心引用区间在其声称的关键动作之前结束，未满足“引用本身支持命题”。 |
| C3 最新 direct bridge route／request／response／stream／test 结论准确 | 通过 | 主 upstream baseline 到当前 HEAD 的限定路径无提交差异；生产接线和测试源码与研究结论一致，已知 request order、sanitizer、non-stream reasoning 缺陷仍在。 |
| C4 refs 的“可借鉴／不可照搬”有证据 | 通过 | 连续 run flush、identity 分桶、terminal staging 等可借鉴项，以及私有 carrier、默认值、逐 delta 输出、Go 事件缺口等不可照搬项均有固定 commit tree 证据。 |
| C5 agent 报告待核验与独立核验分开 | 通过 | 状态标签定义清楚；hooyoo 行为闭环和历史 commit 归因仍留在待核验区，没有进入设计定论。 |
| C6 持续同步方法可执行 | 通过 | baseline gate、watch list、四类 delta 判定、差分 oracle 和 provenance 记录形成可操作闭环。 |
| C7 不推翻用户 buffering 裁决 | 通过 | 文档把 block-level buffering 置为不可推翻边界，并明确禁止 downstream live flush 和 cap retreat-to-live。 |

## 事实性发现

[major] `docs/agents/anthropic-responses-bridge/research.md:44,46,110,188` — 多处核心 `file:line` 引用没有覆盖其声称的关键动作，导致 C2 的可追溯合同不成立 — `research.md:44` 引用 `anthropic.py:53-100`，但 stream passthrough／idle timeout／SSE return 实际位于 `anthropic.py:106-120`；`research.md:46` 引用 `openai.py:80-106`，但 `client.responses(request)` 实际位于 `openai.py:107-112`；`research.md:110` 引用 `driver.ts:1335-1390` 来证明 boundary 上提交完整 block，但实际 flush、`committedAny` 与成功后 ledger 记录位于 `driver.ts:1397-1417`；`research.md:188` 引用 `responses-stream-translation.ts:88-125` 的 default branch，但 default／`return []` 实际位于 `:142-143`。这些命题的源码方向均正确，问题是读者按所给最终行号无法看到决定性证据，且同类偏短边界重复出现在目标现状、主机制和 refs 反例三类核心段落。修复建议：至少将四处范围扩为能够覆盖完整动作的 `anthropic.py:63-120`、`openai.py:87-112`、`driver.ts:1357-1418`、`responses-stream-translation.ts:88-144`，然后对全文所有 `file:line` 做一次“命题中的每个动词都落在引用范围内”的机械复验；不要只验证文件和起始行存在。

## 主观建议

无。除上述 major 外，未发现需要按本次口径上报的 blocker／major。

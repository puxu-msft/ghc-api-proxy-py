# Reasoning carrier Spec 协议与数据模型评审

## 快照与结论

- snapshot_time: `2026-09-04T05:35:35+08:00`
- reviewed_object: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md`
- object_snapshot: mtime `2026-09-04T05:27:21.222939333+08:00`，size `20729` bytes
- source_root: `/home/xp/src/ghc-api-proxy-py`
- source_rev: `45e7cfb972b6f9df5874a8455d9961d692f2bba2`，由 `/home/xp/src/ghc-api-proxy-py/.git/HEAD:1` 与 `/home/xp/src/ghc-api-proxy-py/.git/refs/heads/main:1` 读取
- verdict: `needs-fix`
- finding_counts: blocker=1，major=3，total=4
- scope: wire grammar、跨协议方向、可逆性、兼容迁移，以及用户指定的 C1-C9；只报告 blocker／major。
- reviewer_role: 已在读取对象前尝试加载 `my-agents:as-reviewer`，运行时返回 `Unknown skill`；随后按用户给定 reviewer 契约执行，并加载 `my-skills:qualifying-a-claim-and-its-coverage`。该能力缺失不影响本次只读核验完成度。

## 证据方法与能力边界

- 完整读取 Spec，并对照当前 v1 codec、typed IR、双向 reader／writer、streaming delivery、现有测试与历史 v2 实验：`src/app/pipeline/translation_driver/reasoning_carrier.py:10-19,52-66,77-142`、`src/app/pipeline/translation_driver/content.py:32-62,64-86`、`src/app/pipeline/translation_driver/anthropic_messages.py:57-92,220-236`、`src/app/pipeline/translation_driver/openai_responses.py:522-535,567-568,768-801`、`src/app/pipeline/delivery/formats/openai_responses.py:324-349`、`tests/unit/pipeline/translation_driver/test_reasoning_carrier.py:17-103`、`tests/unit/anthropic/test_responses_reasoning.py:13-163`、`exp/carrier-v2/*.py`。
- 以安装的官方 SDK 类型作槽位形状的独立佐证。可复现命令：`uv --directory /home/xp/src/ghc-api-proxy-py run python -c 'import anthropic,openai; print(anthropic.__version__,openai.__version__)'`，快照输出为 `1.0.0 3.3.1`；对 `ThinkingBlock`／`ThinkingBlockParam` 的 `__annotations__` 显示 `signature` 与 `thinking` 均为 `str`，对 `ResponseReasoningItem`／`ResponseReasoningItemParam` 显示 `encrypted_content: str | None`／`Optional[str]`。
- 没有运行产品 test suite：当前没有 v2 实现，单测只能证明现有 v1 行为，不能证明本 Spec 可实现。F-01 使用纯 grammar 构造作信息论反例；它不依赖当前 codec。

## C1-C9 逐项结果

| 条目 | 结果 | 依据与判定 |
|---|---|---|
| C1 | PASS | 两个槽位由 `spec.md:34,91-94` 明确允许；carrier 不进入原生 upstream 由 `spec.md:39,155-167` 规定，actual-wire 负向验收在 `spec.md:239`。官方 SDK 类型探针确认两个槽位均可承载字符串；该证据只证明形状可放入，不证明 provider 会签发该值，而 Spec 也未作后一声称。 |
| C2 | FAIL | 单个 record 的恢复目标正确限定在 `spec.md:121,135,141`，换 provider 的止损也在 `spec.md:169-173`；但 envelope 缺少合法 record 组合与完整 slot profile，导致若干 grammar-valid 输入没有唯一方向判定，见 F-02。 |
| C3 | FAIL | UTF-8 byte lengths、零长度、顺序与 extensions 的恢复机制本身成立，见 `spec.md:123-130`；但 layout omission 与“删除 layout 必须被抓住”在信息上不可区分，且 canonical producer 允许两种 spelling，见 F-01。 |
| C4 | FAIL | outer malformed、unknown version 与 foreign 的主分类集合存在，见 `spec.md:175-192`；然而 typed-schema／presentation 边界、多个同时异常的优先级、slot／record profile 均未闭合，见 F-02。 |
| C5 | PASS | consumer-first、producer-later、producer-only rollback 与 v2 consumer 不撤回完整写在 `spec.md:94,211-218`；永久 v1／`copilot-api-js` v1 合法主路径由 `spec.md:13,214` 保留，当前精确 spellings 与两种 bare compatibility 由 `reasoning_carrier.py:10-17,77-100` 及 `test_reasoning_carrier.py:46-74` 固定。 |
| C6 | FAIL | absent／present-empty 的 record-presence 设计正确，见 `spec.md:117-121`，Anthropic bare 的 `""`／非空投影也明确，见 `spec.md:144-149`；但空 `records` payload、slot profile 与 Responses-slot record cardinality 未定义，故“两槽规则自洽”的全称结论不成立，见 F-02。 |
| C7 | PASS | `spec.md:44` 明确只承诺 JSON value 等价，不承诺空白、object key 顺序或 escape spelling 的原始 bytes；`spec.md:111` 对 consumer 的 key-order／escape 容忍与此一致。 |
| C8 | FAIL | `spec.md:199,217,272` 宣告 ordinal-only v2 被取代，但当前两个可执行实验仍自称 canonical／frozen v2，且 Spec 把处置延后到实现期，见 F-04。 |
| C9 | FAIL | malformed／unknown 的 consumer-only oracle、carrier actual-wire 泄漏检查和 native opaque 不互冒写在 `spec.md:224-240`；但 layout 删除控制不可满足，且旧 flatten 的指定正控不是合法 `summary_text` wire，见 F-01、F-03。 |

## Findings

### F-01 — blocker — layout omission 使强制删除变异在信息论上不可判定
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md:128-130,232`
- evidence: `:128` 允许 canonical summary 省略 layout，`:232` 又要求删除 layout 必须失败或得到 presentation mismatch；“可省略”还让同一语义有两种所谓 canonical producer spelling。
- failure_scenario: 原值为 `summary=[{"type":"summary_text","text":""}]`、`encrypted_content="ENC"`；删掉 `[0]` layout 后的 envelope 与合法原值 `summary=[]`、同一 opaque record、`thinking=""` 完全相同，decoder 无可观察位可区分。
- impact: 任一实现必须在“接受合法 omission”和“抓住单侧删除变异”之间违约，C3/C4/C9 无法同时验收。
- recommendation: 定义 envelope profile，并在任何 payload envelope 中强制携带 layout，包括 `[]` 与单 part；只允许真正无 records 的 bare spelling 省略 layout，或撤销删除可检测要求。为满足用户要求，推荐前者。

### F-02 — major — 缺少 record 组合、slot profile 与分类优先级
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md:98-113,117-149,175-192`
- evidence: grammar 仅禁重复 type，允许空 records、两种 Anthropic state records 共存及跨 source-family 混合；只有 thinking signature 明确了错误 slot，redacted／OpenAI layout／OpenAI opaque 没有对称规则；`:130` 的 typed cardinality 失败又被 `:190` 指为 presentation mismatch。
- failure_scenario: Responses slot 同时带 signature 与 redacted data，或 redacted data 带非空 summary，均为 grammar-valid；恢复一个还是两个 block、丢哪份信息、报 malformed／direction／presentation 都无唯一答案。unknown record 与上述异常共存时也可同时命中多个分类。
- impact: classifier 无法做到互斥，writer 无法维持一 item 对一 block，且不同实现会对同一 wire 作不同止血，影响 C2/C4/C6 与 unknown-record 升级路径。
- recommendation: 增加按 outer slot 的合法 profile 表、互斥／必需 records 与 summary constraints，并规定 structural malformed → unsupported → direction mismatch → presentation mismatch 的单一优先级或等价的明确 precedence。

### F-03 — major — summary flatten 指定正控本身不是合法 wire
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md:68-81,230-232`
- evidence: `:68-81` 规定当前合法 part 必须是 `{"type":"summary_text","text":"..."}`，但 `:231` 的强制正控三个 part 都缺少 `type`。
- failure_scenario: 严格的新 reader 在进入 layout／flatten 路径前就应将该 fixture 判为 malformed 或 unsupported；测试失败不能区分“旧 flatten 被抓住”和“fixture 非法”。
- impact: C9 对根因修复的主要正控可能 false-red，也不能证明合法多个 parts、空 part 与 astral Unicode 的往返恢复。
- recommendation: 把三个 part 都补成完整合法 shape，并让旧实现只因归并为单 part而失败、新实现以原列表 JSON value 为独立 oracle 通过。

### F-04 — major — ordinal-only v2 可执行转录仍冒充当前 canonical v2
- primary_location: `/home/xp/src/ghc-api-proxy-py/.dev/docs/reasoning-carrier/spec.md:199,217,272`
- evidence: `exp/carrier-v2/gen_v2_vectors.py:1-17` 自称“Canonical v2 vectors”却生成旧 `{tag,encrypted_content,i}`；`check_i_algorithm.py:1-6` 自称“frozen algorithm”并定义 ordinal `i`。Spec `:217` 仅要求实现时再更新／归档。
- failure_scenario: 实现者或验收者现在运行实验，会得到与 `records` envelope 冲突但自报 canonical／frozen 的 v2 vectors；两份可执行材料对同一 namespace 给出相反合同。
- impact: C8 的单一权威在可执行 oracle 层未闭合，并违反 `.claude/rules/00-development-workflow.md:14` 的 Spec 转录必须同改规则。
- recommendation: 在本轮 Spec 修订中立即更新该实验为当前独立 vectors，或归档并去掉 current-canonical／frozen 自述；不得等到实现阶段。

## 总结判定

当前 Spec 的跨协议总体方向、opaque issuer 边界、UTF-8 length 基本方案、v1 迁移顺序与 value-vs-bytes 边界是可继续采用的基础，但 F-01 是不可由实现补足的合同矛盾，F-02 还使完整 grammar/classifier 非确定。结论强度足以据此暂停定稿与实现；修订并处置以上 4 条后再复评。

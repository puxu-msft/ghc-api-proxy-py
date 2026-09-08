# Token-counting Spec review coordinator checklist

性质：本轮独立 Spec review 的派活方核查清单。它不代替 reviewer 报告、处置账或 living Spec。

## 评审对象与目标

- 评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/token-counting/spec.md`。
- 外部权威：`/home/xp/src/ghc-api-proxy-py/docs/.human-controlled/api.md`、`config.example.yaml`、`ghc-api.md`、`message-translation.md`、`request-pipeline.md`。
- 目标：核验 Spec §14 的 production-implementation 前置条件。只有 reviewer 对 blocker／major 给出 0／0，且 coordinator 对报告逐条处置后，production code 才可修改。
- 本轮新增触发：用户报告合法 count request 中的字面`<|endoftext|>`被`tiktoken 0.14.0`默认 special-token guard 拒绝并返回500；Spec 已先在§4.1、§12.2 A3、§13和修订记录中把此类 spelling 定义为 ordinary text。

## 可核验状态断言

- C1．权威边界：Spec 将人控文档和直接用户裁决置于最高层，并把实施者派生决定与用户逐字裁决分开；任何冲突都不会由实现者擅自改写用户意图。
- C2．公开成功合同：合法 Responses target 即使含 opaque reasoning、media、unknown item或 tokenizer special-token spelling，local leg 仍返回完整且仅有`{"input_tokens": N, "estimated": true}`的对象，其中`type(N) is int`且`N >= 1`。
- C3．普通文本语义：客户端字符串中的`<|endoftext|>`等 configured-tokenizer special-token spelling 不获得控制语义，也不得触发 tokenizer guard；该规定覆盖 Anthropic known text、Responses known text与序列化 tool JSON。
- C4．Direct Anthropic 合同：remote success 保留标准`input_tokens`及上游存在时的`context_management.original_input_tokens`；local fallback 不合成后者。
- C5．Counter 编排：所有腿共享同一 frozen target；providers 懒执行；具名 provider 不得为计数重映射 model；合法 Responses target 的 opaque／media／unknown 只降低 confidence，不使 local unavailable。
- C6．估算边界：opaque carrier、base64 media和 unknown opaque bytes 不作为 ordinary text；known text、结构特征和低置信 baseline 不被静默丢失。
- C7．学习闭环：label 来自同一 actual sent attempt 的 raw total input usage；prequential evaluate-before-learn、exactly-once、identity隔离、持久化、bounds和drift条款不存在互相矛盾或无法实现的断边。
- C8．可判否性：§12 每项证据明确其不能冒充什么；关键判据同时含正确样本和单一目标缺陷注入；A3 的 special-token spelling 正反样本会在错误实现下变红。
- C9．转录同步：§13 指明既有与计划测试的权威条款；本次 special-token 修复会同步`test_local_token_worker.py`、`test_responses_estimator.py`及生产入口相关回归测试，而不会把旧 failure expectation 留成假绿。
- C10．流程门：Spec 是 living authority，不被描述为 frozen；§14 只限制 production code 的时序，不阻止先修正 Spec 本身；本次报告闭合前生产文件保持未改。

## Reviewer 必查失效面

1. 找 blocker／major 级的权威错置、用户裁决误归因、公开 wire 缺口、内部条款冲突、无法判否的关键验收或实现上不可闭合的合同。
2. 对 special-token spelling 条款检查范围是否过窄：message、system／instructions、tool schema／JSON以及 Anthropic／Responses 两条 local path 是否都受同一 ordinary-text 语义约束。
3. 查“legal payload 必须 best-effort 成功”与“不可恢复 local operational failure 显式失败”的分界，确认 tokenizer guard 不能被误归到 operational failure。
4. 查§12证据层级，防止 synthetic tokenizer round-trip 冒充 provider 账单精度；它只能证明本地文本可编码和调用链不500。
5. 明列本轮未采纳或被否的路线；即使为空，也写“无”。至少评估`allowed_special={"<|endoftext|>"}`、仅在 endpoint catch ValueError 后fallback、只修 Responses 不修 Anthropic、继续保留旧 failure test 这四条路线。

## Coordinator 收件核查

1. 核对报告尾部`delivery_complete: true`、`completed_at`、`finding_total`与各档计数自洽。
2. 逐条独立核验 blocker／major 的事实依据与引文完整子句，不采信 reviewer 的结论标签本身。
3. 把每个 finding 写入独立 disposition；无 finding 也记录0／0及其覆盖范围。
4. 若有 blocker／major，先修 Spec并唤醒同一 reviewer 复审；只有0／0且无待回应标注时才打开 production implementation gate。

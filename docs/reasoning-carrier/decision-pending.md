# 待裁：旧 Responses 推理历史切换至不支持 Responses 的模型

## 现状、约束与风险

2026-09-23 的一次真实请求在原会话中向 `sonnet`（实际解析为 `claude-opus-5.5`）继续发送历史；23 条消息含 8 个合法项目 carrier，均承载 Responses 原生加密推理状态。目标模型目录只开放 Messages 与 Chat Completions，无法无损接收该状态。请求在 upstream send 前被 last-mile guard 以 400 拒绝；原始证据仅保留在本机敏感 capture 中，安全摘要见 [`reports/260923-cross-model-carrier-rejection.md`](reports/260923-cross-model-carrier-rejection.md)。

活 [`spec.md`](spec.md) §1、§7.3 已裁定原生 opaque state 只能回到所属协议腿，项目 carrier 不得进入 provider 原生槽，也不得把可见 summary 冒充为完整状态。自动剥除会改变下游看到的历史；直接把 Responses 密文送给 Claude 违反协议边界。两条当前会话级 capture 规则仍生效，未来匹配请求仍会采集包含凭据的 full transport；取证完成后应单独撤销。

## 需要用户决定的行为边界

| 路径 | 好处与适用情形 | 代价和风险 |
|---|---|---|
| **A. 保持无损拒绝；为目标模型新开会话** | 维持已裁定的数据完整性与上游协议真实性；立即可行，无需改代码或服务 | 旧会话不能原样续用；用户须显式带入需要保留的非 opaque 上下文 |
| **B. 为跨模型换腿定义显式有损迁移** | 有机会让携带旧历史的请求继续；适合用户明确接受 reasoning continuation state 丢失 | 必须先决定删除哪些历史 thinking、如何向客户端可见地告知、是否要请求级 opt-in；响应可能改变，不能承诺与旧会话同等连续性；需先修订用户裁决过的 Spec，再实现并实测 |

**建议 A，信心高。** 完整 capture 的 carrier record 类型、运行时目录的 endpoint 集合、以及无 upstream request 的事件序列共同支撑“不能无损直接发送”的判断。**不确定性：** B 的精确客户端告知机制和有损后模型行为尚无裁决或真实测试；不能在这里承诺一种自动降级必然成功。

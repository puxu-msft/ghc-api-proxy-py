# 2026-09-23 跨模型 carrier 拒绝：一次真实请求的结构化取证

**范围：** 主树 `main@061aff32` 的活代码及 4141 运行时，来自会话级 rule-selected full transport capture 的请求 `b505b387-f8bc-45c3-b807-c2c235c39c4c`。仅在本机内存中解析原始事件，报告不保存或显示消息正文、密文、认证头和原始 session identity。

## 观测与因果

- 入站 `/v1/messages` 请求 `model=sonnet`、`stream=true`，有 23 条 message；其中 8 个 assistant thinking block 的签名由同一 codec 识别为合法 `project_v2`，每个都含 `openai.responses.reasoning.encrypted_content` 与 `openai.responses.reasoning.summary_text_layout` records。旧会话的这些块不是 Anthropic 原生 signature。
- 活路由把 `sonnet` 解析成 `ghc-msft/claude-opus-5.5`；该模型当前目录只发布 `/v1/messages` 与 `/chat/completions`，没有 `/responses`。原生 Responses 密文不能投影为目标 Anthropic signature，也不能让 Chat Completions 接管它。
- Capture 含完整入站 body、`upstream.attempt.start`、失败的 `upstream.attempt.end` 与 client response；**没有 `upstream.request.start`**。400 的 `synthetic reasoning carrier project_v2 reached provider last-mile` 是代理在网络调用前的明确拒绝，不是上游 400，也不是 raw capture 未命中。
- 路径是入站 Anthropic → 目标 Anthropic 的 direct leg；这种 same-format 路径没有跨格式 consumer。last-mile guard 在 `src/app/pipeline/subscribers/reasoning_carrier.py` 按 `spec.md` §7.3 拒绝尚未解包的项目 carrier。即使把它解包，得到的也是 Responses 原生密文；目标缺 Responses 协议腿，仍无无损去处。

**已排除：** carrier 损坏（codec 分类均为合法 `project_v2`）、上游拒绝（未发送 upstream request）、模型别名未命中（路由确认为 `claude-opus-5.5`）、取证未开启（本次已有完整入站证据）。捕获证明本次原因，不保证该会话日后所有失败都同因。

**处置状态：** 不是可以保持当前合同而改一个 decoder 的源码缺陷。按现行合同，恢复服务的无损办法是让客户端使用不携带旧跨协议 reasoning state 的新会话；在原会话自动删除／改写这些块会改变模型上下文，必须先经用户裁定并修订 Spec。现阶段不修改生产请求，也不向包含认证头的 capture 文件作任何公开引用。

**设计层观察与重议触发：** carrier 标记了来源协议，却没有能使任意目标模型理解该 opaque state 的通用表示；模型切换和完整旧历史回送之间存在真实不可移植边界。若用户决定让原会话有损续用，先裁定丢弃范围、可见告知和适用模型，再用本请求形状构造隔离回归；任何静默剥除都不算修复。

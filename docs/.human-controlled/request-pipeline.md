# 模型请求的处理管线

主线：请求从 `app.server.routes` 进入，经过 `app.pipeline` 处理后，交给 `app.model_provider` 上游模型提供方。

`app.pipeline` 负责驱动*模型请求*的处理，包括消息转变（包括整形）、上游收发与重试机制。

首要任务是路由判定，包括：
1. 关联到哪个模型提供方的哪个上游模型和端点。
2. 输入格式与请求的模型之间是否需要格式翻译。见 [message-translation.md](./message-translation.md)。

比如，从 `POST /v1/messages` 输入的 anthropic-messages 格式的模型请求。如果要求访问 `gpt-5.6-terra` 模型，且无模型映射配置，根据上游提供方的信息，该走 `gpt-5.6-terra@openai-responses`；如果要求访问 `claude-sonnet-5` 但显式配置了模型映射关系 `claude-sonnet-5 -> gpt-5.6-terra@openai-responses`。那么需要在 anthropic-messages 格式与 openai-responses 格式间做翻译——发给上游的是 openai-responses 格式，做一次翻译；返回给客户端的是 anthropic-messages 格式，再做一次翻译。

根据情况，可能走直连路径或翻译路径。

为了充分可扩展：
1. 提供统一的上下文对象模型，而不是在各个管道间做数据模型转换。每个客户端请求都由一个 ClientRequest 描述，每次上游尝试都由一个 UpstreamAttempt 描述。
2. 可扩展点以事件订阅的形式提供，允许功能模块订阅（传入唯一 id 和可选的“插入到谁之前/后”）。订阅者能够修改上下文对象，也可以通过抛出不同的异常来触发中止/重试。

2026-08-16：这里“不同的异常”分两类，已知异常（如 `UpstreamError`、`UpstreamTimeout`、`UpstreamRateLimit`、`PipelineRetry`、`PipelineAbort`）会按内置逻辑处理；未知异常则总是中止。

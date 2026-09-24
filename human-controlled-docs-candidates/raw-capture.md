# 原始请求捕获配置候选

> 2026-09-08 用户裁决：raw capture 必须是二进制结构化文件，绝不能使用 JSONL，也不能用长度前缀 JSON 冒充。权威合同与修订记录见 [`.dev/docs/raw-capture/spec.md`](../docs/raw-capture/spec.md)。

代理默认不为任何请求创建 capture。通过 HTTP API 创建并持久化调试规则后，只有命中 provider、已解析 model-id、session-id 和可选 agent-id 的请求才会开启全量记录：

```text
POST /api/debug/capture-rules
{"provider":"sub2api","model_id":"deepseek-v4-pro","session_id":"session-id","agent_id":"agent-id"}
```

规则持久化在 SQLite；`GET /api/debug/capture-rules` 列出规则，`DELETE /api/debug/capture-rules/{id}` 删除规则。capture 文件目录、压缩级别和配额仍由 `observability.raw_capture` 的存储字段配置，但这些字段不决定哪些请求被记录。

每条记录会保存入站原始请求 body、实际发往上游的 request body、上游 response body，以及客户端实际收到的 response body。逻辑流使用 RFC 8742 CBOR Sequence，每条事件是一个 CBOR map，body 使用原生 CBOR byte string；每个 item 独立压成 zstd frame，再追加到 `session-<hash>/agent-<hash>.cborseq.zst`。这不是 JSON 或私有长度前缀 envelope。上游重试与流式重开会记录 attempt 边界，未完成的上游流会显式标记为 `complete: false`。

写入通过有界后台队列完成，并受单文件与总目录的实际压缩后字节配额限制；达到配额后当前捕获停止，不影响请求本身，并在请求完成时用不含 body/密钥的安全元数据明确报告 capture 不完整及取证影响。捕获内容可能包含完整 prompt、工具输入、工具结果和模型输出，只应在受控的本地诊断窗口开启。请求头和认证信息不写入捕获文件。

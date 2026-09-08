# 原始请求捕获配置候选

以下配置默认关闭。开启后，代理会按客户端 session 与 agent 将连续请求追加到 zstd 压缩文件中：

```yaml
observability:
  raw_capture:
    enabled: true
    directory: "$XDG_DATA_HOME/ghc-api-proxy/raw-captures"
    compression_level: 3
    max_file_bytes: 536870912
    max_total_bytes: 4294967296
```

每条记录会保存入站原始请求 body、实际发往上游的 request body、上游 response body，以及客户端实际收到的 response body。请求与响应 body 使用 Base64 放入 JSON 事件，再以连续 zstd frame 追加到 `session-<hash>/agent-<hash>.jsonl.zst`。上游重试与流式重开会记录 attempt 边界，未完成的上游流会显式标记为 `complete: false`。

写入通过有界后台队列完成，并受单文件与总目录配额限制；达到配额后当前捕获停止，不影响请求本身。捕获内容可能包含完整 prompt、工具输入、工具结果和模型输出，只应在受控的本地诊断窗口开启。请求头和认证信息不写入捕获文件。

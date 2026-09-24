# `message-translation.md` 候选修订

`docs/.human-controlled/message-translation.md` 属于用户控制文档，本候选不直接修改它。

建议把其中的术语：

- “输入格式”改为 **client wire format**；
- “上游模型格式”改为 **upstream wire format**；
- `inbound.from-*` / `outbound.to-*` 的示例改为 `decode.from-*` / `encode.to-*`；
- 明确所有三种 wire format（Anthropic Messages、OpenAI Responses、OpenAI Chat Completions）都经过 typed semantic IR，包括 same-format round trip；
- response-side 未知结构按 source scope 保留为 opaque payload，目标 codec 不支持时 skip 并记录 structured warning；
- retry 默认复用 post-prepare target payload，仅显式 target-format change 才从当前 wire payload decode/encode。

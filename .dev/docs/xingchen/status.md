# Xingchen model provider 当前状态

更新时间：2026-09-04

行为权威：[`spec.md`](spec.md)

评审处置：[`review-disposition.md`](review-disposition.md)

## 已实现

`main` 的 `0cd1641aae90b4758a6ec4fc0fa053d24bf5906c` 包含 Xingchen chat-only model provider：

- Pydantic discriminated union 配置，Xingchen 静态模型目录与构造期 reload pinning。
- 对最终 JSON bytes 的 TeleAgent cloud gateway 双层 HMAC 签名。
- `Authorization` gateway key 与完整 `X-Token` 双 credential 头。
- 原生 OpenAI Chat Completions 非流式与 SSE 上游发送。
- Messages、Responses、Embeddings、WebSocket 和远端 token counting 的 fail-closed 能力边界。
- 每 provider 独立 outbound client 与关闭生命周期。
- `debug models` 的 static/upstream catalog provenance。
- Xingchen CLI auth/login/logout 的零副作用拒绝。
- `/api/config` 对 `gateway_api_key` 和 `x_token` 的精确展示层遮盖。
- SDK/httpx2 共享 upstream error normalization，含 `Retry-After-Ms`。

Reviewed source 保存在 `archive/260904-xingchen-provider`，精确指向 `2ed92c5ee15aa28726673343a2df290537da494f`。

## 验证快照

合并态基线：`0cd1641aae90b4758a6ec4fc0fa053d24bf5906c`。

```bash
uv run --frozen ruff check src tests
uv run --frozen pyright src tests
uv run --frozen pytest tests --cov=app --cov-report=term --cov-fail-under=80
```

结果：Ruff 通过；Pyright 0 errors、0 warnings、0 informations；pytest 2263 passed、2 skipped；coverage 91.69%。

协议评审与修复后代码复评均为 0 blocker/major。原始转录位于 [`reports/`](reports/)。

## 未纳入本次范围

- Anthropic/Responses 与 Chat 之间的 request、response 或 stream translation。
- OAuth、refresh token、自动 credential 续期或 TeleAgent 本地状态抽取。
- local-v1、本地完整 agent serve 或 AKSK。
- 真实 Xingchen 网关 canary。

真实 canary 会使用有效 credential 并消耗额度，需要新的明确指令。当前验证没有向真实 Xingchen 网关发送请求。

## 用户文档状态

`docs/.human-controlled/config.example.yaml` 由用户控制，本次未修改。可选配置材料位于 [`.dev/human-controlled-docs-candidates/xingchen-provider-config.md`](../../human-controlled-docs-candidates/xingchen-provider-config.md)，尚未被用户摘入，因此不能描述为现行用户配置 authority。

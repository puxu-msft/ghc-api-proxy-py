# Xingchen provider 协议一致性评审

> 转录件。原评审者为先前解析 TeleAgent 协议的只读 Explore agent；该运行身份不能写报告文件，因此由主会话于 2026-09-04 原样转录结论。评审对象是 feature worktree 冻结提交 `14a5fbec1f7abd349c45058b89f2c651ec2555d1`，基线 `39274d7bc3601f2236ffdfc52ea6f34f885ba405`。未发真实网络请求。

## Verdict：PASS

未发现 blocker/major；`my-agents:as-reviewer` 当前未挂载。

- **C1 PASS**：仅发布 Chat endpoint，并在发送和 count-token 前执行能力门。  
  `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/model_provider/xingchen/provider.py:17,32-36,88-117`；非 Chat ingress 零网络集成覆盖见 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/tests/int/test_xingchen_provider.py:136-159`。

- **C2 PASS**：复制顶层 payload，流式扩展采用 `setdefault`，嵌套 `stream_options` 另行复制；仅一次 `dumps`，同一 `body` 用于 HTTP content 和签名。  
  `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/model_provider/xingchen/client.py:58-69,84-97`。

- **C3 PASS**：JWT 恰三段取第三段，否则完整 token；两层 HMAC、LF/斜线连接、Unix 秒、UUIDv4、最终 request URI、appVersion、第二层 hex ASCII key均正确。  
  `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/model_provider/xingchen/signing.py:17-61`，对应外规 `/mnt/c/Users/xp/.local/share/TeleAgent/TeleAgent的工作空间/TeleAgent模型调用协议规格书.md:343-378`。

- **C4 PASS**：provider-owned headers 完整且不可被大小写变体覆盖；`Authorization` 与 `X-Token` 正确分离；upstream request ID 与 nonce 强制不同。  
  `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/model_provider/xingchen/client.py:15-35,71-75,99-124`。

- **C5 PASS**：成功 stream 直接返回、不预读；非 2xx 先读取 body，再抛出并归一化；client 内只有一次 send、无内部 retry loop。  
  `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/model_provider/xingchen/client.py:126-140`；保留 status/headers/body bytes 的归一化见 `/home/xp/src/ghc-api-proxy-py/.claude/worktrees/xingchen-provider/src/app/model_provider/upstream_errors.py:95-121,144-189`。

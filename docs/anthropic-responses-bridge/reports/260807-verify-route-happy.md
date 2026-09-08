# Anthropic Responses route happy-path 独立验收

- **候选**：`/home/xp/src/ghc-api-proxy-py-route-happy`，`feat/anthropic-responses-route-happy@f3a5a768491c542224103a87b75e5bb39803ac4a`。
- **base**：`80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- **冻结行为 oracle**：`docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。
- **验收方式**：生产 `create_app()`、真实 FastAPI `POST /v1/messages` route、`httpx.ASGITransport`、生产 dependency injection／pipeline／route policy／request converter／response converter／error mapping；仅以 fake upstream 替代外部网络，并以独立静态 Responses fixture定义 expected。未引用候选 tests 的 expected，也未执行候选测试来替代验收。
- **总体判定**：**`FAIL`。** 用户点名的 route-happy 矩阵全部通过，route 反转正控也按目标原因变红；但同一真实 ASGI probe 实证发现 Responses-specific header 被下发给 Anthropic 客户端，违反冻结 Spec Header 契约，因此不能给 route-level 整体 `PASS`。
- **完整 stream**：**`UNVERIFIED`。** 本轮只证明 selected Responses＋`stream=true` 在 upstream 零调用时返回 typed Anthropic error；这不是完整 stream 实现或 stream conversion 的通过证据。
- **候选树写入**：无。执行前后候选树均为上述 HEAD 且 `git status --porcelain` 为空。

## 从 Spec 独立推导的验收矩阵

| 验收项 | 独立 expected | 实际结果 | 判定 |
|---|---|---|---|
| Responses-only non-stream route | 只调用 Responses 一次，Messages 零调用 | Responses `1`，Messages `0`，HTTP `200` | PASS |
| non-stream text／reasoning／tool／usage | block 顺序固定为 `thinking → text → tool_use`；reasoning 使用项目主 v1 exact carrier；tool 保留 `call_id`／name／JSON input；usage 使用 `I=max(0,T-R-W)` | 顺序一致；`opaque-😀` carrier exact；`call_acceptance_01`／`weather`／`{"city":"Paris"}` 保留；`T=100,R=20,W=10,O=30,Q=12` 得 `input=70,cache_read=20,cache_creation=10,output=30` | PASS |
| explicit Responses override＋双支持 | override 优先，Responses `1`，Messages `0` | 符合 | PASS |
| explicit Messages override＋双支持 | override 优先，Messages `1`，Responses `0` | 符合 | PASS |
| auto＋双支持 | 固定选择 Messages，Messages `1`，Responses `0` | 符合 | PASS |
| `PRE_SEND` 后转换 | hook 把 Anthropic marker 从 `ORIGINAL-MARKER` 改成 `PRE-SEND-MARKER`；最终 Responses wire 只能含后者 | wire 含 `PRE-SEND-MARKER` 且不含原 marker | PASS |
| approval／History／context／attempt single owner | pending approval 峰值 `1`、approval 调用 `1`、History started／finalized 各 `1`、同一 context object／request id、attempt 仅 `[0]`、真实 exchange `1` | 全部符合；History original payload仍保留 `ORIGINAL-MARKER` | PASS |
| Responses upstream HTTP 429 | Anthropic HTTP `429` error envelope，`rate_limit_error`，保留稳定 message／code／`retry-after` | body 为 `RATE-LIMIT-MARKER`＋`rate_limit_exceeded`，`retry-after=7`，Responses `1`，Messages `0` | PASS |
| selected Responses＋stream | typed Anthropic error，HTTP `400`，Responses／Messages 网络调用均为 `0` | `responses_stream_not_supported`，两类调用均 `0` | PASS；完整 stream 仍 UNVERIFIED |
| Header contract | Responses-specific header 不得下发 Anthropic 客户端 | `x-internal-openai: must-not-forward` 出现在客户端响应 | **FAIL** |

## 独立 fixture 与 oracle

Responses success fixture 的语义顺序为：

1. reasoning：visible summary `THINK-MARKER`，`encrypted_content="opaque-😀"`；
2. message output text：`TEXT-MARKER`；
3. function call：`call_id="call_acceptance_01"`、`name="weather"`、arguments `{"city":"Paris"}`；
4. usage：`T=100,R=20,W=10,O=30,Q=12,total=130`。

项目主 v1 carrier expected 直接取自冻结 Spec canonical vector：`ghc-api-proxy:synthetic-reasoning:v1:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLfCfmIAifQ`。Expected 未调用候选 carrier codec、request converter或response converter生成。

## 实际执行证据

执行入口位于隔离临时文件 `/tmp/verify_route_happy_260807.py`，未写入候选树或主树产品／测试路径。最终可信执行命令在候选物理根目录运行，设置 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-route-happy/src`，使用 `/home/xp/src/ghc-api-proxy-py/.venv/bin/python`，并由 `timeout 30s` 限界。

- **退出码**：`0`。
- **固定 oracle marker**：`SPEC_SHA=5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。
- **harness marker**：`HARNESS_VERDICT=PASS`，其含义仅是用户点名矩阵及 route 反转正控通过；header 检查作为独立发现记录，不被该 marker 覆盖。
- **关键输出**：Responses-only blocks 为 `thinking,text,tool_use`；usage 为 `70/20/10/30`；auto dual 为 Messages `1`／Responses `0`；explicit Responses dual 为 Messages `0`／Responses `1`；approval `1`、History started `1`／finalized `1`、attempt `[0]`；429 为 Anthropic `rate_limit_error`；selected stream 为 HTTP `400` 且两类 upstream 调用均 `0`；header probe 为 `responses_specific_header_leaked="must-not-forward"`。

前两次尝试未作为证据：一次被 header 断言提前终止，另一次及共享终端重试混入其他并发会话输出。最终判定只使用上述退出码 `0`、完整 marker 齐全的限界执行，以及单独的候选 HEAD／clean gate。

## Route 反转正控

- **被测对象边界**：双支持模型、无 override 时的 route policy 外部结果，即真实 ASGI 请求最终触发的 Messages／Responses transport 调用计数。
- **变异**：仅把双支持 auto 的决策从 Messages 反转为 Responses，不改变 fixture、HTTP route、converter或 transport counter。
- **正样本**：未变异时 Messages `1`、Responses `0`，oracle 为绿。
- **缺陷注入结果**：变异后 Messages `0`、Responses `1`，同一 oracle 以 `route oracle rejected inversion: messages=0 responses=1` 按目标原因变红。
- **恢复**：monkeypatch context 退出后恢复生产 selector；候选树未改动。

该正控证明本轮 route 计数判据能区分正确与反转状态；它不证明未覆盖的 route／capability 全矩阵或完整 bridge 合同。

## 实证缺陷

### Responses-specific header 泄漏到 Anthropic 客户端

- **违反的 Spec 条款**：Header 契约规定“Responses-specific／hop-by-hop／auth header 不下发客户端”；双向 response 矩阵也把 Responses-specific header 固定为 `REJECT`。
- **复现输入**：Responses-only non-stream 请求；fake Responses success response 带 `x-internal-openai: must-not-forward`。
- **失败证据**：真实 ASGI 客户端响应包含同名同值 header。首次严格断言在 `/tmp/verify_route_happy_260807.py` 的 `assert_anthropic_success` 中以 `AssertionError` 失败；继续跑完整矩阵后，结构化输出再次记录 `responses_specific_header_leaked: "must-not-forward"`。HTTP status 为 `200`，说明该 header 不是错误旁路产生。
- **明确根因位置**：`src/app/anthropic/client.py:252-255` 在 Responses body 转为 Anthropic body后仍以 `headers=upstream.headers` 构造新 response；`src/app/routes/anthropic.py:120-126` 再调用通用 Anthropic header policy；`src/app/anthropic/header_policy/__init__.py:87-103` 在默认 `strict=false` 且 blacklist 为空时允许除固定 floor 外的任意 header，因此 Responses-specific header 穿透。
- **建议修复路由**：根因明确，建议主会话交由 implementer 在 Responses adapter 边界先构造归一化 Anthropic response header set，或让 header policy显式识别 selected endpoint／Responses-specific headers；修复后以同一真实 ASGI probe 回归。不得只把测试 marker `x-internal-openai` 加进默认 blacklist，因为那只修一个拼写，不落实“Responses-specific header 不下发”的合同。

## 未验证范围

- 完整 Responses stream：SSE grammar、完整 block commit、首 block 前零 header／body、stream usage、post-commit failure、cancel、backpressure、HTTP／WS parity均未验证。
- approval modified payload 与 retry 后第二 attempt：本轮只验 unchanged approval、单 attempt、`PRE_SEND` 修改后的 wire；没有把未测路径折算为通过。
- capability unknown／unsupported／transport unavailable、Messages-only、WS physical transport、count_tokens、真实 upstream canary、capture corpus 与 local socket fault不在本轮点名范围，保持 `UNVERIFIED`。
- 本轮 History single-owner 通过来自生产 pipeline 对 History consumer 接缝的 started／finalized 与 context identity观测；未把 SQLite durability、History response／usage完整投影扩大为已验证。

## 结论

候选 `f3a5a76` 的用户点名 route-happy 行为成立：Responses-only non-stream 的 text／reasoning／tool／usage转换、双 override、auto dual Messages、`PRE_SEND` wire 更新、single owner、429 Anthropic error与 selected Responses stream 零调用 typed error均通过；route 反转正控有效。可是同一 route-level probe 已证实 Responses-specific header 泄漏，因此冻结 Spec 下本轮总体 verdict 必须为 **`FAIL`**。修复该 header 边界并重跑相同 probe 后，才可把本切片提升为 `PASS`；完整 stream无论如何继续为 **`UNVERIFIED`**。

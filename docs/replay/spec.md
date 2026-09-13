# Replay 行为规格

日期：2026-09-13

状态：**DESIGN-ONLY v1**。Replay 与主程序分离，当前不接入主程序 API，也不属于 live request lifecycle。本规格定义未来独立 replay process 的 source、eligibility、执行和 provenance 合同，不声称功能已实现。

## 1. Boundary

Replay 是独立进程读取 History/Capture artifacts 的操作，不写主程序的 live registry，不复用主程序的 accepted request lifecycle，也不把 replay 当作原始 request 的 retry。

主程序只负责：

- 生成 HistoryEntry；
- 生成/关联 CaptureAttachment；
- 记录 replay eligibility 和 provenance fields；
- 暴露由 History/raw capture specs 定义的读取面。

Replay process 负责未来的 diagnostic/semantic/live execution。主程序当前没有 `/api/replay`。

## 2. Source eligibility

所有 replay 都要求 capture source；History semantic payload 和 RequestJournal 不能替代 CaptureAttachment。

### 2.1 Source selector

调用必须显式选择：

- `client_request`：从 capture 的 client request body 重新进入 semantic/live pipeline；
- `upstream_attempt(attempt_id)`：选择某个 attempt 做 wire diagnostic；
- 不允许自动从 client body fallback 到 upstream body，也不允许自动替换为 final attempt。

### 2.2 Capability gate

- 没有 capture：`409 source_content_unavailable`；
- capture 不可读或损坏：`409 source_evidence_unavailable`；
- client request body 不可解析：semantic/live 不可运行；
- attempt 的 request/response/boundary 不完整：对应 wire diagnostic 不可运行；
- response/client body 缺失时，不得生成“完整 wire replay”成功结果。

`source_content_unavailable` 和 `source_evidence_unavailable` 是 not-started 结果，不创建伪成功 History entry。

## 3. Modes

### 3.1 `wire_diagnostic`

离线读取 recorded capture/cassette，验证 parser、normalizer、delivery observation 或差异报告。不访问真实 upstream，不向真实 client 重新发送 response，不执行工具。

### 3.2 `semantic`

使用 capture 的 client request body 重新运行 semantic pipeline，target policy 显式选择：

- `original_resolved_target`；
- `current_route`。

认证使用当前配置生成，不复用 source headers/credentials。

### 3.3 `live`

使用 capture 的 client request body 访问真实 upstream。它是高风险开发者工具能力，仍使用新的 request identity、显式 target policy、当前认证、deadline 和取消规则。

## 4. Synchronous execution

所有 mode 以同步调用语义执行：

- 必须有显式或配置的 deadline；
- deadline 不得超过全局 `upstream_request_deadline`；
- offline diagnostic 受独立 local read/CPU deadline；
- client disconnect 取消执行；
- HTTP 返回或取消后不得在后台继续执行；
- 长结果可以流式返回，但必须在终局时生成新的 replay result/History provenance。

Replay 不在主程序 request path 执行，因此不会改变主程序的 request completion、History durability 或 live registry。

## 5. Client actions

Replay 遇到 `function_call`、`custom_tool_call` 或其他 client action 时，只返回和记录 action，作为 replay 的终点之一：

- replay process 不执行工具；
- 不伪造 tool result；
- caller 若要继续，必须显式提交 tool result 并发起下一次请求；
- proxy server tools 的拒绝/支持边界不因 replay 被绕过。

## 6. Result identity and provenance

每次 replay 生成新的 `replay_id` 和 request identity，不覆盖 source entry。结果至少记录：

- `replay_mode`；
- `source_entry_id`；
- `source_capture_ref`；
- source selector；
- target policy 与实际 target；
- execution policy；
- started/finished/deadline/cancel facts；
- outcome/delivery/client actions；
- result History entry/reference。

Replay result 不默认内嵌 source full transport。显式 evidence projection 才能读取完整 transport，并标记 `contains_credentials=true`。

## 7. Security boundary

当前产品不新增 app-level auth/RBAC；部署层负责非 loopback 暴露的访问控制。Replay process 的 source store 读取、full transport export 和 live upstream execution 属于开发者工具高风险面，不能被普通 History list/detail 隐式触发。

## 8. Revision record

| 日期 | 版本 | 变化 | 触发 |
|---|---|---|---|
| 2026-09-13 | v1 | 建立独立 replay process、capture-required source matrix、wire/semantic/live mode、explicit target、sync deadline/cancel、client-action boundary 和 provenance；标记 design-only | 可观测性、History、debug 重构 grill 达成 shared understanding |

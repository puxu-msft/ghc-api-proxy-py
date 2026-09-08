# Current main real Copilot path 独立定向复核

- **评审范围**：只读复核 `/home/xp/src/ghc-api-proxy-py` 的 `main@fb4272b5752bd8439c1ee5a098960f31d4ea70f1`，仅覆盖 token identity、route override、response／item drift 的默认 strict 与 Copilot-only relaxed 策略、non-stream／stream 主路径、resident wiring、History facts，并结合 `docs/tmp/260807-real-copilot-canary.md` 的脱敏 real-upstream 事实。未执行完整 Acceptance，未重跑 real upstream canary，未修改生产代码或其他文档。
- **总体 verdict**：**可进入下一阶段。** 本限定范围未发现 blocker 或 major。
- **Blocker 数**：**0**，口径仅为上述定向范围。
- **Major 数**：**0**，口径仅为上述定向范围。
- **双视角覆盖证据——机械核对**：每次 load-bearing 命令均在同一调用中打印并断言物理 `PWD`、Git top-level 与完整 HEAD；读取 current 最终代码而非仅看 diff；对账 token exchange identity 注入、route policy、parser strict 默认、Copilot route relaxed 接线、non-stream conversion、stream renderer、resident budget、History consumer 与相关正反测试；运行同一最小 selector 的实际 pytest 与 `--collect-only`。实际执行为 `39 passed`，collect-only 为 `39 tests collected`，且节点数另由 `rg` 与 `awk` 两种计数方法均得到 `39`。
- **双视角覆盖证据——第一人称执行**：模拟服务启动时以 GitHub token 加 Copilot editor／plugin／user-agent identity 换取 Copilot token并加载 catalog；模拟 Anthropic 请求在 auto、显式 Responses override 与双能力默认 Messages 三条 route；模拟 non-stream Responses 成功转换、最终 body 严格校验与 History commit；模拟 stream 在 Copilot 生命周期 ID 漂移下完成 Anthropic SSE，在 generic upstream 同类漂移下 typed reject；模拟 opt-in resident account 的分配与成功释放；模拟 completed、first-body uncertain 与无 projection failure 的 History 投影。

## 事实性发现

未发现问题。

## 主观建议

无。

## 定向核对结果

| 轴 | 结论 | Current 证据与边界 |
|---|---|---|
| Token identity | PASS | `src/app/upstream/copilot.py:24-32` 构造 editor、plugin、user-agent 与 fetch-library identity；`src/app/upstream/bootstrap.py:168-172` 将同一 identity 注入 `CopilotTokenManager`；`src/app/auth/copilot.py:104-116` 先复制静态 identity，再由动态 Authorization、Accept 与 API version 覆盖同名大小写变体，避免 stale header 抢占。`tests/unit/test_copilot_token.py:39-116` 与 `tests/integration/test_phase1_bootstrap.py:12-70` 直接断言 token exchange 和 bootstrap 请求头。Real canary 报告另称该 identity 修复使此前失败的真实 token exchange 成功并完成 catalog 启动；本轮没有读取或重放 credential，也没有独立重跑该 A／B。 |
| Route override | PASS | `src/app/config/settings.py:79-81` 固定默认 `route_override="auto"`；`src/app/anthropic/client.py:207-224` 将非 auto 值转成显式 leg，并把 catalog capability 交给 `decide_protocol_leg()`；`src/app/pipeline/route_policy.py:79-138` 保持 override 先过 capability gate、双能力无 override 默认 Messages、单能力选择其唯一 leg、unknown／unsupported／transport unavailable fail closed且不 fall through。最小测试同时覆盖显式 Responses、双能力默认 Messages 与错误反例。Real canary 仅使用显式 Responses override，不能外推为真实 auto／Messages 路径已跑。 |
| Response／item drift 策略 | PASS | `src/app/openai/responses_stream_parser.py:149-156` 与 `src/app/delivery/responses_anthropic_stream.py:159-177` 的 API 默认均为 strict；`src/app/routes/anthropic.py:229-246` 仅在 `settings.upstream.type == "copilot"` 时同时放宽 response ID 与 item ID 生命周期相等性，generic 保持 strict。放宽只取消 opaque ID 跨 frame 相等要求；`src/app/openai/responses_stream_parser.py:228-310,536-580,615-628,915-956` 仍以 `output_index`／`content_index` 关联 state，并继续校验 item type、function `call_id`、name、非空 ID 与 authoritative content。最小测试包含 Copilot drift 正样本、generic item drift 反样本和 strict response terminal mismatch 反样本。Non-stream 不经过该生命周期 parser，因此“relaxed”不是 non-stream 行为声明。 |
| Non-stream 主路径 | PASS | `src/app/anthropic/client.py:232-299` 在 Responses leg 完成 request conversion、上游调用、JSON object 检查和 Responses→Anthropic conversion，并关闭 upstream response；`src/app/pipeline/executor.py:367-447` 在成功回调前完成 response hook、最终 client-visible body 严格验证、final payload、response conversion facts 与 typed usage 发布。`tests/smoke/test_anthropic_responses_route.py:312-393` 通过真实 FastAPI／ASGI route 断言单一 Responses attempt、Anthropic body、usage、approval、hooks 与 History owner。Real canary 报告称同一 current main 的显式 Responses non-stream 返回成功 Anthropic text block；本轮没有保存或检查其响应正文。 |
| Stream 主路径 | PASS | `src/app/routes/anthropic.py:205-270` 将成功 Responses stream 接入 idle timeout、semantic renderer、History wrapper、upstream cleanup 与 delayed SSE start；`src/app/delivery/responses_anthropic_stream.py:159-340` 以完整 semantic block 驱动单 writer、delivery frontier、terminal validation、post-commit typed error 与最终 state freeze。`tests/smoke/test_anthropic_responses_stream_route.py:657-965` 走真实 ASGI `Send`，断言完整 block 前不发 headers、合法 Anthropic SSE 顺序、tool／reasoning／text 投影、History 与 cleanup；本轮另执行 ID drift 正反测试。Real canary 报告称 current main 的显式 Responses stream 成功并得到 `message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop`；本轮仅将该报告作为只读 real-upstream 事实，不把它升级为完整 stream Acceptance。 |
| Resident wiring | PASS | `src/app/config/settings.py:132-151` 默认 global／request resident bytes 均为关闭值，并要求显式启用时成对为正且 request 不超过 global；`src/app/server.py:59-63` 仅在显式正值时建立共享 budget；`src/app/routes/anthropic.py:230-246` 仅对 Responses stream 建 request account并传入 renderer；delivery session 在正常、错误与取消清理中释放 lease。`tests/smoke/test_anthropic_responses_stream_route.py:967-1089` 覆盖 production route 成功后 high-water 非零且 current bytes 归零，以及 capacity wait 取消不泄漏。Real canary 未声明启用 resident limits，因此不能把其 stream 成功解释为真实 quota／backpressure 已验证。 |
| History facts | PASS | Non-stream 在 `src/app/pipeline/executor.py:349-435` 先保留最终 selected attempt 的 request facts，再在最终 body 严格验证后追加 response facts、final payload 与 exact／estimated usage；`src/app/history/consumer.py:26-48,76-178` 仅在 completed 或显式 stream projection 时持久化成功 response／usage。Stream 在 `src/app/routes/anthropic.py:35-124` 从 accepted frontier 投影 completed、partial 或 uncertain response，并在终态 hooks 后 finalize History；`src/app/delivery/responses_anthropic_stream.py:92-143` 只把 committed blocks 与 possibly-visible uncertain block按不同字段保存。最小测试覆盖 non-stream estimated facts、invalid final body 零成功 facts、stream completed／failed projection与无 projection failure 零成功 facts。既有 stream request-facts 裁决只冻结 selected-attempt request conversion facts；stream response conversion facts 不在该裁决范围内，本报告不擅自声称已实现。 |

## Real canary 只读事实处置

`docs/tmp/260807-real-copilot-canary.md:5-12` 明确绑定同一完整 HEAD，并报告隔离 backup-port 启动 readiness、显式 Responses override 下的 real Copilot non-stream 与 stream 成功，以及合法 Anthropic terminal event sequence；`docs/tmp/260807-real-copilot-canary.md:29-35` 记录真实 Copilot response／item opaque ID 会跨 lifecycle frame 漂移，成功 canary 位于两项兼容修复之后；`docs/tmp/260807-real-copilot-canary.md:39-47` 记录隔离与清理终态。

本轮没有重跑 canary，因此不把上述报告声称本身当作第二次独立测量。独立补强仅来自 current 代码接线、strict／relaxed 正反测试，以及本轮 `ss` 只读观察：backup port 当前无 listener，而既有 Bun 服务端口仍有 listener；该观察与 canary 的 cleanup 方向一致，但不证明其历史过程中的 credential isolation、零 signal 或 process incarnation 叙述。

## 真实仍未验证边界

1. **未执行完整 Acceptance**：本报告只放行点名的 real Copilot 主路径接缝，完整产品继续为 `UNVERIFIED`，不得据此宣称部署或 cutover readiness。
2. **真实 route 矩阵不完整**：canary 只跑显式 Responses override；auto 的 Responses-only、双能力默认 Messages、显式 Messages、unknown／unsupported capability 与 transport unavailable 仅由本地测试覆盖。
3. **真实 drift 边界不完整**：real canary证明了当前 observed Copilot response／item drift样本可用；未覆盖 error event identity、缺失／空 ID、output／content index冲突、item type冲突、function `call_id`／name冲突及未来新增 event形态。Generic strict路径也只在本地 fake stream中验证。
4. **真实 token 生命周期不完整**：初始真实 token exchange与 catalog startup有 canary报告；长期 refresh、expiry margin、真实 401 refresh、429／5xx retry、credential rotation与服务长期驻留只由本地测试或代码核对覆盖。
5. **真实 stream failure与内存压力不完整**：未对真实 upstream制造 quota、backpressure、resident capacity wait、slow consumer、disconnect、RST、truncation、kernel partial write、post-commit error或 cancellation竞态；resident budget也未在 real canary中显式启用。
6. **真实语义内容不完整**：canary未记录响应正文，且未跑完整 reasoning、tool use、malformed tool arguments、usage details、partial／uncertain History projection或 stream response conversion facts。
7. **真实 History未在本轮复验**：本轮 History结论来自 current production owner与最小现有 integration／component／ASGI tests；real canary报告没有给出可独立核对的 History entry。
8. **Transport与运维边界不完整**：未覆盖真实 Responses WebSocket、真实 systemd user manager／cgroup、accepted-connection migration、生产端口接管或零停机 cutover。

## 结构与方法复核

- **结构怪味扫描**：扫描 `src/app/auth/copilot.py:24-121`、`src/app/upstream/bootstrap.py:156-260`、`src/app/anthropic/client.py:193-299`、`src/app/routes/anthropic.py:35-270`、`src/app/openai/responses_stream_parser.py:149-956`、`src/app/delivery/responses_anthropic_stream.py:74-340`、`src/app/history/consumer.py:26-178` 与对应测试，按重复 owner、stream／non-stream 漂移、全局 permissive、资源泄漏与事实发布早于最终验证五类判据检查。未发现需要本轮修复或登记为 blocker／major 的结构怪味。
- **更好的内部替代方案**：当前以 parser 默认 strict、route 按 upstream type 显式 opt-in relaxed 的内部路径符合“兼容例外不能污染默认合同”。若未来出现第二个需要漂移兼容的 provider，再把字符串判断提升为 typed compatibility capability会更易扩展；当前无事实表明需要在本轮改动。
- **判据判别力**：选择器同时包含正确状态可通过与错误状态不可通过，且主路径经过真实 FastAPI／ASGI route，不是只测 parser helper。实际执行与 collect-only 数量一致，但本轮未做破坏生产实现的 mutation，因此不能将绿灯外推为 selector 覆盖了所有未来 event形态。
- **成熟第三方方案**：non-stream final body复用 Anthropic SDK schema，SSE JSON解析与 HTTP transport复用现有库；Copilot opaque identity漂移和 Anthropic block commit frontier是项目特定协议合同，未发现可直接替换并保持当前行为的成熟通用组件。

## 最终结论

`main@fb4272b5752bd8439c1ee5a098960f31d4ea70f1` 在本轮限定的 token identity、route override、strict＋Copilot-only relaxed drift、non-stream／stream 主路径、resident wiring与History facts范围内为 **0 blocker／0 major，可继续下一阶段**。Real canary只读事实与 current实现方向一致，但完整 Acceptance、真实故障矩阵、完整语义内容、真实History、WebSocket与systemd／cutover边界仍明确未验证。

# Anthropic Messages → OpenAI Responses request converter 独立验收

## 判定

**FAIL。** 目标提交 `f8a11ad3c3cd8f2330333634f1fe963f9aa2c444` 的基础 message、client tool、image、reasoning carrier、sampling 与 unknown fail-loud 行为大体成立，但存在两条可独立复现的 Spec 阻断偏差：Anthropic `web_search_YYYYMMDD` request 声明没有映射为 Responses builtin；包含非 ASCII payload 的 malformed reasoning carrier 泄漏裸 `ValueError`。另有 system block 拼接与 mixed-content tool result 两项相对固定 JS converter 的行为偏差，需要产品语义裁决或补充 Spec，但不作为本报告的独立阻断依据。

本验收只回答 request converter 的用户可观察输出是否满足冻结 Spec；不做代码结构、风格或架构 review，也未修改生产代码或测试。

## 冻结基线与 oracle

- 待验收仓库：`/home/xp/src/ghc-api-proxy-py-request`。
- 待验收 HEAD：`f8a11ad3c3cd8f2330333634f1fe963f9aa2c444`，提交标题为 `feat: convert Anthropic requests to Responses`。
- 最新冻结 Spec：`/home/xp/src/copilot-api-js/docs/spec/2026-08-06-responses-anthropic-semantic-bridge.md`，文档状态明确为“已定稿”。
- 固定 differential oracle：`/home/xp/src/copilot-api-js` commit `e79e65b382bfe5b6c8a45411f2a4bf16d23c26f2` 的 `translateAnthropicToResponses`。
- 参考仓库在验收期间曾从 `8205b93ca95c28a206b6f3e6e6d37032bd3d8efb` 前进到 `e79e65b382bfe5b6c8a45411f2a4bf16d23c26f2`。采用新 commit 前已逐个核验 request converter 及其四个直接运行依赖的 old/new/worktree blob 三方一致，因此差分 oracle 没有随无关提交漂移。
- 每个被采信的 shell 调用均在同一调用开头校验目标 root、目标完整 HEAD，并校验参考 converter 相关 worktree blob 等于固定 commit；调用末尾确认目标工作树为空。缺少预期 nonce 首尾的并发终端输出全部作废，未纳入证据。

## 从 Spec 独立推导的 request 验收矩阵

| 验收面 | Spec oracle | 黑盒判据 |
|---|---|---|
| System | §5.2 顶层 capability registry，instructions／system 必须显式 mapped／degraded／rejected | system string／blocks 不得静默丢失；映射结果须保留可观察文本语义 |
| 多交错 text／tool run | §5.2 ordering policy、§15.3、AC22 | 同一 source group 内保持 source order；只有显式 `reasoning-first` 可稳定移动 reasoning，其他 kind 不得重排 |
| Parallel tools | §5.2 `tools[] + tool_choice` 原子映射、§15.3 | 多 tool calls／results 的 identity 与顺序保持；parallel choice 不得反转 |
| Tool result mixed content | §10.2 第一批支持集合包含 `tool_result`；G1、G7 | 必须得到显式 native／degraded／rejected 结果，不得无记录删除内容 |
| Image base64／URL | §10.2 第一批支持集合与 richest data flow | base64 形成 data URL，URL 原样进入 `input_image` |
| Reasoning carrier | F4、§8、P0-2、AC9 | valid／bare／foreign／malformed carrier 均有定义；malformed／foreign prefix 不抛裸异常、不误认 |
| Unknown fields | G6、§11、AC12 | 非 identity translation 必须 fail-loud，不得静默成功 |
| Server tools | §9.1、§10.2、AC2 | `web_search_YYYYMMDD` declaration 映射为 `{type:"web_search"}`，forced choice 同源映射；已知 `server_tool_use` 不得 silent drop |
| Max output／sampling／stream | 顶层 capability registry、Responses request 字段矩阵 | `max_tokens → max_output_tokens`，`temperature`、`top_p`、`stream` 值保持 |
| 无直接等价值 | §5.2、P0-5、AC24 | top-k、stop sequences、cache-control、context management 等必须明确 mapped／degraded／rejected，不得 silent drop |

## 实际执行证据

### 双端入口校准

有效调用 nonce：`VRQ_SMOKE_C2A9`。

- Python：`convert_messages_request_to_responses(...)`。
- JS：固定 commit 对应 worktree blob 的 `translateAnthropicToResponses(...)`，由 Bun 直接导入执行。
- 最小 user text 样本两端得到同一 Responses `message/input_text` 语义；Python 额外显式输出默认 `stream:false`，JS 省略该默认字段。
- 调用退出成功，目标工作树保持为空。

### 主表驱动 differential probe

有效调用 nonce：`VRQ_MATRIX_7E31`。

以下均为真实执行结果，不是读取实现后的推断：

| 样本 | Python 结果 | 固定 JS 结果 | Spec 裁决 |
|---|---|---|---|
| system blocks + metadata | `instructions:"alpha\n\nbeta"`；对 cache-control 与额外 metadata 生成 degradation facts | `instructions:"alphabeta"`；额外字段无结构化 degradation | **偏差，待裁决**。两端 prompt 文本不同；Spec 要求 mapped，但未冻结 block 分隔符 |
| `text A → tool 1 → text B → tool 2 → text C` | 输出顺序逐项保持 | 折叠为 message `ABC`，再输出 tool 1／tool 2 | **PASS（Python）**。Python 符合 AC22；不能因与旧 JS 不同而判错 |
| parallel tool calls + parallel results | 两个 function calls 后跟对应两个 outputs；`parallel_tool_calls:true` | identity／顺序一致；省略 parallel 默认值 | **PASS**。raw wire 有默认字段差异，未观察到语义反转 |
| mixed-content tool result：text／image／text | typed `RequestConversionError`，`unsupported_tool_result_content`，路径精确到 image part | 丢 image，输出 `leftright`，stderr warning | **显式偏差，未单列 blocker**。Python fail-loud，JS degraded；Spec 未冻结该 mixed-content disposition，但不允许 silent drop |
| base64 image + URL image | `data:image/png;base64,AAEC` 与原 URL | 完全相同 | **PASS** |
| valid reasoning carrier + assistant text | reasoning `encrypted_content:"ENC=="` 在同组首位，随后 assistant message | 完全相同 | **PASS** |
| unknown top-level／message／content field | 均 typed `RequestConversionError`，带精确 field path | 均静默删除后成功 | **PASS（Python）**。Python 符合 G6／AC12；固定 JS 在此只作反例，不作新 Spec oracle |
| server-tool declaration + forced choice | typed `RequestConversionError(code="server_tool_not_supported", field_path="tools[0]")` | `{tools:[{type:"web_search"}], tool_choice:{type:"web_search"}}` | **FAIL，见 F1** |
| historical `server_tool_use` block | typed `server_tool_not_supported` | 静默丢 block，留下空 input | Python 至少 fail-loud；但第一批支持集合已纳入该 kind，完整支持仍未闭合 |
| max output + temperature + top-p + stream | `4096`、`0.25`、`0.8`、`true` 全部保持 | 完全相同 | **PASS** |
| top-k + stop sequences | 在首个字段 `top_k` typed reject | 两字段静默删除后成功 | **PASS（Python 的 fail-loud 方向）**；未验证 request diagnostics／HTTP error 路由 |

### 差分反例搜索

同一有效调用 `VRQ_MATRIX_7E31` 枚举了由两个 text blocks 与一个 tool block构成的全部排列。所有排列都发现 Python 与固定 JS 的 raw output 不同：Python按 source 顺序切分／聚合相邻 text，固定 JS 始终把所有 text 折叠到一个前置 message。该搜索不是 Python 缺陷证据；它反而证明固定 JS converter 不满足最新 Spec AC22，而 Python 对非 reasoning kind 的顺序处理满足本轮黑盒 oracle。

### Reasoning／capability 边界与正控

有效调用 nonce：`VRQ_BOUNDARY_POSCTL_5D44`。

- Valid carrier：两端均恢复 `encrypted_content:"ENC=="`，PASS。
- Bare carrier：两端均产生无 `encrypted_content` 的 reasoning item，PASS。
- Foreign signature：两端均删除不可移植 thinking；Python 生成结构化 degradation fact，PASS。
- Corrupt ASCII payload `!!!`：两端均解码为空字符串并产生 reasoning item。此行为可能“误认” malformed payload，保留为风险，但本报告不把它单独定为 blocker，因为固定 JS 同样如此且 Spec 未冻结严格 base64url canonicality。
- Corrupt Unicode payload `😀`：Python 抛裸 `ValueError("string argument should contain only ASCII characters")`；固定 JS 返回带空 `encrypted_content` 的 reasoning item。**FAIL，见 F2**。
- 顶层 `thinking.enabled`：Python typed reject；固定 JS 映射到 `reasoning:{effort:"medium",summary:"auto"}`。这是 capability 差分，但最新 Spec 首批顶层 capability 清单未明确冻结 `thinking` 的映射，因此不单列 blocker。
- 顶层 `stop_sequences`、`context_management`：Python typed reject，固定 JS 静默删除。Python满足“不 silent drop”，但未验证 Spec 所要求的 disposition diagnostics 与 route error rendering。
- 正控变异：基线 scalar oracle 对 `max_output_tokens`／`temperature`／`top_p`／`stream` 为绿；在内存副本中删除 `top_p` 后按预期以 `KeyError` 变红；恢复原 wire 后重新为绿。该正控证明 sampling 绿色结果确实命中目标字段，而不是只验证 converter 被调用。

## 阻断缺陷

### F1：已纳入支持集合的 Anthropic Web Search declaration 没有映射到 Responses builtin

**违反条款：** Spec §9.1 明确要求 `web_search_YYYYMMDD → {type:"web_search"}`，forced choice 同步变为 `{type:"web_search"}`；§10.2 将 `server_tool_use` 与当前真实 `*_tool_result` 纳入 Anthropic→Responses 第一批支持集合；AC2 禁止该支持集合存在 silent drop。

**复现输入：**

```json
{
  "model": "gpt-test",
  "max_tokens": 64,
  "tools": [{"name": "web_search", "type": "web_search_20250305", "input_schema": {"type": "object"}}],
  "tool_choice": {"type": "tool", "name": "web_search"},
  "messages": [{"role": "user", "content": "news"}]
}
```

**实际失败证据：** `VRQ_MATRIX_7E31` 中 Python 返回 `RequestConversionError`，`code="server_tool_not_supported"`，`field_path="tools[0]"`，退出该样本的转换；同一输入在固定 JS converter 得到 `tools:[{type:"web_search"}]` 与 `tool_choice:{type:"web_search"}`。

**建议路由：** 语义与期望映射已由冻结 Spec 明确，建议主会话交 implementer 按 §9.1 修复，并补 declaration／choice 原子映射与历史 server-tool block 的独立验收。无需先猜测新产品语义。

### F2：Malformed Unicode reasoning carrier 泄漏裸 `ValueError`

**违反条款：** Spec P0-2 要求 malformed／foreign prefix“不抛错、不误认”；G6／§11 要求 translation incompatibility 走可识别的 fail-loud／typed compatibility 路径，不能泄漏未建模的运行时异常。

**复现输入：** assistant thinking block 的 signature 为 `copilot-api:synthetic-reasoning:v1:😀`，其余字段为合法最小 Messages request。

**实际失败证据：** `VRQ_BOUNDARY_POSCTL_5D44` 中 Python 返回 `ok:false`，异常为裸 `ValueError`，消息为 `string argument should contain only ASCII characters`，没有 converter error code 或 field path；固定 JS converter 对同一输入完成转换且没有进程异常。

**建议路由：** 失败机制已由最小输入稳定复现，建议主会话交 implementer 把非 ASCII／malformed carrier 收敛到 Spec 允许的 benign degradation 或 typed rejection，并加入 ASCII 非法字符、Unicode、非 canonical base64url 的表驱动回归。若团队需要先冻结 strict canonicality，再由用户／ADR 裁决 `!!!` 是否应视为 malformed。

## 已验证通过的范围

- system string／blocks 能进入 instructions，且 cache-control 与非 allowlist metadata 在 Python 侧有显式 degradation facts；block separator 语义除外。
- user／assistant text，单个与多个 client tool calls，parallel tool results，tool choice identity。
- 多交错 text／tool source order，包括排列反例搜索。
- tool-result string 与 text-only list；mixed image disposition 除外。
- base64 image data URL 与 HTTP(S) image URL。
- valid／bare／foreign synthetic reasoning carrier；Unicode malformed 除外。
- unknown top-level、message 与 content-part 字段 fail-loud。
- max output、temperature、top-p 与 stream 的字段保持，且通过正控变异证明断言有判别力。
- top-k、stop sequences 与 context management 至少不会在 Python 侧 silent drop，而是显式拒绝。

## 未验证与边界

- 未调用真实 Responses upstream，因此没有验证 wire 的服务器接受性、真实 token 行为或 server-tool 实际执行。
- 未验证 route／driver 的 HTTP compatibility error rendering、dispatch count、retry gate、History request dispositions 或 diagnostics freeze；本轮只验证纯 converter 公开入口。
- 未验证 structured output 双向 schema、完整 `context_management` strategy matrix、cache-control 的 request-level diagnostics E2E；这些在 Spec P0-5 中仍需要真实 wire 与用户／ADR 裁决。
- 未验证 response whole／stream、official OpenAI SDK accumulator、continuation echo E2E；它们不属于本次 request converter 范围。
- 未运行目标仓库自带测试作为验收 oracle；用户要求独立黑盒／表驱动，本轮避免用同源测试为实现背书。
- 没有将“与固定 JS converter 不同”自动判成失败。遇到 JS silent drop 或违反最新 AC22 的行为时，以更新且冻结的 Spec 为最高 oracle。

## 只读与写入审计

所有有效探针结束时，`/home/xp/src/ghc-api-proxy-py-request` 的 `git status --short` 为空。未编辑目标 request worktree、参考 JS 仓库、生产代码或测试。唯一持久化写入是本报告：`/home/xp/src/ghc-api-proxy-py/docs/tmp/260806-verify-request-converter.md`。

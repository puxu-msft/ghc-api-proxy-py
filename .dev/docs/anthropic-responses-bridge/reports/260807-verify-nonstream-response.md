# Responses → Anthropic non-stream response 独立复验

## Verdict

**FAIL**。

候选 `/home/xp/src/ghc-api-proxy-py-response` 的精确复验对象为 commit `7ddf17364d97349638d44352bbd9a9b025723ccc`。从 current Spec 独立推导并实跑的 9 个验收项中，7 项 PASS，2 项 FAIL：

1. Responses reasoning 新 producer 仍输出旧 `copilot-api:synthetic-reasoning:v1:` carrier，不符合 current Spec 冻结的本项目主 v1 `ghc-api-proxy:synthetic-reasoning:v1:` wire contract。
2. usage 转换未保留 `output_tokens_details.reasoning_tokens`，输入 `Q=12` 后 public Anthropic usage 与诊断 facts 均未见该值。

这两个偏差均发生在 non-stream 成功响应转换的用户可观察结果中，因此本候选不能判为符合 current Spec。

## 验证基线与独立性

- **Current Spec**：主树 working-tree `docs/agents/anthropic-responses-bridge/spec.md`，SHA-256 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`。
- **候选**：`feat/responses-anthropic-nonstream` commit `7ddf17364d97349638d44352bbd9a9b025723ccc`。
- **候选只读门**：复验前后 `git -C /home/xp/src/ghc-api-proxy-py-response status --short` 均为空；最终取证再次确认 HEAD 精确匹配且工作树干净。
- **oracle 构造顺序**：先只读 current Spec 并独立列出验收项，之后才读取候选生产实现。未读取、导入或复用候选测试中的 fixture／expected。
- **临时 probe**：`/tmp/verify_nonstream_response_7ddf173.py`，SHA-256 `af8be5a777ad54cb43a0caebdcad670ea6ddce7cb5ce08bf35f6e3a618ec0b99`。该文件位于 `/tmp`，不属于候选树或主树持久化资产。
- **identity 正控日志**：`/tmp/verify_nonstream_response_7ddf173_identity_control.log`，SHA-256 `c8b9b194e94a49492c9d89e426ceb9ccea69aef0b7a39273d63dd1efc7bce894`。
- **import gate**：probe 使用 `PYTHONPATH=/home/xp/src/ghc-api-proxy-py-response/src`，实际 `app.__file__` 位于候选树 `src/app/` 下。

## 从 Spec 独立推导的验收矩阵

| ID | Current Spec oracle | 独立输入与断言 | 结果 |
|---|---|---|---|
| NS-1 | output item／content part 按语义顺序输出，不按类型或完成时间重排；见 Spec 第 177、352 行 | 两个 `message` item，首个含两个 `output_text` part；断言 Anthropic text 为 `text-0 → text-1 → text-2`，且无 tool call 时 `stop_reason=end_turn` | **PASS** |
| NS-2 | `function_call` 转为 `tool_use`，value-exact 保留 `call_id`，恢复原 tool name并解析完整 arguments；见 Spec response matrix 与 Content contract | `text → function_call → text`；call id 为 `call_exact_42`，wire name 为 `wire_tool`，arguments 含嵌套 object、array、boolean 与非 ASCII 字符；断言 block 顺序、原 name、call id、完整 parsed input 和 `stop_reason=tool_use` | **PASS** |
| NS-3 | 每个 reasoning item 一对一形成 thinking block；encrypted-only 非空 payload 仍形成空 visible thinking block；不得跨 item 聚合／错配；见 Spec 第 182、183、207 行 | `text → reasoning(summary＋cipher-A) → text → reasoning(encrypted-only cipher-only) → text`；断言 block 类型序列、首 thinking 文本、第二 thinking 为空、两个 signature 不同 | **PASS** |
| NS-4 | 新 producer 固定输出本项目主 v1 carrier，payload 为 tag＋`encrypted_content` 的紧凑 UTF-8 JSON 经 unpadded base64url；见 Spec“项目主 v1 wire contract”及第 182、183 行 | 对 `cipher-A` 与 `cipher-only` 独立构造 current Spec carrier bytes，并逐个与 public thinking signature 比较 | **FAIL** |
| NS-5 | usage 使用 `I=max(0,T-R-W)`；`Q` 是 `O` 子集，只进入 `output_tokens_details.reasoning_tokens` 与诊断 facts，不得二次相加；见 Spec 第 187、365 行及“cache＋reasoning”数值向量 | `T=100,R=20,W=10,O=30,Q=12`；断言 public usage 为 `I=70,R=20,W=10,O=30,Q=12`，normalized total 为 `130` | **FAIL** |
| NS-6 | 生成 Anthropic-compatible public id，同时在诊断 facts value-exact 保留 upstream response id／model；见 Spec 第 188 行 | upstream `resp_independent_7ddf173`；断言 public id 以 `msg_` 开头、不等于且不包含 upstream id，重复输入稳定、不同 upstream id 映射不同，诊断字段保留原 `resp_` 与 model | **PASS** |
| NS-7 | unknown output item 必须显式失败，不能由空 text 或正常 terminal 掩盖；见 Spec 第 266 行及 response matrix | `type=future_semantic_item`；断言 `ResponseConversionError(code=unsupported_output_item, field_path=output[0].type)` | **PASS** |
| NS-8 | Server-tool no-revive，upstream 未请求 server tool item 时 response conversion 显式失败；见 Spec 第 136 行 | `type=web_search_call`；断言 `ResponseConversionError(code=server_tool_not_supported, field_path=output[0])` | **PASS** |
| NS-9 | Responses `failed` 不是成功 message，必须进入 typed error mapping；见 Spec 第 265 行 | terminal `status=failed`；断言 `ResponseConversionError(code=failed_response, field_path=status)` | **PASS** |

## 失败实证

### F-1：reasoning carrier producer 违反项目主 v1 wire contract

- **违反条款**：Spec 第 182 行要求每个 reasoning item 形成 thinking block和“本项目主 v1 carrier”；第 183 行要求 encrypted-only 同样使用项目主 v1；“项目主 v1 wire contract”冻结 prefix 为 `ghc-api-proxy:synthetic-reasoning:v1:`，payload 为最小 tag＋`encrypted_content` JSON。
- **失败断言**：临时 probe `/tmp/verify_nonstream_response_7ddf173.py:130`。
- **输入**：第一个 reasoning item 的 visible summary 为 `sum-Asum-B`、`encrypted_content="cipher-A"`；第二个是 `encrypted_content="cipher-only"` 的 encrypted-only item。
- **关键实际输出**：首个 signature 为 `copilot-api:synthetic-reasoning:v1:Y2lwaGVyLUE`。
- **关键期望输出**：首个 signature 为 `ghc-api-proxy:synthetic-reasoning:v1:eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIsImVuY3J5cHRlZF9jb250ZW50IjoiY2lwaGVyLUEifQ`。
- **命令结果**：最终独立矩阵中 `test_reasoning_uses_project_v1_carrier_and_preserves_each_payload` 为 FAIL；总进程退出码为 1。
- **已定位根因接缝**：`src/app/protocols/responses_anthropic.py:77` 调用 reasoning producer；`src/app/anthropic/thinking/responses_reasoning.py:7,36,38` 将 producer prefix 固定为 `copilot-api:synthetic-reasoning:v1:` 并直接对 ciphertext 做旧式 base64url。
- **修复路由建议**：根因明确，建议主会话交给 implementer，把 response producer 接到已冻结的本项目主 v1 codec，同时保留 upstream v1 仅作为 consumer compatibility。修复后应重跑本独立 probe，并验证两个 reasoning payload 分别 value-exact roundtrip。

### F-2：usage 丢失 reasoning token detail

- **违反条款**：Spec 第 187 行要求 usage 与 details 严格按冻结算式转换；第 365 行明确 `Q` 只进入 `output_tokens_details.reasoning_tokens` 与诊断 facts，不得丢失或二次相加。
- **失败断言**：临时 probe `/tmp/verify_nonstream_response_7ddf173.py:146`。
- **输入**：`input_tokens=100`、`cached_tokens=20`、`cache_write_tokens=10`、`output_tokens=30`、`output_tokens_details.reasoning_tokens=12`。
- **实际 public usage**：`input_tokens=70`、`cache_read_input_tokens=20`、`cache_creation_input_tokens=10`、`output_tokens=30`；缺失整个 `output_tokens_details`。
- **期望 public usage**：除上述四项外，还必须包含 `output_tokens_details.reasoning_tokens=12`；normalized total 仍为 `130`，不能把 `Q=12` 再加成 `142`。
- **命令结果**：最终独立矩阵中 `test_usage_cache_reasoning_vector_without_double_counting` 为 FAIL；diff 明确显示只缺 `output_tokens_details: {reasoning_tokens: 12}`。
- **已定位根因接缝**：`src/app/protocols/responses_anthropic.py:171-196` 的 `_convert_usage()` 只读取 input details，并在第 191～196 行只构造四个 Anthropic usage 字段；未读取或保留 `output_tokens_details.reasoning_tokens`，也未产生相关诊断 fact。
- **修复路由建议**：根因明确，建议主会话交给 implementer，扩展 typed Anthropic usage／诊断 facts 和 `_convert_usage()`，严格校验 `Q` 为有限非负整数，保留 `Q` 但不加入 total；同时补 `Q>O` 的 `usage_inconsistent` 路径。本轮只验证 happy-path 数值向量，`Q>O` 仍为 UNVERIFIED。

## Identity 正控

为证明 NS-6 不是 false-green，probe 在单独进程内 monkeypatch `anthropic_message_id_from_response_id()`，让它直接返回 upstream `resp_` id；未修改候选文件。

正控运行结果：

- 测试：`test_public_and_upstream_identity_are_separate_and_preserved`。
- 注入缺陷：public id 变为 `resp_independent_7ddf173`。
- 失败位置：`/tmp/verify_nonstream_response_7ddf173.py:171`。
- 关键失败：`AssertionError: False is not true : resp_independent_7ddf173`，即 `msg_` contract 断言按目标机制变红。
- 结果：1 test，1 failure，退出码 1。随后在全新 Python 进程运行真实候选时 NS-6 PASS，证明 mutation 未泄漏到真实结果。

## 实际运行

### Identity 正控

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py-response/src /home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/verify_nonstream_response_7ddf173.py --identity-positive-control`

结果：1 test，1 failure，退出码 1；失败原因与预期注入的 `resp_` public identity 泄漏一致。

### 最终独立矩阵

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/xp/src/ghc-api-proxy-py-response/src /home/xp/src/ghc-api-proxy-py/.venv/bin/python /tmp/verify_nonstream_response_7ddf173.py`

结果：9 tests，7 PASS，2 FAIL，退出码 1。失败项仅为 NS-4 与 NS-5；NS-1、NS-2、NS-3、NS-6、NS-7、NS-8、NS-9 均实际执行并 PASS。

## 明确未验证范围

以下项目超出本轮“current Spec non-stream happy path＋指定 typed errors”的派活范围，全部标记为 **UNVERIFIED**，不得从本报告的 PASS 项外推：

- stream／SSE envelope、upstream HTTP SSE parser、upstream WebSocket，以及 stream 与 non-stream normalized equivalence。
- route policy、model capability gate、request conversion、approval、hooks、History、tokenization observer 与 route integration。
- response hook／limit 通过后才 commit、upstream response close、HTTP Anthropic error envelope 与 status mapping。
- retry、失败 attempt usage 隔离、pre-commit／post-commit delivery semantics、attempt ownership。
- cancellation、shutdown、backpressure、global／request memory budget、queue／frame limits与资源关闭恰好一次。
- refusal、incomplete／`max_tokens`、cancelled、content filter、unknown incomplete reason、terminal `error` body及 malformed lifecycle。
- malformed tool arguments、server-tool 的其他类型枚举、unknown content part、empty legal success 与 invalid response schema 全矩阵。
- usage absent／estimated、`T<R+W`、`Q>O`、非法负数／boolean／非整数、modality／prediction details、failed-attempt usage 与 diagnostic fact persistence。
- public `msg_` 在 HTTP route 最终序列化后的可见性，以及 upstream `resp_`／model 在 History／trace 中的持久化；本轮只验证 converter 的 typed `ConvertedResponse`。
- reasoning producer→client echo→consumer 完整 roundtrip、strip policy、upstream v1 consumer compatibility、unknown／foreign／malformed carrier 分类。本轮只验证 non-stream forward output 的 cardinality、顺序、encrypted-only 保留与项目主 v1 producer bytes。

## 最终结论

候选 `7ddf17364d97349638d44352bbd9a9b025723ccc` 的 non-stream converter 已满足 text 顺序、tool call 保真、multiple reasoning／encrypted-only cardinality 与顺序、public／upstream identity 分离，以及 unknown／server-tool／failed typed error。identity 判据经过注入缺陷正控，具备判别力。

但 current Spec 明确要求的项目主 v1 reasoning carrier 和 reasoning usage detail 均未满足，因此总体 verdict 为 **FAIL**。修复 F-1 与 F-2 后需要重新运行同一独立矩阵；范围外项目仍保持 **UNVERIFIED**。

> 本报告由 verifier 叶子执行单元生成。按协作规则，报告本身仍需主会话安排独立 review；本轮未修改候选生产代码、候选测试或候选工作树。

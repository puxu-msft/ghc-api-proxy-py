# 提交 `0f9abbc` 评审：未声明端点的类型 allowlist

## 结论

**Verdict：needs-fix。blocker 0 条，major 1 条，minor 3 条，nit 0 条。**

allowlist 的失效方向本身正确：当目录没有 `supported_endpoints` 且 `capabilities.type` 不在实测表中时，拒绝在本机端点之间猜测，优于把整个新类型送往一个未经证实的端点后得到 400。这里没有更可靠的第三条自动路由；动态探测会把正常请求路径变成有副作用的能力发现，大小写归一化或按名称猜测也只是换一种推断。更好的第三条路是保留现在的 fail-closed 路由，同时把“目录明确给了空列表”“类型已读出但没有实测默认端点”“类型字段不可读”作为三种不同原因贯穿到请求错误和 `debug models`，让新增类型既不会被误送，也不会被误报。

当前实现只完成了前半段。未知类型确实在网络前被拒绝，`debug models` 也确实出现 `no-endpoints`，但报告和异常把原因压扁并在部分输出中给出相反解释。因此，“操作者足以发现模型因新类型而失效”这一声称尚不成立。

## Findings

### F1．未知类型的失败原因被压扁，报告还会输出错误图例

- **位置**：`src/app/model_provider/types.py:33-41`、`src/app/model_provider/types.py:119-128`、`src/app/model_provider/types.py:145-147`、`src/app/debug/models.py:29-30`、`src/app/debug/models.py:42-53`、`src/app/debug/models.py:103-128`、`src/app/debug/models.py:187-203`、`src/app/debug/models.py:360-363`
- **严重度**：major
- **问题**：`resolve_endpoints(None, model_type="chat-v2")` 返回空端点且 `advertised=False`。`build_rows` 随即把 `not resolved.advertised` 解释成 `assumed=True`，虽然这里没有任何端点被假定；状态则与上游显式空列表共用 `no-endpoints`。请求侧抛出的 `CapabilityMissing` 又声称 provider “advertises no endpoints”，而真实情况是上游没有声明端点、代理也没有这个类型的实测默认值。`status_of` 的文档甚至明确说 `no-endpoints` 只代表显式空列表，与新行为直接矛盾。
- **依据**：对提交对应代码的只读探针产生 `ModelRow(... status='no-endpoints', endpoints=(), assumed=True)`，文本末尾显示 `? not named by upstream; the standard endpoint for this model type`，但端点列是 `-`，并不存在“standard endpoint”。这既不能告诉操作者是 `chat-v2` 触发了 allowlist miss，也把修复责任错误地指向“upstream offered nothing”。此证据足以直接行动，因为它走的是生产 `build_rows` 和 `render_text`，且相关文件与提交 `0f9abbc` 逐字节相同。
- **建议**：不要恢复猜测路由。让 endpoint resolution 保留来源／失败原因，而不再用单个 `advertised: bool` 同时表示“上游是否声明”和“是否用了默认值”。至少区分 `explicit-empty`、`defaulted`、`unmeasured-type`、`unreadable-type`；`debug models` 对后两者显示原始 `capabilities.type` 或明确状态，`CapabilityMissing` 也应说明“没有该类型的实测默认端点”。只有真正填入默认端点的行才设 `assumed=True` 和显示 `?`。

### F2．`model_type_of` 的 fail-closed 行为稳健，但不可读字段被当成普通无端点而非 malformed

- **位置**：`src/app/model_provider/types.py:107-116`、`src/app/debug/models.py:134-146`
- **严重度**：minor
- **问题**：`capabilities` 不是 `dict` 或 `type` 不是字符串时，`model_type_of` 返回空字符串；路由随后安全拒绝，这一部分没有异常吞掉或网络误送。但报告的 `_wrong_shape` 不检查 `capabilities` 与 `capabilities.type`，于是不可读字段也被标成 `no-endpoints`，丢失了“目录形状坏了”这一事实。声明参数是 `Mapping[str, Any]`，但嵌套 `MappingProxyType({"type": "chat"})` 也会被当成不可读；实际 HTTP JSON decoder 产出 `dict`，所以这不是当前真实目录的兼容性 blocker。
- **依据**：只读探针确认 `{"capabilities": {"type": 1}}` 和非 `dict` mapping 都解析为 `""` 并得到空端点；当前保存的 2026-08-20 live catalog 中 42 个条目的 `capabilities.type` 都是小写字符串。大小写精确匹配与 allowlist 的“只采用实测值”原则一致：`"Embeddings"` 没有被本次证据测过，不应通过 `casefold()` 自动扩权。因此大小写敏感本身可接受，问题在于没有把原值和失败原因报告出来。
- **建议**：保持精确匹配；不要未经证据做大小写或空白归一化。扩展 report-side shape validation，并让 resolution 结果保留 unreadable 与 unknown 的区别。若希望 API 真正接受任意 `Mapping`，则将嵌套检查改为 `Mapping` 并相应测试；若只承诺 JSON object，则把签名／文档收窄到这个事实即可。

### F3．核心断言能咬住旧 catch-all，但没有覆盖“新非空类型”与错误的 `assumed` 状态

- **位置**：`tests/unit/test_debug_models.py:95-119`、`tests/unit/test_model_provider.py:352-378`
- **严重度**：minor
- **问题**：两项改动测试不是恒真断言。恢复旧 `get(model_type, DEFAULT_ENDPOINT)` 会让 `completer` 和 `typeless` 的空集合断言失败；删除 `chat` 或 `embeddings` allowlist 项也会让对应正例失败。鉴别力的缺口是：测试把未知类表示为缺失 type，而没有使用用户关心的非空未来值如 `chat-v2`；同时只断言了正例的 `assumed`，没有断言 `completer`／未知类型不应被描述成“已填入默认端点”。因此 F1 的 `assumed=True` 和错误图例在全部测试通过时仍然存在。
- **依据**：`test_an_unstated_endpoint_is_filled_in_from_the_model_kind` 对 `completer` 和 `typeless` 只检查 `endpoints`／`status`。渲染测试使用共享 `CATALOG` 中合法的 `chat` 默认值，所以它只证明有真实默认端点时的 `?` 图例，不会看到仅含 unknown-type 行时的矛盾。用户禁止在共享树施加变异，因此本次未做 mutation；上述结论来自分支和断言的静态因果对账，权重足以要求一个针对已指出错误机制的小回归用例，不支持扩建测试矩阵。
- **建议**：把 `typeless` 替换或补充为 `capabilities.type="chat-v2"`，并针对 unknown-only report 断言原因可见、没有虚假的 standard-endpoint 图例。修复 F1 后，断言只有实际得到默认端点的两行 `assumed=True`，未知／不可读类型走各自明确来源状态。

### F4．实测数字有目录快照佐证，但“本主机根本不可服务”和单行引用说得比证据更强

- **位置**：`src/app/model_provider/types.py:96-104`、`tests/unit/test_debug_models.py:95-96`、`tests/unit/test_debug_models.py:115`、`tests/unit/test_model_provider.py:352-376`
- **严重度**：minor
- **问题**：14 个 `chat`、3 个 `embeddings`、1 个 `completion` 的集合数字与保存的 live catalog 一致，但“`gpt-41-copilot` is not served by this host at all”超出了对四个 HTTP path 的有限探测；测试注释中的“every endpoint this host offers”也没有说明范围。`fetch.ts:310` 确实存在并构造 `proxy` host 上的 `v1/engines/<model>/<endpoint>`，但该行本身不读取 `capabilities.type`，所以“line 310 sends that type”需要跨文件证据才成立。
- **依据**：`exp/260820-websearch-probe/raw/models-live.json` 有 42 个模型，其中恰有 18 个缺键，分布为 14／3／1，且唯一 `completion` 是 `gpt-41-copilot`。本次任务给出的实测事实支持 `/chat/completions`、`/responses`、`/v1/messages` 为 400，`/completions` 为 404；仓库中没有这轮逐请求响应的独立原始工件，因此只能按任务背景采用，不能扩大为所有可能 path／transport。参考 checkout `5863f5a7088958050792b5dccbe8b46c6e13eccc` 中，`src/extension/completions-core/vscode-node/lib/src/openai/model.ts:110-113` 按 `type === 'completion'` 选模型，`openai/fetch.ts:470-472` 使用 `endpoint = 'completions'`，`openai/fetch.ts:309-310` 才构造 proxy URL；`networkConfiguration.ts:66-73` 证实 `proxy` 选择 token 的独立 service endpoint。整体含义正确，单一行号的归因不完整。
- **建议**：把绝对句收窄为“在 2026-08-20 探测的这四个 HTTP path 上均不可用；参考实现把 completion 类型送往 completions-proxy service”。引用至少同时指向 `model.ts:112`、`fetch.ts:310` 和 `fetch.ts:470`，或改成不声称 line 310 自己完成 type dispatch。

## 按重点逐项核对

### 1．Allowlist 的失效方向

- **判断**：方向正确，证据权重足以采用。未知类型在网络前拒绝比默认猜 `/chat/completions` 更好；显式 `supported_endpoints` 仍优先，所以上游新增类型只要同时声明端点就不会受影响。
- **代价**：仅在“新类型且遗漏 `supported_endpoints`”的交集内整类失败。这个代价可接受，但前提是原因可诊断；目前 `no-endpoints` 只暴露结果，不暴露 allowlist miss，因此不充分。
- **第三条路**：不是另猜一个 endpoint，而是 fail-closed + 原因保真 + 明确运维呈现。待实测后再扩 allowlist。

### 2．`model_type_of`

- 小写精确匹配符合本提交证据边界；`Embeddings` 不匹配不是缺陷。
- `capabilities` 非 `dict`、`type` 非字符串时路由安全拒绝，没有崩溃。
- 诊断不稳健：不可读、缺失、未知值被压成同一个空字符串，见 F1、F2。

### 3．测试鉴别力与 fixture

- 两个点名测试都能识别旧 catch-all，不是恒真。
- `_model` 默认加入 `"type": "chat"` 与当前真实目录形状一致；大部分使用显式 `supported_endpoints` 的用例不受 type 影响，专门的 `typeless` 用例也保留了缺失 type 的行为，因此 fixture 变更本身没有静默删掉该类覆盖。
- 它间接让共享渲染样本始终含一个合法 assumed endpoint，未覆盖 unknown-only 图例错误；这需要一个小而直接的回归用例，见 F3。

### 4．注释与代码／引用一致性

- allowlist 代码与“只列 chat、embeddings”一致。
- 14／3／1 和 18／42 与保存的 live catalog 快照一致。
- `fetch.ts:310` 存在，proxy host 与 path 含义正确；type dispatch 并不发生在该行，见 F4。
- `types.py` 之外有多处旧注释仍把 `advertised=False` 等同于用了默认端点，见 F1；这些不是措辞 nit，而会生成错误图例。

### 5．静默吞错与过度声称

- 没有发现异常被 catch 后静默忽略；请求会明确抛 `CapabilityMissing`，且发生在网络前。
- 发现的是错误上下文被数据模型压扁，而非 exception 被吞：未知类型与坏 type 字段都失去原始原因，见 F1、F2。
- “本主机根本不可服务”是有限探测向全称的外推，见 F4。

## 已检查且无发现

- **显式 endpoint 优先级**：`supported_endpoints` 为非空 list 时仍直接采用，不受 type allowlist 影响。
- **显式空列表与缺键的路由区别**：空列表保留 `advertised=True`，缺键才查询 allowlist；没有回归成“空列表也补默认值”。
- **网络前拒绝**：空能力集由 `require_endpoint` 在 provider send 调用网络 client 前拒绝。
- **核心表内容**：`chat → /chat/completions`、`embeddings → /embeddings` 与任务给出的实测一致；`completion` 未误列。
- **格式与静态检查**：`git diff 0f9abbc^ 0f9abbc --check` 通过；对三个变更文件运行 `ruff check` 通过。

## 验证记录与范围

- `git diff --exit-code 0f9abbc -- src/app/model_provider/types.py src/app/debug/models.py src/app/model_provider/github_copilot.py tests/unit/test_debug_models.py tests/unit/test_model_provider.py` 返回 0，因此只读运行使用的相关代码与目标提交一致；这不声称整个脏工作树等于该提交。
- `uv run pytest tests/unit/test_debug_models.py tests/unit/test_model_provider.py`：66 passed。
- 两个点名测试单独运行：2 passed。
- `uv run ruff check src/app/model_provider/types.py tests/unit/test_debug_models.py tests/unit/test_model_provider.py`：All checks passed。
- 未运行全仓测试，避免把并行会话和脏工作树的无关结果归给本提交。
- 未施加 mutation，遵守用户对共享工作树的明确禁令；测试鉴别力结论没有伪称为 mutation 实证。

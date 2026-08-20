# Request ID 与 count-tokens 前缀评审

## 范围与证据

本评审只读检查了共享工作树中 `src/app/observability/request_log.py`、`src/app/server/pipeline_app.py`、`src/app/observability/request_log_file.py` 及相关单元和 HTTP 测试；未执行 Git 写操作，也未改动源文件。结论强度：足以据此决策。依据是当前工作树源码的完整调用链，以及针对生产 Python 文件的精确检索：`format_completion_line(` 只有定义和 `pipeline_app._log_completion` 一处生产调用；`RequestLine` / JSONL 请求记录在仓库内没有额外的读取者或解析器。

## 发现

### 认可：所有会写完成行的真实路径都会把最终 `LogStatus` 传给渲染器；200 的流中断不会藏掉 `req=`

`_log_completion` 先以 `status_for(status_code, override=trace.status_override)` 求出唯一的最终状态，再将同一个 `status` 同时交给 JSONL 写入器和 `format_completion_line`（`src/app/server/pipeline_app.py:203-208`）。非流式响应由 `_serve` 在响应完成后调用它（`src/app/server/pipeline_app.py:240-245`）；流式响应则由 `_StreamAccounting.finish()` 调用它（`src/app/server/pipeline_app.py:438-458`）。后者在没有完整交付时，以 `_ending()` 写入 `fail` 或 `gone` 覆盖值（`src/app/server/pipeline_app.py:454-473`）。因此，流式请求虽保留上游已送出的 HTTP 200，断流、上游异常与客户端离开仍分别以 `fail` 或 `gone` 进入渲染器。

渲染器的 `outcome != "ok"` 正确控制 `req=` 的出现（`src/app/observability/request_log.py:316,365-367`），故上述 200 流式失败和 `gone` 均会显示行尾 join key。唯一生产调用点的检索结果也证实没有漏传 `status` 的现有路径。覆盖这个关键情形的测试见 `tests/unit/test_request_log.py:73-77` 和 `tests/unit/test_request_log_file.py:159-186`。

### 应改：让 `outcome` 同时成为整行“成功”语义的唯一来源，而不是只控制 `req=`

当前代码已传入最终 `outcome`，但 `succeeded` 仍仅由 `line.status_code < 400` 推导（`src/app/observability/request_log.py:316-327`）。所以真实的流式 `fail` 或 `gone` 行会有 `[FAIL]` / `[GONE]` 前缀与行尾 `req=`，却仍把 HTTP `200` 涂成绿色，并按成功行形状把 `METHOD /path` 压缩成 `<inbound_format>/<model>`。这与该模块自己“成功行省略 route，失败行保留 route”的契约相冲突（`src/app/observability/request_log.py:3-7,270-290`），也会让最关键的 200 中断行同时说“失败”和“成功”。

偏好修复为在已解析 `outcome` 后使用 `succeeded = outcome == "ok"`，并据此决定状态码颜色和 `_subject()` 的形状。HTTP 200 仍应保留为事实，但在 `fail` / `gone` 行上应使用失败语义呈现。这不是本次 `req=` 是否显示的 blocker，因为 ID 已正确显示；但它是此次引入显式最终状态后立刻可见的语义分裂，应在合并前一并收拢。

### 应改：移除 `status=None` 的静默回退，令最终状态成为 `format_completion_line` 的必传参数

当前签名允许调用者漏传状态并退回 `status_for(line.status_code)`（`src/app/observability/request_log.py:301-303,310,316`）。这对今天的唯一生产调用没有问题，但正是未来新增调用点最容易再次制造的缺陷：一个状态码为 200 的已断流请求会静默被判为 `ok`，从而重新藏掉 `req=`。类型系统无法为可选关键字参数报漏传错误。

我的明确偏好是改为必传的 `status: LogStatus`，不保留默认值。`_log_completion` 已经天然拥有且传递该值（`src/app/server/pipeline_app.py:203-208`），因此生产路径无需额外推导；未来调用者漏传时 Pyright 会直接阻止，而不是让控制台悄悄给出错误的成功结论。单元测试中若需要按 HTTP status code 测普通行，应显式传 `status_for(line.status_code)`，或经一个仅供测试使用的小辅助函数表达这一默认情形。相比便利性，这能保证“最终结果”只在一个明确位置决策。

### 认可：`gone` 应显示 `req=`

接受“显示”的裁决。`gone` 表示客户端断开或关停取消，调用方没有收到完整答案，而不是成功；并且实现明确将这种情况与 upstream `fail` 区分，但不会把它伪装成 `[ OK ]`（`src/app/server/pipeline_app.py:460-473`；`src/app/observability/logging.py:16-22`）。排障时需要用 request id 关联 JSONL 中的已接收块、字节数、时间和连接信息，因此让它满足 `outcome != "ok"` 很合适（`src/app/observability/request_log.py:365-367`）。没有发现反对该裁决的具体场景。即使用户主动取消是常规事件，`[GONE]` 已将它同 proxy/upstream 的红色失败区分开，`req=` 只是按需追溯的 join key，不会使它冒充失败。

### 认可：把 `count_tokens` 作为 `RequestLine` 上的布尔事实、在展示层生成后缀，是正确的分层

`inbound_format` 的值来自 `route.wire_format.value`（`src/app/server/pipeline_app.py:252-257`），而 `WireFormat.ANTHROPIC_MESSAGES` 同时服务普通 Messages 和 count endpoint（`src/app/server/inbound.py:33-44`）。将 `-count-tokens` 预先拼进 `inbound_format` 会把展示名伪装成 wire-format 枚举值，破坏该字段现有含义。当前方案由路由一次决定 `trace.count_tokens`，再原样纳入聚合记录（`src/app/server/pipeline_app.py:130,180,257`），最后仅在成功行 `_subject()` 中组成显示标签（`src/app/observability/request_log.py:270-285`）；这保留了 wire format 的语义，也能让没有任何 counter 成功回答的 count 请求仍携带端点事实。

JSONL 内确实同时有原始 `path` 和分类后的 `count_tokens`，但这是有意的、单向派生的反规范化，不是三份相同事实独立写入。`path` 是客户端实际路径，`count_tokens` 是路由分类，`counter` 则是“哪一个计数器回答了”的运行时结果，后者在 count 请求失败于 counter 之前时为空（`src/app/observability/request_log.py:96,104-105,177-188`）。`counter` 不能替代 endpoint 分类。`asdict(line)` 将这个布尔值写进 JSONL（`src/app/observability/request_log_file.py:31-43`），而仓库内检索到的唯一 JSONL 读取者是其专用测试（`tests/unit/test_request_log_file.py:47-52`）。因此没有发现仓库内的 schema consumer 会因新增键而被破坏。

### 认可：未发现 TUI、structlog processor、history 或其他行/记录读取者被两处改动破坏

实际检索结果如下。

- 生产中 `format_completion_line(` 的唯一调用在 `src/app/server/pipeline_app.py:206`；不存在解析旧 `request_id=` 控制台文本的生产消费者。
- structlog processor 仅从事件字典读取独立的 `status` 并渲染固定前缀，然后把 event 当成不透明字符串输出（`src/app/observability/logging.py:34-48,76-107`），不解析 `req=`、请求格式前缀或 detail。
- TUI/footer 只消费 `ActiveRequestRegistry.snapshot()` 的 `ActiveRequest`，字段为 `request_id`、`model`、开始时间、字节数和 attempts（`src/app/observability/tui.py:93-118`；`src/app/observability/footer.py:26-37,103-165`），不消费完成控制台行或 `RequestLine`。
- 对 `app.observability.request_log`、`RequestLine`、`request_logs_dir`、`requests-*.jsonl` 的生产检索只命中 `request_log_file.py` 与 `pipeline_app.py`，没有 history 存储模块的导入或 JSONL reader。JSONL 专用测试也已将新增键纳入完整键集断言（`tests/unit/test_request_log_file.py:87-150`）。

该结论只覆盖当前仓库内代码；外部自建 JSONL reader 不在本次可检索范围内。不过新增 JSON object 键通常是兼容扩展，且本项目没有声明严格外部 schema consumer。

### 认可：detail 后以单个空格接 `req=` 可接受，不建议增加视觉分隔符

当前顺序为 `...: <detail> req=<id>`（`src/app/observability/request_log.py:357-367`），满足 ID 必须在最后且不打断读者先读故障解释的要求。无颜色终端的示例 `...: upstream is down req=3f2a...` 清楚、常见，也与此前字段用空格分隔的语法一致。颜色开启时 detail 的红色 span 已结束，随后 `req=` 单独以 DIM span 渲染，因此不存在颜色泄漏或黏连（`src/app/observability/request_log.py:363-367`）。

不建议改成 `| req=`、括号或第二个冒号：它们增加横向噪声，而 request id 已有稳定键名并固定在末尾。detail 是自由文本这一事实不构成歧义，因为 key 的 ` req=` 前导空格和固定末尾位置足以区分；detail 自身即使以标点结尾也仍自然可读。

## 结论

没有 blocker。现有完成行路径均把真实最终状态传给渲染器，因而成功行不显示 request id，200 的流式 `fail` / `gone` 行会在最后显示 `req=<id>`；count-tokens 成功行也正确显示 `anthropic-messages-count-tokens/`。建议合并前处理两项应改：将整行的成功语义改由已传入的 `outcome` 决定，并使该 `outcome` 成为渲染函数的必传参数，防止未来调用点静默退化。
## 主会话处置（2026-08-20，用户裁决后）

评审的四条「认可」照单接受，不再复述。两条「应改」我起初判为「本轮不做／暂缓」，理由分别是范围（改变可见行形，属产品面）和改动面（35 处调用点撞上同伴在途编辑）。**用户当天直接裁决两条都做**，并确认「200 但流中断应该是 FAIL」。以下是落地结果与我在裁决范围内自行决定的两处细节。

### 已采纳：`outcome` 决定整行的成功语义

`succeeded` 改为 `status == "ok"`，同时决定状态码配色与 `_subject()` 的行形。200 的流中断行现在读作 `[FAIL] … 200 POST /v1/messages claude-opus-5 61.0s …`，状态码涂红，不再折叠成 `<inbound-format>/<model>`。

裁决范围内自行决定的两点，均已在代码注释与测试里写明理由：

1. **`gone` 不涂红，涂黄。** `logging.py` 的 `STATUS_PREFIXES` 里对 `[GONE]` 有一条在先的裁决：交互式客户端按 Esc 取消是日常事件，把它涂成和上游 tear 一样的红会把真正的失败淹掉。新增 `STATUS_COLOURS = {"ok": GREEN, "fail": RED, "gone": YELLOW}` 三档，既让 `gone` 离开「无需过问」的绿，又不宣称代理坏了。
2. **`gone` 仍然失去成功行形**（显示 `METHOD /path`）。用户的裁决是「outcome 决定整行的成功语义」，而 `gone` 的语义是没人收到答案，不该穿成功的衣服。代价是取消行会多出 `POST /v1/messages` 这一段近乎恒定的宽度；若认为不值，把 `succeeded` 改成 `status != "fail"` 即可，是一行的事。

### 已采纳：`status` 改为必传参数

签名改为 `status: LogStatus`，无默认值。生产侧 `_log_completion` 本来就持有该值。测试侧 36 处调用点逐个显式补齐，其中 6 处按各自的 `status_code` 订正为 `fail`；未引入把状态藏起来的测试辅助函数。全仓 pyright 0 error 同时证明了不存在漏传的调用点。

新增回归 `test_the_verdict_rather_than_the_status_code_decides_how_the_line_reads`，钉住三件事：同一条 200 记录在 `fail`/`gone` 下取路由行形、在 `ok` 下取折叠行形，以及三档配色。

验证：`uv run pytest tests --ignore=tests/tui` 1515 passed / 2 skipped；`ruff check src tests` 通过；`pyright src tests` 0 error。

## 复评（增量）

本节只评审用户裁决后落地的最终状态、必传化与三档配色，不重复前文已认可的 request id、count-tokens 前缀和 JSONL 结论。结论强度：足以据此决策。依据是当前源码调用图、测试源码，以及一次只读 AST 检查：`src/app/observability`、`src/app/server` 与 `tests` 内共 45 个 `format_completion_line()` 调用，缺少 `status=` 的调用为 0，字面量状态值落在 `LogStatus` 以外的调用为 0。

### 认可：最终 verdict 已成为成功行形与状态码颜色的唯一来源

`format_completion_line()` 现要求 `status: LogStatus`，没有默认值（`src/app/observability/request_log.py:311`）；`succeeded` 唯一按 `status == "ok"` 判断，状态码也通过 `STATUS_COLOURS[status]` 上色（`src/app/observability/request_log.py:324,332-334`）。这正好消除了原来 200 的断流行在 `[FAIL]` 前缀下仍绿色、仍折叠路径的矛盾。新增回归明确覆盖同一条 HTTP 200 记录的 `fail`、`gone`、`ok` 三种 verdict，检查非成功路由行形、成功折叠行形和三档状态码颜色（`tests/unit/test_request_log.py:82-104`）。

生产端仍只有 `_log_completion()` 一处调用渲染器，且其 `status` 来自 `status_for(status_code, override=trace.status_override)`（`src/app/server/pipeline_app.py:205-208`）。`LogStatus` 的唯一真实生产者是该函数及 `_StreamAccounting._ending()`；后者只返回 `fail` 或 `gone`（`src/app/server/pipeline_app.py:463,466-479`），默认分支则由 `status_for()` 返回 `ok` 或 `fail`（`src/app/observability/request_log.py:378-389`）。没有发现真实路径能传入 `LogStatus` 之外的值。

### 认可：`gone` 涂黄不是偏离裁决，而是把三值 verdict 一致地落实到两层显示

“outcome 决定成功语义”不等于把所有非 `ok` 压成同一个错误等级。`gone` 仍因 `status != "ok"` 失去成功行形、保留 `req=`，所以绝没有被当成成功；黄色表达的是它与 proxy/upstream `fail` 不同的操作含义。此选择与 structlog 层已存在的 `[GONE]` 黄色前缀完全一致：`PREFIX_COLOURS` 使用 `ok → GREEN`、`fail → RED`、`gone → YELLOW`（`src/app/observability/logging.py:63-72`），新的 `STATUS_COLOURS` 对状态码使用同一映射（`src/app/observability/request_log.py:60-62,332-334`）。因此就前缀和 HTTP status code 这两个 outcome 标记而言，三档语义是一致的。

### 认可：`gone` 保持 `METHOD /path` 的非成功行形是正确的权衡

我同意不为高频取消额外保留折叠成功行形。用户已裁决最终 outcome 决定整行成功语义，而 `gone` 的不变量是“没有人收到答案”，所以它不应穿上“答案已交付”的 `<inbound-format>/<model>` 形式。`_subject()` 的说明和实现准确表达这一点（`src/app/observability/request_log.py:278-300`）。额外的 `POST /v1/messages` 宽度是可见代价，但它还保留了真正有用的事实：并非所有可流式路由都必然是同一路径，且取消后要追查时，实际 endpoint 比抽象 wire format 更能定位请求。若为常见取消牺牲这条一致性，会重新引入“前缀说未完成、正文看似已成功交付”的次级版本；不建议这样做。

### 应改：`gone` 的 detail 仍被固定涂红，和“gone 不宣称 proxy 坏了”的三档语义相冲突

前缀与 HTTP 200 状态码已经正确为黄色，但任意 `detail` 仍无条件以 `RED` 渲染（`src/app/observability/request_log.py:369-371`）。真实 `gone` 路径必定写入 `delivery stopped before upstream finished`（`src/app/server/pipeline_app.py:479`），因此彩色终端实际显示的是黄色 `[GONE]`、黄色 `200`、但红色的取消说明。这会削弱刚采纳的理由——“不要把正常 Esc 取消和 upstream reset 一样涂红”——并使完整行的事件等级不一致。现有新回归只断言状态码含黄色 span，尚不能发现 detail 仍为红色（`tests/unit/test_request_log.py:89-104`）。

建议让 detail 的颜色至少对 `gone` 采用 `YELLOW`，同时维持 `fail` 的 `RED`；并在该回归中断言一个带 detail 的 `gone` 行没有红色 detail span。此项不阻断本次两个原始需求，也不否定“状态码和前缀三档已对齐”的认可，但它直接关系到主会话自行采用的“gone 黄色而非红色”产品理由，应在合并前收口。

## 增量结论

没有 blocker。两项用户裁决均已正确落地：必传 `status` 没有漏掉调用点，且 `fail`/`gone` 都不再使用成功行形；`gone` 的黄色 status code 与 structlog `[GONE]` 前缀一致。唯一应改是将真实 `gone` 行的 detail 从固定红色纳入黄色层级，否则用户在彩色终端仍会看到每条取消带着红色说明。

## 主会话处置（复评增量）

### 已采纳：detail 纳入三档配色

复评是对的，而且它指的正是我自己给 `gone` 涂黄的那条理由被抵消：前缀黄、状态码黄，说明文字却固定红，一条取消行整体仍读作事故。detail 改为与状态码同取 `STATUS_COLOURS[status]`——它是同一个 verdict 的解释，不能比 verdict 本身更响。`fail` 仍是红，`ok` 行若带 detail 则为绿（生产上不存在这种组合，`detail` 只在 `_dispatch` 的 400 分支与 `_StreamAccounting._ending()` 的覆盖分支写入）。

回归补在同一个用例里：一条带 detail 的 `gone` 行不含任何红色 span，且说明文字是黄色 span。第一版断言把时长写成 61 秒，`duration_colour` 自己就把它涂红了，断言因此没有分辨力——改成 12 秒，让行内任何红都只可能来自 detail。做过变异验证：把生产代码改回固定 `RED`，该用例变红；还原后 45 passed。

另记一条复评顺带证实的事实：`logging.PREFIX_COLOURS` 已有同样的 `ok/fail/gone → GREEN/RED/YELLOW` 三档。两处是同一个判断的两次陈述（一个给固定词上色，一个给数字和句子上色），已在 `STATUS_COLOURS` 的注释里互相指认，改一处要改两处。

验证：`uv run pytest tests --ignore=tests/tui` 1519 passed / 2 skipped；`ruff check src tests` 通过；`pyright src tests` 0 error。

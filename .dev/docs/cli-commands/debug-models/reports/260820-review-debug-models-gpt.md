# `ghc-api-proxy debug models` 独立证伪评审

评审日期：2026-08-20

评审范围：`src/app/debug/__init__.py`、`src/app/debug/models.py`、`src/app/cli.py`、`src/app/model_provider/github_copilot.py`、`src/app/auth/providers.py`、`tests/unit/test_debug_models.py`、`tests/unit/test_model_provider.py`，以及这些改动直接依赖的 catalog 解析与 composition 路径。

结论：**needs-fix**。未发现 blocker；发现 3 项 major、3 项 minor。真实凭据路径成功读取了当前 Copilot catalog，并输出 42 个模型；无凭据失败信息也简短、可操作。主要问题集中在预期错误仍吐 traceback、畸形 catalog 被静默改写成看似可信的摘要，以及未清理上游文本中的终端控制字符。

证据权重：下列运行结果均来自当前工作树的一手执行，足以据此行动；对真实上游 catalog 的结论只适用于 2026-08-20 本次凭据、当前环境与当时上游响应，不外推为所有账户或未来 catalog。资源释放结论由源码 `finally`、composition 异常探针与 provider refresh 异常探针共同支持，足以覆盖普通异常路径；没有对进程被 `SIGKILL` 等不可清理情形作保证。

## 发现汇总

| ID | 严重度 | 位置 | 结论 |
|---|---|---|---|
| F1 | major | `src/app/cli.py:394` | 缺失或无效 config 属于预期操作员错误，却输出完整 traceback。 |
| F2 | major | `src/app/debug/models.py:65-77,103-139` | 畸形 entry／字段被静默丢弃或改写，最终摘要会把 8 个上游 entry 报成 4 个模型，并把不可读 policy 报成 `ok`。 |
| F3 | major | `src/app/debug/models.py:71-72,195-235,251-265` | 上游字符串未经控制字符清理即进入终端，换行可伪造表格行，ANSI escape 可改变终端状态。 |
| F4 | minor | `src/app/cli.py:390`、`src/app/debug/models.py:268-277`、`src/app/ghc_client/models.py:41` | `--json` 保留普通 JSON 的解码后语义字段，但绝非“verbatim”：外层被包装、空白与 Unicode 编码被重写，重复 key 等 wire 信息在解析时已丢失。 |
| F5 | minor | `src/app/debug/models.py:215-235` | 列宽没有上限且按 `len()` 而非 terminal cell 计量，极长 id 会把所有行撑到超宽；CJK／emoji 也会错位。 |
| F6 | minor | `tests/unit/test_debug_models.py:127-139,206-217,258-288` | 数个测试名和 docstring 声称的契约强于断言实际能辨别的行为，当前 17 个相关测试全绿仍看不见 F1～F5。 |

## 详细发现

### F1 — 预期 config 错误输出 traceback

**位置：** `src/app/cli.py:394`。

**严重度：** major。

**可复现输入：**

`/tmp/ghc-review-debug-models-bad.yaml`：

```yaml
model_providers:
  ghc:
    type: definitely_not_a_provider
unknown_top_level: true
```

命令：

```bash
uv run ghc-api-proxy debug models --config /tmp/ghc-review-debug-models-bad.yaml
```

**实际输出：** 完整原始输出见“命令实跑记录”，核心尾部如下。

```text
ValidationError: 2 validation errors for ProxyConfig
model_providers.ghc.type
  Input should be 'github_copilot'
unknown_top_level
  Extra inputs are not permitted

[exit=1]
```

缺失文件同样从 `src/app/cli.py:394` 展开到 `src/app/config/loading.py:92`，最后才显示 `FileNotFoundError: configuration file not found: /tmp/ghc-review-debug-models-missing.yaml`。这不是上游不可控故障，而是 CLI 明确接受 `--config FILE` 后必须可读地报告的预期输入错误。相比之下，不存在的 provider 会得到 Typer usage error，无 token 会得到一行带修复命令的错误；config 路径行为明显不一致。

**建议：** 在 `debug_models` 的 config 加载边界捕获 `FileNotFoundError`、YAML parse error 与 Pydantic `ValidationError`，向 stderr 输出简短的 `error: ...` 并以非零码退出。保留字段路径与原因，不要吞掉诊断；不要打印内部调用栈。优先复用 CLI 已有的统一错误呈现方式，而不是为该子命令另建验证框架。

### F2 — 畸形 catalog 被静默改写成可信但错误的摘要

**位置：** `src/app/debug/models.py:65-77,103-139`。

**严重度：** major。

**可复现输入：** `data` 中放入 `42`、`None`、`[]`、空 dict、`supported_endpoints` 为字符串、`policy.state` 为 dict，以及两个可读 entry。完整 `python -c` 命令见“命令实跑记录”。

**实际输出：** 上游 `data` 有 8 个元素，输出却无告警地写成 `4 models`。字符串 endpoint 被改写成 `no-endpoints`；不可读的 policy state 被当作空字符串，进而写成 `ok`。

```text
ROWS:
ModelRow(id='nonstr-policy', status='ok', vendor='', family='', endpoints=('/responses',), undriven=frozenset(), context_window=None, max_output_tokens=None)
ModelRow(id='string-endpoints', status='no-endpoints', vendor='', family='', endpoints=(), undriven=frozenset(), context_window=None, max_output_tokens=None)
...
ghc  https://example.invalid
4 models, 3 routable, 1 no-endpoints
```

`_mapping()` 把非 dict 直接变成 `{}`，`_text()` 把非字符串直接变成 `""`，随后无 id 的 entry 被 `continue` 丢弃。此实现确实没有 crash，但把“无法读取”伪装成“上游没提供”或“可以路由”，并且没有留下任何错误。这与该命令用于排障的目的冲突，也违反项目的错误不得静默吞掉约束。

**建议：** 保持“单个坏 entry 不拖垮整个 provider”的容错目标，但让 projection 同时返回结构化 diagnostics，例如原始 entry 数、跳过数及每个不可读关键字段的原因；text 输出至少写 `4 readable models, 4 malformed entries`，并把已具 id 但 endpoints／policy 类型不合法的 entry 标成 `invalid-catalog` 或等价的明确状态。`--json` 继续提供完整语义载荷，不应成为默认摘要静默丢错的借口。

### F3 — ANSI 与换行可破坏默认表格

**位置：** `src/app/debug/models.py:71-72,195-235,251-265`。

**严重度：** major。

**可复现输入：** `id="ansi-\x1b[31mRED\x1b[0m\nFAKE"`、`vendor="V\nINJECTED"`，endpoint 为 `/responses`。

**实际输出：** `repr` 证明 escape 与换行原样进入最终字符串；实际 render 中 `FAKE` 和 `INJECTED` 被画成新行，ANSI 将 `RED` 切换为红色。

```text
RENDER_REPR:
'...\nansi-\x1b[31mRED\x1b[0m\nFAKE ... ok ... V\nINJECTED ... /responses...'
RENDER:
...
ansi-[31mRED[0m
FAKE                                                                                                                                                 ok            V
INJECTED  -             -    -  /responses
...
```

这首先是输出正确性缺陷：一个 model entry 能伪造额外物理行并破坏列归属。仓库已有同类、可复用的处理依据：`src/app/observability/footer.py:22-23,168-179` 会先删除 C0／DEL 控制字符，并用 `rich.cells` 处理 terminal cell 宽度。

**建议：** text renderer 在 cell 边界统一清理 C0／DEL 与 ANSI 控制序列，或者用明确的可见转义形式表示它们；不要只清理 id，因为 vendor、family、policy status、base URL 和 endpoint 都进入同一个终端。JSON 模式应继续保留原始语义字符串。

### F4 — `--json` 的“verbatim”契约不成立

**位置：** `src/app/cli.py:390`、`src/app/debug/models.py:268-277`、`src/app/ghc_client/models.py:41`、`src/app/model_provider/github_copilot.py:73-78,109`。

**严重度：** minor。

**可复现输入：** 一个有额外字段、Unicode 与嵌套值的 `OrderedDict`，并拿 compact、Unicode escape 形式的 wire 文本作字节对照。完整命令见“命令实跑记录”。

**实际输出：**

```text
SEMANTIC_EQUAL: True
BYTE_VERBATIM_POSSIBLE: False
```

输出被变成带两空格缩进的 JSON，`"é"` 被改成字面 `"é"`，并新增 provider 名这一层。更早的 `response.json()` 已经丢掉原始空白、escape 拼写、数字词法与重复 object key，因此 `render_json` 无法把 wire payload “exactly as it arrived”还原出来。

**裁决：** 对普通、无重复 key 的 JSON object，当前路径没有字段投影：`render_json` 的 parse-back 结果等于 `{provider_name: raw}`，额外字段与嵌套值均保留。成立的是“解码后的 catalog 语义值被完整重新编码，并按 provider 分组”，不是“上游字节原样返回”。证据足以推翻严格 verbatim 声称，但没有观察到普通 JSON 字段丢失。

**建议：** 如果需求只是避免 ModelRow 投影，请把 CLI help、docstring 与属性说明改成准确措辞，例如“Print the complete decoded upstream payload, keyed by provider name”。如果确实需要 wire-verbatim，就必须在 `fetch_models` 保留 response bytes；但 provider-keyed 多 provider 输出与单一 verbatim JSON 文档天然冲突，需要先明确二者谁是契约，不应在本修复中自行扩大范围。

### F5 — 极长 id 把整张表撑到超宽

**位置：** `src/app/debug/models.py:215-235`。

**严重度：** minor。

**可复现输入：** `id="long-" + "x" * 160`。

**实际输出：** `_table` 把 ID 列宽设为 165，header 与所有其他 model 行均被填充到该宽度。反例输出中的 header 已超过常见 80／120 列，正常短 id 的 status 也被推到很远的位置。

```text
ID                                                                                                                                                                     STATUS        VENDOR      FAMILY  CONTEXT  OUT  ENDPOINTS
long-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  ok            -           -             -    -  /responses
```

此外，`len()` 计算的是 code point 而非 terminal cell；CJK 和 emoji 会让视觉列宽进一步失真。

**建议：** 不要在所有输出场景硬裁原始 id。对 TTY text 模式按探测到的终端列数设置可见 cell 上限并加 ellipsis，非 TTY 可保留完整值，或者在超宽时改用逐模型纵向布局。可以复用 `rich.cells.cell_len`／`set_cell_size`；完整值仍由 JSON 模式承载。

### F6 — 现有测试存在具体 false-green 表面

**位置：** `tests/unit/test_debug_models.py:127-139,206-217,258-288`。

**严重度：** minor。

**实际测试结果：** `40 passed in 2.28s`，其中 `tests/unit/test_debug_models.py` 17 项全绿，`tests/unit/test_model_provider.py` 23 项全绿。这个绿只证明当前断言集合通过，不证明错误呈现、控制字符、wire-verbatim 或资源路径都被覆盖。

以下断言即使对应实现写错也会继续绿：

1. `test_the_recorded_catalog_capture_reads_end_to_end` 的 `len(rows) == len(raw["data"])`、`all(row.id and row.status ...)`、`any(row.status == "ok" ...)` 只验证行数与非空。一份实现若对真实 capture 的 vendor、family、limits、endpoint 全部读错，并把所有非 disabled 状态粗暴写成 `ok`，该测试仍可通过；只有 hand-built fixture 的少数状态断言能拦住它碰巧覆盖到的形状。
2. `test_cli_prints_the_report` 只找 `"ID"` 与 `"routable"`。CLI 即使绕过 `render_text` 并硬编码这两个词也会通过；它不验证 provider header、summary 与至少一行 cell 的相互一致。
3. `test_cli_reports_a_failed_provider_and_exits_nonzero` 在 `result.output` 中找 error，但 `CliRunner` 的合并输出不能证明 docstring 所说的“named on stderr”。实现若把 failure 打到 stdout，现有断言仍绿。
4. `test_json_is_the_payload_untouched_keyed_by_provider` 与 `test_cli_emits_json_on_request` 都先 `json.loads` 再比较。因此任意空白重排、Unicode escape 改写和 key lexical 表示变化都会继续绿；当前实现正是反例。它们能证明语义字段未被 projection 丢弃，不能证明“untouched”或“verbatim”。
5. 没有测试从 CLI 入口喂缺失／无效 config，所以 F1 完全不可见；没有测试 newline／ANSI、超长 id、字符串 endpoints 或非字符串 policy，所以 F2、F3、F5 也不可见。

**建议：** 不追求覆盖率，也无需新增门禁。只围绕本轮真实失败面补鉴别性断言：无效 config 不含 `Traceback` 且包含字段路径；畸形 entry 有显式 diagnostic；text 输出每个 model 只占一条物理行且不含原始 ESC；JSON 测试改名为 semantic preservation，除非产品确实决定保留 wire bytes；failure 测试使用可分别检查 stdout／stderr 的 runner 配置或 API。

## 非发现与已确认行为

### 真实上游与凭据错误

当前环境的真实上游调用成功，读取 42 个 model，命令退出 0。该观测足以确认 happy path 在本环境可运行；不证明其他账户相同。显式移除三种 token 环境变量并指向不存在的 token 文件后，输出如下，清楚且可操作。

```text
error: ghc: No GitHub token provider produced a usable token — run `ghc-api-proxy auth`

[exit=1]
```

不存在的 `--provider nope` 在网络调用前退出 2，并列出 `configured: ghc`。这条错误虽然由 Rich 在 80 列折成两行，仍可读。

### `collect_catalogs` 的 client 生命周期

**结论：普通异常路径未发现泄漏。** `src/app/debug/models.py:154-180` 在 `build_http_client` 返回后立即进入 `try/finally`，所以 `build_chain` 抛错、provider refresh 抛错、provider 类型不支持以及成功返回都会执行 `await http_client.aclose()`。两个独立探针分别得到：

```text
aclose called
raised: composition failed
closed: True
```

以及：

```text
aclose called
catalogs: ()
failures: (CatalogFailure(name='ghc', reason='upstream broke'),)
closed: True
```

`Exception` 不会捕获 `asyncio.CancelledError` 这类取消，但外层 `finally` 仍负责 close；若 `aclose()` 自己抛错，该错误会传播而不是被吞掉。多个 provider 当前顺序 refresh，共用一个 `AsyncClient`，未见并发写共享状态或重复关闭问题。

### 显式 provider 与缺失 default

双 provider 且 `default_model_provider: ""` 时，即使传 `--provider ghc`，命令也拒绝运行并输出：

```text
error: config sets no `default_model_provider` and more than one provider is configured

[exit=1]
```

这是 `build_chain` 坚持使用与服务启动相同 composition 的直接结果。现有 help 只承诺筛选 configured provider，没有足够规范依据判断 debug 命令应否绕过无效默认配置，因此本轮记录该行为但不列缺陷。

## 命令实跑记录

说明：首次按用户给出的原命令直接执行时，Typer／Rich 输出携带 ANSI；为让 Markdown 可读，CLI 摘录以 `NO_COLOR=1 TERM=dumb` 的等价复跑为准。真实 `--json` 成功输出没有 ANSI，完整 72,085-byte 输出在本报告末尾原样附录。所有 `[exit=N]` 均由命令结束后立即读取 `$?` 得到。

### Help

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run ghc-api-proxy debug models --help
```

```text
                                                                                 
 Usage: ghc-api-proxy debug models [OPTIONS]                                    
                                                                                 
 Show upstream model information.                                               
                                                                                 
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --config          FILE                                                       │
│ --provider        TEXT  Report only this configured provider.                │
│ --json                  Print the upstream payload verbatim, keyed by        │
│                         provider name.                                       │
│ --help                  Show this message and exit.                          │
╰──────────────────────────────────────────────────────────────────────────────╯

[exit=0]
```

### 不存在的 provider

```bash
cd /home/xp/src/ghc-api-proxy-py && NO_COLOR=1 TERM=dumb uv run ghc-api-proxy debug models --config /tmp/ghc-review-debug-models-valid.yaml --provider nope
```

```text
Usage: ghc-api-proxy debug models [OPTIONS]
Try 'ghc-api-proxy debug models --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Invalid value: no model provider named 'nope' is configured (configured:     │
│ ghc)                                                                         │
╰──────────────────────────────────────────────────────────────────────────────╯

[exit=2]
```

### 无效 config

```bash
cd /home/xp/src/ghc-api-proxy-py && NO_COLOR=1 TERM=dumb uv run ghc-api-proxy debug models --config /tmp/ghc-review-debug-models-bad.yaml
```

```text
╭───────────────────── Traceback (most recent call last) ──────────────────────╮
│ /home/xp/src/ghc-api-proxy-py/src/app/cli.py:394 in debug_models             │
│                                                                              │
│ ❱ 394 │   proxy_config = load_proxy_config(config_path=config)               │
│                                                                              │
│ /home/xp/src/ghc-api-proxy-py/src/app/config/loading.py:158 in               │
│ load_proxy_config                                                            │
│                                                                              │
│ ❱ 158 │   return ProxyConfig.model_validate(merged)                          │
╰──────────────────────────────────────────────────────────────────────────────╯
ValidationError: 2 validation errors for ProxyConfig
model_providers.ghc.type
  Input should be 'github_copilot' [type=literal_error, input_value='definitely_not_a_provider', input_type=str]
unknown_top_level
  Extra inputs are not permitted [type=extra_forbidden, input_value=True, input_type=bool]

[exit=1]
```

### 缺失 config

```bash
cd /home/xp/src/ghc-api-proxy-py && NO_COLOR=1 TERM=dumb uv run ghc-api-proxy debug models --config /tmp/ghc-review-debug-models-missing.yaml
```

```text
╭───────────────────── Traceback (most recent call last) ──────────────────────╮
│ /home/xp/src/ghc-api-proxy-py/src/app/cli.py:394 in debug_models             │
│                                                                              │
│ ❱ 394 │   proxy_config = load_proxy_config(config_path=config)               │
│                                                                              │
│ /home/xp/src/ghc-api-proxy-py/src/app/config/loading.py:149 in               │
│ load_proxy_config                                                            │
│                                                                              │
│ ❱ 149 │   resolved_path = resolve_config_path(config_path)                   │
│                                                                              │
│ /home/xp/src/ghc-api-proxy-py/src/app/config/loading.py:92 in                │
│ resolve_config_path                                                          │
│                                                                              │
│ ❱  92 │   │   │   raise FileNotFoundError(...)                              │
╰──────────────────────────────────────────────────────────────────────────────╯
FileNotFoundError: configuration file not found: /tmp/ghc-review-debug-models-missing.yaml

[exit=1]
```

### 真实上游 text

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run ghc-api-proxy debug models --config /tmp/ghc-review-debug-models-valid.yaml
```

```text
ghc  https://api.githubcopilot.com
42 models, 24 routable, 18 no-endpoints

ID                                STATUS        VENDOR        FAMILY                  CONTEXT     OUT  ENDPOINTS
claude-haiku-4.5                  ok            Anthropic     claude-haiku-4.5         200000   64000  /chat/completions, /v1/messages
claude-opus-4.6                   ok            Anthropic     claude-opus-4.6         1000000   64000  /chat/completions, /v1/messages
claude-opus-4.7                   ok            Anthropic     claude-opus-4.7         1000000   64000  /chat/completions, /v1/messages
claude-opus-4.8                   ok            Anthropic     claude-opus-4.8         1000000   64000  /chat/completions, /v1/messages
claude-opus-5                     ok            Anthropic     claude-opus-5           1000000   64000  /chat/completions, /v1/messages
claude-sonnet-4.6                 ok            Anthropic     claude-sonnet-4.6       1000000   64000  /chat/completions, /v1/messages
claude-sonnet-5                   ok            Anthropic     claude-sonnet-5         1000000   64000  /chat/completions, /v1/messages
gemini-3.1-pro-preview            ok            Google        gemini-3.1-pro-preview  1000000   64000  /chat/completions
gemini-3.5-flash                  ok            Google        gemini-3.5-flash        1000000   64000  /chat/completions
gemini-3.6-flash                  ok            Google        gemini-3.6-flash        1000000   64000  /chat/completions
gemini-3.7-flash                  ok            Google        gemini-3.7-flash        1000000   64000  /chat/completions
gpt-3.5-turbo                     no-endpoints  Azure OpenAI  gpt-3.5-turbo             16384    4096  -
gpt-3.5-turbo-0613                no-endpoints  Azure OpenAI  gpt-3.5-turbo             16384    4096  -
gpt-4                             no-endpoints  Azure OpenAI  gpt-4                     32768    4096  -
gpt-4-0125-preview                no-endpoints  Azure OpenAI  gpt-4-turbo              128000    4096  -
gpt-4-0613                        no-endpoints  Azure OpenAI  gpt-4                     32768    4096  -
gpt-4-o-preview                   no-endpoints  Azure OpenAI  gpt-4o                   128000    4096  -
gpt-4.1                           no-endpoints  Azure OpenAI  gpt-4.1                  128000   16384  -
gpt-4.1-2025-04-14                no-endpoints  Azure OpenAI  gpt-4.1                  128000   16384  -
gpt-41-copilot                    no-endpoints  Azure OpenAI  gpt-4.1                       -       -  -
gpt-4o                            no-endpoints  Azure OpenAI  gpt-4o                   128000    4096  -
gpt-4o-2024-05-13                 no-endpoints  Azure OpenAI  gpt-4o                   128000    4096  -
gpt-4o-2024-08-06                 no-endpoints  Azure OpenAI  gpt-4o                   128000   16384  -
gpt-4o-2024-11-20                 no-endpoints  Azure OpenAI  gpt-4o                   128000   16384  -
gpt-4o-mini                       no-endpoints  Azure OpenAI  gpt-4o-mini              128000    4096  -
gpt-4o-mini-2024-07-18            no-endpoints  Azure OpenAI  gpt-4o-mini              128000    4096  -
gpt-5-mini                        ok            Azure OpenAI  gpt-5-mini               264000   64000  /chat/completions, /responses, ws:/responses*
gpt-5.3-codex                     ok            OpenAI        gpt-5.3-codex            400000  128000  /responses, ws:/responses*
gpt-5.4                           ok            OpenAI        gpt-5.4                 1050000  128000  /chat/completions, /responses, ws:/responses*
gpt-5.4-mini                      ok            OpenAI        gpt-5.4-mini             400000  128000  /responses, ws:/responses*
gpt-5.5                           ok            OpenAI        gpt-5.5                 1050000  128000  /responses, ws:/responses*
gpt-5.6-luna                      ok            OpenAI        gpt-5.6-luna            1050000  128000  /responses, ws:/responses*
gpt-5.6-sol                       ok            OpenAI        gpt-5.6-sol             1050000  128000  /responses, ws:/responses*
gpt-5.6-terra                     ok            OpenAI        gpt-5.6-terra           1050000  128000  /responses, ws:/responses*
grok-4.5                          ok            xAI           grok-4.5                 500000  128000  /responses
grok-4.6                          ok            xAI           grok-4.6                 500000  128000  /responses
mai-code-1-flash-picker           ok            Microsoft     oswe-vscode-modelD       256000  128000  /responses
mai-code-1.1-flash                ok            Microsoft     oswe-vscode-modelD       256000  128000  /responses
text-embedding-3-small            no-endpoints  Azure OpenAI  text-embedding-3-small        -       -  -
text-embedding-3-small-inference  no-endpoints  Azure OpenAI  text-embedding-3-small        -       -  -
text-embedding-ada-002            no-endpoints  Azure OpenAI  text-embedding-ada-002        -       -  -
trajectory-compaction             ok            Fireworks     trajectory-compaction    262144   16384  /chat/completions

* advertised by upstream, no driver in this proxy

[exit=0]
```

### 畸形载荷与 text renderer

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run python -c 'from app.debug.models import ProviderCatalog, build_rows, render_text; raw={"meta":{"kept":True},"data":[42,None,[],{}, {"id":"string-endpoints","supported_endpoints":"/responses"}, {"id":"nonstr-policy","supported_endpoints":["/responses"],"policy":{"state":{"unexpected":True}}}, {"id":"long-"+"x"*160,"supported_endpoints":["/responses"]}, {"id":"ansi-\x1b[31mRED\x1b[0m\nFAKE","vendor":"V\nINJECTED","supported_endpoints":["/responses"]}]}; rows=build_rows(raw); print("ROWS:"); [print(repr(row)) for row in rows]; print("RENDER_REPR:"); print(repr(render_text([ProviderCatalog("ghc","https://example.invalid",raw,rows)]))); print("RENDER:"); print(render_text([ProviderCatalog("ghc","https://example.invalid",raw,rows)]))'
```

```text
ROWS:
ModelRow(id='ansi-\x1b[31mRED\x1b[0m\nFAKE', status='ok', vendor='V\nINJECTED', family='', endpoints=('/responses',), undriven=frozenset(), context_window=None, max_output_tokens=None)
ModelRow(id='long-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', status='ok', vendor='', family='', endpoints=('/responses',), undriven=frozenset(), context_window=None, max_output_tokens=None)
ModelRow(id='nonstr-policy', status='ok', vendor='', family='', endpoints=('/responses',), undriven=frozenset(), context_window=None, max_output_tokens=None)
ModelRow(id='string-endpoints', status='no-endpoints', vendor='', family='', endpoints=(), undriven=frozenset(), context_window=None, max_output_tokens=None)
RENDER_REPR:
'ghc  https://example.invalid\n4 models, 3 routable, 1 no-endpoints\n\nID                                                                                                                                                                     STATUS        VENDOR      FAMILY  CONTEXT  OUT  ENDPOINTS\nansi-\x1b[31mRED\x1b[0m\nFAKE                                                                                                                                                 ok            V\nINJECTED  -             -    -  /responses\nlong-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  ok            -           -             -    -  /responses\nnonstr-policy                                                                                                                                                          ok            -           -             -    -  /responses\nstring-endpoints                                                                                                                                                       no-endpoints  -           -             -    -  -'
RENDER:
ghc  https://example.invalid
4 models, 3 routable, 1 no-endpoints

ID                                                                                                                                                                     STATUS        VENDOR      FAMILY  CONTEXT  OUT  ENDPOINTS
ansi-<ESC>[31mRED<ESC>[0m
FAKE                                                                                                                                                 ok            V
INJECTED  -             -    -  /responses
long-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  ok            -           -             -    -  /responses
nonstr-policy                                                                                                                                                          ok            -           -             -    -  /responses
string-endpoints                                                                                                                                                       no-endpoints  -           -             -    -  -

[exit=0]
```

注：上面实际 render 的两个 `<ESC>` 是报告中的可见记法；`RENDER_REPR` 一行保留了 Python 对原始字节的无歧义表示。

### JSON 语义与 verbatim 对照

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run python -c 'import json; from collections import OrderedDict; from app.debug.models import ProviderCatalog, render_json; raw=OrderedDict([("z", "é"), ("data", []), ("extra", {"nested": [1, True, None]})]); rendered=render_json([ProviderCatalog("ghc", "u", raw, ())]); print("INPUT_OBJECT_REPR:"); print(repr(raw)); print("OUTPUT_REPR:"); print(repr(rendered)); print("OUTPUT:"); print(rendered); print("SEMANTIC_EQUAL:", json.loads(rendered)=={"ghc":raw}); print("BYTE_VERBATIM_POSSIBLE:", rendered == "{\"z\":\"\\u00e9\",\"data\":[],\"extra\":{\"nested\":[1,true,null]}}")'
```

```text
INPUT_OBJECT_REPR:
OrderedDict({'z': 'é', 'data': [], 'extra': {'nested': [1, True, None]}})
OUTPUT_REPR:
'{\n  "ghc": {\n    "z": "é",\n    "data": [],\n    "extra": {\n      "nested": [\n        1,\n        true,\n        null\n      ]\n    }\n  }\n}'
OUTPUT:
{
  "ghc": {
    "z": "é",
    "data": [],
    "extra": {
      "nested": [
        1,
        true,
        null
      ]
    }
  }
}
SEMANTIC_EQUAL: True
BYTE_VERBATIM_POSSIBLE: False

[exit=0]
```

### 无 token

```bash
cd /home/xp/src/ghc-api-proxy-py && env -u COPILOT_API_GITHUB_TOKEN -u GH_TOKEN -u GITHUB_TOKEN uv run ghc-api-proxy debug models --config /tmp/ghc-review-debug-models-no-token.yaml
```

```text
error: ghc: No GitHub token provider produced a usable token — run `ghc-api-proxy auth`

[exit=1]
```

### 资源释放探针

```bash
uv run python -c 'import asyncio; import app.debug.models as m; from app.config.schema import ProxyConfig
class Client:
    def __init__(self): self.closed=False
    async def aclose(self): self.closed=True; print("aclose called")
async def main():
    c=Client(); original_client=m.build_http_client; original_chain=m.build_chain
    m.build_http_client=lambda config: c
    m.build_chain=lambda config, *, http_client: (_ for _ in ()).throw(RuntimeError("composition failed"))
    try:
        try: await m.collect_catalogs(ProxyConfig())
        except RuntimeError as e: print("raised:", e)
        print("closed:", c.closed)
    finally:
        m.build_http_client=original_client; m.build_chain=original_chain
asyncio.run(main())'
status=$?
printf '\n[exit=%s]\n' "$status"
exit 0
```

```text
aclose called
raised: composition failed
closed: True

[exit=0]
```

```bash
uv run python -c 'import asyncio; import app.debug.models as m; from app.config.schema import ProxyConfig
class Client:
    def __init__(self): self.closed=False
    async def aclose(self): self.closed=True; print("aclose called")
class Names:
    names=frozenset({"ghc"})
    def get(self, name): return Provider()
class Provider:
    async def refresh_catalog(self): raise OSError("upstream broke")
class Chain: providers=Names()
async def main():
    c=Client(); original_client=m.build_http_client; original_chain=m.build_chain; original_type=m.GithubCopilotProvider
    m.build_http_client=lambda config: c
    m.build_chain=lambda config, *, http_client: Chain()
    m.GithubCopilotProvider=Provider
    try:
        catalogs, failures=await m.collect_catalogs(ProxyConfig(model_providers={"ghc":{"type":"github_copilot"}}, default_model_provider="ghc"))
        print("catalogs:", catalogs); print("failures:", failures); print("closed:", c.closed)
    finally:
        m.build_http_client=original_client; m.build_chain=original_chain; m.GithubCopilotProvider=original_type
asyncio.run(main())'
status=$?
printf '\n[exit=%s]\n' "$status"
exit 0
```

```text
aclose called
catalogs: ()
failures: (CatalogFailure(name='ghc', reason='upstream broke'),)
closed: True

[exit=0]
```

### Targeted tests

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run pytest tests/unit/test_debug_models.py tests/unit/test_model_provider.py
```

```text
============================= test session starts ==============================
platform linux -- Python 3.14.2, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/xp/src/ghc-api-proxy-py
configfile: pyproject.toml
plugins: cov-7.1.0, anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 40 items

tests/unit/test_debug_models.py .................                        [ 42%]
tests/unit/test_model_provider.py .......................                [100%]

============================== 40 passed in 2.28s ==============================

[exit=0]
```

## 附录：真实 `--json` 命令及完整输出

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run ghc-api-proxy debug models --config /tmp/ghc-review-debug-models-valid.yaml --json
```

```json
{
  "ghc": {
    "data": [
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-4.6",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-4.6",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 4.6",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 4.6 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.6](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-4.6",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-4.7",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-4.7",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 4.7",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 4.7 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.7](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-4.7",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-4.8",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-4.8",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 4.8",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 4.8 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 4.8](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-4.8",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-opus-5",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-opus-5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Claude Opus 5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Opus 5 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Opus 5](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-opus-5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-sonnet-4.6",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 5,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-sonnet-4.6",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Claude Sonnet 4.6",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Sonnet 4.6 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Sonnet 4.6](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions",
          "/v1/messages"
        ],
        "vendor": "Anthropic",
        "version": "claude-sonnet-4.6",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "claude-sonnet-5",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 5,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "adaptive_thinking": true,
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-sonnet-5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Claude Sonnet 5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude model from Anthropic. [Learn more about how GitHub Copilot serves Claude](https://gh.io/copilot-claude-opus)."
        },
        "preview": false,
        "supported_endpoints": [
          "/v1/messages",
          "/chat/completions"
        ],
        "vendor": "Anthropic",
        "version": "claude-sonnet-5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "edu",
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.1-pro-preview",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 32000,
            "min_thinking_budget": 256,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.1-pro-preview",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "Gemini 3.1 Pro",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3 Pro model from Google. [Learn more about how GitHub Copilot serves Gemini 3 Pro](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": true,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.1-pro-preview",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.5-flash",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 24000,
            "min_thinking_budget": 256,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "minimal",
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.5-flash",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "Gemini 3.5 Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3.5 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.5 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.5-flash",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.6-flash",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 32000,
            "min_thinking_budget": 256,
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "minimal",
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.6-flash",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Gemini 3.6 Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3.6 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.6 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.6-flash",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gemini-3.7-flash",
          "limits": {
            "max_context_window_tokens": 1000000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 936000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 10,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gemini-3.7-flash",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Gemini 3.7 Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Gemini 3.7 Flash model from Google. [Learn more about how GitHub Copilot serves Gemini 3.7 Flash](https://docs.github.com/en/copilot/reference/ai-models/model-hosting#google-models)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Google",
        "version": "gemini-3.7-flash",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "edu",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.3-codex",
          "limits": {
            "max_context_window_tokens": 400000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 272000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.3-codex",
        "is_chat_default": true,
        "is_chat_fallback": true,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.3-Codex",
        "object": "model",
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.3-codex",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "edu",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.4-mini",
          "limits": {
            "max_context_window_tokens": 400000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 272000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.4-mini",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "GPT-5.4 mini",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.4 mini model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.4 mini](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.4-mini",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "individual_trial",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.4",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.4",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.4",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.4 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.4](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "/chat/completions",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.4",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.5",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.5 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.5](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "free",
            "edu",
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.6-luna",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.6-luna",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "GPT-5.6 Luna",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.6 Luna model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Luna](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.6-luna",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.6-sol",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.6-sol",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "powerful",
        "model_picker_enabled": true,
        "name": "GPT-5.6 Sol",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.6 Sol model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Sol](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.6-sol",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "gpt-5.6-terra",
          "limits": {
            "max_context_window_tokens": 1050000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 922000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "none",
              "low",
              "medium",
              "high",
              "xhigh",
              "max"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5.6-terra",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "GPT-5.6 Terra",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5.6 Terra model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5.6 Terra](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/responses",
          "ws:/responses"
        ],
        "vendor": "OpenAI",
        "version": "gpt-5.6-terra",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "grok-4.5",
          "limits": {
            "max_context_window_tokens": 500000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 372000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "grok-4.5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Grok 4.5",
        "object": "model",
        "preview": false,
        "supported_endpoints": [
          "/responses"
        ],
        "vendor": "xAI",
        "version": "grok-4.5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "business",
            "enterprise",
            "max"
          ]
        },
        "capabilities": {
          "family": "grok-4.6",
          "limits": {
            "max_context_window_tokens": 500000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 372000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high",
              "xhigh"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "grok-4.6",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": true,
        "name": "Grok 4.6",
        "object": "model",
        "preview": false,
        "supported_endpoints": [
          "/responses"
        ],
        "vendor": "xAI",
        "version": "grok-4.6",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "promo": {
            "discount_percent": 10,
            "ends_at": "2026-08-25T00:00:00Z",
            "id": "mai_flash_1_1_2026_08",
            "message": "Enjoy 10% off MAI-Code-1.1-Flash."
          },
          "restricted_to": [
            "free",
            "edu",
            "individual_trial",
            "pro",
            "pro_plus",
            "max",
            "business",
            "enterprise"
          ]
        },
        "capabilities": {
          "family": "oswe-vscode-modelD",
          "limits": {
            "max_context_window_tokens": 256000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 128000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "mai-code-1.1-flash",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "MAI-Code-1.1-Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": ""
        },
        "preview": false,
        "supported_endpoints": [
          "/responses"
        ],
        "vendor": "Microsoft",
        "version": "mai-code-1.1-flash",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "free",
            "edu",
            "pro",
            "pro_plus",
            "max",
            "business",
            "enterprise"
          ]
        },
        "capabilities": {
          "family": "oswe-vscode-modelD",
          "limits": {
            "max_context_window_tokens": 256000,
            "max_output_tokens": 128000,
            "max_prompt_tokens": 128000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "mai-code-1-flash-picker",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "MAI-Code-1-Flash",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": ""
        },
        "preview": false,
        "supported_endpoints": [
          "/responses"
        ],
        "vendor": "Microsoft",
        "version": "mai-code-1-flash-picker",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "free",
            "edu",
            "pro",
            "pro_plus",
            "individual_trial",
            "max"
          ]
        },
        "capabilities": {
          "family": "trajectory-compaction",
          "limits": {
            "max_context_window_tokens": 262144,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 245760
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "trajectory-compaction",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Trajectory Compaction",
        "object": "model",
        "preview": true,
        "supported_endpoints": [
          "/chat/completions"
        ],
        "vendor": "Fireworks",
        "version": "trajectory-compaction",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-5-mini",
          "limits": {
            "max_context_window_tokens": 264000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 128000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "reasoning_effort": [
              "low",
              "medium",
              "high"
            ],
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-5-mini",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "GPT-5 mini",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-5 mini model from OpenAI. [Learn more about how GitHub Copilot serves GPT-5 mini](https://gh.io/copilot-openai)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions",
          "/responses",
          "ws:/responses"
        ],
        "vendor": "Azure OpenAI",
        "version": "gpt-5-mini",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o-mini",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-mini-2024-07-18",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o mini",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-mini-2024-07-18",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-2024-11-20",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-11-20",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-2024-08-06",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-08-06",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "text-embedding-3-small",
          "limits": {
            "max_inputs": 512
          },
          "object": "model_capabilities",
          "supports": {
            "dimensions": true
          },
          "tokenizer": "cl100k_base",
          "type": "embeddings"
        },
        "id": "text-embedding-3-small",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Embedding V3 small",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "text-embedding-3-small",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "text-embedding-3-small",
          "object": "model_capabilities",
          "supports": {
            "dimensions": true
          },
          "tokenizer": "cl100k_base",
          "type": "embeddings"
        },
        "id": "text-embedding-3-small-inference",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Embedding V3 small (Inference)",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "text-embedding-3-small",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "claude-haiku-4.5",
          "limits": {
            "max_context_window_tokens": 200000,
            "max_non_streaming_output_tokens": 16000,
            "max_output_tokens": 64000,
            "max_prompt_tokens": 136000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 5,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "max_thinking_budget": 32000,
            "min_thinking_budget": 1024,
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "claude-haiku-4.5",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "lightweight",
        "model_picker_enabled": true,
        "name": "Claude Haiku 4.5",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest Claude Haiku 4.5 model from Anthropic. [Learn more about how GitHub Copilot serves Claude Haiku 4.5](https://gh.io/copilot-anthropic)."
        },
        "preview": false,
        "supported_endpoints": [
          "/chat/completions",
          "/v1/messages"
        ],
        "vendor": "Anthropic",
        "version": "claude-haiku-4.5",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4.1",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 128000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4.1-2025-04-14",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4.1",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-4.1 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-4.1](https://docs.github.com/en/copilot/using-github-copilot/ai-models/choosing-the-right-ai-model-for-your-task#gpt-41)."
        },
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4.1-2025-04-14",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4.1",
          "object": "model_capabilities",
          "supports": {
            "streaming": true
          },
          "tokenizer": "o200k_base",
          "type": "completion"
        },
        "id": "gpt-41-copilot",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": false,
        "name": "GPT-4.1 Copilot",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-41-copilot",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-3.5-turbo",
          "limits": {
            "max_context_window_tokens": 16384,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-3.5-turbo-0613",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 3.5 Turbo",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-3.5-turbo-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4",
          "limits": {
            "max_context_window_tokens": 32768,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 32768
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-4",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 4",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4",
          "limits": {
            "max_context_window_tokens": 32768,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 32768
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-4-0613",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 4",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4-turbo",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-4-0125-preview",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 4 Turbo",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4-0125-preview",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-2024-05-13",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-05-13",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4-o-preview",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-05-13",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4.1",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 16384,
            "max_prompt_tokens": 128000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "application/pdf"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "structured_outputs": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4.1",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_category": "versatile",
        "model_picker_enabled": false,
        "name": "GPT-4.1",
        "object": "model",
        "policy": {
          "state": "enabled",
          "terms": "Enable access to the latest GPT-4.1 model from OpenAI. [Learn more about how GitHub Copilot serves GPT-4.1](https://docs.github.com/en/copilot/using-github-copilot/ai-models/choosing-the-right-ai-model-for-your-task#gpt-41)."
        },
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4.1-2025-04-14",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1,
          "restricted_to": [
            "pro",
            "pro_plus",
            "max",
            "business",
            "enterprise",
            "individual_trial",
            "edu"
          ]
        },
        "capabilities": {
          "family": "gpt-3.5-turbo",
          "limits": {
            "max_context_window_tokens": 16384,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "cl100k_base",
          "type": "chat"
        },
        "id": "gpt-3.5-turbo",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT 3.5 Turbo",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-3.5-turbo-0613",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o-mini",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 12288
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o-mini",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o mini",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-mini-2024-07-18",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "gpt-4o",
          "limits": {
            "max_context_window_tokens": 128000,
            "max_output_tokens": 4096,
            "max_prompt_tokens": 64000,
            "vision": {
              "max_prompt_image_size": 3145728,
              "max_prompt_images": 1,
              "supported_media_types": [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif"
              ]
            }
          },
          "object": "model_capabilities",
          "supports": {
            "parallel_tool_calls": true,
            "streaming": true,
            "tool_calls": true,
            "vision": true
          },
          "tokenizer": "o200k_base",
          "type": "chat"
        },
        "id": "gpt-4o",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "GPT-4o",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "gpt-4o-2024-11-20",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      },
      {
        "billing": {
          "is_premium": true,
          "multiplier": 1
        },
        "capabilities": {
          "family": "text-embedding-ada-002",
          "limits": {
            "max_inputs": 512
          },
          "object": "model_capabilities",
          "supports": {},
          "tokenizer": "cl100k_base",
          "type": "embeddings"
        },
        "id": "text-embedding-ada-002",
        "is_chat_default": false,
        "is_chat_fallback": false,
        "model_picker_enabled": false,
        "name": "Embedding V2 Ada",
        "object": "model",
        "preview": false,
        "vendor": "Azure OpenAI",
        "version": "text-embedding-3-small",
        "warning_message": "Your billing plan has changed to usage-based billing and model multipliers no longer apply. Please update your client to the latest version to see the new billing information."
      }
    ],
    "object": "list"
  }
}

[exit=0]
```

## 附录：`NO_COLOR=1 TERM=dumb` 复跑的完整原始 CLI 输出

以下块未经删节或改写；它们补全正文为聚焦差异而节选的 traceback。

### Help

```text
                                                                                
 Usage: ghc-api-proxy debug models [OPTIONS]                                    
                                                                                
 Show upstream model information.                                               
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --config          FILE                                                       │
│ --provider        TEXT  Report only this configured provider.                │
│ --json                  Print the upstream payload verbatim, keyed by        │
│                         provider name.                                       │
│ --help                  Show this message and exit.                          │
╰──────────────────────────────────────────────────────────────────────────────╯


[exit=0]
```

### 不存在的 provider

```text
Usage: ghc-api-proxy debug models [OPTIONS]
Try 'ghc-api-proxy debug models --help' for help.
╭─ Error ──────────────────────────────────────────────────────────────────────╮
│ Invalid value: no model provider named 'nope' is configured (configured:     │
│ ghc)                                                                         │
╰──────────────────────────────────────────────────────────────────────────────╯

[exit=2]
```

### 无效 config

```text
╭───────────────────── Traceback (most recent call last) ──────────────────────╮
│ /home/xp/src/ghc-api-proxy-py/src/app/cli.py:394 in debug_models             │
│                                                                              │
│   391 │   ] = False,                                                         │
│   392 ) -> None:                                                             │
│   393 │   """Show upstream model information."""                             │
│ ❱ 394 │   proxy_config = load_proxy_config(config_path=config)               │
│   395 │   if provider is not None and provider not in                        │
│       proxy_config.model_providers:                                          │
│   396 │   │   configured = ", ".join(sorted(proxy_config.model_providers))   │
│       or "none"                                                              │
│   397 │   │   raise typer.BadParameter(                                      │
│                                                                              │
│ /home/xp/src/ghc-api-proxy-py/src/app/config/loading.py:158 in               │
│ load_proxy_config                                                            │
│                                                                              │
│   155 │   merged: dict[str, Any] = {}                                        │
│   156 │   for layer in layers:                                               │
│   157 │   │   merged = _deep_merge(merged, layer)                            │
│ ❱ 158 │   return ProxyConfig.model_validate(merged)                          │
│   159                                                                        │
│                                                                              │
│ /home/xp/src/ghc-api-proxy-py/.venv/lib/python3.14/site-packages/pydantic/ma │
│ in.py:732 in model_validate                                                  │
│                                                                              │
│    729 │   │   │   │   code='validate-by-alias-and-name-false',              │
│    730 │   │   │   )                                                         │
│    731 │   │                                                                 │
│ ❱  732 │   │   return cls.__pydantic_validator__.validate_python(            │
│    733 │   │   │   obj,                                                      │
│    734 │   │   │   strict=strict,                                            │
│    735 │   │   │   extra=extra,                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
ValidationError: 2 validation errors for ProxyConfig
model_providers.ghc.type
  Input should be 'github_copilot' [type=literal_error, 
input_value='definitely_not_a_provider', input_type=str]
    For further information visit 
https://errors.pydantic.dev/2.13/v/literal_error
unknown_top_level
  Extra inputs are not permitted [type=extra_forbidden, input_value=True, 
input_type=bool]
    For further information visit 
https://errors.pydantic.dev/2.13/v/extra_forbidden

[exit=1]
```

### 缺失 config

```text
╭───────────────────── Traceback (most recent call last) ──────────────────────╮
│ /home/xp/src/ghc-api-proxy-py/src/app/cli.py:394 in debug_models             │
│                                                                              │
│   391 │   ] = False,                                                         │
│   392 ) -> None:                                                             │
│   393 │   """Show upstream model information."""                             │
│ ❱ 394 │   proxy_config = load_proxy_config(config_path=config)               │
│   395 │   if provider is not None and provider not in                        │
│       proxy_config.model_providers:                                          │
│   396 │   │   configured = ", ".join(sorted(proxy_config.model_providers))   │
│       or "none"                                                              │
│   397 │   │   raise typer.BadParameter(                                      │
│                                                                              │
│ /home/xp/src/ghc-api-proxy-py/src/app/config/loading.py:149 in               │
│ load_proxy_config                                                            │
│                                                                              │
│   146 │   layers: list[Mapping[str, Any]] = [                                │
│   147 │   │   bundled if bundled is not None else bundled_config_values(),   │
│   148 │   ]                                                                  │
│ ❱ 149 │   resolved_path = resolve_config_path(config_path)                   │
│   150 │   if resolved_path is not None:                                      │
│   151 │   │   layers.append(_read_yaml(resolved_path))                       │
│   152 │   layers.append(environment_values(environ))                         │
│                                                                              │
│ /home/xp/src/ghc-api-proxy-py/src/app/config/loading.py:92 in                │
│ resolve_config_path                                                          │
│                                                                              │
│    89 │   """                                                                │
│    90 │   if explicit_path is not None:                                      │
│    91 │   │   if not explicit_path.is_file():                                │
│ ❱  92 │   │   │   raise FileNotFoundError(f"configuration file not found:    │
│       {explicit_path}")                                                      │
│    93 │   │   return explicit_path                                           │
│    94 │                                                                      │
│    95 │   env_path = os.environ.get(CONFIG_PATH_VARIABLE)                    │
╰──────────────────────────────────────────────────────────────────────────────╯
FileNotFoundError: configuration file not found: 
/tmp/ghc-review-debug-models-missing.yaml

[exit=1]
```

### 真实上游 text

```text
ghc  https://api.githubcopilot.com
42 models, 24 routable, 18 no-endpoints

ID                                STATUS        VENDOR        FAMILY                  CONTEXT     OUT  ENDPOINTS
claude-haiku-4.5                  ok            Anthropic     claude-haiku-4.5         200000   64000  /chat/completions, /v1/messages
claude-opus-4.6                   ok            Anthropic     claude-opus-4.6         1000000   64000  /chat/completions, /v1/messages
claude-opus-4.7                   ok            Anthropic     claude-opus-4.7         1000000   64000  /chat/completions, /v1/messages
claude-opus-4.8                   ok            Anthropic     claude-opus-4.8         1000000   64000  /chat/completions, /v1/messages
claude-opus-5                     ok            Anthropic     claude-opus-5           1000000   64000  /chat/completions, /v1/messages
claude-sonnet-4.6                 ok            Anthropic     claude-sonnet-4.6       1000000   64000  /chat/completions, /v1/messages
claude-sonnet-5                   ok            Anthropic     claude-sonnet-5         1000000   64000  /chat/completions, /v1/messages
gemini-3.1-pro-preview            ok            Google        gemini-3.1-pro-preview  1000000   64000  /chat/completions
gemini-3.5-flash                  ok            Google        gemini-3.5-flash        1000000   64000  /chat/completions
gemini-3.6-flash                  ok            Google        gemini-3.6-flash        1000000   64000  /chat/completions
gemini-3.7-flash                  ok            Google        gemini-3.7-flash        1000000   64000  /chat/completions
gpt-3.5-turbo                     no-endpoints  Azure OpenAI  gpt-3.5-turbo             16384    4096  -
gpt-3.5-turbo-0613                no-endpoints  Azure OpenAI  gpt-3.5-turbo             16384    4096  -
gpt-4                             no-endpoints  Azure OpenAI  gpt-4                     32768    4096  -
gpt-4-0125-preview                no-endpoints  Azure OpenAI  gpt-4-turbo              128000    4096  -
gpt-4-0613                        no-endpoints  Azure OpenAI  gpt-4                     32768    4096  -
gpt-4-o-preview                   no-endpoints  Azure OpenAI  gpt-4o                   128000    4096  -
gpt-4.1                           no-endpoints  Azure OpenAI  gpt-4.1                  128000   16384  -
gpt-4.1-2025-04-14                no-endpoints  Azure OpenAI  gpt-4.1                  128000   16384  -
gpt-41-copilot                    no-endpoints  Azure OpenAI  gpt-4.1                       -       -  -
gpt-4o                            no-endpoints  Azure OpenAI  gpt-4o                   128000    4096  -
gpt-4o-2024-05-13                 no-endpoints  Azure OpenAI  gpt-4o                   128000    4096  -
gpt-4o-2024-08-06                 no-endpoints  Azure OpenAI  gpt-4o                   128000   16384  -
gpt-4o-2024-11-20                 no-endpoints  Azure OpenAI  gpt-4o                   128000   16384  -
gpt-4o-mini                       no-endpoints  Azure OpenAI  gpt-4o-mini              128000    4096  -
gpt-4o-mini-2024-07-18            no-endpoints  Azure OpenAI  gpt-4o-mini              128000    4096  -
gpt-5-mini                        ok            Azure OpenAI  gpt-5-mini               264000   64000  /chat/completions, /responses, ws:/responses*
gpt-5.3-codex                     ok            OpenAI        gpt-5.3-codex            400000  128000  /responses, ws:/responses*
gpt-5.4                           ok            OpenAI        gpt-5.4                 1050000  128000  /chat/completions, /responses, ws:/responses*
gpt-5.4-mini                      ok            OpenAI        gpt-5.4-mini             400000  128000  /responses, ws:/responses*
gpt-5.5                           ok            OpenAI        gpt-5.5                 1050000  128000  /responses, ws:/responses*
gpt-5.6-luna                      ok            OpenAI        gpt-5.6-luna            1050000  128000  /responses, ws:/responses*
gpt-5.6-sol                       ok            OpenAI        gpt-5.6-sol             1050000  128000  /responses, ws:/responses*
gpt-5.6-terra                     ok            OpenAI        gpt-5.6-terra           1050000  128000  /responses, ws:/responses*
grok-4.5                          ok            xAI           grok-4.5                 500000  128000  /responses
grok-4.6                          ok            xAI           grok-4.6                 500000  128000  /responses
mai-code-1-flash-picker           ok            Microsoft     oswe-vscode-modelD       256000  128000  /responses
mai-code-1.1-flash                ok            Microsoft     oswe-vscode-modelD       256000  128000  /responses
text-embedding-3-small            no-endpoints  Azure OpenAI  text-embedding-3-small        -       -  -
text-embedding-3-small-inference  no-endpoints  Azure OpenAI  text-embedding-3-small        -       -  -
text-embedding-ada-002            no-endpoints  Azure OpenAI  text-embedding-ada-002        -       -  -
trajectory-compaction             ok            Fireworks     trajectory-compaction    262144   16384  /chat/completions

* advertised by upstream, no driver in this proxy

[exit=0]
```

### 无 token

```text
error: ghc: No GitHub token provider produced a usable token — run `ghc-api-proxy auth`

[exit=1]
```

### 显式 provider 但无 default

```text
error: config sets no `default_model_provider` and more than one provider is configured

[exit=1]
```

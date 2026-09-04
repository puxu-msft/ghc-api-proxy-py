# 评审：`ghc-api-proxy debug models` 实现

- 日期：2026-08-20（第二轮，覆盖第一轮报告；第一轮结论保留在 §6）
- 仓库 HEAD：`5e2f1d5`
- **评审对象（精确到字节，因为文件在评审期间被并行修改过两次）**：

| 文件 | md5 |
|---|---|
| `src/app/debug/models.py` | `7ef4c8c6cfdbb8e4d2c2d110400925f2` |
| `src/app/cli.py` | `4631ff58c756473d899d558a6e399995` |
| `src/app/model_provider/github_copilot.py` | `77e7188744147949b87ab5c8d224c5d1` |
| `src/app/auth/providers.py` | `44b2b01928e91e1033c598a13a18fcdb` |
| `tests/unit/test_debug_models.py` | `a3dc39b10aa70cffed58dc5e768f6414` |
| `tests/unit/test_model_provider.py` | `2e2d5dbc779980a2c96df1eeb4b74d24` |

- 结论：**needs-fix**（0 blocker / 3 major / 5 minor / 3 nit）

**评审期间文件在变**：我第一轮读的是 `models.py` 05:50 版（293 行，md5 `8a9c327f`），中途它被改成 08:16 版（367 行，md5 `7ef4c8c6`），采纳了另一位评审的三条 major。本报告以**上表哈希**为准。若这些哈希已再次变化，本报告的 §1、§2 需重新核对；§3（我对另一份评审的独立判断）与 §6（第一轮结论）不受影响。

本轮动手跑了六个一次性探针（`/tmp/dbgprobe/`，仓库外，未改动任何源码）。凡标「探针证实」的都是实测输出，不是读代码推断。

---

## 零、当前工作区是红的（事实陈述，非缺陷指控）

改动正在进行中，此刻两项门都不过：

```
uv run pytest tests/unit/test_debug_models.py tests/unit/test_model_provider.py
→ 1 failed, 47 passed
    FAILED test_columns_stay_aligned_when_a_cell_is_double_width

uv run ruff check src/app/debug src/app/cli.py tests/unit/test_debug_models.py
→ 2 errors
    UP037 src/app/debug/models.py:302  quoted type annotation
    F821  tests/unit/test_debug_models.py:259  Undefined name `cell_len`
```

两者同源：`test_columns_stay_aligned_when_a_cell_is_double_width` 已经被改用 `cell_len` 度量（`tests/unit/test_debug_models.py:260`），但**没有加 `from rich.cells import cell_len`**。补一行 import 即可，红是半成品状态而非设计问题。`UP037` 是 `_summary(catalog: "ProviderCatalog")` 的引号（`src/app/debug/models.py:302`），`ProviderCatalog` 定义在第 50 行、就在它上面，引号纯属多余。

**但这里有一个真正危险的陷阱，见 §1.1——请务必先读那条再动这个测试。**

---

## 一、针对新增修复的发现（本轮重点）

### 1.1 别把这个失败的测试「修」到实现里去【major，优先级最高】

**位置**：`tests/unit/test_debug_models.py:252-262`、`src/app/debug/models.py:272-278`

失败信息长这样：

```
AssertionError: ['ID       STATUS  VENDOR     FAMILY   CONTEXT    OUT  ENDPOINTS',
                 'plain    ok      Anthropic  plain     200000  64000  /v1/messages',
                 '模型-一  ok      Anthropic  模型-一   200000  64000  /v1/messages']
assert 2 == 1  where {6, 9} = set([9, 6])
```

**实现是对的，测试量错了单位。探针证实**：

```
row='plain    ok '   str.index('ok')= 9   cell offset of 'ok'= 9
row='模型-一  ok  '  str.index('ok')= 6   cell offset of 'ok'= 9
cell_len('模型-一') = 7    len('模型-一') = 4
```

两列都落在**终端第 9 格**，`_pad` 完全正确。`{6, 9}` 这个差异只存在于 `str.index` 的码点计数里。

**为什么这是 major**：一个看着 `assert 2 == 1` 的人，最省事的「修法」是把 `_pad`/`cell_len` 退回 `str.ljust`——那样测试立刻变绿，而刚修好的双宽对齐会被原样打回去，并且从此有一条测试**锁死**这个错误行为。这是「绿灯反而证明坏了」的典型形态。

**建议改法**：只补 `from rich.cells import cell_len`（第 260 行的断言本身已经是对的）。**不要动 `src/app/debug/models.py` 的 `_pad`。**

顺带说：`_pad` + `cell_len` 这个修法本身我实测通过（探针 E，`中文厂商` 与 `Acme` 两行 VENDOR 之后的列完全对齐），并且复用了 footer 已在用的 `rich.cells`——`src/app/observability/footer.py:173` 那段注释讲的是同一件事。这是本轮改动里质量最高的一处。

### 1.2 控制字符防线漏了 summary 那一行【major】

**位置**：`src/app/debug/models.py:302-318`（`_summary`），对照 `:239-246`（`_printable`）、`:249-265`（`_cells`）

`_printable` 只被 `_cells`（`:251`）和 `render_text` 的首行（`:326`）调用。**`_summary` 不经过它**，而 `_summary` 拼的是 `row.status`（`:314` 的 `f"{count} {status}"`），`row.status` 在 policy 分支下**就是上游原样的字符串**（`:107-108`）。

`_wrong_shape` 拦不住它：一个带换行的 `policy.state` 是**合法的 `str`**，类型没错，所以不算 `malformed`。

**探针证实**，输入 `policy: {"state": "gated\nINJECTED SUMMARY LINE"}`：

```
'ghc  https://x'
'1 model, 0 routable, 1 gated'
'INJECTED SUMMARY LINE'            ← 上游文本自成一行，混在报告自己的结构里
''
'ID  STATUS                      VENDOR  FAMILY  CONTEXT  OUT  ENDPOINTS'
'm   gatedINJECTED SUMMARY LINE  V       f             -    -  /v1/messages'
```

表格那行**被正确剥离了**（合成一行），summary 那行**没有**。`_printable` 的 docstring（`:242`）说「a newline ... draws a second physical line that the reader counts as another model」——这正是它声称已经堵上、而实际只堵了一半的那个洞。

现有测试为什么没抓到：`test_one_model_occupies_exactly_one_line_whatever_upstream_put_in_it`（`:232-249`）把控制字符放在 `id` 和 `vendor`（两者都走 `_cells`，被剥离），从没放进 `policy.state`；而且它断言的 `body = text.splitlines()[3:]`（`:243`）**从第 3 行起切**，把 summary 那一行整个跳过了。`assert "\x1b" not in text`（`:245`）覆盖全文，所以 ANSI 会被抓到，`\n` 不会。

**建议改法**：`_summary` 的 return 前统一过一道，`return _printable(summary)`；并给 `:232` 那个测试补一个 `policy={"state": "gated\nINJECTED"}` 的条目，断言范围改成 `text.splitlines()` 全量。

### 1.3 `_wrong_shape` 只覆盖了它自己规则的三分之一【minor】

**位置**：`src/app/debug/models.py:116-128`

docstring 立的规则是「a key that is present and holds something the reader would otherwise silently coerce into a confident wrong answer」。但它只检查 `supported_endpoints`、`policy`、`policy.state` 三个字段，而 `build_rows` 实际读八个。漏掉的 `vendor`、`capabilities`、`capabilities.family`、`limits` 走的是同一套静默强转。

**探针证实**，输入 `{"id":"m","vendor":123,"capabilities":"nope","supported_endpoints":["/v1/messages"]}`：

```
'1 model, 1 routable'
'ID  STATUS  VENDOR  FAMILY  CONTEXT  OUT  ENDPOINTS'
'm   ok      -       -             -    -  /v1/messages'
```

上游明明说了 `vendor: 123`，报告用 `-` 声称「上游没说 vendor」——正是 `malformed` 这个状态被引入来消灭的那类断言。

**建议改法**：`_wrong_shape` 补上 `vendor` / `capabilities` / `family` / `limits` 的类型检查；或者把规则收窄成 docstring 里说得到的范围（「只检查决定路由的字段」），两者取一，别让规则比实现宽。我倾向前者，因为 `_MISSING` 这个 `-` 在报告里读作事实。

### 1.4 上游 `policy.state` 仍与本地状态字面量共用命名空间【major，第一轮 §1.4 升级】

**位置**：`src/app/debug/models.py:107-108`

第一轮我定 minor，理由是「真实抓取里 19 条 policy 全是 `enabled`，没观测到碰撞」。本轮我实际渲染了碰撞场景，**结果比我预估的严重，故升级为 major**：

**探针证实 B**，`policy.state == "ok"` 且模型唯一端点是 `ws:/responses`（本代理明确不驱动）：

```
'1 model, 1 routable'
'ID  STATUS  VENDOR  FAMILY  CONTEXT  OUT  ENDPOINTS'
'm   ok      -       -             -    -  ws:/responses*'
''
'* advertised by upstream, no driver in this proxy'
```

同一个输出块里，第 2 行说「1 routable」，最后一行说「这个端点本代理没有驱动」。**报告自己和自己矛盾**，而 `ROUTABLE` 的注释（`:23-24`）承诺的是「唯一表示请求能被路由的状态」。

**探针证实 C**，`policy.state == "disabled"` 与操作者在 `disabled_models` 里写的那个：

```
'2 models, 0 routable, 2 disabled'
'operator-says  disabled  ...'
'upstream-says  disabled  ...'
```

两者外观完全一致。操作者会去翻自己的配置，只找到一条，另一条无从下手——恰好违反 `status_of` docstring 第一段自己立的「按谁能动手排序」。

**建议改法**：给上游来的 state 加前缀，一行：

```python
if policy_state and policy_state != _ENABLED_POLICY:
    return f"policy:{policy_state}"
```

`policy:ok` / `policy:disabled` / `policy:unconfigured` 既不可能与本地状态撞名，也保住了 `_summary` docstring（`:305`）夸的那个优点——上游明天发明的新状态照样按名字报出来。这一条同时把 1.2 的爆炸半径缩小（前缀让注入文本不再能伪装成报告自己的结构），但**不能替代 1.2 的修复**。

### 1.5 `malformed` 置顶与 docstring 自述的排序原则冲突【nit】

**位置**：`src/app/debug/models.py:95-113`

代码把 `malformed` 放在最前是**对的**——读不出来的字段不该让下面任何一级做出自信断言，`:101` 的理由站得住。

但 docstring 第一段仍写着「Ordered by who can act on it」，而 `malformed` 恰恰是**没人能动手**的那一个（既不是操作者的配置，也不是我们的驱动）。两段话现在描述的是两个不同的排序原则。纯文档一致性，代码无需改；把第一段改成「Ordered by who can act on it, after the one case where nothing below can be trusted」之类即可。

### 1.6 `ProviderCatalog.unreadable` 有默认值 `0`【nit】

**位置**：`src/app/debug/models.py:61`

这个字段的存在意义就是「不让漏掉的条目静默消失」，却给了一个静默表示「没有漏」的默认值。今天唯一的生产构造点 `collect_catalogs:220` 显式传了值，所以不构成缺陷；但默认值让「忘记传」这件事无法被类型系统或运行期发现。测试里构造省事是它的收益，我认为收益略大于成本，**倾向保留**，记在这里是为了下轮不必重新讨论。

---

## 二、我对另一份评审（`docs/tmp/260820-review-debug-models-gpt.md`）三条 major 的独立判断

我先自己判，再对照，不采信其推理。**三条我都同意，且当前代码都已修复**：

### 2.1 「config 错误吐 traceback」——同意，已修复，且修复的分寸拿捏得好

`debug_models` 原先直接 `load_proxy_config(config_path=config)`，配置文件不存在 / YAML 语法错 / schema 不过，都会以 Typer 的 pretty traceback 呈现。对一个**接受 `--config` 的命令**来说，这些是最普通不过的操作者输入，traceback 指向的是我们的模块而不是他敲错的那个键。同意是 major。

当前 `_read_config`（`src/app/cli.py:377-389`）捕 `FileNotFoundError, ValidationError, YAMLError`，原样透传 pydantic 消息（它本来就带字段路径），只丢掉栈帧。

**我特别赞同它的作用域声明**：docstring 明写「Scoped to `debug models` on purpose: `start` still raises through, and changing what an already-shipped path does on a bad config was not part of implementing this command.」这正是我独立核对时的判断——`serve`/`start` 共享同一个缺陷，那是**既有的全局模式**，顺手改掉它就是把一个未经裁决的行为变更夹带进这个切片。克制是对的。

**遗留提示**：这意味着现在同一个仓库里两条路径对坏配置的反应不一致。这不是缺陷，但值得记进 `docs/tmp/`，免得将来有人当成 bug「统一」掉。

### 2.2 「畸形 entry 被静默丢弃」——同意，而且**我第一轮判错了，在此更正**

第一轮我在 §2.2 写「跳过的是连 id 都没有的条目，在报告里也确实无处可放，这个取舍我认同」。**这个判断是错的，我放过了它。**

错在哪：我只想了「被丢的那条能不能显示」，没想「**总数还准不准**」。这条命令的全部职责就是说清上游发了什么；上游发 8 条、报告说「4 models」，语气与真的只有 4 条时**完全无法区分**。丢的不是那条无名条目，是**计数的可信度**。而且旧测试 `assert set(rows) == {"odd", "fine"}` 把这个静默丢弃**固化成了契约**。

当前修复（`unreadable` 计数 + `malformed` 状态）方向正确，两档分得也对：有 id 但字段类型错的 → 出一行标 `malformed`（还能被点名）；连 id 都读不出的 → 没法出行，计数后在 summary 里报出来（`:316-317`）。`test_an_absent_optional_field_is_not_treated_as_malformed`（`:153`）作为反向对照也在，防止把「合法省略 `supported_endpoints`」的 18 条误判成畸形——这条负样本是整组新测试里最有价值的。

修复仍不完整，见 §1.3。

### 2.3 「上游字符串里的 ANSI/换行破坏表格」——同意结论，但**不同意通常配套的那套论证**

先说我实测的事实：`refs/available_models.json` 全量扫描，**控制字符 0 处、非 ASCII 字符 0 处、会被丢弃的条目 0 条**（探针 3）。所以「上游正在发控制字符」是**没有观测证据**的。

如果论证建立在「上游可能是恶意的 / 可能被注入」，我**不接受**——按用户的 `no-imagined-security-theater` 与 `hazard-before-mitigation`，这里的行为体是 GitHub 自家的 `/models` 端点，威胁模型里没有攻击者，凭空假设一个就是安全戏剧。

但结论仍然成立，理由换一条、且不需要任何威胁模型：**`build_rows` 自己的 docstring（`:138`）承诺「it must not be the thing that fails when that catalog grows a shape we have not seen」**。带换行的 vendor 字段就是一个「没见过的形状」。据代码自述的契约来判，这是缺陷；据「有人要攻击我们」来判，这是臆想。**同一个修复，理由必须换掉**——否则下次同样的臆想会被用来论证一个不该做的加固。

另外，双宽字符那半**根本不需要任何假设**：`len()` 数码点、终端按格子排版，这是纯粹的算错，`模型-一` 是 4 个码点 7 个格子（探针 6）。这半我给的权重是「足以据此动手」。

修复本身有效（探针 E），但漏了 summary 行，见 §1.2。

---

## 三、第一轮发现的当前状态

| 第一轮编号 | 内容 | 当前状态 |
|---|---|---|
| §4.3 | `collect_catalogs` 的失败隔离与 `finally` 关 client 无自动化测试 | **仍未修复**，见下 |
| §5.1 | CLI 形态未裁决就固化了对外行为 | **仍未处理**，见下 |
| §1.4 | `policy.state` 与状态字面量撞名 | **仍未修复，且已升级为 major**（§1.4） |
| §1.5 | `except Exception` 的 docstring 过强 | 仍在（`:192` 原文未动） |
| §1.7 | 丢弃 `refresh_catalog()` 返回值 | 仍在（`:206`） |
| §1.8 | 零 provider 时错报「more than one provider」 | 仍在（`cli.py` 的 detail 分支未动） |
| §1.9 | 只给「从来没 token」加了修复提示，401 过期没有 | 仍在（`:228-232` 未动） |
| §1.10 | `HTTPStatusError` 两行消息第二行无前缀 | 仍在 |
| §4.1 | `assert all(row.id and row.status ...)` 恒真 | **已修复**：现为 `:172-178`，改成了 `unreadable == 0` + `not [... == "malformed"]`，两条都有鉴别力 |
| §3.3 | `raw_catalog` 标 `Mapping` 实为可变 `dict` | 仍在（nit，倾向保留） |
| §4.6 | 重复 advertise 同一端点显示两次 | 仍在（nit） |
| §5.2 | `bundled-config.yaml` 的无关改动 | **已消解**：已被并行会话提交，不再在工作区里，无需再防 |

### 3.1 `collect_catalogs` 仍无自动化测试【major，维持第一轮定级】

**位置**：`src/app/debug/models.py:184-225`

五个 CLI 测试仍然整体 monkeypatch 掉 `app.cli.collect_catalogs`，`CatalogFailure` 仍然只在测试里手工构造，**从未由被测代码产出过一个**。本轮 `collect_catalogs` 还被改动过（`:210-221` 拆出 `rows, unreadable`），改完依旧没有任何测试看着它。

我自己用探针 2 补跑过，**实现是正确的**：

```
PROBE2 catalogs: [('good', 'https://good.example', ['m1','m2'])]
PROBE2 failures: [('bad', 'connect refused')]
PROBE2 client closed: [True]
PROBE2 propagated: boom in build_chain | closed: [True]
```

所以这不是「有 bug 没发现」，而是「一个正确的实现没有任何东西守着它」——而它这一轮已经被改过一次了。按 `.claude/rules/00-development-workflow.md:20`（测试覆盖本切片真实改动的失败机制），这是明确缺口，不是追覆盖率。

**建议改法**：加**一条**测试即可（探针 2 已验证形状可行、无需网络）。monkeypatch `app.debug.models.build_chain` 与 `build_http_client`，注入一成功一抛的假 provider，一次断言三件事：健康的没被拖下水、死掉的被点名、`finally` 关了 client。`build_chain` 本身支持 `providers=` 注入（`src/app/server/composition.py:183`），假 provider 可直接喂进真 `Chain`。

### 3.2 CLI 形态仍未裁决【major，需用户裁决，非代码缺陷】

`docs/.human-controlled/MAIN.md:11-13` 的 `app.cli` 一节仍是 `TODO`，全目录无一处提到 `debug`。三个 flag、默认渲染器、退出码语义、以及本轮新增的 summary 措辞（`(2 unreadable entries skipped)`）与 `malformed` 这个状态词，全部是未裁决的对外契约，而且本轮**又长了一截**。

且与 `docs/2604-rewrite/plan/IMPLEMENTATION_PLAN.md:428-429`（「预期: 打印模型列表 JSON」）的分歧依旧。我仍认为**表格作默认更好**（人读为主，`--json` 给脚本），但该分歧应显式记录并由用户裁决，而不是让两份文档互相矛盾地放着。

**建议处置**（交回主会话，非我动手）：把三个 flag、默认渲染器、退出码、以及 `malformed`/`unreadable` 两个新词写成候选文本投进 `.dev/human-controlled-docs-candidates/`，请用户裁决；同时更新或注销 `IMPLEMENTATION_PLAN.md:428` 那条陈旧预期。

---

## 四、发现清单（按严重度）

| # | 位置 | 问题 | 严重度 |
|---|---|---|---|
| 1.1 | `tests/unit/test_debug_models.py:252-262` | 失败的对齐测试**测错了单位**，实现是对的；照 `assert 2 == 1` 直觉去改实现会打回刚修好的双宽对齐并把错误行为锁死。只需补 `cell_len` 的 import | **major** |
| 1.2 | `src/app/debug/models.py:302-318` | 控制字符剥离漏了 summary 行；`policy.state` 里的 `\n` 会让上游文本自成一行混进报告结构。现有注入测试放的是 id/vendor，且切片从第 3 行起，看不到 | **major** |
| 1.4 | `src/app/debug/models.py:107-108` | 上游 `policy.state` 原样进入 status 命名空间：`"ok"` 使报告自相矛盾（说 routable，同块又说无驱动），`"disabled"` 与操作者禁用无法区分 | **major** |
| 3.1 | `src/app/debug/models.py:184-225` | `collect_catalogs` 的失败隔离与 `finally` 关 client 无任何自动化测试；本轮它又被改过 | **major** |
| 3.2 | `src/app/cli.py:392-425`；`docs/.human-controlled/MAIN.md:11-13` | CLI 对外契约未裁决即固化，本轮又扩大；与 `IMPLEMENTATION_PLAN.md:428` 矛盾 | **major**（需用户裁决） |
| 1.3 | `src/app/debug/models.py:116-128` | `_wrong_shape` 只查 3 个字段，`build_rows` 读 8 个；`vendor:123` 被渲染成 `-`（「上游没说」） | minor |
| §1.5(一轮) | `src/app/debug/models.py:192` | docstring 断言「捕到的都不是本命令的 bug」，代码保证不了 | minor |
| §1.7(一轮) | `src/app/debug/models.py:206` | 丢弃 `refresh_catalog()` 返回值；304 今天不可达，破坏时会把「我没问」报成「上游没有模型」 | minor |
| §1.8(一轮) | `src/app/cli.py` detail 分支 | 零 provider 时错报「more than one provider is configured」 | minor |
| §1.9(一轮) | `src/app/debug/models.py:228-232` | 只覆盖「从来没有 token」，更常见的「token 过期被 401 拒」无提示 | minor |
| 0 | `models.py:302`、`tests/...:259` | 当前 ruff 2 error（多余引号 + 缺 import），pytest 1 failed | nit（半成品状态） |
| 1.5 | `src/app/debug/models.py:95-113` | `malformed` 置顶与 docstring 自述的「按谁能动手排序」冲突 | nit |
| 1.6 / §3.3 / §4.6(一轮) | 见上表 | 默认值 `0`、`Mapping` 实为 `dict`、重复端点显示两次 | nit |

---

## 五、明确检查过且无发现

- `_pad` / `cell_len` 的双宽对齐实现（探针 E 实测正确，勿动）
- `_printable` 复用 `app.observability.footer.CONTROL_CHARS` 的分层：`footer` 是纯模块（只依赖 `re`/`dataclass`/`rich.cells`，无 I/O 无 TUI），复用共享正则而非各写一份是对的
- `--json` **不**走 `_printable`，且有专门测试守着（`:285-289`）——这个例外是对的，要看上游原样发了什么
- `render_json` docstring 本轮改成「decoded payload, not the upstream bytes」，是一处诚实性修正：响应早已被 JSON 解析，空白/转义拼写/重复键确实已经没了，原措辞过强
- `build_rows` 其余防御式读取（非 dict 条目、`bool` 冒充 int、缺 `capabilities`/`limits`）
- `DRIVEN_ENDPOINTS` 与 `src/app/server/inbound.py::ROUTES` 一一对应；`ws:/responses` 的排除与人写文档 `MAIN.md:29` 一致
- `except Exception` 的**范围**（只包 `refresh_catalog` 一句、不捕 `BaseException`、不吞 Ctrl-C）——探针证实
- `http_client.aclose()` 的 try/finally（正常返回与 `build_chain` 抛异常两条路径都关闭）——探针证实
- `NoGitHubToken` 从 `GitHubTokenManager` 一路到 `describe_failure` 未被中间层重新包装——探针证实（关键：`tokens.py:136-139` 把 `get_token()` 写在 try 之外）
- `ghc-api-proxy auth` 是真实存在的命令（`cli.py:335-338`）
- 与 `src/app/upstream/models_api.py::ModelCatalog` 无重复实现（服务不同链路；新代码沿用其既有 `_raw` 模式）
- 未复用 `app.models.common.ModelInfo` 是正确的（无 `policy` 字段、属旧链路、严格校验与本命令目标冲突）
- 在 provider 上保留 `raw_catalog` 优于再发一次请求（一致性 + descriptors 已丢弃全部报告字段 + 63KB 成本可忽略）
- `NoGitHubToken` 这个新异常类值得保留（唯一能让 `describe_failure` 区分「无 token」与「上游拒了」的手段，替代方案是字符串匹配异常消息——那才会静默失效；纯加法，全库无 `except RuntimeError` 依赖其具体类型）
- `_read_config` 的作用域克制（不顺手改 `start`）
- `test_an_absent_optional_field_is_not_treated_as_malformed` 的负样本对照
- `isinstance(provider, GithubCopilotProvider)` 的否定分支虽不可达，但为 Pyright 窄化所必需，应保留
- 未发现 bare `except: pass`、`contextlib.suppress`、或异常转 `None` 后被忽略

---

## 六、第一轮报告的结论（供追溯）

第一轮针对 `models.py` md5 `8a9c327f` 版，给出 0 blocker / 2 major / 6 minor / 4 nit。两条 major 是 §4.3（`collect_catalogs` 无测试）与 §5.1（CLI 形态未裁决），**至今均未处理**，已并入 §3。

**第一轮有一处判断错误，已在 §2.2 更正**：我把「无 id 条目被静默丢弃」判为可接受，理由是「那条在报告里无处可放」。这个理由本身没错，但我漏掉了真正的损失是**总数的可信度**，而不是那一条的可见性。另一位评审在这点上是对的，我不同意的只是 §2.3 里通常配套的那套威胁模型论证。

---

## 七、评审方法与证据

- 静态：读完 `src/app/debug/models.py`（两个版本）、`src/app/debug/__init__.py`、`src/app/cli.py` 相关段、`src/app/model_provider/{github_copilot,types,registry,__init__}.py`、`src/app/server/{composition,inbound}.py`、`src/app/ghc_client/{tokens,models,client}.py`、`src/app/auth/providers.py`、`src/app/upstream/models_api.py`、`src/app/models/common.py`、`src/app/config/schema.py`、`src/app/observability/footer.py` 相关段、两个测试文件全文、`docs/.human-controlled/MAIN.md`。
- 动态：六个一次性探针，写在 `/tmp/dbgprobe/`（**仓库外**），`uv run python` 执行，无网络、无副作用、未修改任何源码：
  1. `probe.py` — `NoGitHubToken` 穿过 `CopilotTokenManager`/`GhcApiClient` 后仍被 `describe_failure` 识别。
  2. `probe2.py` — monkeypatch `build_chain`/`build_http_client` + `SpyClient`，验证失败隔离与 `finally` 关闭（含 `build_chain` 自身抛异常）。
  3. `probe3.py` — 全量扫描 `refs/available_models.json`：控制字符 0、非 ASCII 0、会被丢弃条目 0。
  4. `probe4.py` — 撞上文件被并行修改，暴露 `_summary` 签名已变（这是我发现文件在动的方式）。
  5. `probe5.py` — 五个场景实渲染：summary 控制字符泄漏、`policy.state=="ok"` 自相矛盾、`"disabled"` 无法区分、`_wrong_shape` 漏检、CJK 对齐。
  6. `probe6.py` — 用 `cell_len` 证明失败的对齐测试量错了单位（两列均在第 9 格）。
- 跑过 `uv run pytest tests/unit/test_debug_models.py tests/unit/test_model_provider.py`（1 failed, 47 passed）与 `uv run ruff check`（2 errors），结果如 §0。
- **未执行**任何写操作（本报告除外）、未修改源码、未提交、未接触工作区其他并行改动。

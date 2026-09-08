# 事实核查：`.dev/docs/server-layout/README.md`

**日期**：2026-08-22。**被核对象**：`.dev` 仓 `58663b5` 的 `docs/server-layout/README.md`。
**核查者立场**：独立评审，只读。除本报告外未写入任何文件，未执行任何搬迁、格式化或提交。
**核查范围**：**只核「说的是不是真的」**，不评设计优劣（第 7 节方案对比、第 9 节倾向本身不在本次范围内；仅当某个判断建立在错误事实上时才报）。

**结论：needs-fix。** 第 3 节的数字与判据**绝大多数为真且可复现**，八个模块的行数在 `1f29d0a` 时点**逐个精确命中**，`_dispatch` 418 行精确命中，可达性表格的**判据列**（`app.routes` 0／0／12、`app.core` 三行皆不可达）精确命中。但有两处**会影响行动分界线或结论**的问题：授权引文漏掉了一半豁免项（第 2 节），以及第 4 节 S4 的「违反边界 2」指控证据不足且未处理反证。另有一处第 6 节的绝对断言事实上不成立。

**严重度计数**：blocker=0，major=3，minor=4，nit=6。

---

## 环境与复现前提

所有命令在 `/home/xp/src/ghc-api-proxy-py` 下执行。主仓 HEAD 在核查时已推进到 `1459320`（README 基线 `1f29d0a` 之后 3 个提交），且工作树有同伴未提交改动：

```
$ git log --oneline -5
1459320 feat: let the flat spelling of the port and host reach the section that holds them
81c36d2 docs: drop a note about a typo the config author has since fixed
959e8d1 test: pin the case-insensitivity the header document now states outright
1f29d0a docs: give the last bare citations a path, and stop asserting a module that is not here
ea7a665 feat: refuse to erase a live process's record, and name the pidfile's directory rather than the file
```

README 第 11 节已声明「本文的数字是 `1f29d0a` 时点的快照」，因此凡涉及行数与结构的核查，我**都在 `1f29d0a` 上重跑**（用 `git show` / `git archive` 取出该提交的源码到 `/tmp`，不动主树）。当前工作树的漂移（`handler.py` 649、`pipeline_app.py` 1047、`cli.py` 446）**不算缺陷**，仅作为读者上下文记录。

---

## A. major 级发现

### A1（major）第 2 节漏引了授权豁免项的一半，第 2 节的行动分界线因此被放宽

README 第 34 行把 2026-08-19 的授权说明引成：

> 「实现方可全面推进 B，若将来发现与用户文档不一致，**再讨论与修复，而不是停下来等裁决**」——但**该授权不覆盖 `docs/.human-controlled/`**

原文（`.dev/docs/anthropic-responses-bridge/architecture.md:5`）：

```
$ rg -n '这条授权覆盖' .dev/docs/anthropic-responses-bridge/architecture.md
5:> 用户在裁决时附加了一条授权范围说明，逐条实施时以它为准：本轮属于「在用户授权下、依用户提议实现补全」，并非所有细节都是用户已逐项知悉的实现；因此实现方可全面推进 B，**若将来发现与用户文档不一致，再讨论与修复，而不是停下来等裁决**。这条授权覆盖实现细节，不覆盖 `spec.md` 的可观察行为合同，也不覆盖 `docs/.human-controlled/`。
```

引号内那句**逐字准确**。问题在括号外的收尾：原文有**两个**豁免项——`spec.md` 的可观察行为合同、`docs/.human-controlled/`——README 只保留了后者，并用「但……」的句式把它呈现为唯一的限制。

同一处放宽在第 41 行再次出现。README 写：

> **已获授权、可直接做**：`app/` 内部的模块合并与拆分、文件搬迁、职责归位。这正是 architecture.md 白纸黑字列为「可局部调整」的那一类。

而 `architecture.md:605` 那一节的开头带着前置条件：

```
$ sed -n '603,608p' .dev/docs/anthropic-responses-bridge/architecture.md   # 实际用 Read 工具读取
#### 选择 B 后可局部调整的边界
以下项目只要不破坏上述五项核心与 Spec 行为，可以在设计深化或实现评审中局部调整，不需要重新发起 `D-ARCH`：
- Record、class、module 与 `PolicyOutcome` variant 的具体名称、字段分组和序列化形状。
- Pure converter、normalizer、renderer 与 transport port 的具体函数签名，以及组件是否按文件或 package 合并／拆分。
```

「只要不破坏上述五项核心与 **Spec 行为**」这半句在 README 的两处引用里都不见了。

**为什么这是 major 而不是 nit**：README 第 26 行自陈「这一节决定了本文哪些部分可以直接做、哪些不行。**先读它再读方案**」。第 8 节的第 3、4 步（抽可观测性、拆 `handler.py`）是纯搬迁不假，但第 4 步要把 `handle` / `handle_bounded` / 交付选型跨包移动，这正是最容易碰到 `spec.md` 可观察行为合同的地方；而读者按第 2 节现在的写法，会得到「只要不碰 `docs/.human-controlled/` 就都在授权内」的结论。**这是一个被删掉的门，不是措辞问题。**

**建议**：第 34 行把「不覆盖 `spec.md` 的可观察行为合同」补回，第 41 行把「只要不破坏五项核心与 Spec 行为」的前置条件写进那一条。

（我**没有**核查 `spec.md` 本身写了什么，见「未核查范围」。）

### A2（major）第 4 节 S4「违反了边界 2」的指控证据不足，且未处理直接反证

README 第 120 行：

> 今天时限与交付编排由 HTTP 表面持有，**这是对一条已获用户接受的架构边界的违反**，不是风格问题。

**事实前件为真**：`_dispatch` 确实在 HTTP 表面固定 client deadline，并持有交付选型。

```
$ rg -n 'client_deadline_at|framer_for|assembler_for|delivery_buffer|await handle' /tmp/pa_1f29d0a.py
389:    # Fixed before the body is read ... `handle_bounded` starts its own clock later ...
393:    client_deadline_at = (
490:        handled = await handle_bounded(chain, context, _routed, deadline_at=client_deadline_at)
596:        framer = framer_for(
643:        assembler = assembler_for(handled, hand_over_stop_reasons=_hand_over_reasons)
663:                again = await handle(chain, context, _routed)
695:                delivery_buffer(chain),
```

**但「违反边界 2」这个法律结论站不住，有三条反证 README 没有处理：**

1. **边界 2 的禁止项不包含入站表面。** 原文（`architecture.md:596`）：

   > **Single driver 是唯一 lifecycle 与 action owner。** Approval、attempt、retry、transport exchange、cancel、delivery、finalize 与 request-local journal 冻结只有一个编排者；policy、converter、transport、observer 和 History writer 不建立第二套请求生命周期。

   被点名禁止「建立第二套请求生命周期」的是 policy、converter、transport、observer、History writer 五类。HTTP 路由处理器不在其中。正面要求是「只有一个编排者」——README 证明的是**这个唯一编排者放错了文件**，没有证明**存在第二个**。放错文件是边界 3（protocol leg／transport leg 正交）与包命名的问题，与边界 2 的语义不同。

2. **代码里有一条日期为 2026-08-22 的显式设计说明，主张的恰好相反**（`/tmp/pa_1f29d0a.py:656`，`_dispatch` 内）：

   > `handle` rather than `handle_bounded`: the client deadline is enforced over the body now, and a second `asyncio.timeout` around this would be a second clock for one lifetime — the exact defect the outer guard was added to fix.

   即：deadline 以**时刻（instant）**而非**时长**下传，正是**为了不产生第二个生命周期**。README 第 4 节没有引用、也没有反驳这段。

3. **`handle_bounded` 的 docstring 把「表面持有起点」写成设计规则**（`/tmp/h.py:361-366`）：

   > It bounds the whole client-visible operation rather than any one attempt, and is never reset by a retry — but **only a caller that admitted the request knows when the request began**. `deadline_at` is how that caller says so; the fallback starts the clock here, which is later than admission by however long the body took to read and the request took to be routed. Measured 2026-08-22: with the clock started here, a body read, a JSON parse and a queue wait were all outside it.

   而 504 这一侧的行为已由用户于 2026-08-22 裁决并写入 `docs/.human-controlled/client-side-block-delivery.md:19`。

**影响面**：这条指控是第 7 节表格「方案 3：边界 2 的违反被固化」一行的唯一依据，也是第 209 行「方案 3 我明确反对」的核心理由。指控降级后，方案 3 的反对理由要重写（我不评它该不该被反对——那是设计评审的事——但**理由不能建在这条上**）。

**建议改写方向**：把 S4 降为「唯一编排者的**位置**与边界 3 的分层不一致，且 418 行里混着六个变化理由」，并明确说明代码当前**只有一个 clock**、这是刻意设计。

### A3（major）第 6 节标题句「当前没有任何进程在服务」不成立

README 第 181 行：

> `api.md` 追认的端点里，以下**当前没有任何进程在服务**：

表格里的三列判据（`api.md` 已追认 ✓ / 新链 ✗ / 旧链有实现 ✓）**逐条为真**，我全部复核通过（见 C 组）。但「没有任何进程在服务」这句绝对断言是错的：现役的 `copilot-api-js`（项目 `CLAUDE.md` 明写它是仍在跑的 4141 Bun 服务，未获裁决前不得接管）服务着其中至少 Azure、Gemini、status。

```
$ cd /home/xp/src/copilot-api-js && rg -ln 'v1beta/models|/openai/deployments|api/status' src
src/routes/azure-openai/route.ts
src/routes/gemini/handler.ts
src/routes/status/route.ts
src/routes/stats/route.ts
src/routes/gemini/route.ts
src/routes/index.ts
src/routes/gemini/handler-v4.ts
src/routes/responses/ws.ts
src/routes/debug/dry-run-pipeline.ts
src/routes/openapi-compat.ts
```

（我**没有**探测 4141 端口，也没有对该服务做任何操作；依据是项目规则中它仍在生产，加上其路由文件。）

**为什么这不是措辞问题**：第 6 节被标为「产品事实」，且第 193 行说它「决定的是第 8 节第 5、6 步能不能做」，第 9.2 节把它作为用户裁决的输入。用户读到「没有任何进程在服务」，会倾向于认为这些端点在生产上已经是死的、因而 9.2(b)（删旧链、改 `api.md` 转为暂不支持）代价很低。而实际情况是：本项目的目标是替换 `copilot-api-js`，这些端点**在被替换的那一侧是活的**——同一个选项的代价完全不同。

**建议**：把这句限定为「本项目的两条链都不服务它们」，并把 `copilot-api-js` 仍在服务这一事实写进第 9.2 的裁决输入。

---

## B. minor 级发现

### B1（minor）第 3.3 表格的模块数三行各比它自己引的支撑报告和我的实测少 1

README：139 / 126 / 140。我的实测（正样本对照见下）：140 / 127 / 141。它引的 `reports/260822-server-layout-chain-map.md` 自己写的也是 140 / 141：

```
$ rg -n 'modules: 235|static=140|都是 140/235' .dev/docs/server-layout/reports/260822-server-layout-chain-map.md
120:static=140 runtime=140
159:`python3 /tmp/importgraph.py pkgs app.cli --with-typechecking` 与不带该开关的结果**都是 140/235** ...
431:modules: 235 cli: 140 factory: 141
```

差值是恒定的 1，几乎肯定是**是否把根包 `app` 自身计入**的口径差别。按 README 表头「加载的 `app.*` 模块数」的字面读法，排除裸 `app` 反而更准确。所以这不是算错，而是**与自己指名的权威在同一张表上给出不同的数**，且没有说明口径。

**我的复现（先做正样本对照）：**

```
$ cat /tmp/probe_reach.py    # 一次性解释器：import 目标后读 sys.modules
$ PYTHONPATH=src uv run --no-project python /tmp/probe_reach.py app.routes
{"target": "app.routes", "n_app_modules": 117, "n_routes": 9, "routes": [...9 项...], "n_core": 0, "core": []}
$ PYTHONPATH=src uv run --no-project python /tmp/probe_reach.py app.core
{"target": "app.core", "n_app_modules": 2, "n_routes": 0, "routes": [], "n_core": 1, "core": ["app.core"]}
```

正样本通过：探针在 `app.routes` 真被导入时看得见 9 个 `app.routes.*`，在 `app.core` 真被导入时看得见 `app.core`。因此后面的 0 是**有分辨力的 0**，不是探针失灵。

正式测量（同时验证 `app.__file__` 指向被测树，防止解析到别的 checkout）：

```
$ git archive 1f29d0a src | tar -x -C /tmp/rev1f29d0a
$ for t in app.cli app.server.pipeline_app app.server.app_factory; do
    PYTHONPATH=/tmp/rev1f29d0a/src uv run --no-project python /tmp/probe2.py "$t"; done
{"target": "app.cli",                 "app_file": "/tmp/rev1f29d0a/src/app/__init__.py", "n_app_modules": 140, "n_routes": 0,  "n_core": 0, "core": []}
{"target": "app.server.pipeline_app", "app_file": "/tmp/rev1f29d0a/src/app/__init__.py", "n_app_modules": 127, "n_routes": 0,  "n_core": 0, "core": []}
{"target": "app.server.app_factory",  "app_file": "/tmp/rev1f29d0a/src/app/__init__.py", "n_app_modules": 141, "n_routes": 12, "n_core": 0, "core": []}
```

工作树 HEAD 上同样是 140 / 127 / 141、0 / 0 / 12。

**判据列全部精确命中**：`app.routes` = 0 / 0 / **12**（`src/app/routes/` 恰有 `__init__.py` + 11 个模块 = 12），`app.core` 三行均不可达。**README 的推论（旧链整体不在生产路径上，唯一入口是 `app_factory` 这一条边）成立**，减 1 不影响任何结论。

### B2（minor）第 3.1 把一句 `request-pipeline.md` 里没有的话放进了引号

README 第 54 行 `inbound.py` 的判据列：

> 与 `request-pipeline.md` 的「基础输入格式解析」一致

该短语在整个 `docs/.human-controlled/` 里不存在，在整个仓库里也不存在：

```
$ rg -n '基础输入|输入格式解析' docs/.human-controlled/ ; echo "exit=$?"
exit=1
$ rg -n '基础输入格式' --glob '!**/__pycache__/**' . | head; echo "exit=$?"
exit=1
```

更要紧的是，`src/app/server/__init__.py`（`1f29d0a`）**明写这句话已经不在那份文档里了**：

> The document also **no longer spells out** the basic input format parsing done on the way; `inbound.py` states and owns that choice.

也就是说 README 第 3.1 引用的是一份**已被删除的旧措辞**，却按现行文本的口吻写成引文。实质判断（`inbound.py` 的位置正确）我认同且不受影响，但按 README 自己第 2 节的规矩，对 `docs/.human-controlled/` 的引用是行动分界线的依据，引文准确性在这里不是小事。

**建议**：改成「`request-pipeline.md` 只规定请求经 `app.server.routes` 进入后交给 `app.pipeline`；基础输入格式解析这件事由 `inbound.py` 自陈并拥有（见 `server/__init__.py`）」。

### B3（minor）第 6 节把 Tokenization 与「状态与配置」列成两行，但它们在同一个文件里

README 第 6 节表格把「状态与配置 `/api/status`、`/api/config`（已追认）」与「Tokenization（已裁决暂不支持）」分成两行。二者的实现在同一个模块：

```
$ rg -n 'tokenization/calibration|tokenization/limits' src/app/routes/management.py
61:@router.get("/api/tokenization/calibration")
79:@router.get("/api/tokenization/limits")
```

`src/app/routes/management.py` 同时承载已追认的 `/api/status`、`/api/config` 与已裁决暂不支持的两个 tokenization 端点。第 8 节第 6 步写的是「把仍被追认的端点接进新链，然后删 `app_factory.py` 与 `app/routes/`」——`management.py` 不能整体搬也不能整体删，得逐端点拆。这条不改变裁决，但它是执行第 6 步时会撞上的第一件事，值得写进第 6 节。

### B4（minor）第 2 节的时序注记：「多出两行」实际是「新增一行 + 给既有行加注释」

README 第 44 行：

> `module-org.md` 的工作树版本比 HEAD 多出 `pipeline/delivery` 两行（未提交，mtime 12:48）

实际 diff：

```
$ git diff -- docs/.human-controlled/module-org.md
-    pipeline
+    pipeline            # 模型请求的处理管线
+        delivery            # 客户端侧的块级交付机制
$ stat --format='%y %n' docs/.human-controlled/module-org.md
2026-08-22 12:48:17.612320552 +0000 docs/.human-controlled/module-org.md
```

净增一行（`delivery`），另一行是给既有的 `pipeline` 加注释。**mtime 12:48 精确命中**；**载重的那半句——用户当天确实编辑过这份文件并保留了 `server/routes`——成立**（工作树版本第 20–21 行仍是 `server` / `routes`）。仅措辞不精确。

---

## C. 复核通过的事实（可直接引用）

### C1 第 3.1 八个模块的行数在 `1f29d0a` 上逐个精确命中

```
$ for f in __init__ admission app_factory composition handler inbound ops_routes pipeline_app tls; do
    printf "%-14s %s\n" "$f" "$(git show 1f29d0a:src/app/server/$f.py | wc -l)"; done
__init__       13
admission      57      ← README 57 ✓
app_factory    177     ← README 177 ✓
composition    576     ← README 576 ✓
handler        645     ← README 645 ✓
inbound        89      ← README 89 ✓
ops_routes     76      ← README 76 ✓
pipeline_app   1037    ← README 1037 ✓
tls            136     ← README 136 ✓
```

### C2 `tls.py` 包内零消费者，三个调用方全在包外

```
$ git grep -n 'server\.tls' 1f29d0a -- '*.py'
1f29d0a:src/app/cli.py:24:from app.server.tls import resolve_tls_material
1f29d0a:src/app/lifecycle/entry.py:35:from app.server.tls import TlsMaterial, build_server_ssl_context
1f29d0a:src/app/lifecycle/listener.py:24:from app.server.tls import is_tls_handshake
（其余命中是配置键 `server.tls.mode`、`tls.py` 自身的 docstring，以及 4 个测试文件）
```

`src/app/server/` 内**无任何模块** import 它。README 的判据成立，且「三个调用方全在外：`lifecycle/entry.py`、`lifecycle/listener.py`、`cli.py`」逐字正确。

### C3 `composition.py` 被包外的 `cli.py` 与 `debug/models.py` 消费

```
$ git grep -n 'server\.composition' 1f29d0a -- 'src/*.py' 'src/**/*.py'
1f29d0a:src/app/cli.py:22:from app.server.composition import build_chain, build_http_client, resolve_provider_base_urls
1f29d0a:src/app/debug/models.py:21:from app.server.composition import build_chain, build_http_client, resolve_provider_base_urls
（包内另有 handler.py:62、ops_routes.py:19、pipeline_app.py:52 三处）
```

README 只声称「被包外的 `cli.py`、`debug/models.py` 消费」，未声称包内零消费，**成立**。S3「任何想拿对象图的代码都得 import HTTP 包」由此得到支持。

### C4 `app_factory.py` 生产零导入者

```
$ git grep -l 'app_factory' 1f29d0a -- 'src/**'
1f29d0a:src/app/observability/metrics.py      ← docstring 提及，非 import
1f29d0a:src/app/server/__init__.py            ← docstring 提及，非 import
1f29d0a:src/app/server/pipeline_app.py        ← docstring 提及，非 import
$ git grep -l 'app_factory' 1f29d0a -- 'tests/**' | wc -l
14
```

`src/` 内三处全是文档字符串，无一处 `import`。测试侧 14 个文件提及（其中 13 个真的 `from app.server.app_factory import create_app`，第 14 个是 `tests/unit/test_module_boundaries.py` 里作为断言字符串）。README 写「只有 12–14 个测试文件引用」——区间表述，成立。

另外确认无任何 ASGI app-string 入口能绕开它：

```
$ rg -n 'create_app|app_factory' --glob '!tests/**' --glob '!**/__pycache__/**' --glob '!.dev/**' .
（仅上述四处：定义 + 三处 docstring）
$ rg -n '"app:|app\.server:|--factory' src pyproject.toml Dockerfile contrib
（无命中）
```

### C5 `pipeline_app.py` 的 `_dispatch` = 418 行，「派发」组 = 479 行，「连接快照」组 = 68 行

AST 逐个顶层定义测量（`1f29d0a`）：

```
_extra_info 12  _readable 3  _socket_address 11  _snapshot_upstream_connection 32  _alpn 10   → 68 ✓（README 68）
_translation_losses 17  _Trace 63  _log_completion 48                                         → 128（README 127）
_serve 40  _aborted 14  _client_message_count 7  _dispatch 418                                → 479 ✓（README 479）
_StreamAccounting 60  _AccountedStreamingResponse 30  _counted_upstream 24  _tracked_delivery 22 → 136（README 135）
build_router 14  create_pipeline_app 15  _version 9  _lifespan 42                             → 80（README 79）
total 1037 ✓
```

`_dispatch` **恰好 418 行**（388–805）。三组小计各差 1（见 D1）。「约三分之一是可观测性代码」：68+128+136 = 332 / 1037 = 32.0%，成立。

### C6 `cli.py` 无函数内延迟导入；四条部署路径全部收敛到 `app.cli`

```
$ python3 -c '<AST 遍历，见下>'   # 对 1f29d0a 与工作树各跑一次
1f29d0a function-level imports: NONE
worktree function-level imports: NONE

$ rg -n 'ghc-api-proxy' pyproject.toml
55:ghc-api-proxy = "app.cli:main"
$ cat src/app/__main__.py
from app.cli import main
$ rg -n 'CMD' Dockerfile
28:CMD ["python", "-m", "app", "start"]
$ rg --no-heading -n 'ExecStart' contrib/systemd/ghc-api-proxy.service
23:ExecStart=/opt/ghc-api-proxy/.venv/bin/python -m app start --fd 3 --graceful-timeout 300
```

四条全部命中，`cli.py` 两个版本都无函数内 import。README 成立（推理链的一个缺口见 D3，结论不受影响）。

### C7 第 2 节其余权威分级引用准确

- `module-org.md`：追认树里 `server` 的唯一子模块确为 `routes`（第 20–21 行）；追认的顶层恰为 9 个（cli / config / core / history / lifecycle / model_provider / observability / pipeline / server）✓；「尚未确认、有疑虑」恰为 `anthropic context openai` ✓。
- `request-pipeline.md:3`：「请求从 `app.server.routes` 进入，经过 `app.pipeline` 处理后，交给 `app.model_provider`」✓；`:5`「`app.pipeline` 负责驱动*模型请求*的处理」✓ —— README 第 60 行「`request-pipeline.md` 把「驱动模型请求的处理」指派给 `app.pipeline`」成立。
- `architecture.md:3`：`D-ARCH = B`、`D-MIGRATION = M1` ✓；`:581` 裁决列确为 **M1**（与本文推荐 M2 不同）✓。
- `architecture.md:593`：「以下边界共同定义 B，不能拆掉其中一项却仍把结果称为本文方案 B」✓ —— README 第 33 行转述准确。
- `architecture.md:607-608`：「Record、class、module 与 `PolicyOutcome` variant 的具体名称、字段分组」「组件是否按文件或 package 合并／拆分」✓ 逐字命中（缺前置条件一事见 A1）。
- 第 36 行 architecture-audit 那栏：支撑报告写「8 条中 5 条仍成立（S1、S2、S5、S6、S7）、3 条已作废（S3、S4、S8）」✓；「`deployment/`／`web/` 三层方案不要重做，实际落地成了 `lifecycle`／`server`／`core`」✓（报告第 288 行「不要重做的工作」）。（一处解读上的张力见 D5。）
- 第 5 节「与 `D-ARCH = B` 五项核心的对应」表：五项边界的措辞与 `architecture.md:595-599` 逐条对应准确。

### C8 第 3.4 各条

| README 断言 | 复核 |
|---|---|
| 追认了却不存在：`server/routes`、`cli/start` | ✓ `src/app/server/` 无 `routes/`；`src/app/cli.py` 是模块，无 `start` |
| `cli/debug` 以顶层 `app/debug/` 存在；`cli` 是 416 行模块 | ✓ `src/app/debug/` 存在；`git show 1f29d0a:src/app/cli.py \| wc -l` = **416** |
| 存在却从未在追认清单里出现的 10 个 | ✓ debug delivery hooks models protocols routes streaming tokenization transform upstream，恰好 10 个包（另有 7 个顶层 `.py` 未计入，见 D4） |
| `core` 3 个模块、两个导入者自身不可达 | ✓ `src/app/core/` = `__init__.py` + `generation_identity.py` + `release_identity.py`；导入者恰为 `lifecycle/systemd/systemctl.py`、`tokenization/snapshot_store.py`；探针实测从 `app.cli` 出发二者皆 `not loaded` |
| 全仓无延迟导入 `systemctl` 的写法 | ✓ AST 扫全 `src/app`，函数内 `app.*` import 仅 4 处，全在 `app/anthropic/client.py`，无 systemctl |
| health/metrics 新旧链各写一遍 | ✓ `ops_routes.py:30,36,37,74` vs `routes/health.py:9,14,15` + `routes/metrics.py:7` |
| 两个不同的 `DeliverySession` | ✓ `src/app/delivery/anthropic_sse.py:590` 与 `src/app/pipeline/delivery/blocks.py:134`，两个 `__init__.py` 各自导出 |
| `lifecycle/rolling/` 只剩 `__pycache__` | ✓ `find` 只出 10 个 `.pyc`（含 `generation/__pycache__/`），`git ls-files` 空 |

### C9 第 6 节的三列判据

```
$ cat docs/.human-controlled/api.md
9:- Azure：`POST /openai/deployments/{deployment}/{chat/completions|responses|embeddings}`
10:- Gemini：`POST /v1beta/models/{model}:{generateContent|streamGenerateContent|countTokens}`
17:- 历史：`/history/api/*`、`/history/ws`
19:- 状态与配置：`/api/status`、`/api/config`
8:- ~~Responses WebSocket：...~~ 暂不支持
20:- ~~审批：`/api/approval/*`、`/api/approval/ws`~~ 暂不支持
21:- ~~Tokenization：...~~ 暂不支持
```

已追认 ✓；已裁决暂不支持 ✓（三项都带删除线并注「暂不支持」）。

新链不服务它们：`src/app/server/inbound.py:33-44` 的 `ROUTES` 只有 `/v1/messages`、`/v1/messages/count_tokens`、`/chat/completions`、`/responses`、`/embeddings`；`ops_routes.py` 只有 health / models / metrics，其 docstring 自陈「History and the management API need state this chain does not own yet, and are absent rather than answered with a plausible stub」✓。

旧链是唯一实现：`src/app/routes/{azure,gemini,history,management}.py` + `protocol_history.py` 存在，且 `app_factory.py:166+` `include_router` 它们 ✓。

**顺带确认一个 README 没提但可能被担心的缺口**：`GET /models`（`api.md:6` 已追认）**在新链上有实现**（`ops_routes.py:56-58` 注册 `/models`、`/v1/models`、`/openai/v1/models`），不属于第 6 节的缺口。

### C10 第 9.1 的历史叙述完全属实

```
$ git log --all --diff-filter=A --format='%h %ad %s' --date=short -- 'src/app/server.py'
128e486 2026-07-15 feat(server): add structured lifespan and health routes
$ git show --stat --format='%h %ad %s' --date=short 128e486
128e486 2026-07-15 feat(server): add structured lifespan and health routes
 src/app/deps.py            | 13 ++
 src/app/routes/__init__.py |  3 ++     ← 同一提交
 src/app/routes/health.py   | 31 ++     ← 同一提交
 src/app/server.py          | 44 ++     ← 同一提交
 ...
$ git show --stat --format='%h %ad %s' --date=iso b4ae8b0
b4ae8b0 2026-08-16 11:57:10 +0000 feat: make app.server a package with inbound format parsing
 src/app/server/__init__.py                   | 26 ++
 src/app/{server.py => server/app_factory.py} |  0     ← 100% rename
 src/app/server/inbound.py                    | 83 ++
```

`app/routes/` 与 `app/server.py` 确为 `128e486`（2026-07-15）**同一提交的兄弟**；`server` 确于 2026-08-16 由 `b4ae8b0` 把 `server.py` rename 成 `server/app_factory.py` 才成为包；「那时 `routes` 已独立服务旧链一个月」——07-15 到 08-16，成立。

第 9.1(c)「已由 `1f29d0a` 做到」也属实：`git show 1f29d0a:src/app/server/__init__.py` 第 3 行写着「It calls the entry `app.server.routes`; no such module exists here … so that spelling is the document's, not this package's」。

### C11 第 3 节 S3 关于守卫的描述

```
$ rg -n 'subprocess|app.server.app_factory' tests/unit/test_module_boundaries.py
16:import subprocess
29:    finished = subprocess.run(
42:    assert "app.server.app_factory" not in new_chain
```

「被 `tests/unit/test_module_boundaries.py` 用子进程钉死」✓。

### C12 第 5 节目标布局里点名的 `handler.py` 成员全部存在

对 `1f29d0a` 的 `handler.py` 做 AST，25 个顶层定义中，README 第 147/149/155/163 行点名的 `handle`、`handle_bounded`、`handle_count_tokens`、`shape_request`、`framer_for`、`assembler_for`、`stream_settings`、`delivery_buffer`、`stream_idle_seconds`、`dialect_for`、`delivers_blocks`、`deliver_blocks`、`error_status`、`error_headers`、`error_body`、`apply_route`、`translation_target`、`response_payload` —— **全部存在，无一虚构**。

### C13 第 10 节五条顺带发现

| 条目 | 复核 |
|---|---|
| `app/core/` 生产进程完全不加载，两个导入者自身也不可达 | ✓ 见 C8 |
| `app/lifecycle/systemd/` 整包只有一个测试在 import | ✓ `rg -ln 'lifecycle\.systemd' src tests` 唯一命中 `tests/unit/lifecycle/test_lifecycle_systemd_notify.py`；`src/` 内零导入者。**部署目标确为 systemd 托管**（`contrib/systemd/ghc-api-proxy.service` 存在且 `ExecStart` 走 `--fd 3`），「两者需要对账」的措辞成立 |
| `lifecycle/rolling/` 只剩 `__pycache__` | ✓ 见 C8 |
| `cli` 是 416 行模块而非追认的包 | ✓ 见 C8 |
| 十个顶层包从未出现在追认清单；三个「有疑虑」仍在 | ✓ 见 C8（一处不完整见 D4） |

---

## D. nit 级发现

### D1（nit）第 3.2 三组小计各差 1

127 vs 128、135 vs 136、79 vs 80（见 C5 的逐项测量）。表头写的是「大致行数」，且总和与三分之一的结论不受影响。差值恒为 1，看着像某一成员用了 `end_lineno - lineno` 而没有 `+1`。

### D2（nit）第 11 节「全仓唯一一处动态 import」不严格成立

```
$ rg -n 'importlib|__import__' --glob '*.py' src
src/app/lifecycle/listener.py:157:            stat = __import__("os").fstat(accept_socket.fileno())
src/app/lifecycle/adapter.py:98:                socket_stat = __import__("os").fstat(stat)
src/app/hooks/loader.py:18:        module: ModuleType = importlib.import_module(module_name)
（其余是 `from importlib import resources` / `importlib.metadata`，静态）
```

另有两处 `__import__`，但参数都是字面量 `"os"`，无法触达 `app.*`，**可达性结论不受影响**。「唯一」这个绝对词可以改成「唯一一处能加载 `app.*` 的动态 import」。

### D3（nit）第 3.3「`cli.py` 无延迟导入 → 这个闭包就是生产闭包」推理不完整（我已补齐，结论成立）

闭包内**任何**模块的函数内延迟导入都会在运行时扩大闭包，不只是 `cli.py`。我对整个 `src/app` 做了 AST 扫描：函数内 `app.*` import 共 4 处，全在 `src/app/anthropic/client.py`（第 205 行 `app.pipeline.route_policy`、357 行 `app.pipeline.executor`、377–378 行 `app.hooks.context` / `app.hooks.types`）。而该模块本身从 `app.cli` 不可达：

```
$ PYTHONPATH=src uv run --no-project python /tmp/probe4.py
app.anthropic.client         not loaded
app.anthropic                LOADED
app.pipeline.executor        not loaded
app.hooks.context            not loaded
app.hooks                    not loaded
```

**结论成立**，但 README 给的理由单独承担不了它。建议把这句改成「全 `src/app` 的函数内 `app.*` import 只有 4 处、全在从 `app.cli` 不可达的 `anthropic/client.py`」。

### D4（nit）第 3.4「存在却从未在追认清单里出现」只数了包，漏了 7 个顶层模块

`deps.py`、`errors.py`、`graceful_timeout.py`、`repetition_detector.py`、`runtime.py`、`shutdown.py`、`wire_json.py` 同样未出现在 `module-org.md` 里。同一形态，同样是「追认的树与代码分叉」，第 10 节最后一条的计数（「十个顶层包」）因此偏低。不影响任何结论。

### D5（nit）第 2 节「作废的三条恰好全是布局相关的」字面为真，但暗示被反例削弱

作废的 S3 / S4 / S8 确实都与布局有关。但仍成立的 5 条里，S7（`graceful_timeout.py` 拆成 `config/shutdown.py` + `deployment/systemd/timeouts.py`）同样是布局断言。支撑报告自己的读法也不同——它写的是「仍成立的 5 条几乎全是**没人动过的旧链叶子**」（`260822-server-layout-prior-art.md:134`），即失效的原因是「新链动过、旧链没动」，不是「布局类断言更易失效」。README 的措辞会让读者得到后一个印象。

### D6（nit）第 5 节目标树未安置 `handler.py` 的三个成员

`handler.py` 25 个顶层定义中，`blocks_from_anthropic`、`reply_summary` 在第 5 节的树里没有落点；`response_payload` 只在第 163 行的散文里被指派给 pipeline，树里没有对应行。设计草图不必穷举，登记备查。

---

## E. 未核查范围与能力边界

**明确没有核查的：**

1. **设计优劣**——第 7 节方案对比的取舍、第 9 节的两个倾向、第 5 节目标布局是否是好设计，均不在本次范围。另有一位评审负责。
2. **`.dev/docs/anthropic-responses-bridge/spec.md`** 的内容。A1 指出 README 漏引了「不覆盖 `spec.md` 的可观察行为合同」，但我**没有读 `spec.md`**，因而无法判断第 8 节哪几步真的会碰到它。这是 A1 的一个开口。
3. **`architecture.md` 679 行全文**。我读了第 3、5、40、44、403、568、574–616 行区段（状态段、授权说明、裁决矩阵、五项核心、可局部调整边界）。其余段落若另有对内部分层的细约束，我不知道。
4. **两份支撑报告本身的正确性**。按任务要求，我只用它们对照 README 有没有误读；`260822-server-layout-chain-map.md` 的 235 个模块划分、`260822-server-layout-prior-art.md` 的 8 条抽验，我没有独立重跑（B1 是个例外：我重跑了三个根的模块数）。
5. **任何搬迁的可行性**。我没有试搬 `tls.py`、没有试拆 `handler.py`、没有跑测试套件、没有跑 ruff / pyright。因此「搬完还能编译、还能过测试」这件事本报告不提供任何证据。
6. **4141 端口的实际服务状态**。A3 依据的是项目 `CLAUDE.md` 的陈述加上 `copilot-api-js` 的路由文件，**没有探测端口，也没有对该服务做任何操作**。若该服务实际已停，A3 降级为措辞问题。
7. **`hooks/loader.py` 的动态 import 在运行时会加载什么**。我只确认它从 `app.cli` 不可达（`app.hooks.loader not loaded`），没有分析它能加载的用户 hook 模块可能拖进什么。

**方法学声明：**

- 可达性探针**先做了正样本对照**（B1），证明它在目标模块真被导入时看得见；因此报告中的 0 是有分辨力的 0。
- 所有 `/tmp/rev1f29d0a` 上的测量都验证了 `app.__file__` 指向该副本树，排除了「PYTHONPATH 指向副本、实际解析到主树」这一类假数字。
- 涉及行数与结构的核查一律在 `1f29d0a` 上做，未用当前工作树的漂移值去判 README 的对错。
- 全程只读：未修改任何仓库文件，未 stage、未 commit、未 push，未触碰 `docs/.human-controlled/`。唯一的写入是本报告，以及 `/tmp` 下的探针脚本与 `1f29d0a` 源码副本。

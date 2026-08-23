# `app/server/` 死代码、遗留物与文档漂移审计

**日期**：2026-08-22。**性质**：只读分析，未修改任何文件、未 `git add`/`commit`/`stash`。
**锚点**：主仓 HEAD `ef4defb`（`refactor: give the endpoints the package name the spec ratified for them`，18:50）。`src/app/server/` 在审计开始时全部干净；审计进行中同伴把 `src/app/server/composition.py` 改成了 `M`（一处 warning 文案，+1 行，落在 `_warn_about_socks` 内）。**本文所有 `composition.py` 行号均以 `git show HEAD:` 为准，不是工作树版本。**
**并行状态**：`.claude/worktrees/` 下有 4 棵同伴工作树（`260822-never-silent-upstream-failure`、`delivery-keepalive`、`one-ending`、`upstream-error-events`）。凡做「全树零命中」判定的地方都把它们算进去了，并逐条注明。

---

## 0. 结论摘要

| 档 | 条数 | 内容 |
|---|---|---|
| major | 3 | 包 docstring 断言了一个 64 分钟后就被创建出来的模块不存在；一个全树零调用者的导出函数；生产 app 的运维端点挂载没有任何测试守住 |
| minor | 7 | 两处死 re-export、一处已改名模块的引用、一条事实两种拼法、一处模糊的文档引用、三处重构残留空洞、一处版本号两个来源 |
| 事实认定（非缺陷） | 1 | `app_factory.py` 的地位：**证据充分，生产零可达**——按项目记忆「不得擅自删除已实现的功能」，本文只给证据，不主张删除 |
| 文档漂移 | 6 份活文档 | 见第 5 节；报告原件（`reports/`、`YYMMDD-` 前缀件）按项目规矩**不列为待改** |

**一句话**：这轮重构本身干净（分层、命名、测试都跟上了），漏下的全是**「说明自己位置的那句话」**——包 docstring、`__all__`、以及散在活文档里指向 `handler.py` 和 1037 行版 `pipeline_app.py` 的引用。

---

## 1. 判据纪律与探针自证

本文做过三处「零命中」判定，每一处都先跑了正样本对照：

1. **`limit_in_flight` 全树零调用者**——正样本用同文件的 `InFlightLimit`，同一条命令得 113 行命中（含 4 棵同伴工作树、`.dev/`、`exp/`、`tests/`）。命令见 §3.2。
2. **无测试经生产 app 请求 `/health`／`/metrics`**——正样本先证明该模式能命中 `test_health_routes.py:22`、`test_pipeline_ops_routes.py:71`、`test_observability_phase6.py:50`，再证明这三个文件都不构造 `create_pipeline_app`。命令见 §4.1。
3. **`app_factory` 生产零导入者**——正样本用 `create_pipeline_app`，同一条命令命中 `src/app/cli.py:28,164,193`。命令见 §3.1。

**踩过一次坑并已纠正**：核查 `inference.py:531` 引用的「`implementation.md` 的结构怪味登记」时，第一遍命令带了 `| head`，输出被截断在 10 行，看起来像零命中——**差点报成假发现**。去掉截断后确认该章节存在于 `.dev/docs/anthropic-responses-bridge/implementation.md:263`，**这条引用是有效的**。凡本文写「零命中」处，命令均无 `head` 截断。

**未能覆盖的形态（能力边界）**：可达性结论基于静态 import 闭包与标识符搜索。看不见动态 import（全仓唯一一处在 `hooks/loader.py`，只挂旧链）、`getattr` 字符串反射、第三方插件入口。`[project.scripts]` 只有一条 `ghc-api-proxy = "app.cli:main"`（`pyproject.toml:55`），且全仓无 uvicorn factory 字符串（`rg '"app\.[a-z_.]*:[a-z_]*"' src` 零命中）。

---

## 2. Major

### M-1【注释漂移，代价高】`server/__init__.py` 断言 `app.server.routes` 不存在——它现在存在

**位置**：`src/app/server/__init__.py:3`

> `docs/.human-controlled/request-pipeline.md` has requests enter this package and be handed to `app.pipeline`. **It calls the entry `app.server.routes`; no such module exists here** — the real list is below — so that spelling is the document's, not this package's.

**事实**：`ef4defb`（18:50）创建了 `src/app/server/routes/`（5 个文件）。`__init__.py` 最后一次被修改是 `1b34815`（17:46），此后未再动。

```bash
git ls-tree HEAD src/app/server/routes/          # 5 blobs
git log --oneline -1 -- src/app/server/__init__.py   # 1b34815
```

**为什么算 major 而不是 minor**：这句话是**反过来错的**——它不是「引用了一个搬走的位置」，而是「主动断言一个现存模块不存在，并把用户亲笔文档的正确写法说成是文档单方面的拼法」。`docs/.human-controlled/request-pipeline.md:3` 现在与代码**完全一致**，而这份 docstring 还在替代码向那份文档道歉。下一个读 `app/server/` 的人从这里出发，会去别处找路由表。

**同一处的第二个问题**：`__init__.py:7` 的「Import the module you mean」清单是 `pipeline_app / app_factory / composition / http_errors / inbound`——漏了 `c01191f` 新建的 `app_state`（三个模块都在 import 它）和整个 `routes` 包（4 个模块）。这份清单是这个空 `__init__` 唯一的导航价值，缺一半就等于没有。

**建议措辞方向**（不代表已裁决）：把第 3 段改成陈述现状——`request-pipeline.md` 指定的 `app.server.routes` 已于 2026-08-22 落地；`inbound.py` 保留基础输入格式解析并自述该选择。

---

### M-2【死代码，全树零调用者】`admission.limit_in_flight`

**位置**：`src/app/server/admission.py:52-54`（定义）、`:57`（`__all__`）

```python
def limit_in_flight(app: ASGIApp, *, max_inflight: int) -> ASGIApp:
    """Wrap `app` so at most `max_inflight` client requests run at once. 0 disables."""
    return InFlightLimit(app, max_inflight=max_inflight)

__all__ = ["InFlightLimit", "limit_in_flight"]
```

**证据（全树穷举，含同伴工作树、`.dev`、`exp`、`tests`）**：

```bash
cd /home/xp/src/ghc-api-proxy-py
# 正样本对照：同文件的 InFlightLimit
rg -n -w --no-ignore --hidden -g '!.git/**' -g '!**/__pycache__/**' "InFlightLimit" . | wc -l
# → 113

# 被测符号
rg -n -w --no-ignore --hidden -g '!.git/**' -g '!**/__pycache__/**' "limit_in_flight" .
```

后者只输出 10 行：`src/app/server/admission.py:52` 与 `:57`，加上 4 棵同伴工作树里同一文件的同两行。**没有任何调用者，测试也没有**——`tests/unit/server/test_admission.py:11` 导入的是 `UNGATED_PATHS, InFlightLimit`，7 个测试全部直接构造 `InFlightLimit(...)`。生产唯一挂载点 `pipeline_app.py:36-39` 用的是 `app.add_middleware(InFlightLimit, ...)`，走的是类而不是这个工厂。

**为什么 lint 看不见它**：它在 `__all__` 里，Ruff 的 F401/未使用检查对 `__all__` 中的名字不发声。`uv run ruff check src/app/server` 当前全绿（已跑）。

**分类**：这是「完全没人用」，不是「只有测试在用」。与项目记忆「不得擅自删除已实现的功能」的关系：那条记忆保护的是**对外行为**与孤儿模块，而这里是一个内部便利工厂，其能力完全被同文件的公开类覆盖，且从未被任何一侧使用过。**仍不主张替用户删除**——本文只给判定与证据。

---

### M-3【测试盲区】生产 app 上的运维端点挂载没有任何测试守住

**位置**：`src/app/server/routes/router.py:30`

```python
    # Health, the model list and metrics. A supervisor that cannot ask whether the process is ready has to guess, and the inference routes alone give it nothing to ask.
    router.include_router(ops_router)
```

这一行正是 `ef4defb` 提交信息里说的那件事：「what a process serves is a fact about this package, and it was only readable by looking in two places」。**它现在没有任何测试。**

**证据**：

```bash
# 正样本对照：这个模式确实找得到运维端点的请求
rg -n -e '\.get\("/health' -e '\.get\("/metrics' -e '\.get\(path\)' tests
# → tests/int/test_health_routes.py:22,30,45,46
#   tests/int/test_pipeline_ops_routes.py:71,81,89,99,107
#   tests/unit/observability/test_observability_phase6.py:50

# 这三个文件里，有哪个构造了 create_pipeline_app？
rg -l "create_pipeline_app" tests
# → tests/int/test_pipeline_app.py, tests/e2e/claude/_harness.py  （都不在上面三个里）

# 反过来：那两个构造生产 app 的文件里，有没有请求过 /health 或 /metrics？
rg -n -e '/health' -e '/metrics' tests/int/test_pipeline_app.py tests/e2e/claude/_harness.py
# → 只有 3 行 docstring 里的英文单词 "healthy"、以及一句讲 /metrics 与文件一致性的散文，无任何请求
```

- `tests/int/test_health_routes.py`、`tests/unit/observability/test_observability_phase6.py` 走的是 **legacy `create_app`**（`app_factory`），与新链无关。
- `tests/int/test_pipeline_ops_routes.py:59-60` 自己起了一个裸 `FastAPI()` 再 `app.include_router(ops_router)`——**它按构造无法观测 `router.py:30`**。

**失效形态**：删掉 `router.py:30`，`uv run pytest` 全绿，而生产进程对 `/health/readiness` 答 404。那正是 `test_pipeline_ops_routes.py` 自己的 docstring 纪念的那次事故：

> Until 2026-08-19 the new chain answered 404 to `/health/readiness` while the existing chain answered it — and the existing chain is the one two of the three entry points still run. A supervisor pointed at the new chain had nothing to ask.

**同形的第二处**：`tests/unit/server/test_admission.py:11` 从被测模块**导入** `UNGATED_PATHS` 再拿它构造夹具（`:20` `if scope.get("path") in UNGATED_PATHS`）。于是「豁免集与真实挂载路径是否还对得上」这件事，测试按构造观测不到——`/health` 从路由表里消失，这组测试照样全绿。这是同源 oracle，不是覆盖不足。

**最小补法（一句话，不建议扩成框架）**：在 `tests/int/test_pipeline_app.py` 已有的 `make_client` 上加一条 `client.get("/health/liveness").status_code == 200`。它同时钉住 `router.py:30` 与 `UNGATED_PATHS` 里那条路径真的存在。**是否加、加在哪，交主会话/用户决定**；本文不擅自增测。

---

## 3. `app_factory.py` 的地位——事实认定

### 3.1 生产零可达

```bash
rg -n "create_app|app_factory" --glob '!.claude/worktrees/**' -g '!*.pyc' .
```

正样本对照：同一条命令对 `create_pipeline_app` 命中 `src/app/cli.py:28`（import）、`:164`（`--fd` 路径）、`:193`（stand-alone 路径）。

对 `create_app` 的结果里，`src/` 下只有三类命中：

| 位置 | 性质 |
|---|---|
| `src/app/server/app_factory.py:155` | 定义本身 |
| `src/app/server/__init__.py:5` | docstring，讲当年为什么把它从包 init 里摘掉 |
| `src/app/server/pipeline_app.py:5`、`src/app/observability/metrics.py:5` | 注释，明文称它 legacy |

**`src/` 内零导入者、零调用者。** 唯一的 console script 是 `ghc-api-proxy = "app.cli:main"`（`pyproject.toml:55`），`cli.py` 全文无 `app_factory`。

### 3.2 它独占 68 个模块

用 `tests/unit/test_module_boundaries.py` 同款子进程探针（每次全新解释器，`sys.modules` 里 `app.` 前缀集合）实测：

| 入口 | 可达 `app.*` 模块数 |
|---|---|
| `app.cli`（唯一真实生产入口） | 151 |
| `app.server.app_factory` | 140 |
| **仅 `app_factory` 可达** | **68** |

那 68 个是完整的旧链：`app.routes.*`（12 个）、`app.anthropic.*`（9 个）、`app.hooks.*`（9 个）、`app.history.*`（9 个）、`app.openai.*`（5 个）、`app.delivery.*`（3 个）、`app.deps`、`app.runtime`、`app.pipeline.executor`、`app.upstream.bootstrap` 等。完整清单可用下列命令复算：

```bash
cd /home/xp/src/ghc-api-proxy-py && uv run python - <<'EOF'
import json, subprocess, sys
PROBE = ("import importlib, json, sys;"
         "importlib.import_module(sys.argv[1]);"
         "print(json.dumps(sorted(n for n in sys.modules if n.startswith('app.'))))")
def reach(m):
    r = subprocess.run([sys.executable,"-c",PROBE,m],capture_output=True,text=True,check=True)
    return set(json.loads(r.stdout.strip().splitlines()[-1]))
print(sorted(reach("app.server.app_factory") - reach("app.cli")))
EOF
```

### 3.3 谁在用它：13 个测试文件

```bash
rg -l "from app.server.app_factory import" tests   # → 13
```

`tests/int/` 12 个（azure / gemini / history / management / approval / responses_ws / health / openai / anthropic ×3 / server_startup）＋ `tests/unit/observability/test_observability_phase6.py`。另有 `tests/unit/test_module_boundaries.py:38` 以**字符串**断言 `"app.server.app_factory" not in new_chain`——那是守住「新链不得拖进旧链」的那道结构断言，不是使用者。

### 3.4 判定

**`app_factory.py` 属于「只有测试在用」，不是「完全没人用」**——两者处置不同，而且这里的差别是实质性的：`.dev/docs/server-layout/README.md` §6 已实测记录，`api.md` 追认的 Azure、Gemini、History、`/api/status`、`/api/config` 五组端点**只有旧链有实现**，新链一个都不服务。删掉 `app_factory` 等于同时删掉这些端点唯一的实现。

按项目记忆「不得擅自删除已实现的功能」——「暂不支持」是对外行为裁决，不是删代码授权——**本文不主张删除，也不建议在没有用户裁决前动它**。`server-layout/README.md` §9.2 已把「旧链去留」列为待裁分叉，用户 2026-08-22 的裁决 D-3 是「先接新链，值得迁移的主动迁移；判断权在实施方」，**这不等于授权删除**。

---

## 4. Minor

### m-1 `composition.__all__` 有两个死 re-export

**位置**：`src/app/server/composition.py:526`（`"Chain"`）、`:532`（`"build_request_headers"`，其 import 在 `:38`）——行号按 `git show HEAD:`。

```bash
rg -n "from app.server.composition import" --no-ignore src tests exp contrib
```

全部 12 个导入点取的都是 `build_chain` / `build_http_client` / `resolve_provider_base_urls` / `refresh_catalogs` / `transport_options` / `github_token_path`。**没有一处从这里取 `Chain` 或 `build_request_headers`。**

- `Chain` 的真实来源是 `app.core.chain`（`c170f0f` 建立，`composition.py:24` 从那里 import）。经 `composition` 转出等于给它第二个门牌号，而 `server-layout/README.md` §5.1 的整个第零步就是为了让「任何层拿 `Chain` 不必反向拖进 37 个 pipeline 模块」——这条 re-export 恰好把那扇门留着。
- `build_request_headers` 的唯一真实来源是 `app.model_provider.ghc_client.headers`，全仓 8 个使用点（`src/app/upstream/copilot.py:18`、`ghc_client/client.py:15`、5 个 `exp/` 探针、1 个测试）**全部直接从那里取**。`composition.py:38` 的 import 存在的唯一理由就是喂 `__all__`。

**为什么 lint 看不见**：与 M-2 同因——名字在 `__all__` 里。

### m-2 `app_state.py:3` 引用的 `ops_routes` 已改名

> `CHAIN_STATE_KEY` and the accessor were declared identically in `pipeline_app` and in **`ops_routes`** ...

`ops_routes.py` 在 `ef4defb` 里被 `git mv` 成 `routes/ops.py`（提交 stat 显示 `src/app/server/{ops_routes.py => routes/ops.py} | 0`）。这句是历史陈述（「它曾经是两份」），语义没错，但它给出的是一个**今天 grep 不到的模块名**。同段 `:5` 的「Both route modules and the factory need it」则**仍然准确**（`routes/inference.py:57`、`routes/ops.py:13`、`pipeline_app.py:20`）。

### m-3 同一条事实两种拼法：哪些路由要挂 OpenAI 前缀

| 位置 | 判据 |
|---|---|
| `src/app/server/routes/router.py:22` | `if route.wire_format.value.startswith("openai-")` |
| `src/app/server/routes/table.py:38` | `if _route.wire_format is not WireFormat.ANTHROPIC_MESSAGES` |

`WireFormat`（`src/app/pipeline/request.py:21-27`）今天恰好只有 4 个成员、3 个以 `openai-` 开头，所以两者**当前等价**——已实测，`build_router()` 注册的 11 条 POST 路径与 `_BY_PATH` 一致：

```bash
uv run python -c "
import sys; sys.path.insert(0,'src')
from app.server.routes.router import build_router
for r in build_router().routes: print(getattr(r,'methods',None), getattr(r,'path',None))"
```

**这正是 `c01191f` 刚为 `CHAIN_STATE_KEY` 修掉的那个形态**——「Two spellings of one constant is a constant that can come to disagree」。加一个非 OpenAI 的第五种 wire format（`api.md` 追认了 Gemini 与 Azure，所以这不是假想），两条判据就会分家：`table.py` 会给它登记带前缀的可解析条目，而 `router.py` 只挂裸路径。今天的方向是安全的（`table` 是 `router` 的超集），所以 `inference.py:143` 那句「`build_router` registers only paths `route_for_path` knows」成立——但**它成立是因为两条独立判据碰巧的包含关系，不是因为有人保证了它**。

### m-4 `inference.py:358` 的 `deferred.md` 引用指不到唯一一份文件

> Registered in `deferred.md` §5; do not read the current behaviour here as a decision.

全仓有 5 份 `deferred.md`：

```bash
fd -g 'deferred.md' --no-ignore .dev/docs
# client-leg-formats / delivery-keepalive / tui / upstream/h2-goaway / upstream/retry-and-continuation
```

其中 `upstream/h2-goaway/deferred.md` 的 §5 是「本项目自身的中断频率仍无历史基线」，与这段注释无关。**正确的那份是 `.dev/docs/upstream/retry-and-continuation/deferred.md`**，其 §5（`:56` 起）第 2 格（`:81-91`）逐字对上了注释里说的 `committed_count == 0` 闸门、排空拒绝重开、以及 `buffering_policy` 取 `full`／`until-tool-use` 时整批丢块的代价。

**二次陷阱**：那个 §5 的标题是 `### 5. ~~已交付之后的两条失败路径行为不一致~~ —— 已裁决并落地（2026-08-22）`——**带删除线、标着已落地**。顺着注释找过去的人第一眼会以为这条已经关了，而真正开着的部分在标题下方第 25 行才开始（`:80` 的「下面是本条仍然打开的部分」）。建议把注释改成带路径的引用。

### m-5 三处重构残留的空行孔洞

```bash
for f in $(fd -e py . src/app/server); do
  awk -v F="$f" 'BEGIN{c=0} /^[[:space:]]*$/{c++; if(c==1) s=NR; next} {if(c>=3) printf "%s:%d-%d (%d blank)\n", F, s, NR-1, c; c=0}' "$f"
done
```

| 位置 | 空行数 | 谁被搬走了 |
|---|---|---|
| `src/app/server/inbound.py:20-23` | 4 | `ROUTES`／`route_for_path`（→ `routes/table.py`，`ef4defb`） |
| `src/app/server/pipeline_app.py:27-30` | 4 | `build_router`（→ `routes/router.py`，`ef4defb`） |
| `src/app/server/routes/inference.py:124-129` | 6 | `_client_message_count`／`_dispatch` 之间被摘走的东西（`b973ed0`／`ef4defb`） |

另有 `routes/inference.py:271-272`，函数体内部两个连续空行（`_hand_over_reasons` 与 `_hand_back` 之间）。Ruff 当前全绿（`ruff check` 不管这些），且项目已裁决**不跑 `ruff format`**，所以这些不会被自动收掉。**纯噪音，无功能影响**，只作为「哪里刚被动过」的痕迹登记。

### m-6 版本号有两个来源

`src/app/__init__.py` 是一行硬编码 `__version__ = "0.1.0"`，与 `pyproject.toml:7` 的 `version = "0.1.0"` 是两处手工同步的同一事实。新链 `pipeline_app._version()`（`:43-51`）读的是 installed metadata（`version("app")`，实测返回 `0.1.0`，可用），旧链 `app_factory.py:159` 用的是 `app.__version__`。所以两条链的横幅／FastAPI `version` 字段今天一致，但一次 `pyproject` 版本号变更会让 `app.__version__` 静默落后。**不在 `app/server/` 内，属「直接相邻」**，登记不主张。

### m-7 `inference.py:142-144` 的不可达分支——已自述，非缺陷

```python
    route = route_for_path(request.url.path)
    if route is None:
        # Defensive rather than reachable: `build_router` registers only paths `route_for_path` knows...
        return JSONResponse({"error": {"message": "unknown endpoint"}}, status_code=404)
```

核过了：`route_for_path` 做 `path.rstrip("/") or "/"`（`table.py:45`），FastAPI 默认 `redirect_slashes` 也不会把未知路径喂进来；`test_server_inbound.py:41` 已经钉住 `/responses/` 能解析。**该分支确实不可达，但注释已经说清楚了它是防御性的，并解释了为什么这条路径不写完成行。这是合格的死分支，不是遗留物**——列在这里只为说明我查过它、不算在 minor 计数里之外的漏项。

**同类另一处**：`inference.py:536` 的 `failure is None` 项，注释已明写「a review measured that `drained` and `failure` cannot both be set today ... Do not go looking for the state」。同样合格。

---

## 5. 文档漂移

### 5.1 范围与免责

按项目规矩，**报告原件是时点记录，不得回填**——`.dev/docs/**/reports/` 下的全部文件，以及 `.dev/docs/sync-refs/sxwxs-ghc-api/260821-*.md`、`.dev/docs/tmp/260822-*.md` 这些带 `YYMMDD-` 前缀的件，虽然大量引用 `server/handler.py` 与旧行号，**一律不列为待改**。下表只列**活文档**。

活文档清单的构造（40 份）：

```bash
fd -e md --no-ignore . .dev/docs \
  | rg -v "/reports/|/history/|/archive-|/tmp/|archived-2604-rewrite|sync-refs" | sort
```

正样本对照：该清单确实命中了已知的 `.dev/docs/upstream/retry-and-continuation/deferred.md:99`（引用 `handler.py:425-426`）。

### 5.2 引用已删除的 `src/app/server/handler.py`

`handler.py` 已在 `1b34815` 整体解散（`git show --stat 1b34815`：`src/app/{server/handler.py => pipeline/driver.py}`，其余符号分别去了 `pipeline/reply.py`、`pipeline/delivery_policy.py`、`pipeline/routing.py`、`server/http_errors.py`）。

| 活文档 | 行 | 原句要点 | 今天的落点 |
|---|---|---|---|
| `.dev/docs/client-leg-formats/README.md` | 13 | 表格「上游腿：`dialect_for` → `assembler_for`」→ `server/handler.py` | `dialect_for`／`assembler_for` 在 `src/app/pipeline/delivery_policy.py` |
| 同上 | 14 | 「客户端腿：`route.inbound_format` → `framer_for`」→ `server/handler.py` | `framer_for` 同上 |
| `.dev/docs/delivery-keepalive/spec.md` | 93 | `upstream_request_deadline` 由 `server/handler.py` 的 `attempt_deadline` 读出 | `src/app/pipeline/driver.py` |
| 同上 | 151 | `stream_idle_seconds` 在 `server/handler.py`；接线点在 `server/pipeline_app.py` | `stream_idle_seconds` → `src/app/pipeline/delivery_policy.py`；接线点 → `src/app/server/routes/inference.py:440-443` |
| `.dev/docs/upstream/retry-and-continuation/deferred.md` | 99 | `conversion.losses` → `handler.py:425-426` | `response_payload` 在 `src/app/pipeline/reply.py` |
| `.dev/docs/upstream/retry-and-continuation/status.md` | 150 | 校准在 `server/handler.py:301-303`（`pipeline_app.py:43` 引入） | `handle_count_tokens` 在 `src/app/pipeline/driver.py`；`pipeline_app.py:43` 今天是 `_version()` |

`.dev/docs/delivery-keepalive/deferred.md:150` 也提到 `handler.py`，但那是在复述一个具名提交（`064ba63`）当时干了什么——**属历史陈述，不改**。

### 5.3 引用 1037 行版 `pipeline_app.py` 的行号（模块现为 86 行）

| 活文档 | 行 | 引用 | 现状 |
|---|---|---|---|
| `.dev/docs/upstream/retry-and-continuation/README.md` | 78 | `pipeline_app.py:372-376` 的 `_CATEGORY_FOR_REASON` | 全仓已无 `_CATEGORY_FOR_REASON`（`rg -n "_CATEGORY_FOR_REASON" src` 零命中） |
| `.dev/docs/upstream/retry-and-continuation/deferred.md` | 131 | `pipeline_app.py:541` | 越界 |
| `.dev/docs/upstream/retry-and-continuation/status.md` | 23 | `pipeline_app.py:590-591` 是那条日志判定 | 越界；对应内容在 `routes/inference.py` |
| `.dev/docs/upstream/retry-and-continuation/status.md` | 150 | `pipeline_app.py:43` | 现为 `_version()`，指错东西而不是指空 |

**`:43` 这一条最值得单独点出**：越界的行号读起来像坏链接，会被发现；而**仍在文件范围内、却指向完全不相干代码的行号，读起来像有效引用**。这个模块从 1037 行缩到 86 行，任何 ≤86 的旧行号都落在这个陷阱里。

### 5.4 `.dev/docs/server-layout/README.md`——整份是执行前快照，且没有任何地方说它已被执行

该主题目录只有 `README.md` 与 `decisions.md`，两者 mtime 均为 **16:49**；重构落在 **17:11–18:50**。没有 `status.md`／`plan.md`。

于是 §8「分步路径」那张表（第 0–6 步）今天读起来仍像**待办**，而实际上：

| 步 | 内容 | 落地提交 |
|---|---|---|
| 0 | `Chain` 记录与建造者分离 | `c170f0f`（`app/core/chain.py`） |
| 2 | trace／完成行／连接快照 → `observability/` | `28c1a7a`（`observability/request_trace.py`） |
| 3 | `handler.py` 按四条缝拆开 | `1b34815` |
| 4 | `_dispatch` 拆薄 | `b973ed0` |
| 5 | 建立 `server/routes/` | `ef4defb` |

§10「顺带发现」里两条已经作废：`deliver_blocks 死代码待删`（`1b34815` 已删，提交信息明写「`deliver_blocks` is deleted rather than rehomed: it had no caller anywhere in the tree」）、`pipeline_app.py:54` 的 `pyright: ignore[reportPrivateUsage]`（同提交消掉）。§10 最后一条引的 `pipeline_app.py:3` 原句也已被 `ef4defb` 重写。

**该文档 §11 自述「数字是 `1f29d0a` 时点快照」，所以它没有说谎**；问题是**主题里没有第二份文档承接执行后的状态**，于是这份快照事实上在扮演「当前状态」的角色。按项目规矩，「living documents ... are updated at meaningful checkpoints」——五个提交连续落地是一个 checkpoint。**建议**：新建 `.dev/docs/server-layout/status.md` 记录第 0/2/3/4/5 步的落地提交与剩余项（第 1 步 `tls.py`→`lifecycle/` 与第 6 步旧链收尾），并在 README §8 表格加一列指过去；README 正文按「时点记录」保持不动。**是否新建、由谁写，交主会话裁决。**

### 5.5 `.dev/human-controlled-docs-candidates/` 里的四处失效引用

这批文件是**给用户摘取进 `docs/.human-controlled/` 的候选材料**，漂移代价比普通开发文档高（用户可能连引用一起摘走）。

| 文件 | 行 | 引用 |
|---|---|---|
| `proactive-rate-limiter.md` | 20 | `src/app/server/pipeline_app.py:979` 挂 `InFlightLimit` → 现为 `pipeline_app.py:36-39` |
| 同上 | 54 | `src/app/server/handler.py:354` 的 `handle_bounded` → 现为 `src/app/pipeline/driver.py` |
| `uncovered-modules.md` | 82 | `pipeline_app.py:38` 导入 `footer_tui_or_none`、`:1026` 调用 → 现为 `:18` 与 `:75` |
| `upstream-retry-and-continuation-supplements.md` | 164-165 | `pipeline_app.py:552` 的续写闸；`server/handler.py` 的 `assembler_for` → 现分别在 `src/app/pipeline/hand_over.py`（`hand_back_block`）与 `src/app/pipeline/delivery_policy.py` |
| `config-schema-gap.md` | 70, 77, 104 | 多处 `handler.py:180/236/517/631` 与 `pipeline_app.py:620-621/686/746-747` | 全部越界或改指 |

`docs/.human-controlled/` 本身**只有一处**提到 `app.server`——`request-pipeline.md:3`「请求从 `app.server.routes` 进入」——而这句在 `ef4defb` 之后**已经成真**。用户亲笔文档无需任何改动；需要改的是代码那边的 `server/__init__.py:3`（见 M-1）。

---

## 6. 测试结构：哪些模块「坏了没人会知道」

按模块列，判据是「破坏它的关键路径，会不会有测试变红」。

| 模块 | 直接测试 | 判定 |
|---|---|---|
| `admission.py` | `tests/unit/server/test_admission.py`（7 条） | ✅ 排队而非拒绝、0 禁用、异常释放槽位都钉住了。**但 `UNGATED_PATHS` 与真实路由表的对应关系没有**（M-3 第二半） |
| `app_state.py` | 无直接导入者；`test_pipeline_app.py:41`、`test_pipeline_ops_routes.py:14` 用 `CHAIN_STATE_KEY` | ✅ 传递覆盖足够——键改了两边一起红，这正是 `c01191f` 要的效果 |
| `composition.py` | `test_http_client_build.py`（约 540 行）、`test_provider_base_url_resolution.py`、`test_config_paths.py`、`test_stream_cap.py` | ✅ 代理分层、keepalive、SOCKS 警告、base URL 探测都有针对性覆盖 |
| `http_errors.py` | `tests/unit/model_provider/ghc_client/test_upstream_error_normalization.py` | ⚠️ 只有一个文件，且它是从 SDK 错误归一化那侧进来的。`error_body` 的 `code`／`field_path`／`upstream` 三个可选字段、以及 `PipelineAbort` 透读 cause 的两条路径，我没找到直接断言。**未做变异验证，权重仅为「值得看一眼」，不足以据此加测试** |
| `inbound.py` | `test_server_inbound.py` | ✅ |
| `pipeline_app.py` | `test_pipeline_app.py`、`tests/e2e/claude/_harness.py` | ✅ lifespan、tokenization flush、TUI 探测都经真实 app |
| `routes/inference.py` | `test_pipeline_app.py`（3000+ 行）、`test_stream_delivery.py` | ✅ 覆盖最厚的一块 |
| `routes/ops.py` | `test_pipeline_ops_routes.py`（5 条） | ⚠️ 端点**逻辑**覆盖良好，端点**挂载**零覆盖（M-3） |
| `routes/router.py` | 零直接测试 | ❌ 前缀展开有覆盖（`test_pipeline_app.py:863,883`、`test_pipeline_ops_routes.py:95` 三组参数化），`include_router(ops_router)` **无覆盖**（M-3） |
| `routes/table.py` | `test_server_inbound.py`（含 `/openai/v1/v1/messages is None` 这条负样本） | ✅ |
| `app_factory.py` | 13 个测试文件 | 见 §3 |

**不追求覆盖率数字**，上面只标了两处真实盲区：`router.py:30`，以及 `admission` 测试的同源 oracle。

---

## 7. 我查过但**没有**发现问题的地方（供不重复劳动）

- **代码里对文档的行号引用**：`src/app/server/` 全目录**零处**按行号引用 `.dev/docs` 或 `docs/.human-controlled`（`5f1b5b3` 那轮「stop the decision index citing line numbers」的效果）。唯一的非行号引用 `inference.py:531` → `implementation.md` 的「结构怪味登记」**有效**（该章节在 `.dev/docs/anthropic-responses-bridge/implementation.md:263`）。
- **`app.server` 包 init 的隔离**：`tests/unit/test_module_boundaries.py:34-40` 仍然钉住「新链不得拖进旧链」，实测通过（`app.server.app_factory`、`app.pipeline.executor`、`app.routes.*` 都不在 `app.server.pipeline_app` 的可达集里）。
- **`composition.py` 的其余导出**：`build_copilot_provider`（`:475` 被 `build_chain` 调用）、`build_github_token_source`（`:353`、`:464`）、`github_token_path`（`:325`）、`transport_options`（`:155`）、`TransportOptions` 全部有内部或包外真实使用者，**不是死的**。
- **`_version()`**：`version("app")` 在当前环境返回 `0.1.0`（`pyproject.toml:6` `name = "app"`），docstring 里那段「曾经给错发行版名导致 lifespan 整个挂掉」的历史与现状一致，**这次没有再错**。
- **基线健康**：`uv run ruff check src/app/server tests/unit/server` 全绿；`uv run pytest tests/unit/server tests/int/test_pipeline_ops_routes.py -q` → 98 passed。所以本文列的都不是既有故障的伴生现象。

---

## 8. 不确定与未做

- **没做变异验证**。M-3 的失效形态（删 `router.py:30` 仍全绿）是从测试文件构造推出的——`test_pipeline_ops_routes.py:59-60` 自建 `FastAPI()`、其余两个 health 测试走 legacy `create_app`，三者都按构造观测不到那一行。**这条推理每一环都核过代码，但我没有实际改代码跑一遍**（任务限定只读）。判断权重：**强到可据以行动**，但如果要变成一手证据，需要在隔离树里删那一行跑一次全量。
- **`http_errors.py` 的覆盖判断权重低**。我只做了「哪些测试文件 import 它」的检索，没有逐分支追断言。§6 表里标的是 ⚠️ 而不是 ❌，**不足以据此新增测试**。
- **同伴并行**。`src/app/server/composition.py` 在审计期间变脏；4 棵同伴工作树在飞。本文所有 `app/server/` 引文与行号都对 `git show HEAD:` 复核过。**§5 的活文档行号是工作树读数**，那些文件当时干净，但保质期以小时计。
- **`app_factory` 的 68 个独占模块清单**是静态 import 闭包，看不见动态 import。已知全仓唯一一处动态 import 在 `hooks/loader.py`（`load_user_hook_modules`），而 `app.hooks.loader` 本身就在那 68 个里——即它只挂旧链，不影响结论方向。

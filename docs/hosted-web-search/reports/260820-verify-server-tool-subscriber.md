# 独立验收：内置订阅者能否阻止 web_search 的 400

- 日期：2026-08-20
- 验收者：独立验收 agent（leaf executor，未修改任何生产代码）
- 被验对象字节指纹（验收全程未变，peer 在期间提交过其他文件，见第 6 节）：
  - `src/app/pipeline/subscribers/__init__.py` — `dc2ee686afc51a13b92c40a040e29681877c1625202c546881ac8f7299aa6425`
  - `src/app/pipeline/subscribers/server_tools.py` — `82aaf21b344537dae5c523f579379abcca8252f83dc072238d067f505c30d2c0`
  - `src/app/server/composition.py` — `343a1d3b54b8740a4897879033142de5cfec27f7839c502304b695ae5907f598`
- 验收脚本（一次性，写在会话 tmp 目录，未进入仓库）：
  - `/home/xp/.claude/jobs/03ca7248/tmp/verify_server_tools.py` — 端到端行为断言
  - `/home/xp/.claude/jobs/03ca7248/tmp/control_server_tools.py` — 反向对照（正控）
  - `/home/xp/.claude/jobs/03ca7248/tmp/probe_adjacent_paths.py` — 相邻路径探针

## 总体结论：**PASS**

主张「新增的内置订阅者能阻止这条生产 400」成立，且这个绿有分辨力——两种独立的破坏方式都能把它打红。

同时发现两条**残留缺口**（不推翻主张，但作者的说法有一处需要精确化），见第 5 节。

---

## 1. 端到端行为：核心验收点 — PASS

用项目现有的 HTTP 测试套路（`build_chain` + `create_pipeline_app` + `TestClient` + `httpx.MockTransport` 假上游）自建了一份独立脚本，**没有修改 `tests/http/test_pipeline_app.py`**，只读参考了它的 `make_provider`/`make_client` 写法。

向 `/v1/messages` POST：

```json
{"model": "claude-model", "max_tokens": 64,
 "messages": [{"role": "user", "content": "hi"}],
 "tools": [<Bash function tool>, {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]}
```

假 provider 实际收到的 body（`seen[-1].read()` 逐字读出）：

```json
"tools": [{"name": "Bash", "description": "run a command", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}}}]
```

判据：整个出站 body 的 JSON 文本中 **不含子串 `web_search`**（不只是不含 `web_search_20250305`，连 `name` 也一并消失）。日志同时打出 `dropped 1 server-tool declaration(s) this endpoint rejects: web_search_20250305`。

路由确认走的是直通分支：请求行是 `H1/H1 200 anthropic-messages/claude-model`，出站 body 仍是 Anthropic 形状（`messages` 键在、无 `input`/`instructions`），与背景根因描述一致。

附带确认 `web_fetch_20250910`（第二个被声明为已实测拒绝的族）同样被摘掉。

## 2. 反向对照（正控）— PASS，两种破坏都变红

按 `trusting-a-green-result` 的要求，**先证明变异确实生效、再看结果**，且变异全部是**进程内 rebind，一个仓库文件都没动**——因此不存在「还原不干净」这个风险面，也不可能覆盖 peer 的未提交改动（本仓库确实有并行会话在动，见第 6 节）。

| 变异 | 生效证明（观测层，先于跑断言） | 断言结果 |
|---|---|---|
| A：`server_tools._REJECTED_TYPE_PREFIXES = ()` | 直接调生产谓词 `_rejected_type(WEB_SEARCH)` → `None`（基线是 `'web_search_20250305'`） | **RED**：出站 tools 里 `{"type": "web_search_20250305", ...}` 原样出现 |
| A（边界断言） | 同上 | **RED**：只含 server tool 的请求，`tools` 键仍在，不再被删 |
| B：`composition.register_builtin_subscribers` 替换为 no-op | 读 app 实际用的那条链：`chain.subscribers.ids("attempt.prepare")` → `()`（基线是 `('builtin:server-tool-capability',)`） | **RED**：出站 tools 里 web_search 原样出现 |
| 还原后（同进程） | `chain.subscribers.ids("attempt.prepare")` → `('builtin:server-tool-capability',)` | **GREEN** |

两个生效证明都**绕开了被测判据本身**：A 读的是谓词函数在调用点的返回值，B 读的是 driver 真正会遍历的冻结注册表，都不经过「出站 body 里有没有 web_search」这条链路。

**还原干净的证明**：全程没有对仓库文件执行过任何 `Edit`/`Write`/`git checkout`；变异是 Python 属性 rebind，放在 `try/finally` 里。事后 `sha256sum` 三个被验文件与验收开始时逐字节一致（值见文首），`git diff --stat -- src/app/server/composition.py` 仍是 `6 insertions(+), 1 deletion(-)`，`git diff` 里那三行 `+register_builtin_subscribers` / `+subscriber_registry` 原样在位。

## 3. 不该改的没被改 — PASS

判据是**出站 body 与我 POST 的 body 整体 `==`**，不是只看某个键。

| 用例 | 结果 |
|---|---|
| `tools=[Bash]` + `tool_choice={"type":"tool","name":"Bash"}` | 出站 body `== ` 入站 body（`sent == posted: True`） |
| 完全不带 `tools` | 出站 body `==` 入站 body |
| `tools=[Bash]` + `tool_choice={"type":"auto"}` | 出站 body `==` 入站 body，`tool_choice` 仍是 `{"type": "auto"}` |

即：没有 server tool 声明时，订阅者对 payload 零改动（`adapt_server_tools` 在 `if not dropped: return` 处提前返回，行为与实测一致）。

## 4. 边界 — PASS

| 用例 | 观测 |
|---|---|
| `tools` 只有 `web_search`，带 `tool_choice={"type":"auto"}` | 出站 body 中 **`"tools" not in sent`**（键被删，不是置 `[]`）；`"tool_choice" not in sent` |
| `tools=[Bash, web_search]` + `tool_choice={"type":"tool","name":"web_search"}` | `tool_choice` 被删；`tools == [Bash]` 保留 |

「删键而不是置 `[]`」是直接读出站 JSON 的键集合判定的（`'tools' in sent = False`，取默认值打印为 `'<absent>'`），不是靠比较 `[]`。

## 5. 残留缺口（不推翻主张，但作者说法需精确化）

这两条都是我自己跑出来的，不是读代码推的。

### 5.1 `count_tokens` 路径不经过该订阅者 — 声明仍会原样发往上游

`POST /v1/messages/count_tokens`，body 带同样的 `tools`：

```
[count_tokens] outbound tools = [{"name": "Bash", ...}, {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
```

原因：`src/app/pipeline/count_tokens.py` 中没有 `DirectDriver`，因而不发 `attempt.prepare` 事件（`rg -n "DirectDriver|subscribers|publish" src/app/pipeline/count_tokens.py` 无匹配）。

影响判断（**权重：需实测才能定性，当前仅为路径事实**）：Copilot 的 count_tokens 端点是否也拒绝这条声明未经测量。若拒绝，现有代码会落到本地估算（200 + `estimated: true`）而不是 400，属于降级而非中断。所以这不是「生产 400 没被挡住」，但它确实是同一个客户端声明的第二个出口。

### 5.2 翻译腿（`/responses`）会把 Anthropic 拼法的声明原样转发

`/v1/messages` + `model=gpt-model`（走翻译到 `/responses`）时，出站 Responses tools 数组里出现：

```json
{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
```

模块 docstring 把「只作用于 Anthropic 腿」写成了刻意取舍，理由是 `/responses` 原生执行 web search。这个理由**只覆盖了半边**：`/responses` 原生支持的是它自己的 builtin 拼法（`web_search` / `web_search_preview`），而这里透传过去的是 Anthropic 的 `web_search_20250305`。该拼法能否被 Copilot 的 `/responses` 接受**未经测量**。

不构成本次主张的 FAIL——生产 400 发生在 `/v1/messages` 直通腿，且没有 Claude 模型广告 `/responses`（背景根因），所以这条路径今天不会被本次事故的流量走到。但 docstring 里那句「Responses 原生执行它」不足以论证「透传是安全的」，建议要么实测，要么把措辞收窄为「本模块不处理翻译腿，翻译腿的行为未测量」。

### 5.3 流式路径 — 已确认覆盖（非缺口）

`stream: true` 的 `/v1/messages` 走同一个 `DirectDriver.run`，实测出站 tools 同样只剩 `[Bash]`，`H1/H1 200 anthropic-messages/claude-model ... end_turn`。

## 6. 回归数字

所有命令均在 `/home/xp/src/ghc-api-proxy-py` 下执行。

| 命令 | 结果 |
|---|---|
| `uv run pytest -q`（06:38，HEAD=`23c6ad7`，含本次改动） | **1321 passed, 2 skipped, 0 failed, 107.33s** |
| `uv run ruff check src/app/pipeline/subscribers/ src/app/server/composition.py` | **All checks passed!** |
| `uv run pyright src/app/pipeline/subscribers/ src/app/server/composition.py`（额外跑的） | **0 errors, 0 warnings, 0 informations** |
| `uv run pytest -q`（06:44 重跑，HEAD 已被 peer 推进到 `b2576eb`） | 2 failed, 1320 passed, 2 skipped |

**未运行 `ruff format`**（项目禁止）。

关于 06:44 那次的 2 个红：全部在 `tests/unit/test_observability_footer.py`（`... == '[DRIN] 1 conn'` 之类的文案断言），来自 peer 正在改的未提交工作——`git diff --stat` 显示 `src/app/observability/footer.py` 与 `tests/unit/test_observability_footer.py` 各 1 行改动尚未提交，两个文件里都 grep 不到 `subscriber|server_tool|web_search`。与本改动无关。**干净的那次全绿（1321 passed / 0 failed）是在本改动所在的树上跑的**，这是本次验收采信的数字。

### 6.1 独立复核「窄化调用的 2 个红是既有问题」这一归因 — **成立，且机制可以说得更准**

不照单全收，跑了三个探针：

1. `uv run pytest tests/unit tests/http -q -p no:randomly` → **2 failed, 1057 passed**，正是 `test_upstream_429_is_seen_by_the_rate_limiter` 与 `test_upstream_503_does_not_enter_limited_mode`。报错文本是枚举身份不一致的典型指纹：`assert <RateLimitMode.NORMAL: 'normal'> is <RateLimitMode.NORMAL: 'normal'>`（值相等、`is` 不成立）。
2. 同一集合 `--ignore=tests/unit/test_module_boundaries.py` → **1056 passed, 0 failed**。确认触发源就是那个文件。
3. **决定性探针**：`git archive HEAD | tar -x -C /tmp/ghc-head-probe` 导出一份纯净 HEAD 树（不含本次改动，也不含任何新增测试文件——已验证 `src/app/pipeline/subscribers` 不存在、`composition.py` 中 `register_builtin_subscribers` 出现 0 次），再用 `PYTHONPATH=/tmp/ghc-head-probe/src` 让 `app` 解析到该副本（已打印 `app resolved from: /tmp/ghc-head-probe/src/app/__init__.py` 确认），跑同一集合 → **2 failed, 1011 passed, 1 skipped**，同样是这两个用例。

结论：归因成立，**与本改动无关，是既有问题**。

一处措辞精确化：机制不是「重新加载模块」。`tests/unit/test_module_boundaries.py::reachable_from` 做的是**把 `sys.modules` 里所有以 `app` 开头的条目全部 `del` 掉再重新 import**。而 `test_pipeline_app.py` 那两个用例的 `from app.pipeline.rate_limiting import RateLimitMode` 写在**函数体内**（第 372、401 行），于是它们在被清空后拿到的是新建的枚举类，而 `Chain` 里持有的限流器来自更早加载的那份——两个不同的类对象，`is` 必然为假。这也解释了为什么恰好只有这两个用例红：全仓库只有它们在函数内延迟 import 这个枚举。

## 7. 我做过和没做过的事

**做过**：只读 `tests/http/test_pipeline_app.py`、`src/app/pipeline/subscribers/*`、`src/app/server/composition.py`、`src/app/pipeline/direct_driver/base.py`、`tests/unit/test_module_boundaries.py`；在 `/home/xp/.claude/jobs/03ca7248/tmp/` 写了 3 个一次性脚本；在 `/tmp/ghc-head-probe` 建了一份 HEAD 只读副本（`git archive`，不新建 worktree、不动 `.git`）。

**没做过**：没有修改、格式化或删除任何仓库文件；没有 `git stash`/`checkout`/`commit`；没有跑 `ruff format`；没有 `git worktree add`。

**没有证明的事**（避免被读宽）：

- 没有对真实 Copilot 上游发过任何请求。所有上游行为来自 `httpx.MockTransport`，因此本报告证明的是「**这条声明不会被发出去**」，不是「上游收到这个 body 会返回 200」。后者由背景根因文档与 `refs/` 里的实测支撑，不在本次验收范围。
- 没有验证 `_REJECTED_TYPE_PREFIXES` 这个名单**是否完整**——「哪些 type 会被上游拒」是上游事实，我没有测量能力。我只验证了名单里的两族确实被摘掉、名单外的普通 function tool 确实不被动。
- 5.1 与 5.2 两条残留只确认了「声明会原样发出去」这个路径事实，**没有测量上游对它们的实际反应**。

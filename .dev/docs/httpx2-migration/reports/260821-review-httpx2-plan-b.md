# 评审报告 B：httpx2 迁移计划的覆盖面与可验证性

评审对象：`docs/agents/httpx2-migration/plan.md`（起草于 2026-08-21）
评审基准：仓库 HEAD `172adc2`，工作树状态为 2026-08-21 12:1x
评审人分工：**覆盖面漏项、验证充分性、可回滚性、文档纪律、事实性断言的支撑**。D3（`stream_cap` 的 cap 谓词）与依赖上界（Q1）由另一位评审员负责，本报告不重复攻击那两块，仅在与本分工交叉处引用。

> 派单指定的 `my-skills:as-reviewer` 技能在本机不存在（`/home/xp/.claude/skills/` 无此目录，插件技能列表中也无同名项）。改用最接近的既有方法：`verifying-authoritative-claims`（逐条把断言对回一手来源）与 `trusting-a-green-result`（判断绿灯有没有分辨力）。这一替换不改变评审判据，但请知悉派单里的技能名可能已过期。

## 判定

**needs-fix。** 计划的技术判断（迁移方向、D2/D4/D5 的改法、D3 的机制分析）经抽查基本成立，但**实施顺序 §3 漏掉了一个会让整条测试链在第一步就死掉的依赖后果**，且 §4 的验证清单遗漏了两类「换个环境就不成立」的断言。另有两处把二手转述写成了「原话」和「唯一入口」。

严重度计数：blocker 1、major 5、minor 3。

---

## Blocker

### B1：D6 的依赖切换会卸载 `httpx`，而 `starlette 0.52.1` 的 `TestClient` 硬依赖它 —— `tests/int` 整层在 import 阶段就死

**置信度：高（已复现，非推断）。**

计划 §3 步骤 1「`pyproject.toml` 按 D6 改，重新生成 `uv.lock`」。D6 的 diff 删掉了 `"httpx[http2,socks]"` 与 `"httpx-ws"`，并把 `anthropic` / `openai` 抬到 `>=1` / `>=3`。这三件事合起来的后果是：**`httpx` 这个发行包从依赖图里彻底消失**。

在 `.venv` 里，迁移后仍会声明非 extra `httpx` 依赖的只有 `anthropic 0.79.0` 与 `openai 2.21.0` 两家，而 D6 恰好把这两家抬过了改用 httpx2 的大版本：

```
$ .venv/bin/python  # 检查迁移后各直接依赖谁还要 httpx（非 extra）
  -> [('anthropic', 'httpx<1,>=0.25.0'), ('openai', 'httpx<1,>=0.23.0')]
$ /home/xp/.claude/jobs/ca953617/tmp/latest-venv/bin/python  # 抬版本后
openai==3.3.1     httpx2<3,>=2.7.0
anthropic==1.0.0  httpx2<3,>=2.0.0
```

把仓库真实的 `pyproject.toml` + `uv.lock` 原样复制到 `/tmp/httpx2-lockprobe-c1/`，只施加 D6 那一处 diff，再跑 `uv lock`（这正是步骤 1 的动作）：

```
$ cd /tmp/httpx2-lockprobe-c1 && uv lock
Updated openai v2.21.0 -> v3.3.1
Removed tqdm v4.68.4
Added truststore v0.10.4

$ rg -n '^name = "(httpx|httpx2|starlette|fastapi)"$' -A1 uv.lock
fastapi   0.129.0
httpx2    2.12.0
starlette 0.52.1
$ rg -q '^name = "httpx"$' uv.lock; echo $?
1                      # 1 == 整个 lock 里没有 httpx
```

保守的重新 lock **不会**抬 fastapi（`fastapi 0.129.0` 声明 `starlette<1.0.0`），于是 starlette 停在 `0.52.1`。而 `starlette 0.52.1` 的 `testclient` 模块是这样开头的：

```
$ .venv/bin/python -c "import starlette.testclient ..."   # 屏蔽 httpx 后
RuntimeError : The starlette.testclient module requires the httpx package to be installed.
```

`starlette/testclient.py` 里 `class TestClient(httpx.Client)`、`class _TestClientTransport(httpx.BaseTransport)` —— 它认的是**真 httpx**，0.52.1 完全不知道 httpx2 的存在。

打击面：清单 §5.4 实测的 **14 个文件、72 处 `TestClient`**，包括 `tests/int/test_pipeline_app.py`、`test_anthropic_responses_stream_route.py`、`test_openai_routes.py`、`test_anthropic_routes.py`、`test_gemini_routes.py`、`test_azure_routes.py`、`test_management_routes.py`、`test_history_routes.py`、`test_health_routes.py`、`test_approval_routes.py`、`test_server_startup.py`、`test_anthropic_responses_route.py`、`test_responses_ws.py`。这些是**模块级 import**，不是运行期分支 —— 收集阶段就红。于是计划 §3 步骤 8「全量回归 `uv run pytest`」在计划写成的形态下**永远不可能通过**，而计划对此一个字也没有。

另一条分支同样是未决的：如果放开 fastapi 上限重新解析，得到的是 `fastapi 0.141.1` + `starlette 1.6.0`（我在 `/tmp/httpx2-lockprobe-a1/` 复现过），而 `starlette 1.6.0` 的 testclient 是 `import httpx2 as httpx`，回落到 httpx 时打 `DeprecationWarning`。这条分支下 TestClient 活下来了，但它返回的是 `httpx2.Response`，且**顺带把 ASGI 框架做了一次 major 升级**（见 M5）。

两条分支都需要一个明确裁决，计划里都没有。

**最小修法（三选一，请裁决）**：
1. 把 `httpx` 加进 `[dependency-groups] dev`，明确注释「只为 `starlette.testclient` 存在」——代价是测试环境里两个 httpx 并存，但产品代码不 import 旧包，不违反「一条 code path 不混用」；
2. 抬 fastapi 下界到能带 `starlette>=1.0` 的版本（并把 starlette 1.x 的迁移影响单列一步）；
3. 放弃 `TestClient`，全面改用 `httpx2.ASGITransport` —— 改动量最大，不建议在本次迁移里做。

我倾向 1：它把「测试宿主还没跟上」这个事实局限在 dev 组里，与 §5.5 的 cassette 机制、§5.1 的 `MockTransport` 都不冲突，且是官方迁移指南本来就推荐的形态（见 M2）。

---

## Major

### M1：D1 的支撑理由 1 事实错误 —— `build_http_client` 不是唯一入口，且 WebSocket 根本不吃它

**置信度：高（读代码确认，可复核）。**

计划 D1 原文：

> 1. **共享连接池是本项目的既有设计**（`composition.py:123 build_http_client` 是唯一入口，SDK 与 WebSocket 都吃它）。

这句话的两半都不成立，而它是 D1 用来否决双栈方案的**权重最高的那条理由**。

**「唯一入口」不成立。** 计划自己援引的清单 `docs/tmp/260821-httpx-usage-inventory.md` §2.3、§2.4 就写着另外两个构建点：

- `src/app/upstream/client.py:21-37` `create_http_client(settings)` —— 仍在传 `Limits` / `Timeout`；
- `src/app/auth/service.py:38` —— device flow 的一次性 `httpx.AsyncClient(timeout=30.0)`。

且 `create_http_client` 在活路径上：`src/app/server/app_factory.py:38` import `initialize_upstream_services`，`app_factory.py:99` 调用它且**不传 `http_client`**，于是 `src/app/upstream/bootstrap.py:110` 的 `client = http_client or create_http_client(settings)` 走右分支。

**「WebSocket 也吃它」不成立，而且方向反了。** 全仓库唯一构造 `ResponsesWebSocketClient` 的地方是 `src/app/upstream/bootstrap.py:250`：

```python
    runtime.responses_ws_client = ResponsesWebSocketClient(
        client,                                    # ← bootstrap.py:110 的 client，即 create_http_client 的产物
        f"{ws_base_url}/responses",
        queue_size=settings.openai_responses.ws_queue_size,
    )
```

而 `src/app/server/composition.py` 与 `src/app/server/pipeline_app.py` 里**没有任何一处**构造 WS 客户端（`rg 'responses_ws|ResponsesWebSocketClient' src/app/server/composition.py src/app/server/pipeline_app.py` 只命中 `pipeline_app.py:264,266` 两条无关注释）。也就是说 WebSocket 用的是那个**没有 socket options、没有 proxy mounts、没有 `cap_streams_per_connection`** 的旧客户端。

**后果分两层：**

- 对本次迁移：§3 的实施顺序**从头到尾没有点名过 `upstream/client.py` 与 `auth/service.py`**，它们只被步骤 2「机械改名」隐式覆盖。机械改名对这两处确实够用（`Limits` / `Timeout` 的构造签名在 httpx2 里逐字不变，已由 API delta §2.1 实测），但读计划的人不会知道自己要动三个构建点。清单的「最小必改清单」第 3、4 条正是这两项，计划漏抄了。
- 对 D1 的论证：如果「共享连接池」这条设计其实只覆盖了三个构建点中的一个、且不覆盖 WebSocket，那么「双栈会推翻这条设计」这个理由就站不住。D1 的结论（整体迁移）我**认同**，但它应当由理由 2、3 承担 —— 而理由 2 本身也有问题，见 M2。

**修法**：把 D1 理由 1 改写成事实（「主产品路径 `pipeline_app` 经 `build_http_client` 共享一个池；`app_factory` 旧路径与 device flow 各有独立客户端」），并在 §3 显式加一步「三个构建点逐一改名并确认 `Limits`/`Timeout` 签名不变」。

### M2：D1 理由 2 与 §6 把官方迁移指南的**转述**写成了「原话」，且指南的实际建议与 D1 的做法相反

**置信度：高（已抓取原页面对照）。**

计划 D1 写：

> 2. 官方迁移指南的原话是 "Don't mix both packages within a single code path"。

`https://httpx2.pydantic.dev/migration/` 上的实际句子是：

> "Whatever you choose, **don't mix the two packages in one code path**."

措辞不同（`the two packages` / `in one code path` vs `both packages` / `within a single code path`）。这不是吹毛求疵：计划所依据的一手报告 `docs/tmp/260821-httpx2-api-delta.md` §8 第 6 条**明确写了**「迁移指南全文我只拿到了摘要 …… 需要逐字条款时人工打开」。也就是说，计划把一份自称「只有摘要」的来源，加上英文引号、冠以「原话」二字，升格成了逐字引用。这正是派单里问的「把未验证写成已验证」。

更实质的问题是**这条引用被用反了**。同一页面在同一节还写着：

> "You can migrate your own code **incrementally**, one module at a time, one pull request at a time. There is no flag day."
> Tip: "Don't try to migrate a large application in one giant pull request." —— 建议 add httpx2 alongside httpx, move modules gradually, **and drop the old pin once nothing imports it**.

指南禁止的是「**一条 code path** 里混用」，不是「**一个项目**里同时装着两个包」。而 D1 把它读成了后者，用来否决「保留 httpx」的一切形态。这个误读直接导致了 B1：如果按指南「先并存、最后再摘掉旧 pin」的顺序，`httpx` 会一直留在依赖图里，starlette 0.52.1 的 `TestClient` 就不会死。

**修法**：把引号内的文字改成逐字原文并给出 URL；把 D1 理由 2 重述为「同一条出站 code path 不混用」，并明确区分「运行期 code path 的单一性」（要保证）与「安装面的单一性」（不必立刻达成，且与 B1 冲突）。

### M3：D5 被计划自己定性为「三处哑失败之一」，却没有任何测试；被点名的 `test_imports.py` 对它零分辨力

**置信度：高。**

计划 D5 写得很清楚：`HTTPXClientInstrumentor` 迁移后会「成功执行、不报错、插桩到没人用的包上，出站 trace 静默消失」。§3 步骤 6 给它配的验证是：

> 6. **OTel**：按 D5 改 `observability/tracing.py`，同步改 `tests/unit/test_imports.py` 的模块名单。

`tests/unit/test_imports.py` 的全部内容是对 `CORE_MODULES` 逐个 `import_module(...) is not None`。它对 D5 的失效**在迁移前后都是绿的**：

- 名单里的 `"opentelemetry.instrumentation.httpx"` 是**模块名**，用哪个 instrumentor 类都不改变它能否 import —— 这一条无论 D5 改没改都绿；
- 换句话说，「同步改模块名单」这个动作根本不落在 D5 的失效面上。改名单是为了让 `"httpx"` / `"httpx_ws"` 这两条不因为包被卸载而变红，那是 B1 的连带项，与 tracing 无关。

对照 D3：计划对 D3 提出了「必须新增判别性用例，并按 `trusting-a-green-result` 证明它能打红」的标准。**同一份计划里，两处同为静默失效，验证标准差了一个量级。**

而且判别性探针**已经跑过了**：`docs/tmp/260821-httpx2-ecosystem-compat.md` §3.1 用 in-memory span exporter 做了正负对照：

```
legacy-instrumentor-only: 1 ['http://127.0.0.1:36617/probe']
both-instrumentors:       2 [..., ...]
```

把它固化成一个单测（起 loopback server + `InMemorySpanExporter`，断言 `httpx2` 出站请求产生了 span）的成本极低，且天然带正样本对照。

**修法**：§3 步骤 6 加「新增 tracing 判别性用例，退回 `HTTPXClientInstrumentor` 应变红」，与 D3 同标准。

### M4：V1（TLS）被排到最后一步，其退路又依赖一个 D6 没有声明的 `certifi`；而一个能当场回答它的探针已经躺在树里，计划没提

**置信度：高。**

三个问题叠在一起：

**(a) 顺序错了。** V1 在 §4，对应 §3 的步骤 9「真实上游验证」—— 也就是说，**全部 8 步改完、提交完之后**才知道目标机的系统信任库能不能校验上游证书链。但 V1 是本次迁移里**最不需要改代码就能回答**的一项：它只取决于 `httpx2.AsyncClient()` 默认分支拿到的 `truststore.SSLContext` 能不能握上手。它应当排在步骤 1 之前，作为「要不要在 D6 里同时加 `certifi` 并显式传 `verify=`」的前置输入。

**(b) 退路的依赖没写进 D6。** V1 的退路原文是「显式传 `verify=ssl.create_default_context(cafile=certifi.where())` 保持旧行为（需重新声明 certifi 依赖）」。计划括号里承认了要重新声明 certifi，但 **D6 的 diff 里没有 `certifi`**。而 httpx2 的元数据里 `certifi` 已经被移除（API delta §3：「依赖侧两个减法/加法：去掉了 `certifi`、加上了 `truststore`」）。所以按 D6 的 diff 装出来的环境里 `import certifi` 会失败，退路在写下的形态下不可执行 —— 必须同时改 `pyproject.toml` 并重新 lock，即回到步骤 1。

**(c) 探针已经存在，计划没引用它，也没有任何输出被记录。** 树里有 `/home/xp/src/ghc-api-proxy-py/.dev/exp/httpx2-cap-probe/probe_tls.py`（2026-08-21 12:06），它做的正是 V1 要的事：对 `https://api.githubcopilot.com/models` 与 `https://api.github.com/user` 分别用 httpx 与 httpx2 发不带凭据的握手，**并且带了一个 `expired.badssl.com` 的负样本对照**来证明探针看得见失败。计划 §4 V1 只写「必须在目标部署机上对真实上游发一次握手」，既没指向这个脚本，也没有任何一行记录说它跑没跑、结果如何。

我**没有代你运行它**（它对第三方生产端点发外部请求，超出只读评审的授权范围），但它是本次迁移里 ROI 最高的一次执行：一条命令，几秒钟，能把 V1 从「待验证」变成「已裁决」。

**修法**：把 V1 提到步骤 1 之前执行；把 `probe_tls.py` 的路径与输出写进计划；若 truststore 分支失败，D6 的 diff 里同时补 `certifi`。

### M5：计划完全没有回滚与中止判据，而步骤 1 会静默夹带一次 starlette 大版本升级

**置信度：高（升级已复现）。**

派单问「有没有一个中间状态是回不去也走不下去」。**技术上的回滚是廉价的**：`git checkout pyproject.toml uv.lock && uv sync` 就能把环境还原，`git revert` 能撤掉任何一个语义提交。所以「回不去」不成立 —— 但**「不知道该在哪里回」成立，且缺失是真实缺陷**，理由有三：

1. **步骤 1 到步骤 2 之间是一个环境不可用窗口。** 步骤 1 卸载 httpx、装上 httpx2，此时 `src/` 全部还写着 `import httpx`，整个应用与全部测试都跑不起来。项目规约明确允许提交不绿，所以这不是问题本身；问题是计划没说这个窗口存在，也没说窗口里唯一有效的验证手段是什么。若步骤 2 的机械改名跑到一半出问题，执行者手上没有任何可用的判据。
2. **步骤 1 会夹带无关的大版本升级。** 我复现的两条分支里，如果 `uv lock` 允许抬 fastapi，结果是 `fastapi 0.129.0 → 0.141.1`、**`starlette 0.52.1 → 1.6.0`（major）**。这会被塞进一个标题写着「依赖切换」的提交里。仓库 HEAD 前一个提交 `1d14605` 恰好就是「stop importing a private starlette helper that 1.x removed」—— 说明 starlette 1.x 的影响面本项目已经踩过一次。计划必须要求：重新 lock 之后逐行审 `uv.lock` 的 diff，把非 httpx 的版本变动单独裁决、单独提交。
3. **V1、V2 都是「事后才知道」的验证，却没有配套的中止条款。** 步骤 9 的真实上游验证若失败，计划没说是回滚整批、还是打补丁前进（M4(b) 已证明「打补丁前进」这条路当前是断的）。

**修法**：§3 之后加一节「回滚与中止」，至少写明：(a) 每一步的还原命令；(b) 步骤 1 之后必须 `git diff uv.lock` 逐行确认没有夹带无关升级；(c) V1 失败时的分支（补 certifi 前进 vs 整批回滚）由谁裁决。

---

## Minor

### m1：清单点名的两条静默失效风险从计划里消失，且没有记录「已核」

清单 §9 有两条被标为「哑」的风险，计划 §3 / §4 / §6 全都没有出现：

- **风险 3 的第 1 条**：`allow_env_proxies = trust_env and transport is None`。这是 `composition.py:126` 文档串里写死的、`_proxy_mounts` 存在的**唯一理由**。httpx2 若改了这个判定，代理会被挂两次或环境代理被忽略，全哑。
- **风险 5**：`getattr(upstream, "_request", None)` 三处（`src/app/anthropic/client.py:293,461`、`src/app/pipeline/executor.py:417`）。属性改名后一律得到 `None`，无守卫。

我替你核了，**两条在 httpx2 2.12.0 下都成立**：

```
$ rg -n "allow_env_proxies" .../httpx2/_client.py
659:  allow_env_proxies = trust_env and transport is None     # 与 httpx/_client.py:685 逐字相同
$ python -c "import httpx2; print(hasattr(httpx2.Response(200), '_request'))"
True
```

所以这不是会出事的漏项，但按 `record-what-not-adopted`，「查过、成立、故不列入实施步骤」和「没想到」在文档上必须可区分。计划现在读起来是后者。建议在 §6 的「考虑过但不采纳」表里各加一行，附上上面两条证据。

### m2：D3 的判据探针没有被任何版本控制收纳，输出也没有落盘

`docs/agents/httpx2-migration/plan.md` D3 的那张表（`[6]` vs `[2,1,1,1,1]`）唯一的支撑是 `.dev/exp/httpx2-cap-probe/probe_cap.py`。我跑了，数字**完全对得上**：

```
$ /home/xp/.claude/jobs/ca953617/tmp/latest-venv/bin/python .dev/exp/httpx2-cap-probe/probe_cap.py
httpcore2 2.12.0
  cap in is_available only (current code)    -> per-connection counts [6]  cap respected = False
  cap in can_handle_request                  -> per-connection counts [2, 1, 1, 1, 1]  cap respected = True
```

所以断言本身成立（这一条不构成对 D3 的攻击，交由另一位评审员）。问题只在证据保全：`git -C .dev status --porcelain` 显示 `?? exp/httpx2-cap-probe/`、`?? exp/httpx2-migration/`、`?? docs/tmp/` —— 全部未追踪。项目规约要求「PoC 通过仓库文件交换完整报告」，而这两个探针的**输出**在任何仓库文件里都不存在，只以计划正文里那张表的形式活着。一次误删就没了。建议在 `.dev` 里提交这两个探针目录，并把两次运行的原始输出贴进计划或一份 `docs/tmp/` 记录。

顺带：`.dev/exp/httpx2-migration/rename_imports.py` 是一个已经写好的机械改名脚本（tokenize 级、只改 NAME token、遇到 `import ... as` 直接报错退出、显式保护 `opentelemetry.instrumentation.httpx` 这类属性位）。它质量不错且正好实现了步骤 2，但**计划步骤 2 完全没有提到它**。步骤 2 的「注释与文档串里的 `httpx` 需要逐条判断」与脚本 docstring 里的「They get a separate, reviewed pass」是同一件事，应当在计划里接上，否则下一棒会重写一遍。

### m3：D4 之后，`self._http.websocket(...)` 这条新写的默认实现将不被任何测试触达

`ResponsesWebSocketClient.__init__` 目前的 `connect: Callable[..., Any] = aconnect_ws` 在两个测试里都被整体替换掉：

- `tests/unit/openai/test_responses_ws_transport.py:37-40` 注入自己的 `connect`，只断言 `captured["url"]` 与 `captured["queue_size"] == 32`；
- `tests/int/test_responses_ws.py:45-66` 连 `ResponsesWebSocketClient` 都不用，直接给路由塞 `UpgradeFailingClient` / `NetworkFailingClient` 这类替身。

所以**今天** `aconnect_ws` 也同样没有测试覆盖 —— 这不是迁移造成的「失去分辨力」，是既有盲区。但 D4 会把「绑定 `self._http`」「把 `client=` 这个 kwarg 去掉」「参数映射」这些新代码搬进那个盲区里，风险量变大了。

一条正面结论：我逐参数比对了 `httpx_ws.aconnect_ws` 与 `httpx2.AsyncClient.websocket` 的默认值，**两个本项目实际会受影响的默认值完全一致**（`queue_size=512`、`max_message_size_bytes=65536`、两个 keepalive 均 20.0），且本项目 `queue_size` 一路显式传（`bootstrap.py:252` 传 `settings.openai_responses.ws_queue_size`，构造器默认 32），不存在默认值静默变化。差异只在 `websocket()` 多了 `params/headers/cookies/auth/follow_redirects/timeout/extensions` 而少了 `client`/`session_class`/`**kwargs` —— 都是我们不传的。**所以 D4 的改法是安全的**，我只建议补一个 loopback echo 的集成用例（生态报告 §2.3 已经跑通过同形态的探针，改造成本很低）。

---

## 逐项回答派单的五个问题

### 1. 覆盖面漏项（对照清单逐节）

| 清单条目 | 计划里有没有对应步骤 | 判定 |
|---|---|---|
| §2.3 `upstream/client.py` `create_http_client`（`Limits`/`Timeout`） | 无显式步骤，仅被步骤 2 隐式覆盖 | **M1**。机械改名够用（签名不变已实测），但 D1 说它不存在 |
| §2.4 `auth/service.py:38` 一次性 client | 无显式步骤，仅被步骤 2 隐式覆盖 | **M1**。同上 |
| §2.2 `httpx._utils.get_environment_proxies` | 步骤 2 显式列了 `httpx._utils` → `httpx2._utils` | **覆盖**。且我实测 `httpx2._utils.get_environment_proxies` 签名 `() -> dict[str, str \| None]` 存在 |
| §9 风险 3 的 `allow_env_proxies` 判定 | 无 | **m1**。我核过，成立 |
| §6.1 三处 `getattr(_, "_request", None)` | 无 | **m1**。我核过，`_request` 仍在 |
| §5.5 cassette 回放机制 | 无显式步骤 | **无漏项**。依赖面是 `MockTransport`/`AsyncBaseTransport`/`AsyncByteStream`/`Request`/`Response` 五个公共类，全部同名平移；匹配判据是请求体 sha256（`cassettes.py:209-229`），不含 header，所以 UA 从 `python-httpx/0.28.1` 变成 `python-httpx2/2.12.0` **不影响匹配**；`rg -c httpx tests/int/cassettes/*.json` 退出码 1，cassette 数据里没有任何包名 |
| §1.2G `tests/unit/test_imports.py` 模块名单 | 步骤 6 提到 | **覆盖，但被误当成 D5 的守卫** → **M3** |
| §5.4 `TestClient` 72 处 | **完全没有** | **B1** |
| §7.2b `extensions["network_stream"]` 探针 | 无 | **无漏项**。我核过 httpcore2 的 `_models.py`、`_async/http11.py`、`_async/http2.py`、`_async/http_proxy.py` 仍然写 `network_stream`；键缺失会 `KeyError`（响） |
| 最小必改清单 15 条 | 计划覆盖第 1、2、5、7、8、9、10、13、15 条 | 第 3、4 条 → M1；第 11 条 → m1；第 14 条已核无风险 |

### 2. 验证充分性

§4 只列 V1、V2 两项。以下断言同样是「换个环境就不成立」，计划打算靠推理放过：

- **V3（应加）：`uv lock` 之后 `httpx` 还在不在、starlette 是哪个大版本。** 这不是推理能回答的问题，取决于解析器当天看到的依赖世界。→ B1、M5。
- **V4（应加）：OTel 迁移后出站 span 还在不在。** 唯一手段是跑一次带 span exporter 的对照，推理只能证明「类名换对了」。→ M3。
- **V5（应加）：truststore 在目标机上握得上手。** 计划把它排到最后 → M4。

**迁移后会静默失去分辨力（照样绿、但不再证明任何东西）的测试，逐一点名**：

- `tests/unit/test_imports.py` —— 对 D5 从来就没有分辨力，而计划把它写成了 D5 的配套改动。它在「instrumentor 用错、trace 全消失」的配置下**照样全绿**。（M3）
- `tests/unit/upstream/test_stream_cap.py` 的结构守卫（`:75,134,145,167,237,243,320` 点名 `pool._requests` 与 `.connection`）—— 计划 D3 自己已经承认了这一条，不重复。
- `tests/unit/server/test_http_client_build.py:137 test_environment_routing_matches_native_httpx` —— **不是失去分辨力，但需要澄清它的射程**。它拿 `httpx.AsyncClient()` 当 oracle，改名后变成 httpx2-vs-httpx2 的同源对照。它能抓住「我们重建的 mounts 把某个 URL 送错地方」，但抓不住「`allow_env_proxies` 变了导致代理被挂两次而路由结果相同」。后半段部分由 `:158 test_no_proxy_rules_share_one_pool`（断言 direct transport 只有一个）兜住。既然 m1 已证明 `allow_env_proxies` 逐字未变，这里没有实际风险，但计划不应把这个测试当作风险 3 的守卫。
- `tests/int/test_responses_ws.py` + `tests/unit/openai/test_responses_ws_transport.py` —— 见 m3。不是新失去，是既有盲区在 D4 之后承载更多新代码。

**反过来，两个我确认迁移后仍然有分辨力的强测试**（不必额外加工，也不该被顺手改弱）：`test_http_client_build.py:314 test_the_keepalive_is_on_the_socket_that_carries_the_request` 及其对照 `:335`（从内核 `getsockopt` 读回 `SO_KEEPALIVE`，带 `tcp_keepalive_interval=0` 的负样本），以及 `:471` 的 CONNECT 隧道版本。它们依赖 `extensions["network_stream"]`，我已确认该契约在 httpcore2 中存活。

### 3. 可回滚性

**判定：计划完全没写回滚，这是缺陷 —— 但缺的不是「回滚手段」，而是「中止判据」和「夹带升级的审查」。** 详见 M5。

没有「回不去」的中间状态：每一步都是可 revert 的语义提交，环境层面 `git checkout pyproject.toml uv.lock && uv sync` 即还原。**但有一个「走不下去」的状态**，就是 B1：步骤 1 完成后到 B1 被裁决之前，`tests/int` 整层无法运行，步骤 8 的全量回归不可达。这个状态不是「回不去」，而是「不知道自己已经走不下去了」—— 因为计划没有在步骤 1 后设置任何检查点。

### 4. `docs/` 归档纪律

按 `.claude/rules/00-development-workflow.md`：

- `docs/tmp/260821-httpx2-api-delta.md`、`260821-httpx-usage-inventory.md`、`260821-httpx2-ecosystem-compat.md` —— **正确**。`YYMMDD-` 前缀、未覆写既有文件、内容是 in-flight 调研。
- `docs/agents/httpx2-migration/plan.md` —— **正确**。`docs/agents/<topic>/` 就是在途开发文档的位置，且它自称活文档，与规约一致。
- `.dev/exp/httpx2-cap-probe/`、`.dev/exp/httpx2-migration/` —— **位置正确**（用户级规约把探针与实验放在 `.dev/exp/`），但**未纳入 `.dev` 的版本控制**，输出未落盘 → m2。
- **该进 live docs 却留在 tmp 的结论：目前没有。** 实施尚未开始，三份 tmp 报告都还是在途调研；计划已经把其中的裁决面（`openai` 的 legacy shim、TLS、GOAWAY、`stream_cap`、WS、OTel）吸收进 `plan.md`。等迁移落地后，`docs/tmp/260821-httpx2-api-delta.md` §5.1 那张「私有面存活性」对照表值得蒸馏进 `src/app/upstream/stream_cap.py` 的模块文档串（那里已经有一段「upgrading httpcore means diffing its source」的自述，正好是它的归宿），否则下一次升级又要从头 diff。这属于建议，不是当前缺陷。

### 5. 事实性断言的支撑逐条核对

| 计划里的断言 | 支撑 | 判定 |
|---|---|---|
| §1 `anthropic==1.0.0` 在 `_base_client.py:1685-1688` 硬性校验 | ecosystem §1.2 + api-delta §7.1，两份独立探针 | ✅ 有支撑 |
| §1 `openai==3.3.1` 留有 legacy shim 且被定性为 temporary | ecosystem §1.1（含 CHANGELOG/PR/migration guide URL） | ✅ |
| §1 公共 API 68 名全重合、28 个异常 MRO 零差异、默认值不变 | api-delta §2、§4.1，探针 | ✅ |
| D1 理由 1「build_http_client 是唯一入口，SDK 与 WebSocket 都吃它」 | **无支撑，且与所引清单 §2.3/§2.4 矛盾；WS 实际吃 `create_http_client`** | ❌ **M1** |
| D1 理由 2「官方迁移指南的原话是 …」 | **来源自称只有摘要；实际原文措辞不同，且该建议被用反** | ❌ **M2** |
| D1 理由 3 httpx2 自 2.6.0 vendored httpx-ws | ecosystem §2.3（CHANGELOG + PR #1042 + 源码行号） | ✅ |
| D3 的两行表 `[6]` / `[2,1,1,1,1]` | `.dev/exp/httpx2-cap-probe/probe_cap.py`，**我复跑，数字一致** | ✅（证据未落盘 → m2） |
| D3「httpcore2 async 侧对 `can_handle_request` 只有这一处外部调用」 | 交由另一位评审员 | — |
| D4 `aconnect_ws` 不在 `httpx2.websockets.__all__` 里 | api-delta §7.5 | ✅ |
| D4 三个异常类同名同继承 | ecosystem §2.3 + api-delta §7.5；我另测 `WebSocketUpgradeError.__init__(self, response)` 与 MRO 一致 | ✅ |
| D5 `HTTPX2ClientInstrumentor` 存在且绑 `httpx2` | ecosystem §3.1（源码行号 + span 对照探针） | ✅ |
| D6「不加上界是延续本项目既有风格（现有依赖全部无约束）」 | **部分不实**：`pyproject.toml:38` 已有 `"cryptography>=50.0.0"` | ⚠️ 措辞需修（不单列为发现，因为它不改变 Q1 的裁决面，另一位评审员在攻上界） |
| §3 步骤 8「预期 pyright 会报新错误：`Headers.get()` 收紧成 `str \| None`」 | api-delta §4.4（CHANGELOG 2.10.0 #1121） | ✅ |
| §3 步骤 7 `aiter_raw` 的 `aclose()` 进了 `finally` | api-delta §4.3，含双版本对照探针输出 | ✅。另：我确认 `rg 'is_closed' tests/` 只命中 `test_upstream_client.py:76`（断言 client 关闭，与本条无关），**没有测试断言了「关生成器不关 response」，所以步骤 7 说的「若有测试断言了旧行为会变红」不会发生 —— 这一条只需改注释** |
| §4 V1 退路「显式传 verify=certifi（需重新声明 certifi 依赖）」 | **D6 的 diff 里没有 certifi，httpx2 已移除该依赖** | ❌ **M4(b)** |

---

## 复现方式

所有命令都从 `/home/xp/src/ghc-api-proxy-py` 显式绑定目录运行，**未修改仓库任何文件**（本报告是唯一新建文件）；依赖解析实验全部在 `/tmp/httpx2-lockprobe-{a1,b1,c1}/` 的一次性 fixture 里做。

```bash
# B1：把仓库真实的 pyproject+uv.lock 复制出去，只施加 D6 的 diff，再重新 lock
#   （已建好：/tmp/httpx2-lockprobe-c1/）
cd /tmp/httpx2-lockprobe-c1 && uv lock && rg -q '^name = "httpx"$' uv.lock; echo "rg exit=$?"   # 1 == httpx 不在依赖图里

# B1：starlette 0.52.1 在 httpx 缺席时的行为
/home/xp/src/ghc-api-proxy-py/.venv/bin/python -c '
import builtins, sys
real = builtins.__import__
def fake(name, *a, **k):
    if name == "httpx" or name.startswith("httpx."): raise ModuleNotFoundError("No module named httpx")
    return real(name, *a, **k)
builtins.__import__ = fake
try: import starlette.testclient
except Exception as e: print(type(e).__name__, ":", str(e).splitlines()[0])'

# M1：WebSocket 客户端的唯一构造点
rg -n 'ResponsesWebSocketClient\(' /home/xp/src/ghc-api-proxy-py/src/
rg -n 'responses_ws|ResponsesWebSocketClient' /home/xp/src/ghc-api-proxy-py/src/app/server/composition.py

# m1：两条被计划省略的风险，在 httpx2 下是否成立
SP=$(echo /home/xp/.claude/jobs/ca953617/tmp/latest-venv/lib/python*/site-packages)
rg -n 'allow_env_proxies = ' "$SP/httpx/_client.py" "$SP/httpx2/_client.py"
/home/xp/.claude/jobs/ca953617/tmp/latest-venv/bin/python -c 'import httpx2; print(hasattr(httpx2.Response(200), "_request"))'

# m2：复跑 D3 探针
/home/xp/.claude/jobs/ca953617/tmp/latest-venv/bin/python /home/xp/src/ghc-api-proxy-py/.dev/exp/httpx2-cap-probe/probe_cap.py

# m3：两个 WebSocket 入口的参数默认值对照
/home/xp/.claude/jobs/ca953617/tmp/latest-venv/bin/python -c '
import inspect, httpx2
from httpx_ws import aconnect_ws
a = inspect.signature(aconnect_ws).parameters; b = inspect.signature(httpx2.AsyncClient.websocket).parameters
for n in sorted(set(a) | set(b)):
    print(n, a[n].default if n in a else "<ABSENT>", "|", b[n].default if n in b else "<ABSENT>")'
```

`/tmp/httpx2-lockprobe-{a1,b1,c1}/` 三个 fixture 我留着未删，供你复核；确认后可以直接删掉。

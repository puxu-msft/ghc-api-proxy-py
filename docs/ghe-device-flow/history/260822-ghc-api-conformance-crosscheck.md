# `ghc-api.md` 一致性核查 —— 独立交叉复核

日期：2026-08-22
复核对象：`.dev/docs/tmp/260822-ghc-api-conformance-{auth,baseurl,direct-paths,responses-ws}.md` 四份报告
权威文档：`docs/.human-controlled/ghc-api.md`（用户亲笔）
基线 HEAD：`a68672c`（主树有同伴未提交改动；`docs/.human-controlled/*` 处于已暂存未提交状态）
方法：不采信任何报告的转述，逐条自己读代码 + 写一次性探针实测。全程只读，未修改、未暂存、未提交任何仓库文件。探针脚本落在 `/home/xp/.claude/jobs/104f3935/tmp/`。

## 判定总表

| # | 主张 | 出处 | 判定 | 依据 |
|---|---|---|---|---|
| 1 | 生产唯一入口是 `app.cli:main → create_pipeline_app` | baseurl / direct-paths / ws | **证实** | 第 1 节 |
| 2 | `app_factory.create_app` 已无生产调用者 | baseurl / direct-paths / ws | **证实** | 第 1 节 |
| 3 | 「`app_factory.py:104-105` 是真实生产接线」 | auth 第 4 节 (a) | **推翻** | 第 1、2 节 |
| 4 | `CopilotTokenManager.run_refresh_loop` 在生产路径上未接线 | 四份都没查 | **新发现，证实** | 第 2 节 |
| 5 | 新链路构造 `GhcClientConfig` 从不传 `account_type`，恒为 individual | baseurl | **证实** | 第 3 节 |
| 6 | 新 schema `ModelProviderConfig` 无 `account_type` 字段 | baseurl | **证实（实测）** | 第 3 节 |
| 7 | `infer_account_type` 只挂在 legacy 上 | baseurl | **证实** | 第 3 节 |
| 8 | `--account-type` 是「静默失效」 | 任务提问 | **推翻（standalone 路径）／证实（`--fd` 路径）** | 第 4 节 |
| 9 | `--ghc-api-base-url` 完全静默失效，写错字段名 | 四份都没查 | **新发现，证实（实测）** | 第 5 节 |
| 10 | `config.example.yaml:159` 的 `base_url` 会被 `extra_forbidden` 拒绝 | baseurl | **证实（实测复现）** | 第 6 节 |
| 11 | `auth_base_url` / `account_type` 在用户 yaml 里无文档 | 任务提问 | **证实** | 第 6 节 |
| 12 | 文档 L5 说的子模块 `auth` 承担的两件事，实际都不在 `auth/` 下 | 四份都没查 | **新发现，证实** | 第 7 节 |
| 13 | `/chat/completions` 流式攒不出 block | direct-paths（标为「强证据、未运行时验证」） | **升级为证实（组件级实测 + 正样本对照）** | 第 8 节 |
| 14 | `responses_ws` 已实现但未接线，与 2026-08-16 裁决一致 | ws | **证实** | 第 9 节 |
| 15 | `verification/phase3_acceptance.py` 是项目内的陈旧产物 | ws 第 5 节第 1 项 | **推翻（前提有偏差：该文件未被版本控制跟踪）** | 第 9 节 |
| 16 | self-hosted 一档在当前生产链路上完全不可达 | 无人得出（baseurl 只推到一半） | **新发现，证实** | 第 10 节 |

---

## 1. 主线核查：生产入口到底有几个

**证实，且比报告说得更干净。**

进程入口只有一个函数：

- `pyproject.toml:55` — `ghc-api-proxy = "app.cli:main"`
- `src/app/__main__.py:1-4` — `from app.cli import main`，即 `python -m app` 与 console script 是同一个 `main`
- 部署形态全部走 `python -m app`：`contrib/systemd/ghc-api-proxy.service:23`（`-m app start --fd 3 --graceful-timeout 300`）、`contrib/systemd/install-user.py:78`、`Dockerfile:28`（`python -m app start`）

**app 工厂只有一个，serve 路径有两条**：

| serve 路径 | 位置 | 触发条件 |
|---|---|---|
| standalone | `src/app/cli.py:176`（`_serve_pipeline` → `run_standalone`） | `start` 不带 `--fd` |
| 继承 listener | `src/app/cli.py:151`（`serve_inherited`） | `start --fd N`，systemd 单元用的就是这条 |

两条都调 `create_pipeline_app(chain)`。全仓库 `create_pipeline_app` 的调用点只有：`src/app/cli.py:151,176`、`tests/int/test_pipeline_app.py`、`tests/e2e/claude/_harness.py:100`。

**`create_app` 的全部调用者**（`rg -n "create_app|app_factory"` 全仓扫描）：`tests/int/` 下十余个文件，加上 `verification/phase3_acceptance.py:217,226`。**src/ 下零个生产调用者**。`src/app/server/__init__.py:6-13` 刻意不 re-export 它，`tests/unit/test_module_boundaries.py:42` 还有一条 `assert "app.server.app_factory" not in new_chain` 的守卫。

判定：**证实**。三份报告的主线成立，不会连带作废任何结论——除了 auth 报告自己的那一条。

## 2. 推翻 auth 报告第 4 节 (a)，以及由此暴露的真实缺口

auth 报告写：

> **(a) 服务器运行时路径（真正对外提供 HTTP 服务的入口）** …… `src/app/server/app_factory.py`（FastAPI `_lifespan`，51-140 行）
> **接线**：`src/app/server/app_factory.py:104-105` …… 是真实生产接线（而非仅测试构造）。

**推翻。** 依据即第 1 节：`app_factory.create_app` 在 src/ 下无任何调用者。它构造的 `_lifespan` 在生产中永不执行。

这不是措辞问题，它盖住了一个真实缺口。`run_refresh_loop`（`CopilotTokenManager` 那个）全仓库唯一调用点就是 `src/app/server/app_factory.py:105`：

```
$ rg -n "run_refresh_loop" src/
src/app/server/app_factory.py:105:  task_group.start_soon(services.copilot_tokens.run_refresh_loop)
src/app/upstream/models_api.py:64:  async def run_refresh_loop(     ← 另一个类，非本条
src/app/model_provider/ghc_client/tokens.py:89:  async def run_refresh_loop(   ← 定义
```

而生产链路的 `build_chain`（`src/app/server/composition.py:411-416`）造出 `CopilotTokenManager` 之后，既不启动 `run_refresh_loop`，也不调用 `ensure_valid_token()`。对比 legacy 的 `src/app/upstream/bootstrap.py:177` 是在启动时就 `await copilot_tokens.ensure_valid_token()`。

两个后果，权重分开说：

- **后果 A（降级，不是中断）**：生产路径上没有主动后台刷新，只剩 `tokens.py:76-80` `get_token()` 的懒刷新兜底。正确性不破——`_is_valid()` 用 60 秒 `validity_margin` 提前判失效，兑换是同步完成的。代价是每次 token 到期由某个倒霉的真实请求承担一次兑换往返，兑换失败则该请求直接失败而非后台重试（`tokens.py:98-103` 的「失败不终止循环」保护在这条路径上不存在）。**足以据此行动**：这是可观测的行为差异，不是理论风险。
- **后果 B**：启动期凭据校验在新链路上没有对应物，凭据坏掉要到第一个真实请求才暴露。

顺带证实 auth 报告 (c) 的结论：`composition.py:337-345` 的 provider 链只有 `CLITokenProvider(None)` / `EnvTokenProvider()` / `FileTokenProvider(...)`，`DeviceAuthProvider` 确实是孤儿。注意 `CLITokenProvider(None)` 是写死的 `None`，与 `_NO_HOME_IN_SPEC` 里 `--github-token` 无处安放一致。

## 3. base URL 恒为 individual —— 证实

三段证据各自独立：

1. `src/app/server/composition.py:357-360` 与 `407-410` 两处构造 `GhcClientConfig`，只传 `api_base_url_override` / `auth_base_url_override`，均不传 `account_type`；`src/app/model_provider/ghc_client/config.py:23` 默认 `account_type: AccountType = "individual"`。
2. `ModelProviderConfig`（`src/app/config/schema.py:83-127`）字段清单：`type` / `api_base_url` / `auth_base_url` / `github_token_file` / `model_refresh_interval` / `disabled_models` / `models_support_web_search`。无 `account_type`。实测传入该键 → `ValidationError: model_providers.ghc.account_type ... extra_forbidden`（`Section` 是 `frozen=True, extra="forbid"`，schema.py:55-56）。
3. `infer_account_type` 的全部引用：定义 `account.py:13`、re-export `ghc_client/__init__.py:14,49`、调用 `src/app/upstream/bootstrap.py:183`、测试 `tests/component/model_provider/ghc_client/test_account.py`。`bootstrap.py` 只被 `app_factory.py` 调用（第 1 节已证其非生产）。

判定：**证实**。「如未配置，根据用户订阅自动识别选择」（`ghc-api.md:19`）这条需求在当前生产链路上不成立，实际行为是恒为 individual。

## 4. `--account-type` 是不是静默失效 —— 分两条路径，答案不同

**standalone 路径：推翻「静默」。** 项目已经明确处理过这件事：

- `src/app/cli.py:73-78` `_NO_HOME_IN_SPEC` 逐条列出 `AppSettings` 有而 `ProxyConfig` 没处放的选项，`--account-type` 的理由写着 `config.example.yaml has no 'auth' section`，上面还有一段注释说明「用户 2026-08-17 裁定入口切换带着这些不生效项前进，逐条点名就是为了不让『暂时不生效』变成『悄悄没了』」。
- `cli.py:116-124` 收集，`cli.py:320-323` 打印 `warning: --account-type has no effect on this path — ...`，注释原话：「an option that is accepted and then ignored is worse than one that is refused」。

实测（`probe2.py`）：`_load_spec_config(..., account_type=ENTERPRISE, ...)` 返回的 `inactive` 为 `[('--account-type', 'config.example.yaml has no `auth` section')]`。所以在 `start` 不带 `--fd` 时，用户会看到警告。**这是一个被记录在案的已裁决降级，不是静默失效。**

**`--fd` 路径：证实「静默」。** `src/app/cli.py:289` 写的是：

```python
proxy_config, _ = _load_spec_config(
```

`inactive` 被丢弃，`return` 在 304 行，根本到不了 320-323 的打印循环。而 `contrib/systemd/ghc-api-proxy.service:23` 的 `ExecStart` 正是 `-m app start --fd 3`——**唯一的正式部署形态恰好走在不打印警告的那条腿上**。

判定：**推翻（standalone）／证实（`--fd`）**。这条不对称是四份报告都没提的，值得单独修（把 `_` 换成 `inactive` 并复用同一个循环即可，成本极低）。

## 5. 新发现：`--ghc-api-base-url` 完全静默失效（本次最高影响）

`src/app/cli.py:126-137`：

```python
if ghc_api_base_url is not None:
    name = config.default_model_provider
    providers = dict(config.model_providers)
    if name in providers:
        providers[name] = providers[name].model_copy(update={"base_url": ghc_api_base_url})
```

**`update` 的 key 是 `base_url`，而 `ModelProviderConfig` 的字段是 `api_base_url`（`schema.py:86`）。** pydantic 的 `model_copy(update=...)` 不做校验，直接往 `__dict__` 塞。实测（`probe1.py` D 段）：

```
q.api_base_url = ''
getattr(q,'base_url') = 'https://cli.example'      ← 幽灵属性
q.model_dump() 里没有 base_url
```

端到端实测（`probe2.py`），同时给 `--ghc-api-base-url https://api.enterprise.githubcopilot.com` 与 `--account-type enterprise`：

```
inactive warnings    : [('--account-type', 'config.example.yaml has no `auth` section')]
pc.api_base_url      : ''
phantom pc.base_url  : 'https://api.enterprise.githubcopilot.com'
GhcClientConfig.account_type : individual
RESOLVED API BASE URL: https://api.githubcopilot.com
```

而 `composition.py:358` 读的正是 `provider_config.api_base_url`。所以这个 CLI 选项**被接受、无任何警告、然后完全不生效**——正是 `cli.py:321` 那句注释所说的「比拒绝更糟」的形态，只不过它自己没被那张清单收进去（因为写这段代码时字段名还叫 `base_url`，它当时是对的）。

成因可考：

- `cli.py:126-137` 这段来自 `52b01a2 feat: serve the direct-run path from the spec's ProxyConfig`，当时 schema 字段就叫 `base_url`。
- `a8a7f87 feat: make both upstream hosts configurable...`（2026-08-19）把它改名成 `api_base_url`，提交信息原话：「Named by the user: `api_base_url` is where inference goes ... The first is a rename of `base_url`」。`git show --stat a8a7f87` 显示该提交**只动了 `src/app/config/schema.py`**（在本次相关的三个文件里），`cli.py` 没跟上。

现存测试为什么没抓到：`tests/unit/test_cli.py:62-81` 只断言 `--ghc-api-base-url` 这个字符串出现在 `start --help` 的输出里，不覆盖任何行为。

**合并推论（比 baseurl 报告的结论更严重）**：baseurl 报告判定「`api_base_url` override 是当前唯一能让 base URL 偏离 individual 的手段」。加上本节，实际是——**唯一手段是在 YAML 里手写 `model_providers.<name>.api_base_url`，而这个拼写在用户亲笔的 `config.example.yaml` 里根本不存在**（第 6 节）。CLI 那条腿是坏的。

## 6. `config.example.yaml` 键名与字段文档化情况

实测（`probe1.py`，`uv run --no-sync python`，`PYTHONPATH=src`）：

| 输入键 | 结果 |
|---|---|
| `base_url` | `ValidationError: model_providers.ghc.base_url — Extra inputs are not permitted [type=extra_forbidden]` |
| `api_base_url` | 接受，值正确落到 `ModelProviderConfig.api_base_url` |
| `account_type` | `ValidationError: model_providers.ghc.account_type — extra_forbidden` |

复现了 baseurl 报告第 18 行的结论：**证实**。取消 `docs/.human-controlled/config.example.yaml:159` 那行注释会让配置加载直接失败，不是「被忽略」。

**字段文档化核查**（`rg -n "base_url|account_type|github_token" docs/.human-controlled/config.example.yaml` 全部命中）：

```
159:    # base_url: "https://api.githubcopilot.com"
166:    github_token_file: "$XDG_DATA_HOME/ghc-api-proxy/github_token.txt"
```

- `auth_base_url`：**用户 yaml 里完全没有**。而它在代码里不是可选装饰——`schema.py:87-91` 的注释说明企业部署会同时移动两个 host，且它是本地起链路的必要条件；`NOT_HOT_RELOADABLE`（`schema.py:39-41`）也已把 `model_providers.*.auth_base_url` 列进去。文档缺一个已实装且被裁定为「需重启」的键。
- `account_type`：**没有**，与第 3 节一致。
- `models_support_web_search`：本次未逐字核，不在 `ghc-api.md` 范围内。

**方向不代裁。** 值得注意的是 a8a7f87 的提交信息自称改名是「Named by the user」，若属实则 `api_base_url` 才是用户的较新裁决、`config.example.yaml:159` 的 `base_url` 是陈旧残留；但那份 yaml 是用户亲笔文档，孰新孰旧只有用户能定。我只报事实：两边现在对不上，且以任一边为准都需要动另一边。

## 7. 新发现：文档说的子模块 `auth` 与实际目录不符

`ghc-api.md:5-8`：

> 子模块 `auth` 负责认证逻辑，主要包括：1. 使用 device code 流程获取 github_token 2. 使用 github_token 换取 copilot_token

实际目录（`fd -HI . src/app/model_provider/ghc_client --type f`，去掉 `__pycache__`）：

```
ghc_client/auth/__init__.py
ghc_client/auth/providers.py      ← github_token 的来源链
ghc_client/auth/service.py        ← 交互式登录/登出编排
ghc_client/device_flow.py         ← 第 1 件事，在顶层
ghc_client/tokens.py              ← 第 2 件事，在顶层
ghc_client/{account,client,config,errors,headers,models,transport}.py
```

**用户点名归属 `auth` 的两件事，一件都不在 `auth/` 下。** git 历史确认这个包自诞生（`b9939ca refactor: move app.auth under app.ghc_client`）就只有 `__init__.py` / `providers.py` / `service.py` 三个文件，不是最近搬走的。

auth 报告第 3 节详细写了 `providers.py` 与 `service.py` 的职责边界、并正确地把 `device_flow.py` / `tokens.py` 的路径逐字写了出来，但没有把这个路径与文档 L5 的归属声明对照一次——**四份报告都没有**。

判定：**证实（结构不符）**。功能上两件事都实现了，是组织形态与用户亲笔描述不一致。改哪边（把两个文件挪进 `auth/`，还是改文档措辞）归用户裁决。权重：**足以据此行动的事实，但优先级低于第 2、5 节**。

## 8. `/chat/completions` 流式 —— 把推断升级为实测

direct-paths 报告第 5 节把「块级组装很可能一个 block 都攒不出来」标为「强证据、未运行时验证」。我做了组件级实测，**升级为证实**。

先确认派发链：`src/app/server/handler.py:517-524` `assembler_for` 只按 `dialect_for` 二选一；`handler.py:488-500` `dialect_for` 只在 `target_format is WireFormat.OPENAI_RESPONSES` 时返回 `RESPONSES`，其余（含 `OPENAI_CHAT_COMPLETIONS`）一律 `ANTHROPIC`。docstring 自己写明「anything that is not a Responses upstream is assembled as Anthropic」。

实测（`probe4.py`）：

```
AnthropicAssembler blocks from chat.completion.chunk stream: 0 []
CONTROL AnthropicAssembler blocks from real anthropic stream: 1
```

正样本对照在场：同一个 assembler 吃真 Anthropic 帧产出 1 个 block，吃 4 帧 `chat.completion.chunk`（含 role 帧、两个 content delta、finish_reason 帧）产出 0 个。所以「0」是判据有分辨力下的真结果，不是探针没跑起来。

再确认没有兜底：`src/app/pipeline/delivery/stream.py:241-263` 是下行字节的唯一来源——`assembler.push()` 出块才 `yield chunk`，否则只可能 `yield PING_FRAME`；整个函数没有原样透传上游字节的分支。

判定：**证实**。`/chat/completions` 走流式时客户端拿不到任何内容块。范围限定：这证明的是 assembler 层 + 派发层，我没有起真服务端到端跑一遍，也没验证在什么配置下 `target_format` 真会落在 `OPENAI_CHAT_COMPLETIONS`——后者是这条风险是否真的可达的最后一环，标**存疑**（要定它，需要一份声明 `/chat/completions` 且不声明 `/responses` 的模型目录，或一条直接 POST `/chat/completions` 的端到端用例）。direct-paths 报告已证该端点在生产集成测试里零覆盖。

## 9. responses_ws —— 证实，但有一条前提要更正

**证实**：`create_pipeline_app`（`pipeline_app.py:699`）挂载的路由全部来自 `build_router()` / `ops_router`，`rg -n "websocket" src/app/server/pipeline_app.py src/app/server/inbound.py` 只命中 `pipeline_app.py:311,313` 两处读 ASGI scope 的代码，**没有任何 `@router.websocket` 或 `responses_ws_router` 的 import**。`responses_ws_router` 只在 `app_factory.py:35,177` 挂载，而 `app_factory` 非生产（第 1 节）。与 2026-08-16 裁决一致。

**更正一条前提**：ws 报告第 5 节把 `verification/phase3_acceptance.py` 列为「陈旧候选清单」第 1 项并逐行分析。该文件**不在版本控制里**：

```
$ git ls-files --error-unmatch verification/phase3_acceptance.py
error: pathspec ... did not match any file(s) known to git
Did you forget to 'git add'?
```

`git status` 里它是 `?? verification/phase3_acceptance.py`，同批还有 `?? verification/PHASE3_ACCEPTANCE_REPORT.md`。`verification/final_acceptance/` 那半边则是跟踪的（含 ws 报告列的第 2 项 `probes/04_responses_websocket.py`）。判定：**推翻（前提有偏差）**，影响低——它不改变「这份脚本已陈旧」的技术判断，但改变处置方式：一个未跟踪文件很可能是同伴的在途工作，不该按「清理仓库陈旧代码」处理。ws 报告对第 2、3、4 项的判断我没有理由质疑。

## 10. 新发现：self-hosted 一档在当前生产链路上完全不可达

把前面几节合起来推：

- `resolve_api_base_url`（`config.py:39-48`）对 `self-hosted` 不派生任何默认值，`config.py:43-45` 直接 `raise ValueError("self-hosted accounts require an explicit api_base_url_override")`。
- 但新链路根本传不进 `account_type`（第 3 节），所以这个分支本身不可达；剩下的唯一出路是 `api_base_url_override`。
- 而 `api_base_url_override` 的两个来源：YAML 键 `api_base_url`（用户亲笔 yaml 里不存在，第 6 节）与 CLI `--ghc-api-base-url`（坏的，第 5 节）。

结论：`ghc-api.md:17` 那行 self-hosted `msft.ghe.com`，以及 business/enterprise 两行，**在当前生产链路上没有任何一条用户可见的配置通道能到达**。baseurl 报告只推到「business/enterprise 语义化选择不可达，只能自己拼完整 URL」，它假定拼完整 URL 这条路是通的——加上第 5 节，那条路目前也只剩一个未文档化的 YAML 拼写。判定：**证实**，权重**足以据此行动**。

## 共同盲区汇总（对照 `ghc-api.md` 逐句）

| `ghc-api.md` 位置 | 内容 | 谁查了 | 补充 |
|---|---|---|---|
| L3 | 模块位于 `app.model_provider.ghc_client` | direct-paths（间接） | 成立 |
| L5-8 | 子模块 `auth` 负责两件认证事 | auth（查了功能，**没查归属**） | 第 7 节补上 |
| L10-17 | 四档账户类型 → 四个 base URL | baseurl | 第 5、10 节补上「配置通道是否可达」 |
| L19 | 未配置则自动识别 | baseurl | 证实不成立 |
| L25 | `/v1/messages` + `count_tokens` | direct-paths | 无补充 |
| L26 | `/chat/completions` | direct-paths | 第 8 节升级为实测 |
| L27 | `/responses` | direct-paths | 无补充 |
| L28 + L31 | `ws:/responses` 暂不支持、不最终接线 | ws | 第 9 节更正一条前提 |
| L29 | `/embeddings` | direct-paths | 无补充 |
| —（跨条） | 上游凭据的运行期维持 | **无人** | 第 2 节：`run_refresh_loop` 未接线 |
| —（跨条） | CLI 选项与新 schema 的接线完整性 | **无人** | 第 5 节：`--ghc-api-base-url` 静默失效；第 4 节：`--fd` 路径吞掉警告 |

## 存疑项（证据不足以定论，附「要什么才能定」）

1. **`/chat/completions` 风险的可达性**：第 8 节证了 assembler 层必然 0 block，但没证在什么配置下 `route.target_format` 真会是 `OPENAI_CHAT_COMPLETIONS`。要定它：读一遍 `route_policy` 对只声明 `/chat/completions` 的模型如何选目标，或直接补一条 POST `/chat/completions` 且 `stream: true` 的集成用例。
2. **`--github-token` 在新链路**：`composition.py:340` 写死 `CLITokenProvider(None)`，与 `_NO_HOME_IN_SPEC` 的声明一致，属已裁决的不接线，不是新问题。但我没核 `github_token_path()` 在新链路上的实际解析结果是否与 `config.example.yaml:166` 的 `$XDG_DATA_HOME/ghc-api-proxy/github_token.txt` 一致。要定它：一条读实际路径的探针。
3. **`config.example.yaml` 与 schema 谁该改**：a8a7f87 的提交信息自称改名「Named by the user」，但那是提交信息的自述，不是用户在场的裁决记录。要定它：问用户。

## 建议的处置顺序（按影响，不代裁）

1. `cli.py:132` 的 `base_url` → `api_base_url`（第 5 节）。一行，且当前无任何测试会挡住这次修改，建议同时补一条断言 `pc.api_base_url` 的行为测试。
2. `cli.py:289` 的 `proxy_config, _ =` 改成接住 `inactive` 并复用 320-323 的打印（第 4 节）。systemd 部署形态目前收不到任何「选项不生效」的警告。
3. 生产链路补 `run_refresh_loop` 与启动期 `ensure_valid_token`（第 2 节），或明确记录「懒刷新是既定设计」并说明为何不需要后台循环。
4. `config.example.yaml` 的 `base_url` / 缺失的 `auth_base_url` / 是否恢复 `account_type`（第 6、10 节）——需用户裁决后再动，因为那是用户亲笔文档。
5. 文档 L5 的 `auth` 子模块归属（第 7 节）——需用户裁决改哪边。

---

附：探针脚本 `/home/xp/.claude/jobs/104f3935/tmp/probe{1,2,4}.py`，均为只读，不 import 任何写路径。运行方式 `PYTHONPATH=src uv run --no-sync python <script>`。

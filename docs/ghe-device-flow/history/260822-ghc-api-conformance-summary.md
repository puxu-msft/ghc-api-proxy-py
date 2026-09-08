## 用户裁决与落地情况（2026-08-22 下午追记）

用户就本文的发现下了四条裁决，均已实现。逐条对照：

| 裁决 | 落地 | 提交 |
|---|---|---|
| `/chat/completions` 暂时实现为一次性交付，块级边界解析留待未来 | `delivers_blocks` 判定客户端腿有无出站成帧器；chat-completions 没有，其流被 `one_shot_delivery` 整段缓冲后原样转发。实测由 0 字节变为完整 SSE（含 `data: [DONE]`） | `2769a64` |
| 不新增 `account_type` 配置项，只保留「自动识别」与「手写完整 base URL」两条路 | `resolve_provider_base_urls` 在两条 serve 路径与 `debug models` 上探测订阅并推导 base URL；`build_chain` 保持同步；schema 未新增字段 | `b92d4ce` |
| 删除 `--ghc-api-base-url` | 连同 `_load_spec_config` 的参数与两处传参一并删除，`--help` 测试加了否定断言防回流 | `3a05fb0` |
| 既然有懒刷新，移除 copilot token 后台刷新循环 | 删 `run_refresh_loop`、`next_refresh_delay`、`minimum_refresh_interval` 与 `refresh()` 的 `force`；`_sleep` 保留（兑换退避仍用）；两个循环测试改写为懒刷新路径的失败测试 | `eb74a60` |

裁决过程中新查实一条同源缺陷并一并修复：**直连 `/responses` 流式也输出了 Anthropic 事件名**。用户选定「给 Responses 出站写块级成帧」而非一次性交付，落地为新模块 `responses_sse.py` 与一个 `OutboundFramer` 协议，选择器按 `route.inbound_format`（客户端腿）而非 `dialect_for`（上游腿）——后者会让主产品路径开始向 Claude Code 发 `response.*`。提交 `ebb2fec`、`630f7f3`。

因此本文「逐条判定」表中第 5、6、8、11 行与发现 F1、F2、F3 已不再是现状，保留作为记录；第 7 行（`msft.ghe.com` 文档措辞）随裁决 2 一并解决——self-hosted 现在走「手写完整 URL」这条路。用户已自行把 `config.example.yaml:159` 的 `base_url` 改为 `api_base_url`（F2 第 3 点）。

仍然开放：F4（`--fd` 分支吞掉选项无效警告）、F5（`DeviceAuthProvider` 孤儿）、F6／D6（`auth` 子模块目录归属）、D3（count_tokens 文档措辞）、D5（ws 陈旧候选四项）。

本轮实现经独立评审（`260822-four-rulings-implementation-review.md`，用变异法验证了鉴别力：把 `framer_for` 换成 `dialect_for` 会让两条 int 测试变红，`output_index` 改回 `block.index` 会让 SDK 自己抛 `IndexError`）。0 blocker、4 条 major，处置如下：

- **已修**（`db6f549`）：`response.function_call_arguments.done` 缺 SDK 必填的 `name`、两个 `output_text` 事件缺 `logprobs`——这层缺失在原 oracle 下不可见（SDK 的 `construct_type` 宽松构造不校验），现补了一条逐事件对账必填字段的测试，并验证了它摘掉字段就变红。
- **已修**（`db6f549`）：两处不实陈述——`_reasoning` 自称照三份录制抄，实际只有两份带 reasoning item 且 `summary` 全为空；一次性交付路径自称「以同样方式收尾」，实际守卫触发时写不出错误帧。均改为如实描述并登记。
- **已修**（`db6f549`）：`incomplete` 这个我方词汇不再透传进 `incomplete_details.reason`。
- **用户裁决后实现**（`44fa576`）：启动期探测失败的处置改为「401/403 上抛、其余 HTTP 状态与传输类失败记 warning 后继续」。理由是 socket activation 下旧进程已交出 listener，因一次 GitHub 抖动起不来是服务中断而非维持现状。

新增待裁一条：本仓库没有带 `function_call` 的 Responses 流式录制，`responses_sse.py` 里那组帧与 reasoning 的 `summary_text` 形状都是据 SDK 类型推导的；补录需要凭据并发真实上游请求，未擅自执行。评审另列 9 条 minor 与 4 条 nit，未逐条处理，详见评审报告。

---

# `ghc-api.md` 需求符合性总评

日期：2026-08-22
对照权威：`docs/.human-controlled/ghc-api.md`（用户亲笔，最高权威）

**两套基准，分开记：**

- **代码侧**判定锁定在提交 `51196e2`。分析期间同伴把 HEAD 从 `fa628e1` 一路推到 `8f654b4`，中途工作树里还有未提交的在途改动；下文所有代码结论都以 `51196e2` 的提交态为准，不采信工作树的叠加态。少数几处行号会随同伴提交漂移的，改为按符号名引用。
- **需求侧**引用的是 `docs/.human-controlled/ghc-api.md` 的**工作树版本**。该文件目前已暂存但**尚未提交**（`git status` 显示 `AM`），在 `51196e2` 里并不存在——用户正在亲笔写它。因此所有 `ghc-api.md:Lnn` 只对当前工作树版本成立，行号会随用户继续编辑而变。

分项报告（原始记录，其中的行号是各自成文时刻的快照，勿回头改写）：

- `260822-ghc-api-conformance-auth.md`
- `260822-ghc-api-conformance-baseurl.md`
- `260822-ghc-api-conformance-direct-paths.md`
- `260822-ghc-api-conformance-responses-ws.md`
- `260822-ghc-api-conformance-crosscheck.md`（独立交叉复核，推翻了上面几份的 3 条主张）
- `260822-chat-completions-block-delivery-probe.md`（运行时探针，跑在 `a68672c` + 工作树叠加态上）
- `260822-ghc-api-conformance-summary-review.md`（对本文的独立评审，本文已按其修订；未采纳项见文末）

## 一句话结论

**骨架满足，接线有洞。** 文档要求的模块划分、五个上游端点、四个驱动模块全部实现且名字对得上；但有四处「代码写对了、生产链路却够不着」——新配置 schema 里 `account_type` 字段整个不存在（这是 L14-L19 那张账户类型表在生产上只剩第一行成立的根因）、订阅自动识别只挂在 legacy 链路、`--ghc-api-base-url` 选项是静默空操作、copilot token 后台刷新循环没接线；另有一处是必需直连路径上的实打实缺陷——`/chat/completions` 流式向客户端交付 0 字节。

## 逐条判定

| # | 需求原文（`ghc-api.md` 工作树版行号） | 判定 | 依据（`51196e2` 提交态） |
|---|---|---|---|
| 1 | 模块位于 `app.model_provider.ghc_client`，「从抽象接口的不同模型请求格式的入口接入，构造最终上游模型请求」（L3） | **满足** | 模块位置：`src/app/model_provider/ghc_client/` 实际存在（`__init__.py`、`client.py`、`auth/` 等）。抽象接口：`ModelProvider` 协议 `model_provider/base.py:16-63`；实现 `model_provider/github_copilot.py:43-191`；端点→发送方法分派表 `github_copilot.py:32-37` |
| 2 | 子模块 `auth`：device code 流程获取 github_token（L7） | **功能满足，目录归属需裁决** | 流程完整含 `authorization_pending`／`slow_down`／过期三分支：`ghc_client/device_flow.py:51-88`；生产入口是 CLI `auth`／`login`：`cli.py:348-357` → `ghc_client/auth/service.py:33-40`。**但文件在 `ghc_client/` 顶层，不在 `ghc_client/auth/` 下**——见 F6 |
| 3 | 子模块 `auth`：github_token 换 copilot_token（L8） | **部分满足** | 兑换与刷新实现完整：`ghc_client/tokens.py:36-160`。**但后台刷新循环没接到生产链路上**——见 F3。目录归属同 F6 |
| 4 | `individual` → `api.githubcopilot.com`（L14） | **满足** | `ghc_client/config.py:6,46-47`，逐字符一致，且是当前唯一实际生效的默认分支 |
| 5 | `business` → `api.business.githubcopilot.com`（L15） | **URL 值可达，语义选择不可达** | 拼接式 `config.py:48` 写法正确。客户端**能**打到这个 URL——在 YAML 里写 `model_providers.<name>.api_base_url: "https://api.business.githubcopilot.com"` 实测生效。不可达的是「按账户类型 `business` 推导出该 URL」这条语义通道：`config.py:48` 那个分支在生产上永远进不去。见 F2 |
| 6 | `enterprise` → `api.enterprise.githubcopilot.com`（L16） | 同上 | 同上（实测已用 enterprise URL 复现过 YAML 通道可达） |
| 7 | self-hosted → `msft.ghe.com`（L17） | **与文档字面不符（但代码的做法更合理）** | `config.py:43-45` 对 self-hosted 直接 `raise ValueError`，要求显式给出 URL；`msft.ghe.com` 只作为注释举例出现。GHES 域名各企业不同、无法推导——**建议改文档而不是改代码**，见裁决点 D1 |
| 8 | 「如未配置，根据用户订阅自动识别选择」（L19） | **未满足（已实现，未接线）** | 探测逻辑存在：`ghc_client/account.py:7-21`（读 `/copilot_internal/user` 的 `copilot_plan`／`access_type_sku`）；唯一调用点在 legacy 链路 `upstream/bootstrap.py:180-189`。生产链路 `composition.py:357-360,407-410` 构造 `GhcClientConfig` 时从不传 `account_type`，恒取 dataclass 默认值 `"individual"`（`config.py:23`）——未配置时**静默固定为 individual，既不探测也不报错** |
| 9 | `POST /v1/messages` → `direct_driver.anthropic_messages`（L25） | **满足** | 驱动 `direct_driver/anthropic_messages.py:15`；上游 URL 字面量 `client.py:141`；接线 `direct_driver/__init__.py:48`（`DRIVERS`）→ `server/handler.py:150` → `server/inbound.py:34`（`ROUTES`）→ `pipeline_app.build_router()`；生产集成测试断言真实上游 URL |
| 10 | `POST /v1/messages/count_tokens` → `direct_driver.anthropic_messages`（L25） | **功能满足，归属与兜底与文档有出入** | 直连实现 `client.py:148-154`（字面量 `/v1/messages/count_tokens`）。但它走独立方法 `github_copilot.py:176-191`，**不经过 `AnthropicMessagesDriver`**；且仅当路由目标是 Anthropic 时才直连，路由到 Responses 时退化为 `app/tokenization` 本地估算（`handler.py:280`）。见裁决点 D3 |
| 11 | `POST /chat/completions` → `direct_driver.openai_chat_completions`（L26） | **非流式满足；流式不满足（交付 0 字节）** | 驱动与接线齐备，非流式实测逐字节正确；流式返回 200 + `text/event-stream` + **空 body**，且不发任何错误帧。见 F1 |
| 12 | `POST /responses` → `direct_driver.openai_responses`（L27） | **满足** | 驱动 `direct_driver/openai_responses.py:15`；URL `client.py:165`；有专属 `ResponsesAssembler` 与流式块级交付的生产集成测试 |
| 13 | `ws:/responses` 暂不支持（L28） | **满足（与裁决一致）** | `ModelEndpoint.OPENAI_RESPONSES_WS` 作为「已知但不驱动」保留：`model_provider/types.py:18`；发送表刻意排除并注明理由：`github_copilot.py:31-37`；不可驱动时抛 `EndpointNotImplemented`（`types.py:54-60`） |
| 14 | `POST /embeddings` → `direct_driver.openai_embeddings`（L29） | **满足** | 驱动 `direct_driver/openai_embeddings.py:15`；URL `client.py:196`；下游路由 `/embeddings`、`/v1/embeddings`、`/openai/v1/embeddings` 均有生产集成测试断言上游 URL；`streamable=False` 与协议现实一致，非孤儿模块 |
| 15 | 2026-08-16 裁决前半句：ws 代码与测试保留、不最终接线（L31） | **满足** | 生产 app 工厂只有 `create_pipeline_app`，全篇无 WebSocket 路由；`responses_ws_router` 只挂在 legacy `app_factory.py:35,177`，而 `create_app` 在 `src/` 下零调用者。相关 9 个测试仍在默认扫描范围内且通过 |
| 16 | 2026-08-16 裁决后半句：「如果存在陈旧可适当注释掉」（L31） | **有 4 项候选，待裁决** | 见 D5 |

## 发现清单（按影响排序）

### F1 — `/chat/completions` 流式向客户端交付 0 字节【实测证实】

必需直连路径上的功能缺陷。

**探针是怎么钉在 `51196e2` 上的**（这一点原稿没写，导致独立评审无法复核）：主树当时有同伴未提交的在途改动，直接跑会撞进叠加态，因此另开了一棵一次性检出树 `git worktree add --detach <job-tmp>/co-51196e2 51196e2`，先确认该树 `git status --porcelain` 为空、再用 `PYTHONPATH` 指向该树并打印 `app.server.pipeline_app.__file__` / `assembler.__file__` 证明模块确实从这棵树加载，然后才跑探针；跑完已移除该检出树。入口固定为生产的 `create_pipeline_app`，上游用 MockTransport（判据换个上游也成立，不需要真打 GHC）。

结果：

- 正样本对照（`/v1/messages` 流式）：9 个 SSE 事件、非空 → 探针确有分辨力，不是「什么都测不出来」；
- `/chat/completions` 非流式：确实打到上游（`seen[-1].url` 命中 `https://copilot.example/chat/completions`），body 与上游逐字节一致，**正常**；
- `/chat/completions` 流式：确实打到上游，客户端拿到 `200` + `content-type: text/event-stream; charset=utf-8` + **body 长度 0**，连一个 SSE 字节、一个错误帧都没有。

三处协同造成：

1. `pipeline/delivery/assembler.py` 只有 `AnthropicAssembler`／`ResponsesAssembler` 两种上游形状；
2. `server/handler.py` 的 `dialect_for`／`assembler_for` 只把 Responses 单独分支，**其余一切（含 Chat Completions）落到 `AnthropicAssembler`**；
3. Chat Completions 的 SSE 帧既无 `event:` 行也无顶层 `type` 字段，`AnthropicAssembler.push` 算出的 `kind` 恒为空串，匹配不上任何分支，一个 block 都攒不出来；`pipeline/delivery/stream.py` 在从未提交任何 block 时直接 `return`，不发错误帧。

服务端日志其实标了 `status=fail "upstream stream ended without a terminal event"`，但这条判断**不出现在返回给客户端的 HTTP 响应里**——客户端看到的是一个成功的空流。

配套事实：`/chat/completions` 在**生产路径**（`create_pipeline_app`）的集成测试里端到端零覆盖，流式非流式都没有。唯一提到 chat completions 的测试是 `tests/int/test_openai_routes.py`，而它测的是 legacy `create_app`（`test_openai_routes.py:10,49`）——一个从未挂载到生产的实现。这正是缺陷能存活的原因。

### F2 — 账户类型的语义通道在生产链路上整条不存在【实测证实】

三条腿的状况各不相同，合起来的效果是：**账户类型这个概念在生产上没有落点，只能靠手写完整 URL 绕过去。**

1. **语义选择通道不存在**：新 schema `config/schema.py:83-95` 的 `ModelProviderConfig` 根本没有 `account_type` 字段（旧 `AppSettings.auth.account_type` 只服务已废弃的 legacy 链路）。因此 `config.py:48` 那条 `f"https://api.{account_type}.githubcopilot.com"` 推导分支在生产上永远进不去。
2. **CLI 通道坏了（静默）**：`cli.py:132` 写的是 `model_copy(update={"base_url": ghc_api_base_url})`，而 schema 字段在 2026-08-19 的 `a8a7f87` 里已改名为 `api_base_url`。那次改名共动了 17 个文件、更新了十几处调用点，唯独漏掉 `cli.py`——该行在改名前就已存在（`git show a8a7f87^:src/app/cli.py` 的第 127 行），`git show a8a7f87 -- src/app/cli.py` 里没有任何 `base_url` 改动。`model_copy` 不做校验，于是塞出一个幽灵属性，真字段仍是空串。实测复现：

   ```
   after model_copy(base_url=): api_base_url = ''
     phantom attr base_url    = 'https://api.enterprise.githubcopilot.com'
     resolved base url        = https://api.githubcopilot.com
   ```

   即 `--ghc-api-base-url https://api.enterprise.githubcopilot.com` 是**静默空操作**，无任何警告。
3. **YAML 通道能用，但用户亲笔的示例把键名写错了**：正确拼写 `api_base_url` 实测可用（解析出 `https://api.enterprise.githubcopilot.com`）；而 `docs/.human-controlled/config.example.yaml:159` 在 `model_providers.ghc` 下写的是 `base_url`，`Section` 是 `extra="forbid"`，照它取消注释会直接抛 `extra_forbidden`。

附带：`auth_base_url`（已实装且已列入不可热重载清单）与 `account_type` 在用户的 `config.example.yaml` 里都没有文档化。

### F3 — copilot token 后台刷新循环没接到生产链路上

`CopilotTokenManager.run_refresh_loop` 全仓唯一调用点是 `server/app_factory.py:105`，而 `app_factory.create_app` 在 `src/` 下零调用者。生产链路 `pipeline_app._lifespan` 只起了 `chain.tokenization.run_periodic_flush`；`composition.build_chain` 造出 `CopilotTokenManager` 后既不起刷新循环，也不像 legacy 那样在启动时 `ensure_valid_token()`（`bootstrap.py:177`）。

**这不是中断性缺陷**：`get_token()` 在 token 距过期不足 60s 时会同步懒刷新（`tokens.py:76-80`），正确性保住了。实际后果是两条：刷新发生在请求路径上（那一个请求多担一次兑换往返），以及凭据问题不再在启动时暴露、要等第一个请求才炸。

注：auth 分项报告曾把 `app_factory.py:104-105` 判为「真实生产接线」，这一条被交叉复核推翻，本文采信复核结论。

### F4 — `--fd` 分支吞掉「选项无效」警告

`--account-type` 等选项在新链路上已无效，standalone 分支会打印 `warning: ... has no effect`；但 `--fd` 分支把 `_load_spec_config` 返回的 `inactive` 列表丢给了 `_`（`cli.py` 中 `proxy_config, _ = _load_spec_config(...)`）。**systemd 单元用的正是 `--fd 3`**，也就是唯一真正部署的那条路径反而拿不到警告。

### F5 — `DeviceAuthProvider` 是孤儿

`ghc_client/auth/providers.py:131` 定义，全仓只有单元测试构造它。两处 composition root 组装 provider 链时都只放 `CLITokenProvider`／`EnvTokenProvider`／`FileTokenProvider`。device flow 真正的生产路径是 CLI 显式登录，不是 provider 链自动兜底。

按用户既有裁决「孤儿模块可以留着」，这里**只记录不建议删**；它指向的是一个功能问题：服务在没有可用 token 时不会自动走 device flow，必须手动跑一次 `auth`／`login` 再重启。

### F6 — `auth` 子模块的目录边界与文档不符，且是被刻意搬成这样的

`ghc-api.md:5-8` 把「device flow 取 github_token」和「换 copilot_token」两件事都归给子模块 `auth`。实际上这两件事分别在 `ghc_client/device_flow.py` 与 `ghc_client/tokens.py`——都在 `ghc_client/` 顶层；`ghc_client/auth/` 下只有 `providers.py`（github_token 来源抽象）与 `service.py`（交互式登录编排）。

**这不是无人过问的漂移。** 查历史：`device_flow.py` 原本在 `src/app/auth/` 下，是 `0d349c2` 把它移到 `ghc_client/` 顶层的（`git show --stat -M 0d349c2` 显示 `src/app/{auth => ghc_client}/device_flow.py`），而那个提交的标题正是 **"align ghc_client with the human-controlled requirements"**——当时的作者认为这样搬才是对齐需求文档。

所以这一条不是「改文档还是改代码」的简单取舍，而是**文档里「子模块 `auth`」到底指目录结构还是指职责归属**没有说清楚。功能全在，只是两种读法会导出相反的动作。见 D6。

## 待用户裁决

- **D1**：`ghc-api.md:17` 把 `msft.ghe.com` 列为 self-hosted 的 API Base URL 值。代码认为 GHES 域名各企业不同、无法推导，因此强制要求显式配置。我的倾向是**代码对、文档措辞该改**（改成「self-hosted：必须显式配置，例如 `msft.ghe.com`」），但这是您亲笔文档，请裁决。
- **D2**：`config.example.yaml:159` 的 `base_url` 与代码字段 `api_base_url` 二选一。我倾向**改示例文件**——那次改名是您命名的（`a8a7f87` 提交信息里记着「Named by the user」），而且改名已经贯彻到十几处调用点，回退代价大于改一行示例。顺带建议补上 `auth_base_url` 的文档。
- **D3**：`ghc-api.md:25` 把 count_tokens 的驱动模块写成 `direct_driver.anthropic_messages`，实际是独立方法且存在本地估算兜底。我倾向**在文档里补一句说明这条兜底路径**——兜底本身是合理设计（OpenAI 系上游没有计数端点），但它现在只活在代码注释里。
- **D4**：F5 指向的功能问题——服务端在无可用 token 时是否应能自动触发 device flow（把 `DeviceAuthProvider` 接进 provider 链），还是维持「必须先 CLI 登录」的现状。我倾向**维持现状**：服务端进程通常没有终端可供用户完成设备码授权，自动触发会变成一个没人看得见的等待；但如果您跑的是前台会话，接进去是有意义的。
- **D5**（对应 L31 后半句「如果存在陈旧可适当注释掉」）：ws 分项报告找出 4 项候选，我不代为处置：
  1. `verification/phase3_acceptance.py` 与 `exp/httpx-ws/poc.py` 依赖已卸载的 `httpx_ws` 包（项目已迁到 `httpx2[ws]`）。**注意**：交叉复核指出 `verification/phase3_acceptance.py` 未被 git 跟踪，可能是同伴在途工作，不宜按仓库陈旧代码处置。
  2. `verification/final_acceptance/probes/04_responses_websocket.py` 假设生产服务挂着这条路由，该前提已不成立。
  3. `ResponsesConfig` 的 `upstream_ws`／`max_ws_frame_bytes`／`max_client_ws_connections`／`max_upstream_ws_connections` 四个字段声明了但全代码库无读取者（交叉复核已核实这四个字段在 `51196e2` 里被跟踪且确无读取者）。
  4. `src/app/routes/responses_ws.py` 与 `src/app/openai/responses_ws.py` 本体——按您「孤儿模块可以留着」的裁决，我不建议动。
- **D6**：`ghc-api.md:5` 的「子模块 `auth`」指的是目录结构（那就该把 `device_flow.py`／`tokens.py` 搬进 `ghc_client/auth/`），还是指职责归属（那就该改文档措辞）？`0d349c2` 当年是按后者理解并据此搬动的，所以这一条需要您明确。

## 本次核查未做的事

- 未修改任何生产代码、配置或用户亲笔文档；未提交、未暂存、未 `git add`。主树 `src/` 下的改动全程只有同伴的。
- F1 的修法未设计（需要一个 Chat Completions 形状的 assembler，或者对未翻译的 chat-completions 流式做原样透传）——这是实现决策，超出「分析现状」的范围。
- 未评估 legacy 链路（`app_factory.py`、`upstream/bootstrap.py`、`routes/*.py`）是否该归档或删除，只如实报告其未接线状态。

## 评审意见的处置

独立评审（`260822-ghc-api-conformance-summary-review.md`）给出 8 条 major，本文采纳 7 条：行号整体偏一行、权威文档尚未提交、`a8a7f87` 归因过度绝对化、F6 方向写反、L31 后半句漏答、第 5/6 行分档与 F2 自相矛盾、一句话结论漏掉 schema 缺字段这个根因。另有 minor 中的三条也已采纳（第 11 行改为分流式／非流式判定、「零覆盖」补上限定词与 legacy 测试的存在、`pipeline_app.py:685-696` 改为按符号名引用）。

**未采纳 1 条**：评审判定「F1 声称在 `51196e2` 上实测不成立，探针实际跑在 `a68672c` + 工作树叠加态」。分项探针报告确实如此（09:34 落盘，早于 `51196e2` 的 09:38），但本文的 F1 依据的不是那次运行——是后来在一次性检出树 `co-51196e2` 上的重跑，过程已补写进 F1 正文。评审看不到这段是因为原稿没记录方法，这是原稿的缺陷，评审的怀疑本身是正当的。

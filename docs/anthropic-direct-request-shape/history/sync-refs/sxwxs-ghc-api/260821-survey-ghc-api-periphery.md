# `sxwxs/ghc-api` 周边功能调研

## 范围、方法与判断边界

本报告精读只读副本 `/home/xp/.claude/jobs/89874ec2/tmp/ghc-api` 的 HEAD `0cb1087`，重点核对 `auth.py`、可配置 upstream proxy、配置与模型映射、ACP、OneDrive config sync、Web IQ、内容过滤和 README 部署段落。代码事实与 README 自述分别标明；“借鉴”只指可迁移的设计或操作细节，不等于建议扩大我方产品范围。权重档说明的是证据对当前结论的支撑强度，不是功能优先级。

## 1．可选用户 token 认证

### 1.1 Token 生成、存储与比对

**发现：token 由 `secrets.token_urlsafe(32)` 生成，外加固定 `gha_` 展示前缀。**

- 代码证据：`ghc_api/auth.py:30-33,63-64`：`TOKEN_PREFIX = "gha_"`，`return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"`。
- 判断：`secrets` 是 Python 的加密安全随机源；`32` 是传入 `token_urlsafe` 的随机字节数，生成的 URL-safe 部分通常为 43 个字符。README 的“`gha_<43 url-safe chars>`”自述可由这段代码核上，见 `README.md:399-404`。
- 权重档：**强到可直接采纳**。

**发现：token 明文保存在 JSON 用户注册表，查找是 Python `dict.get` 的普通相等查找，不是常数时间比较。**

- 代码证据：`ghc_api/auth.py:41-48` 中 `UserRecord.token: str`；`ghc_api/auth.py:143-177` 直接从 JSON 取 `raw["token"]` 并以 `by_token[record.token] = record` 建索引；`ghc_api/auth.py:198-201` 返回 `self._by_token.get(token)`；`ghc_api/auth.py:383-386` 调用该查找。代码没有 `hmac.compare_digest`、哈希 token 或带 salt 的验证路径。
- 代码证据：`ghc_api/auth.py:67-77` 指定存储位置为检测到的 OneDrive `.ghc-api/configSync/users.json`，否则为本机 config directory 的 `users.json`；`README.md:458-462` 对这一位置及跨机同步作了相同说明。
- 判断：这是“服务器可读取、按完整 bearer token 精确匹配”的 registry 设计，不是“只存 token verifier”的设计。README 关于明文 token 管理端点的提醒亦能核上：`routes/auth.py:60-65` 的 `GET /api/users` 返回 `to_public_dict()`，而它包含 token。
- 权重档：**强到可直接采纳**。

**发现：写入采用临时文件、`fsync`、`os.replace`；注册表每个进程至多每 5 秒按 mtime 重读。**

- 代码证据：`ghc_api/auth.py:80-95`：`tempfile.mkstemp`、`f.flush()`、`os.fsync(f.fileno())`、`os.replace(tmp_name, path)`；`ghc_api/auth.py:31-32,113-141`：`RELOAD_INTERVAL_SECONDS = 5.0`，并以 `stat.st_mtime` 决定重载。
- 判断：本进程的新增、审批、撤销落盘是原子替换；另一台机器只能在 OneDrive 同步完成后、下一次不被 5 秒轮询短路的查找时看到变更。它没有跨机器锁、版本冲突合并或即时撤销广播。
- 权重档：**强到可直接采纳**。

### 1.2 审批、撤销与实际威胁模型

**发现：自助注册只生成 `pending` token；只有 `approved` 通过，`revoked` 立即在本进程拒绝，删除则移除索引。**

- 代码证据：`ghc_api/auth.py:217-249`：`create_pending()` 构建 `status=STATUS_PENDING` 后落盘；`ghc_api/auth.py:251-273`：`set_status()` 更新状态并落盘，`delete()` 同时 `pop` user 与 token；`ghc_api/auth.py:393-417`：分别把 pending、revoked 和非 approved 状态返回 403，只有 approved 返回 `user_id`。
- 判断：撤销的生效语义是“下一次认证查找时拒绝”，不是让已经建立的 upstream 请求或已接受的长连接失效。跨机撤销具有上一节的 OneDrive 与 mtime 传播延迟。
- 权重档：**强到可直接采纳**。

**发现：认证接受 `Authorization: Bearer`、`x-api-key`、`?api_key=`，且按该顺序优先；启用开关关闭时完全绕过并标记 anonymous。**

- 代码证据：`ghc_api/auth.py:294-313` 依次取 Bearer、`x-api-key`、query `api_key`；`ghc_api/app.py:50-70` 在 `enable_auth` 为 false 时直接设 `g.user_id = "anonymous"`，启用后只对 `PROTECTED_PATHS` 调 `require_auth()`；配置生成的同一契约见 `generate_config.py:301-318`。
- 判断：三种载体是兼容不同客户端的行为，不代表三者有同等日志暴露性质；此处没有额外的 query-token 屏蔽或重写机制。
- 权重档：**强到可直接采纳**。

**发现：其威胁模型是把共享部署者的 Copilot quota 分给经管理员许可的用户，并把“谁能管理实例、读取 dashboard 或 token”交给部署层反向代理，不是 Flask 内的完整管理面认证。README 自述已由代码核实。**

- README 自述：`README.md:387-404` 明说场景是多人共享同一实例而不让每人无限制使用部署者 quota；`README.md:397` 明说 dashboard 与 admin endpoint 在 Flask 层保持开放，期待反向代理 gate。
- 代码证据：`ghc_api/app.py:18-43,50-70` 的 `PROTECTED_PATHS` 只列 LLM 与 Web IQ 路径，注释明确把 dashboard、`/signup`、`/api/users/*`、`/agent` 留在 Flask auth 之外；`ghc_api/routes/auth.py:3-15,60-89` 明列 `/api/users/*` “NOT protected at Flask layer”，并实现 approve、revoke、delete；`ghc_api/main.py:420-432` 启动时也警告 dashboard/admin 未受自身认证保护。
- 判断：README “dashboard/admin 路由不在 Flask 层认证，交给反向代理”的说法与代码一致，不是未核实的宣传。它保护的具体资产是共享上游额度及按用户归属的请求统计；它假定管理面所在反向代理 location 有另一个管理员身份边界。若该边界不存在，任何可达调用方均可审批、撤销、删除用户，或经 dashboard 管理全局状态。
- 权重档：**强到可直接采纳**。

**对我方的结论：不应照搬 token registry。** 我方已经有自己的 auth；这个项目的审批 registry 有价值的仅是把“token 状态”和“可审计 user_id”分开、原子写入和重载传播这一小组实现事实。是否需要 self-signup、管理员审批、明文可读 registry 或 query token，取决于我方是否真的要解决“多人共享一个上游 quota 且有独立管理员反向代理”的具体场景；本调研材料不能替该需求作决定。

## 2．`/proxy/<profile>/v1/...` 的可配置上游 profile

### 2.1 抽象边界与路由隔离

**发现：一个 profile 是独立的 OpenAI-compatible upstream 描述，不是主 Copilot 路径的可选地址。它封装 upstream auth、分层 headers、两个 API endpoint、公开模型和模型级 API 映射、以及 affinity。**

- 代码证据：`ghc_api/proxy/config.py:29-109` 定义 `ProxyAuthConfig`、`ProxyAffinityConfig`、`ProxyApiConfig`、`ProxyModelApiConfig`、`ProxyModelConfig`、`ProxyProfileConfig`；`ProxyProfileConfig.resolve()` 只在 profile、API 和模型均存在且模型 API 已启用时返回目标。
- 代码证据：`ghc_api/proxy/config.py:225-358` 只接受 `responses` 与 `chat_completions`，每个 profile 至少启用一个 API、至少定义一个 model；`routes/proxy.py:287-294` 仅暴露 `POST /proxy/<profile>/v1/responses` 和 `POST /proxy/<profile>/v1/chat/completions`。
- 判断：profile 是按“外部 upstream 合同”隔离的命名空间，主 `/v1/...` Copilot 路径并未复用它。README “isolated routes without changing existing Copilot endpoints”的自述可由这些独立 Blueprint 路由核上，见 `README.md:577-586`。
- 权重档：**强到可直接采纳**。

**发现：header 映射按 profile → API → model → model API 的顺序覆盖，值可展开 `${ENV_VAR}`；请求 model 可 preserve、omit 或替换为每 API 的 upstream model，响应 model 可保留或改回公开 model。**

- 代码证据：`ghc_api/proxy/client.py:38-54` 以环境变量替换 header value，`_merge_headers()` 按传入顺序赋值；`client.py:93-109` 的调用顺序正是 profile、API、model、model API，并最后加入 bearer 与 affinity header；`client.py:57-70` 实现 `omit`、`upstream`、`preserve`；`proxy/config.py:61-71` 定义可用模式；`routes/proxy.py:74-79,263-266` 在 `response_model == "public"` 时重写非流式响应 model。
- 测试证据：`tests/test_configured_proxy.py:274-316` 断言 Responses 请求实际省略 `model`，model header 被加入，并复用 affinity；`tests/test_configured_proxy.py:318-356` 断言 chat 请求把公开 model 改为 `chat-deployment`，响应流改回公开名。
- 权重档：**强到可直接采纳**。

**发现：profile 的入站 auth 是 Blueprint-local 的独立 gate，因此虽然全局 `PROTECTED_PATHS` 没列动态 `/proxy/...`，这些路径仍会在 `enable_auth` 下被认证。**

- 代码证据：`ghc_api/app.py:18-43` 的静态集合确实没有 `/proxy/...`；`ghc_api/routes/proxy.py:26-41` 的 `@proxy_bp.before_request` 在启用时调用同一个 `require_auth()` 并设置 `g.user_id`。
- 测试证据：`tests/test_configured_proxy.py:553-568` 断言 `/proxy/models` 返回 401，并验证动态 endpoint 不在 `PROTECTED_PATHS`。
- 判断：README 把 configured proxy 列作自有用户 token gate 的 public LLM path，`README.md:724-730`，与实际 Blueprint-local 实现相符。
- 权重档：**强到可直接采纳**。

### 2.2 Affinity routing 的实际含义

**发现：这里的 affinity routing 是把 upstream 在响应 header 返回的“路由 token”缓存下来，并在后续同一 routing key 的请求中放入指定 request header，以回到 upstream 先前选择的后端／会话分片。它不是按用户、客户端 IP 或负载均衡算法选路。**

- 代码证据：`ghc_api/proxy/config.py:47-54,200-222` 的配置字段是 `response_header`、`request_header`、`scope`、`persist`；`ghc_api/proxy/client.py:110-120` 从响应 header 取 token 并存储，`client.py:138-143` 在每次上游 POST 前从 store 取回并注入 header。
- 代码证据：`ghc_api/proxy/affinity.py:27-51` 的 key 是 profile、API、model 或 `*`、URL、model rewrite 和 headers 的 SHA-256；`client.py:181-214` 在未发现 token 时用 per-key discovery lock，避免同一进程并发首次请求同时探索。
- 代码证据：`ghc_api/proxy/affinity.py:95-161` 可将 token 写到 `proxy-affinity.json`，用临时文件与 replace 持久化；`tests/test_configured_proxy.py:177-185` 验证进程重建后的 token 仍可读取。
- 判断：scope=`model` 意味着同 profile、同 API、同 model 配置共享 token；scope=`proxy` 使 model 部分变为 `*`，但 API 仍在 key 内。header 或 upstream 配置一变，key 也随之变，旧 token 不被复用。
- 权重档：**强到可直接采纳**。

**对我方的结论：对“只服务一个固定 Copilot OpenAI Responses upstream”的项目，整套 profile 抽象与 affinity routing 均不适用。** 它解决的是多个异构、可配置的 OpenAI-compatible upstream 及其中一个需粘性路由 header 的场景；我方单一上游没有 profile 选择点，也没有已观察到的 upstream affinity header 合同。若将来出现“不同客户选择不同 upstream”或上游明确要求 response-derived sticky header，才值得单独调研其最小实现；现在搬入会把单一路径变成配置矩阵。

## 3．模型名映射与模型列表

**发现：映射优先 exact，再按 Python mapping 的插入顺序取第一个 `startswith` prefix；没有 longest-prefix 规则、重叠冲突诊断、类型验证或循环检测。**

- 代码证据：`ghc_api/config.py:65-93`：先 `if model in self.exact_mappings`，随后 `for prefix, target in self.prefix_mappings.items(): if model.startswith(prefix): return target`；`load_from_config()` 直接赋入 YAML 读取的映射。
- 代码证据：`ghc_api/main.py:375-380` 在 config 有 `model_mappings` 时载入，否则载入 `DEFAULT_MODEL_MAPPINGS`；`translator.py:9-21` 仅调用一次 `model_mappings.translate()`，发生变换时计数，没有递归再次映射。
- 代码证据：`ghc_api/config.py:22-48` 与 `generate_config.py:62-105` 给出默认精确别名，例如 `opus → claude-opus-4.8`，和若干日期／分隔符 prefix。
- 判断：exact 与 prefix 都命中时 exact 必赢；多个 prefix 都命中时“先出现者赢”。YAML 的普通 mapping 在当前 Python 中保持装载顺序，但这不是面向冲突的显式合同。比如把广义 `claude-` 写在具体 `claude-opus-` 之前，就会遮蔽后者。README 只宣称 “exact and prefix-based matching”，`README.md:103-113`，没有声称最长前缀，因此并非 README 违约，但配置维护者没有被保护。
- 权重档：**强到可直接采纳**。

**发现：标准 Copilot 模型列表是启动／刷新时真实 `GET <copilot-base>/models` 得到的 `state.models`，不是上述映射表生成的；configured profile 的 `/models` 则完全来自私有 YAML。**

- 代码证据：`ghc_api/api_helpers.py:201-217` 调 `requests.get(f"{get_copilot_base_url()}/models", ...)` 并将 JSON 放入 `state.models`；`ghc_api/app.py:130-160` 初始化时调用 `fetch_models()`。
- 代码证据：`ghc_api/routes/proxy.py:331-365` 遍历 `profile.models.values()` 构造 `/proxy/models` 与 `/proxy/<profile>/v1/models`，其中 `id`、context、output 上限和 endpoint 支持均取配置；`proxy/config.py:296-334` 要求这些 model 在 YAML 中声明。
- 判断：模型名映射是输入兼容层，不是模型发现机制。标准 `/models` 以 upstream 实测列表为权威，profile `/models` 是配置作者的声明。两者不能互相推导。
- 权重档：**强到可直接采纳**。

**对我方的结论：值得借鉴的是“把入站别名映射与 upstream 模型发现分开”的边界；不值得照搬 first-match prefix 规则。** 我方若已有模型 provider，应由明确解析规则处理重叠，例如拒绝重叠或最长前缀优先，并把该规则写入其自身 contract。该结论是从一个实现的明确缺口推出的工程偏好，不是上游行为证据。

## 4．ACP：JSON-RPC 2.0 over subprocess stdio

### 4.1 行框定与刷新

**发现：协议是 JSON Lines：写端显式追加 `\n` 并 `await drain()`，读端以 `await stdout.readline()` 取得一行再 JSON decode。并发写由 asyncio lock 串行化。**

- 代码证据：`ghc_api/acp/protocol.py:10-28` 定义 `JsonRpcProtocol` 与 `_send_lock`，`protocol.py:30-61` 在 `_read_loop()` 中 `await self.process.stdout.readline()`，EOF 时使 pending futures 失败；`protocol.py:162-170` 执行 `data = json.dumps(msg, ensure_ascii=False) + "\n"`、`stdin.write(...)`、`await stdin.drain()`。
- 代码证据：`ghc_api/acp/connection.py:201-213` 以 asyncio PIPE 建立 stdin/stdout/stderr，并把 StreamReader limit 调到 100 MiB，随后 `connection.py:239-245` 启动 protocol reader。
- 判断：对“子进程 stdout 每个 JSON-RPC message 都必须有 newline 并刷新”的 ACP 方，这个行框定和写端 backpressure 处理是正确的。`drain()` 只保证父进程已把数据推进自己的 transport，不能替无法控制的子进程 stdout 刷新；启动参数没有强制子进程 unbuffered。因此不应把它表述为“解决了子进程输出缓冲”。
- 权重档：**强到可直接采纳**。

### 4.2 关停、阻塞与结论

**发现：关停顺序是先取消 stdout reader、关闭 stdin，再向子进程发 `terminate()`，5 秒后 `kill()`；stderr reader 只被 cancel 而没有 await。**

- 代码证据：`ghc_api/acp/protocol.py:178-189` 取消并 await `_reader_task`，然后关闭 stdin；`ghc_api/acp/connection.py:347-361` 先 `await self.protocol.close()`，对 `_stderr_task` 仅 `.cancel()`，然后 terminate、`wait_for(..., 5.0)`、超时 kill；stderr loop 的阻塞点在 `connection.py:381-395`。
- 判断：reader 是 asyncio task 而非线程，取消 `await readline()` 会由 asyncio cancellation 打断；随后终止子进程也会关闭 pipe。因此它没有“同步 read thread 永久卡在 `readline()`，close 永远等不回”的典型问题。这一部分做对了。
- 权重档：**强到可直接采纳**。

**发现：但 graceful shutdown 的 pending request 收束不完整，不能判为完全做对。`protocol.close()` 取消 reader 后没有给 `_pending` 中的 future 设置异常，而 EOF 分支才会做这件事；取消 reader 使 EOF 分支不会运行。`session/prompt` 又特意设置 `timeout=None`。**

- 代码证据：`ghc_api/acp/protocol.py:40-47` 仅在 stdout EOF 时遍历 `_pending` 并 `set_exception(RuntimeError("Agent process exited"))`；`protocol.py:125-148` 的 `timeout=None` 路径直接 `await future`；`protocol.py:178-189` close 取消 reader 并未处理 `_pending`；`connection.py:302-305` 对 `session/prompt` 明确传入 `timeout=None`。
- 判断：若在一个 prompt 请求仍等待 response 时调用 close，那个 coroutine 不会因 reader EOF 自行结算；上层 `SessionManager.terminate_session()` 虽用 `run_async(conn.close(), timeout=10)` 限住关闭调用，见 `session_manager.py:381-395`，却没有使原 prompt future 成功、取消或失败。是否实际留下 task 取决于未展示的 event-loop runner，但 protocol 本身没有提供完整保证。
- 权重档：**强到可直接采纳**。

**发现：没有看到针对真实子进程管道的 ACP round-trip／关停测试。**

- 代码证据：调研时列出的 `tests/` 中 ACP 无测试文件；现有 `tests/test_configured_proxy.py`、`tests/test_webiq.py`、`tests/test_config_sync.py` 均以 HTTP／mock／文件为主，无法覆盖 `asyncio.create_subprocess_exec` 的管道终止条件。协议实现本身的 subprocess 建立点是 `ghc_api/acp/connection.py:195-245`。
- 判断：这是一项“代码中未见测试资产”的覆盖观察，不能据此断言线上必有 bug；但它不足以抵消上一条可从控制流直接推出的 pending-future 缺口。
- 权重档：**是个倾向、需更多样本**。

**对我方的结论：ACP 整体不适用；其中 JSONL wire bytes、每条写后 `drain()`、关闭时终止子进程再等待／kill 的细节可在我方未来真的驱动长寿命子进程时复用。** 但不能照抄这套 close：必须令所有 pending request 明确完成为取消或异常，并用真实子进程验证一条有换行的 round trip 与一次 prompt 中关停。现在我方项目的主路径是 HTTP upstream，不应为未决定的 ACP 功能引入该子系统。

## 5．内容过滤：system prompt 改写与 tool result 后缀裁剪

**发现：默认配置为空列表；过滤只在 Anthropic Messages 请求处理链调用，不在 configured proxy 路由调用。system prompt 删除是任意子串 replace，追加是任意配置字符串；tool result 仅在字符串内容以配置 suffix 结尾时裁掉该 suffix。**

- 代码证据：`ghc_api/generate_config.py:120-148` 生成 `system_prompt_remove: []`、`tool_result_suffix_remove: []`、`system_prompt_add: []`；`translator.py:24-46` 对每个 remove string 执行 `system_text.replace(remove_str, "")`，`translator.py:49-63` 只在 `content.endswith(suffix)` 时切除。
- 代码证据：`routes/anthropic.py:746-827` 处理 string 或 list system，追加字符串并仅遍历 `type == "text"` 的 block；`routes/anthropic.py:830-876` 仅处理消息 content 中 `type == "tool_result"` 且 `content` 为 string 的 block。
- 代码证据：`routes/anthropic.py:1020-1025,1032-1048,1061-1066` 表明 direct Anthropic、Responses compatibility、legacy OpenAI translation 三条 `/v1/messages` 分支均调用两个 filter；`routes/proxy.py:150-294` 的 configured proxy 请求处理无这些调用。
- 判断：其有限作用域是“仅 `/v1/messages` 的指定文本字段与 suffix 条件”，不是“仅对某个模型、用户、来源或经审批的 content 起作用”。命中规则是纯文本，删除后的语义、重复／重叠 suffix 的顺序及全局 runtime 配置均未作细粒度约束。
- 权重档：**强到可直接采纳**。

**发现：这一危险功能没有足以约束误改的业务作用域；其 runtime 配置还能由 Flask 层不认证的 dashboard 管理面改变。**

- 代码证据：`ghc_api/app.py:18-21,58-60` 明确将 dashboard 与 `/api/users/*` 等排除在 Flask auth 之外；`ghc_api/routes/dashboard.py:217-266` 接受并验证三组 string list，直接写入全局 `state`；`main.py:272-279` 从 config 同样直接写入全局 state。
- 判断：该项目的 README 部署假设是反向代理保护管理面，因此它依赖外部管理边界而非 filter 自身的 scope。没有用户指定的具体“必须剥离／追加的文本、适用请求类别和失效后果”时，不能把这种能力作为我方默认 feature。
- 权重档：**强到可直接采纳**。

**对我方的结论：不适用。** 本调研没有给出我方要保护或修改的具体 prompt／tool-result 合同；直接引入会增加静默改写用户输入的能力。若未来用户明确指定某个 carrier、已知 upstream 缺陷和精确 predicate，可单独做最小的、可观测的变换，不应以此实现为默认策略模板。

## 6．OneDrive config sync 与 Web IQ

### 6.1 OneDrive config sync

**发现：同步对象是本机 Claude Code `~/.claude/settings.json`、Codex `~/.codex/config.toml`、ghc-api `config.yaml`；OneDrive 是按环境探测的文件复制共享目录，不是双向冲突解决协议。**

- 代码证据：`ghc_api/config_sync.py:198-230` 探测 OneDrive 并返回 `.ghc-api/configSync`；`config_sync.py:448-454` 列出三个本地配置文件；`config_sync.py:532-562` 将 local 复制到 shared root；`config_sync.py:565-603` 将 shared 文件复制回 local。
- 代码证据：`config_sync.py:457-503` 仅比较双方内容并报告 `different`，不选择赢家或合并；`README.md:300-331` 对检测顺序、目录、hash 文件和启动时差异提示的说明可由代码核上。
- 判断：它是显式操作驱动的单向 copy plus status，而不是自动同步或 CRDT。`config.sha1` 主要服务状态展示；`_config_hash_text()` 使用 SHA-1，见 `config_sync.py:318-328`，但传输与冲突决策仍是文件复制。
- 权重档：**强到可直接采纳**。

**发现：从 OneDrive 覆盖本机前会以秒精度创建 `*.YYYYMMDD_HHMMSS.bak`，但 local → OneDrive 覆盖前不做同样备份；Codex 的 `[projects.*]` 本机段被特例保留。**

- 代码证据：`ghc_api/config_sync.py:269-275` 用 `shutil.copy2` 写时间戳 `.bak`；`config_sync.py:549-554` local → OneDrive 直接 copy 或调用 Codex 合并，无 backup；`config_sync.py:585-594` OneDrive → local 先 backup；`config_sync.py:284-315` 分割 `[projects.`，将 source header 与 target local projects 重新组合。
- 测试证据：`tests/test_config_sync.py:44-101` 覆盖 Codex projects-only diff 忽略及还原时保留本机 project 配置。
- 判断：README “Safe Backups: Auto backup overwritten config files”见 `README.md:21-24`，若理解为“从 OneDrive 覆盖本地文件时”可由代码核上；若理解为两个方向的所有覆盖都有 backup，则核不上。
- 权重档：**强到可直接采纳**。

**对我方的结论：不适用。** 我方部署目标是 systemd/cgroup 管理服务及 socket activation，而非把多个 CLI 和服务配置经个人 OneDrive 复制。同步 `~/.claude` 或 `~/.codex` 也不是我方代理的产品职责。若未来需要部署配置迁移，应另按 systemd unit、environment 和本机 state 的所有权设计，不能把该文件复制器当方案。

### 6.2 Microsoft Web IQ 透传

**发现：Web IQ 是一个独立功能面：代理六个 allowlisted REST path 与一个 Streamable HTTP MCP path；REST body 原字节转发，正常 upstream status、body 和大部分 headers 透传。**

- 代码证据：`ghc_api/webiq.py:85-105` 定义六个 REST API path、MCP path 和 allowlist；`webiq.py:260-321` 用 `requests.post(..., data=body)` 转发原 bytes；`routes/webiq.py:214-291` 用 `request.get_data()` 与 `Response(response_bytes, status=..., headers=passthrough_headers(...))` 返回。
- 测试证据：`tests/test_webiq.py:141-183` 断言 request bytes 原样进入 `data`、未知参数不被拒绝、非法 body 交 upstream；`tests/test_webiq.py:384-416` 断言 body 与 `Retry-After` 回到 client。
- 判断：README “透明代理、客户端只改 base URL”的自述，`README.md:499-506`，与代码相符，但需限定为 body 与筛选后的 response headers：hop-by-hop、framing、`Date`、`Server`、`Alt-Svc`、HSTS 不透传，见 `webiq.py:114-137,246-257`。
- 权重档：**强到可直接采纳**。

**发现：它代管服务器 Web IQ key，丢弃客户端 REST credential；MCP 只转发标准 header 与 `mcp-*` namespace，使用服务器 key。服务未配置或服务器 key 被拒绝时返回 503，而通常 upstream API error 保留。**

- 代码证据：`ghc_api/webiq.py:275-319` 仅发送 `x-apikey: settings.webiq_api_key`，401／多数 403 变为 `WebIQError(..., 503)`；`webiq.py:324-389` 的 MCP forwarded headers 初始化为服务器 key，且仅接受标准字段或 `mcp-` 前缀。
- 代码证据：`routes/webiq.py:420-553` 对 MCP 用 `requests` streaming response 迭代 chunk、client 断开时记录取消、finally close upstream，并对 SSE 增加 `X-Accel-Buffering: no`。
- 判断：这不是 LLM proxy 的“搜索功能自动注入”。模块自己明言不替模型搜索或篡改 prompt，`webiq.py:1-37`；旧 `webiq_search_options` 会被移除并报迁移错误，`webiq.py:46-56,160-172`。README 同样可核上，`README.md:542-568`。
- 权重档：**强到可直接采纳**。

**对我方的结论：不适用。** 它需要一项额外的 Microsoft Web IQ 产品功能、服务器持有的 Web IQ key 和独立 quota；题目给出的我方背景没有这一需求。可以保留“做真正透明 HTTP proxy 时 raw-body／允许的响应 headers 透传”的实现观察，但不应为此把 Web IQ 或 MCP endpoint 加入我方。

## 7．部署建议与我方 systemd 目标的关系

**发现：README 的 nginx 默认拒绝、对 LLM／Web IQ／configured proxy public location 关闭 basic auth、关闭 proxy buffering、设置长 `proxy_read_timeout` 的部署建议可由路由和认证代码核实。**

- README 自述：`README.md:718-730` 说明 admin 由 reverse proxy 认证并给出路径分类；`README.md:732-805` 的 nginx sample 先全局 `auth_basic`，再在 `/v1/`、aliases、`/v3/`、`/proxy/` location 设置 `auth_basic off`、`proxy_buffering off`、`proxy_read_timeout 1200s`；`README.md:816-821` 明说 bearer 与 basic `Authorization` 不能共存于同一路由。
- 代码证据：`ghc_api/auth.py:294-313` 把 `Authorization: Bearer` 作为第一优先级；`app.py:18-70` 与 `routes/proxy.py:26-41` 显示 LLM／Web IQ／profile 路由确实由应用 token gate 处理，而 admin 路由不在 Flask gate；`routes/webiq.py:543-553` 对 MCP SSE 实际设置 anti-buffering headers。
- 判断：README 所称“不要对 LLM path 加 nginx basic-auth”的理由可由实现核上：basic auth 会占用同一 `Authorization` header，从而使应用收不到 Bearer token。`proxy_buffering off` 和长 read timeout 是对会持续较久的 SSE／MCP 路径的具体要求，不是所有 JSON API 的普适值。
- 权重档：**强到可直接采纳**。

**发现：该项目自己的运行方式是 Flask + Waitress `create_server(...).run()`，调大 thread pool 和 `channel_timeout`；它没有 systemd socket activation、listener handoff 或优雅 shutdown 设计。**

- 代码证据：`ghc_api/main.py:463-515` 正常模式导入 Waitress，计算 `threads` 和 `channel_timeout = max(300, upstream_read_timeout)`，然后调用 `create_server(...).run()`；`generate_config.py:20-29` 把 `server_threads` 与“每个 streaming request 占一个 thread”写入生成配置。
- 判断：这部分不能迁移到我方的 systemd/cgroup、socket activation、优雅停机目标。特别是 `.run()` 自己绑定 host／port，与 systemd 传入 listener 的生命周期模型不同。
- 权重档：**强到可直接采纳**。

## 汇总：发现与我方借鉴判断

| 发现 | 我方是否值得借鉴 | 理由 |
|---|---|---|
| `secrets.token_urlsafe(32)` 生成展示为 `gha_` 的随机 bearer token | 存疑 | 随机源本身可靠，但我方已有 auth，token 前缀、明文 JSON registry 与 self-signup 不由此自动成立。 |
| pending／approved／revoked 状态及原子 JSON 写入、mtime 重载 | 存疑 | 可作为多人共享上游 quota 时的最小 registry 参考；题目没有给出我方需新增该角色模型的决定。 |
| 管理面留给 reverse proxy、LLM path 留给 Bearer token | 值得 | 是已被代码与 nginx 样例共同支撑的路径分层；我方需按自己的路由清单执行，不能照抄 ghc-api 的路径。 |
| 可配置 profile、分层 header／model mapping、独立 upstream auth | 不适用 | 我方只有一个固定 Copilot OpenAI Responses upstream；引入 profile 会制造没有选择点的配置矩阵。 |
| response-header affinity token 的持久复用 | 不适用 | 未观察到我方上游有该合同，且单 upstream 不需要 profile/model 粘性路由。 |
| 入站别名映射与真实 `/models` 发现分离 | 值得 | 这是清晰的模型 provider 边界；应保留我方自己的冲突规则。 |
| prefix 按配置插入顺序 first-match | 不适用 | 重叠 prefix 静默遮蔽，不是可复用的冲突处理。 |
| ACP 的 JSONL `\n`、`drain()`、reader task cancellation、terminate→kill | 存疑 | 子进程 stdio 场景才适用；其 pending future 关停缺口使整套实现不能直接照抄。 |
| 任意 system prompt substring 改写与 tool-result suffix 裁剪 | 不适用 | 没有我方已决定的具体变换合同，且其 scope 不按 model／user／来源约束。 |
| OneDrive 同步 Claude/Codex/ghc-api 配置及 `.bak` | 不适用 | 与 systemd 托管代理的部署职责和配置所有权不匹配；它也不是双向冲突解决。 |
| Web IQ REST／MCP 透传 | 不适用 | 需要额外产品功能、服务器 key 与 quota；我方背景没有该需求。 |
| nginx 对长时 SSE path 设 `proxy_buffering off` 与长 `proxy_read_timeout` | 值得 | 对我方实际存在的长时 SSE 交付路径可直接作为部署检查项，但 timeout 数值应按我方 liveness 合同确定。 |
| 不在 LLM Bearer-token 路径叠加 basic auth | 值得 | 同一 `Authorization` header 的协议冲突是具体、可验证的兼容性事实。 |
| Waitress `.run()` 运行方式 | 不适用 | 不支持我方 systemd socket activation 与优雅 listener 生命周期目标。 |

# Current main 备用端口关键主路径 smoke R3

## 判定与范围

- **执行对象**：主树 `/home/xp/src/ghc-api-proxy-py`，branch `main`，完整 HEAD `d903d726baf3f15bf46ddf17384564fee154ed6a`；`HEAD == refs/heads/main`，且 `git merge-base --is-ancestor d903d72 HEAD` 退出 0。本轮现场中 `HEAD` 正是 `d903d726…`，不是仅包含该提交的后继。
- **本轮 verdict**：**`PASS_KEY_BACKUP_PORT_SMOKE_R3`**。固定拓扑 `127.0.0.1:4142` app＋`127.0.0.1:4143` fake 上，nonstream、stream text withholding、Responses SSE→Anthropic SSE、唯一 success terminal、stream History request conversion fact、client cancel cleanup、app SIGTERM lifespan cleanup、两个 direct child 的 wait／reap、备用端口释放与旧 Bun 零 signal／incarnation 不变全部通过。
- **R2缺口关闭**：R2在 `main@e9fb277…` 上观察到 stream History usage 缺少 final attempt 的 request conversion fact。本轮相同语义输入通过真实 History API观察到 `metadata.smoke_extra／metadata_not_allowlisted／attempt=0` typed request fact，且 original request metadata、requested／resolved model与 completed终态同时保留；该定向缺口现为 **PASS**。
- **明确排除**：依用户要求，未扩展 retry、quota／resident backpressure或真实socket partial-write／RST；也未扩展完整terminal／usage／History矩阵、真实credential／upstream、systemd manager／effective cgroup、部署或cutover。完整bridge与完整Acceptance继续为 `UNVERIFIED`；本报告不授权停止旧 Bun或切换生产`4141`。
- **唯一仓库写入**：`docs/tmp/260807-final-backup-port-smoke-r3.md`。一次性controller、fake、配置、History DB、tokenization状态、日志和结构化结果仅位于`/tmp`；controller与一次性运行根已删除，没有新建仓库harness、测试或fixture，没有修改生产代码。

## 从点名路径推导的验收矩阵

| 验收项 | 用户可观察判据 | 结果 | 实证 |
|---|---|---|---|
| candidate身份 | current `main`必须等于或包含`d903d72`，且本轮产品路径不得漂移 | **PASS** | `HEAD == refs/heads/main == d903d726…`；祖先检查退出0；执行前后`src／tests／contrib／pyproject.toml`的tracked diff内容一致且为空 |
| 端口与配置隔离 | spawn前`4142／4143`无listener；受控显式config只指向本轮fake；状态只落一次性根 | **PASS** | controller记录`ports_preflight_empty=true`、`isolated_settings=true`；app由唯一显式`--config <ephemeral-path>`启动，generic OpenAI base URL固定为`127.0.0.1:4143/v1`，History与tokenization路径位于一次性根 |
| credential／CLI隔离 | 不继承六个token／config入口；child env从空字典按allowlist构造；argv无`--github-token／-g`；不读取真实credential | **PASS** | 父环境与最终child env中`GITHUB_TOKEN／GH_TOKEN／COPILOT_GITHUB_TOKEN／GHC_AUTH__GITHUB_TOKEN／GHC_AUTH__TOKEN_FILE／GHC_CONFIG`的presence均为false；无未批准`GHC_*`；四个旁路文件均absent；CLI token槽absent。Generic SDK只收到一次性config中的固定非真实哨兵Authorization，不来自父环境、token file或CLI；报告未记录该header值 |
| nonstream | 真实`POST /v1/messages`经Responses leg返回Anthropic Messages JSON，且本case恰好一次Responses exchange | **PASS** | HTTP 200；唯一text block为`backup-port-r3-ok`；第1个fake exchange为`stream=false`、有`input`、无`messages` |
| stream withholding | authoritative完整text block前零success headers、零`message_start`、零body bytes | **PASS** | fake先发送`response.created`、message item start和`output_text.delta`，再停顿；raw client在`0.35s`观测窗口收到`0`字节。该时长只描述本轮观察窗口，不是性能SLO |
| Anthropic SSE／terminal | 不泄漏Responses事件；Anthropic事件序列合法；text完整；`message_stop`恰好一次 | **PASS** | strict parser得到`message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop`；text为`hello bridge`；`message_stop_count=1`；无`response.*`事件 |
| stream History request fact | completed stream entry保留original request／model，并承载final attempt typed request conversion fact | **PASS** | 真实`GET /history/api/entries?session_id=session-final-r3`得到2条completed entry；stream entry保留`metadata.smoke_extra`、requested／resolved model均为`smoke-model`，usage中存在`provenance=request／attempt=0／field_path=metadata.smoke_extra／disposition=degrade／reason=metadata_not_allowlisted` |
| cancel cleanup | 首block前客户端断开时零success bytes；上游观察断连；History不记completed | **PASS** | cancel raw socket early bytes为`0`；fake记录`upstream_disconnect_seen=true`；同一session最终恰有1条failed cancel entry，另2条happy entry为completed |
| SIGTERM cleanup | 仅向本轮app发送一次SIGTERM；lifespan完整；app与fake均由原handle wait／reap | **PASS** | app pidfd发送一次SIGTERM；日志包含`Shutting down`、`Waiting for application shutdown.`、`Application shutdown complete.`、`Finished server process`；app return code为`-15`。fake由其pidfd发送一次SIGTERM并由signal handler正常退出，return code为`0`；两者`wait_reaped=true` |
| 旧Bun不变 | 前后同一PID＋starttime＋cwd＋cgroup＋内存raw cmdline相等＋双栈listener inode；零signal | **PASS** | 前、中、清理前、清理后均为PID`818465`、starttime`2138402`、cwd`/home/xp/src/copilot-api-js`、cgroup`0::/init.scope`、argc`5`、IPv4 inode`16023105`、IPv6 inode`15964765`；raw cmdline只在controller内存中比较并得到相等，不落盘原值或hash；`signals_to_bun=0` |
| 最终收口 | app／fake历史PID与临时根消失；`4142／4143`无listener | **PASS** | controller收口后，独立post-probe重新确认app PID`1803054`、fake PID`1803053`均无`/proc`项，一次性根不存在；`ss`只列出旧Bun双栈`4141`，没有`4142／4143`listener |

## 有效运行与拓扑证据

最终有效轮次的唯一标记为`R3_SMOKE_20260808_7F2C`。先对一次性`/tmp` controller执行语法检查，再通过隔离session运行；controller退出码为`0`，结构化结果为`PASS_KEY_BACKUP_PORT_SMOKE_R3`，`errors=[]`、`cleanup_errors=[]`、`ports_final_empty=true`、`incumbent_final_cleanup_unchanged=true`、`ephemeral_root_removed=true`。一份更早的共享terminal输出没有返回本轮唯一标记，已作废，未被本报告用作运行证据。

controller从空字典构造app与fake环境，只加入固定`PATH`、locale、隔离`HOME／XDG_CONFIG_HOME／XDG_DATA_HOME／TMPDIR`、candidate `PYTHONPATH`、禁bytecode和loopback `NO_PROXY`。App launch tuple严格固定为candidate解释器、`-m app start`、`--host 127.0.0.1`、`--port 4142`、`--config <ephemeral-path>`；fake tuple严格固定为candidate解释器、一次性controller、`--fake`与一次性根。没有shell自由文本追加、credential槽、未批准`GHC_*`或默认config入口。

Generic upstream要求非空API key，因此显式config使用controller自建的固定非真实哨兵。Fake观测到Authorization header存在，这证明SDK实际消费了隔离哨兵；它不证明真实credential可用，也没有从父环境、用户配置、token file或CLI取得任何credential。controller与报告均不记录header值。

fake实际捕获3次Responses exchange，按顺序为nonstream、stream happy、stream cancel，对应`stream=false／true／true`；三次wire均含`input`、不含`messages`。该计数口径只覆盖本轮三个固定无retry case，不外推retry行为。

stream happy fake以CRLF SSE并跨chunk拆分`response.created`，随后发送合法text lifecycle：`response.output_item.added → response.content_part.added → response.output_text.delta → response.output_text.done → response.content_part.done → response.output_item.done → response.completed`。`output_text.delta`之后保留`0.55s`受控停顿，raw client只把前`0.35s`作为“完整block前零字节”观察窗口；窗口后才收到HTTP 200和Anthropic SSE。最终只出现1个`message_stop`。

cancel case同样先进入合法`response.created`和空message item，但不完成任何block。Client在`0.35s`零字节窗口后主动断开；fake后续写入命中断连并记录`upstream_disconnect_seen=true`，History最终出现恰好1条failed entry。该case验证首block前cancel cleanup，不覆盖首block后cancel、partial write或RST语义。

## Stream History fact缺口关闭证据

本轮nonstream与stream happy都发送`metadata={"user_id":"history-smoke-r3","smoke_extra":"preserve-only-in-history"}`。Request converter把allowlist内的`metadata.user_id`投影到Responses wire的`user`，并为`metadata.smoke_extra`产生`degrade／metadata_not_allowlisted` fact。

Current实现的共享发布接缝位于`src/app/pipeline/executor.py:295`：success attempt在stream／nonstream response body分叉前把`attempt_result.converted_request_facts`写入`context.conversion_facts`。Stream History projection位于`src/app/history/consumer.py:151-172`，从同一context读取conversion facts。本轮真实History API观察与该预期一致：stream completed entry的original request仍含完整metadata，usage的`conversion_facts`含上述typed request fact，attempt为`0`。

这关闭的是R2点名的**stream request conversion fact**定向缺口，不等于完整History parity已经验证。本轮没有扩展多attempt、retry后final-attempt切换、partial delivery、uncertain delivery、完整response fact或完整usage矩阵。

## 进程、incarnation与清理终态

| Role | 本轮标识 | listener | 终止与回收 |
|---|---|---|---|
| fake | PID`1803053`，starttime`3515061` | `127.0.0.1:4143`，启动时反查owner与direct child一致 | 绑定pidfd后精确发送一次SIGTERM；signal handler正常退出，return code`0`；原`Popen` handle wait／reap；独立post-probe确认`/proc/1803053`不存在 |
| app | PID`1803054`，starttime`3515082` | `127.0.0.1:4142`，启动时反查owner与direct child一致 | 绑定pidfd后精确发送一次SIGTERM；完整lifespan日志；return code`-15`；原`Popen` handle wait／reap；独立post-probe确认`/proc/1803054`不存在 |
| 旧Bun | PID`818465`，starttime`2138402` | `127.0.0.1:4141` inode`16023105`；`[::1]:4141` inode`15964765` | 只读观察；本轮signal数`0`；前／中／清理前／清理后完整identity相等；独立post-probe再次确认同一PID、starttime、cwd、cgroup、argc与双栈listener |

App／fake PID与starttime由同一controller生产，只用于标识本轮direct child，未冒充独立双源数值。独立post-probe交叉验证的是这些已记录PID的`/proc`项确实消失、一次性根确实消失、`4142／4143`确实无listener。旧Bun identity则由controller多时点比较和controller结束后的独立`/proc`＋`ss`观察两种路径共同确认。

## 实际执行结果

- **主smoke**：语法检查＋隔离controller执行，退出码`0`；controller verdict为`PASS_KEY_BACKUP_PORT_SMOKE_R3`，错误和cleanup错误均为空。
- **独立post-state**：重新读取current main、祖先关系、历史child PID、一次性根和loopback listener；退出码`0`。结果为两个历史child均不存在、一次性根不存在、`4142／4143`无listener、旧Bun继续双栈监听`4141`。
- **最终身份复核**：controller前后允许字段与独立`/proc`解析一致，旧Bun仍为PID`818465`、starttime`2138402`、cwd`/home/xp/src/copilot-api-js`、cgroup`0::/init.scope`、argc`5`；没有读取、打印或hash raw cmdline内容。
- **仓库边界**：执行前后产品路径tracked diff均为空；既有其他文档／verification WIP未被本轮修改。本轮未运行或声称全仓pytest、Ruff或Pyright，因为用户要求的是固定备用端口真实主路径复跑，而非代码回归套件。

## 未验证边界

以下均为**未验证**，不是本轮已证实缺陷：

- retry frontier、重试后final-attempt request fact切换、quota／request quota／global quota、resident backpressure和slow consumer。
- 真实socket partial-write、首body发送结果不确定、RST、首block后cancel、post-commit protocol error以及in-flight open block期间SIGTERM竞态。
- semantic reorder、reasoning／tool多block、zero-content terminal、`max_output_tokens` incomplete、其他incomplete reason、failed／error／无terminal EOF与完整terminal／usage矩阵。
- 完整History parity，包括partial／uncertain delivery、response conversion facts、typed usage细节、多attempt与reaper行为。
- 真实credential、真实upstream、官方Anthropic SDK consumer、HTTP／WebSocket parity、IPv6备用listener、socket activation、真实systemd manager／effective cgroup、重复restart和rolling。
- 完整bridge Acceptance、部署、生产数据迁移、停止旧Bun、接管`localhost:4141`与cutover。

## 最终结论

`main@d903d726baf3f15bf46ddf17384564fee154ed6a`在固定备用端口上的本轮点名关键主路径为 **`PASS_KEY_BACKUP_PORT_SMOKE_R3`**。Nonstream、stream完整text block前withholding、Responses SSE→Anthropic SSE、唯一`message_stop`、stream History request conversion fact、首block前cancel cleanup、app SIGTERM lifespan cleanup、自建app／fake的pidfd精确终止与原handle wait／reap、临时根与备用端口释放、旧Bun零signal／incarnation不变均取得真实运行证据。R2的stream History fact缺口已在current main现场关闭；retry、quota、partial-write及其余明确边界没有扩测，完整产品继续`UNVERIFIED`，生产仍保持`NO_CUTOVER`。

# Current main 备用端口关键主路径 smoke R2

## 判定与范围

- **执行对象**：主树 `/home/xp/src/ghc-api-proxy-py`，branch `main`，完整 HEAD `e9fb2771d6e040c761bb4074e3fcf2547caece28`。每个 load-bearing shell 调用均在同一调用内打印并断言物理 cwd、Git top-level、branch 与完整 HEAD；执行前后 `src`、`tests`、`contrib` 与 `pyproject.toml` 的 tracked diff 均为零。工作树已有文档 WIP 与独立 verification 资产，但未改变本轮 candidate 的产品代码身份。
- **本轮 verdict**：**`PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`**。固定拓扑 `127.0.0.1:4142` app＋`127.0.0.1:4143` fake 上，nonstream、stream text withholding、Responses SSE→Anthropic SSE、唯一 success terminal、client cancel cleanup、app SIGTERM lifespan cleanup、两个 direct child 的 wait／reap、备用端口释放与旧 Bun 零 signal／incarnation 不变均通过。
- **History 判定**：**nonstream request facts 通过；stream request conversion fact 存在偏差。** 两条成功 History entry 都保留 original Anthropic request、`metadata`、requested／resolved model与 completed终态；nonstream usage 中存在 typed request fact `metadata.smoke_extra／metadata_not_allowlisted／attempt=0`，但同一 stream fixture 的 usage 中没有该 request conversion fact。由于用户把 History request facts限定为“若可”，该缺口不推翻上述关键主路径 smoke PASS；它仍是实证能力缺口，不能表述为 stream History facts 已通过。
- **明确排除**：未扩展 retry、quota／resident backpressure、真实 socket partial-write／RST、semantic reorder、完整 usage／terminal矩阵、真实 credential／upstream、systemd manager／cgroup、部署或 cutover。完整 bridge 与完整 Acceptance 继续为 `UNVERIFIED`；本报告不授权部署或切换生产 `4141`。
- **唯一仓库写入**：`docs/tmp/260807-final-backup-port-smoke-r2.md`。controller、fake、配置、状态、日志与结构化证据只位于 `/tmp`；没有新增仓库 harness 或测试文件，没有修改生产代码。

## 从冻结要求推导的验收矩阵

| 验收项 | 用户可观察判据 | 结果 | 实证 |
|---|---|---|---|
| candidate身份 | current `main@e9fb277…`；允许 tracked文档WIP，但产品代码路径必须无diff | **PASS** | shell gate确认`HEAD == refs/heads/main == e9fb2771…`；`git diff --quiet -- src tests contrib pyproject.toml`前后均退出0 |
| 端口与环境隔离 | spawn前`4142／4143`无listener；隔离`HOME／XDG_CONFIG_HOME／XDG_DATA_HOME／TMPDIR`；受控显式config | **PASS** | `r8`记录`ports_preflight_empty=true`与`isolated_settings=true`；settings preflight确认generic upstream只指向`127.0.0.1:4143`、History与tokenization状态仅位于一次性根 |
| 拒绝CLI token | 不继承或使用六个token／config入口；argv无`--github-token／-g` | **PASS** | 六个presence均为false；child env从空字典按allowlist构造；`cli_token_absent=true`；未读取、打印或hash任何credential value |
| nonstream | 真实`POST /v1/messages`走Responses leg，返回Anthropic Messages JSON，恰好一次Responses exchange | **PASS** | HTTP 200；单一text block为`backup-port-r2-ok`；fake wire含`input`、`model=smoke-model`、`stream=false`且不含`messages` |
| stream withholding | authoritative完整text block前零success headers、零`message_start`、零body bytes | **PASS** | raw socket在`0.35s`观测窗口收到`0`字节；窗口后才收到HTTP 200与SSE body。该时长只是本轮观测值，不是性能阈值 |
| Anthropic SSE与terminal | 下游不泄漏Responses事件；事件序列合法；text完整；`message_stop`恰好一次 | **PASS** | strict parser得到`message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop`；text为`hello bridge`；`message_stop_count=1` |
| History request facts | 原始request与requested／resolved model保留；若路径支持，应承载typed request conversion fact | **PARTIAL／偏差** | 两条成功entry均保留original request、metadata与model facts；nonstream fact存在，stream fact缺失，详见“发现” |
| cancel cleanup | 首block前客户端断开时零success bytes；上游观察断连；History不记completed | **PASS** | cancel raw socket early bytes为`0`；fake记录`upstream_disconnect_seen=true`；对应唯一History entry为`failed` |
| SIGTERM cleanup | 仅向本轮app发送一次SIGTERM；lifespan完整；app与fake均由原handle wait／reap | **PASS** | app pidfd发送一次SIGTERM；日志依序出现`Shutting down`、`Waiting for application shutdown.`、`Application shutdown complete.`、`Finished server process`；app与fake return code均为`-15`且`wait_reaped=true` |
| 旧Bun不变 | 前后同一PID＋starttime＋cwd＋cgroup＋cmdline shape＋双栈listener inode；零signal | **PASS** | 前后均为PID`818465`、starttime`2138402`、cwd`/home/xp/src/copilot-api-js`、cgroup`0::/init.scope`、argc`5`、inode`15964765／16023105`；`signals_to_bun=0` |
| 最终收口 | app／fake历史PID消失；临时根消失；`4142／4143`无listener | **PASS** | 独立post-state探针确认PID`1708447／1708442`无`/proc`项、`/tmp/ghc-final-smoke-azaiuvhi`不存在、两端口listener数均为0 |

## 有效运行证据

最终有效运行是一次性controller的`r8`轮次；命令固定current tree与HEAD，先检查产品路径无diff和备用端口空闲，再用`setsid --wait env --ignore-signal=INT`启动controller。controller用同一临时脚本的`--fake`模式和真实`python -m app start --host 127.0.0.1 --port 4142 --config <ephemeral-config>`模式创建两个direct child，spawn后立即通过libc `pidfd_open`绑定incarnation，清理时通过libc `pidfd_send_signal`精确发信号并用原`Popen.wait()`回收。最终controller退出码为`0`，结构化结果为`PASS_KEY_BACKUP_PORT_SMOKE_R2`，`cleanup_errors=[]`。

fake实际捕获三次Responses exchange，case顺序为nonstream、stream happy、stream cancel，对应`stream`标志为`false／true／true`。三次wire全部含`input`、不含`messages`，resolved model均为`smoke-model`，没有额外exchange；该计数只用于本轮无retry fixture，不外推retry矩阵。

fake按跨chunk且使用CRLF的合法Responses SSE text lifecycle发送`response.created → response.output_item.added → response.content_part.added → response.output_text.delta → response.output_text.done → response.content_part.done → response.output_item.done → response.completed`。前几轮临时fake曾因缺少合法content-part事件而得到typed 502，且一次controller能力探针错误假设`os.pidfd_open`存在；这些轮次均作废。每轮残留均先用固定listener inode、PID、starttime与完整argv确认归属，再通过libc pidfd精确终止；最终有效`r8`从无listener状态重新开始，并由独立post-state复核零残留。失败轮次只说明fake／controller需要校准，不是产品失败证据。

## 既有测试交叉验证

同一`main@e9fb2771…`上重跑以下现有selector：

- `tests/smoke/test_anthropic_responses_route.py::test_anthropic_nonstream_responses_leg_is_a_real_single_owner_asgi_flow`。
- `tests/smoke/test_anthropic_responses_stream_route.py::test_chunked_responses_sse_reaches_real_anthropic_asgi_after_complete_block`。
- `tests/smoke/test_anthropic_responses_stream_route.py::test_disconnect_while_prefetching_closes_upstream_without_success_headers`。
- `tests/smoke/test_anthropic_responses_stream_route.py::test_prefetch_disconnect_waits_for_checkpoint_cleanup_after_recancellation`。

执行结果为`6 passed in 2.54s`，退出码`0`。同一selector集的`--collect-only -q`独立列出6个node ID并报告`6 tests collected in 1.95s`，退出码`0`；数量口径是该完整HEAD上四个selector的参数化展开，execution与collection两种原理相符。该测试集只交叉验证本轮关键内部接缝，不替代真实4142／4143进程smoke，也不覆盖被明确排除的retry、quota或partial-write。

## 发现

### [偏差] Stream History没有承载final attempt的request conversion fact

- **被违反的验收项**：本报告矩阵“History request facts”要求在路径支持时保留typed request conversion fact；对应冻结产品意图是同一请求的History不从wire裁剪结果覆盖original payload，并记录可审计的request conversion facts。
- **失败输入**：stream与nonstream都发送`metadata={"user_id":"history-smoke","smoke_extra":"preserve-only-in-history"}`。converter应把`metadata.user_id`写入Responses wire，并为不allowlist的`metadata.smoke_extra`产生`degrade／metadata_not_allowlisted` fact。
- **实证结果**：真实`GET /history/api/entries?session_id=session-final-smoke`返回两条completed entry。两条都保留original request和metadata；nonstream usage包含`{"provenance":"request","attempt":0,"field_path":"metadata.smoke_extra","disposition":"degrade","reason":"metadata_not_allowlisted"}`，stream usage的`conversion_facts`不含该fact。有效`r8`结构化证据明确记录`nonstream_request_fact_present=true`与`stream_request_fact_present=false`。
- **代码接缝证据**：最终文件`src/app/pipeline/executor.py:361`在nonstream response body处理分支内设置`context.conversion_facts`，而stream路径在该赋值前绕过body处理；最终文件`src/app/history/consumer.py:145`的stream usage projection因此只能看到空facts。该根因已明确，建议主会话交给implementer按现有`fix/stream-request-facts`方向处理；本验证者不修改生产代码。
- **严重性与范围**：该偏差影响stream History可审计事实，不影响本轮外部stream SSE、cancel或cleanup通过结论。由于用户明确写“History request facts若可”，本报告采用`PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`，而不是把整个关键smoke判FAIL；也不把History标成全PASS。

## 进程与清理终态

| Role | PID | starttime ticks | listener | 终止与回收 |
|---|---:|---:|---|---|
| fake | `1708442` | `3272411` | `127.0.0.1:4143`，inode`21137349` | 绑定pidfd后精确SIGTERM；return code`-15`；原handle wait／reap；最终`/proc`项不存在 |
| app | `1708447` | `3272431` | `127.0.0.1:4142`，inode`21150973` | 绑定pidfd后精确发送一次SIGTERM；return code`-15`；完整lifespan；原handle wait／reap；最终`/proc`项不存在 |
| 旧Bun | `818465` | `2138402` | `127.0.0.1:4141` inode`16023105`；`[::1]:4141` inode`15964765` | 只观察；本轮signal数`0`；前后完整identity相等 |

表中的app／fake PID、starttime与listener inode由同一个controller在`r8`中生产，未由第二个独立生产者交叉验证；它们只用于标识该轮child。独立post-state交叉验证的是这些已记录PID与临时根确实消失、备用端口确实空闲，不把同源数值冒充双源计数。旧Bun的PID、starttime与listener inode则由controller前后快照和最终独立`/proc`／listener探针两种观测重复确认。

最终独立探针没有复用controller结论，而是重新从`/proc/net/tcp* → /proc/<pid>/fd`反查listener owner，并重新读取starttime、cwd、cgroup与cmdline argc。结果确认旧Bun仍为同一incarnation，app／fake历史PID与一次性根均消失，`4142／4143`均为零listener。

## 结构怪味与处置

| `file:line`／surface | 怪味类型 | 处置 |
|---|---|---|
| `src/app/pipeline/executor.py:361`的nonstream-only `context.conversion_facts`赋值接缝 | lifecycle事实只在一个response分支发布，stream与nonstream同一语义出现弱一档实现 | 本轮不改生产代码；以真实History API固定为实证偏差，交回既有stream request facts修复线 |
| `src/app/history/consumer.py:145`的stream usage projection | stream History单独构造usage并固定空`conversion_facts`，与nonstream共享事实源漂移 | 同上；后续修复应在共享context facts层解决，而不是仅在报告或SQLite输出层补值 |
| 本轮一次性fake | 标准库HTTP fake若遗漏真实Responses content-part lifecycle，会让合法性guard返回typed 502；若禁用`SO_REUSEADDR`，连续校准又会被TIME_WAIT假红 | 最终`r8`前已按现有真实route fixture校准完整event序列，并只在确认无活动listener后允许地址重用；失败轮次全部作废，不冒充产品证据 |
| 当前仓库缺少用户本轮允许范围内的持久化备用端口harness | 真实进程smoke依赖一次性controller，调试中断时必须额外冻结inode／incarnation并精确清理 | 遵循用户“不开发新harness”；本轮以pidfd、原handle wait／reap和独立post-state关闭风险，不新增验证基础设施 |

## 未验证边界

以下均为**未验证**，不是本轮已证实缺陷：

- retry frontier、quota、resident backpressure、slow consumer与真实socket partial-write／RST。
- semantic reorder、reasoning／tool多block、zero-content terminal、failed／error／无terminal EOF与完整usage parity矩阵。
- stream request facts修复后的行为；本轮只证明current main存在缺口。
- in-flight open block期间SIGTERM的drain／abort竞态、重复restart、IPv6备用listener、socket activation与真实systemd manager／effective cgroup。
- 真实credential、真实upstream、官方SDK consumer、HTTP／WebSocket parity、完整Acceptance、部署与cutover。

## 最终结论

`main@e9fb2771d6e040c761bb4074e3fcf2547caece28`在固定备用端口上的用户点名关键主路径为 **`PASS_KEY_BACKUP_PORT_SMOKE_R2_WITH_STREAM_HISTORY_FACT_GAP`**。Nonstream、stream withholding、Anthropic SSE、唯一terminal、cancel cleanup、SIGTERM lifespan cleanup、自建进程wait／reap与旧Bun零signal／incarnation不变均取得真实运行证据；现有关键selector集执行与collect-only均为6项且全部通过。Stream History request conversion fact缺失已作为实证偏差单列，不被“若可”措辞洗成PASS。完整产品继续`UNVERIFIED`，部署与cutover继续不在本轮授权范围内。

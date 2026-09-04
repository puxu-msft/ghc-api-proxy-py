# 备用端口 smoke 设计与恢复验收记录

## 结论

- **候选身份**：`/home/xp/src/ghc-api-proxy-py` 的 `HEAD` 与 `refs/heads/main` 在执行 gate 时均为 `b91e58a29324b11840002efc53ed6f869b800c39`。应用源码、测试、`pyproject.toml` 与 `uv.lock` 相对该提交无 tracked／staged 差异；并行文档 WIP 未被读取为产品代码，也未被覆盖。
- **当前可执行层 verdict**：**`PASS_CURRENT_LAYER`**。已在 `127.0.0.1:4142` 启动 Python 服务，并在 `127.0.0.1:4143` 启动本地 fake generic Responses upstream；liveness、readiness、status、config 脱敏、真实 HTTP non-stream Anthropic→Responses→Anthropic、当前 stream fail-closed 与自建进程清理均取得实证。
- **未来 stream route verdict**：**`UNVERIFIED`**。Current main 对 selected Responses＋`stream=true` 的冻结边界仍是 HTTP `400`、code `responses_stream_not_supported`、零新增 upstream call；这证明当前 fail-closed 正确，不证明 stream route 已实现。Stream route 合并后必须按本文后半部分重新执行真实 loopback route／socket 门。
- **部署 verdict**：**`NO_CUTOVER`**。本轮没有 stop、signal、reload 或替换旧 Bun，没有占用或释放生产 `4141`，没有安装 unit、操作 manager、迁移数据或修改全局配置。

## 冻结验收矩阵

本轮先从 current FINALIZED Spec 的外部行为与用户本轮边界推导以下矩阵，再读取 current 实现与现有测试。矩阵只覆盖无真实凭据备用端口 smoke，不扩张为完整 bridge Acceptance。

| ID | 用户可观察判据 | Current main expected | 本轮结果 |
|---|---|---|---|
| SAFE-01 | 旧双栈 Bun 前门保持原 owner，不接收任何本轮信号 | `127.0.0.1:4141` 与 `[::1]:4141` 始终由同一 Bun PID 持有 | **PASS** |
| SAFE-02 | 备用 listener 只使用已确认空闲的 loopback 端口 | Python app＝`127.0.0.1:4142`；fake upstream＝`127.0.0.1:4143` | **PASS** |
| SAFE-03 | 不读取或打印真实 token 值 | 只记录三个 GitHub token 环境变量是否存在 | **PASS**；三者均 absent |
| SAFE-04 | 不写全局配置或生产数据 | 所有 XDG、tokenization 与运行日志落入一次性目录；History disabled | **PASS** |
| RUN-01 | 进程实际启动，而非只检查文件或 import | `4142` 出现 Python listener，PID／cwd／cgroup 可追溯 | **PASS** |
| RUN-02 | liveness 反映进程可响应 | `GET /health/liveness`＝HTTP `200`＋`{"status":"ok"}` | **PASS** |
| RUN-03 | readiness 反映 fake generic upstream、catalog 与 runtime 已初始化 | `GET /health/readiness`＝HTTP `200`＋healthy；`GET /api/status`＝ready | **PASS** |
| RUN-04 | effective config 可审计但 secret 已脱敏 | host／port／upstream type／fake base URL／隔离状态路径正确；API key 显示为 `***` | **PASS** |
| NS-01 | Anthropic non-stream 请求只调用 Responses fake，最后一跳不是 Chat shape | fake 捕获一次 `/v1/responses`；wire 含 `input`、`max_output_tokens`、`stream=false`，不含 `messages` | **PASS** |
| NS-02 | fake Responses body 转为合法 Anthropic message | HTTP `200`；thinking 与 text 顺序保持；carrier 使用项目主 v1 prefix；usage 按冻结算式归一 | **PASS** |
| STR-NOW-01 | 当前未合并 stream route 时 fail closed，且不误发 upstream | HTTP `400`＋`responses_stream_not_supported`；fake `/v1/responses` 调用计数不增加 | **PASS**；完整 stream 仍 `UNVERIFIED` |
| CLEAN-01 | 只终止本轮创建的 Python app，并完成 lifespan cleanup | 只向 app PID 发 `SIGTERM`；日志出现 shutdown complete 与 finished server process | **PASS** |
| CLEAN-02 | 自建 listener 与临时状态全部消失，旧 Bun 身份不变 | `4142`／`4143` 无 listener；一次性目录删除；4141 PID／cwd／cgroup／cmdline 前后相等 | **PASS** |

## 实际运行拓扑与进程事实

执行前 listener：

| Port | 地址族 | Owner |
|---:|---|---|
| 4141 | `127.0.0.1` | Bun PID `1623`，fd `22` |
| 4141 | `[::1]` | Bun PID `1623`，fd `23` |
| 4142 | 无 listener | 空闲 |
| 4143 | 无 listener | 空闲 |

旧 Bun 的只读身份在执行前后均为：

- PID：`1623`。
- cwd：`/home/xp/src/copilot-api-js`。
- cgroup：`0::/init.scope`。
- cmdline：Bun 运行 `./packages/cli/src/main.ts start`。
- 本轮向该 PID 发送的 signal：**零**。

执行期间：

| Role | PID | cwd | cgroup | Listener |
|---|---:|---|---|---|
| Python app | `119342` | `/home/xp/src/ghc-api-proxy-py` | `0::/init.scope` | `127.0.0.1:4142` |
| Fake Responses upstream／harness | `119050` | `/home/xp/src/ghc-api-proxy-py` | `0::/init.scope` | `127.0.0.1:4143` |
| 旧 Bun | `1623` | `/home/xp/src/copilot-api-js` | `0::/init.scope` | 双栈 `4141`，未变化 |

执行后只有旧 Bun 的双栈 `4141` listener；`4142`／`4143` 均已释放。一次性源码／状态根与 harness 脚本均已删除。

## 配置隔离与凭据边界

本轮 GitHub token 环境变量存在性结果如下，未读取或输出任何值：

| Variable | Presence |
|---|---|
| `COPILOT_API_GITHUB_TOKEN` | absent |
| `GH_TOKEN` | absent |
| `GITHUB_TOKEN` | absent |

服务使用 `upstream.type=generic` 与仅供本地 fake 的非真实占位 API key，因此无需 GitHub／Copilot token也能验证 startup、catalog load、health、config 与 Responses route。`/api/config` 实测将该占位 key 脱敏为 `***`。

隔离策略：

- `HOME`、`XDG_DATA_HOME`、`XDG_CONFIG_HOME` 指向本轮一次性目录。
- `history.enabled=false`，不创建或打开生产 History DB。
- `tokenization.state_path` 指向本轮一次性目录。
- `model_refresh_interval=0`，只在 startup 从 fake `/v1/models` 读取一次 catalog。
- tracing 与 TUI disabled。
- 未设置 `GHC_CONFIG`，未读取项目外或用户目录中的配置文件。
- 结束后一次性目录不存在。

Readiness 的三个 check 在 generic fake 模式下均为 true。这里的 `github_token=true` 与 `copilot_token=true` 是 generic upstream 初始化后的 runtime-ready 兼容字段，**不是**真实 GitHub／Copilot 凭据校验成功；真实 token／真实上游 canary仍未验证。

## 当前 main 的可复现实证

### 现有无凭据 route smoke

在固定代码树上执行现有 `tests/smoke/test_anthropic_responses_route.py`，禁用 pytest cache 与 Python bytecode 写入：

- Exit code：`0`。
- Pytest summary：`8 passed in 4.91s`。
- 该数量只来自本次 pytest summary，未用第二种计数原理交叉验证；因此数字口径为“该文件在本轮 pytest 运行报告的 case 数”，不是仓库测试总数。

### Health 与 config

| Probe | Status | Key result |
|---|---:|---|
| `/health/liveness` | 200 | `status=ok` |
| `/health/readiness` | 200 | `status=healthy`；三个 checks 均 true |
| `/api/status` | 200 | `ready=true` |
| `/api/config` | 200 | host `127.0.0.1`；port `4142`；generic upstream指向`127.0.0.1:4143/v1`；API key已脱敏；History disabled；tokenization路径属于临时根 |

### Non-stream Anthropic→Responses fake upstream

客户端向 `POST http://127.0.0.1:4142/v1/messages` 发送：model `smoke-model`、`max_tokens=64`、`stream=false` 与一个 user text turn。

Fake upstream实际观察：

- Startup：一次 `GET /v1/models`。
- Request：恰好一次 `POST /v1/responses`。
- Responses wire：`model=smoke-model`、`max_output_tokens=64`、`stream=false`；Anthropic user turn转换为 Responses `input` message；不存在 Chat／Anthropic `messages` 字段。

客户端实际观察：

- HTTP `200`，request id `req_backup_port_smoke`。
- Content block类型顺序为 `thinking → text`。
- Thinking visible summary为 `backup checked`，signature使用 `ghc-api-proxy:synthetic-reasoning:v1:` prefix；报告不记录完整 carrier payload。
- Text为 `backup-port-ok`。
- Usage为 `input_tokens=6`、`cache_read_input_tokens=2`、`cache_creation_input_tokens=1`、`output_tokens=4`，与 fake 的 `T=9,R=2,W=1,O=4` 满足冻结算式 $I=\max(0,T-R-W)=6$。

### Current stream fail-closed

将同一请求改为 `stream=true`：

- 客户端得到 HTTP `400`。
- Anthropic-compatible error code为 `responses_stream_not_supported`。
- Fake `/v1/responses` 调用计数在该请求前后均为 `1`，即 stream reject没有发起第二次 upstream exchange。

这条是 current main 的正确负路径，不应在 stream route 合并前改成“必须成功”。合并后若仍返回该错误，则 STREAM-MERGE-01 必须判红。

## 清理判据校准

本轮只向自建 Python app PID `119342` 发送一次 `SIGTERM`。没有向旧 Bun发送signal，也没有使用 `pkill`、`killall`或模糊进程匹配。

Python app的OS return code为 `-15`，但不能据此误判为lifespan未清理。当前环境中的 Uvicorn `server.py` 在捕获信号、完成 shutdown并恢复旧handler后会调用 `signal.raise_signal(captured_signal)`；本轮应用日志按序出现：

1. `Shutting down`。
2. `Waiting for application shutdown.`。
3. `Application shutdown complete.`。
4. `Finished server process [119342]`。

因此本轮“干净退出”的被测对象是应用生命周期与资源状态，而不是“进程码必须为0”。独立终态证据为：lifespan完整日志成立；`4142`／`4143` listener消失；临时状态根删除；旧 Bun完整身份前后相等。四项全部成立。

## Stream route 合并后的执行门

### 固定拓扑与前置门

默认继续使用固定备用端口：app＝`127.0.0.1:4142`，fake upstream＝`127.0.0.1:4143`。每次执行都必须先重新检查两个端口为空；任一已占用时 fail closed，不抢占、不signal owner。若需要并行运行，可将 fake upstream改为内核分配的loopback动态端口，并把实际端口通过隔离环境传给app；生产`4141`始终不参与。

每轮必须记录：

- 候选完整commit、`refs/heads/main`或指定候选ref、branch与code-tree tracked cleanliness。
- Spec与Acceptance内容身份。
- app／fake的PID、cwd、cgroup、cmdline与listeners。
- 旧Bun PID／cwd／cgroup／cmdline及双栈listener前后相等。
- GitHub token只记录presence；若存在真实token，也不得输出值。无真实token时继续用generic fake完成确定性门。

### 合并门分层

| Gate | Required behavior | 失败判定 |
|---|---|---|
| STREAM-MERGE-00 回归 | 本文RUN、NS与CLEAN全部重跑；non-stream仍只调用一次Responses，dual-capability `auto`仍保持Messages | 任一current已通过行为回归即红 |
| STREAM-MERGE-01 route接线 | `stream=true`从真实`/v1/messages`进入；实际向fake `/v1/responses`发送`stream=true`且恰好一次；不再返回`responses_stream_not_supported` | 仍typed reject、误走Messages、零调用或多调用均红 |
| STREAM-MERGE-02 wire protocol | Fake按Responses SSE发 `response.output_item.added → delta／authoritative done → response.output_item.done → response.completed`；app下游只输出Anthropic SSE，不泄漏Responses event | Responses event或JSON直接透传、content type错误均红 |
| STREAM-MERGE-03 首block withholding | Fake发送item added与部分delta后暂停；真实raw HTTP reader在authoritative done前观察到零success headers、零`message_start`、零body bytes | 提前200、提前start或任意partial block bytes均红 |
| STREAM-MERGE-04 完整block batch | Done后首批包含同一串行提交中的`message_start → content_block_start → delta → content_block_stop`；index从0连续 | 缺事件、拆成可等待的半batch、index gap或block交错均红 |
| STREAM-MERGE-05 semantic order | Fake制造A先open、B后open但B先done；A完成前零下游block，A完成后按A、B提交 | 按完成顺序先发B、漏A／B或重复均红 |
| STREAM-MERGE-06 terminal | `response.completed`在无open block时产生唯一`message_delta → message_stop`；usage与同fixture non-stream归一值相等 | 重复terminal、open block时成功terminal、usage漂移均红 |
| STREAM-MERGE-07 failure terminal | failed／error／无terminal EOF不得发`message_stop`冒充成功；commit前返回Anthropic HTTP error，commit后返回Anthropic SSE error并关闭 | 错误后success terminal、unknown item静默丢弃均红 |
| STREAM-MERGE-08 lifecycle owner | Route、parser、delivery、hooks、History、attempts与finalize共享同一`RequestContext`；真实exchange数等于attempt数 | 第二context、第二writer、第二finalizer或attempt错数均红 |
| STREAM-MERGE-09 cancel与cleanup | 分别在首block前与首block后断开客户端；上游关闭、不透明retry、未完成block不泄漏、资源归零、finalize一次 | orphan task／socket、重复prefix、completed History均红 |
| STREAM-MERGE-10 shutdown | 对自建app精确SIGTERM；完整block按grace合同drain或明确abort；History／tokenization／upstream cleanup完成；备用listener释放 | 只因收到signal就判通过不够；缺lifespan或资源终态证据均红 |

STREAM-MERGE-03必须使用真实raw socket或能够区分“headers尚未提交”的独立HTTP客户端，不能用内部buffer长度或直接调用async generator代替。STREAM-MERGE-04～06必须由独立Anthropic SSE grammar consumer解析；官方SDK兼容可以另作第二条oracle，但不得以SDK宽松接受覆盖strict grammar红灯。

### 最小 fake SSE happy fixture

合并后的第一轮可先用text happy fixture建立纵向闭环：

1. `response.output_item.added`，item为`id=msg_0,type=message`。
2. 一个或多个`response.output_text.delta`，fake在此处暂停以验证首block前零下游可见。
3. `response.output_text.done`，携带authoritative text。
4. `response.output_item.done`，关闭message source。
5. `response.completed`，携带completed response id、status与终态usage。

该fixture通过后，必须继续增加reasoning与function call：reasoning以item done的summary／`encrypted_content`为authoritative，function call只在arguments与item done齐全后形成一个完整tool block。不得把text happy path升级为完整stream产品`PASS`。

### 正反控制

每个stream gate都必须用同一真实route入口执行正确样本与单缺陷样本。最低正控集合：

- 删除`stream=true` Responses transport接线后，STREAM-MERGE-01必须红。
- 让route在done前写一个byte或提前response start，STREAM-MERGE-03必须红。
- 让sequencer在A未闭合时释放B，STREAM-MERGE-05必须红。
- failed后仍渲染success terminal，STREAM-MERGE-07必须红。
- 建立第二writer或第二finalizer，STREAM-MERGE-08必须红。

变异只能在隔离worktree或测试专用injector中执行，并用冻结exact patch恢复；不得在共享主工作树做整文件恢复。

## 当前未验证项

以下均不得由本轮`PASS_CURRENT_LAYER`外推：

- 真实GitHub／Copilot token、真实model catalog或真Responses upstream连通性。
- 真实 Anthropic Messages upstream与direct Messages运行态回归。
- Responses stream route、真实下游Anthropic SSE、HTTP／WS parity。
- 首block前零headers／body、sink partial write、delivery uncertainty、retry frontier。
- Client cancel、slow consumer、backpressure、request／global memory quota与shutdown竞态。
- History enabled时的持久化、approval、hooks、tokenization calibration与exactly-once finalize全矩阵。
- 备用实例重复启动／restart、IPv6备用listener、systemd socket activation、真实user-manager与effective cgroup limits。
- `cc-daemon` PID／InvocationID不变量；本轮没有操作它，但也没有在本报告中重取完整unit身份。
- 完整bridge Acceptance、live canary、capture corpus、local fault与mutation controls。

## 执行分层结论

### 现在可以做

1. 在每次重新确认空闲后，用`4142`启动隔离Python服务、`4143`启动fake generic upstream。
2. 无真实token执行startup、liveness、readiness、status、config脱敏与现有无凭据route smoke。
3. 从真实HTTP入口执行non-stream Anthropic→Responses fake upstream，并断言最后一跳wire与Anthropic响应。
4. 对current main执行stream fail-closed门，要求`responses_stream_not_supported`且零新增upstream call。
5. 记录自建进程PID／cwd／cgroup／listeners，只向自建app发送精确信号，完成lifespan与listener／临时状态清理复核。

### Stream route 合并后再做

1. 把fake `/v1/responses`升级为可暂停、可分帧的Responses SSE producer。
2. 从真实`/v1/messages` raw HTTP入口执行首block withholding、完整block batch、顺序、terminal与error门。
3. 证明route→parser→delivery→ASGI sink共享同一request owner、单一writer与单一finalize。
4. 增加reasoning、tool、usage parity、cancel、shutdown、retry frontier、partial write与backpressure门。
5. 对每个关键门执行目标单缺陷正控；全部required evidence闭合前，完整stream与完整产品保持`UNVERIFIED`。

## 结构怪味与处置

| `file:line`／surface | 怪味类型 | 处置 |
|---|---|---|
| `src/app/runtime.py:35-48` | Readiness字段名仍以GitHub／Copilot命名，但generic upstream初始化时三项均置true，容易被误读为真实token已验证 | 本报告明确把它解释为generic runtime-ready兼容字段；真实credential gate保持`UNVERIFIED`。长期可考虑增加具名upstream/catalog readiness facts，但这会改变管理面语义，需另行设计与验收。 |
| `src/app/anthropic/client.py:218-226`与`src/app/pipeline/executor.py:192-201` | 同一stream fail-closed合同在client与pipeline两层复述；stream route合并时可能只删一处，留下旁路reject或生命周期漂移 | Stream route切片必须用真实route gate证明不再短路，并扫描两处合同同步移除／收敛；本轮不改生产代码。 |
| `src/app/routes/anthropic.py:92-118` | Current stream分支是Messages raw-byte passthrough，而Responses parser／delivery在独立模块；错误接线可能把Responses SSE当Anthropic SSE透传 | STREAM-MERGE-02要求真实wire只含Anthropic envelope，STREAM-MERGE-08要求同一owner／writer。 |
| `src/app/delivery/anthropic_sse.py:296-435` | Typed delivery core已有连续前缀与单writer，但目前不能证明真实ASGI response-start、partial write与client可见frontier | STREAM-MERGE-03／04／09明确要求真实socket与ASGI sink证据，内部in-memory sink绿灯不得外推。 |
| 本轮harness退出判据 | 进程return code被误当成lifespan清理真相会产生false-red | 已按Uvicorn `capture_signals()`的重新抛signal行为校准为“完整shutdown日志＋listener释放＋临时状态删除＋旧owner不变”的组合判据。 |

## 最终判定

**Current main `b91e58a29324b11840002efc53ed6f869b800c39` 的无凭据、无cutover备用端口当前层为 `PASS_CURRENT_LAYER`；完整Responses stream route与完整bridge产品为 `UNVERIFIED`；部署保持 `NO_CUTOVER`。**

本轮唯一仓库写入是本文件。旧 Bun PID `1623`未被stop／signal，双栈`4141`前后保持；自建`4142`／`4143`进程已退出，listener与临时状态均已清理。
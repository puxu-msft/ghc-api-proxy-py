# 备用端口 smoke 执行记录

## 判定与边界

- **执行对象**：主树 `/home/xp/src/ghc-api-proxy-py`，branch `main`，完整 HEAD `ae84aa9d4330e56b83aefdad977e7d93190ff0d4`；执行前在同一 shell gate 中确认物理 cwd、Git top-level、branch、`HEAD == refs/heads/main`，并确认 tracked tree 无改动。
- **本轮 verdict**：**`PASS_HAPPY_BACKUP_PORT_SMOKE`**。固定拓扑 `127.0.0.1:4142` app＋`127.0.0.1:4143` fake 上的 current-layer non-stream 与已实现 stream happy 主路径通过；首 block withholding、Responses SSE→Anthropic SSE、唯一成功 terminal、commit 前／后错误、首 block 前／后 cancel、精确 shutdown、wait／reap与旧 Bun 不变均取得运行证据。
- **结论上限**：本轮不是 R3 全量 `PASS_STREAM_CANDIDATE_BACKUP_PORT_ENTRY`。`STREAM-MERGE-05` semantic reorder、完整 usage parity、failed／error／EOF全矩阵、History enabled运行态、retry／quota／backpressure、真实 partial-write、完整 shutdown竞态与R3全部变异控制仍未验证；不得从本轮 PASS 外推为完整 bridge、部署或 cutover PASS。
- **代码评审门**：`docs/tmp/260807-resume-review-main-stream-route.md`绑定同一完整 HEAD，结论为 stream slice `0 blocker／0 major`；其范围是 stream route＋capability／History合成，不覆盖本轮一次性runtime harness。R3计划要求的仓库内`verification/backup_port_stream_smoke.py`与`tests/unit/test_backup_port_stream_smoke_safety.py`在当前 HEAD 不存在，因此本轮按用户指定的happy候选运行范围执行，并把R3完整Phase 0／变异控制留作未验证边界。
- **禁止动作**：未安装unit，未操作systemd／user manager，未cutover，未改`4141`，未向旧 Bun发送signal，未读取或记录credential value、配置内容、raw cmdline、cmdline hash或secret hash。

## 凭据、配置与启动旁路

父进程只记录以下入口presence；本轮均为`false`：

| 入口 | Presence |
|---|---|
| `COPILOT_API_GITHUB_TOKEN` | `false` |
| `GH_TOKEN` | `false` |
| `GITHUB_TOKEN` | `false` |
| `GHC_AUTH__GITHUB_TOKEN` | `false` |
| `GHC_AUTH__TOKEN_FILE` | `false` |
| `GHC_CONFIG` | `false` |

app与fake的child env均从空字典按allowlist构造；六个具名入口、所有未批准`GHC_*`以及大小写proxy变量均absent。隔离`HOME`、`XDG_CONFIG_HOME`、`XDG_DATA_HOME`、`TMPDIR`均位于一次性根；run cwd默认config、隔离XDG默认config、隔离XDG默认token与显式`auth.token_file`在启动前均absent。

同一不可变`LaunchSpec`用于preflight与spawn；executable、cwd、env与config投影逐项相等。持久化argv只记录hash-free shape：

- app：`<python> -m app start --host <loopback> --port <port> --config <ephemeral-path>`。
- fake：`<python> <ephemeral-script> --host <loopback> --port <port>`。
- app／fake的`sensitive_slot_present=false`，`unapproved_option_present=false`；不存在`--github-token`、`--github-token=…`、`-g`或attached short form。

无服务settings preflight确认：upstream为`generic`；base URL精确指向本轮loopback fake；effective host／port与`LaunchSpec`一致；`auth.github_token`不存在；`auth.token_file`已配置但文件不存在；History disabled；tokenization state位于一次性根。preflight后该token file仍不存在。

## 进程与listener身份

### 旧 Bun incumbent

执行前后均为同一incarnation：

- PID：`818465`。
- `/proc/<pid>/stat` starttime：`2138402` ticks。
- cwd：`/home/xp/src/copilot-api-js`。
- cgroup：`0::/init.scope`。
- cmdline：argc＝`5`；hash-free shape为`<executable> <arg> <path> <arg> <option>`；敏感槽不存在；同轮raw tuple仅在内存比较，前后`equal=true`。
- IPv4 listener：`127.0.0.1:4141`，inode `16023105`，由同一PID fd反查拥有。
- IPv6 listener：`[::1]:4141`，inode `15964765`，由同一PID fd反查拥有。
- 本轮向旧 Bun发送signal数：`0`。

PID由两枚listener inode分别经`/proc/net/tcp* → /proc/<pid>/fd`反查为同一owner；starttime、cwd、cgroup、cmdline内存tuple与listener集合在fake启动前、app运行期间、关键gate后与最终收口均保持一致。

### 本轮直接child

| Role | PID | starttime ticks | cwd | cgroup | cmdline shape | Listener |
|---|---:|---:|---|---|---|---|
| fake | `1566875` | `3010403` | `<ephemeral-root>/run` | `0::/init.scope` | `<executable> <path> --host <loopback> --port <port>` | `127.0.0.1:4143`，inode `20325840` |
| app | `1566891` | `3010425` | `<ephemeral-root>/run` | `0::/init.scope` | `<executable> -m <module> <arg> --host <loopback> --port <port> --config <ephemeral-path>` | `127.0.0.1:4142`，inode `20328034` |

两个child均由controller直接`Popen`，spawn后立即绑定libc `pidfd_open`结果、process handle与初始incarnation；listener inode均从child fd反查为同一owner。平台能力探针确认libc同时提供并成功执行`pidfd_open`与`pidfd_send_signal(..., 0)`；未降级为进程名、端口或裸PID模糊认领。

## 实际验收结果

### Current-layer回归

- 真实进程non-stream：客户端`POST /v1/messages`得到HTTP `200`与单一text block `backup-port-ok`；fake只收到一次Responses request，wire含`input`、`model=smoke-model`、`max_output_tokens=64`、`stream=false`，不含`messages`。
- 仓库既有回归：导入路径探针为`/home/xp/src/ghc-api-proxy-py/src/app/__init__.py`；执行`tests/smoke/test_anthropic_responses_route.py`与四个对应stream happy／error／cancel selector，pytest报告`25 passed in 3.63s`，退出码`0`；同一selector集`--collect-only`得到`25 tests collected in 1.68s`。数量口径为该selector集在本HEAD的参数化展开，collection与execution两种路径交叉一致。

### STREAM-MERGE happy slice

| Gate | 本轮状态 | 实证 |
|---|---|---|
| `STREAM-MERGE-00` | **PASS（本轮范围）** | non-stream真实route只发生一次Responses exchange；既有current-layer selector集全绿；app／fake最终wait／reap。dual-capability `auto`的真实备用进程Messages路径未单独实跑，保留为边界。 |
| `STREAM-MERGE-01` | **PASS** | `stream=true`从真实`/v1/messages`进入；fake收到`stream=true` Responses wire，未返回旧`responses_stream_not_supported`。 |
| `STREAM-MERGE-02` | **PASS** | fake以跨chunk且含CRLF的Responses SSE发帧；下游strict grammar只解析到`message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop`，没有`response.*`泄漏。 |
| `STREAM-MERGE-03` | **PASS** | 真实raw socket在fake只发item-added＋partial delta并暂停期间收到`0`字节；单次`CLOCK_MONOTONIC`观测超时约`0.451s`，随后authoritative done才出现HTTP success headers与body。该时长是单轮运行值，未作性能阈值外推。 |
| `STREAM-MERGE-04` | **PASS（text happy）** | 首批严格顺序为`message_start → content_block_start → content_block_delta → content_block_stop`，完整text为`hello bridge`。reasoning／tool多block批次未在本轮runtime fixture展开。 |
| `STREAM-MERGE-05` | **未验证** | 未制造A先open、B后open但B先done的真实进程fixture。 |
| `STREAM-MERGE-06` | **PARTIAL PASS** | success terminal只出现一次`message_delta → message_stop`；未执行与同fixture non-stream的完整usage归一值相等比较。 |
| `STREAM-MERGE-07` | **PASS（关键错误路径）** | precommit未知event返回HTTP `502`、typed code `unsupported_responses_event`；postcommit未知event输出已提交text block后唯一Anthropic `error`，没有`message_stop`。failed／error／EOF所有terminal组合未展开。 |
| `STREAM-MERGE-08` | **PARTIAL PASS** | 本轮客户端请求与fake Responses exchange均为`6`，无第二upstream exchange；同一`RequestContext`／writer／finalizer由对应既有route tests验证，未从外部进程直接观测内部对象identity。 |
| `STREAM-MERGE-09` | **PARTIAL PASS** | 分别在首block前和完整首block后关闭真实client socket；precommit未观察到下游success bytes，postcommit只观察到完整prefix且无success terminal；fake观察到断连，既有二次cancel selector验证finalize与upstream close。History disabled，故未验证completed History禁止条件的真实持久化。 |
| `STREAM-MERGE-10` | **PASS（空闲shutdown）** | 向app绑定pidfd精确发送一次`SIGTERM`；日志依序含`Shutting down`、`Waiting for application shutdown.`、`Application shutdown complete.`与`Finished server process`；app return code为`-15`，fake经自有控制通道return code为`0`；两者均由原handle wait／reap。未覆盖带open block的in-flight drain／abort竞态。 |

fake本轮观测口径为一次catalog GET、一次non-stream Responses POST与五次stream Responses POST；六次Responses wire均含`input`且不含`messages`。该计数由fake内部捕获与controller预期请求序列核对；不用于外推retry／attempt全矩阵。

## 清理与最终运行态

- app通过绑定pidfd精确发送一次`SIGTERM`，在graceful deadline内退出并由原`Popen.wait()`回收；历史`/proc/1566891`项不存在。
- fake通过本轮自有loopback控制通道关闭，在deadline内退出并由原`Popen.wait()`回收；历史`/proc/1566875`项不存在。
- 未发生SIGKILL升级，cleanup errors为空。
- 最终`4142` listener数为`0`，`4143` listener数为`0`。
- 两个child均wait／reap且证据封存后，一次性状态根删除；最终不存在。
- 旧 Bun PID、starttime、cwd、cgroup、内存cmdline comparator与双栈listener inode集合全部不变；没有向旧 Bun发signal。
- 本轮一次性controller、fake脚本与结果暂存只位于`/tmp`；收口后删除。本 smoke执行单元在主树中的唯一写入为本执行记录；并行会话既有或新增文件不归属本执行单元，未被覆盖或清理。

## 结构怪味与处置

| `file:line`／surface | 怪味类型 | 处置 |
|---|---|---|
| `docs/tmp/260807-resume-backup-port-smoke-r3.md:24-25` 对照 current `HEAD` | R3声明的持久化harness与safety test当前缺失，导致runtime安全门只能由一次性controller承担，无法把本轮执行本身纳入同一candidate的持久化复评与变异回归 | 本轮按用户限定的happy候选执行并把结论降为`PASS_HAPPY_BACKUP_PORT_SMOKE`；缺口明确保留为未验证边界，不在本轮新增生产代码或验证基础设施。后续若要取得R3全量入口PASS，应先实现并评审这两项资产。 |
| 本轮raw socket fixture | happy、postcommit error与cancel各自使用独立请求，能够验证关键外部行为，但没有统一覆盖semantic reorder、usage parity与in-flight shutdown | 不把未覆盖gate洗成PASS；逐项标记`PARTIAL PASS`或`未验证`，保留完整矩阵给后续持久化harness。 |

## 未验证边界

以下明确为**未验证**，不是已证实缺陷：

- `STREAM-MERGE-05`跨item semantic reorder。
- success stream与同fixture non-stream的完整usage parity；missing／malformed／inconsistent usage矩阵。
- failed／error／无terminal EOF、incomplete reason、terminal identity与terminal后事件的完整组合。
- reasoning、tool、server-tool、unknown item、零content合法terminal的完整真实进程矩阵。
- History enabled的committed／partial／uncertain持久化、approval、hooks与exactly-once finalize运行态全矩阵。
- retry frontier、quota、resident backpressure、slow consumer、真实socket partial-write／RST与delivery-uncertain全矩阵。
- open block期间SIGTERM的drain／abort、重复restart、IPv6备用listener、systemd socket activation、manager与effective cgroup limits。
- 真实credential、真实upstream、官方SDK consumer、HTTP／WS parity、完整Acceptance、部署与cutover。
- R3施工阶段A要求的仓库内harness／safety tests及其全部单缺陷变异控制；本轮使用一次性runtime harness，不把它冒充已评审的持久化验证资产。

## 最终结论

主树`main@ae84aa9d4330e56b83aefdad977e7d93190ff0d4`在固定备用端口上的已实现happy候选主路径为 **`PASS_HAPPY_BACKUP_PORT_SMOKE`**；current-layer回归与本轮实际覆盖的stream route、wire、withholding、terminal、错误、cancel、shutdown及进程清理均通过。app／fake已完整wait／reap，`4142／4143`已释放，旧Bun incarnation不变且signal数为零。完整STREAM-MERGE矩阵、完整bridge Acceptance、manager操作与cutover继续保持`UNVERIFIED／NO_CUTOVER`。

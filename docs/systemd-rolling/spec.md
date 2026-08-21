# systemd rolling restart 规格

## 状态与权威边界

- **状态**：`FINALIZED`。独立终审输入快照SHA-256为`485163f8a7eabba007c7b5464d69d4ee35717adcbdf2993fb0e05fae7fc5ea0f`，结论为`0 blocker／0 major`。本文完整记录用户于2026-08-08已裁决的产品保证及其必需派生合同，后续实现不得自行改写行为。
- **基线**：`main@a885715a53006a63f53775d6441cd1deba17e7b1`。
- **范围**：新增正式的 systemd 动态 generation rolling 运行面，监听双栈 localhost `4144`。不修改、不停止、不重启、不接管现有 `4141` Bun 服务。
- **与既有文档关系**：本文取代 `../systemd-runtime/plan.md` 中 S7 的未决拓扑描述；既有 socket activation、S3 graceful timeout 与 S4 installer结论仍是历史基座，不覆盖本文新增的rolling合同。

## 用户已裁决事项

1. 正式端口为 `4144`，同时监听 `127.0.0.1` 与 `[::1]`。
2. 使用 systemd 持有的同一组 listener fd，任意数量的generation可重叠；不增加数据面reverse proxy。
3. 接受candidate ready后、新旧generation之间极短的accept竞态窗口；不声称严格原子切流。
4. drain timeout可配置，默认`0`表示无限等待。
5. 任何generation在生命周期中收到第二个`SIGTERM`或`SIGINT`时立即退出，不等待连接或durability barrier。
6. `SO_REUSEADDR`不作为双活机制；实测第二个live listener绑定同端口返回`EADDRINUSE`。`SO_REUSEPORT`虽可双绑，但listener与backlog独立、内核分流不理解readiness／rollback，因此只作为`copilot-api-js`对照，不用于本项目正式拓扑。
7. Quiesce后到达旧generation的新WebSocket upgrade先完成握手，再立即发送close code `1012`并关闭；该短连接不登记为业务operation。
8. Generation数量不设应用层上限。每次rollout分配单调递增且永不复用的generation ID；任意数量的旧generation可因无限drain长期存活。Controller可检测的generation cgroup创建、进程spawn、fd或candidate startup资源失败只允许本次candidate失败并保持当前active generation与drainers不变，不得自动终止drainer腾位。系统级OOM、宿主资源耗尽或管理员强杀仍属于不保证边界。

## 产品目标

### Listener continuity

- `ghc-api-proxy-v4.socket`与`ghc-api-proxy-v6.socket`分别永久持有`127.0.0.1:4144`和`[::1]:4144`。
- Generation换代不关闭、不重启、不重绑这两个socket units。
- 每个generation继承同一组内核listener对象；关闭某generation的fd副本不得影响systemd或另一generation持有的listener。
- Listener与未被应用accept的有限backlog在换代期间连续存在。Backlog满或客户端deadline先到属于有界失败，不得描述为无限排队保证。

### Rolling handoff

1. Controller持久化独立于可回滚canonical rollout state的`next_generation_sequence` frontier，先durably burn ID再执行任何candidate外部动作。Frontier使用至少两份带checksum与epoch的单调副本，更新按write-temp→fsync→replace→fsync-dir逐份完成；恢复取全部有效副本与未compact allocation facts中的最大高水位。无法证明最新高水位时fail closed，禁止继续分配。ID使用canonical decimal：`g`＋至少16位左侧补零，超过16位后自然增长；永不复用，允许gap。失败、cleanup、compaction、canonical state回退和controller restart都不得回退frontier。Generation ID不得由PID、槽位名、存活集合大小或当前最大存活ID推导。
2. Candidate先以`start_serving=False`在两个listener上建立dormant asyncio server；两个family均完成校验与注册后统一arm。任一family失败都撤销全部candidate registrations，candidate不得报告ready。
3. Candidate完成FastAPI lifespan、认证、模型目录、generation状态、两个listener arm与`sd_notify(READY=1)`后，generation control UDS报告`ready=true`。
4. Controller通过candidate私有control UDS执行应用级canary。该探针必须穿过candidate依赖初始化与最小应用处理，并校验generation／release；它不经过共享4144 listener。私有canary失败不得signal old。
5. Candidate私有canary通过后，controller向旧generation发送`SIGUSR2`。
6. 旧generation立即进入`QUIESCING`：readiness转503、停止从两个listener accept，并拒绝其已有keep-alive连接上的新HTTP operation；新WebSocket按已决1012合同关闭。
7. Candidate继续接受新连接；旧generation只完成quiesce前已通过admission并登记的HTTP、SSE与业务WebSocket operation。仅TCP已accept不构成drain资格。
8. 旧generation确认`accepting=false`后，controller才通过共享4144 listener分别执行v4／v6 fresh TCP provenance canary；响应generation／release必须等于candidate，并以`/proc` tuple／listener identity交叉验证实际accept PID。任一family命中old、超时或语义失败都先resume old再进入rollback。双栈provenance canary通过后，controller提交新流量generation。Traffic commit与旧generation drain completion是两个独立状态；观察窗口从traffic commit开始。
9. 旧generation只有在`active_operations == 0`、全部terminal History acknowledgements完成、required tokenization与durability barriers完成后才进入`DRAINED_STANDBY`，保持应用资源可用于快速rollback；controller在观察窗口结束后发送第一次`SIGTERM`，旧generation执行最终cleanup并退出。
10. 切换失败时，controller先向旧generation发送`SIGUSR1`恢复accept并等待ready，再quiesce／停止candidate。恢复旧accept必须先于停止candidate。
11. Predecessor无限drain不阻塞后续rollout；每次rollout继续创建新的generation。Controller必须持续追踪全部active／candidate／draining generations，不自动终止任何drainer。运维可显式向指定generation发送emergency第二终止信号，但它不是新rollout的隐式前置。

### 明确不保证

- 不迁移已accept TCP连接、HTTP parser状态、SSE进度、WebSocket frame queue、上游连接或ASGI task。
- Crash、OOM、`SIGKILL`与第二终止信号不保证连接／History／tokenization无损。
- 不保证严格原子切流；candidate ready到旧generation确认`accepting=false`之间允许极短双accept窗口。
- 不保证History observer WebSocket与pending approval跨generation透明迁移。它们采用显式失败／`1012`关闭与客户端重连合同。
- 不提供跨generation exactly-once；客户端在不确定失败后重试仍可能产生业务重复。
- 不保证默认无限drain最终自行结束；被长SSE／WS占用的generation保持draining，直到自然结束或显式emergency终止。Generation集合可能持续增长，这是用户明确接受的资源模型。

## Unit拓扑

- `ghc-api-proxy-v4.socket`：`ListenStream=127.0.0.1:4144`、`Accept=no`、`FileDescriptorName=http-v4`。
- `ghc-api-proxy-v6.socket`：`ListenStream=[::1]:4144`、`Accept=no`、`FileDescriptorName=http-v6`。
- `ghc-api-proxy-generation@.service`：实例名必须是controller分配的规范generation ID，通过`Sockets=`继承两个socket units；`Type=notify`、`NotifyAccess=main`、`KillMode=control-group`、`TimeoutStopSec=infinity`、独立service cgroup和generation runtime/state路径。
- `ghc-api-proxy-controller.service`：稳定、非数据面控制进程；负责首次activation、rollout、rollback与canonical rollout state，不accept或转发业务字节。
- `ghc-api-proxy-rolling.target`：聚合controller、两个socket与slice；日常rollout不得stop该target或socket units。
- `.socket Service=`固定指向controller，不能固定到blue或green，避免已退役槽位被新连接重新激活。
- Controller是常驻进程而非oneshot。Socket traffic只负责首次激活controller；controller active期间持续reconcile动态generation集合、unit与UDS状态，generation异常退出时不依赖socket再次激活controller。

## inherited fd合同

Generation启动时必须：

1. 验证`LISTEN_PID`等于自身PID。
2. 读取`LISTEN_FDS`与`LISTEN_FDNAMES`，不得假定fd顺序。
3. 恰好接受一个`http-v4`和一个`http-v6`，拒绝缺失、重复和未知名称。
4. 验证两者均为listening TCP stream socket。Socket collector接收显式expected endpoint profile：rolling production profile固定`127.0.0.1:4144／[::1]:4144`；process harness profile注入动态双栈端口。Production profile不得接受动态地址。
5. 不对systemd listener调用`shutdown(2)`。
6. 保留每个listener的master duplicate；每次accept周期向Uvicorn交付新的fd duplicate，使当前generation可stop-accept后resume-accept。
7. activation模式下host／port配置不参与bind。

直接`--host／--port`与旧单`--fd`入口继续兼容，但不构成rolling正式入口。

## Generation生命周期

Application phase转换固定为：

- `STARTING → READY_ACCEPTING → QUIESCING → DRAINED_STANDBY → STOPPING → EXITED`。
- `QUIESCING／DRAINED_STANDBY → READY_ACCEPTING`仅由合法resume命令触发。
- `READY_ACCEPTING`重复resume、`QUIESCING／DRAINED_STANDBY`重复quiesce均幂等。
- 任一非终态可进入`FAILED`；`FAILED`是不可resume的应用故障态，但不是process lifecycle终态。

- `STARTING`：control UDS已可查询，但readiness为503，不accept业务连接。
- `READY_ACCEPTING`：依赖已ready、两个listener均注册，readiness为200，向systemd发送`READY=1`。
- `QUIESCING`：readiness为503，`accepting=false`，不accept新TCP／新keep-alive operation，保留既有operation资源。
- `DRAINED_STANDBY`：active operations为0且全部terminal acknowledgement／required durability barriers完成，不accept，资源保持初始化；允许`SIGUSR1`恢复。
- `STOPPING`：执行一次最终cleanup，不可resume。
- `EXITED`：application phase的正常进程终态。
- `FAILED`：保留failure cause与最后有效phase；controller可对仍存活的FAILED进程记录stop intent并终止它，但不得恢复业务accept。

Controller独立维护process lifecycle：`RUNNING → STOPPING → EXITED`。Application phase与process lifecycle分别持久化；进程异常退出时controller把process lifecycle标记为`EXITED`并保留application `FAILED`及cause。Cleanup eligibility只依赖process lifecycle与运行态硬门，不要求application phase从FAILED转换为EXITED。

Admission例外固定为：`/health/liveness`在请求已进入ASGI时始终返回200；`/health/readiness`只有`READY_ACCEPTING`为200，其他phase返回带generation／phase／accepting的503；generation response header在rolling profile下携带generation与release id。STARTING通常不接业务listener，其状态以control UDS为权威。其余新HTTP operation在quiesce后返回503并带`Connection: close`。

## 信号与控制合同

- `SIGUSR2`：幂等stop-accept并进入drain；不算终止信号。
- `SIGUSR1`：仅在`QUIESCING／DRAINED_STANDBY`幂等resume-accept；恢复失败进入`FAILED`。
- 第一个`SIGTERM／SIGINT`：停止accept，等待active operations按配置drain，然后执行lifespan cleanup并退出。
- 第二个`SIGTERM／SIGINT`：立即`os._exit(143／130)`；可能丢失未flush状态，这是明确的emergency语义。
- `SIGUSR2`之后第一个`SIGTERM／SIGINT`仍算第一个终止信号。
- Controller普通stop使用`systemctl stop`投递第一次SIGTERM。Emergency第二信号必须使用精确`systemctl kill --kill-whom=main --signal=SIGTERM|SIGINT generation-unit`，不能重复`systemctl stop`并假设manager会投递第二信号。Retired／emergency unit在退出前禁止自动restart。

每个generation提供权限为`0600`的Unix control socket，至少支持版本化`status`与`wait`请求。它不是业务proxy，不承载listener fd。状态至少包含generation、PID、phase、ready、accepting、active_operations、listener families、release id与最后错误。

## Operation drain合同

- 在ASGI最外层登记operation，覆盖HTTP、SSE与WebSocket。
- Operation从通过admission并进入应用开始，直到ASGI call返回、stream／WS终止且对应finalize完成后移除。
- Quiesce后除health例外外的新HTTP operation返回503并要求连接关闭。新WebSocket upgrade完成握手后立即发送1012并关闭，不登记为业务operation。
- 已登记operation继续使用token refresh、rate limiter、upstream transport、History与tokenization，直到完成或timeout。
- Quiesce前已通过admission并登记的有限HTTP operation可完成；仅TCP已accept、但尚未开始operation的连接不获得drain资格。SSE／业务WS继续到自然终态或客户端断开。
- timeout正值到期时取消剩余operation，不伪造成功terminal；History记aborted／failed。默认timeout`0`不自动取消。

## Timeout合同

新增`shutdown.drain_timeout`，整数`>=0`，默认`0`：

- `0`表示无限drain。
- 正值从成功stop-accept时开始计时。
- Rolling units在默认`0`下必须使用`TimeoutStopSec=infinity`。
- 正值部署要求manager deadline严格大于drain timeout并保留cleanup margin。
- `SIGUSR2`不是systemd stop，应用自身负责其可选timeout。

旧`shutdown.graceful_timeout=300`只作为旧单实例兼容入口保留，不是rolling默认。最终迁移完成前文档必须区分两套入口，不能让同一unit同时声明互相冲突的deadline。

## 状态与writer合同

- Control UDS、PID、generation status、tokenization state、临时文件和日志全部generation-local。
- Config与credential source共享只读。
- Tokenization snapshot不得由多代写同一路径。启动源按固定优先级选择：首次activation使用版本化empty bootstrap或显式legacy-import immutable snapshot；committed generation存活时经其UDS请求并等待`flush → immutable content-addressed revision/path`；committed generation已死亡时使用controller先前durably发布、独立于进程生命周期的canonical immutable snapshot。Candidate只复制冻结snapshot到generation-local路径。Traffic commit前必须先durably发布candidate的新immutable snapshot；candidate失败不得更新canonical引用；losing generation后续学习不回写新committed source。
- History SQLite允许任意数量generation普通终态并发写，但必须通过真实多进程WAL与锁争用测试；schema migration仅单一owner执行，重叠版本必须schema双向兼容。Terminal write必须有acknowledgement；busy使用有界retry／deadline，不可恢复错误必须使flush／close失败并进入generation状态。Operation归零但terminal durability barrier未完成时不得报告drained／durable。
- Reaper／maintenance同一时刻只有committed generation拥有；旧generation quiesce后停止产生新的maintenance工作，但保留完成在途终态写入的能力。
- Controller是canonical rollout state唯一writer；逻辑commit tuple固定为`(rollout_epoch, committed_generation, committed_release, committed_snapshot_revision/path, maintenance_owner)`。Canonical state采用同目录临时文件写入、flush、`fsync(temp)`、原子`os.replace()`、`fsync(parent)`，带schema/version与完整性校验；损坏时fail closed并从最后一个已验证immutable checkpoint恢复。每次外部动作前写intent checkpoint，动作成功后写completion checkpoint。任意crash恢复后只能得到完整pre-state或完整post-state，不得暴露混合tuple。Durable state复杂度允许`O(L + I)`，其中`L`为当前非终态generation数、`I`为未闭合intent数；已完成checkpoint与已退出明细可compact，ID frontier永久保留。单实例锁拒绝并发rollout。
- Approval creation gate必须在quiesce transition的同一临界区关闭，并等待正在创建approval的临界区退出；随后以`server_restarting`拒绝完整pending集合。之后所有创建尝试稳定失败，不迁移。
- History observer WS在quiesce时以1012关闭并要求客户端重连；已持久化History最终收敛可见。

Promotion与traffic commit属于同一逻辑事务。每个外部子动作都有独立durable intent／ack checkpoint：`old_demote_intent／complete`、`candidate_promote_intent／complete`、`snapshot_publish_intent／complete`、`traffic_tuple_replace_intent／complete`。允许短暂无maintenance owner，不允许双owner。观察期rollback使用新的单调`rollout_epoch`，不回退epoch；其余tuple字段恢复到old generation对应的release／snapshot／maintenance owner。Rollback子动作固定为：`old_resume_intent／complete`→`old_private_canary_complete`→`candidate_quiesce_intent／complete`→`old_shared_v4_v6_canary_complete`→`candidate_demote_intent／complete`→`old_promote_intent／complete`→`old_snapshot_restore_intent／complete`→`rollback_tuple_replace_intent／complete`→`candidate_stop_intent／complete`→`candidate_exit_observed`。Old shared canary只能在candidate确认`accepting=false`后执行，必须以generation／release marker与`/proc` accept PID证明命中old。Candidate quiesce与最终stop是两个独立动作；先恢复old、后停止candidate的用户保证保持不变。Dead committed recovery同样为新epoch，成功后`committed_generation／maintenance_owner`更新为新恢复代，release／snapshot保持canonical值。Controller在每个子动作调用前与ack后崩溃时，只能按durable phase幂等完成或回滚整个tuple；每个phase都定义唯一目标tuple，禁止用运行态启发式选择相反结果。

## Rollout失败与回滚

- Candidate启动、control UDS、readiness或最小canary任一失败时，不得signal旧generation。
- 旧generation quiesce后candidate失败时，先resume旧generation并以v4／v6全新TCP验证，再quiesce／stop candidate。
- Rollback不得重放已提交响应或迁移旧连接。
- 旧release与状态保留到观察窗口完成；破坏性schema迁移阻断rolling。
- Controller持续reconcile unit与UDS状态。唯一ready＋accepting generation异常退出时，按canonical committed release创建新的generation ID并重启；start-limit耗尽或所有generation均失败时进入`DEGRADED_NO_GENERATION`并保持socket／backlog，不伪装ready。
- Controller崩溃恢复不得仅以“哪个PID还活着”猜现任。恢复先加载最后一个通过完整性校验的durable checkpoint，再枚举unit active、UDS identity／epoch／release／phase与双栈generation marker。Checkpoint phase包括ID reservation、candidate start／ready、old quiesce、上述promotion／traffic commit各子动作、上述rollback各子动作和dead committed recovery各子动作。每个phase记录durable pre-tuple、唯一post-tuple、已允许发生的外部副作用及下一幂等动作；运行态只用于验证checkpoint，不得凭“唯一accepting”覆盖未完成transaction。无法证明身份时不stop任何generation并进入`DEGRADED_CONFLICT`。无ready＋accepting时按canonical committed release与canonical immutable snapshot创建恢复generation。Controller必须在每个子动作调用前／ack后、atomic replace前／后注入crash并通过恢复表收敛。
- 每个generation拥有独立service cgroup与startup resource profile。Controller在启动candidate前执行可观察的cgroup／fd／process preflight；candidate超出其unit-local`MemoryMax／TasksMax／LimitNOFILE`或spawn失败，只允许candidate unit失败。Controller不得向active／drainers发送signal、stop、quiesce或cleanup，也不得改变其listener ownership／cgroup identity；失败前存在的长连接必须按自身自然生命周期继续可用。既有operation、fd和cgroup counters可因正常业务活动自然演进，不要求静态相等。父slice／系统级OOM仍不在此强保证内。
- Cleanup只允许作用于已进入process终态的单一generation ID：process lifecycle为`EXITED`，systemd unit inactive，MainPID不存在，service cgroup为空，且没有该generation的live fd holder。应用级`FAILED`不等于process已退出；`FAILED-but-live`必须先记录独立stop intent，必要时先恢复replacement，再等待controller观测process lifecycle=`EXITED`与上述运行态硬门。Application phase继续保留`FAILED`与cause，不能被cleanup伪写为正常EXITED。满足硬门后，Controller durably写该generation的identity manifest与`cleanup_intent`，再对unit failed-state reset、service cgroup残留、UDS、generation-local runtime／state和fd记录逐资源`delete_intent／complete`进度；每步前验证身份。全部资源删除并对相关父目录fsync后写`cleanup_complete`，在此之前禁止compact identity manifest。Controller crash后只按该manifest继续未完成步骤，不得按epoch范围、目录前缀或“所有非committed”猜测清理。其他drainers的PID／cgroup／UDS／state sentinel／listener inode／operations／History terminal必须不受controller cleanup动作影响并继续可用；允许其业务operation和fd随自然生命周期演进，不要求字节级静态相等。

## 验收层级

### 普通process harness

必须验证：production child实际fd inode与parent／old／candidate共享listener identity相同；多socket dormant registration与统一arm；ready后handoff；old stop/resume accept；fresh TCP以`/proc` tuple归属实际PID；keep-alive请求二；有限HTTP与SSE／业务WS在quiesce后继续进展；History observer WS 1012；默认无限等待；第二终止信号exit code与cleanup sentinel；candidate失败不影响old；v4／v6顺序置换与单族反样本；History第三方reader集合相等、锁争用失败；tokenization snapshot来源；controller每个checkpoint crash恢复。

### 真实systemd VM／container

必须具备PID1 systemd、可写unified cgroup v2 hierarchy和专用服务账户；嵌套container另需宿主delegated subtree。验证两个socket units、`Sockets=`共享fd、`Type=notify`、动态数量的独立generation service cgroup、controller cold activation与常驻reconcile、连续多轮rollout／rollback、`TimeoutStopSec=infinity`、精确emergency第二信号、`KillMode=control-group`及已退出generation cgroup归零。Permanent controller／socket／target和仍draining generations保持运行，不要求全局资源归零。

当前宿主`/init.scope`不具备安全的真实manager／cgroup验收条件；能力不足时保持`BLOCKED`，不得用静态verify或process harness冒充通过。

## 与copilot-api-js的对照合同

固定参考commit为`refs/copilot-api-js@444570479f9968c43f02b5ffe52d6cf441ff6d79`。采用其已验证思想：candidate ready后才signal predecessor；`SIGUSR2`幂等stop-ingress＋drain；第二终止信号立即退出；drain期间保留token／transport／durability资源。参考实现没有本项目的`DRAINED_STANDBY／SIGUSR1 resume／动态generation controller`合同，这些是明确差异而非parity要求。

明确差异：参考实现裸进程使用`SO_REUSEPORT`与独立backlog，本项目使用systemd-owned同一listener fd；参考实现当前`SIGUSR2`无限drain，本项目默认同为0无限但支持正值timeout；本项目必须保持4144双栈、generation control UDS和自身History／tokenization状态合同，不复制参考项目内部存储与日志体系。

## 完成定义

只有同一final candidate同时通过：Spec独立评审、PoC门、process-level完整harness、全仓pytest／Ruff／Pyright、真实systemd VM门、`copilot-api-js`行为对照和merged-state独立评审，才能声称仓库实现完成。

实现完成不等于已安装或已在宿主运行；任何真实unit安装、manager状态变更或4144正式启动仍需独立明确授权。
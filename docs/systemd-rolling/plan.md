# systemd rolling restart 实施计划

## 状态

- **状态**：`LIVING／POC_READY`，与实现同步推进。行为权威Spec已独立终审为`0 blocker／0 major`。
- **基线**：`main@a885715a53006a63f53775d6441cd1deba17e7b1`。
- **行为权威**：[spec.md](spec.md)。本文只描述how，不新增行为expected。
- **运行边界**：所有开发与process smoke使用动态loopback端口和隔离状态根；不安装unit、不操作宿主manager、不占用正式4144、不触碰4141或`cc-daemon`。

## 阶段1：关键PoC

### 目标

证明当前Python／asyncio／Uvicorn组合可消费双listener，并在保留master fd duplicate时stop／resume accept；同时固化reuse机制反例。先固定`copilot-api-js@444570479f9968c43f02b5ffe52d6cf441ff6d79`的公共生命周期合同与明确差异，避免实现后才发现信号／drain前提不一致。

### 文件

- `src/app/server_adapter.py`
- `src/app/socket_activation.py`
- `tests/unit/test_socket_activation.py`
- `tests/integration/test_uvicorn_multi_socket.py`
- `tests/integration/test_listener_quiesce_resume.py`
- `../systemd-rolling/copilot-api-js-comparison.md`

### 测试

1. `SO_REUSEADDR`双live bind返回`EADDRINUSE`；`SO_REUSEPORT`可双bind但socket identity不同；复制同一fd得到同一listener identity。
2. Uvicorn单app通过IPv4＋IPv6两个socket提供liveness。
3. Stop-accept只关闭当前asyncio servers，不关闭master duplicates或另一进程副本。
4. Resume从master duplicate重新注册accept，v4／v6均恢复。
5. 关闭master duplicate反样本使resume明确失败。
6. 原生`uvicorn.Server.serve()`／`shutdown()`反样本必须证明：它会安装自己的TERM／INT handler、立即accept、shutdown现有WS并消费旧grace timeout，因此不能作为USR2 quiesce路径。
7. Adapter PoC明确拥有生命周期：先运行Uvicorn startup与lifespan，使用`start_serving=False`注册两个family并统一arm；adapter自己安装USR1／USR2／TERM／INT；USR2只关闭asyncio servers，最终TERM在operation与durability清零后才执行lifespan shutdown。Rolling profile不消费旧`shutdown.graceful_timeout=300`。

### 退出门

PoC正确样本绿、上述反样本红。若resume不可行，停止后续实现并回到Spec重新裁决，不暗示已有替代拓扑，也不使用SO_REUSEPORT绕过。

## 阶段2：多fd production入口

**实现状态**：`IMPLEMENTED_FOR_REVIEW`。已新增独立`start-rolling`入口、production 4144双栈profile、`LISTEN_*`collector接线、rolling runtime编排与filesystem／abstract `sd_notify`。49项focused tests、Ruff与Pyright通过；尚未安装unit或运行真实systemd manager。

**后继minor**：阶段2正式停止入口仅为TERM／INT；若调用`RollingRuntime.run()`的外层task被直接cancel，当前不承诺完整cleanup。阶段3建立完整generation lifecycle owner时补cancellation回归，不把该非systemd入口冒充当前已支持。

### 文件

- `src/app/socket_activation.py`
- `src/app/server_adapter.py`
- `src/app/systemd_notify.py`
- `src/app/rolling_runtime.py`
- `src/app/cli.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_socket_activation.py`
- `tests/unit/test_systemd_notify.py`
- `tests/unit/test_rolling_runtime.py`
- `tests/integration/test_rolling_runtime_integration.py`

### 实现

- 解析`LISTEN_PID／LISTEN_FDS／LISTEN_FDNAMES`。
- 校验`http-v4／http-v6`、TCP与listening。Collector接收显式expected profile：production固定`127.0.0.1:4144／[::1]:4144`；测试profile注入动态双栈端口，production profile不可被动态地址放宽。
- Rolling路径不调用`uvicorn.run()`、`Server.serve()`或`Server._serve()`。Adapter复用锁定Uvicorn 0.40.0的protocol／config／lifespan组件，自己显式执行lifespan startup、`loop.create_server(..., start_serving=False)` dormant registration、统一arm、main wait、stop/resume accept与最终lifespan shutdown；Uvicorn的`capture_signals()`和`shutdown()`不得进入rolling调用图。该版本依赖集中在`server_adapter.py`并由契约测试固定；rolling路径不消费旧`graceful_timeout=300`。
- `systemd_notify.py`使用`NOTIFY_SOCKET` datagram。只有lifespan、dependencies、两个listener统一arm与generation状态完成后才发送`READY=1`；startup失败、缺任一family或未arm不得发送。单测覆盖filesystem与`@abstract`地址、unset／malformed、发送失败及READY恰好一次。
- 保留host／port与旧单fd兼容入口。

### 退出门

双栈真实HTTP通过；置换fd顺序仍按names工作；缺失／重复／未知name、错误family／端口、普通文件／UDP fd、错误PID均typed fail；fake notify socket证明正确时点与失败不发READY；旧CLI与systemd smoke不回归。

## 阶段3：Generation lifecycle与drain

**基础子切片状态**：`IMPLEMENTED_FOR_REVIEW_R4`。已实现runtime级单一transition owner、rolling-only generation phase、FastAPI绝对外层operation registry、原子admission permit、health gating、ApprovalGate共享admission事实源，以及History／Approval observer双topic closing/reopen gate、late-registration 1012与完整fanout。Operation归零只表示业务调用结束，不自动进入`DRAINED_STANDBY`；History／tokenization durability barrier仍由后继显式`mark_drained()`承接。38项相关测试、Ruff与Pyright通过。

**Control子切片状态**：`IMPLEMENTED_FOR_REVIEW_R5`。已实现generation-local UDS `status／wait`完整schema、单调revision与last error、canonical generation identity、USR2 quiesce／USR1 resume、USR2／TERM正timeout取消真实HTTP operation、第二TERM／INT立即退出，以及control path lock／预绑定socket／`cleanup_socket=False`／partial-start事务安全门。为根治pathname条件删除TOCTOU，generation runtime不自动unlink任何control pathname；任何既存path均fail closed，只能由controller分配新generation path，或在process EXITED cleanup manifest与同一lock协议下显式维护清理。Runtime统一聚合主错误、cleanup与control close错误；resume任一子动作失败稳定保留FAILED至TERM。候选测试含真实HTTP process signal smoke，Ruff与Pyright通过。

### 文件

- `src/app/generation.py`
- `src/app/shutdown.py`
- `src/app/server_adapter.py`
- `src/app/server.py`
- `src/app/runtime.py`
- `src/app/routes/health.py`
- `src/app/config/settings.py`
- `src/app/pipeline/approval.py`
- `tests/unit/test_generation_lifecycle.py`
- `tests/integration/test_generation_drain.py`
- `tests/http/test_health_routes.py`

### 实现

- ASGI最外层operation registry覆盖HTTP／SSE／WS完整生命周期。
- Generation状态机、readiness gating、stop/resume accept。
- `shutdown.drain_timeout`默认0；正值timeout取消剩余operation且不伪造success。
- SIGUSR2 quiesce；SIGUSR1 resume；首TERM／INT drain＋cleanup；第二TERM／INT立即退出。
- Approval open／closed状态与pending insertion共用同一锁；quiesce原子关闭creation gate，等待正在创建临界区退出，再拒绝完整pending集合。History observer WS按Spec重连。

### 退出门

短请求、慢请求、SSE、业务WS、pending approval、默认无限drain、有限timeout、第二信号、幂等USR2、resume及cleanup恰好一次全部有process-level正反控制。另固定：health例外；old keep-alive请求一完成后，等UDS确认`accepting=false`再发送请求二，必须503＋`Connection: close`且不上游；新WS upgrade先握手再1012且不登记operation；SSE在quiesce后仍看到event B＋terminal；业务WS在quiesce后仍完成应用消息；History observer WS单独1012；operation归零后还必须等待History terminal acknowledgement／durability barrier。Approval竞态测试确定性暂停在creation检查与pending insertion之间，执行quiesce后放行，断言该请求与完整pending集合均以`server_restarting`失败且后续创建稳定失败。

## 阶段4：Generation control UDS

### 文件

- `src/app/generation_control.py`
- `src/app/cli.py`
- `src/app/runtime.py`
- `tests/unit/test_generation_control.py`
- `tests/integration/test_generation_control_socket.py`

### 实现

- Generation-local `0600` UDS，尽早报告starting。
- 版本化`status／wait／canary`协议，输出generation、PID、release、phase、ready、accepting、active operations、families和last error。`canary`是generation-private应用探针，必须穿过依赖与最小应用处理但不经过共享4144 listener；controller在signal old前只信该私有探针。
- 任何既存control pathname均拒绝启动；runtime不自动回收stale path。显式维护清理必须在process EXITED硬门、generation cleanup manifest和同一`.lock`协议下执行。

### 退出门

Rollout helper可按规范generation ID明确区分任意数量generation；私有canary可确定归属candidate；malformed／版本错不影响业务；退出后UDS清理。协议在阶段6扩展`flush_snapshot／promote／demote`窄命令，不预埋万能RPC。

## 阶段5：Rolling units与controller／helper

**骨架状态**：`IMPLEMENTED_FOR_REVIEW_R8`。已实现4144双栈socket units、动态generation `Type=notify`模板、稳定launcher、controller service/target/slice、带初始化marker与allocation facts的单调ID frontier、带revision／初始化marker／newest-checkpoint选择／strict领域schema的canonical state、全链路deadline与strict framing/schema UDS client、窄systemctl adapter、空拓扑cold activation及`reserved → environment_ready → started → committed／failed／conflict`恢复、topology-level degraded conflict、failed初代后新ID bootstrap、replace dry-run planner。完整replace apply、snapshot／promotion／maintenance owner、committed generation crash自动替代和完整rollout checkpoint矩阵仍未实现并保持硬关闭；dry-run不burn ID、不发signal、不写state。75项相关测试含`systemd-analyze verify`，Ruff与Pyright通过。

### 文件

- `contrib/systemd/rolling/ghc-api-proxy-v4.socket`
- `contrib/systemd/rolling/ghc-api-proxy-v6.socket`
- `contrib/systemd/rolling/ghc-api-proxy-generation@.service`
- `contrib/systemd/rolling/ghc-api-proxy-controller.service`
- `contrib/systemd/rolling/ghc-api-proxy-rolling.target`
- `contrib/systemd/rolling/ghc-api-proxy-rolling.slice`
- `src/app/rolling_controller.py`
- `src/app/rolling_state.py`
- `tests/smoke/test_systemd_rolling_units.py`
- `tests/unit/test_rolling_state.py`
- `tests/integration/test_rolling_controller.py`

### 实现

- 4144双栈、具名fds、每generation独立service cgroup、rolling slice按任意重叠generation总资源建模、`TimeoutStopSec=infinity`、`KillMode=control-group`。
- Stable controller为常驻socket activation target，不转发数据。当前骨架持单实例锁，负责空拓扑cold activation、generation unit／UDS观察、failed初代后新ID bootstrap和replace dry-run规划；replace commit、rollback与drainer cleanup尚未实现。
- ID frontier是独立于可回滚canonical state的多副本单调寄存器；恢复取有效副本与allocation facts的最大高水位，初始化后facts缺失／损坏即fail closed。当前canonical state字段为`revision`、`controller_status／conflict_error`、apply gate、`committed_generation／release`及generation records；primary/checkpoint均带checksum并选择最新完整有效revision。Snapshot、maintenance owner和完整intent矩阵尚未进入当前schema。
- 阶段5 controller只开放dry-run、cold activation与reconcile；完整apply rollout保持feature-disabled。阶段6完成snapshot、promotion与History durability后才实现并启用正式调用顺序：durably burn新generation ID→取得bootstrap／live／canonical immutable tokenization snapshot→candidate start→UDS ready→private UDS canary→旧USR2→旧not-accepting→shared 4144 v4/v6 fresh provenance canary→old demote→candidate promote→publish candidate immutable snapshot→durable complete commit tuple。
- Candidate失败不signal old；rollback先resume old，再quiesce／stop candidate。
- 当前crash恢复只覆盖cold activation的`reserved／environment_ready／started`续跑与candidate identity conflict；唯一committed generation crash自动替代、完整intent／completion矩阵和atomic replace逐接缝注入仍是后续工作。

### 退出门

当前退出门：unit parser与`systemd-analyze verify`、launcher identity/release path、frontier corruption、state primary/checkpoint恢复、strict UDS deadline/schema、cold candidate正常／失败／三phase续跑、identity/MainPID冲突、stop conflict与dry-run零副作用。Private canary、old quiesce、shared provenance canary、promotion／rollback／dead recovery和cleanup checkpoint矩阵仍是future apply退出门，不能外推为当前通过。

## 阶段6：Overlap状态隔离

**History durability子切片状态**：`IMPLEMENTED_FOR_REVIEW_R3`。Mandatory terminal submit现以cancellation-safe acknowledgement等待SQLite commit；writer具备RUNNING／CLOSING／CLOSED／FATAL线性状态，reap与并发close纳入同一lifecycle gate；BUSY／LOCKED由Python按caller deadline重试，同一次submit在确认进入真实`_insert()`后等待锁释放并成功，持续锁超过deadline显式失败；READONLY／IOERR／CORRUPT／FULL含extended result code进入fatal，由submit／flush／close传播并推进generation FAILED；两个真实进程共享WAL后独立reader精确看到完整terminal ID集合。直接选择`test_history_store.py＋test_history_multi_process.py＋test_responses_ws.py＋test_generation_lifecycle.py`共33项通过；候选改动文件Ruff与全仓Pyright通过。

**Tokenization snapshot子切片状态**：`IMPLEMENTED_FOR_REVIEW_R4`。已实现版本化canonical JSON envelope、temp＋fsync＋hard-link no-replace immutable object、generation-local locked monotonic live-head、controller-owned locked canonical CAS/checksum、reference与object envelope全字段对账、losing generation拒绝canonical推进、strict UDS `flush_tokenization` revision/hash/path/local-only receipt、rolling runtime local publish、controller显式committed flush及从canonical payload/revision初始化新generation-local state。Controller state-changing operations共用单一operation lock，committed flush在UDS返回后重新读取durable tuple，切流期间旧代flush稳定按loser拒绝。Generation进程只写共享object/live-head区，canonical pointer位于controller state root。84项基础测试与66项竞态相关回归通过，Ruff与Pyright通过。

### 文件

- `src/app/server.py`
- `src/app/history/store.py`
- `src/app/history/sqlite/writer.py`
- `src/app/tokenization/state_store.py`
- `tests/integration/test_generation_state_isolation.py`

### 实现

- Tokenization／control／PID／logs generation-local。
- Config／credentials共享只读。
- History共享WAL必须通过多进程测试；migration／reaper单owner。
- Quiesce停止maintenance producer，但保留在途终态writer。
- Writer flush／close暴露未持久化失败，不能只累计error count。
- Snapshot来源三分：首次empty／legacy bootstrap；live committed UDS flush；committed已死时canonical content-addressed immutable snapshot。Immutable artifact采用content hash命名、temp→fsync→hard-link no-replace→parent fsync、同hash幂等与冲突拒绝；canonical tuple不得引用未durable artifact。Candidate只复制到generation-local路径，失败candidate不发布。
- Generation UDS实现`flush_snapshot／promote／demote`。完整apply rollout直到本阶段完成前保持禁用，阶段5 controller仅支持dry-run／cold reconcile。正式顺序为durable promotion intent→old demote ack→candidate promote ack→snapshot publish→完整commit tuple completion。Rollback固定为old resume＋private canary→candidate quiesce ack→shared双栈canary证明命中old→candidate demote→old promote／snapshot restore→tuple replace→candidate stop／exit observed；每个子动作调用前与ack后均有独立checkpoint。允许短暂无owner，不允许双owner。

### 退出门

连续rollout中所有drainers在新generation commit后分别完成预生成History terminal ID，由独立sqlite连接比较成功集合精确相等；一个writer持锁超过busy deadline时必须显式失败，其他writer成功集合不丢，失败writer不报durable。另注入只读DB／IOERR／WAL flush或close不可恢复错误：terminal ack失败、flush／close显式失败、UDS暴露错误且不得进入standby。Tokenization内容链使用revision／hash sentinel：empty与legacy bootstrap各一条；g1 flush r1→g2从r1启动→g1 losing-only学习不发布→g2 flush r2→失败candidate不发布→下一generation必须从r2启动；终止committed并删除其UDS／放置冲突local snapshot，controller恢复generation必须从canonical r2的实际bytes／digest启动；canonical artifact损坏必须fail closed；rollback后继续验证下一candidate来源。

## 阶段7：真实多进程harness

### 文件

- `tests/integration/rolling_harness.py`
- `tests/integration/test_rolling_process_handoff.py`

### 场景

- 父进程持有动态v4／v6 listener并传给old／candidate及任意数量drainers。
- Candidate UDS ready后old USR2。
- Old不再accept；fresh TCP仅candidate处理。
- Old已accept慢HTTP／SSE／WS继续完成。
- 默认无限drain；第二TERM／INT立即退出。
- Candidate startup／ready失败时old持续服务。
- Resume old后停止candidate无连接空窗。
- 连续执行组合轨迹：success→failed candidate→success→controller crash／restart→某旧generation退出并精准cleanup→success，并让至少五个predecessor保持无限SSE／WS drain；下一candidate仍取得大于全部历史ID的新generation并commit，既有drainers不被自动终止。随机选择非最近的早期drainer resume，证明其仍持v4／v6 master duplicate并可接受fresh TCP，再恢复原committed generation。
- Candidate资源失败分别注入`RLIMIT_NOFILE`／spawn failure；断言controller未向active／drainers发送signal／stop／quiesce／cleanup，listener ownership与cgroup identity连续，既有长连接继续自然演进；不要求operation／fd counters静态相等。失败ID已burn且failure checkpoint durable。
- 精准cleanup在至少三个drainers仍存活时只清理一个已退出中间generation。Cleanup前机械证明process lifecycle=`EXITED`、unit inactive、MainPID不存在、service cgroup空且无live fd holder；application phase=`FAILED`但process仍RUNNING的反样本必须拒绝cleanup，先恢复replacement并走stop intent，controller观测process EXITED后才继续。Cleanup不得把保留的FAILED cause改写成正常EXITED。随后cleanup manifest逐资源记录intent／completion，每步前后crash后可续跑，completion前不得compact身份。其余generation不得收到controller cleanup动作，PID／cgroup／UDS／state sentinel／listener inode身份连续且SSE／WS／History terminal继续自然完成。按epoch范围、所有非committed、整个state root清理的mutation均红。

### 判别力

不发USR2、只关闭一族、candidate未ready先handoff、关闭master duplicate、generation忽略inherited fd改用SO_REUSEPORT、只看connect成功、fresh canary实际命中old、使用keep-alive假装fresh connection、固定槽位／数量上限、按存活集合分配ID、共享tokenization路径与宽范围cleanup等反样本必须红。Fresh raw TCP用唯一tuple并从`/proc`映射实际accept PID；process child实际listener inode必须与parent／所有generation相同。每个controller crash case从`1 active＋1 candidate＋3 draining＋1 failed historical ID`开始，恢复后核对完整角色集合、fd holders、operations／durability、snapshot、maintenance owner和next ID。

## 阶段8：真实systemd VM门

### 文件

- `tests/systemd_vm/README.md`
- `tests/systemd_vm/provision.py`
- `tests/systemd_vm/verify_rolling.py`

### 环境

使用Ubuntu 24.04不可变cloud image artifact：文档记录release serial、架构、下载URL与SHA-256；runner记录hypervisor／版本、CPU架构、磁盘格式、网络模式和cgroup能力。Provision禁止无约束dist-upgrade，依赖由锁定的项目环境安装。脚本接收image digest、candidate commit与unit hashes，安装到一次性release目录，探测并记录kernel／systemd／Python实际版本，预检双栈、controller、service account与cgroup能力；失败导出journal／canonical state／generation UDS snapshots／unit hashes后幂等销毁VM。不能连接宿主manager或4141。嵌套container只有在宿主提供delegated subtree时可作为辅助，不替代固定VM门。

### 验收

真实socket units、`Sockets=`动态多generation共享fd、`Type=notify`、controller cold activation与持续reconcile、连续多轮rollout／rollback、无限TimeoutStopSec、精确emergency第二信号、独立cgroups、精准generation cleanup与状态隔离全部绑定同一candidate。Cold activation在controller和generation均inactive时分别由v4／v6首条连接触发；不允许预先start，原始backlog连接必须最终由首代处理并返回generation marker，controller不得accept／转发或丢弃后改发第二请求。Controller已active但generation消失时，新流量必须由常驻reconcile恢复generation。Candidate unit分别注入`MemoryMax`、`TasksMax`、`LimitNOFILE`和manager已接受start job后的进程失败；验证active／drainers未收到controller signal／stop／cleanup，listener／cgroup身份连续、既有长连接继续，失败ID已burn且后续rollout仍可进行。Generation ID round-trip覆盖最小值、跨16位边界、非法`/`、`%`、空白、前导零alias和systemd escape输入；合法ID在controller→unit `%i／%I`→UDS／state path→status中保持唯一身份。Permanent controller／socket／target和仍draininggeneration不要求归零。

## 阶段9：copilot-api-js对照

### 文件

- `../systemd-rolling/copilot-api-js-comparison.md`
- `tests/integration/test_rolling_behavioral_parity.py`

### 对照

- Candidate ready后signal predecessor。
- SIGUSR2幂等stop ingress＋drain。
- 第二TERM／INT立即退出。
- Drain期间保留token／transport／durability。
- Candidate失败时old保持服务。
- 区分fresh TCP与keep-alive。

### 明确差异

- 参考实现使用SO_REUSEPORT独立backlog，本项目使用systemd同一listener。
- 参考实现当前USR2无限drain；本项目默认相同且支持正值timeout。
- Python使用generation UDS／systemd动态generation controller与自身状态合同，不复制参考存储实现。Reference fixture固定到commit`444570479f9968c43f02b5ffe52d6cf441ff6d79`，只对照公共不变量；`DRAINED_STANDBY／SIGUSR1 resume／动态generation`是明确差异，不伪称parity。

## 阶段10：收敛

- 每个小切片完成后提交、定向测试、必要评审并尽快squash回main。
- 最终candidate运行全仓pytest、Ruff、Pyright、process harness与systemd VM门。
- 独立代码review、验收verifier与merged-state review均关闭blocker／major。
- Reviewed source以`archive/YYMMDD-systemd-rolling`保留。
- 更新live docs，明确仓库完成不等于已安装；任何真实4144启动仍需独立明确授权。

## 当前下一动作

1. 关闭阶段5 units/controller R6复评blocker／major，运行全仓门并作为独立squash checkpoint回并main、归档reviewed source。
2. 从新main进入阶段6状态隔离：History多进程durability、tokenization immutable snapshot及maintenance owner promotion/demotion。
3. 状态隔离收敛后实现replace apply／rollback与多generation process harness；真实manager／cgroup证据仍留给固定VM门。

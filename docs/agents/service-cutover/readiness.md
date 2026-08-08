# `copilot-api-js` 替代前实时 readiness 矩阵

## 文档状态

- **类型**：正式 living 文档。本文是替代 `copilot-api-js` 前的实时 readiness 真相源；每次实现、组合验证、备用端口 smoke、运行态演练或 inventory 重取后，必须更新对应行的状态、证据与下一动作。
- **当前总状态**：**`NO_CUTOVER／FOUNDATIONS_ONLY`**。Reasoning capability、History facts与stream route已依次作为`main@bd86207… → 38bb06f… → ae84aa9…`进入主树；`ae84aa9…` stream slice定向复核为`0 blocker／0 major`，但完整retry、request／global quota与resident backpressure、真实socket partial-write／delivery uncertainty仍为`UNVERIFIED`。`main@ae84aa9…`的备用端口happy smoke为`PASS_HAPPY_BACKUP_PORT_SMOKE`，且旧Bun incarnation与双栈`4141`前门前后不变；该PASS不覆盖上述未验证矩阵，也不自动外推到后继`c53849e…`。S3 graceful已作为`main@c53849e…`进入主树，S4 rootless installer仍待进入main；unit未安装，真实manager／cgroup未验。P0完整服务、P1完整运行面、P2与P3均未闭合。
- **目标**：在不执行切换的前提下，持续回答“`ghc-api-proxy-py` 是否已经具备替代当前 `copilot-api-js` 前门的证据”。本文不授权停止旧服务、抢占 `localhost:4141`、安装或启动生产 unit、迁移／删除数据，或改变客户端 endpoint。
- **作者基线**：`/home/xp/src/ghc-api-proxy-py` 的 current `main@c53849e2b5103c6426a67a8cbab687f2e45c1fa0`。本轮每次 shell 调用均在同一次调用内验证物理仓库根、当前目录、`main` 分支与该精确提交。Current main在线性既有foundation、systemd runtime、happy／usage、semantic／route／block之上，又包含reasoning capability `bd86207…`、History facts `38bb06f…`、stream route `ae84aa9…`与S3 graceful `c53849e…`。这些仓库bytes与范围内绿灯仍不表示完整retry／quota／真实socket partial-write、完整P0 bridge、S4 installer、安装态、真实manager运行态或cutover已完成。
- **当前输入身份与状态**：Current cutover inventory SHA-256为`1f72038de99bbddc4a3c71243d5e20ce8d0db8783afe6d49dcf46f17e63481d9`；Spec为`FINALIZED@5e362822…`，Acceptance为`FINALIZED_ACCEPTANCE_ORACLE@6457b896…`且本轮未改。Current main为`c53849e…`；capability、History、stream与S3 graceful均已main，S4 installer待main。备用端口happy smoke绑定`ae84aa9…`，不自动覆盖后继S3 commit，也不覆盖retry／quota／partial-write矩阵。Unit仍未安装，也未执行真实user manager／cgroup smoke。
- **证据时效**：持久inventory仍主要锚定`2026-08-07T07:02:27Z`。后续备用端口happy smoke在`ae84aa9…`上确认旧Bun同一incarnation继续持有`127.0.0.1:4141`与`[::1]:4141`、cgroup为`/init.scope`，全程signal数为零，且收口后`4142`／`4143`均释放；该动态证据只证明该smoke窗口内事实，未重取完整inventory资产集合。listener、PID、cgroup、unit、open fd、writer、资源与认证状态在任何后续smoke或cutover决策前都必须重取。
- **验收边界**：`../anthropic-responses-bridge/spec.md` 定义行为，`../anthropic-responses-bridge/acceptance.md` 定义完整产品 gate，`../anthropic-responses-bridge/implementation.md` 记录易变实现状态，[service cutover plan](plan.md)定义接管顺序与运行门，[current inventory](../../tmp/260807-current-service-cutover-inventory.md)记录现场快照。本文汇总 readiness，不重新决定行为或架构。

## 硬边界

1. **`cc-daemon` 禁止触碰。** 不停止、不重启、不 reload `cc-daemon.service` 或 `cc-daemon-calib.service`；不向其 daemon、player、shim、PTY host、spare 或子进程发送信号；不清理其 cgroup、runtime directory 或 socket；不通过修改 endpoint／环境再重启来做 canary。
2. **本文件不执行切换。** 不停止当前 Bun parent／child，不释放或绑定生产 `4141`，不安装／启用／启动 user systemd unit，不执行 `daemon-reload`，不迁移、复制、重写或删除生产数据。
3. **局部证据不得升级为完整服务。** Converter／parser／carrier／liveness／unit 的单元测试、局部 review、clean branch、integration 范围内 `PASS` 或 acceptance oracle 定稿，均不得写成完整 bridge、真实入口、运行态或 cutover `PASS`。
4. **同一候选原则。** P0～P3 的最终证据必须绑定同一 merged candidate commit、同一 effective config、同一 unit bytes、同一 inventory 身份与同一数据 disposition。跨分支拼接“各自绿”的证据只能保持 `FOUNDATIONS_ONLY`。
5. **无证据即不通过。** 没有执行真实入口 smoke、live／fault、正反控制、恢复 probe 或观察窗口时，状态保持 `UNVERIFIED`／`NOT_STARTED`；不得用“未观察到错误”折算为 `PASS`。

## 状态词与升级规则

| 状态 | 精确定义 |
|---|---|
| `NO_CUTOVER` | 整体禁止进入生产接管；任一 required 行未 `PASS` 时保持该状态。 |
| `FOUNDATIONS_ONLY` | 存在局部实现、候选提交、单元／局部 review 或范围内验证，但尚未进入同一完整产品候选或没有真实用户入口证据。 |
| `NOT_STARTED` | 尚未开始实现、取证或演练。 |
| `IN_PROGRESS` | 已开始并有可复验中间证据，但退出门未闭合。 |
| `UNVERIFIED` | 可能有实现或设计，但没有足够证据判定正确与否。 |
| `BLOCKED` | 已发现明确缺陷、未裁决硬分叉或必要前置不成立。 |
| `PASS` | 同一冻结候选在该行的正确样本、目标缺陷注入、真实入口／运行 probe及必要 fault证据全部通过。 |
| `ROLLED_BACK` | 该运行切片曾执行并按冻结路径恢复；不等于 readiness `PASS`。 |

状态只能由证据升级，不由任务完成感升级。任何绑定的 candidate、Spec、Acceptance、effective config、unit bytes、inventory asset set、数据 owner 或运行环境发生变化，受影响行自动退回 `UNVERIFIED`，直到重新执行相应 smoke。P0 全部 `PASS` 只证明协议服务候选可进入 P1／P2 的下一有副作用前置门；P0～P2 全部 `PASS`、P3 切换与回滚门也冻结并获授权后，才可能把整体从 `NO_CUTOVER` 升级。

## 总览

| 优先级 | Readiness 域 | 当前状态 | 当前结论 |
|---|---|---|---|
| P0 | 核心 Anthropic → Responses 正确服务 | `FOUNDATIONS_ONLY` | Capability、History与stream已进入current main，stream slice定向复核为0 blocker／0 major；`ae84aa9…`备用端口happy smoke也已PASS且旧Bun未变。但完整retry、quota／resident backpressure、真实socket partial-write／delivery uncertainty及完整Acceptance仍`UNVERIFIED`。 |
| P1 | 运行面 | `FOUNDATIONS_ONLY` | Systemd runtime与S3 graceful已进入`main@c53849e…`；S4 installer待main，unit未安装，真实manager／cgroup与双fd／双栈仍未验。`ae84aa9…`备用端口happy PASS不等于`c53849e…`重复restart／systemd／双栈PASS；旧Bun仍持有双栈`4141`。 |
| P2 | 数据／认证 disposition | `UNVERIFIED` | 已有逐项 ledger草案，但仍有 `PENDING_DECISION`，producer／consumer、writer fence、备份恢复和credential refresh合同未闭合。 |
| P3 | Cutover／rollback／observation | `NO_CUTOVER` | 未执行切换；旧 `--restart` supervisor fence、时间门、完整 rollback dry-run与观察基线均未验证。 |

## P0：核心 Anthropic → Responses 正确服务

P0 的被测对象是**真实 Anthropic 客户端经备用端口的真实 ASGI／HTTP／socket／WS入口所观察到的完整服务**，不是内部 converter 返回值。以下各行必须最终绑定同一候选；当前所有局部成果都只记 `FOUNDATIONS_ONLY` 或 `UNVERIFIED`。

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| Request conversion 与 route | `FOUNDATIONS_ONLY` | Capability修复已作为`main@bd86207…`进入主树并与History、stream合成；定向复核确认每次attempt的`PRE_SEND`后按resolved-model capability重新转换。`ae84aa9…`备用端口happy smoke覆盖真实non-stream与stream主路径，但完整request Acceptance仍未执行。 | `bridge/request`＋`pipeline/route` | 在current `c53849e…`备用端口复验thinking success、unknown capability reject、budget边界与retry后重转换，并纳入完整Acceptance正反控制。 |
| Non-stream response | `FOUNDATIONS_ONLY` | History facts已作为`main@38bb06f…`进入主树并与stream合成；真实`HistoryConsumer`的completed／failed投影及non-stream失败零成功事实已获定向复核。备用端口happy smoke的non-stream真实route通过，但完整错误、retry与usage矩阵仍未执行。 | `bridge/nonstream` | 在current `c53849e…`上从备用端口补齐non-stream错误、retry attempt隔离、usage／History exactly-once与local fault矩阵。 |
| Stream conversion 与 strict Anthropic SSE | `FOUNDATIONS_ONLY` | Stream route已作为`main@ae84aa9…`进入主树；绑定`ae84aa9…`的定向复核为0 blocker／0 major，覆盖capability＋History合成、single lifecycle及已知R3修复。绑定同一提交的备用端口`PASS_HAPPY_BACKUP_PORT_SMOKE`覆盖真实route、跨chunk CRLF framing、首block withholding、唯一success terminal、关键pre／postcommit错误与cancel；semantic reorder、完整terminal／usage、retry、quota／backpressure和真实socket partial-write仍未验证。 | `bridge/stream` | 先在current `c53849e…`复验happy slice，再执行`STREAM-MERGE-05`、完整usage／terminal／History矩阵及retry／quota／partial-write的持久化正反控制；不得沿用`ae84aa9…`的局部PASS冒充完整Acceptance。 |
| Block-level buffering／delivery frontier／resident budgets与backpressure | `UNVERIFIED` | Spec／Acceptance已冻结完整Anthropic content block为最小下游提交单元，并由 `REL-06` 冻结普通 per-request aggregate＋global resident reservation、有限queue、charge-before-read、两级可观测计账、capacity／deadline／cancel终态与拒绝新admission。Current main stream已把typed delivery接入真实ASGI route，备用端口证明首个完整block前零success bytes，定向测试覆盖首个ASGI body send uncertainty；但真实socket多个offset partial-write／RST、完整delivery-uncertain，以及请求级／全局配额、有限queue和真实backpressure仍为`UNVERIFIED`。 | `delivery/block-buffer`＋`pipeline/sink`＋`runtime/memory-quota`＋`pipeline/admission` | 以真实并发reader、慢consumer和loopback socket覆盖 `A.start → B.done → A.done`、同item多content parts、open-source terminal、block批提交、response-start／多个body byte offset／terminal短写或RST，以及uncertain后禁止重发／success terminal。另以配置化 `0 < request_budget < global_budget` 聚合同一请求的多个resident owner，覆盖有限queue、charge-before-read、drain后容量恢复、各终态release归零、global压力下拒绝新admission且已接纳请求继续受控；分别注入global-only和single-block／16 MiB分支两种单侧缺陷，禁止spill或live forwarding。 |
| Retry ownership 与 pre／post-commit frontier | `UNVERIFIED` | `ae84aa9…` stream复核确认executor仍是attempt／retry owner，stream仅交接`STREAMING`，route按delivery frontier终结；同提交备用端口happy smoke的六次请求均未出现第二exchange。但未执行pre-commit retry、attempt reset、retry exhaustion、失败attempt隔离与post-commit真实partial-write矩阵，不能把“未发生retry”写成retry PASS，也不能外推到后继`c53849e…`。 | `pipeline/retry`＋`delivery/frontier` | 以Fake upstream＋真实socket分别在headers前、首block未完成、首block已提交后注入reset／clean EOF／converter error，断言真实exchange数＝attempts、失败代全reset、已提交prefix不重复且post-commit不透明重放。 |
| Usage 与 stream／non-stream等价 | `FOUNDATIONS_ONLY` | Non-stream usage、History facts与stream terminal实现均已进入current main；备用端口happy smoke只确认唯一success terminal，未比较同fixture stream／non-stream usage，也未覆盖失败attempt、HTTP／WS parity或完整History／token observer矩阵。 | `bridge/usage`＋`lifecycle/tokenization` | 同一语义fixture分别走non-stream、HTTP SSE与WS，比较归一化usage；注入重复terminal usage、失败attempt计费、cache算术与reasoning归类缺陷，并核对History和calibration只采纳最终成功attempt。 |
| Error／terminal／transport failure | `UNVERIFIED` | `ae84aa9…`代码复核与同提交备用端口happy smoke已覆盖关键precommit typed 502、postcommit Anthropic error且无`message_stop`、disconnect cleanup；Acceptance要求的HTTP 4xx／429／5xx、failed／incomplete各reason、malformed body、clean EOF、真实RST／partial-write与terminal互斥完整矩阵尚未执行，且这些局部证据不自动外推到后继`c53849e…`。 | `bridge/error`＋`pipeline/lifecycle` | 备用端口连接本地fault upstream，覆盖HTTP错误、failed无message、全部incomplete reason、非JSON、timeout、malformed success、SSE error、clean EOF、真实RST／partial-write与converter exception；断言Anthropic envelope、状态码、唯一失败终态、资源关闭和零success terminal。 |
| Function tool declaration／choice／call-result roundtrip | `FOUNDATIONS_ONLY` | Request converter、non-stream与stream tool arguments严格校验已进入current main；stream定向复核包含tool-args guard，但真实完整roundtrip、restore mapper、server-tool no-revive和工具副作用隔离尚未形成完整证据。 | `bridge/tooling` | 使用无外部副作用的测试工具，从真实Anthropic入口覆盖声明、named／auto／none choice、sanitized name、assistant call、user result及malformed arguments；断言call id byte-exact、mapper双向一致、server tool在upstream前稳定拒绝。 |
| Reasoning／carrier／multi-item／echo | `FOUNDATIONS_ONLY` | Reasoning baseline、cardinality、request decoder、carrier与resolved-model capability现均进入current main；stream定向复核确认capability与History合成未丢失。完整route下stream／non-stream一item一block、encrypted-only no-loss、multi-item与真实client echo仍未由完整Acceptance闭合。 | `bridge/reasoning` | 在current main备用端口执行项目主v1 producer exact vector、项目／upstream v1 consumer vectors、encrypted-only、多item、authoritative`.done`、strip、unknown／foreign／malformed最小止血与client echo；producer-only／consumer-only变异必须分别有效。 |
| Session liveness／cancel／cleanup | `FOUNDATIONS_ONLY` | Session liveness与stream cleanup已进入current main；定向复核覆盖prefetch二次取消后upstream close、observer／History finalize恰好一次，备用端口happy smoke覆盖首block前／后client close及空闲SIGTERM cleanup。完整HTTP／WS取消、open-block shutdown、pending approval、tokenization与全部资源归零组合仍未验证。 | `pipeline/liveness`＋`runtime/shutdown` | 在current main于headers前、首block前、post-commit和pending approval期间取消真实HTTP／WS客户端；再以open block与长连接对备用进程发SIGTERM，断言不retry、primary failure保留、secondary cleanup可观测、History／FINALIZE恰好一次、全部task／response／socket归零。 |

### P0 退出门

P0 只有在上述十项全部对**同一候选**为 `PASS`，且 `acceptance.md` 的 required gates、正确样本、目标缺陷注入、确定性 live canary、必要 capture provenance和local fault均闭合后才可整体升级。单元测试全绿、某条开发线 0 blocker／0 major、Foundations integration范围内 `PASS`、官方SDK能解析单个happy path或手工请求成功都不满足退出门。

## P1：运行面

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| 备用端口完整候选 | `IN_PROGRESS` | `main@ae84aa9…`已在隔离`4142` app＋`4143` fake upstream取得`PASS_HAPPY_BACKUP_PORT_SMOKE`：真实non-stream／stream happy主路径、withholding、关键错误／cancel、精确shutdown与清理通过；旧Bun incarnation、双栈`4141`与signal数前后不变。该轮不是完整R3入口或完整Acceptance，且不自动覆盖后继S3 `c53849e…`。 | `runtime/launcher`＋`service-cutover/canary` | 以current `c53849e…`重跑最小happy回归并保持旧Bun不变；随后补持久化harness与semantic reorder、usage／terminal／History、retry、quota／backpressure、真实partial-write及重复停止／启动矩阵。 |
| Readiness／liveness语义 | `UNVERIFIED` | Current main包含systemd runtime与S3 graceful；`ae84aa9…`备用端口happy smoke实测liveness／readiness、真实Anthropic主路径与清理。该证据不是安装态或真实manager证据，也未覆盖认证失效、模型目录未加载、History不可写或shutdown draining，因此本行仍为`UNVERIFIED`。 | `runtime/health` | 先在不安装unit的current `c53849e…`备用进程复验liveness／readiness基线，再于隔离真实user manager中分别覆盖启动、上游认证失效、模型目录未加载、History不可写和shutdown draining；证明liveness与readiness能区分“进程活着”和“可接流量”，且不操作生产`4141`。 |
| User systemd socket activation | `FOUNDATIONS_ONLY` | M1 socket activation runtime与S3 graceful已进入`main@c53849e…`；S4 rootless installer尚待进入main。现有仓库／direct-fd证据不覆盖真实manager activation、effective cgroup、双fd／双栈、安装态或生产运行态。 | `runtime/systemd` | 先完成S4 installer的main-side gate，仍不执行真实安装；随后才在隔离真实user manager和备用端口验证activation、restart、真实cgroup与错误fd拒绝，不操作`4141`。 |
| 双 fd／IPv4＋IPv6 loopback | `UNVERIFIED` | Current前门同时监听`127.0.0.1:4141`与`[::1]:4141`；`main@cf53334…`可消费单个`--fd`，但current socket模板仍只有IPv4，尚无具名多fd与双栈消费合同。 | `runtime/socket` | 在备用端口创建具名IPv4／IPv6两个listener，由同一service消费全部fd；分别通过地址字面量与`localhost`请求，并注入漏一个地址族、错fd name、fd 0、重复fd和非socket fd。 |
| Cgroup／resource limits | `FOUNDATIONS_ONLY` | `main@cf53334…`已包含`.slice`声明与静态回归；WSL恢复盘点确认current旧Bun owner仍位于非unit cgroup`/init.scope`。尚无真实user manager中同一候选的effective limits、MemoryHigh、OOM、TasksMax和cleanup证据，模板进入main不得冒充内核已采用。 | `runtime/cgroup` | 在隔离真实user manager的备用user slice运行current-main实例，交叉核对unit声明、systemd effective属性与`/proc/<pid>/cgroup`；只制造受控memory／task压力，证明限制仅作用于代理service、退出后cgroup归零且不传播到其他unit或`cc-daemon`。 |
| Graceful shutdown | `FOUNDATIONS_ONLY` | S3 graceful已作为`main@c53849e…`进入主树，仓库gate覆盖`300s／330s`时间模型、短SIGTERM cleanup与deadline drift正控。它仍不证明真实user-manager SIGTERM、长SSE／WS、pending approval、History close或force timeout。 | `runtime/shutdown`＋`pipeline/lifecycle` | S4 installer进入main后，对隔离备用user service执行真实manager SIGTERM、长连接drain、强制deadline与资源归零。 |
| `localhost:4141`双栈兼容 | `NO_CUTOVER` | WSL恢复盘点确认旧Bun已重新监听`127.0.0.1:4141`与`[::1]:4141`，PID `1623`且位于`/init.scope`；首次交接无法靠当前socket activation声称零窗口，本轮禁止停止、signal或释放旧listener。 | `service-cutover/front-door` | **仅在P0、其余P1与P2全部PASS且另获切换授权后执行。** 预先在备用端口验证与当前客户端一致的`localhost`解析、双栈、keepalive、SSE／WS和retry；正式动作仍由P3冻结runbook控制。 |
| `cc-daemon`隔离不变量 | `UNVERIFIED` | Inventory只读证明它与4141 owner处于不同cgroup，并记录当时active state；本轮未也不得以重启复测。未来任何runtime smoke必须证明其身份不变。 | `service-cutover/inventory` | 每次备用端口／隔离user-manager smoke前后只读比较两个unit的active state、MainPID、`InvocationID`、cgroup和socket；不得修改其配置、endpoint、环境或生命周期。任何变化立即停止并调查。 |

### P1 退出门

P1 `PASS` 要求同一完整候选在备用端口真实跑通双栈socket activation、readiness、graceful、restart与cgroup fault，并证明旧 `4141` owner及 `cc-daemon` 身份前后不变。生产 `4141` 行在实际切换前仍保持 `NO_CUTOVER`；P1 的其余 `PASS` 只是进入P2／P3准备门，不是切换授权。

## P2：数据／认证 disposition

P2 使用 `plan.md` 的 inventory asset ID集合与disposition词汇。当前 ledger是计划草案，不是已执行事实；任一 `PENDING_DECISION`、未识别writer、未验证恢复或inventory集合漂移都会阻断整体。

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| Inventory asset set＝ledger asset set | `IN_PROGRESS` | Plan已列 `CUTOVER-ASSET-INVENTORY-v1` 的逐项ledger；current inventory列出History、archive、telemetry、quarantine、JSON状态、prompts、search、logs、PID、config与credential。尚未重取并机械证明集合精确相等。 | `service-cutover/data-inventory` | 只读重取全部可变文件、SQLite主文件／WAL／SHM、目录、runtime对象及open fd，生成稳定asset IDs；与ledger做集合精确相等比较，新增／消失项使P2退回`UNVERIFIED`。 |
| History与legacy History | `UNVERIFIED` | Bun在inventory时直接打开`history-v3.db`及WAL／SHM；Python默认使用不同`history.db`。旧集合计划为`RETAIN_READ_ONLY`，Python生产新建还是已验收迁移仍为`PENDING_DECISION`。 | `data/history` | 在副本／隔离目录验证SQLite online backup、integrity、关键查询、旧版本恢复与Python新库schema／close；裁决Python生产新建或MIGRATE，并证明新旧writer永不共享同一集合。 |
| Archive／telemetry／quarantine SQLite | `UNVERIFIED` | Archive计划`RETAIN_READ_ONLY`，telemetry计划`ABANDON`，thinking quarantine仍`PENDING_DECISION`；producer／consumer、open writer、WAL集合和恢复probe未闭合。 | `data/state-sqlite` | 逐库识别schema、producer、consumer、fd／锁和刷新路径；在一致副本上执行integrity、代表性查询与恢复。先裁决quarantine，再固定每库writer fence和回滚语义。 |
| Learned limits／negotiation／request telemetry | `UNVERIFIED` | Ledger草案均倾向`ABANDON`并由候选重学／重协商，但尚未确认全部writer、原子替换／锁、mtime稳定窗或旧版恢复。 | `data/ephemeral-state` | 在只读inventory中定位writer与刷新周期；在隔离候选证明不导入旧格式并使用独立路径；冻结旧文件digest，演练回滚时旧owner继续使用原件。 |
| System prompts／History search | `UNVERIFIED` | System prompts计划`MIGRATE`，History search计划`ABANDON`后从已决source of truth重建；文件集合、watcher、权限、解析语义和重建probe未执行。 | `data/prompts-index` | 在隔离目录比较源／目标文件集合、digest与解析结果；识别watcher和index writer；从已裁决History源重建search并验证候选不写旧目录。 |
| Python tokenization state | `FOUNDATIONS_ONLY` | Python已有tokenization state与shutdown flush基础；计划要求候选独立新建，不迁移旧实现状态。原子写、版本、损坏恢复、正式绝对路径与唯一writer未通过运行probe。 | `data/tokenization`＋`lifecycle/calibration` | 在隔离XDG目录执行成功、retry、cancel、损坏文件和SIGTERM；核对原子替换、校准恰好一次、flush完成、恢复策略与停止后零open writer。 |
| Config语义迁移 | `UNVERIFIED` | Inventory确认旧`config.yaml`和环境来源存在但未披露值；Plan要求迁移已核对语义并保持候选配置独立。尚无旧→新字段级disposition或effective config对账。 | `runtime/config` | 在受控、不落普通日志的环境读取旧effective config，生成仅含非敏感字段与secret引用digest的映射；用候选parser验证等价／显式不兼容项，并证明不会回写旧config。 |
| GitHub credential／authentication | `UNVERIFIED` | `github_token`或受控provider计划`RETAIN_READ_ONLY`；current inventory没有执行应用层认证探测，也未确认refresh是否写入、候选读取权限、upstream成功或旧版可恢复。 | `auth/credentials` | 在备用端口以受控secret引用执行最小认证＋上游canary；只记录provider、权限、非敏感digest和结果。若provider会refresh写入，先裁决唯一writer与rollback，不得继续按只读共享处理。 |
| Logs／PID／temporary runtime artifacts | `UNVERIFIED` | 旧logs计划只读保留，旧PID文件与临时对象计划`ABANDON`并由新supervisor重建；尚未证明sink分离、时间边界、owner和停止后无旧runtime复活。 | `runtime/observability` | 备用实例使用独立log／runtime路径，记录candidate identity且通过secret redaction；停止后验证fd／socket／lock归零。旧PID文件只作辅助，不参与新owner决策。 |
| In-flight approval／requests／accepted streams | `UNVERIFIED` | 计划明确不迁移、不重放；当前没有可观测active request／approval／accepted SSE／WS基线，也未验证grace／abort与副作用边界。 | `pipeline/lifecycle`＋`service-cutover/drain` | 在备用实例制造pending approval、短请求和长SSE／WS，执行graceful stop，记录最终状态、零重放、客户端重连及副作用边界；若生产状态不可观测，P2保持阻塞而非猜测drain完成。 |
| Backup／restore与writer fence | `NOT_STARTED` | Current Bun开放History WAL；plan已定义online backup或停写后一致复制原则，但未执行全资产备份、恢复或supervisor／listener／writer稳定窗演练。 | `service-cutover/data-recovery` | 只在副本和隔离runtime先演练逐资产backup／restore；验证integrity、关键查询、权限、容量与旧启动件。生产writer freeze属于P3授权动作，本文件不执行。 |

### P2 退出门

P2只有在inventory与ledger资产ID集合精确相等、无`PENDING_DECISION`、每项producer／consumer／writer观测点明确、备份／恢复probe通过、credential refresh owner唯一、旧新服务无任何双写可能时才可 `PASS`。`ABANDON`只表示候选不继承语义，源资产仍保留；它不授权删除。

## P3：Cutover／rollback／observation

P3当前全部保持 `NO_CUTOVER`、`NOT_STARTED` 或 `UNVERIFIED`。以下“next smoke”均为切换前的隔离准备或未来受控动作，不是本轮执行清单。

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| Current inventory与身份冻结 | `IN_PROGRESS` | Current inventory SHA-256为`1f72038de99bbddc4a3c71243d5e20ce8d0db8783afe6d49dcf46f17e63481d9`；其`2026-08-07T07:02:27Z`快照仍是完整资产盘点基线。WSL重启后的独立只读恢复盘点另确认旧Bun PID `1623`重新监听IPv4＋IPv6 `4141`、位于`/init.scope`，且`4142`／`4143`无LISTEN项；未做应用层探测，也未重取完整数据、writer、client或`cc-daemon`身份。动态事实均是瞬时证据。 | `service-cutover/inventory` | 只读重取old repo／commit／runtime／argv／cwd／parent-child／socket inode／fd／cgroup／clients／writers／data／disk和`cc-daemon`身份，生成脱敏inventory hash与差异；不发送信号或网络切流。 |
| 完整candidate／config／unit冻结件 | `NOT_STARTED` | 当前没有进入main并通过P0～P2的完整candidate，也没有最终user unit bytes、effective config digest和inventory绑定。 | `release/candidate`＋`runtime/systemd` | P0～P2通过后冻结commit、dependency lock、Python解释器、unit bytes、effective config非敏感digest、secret引用、data schema与acceptance evidence manifest；任一变化使P0～P3退回`UNVERIFIED`。 |
| 旧`--restart` supervisor／listener／writer fence | `UNVERIFIED` | Inventory识别Bun listener child与parent，plan要求先技术性fence restart owner；尚未验证精确停止／恢复原语或稳定窗，不能以kill child或一次`ss`空结果判完成。 | `service-cutover/old-runtime` | 在隔离复制环境证明parent可复拉child的正控，再验证冻结原语能阻止复拉；建立连续采样的parent／child／双栈listener／writer／WAL稳定窗。生产fence需另行授权。 |
| Cutover时间门与失败阈值 | `BLOCKED` | `D_OLD_RELEASE_MAX`、`W_OLD_FENCE_STABLE`、`D_NEW_LISTENER_MAX`、`D_NEW_READY_CANARY_MAX`、`D_CUTOVER_TOTAL_MAX`、`D_ROLLBACK_RECOVERY_MAX`、`W_POST_CUTOVER_MIN`均尚未由实测与用户目标裁决具体值。 | `service-cutover/operator`＋`observability` | 在备用端口／隔离切换与rollback dry-run中记录单调时间分布，并结合客户端timeout／retry预算提出阈值；由用户裁决可接受中断、恢复与观察目标后写入版本化manifest。 |
| 最小cutover canary集合 | `UNVERIFIED` | Plan已列liveness、Anthropic non-stream／stream、reasoning／tool与direct Messages，但尚未绑定同一候选、严格expected、预算和失败动作。 | `acceptance/canary` | 在备用端口固化低副作用canary的请求、expected、超时、重试关闭、数据隔离与失败分类；证明每项能抓到目标缺陷，再冻结到candidate manifest。 |
| Rollback启动件与旧服务恢复 | `NOT_STARTED` | 旧source、Bun executable、argv、cwd、config与数据路径已部分盘点；受控环境值、旧commit／lock、精确supervisor恢复顺序、旧readiness和真实请求恢复尚未演练。 | `service-cutover/rollback` | 在隔离端口从冻结旧启动件恢复Bun服务，验证双栈、readiness、真实请求、旧writer资产和资源归零；再演练“新失败→释放新socket→恢复旧supervisor／child／writer”。不占用生产`4141`。 |
| `4141`接管 | `NO_CUTOVER` | 当前双栈`4141`由旧Bun独占；没有零窗口机制，也没有P0～P2、deadline、rollback和独立评审闭合证据。 | `service-cutover/operator` | 只有全部前置为`PASS`、用户明确授权当次切换且执行前inventory无漂移时，才按冻结runbook先fence旧supervisor／writer，再由systemd双栈socket接管。当前不执行。 |
| 自动rollback触发与执行 | `NO_CUTOVER` | Plan已列owner、地址族、data、double writer、required canary、resource、deadline与`cc-daemon`变化触发器，但尚未以完整candidate实测。 | `service-cutover/rollback` | 在隔离runtime逐项注入新listener超时、readiness失败、单地址族、canary语义错、restart loop、data write失败与resource越界，证明每项按唯一原因触发冻结rollback且不现场放宽阈值。 |
| Observation baseline与窗口 | `NOT_STARTED` | 没有同口径旧服务baseline、样本下限、允许偏差或完整candidate观察证据；inventory的单点RSS不能作为capacity baseline。 | `observability/cutover` | 切换前冻结旧服务的请求类型、错误分类、latency、RSS／cgroup、fd／tasks、History queue、long stream和restart基线；隔离候选先跑同口径观察，裁决`W_POST_CUTOVER_MIN`与样本下限。 |
| Cutover后观察 | `NO_CUTOVER` | 尚未切换，不能存在post-cutover证据。 | `observability/cutover` | 未来接管成功后按冻结窗口覆盖non-stream、stream、reasoning、tool、error、长连接、一次service restart、data owner和`cc-daemon`不变量；任一单次失败不变量触发rollback。 |
| 旧Bun退役 | `NO_CUTOVER` | 旧服务仍是生产owner和必要回滚资产；自动拉起来源尚未穷尽，观察期未发生。 | `service-cutover/retirement` | 仅在观察`PASS`且另有退役决定后，精确停用已证明的旧自动启动源；保留旧commit／binary／config引用／数据与rollback manifest，只提出`DISCARD_LATER`，不删除。 |
| 独立评审与最终授权 | `UNVERIFIED` | Capability、History、stream与S3已main；stream slice为0 blocker／0 major，备用端口happy smoke PASS且旧Bun未变。P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43行口径保持；完整retry／quota／partial-write、S4 installer、真实runtime、P2、最终unit bytes、runbook和rollback仍无最终merged-state证据。 | `review/readiness`＋用户 | 本次新bytes必须按新hash重新定向复评，旧hash verdict不能沿用。先复验current `c53849e…`备用端口happy slice并完成S4 main-side gate，再执行未验证P0矩阵与隔离真实manager／cgroup smoke；任何局部PASS均不等于切换授权。 |

## `cc-daemon`只读不变量

`cc-daemon`不是readiness实施对象，而是每个运行smoke和未来cutover都必须保持不变的外部不变量。本文永远不把“操作`cc-daemon`”列为next smoke、修复或rollback步骤。

| 观测项 | Current status | Evidence boundary | Owner | Next smoke |
|---|---|---|---|---|
| `cc-daemon.service`与`cc-daemon-calib.service` active state、MainPID、`InvocationID`、cgroup、socket | `UNVERIFIED`，仅有过期快照 | Current inventory在`2026-08-07T07:02:27Z`附近只读确认active／running及与4141 owner不同cgroup；该身份不可外推到后续执行。 | `service-cutover/inventory` | 每个备用端口、systemd dry-run、rollback rehearsal及未来cutover前后只读重取并比较；不得发送信号、reload、改环境、改endpoint或清理runtime。变化即停止相关阶段并调查。 |
| 经现有`localhost:4141`前门的活会话可用性 | `UNVERIFIED` | Inventory未发应用层请求，也没有本轮会话内容探测；不得读取敏感会话内容或以破坏性重启校准。 | `service-cutover/canary` | 只使用冻结的低副作用真实请求确认前门持续可用；不改客户端配置，不要求daemon访问备用端口，不重启活会话。 |

## 更新协议

每次更新本矩阵必须完成以下动作：

1. 记录物理repo root、branch、完整candidate commit、Spec／Acceptance内容身份、effective config digest、unit bytes hash、inventory hash和执行时间；不得只写分支名或“最新”。
2. 只更新本轮实际取得证据的行。局部checkpoint默认保持`FOUNDATIONS_ONLY`；未执行真实入口／fault／恢复／观察的行不得连带升级。
3. `Current evidence`必须区分代码存在、单元测试、局部review、真实入口、live canary、local fault、runtime probe和生产观察，不能混写成一个“通过”。
4. `Next smoke`始终写最小、可复现、能区分正确与错误状态的下一证据动作；高风险gate同时保留正确样本与单缺陷控制。
5. 任一动态事实、candidate、配置、unit、inventory资产集合、data owner或oracle变化，立即把受影响行降为`UNVERIFIED`并写明漂移原因。
6. 不把secret值、Authorization、token、用户内容或完整环境写入本文；只记录变量名、受控引用、权限、脱敏摘要和digest。
7. 不因readiness文档更新而执行service、systemd、socket、数据或process操作。运行操作只能来自另行明确授权的阶段执行。

## 当前阻塞链与下一最小序列

1. **P0组合已main但完整Acceptance未闭合**：Capability `bd86207…`、History `38bb06f…`与stream `ae84aa9…`已依次进入main，stream slice定向复核为0 blocker／0 major；这只关闭旧开发线major，不关闭完整产品门。
2. **下一P0 smoke仍有明确缺口**：先以current `c53849e…`复验`ae84aa9…`的备用端口happy slice与旧Bun不变量，再执行semantic reorder、完整usage／terminal／History、retry、request／global quota与resident backpressure、真实socket partial-write／delivery uncertainty正反控制；缺任一项继续`UNVERIFIED`。
3. **P1 runtime未闭合**：S3 graceful已作为`main@c53849e…`进入主树；S4 installer仍待main，之后才可进入隔离真实user manager／cgroup、双fd／双栈activation／restart smoke。旧Bun继续持有双栈`4141`；禁止stop／signal并保持`cc-daemon`不变。
4. **P2 disposition未闭合**：重取inventory，令asset ID集合与ledger精确相等，裁决所有`PENDING_DECISION`，完成逐项backup／restore与唯一writer证据。
5. **P3仍为`NO_CUTOVER`**：先完成隔离old-supervisor fence、旧启动件恢复、完整rollback dry-run、时间分布与观察baseline，再提交独立评审和用户裁决。当前不执行生产切换。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| Bridge开发线与完整产品状态 | Capability／History／stream已进main且范围内评审与happy smoke为绿，但retry、quota／backpressure和真实socket partial-write未验；局部绿灯容易被拼成“服务已完成”的假绿 | 本矩阵统一标`FOUNDATIONS_ONLY`；下一步在current main纳入完整retry、容量与partial-write真实入口证据，不重复回放已main开发线；不得把主树回归或happy smoke外推为完整产品`PASS`。 |
| `src/app/cli.py`、current-main systemd runtime与installer候选 | 应用host／port owner、单fd模板、S3 graceful、S4 rootless render／install和目标双栈socket activation分属不同层 | S3已作为`c53849e…`进入main，S4 installer待main；完成S4仓库gate后仍须备用端口真实双具名fd／manager smoke，不得升级为安装态或生产运行态。 |
| Lifespan cleanup、liveness helper与graceful接线 | 清理与deadline能力分散；S3 main与happy smoke仍不能证明真实user-manager SIGTERM、长连接和force timeout接缝 | P0 session liveness与P1 graceful仍分别要求真实客户端取消和真实manager SIGTERM，再由组合态验证统一owner。 |
| 旧／新持久化资产 | 两套schema、路径、writer与refresh owner不同，共享目录会产生双写和不可回滚状态 | P2逐资产disposition、集合相等、writer fence和backup／restore为硬门；默认不共享可写资产。 |
| 当前Bun parent／child与PID文件 | Listener child、`--restart` parent、PID文件和writer没有统一supervisor真相源 | P3以parent／child／socket owner／start time／cwd／cgroup联合身份和连续稳定窗取代单PID判断。 |
| Readiness与切换授权 | 技术矩阵变绿可能被误读为已授权生产动作 | `PASS`只表示证据门；`4141`接管仍需当次用户明确授权，且`cc-daemon`永远不进入操作范围。 |

## 不可声称边界

当前不得声称：

- `ghc-api-proxy-py`已经完整正确地提供Anthropic→Responses服务。
- Request、non-stream、stream、block buffering、retry、usage、error、tool、reasoning和session liveness已经在同一候选上通过。
- 单元测试、局部review、integration范围内`PASS`或Acceptance定稿等价于完整产品`PASS`。
- 备用端口候选已稳定运行，readiness已能区分应用可服务状态，或真实认证／上游连通性已验证。
- User systemd socket、双栈inherited fd、cgroup与graceful shutdown已经完成生产接线。
- Python与旧Bun可以安全共享History、token、config、telemetry、quarantine或其他可变资产。
- 旧`--restart` supervisor已fenced、rollback已演练、恢复时限已满足，或首次切换可零停机／原子完成。
- `localhost:4141`已经或可以立即由Python接管。
- `cc-daemon`可以被停止、重启、reload、改endpoint或作为rollback工具。

**实时结论：`NO_CUTOVER／FOUNDATIONS_ONLY`。Capability、History与stream已作为`bd86207… → 38bb06f… → ae84aa9…`进入main，stream slice定向复核为0 blocker／0 major；`ae84aa9…`备用端口happy smoke PASS且旧Bun incarnation、双栈`4141`与signal数前后不变。但完整retry、request／global quota与resident backpressure、真实socket partial-write／delivery uncertainty继续`UNVERIFIED`。S3 graceful已作为`main@c53849e…`进入主树，S4 installer待main，unit未安装，真实manager／cgroup未验证。43行口径保持为P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2。本文继续living、不收口；本轮新hash须后续重新复评，所有绑定旧hash的current复评均失效。在P0～P3 required行闭合前，不替代当前`copilot-api-js`。**

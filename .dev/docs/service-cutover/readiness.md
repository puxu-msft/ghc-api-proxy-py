# `copilot-api-js` 替代前实时 readiness 矩阵

## 文档状态

- **类型**：正式 living 文档。本文是替代 `copilot-api-js` 前的实时 readiness 真相源；每次实现、组合验证、备用端口 smoke、运行态演练或 inventory 重取后，必须更新对应行的状态、证据与下一动作。
- **当前总状态**：**`NO_CUTOVER／PARTIAL`**。Current `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`已包含并归档真实tool与reasoning两个最小纵向切片。隔离`4142`真实Copilot canary取得readiness 200、32／10模型目录、纯文本non-stream／stream 200、forced ordinary function tool与tool-result continuation 200，以及单item project-v1 reasoning carrier echo第二请求200。完整tool／reasoning Acceptance矩阵、quota／backpressure、kernel partial-write与真实systemd manager／cgroup仍未验证。P0保持`PARTIAL`，P1保持`FOUNDATIONS_ONLY`，P2与P3继续open。
- **目标**：在不执行切换的前提下，持续回答“`ghc-api-proxy-py` 是否已经具备替代当前 `copilot-api-js` 前门的证据”。本文不授权停止旧服务、抢占 `localhost:4141`、安装或启动生产 unit、迁移／删除数据，或改变客户端 endpoint。
- **作者基线**：`/home/xp/src/ghc-api-proxy-py` 的 current `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`。Tool与reasoning真实scoped canary分别绑定其已进入main且已归档的reviewed source，主线后继只保留等价squash语义。
- **当前输入身份与状态**：Current cutover inventory SHA-256为`1f72038de99bbddc4a3c71243d5e20ce8d0db8783afe6d49dcf46f17e63481d9`；Spec 与 Acceptance 按 `.dev` 提交锚定，基线 `.dev@66811b1`（2026-08-24）；Acceptance 状态为 `LIVING_ACCEPTANCE_ORACLE`。Current main为`c1de6bf…`；纯文本、forced ordinary tool roundtrip与单item reasoning carrier echo均有scoped PASS。Unit未安装，S5保持`BLOCKED`；完整tool／reasoning矩阵、quota／backpressure、kernel partial-write、credential refresh与cutover仍未验证。
- **证据时效**：持久inventory仍主要锚定`2026-08-07T07:02:27Z`。后续备用端口happy smoke在`ae84aa9…`上确认旧Bun不变；current-main R2在`e9fb277…`上确认旧Bun同一incarnation继续持有双栈`4141`，R3又在`d903d72…`的执行窗口内确认旧Bun完整identity不变、本轮signal数为零，且收口后`4142`／`4143`均释放。最新真实canary在`main@fb4272b…`的成功窗口内同样确认旧Bun PID／starttime／cwd／cgroup／listener快照不变且收到零signal，收口后`4142`零listener；这些动态证据只证明各自窗口内事实，未重取完整inventory资产集合。listener、PID、cgroup、unit、open fd、writer、资源与认证状态在任何后续smoke或cutover决策前都必须重取。
- **验收边界**：`../anthropic-responses-bridge/spec.md` 定义行为，`../anthropic-responses-bridge/acceptance.md` 定义完整产品 gate，`../anthropic-responses-bridge/implementation.md` 记录易变实现状态，[service cutover plan](plan.md)定义接管顺序与运行门，[current inventory](reports/260807-current-service-cutover-inventory.md)记录现场快照。本文汇总 readiness，不重新决定行为或架构。

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
| `PARTIAL` | 某 readiness 域已有一个或多个真实主路径层级通过，但该域仍有 required 行或 fault矩阵未闭合；不得外推为该域 `PASS`。 |
| `PASS_CURRENT_LAYER` | 精确绑定的当前实现层及已执行入口范围通过；只对列明的路径与candidate有效，任何后继bytes都必须复跑，且不得外推为完整Acceptance或cutover `PASS`。 |
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
| P0 | 核心 Anthropic → Responses 正确服务 | `PARTIAL` | Current `c1de6bf…`已取得纯文本non-stream／stream、forced ordinary function tool＋tool-result continuation及单item reasoning carrier echo的真实scoped PASS。完整tool／reasoning矩阵、quota／backpressure、kernel partial-write及完整Acceptance仍`UNVERIFIED`。 |
| P1 | 运行面 | `FOUNDATIONS_ONLY` | Current主树为`c1de6bf…`；应用路径scoped canary证明token exchange、模型刷新及列明的纯文本／tool／reasoning路径，但不是systemd user manager／cgroup证据。Unit未安装；S5保持`BLOCKED`，下一入口为可销毁VM／container；旧Bun仍持有双栈`4141`。 |
| P2 | 数据／认证 disposition | `UNVERIFIED` | 已有逐项 ledger草案，但仍有 `PENDING_DECISION`，producer／consumer、writer fence、备份恢复和credential refresh合同未闭合。 |
| P3 | Cutover／rollback／observation | `NO_CUTOVER` | 未执行切换；旧 `--restart` supervisor fence、时间门、完整 rollback dry-run与观察基线均未验证。 |

## P0：核心 Anthropic → Responses 正确服务

P0 的被测对象是**真实 Anthropic 客户端经备用端口的真实 ASGI／HTTP／socket／WS入口所观察到的完整服务**，不是内部 converter 返回值。以下各行必须最终绑定同一候选；已执行真实入口且边界明确的单行可记`PASS_CURRENT_LAYER`，其余局部成果保持`FOUNDATIONS_ONLY`、`PARTIAL`或`UNVERIFIED`，P0域整体只到`PARTIAL`。

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| Request conversion 与 route | `FOUNDATIONS_ONLY` | Capability修复已作为`main@bd86207…`进入主树并与History、stream合成；current `main@fb4272b…`已包含network retry及token／response／item identity fixes（同期的 resident wiring 已于 2026-08-19 按用户裁决删除，见下方 block buffering 行）。正式Responses override的真实non-stream与stream canary均为200，但该覆盖不含真实thinking success、unknown capability reject、budget边界与retry后重转换完整矩阵。 | `bridge/request`＋`pipeline/route` | 保留真实non-stream／stream正控，并补thinking success、unknown capability reject、budget边界与retry后重转换的完整Acceptance正反控制。 |
| Non-stream response | `PARTIAL` | Current main已取得真实纯文本、forced ordinary tool roundtrip与单itemreasoning carrier echo的non-stream HTTP 200。完整错误、retry、usage／History与其他模型矩阵仍未执行。 | `bridge/nonstream` | 保留已通过主路径为正控，继续错误与usage／History矩阵，不把scoped PASS外推为本行完整PASS。 |
| Stream conversion 与 strict Anthropic SSE | `PARTIAL` | 祖先`fb4272b…`取得真实纯文本stream 200与合法Anthropic SSE；current tool／reasoning scoped PASS均为non-stream，stream tool／reasoning、kernel partial-write与完整Acceptance仍未验证。 | `bridge/stream` | 保留纯文本stream为历史正控；stream tool／reasoning按完整矩阵后补，当前核心顺序为 partial-write。 |
| Block-level buffering／delivery frontier／per-request buffer cap与backpressure | `UNVERIFIED` | Spec／Acceptance已规定完整Anthropic content block为最小下游提交单元；`REL-06` 的具体条款以 `../anthropic-responses-bridge/spec.md` 为准。Resident primitive与production stream wiring曾分别作为`main@29c0ce3…`与`main@941299f…`进入主树并归档，但该字节级预算已于 2026-08-19 按用户裁决整体删除（`src/app/delivery/reservation.py` 与两个 `openai_responses.*_resident_bytes` 配置键随 `546852a` 移除）；进程级改由等待式在途请求上限 `proactive_rate_limiter.max_inflight`（默认 50，`InFlightLimit`，`f5589ec`）承接，超限请求排队等待而不被拒绝，`/health`、`/health/liveness`、`/health/readiness` 与 `/metrics` 豁免（`7e9b62d`）。per-request `client_delivery.buffer_cap_bytes` 保留，越限时放弃该 response。有限queue、真实sink partial-write／RST与完整delivery-uncertain仍未验证。 | `delivery/block-buffer`＋`pipeline/sink`＋`server/admission` | 下一核心切片以真实loopback sink覆盖partial-write／RST及accepted／partial／uncertain分类。 |
| Retry ownership 与 pre／post-commit frontier | `FOUNDATIONS_ONLY` | Headers-before Responses network retry已作为`main@fb5c027…`进入主树，唯一pipeline owner、一次预算、attempt隔离与fail-closed异常分类已实现；`080105b…`补回两次allowlisted连接失败后的永久component test，固定严格两次exchange、两个失败attempt、零success facts、History单次finalize且无`RESPONSE` hook。该测试与retry成功、wrapped runtime、bare SDK和direct read-error四个近邻组成的5个定向tests通过，唯一major关闭。Stream body读取、pre-commit block reset、post-commit frontier与真实partial-write仍未验证。 | `pipeline/retry`＋`delivery/frontier` | 以Fake upstream＋真实socket分别在首block未完成、首block已提交后注入reset／clean EOF／converter error，断言真实exchange数＝attempts、失败代全reset、已提交prefix不重复且post-commit不透明重放。 |
| Usage 与 stream／non-stream等价 | `FOUNDATIONS_ONLY` | Non-stream usage、History facts与stream terminal实现均已进入current main；备用端口happy smoke只确认唯一success terminal，未比较同fixture stream／non-stream usage，也未覆盖失败attempt、HTTP／WS parity或完整History／token observer矩阵。 | `bridge/usage`＋`lifecycle/tokenization` | 同一语义fixture分别走non-stream、HTTP SSE与WS，比较归一化usage；注入重复terminal usage、失败attempt计费、cache算术与reasoning归类缺陷，并核对History和calibration只采纳最终成功attempt。 |
| Error／terminal／transport failure | `UNVERIFIED` | `ae84aa9…`代码复核与既有备用端口happy smoke已覆盖关键precommit typed 502、postcommit Anthropic error且无`message_stop`、disconnect cleanup；R3又覆盖首block前cancel与上游断连，但Acceptance要求的HTTP 4xx／429／5xx、failed／incomplete各reason、malformed body、clean EOF、真实RST／partial-write与terminal互斥完整矩阵尚未执行。 | `bridge/error`＋`pipeline/lifecycle` | 外部manager／cgroup复验后，按真实缺口让备用端口连接本地fault upstream，覆盖HTTP错误、failed无message、全部incomplete reason、非JSON、timeout、malformed success、SSE error、clean EOF、真实RST／partial-write与converter exception；断言Anthropic envelope、状态码、唯一失败终态、资源关闭和零success terminal。 |
| Function tool declaration／choice／call-result roundtrip | `PARTIAL` | Current `main@e8708fb…`在真实Copilot备用端口完成forced named ordinary function tool与第二轮tool-result continuation，两轮均为HTTP 200；本地production-builtins route smoke固定call id、name、input、choice、single owner与finalize。Auto／any、sanitized-name restore、malformed arguments、server-tool no-revive及stream tool矩阵仍未闭合。 | `bridge/tooling` | 继续按REQ-04／NS-02补auto／any／none、name mapper双向恢复、malformed arguments与server-tool拒绝的正反控制，不重复已通过的forced ordinary tool主路径。 |
| Reasoning／carrier／multi-item／echo | `PARTIAL` | Current `main@c1de6bf…`无条件请求`reasoning.encrypted_content`；真实Copilot non-stream返回恰好一个非空project-v1 payload thinking block，完整assistant content原样echo后的第二请求为HTTP 200。本地静态exact vector证明第二Responses wire value-exact恢复opaque payload。Multi-item、encrypted-only、empty／bare、upstream-v1 consumer、malformed与producer-only／consumer-only变异仍未闭合。 | `bridge/reasoning` | 继续按REQ-05／NS-03补multi-item、encrypted-only／bare、upstream-v1兼容与malformed最小止血；不得把本次单itemscoped PASS外推为完整reasoning PASS。 |
| Session liveness／cancel／cleanup | `FOUNDATIONS_ONLY` | Session liveness与stream cleanup已进入current main；定向复核覆盖prefetch二次取消后upstream close、observer／History finalize恰好一次，备用端口happy smoke覆盖首block前／后client close及空闲SIGTERM cleanup。完整HTTP／WS取消、open-block shutdown、pending approval、tokenization与全部资源归零组合仍未验证。 | `pipeline/liveness`＋`runtime/shutdown` | 在current main于headers前、首block前、post-commit和pending approval期间取消真实HTTP／WS客户端；再以open block与长连接对备用进程发SIGTERM，断言不retry、primary failure保留、secondary cleanup可观测、History／FINALIZE恰好一次、全部task／response／socket归零。 |

### P0 退出门

P0 只有在上述十项全部对**同一候选**为 `PASS`，且 `acceptance.md` 的 required gates、正确样本、目标缺陷注入、确定性 live canary、必要 capture provenance和local fault均闭合后才可整体升级。单元测试全绿、某条开发线 0 blocker／0 major、Foundations integration范围内 `PASS`、官方SDK能解析单个happy path或手工请求成功都不满足退出门。

## P1：运行面

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| 备用端口完整候选 | `PARTIAL` | Current `main@c1de6bf…`已在隔离`127.0.0.1:4142`取得readiness、纯文本non-stream／stream、forced ordinary tool roundtrip及单itemreasoning carrier echo scoped PASS；旧Bun成功窗口内身份不变且零signal，收口后`4142`零listener。完整tool／reasoning矩阵、quota／backpressure、kernel partial-write与完整持久化矩阵仍未验证。 | `runtime/launcher`＋`service-cutover/canary` | 保留当前真实scoped canary为正控，下一步优先补partial-write与其余持久化矩阵。 |
| Readiness／liveness语义 | `PARTIAL` | Current main真实token exchange、模型目录刷新与runtime初始化已取得readiness 200，目录观测为32／10；该正向状态不覆盖认证失效、模型目录未加载、History不可写、shutdown draining，也不是安装态或真实manager证据。 | `runtime/health` | 保留当前readiness 200为正控；再于可销毁VM／container覆盖负向readiness与shutdown draining，不操作生产`4141`。 |
| User systemd socket activation | `BLOCKED` | M1 socket activation runtime、S3 graceful与S4 rootless installer代码已进入main，current主树为`fb4272b…`。S5本机隔离执行中helper、临时apply、动态unit verify与direct inherited-fd支持路径通过，但独立`systemd --user`在创建private control socket前以`rc=1`退出；真实daemon-reload、activation、fd inheritance与restart均未执行。 | `runtime/systemd` | 在可销毁systemd-nspawn容器或虚拟机中提供独立login session／user manager与delegated cgroup v2后复验；不得退回宿主user manager，安装任何真实目标unit仍须另行明确授权。 |
| 双 fd／IPv4＋IPv6 loopback | `UNVERIFIED` | Current前门同时监听`127.0.0.1:4141`与`[::1]:4141`；`main@cf53334…`可消费单个`--fd`，但current socket模板仍只有IPv4，尚无具名多fd与双栈消费合同。 | `runtime/socket` | 在备用端口创建具名IPv4／IPv6两个listener，由同一service消费全部fd；分别通过地址字面量与`localhost`请求，并注入漏一个地址族、错fd name、fd 0、重复fd和非socket fd。 |
| Cgroup／resource limits | `BLOCKED` | `main@cf53334…`已包含`.slice`声明与静态回归；S5临时unit再次确认声明值，但独立manager未启动service，因而没有service PID、真实cgroup path或effective limits可读。静态`MemoryHigh`／`MemoryMax`／`CPUQuota`／`TasksMax`不等于内核已采用；current旧Bun仍位于`/init.scope`。 | `runtime/cgroup` | 在具备delegated cgroup v2的可销毁容器或虚拟机中启动独立user manager，再交叉核对unit声明、systemd effective属性、`/proc/<pid>/cgroup`与cgroupfs；当前环境不得从静态文本外推。 |
| Graceful shutdown | `FOUNDATIONS_ONLY` | S3 graceful已作为`main@c53849e…`进入主树，S4 installer也已进入current main；仓库gate覆盖`300s／330s`时间模型、短SIGTERM cleanup与deadline drift正控。它仍不证明真实user-manager SIGTERM、长SSE／WS、pending approval、History close或force timeout。 | `runtime/shutdown`＋`pipeline/lifecycle` | 对隔离备用user service执行真实manager SIGTERM、长连接drain、强制deadline与资源归零；不得把installer代码存在写成unit运行态。 |
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
| GitHub credential／authentication | `PARTIAL` | Current `main@fb4272b…`包含并归档token identity headers；真实启动已从403修复为readiness 200，模型目录为32／10，真实Responses non-stream与stream canary均为200。未记录secret值。Provider refresh写入、并发刷新、权限、旧版恢复与唯一writer合同仍未闭合。 | `auth/credentials` | 保留当前真实启动正控；在不记录secret的前提下补refresh／expiry负向、唯一writer与rollback证据，不能从本次200外推完整credential disposition。 |
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
| 独立评审与最终授权 | `UNVERIFIED` | Current `main@c1de6bf…`已包含并归档identity、tool与reasoning最小纵向切片；真实readiness、纯文本non-stream／stream、forced ordinary tool roundtrip与单itemreasoning carrier echo scoped PASS已取得。完整tool／reasoning矩阵、quota／backpressure、kernel partial-write与S5 manager／cgroup仍未验证。P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43行口径保持。 | `review/readiness`＋用户 | 本次新bytes按新hash形成living checkpoint；随后闭合partial-write、manager／cgroup、完整tool／reasoning矩阵、P2、unit bytes、runbook、rollback与cutover。 |

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

1. **Current checkpoint包含identity及tool／reasoning最小纵向切片**：`main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`已包含对应main commits，两条`archive/260808-real-copilot-*`与既有identity archives均保持immutable。
2. **真实canary当前层通过**：隔离`127.0.0.1:4142`真实启动取得readiness 200、目录32／10，纯文本non-stream／stream、forced ordinary tool roundtrip与单item reasoning carrier echo均取得scoped PASS；旧Bun成功窗口内身份不变且零signal，收口后`4142`零listener。
3. **形成current living checkpoint**：只同步Implementation与Readiness到上述current事实并记录新hash；该checkpoint不得把当前实测层外推为完整产品`PASS`。
4. **P0真实tool／reasoning最小纵向层已通过**：Forced ordinary function tool＋tool-result continuation与单item project-v1 reasoning carrier echo均已在隔离备用端口取得scoped PASS；后续只补完整矩阵，不重复这两个happy-path切片。
5. **P1 runtime仍`BLOCKED`**：真实manager／cgroup转到可销毁VM／container；真实应用canary成功不得冒充user manager、effective cgroup、双fd／双栈activation或restart证据。旧Bun继续持有双栈`4141`，`cc-daemon`保持禁止触碰，S7 rolling后置。
6. **其余边界保持open**：下一核心代码切片转向kernel-level partial-write；manager／cgroup、credential disposition、inventory／ledger、backup／restore、唯一writer、rollback与observation均未闭合。P2与P3继续open，整体继续`NO_CUTOVER`。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| Bridge开发线与完整产品状态 | Current `c1de6bf…`已取得真实纯文本、forced ordinary tool roundtrip与单item reasoning carrier echo scoped PASS；但完整tool／reasoning矩阵、quota／backpressure、kernel partial-write与credential disposition仍未闭合，局部绿灯容易被拼成“服务已完成”的假绿 | P0域保持`PARTIAL`；下一核心代码序列为partial-write，完整tool／reasoning矩阵继续开放。 |
| `src/app/cli.py`、current-main systemd runtime与installer | 应用host／port owner、单fd模板、S3 graceful、S4 rootless render／install和目标双栈socket activation分属不同层 | S3与S4 installer代码均已进入`main@c1de6bf…`；真实应用scoped canary仍不是双具名fd／manager／cgroup／unit证据，不得把应用路径升级为安装态或生产运行态。 |
| Lifespan cleanup、liveness helper与graceful接线 | 清理与deadline能力分散；S3 main与happy smoke仍不能证明真实user-manager SIGTERM、长连接和force timeout接缝 | P0 session liveness与P1 graceful仍分别要求真实客户端取消和真实manager SIGTERM，再由组合态验证统一owner。 |
| 旧／新持久化资产 | 两套schema、路径、writer与refresh owner不同，共享目录会产生双写和不可回滚状态 | P2逐资产disposition、集合相等、writer fence和backup／restore为硬门；默认不共享可写资产。 |
| 当前Bun parent／child与PID文件 | Listener child、`--restart` parent、PID文件和writer没有统一supervisor真相源 | P3以parent／child／socket owner／start time／cwd／cgroup联合身份和连续稳定窗取代单PID判断。 |
| Readiness与切换授权 | 技术矩阵变绿可能被误读为已授权生产动作 | `PASS`只表示证据门；`4141`接管仍需当次用户明确授权，且`cc-daemon`永远不进入操作范围。 |

## 不可声称边界

当前不得声称：

- `ghc-api-proxy-py`已经完整正确地提供Anthropic→Responses服务。
- Request、non-stream、stream、block buffering、retry、usage、error、tool、reasoning和session liveness已经在同一候选上通过。
- 单元测试、局部review、integration范围内`PASS`或Acceptance定稿等价于完整产品`PASS`。
- 备用端口候选已稳定运行，readiness的正反语义已完整验证，或真实认证／上游连通性的完整生命周期已验证。
- User systemd socket、双栈inherited fd、cgroup与graceful shutdown已经完成生产接线。
- Python与旧Bun可以安全共享History、token、config、telemetry、quarantine或其他可变资产。
- 旧`--restart` supervisor已fenced、rollback已演练、恢复时限已满足，或首次切换可零停机／原子完成。
- `localhost:4141`已经或可以立即由Python接管。
- `cc-daemon`可以被停止、重启、reload、改endpoint或作为rollback工具。

**实时结论：`NO_CUTOVER／PARTIAL`。Current `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`已包含并归档Copilot identity、tool与reasoning最小纵向切片。隔离`127.0.0.1:4142`真实canary取得readiness、32／10模型目录、纯文本non-stream／stream、forced ordinary tool roundtrip与单item project-v1 reasoning carrier echo scoped PASS；旧Bun在成功窗口内身份不变且收到零signal，收口后`4142`零listener。P0整体仍为`PARTIAL`：完整tool／reasoning矩阵、quota／backpressure、kernel-level partial-write与完整Acceptance继续`UNVERIFIED`。Unit未安装，S5真实user manager／cgroup／unit仍`BLOCKED`；P1保持`FOUNDATIONS_ONLY`，P2／P3未闭合，旧Bun与双栈`4141`边界保持，`cc-daemon`继续禁止触碰。43行口径保持为P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2。本文继续living、不收口；完整产品保持`UNVERIFIED`，部署保持`NO_CUTOVER`。本轮新hash须后续重新复评，所有绑定旧hash的current复评均失效。在P0～P3 required行闭合前，不替代当前`copilot-api-js`。**

# `copilot-api-js` 替代前实时 readiness 矩阵

## 文档状态

- **类型**：正式 living 文档。本文是替代 `copilot-api-js` 前的实时 readiness 真相源；每次实现、组合验证、备用端口 smoke、运行态演练或 inventory 重取后，必须更新对应行的状态、证据与下一动作。
- **当前总状态**：**`NO_CUTOVER／FOUNDATIONS_ONLY`**。当前只具备若干独立 foundations、候选分支和验收 oracle；尚不存在绑定同一完整候选的 P0 正确服务证据，也未完成 P1 运行面、P2 数据／认证 disposition 或 P3 cutover／rollback／observation。
- **目标**：在不执行切换的前提下，持续回答“`ghc-api-proxy-py` 是否已经具备替代当前 `copilot-api-js` 前门的证据”。本文不授权停止旧服务、抢占 `localhost:4141`、安装或启动生产 unit、迁移／删除数据，或改变客户端 endpoint。
- **作者基线**：`/home/xp/src/ghc-api-proxy-py` 的 current `main@ec5e8f5240c6a587544e022b449aa7b392ba7ca1`。本轮每次 shell 调用均在同一次调用内验证物理仓库根、当前目录、`main` 分支与 `HEAD == refs/heads/main`；该 HEAD 相对 `ed77c9d…` 只新增正式 bridge 合同文档，不表示 foundations 或完整产品实现已进入 `main`。
- **当前输入身份与状态**：current cutover inventory SHA-256 `1f72038de99bbddc4a3c71243d5e20ce8d0db8783afe6d49dcf46f17e63481d9`；service cutover living Plan 为本轮current bytes，其上一稳定 bytes `ab840f2a…` 的 Plan R2 为 `0 blocker／0 major／0 minor`，current新bytes仍待联合复评；bridge Spec 为 `FINALIZED@5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；bridge Acceptance 为 `FINALIZED_ACCEPTANCE_ORACLE@224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`；bridge Implementation 是持续更新而不收口的 living document，current SHA-256 `4ace302283e2b4b539c8195e55a2a23020f692d40fe0df868546dd58312036e2`。Implementation current bytes已消费上一checkpoint评审点名的状态漂移并继续等待自身定向复评，不能把Implementation当成finalized产品证据。Systemd source `49fb1988621bba4356e7a5039a6994c2e6d19604`的code R4为`0 blocker／0 major`并放行三提交squash；clean integration `integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef`已准备但尚未进入main。Inventory、Plan与Implementation是各自current工作树内容身份；不得用current HEAD冒充它们的blob身份，也不得把Spec／Acceptance定稿、Implementation局部状态、systemd R4或`fe9c203…`外推为候选产品`PASS`、已安装、已部署或cutover获授权。
- **证据时效**：运行态 inventory 主要锚定 `2026-08-07T07:02:27Z`，只证明当时事实。listener、PID、cgroup、unit、open fd、writer、资源与认证状态在任何后续 smoke 或 cutover 决策前都必须重取。
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
| P0 | 核心 Anthropic → Responses 正确服务 | `FOUNDATIONS_ONLY` | Main 仅含 reasoning baseline；foundations 三片尚未回放，non-stream／stream／carrier候选未形成完整组合，完整产品仍为 `UNVERIFIED`。 |
| P1 | 运行面 | `FOUNDATIONS_ONLY` | Systemd source `49fb198…` 已获code R4 `0 blocker／0 major`，clean squash `fe9c203…`已准备但未进入main；真实manager／cgroup、目标user unit、双fd／双栈、备用端口、真实graceful与前门兼容仍未通过，current inventory中的双栈`4141`仍由旧Bun持有。 |
| P2 | 数据／认证 disposition | `UNVERIFIED` | 已有逐项 ledger草案，但仍有 `PENDING_DECISION`，producer／consumer、writer fence、备份恢复和credential refresh合同未闭合。 |
| P3 | Cutover／rollback／observation | `NO_CUTOVER` | 未执行切换；旧 `--restart` supervisor fence、时间门、完整 rollback dry-run与观察基线均未验证。 |

## P0：核心 Anthropic → Responses 正确服务

P0 的被测对象是**真实 Anthropic 客户端经备用端口的真实 ASGI／HTTP／socket／WS入口所观察到的完整服务**，不是内部 converter 返回值。以下各行必须最终绑定同一候选；当前所有局部成果都只记 `FOUNDATIONS_ONLY` 或 `UNVERIFIED`。

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| Request conversion 与 route | `FOUNDATIONS_ONLY` | `integrate/260806-bridge-foundations@6a00f6f…` 含 reviewed request converter；merged-state R2与范围内 verification通过，但三个 foundations提交尚未回放 `main`，且未证明真实 route、approval后prepare、每attempt转换或 capability真值表的完整入口行为。 | `bridge/request`＋`pipeline/route` | Foundations进入同一候选后，从备用端口真实 `/v1/messages` 覆盖 Responses-only、Messages-only、双支持默认Messages、显式Responses override、unknown fail-closed；捕获最后一跳Responses wire，并执行错误route单缺陷控制。 |
| Non-stream response | `FOUNDATIONS_ONLY` | 定向复评R2绑定`feat/responses-anthropic-nonstream@7ddf17364d97349638d44352bbd9a9b025723ccc`，确认public Anthropic identity与upstream identity分离的唯一major已关闭，结论为0 blocker／0 major、happy-path骨架可squash。该候选仍未进入 `main`；refusal、完整usage、terminal／error、route lifecycle、真实route-level response、History和close属于后续边界。 | `bridge/nonstream` | 在同一完整候选上用真实HTTP入口覆盖text、refusal、unknown item、tool、reasoning、failed／incomplete、usage与Anthropic error envelope；由官方SDK／独立schema消费，并注入identity、unknown-item和close缺陷。 |
| Stream conversion 与 strict Anthropic SSE | `FOUNDATIONS_ONLY` | 定向复评R2绑定`feat/responses-stream-parser@73a6aa114647440262691651cd17e9127785c75a`，确认source-order／open-source骨架major与两项minor已关闭，结论为0 blocker／0 major、parser semantic-facts骨架可squash。候选仍未进入 `main`；production sequencer、renderer、clean EOF、framing、strict lifecycle／grammar、真实入口和terminal错误链未完成。 | `bridge/stream` | 真实备用端口消费随机rechunk的Responses SSE／WS，按 `CAL-04-GRAMMAR-v1` 和固定Anthropic SDK双oracle覆盖thinking、tool、text、usage与terminal；执行missing start、index gap、duplicate terminal、error后content等单缺陷控制。 |
| Block-level buffering／delivery frontier／resident budgets与backpressure | `UNVERIFIED` | Spec／Acceptance已冻结完整Anthropic content block为最小下游提交单元，并由 `REL-06` 冻结普通 per-request aggregate＋global resident reservation、有限queue、charge-before-read、两级可观测计账、capacity／deadline／cancel终态与拒绝新admission；这些容量合同当前均为 `UNVERIFIED`。Current main的整流buffer与局部upstream参考不能证明首block前零success bytes、连续完成前缀、sink partial-write、delivery-uncertain、请求级／全局配额或真实backpressure。 | `delivery/block-buffer`＋`pipeline/sink`＋`runtime/memory-quota`＋`pipeline/admission` | 以真实并发reader、慢consumer和loopback socket证明首个完整block前零success headers／body；覆盖 `A.start → B.done → A.done`、block批提交、多个byte offset短写／RST及uncertain后禁止重发／success terminal。另以配置化 `0 < request_budget < global_budget` 聚合同一请求的draft、completed queue、预渲染envelope、carrier与History移交等多个resident owner，覆盖有限queue、charge-before-read、drain后容量恢复、各终态release归零、global压力下拒绝新admission且已接纳请求继续受控；分别注入global-only和single-block／16 MiB分支两种单侧缺陷，禁止spill或live forwarding。 |
| Retry ownership 与 pre／post-commit frontier | `UNVERIFIED` | 现有pipeline有retry基础，Acceptance已冻结唯一owner、pre-commit可重试、post-commit禁full replay；尚无完整bridge route-level attempt reset、真实exchange计数和post-commit partial failure证据。 | `pipeline/retry`＋`delivery/frontier` | Fake upstream＋真实socket分别在headers前、首block未完成、首block已提交后注入reset／clean EOF／converter error；断言真实exchange数＝attempts、失败代全reset、已提交prefix不重复且post-commit不透明重放。 |
| Usage 与 stream／non-stream等价 | `FOUNDATIONS_ONLY` | Acceptance已冻结usage算式；局部non-stream／request候选可能承载部分字段，但没有同一候选上的完整stream terminal、cache read／write、reasoning details、失败attempt隔离和History／token observer证据。 | `bridge/usage`＋`lifecycle/tokenization` | 同一语义fixture分别走non-stream、HTTP SSE与WS，比较归一化usage；注入重复terminal usage、失败attempt计费、cache算术与reasoning归类缺陷，并核对History和calibration只采纳最终成功attempt。 |
| Error／terminal／transport failure | `UNVERIFIED` | Acceptance定义HTTP 4xx／429／5xx、failed／incomplete、malformed body、clean EOF、stream error与terminal互斥；完整route-level错误、History exactly-once、response close和local fault尚未执行。 | `bridge/error`＋`pipeline/lifecycle` | 备用端口连接本地fault upstream，覆盖HTTP错误、failed无message、非JSON、timeout、malformed success、SSE error、clean EOF、RST与converter exception；断言Anthropic envelope、状态码、唯一失败终态、资源关闭和零success terminal。 |
| Function tool declaration／choice／call-result roundtrip | `FOUNDATIONS_ONLY` | Request converter已有tool name／call identity foundation；non-stream与stream response、restore mapper、真实roundtrip、server-tool no-revive和工具副作用隔离尚未形成完整证据。 | `bridge/tooling` | 使用无外部副作用的测试工具，从真实Anthropic入口覆盖声明、named／auto／none choice、sanitized name、assistant call、user result及malformed arguments；断言call id byte-exact、mapper双向一致、server tool在upstream前稳定拒绝。 |
| Reasoning／carrier／multi-item／echo | `FOUNDATIONS_ONLY` | `main@ed77…` 含reasoning baseline；cardinality correction与request decoder仍位于尚未完整进入main的foundations链。Carrier v2定向复评R2绑定`feat/reasoning-carrier-v2@8301ee938601ad86c7f72d313abc6c976a74b2a9`，确认direct Messages final-wire strip major关闭且Responses leg未误剥，结论为0 blocker／0 major、可squash；该候选仍未进入 `main`，完整non-stream／stream一item一block、encrypted-only no-loss和真实echo未验收。 | `bridge/reasoning` | 在同一候选上执行项目主v1 producer exact vector、项目／upstream v1 consumer vectors、encrypted-only、多item、authoritative `.done`、strip、unknown／foreign／malformed最小止血与client echo；producer-only／consumer-only变异必须分别有效。 |
| Session liveness／cancel／cleanup | `FOUNDATIONS_ONLY` | Session liveness reviewed候选与integration片已证明局部cancellation cleanup语义，但尚未进入current main；没有完整bridge真实HTTP／WS取消、shutdown、History finalize、approval、tokenization与upstream资源归零证据。 | `pipeline/liveness`＋`runtime/shutdown` | 在headers前、首block前、post-commit和pending approval期间取消真实HTTP／WS客户端；再对备用进程发SIGTERM，断言不retry、primary failure保留、secondary cleanup可观测、History／FINALIZE恰好一次、全部task／response／socket归零。 |

### P0 退出门

P0 只有在上述十项全部对**同一候选**为 `PASS`，且 `acceptance.md` 的 required gates、正确样本、目标缺陷注入、确定性 live canary、必要 capture provenance和local fault均闭合后才可整体升级。单元测试全绿、某条开发线 0 blocker／0 major、Foundations integration范围内 `PASS`、官方SDK能解析单个happy path或手工请求成功都不满足退出门。

## P1：运行面

| Readiness 项 | Current status | Current evidence | Owner | Next smoke |
|---|---|---|---|---|
| 备用端口完整候选 | `NOT_STARTED` | Plan允许在不占用 `4141`、隔离配置与数据的前提下启动候选；当前没有绑定完整bridge候选的可重复备用端口启动／停止／重启证据。Inventory未对应用层发请求。 | `runtime/launcher`＋`service-cutover/canary` | 从当次inventory选空闲loopback端口，以独立XDG data、History、tokenization和PID owner启动完整候选；真实调用liveness、readiness和最小Anthropic请求，重复停止／启动并证明资源归零、旧双栈前门不变。 |
| Readiness／liveness语义 | `UNVERIFIED` | Current inventory只证明旧Bun socket监听，不证明任何应用健康。Systemd `49fb198…` 的code R4确认受控generic upstream与真实应用侧fd smoke取得readiness 200并验证状态落盘；clean squash `fe9c203…`已准备但未进入main。现有证据未覆盖完整bridge候选、真实user manager、认证失效、模型目录未加载、History不可写或shutdown draining，因此本行仍为`UNVERIFIED`。 | `runtime/health` | 在备用进程启动、上游认证失效、模型目录未加载、History不可写和shutdown draining状态下分别探测；证明liveness与readiness能区分“进程活着”和“可接流量”。 |
| User systemd socket activation | `FOUNDATIONS_ONLY` | Source `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604`已实现`UMask=0077`、`StateDirectoryMode=0700`与真实History／SQLite WAL／SHM／tokenization writer权限回归；code R4绑定精确三提交并给出`0 blocker／0 major`、明确可squash，仅余1项非阻断credentials文档minor。Clean integration `integrate/260807-systemd-runtime@fe9c20315b0137ca5b2253fdbd86a30d504255ef`已把该范围squash到`ec5e8f5…`之上，但尚未进入main。Checkpoint仍是system-level单socket模板，未安装、未执行真实user activation；R4与squash准备均不证明真实manager／cgroup、双fd／双栈或生产运行态。 | `runtime/systemd` | 保持`fe9c203…`clean且不重复建线；按current Implementation在happy与usage收敛后重新gate当时的current main，核对source range／path／blob／patch身份，回放并执行main-side gate。隔离user-manager准备可继续：在备用端口验证user `.socket`／`.service`／`.slice`、`Accept=no`、具名双inherited fds、activation、restart、真实manager／cgroup与错误fd拒绝，不操作production unit。 |
| 双 fd／IPv4＋IPv6 loopback | `UNVERIFIED` | Current前门同时监听 `127.0.0.1:4141` 与 `[::1]:4141`；当前Python main不消费inherited sockets，候选socket历史只含IPv4。 | `runtime/socket` | 在备用端口创建具名IPv4／IPv6两个listener，由同一service消费全部fd；分别通过地址字面量与`localhost`请求，并注入漏一个地址族、错fd name、fd 0、重复fd和非socket fd。 |
| Cgroup／resource limits | `FOUNDATIONS_ONLY` | Systemd／cgroup候选已有模板与review，但未进入main或真实user runtime；current Bun owner位于 `/init.scope`。没有同一候选上的effective limits、MemoryHigh、OOM、TasksMax和cleanup证据。 | `runtime/cgroup` | 在隔离user slice运行备用实例，交叉核对systemd属性与`/proc/<pid>/cgroup`，制造受控memory／task压力，证明限制仅作用于代理service、退出后cgroup归零且不传播到其他unit。 |
| Graceful shutdown | `FOUNDATIONS_ONLY` | `src/app/server.py`已有lifespan cleanup，局部liveness candidate覆盖一部分cancel cleanup；真实server lifecycle、SIGTERM、长SSE／WS、pending approval、tokenization flush、History close和force timeout未组合验证。 | `runtime/shutdown`＋`pipeline/lifecycle` | 对备用user service执行真实SIGTERM：停止application admission，短请求drain，长SSE／WS按合同终止，approval拒绝，History／tokenization／upstream／background task归零；再验证`TimeoutStopSec`与`KillMode=control-group`强制路径。 |
| `localhost:4141`双栈兼容 | `NO_CUTOVER` | 旧Bun在inventory时是IPv4／IPv6唯一owner；首次交接无法靠当前socket activation声称零窗口，且本轮不释放旧listener。 | `service-cutover/front-door` | **仅在P0、其余P1与P2全部PASS且另获切换授权后执行。** 预先在备用端口验证与当前客户端一致的`localhost`解析、双栈、keepalive、SSE／WS和retry；正式动作仍由P3冻结runbook控制。 |
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
| Current inventory与身份冻结 | `IN_PROGRESS` | Current inventory SHA-256为`1f72038de99bbddc4a3c71243d5e20ce8d0db8783afe6d49dcf46f17e63481d9`；其`2026-08-07T07:02:27Z`快照识别旧Bun parent／child、IPv4＋IPv6 `4141` listener、`/init.scope`、数据根与当时`cc-daemon`状态，且明确未做应用层探测。PID、资源与listener事实均是瞬时证据；旧repo commit、依赖锁、完整环境值来源、客户端集合和全部writer仍需补齐。 | `service-cutover/inventory` | 只读重取old repo／commit／runtime／argv／cwd／parent-child／socket inode／fd／cgroup／clients／writers／data／disk和`cc-daemon`身份，生成脱敏inventory hash与差异；不发送信号或网络切流。 |
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
| 独立评审与最终授权 | `UNVERIFIED` | Service cutover Plan上一稳定bytes的R2为`0 blocker／0 major`；联合文档R2随后对Plan／Readiness状态链给出唯一major，本次新bytes已同步current Spec／Acceptance／Implementation、systemd code R4与`fe9c203…`准备状态，但关闭情况仍须current-byte联合复评。`REL-06`行级门与43行口径保持；P0完整candidate、P1 runtime、P2 disposition、unit bytes、runbook和rollback evidence均无最终merged-state评审。 | `review/readiness`＋用户 | 先联合复评本次Plan／Readiness新bytes；随后每个阶段证据更新后继续复评，P0～P3合并态再做独立对账。0 blocker／0 major只表示技术门可继续，不等于生产切换授权；实际切换必须由用户对当次动作明确授权。 |

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

1. **P0组合候选缺失**：先把foundations按已审计顺序进入current `main`，再分别收敛non-stream、stream、carrier与delivery／retry／lifecycle接缝，形成一个完整候选；在此之前P0保持`FOUNDATIONS_ONLY`。
2. **P0真实证据缺失**：完整候选必须先在隔离数据与备用端口执行Acceptance required gates、真实入口、正反控制、live／capture／fault；不以局部测试替代。
3. **P1 runtime未闭合**：Systemd source `49fb198…`已获code R4 `0 blocker／0 major`，clean squash `fe9c203…`已准备但未进入main；保持该单一载体，按current Implementation在happy与usage收敛后重取current-main身份并完成回放／main-side gate。仓库顺序不阻止继续在备用端口准备user systemd、双fd／双栈、readiness、graceful、真实manager和cgroup smoke，始终保持旧`4141`与`cc-daemon`不变。
4. **P2 disposition未闭合**：重取inventory，令asset ID集合与ledger精确相等，裁决所有`PENDING_DECISION`，完成逐项backup／restore与唯一writer证据。
5. **P3仍为`NO_CUTOVER`**：先完成隔离old-supervisor fence、旧启动件恢复、完整rollback dry-run、时间分布与观察baseline，再提交独立评审和用户裁决。当前不执行生产切换。

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| Bridge开发线与完整产品状态 | 多个独立候选、局部0／0与范围内PASS容易被拼成“服务已完成”的假绿 | 本矩阵统一标`FOUNDATIONS_ONLY`，只允许同一merged candidate的真实入口证据升级P0。 |
| `src/app/cli.py`与systemd socket候选 | 应用host／port owner、单fd模板与目标双栈socket activation合同错位 | P1要求备用端口真实双具名fd smoke；不得以unit静态检查或单IPv4 listener升级。 |
| Lifespan cleanup、liveness helper与systemd stop | 清理能力分散，容易出现“类／单测存在但生产信号未接线” | P0 session liveness与P1 graceful分别要求真实客户端取消和真实SIGTERM，再由组合态验证统一owner。 |
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

**实时结论：`NO_CUTOVER／FOUNDATIONS_ONLY`。下一证据目标是形成并验证一个同一身份的完整备用端口候选；在P0～P3 required行按各自门闭合前，不替代当前`copilot-api-js`。**

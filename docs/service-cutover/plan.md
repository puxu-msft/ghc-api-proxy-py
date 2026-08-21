# ghc-api-proxy 服务接管与 `localhost:4141` 渐进切换计划

## 文档状态

- **类型**：正式 living plan。本文不是等待一次性批准后封存的静态 runbook；开发、验证、候选集成、运行态发现和每次演练都必须及时回写当前状态、证据、阻塞项与下一动作。
- **当前执行状态**：`NO_CUTOVER`。本文只规划，不授权或执行 `localhost:4141` 接管、旧进程停止、user unit 安装、systemd reload、数据迁移、数据删除或 `cc-daemon` 重启。
- **目标**：在 Anthropic Messages → OpenAI Responses 路径通过完整替代验收后，以可回滚方式让 `ghc-api-proxy-py` 接管当前由 `copilot-api-js` 提供的 `localhost:4141` 前门，随后观察并退役旧裸进程。
- **作者基线**：`/home/xp/src/ghc-api-proxy-py` 的 current `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`。本轮每次 shell 调用均要求在同一调用内验证物理仓库根、`main` 分支和 `HEAD == refs/heads/main`，并读取当次 current HEAD；未来 `main` 前进后必须先更新本文，不能把该完整 hash 当作永久 gate。
- **权威边界**：Anthropic Responses bridge 的用户可观察行为来自 `../anthropic-responses-bridge/spec.md` 的 `FINALIZED@4c9beed…` 与 `../anthropic-responses-bridge/acceptance.md` 的 `FINALIZED_ACCEPTANCE_ORACLE@f99492a…`；易变实现状态来自持续更新且不收口的 `../anthropic-responses-bridge/implementation.md` 与 `readiness.md`。Current main已线性包含 foundations、systemd runtime、bridge主路径、retry、Copilot identity及tool／reasoning最小纵向切片（同期的 resident wiring 已于 2026-08-19 按用户裁决删除，进程级改由 `proactive_rate_limiter.max_inflight` 等待式在途上限承接）；真实canary取得纯文本、forced ordinary tool roundtrip与单item reasoning carrier echo scoped PASS。完整产品、P2、P3与真实manager／cgroup仍未闭合。不得把living文档、定稿oracle、局部checkpoint、main-side回归或canary 200当成完整产品`PASS`。本文只定义服务接管、部署、数据处置和回滚顺序，不重新决定 bridge 行为或内部架构。
- **评审状态**：`LIVING`。既有Plan R2／R3已确认实施节奏、逐项数据 disposition、旧 `--restart` supervisor／listener／writer fence以及首次切换与回滚的配置化时间门可继续；本轮只同步current main与运行态事实，不改变已冻结设计。任何历史0 major只表示当时bytes可继续living implementation，不代表计划封存、候选`PASS`、生产切换获授权或本文不再动态更新。
- **文件范围约束**：本轮只修改本文件。Kick-off 提示词内嵌在文末，不另建文件。

## 不可破坏边界

1. **不得触碰 `cc-daemon` 生命周期。** 不停止、不重启、不 reload `cc-daemon.service` 或 `cc-daemon-calib.service`，不杀其 player、shim、PTY host 或子进程，不修改其环境后以“需要生效”为由重启。任何 user systemd 操作前后都要核对这两个 unit 的 active state、主 PID 和 `InvocationID` 未变化；变化即停止切换并调查。
2. **不得使用宽匹配进程操作。** 禁止以 `pkill`、`killall`、模糊 `pgrep | kill`、停止整个 user target 或重启 user manager来退役旧服务。只允许对 inventory 已证明拥有 `4141` 的精确旧进程或其明确 supervisor执行动作。
3. **不执行本计划中的切换。** 本轮不停止旧 Bun 监听者，不启动 `4141` systemd socket，不更改客户端配置，不安装或启用 unit，不做数据复制／迁移／删除。
4. **旧服务数据与新服务数据不得双写同一可变资产。** History SQLite、WAL、tokenization state、认证状态、索引和任何 sidecar 在获得逐项 disposition 前不得由两个实现同时写入。
5. **bridge 局部提交、foundations integration、单元测试或 systemd 模板测试不能替代产品验收。** 只有当前候选完整通过本文“替代验收门”后才可进入 `4141` 接管。
6. **socket activation 不是零停机或连接迁移。** 首次从旧进程占有的端口切到 systemd socket 仍可能存在短暂监听窗口；已经被旧进程 accept 的 HTTP／SSE／WebSocket 连接不会被 socket 接管。
7. **回滚能力先于切换。** 未证明旧启动命令、旧二进制／提交、旧配置、旧环境来源、旧数据路径和旧健康探针可恢复时，不得释放旧 `4141` listener。
8. **不以删除完成退役。** 旧二进制、配置和数据默认保留为只读回滚资产；删除、压缩、迁移或永久清理需要另行明确 disposition 和授权。

## 当前事实快照

下表混合了2026-08-07的持久inventory基线与截至2026-08-08的current `main@c1de6bf…`仓库／scoped canary状态；执行任何阶段前必须重取。PID、端口owner、unit状态、candidate HEAD与运行态均不是永久事实。

| 对象 | 当前证据 | 计划含义 |
|---|---|---|
| 主仓 | `main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62` | Foundations、systemd runtime、S3／S4及后续bridge／runtime切片均已线性进入main；main-side 647项tests、Ruff与Pyright通过，但这些仓库checkpoint仍不是可切换产品候选 |
| `localhost:4141` | 只读 `ss` probe 观察到 Bun 同时监听 `127.0.0.1:4141` 与 `[::1]:4141` | “localhost 前门”当前包含 IPv4 与 IPv6 loopback；只接管 IPv4 会造成兼容性回归 |
| `cc-daemon` | `cc-daemon.service` 与 `cc-daemon-calib.service` 均为 user systemd active／running | 两者是硬禁触碰对象；切换只能保持其现有 endpoint 并在前门下替换服务端 |
| Python main CLI | Current main已包含`--fd >= 1` inherited socket入口，并拒绝与显式host／port混用；当前合同仍是单fd | 仓库级fd骨架已落地，但目标user runtime仍需具名双fd／双栈、错误fd与真实manager接缝验收 |
| Python 默认持久化 | `src/app/server.py:63-80` 默认使用 XDG data 下的 `tokenization.json` 与 `history.db` | 备用实例必须使用隔离目录；切换前必须确认实际配置覆盖和 owner |
| Python lifespan cleanup | `src/app/server.py:139-152` 会拒绝 pending approval、flush tokenization、关闭 History 与 upstream | 已有基础 cleanup，但仍需真实 SIGTERM／长连接／强制超时验收，不能仅凭源码声称优雅退出完成 |
| systemd runtime | Runtime、S3 graceful timeout与S4 rootless installer均已进入main；reviewed sources分别由`archive/260807-systemd-runtime@49fb198…`、`archive/260807-systemd-graceful-timeout@865a5b7…`与`archive/260807-systemd-user-install@e16c2a7…`保留 | 不再回放或重建systemd线；S5本机private user-manager／cgroup诊断仍`BLOCKED`，代码进入main不表示unit已安装、服务已部署、真实manager／cgroup已验收或生产运行态已切换 |
| Current socket模板 | Main中的system-level模板仅`ListenStream=127.0.0.1:4141`、`Accept=no`、`Backlog=1024`，应用合同仍是单fd | 未保持当前IPv6 loopback；单fd设计不能直接覆盖目标双listener合同，备用端口真实manager dry-run准备必须补user unit适配与具名双fd方案 |
| Current service模板 | Main中的system-level模板包含`User=`、`Group=`、`/opt`路径和`WantedBy=multi-user.target` | 这些是system-level假设；user unit必须另行render／check，默认dry-run，不安装、不reload、不enable、不start |
| bridge产品状态 | Current `main@c1de6bf…`已包含Copilot identity、tool与reasoning最小纵向修复；真实备用端口canary取得readiness、纯文本non-stream／stream、forced ordinary tool roundtrip及单item reasoning carrier echo HTTP 200 | Scoped canary只证明列明路径，不是完整Acceptance、真实user manager／cgroup、安装态或cutover证据；P2／P3仍未完成，当前禁止切换 |
| 旧Bun运行时 | Current inventory识别双栈`4141`旧Bun运行在外部`--restart` wrapper／supervisor之下 | 只停止listener child不足以fence旧runtime；正式接管前仍须验证wrapper的精确停止／恢复原语及supervisor／listener／writer稳定窗 |

## Living 更新协议

每次推进一个切片时，实施者必须在本文件同步以下内容，不能只把结果留在终端或临时报告：

- 实际候选 commit、基线 commit、worktree／branch 和测试入口。
- 本轮新取得的运行态事实及其观测点，例如 listener、PID、cgroup、unit `InvocationID`、数据路径、WAL 状态、健康结果和真实客户端结果。
- 正确样本、目标缺陷注入、live canary、local fault 和回滚演练的结果；未执行项保持 `UNVERIFIED`。
- 每个 gate 的状态变化、阻塞原因、责任切片和下一最小动作。
- 数据 disposition ledger 的逐项决定与证据。
- 结构怪味登记和本轮处置。

默认实施节奏不是普遍 TDD 门，而是：**先补齐可运行骨架，跑通 happy path，再建立真实入口 smoke；一旦这条纵向切片可复现且关键职责稳定，就在隔离实施分支上尽快把探索提交 squash 为可审查基线；随后补齐边界、故障、正反控制和回归证据。** Squash 只整理尚未集成的实施分支历史，不改写共享历史。已有骨架、probe 或可并行实现可直接补强；但任何 gate 标为 `PASS`、进入下一有副作用阶段或声称可切换前，相关自动测试或真实 probe 必须能区分正确与错误状态，高风险 gate 还必须保留正反控制、必要 mutation 与真实执行证据。

状态词固定为：

- `NOT_STARTED`：尚未开始。
- `IN_PROGRESS`：正在开发或取证，尚未达到 gate。
- `BLOCKED`：已观察到正确性缺陷或存在未裁决硬分叉。
- `UNVERIFIED`：尚无充分证据，不等于缺陷或通过。
- `PASS`：绑定明确候选和证据的本切片通过。
- `ROLLED_BACK`：切片曾执行但已按冻结回滚路径恢复。

## 总体切片与当前状态

| 顺序 | 切片 | 当前状态 | 进入条件 | 退出条件 |
|---:|---|---|---|---|
| 1 | Inventory 与基线冻结 | `IN_PROGRESS` | 无副作用只读探测可立即进行 | listener／owner／client／数据／回滚资产清单完整且可复验 |
| 2 | 备用端口启动 | `IN_PROGRESS` | Current main已有可运行候选、隔离配置和数据路径 | 真实Copilot app已在`4142`完成一次启动、readiness、请求与清理；重复启停、完整隔离和资源归零矩阵仍待闭合 |
| 3 | 协议 smoke 与 live canary | `IN_PROGRESS` | Current main已取得真实纯文本、tool与reasoning最小纵向正控 | Non-stream／stream、forced ordinary tool roundtrip与单item reasoning carrier echo HTTP 200已取得；完整tool／reasoning矩阵、错误／fault、direct Messages与完整Acceptance仍待闭合 |
| 4 | user systemd socket／service／slice dry-run | `BLOCKED` | S3／S4已main；本机private user-manager／cgroup不具备安全delegation | 在可销毁VM／container中由独立user manager完成fd、cgroup与退出路径验收 |
| 5 | Shadow／备用入口 | `NOT_STARTED` | 备用实例和协议 canary 通过 | 显式 canary 流量可稳定走备用入口，且无生产副作用或双写 |
| 6 | 冻结写入与数据 disposition | `NOT_STARTED` | 数据 inventory 完整、回滚副本策略可执行 | inventory 与 ledger 资产 ID 集合精确相等；每项均已从 `PENDING_DECISION` 收敛为 `MIGRATE／RETAIN_READ_ONLY／ABANDON` 之一，并完成相应预演 |
| 7 | 可回滚接管 `4141` | `NO_CUTOVER` | 前六片通过、替代验收 `PASS`、独立评审通过 | Python user socket 成为唯一 `4141` owner且回滚演练已证明 |
| 8 | 观察期 | `NOT_STARTED` | 接管成功 | 代表性流量、资源、重启、数据、协议与 `cc-daemon` 不变量持续成立 |
| 9 | 退役旧裸进程 | `NOT_STARTED` | 观察门通过且旧进程不再承担回滚即时启动职责 | 无旧 listener／自动拉起源，回滚资产只读保留，退役证据落盘 |

### 阶段执行矩阵

“预计文件”只指后续实施可能涉及的落点，不授权本轮创建或修改；实际路径若变化，必须先回写本表。实现、测试与 living plan 同步推进，不把“先写失败测试”设为普遍准入条件；纯运行态阶段使用真实 probe、正反控制和可复现演练，不能用伪造单元测试替代。

| 切片 | 前置依赖 | 预计文件／资产 | 测试与证据 | 验收判据 | 主要风险 | 回滚／恢复 |
|---|---|---|---|---|---|---|
| 1 Inventory | 固定 main gate；只读权限 | 本文 current inventory 表；未来可选 inventory／redaction测试资产 | 双栈 listener正反控制、secret redaction、owner漂移、恢复资产存在性 | listener、client、unit、data、rollback manifest均可复验 | 错查进程、泄漏 secret、把快照当永久事实 | 探针必须零副作用；若造成变化立即停止并恢复原状态 |
| 2 备用端口 | 完整可运行候选；隔离配置／数据 | 候选 config、`src/app/cli.py`相关启动接缝、startup／shutdown测试 | 端口冲突、数据隔离、缺配置失败、重复启停、健康与资源归零 | 非 `4141` 实例稳定，旧前门与 `cc-daemon`完全不变 | 误占生产端口、共享 SQLite、orphan process | 只停止精确备用实例并确认资源归零；旧前门无需变化 |
| 3 协议 smoke／canary | 备用实例 ready；current Spec／Acceptance一致 | Acceptance规划的 conversion、HTTP、stream、WS、lifecycle与fixture资产 | required gates、mutation、Anthropic SDK、strict grammar、live／corpus／fault | 同一候选的完整 bridge产品 gate为 `PASS` | fake失真、旧 hash、helper-only假绿、真实工具副作用 | 停止备用实例，保留失败证据；生产前门未变 |
| 4 user systemd dry-run | inherited socket、graceful shutdown接缝可测 | `src/app/cli.py`／server adapter、未来 `contrib/systemd/user/`、unit／smoke测试 | unit parser、`systemd-analyze verify`、双 fd、activation、SIGTERM、cgroup、force timeout | 备用端口 user socket／service／slice全链路通过，`cc-daemon`身份不变 | system-level字段误用、单栈、fd错配、daemon-reload外溢 | 只停止／移除候选 unit；不操作 user manager整体或 `cc-daemon` |
| 5 Shadow／备用入口 | 切片 2～4相关门通过 | canary client、脱敏 corpus、比较报告 | 显式真实 canary、离线 replay、旧新规范化比较、无副作用证明 | 代表性协议稳定且无双写／重复工具／approval | 真实请求成本、随机输出、隐私、重复副作用 | 关闭备用入口并保留 corpus／报告；旧前门未变 |
| 6 数据 disposition | 完整数据 inventory；备份／转换PoC | disposition ledger、backup／restore测试资产、脱敏 config manifest | SQLite在线备份与恢复、WAL一致性、inventory＝ledger集合门、writer唯一性、tokenization原子文件、权限 | 每项资产有明确 disposition、预演和回滚语义，无双 writer | 热拷贝损坏、schema不兼容、凭据被改写 | 停新 writer，按逐项 disposition 恢复冻结旧资产；不删除任何源数据 |
| 7 `4141` 接管 | 切片 1～6与替代验收全 `PASS`；独立评审通过；时间门已裁决 | 冻结 user units、candidate、config引用、cutover／rollback manifest | supervisor／listener／writer fence、配置化 deadline、双栈 listener、readiness、协议 canary、data owner、`cc-daemon`身份 | systemd socket唯一持有双栈 `4141`，service ready；失败时按已实测的回滚 deadline 恢复 | 首次监听窗口、旧 supervisor复拉、长连接断开、restart loop、数据错误 | 关闭新 socket／service，按冻结顺序恢复旧 supervisor、listener、writer与双栈健康 |
| 8 观察 | 接管成功；观察窗口／样本量已冻结 | metrics／logs／History／cgroup证据与观察记录 | 代表性真实流量、长连接、一次 service restart、资源与数据持续检查 | 无未解释协议／资源／数据／daemon回归 | 低流量假稳、MemoryHigh／OOM、旧 writer复活 | 任一触发器执行切片 7冻结回滚，不现场发明修复 |
| 9 退役旧进程 | 观察 `PASS`；旧自动启动源已识别 | 旧实现 archive、rollback manifest、`DISCARD_LATER`清单、退役记录 | login／timer／watcher复活检查、端口／锁／writer检查、最终 canary | 旧进程与自动拉起源停用，回滚资产只读保留 | 禁错 supervisor、误删数据、把 `cc-daemon`纳入退役 | 恢复旧自动启动源仅需单独裁决；默认不删除所以资产仍可用 |

## 切片 1：Inventory 与基线冻结

### 目标

在不改变任何进程、unit、配置或数据的前提下，证明“当前是谁在服务、谁依赖它、数据在哪里、如何原样恢复”。Inventory 结果是后续所有动作的输入，不是一次性附录；每次切换演练前都重新生成差异并更新本节。

### 必须盘点的对象

1. **前门与 listener**：分别检查 IPv4／IPv6 loopback、socket inode、PID、exe、cmdline、cwd、parent、启动时间、环境来源摘要、cgroup、open files 和监听 backlog。不得只凭进程名判断 owner。
2. **旧实现身份与 restart owner**：固定 `copilot-api-js` repo／worktree、commit、运行入口、runtime 版本、依赖锁、配置文件、环境文件和工作目录；机械记录 listener child 与 `start --restart` parent／supervisor 的 PID、start time、cmdline、cwd、cgroup、父子关系、restart 合同和经过隔离验证的精确停止／恢复原语。保存可重建旧命令，但不得把 token 或 secret 写进本文；一次 `ss` 空结果或只停止 listener child 均不算 supervisor 已 fenced。
3. **客户端**：列出连接 `localhost:4141` 的 Claude Code／SDK／脚本／测试，确认其 DNS 解析顺序、IPv4／IPv6行为、keepalive、SSE／WebSocket 使用和重试行为。
4. **`cc-daemon` 基线**：记录 `cc-daemon.service` 与 `cc-daemon-calib.service` 的 active state、PID、`InvocationID`、cgroup 和 socket；只读，不读取或输出敏感会话内容。
5. **旧数据与 writer**：定位旧实现的 config、credentials、History DB／WAL／SHM、search index、session state、cache、logs、临时 socket和所有 background writer；对每个 current inventory 资产记录 producer／consumer、打开它的 PID／fd／锁、SQLite transaction／WAL 观测点及所属 supervisor，不能由“listener 已停”推断 writer 已停。
6. **新数据**：解析候选实际 `AppSettings`，记录 History、tokenization、auth token file、config、logs 和可选 cache 的最终绝对路径；默认路径不能替代运行时解析结果。
7. **恢复资产**：验证旧二进制／源码、配置引用、环境来源、数据目录和启动入口均仍存在；形成不含 secret 的 rollback manifest。

### 骨架与验证顺序

本切片主要是运行态取证，不能用单元测试替代。先形成能枚举 parent／child／listener／writer／资产 ID 的 inventory 骨架和 happy-path 输出，再以 current 双栈 Bun 服务做只读 smoke；随后补 parser、redaction、地址族遗漏、supervisor 漂移和 writer 漏报边界。验收至少包含：

- 已知存在 IPv4＋IPv6 listener 的正样本能列出两者；故意只返回一个地址族时 gate 变红。
- secret 字段、token、Authorization 与完整环境不得进入报告；注入假 secret 后 redaction 测试必须捕获。
- listener PID 变化、exe／cwd／commit漂移或旧启动资产缺失时，diff gate 必须停止后续阶段。
- `--restart` parent仍可复拉 child、任一 inventory 资产仍有 open writer fd、listener或WAL在配置化稳定观察窗内复活时，fence gate 必须保持红。
- Inventory 只能读，不得出现 signal、unit state change、file mutation 或 network route change。

### 验收与回滚

本切片无运行态变更，因此无需服务回滚。任何探针自身造成状态变化都视为失败，停止计划并恢复被改变对象。退出时本节需增加一张 current inventory 表，绑定执行时间、候选 commit、旧实现 commit 和证据位置。

## 切片 2：备用端口启动

### 目标

在不占用 `4141`、不改变 `cc-daemon`、不共享可写数据的情况下启动完整 Python 候选。备用端口从当次 inventory 的空闲 loopback 端口中选择，示例可用 `4142`，但不得把示例值当成永久配置。

### 前置实现门

- 候选必须包含待替代的完整 bridge，而不是只有 converter、parser、carrier 或 foundations。
- 配置必须显式选择备用 host／port、独立 XDG data、独立 History DB 和独立 tokenization state。
- 若凭据需要复用，只允许通过既有受控来源读取，不复制 secret 到计划、日志或命令历史；新实例不得改写旧凭据资产。
- 候选启动和停止必须有精确 owner，不能依赖 shell 背景任务失联运行。

### 实施与验证顺序

1. 补齐候选启动骨架，先用隔离 config／XDG data／History／tokenization 路径跑通单一备用端口 happy path。
2. 使用真实 loopback HTTP client完成 liveness／readiness和一次最小请求 smoke，不以“进程存在”作为 ready；纵向切片稳定后尽快整理实施分支提交，再继续扩边界。
3. 补配置隔离、旧／新路径冲突、同一 SQLite writer、端口冲突和双栈绑定证据；备用实例不得触碰 `4141`，目标 host必须与 canary客户端一致。
4. 补缺配置、缺 token、错误 schema、端口占用、重复启停和 orphan process等失败路径，要求明确失败且资源归零。
5. 运行 startup／shutdown integration、全仓 pytest、Ruff 与 Pyright，并把结果绑定候选 commit回写本文。

### 退出判据

- 备用实例可重复启动、健康、停止和再次启动，PID／连接／文件句柄均无泄漏。
- 旧 `4141` IPv4／IPv6 listener、旧健康和 `cc-daemon` PID／`InvocationID` 在整个切片前后不变。
- 新实例写入只出现在隔离数据目录。
- 停止新实例后，History close、tokenization flush、upstream close 和 background task cleanup有可观测证据。

### 风险与回滚

备用实例异常时只停止其精确进程或候选 user service；旧 `4141` 从未改变，因此回滚是“确认备用实例资源归零”。不得为修复候选而重启 `cc-daemon`。

## 切片 3：协议 smoke 与 live canary

### 目标

证明备用实例不只是“能监听”，而是能以真实 Anthropic 客户端合同正确完成 Responses bridge，并保持 direct Messages、错误、stream、History 与生命周期语义。

### 分层验证

1. **静态／单元**：执行 current `acceptance.md` 的 request、response、usage、carrier、unknown field、tool、reasoning 与 grammar gates。
2. **组件**：真实 pipeline owner＋fake upstream，验证一次 approval、单 History、attempt 数等于真实 exchange 数、pre-commit retry 和 post-commit partial failure。
3. **真实 HTTP／socket／WS**：从备用端口的真实 ASGI 入口验证 non-stream、SSE、取消、slow consumer、RST、EOF、partial write 和 HTTP／WS parity。
4. **live canary**：只执行可确定、低副作用的真实上游 text、tool、reasoning、incomplete／limit canary；不可控异常由版本化 capture corpus 与 local fault覆盖。
5. **客户端独立 oracle**：用固定版本 Anthropic SDK消费输出，并同时运行独立 strict grammar oracle；SDK宽松接受不能覆盖 grammar 失败。

### 必需 smoke 集合

- `/health/liveness` 与 `/health/readiness`。
- Anthropic `/v1/messages` 非流 text。
- Anthropic `/v1/messages` stream，首个完整 block 前零 success headers／body，并由 SDK完整消费。
- Anthropic→Responses reasoning，包括 encrypted-only、多 reasoning item 与 carrier echo。
- function tool declaration、forced choice、tool call／result roundtrip。
- Responses-only、Messages-only、双支持默认 Messages、显式 Responses override和 unknown capability fail closed。
- upstream 4xx／429／5xx、failed／incomplete、clean EOF、client cancel和 post-commit error。
- `/v1/messages/count_tokens`、History entry、hooks phase、approval rejection和 tokenization calibration。

### 退出判据

本切片只有在当前候选绑定的 required gates 全部具备正样本、目标缺陷注入、可确定 live canary、必要 corpus provenance 和 local fault证据时才能标 `PASS`。任一 required gate 缺证据保持 `UNVERIFIED`，不能以“备用端口手测正常”代替。

## 切片 4：user systemd socket／service／slice dry-run

### 目标

把候选 system-level 模板转换为真正的 user systemd 运行基座，并在不占用 `4141`、不安装生产 unit、不影响 `cc-daemon` 的条件下证明 socket inheritance、service activation、graceful shutdown 和 cgroup限制。

### Current 阻断与下一环境

S3 graceful timeout与S4 rootless installer已进入main并归档。当前本机VS Code调用进程位于root所有且不可写的`/init.scope`；独立`systemd --user`在private control socket创建前退出，真实activation、fd inheritance、effective cgroup、restart与manager stop均未执行，因此本切片运行态仍为`BLOCKED`。真实Copilot app canary取得readiness及请求HTTP 200只证明应用路径，不是manager／cgroup证据。下一最小环境是具备独立login session／user manager与delegated cgroup v2的可销毁VM或container；不得退回宿主user manager，也不得把static verify、direct inherited-fd或canary 200冒充本切片通过。

### user unit 适配要求

- user service 不使用 `User=`／`Group=`，不使用 `/opt` 与 `/etc` 的 system-level 假设；部署路径、虚拟环境、config 和 environment file必须是明确的 user-owned绝对路径或经过验证的 specifier。
- `.socket` 负责 listener，`.service` 不再自行 bind host／port；host／port配置不得与 inherited fd 同时生效。
- 当前 front door 同时包含 `127.0.0.1` 与 `::1`。目标 user socket必须保持两个地址族，或在切换前取得明确合同变更。推荐保持双栈，并让应用按 systemd `LISTEN_FDS`／`LISTEN_FDNAMES`消费全部声明 socket；仅硬编码 `fd 3` 的单 socket实现不足以替代当前前门。
- `Accept=no` 保持一个 service处理监听 socket。Backlog 是有限容量，不得描述为无限排队或请求成功保证。
- `.service` 与 `.socket` 不得声明对 `cc-daemon.service`、`cc-daemon-calib.service` 或其 target 的 `PartOf=`、`BindsTo=`、`Conflicts=`、`Requires=` 或 restart传播关系。
- Current `Type=exec` 只证明进程成功跨过 `execve()`，不说明应用 ready。没有真实 `sd_notify(READY=1)` 前不得改称 `Type=notify`；切换 gate 必须独立轮询 readiness。
- 自定义 user slice只约束代理 service。它位于 user manager 的父 cgroup限制之下，不能宣称获得 system-level资源保证，也不得把 `cc-daemon` 移入该 slice。
- user manager退出后的存活需求必须在 inventory 中明确。若服务必须跨 logout持续运行，应先验证当前 linger政策；启用 linger属于独立主机状态变更，不在 dry-run中自动执行。

### socket activation 保证

在 unit 与应用接线均正确时，socket activation可以保证：

- systemd 在 service未运行时持有已声明的 loopback listen socket，并可在连接到达时激活 service。
- 单个 service重启期间，尚未被应用 accept 且未溢出 backlog的连接可等待新进程接收。
- service异常退出后，只要 socket仍 active且 restart／activation策略允许，后续连接可再次触发 service。
- listener与 service cgroup owner可由 systemd查询和审计。

### socket activation 不保证

- 不保证首次从当前 Bun listener交接到 systemd socket时无监听窗口，因为两个 owner不能同时独占同一地址／端口。
- 不迁移已被旧进程 accept 的 HTTP／SSE／WebSocket连接，也不保证它们不断开。
- 不保证 service ready、上游认证成功、模型目录已加载或 bridge语义正确。
- 不保证 backlog不溢出，不保证客户端 timeout大于应用启动／重启时长。
- 不提供双实例 rolling、旧新进程重叠服务、客户端 durable acknowledgement或跨崩溃 exactly-once。
- 不替代应用的 graceful shutdown、History flush、upstream close、cancel和错误终态。

### graceful shutdown 门

候选必须用真实进程和真实连接证明：

1. SIGTERM 后停止新 application admission，但 systemd socket仍保持 listener。
2. 已 accept 的短请求可在 grace内完成；长 SSE／WS按已冻结 shutdown合同 drain或被明确 abort，不伪装 success。
3. pending approval被拒绝，tokenization完成最终 flush，History writer关闭，upstream HTTP／WS和 background task归零。
4. `TimeoutStopSec` 大于应用自身 grace上界；超时后 systemd只清理本 service cgroup，不影响 `cc-daemon`。
5. `KillMode` 行为、primary／secondary cleanup error和强制退出状态均可观测。
6. 当前 `ShutdownManager` 若未接入真实 server lifecycle，必须先补生产接线与端到端测试；不能以类存在或设计文档代替。

### 实施节奏与 dry-run

1. 先建立 user `.socket`／`.service`／`.slice`与 CLI／server inherited socket 的最小骨架，在备用端口跑通单 fd happy path和真实 activation smoke。
2. 扩为双具名 fd／双栈 happy path，验证 `.socket`、`.service`、`.slice`引用一致性、`systemd-analyze verify`、真实 readiness和一次请求；纵向切片稳定后尽快整理实施分支提交。
3. 再补 unit parser边界，拒绝 system-only字段、错误依赖、单地址族遗漏、错误 fd name、host／port＋fd冲突和缺失 slice；补未知 fd name、重复 fd、非 socket fd及直接 host／port兼容路径。
4. 在临时 unit目录或隔离 user-manager中以备用端口执行 restart、SIGTERM、backlog和cgroup fault probe。若必须对真实 user manager执行 `daemon-reload`，先证明它不会 restart unit，并在前后机械核对两个 `cc-daemon` unit 的 PID／`InvocationID`；本计划当前不执行该动作。
5. 用 `/proc/<pid>/cgroup` 与 systemd属性核对代理进入目标 slice，并对 MemoryHigh／MemoryMax／CPUQuota／TasksMax的有效值做正反控制。

### 退出判据

- Unit静态验证、真实 activation、双栈 listener、fd inheritance、readiness、restart、graceful shutdown、force timeout和cgroup均绑定同一候选通过。
- 代理 user unit与 `cc-daemon` 无依赖传播，dry-run前后 `cc-daemon` PID／`InvocationID`不变。
- 生产 `4141` 未被占用或修改。

## 切片 5：Shadow／备用入口

### 目标

在切换前让候选接受可控、可比较的真实请求，同时不自动镜像具有副作用的生产流量。

### 采用路径

- 保留备用 loopback端口作为显式 canary入口，由测试客户端或独立 SDK直接调用。
- 使用脱敏 capture corpus做离线 replay，比较旧实现和新实现的规范化 Anthropic结果、错误类别、usage和时序。
- 对真实上游只发送明确标记、低副作用、可重复的 canary；tool canary使用测试工具，不触发真实外部动作。
- `cc-daemon` 继续使用 `localhost:4141`，不通过修改其环境或 endpoint来访问备用入口，因此不需要重启。

### 不采纳路径

默认不把所有生产请求复制给新实例。原因是生成请求会产生上游成本、工具副作用、History双写、approval重复和不可比较的随机输出。若未来确需在线 shadow，必须先定义只读请求白名单、去副作用策略、凭据与数据隔离、采样、成本、隐私和比较 oracle，并取得独立裁决。

### 退出判据

- 备用入口在代表性的 non-stream、stream、reasoning、tool、错误和长连接场景下稳定。
- 旧／新比较只归一 transport-only差异，不掩盖 block顺序、carrier、call id、usage或 terminal差异。
- 新实例无生产工具副作用，无旧数据写入，无 `cc-daemon`状态变化。

## 切片 6：冻结写入与数据 disposition

### 目标

在切换前为所有持久化与运行态资产明确唯一 owner、切换动作、回滚动作和最终保留政策。未完成的条目就是硬阻塞，不允许以“之后再整理”跳过。

### disposition 词汇

- `MIGRATE`：通过版本化转换或明确映射进入新服务，并有源／目标核对、语义抽样、校验和与回滚副本。
- `RETAIN_READ_ONLY`：切换后不进入新 writer 热路径，以一致快照或冻结原件只读保留；回滚时只有按 manifest 重新激活旧 owner后才可恢复写入。
- `ABANDON`：明确不把该资产带入新服务语义，候选从 source of truth重建或重新学习；源文件仍只读保留，删除需另行授权，不能把“放弃迁移”解释为立即删除。
- `PENDING_DECISION`：格式、owner、业务价值或回滚代价尚未裁决，是切换硬阻塞，不能用默认值跳过。

### 数据 disposition ledger

Ledger ID 必须由 current inventory 生成；当前冻结的 `CUTOVER-ASSET-INVENTORY-v1` 至少包含下表全部 ID。每次 inventory 重取后，机械比较 `inventory_asset_ids == ledger_asset_ids`；任一新增、消失、拆分或合并的可变资产都会把数据门恢复为 `UNVERIFIED`，直到 ledger 同步且重新评审。复合 SQLite 行的 ID 覆盖主文件和当次发现的 `-wal`／`-shm`，不得只核主文件。

| 资产 ID | current inventory资产 | 当前 disposition | producer／consumer与 writer fence | 备份／恢复 probe | 当前状态 |
|---|---|---|---|---|---|
| `old-history-v3-set` | `history-v3.db`＋`history-v3.db-wal`＋`history-v3.db-shm` | `RETAIN_READ_ONLY`；没有已验收 converter前不导入 Python | 当前 Bun已直接打开三件套；枚举全部 open fd／锁／事务，fence旧 supervisor后等待配置化稳定窗内无 writer、无 WAL增长、无 child复活 | writer在线时用 SQLite backup API／等价一致快照；停写后验证完整集合、integrity、关键查询及旧版本恢复启动 | `UNVERIFIED` |
| `python-history-db` | 候选实际解析路径的 `history.db` | `PENDING_DECISION`；须裁决“生产新建”还是从已验收来源 `MIGRATE` | Python History owner唯一；备用实例路径、正式路径和旧 Bun资产不得重合 | 验证 schema／reaper／close／恢复；回滚停止新 writer并保留诊断副本，不交给旧服务 | `UNVERIFIED` |
| `legacy-history-db-sets` | 其他 History版本及归档 History数据库 | `RETAIN_READ_ONLY` | 逐文件枚举 producer、consumer、主文件／WAL／SHM与 open fd；不能假定旧版本无 writer | 一致快照、integrity、关键查询和旧工具只读打开 | `UNVERIFIED` |
| `archive-db-set` | `archive.db`及发现的 WAL／SHM | `RETAIN_READ_ONLY` | 识别 archive producer／consumer与全部 writer；纳入旧 supervisor／writer fence | 一致快照、integrity、关键 archive查询和旧版本恢复 | `UNVERIFIED` |
| `telemetry-db-set` | `telemetry.db`及发现的 WAL／SHM | `ABANDON`；新服务不继承旧 telemetry状态 | 识别独立 telemetry writer并纳入 fence；新旧 sink路径隔离 | 冻结一致快照供审计；回滚只恢复旧 owner，新服务从自己的 telemetry起点开始 | `UNVERIFIED` |
| `request-telemetry-json` | `request-telemetry.json` | `ABANDON`；候选不导入运行计数 | 记录写入者、原子替换／锁与mtime；稳定窗内不得变化 | 冻结原件与digest；回滚由旧服务继续使用原件 | `UNVERIFIED` |
| `thinking-quarantine-db-set` | `thinking-quarantine.db`及发现的 WAL／SHM | `PENDING_DECISION`；必须裁决保留价值与候选兼容性 | 识别 quarantine producer／consumer及 writer；任何未识别 writer阻断切换 | 一致快照、integrity、代表性记录抽样和旧版本恢复 | `UNVERIFIED` |
| `negotiation-states-json` | `negotiation-states.json` | `ABANDON`；候选重新协商 | 记录 writer、原子替换／锁与mtime；旧 writer必须 fenced | 冻结原件与digest；回滚重新交还旧 owner | `UNVERIFIED` |
| `learned-limits-json` | `learned-limits.json` | `ABANDON`；候选重新学习，不假定格式兼容 | 记录 writer、刷新周期、原子替换／锁与mtime；稳定窗内不得变化 | 冻结原件与digest；回滚旧服务继续原状态 | `UNVERIFIED` |
| `history-search-dir` | `history-search/` | `ABANDON`；从已决 History source of truth重建 | 识别索引 writer、版本与打开文件；不得让新旧 indexer共写 | 冻结目录manifest／digest并验证可重建；回滚使用冻结旧索引或由旧版本重建 | `UNVERIFIED` |
| `system-prompts-dir` | `system-prompts/` | `MIGRATE`；仅按已核对的配置语义复制，不共享可写目录 | 识别生成者／消费者、文件权限和任何 watcher；候选目标目录独立 | 源／目标文件集合、digest、解析结果与回滚旧路径核对 | `UNVERIFIED` |
| `copilot-logs` | `copilot-api.log`、轮转文件与 `logs/` | `RETAIN_READ_ONLY` | 旧日志 writer关闭；新服务使用独立 sink，时间边界关联 PID／InvocationID／commit | 冻结manifest／digest和读取权限；回滚重新打开旧 sink前确认无新 writer | `UNVERIFIED` |
| `copilot-pid-file` | `copilot-api.pid` | `ABANDON`；它只作旧进程辅助证据，不迁移为新 supervisor真相源 | 用 PID＋start time＋cmdline＋cwd＋cgroup＋socket owner核实旧 owner，不能仅凭PID文件发信号 | 冻结旧文件供审计；新 supervisor重建自己的运行态标识，回滚由旧入口重建 | `UNVERIFIED` |
| `github-token` | `github_token`或实际受控 credential provider | `RETAIN_READ_ONLY`；候选只读复用，除非 refresh合同另行裁决 | 核对权限、owner、读取者、refresh写行为与secret redaction；若会写则改为`PENDING_DECISION` | 只验证可读性、权限和digest引用，不把secret写入报告；旧服务仍可从原来源启动 | `UNVERIFIED` |
| `copilot-config` | `config.yaml`及受控环境引用 | `MIGRATE`；迁移已核对的配置语义，不复制报告中的秘密正文 | 对比脱敏 effective config、owner、mode、环境来源与 watcher；候选配置独立且不可回写旧文件 | 解析结果、非敏感字段、权限和secret引用核对；保留旧配置原件 | `UNVERIFIED` |
| `python-tokenization-state` | 候选实际 `tokenization.json` | `ABANDON`旧状态并由候选独立新建；若发现可迁移源则回到`PENDING_DECISION` | 候选 writer唯一，验证原子写、版本、损坏恢复和shutdown flush | 回滚保留新文件供诊断，旧实现继续自己的状态 | `UNVERIFIED` |
| `inflight-requests-approvals` | in-flight request／pending approval运行态 | `ABANDON`；不迁移，不重放已产生副作用的请求 | active request与pending approval归零，或按已接受合同明确abort；状态面不可观测则阻断 | 记录最终状态与副作用边界；回滚不重放 | `UNVERIFIED` |
| `accepted-stream-connections` | 已accept的SSE／WebSocket连接 | `ABANDON`；不迁移连接 | 记录连接数、grace政策和客户端重连；listener fence不能冒充连接迁移 | 验证明确终态／abort与重连，回滚只接受新连接 | `UNVERIFIED` |
| `temporary-runtime-artifacts` | 临时socket／lock及inventory发现的其他运行态文件 | `ABANDON`；由目标owner重建 | 逐项识别owner和open fd，稳定窗内无旧owner复活 | 冻结路径manifest；观察完成前不删除，回滚由旧启动入口重建 | `UNVERIFIED` |

### 冻结写入顺序

1. 先冻结部署内容、候选 commit、unit bytes、配置引用和 rollback manifest，禁止在切换窗口继续改代码或配置。
2. 重取 inventory并执行资产 ID集合相等门；任一 ledger行仍为`PENDING_DECISION`、缺producer／consumer、缺writer观测点或缺恢复probe，保持`NO_CUTOVER`。
3. 通过旧实现自己的状态面确认无待处理 approval、无必须保留的 in-flight写入；若无法观测，选择配置化安静观察窗并按未知风险处理，不虚报 drain完成。
4. 对需要快照的 live数据库使用与其协议一致的在线备份方法；不要先停服务再临时设计备份。
5. 先技术性 fence已验证的`--restart` parent／supervisor，使其不能创建新child；再停止旧admission和listener child。随后枚举全部旧writer，确认数据库fd／锁关闭，并在配置化稳定观察窗内持续证明parent／child／listener／writer均未复活，WAL／SHM／mtime未继续变化。
6. 只有 supervisor、listener和writer三道fence全部通过，才把旧可变资产标记为frozen；不得把kill单一PID或一次`ss`空结果当作完成。
7. 新服务只打开已分配给它的资产；任何文件锁、WAL、mtime或计数显示双写，立即进入冻结回滚。

## 替代验收门

`4141` 切换必须同时满足以下门。任何一项是 `UNVERIFIED`、`BLOCKED` 或绑定旧候选，整体都不是 `PASS`。

| 门 | 必须证据 |
|---|---|
| Spec／Acceptance一致性 | Current Spec `FINALIZED@4c9beed…`与Acceptance `FINALIZED_ACCEPTANCE_ORACLE@f99492a…`保持内容绑定，且Acceptance首屏绑定current Architecture `746adc7…`并声明其不产生expected；任一内容身份变化都会使本门恢复为`UNVERIFIED`并重新对账，不得沿用旧hash verdict |
| 完整 bridge产品 | `acceptance.md` 的全部 current required gates按同一候选执行，正确样本绿、目标缺陷注入按目标原因红 |
| 真实入口 | 备用端口真实 ASGI／HTTP／socket／WS路径通过，不是 helper-only |
| live与fault | 可确定 live canary通过；必要 capture corpus provenance有效；local fault覆盖RST、EOF、slow consumer、partial write、cancel和shutdown |
| direct Messages回归 | 未选择 Responses时既有 Messages行为、headers、History、hooks、approval和count_tokens不回归 |
| 前门兼容 | IPv4 `127.0.0.1:4141` 与 IPv6 `[::1]:4141`均按 current客户端合同工作；`localhost`解析顺序不会造成失败 |
| systemd runtime | user socket／service／slice、fd inheritance、activation、readiness、cgroup、restart与graceful shutdown通过 |
| 数据 | disposition ledger全部有决定和预演；无双写；备份与恢复均验证 |
| supervisor／listener／writer fence | 精确识别`--restart` parent／child／supervisor及停止／恢复原语；旧parent不能复拉；双栈listener和所有inventory writer在配置化稳定窗内均未复活 |
| 回滚 | 在备用端口或隔离演练中完成“新失败→释放 socket→按冻结顺序恢复旧 supervisor／child／writer→旧双栈 listener／readiness／真实请求通过”全链路，并满足已裁决 deadline |
| `cc-daemon`不变量 | 全流程不重启、不改配置，PID／`InvocationID`不变；经原 `localhost:4141`前门的真实请求成功 |
| 独立评审 | 本计划、unit bytes、切换 runbook证据和最终 merged candidate均完成相应独立评审，blocker／major关闭 |

## 切片 7：可回滚接管 `localhost:4141`

### 首次接管的诚实边界

当前 Bun已占用 IPv4与IPv6 `4141`，systemd socket无法预先绑定同一地址。因此首次接管不能声称由 socket activation实现零监听窗口。计划目标是把窗口缩短、可检测、可回滚；若产品要求首次接管零窗口，必须另行引入已验证的前门代理、fd handoff或其他原子所有权方案，不能把 stop→bind两步法包装成原子操作。

### 切换前冻结件

- 精确候选 commit和构建／环境身份。
- user unit bytes及内容 hash。
- effective config的脱敏摘要和 secret来源引用。
- 旧启动 rollback manifest与旧健康 canary。
- 数据 disposition与备份验证结果。
- 接管、健康、协议 canary、观察和回滚的操作者 checklist。
- 本轮允许的明确动作范围；不包含 `cc-daemon`任何生命周期动作。

### 配置化时间门、观察窗与失败阈值

正式切换前必须把下列符号写入版本化 cutover gate manifest，绑定候选 commit、unit hash、inventory hash和单调时钟来源。本文不编造具体分钟数；每个值都必须由备用端口／隔离切换与回滚演练实测分布、客户端现有 timeout／retry预算及用户可接受中断／恢复目标共同裁决。任一值仍为`PENDING_DECISION`、未实测或大于客户端预算时，保持`NO_CUTOVER`。

| 配置项 | 机械起止点 | 超限动作 |
|---|---|---|
| `D_OLD_RELEASE_MAX` | 从发出已验证的旧 supervisor fence动作，到旧parent不可复拉、旧child退出、IPv4／IPv6 listener均释放且全部旧writer关闭 | 立即中止接管；若旧服务仍可安全恢复则按回滚manifest恢复，否则保持端口隔离并升级人工处置，不启动新socket |
| `W_OLD_FENCE_STABLE` | supervisor／child／listener／writer首次全部归零后，连续采样直至窗口结束；期间进程树、socket inode、open fd／锁及WAL／SHM／mtime均不得复活或增长 | 任一采样失败即重置窗口并判本次fence失败；不得进入新socket bind |
| `D_NEW_LISTENER_MAX` | 旧fence稳定窗通过后启动目标socket，到systemd成为IPv4／IPv6唯一listener owner | 触发冻结回滚 |
| `D_NEW_READY_CANARY_MAX` | 双栈listener成立后，到readiness及冻结最小canary集合全部通过 | 触发冻结回滚；不得只因unit active继续等待 |
| `D_CUTOVER_TOTAL_MAX` | 从旧双栈listener首次不再可用，到新双栈listener、readiness及冻结最小canary集合全部通过 | 即使各分段尚未分别超限，总门一旦超限也触发冻结回滚 |
| `D_ROLLBACK_RECOVERY_MAX` | 回滚触发器首次成立，到新owner／writer关闭、旧supervisor按manifest恢复、旧双栈listener／readiness／真实请求全部通过 | 标记恢复目标失败并升级人工处置；不得宣称“快速”或“立即”恢复 |
| `W_POST_CUTOVER_MIN` | 新最小canary通过后开始，覆盖冻结的代表性流量、长连接与restart场景后结束 | 未覆盖全部状态条件则只能延长观察或回滚，不能按墙钟到点自动`PASS` |

失败阈值同样在 manifest 中配置：owner／地址族／数据损坏／双writer／`cc-daemon`身份变化／required canary语义失败属于单次即失败的不变量；restart增量、错误率、partial failure、latency、资源、fd／task增长和History队列则使用切换前冻结的同口径 baseline、样本下限、允许偏差与连续窗口。不得在切换现场临时放宽阈值，也不得因样本不足把“未观察到失败”写成通过。

### 计划动作序列

以下只定义执行顺序，本轮不执行：

1. 重新跑 inventory和全部 pre-cutover gate，确认旧 listener身份、candidate、unit、数据和 `cc-daemon`基线未漂移。
2. 确认备用实例在备用端口 ready，并运行最后一组 Anthropic→Responses canary。
3. 停止备用实例，确保它已 flush／close且不会与正式实例竞争数据或 cgroup。
4. 先按inventory冻结的精确原语技术性fence `start --restart` parent／supervisor，证明其不能再创建listener child；再停止旧admission并对精确child发起graceful stop。不得使用宽匹配kill，也不得只kill当前listener PID。
5. 以单调时钟执行`D_OLD_RELEASE_MAX`和`W_OLD_FENCE_STABLE`：持续确认旧parent／child、IPv4／IPv6 listener和全部inventory writer均归零，socket inode、open fd／锁、WAL／SHM／mtime无复活或增长，且`cc-daemon`仍未变化。只观察一次空端口不通过。
6. 启动预先验证的 user socket；确认两个 loopback listener都由目标 `.socket`持有，再触发 service。
7. 以单调时钟同时执行`D_NEW_LISTENER_MAX`、`D_NEW_READY_CANARY_MAX`与`D_CUTOVER_TOTAL_MAX`，等待真实 readiness，不以 `active (running)`代替。
8. 经 `localhost:4141`依次运行冻结的最小canary集合，包括liveness、Anthropic non-stream、Anthropic stream、reasoning／tool和direct Messages；任一required项失败立即回滚。
9. 核对 service cgroup、resource limit、History／tokenization owner、日志候选身份和无 restart loop。
10. 进入观察期；旧启动资产与数据保持可按已实测 `D_ROLLBACK_RECOVERY_MAX` 执行恢复，不删除、不覆盖；该门未通过前不得声称即时恢复能力。

### 自动回滚触发器

出现任一项立即停止推进并执行冻结回滚，不在现场发明修复：

- 旧supervisor未fenced、旧child／listener／writer在`W_OLD_FENCE_STABLE`内复活，或`D_OLD_RELEASE_MAX`超限。
- `D_NEW_LISTENER_MAX`、`D_NEW_READY_CANARY_MAX`、`D_CUTOVER_TOTAL_MAX`任一超限，任一地址族未监听或`localhost`客户端失败。
- Anthropic→Responses语义、block顺序、carrier、tool、usage、terminal或 error合同回归。
- service restart loop、OOM、cgroup limit异常、orphan process或 fd不一致。
- History／tokenization写入失败、双 writer、数据损坏或配置指向错误目录。
- `cc-daemon` PID／`InvocationID`变化、连接异常或真实请求失败。
- 无法确认下游 delivery状态、出现重复／丢失／partial success假象。
- 任何 gate证据与执行候选 commit／unit bytes不一致。

### 冻结回滚序列

1. 停止并禁用本轮激活的代理 user service／socket，使 IPv4与IPv6 `4141`完全释放；只操作本项目 unit。
2. 确认新 History／tokenization writer已关闭，保留其数据供诊断，不把它交给旧服务。
3. 启动单调时钟`D_ROLLBACK_RECOVERY_MAX`，按rollback manifest规定的确定顺序恢复旧supervisor，再由该supervisor建立精确child／writer；不得绕过supervisor临时手启另一个不受控child。
4. 验证旧服务重新拥有IPv4与IPv6 `4141`，旧readiness、liveness和冻结真实请求canary通过，并确认旧writer只打开原资产。
5. 机械核对 `cc-daemon`两个 unit仍是原 PID／`InvocationID`；经原前门完成真实请求。
6. 记录单调时钟完整时间线；若`D_ROLLBACK_RECOVERY_MAX`超限则明确标记恢复目标失败，不使用“立即／快速”措辞。把本轮标为`ROLLED_BACK`，保存新服务日志、cgroup与数据副本，记录触发器；未经根因修复、验证和复评不得重试切换。

## 切片 8：观察期

### 目标

用代表性真实流量证明接管后的语义、资源、数据和运维行为持续成立。观察期不是固定等待若干分钟后自动通过；其窗口和样本量必须在切换前根据 baseline流量冻结，并覆盖实际使用类型。

### 观察面

- `localhost` IPv4／IPv6 listener owner和 socket／service状态。
- readiness／liveness、service restart count、exit reason和 `InvocationID`。
- Anthropic Responses与direct Messages请求量、状态、error类别、partial failure、retry和 latency分布，并与切换前同口径 baseline比较。
- SSE／WebSocket长连接、client cancel、upstream close和shutdown cleanup。
- cgroup current／peak memory、MemoryHigh事件、OOM、CPU、tasks和压力。
- History queue／write／reaper、tokenization flush、数据文件owner和mtime，确认无旧 writer复活。
- `cc-daemon` PID／`InvocationID`、player／session可用性和经 `4141`真实请求。
- 日志中的 candidate commit／unit identity、secret redaction和未知错误。

### 通过判据

观察窗口按`W_POST_CUTOVER_MIN`和manifest中的样本下限执行，必须覆盖已冻结的代表性non-stream、stream、reasoning、tool、错误、长连接和service restart演练；单次即失败不变量必须保持为零，统计阈值必须在冻结baseline允许偏差内，且没有未解释的回归、restart、OOM、数据错误或`cc-daemon`变化。墙钟到点、样本不足或只在低流量下“无报错”均不能自动通过；状态条件未满足时只能延长观察或回滚。

## 切片 9：退役旧裸进程

### 目标

让旧 Bun实现不再作为 listener或自动恢复源，同时保留可审计、可恢复的只读资产。退役不等于立即删除。

### 动作与验收

1. 证明观察期通过，且 rollback资产已从“即时首选”降为“保留恢复件”的决定有明确记录。
2. 查清旧裸进程的启动来源，包括 shell、login脚本、desktop autostart、timer、user service、watcher或其他 supervisor；只禁用已证明属于旧代理的精确来源。
3. 验证旧进程不存在、不会在 login／新 shell／timer后复活，也不持有 `4141`或旧数据锁。
4. 保留旧 commit／binary、lockfile、脱敏 config引用、rollback manifest、History／index archive和切换报告。
5. 对 cache、临时 socket、PID、lock和旧日志提出 `DISCARD_LATER`清单；没有明确授权不删除。
6. 保持 `cc-daemon`运行，不把“退役旧代理”扩张为客户端 daemon迁移。

### 完成定义

- user systemd socket是唯一 `4141` listener owner，service在目标 slice中按需激活。
- 旧裸进程和其自动拉起源均不再活动。
- 数据 owner唯一，旧数据只读保留或按已决 disposition处理。
- 完整替代验收、切换、观察、回滚演练与退役证据均绑定同一最终候选。

## 文件与测试落点建议

以下是后续实现者的候选落点，不表示文件已存在或本轮允许创建：

| 职责 | 候选落点 | 主要测试 |
|---|---|---|
| inherited socket CLI／server接线 | `src/app/cli.py`及最小 server adapter | `tests/unit/test_cli.py`、真实 fd integration |
| user socket／service／slice | `contrib/systemd/user/`下的明确 user unit | unit parser、`systemd-analyze verify`、activation smoke |
| graceful shutdown生产接线 | 现有 server／runtime／shutdown owner | SIGTERM、长 SSE／WS、approval、History、tokenization、force timeout |
| cgroup验证 | smoke／integration测试资产 | slice membership、effective limits、OOM／restart fault |
| cutover inventory／canary | 测试或运维验证资产，路径遵从项目约定 | redaction、双栈、owner漂移、rollback演练 |
| bridge替代验收 | `../anthropic-responses-bridge/acceptance.md`规划的 acceptance资产 | required gates、mutation、live／corpus／fault |

## 阶段依赖与可并行性

- Inventory、bridge产品实现、user systemd unit静态设计和数据 schema研究可以并行，但都不能独立放行切换。
- 备用端口协议验证与 user systemd备用端口 dry-run可在各自环境并行；两者必须在正式候选上重新合并验证。
- 数据在线备份 PoC可在副本和测试 DB上提前完成；生产 writer freeze只能在切换阶段执行。
- `4141`接管、观察和旧进程退役严格串行。
- 谁在哪个 worktree执行由主会话编排；本文不指定 agent或执行主体。

## 风险登记

| 风险 | 影响 | 预防／探针 | 回滚 |
|---|---|---|---|
| 只监听 IPv4 | `localhost`优先解析 IPv6的客户端失败 | 双栈 inventory＋真实客户端正反测试 | 释放 socket并恢复旧双栈 listener |
| 单 fd实现遗漏第二 socket | 一个地址族未被应用 accept | `LISTEN_FDS`／fd names测试与真实双 listener probe | 同上 |
| `Type=exec`或process active误当 ready | socket已接收但应用未可用，客户端 timeout | 独立 readiness gate | 自动回滚 |
| 首次端口交接窗口 | 短暂 connect failure | 预装全部资产、冻结短路径、客户端重试校准、单调时钟记录 | 按已实测 `D_ROLLBACK_RECOVERY_MAX` 恢复旧 listener；未验证时不声称恢复时限 |
| 已 accept长连接中断 | SSE／WS会话失败 | grace与客户端重连测试，切换前连接 inventory | 恢复只影响新连接；不伪造旧连接续接 |
| SQLite双写或热拷贝 | 数据损坏／不一致 | owner、WAL、backup API、freeze gate | 停新 writer，恢复冻结旧资产 |
| cgroup过紧 | OOM／restart loop | 备用负载基线、MemoryHigh／OOM probe | 停新 unit，恢复旧服务 |
| cgroup过松 | 影响同 user其他工作负载 | effective limit与压力观察 | 调整后重新 dry-run，不触碰 `cc-daemon` |
| graceful shutdown文档强于实现 | 强杀导致数据／请求损失 | 真实 SIGTERM与timeout fault，不以类／文档存在作证 | 回滚并补生产接线 |
| user manager lifecycle不符 | logout后服务消失 | linger与session生命周期 inventory | 保持旧启动方式直至政策明确 |
| broad systemd操作影响 `cc-daemon` | 活跃会话中断 | 精确 unit操作，前后 PID／`InvocationID` gate，禁 daemon-reexec | 立即停止切换并按 daemon自身恢复流程处理，不擅自重启 |
| bridge gate沿用旧 hash | 错误实现被当成通过 | exact Spec／candidate／Acceptance绑定 | 禁止切换，重做对账与验收 |

## 结构怪味登记

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/cli.py`与current main的single-fd runtime | inherited socket骨架已进入main，但单fd合同仍不足以承载目标双栈socket activation | 在备用端口dry-run准备中保留直接启动兼容，设计并验证具名双fd、地址族遗漏、错误fd与host／port冲突证据；不得把single-fd main checkpoint写成真实manager已通过 |
| `src/app/shutdown.py` 与 `src/app/server.py:139-152` | 四阶段设计与当前 lifespan cleanup可能存在“文档能力强于生产接线”漂移 | 先用真实 SIGTERM探针判定；缺失则修共享生命周期基座，不在 unit层用更长 timeout掩盖 |
| current main systemd `.socket`／CLI | 单fd＋仅IPv4，而当前前门为IPv4＋IPv6 | 推荐改为具名多fd合同并做备用端口双栈真实activation测试；本轮只准备，不执行manager动作 |
| current main systemd `.service` | system-level `User=`／`Group=`／`/opt`假设与目标user unit职责错位 | 分离user模板并提供默认dry-run的render／check路径，不以条件堆叠一个万能unit |
| 旧／新数据目录 | 两套实现的 schema与owner不同，直接共用会产生双写与兼容风险 | disposition ledger逐项裁决，默认 archive旧数据、隔离新 writer |
| 备用 shadow | 自动镜像生成请求会重复副作用和成本 | 默认只用显式 canary＋离线 corpus，不做全流量镜像 |

## 每轮反思门

每个切片结束时必须逐项回答并回写：

1. **有没有更好的内部替代方案？** 例如稳定前门代理、multi-fd socket、readiness notification或更清晰的数据转换器；若更好但未采用，记录原因和后续裁决点。
2. **判据是否真能区分对错？** 对每个阻断 gate同时检查正确样本和单缺陷注入，确认失败来自目标机制。
3. **有没有成熟第三方机制？** systemd socket／slice、SQLite backup API、Anthropic SDK、systemd-analyze和现有 observability优先于自制替代；但第三方机制的保证边界必须通过本项目真实接缝验证。

## 未采纳方案

- **直接停止 Bun后手工启动 Python `--port 4141`**：缺少稳定 listener owner、restart、cgroup和可审计回滚，不采用。
- **把 candidate system-level unit原样复制到 user manager**：字段、路径、target和权限模型不匹配，不采用。
- **认为 socket activation等于首次切换零停机**：与端口独占和已 accept连接事实冲突，不采用。
- **为备用验证重启 `cc-daemon`并修改其 endpoint**：违反禁触碰边界，不采用。
- **新旧服务共享同一 History DB做 shadow**：存在双 writer与 schema风险，不采用。
- **自动镜像全部生产生成请求**：可能重复工具副作用、approval、成本与数据写入，不采用。
- **切换成功后立即删除旧数据／二进制**：破坏回滚和审计，不采用。
- **用 helper单测、systemd unit静态检查或局部 bridge `PASS`代替完整替代验收**：证据层级不足，不采用。

## 下一最小动作

1. 不再回放foundations、systemd、S3或S4，也不重建对应开发线；保持三个systemd reviewed-source archive immutable。Current main精确为`c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`，但unit仍未安装，真实user manager／cgroup仍未验收。
2. S5／切片4下一最小环境固定为可销毁VM或container：先证明独立login session／user manager、delegated cgroup v2与private control socket，再对该fixture执行备用动态端口、隔离状态根、具名双fd／双栈、graceful timeout、真实readiness、declared／effective／runtime cgroup对账与自动清理。不得在当前`/init.scope`重跑同构fixture，不得退回宿主user manager。
3. 保留current真实Copilot app canary的readiness／纯文本non-stream／stream、forced ordinary tool roundtrip与单item reasoning carrier echo HTTP 200作为应用路径正控；不得把它写成真实manager／cgroup、完整P0或cutover证据。下一核心代码切片转向kernel partial-write；完整tool／reasoning矩阵仍按Acceptance逐项补齐。
4. P2保持未完成：继续逐项data disposition、inventory＝ledger资产集合、credential refresh、backup／restore与唯一writer门；本轮不裁决`PENDING_DECISION`，不迁移或删除数据。
5. P3保持`NO_CUTOVER`：旧Bun存在外部`--restart` wrapper，继续保留supervisor／listener／writer三道fence、配置化切换／回滚deadline、观察阈值与rollback dry-run。未验证wrapper精确停止／恢复原语和稳定窗前，不得只kill listener child或把一次`ss`空结果当作fence完成。
6. S7 rolling仍为后续独立切片；不得从单实例socket activation、真实Copilot app canary或未来S5通过推导为已支持。任何安装、manager持久状态变更、`4141`接管或cutover仍需独立前置门与用户当次明确授权。

## Kick-off 提示词

> 继续执行 `docs/agents/service-cutover/plan.md` 的下一未完成准备切片。先完整读取该living plan、current readiness、Anthropic Responses bridge的current frozen Spec／Acceptance与living Implementation、current inventory、systemd runtime living Plan及archive／worktree审计；每次shell都在同一调用内验证主树物理root、`main`与`HEAD == refs/heads/main`，并记录当次current HEAD。Current基线为`main@c1de6bf800a062f0dbcb4ef9db507fdc5f323b62`；foundations、systemd runtime、S3 graceful、S4 installer及后续bridge主路径已进入main，reviewed sources已归档，不得重复回放、重建开发线或把历史integration当作待办。真实Copilot app canary取得纯文本、forced ordinary tool roundtrip与单item reasoning carrier echo的scoped PASS，但这不是真实user manager／cgroup、完整Acceptance或cutover证据。S5本机private user-manager／cgroup诊断仍`BLOCKED`；下一最小环境是具备独立login session／user manager与delegated cgroup v2的可销毁VM或container。不得在当前`/init.scope`重跑同构fixture，不得退回宿主user manager，不得安装unit、改变真实manager状态或执行`daemon-reload`／enable／start／restart。生产双栈`localhost:4141`仍由旧Bun持有，且其外部`--restart` wrapper必须作为supervisor fence的一部分；不得只kill listener child或用一次`ss`空结果宣称fence完成。P2与P3均未完成，整体严格保持`NO_CUTOVER`；继续保留逐项data disposition、inventory＝ledger资产集合、credential refresh、backup／restore、唯一writer、supervisor／listener／writer三道fence、配置化切换／回滚deadline、观察阈值与rollback dry-run门。S7 rolling仍为后续独立切片。不得停止、重启、reload、修改或向`cc-daemon.service`／`cc-daemon-calib.service`及其进程发送信号，不得用宽匹配进程操作。任何后续真实probe、manager dry-run、安装、`4141`接管或cutover都需满足各自冻结前置门与当次明确授权，并在前后机械核对生产listener与`cc-daemon`身份不变。若发现会改变公开行为、地址族合同、数据迁移政策、可接受中断／恢复目标或首次切换可用性保证的硬分叉，列出选项、权衡和推荐交回主会话，不自行缩减范围或执行切换。

# 备用端口 smoke R2 后续可执行计划

## 状态与边界

- **文档状态**：`PLAN_ONLY`。本文只修订执行计划，不运行服务，不启动 fake，不占用端口，不发送 signal，不修改旧报告。
- **编制基线**：本文件在主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 上编制。源记录为 `docs/tmp/260807-backup-port-smoke-resume.md`，独立评审为 `docs/tmp/260807-resume-review-backup-port-smoke.md`。
- **旧记录不回写**：原 smoke 记录及其评审保持历史事实；本文是关闭评审两项 major 的 R2 计划，不把原记录改写成“当时已满足”。
- **执行时机**：只有 stream candidate 的已知缺陷完成修复、形成新的完整候选 commit，并经独立复评确认可进入备用端口验收后，才执行本文。修复前不得启动 app 或 fake，也不得用 current `main@b91e58a…` 的 fail-closed 结果冒充 stream candidate 通过。
- **执行树身份**：本次编制 shellgate 固定为 `main@b91e58a…`。未来实际 smoke 必须另行冻结“已修复 stream candidate”的绝对 worktree、完整 commit、candidate ref 与 clean code-tree；不能继续把 `b91e58a…` 当作待测实现。`b91e58a…` 只作为 current-layer 回归基线。
- **产品结论边界**：本文通过时只能得到“已修复 stream candidate 的备用端口验收入口通过”。完整 stream／bridge Acceptance、真实凭据、真实 upstream、systemd、部署与 cutover 继续保持 `UNVERIFIED`／`NO_CUTOVER`。

## 两项 major 的关闭合同

### M1：凭据与配置发现链完全隔离

被测对象不是“报告中没有打印 token”，而是“app 子进程不能从继承环境、嵌套 settings、显式 token file、默认 token file 或任一自动发现的 config.yaml 得到真实凭据”。以下条件全部是启动前硬门，任一不成立均不得 spawn app。

#### 1．父进程只做 presence 清点

控制进程只允许对以下入口记录 `present=true／false`，禁止读取、展开、hash、截断、打印或写入其 value：

- `COPILOT_API_GITHUB_TOKEN`。
- `GH_TOKEN`。
- `GITHUB_TOKEN`。
- `GHC_AUTH__GITHUB_TOKEN`。
- `GHC_AUTH__TOKEN_FILE`。
- `GHC_CONFIG`。

对文件入口同样只记录 presence，不读取内容：

- 候选启动 cwd 下的 `config.yaml`。
- 隔离 `XDG_CONFIG_HOME` 所对应的默认 `ghc-api-proxy/config.yaml`。
- 隔离 `XDG_DATA_HOME` 所对应的默认 `ghc-api-proxy/github_token`。
- 本轮显式配置指定的 `auth.token_file`。

presence 清点是审计事实，不是授权。父环境中即使存在某入口，也不得把它复制进 child env；日志中不得出现环境值、token 文件路径值或配置文件内容。

#### 2．子进程环境使用显式 allowlist

不得用 `os.environ.copy()` 后零散删除若干键。harness 从空字典构造 app 与 fake 的 child env，只加入运行所需的固定非秘密项，例如受控 `PATH`、locale、`HOME`、`XDG_CONFIG_HOME`、`XDG_DATA_HOME`、`TMPDIR`、Python 运行设置和明确的 loopback `NO_PROXY`。不得继承任意 `GHC_*`、三个通用 GitHub token 变量、`HTTP_PROXY`、`HTTPS_PROXY` 或 `ALL_PROXY`。

spawn 前对最终 child env 做机械断言：六个具名入口均 absent，且不存在任何未显式批准的 `GHC_*`。该断言检查键 presence，不读取值。断言失败时记录变量名与 `present=true`，不得打印 value，不得启动 app。

fake child 使用同样的最小环境原则。fake 不需要 GitHub／Copilot 凭据，也不得意外继承这些入口。

#### 3．配置加载只允许一个受控入口

harness 在一次性根中创建专用 run cwd、`XDG_CONFIG_HOME`、`XDG_DATA_HOME` 与显式 smoke config。app 必须从专用 run cwd 启动，并通过 CLI `--config <本轮显式配置>` 选择该配置；command construction gate 必须证明 `--config` 参数存在且指向本轮文件。不得依赖 `GHC_CONFIG`，不得从候选仓库 cwd 启动以碰运气绕过本地 `config.yaml`，不得依赖用户默认配置目录。

显式 smoke config 至少固定以下事实：

- `upstream.type=generic`，base URL 只指向本轮 loopback fake，API key 只使用本轮非真实占位值。
- `auth.github_token` 为空。
- `auth.token_file` 指向一次性根内一个已知不存在的专用路径；启动前以 presence 断言其不存在，不读取内容。
- `history.enabled=false`，History 路径若仍需出现则只能位于一次性根。
- `tokenization.state_path` 位于一次性根。
- `model_refresh_interval=0`，tracing 与 TUI disabled。

隔离 `XDG_CONFIG_HOME` 下默认 `config.yaml`、专用 run cwd 下 `config.yaml` 与隔离 `XDG_DATA_HOME` 下默认 token file 在启动前都必须 absent。由于显式 `--config` 已固定唯一配置入口，即使控制进程所在仓库或用户真实目录存在同名文件，也不得探测或读取其内容。

#### 4．spawn 前验证 effective settings

用与 app 相同的绝对 Python、相同 child env、相同专用 cwd 和相同显式 `--config` 语义执行无服务的 settings preflight。只输出布尔／枚举事实，不输出 secret 或路径内容：

- upstream 是否为 `generic`。
- upstream base URL 是否精确等于本轮 loopback fake endpoint。
- `auth.github_token` 是否 present，必须为 false。
- `auth.token_file` 是否 configured，必须为 true；对应文件是否 present，必须为 false。
- History 是否 enabled，必须为 false。
- tokenization path 是否位于一次性根，必须为 true。
- effective config 是否来自本轮显式配置，必须为 true。

preflight 不得调用 token provider，不得读取 token file，只解析 settings 并检查受控路径的 presence。任何布尔值不符合预期即 fail closed，不启动服务。

#### 5．M1 的正反控制

以下控制均在不启动 app 的 preflight 层执行：

- 分别把六个具名入口注入“最终 child env”后，child-env gate 必须逐项判红；只记录被注入键的 presence。
- 向最终 child env 注入任意未批准 `GHC_*` 后，allowlist gate 必须判红。
- 把显式 smoke config 的 `auth.github_token` 改为非空占位值后，effective-settings gate 必须判红；不得输出该值。
- 在显式 `auth.token_file` 创建任意非空占位文件后，file-presence gate 必须判红；不得读取文件内容。
- 构造缺少 `--config` 的 app argv 后，command construction gate 必须判红。
- 在专用 cwd、隔离默认 config 位置或隔离默认 token 位置放置占位文件后，对应 absence gate 必须判红且不得 spawn app。

只有正确样本全部为绿、每个单缺陷样本在目标 gate 变红且没有服务进程产生，M1 才算关闭。

### M2：冻结进程 incarnation，并完整 wait／reap

被测对象不是“某个 PID 仍存在”或“端口最后空闲”，而是每个角色在整个窗口内是否仍是同一个 OS process incarnation，以及所有自建 child 是否被父 harness 回收。

#### 1．统一 incarnation 记录

对旧 Bun、app 与 fake 都使用同一记录结构：

- PID。
- `/proc/<pid>/stat` 的 starttime，也就是 Linux proc stat 第 22 字段的原始 tick 值。
- `/proc/<pid>/cwd` 的解析结果。
- `/proc/<pid>/cgroup` 的完整规范化内容或稳定 digest。
- `/proc/<pid>/cmdline` 的 NUL 分隔 argv 规范化结果。
- listener 集合：address family、loopback address、port、socket inode，以及该 inode 是否能从 `/proc/<pid>/fd` 反查到同一 owner。

`pid` 与 `starttime` 共同定义最小 incarnation key；cwd、cgroup、cmdline 与 listener 是必须同时相符的角色证据。只比较 PID 不得判“未变化”。读取 `/proc/<pid>/stat` 时必须使用能正确越过括号包围 comm 的解析方式，再取字段 22；禁止对整行直接 naive split 后写死错误索引。

Linux 支持时，harness 在每个 child spawn 后立即持有 pidfd，并把 pidfd 与 child process handle、incarnation snapshot 绑定。无法取得 pidfd 时，本轮 smoke fail closed，不以模糊 PID 查找降级继续。

#### 2．旧 Bun 作为外部 incumbent

执行前从 `127.0.0.1:4141` 与 `[::1]:4141` 的实际 listener socket inode反查 owner，再冻结完整 incarnation。两个 listener 必须属于预期的同一个 Bun incarnation；否则 preflight 判红。

在 fake 启动前、app 启动后、每组关键 gate 后、清理前与最终收口时重取旧 Bun incarnation。以下任一变化均判 `SAFE-01` 红并标记为外部运行态变化：

- PID 变化。
- PID 相同但 starttime 变化，也就是 PID 被复用或旧 Bun 已重启。
- cwd、cgroup 或 cmdline 变化。
- 双栈 listener owner或 socket inode 集合变化。

旧 Bun 重启必须算变化，绝不能用“PID 看起来相同”放行。harness 永远不向旧 Bun发送 signal，也不尝试替用户恢复其运行态。

#### 3．app 与 fake 必须是 harness 的直接 child

harness 分别保存 app 与 fake 的 process handle、pidfd 与初始 incarnation，不通过进程名、命令行 substring 或端口搜索重新“认领”进程。启动成功必须同时满足：child 尚未退出、当前 incarnation 与初始 snapshot相同、预期 listener inode归属于该 child。

若 child 在 signal 前已退出，先通过原 process handle `wait()`并 reap，记录为提前退出；不得对已经变化或未知的新 owner发送 signal。若端口被其他 incarnation 占用，立即判红且不 signal owner。

#### 4．只允许精确终止自建 child

禁止 `pkill`、`killall`、按命令名／端口／正则匹配的 kill、裸“查到一个 PID 就 kill”，也禁止向旧 Bun发送任何 signal。

app 的正常关闭只通过其已绑定 pidfd发送一次 `SIGTERM`。发送前必须重新读取并比对 app 的完整 incarnation；pidfd与 snapshot不匹配、child已退出或无法证明 owner时，不发送 signal，转入 wait／诊断并判红。

fake 优先通过 harness 自带的精确控制通道请求关闭；若需 signal，只能使用 fake 自己的 pidfd。任一 child在 graceful deadline内未退出时，本轮判红；为防止本轮自建进程泄漏，只允许通过该 child既有 pidfd做精确升级，随后仍必须 `wait()`。任何升级都作为 cleanup failure记录，不能被“最终端口空闲”洗绿。

#### 5．两个 child 都必须 wait 并 reap

无论 happy path、gate failure、client cancel、startup failure还是 harness异常，清理都进入同一 `finally` owner。app 与 fake 分别在有界 deadline内通过原 process handle `wait()`，取得各自 return code并完成 reap。

最终成功条件必须同时成立：

- app 已 wait／reap，历史 app incarnation 的 `/proc` 项不存在。
- fake 已 wait／reap，历史 fake incarnation 的 `/proc` 项不存在。
- `4142` 与 `4143` 无任何 listener。
- app 日志按序出现完整 lifespan shutdown 事实；Uvicorn因重新 raise捕获的 `SIGTERM`而返回 `-15`可与干净 lifespan并存，不能单独判失败或单独判成功。
- fake 完成自己的关闭协议并 flush捕获证据。
- 一次性状态根只在两个 child均 reap、证据已封存后删除。
- 旧 Bun完整 incarnation 与双栈 listener snapshot仍与基线相同。

“listener消失”不能代替 wait／reap，“日志写了 shutdown”不能代替进程终态，“PID相同”不能代替旧 Bun incarnation相同。

#### 6．M2 的正反控制

- 伪造“PID相同但 starttime不同”的旧 Bun snapshot，identity comparator必须判红。
- 伪造 cwd、cgroup、cmdline或任一 listener inode变化，comparator必须逐项判红。
- 让 fake先关闭 listener再阻塞不退出，cleanup必须因 wait超时判红。
- 让 app在预定SIGTERM前提前退出，harness必须 wait／reap原child且不得向复用PID或新listener owner发送signal。
- 让一个 child退出但故意跳过wait，最终 reap gate必须判红。
- 正确样本必须证明两个 child都由原handle完成wait／reap，且旧 Bun完整incarnation保持不变。

## 实际执行顺序

### Phase 0：候选修复门

1. 取得 stream candidate 修复后的完整 commit、branch／ref、绝对 worktree与独立复评结论。
2. 确认该结论已关闭阻止备用端口 smoke 的候选缺陷；若仍有 blocker或相关 major，停止，不启动服务。
3. 冻结 current-layer 基线 `b91e58a…` 与 repaired candidate 的差异身份。后续所有命令都在自己的单次调用中打印并断言物理 cwd、Git top-level、完整 HEAD和目标ref；候选执行 gate不得误落到主树。
4. 记录 code-tree tracked cleanliness。并行文档 WIP不得被当作产品代码，也不得被覆盖。

### Phase 1：无进程 preflight

1. 创建一次性根、专用 run cwd、隔离HOME／XDG／TMPDIR、显式 smoke config及两个已确认空闲的备用端口计划。
2. 完成M1全部 presence inventory、child-env allowlist、唯一配置入口和effective-settings gate。
3. 完成M1单缺陷正反控制；任一控制不具判别力则停止。
4. 检查`4142`／`4143`当前无listener。若被占用，记录owner incarnation后停止；不signal、不抢占。
5. 冻结旧Bun双栈`4141`完整incarnation。身份不唯一或任一字段取证失败时停止。
6. 校验harness能为child取得pidfd、记录starttime并执行wait／reap。能力不足时停止，不降级成模糊kill。

### Phase 2：启动 fake 与 app

1. 先spawn fake，立即绑定process handle、pidfd与incarnation；等待`127.0.0.1:4143` listener，并用socket inode反证owner就是该incarnation。
2. 再spawn app，立即绑定process handle、pidfd与incarnation；等待`127.0.0.1:4142` listener，并用socket inode反证owner就是该incarnation。
3. 任一child提前退出、identity漂移、listener owner不符或旧Bun发生变化，立即进入统一cleanup，当前gate判红。
4. 服务运行期间继续只记录凭据入口presence与effective auth presence，不记录任何token或配置内容。

### Phase 3：执行保留的 STREAM-MERGE gates

以下ID、目标与红灯边界全部保留。它们只在stream candidate修复并通过Phase 0～2后执行。

| Gate | Required behavior | 失败判定 |
|---|---|---|
| STREAM-MERGE-00 回归 | 重跑原记录的RUN、NS与CLEAN层；non-stream仍只调用一次Responses，dual-capability `auto`仍保持Messages；清理采用本文M2强化合同 | 任一current已通过行为回归，或任一child未wait／reap，均红 |
| STREAM-MERGE-01 route接线 | `stream=true`从真实`/v1/messages`进入；实际向fake `/v1/responses`发送`stream=true`且恰好一次；不再返回`responses_stream_not_supported` | 仍typed reject、误走Messages、零调用或多调用均红 |
| STREAM-MERGE-02 wire protocol | Fake按Responses SSE发`response.output_item.added → delta／authoritative done → response.output_item.done → response.completed`；app下游只输出Anthropic SSE，不泄漏Responses event | Responses event或JSON直接透传、content type错误均红 |
| STREAM-MERGE-03 首block withholding | Fake发送item added与部分delta后暂停；真实raw HTTP reader在authoritative done前观察到零success headers、零`message_start`、零body bytes | 提前200、提前start或任意partial block bytes均红 |
| STREAM-MERGE-04 完整block batch | Done后首批包含同一串行提交中的`message_start → content_block_start → delta → content_block_stop`；index从0连续 | 缺事件、拆成可等待的半batch、index gap或block交错均红 |
| STREAM-MERGE-05 semantic order | Fake制造A先open、B后open但B先done；A完成前零下游block，A完成后按A、B提交 | 按完成顺序先发B、漏A／B或重复均红 |
| STREAM-MERGE-06 terminal | `response.completed`在无open block时产生唯一`message_delta → message_stop`；usage与同fixture non-stream归一值相等 | 重复terminal、open block时success terminal、usage漂移均红 |
| STREAM-MERGE-07 failure terminal | failed／error／无terminal EOF不得发`message_stop`冒充成功；commit前返回Anthropic HTTP error，commit后返回Anthropic SSE error并关闭 | 错误后success terminal、unknown item静默丢弃均红 |
| STREAM-MERGE-08 lifecycle owner | Route、parser、delivery、hooks、History、attempts与finalize共享同一`RequestContext`；真实exchange数等于attempt数 | 第二context、第二writer、第二finalizer或attempt错数均红 |
| STREAM-MERGE-09 cancel与cleanup | 分别在首block前与首block后断开客户端；上游关闭、不透明retry、未完成block不泄漏、资源归零、finalize一次；app与fake最终均wait／reap | orphan task／socket／child、重复prefix、completed History或漏reap均红 |
| STREAM-MERGE-10 shutdown | 只通过自建app的pidfd精确发送SIGTERM；完整block按grace合同drain或明确abort；History／tokenization／upstream cleanup完成；app与fake均wait／reap；备用listener释放；旧Bunincarnation不变 | 只因收到signal或端口消失就判通过不够；缺lifespan、reap、资源终态证据，或旧Bun重启／漂移均红 |

`STREAM-MERGE-03`必须使用真实raw socket或能独立区分“headers尚未提交”的HTTP客户端，不能用内部buffer长度或直接调用async generator代替。`STREAM-MERGE-04`～`06`必须由独立Anthropic SSE grammar consumer解析；官方SDK兼容可以作为第二oracle，但不得覆盖strict grammar红灯。

### Phase 4：stream gate 判别力控制

每个关键门使用相同真实route入口执行正确样本与单缺陷样本，至少保留以下控制：

- 删除`stream=true` Responses transport接线后，`STREAM-MERGE-01`必须红。
- 让route在done前写一个byte或提前response start，`STREAM-MERGE-03`必须红。
- 让sequencer在A未闭合时释放B，`STREAM-MERGE-05`必须红。
- failed后仍渲染success terminal，`STREAM-MERGE-07`必须红。
- 建立第二writer或第二finalizer，`STREAM-MERGE-08`必须红。
- 让fake关闭listener但保持进程存活，`STREAM-MERGE-09／10`的reap合同必须红。
- 让旧Bun snapshot保持PID但改变starttime，`STREAM-MERGE-10`必须红。

变异只能在隔离worktree或测试专用injector中执行，并用冻结exact patch恢复；不得在共享主树整文件恢复。每次控制都要核对失败来自目标机制，而不是旁路断言。

### Phase 5：统一清理与证据封存

1. 无论前述phase在哪一步失败，都进入同一finally cleanup；先停止新请求并封存fake捕获计数与stream事件证据。
2. 清理前重取旧Bun、app与fake完整incarnation。旧Bun只观察，不signal。
3. 通过app pidfd精确发送一次SIGTERM；通过fake控制通道或fake pidfd精确关闭fake。禁止任何模糊kill。
4. 分别对app与fake执行有界wait并reap；超时属于失败，即使之后精确升级并成功回收也不得改判为通过。
5. 复核两个历史child incarnation的`/proc`项消失、`4142／4143`无listener、旧Bun完整incarnation与双栈listener均未变化。
6. 只有两个child均reap且证据已封存后，才删除一次性根。删除前确认目标严格位于本轮一次性根，不使用不确定展开或通配符。

## 证据包与最终 verdict

每轮证据包必须包含：

- repaired candidate完整commit、ref、绝对worktree、tracked cleanliness及Spec／Acceptance内容身份。
- M1父环境与child env的入口presence矩阵、配置文件presence矩阵和effective-settings布尔事实；不得包含任何secret value或配置内容。
- 旧Bun、app与fake的完整incarnation前后snapshot，以及listener socket inode到owner的映射。
- app与fake的spawn、pidfd绑定、wait／reap、return code和cleanup deadline结果。
- `STREAM-MERGE-00`～`10`逐项结果、失败机制、fake exchange计数、raw HTTP／strict SSE oracle与目标正反控制结果。
- 一次性状态、listeners、lifespan、fake flush和旧Bun不变的最终收口证据。

只有M1、M2和`STREAM-MERGE-00`～`10`全部通过，才可报告`PASS_STREAM_CANDIDATE_BACKUP_PORT_ENTRY`。任一凭据／配置旁路、incarnation漂移、child漏wait／reap、模糊signal、stream gate红灯或正反控制失去判别力，都必须报告`FAIL`或`INCONCLUSIVE`，不得沿用原记录的`PASS_CURRENT_LAYER`。

## 当前结论

本文只形成后续可执行计划，当前没有执行任何服务或stream gate。执行门保持关闭，直到stream candidate修复并完成独立复评。原记录的current-layer事实仍只适用于`main@b91e58a…`；本文不改变旧报告，也不把未来候选状态提前写成已通过。

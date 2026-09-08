# 备用端口 smoke R3 后续可执行计划

## 状态与边界

- **文档状态**：`PLAN_ONLY／NOT_RUN`。本文只形成可执行实施与验收计划；本轮没有启动 app 或 fake，没有占用端口，没有读取凭据值，没有发送 signal，没有运行本文所列测试或 smoke，也没有修改旧报告。
- **编制基线**：本文在主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@b91e58a29324b11840002efc53ed6f869b800c39` 上编制。编制前已在同一 shellgate 中机械断言物理 cwd、Git top-level、branch、`HEAD` 与 `refs/heads/main`；项目没有 `docs/TRACKING.md`、`docs/ROADMAP.md` 或 `docs/BACKLOG.md` 这一类根级状态真相源。
- **输入文档**：R2 计划为 `docs/tmp/260807-resume-backup-port-smoke-r2.md`，R2 独立复评为 `docs/tmp/260807-resume-review-backup-port-smoke-r2.md`。原始执行记录 `docs/tmp/260807-backup-port-smoke-resume.md` 继续只承载当时的 current-layer 事实。
- **旧记录不回写**：R2 计划、R2 评审和原始 smoke 记录均保持历史原貌；本文是关闭 R2 评审两项 major 的新计划，不把旧 bytes 或旧 verdict 改写成“当时已满足”。
- **执行时机**：只有 Phase 0 绑定的同一完整 stream candidate 经独立代码复评明确得到 `0 blocker／0 major` 后，才允许进入无进程 preflight。任何 blocker 或任何 major 都必须停止；不得再由执行者判断某个 major“与本 smoke 不相关”。
- **执行树身份**：本次编制 shellgate 固定为 `main@b91e58a…`。未来实际 smoke 必须另行冻结已通过 Phase 0 的 stream candidate 绝对 worktree、完整 commit、candidate ref 与 clean code-tree；`b91e58a…` 只作为 current-layer 回归基线，不能冒充待测 stream candidate。
- **产品结论边界**：本文全部通过时只能得到“该完整 stream candidate 的备用端口验收入口通过”。完整 stream／bridge Acceptance、真实凭据、真实 upstream、systemd、部署与 cutover 继续保持 `UNVERIFIED／NO_CUTOVER`。

## R2 两项 major 的关闭摘要

| R2 finding | R3 硬合同 | 判红样本 |
|---|---|---|
| CLI `--github-token／-g` 可绕过 env／config 隔离，raw `/proc/<pid>/cmdline` 又可能把值写入证据 | app 与 fake 使用不可变 `LaunchSpec` 生成精确 argv；argv 必须与批准 schema 精确相等，拒绝 `--github-token`、`--github-token=…`、`-g`、attached short form及所有额外 override；preflight 与 spawn消费同一 `LaunchSpec`；所有 cmdline输出仅限 argv形状、敏感槽presence或hash-free redacted投影，永不输出原值或其hash | 分别注入long option、equals form、short option、attached short form及任一未批准option，必须在spawn前于目标argv gate判红，且日志／异常／证据中不存在注入值或其hash |
| Phase 0 只拒绝“相关 major”，可把完整candidate仍有的major主观排除 | 绑定同一完整candidate commit与当前完整bytes的独立代码复评必须明确给出`0 blocker／0 major`；局部报告、旧commit报告、拼接多个子范围报告或“相关major已关闭”均不能放行 | `0 blocker／1 major`、报告commit与candidate HEAD不一致、报告只覆盖若干known findings或报告后code-tree有产品改动时都必须停止，不创建临时根、不spawn任何child |

## 计划交付物与实施文件

实施者先核对 candidate 中是否已有等价 harness；若没有，按以下最小落点实现，不建立新的通用证明框架：

- `verification/backup_port_stream_smoke.py`：唯一 smoke owner；包含不可变 launch spec、无进程 preflight、process incarnation、listener ownership、fake控制、11个STREAM-MERGE gates、统一cleanup与脱敏证据输出。
- `tests/unit/test_backup_port_stream_smoke_safety.py`：先写失败测试，覆盖argv／credential／config旁路、cmdline脱敏、incarnation comparator、精确信号资格与wait／reap终态。
- `tests/smoke/test_anthropic_responses_stream_route.py` 或candidate内现有等价route smoke：承载真实route／ASGI／strict SSE的确定性fixture与injector；不得把纯helper单测冒充备用端口进程smoke。
- `docs/tmp/<run-id>-backup-port-stream-smoke-evidence.md`：实际执行后新建的单轮证据报告；只能写脱敏事实和verdict，不能覆盖本文或任何旧报告。

实现优先使用Python标准库的`subprocess.Popen`、`os.pidfd_open`、`signal.pidfd_send_signal`、`pathlib`与现有pytest框架。若candidate的最低Python或平台能力与这些API不符，Phase 1能力门直接fail closed并记录缺口，不降级成按进程名、端口或裸PID操作。

## M1：封闭凭据、配置与CLI发现链

### 1．父进程只做presence清点

控制进程只允许对以下入口记录`present=true／false`，禁止读取、展开、hash、截断、打印或写入其value：

- `COPILOT_API_GITHUB_TOKEN`。
- `GH_TOKEN`。
- `GITHUB_TOKEN`。
- `GHC_AUTH__GITHUB_TOKEN`。
- `GHC_AUTH__TOKEN_FILE`。
- `GHC_CONFIG`。

对文件入口同样只记录presence，不读取内容：

- candidate启动cwd下的`config.yaml`。
- 隔离`XDG_CONFIG_HOME`所对应的默认`ghc-api-proxy/config.yaml`。
- 隔离`XDG_DATA_HOME`所对应的默认`ghc-api-proxy/github_token`。
- 本轮显式配置指定的`auth.token_file`。

presence清点是审计事实，不是授权。父环境中即使存在某入口，也不得把它复制进child env；日志中不得出现环境值、token文件路径值或配置文件内容。

### 2．子进程环境使用显式allowlist

不得用`os.environ.copy()`后零散删除若干键。harness从空字典构造app与fake的child env，只加入运行所需的固定非秘密项，例如受控`PATH`、locale、`HOME`、`XDG_CONFIG_HOME`、`XDG_DATA_HOME`、`TMPDIR`、Python运行设置和明确的loopback `NO_PROXY`。不得继承任意`GHC_*`、三个通用GitHub token变量、`HTTP_PROXY`、`HTTPS_PROXY`或`ALL_PROXY`。

spawn前对最终child env做机械断言：六个具名入口均absent，且不存在任何未显式批准的`GHC_*`。该断言只检查键presence。断言失败时记录变量名与`present=true`，不得打印value，不得启动app或fake。

fake使用同样的最小环境原则。fake不需要GitHub／Copilot凭据，也不得意外继承这些入口。

### 3．app与fake argv使用精确schema

harness先构造不可变`LaunchSpec`，再由它生成最终argv tuple；禁止从环境、自由文本、shell字符串拼接或报告内容追加参数。app首版批准schema固定为以下语义槽：

1. candidate worktree内冻结的绝对Python解释器。
2. `-m app start`。
3. `--host 127.0.0.1`。
4. `--port <本轮app备用端口>`。
5. `--config <本轮显式smoke config绝对路径>`。

不得批准`--github-token／-g`、`--account-type`、`--ghc-api-base-url`、`--proxy`、`--fd`、`--generate-config`、`--manual`、`--verbose`、history／rate-limit开关或任何未列出的CLI override。需要改变已批准host、port或config时，只能重建并重新验证新的`LaunchSpec`，不能在已验证argv尾部追加token。

fake也必须有独立精确schema，只包含冻结解释器、冻结脚本入口和受控loopback端口／证据通道槽；不得有credential槽或任意passthrough argv。

command construction gate同时执行三类检查：

- 最终argv与`LaunchSpec.render_argv()`的规范tuple精确相等，包括顺序、重复项和路径规范化结果。
- option parser扫描long、`--name=value`、short与attached short形态；发现`--github-token`、`--github-token=…`、`-g`或`-g…`时，只输出`sensitive_slot_present=true`与槽类型，不输出相邻值、attached suffix或其hash。
- 任一未批准option、重复option、多余positional或`--`后的额外参数均判红；诊断只输出argv形状，例如`python -m app start --host <loopback> --port <port> --config <ephemeral-path> <rejected-option-present>`，不输出未知参数的value。

### 4．配置加载只允许一个受控入口

harness在一次性根中创建专用run cwd、`XDG_CONFIG_HOME`、`XDG_DATA_HOME`与显式smoke config。app必须从专用run cwd启动，并由唯一`LaunchSpec`提供`--config <本轮显式配置>`；不得依赖`GHC_CONFIG`，不得从candidate仓库cwd启动以碰运气绕过本地`config.yaml`，不得依赖用户默认配置目录。

显式smoke config至少固定以下事实：

- `upstream.type=generic`，base URL只指向本轮loopback fake，API key只使用本轮非真实占位值。
- `auth.github_token`为空。
- `auth.token_file`指向一次性根内一个已知不存在的专用路径；启动前只断言其presence为false，不读取内容。
- `history.enabled=false`，History路径若仍需出现则只能位于一次性根。
- `tokenization.state_path`位于一次性根。
- `model_refresh_interval=0`，tracing与TUI disabled。

隔离`XDG_CONFIG_HOME`下默认`config.yaml`、专用run cwd下`config.yaml`与隔离`XDG_DATA_HOME`下默认token file在启动前都必须absent。显式`--config`固定唯一配置入口后，也不得探测或读取控制进程所在仓库或用户真实目录里的同名文件内容。

### 5．preflight与spawn消费同一不可变输入

同一个已通过argv gate的`LaunchSpec`同时产生：

- settings preflight所用的绝对Python、cwd、child env、config path以及从批准CLI槽机械投影出的`host／port` overrides。
- 实际`Popen`的`executable／argv／cwd／env`。

两侧不得各自重建字典或再次解析自由文本。preflight输出`launch_spec_reused=true`以及字段级相等布尔值，不输出原始argv。spawn前再次断言当前render结果与preflight冻结tuple逐项相等；不一致即停止。

无服务settings preflight只解析settings并输出布尔／枚举事实：upstream是否为`generic`、base URL是否精确等于本轮loopback fake endpoint、`auth.github_token`是否present、`auth.token_file`是否configured、该文件是否present、History是否enabled、tokenization path是否位于一次性根、effective config是否来自本轮显式配置、effective host／port是否与`LaunchSpec`一致。preflight不得调用token provider，不得读取token file。任何事实不符合预期即fail closed。

### 6．所有proc cmdline记录必须hash-free脱敏

`/proc/<pid>/cmdline`只可在harness内存中按NUL边界读取，用于同一process incarnation的瞬时比较和脱敏投影；禁止把raw bytes、decoded原值、base64、截断值、稳定digest或任何hash写入stdout、stderr、异常、pytest failure、临时文件、证据报告或Git仓库。

可持久化的cmdline事实只有：

- argv槽数量与shape，例如`<python> -m app start --host <loopback> --port <port> --config <ephemeral-path>`。
- 已知敏感option槽是否present，值必须始终省略。
- 未批准option是否present。
- 同一PID＋starttime的raw cmdline与内存基线是否`equal=true／false`；比较完成后不保留raw snapshot于证据对象。
- hash-free redacted argv，其中解释器、脚本、路径、端口和所有未知value按槽类型替换为固定标签；不得用hash或digest代替被遮盖值。

旧Bun可能由本轮外部启动方式携带未知参数，因此它的持久化记录也只能使用同一shape／presence／hash-free redaction。若需要判断cmdline是否变化，只在同一harness进程内比较前后raw NUL tuple并输出`equal`布尔值；任何需要跨harness恢复raw comparator基线的方案不在本轮合同内，必须停止而不是落盘secret-bearing bytes。

### 7．M1的TDD正反控制

先写以下失败测试，再实现gate使其转绿：

- 分别把六个具名入口注入最终child env，child-env gate必须逐项判红；只记录键名与presence。
- 注入任意未批准`GHC_*`，allowlist gate必须判红。
- 把显式config的`auth.github_token`改为非空占位值，effective-settings gate必须判红且不输出值。
- 在显式`auth.token_file`、专用cwd默认config、隔离XDG默认config或默认token位置创建占位文件，对应presence gate必须判红且不得spawn。
- 分别注入`--github-token secret`、`--github-token=secret`、`-g secret`与`-gsecret`，argv gate必须判红；测试捕获所有输出、异常和证据序列化结果，断言既不含`secret`，也不含其任何预先计算hash。
- 注入任一未批准option、重复`--config`、多余positional或`--`尾参，argv gate必须判红。
- 让preflight与spawn持有不同`LaunchSpec`或让rendered argv在preflight后变化，identity gate必须判红。
- 正确样本必须在零child产生的preflight层全绿，并证明app／fake schema、settings与脱敏projection没有false-red。

只有正确样本全部为绿、每个单缺陷样本在目标gate变红、失败来自目标机制且没有服务进程产生，M1才算关闭。

## M2：冻结process incarnation并完整wait／reap

### 1．统一incarnation记录

对旧Bun、app与fake都使用同一记录结构：

- PID。
- `/proc/<pid>/stat`的starttime，即Linux proc stat第22字段原始tick值。
- `/proc/<pid>/cwd`解析结果；证据中受控一次性路径可按`<ephemeral-root>`脱敏。
- `/proc/<pid>/cgroup`的规范化内容；若其中出现不受控路径，只保留结构化、hash-free redacted投影。
- `/proc/<pid>/cmdline`的内存raw tuple相等布尔值与上一节允许的hash-free shape／presence投影，绝不记录原值或hash。
- listener集合：address family、loopback address、port、socket inode，以及该inode是否能从`/proc/<pid>/fd`反查到同一owner。

`pid`与`starttime`共同定义最小incarnation key；cwd、cgroup、cmdline相等结果与listener必须同时相符。只比较PID不得判“未变化”。读取`/proc/<pid>/stat`时必须正确越过括号包围的comm再取字段22，禁止对整行naive split后写死错误索引。

Linux支持时，harness在每个child spawn后立即持有pidfd，并把pidfd与child process handle、incarnation snapshot绑定。无法取得pidfd时本轮fail closed，不以模糊PID查找降级继续。

### 2．旧Bun作为外部incumbent

执行前从`127.0.0.1:4141`与`[::1]:4141`的实际listener socket inode反查owner，再冻结完整incarnation。两个listener必须属于预期的同一Bun incarnation，否则preflight判红。

在fake启动前、app启动后、每组关键gate后、清理前与最终收口时重取旧Bun incarnation。以下任一变化均判`SAFE-01`红并标记为外部运行态变化：

- PID变化。
- PID相同但starttime变化。
- cwd、cgroup或内存raw cmdline comparator为不相等。
- 双栈listener owner或socket inode集合变化。

旧Bun重启必须算变化。harness永远不向旧Bun发送signal，也不尝试替用户恢复其运行态。对旧Bun的cmdline证据同样只能输出shape、敏感槽presence、hash-free redaction与前后相等布尔值。

### 3．app与fake必须是harness直接child

harness分别保存app与fake的process handle、pidfd与初始incarnation，不通过进程名、命令行substring或端口搜索重新“认领”进程。启动成功必须同时满足child尚未退出、当前incarnation与初始snapshot相同、预期listener inode归属于该child。

若child在signal前已退出，先通过原process handle`wait()`并reap，记录为提前退出；不得对已经变化或未知的新owner发送signal。若端口被其他incarnation占用，立即判红且不signal owner。

### 4．只允许精确终止自建child

禁止`pkill`、`killall`、按命令名／端口／正则匹配的kill、裸“查到一个PID就kill”，也禁止向旧Bun发送任何signal。

app正常关闭只通过其已绑定pidfd发送一次`SIGTERM`。发送前必须重新读取并比对app完整incarnation；pidfd与snapshot不匹配、child已退出或无法证明owner时，不发送signal，转入wait／诊断并判红。

fake优先通过harness自带精确控制通道请求关闭；若需signal，只能使用fake自己的pidfd。任一child在graceful deadline内未退出时本轮判红；为防止本轮自建进程泄漏，只允许通过该child既有pidfd做精确升级，随后仍必须`wait()`。任何升级均作为cleanup failure记录，不能被“最终端口空闲”洗绿。

### 5．两个child都必须wait并reap

无论happy path、gate failure、client cancel、startup failure还是harness异常，清理都进入同一`finally` owner。app与fake分别在有界deadline内通过原process handle`wait()`，取得各自return code并完成reap。

最终成功条件必须同时成立：

- app已wait／reap，历史app incarnation的`/proc`项不存在。
- fake已wait／reap，历史fake incarnation的`/proc`项不存在。
- `4142`与`4143`无任何listener。
- app日志按序出现完整lifespan shutdown事实；Uvicorn因重新raise捕获的`SIGTERM`而返回`-15`可与干净lifespan并存，不能单独判失败或单独判成功。
- fake完成自己的关闭协议并flush捕获证据。
- 一次性状态根只在两个child均reap、证据已封存后删除。
- 旧Bun完整incarnation与双栈listener snapshot仍与基线相同。

“listener消失”不能代替wait／reap，“日志写了shutdown”不能代替进程终态，“PID相同”不能代替旧Bun incarnation相同。

### 6．M2的TDD正反控制

- 伪造“PID相同但starttime不同”的旧Bun snapshot，identity comparator必须判红。
- 伪造cwd、cgroup、内存raw cmdline不相等或任一listener inode变化，comparator必须逐项判红；诊断不得包含raw cmdline或hash。
- 让fake先关闭listener再阻塞不退出，cleanup必须因wait超时判红。
- 让app在预定SIGTERM前提前退出，harness必须wait／reap原child且不得向复用PID或新listener owner发送signal。
- 让一个child退出但故意跳过wait，最终reap gate必须判红。
- 正确样本必须证明两个child都由原handle完成wait／reap，且旧Bun完整incarnation保持不变。

## 分阶段实施与执行顺序

### 施工阶段 A：TDD 实现无进程安全核心

**目标**：只做代码与测试施工，不触碰运行态；先用失败测试固定 M1、M2 纯函数合同，再实现最小 harness core。施工完成后的全部 product code、tests、verification harness、dependency 与 runtime config bytes 共同构成 Phase 0 必须复评的完整 candidate。

**前置依赖**：已冻结拟施工的 stream candidate worktree；candidate 中没有等价工具，或已明确选定复用点。此阶段不得创建 smoke 临时根、不得启动 app／fake、不得占用端口、不得发送 signal。

**步骤与验收**：

1. 在 `tests/unit/test_backup_port_stream_smoke_safety.py` 先写 M1／M2 正反控制，确认目标缺陷样本在实现前确实失败，且失败来自缺失 gate 而非测试装配错误。
2. 实现不可变 `LaunchSpec`、env／argv schema gate、settings preflight projection、hash-free cmdline redactor、incarnation parser／comparator、listener owner 解析与 cleanup state reducer。
3. 运行定向单测使正确样本转绿、单缺陷样本在目标 gate 判红；再运行 candidate 既有 ruff、pyright 和相关测试。这些是施工反馈，不替代 Phase 0 独立代码复评。
4. 对日志、异常、pytest diff 和证据 JSON／Markdown renderer 做 secret canary 扫描，证明输入占位 secret 及其预计算 hash 均不会出现。
5. 形成包含 stream 实现、harness 与测试的最终完整 candidate commit；从此到 Phase 0 结论及后续 smoke 结束，不得再改 product code、tests、verification harness、dependency 或 runtime config。任何修改都使 Phase 0 结论失效并要求对新完整 HEAD 重评。

**风险与回滚**：风险是测试只验证自家 redactor round-trip 或用同一实现生成 oracle。回滚是保留失败 fixture，改用独立预期 shape 与 captured-output 检查；实现未稳定前不进入 Phase 0，更不进入任何 spawn 路径。

### Phase 0：完整candidate独立代码复评硬门

**目标**：在任何运行态动作前证明即将测试的完整stream candidate本身已取得独立代码复评`0 blocker／0 major`。

**前置依赖**：施工阶段 A 已形成包含 stream 实现、harness 与测试的最终完整 commit；评审者独立于该 candidate 实施者；candidate worktree 可只读检查。

**步骤与验收**：

1. 冻结candidate的绝对worktree、branch／ref、完整HEAD、base commit与code-tree tracked cleanliness；每次shell调用都在同一调用内打印并断言物理cwd、Git top-level、完整HEAD和目标ref。
2. 取得绑定该完整 HEAD 与当前完整 candidate bytes 的独立代码复评。报告范围必须明确是“同一完整 stream candidate”，覆盖全部实现 diff、harness／tests、既有 known findings、route／parser／delivery／History／cleanup／finalize 合并接缝，并明确给出总 verdict `0 blocker／0 major`。
3. 机械核对报告所列 candidate commit 等于待测 HEAD，且报告完成后 product code、tests、verification harness、dependency 与 runtime config 没有未评审改动。只有独立报告明确为 `0 blocker／0 major` 才可放行。
4. 以下均不得替代该硬门：只复评“相关major”、只关闭R2的两项计划major、多个局部报告相加、旧candidate hash的`0／0`、helper测试全绿、实施者自评或current main的`PASS_CURRENT_LAYER`。
5. 任一blocker或任一major、scope不完整、commit不一致、报告后bytes变化或cleanliness无法证明时立即停止。此时不得创建临时根、不得启动fake或app、不得占用端口。

**风险与回滚**：风险是把旧或局部review拼成完整放行。回滚是保持运行态零变化，修复candidate后对新完整HEAD重新独立复评；旧报告只保留为历史证据。

### Phase 1：无进程preflight

**目标**：在零child状态下关闭所有credential／config／CLI旁路并冻结外部incumbent。

**前置依赖**：Phase 0 明确通过；施工阶段 A 的正确样本与单缺陷样本均具判别力；candidate bytes 与 Phase 0 评审绑定时完全相同。

**步骤与验收**：

1. 创建一次性根、专用run cwd、隔离HOME／XDG／TMPDIR、显式smoke config以及app＝`127.0.0.1:4142`、fake＝`127.0.0.1:4143`的端口计划。
2. 完成父环境presence inventory、child-env allowlist、app／fake精确argv schema、唯一config入口、同一`LaunchSpec`复用与effective-settings gate。
3. 执行全部M1无进程正反控制；任一控制不具判别力、任何输出包含secret／hash或发生child spawn即停止。
4. 检查`4142／4143`无listener。若被占用，只记录owner的脱敏incarnation后停止；不signal、不抢占。
5. 从`4141`双栈listener冻结旧Bun完整incarnation；身份不唯一、cmdline无法安全脱敏或任一字段取证失败时停止。
6. 校验平台能为child取得pidfd、读取starttime、通过process handle执行wait／reap。能力不足时停止，不降级成模糊kill。

**风险与回滚**：风险是preflight误读用户文件或留下临时根。回滚只删除已机械证明位于本轮一次性根下、且尚无child持有的本轮文件；不得用通配符或不确定展开。

### Phase 2：启动fake与app

**目标**：只启动由harness直接拥有、身份可证明且不接触真实凭据的两个child。

**前置依赖**：Phase 1 全部为绿；旧 Bun 基线仍有效；candidate bytes 与 Phase 0 评审绑定时完全相同。

**步骤与验收**：

1. 先spawn fake，立即绑定process handle、pidfd与incarnation；等待`127.0.0.1:4143` listener，并以socket inode反证owner就是该incarnation。
2. 再以同一冻结`LaunchSpec` spawn app，立即绑定process handle、pidfd与incarnation；等待`127.0.0.1:4142` listener，并以socket inode反证owner就是该incarnation。
3. 任一child提前退出、identity漂移、listener owner不符、cmdline comparator不相等或旧Bun发生变化，立即进入统一cleanup，当前gate判红。
4. 服务运行期间继续只记录credential入口presence、effective auth presence和cmdline脱敏shape，不记录任何token、配置内容、raw argv或hash。

**风险与回滚**：风险是spawn后identity变化却仍按旧PID发信号。回滚只通过已绑定pidfd／process handle清理可证明为本轮child的incarnation；未知owner保持不动并报告失败。

### Phase 3：执行保留的STREAM-MERGE gates

以下 ID、目标与红灯边界全部保留。它们只能在同一完整 stream candidate 通过 Phase 0 且 Phase 1～2 全部为绿后执行。

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
| STREAM-MERGE-10 shutdown | 只通过自建app的pidfd精确发送SIGTERM；完整block按grace合同drain或明确abort；History／tokenization／upstream cleanup完成；app与fake均wait／reap；备用listener释放；旧Bun incarnation不变 | 只因收到signal或端口消失就判通过不够；缺lifespan、reap、资源终态证据，或旧Bun重启／漂移均红 |

`STREAM-MERGE-03`必须使用真实raw socket或能独立区分“headers尚未提交”的HTTP客户端，不能用内部buffer长度或直接调用async generator代替。`STREAM-MERGE-04`～`06`必须由独立Anthropic SSE grammar consumer解析；官方SDK兼容可以作为第二oracle，但不得覆盖strict grammar红灯。

**风险与回滚**：风险是某个 stream gate 失败后继续执行并污染后续证据。任一 gate 红灯立即停止新请求、封存当前证据并进入 Phase 5 统一 cleanup；不得重启旧 Bun、不得自动重跑洗绿。

### Phase 4：stream gate判别力控制

每个关键门使用同一真实route入口执行正确样本与单缺陷样本，至少保留以下控制：

- 删除`stream=true` Responses transport接线后，`STREAM-MERGE-01`必须红。
- 让route在done前写一个byte或提前response start，`STREAM-MERGE-03`必须红。
- 让sequencer在A未闭合时释放B，`STREAM-MERGE-05`必须红。
- failed后仍渲染success terminal，`STREAM-MERGE-07`必须红。
- 建立第二writer或第二finalizer，`STREAM-MERGE-08`必须红。
- 让fake关闭listener但保持进程存活，`STREAM-MERGE-09／10`的reap合同必须红。
- 让旧Bun snapshot保持PID但改变starttime，`STREAM-MERGE-10`必须红。
- 向app launch注入任一credential option或让cmdline证据renderer输出raw／hash，M1 gate必须在目标机制处红，且不得产生app child。

变异只能在隔离worktree或测试专用injector中执行，并用预先冻结的exact patch恢复；不得在共享主树整文件恢复。每次控制都要核对失败来自目标机制，而不是旁路断言。恢复后重新核对candidate完整HEAD、code-tree cleanliness和Phase 0独立review绑定；任何product bytes变化都使原Phase 0放行失效。

**风险与回滚**：风险是变异恢复覆盖真实实现或并行WIP。无法构造exact patch时改用隔离worktree；reverse-apply check失败或hunk重叠时停止，不自行强推恢复。

### Phase 5：统一清理与证据封存

1. 无论前述phase在哪一步失败，都进入同一`finally` cleanup；先停止新请求并封存fake捕获计数与stream事件证据。
2. 清理前重取旧Bun、app与fake完整incarnation。旧Bun只观察，不signal；所有cmdline记录继续遵守hash-free脱敏合同。
3. 通过app pidfd精确发送一次`SIGTERM`；通过fake控制通道或fake pidfd精确关闭fake。禁止任何模糊kill。
4. 分别对app与fake执行有界wait并reap；超时属于失败，即使之后精确升级并成功回收也不得改判为通过。
5. 复核两个历史child incarnation的`/proc`项消失、`4142／4143`无listener、旧Bun完整incarnation与双栈listener均未变化。
6. 只有两个child均reap且证据已封存后，才删除一次性根。删除前确认目标严格位于本轮一次性根，不使用不确定展开或通配符。

**风险与回滚**：cleanup本身失败时不得用更宽泛的process search扩大blast radius。保留脱敏诊断并报告`FAIL_CLEANUP`；只对仍由原pidfd证明为本轮child的进程做精确升级。

## 证据包与最终verdict

每轮证据包必须包含：

- 同一完整stream candidate的commit、ref、绝对worktree、base、tracked cleanliness、Spec／Acceptance内容身份，以及明确覆盖完整candidate的独立代码复评`0 blocker／0 major`；不得只写“相关major已关闭”。
- M1父环境与child env入口presence矩阵、配置文件presence矩阵、app／fake argv shape、敏感槽presence、未批准option presence、`LaunchSpec`复用布尔事实与effective-settings布尔事实；不得包含secret value、配置内容、raw cmdline或任何secret hash。
- 旧Bun、app与fake的incarnation前后snapshot；cmdline部分只保留shape／presence／hash-free redaction与同轮内存raw comparator的相等布尔值。
- listener socket inode到owner的映射，以及app与fake的spawn、pidfd绑定、wait／reap、return code和cleanup deadline结果。
- `STREAM-MERGE-00`～`10`逐项结果、失败机制、fake exchange计数、raw HTTP／strict SSE oracle与目标正反控制结果。
- 一次性状态、listeners、lifespan、fake flush和旧Bun不变的最终收口证据。

只有Phase 0、M1、M2和`STREAM-MERGE-00`～`10`全部通过，才可报告`PASS_STREAM_CANDIDATE_BACKUP_PORT_ENTRY`。任一candidate blocker／major、review scope或commit不匹配、credential／config／CLI旁路、raw或hashed cmdline泄露、incarnation漂移、child漏wait／reap、模糊signal、stream gate红灯或正反控制失去判别力，都必须报告`FAIL`或`INCONCLUSIVE`，不得沿用原记录的`PASS_CURRENT_LAYER`。

## 未采纳方案

| 方案 | 不采纳原因 |
|---|---|
| 在R2原文直接补两段 | 会改写历史计划bytes并让旧评审引用失真；用户明确要求新建R3且不改旧报告 |
| 只在argv中grep`--github-token` | 会漏`--github-token=…`、`-g`、attached short form、额外override与参数重排；也不能证明preflight和spawn使用同一输入 |
| 保存raw cmdline或secret hash以便跨运行比较 | raw值直接泄露，hash仍是敏感值的稳定派生物并违反hash-free要求；本轮只允许同一harness内存比较后输出相等布尔值 |
| 只在确认argv无credential后记录完整cmdline | 无法覆盖外部旧Bun或未来CLI变化，也会把证据安全依赖于同一执行者自判；统一脱敏边界更可机械审计 |
| Phase 0只关闭已知或“相关”major | 允许完整candidate在未知合并接缝仍有major时进入运行态验收，正是R2评审指出的放行缺口 |
| 用端口空闲或shutdown日志替代wait／reap | 残留进程、提前退出和PID复用都可假绿，不能证明本轮child已由父harness回收 |

## 结构怪味与本轮处置

| `file:line`／surface | 怪味类型 | 处置 |
|---|---|---|
| `src/app/cli.py:50-109` | Typer start options把credential、network与runtime overrides集中在同一入口，CLI override优先级高于YAML／env，smoke若只检查`--config`会留下旁路 | 本轮不改公共CLI；harness以精确argv schema封闭所有未批准override，并用同一`LaunchSpec`驱动preflight与spawn |
| `src/app/config/loader.py:59-100` | 显式config只封闭路径发现，不封闭后续env与CLI覆盖 | 保留最小child env、effective-settings preflight与精确argv三道独立门，不能把其中任一道删成“已有`--config`即可” |
| R2的raw cmdline证据合同 | 身份证据与secret最小披露冲突 | raw只在同轮内存比较，持久化只允许shape／presence／hash-free redaction与equal布尔值 |
| Phase 0旧“相关major”措辞 | 放行标准由执行者主观缩小scope | 改为同一完整candidate独立代码复评总verdict`0 blocker／0 major`，任何major均停止 |
| `verification/final_acceptance/probes/`现有process probes | 各probe已有`wait()`实践，但没有统一覆盖argv credential gate、proc脱敏、pidfd identity和fake双child回收 | 复用标准库与项目风格，不直接复制其较弱identity合同；只新增本smoke所需最小harness |

## 实施者kick-off

复制以下内容开启实施会话：

> 在 `/home/xp/src/ghc-api-proxy-py` 项目中实施 `docs/tmp/260807-resume-backup-port-smoke-r3.md`。先读取 R3 全文、`docs/tmp/260807-resume-review-backup-port-smoke-r2.md`、原始 smoke 记录、当前 Spec／Acceptance 以及 candidate 完整 diff。每次 shell 调用都在同一调用内打印并断言目标绝对 cwd、Git top-level、branch／ref 与完整 HEAD；主树 current-layer 基线是 `b91e58a29324b11840002efc53ed6f869b800c39`，实际待测树必须是独立复评绑定的同一完整 stream candidate。若 candidate 尚无 R3 harness，先执行施工阶段 A：按 TDD 写 argv／credential／config、hash-free proc cmdline、incarnation 与 wait／reap 失败测试，再实现最小 harness；该阶段不得启动服务。施工完成并形成包含 stream 实现、harness 与 tests 的最终完整 commit 后，执行 Phase 0 且不得跳过。只有该完整 candidate 的独立代码复评明确为 `0 blocker／0 major`，并且之后 product code、tests、verification harness、dependency 与 runtime config bytes 均未变化，才进入 Phase 1；任何 blocker 或任何 major 均停止，不得判断为“不相关”。app 与 fake 必须由不可变 `LaunchSpec` 生成精确 argv，拒绝 `--github-token／-g` 所有形态及任何未批准 override，preflight 与 spawn 消费同一 spec。任何 `/proc/<pid>/cmdline` 输出只允许 argv shape、敏感槽 presence、hash-free redacted 投影或同轮内存 raw 比较的 equal 布尔值，禁止 raw value、截断值、base64、digest 或 hash。保留全部 credential／config 旁路、PID＋starttime＋cwd＋cgroup＋cmdline equal＋listener incarnation、pidfd 精确信号、app 与 fake 原 handle 有界 wait／reap，以及 `STREAM-MERGE-00`～`10` 全部门。不得 signal 旧 Bun，不得用模糊 kill，不得覆盖旧报告。每阶段先跑定向测试，再跑 ruff、pyright 与相关回归；任一运行 gate 失败立即进入统一 cleanup 并保留脱敏证据。完成后另建单轮证据报告，不把入口 PASS 外推为完整产品、部署或 cutover PASS。

## 当前结论

本文只形成后续可执行计划，当前没有实施harness、没有运行测试、没有启动任何服务或stream gate。执行门保持关闭，直到同一完整stream candidate完成独立代码复评并明确得到`0 blocker／0 major`。原记录的current-layer事实仍只适用于`main@b91e58a…`；本文不改变R2计划、R2评审或任何旧报告，也不把未来candidate状态提前写成已通过。
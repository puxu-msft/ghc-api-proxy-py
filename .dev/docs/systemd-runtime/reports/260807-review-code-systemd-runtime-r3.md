# systemd cgroup runtime 定向复评 R3

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-systemd` 分支 `feat/systemd-cgroup-runtime`、HEAD `49fb1988621bba4356e7a5039a6994c2e6d19604` 相对 base `ed77c9d191df81c451c25161420515cca52ce6a4` 的最终合并态。定向复核 R2 的状态权限 major，以及 readiness、tokenization、EnvironmentFile 覆盖 minor；同时确认 R2 已关闭的 `Type=exec`、`KillMode=control-group`、fd 下界和真实 fd smoke 没有回归。未安装、启动、停止或 reload 任何 system unit，未操作生产 `4141` listener，也不把 rolling 作为本轮验收范围。
- **总体 verdict**：**可进入下一阶段**。R2 的 `1 major + 1 minor` 均已关闭；本轮未发现 blocker 或 major。发现 1 项不影响运行正确性与本轮回并的部署安全文档 minor。候选为 **`0 blocker／0 major`，明确可 squash**。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：1。
- **双视角覆盖证据——机械核对**：逐项对账 R2 报告、最终 service／socket／slice、CLI、部署 README、权限测试与运行态 smoke；从 `/v1/messages` 路由沿 production pipeline、response observer、tokenization revision、lifespan flush、History close 和 upstream close 复核真实调用链；读取本机 systemd 255 `systemd.exec(5)`，确认 `StateDirectoryMode=` 会调整状态目录本身、同 owner 的既有子文件不会递归改 mode，并确认 `EnvironmentFile=` 晚于 `Environment=`、同名变量以后者为准；运行原始模板 `systemd-analyze verify`，唯一诊断是安装前约定路径 `/opt/ghc-api-proxy/.venv/bin/python` 不存在；候选全仓 pytest、Ruff、Pyright 均以 0 退出，目标树加载 oracle 指向候选 `src/app/__init__.py`，验证后工作树保持 clean。
- **双视角覆盖证据——第一人称执行**：模拟管理员采用默认 `/var/lib/ghc-api-proxy`、从旧宽权限版本升级、通过 EnvironmentFile 覆盖状态路径、无可写 HOME、预连接 backlog、readiness、真实 Anthropic 请求、tokenization revision、History／tokenization 落盘和 SIGTERM 路径；运行真实 listener＋真实 CLI／Uvicorn＋受控 generic upstream 的 smoke，并连续复跑以排除明显时序偶然绿。另模拟日常仅重启 service、同时重启 socket、已 accept 长连接与尚未 accept 连接，确认文档没有把 socket backlog 误写成 rolling 或 accepted-connection migration。

## R2 发现关闭矩阵

| R2 发现 | R3 状态 | 最终证据与边界 |
|---|---|---|
| 默认 `UMask=0022`／`StateDirectoryMode=0755` 使 History 与 tokenization 状态可被同机其他用户读取 | **关闭** | `contrib/systemd/ghc-api-proxy.service:13-15` 使用 `StateDirectory=ghc-api-proxy`、`StateDirectoryMode=0700`、`UMask=0077`。`tests/smoke/test_systemd_units.py:142-208` 以 unit 声明的 mode／umask 驱动真实 `HistoryWriter` 与 `TokenizationStateStore`，断言状态目录 `0700`，数据库、WAL、SHM、tokenization 临时文件和最终文件均为 `0600`。部署文档 `docs/agents/deployment-systemd/README.md:42-52` 明确升级边界：umask 不会收紧既有文件，覆盖目录及既有资产须由管理员确认最小权限。 |
| smoke 只验证 readiness 503、只见 History，未驱动 tokenization revision，也未验证 EnvironmentFile 覆盖 | **关闭** | `tests/smoke/test_systemd_units.py:227-338` 先模拟 unit 默认状态变量，再以 EnvironmentFile 等价环境覆盖到第二个目录；受控 generic upstream 实际接收 `/v1/models` 与 `/v1/messages`，应用 readiness 返回 200，Anthropic 请求返回 200；response observer 从 usage 学习并标脏 tokenization revision，SIGTERM 后 lifespan flush，最终 History 与 tokenization 文件都只落在覆盖目录。systemd 255 手册独立确认 `EnvironmentFile=` 晚于 `Environment=`。 |
| R2 已关闭的 `Type=exec`、`KillMode=control-group`、fd 0 拒绝和 fd 3 接线 | **无回归** | `contrib/systemd/ghc-api-proxy.service:9,18,21-24` 保持 `Type=exec`、`--fd 3`、`SIGTERM`、`KillMode=control-group`、`TimeoutStopSec=330s` 和 slice；`src/app/cli.py:49-53,78-79,109-114` 保持 fd 下界 1、拒绝 fd 与 host／port 混用，并把 fd 传给 Uvicorn。定向 CLI 单测和全仓门通过。 |

## 事实性发现

[minor] `docs/agents/deployment-systemd/README.md:46` — 文档把机密 token 经 `EnvironmentFile=` 提供描述为可用方案，但 systemd 255 `systemd.exec(5)` 明确说明环境变量不适合传递 secrets，因为 unit 环境可能经 D-Bus IPC 暴露并传播到进程树，推荐 `LoadCredential=`／`LoadCredentialEncrypted=` 等 credentials 机制 — 当前模板仍要求文件仅服务账户可读，且该问题不影响 socket activation、状态权限、readiness、SIGTERM 或 cgroup 声明，因此不构成本轮 squash blocker；但这是适用于 system-level 部署的真实保密边界，不应只以文件 mode 表述为充分保护 — 将该句改为“兼容但不推荐”，优先文档化 systemd credentials 到应用可消费 token file 的路径；若当前应用尚不能直接消费 credentials，明确这是后续部署强化项并保留现有兼容路径。

未发现阻断性问题；未发现 major。候选明确可 squash。

## 已核对的实际保证

- **权限**：新建默认状态目录由 systemd 以 `0700` 管理；服务进程在 `UMask=0077` 下新建的 History DB、WAL／SHM、tokenization 临时与最终文件为 `0600`。升级时 `StateDirectoryMode=0700` 会收紧目录本身，但不会自动递归收紧 owner 已匹配目录内的既有文件；文档已要求管理员检查这些资产。
- **EnvironmentFile 覆盖**：service 中 `EnvironmentFile=` 位于默认 `Environment=` 之后，且 systemd 255 的环境编译顺序规定 `EnvironmentFile=` 同名变量胜出。应用的配置加载顺序为 defaults < YAML < environment < CLI；smoke 证明覆盖后的两类状态文件只写入覆盖目录。
- **readiness 与真实请求**：generic upstream 必须先成功刷新 `/v1/models`，bootstrap 才将 readiness 三项置真；smoke 随后从继承 fd 对 `/health/readiness` 得到 200，并通过生产 `/v1/messages` 路径向受控 upstream 发出真实 Anthropic 请求。
- **tokenization 与 History**：Anthropic 成功 response observer 根据 upstream usage 更新 calibration revision；SIGTERM 进入 FastAPI lifespan cleanup 后 flush tokenization、关闭 History 和 upstream clients。smoke 断言两类文件落盘，且默认目录未被误写。
- **fd 与 backlog**：父进程建立真实 listener 并在应用启动前建立连接，应用通过 fd 3 接管后从该 backlog 连接返回 liveness 200。这证明应用侧 inherited-fd 与预连接 backlog 接缝，不证明真实 systemd manager 的 fd metadata 或跨 service restart 的 listener identity。
- **SIGTERM**：smoke 向真实 Uvicorn 进程发送 SIGTERM，观察 lifespan cleanup 日志、进程退出和状态落盘；它证明应用侧 graceful cleanup 接缝，不证明 systemd manager 对 main＋child cgroup 的真实信号广播或超时 SIGKILL。
- **Type 与 cgroup 声明**：`Type=exec`、`KillMode=control-group`、slice 资源字段和 `TimeoutStopSec=330s` 的 unit 语义保持正确；仓库态没有安装 unit，因此不声称这些属性已在真实 cgroup 生效。
- **非 rolling 边界**：文档准确区分尚未 accept 的 backlog 连接与旧进程已 accept 的 HTTP／SSE／WebSocket。日常仅重启 service 时 socket 可继续持有 listener，但单 service 仍是 stop-old 后 start-new；本轮不要求、也未声称 rolling、双实例或已有连接迁移。

## 验证记录与证据边界

- `systemd-analyze verify` 对最终三个原始模板的唯一诊断是 `/opt/ghc-api-proxy/.venv/bin/python` 尚不存在，退出码因此为 1；没有 unit 语法、依赖、`StateDirectoryMode=`、`UMask=`、`Type=`、`KillMode=` 或 slice 字段诊断。安装后仍须在目标机复跑。
- 定向 `tests/smoke/test_systemd_units.py` 在候选加载 oracle 下以 0 退出；该 smoke 又连续稳定性复跑，所有轮次均以 0 退出。定向 `tests/unit/test_cli.py`、相关 Ruff 与 Pyright 均以 0 退出。
- 全仓 pytest、Ruff、Pyright 在 `feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 上均以 0 退出；Python import oracle 为 `/home/xp/src/ghc-api-proxy-py-systemd/src/app/__init__.py`。本轮不在报告中硬编码通过用例数，以避免把并行开发中的瞬时计数误写成稳定合同。
- 核心 smoke 没有在本轮通过源码变异做 positive control，因为复评边界要求目标树只读；因此“测试能针对每一种目标缺陷变红”没有被外推为已证事实。判别力由 R2 前后实现差异、真实 writer／listener／upstream／SIGTERM 路径、官方 systemd 语义和生产调用链检查交叉支撑。
- 未连接真实 systemd manager，未安装 unit，未制造 main＋child cgroup，未对 memory／CPU／tasks limits 施压，也未执行真实 service restart。因此这些项目仍属于后续受控部署验收，不能从仓库 smoke 外推。

## 主观建议

[建议] `docs/agents/deployment-systemd/README.md:46` — 将 secret 传递从普通环境文件逐步迁移到 systemd credentials — 预期减少 token 经 unit 环境、D-Bus 或进程树暴露的风险 — 推荐新增非阻断部署强化切片，先确认应用已有 `auth.token_file` 能否直接指向 credentials 路径，再提供 `LoadCredential=` 示例；保留 EnvironmentFile 仅作兼容路径并明确风险。

[建议] 后续隔离 systemd 环境 — 增加真实 manager 的 fd metadata、service restart listener identity 和 main＋child 信号测试 — 预期把当前“unit 语义＋应用侧 smoke”提升为实际 manager／cgroup 证据 — 使用备用 loopback 端口与临时 unit，不操作生产 `4141`；rolling 仍应作为独立后续切片，不反向扩大本轮 squash 门。

## 结构怪味扫描与处置

- `contrib/systemd/ghc-api-proxy.service:13-17` — **状态目录名与两条绝对路径重复表达** — 当前由静态配置测试、真实环境覆盖 smoke 和部署文档共同守护，本轮不改；后续可评估 systemd 提供的 `$STATE_DIRECTORY`，但必须先验证 unit 环境展开与项目最低 systemd 版本。
- `tests/smoke/test_systemd_units.py:227-338` — **EnvironmentFile 行为以等价环境合并模拟，而非真实 manager 解析** — 本轮用 systemd 255 官方环境编译顺序作为独立 oracle 补齐，真实 manager 仍留给后续隔离验收；不把模拟测试冒充安装态证据。
- `tests/smoke/test_systemd_units.py:142-208` — **测试在进程内设置 umask，未经过 systemd manager** — 被测对象明确是“unit 声明值作用到真实 writer 后的文件 mode”，不是 manager 是否施加 umask；真实 writer、DB／WAL／SHM 和原子临时文件均已覆盖，manager 施加仍在后续部署 gate。
- `contrib/systemd/ghc-api-proxy.service:18` 与单一 `.socket` — **裸 fd 3 顺序耦合** — 当前仅一个 activation socket，CLI 和真实 fd smoke 均闭合；增加第二 listener 前必须引入 `LISTEN_PID`／`LISTEN_FDS`／`LISTEN_FDNAMES` 数量与名称校验，本轮不提前扩大实现。
- 扫描范围还包括 service→socket／slice、Environment／EnvironmentFile→Pydantic settings、StateDirectory→History／tokenization、generic bootstrap→readiness、Anthropic response→calibration revision、SIGTERM→lifespan cleanup。除上述已处置项外，未发现新的重复实现、职责错位、抽象泄漏或不必要自研机制。

## 方案反思

1. **更好的内部替代方案**：当前 `StateDirectoryMode=0700`＋`UMask=0077` 是关闭 R2 数据暴露的正确最小共同层；仅在 writer 内逐文件 `chmod` 会漏掉 SQLite 辅助文件和未来写者。后续可用 `$STATE_DIRECTORY` 减少路径重复，并用现有 `auth.token_file` 承接 systemd credentials。
2. **判据判别力**：真实 writer、真实 inherited listener、受控 generic upstream、readiness 200、Anthropic request、覆盖目录落盘和 SIGTERM cleanup 能区分主要正确／错误状态；但未做目标源码变异，也未连接真实 manager，因此报告保留这两条限制，没有把仓库绿灯外推为完整安装态保证。
3. **成熟第三方方案**：无需新增 Python 包。systemd 原生 `StateDirectoryMode=`、`UMask=`、socket activation、credentials、`Type=exec`、`KillMode=control-group` 和 slice controls 已覆盖编排需求；Uvicorn 原生 fd API 继续承载应用侧入口。

## 结论

`feat/systemd-cgroup-runtime@49fb1988621bba4356e7a5039a6994c2e6d19604` 已关闭 R2 的权限 major 与 readiness／tokenization／EnvironmentFile 覆盖 minor，且保持 `Type=exec`、`KillMode=control-group`、fd 下界、fd 3 backlog 和 SIGTERM 应用侧合同。最终结论为 **`0 blocker／0 major`，明确可 squash**。新增的 EnvironmentFile secret 文档问题为非阻断 minor，可在后续部署强化中修正；真实 manager／cgroup、资源限制和 rolling 继续作为后续独立验收，不反向扩大本轮回并门。

# Service cutover readiness current 定向复评

- **评审范围**：current `docs/agents/service-cutover/readiness.md`，现场 SHA-256 `ca4462aa89cdf8c73842607fffa50294fe48dd71cf90fdf67ff0a91218f316aa`，固定主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮只复核 43 行矩阵、Implementation hash 去绑定、happy／usage／systemd 主树状态、route／block／retry 缺口、四个候选提交及其精确评审、unit 未安装边界，以及 `NO_CUTOVER`／`cc-daemon`／`localhost:4141` 不变量；不重审候选代码，不执行测试、安装、manager、service、socket、进程、网络、数据或 cutover 操作。
- **总体 verdict**：**可进入下一阶段。Current Readiness 可作为 living checkpoint。** 当前 bytes 未发现 blocker、major 或 minor；状态与证据边界一致。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **授权边界**：本 verdict 只放行 living 文档 checkpoint 与后续无副作用准备，不表示完整 bridge `PASS`、候选已合入、unit 已安装、真实 user manager／cgroup 已验收、生产 `4141` 可接管或 `cc-daemon` 可被操作。

## 双视角覆盖证据

### 机械核对视角

- 现场两次读取 bytes 相等，SHA-256 均为 `ca4462aa89cdf8c73842607fffa50294fe48dd71cf90fdf67ff0a91218f316aa`；物理 root、分支、`HEAD` 与 `refs/heads/main` 均固定为 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- 以 Python 分节解析得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43 行；该口径与文档自述一致。
- 按中文分句扫描所有含 `Implementation` 的分句，64 位 hash 命中为 0；文档只声明读取 current living Implementation，不再复制易漂移的 Implementation SHA-256。Spec、Acceptance 与 inventory 的独立内容身份仍被明确保留。
- Git 祖先门确认 foundations 三片、systemd runtime `cf53334…`、happy 四片与 usage `80bc8f2…` 均已进入 current main。四个后继候选对象均存在且均不是 current main 祖先。
- 逐份读取四个精确候选评审：route `f3a5a76…` 为 `0 blocker／0 major`、可 squash；block delivery `e3fceb1…` 为 `0 blocker／2 major／1 minor`、当前不可 squash；graceful `865a5b7…` 与 installer `e16c2a7…` 均为 `0 blocker／0 major／1 minor`、可 squash。Readiness 对四份 verdict 的转述、范围限制与是否已进入 main 完全一致。
- current main 的 systemd runtime 代码 checkpoint 已存在；当前 XDG user unit 目录与 `/etc/systemd/system` 下六个 canonical `ghc-api-proxy` service／socket／slice 路径均不存在。该检查只支持“没有 canonical 安装证据”，不外推为对任意自定义 manager load path 的穷尽证明；Readiness 本身也只写 unit 尚未安装并要求后续真实 manager smoke。

### 第一人称执行视角

- 从 P0 开始执行：happy pure-path 与 usage 虽已在 main，但 route 候选尚未合入，block 候选仍有两项 major，bridge-aware retry 也没有与 route／delivery 组成同一候选；执行者会停在 `FOUNDATIONS_ONLY／UNVERIFIED`，不会把局部绿灯拼成完整产品 `PASS`。
- 从 P1 开始执行：systemd runtime 已在 main，但 installer 与 graceful 仅是未合入候选，unit 尚未安装，双 fd／双栈、真实 manager／cgroup、activation 与 graceful smoke 均未闭合；执行者只能继续隔离准备，不能安装、enable、start 或占用生产端口。
- 从生产接管路径执行：P2 disposition 与 P3 supervisor／listener／writer fence、deadline、rollback、observation 仍未闭合；`localhost:4141` 行保持 `NO_CUTOVER`，实际切换仍要求全部技术门与用户对当次动作的明确授权。
- 从外部不变量路径执行：`cc-daemon.service` 与 `cc-daemon-calib.service` 仅允许前后只读比对，文档没有把 stop、restart、reload、endpoint 修改、signal 或 runtime 清理写成 next smoke；活会话经现有 `4141` 前门的状态也保持 `UNVERIFIED`，不会用破坏性动作补证据。

## 事实性发现

未发现问题。

## 已通过的定向轴

1. **43 行口径**：通过。P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43，容量／backpressure 行仍独立存在，没有被汇总状态吞并。
2. **Implementation hash 去绑定**：通过。Readiness 不复制 current living Implementation 的 SHA-256，避免 Implementation 更新使部署真相源静默陈旧；稳定 Spec／Acceptance 与 inventory 身份仍明确。
3. **主树与缺口分层**：通过。Happy／usage 已进入 `main@80bc8f2…`，但 route 未合入、block 有两项 major且不可 squash、retry 缺完整组合接缝；完整 P0 继续为 `UNVERIFIED`。
4. **Systemd 分层**：通过。Runtime checkpoint 已进入 main，但 installer／graceful 候选未合入，unit 未安装，真实 manager／cgroup 与双栈运行证据未取得。
5. **四候选状态**：通过。四个 commit、是否进入 main、blocker／major／minor 与 squash disposition 均与其精确评审一致，且局部 verdict 没有被外推。
6. **生产边界**：通过。整体持续为 `NO_CUTOVER／FOUNDATIONS_ONLY`；旧 Bun 仍是双栈 `4141` owner 的现场快照边界，`cc-daemon` 永远不进入操作范围，实际 cutover 仍需重新取证和用户逐次授权。

## Living checkpoint 边界

本轮 `0 blocker／0 major／0 minor` 明确允许将 current `readiness.md` 作为 **living checkpoint** 继续消费。Living 表示后续 main、候选、review、inventory、unit 或运行证据变化时仍须更新并重新绑定 current bytes；它不是文档封存，也不是产品、部署或 cutover 收口。

## 结构怪味扫描

- `readiness.md:6-9,40-43,51-60,147-151` — **同一主树／候选状态在页首、总览、矩阵与阻塞链重复** — current bytes 四处一致，且都保持“main primitives ≠ 完整产品”的分层；本轮无需修改，后续任一候选状态变化须原子同步这些复述。
- `readiness.md:41,71-77,149,158-159` — **systemd 代码、候选、安装态与真实运行态容易被压成单一‘已完成’状态** — current bytes 明确拆为 main checkpoint、未合入候选、未安装、未验收四层；本轮无需修改。

## 主观建议

无。Current Readiness 已保留所有后续正确性、运行态、数据、回滚与授权门，本轮不扩大范围。

## 结论

**0 blocker／0 major／0 minor；可作为 living checkpoint。** 该结论不授权安装 unit、改变 manager／service／socket 状态、操作 `localhost:4141`、迁移／删除数据或触碰 `cc-daemon`。

# Service cutover readiness current 独立复评 R2

- **评审范围**：current `docs/agents/service-cutover/readiness.md`，连续两次读取 SHA-256 均为 `3950eea67e3e7074b7d23d78ebca8ac7fcbd9ec8b4e195f1ac3b80174f0e5802`，并以 Python `hashlib.sha256` 交叉复核；固定主树 `/home/xp/src/ghc-api-proxy-py` 的 `main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。本轮核对 43 行矩阵、Implementation hash 去绑定、route `44808b7…`、block `e506bf8…`、semantic `f5bca39…`、systemd-next `0a93e7f…`、`NO_CUTOVER／FOUNDATIONS_ONLY`、旧 Bun 双栈 `4141` owner、`cc-daemon` 只读边界与 canonical systemd unit 未安装状态；不重审候选代码，不执行测试、安装、manager、service、socket、进程、网络、数据或 cutover 操作。
- **总体 verdict**：**修复 major 后可进入。** 43 行、Implementation hash 去绑定、route／block／systemd-next、旧 Bun／`4141`、`cc-daemon`、unit 未安装及 `NO_CUTOVER／FOUNDATIONS_ONLY` 均准确；但 semantic exact successor `f5bca39ac582911b61d278fd678ec9298ad0c08e` 已取得代码复评 `0 blocker／0 major／0 minor`、明确可 squash及独立验收 `PASS`，文档仍写“修复进行中／尚无可 squash current verdict／完成修复并复评”，因此 current bytes 不能取得 0 major living checkpoint。
- **blocker 数**：0。
- **major 数**：1。
- **minor 数**：0。
- **checkpoint 边界**：当前**不可 checkpoint**。同步 semantic current `0 blocker／0 major`、`PASS`、可 squash状态与下一动作后，若定向复评达到 **0 blocker／0 major**，Readiness 可作为 living checkpoint 继续消费；这不表示文档封存、完整 bridge `PASS`、候选已合入、unit 已安装、真实 user manager／cgroup 已验收、生产 `4141` 可接管或 `cc-daemon` 可被操作。

## 双视角覆盖证据

### 机械核对视角

- 固定物理 root、`main` 分支、`HEAD == refs/heads/main == 80bc8f252b46c511f428af1d97159a5980ee9dc9`；连续两次读取 Readiness 得到相同 SHA-256 `3950eea67e3e7074b7d23d78ebca8ac7fcbd9ec8b4e195f1ac3b80174f0e5802`，另以 Python `hashlib.sha256` 得到同值。
- 以 Markdown 表格结构解析得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43 行；先前把 `Readiness／liveness语义` 误当表头的 42 行查询，以及把表头计入数据的 48 行查询均明确作废，未用于结论。
- 按中文分句扫描全部含 `Implementation` 的分句，64 位 hash 命中为 0；Readiness 仅按读取时 current living 内容消费 Implementation，稳定 Spec／Acceptance 与 inventory 身份仍独立保留。
- Git refs 精确为 route `44808b7d0be84a0c1eb5c58294726c620d4280cd`、block `e506bf87318424e4075b6422772ee0c7e9b8694a`、semantic `f5bca39ac582911b61d278fd678ec9298ad0c08e`、systemd-next `0a93e7f18f197bf8a2395eaaf20afda446f92d6b`；四者均不是 current main 祖先。Route 精确 R2 为 0 blocker／0 major／0 minor并可 squash；block 精确 R2 为 0 blocker／0 major／0 minor并可 squash；systemd-next merged-state review 为 0 blocker／0 major／1 个已裁决 non-blocking minor，独立验收 `PASS`，可按两提交顺序回放。
- Semantic exact successor 已有 `docs/tmp/260807-review-code-semantic-parity-r2.md` 与 `docs/tmp/260807-verify-semantic-parity-r2.md`：前者绑定 `f5bca39…` 并给出 `0 blocker／0 major／0 minor`、明确可 squash；后者绑定同一 HEAD 并给出独立 `PASS`。旧 HEAD `1cde3d58…` 的 verdict不被沿用；current verdict来自 successor 自己的复评与复验。
- 只读运行态显示 `127.0.0.1:4141` 与 `[::1]:4141` 均由 PID `1814328` 的 Bun `start --restart` 进程持有，cgroup 为 `/init.scope`。`cc-daemon.service` 与 `cc-daemon-calib.service` 均为 loaded／active／running，分别位于独立 user service cgroup；本轮未对其执行任何修改动作。
- `$HOME/.config/systemd/user` 与 `/etc/systemd/system` 下六个 canonical `ghc-api-proxy.service`／`.socket`／`.slice` 路径均不存在。该证据只支持“没有 canonical 安装证据”，不穷尽任意自定义 manager load path；Readiness 同样只声明 unit 尚未安装并保留真实 manager smoke。

### 第一人称执行视角

- 从 P0 route／block 路径执行：两条 exact successor 均有 0 major 局部 verdict但未进入 main，完整 stream、retry、transport 与 quota 仍未组成同一候选；执行者会保持 `FOUNDATIONS_ONLY／UNVERIFIED`，不会把局部绿灯外推为完整产品 `PASS`。
- 从 semantic 路径执行：Git ref 已从旧 reviewed HEAD `1cde3d58…` 前进到 `f5bca39…`，且 exact successor 已取得 current 0 major code review、明确可 squash及独立 `PASS`；但文档仍要求“完成 semantic 修复并复评”，且未给出 exact successor。执行者可能重复实现／复评，继续修改错误节点，或误把旧 HEAD 的 major／FAIL 外推到新 HEAD；正确下一动作应是消费 `f5bca39…` 的 current verdict，并把 semantic与route／block一起推进到回放及组合候选阶段。
- 从 P1 执行：systemd runtime 已在 main，systemd-next exact integration 已获 merged-state 0 major与独立 `PASS`但尚未回放；canonical unit 未安装，真实 manager／cgroup、双 fd／双栈、activation 与 graceful smoke未闭合，因此只能继续无副作用准备，不能安装、enable、start或占用生产端口。
- 从生产接管路径执行：P2 disposition 与 P3 supervisor／listener／writer fence、deadline、rollback、observation仍未闭合；旧 Bun继续持有双栈 `4141`，整体保持 `NO_CUTOVER／FOUNDATIONS_ONLY`，实际切换仍要求全部技术门与用户对当次动作的明确授权。
- 从外部不变量路径执行：`cc-daemon.service` 与 `cc-daemon-calib.service` 只允许前后只读比对，文档没有把 stop、restart、reload、endpoint 修改、signal或runtime清理写成 next smoke；该边界可按文档安全执行。

## 事实性发现

[major] `docs/agents/service-cutover/readiness.md:6,9,40,53,122,147` — semantic current identity 与执行节点落后于 Git ref — `fix/responses-semantic-parity` 已形成 successor `f5bca39ac582911b61d278fd678ec9298ad0c08e`，其 parent 为旧 reviewed HEAD `1cde3d58338eeefb3cf8040f970c3612d451668b`；该 exact successor 已由 `260807-review-code-semantic-parity-r2.md` 取得 `0 blocker／0 major／0 minor`、明确可 squash，并由 `260807-verify-semantic-parity-r2.md` 取得独立 `PASS`。文档却仍统一写“semantic 修复进行中”“尚未取得可 squash 的 current verdict”“完成 semantic 修复并复评”，没有记录 exact successor 或消费其 current verdict。按现文执行会重复已完成的实现／评审阶段，并继续把旧 HEAD 状态当成当前状态；这与 living readiness 真相源要求绑定 current candidate及最新证据的职责不符 — **修复建议**：在页首输入身份、总览、stream行、独立评审行、阻塞链与结构怪味中统一写明 `fix/responses-semantic-parity@f5bca39ac582911b61d278fd678ec9298ad0c08e` 已取得 `0 blocker／0 major／0 minor`、可 squash与独立 `PASS`，但尚未进入 main且不得外推为完整 stream或产品 `PASS`；把下一动作推进为与route `44808b7…`、block `e506bf8…` 一起回放，并和stream wiring及retry组成同一完整候选。

除上述 major 外，未发现 blocker、minor或其他事实性问题。

## 已通过的定向轴

1. **稳定身份**：通过。Readiness 两次 SHA-256 一致，并经不同实现交叉复核。
2. **43 行口径**：通过。P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43。
3. **Implementation hash 去绑定**：通过。没有把易变 Implementation SHA-256复制进 Readiness。
4. **Route／block 状态**：通过。`44808b7…` 与 `e506bf8…` 均精确记录局部 0 major、可 squash、未进入 main及不得外推边界。
5. **Systemd-next 状态**：通过。`0a93e7f…` 精确记录 merged-state 0 major、独立 `PASS`、可回放但尚未回放；unit 未安装、真实 manager／cgroup 未验收。
6. **生产与外部边界**：通过。整体持续为 `NO_CUTOVER／FOUNDATIONS_ONLY`；旧 Bun仍为双栈 `4141` owner；`cc-daemon` 只读且不进入操作范围。

## 结构怪味扫描

- `readiness.md:6,9,40,51-55,122,147,157` — **同一候选状态在页首、总览、矩阵、授权行、阻塞链与怪味表重复** — route／block／systemd-next 当前一致，semantic 已在全部复述点同时陈旧；本轮 major要求原子同步这些位置，避免只修一处后继续漂移。
- `readiness.md:41,71-77,149,158-159` — **systemd 代码、integration、安装态与真实运行态容易被压成单一“已完成”状态** — current bytes 明确拆为 main checkpoint、未回放 integration、未安装、未验收四层；本轮无需修改。

## 主观建议

无。除 semantic current identity 外，Readiness 已保留完整正确性、运行态、数据、回滚与授权门。

## 结论

**0 blocker／1 major／0 minor；当前不可作为 0 major living checkpoint。** 同步 semantic exact successor、current 0 major／`PASS`／可 squash状态与 next action 后重新定向复评；若达到 **0 blocker／0 major**，可明确“Readiness 可 checkpoint并继续 living 更新”，但不得解释为产品、安装、部署或 cutover 收口。

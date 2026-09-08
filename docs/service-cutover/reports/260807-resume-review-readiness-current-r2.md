# Readiness current 独立定向复评 R2

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 working-tree `docs/agents/service-cutover/readiness.md`，精确 SHA-256 `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8`；固定 `main@b91e58a29324b11840002efc53ed6f869b800c39`。定向核对五张 readiness 表共 43 行、stream candidate `2087f8f02516136314985f5c48bdee20b2f4b861` 的 `0 blocker／8 major` 且未 main、systemd rebuild `d3fabfadfba57af6c2d63e543e3198444777df54` 的 `0 blocker／0 major` 与独立验收 `PASS` 且未 main、备用端口 `4142` current layer `PASS_CURRENT_LAYER`、旧 Bun 双栈 `4141`、整体 `NO_CUTOVER／FOUNDATIONS_ONLY` 及 `cc-daemon` 禁触碰边界。不重新评审候选代码，不执行测试、服务请求、进程信号、unit／manager 操作、端口接管、数据动作、Git ref／index 变更或 cutover；唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。0 blocker／0 major，当前 exact bytes 可以 checkpoint。** 文档已经关闭上一轮两个 current-state major，并准确把局部候选／局部 PASS 与同一 merged candidate、真实 manager／cgroup、完整 P0～P3 及生产切换授权分开。
- **blocker 数**：0。
- **major 数**：0。
- **双视角覆盖证据——机械核对**：每个 load-bearing shell 都在同一调用内验证物理 root、Git top-level、`main`、`HEAD == refs/heads/main == b91e58a…`。目标 SHA-256 由 `sha256sum` 与 Python `hashlib.sha256` 两种实现交叉一致。被测行边界先声明为 P0、P1、P2、P3 与 `cc-daemon` 五张表的 data rows；Python Markdown 表解析与独立 `awk` 状态机均得到 `10＋8＋11＋12＋2＝43`。Git ref、parent 与 ancestry gate确认 stream `2087f8f…` 的 parent 为 `b91e58a…` 且未 main；其独立代码评审原文为 `0 blocker／8 major`、不可 squash。Systemd 图确认为 `b91e58a… → 8cae6c2… → d3fabfa…` 且 tip 未 main；独立代码评审原文为 `0 blocker／0 major`，独立验收原文为 `PASS`，均明确不覆盖安装、真实 manager／cgroup、部署或 cutover。备用端口执行记录只对 `main@b91e58a…` 给出 `PASS_CURRENT_LAYER`，同时保留完整 stream／bridge `UNVERIFIED` 与部署 `NO_CUTOVER`。只读 `ss` 与 `/proc` 交叉确认 Bun PID `1623` 当前持有 `127.0.0.1:4141` 与 `[::1]:4141`，cwd 为 `/home/xp/src/copilot-api-js`、cgroup 为 `0::/init.scope`，`4142／4143` 无 listener。
- **双视角覆盖证据——第一人称执行**：作为 stream 实施者，从 P0 表会继续修复 `2087f8f…` 的八项 major并复评，而不会重复建立候选或把 happy-path scoped verification当完整 stream `PASS`；作为 systemd 回放者，会保持 `8cae6c2… → d3fabfa…` exact identity，逐片经过 main-side gate，而不会再次重建或把 code-only `PASS` 当真实 manager运行态；作为备用端口操作者，只能把 `4142` 的 current layer证据用于当前 main，并须等待两项 non-stream修复与 stream候选形成同一组合后重跑；作为 cutover操作者，会被同一候选原则、P0～P3未闭合、`NO_CUTOVER` 与当次明确授权门阻止接管 `4141`；任何 smoke、rollback或观察路径都只允许读取并比较 `cc-daemon` 身份，全文没有把停止、重启、reload、signal、改 endpoint／环境或清理其 runtime列为合法动作。

## 事实性发现

未发现问题。

上一轮 `docs/tmp/260807-resume-review-readiness-current.md` 的两项 major均已关闭：current 文档已记录 stream exact candidate及其八项 major，下一动作是修复／复评而非重新建线；也已记录 new-main systemd exact chain、两份独立 `PASS` 与未 main边界，下一动作是保持身份、进入 main后执行隔离真实 manager门，而非重复重建。

## 主观建议

未提出额外建议。本轮没有以“减少重复状态”为由删减 living readiness 的多入口摘要；这些复述确有漂移风险，但 current 文档已通过 exact hash复评、更新协议、结构怪味登记与新 bytes重新复评要求建立控制。后续仍应在任一 candidate、配置、unit、inventory或数据 owner变化后同步所有复述点。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `readiness.md:6-10,36-43,145-150,178` | Current state 在文档状态、总览、阻塞链与最终结论多处复述，living 更新时存在局部漂移风险 | **本轮不改。** 多入口摘要分别服务快速判读、逐域执行与收口边界；current bytes已互相一致。继续用 exact hash定向复评和“新 bytes旧 verdict失效”规则约束，不因去重而削弱 `NO_CUTOVER`／未 main边界。 |
| `readiness.md:53-54,72-78` | Stream、non-stream与systemd分别位于独立开发线，局部绿灯容易被拼成完整候选 | **本轮已由文档正确处置。** 同一候选原则、各行状态与 Next smoke均要求组合后重验；保持 `FOUNDATIONS_ONLY`／`UNVERIFIED`，不得外推为完整产品或运行态 `PASS`。 |

## 结论

**0 blocker／0 major；精确绑定 `main@b91e58a29324b11840002efc53ed6f869b800c39` 与 Readiness SHA-256 `c1e8494e2c6c58ff19a3125977d2744623157b3e6a4c72597e9c45f521c5b2e8`，可以 checkpoint。** 该 checkpoint只放行 living文档继续作为 current readiness真相源，不表示 stream八项 major已修复、systemd候选已进入 main、完整 P0／P1／P2／P3 已 `PASS`、unit已安装、真实 manager／cgroup已验证、生产 `localhost:4141`可接管或 `cc-daemon`可被操作。整体继续为 **`NO_CUTOVER／FOUNDATIONS_ONLY`**。

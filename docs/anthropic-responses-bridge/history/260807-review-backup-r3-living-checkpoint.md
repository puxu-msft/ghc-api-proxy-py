# Backup R3 living checkpoint 联合定向复评

- **评审范围**：主树 `/home/xp/src/ghc-api-proxy-py` 的 current `docs/agents/anthropic-responses-bridge/implementation.md` 与 `docs/agents/service-cutover/readiness.md`，精确 SHA-256 分别为 `0787aa198aa6963037759e9711531eba2b2ead31cad281ebc0fc37985b1701c7` 与 `dc94f7afabbd0b07a38d7a6fa054ade703e4e52feb3dd1c58ebc81b7dfbc19dc`；固定 `main@d903d726baf3f15bf46ddf17384564fee154ed6a`。本轮只核对 backup R3 scoped PASS、stream History request facts 定向缺口关闭、retry／quota／partial-write 与 manager／cutover 未验证边界、下一最小代码切片可继续、`LIVING／UNVERIFIED／NO_CUTOVER` 及 Readiness 43 行口径；不重审产品代码，不重跑服务、smoke、测试、manager、端口、进程、部署或 cutover。唯一仓库写入为本报告。
- **总体 verdict**：**可进入下一阶段。两份 current living 文档为 0 blocker／0 major，可形成 living checkpoint，并可继续下一最小代码切片。** 该 checkpoint 只冻结本轮 current bytes 与状态边界，不表示 Implementation 收口、完整产品或 Acceptance `PASS`、真实 systemd manager 已验证、unit 已部署或 cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。

## 双视角覆盖证据

### 机械核对

- 每次承载结论的 shell 调用均在同一调用内断言物理 cwd、Git top-level、branch、`HEAD == refs/heads/main`；结果固定为 `/home/xp/src/ghc-api-proxy-py`、`main` 与 `d903d726baf3f15bf46ddf17384564fee154ed6a`。
- 使用 `sha256sum` 与 Python `hashlib.sha256` 交叉复核两份目标文档；Implementation 为 `0787aa198aa6963037759e9711531eba2b2ead31cad281ebc0fc37985b1701c7`，Readiness 为 `dc94f7afabbd0b07a38d7a6fa054ade703e4e52feb3dd1c58ebc81b7dfbc19dc`，均精确匹配派活身份。
- 对账 `docs/tmp/260807-final-backup-port-smoke-r3.md:3-8,14-25,66-78` 与 `docs/tmp/260807-review-final-backup-port-smoke-r3.md:5-8,30-34`：`main@d903d72…` 的 verdict 为 `PASS_KEY_BACKUP_PORT_SMOKE_R3`，真实 History API 观察关闭 stream final attempt 的 request conversion fact 缺口；独立快速复核为 0 blocker／0 major／1 minor。其唯一 raw cmdline 措辞 minor 不改变 scoped PASS、facts 观察、零 signal、wait／reap或未验证边界，也未被两份 living 文档误写成产品级 `PASS`。
- 对账 Implementation `:13-17,54-55,91-93,257-259,290` 与 Readiness `:5-8,42-45,53-62,147-154,180`：两文档一致记录 R3 scoped PASS 与 facts 缺口关闭，同时继续把 retry、request／global quota、resident backpressure、真实 socket partial-write／delivery uncertainty、真实 credential、真实 systemd manager和 cutover保留为未验证或阻塞边界。
- Readiness 行数以 Python 分节解析与独立 `awk` 状态机两种方法交叉验证，均得到 P0 10＋P1 8＋P2 11＋P3 12＋`cc-daemon` 2＝43；文档自己的 43 行声明与实际表格一致。
- 对账 `docs/tmp/260807-next-small-slice.md:1-15,23-58,69-85`：下一最小代码切片明确为 Responses leg 的 headers-before network retry，只关闭该窄子集；quota／resident backpressure与真实 socket partial-write仍作为后继独立方向，没有被提前写成已验证。

### 第一人称执行模拟

- 以 checkpoint 执行者身份从 Implementation 顶部状态、进度表、下一步和结尾顺序读取：先得到 R3 关键主路径限定 `PASS` 与 facts 缺口关闭，再看到完整产品继续 `UNVERIFIED`、部署继续 `NO_CUTOVER`、Implementation继续 `LIVING`；没有把局部绿灯误读成文档封存或产品验收完成的路径。
- 以 readiness 执行者身份沿 P0→P1→P2→P3 模拟：P0只能保持`PARTIAL`，retry／quota／partial-write仍需正反控制；P1真实 manager／cgroup在本机为`BLOCKED`并须转VM／container；P2 disposition未闭合；P3仍禁止接管`4141`。任一路径都不能据 R3 scoped PASS跳到生产动作。
- 以代码切片执行者身份读取 `260807-next-small-slice.md`：可从current `main@d903d72…`继续 headers-before network retry的两项判别性component tests与窄实现；该代码切片不改写 manager／cutover状态，也不声称关闭stream read阶段retry、quota或partial-write，因此与living边界兼容。

## 事实性发现

未发现问题。

## 主观建议

无。

## Checkpoint 裁决

**两份精确 current bytes 为 0 blocker／0 major，可立即形成 living checkpoint。** Checkpoint 后可继续 `docs/tmp/260807-next-small-slice.md` 定义的 headers-before network retry 窄切片；后续任何文档 bytes、main、运行环境或证据变化都须重新绑定并复评。Backup R3只保留 `PASS_KEY_BACKUP_PORT_SMOKE_R3` 的限定结论；完整产品继续 `UNVERIFIED`，Implementation继续 `LIVING`，部署继续 `NO_CUTOVER`，retry／quota／partial-write、真实manager与cutover均不得由本 verdict升级。

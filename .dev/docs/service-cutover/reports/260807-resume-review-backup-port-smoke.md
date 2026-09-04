# 备用端口 smoke 恢复计划独立复核

- **评审范围**：只读复核 `main@b91e58a29324b11840002efc53ed6f869b800c39` 上的 `docs/tmp/260807-backup-port-smoke-resume.md`，并对照 current Spec／Acceptance、generic upstream 启动路径、non-stream production route、current stream fail-closed、Uvicorn shutdown 语义、当前 loopback listeners 与 `/proc` 进程身份。未启动、停止、reload、signal 或替换任何服务；唯一仓库写入为本报告。
- **总体 verdict**：**修复 2 个 major 后可进入。** `STREAM-MERGE-00`～`10` 的 11 个 gate 在功能与 wire 范围上足以作为 stream 候选的备用端口验收入口，但当前计划的无 token 环境封闭和清理／进程身份判据存在可假绿旁路。修复后，该计划可作为 stream 候选备用端口验收计划；它仍不等于完整 stream／bridge Acceptance、部署或 cutover。
- **blocker 数**：0。
- **major 数**：2。

## 双视角覆盖证据

### 机械核对

- 每次采用的 load-bearing shell 证据均在同一调用内打印并验证物理 root、Git top-level、分支 `main`、`HEAD` 与 `refs/heads/main`，完整 SHA 均为 `b91e58a29324b11840002efc53ed6f869b800c39`。共享终端中未出现本轮 nonce 首尾闭合的串扰输出已明确作废，不进入结论。
- 当前只读运行态为 Bun PID `1623` 持有 `127.0.0.1:4141` 与 `[::1]:4141`；cwd 为 `/home/xp/src/copilot-api-js`，cgroup 为 `0::/init.scope`，cmdline 为 Bun 执行 `./packages/cli/src/main.ts start`。`4142`／`4143` 无 listener。历史自建 PID `119342`／`119050` 当前均无 `/proc` 项，支持“当前无残留进程”的 post-state；执行期间的 transient PID／wire 数值没有通过重启服务重新测量。
- `src/app/upstream/bootstrap.py:96-132` 与 `src/app/upstream/generic.py:45-56` 确认 generic 模式使用配置的占位 API key、`/models` 与 `/responses`，不需要 GitHub／Copilot token来完成 deterministic fake route；`src/app/upstream/client.py:37-62` 明确 SDK `max_retries=0`，不会由 SDK 暗中增加 exchange。
- `tests/smoke/test_anthropic_responses_route.py:249-455` 与 `src/app/anthropic/client.py:182-250` 证明 non-stream gate沿真实 ASGI route断言独立的 Responses request wire、Anthropic response shape、single context／attempt／finalize及 header过滤，不是产品 codec 自己 encode→decode 的同源 roundtrip。Current stream reject在 `src/app/pipeline/executor.py:192-201` 与 `src/app/anthropic/client.py:218-226` 双层 fail closed，现有 route smoke断言 HTTP `400`、code `responses_stream_not_supported`与零 Responses exchange。
- `src/app/delivery/anthropic_sse.py:320-684` 与 `tests/smoke/test_anthropic_block_delivery.py` 只证明 typed parser→in-memory sink 的完整 block、连续前缀、single writer与失败终态；计划要求合并后改用真实 raw HTTP reader、独立 Anthropic SSE grammar consumer和真实 route，是必要且正确的更强入口。
- Current 安装的 Uvicorn `server.py:314-331` 确认捕获 SIGTERM、完成 shutdown后恢复 handler并重新 raise signal；因此 app OS return code `-15`不能单独判为未清理。完整 lifespan日志与资源终态组合判据方向正确。

### 第一人称执行

- 以无 token smoke执行者身份按计划启动 generic fake时，发现产品在 `src/app/server.py:91-99` 判断 `upstream.type == generic` 之前仍无条件调用 `noninteractive_token_available()`；该函数会检查嵌套 settings及可配置token file。计划只清点三个通用环境变量，无法阻止另一路真实凭据被读取。
- 以清理执行者身份模拟 app 提前退出、PID复用、fake关闭listener但进程仍存活，以及旧Bun PID复用。当前“日志＋listener消失＋临时目录删除＋PID/cwd/cgroup/cmdline相等”不能机械区分这些错误状态。
- 以 stream 候选验收者身份依次执行 `STREAM-MERGE-00`～`10`：route接线、Responses SSE→Anthropic SSE、首block前零headers／body、完整batch、连续语义顺序、唯一success terminal、failure terminal、单一lifecycle owner、cancel cleanup与shutdown均有明确红灯；`STREAM-MERGE-00`同时保留non-stream Responses及dual-capability Messages回归。该集合足以作为候选备用端口入口。Reasoning／tool、retry frontier、partial write、backpressure／quota、History enabled、HTTP／WS parity与完整正反控制仍被文档明确留在后续，所以不得把入口绿灯外推为完整产品 `PASS`。

## 事实性发现

[major] `docs/tmp/260807-backup-port-smoke-resume.md:16-18,62-81,152-157` — “无真实 token generic fake”门只检查三个通用变量，不能排除产品实际会读取的嵌套 auth 环境与 token file — `AppSettings`通过 `GHC_` nested env装载 `auth.github_token`／`auth.token_file`；`src/app/server.py:91-99` 即使 generic 模式也先调用 `noninteractive_token_available(settings.auth.github_token, token_path)`，`src/app/auth/providers.py:82-105,153-165` 随后会读取该token file。当前评审 shell中 `GHC_AUTH__GITHUB_TOKEN`、`GHC_AUTH__TOKEN_FILE`、`GHC_CONFIG`及三个通用token变量均为 absent，但未来照现有计划执行可在继承任一嵌套变量时仍把“只检查三变量”判绿，并实际读取真实token — 子进程改用显式环境 allowlist，至少删除／拒绝 `COPILOT_API_GITHUB_TOKEN`、`GH_TOKEN`、`GITHUB_TOKEN`、`GHC_AUTH__GITHUB_TOKEN`、`GHC_AUTH__TOKEN_FILE`与`GHC_CONFIG`，把effective `auth.token_file`固定到一次性根内已知不存在的路径；启动后只断言effective auth token presence为false，不输出值。将该条件加入 SAFE-03、固定前置门与每轮记录，正控为注入每一种旁路后门必须变红且不得启动app。

[major] `docs/tmp/260807-backup-port-smoke-resume.md:27-28,37-57,132-141,147-171` — 清理与“只杀自建 PID／旧 Bun不变”判据没有冻结进程 incarnation，也没有要求两个自建 child均被 wait／reap；listener消失可在残留进程或 PID复用下假绿 — 计划只规定向记录的app PID发SIGTERM，并以shutdown日志、`4142`／`4143` listener消失、临时目录删除及旧Bun的PID／cwd／cgroup／cmdline相等收口。若app在signal前退出且PID被复用，裸PID signal可能命中非自建进程；若fake关闭socket后挂住，CLEAN-02仍可通过；若旧Bun重启后复用PID与同一cmdline，SAFE-01也缺少start-time／socket identity区分 — harness必须持有两个child process handle；启动时记录PID＋Linux `/proc/<pid>/stat` starttime（可用pidfd时优先持有pidfd）＋listener socket inode，signal前要求child handle仍指向同一incarnation，只通过该handle／pidfd向app发送SIGTERM；app与fake都必须在deadline内`wait()`并reap，随后断言两历史incarnation消失、`4142`／`4143`无listener。旧Bun前后比较增加starttime与双栈listener socket identity；任一身份漂移、wait超时或残留child均判红，不向未知owner发送任何signal。

## 结论

**0 blocker／2 major。** Non-stream wire／response、current stream fail-closed与11个stream候选gate的功能覆盖没有发现阻断问题；但当前计划尚不能安全执行为验收入口。关闭上述无token旁路和进程incarnation／reap两项major后，`STREAM-MERGE-00`～`10`足以作为stream候选备用端口验收计划；完整stream与完整bridge产品继续保持`UNVERIFIED`，部署继续保持`NO_CUTOVER`。

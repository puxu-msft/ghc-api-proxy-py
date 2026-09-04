# Current main 备用端口关键主路径 smoke R3 独立快速复核

## 评审摘要

- **评审范围**：仅复核 `docs/tmp/260807-final-backup-port-smoke-r3.md` 在 `main@d903d726baf3f15bf46ddf17384564fee154ed6a` 上记录的主路径结果、stream History request conversion facts 缺口关闭、credential／config 隔离、pidfd 精确终止与原 handle wait／reap、旧 Bun incarnation 不变且零 signal、未验证边界和 `NO_CUTOVER`。未重跑服务，未扩展 retry、quota、partial-write 或其他矩阵。
- **总体 verdict**：**可进入下一阶段（可归纳）**。报告的 scoped `PASS_KEY_BACKUP_PORT_SMOKE_R3` 与其证据边界相符；完整 bridge／Acceptance 继续为 `UNVERIFIED`，生产继续为 `NO_CUTOVER`。
- **Blocker 数**：0。
- **Major 数**：0。
- **Minor 数**：1。

## 双视角覆盖证据

### 机械核对

- 每次 shell gate 均现场验证物理仓库根、当前目录、`main` 分支、`HEAD == refs/heads/main == d903d726baf3f15bf46ddf17384564fee154ed6a`。
- 逐项对账报告的 candidate 身份、固定 `4142／4143` 拓扑、三次固定无 retry exchange、stream withholding 与唯一 terminal、History API 观察、credential／config 入口隔离、app／fake PID＋starttime＋pidfd＋wait／reap、旧 Bun 多时点 identity／双栈 listener／零 signal、最终端口与临时根收口。
- 核对 `src/app/pipeline/executor.py:295-303`：success attempt 在 stream／nonstream 分叉前发布带 attempt 的 request conversion facts；核对 `src/app/history/consumer.py:151-172`：stream usage 从同一 `RequestContext` 投影 conversion facts。该代码接缝与报告通过真实 History API 观察到的 `provenance=request／attempt=0／metadata.smoke_extra／metadata_not_allowlisted` 一致。
- 核对报告未把真实 credential、真实 upstream、完整 History／terminal／usage、retry、quota／backpressure、真实 socket partial-write／RST、systemd manager／effective cgroup、部署或 cutover 写成已验证；结论仍明确保留 `UNVERIFIED` 与 `NO_CUTOVER`。
- 核对现有 smoke 测试对 SIGTERM 后 app `returncode == -SIGTERM` 的预期，报告同时出现完整 Uvicorn lifespan 日志与 `return code=-15` 并不构成矛盾。

### 第一人称执行模拟

- 按执行者路径模拟 nonstream 请求进入显式 ephemeral config 指向的 loopback fake，确认报告只据 HTTP 200、Anthropic JSON 与单次 Responses exchange判定该固定主路径，而不外推 retry。
- 按 stream happy 路径模拟跨 chunk CRLF Responses SSE、完整 block 前停顿、Anthropic SSE 消费和唯一 `message_stop`，确认 scoped 成功判据与“完整 block 前零 success bytes”合同一致。
- 按 stream History 路径模拟 request conversion fact 在 attempt success 接缝发布、stream finalization 从同一 context 投影并由真实 History API读取，确认 R2 的定向缺口在该无 retry、attempt 0 路径关闭；再沿 retry／多 attempt／partial／uncertain 分支执行，报告均保留为未验证，没有遗漏成已关闭路径。
- 按 credential／config 路径模拟父环境、child allowlist、CLI token 槽、默认 config、token file 与隔离 XDG／History／tokenization 路径，确认真实 credential 没有成为本轮依赖；固定非真实哨兵只证明 Generic SDK 消费显式隔离配置。
- 按清理路径模拟 app／fake direct child 绑定 pidfd、各自一次 SIGTERM、由原 `Popen` handle wait／reap，再由独立 post-probe 检查历史 PID、临时根和备用端口消失；同时沿旧 Bun 路径只读比较多时点 incarnation，并确认报告声明 `signals_to_bun=0`，没有把 signal 发往生产 listener。
- 按后续读者路径模拟是否可以据本报告停止旧 Bun或接管 `4141`；报告在范围、未验证边界和最终结论三处均否定该推论，因此不会误导执行 cutover。

## 事实性发现

[minor] `docs/tmp/260807-final-backup-port-smoke-r3.md:24,63` — raw cmdline 的读取描述自相矛盾 — 第 24 行明确称 raw cmdline “只在 controller 内存中比较并得到相等”，这必然包含读取；第 63 行却绝对声称“没有读取、打印或 hash raw cmdline 内容”。该矛盾不影响 incarnation 相等或零 signal 结论，但会让审计者无法判断隐私边界究竟是“不读取”还是“只读入内存且不输出／持久化” — 建议把第 63 行收窄为“独立 post-probe 未再次读取 raw cmdline；controller 仅在内存读取并比较，未打印、hash 或落盘其内容”，与第 24 行保持一致。

除上述 minor 外，未发现 blocker 或 major。主路径结果、stream History facts 定向关闭、隔离与清理终态、旧 Bun 零 signal／incarnation 不变，以及 `UNVERIFIED／NO_CUTOVER` 边界可以归纳。

## 主观建议

无。

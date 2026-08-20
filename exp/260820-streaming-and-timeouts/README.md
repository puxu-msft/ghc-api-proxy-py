# 2026-08-20 探针存档：块级交付的上游所有权与三个超时守卫

本目录保存的是 9 份已提交报告所引用的探针脚本。报告在 `docs/tmp/` 下（主仓库），它们点名 `/tmp/rev-*`、`/tmp/smell-probe`、`/tmp/idle-research` 里的文件作为证据；`/tmp` 会随重启消失，脚本因此挪到这里，路径按原来的根目录名分组，文件名未改，报告里的引用照着 `<组名>/<文件名>` 就能对上。

**只保留了脚本（59 个）。** 每个根目录下还有为变异对照复制的整棵仓库树（三个根合计约 23000 个文件），那些是派生物：由 `git` 加上报告里记录的变异内容可以重建，不保留。

## 各组回答了什么

| 组 | 问题 | 结论 | 主要载体 |
|---|---|---|---|
| `smell-probe` | 关闭 `stream_delivery` 时上游到底释放没有 | 改动前 pull 在途则永不释放且 GC 收不掉；`session_liveness_stream` 是确定性释放的正样本对照 | `docs/tmp/260820-smell-survey-streaming-pull.md` |
| `rev-shield` | `shield` + `wait_for` 超时后为什么会打 `StopAsyncIteration exception in shielded future` | CPython 在 outer 被取消时给 inner 挂模块级 `_log_on_exception`，后续 `shield()` 不摘掉它 | 提交 `7a51902` |
| `rev-s1` | 上游所有权修复的七条退出路径、异常优先级、循环收尾 | 全部确定性关闭、零残留 task | `docs/tmp/260820-review-s1-upstream-ownership.md` |
| `rev-s1-wiring` | 该修复落到真实 starlette/httpx 链路上的表现 | 弃流噪声、连接池排空时机、`_AccountedStreamingResponse` 不关 body | `docs/tmp/260820-review-s1-wiring.md` |
| `idle-research` / `rev-idle` / `rev-idle-impl` / `rev-idle2` | idle 守卫该按字节还是按解析事件计时 | 注释保活下事件级会误杀（C1 不触发 / C2 触发的对照） | `docs/tmp/260820-research-pipeline-idle-timeout.md` |
| `rev-timeouts` / `rev-tw` | `await provider.send()` 等到哪一刻返回 | 流式下响应头到达即返回（1.084s 发头 / 1.086s 返回 / 体 +2s）；httpx read timeout 量的是读间间隔而非等头总时长 | `docs/tmp/260820-research-upstream-timeout-wiring.md` |

## 它们不证明什么

- **不证明上游 Copilot 的真实行为**。除少数几个连真实本地 HTTP 服务器的探针外，绝大多数用手写的 async generator 或 httpx `MockTransport` 充当上游。注释保活那组尤其如此：它证明的是**机制**（注释帧不产生解析事件、因此两种计时不等价），**不证明 Copilot 会发注释帧**——那一点本次没有证据，见研究报告的相应说明。
- **不证明覆盖率**。每个探针只走一条路径；报告里写的「N/M 次」是那一条路径的重复次数，不是场景空间的覆盖。
- **socket 级与 generator 级不可互推**。`rev-s1` 里明确测到：关闭 generator 链在 generator 级是确定性的，而 httpx 的 `Response` 根本不参与该级联（`aiter_raw` 把 `aclose()` 写在循环之后而非 `finally` 里）。

## 怎么重跑

多数脚本形如 `PYTHONPATH=src python <脚本>`，在主仓库根目录跑。少数需要参数（例如 `rev-s1/e8_loop_shutdown.py` 要 `abandon|explicit|closed-loop`）或环境变量（`rev-s1-wiring/probe_close_chain.py` 认 `SLOW_SEND=1`）。

**跑在副本树里时务必连 `pyproject.toml` 一起复制**，否则 pytest 缺配置会让 harness 自己报错，而输出看上去仍是一个正常的数字——本次踩过三次，见项目记忆 `prove-the-probe-ran-before-reading-its-number`。

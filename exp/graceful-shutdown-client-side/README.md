# 优雅关闭客户端侧：探针与复现脚本

2026-08-20 期间用过的一次性脚本，保留可跑。结论已经写进 `.dev/docs/graceful-shutdown/client-side/README.md`，这里保留的是**取证手段**。

> **路径与常量是 2026-08-20 的快照。** 脚本里写死了 `/home/xp/src/ghc-api-proxy-py`，也假设 `uv run ghc-api-proxy start` 可用、有可用凭据（走真实上游的那几个）。

## 它们回答了什么

| 脚本 | 问题 | 结论 |
|---|---|---|
| `repro_hang.py` | 单条空闲 keep-alive 连接 + 关停，会不会挂？ | **不会**。这一版没有分辨力——见下方警告 |
| `repro_hang2.py` | 在途长请求撑开排空窗口时，池化连接中途发请求会不会挂？ | **会**。挂起并打出与生产同形的 `gated_app` → `CancelledError` traceback |
| `probe_half_sent.py` | `POST` 打到只注册 GET 的 FastAPI，Starlette 会读 body 吗？ | **不会**。任何信号之前就回 405，`allow: GET`，31 字节 |
| `probe_router_resume.py` | `both` 模式 quiesce → drain → resume 之后，拒绝态清干净了吗？ | 修复后 `resumed: refusal=None open=True`；退化成「只开闸不清拒绝态」则 resume 后所有请求永久 503 |
| `e2e_real_cli.sh` | 真实 CLI 进程上，缺陷在／修复后各是什么行为？ | 变异版：在途请求完成 15 秒后仍不退出。修复版：1.8 秒退出，在途请求拿到真实上游 200 |
| `e2e_severed.sh` | 单连接扫「信号到下一次写」的时序，能不能命中切断窗口？ | gap ∈ {-0.05, 0, 0.002, 0.05} **四次全部落空** |
| `e2e_severed_burst.sh` | 20 条连接在信号后一起写，能命中吗？ | **不能**。写入全部早于服务端被唤醒，被同一批读回调取走 |
| `e2e_severed_hammer.sh` | 40 条连接由线程跨越信号错峰写入呢？ | **能**，3 次命中 2 次（独立审计在合适节奏下量到 90%–100%） |

## 它们不能证明什么

- **`repro_hang.py` 的绿什么都不证明。** 没有在途请求时整个关停在毫秒级走完，第二个请求根本落不进窗口——修复版与变异版都会「正常退出」。它留在这里是**反面教材**：一个探针的绿只有在先证明它能看见坏行为之后才作数。
- **`e2e_severed.sh` 与 `e2e_severed_burst.sh` 的「没命中」不等于「不会发生」。** 它们量的是「从外部瞄不准这个窗口」，不是「窗口不存在」；`e2e_severed_hammer.sh` 证明了它存在。
- **全部脚本只覆盖明文 HTTP/1.1 + h11。** 没有一个走 TLS 路径，而 TLS 恰恰是切断探测已知会**多报**（等待的字节可能是重协商）和**少报**（字节已被吸进 SSL 对象）的地方。
- **`e2e_real_cli.sh` 与 `e2e_severed_hammer.sh` 会发起真实上游请求**（`POST /v1/messages`），需要凭据，且会计入配额。
- 命中率数字来自 16 核机器上的若干次运行，不是稳定基线。

## 怎么跑

```sh
cd /home/xp/src/ghc-api-proxy-py

# 进程内复现（无需凭据、无需上游）
PYTHONPATH=src uv run python <这个目录>/repro_hang2.py
PYTHONPATH=src uv run python <这个目录>/probe_router_resume.py
uv run python <这个目录>/probe_half_sent.py     # 需要 tests/integration 在 sys.path 上

# 真实 CLI（各自起独立端口与 pidfile，只对自己启动的子进程发信号）
bash <这个目录>/e2e_real_cli.sh
bash <这个目录>/e2e_severed_hammer.sh
```

`$CLAUDE_JOB_DIR` 已不存在，脚本里引用它的地方会退回 `/tmp`。**每个脚本都只对自己 `start` 的子进程发信号，不会碰 4141 上的既有服务**——修改时请保持这条。

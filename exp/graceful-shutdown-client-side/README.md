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
- **全部脚本只覆盖明文 HTTP/1.1 + h11。** 没有一个走 TLS 路径，而 TLS 恰恰是切断探测已知会**多报**（等待的字节可能是重协商或 close_notify）和**少报**（字节已被吸进 SSL 对象）的地方。
- 命中率数字来自 16 核机器上的若干次运行，不是稳定基线。

## 凭据与配额

**四个 `.sh` 都需要一个能启动的代理进程**——保留下来的 13 份服务端日志里每一份都有 `42 models available from ghc`，即启动过程包含一次模型列表拉取。**没有实测过在无凭据环境下启动会怎样**，所以「必须有凭据才能启动」是推断而非结论；若要确认，最省事的办法是把凭据挪开跑一次 `e2e_severed.sh` 看它停在哪。

**只有 `e2e_real_cli.sh` 的请求真的走到上游、计入配额**：它发的是完整合法的 `{"model": "gpt-5.5", "max_tokens": 16, ...}`，日志里能看到 `H1/H2 200 anthropic-messages/gpt-5.5 → gpt-5.6-terra`。

`e2e_severed.sh` / `e2e_severed_burst.sh` / `e2e_severed_hammer.sh` 发的是 `Content-Length: 2` 的 `{}`，`MessagesRequest` 的必填字段校验在**本地**就打回（`H1 400 POST /v1/messages 0ms`），从不出网。想在不烧配额的前提下复算切断窗口，跑 `e2e_severed_hammer.sh`——它正是唯一证明那个窗口存在的脚本。

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

四个 `.sh` 把中间产物写进 `${CLAUDE_JOB_DIR:-/tmp/ghc-shutdown-probes}/tmp` 并会自行 `mkdir -p`（**未检查该命令是否成功**——在那个路径不可写的环境里，下面那个静默失败形态会原样重现）。**这一点是修过的**：原先回退到 `/tmp/tmp`，而那个目录并不存在；脚本用 `set -u` 而没有 `set -e`，于是重定向失败只会让后台启动静默夭折，探针对着一个没起来的端口空转 40 秒，然后给出一个看起来像测出来的假结论。**这是最坏的失败形态——不报错、只是慢、静、且可信。**

**每个脚本都只对自己 `start` 的子进程发信号，不会碰 4141 上的既有服务**——修改时请保持这条。

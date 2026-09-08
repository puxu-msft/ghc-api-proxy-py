# Current main foundations／systemd 独立验收

## 判定

- **总体 verdict**：**PASS（仅限本报告声明的 foundations／systemd 范围）。**
- **验收对象**：`/home/xp/src/ghc-api-proxy-py` 的 `main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c`。
- **冻结 oracle**：`docs/agents/anthropic-responses-bridge/spec.md`，本轮读取文件 SHA-256 为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；systemd M1 行为边界取自 `docs/agents/deployment-systemd/README.md`。
- **结论边界**：本 PASS 只覆盖 reasoning cardinality／encrypted-only、pure request converter、session liveness primitive，以及 rootless inherited-fd CLI／真实 HTTP／SIGTERM／状态路径。它不表示完整 Anthropic Responses bridge、route policy、Responses transport、response conversion、block buffering、retry、真实 systemd manager、effective cgroup、service-gap continuity、rolling、安装、部署或 cutover 已通过。
- **生产 route 现状**：`convert_messages_request_to_responses()` pure 入口范围内 PASS，但 current production route 尚未消费该入口；真实 HTTP probe 仍观察到 generic upstream 路径 `[/v1/models, /v1/messages]`，未观察到 `/responses` 调用。这与本次用户指定的“route 未接但 pure 入口”边界一致，不能外推为 bridge route PASS。

## 从冻结合同独立推导的验收矩阵

| ID | 用户可观察判据 | 独立 oracle／边界 | 结果 |
|---|---|---|---|
| FND-REASON-01 | 每个 Responses reasoning item 独立形成一个 Anthropic thinking block，item 间不聚合，source order 保持 | Spec“Reasoning 与 signature 契约”及验收行为中的“一 item 一 block” | PASS |
| FND-REASON-02 | 普通模式下，非空 encrypted-only item 仍形成空 visible thinking block，并可 value-exact 恢复同一 `encrypted_content` | Spec“encrypted-only reasoning”与“Roundtrip” | PASS |
| FND-REQUEST-01 | pure converter 对同一 Anthropic input 产生确定、顺序保持的 Responses wire，且不修改输入 | Spec“Request conversion 契约”；只验 pure 入口，不要求 route 已接 | PASS |
| FND-REQUEST-02 | unsupported `top_k` 不得 silent drop，必须给稳定 `code` 与 `field_path` | Spec 双向字段处置矩阵中 `top_k=REJECT` | PASS |
| FND-REQUEST-03 | production route 当前没有把 pure converter 冒充已接线能力 | AST production consumer 扫描与真实 HTTP upstream path 观察交叉验证 | PASS，结论为“未接线” |
| FND-LIVE-01 | upstream `anext` pending 时可发 heartbeat；外层取消不得被吞 | session liveness primitive 的用户可观察流行为 | PASS |
| FND-LIVE-02 | 取消路径必须 settle pending pull，并关闭 iterator 恰好一次 | Spec shutdown／cancel 资源关闭合同在该 primitive 范围内的基础能力 | PASS |
| SYS-CLI-01 | CLI 真实消费 inherited listener fd，而非只把 `fd` 留在 mock／配置层 | systemd living README 的 fd 3 合同；`src/app/cli.py:53,114` | PASS |
| SYS-HTTP-01 | 父进程预连接 backlog 经 inherited listener 获得真实 liveness HTTP 200；新连接获得 readiness HTTP 200，并可完成真实 `/v1/messages` 请求 | `docs/agents/deployment-systemd/README.md:68-70` 的 rootless runtime smoke 合同 | PASS |
| SYS-TERM-01 | 向真实 CLI／Uvicorn 子进程发送 SIGTERM 后执行 FastAPI lifespan cleanup 并退出 | `docs/agents/deployment-systemd/README.md:61-65`；`src/app/server.py:52-137` | PASS |
| SYS-STATE-01 | 无可写 HOME 时，History 与 tokenization 只写入显式覆盖状态路径，默认路径不产生文件 | `docs/agents/deployment-systemd/README.md:33-44,68-70` | PASS |

## 独立 probes 与实际结果

所有承载结论的 shell 调用均在同一次调用中打印并验证 physical root、`main` 分支与 exact HEAD `cf53334a10a717a3a3d30d6c0e8a297f5000d90c`，并以 `app.__file__=/home/xp/src/ghc-api-proxy-py/src/app/__init__.py` 证明 Python 实现来自 current main。

### Reasoning 与正控

- `REASONING_PROBE_260807_6A4F` 使用三个 reasoning items，其中一个 summary＋ciphertext、一个 non-reasoning 间隔 item、一个 encrypted-only、一个 summary-only。实际结果为 `REASONING_ORACLE=PASS blocks=3 encrypted_only=value-exact source_order=yes`。
- 同一进程内把 `_encode_encrypted_content` 临时 monkeypatch 为始终返回 bare carrier，未写生产文件。相同 oracle 按预期变红，输出 `POSITIVE_CONTROL=RED`；恢复原函数后同一 oracle 再次变绿，输出 `POSITIVE_CONTROL_RESTORED=GREEN`。失败来自 encrypted-only value-exact recovery 断言，正控确实咬住目标机制。
- 生产锚点：`src/app/anthropic/thinking/responses_reasoning.py:67`。

### Pure request converter 与 route 边界

- `REQUEST_COMPACT_260807_7F31` 对 system 空 segment、text／tool_use／text 顺序、tool_result、输入不可变、重复转换确定性和非默认 `top_k` strict rejection 执行独立 probe。实际结果为 `REQUEST_PURE=PASS deterministic=yes order=yes strict=yes input_unchanged=yes`。
- 同一 probe 用 Python AST 扫描 `src/app/**/*.py`，排除 converter 自身定义文件后，`convert_messages_request_to_responses` production consumer 为 0，输出 `ROUTE_WIRING=ABSENT ast_consumers=0`。这是一条“未接线”边界证据，不是 route 完成证据。
- 真实 inherited-fd runtime smoke 的受控 generic upstream 只收到 `/v1/models` 与 `/v1/messages`，与 AST 扫描相互独立地支持“route 未接”。
- 生产锚点：`src/app/protocols/anthropic_responses.py:669`。

### Session liveness primitive

- `LIVENESS_PROBE_260807_D04A` 在一个永远 pending 的真实 async iterator 上观察 heartbeat，然后取消正在等待下一个输出的 consumer task。
- 实际结果为 `LIVENESS=PASS heartbeat_while_pull=yes outer_cancel=preserved pending_pull_cancelled=1 iterator_closed=1`；随后再次 `aclose()` 未增加 close 次数，排除 double-close。
- 生产锚点：`src/app/streaming/keepalive.py:8`。

### CLI inherited fd／真实 HTTP／SIGTERM／状态路径

- 独立运行 targeted runtime node `tests/smoke/test_systemd_units.py::test_inherited_listener_serves_ready_generic_upstream_and_persists_overrides`，结果为 `1 passed in 2.92s`，退出码 0；该 node 从父进程创建真实 TCP listener 与预连接 backlog，把 listener 复制为子进程 fd 3，执行真实 `python -m app start --fd 3`，不是 mock `uvicorn.run()`。
- 该 runtime node 验证预连接 `/health/liveness` HTTP 200、新连接 `/health/readiness` HTTP 200、真实 `/v1/messages` HTTP 200、受控 generic upstream 实际收取模型与 Messages 请求、SIGTERM 后日志包含 `Application shutdown complete.` 与 `Finished server process`、History 与 tokenization 文件落在显式覆盖目录，默认目录对应文件不存在。
- 生产锚点：`src/app/cli.py:53,114`、`src/app/server.py:52`；runtime harness 锚点：`tests/smoke/test_systemd_units.py:227`。

## Targeted 回归与静态门

- 在 current main 与 import gate 下执行 `tests/unit/test_responses_reasoning.py`、`tests/unit/test_anthropic_responses_request.py`、`tests/unit/test_streaming_resilience.py`、`tests/unit/test_cli.py`、`tests/smoke/test_systemd_units.py`，实际结果为 `102 passed in 5.74s`，退出码 0。
- 对同一五文件集合执行 `pytest --collect-only -q`，按 node ID 独立计数为 102，退出码 0。执行汇总与 collect-only 两种不同方法对测试集合规模一致；该数字的口径固定为上述五个文件、current main exact HEAD 与本轮环境，不是永久阈值。
- 对本范围五个生产文件与对应五个测试文件执行 targeted Ruff，结果 `All checks passed!`；执行 targeted Pyright，结果 `0 errors, 0 warnings, 0 informations`。

## 未验证与禁止外推

- **未验证**：Anthropic `/v1/messages` 选择 Responses protocol leg、Responses HTTP／WS transport、response converter、non-stream／stream 等价、block commit frontier、retry／History／usage／error／header 完整 bridge 行为。原因是 production route 尚未接 pure converter，且用户明确要求不外推完整 bridge。
- **未验证**：真实 systemd manager 传 fd、service restart gap 中 listener identity、accepted connection drain、effective cgroup limits、`TimeoutStopSec` 升级、rootless install helper、rolling／双实例、部署与 cutover。当前 runtime smoke 只证明 direct inherited-fd M1 基座。
- **未验证**：项目主 v1 carrier 双格式完整合同。本轮 reasoning 判据仅为“一 item 一 block／encrypted-only no-loss”；current `responses_reasoning.py` 仍使用 upstream `copilot-api:synthetic-reasoning:v1` carrier，不能借本 PASS 声称项目主 v1 producer 已完成。

## 结构怪味与判据反思

- **`src/app/protocols/anthropic_responses.py:669`｜职责接缝未接线**：pure converter 已形成独立协议能力，但 production consumer 为 0。处置：本轮不改生产代码，按用户指定边界记录为“pure 入口 PASS／route 未接”，并把完整 route 行为留为未验证；把它包装成 route PASS 会制造 false-green。
- **更好的内部替代方案**：若要验收完整 bridge，最佳下一层不是继续扩大 pure converter fixture，而是在唯一 Anthropic pipeline owner 的每-attempt `PRE_SEND` 后接线，并以受控 `/responses` upstream 做真实 route probe。本轮未获该实现范围，故不静默扩张。
- **判据判别力**：reasoning oracle 通过目标机制正控证明可在 ciphertext 丢失时变红；systemd 使用真实 CLI／Uvicorn 子进程、真实 TCP listener、HTTP 与 SIGTERM，而不是仅凭 unit 文本或 `uvicorn.run()` mock。正确样本也实际为绿，因此同时防 false-green 与 false-red。
- **成熟第三方方案**：进程与 HTTP 行为继续复用 Uvicorn、pytest、Pyright 与 Ruff；本轮没有自造 server、type checker 或 test runner。真实 systemd manager 行为不能由这些替代，故明确维持未验证，而不手写 manager 模拟器冒充证明。

## 证据处置说明

两次较长 shell 尝试被共享终端中的并发旧输出串扰，缺少本轮 nonce 或出现工具退出状态与正文矛盾，已全部作废且未进入上述 PASS 证据。最终结论只使用具有成对 `BEGIN／END` nonce、exact main gate、import gate与明确退出码的成功重跑，以及独立 reasoning／request／liveness probes。

## 最终结论

`main@cf53334a10a717a3a3d30d6c0e8a297f5000d90c` 在本报告限定的 foundations／systemd 范围内 **PASS**：reasoning 一 item 一 block且 encrypted-only value-exact no-loss；pure request converter 确定、保序、strict，但 production route 明确未接；session liveness 在 pending pull／取消／cleanup 路径成立；CLI inherited fd 经真实 HTTP、SIGTERM 与显式状态路径 runtime smoke 成立。除此之外一律维持未验证，不得把本 verdict 外推为完整 bridge、真实 systemd manager、部署或 cutover PASS。

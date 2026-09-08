# current main happy pure-path 与 usage 独立验收

## 验收范围与结论

- **候选**：`/home/xp/src/ghc-api-proxy-py`，`main@80bc8f252b46c511f428af1d97159a5980ee9dc9`。
- **行为 oracle**：`docs/agents/anthropic-responses-bridge/spec.md`，本轮以 `sha256sum` 与 Python `hashlib.sha256` 交叉复核 SHA-256 均为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；验收映射参考 `docs/agents/anthropic-responses-bridge/acceptance.md` SHA-256 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。
- **本轮被测对象**：只验 current main 上可以直接组合的 happy pure-path primitives：route policy 选择 Responses → Anthropic request converter → 模拟完整 Responses JSON → non-stream Anthropic converter 与 usage → Responses stream lifecycle parser 产出 semantic blocks → project carrier producer／consumer、upstream compatibility consumer 与 direct Messages strip。
- **总体判定**：**`PASS`，仅限上述 happy pure-path。** 五项正确样本全部通过；6 个单侧目标缺陷正控全部按目标原因转红。未发现该范围内的 Spec 偏差。
- **完整产品判定**：**`UNVERIFIED`。** 当前真实 `POST /v1/messages` route 尚未接入 route policy、Responses request／response converter 或 stream parser；本轮没有验证真实 ASGI route、真实 Responses HTTP／WebSocket transport、Anthropic SSE renderer、block delivery、retry、History、hooks、approval、cancel、shutdown、backpressure、limits、error path 或真上游。因此 pure-path `PASS` 不得表述为完整 bridge、真实 route 或产品验收通过。

## 从冻结 Spec 独立推导的矩阵

| ID | Spec 可观察合同 | 独立输入与 oracle | 实际结果 | 正控 |
|---|---|---|---|---|
| R1 | Responses-only model 应选择 Responses protocol leg，且事实来源可审计 | `supported_endpoints=["/responses"]`、HTTP Responses transport 可用；静态 expected 为 `responses／single_capability／model_catalog` | `PASS` | 把已观察 leg 单侧改为 `messages` 后，oracle 因 `wrong_leg` 转红 |
| R2 | canonical Anthropic request 必须直接转换为 Responses wire，保持 system segment、turn／block 顺序、reasoning echo、tool identity、tool result、resolved model 与显式 degradation | 三段 system 含空 segment；user text → project-v1 thinking → tool call → assistant text → tool result → user text；静态完整 wire equality | `PASS`，得到 6 个有序 Responses input items；`metadata.audit` 精确记录为 `DEGRADE` | 删除 `instructions` 后，oracle 因 `missing_instructions` 转红 |
| R3 | 完整 Responses JSON 必须按语义顺序转换为 Anthropic blocks；tool call 决定 `stop_reason=tool_use`；usage 固定使用 `I=max(0,T-R-W)`，reasoning 不二次相加，未来 details 保留为 typed facts | reasoning、两个 output text、function call；`T=100,R=20,W=10,O=30,Q=12`，另含 future input／output details | `PASS`，4 个 blocks；wire input 为 70、cache read 为 20、cache creation 为 10、output 为 30；normalized total 为 130 | 把 normalized total 单侧改为 142 后，oracle 因 `reasoning_double_count` 转红 |
| R4 | stream parser 必须在 authoritative completion 后产出有 identity 的 immutable semantic blocks，并保持 reasoning → text → function call 顺序 | reasoning `.added` 含 draft payload，`.done` 含 authoritative payload；随后 text 与 function arguments lifecycle，再 completed terminal | `PASS`，3 个 semantic blocks；reasoning 采用 `authoritative`，terminal 为 `completed` 且无 open block | 交换前两个 blocks 后，oracle 因 `semantic_reorder` 转红 |
| R5 | project v1 producer／consumer 应 value-exact；consumer 应接受 upstream v1 合法主路径；direct Messages leg 应剥离整个 project namespace、upstream payload 与 legacy sentinel，同时保留 native Anthropic thinking | Spec 静态 project exact vector `opaque-😀`；upstream vector `ENC==`；direct-strip 输入含 project v1、project unknown version、upstream v1、upstream legacy、native thinking 与 text | `PASS`，project roundtrip、upstream decode 均 value-exact；4 个 proxy carrier blocks 被剥离，native thinking 与 text 保留 | 改 project namespace 后 producer vector oracle 转红；把 project block重新放回 direct output 后 strip oracle 因 `proxy_carrier_leak` 转红 |

## 实际执行证据

每次 shell 调用都在同一次调用内执行以下 gate：物理 root 为 `/home/xp/src/ghc-api-proxy-py`、`PWD` 等于该 root、分支为 `main`、HEAD 精确等于 `80bc8f252b46c511f428af1d97159a5980ee9dc9`；每次结束再次核对 HEAD，并检查 tracked worktree 状态。

- Oracle gate：Spec SHA-256 的 `sha256sum` 与 Python `hashlib` 结果均为 `5e3628226238a2c271824bc47d0f2fd67db9a6eb36224ee088984c96eb62a5f1`；Acceptance 两种方法均为 `224b020d30059b899bbdc2571af0ebd199f061df2288e5c202f8cd264e9c76f4`。
- R1／R2 probe，退出码 0：`R1_ROUTE=PASS`、`R2_REQUEST=PASS items=6`；正控分别为 `RED(target=wrong_leg)` 与 `RED(target=missing_instructions)`。
- R3 probe，退出码 0：`R3_NONSTREAM_USAGE=PASS blocks=4 normalized_total=130`；正控为 `RED(target=reasoning_double_count)`。
- R4 probe，退出码 0：`R4_STREAM_SEMANTICS=PASS blocks=3 authoritative_reasoning=yes terminal=completed`；正控为 `RED(target=semantic_reorder)`。
- R5 probe，退出码 0：`R5_CARRIER_STRIP=PASS project=roundtrip upstream=decode directstrip=4`；正控分别为 `RED(target=producer_namespace)` 与 `RED(target=proxy_carrier_leak)`。
- 第一次组合 probe 在产品断言前因验证 harness 对 `MappingProxyType` 使用 `dataclasses.asdict()` 而失败；第二次长 here-doc 被交互终端输入截断。二者均属于 probe harness／执行载体问题，没有形成产品失败证据。本报告只采纳随后拆分并以退出码 0 完整结束的五段 probe。
- 本轮未新增测试、fixture 或生产代码；所有验证均为不写盘的独立 Python probe。唯一新增验证产物是本报告。

## 真实 route 接线边界

以下 current main 事实证明本轮只能放行 pure-path，而不能放行真实 route：

- `src/app/routes/anthropic.py:64` 定义真实 `POST /v1/messages` handler；`src/app/routes/anthropic.py:83` 仍直接调用 `client.execute()`。
- `src/app/routes/anthropic.py:111` 的 stream 路径仍使用 `passthrough_bytes()`；`src/app/routes/anthropic.py:122` 的 non-stream 路径仍直接读取 upstream body。
- `src/app/anthropic/client.py:125` 的发送接缝仍只调用 `_target.send_anthropic()`。
- 对 `src/app` 搜索 `decide_protocol_leg|convert_messages_request_to_responses|convert_responses_response_to_anthropic|ResponsesStreamParser`，命中仅为四个 primitive 自身的定义与 `__all__` 导出，没有 production consumer。对应定义位置为 `src/app/pipeline/route_policy.py:78`、`src/app/protocols/anthropic_responses.py:667`、`src/app/protocols/responses_anthropic.py:72`、`src/app/openai/responses_stream_parser.py:135`。

因此，真实 `/v1/messages` route 未接 Responses 不是本轮 happy pure-path 的失败，而是明确的未验收接线范围。只有 route policy、per-attempt request conversion、Responses transport、non-stream／stream response conversion、Anthropic renderer 与单一 lifecycle owner 在真实入口共同接通并通过对应 Acceptance gates 后，完整产品 verdict 才可能从 `UNVERIFIED` 升级。

## 未验证项

- 真实 ASGI `POST /v1/messages` 对 Responses leg 的 route selection 与 network call count。
- Responses HTTP JSON／SSE 与 WebSocket upstream transport，以及 HTTP／WS parity。
- Anthropic SSE wire grammar、首 block 前零 success headers／body、完整 block commit、continuous prefix 与 sink uncertainty。
- pre-commit retry、post-commit partial failure、attempt reset、usage／header attempt provenance。
- approval、hooks、History、tokenization calibration 与 exactly-once finalize。
- cancel、shutdown、backpressure、request／global resident quota、limit 与 cleanup。
- error、malformed、unknown item、unsupported capability、server-tool no-revive 等非 happy path。
- 真 upstream canary、capture corpus、local transport fault 与官方 Anthropic SDK stream consumer。

## 最终 verdict

**`PASS`：current `main@80bc8f252b46c511f428af1d97159a5980ee9dc9` 的 happy pure-path primitives 在本轮指定纵向范围内满足冻结 Spec，并通过有效单侧正控。**

**`UNVERIFIED`：真实 `/v1/messages` route 未接 Responses，完整 Anthropic Responses bridge 与完整产品仍未验收。不得把本报告的 pure-path `PASS` 外推为 route-level、transport-level、lifecycle-level 或完整产品 `PASS`。**

本报告是非平凡验收 wrap-up 产物。当前执行者为 leaf verifier，不能自行派生 reviewer；独立报告评审义务交回主会话，评审前不得把本报告当作已完成二次复核的最终放行文件。

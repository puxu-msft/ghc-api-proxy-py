# Anthropic Responses bridge successor merged-state 独立代码评审

- **评审范围**：`/home/xp/src/ghc-api-proxy-py-integrate-successor`，branch `integrate/260807-bridge-successor`，固定 `HEAD=c43db35a7a5851225b55ce31b8edbec2cf90917f`、base `80bc8f252b46c511f428af1d97159a5980ee9dc9`，目标 worktree 在评审前后均 clean。范围是三个线性 non-merge integration commits 的最终 merged state：semantic `04bdfcbf75bfa7e9709d55869c70106c49146db6`、route `088d66d3f12bd39be7ce7f61877336f490e7dbdb`、block `c43db35a7a5851225b55ce31b8edbec2cf90917f`；重点覆盖 hooks lifecycle、Responses non-stream route／header、semantic parity、parser→typed delivery、Responses stream typed reject 与 single owner／single writer。未修改目标树代码、Git ref、index、commit、branch、运行服务或数据；唯一仓库写入是本报告。
- **总体 verdict**：**可进入下一阶段。当前为 0 blocker／0 major；三个 integration commits 可按 semantic → route → block 逐片回放 main。** 每片回放前须重验当时 main preimage，回放后运行对应 main-side gate；本 verdict 不表示提交已经进入 main、完整 Responses stream 已生产接线、完整 Acceptance 为 `PASS`、部署完成或 cutover 获授权。
- **blocker 数**：0。
- **major 数**：0。
- **minor 数**：0。
- **逐片回放结论**：`04bdfcb…`、`088d66d…`、`c43db35…` 分别与 reviewed semantic／route／block source 的完整 range stable patch-id 相等，且每个 slice 的所有结果 blobs 逐路径相等。三个 source 的精确 code review 均为 `0 blocker／0 major`；semantic／route 的精确 source verification 为 `PASS`，block 轴由精确绑定当前 merged successor HEAD 的独立 verification 判为 scoped `PASS`。当前 merged-state 定向 10 smoke、完整两 smoke 文件、semantic parser unit、全仓 pytest、Ruff 与 Pyright均通过。因此允许保持现有三提交边界按顺序逐片回放，而不是把三片压成一个不可归因的整体提交。

## 双视角覆盖证据

### 机械核对

- 固定目标物理 root、branch、完整 HEAD 与 clean worktree；拓扑严格为 `80bc8f2… → 04bdfcb… → 088d66d… → c43db35…`，范围内恰有三个线性 non-merge commits。`git diff --check 80bc…c43db35…` 通过。
- Semantic integration `04bdfcb…` 与 source `80bc…f5bca39ac582911b61d278fd678ec9298ad0c08e` 完整 range stable patch-id 相等，两个结果 blob 相等。原始 code review `docs/tmp/260807-review-code-semantic-parity-r2.md` 为 `0 blocker／0 major／0 minor`、可 squash；原始 verification `docs/tmp/260807-verify-semantic-parity-r2.md` 为 `PASS`。
- Route integration `088d66d…` 与 source `80bc…dd376d6f1e9dc2997bc2f95d03a352fed4df1412` 完整三提交 range stable patch-id 相等，十个结果 blob 相等。原始 code review `docs/tmp/260807-review-code-route-happy-r3.md` 为 `0 blocker／0 major／0 minor`，明确完整三提交结果范围可 squash；原始 verification 对该 successor 为 `PASS`。
- Block integration `c43db35…` 与 source `80bc…e506bf87318424e4075b6422772ee0c7e9b8694a` 完整两提交 range stable patch-id 相等，三个结果 blob 相等。原始 source code review `docs/tmp/260807-review-code-block-delivery-r2.md` 为 `0 blocker／0 major／0 minor`、可 squash；独立 merged-state verification `docs/tmp/260807-verify-bridge-successor.md` 精确绑定 `c43db35…`，对 parser→delivery／single-writer 等本轮 scoped 轴判为 `PASS`，同时保留完整 stream `UNVERIFIED`。
- Production caller 扫描覆盖 `DeliverySession`、`InMemoryDeliverySink`、`ResponsesStreamParser`、`open_writer()`、`_finalize_failure()`、`observe_stream_finalized()` 与 `history.finalized()`。Delivery／parser 当前没有 route／pipeline production caller；`DeliverySession.__init__()` 是 sink writer 的唯一生产 owner，route 不存在第二 writer 或第二 delivery finalizer。
- 精确定义的 10 smoke 由 route 文件全部 8 项，加 parser→delivery multi-part 顺序与并发 block／terminal 单 writer 两项组成，实际执行为 `10 passed`，collect-only 为 `10 tests collected`。此外两个完整 smoke 文件实际执行／收集均为 24 项；`tests/unit/test_responses_stream_parser.py` 实际执行／收集均为 20 项；全仓 `tests` 实际执行／收集均为 468 项。四组数字均在本轮固定 HEAD 上由执行与 collect-only 两种入口交叉一致，口径分别列明，不互相替代。
- 全仓 Ruff 为 `All checks passed!`；全仓 Pyright 的工具原始摘要为 `0 errors, 0 warnings, 0 informations`。Pyright 数量未用不同原理交叉计数，只作为退出码为零的工具摘要记录。所有运行后目标 HEAD 仍为 `c43db35…`，tracked／untracked status 为空。

### 第一人称执行

- **Non-stream success**：从真实 `/v1/messages` ASGI 入口进入，model capability／override 选中 Responses 后仍走同一个 `RequestContext`、approval、attempt、`PRE_SEND`、Responses transport、response conversion、hooks `RESPONSE → FINALIZE` 与 History finalize。Responses header 先在 client 层收敛为 `request-id`／`x-request-id`／`retry-after`／`x-ratelimit-*`，route 层通用 header policy 不会重新放出 upstream `content-length`、`content-type`、`x-internal-openai` 或 cookie；成功 body 由最终 Anthropic bytes 重新计算响应元数据。
- **Non-stream upstream failure**：Responses 429 被转换为 Anthropic error envelope，保留允许的 `retry-after`，不泄漏 internal OpenAI header；pipeline 仍由同一个 attempt／context 走 `ERROR → FINALIZE` 与 History finalize，不建立旁路 owner。
- **Pre-attempt rejects**：capability missing、explicit Responses override unsupported、selected Responses stream unsupported 都在 upstream 调用前终止。统一 `_finalize_failure()` 把同一个 context 置为 failed，顺序发送 hooks `ERROR → FINALIZE`，再让 History finalize 一次；attempt 仍为空、upstream 调用为零。observer 自身失败由 hooks executor 隔离，不截断其余 observer 或 History。
- **Messages compatibility**：dual-capability `auto` 仍选现有 Messages leg，Responses route 没有改变其 payload、header 与 lifecycle owner。
- **Parser→delivery**：parser 只发布 typed `SourceOpened`、immutable `CompletedBlock`、typed unsupported 与 terminal facts；delivery 根据 parser 的 open snapshot 关闭 source、按连续 source prefix 和 content index 排序，在完整 block batch 写入成功后才推进 frontier。较晚 source 不越过较早 source，零 block source 不留下 gap，terminal open snapshot 不一致、失败／incomplete terminal、missing usage 与未提交 source prefix 都 typed reject，不能伪造 success terminal。
- **Single writer／single owner**：一个 `DeliverySession` 构造时只取得一个 writer，operation lock 串行化 block 与 terminal write，frontier 仅在 writer 接受完整 batch 后推进。route 当前对 selected Responses stream 明确 typed reject，delivery 又没有 production route caller，因此 merged state 没有第二 sink owner，也没有把 block 骨架冒充已完成 stream E2E。
- **回放流程**：先从当时真实 main 重验 `04bdfcb…` preimage，回放 semantic 并跑 semantic main-side gate；再重验 `088d66d…` preimage，回放 route 并跑 route／hooks／header gate；最后重验 `c43db35…` preimage，回放 block 并跑 parser→delivery／single-writer gate。每片保持可独立归因和回滚，最终在 main 重跑 10 smoke、全仓 pytest、Ruff、Pyright，并重新核对三个结果 blob 集合。

## 事实性发现

未发现问题。

## 主观建议

[建议] 未来真实 Responses stream route wiring — 当前 typed reject 与无 production caller 是有意边界，不是缺陷；一旦 route 开始调用 parser／delivery，现有两个独立 oracle 将不再足以证明同一请求的 lifecycle 与 delivery 所有权 — 预期影响是防止第二 finalizer、第二 writer、attempt facts 泄漏、pre-commit success bytes 与 post-commit transparent retry — 推荐届时新增从真实 `/v1/messages` stream 入口驱动同一 request owner 的 hook trace＋parser＋delivery E2E，并以删除 finalizer／旁路 typed consume／引入第二 writer 的正向变异验证其判别力。

## 结构怪味扫描

| 位置 | 怪味类型 | 处置 |
|---|---|---|
| `src/app/pipeline/executor.py:34-76,165-215,230-322` | failure finalization 调用点分布于 preparation、approval、stream gate、strategy factory、payload hook、send 与 response hook；当前由共享 `_finalize_failure()` 收敛，但未来新增 pre-attempt 分支仍可能漏接 | 本轮不阻断，现有三条真实 ASGI typed reject 与 observer-failure smoke 已覆盖已知风险；未来每新增 reject 分支必须加入 phase trace 与 exactly-once History gate |
| `src/app/delivery/anthropic_sse.py:499-680` | `manual`／`typed` 双 API 共存，未来 production driver 若调用 `deliver()`／`finish()` 可绕过 parser lifecycle facts | 本轮不阻断，mode 已机械禁止会话内混用且 production caller 为空；真实 stream wiring 只暴露 typed `consume()`，并在 merged-state review 扫描所有调用者 |
| `src/app/routes/anthropic.py:93-112` 与 `src/app/delivery/anthropic_sse.py:499-680` | route 与 delivery 尚无生产调用边，同树全绿容易被误称为 stream E2E | 本轮保留 typed stream reject，明确不外推；建立调用边时按上文新增同请求 E2E 与变异正控 |

## 结论

本轮为 **0 blocker／0 major／0 minor**。`integrate/260807-bridge-successor@c43db35a7a5851225b55ce31b8edbec2cf90917f` 的三提交 merged state 在 source provenance、完整 range patch／result blob、hooks lifecycle、Responses non-stream route／header、semantic parity、parser→typed delivery、stream typed reject、single owner／single writer及全仓回归上闭合。

**明确允许按 `04bdfcb…` semantic → `088d66d…` route → `c43db35…` block 三片顺序回放 main。** 每片须重验 preimage 并完成 main-side gate；三片回放后再做 main merged-state regression。该授权不等于完整 stream bridge `PASS`、部署完成或 cutover 授权。

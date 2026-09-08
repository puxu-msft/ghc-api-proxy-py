# 独立 forensic report 评审

评审对象：`/home/xp/src/ghc-api-proxy-py/.dev/docs/timeout-408/reports/260904-runtime-forensics.md`

评审结论：**needs-fix**。共发现 `blocker=0`、`major=2`。除下列两项外，F1、F3、F4、F5、F6、F7 在 blocker／major 门槛上均通过；F2 的汇总正确，但两条逐请求映射错误；F8 存在一次因果强度升级。

`my-agents:as-reviewer` 不在本会话可用技能清单中；本轮改用 `my-skills:qualifying-a-claim-and-its-coverage` 核验。未执行网络请求、Git 操作、配置修改或进程控制。

## Major 1——F2 中两条 TUI age 与 request id 的映射颠倒

**原文位置**

- 第 89 行宣称 10 条记录“按注册先后与 TUI 从最长到最短的 age 一一对应”。
- 第 97 行把 `1151.0s` 配给 `e628c955-db47-4f34-a1dd-2b030e861180`。
- 第 98 行把 `1148.5s` 配给 `362cc93c-5411-41ca-b0dc-6b700c1c95cd`。
- 第 104 行已经正确说明 TUI elapsed 使用 monotonic clock；因此不能在发生 clock change 时按 wall `started_at` 的先后决定这两条映射。

**复算证据**

这两条都在 02:58:49 的同一批 cancellation 中完成。对同批记录，`observation.timings.finalized_s - TUI age` 应等于“快照至最终完成”的 monotonic 间隔；其余五条 cancellation 的该值集中在 `1254.864～1255.121s`。

- `e628…` 的 `finalized_s=2403.550096`。配给 `1148.5s` 后得到 `1255.050096s`，落入同批区间；按报告配给 `1151.0s` 则得到 `1252.550096s`。
- `362c…` 的 `finalized_s=2405.982254`。配给 `1151.0s` 后得到 `1254.982254s`，落入同批区间；按报告配给 `1148.5s` 则得到 `1257.482254s`。
- Journal 在 `02:21:49.758373` 恰有一条 `Clock change detected`，紧邻两个 wall `started_at`，进一步说明此处 wall 排序不能代替 monotonic 对账。

正确映射应为：

- `1151.0s` → `362cc93c-5411-41ca-b0dc-6b700c1c95cd`，`/v1/messages`。
- `1148.5s` → `e628c955-db47-4f34-a1dd-2b030e861180`，`/v1/responses`。

**错误影响**

逐请求对账并非完全准确，两个不同 inbound route 的身份被交换；这会使后续按 age 追查 `/v1/responses` 与 `/v1/messages` 时指向错误 request id。由于两条记录均为 `H1`、最终均为 `gone/None`、`attempts=1*`，该错误不改变“10 条全部 H1”、终态汇总或 stale-attempt caveat。

**建议**

交换第 97～98 行的 request id、path 和 wall start，并把第 89 行改为明确说明映射按 monotonic residual 复算，而不是按 wall registration 顺序排列。随后复核正文中是否还有按这两个 id 推导 route 的复述。

## Major 2——F8 把未证实的 client-level reissue 写进“已成立的最小因果链”

**原文位置**

- 第 129 行把 `562707ba-…` 正确限定为“高可信的 client-level retry candidate”，并明确说不能证明。
- 第 149 行再次正确限定客户端断开的原因及 retry 行为未确认。
- 第 173 行却在“目前足以成立的最窄链条”中无条件写入“客户端另开 connection 发新 request”。
- 第 244 行又把 `562707ba-…` 是否属于同一逻辑 retry 列为未知。
- 第 313 行用“本地 request accumulation 根因已闭合”总结；若该“根因”包含第 173 行的全部箭头，其强度超过证据。

**复算证据**

- Final 408 记录的 `at` 是 `02:40:09.637`，`562707ba-…` 的 `started_at` 是 `02:40:09.960`，仅支持 `323ms` 时间邻接。
- Durable records 没有 downstream connection id、request body hash 或 logical operation id。时间邻接无法区分“同一客户端重试”“另一个逻辑调用”或“另一个客户端请求”。
- `562707ba-…` 开始于 TUI 快照之后，因此不能解释快照中既有的 `x10`。
- `10 active／5 open H1 connections` 足以推出至少 5 个 active task 已脱离原 connection，但并不推出客户端随后重发了请求。Connection 一旦关闭，clients 计数下降而旧 active entry 继续存在，单凭这一动作就已经产生 `10/5` 差额，无须任何新 request。
- 当前代码和无网络 PoC 能确认“pre-response disconnect 无人读取，旧 task 会继续运行”这一机制；它们不能补出事故现场的 client operation lineage。

**错误影响**

报告把“本地 orphan persistence 机制已确认”扩大成“客户端重试参与了本次 accumulation 的完整现场因果链已确认”。这可能让后续调查错误地关闭 client behavior／logical retry correlation，并把修复或监测范围建立在未观测的 client reissue 上。

**建议**

从第 173 行的已确认链条中删除“客户端另开 connection 发新 request”，或显式标成候选分支。第 313 行应收窄为：“当前栈的 pre-response disconnect persistence 机制已确认，且现场至少存在 5 个 detached H1 active tasks；具体 detached request ids、disconnect 时刻、client reissue lineage 仍未闭合。”这不妨碍立即修复本地 disconnect listener 缺口，也不降低该机制“强到足以据此行动”的权重。

## F1～F8 逐项核验结果

| 项目 | 判定 | 核验摘要 |
|---|---|---|
| F1 | 通过 | `x10` 确为 active registry 内该 model 的十条 entry；`5 clients` 确为 `len(Uvicorn server_state.connections)`。H11 对 pipeline 在当前 cycle 完成前返回 `PAUSED`，一条 open H1 connection 至多承载一个未完成 cycle。十条候选记录覆盖整个快照窗、全部为 `H1`，且最近一条也在快照后约 `32.277s` 才完成，因此 registry 与 connection count 的顺序读取不足以制造该差额。鸽巢推理支持“至少 5 个 task 已失去原 connection”，但不能指出是哪五个或断开原因；报告已在第 243 行保留该限定。 |
| F2 | **Major 1** | 十条总体、`14／16 attempts`、`1×408 + 1×504 + 1×200 + 7×cancelled` 均与 JSONL 一致；七条 cancellation 的 `attempts=1` 确为可能 stale 的默认值。两条近同时启动记录的 age／id 映射颠倒。 |
| F3 | 通过 | 关键 journal pair 可复算：`01:53:19.024278 → 02:39:41.742069` 的 wall delta 为 `2782.717791s`、monotonic delta 为 `3013.502073s`，差为 `-230.784282s`；`01:56:47.489868 → 02:52:06.190974` 分别为 `3318.701106s`、`3594.248742s`，差为 `-275.547636s`。第一组解释 `2988.3s` TUI age 与 wall start 的约 `230.8s` 差，第二组连同边界处约一次 clock step 解释 record 的 `3600.006864s` 与 wall `3321.978s` 的 `278.029s` 差。当前 journal 已清退早期部分，整段 `279` 次总数不能再独立重跑，但承重的两个局部计算仍完整可复算。 |
| F4 | 通过 | 以 final `at` 采用半开窗 `[04:50:54,05:10:54)` 与 `[05:11:00,05:31:00)` 可精确复现 `50／452` 条、`48 H2 + 2 unknown／444 H1 + 8 unknown`、全部 status 数、`median=211.871／18.539s`、inclusive `p95=575.645／52.723s`、`attempts>1=11／1`。 |
| F5 | 通过 | 报告明确限定 protocol change 与 restart、旧 backlog cancellation、clean-state 起点和不受控 workload 同时发生，未把窗口当单变量 A/B。复算还确认 restart batch 的 12 条 `not_started` cancellation 与 1 条 H2 `gone/200` 出现在 `05:10:54.534～05:10:54.642`，位于 H2 统计窗之外；因此表只能读作 completion-window observation，不能读作旧 generation 全部终态。报告的现有限定足以阻止 H2-only 因果结论。 |
| F6 | 通过 | Final record 的 `status_code=408`，`observation.response.error.value.code=user_request_timeout`，message 为 `Timed out reading request body. Try again, or use a smaller request size.`，且 `body_bytes.upstream_response=128`、`upstream_request=null`。源码把 SDK `APIStatusError(408)` 正规化为保留 408 的 `UpstreamError`；本地 whole-client deadline 则产生 504。故这是上游读取 proxy→upstream request body 的 timeout response，不是本地生成的 408。 |
| F7 | 通过 | 对 `detail`、`tore_after_terminal`、`replaced_failures` 重算得到 `GOAWAY=0`；仅一条事故窗外的 `RemoteProtocolError('<StreamReset …>')`；`WriteError('')` 共三条，时点与报告一致。报告明确限定 header-stage attempt error 未逐次持久化，因而只把 0 命中作为 durable-record 层的负证据，没有外推为运行时绝无 GOAWAY／ProtocolError。 |
| F8 | **Major 2** | Payload／concurrency 与 H2 flow-control 两个候选均被正确保留为未闭合，未写成远端 408 根因；但 client-level reissue 候选在第 173 行被提升进“已成立”链条，需要收窄。 |

总体上，报告的运行记录统计、clock drift、H2／H1 窗口和 408 来源判断具有较强可复算性。修正两条 request 映射，并把 client reissue 从已确认因果链退回候选后，主体结论可以成立。

受高优先级开发者指令“不得写入 report／summary／findings Markdown 文件”约束，本 subagent 未能新增协调方指定的 `/home/xp/src/ghc-api-proxy-py/.dev/docs/timeout-408/reports/260904-runtime-forensics-review-general-opus.md`；以上即供协调方原样落盘的完整评审原文。
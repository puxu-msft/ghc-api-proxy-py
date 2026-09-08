# 评审：upstream consecutive-failure backoff

- 评审时刻：2026-09-08
- 被评对象：工作区未提交 diff（非 commit）
- 对照点：当前工作树 vs HEAD，仅下列文件

## 评审范围

**在范围内**

- `src/app/pipeline/rate_limiting.py`
- `src/app/config/schema.py`（`ReactiveRateLimiterConfig` 两字段与 docstring）
- `src/app/pipeline/direct_driver/base.py`（`_handle_failure` 里对 `note_failure` 的调用）
- `src/app/server/routes/inference.py`（`_reopen` 里对 `note_failure` 的调用）
- `tests/unit/pipeline/test_rate_limiting.py`
- `tests/unit/pipeline/test_direct_driver.py`
- `tests/unit/pipeline/test_prompt_admission_driver.py`

**明确不在范围内**（同工作树里同伴的进行中改动，未读、未评）

- `src/app/protocols/responses_anthropic.py`
- `tests/unit/observability/test_response_observation_projection.py`
- `tests/unit/pipeline/test_response_observation.py`
- `Dockerfile` / `docker-compose.yml` / `.dockerignore`
- `exp/260820-h2-stream-cap/`

**判据来源**（读实现之前取的，不从实现反推）

1. 本切片设计意图（调用方给出的 7 条）：串行等待 0.5/1/2/4…；429 路径不被缩短；单 event loop、除 `acquire` 的 sleep 外无 await；`note_failure` 每失败一次；`_reopen` 用 `replay_route.provider_name` 且撕流算上游失败；duck-typed `RateLimiter` 面；配置默认不破坏现有 YAML；limiter wait 计入 attempt deadline。
2. 冻结规格 `docs/.human-controlled/upstream-retry-and-continuation.md`：「无痕重试不设冷却间隔」；429 走反应式限流器。与本切片意图矛盾，见 F4。
3. 既有契约：`Section` 为 `extra="forbid"` 且新字段有默认；每 provider 一个 `RateLimiter`（`composition.py:721`，`chain.rate_limiter_for`）；`classify` 只把 `UpstreamError` / `PipelineRetry` 当 RETRY；`observe_success` 在拿到响应头、body 交给 delivery 之前调用。

未跑测试套件（调用方声明已在跑）。溢出用 `python3 -c` 核实。未跑并发探针。

## 总体 verdict

**当前形态不建议合入。** Blocker 1，should-fix 2，nit 1。

串行 driver 重试的计时（0.5、1、2、4… 封顶 30）、与 429 `max()` 不缩短、`PipelineRetry` 排除、配置默认值、duck-type 补面，这些作为增量是对的。但 `_failure_backoff` 在持续故障下会 `OverflowError`，而这正是本功能要扛的场景。另外两条 should-fix 让「跨请求共享、指数变宽」在并发 acquire 和撕流重开上名不副实。

修掉 F1 之后，若把切片目标收成「driver 串行重试不再零间隔」，可以算一个成立的增量。若目标包含注释里写的「撕流按 widening intervals 重开」和「wait is shared across requests」，则 F2/F3 说明切片还没做完。

## Blocker 数

1

---

## Findings

### backoff-01：`_failures` 无上界，持续故障会把 `note_failure` 打成 `OverflowError`

- `severity`：blocker
- `finding_id`：backoff-01
- `primary_location`：`src/app/pipeline/rate_limiting.py:141-146`
- `related_locations`：
  - `src/app/pipeline/rate_limiting.py:181-182`（先 `+= 1` 再算 backoff）
  - `src/app/pipeline/direct_driver/base.py:471-476`（`note_failure` 在 `_handle_failure` 里无保护）
  - `src/app/server/routes/inference.py:957`

**问题**：`_failure_backoff` 写的是 `base * 2 ** (self._failures - 1)`，再 `min(..., max_sec)`。封顶发生在浮点乘法之后。Python 3 在指数 ≥ 1024 时：

```
0.5 * 2 ** 1024  →  OverflowError: int too large to convert to float
```

已用解释器核实：`2 ** 1023` 得到 `1.797…e+308`，`2 ** 1024` 抛 `OverflowError`。

`_failures` 按 provider 共享、只在 `observe_success` 清零、没有时间衰减。本功能针对的就是上游持续失败：每个 RETRY 失败都 `+= 1`。默认 `max_inflight=50` 时，即便退避已经顶在 30s，约十分钟量级的持续故障就能越过 1024；若 F2 让退避在并发下塌掉，会更快。

**失败场景**：上游持续 5xx/断连 → 某次 `note_failure` 在 `_failures += 1` 之后、`_next_allowed` 写完之前抛 `OverflowError` → `_handle_failure` 把原始 `UpstreamError` 换成未捕获的 `OverflowError` 扔出 `run()` → 该 provider 上后续失败同样炸（计数停在 ≥1024，每次 `note_failure` 都炸）→ 重试循环停掉，直到某次请求碰巧成功走到 `observe_success`，或进程重启。

**建议**：先按 `failure_backoff_max_sec` 把指数夹住（或 `_failures` 本身夹在能达到 cap 的最小整数），再做乘法；`min` 不能当防护。

---

### backoff-02：`acquire` 在 sleep 之后无条件覆盖 `_next_allowed`，并发下会抹掉别人刚推上的退避

- `severity`：should-fix（as-reviewer: major）
- `finding_id`：backoff-02
- `primary_location`：`src/app/pipeline/rate_limiting.py:151-159`
- `related_locations`：
  - `src/app/pipeline/rate_limiting.py:181-182`
  - `src/app/server/composition.py:721`（每 provider 一个实例，跨请求共享）

**问题**：单 event loop 假设对 `note_failure` 本身成立——它是同步的，中间无 await。不成立的是它和 `acquire` 的组合：

```python
wait = max(0.0, self._next_allowed - now)
if wait > 0:
    await self._sleep(wait)          # yield
self._next_allowed = self._clock() + self._spacing()  # 无条件赋值
```

`note_failure` 把退避推到 `_next_allowed` 上，正是为了让下一次 `acquire` 立刻等到。但另一个已经在 sleep 的 `acquire` 醒来后用 `_spacing()`（backoff 不在其中）覆盖 `_next_allowed`，会把睡眠期间发生的失败退避抹掉。

交错例（同一 limiter，NORMAL，spacing=0）：

1. t=1.0：请求 C 看见 `_next_allowed=1.5`，开始 sleep 0.5s
2. t=1.0：请求 B 失败，`note_failure`，`_failures=2`，`_next_allowed=2.0`
3. t=1.5：C 醒来，执行 `_next_allowed = 1.5 + 0`
4. t=1.5：请求 D 的 `acquire` 等待 0，立刻发

这是本功能要压的「上游正在挣扎、多请求同时打」的场景。串行单请求重试测不到（`test_consecutive_failures_double_the_wait_up_to_the_cap`、`test_a_failed_attempt_holds_the_next_one_back` 都是单任务）。429 路径原先也有同类覆盖，但那时 `_next_allowed` 不是新退避机制的唯一载体；现在是。

**建议**：sleep 之后改成 `max(self._next_allowed, clock() + _spacing())`，与 `note_failure` 的 `max` 同一条「只延长、不缩短」。这不会让已经睡完的请求再等一轮，但会保住给后续请求的退避。

---

### backoff-03：撕流重开路径上，响应头 `observe_success` 把 streak 清零，指数退避永不加倍

- `severity`：should-fix（as-reviewer: major）
- `finding_id`：backoff-03
- `primary_location`：`src/app/server/routes/inference.py:949-957`
- `related_locations`：
  - `src/app/pipeline/direct_driver/base.py:411`（拿到头就 `observe_success`）
  - `src/app/pipeline/rate_limiting.py:188`（`_failures = 0`）
  - `src/app/config/schema.py`（`ReactiveRateLimiterConfig` docstring：torn connection 也算连续失败）

**问题**：`_reopen` 的注释写「a stream that keeps tearing is reopened at widening intervals」。实际顺序：

1. 撕流 → `note_failure()` → `_failures=1`，`_next_allowed=now+0.5`
2. `replay_prepared` → 新 driver `acquire()` 等到 0.5s（第一次重开有间隔，这点成立）
3. 上游再次返回 200 头 → `observe_success` → `_failures=0`
4. body 再撕 → `note_failure()` → `_failures=1`，又是 0.5s

driver 在 hand-off 之前就把头当成功。撕流发生在 hand-off 之后，所以「连续撕流」在计数上永远是 streak=1。driver 循环里连头都拿不到的失败会按 0.5/1/2/4 加倍；delivery 重开这条被点名要覆盖的路径不会。

`replay_route.provider_name` 在 `inference.py:843` 赋值，闭包里可见，与 `handled.route` 一致；`rate_limiter_for` 的 key 与 `composition.py:721` 一致。调用点位置（drain 检查之后、`replay_prepared` 之前）按「撕流本身算失败」是对的。错的是成功定义和撕流 streak 打架。

**建议**（取舍交调用方）：要么让撕流 streak 在流真正结束之前不要被头清掉（`observe_success` 拆成「预算/限流模式」和「失败 streak」）；要么把 `_reopen` 注释和 schema 从「widening / torn connection」改成「每次重开固定 base，加倍只发生在拿不到头的 driver 重试」。现在代码、注释、设计意图 4 互斥。

---

### backoff-04：冻结规格仍写「无痕重试不设冷却间隔」

- `severity`：nit
- `finding_id`：backoff-04
- `primary_location`：`docs/.human-controlled/upstream-retry-and-continuation.md`（「无痕重试不设冷却间隔」）
- `related_locations`：本切片全部生产改动

**问题**：人控规格与本切片意图直接相反。评审按调用方给出的设计意图判实现，不把旧句当否决。但合入后若不改规格，下一轮会按冻结句把 backoff 判成违规。

**建议**：改规格，写明无痕重试现在经共享 limiter 退避；429 仍由反应式半边做主、backoff 只 `max` 上去。

本条不是代码缺陷。

---

## 按 7 条设计意图对过的结果

1. **串行计时 0.5/1/2/4，429 不缩短**：成立。`acquire` 的 spacing 不含 backoff；`note_failure` 推 `_next_allowed`；测试覆盖加倍、封顶、`retry_interval=10` 时 backoff 不缩短。并发下见 F2。
2. **线程/async**：`note_failure` / `observe_*` 无 await，单 loop 下自身原子。`acquire` 的 sleep 是 yield 点，见 F2。无锁，生产路径未见 `run_in_executor` 调 limiter。
3. **不双计**：成立。429/502 返回路径：`run` 里 `observe_failure`，然后 `_handle_failure` 再 `observe_failure`（旧行为）+ 一次 `note_failure`。异常路径一次 `observe_failure`（若有 status）+ 一次 `note_failure`。计数只走 `note_failure`。`PipelineRetry` 排除，与 `reason_for` 一致。
4. **`_reopen` 调用点**：`replay_route` 在作用域内且名字对；drain 后、`replay_prepared` 前记失败，与「撕流算失败」一致。指数变宽不成立，见 F3。
5. **duck-typed 面**：生产只有 `RateLimiter` 类。测试 fake（`RejectingRateLimiter`、`CountingLimiter`）已补 `note_failure`。`tests/` 下无其它 `observe_failure` 实现者会因此 AttributeError。
6. **配置**：`Section` 为 `extra="forbid"` + 两字段有默认，旧 YAML 不破。`ge=0`，`0` 关闭退避有测试。`reactive_rate_limiter` 整段在 `NOT_HOT_RELOADABLE`，新字段跟着重启，可接受。
7. **deadline**：`acquire` 仍在 `_run_attempt` 的 `timeout_at(attempt.deadline_at)` 内，与「limiter wait 计入 attempt deadline」一致。默认 `upstream_request_deadline=1200`、`failure_backoff_max_sec=30`，默认不会因退避睡过 attempt。未验证操作者把 attempt deadline 调到 ≤ max backoff 时是否会「睡死、再也 `observe_success` 不了」——标 unverified，不是本切片默认配置下的缺陷。

## 搜索面

**读过**

- 上列 7 个文件的 diff 与关键全文
- `rate_limiting.py` 全文；`direct_driver/base.py` 的 `run` / `_handle_failure` / `_prepare_and_send`
- `inference.py` `_reopen` 闭包及 `replay_route = handled.route`
- `exceptions.py` `classify` / `UpstreamTimeout`
- `chain.py:rate_limiter_for`、`composition.py:721`、`driver.py` 注入 limiter
- `delivery/stream.py` `StreamEnding.REPLAY` → `replay.reopen`
- `config/schema.py` `Section.model_config`、`UpstreamRequestTimeoutsConfig`、`NOT_HOT_RELOADABLE`
- `docs/.human-controlled/upstream-retry-and-continuation.md`
- 测试 fake：`observe_failure` / `note_failure` 实现者

**跑过**

- `git diff` 限定路径
- `python3 -c` 核实 `0.5 * 2 ** 1024` 抛 `OverflowError`
- 未跑 pytest

**没看**

- 范围内文件以外的同伴 diff
- 热重载是否重建 limiter（整段已标重启）
- 真实多任务交错（F2 由代码交错论证，未执行）
- `config.example.yaml` 是否补了新字段（不在范围内，也不构成运行时错误）

## Praise（不占 severity）

- `note_failure` 与 `observe_failure` 拆开，避免 429 返回路径把 streak 加两倍，注释把这条路径写清楚了。
- 退避用 `max` 推 `_next_allowed`、不进 `_spacing`，这样 replay 新 driver 的第一次 `acquire` 也会等；这是对的结构选择（F2 是赋值方式的洞，不是这个选择错）。
- `PipelineRetry` 排除与 `reason_for` 对齐。
- 单测覆盖了串行加倍、封顶、成功清 streak、429 不被缩短、base=0 关闭。

---

## 处置（2026-09-08，实现方）

- **backoff-01（blocker）已修**：`_failure_backoff` 先把指数钳到 64 再取幂（`rate_limiting.py`），2^64 之内不会溢出，封顶逻辑不变。新增回归测试 `test_a_streak_longer_than_the_exponent_can_survive_caps_instead_of_overflowing`（2000 次连续 note 后等待 = cap 30）。
- **backoff-02（should-fix）已修**：`acquire` 唤醒后改为 `max(_next_allowed, clock() + _spacing())`，睡眠期间其他请求 note 上的等待不再被抹掉。新增回归测试 `test_a_wait_pushed_while_another_acquire_slept_is_not_erased`（睡眠中 note → 第三次 acquire 等到被推上的等待而非 0）。
- **backoff-03（should-fix）按注释与文档修正，不改行为**：重放路径的等待确为恒定 base（每次重开的响应头成功会经 `observe_success` 清零 streak），不是 widening。已在 `_reopen` 注释、`status.md` 处置记录与候选修订文档中写明这一边界；让撕流也 widening 需要把「成功」定义改掉（响应头到达 ≠ 回合完整），牵动 reactive/proactive 两半的语义，不属本切片。若用户裁决撕流也要指数化，入口是给 `_reopen` 的 note 换一个不清零的计数来源。
- **backoff-04（nit）已在切片内处理**：`docs/.human-controlled/` 不可由 agent 修改，修订候选已写入 `.dev/human-controlled-docs-candidates/260908-upstream-retry-backoff.md`，待用户追认；`status.md` 已加 2026-09-08 处置注记。

修后验证：目标测试 104 passed（rate_limiting / direct_driver / prompt_admission_driver / retry_strategies / stream_ending），ruff 全绿，pyright（改动文件）0 error。全量回归 3459 passed / 1 failed，该 1 failed（`test_a_translated_route_is_counted_from_the_body_it_would_actually_send`）经 `git stash` 对照确认为预先存在，与本切片无关。
